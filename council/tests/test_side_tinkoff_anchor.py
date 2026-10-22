"""council.side (shared guard) and council.side.tinkoff_anchor (H8) on synthetic data; no real data is read.

Checks: the AST guard of the side package (no broker, C_val/C_test, holdout, val/test/kaggle collections, label files,
sealed, connect(<path>) without read_only=True);
Out refuses paths outside its roots and inside artifacts/xfer, artifacts/task1; the snapshot names a change;
heavy_step takes a temporary lock and refuses next to a foreign heavy process; H8: the anchor split, the group
contrast and the decision on synthetic per-user NDCG, run() with fake fits writes only under the temporary roots and
exits 3 when a protected tree changes during the run.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_side_tinkoff_anchor -v
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from council import side as S
from council.side import tinkoff_anchor as H8
from council.xfer import queue as Q

ROOT = Path(__file__).resolve().parents[2]
MODULES = {m: ROOT / 'council' / 'side' / f'{m}.py' for m in ('__init__', 'tinkoff_anchor', 'proxy', 'coverage')}
FORBIDDEN_NAMES = {'y_select', 'c_val', 'c_test', 'broker', 'holdout', 'read_test', 'start_test', 'final_labels',
                   'read_sealed', 'current_holdout_collection', 'score_chunked', 'sealed', 'reveal'}
FORBIDDEN_IMPORTS = ('council.broker', 'council.xfer.broker', 'council.plan', 'council.xfer.plan', 'council.reveal',
                     'task1.leakcheck')
FORBIDDEN_EXACT = {'kaggle', 'holdout', 'test', 'val', 'refit', 'C_val', 'C_test', 'final'}
FORBIDDEN_SUBSTRINGS = ('holdout', 'kaggle-', 'val-', 'test-', 'c_val', 'c_test', 'labels.parquet', 'targets.parquet',
                        'sealed')
ALLOWED_SPANS = {'S0', 'T_fit'}
# legal strings that hold a forbidden substring: (module, exact string) -> why
ALLOWLIST = {('__init__', 'sealed'): 'SKIP_DIR: protected_snapshot lists a closed directory and does not enter it'}


def tmp_root() -> Path:
    return Path(tempfile.mkdtemp(dir='/tmp', prefix='tlab-side-'))


def docstrings(tree) -> set:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                out.add(id(b.value))
    return out


def violations(path: Path) -> list:
    """What the side module may not touch: names, imports and string constants (docstrings aside)."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    docs = docstrings(tree)
    parent = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id.lower() in FORBIDDEN_NAMES:
            bad.append(f'name {n.id}')
        elif isinstance(n, ast.Attribute) and n.attr.lower() in FORBIDDEN_NAMES:
            bad.append(f'attribute {n.attr}')
        elif isinstance(n, ast.arg) and n.arg.lower() in FORBIDDEN_NAMES:
            bad.append(f'argument {n.arg}')
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module or ''] + [f'{n.module}.{a.name}' for a in n.names]
            bad += [f'import {m}' for m in mods if any(m == f or m.startswith(f + '.') for f in FORBIDDEN_IMPORTS)]
            if isinstance(n, ast.ImportFrom):
                bad += [f'import {a.name}' for a in n.names if a.name.lower() in FORBIDDEN_NAMES]
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            v, p = n.value, parent.get(id(n))
            guard = isinstance(p, ast.Compare) and p.left is n and all(isinstance(o, ast.In) for o in p.ops)
            hit = [f for f in FORBIDDEN_SUBSTRINGS if f in v.lower()]
            if hit and not guard and (path.stem, v) not in ALLOWLIST:
                bad.append(f'string {v!r} ({", ".join(hit)})')
            if v in FORBIDDEN_EXACT:
                bad.append(f'string {v!r}')
            if v == 'S0' and not (isinstance(p, ast.Call) and isinstance(p.func, ast.Attribute)
                                  and p.func.attr == 'days'):
                bad.append("string 'S0' outside roles.days()")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'days' and n.args:
            a = n.args[0]
            if isinstance(a, ast.Constant) and a.value not in ALLOWED_SPANS:
                bad.append(f'roles.days({a.value!r})')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                n.func.attr in ('collection', 'check_collection', 'collections'):
            role_args = [a for a in n.args if isinstance(a, (ast.Name, ast.Constant))]
            if not any(isinstance(a, ast.Name) and a.id == 'ROLE' for a in role_args):
                bad.append(f'{n.func.attr}() without ROLE')
        if isinstance(n, ast.Call) and (isinstance(n.func, ast.Name) and n.func.id == 'connect' or
                                        isinstance(n.func, ast.Attribute) and n.func.attr == 'connect'):
            ro = [kw for kw in n.keywords if kw.arg == 'read_only']
            ro_true = bool(ro) and all(isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in ro)
            if ro and not ro_true:
                bad.append('connect(read_only=not True)')
            elif n.args and not ro_true:
                bad.append('connect(<path>) without read_only=True')
    return bad


