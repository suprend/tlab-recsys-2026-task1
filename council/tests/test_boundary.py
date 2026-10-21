"""The label boundary of the council package (council/runs/rees46-2020/contract.md §3, deviation 1).

Except council/fit.py and council/broker.py, no module of council/ (every council/*.py, found at test time):
  - holds a string with `label`, `n_targets`, `ndcg` or `recall` (lower case, as the columns are named; docstrings are
    documentation and are not checked);
  - uses a name, attribute, argument or imported name label*, n_targets*, *ndcg*, *recall*, per_query, _read,
    read_day or FITS;
  - imports task1.exp or task1.placebo (whole or their _read, read_day, run, *) or names them in a string;
  - builds a path to the directory of fits: a string 'fits' as a path segment.
council/roles.py defines FITS and its path and is exempt from the last two FITS rules only.
council/memory.py trains (the memory trial of contract §2) and may import task1.exp and task1.placebo, nothing more of
the rules above; it never predicts.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_boundary
"""
import ast
import re
import textwrap
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
EXEMPT = {'fit.py', 'broker.py'}
TRAINS_ONLY = {'memory.py'}
TRAIN_IMPORT = re.compile(r'^\d+: from task1 import (exp|placebo)$')
DEFINES_FITS = {'roles.py'}
WORDS = ('label', 'n_targets', 'ndcg', 'recall')
NAME = re.compile(r'^(label\w*|n_targets\w*|\w*ndcg\w*|\w*recall\w*|per_query|_read|read_day)$')
FITS_NAME = 'FITS'
FITS_PATH = re.compile(r'(^|[/\\])fits([/\\]|$)')
BANNED_MODULES = ('task1.exp', 'task1.placebo')
BANNED_FROM = {'_read', 'read_day', 'run', '*'}


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
        yield node.name.split('.')[-1]
        if node.asname:
            yield node.asname
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        yield from node.names


def violations(source, filename='<module>'):
    """The breaches of the boundary in one module's source, as 'line: what' strings."""
    tree = ast.parse(source, filename)
    docs = docstrings(tree)
    fits_rules = Path(filename).name not in DEFINES_FITS
    out = []
    for node in ast.walk(tree):
        line = getattr(node, 'lineno', 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and id(node) not in docs:
            text = node.value.decode('utf-8', 'replace') if isinstance(node.value, bytes) else node.value
            out += [f'{line}: string mentions {w!r}' for w in WORDS if w in text]
            out += [f'{line}: string names {m}' for m in BANNED_MODULES if m in text]
            if fits_rules and FITS_PATH.search(text):
                out.append(f'{line}: string builds a path to the fits directory')
        for name in identifiers(node):
            if NAME.match(name):
                out.append(f'{line}: name {name}')
            if fits_rules and name == FITS_NAME:
                out.append(f'{line}: name {FITS_NAME}')
        if isinstance(node, ast.Import):
            out += [f'{line}: imports {a.name}' for a in node.names
                    if any(a.name == m or a.name.startswith(m + '.') for m in BANNED_MODULES)]
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mod = node.module
            if mod in BANNED_MODULES:
                out += [f'{line}: from {mod} import {a.name}' for a in node.names if a.name in BANNED_FROM]
                out.append(f'{line}: imports from {mod}')
            if mod == 'task1':
                out += [f'{line}: from task1 import {a.name}' for a in node.names if f'task1.{a.name}' in BANNED_MODULES]
    return sorted(set(out), key=lambda x: (int(x.split(':')[0]), x))


def modules():
    return sorted(p for p in PKG.glob('*.py') if p.name not in EXEMPT)


class BoundaryTest(unittest.TestCase):
    def test_every_council_module_keeps_the_boundary(self):
        files = modules()
        self.assertIn('roles.py', [p.name for p in files])
        bad = {p.name: v for p in files
               if (v := [x for x in violations(p.read_text(encoding='utf-8'), p.name)
                         if not (p.name in TRAINS_ONLY and TRAIN_IMPORT.match(x))])}
        self.assertEqual(bad, {}, 'modules of council/ outside fit.py and broker.py cross the label boundary')

    def test_the_exempt_modules_exist(self):
        for name in EXEMPT:
            self.assertTrue((PKG / name).exists(), name)


class CheckerTest(unittest.TestCase):
    """The checker itself catches each kind of breach and leaves clean code alone."""

    def bad(self, code, filename='design.py'):
        v = violations(textwrap.dedent(code), filename)
        self.assertTrue(v, f'not caught: {code}')
        return v

    def test_clean_code_passes(self):
        code = '''
            """Docstrings may say label, ndcg and recall."""
            import numpy as np
            from council import roles
            from task1 import extra, model as M
            def beta(y, x):
                """OLS over label-free values."""
                return np.linalg.lstsq(x, y, rcond=None)[0]
            PROMPT = "The target metric is NDCG@20."
            PATH = roles.RUNS / 'prereg-2.json'
            F = M.base_features
        '''
        self.assertEqual(violations(textwrap.dedent(code), 'design.py'), [])

    def test_strings(self):
        for s in ("'label'", "'label_purchase'", "'n_targets_purchase'", "'purchase_ndcg'", "'recall'",
                  '"SELECT label FROM t"', "f'{x}_ndcg'", "b'label'"):
            self.bad(f'x = {s}')

    def test_names_and_calls(self):
        for code in ('df.label.mean()', 'M.per_query(df, s)', 'from task1.model import per_query',
                     'x = exp._read("train", d)', 'exp.read_day(d, p)', 'def ndcg_at(k): pass',
                     'f(recall=1)', 'n_targets = 3', 'import task1.model as per_query'):
            self.bad(code)

    def test_imports_of_exp_and_placebo(self):
        for code in ('from task1 import exp', 'from task1 import placebo as P', 'import task1.exp',
                     'import task1.placebo as pl', 'from task1.exp import half', 'from task1.placebo import run',
                     'from task1.exp import *', 'importlib.import_module("task1.exp")'):
            self.bad(code)

    def test_fits(self):
        for code in ('p = roles.FITS / "a.parquet"', 'from council.roles import FITS', "p = roles.OUT / 'fits'",
                     "p = 'artifacts/task1/v2020/council/fits/runs.jsonl'"):
            self.bad(code)

    def test_roles_may_define_fits_but_not_the_rest(self):
        self.assertEqual(violations("FITS = OUT / 'fits'\n", 'roles.py'), [])
        self.bad("x = 'label'\n", 'roles.py')

    def test_the_training_module_never_predicts(self):
        for name in TRAINS_ONLY:
            text = (PKG / name).read_text(encoding='utf-8')
            self.assertTrue(any(TRAIN_IMPORT.match(x) for x in violations(text, name)), name)
            self.assertNotRegex(text, r'\bpredict\b|\.eval\b|days\(s\[.eval.\]\)')

    def test_the_real_exempt_modules_would_fail(self):
        """fit.py and broker.py read metrics; the checker would catch them, so the exemption is what lets them."""
        for name in EXEMPT:
            self.assertTrue(violations((PKG / name).read_text(encoding='utf-8'), name), name)


if __name__ == '__main__':
    unittest.main()
