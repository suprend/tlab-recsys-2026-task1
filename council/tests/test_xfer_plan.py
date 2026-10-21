"""council.xfer.plan on a synthetic curation and synthetic per-query tables (contract council/runs/xfer/contract.md
§3.3, §4). The broker and fit are replaced by fakes; every file goes to a temporary Dataset.paths.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_plan -v
"""
import collections
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from council import design as D
from council.xfer import fit, plan, roles

SPEC_KEYS = ('name', 'phase', 'arm', 'seed', 'half', 'tables', 'placebo', 'selection_sha256')
CONTRACT_TEST_FITS = {'Hrp': (7, 11, 13, 17), 'SEL': (7, 11, 13, 17), 'Hr': (7, 11), 'TWIN': (7, 11),
                      'Rb1': (7,), 'Rb2': (7,)}                 # contract §3.3, the table of the 14 C_test fits


def curation(n=5, t=3):
    fams = [f'G{1 + k % 4}-{1 + k // 4}' for k in range(n)]
    return {'families': fams, 'twins': fams[:t], 'columns': {f: [f'f_x_c{f[1]}_c{k}'] for k, f in enumerate(fams)},
            'placebo': [f'f_x_c{f[1]}_c{k}' for k, f in enumerate(fams[:4])], 'placebo_families': fams[:4],
            'parity': {'ok': True, 'reference_drop': ['rb2_cut']},
            'reference_order': ['rb1_a', 'rb1_gone', 'rb2_b', 'rb2_cut'],
            'reference_removed': [{'table': 'rb1_gone', 'step': 2, 'reason': 'duplicate of H+r'}]}


N_SELECT, SIGMA_Q, DEFF = 2000, 0.05, 1.3
IDENTITY = {'code': {'x': 'y'}, 'council': {'f': 's'}}


def prereg0_stub(gate=False, path_ok=True, tolerance=None):
    """prereg-0 as plan.prereg0 writes it; the gate and its 12/4 rehearsal of the stub are not recomputed."""
    return {'power': 0.9 if gate else 0.3, 'gate': gate,
            'rule': 'SEL = ALL_P minus D' if gate else 'SEL = ALL_P by construction: power 0.300 < 0.8',
            'rehearsal': {'sd_t_interval': [0.3, 1.2]}, 'select_queries_expected': N_SELECT,
            'sigma_q': SIGMA_Q, 'deff': DEFF, 'path_ok': path_ok,
            'path_tolerance': tolerance or {'value': roles.PATH_TOL, 'reason': 'contract §3.1', 'explicit': False,
                                            'max_abs_diff': {'select': 0.0, 'test': 0.0}}}


def qids(n, per_user=2, anchor=641):
    """Unique query ids '<anchor>:<user>'; a user holds `per_user` queries on consecutive anchors (clusters)."""
    return [f'{anchor + i % per_user}:{i // per_user}' for i in range(n)]


def plan_read(names, n=2000, effects=(), seed=0):
    """qid x 48 plan fits: noise + sum of effect * column of the matrix (row r of the matrix is fit r)."""
    rng = np.random.default_rng(seed)
    x = D.matrix()
    y = 0.2 + rng.normal(0, 0.05, (n, 48))
    for col, size in effects:
        y = y + size * x[:, D.COLUMNS.index(col)][None, :]
    return pd.DataFrame(y, index=qids(n), columns=names)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snap(paths):
    out = {}
    for p in paths:
        p = Path(p)
        if not p.exists():
            out[str(p)] = None
            continue
        out[str(p)] = {str(q): q.lstat().st_mtime_ns for q in p.rglob('*')}
    return out


REAL = [d for x in roles.DATASETS for d in (roles.paths(x).runs, roles.paths(x).out)]


class TmpCase(unittest.TestCase):
    """A Dataset whose paths are a temporary directory; the real council/xfer directories must not change."""

    def setUp(self):
        self.before = snap(REAL)
        self.tmp = tempfile.TemporaryDirectory(prefix='tlab-plan-test-', dir='/tmp')
        self.root = Path(self.tmp.name)
        p = roles.paths('tinkoff', root=self.root)                       # contract §8.8: an explicit /tmp/tlab- root
        self.ds = roles.Dataset(name='tinkoff', adapter=None, anchors={}, paths=p)
        self.runs = p.runs
        self.identity = dict(IDENTITY)
        self.reads = []
        self.stops = [mock.patch.object(plan.roles, 'identity', side_effect=lambda ds: self.identity),
                      mock.patch.object(plan.broker, 'reads', side_effect=lambda ds: list(self.reads))]
        for x in self.stops:
            x.start()

    def tearDown(self):
        for x in self.stops:
            x.stop()
        self.tmp.cleanup()
        self.assertEqual(snap(REAL), self.before, 'the real council/runs/xfer-* or artifacts/council/xfer-* changed')

    def put(self, name, obj):
        self.runs.mkdir(parents=True, exist_ok=True)
        (self.runs / name).write_text(json.dumps(obj), encoding='utf-8')

    def get(self, name):
        return json.loads((self.runs / name).read_text(encoding='utf-8'))

    def files(self):
        """Every file under the temporary root, as runs/<path> or out/<path> (other/<path> elsewhere)."""
        out = []
        for q in self.root.rglob('*'):
            if q.is_file():
                for tag, base in (('runs', self.ds.paths.runs), ('out', self.ds.paths.out), ('other', self.root)):
                    if q.is_relative_to(base):
                        out.append(f'{tag}/{q.relative_to(base).as_posix()}')
                        break
        return sorted(out)


# ---------------------------------------------------------------- pure builders