class Guard(unittest.TestCase):
    def test_no_forbidden_reads(self):
        for name, path in MODULES.items():
            with self.subTest(module=name):
                self.assertEqual(violations(path), [])

    def test_guard_catches(self):
        p = tmp_root() / 'bad.py'
        p.write_text('from council.xfer import broker\nimport council.plan\n'
                     "def f(ctx, roles):\n    ctx.collection('holdout', 671)\n    broker.y_select(1)\n"
                     "    roles.days('val')\n    x = 'artifacts/task1/v2020/sealed/a'\n"
                     "    y = 'artifacts/xfer/tinkoff/collections/holdout-671'\n"
                     "    xc.output_dir('tinkoff', 'collections', 'val-641')\n"
                     "    duckdb.connect('artifacts/xfer/tinkoff/load/static.duckdb')\n"
                     "    duckdb.connect('a.duckdb', read_only=False)\n    return c_test\n",
                     encoding='utf-8')
        bad = violations(p)
        for frag in ('import council.plan', 'import broker', 'attribute y_select', "string 'holdout'",
                     "roles.days('val')", 'collection() without ROLE', 'name c_test',
                     "string 'artifacts/task1/v2020/sealed/a'", "string 'artifacts/xfer/tinkoff/collections/holdout-671'",
                     "string 'val-641'", 'connect(<path>) without read_only=True', 'connect(read_only=not True)'):
            self.assertTrue(any(frag in b for b in bad), (frag, bad))

    def test_role_is_train(self):
        self.assertEqual(H8.ROLE, 'train')

    def test_allowlist_is_used(self):
        """Every allowlisted string still exists where it is allowed (no stale exceptions)."""
        for (module, value) in ALLOWLIST:
            tree = ast.parse(MODULES[module].read_text(encoding='utf-8'))
            self.assertIn(value, {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)})

    def test_only_import_of_protected_code(self):
        """The side package imports the frozen modules; it is not one of them and writes none of them."""
        for path in MODULES.values():
            src = path.read_text(encoding='utf-8')
            for frozen in ('council/xfer/', 'council/design.py', 'council/fit.py', 'council/roles.py',
                           'council/plan.py', 'scripts/', 'task1/'):
                self.assertNotIn(f"open('{frozen}", src)


class Outputs(unittest.TestCase):
    def setUp(self):
        self.root = tmp_root()
        self.out = S.Out('x', self.root / 'art', self.root / 'runs')

    def test_paths(self):
        self.assertEqual(self.out.path('a.json'), self.root / 'art' / 'x' / 'a.json')
        self.assertEqual(self.out.path('a.json', runs=True), self.root / 'runs' / 'a.json')
        with self.assertRaises(S.Refused):
            self.out.path('..', '..', 'escape.json')
        with self.assertRaises(S.Refused):
            S.Out('x', ROOT / 'artifacts' / 'xfer', self.root / 'runs')
        with self.assertRaises(S.Refused):
            S.Out('x', Path('/tmp/tlab-a/../../etc'), self.root / 'runs')
        with self.assertRaises(S.Refused):
            S.Out('../x', self.root / 'art', self.root / 'runs')
        default = S.Out('x')
        self.assertEqual(default.art, ROOT / 'artifacts' / 'side' / 'x')
        self.assertEqual(default.runs, ROOT / 'council' / 'runs' / 'side')
        for prot in S.PROTECTED:
            self.assertFalse(S.inside(default.art, prot))
            self.assertFalse(S.inside(default.runs, prot))

    def test_writes(self):
        import pandas as pd
        p = self.out.write_json({'a': 1}, 'r.json', runs=True)
        self.assertEqual(json.loads(p.read_text()), {'a': 1})
        f = self.out.write_frame(pd.DataFrame({'a': [1, 2]}), 'f.parquet')
        import duckdb
        self.assertEqual(duckdb.connect().execute(f"SELECT sum(a) FROM read_parquet('{f}')").fetchone()[0], 3)

    def test_snapshot(self):
        prot = self.root / 'prot'
        (prot / 'd').mkdir(parents=True)
        (prot / 'd' / 'f').write_text('1')
        before = S.protected_snapshot([prot])
        self.assertTrue(S.protected_verdict(before, [prot])['unchanged'])
        (prot / 'd' / 'g').write_text('2')
        v = S.protected_verdict(before, [prot])
        self.assertFalse(v['unchanged'])
        self.assertTrue(any(x.endswith('/g') for x in v['first']))
        before = S.protected_snapshot([prot])
        os.utime(prot / 'd' / 'f', ns=(1, 1))
        self.assertFalse(S.protected_verdict(before, [prot])['unchanged'])

    def test_snapshot_does_not_enter_sealed(self):
        prot = self.root / 'prot2'
        (prot / 'x' / 'sealed').mkdir(parents=True)
        (prot / 'x' / 'sealed' / 'labels.parquet').write_text('1')
        snap = S.protected_snapshot([prot])
        self.assertIn(str(prot / 'x' / 'sealed'), snap)
        self.assertEqual(snap[str(prot / 'x' / 'sealed')][0], 'dir')
        self.assertFalse(any('/sealed/' in k for k in snap), snap)


