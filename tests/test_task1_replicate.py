"""Task 1 period switch and the 2020 replication: paths, the exclusion rule, the capped pool and the reading rules.

Run: .venv/bin/python -m unittest tests.test_task1_replicate
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def run(code, period=None):
    """Run code in a fresh interpreter (modules read TASK1_PERIOD at import) and return its stdout."""
    env = {k: v for k, v in os.environ.items() if k not in ('TASK1_PERIOD', 'TASK1_DAYS')}
    if period:
        env['TASK1_PERIOD'] = period
    r = subprocess.run([sys.executable, '-c', textwrap.dedent(code)], cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(r.stderr)
    return r.stdout


PATHS = """
    import json
    from task1 import data, exp, extra, model as M
    rel = lambda p: str(p.relative_to(M.ROOT))
    print(json.dumps({'splits': M.SPLITS, 'days': rel(M.DAYS), 'extra': rel(M.EXTRA), 'raw': rel(data.RAW),
                      'months': data.MONTHS, 'db': rel(data.DB), 'days6': rel(extra.DAYS), 'events': rel(extra.EVENTS),
                      'exp': rel(exp.OUT)}))
"""


class PeriodTest(unittest.TestCase):
    def test_default_is_the_study_period(self):
        p = json.loads(run(PATHS))
        self.assertEqual(p['splits'], {'train': ['2019-10-15', '2019-11-07'], 'val': ['2019-11-08', '2019-11-13'],
                                       'refit': ['2019-10-15', '2019-11-13'], 'test': ['2019-11-18', '2019-11-28']})
        self.assertEqual([p[k] for k in ('days', 'extra', 'days6', 'events', 'exp')],
                         ['artifacts/task1/v2/days', 'artifacts/task1/v2/extra', 'artifacts/task1/v2/days6',
                          'artifacts/task1/v2/events_by_day', 'artifacts/task1/v2/exp'])
        self.assertEqual((p['raw'], p['months'], p['db']), ('data/raw', ['2019-Oct', '2019-Nov'], 'data/processed/rees46.duckdb'))

    def test_2020_has_its_own_paths_and_splits(self):
        p = json.loads(run(PATHS, '2020'))
        self.assertEqual(p['splits']['refit'], ['2020-01-15', '2020-02-13'])
        self.assertEqual(p['splits']['test'], ['2020-02-14', '2020-02-29'])
        self.assertTrue(all(p[k].startswith('artifacts/task1/v2020/') for k in ('days', 'extra', 'days6', 'events', 'exp')))
        self.assertEqual((p['raw'], p['db']), ('data/raw2020', 'data/processed/rees46-2020.duckdb'))

    def test_2019_decisions_refuse_2020(self):
        # if a guard regressed, the module would reach the stubs (or the empty day directory) instead of scoring
        # the 2020 test or calling the model
        stub = '''
            import runpy, subprocess, sys, duckdb
            def side_effect(*a, **k):
                raise RuntimeError('a side effect ran before the period guard')
            for name in ('connect', 'sql', 'query', 'read_parquet', 'read_csv'):
                setattr(duckdb, name, side_effect)
            subprocess.run = subprocess.Popen = side_effect
            sys.argv = [sys.argv[1], *sys.argv[2:]]
            runpy.run_module(sys.argv[0], run_name='__main__', alter_sys=True)
        '''
        with tempfile.TemporaryDirectory() as empty:
            env = dict(os.environ, TASK1_PERIOD='2020', TASK1_DAYS=empty)
            for module, args in (('task1.final', ['--eval', 'test']), ('task1.dfs', ['--select', '20']),
                                 ('task1.agent', []), ('task1.baseline', []), ('task1.model', ['--eval', 'test']),
                                 ('task1.posthoc', [])):
                r = subprocess.run([sys.executable, '-c', textwrap.dedent(stub), module, *args], cwd=ROOT, env=env,
                                   capture_output=True, text=True)
                self.assertNotEqual(r.returncode, 0, module)
                self.assertRegex(r.stderr, '2019 study period only|task1.replicate only', module)
                self.assertNotIn('side effect', r.stderr, module)

    def test_unknown_period_stops(self):
        with self.assertRaises(AssertionError):
            run('import task1.model', '1999')


class ExclusionTest(unittest.TestCase):
    def test_frozen_anchors_follow_from_the_broken_days(self):
        # the broken days are those of the raw files; that the imported database gives the same is checked by
        # replicate.main before every evaluation
        out = run("""
            import json
            from task1 import replicate
            spec = json.loads(replicate.SPEC.read_text())
            print(json.dumps([replicate.excluded(['2020-01-01', '2020-01-02', '2020-02-27']), spec['excluded']]))
        """, '2020')
        got, frozen = json.loads(out)
        self.assertEqual(got, ['2020-02-27', '2020-02-28'])
        self.assertEqual(got, frozen)

    def test_rule_on_a_small_database(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'events.duckdb'
            con = duckdb.connect(str(db))
            rows = []
            for day in range(1, 11):
                views, carts, buys = 100, 40, 20
                if day == 5:
                    buys = 8      # 0.4 of the median: broken
                if day == 8:
                    views = 60    # 0.6 of the median: kept
                for kind, n in (('view', views), ('cart', carts), ('purchase', buys)):
                    rows += [(f'2020-01-{day:02d} 12:00:00', kind)] * n
            con.execute('CREATE TABLE events(event_time TIMESTAMP, event_type VARCHAR)')
            con.executemany('INSERT INTO events VALUES (?, ?)', rows)
            con.close()
            out = run(f"""
                from pathlib import Path
                from task1 import replicate
                replicate.P.DB = Path({str(db)!r})
                print(replicate.broken_days())
            """, '2020')
            self.assertEqual(out.strip(), "['2020-01-05']")

            con = duckdb.connect(str(db))
            con.execute("DELETE FROM events WHERE event_time::DATE = DATE '2020-01-07'")
            con.close()
            with self.assertRaisesRegex(AssertionError, 'misses whole days'):
                run(f"""
                    from pathlib import Path
                    from task1 import replicate
                    replicate.P.DB = Path({str(db)!r})
                    replicate.broken_days()
                """, '2020')


LAYOUT = """
    import json, sys
    from pathlib import Path
    import duckdb, pandas as pd
    from task1 import model as M, replicate as R
    tmp, case = Path(sys.argv[1]), sys.argv[2]
    d6, d4 = tmp / 'days6', tmp / 'days'
    M.EXTRA = tmp / 'extra'
    days = [str(d) for d in M.days('refit')] + [str(d) for d in M.days('test')]
    for i, d in enumerate(days):
        users = [1, 2, 3]
        for path, extra_user in ((d6, False), (d4, case == 'queries' and d == '2020-02-20')):
            df = pd.DataFrame({'anchor': pd.Timestamp(d), 'user_id': users + [9] * extra_user, 'product_id': 5,
                               'label': 0, 's_rank': 1.0, 'u_n': 2.0, 'i_n': 3.0})
            if case == 'drift' and path == d6 and d == '2020-02-20':
                df['s_new'] = 1.0
            path.mkdir(exist_ok=True)
            if not (case == 'no_day' and path == d4 and d == '2020-02-29'):
                duckdb.sql(f"COPY (SELECT * FROM df) TO '{path / (d + '.parquet')}' (FORMAT PARQUET)")
        x = pd.DataFrame({'user_id': users, 'f_x_v': 0.5})
        (M.EXTRA / 'tab').mkdir(parents=True, exist_ok=True)
        if not (case == 'no_extra' and i == 3):
            duckdb.sql(f"COPY (SELECT * FROM x) TO '{M.EXTRA / 'tab' / (d + '.parquet')}' (FORMAT PARQUET)")
    spec = {'cap': 100, 'dfs_selected': [], 'features': {'base': 3, 'base_4src': 3, 'x': 4 if case != 'count' else 5},
            'arms': [{'name': 'base', 'config': {'days': str(d6)}}, {'name': 'base_4src', 'config': {'days': str(d4)}},
                     {'name': 'x', 'config': {'days': str(d6), 'extra': ['tab']}}]}
    print(R.preflight(spec, 'test')[0])
