# Independent targeted audit source archive

Historical exact-version audit; only machine paths are portable. Dependent archived scripts must be extracted to the system temporary directory before use. Original false accepts remain evidence for their original versions; later fixes have separate reviews. No source/model execution or new acceptance is claimed by archiving.

```python
import sys,json,time,resource,contextlib,io,hashlib,tempfile,ast,threading,uuid,types
from pathlib import Path,PurePosixPath
from datetime import datetime,timedelta
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd().resolve()))
from tests.test_metadata_price_collection import FullExportTests
from scripts import metadata_price_collection as c

def read(p):return json.loads(p.read_text())
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def write(p,v):p.write_text(enc(v)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def approval(f,d):
 manifest=read(d/'run.json');pins=dict(manifest['identity']['fingerprints']);r=manifest['execution_approval'];pins[r['path']]=r['sha256']
 for days in manifest['outputs'].values():
  for day in days:
   for a in day['artifacts'].values():pins[a['path']]=a['sha256']
 for p in [d/'run.json',d/'report.json']:pins[str(p.relative_to(f.root))]=sha(p)
 ap=f.root/'independent-final-marker-acceptance.json';write(ap,dict(version=1,approved=True,scope='reviewed_metadata_price_development_export',run_id=manifest['run_id'],fingerprints=pins));return ap
start=time.monotonic();cpu=time.process_time();results=[]
for case in ['healthy_finalization','final_receipt_writer_failure','legacy_stale_complete_plus_failed_marker']:
 f=FullExportTests('test_daily_full_exports_same_keys_no_labels_no_models_and_accepted_consumption');f.setUp()
 try:
  original=c._atomic_json;raised=None;writes=[]
  def final_writer(p,v):
   if p.name=='report.json':writes.append(v.get('status'))
   if p.name=='report.json' and v.get('status')=='complete_produced_unreviewed' and case=='final_receipt_writer_failure':raise OSError('INDEPENDENT final receipt unavailable')
   return original(p,v)
  try:
   with patch.object(c,'_atomic_json',side_effect=final_writer),contextlib.redirect_stdout(io.StringIO()):c.run_export(f.train_path,f.selection_path,f.gate_path,execution_approval=f.approval_path)
  except Exception as e:raised=type(e).__name__+': '+str(e)
  d=f.root/'artifacts/metadata-price-development'/f.plan['run_id'];disk=read(d/'report.json')
  if case=='legacy_stale_complete_plus_failed_marker':write(d/'report.failed.json',dict(status='failed',error='known legacy finalization failure'))
  ap=approval(f,d)
  def no_preparation(*a,**kw):raise AssertionError('Failure marker must reject BEFORE preparation')
  boundary=patch.object(c,'prepare_export_plan',side_effect=no_preparation) if case!='healthy_finalization' else contextlib.nullcontext()
  try:
   with boundary:c.verify_accepted_export(ap)
   consumed='accepted';gate=None
  except Exception as e:consumed='rejected';gate=type(e).__name__+': '+str(e)
  marker=d/'report.failed.json'
  result=dict(case=case,raised=raised,disk_report_status=disk['status'],marker_status=read(marker)['status'] if marker.exists() else None,consumer=consumed,gate=gate,terminal_status_writes=writes[-3:]);results.append(result)
  assert consumed==('accepted' if case=='healthy_finalization' else 'rejected')
  if case=='final_receipt_writer_failure':assert raised.startswith('OSError') and disk['status']=='finalizing' and marker.exists()
 finally:f.doCleanups()
# Source observer: compile its unchanged run/need definitions only; no Root imports.
p=(Path(__import__('tempfile').gettempdir())/'tlab009-verify-full-source.py');tree=ast.parse(p.read_text());defs=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)],type_ignores=[])
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp).resolve();d=root/'artifacts/metadata-price-development'/('a'*64);d.mkdir(parents=True);write(d/'report.failed.json',dict(status='failed'))
 calls=dict(transport=0,engine=0)
 def forbidden_plan(*a,**k):calls['transport']+=1;raise AssertionError('Unexpected plan/source work')
 def forbidden_engine(*a,**k):calls['engine']+=1;raise AssertionError('Unexpected SQL work')
 ns=dict(ROOT=root,MODULE_WALL_START=time.monotonic(),__file__=str(p),Path=Path,PurePosixPath=PurePosixPath,datetime=datetime,timedelta=timedelta,sys=sys,json=json,hashlib=hashlib,math=__import__('math'),time=time,resource=resource,threading=threading,tempfile=types.SimpleNamespace(gettempdir=lambda:temp),uuid=uuid,transport=types.SimpleNamespace(prepare_export_plan=forbidden_plan),duckdb=types.SimpleNamespace(connect=forbidden_engine))
 exec(compile(defs,str(p),'exec'),ns)
 try:ns['run'](d);raised=None
 except Exception as e:raised=type(e).__name__+': '+str(e)
 evidence=read(next(root.glob('tlab009-full-source-*/report.json')))
 results.append(dict(case='source_observer_early_known_failure',raised=raised,failed_evidence=evidence['status'],calls=calls,manifest_exists=(d/'run.json').exists()))
 assert raised=='ValueError: Producer has a known failed finalization receipt' and evidence['status']=='failed' and calls==dict(transport=0,engine=0)
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab009-full-independent-final-marker-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
