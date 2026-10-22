"""council.side.task1_side (H9–H11) on synthetic day tables under /tmp/tlab-side-*; no REES46 data is read.

Checks: the one reader of day tables refuses a test day before a file is opened, any split but train/val, anchors
outside 15.10–13.11.2019 and sealed directories, and keeps only half A of val; outputs outside artifacts/side/<h>/
and council/runs/side/ (or through a sealed directory) are refused; TASK1_PERIOD != 2019 stops the module; `fit`
without rsm is exp.fit; the last stage of staged_predict(RawFormulaVal) ranks every query as M.predict and gives the
same NDCG@20, and stage j holds min((j+1)·every, trees) trees; N*, N_full, the H10 and H11 rules; the snapshot skips
sealed directories and splits incidents from reconciliations; the AST guard (no test/refit/sealed reads, no half B,
day tables only through `read_days`). End to end on synthetic days: the reference fits come from exp.run itself and
the path check must repeat them with max|Δ| = 0; h9, h10, h11 and --dry run on the same stand, B rows of the
references are NaN (reading them would fail), and every write stays under the temporary roots.

Run: TASK1_PERIOD=2019 .venv/bin/python -m unittest council.tests.test_side_task1 -v
"""
import ast
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from council import side as S
from council.side import task1_side as T
from task1 import exp
from task1 import model as M

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'council' / 'side' / 'task1_side.py'
SMALL = dict(iterations=20, threads=2)
SCAN = dict(iterations=150, eval_period=50)
BASE_FEATURES = 3  # s_a, u_b, cf_cv_cond_tdecay20


CREATED = []  # the temporary roots of this module, removed in tearDownModule


def tmp_root() -> Path:
    p = Path(tempfile.mkdtemp(dir='/tmp', prefix='tlab-side-'))
    CREATED.append(p)
    return p


def tearDownModule():
    for p in CREATED:
        if str(p).startswith('/tmp/tlab-side-'):
            shutil.rmtree(p, ignore_errors=True)


