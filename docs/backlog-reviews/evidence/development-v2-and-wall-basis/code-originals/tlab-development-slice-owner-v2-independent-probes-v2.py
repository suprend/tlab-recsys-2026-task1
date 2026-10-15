"""Frozen pure/mock owner checks plus source-only portable transport comparison."""
import time
ENTRY=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(30,30))
import signal
signal.alarm(60)
import ast
import builtins
from contextlib import ExitStack
from copy import deepcopy
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

manifest_pins={
 '/tmp/tlab-development-slice-owner-v2-independent-inputs/input-freeze.json':'a993d9727bd8975eae51ee5a931a09aca609d15a8fe3cac591f6a6a3f0ad9ab7',
 '/tmp/tlab-development-slice-owner-v2-independent-portable-inputs/input-freeze.json':'a5802ccb93a39c92a99a32b25e26fc0af457d8c173390e0a541c1b0c9ab7dfe2'}
files={};raws={}
for path,sha in manifest_pins.items():
 raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==sha
 for name,e in json.loads(raw)['files'].items():
  if name in files:assert files[name]['sha256']==e['sha256']
  files[name]=e
def freshness():
 for name,e in files.items():
  raw=Path(name).read_bytes();copy=Path(e['snapshot_path']).read_bytes()
  assert raw==copy and len(raw)==e['bytes'] and hashlib.sha256(raw).hexdigest()==e['sha256']
  raws[name]=copy
freshness()
violations=[];observations={}
def forbidden(label):
 def fail(*args,**kwargs):violations.append(label);raise AssertionError('Forbidden actual operation: '+label)
 return fail
real_import=builtins.__import__
def safe_import(name,*args,**kwargs):
 if name=='scripts' or name.startswith('scripts.') or name.split('.')[0] in {'duckdb','numpy','pandas','catboost','torch','ctypes'}:return forbidden('import '+name)()
 return real_import(name,*args,**kwargs)
real_read=Path.read_bytes
def frozen_read(path):
 if str(path) in raws:return raws[str(path)]
 if str(path).startswith(('/tmp/','/private/tmp/')) or path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):return real_read(path)
 return forbidden('nonfrozen read '+str(path))()

