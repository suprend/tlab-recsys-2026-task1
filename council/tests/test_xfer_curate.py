"""council.xfer.curate (council/runs/xfer/contract.md §3 golden test 2, §3.4, §7.2).

1. Golden test 2: council.agents.curator_stage on the saved REES46 run (cards-final.json, probes.json,
   critiques.json, reference-rb*.json) with council.evidence.curate replaced by council.xfer.curate.curate and the
   REES46 rules injected (evidence.validate_card, evidence.MAX_SECONDS, evidence.cross, evidence.twin_check) writes
   council/runs/rees46-2020/curation.json byte for byte. The REES46 step helpers are made to raise, so the bytes
   come from the xfer code. Offline as test_golden_rees46 (a copy of the run, no SQL, no probe computation, no
   LLM); a missing cached reference probe skips the test (~2 min: the card-card statistics on the stored values).
2. The xfer rules: a time limit per level, the injected functions, and stage() on synthetic run files.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_curate -v
"""
import contextlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from council import agents
from council import evidence as ev
from council.tests.test_golden_rees46 import SAVED, CacheMiss, _copy_run, offline
from council.tests.test_xfer_sandbox import CARDS, World
from council.xfer import curate, roles, sandbox


def xfer_curate(cards, probes, reference_width=None, critiques=(), cross_fn=None, reference_probes=None):
    """evidence.curate's signature over the xfer port with the REES46 rules."""
    return curate.curate(cards, probes, reference_width, critiques, cross_fn or ev.cross, reference_probes,
                         validate=ev.validate_card, max_seconds=ev.MAX_SECONDS, twin_check_fn=ev.twin_check)


def _refuse(name):
    def f(*a, **k):
        raise AssertionError(f'council.evidence.{name} was called: the xfer port must do this step')
    return f


class GoldenCuration(unittest.TestCase):
    def test_port_reproduces_rees46_curation(self):
        with tempfile.TemporaryDirectory() as d:
            _copy_run(d)
            with contextlib.ExitStack() as s:
                s.enter_context(offline(d))
                s.enter_context(mock.patch.object(ev, 'curate', xfer_curate))
                for name in ('_step1', '_filter_reference', '_dup_hplus', '_dup_cross', '_widths'):
                    s.enter_context(mock.patch.object(ev, name, _refuse(name)))
                final = agents._final_cards()
                try:
                    out = agents.curator_stage(final, agents.evidence_stage(final), agents._critiques())
                except CacheMiss as e:
                    self.skipTest(f'missing input: a cached reference probe: {e}')
            got = (Path(d) / 'curation.json').read_bytes()
        self.assertEqual(json.loads(got), out)
        self.assertEqual(got, (SAVED / 'curation.json').read_bytes())


def green(level='pair', seconds=10.0, cols=('ag_c1_a',), coverage=0.5):
    cols = list(cols)
    return dict(check=None, nondeterministic=None, error=None, per_day={'1': {}}, batch_invariant=True,
                level=level, seconds_median=seconds, columns=cols, coverage={c: coverage for c in cols},
                parity={'ok': True, 'columns': {c: {'outside': []} for c in cols}},
                r2={c: 0.1 for c in cols}, max_abs_rho={c: 0.2 for c in cols}, nearest={c: 'f1' for c in cols})


class Rules(unittest.TestCase):
    def test_time_limit_per_level(self):
        limits = {'pair': 20.0, 'user': 20.0, 'item': 60.0}
        self.assertIsNone(curate.step1(green('item', 50.0), limits))
        self.assertEqual(curate.step1(green('pair', 50.0), limits), 'median seconds 50.0 > 20')
        self.assertIn('no time limit', curate.step1(green('day', 1.0), limits))
        self.assertIsNone(curate.step1(green('pair', 50.0), 60.0))
        self.assertIn('coverage', curate.step1(green(coverage=0.001), 60.0))

    def test_reference_filter_uses_the_injected_cross(self):
        probes = {'rb1_a': green(cols=['ag_rb1_a']), 'rb1_b': green(cols=['ag_rb1_b']),
                  'rb2_c': green('item', 50.0, cols=['ag_rb2_c'])}
        seen = []

        def cross(a, b):
            seen.append((a['columns'][0], b['columns'][0]))
            return dict(max_abs_rho=0.99, r2_a_on_b={}, r2_b_on_a={})
        kept, removed = curate._filter_reference(probes, cross, {'pair': 20.0, 'item': 60.0})
        self.assertEqual(kept, [('rb1_a', 1)])
        self.assertEqual([r['table'] for r in removed], ['rb1_b', 'rb2_c'])
        self.assertEqual(seen, [('ag_rb1_b', 'ag_rb1_a'), ('ag_rb2_c', 'ag_rb1_a')])


