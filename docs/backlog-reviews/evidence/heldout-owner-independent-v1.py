from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from scripts import run_heldout_reporting as m
from tests.test_heldout_contract import fixture,r
class PredictionBoundary(unittest.TestCase):
 def setUp(self):
  self.lock,_,inv,self.source,*_=fixture('B')
  self.prepared={'lock':self.lock,'plan':{'choice':'B'}}
  self.manifest=r('source-manifest.json');self.produced={'source_acceptance':self.source['acceptance'],'source_manifest':self.manifest,'created_at':inv['created_at'],'days':deepcopy(inv['days']),'native_prediction_count':5}
  self.session=SimpleNamespace(plan={'run_id':'a'*64,'fingerprints':{}},directory=Path('/tmp/toy'),states=[{'role':role,'receipt':r(role+'-receipt.json')} for role in ('predictions','prediction_oracle')],authority_pins={})
  self.core=dict(status='independent_all_seven_scores_match_pending_owner_acceptance',days=[],native_prediction_count=5,fit_attempt_count=0,labels_loaded=False,proof_scope='all7_independent_matrix_native_scores_rank_order_with_external_byte_lifetime_authority')
  for day in self.produced['days']:
   for side in ('B','W'):day['predictions'][side]['artifact']=r('predictions/day-'+day['anchor'][8:10]+'/B.npz')
   self.core['days'].append(dict(status='independent_daily_scores_match_pending_all_date_and_owner_acceptance',anchor=day['anchor'],queries=day['query_count'],candidate_pairs=day['candidate_count'],native_prediction_count=int(day['candidate_count']>0),fit_attempt_count=0,outcome_relations_opened=0,proof_scope='independent_Q_C_F_numeric_projection_native_state_all_rawscores_complete_rank_order_no_byte_or_lifetime_authentication'))
  self.written=[]
  self.stack=ExitStack();self.addCleanup(self.stack.close)
  patches={'unaccepted_manifest':lambda *a:(r('prediction-manifest.json'),deepcopy(self.produced)),'issued_for':lambda *a:dict(inputs={'source_acceptance':self.source['acceptance'],'source_manifest':self.manifest}),'role_receipt':lambda *a:{'native_prediction_count':5},'oracle_core':lambda *a:deepcopy(self.core),'role_output':lambda s,role,name:r(role+'/'+name),'closure':lambda *a:{},'now':lambda:'2026-10-15T13:00:00Z','write_once':self.writer}
  for name,value in patches.items():self.stack.enter_context(patch.object(m,name,value))
 def writer(self,directory,name,body):self.written.append((name,deepcopy(body)));return r(name)
 def verify(self):return m.finish_prediction_inventory(self.session,self.prepared,self.source,self.manifest)
 def test_legal_complete_fixture_reaches_REAL_inventory_contract(self):self.assertEqual(len(self.verify()[0]['days']),7)
 def test_failed_or_target_opened_top_proof_must_reject_before_inventory(self):
  self.core.update(status='failed',labels_loaded=True,fit_attempt_count=4,native_prediction_count=99,proof_scope='not_replayed')
  with self.assertRaises(ValueError):self.verify()
 def test_omitted_top_status_must_reject(self):
  self.core.pop('status')
  with self.assertRaises(ValueError):self.verify()
 def test_daily_extra_private_values_must_reject(self):
  self.core['days'][0]['private_targets']=['synthetic_only']
  with self.assertRaises(ValueError):self.verify()
 def test_bool_zero_query_count_must_reject(self):
  self.core['days'][0]['queries']=False
  with self.assertRaises(ValueError):self.verify()
if __name__=='__main__':unittest.main(verbosity=2)
