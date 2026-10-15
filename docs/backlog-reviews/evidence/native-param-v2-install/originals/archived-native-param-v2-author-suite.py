"""Saved-capture pure regressions; no native imports/loads, IO or model edits."""
import ast
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import resource
import signal
import struct
import sys
import time
import types
import unittest

resource.setrlimit(resource.RLIMIT_CPU,(30,30));signal.alarm(60)
START=time.monotonic();CPU=time.process_time()
PROJECT=Path('/Users/mdpospelov/tlab-recsys-2026')
CAPTURE_PATH=Path('/tmp/tlab-018-native-param-diagnostic-20261015-once/capture.json')
CAPTURE_RAW=CAPTURE_PATH.read_bytes()
assert hashlib.sha256(CAPTURE_RAW).hexdigest()=='c5da7fdd527abcbf9b98f43c2bea66774e3fcca285e913efa6025f1618188a8c'
CAPTURE=json.loads(CAPTURE_RAW)
SPEC=CAPTURE['expected_spec'];PARAMS=CAPTURE['actual_params']
E=SPEC['effective_parameters']['bayesian_matrix_reg'];A=PARAMS['bayesian_matrix_reg']


def load_pure(path,role,sha=None):
    raw=path.read_bytes()
    assert len(raw)<=262144
    if sha:assert hashlib.sha256(raw).hexdigest()==sha
    tree=ast.parse(raw,filename=str(path))
    names=({'_bayesian_serialized_alias','_same','verify_model'} if role=='production' else
           {'need','keys','identifier','ref','native_equal','model_spec','native_model'})
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    required={'_same','verify_model'} if role=='production' else names
    assert required.issubset({n.name for n in nodes})
    m=types.ModuleType('pure_'+role+'_'+path.stem)
    m.__dict__.update(math=math,struct=struct,re=re,META={'query_id','user_id','product_id','anchor','last_user_event_time','candidate_category_id'},
        DERIVED=['retrieval_last_event_age_seconds','retrieval_last_event_missing'],h=H)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec',dont_inherit=True),m.__dict__)
    return m


H=types.ModuleType('pure_original_contract')
H_RAW=(PROJECT/'scripts/heldout_contract.py').read_bytes()
assert hashlib.sha256(H_RAW).hexdigest()=='fc50d11d3b6dfdc2906522472f5b66138424bc4586e7833b43c6fc4e6c4f1abc'
exec(compile(H_RAW,'original_contract','exec',dont_inherit=True),H.__dict__)
OLD_P=load_pure(PROJECT/'scripts/heldout_predictions.py','production','e1b06b2aac68c59379d15298c39101ec02b6a176c26b13d4671f8e445de2851b')
OLD_O=load_pure(PROJECT/'tests/oracles/heldout_prediction_audit.py','oracle','c552ab5a99bde1f8aac8cfc72a0bb0ea758829b558ca02d457e6a7c2b2c30438')
NEW_P=load_pure(Path('/tmp/tlab-heldout-predictions-bayesian-alias-proposal-v2.py'),'production')
NEW_O=load_pure(Path('/tmp/tlab-heldout-prediction-audit-bayesian-alias-proposal-v2.py'),'oracle')


class SavedModel:
    def __init__(self,params=None,tree=300,names=None,indices=None):
        self.params=deepcopy(PARAMS if params is None else params)
        self.tree_count_=tree;self.feature_names_=deepcopy(SPEC['feature_names'] if names is None else names)
        self.indices={} if indices is None else indices
    def get_all_params(self):return deepcopy(self.params)
    def get_cat_feature_indices(self):return self.indices.get('cat',[])
    def get_text_feature_indices(self):return self.indices.get('text',[])
    def get_embedding_feature_indices(self):return self.indices.get('embedding',[])


def both_full(model=None,spec=None):
    model=SavedModel() if model is None else model;spec=deepcopy(SPEC if spec is None else spec)
    NEW_P.verify_model(model,spec);NEW_O.model_spec(spec,41);NEW_O.native_model(model,spec)


def leaf(module,expected,actual,path):
    if hasattr(module,'_same'):return module._same(expected,actual,path)
    return module.native_equal(actual,expected,path)


