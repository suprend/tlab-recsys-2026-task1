from copy import deepcopy
import unittest
from scripts import heldout_contract as h


def r(name):return dict(path='artifacts/synthetic/'+name,sha256='a'*64)

def fixture(choice='I1'):
 names=['feature_'+str(i) for i in range(41)]
 b=dict(model=r('B.cbm'),feature_names=names,trained_iterations=300,scoring_prefix=300,population=26000,
        effective_parameters=dict(loss_function='Logloss',depth=6,l2_leaf_reg=30,iterations=300,task_type='CPU'))
 w=deepcopy(b)
 if choice!='B':w['model']=r('W.cbm');w['feature_names']+=['auto_1','auto_2','auto_3']
 auth={n:r(n+'.json') for n in ['control','automation','source','selector','pool']}
 c=dict(candidate_id=choice,models=dict(B=b,W=w),authority_refs=auth)
 lock=dict(version=1,scope='whole_reserved_decision_lock',policy=deepcopy(h.POLICY),choice=choice,models=deepcopy(c['models']),authority_refs=deepcopy(auth),
           code_refs=[r('code.py'),r('lockfile')],sealed_at='2026-10-15T12:00:00Z',heldout_targets_opened=False,
           simulated_clock=dict(maximum_used_label_maturity=h.MATURITY,declared_compute_allowance_seconds=43200,decision_available_at=h.DECISION_AVAILABLE),
           compute_evidence=[dict(stage=n,measured_active_wall_upper_seconds=100,declared_unmeasured_wall_upper_seconds=100,receipt=r(n+'.json')) for n in sorted(h.STAGES)])
 days=[]
 for k,day in enumerate(h.DAYS):
  # Empty Q and positive Q with empty C remain explicit days; maturity is calendar-only.
  q=0 if k==0 else 2;n=0 if k<2 else 3
  row=dict(anchor=day,queries=r(str(k)+'Q.parquet'),candidates=r(str(k)+'C.parquet'),base_features=r(str(k)+'F.parquet'),extra_features=None if choice=='B' else r(str(k)+'A.parquet'),query_count=q,candidate_count=n,mature_query_count=q)
  days.append(row)
 source=dict(acceptance=r('new-date-source.json'),days=deepcopy(days))
 inv=dict(version=1,scope='all_reserved_predictions_before_targets',decision_lock_sha256=h.digest(lock),created_at='2026-10-15T12:01:00Z',source_acceptance=source['acceptance'],days=days,
          output_verification=r('native-replay.json'),lifetime_receipt=r('lifetime.json'),heldout_targets_opened=False)
 for row in days:
  row['predictions']={n:dict(artifact=r(row['anchor'][:10]+'-'+n+'.npz'),model=lock['models'][n]['model'],rows=row['candidate_count'],queries=row['query_count'],scoring_prefix=300,feature_names=lock['models'][n]['feature_names']) for n in ['B','W']}
  if choice=='B':row['predictions']['W']=deepcopy(row['predictions']['B'])
 pa=dict(reference=r('all-predictions-accepted.json'),inventory_sha256=h.digest(inv),decision_lock_sha256=h.digest(lock))
 intent=dict(version=1,scope='report_only_reserved_fullY',prediction_acceptance=pa['reference'],prediction_inventory_sha256=pa['inventory_sha256'],decision_lock_sha256=pa['decision_lock_sha256'],opened_at='2026-10-15T12:02:00Z',periods=['confirmation25_reporting_only','final26_31_frozen'],no_adaptation=True)
 return lock,c,inv,source,intent,pa


