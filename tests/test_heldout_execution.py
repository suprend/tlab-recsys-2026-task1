import json,tempfile,time,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from scripts import heldout_execution as m
class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.plan=dict(run_id='a'*64,choice='R2',fingerprints={});self.b=m.Budget(started=time.monotonic())
  self.pin('inputs/request.json',{});self.pin('inputs/claim.json',{});self.pin('inputs/shared.json',{})
  for name in set(m.ENTRY.values()):self.pin(name,{'reviewed_fixed_entry':name})
  self.request=self.reference('inputs/request.json');self.claim=self.reference('inputs/claim.json')
  self.s=m.Session(self.root,'artifacts/invocation',self.plan,self.request,self.claim,self.b)
 def tearDown(self):self.tmp.cleanup()
 def pin(self,name,body):
  p=m.local(self.root,name);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(m.canonical(body)+'\n');self.plan['fingerprints'][name]=m.sha(p);return self.reference(name)
 def reference(self,name):return dict(path=name,sha256=m.sha(m.local(self.root,name)))
 def gate(self,name):
  scopes={'initial_execution':'reserved_source_inference_execution','source_acceptance':'reviewed_reserved_source','prediction_acceptance':'reviewed_all_reserved_predictions_before_targets','target_execution':'report_only_reserved_fullY'}
  body=dict(version=1,approved=True,scope=scopes[name],run_id=self.plan['run_id']);r=self.pin('authority/'+name+'.json',body);self.s.record_gate(name,r,expected=body);return r
 def issue(self,role):
  r=self.reference('inputs/shared.json');return self.s.issue(role,{name:r for name in m.INPUT_KEYS[role]})
 def result(self,issued):
  ctx=issued['context'];role=ctx['role'];outputs={}
  for name in ctx['expected_outputs']:
   p=m.local(self.root,name);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}\n');outputs[name]=m.sha(p)
  consumed=m.exclusive(self.s.directory/role/'execution.consumed.json',dict(version=1,scope='reserved_child_execution_consumed',role=role,run_id=self.plan['run_id'],context=issued['context_ref'],slot=issued['slot_ref']))
  body=dict(version=1,scope='reserved_reporting_'+role,status='role_complete_unaccepted',run_id=self.plan['run_id'],role=role,context=issued['context_ref'],
   execution_consumed=dict(path=self.s.relative(consumed['path']),sha256=consumed['sha256']),inputs=deepcopy(ctx['inputs']),outputs=outputs,evidence=dict(path=ctx['expected_outputs'][-1],sha256=outputs[ctx['expected_outputs'][-1]]),
   fit_attempt_count=0,labels_loaded=role in m.ROLES[4:],native_prediction_count=0,started_monotonic=ctx['issued_at_monotonic'],finished_monotonic=time.monotonic(),process_cpu_seconds=.1,process_peak_rss_bytes=1024,descendant_cpu_seconds=0)
  p=m.local(self.root,ctx['output_path']);p.write_text(m.canonical(body)+'\n');return body,self.reference(ctx['output_path'])
 def accept(self,issued,mutate=None):
  body,r=self.result(issued)
  if mutate:
   mutate(body);m.local(self.root,r['path']).write_text(m.canonical(body)+'\n');r=self.reference(r['path'])
  return self.s.accept_receipt(body,r,exit_code=0,actual_reaped_cpu=.11)
 def complete(self,role):return self.accept(self.issue(role))
 def all_roles(self):
  self.gate('initial_execution');self.complete('source');self.complete('source_oracle');self.gate('source_acceptance');self.complete('predictions');self.complete('prediction_oracle');self.gate('prediction_acceptance');self.gate('target_execution');self.complete('targets_evaluation');self.complete('metric_oracle')
 def test_all_roles_fixed_gates_final_unaccepted_boundary(self):
  self.all_roles();result=self.s.finish();self.assertEqual(result['status'],'verified_reporting_pending_external_lifetime_acceptance');self.assertTrue(result['external_exit_tail_acceptance_required']);self.assertEqual(len(result['roles']),6);self.assertTrue(result['reserved_targets_may_have_been_opened'])
 def test_no_role_skip_retry_or_target_before_prediction_seal(self):
  with self.assertRaises(ValueError):self.issue('predictions')
  with self.assertRaises(ValueError):self.gate('target_execution')
  self.gate('initial_execution');x=self.issue('source')
  with self.assertRaises(ValueError):self.issue('source')
  self.accept(x)
  with self.assertRaises(ValueError):self.issue('source')
 def test_initial_gate_absent_cannot_consume_source(self):
  with self.assertRaises(ValueError):self.issue('source')
  self.assertFalse((self.s.directory/'source').exists())
 def test_caller_cannot_choose_an_arbitrary_pinned_script(self):
  self.gate('initial_execution');self.s.plan['fingerprints'].pop(m.ENTRY['source']);self.s.plan['fingerprints']['arbitrary.py']='b'*64
  with self.assertRaises(ValueError):self.issue('source')
 def test_issued_slot_context_and_launch_are_deepcopied_and_bound(self):
  self.gate('initial_execution');x=self.issue('source');x['slot']['allocation']['cpu_seconds']=9999;x['context']['allocation']['cpu_seconds']=9999
  self.assertLess(self.s.active['context']['allocation']['cpu_seconds'],9999)
  body,r=self.result(self.s.active);self.s.active['launch_ref']['sha256']='b'*64
  with self.assertRaises(ValueError):self.s.accept_receipt(body,r,exit_code=0,actual_reaped_cpu=.11)
 def test_changed_external_authority_rejects_before_next_role(self):
  r=self.gate('initial_execution');m.local(self.root,r['path']).write_text('{}\n')
  with self.assertRaises(ValueError):self.issue('source')
 def test_label_reference_not_in_source_vocabulary(self):
  self.gate('initial_execution');inputs={name:self.reference('inputs/shared.json') for name in m.INPUT_KEYS['source']};inputs['target_intent']=inputs['source']
  with self.assertRaises(ValueError):self.s.issue('source',inputs)
 def test_false_child_label_state_or_fit_count_rejected(self):
  self.gate('initial_execution');x=self.issue('source')
  with self.assertRaises(ValueError):self.accept(x,lambda b:b.update(labels_loaded=True))
 def test_bool_fit_count_is_not_integer_zero(self):
  self.gate('initial_execution');x=self.issue('source')
  with self.assertRaises(ValueError):self.accept(x,lambda b:b.update(fit_attempt_count=False))
 def test_omitted_output_fresh_receipt_rejected(self):
  self.gate('initial_execution');x=self.issue('source')
  with self.assertRaises(ValueError):self.accept(x,lambda b:b['outputs'].pop(next(iter(b['outputs']))))
 def test_execution_consumption_bool_version_rejected(self):
  self.gate('initial_execution');x=self.issue('source');body,r=self.result(x);p=m.local(self.root,body['execution_consumed']['path']);c,_=m.read(p);c['version']=True;p.write_text(m.canonical(c)+'\n');body['execution_consumed']['sha256']=m.sha(p);m.local(self.root,r['path']).write_text(m.canonical(body)+'\n');r=self.reference(r['path'])
  with self.assertRaises(ValueError):self.s.accept_receipt(body,r,exit_code=0,actual_reaped_cpu=.11)
 def test_missing_receipt_failure_retains_unknown_work_and_consumed_role(self):
  self.gate('initial_execution');self.issue('source');out=self.s.fail(OSError('lost receipt'));self.assertTrue(out['unknown_active_work']);self.assertEqual(out['active_role'],'source');self.assertTrue((self.s.directory/'source/slot.json').exists())
  with self.assertRaises(ValueError):self.issue('source')
 def test_late_role_marker_blocks_finalization_and_persists_failure(self):
  self.all_roles();(self.s.directory/'source/report.failed.json').write_text('{}\n')
  with self.assertRaises(ValueError):self.s.finish()
  self.assertTrue((self.s.directory/'report.failed.json').exists());self.assertEqual(self.s.report['status'],'failed')
 def test_changed_dynamic_gate_blocks_finalization(self):
  self.all_roles();r=self.s.gates['target_execution'];m.local(self.root,r['path']).write_text('{}\n')
  with self.assertRaises(ValueError):self.s.finish()
 def test_consumption_exclusive_and_session_directory_retry_refused(self):
  with self.assertRaises(FileExistsError):m.Session(self.root,'artifacts/invocation',self.plan,self.request,self.claim,self.b)
  p=self.root/'once.json';m.exclusive(p,{})
  with self.assertRaises(FileExistsError):m.exclusive(p,{})
 def test_symlink_escape_rejected(self):
  (self.root/'escape').symlink_to('/tmp',target_is_directory=True)
  with self.assertRaises(ValueError):m.local(self.root,'escape/outside.json')
 def test_budget_shared_cpu_actual_counters_and_reserves(self):
  with patch.object(m,'counters',return_value=(100,200,1024)):
   self.assertEqual(self.b.cpu(),300);self.assertEqual(self.b.allocation('source')['cpu_seconds'],900)
  with patch.object(m,'counters',return_value=(4100,0,1024)):
   self.assertEqual(self.b.allocation('source')['cpu_seconds'],38)
  with patch.object(m,'counters',return_value=(4200,0,1024)),self.assertRaises(TimeoutError):self.b.guard()
 def test_unknown_cpu_and_parent_rss_fail_closed(self):
  with patch.object(m,'counters',return_value=(float('nan'),0,1024)),self.assertRaises(ValueError):self.b.guard()
  with patch.object(m,'counters',return_value=(0,0,2**30+1)),self.assertRaises(MemoryError):self.b.guard()
 def test_output_mutation_during_finalizing_persistence_fails(self):
  self.all_roles();original=self.s.persist
  def persist():
   original()
   if self.s.report['status']=='finalizing':m.local(self.root,next(iter(self.s.output_pins))).write_text('changed\n')
  self.s.persist=persist
  with self.assertRaises(ValueError):self.s.finish()
  self.assertEqual(self.s.report['status'],'failed');self.assertTrue((self.s.directory/'report.failed.json').exists())
 def test_gate_mutation_during_terminal_persistence_fails(self):
  self.all_roles();original=self.s.persist
  def persist():
   original()
   if self.s.report['status']=='verified_reporting_pending_external_lifetime_acceptance':m.local(self.root,self.s.gates['target_execution']['path']).write_text('{}\n')
  self.s.persist=persist
  with self.assertRaises(ValueError):self.s.finish()
  self.assertEqual(self.s.report['status'],'failed')
 def test_last_resource_guard_cannot_create_unchecked_failure_marker(self):
  self.all_roles();original=self.b.guard
  def guard():
   original()
   if self.s.report['status']=='verified_reporting_pending_external_lifetime_acceptance':(self.s.directory/'source/report.failed.json').write_text('{}\n')
  self.b.guard=guard
  with self.assertRaises(ValueError):self.s.finish()
  self.assertEqual(self.s.report['status'],'failed')
 def test_metadata_exponent_overflow_is_rejected_inside_reader(self):
  p=self.root/'overflow.json';p.write_text('{"nested":[{"x":1e999}]}')
  with self.assertRaisesRegex(ValueError,'Nonfinite JSON'):m.read(p)
  p.write_text('{"nested":[{"x":1e2}]}');body,_=m.read(p);self.assertEqual(body['nested'][0]['x'],100.)
 def test_W_equal_B_output_vocabulary_reuses_only_B(self):
  outputs=m.expected_paths('artifacts/x','predictions','B');self.assertEqual(len(outputs),8);self.assertFalse(any('/W.npz' in name for name in outputs))
 def test_issued_context_retains_original_authority_snapshot(self):
  gate=self.gate('initial_execution');issued=self.issue('source')
  self.assertEqual(issued['context']['authorities'],{'initial_execution':gate})
  issued['context']['authorities']['initial_execution']['sha256']='0'*64
  self.assertEqual(self.s.active['context']['authorities']['initial_execution'],gate)
 def test_target_policy_is_prospective_input_not_fabricated_actual_intent(self):
  self.assertIn('target_policy',m.INPUT_KEYS['targets_evaluation']);self.assertIn('target_policy',m.INPUT_KEYS['metric_oracle'])
  self.assertNotIn('target_intent',m.INPUT_KEYS['targets_evaluation'])
  for role in m.ROLES[:4]:self.assertFalse(any('target' in name or 'label' in name for name in m.INPUT_KEYS[role]))
if __name__=='__main__':unittest.main(verbosity=2)
