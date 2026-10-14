# Independent targeted audit source archive

Historical exact-version audit; only machine paths are portable. Dependent archived scripts must be extracted to the system temporary directory before use. Original false accepts remain evidence for their original versions; later fixes have separate reviews. No source/model execution or new acceptance is claimed by archiving.

```python
import sys,json,time,resource,contextlib,io,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd().resolve()))
from tests.test_metadata_price_collection import FullExportTests
from scripts import metadata_price_collection as c

def read(p):return json.loads(p.read_text())
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def write(p,v):p.write_text(enc(v)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
start=time.monotonic();cpu=time.process_time();results=[]
f=FullExportTests('test_daily_full_exports_same_keys_no_labels_no_models_and_accepted_consumption');f.setUp()
try:
 with contextlib.redirect_stdout(io.StringIO()):report=c.run_export(f.train_path,f.selection_path,f.gate_path,execution_approval=f.approval_path)
 results.append(dict(case='phase_encoded_union',days=[d['model_boundary']['diagnostic_cardinality']['brand'] for d in report['phases']['train']['days']],phase=report['phases']['train']['diagnostic_phase_encoded_cardinality']['brand']))
finally:f.doCleanups()
f=FullExportTests('test_daily_full_exports_same_keys_no_labels_no_models_and_accepted_consumption');f.setUp()
try:
 original=c._atomic_json;written=[0];raised=None
 def failed_last_receipt(p,v):
  if p.name=='report.json' and v.get('status')=='complete_produced_unreviewed':
   written[0]+=1
   if written[0]>=2:raise OSError('INDEPENDENT final receipt unavailable')
  if p.name=='report.json' and v.get('status')=='failed':raise OSError('INDEPENDENT final receipt unavailable')
  return original(p,v)
 try:
  with patch.object(c,'_atomic_json',side_effect=failed_last_receipt),contextlib.redirect_stdout(io.StringIO()):c.run_export(f.train_path,f.selection_path,f.gate_path,execution_approval=f.approval_path)
 except Exception as e:raised=type(e).__name__+': '+str(e)
 directory=f.root/'artifacts/metadata-price-development'/f.plan['run_id'];manifest=read(directory/'run.json');report=read(directory/'report.json');fallback=read(directory/'report.failed.json')
 pins=dict(manifest['identity']['fingerprints']);ref=manifest['execution_approval'];pins[ref['path']]=ref['sha256']
 for days in manifest['outputs'].values():
  for d in days:
   for a in d['artifacts'].values():pins[a['path']]=a['sha256']
 for p in [directory/'run.json',directory/'report.json']:pins[str(p.relative_to(f.root))]=sha(p)
 ap=f.root/'independent-after-failed-receipt.json';write(ap,dict(version=1,approved=True,scope='reviewed_metadata_price_development_export',run_id=f.plan['run_id'],fingerprints=pins))
 try:c.verify_accepted_export(ap);consumed='accepted';gate=None
 except Exception as e:consumed='rejected';gate=str(e)
 results.append(dict(case='final_writer_failure_after_first_complete_summary',raised=raised,disk_report_status=report['status'],failed_receipt_status=fallback['status'],consumer=consumed,consumer_gate=gate))
finally:f.doCleanups()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab009-full-independent-rereview-finalization-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