class PlanSpecsTest(unittest.TestCase):
    def test_48_unique_deterministic_specs(self):
        cur = curation()
        a, b = plan.plan_specs(cur), plan.plan_specs(json.loads(json.dumps(cur)))
        self.assertEqual(json.dumps(a), json.dumps(b))
        self.assertEqual(len(a), 48)
        self.assertEqual(len({s['name'] for s in a}), 48)
        self.assertEqual(len({json.dumps(s['tables']) + json.dumps(s['placebo']) for s in a}), 48)
        self.assertEqual(plan.SPEC_KEYS, fit.SPEC_KEYS)
        for r, s in enumerate(a, start=1):
            self.assertEqual(tuple(s), SPEC_KEYS)
            self.assertEqual((s['phase'], s['arm'], s['half']), ('plan', f'r{r:02d}', roles.SELECT))
            self.assertEqual(s['seed'], 1000 + r)
            self.assertEqual(s['seed'], roles.plan_seed(r))
            self.assertEqual(s['name'], f'plan-r{r:02d}-{1000 + r}')
            self.assertIsNone(s['selection_sha256'])

    def test_tables_follow_the_matrix(self):
        cur = curation()
        x = D.matrix()
        col = {c: j for j, c in enumerate(D.COLUMNS)}
        for r, s in enumerate(plan.plan_specs(cur)):
            for k, f in enumerate(cur['families']):
                self.assertEqual(roles.family_table(f) in s['tables'], x[r, col[f'F{k + 1}']] > 0)
            for k, f in enumerate(cur['twins']):
                self.assertEqual(roles.twin_table(f) in s['tables'], x[r, col[f'T{k + 1}']] > 0)
            self.assertEqual(s['placebo'] is not None, x[r, col['PL']] > 0)
            self.assertFalse(any(t.startswith('g2_2') for t in s['tables']))           # 5 families only
            if s['placebo']:
                self.assertEqual(s['placebo'], {'tables': ['g1_1', 'g2_1', 'g3_1', 'g4_1'],
                                                'columns': ['ag_c1_c0', 'ag_c2_c1', 'ag_c3_c2', 'ag_c4_c3']})

    def test_columns_match_the_rees46_plan_on_the_same_curation(self):
        from council import plan as R
        from council import roles as R_roles
        for n, t in ((5, 3), (12, 4), (1, 0)):
            cur = curation(n, t)
            rq, _ = R._queue(cur)
            xs = plan.plan_specs(cur)
            for a, b in zip(rq, xs):
                extra = a['extra'][len(R_roles.HPLUS):]
                self.assertEqual([e.removeprefix('council_') for e in extra], b['tables'])
                self.assertEqual(a['placebo'] is None, b['placebo'] is None)
                if a['placebo']:
                    self.assertEqual([e.removeprefix('council_') for e in a['placebo']['tables']], b['placebo']['tables'])
                    self.assertEqual([roles.sandbox_column(c) for c in a['placebo']['columns']], b['placebo']['columns'])

    def test_bad_curations_and_matrices(self):
        for cur in (curation(13, 0), curation(5, 3) | {'twins': ['G4-9']}, curation(5, 3) | {'twins': ['G1-1'] * 2}):
            with self.assertRaises(ValueError):
                plan.plan_specs(cur)
        with self.assertRaises(ValueError):
            plan.plan_specs(curation(), D.matrix()[:24])

    def test_arms(self):
        a = plan.arms(curation())
        self.assertEqual(a['Hr'], [])
        self.assertEqual(a['Hrp'], ['rb1_a', 'rb2_b'])                    # removed and parity-cut tables gone
        self.assertEqual((a['Rb1'], a['Rb2']), (['rb1_a'], ['rb2_b']))
        self.assertEqual(a['ALLP'], ['g1_1', 'g2_1', 'g3_1', 'g4_1', 'g1_2'])
        with self.assertRaises(ValueError):
            plan.arms({k: v for k, v in curation().items() if k != 'reference_order'})

    def test_confirm_specs(self):
        specs = plan.confirm_specs(curation(), ['F3'])
        self.assertEqual([s['name'] for s in specs], ['confirm-ALLP-3001', 'confirm-ALLP-3002',
                                                      'confirm-SEL-3001', 'confirm-SEL-3002'])
        self.assertTrue(all(s['half'] == roles.SELECT and s['placebo'] is None for s in specs))
        self.assertIn('g3_1', specs[0]['tables'])
        self.assertNotIn('g3_1', specs[2]['tables'])
        with self.assertRaises(ValueError):
            plan.confirm_specs(curation(), ['F9'])