"""


class PreflightTest(unittest.TestCase):
    def check(self, case):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k != 'TASK1_DAYS'} | {'TASK1_PERIOD': '2020'}
            return subprocess.run([sys.executable, '-c', textwrap.dedent(LAYOUT), d, case], cwd=ROOT, env=env,
                                  capture_output=True, text=True)

    def test_a_complete_layout_passes(self):
        r = self.check('ok')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), '90')  # 30 refit days of 3 users, under the cap of 100

    def test_each_gap_stops_it(self):
        for case, message in (('no_day', 'lacks 1 days, first 2020-02-29'), ('no_extra', 'x: extra tab lacks 1 days'),
                              ('drift', 'the columns of 1 days differ from 2020-01-15, first 2020-02-20'),
                              ('count', 'x: 4 features, spec.json expects 5'), ('queries', 'different queries on test')):
            r = self.check(case)
            self.assertNotEqual(r.returncode, 0, case)
            self.assertIn(message, r.stderr, case)


FAKE_TEST = """
    import sys
    from pathlib import Path
    import numpy as np, pandas as pd
    from task1 import model as M, replicate as R
    out, version, crash = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    R.OUT = out
    R.check_frozen = lambda spec: None
    R.broken_days = lambda: ['2020-01-01', '2020-01-02', '2020-02-27']
    R.preflight = lambda spec, split: (140680, 'digest')
    R.stamp = lambda inputs: {'files': {'task1/x.py': version}, 'inputs': inputs}
    R.GRID_2019 = out / 'grid-2019.json'
    R.GRID_2019.write_text('{"grid": {"verdict": {"R": "x", "H+": "y"}}}')
    def run_arm(arm, spec, split, seeds, over, expect):
        with open(out / 'calls.txt', 'a') as f:
            f.write(arm['name'] + '\\n')
        if arm['name'] == crash:
            raise RuntimeError('crash in ' + crash)
        rng = np.random.default_rng(len(arm['name']))
        days = [str(d) for d in M.days(split)]
        qid = [f'{days[i % len(days)]}:{i}' for i in range(400)]
        frames = [pd.DataFrame({'ndcg': rng.random(400) * 0.3, 'recall': rng.random(400),
                                'anchor': [q.split(':')[0] for q in qid]}, index=pd.Index(qid, name='qid')).sort_index()
                  for _ in seeds]
        return frames, {'arm': arm['name'], 'fits': [{'fit_queries': expect}] * len(seeds)}
    R.run_arm = run_arm
    sys.argv = ['replicate', '--eval', 'test', *sys.argv[4:]]
    R.main()
