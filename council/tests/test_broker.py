"""council.broker (council/runs/rees46-2020/contract.md §3.2) on synthetic per-query files in a temporary directory:
which fits each read takes, the one-time reads, the gate of a committed selection.json (a real temporary git
repository), the owner's approval and the marker of the test, equal queries, the log and the path check.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_broker
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from council import broker, roles
from task1 import exp

GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']


def spec(name, fit='T_fit', ev='S0', keep_half='B', recipe='plan', seed=1001, neg_seed=1, extra=('tx',), placebo=None):
    return {'name': name, 'fit': fit, 'eval': ev, 'keep_half': keep_half, 'recipe': recipe, 'extra': list(extra),
            'seed': seed, 'neg_seed': neg_seed, 'placebo': placebo}


def queries(span, half=None, n=8):
    rows = [(f'{d}:{u}', str(d), h) for d in roles.days(span) for u in range(1, n + 1)
            for h in exp.half([u]) if half is None or h == half]
    return pd.DataFrame(rows, columns=['qid', 'anchor', 'half'])


class BrokerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.repo = root / 'repo'
        self.runs = self.repo / 'council/runs/rees46-2020'
        self.runs.mkdir(parents=True)
        self.git('init', '-q')
        (self.repo / 'README').write_text('x')
        self.commit()
        self.fits, self.exp_out = root / 'fits', root / 'exp'
        self.fits.mkdir()
        self.exp_out.mkdir()
        for p in (mock.patch.object(roles, 'RUNS', self.runs), mock.patch.object(roles, 'FITS', self.fits),
                  mock.patch.object(exp, 'OUT', self.exp_out)):
            p.start()
            self.addCleanup(p.stop)
        self.rng = np.random.default_rng(0)

    def git(self, *args):
        subprocess.run(GIT + list(args), cwd=self.repo, check=True, capture_output=True)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'x', '--allow-empty')

    def fit(self, s, q):
        """A fit's per-query file with made-up metrics and its record."""
        df = q.assign(ndcg=self.rng.random(len(q)), recall=self.rng.random(len(q)),
                      purchase_ndcg=np.where(self.rng.random(len(q)) < 0.5, np.nan, self.rng.random(len(q))),
                      purchase_recall=np.nan)
        duckdb.sql(f"COPY (SELECT * FROM df) TO '{self.fits / s['name']}.parquet' (FORMAT PARQUET)")
        with (self.fits / 'runs.jsonl').open('a') as f:
            f.write(json.dumps({'name': s['name'], 'spec': s}) + '\n')
        return df.set_index('qid')

    def logged(self):
        path = self.runs / 'reads.jsonl'
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def select(self):
        (self.runs / 'selection.json').write_text('{"SEL": []}\n')
        self.commit()

    def test_y_select_takes_s0_select_fits_with_the_same_queries(self):
        q = queries('S0', 'B')
        a, b = self.fit(spec('p1'), q), self.fit(spec('p2', seed=1002, neg_seed=2), q)
        y = broker.y_select(['p1', 'p2'])
        self.assertEqual(list(y.columns), ['p1', 'p2'])
        pd.testing.assert_series_equal(y.p1, a.ndcg.sort_index(), check_names=False)
        pd.testing.assert_series_equal(y.p2, b.ndcg.sort_index(), check_names=False)
        self.assertEqual(broker.y_select(['p1'], metric='recall').p1.tolist(), a.recall.sort_index().tolist())
        self.assertEqual([(r['what'], r['names'], r['queries']) for r in self.logged()],
                         [('y_select', ['p1', 'p2'], len(q)), ('y_select', ['p1'], len(q))])
        self.assertFalse([k for r in self.logged() for k in r if 'ndcg' in k])

        self.fit(spec('explore', keep_half='A'), queries('S0', 'A'))
        self.fit(spec('val', fit='train', ev='val', keep_half=None, recipe='full_val'), queries('val'))
        self.fit(spec('short'), q.iloc[1:])
        for names, err in ((['p1', 'explore'], PermissionError), (['val'], PermissionError),
                           (['p1', 'missing'], PermissionError), (['p1', 'short'], ValueError), ([], ValueError),
                           (['p1', 'p1'], ValueError)):
            with self.subTest(names=names), self.assertRaises(err):
                broker.y_select(names)
        with self.assertRaises(ValueError):
            broker.y_select(['p1'], metric='label')
        self.assertEqual(len(self.logged()), 2)  # refused reads leave no trace and return nothing

    def test_a_file_whose_halves_lie_is_refused(self):
        q = queries('S0', 'B')
        self.fit(spec('mixed'), pd.concat([q, queries('S0', 'A')]))
        with self.assertRaisesRegex(ValueError, 'outside half B'):
            broker.y_select(['mixed'])

    def test_noise_explore_once_with_the_two_noise_fits(self):
        q = queries('S0', 'A')
        noise = dict(keep_half='A', extra=roles.HPLUS)
        self.fit(spec('n0', seed=2026, neg_seed=0, **noise), q)
        self.fit(spec('n1', seed=7, neg_seed=1, **noise), q)
        self.fit(spec('n2', seed=11, neg_seed=2, **noise), q)
        self.fit(spec('n3', seed=7, neg_seed=1, keep_half='A', extra=['tx']), q)
        for names in (['n0', 'n2'], ['n0', 'n3'], ['n0']):
            with self.subTest(names=names), self.assertRaises(PermissionError):
                broker.noise_explore(names)
        y = broker.noise_explore(['n1', 'n0'])
        self.assertEqual(list(y.columns), ['n1', 'n0'])
        with self.assertRaisesRegex(PermissionError, 'once'):
            broker.noise_explore(['n1', 'n0'])
        self.assertEqual([r['what'] for r in self.logged()], ['noise_explore'])

    def test_c_val_once_after_selection_is_committed(self):
        q = queries('val')
        for n in ('hr', 'sel'):
            self.fit(spec(n, fit='train', ev='val', keep_half=None, recipe='full_val'), q)
        self.fit(spec('proxy', fit='train', ev='val', keep_half=None, recipe='plan'), q)
        with self.assertRaisesRegex(PermissionError, 'selection.json'):
            broker.c_val(['hr', 'sel'])
        (self.runs / 'selection.json').write_text('{}\n')
        with self.assertRaisesRegex(PermissionError, 'selection.json'):  # not committed
            broker.c_val(['hr', 'sel'])
        self.commit()
        (self.runs / 'selection.json').write_text('{"changed": 1}\n')
        with self.assertRaisesRegex(PermissionError, 'selection.json'):  # changed after the commit
            broker.c_val(['hr', 'sel'])
        self.commit()
        with self.assertRaises(PermissionError):
            broker.c_val(['hr', 'proxy'])
        y = broker.c_val(['hr', 'sel'])
        self.assertEqual((list(y.columns), len(y)), (['hr', 'sel'], len(q)))
        with self.assertRaisesRegex(PermissionError, 'once'):
            broker.c_val(['hr', 'sel'])
        self.assertEqual([r['what'] for r in self.logged()], ['c_val'])

    def read_c_val(self):
        for n in ('v_hr', 'v_sel'):
            self.fit(spec(n, fit='train', ev='val', keep_half=None, recipe='full_val'), queries('val'))
        return broker.c_val(['v_hr', 'v_sel'])

    def approve(self, text):
        (self.runs / 'test-approved.md').write_text(text, encoding='utf-8')

    def test_c_test_needs_approval_c_val_unchanged_selection_and_marker(self):
        q = queries('test')
        for n in ('sel_s0', 'hrp_s0'):
            self.fit(spec(n, fit='refit', ev='test', keep_half=None, recipe='full_test'), q)
        names = ['sel_s0', 'hrp_s0']
        with self.assertRaisesRegex(PermissionError, 'test-approved'):
            broker.c_test(names)
        with self.assertRaisesRegex(PermissionError, 'test-approved'):
            broker.start_test()
        self.approve('approved: «Да, запускай тест» (владелец в чате 21.10)\n')
        with self.assertRaisesRegex(PermissionError, 'selection.json'):
            broker.start_test()
        self.select()
        with self.assertRaisesRegex(PermissionError, 'C_val has not been read'):
            broker.start_test()
        self.read_c_val()
        with self.assertRaisesRegex(PermissionError, 'test.started'):
            broker.c_test(names)
        broker.start_test()
        self.assertTrue((self.runs / 'test.started').exists())
        with self.assertRaisesRegex(PermissionError, 'exists already'):
            broker.start_test()
        y = broker.c_test(names)
        self.assertEqual(list(y.columns), ['anchor'] + names)
        self.assertFalse(y.anchor.isin(roles.TEST_EXCLUDED).any())
        self.assertEqual(len(y), (~q.anchor.isin(roles.TEST_EXCLUDED)).sum())
        full = broker.c_test(names, primary=False)
        self.assertEqual(len(full), len(q))
        self.assertEqual(sorted(full.anchor.unique()), [str(d) for d in roles.days('test')])
        self.assertEqual([(r['what'], r.get('primary')) for r in self.logged()],
                         [('c_val', None), ('test.started', None), ('c_test', True), ('c_test', False)])

    def test_the_approval_is_an_approved_line_with_the_owners_yes(self):
        self.select()
        self.read_c_val()
        for text in ('Владелец: «Да, запускай»\n',  # no approved: line
                     'approved: <дословная цитата>\n', 'approved: <дословная цитата с «да»>\n',
                     'approved: «давай потом»\n', 'approved:\n', '# approved: «да»\n',
                     'Шаблон: впишите строку approved: и цитату владельца с «да»\n'):
            self.approve(text)
            with self.subTest(text=text), self.assertRaisesRegex(PermissionError, 'approved:'):
                broker.start_test()
        self.approve('# Тест\n\napproved: «да»\n')
        broker.start_test()

    def test_selection_changed_after_c_val_stops_the_test(self):
        """After C_val SEL is edited and committed: the selection is committed, but not the one C_val read."""
        self.select()
        self.read_c_val()
        sha = [r for r in self.logged() if r['what'] == 'c_val'][0]['selection_sha256']
        self.assertEqual(sha, broker.selection_sha())
        (self.runs / 'selection.json').write_text('{"SEL": ["g1"]}\n')
        self.commit()
        self.approve('approved: «да»\n')
        with self.assertRaisesRegex(PermissionError, 'differs from the one C_val was read with'):
            broker.start_test()
        (self.runs / 'test.started').write_text('{}')  # even with a marker written by hand
        self.fit(spec('t', fit='refit', ev='test', keep_half=None, recipe='full_test'), queries('test'))
        with self.assertRaisesRegex(PermissionError, 'differs from the one C_val was read with'):
            broker.c_test(['t'])
        (self.runs / 'selection.json').write_text('{"SEL": []}\n')  # back to the bytes C_val read
        self.commit()
        self.assertEqual(list(broker.c_test(['t']).columns), ['anchor', 't'])

    def test_path_check(self):
        q = queries('val')
        s = spec('path', fit='train', ev='val', keep_half=None, recipe='full_val', seed=2026, neg_seed=0,
                 extra=roles.HPLUS)
        ours = self.fit(s, q)
        ref = ours.drop(columns='anchor').reset_index()[['qid', 'ndcg', 'recall', 'half', 'purchase_ndcg',
                                                         'purchase_recall']].sample(frac=1, random_state=1)
        duckdb.sql(f"COPY (SELECT * FROM ref) TO '{self.exp_out}/pl20_Hp_s0.parquet' (FORMAT PARQUET)")
        res = broker.path_check('path')
        self.assertTrue(res['ok'], res)
        self.assertEqual(res['max_abs_diff'], {m: 0.0 for m in broker.METRICS})
        off = ref.assign(ndcg=ref.ndcg + 1e-7)
        duckdb.sql(f"COPY (SELECT * FROM off) TO '{self.exp_out}/off.parquet' (FORMAT PARQUET)")
        self.assertFalse(broker.path_check('path', ref='off')['ok'])
        short = ref.iloc[1:]
        duckdb.sql(f"COPY (SELECT * FROM short) TO '{self.exp_out}/short.parquet' (FORMAT PARQUET)")
        self.assertEqual(broker.path_check('path', ref='short')['same_queries'], False)
        self.fit(spec('other_seed', fit='train', ev='val', keep_half=None, recipe='full_val', seed=7, neg_seed=1,
                      extra=roles.HPLUS), q)
        with self.assertRaises(PermissionError):
            broker.path_check('other_seed')


if __name__ == '__main__':
    unittest.main()
