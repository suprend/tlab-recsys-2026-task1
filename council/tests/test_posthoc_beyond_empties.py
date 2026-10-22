"""council.posthoc_beyond_empties on synthetic plan JSON under a temp dir: below-min / above-max / beyond-|.| sets,
beta vs t disagreement, the exchangeability null level (checked by Monte Carlo), the contract nomination from saved
t and wy_harm, the outcome classes, and the xfer layout where unused F-columns are empties, not families."""
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from council import posthoc_beyond_empties as B
from council import posthoc_phantom_fwer as P
from council.tests.test_posthoc_phantom_fwer import EMPTY6, write_run

EMPTY_BETAS = (1e-4, -1e-4, 2e-4, -2e-4, 0.5e-4, -0.5e-4)


class BeyondTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='tlab-posthoc-test-'))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_beyond_sets(self):
        v = {'F1': -3e-4, 'F2': 3e-4, 'F3': -1.5e-4, 'F4': 2.5e-4, 'F5': -2.5e-4}
        v.update(dict(zip(EMPTY6, EMPTY_BETAS)))
        r = B.beyond(v, ['F1', 'F2', 'F3', 'F4', 'F5'], EMPTY6)
        self.assertEqual(r['below_min'], ['F1', 'F5'])
        self.assertEqual(r['above_max'], ['F2', 'F4'])
        self.assertEqual(r['beyond_abs'], ['F1', 'F2', 'F4', 'F5'])
        self.assertEqual((r['empty_min'], r['empty_max'], r['empty_abs_max']), (-2e-4, 2e-4, 2e-4))

    def test_null_level(self):
        n = B.null_level(12, 6)
        self.assertAlmostEqual(n['per_family'], 1 / 7)
        self.assertAlmostEqual(n['any_of_k'], 12 / 18)
        self.assertAlmostEqual(n['expected_count'], 12 / 7)

    def test_null_level_monte_carlo(self):
        rng = np.random.default_rng(0)
        k, m, sims = 8, 10, 40000
        z = rng.standard_normal((sims, k + m))
        any_above = (z[:, :k].max(axis=1) > z[:, k:].max(axis=1)).mean()
        per = (z[:, 0] > z[:, k:].max(axis=1)).mean()
        n = B.null_level(k, m)
        self.assertAlmostEqual(any_above, n['any_of_k'], delta=0.01)
        self.assertAlmostEqual(per, n['per_family'], delta=0.006)

    def test_contract_nomination(self):
        run = {'families': ['F1', 'F2', 'F3'], 't': {'F1': -2.5, 'F2': -2.5, 'F3': -1.0, 'PL': -5.0},
               'wy_harm': {'F1': 0.05, 'F2': 0.2, 'F3': 0.01, 'PL': 0.001}}
        self.assertEqual(B.contract_nomination(run), ['F1'])

    def test_outcome(self):
        self.assertEqual(B.outcome(['F1'], ['F1']), 'совпадение')
        self.assertEqual(B.outcome([], []), 'совпадение')
        self.assertEqual(B.outcome(['F1', 'F2'], ['F1']), 'правило шире')
        self.assertEqual(B.outcome(['F2'], []), 'правило шире')
        self.assertEqual(B.outcome([], ['F1']), 'правило уже')
        self.assertEqual(B.outcome(['F2'], ['F1']), 'расходятся')

    def test_beta_vs_t_disagree(self):
        # F1 is below all empties by beta, but its own SE_boot is large, so not by t
        betas = {'F1': -3e-4, 'F2': 0.0, 'PL': 0.0}
        betas.update(dict(zip(EMPTY6, EMPTY_BETAS)))
        sb = {c: 1e-5 for c in betas}
        sb['F1'] = 1e-3
        d = write_run(self.root, 'x', betas, sb, EMPTY6, ['F1', 'F2'], wy_harm={'F1': 1, 'F2': 1, 'PL': 1})
        r = B.analyze_run(P.load_run(d))
        self.assertEqual(r['beta']['below_min'], ['F1'])
        self.assertEqual(r['t']['below_min'], [])
        self.assertEqual(r['beta_vs_t_disagree']['below_min'], ['F1'])

    def test_analyze_run_recorded_vs_rule(self):
        betas = {'F1': -5e-4, 'F2': 3e-4, 'PL': 0.0}
        betas.update(dict(zip(EMPTY6, EMPTY_BETAS)))
        sb = {c: 1e-5 for c in betas}
        wy = {'F1': 0.01, 'F2': 1.0, 'PL': 1.0}
        rec = B.analyze_run(P.load_run(write_run(self.root, 'rec', betas, sb, EMPTY6, ['F1', 'F2'], wy_harm=wy,
                                                 D=['F1'])))
        self.assertEqual(rec['nomination_recorded'], ['F1'])
        self.assertEqual(rec['outcome_below_min_vs_nomination'], 'совпадение')
        self.assertEqual(rec['outcome_reference'], 'recorded')
        self.assertEqual(rec['beta']['above_max'], ['F2'])
        norec = B.analyze_run(P.load_run(write_run(self.root, 'norec', betas, sb, EMPTY6, ['F1', 'F2'],
                                                   wy_harm=wy)))
        self.assertIsNone(norec['nomination_recorded'])
        self.assertEqual(norec['nomination_by_rule'], ['F1'])
        self.assertTrue(norec['outcome_reference'].startswith('rule'))
        # t with SE from the empties only: F1 = -5e-4 / SD(empties)
        se_e = P.sd(EMPTY_BETAS)
        self.assertAlmostEqual(rec['t_se_empty_only']['values']['F1'], -5e-4 / se_e, places=9)
        self.assertEqual(rec['t_se_empty_only']['df'], 5)

    def test_xfer_layout_unused_families_are_shadows(self):
        empty = ['F3', 'F4'] + EMPTY6
        betas = {'F1': 2.5e-4, 'F2': 0.0, 'PL': 0.0, 'F3': 9e-4, 'F4': -1e-4}
        betas.update(dict(zip(EMPTY6, EMPTY_BETAS)))
        d = write_run(self.root, 'sb', betas, {}, empty, ['F1', 'F2'], wy_harm={'F1': 1, 'F2': 1, 'PL': 1},
                      nominated=[])
        r = B.analyze_run(P.load_run(d))
        self.assertEqual(r['families'], ['F1', 'F2'])
        self.assertEqual(r['m'], 8)
        self.assertEqual(r['beta']['above_max'], [])  # F3 (empty) at 9e-4 is the shadow maximum
        self.assertEqual(r['nomination_recorded_from'], 'selection.nominated')
        self.assertAlmostEqual(r['null_level']['per_family'], 1 / 9)


if __name__ == '__main__':
    unittest.main()
