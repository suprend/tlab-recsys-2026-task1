# Independent recovered-source consumer output

Actual author11+independent4 unique tests; bounded actual metadata only, no full166-byte reauthentication.

```text
test_bool_version_and_approval_are_not_integer_authority (source_author.RecoveredSourceTests.test_bool_version_and_approval_are_not_integer_authority) ... ok
test_external_exit_tail_and_paid_prefix_cannot_reset (source_author.RecoveredSourceTests.test_external_exit_tail_and_paid_prefix_cannot_reset) ... ok
test_fresh_reseal_without_external_anchor_rejected (source_author.RecoveredSourceTests.test_fresh_reseal_without_external_anchor_rejected) ... ok
test_guard_and_nonlocal_pins_fail_before_data (source_author.RecoveredSourceTests.test_guard_and_nonlocal_pins_fail_before_data) ... ok
test_known_failure_precedes_large_pin_or_planner_work (source_author.RecoveredSourceTests.test_known_failure_precedes_large_pin_or_planner_work) ... ok
test_late_marker_rejected_after_hashing (source_author.RecoveredSourceTests.test_late_marker_rejected_after_hashing) ... ok
test_launch_context_issuer_binding_rejects_resealed_slot (source_author.RecoveredSourceTests.test_launch_context_issuer_binding_rejects_resealed_slot) ... ok
test_original_plan_binding_mismatch_rejected (source_author.RecoveredSourceTests.test_original_plan_binding_mismatch_rejected) ... ok
test_same_cardinality_missing_proof_pin_rejected (source_author.RecoveredSourceTests.test_same_cardinality_missing_proof_pin_rejected) ... ok
test_success_preserves_original_failure_and_returns_daily_only_without_source_materialization (source_author.RecoveredSourceTests.test_success_preserves_original_failure_and_returns_daily_only_without_source_materialization) ... ok
test_unpinned_changed_export_detected_without_formula_rerun (source_author.RecoveredSourceTests.test_unpinned_changed_export_detected_without_formula_rerun) ... ok
test_independent_changed_evidence_rejects_before_delegate (__main__.Independent.test_independent_changed_evidence_rejects_before_delegate) ... ok
test_independent_escaping_symlink_stops_before_streaming (__main__.Independent.test_independent_escaping_symlink_stops_before_streaming) ... ok
test_independent_first_streaming_guard_preserves_no_skip_contract (__main__.Independent.test_independent_first_streaming_guard_preserves_no_skip_contract) ... ok
test_independent_late_acceptance_mutation_cannot_return_accepted (__main__.Independent.test_independent_late_acceptance_mutation_cannot_return_accepted) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.159s

OK
ACTUAL_SMALL_GATE_PASS_before_paid107_plan;0largebytes;notfullverification
3_frozen_SHA_PASS
```
