import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from scripts import xfer_common as xc


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


class TempRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q')
        (self.root/'configs'/'datasets').mkdir(parents=True)
        (self.root/'artifacts'/'xfer').mkdir(parents=True)
        (self.root/'README').write_text('x')
        git(self.root, 'add', 'README')
        git(self.root, 'commit', '-q', '-m', 'init')
        self.patch = mock.patch.object(xc, 'ROOT', self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for path in self.root.rglob('*'):
            if path.is_dir():
                path.chmod(0o700)
            else:
                path.chmod(0o600)
        self.tmp.cleanup()

    def commit(self, *paths):
        git(self.root, 'add', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def write_config(self, kind, value, dataset='tinkoff', commit=True):
        path = xc.config_path(dataset, kind)
        path.write_text(json.dumps(value))
        if commit:
            self.commit(path)
        return path


class OrderAndPermutation(unittest.TestCase):
    def test_query_order_matches_duckdb(self):
        users = [0, 1, 7, 42, 11046, 123456789]
        con = duckdb.connect()
        sql = xc.QUERY_ORDER_SQL.format(column='u')
        rows = con.execute(f'SELECT u, {sql} FROM (SELECT unnest(?::BIGINT[]) AS u)', [users]).fetchall()
        for u, h in rows:
            self.assertEqual(h, xc.query_order_key(u))
            self.assertEqual(h, hashlib.sha256(f'{u}:2026'.encode()).hexdigest())

    def test_cap_queries(self):
        users = list(range(100))
        capped = xc.cap_queries(users, 10)
        self.assertEqual(len(capped), 10)
        self.assertEqual(capped, sorted(users, key=lambda u: (xc.query_order_key(u), u))[:10])
        self.assertEqual(len(xc.cap_queries(users[:5], 10)), 5)

    def test_permutation_reproducible(self):
        a = xc.permutation(2026, 641, 0, 50)
        b = xc.permutation(2026, 641, 0, 50)
        c = xc.permutation(2027, 641, 0, 50)
        self.assertTrue((a == b).all())
        self.assertFalse((a == c).all())
        expected = np.random.default_rng([20261021, 2026, 641, 0]).permutation(50)
        self.assertTrue((a == expected).all())
        self.assertEqual(xc.anchor_int('2020-09-02'), __import__('datetime').date(2020, 9, 2).toordinal())


class Reading(unittest.TestCase):
    def test_bootstrap_deterministic(self):
        rng = np.random.default_rng(1)
        ref = {u: float(rng.random()) for u in range(300)}
        alt = {u: v+0.05 for u, v in ref.items()}
        r1 = xc.bootstrap(ref, alt)
        r2 = xc.bootstrap(dict(reversed(list(ref.items()))), alt)
        self.assertEqual(r1, r2)
        self.assertAlmostEqual(r1['mean'], 0.05)
        self.assertFalse(r1['covers_zero'])

    def test_bootstrap_requires_pairs(self):
        with self.assertRaises(xc.ContractError):
            xc.bootstrap({1: 0.0}, {2: 0.0})

    def test_verdicts(self):
        self.assertTrue(xc.verdict_transfer([[0.1, 0.2], [0.01, 0.3]], 'T').startswith('колонки агента без отбора'))
        self.assertEqual(xc.verdict_transfer([[-0.2, -0.1], [-0.3, -0.01]], 'T'), 'колонки агента вредят базе')
        self.assertEqual(xc.verdict_transfer([[-0.1, 0.1], [0.0, 0.2]], 'T'), 'не различено')
        self.assertEqual(xc.verdict_transfer([[0.1, 0.2], [-0.1, 0.2]], 'T'), 'не решено')
        self.assertEqual(xc.verdict_content([[0.1, 0.2], [0.1, 0.3]]),
                         'прирост несёт содержание колонок агента, а не их число')

    def test_kaggle_reading(self):
        self.assertEqual(xc.kaggle_reading([0.30, 0.31], [0.20, 0.21]), 'BA выше B на обоих зёрнах')
        self.assertEqual(xc.kaggle_reading([0.20, 0.21], [0.30, 0.31]), 'BA ниже B')
        self.assertEqual(xc.kaggle_reading([0.20, 0.30], [0.10, 0.25]), 'не различено')
        self.assertEqual(xc.kaggle_reading([0.3, 0.3], [0.3, 0.3]), 'не различено')
        self.assertEqual(xc.kaggle_reading([0.3], [0.2, 0.2]), 'один seed — не читается')

    def test_gate_arms(self):
        self.assertEqual(xc.gate_arms(dict(B=True, BA=True, BApl=True)), ['Pop', 'B', 'BA', 'BApl'])
        self.assertEqual(xc.gate_arms(dict(B=True, BA=False, BApl=True)), ['Pop', 'B'])
        self.assertEqual(xc.gate_arms(dict(B=False, BA=True, BApl=True)), ['Pop'])


class Base(unittest.TestCase):
    def test_base_digest(self):
        base = xc.make_base('tinkoff', dict(sources=['a']), [dict(name='f', formula='x', missing='0')], [])
        xc.check_base(base, 'tinkoff')
        base['features'][0]['formula'] = 'y'
        with self.assertRaises(xc.ContractError):
            xc.check_base(base)


class Seal(TempRoot):
    def make_collection(self, role='holdout', name='holdout-671'):
        col = xc.new_output(xc.output_dir('tinkoff', 'collections', name))
        xc.write_parquet(pd.DataFrame(dict(user_id=[1], item_id=[2])), col/'frame.parquet')

        def writer(d):
            xc.write_parquet(pd.DataFrame(dict(user_id=[1], item_id=[2], label=[1])), d/'labels.parquet')
            xc.write_parquet(pd.DataFrame(dict(user_id=[1], n_targets=[1])), d/'targets.parquet')
        sealed = xc.write_sealed(col, writer)
        base = xc.make_base('tinkoff', {}, [], [])
        xc.write_manifest(col, 'tinkoff', role, 671, dict(queries=1, users=1, rows=1), base, {}, sealed=sealed)
        return col

    def test_sealed_needs_receipts(self):
        col = self.make_collection()
        self.assertEqual(oct((col/'sealed'/'labels.parquet').stat().st_mode & 0o777), '0o400')
        with self.assertRaises(xc.ContractError):
            xc.read_sealed(col, 'holdout')
        self.write_config('holdout-open', dict(x=1))
        paths = xc.read_sealed(col, 'holdout')
        self.assertTrue(paths['labels'].exists())
        with self.assertRaises(xc.ContractError):
            xc.read_sealed(col, 'final')
        self.write_config('holdout', dict(x=1))
        xc.read_sealed(col, 'final')

    def test_uncommitted_receipt_refused(self):
        col = self.make_collection()
        self.write_config('holdout-open', dict(x=1), commit=False)
        with self.assertRaises(xc.ContractError):
            xc.read_sealed(col, 'holdout')

    def test_holdout_manifest_without_label_counts(self):
        col = xc.new_output(xc.output_dir('tinkoff', 'collections', 'holdout-x'))
        xc.write_parquet(pd.DataFrame(dict(user_id=[1], item_id=[2])), col/'frame.parquet')
        with self.assertRaises(xc.ContractError):
            xc.write_manifest(col, 'tinkoff', 'holdout', 671, dict(positives=3), xc.make_base('tinkoff', {}, [], []),
                              {}, sealed={})

    def test_window(self):
        self.assertFalse(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        base = self.write_config('base', dict(b=1))
        aset = self.write_config('set', dict(s=1))
        prereg = self.write_config('prereg', dict(base_sha256=xc.sha256_file(base), set_sha256=xc.sha256_file(aset)))
        self.assertTrue(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        self.assertFalse(xc.holdout_window_open('tinkoff', 'sidecar'))
        # dirty prereg closes the window
        prereg.write_text(prereg.read_text()+' ')
        self.assertFalse(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        git(self.root, 'checkout', '--', str(prereg.relative_to(self.root)))
        self.assertTrue(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        # an existing holdout collection closes it, a committed deviation reopens it
        col = self.make_collection()
        self.assertFalse(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        self.write_config('deviations', dict(format=xc.DEVIATIONS_FORMAT, dataset='tinkoff', records=[
            dict(id='d1', step='collect-holdout', supersedes=[col.relative_to(self.root).as_posix()])]))
        self.assertTrue(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        self.assertEqual(xc.current_holdout_collection('tinkoff', 671).name, 'holdout-671-d1')
        # an open receipt closes collect-holdout for good
        self.write_config('holdout-open', dict(x=1))
        self.assertFalse(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        self.write_config('holdout', dict(x=1))
        self.assertTrue(xc.holdout_window_open('tinkoff', 'sidecar'))

    def test_window_base_mismatch(self):
        base = self.write_config('base', dict(b=1))
        aset = self.write_config('set', dict(s=1))
        self.write_config('prereg', dict(base_sha256='0'*64, set_sha256=xc.sha256_file(aset)))
        self.assertFalse(xc.holdout_window_open('tinkoff', 'collect-holdout'))
        self.assertTrue(base.exists())


class Outputs(TempRoot):
    def test_new_output_refuses_existing_and_outside(self):
        path = xc.output_dir('tinkoff', 'fits', 'B2026')
        xc.new_output(path)
        with self.assertRaises(FileExistsError):
            xc.new_output(path)
        with self.assertRaises(xc.ContractError):
            xc.new_output(self.root/'elsewhere')

    def test_atomic_json_refuses_overwrite(self):
        path = self.root/'artifacts'/'x.json'
        xc.atomic_json(path, dict(a=1))
        with self.assertRaises(xc.ContractError):
            xc.atomic_json(path, dict(a=2))


class Static(unittest.TestCase):
    def test_sealed_and_events_literals_only_in_common(self):
        import ast
        scripts = Path(xc.__file__).resolve().parent
        for path in sorted(scripts.glob('xfer_*.py')):
            if path.name == 'xfer_common.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    parts = set(node.value.replace('\\', '/').split('/'))
                    self.assertNotIn('sealed', parts, f'{path.name}: literal sealed')
                    self.assertNotIn('events.duckdb', node.value, f'{path.name}: literal events.duckdb')
                    self.assertFalse('events' in parts and '/' in node.value, f'{path.name}: events path literal')

    def test_sealed_callers(self):
        import ast
        scripts = Path(xc.__file__).resolve().parent
        allowed = {'write_sealed': {('xfer_tinkoff.py', 'collect'), ('xfer_sber.py', 'collect')},
                   'read_sealed': {('xfer_model.py', 'holdout'), ('xfer_model.py', 'final_labels')},
                   'events_path': {('xfer_tinkoff.py', 'history'), ('xfer_tinkoff.py', 'views'),
                                   ('xfer_tinkoff.py', 'load'), ('xfer_sber.py', 'history'),
                                   ('xfer_sber.py', 'views'), ('xfer_sber.py', 'load'),
                                   ('xfer_agent.py', 'sandbox')}}
        for path in sorted(scripts.glob('xfer_*.py')):
            if path.name == 'xfer_common.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                if any(func is not other and func in ast.walk(other) for other in ast.walk(tree)
                       if isinstance(other, (ast.FunctionDef, ast.AsyncFunctionDef))):
                    continue  # nested functions are judged by their top-level owner
                for node in ast.walk(func):
                    if isinstance(node, ast.Attribute) and node.attr in allowed:
                        self.assertIn((path.name, func.name), allowed[node.attr],
                                      f'{path.name}:{func.name} calls {node.attr}')


if __name__ == '__main__':
    unittest.main()
