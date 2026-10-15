# Reserved lifecycle core independent review evidence

15October2026. Synthetic code/interface checks only. No actual private source/models/native scoring/targets or execution grant. Original SHA below; local roots/trailing whitespace sanitized for publication only. Fenced material is audit evidence rather than a reporting/approval command.

## tlab-heldout-execution-independent.py

Original SHA256 d794e09a8acac80e57d20612a4e7d79b919979ed002deb7aa8c13093d2178e61.

```python
import importlib.util,unittest,json,hashlib
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('fixture','<temporary>/tlab-test-heldout_execution.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);m=f.m
class Independent(unittest.TestCase):
 def setUp(self):self.f=f.Lifecycle();self.f.setUp()
 def tearDown(self):self.f.tearDown()
 def test_finalizing_persistence_output_mutation_must_reject(self):
  self.f.all_roles();s=self.f.s;original=s.persist;changed=False
  def persist():
   nonlocal changed
   value=original()
   if s.report['status']=='finalizing' and not changed:
    m.local(self.f.root,next(iter(s.output_pins))).write_text('{"altered":true}\n');changed=True
   return value
  with patch.object(s,'persist',persist),self.assertRaises(ValueError):s.finish()
 def test_success_persistence_authority_mutation_must_reject(self):
  self.f.all_roles();s=self.f.s;original=s.persist;changed=False
  def persist():
   nonlocal changed
   value=original()
   if s.report['status']=='verified_reporting_pending_external_lifetime_acceptance' and not changed:
    m.local(self.f.root,s.gates['target_execution']['path']).write_text('{"altered":true}\n');changed=True
   return value
  with patch.object(s,'persist',persist),self.assertRaises(ValueError):s.finish()
 def test_last_guard_created_failure_marker_must_reject(self):
  self.f.all_roles();s=self.f.s;original=self.f.b.guard;changed=False
  def guard():
   nonlocal changed
   value=original()
   if s.report['status']=='verified_reporting_pending_external_lifetime_acceptance' and not changed:
    (s.directory/'report.failed.json').write_text('{}\n');changed=True
   return value
  with patch.object(self.f.b,'guard',guard),self.assertRaises(ValueError):s.finish()
 def test_missing_target_receipt_retains_unknown_target_opening(self):
  self.f.gate('initial_execution')
  for role in ['source','source_oracle']:self.f.complete(role)
  self.f.gate('source_acceptance')
  for role in ['predictions','prediction_oracle']:self.f.complete(role)
  self.f.gate('prediction_acceptance');self.f.gate('target_execution');self.f.issue('targets_evaluation')
  out=self.f.s.fail(OSError('lost'));self.assertTrue(out['reserved_targets_may_have_been_opened']);self.assertTrue(out['unknown_active_work']);self.assertEqual(out['active_role'],'targets_evaluation')
 def test_failed_child_descendant_and_cpu_association_reject(self):
  self.f.gate('initial_execution');issued=self.f.issue('source')
  with self.assertRaises(ValueError):self.f.accept(issued,lambda b:b.update(descendant_cpu_seconds=True))
 def test_invalid_gate_bool_version_rejected(self):
  body=dict(version=True,approved=True,scope='reserved_source_inference_execution',run_id=self.f.plan['run_id']);r=self.f.pin('authority/bad.json',body)
  with self.assertRaises(ValueError):self.f.s.record_gate('initial_execution',r,expected=body)
 def test_read_exponent_overflow_should_reject_nonfinite_json(self):
  p=self.f.root/'bad.json';p.write_text('{"x":1e999}\n')
  with self.assertRaises(ValueError):m.read(p)
if __name__=='__main__':
 freeze=json.loads(Path('<temporary>/tlab-heldout-execution-primitives-freeze-v1.json').read_text())
 for name,sha in freeze.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha
 unittest.main(verbosity=2,defaultTest='Independent')
```

## tlab-heldout-execution-independent-v1.log

