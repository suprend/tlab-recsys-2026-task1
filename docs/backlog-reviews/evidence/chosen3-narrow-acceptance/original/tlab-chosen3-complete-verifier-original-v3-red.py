"""One bounded pure author suite; no native/process/DB/resource mutation."""
import time
PURE_ENTRY_CPU=time.process_time();PURE_ENTRY_WALL=time.monotonic()
import builtins
from contextlib import ExitStack
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import time
import types
import unittest
from unittest.mock import patch

CANDIDATE=Path('/tmp/tlab-chosen3-six-role-candidate-v4.py')
TEST=Path('/tmp/tlab-test-chosen3-six-role-candidate-v4.py')
OLD=Path('/tmp/tlab heldout six role integration 20261015')
NEW=Path('/tmp/tlab chosen3 W44 integration 20261015')
EXPECTED={str(CANDIDATE):'728a7b276655e6a625c9ae92130f37c2d4464f27fe601e140a1f56082abdfc64',
 str(TEST):'453de3d38b4f976bdff5df6578a75b5d70547b2bb51af2f51ce44b20c55f6f46',
 '/tmp/tlab-chosen3-integration-draft-freeze-v4.json':'3373f2e95fc2cca7ced9ba3b3e7b79c066c6dc0c29bb75437112d5fdc53b16aa',
 '/tmp/tlab-heldout-six-role-harness-freeze-v2.json':'49a95a26e9ec7a08b28ace4cbb673052b40c49e3043dcc8a243f959655defaf6',
 '/tmp/tlab-chosen3-six-role-candidate.py':'a80182e93dc60c493d5172a3824ae3f8229fffb5d47c5e0d95b37ce74f93dada',
 '/tmp/tlab-test-chosen3-six-role-candidate.py':'282b7228fd5ef3dd69b7b204899de58b6af99b6a0afafbf863fa03bab271e1eb',
 '/tmp/tlab-run-heldout-six-role-toy.py':'52a31321776652d97d0ce417748deb2fa13bb5fdf7a6fb8a8087d4d28e2ee6a8',
 '/tmp/tlab-heldout-harness-processes.py':'449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'}

EXPECTED.update({'/tmp/tlab-chosen3-six-role-candidate-v3.py': 'b40060a970546ea749291695bd60585b06ad7f1facdbf2388e6bfb1371f43a6d', '/tmp/tlab-test-chosen3-six-role-candidate-v3.py': 'e5cc579cf05ea19b6ac4d4943c412f6de7ba3a5ea53aedc8083fe46f3883e2ac', '/tmp/tlab-chosen3-integration-draft-freeze-v3.json': 'fc3a44a40b00b90dc0df7ddff0a5492772d3bfb802533a9523fb439c81737c8e', '/tmp/tlab-root-chosen3-v3-failed-external-receipt.json': 'd32348f7a3831216aa2efdac8c22da53216cc53f696c7dd349f351ef645ed789', '/tmp/tlab-root-chosen3-v3-setup-external-receipt.json': 'b71b722093361d404b290c6fffe52f77651f642e0c386deb52fc0815a38d258e', '/tmp/tlab-chosen3-v4-complete-json-fixture.json': '47476d48fd73ce4e64603703c53e32fb35f17f161c1a799a96741f8b130951af'})

def hashes():return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in EXPECTED}
def root_metadata():
    result={}
    for root in [OLD,NEW]:
        entries={}
        for p in [root,*sorted(root.rglob('*'))]:
            s=p.lstat();entries[str(p.relative_to(root))]=dict(mode=s.st_mode,size=s.st_size,mtime_ns=s.st_mtime_ns,symlink=os.readlink(p) if p.is_symlink() else None)
        result[str(root)]=entries
    return result