class Stage(unittest.TestCase):
    """probe_stage -> curate.stage on the synthetic world of test_xfer_sandbox."""

    def setUp(self):
        self.w = World().__enter__()
        self.addCleanup(self.w.__exit__, None, None, None)
        self.ds = self.w.ds
        self.runs = self.ds.paths.runs
        self.runs.mkdir(parents=True)
        refs = {1: [dict(table='rb1_ucnt', level='user', sql=sandbox.to_sandbox(CARDS[0]['sql'])
                         .replace('ag_c1_uval', 'ag_rb1_uval'), columns=['ag_rb1_uval'])],
                2: [dict(table='rb2_pcnt', level='pair', sql=sandbox.to_sandbox(CARDS[1]['sql'])
                         .replace('ag_c2_pcnt', 'ag_rb2_pcnt'), columns=['ag_rb2_pcnt'])]}
        for k, props in refs.items():
            (self.runs / f'reference-rb{k}.json').write_text(json.dumps({'proposals': props}))
        self.refs = refs
        withdrawn = dict(CARDS[2], id='G3-2', name='ipop2', sql=CARDS[2]['sql'].replace('ipop', 'ipop2'),
                         twin=dict(how='time_shuffle', sql=CARDS[2]['twin']['sql'].replace('ipop', 'ipop2')))
        self.withdrawn = withdrawn
        (self.runs / 'cards-wave1.json').write_text(json.dumps({'cards': CARDS + [withdrawn]}))
        (self.runs / 'cards-final.json').write_text(json.dumps({'cards': CARDS, 'withdrawn': [{'id': 'G3-2'}]}))
        (self.runs / 'critiques.json').write_text(json.dumps({'skeptic': {'critiques': [
            dict(card='G2-1', critic='skeptic', type='LEAK', text='t', kill_test='k')]}}))
        self.ctx = contextlib.ExitStack()
        self.ctx.enter_context(mock.patch.object(ev, 'MIN_ROWS', 5))
        self.ctx.enter_context(mock.patch.object(ev, 'MIN_QUERIES', 3))
        self.addCleanup(self.ctx.close)
        sandbox.probe_stage(self.ds, CARDS + [withdrawn], refs, threads=2)

    def test_stage_writes_once(self):
        calls = []
        real = curate.curate

        def spy(cards, probes, *a, **k):
            calls.append(dict(cards=[c['id'] for c in cards], probes=sorted(probes), **k))
            return real(cards, probes, *a, **k)
        with mock.patch.object(curate, 'curate', spy):
            out = curate.stage(self.ds)
            again = curate.stage(self.ds)
        self.assertEqual(len(calls), 1)
        self.assertEqual(again, out)
        c = calls[0]
        self.assertEqual(c['cards'], ['G1-1', 'G2-1', 'G3-1', 'G3-2'])
        self.assertEqual(c['probes'], ['G1-1', 'G2-1', 'G3-1', 'G3-2'])
        self.assertEqual(list(c['reference_probes']), ['rb1_ucnt', 'rb2_pcnt'])
        self.assertEqual(c['max_seconds'], {'pair': 20.0, 'user': 20.0, 'item': 60.0})
        self.assertEqual([q['type'] for q in c['critiques']], ['LEAK', 'WITHDRAWN'])
        self.assertEqual(out['reference_order'], ['rb1_ucnt', 'rb2_pcnt'])
        for k in ('families', 'columns', 'twins', 'parity', 'reference_removed', 'removed'):
            self.assertIn(k, out)
        self.assertNotIn('G3-2', out['families'])
        text = self.ds.paths.run_file('curation.json').read_text()
        self.assertTrue(text.endswith('}\n'))
        self.assertEqual(json.loads(text), out)

    def test_curation_feeds_compute(self):
        from council.xfer import compute
        out = curate.stage(self.ds)
        # this world: three cards against two Rb columns; the parity cut drops G3-1, both twins stay
        self.assertEqual(out['families'], ['G1-1', 'G2-1'])
        self.assertEqual(out['twins'], ['G1-1', 'G2-1'])
        self.assertEqual(out['parity']['council_removed'], ['G3-1'])
        self.assertEqual(out['reference_removed'], [])
        with mock.patch.object(compute, 'BATCH_ROWS', 50):
            state = compute.stage(self.ds, threads=2)
        tables = ['g1_1', 'g2_1', 'g1_1_tw', 'g2_1_tw', 'rb1_ucnt', 'rb2_pcnt']
        self.assertEqual(list(state), tables)
        self.assertTrue(all(v['status'] == 'done' and len(v['collections']) == 4 for v in state.values()))

    def test_stale_card_probe_counts_as_none(self):
        final = json.loads((self.runs / 'cards-final.json').read_text())
        final['cards'][0] = dict(final['cards'][0], sql=final['cards'][0]['sql'].replace('- 40', '- 30'))
        (self.runs / 'cards-final.json').write_text(json.dumps(final))
        seen = {}
        with mock.patch.object(curate, 'curate', lambda cards, probes, *a, **k: seen.update(probes) or {}):
            curate.stage(self.ds)
        self.assertNotIn('G1-1', seen)
        self.assertIn('G2-1', seen)

    def test_rb_columns_must_be_the_probe_output(self):
        store = json.loads(self.ds.paths.run_file('probes.json').read_text())
        store['reference']['rb1_ucnt']['columns'] = ['ag_rb1_uval', 'ag_rb1_x']
        self.ds.paths.run_file('probes.json').write_text(json.dumps(store))
        rb = json.loads((self.runs / 'reference-rb1.json').read_text())
        rb['proposals'][0]['columns'] = ['ag_rb1_x', 'ag_rb1_uval']             # another order: accepted
        (self.runs / 'reference-rb1.json').write_text(json.dumps(rb))
        with mock.patch.object(curate, 'curate', lambda *a, **k: {}):
            curate.stage(self.ds)
        self.ds.paths.run_file('curation.json').unlink()
        rb['proposals'][0]['columns'] = ['ag_rb1_x', 'ag_rb1_y']                # other names: refused
        (self.runs / 'reference-rb1.json').write_text(json.dumps(rb))
        with self.assertRaises(SystemExit):
            curate.stage(self.ds)
        self.assertFalse(self.ds.paths.run_file('curation.json').exists())

    def test_rb_without_probe_stops(self):
        rb = json.loads((self.runs / 'reference-rb2.json').read_text())
        rb['proposals'][0]['sql'] += ' '
        (self.runs / 'reference-rb2.json').write_text(json.dumps(rb))
        with self.assertRaises(SystemExit):
            curate.stage(self.ds)
        self.assertFalse(self.ds.paths.run_file('curation.json').exists())


if __name__ == '__main__':
    unittest.main()
