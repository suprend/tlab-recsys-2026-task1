"""ONE bounded environment-policy test process; raw source, pure mocked OS."""
import time
START=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(9,10))
import signal
signal.alarm(14)
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

SOURCE=Path('/tmp/tlab-real015-existing-v6-driver-v4.py');RAW=SOURCE.read_bytes()
SOURCE_SHA=hashlib.sha256(RAW).hexdigest()
V3=Path('/tmp/tlab-real015-existing-v6-driver-v3.py').read_bytes()
assert hashlib.sha256(V3).hexdigest()=='7ba7ffec6654515715b1d30be88eb54819ac31d0d1e9cf94a4388e43dffde7fa'
d=ModuleType('environment_guard_v4');d.__file__=str(SOURCE);sys.modules[d.__name__]=d
exec(compile(RAW,str(SOURCE),'exec',dont_inherit=True),d.__dict__)
VIOLATIONS=[]
def forbidden(*args,**kwargs):
    VIOLATIONS.append('unmocked operation');raise AssertionError('No process/backend/native/job allowed')

class Environment(unittest.TestCase):
    def validate(self,extra=None,platform='darwin',uid=501,euid=501,actual=None):
        value=({**d.environment(),**(extra or {})} if actual is None else actual)
        before=dict(value)
        with patch.object(d.sys,'platform',platform),patch.object(d.os,'getuid',return_value=uid),patch.object(d.os,'geteuid',return_value=euid):
            result=d.validate_child_environment(value)
        self.assertEqual(value,before);return result
    def test_exact_curated_environment_remains_valid_on_all_platforms(self):
        for platform in ['darwin','linux','win32']:self.assertTrue(self.validate(platform=platform))
    def test_observed_extra_key_in_strict_mock_Darwin_format_accepted(self):
        for value in ['0x1F5:0x0:0x0','0x1f5:0xA:0xB','0x000001F5:0xFFFFFFFF:0x00000000']:
            with self.subTest(value=value):self.assertTrue(self.validate({'__CF_USER_TEXT_ENCODING':value}))
    def test_each_missing_or_changed_curated_key_rejected(self):
        original=d.environment()
        for name in original:
            with self.subTest(name=name,kind='missing'):
                actual=dict(original);actual.pop(name)
                with self.assertRaisesRegex(ValueError,'curated'):self.validate(actual=actual)
            with self.subTest(name=name,kind='changed'):
                actual={**original,name:original[name]+'-changed'}
                with self.assertRaisesRegex(ValueError,'curated'):self.validate(actual=actual)
    def test_other_extras_and_Python_locale_changes_rejected(self):
        for extra in [{'PYTHONPATH':'unexpected'},{'LC_CTYPE':'unexpected'},{'OTHER':'1'},
                      {'__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0','OTHER':'1'}]:
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError,'Unexpected'):self.validate(extra)
    def test_malformed_CF_and_non_string_values_rejected(self):
        for value in ['', '501:0x0:0x0','0x1F5:0:0','0x1F5:0x0','0x1F5:0x0:0x0:0x0',
                      '0x1F5:0x0:0x0 ','0x1F5:0x0:0x0\n','0x1F5:0x-1:0x0','0x1F5:0xG:0x0',
                      '0X1F5:0x0:0x0','0x1F5:0x100000000:0x0','0x1F5:0x:0x0',None,True,501]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):self.validate({'__CF_USER_TEXT_ENCODING':value})
    def test_wrong_real_UID_or_effective_UID_rejected(self):
        for extra,uid,euid in [({'__CF_USER_TEXT_ENCODING':'0x1F6:0x0:0x0'},501,501),
                               ({'__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},501,0)]:
            with self.assertRaisesRegex(ValueError,'UID differs'):self.validate(extra,uid=uid,euid=euid)
    def test_CF_key_rejected_on_non_Darwin(self):
        for platform in ['linux','win32','freebsd']:
            with self.assertRaisesRegex(ValueError,'Unexpected'):self.validate({'__CF_USER_TEXT_ENCODING':'0x1F5:0x0:0x0'},platform=platform)
    def test_controller_rejects_before_consumption_write_or_owner_launch(self):
        with patch.object(d,'check_fixed',return_value={}),patch.dict(os.environ,{**d.environment(),'OTHER':'1'},clear=True),\
             patch.object(d,'write') as write,patch.object(d.subprocess,'Popen',side_effect=forbidden) as popen:
            with self.assertRaisesRegex(ValueError,'Unexpected'):d.controller('a'*64)
        write.assert_not_called();popen.assert_not_called()
    def test_exact_AST_delta_only_helper_guard_SELF_OUT(self):
        old=ast.parse(V3);new=ast.parse(RAW);normal=copy.deepcopy(new)
        normal.body=[n for n in normal.body if not(isinstance(n,ast.FunctionDef) and n.name=='validate_child_environment')]
        replacements={str(d.SELF):'/tmp/tlab-real015-existing-v6-driver-v3.py',str(d.OUT):'/tmp/tlab-real015-observer-original-20261015'}
        literal_count=0;guard_count=0
        class Restore(ast.NodeTransformer):
            def visit_Constant(self,node):
                nonlocal literal_count
                if type(node.value) is str and node.value in replacements:
                    node.value=replacements[node.value];literal_count+=1
                return node
            def visit_Call(self,node):
                nonlocal guard_count
                if isinstance(node.func,ast.Name) and node.func.id=='validate_child_environment':
                    guard_count+=1;return ast.parse('dict(os.environ)==environment()',mode='eval').body
                return self.generic_visit(node)
        normal=Restore().visit(normal)
        self.assertEqual((literal_count,guard_count),(2,1))
        self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(normal,include_attributes=False))

with patch.object(subprocess,'Popen',side_effect=forbidden),patch.object(os,'wait4',side_effect=forbidden),\
     patch.object(os,'fork',side_effect=forbidden),patch.object(os,'system',side_effect=forbidden),\
     patch.object(socket.socket,'connect',side_effect=forbidden):
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Environment))
assert SOURCE.read_bytes()==RAW
r=resource.getrusage(resource.RUSAGE_SELF);c=resource.getrusage(resource.RUSAGE_CHILDREN)
cpu=r.ru_utime+r.ru_stime;wall=time.monotonic()-START;rss=r.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
safe=cpu<10 and wall<15 and rss<=128*2**20 and c.ru_utime+c.ru_stime==0 and c.ru_maxrss==0 and not VIOLATIONS
value=dict(scope='V4_environment_only_pure_mock_CODE_candidate',status='PASS' if result.wasSuccessful() and safe else 'FAIL',
 tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),CPU_seconds=cpu,wall_seconds=wall,peak_RSS_bytes=rss,
 bounds=dict(CPU_seconds=10,wall_seconds=15,RSS_bytes=128*2**20),source_sha256=SOURCE_SHA,
 guard_violations=VIOLATIONS,source_initial_final_bytes_identical=True,AST_only_helper_guard_SELF_OUT=True,
 observed_key_name_only=True,actual_CF_runtime_value_not_read_or_claimed=True,
 actual_child_backend_native_owner_439_data_model_Y_claim_gate_project_work=0,actual_recovery_granted=False)
Path('/tmp/tlab-real015-existing-v6-driver-v4-environment-result.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps(value,sort_keys=True));raise SystemExit(0 if value['status']=='PASS' else 1)
