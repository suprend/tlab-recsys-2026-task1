# Independent016 runner v1 output

Original SHA256 ada8510aa98f0c4487a52d93c954316978d9f06d19ae414bf436b900566d5a0b. Temporary traceback roots sanitized for publication; synthetic fixture source/assertions unchanged. No actual model/source execution.

```text
test_independent_failed_owner_reports_unknown_when_child_started_but_receipt_unavailable (__main__.WorkerAccounting.test_independent_failed_owner_reports_unknown_when_child_started_but_receipt_unavailable) ... {"approval_path":"approval.json","proposal":"artifacts/feature-program-invocations/114b203f8f7f4fc4b91d8b4ad2cc98b5/proposal.json","run_id":"350e4bc992013bd3c322f7f6ccdac1877e7461d8f6999a363dcf642be3b215b8","status":"awaiting_exact_execution_approval"}
FAIL

======================================================================
FAIL: test_independent_failed_owner_reports_unknown_when_child_started_but_receipt_unavailable (__main__.WorkerAccounting.test_independent_failed_owner_reports_unknown_when_child_started_but_receipt_unavailable)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab016-model-runner-additional-probes.py", line 16, in test_independent_failed_owner_reports_unknown_when_child_started_but_receipt_unavailable
    self.assertTrue(report.get('unknown_live_fit') is True or report.get('fit_attempt_count') is None,
AssertionError: False is not true : Owner reported exact fit_attempt_count=0 even though invoked worker count is unknown

----------------------------------------------------------------------
Ran 1 test in 0.030s

FAILED (failures=1)
```
