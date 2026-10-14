# Historical independent synthetic fault harness

Only local paths were made portable. Run from the project root after extracting any dependent archived helper into the system temporary directory. Evidence belongs to the original f60b639f freeze in the [changes-requested review](tlab009-full-export-code-review.md); it deliberately records false accepts and accounting failures. Later fixes require a separate re-review. No real data/model execution or new acceptance is claimed by archiving.

```python
from pathlib import Path
exec((Path(__import__('tempfile').gettempdir())/'tlab018-independent-faults.py').read_text().split('start=time.monotonic();cpu=time.process_time();results=[]')[0])
from scripts import metadata_price_collection as c,train_baselines as b
from tests.test_metadata_price_collection import FullExportTests
start=time.monotonic();cpu=time.process_time();results=[]
with patch('duckdb.connect',side_effect=limited):
 f=Tiny()
 try:
  with patch.object(c,'ROOT',f.root),patch.object(b,'ROOT',f.root):
   baseline=c.verify_collection_strict(f.exp);results.append(dict(case='strict_actual_tiny_lineage',status='accepted',role=baseline['phase']['role']))
   e=f.state['shards'][0];am=read(f.root/e['anchor']['directory']/'run.json');cm=read(f.root/e['candidate']['directory']/'run.json');ap=f.root/e['acceptance']['path'];a=read(ap);fm_path=f.root/e['features']['directory']/'run.json';fm=read(fm_path)
   for n in [am['artifact_refs']['queries'],cm['artifact_refs']['candidates']]:a['fingerprints'].pop(n);fm['identity']['input_hashes'].pop(n)
   write(ap,a);write(fm_path,fm);f.reseal()
   b.verify_collection(f.exp)
   try:c.verify_collection_strict(f.exp);out='unexpected_accepted';gate=None
   except Exception as err:out='rejected';gate=str(err)
   results.append(dict(case='strict_fresh_resealed_joint_QC_omission',legacy_pass=True,status=out,gate=gate))
 finally:f.close()
for case in ['emptyC_day','zeroQ_calendar_day','fullcardinality_diagnostic_union']:
 f=FullExportTests('test_daily_full_exports_same_keys_no_labels_no_models_and_accepted_consumption');f.setUp()
 try:
  if case=='emptyC_day':
   p=f.root/'f.parquet';con=limited(':memory:');con.read_parquet(str(p)).create_view('old');temp=p.with_suffix('.emptyC.parquet');con.execute("COPY (SELECT * FROM old WHERE query_id LIKE 'q0-%') TO ? (FORMAT PARQUET)",[str(temp)]);con.close();temp.replace(p)
   f.plan['identity']['fingerprints']['f.parquet']=digest(p);f.plan['run_id']=hashlib.sha256(enc(f.plan['identity']).encode()).hexdigest()
   write(f.approval_path,dict(version=1,approved=True,scope=c.ROLE,run_id=f.plan['run_id'],fingerprints=f.plan['identity']['fingerprints']))
  if case=='zeroQ_calendar_day':
   for col in f.collections.values():col['phase']['range']['end']='2019-10-13T00:00:00Z'
  original=c.validate_day_arrays
  def distinct_brands(con,**kw):
   anchor=con.execute('SELECT min(anchor) FROM metadata_queries').fetchone()[0]
   con.execute('UPDATE metadata_price_features SET brand=?',['value:'+str(anchor)])
   return original(con,**kw)
  replacement=patch.object(c,'validate_day_arrays',side_effect=distinct_brands) if case=='fullcardinality_diagnostic_union' else contextlib.nullcontext()
  with replacement,contextlib.redirect_stdout(io.StringIO()):r=c.run_export(f.train_path,f.selection_path,f.gate_path,execution_approval=f.approval_path)
  results.append(dict(case=case,status=r['status'],phases={role:dict(queries=p['queries'],pairs=p['pairs'],days=[dict(anchor=d['anchor'],rows={k:a['rows'] for k,a in d['artifacts'].items()},diagnostic=d['model_boundary']['diagnostic_cardinality']) for d in p['days']],phase_cardinality=p.get('diagnostic_cardinality')) for role,p in r['phases'].items()}))
 finally:f.doCleanups()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab009-full-independent-boundary-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