Original SHA256 9f9d5379f09e90aa79d372a2f14e29b3aa194e1ed63895b1a99a944a31965b8c.

```text
test_failed_child_descendant_and_cpu_association_reject (__main__.Independent.test_failed_child_descendant_and_cpu_association_reject) ... ok
test_finalizing_persistence_output_mutation_must_reject (__main__.Independent.test_finalizing_persistence_output_mutation_must_reject) ... FAIL
test_invalid_gate_bool_version_rejected (__main__.Independent.test_invalid_gate_bool_version_rejected) ... ok
test_last_guard_created_failure_marker_must_reject (__main__.Independent.test_last_guard_created_failure_marker_must_reject) ... FAIL
test_missing_target_receipt_retains_unknown_target_opening (__main__.Independent.test_missing_target_receipt_retains_unknown_target_opening) ... ok
test_read_exponent_overflow_should_reject_nonfinite_json (__main__.Independent.test_read_exponent_overflow_should_reject_nonfinite_json) ... FAIL
test_success_persistence_authority_mutation_must_reject (__main__.Independent.test_success_persistence_authority_mutation_must_reject) ... FAIL

======================================================================
FAIL: test_finalizing_persistence_output_mutation_must_reject (__main__.Independent.test_finalizing_persistence_output_mutation_must_reject)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-execution-independent.py", line 16, in test_finalizing_persistence_output_mutation_must_reject
    with patch.object(s,'persist',persist),self.assertRaises(ValueError):s.finish()
                                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_last_guard_created_failure_marker_must_reject (__main__.Independent.test_last_guard_created_failure_marker_must_reject)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-execution-independent.py", line 34, in test_last_guard_created_failure_marker_must_reject
    with patch.object(self.f.b,'guard',guard),self.assertRaises(ValueError):s.finish()
                                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_read_exponent_overflow_should_reject_nonfinite_json (__main__.Independent.test_read_exponent_overflow_should_reject_nonfinite_json)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-execution-independent.py", line 50, in test_read_exponent_overflow_should_reject_nonfinite_json
    with self.assertRaises(ValueError):m.read(p)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_success_persistence_authority_mutation_must_reject (__main__.Independent.test_success_persistence_authority_mutation_must_reject)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-execution-independent.py", line 25, in test_success_persistence_authority_mutation_must_reject
    with patch.object(s,'persist',persist),self.assertRaises(ValueError):s.finish()
                                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 7 tests in 0.283s

FAILED (failures=4)
```

## tlab-heldout-execution-independent-v2.log

Original SHA256 024c0ea216fc983c2da5d176c6126d708235fe60861a1beecd23fdf67b96f150.

```text
test_failed_child_descendant_and_cpu_association_reject (__main__.Independent.test_failed_child_descendant_and_cpu_association_reject) ... ok
test_finalizing_persistence_output_mutation_must_reject (__main__.Independent.test_finalizing_persistence_output_mutation_must_reject) ... ok
test_invalid_gate_bool_version_rejected (__main__.Independent.test_invalid_gate_bool_version_rejected) ... ok
test_last_guard_created_failure_marker_must_reject (__main__.Independent.test_last_guard_created_failure_marker_must_reject) ... ok
test_missing_target_receipt_retains_unknown_target_opening (__main__.Independent.test_missing_target_receipt_retains_unknown_target_opening) ... ok
test_read_exponent_overflow_should_reject_nonfinite_json (__main__.Independent.test_read_exponent_overflow_should_reject_nonfinite_json) ... ok
test_success_persistence_authority_mutation_must_reject (__main__.Independent.test_success_persistence_authority_mutation_must_reject) ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.322s

OK
```

## tlab-heldout-execution-project-v3.log

Original SHA256 bb1ae153db471cf7f79ded92f987871122ea2b1eb465da81f22a41345d5b6cfb.

