"""One bounded stdlib/mock WHOLE018 CODE probe; no application process."""
import time
ENTRY=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(15,15))
import signal
signal.alarm(20)
import ast
import builtins
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch

mp=Path('/tmp/tlab-development-whole018-v2-independent-inputs/input-freeze.json');mr=mp.read_bytes()
assert hashlib.sha256(mr).hexdigest()=='e8856d9887b263740db9db1d5df3149939f08fdd2cf9a65b45b19fa1f214f66d'
manifest=json.loads(mr);files=manifest['files'];raws={}
def freshness():
 for name,e in files.items():
  raw=Path(name).read_bytes();copy=Path(e['snapshot_path']).read_bytes()
  assert raw==copy and len(raw)==e['bytes'] and hashlib.sha256(raw).hexdigest()==e['sha256']
  raws[name]=raw;raws[str(Path(name).resolve())]=raw
freshness()
violations=[];observations={}
def forbidden(label):
 def fail(*args,**kwargs):violations.append(label);raise AssertionError('Forbidden actual operation: '+label)
 return fail
original_import=builtins.__import__
def safe_import(name,*args,**kwargs):
 if name=='scripts' or name.startswith('scripts.') or name.split('.')[0] in {'duckdb','numpy','pandas','catboost','ctypes'}:return forbidden('import '+name)()
 return original_import(name,*args,**kwargs)
original_read=Path.read_bytes
def read(path):
 if str(path) in raws:return raws[str(path)]
 if path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):return original_read(path)
 return forbidden('nonfrozen Path.read_bytes '+str(path))()
name='/tmp/test_tlab_development_whole018_driver_v2.py';tree=ast.parse(raws[name],name)
removed=[];body=[]
for node in tree.body:
 if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and isinstance(node.value.func.value,ast.Name) and (node.value.func.value.id,node.value.func.attr) in {('resource','setrlimit'),('signal','alarm')}:
  removed.append(ast.unparse(node));continue
 body.append(node)