class AliasTests(unittest.TestCase):
    def assert_leaf_rejected(self,expected,actual,path=('bayesian_matrix_reg',)):
        for module in (NEW_P,NEW_O):
            with self.subTest(module=module.__name__,path=path,actual=actual):
                with self.assertRaises(ValueError):leaf(module,expected,actual,path)

    def test_01_actual_full_capture_originals_RED_proposals_GREEN(self):
        with self.assertRaisesRegex(ValueError,'Native effective parameter differs'):OLD_P.verify_model(SavedModel(),deepcopy(SPEC))
        with self.assertRaisesRegex(ValueError,'Native parameter float differs'):OLD_O.native_model(SavedModel(),deepcopy(SPEC))
        both_full()

    def test_02_minimum_actual_pair_original_same_AST_RED_proposed_GREEN(self):
        for module in (OLD_P,OLD_O):
            with self.assertRaises(ValueError):leaf(module,E,A,('bayesian_matrix_reg',))
        for module in (NEW_P,NEW_O):leaf(module,E,A,('bayesian_matrix_reg',))

    def test_03_observed_discriminator_both_diffs_float32_same_decimal10(self):
        for key in ('bayesian_matrix_reg','learning_rate'):
            expected=SPEC['effective_parameters'][key];actual=PARAMS[key]
            self.assertNotEqual(expected,actual)
            self.assertEqual(struct.pack('!f',expected),struct.pack('!f',actual))
            self.assertEqual(float(format(expected,'.10g')),actual)
        self.assertEqual(E,struct.unpack('!f',struct.pack('!f',E))[0])

    def test_04_learning_rate_original_contract_unchanged(self):
        expected=SPEC['effective_parameters']['learning_rate'];actual=PARAMS['learning_rate']
        for module in (OLD_P,OLD_O,NEW_P,NEW_O):
            leaf(module,expected,actual,('learning_rate',))
            with self.assertRaises(ValueError):leaf(module,expected,expected+1e-8,('learning_rate',))
        oldp=ast.parse((PROJECT/'scripts/heldout_predictions.py').read_bytes())
        newp=ast.parse(Path('/tmp/tlab-heldout-predictions-bayesian-alias-proposal-v2.py').read_bytes())
        def tolerance(tree):
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_same')
            return ast.dump(next(n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='tolerance' for t in n.targets)))
        self.assertEqual(tolerance(oldp),tolerance(newp))

    def test_05_next_float32_ULP_from_point1_rejected(self):
        bits=struct.unpack('!I',struct.pack('!f',.1))[0]
        successor=struct.unpack('!f',struct.pack('!I',bits+1))[0]
        self.assertNotEqual(struct.pack('!f',E),struct.pack('!f',successor))
        self.assert_leaf_rejected(E,successor)

    def test_06_same_float32_bin_without_observed_alias_rejected(self):
        different=E+1e-10
        self.assertEqual(struct.pack('!f',E),struct.pack('!f',different))
        self.assertNotEqual(different,float(format(E,'.10g')))
        self.assert_leaf_rejected(E,different)

    def test_07_unrelated_and_nested_float_keys_do_not_gain_alias(self):
        for path in (('other_float',),('metadata','bayesian_matrix_reg'),('bayesian_matrix_reg','nested')):
            self.assert_leaf_rejected(E,A,path)

    def test_08_bool_int_and_float_types_remain_exact(self):
        for expected,actual in ((E,True),(E,0),(True,1),(1,1.0),(1.0,1)):
            self.assert_leaf_rejected(expected,actual)
        for expected,actual in ((True,True),(1,1),(E,E)):
            for module in (NEW_P,NEW_O):leaf(module,expected,actual,('bayesian_matrix_reg',))

    def test_09_nonfinite_and_overflow_values_rejected(self):
        for invalid in (float('nan'),float('inf'),float('-inf')):
            self.assert_leaf_rejected(E,invalid);self.assert_leaf_rejected(invalid,E)
        self.assert_leaf_rejected(1e100,1e100+1e90)

    def test_10_model_parameter_schema_missing_extra_renamed_rejected(self):
        for operation in ('missing','extra','rename'):
            params=deepcopy(PARAMS)
            if operation=='missing':del params['bayesian_matrix_reg']
            if operation=='extra':params['new_float']=A
            if operation=='rename':params['renamed']=params.pop('bayesian_matrix_reg')
            for module,call in ((NEW_P,lambda m:NEW_P.verify_model(m,deepcopy(SPEC))),
                                (NEW_O,lambda m:NEW_O.native_model(m,deepcopy(SPEC)))):
                with self.subTest(operation=operation,module=module.__name__):
                    with self.assertRaises(ValueError):call(SavedModel(params=params))

    def test_11_fixed_effective_setting_corruption_rejected(self):
        params=deepcopy(PARAMS);params['depth']=7
        for call in (lambda:NEW_P.verify_model(SavedModel(params=params),deepcopy(SPEC)),
                     lambda:NEW_O.native_model(SavedModel(params=params),deepcopy(SPEC))):
            with self.assertRaises(ValueError):call()
        spec=deepcopy(SPEC);spec['effective_parameters']['depth']=7
        for call in (lambda:NEW_P.verify_model(SavedModel(),spec),lambda:NEW_O.model_spec(spec,41)):
            with self.assertRaises(ValueError):call()

    def test_12_native_tree_count_or_type_corruption_rejected(self):
        for tree in (299,300.0,True):
            with self.assertRaises(ValueError):NEW_P.verify_model(SavedModel(tree=tree),deepcopy(SPEC))
            with self.assertRaises(ValueError):NEW_O.native_model(SavedModel(tree=tree),deepcopy(SPEC))

    def test_13_native_feature_order_corruption_rejected(self):
        names=deepcopy(SPEC['feature_names']);names[0],names[1]=names[1],names[0]
        with self.assertRaises(ValueError):NEW_P.verify_model(SavedModel(names=names),deepcopy(SPEC))
        with self.assertRaises(ValueError):NEW_O.native_model(SavedModel(names=names),deepcopy(SPEC))

    def test_14_native_non_numeric_features_rejected(self):
        for kind in ('cat','text','embedding'):
            with self.assertRaises(ValueError):NEW_P.verify_model(SavedModel(indices={kind:[0]}),deepcopy(SPEC))
            with self.assertRaises(ValueError):NEW_O.native_model(SavedModel(indices={kind:[0]}),deepcopy(SPEC))

    def test_15_other_float_threshold_and_noncanonical_expected_unchanged(self):
        for module in (NEW_P,NEW_O):
            leaf(module,0.0,1e-12,('unrelated',))
            with self.assertRaises(ValueError):leaf(module,0.0,1.01e-12,('unrelated',))
        self.assert_leaf_rejected(.1,float(format(.1,'.10g'))+1e-10)
        self.assertFalse(NEW_P._bayesian_serialized_alias(True,True,('bayesian_matrix_reg',)))


    def test_16_original_list_origin_REDV1_GREEN_bothV2_RED(self):
        v1p=load_pure(Path('/tmp/tlab-heldout-predictions-bayesian-alias-proposal-v1.py'),'production',
            'a36772a2320634c82f1542658715175ff8956a70e36f803b578a3a2dbf01f68c')
        v1o=load_pure(Path('/tmp/tlab-heldout-prediction-audit-bayesian-alias-proposal-v1.py'),'oracle',
            'f78d7599ce182299a2275c83d4196b1baea6ec29e7a764a5a310502d02a23ad3')
        cases=[([E],[A],('bayesian_matrix_reg',)),([[E]],[[A]],('bayesian_matrix_reg',)),
            ({'bayesian_matrix_reg':[E]},{'bayesian_matrix_reg':[A]},()),
            ([{'bayesian_matrix_reg':E}],[{'bayesian_matrix_reg':A}],())]
        for expected,actual,path in cases:
            for old in (OLD_P,OLD_O):
                with self.assertRaises(ValueError):leaf(old,expected,actual,path)
            for v1 in (v1p,v1o):leaf(v1,expected,actual,path)
            for new in (NEW_P,NEW_O):
                with self.assertRaises(ValueError):leaf(new,expected,actual,path)

    def test_17_learning_rate_list_context_preserves_original_tolerance(self):
        e=SPEC['effective_parameters']['learning_rate'];a=PARAMS['learning_rate']
        for module in (OLD_P,OLD_O,NEW_P,NEW_O):
            for expected,actual in (([e],[a]),([[e]],[[a]])):
                leaf(module,expected,actual,('learning_rate',))
            with self.assertRaises(ValueError):leaf(module,[e],[e+1e-8],('learning_rate',))
            with self.assertRaises(ValueError):leaf(module,[E],[A],('unrelated',))
        # The new flag must affect only alias eligibility, never path/tolerance.
        both_full()


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(AliasTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt=dict(version=1,scope='captured_only_Bayesian_alias_proposal_pure_tests',tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),
        body_CPU_seconds=time.process_time()-CPU,body_wall_seconds=time.monotonic()-START,
        self_CPU_seconds=own.ru_utime+own.ru_stime,self_peak_RSS_bytes=own.ru_maxrss,
        children_CPU_seconds=child.ru_utime+child.ru_stime,children_peak_RSS=child.ru_maxrss,
        native_imports=0,native_loads=0,predict=0,fit=0,source_DB_Y_opens=0,project_writes=False)
    assert receipt['self_peak_RSS_bytes']<=512*2**20 and receipt['body_CPU_seconds']<30 and receipt['body_wall_seconds']<60
    with Path('/tmp/tlab-native-param-alias-proposal-v2-test-results.json').open('x') as handle:json.dump(receipt,handle,indent=2)
    raise SystemExit(0 if result.wasSuccessful() else 1)