class Heavy(unittest.TestCase):
    def setUp(self):
        self.root = tmp_root()
        self.out = S.Out('x', self.root / 'art', self.root / 'runs')
        self.lock = self.root / 'heavy.lock'

    def test_lock_and_journal(self):
        with S.heavy_step('x', 'tinkoff', self.out, lock_path=self.lock, procs_fn=lambda: []):
            holder = Q.lock_holder(self.lock)
            self.assertEqual(holder['what'], 'side x')
        self.assertIsNone(Q.lock_holder(self.lock))
        events = [json.loads(x)['event'] for x in self.out.journal.read_text().splitlines()]
        self.assertIn('start', events)
        self.assertIn('end', events)

    def test_busy_next_to_foreign(self):
        foreign = [(4242, 1, f'{sys.executable} -m council.fit --plan')]
        with self.assertRaises(Q.Busy):
            with S.heavy_step('x', 'rees46-2020', self.out, wait=False, lock_path=self.lock,
                              procs_fn=lambda: foreign):
                pass
        with self.assertRaises(Q.Busy):
            S.check(foreign, own=set())


def users_ndcg(n, shift, seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    return {u: float(np.clip(0.3 + shift + rng.normal(0, 0.05), 0, 1)) for u in range(n)}


class Tinkoff(unittest.TestCase):
    def test_split(self):
        self.assertEqual(H8.split_anchors((461, 491, 521, 551, 581, 611), 611), [461, 491, 521, 551, 581])
        with self.assertRaises(S.Refused):
            H8.split_anchors((461, 491, 521), 641)
        with self.assertRaises(S.Refused):
            H8.split_anchors((461, 611), 611)

    def test_contrast_and_decision(self):
        n = 400
        kaggle = set(range(200))
        b = users_ndcg(n, 0, 1)
        ba = {u: v + (0.0 if u in kaggle else 0.05) for u, v in b.items()}
        c = H8.group_contrast(b, ba, kaggle, draws=300)
        self.assertGreater(c['D_rest_minus_D_kaggle']['ci'][0], 0)
        self.assertEqual(H8.decide({2026: c, 2027: c}), 'reproduced')
        ba2 = {u: v + (0.05 if u in kaggle else 0.0) for u, v in b.items()}
        c2 = H8.group_contrast(b, ba2, kaggle, draws=300)
        self.assertEqual(H8.decide({2026: c2, 2027: c2}), 'reversed')
        self.assertEqual(H8.decide({2026: c, 2027: c2}), 'not distinguished')

    def spec(self):
        return {'format': H8.FORMAT, 'seeds': [2026, 2027], 'arms': list(H8.ARMS), 'eval_anchor': 611,
                'training_anchors': [461, 491, 521, 551, 581]}

    def fake_fit(self, arm, seed, out, s):
        shift = 0.03 if arm == 'BA' else 0.0
        return {u: v + (shift if u >= 150 else 0.0) for u, v in users_ndcg(300, 0, seed).items()}

    def test_run_writes_only_side(self):
        root = tmp_root()
        out = S.Out(H8.NAME, root / 'art', root / 'runs')
        prot = root / 'prot'
        prot.mkdir()
        (prot / 'f').write_text('x')
        calls = []
        res = H8.run(out, self.spec(), fit_eval_fn=self.fake_fit, users_fn=lambda: set(range(150)),
                     check_fn=lambda: calls.append(1), wait=False,
                     heavy_kw={'lock_path': root / 'heavy.lock', 'procs_fn': lambda: []},
                     protected=[prot], draws=200)
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(len(calls), 4)
        self.assertEqual(res['decision'], 'reproduced')
        written = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
        self.assertIn(f'runs/{H8.NAME}.json', written)
        self.assertTrue(all(w.startswith(('runs/', 'prot/', 'art/', 'heavy.lock')) for w in written), written)

    def test_writes_while_waiting_are_not_a_change(self):
        """A REES46 step that writes while H8 waits for it is before the snapshot: no refusal."""
        root = tmp_root()
        out = S.Out(H8.NAME, root / 'art', root / 'runs')
        prot = root / 'prot'
        prot.mkdir()
        calls = []

        def procs():
            calls.append(1)
            if len(calls) == 1:
                (prot / 'fits.jsonl').write_text('x')
                return [(4242, 1, 'python -m council.queue c_val')]
            return []
        res = H8.run(out, self.spec(), fit_eval_fn=self.fake_fit, users_fn=lambda: set(range(150)),
                     check_fn=lambda: None, wait=True,
                     heavy_kw={'lock_path': root / 'heavy.lock', 'procs_fn': procs, 'sleep': lambda _: None},
                     protected=[prot], draws=100)
        self.assertEqual(res['status'], 'ok')
        self.assertGreater(len(calls), 1)

    def test_run_refuses_on_protected_change(self):
        root = tmp_root()
        out = S.Out(H8.NAME, root / 'art', root / 'runs')
        prot = root / 'prot'
        prot.mkdir()

        def touching(arm, seed, o, s):
            (prot / f'{arm}{seed}').write_text('x')
            return self.fake_fit(arm, seed, o, s)
        with self.assertRaises(SystemExit) as e:
            H8.run(out, self.spec(), fit_eval_fn=touching, users_fn=lambda: set(range(150)), check_fn=lambda: None,
                   wait=False, heavy_kw={'lock_path': root / 'heavy.lock', 'procs_fn': lambda: []},
                   protected=[prot], draws=100)
        self.assertEqual(e.exception.code, S.PROTECTED_EXIT)
        self.assertEqual(json.loads((root / 'runs' / f'{H8.NAME}.json').read_text())['status'], 'refused')


DRY_HOOK = '''
import runpy, sys
ROOT = sys.argv[1]
BANNED = tuple(ROOT + p for p in ('/artifacts/', '/data/'))
def hook(event, args):
    if event == 'open' and isinstance(args[0], str) and args[0].startswith(BANNED):
        raise PermissionError('dry opened ' + args[0])
sys.addaudithook(hook)
sys.argv = [sys.argv[2], '--dry']
runpy.run_path(sys.argv[0], run_name='__main__')
'''


def run_dry(module: str):
    """`<module> --dry` in a fresh `python -I` with an audit hook that refuses open() under artifacts/ and data/.
    (DuckDB opens files natively, outside the hook; the modules open no database in --dry.)"""
    return subprocess.run([sys.executable, '-I', '-c', DRY_HOOK, str(ROOT), str(MODULES[module])],
                          capture_output=True, text=True, cwd=ROOT, env={**os.environ, 'TASK1_PERIOD': '2020'},
                          timeout=120)


class Dry(unittest.TestCase):
    def test_hook_refuses(self):
        r = subprocess.run([sys.executable, '-I', '-c', DRY_HOOK.replace("runpy.run_path(sys.argv[0], run_name='__main__')",
                            "open(ROOT + '/artifacts/x.json')"), str(ROOT), 'x'], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('dry opened', r.stderr)

    def test_dry_reads_nothing(self):
        """--dry with open() under artifacts/ and data/ refused by an audit hook: only the spec is printed."""
        r = run_dry('tinkoff_anchor')
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(d['dry'])
        self.assertEqual(d['spec']['eval_anchor'], 611)


if __name__ == '__main__':
    unittest.main()