def write(path,body):
    with Path(path).open('x') as stream:json.dump(body,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')

pre=hashes();assert pre==EXPECTED
before=root_metadata();assert OLD.is_dir() and NEW.is_dir()
write('/tmp/tlab-chosen3-complete-verifier-original-v3-red-pre.json',dict(hashes=pre,original_root_metadata=before,consumed_roots_retained=True))
candidate_raw=CANDIDATE.read_bytes();test_raw=TEST.read_bytes()
assert hashlib.sha256(candidate_raw).hexdigest()==EXPECTED[str(CANDIDATE)]
assert hashlib.sha256(test_raw).hexdigest()==EXPECTED[str(TEST)]
calls={};denied_imports=[];original_import=builtins.__import__;original_read=Path.read_bytes
def forbid(name):
    def blocked(*args,**kwargs):calls[name]=calls.get(name,0)+1;raise AssertionError('Forbidden actual seam: '+name)
    return blocked
def imported(name,*args,**kwargs):
    if name.split('.')[0] in {'catboost','duckdb','sqlite3','requests','httpx','urllib','scripts'}:
        denied_imports.append(name);raise AssertionError('Forbidden native/DB/network/project import: '+name)
    return original_import(name,*args,**kwargs)
def pinned_read(path):
    return candidate_raw if path==CANDIDATE else original_read(path)
binary_suffixes={'.cbm','.duckdb','.npz','.npy','.parquet','.csv','.gz','.zip','.tar'}
original_path_open=Path.open;original_builtin_open=builtins.open;original_os_open=os.open

def deny_binary(path):
    if isinstance(path,(str,bytes,os.PathLike)) and Path(os.fsdecode(path)).suffix.lower() in binary_suffixes:
        calls['binary_open']=calls.get('binary_open',0)+1;raise AssertionError('Forbidden actual model/data binary open')
def path_open(path,*args,**kwargs):deny_binary(path);return original_path_open(path,*args,**kwargs)
def builtin_open(path,*args,**kwargs):deny_binary(path);return original_builtin_open(path,*args,**kwargs)
def os_open(path,*args,**kwargs):deny_binary(path);return original_os_open(path,*args,**kwargs)

cpu_start=PURE_ENTRY_CPU;wall_start=PURE_ENTRY_WALL;lines=0;trace_active=True
def bounded(frame,event,arg):
    global lines,trace_active
    if trace_active and event=='line':
        lines+=1
        if lines>5000000 or time.process_time()-cpu_start>2 or time.monotonic()-wall_start>5:
            trace_active=False;raise TimeoutError('Pure suite finite2CPU/5wall/5M-line bound')
    return bounded
stream=io.StringIO();result=None;unexpected=None
try:
    with ExitStack() as stack:
        for owner,names in [(ctypes,['CDLL','PyDLL']),(subprocess,['Popen','run','call','check_call','check_output']),
          (resource,['setrlimit','getrlimit','getrusage']),
          (os,['fork','forkpty','posix_spawn','posix_spawnp','system','wait4','kill','killpg']),
          (socket,['socket','create_connection','getaddrinfo'])]:
            for name in names:
                if hasattr(owner,name):stack.enter_context(patch.object(owner,name,side_effect=forbid(owner.__name__+'.'+name)))
        stack.enter_context(patch.object(Path,'open',path_open))
        stack.enter_context(patch.object(builtins,'open',builtin_open))
        stack.enter_context(patch.object(os,'open',os_open))
        stack.enter_context(patch.object(builtins,'__import__',side_effect=imported))
        stack.enter_context(patch.object(Path,'read_bytes',pinned_read))
        namespace=types.ModuleType('chosen3_bounded_author_tests');namespace.__file__=str(TEST)
        sys.settrace(bounded)
        exec(compile(test_raw,str(TEST),'exec',dont_inherit=True),namespace.__dict__)
        original_raw=Path('/tmp/tlab-chosen3-six-role-candidate-v3.py').read_bytes()
        assert hashlib.sha256(original_raw).hexdigest()=='b40060a970546ea749291695bd60585b06ad7f1facdbf2388e6bfb1371f43a6d'
        original=types.ModuleType('chosen3_exact_original_v3_complete_regression');original.__file__='/tmp/tlab-chosen3-six-role-candidate-v3.py'
        exec(compile(original_raw,original.__file__,'exec',dont_inherit=True),original.__dict__)
        namespace.c=original;namespace.source_raw=original_raw
        suite=unittest.TestSuite([namespace.Chosen3Contracts('test_complete_verify_results_returns_summary_from_full_production_JSON_scene')])
        assert suite.countTestCases()==1
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        sys.settrace(None)
except BaseException as error:
    sys.settrace(None);unexpected=dict(type=type(error).__name__,message=str(error))
finally:
    sys.settrace(None)
elapsed=time.monotonic()-wall_start;cpu=time.process_time()-cpu_start
after=root_metadata();post=hashes();same=after==before and post==pre and OLD.is_dir() and NEW.is_dir()
with Path('/tmp/tlab-chosen3-complete-verifier-original-v3-red.log').open('x') as out:out.write(stream.getvalue())
passed=result is not None and result.wasSuccessful() and result.testsRun==1 and not calls and not denied_imports and unexpected is None and same
receipt=dict(scope='new_complete_fixture_regression_on_exact_original_V3_expected_red_no_actual_job',status='pass' if passed else 'failed_stop_preserve',
 tests_run=result.testsRun if result else 0,failures=len(result.failures) if result else None,errors=len(result.errors) if result else None,
 elapsed_seconds=elapsed,process_cpu_seconds=cpu,line_events=lines,guard_attempt_counts=calls,denied_imports=denied_imports,unexpected=unexpected,
 pre_hashes=pre,post_hashes=post,original_root_metadata_unchanged=after==before,consumed_roots_retained=OLD.is_dir() and NEW.is_dir(),
 candidate_source_from_original_verified_snapshot=True,actual_fit_prediction_DB_process_backend_resource_calls=0,execution_authority=False)
write('/tmp/tlab-chosen3-complete-verifier-original-v3-red-result.json',receipt)
write('/tmp/tlab-chosen3-complete-verifier-original-v3-red-post.json',dict(hashes=post,original_root_metadata=after,consumed_roots_retained=OLD.is_dir() and NEW.is_dir()))
print(json.dumps({k:v for k,v in receipt.items() if k not in {'pre_hashes','post_hashes'}},sort_keys=True))
if not passed:raise SystemExit(1)
