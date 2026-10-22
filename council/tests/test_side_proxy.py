"""council.side.proxy (H6) on synthetic frames; no REES46 data is read.

Checks: the head/tail split of T_fit before S0; the column -> table map of prereg-2; user folds; the OOF base and
the proxies on a synthetic pool where one table carries signal the base lacks (its Δ is the largest and positive,
a noise table's Δ is near zero); the gate of summarize; run() with the loaders replaced writes only under temporary
roots, holds the heavy lock and checks before every fit; --dry opens nothing under artifacts/ or data/ (audit hook).

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_side_proxy -v
"""
import json
import os
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from council import side as S
from council.side import proxy as P
from council.tests.test_side_tinkoff_anchor import run_dry, tmp_root

ROOT = Path(__file__).resolve().parents[2]
CFG = dict(iterations=30, depth=4, lr=0.2, l2=3, threads=2)
SMALL = dict(iterations=30, depth=3, learning_rate=0.2, l2_leaf_reg=3, random_seed=2026, boost_from_average=False)


def frame(n_queries, seed, anchor='2020-01-20', per=20):
    """Queries of `per` candidates; label from s_a (base) and f_x_sig (table g1); f_x_noise is noise (table g2)."""
    rng = np.random.default_rng(seed)
    n = n_queries * per
    users = np.repeat(rng.choice(10 ** 7, n_queries, replace=False), per)
    s_a, s_b, sig, noise = (rng.normal(size=n) for _ in range(4))
    logit = -2.5 + 1.0 * s_a + 2.0 * sig
    label = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    df = pd.DataFrame({'anchor': anchor, 'user_id': users, 'product_id': np.tile(np.arange(per), n_queries),
                       's_a': s_a, 's_b': s_b, 'f_x_sig': sig, 'f_x_noise': noise, 'label': label})
    df['qid'] = df['anchor'] + ':' + df['user_id'].astype(str)
    df['n_targets'] = df.groupby('qid')['label'].transform('sum')
    return df[df['n_targets'] > 0].reset_index(drop=True)


class Spec(unittest.TestCase):
    def test_split(self):
        from council import roles
        head, tail = P.split_days(roles.days('T_fit'), before=roles.days('S0')[0])
        self.assertEqual([str(d) for d in tail], ['2020-01-29', '2020-01-30', '2020-01-31', '2020-02-01',
                                                  '2020-02-02'])
        self.assertEqual(str(head[0]), '2020-01-15')
        self.assertEqual(len(head), 14)
        with self.assertRaises(S.Refused):
            P.split_days(roles.days('T_fit') + [date(2020, 2, 3)], before=date(2020, 2, 3))

    def test_check_days(self):
        s = {'head': ['2020-01-15'], 'tail': ['2020-02-03'], 'days_dir': '/tmp/tlab-x'}
        with self.assertRaises(S.Refused):
            P.check_days(s)
        s = {'head': ['2020-01-30'], 'tail': ['2020-01-29'], 'days_dir': '/tmp/tlab-x'}
        with self.assertRaises(S.Refused):
            P.check_days(s)
        P.check_days({'head': ['2020-01-15'], 'tail': ['2020-01-29'], 'days_dir': '/tmp/tlab-x'})

    def test_tables(self):
        pre = {'families': {f'F{k}': f'G{k}-1' for k in range(1, 13)},
               'twins': {f'T{k}': {'family': f'F{k}', 'card': f'G{k}-1'} for k in range(1, 5)}}
        t = P.tables_of(pre)
        self.assertEqual(list(t), P.COLUMNS)
        self.assertEqual(t['F1'], 'council_g1_1')
        self.assertEqual(t['T1'], 'council_g1_1_tw')
        del pre['twins']['T4']
        with self.assertRaises(S.Refused):
            P.tables_of(pre)

    def test_folds(self):
        u = np.arange(10000)
        f = P.folds(u)
        self.assertEqual(set(f), {0, 1, 2, 3})
        self.assertTrue(all(abs((f == j).mean() - 0.25) < 0.03 for j in range(4)))
        self.assertTrue((P.folds(u) == f).all())


