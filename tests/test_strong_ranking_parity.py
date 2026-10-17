"""Native-free CODE regressions for actual historical strong acceptance seams.

Only selected source definitions and acceptance statements execute. No worker,
observer controller, model callback, SQL, fit or accepted-data replay is invoked.
"""
import ast
import builtins
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ORACLES = ('strong_output_audit', 'strong_recovery_audit')


def source(relative):
    return ast.parse((ROOT/relative).read_bytes(), filename=relative)


def definitions(tree, names, namespace):
    body = [node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    if {node.name for node in body} != set(names):
        raise AssertionError('Expected exact actual source definition set')
    exec(compile(ast.Module(body=body, type_ignores=[]), '<actual-parity-definitions>', 'exec'), namespace)


class StrongRankingParityTests(unittest.TestCase):
    def setUp(self):
        native_import = builtins.__import__
        def bounded_import(name, *args, **kwargs):
            if name.split('.')[0] in {'catboost', 'duckdb'}:
                raise AssertionError('Native ML/SQL imports are forbidden in parity CODE tests')
            return native_import(name, *args, **kwargs)
        self.addCleanup(patch.stopall)
        patch('builtins.__import__', side_effect=bounded_import).start()

        # Use the real producer ranking definition without importing its I/O
        # module. This stub contains no replacement ranking implementation.
        ranking = dict(__name__=__name__, np=np, dataclass=dataclass,
                       Hashable=Hashable, Iterable=Iterable, Sequence=Sequence)
        definitions(source('scripts/ranking_metrics.py'), {'QueryRanking'}, ranking)
        definitions(source('scripts/train_baselines.py'), {'rankings'}, ranking)
        scripts = ModuleType('scripts');baseline = ModuleType('scripts.train_baselines')
        baseline.rankings = ranking['rankings'];scripts.train_baselines = baseline
        patch.dict(sys.modules, {'scripts': scripts, 'scripts.train_baselines': baseline}).start()
        self.producer = {}
        self.producer_tree = source('scripts/strong_baseline.py')
        definitions(self.producer_tree, {'saved_prefix_rankings'}, self.producer)
        self.oracles = {}
        self.oracle_trees = {}
        for name in ORACLES:
            tree = source('tests/oracles/'+name+'.py');namespace = dict(hashlib=hashlib)
            definitions(tree, {'need', 'ranking_order', 'score_parity'}, namespace)
            observer = next(node for node in tree.body
                            if isinstance(node, ast.ClassDef) and node.name == 'Observer')
            # Execute the actual NPZ method only; constructors/controllers and
            # native model/predict callbacks never enter this fixture.
            methods = [node for node in observer.body
                       if isinstance(node, ast.FunctionDef) and node.name == 'npz']
            self.assertEqual(len(methods), 1)
            shell = ast.ClassDef(name='Observer', bases=[], keywords=[], body=methods,
                                 decorator_list=[])
            module = ast.fix_missing_locations(ast.Module(body=[shell], type_ignores=[]))
            exec(compile(module, '<actual-oracle-npz>', 'exec'), namespace)
            self.oracles[name] = namespace;self.oracle_trees[name] = tree

    def data(self, groups, items, *, positive=True):
        count = max(groups, default=-1)+1
        return SimpleNamespace(group=np.asarray(groups, dtype=np.int32),
            items=np.asarray(items, dtype=np.int64),
            queries=[('query'+str(g), 'user'+str(g), None,
                      frozenset({1}) if positive and g == 0 else frozenset())
                     for g in range(count)])

    def producer_route(self, data, predicted, replay, *, actual_trees=50):
        # Run the actual worker acceptance statement, with supplied vectors.
        # No fit/predict/save/load or any other worker stage can be called.
        worker = next(node for node in self.producer_tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == 'worker_main')
        statements = [node for node in ast.walk(worker)
                      if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'rows' for t in node.targets)
                      and isinstance(node.value, ast.Call)
                      and isinstance(node.value.func, ast.Attribute)
                      and node.value.func.attr == 'stage']
        self.assertEqual(len(statements), 1)
        stages = []
        def stage(name, callback):
            self.assertEqual(name, 'rank_prefix50');stages.append(name)
            return callback()
        namespace = dict(self.producer, selection=data, scores=predicted, replay=replay,
                         loaded=SimpleNamespace(tree_count_=actual_trees), k=50,
                         audit=SimpleNamespace(stage=stage))
        exec(compile(ast.Module(body=statements, type_ignores=[]), '<actual-worker-parity-route>', 'exec'), namespace)
        self.assertEqual(stages, ['rank_prefix50'])
        return namespace['rows']

    def checks(self, data, predicted, replay):
        yield 'producer worker route', lambda: self.producer_route(data, predicted, replay)
        for name in self.oracles:
            for message in ('Full300/prefix equivalence', 'Partial prefix fidelity'):
                yield name+' '+message, lambda name=name, message=message: self.oracle_route(
                    name, message, data, predicted, replay)

    def oracle_route(self, name, message, data, predicted, replay):
        # Isolate the actual successful/partial acceptance expression. Predict,
        # load, SQL and controller statements surrounding it do not execute.
        tree = self.oracle_trees[name]
        observer = next(node for node in tree.body
                        if isinstance(node, ast.ClassDef) and node.name == 'Observer')
        execute = next(node for node in observer.body
                       if isinstance(node, ast.FunctionDef) and node.name == 'execute')
        statements = [node for node in ast.walk(execute)
                      if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                      and isinstance(node.value.func, ast.Name)
                      and node.value.func.id == 'score_parity'
                      and isinstance(node.value.args[-1], ast.Constant)
                      and node.value.args[-1].value == message]
        self.assertEqual(len(statements), 1)
        namespace = dict(self.oracles[name], pred=predicted, pp=replay,
                         score=predicted, replay=replay, g=data.group, it=data.items)
        exec(compile(ast.Module(body=statements, type_ignores=[]), '<actual-oracle-parity-route>', 'exec'), namespace)

    def assert_parity(self, data, predicted, replay, *, error=None):
        predicted = np.asarray(predicted, dtype=np.float64)
        replay = np.asarray(replay, dtype=np.float64)
        for name, check in self.checks(data, predicted, replay):
            with self.subTest(route=name):
                if error:
                    with self.assertRaisesRegex(ValueError, error):check()
                else:check()

    def test_identical_and_same_order_tolerated_scores_accept(self):
        for positive in (True, False):
            data = self.data([0, 0], [1, 2], positive=positive)
            self.assert_parity(data, [5e-13, 0], [5e-13, 0])
            self.assert_parity(data, [5e-13, 0], [6e-13, 1e-13])

    def test_literal_near_tie_rank_swap_rejects_positive_and_nonpositive(self):
        for positive in (True, False):
            with self.subTest(positive=positive):
                self.assert_parity(self.data([0, 0], [1, 2], positive=positive),
                    [5e-13, 0], [0, 5e-13], error='rankings differ')

    def test_nonpositive_query_swap_cannot_hide_behind_positive_metrics(self):
        self.assert_parity(self.data([0, 0, 1, 1], [1, 2, 1, 2]),
            [1, 0, 5e-13, 0], [1, 0, 0, 5e-13], error='rankings differ')

    def test_rank_swap_after_top20_rejects(self):
        self.assert_parity(self.data([0]*22, list(range(1, 23))),
            [float(x) for x in range(20, 0, -1)]+[5e-13, 0],
            [float(x) for x in range(20, 0, -1)]+[0, 5e-13], error='rankings differ')

    def test_numeric_tolerance_shape_finiteness_and_tree_count_stay_enforced(self):
        data = self.data([0, 0], [1, 2])
        for replay in ([1+2e-12, 0], [1], [float('nan'), 0]):
            self.assert_parity(data, [1, 0], replay, error='fidelity|equivalence')
        with self.assertRaisesRegex(ValueError, 'fidelity'):
            self.producer_route(data, np.asarray([1., 0.]), np.asarray([1., 0.]), actual_trees=49)

    def test_empty_singleton_and_exact_item_id_ties_accept(self):
        for groups, items, scores in (([], [], []), ([0], [7], [0]), ([0, 0], [2, 1], [0, 0])):
            data = self.data(groups, items)
            self.assert_parity(data, scores, scores)
        data = self.data([0, 0], [2, 1]);scores = np.asarray([0., 0.])
        self.assertEqual(self.producer_route(data, scores, scores)[0].ranked_items, (1, 2))
        for namespace in self.oracles.values():
            order = namespace['ranking_order'](scores, data.group, data.items)
            self.assertEqual(tuple(data.items[order]), (1, 2))

    def test_actual_npz_method_accepts_control_rejects_score_only_rank_corruption(self):
        for positive in (True, False):
            data = self.data([0, 0], [1, 2], positive=positive)
            predicted = np.asarray([5e-13, 0])
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'synthetic-scores.npz'
                for name, namespace in self.oracles.items():
                    observer = namespace['Observer']()
                    with self.subTest(oracle=name, positive=positive):
                        np.savez_compressed(path, group=data.group, product_id=data.items, raw_score=predicted)
                        observer.npz(path, predicted, data.group, data.items)
                        np.savez_compressed(path, group=data.group, product_id=data.items, raw_score=np.asarray([0, 5e-13]))
                        with self.assertRaisesRegex(ValueError, 'Saved score replay rankings differ'):
                            observer.npz(path, predicted, data.group, data.items)

    def test_both_oracles_wire_successful_and_partial_replay_to_actual_predicate(self):
        for name, tree in self.oracle_trees.items():
            observer = next(node for node in tree.body
                            if isinstance(node, ast.ClassDef) and node.name == 'Observer')
            execute = next(node for node in observer.body
                           if isinstance(node, ast.FunctionDef) and node.name == 'execute')
            calls = [node for node in ast.walk(execute) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == 'score_parity']
            with self.subTest(oracle=name):
                self.assertEqual({ast.unparse(node) for node in calls}, {
                    "score_parity(score, replay, g, it, 'Partial prefix fidelity')",
                    "score_parity(pred, pp, g, it, 'Full300/prefix equivalence')"})


if __name__ == '__main__':unittest.main()
