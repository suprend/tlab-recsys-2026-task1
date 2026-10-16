"""CLI-boundary CODE tests with actual orchestration/helper and fake ML/data I/O.

NumPy numerics are allowed. No actual CatBoost/DuckDB import, fit or data read.
These tests do not establish native fit/serialization or accepted-data lineage.
"""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import train_development as cli

ROOT = Path(__file__).resolve().parents[1]


def definitions(relative, names, namespace):
    body = [node for node in ast.parse((ROOT/relative).read_bytes()).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    if {node.name for node in body} != set(names):
        raise AssertionError('Expected exact source definition set')
    exec(compile(ast.Module(body=body, type_ignores=[]), '<actual-source-definitions>', 'exec'), namespace)


class FakePool:
    def __init__(self, x, **kwargs):
        assert set(kwargs) == {'label', 'weight', 'feature_names', 'thread_count'}
        assert kwargs['thread_count'] == 2
        self.feature_names = kwargs['feature_names']


class FakeClassifier:
    counts = None
    fail_fit = fail_save = bad_reload = False

    def __init__(self, **parameters):
        self.parameters = parameters
        self.tree_count_ = 0
        self.feature_names_ = []

    def get_params(self): return deepcopy(self.parameters)
    def get_all_params(self): return deepcopy(self.parameters)
    def is_fitted(self): return self.tree_count_ > 0
    def get_cat_feature_indices(self): return []
    def get_text_feature_indices(self): return []
    def get_embedding_feature_indices(self): return []

    def fit(self, pool, **kwargs):
        type(self).counts['fit'] += 1
        assert set(kwargs) == {'callbacks'} and len(kwargs['callbacks']) == 1
        if self.fail_fit:
            raise RuntimeError('invented native fit failure')
        assert kwargs['callbacks'][0].after_iteration(None)
        self.tree_count_ = self.parameters['iterations']
        self.feature_names_ = list(pool.feature_names)
        return self

    def copy(self): return deepcopy(self)

    def shrink(self, count, ntree_start=0):
        assert ntree_start == 0
        type(self).counts['shrink'] += 1
        self.tree_count_ = count

    def save_model(self, path):
        type(self).counts['save'] += 1
        if self.fail_save:
            raise OSError('invented save failure')
        Path(path).write_text(json.dumps(dict(parameters=self.parameters, trees=self.tree_count_,
                                             features=self.feature_names_)))

    def load_model(self, path):
        type(self).counts['load'] += 1
        body = json.loads(Path(path).read_text())
        self.parameters, self.feature_names_ = body['parameters'], body['features']
        self.tree_count_ = body['trees'] + int(self.bad_reload)

    def predict(self, x, **kwargs):
        import numpy as np
        type(self).counts['predict'] += 1
        assert set(kwargs) == {'prediction_type', 'ntree_start', 'ntree_end', 'thread_count'}
        assert kwargs['prediction_type'] == 'RawFormulaVal' and kwargs['ntree_start'] == 0
        assert kwargs['thread_count'] == 2
        return np.arange(len(x), dtype=np.float64) + (kwargs['ntree_end'] or self.tree_count_)


class DevelopmentCLI(unittest.TestCase):
    def setUp(self):
        import numpy as np
        import scripts
        from scripts.ranking_metrics import QueryRanking
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.np = np
        b = ModuleType('scripts.train_baselines')
        b.__dict__.update(np=np, dataclass=dataclass, Path=Path, QueryRanking=QueryRanking,
                          utc=lambda value: datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc))
        definitions('scripts/train_baselines.py',
                    {'Prepared', 'group_accounting', '_BudgetCallback', 'validate_training_phases', 'rankings'}, b.__dict__)
        b.canonical_json = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        definitions('scripts/development_collection.py', {'_atomic_json'}, b.__dict__)
        b.sha256_file = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        b._local = lambda name: self.root/name
        b.CODE = ('uv.lock',)
        for name in set(b.CODE) | set(cli.CODE) | {'train.json', 'validation.json'}:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('invented pinned input '+name)
        self.b = b
        shared = dict(base_protocol='invented-protocol.json', feature_registry='invented-registry.json',
                      final_holdout_start='2019-10-26T00:00:00Z',
                      model_timing=dict(fit_data_cutoff='2019-10-21T00:00:00Z', available_at='2019-10-22T00:00:00Z'))
        self.collections = {}
        for role, filename in (('train', 'train.json'), ('selection', 'validation.json')):
            phase = dict(deepcopy(shared), role=role, label_available_before='2019-10-21T00:00:00Z',
                         range=dict(start='2019-10-08T00:00:00Z' if role == 'train' else '2019-10-22T00:00:00Z'))
            self.collections[filename] = dict(phase=phase, feature_columns=['invented_numeric'],
                pins={filename: b.sha256_file(self.root/filename)},
                plan=dict(collection_id=role+'-invented', identity=dict(source_sha256='a'*64,
                          registry_sha256='b'*64, shard_protocols=[dict.fromkeys(
                              ('source', 'query', 'target', 'candidates', 'history'), 'invented-shared-policy')])))
        def prepared(queries, groups, items, labels):
            return b.Prepared(queries, np.asarray(groups, dtype=np.int32), np.asarray(items, dtype=np.int64),
                              np.arange(len(items), dtype=np.float32).reshape(-1, 1),
                              np.asarray(labels, dtype=np.int8), ['invented_numeric'])
        self.train = prepared([('train-q', 'invented-u', None, frozenset({1}))], [0, 0], [1, 2], [1, 0])
        self.validation = prepared([('mixed', 'u1', None, frozenset({1})),
                                   ('off-C', 'u2', None, frozenset({99})),
                                   ('empty-C', 'u3', None, frozenset({77})),
                                   ('negative', 'u4', None, frozenset())], [0, 0, 1, 3], [1, 2, 3, 4], [1, 0, 0, 0])
        self.preparations, self.selections, self.choices = [], [], [2]
        self.on_select = lambda: None
        def verify(path, *, check):
            check()
            return deepcopy(self.collections[Path(path).name])
        def prepare(collection, *, max_queries, max_rows, check):
            check()
            self.preparations.append((collection['phase']['role'], max_queries, max_rows))
            return self.train if collection['phase']['role'] == 'train' else self.validation
        b.verify_collection, b.prepare_dataset = verify, prepare
        b.environment_snapshot = lambda: dict(backend='fake ML; actual NumPy', numpy=np.__version__)
        selector = ModuleType('scripts.adaptive_tree_selection')
        def select(model, validation, *, maximum, check):
            self.assertIs(validation, self.validation)
            self.assertEqual(maximum, 5)
            self.selections.append(validation)
            check(); self.on_select()
            best = self.choices.pop(0)
            curve = [0.1]*maximum
            curve[best-1] = 0.8
            return best, curve, dict(fullY_positive_queries=3, candidate_rows=3)
        selector.select_best_tree = select
        cb = ModuleType('catboost')
        cb.CatBoostClassifier, cb.Pool = FakeClassifier, FakePool
        helper = ModuleType('development_cli_actual_helper_under_test')
        self.addCleanup(sys.modules.pop, helper.__name__, None)
        sys.modules[helper.__name__] = helper
        exec(compile((ROOT/'scripts/development_training.py').read_bytes(), '<actual-development-helper>', 'exec'), helper.__dict__)
        self.helper_calls = []
        def fit(*args, **kwargs):
            self.helper_calls.append(args)
            return helper.fit_development(*args, **kwargs)
        self.runtime = SimpleNamespace(np=np, b=b, Classifier=FakeClassifier, fit=fit)
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'catboost': cb, 'scripts.train_baselines': b,
                                 'scripts.adaptive_tree_selection': selector}).start()
        patch.object(scripts, 'train_baselines', b, create=True).start()
        patch.object(scripts, 'adaptive_tree_selection', selector, create=True).start()
        patch.object(cli, 'load_runtime', return_value=self.runtime).start()
        FakeClassifier.counts = dict(fit=0, shrink=0, save=0, load=0, predict=0)
        FakeClassifier.fail_fit = FakeClassifier.fail_save = FakeClassifier.bad_reload = False

    def argv(self, name='output'):
        return ['--train-acceptance', str(self.root/'train.json'), '--validation-acceptance', str(self.root/'validation.json'),
                '--output', str(self.root/name), '--max-iterations', '5', '--train-query-cap', '1',
                '--max-matrix-rows', '100', '--depth', '2', '--learning-rate', '.1', '--l2-leaf-reg', '3',
                '--random-seed', '7', '--cpu-seconds', '10', '--wall-seconds', '20', '--rss-bytes', str(2**30)]

    def call(self, name='output'):
        with redirect_stdout(io.StringIO()):
            return cli.main(self.argv(name))

    def failed_report(self, name):
        report = json.loads((self.root/name/'report.json').read_text())
        self.assertEqual(report['status'], 'failed')
        return report

    def test_independent_calls_select_separately_and_save_reload_without_refit(self):
        self.choices = [2, 4]
        first, second = self.call('first'), self.call('second')
        self.assertEqual((first['selected_trees'], second['selected_trees']), (2, 4))
        self.assertEqual((first['trained_ceiling'], second['trained_ceiling']), (5, 5))
        self.assertEqual(len(self.helper_calls), 2)
        self.assertEqual(FakeClassifier.counts, dict(fit=2, shrink=2, save=4, load=2, predict=6))
        for name, best in (('first', 2), ('second', 4)):
            out = self.root/name
            self.assertEqual(json.loads((out/'full.cbm').read_text())['trees'], 5)
            self.assertEqual(json.loads((out/'selected.cbm').read_text())['trees'], best)
            report = json.loads((out/'report.json').read_text())
            self.assertEqual(report['status'], 'complete_produced_unreviewed')
            self.assertEqual(len(report['validation_curve']), 5)
            self.assertEqual(report['score_parity']['reloaded_max_abs_difference'], 0)
            self.assertEqual(report['constructor_parameters']['thread_count'], 2)
            self.assertFalse(report['constructor_parameters']['use_best_model'])
            with self.np.load(out/'validation-scores.npz') as scores:
                self.np.testing.assert_array_equal(scores['product_id'], self.validation.items)
                self.np.testing.assert_array_equal(scores['full_prefix_raw_score'], scores['reloaded_raw_score'])

    def test_validation_and_ceiling_are_required_parser_arguments(self):
        for flag in ('--validation-acceptance', '--max-iterations'):
            argv = self.argv()
            index = argv.index(flag)
            del argv[index:index+2]
            with self.subTest(flag=flag), redirect_stdout(io.StringIO()), patch('sys.stderr', new=io.StringIO()):
                with self.assertRaises(SystemExit): cli.main(argv)
        self.assertFalse((self.root/'output').exists())
        self.assertEqual(FakeClassifier.counts['fit'], 0)

    def test_validation_is_uncapped_and_keeps_off_candidate_and_empty_candidate_queries(self):
        result = self.call()
        self.assertEqual(self.preparations, [('train', 1, 100), ('selection', None, 100)])
        self.assertEqual(len(self.selections[0].queries), 4)
        self.assertEqual([q[3] for q in self.selections[0].queries],
                         [frozenset({1}), frozenset({99}), frozenset({77}), frozenset()])
        self.assertEqual(result['validation_population']['empty_candidate_groups'], 1)
        self.assertEqual(result['validation_support']['fullY_positive_queries'], 3)

    def test_chronology_failure_precedes_preparation_and_fit(self):
        self.collections['validation.json']['phase']['range']['start'] = '2019-10-21T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'availability/maturity'): self.call()
        self.assertEqual(self.preparations, [])
        self.assertEqual(self.helper_calls, [])
        self.assertEqual(FakeClassifier.counts['fit'], 0)
        self.failed_report('output')

    def test_fit_or_save_failure_never_retries_or_reports_complete(self):
        for attr, name, exception in (('fail_fit', 'fit-failed', RuntimeError), ('fail_save', 'save-failed', OSError)):
            with self.subTest(stage=attr):
                FakeClassifier.counts['fit'] = 0
                setattr(FakeClassifier, attr, True)
                with self.assertRaises(exception): self.call(name)
                setattr(FakeClassifier, attr, False)
                self.assertEqual(FakeClassifier.counts['fit'], 1)
                self.failed_report(name)
                self.choices = [2]

    def test_reload_mismatch_prevents_complete_without_another_fit(self):
        FakeClassifier.bad_reload = True
        with self.assertRaisesRegex(ValueError, 'Reloaded selected'): self.call()
        self.assertEqual(FakeClassifier.counts['fit'], 1)
        self.failed_report('output')

    def test_primary_fit_exception_survives_secondary_failure_telemetry_or_formatting(self):
        class UnprintableError(RuntimeError):
            def __str__(self):
                raise OSError('invented exception formatting failure')
        actual_observation = cli.Budget.observation
        for mode in ('observation', 'formatting'):
            with self.subTest(mode=mode):
                primary = (UnprintableError('invented fit failure') if mode == 'formatting'
                           else RuntimeError('invented fit failure'))
                armed = False
                def observation(budget):
                    if armed and mode == 'observation':
                        raise OSError('invented failure telemetry error')
                    return actual_observation(budget)
                def failed_fit(instance, pool, **kwargs):
                    nonlocal armed
                    FakeClassifier.counts['fit'] += 1
                    armed = True
                    raise primary
                FakeClassifier.counts['fit'] = 0
                before = len(self.helper_calls)
                with patch.object(cli.Budget, 'observation', observation), patch.object(FakeClassifier, 'fit', failed_fit):
                    with self.assertRaises(RuntimeError) as caught:
                        self.call('secondary-'+mode)
                self.assertIs(caught.exception, primary)
                self.assertEqual(FakeClassifier.counts['fit'], 1)
                self.assertEqual(len(self.helper_calls)-before, 1)
                self.assertTrue(any('Failure telemetry also failed' in note for note in primary.__notes__))
                report = self.failed_report('secondary-'+mode)
                self.assertEqual(report['error_type'], type(primary).__name__)
                self.assertNotIn('selected_trees', report)
                self.assertFalse((self.root/('secondary-'+mode)/'selected.cbm').exists())

    def test_input_mutation_during_fit_prevents_complete_without_refit(self):
        self.on_select = lambda: (self.root/'train.json').write_text('mutated invented acceptance')
        with self.assertRaisesRegex(ValueError, 'Input changed'): self.call()
        self.assertEqual(FakeClassifier.counts['fit'], 1)
        self.failed_report('output')

    def test_near_equal_scores_with_changed_ranking_are_rejected_without_refit(self):
        full = self.np.zeros(len(self.validation.group), dtype=self.np.float64)
        changed = full.copy()
        changed[:2] = [-5e-13, 5e-13]
        self.assertLessEqual(float(self.np.max(self.np.abs(changed-full))), 1e-12)
        self.assertEqual(self.b.rankings(self.validation, full)[0].ranked_items, (1, 2))
        self.assertEqual(self.b.rankings(self.validation, changed)[0].ranked_items, (2, 1))
        self.assertEqual(self.validation.queries[0][3], frozenset({1}))
        def predict(instance, x, **kwargs):
            FakeClassifier.counts['predict'] += 1
            self.assertEqual(kwargs['thread_count'], 2)
            return full if kwargs['ntree_end'] else changed
        with patch.object(FakeClassifier, 'predict', predict):
            with self.assertRaisesRegex(ValueError, 'rankings differ'):
                self.call('near-tie')
        self.assertEqual(FakeClassifier.counts['fit'], 1)
        self.assertEqual(len(self.helper_calls), 1)
        self.assertEqual(FakeClassifier.counts['predict'], 3)
        self.failed_report('near-tie')

    def test_input_mutation_by_final_report_writer_is_rejected_without_refit(self):
        actual_write = self.b._atomic_json
        mutations = []
        def write(path, body):
            actual_write(path, body)
            if Path(path).name == 'report.json' and body['status'] == 'complete_produced_unreviewed':
                (self.root/'train.json').write_text('invented terminal-writer mutation')
                mutations.append(True)
        with patch.object(self.b, '_atomic_json', write):
            with self.assertRaisesRegex(ValueError, 'Input changed'):
                self.call('writer-mutation')
        self.assertEqual(mutations, [True])
        self.assertEqual(FakeClassifier.counts['fit'], 1)
        self.assertEqual(len(self.helper_calls), 1)
        self.failed_report('writer-mutation')

    def test_existing_or_dangling_output_is_preserved_before_backend_load(self):
        existing = self.root/'existing'
        existing.mkdir(); (existing/'keep').write_text('keep')
        (self.root/'alias').symlink_to(self.root/'absent', target_is_directory=True)
        for name in ('existing', 'alias'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Existing output'):
                self.call(name)
        cli.load_runtime.assert_not_called()
        self.assertEqual((existing/'keep').read_text(), 'keep')
        self.assertFalse((self.root/'absent').exists())

    def test_default_cli_source_import_has_no_backend_or_filesystem_effect(self):
        import builtins
        imports = []
        actual_import = builtins.__import__
        def tracked(name, *args, **kwargs):
            imports.append(name)
            return actual_import(name, *args, **kwargs)
        raw = (ROOT/'scripts/train_development.py').read_bytes()
        with patch('builtins.__import__', side_effect=tracked), patch('pathlib.Path.mkdir', side_effect=AssertionError('import mkdir')):
            exec(compile(raw, '<CLI-import-only>', 'exec'), {'__name__': 'development_cli_import_only'})
        self.assertFalse(any(name.split('.')[0] in {'catboost', 'duckdb', 'numpy'} for name in imports))
        self.assertEqual(FakeClassifier.counts['fit'], 0)


if __name__ == '__main__':
    unittest.main()