class TestSpecsTest(unittest.TestCase):
    SHA = 'ab' * 32
    TWIN = {'family': 'F2', 'card': 'G2-1', 'replace': ['g2_1', 'g2_1_tw']}

    def selection(self, d=(), twin=True, cut=()):
        tw = self.TWIN if twin else {'family': None, 'card': None, 'replace': None}
        return {'SEL': 'ALL_P', 'D': list(d), 'twin_arm': tw, 'cut': list(cut),
                'tables': plan._arm_tables(curation(), list(d), tw['replace'])}

    def test_14_fits_with_the_contract_seeds(self):
        specs = plan.test_specs(curation(), self.selection(), self.SHA)
        self.assertEqual(len(specs), 14)
        self.assertEqual(len({s['name'] for s in specs}), 14)
        by_arm = collections.defaultdict(list)
        for s in specs:
            by_arm[s['arm']].append(s['seed'])
            self.assertEqual(tuple(s), SPEC_KEYS)
            self.assertEqual((s['phase'], s['half'], s['placebo'], s['selection_sha256']), ('test', None, None, self.SHA))
            self.assertEqual(s['name'], f"test-{s['arm']}-{s['seed']}")
        self.assertEqual({k: tuple(v) for k, v in by_arm.items()}, CONTRACT_TEST_FITS)
        self.assertEqual(dict(roles.TEST_FITS), CONTRACT_TEST_FITS)
        t = {s['arm']: s['tables'] for s in specs}
        self.assertEqual(t['Hr'], [])
        self.assertEqual(t['Hrp'], ['rb1_a', 'rb2_b'])
        self.assertEqual((t['Rb1'], t['Rb2']), (['rb1_a'], ['rb2_b']))
        self.assertEqual(t['SEL'], ['g1_1', 'g2_1', 'g3_1', 'g4_1', 'g1_2'])
        self.assertEqual(t['TWIN'], ['g1_1', 'g2_1_tw', 'g3_1', 'g4_1', 'g1_2'])

    def test_d_adds_allp_and_no_twin_drops_twin(self):
        specs = plan.test_specs(curation(), self.selection(d=['F3']), self.SHA)
        self.assertEqual(len(specs), 16)
        t = {s['arm']: s['tables'] for s in specs}
        self.assertEqual(sorted(s['seed'] for s in specs if s['arm'] == 'ALLP'), [7, 11])
        self.assertNotIn('g3_1', t['SEL'])
        self.assertIn('g3_1', t['ALLP'])
        specs = plan.test_specs(curation(), self.selection(twin=False), self.SHA)
        self.assertEqual(len(specs), 12)
        self.assertNotIn('TWIN', {s['arm'] for s in specs})

    def test_refusals(self):
        with self.assertRaises(ValueError):
            plan.test_specs(curation(), self.selection(), 'nope')
        bad = self.selection() | {'tables': {'SEL': ['g1_1']}}
        with self.assertRaises(ValueError):
            plan.test_specs(curation(), bad, self.SHA)
        with self.assertRaises(ValueError):                              # tables are required (§9.4)
            plan.test_specs(curation(), {k: v for k, v in self.selection().items() if k != 'tables'}, self.SHA)
        with self.assertRaises(ValueError):                              # the twin family subtracted by D
            sel = self.selection() | {'D': ['F2']}
            plan.test_specs(curation(), sel, self.SHA)

    def test_cut_line(self):
        """Contract §4 items 1-3: Rb1+Rb2, then TWIN, then Hr; the H1 arms are never cut."""
        arms = lambda cut: collections.Counter(s['arm'] for s in plan.test_specs(curation(), self.selection(cut=cut),
                                                                                self.SHA))
        self.assertEqual(sum(arms(['Rb1', 'Rb2']).values()), 12)
        self.assertEqual(sum(arms(['TWIN', 'Rb2', 'Rb1']).values()), 10)
        self.assertEqual(arms(['Rb1', 'Rb2', 'TWIN', 'Hr']), {'Hrp': 4, 'SEL': 4})
        self.assertEqual(plan.check_cut(['TWIN', 'Rb2', 'Rb1']), ['Rb1', 'Rb2', 'TWIN'])
        for bad in (['Rb1'], ['TWIN'], ['Hr'], ['Rb1', 'Rb2', 'Hr'], ['Hrp'], ['SEL'], ['Rb1', 'Rb1', 'Rb2']):
            with self.assertRaises(ValueError):
                plan.check_cut(bad)
            with self.assertRaises(ValueError):
                plan.test_specs(curation(), self.selection() | {'cut': bad}, self.SHA)


# ---------------------------------------------------------------- statistics

class StatisticsTest(unittest.TestCase):
    def test_noise_summary(self):
        rng = np.random.default_rng(1)
        n = 20000
        mu = rng.normal(0.3, 0.2, n)
        y = pd.DataFrame({'noise-Hr-7': mu + rng.normal(0, 0.05, n), 'noise-Hr-11': mu + 0.001 + rng.normal(0, 0.05, n)},
                         index=[f'641:{i}' for i in range(n)])
        s = plan.noise_summary(y)
        self.assertEqual((s['queries'], s['users']), (n, n))
        self.assertAlmostEqual(s['sigma_q'], 0.05, delta=0.002)
        self.assertAlmostEqual(s['deff'], 1.0, places=9)                  # one query per user
        self.assertAlmostEqual(s['seed_mean_shift_abs'], 0.001, delta=0.0015)
        with self.assertRaises(ValueError):
            plan.noise_summary(y.assign(x=1.0))

    def test_power_gate(self):
        low = plan.power_gate(20000, 0.06, 1.5)                          # mid power: the rows differ beyond MC noise
        self.assertFalse(low['gate'])
        self.assertIn('SEL = ALL_P by construction', low['rule'])
        self.assertEqual((low['n_select'], low['rehearsal']['n_q'], low['rehearsal']['deff']), (20000, 20000, 1.5))
        self.assertEqual(set(low['sensitivity']), {'deff1', 'sigma_fit_1', 'beta_-0.001'})
        # the design effect, the fit noise and a smaller harm move the power the way they must
        self.assertGreater(low['sensitivity']['deff1']['power'], low['power'])
        self.assertLess(low['sensitivity']['sigma_fit_1']['power'], low['power'])
        self.assertGreater(low['sensitivity']['beta_-0.001']['power'], low['power'])
        self.assertGreater(plan.power_gate(40000, 0.06, 1.5)['power'], low['power'])
        high = plan.power_gate(200000, 0.06, 1.0)
        self.assertTrue(high['gate'])
        self.assertGreaterEqual(high['power'], D.POWER_GATE)
        json.dumps(low)
        with self.assertRaises(ValueError):
            plan.power_gate(1, 0.06, 1.0)

    def test_mechanism_repeat(self):
        rng = np.random.default_rng(3)
        n = 3000
        base = rng.normal(0.2, 0.05, (n, 1))
        y = pd.DataFrame(np.hstack([base + 0.01 + rng.normal(0, 0.01, (n, 2)), base + rng.normal(0, 0.01, (n, 2))]),
                         index=qids(n), columns=['test-SEL-7', 'test-SEL-11', 'test-TWIN-7', 'test-TWIN-11'])
        sel, tw = ['test-SEL-7', 'test-SEL-11'], ['test-TWIN-7', 'test-TWIN-11']
        up = plan.mechanism_repeat(y, sel, tw, +0.004, n_boot=500)
        self.assertTrue(up['repeated'])
        self.assertGreater(up['lower'], 0)
        self.assertFalse(plan.mechanism_repeat(y, sel, tw, -0.004, n_boot=500)['repeated'])
        self.assertFalse(plan.mechanism_repeat(y, tw, sel, +0.004, n_boot=500)['repeated'])
        row = {'t': 3.0, 'beta': 0.004, 't_family': 2.5}
        self.assertEqual(plan.mechanism_class(row, True), D.MECHANISM)
        self.assertEqual(plan.mechanism_class(row, False), D.NOT_DISTINGUISHED)
        self.assertEqual(plan.mechanism_class(row | {'t': 1.0}, False), D.FORM)