author=ModuleType('independent_frozen_owner_author_tests');author.__file__='/tmp/test_tlab_development_slice_owner_v2.py';sys.modules[author.__name__]=author
log=io.StringIO()
with ExitStack() as guards:
 guards.enter_context(patch.object(builtins,'__import__',side_effect=safe_import))
 guards.enter_context(patch.object(Path,'read_bytes',frozen_read))
 for module,name in [(subprocess,'Popen'),(os,'system'),(os,'fork'),(os,'posix_spawn'),(os,'posix_spawnp'),(os,'kill'),(os,'wait4'),(socket,'create_connection')]:
  if hasattr(module,name):guards.enter_context(patch.object(module,name,side_effect=forbidden(module.__name__+'.'+name)))
 guards.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden('network connect')))
 exec(compile(raws[author.__file__],author.__file__,'exec',dont_inherit=True),author.__dict__)
 M=author.M
 class IndependentOwnerTests(unittest.TestCase):
  def test_exact_real_small_handoff_authenticates_with_all_paid_IO_mocked(self):
   root=Path('/Users/mdpospelov/tlab-recsys-2026')
   handoff=json.loads(raws['/tmp/tlab-root-development-day-reference-handoff-prepared.json'])
   value=author.request()
   for key in ['source','models','manual_registry','pool_contract']:value[key]=deepcopy(handoff[key])
   value['comparison']['references']=deepcopy(handoff['reference_artifacts'])
   value['comparison']['required_checks']=handoff['mandatory_parity']
   value['environment']['python_version']=list(sys.version_info[:3])
   M._owner_request(value)
   receipt=json.loads(raws['/tmp/tlab-root-full-source018-source-prefix-acceptance.json'])
   dbpath=str(root/value['source']['database']['path'])
   dbstat=next(row['stat'] for row in receipt['large_current_bindings'] if row['path']==dbpath)
   bodies={value['protocol']['path']:json.loads(raws[str(root/'configs/protocols/clock-48h.json')]),value['manual_registry']['path']:json.loads(raws[str(root/'configs/features/manual-18.json')]),value['pool_contract']['path']:json.loads(raws[str(root/'configs/features/automation-pool.json')]),value['reference_handoff']['path']:handoff,value['source']['prefix_acceptance']['path']:receipt,value['source']['kernel_evidence']['path']:json.loads(raws[str(root/value['source']['kernel_evidence']['path'])])}
   hashed=[];small=[]
   def fake_stat(path):return deepcopy(dbstat if str(path)==dbpath else dict(device=1,inode=2,size_bytes=3,mtime_ns=4,ctime_ns=5))
   def fake_hash(path,sha,check):check();hashed.append(str(path));return dict(sha256=sha,stat=fake_stat(path))
   def fake_small(path,sha):
    name=path.relative_to(root).as_posix();small.append(name);body=deepcopy(bodies[name]);return body,json.dumps(body).encode()
   with patch.object(M,'_owner_path',side_effect=lambda root,name:root/name),patch.object(M,'_owner_stat',side_effect=fake_stat),patch.object(M,'_owner_hash',side_effect=fake_hash),patch.object(M,'_owner_small',side_effect=fake_small),patch.object(M.importlib.metadata,'version',side_effect=lambda name:value['environment']['packages'][name]):
    loaded,pins=M._owner_authenticate(root,value,SimpleNamespace(check=lambda:None))
   self.assertEqual(len(hashed),22)
   self.assertEqual(len(small),6)
   self.assertEqual(len(pins),28)
   old_leaves=[]
   for key,ref in value['comparison']['references'].items():
    if type(ref) is dict:old_leaves.append(str(root/ref['path']))
    elif type(ref) is list and ref and type(ref[0]) is dict:old_leaves.extend(str(root/x['path']) for x in ref)
   self.assertFalse(set(old_leaves)&set(hashed))
   self.assertEqual(loaded['reference_handoff'],handoff)
   observations['real_small_handoff_auth']=dict(paid_IO_mocked=True,closed_hash_calls=22,small_metadata_reads=6,pins=28,old_references_not_hashed_before_fresh_core=True)

  def test_consumed_nonce_exists_before_mock_paid_work_and_interrupt_retained(self):
   fixture=author.MockPublicEntry()
   with tempfile.TemporaryDirectory(prefix='tlab-owner-independent-once-') as folder:
    root,value,sha=fixture.fixture(folder);paid=[]
    exc=KeyboardInterrupt('original synthetic interrupt')
    def auth(root,request,checks):
     out=root/request['output_directory']
     self.assertEqual(json.loads((out/'consumed.json').read_text())['original_request_sha256'],sha)
     self.assertEqual(hashlib.sha256((out/'request-snapshot.json').read_bytes()).hexdigest(),sha)
     paid.append('mock-authentication');raise exc
    with patch.object(M,'__file__',str(root/M.OWNER_FILE)),patch.object(M.sys,'pycache_prefix',None),patch.object(M,'_owner_authenticate',side_effect=auth):
     with self.assertRaises(KeyboardInterrupt) as caught:M.run_slice('request.json',sha,started_monotonic=time.monotonic())
     self.assertIs(caught.exception,exc)
     with self.assertRaises(FileExistsError):M.run_slice('request.json',sha,started_monotonic=time.monotonic())
    self.assertEqual(paid,['mock-authentication'])
    failure=json.loads((root/value['output_directory']/'failure.json').read_text())
    self.assertEqual(failure['error_type'],'KeyboardInterrupt')
    observations['nonce_before_paid_work']=dict(attempts=len(paid),interrupt_preserved=True,second_entry_rejected=True)

  def test_failure_report_error_does_not_mask_primary_interruption_or_refill(self):
   fixture=author.MockPublicEntry()
   with tempfile.TemporaryDirectory(prefix='tlab-owner-independent-failure-') as folder:
    root,value,sha=fixture.fixture(folder);primary=KeyboardInterrupt('primary marker');write=M._owner_write
    def execute(root,out,value,loaded,checks,progress):progress['native_prediction_attempts']=1;raise primary
    def fail_report(path,body):
     if path.name=='failure.json':raise OSError('synthetic persistence failure')
     return write(path,body)
    with patch.object(M,'__file__',str(root/M.OWNER_FILE)),patch.object(M,'_owner_runtime'),patch.object(M,'_owner_authenticate',return_value=({},{})),patch.object(M,'_owner_execute',side_effect=execute),patch.object(M,'_owner_write',side_effect=fail_report):
     with self.assertRaises(KeyboardInterrupt) as caught:M.run_slice('request.json',sha,started_monotonic=time.monotonic())
    self.assertIs(caught.exception,primary)
    self.assertIn('OSError',primary.failure_report_error)
    self.assertTrue((root/value['output_directory']/'consumed.json').exists())
    observations['secondary_reporting_failure']=dict(primary_preserved=True,failure_report_error=primary.failure_report_error,consumption_retained=True)

  def test_source_close_failure_preserves_active_primary_error(self):
   schema=[(row['name'],row['type']) for row in json.loads(raws['/Users/mdpospelov/tlab-recsys-2026/artifacts/source-import-runs/oct2019-full-018-20261015-once/kernel/import-evidence.json'])['schema']]
   class FakeConnection:
    def execute(self,sql):self.sql=sql;return self
    def fetchall(self):return schema
    def close(self):raise OSError('synthetic close failure')
   con=FakeConnection();cores=SimpleNamespace(programs=SimpleNamespace(generate_pool=lambda *args:{}),duckdb=SimpleNamespace(connect=lambda *args,**kwargs:con))
   loaded=dict(protocol=dict(query=dict(eligibility_hours=48,sampling='sha256_user_day_seed_before_labels',sample_seed=2026)),pool_contract={},manual_registry={})
   primary=RuntimeError('original core failure');progress=dict(model_load_attempts=0,native_prediction_attempts=0,native_prediction_returns=0,source_connection_opened_read_only=False,source_connection_closed=False)
   with tempfile.TemporaryDirectory(prefix='tlab-owner-independent-close-') as folder:
    root=Path(folder);out=root/'out';out.mkdir();checks=M._OwnerChecks(author.request()['resources'],time.monotonic(),out/'spill')
    with patch.object(M,'_owner_fixed_cores',return_value=cores),patch.object(M,'build_and_score',side_effect=primary):
     with self.assertRaises(RuntimeError) as caught:M._owner_execute(root,out,author.request(),loaded,checks,progress)
   self.assertIs(caught.exception,primary)
   self.assertTrue(progress['source_connection_opened_read_only'])
   self.assertFalse(progress['source_connection_closed'])
   self.assertIn('OSError',progress['connection_close_error'])
   observations['close_failure']=deepcopy(progress)

  def test_changed_pin_stops_before_rehash_and_no_adopted_identity(self):
   with tempfile.TemporaryDirectory(prefix='tlab-owner-independent-repin-') as folder:
    root=Path(folder);path=root/'metadata.json';path.write_bytes(b'original')
    initial=M._owner_hash(path,hashlib.sha256(b'original').hexdigest(),lambda:None)
    path.write_bytes(b'changed!')
    stat=path.stat();os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000))
    with patch.object(M,'_owner_hash') as rehash:
     with self.assertRaisesRegex(ValueError,'stat changed'):M._owner_repin(root,{}, {'metadata.json':initial},SimpleNamespace(check=lambda:None))
     rehash.assert_not_called()
   observations['changed_pin']=dict(rejected_before_rehash=True,new_identity_not_adopted=True)

  def test_portable_nine_case_bodies_unchanged_after_declared_context_transport(self):
   old=ast.parse(raws['/tmp/tlab-test-reproduce-development-slice-v1.py']);new=ast.parse(raws['/tmp/test_reproduce_development_slice_portable_v1.py'])
   def methods(tree):return {node.name:node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name.startswith('test_')}
   before,after=methods(old),methods(new);self.assertEqual(set(before),set(after));self.assertEqual(len(after),9)
   class Normalize(ast.NodeTransformer):
    mapping={'FIXTURE':'root','CORES':'cores','MODEL_CALLS':'model_calls','anchor_pilot':'anchors','duckdb':'duckdb','inference_data':'inference','stage':'stage'}
    def visit_Name(self,node):
     if isinstance(node.ctx,ast.Load) and node.id in self.mapping:return ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr=self.mapping[node.id],ctx=node.ctx)
     if node.id=='guard':return ast.Lambda(args=ast.arguments(posonlyargs=[],args=[],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[]),body=ast.Constant(None))
     return node
   for name in sorted(before):self.assertEqual(ast.dump(Normalize().visit(before[name])),ast.dump(after[name]),name)
   top_imports=[alias.name for node in new.body if isinstance(node,(ast.Import,ast.ImportFrom)) for alias in node.names]
   self.assertFalse(set(top_imports)&{'resource','signal','duckdb','numpy','pandas'})
   text=raws['/tmp/test_reproduce_development_slice_portable_v1.py'].decode()
   self.assertNotIn('/tmp/',text);self.assertNotIn('/Users/',text);self.assertNotIn('sys.path',text);self.assertNotIn('pycache',text)
   observations['portable_transport']=dict(unchanged_normalized_intent_cases=9,native_test_rerun=False,no_TMP_proof_dependency=True,three_class_patch_cleanups_registered=True)

 suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(author),unittest.defaultTestLoader.loadTestsFromTestCase(IndependentOwnerTests)])
 result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)