def write_parquet(df, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.register('_f', df)
        cast = ', anchor::DATE AS anchor' if 'anchor' in df.columns else ''
        cols = 'EXCLUDE (anchor)' if cast else ''
        con.execute(f"COPY (SELECT * {cols}{cast} FROM _f) TO '{path}' (FORMAT PARQUET)")
    finally:
        con.close()


def all_days():
    return list(M.days('train')) + list(M.days('val'))


def build_stand(root: Path, users=30, per=10):
    """days/<day>.parquet for train, val and one test day; extra/<table>/<day>.parquet for the 34 tables of H+."""
    days, extra = root / 'days', root / 'extra'
    rng = np.random.default_rng(0)
    pool = rng.choice(10 ** 6, 80, replace=False)
    for d in all_days() + [date(2019, 11, 18)]:
        u = np.repeat(rng.choice(pool, users, replace=False), per)
        n = len(u)
        s_a, u_b, cf = rng.normal(size=n), rng.normal(size=n), rng.normal(size=n)
        label = (rng.random(n) < 1 / (1 + np.exp(-(-1.5 + 1.2 * s_a + 0.6 * u_b)))).astype(np.int32)
        purchase = (label * (rng.random(n) < 0.4)).astype(np.int32)
        df = pd.DataFrame({'anchor': pd.Timestamp(d), 'user_id': u.astype(np.int64),
                           'product_id': np.tile(np.arange(per), users).astype(np.int64), 'label': label,
                           'label_purchase': purchase, 's_a': s_a, 'u_b': u_b, 'cf_cv_cond_tdecay20': cf})
        g = df.groupby('user_id')
        df['n_targets'] = (g.label.transform('sum') + (df.user_id % 2)).astype(np.int32)
        df['n_targets_purchase'] = g.label_purchase.transform('sum').astype(np.int32)
        write_parquet(df, days / f'{d}.parquet')
        for i, t in enumerate(T.HP_EXTRA):
            x = df[['user_id', 'product_id']].copy()
            x[f'f_x_t{i}'] = rng.normal(size=n) + (0.5 * label if i % 7 == 0 else 0)
            if d in all_days():
                write_parquet(x, extra / t / f'{d}.parquet')
    return days, extra


def expected_small():
    """EXPECTED with the feature counts of the synthetic stand (one column per extra table)."""
    return {n: (o, BASE_FEATURES + len(o.get('extra', []))) for n, (o, _) in T.EXPECTED.items()}


class Stand:
    """One synthetic stand shared by the end-to-end tests: reference fits made by exp.run, B rows set to NaN."""
    root = days = extra = ref = None

    @classmethod
    def get(cls):
        if cls.root is None:
            cls.root = tmp_root()
            cls.days, cls.extra = build_stand(cls.root)
            cls.ref = cls.root / 'ref'
            (cls.root / 'refcwd').mkdir()
            with cls.patched(), chdir(cls.root / 'refcwd'):  # exp.fit writes catboost_info into the cwd
                ctx = cls.ctx('path')
                for name, (over, _) in T.EXPECTED.items():
                    exp.run(name, **T.config(ctx, over))
            for name in T.EXPECTED:
                p = cls.ref / f'{name}.parquet'
                df = duckdb.sql(f"SELECT * FROM read_parquet('{p}')").df()
                for c in T.METRICS:
                    df.loc[df.half != 'A', c] = np.nan
                p.unlink()
                write_parquet(df, p)
        return cls

    @classmethod
    @contextlib.contextmanager
    def patched(cls):
        with mock.patch.object(M, 'EXTRA', cls.extra), mock.patch.object(exp, 'OUT', cls.ref), \
                mock.patch.dict(T.EXPECTED, expected_small()):
            yield

    @classmethod
    def ctx(cls, h, **kw):
        out = T.make_out(h, cls.root / 'art', cls.root / 'runs')
        prot = cls.root / 'prot'
        (prot / 'v2').mkdir(parents=True, exist_ok=True)
        (prot / 'xfer').mkdir(parents=True, exist_ok=True)
        return T.Ctx(h, out, days=cls.days, ref_dir=cls.ref, over=dict(SMALL), scan=dict(SCAN),
                     heavy_kw={'lock_path': cls.root / 'heavy.lock', 'procs_fn': lambda: []}, wait=False,
                     check_fn=lambda: None, snapshot_roots={prot / 'v2': 'incident', prot / 'xfer': 'reconcile'},
                     **kw)


@contextlib.contextmanager
def chdir(p):
    old = os.getcwd()
    os.chdir(p)
    try:
        yield
    finally:
        os.chdir(old)


# ---------------------------------------------------------------- guard of the reader

class Reader(unittest.TestCase):
    def test_test_day_refused_before_read(self):
        root = tmp_root()
        (root / 'days').mkdir()
        write_parquet(pd.DataFrame({'anchor': [pd.Timestamp('2019-11-18')], 'user_id': [1]}),
                      root / 'days' / '2019-11-18.parquet')
        boom = mock.Mock(side_effect=AssertionError('a file was read'))
        with mock.patch.object(exp, 'read_day', boom), mock.patch.object(exp, '_read', boom), \
                mock.patch.object(duckdb, 'sql', boom):
            for split in ('train', 'val'):
                with self.assertRaises(S.Refused):
                    T.read_days(split, root / 'days', date(2019, 11, 18))
            with self.assertRaises(S.Refused):
                T.count_queries(root / 'days', [date(2019, 11, 18)])
            for split in ('te' + 'st', 'ref' + 'it'):
                with self.assertRaises(S.Refused):
                    T.read_days(split, root / 'days')
                with self.assertRaises(S.Refused):
                    T.read_days(split, root / 'days', date(2019, 11, 8))
            with self.assertRaises(S.Refused):
                T.read_days('train', root / 'days', date(2019, 10, 14))
            with self.assertRaises(S.Refused):
                T.read_days('val', root / 'days', date(2019, 11, 7))  # a train day asked as val
            with self.assertRaises(S.Refused):
                T.read_days('val', root / 'days')  # the pool is train only
            sealed = root / 'sealed' / 'days'
            sealed.mkdir(parents=True)
            with self.assertRaises(S.Refused):
                T.read_days('train', sealed, date(2019, 11, 4))
        boom.assert_not_called()

    def test_val_keeps_half_a_only(self):
        st = Stand.get()
        d = date(2019, 11, 8)
        full = exp.read_day(d, str(st.days))
        a = T.read_days('val', st.days, d)
        self.assertTrue((exp.half(a.user_id.to_numpy()) == 'A').all())
        self.assertEqual(len(a), int((exp.half(full.user_id.to_numpy()) == 'A').sum()))
        self.assertGreater(len(full), len(a))
        tail = T.read_days('train', st.days, date(2019, 11, 4))
        self.assertEqual(len(tail), len(exp.read_day(date(2019, 11, 4), str(st.days))))


# ---------------------------------------------------------------- outputs, period, names

class Outputs(unittest.TestCase):
    def test_paths_outside_refused(self):
        root = tmp_root()
        with self.assertRaises(S.Refused):
            T.make_out('h9', Path('/tmp/elsewhere-side'), root / 'runs')
        ctx = T.Ctx('h9', T.make_out('h9', root / 'art', root / 'runs'), check_fn=lambda: None)
        for parts in (('..', 'x.json'), ('..', '..', 'artifacts', 'task1', 'x'), (SEALED_PART, 'x.json')):
            with self.assertRaises(S.Refused):
                T.wpath(ctx, *parts)
        with self.assertRaises(S.Refused):
            T.wpath(ctx, '..', 'x.json', runs=True)
        self.assertEqual(T.wpath(ctx, 'runs.jsonl'), root / 'art' / 'h9' / 'runs.jsonl')
        self.assertEqual(T.wpath(ctx, T.result_name(ctx), runs=True), root / 'runs' / 'h9-result.json')
        with self.assertRaises(S.Refused):  # the real roots are fixed; another default is refused by Out
            S.Out('h9', ROOT / 'artifacts' / 'task1', None)

    def test_names_and_sealed_inputs_refused(self):
        root = tmp_root()
        ctx = T.Ctx('h9', T.make_out('h9', root / 'art', root / 'runs'), days=root / 'days', check_fn=lambda: None)
        with self.assertRaises(S.Refused):
            T.validate(ctx, 'h10_x_s0', T.config(ctx, {}))
        with self.assertRaises(S.Refused):
            T.validate(ctx, 'q2_d8', T.config(ctx, {}))
        with self.assertRaises(S.Refused):
            T.validate(ctx, 'h9_x_s0', T.config(ctx, {'loss': 'YetiRank'}))
        with self.assertRaises(S.Refused):
            T.validate(ctx, 'h9_x_s0', T.config(ctx, {'cap': 5}))
        sealed = T.Ctx('h9', ctx.out, days=root / SEALED_PART / 'days', check_fn=lambda: None)
        with self.assertRaises(S.Refused):
            T.validate(sealed, 'h9_x_s0', T.config(sealed, {}))
        T.validate(ctx, 'h9_x_s0', T.config(ctx, {'rsm': 0.5}))
        self.assertEqual(T.result_name(T.Ctx('h11', T.make_out('h11', root / 'art', root / 'runs'), groups=10,
                                             check_fn=lambda: None)), 'h11-L10-result.json')

    def test_period_other_than_2019_stops(self):
        for env in ('2020', '2021'):
            r = subprocess.run([sys.executable, '-m', 'council.side.task1_side', 'h9', '--dry'], cwd=ROOT,
                               capture_output=True, text=True, env={**os.environ, 'TASK1_PERIOD': env}, timeout=120)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('2019 only', r.stderr)
            self.assertEqual(r.stdout, '')

    def test_committed_list(self):
        self.assertEqual(T.COMMITTED, ('council/side/task1_side.py', 'council/tests/test_side_task1.py',
                                       'council/side/__init__.py', 'council/runs/side/h9.md',
                                       'council/runs/side/h10.md', 'council/runs/side/h11.md'))
        self.assertEqual(T.STAMPED, ('task1/exp.py', 'task1/model.py', 'task1/period.py', 'council/side/__init__.py',
                                     'council/side/task1_side.py'))
        self.assertEqual(set(T.SNAPSHOT_ROOTS), {'artifacts/task1/v2', 'task1/runs', 'artifacts/task1/v2020',
                                                 'artifacts/xfer'})
        self.assertEqual(T.SKIPS, ('stage3', 'refit_H'))


SEALED_PART = 'sea' + 'led'


# ---------------------------------------------------------------- fit, staged scan, rules

def frame(n_queries, seed, per=15):
    rng = np.random.default_rng(seed)
    n = n_queries * per
    s_a, u_b = rng.normal(size=n), rng.normal(size=n)
    label = (rng.random(n) < 1 / (1 + np.exp(-(-1.5 + 1.5 * s_a + 0.7 * u_b)))).astype(int)
    df = pd.DataFrame({'qid': np.repeat([f'q{i:04d}' for i in range(n_queries)], per),
                       'product_id': np.tile(np.arange(per), n_queries), 's_a': s_a, 'u_b': u_b, 'label': label})
    df['n_targets'] = df.groupby('qid').label.transform('sum') + 1
    return df


class FitAndScan(unittest.TestCase):
    CFG = exp.DEFAULT | dict(iterations=60, depth=4, threads=2)

    def test_fit_is_exp_fit_without_rsm(self):
        train = frame(150, 1)
        test = frame(80, 2)
        f = ['s_a', 'u_b']
        root = tmp_root()
        with chdir(root):
            ref = exp.fit(train, f, self.CFG)
        m = T.fit(train, f, self.CFG)
        np.testing.assert_array_equal(M.predict(ref, test, f), M.predict(m, test, f))
        self.assertNotIn('rsm', m.get_params())
        self.assertEqual(T.fit(train, f, self.CFG | {'rsm': 0.5}).get_params()['rsm'], 0.5)

    def test_staged_last_stage_is_predict_order(self):
        train, val = frame(200, 3), frame(120, 4)
        f = ['s_a', 'u_b']
        m = T.fit(train, f, self.CFG | {'iterations': 120})
        stages = list(m.staged_predict(val[f], prediction_type='RawFormulaVal', eval_period=50))
        self.assertEqual(len(stages), 3)
        for j, raw in enumerate(stages):
            k = T.stage_trees(j, 50, m.tree_count_)
            np.testing.assert_allclose(raw, m.predict(val[f], prediction_type='RawFormulaVal', ntree_end=k))
        proba = M.predict(m, val, f)
        last = stages[-1]
        order = lambda s: (val.assign(s=s).sort_values(['qid', 's', 'product_id'], ascending=[True, False, True],
                                                       kind='stable').groupby('qid').product_id.apply(list))
        self.assertEqual(order(last).to_dict(), order(proba).to_dict())
        curve = T.staged_ndcg(m, val, f, 50)
        self.assertEqual(sorted(curve), [50, 100, 120])
        pd.testing.assert_series_equal(curve[120], M.per_query(val, proba)['ndcg'])

    def test_n_star_and_n_full(self):
        self.assertEqual(T.n_star({50: 0.1, 100: 0.3, 150: 0.3, 200: 0.2}), 100)
        self.assertEqual(T.n_full(500, 101959, 85000), 600)  # 599.75 -> 600
        self.assertEqual(T.n_full(50, 5, 2), 150)  # 125 is exactly between 100 and 150: up
        self.assertEqual(T.n_full(1500, 2, 1), 2000)
        self.assertEqual(T.n_full(450, 101959, 101959), 450)

    def test_h10_verdicts(self):
        sc = {'n_star': 450, 'n_full': 550}
        self.assertIn('у оптимума', T.h10_verdict('H', sc, None))
        sc = {'n_star': 900, 'n_full': 1100}
        good = {'mean': {'d': 0.001, 'ci': [0.0001, 0.002]}, 'by_seed': [{'d': 0.001}, {'d': 0.0005}]}
        self.assertIn('даёт прирост', T.h10_verdict('H', sc, good))
        one_seed = {'mean': {'d': 0.001, 'ci': [0.0001, 0.002]}, 'by_seed': [{'d': 0.002}, {'d': -0.0001}]}
        self.assertEqual(T.h10_verdict('H', sc, one_seed), 'без выигрыша на A')
        worse = {'mean': {'d': -0.002, 'ci': [-0.003, -0.001]}, 'by_seed': [{'d': -0.002}, {'d': -0.002}]}
        self.assertIn('хуже', T.h10_verdict('H', sc, worse))

    def test_h11_rules_in_order(self):
        ci = lambda lo, hi: {'ci': [lo, hi]}
        self.assertEqual(T.h11_rule({'D': ci(-2, -1), 'E': ci(1, 2)}, 0, 5)[0], 1)
        self.assertEqual(T.h11_rule({'D': ci(-2, -1), 'E': ci(1, 2)}, 1, 5)[0], 2)
        self.assertEqual(T.h11_rule({'D': ci(-1, 1), 'E': ci(1, 2)}, 1, 5)[0], 3)
        self.assertEqual(T.h11_rule({'D': ci(1, 2), 'E': ci(1, 2)}, 1, 5)[0], 4)
        self.assertEqual(T.h11_rule({'D': ci(-1, 1), 'E': ci(-1, 1)}, 2, 5)[0], 5)
        self.assertIn('по 10', T.h11_rule({}, 0, 10)[1])

    def test_groups(self):
        g5, g10, g15 = T.groups_of(5), T.groups_of(10), T.groups_of(15)
        self.assertEqual([len(g) for g in g5], [5] * 6)
        self.assertEqual([len(g) for g in g10], [10] * 3)
        self.assertEqual([len(g) for g in g15], [15] * 2)
        for gs in (g5, g10, g15):
            self.assertEqual([t for g in gs for t in g], T.AGENT)
        self.assertEqual(T.h11_name(10, 2, 1), 'h11_L10_g2_s1')
        self.assertEqual(T.h11_name(5, 3, 0), 'h11_g3_s0')
        if T.GRID_JSON.exists():
            T.check_grid_order()


# ---------------------------------------------------------------- snapshot, processes

class Snapshot(unittest.TestCase):
    def test_skips_sealed_and_splits(self):
        root = tmp_root()
        (root / 'v2' / SEALED_PART).mkdir(parents=True)
        (root / 'v2' / SEALED_PART / 'hidden.json').write_text('{}')
        (root / 'v2' / 'a.txt').write_text('a')
        (root / 'xfer').mkdir()
        roots = {root / 'v2': 'incident', root / 'xfer': 'reconcile'}
        before = T.snapshot(roots)
        self.assertFalse(any(SEALED_PART in k for k in before))
        (root / 'v2' / SEALED_PART / 'hidden.json').write_text('{"x": 1}')
        self.assertTrue(T.snapshot_verdict(before, roots)['unchanged'])
        (root / 'xfer' / 'n.txt').write_text('n')
        v = T.snapshot_verdict(before, roots)
        self.assertEqual((v['n_incident'], len(v['reconcile'])), (0, 1))
        (root / 'v2' / 'a.txt').write_text('changed!')
        self.assertEqual(T.snapshot_verdict(before, roots)['n_incident'], 1)

    def test_check_2019_sees_task1_fits(self):
        from council.xfer import queue as Q
        T.check_2019([(1, 0, 'python -m council.side.task1_side h9')], own={99})
        for cmd in ('.venv/bin/python -m task1.placebo run q.json', 'python -m task1.exp queue.json',
                    'python -m council.fit --spec x'):
            with self.assertRaises(Q.Busy):
                T.check_2019([(1, 0, cmd)], own={99})


# ---------------------------------------------------------------- AST guard

LATE_DAY = re.compile(r'2019-11-(1[4-9]|[23]\d)|2019-12|2020-')
WORD = re.compile(r'(?<![a-z])(test|refit|final|v2020)(?![a-z])')
ALLOWED_NAMES = ('SNAPSHOT_ROOTS', 'COMMITTED', 'STAMPED', 'TASK1_HEAVY', 'SKIPS', 'DEVIATIONS')  # names, not reads
READERS = ('metrics_a', 'count_queries')
FORBIDDEN_IMPORTS = ('task1.placebo', 'task1.posthoc', 'task1.leakcheck', 'task1.final', 'task1.replicate',
                     'council.broker', 'council.xfer.broker', 'council.reveal')


def violations(src: str) -> list:
    """What task1_side may not contain: words test/refit/final/v2020 in string constants (docstrings and the
    constants of ALLOWED_NAMES aside), `sealed` outside SEALED, a comparison with 'B' or `!= 'A'`, a date after
    2019-11-13, read_parquet/read_csv outside the readers, exp._read/read_day outside read_days, exp.run/metrics/
    compare, M.load/M.DAYS, M.days with a split other than a literal train/val, forbidden imports."""
    tree = ast.parse(src)
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            docs.add(id(n.body[0].value))
    func = {}
    for f in ast.walk(tree):
        if isinstance(f, ast.FunctionDef):
            for n in ast.walk(f):
                func.setdefault(id(n), f.name)
    allowed, sealed_ok = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and \
                n.targets[0].id in ALLOWED_NAMES:
            allowed |= {id(c) for c in ast.walk(n.value) if isinstance(c, ast.Constant)}
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and \
                getattr(n.targets[0], 'id', None) in ('SEALED', 'DEVIATIONS'):
            sealed_ok |= {id(c) for c in ast.walk(n.value) if isinstance(c, ast.Constant)}
    bad = []
    for n in ast.walk(tree):
        line = getattr(n, 'lineno', 0)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            v = n.value.lower()
            if n.value == 'B':
                bad.append(f"constant 'B' line {line}")
            if LATE_DAY.search(v):
                bad.append(f'a day after 2019-11-13 line {line}')
            if WORD.search(v) and id(n) not in allowed:
                bad.append(f'word {WORD.search(v).group(1)!r} line {line}')
            if SEALED_PART in v and id(n) not in sealed_ok:
                bad.append(f'{SEALED_PART} line {line}')
            if ('read_parquet' in v or 'read_csv' in v) and func.get(id(n)) not in READERS:
                bad.append(f'a file read in SQL outside the readers, line {line}')
        if isinstance(n, ast.Compare):
            consts = [c for c in [n.left, *n.comparators] if isinstance(c, ast.Constant)]
            if any(c.value == 'B' for c in consts) or \
                    (any(isinstance(o, ast.NotEq) for o in n.ops) and any(c.value == 'A' for c in consts)):
                bad.append(f'half B comparison line {line}')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'date' and len(n.args) == 3 \
                and all(isinstance(a, ast.Constant) for a in n.args):
            y, m, d = (a.value for a in n.args)
            if (y, m, d) > (2019, 11, 13):
                bad.append(f'date {y}-{m}-{d} line {line}')
        if isinstance(n, ast.Attribute):
            if n.attr in ('read_parquet', 'read_csv') and func.get(id(n)) not in READERS:
                bad.append(f'.{n.attr} outside the readers, line {line}')
            if isinstance(n.value, ast.Name):
                if n.value.id == 'exp' and n.attr in ('_read', 'read_day') and func.get(id(n)) != 'read_days':
                    bad.append(f'exp.{n.attr} outside read_days, line {line}')
                if n.value.id == 'exp' and n.attr in ('run', 'metrics', 'compare', 'main'):
                    bad.append(f'exp.{n.attr} line {line}')
                if n.value.id == 'M' and n.attr in ('load', 'main', 'DAYS'):
                    bad.append(f'M.{n.attr} line {line}')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'days' and \
                isinstance(n.func.value, ast.Name) and n.func.value.id == 'M':
            a = n.args[0] if n.args else None
            if not (isinstance(a, ast.Constant) and a.value in T.SPLITS_OK) and \
                    func.get(id(n)) not in ('read_days', 'guard_days'):
                bad.append(f'M.days with a split that is not a literal train/val, line {line}')
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module or ''] + [f'{n.module}.{a.name}' for a in n.names]
            bad += [f'import {m}' for m in mods if m.startswith(FORBIDDEN_IMPORTS)]
    return bad


