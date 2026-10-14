# Historical independent synthetic fault harness

Only local paths were made portable. Run from the project root after extracting any dependent archived helper into the system temporary directory. Evidence belongs to the original f60b639f freeze in the [changes-requested review](tlab009-full-export-code-review.md); it deliberately records false accepts and accounting failures. Later fixes require a separate re-review. No real data/model execution or new acceptance is claimed by archiving.

```python
import sys,json,time,resource,tempfile,contextlib,io,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd().resolve()))
from scripts import metadata_price_collection as c
from tests.test_metadata_price_collection import FullExportTests
import duckdb

def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(enc(x)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
start=time.monotonic();cpu=time.process_time();results=[]
for case in ['baseline','stage_primary_cpu_secondary','terminal_CPU_ledger','terminal_RSS_counter_primary','report_write_primary']:
 with tempfile.TemporaryDirectory() as tmp:
  directory=Path(tmp)/'out';clock=[0.];cpu_bad=[False];rss_bad=[False];raised=None;audit=None
  def writer(p,value):
   write(p,value)
   if p.name=='run.json' and case=='terminal_CPU_ledger':clock[0]+=10
   if p.name=='report.json' and value.get('status')=='failed' and case=='report_write_primary':raise OSError('INDEPENDENT report write secondary')
  def cpucounter():
   if cpu_bad[0]:raise OSError('INDEPENDENT stage CPU secondary')
   return clock[0]
  def rss():
   if rss_bad[0]:raise OSError('INDEPENDENT RSS secondary')
   return 0
  try:
   with patch.object(c,'_atomic_json',side_effect=writer),patch.object(c,'cpu_time',side_effect=cpucounter),patch.object(c,'peak_rss_bytes',side_effect=rss):
    with c.ExecutionAudit(directory,seconds=30,scope='independent',cpu_seconds=900) as audit:
     if case=='stage_primary_cpu_secondary':
      def operation():cpu_bad[0]=True;raise ValueError('INDEPENDENT PRIMARY')
      audit.stage('independent_operation',operation)
     elif case=='terminal_RSS_counter_primary':rss_bad[0]=True;raise ValueError('INDEPENDENT PRIMARY')
     elif case=='report_write_primary':raise ValueError('INDEPENDENT PRIMARY')
     else:
      audit.manifest={'synthetic':True};audit.report['status']='complete_produced_unreviewed'
  except Exception as e:raised=type(e).__name__+': '+str(e)
  reports=list(directory.glob('*/report.json'));disk=read(reports[0]) if reports else None
  results.append(dict(case=case,raised=raised,actual_mock_CPU=clock[0],report=disk))

for case in ['full_export_baseline','fresh_resealed_wrong_physical_key','fresh_resealed_wrong_schema','fresh_resealed_missing_output_row']:
 fixture=FullExportTests('test_daily_full_exports_same_keys_no_labels_no_models_and_accepted_consumption');fixture.setUp()
 try:
  with contextlib.redirect_stdout(io.StringIO()):report=c.run_export(fixture.train_path,fixture.selection_path,fixture.gate_path,execution_approval=fixture.approval_path)
  root=fixture.root;directory=root/'artifacts/metadata-price-development'/report['run_id'];mp=directory/'run.json';rp=directory/'report.json';manifest=read(mp);disk=read(rp)
  if case!='full_export_baseline':
   day=manifest['outputs']['train'][0];a=day['artifacts']['features'];p=root/a['path'];con=duckdb.connect(':memory:');con.execute('SET threads=2')
   try:
    con.read_parquet(str(p)).create_view('old')
    statement={'fresh_resealed_wrong_physical_key':"SELECT * REPLACE('INDEPENDENT_BAD_KEY'::VARCHAR AS query_id) FROM old",'fresh_resealed_wrong_schema':'SELECT * EXCLUDE(brand) FROM old','fresh_resealed_missing_output_row':'SELECT * FROM old LIMIT 1'}[case]
    con.execute('CREATE TABLE changed AS '+statement);new=p.with_suffix('.independent.parquet');con.execute('COPY changed TO ? (FORMAT PARQUET)',[str(new)]);new.replace(p)
    a.update(sha256=sha(p),bytes=p.stat().st_size,rows=con.execute('SELECT count(*) FROM changed').fetchone()[0],schema=[list(r[:2]) for r in con.execute('DESCRIBE changed').fetchall()])
   finally:con.close()
   disk['phases']['train']['days']=manifest['outputs']['train'];disk['phases']['train']['pairs']=sum(d['artifacts']['features']['rows'] for d in manifest['outputs']['train']);write(mp,manifest);write(rp,disk)
  pins=dict(manifest['identity']['fingerprints']);ref=manifest['execution_approval'];pins[ref['path']]=ref['sha256']
  for days in manifest['outputs'].values():
   for d in days:
    for a in d['artifacts'].values():pins[a['path']]=a['sha256']
  for p in [mp,rp]:pins[str(p.relative_to(root))]=sha(p)
  acceptance=root/'independent-full-acceptance.json';write(acceptance,dict(version=1,approved=True,scope='reviewed_metadata_price_development_export',run_id=report['run_id'],fingerprints=pins))
  try:c.verify_accepted_export(acceptance);out='accepted';error=None
  except Exception as e:out='rejected';error=type(e).__name__+': '+str(e)
  results.append(dict(case=case,status=out,error=error,transport_scope='author tiny fixture/mock prepare; physical Parquet modified and independently resealed'))
 finally:fixture.doCleanups()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab009-full-independent-fault-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
