# Independent synthetic model-data/ablation audit archive

Historical exact-version audit, with only machine paths made portable. Extract dependent archived helpers into the system temporary directory before use. Initial model-data overflow assertion mismatch and initial terminal-decision faults remain evidence for their original versions. Archiving claims no new execution or actual fitting.

```python
import sys, tempfile, json, time, resource, hashlib
from pathlib import Path
from datetime import datetime
from copy import deepcopy
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd().resolve()))
import duckdb, numpy as np
from scripts import model_data as d
from scripts import train_baselines as b
from scripts import metadata_price_features as m
T=time.monotonic();CPU=time.process_time();results=[]
FILES=['scripts/model_data.py','tests/test_model_data.py','docs/experiments/model-data.md']
REPO=Path(str(Path.cwd().resolve()))
def hashes():return {p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in FILES}
before=hashes()
real_connect=duckdb.connect
class Fixture:
 def __enter__(self):
  self.temp=tempfile.TemporaryDirectory(prefix='tlab-model-independent-',dir='/tmp');self.root=Path(self.temp.name)
  self.con=real_connect(':memory:')
  self.con.execute("CREATE TABLE q AS SELECT 'q'||lpad(i::VARCHAR,2,'0') query_id,i::BIGINT user_id,TIMESTAMP '2019-10-08' anchor,true label_is_mature FROM range(12) t(i)")
  self.con.execute("CREATE TABLE f AS SELECT query_id,user_id,(1152921504606846977+j)::BIGINT product_id,anchor,77::BIGINT candidate_category_id,CASE WHEN j=0 THEN NULL ELSE TIMESTAMP '2019-10-07' END last_user_event_time,CASE WHEN j=1 THEN NULL ELSE j END::BIGINT user_view_7d FROM q CROSS JOIN range(220) s(j) WHERE user_id<>11")
  self.con.execute("CREATE TABLE y(query_id VARCHAR,product_id BIGINT)")
  self.con.execute("INSERT INTO y VALUES ('q00',1152921504606846977),('q00',9223372036854775807),('q11',-9223372036854775808)")
  self.con.execute("CREATE TABLE addon AS SELECT query_id,product_id,'value:77' category_id_nominal,'state:missing' category_code_by_id,'value:бренд' brand,"+','.join(self.expr(n)+' '+n for n in m.NUMERIC)+' FROM f')
  self.collection=dict(phase=dict(role='train'),refs=dict(queries=['q.parquet'],features=['f.parquet'],labels=['y.parquet']),feature_columns=[r[0] for r in self.con.execute('DESCRIBE f').fetchall()])
  for tab in ['q','f','y','addon']:self.save(tab)
  self.patches=[patch.object(d,'ROOT',self.root),patch.object(b,'ROOT',self.root)]
  for p in self.patches:p.start()
  return self
 def expr(self,n):
  return {'log_price':'NULL::DOUBLE','category_peer_log_price_mean':'NULL::DOUBLE','category_peer_product_support':'0::BIGINT','category_log_price_difference':'NULL::DOUBLE','price_zero':'true','code_missing':'true','category_peer_mean_missing':'true','category_price_difference_missing':'true'}.get(n,'false')
 def save(self,t):
  p=self.root/(t+'.parquet')
  if p.exists():p.unlink()
  self.con.execute('COPY '+t+' TO ? (FORMAT PARQUET)',[str(p)])
 def load(self,**opts):return d.prepare_model_data(self.collection,**dict(dict(max_queries=None,max_rows=10000,metadata_paths=['addon.parquet'],chunk_vectors=1),**opts))
 def __exit__(self,*args):
  for p in self.patches:p.stop()
  self.con.close();self.temp.cleanup()
class Transport:
 def __init__(self,mode=None):self.real=real_connect(':memory:');self.mode=mode;self.trace=[];self.fetches=0;self.final_execs=0
 def __getattr__(self,k):return getattr(self.real,k)
 def read_parquet(self,paths,*a,**kw):self.trace.append(('read',[Path(p).name for p in paths]));return self.real.read_parquet(paths,*a,**kw)
 def execute(self,sql,*a,**kw):
  self.trace.append(('sql',sql))
  if sql.startswith('SELECT f.group_index'):self.final_execs+=1
  self.real.execute(sql,*a,**kw);return self
 def fetch_df_chunk(self,v):
  self.trace.append(('chunk',v));self.fetches+=1;f=self.real.fetch_df_chunk(v)
  if not f.empty and self.fetches==2:
   if self.mode=='duplicate_boundary':f.iloc[0,f.columns.get_loc('product_id')]=1152921504606847044 # previous item at offset2047, group9
   if self.mode=='reverse':f=f.iloc[::-1].copy()
   if self.mode=='short':f=f.iloc[1:].copy()
   if self.mode=='floatkey':f['product_id']=f['product_id'].astype(float)
   if self.mode=='badgroup':f.iloc[0,f.columns.get_loc('group_index')]=12
   if self.mode=='infinite':f.iloc[0,f.columns.get_loc('user_view_7d')]=float('inf')
  return f
 def close(self):self.real.close()
def rejects(call,typ=ValueError):
 try:call()
 except typ as e:return str(e)
 raise AssertionError('mutant accepted')
def run(name,fn):
 try:
  detail=fn();results.append(dict(case=name,status='PASS',detail=detail))
 except Exception as e:
  results.append(dict(case=name,status='FAIL',error=repr(e)))
def healthy():
 with Fixture() as f:
  transport=Transport()
  with patch.object(d.duckdb,'connect',return_value=transport):data=f.load()
  expected_groups=[];expected_items=[];expected_y=[]
  for g in range(11):
   for j in range(220):expected_groups.append(g);expected_items.append(1152921504606846977+j);expected_y.append(int(g==0 and j==0))
  assert data.queries==[(f'q{g:02}',g,datetime(2019,10,8),frozenset([1152921504606846977,9223372036854775807]) if g==0 else frozenset([-9223372036854775808]) if g==11 else frozenset()) for g in range(12)]
  assert data.group.tolist()==expected_groups and data.items.tolist()==expected_items and data.y.tolist()==expected_y
  expected_x=np.array([[float('nan') if j==1 else j,float('nan') if j==0 else 86400,int(j==0)] for g in range(11) for j in range(220)],dtype=np.float32)
  np.testing.assert_array_equal(data.x[:,:3],expected_x)
  assert transport.final_execs==1 and transport.fetches==3 and [v for k,v in transport.trace if k=='chunk']==[1,1,1]
  labelread=next(i for i,e in enumerate(transport.trace) if e==('read',['y.parquet']))
  assert any(e[0]=='sql' and e[1].startswith('CREATE TEMP TABLE chosen ') for e in transport.trace[:labelread])
  assert data.categorical[0,2]==b'value:\xd0\xb1\xd1\x80\xd0\xb5\xd0\xbd\xd0\xb4' and data.categorical[0,2] is data.categorical[-1,2]
  reference=b.prepare_dataset(f.collection,max_queries=None,max_rows=10000)
  d.assert_base_equivalent(data,reference);d.assert_base_equivalent(f.load(metadata_paths=None),reference)
  return dict(rows=len(data.items),chunks=data.preparation['chunks'],execute_once=transport.final_execs,fullY_misses=2,emptyC_queries=1)
run('direct_expected_rows_fullY_chunks_UTF8_base_equivalence',healthy)
def chunk_fault(mode):
 with Fixture() as f:
  t=Transport(mode)
  with patch.object(d.duckdb,'connect',return_value=t):return rejects(f.load)
for mode in ['duplicate_boundary','reverse','short','floatkey','badgroup','infinite']:run('transport_'+mode,lambda mode=mode:chunk_fault(mode))
def sampling():
 with Fixture() as f:
  first=f.load(max_queries=3)
  expected=sorted(sorted([f'q{g:02}' for g in range(12)],key=lambda q:(hashlib.sha256(q.encode()).hexdigest(),q))[:3])
  assert [r[0] for r in first.queries]==expected
  f.con.execute('DELETE FROM y');f.con.execute("INSERT INTO y VALUES ('q01',1152921504606846980)");f.save('y')
  second=f.load(max_queries=3)
  assert [q[:3] for q in first.queries]==[q[:3] for q in second.queries]
  for field in ['group','items','x','categorical']:np.testing.assert_array_equal(getattr(first,field),getattr(second,field))
  return dict(expected=expected)
run('independent_SHA_sampling_before_labels',sampling)
def cap(kind):
 with Fixture() as f:
  t=Transport();opts=dict(max_rows=1) if kind=='rows' else dict(matrix_byte_cap=1)
  with patch.object(d.duckdb,'connect',return_value=t),patch.object(d.np,'empty',side_effect=AssertionError('premature array allocation')):
   message=rejects(lambda:f.load(**opts),(ValueError,MemoryError))
  assert ('read',['y.parquet']) not in t.trace
  return message
for kind in ['rows','bytes']:run('prealloc_'+kind,lambda kind=kind:cap(kind))
def mutate(table,sql):
 with Fixture() as f:
  f.con.execute(sql);f.save(table);return rejects(f.load)
for name,tab,sql in [
 ('duplicate_metadata','addon','INSERT INTO addon SELECT * FROM addon LIMIT 1'),
 ('missing_metadata','addon','DELETE FROM addon WHERE product_id=1152921504606846977'),
 ('orphan_metadata','addon',"INSERT INTO addon SELECT query_id,123::BIGINT,*EXCLUDE(query_id,product_id) FROM addon LIMIT 1"),
 ('wrong_user','f','UPDATE f SET user_id=999 WHERE query_id=\'q00\''),
 ('nonpast','f','UPDATE f SET last_user_event_time=anchor WHERE query_id=\'q00\''),
 ('duplicate_targets','y','INSERT INTO y SELECT * FROM y LIMIT 1'),
 ('mask_mismatch','addon','UPDATE addon SET price_zero=false'),
 ('namespace','addon',"UPDATE addon SET brand='бренд'"),
 ('f32_overflow','f','ALTER TABLE f ALTER user_view_7d TYPE DOUBLE;UPDATE f SET user_view_7d=1e39'),
]:run(name,lambda tab=tab,sql=sql:mutate(tab,sql))
def empty(zeroQ=False):
 with Fixture() as f:
  f.con.execute('DELETE FROM f');f.con.execute('DELETE FROM addon');f.save('f');f.save('addon')
  if zeroQ:f.con.execute('DELETE FROM q');f.save('q')
  data=f.load();assert data.x.shape==(0,18) and data.categorical.shape==(0,3)
  assert len(data.queries)==(0 if zeroQ else 12)
  assert data.preparation['chunks']==0
  return dict(queries=len(data.queries),rows=0,full_target_rows=data.preparation['full_target_rows'])
run('all_emptyC',empty);run('zero_Q',lambda:empty(True))
def cardinality():
 a=np.array([[b'value:'+str(i).encode(),b'state:missing',b'value:b'] for i in range(4095)]+[[b'state:missing',b'state:missing',b'value:b']],dtype=object)
 assert m.validate_train_cardinality(a)['category_id_nominal']==4096
 message=rejects(lambda:m.validate_train_cardinality(np.concatenate([a,np.array([[b'state:ambiguous',b'state:missing',b'value:b']],dtype=object)])))
 return dict(at_4096='accepted',at_4097=message,caller_must_invoke=True)
run('encoded_actual_train_cardinality_explicit_gate',cardinality)
after=hashes();assert before==after
out=dict(scope='synthetic only; no Pool, fit, real artifact/source reads',before=before,after=after,cases=results,wall_seconds=time.monotonic()-T,cpu_seconds=time.process_time()-CPU,maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
(Path(__import__('tempfile').gettempdir())/'tlab-model-data-independent-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))
if any(r['status']!='PASS' for r in results):sys.exit(1)

```
