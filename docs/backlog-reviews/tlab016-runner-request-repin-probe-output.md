# Independent016 runner v1 output

Original SHA256 f3232b62f254fd8e899b112be8f59a4429d6016c914f0b68522c199aa2a05e10. Temporary traceback roots sanitized for publication; synthetic fixture source/assertions unchanged. No actual model/source execution.

```text
test_independent_observer_request_mutation_must_reject_pending_source (__main__.ObserverRepin.test_independent_observer_request_mutation_must_reject_pending_source) ... FAIL

======================================================================
FAIL: test_independent_observer_request_mutation_must_reject_pending_source (__main__.ObserverRepin.test_independent_observer_request_mutation_must_reject_pending_source)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab016-model-runner-observer-repin-probe.py", line 37, in test_independent_observer_request_mutation_must_reject_pending_source
    with self.assertRaisesRegex(ValueError,'request|authority|changed'):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 1 test in 0.040s

FAILED (failures=1)
```