class Ast(unittest.TestCase):
    def test_module_reads_nothing_forbidden(self):
        self.assertEqual(violations(MODULE.read_text(encoding='utf-8')), [])

    def test_each_forbidden_snippet_is_caught(self):
        snippets = {
            'word': "p = DAYS6 / ('ref' 'it')\nq = 'te' + 'st'\n",
            'word_in_fstring': "def f(x):\n    return f'{x}/final.json'\n",
            'v2020': "ART = 'artifacts/task1/v2020/days6'\n",
            'half_b': "def f(df):\n    return df[df.half == 'B']\n",
            'not_a': "def f(df):\n    return df[df.half != 'A']\n",
            'isin_b': "def f(df):\n    return df[df.half.isin(['B'])]\n",
            'half_b_const': "HALF_B = 'B'\n",
            'late_ts': "T0 = pd.Timestamp('2019-11-20')\n",
            'dec': "T0 = '2019-12-01'\n",
            'y2020': "def f(x):\n    return f'{x}/2020-02-14.parquet'\n",
            'allow_needs_one_target': "COMMITTED = X = 'v2020'\n",
            'late_date': "D = date(2019, 11, 18)\n",
            'parquet_attr': "def f():\n    return duckdb.read_parquet('x.parquet')\n",
            'parquet_sql': "def f():\n    return duckdb.sql(\"SELECT * FROM read_parquet('x')\")\n",
            'read_day': "def f(d, p):\n    return exp.read_day(d, p)\n",
            'days_split': "def f(s):\n    return M.days(s)\n",
            'sealed': "P = 'a/" + SEALED_PART + "/b'\n",
            'import': "from task1 import placebo\n",
        }
        for k, src in snippets.items():
            with self.subTest(k):
                self.assertNotEqual(violations(src), [], k)
        self.assertEqual(violations("COMMITTED = ('council/tests/test_side_task1.py', 'x/v2020')\n"), [])
        self.assertEqual(violations("def metrics_a(p):\n    return duckdb.sql(f\"SELECT * FROM read_parquet('{p}') "
                                    "WHERE half = 'A'\")\n"), [])
        self.assertEqual(violations("D = date(2019, 11, 13)\n"), [])
        self.assertEqual(violations("T0 = pd.Timestamp('2019-11-13')\nT1 = '2019-10-15'\n"), [])


