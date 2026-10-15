from copy import deepcopy
from datetime import datetime
import struct
import unittest
from unittest.mock import patch
import numpy as np
from scripts import heldout_predictions as m
from scripts.inference_data import InferenceData
from tests.test_heldout_contract import fixture


class NativeFake:
    """No actual CatBoost object, file load, Pool, native prediction or fit."""
    def __init__(self,spec,offset):
        self.feature_names_=list(spec['feature_names']);self.tree_count_=300
        self.params=deepcopy(spec['effective_parameters']);self.offset=offset;self.calls=[];self.hook=None
    def get_all_params(self):return deepcopy(self.params)
    def get_cat_feature_indices(self):return []
    def get_text_feature_indices(self):return []
    def get_embedding_feature_indices(self):return []
    def predict(self,x,**kwargs):
        self.calls.append((x,kwargs));result=np.asarray(x[:,0]+self.offset,dtype=np.float64)
        return self.hook(result) if self.hook else result


class FrozenPredictionTests(unittest.TestCase):
    def setUp(self):self.reset()
    def reset(self,choice='I1',anchor='2019-10-27T00:00:00Z'):
        self.anchor=anchor;self.lock,self.choice,_,self.source,*_=fixture(choice)
        fixed=dict(random_seed=2026,boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',
            leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',random_strength=1,
            boost_from_average=False,use_best_model=False,border_count=254,nan_mode='Min',rsm=1,
            learning_rate=struct.unpack('!f',struct.pack('!f',.05))[0])
        for spec in self.lock['models'].values():spec['effective_parameters'].update(fixed)
        self.choice['models']=deepcopy(self.lock['models'])
        self.models={role:NativeFake(self.lock['models'][role],0 if role=='B' else .5) for role in ['B','W']}
        self.loads=[];self.data_calls=[];self.data_hook=None
    def load_model(self,ref):
        self.loads.append(ref)
        return self.models['B'] if ref==self.lock['models']['B']['model'] else self.models['W']
    def load_data(self,qp,fp,**kw):
        self.data_calls.append((qp,fp,deepcopy(kw)));row=next(r for r in self.source['days'] if r['anchor']==self.anchor)
        qn,n=row['query_count'],row['candidate_count'];names=kw['expected_feature_names'];when=m.h.utc(self.anchor).replace(tzinfo=None)
        queries=[(name,2**60+i,when) for i,name in enumerate(['a','z'][:qn])]
        group=np.array([0,0,1] if n else [],dtype=np.int32);items=np.array([2**60,2**60+1,7] if n else [],dtype=np.int64)
        x=np.zeros((n,len(names)),dtype=np.float32)
        if n:x[:,0]=[-1.,2.,3.]
        data=InferenceData(queries,group,items,x,list(names),np.ones(qn,dtype=np.bool_),dict(outcome_relations_opened=0))
        if self.data_hook:self.data_hook(data,len(self.data_calls))
        return data
    def run_core(self,**kwargs):
        return m.score_day(self.anchor,self.lock,authenticated_choice=self.choice,authenticated_source=self.source,
            load_model=self.load_model,load_data=self.load_data,**kwargs)
    def test_exact_raw_prefix_thread2_bigint_and_no_labels(self):
        result=self.run_core();b,w=(result['predictions'][name] for name in ['B','W'])
        np.testing.assert_array_equal(b.scores,[-1.,2.,3.]);np.testing.assert_array_equal(w.scores,[-.5,2.5,3.5])
        self.assertEqual(b.items.tolist(),[2**60,2**60+1,7]);self.assertEqual(b.queries[0][1],2**60)
        self.assertEqual(result['native_prediction_calls'],2);self.assertEqual(result['outcome_relations_opened'],0)
        self.assertFalse(hasattr(b,'y'));self.assertEqual(len(b.queries[0]),3)
        for model in self.models.values():self.assertEqual(model.calls[0][1],dict(prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2))
        self.assertEqual(self.data_calls[0][2]['extra_feature_paths'],None)
        self.assertEqual(self.data_calls[1][2]['extra_feature_paths'],[self.source['days'][2]['extra_features']['path']])
        self.assertEqual(len(w.feature_names),44)
    def test_W_equal_B_transparently_reuses_exact_score_object(self):
        self.reset('B');result=self.run_core();self.assertIs(result['predictions']['B'],result['predictions']['W'])
        self.assertEqual((len(self.loads),len(self.data_calls),result['native_prediction_calls']),(1,1,1))
    def test_empty_candidates_keep_all_queries_and_skip_native_predict(self):
        self.reset(anchor='2019-10-26T00:00:00Z');result=self.run_core()
        self.assertEqual(result['native_prediction_calls'],0)
        for output in result['predictions'].values():self.assertEqual((len(output.queries),len(output.scores)),(2,0))
        self.assertTrue(all(not model.calls for model in self.models.values()))
    def test_empty_query_date_remains_explicit_and_typed(self):
        self.reset(anchor='2019-10-25T00:00:00Z');result=self.run_core()
        self.assertEqual(result['anchor'],self.anchor);self.assertEqual(len(result['predictions']['B'].queries),0)
        self.assertEqual(result['predictions']['W'].scores.dtype,np.dtype('float64'))
    def test_model_prefix_order_and_native_params_reject_before_data_or_predict(self):
        for bad in ['trees','names','params','lr','cat']:
            self.reset();model=self.models['B']
            if bad=='trees':model.tree_count_=301
            elif bad=='names':model.feature_names_=list(reversed(model.feature_names_))
            elif bad=='params':model.params['depth']=4
            elif bad=='lr':model.params['learning_rate']=.07
            else:model.get_cat_feature_indices=lambda:[0]
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.run_core()
            self.assertEqual(self.data_calls,[]);self.assertEqual(model.calls,[])
    def test_embedding_model_rejected_before_data_or_prediction(self):
        self.models['B'].get_embedding_feature_indices=lambda:[0]
        with self.assertRaises(ValueError):self.run_core()
        self.assertEqual(self.data_calls,[]);self.assertEqual(self.models['B'].calls,[])
    def test_missing_native_parameter_and_bool_integer_type_reject(self):
        for bad in ['missing','bool']:
            self.reset()
            if bad=='missing':self.models['B'].params.pop('random_seed')
            else:self.models['B'].params['iterations']=True
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.run_core()
    def test_loaded_LR_serialization_rounding_tolerated_only_at_native_boundary(self):
        self.models['B'].params['learning_rate']=.05000000075;self.run_core()
    def test_model_state_changed_by_prediction_is_rejected(self):
        def mutate(scores):self.models['B'].tree_count_=301;return scores
        self.models['B'].hook=mutate
        with self.assertRaises(ValueError):self.run_core()
    def test_nonfinite_or_reduced_precision_raw_scores_rejected(self):
        for mode in ['inf','float32','shape']:
            self.reset()
            def wrong(scores):
                if mode=='inf':scores[0]=np.inf;return scores
                return scores.astype(np.float32) if mode=='float32' else scores.reshape(-1,1)
            self.models['B'].hook=wrong
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_core()
    def test_input_NaN_allowed_inf_or_float_keys_rejected(self):
        self.data_hook=lambda data,n:data.x.__setitem__((0,1),np.nan);self.run_core()
        for mode in ['inf','keys','shape']:
            self.reset()
            def wrong(data,n):
                if mode=='inf':data.x[0,1]=np.inf
                elif mode=='keys':data.items=data.items.astype(np.float64)
                else:data.x=data.x[:,:-1]
            self.data_hook=wrong
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_core()
            self.assertEqual(self.models['B'].calls,[])
    def test_duplicate_unordered_and_unknown_group_keys_reject_before_predict(self):
        for mode in ['duplicate','unordered','orphan']:
            self.reset()
            def wrong(data,n):
                if mode=='duplicate':data.items[1]=data.items[0]
                elif mode=='unordered':data.items[:2]=data.items[:2][::-1]
                else:data.group[0]=2
            self.data_hook=wrong
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_core()
            self.assertEqual(self.models['B'].calls,[])
    def test_B_W_query_domain_substitution_is_rejected(self):
        def wrong(data,n):
            if n==2:data.queries[0]=('b',*data.queries[0][1:])
        self.data_hook=wrong
        with self.assertRaises(ValueError):self.run_core()
    def test_future_source_date_or_duplicate_inventory_reject_before_loading(self):
        for mode in ['missing','duplicate','closed']:
            self.reset()
            if mode=='missing':self.source['days'].pop()
            elif mode=='duplicate':self.source['days'][-1]=deepcopy(self.source['days'][0])
            else:self.anchor='2019-10-24T00:00:00Z'
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_core()
            self.assertEqual(self.loads,[])
    def test_maturity_false_and_changed_anchor_or_target_tuple_reject(self):
        for mode in ['maturity','anchor','target']:
            self.reset()
            def wrong(data,n):
                if mode=='maturity':data.calendar_maturity[0]=False
                elif mode=='anchor':data.queries[0]=(*data.queries[0][:2],datetime(2019,10,28))
                else:data.queries[0]=(*data.queries[0],frozenset({7}))
            self.data_hook=wrong
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_core()
    def test_guard_before_loading_and_after_prediction(self):
        with self.assertRaises(TimeoutError):self.run_core(check=lambda:(_ for _ in ()).throw(TimeoutError('stop')))
        self.assertEqual(self.loads,[])
        self.reset();checks=[0]
        def guard():
            checks[0]+=1
            if self.models['B'].calls:raise TimeoutError('after native')
        with self.assertRaises(TimeoutError):self.run_core(check=guard)
        self.assertEqual(len(self.models['B'].calls),1)
    def test_native_valid_key_substitution_and_target_tuple_mutation_reject(self):
        for mode in ['validkey','target']:
            self.reset('B');held=[]
            self.data_hook=lambda data,n:held.append(data)
            def mutate(scores):
                if mode=='validkey':held[0].items[0]-=1
                else:held[0].queries[0]=(*held[0].queries[0],frozenset({7}))
                return scores
            self.models['B'].hook=mutate
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_core()
    def test_native_finite_feature_mutation_rejects_without_dense_copy(self):
        self.reset('B');held=[];self.data_hook=lambda data,n:held.append(data)
        def mutate(scores):held[0].x[0,1]=123.;return scores
        self.models['B'].hook=mutate
        with self.assertRaisesRegex(ValueError,'Feature matrix changed'):self.run_core()
    def test_invalid_loader_cannot_fall_back_to_source_reads(self):
        for bad in [0,False,{},'']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                m.score_day(self.anchor,self.lock,authenticated_choice=self.choice,authenticated_source=self.source,
                    load_model=self.load_model,load_data=bad)
        self.assertEqual(self.loads,[])
    def test_snapshots_immutable_and_core_opens_no_files_or_target_APIs(self):
        before=deepcopy([self.lock,self.choice,self.source])
        with patch('builtins.open',side_effect=AssertionError('No files')),patch('io.open',side_effect=AssertionError('No path files')):
            self.run_core()
        self.assertEqual([self.lock,self.choice,self.source],before)

if __name__=='__main__':unittest.main()
