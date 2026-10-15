# Label-blind prediction core: original fault and final rereview evidence

15 October 2026. Tiny synthetic interface checks only; no actual source/CBM/native prediction/heldout target or execution policy. Initial red and final30 unique methods are preserved. Temporary/local roots are sanitized for publication only; original file SHA values below. Fenced material is audit evidence rather than a runtime command.

## tlab-heldout-predictions-own-probes.py

Original SHA256 d043ce871a41ca04b2413f1b9a5c146648016ccd369a79505b53ce5c3f7a2276.

```python
"""Read-only frozen core faults, arrays/fake models only; no native ML/file IO."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,'<repository>')
from tests.test_heldout_predictions import FrozenPredictionTests
from scripts import heldout_predictions as m
ROOT=Path('<repository>')
FREEZE=json.loads(Path('<temporary>/tlab-heldout-predictions-freeze-v2.json').read_text())

class Independent(unittest.TestCase):
 def setUp(self):
  self.fixture=FrozenPredictionTests('test_exact_raw_prefix_thread2_bigint_and_no_labels');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
 def mutate_during_predict(self,mode):
  f=self.fixture;f.reset('B');loaded=[]
  f.data_hook=lambda data,n:loaded.append(data)
  def predict(raw):
   data=loaded[-1]
   if mode=='valid_key':data.items[1]=data.items[1]+1
   elif mode=='duplicate_key':data.items[1]=data.items[0]
   elif mode=='group':data.group[0]=2
   elif mode=='target_tuple':data.queries[0]=(*data.queries[0],frozenset({7}))
   return raw
  f.models['B'].hook=predict
  return f.run_core()
 def test_valid_key_substitution_during_predict_must_not_reassociate_scores(self):
  with self.assertRaises(ValueError):self.mutate_during_predict('valid_key')
 def test_duplicate_keys_during_predict_must_not_return_success(self):
  with self.assertRaises(ValueError):self.mutate_during_predict('duplicate_key')
 def test_group_or_target_tuple_during_predict_must_not_return_success(self):
  for mode in ('group','target_tuple'):
   with self.subTest(mode=mode),self.assertRaises(ValueError):self.mutate_during_predict(mode)
 def test_final_output_owns_copied_keys_and_scores(self):
  f=self.fixture;f.reset('B');held=[];f.data_hook=lambda d,n:held.append(d)
  out=f.run_core()['predictions']['B'];before=(out.items.copy(),deepcopy(out.queries),out.scores.copy())
  held[0].items[:]=0;held[0].queries.clear();held[0].x[:]=999
  np.testing.assert_array_equal(out.items,before[0]);self.assertEqual(out.queries,before[1]);np.testing.assert_array_equal(out.scores,before[2])
 def test_embedding_rejected_before_predict_and_typed_user_rejected(self):
  f=self.fixture;f.models['B'].get_embedding_feature_indices=lambda:[0]
  with self.assertRaises(ValueError):f.run_core()
  self.assertFalse(f.models['B'].calls);self.assertFalse(f.data_calls)
  f.reset();f.data_hook=lambda d,n:d.queries.__setitem__(0,(d.queries[0][0],True,d.queries[0][2]))
  with self.assertRaises(ValueError):f.run_core()
  self.assertFalse(f.models['B'].calls)
 def test_only_learning_rate_native_serialization_tolerance(self):
  f=self.fixture;f.lock['models']['B']['effective_parameters']['arbitrary_float']=.1;f.choice['models']=deepcopy(f.lock['models'])
  f.models['B'].params['arbitrary_float']=.1+1e-9
  with self.assertRaises(ValueError):f.run_core()
  self.assertFalse(f.models['B'].calls)

if __name__=='__main__':
 before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FREEZE};assert before==FREEZE
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
 after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FREEZE};assert after==FREEZE
 Path('<temporary>/tlab-heldout-predictions-own-probe-results.json').write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),before=before,after=after,fit_attempt_count=0,native_predictions=0,actual_artifacts_opened=0),indent=2)+'\n')
 raise SystemExit(0 if result.wasSuccessful() else 1)
```

## tlab-heldout-predictions-own-probes.log

Original SHA256 87507f4838afe5396cc17c8638e2a7c065c021df60061d2bf3bbf6a2cc4f35a9.