# ---------------------------------------------------------------- stages on a temporary Dataset.paths

PATH = [{'name': 'path_select-Hr-2026'}, {'name': 'path_test-Hr-2026'}]
NOISE = [{'name': 'noise-Hr-7'}, {'name': 'noise-Hr-11'}]


class Prereg0Test(TmpCase):
    def noise(self, n=6000):
        rng = np.random.default_rng(5)
        mu = rng.normal(0.3, 0.2, n)
        return pd.DataFrame({'noise-Hr-7': mu + rng.normal(0, 0.06, n), 'noise-Hr-11': mu + rng.normal(0, 0.06, n)},
                            index=qids(n))

    def patches(self, noise_explore, diff=0.0, same=True, records=True):
        recs = {s['name']: {'spec': s, 'data': {'tables': {}}, 'identity': {'code': 'c'}, 'peak_rss_gb': 3.0}
                for s in PATH + NOISE} if records else {}
        check = lambda ds, kind: {'kind': kind, 'max_abs_diff': diff if kind == 'select' else 0.0,
                                  'same_queries': same if kind == 'select' else True,
                                  'ok': bool(same and diff <= roles.PATH_TOL)}
        return [mock.patch.object(plan.fit, 'path_specs', return_value=PATH),
                mock.patch.object(plan.fit, 'noise_specs', return_value=NOISE),
                mock.patch.object(plan.fit, 'records', return_value=recs),
                mock.patch.object(plan.broker, 'path_check', side_effect=check),
                mock.patch.object(plan.broker, 'noise_explore', side_effect=noise_explore),
                mock.patch.object(plan, 's0_users', return_value=np.arange(10602)),
                mock.patch.object(plan.roles, 'identity', return_value={'code': {'x': 'y'}, 'council': {'f': 's'}})]

    def run_with(self, patches, fn):
        for p in patches:
            p.start()
        try:
            return fn()
        finally:
            for p in patches:
                p.stop()

    def test_writes_prereg0_and_the_kept_read_only(self):
        calls = []
        noise = self.noise()

        def explore(ds, names):
            calls.append(list(names))
            return noise
        for what, gb in (('fit noise-Hr-7', 7.5), ('fit path_test-Hr-2026', 6.0), ('fit plan-r01-1001', 19.0)):
            plan.Q.journal(self.ds.paths.queue_log, {'event': 'end', 'what': what, 'peak_gb': gb})
        out = self.run_with(self.patches(explore), lambda: plan.prereg0(self.ds))
        self.assertEqual(self.files(), ['out/noise-read.parquet', 'runs/prereg-0.json', 'runs/queue.jsonl'])
        self.assertEqual(out['peak_gb'], 7.5)
        self.assertEqual(calls, [['noise-Hr-7', 'noise-Hr-11']])
        p0 = self.get('prereg-0.json')
        self.assertEqual(p0, json.loads(json.dumps(out, default=plan._default)))
        n_b = int((roles.halves(np.arange(10602)) == roles.SELECT).sum())
        self.assertEqual(p0['select_queries_expected'], n_b)
        self.assertEqual(p0['explore_queries'], 6000)
        self.assertEqual(p0['users'], 3000)
        self.assertAlmostEqual(p0['sigma_q'], 0.06, delta=0.003)
        self.assertFalse(p0['gate'])                                    # §6.5: expected to fail
        self.assertEqual(p0['rehearsal']['n_q'], n_b)
        self.assertTrue(p0['path_ok'])
        self.assertIsNone(p0['deviation_6_8'])
        self.assertFalse(p0['path_tolerance']['explicit'])
        n_a = 10602 - n_b                                               # §9.6: S0-explore is half A of the frame
        self.assertEqual(p0['explore_check'], {'frame_half_users': n_a, 'explore_queries': 6000,
                                               'equal': n_a == 6000})
        self.assertEqual(p0['identity'], {'code': {'x': 'y'}, 'council': {'f': 's'}})
        self.assertEqual(set(p0['fits']), {'path_select-Hr-2026', 'path_test-Hr-2026', 'noise-Hr-7', 'noise-Hr-11'})
        for key in ('expected_gate', 'shares_before_test', 'sensitivity', 'rule'):
            self.assertIn(key, p0)
        # written once; the noise read is never repeated, even when prereg-0 is rebuilt
        once = lambda ds, names: self.fail('second noise read')
        with self.assertRaises(SystemExit):
            self.run_with(self.patches(once), lambda: plan.prereg0(self.ds))
        (self.runs / 'prereg-0.json').unlink()
        again = self.run_with(self.patches(once), lambda: plan.prereg0(self.ds))
        self.assertEqual(again['sigma_q'], p0['sigma_q'])

    def test_path_failure_stops_before_the_noise(self):
        no = lambda *a: self.fail('noise read after a failed path check')
        for kw in ({'same': False}, {'diff': float('inf')}, {'diff': float('nan')}, {'diff': 3e-6}):
            with self.subTest(**{k: str(v) for k, v in kw.items()}), self.assertRaises(SystemExit):
                self.run_with(self.patches(no, **kw), lambda: plan.prereg0(self.ds))
            self.assertEqual(self.files(), [])
        tol = self.runs / plan.PATH_TOLERANCE
        for bad in ({'path_tolerance': 1e-6, 'reason': 'catboost threads'},          # below the measured 3e-6
                    {'path_tolerance': 1e-5, 'reason': ' '}, {'path_tolerance': 'x', 'reason': 'r'}):
            self.put(plan.PATH_TOLERANCE, bad)
            with self.assertRaises(SystemExit):
                self.run_with(self.patches(no, diff=3e-6), lambda: plan.prereg0(self.ds))
        self.put(plan.PATH_TOLERANCE, {'path_tolerance': 1e-5, 'reason': 'catboost threads: order of sums'})
        with self.assertRaises(SystemExit):                              # another query set: no tolerance helps
            self.run_with(self.patches(no, diff=3e-6, same=False), lambda: plan.prereg0(self.ds))
        self.assertEqual(self.files(), ['runs/path-tolerance.json'])
        p0 = self.run_with(self.patches(lambda ds, names: self.noise(), diff=3e-6), lambda: plan.prereg0(self.ds))
        self.assertFalse(p0['path_ok'])
        self.assertEqual(p0['path_tolerance']['value'], 1e-5)
        self.assertTrue(p0['path_tolerance']['explicit'])
        self.assertEqual(p0['path_tolerance']['file_sha256'], sha(tol))
        self.assertEqual(p0['deviation_6_8']['select'], 3e-6)
        self.assertIn('catboost', p0['deviation_6_8']['reason'])

    def test_no_records_no_read(self):
        no = lambda *a: self.fail('read without the fit records')
        ps = self.patches(no, records=False)
        ps[3] = mock.patch.object(plan.broker, 'path_check', side_effect=no)
        with self.assertRaises(SystemExit):
            self.run_with(ps, lambda: plan.prereg0(self.ds))
        self.assertEqual(self.files(), [])

    def test_path_queue(self):
        with mock.patch.object(plan.fit, 'path_specs', return_value=PATH), \
                mock.patch.object(plan.fit, 'noise_specs', return_value=NOISE):
            self.assertEqual(plan.path_queue(self.ds), PATH + NOISE)
            plan.path_queue(self.ds)                                    # the same content: no-op
        self.assertEqual(self.files(), ['runs/queue-path.json'])
        self.assertEqual(self.get('queue-path.json'), PATH + NOISE)
        with mock.patch.object(plan.fit, 'path_specs', return_value=PATH[:1]), \
                mock.patch.object(plan.fit, 'noise_specs', return_value=NOISE), self.assertRaises(SystemExit):
            plan.path_queue(self.ds)


