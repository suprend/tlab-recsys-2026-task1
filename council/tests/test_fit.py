"""council.fit and council.queue on a synthetic fixture (council/runs/rees46-2020/contract.md §3.1): the pool over an
explicit list of days against exp._read, the path check against task1.placebo.run, the spans read, keep_half, the
placebo, the refusals, the atomic write without overwrite and the queue. No real day table, label or fit is read.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_fit
"""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from council import fit, queue, roles
from task1 import exp, placebo
from task1 import model as M

EXTRA = ['tx_p', 'tx_u', 'tx_up']
TINY = dict(iterations=12, lr=0.1, cap=40, threads=2, depth=3)


def write_fixture(root):
    """Day tables of every anchor day of the rehearsal (15.01-29.02) and three extra tables keyed like the real ones:
    by product, by user (one user missing) and by pair."""
    rng = np.random.default_rng(5)
    (root / 'days').mkdir()
    for name in EXTRA:
        (root / 'extra' / name).mkdir(parents=True)
    for d in roles.days('refit') + roles.days('test'):
        parts = []
        for u in rng.choice(np.arange(1, 40), 6, replace=False):
            items = rng.choice(np.arange(100, 160), 12, replace=False)
            label = (np.arange(12) == rng.integers(0, 12)).astype(np.int32)
            bought = label * int(rng.random() < 0.5)
            parts.append(pd.DataFrame({'anchor': d, 'user_id': int(u), 'product_id': items, 'label': label,
                                       'label_purchase': bought, 'n_targets': 1 + int(rng.integers(0, 2)),
                                       'n_targets_purchase': int(bought.sum()), 's_pop_rank': np.arange(12),
                                       'u_n': rng.random(), 'i_price': items / 10.0,
                                       'i_cat_l1': [f'c{i % 3}' for i in items],
                                       'cf_cv_cond_tdecay20': label + rng.random(12)}))
        days = pd.concat(parts, ignore_index=True)
        duckdb.sql(f"COPY (SELECT * FROM days) TO '{root / 'days' / f'{d}.parquet'}' (FORMAT PARQUET)")
        tables = {'tx_p': pd.DataFrame({'product_id': np.arange(100, 160), 'f_x_p_pop': rng.random(60)}),
                  'tx_u': pd.DataFrame({'user_id': days.user_id.unique()[1:], 'f_x_u_act': rng.random(5)}),
                  'tx_up': days[['user_id', 'product_id']].assign(
                      f_x_up_sig=days.label + rng.random(len(days)),
                      f_x_up_rec=np.where(rng.random(len(days)) < 0.3, np.nan, rng.random(len(days))))}
        for name, x in tables.items():
            duckdb.sql(f"COPY (SELECT * FROM x) TO '{root / 'extra' / name / f'{d}.parquet'}' (FORMAT PARQUET)")


