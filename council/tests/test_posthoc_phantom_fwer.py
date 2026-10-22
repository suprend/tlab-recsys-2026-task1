"""council.posthoc_phantom_fwer on synthetic plan JSON under a temp dir: loading the recorded nomination, the
se_empty consistency check, leave-one-empty-out t (an outlier empty masked by its own SE_empty is unmasked), the WY
approximation, reference rates, the Poisson-binomial quantile, the outcome classes, and a guard that the post-hoc
modules read JSON only."""
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy import stats

from council import design as D
from council import posthoc_phantom_fwer as P

EMPTY6 = [f'E{i}' for i in range(1, 7)]


def sd(v):
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def write_run(root: Path, name: str, betas: dict, se_boot: dict, empty, families, wy_harm=None, D=None,
              nominated=None, se_empty=None):
    """plan-result.json / prereg-2.json / selection.json of a synthetic plan; se = sqrt(se_boot^2 + se_empty^2)."""
    d = root / name
    d.mkdir(parents=True)
    se_e = sd([betas[c] for c in empty]) if se_empty is None else se_empty
    cols = {}
    for c, b in betas.items():
        se = math.sqrt(se_boot.get(c, 0.0) ** 2 + se_e ** 2)
        cols[c] = {'what': 'empty' if c in empty else c, 'beta': b, 'se': se, 't': b / se}
    plan = {'beta': cols, 'se_empty': se_e, 'wy_harm': wy_harm if wy_harm is not None else {f: 1.0 for f in families}}
    if D is not None:
        plan['D'] = D
    (d / 'plan-result.json').write_text(json.dumps(plan), encoding='utf-8')
    (d / 'prereg-2.json').write_text(json.dumps({'empty': list(empty),
                                                 'families': {f: f'G-{f}' for f in families}}), encoding='utf-8')
    sel = {'SEL': 'ALL_P', 'D': []}
    if nominated is not None:
        sel['nominated'] = nominated
    (d / 'selection.json').write_text(json.dumps(sel), encoding='utf-8')
    return d


class PhantomTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='tlab-posthoc-test-'))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_dir(self, name='a', empty_betas=(1e-4, -1e-4, 1e-4, -1e-4, 0.0, -3e-4), sb=1e-5, **kw):
        betas = {'F1': -3e-4, 'F2': 2e-4, 'PL': 0.0}
        betas.update(dict(zip(EMPTY6, empty_betas)))
        return write_run(self.root, name, betas, {c: sb for c in betas}, EMPTY6, ['F1', 'F2'],
                         wy_harm=kw.pop('wy_harm', {'F1': 0.5, 'F2': 1.0, 'PL': 1.0}), **kw)

    def test_recorded_nomination_source(self):
        a = P.load_run(self.run_dir('a', D=['F1'], nominated=['F2']))
        self.assertEqual((a['D_saved'], a['D_from']), (['F1'], 'plan-result.D'))
        b = P.load_run(self.run_dir('b', nominated=['F2']))
        self.assertEqual((b['D_saved'], b['D_from']), (['F2'], 'selection.nominated'))
        c = P.load_run(self.run_dir('c'))
        self.assertIsNone(c['D_saved'])
        self.assertEqual(c['families'], ['F1', 'F2'])

    def test_se_empty_check(self):
        run = P.load_run(self.run_dir('ok'))
        self.assertLess(P.check_se_empty(run), 1e-12)
        bad = P.load_run(self.run_dir('bad', se_empty=1e-3))
        with self.assertRaises(SystemExit):
            P.check_se_empty(bad)

    def test_se_boot_recovered_from_design_estimate(self):
        """plan-result JSON written from a real design.estimate: se_boot recovered from se and se_empty."""
        rng = np.random.default_rng(1)
        beta_true = np.zeros(len(D.COLUMNS))
        beta_true[D.COLUMNS.index('F1')] = -0.01
        y = D.matrix() @ beta_true + 0.05 * rng.standard_normal((300, 48)) + rng.uniform(0, 0.5, (300, 1))
        est = D.estimate(y, groups=None, n_boot=200)
        d = self.root / 'est'
        d.mkdir()
        plan = {'beta': {c: {'what': c, 'beta': float(est.beta[c]), 'se': float(est.se[c]), 't': float(est.t[c])}
                         for c in D.COLUMNS},
                'se_empty': float(est.se_empty), 'wy_harm': {c: 1.0 for c in D.FAMILIES + [D.PLACEBO]}}
        (d / 'plan-result.json').write_text(json.dumps(plan), encoding='utf-8')
        (d / 'prereg-2.json').write_text(json.dumps({'empty': list(D.EMPTIES),
                                                     'families': {f: f for f in D.FAMILIES}}), encoding='utf-8')
        run = P.load_run(d)
        self.assertLess(P.check_se_empty(run), 1e-9)
        for c in D.COLUMNS:
            self.assertAlmostEqual(P.se_boot(run, c), float(est.se_boot[c]), delta=1e-12)

    def test_scaled_rates(self):
        run = P.load_run(self.run_dir(sb=3e-5))
        sc = P.scaled_rates(run)
        for c in EMPTY6:
            share = run['se_empty'] ** 2 / run['se'][c] ** 2
            self.assertAlmostEqual(sc['share'][c], share, places=12)
        z = -2 / math.sqrt(sc['share']['E1'])
        self.assertAlmostEqual(sc['normal']['harm'][0], stats.norm.cdf(z), places=12)
        self.assertAlmostEqual(sc['t']['abs'][0], 2 * stats.t.cdf(z, 4), places=12)
        # share < 1 makes both scaled rates smaller than the unscaled references
        ref = P.reference_rates(6)
        self.assertTrue(all(r < ref['normal']['harm'] for r in sc['normal']['harm']))
        self.assertTrue(all(r < ref['t']['harm'] for r in sc['t']['harm']))

    def test_leave_one_out_by_hand(self):
        e = (1e-4, -1e-4, 1e-4, -1e-4, 0.0, -3e-4)
        run = P.load_run(self.run_dir(empty_betas=e, sb=1e-5))
        rows = {r['column']: r for r in P.leave_one_out(run)}
        se_loo = sd(list(e[:5]))
        self.assertAlmostEqual(rows['E6']['se_empty_loo'], se_loo, delta=1e-15)
        self.assertAlmostEqual(rows['E6']['t_loo'], e[5] / math.sqrt(1e-10 + se_loo ** 2), places=9)
        # the outlier is masked by its own SE_empty in the saved t and unmasked when left out
        self.assertGreater(rows['E6']['t_saved'], -2)
        self.assertFalse(rows['E6']['saved_harm_t'])
        self.assertTrue(rows['E6']['harm_t'] and rows['E6']['abs_t'] and rows['E6']['nominated_approx'])
        self.assertLess(rows['E6']['wy_harm_approx'], 0.01)
        # the other empties: a positive one is never a harm candidate
        self.assertFalse(rows['E1']['harm_t'])

    def test_null_empties_pass_nothing(self):
        run = P.load_run(self.run_dir(empty_betas=(1e-4, -1e-4, 0.5e-4, -0.5e-4, 0.2e-4, -0.2e-4)))
        rows = P.leave_one_out(run)
        self.assertFalse(any(r['harm_t'] or r['abs_t'] or r['nominated_approx'] for r in rows))

    def test_wy_approx(self):
        self.assertAlmostEqual(P.wy_approx(-2.0, 1), stats.norm.cdf(-2.0), places=12)
        z = np.random.default_rng(7).standard_normal((200000, 14))
        self.assertAlmostEqual(P.wy_approx(-2.5, 14), float((z.min(axis=1) <= -2.5).mean()), delta=0.003)
        self.assertLess(P.wy_approx(-3.0, 14), P.wy_approx(-2.0, 14))
        self.assertLess(P.wy_approx(-2.0, 2), P.wy_approx(-2.0, 14))

    def test_reference_rates(self):
        r = P.reference_rates(6)
        self.assertEqual(r['df_t'], 4)
        self.assertAlmostEqual(r['normal']['harm'], 0.0227501, places=6)
        self.assertAlmostEqual(r['normal']['abs'], 2 * 0.0227501, places=6)
        self.assertAlmostEqual(r['t']['harm'], stats.t.cdf(-2, 4), places=12)
        self.assertGreater(r['t']['harm'], r['normal']['harm'])

    def test_poisson_binomial(self):
        pmf = P.poisson_binomial([0.1] * 20)
        self.assertAlmostEqual(sum(pmf), 1.0, places=12)
        for j in range(21):
            self.assertAlmostEqual(pmf[j], stats.binom.pmf(j, 20, 0.1), places=12)
        self.assertEqual(P.quantile(pmf), int(stats.binom.ppf(0.95, 20, 0.1)))
        self.assertAlmostEqual(P.upper_tail(pmf, 0), 1.0, places=12)
        self.assertAlmostEqual(P.upper_tail(pmf, 3), stats.binom.sf(2, 20, 0.1), places=12)

    def test_classify(self):
        self.assertEqual(P.classify(1, 2, 4), 'не противоречит номиналу')
        self.assertEqual(P.classify(3, 2, 4), 'в пределах t-хвоста')
        self.assertEqual(P.classify(5, 2, 4), 'превышение номинала')

    def test_analyze_pools_datasets(self):
        a = self.run_dir('a')  # E6 outlier: one false nomination
        b = self.run_dir('b', empty_betas=(1e-4, -1e-4, 0.5e-4, -0.5e-4, 0.2e-4, -0.2e-4))
        res = P.analyze({'a': a, 'b': b})
        self.assertEqual(res['pooled']['n_candidates'], 12)
        self.assertEqual(res['pooled']['counts']['nominated_approx'], 1)
        self.assertEqual(res['pooled']['datasets_with_false_nomination_approx'], ['a'])
        self.assertEqual(res['datasets']['a']['k_wy'], 4)
        self.assertAlmostEqual(res['pooled']['harm']['normal']['expected'], 12 * stats.norm.cdf(-2), places=9)
        self.assertIn(res['pooled']['harm']['outcome'],
                      {'не противоречит номиналу', 'в пределах t-хвоста', 'превышение номинала'})

    def test_sber_layout_more_empties(self):
        empty = ['F3', 'F4'] + EMPTY6
        betas = {'F1': 0.0, 'F2': 0.0, 'PL': 0.0, 'F3': 1e-4, 'F4': -1e-4}
        betas.update(dict(zip(EMPTY6, (1e-4, -1e-4, 1e-4, -1e-4, 0.0, 0.0))))
        d = write_run(self.root, 's', betas, {}, empty, ['F1', 'F2'], wy_harm={'F1': 1, 'F2': 1, 'PL': 1})
        res = P.analyze({'s': d})
        ds = res['datasets']['s']
        self.assertEqual(ds['m'], 8)
        self.assertEqual(ds['reference']['df_t'], 6)
        self.assertEqual([r['column'] for r in ds['columns']], empty)


class GuardTest(unittest.TestCase):
    def test_posthoc_modules_read_json_only(self):
        for name in ('posthoc_phantom_fwer.py', 'posthoc_beyond_empties.py'):
            src = (Path(P.__file__).parent / name).read_text(encoding='utf-8')
            for bad in ('parquet', 'duckdb', 'sealed', 'read_csv', 'broker', "'data/", '"data/', 'open('):
                self.assertNotIn(bad, src, f'{name} mentions {bad}')


if __name__ == '__main__':
    unittest.main()