freshness()
usage=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
cpu=usage.ru_utime+usage.ru_stime;elapsed=time.monotonic()-ENTRY;rss=usage.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
assert cpu<=30 and elapsed<=60 and rss<=512*2**20
safety_ok=children.ru_utime+children.ru_stime==0 and children.ru_maxrss==0 and not violations
out=dict(status='PASS' if result.wasSuccessful() and safety_ok else 'FAIL',methods=result.testsRun,author_methods=21,independent_owner_methods=5,portable_AST_methods=1,failures=len(result.failures),errors=len(result.errors),observations=observations,freshness_input_count=len(files),input_hashes={p:e['sha256'] for p,e in files.items()},guard_violations=violations,process_cpu_seconds=cpu,elapsed_seconds=elapsed,process_peak_rss_bytes=rss,application_children=0,actual_native_DB_CBM_NPZ_Parquet_large_hash_claim_project_work=0,body_timing_not_external_full_exit=True,execution_grant=False)
prefix=Path('/tmp/tlab-development-slice-owner-v2-independent-probes-v2')
with prefix.with_suffix('.log').open('x') as stream:stream.write(log.getvalue())
with prefix.with_suffix('.json').open('x') as stream:json.dump(out,stream,sort_keys=True,indent=2);stream.write('\n')
print(json.dumps({k:out[k] for k in ['status','methods','failures','errors','process_cpu_seconds','elapsed_seconds','process_peak_rss_bytes','guard_violations','freshness_input_count']}))
if out['status']!='PASS':
 print(log.getvalue());print(json.dumps(dict(violations=violations,children_cpu=children.ru_utime+children.ru_stime,children_peak=children.ru_maxrss)))
 raise SystemExit(1)