```text
test_duplicate_keys_during_predict_must_not_return_success (__main__.Independent.test_duplicate_keys_during_predict_must_not_return_success) ... FAIL
test_embedding_rejected_before_predict_and_typed_user_rejected (__main__.Independent.test_embedding_rejected_before_predict_and_typed_user_rejected) ... ok
test_final_output_owns_copied_keys_and_scores (__main__.Independent.test_final_output_owns_copied_keys_and_scores) ... ok
test_group_or_target_tuple_during_predict_must_not_return_success (__main__.Independent.test_group_or_target_tuple_during_predict_must_not_return_success) ...
  test_group_or_target_tuple_during_predict_must_not_return_success (__main__.Independent.test_group_or_target_tuple_during_predict_must_not_return_success) (mode='group') ... FAIL
  test_group_or_target_tuple_during_predict_must_not_return_success (__main__.Independent.test_group_or_target_tuple_during_predict_must_not_return_success) (mode='target_tuple') ... FAIL
test_only_learning_rate_native_serialization_tolerance (__main__.Independent.test_only_learning_rate_native_serialization_tolerance) ... ok
test_valid_key_substitution_during_predict_must_not_reassociate_scores (__main__.Independent.test_valid_key_substitution_during_predict_must_not_reassociate_scores) ... FAIL

======================================================================
FAIL: test_duplicate_keys_during_predict_must_not_return_success (__main__.Independent.test_duplicate_keys_during_predict_must_not_return_success)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-predictions-own-probes.py", line 33, in test_duplicate_keys_during_predict_must_not_return_success
    with self.assertRaises(ValueError):self.mutate_during_predict('duplicate_key')
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_group_or_target_tuple_during_predict_must_not_return_success (__main__.Independent.test_group_or_target_tuple_during_predict_must_not_return_success) (mode='group')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-predictions-own-probes.py", line 36, in test_group_or_target_tuple_during_predict_must_not_return_success
    with self.subTest(mode=mode),self.assertRaises(ValueError):self.mutate_during_predict(mode)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_group_or_target_tuple_during_predict_must_not_return_success (__main__.Independent.test_group_or_target_tuple_during_predict_must_not_return_success) (mode='target_tuple')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-predictions-own-probes.py", line 36, in test_group_or_target_tuple_during_predict_must_not_return_success
    with self.subTest(mode=mode),self.assertRaises(ValueError):self.mutate_during_predict(mode)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_valid_key_substitution_during_predict_must_not_reassociate_scores (__main__.Independent.test_valid_key_substitution_during_predict_must_not_reassociate_scores)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-predictions-own-probes.py", line 31, in test_valid_key_substitution_during_predict_must_not_reassociate_scores
    with self.assertRaises(ValueError):self.mutate_during_predict('valid_key')
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 6 tests in 0.009s

FAILED (failures=4)
```

## tlab-heldout-predictions-own-probe-results.json

Original SHA256 7c5842ed177be4b11ea5aea22ec7fd0dcc4b5bf2225705dad5b7ff0227862124.

```text
{
  "tests": 6,
  "failures": 4,
  "errors": 0,
  "before": {
    "docs/experiments/heldout-predictions.md": "ce970986016914c5b5d82d45ac8a674df7d9a6dbdde5accbb6f95ec90f26af16",
    "scripts/heldout_predictions.py": "79a35bb01b71866141503e8409f91739141dc532c4c0d0c1d202d52182e794b0",
    "tests/test_heldout_predictions.py": "04dab781e2a5638c255d68d5dffaeef94d398938ef54d467de9ec93057602e4f"
  },
  "after": {
    "docs/experiments/heldout-predictions.md": "ce970986016914c5b5d82d45ac8a674df7d9a6dbdde5accbb6f95ec90f26af16",
    "scripts/heldout_predictions.py": "79a35bb01b71866141503e8409f91739141dc532c4c0d0c1d202d52182e794b0",
    "tests/test_heldout_predictions.py": "04dab781e2a5638c255d68d5dffaeef94d398938ef54d467de9ec93057602e4f"
  },
  "fit_attempt_count": 0,
  "native_predictions": 0,
  "actual_artifacts_opened": 0
}
```

## tlab-heldout-predictions-own-probes-v3-original-replay.py

Original SHA256 8015e394ff0708dcbd76a10437b5e07a83c10446b8e9abb924ea83256455149b.

