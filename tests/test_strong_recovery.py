from copy import deepcopy
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_strong_recovery as m


class Contract(unittest.TestCase):
 def setUp(self):
  self.policy=dict(version=1,scope='zero_fit_strong_observer_recovery',approved=True,run_id=m.RUN,old_invocation=m.OLD,
   controller_sha256='a'*64,entry_path='/synthetic/not-used',entry_sha256='b'*64,fingerprints={},diagnostic_cpu_seconds=.95999,
   diagnostic_cpu_upper_seconds=2.,old_external_cpu_upper_seconds=1563.42,old_external_peak_rss_bytes=5357060096)
  self.old=dict(status='failed',run_id=m.RUN,producer_calls=1,verifier_calls=1,labels_reserved_opened=False,error_type='RuntimeError',
   error='Independent verifier failed; no promotion/refill',actual_reaped_children_cpu_seconds=1407.971288,
   actual_total_cpu_seconds=1563.382506,actual_parent_cpu_seconds=155.411218,seconds=1191.91,
   started_monotonic=19391.362354375,outer_deadline_monotonic=22991.362354375,parent_peak_rss_bytes=636715008)
  self.producer=dict(status='complete_produced_unreviewed',run_id=m.RUN,fit_attempt_count=4,actual_seen_looks=12,unknown_live_fit=False,
   actual_reaped_children_cpu_seconds=1331.492228,outer_deadline_monotonic=22991.362354375)
  self.request=dict(run_id=m.RUN,maximum_verifier_cpu_seconds=300,outer_deadline_monotonic=22991.362354375,
   producer_manifest=dict(path='producer/run.json',sha256='c'*64),producer_report=dict(path='producer/report.json',sha256='d'*64))
  self.context=dict(run_id=m.RUN,producer_manifest=self.request['producer_manifest'],producer_report=self.request['producer_report'],allocation=dict(cpu_seconds=300))
 def call(self):return m.validate_policy(self.policy,self.old,self.request,self.context,self.producer)
 def test_cost_prefix_retains_failed_verifier_original_tail_and_diagnosis(self):
  b=self.call();self.assertAlmostEqual(b['failed_verifier_cpu_seconds'],76.47906)
  self.assertAlmostEqual(b['maximum_recovery_cpu_seconds'],221.52094)
  self.assertAlmostEqual(b['previous_cpu_upper_seconds'],1565.42)
  self.assertEqual(b['outer_deadline_monotonic'],22991.362354375)
 def test_other_failure_class_partial_producer_unknown_fit_or_heldout_cannot_recover(self):
  for obj,key,value in [(self.old,'error_type','TimeoutError'),(self.old,'producer_calls',2),
    (self.old,'labels_reserved_opened',True),(self.producer,'fit_attempt_count',3),
    (self.producer,'actual_seen_looks',11),(self.producer,'unknown_live_fit',True)]:
   old=obj[key];obj[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.call()
   obj[key]=old
 def test_unknown_negative_or_reset_cost_and_extended_deadline_reject(self):
  for obj,key,value in [(self.policy,'diagnostic_cpu_seconds',float('nan')),
    (self.policy,'old_external_cpu_upper_seconds',1563.),(self.policy,'diagnostic_cpu_upper_seconds',0.),
    (self.old,'actual_reaped_children_cpu_seconds',1300.),(self.context['allocation'],'cpu_seconds',301),
    (self.old,'outer_deadline_monotonic',23991.362354375)]:
   old=obj[key];obj[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.call()
   obj[key]=old
 def test_old_conservative_job_peak_includes_parent_and_child(self):
  self.policy['old_external_peak_rss_bytes']=8*2**30
  with self.assertRaisesRegex(ValueError,'RSS'):self.call()
 def test_new_policy_fields_or_changed_producer_reference_stop(self):
  self.policy['allow_extra_fit']=True
  with self.assertRaises(ValueError):self.call()
  del self.policy['allow_extra_fit'];self.context['producer_report']=dict(path='other.json',sha256='d'*64)
  with self.assertRaisesRegex(ValueError,'binding'):self.call()
 def test_cumulative_original_observer_cap_counts_fresh_owner_and_reaped_children(self):
  class S:
   def rss(self):return 1000000
  b=m.Budget(self.call(),S())
  with patch.object(m.time,'monotonic',return_value=22000),patch.object(m,'cpu',return_value=100.):b.guard()
  with patch.object(m.time,'monotonic',return_value=22000),patch.object(m,'cpu',return_value=220.):
   with self.assertRaisesRegex(TimeoutError,'observer'):b.guard()
  with patch.object(m.time,'monotonic',return_value=23000),patch.object(m,'cpu',return_value=0.):
   with self.assertRaisesRegex(TimeoutError,'deadline'):b.guard()
 def test_issued_child_budget_reserves_full_monitored_live_parent_CPU_and_tail(self):
  class S:
   def rss(self):return 1000000
  b=m.Budget(self.call(),S())
  live_parent=b.limits['parent_launch_cpu_reserve']-20
  spent=1.;remaining=b.boundary['maximum_recovery_cpu_seconds']
  with patch.object(m.time,'monotonic',return_value=22000),patch.object(m,'cpu',return_value=spent):
   issued=b.allocation()
  child=issued['cpu_seconds']
  self.assertEqual(live_parent,10)
  self.assertLessEqual(spent+child+live_parent+2,remaining)
  # The old −2 issuance allowed the live parent to overspend the original cap.
  old_child=int(remaining-spent-2)
  self.assertGreater(spent+old_child+live_parent,remaining)
 def test_only_documented_final_SELF_and_wall_tail_can_change(self):
  marker=dict(self.old,actual_total_cpu_seconds=1563.381867,actual_parent_cpu_seconds=155.410577,seconds=1191.90)
  m.validate_failure_tail(marker,self.old)
  changed=deepcopy(self.old);changed['extra_state']=True
  with self.assertRaisesRegex(ValueError,'schemas'):m.validate_failure_tail(marker,changed)
  changed=deepcopy(self.old);changed['actual_reaped_children_cpu_seconds']+=.001
  with self.assertRaisesRegex(ValueError,'identity/state'):m.validate_failure_tail(marker,changed)
  changed=deepcopy(self.old);changed['actual_total_cpu_seconds']-=1
  with self.assertRaisesRegex(ValueError,'regressed'):m.validate_failure_tail(marker,changed)
 def test_recovery_owner_RSS_is_a_separate_hard_guard(self):
  class S:
   def rss(self):return 2**30+1
  with patch.object(m.time,'monotonic',return_value=22000),patch.object(m,'cpu',return_value=0.):
   with self.assertRaisesRegex(MemoryError,'RSS'):m.Budget(self.call(),S()).guard()


class OwnerLifecycle(unittest.TestCase):
 def setUp(self):
  Contract.setUp(self)
  from scripts import strong_baseline as strong
  self.strong=strong;tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
  p=patch.object(strong,'ROOT',self.root);p.start();self.addCleanup(p.stop)
  self.owner_path=self.root/'scripts/run_strong_recovery.py';self.owner_path.parent.mkdir()
  self.owner_path.write_bytes(Path(m.__file__).read_bytes())
  sp=importlib.util.spec_from_file_location('owner_fixture',self.owner_path)
  self.owner=importlib.util.module_from_spec(sp);sp.loader.exec_module(self.owner);self.owner.START=20000.
  self.entry=self.root/'tests/oracles/fake_observer.py';self.entry.parent.mkdir(parents=True);self.entry.write_text('# synthetic observer replacement only\n')
  self.policy.update(controller_sha256=m.sha(self.owner_path),entry_path=str(self.entry),entry_sha256=m.sha(self.entry))
  self.oldroot=self.root/m.OLD;self.oldroot.mkdir(parents=True)
  self.prodroot=self.root/'artifacts/strong-baseline'/m.RUN;self.prodroot.mkdir(parents=True)
  def put(p,v):p.write_text(json.dumps(v,sort_keys=True)+'\n')
  put(self.prodroot/'report.json',self.producer);put(self.prodroot/'run.json',dict(run_id=m.RUN))
  refs={k:dict(path=str((self.prodroot/(f+'.json')).relative_to(self.root)),sha256=m.sha(self.prodroot/(f+'.json')))
    for k,f in [('producer_manifest','run'),('producer_report','report')]}
  self.request.update(refs);self.context.update(refs)
  failure_marker=dict(self.old,actual_total_cpu_seconds=1563.381867,actual_parent_cpu_seconds=155.410579,seconds=1191.90)
  values={'report.json':self.old,'report.failed.json':failure_marker,'verification-request.json':self.request,
   'verification-context.json':self.context,'verification.failed.json':dict(status='failed',run_id=m.RUN,fit_attempt_count=0,error_type='ValueError'),
   'verification.log':dict(synthetic=True),'verification.json.attempt':dict(synthetic=True)}
  for name,value in values.items():put(self.oldroot/name,value)
  self.policy['fingerprints']={str(p.relative_to(self.root)):m.sha(p) for p in [*self.oldroot.iterdir(),self.prodroot/'run.json',self.prodroot/'report.json']}
  put(self.root/'approval.json',self.policy)
  self.calls=[]
 def fake_observer(self,argv,log_path,**kwargs):
  self.calls.append(argv);Path(log_path).write_text('synthetic observer output\n')
  context_path=Path(argv[argv.index('--context')+1]);context=json.loads(context_path.read_text())
  receipt=dict(version=1,status='verified',scope=context['scope'],run_id=m.RUN,context_sha256=m.sha(context_path),
   request_sha256=context['request_sha256'],producer_manifest=context['producer_manifest'],producer_report=context['producer_report'],
   verifier_source=context['expected_verifier_source'],allocation=context['allocation'],fit_attempt_count=0,process_cpu_seconds=0.,
   reaped_children_cpu_seconds=0.,process_peak_rss_bytes=1000,started_monotonic=20000.,finished_monotonic=20000.,seconds=0.,
   evidence=dict(synthetic_only=True))
  (self.root/context['output_path']).write_text(json.dumps(receipt,sort_keys=True)+'\n');return 0
 def invoke(self,side_effect=None):
  with patch.object(self.owner.sys,'argv',[str(self.owner_path),'--project-root',str(self.root),'--approval','approval.json']),\
    patch.object(self.owner.time,'monotonic',return_value=20000.),\
    patch.object(self.strong,'run_process',side_effect=side_effect or self.fake_observer):
   self.owner.main()
 def test_success_is_zero_fit_keeps_old_failure_and_global_claim_blocks_replay(self):
  old={p:p.read_bytes() for p in self.oldroot.iterdir()};self.invoke()
  self.assertEqual(len(self.calls),1)
  report=json.loads(next((self.root/'artifacts/strong-recoveries').glob('*/report.json')).read_text())
  self.assertEqual(report['status'],'recovery_verified_pending_external_acceptance');self.assertEqual(report['producer_calls'],0)
  self.assertEqual(report['fit_attempt_count'],0);self.assertTrue(all(p.read_bytes()==v for p,v in old.items()))
  with self.assertRaises(FileExistsError):self.invoke()
  self.assertEqual(len(self.calls),1)
 def test_failed_observer_remains_consumed_and_preserves_old_failure(self):
  before=(self.oldroot/'report.failed.json').read_bytes()
  def fail(*args,**kwargs):raise RuntimeError('synthetic launch failure')
  with self.assertRaisesRegex(RuntimeError,'synthetic launch'):self.invoke(fail)
  failure=next((self.root/'artifacts/strong-recoveries').glob('*/report.failed.json'))
  self.assertEqual(json.loads(failure.read_text())['status'],'failed')
  self.assertEqual((self.oldroot/'report.failed.json').read_bytes(),before)
  with self.assertRaises(FileExistsError):self.invoke()
  self.assertEqual(self.calls,[])
 def test_changed_old_receipt_aborts_before_any_verifier_launch(self):
  (self.oldroot/'verification.failed.json').write_text('changed')
  with self.assertRaisesRegex(ValueError,'evidence changed'):self.invoke()
  self.assertEqual(self.calls,[]);self.assertFalse((self.root/m.CLAIM).exists())


if __name__=='__main__':unittest.main()
