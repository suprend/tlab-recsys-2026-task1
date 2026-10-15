# Independent016 runner v1 source

Original SHA256 448af580d416a65a1762074fca7d3853d0d13885030653359280f1c3b3ef79c4. Temporary traceback roots sanitized for publication; synthetic fixture source/assertions unchanged. No actual model/source execution.

```python
import json,unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_feature_program_experiment as a
m=a.m
class WorkerAccounting(a.OwnerLifecycle):
 def test_independent_failed_owner_reports_unknown_when_child_started_but_receipt_unavailable(self):
  def interrupted(directory,parent,slot,path,issued,budget):
   out=directory/'workers'/slot['candidate_id']/'paid-unreadable';out.mkdir(parents=True)
   (out/'native-fit-started.audit').write_text('synthetic fixture says fit was entered; not native execution')
   raise OSError('synthetic missing receipt after consumed native fit')
  with patch.object(m,'_invoke_worker',side_effect=interrupted):
   with self.assertRaisesRegex(OSError,'missing receipt'):self.run_owner()
  path=next((self.root/'artifacts/feature-program-invocations').glob('*/report.failed.json'))
  report=json.loads(path.read_text())
  self.assertTrue(report.get('unknown_live_fit') is True or report.get('fit_attempt_count') is None,
                  'Owner reported exact fit_attempt_count=0 even though invoked worker count is unknown')
suite=unittest.TestSuite([WorkerAccounting('test_independent_failed_owner_reports_unknown_when_child_started_but_receipt_unavailable')])
r=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if r.wasSuccessful() else 1)
```
