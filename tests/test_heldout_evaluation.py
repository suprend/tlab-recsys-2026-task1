from copy import deepcopy
from datetime import datetime,timedelta
import math,random,unittest
from unittest.mock import patch
import duckdb
import numpy as np
from scripts import heldout_evaluation as m
from tests.test_heldout_contract import fixture

BIG=2**60


class EvaluationCoreTests(unittest.TestCase):
    def setUp(self):
        self.con=duckdb.connect(':memory:');self.con.execute('SET threads=2');self.con.execute("SET memory_limit='128MB'");self.con.execute("SET max_temp_directory_size='0B'")
        self.con.execute('CREATE TABLE heldout_raw_events(event_time TIMESTAMP,event_type VARCHAR,user_id BIGINT,product_id BIGINT)')
        self.configure()
    def tearDown(self):self.con.close()
    def configure(self,choice='R2',empty=False):
        self.lock,self.choice,self.inventory,self.source,self.intent,self.acceptance=fixture(choice)
        self.pop={};self.saved={};self.calls=[]
        ids=['a','b','c','d','e',None,'f'];users=[BIG+100,BIG+100,BIG+101,BIG+101,BIG+102,None,BIG+103]
        items=[[BIG,BIG+1],[],[20,21],[30],[40],[],[50]]
        base=[[0.,0.],[],[1.,0.],[0.],[0.],[],[0.]];extra=[[0.,1.],[],[0.,1.],[0.],[0.],[],[0.]]
        for index,day in enumerate(self.source['days']):
            qn=0 if empty or ids[index] is None else 1;chosen=[] if empty else items[index];n=len(chosen)
            for entry in [day,self.inventory['days'][index]]:entry.update(query_count=qn,candidate_count=n,mature_query_count=qn)
            when=m.h.utc(day['anchor']).replace(tzinfo=None)
            self.pop[day['anchor']]=dict(queries=[(ids[index],users[index],when)] if qn else [],calendar_maturity=np.ones(qn,dtype=np.bool_),
                candidate_group=np.zeros(n,dtype=np.int32),candidate_items=np.asarray(chosen,dtype=np.int64))
            for role in ['B','W']:
                descriptor=self.inventory['days'][index]['predictions'][role];descriptor.update(rows=n,queries=qn)
                raw=base[index] if role=='B' or choice=='B' else extra[index]
                self.saved[descriptor['artifact']['path']]=dict(group=np.zeros(n,dtype=np.int32),items=np.asarray(chosen,dtype=np.int64),scores=np.asarray([] if empty else raw,dtype=np.float64))
        self.acceptance['inventory_sha256']=m.h.digest(self.inventory);self.intent['prediction_inventory_sha256']=self.acceptance['inventory_sha256']
    def raw(self):
        t=datetime(2019,10,25);u=BIG+100
        rows=[(t,'purchase',u,999),(t+timedelta(hours=1),'purchase',u,BIG+1),(t+timedelta(hours=1),'purchase',u,BIG+1),
            (t+timedelta(days=1),'purchase',u,123),(t+timedelta(days=2,hours=2),'purchase',u+1,20),
            (t+timedelta(days=3,hours=4),'purchase',u+1,30),(t+timedelta(days=6),'purchase',u+3,50),
            (t+timedelta(days=7),'purchase',u+3,51),(t+timedelta(hours=2),'cart',u,888),
            (t+timedelta(days=6,hours=1),'purchase',u+3,None)]
        self.con.executemany('INSERT INTO heldout_raw_events VALUES (?,?,?,?)',rows)
    def population(self,day):self.calls.append(('population',day['anchor']));return self.pop[day['anchor']]
    def scores(self,descriptor):self.calls.append(('score',descriptor['artifact']['path']));return self.saved[descriptor['artifact']['path']]
    def evaluate(self,**kwargs):
        return m.evaluate_windows(self.con,self.lock,self.inventory,self.intent,authenticated_choice=self.choice,
            authenticated_source=self.source,authenticated_prediction_acceptance=self.acceptance,
            load_day_population=self.population,load_saved_scores=self.scores,**kwargs)
    def assert_no_targets(self):
        names={r[0] for r in self.con.execute('SHOW TABLES').fetchall()};self.assertNotIn('heldout_target_queries',names);self.assertNotIn('heldout_full_targets',names)
    def test_fullY_exact_boundaries_duplicates_outC_emptyC_and_bigint(self):
        self.raw();result=self.evaluate();targets=result['private_targets']
        self.assertEqual(targets['a'],frozenset({BIG+1,999}));self.assertEqual(targets['b'],frozenset({123}));self.assertEqual(targets['f'],frozenset({50}));self.assertEqual(targets['e'],frozenset())
        first=result['periods']['confirmation25_reporting_only'];final=result['periods']['final26_31_frozen'];d=1/math.log2(3)
        self.assertAlmostEqual(first['metrics']['B']['conditional_macro_query']['ndcg'],d/(1+d))
        self.assertAlmostEqual(first['metrics']['W']['conditional_macro_query']['ndcg'],1/(1+d))
        self.assertEqual(first['metrics']['B']['conditional_macro_query']['recall'],.5)
        self.assertEqual(final['support'],dict(query_count=5,candidate_pairs=5,target_pairs=4,retrieved_target_pairs=3,positive_empty_C_queries=1))
        self.assertEqual(final['metrics']['B']['conditional_macro_query']['ndcg'],.75)
        self.assertAlmostEqual(final['metrics']['W']['conditional_macro_query']['ndcg'],(2+d)/4)
        self.assertEqual(final['metrics']['B']['all_query_zero']['ndcg'],.6)
        self.assertAlmostEqual(final['metrics']['W']['conditional_user_macro']['ndcg'],(1+(1+d)/2)/3)
        self.assertEqual((result['fit_attempt_count'],result['native_prediction_count']),(0,0))
    def test_all_200_shared_user_draws_match_literal_query_and_user_weights(self):
        self.raw();final=self.evaluate()['periods']['final26_31_frozen'];users=[BIG+100,BIG+101,BIG+102,BIG+103]
        rng=random.Random(2026);discount=1/math.log2(3)
        expected={name:[] for name in m.metrics.ESTIMANDS}
        for _ in range(200):
            drawn=rng.choices(users,k=4);a,b,c,d=[drawn.count(user) for user in users]
            for name,denom,numer in [('conditional_macro_query',a+2*b+d,-(1-discount)*b),
                ('all_query_zero',a+2*b+c+d,-(1-discount)*b),('conditional_user_macro',a+b+d,-(1-discount)*b/2),
                ('all_user_macro_zero',a+b+c+d,-(1-discount)*b/2)]:expected[name].append(numer/denom if denom else None)
        for name,values in expected.items():
            actual=final['paired_user_bootstrap'][name]
            self.assertEqual(actual['replicates'],200);self.assertEqual(actual['undefined_draws'],values.count(None))
            for a,b in zip(actual['samples'],values):
                if b is None:self.assertIsNone(a)
                else:self.assertAlmostEqual(a,b,places=12)
    def test_W_equal_B_is_zero_for_every_defined_estimand_and_draw(self):
        self.configure('B');self.raw();result=self.evaluate()
        for period in result['periods'].values():
            self.assertTrue(all(v==0 for v in period['ndcg_W_minus_B'].values()))
            for boot in period['paired_user_bootstrap'].values():self.assertTrue(all(v is None or v==0 for v in boot['samples']))
    def test_zeroY_is_not_censoring_or_discarded_population(self):
        result=self.evaluate()
        for period in result['periods'].values():
            self.assertGreater(period['metrics']['B']['query_count'],0);self.assertEqual(period['metrics']['B']['censored_query_count'],0)
            self.assertEqual(period['metrics']['B']['all_query_zero']['ndcg'],0);self.assertIsNone(period['metrics']['B']['conditional_macro_query']['ndcg'])
            self.assertEqual(period['paired_user_bootstrap']['conditional_macro_query']['undefined_draws'],200)
    def test_empty_all_dates_keep_two_explicit_undefined_reports(self):
        self.configure(empty=True);result=self.evaluate();self.assertEqual(len(result['periods']),2)
        for period in result['periods'].values():
            self.assertEqual(period['metrics']['B']['query_count'],0)
            for boot in period['paired_user_bootstrap'].values():self.assertEqual(boot['undefined_draws'],200);self.assertIsNone(boot['interval_95'])
    def test_unaccepted_or_misbound_prediction_cannot_open_any_provider_or_Y(self):
        self.acceptance['inventory_sha256']='b'*64
        with self.assertRaises(ValueError):self.evaluate()
        self.assertEqual(self.calls,[]);self.assert_no_targets()
    def test_missing_day_and_adaptation_rejected_before_loading(self):
        self.inventory['days'].pop()
        with self.assertRaises(ValueError):self.evaluate()
        self.assertEqual(self.calls,[]);self.assert_no_targets()
    def test_target_intent_time_and_no_adaptation_are_mandatory(self):
        for field,value in [('opened_at',self.inventory['created_at']),('no_adaptation',False)]:
            old=self.intent[field];self.intent[field]=value
            with self.assertRaises(ValueError):self.evaluate()
            self.assertEqual(self.calls,[]);self.assert_no_targets();self.intent[field]=old
    def test_late_last_day_corrupt_score_still_precedes_all_target_operations(self):
        last=self.inventory['days'][-1]['predictions']['W']['artifact']['path'];self.saved[last]['scores']=np.zeros(1,dtype=np.float32)
        with self.assertRaises(ValueError):self.evaluate()
        self.assertGreater(len(self.calls),18);self.assert_no_targets()
    def test_exact_candidate_score_key_matching_and_null_nonfinite_reject(self):
        path=self.inventory['days'][0]['predictions']['B']['artifact']['path'];self.saved[path]['items'][0]-=1
        with self.assertRaises(ValueError):self.evaluate()
        self.assert_no_targets()
    def test_wrong_population_float_ID_or_target_tuple_rejects_beforeY(self):
        for mode in ['float','target','calendar']:
            self.configure();pop=self.pop[m.h.DAYS[0]]
            if mode=='float':pop['candidate_items']=pop['candidate_items'].astype(np.float64)
            elif mode=='target':pop['queries'][0]=(*pop['queries'][0],frozenset({7}))
            else:pop['calendar_maturity'][0]=False
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.evaluate()
            self.assert_no_targets()
    def test_nonfinite_scores_and_out_of_range_group_fail_beforeY(self):
        for mode in ['score','group']:
            self.configure();path=self.inventory['days'][0]['predictions']['B']['artifact']['path']
            if mode=='score':self.saved[path]['scores'][0]=np.nan
            else:self.saved[path]['group'][0]=4
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.evaluate()
            self.assert_no_targets()
    def test_typed_raw_source_and_two_threads_mandatory_before_target_join(self):
        self.con.execute('SET threads=1')
        with self.assertRaises(ValueError):self.evaluate()
        self.assert_no_targets()
    def test_every_seven_day_population_and_both_scores_loaded_before_Y(self):
        self.raw()
        def stage(name,operation):
            self.assertEqual(len(self.calls),21)
            return operation()
        self.evaluate(stage=stage)
    def test_staged_query_omission_rejects_before_creating_fullY(self):
        self.raw()
        def stage(name,operation):
            value=operation()
            if name=='create_complete_target_query_population':self.con.execute("DELETE FROM heldout_target_queries WHERE query_id='f'")
            return value
        with self.assertRaisesRegex(ValueError,'Staged target Q'):self.evaluate(stage=stage)
        self.assertNotIn('heldout_full_targets',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
    def test_user_substitution_inside_fullY_stage_rejects_before_JOIN(self):
        self.raw()
        def stage(name,operation):
            if name=='create_fullY_independent_of_candidates':self.con.execute("UPDATE heldout_target_queries SET user_id=7 WHERE query_id='a'")
            return operation()
        with self.assertRaisesRegex(ValueError,'Staged target Q'):self.evaluate(stage=stage)
        self.assertNotIn('heldout_full_targets',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
    def test_query_deletion_after_fullY_stage_is_rejected(self):
        self.raw()
        def stage(name,operation):
            value=operation()
            if name=='create_fullY_independent_of_candidates':self.con.execute("DELETE FROM heldout_target_queries WHERE query_id='f'")
            return value
        with self.assertRaisesRegex(ValueError,'Staged target Q'):self.evaluate(stage=stage)
        self.assertIn('heldout_full_targets',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
    def test_last_terminal_guard_cannot_mutate_staged_Q_unchecked(self):
        self.raw();pending=False;modified=False;original=m.metrics.paired_user_bootstrap;calls=0
        def bootstrap(*args,**kwargs):
            nonlocal pending,calls
            value=original(*args,**kwargs);calls+=1
            if calls==8:pending=True
            return value
        def check():
            nonlocal pending,modified
            if pending:
                self.con.execute("UPDATE heldout_target_queries SET user_id=7 WHERE query_id='a'")
                pending=False;modified=True
        with patch.object(m.metrics,'paired_user_bootstrap',bootstrap),self.assertRaisesRegex(ValueError,'Staged target Q'):self.evaluate(check=check)
        self.assertTrue(modified)
    def test_snapshots_are_decoupled_from_providers_and_no_files_models_or_Y_API(self):
        self.raw();before=deepcopy([self.lock,self.inventory,self.source,self.intent,self.acceptance])
        with patch('builtins.open',side_effect=AssertionError('No files')),patch('io.open',side_effect=AssertionError('No path reads')):self.evaluate()
        self.assertEqual([self.lock,self.inventory,self.source,self.intent,self.acceptance],before)
    def test_guard_and_failed_after_Y_attempt_do_not_erase_or_allow_same_connection_retry(self):
        with self.assertRaises(TimeoutError):self.evaluate(check=lambda:(_ for _ in ()).throw(TimeoutError('stop')))
        self.assertEqual(self.calls,[]);self.assert_no_targets();self.raw()
        def stage(name,operation):
            value=operation()
            if name=='create_fullY_independent_of_candidates':raise TimeoutError('after Y')
            return value
        with self.assertRaises(TimeoutError):self.evaluate(stage=stage)
        self.assertIn('heldout_full_targets',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
        with self.assertRaises(duckdb.CatalogException):self.evaluate()

if __name__=='__main__':unittest.main()
