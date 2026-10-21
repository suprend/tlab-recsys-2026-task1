"""council.xfer.compute on the synthetic world of test_xfer_sandbox (council/runs/xfer/contract.md §3.4, §4).

The plan order (families, twins, kept Rb), the collection order (the C_test collection first), batching, the
table manifests, the refusal to overwrite another SQL, and the stage: stress first, failed_stress stops it and
stays recorded, a finished stage recomputes nothing.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_compute -v
"""
import json
import unittest
from unittest import mock

import numpy as np

from council.tests.test_xfer_sandbox import CARDS, PROBE, S0, TEST, TRAIN, World
from council.xfer import compute, roles, sandbox
from scripts import xfer_agent as xa
from scripts import xfer_common as xc

# rb1_ab: the inner SELECT names b before a, the outer one gives a, b; reference-rb1.json lists them in the
# order of their first appearance in the SQL (b, a), the probe and xa.agent_columns see a, b.
RB = {'rb1_ab': dict(level='user', columns=['ag_rb1_b', 'ag_rb1_a'],
                     sql='WITH t AS (SELECT e.user_id, count(*)::DOUBLE AS ag_rb1_b, avg(e.value)::DOUBLE AS ag_rb1_a '
                         'FROM events e WHERE e.user_id IN (SELECT user_id FROM users) GROUP BY e.user_id) '
                         'SELECT user_id, ag_rb1_a, ag_rb1_b FROM t'),
      'rb2_gone': dict(level='item', columns=['ag_rb2_gone'],
                       sql='SELECT e.item_id, 1.0 AS ag_rb2_gone FROM events e GROUP BY e.item_id'),
      'rb2_cut': dict(level='item', columns=['ag_rb2_cut'],
                      sql='SELECT e.item_id, 2.0 AS ag_rb2_cut FROM events e GROUP BY e.item_id')}
CURATION = {'families': ['G2-1', 'G3-1'], 'columns': {'G2-1': ['ag_c2_pcnt'], 'G3-1': ['ag_c3_ipop']},
            'twins': ['G2-1'], 'parity': {'ok': True, 'reference_drop': ['rb2_cut']},
            'reference_removed': [{'table': 'rb2_gone', 'step': 1, 'reason': 'r'}],
            'reference_order': ['rb1_ab', 'rb2_gone', 'rb2_cut']}


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World().__enter__()
        self.addCleanup(self.w.__exit__, None, None, None)
        self.ds = self.w.ds
        runs = self.ds.paths.runs
        runs.mkdir(parents=True)
        (runs / 'curation.json').write_text(json.dumps(CURATION))
        (runs / 'cards-final.json').write_text(json.dumps({'cards': CARDS}))
        props = [dict(table=t, **v) for t, v in RB.items()]
        (runs / 'reference-rb1.json').write_text(json.dumps({'proposals': props[:1]}))
        (runs / 'reference-rb2.json').write_text(json.dumps({'proposals': props[1:]}))
        sandbox.probe_stage(self.ds, [], {1: props[:1]}, threads=2)       # only the kept Rb table is probed
        self.plan = compute._inputs(self.ds)


class Plan(Base):
    def test_order_and_names(self):
        self.assertEqual([e['table'] for e in self.plan], ['g2_1', 'g3_1', 'g2_1_tw', 'rb1_ab'])
        self.assertEqual([e['columns'] for e in self.plan],
                         [['ag_c2_pcnt'], ['ag_c3_ipop'], ['ag_c2_pcnt_tw'], ['ag_rb1_a', 'ag_rb1_b']])
        self.assertEqual(self.plan[0]['sql'], sandbox.to_sandbox(CARDS[1]['sql']))
        self.assertEqual(self.plan[2]['sql'], sandbox.to_sandbox(CARDS[1]['twin']['sql']))
        self.assertEqual([e['level'] for e in self.plan], ['pair', 'item', 'pair', 'user'])
        clash = dict(CURATION, columns={'G2-1': ['ag_c2_pcnt'], 'G3-1': ['ag_c2_pcnt']})
        with self.assertRaises(SystemExit):
            compute.plan(clash, CARDS, RB)
        with self.assertRaises(SystemExit):
            compute.plan({k: v for k, v in CURATION.items() if k != 'reference_order'}, CARDS, RB)

    def test_collections(self):
        got = [(phase, a, p.name) for phase, a, p in compute.collections(self.ds)]
        test_role = roles.COLLECTION_ROLES['test']
        self.assertEqual(got, [('test', TEST, f'{test_role}-{TEST}'), ('fit', TRAIN[0], f'train-{TRAIN[0]}'),
                               ('fit', TRAIN[1], f'train-{TRAIN[1]}'), ('select', S0, f'val-{S0}')])
        self.assertNotIn(PROBE, [a for _, a, _ in got])


