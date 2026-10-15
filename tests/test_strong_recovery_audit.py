import importlib.util,unittest,ast,hashlib,json
from pathlib import Path
from unittest.mock import patch

def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
PROJECT=Path(__file__).resolve().parents[1]
owner_tests=module('owner_tests',str(PROJECT/'tests/test_strong_recovery.py'))
rec=module('recovery',str(PROJECT/'tests/oracles/strong_recovery_audit.py'))
class RecoveryContract(owner_tests.OwnerLifecycle):
 def setUp(self):
  super().setUp();self.entry.write_bytes(Path(rec.__file__).read_bytes())
  self.observer_module=module('fixture_observer',self.entry)
  self.policy.update(entry_sha256=owner_tests.m.sha(self.entry),diagnostic_cpu_upper_seconds=5.)
  (self.root/'approval.json').write_text(json.dumps(self.policy)+'\n')
  self.context=None;self.controller=None;self.observer=None
 def fake_observer(self,argv,log_path,**kwargs):
  context_path=Path(argv[argv.index('--context')+1]);c=json.loads(context_path.read_text())
  self.context=c;self.controller=json.loads((context_path.parent/'report.json').read_text())
  o=self.observer_module.Observer.__new__(self.observer_module.Observer)
  o.root=self.root;o.context=c;o.self_sha=owner_tests.m.sha(self.entry);o.allocation=c['allocation'];o.expired=__import__('threading').Event();o.phase='synthetic_binding';self.observer=o
  policy=json.loads((self.root/'approval.json').read_text());request=json.loads((context_path.parent/'verification-request.json').read_text())
  with patch.object(o,'guard',return_value=None):o.recovery_binding(request,self.controller,policy,self.controller['verifier_approval'])
  self.request=request;self.bound_policy=policy
  return super().fake_observer(argv,log_path,**kwargs)
 def test_owner_observer_same_exact_contract_and_failed_cpu_is_retained(self):
  self.invoke();self.assertEqual(self.observer.recovery_proof['producer_calls'],0)
  self.assertAlmostEqual(self.observer.recovery_proof['boundary']['maximum_recovery_cpu_seconds'],218.52094)
 def test_context_block_or_ownercalls_mutation_rejects(self):
  self.invoke();o=self.observer
  with patch.object(o,'guard',return_value=None):
   for body,key,value in [(o.context['recovery'],'old_invocation','other'),(self.controller,'producer_calls',1)]:
    original=body[key];body[key]=value
    try:
     # producer_calls is also checked by the enclosing binding, so directly
     # test the recovery-only nofit flags here.
     if key=='producer_calls':
      self.controller['fit_attempt_count']=1
     with self.assertRaises(ValueError):o.recovery_binding(self.request,self.controller,self.bound_policy,self.controller['verifier_approval'])
    finally:
     body[key]=original;self.controller['fit_attempt_count']=0
 def test_more_allowance_or_changed_failedhistory_rejects(self):
  self.invoke();o=self.observer
  with patch.object(o,'guard',return_value=None):
   original=o.allocation['cpu_seconds'];o.allocation['cpu_seconds']=300
   with self.assertRaises(ValueError):o.recovery_binding(self.request,self.controller,self.bound_policy,self.controller['verifier_approval'])
   o.allocation['cpu_seconds']=original
   (self.oldroot/'verification.failed.json').write_text('changed')
   with self.assertRaises(ValueError):o.recovery_binding(self.request,self.controller,self.bound_policy,self.controller['verifier_approval'])
 def test_documented_final_persistence_tail_keeps_both_history_seals(self):
  failed=dict(self.old);failed.update(actual_parent_cpu_seconds=155.410577,actual_total_cpu_seconds=1563.381867,seconds=1191.907734)
  final=dict(failed);final.update(actual_parent_cpu_seconds=155.411218,actual_total_cpu_seconds=1563.382506,seconds=1191.9083710410014)
  for name,body in [('report.json',final),('report.failed.json',failed)]:
   path=self.oldroot/name;path.write_text(json.dumps(body)+'\n');self.policy['fingerprints'][str(path.relative_to(self.root))]=owner_tests.m.sha(path)
  (self.root/'approval.json').write_text(json.dumps(self.policy)+'\n')
  self.invoke();self.assertTrue(self.observer.recovery_proof['failed_history_preserved'])
class Preservation(unittest.TestCase):
 def test_original_numerical_definitions_unchanged(self):
  orig=module('original',str(PROJECT/'tests/oracles/strong_output_audit.py'))
  a=ast.parse(Path(orig.__file__).read_text());b=ast.parse(Path(rec.__file__).read_text())
  defs=lambda x:{n.name:ast.dump(n,include_attributes=False) for n in x.body if isinstance(n,ast.FunctionDef)}
  x,y=defs(a),defs(b)
  for name in ['same','compare','effective_learning_rate','select','metric_values','summarize','bootstrap','worker_resource_policy','whole_resource_policy']:
   self.assertEqual(x[name],y[name],name)
  methods=lambda t:{n.name:ast.dump(n,include_attributes=False) for cl in t.body if isinstance(cl,ast.ClassDef) and cl.name=='Observer' for n in cl.body if isinstance(n,ast.FunctionDef)}
  x,y=methods(a),methods(b)
  for name in ['collection','model','npz','scored','guard','sql']:self.assertEqual(x[name],y[name],name)
 def test_assertion_identifier_constant_without_raw_values(self):
  with self.assertRaises(ValueError) as cm:rec.need(False,'Known constant contract')
  self.assertEqual(cm.exception.assertion_id,hashlib.sha256(b'Known constant contract').hexdigest()[:16])
if __name__=='__main__':unittest.main()