def spec(name, **over):
    return {'name': name, 'fit': 'T_fit', 'eval': 'S0', 'keep_half': 'B', 'recipe': 'plan', 'extra': ['tx_p', 'tx_u'],
            'seed': 1007, 'neg_seed': 7, 'placebo': None} | over


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        write_fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        work = Path(tempfile.mkdtemp(dir=self.root))
        self.fits, self.runs, self.exp_out = work / 'fits', work / 'runs', work / 'exp'
        self.runs.mkdir()
        recipes = {k: roles.BASE | TINY for k in roles.RECIPES}
        for p in (mock.patch.object(roles, 'DAYS6', self.root / 'days'), mock.patch.object(roles, 'FITS', self.fits),
                  mock.patch.object(roles, 'RUNS', self.runs), mock.patch.object(M, 'EXTRA', self.root / 'extra'),
                  mock.patch.object(exp, 'OUT', self.exp_out), mock.patch.dict(roles.RECIPES, recipes)):
            p.start()
            self.addCleanup(p.stop)
        exp._cache.clear()
        self.addCleanup(exp._cache.clear)

    def quiet(self, fn, *args, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            out = fn(*args, **kw)
        return out, printed.getvalue()

    def metrics(self, name):
        return duckdb.sql(f"SELECT * FROM '{self.fits / name}.parquet'").df()


class PoolTest(Fixture):
    def test_the_pool_of_explicit_days_is_exp_read(self):
        days = str(self.root / 'days')
        for cap in (None, 30):
            exp._cache.clear()
            pd.testing.assert_frame_equal(fit.pool(roles.days('train'), days, cap), exp._read('train', days, cap))
        t_fit = fit.pool(roles.days('T_fit'), days, None)
        self.assertEqual(sorted(t_fit.anchor.astype(str).str[:10].unique()), [str(d) for d in roles.days('T_fit')])


class PathCheckTest(Fixture):
    def test_h_plus_r_train_to_val_is_the_placebo_run(self):
        """§3.1 on the fixture: fit.path_spec() and task1.placebo.run with the same config agree per query to 1e-9,
        and broker.path_check says so."""
        from council import broker
        with mock.patch.object(roles, 'HPLUS', EXTRA), mock.patch.object(roles, 'HPLUS_FEATURES', 9):
            s = fit.path_spec()
            rec, printed = self.quiet(fit.run, s)
            cfg = {k: v for k, v in fit.config(fit.validate(s)).items()}
            exp._cache.clear()
            self.quiet(placebo.run, 'pl20_Hp_s0', **cfg)
            ours = self.metrics(s['name']).drop(columns='anchor').set_index('qid').sort_index()
            ref = duckdb.sql(f"SELECT * FROM '{self.exp_out}/pl20_Hp_s0.parquet'").df().set_index('qid').sort_index()
            pd.testing.assert_frame_equal(ours, ref[ours.columns], check_exact=False, atol=1e-9, rtol=0)
            self.assertEqual(rec['features'], 9)
            check = broker.path_check(s['name'])
        self.assertTrue(check['ok'], check)
        self.assertEqual(set(check['max_abs_diff']), set(broker.METRICS))
        self.assertNotIn('ndcg', printed)
        with self.assertRaisesRegex(ValueError, 'H\\+r has'), mock.patch.object(roles, 'HPLUS', EXTRA):
            fit.run(s | {'name': 'wrong_width'})


class RunTest(Fixture):
    def test_s0_reads_t_fit_for_the_pool_and_s0_for_the_scores_and_keeps_one_half(self):
        pooled, scored = [], []
        real_pool, real_day = fit.pool, exp.read_day

        def pool(days, days_dir, cap=None):
            pooled.append(list(days))
            return real_pool(days, days_dir, cap)

        def read_day(d, days_dir):
            scored.append(d)
            return real_day(d, days_dir)

        with mock.patch.object(fit, 'pool', pool), mock.patch.object(exp, 'read_day', read_day):
            rec, printed = self.quiet(fit.run, spec('plan_r07'), 'abc123')
        self.assertEqual(pooled, [roles.days('T_fit')])
        self.assertEqual(scored, roles.days('S0'))
        res = self.metrics('plan_r07')
        self.assertEqual(list(res.columns), fit.COLUMNS)
        self.assertEqual(set(res.half), {'B'})
        self.assertTrue(set(res.anchor) <= {str(d) for d in roles.days('S0')})
        self.assertTrue(res.qid.is_unique and (res.qid.str[:10] == res.anchor).all())
        self.assertEqual(rec['fit_queries'], TINY['cap'])
        self.assertEqual(rec['spec'], fit.validate(spec('plan_r07')))
        self.assertEqual((rec['commit'], rec['eval_queries'], rec['placebo_columns']), ('abc123', len(res), 0))
        self.assertEqual(rec['code'], fit.code_stamp())
        self.assertTrue({'council/fit.py', 'council/roles.py', 'task1/extra.py', 'task1/period.py'} <= set(rec['code']))
        self.assertEqual(set(rec['seconds']), {'prepare', 'fit', 'predict', 'write'})
        self.assertFalse([k for k in json.dumps(rec).split('"') if 'ndcg' in k or 'recall' in k])
        self.assertNotIn('ndcg', printed)
        self.assertEqual([r['name'] for r in map(json.loads, (self.fits / 'runs.jsonl').read_text().splitlines())],
                         ['plan_r07'])
        self.assertFalse([p for p in self.fits.iterdir() if p.name.startswith('.')])
        # the other half of the same fit gives the complementary queries
        self.quiet(fit.run, spec('plan_r07_a', keep_half='A'))
        a = self.metrics('plan_r07_a')
        self.assertEqual(set(a.half), {'A'})
        self.assertFalse(set(a.qid) & set(res.qid))

    def test_no_overwrite_and_a_changed_code_writes_nothing(self):
        self.quiet(fit.run, spec('once'))
        before = (self.fits / 'once.parquet').read_bytes()
        with mock.patch.object(fit, 'pool', side_effect=AssertionError('read')), \
                self.assertRaisesRegex(ValueError, 'never overwritten'):
            fit.run(spec('once', seed=5))
        self.assertEqual((self.fits / 'once.parquet').read_bytes(), before)
        stamp = fit.code_stamp()
        with mock.patch.object(fit, 'code_stamp', side_effect=[stamp, stamp | {'council/design.py': 'later'}]), \
                self.assertRaisesRegex(SystemExit, 'code changed during the fit'):
            self.quiet(fit.run, spec('changed'), stamp=stamp)
        self.assertFalse((self.fits / 'changed.parquet').exists())
        with self.assertRaisesRegex(SystemExit, 'stamp of the queue'):
            fit.run(spec('stale'), stamp=stamp | {'council/fit.py': 'other'})
        self.assertEqual(len((self.fits / 'runs.jsonl').read_text().splitlines()), 1)

    def test_the_data_fingerprint(self):
        s = fit.validate(spec('fp', placebo={'columns': ['f_x_up_sig'], 'tables': ['tx_up']}))
        d = fit.data_stamp(s)
        n = len(roles.days('T_fit') + roles.days('S0'))
        self.assertEqual(set(d['tables']), {'tx_p', 'tx_u', 'tx_up'})
        self.assertEqual([d['days6']['files']] + [v['files'] for v in d['tables'].values()], [n] * 4)
        self.assertTrue(all(v['bytes'] > 0 and v['mtime_ns'] > 0 for v in [d['days6'], *d['tables'].values()]))
        f = self.root / 'extra/tx_up' / f"{roles.days('S0')[0]}.parquet"
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        self.addCleanup(os.utime, f, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertNotEqual(fit.data_stamp(s), d)
        self.assertEqual(fit.data_stamp(s)['days6'], d['days6'])
        with mock.patch.object(fit, 'pool', side_effect=AssertionError('read')), \
                self.assertRaisesRegex(SystemExit, 'data differ from the fingerprint of the queue'):
            fit.run(s, data=d)
        rec, _ = self.quiet(fit.run, s)
        self.assertEqual(rec['data'], fit.data_stamp(s))
        self.assertEqual(fit.records()['fp']['data'], rec['data'])

    def test_data_changed_during_the_fit_writes_nothing(self):
        s = fit.validate(spec('moved'))
        d = fit.data_stamp(s)
        later = d | {'days6': d['days6'] | {'bytes': d['days6']['bytes'] + 1}}
        with mock.patch.object(fit, 'data_stamp', side_effect=[d, later]), \
                self.assertRaisesRegex(SystemExit, 'data changed during the fit; nothing was written'):
            self.quiet(fit.run, s, data=d)
        self.assertFalse((self.fits / 'moved.parquet').exists())
        self.assertFalse((self.fits / 'runs.jsonl').exists())

    def test_a_file_vanishing_from_the_code_stamp_is_a_clear_error(self):
        real = Path.read_bytes

        def read_bytes(path):
            if path.name == 'roles.py':
                raise FileNotFoundError(path)
            return real(path)

        with mock.patch.object(Path, 'read_bytes', read_bytes), \
                self.assertRaisesRegex(SystemExit, 'council/roles.py disappeared'):
            fit.code_stamp()

    def test_the_cli_runs_one_spec(self):
        f = self.root / 'cli.json'
        f.write_text(json.dumps(spec('cli')))
        with mock.patch.object(fit, 'git_head', return_value=('c0ffee', False)):
            _, printed = self.quiet(fit.main, ['--spec', str(f)])
        rec = fit.records()['cli']
        self.assertEqual((rec['commit'], rec['dirty']), ('c0ffee', False))
        self.assertEqual(json.loads(printed)['name'], 'cli')
        f.write_text(json.dumps(spec('cli2', eval='val')))
        with self.assertRaisesRegex(SystemExit, 'council.fit: cli2'):
            fit.main(['--spec', str(f)])


class PlaceboTest(Fixture):
    def capture(self, s):
        fits, scored = [], []
        real_fit, real_predict = exp.fit, M.predict

        def fit_(train, features, cfg):
            fits.append(train.copy())
            return real_fit(train, features, cfg)

        def predict(model, df, features):
            scored.append(df.copy())
            return real_predict(model, df, features)

        with mock.patch.object(exp, 'fit', fit_), mock.patch.object(M, 'predict', predict):
            rec, _ = self.quiet(fit.run, s)
        return rec, fits + scored

    def test_placebo_columns_are_the_campaign_permutation_and_foreign_tables_leave(self):
        pl = {'columns': ['f_x_up_sig', 'f_x_p_pop'], 'tables': ['tx_up', 'tx_p']}
        plain_rec, plain = self.capture(spec('plain', extra=EXTRA))
        rec, frames = self.capture(spec('plc', extra=['tx_p', 'tx_u'], placebo=pl))
        self.assertEqual(rec['placebo_columns'], 2)
        self.assertEqual(rec['features'], plain_rec['features'])  # 2 tx_up columns out, 2 placebo columns in
        self.assertEqual(len(frames), len(plain))
        new = ['f_x_plc_up_sig', 'f_x_plc_p_pop']
        for a, b in zip(plain, frames):
            want = a.assign(f_x_plc_up_sig=a.f_x_up_sig, f_x_plc_p_pop=a.f_x_p_pop)
            want = placebo.permute_within_days(want, new, roles.PLACEBO_SEED, 0).drop(columns=['f_x_up_sig', 'f_x_up_rec'])
            pd.testing.assert_frame_equal(b, want)
            self.assertIn('f_x_p_pop', b.columns)  # tx_p is in extra: its column stays
            self.assertGreater((b.f_x_plc_p_pop != b.f_x_p_pop).mean(), 0.5)
        # on the scored days the permutation does not depend on the fit's seeds
        _, other = self.capture(spec('plc_s2', extra=['tx_p', 'tx_u'], placebo=pl, seed=1002, neg_seed=2))
        for a, b in zip(frames[1:], other[1:]):
            pd.testing.assert_frame_equal(a[new], b[new])

    def test_placebo_columns_must_come_from_the_placebo_tables(self):
        bad = {'columns': ['f_x_u_act'], 'tables': ['tx_up']}
        with mock.patch.object(exp, 'fit', side_effect=AssertionError('fitted')), \
                self.assertRaisesRegex(ValueError, 'not columns of the placebo tables'):
            fit.run(spec('bad_plc', extra=['tx_p', 'tx_u'], placebo=bad))
        self.assertFalse(self.fits.exists() and list(self.fits.iterdir()))


class ValidateTest(Fixture):
    def test_bad_specs_stop_before_any_read(self):
        bad = [spec('x', extra_days=3), {k: v for k, v in spec('x').items() if k != 'seed'}, spec('x', eval='test'),
               spec('x', fit='refit', eval='test'), spec('x', keep_half=None), spec('x', keep_half='C'),
               spec('x', fit='train', eval='val', keep_half='B'), spec('x', fit='T_fit', eval='val', keep_half=None),
               spec('x', fit='train'), spec('x', recipe='huge'), spec('x', extra=['tx_p', 'sealed_tx']),
               spec('x', extra=['../tx_p']), spec('x', extra=['tx_missing']), spec('x', extra=['tx_p', 'tx_p']),
               spec('x', seed=True), spec('x', neg_seed=-1), spec('x', seed='1'), spec('x/y'), spec('.x'),
               spec('x', placebo={'columns': ['u_n'], 'tables': ['tx_up']}),
               spec('x', placebo={'columns': ['f_x_up_sig'], 'tables': []}),
               spec('x', placebo={'columns': ['f_x_plc_a'], 'tables': ['tx_up']}),
               spec('x', placebo={'columns': ['f_x_up_sig'], 'tables': ['tx_up'], 'seed': 1}), spec('x', eval=['S0'])]
        with mock.patch.object(fit, 'pool', side_effect=AssertionError('pool read')), \
                mock.patch.object(exp, 'read_day', side_effect=AssertionError('day read')):
            for s in bad:
                with self.subTest(s=s), self.assertRaises(ValueError):
                    fit.run(s)
            with mock.patch.object(roles, 'DAYS6', self.root / 'sealed' / 'days'), self.assertRaisesRegex(ValueError, 'sealed'):
                fit.run(spec('x'))
        self.assertFalse(self.fits.exists())

    def test_the_test_needs_the_marker(self):
        s = spec('t', fit='refit', eval='test', keep_half=None, recipe='full_test')
        with self.assertRaisesRegex(ValueError, 'test.started'):
            fit.validate(s)
        (self.runs / 'test.started').write_text('{}')
        self.assertEqual(fit.validate(s)['eval'], 'test')

    def test_normalized_spec(self):
        s = {k: v for k, v in spec('n', fit='train', eval='val').items() if k not in ('keep_half', 'placebo')}
        self.assertEqual(list(fit.validate(s)), list(fit.KEYS))
        self.assertEqual(fit.validate(s)['keep_half'], None)
        cfg = fit.config(fit.validate(spec('n')))
        self.assertEqual(cfg, exp.DEFAULT | roles.RECIPES['plan'] | {'seed': 1007, 'neg_seed': 7, 'extra': ['tx_p', 'tx_u'],
                                                                      'days': str(self.root / 'days')})

    def test_the_real_recipes_and_the_path_spec(self):
        mock.patch.stopall()  # the real roles.RECIPES of the contract
        self.assertEqual({k: (v['depth'], v['iterations'], v['lr'], v['l2'], v['cap'], v['neg'], v['threads'])
                          for k, v in roles.RECIPES.items()},
                         {'plan': (8, 300, 0.12, 10, 60000, 50, 10), 'full_val': (8, 500, 0.08, 10, 101959, 50, 10),
                          'full_test': (8, 500, 0.08, 10, 140680, 50, 10)})
        log = roles.ROOT / 'artifacts/task1/v2020/exp/runs.jsonl'  # the record's config only, never a metric
        lines = [x for x in log.read_text().splitlines() if x.startswith('{"name": "pl20_Hp_s0"')] if log.exists() else []
        if not lines:
            self.skipTest('no record of pl20_Hp_s0 on this machine')
        rec = json.loads(lines[-1])
        s = fit.path_spec()
        cfg = exp.DEFAULT | roles.RECIPES[s['recipe']] | {'seed': s['seed'], 'neg_seed': s['neg_seed'],
                                                          'extra': s['extra']}
        want = {k: v for k, v in rec['cfg'].items() if k != 'days'}
        self.assertEqual({k: v for k, v in cfg.items() if k != 'days'}, want)
        self.assertEqual(Path(rec['cfg']['days']).name, roles.DAYS6.name)


class QueueTest(Fixture):
    def setUp(self):
        super().setUp()
        self.calls = []

    def fake(self, code=0, write=True):
        """subprocess.run of council.fit: records the call and writes the file and the record the fit would."""
        def run(cmd, cwd=None):
            s = json.loads(Path(cmd[cmd.index('--spec') + 1]).read_text())
            data = json.loads(cmd[cmd.index('--data') + 1])
            self.calls.append((s['name'], json.loads(cmd[cmd.index('--stamp') + 1]), data))
            if write and not code:
                self.done(s, data=data)
            return subprocess.CompletedProcess(cmd, code)
        return run

    def done(self, s, record=True, data=None):
        self.fits.mkdir(exist_ok=True)
        (self.fits / f"{s['name']}.parquet").write_bytes(b'x')
        if record:
            s = fit.validate(s)
            with (self.fits / 'runs.jsonl').open('a') as f:
                f.write(json.dumps({'name': s['name'], 'spec': s, 'data': data or fit.data_stamp(s)}) + '\n')

    def queue(self, specs):
        path = self.root / f'queue-{id(specs)}.json'
        path.write_text(json.dumps(specs))
        return path

    def test_runs_in_order_skipping_done_fits(self):
        q = [spec(f'q{i}') for i in range(3)]
        self.done(q[0])
        with mock.patch.object(subprocess, 'run', self.fake()):
            self.quiet(queue.run, self.queue(q))
        self.assertEqual([c[0] for c in self.calls], ['q1', 'q2'])
        self.assertTrue(all(c[1] == fit.code_stamp() for c in self.calls))
        self.assertTrue(all(c[2] == fit.data_stamp(fit.validate(spec(c[0]))) for c in self.calls))

    def test_the_fingerprint_is_taken_once_and_a_done_fit_on_other_data_stops(self):
        q = [spec('a'), spec('b')]
        first = fit.data_stamp(fit.validate(q[1]))
        calls = []
        real = fit.data_stamp

        def counted(s):
            calls.append(s['name'])
            return real(s)

        with mock.patch.object(fit, 'data_stamp', counted), mock.patch.object(subprocess, 'run', self.fake()):
            self.quiet(queue.run, self.queue(q))
        self.assertEqual(calls, ['a', 'b'])  # once per fit, at the start of the queue, not again per fit
        self.assertEqual(self.calls[1][2], first)
        other = [spec('c')]
        self.done(other[0], data={'days6': {'files': 0, 'bytes': 0, 'mtime_ns': 0}, 'tables': {}})
        with mock.patch.object(subprocess, 'run', self.fake()), self.assertRaisesRegex(SystemExit, 'other data'):
            self.quiet(queue.run, self.queue(other))
        self.assertEqual([c[0] for c in self.calls], ['a', 'b'])

    def test_the_whole_queue_is_validated_first(self):
        for q in ([spec('a'), spec('b'), spec('c', recipe='huge')], [spec('a'), spec('a')], []):
            with mock.patch.object(subprocess, 'run', self.fake()), self.assertRaises(SystemExit):
                self.quiet(queue.run, self.queue(q))
        self.assertEqual(self.calls, [])

    def test_a_file_without_a_record_or_with_another_spec_stops(self):
        q = [spec('a'), spec('b'), spec('c')]
        self.done(q[1], record=False)
        with mock.patch.object(subprocess, 'run', self.fake()), self.assertRaisesRegex(SystemExit, 'b: a file exists'):
            self.quiet(queue.run, self.queue(q))
        self.assertEqual([c[0] for c in self.calls], ['a'])
        q2 = [spec('d', seed=1)]
        self.done(spec('d', seed=2))
        with mock.patch.object(subprocess, 'run', self.fake()), self.assertRaisesRegex(SystemExit, 'another spec'):
            self.quiet(queue.run, self.queue(q2))

    def test_a_failed_fit_stops_the_queue_with_its_code(self):
        with mock.patch.object(subprocess, 'run', self.fake(code=3)), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            self.quiet(queue.run, self.queue([spec('a'), spec('b')]))
        self.assertEqual((stop.exception.code, [c[0] for c in self.calls]), (3, ['a']))
        with mock.patch.object(subprocess, 'run', self.fake(write=False)), self.assertRaisesRegex(SystemExit, 'without'):
            self.quiet(queue.run, self.queue([spec('e')]))


if __name__ == '__main__':
    unittest.main()
