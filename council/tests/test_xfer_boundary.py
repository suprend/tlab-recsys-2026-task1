"""The label boundary of the council on xfer (council/runs/xfer/contract.md §3 «Тест границы»).

Scope: every council/xfer/**/*.py, found at test time. Exemptions are relative paths from the repository root
(council/xfer/broker.py, council/xfer/fit.py, council/xfer/roles.py), never file names. Names and string literals
are compared case-insensitively; docstrings are documentation and are not checked (as in the REES46 test).

  1. Everywhere except broker.py: no name or string containing an evaluation word (EVAL_WORDS); no string with a
     REES46 word (label, n_targets, ndcg, recall) and no name label*, n_targets*, *ndcg*, *recall*.
  2. fit.py may use names label*; a string with 'label', the string 'weight' and the attributes .label/.weight
     only on a frame rooted at a name assigned from a training_block call (the training labels, as REES46
     fit.py). The evaluation words stay banned there (rule 1).
  3. training_block: only in fit.py. write_sealed, holdout_command, prepare_probe, output_dir: nowhere.
  4. Imports of scripts.*: xfer_common and xfer_agent anywhere (the adapter only through xc), xfer_model only in
     fit.py and broker.py and only as `from scripts import xfer_model as xm`. There every use of xm is an
     attribute from a white list (XM_FIT, XM_BROKER; xm.fit and xm.holdout nowhere, contract §8.1). Elsewhere
     the names xm and xfer_model are banned, attributes included (fit.xm..., scripts.xfer_model). A string
     naming xfer_model or sys.modules (or the string 'modules'), importlib, __import__, any attribute .modules
     and sys other than as sys.<attribute>: nowhere.
  5. 'holdout' (names and string substrings): free in fit.py and broker.py; in roles.py only inside the dict
     literals of the module-level assignments SERIES and COLLECTION_ROLES; nowhere else.
  6. No path under artifacts/xfer: no string with artifacts/xfer, no 'artifacts' / 'xfer' chain (constants,
     Path('artifacts') / 'xfer', joinpath chains), no Path('artifacts', 'xfer') arguments; in every module.
  7. Outside broker.py no name or string containing metric, map@ or gate.json; report.json only in fit.py and
     broker.py (contract §8.2, §10.8).
  8. fit.py does not import the broker: no name broker there, in imports or attributes (contract §10.4; the
     test.started marker is read through council.xfer.marker).

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_boundary -v
"""
import ast
import re
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / 'council' / 'xfer'
BROKER = 'council/xfer/broker.py'
FIT = 'council/xfer/fit.py'
ROLES = 'council/xfer/roles.py'
XFER_MODEL_IMPORTERS = {FIT, BROKER}
HOLDOUT_FREE = {FIT, BROKER}
HOLDOUT_DICTS = ('SERIES', 'COLLECTION_ROLES')

EVAL_WORDS = ('open_labels', 'final_labels', 'label_files', 'sealed_files', 'targets', 'query_targets',
              'query_users', 'evaluate', 'metric_of', 'per_query', 'read_sealed', 'labels.parquet',
              'targets.parquet', 'sealed')
REES46_WORDS = ('label', 'n_targets', 'ndcg', 'recall')
REES46_NAME = re.compile(r'^(label\w*|n_targets\w*|\w*ndcg\w*|\w*recall\w*)$', re.I)
LABEL_NAME = re.compile(r'^label\w*$', re.I)
TRAINING_BLOCK = 'training_block'
NOWHERE = ('write_sealed', 'holdout_command', 'prepare_probe', 'output_dir')
DYNAMIC = ('importlib', '__import__')
XFER_MODEL = 'scripts.xfer_model'
HOLDOUT = 'holdout'
TRAINING_COLUMNS = ('label', 'weight')
XFER_PATH = re.compile(r'artifacts[/\\]+xfer([/\\]|$)', re.I)
XM = 'xm'
XM_FIT = frozenset({'Context', 'connect', 'training_block', 'frame_rows', 'with_agent', 'matrices', 'make_pool',
                    'predict', 'recipe_for', 'fit_dir', 'KEYS', 'check_sidecar_rows', 'rows_digest',
                    'keys_digest'})