"""


class TestLogTest(unittest.TestCase):
    """The test is opened once: a stopped run goes on or starts over, nothing about it is printed before the end."""

    def run_test(self, out, version, crash='', *args):
        env = {k: v for k, v in os.environ.items() if k != 'TASK1_DAYS'} | {'TASK1_PERIOD': '2020'}
        return subprocess.run([sys.executable, '-c', textwrap.dedent(FAKE_TEST), str(out), version, crash, *args],
                              cwd=ROOT, env=env, capture_output=True, text=True)

    def calls(self, out):
        return (out / 'calls.txt').read_text().split()

    def test_resume_after_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            r = self.run_test(out, 'v1', 'F0')
            self.assertIn('crash in F0', r.stderr)
            self.assertNotIn('ndcg', r.stdout)  # five arms were done, none showed a metric
            self.assertTrue((out / 'test_dfs.json').exists() and (out / 'test_dfs_s1.parquet').exists())
            self.assertIn('--resume continues it', self.run_test(out, 'v1').stderr)
            self.assertIn('--resume needs the code, spec and inputs', self.run_test(out, 'v2', '', '--resume').stderr)
            (out / 'calls.txt').unlink()
            r = self.run_test(out, 'v1', '', '--resume')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.calls(out), ['F0', 'F1', 'Hp'])
            res = json.loads((out / 'test.json').read_text())
            self.assertEqual([e['event'] for e in res['run']['log']], ['start', 'resume'])
            self.assertEqual(sum(a.get('resumed', False) for a in res['arms']), 5)
            self.assertEqual(res['primary']['anchors'], 14)
            self.assertEqual(res['all_days']['anchors'], 16)
            self.assertIn('already evaluated', self.run_test(out, 'v1', '', '--resume').stderr)

    def test_restart_after_a_fix(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            self.run_test(out, 'v1', 'agent')
            (out / 'calls.txt').unlink()
            r = self.run_test(out, 'v2', '', '--restart', 'out of memory in agent; fixed in abc123')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(len(self.calls(out)), 8)
            self.assertTrue((out / 'aborted-1' / 'test_base_s0.parquet').exists())
            log = json.loads((out / 'test.json').read_text())['run']['log']
            self.assertEqual([e['event'] for e in log], ['start', 'restart'])
            self.assertEqual(log[1]['reason'], 'out of memory in agent; fixed in abc123')
            self.assertEqual(log[1]['stamp'], {'files': {'task1/x.py': 'v2'}, 'inputs': 'digest'})

    def test_refusals(self):
        import fcntl
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out'
            out.mkdir()
            self.assertIn('no test run to resume', self.run_test(out, 'v1', '', '--resume').stderr)
            self.assertIn('frozen spec only', self.run_test(out, 'v1', '', '--iterations', '5').stderr)
            with open(out / 'test.lock', 'w') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertIn('another test process is running', self.run_test(out, 'v1').stderr)
            (out / 'test_base_s0.parquet').write_text('')
            self.assertIn('test files without a test log', self.run_test(out, 'v1').stderr)
            self.assertFalse((out / 'test.started').exists())


class CapTest(unittest.TestCase):
    def test_cap_keeps_whole_queries_in_hash_order(self):
        from task1 import exp, model as M
        rng = np.random.default_rng(0)
        with tempfile.TemporaryDirectory() as d:
            for day in M.days('train'):
                n = 60
                df = pd.DataFrame({'anchor': pd.Timestamp(day), 'user_id': rng.integers(1, 15, n),
                                   'product_id': rng.integers(1, 10**6, n), 'label': (rng.random(n) < 0.1).astype(int),
                                   'cf_cv_cond_tdecay20': rng.random(n)})
                df = df.drop_duplicates(['user_id', 'product_id'])
                duckdb.sql(f"COPY (SELECT * FROM df) TO '{d}/{day}.parquet' (FORMAT PARQUET)")
            full = exp._read('train', d)
            capped = exp._read('train', d, cap=25)
            exp._cache.clear()
            want = duckdb.sql(f"""SELECT anchor::VARCHAR || ':' || user_id::VARCHAR qid FROM (
                SELECT DISTINCT anchor, user_id FROM read_parquet('{d}/*.parquet'))
                ORDER BY hash(user_id, 2026), user_id, anchor LIMIT 25""").df().qid
            self.assertEqual(sorted(capped.qid.unique()), sorted(want))
            same = full[full.qid.isin(want)].reset_index(drop=True)
            pd.testing.assert_frame_equal(capped.reset_index(drop=True), same)


def fake_runs(effects, n=3000, anchors=('2020-02-14', '2020-02-15', '2020-02-27'), noise=None):
    """Per-query metrics per arm and seed: base plus an effect (one number, or one per seed) and noise per arm."""
    rng = np.random.default_rng(1)
    qid = [f'{anchors[i % len(anchors)]}:{i}' for i in range(n)]
    base = rng.random(n) * 0.3
    runs = {}
    for arm, eff in effects.items():
        eff = eff if isinstance(eff, tuple) else (eff, eff)
        sd = (noise or {}).get(arm, 0.002)
        runs[arm] = [pd.DataFrame({'ndcg': base + e + rng.normal(0, sd, n), 'anchor': [q.split(':')[0] for q in qid]},
                                  index=pd.Index(qid, name='qid')) for e in eff]
    return runs


ARMS = ('base', 'base_4src', 'base_4src_d8', 'dfs', 'agent', 'F0', 'F1', 'Hp')


class RulesTest(unittest.TestCase):
    def setUp(self):
        from task1 import replicate  # compare() needs no period: it reads only the runs it is given
        self.replicate = replicate

    def test_rules_read_the_effects(self):
        runs = fake_runs({'base': 0, 'base_4src': -0.06, 'base_4src_d8': -0.05, 'dfs': 0.05, 'agent': 0.0,
                          'F0': -0.1, 'F1': -0.01, 'Hp': 0.0})
        res = self.replicate.compare(runs, ['2020-02-14', '2020-02-15'], {'R': 'x', 'H+': 'y'})
        self.assertEqual(res['queries'], 2000)
        r = res['rules']
        self.assertEqual(r['candidates'], 'повторён')
        self.assertEqual(r['dfs'], 'опровергнут: прирост с CI > 0')
        self.assertEqual(r['agent'], 'повторён: прирост от +0.0008 исключён')
        self.assertEqual(r['grid']['R'], 'автоматика воспроизводит большую часть вклада ручных признаков, но уступает им')
        self.assertTrue(r['grid']['H+'].startswith('автоматика не дополняет'))
        self.assertFalse(r['grid_same_as_2019'])
        self.assertAlmostEqual(res['grid']['R_F1'][0], 0.9, places=2)

    def test_the_other_outcomes(self):
        runs = fake_runs({a: 0 for a in ARMS} | {'base_4src_d8': 0.05, 'agent': 0.0004, 'dfs': 0.01, 'F0': -0.1,
                                                 'F1': 0.0, 'Hp': (0.01, 0.0)}, noise={'agent': 0.04})
        res = self.replicate.compare(runs, ['2020-02-14', '2020-02-15'], None)
        r, (_, lo, hi) = res['rules'], res['diff']['agent-base']
        self.assertEqual(r['candidates'], 'опровергнут')
        self.assertLessEqual(lo, 0)
        self.assertGreaterEqual(hi, 0.0008)
        self.assertEqual(r['agent'], 'не повторён: CI доходит до +0.0008')
        self.assertEqual(r['dfs'], 'опровергнут: прирост с CI > 0')
        self.assertTrue(r['grid']['H+'].startswith('автоматика не дополняет'))  # one seed of two is not enough
        self.assertAlmostEqual(res['grid']['Hp-H_by_seed'][0][0], 0.01, places=3)

    def test_excluded_anchors_leave_the_primary_set(self):
        runs = fake_runs({a: 0 for a in ARMS} | {'F0': -0.1})
        runs['agent'] = [r.assign(ndcg=r.ndcg + np.where(r.anchor == '2020-02-27', 0.3, 0)) for r in runs['agent']]
        primary = self.replicate.compare(runs, ['2020-02-14', '2020-02-15'], None)
        every = self.replicate.compare(runs, ['2020-02-14', '2020-02-15', '2020-02-27'], None)
        self.assertEqual(primary['rules']['agent'], 'повторён: прирост от +0.0008 исключён')
        self.assertEqual(every['rules']['agent'], 'опровергнут: прирост с CI > 0')
        self.assertNotIn('grid_same_as_2019', primary['rules'])


if __name__ == '__main__':
    unittest.main()
