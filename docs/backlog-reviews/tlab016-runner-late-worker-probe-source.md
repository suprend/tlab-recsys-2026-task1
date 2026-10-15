# Independent016 runner v1 source

Original SHA256 d8470e760bc383c90f622c6a67af0b13702e6e12c0f24035aaf228851fc19d22. Temporary traceback roots sanitized for publication; synthetic fixture source/assertions unchanged. No actual model/source execution.

```python
import unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_feature_program_experiment as a
m=a.m

class LateWorkerFailure(a.OwnerLifecycle):
    def test_independent_late_worker_failed_marker_must_block_owner_success(self):
        native=self.fake_observer
        def observer(directory,parent,producer,budget):
            result=native(directory,parent,producer,budget)
            worker_report=m._local(producer['children'][0]['report']['path'])
            worker_report.with_name('report.failed.json').write_text('{"status":"failed","outcome":"integrity_or_API_failure"}\n')
            return result
        with patch.object(m,'_observer',side_effect=observer):
            with self.assertRaisesRegex(RuntimeError,'Late known|failed'):
                self.run_owner()

suite=unittest.defaultTestLoader.loadTestsFromModule(a)
suite.addTest(LateWorkerFailure('test_independent_late_worker_failed_marker_must_block_owner_success'))
r=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if r.wasSuccessful() else 1)
```