```text
test_W_equal_B_output_vocabulary_reuses_only_B (tests.test_heldout_execution.Lifecycle.test_W_equal_B_output_vocabulary_reuses_only_B) ... ok
test_all_roles_fixed_gates_final_unaccepted_boundary (tests.test_heldout_execution.Lifecycle.test_all_roles_fixed_gates_final_unaccepted_boundary) ... ok
test_bool_fit_count_is_not_integer_zero (tests.test_heldout_execution.Lifecycle.test_bool_fit_count_is_not_integer_zero) ... ok
test_budget_shared_cpu_actual_counters_and_reserves (tests.test_heldout_execution.Lifecycle.test_budget_shared_cpu_actual_counters_and_reserves) ... ok
test_caller_cannot_choose_an_arbitrary_pinned_script (tests.test_heldout_execution.Lifecycle.test_caller_cannot_choose_an_arbitrary_pinned_script) ... ok
test_changed_dynamic_gate_blocks_finalization (tests.test_heldout_execution.Lifecycle.test_changed_dynamic_gate_blocks_finalization) ... ok
test_changed_external_authority_rejects_before_next_role (tests.test_heldout_execution.Lifecycle.test_changed_external_authority_rejects_before_next_role) ... ok
test_consumption_exclusive_and_session_directory_retry_refused (tests.test_heldout_execution.Lifecycle.test_consumption_exclusive_and_session_directory_retry_refused) ... ok
test_execution_consumption_bool_version_rejected (tests.test_heldout_execution.Lifecycle.test_execution_consumption_bool_version_rejected) ... ok
test_false_child_label_state_or_fit_count_rejected (tests.test_heldout_execution.Lifecycle.test_false_child_label_state_or_fit_count_rejected) ... ok
test_gate_mutation_during_terminal_persistence_fails (tests.test_heldout_execution.Lifecycle.test_gate_mutation_during_terminal_persistence_fails) ... ok
test_initial_gate_absent_cannot_consume_source (tests.test_heldout_execution.Lifecycle.test_initial_gate_absent_cannot_consume_source) ... ok
test_issued_slot_context_and_launch_are_deepcopied_and_bound (tests.test_heldout_execution.Lifecycle.test_issued_slot_context_and_launch_are_deepcopied_and_bound) ... ok
test_label_reference_not_in_source_vocabulary (tests.test_heldout_execution.Lifecycle.test_label_reference_not_in_source_vocabulary) ... ok
test_last_resource_guard_cannot_create_unchecked_failure_marker (tests.test_heldout_execution.Lifecycle.test_last_resource_guard_cannot_create_unchecked_failure_marker) ... ok
test_late_role_marker_blocks_finalization_and_persists_failure (tests.test_heldout_execution.Lifecycle.test_late_role_marker_blocks_finalization_and_persists_failure) ... ok
test_metadata_exponent_overflow_is_rejected_inside_reader (tests.test_heldout_execution.Lifecycle.test_metadata_exponent_overflow_is_rejected_inside_reader) ... ok
test_missing_receipt_failure_retains_unknown_work_and_consumed_role (tests.test_heldout_execution.Lifecycle.test_missing_receipt_failure_retains_unknown_work_and_consumed_role) ... ok
test_no_role_skip_retry_or_target_before_prediction_seal (tests.test_heldout_execution.Lifecycle.test_no_role_skip_retry_or_target_before_prediction_seal) ... ok
test_omitted_output_fresh_receipt_rejected (tests.test_heldout_execution.Lifecycle.test_omitted_output_fresh_receipt_rejected) ... ok
test_output_mutation_during_finalizing_persistence_fails (tests.test_heldout_execution.Lifecycle.test_output_mutation_during_finalizing_persistence_fails) ... ok
test_symlink_escape_rejected (tests.test_heldout_execution.Lifecycle.test_symlink_escape_rejected) ... ok
test_unknown_cpu_and_parent_rss_fail_closed (tests.test_heldout_execution.Lifecycle.test_unknown_cpu_and_parent_rss_fail_closed) ... ok

----------------------------------------------------------------------
Ran 23 tests in 0.595s

OK
```
