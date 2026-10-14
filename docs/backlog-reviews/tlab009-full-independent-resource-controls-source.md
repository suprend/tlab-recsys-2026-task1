# Historical independent synthetic fault harness

Only local paths were made portable. Run from the project root after extracting any dependent archived helper into the system temporary directory. Evidence belongs to the original f60b639f freeze in the [changes-requested review](tlab009-full-export-code-review.md); it deliberately records false accepts and accounting failures. Later fixes require a separate re-review. No real data/model execution or new acceptance is claimed by archiving.

```python
import sys,json,time,resource,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd().resolve()))
from scripts import metadata_price_collection as c
start=time.monotonic();cpu=time.process_time();results=[]
for name in ['close_wall','close_CPU','close_RSS','close_error','manifest_write_error','report_write_overrun']:
 with tempfile.TemporaryDirectory() as tmp:
  path=Path(tmp)/'out';wall=time.monotonic;offset=[0.];counter=[0.];rss=[0];done=[False];raised=None
  def writer(p,value):
   p.write_text(json.dumps(value)+'\n')
   if p.name=='run.json' and name=='manifest_write_error':raise OSError('INDEPENDENT manifest failure')
   if p.name=='report.json' and value.get('status')=='complete_produced_unreviewed' and name=='report_write_overrun' and not done[0]:offset[0]+=1300;done[0]=True
  class Connection:
   def close(self):
    if name=='close_wall':offset[0]+=1300
    if name=='close_CPU':counter[0]+=901
    if name=='close_RSS':rss[0]=8*2**30+1
    if name=='close_error':raise OSError('INDEPENDENT close failure')
  try:
   with patch.object(c.time,'monotonic',side_effect=lambda:wall()+offset[0]),patch.object(c,'cpu_time',side_effect=lambda:counter[0]),patch.object(c,'peak_rss_bytes',side_effect=lambda:rss[0]),patch.object(c,'_atomic_json',side_effect=writer):
    with c.ExecutionAudit(path,seconds=1200,scope='independent',cpu_seconds=900) as a:
     a.connection=Connection();a.manifest={'synthetic':True};a.report['status']='complete_produced_unreviewed'
  except Exception as e:raised=type(e).__name__+': '+str(e)
  disk=json.loads(next(path.glob('*/report.json')).read_text());results.append(dict(case=name,raised=raised,status=disk['status'],CPU=disk.get('process_cpu_user_system_seconds'),wall=disk.get('seconds')))
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab009-full-independent-resource-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
assert all(x['raised'] is not None and x['status']=='failed' for x in results)

```
