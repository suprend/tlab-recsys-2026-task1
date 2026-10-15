from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch
import importlib.util,unittest
spec=importlib.util.spec_from_file_location('old','/tmp/tlab-heldout-owner-independent-v1-valid-scope.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
m=old.m
class Fresh(unittest.TestCase):
 def test_full_R2_inventory_two_calls_and_output_ref_exact(self):
  c=old.PredictionBoundary('test_legal_complete_fixture_reaches_REAL_inventory_contract');c.setUp();self.addCleanup(c.doCleanups)
  c.lock,_,inv,c.source,*_=old.fixture('R2');c.prepared={'lock':c.lock,'plan':{'choice':'R2'}}
  c.produced.update(source_acceptance=c.source['acceptance'],days=deepcopy(inv['days']),native_prediction_count=10)
  c.core.update(native_prediction_count=10)
  for row,day in zip(c.core['days'],c.produced['days']):
   row['native_prediction_count']=2 if day['candidate_count'] else 0
   for side in ('B','W'):day['predictions'][side]['artifact']=old.r('predictions/day-'+day['anchor'][8:10]+'/'+side+'.npz')
  with patch.object(m,'role_receipt',return_value={'native_prediction_count':10}):result=c.verify()
  self.assertEqual(result[0]['days'][2]['predictions']['W']['feature_names'],c.lock['models']['W']['feature_names']);self.assertEqual(len(c.written),2)
 def test_wrong_daily_scope_rejects_before_any_persistence(self):
  c=old.PredictionBoundary('test_legal_complete_fixture_reaches_REAL_inventory_contract');c.setUp();self.addCleanup(c.doCleanups)
  c.core['days'][-1]['proof_scope']='other_unsupported_proof'
  with self.assertRaises(ValueError):c.verify()
  self.assertEqual(c.written,[])
if __name__=='__main__':unittest.main(verbosity=2)