class RbColumns(Base):
    def test_probe_order_not_the_proposal_list(self):
        e = self.plan[3]
        coll = self.w.collections[TRAIN[0]]
        keys = compute.frame_keys(coll)
        got, _ = compute.compute_table(self.ds, TRAIN[0], keys, e, threads=2)
        self.assertEqual(list(got.columns), ['user_id', 'item_id', 'ag_rb1_a', 'ag_rb1_b'])
        listed = dict(e, columns=RB['rb1_ab']['columns'])          # what the proposal file says: refused by xa
        with self.assertRaises(xa.ProposalError):
            compute.compute_table(self.ds, TRAIN[0], keys, listed, threads=2)

    def test_kept_rb_without_probe_stops(self):
        self.ds.paths.run_file('probes.json').unlink()
        with self.assertRaises(SystemExit):
            compute._inputs(self.ds)


class Tables(Base):
    def test_batches_equal_one_batch_and_values(self):
        coll = self.w.collections[TRAIN[0]]
        keys = compute.frame_keys(coll)
        views = sandbox.views_spec(self.ds, TRAIN[0], 'sidecar')
        for e in self.plan:
            whole, info = compute.compute_table(self.ds, TRAIN[0], keys, e, {}, threads=2, views=views)
            with mock.patch.object(compute, 'BATCH_ROWS', 7):
                parts, _ = compute.compute_table(self.ds, TRAIN[0], keys, e, {}, threads=2, views=views)
            self.assertEqual(list(whole.columns), ['user_id', 'item_id'] + e['columns'])
            self.assertEqual(info['rows'], len(keys))
            np.testing.assert_array_equal(whole[['user_id', 'item_id']].to_numpy(), keys.to_numpy())
            np.testing.assert_allclose(whole[e['columns']].to_numpy(), parts[e['columns']].to_numpy())
        pair, _ = compute.compute_table(self.ds, TRAIN[0], keys, self.plan[0], threads=2, views=views)
        ev_ = xc.read_parquet(self.w.events)
        n = ev_[ev_.step < TRAIN[0]].groupby(['user_id', 'item_id']).size()
        exp = [n.get((u, i), 0) for u, i in zip(pair.user_id, pair.item_id)]
        np.testing.assert_allclose(pair['ag_c2_pcnt'].to_numpy(), exp)

    def test_write_and_refuse(self):
        coll = self.w.collections[S0]
        keys = compute.frame_keys(coll)
        e = self.plan[3]
        frame, info = compute.compute_table(self.ds, S0, keys, e, threads=2)
        rec = compute.write_table(self.ds, coll, e['table'], frame, e, info, identity={'code': 'test'})
        path = self.ds.paths.table(coll.name, e['table'])
        self.assertEqual(rec['file_sha256'], xc.sha256_file(path))
        man = json.loads((self.ds.paths.sidecars / coll.name / xc.MANIFEST_FILE).read_text())
        self.assertEqual(man['format'], compute.FORMAT)
        self.assertEqual(man['collection_manifest_sha256'], xc.sha256_file(coll / xc.MANIFEST_FILE))
        self.assertEqual(man['tables'][e['table']]['columns'], e['columns'])
        self.assertTrue(compute.present(self.ds, coll, e))
        other = dict(e, sql=e['sql'] + ' ')
        with self.assertRaises(ValueError):
            compute.write_table(self.ds, coll, e['table'], frame, other, info)
        with self.assertRaises(SystemExit):
            compute.present(self.ds, coll, other)
        with self.assertRaises(ValueError):
            compute.write_table(self.ds, coll, e['table'], frame.drop(columns=e['columns']), e, info)

    def test_present_checks_the_stamp(self):
        coll = self.w.collections[S0]
        keys = compute.frame_keys(coll)
        e = self.plan[0]
        frame, info = compute.compute_table(self.ds, S0, keys, e, threads=2)
        ident = {'code': 'test'}
        compute.write_table(self.ds, coll, e['table'], frame, e, info, identity=ident)
        self.assertTrue(compute.present(self.ds, coll, e, identity=ident, rows=len(keys)))
        self.assertFalse(compute.present(self.ds, coll, e, identity={'code': 'other'}, rows=len(keys)))
        self.assertFalse(compute.present(self.ds, coll, e, identity=ident, rows=len(keys) + 1))
        path = self.ds.paths.table(coll.name, e['table'])
        good = path.read_bytes()
        path.write_bytes(good + b'x')
        self.assertFalse(compute.present(self.ds, coll, e, identity=ident, rows=len(keys)))
        path.write_bytes(good)
        man = json.loads((coll / xc.MANIFEST_FILE).read_text())
        (coll / xc.MANIFEST_FILE).write_text(json.dumps(dict(man, rebuilt=True)))
        self.assertFalse(compute.present(self.ds, coll, e, identity=ident, rows=len(keys)))


