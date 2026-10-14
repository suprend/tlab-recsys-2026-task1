# Independent synthetic runner harness archive

Original faults and exact freeze pins are retained; only local paths are portable. This audit uses synthetic fixtures/mock transport, no actual source scans or fits. Pin mismatches reject later versions by design. See [initial finding](tlab009-runner-review.md) and [targeted acceptance](tlab009-runner-rereview.md). No new execution is claimed for this archive.

```python
"""Independent tiny runner fault audit; synthetic files only in temporary directories."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import hashlib,json,math,time,resource,signal
from copy import deepcopy
from datetime import datetime,timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from contextlib import ExitStack,redirect_stdout
import io
ROOT=Path.cwd().resolve();sys.path.insert(0,str(ROOT))
import duckdb
from scripts import metadata_price_features as m
PINS={'scripts/metadata_price_features.py':'596f137e5f41649c99c568f03333e1517bc1a72b9e1dfbf7d51d8a881fa652b4',
 'tests/test_metadata_price_features.py':'e3d92fc1a8497bdd0a758a1e6ea41aa9a6b234788e7fcf5c1fd52e5ca590d11d',
 'configs/features/metadata-price.json':'20c11d9bc2e752816c07fe894e975a93a94fd81926ce5de20e250c31283fa2b8',
 'docs/experiments/metadata-price-features.md':'09289f58018163398062a78d50ed527ee81d809bc0ae98d5cba4017c5c53bbd7'}
def checkpins():
 for n,h in PINS.items():
  if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h:raise ValueError('freeze drift')
checkpins();START=time.monotonic();signal.alarm(60)
real_connect=duckdb.connect;real_clock=time.monotonic
def probe(mode):
 with TemporaryDirectory(prefix='tlab009-independent-runner-') as tmp, ExitStack() as stack:
  root=Path(tmp);stack.enter_context(patch.object(m,'ROOT',root))
  for name in [*m.GATE_CODE,'pyproject.toml']:
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('independent fixture '+name)
  spec=root/'spec.json';spec.write_text(json.dumps(m.SPEC));accept=root/'collection.json';accept.write_text('{}')
  source=root/'source.duckdb';S=datetime(2019,10,1);T=datetime(2019,10,10)
  c=real_connect(str(source));c.execute('CREATE TABLE events(event_time TIMESTAMP,product_id BIGINT,user_id BIGINT,category_id BIGINT,category_code VARCHAR,brand VARCHAR,price DOUBLE)')
  c.executemany('INSERT INTO events VALUES(?,?,?,?,?,?,?)',[(T-timedelta(seconds=1),i,999,10,'cat','бренд',i*9.) for i in (1,2)])
  c.execute('CREATE TABLE q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)')
  qs=[(f'd{d}-u{u}',d*100+u,T+timedelta(days=d)) for d in range(13) for u in range(12)]
  c.executemany('INSERT INTO q VALUES(?,?,?)',qs)
  c.execute('CREATE TABLE f AS SELECT query_id,i::BIGINT product_id,10::BIGINT candidate_category_id,false candidate_category_ambiguous,false candidate_category_missing FROM q CROSS JOIN range(1,3) x(i)')
  for name in ('q','f'):c.execute('COPY '+name+' TO ? (FORMAT PARQUET)',[str(root/(name+'.parquet'))])
  c.close()
  cpins={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('source.duckdb','q.parquet','f.parquet','collection.json')}
  collection=dict(phase=dict(role='train',lock_required=False),pins=cpins,
   refs=dict(queries=['q.parquet'],features=['f.parquet']),plan=dict(collection_id='c'*64,
    execution_inputs=dict(source_path='source.duckdb'),identity=dict(shard_protocols=[dict(source=dict(start='2019-10-01T00:00:00Z',end='2019-11-01T00:00:00Z'))])))
  def verified(*args,**kwargs):
   for n,h in cpins.items():
    if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h:raise ValueError('fixture externalpin changed')
   return deepcopy(collection)
  stack.enter_context(patch('scripts.train_baselines.verify_collection',side_effect=verified))
  plan,_=m.prepare_gate_plan(accept,spec)
  gate=root/'gate.json';gate.write_text(json.dumps(dict(version=1,approved=True,scope=m.GATE_ROLE,run_id=plan['run_id'],fingerprints=plan['identity']['fingerprints'])))
  closed={'value':False};offset={'value':0.}
  class Proxy:
   def __init__(self,con):self.con=con
   def __getattr__(self,name):return getattr(self.con,name)
   def execute(self,sql,*args,**kwargs):
    if mode in ('partial_export','primary_plus_close_error') and sql.startswith('COPY ') and 'metadata_price_provenance' in sql:raise OSError('injected independent export fault')
    return self.con.execute(sql,*args,**kwargs)
   def close(self):
    self.con.close();closed['value']=True
    if mode=='terminal_wall':offset['value']=700.
    if mode in ('terminal_close_error','primary_plus_close_error'):raise OSError('injected terminal close fault')
  stack.enter_context(patch('duckdb.connect',side_effect=lambda *a,**k:Proxy(real_connect(*a,**k))))
  if mode in ('terminal_wall','audit_time'):stack.enter_context(patch.object(m.time,'monotonic',side_effect=lambda:real_clock()+offset['value']))
  if mode=='terminal_rss':
   original_rss=m.peak_rss_bytes
   stack.enter_context(patch.object(m,'peak_rss_bytes',side_effect=lambda:m.SPEC['gate']['rss_bytes']+1 if closed['value'] else original_rss()))
  if mode=='terminal_cpu':
   original_cpu=m._process_cpu_seconds
   def cpu():
    if closed['value']:raise OSError('injected terminal CPU fault')
    return original_cpu()
   stack.enter_context(patch.object(m,'_process_cpu_seconds',side_effect=cpu))
  if mode in ('manifest_error','audit_time'):
   original_json=m._atomic_json
   def writing(path,value):
    if mode=='manifest_error' and Path(path).name=='run.json':raise OSError('injected terminal manifest fault')
    result=original_json(path,value)
    if mode=='audit_time' and Path(path).name=='report.json' and value.get('status')=='complete_produced_unreviewed':offset['value']=700.
    return result
   stack.enter_context(patch.object(m,'_atomic_json',side_effect=writing))
  if mode=='helper_drift':(root/'uv.lock').write_text('drift after approval')
  error=None;returned=None
  with redirect_stdout(io.StringIO()):
   try:returned=m.run_gate(accept,spec,gate_approval_path=gate)
   except Exception as e:error=dict(type=type(e).__name__,message=str(e))
  reports=[json.loads(p.read_text()) for p in (root/'artifacts/metadata-price').glob('*/report.json')]
  if len(reports)!=1:raise AssertionError('audit missing')
  r=reports[0]
  record=dict(mode=mode,status=r['status'],returned=returned is not None,error=error,
   reported_seconds=r['seconds'],reported_rss=r['process_peak_rss_bytes'],query_selection=r.get('query_selection'),
   partial_parquets=sorted(p.name for p in (root/'artifacts/metadata-price').glob('*/*.parquet')),
   cpu_measurement_error=r.get('cpu_measurement_error'),primary_error_type=r.get('error_type'),primary_error=r.get('error'),terminal_errors=r.get('terminal_errors'))
  if mode=='baseline':
   if r['status']!='complete_produced_unreviewed':raise AssertionError(record)
   if [v['queries'] for v in r['query_selection']['by_day']]!=[8]*9+[7]*4:raise AssertionError('balanced selection')
   expected=sorted((rank,d,q) for d in range(13) for rank,q in enumerate(sorted((f'd{d}-u{u}' for u in range(12)),key=lambda x:(hashlib.sha256(x.encode()).hexdigest(),x))))[:100]
   queryids=sorted(q for _,_,q in expected)
   h=hashlib.sha256(json.dumps(queryids,sort_keys=True,separators=(',',':')).encode()).hexdigest()
   if r['query_selection']['query_key_sha256']!=h:raise AssertionError('independent selected keys')
  if mode!='baseline' and (r['status']!='failed' or returned is not None or error is None):raise AssertionError('fault not failclosed')
  if mode=='primary_plus_close_error':
   if record['primary_error']!='injected independent export fault' or error['message']!='injected independent export fault':raise AssertionError('root cause masked')
   if not any(e['error']=='injected terminal close fault' for e in record['terminal_errors']):raise AssertionError('cleanup fault lost')
  return record
results=[probe(mode) for mode in ('baseline','terminal_wall','terminal_rss','terminal_cpu','partial_export','helper_drift','terminal_close_error','primary_plus_close_error','manifest_error','audit_time')]
checkpins();signal.alarm(0);u=resource.getrusage(resource.RUSAGE_SELF)
out=dict(pins=PINS,cases=results,actual_wall_seconds=real_clock()-START,cpu_user_seconds=u.ru_utime,cpu_system_seconds=u.ru_stime,peak_rss_bytes=u.ru_maxrss,
 scope='synthetic local transport/finalization faults; acceptedcollection verifier mocked; no realdata/fits/realacceptancewrites')
(Path(__import__('tempfile').gettempdir())/'tlab009-runner-independent-rereview-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))

```