class BuildAnalyzeSelectTest(TmpCase):
    def build(self, cur=None, p0=None):
        self.put('curation.json', cur or curation())
        self.put('prereg-0.json', p0 or prereg0_stub())
        return plan.build(self.ds)

    def names(self):
        return [s['name'] for s in self.get('queue-plan.json')]

    def analyze(self, y):
        with mock.patch.object(plan.broker, 'y_select', return_value=y) as m:
            res = plan.analyze(self.ds)
        return res, m

    def test_build_writes_only_into_the_given_paths(self):
        pre = self.build()
        self.assertEqual(self.files(), ['runs/curation.json', 'runs/prereg-0.json', 'runs/prereg-2.json',
                                        'runs/queue-plan.json'])
        self.assertEqual(self.get('queue-plan.json'), plan.plan_specs(curation()))
        self.assertEqual(pre['matrix_sha256'], hashlib.sha256(D.matrix().tobytes()).hexdigest())
        self.assertEqual(pre['curation_sha256'], sha(self.runs / 'curation.json'))
        self.assertEqual(pre['empty'], [f'F{k}' for k in range(6, 13)] + ['T4'] + D.EMPTIES)
        self.assertEqual(pre['columns'], D.COLUMNS)
        self.assertEqual(pre['seeds']['plan-r07-1007'], 1007)
        self.assertEqual(pre['twins']['T2'], {'family': 'F2', 'card': 'G2-1', 'table': 'g2_1_tw'})
        self.assertEqual(pre['tables_over_hr'], {'Hr': 0, 'Hrp': 2, 'ALLP': 5, 'Rb1': 1, 'Rb2': 1})
        self.assertIn('SEL = ALL_P', pre['rule'])
        self.assertEqual(pre['identity'], IDENTITY)
        self.assertEqual(self.get('prereg-2.json'), pre)
        before = snap([self.runs])
        plan.build(self.ds)                                              # idempotent
        self.assertEqual(snap([self.runs]), before)
        self.put('curation.json', curation(6, 3))                        # another curation over a built plan
        with self.assertRaises(SystemExit):
            plan.build(self.ds)

    def test_rehearsal_on_the_actual_layout(self):
        """§9.1: the calibration interval of a 5/3 curation is not the one of 12/4; analyze takes the 5/3 one."""
        pre = self.build()
        own = D.rehearse(N_SELECT, SIGMA_Q, deff=DEFF, beta_harm=D.BETA_HARM, n_families=5, n_twins=3)
        full = D.rehearse(N_SELECT, SIGMA_Q, deff=DEFF, beta_harm=D.BETA_HARM)
        self.assertEqual(pre['rehearsal']['sd_t_interval'], list(own['sd_t_interval']))
        self.assertNotEqual(own['sd_t_interval'], full['sd_t_interval'])
        self.assertEqual(pre['rehearsal']['power'], own['power'])
        self.assertEqual((pre['rehearsal']['n_q'], pre['rehearsal']['deff']), (N_SELECT, DEFF))
        self.assertEqual(pre['rehearsal']['layout'], {'n_families': 5, 'n_twins': 3})
        self.assertEqual(pre['power_gate']['sd_t_interval'], [0.3, 1.2])          # the gate of prereg-0 stays
        res, _ = self.analyze(plan_read(self.names()))
        self.assertEqual(list(res['calibration']['interval']), pre['rehearsal']['sd_t_interval'])
        self.assertNotIn('thresholds', res)

    def test_no_placebo_puts_pl_into_the_empties(self):
        cur = curation(5, 3) | {'placebo': [], 'placebo_families': []}
        pre = self.build(cur)
        self.assertIsNone(pre['placebo'])
        self.assertEqual(pre['empty'], [f'F{k}' for k in range(6, 13)] + ['T4', 'PL'] + D.EMPTIES)
        self.assertTrue(all(s['placebo'] is None for s in self.get('queue-plan.json')))
        res, _ = self.analyze(plan_read(self.names()))
        self.assertEqual(res['beta']['PL']['what'], 'empty')
        self.assertNotIn('PL', res['wy_harm'])

    def test_build_refuses_a_failed_path_without_a_tolerance(self):
        tol = {'value': roles.PATH_TOL, 'reason': 'contract §3.1', 'explicit': False, 'max_abs_diff': {'select': 3e-6}}
        with self.assertRaises(SystemExit):
            self.build(p0=prereg0_stub(path_ok=False, tolerance=tol))
        with self.assertRaises(SystemExit):                              # a tolerance below the difference
            self.build(p0=prereg0_stub(path_ok=False, tolerance=tol | {'value': 1e-6, 'explicit': True}))
        self.assertFalse((self.runs / 'prereg-2.json').exists())
        pre = self.build(p0=prereg0_stub(path_ok=False, tolerance=tol | {'value': 1e-5, 'explicit': True,
                                                                          'reason': 'catboost threads'}))
        self.assertEqual(len(pre['families']), 5)

    def test_analyze_refuses_another_code(self):
        self.build()
        self.identity = {'code': {'x': 'z'}, 'council': {'f': 's'}}
        with mock.patch.object(plan.broker, 'y_select', side_effect=AssertionError('read')), \
                self.assertRaises(SystemExit):
            plan.analyze(self.ds)
        self.assertFalse((self.runs / 'plan-result.json').exists())

    def test_select_cut_plan(self):
        """§4 items 4-5: the plan did not start in time - SEL = ALL_P without plan-result and without a twin."""
        self.build()
        with mock.patch.object(plan.broker, 'y_select', side_effect=AssertionError('read')):
            sel = plan.select(self.ds, cut=['Rb1', 'Rb2'], cut_plan=True)
        self.assertEqual((sel['SEL'], sel['D'], sel['nominated']), ('ALL_P', [], None))
        self.assertIn('§4 п. 4/5', sel['reason'])
        self.assertEqual(sel['twin_arm'], {'family': None, 'card': None, 'replace': None})
        self.assertNotIn('TWIN', sel['tables'])
        self.assertEqual((sel['cut'], sel['cut_plan'], sel['plan_result_sha256']), (['Rb1', 'Rb2'], True, None))
        self.assertEqual(sel['prereg2_sha256'], sha(self.runs / 'prereg-2.json'))
        specs = plan.test_specs(curation(), sel, sha(self.ds.paths.selection))
        self.assertEqual(collections.Counter(s['arm'] for s in specs), {'Hrp': 4, 'SEL': 4, 'Hr': 2})

    def test_select_cut_plan_needs_prereg2_and_no_plan_result(self):
        self.put('curation.json', curation())
        with self.assertRaises(SystemExit):
            plan.select(self.ds, cut_plan=True)
        self.build()
        self.analyze(plan_read(self.names()))
        with self.assertRaises(SystemExit):
            plan.select(self.ds, cut_plan=True)
        with self.assertRaises(ValueError):
            plan.select(self.ds, cut=['Hr'])
        self.assertFalse(self.ds.paths.selection.exists())

    def test_build_needs_prereg0(self):
        self.put('curation.json', curation())
        with self.assertRaises(SystemExit):
            plan.build(self.ds)
        self.assertEqual(self.files(), ['runs/curation.json'])

    def test_analyze_and_select_with_the_gate_failed(self):
        self.build()
        names = self.names()
        res, m = self.analyze(plan_read(names, effects=(('F2', 0.004), ('T1', 0.003))))
        self.assertEqual(m.call_args.args, (self.ds, names))
        self.assertGreater(res['beta']['F2']['t'], 2)
        self.assertAlmostEqual(res['beta']['F2']['beta'], 0.004, delta=0.002)
        self.assertEqual(res['beta']['F2']['what'], 'g2_1')
        self.assertEqual(res['beta']['T1']['what'], 'g1_1_tw')
        self.assertEqual(res['beta']['E1']['what'], 'empty')
        self.assertEqual(res['twin_arm_family'], 'F2')                   # largest t(beta_g - beta_twin)
        self.assertEqual(self.get('plan-result.json'), json.loads(json.dumps(res, default=plan._default)))
        self.assertFalse((self.runs / 'queue-confirm.json').exists())
        with mock.patch.object(plan.broker, 'y_select', side_effect=AssertionError('no confirmation read')):
            sel = plan.select(self.ds)
        self.assertEqual((sel['SEL'], sel['D']), ('ALL_P', []))
        self.assertIn('power gate failed', sel['reason'])
        self.assertEqual(sel['twin_arm'], {'family': 'F2', 'card': 'G2-1', 'replace': ['g2_1', 'g2_1_tw']})
        self.assertEqual(sel['tables']['TWIN'], ['g1_1', 'g2_1_tw', 'g3_1', 'g4_1', 'g1_2'])
        self.assertEqual(sel['curation_sha256'], sha(self.runs / 'curation.json'))
        self.assertEqual(sel['prereg2_sha256'], sha(self.runs / 'prereg-2.json'))
        self.assertEqual(sel['plan_result_sha256'], sha(self.runs / 'plan-result.json'))
        self.assertEqual((sel['cut'], sel['cut_plan']), ([], False))
        self.assertEqual(self.get('selection.json'), sel)
        s = sha(self.ds.paths.selection)
        specs = plan.test_specs(curation(), self.get('selection.json'), s)
        self.assertEqual(len(specs), 14)
        self.assertTrue(all(x['selection_sha256'] == s for x in specs))
        with self.assertRaises(SystemExit):
            plan.select(self.ds)                                         # written once
        with self.assertRaises(SystemExit):
            self.analyze(plan_read(names))                               # the plan result is frozen
        self.assertEqual(sha(self.ds.paths.selection), s)

    def test_analyze_refuses_an_edited_queue(self):
        self.build()
        q = self.get('queue-plan.json')
        q[0], q[1] = q[1], q[0]
        self.put('queue-plan.json', q)
        with mock.patch.object(plan.broker, 'y_select', side_effect=AssertionError('read')), \
                self.assertRaises(SystemExit):
            plan.analyze(self.ds)
        self.assertFalse((self.runs / 'plan-result.json').exists())

    def test_analyze_refuses_another_matrix(self):
        self.build()
        flipped = D.matrix()[::-1].copy()
        with mock.patch.object(plan.D, 'matrix', return_value=flipped), \
                mock.patch.object(plan.broker, 'y_select', side_effect=AssertionError('read')), \
                self.assertRaises(SystemExit):
            plan.analyze(self.ds)

    def test_analyze_refuses_another_curation(self):
        self.build()
        cur = curation()
        cur['warnings'] = ['edited after prereg-2']
        self.put('curation.json', cur)
        with mock.patch.object(plan.broker, 'y_select', side_effect=AssertionError('read')), \
                self.assertRaises(SystemExit):
            plan.analyze(self.ds)

    def test_gate_passed_d_confirmed(self):
        self.build(p0=prereg0_stub(gate=True))
        res, _ = self.analyze(plan_read(self.names(), effects=(('F3', -0.02), ('F2', 0.004))))
        self.assertTrue(res['calibration']['passed'])
        self.assertIn('отклонение 4', res['thresholds'])                 # §6.1: the thresholds are absolute
        self.assertEqual(res['D'], ['F3'])
        conf = self.get('queue-confirm.json')
        self.assertEqual(conf, plan.confirm_specs(curation(), ['F3']))
        names = [s['name'] for s in conf]
        rng = np.random.default_rng(9)
        n = 2000
        base = rng.normal(0.2, 0.05, (n, 1))
        y = pd.DataFrame(np.hstack([base + rng.normal(0, 0.01, (n, 2)), base + 0.01 + rng.normal(0, 0.01, (n, 2))]),
                         index=qids(n), columns=names)
        with mock.patch.object(plan.broker, 'y_select', return_value=y) as m:
            sel = plan.select(self.ds)
        self.assertEqual(m.call_args.args, (self.ds, names))
        self.assertTrue(sel['confirmation']['confirmed'])
        self.assertEqual((sel['SEL'], sel['D']), ('ALL_P minus D', ['F3']))
        self.assertNotIn('g3_1', sel['tables']['SEL'])
        self.assertNotEqual(sel['twin_arm']['family'], 'F3')
        specs = plan.test_specs(curation(), sel, sha(self.ds.paths.selection))
        self.assertEqual(len(specs), 16)

    def test_gate_passed_d_not_confirmed(self):
        self.build(p0=prereg0_stub(gate=True))
        self.analyze(plan_read(self.names(), effects=(('F3', -0.02),)))
        names = [s['name'] for s in self.get('queue-confirm.json')]
        y = plan_read(names + [f'x{i}' for i in range(44)])[names]
        with mock.patch.object(plan.broker, 'y_select', return_value=y):
            sel = plan.select(self.ds)
        self.assertEqual((sel['SEL'], sel['D'], sel['nominated']), ('ALL_P', [], ['F3']))


