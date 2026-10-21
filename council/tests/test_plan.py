"""council.plan on a synthetic curation and synthetic per-query values: the queue follows the matrix, the
analysis recovers a planted family effect and picks the twin arm."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from council import design as D, plan, roles


def curation(n=5, t=3):
    fams = [f'G{1 + k % 4}-{1 + k // 4}' for k in range(n)]
    return {'families': fams, 'twins': fams[:t], 'columns': {f: [f'f_x_c{f[1]}_{k}'] for k, f in enumerate(fams)},
            'placebo': [f'f_x_c{f[1]}_{k}' for k, f in enumerate(fams[:4])], 'placebo_families': fams[:4],
            'parity': {'ok': True, 'reference_drop': []}, 'reference_order': ['council_rb1_a', 'council_rb2_b'],
            'reference_removed': []}


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name)
        (self.runs / 'curation.json').write_text(json.dumps(curation()))
        (self.runs / 'prereg-0.json').write_text(json.dumps({'rehearsal': {'sd_t_interval': [0.3, 1.2]}}))
        self.p = mock.patch.object(plan, 'RUNS', self.runs)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_queue_follows_the_matrix(self):
        plan.build()
        q = json.loads((self.runs / 'queue-plan.json').read_text())
        pre = json.loads((self.runs / 'prereg-2.json').read_text())
        x = D.matrix()
        self.assertEqual(len(q), 48)
        self.assertEqual(pre['empty'], [f'F{k}' for k in range(6, 13)] + ['T4'] + D.EMPTIES)
        for r, spec in enumerate(q):
            self.assertEqual(spec['extra'][:len(roles.HPLUS)], roles.HPLUS)
            self.assertEqual('council_g1_1' in spec['extra'], x[r, 0] > 0)          # F1 = G1-1
            self.assertEqual('council_g1_1_tw' in spec['extra'], x[r, 12] > 0)      # T1 = twin of G1-1
            self.assertEqual(spec['placebo'] is not None, x[r, 16] > 0)
            self.assertFalse(any('g2_2' in t for t in spec['extra']))               # 5 families only
            self.assertEqual((spec['seed'], spec['neg_seed']), roles.plan_seed(r + 1))
        self.assertEqual(pre['arms']['Hrp'][len(roles.HPLUS):], ['council_rb1_a', 'council_rb2_b'])

    def test_analysis_recovers_a_planted_family(self):
        plan.build()
        q = json.loads((self.runs / 'queue-plan.json').read_text())
        rng = np.random.default_rng(0)
        n = 4000
        qid = [f'2020-02-0{3 + i % 5}:{i // 2}' for i in range(n)]
        x = D.matrix()
        y = 0.2 + rng.normal(0, 0.05, (n, 48)) + 0.004 * x[:, 1][None, :] + 0.003 * x[:, 12][None, :]
        frame = pd.DataFrame(y, index=qid, columns=[s['name'] for s in q])
        with mock.patch.object(plan.broker, 'y_select', return_value=frame):
            plan.analyze()
        res = json.loads((self.runs / 'plan-result.json').read_text())
        sel = json.loads((self.runs / 'selection.json').read_text())
        self.assertGreater(res['beta']['F2']['t'], 2)
        self.assertAlmostEqual(res['beta']['F2']['beta'], 0.004, delta=0.002)
        self.assertEqual(sel['SEL'], 'ALL_P')
        self.assertEqual(sel['twin_arm']['family'], 'F2')                    # largest t(beta_g - beta_twin)
        self.assertEqual(sel['twin_arm']['replace'], ['council_g2_1', 'council_g2_1_tw'])

    def test_analysis_refuses_an_edited_queue(self):
        plan.build()
        q = json.loads((self.runs / 'queue-plan.json').read_text())
        q[0], q[1] = q[1], q[0]
        (self.runs / 'queue-plan.json').write_text(json.dumps(q))
        with mock.patch.object(plan.broker, 'y_select', side_effect=AssertionError('read')), \
                self.assertRaises(SystemExit):
            plan.analyze()

    def test_the_one_c_val_read_is_kept(self):
        plan.build()
        (self.runs / 'selection.json').write_text(json.dumps(
            {'SEL': 'ALL_P', 'twin_arm': {'family': None, 'card': None, 'replace': None}}))
        plan.cval()
        names = ['path_Hr_full_val_s0'] + [s['name'] for s in json.loads((self.runs / 'queue-cval.json').read_text())]
        y = pd.DataFrame(np.full((40, len(names)), 0.3), index=[f'2020-02-08:{i}' for i in range(40)], columns=names)
        out = self.runs / 'out'
        with mock.patch.object(plan.roles, 'OUT', out), mock.patch.object(plan.D, 'two_level', side_effect=RuntimeError):
            with mock.patch.object(plan.broker, 'c_val', return_value=y), self.assertRaises(RuntimeError):
                plan.read_val()
            self.assertTrue((out / 'cval-read.parquet').exists())
            with mock.patch.object(plan.broker, 'c_val', side_effect=AssertionError('second read')), \
                    self.assertRaises(RuntimeError):
                plan.read_val()                                     # reuses the kept read, never reads again

    def test_cval_and_ctest_queues(self):
        plan.build()
        (self.runs / 'selection.json').write_text(json.dumps(
            {'SEL': 'ALL_P', 'twin_arm': {'family': 'F2', 'card': 'G2-1', 'replace': ['council_g2_1', 'council_g2_1_tw']}}))
        plan.cval()
        q = {s['name']: s for s in json.loads((self.runs / 'queue-cval.json').read_text())}
        self.assertNotIn('cval_Hr_s0', q)
        self.assertIn('council_g2_1_tw', q['cval_TWIN_s1']['extra'])
        self.assertNotIn('council_g2_1', q['cval_TWIN_s1']['extra'])
        self.assertEqual(q['cval_Rb2_s0']['extra'][len(roles.HPLUS):], ['council_rb2_b'])
        self.assertTrue(all(s['recipe'] == 'full_val' and s['fit'] == 'train' for s in q.values()))
        plan.ctest()
        t = [s['name'] for s in json.loads((self.runs / 'queue-test.json').read_text())]
        self.assertEqual(len(t), 10)


if __name__ == '__main__':
    unittest.main()
