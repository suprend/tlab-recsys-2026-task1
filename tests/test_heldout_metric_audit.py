from copy import deepcopy
import ast,math,random,unittest
from unittest.mock import patch

import numpy as np
from tests import test_heldout_evaluation as fixtures
from tests.oracles import heldout_metric_audit as a


class MetricOracleTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.EvaluationCoreTests();self.f.setUp();self.f.raw()
    def tearDown(self):self.f.tearDown()
    def inputs(self,**kwargs):
        produced=self.f.evaluate(**kwargs);days=[]
        for day in self.f.source['days']:
            pop=self.f.pop[day['anchor']];descriptors=self.f.inventory['days'][len(days)]['predictions']
            days.append(dict(anchor=day['anchor'],queries=pop['queries'],calendar_maturity=pop['calendar_maturity'],
                group=pop['candidate_group'],items=pop['candidate_items'],
                scores={role:self.f.saved[descriptors[role]['artifact']['path']]['scores'] for role in ('B','W')}))
        return dict(days=days,produced_targets=produced['private_targets'],produced_periods=produced['periods'])
    def test_independent_source_and_all_report_values_match_production_synthetic_gold(self):
        result=a.audit_windows(self.f.con,**self.inputs())
        self.assertEqual(result['fullY_pairs'],6);self.assertEqual(result['private_targets']['a'],frozenset({fixtures.BIG+1,999}))
        self.assertEqual(result['periods']['final26_31_frozen']['metrics']['B']['conditional_macro_query']['ndcg'],.75)
        self.assertEqual(result['fit_attempt_count'],0);self.assertEqual(result['native_prediction_count'],0)
    def test_independent_literal_AP_denominator_and_exact_tie_rank(self):
        full=frozenset(range(30));ordered=[100,5,101,7]
        values=a.query_values(ordered,full)
        self.assertAlmostEqual(values['recall'],2/30);self.assertAlmostEqual(values['average_precision'],(1/2+2/4)/30)
        ideal=sum(1/math.log2(rank+1) for rank in range(1,21))
        self.assertAlmostEqual(values['ndcg'],(1/math.log2(3)+1/math.log2(5))/ideal)
        self.assertEqual(values['reciprocal_rank'],.5)
    def test_every_200_literal_user_draw_checks_conditional_and_all_query_vs_user(self):
        result=a.audit_windows(self.f.con,**self.inputs())['periods']['final26_31_frozen']
        users=[fixtures.BIG+100,fixtures.BIG+101,fixtures.BIG+102,fixtures.BIG+103];rng=random.Random(2026);d=1/math.log2(3)
        for i in range(200):
            draw=rng.choices(users,k=4);n1,n2,n3,n4=[draw.count(u) for u in users]
            for estimand,denom,numer in [('conditional_macro_query',n1+2*n2+n4,-(1-d)*n2),
                    ('all_query_zero',n1+2*n2+n3+n4,-(1-d)*n2),
                    ('conditional_user_macro',n1+n2+n4,-(1-d)*n2/2),('all_user_macro_zero',n1+n2+n3+n4,-(1-d)*n2/2)]:
                actual=result['paired_user_bootstrap'][estimand]['samples'][i]
                if denom:self.assertAlmostEqual(actual,numer/denom,places=12)
                else:self.assertIsNone(actual)
    def test_wrong_outside_C_target_rejects(self):
        inputs=self.inputs();inputs['produced_targets']['a']=frozenset({fixtures.BIG+1})
        with self.assertRaisesRegex(ValueError,'raw fullY mismatch'):a.audit_windows(self.f.con,**inputs)
    def test_same_connection_retry_does_not_repeat_original_target_oracle(self):
        inputs=self.inputs();a.audit_windows(self.f.con,**inputs)
        with self.assertRaises(fixtures.duckdb.CatalogException):a.audit_windows(self.f.con,**inputs)
    def test_corrupt_saved_bootstrap_draw_rejects(self):
        inputs=self.inputs();inputs['produced_periods']['final26_31_frozen']['paired_user_bootstrap']['all_user_macro_zero']['samples']=list(inputs['produced_periods']['final26_31_frozen']['paired_user_bootstrap']['all_user_macro_zero']['samples'])
        inputs['produced_periods']['final26_31_frozen']['paired_user_bootstrap']['all_user_macro_zero']['samples'][0]=999.0
        with self.assertRaisesRegex(ValueError,'numeric mismatch'):a.audit_windows(self.f.con,**inputs)
    def test_score_reordering_detected_against_produced_unchanged_claim(self):
        inputs=self.inputs();inputs['days'][0]['scores']['W']=np.asarray([1.,0.])
        with self.assertRaisesRegex(ValueError,'numeric mismatch'):a.audit_windows(self.f.con,**inputs)
    def test_zero_Y_empty_C_and_zero_Q_have_explicit_undefined_or_zero_estimands(self):
        self.f.con.execute('DELETE FROM heldout_raw_events');inputs=self.inputs();result=a.audit_windows(self.f.con,**inputs)
        for period in result['periods'].values():
            self.assertIsNone(period['metrics']['B']['conditional_macro_query']['ndcg'])
            self.assertEqual(period['metrics']['B']['all_query_zero']['ndcg'],0)
            self.assertEqual(period['paired_user_bootstrap']['conditional_macro_query']['undefined_draws'],200)
    def test_empty_all_seven_days_are_not_omitted(self):
        self.f.configure(empty=True);result=a.audit_windows(self.f.con,**self.inputs())
        self.assertEqual(result['fullY_pairs'],0)
        for period in result['periods'].values():self.assertEqual(period['paired_user_bootstrap']['all_query_zero']['undefined_draws'],200)
    def test_identical_models_are_transparent_zero_without_an_extra_model(self):
        self.f.configure('B');result=a.audit_windows(self.f.con,**self.inputs())
        for period in result['periods'].values():self.assertTrue(all(value==0 for value in period['ndcg_W_minus_B'].values()))
    def test_last_day_wrong_score_precision_rejects_before_own_raw_Y(self):
        inputs=self.inputs();inputs['days'][-1]['scores']['W']=np.asarray([0.],dtype=np.float32)
        with self.assertRaisesRegex(ValueError,'typed vector'):a.audit_windows(self.f.con,**inputs)
        self.assertNotIn('heldout_metric_queries',{row[0] for row in self.f.con.execute('SHOW TABLES').fetchall()})
    def test_wrong_calendar_float_or_duplicate_ID_and_target_tuple_reject_before_own_raw_Y(self):
        original=self.inputs()
        for mode in ['calendar','float','duplicate','tuple']:
            inputs=deepcopy(original);day=inputs['days'][0]
            if mode=='calendar':day['calendar_maturity'][0]=False
            elif mode=='float':day['items']=day['items'].astype(np.float64)
            elif mode=='duplicate':day['items'][1]=day['items'][0]
            else:day['queries'][0]=(*day['queries'][0],frozenset({7}))
            with self.subTest(mode=mode),self.assertRaises(ValueError):a.audit_windows(self.f.con,**inputs)
            self.assertNotIn('heldout_metric_queries',{row[0] for row in self.f.con.execute('SHOW TABLES').fetchall()})
    def test_missing_zero_Y_query_and_non_int_target_reject_before_own_source(self):
        original=self.inputs()
        for mode in ['missing','float']:
            inputs=deepcopy(original)
            if mode=='missing':inputs['produced_targets'].pop('e')
            else:inputs['produced_targets']['e']=frozenset({7.0})
            with self.subTest(mode=mode),self.assertRaises(ValueError):a.audit_windows(self.f.con,**inputs)
            self.assertNotIn('heldout_metric_queries',{row[0] for row in self.f.con.execute('SHOW TABLES').fetchall()})
    def test_exact_BIGINT_equal_score_tie_has_literal_hand_derived_NDCG(self):
        for descriptor in self.f.inventory['days'][0]['predictions'].values():self.f.saved[descriptor['artifact']['path']]['scores'][:]=0
        first=a.audit_windows(self.f.con,**self.inputs())['periods']['confirmation25_reporting_only']
        discount=1/math.log2(3)
        for role in ('B','W'):
            self.assertAlmostEqual(first['metrics'][role]['conditional_macro_query']['ndcg'],discount/(1+discount),places=14)
            self.assertEqual(first['metrics'][role]['conditional_macro_query']['recall'],.5)
    def test_input_snapshots_and_source_free_no_production_metric_or_file_API(self):
        inputs=self.inputs();before=deepcopy(inputs['produced_periods'])
        with patch('builtins.open',side_effect=AssertionError('No file API')),patch('io.open',side_effect=AssertionError('No path API')):
            a.audit_windows(self.f.con,**inputs)
        self.assertEqual(before,inputs['produced_periods'])
        import inspect
        tree=ast.parse(inspect.getsource(a))
        names=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
        names += [alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names]
        self.assertEqual(set(names),{'copy','datetime','math','random','numpy'})
    def test_guard_failure_and_terminal_Q_swap_reject(self):
        inputs=self.inputs()
        with self.assertRaises(TimeoutError):a.audit_windows(self.f.con,**inputs,check=lambda:(_ for _ in ()).throw(TimeoutError('stop')))
        old=a.compare;done=False
        def compare(*args,**kwargs):
            nonlocal done
            value=old(*args,**kwargs);done=True;return value
        def check():
            if done:self.f.con.execute("UPDATE heldout_metric_queries SET user_id=7 WHERE query_id='a'")
        with patch.object(a,'compare',compare),self.assertRaisesRegex(ValueError,'staged Q'):a.audit_windows(self.f.con,**inputs,check=check)
    def test_output_shape_types_extra_keys_and_nonfinite_values_fail_closed(self):
        expected={'samples':(1.,None),'count':2}
        for actual in [{'samples':(1.,None),'count':True},{'samples':(float('nan'),None),'count':2},
                {'samples':(1.,None),'count':2,'extra':0},{'samples':(1.,),'count':2}]:
            with self.subTest(actual=actual),self.assertRaises(ValueError):a.compare(actual,expected)
        a.compare({'samples':[1.,None],'count':2},expected)

if __name__=='__main__':unittest.main()