```python
"""Read-only frozen core faults, arrays/fake models only; no native ML/file IO."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,'<repository>')
from tests.test_heldout_predictions import FrozenPredictionTests
from scripts import heldout_predictions as m
ROOT=Path('<repository>')
FREEZE=json.loads(Path('<temporary>/tlab-heldout-predictions-freeze-v3.json').read_text())

class Independent(unittest.TestCase):
 def setUp(self):
  self.fixture=FrozenPredictionTests('test_exact_raw_prefix_thread2_bigint_and_no_labels');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
 def mutate_during_predict(self,mode):
  f=self.fixture;f.reset('B');loaded=[]
  f.data_hook=lambda data,n:loaded.append(data)
  def predict(raw):
   data=loaded[-1]
   if mode=='valid_key':data.items[1]=data.items[1]+1
   elif mode=='duplicate_key':data.items[1]=data.items[0]
   elif mode=='group':data.group[0]=2
   elif mode=='target_tuple':data.queries[0]=(*data.queries[0],frozenset({7}))
   return raw
  f.models['B'].hook=predict
  return f.run_core()
 def test_valid_key_substitution_during_predict_must_not_reassociate_scores(self):
  with self.assertRaises(ValueError):self.mutate_during_predict('valid_key')
 def test_duplicate_keys_during_predict_must_not_return_success(self):
  with self.assertRaises(ValueError):self.mutate_during_predict('duplicate_key')
 def test_group_or_target_tuple_during_predict_must_not_return_success(self):
  for mode in ('group','target_tuple'):
   with self.subTest(mode=mode),self.assertRaises(ValueError):self.mutate_during_predict(mode)
 def test_final_output_owns_copied_keys_and_scores(self):
  f=self.fixture;f.reset('B');held=[];f.data_hook=lambda d,n:held.append(d)
  out=f.run_core()['predictions']['B'];before=(out.items.copy(),deepcopy(out.queries),out.scores.copy())
  held[0].items[:]=0;held[0].queries.clear();held[0].x[:]=999
  np.testing.assert_array_equal(out.items,before[0]);self.assertEqual(out.queries,before[1]);np.testing.assert_array_equal(out.scores,before[2])
 def test_embedding_rejected_before_predict_and_typed_user_rejected(self):
  f=self.fixture;f.models['B'].get_embedding_feature_indices=lambda:[0]
  with self.assertRaises(ValueError):f.run_core()
  self.assertFalse(f.models['B'].calls);self.assertFalse(f.data_calls)
  f.reset();f.data_hook=lambda d,n:d.queries.__setitem__(0,(d.queries[0][0],True,d.queries[0][2]))
  with self.assertRaises(ValueError):f.run_core()
  self.assertFalse(f.models['B'].calls)
 def test_only_learning_rate_native_serialization_tolerance(self):
  f=self.fixture;f.lock['models']['B']['effective_parameters']['arbitrary_float']=.1;f.choice['models']=deepcopy(f.lock['models'])
  f.models['B'].params['arbitrary_float']=.1+1e-9
  with self.assertRaises(ValueError):f.run_core()
  self.assertFalse(f.models['B'].calls)

if __name__=='__main__':
 before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FREEZE};assert before==FREEZE
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
 after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FREEZE};assert after==FREEZE
 Path('<temporary>/tlab-heldout-predictions-own-probe-results.json').write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),before=before,after=after,fit_attempt_count=0,native_predictions=0,actual_artifacts_opened=0),indent=2)+'\n')
 raise SystemExit(0 if result.wasSuccessful() else 1)
```

## tlab-heldout-predictions-v3-rereview-probes.py

Original SHA256 1cb14c8f6efd45f8ba4748f72ebb1bd38121951784a2428aadaae897457bedf2.