# ---------------------------------------------------------------- decision flow with fake fits and differences

class Flow(unittest.TestCase):
    """run_h9 / run_h11 with fit_one recorded and boot answering from a table (no data)."""

    def ctx(self, h):
        root = tmp_root()
        return T.Ctx(h, T.make_out(h, root / 'art', root / 'runs'), check_fn=lambda: None)

    def fake(self, table):
        fits = []

        def fit_one(ctx, name, over, **kw):
            fits.append((name, over))

        def boot(ctx, ref, new):
            key = (tuple(ref) if isinstance(ref, list) else ref, tuple(new) if isinstance(new, list) else new)
            d, lo, hi = table.get(key, table.get(new if isinstance(new, str) else tuple(new), (0.0, -1.0, 1.0)))
            return {'ref': ref, 'new': new, 'd': d, 'ci': [lo, hi], 'queries': 10}
        return fits, fit_one, boot

    def test_h9_d10_wins_and_stage3_reuses_grid_d10(self):
        table = {'h9_rsm05_s0': (0.0009, -0.001, 0.002), 'h9_d10_s0': (0.002, 0.001, 0.003),
                 'h9_l2_3_s0': (0.002, 0.001, 0.003),  # equal d: d10 (number 3) ranks above l2 3 (number 4)
                 'h9_d10_s1': (0.001, 0.0, 0.002), ('h9_d10_s0', 'h9_d10_s1'): (0.0015, 0.0002, 0.003),
                 'h9_l2_3_s1': (0.001, 0.0, 0.002), ('h9_l2_3_s0', 'h9_l2_3_s1'): (0.0014, 0.0002, 0.003)}
        fits, fit_one, boot = self.fake(table)
        with mock.patch.object(T, 'fit_one', fit_one), mock.patch.object(T, 'boot', boot), \
                mock.patch.object(T, 'require_reused', lambda ctx, names: {n: 'ok' for n in names}):
            res = T.run_h9(self.ctx('h9'))
        names = [n for n, _ in fits]
        self.assertEqual(names[:5], [f'{a}_s0' for a, _ in T.H9_ARMS])
        self.assertEqual(names[5:7], ['h9_d10_s1', 'h9_l2_3_s1'])  # two passing arms, rsm05 third by d
        self.assertEqual(res['W'], 'h9_d10')
        self.assertIn('недонастроен', res['verdict'])
        self.assertEqual(names[7:], ['h9_H_d10_s1'])  # seed 0 of H with depth 10 is grid_d10_s0
        self.assertEqual(res['stage3']['H_W'], ['grid_d10_s0', 'h9_H_d10_s1'])
        self.assertEqual(dict(fits)['h9_H_d10_s1'], T.H | T.SEEDS[1] | {'depth': 10})
        self.assertEqual(dict(fits)['h9_rsm05_s0'], T.HP | T.SEEDS[0] | {'rsm': 0.5})

    def test_h9_nobody_passes(self):
        fits, fit_one, boot = self.fake({})
        with mock.patch.object(T, 'fit_one', fit_one), mock.patch.object(T, 'boot', boot):
            res = T.run_h9(self.ctx('h9'))
        self.assertEqual(len(fits), 5)
        self.assertIn('без выигрыша', res['verdict'])

    def test_h9_one_seed_negative_is_no_gain(self):
        table = {'h9_rsm05_s0': (0.002, 0.001, 0.003), 'h9_rsm05_s1': (-0.0001, -0.001, 0.001),
                 ('h9_rsm05_s0', 'h9_rsm05_s1'): (0.001, 0.0001, 0.002)}
        fits, fit_one, boot = self.fake(table)
        with mock.patch.object(T, 'fit_one', fit_one), mock.patch.object(T, 'boot', boot):
            res = T.run_h9(self.ctx('h9'))
        self.assertIn('без выигрыша', res['verdict'])
        self.assertEqual(len(fits), 6)

    def test_h11_acceptance_chain(self):
        # round 2 passes on both seeds, round 4 passes on seed 0 only
        table = {'h11_g2_s0': (0.002, 0.001, 0.003), 'h11_g2_s1': (0.001, 0.0002, 0.002),
                 'h11_g4_s0': (0.002, 0.001, 0.003), 'h11_g4_s1': (0.0004, 0.0001, 0.001)}
        fits, fit_one, boot = self.fake(table)
        with mock.patch.object(T, 'fit_one', fit_one), mock.patch.object(T, 'boot', boot):
            res = T.run_h11(self.ctx('h11'))
        over = dict(fits)
        self.assertEqual([n for n, _ in fits], ['h11_step_s1', 'h11_g1_s0', 'h11_g2_s0', 'h11_g2_s1', 'h11_g3_s0',
                                                'h11_g4_s0', 'h11_g4_s1', 'h11_g5_s0', 'h11_g6_s0'])
        self.assertEqual(over['h11_g3_s0']['extra'], T.ROUNDS[2] + T.ROUNDS[3])
        self.assertEqual(over['h11_g6_s0']['extra'], T.ROUNDS[2] + T.ROUNDS[6])
        self.assertEqual(over['h11_step_s1'], T.R6BASE | T.SEEDS[1])
        self.assertEqual(res['accepted'], 1)
        self.assertEqual(res['G_star']['fits'], ['h11_g2_s0', 'h11_g2_s1'])
        self.assertEqual([r['accepted'] for r in res['rounds']], [False, True, False, False, False, False])