tree.body=body;assert len(removed)==2
author=ModuleType('whole018_independent_selected_author_fixtures');author.__file__=name;sys.modules[author.__name__]=author
log=io.StringIO()
with ExitStack() as guards:
 guards.enter_context(patch.object(builtins,'__import__',side_effect=safe_import))
 guards.enter_context(patch.object(Path,'read_bytes',read))
 for module,attr in [(subprocess,'Popen'),(os,'system'),(os,'fork'),(os,'posix_spawn'),(os,'posix_spawnp'),(os,'kill'),(os,'wait4'),(socket,'create_connection')]:
  if hasattr(module,attr):guards.enter_context(patch.object(module,attr,side_effect=forbidden(module.__name__+'.'+attr)))
 guards.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden('network connect')))
 exec(compile(tree,name,'exec',dont_inherit=True),author.__dict__);M=author.M
 class IndependentTests(unittest.TestCase):
  def test_exact_candidate_passes_literal_owner_and_driver_admission(self):
   candidate=raws['/tmp/tlab-development-whole018-request-candidate-v1.json']
   combined=raws['/tmp/tlab-reproduce-development-slice-v1.py']+b'\n\n'+raws['/tmp/tlab-development-slice-owner-v2.py']
   self.assertEqual(hashlib.sha256(combined).hexdigest(),M.OWNER_SHA)
   owner=ModuleType('whole018_independent_owner_declarations_only');owner.__file__=str(M.PROJECT/M.OWNER)
   exec(compile(combined,owner.__file__,'exec',dont_inherit=True),owner.__dict__)
   with patch.object(M,'snapshot',return_value=candidate) as source:body=M.fixed_request(M.REQUEST_SHA)
   source.assert_called_once_with(M.PROJECT/M.REQUEST,M.REQUEST_SHA)
   self.assertIs(owner._owner_request(body),body)
   handoff=json.loads(raws['/tmp/tlab-root-development-day-reference-handoff-prepared.json'])
   for key in ['source','models','manual_registry','pool_contract']:self.assertEqual(body[key],handoff[key])
   self.assertEqual(body['comparison']['references'],handoff['reference_artifacts'])
   self.assertEqual((M.LIMITS['cpu_seconds']+10,M.LIMITS['wall_seconds']+10),(600,900))
   checker=ast.parse(raws['/tmp/tlab-development-day-parity-v2.py'])
   fn=next(n for n in checker.body if isinstance(n,ast.FunctionDef) and n.name=='verify_request')
   self.assertEqual([a.arg for a in fn.args.args],['request_path','expected_request_sha'])
   self.assertEqual([a.arg for a in fn.args.kwonlyargs],['check'])
   observations['candidate']=dict(driver_and_literal_owner_admission=True,checker_API_matches=True,owner_combined_sha256=M.OWNER_SHA,outer_plus_outside_reserve=[600,900])

  def test_late_owner_wall_never_even_loads_parity(self):
   fixture=author.PipelineTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
   previous=fixture.owner.run_slice
   def late(*args,**kwargs):
    result=previous(*args,**kwargs);M.time.monotonic.return_value=750.01;return result
   fixture.owner.run_slice=late;loads=[];old_loader=M.load_exact.side_effect
   def loader(*args):loads.append(args[0]);return old_loader(*args)
   M.load_exact.side_effect=loader
   self.assertEqual(M.pipeline_main(author.SHA,author.DRIVER_SHA,100.0),1)
   self.assertEqual(loads,[fixture.root/M.OWNER])
   self.assertEqual([row[0] for row in fixture.events],['owner'])
   self.assertFalse(M.PIPELINE.exists());self.assertTrue(M.PIPELINE_FAILURE.exists())
   observations['late_owner_wall']=dict(parity_loaded=False,parity_called=False,failure_retained=True)

  def test_keyboardinterrupt_preserves_raw_cleanup_and_fails_once(self):
   fixture=author.OuterTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
   cleanup=dict(reaped=True,exit_code=0,retained_wait4_result=[123,0,1.25],actual_cpu=1.25,cleanup_nested_unknown=False,scope='original_scope_unchanged')
   error=KeyboardInterrupt('original interruption');error.supervisor_cleanup_evidence=cleanup;calls=[]
   def supervise(*args,**kwargs):calls.append(1);raise error
   with patch.object(M,'load_exact',return_value=SimpleNamespace(supervise=supervise)):
    self.assertEqual(M.outer_main(author.SHA,author.DRIVER_SHA),1)
   receipt=json.loads(M.PROCESS.read_bytes())
   self.assertEqual(receipt['supervisor_exception_cleanup_evidence'],cleanup)
   self.assertEqual(calls,[1]);self.assertFalse(M.DRIVER.exists());self.assertTrue(M.ERROR.exists())
   self.assertFalse(receipt['full_exit_acceptance_issued'])
   observations['interrupt']=dict(raw_cleanup_unchanged=True,attempts=1,no_success=True)

 selected=[(author.BudgetTests,'test_original_clock_not_future_reset_or_nonfinite'),(author.BudgetTests,'test_late_owner_stops_before_parity'),(author.BudgetTests,'test_parity_delta_retains_original_whole_baseline'),(author.PipelineTests,'test_owner_then_independent_checker_with_same_original_identity'),(author.OuterTests,'test_one_supervision_global_limits_raw_flags_preserved'),(author.OuterTests,'test_normal_reap_without_mandatory_parity_stops'),(author.OuterTests,'test_exception_cleanup_unknown_preserved_not_success'),(author.OuterTests,'test_existing_namespace_no_launch_or_overwrite')]
 suite=unittest.TestSuite([cls(method) for cls,method in selected]+[unittest.defaultTestLoader.loadTestsFromTestCase(IndependentTests)])
 with patch.object(sys,'stderr',log):result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
freshness()
u=resource.getrusage(resource.RUSAGE_SELF);c=resource.getrusage(resource.RUSAGE_CHILDREN)
cpu=u.ru_utime+u.ru_stime;elapsed=time.monotonic()-ENTRY;rss=u.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
safe=cpu<=15 and elapsed<=20 and rss<=512*2**20 and c.ru_utime+c.ru_stime==0 and c.ru_maxrss==0 and not violations
out=dict(status='PASS' if result.wasSuccessful() and safe else 'FAIL',methods=result.testsRun,selected_author_methods=8,independent_methods=3,failures=len(result.failures),errors=len(result.errors),observations=observations,guard_violations=violations,safety_ok=safe,process_cpu_seconds=cpu,elapsed_seconds=elapsed,process_peak_rss_bytes=rss,application_children=0,actual_data_model_target_native_backend_claim_project_work=0,input_hashes={p:e['sha256'] for p,e in files.items()},input_count=len(files),fixture_transport=dict(duplicate_author_30CPU60wall_fences_removed=removed,independent_stricter_fences=[15,20]),body_timing_not_full_exit=True,execution_grant=False)
p=Path('/tmp/tlab-development-whole018-v2-independent-probes')
with p.with_suffix('.json').open('x') as f:json.dump(out,f,sort_keys=True,indent=2);f.write('\n')
with p.with_suffix('.log').open('x') as f:f.write(log.getvalue())
print(json.dumps({k:out[k] for k in ['status','methods','failures','errors','guard_violations','process_cpu_seconds','elapsed_seconds','process_peak_rss_bytes','input_count']}))
if out['status']!='PASS':print(log.getvalue());raise SystemExit(1)