class StageRun(Base):
    def test_stress_failure_then_success(self):
        real = compute.compute_table
        calls = []

        def failing(ds, anchor, keys, entry, cache=None, **kw):
            calls.append((xc.anchor_text(anchor), entry['table']))
            if entry['table'] == 'g3_1' and xc.anchor_text(anchor) == str(TEST):
                raise MemoryError('out of memory')
            return real(ds, anchor, keys, entry, cache, **kw)
        with mock.patch.object(compute, 'compute_table', failing), mock.patch.object(compute, 'THREADS', 2):
            with self.assertRaises(SystemExit):
                compute.stage(self.ds, threads=2)
            state = json.loads(self.ds.paths.run_file('compute.json').read_text())
            self.assertEqual(state['g3_1']['status'], 'failed_stress')
            self.assertIn('MemoryError', state['g3_1']['error'])
            self.assertEqual(calls, [(str(TEST), 'g2_1'), (str(TEST), 'g3_1')])  # stress first, stop at once
            self.assertEqual(self.w.heavy_calls[-1][:2], ('compute', 'tinkoff'))
            calls.clear()
            with self.assertRaises(SystemExit):
                compute.stage(self.ds, threads=2)                      # the same SQL: refused, nothing run
            self.assertEqual(calls, [])
            state['zz_other'] = {'status': 'done'}                    # another writer's record
            self.ds.paths.run_file('compute.json').write_text(json.dumps(state))

        # the curation rebuilt without G3-1
        cur = dict(CURATION, families=['G2-1'], columns={'G2-1': ['ag_c2_pcnt']})
        self.ds.paths.run_file('curation.json').write_text(json.dumps(cur))
        with mock.patch.object(compute, 'compute_table', failing):
            state = compute.stage(self.ds, threads=2)
        tables = ['g2_1', 'g2_1_tw', 'rb1_ab']
        stress = [c for c in calls if c[0] == str(TEST)]
        self.assertEqual(stress, [(str(TEST), 'g2_1_tw'), (str(TEST), 'rb1_ab')])     # g2_1 was already there
        self.assertEqual(state['zz_other'], {'status': 'done'})
        self.assertEqual(calls[:2], stress)
        for t in tables:
            self.assertEqual(state[t]['status'], 'done')
            self.assertEqual(len(state[t]['collections']), 4)
        for _, _, coll in compute.collections(self.ds):
            man = json.loads((self.ds.paths.sidecars / coll.name / xc.MANIFEST_FILE).read_text())
            self.assertEqual(sorted(man['tables']), sorted(tables))
            for t in tables:
                got = xc.read_parquet(self.ds.paths.table(coll.name, t))
                self.assertEqual(len(got), len(compute.frame_keys(coll)))
        calls.clear()
        with mock.patch.object(compute, 'compute_table', failing):
            compute.stage(self.ds, threads=2)
        self.assertEqual(calls, [])
        self.w.ident = {'code': 'changed'}                            # another code: every table again
        with mock.patch.object(compute, 'compute_table', failing):
            state = compute.stage(self.ds, threads=2)
        self.assertEqual(len(calls), 3 * 4)
        self.assertTrue(all(state[t]['identity'] == {'code': 'changed'} for t in tables))

    def test_other_exceptions_are_not_failed_stress(self):
        with mock.patch.object(compute, 'compute_table', side_effect=RuntimeError('bug')):
            with self.assertRaises(RuntimeError):
                compute.stage(self.ds, threads=2)
        self.assertFalse(self.ds.paths.run_file('compute.json').exists())


if __name__ == '__main__':
    unittest.main()