# ---------------------------------------------------------------- run(): lock, refusals

class RunGuards(unittest.TestCase):
    """run() with a fake step body: what happens around it (no data)."""

    def ctx(self, h, root=None, **kw):
        root = root or tmp_root()
        (root / 'prot').mkdir(exist_ok=True)
        return root, T.Ctx(h, T.make_out(h, root / 'art', root / 'runs'), check_fn=kw.pop('check_fn', lambda: None),
                           heavy_kw={'lock_path': root / 'heavy.lock', 'procs_fn': lambda: []}, wait=False,
                           snapshot_roots={root / 'prot': 'incident'}, **kw)

    @contextlib.contextmanager
    def fake(self, body=lambda ctx: {'verdict': 'x'}):
        with mock.patch.dict(T.STEPS, {h: body for h in T.STEPS}), mock.patch.object(T, 'check_grid_order', dict), \
                mock.patch.object(T, 'require_reused', lambda ctx, names: {}), \
                mock.patch.object(T, 'path_passed', lambda ctx: True):
            yield

    def test_snapshots_are_taken_under_the_lock(self):
        root, ctx = self.ctx('h9')
        held = []
        real = T.snapshot

        def snap(roots):
            held.append((root / 'heavy.lock').read_text() if (root / 'heavy.lock').exists() else '')
            return real(roots)
        with self.fake(), mock.patch.object(T, 'snapshot', snap):
            res = T.run(ctx)
        self.assertEqual(len(held), 2)
        self.assertTrue(all('"side h9"' in x for x in held), held)
        self.assertEqual(res['deviations'], T.DEVIATIONS)
        self.assertEqual(json.loads((root / 'runs' / 'h9-result.json').read_text())['deviations'], T.DEVIATIONS)

    def test_incident_refuses(self):
        root, ctx = self.ctx('h9')

        def body(ctx):
            (root / 'prot' / 'new.txt').write_text('x')
            return {'verdict': 'x'}
        with self.fake(body), self.assertRaises(SystemExit) as e:
            T.run(ctx)
        self.assertEqual(e.exception.code, S.PROTECTED_EXIT)
        self.assertEqual(json.loads((root / 'runs' / 'h9-result.json').read_text())['status'], 'refused')

    def test_busy_from_check_2019_stops_the_run(self):
        from council.xfer import queue as Q
        busy = lambda: T.check_2019([(1, 0, '.venv/bin/python -m task1.placebo run q.json')], own={99})
        root, ctx = self.ctx('h10', check_fn=busy)
        with self.fake(), self.assertRaises(Q.Busy):
            T.run(ctx)
        self.assertFalse((root / 'runs' / 'h10-result.json').exists())
        for cmd in ('python -m task1.build x', 'python -m task1.final', 'python -m task1.leakcheck'):
            with self.assertRaises(Q.Busy):
                T.check_2019([(1, 0, cmd)], own={99})

    def test_committed_refuses_dirty(self):
        def git(*args):
            return ' M council/side/task1_side.py\n' if args[0] == 'status' else 'abc\n'
        with mock.patch.object(T, 'git', git), self.assertRaises(SystemExit) as e:
            T.committed()
        self.assertIn('task1_side.py', str(e.exception))
        with mock.patch.object(T, 'git', lambda *a: '' if a[0] == 'status' else 'abc\n'):
            self.assertEqual(T.committed(), 'abc')

    def test_large_groups_need_the_main_h11(self):
        root, ctx = self.ctx('h11', groups=10)
        with self.fake(), self.assertRaises(SystemExit):
            T.run(ctx)
        ctx.out.write_json({'status': 'refused'}, 'h11-result.json', runs=True)
        with self.fake(), self.assertRaises(SystemExit):
            T.run(ctx)
        ctx.out.write_json({'status': 'ok'}, 'h11-result.json', runs=True)
        with self.fake():
            self.assertEqual(T.run(ctx)['status'], 'ok')
        self.assertTrue((root / 'runs' / 'h11-L10-result.json').exists())

    def test_counts_wait_at_the_light_gate(self):
        root, ctx = self.ctx('h10')
        gates = []
        with mock.patch.object(S, 'light_gate_wait', lambda *a, **k: gates.append(a[0])), \
                mock.patch.object(T, 'check_grid_order', dict), mock.patch.object(duckdb, 'sql') as sql:
            sql.return_value.fetchone.return_value = (7,)
            d = T.dry(ctx, counts=True)
        self.assertEqual(d['counts']['q_full'], 7)
        self.assertEqual(len(gates), 3)
        self.assertEqual(d['deviations'], T.DEVIATIONS)


