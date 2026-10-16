"""Native-free development lifecycle tests; accepted selector delegation only."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]


def raw_source(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(128*1024+1)
    assert len(raw) <= 128*1024
    return raw


def actual_callback():
    raw = raw_source(REPO_ROOT/'scripts/train_baselines.py')
    body = [n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name == '_BudgetCallback']
    assert len(body) == 1
    ns = {}; exec(compile(ast.Module(body=body,type_ignores=[]),'<actual-budget-callback>','exec'),ns)
    return ns['_BudgetCallback']


class Array:
    def __init__(self, dtype, shape): self.dtype, self.shape = SimpleNamespace(name=dtype), shape
    def __len__(self): return self.shape[0]


class Prepared:
    def __init__(self):
        self.queries = [('invented-q','invented-u',None,frozenset({7}))]
        self.x = Array('float32',(2,1)); self.group = Array('int32',(2,))
        self.items = Array('int64',(2,)); self.y = Array('int8',(2,)); self.feature_names = ['invented_numeric']


class FakePool:
    def __init__(self, x, **kwargs):
        assert set(kwargs) == {'label','weight','feature_names','thread_count'} and kwargs['thread_count'] == 2
        self.feature_names = kwargs['feature_names']


class FakeClassifier:
    total_fits = 0
    def __init__(self):
        self.params = dict(iterations=5,loss_function='Logloss',task_type='CPU',thread_count=2,
                           use_best_model=False,allow_writing_files=False)
        self.tree_count_ = 0; self.feature_names_ = []; self.in_callback = False; self.short = False; self.shrinks = []
    def is_fitted(self): return self.tree_count_ > 0
    def get_params(self): return deepcopy(self.params)
    def fit(self, pool, **kwargs):
        assert set(kwargs) == {'callbacks'} and len(kwargs['callbacks']) == 1
        type(self).total_fits += 1; self.in_callback = True
        try: proceed = kwargs['callbacks'][0].after_iteration(None)
        finally: self.in_callback = False
        self.tree_count_ = 1 if not proceed else self.params['iterations']-int(self.short)
        self.feature_names_ = list(pool.feature_names); return self
    def get_cat_feature_indices(self): return []
    def get_text_feature_indices(self): return []
    def get_embedding_feature_indices(self): return []
    def copy(self): return deepcopy(self)
    def shrink(self, best, ntree_start=0):
        assert ntree_start == 0; self.shrinks.append(best); self.tree_count_ = best


author = SimpleNamespace(FakeClassifier=FakeClassifier)


class DevelopmentTrainingSeam(unittest.TestCase):
    def setUp(self):
        raw = raw_source(REPO_ROOT/'scripts/development_training.py')
        module = ModuleType('development_training_under_test')
        self.addCleanup(sys.modules.pop,module.__name__,None); sys.modules[module.__name__] = module
        exec(compile(raw,'<source-bound-development-helper>','exec'),module.__dict__)
        self.helper = module.fit_development; FakeClassifier.total_fits = 0
        self.train, self.validation = Prepared(), Prepared(); self.choices = [2]; self.selections = []
        b = ModuleType('scripts.train_baselines'); b.Prepared = Prepared; b._BudgetCallback = actual_callback()
        b.group_accounting = lambda data: ([2],[1],[1],[True],[.5,.5],{'positive_fullY_queries':1,'informative_groups':1})
        selector = ModuleType('scripts.adaptive_tree_selection')
        def select(model, validation, *, maximum, check):
            assert validation is self.validation and maximum == model.tree_count_ == 5
            self.selections.append(model); check(); best = self.choices.pop(0)
            curve = {2:[.1,.8,.4,.2,.3],4:[.1,.2,.3,.9,.4]}[best]
            return best,curve,dict(fullY_positive_queries=1,candidate_rows=2)
        selector.select_best_tree = select
        package = ModuleType('scripts'); package.train_baselines = b; package.adaptive_tree_selection = selector
        cb = ModuleType('catboost'); cb.CatBoostClassifier = FakeClassifier; cb.Pool = FakePool
        self.modules = {'catboost':cb,'scripts':package,'scripts.train_baselines':b,'scripts.adaptive_tree_selection':selector}
    def run_fit(self, model, validation='present', check=lambda:None):
        with patch.dict(sys.modules,self.modules):
            return self.helper(model,self.train,self.validation if validation == 'present' else None,max_iterations=5,check=check)
    def test_each_run_uses_its_own_selected_count(self):
        self.choices = [2,4]
        first = self.run_fit(FakeClassifier()); second = self.run_fit(FakeClassifier())
        self.assertEqual((first.selected_trees,second.selected_trees),(2,4))
        self.assertEqual((first.trained_ceiling,second.trained_ceiling),(5,5))
        self.assertEqual(FakeClassifier.total_fits,2); self.assertEqual(len(self.selections),2)
    def test_missing_validation_rejects_before_fit(self):
        with self.assertRaisesRegex(ValueError,'validation'): self.run_fit(FakeClassifier(),validation=None)
        self.assertEqual(FakeClassifier.total_fits,0); self.assertEqual(self.selections,[])
    def test_actual_callback_failure_is_preserved(self):
        model = FakeClassifier(); failure = RuntimeError('invented budget exhaustion')
        def check():
            if model.in_callback: raise failure
        with self.assertRaises(RuntimeError) as caught: self.run_fit(model,check=check)
        self.assertIs(caught.exception,failure); self.assertEqual(FakeClassifier.total_fits,1); self.assertEqual(self.selections,[])
    def test_short_fit_never_selects_or_falls_back(self):
        model = FakeClassifier(); model.short = True
        with self.assertRaisesRegex(ValueError,'entire declared'): self.run_fit(model)
        self.assertEqual(FakeClassifier.total_fits,1); self.assertEqual(self.selections,[]); self.assertEqual(model.shrinks,[])
    def test_only_copy_is_shrunk_and_original_stays_full(self):
        model = FakeClassifier(); result = self.run_fit(model)
        self.assertIs(result.full_model,model); self.assertIsNot(result.selected_model,model)
        self.assertEqual(model.tree_count_,5); self.assertEqual(model.shrinks,[])
        self.assertEqual(result.selected_model.tree_count_,2); self.assertEqual(result.selected_model.shrinks,[2])
        self.assertEqual(len(result.validation_curve),5); self.assertEqual(FakeClassifier.total_fits,1)
    def test_native_stopping_option_rejects_before_fit(self):
        model = FakeClassifier(); model.params['od_type'] = 'Iter'
        with self.assertRaisesRegex(ValueError,'Unsupported constructor'): self.run_fit(model)
        self.assertEqual(FakeClassifier.total_fits,0)

    def test_callback_error_remains_primary_when_native_fit_wraps_it(self):
        model = author.FakeClassifier()
        guard_error = RuntimeError('invented guard exhaustion')
        native_error = ValueError('invented native wrapper')

        def guard():
            if model.in_callback:
                raise guard_error

        def wrapped_fit(instance, pool, **kwargs):
            type(instance).total_fits += 1
            instance.in_callback = True
            try:
                kwargs['callbacks'][0].after_iteration(None)
            finally:
                instance.in_callback = False
            raise native_error

        with patch.object(author.FakeClassifier, 'fit', wrapped_fit):
            with self.assertRaises(RuntimeError) as caught:
                self.run_fit(model, check=guard)
        self.assertIs(caught.exception, guard_error)
        self.assertIs(caught.exception.__cause__, native_error)
        self.assertEqual(author.FakeClassifier.total_fits, 1)
        self.assertEqual(self.selections, [])

    def test_native_error_without_guard_failure_is_preserved(self):
        failure = ValueError('invented native failure')

        def failed_fit(instance, pool, **kwargs):
            type(instance).total_fits += 1
            raise failure

        with patch.object(author.FakeClassifier, 'fit', failed_fit):
            with self.assertRaises(ValueError) as caught:
                self.run_fit(author.FakeClassifier())
        self.assertIs(caught.exception, failure)
        self.assertEqual(author.FakeClassifier.total_fits, 1)
        self.assertEqual(self.selections, [])

    def test_fitted_model_is_rejected_without_another_fit(self):
        model = author.FakeClassifier()
        model.tree_count_ = 5
        with self.assertRaisesRegex(ValueError, 'Fresh exact'):
            self.run_fit(model)
        self.assertEqual(author.FakeClassifier.total_fits, 0)
        self.assertEqual(self.selections, [])

    def test_no_positive_full_targets_rejects_before_fit(self):
        self.validation.queries = [('invented-q', 'invented-u', None, frozenset())]
        accounting = self.modules['scripts.train_baselines']
        accounting.group_accounting = lambda data: (
            [2], [1], [1], [True], [.5, .5],
            {'positive_fullY_queries': sum(bool(query[3]) for query in data.queries)})
        with self.assertRaisesRegex(ValueError, 'positive full targets'):
            self.run_fit(author.FakeClassifier())
        self.assertEqual(author.FakeClassifier.total_fits, 0)
        self.assertEqual(self.selections, [])


    def test_off_candidate_targets_report_zero_informative_groups_without_changing_selection(self):
        from dataclasses import dataclass
        import math
        import numpy as np
        from scripts import ranking_metrics as metrics

        # Actual accounting and ranking bodies, without importing SQL/data loaders.
        accounting = ModuleType('scripts.train_baselines')
        accounting.__dict__.update(np=np, dataclass=dataclass,
                                   QueryRanking=metrics.QueryRanking)
        wanted = {'Prepared', 'group_accounting', 'rankings', '_BudgetCallback'}
        body = [node for node in ast.parse(raw_source(REPO_ROOT/'scripts/train_baselines.py')).body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted]
        self.assertEqual({node.name for node in body}, wanted)
        selector = ModuleType('scripts.adaptive_tree_selection')
        selector.__dict__['math'] = math
        selector_names = {'need', 'positive_layout', '_choose_curve', 'select_best_tree'}
        selector_body = [node for node in ast.parse(raw_source(REPO_ROOT/'scripts/adaptive_tree_selection.py')).body
                         if isinstance(node, ast.FunctionDef) and node.name in selector_names]
        self.assertEqual({node.name for node in selector_body}, selector_names)
        package = ModuleType('scripts')
        package.train_baselines, package.adaptive_tree_selection = accounting, selector
        package.ranking_metrics = metrics
        modules = dict(self.modules, scripts=package)
        modules.update({'scripts.train_baselines': accounting,
                        'scripts.adaptive_tree_selection': selector,
                        'scripts.ranking_metrics': metrics})
        selector_supports = []
        prefixes = ((3.0, -1.0), (-2.0, 7.0), (0.0, 0.0))

        def staged(instance, x, **kwargs):
            self.assertEqual(kwargs, dict(prediction_type='RawFormulaVal', ntree_start=0,
                                          ntree_end=3, eval_period=1, thread_count=2))
            self.assertEqual(x.shape, (2, 1))
            return (np.asarray(values, dtype=np.float64) for values in prefixes)

        with patch.dict(sys.modules, modules):
            exec(compile(ast.Module(body=body, type_ignores=[]), '<actual-accounting-and-rankings>', 'exec'),
                 accounting.__dict__)
            exec(compile(ast.Module(body=selector_body, type_ignores=[]), '<actual-selector>', 'exec'),
                 selector.__dict__)
            actual_select = selector.select_best_tree

            def capture_support(*args, **kwargs):
                best, curve, support = actual_select(*args, **kwargs)
                selector_supports.append(support)
                return best, curve, support

            selector.select_best_tree = capture_support

            def prepared(query_id, targets, labels):
                return accounting.Prepared(
                    [(query_id, 'invented-u', None, frozenset(targets))],
                    np.asarray([0, 0], dtype=np.int32), np.asarray([1, 2], dtype=np.int64),
                    np.asarray([[0.0], [1.0]], dtype=np.float32),
                    np.asarray(labels, dtype=np.int8), ['invented_numeric'])

            train = prepared('train', {1}, [1, 0])
            validation = prepared('validation', {99}, [0, 0])
            self.assertEqual(accounting.group_accounting(validation)[-1]['informative_groups'], 0)
            orders = [tuple(accounting.rankings(validation, scores)[0].ranked_items)
                      for scores in prefixes]
            self.assertEqual(orders, [(1, 2), (2, 1), (1, 2)])
            model = FakeClassifier()
            model.params['iterations'] = 3
            with patch.object(FakeClassifier, 'staged_predict', staged, create=True):
                result = self.helper(model, train, validation, max_iterations=3, check=lambda: None)
        # FullY={99} is outside fixed C={1,2}; every prefix has literal NDCG=0.
        self.assertEqual(result.validation_curve, (0.0, 0.0, 0.0))
        self.assertEqual((result.selected_trees, result.trained_ceiling), (1, 3))
        self.assertEqual(result.validation_support['informative_candidate_groups'], 0)
        self.assertEqual(result.validation_support['fullY_positive_queries'], 1)
        self.assertEqual(len(selector_supports), 1)
        self.assertNotIn('informative_candidate_groups', selector_supports[0])
        self.assertIsNot(result.validation_support, selector_supports[0])
        self.assertEqual((FakeClassifier.total_fits, model.tree_count_, model.shrinks), (1, 3, []))
        self.assertEqual((result.selected_model.tree_count_, result.selected_model.shrinks), (1, [1]))


if __name__ == '__main__':
    unittest.main()