class TestQueueAndReadTest(TmpCase):
    TWIN = {'family': 'F2', 'card': 'G2-1', 'replace': ['g2_1', 'g2_1_tw']}

    def setUp(self):
        super().setUp()
        self.select()

    def select(self, cut=()):
        """curation, prereg-2, plan-result and the selection.json bound to them by sha (as plan.select writes)."""
        cur = curation()
        self.put('curation.json', cur)
        self.put('prereg-2.json', {'identity': IDENTITY})
        self.put('plan-result.json', {'mechanism': [
            {'family': 'F1', 'twin': 'T1', 'beta': 0.0, 'beta_twin': 0.0, 'diff': 0.0, 'se': 1, 't': 0.1, 't_family': 0},
            {'family': 'F2', 'twin': 'T2', 'beta': 0.004, 'beta_twin': 0.0, 'diff': 0.004, 'se': 0.001, 't': 4.0,
             't_family': 3.0}]})
        self.put('selection.json', {'SEL': 'ALL_P', 'D': [], 'twin_arm': self.TWIN, 'cut': list(cut),
                                    'tables': dict(plan.arms(cur), SEL=plan.sel_tables(cur, []),
                                                   TWIN=['g1_1', 'g2_1_tw', 'g3_1', 'g4_1', 'g1_2']),
                                    **plan._shas(self.ds)})
        self.sha = sha(self.ds.paths.selection)

    def queue(self, marker):
        with mock.patch.object(plan.broker, 'selection_sha', return_value=self.sha), \
                mock.patch.object(plan.broker, 'marker', return_value=marker):
            return plan.test_queue(self.ds)

    def test_queue_needs_the_marker_with_the_same_sha(self):
        with self.assertRaises(SystemExit):
            self.queue(None)
        with self.assertRaises(SystemExit):
            self.queue({'what': 'test.started', 'selection_sha256': 'cd' * 32})
        self.assertFalse((self.runs / 'queue-test.json').exists())
        specs = self.queue({'what': 'test.started', 'selection_sha256': self.sha})
        self.assertEqual(len(specs), 14)
        self.assertEqual(self.get('queue-test.json'), specs)
        self.assertTrue(all(s['selection_sha256'] == self.sha for s in specs))

    def read(self, y, c_test=None):
        with mock.patch.object(plan.broker, 'selection_sha', return_value=self.sha), \
                mock.patch.object(plan.broker, 'c_test', side_effect=c_test or (lambda ds, names: y[names])), \
                mock.patch.object(plan.broker, 'target_shares', return_value={'select': 0.5, 'test': 0.4}):
            return plan.read_test(self.ds)

    def c_test_read(self, names, n=3000):
        rng = np.random.default_rng(11)
        base = rng.normal(0.2, 0.05, (n, 1))
        cols = {nm: base[:, 0] + rng.normal(0, 0.01, n) + (0.01 if '-SEL-' in nm else 0.0) for nm in names}
        return pd.DataFrame(cols, index=qids(n, anchor=671))

    def test_read_test_once(self):
        specs = self.queue({'what': 'test.started', 'selection_sha256': self.sha})
        names = [s['name'] for s in specs]
        y = self.c_test_read(names)
        out = self.read(y)
        self.assertEqual(out['h1']['verdict'], D.BEATS)
        self.assertEqual(out['h1']['n_pairs'], 4)
        self.assertEqual(out['mechanism']['family'], 'F2')
        self.assertTrue(out['mechanism']['repeat']['repeated'])
        self.assertEqual(out['mechanism']['class'], D.MECHANISM)
        self.assertIn('H+r⁺ − H+r (кривая объёма)', out['contrasts'])
        self.assertIn('H+Rb2 − H+Rb1 (генерация и ширина)', out['contrasts'])
        for what in ('H+Rb1 − H+r (зерно 7)', 'H+Rb2 − H+r (зерно 7)'):            # REES46 contrasts
            self.assertEqual(out['contrasts'][what]['by_seed'].__len__(), 1)
        self.assertNotIn('SEL − ALL_P (вычитание D)', out['contrasts'])
        self.assertNotIn('ALL_P − H+r (вклад совета)', out['contrasts'])
        self.assertEqual(out['target_shares'], {'select': 0.5, 'test': 0.4})
        self.assertTrue(out['test'].startswith('повторный'))
        kept = self.ds.paths.out / plan.TEST_READ.format(sha=self.sha[:16])
        self.assertTrue(kept.exists())
        self.reads = [{'what': 'c_test'}]                                 # logged by the broker: the kept read is used
        again = self.read(y, c_test=lambda *a: self.fail('second C_test read'))
        self.assertEqual(again, out)

    def test_cut_from_the_selection_only(self):
        specs = self.queue({'what': 'test.started', 'selection_sha256': self.sha})
        no = lambda *a: self.fail('read with a queue cut by hand')
        self.put('queue-test.json', [s for s in specs if s['arm'] not in ('Rb1', 'Rb2', 'TWIN')])
        with self.assertRaises(SystemExit):                              # §9.3: the cut is in selection.json
            self.read(None, c_test=no)
        (self.runs / 'queue-test.json').unlink()
        self.select(cut=['Rb1', 'Rb2', 'TWIN'])
        cut = self.queue({'what': 'test.started', 'selection_sha256': self.sha})
        self.assertEqual(collections.Counter(s['arm'] for s in cut), {'Hrp': 4, 'SEL': 4, 'Hr': 2})
        out = self.read(self.c_test_read([s['name'] for s in cut]))
        self.assertEqual(out['cut'], ['Rb1', 'Rb2', 'TWIN'])
        self.assertNotIn('H+Rb2 − H+Rb1 (генерация и ширина)', out['contrasts'])
        self.assertIn('SEL − H+r', out['contrasts'])
        self.assertIsNone(out['mechanism']['repeat'])

    def test_files_bound_to_the_selection(self):
        """§9.4: curation, prereg-2 and plan-result must be the files selection.json names, before any read."""
        marker = {'what': 'test.started', 'selection_sha256': self.sha}
        specs = self.queue(marker)
        no = lambda *a: self.fail('read with a changed plan-result')
        for name, edit in (('plan-result.json', lambda o: o | {'D': ['F1']}),
                           ('prereg-2.json', lambda o: o | {'empty': []}),
                           ('curation.json', lambda o: o | {'warnings': ['x']})):
            before = self.get(name)
            self.put(name, edit(before))
            with self.subTest(name), self.assertRaises(SystemExit):
                self.read(None, c_test=no)
            (self.runs / 'queue-test.json').unlink()
            with self.subTest(name), self.assertRaises(SystemExit):
                self.queue(marker)
            self.put(name, before)
            self.put('queue-test.json', specs)
        selection = self.get('selection.json')
        del selection['plan_result_sha256']
        self.put('selection.json', selection)
        with self.assertRaises(SystemExit):
            self.read(None, c_test=no)

    def test_another_code_refuses_the_read(self):
        self.queue({'what': 'test.started', 'selection_sha256': self.sha})
        self.identity = {'code': {'x': 'z'}, 'council': {'f': 's'}}
        with self.assertRaises(SystemExit):
            self.read(None, c_test=lambda *a: self.fail('read with another code'))

    def test_logged_c_test_without_the_kept_read_stops(self):
        """§9.5: reads.jsonl says C_test was read but the kept file is gone - no second read."""
        self.queue({'what': 'test.started', 'selection_sha256': self.sha})
        self.reads = [{'what': 'noise_explore'}, {'what': 'c_test', 'names': ['test-Hr-7']}]
        with self.assertRaises(SystemExit):
            self.read(None, c_test=lambda *a: self.fail('second C_test read'))
        self.assertFalse((self.runs / 'test.json').exists())

    def test_foreign_fits(self):
        specs = self.queue({'what': 'test.started', 'selection_sha256': self.sha})
        bad = [dict(s) for s in specs]
        bad[0]['tables'] = ['g1_1']
        self.put('queue-test.json', bad)
        no = lambda *a: self.fail('read with a foreign queue')
        with self.assertRaises(SystemExit):
            self.read(None, c_test=no)
        self.put('queue-test.json', specs + specs[:1])
        with self.assertRaises(SystemExit):
            self.read(None, c_test=no)
        self.put('queue-test.json', [s for s in specs if s['arm'] != 'SEL'])
        with self.assertRaises(SystemExit):
            self.read(None, c_test=no)


if __name__ == '__main__':
    unittest.main()
