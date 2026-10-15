from pathlib import Path
import json,sys,tempfile
from unittest.mock import patch
project=Path(sys.argv[1]).resolve();sys.path.insert(0,str(project))
from scripts import heldout_reporting_worker as worker
from scripts import heldout_execution as x
observed=(project/'scripts/heldout_reporting_worker.py').read_bytes()
Path('/tmp/tlab-production-adapter-independent-v1-source.py').write_bytes(observed)
results=[]
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp).resolve()
 def save(name,body):
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(x.canonical(body)+'\n');return {'path':name,'sha256':x.sha(path)}
 code={}
 for name in ['scripts/heldout_reporting_worker.py','scripts/heldout_worker_context.py','scripts/heldout_execution.py','scripts/heldout_contract.py','uv.lock','pyproject.toml']:
  code[name]=save(name,{'synthetic_code':name})['sha256']
 request=save('fixture/request.json',{'code_fingerprints':code});context=save('fixture/context.json',{'role':'source','request':request})
 for case in ['control_absent_initializer','unlisted_scripts_initializer']:
  if case=='unlisted_scripts_initializer':(root/'scripts/__init__.py').write_text('raise AssertionError("unlisted execution before helper")\n')
  error=None
  with patch.object(worker,'ROOT',root):
   try:result=worker.bootstrap(root/context['path'],context['sha256'])
   except BaseException as value:error=type(value).__name__+': '+str(value);result=None
   finally:
    if str(root) in sys.path:sys.path.remove(str(root))
  results.append({'case':case,'accepted':error is None,'role':result,'error':error})
print(json.dumps({'scope':'bootstrap_only_no_imported_initializer_no_CLI_or_role_execution','source_sha256':__import__('hashlib').sha256(observed).hexdigest(),'results':results,'private_source_model_reads':0,'native_calls':0,'fits':0},indent=2))
