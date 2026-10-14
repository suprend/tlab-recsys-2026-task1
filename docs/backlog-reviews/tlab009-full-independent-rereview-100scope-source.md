# Historical independent targeted re-review source

Only machine paths are portable. Evidence belongs to ebac0976 freeze in [targeted re-review](tlab009-full-export-code-rereview.md); this preserves the remaining stale-receipt failure and earlier findings that were closed. Helpers require extraction to the temporary directory. No new execution is claimed.

```python
import sys,json,hashlib,shutil,time,resource,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path.cwd().resolve()))
from tests.test_metadata_price_collection import FullExportTests
from scripts import metadata_price_collection as c
ROOT=Path(str(Path.cwd().resolve()))
def read(p):return json.loads(p.read_text())
def enc(o):return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def write(p,o):p.write_text(enc(o)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
start=time.monotonic();cpu=time.process_time();results=[]
for case in ['healthy_with_actual_source_and_candidate_code','drop_actual_source','drop_candidate_code','drop_spec_file']:
 f=FullExportTests('test_daily_full_exports_same_keys_no_labels_no_models_and_accepted_consumption');f.setUp()
 try:
  top=read(f.gate_path);old=f.root/'artifacts/metadata-price'/top['run_id'];m=read(old/'run.json');r=read(old/'report.json');pins=m['identity']['fingerprints']
  candidate=f.root/'scripts/candidate_pilot.py'
  if not candidate.exists():shutil.copyfile(ROOT/'scripts/candidate_pilot.py',candidate)
  pins['source.duckdb']=sha(f.fixture.source);pins['scripts/candidate_pilot.py']=sha(candidate)
  if case=='drop_actual_source':pins.pop('source.duckdb')
  if case=='drop_candidate_code':pins.pop('scripts/candidate_pilot.py')
  if case=='drop_spec_file':pins.pop('configs/features/metadata-price.json')
  rid=hashlib.sha256(enc(m['identity']).encode()).hexdigest();new=old.parent/rid;old.rename(new);m['run_id']=r['run_id']=rid
  for name,a in m['outputs'].items():a['path']=str((new/(name+'.parquet')).relative_to(f.root));a['sha256']=sha(f.root/a['path'])
  r['artifacts']=m['outputs']
  ap=f.root/m['gate_approval']['path'];write(ap,dict(version=1,approved=True,scope=m['identity']['role'],run_id=rid,fingerprints=pins));m['gate_approval']['sha256']=sha(ap)
  write(new/'run.json',m);write(new/'report.json',r)
  scopepins=dict(pins);scopepins[m['gate_approval']['path']]=sha(ap)
  for a in m['outputs'].values():scopepins[a['path']]=a['sha256']
  for p in [new/'run.json',new/'report.json']:scopepins[str(p.relative_to(f.root))]=sha(p)
  write(f.gate_path,dict(version=1,approved=True,scope='reviewed_metadata_price_100q',run_id=rid,fingerprints=scopepins))
  try:c.verify_accepted_metadata_gate(f.gate_path);out='accepted';err=None
  except Exception as e:out='rejected';err=str(e)
  results.append(dict(case=case,status=out,error=err,synthetic_scope_pins=len(scopepins)))
 finally:f.doCleanups()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),fits=0,real_source_reads=0,scope='tiny gate transport with source/code added then omitted; not actual93pin artifact audit')
(Path(__import__('tempfile').gettempdir())/'tlab009-full-independent-rereview-100scope-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