XM_BROKER = XM_FIT | {'open_labels', 'final_labels', 'evaluate', 'top_k', 'read_scores', 'read_metrics'}
XM_ALLOWED = {FIT: XM_FIT, BROKER: XM_BROKER}
SCRIPTS_ANYWHERE = ('xfer_common', 'xfer_agent')
BROKER_ONLY = ('metric', 'map@', 'gate.json')
REPORT_WORDS = ('report.json',)
REPORT_ALLOWED = {FIT, BROKER}
NOT_IN_FIT = 'broker'


def docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def identifiers(node):
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Attribute):
        yield node.attr
    elif isinstance(node, ast.arg):
        yield node.arg
    elif isinstance(node, ast.keyword) and node.arg:
        yield node.arg
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name
    elif isinstance(node, ast.alias):
        yield node.name
        yield from node.name.split('.')
        if node.asname:
            yield node.asname
    elif isinstance(node, ast.ImportFrom) and node.module:
        yield node.module
        yield from node.module.split('.')
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        yield from node.names


def strings(tree, docs):
    """(node, text) of every str/bytes constant outside docstrings, f-string parts included."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and id(node) not in docs:
            v = node.value
            yield node, (v.decode('utf-8', 'replace') if isinstance(v, bytes) else v)


def parents(tree):
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def root_name(node):
    """The Name a chain of attributes, subscripts and calls starts from, or None."""
    while True:
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            return node.id if isinstance(node, ast.Name) else None


def callee(node):
    f = node.func if isinstance(node, ast.Call) else None
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def block_names(tree):
    """Names assigned from a training_block(...) call anywhere in the module (tuple targets included)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call) \
                and (callee(node.value) or '').lower() == TRAINING_BLOCK:
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out.add(n.id)
    return out


def from_block(node, up, blocks):
    """True if a string constant is (inside a tuple/list of) the key of a subscript of a frame rooted at a
    training_block name."""
    child, p = node, up.get(id(node))
    while isinstance(p, (ast.Tuple, ast.List, ast.Set)):
        child, p = p, up.get(id(p))
    return isinstance(p, ast.Subscript) and p.slice is child and root_name(p.value) in blocks


def holdout_dict_constants(tree):
    """ids of the constants inside the dict values of module-level SERIES = {...} and COLLECTION_ROLES = {...}."""
    out = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id in HOLDOUT_DICTS:
            out |= {id(n) for n in ast.walk(node.value) if isinstance(n, ast.Constant)}
    return out


def _is(node, text):
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip('/\\').lower() == text


