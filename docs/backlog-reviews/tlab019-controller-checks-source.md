# Historical019 audit source: controller-checks

Aggregate/synthetic evidence archive. Paths below are normalized for privacy; this preserves the historical observer, not a new execution approval. Original freeze references belong to the version reviewed by that pass. No real019 model fit was run by these checks.

```python
from pathlib import Path
import hashlib,importlib.util,unittest
from unittest.mock import patch
p=Path('test-tlab019-controller.py');s=importlib.util.spec_from_file_location('rootchecks',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class LaunchChecks(m.ControllerTests):
 def test_durable_issuer_evidence_precedes_spawn_and_matches_memory(self):
  original=m.s.run_process;observed=[]
  def launched(argv,log,**kwargs):
   d=Path(log).parent;report=m.s.read(d/'report.json');context=d/'verification-context.json';issued=hashlib.sha256(context.read_bytes()).hexdigest()
   self.assertEqual(argv[-2:],['--issued-context-sha256',issued]);self.assertEqual(report['verifier_launch']['argv'],argv)
   self.assertEqual(report['verifier_launch']['issued_context_sha256'],issued)
   self.assertEqual(report['verifier_launch']['allocation'],kwargs['allocation']);observed.append(issued)
   return original(argv,log,**kwargs)
  with patch.object(m.s,'run_process',side_effect=launched):self.invoke()
  self.assertEqual(len(observed),1)
 def test_live_valid_receipt_cannot_bind_changed_allocation(self):
  original=m.s.run_process
  def changed(argv,log,**kwargs):
   value=original(argv,log,**kwargs);p=Path(log).with_name('verification.json');r=m.s.read(p)
   r['allocation']['cpu_seconds']-=1;m.s.write(p,r);return value
  with patch.object(m.s,'run_process',side_effect=changed):
   with self.assertRaisesRegex(ValueError,'binding differs: allocation'):self.invoke()
if __name__=='__main__':unittest.main(verbosity=2)

```
