# Historical source-oracle version

Preserved byte content of the earlier oracle. Initial nullable-BIGINT false acceptance and subsequent typed-transport acceptance are documented separately. Current executable audit is [metadata_export_audit.py](../../tests/oracles/metadata_export_audit.py); this archive authorizes no execution or data acceptance.

```python
"""Independent full source oracle. No write-acceptance or producer materializer."""
from pathlib import Path,PurePosixPath
from datetime import datetime,timedelta
import sys,json,hashlib,math,time,resource,threading,tempfile,uuid,importlib.util
import duckdb
import pandas as pd
ROOT=Path.cwd().resolve()
sys.path.insert(0,str(ROOT))
from scripts import metadata_price_collection as transport
from tests.oracles import metadata_source as oracle
MODEL=[('category_id_nominal','VARCHAR'),('category_code_by_id','VARCHAR'),('brand','VARCHAR'),
('brand_missing','BOOLEAN'),('brand_ambiguous','BOOLEAN'),('code_missing','BOOLEAN'),('code_ambiguous','BOOLEAN'),('code_recovered','BOOLEAN'),
('log_price','DOUBLE'),('price_missing','BOOLEAN'),('price_ambiguous','BOOLEAN'),('price_zero','BOOLEAN'),('price_negative','BOOLEAN'),
('category_peer_log_price_mean','DOUBLE'),('category_peer_product_support','BIGINT'),('category_log_price_difference','DOUBLE'),
('category_peer_mean_missing','BOOLEAN'),('category_price_difference_missing','BOOLEAN')]
PROVENANCE=[('latest_timestamp','TIMESTAMP'),('category_id','BIGINT'),('category_ambiguous','BOOLEAN'),('latest_code','VARCHAR'),
('latest_code_ambiguous','BOOLEAN'),('latest_brand','VARCHAR'),('latest_brand_ambiguous','BOOLEAN'),('latest_price','DOUBLE'),
('latest_price_ambiguous','BOOLEAN'),('dictionary_code','VARCHAR'),('dictionary_code_count','BIGINT'),('dictionary_first_known','TIMESTAMP'),('in_reference','BOOLEAN')]
FEATURE_SCHEMA=[('query_id','VARCHAR'),('product_id','BIGINT')]+MODEL
PROV_SCHEMA=[('query_id','VARCHAR'),('product_id','BIGINT'),('anchor','TIMESTAMP')]+PROVENANCE
REF_SCHEMA=[('anchor','TIMESTAMP'),('product_id','BIGINT'),('category_id','BIGINT'),('log_price','DOUBLE')]
def need(value,message):
 if not value:raise ValueError(message)
def local(name):
 p=PurePosixPath(name)
 need(not p.is_absolute() and '..' not in p.parts,'Unsafe pinned path')
 path=(ROOT/name).resolve();need(path.is_relative_to(ROOT),'Pinned path escapes project');return path
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def sha(path,guard):
 h=hashlib.sha256()
 with Path(path).open('rb') as handle:
  while data:=handle.read(8*2**20):guard();h.update(data)
 guard();return h.hexdigest()
def same(a,b):
 if a is None or b is None:return a is b
 if isinstance(b,(bool,int,str,datetime)):return type(a) is type(b) and a==b
 return isinstance(a,(float,int)) and math.isfinite(a) and math.isclose(a,b,abs_tol=1e-12,rel_tol=1e-9)
def equal_relations(con,left,right):
 for a,b in [(left,right),(right,left)]:
  need(con.execute('SELECT count(*) FROM ('+a+' EXCEPT ALL '+b+')').fetchone()[0]==0,'Independent relation multiset mismatch')
def compare_broadcast(con,table,expected,columns,guard):
 """Compare EVERY physical row, never a representative producer row."""
 bad=[]
 for name,kind in columns:
  guard();a='a."'+name+'"';b='e."'+name+'"'
  if kind=='DOUBLE':
   condition='('+a+' IS NULL) IS DISTINCT FROM ('+b+' IS NULL) OR ('+a+' IS NOT NULL AND '+b+' IS NOT NULL AND (NOT isfinite('+a+') OR abs('+a+'-'+b+')>greatest(1e-12,1e-9*greatest(abs('+a+'),abs('+b+')))))'
  else:condition=a+' IS DISTINCT FROM '+b
  n=con.execute('SELECT count(*) FROM '+table+' a JOIN '+expected+' e USING(product_id) WHERE '+condition).fetchone()[0]
  if n:bad.append((name,n))
 need(not bad,'Every-row metadata mismatch '+repr(bad))
def install_expected(con,name,rows,schema):
 frame=pd.DataFrame(rows,columns=[n for n,k in schema]);con.register('_oracle_frame',frame)
 try:con.execute('CREATE OR REPLACE TEMP TABLE '+name+' AS SELECT '+','.join('CAST("'+n+'" AS '+k+') "'+n+'"' for n,k in schema)+' FROM _oracle_frame')
 finally:con.unregister('_oracle_frame')
def run(directory):
 directory=Path(directory).resolve();need(directory.is_relative_to(ROOT/'artifacts/metadata-price-development'),'Wrong export namespace')
 started=time.monotonic();cpu=time.process_time();expired=threading.Event();con=timer=None
 attempt=Path(tempfile.gettempdir())/('tlab009-full-source-'+uuid.uuid4().hex);attempt.mkdir()
 report=dict(status='running',purpose='independent_complete_metadata_source_audit',attempt_directory=str(attempt),completed=[],fits=0,labels_parsed=False,oracle_code_hashes={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'tests/oracles/metadata_source.py',ROOT/'tests/oracles/metadata_price.py']})
 def write():
  report.update(wall_seconds=time.monotonic()-started,actual_process_cpu_seconds=time.process_time()-cpu,process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
  (attempt/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 def guard():
  if expired.is_set() or time.monotonic()-started>=1200:raise TimeoutError('Full source oracle wall1200s')
  if time.process_time()-cpu>=900:raise TimeoutError('Full source oracle actualCPU900s')
  if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>8*2**30:raise MemoryError('Full source oracle RSS8GiB')
 def checkpins(pins):
  for name,digest in pins.items():need(sha(local(name),guard)==digest,'Changed independent audit pin '+name)
 write();primary=None
 try:
  manifest=json.loads((directory/'run.json').read_text());producer=json.loads((directory/'report.json').read_text());identity=manifest['identity']
  need(producer['status']=='complete_produced_unreviewed' and producer['scope']=='metadata_price_development_export','Producer incomplete')
  need(producer['run_id']==manifest['run_id']==directory.name==hashlib.sha256(canon(identity).encode()).hexdigest(),'Detached full export identity')
  need(producer['labels_loaded'] is False and producer['fit_attempt_count']==0,'Unexpected labels/model scope')
  need(producer['seconds']<=1200 and 0<=producer['process_cpu_user_system_seconds']<=900 and producer['process_peak_rss_bytes']<=8*2**30,'Producer resource gate failed')
  need(all(s['status']=='complete' for s in producer['stages']),'Incomplete producer stage')
  refs=identity['acceptance_refs']
  current,collections=transport.prepare_export_plan(local(refs['train']),local(refs['selection']),local(refs['gate']),check=guard)
  need(current['identity']==identity and current['run_id']==manifest['run_id'],'Actual reviewed inputs not bound to export')
  approval_ref=manifest['execution_approval'];approval=json.loads(local(approval_ref['path']).read_text())
  need(approval==dict(version=1,approved=True,scope=identity['role'],run_id=manifest['run_id'],fingerprints=identity['fingerprints']),'External execution approval mismatch')
  pins=dict(identity['fingerprints']);pins[approval_ref['path']]=approval_ref['sha256']
  for file in [directory/'run.json',directory/'report.json']:pins[file.relative_to(ROOT).as_posix()]=sha(file,guard)
  for days in manifest['outputs'].values():
   for day in days:
    for artifact in day['artifacts'].values():
     name=artifact['path'];need(name not in pins,'Duplicate artifact path');pins[name]=artifact['sha256']
  checkpins(pins);report['completed'].append('exact_input_lineage_execution_approval_output_hashes')
  con=duckdb.connect(':memory:');con.execute('SET threads=2');con.execute("SET memory_limit='2GB'");con.execute("SET max_temp_directory_size='2GB'");con.execute('SET temp_directory=?',[str(attempt/'spill')])
  def stop():expired.set();con.interrupt()
  timer=threading.Timer(max(.001,1200-(time.monotonic()-started)),stop);timer.daemon=True;timer.start()
  source=collections['train']['plan']['execution_inputs']['source_path'];con.execute("ATTACH '"+str(local(source)).replace("'","''")+"' AS source (READ_ONLY)")
  counts=dict(anchors=0,queries=0,pairs=0,distinct_anchor_items=0,model_comparisons=0,provenance_rows=0,full_reference_rows=0)
  for role,collection in collections.items():
   phase=collection['phase'];start=datetime.fromisoformat(phase['range']['start'].replace('Z','+00:00')).replace(tzinfo=None);end=datetime.fromisoformat(phase['range']['end'].replace('Z','+00:00')).replace(tzinfo=None)
   days=manifest['outputs'][role];expected_days=[];t=start
   while t<end:expected_days.append(t.strftime('%Y-%m-%dT%H:%M:%SZ'));t+=timedelta(days=1)
   need([d['anchor'] for d in days]==expected_days,'Missing/duplicate/reordered export day')
   need(producer['phases'][role]['days']==days and producer['phases'][role]['status']=='complete_produced_unreviewed','Producer report daily cover detached')
   con.read_parquet([str(local(p)) for p in collection['refs']['queries']]).create_view('base_q',replace=True)
   con.read_parquet([str(local(p)) for p in collection['refs']['features']]).create_view('base_f',replace=True)
   source_start=datetime.fromisoformat(collection['plan']['identity']['shard_protocols'][0]['source']['start'].replace('Z','+00:00')).replace(tzinfo=None)
   for day in days:
    guard();anchor=datetime.fromisoformat(day['anchor'].replace('Z','+00:00')).replace(tzinfo=None)
    con.execute('CREATE OR REPLACE TEMP TABLE expected_q AS SELECT * FROM base_q WHERE anchor=?',[anchor])
    con.execute('CREATE OR REPLACE TEMP TABLE expected_pairs AS SELECT f.query_id,f.product_id FROM base_f f SEMI JOIN expected_q q USING(query_id)')
    for key,artifact in day['artifacts'].items():
     need(local(artifact['path'])==directory/role/day['anchor'][:10]/(key+'.parquet'),'Detached day output path')
     con.read_parquet(str(local(artifact['path']))).create_view(key,replace=True)
     schema=[tuple(r[:2]) for r in con.execute('DESCRIBE '+key).fetchall()]
     expected_schema={'features':FEATURE_SCHEMA,'provenance':PROV_SCHEMA,'reference':REF_SCHEMA,'queries':[tuple(r[:2]) for r in con.execute('DESCRIBE expected_q').fetchall()]}[key]
     need(schema==expected_schema==[tuple(x) for x in artifact['schema']],'Independent typed output schema mismatch')
     need(con.execute('SELECT count(*) FROM '+key).fetchone()[0]==artifact['rows'],'Artifact rowcount mismatch')
    equal_relations(con,'SELECT * FROM queries','SELECT * FROM expected_q')
    for table in ['features','provenance']:
     equal_relations(con,'SELECT query_id,product_id FROM '+table,'SELECT query_id,product_id FROM expected_pairs')
     n,u=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM '+table).fetchone();need(n==u,'Duplicate physical metadata key')
    need(con.execute('SELECT count(*) FROM provenance WHERE anchor IS DISTINCT FROM ?',[anchor]).fetchone()[0]==0,'Wrong provenance anchor')
    products=[r[0] for r in con.execute('SELECT DISTINCT product_id FROM expected_pairs ORDER BY product_id').fetchall()]
    need(len(products)<=22000,'Independent domain exceeds cap')
    qn=con.execute('SELECT count(*) FROM expected_q').fetchone()[0]
    snapshot=oracle.extract_snapshot(con,source_start,anchor,products,check=guard) if qn else {'reference':{}}
    models=[];provenances=[]
    for index,pid in enumerate(products):
     model,provenance=oracle.expected_product(snapshot,pid)
     models.append([pid,*[model[n] for n,k in MODEL]])
     provenances.append([pid,*[provenance[n] for n,k in PROVENANCE]])
     if index%50==0:guard()
    install_expected(con,'expected_model',models,[('product_id','BIGINT')]+MODEL)
    install_expected(con,'expected_provenance',provenances,[('product_id','BIGINT')]+PROVENANCE)
    compare_broadcast(con,'features','expected_model',MODEL,guard)
    compare_broadcast(con,'provenance','expected_provenance',PROVENANCE,guard)
    refs_actual=con.execute('SELECT anchor,product_id,category_id,log_price FROM reference').fetchall()
    actual={pid:(cat,z) for a,pid,cat,z in refs_actual};need(len(actual)==len(refs_actual),'Duplicate reference product')
    need(all(a==anchor for a,pid,cat,z in refs_actual) and set(actual)==set(snapshot['reference']),'Reference domain/anchor differs')
    for index,(pid,(cat,z)) in enumerate(snapshot['reference'].items()):
     need(actual[pid][0]==cat and same(actual[pid][1],z),'Reference source value mismatch')
     if index%10000==0:guard()
    qn=con.execute('SELECT count(*) FROM expected_q').fetchone()[0];pn=con.execute('SELECT count(*) FROM expected_pairs').fetchone()[0]
    counts['anchors']+=1;counts['queries']+=qn;counts['pairs']+=pn;counts['distinct_anchor_items']+=len(products);counts['model_comparisons']+=18*pn;counts['provenance_rows']+=pn;counts['full_reference_rows']+=len(actual)
    report['completed'].append(role+'_'+day['anchor'][:10]);write();guard()
    del snapshot,models,provenances,actual,refs_actual
  checkpins(pins);guard()
  report.update(counts=counts,run_id=manifest['run_id'],all_output_pins=pins,float_tolerance=dict(absolute=1e-12,relative=1e-9),expected_domain='acceptedQ/C_unique_anchor_product',comparison='every_physical_keyed_row_against_independent_source_values',peer_mean='direct_excluded_self_fsum_lists_not_sum_minus_self')
 except BaseException as error:primary=error
 finally:
  if timer is not None:timer.cancel()
  if con is not None:
   try:con.close()
   except BaseException as e:
    if primary is None:primary=e
    else:report.setdefault('secondary_errors',[]).append(str(e))
  try:guard()
  except BaseException as e:
   if primary is None:primary=e
   else:report.setdefault('secondary_errors',[]).append(str(e))
  report['status']='independently_verified_full_metadata_source' if primary is None else 'failed'
  if primary is not None:report.update(error_type=type(primary).__name__,error=str(primary))
  try:write()
  except BaseException as e:
   if primary is None:primary=e
   else:report.setdefault('secondary_errors',[]).append(str(e))
   report.update(status='failed',error_type=type(primary).__name__,error=str(primary))
   try:(attempt/'report.json').write_text(json.dumps(report,indent=2)+'\n')
   except BaseException as secondary:report.setdefault('secondary_errors',[]).append(str(secondary))
  try:guard()
  except BaseException as e:
   if primary is None:primary=e
   else:report.setdefault('secondary_errors',[]).append(str(e))
   report.update(status='failed',error_type=type(primary).__name__,error=str(primary))
   try:(attempt/'report.json').write_text(json.dumps(report,indent=2)+'\n')
   except BaseException as secondary:report.setdefault('secondary_errors',[]).append(str(secondary))
 if primary is not None:raise primary
 print(json.dumps({k:v for k,v in report.items() if k not in ['all_output_pins','completed']},indent=2));return report
if __name__=='__main__':run(sys.argv[1])

```
