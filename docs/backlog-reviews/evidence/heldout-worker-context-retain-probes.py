import unittest
from unittest.mock import patch
from tests import test_heldout_worker_context as f
from scripts import heldout_execution as x
class Retain(unittest.TestCase):
 def setUp(self):self.f=f.Admission();self.f.setUp()
 def tearDown(self):self.f.doCleanups()
 def test_guard_mutated_caller_map_cannot_change_retained_snapshot(self):
  run=self.f.f.begin();ref=self.f.f.file('fixture/new.json',{'tiny':1});mapping={ref['path']:ref['sha256']};original=run.budget.guard;modified=False
  def guard():
   nonlocal modified
   if not modified:mapping[ref['path']]='f'*64;mapping['fixture/added']='f'*64;modified=True
   return original()
  with patch.object(run.budget,'guard',side_effect=guard):retained=run.retain_pins(mapping)
  self.assertEqual(retained,{ref['path']:ref['sha256']});self.assertEqual(run.pins[ref['path']],ref['sha256']);self.assertNotIn('fixture/added',run.pins)
 def test_late_key_conflict_keeps_whole_original_map_and_performs_no_stream(self):
  run=self.f.f.begin();before=run.pins;ref=self.f.f.file('fixture/new.json',{'tiny':1});name=next(iter(before))
  with patch.object(x,'sha',side_effect=AssertionError('No paid stream')),self.assertRaisesRegex(ValueError,'Conflicting'):run.retain_pins({ref['path']:ref['sha256'],name:'f'*64})
  self.assertEqual(run.pins,before)
if __name__=='__main__':unittest.main(verbosity=2,defaultTest='Retain')
