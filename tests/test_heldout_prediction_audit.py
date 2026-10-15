from copy import deepcopy
from datetime import datetime,timedelta
import ast,inspect,unittest
from unittest.mock import patch
import duckdb
import numpy as np
from tests import test_heldout_predictions as fixtures
from tests.oracles import heldout_prediction_audit as a

BIG=2**60


class PredictionOracleTests(unittest.TestCase):
    def setUp(self):
        self.con=duckdb.connect(':memory:');self.con.execute('SET threads=2');self.con.execute("SET memory_limit='128MB'");self.con.execute("SET max_temp_directory_size='0B'")
        f=fixtures.FrozenPredictionTests();f.reset('I1');self.modelspec=deepcopy(f.lock['models'])
        names=['feature_'+str(i) for i in range(39)]+a.DERIVED
        for role in ('B','W'):self.modelspec[role]['feature_names']=names+(['auto_1','auto_2','auto_3'] if role=='W' else [])
        self.anchor='2019-10-27T00:00:00Z';self.when=datetime(2019,10,27);self.row=dict(anchor=self.anchor,query_count=3,candidate_count=3,mature_query_count=3)
        self.queries=[('a',BIG,self.when),('z',BIG+1,self.when),('zz',BIG+2,self.when)]
        self.con.execute('CREATE TABLE heldout_prediction_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN,_group BIGINT)')
        self.con.executemany('INSERT INTO heldout_prediction_queries VALUES (?,?,?,?,?)',[(q,u,t,True,999) for q,u,t in self.queries])
        self.con.execute('CREATE TABLE heldout_prediction_candidates(query_id VARCHAR,product_id BIGINT)')
        pairs=[('a',BIG),('a',BIG+1),('z',7)];self.con.executemany('INSERT INTO heldout_prediction_candidates VALUES (?,?)',pairs)
        sql='CREATE TABLE heldout_prediction_base_features(query_id VARCHAR,user_id BIGINT,product_id BIGINT,anchor TIMESTAMP,last_user_event_time TIMESTAMP,candidate_category_id BIGINT,'+','.join('feature_'+str(i)+' DOUBLE' for i in range(39))+')'
        self.con.execute(sql)
        self.expected=np.zeros((3,44),dtype=np.float32);self.expected[:,0]=[-1.,2.,3.];self.expected[0,1]=np.nan
        self.expected[:,39]=[3600.,np.nan,7200.];self.expected[:,40]=[0.,1.,0.];self.expected[:,41:]=[[4.,5.,0.],[6.,7.,1.],[8.,9.,0.]]
        rows=[]
        for i,(qid,item) in enumerate(pairs):
            user=BIG if qid=='a' else BIG+1;last=None if i==1 else self.when-timedelta(seconds=3600 if i==0 else 7200)
            values=[None if np.isnan(v) else float(v) for v in self.expected[i,:39]]
            rows.append((qid,user,item,self.when,last,123,*values))
        self.con.executemany('INSERT INTO heldout_prediction_base_features VALUES ('+','.join(['?']*45)+')',rows)
        self.con.execute('CREATE TABLE heldout_prediction_extra_features(query_id VARCHAR,product_id BIGINT,auto_1 BIGINT,auto_2 DOUBLE,auto_3 BOOLEAN)')
        self.con.executemany('INSERT INTO heldout_prediction_extra_features VALUES (?,?,?,?,?)',[(q,it,int(self.expected[i,41]),float(self.expected[i,42]),bool(self.expected[i,43])) for i,(q,it) in enumerate(pairs)])
        self.group=np.asarray([0,0,1],dtype=np.int32);self.items=np.asarray([BIG,BIG+1,7],dtype=np.int64)
        self.choice='I1';self.reset_models()
    def tearDown(self):self.con.close()
    def reset_models(self):
        self.native={role:fixtures.NativeFake(spec,0. if role=='B' else .5) for role,spec in self.modelspec.items()};self.loads=[]
        self.produced={role:dict(artifact=dict(path='artifacts/synthetic/'+role+'.npz',sha256='a'*64),model=deepcopy(spec['model']),feature_names=list(spec['feature_names']),
            queries=deepcopy(self.queries),calendar_maturity=np.ones(3,dtype=np.bool_),group=self.group.copy(),items=self.items.copy(),scores=np.asarray([-1.,2.,3.])+(.5 if role=='W' else 0.)) for role,spec in self.modelspec.items()}
    def loader(self,ref):
        self.loads.append(ref);return self.native['B'] if ref==self.modelspec['B']['model'] else self.native['W']
    def audit(self,**kwargs):return a.audit_day(self.con,self.anchor,self.row,choice=self.choice,models=self.modelspec,produced=self.produced,load_model=self.loader,**kwargs)
    def test_literal_independent_B41_W44_matrices_bigint_NULL_age_mask_and_raw_scores(self):
        result=self.audit();self.assertEqual((result['queries'],result['candidate_pairs'],result['native_prediction_count']),(3,3,2))
        for role,width in [('B',41),('W',44)]:
            matrix,kwargs=self.native[role].calls[0];np.testing.assert_array_equal(matrix,self.expected[:,:width])
            self.assertEqual(kwargs,dict(prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2))
        self.assertEqual(self.produced['B']['items'].tolist(),[BIG,BIG+1,7]);self.assertEqual(len(self.produced['B']['queries']),3)
        self.assertEqual((result['fit_attempt_count'],result['outcome_relations_opened']),(0,0))
    def test_source_group_helper_cannot_shadow_independent_numbering(self):
        self.con.execute('UPDATE heldout_prediction_queries SET _group=-100');self.audit()
    def test_B_only_reuses_native_replay_and_exact_produced_artifact(self):
        self.choice='B';self.modelspec['W']=deepcopy(self.modelspec['B']);self.reset_models();self.produced['W']=deepcopy(self.produced['B'])
        result=self.audit();self.assertEqual(result['native_prediction_count'],1);self.assertEqual(len(self.loads),1)
        self.assertIs(result['private_replayed_scores']['W'],result['private_replayed_scores']['B'])
    def test_empty_C_retains_all_Q_and_skips_native_predict(self):
        for table in ['candidates','base_features','extra_features']:self.con.execute('DELETE FROM heldout_prediction_'+table)
        self.row['candidate_count']=0
        for body in self.produced.values():body['group']=np.empty(0,dtype=np.int32);body['items']=np.empty(0,dtype=np.int64);body['scores']=np.empty(0,dtype=np.float64)
        result=self.audit();self.assertEqual(result['queries'],3);self.assertEqual(result['native_prediction_count'],0)
        self.assertTrue(all(not model.calls for model in self.native.values()))
    def test_missing_extra_key_fails_before_native(self):
        self.con.execute("DELETE FROM heldout_prediction_extra_features WHERE query_id='z'")
        with self.assertRaisesRegex(ValueError,'key multiset'):self.audit()
        self.assertEqual(self.loads,[])
    def test_wrong_F_user_rejects_before_native(self):
        self.con.execute("UPDATE heldout_prediction_base_features SET user_id=7 WHERE query_id='z'")
        with self.assertRaisesRegex(ValueError,'identity'):self.audit()
        self.assertEqual(self.loads,[])
    def test_float_candidate_ID_rejects(self):
        self.con.execute('ALTER TABLE heldout_prediction_candidates ALTER product_id TYPE DOUBLE')
        with self.assertRaisesRegex(ValueError,'Typed independent C'):self.audit()
    def test_float32_overflow_rejected_before_native(self):
        self.con.execute('UPDATE heldout_prediction_base_features SET feature_1=1e100')
        with np.errstate(over='ignore'),self.assertRaisesRegex(ValueError,'overflow'):self.audit()
        self.assertEqual(self.loads,[])
    def test_saved_valid_key_substitution_rejects(self):
        self.produced['B']['items'][0]-=1
        with self.assertRaisesRegex(ValueError,'key domain'):self.audit()
        self.assertEqual(self.loads,[])
    def test_raw_score_corruption_is_independently_replayed(self):
        self.produced['W']['scores'][0]=999.
        with self.assertRaisesRegex(ValueError,'raw score mismatch'):self.audit()
    def test_near_tie_score_within_numeric_tolerance_still_rejects_rank_change(self):
        self.con.execute("UPDATE heldout_prediction_base_features SET feature_0=0 WHERE query_id='a'")
        for role in ('B','W'):self.produced[role]['scores'][:2]=0. if role=='B' else .5
        self.produced['B']['scores'][1]=1e-13
        with self.assertRaisesRegex(ValueError,'tie/rank'):self.audit()
    def test_native_embedding_model_rejects(self):
        self.native['B'].get_embedding_feature_indices=lambda:[0]
        with self.assertRaisesRegex(ValueError,'Numeric native'):self.audit()
        self.assertEqual(self.native['B'].calls,[])
    def test_native_mutation_of_input_matrix_rejects(self):
        def mutate(scores):self.native['B'].calls[0][0][0,1]=123.;return scores
        self.native['B'].hook=mutate
        with self.assertRaisesRegex(ValueError,'matrix changed'):self.audit()
    def test_reduced_precision_native_result_rejects(self):
        self.native['B'].hook=lambda scores:scores.astype(np.float32)
        with self.assertRaisesRegex(ValueError,'float64'):self.audit()
    def test_guard_failure_before_loader_and_no_same_connection_retry(self):
        with self.assertRaises(TimeoutError):self.audit(check=lambda:(_ for _ in ()).throw(TimeoutError('stop')))
        self.assertEqual(self.loads,[]);self.audit()
        with self.assertRaises(duckdb.CatalogException):self.audit()
    def test_missing_empty_C_query_rejects(self):
        self.produced['B']['queries']=self.produced['B']['queries'][:2]
        with self.assertRaisesRegex(ValueError,'all-Q list'):self.audit()
    def test_native_B_cannot_mutate_W_extras_through_matrix_base(self):
        def mutate(scores):self.native['B'].calls[0][0].base[0,43]=123.;return scores
        self.native['B'].hook=mutate
        with self.assertRaisesRegex(ValueError,'matrix changed'):self.audit()
    def test_target_bearing_saved_Q_is_rejected_before_model_loader_or_matrix(self):
        self.produced['W']['queries'][0]=(*self.produced['W']['queries'][0],frozenset({7}))
        with self.assertRaisesRegex(ValueError,'without targets'):self.audit()
        self.assertEqual(self.loads,[])
        self.assertNotIn('heldout_prediction_oracle_q',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
    def test_future_retrieval_timestamp_is_rejected_before_loader(self):
        self.con.execute('UPDATE heldout_prediction_base_features SET last_user_event_time=anchor')
        with self.assertRaisesRegex(ValueError,'strictpast'):self.audit()
        self.assertEqual(self.loads,[])
    def test_no_file_opener_and_no_production_matrix_or_scoring_import(self):
        with patch('builtins.open',side_effect=AssertionError('No files')),patch('io.open',side_effect=AssertionError('No paths')):self.audit()
        tree=ast.parse(inspect.getsource(a));names=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        names += [alias.name for n in ast.walk(tree) if isinstance(n,ast.Import) for alias in n.names]
        self.assertEqual(set(names),{'copy','datetime','hashlib','math','re','numpy'})

if __name__=='__main__':unittest.main()
