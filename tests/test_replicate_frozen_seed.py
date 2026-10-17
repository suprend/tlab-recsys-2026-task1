"""Synthetic orchestration controls: NumPy only, no CatBoost/DuckDB/backend imports."""
from copy import deepcopy
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('seed2027_caller', ROOT/'scripts'/'replicate_frozen_seed.py')
c = importlib.util.module_from_spec(spec); sys.modules[spec.name] = c; spec.loader.exec_module(c)

@dataclass
class Prepared:
    queries: list
    group: object
    items: object
    x: object
    y: object
    feature_names: list

class FakeModel:
    saved = {}; fit_calls = 0; predict_calls = 0; rank_drift = False
    def __init__(self, **parameters): self.parameters = parameters; self.tree_count_ = 0; self.feature_names_ = []
    def get_all_params(self): return self.parameters
    def get_cat_feature_indices(self): return []
    get_text_feature_indices = get_cat_feature_indices
    get_embedding_feature_indices = get_cat_feature_indices
    def save_model(self, path, format):
        Path(path).write_bytes(b'fake model, no native bytes')
        self.saved[path] = deepcopy(self)
    def load_model(self, path, format): self.__dict__.update(deepcopy(self.saved[path].__dict__))
    def predict(self, x, **kwargs):
        type(self).predict_calls += 1
        if self.rank_drift and self.tree_count_ != 1200: return np.asarray([1.-1e-13,1.,0.])
        return np.asarray([1.,1.-1e-13,0.])

class PairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.recipe = dict(constructor_parameters=dict(iterations=300,random_seed=2026),
            effective_parameters=dict(iterations=300,random_seed=2026),
            feature_names={'B':['b'+str(i) for i in range(41)],'W':['b'+str(i) for i in range(41)]+['e1','e2','e3']})
        self.data = {}
        for arm in c.ARMS:
            names = self.recipe['feature_names'][arm]
            self.data[arm] = dict(
                train=Prepared([('t',1,None,{10})],np.asarray([0,0],dtype=np.int32),np.asarray([10,11],dtype=np.int64),
                    np.ones((2,len(names)),dtype=np.float32),np.asarray([1,0],dtype=np.int8),names),
                selection=Prepared([('v',1,None,{10}),('off',2,None,{99}),('emptyC',3,None,{88}),('emptyY',4,None,set())],
                    np.asarray([0,0,1],dtype=np.int32),np.asarray([10,11,20],dtype=np.int64),
                    np.ones((3,len(names)),dtype=np.float32),np.asarray([1,0,0],dtype=np.int8),names))
        def ident(data, check):
            return dict(queries_sha256=repr(data.queries),group=data.group.tolist(),items=data.items.tolist(),y=data.y.tolist(),
                        base41=data.x[:,:41].tolist(),x=data.x.tolist(),feature_names=data.feature_names)
        def accounting(data): return None,None,None,None,np.asarray([.5,.5]),dict(positive_fullY_queries=sum(bool(q[3]) for q in data.queries))
        def shared(actual, expected, phase):
            for key in ('queries_sha256','group','items','y','base41'):
                c.need(actual[key] == expected[key], 'shared input differs')
            if phase == 'train': c.need(actual['weights'] == expected['weights'], 'weights differ')
        def rankings(data, scores):
            return tuple(tuple(sorted((int(data.items[i]) for i,g in enumerate(data.group) if g == group),
                key=lambda item: (-float(scores[np.flatnonzero(data.items == item)[0]]),item))) for group in range(len(data.queries)))
        def same(expected, actual): c.need(expected == actual, 'Effective parameters differ')
        def fit(model, train, validation, *, max_iterations, check):
            self.assertTrue((self.out/'both-recipes-sealed.json').is_file())
            self.assertTrue((self.out/'W.recipe.json').is_file())
            self.assertIs(type(train),Prepared); self.assertEqual(len(validation.queries),4)
            self.assertEqual(validation.queries[1][3],{99}); self.assertEqual(validation.queries[2][3],{88})
            self.assertEqual(model.parameters,dict(iterations=1200,random_seed=2027))
            FakeModel.fit_calls += 1
            model.tree_count_, model.feature_names_ = 1200, list(train.feature_names)
            selected = deepcopy(model); selected.tree_count_ = 300
            return SimpleNamespace(full_model=model,selected_model=selected,selected_trees=300,trained_ceiling=1200,
                validation_curve=tuple([.25]*1200),validation_support={'fullY_positive_queries':3},training_accounting={})
        @dataclass
        class Eval:
            conditional_macro_query: dict
        self.r = SimpleNamespace(prepare_matrix=lambda files,recipe,arm,**kw: self.data[arm][files],matrix_identity=ident,
            array_ref=lambda array,check: array.tolist(),require_shared_base=shared)
        self.api = SimpleNamespace(r=self.r,b=SimpleNamespace(Prepared=Prepared,group_accounting=accounting,rankings=rankings),
            np=np,fit=fit,Classifier=FakeModel,same=same,evaluate=lambda rows,k:Eval({'ndcg':.25,'recall':.3}),reserve_fit=self.reserve)
        self.original = {'comparison':{arm:{} for arm in c.ARMS}}
        for arm in c.ARMS:
            for phase in ('train','selection'):
                body = ident(self.data[arm][phase],lambda:None)
                if phase == 'train': body['weights'] = [.5,.5]
                self.original['comparison'][arm][phase] = deepcopy(body)
        FakeModel.saved={}; FakeModel.fit_calls=0; FakeModel.predict_calls=0; FakeModel.rank_drift=False
        self.reserved=0
        self.pop = patch.object(c,'POPULATIONS',{'train':(1,2),'selection':(4,3)})
        self.pop.start(); self.addCleanup(self.pop.stop)
    def reserve(self): self.reserved += 1; c.need(self.reserved <= 2,'fit cap')
    def run_pair(self): return c.execute_pair(self.api,self.recipe,self.original,{'train':'train','selection':'selection'},self.out,lambda:None)
    def assert_no_new_backend_imports(self, before):
        new = set(sys.modules) - before
        backends = {name for name in new if name.partition(".")[0] in {"catboost", "duckdb"}}
        self.assertFalse(backends, f"New backend imports: {sorted(backends)}")
    def test_paired_recipes_fullY_parity_accounting_and_no_native_imports(self):
        before=set(sys.modules)
        result=self.run_pair()
        self.assertEqual(FakeModel.fit_calls,2); self.assertEqual(FakeModel.predict_calls,6); self.assertEqual(self.reserved,2)
        self.assertEqual(result['accounting']['parity_score_values'],18)
        self.assertEqual(result['accounting']['persisted_score_values'],6)
        self.assertEqual(result['accounting']['dependent_prefix_points'],2400)
        self.assertFalse(result['comparison']['finite_criterion_met'])
        self.assert_no_new_backend_imports(before)
    def test_preloaded_duckdb_allows_pair_but_new_backend_import_rejects(self):
        name='duckdb.__seed2027_synthetic_new_backend__'
        self.assertNotIn(name,sys.modules)
        with patch.dict(sys.modules,{'duckdb':ModuleType('duckdb')}):
            before=set(sys.modules)
            self.run_pair()
            self.assert_no_new_backend_imports(before)
            with patch.dict(sys.modules,{name:ModuleType(name)}):
                with self.assertRaisesRegex(AssertionError,'New backend imports.*duckdb'):
                    self.assert_no_new_backend_imports(before)
    def test_base41_mutation_rejects_before_any_fit(self):
        self.data['W']['train'].x[0,0]=7
        with self.assertRaisesRegex(ValueError,'matrix identity'): self.run_pair()
        self.assertEqual(FakeModel.fit_calls,0)
    def test_fullY_off_candidate_mutation_rejects_before_fit(self):
        self.data['W']['selection'].queries[1]=('off',2,None,{123})
        with self.assertRaisesRegex(ValueError,'matrix identity'): self.run_pair()
        self.assertEqual(FakeModel.fit_calls,0)
    def test_population_is_not_silently_subsampled(self):
        self.data['B']['selection'].queries.pop()
        with self.assertRaisesRegex(ValueError,'population'): self.run_pair()
        self.assertEqual(FakeModel.fit_calls,0)
    def test_exact_rank_flip_rejects_despite_score_tolerance(self):
        FakeModel.rank_drift=True
        with self.assertRaisesRegex(ValueError,'exact ranking parity'): self.run_pair()
        self.assertEqual(FakeModel.fit_calls,1)
    def test_constructor_effective_seed_is_both_2027_without_mutating_historical_recipe(self):
        original=deepcopy(self.recipe); specs=c.arm_recipes(self.recipe)
        self.assertEqual(self.recipe,original)
        for arm in c.ARMS:
            self.assertEqual(specs[arm]['constructor']['random_seed'],2027)
            self.assertEqual(specs[arm]['effective']['random_seed'],2027)
    def test_duplicate_json_and_current_pipeline_scope_are_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'): c.parse(b'{"scope":1,"scope":2}')
        self.assertNotEqual(c.SCOPE,'current_fixed_raw_pipeline')
    def test_transport_reconstructs_exact_prepared_preserving_array_objects(self):
        class Other(Prepared): pass
        source=Other(**self.data['B']['train'].__dict__)
        actual=c.exact_prepared(source,Prepared)
        self.assertIs(type(actual),Prepared); self.assertIs(actual.x,source.x); self.assertIs(actual.queries,source.queries)
    def test_loaded_source_uses_the_authenticated_snapshot(self):
        name='invented_seed_source'
        path=self.out/'source.py'; path.write_text('marker = 17\n')
        expected=c.witness(path)
        self.addCleanup(sys.modules.pop,name,None)
        module=c.load_module(name,path,expected)
        self.assertEqual(module.marker,17)
    def test_changed_source_rejected_without_execution(self):
        name='invented_seed_mutant'
        path=self.out/'mutant.py'; path.write_text('marker = 17\n'); expected=c.witness(path)
        path.write_text('raise AssertionError("must never execute")\n')
        with self.assertRaisesRegex(ValueError,'Source snapshot differs'): c.load_module(name,path,expected)
        self.assertNotIn(name,sys.modules)
    def test_late_W_recipe_tampering_stops_before_second_fit(self):
        fit=self.api.fit
        def tamper(*args,**kwargs):
            result=fit(*args,**kwargs)
            path=self.out/'W.recipe.json'; body=c.parse(path.read_bytes())
            body['constructor']['random_seed']=2028
            path.write_text(c.json.dumps(body))
            return result
        self.api.fit=tamper
        with self.assertRaisesRegex(ValueError,'Sealed arm recipe'): self.run_pair()
        self.assertEqual(FakeModel.fit_calls,1); self.assertEqual(self.reserved,1)
    def test_wrong_effective_seed_stops_before_parity(self):
        fit=self.api.fit
        def wrong(*args,**kwargs):
            result=fit(*args,**kwargs); result.full_model.parameters['random_seed']=2028
            return result
        self.api.fit=wrong
        with self.assertRaisesRegex(ValueError,'Effective parameters'): self.run_pair()
        self.assertEqual(FakeModel.predict_calls,0)
    def test_prepared_mutation_during_fit_is_detected(self):
        fit=self.api.fit
        def mutate(*args,**kwargs):
            result=fit(*args,**kwargs); self.data['B']['train'].x[0,0]=13
            return result
        self.api.fit=mutate
        with self.assertRaisesRegex(ValueError,'Prepared input mutated'): self.run_pair()
        self.assertEqual(FakeModel.fit_calls,1)
    def test_helper_failure_is_not_retried(self):
        error=RuntimeError('invented helper failure')
        def fail(*args,**kwargs): raise error
        self.api.fit=fail
        with self.assertRaises(RuntimeError) as caught: self.run_pair()
        self.assertIs(caught.exception,error); self.assertEqual(self.reserved,1)
        self.assertTrue((self.out/'B.fit-consumed.json').is_file())
        self.assertFalse((self.out/'W.fit-consumed.json').exists())
    def test_live_module_and_package_alias_replacement_reject(self):
        package=ModuleType('invented_package'); module=ModuleType('invented_package.worker')
        package.worker=module
        with patch.dict(sys.modules,{'invented_package':package,'invented_package.worker':module}):
            c.check_live_modules({'invented_package.worker':module})
            package.worker=ModuleType('different_worker')
            with self.assertRaisesRegex(ValueError,'package alias'): c.check_live_modules({'invented_package.worker':module})
            package.worker=module; sys.modules['invented_package.worker']=ModuleType('replacement')
            with self.assertRaisesRegex(ValueError,'module replaced'): c.check_live_modules({'invented_package.worker':module})

if __name__ == '__main__': unittest.main(verbosity=2)