def _ends(node, text):
    """A path expression whose last segment is `text`: 'text', '.../text', x / 'text', Path(..., 'text'),
    x.joinpath(..., 'text')."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        node = node.right
    if isinstance(node, ast.Call) and node.args:
        node = node.args[-1]
    return isinstance(node, ast.Constant) and isinstance(node.value, str) \
        and re.split(r'[/\\]+', node.value.strip('/\\').lower())[-1] == text


def _starts(node, text):
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        node = node.left
    if isinstance(node, ast.Call) and node.args and isinstance(node.func, ast.Name):
        node = node.args[0]
    return isinstance(node, ast.Constant) and isinstance(node.value, str) \
        and re.split(r'[/\\]+', node.value.strip('/\\').lower())[0] == text


def scripts_imports(node, relpath):
    """Breaches of rule 4 by one import statement."""
    out = []
    allowed = set(SCRIPTS_ANYWHERE)
    if isinstance(node, ast.Import):
        for a in node.names:
            if a.name == 'scripts' or a.name.startswith('scripts.'):
                mod = a.name.split('.')[1] if '.' in a.name else ''
                if mod not in allowed or mod == '':
                    out.append(f'imports {a.name}')
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        parts = node.module.split('.')
        if parts[0] == 'scripts':
            if len(parts) > 1:
                if parts[1] not in allowed:
                    out.append(f'imports from {node.module}')
            else:
                for a in node.names:
                    if a.name == 'xfer_model' and relpath in XM_ALLOWED and a.asname == XM:
                        continue
                    if a.name not in allowed:
                        out.append(f'from scripts import {a.name}' + (f' as {a.asname}' if a.asname else ''))
    return out


def violations(source, relpath):
    """The breaches of the xfer boundary in one module, as 'line: what' strings; relpath is the module's path
    relative to the repository root (posix), which decides the exemptions."""
    tree = ast.parse(source, relpath)
    docs = docstrings(tree)
    up = parents(tree)
    broker, fit, roles = relpath == BROKER, relpath == FIT, relpath == ROLES
    blocks = block_names(tree) if fit else set()
    allowed_holdout = holdout_dict_constants(tree) if roles else set()
    out = []

    for node, text in strings(tree, docs):
        line, low = node.lineno, text.lower()
        if not broker:
            out += [f'{line}: string mentions {w!r}' for w in EVAL_WORDS if w in low]
            for w in REES46_WORDS:
                if w in low and not (fit and w == 'label' and from_block(node, up, blocks)):
                    out.append(f'{line}: string mentions {w!r}')
        if fit and low == 'weight' and not from_block(node, up, blocks):
            out.append(f"{line}: column 'weight' not taken from the training_block result")
        if not fit and TRAINING_BLOCK in low:
            out.append(f'{line}: string names {TRAINING_BLOCK}')
        out += [f'{line}: string names {w}' for w in NOWHERE if w in low]
        out += [f'{line}: string names {w}' for w in DYNAMIC if w in low]
        if 'xfer_model' in low:
            out.append(f'{line}: string names xfer_model')
        if 'sys.modules' in low or low == 'modules':
            out.append(f'{line}: string names sys.modules')
        if not broker:
            out += [f'{line}: string mentions {w!r}' for w in BROKER_ONLY if w in low]
        if relpath not in REPORT_ALLOWED:
            out += [f'{line}: string mentions {w!r}' for w in REPORT_WORDS if w in low]
        if HOLDOUT in low and relpath not in HOLDOUT_FREE and id(node) not in allowed_holdout:
            out.append(f'{line}: string mentions {HOLDOUT!r}')
        if XFER_PATH.search(text):
            out.append(f'{line}: string builds a path under artifacts/xfer')

    for node in ast.walk(tree):
        line = getattr(node, 'lineno', 0)
        for name in identifiers(node):
            low = name.lower()
            if not broker:
                out += [f'{line}: name {name} contains {w!r}' for w in EVAL_WORDS if w in low]
                if REES46_NAME.match(name) and not (fit and LABEL_NAME.match(name)):
                    out.append(f'{line}: name {name}')
            if not fit and TRAINING_BLOCK in low:
                out.append(f'{line}: name {name}')
            out += [f'{line}: name {name}' for w in NOWHERE + DYNAMIC if w in low]
            if HOLDOUT in low and relpath not in HOLDOUT_FREE:
                out.append(f'{line}: name {name} contains {HOLDOUT!r}')
            if not broker:
                out += [f'{line}: name {name} contains {w!r}' for w in BROKER_ONLY if w in low]
            if relpath not in XM_ALLOWED and (low == XM or 'xfer_model' in low):
                out.append(f'{line}: name {name}')
            if fit and low == NOT_IN_FIT:
                out.append(f'{line}: fit.py names the broker')
        if fit and isinstance(node, ast.Attribute) and node.attr.lower() in TRAINING_COLUMNS \
                and root_name(node.value) not in blocks:
            out.append(f'{line}: .{node.attr} not taken from the training_block result')
        if isinstance(node, ast.Attribute) and node.attr.lower() == 'modules':
            out.append(f'{line}: attribute .modules')
        if isinstance(node, ast.Name) and node.id == 'sys' and not (
                isinstance(up.get(id(node)), ast.Attribute) and up[id(node)].value is node):
            out.append(f'{line}: sys used other than as sys.<attribute>')
        if isinstance(node, ast.ImportFrom) and node.module == 'sys' and any(a.name == 'modules' for a in node.names):
            out.append(f'{line}: from sys import modules')
        out += [f'{line}: {x}' for x in scripts_imports(node, relpath)]
        if relpath in XM_ALLOWED and isinstance(node, ast.Name) and node.id == XM:
            p = up.get(id(node))
            if not (isinstance(p, ast.Attribute) and p.value is node):
                out.append(f'{line}: xm used other than as xm.<attribute>')
            elif p.attr not in XM_ALLOWED[relpath]:
                out.append(f'{line}: xm.{p.attr} is not on the white list of {relpath}')
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and _ends(node.left, 'artifacts') \
                and _starts(node.right, 'xfer'):
            out.append(f"{line}: 'artifacts' / 'xfer' path")
        if isinstance(node, ast.Call):
            args = node.args
            out += [f"{line}: path arguments 'artifacts', 'xfer'" for a, b in zip(args, args[1:])
                    if _ends(a, 'artifacts') and _starts(b, 'xfer')]
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == 'joinpath' and args and _ends(f.value, 'artifacts') \
                    and _starts(args[0], 'xfer'):
                out.append(f"{line}: joinpath 'artifacts' -> 'xfer'")
    return sorted(set(out), key=lambda x: (int(x.split(':')[0]), x))


def modules():
    return sorted(p for p in PKG.rglob('*.py') if '__pycache__' not in p.parts)


def rel(p):
    return p.relative_to(ROOT).as_posix()


class BoundaryTest(unittest.TestCase):
    def test_every_module_of_the_package_keeps_the_boundary(self):
        files = modules()
        names = {rel(p) for p in files}
        for must in (ROLES, FIT, BROKER, 'council/xfer/run.py', 'council/xfer/queue.py', 'council/xfer/plan.py',
                     'council/xfer/sandbox.py', 'council/xfer/compute.py', 'council/xfer/curate.py'):
            self.assertIn(must, names)
        bad = {rel(p): v for p in files if (v := violations(p.read_text(encoding='utf-8'), rel(p)))}
        self.assertEqual(bad, {}, 'modules of council/xfer cross the label boundary')

    def test_roles_names_the_test_series_only_in_its_two_dicts(self):
        tree = ast.parse((ROOT / ROLES).read_text(encoding='utf-8'))
        inside = holdout_dict_constants(tree)
        hits = [n for n, t in strings(tree, docstrings(tree)) if HOLDOUT in t.lower()]
        self.assertEqual(len(hits), 2)
        self.assertTrue(all(id(n) in inside for n in hits))

    def test_only_fit_and_broker_import_xfer_model(self):
        importers = set()
        for p in modules():
            for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
                if isinstance(node, ast.ImportFrom) and node.module == 'scripts' \
                        and any(a.name == 'xfer_model' for a in node.names):
                    importers.add(rel(p))
        self.assertEqual(importers, XFER_MODEL_IMPORTERS)


class CheckerTest(unittest.TestCase):
    """The checker catches every kind of planted breach and leaves clean code alone."""

    PLAN = 'council/xfer/plan.py'

    def v(self, code, relpath=None):
        return violations(textwrap.dedent(code), relpath or self.PLAN)

    def bad(self, code, relpath=None):
        found = self.v(code, relpath)
        self.assertTrue(found, f'not caught in {relpath or self.PLAN}: {code}')
        return found

    def good(self, code, relpath=None):
        self.assertEqual(self.v(code, relpath), [], code)

    def test_clean_code_passes(self):
        self.good('''
            """Docstrings may say open_labels, holdout, NDCG, artifacts/xfer and training_block."""
            import numpy as np
            from council import design as D
            from council.xfer import roles, broker
            def beta(y, x):
                """OLS of the per_query table from the broker."""
                return np.linalg.lstsq(x, y, rcond=None)[0]
            OUT = roles.ROOT / 'artifacts' / 'council' / 'xfer-tinkoff'
            Y = broker.y_select(ds, names)
            C = ds.collection('test')
            S = roles.SERIES['test']
            LEVEL = 'pair'
        ''')

    def test_evaluation_words(self):
        for code in ("x = 'open_labels'", 'xm.open_labels(c)', 'xm.final_labels(c)', 'def evaluate(): pass',
                     'LABEL_FILES = 1', "p = c / 'Labels.parquet'", "p = 'TARGETS.parquet'", "x = 'SEALED'",
                     'f(query_users=1)', 'from scripts.xfer_model import final_labels', 'y = targets',
                     'xa.query_targets(c)', 'metric_of(x)', 'xc.read_sealed(x, "final")', 'xc.SEALED_FILES',
                     'class Per_Query: pass', "x = f'{a}/sealed/{b}'", 'from scripts.xfer_agent import sealed'):
            self.bad(code)
            self.bad(code, FIT)
            self.good(code.replace('scripts.xfer_model', 'scripts.xfer_agent'), BROKER)

    def test_broker_only_and_fit_only_words(self):
        for code in ("x = 'metric'", 'per_metric = 1', "x = 'MAP@50'", "p = d / 'gate.json'", 'def metric(): pass',
                     'adapter.metric(x)', "p = d / 'report.json'"):
            self.bad(code)
            self.bad(code, ROLES)
        for code in ("x = 'metric'", 'adapter.metric(x)', "x = 'MAP@50'", "p = d / 'gate.json'"):
            self.bad(code, FIT)
            self.good(code, BROKER)
        self.good("p = d / 'report.json'", FIT)
        self.good("p = d / 'Report.json'", BROKER)
        self.bad("p = d / 'report.json'", 'council/xfer/marker.py')

    def test_fit_does_not_import_the_broker(self):
        for code in ('from council.xfer import broker', 'from council.xfer import roles, broker as b',
                     'import council.xfer.broker', 'from council.xfer.broker import marker',
                     'from . import broker', 'x = council.xfer.broker.marker(ds)', 'def f():\n    from council.xfer import broker'):
            self.bad(code, FIT)
            self.good(code, self.PLAN)
        self.good('from council.xfer import marker\nm = marker.marker(ds)', FIT)

    def test_exemptions_go_by_relative_path(self):
        code = "x = xm.open_labels(c)['label']"
        self.good(code, BROKER)
        for path in ('x/broker.py', 'broker.py', 'council/tests/broker.py', 'council/xfer/sub/broker.py',
                     'council/broker.py', 'council/xfer/Broker.py'):
            self.bad(code, path)
        self.bad("x = 'holdout'", 'council/fit.py')
        self.bad('from scripts import xfer_model as xm', 'tests/council/xfer/fit.py')

    def test_rees46_words(self):
        for code in ("PROMPT = 'NDCG@20'", "x = 'Recall'", 'n_targets = 1', 'def my_ndcg(): pass',
                     'label = 1', "x = b'label'", 'f(Labels=1)', 'x.recall_at', "c = 'n_targets_x'"):
            self.bad(code)
        self.good('label = 1\nlabels_n = 2', FIT)
        for code in ("x = 'n_targets'", "x = 'NDCG'", 'def recall(): pass', 'n_targets = 1'):
            self.bad(code, FIT)

    def test_fit_takes_label_and_weight_only_from_training_block(self):
        clean = '''
            from scripts import xfer_model as xm
            block, population, shares, permuted, inputs = xm.training_block(ctx, con, s, a, 'BA', seed)
            labels = block['label'].to_numpy()
            w = block['weight']
            y = block.label
            cols = block[['label', 'Weight']]
            z = block.loc[:, 'label']
            q = block.assign(x=1)['label']
        '''
        self.good(clean, FIT)
        self.bad(clean, self.PLAN)
        for code in ("frame['label']", "pd.read_parquet(p)['label']", "x = 'label'", 'other.weight',
                     "block.drop(columns=['label'])", "frame['weight']", "x = 'weight'", 'other.Label',
                     "block2['label']"):
            self.bad("block, *_ = xm.training_block(ctx, con, s, a, 'BA', seed)\n" + code, FIT)

    def test_training_block_and_nowhere_names(self):
        for code in ("xm.training_block(ctx, con, s, a, 'BA', 7)", "x = 'training_block'",
                     'from scripts.xfer_model import training_block'):
            self.bad(code)
            self.bad(code, BROKER)
        for code in ('xc.output_dir(x)', 'xm.write_sealed(x)', "x = 'holdout_command'", 'xa.prepare_probe()',
                     'def output_dir(): pass'):
            for path in (self.PLAN, FIT, BROKER, ROLES):
                self.bad(code, path)

    def test_dynamic_imports_and_xfer_model(self):
        for code in ('import importlib', "importlib.import_module('scripts.xfer_model')", "__import__('x')",
                     "sys.modules['scripts.xfer_model']", 'from sys import modules', "getattr(scripts, 'xfer_model')",
                     "x = 'scripts.xfer_model'", 'from importlib import import_module', "m = 'XFER_MODEL'",
                     'm = S.modules', "getattr(sys, 'modules')", "x = 'sys.modules'", 'v = vars(sys)["modules"]'):
            for path in (self.PLAN, FIT, BROKER):
                self.bad(code, path)
        for code in ('from scripts import xfer_model as xm', 'import scripts.xfer_model as xm',
                     'import scripts.xfer_model', 'from scripts.xfer_model import fit_dir', 'from scripts import *',
                     'x = fit.xm.training_block', 'x = scripts.xfer_model', 'xm = 1', 'def f(xm): pass',
                     'from council.xfer.fit import xm', 'y = XM.fit_dir'):
            self.bad(code)
            self.bad(code, ROLES)
        for code in ('from scripts import xfer_model as xm', 'from scripts import xfer_common as xc, xfer_model as xm',
                     'p = xm.fit_dir(d, s, "BA", 2026)', 'k = xm.KEYS'):
            self.good(code, FIT)
            self.good(code, BROKER)
        # on the broker white list by §8.1, but rule 3 (training_block only in fit.py) still holds there
        self.good('x = xm.training_block(c, n, s, a, "BA", 7)', FIT)
        self.bad('x = xm.training_block(c, n, s, a, "BA", 7)', BROKER)
        for code in ('import scripts.xfer_model as xm', 'from scripts import xfer_model', 'from scripts import xfer_model as M',
                     'from scripts.xfer_model import training_block', 'xm.fit(ctx, s, a, 7, o)', 'xm.holdout(c)',
                     'f(xm)', 'm = xm', "getattr(xm, 'fit')", 'xm.REPORT_FILE'):
            self.bad(code, FIT)
            self.bad(code, BROKER)
        for code in ('xm.open_labels(c)', 'xm.final_labels(c)', 'xm.evaluate(ctx, s, t, l)', 'xm.top_k(s, 20)',
                     'xm.read_scores(d, r)', 'xm.read_metrics(d, r)'):
            self.bad(code, FIT)
            self.good(code, BROKER)
        for code in ('k = xm.keys_digest(scores)',):
            self.good(code, FIT)
            self.good(code, BROKER)
            self.bad(code, self.PLAN)

    def test_scripts_imports(self):
        for code in ('from scripts import xfer_common as xc', 'from scripts import xfer_agent as xa',
                     'import scripts.xfer_common', 'from scripts.xfer_agent import LEVELS'):
            for path in (self.PLAN, FIT, BROKER, ROLES):
                self.good(code, path)
        for code in ('from scripts import xfer_tinkoff', 'import scripts.xfer_sber as S', 'from scripts import hm_kaggle',
                     'import scripts', 'from scripts.hm_baseline import x', 'from scripts import xfer_common, hm_agent_loop'):
            for path in (self.PLAN, FIT, BROKER, ROLES):
                self.bad(code, path)

    def test_holdout(self):
        for code in ("x = 'holdout'", 'HOLDOUT = 1', 'xc.current_holdout_collection(x, a)', "x = f'{a}_HOLDOUT'",
                     "SERIES = {'test': 'Holdout'}", 'def holdout(): pass', "p = c / 'holdout-671'"):
            self.bad(code)
            self.bad(code, 'council/xfer/run.py')
            self.good(code, FIT)
            self.good(code, BROKER)
        self.good("SERIES = {'select': 'dev', 'test': 'holdout'}\n"
                  "COLLECTION_ROLES = {'fit': 'train', 'test': 'holdout'}", ROLES)
        for code in ("X = {'test': 'holdout'}", "def f():\n    SERIES = {'test': 'holdout'}",
                     "SERIES['x'] = 'holdout'", "def f():\n    return 'holdout'",
                     "SERIES = {'test': 'holdout'}\nY = SERIES['holdout']", 'HOLDOUT = 1',
                     "SERIES: dict = {'test': 'holdout'}", "SERIES = dict(test='holdout')",
                     'xc.current_holdout_collection(x, a)'):
            self.bad(code, ROLES)

    def test_paths_under_artifacts_xfer(self):
        for code in ("P = ROOT / 'artifacts/xfer/tinkoff'", "P = ROOT / 'artifacts' / 'xfer'",
                     "P = ROOT / 'artifacts' / 'xfer' / x", "P = Path('artifacts', 'xfer')",
                     "P = 'ARTIFACTS\\\\xfer'", "P = ROOT / 'artifacts' / 'XFER/sber'", "P = f'{ROOT}/artifacts/xfer'",
                     "P = ROOT.joinpath('artifacts', 'xfer', x)", "P = ROOT / 'x/artifacts' / 'xfer'",
                     "P = Path('artifacts') / 'xfer'", "P = ROOT / Path('artifacts') / 'xfer' / x",
                     "P = ROOT.joinpath('artifacts').joinpath('xfer')", "P = ROOT.joinpath('artifacts') / 'xfer'",
                     "P = ROOT / 'artifacts' / Path('xfer')"):
            for path in (self.PLAN, FIT, BROKER, ROLES):
                self.bad(code, path)
        self.good("P = ROOT / 'artifacts' / 'council' / 'xfer-tinkoff'")
        self.good("P = ROOT / 'artifacts' / 'xfer_notes'")
        self.good("P = ROOT.joinpath('artifacts').joinpath('council')")


if __name__ == '__main__':
    unittest.main()
