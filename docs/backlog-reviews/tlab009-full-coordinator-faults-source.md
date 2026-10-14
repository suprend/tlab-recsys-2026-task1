# Historical independent synthetic fault harness

Only local paths were made portable. Run from the project root after extracting any dependent archived helper into the system temporary directory. Evidence belongs to the original f60b639f freeze in the [changes-requested review](tlab009-full-export-code-review.md); it deliberately records false accepts and accounting failures. Later fixes require a separate re-review. No real data/model execution or new acceptance is claimed by archiving.

```python
from pathlib import Path
import sys,tempfile,json
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()))
from scripts import metadata_price_collection as c
out={}
with tempfile.TemporaryDirectory() as temp:
 state={'failed':False}
 def cpu():
  if state['failed']:raise OSError('secondary stage CPU unavailable')
  return 0.
 def operation():
  state['failed']=True;raise ValueError('PRIMARY operation failure')
 try:
  with patch.object(c,'cpu_time',side_effect=cpu):
   with c.ExecutionAudit(Path(temp),seconds=10,scope='synthetic-review') as audit:
    audit.stage('fault',operation)
 except Exception as e:out['stage_primary_preservation']={'raised':type(e).__name__,'error':str(e),'report':audit.report}
with tempfile.TemporaryDirectory() as temp:
 clock=[0.]
 actual=c._atomic_json
 def writer(path,value):
  actual(path,value)
  if Path(path).name=='run.json':clock[0]+=10.
 try:
  with patch.object(c,'cpu_time',side_effect=lambda:clock[0]),patch.object(c,'_atomic_json',side_effect=writer):
   with c.ExecutionAudit(Path(temp),seconds=10,scope='synthetic-review') as audit:
    audit.manifest={'only':'synthetic'};audit.report['status']='complete_produced_unreviewed'
  out['terminal_cpu_record']={'status':audit.report['status'],'reported':audit.report['process_cpu_user_system_seconds'],'actual_mocked':clock[0]}
 except Exception as e:out['terminal_cpu_record']={'raised':type(e).__name__,'error':str(e)}
(Path(__import__('tempfile').gettempdir())/'tlab009-full-coordinator-fault-results.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:({q:v for q,v in value.items() if q!='report'}) for k,value in out.items()},indent=2))

```