# ---------------------------------------------------------------- end to end on the synthetic stand

class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = Stand.get()
        with cls.st.patched():
            ctx = cls.st.ctx('path')
            cls.path_result = T.run(ctx)

    def written(self):
        root = self.st.root
        skip = ('days/', 'extra/', 'ref/', 'refcwd/')
        rel = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()]
        return sorted(r for r in rel if not r.startswith(skip))

    def test_path_repeats_exp_run(self):
        r = self.path_result
        self.assertTrue(r['passed'], r['points'])
        self.assertEqual(r['status'], 'ok')
        for p in r['points'].values():
            self.assertTrue(p['same_queries'])
            self.assertEqual(set(p['max_abs'].values()), {0.0})
        recs = [json.loads(x) for x in (self.st.root / 'art' / 't1-path' / 'runs.jsonl').read_text().splitlines()]
        self.assertEqual({r['name'] for r in recs}, set(T.PATH_POINTS))
        for rec in recs:
            self.assertIn('peak_rss_gb', rec)
            self.assertEqual(rec['code'], T.code_stamp())
            self.assertTrue((self.st.root / 'art' / 't1-path' / rec['model']).exists())

    def test_rerun_skips_and_other_config_stops(self):
        with self.st.patched():
            ctx = self.st.ctx('path')
            n0 = len((self.st.root / 'art' / 't1-path' / 'runs.jsonl').read_text().splitlines())
            T.fit_one(ctx, 'side_path_H_s0', T.H | T.SEEDS[0])
            n1 = len((self.st.root / 'art' / 't1-path' / 'runs.jsonl').read_text().splitlines())
            self.assertEqual(n0, n1)
            with self.assertRaises(SystemExit):
                T.fit_one(ctx, 'side_path_H_s0', T.H | T.SEEDS[1])

    def test_h9_h10_h11_and_dry(self):
        held = []
        with self.st.patched():
            for h, kw in (('h9', {}), ('h10', {}), ('h11', {}), ('h11', {'groups': 15})):
                ctx = self.st.ctx(h, **kw)
                fn = ctx.check_fn
                ctx.check_fn = lambda: held.append(Path(self.st.root / 'heavy.lock').read_text()) or fn()
                res = T.run(ctx)
                self.assertEqual(res['status'], 'ok', res)
                self.assertIn('verdict', res)
                d = T.dry(self.st.ctx(h, **kw), counts=True)
                self.assertTrue(d['dry'])
                self.assertTrue(all(v == 'ok' for v in d['reused'].values()), d['reused'])
                if h == 'h10':
                    self.assertEqual(d['counts']['q_full'], res['H']['scan']['q_full'])
                    self.assertEqual(d['counts']['q_sub'], res['H']['scan']['q_sub'])
        self.assertTrue(held and all('side h' in x for x in held))
        h9 = json.loads((self.st.root / 'runs' / 'h9-result.json').read_text())
        self.assertEqual([r['arm'] for r in h9['stage1']], [a for a, _ in T.H9_ARMS])
        h10 = json.loads((self.st.root / 'runs' / 'h10-result.json').read_text())
        for arm in ('H', 'Hp'):
            self.assertEqual(sorted(map(int, h10[arm]['curve'])), [50, 100, 150])
        scan = json.loads((self.st.root / 'art' / 'h10' / 'scan-h10_H_scan_s0.json').read_text())
        self.assertLess(scan['q_sub'], scan['q_full'])
        h11 = json.loads((self.st.root / 'runs' / 'h11-result.json').read_text())
        self.assertEqual(len(h11['rounds']), 6)
        self.assertTrue((self.st.root / 'runs' / 'h11-L15-result.json').exists())
        for w in self.written():
            self.assertTrue(w.startswith(('art/t1-path/', 'art/h9/', 'art/h10/', 'art/h11/', 'runs/', 'heavy.lock',
                                          'prot/')), w)
        for w in self.written():
            if w.startswith('runs/'):
                self.assertTrue(w in ('runs/queue.jsonl', 'runs/t1-path-result.json', 'runs/h9-result.json',
                                      'runs/h10-result.json', 'runs/h11-result.json', 'runs/h11-L15-result.json'), w)
        for h in ('h9', 'h10', 'h11'):
            for line in (self.st.root / 'art' / h / 'runs.jsonl').read_text().splitlines():
                rec = json.loads(line)
                self.assertTrue(rec['name'].startswith(T.PREFIX[h]))
                self.assertIn('peak_rss_gb', rec)
                self.assertEqual(rec['code'], T.code_stamp())

    def test_needs_passed_path_with_same_code(self):
        with self.st.patched():
            ctx = self.st.ctx('h9')
            ctx.stamp = {'other': 'code'}
            with self.assertRaises(SystemExit):
                T.run(ctx)


if __name__ == '__main__':
    unittest.main()
