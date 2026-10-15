import unittest,json,hashlib
from pathlib import Path
from unittest.mock import patch
from tests import test_heldout_worker_context as fixtures
from scripts import heldout_worker_context as w
from scripts import heldout_execution as x
class Independent(unittest.TestCase):
 def setUp(self):self.f=fixtures.Admission();self.f.setUp()
 def tearDown(self):self.f.doCleanups()
 def test_receipt_body_mutated_by_writer_must_not_return_success(self):
  run=self.f.f.begin();outputs,evidence=self.f.f.outputs(run);original=x.exclusive
  def replace(path,body):
   result=original(path,body)
   if Path(path).name=='receipt.json':
    changed=dict(body);changed['process_cpu_seconds']=.5;Path(path).write_text(x.canonical(changed)+'\n')
   return result
  with patch.object(x,'exclusive',side_effect=replace),self.assertRaises(ValueError):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
 def test_post_snapshot_caller_output_and_evidence_aliases_do_not_rebind_receipt(self):
  run=self.f.f.begin();outputs,evidence=self.f.f.outputs(run);expected=dict(outputs);expected_evidence=dict(evidence);original=run.budget.guard;modified=False
  def guard():
   nonlocal modified
   if not modified:outputs.clear();evidence['sha256']='b'*64;modified=True
   return original()
  with patch.object(run.budget,'guard',side_effect=guard):result=run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
  self.assertEqual(result['outputs'],expected);self.assertEqual(result['evidence'],expected_evidence)
 def test_context_budget_and_prior_failed_marker_cannot_be_reset(self):
  run=self.f.f.begin();run.fail(RuntimeError('original'))
  with self.assertRaises(FileExistsError):self.f.f.begin()
  with self.assertRaises(ValueError):run.environment()
 def test_changed_consumption_pin_is_retained_through_terminal(self):
  run=self.f.f.begin();outputs,evidence=self.f.f.outputs(run)
  (self.f.root/run.consumed['path']).write_text('{}\n')
  with self.assertRaisesRegex(ValueError,'changed'):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
if __name__=='__main__':
 freeze=json.loads(Path('/tmp/tlab-heldout-worker-context-freeze-v2.json').read_text())
 for name,sha in freeze.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha
 unittest.main(verbosity=2,defaultTest='Independent')