class Core(unittest.TestCase):
    def test_signal_table_ranks_first(self):
        head = frame(400, 1)
        tails = [('2020-01-29', frame(300, 2, '2020-01-29')), ('2020-01-30', frame(300, 3, '2020-01-30'))]
        checks = []
        pq, sec = P.run_core(head, ['s_a', 's_b'], {'g1': ['f_x_sig'], 'g2': ['f_x_noise']}, iter(tails), CFG,
                             check_fn=lambda: checks.append(1), proxy_params=SMALL)
        self.assertEqual(len(checks), 4 + 2 + 2)
        self.assertEqual(set(pq.columns), {'qid', 'base', 'g1', 'g2', 'day'})
        self.assertEqual(pq['qid'].nunique(), len(pq))
        d1 = (pq['g1'] - pq['base']).mean()
        d2 = (pq['g2'] - pq['base']).mean()
        self.assertGreater(d1, 0.05)
        self.assertLess(abs(d2), 0.02)
        self.assertEqual(len(sec['base_folds']), 4)

    def test_oof_never_sees_own_fold(self):
        head = frame(200, 4)
        margin, models, _ = P.oof(head, ['s_a', 's_b'], CFG, k=4)
        f = P.folds(head['user_id'].to_numpy())
        for j, m in enumerate(models):
            np.testing.assert_allclose(margin[f == j],
                                       m.predict(head.loc[f == j, ['s_a', 's_b']], prediction_type='RawFormulaVal'))

    def test_summarize_gate(self):
        cols = [f'g{k}' for k in range(6)]
        rng = np.random.default_rng(0)
        base = rng.random(200)
        pq = pd.DataFrame({'base': base} | {g: base + 0.01 * k + rng.normal(0, 0.001, 200)
                                            for k, g in enumerate(cols)})
        beta = {g: {'beta': 0.001 * k, 't': k / 2} for k, g in enumerate(cols)}
        s = P.summarize(pq, beta, cols, draws=200)
        self.assertTrue(s['gate']['passed'])
        self.assertAlmostEqual(s['spearman_beta']['rho'], 1.0)
        rev = {g: {'beta': -0.001 * k, 't': -k / 2} for k, g in enumerate(cols)}
        self.assertFalse(P.summarize(pq, rev, cols, draws=200)['gate']['passed'])


class Run(unittest.TestCase):
    def test_run_writes_only_side(self):
        root = tmp_root()
        out = S.Out(P.NAME, root / 'art', root / 'runs')
        prot = root / 'prot'
        prot.mkdir()
        s = {'head': ['2020-01-15'], 'tail': ['2020-01-29'], 'days_dir': '/tmp/tlab-x', 'base_tables': ['h'],
             'columns': ['g1', 'g2'], 'tables': {'g1': 't1', 'g2': 't2'}}
        head = frame(300, 5)
        held = []

        def load_head(spec):
            from council.xfer import queue as Q
            held.append(Q.lock_holder(root / 'heavy.lock'))
            return head, ['s_a', 's_b'], {'g1': ['f_x_sig'], 'g2': ['f_x_noise']}, CFG
        beta = {'g1': {'beta': 0.01, 't': 2.0}, 'g2': {'beta': 0.0, 't': 0.0}}
        with mock.patch.object(P, 'load_head', load_head), \
                mock.patch.object(P, 'tail_frames', lambda spec, tables: iter([('2020-01-29', frame(200, 6))])), \
                mock.patch.object(P, 'read_beta', lambda: beta), mock.patch.object(P, 'COLUMNS', ['g1', 'g2']):
            res = P.run(out, s, wait=False, heavy_kw={'lock_path': root / 'heavy.lock', 'procs_fn': lambda: []},
                        protected=[prot], check_fn=lambda: None, proxy_params=SMALL)
        self.assertEqual(held[0]['what'], 'side proxy')
        self.assertEqual(res['status'], 'ok')
        written = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
        self.assertIn('runs/proxy.json', written)
        self.assertIn('art/proxy/per_query.parquet', written)
        self.assertTrue(all(w.startswith(('runs/', 'art/proxy/', 'heavy.lock')) for w in written), written)
        self.assertGreater(res['delta']['g1']['mean'], res['delta']['g2']['mean'])



class Dry(unittest.TestCase):
    def test_dry(self):
        r = run_dry('proxy')
        if not P.PREREG2.exists():
            self.skipTest('prereg-2.json is not in this checkout')
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(d['dry'])
        self.assertEqual(d['fits'], {'base_oof': 4, 'proxies': 16})
        self.assertEqual(len(d['spec']['tables']), 16)


if __name__ == '__main__':
    unittest.main()
