"""Exactly TWO authorized in-memory AST probes; no accepted-core/native execution."""
import time
ENTRY=time.monotonic()
import resource,signal
resource.setrlimit(resource.RLIMIT_CPU,(2,3));signal.alarm(4)
import ast
import builtins
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

manifest=Path('/tmp/tlab-public-frozen-comparison-review-b-input-freeze-v1.json')
assert hashlib.sha256(manifest.read_bytes()).hexdigest()=='a077410e8990b76d3f2b4ea8876e1630d97bb4b9531de4e896117f1891ceb664'
context=Path('/tmp/tlab-public-frozen-comparison-review-b-context-freeze-v1.json')
assert hashlib.sha256(context.read_bytes()).hexdigest()=='1c1b0f18b4cda9272d2003188be279f51494c51cc8c394626de46f4f0c0a05e6'
files={**json.loads(manifest.read_bytes())['files'],**json.loads(context.read_bytes())['files']};raws={}
def fresh():
 for name,e in files.items():
  raw=Path(name).read_bytes();assert raw==Path(e['snapshot_path']).read_bytes() and len(raw)==e['bytes'] and hashlib.sha256(raw).hexdigest()==e['sha256'],name
  raws[name]=raw
fresh()
source='/tmp/tlab-reproduce-frozen-comparison-v1.py';recipepath='/tmp/tlab-frozen-bw-oct2019-v1.json'
assert hashlib.sha256(raws[source]).hexdigest()=='5409bd4393bcaef2b455bef580e1f6ca9edb8b5e146e7fde617676c975a2c0b7'
whole=ast.parse(raws[source]);names={'need','read_json','file_ref','validate_recipe','run'}
functions=ast.Module(body=[n for n in whole.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
assert len(functions.body)==len(names)
recipe_raw=raws[recipepath];original=json.loads(recipe_raw)
violations=[]
def forbidden(*args,**kwargs):violations.append('forbidden import/operation');raise AssertionError('No native/core/child operation')
def fake_import(name,globals=None,locals=None,fromlist=(),level=0):
 if name=='importlib.metadata':return SimpleNamespace(version=lambda name:original['environment']['packages'][name])
 if name=='scripts.source_import':return SimpleNamespace(PRODUCTION_PROFILE=deepcopy(original['source']))
 return forbidden(name)
basebuiltins=dict(vars(builtins));basebuiltins['__import__']=fake_import
ns={'__builtins__':basebuiltins,'json':json,'hashlib':hashlib,'ROOT':'MOCKROOT','RECIPE_SHA256':hashlib.sha256(recipe_raw).hexdigest(),'sys':SimpleNamespace(version_info=(3,12))}
exec(compile(functions,source,'exec',dont_inherit=True),ns)

# PROBE 1: primary failure must remain primary when writer OR telemetry also fails.
class MockPath:
 def __init__(self,name):self.name=str(name)
 def absolute(self):return self
 def resolve(self):return self
 @property
 def parent(self):return MockPath('parent')
 def is_dir(self):return True
 def exists(self):return False
 def is_symlink(self):return False
 def mkdir(self,**kwargs):pass
 def __truediv__(self,part):return MockPath(self.name+'/'+part)
 def __str__(self):return self.name
ns['Path']=lambda value:value if isinstance(value,MockPath) else MockPath(value)
observations=[]
for primary,secondary,stage in [(KeyboardInterrupt('primary interruption'),OSError('secondary disk full'),'writer'),(RuntimeError('primary fit failure'),OSError('secondary write failure'),'writer'),(SystemExit('primary exit'),RuntimeError('secondary telemetry failure'),'telemetry')]:
 writes=[]
 def validate(path,check):raise primary
 def write(path,body):
  writes.append(str(path))
  if str(path).endswith('/failed.json') and stage=='writer':raise secondary
 def telemetry():
  if stage=='telemetry':raise secondary
  return {'fit_attempts':1}
 budget=SimpleNamespace(cpu_limit=1,wall_limit=1,rss_limit=1,spill_limit=8*2**30,check=lambda:None,telemetry=telemetry)
 ns.update(validate_recipe=validate,write_new=write)
 try:ns['run']('mockraw','mockout','mockrecipe',budget)
 except BaseException as escaped:
  observations.append({'primary_type':type(primary).__name__,'secondary_stage':stage,'secondary_type':type(secondary).__name__,'escaped_type':type(escaped).__name__,'escaped_is_primary':escaped is primary,'escaped_is_secondary':escaped is secondary,'synthetic_write_calls':writes})
 else:raise AssertionError('Expected concrete primary failure')
assert len(observations)==3 and all(not r['escaped_is_primary'] and r['escaped_is_secondary'] for r in observations)

# Restore exact extracted functions before PROBE 2; only RAM input bytes change.
exec(compile(functions,source,'exec',dont_inherit=True),ns)
changed=deepcopy(original);changed['k']=1
changed_raw=(json.dumps(changed,sort_keys=True)+'\n').encode();opened=[]
class RecipePath:
 def open(self,mode):
  assert mode=='rb';opened.append('hash_old_bytes');return io.BytesIO(recipe_raw)
 def read_text(self):opened.append('parse_changed_bytes');return changed_raw.decode()
class RootPath:
 def __truediv__(self,name):return name
rp=RecipePath();actual_file_ref=ns['file_ref']
ns.update(Path=lambda p:p,ROOT=RootPath())
def file_ref(path,check):
 if path is rp:return actual_file_ref(path,check)
 return {'sha256':original['dependencies'][path]}
ns['file_ref']=file_ref
accepted=ns['validate_recipe'](rp,lambda:None)
assert opened==['hash_old_bytes','parse_changed_bytes'] and accepted['k']==1 and original['k']==20
assert hashlib.sha256(changed_raw).hexdigest()!=ns['RECIPE_SHA256']
recipe_observation={'read_order':opened,'claimed_recipe_sha256':ns['RECIPE_SHA256'],'actually_parsed_sha256':hashlib.sha256(changed_raw).hexdigest(),'original_k':20,'accepted_changed_k':accepted['k'],'mutated_input_accepted':True,'all_dependencies_versions_source_profile_stayed_equal':True,'bytes_in_memory_only':True}
fresh()
u=resource.getrusage(resource.RUSAGE_SELF);c=resource.getrusage(resource.RUSAGE_CHILDREN);cpu=u.ru_utime+u.ru_stime;elapsed=time.monotonic()-ENTRY;rss=u.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
assert cpu<3 and elapsed<5 and rss<=128*2**20 and c.ru_utime+c.ru_stime==0 and c.ru_maxrss==0 and not violations
out={'scope':'TWO_authorized_pure_in_memory_AST_fault_probes','status':'both_source_defects_reproduced','expected_defect_assertions_passed':True,'probes':2,'primary_mask_observations':observations,'recipe_hash_parse_observation':recipe_observation,'source_sha256':hashlib.sha256(raws[source]).hexdigest(),'input_count':len(files),'initial_final_hashes_unchanged':True,'input_hashes':{p:e['sha256'] for p,e in files.items()},'guard_violations':violations,'actual_native_raw_DB_models_Y_acceptedcore_children_project_operations':0,'application_children':0,'execution_grant':False,'body_timing_not_full_exit':{'cpu_seconds':cpu,'wall_seconds':elapsed,'peak_rss_bytes':rss},'bounds':{'cpu_seconds':3,'wall_seconds':5,'rss_bytes':128*2**20}}
p=Path('/tmp/tlab-public-frozen-comparison-review-b-two-probes-v1.json')
with p.open('x') as s:json.dump(out,s,sort_keys=True,indent=2);s.write('\n')
print(json.dumps({k:out[k] for k in ['status','probes','input_count','application_children','body_timing_not_full_exit']}))