```python
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys
import unittest
import numpy as np
sys.path.insert(0,'<repository>')
from tests.test_heldout_predictions import FrozenPredictionTests
from scripts import heldout_predictions as m
p=importlib.util.spec_from_file_location('unchanged_original_tests','<temporary>/tlab-heldout-predictions-own-probes-v3-original-replay.py')
original=importlib.util.module_from_spec(p);p.loader.exec_module(original)

class Fresh(unittest.TestCase):
 def setUp(self):
  self.f=FrozenPredictionTests('test_exact_raw_prefix_thread2_bigint_and_no_labels');self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.f.reset('B');self.held=[];self.f.data_hook=lambda d,n:self.held.append(d)
 def test_finite_matrix_value_mutation_detected_before_success(self):
  def mutate(scores):self.held[0].x[0,1]=123.;return scores
  self.f.models['B'].hook=mutate
  with self.assertRaisesRegex(ValueError,'Feature matrix changed'):self.f.run_core()
 def test_preparation_mutation_detected_before_success(self):
  def mutate(scores):self.held[0].preparation['outcome_relations_opened']=1;return scores
  self.f.models['B'].hook=mutate
  with self.assertRaisesRegex(ValueError,'snapshot changed'):self.f.run_core()
 def test_calendar_mutation_detected_before_success(self):
  def mutate(scores):self.held[0].calendar_maturity[0]=False;return scores
  self.f.models['B'].hook=mutate
  with self.assertRaises(ValueError):self.f.run_core()
 def test_strided_and_empty_matrix_witness_literal_bytes_and_guards(self):
  x=np.array([[1.,2.],[3.,4.]],dtype=np.float32)[:,::-1];calls=[]
  expected=hashlib.sha256(struct.pack('<4f',2.,1.,4.,3.)).hexdigest()
  self.assertEqual(m._matrix_witness(x,lambda:calls.append(1)),expected);self.assertGreaterEqual(len(calls),2)
  self.assertEqual(m._matrix_witness(np.empty((0,44),np.float32),lambda:None),hashlib.sha256(b'').hexdigest())
  with self.assertRaises(TimeoutError):m._matrix_witness(x,lambda:(_ for _ in ()).throw(TimeoutError('stop')))

if __name__=='__main__':
 root=Path('<repository>');f=json.loads(Path('<temporary>/tlab-heldout-predictions-freeze-v3.json').read_text())
 before={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in f};assert before==f
 suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(original.Independent),unittest.defaultTestLoader.loadTestsFromTestCase(Fresh)])
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 after={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in f};assert after==f
 Path('<temporary>/tlab-heldout-predictions-own-probe-results-v3.json').write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),before=before,after=after,fit_attempt_count=0,native_predictions=0,actual_artifacts_opened=0),indent=2)+'\n')
 raise SystemExit(0 if result.wasSuccessful() else 1)
```

## tlab-heldout-predictions-own-probes-v3.log

Original SHA256 5c3241cb1e02127779e9b95fd57be8cf8db0d83b282d9e5ddf4a28f3ae50f3f0.

```text
test_duplicate_keys_during_predict_must_not_return_success (unchanged_original_tests.Independent.test_duplicate_keys_during_predict_must_not_return_success) ... ok
test_embedding_rejected_before_predict_and_typed_user_rejected (unchanged_original_tests.Independent.test_embedding_rejected_before_predict_and_typed_user_rejected) ... ok
test_final_output_owns_copied_keys_and_scores (unchanged_original_tests.Independent.test_final_output_owns_copied_keys_and_scores) ... ok
test_group_or_target_tuple_during_predict_must_not_return_success (unchanged_original_tests.Independent.test_group_or_target_tuple_during_predict_must_not_return_success) ... ok
test_only_learning_rate_native_serialization_tolerance (unchanged_original_tests.Independent.test_only_learning_rate_native_serialization_tolerance) ... ok
test_valid_key_substitution_during_predict_must_not_reassociate_scores (unchanged_original_tests.Independent.test_valid_key_substitution_during_predict_must_not_reassociate_scores) ... ok
test_calendar_mutation_detected_before_success (__main__.Fresh.test_calendar_mutation_detected_before_success) ... ok
test_finite_matrix_value_mutation_detected_before_success (__main__.Fresh.test_finite_matrix_value_mutation_detected_before_success) ... ok
test_preparation_mutation_detected_before_success (__main__.Fresh.test_preparation_mutation_detected_before_success) ... ok
test_strided_and_empty_matrix_witness_literal_bytes_and_guards (__main__.Fresh.test_strided_and_empty_matrix_witness_literal_bytes_and_guards) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.015s

OK
```

## tlab-heldout-predictions-own-probe-results-v3.json

Original SHA256 22f97f9558699478aa743795de5e89df82e0e64cb20fa0ff9620fabd15284337.

```text
{
  "tests": 10,
  "failures": 0,
  "errors": 0,
  "before": {
    "docs/experiments/heldout-predictions.md": "82aefcedc06e48c7f6b7db3c2d65e112a2a53c505a0ca86d654ff7f47aec9845",
    "scripts/heldout_predictions.py": "e1b06b2aac68c59379d15298c39101ec02b6a176c26b13d4671f8e445de2851b",
    "tests/test_heldout_predictions.py": "4b3579c32a453cb6cf67260222ff3374836f5fe3e85df69b9b261da3232b2bd8"
  },
  "after": {
    "docs/experiments/heldout-predictions.md": "82aefcedc06e48c7f6b7db3c2d65e112a2a53c505a0ca86d654ff7f47aec9845",
    "scripts/heldout_predictions.py": "e1b06b2aac68c59379d15298c39101ec02b6a176c26b13d4671f8e445de2851b",
    "tests/test_heldout_predictions.py": "4b3579c32a453cb6cf67260222ff3374836f5fe3e85df69b9b261da3232b2bd8"
  },
  "fit_attempt_count": 0,
  "native_predictions": 0,
  "actual_artifacts_opened": 0
}
```
