"""One bounded independent narrow environment-policy process; no actual job."""
import time
ENTRY=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(9,10))
import signal
signal.alarm(14)
import ast
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import os
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

BASE='/tmp/tlab-real015-existing-v6-driver-v4-independent'
manifest=Path(BASE+'-inputs/input-freeze.json')
assert hashlib.sha256(manifest.read_bytes()).hexdigest()=='1ed58125e9b103a74262b0d382d99070d71875704716a1ea2a53869b43579f1c'
files=json.loads(manifest.read_bytes())['files'];raws={}
def freshness():
 for name,e in files.items():
  raw=Path(name).read_bytes();assert raw==Path(e['snapshot_path']).read_bytes() and len(raw)==e['bytes'] and hashlib.sha256(raw).hexdigest()==e['sha256'],name
  raws[name]=raw
freshness()
source='/tmp/tlab-real015-existing-v6-driver-v4.py';test='/tmp/tlab-test-real015-existing-v6-driver-v4-environment.py'
assert hashlib.sha256(raws[source]).hexdigest()=='c00775f4ac0127b565c73b211d1783cde46fd4c357841c788050d2eac0d93428'
assert hashlib.sha256(raws[test]).hexdigest()=='b9f6563c85f7d0fad6dbf1f62f7d9c594633485f00e51cf7968f3f1d885fa5a8'
tree=ast.parse(raws[test]);original_methods={n.name:ast.dump(n) for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef)}
kept=[];fences=0;terminal=0
for n in tree.body:
 if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and (n.value.func.value.id,n.value.func.attr) in {('resource','setrlimit'),('signal','alarm')}:fences+=1;continue
 if isinstance(n,ast.Raise):terminal+=1;continue
 kept.append(n)
tree.body=kept
paths=0
for n in ast.walk(tree):
 if isinstance(n,ast.Constant) and n.value=='/tmp/tlab-real015-existing-v6-driver-v4-environment-result.json':n.value=BASE+'-author-9-result.json';paths+=1
assert (fences,terminal,paths)==(2,1,1)
assert original_methods=={n.name:ast.dump(n) for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef)}
violations=[]
def forbidden(*args,**kwargs):violations.append('actual process/network operation');raise AssertionError('No actual child/native/backend/job')
def read_frozen(path):
 key=str(path)
 if key not in raws:raise AssertionError('Unexpected runtime external read '+key)
 return raws[key]
namespace=dict(__name__='independent_frozen_V4_environment',__file__=test)
with ExitStack() as stack:
 for module,name in [(subprocess,'Popen'),(subprocess,'run'),(os,'wait4'),(os,'fork'),(os,'system'),(os,'posix_spawn'),(os,'posix_spawnp'),(socket,'create_connection')]:
  if hasattr(module,name):stack.enter_context(patch.object(module,name,side_effect=forbidden))
 stack.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden))
 stack.enter_context(patch.object(Path,'read_bytes',read_frozen))
 exec(compile(tree,test,'exec',dont_inherit=True),namespace)
 assert namespace['value']['status']=='PASS' and namespace['value']['tests']==9
 d=namespace['d']
 class IndependentEnvironment(unittest.TestCase):
  def validate(self,actual,uid=501,euid=501):
   before=dict(actual)
   with patch.object(d.sys,'platform','darwin'),patch.object(d.os,'getuid',return_value=uid),patch.object(d.os,'geteuid',return_value=euid):
    try:return d.validate_child_environment(actual)
    finally:self.assertEqual(dict(actual),before)
  def test_exact_32_character_boundary_and_unsigned_UID(self):
   value='0x000001f5:0xffffffff:0x12345678';self.assertEqual(len(value),32)
   self.assertTrue(self.validate({**d.environment(),'__CF_USER_TEXT_ENCODING':value}))
   self.assertTrue(self.validate({**d.environment(),'__CF_USER_TEXT_ENCODING':'0xffffffff:0x0:0x0'},uid=2**32-1,euid=2**32-1))
   for value in ['0x0000001f5:0x0:0x0','0x1f5:0x\u0661:0x0','0x1f5:0x0:0x0\t']:
    with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Malformed'):self.validate({**d.environment(),'__CF_USER_TEXT_ENCODING':value})
  def test_exact_mapping_and_string_types_fail_without_mutation(self):
   class Mapping(dict):pass
   class String(str):pass
   curated=d.environment()
   for actual in [Mapping(curated),{**curated,'LANG':String('C')},{**curated,String('EXTRA'):'x'},{**curated,'__CF_USER_TEXT_ENCODING':String('0x1f5:0x0:0x0')}]:
    with self.subTest(kind=type(actual).__name__),self.assertRaisesRegex(ValueError,'Exact string'):self.validate(actual)
  def test_optional_CF_failures_precede_consumption_and_owner_call(self):
   for value,expected in [('0x1f6:0x0:0x0','UID differs'),('0x1f5:0xG:0x0','Malformed')]:
    with self.subTest(value=value),patch.object(d,'check_fixed',return_value={}),patch.dict(d.os.environ,{**d.environment(),'__CF_USER_TEXT_ENCODING':value},clear=True),patch.object(d.sys,'platform','darwin'),patch.object(d.os,'getuid',return_value=501),patch.object(d.os,'geteuid',return_value=501),patch.object(d,'write') as write,patch.object(d.subprocess,'Popen',side_effect=forbidden) as popen:
     with self.assertRaisesRegex(ValueError,expected):d.controller('a'*64)
     write.assert_not_called();popen.assert_not_called()
 independent=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IndependentEnvironment))
freshness()
u=resource.getrusage(resource.RUSAGE_SELF);c=resource.getrusage(resource.RUSAGE_CHILDREN);cpu=u.ru_utime+u.ru_stime;wall=time.monotonic()-ENTRY;rss=u.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
assert independent.wasSuccessful() and independent.testsRun==3 and not violations
assert cpu<10 and wall<15 and rss<=128*2**20 and c.ru_utime+c.ru_stime==0 and c.ru_maxrss==0
proof=dict(scope='independent_V4_environment_narrow_CODE_rereview',status='PASS',source_sha256=hashlib.sha256(raws[source]).hexdigest(),author_methods=9,independent_methods=3,unique_methods=12,failures=0,errors=0,guard_violations=violations,original_author_method_AST_identity=True,transport=['duplicate fences omitted under existing9/10CPU14wall bounds','one result path changed to new independent TMP output','one terminal SystemExit omitted to run3independentmethods in SAME process'],process_cpu_seconds=cpu,elapsed_seconds=wall,peak_RSS_bytes=rss,input_count=len(files),input_hashes={p:e['sha256'] for p,e in files.items()},actual_child_backend_native_owner_439_data_model_Y_claim_gate_project_operations=0,actual_CF_value_not_read_or_claimed=True,execution_grant=False,body_timing_not_full_exit=True)
with Path(BASE+'-result.json').open('x') as s:json.dump(proof,s,sort_keys=True,indent=2);s.write('\n')
print(json.dumps({k:proof[k] for k in ['status','author_methods','independent_methods','unique_methods','process_cpu_seconds','elapsed_seconds','peak_RSS_bytes']}))