class HeldoutContract(unittest.TestCase):
 def test_two_distinct_clocks_and_complete_empty_days(self):
  l,c,i,s,t,a=fixture();self.assertEqual(h.validate_lock(l,authenticated_choice=c),l)
  self.assertEqual(h.validate_prediction_inventory(i,l,authenticated_source=s),i)
  self.assertEqual(h.validate_target_intent(t,l,i,authenticated_prediction_acceptance=a),t)
  self.assertEqual(len(i['days']),7);self.assertEqual(i['days'][0]['query_count'],0);self.assertEqual(i['days'][1]['candidate_count'],0)
 def test_w_equal_b_reuses_exact_model_and_predictions(self):
  l,c,i,s,t,a=fixture('B');h.validate_lock(l,authenticated_choice=c);h.validate_prediction_inventory(i,l,authenticated_source=s)
  i['days'][0]['predictions']['W']['artifact']=r('different.npz')
  with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
 def test_no_fake_2019_physical_file_requirement(self):
  l,c,*_=fixture();self.assertEqual(h.utc(l['sealed_at']).year,2026);h.validate_lock(l,authenticated_choice=c)
 def test_original_calendar_and_midnight_no_compute_gap_rejected(self):
  for edit in ['calendar','available','zero']:
   l,c,*_=fixture()
   if edit=='calendar':l['policy']['confirmation']['start']='2019-10-24T00:00:00Z'
   elif edit=='available':l['simulated_clock']['decision_available_at']=h.MATURITY
   else:l['simulated_clock']['declared_compute_allowance_seconds']=0
   with self.assertRaises(ValueError):h.validate_lock(l,authenticated_choice=c)
 def test_wall_upper_not_cpu_substitution_or_missing_stage(self):
  for edit in ['CPU','missing','over','nan','duplicate']:
   l,c,*_=fixture()
   if edit=='CPU':l['compute_evidence'][0]['actual_cpu_seconds']=1
   elif edit=='missing':l['compute_evidence'].pop()
   elif edit=='over':l['compute_evidence'][0]['declared_unmeasured_wall_upper_seconds']=43201
   elif edit=='nan':l['compute_evidence'][0]['measured_active_wall_upper_seconds']=float('nan')
   else:l['compute_evidence'][0]['stage']=l['compute_evidence'][1]['stage']
   with self.assertRaises(ValueError):h.validate_lock(l,authenticated_choice=c)
 def test_saved_model_prefix_params_and_exact_extra_closure(self):
  for field,value in [('scoring_prefix',50),('trained_iterations',301),('population',6000),('feature_names',['bad']*44)]:
   l,c,*_=fixture();l['models']['W'][field]=value;c['models']['W'][field]=value
   with self.assertRaises(ValueError):h.validate_lock(l,authenticated_choice=c)
  l,c,*_=fixture();l['models']['W']['effective_parameters']['depth']=4;c['models']['W']['effective_parameters']['depth']=4
  with self.assertRaises(ValueError):h.validate_lock(l,authenticated_choice=c)
 def test_changed_choice_or_model_ref_after_independent_acceptance(self):
  l,c,*_=fixture();l['models']['W']['model']['sha256']='b'*64
  with self.assertRaises(ValueError):h.validate_lock(l,authenticated_choice=c)
 def test_missing_and_duplicate_or_outside_day_cannot_open_Y(self):
  for edit in ['missing','duplicate','outside']:
   l,c,i,s,*_=fixture()
   if edit=='missing':i['days'].pop()
   elif edit=='duplicate':i['days'][-1]=deepcopy(i['days'][0])
   else:i['days'][-1]['anchor']='2019-10-24T00:00:00Z'
   with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
 def test_authenticated_source_cannot_hide_duplicate_eighth_day(self):
  l,c,i,s,*_=fixture();s['days'].append(deepcopy(s['days'][0]))
  with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
 def test_oct31_full_horizon_maturity_cannot_be_self_asserted_censoring(self):
  l,c,i,s,*_=fixture();s['days'][-1]['mature_query_count']=0;i['days'][-1]['mature_query_count']=0
  with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
  i['days'][-1]['mature_query_count']=s['days'][-1]['mature_query_count']=2
  h.validate_prediction_inventory(i,l,authenticated_source=s)
 def test_day_domain_and_empty_C_queries_not_dropped(self):
  l,c,i,s,*_=fixture();i['days'][1]['predictions']['B']['queries']=0
  with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
  l,c,i,s,*_=fixture();i['days'][2]['query_count']=1
  with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
 def test_all_date_prediction_seal_before_even_confirmation_Y(self):
  for edit in ['equal','before','opened','late_predictions']:
   l,c,i,s,t,a=fixture()
   if edit=='equal':t['opened_at']=i['created_at']
   elif edit=='before':t['opened_at']=l['sealed_at']
   elif edit=='opened':i['heldout_targets_opened']=True
   else:i['created_at']='2026-10-15T11:59:00Z'
   with self.assertRaises(ValueError):
    h.validate_prediction_inventory(i,l,authenticated_source=s);h.validate_target_intent(t,l,i,authenticated_prediction_acceptance=a)
 def test_fresh_self_reseal_not_external_target_authority(self):
  l,c,i,s,t,a=fixture();i['days'][0]['predictions']['B']['artifact']=r('resealed.npz');t['prediction_inventory_sha256']=h.digest(i)
  with self.assertRaises(ValueError):h.validate_target_intent(t,l,i,authenticated_prediction_acceptance=a)
 def test_reporting_no_adaptation_and_no_period_sign_selection(self):
  for edit in ['period','adapt']:
   l,c,i,s,t,a=fixture()
   if edit=='period':t['periods']=['final26_31_frozen']
   else:t['no_adaptation']=False
   with self.assertRaises(ValueError):h.validate_target_intent(t,l,i,authenticated_prediction_acceptance=a)
 def test_bool_integer_alias_and_reference_path_escape(self):
  for name in ['version','population']:
   l,c,*_=fixture()
   if name=='version':l['version']=True
   else:l['models']['B']['population']=True;c['models']['B']['population']=True
   with self.assertRaises(ValueError):h.validate_lock(l,authenticated_choice=c)
  for name in ['/outside','artifacts/../private','artifacts//x','artifacts/./x']:
   with self.assertRaises(ValueError):h.ref(dict(path=name,sha256='a'*64))
 def test_validators_leave_inputs_unchanged_and_no_IO(self):
  from unittest.mock import patch
  l,c,i,s,t,a=fixture();before=deepcopy([l,c,i,s,t,a])
  with patch('builtins.open',side_effect=AssertionError('No files including Y may be opened')):
   h.validate_lock(l,authenticated_choice=c);h.validate_prediction_inventory(i,l,authenticated_source=s);h.validate_target_intent(t,l,i,authenticated_prediction_acceptance=a)
  self.assertEqual([l,c,i,s,t,a],before)

if __name__=='__main__':unittest.main()
