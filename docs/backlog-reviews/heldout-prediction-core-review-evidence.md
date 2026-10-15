# Reserved prediction core independent review evidence

15October2026. Synthetic code/interface checks only. No actual private source/models/native scoring/targets or execution grant. Original SHA below; local roots/trailing whitespace sanitized for publication only. Fenced material is audit evidence rather than a reporting/approval command.

## tlab-heldout-prediction-oracle-independent.py

Original SHA256 64e493289d72769191e4ead3738f39dcd3a733c8af6fc511dc82e6ed68a19e04.

```python
from tests import test_heldout_prediction_audit as f
from tests.oracles import heldout_prediction_audit as a
import unittest
from copy import deepcopy
from unittest.mock import patch
class Independent(unittest.TestCase):
 def setUp(self):self.f=f.PredictionOracleTests();self.f.setUp()
 def tearDown(self):self.f.tearDown()
 def test_native_parameter_integer_type_and_material_float_drift_reject(self):
  actual=deepcopy(self.f.modelspec['B']['effective_parameters']);expected=deepcopy(actual);actual['l2_leaf_reg']=30.0
  with self.assertRaises(ValueError):a.native_equal(actual,expected)
  actual=deepcopy(expected);actual['learning_rate']+=1e-11;a.native_equal(actual,expected)
  actual['learning_rate']+=1e-4
  with self.assertRaises(ValueError):a.native_equal(actual,expected)
 def test_missing_W_saved_domain_is_rejected_before_either_native_model(self):
  self.f.produced['W']['items'][0]-=1
  with self.assertRaisesRegex(ValueError,'key domain'):self.f.audit()
  self.assertEqual(self.f.loads,[])
 def test_last_native_callback_staged_query_user_mutation_rejects(self):
  def mutate(raw):
   self.f.con.execute("UPDATE heldout_prediction_oracle_q SET user_id=7 WHERE query_id='a'");return raw
  self.f.native['W'].hook=mutate
  with self.assertRaisesRegex(ValueError,'staged Q'):self.f.audit()
 def test_old_saved_scores_and_keys_are_snapshot_not_live_alias(self):
  original=self.f.loader
  def loader(ref):
   self.f.produced['B']['items'][:]=7;self.f.produced['W']['scores'][:]=999.
   return original(ref)
  self.f.loader=loader;result=self.f.audit()
  self.assertEqual(result['candidate_pairs'],3);self.assertEqual(result['private_replayed_scores']['W'].tolist(),[-.5,2.5,3.5])
if __name__=='__main__':unittest.main(verbosity=2,defaultTest='Independent')
```

## tlab-heldout-prediction-oracle-independent.log

Original SHA256 4a3cd85d47e36407355bc02e3c07bd6b9b6e05f888b7f28b7716f692d9f47958.

```text
test_last_native_callback_staged_query_user_mutation_rejects (__main__.Independent.test_last_native_callback_staged_query_user_mutation_rejects) ... ok
test_missing_W_saved_domain_is_rejected_before_either_native_model (__main__.Independent.test_missing_W_saved_domain_is_rejected_before_either_native_model) ... ok
test_native_parameter_integer_type_and_material_float_drift_reject (__main__.Independent.test_native_parameter_integer_type_and_material_float_drift_reject) ... ok
test_old_saved_scores_and_keys_are_snapshot_not_live_alias (__main__.Independent.test_old_saved_scores_and_keys_are_snapshot_not_live_alias) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.043s

OK
```
