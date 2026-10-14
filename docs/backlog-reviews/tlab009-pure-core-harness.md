# Independent synthetic009 harness archive

The reviewer executed this harness twice on the exact four frozen pure-core pins, with no realdata reads or fits. Only machine paths below are made portable; the independent list oracle is preserved verbatim in [tests/oracles/metadata_price.py](../../tests/oracles/metadata_price.py). [Actual evidence](tlab009-pure-core-evidence.json) and [scope verdict](tlab009-pure-core-review.md) distinguish code acceptance from future runner/source/cardinality/model gates.

Run from the project root only if the exact recorded pure-core version is checked out; later runner appends will intentionally fail its frozen pin check. It is an archived audit, not an automatic approval mechanism or unbounded repeated experiment. Synthetic fixtures use in-memory DuckDB and only aggregate evidence is written to a temporary directory. The portable path conversion was AST-checked without a new execution or fit.

```python
"""Tiny independent verification of exact frozen009 pure core; synthetic only."""
import sys
sys.dont_write_bytecode = True
import hashlib, importlib.util, json, math, random, resource, signal, time,tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
START = time.monotonic()
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('60s cap')))
signal.alarm(60)
resource.setrlimit(resource.RLIMIT_CPU, (55,55))
ROOT=Path.cwd().resolve()
sys.path.insert(0,str(ROOT))
PINS={
 'scripts/metadata_price_features.py':'7c348c28e21baa183b7243c651e976872a23bdd46c44a31b9581a48a33787e3b',
 'tests/test_metadata_price_features.py':'4cc95e3275f7254a6c5413b04274c9f282d1dd323e55f7f76b0971ac88eba021',
 'configs/features/metadata-price.json':'20c11d9bc2e752816c07fe894e975a93a94fd81926ce5de20e250c31283fa2b8',
 'docs/experiments/metadata-price-features.md':'f7f6e921afde0f0d0fb3e497810a364aa13db7a2f3d84fac94c8855c4d2c58f0'}
def checkpins():
 for name, pin in PINS.items():
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=pin:raise ValueError('freeze drift '+name)
checkpins()
spec=importlib.util.spec_from_file_location('independent_oracle',str(ROOT/'tests/oracles/metadata_price.py'))
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
import duckdb, numpy as np
from scripts import metadata_price_features as actual
S=datetime(2019,10,1,tzinfo=timezone.utc);T=datetime(2019,10,10,tzinfo=timezone.utc)
END=datetime(2019,11,1)
def event(i,days=0,seconds=-1,c=1,p=9.,code='code',brand='brand',u=1):
 return dict(event_time=T+timedelta(days=days,seconds=seconds),product_id=i,user_id=u,
             category_id=c,category_code=code,brand=brand,price=p)
gold=[event(1,c=0,code='',brand=''),event(2,c=0,p=99,brand='state:missing',u=99),
 event(3,c=0,p=0),event(4,c=0,p=-2),event(5,c=0,p=None),
 event(6,c=0,p=8),event(6,c=0,p=None,brand=None,u=999),
 event(7,c=7,p=15),event(7,c=None,p=15,u=999),event(8,c=None,p=None,code=None,brand=None),
 event(9,c=9,p=9),event(10,c=10,p=0,code=None),
 event(11,c=11,p=1),event(12,c=11,p=3,code='other'),
 event(13,c=13,p=9,code=None),event(13,days=-8,c=13,p=99,code='прошлый',brand='old'),
 event(14,days=-8,c=0,p=999),event(15,days=-7,seconds=0,c=0,p=3),
 event(16,days=-7,seconds=-1,c=0,p=7),
 event(17,days=-8,c=17,p=3,code='old'),event(17,c=0,p=15),
 event(18,c=18,p=1e-20),event(19,c=18,p=1e300),
 event(20,c=20,p=None,code='value:quoted',brand='state:ambiguous'),
 event(20,c=20,p=None,code=None,brand='state:ambiguous',u=2)]
gold += [dict(gold[1]) for _ in range(4)]
queries=[dict(query_id='a',anchor=T,user_id=1),dict(query_id='b',anchor=T,user_id=2),
         dict(query_id='c',anchor=T+timedelta(days=1),user_id=3)]
candidates=[dict(query_id=q['query_id'],product_id=i) for q in queries
            for i in ([1,3,4,5,6,7,8,9,10,11,13,14,16,17,18,19,20,999] if q['query_id']!='b' else [2,9])]
gold += [event(1,seconds=0,c=999,p=float('nan'),code='future',brand='future'),
         event(999,days=2,c=1,p=float('inf'))]
# First anchor excludes malformed exact-time peer. Second anchor would include it;
# provide a later clean timestamp to exercise selected-latest rather than allpast guard.
gold += [event(1,seconds=1,c=0,p=19,code='',brand=''), event(13,seconds=1,c=13,p=20,code='futurecode')]
counts=dict(cases=0,model_rows=0,feature_comparisons=0,reference_rows=0,provenance_rows=0,
            nonfinite_rejections=0,fault_rejections=0,metamorphic_cases=0)
max_abs=0.;tiny=[]
def rows(con,name):
 cursor=con.execute('SELECT * FROM '+name)
 names=[c[0] for c in cursor.description]
 return [dict(zip(names,r)) for r in cursor.fetchall()]
def run(records,qs,cs,setup_expected=None):
 expected=setup_expected if setup_expected is not None else o.calculate(records,qs,cs,S)
 con=duckdb.connect(':memory:')
 con.execute('SET threads=2');con.execute("SET memory_limit='128MB'");con.execute("SET max_temp_directory_size='0B'")
 con.execute('CREATE TABLE events(event_time TIMESTAMP,product_id BIGINT,user_id BIGINT,category_id BIGINT,category_code VARCHAR,brand VARCHAR,price DOUBLE)')
 if records:con.executemany('INSERT INTO events VALUES(?,?,?,?,?,?,?)',[(r['event_time'].replace(tzinfo=None),r['product_id'],r['user_id'],r['category_id'],r['category_code'],r['brand'],r['price']) for r in records])
 con.execute('CREATE TABLE metadata_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)')
 if qs:con.executemany('INSERT INTO metadata_queries VALUES(?,?,?)',[(q['query_id'],q['user_id'],q['anchor'].replace(tzinfo=None)) for q in qs])
 con.execute('CREATE TABLE metadata_pairs(query_id VARCHAR,product_id BIGINT,candidate_category_id BIGINT,candidate_category_ambiguous BOOLEAN,candidate_category_missing BOOLEAN)')
 for p in expected['source_provenance']:
  state,c=p['field_states']['category_id']
  con.execute('INSERT INTO metadata_pairs VALUES(?,?,?,?,?)',[p['query_id'],p['product_id'],c,state=='ambiguous',state!='clean'])
 try:
  actual.create_metadata_price_features(con,json.loads((ROOT/'configs/features/metadata-price.json').read_text()),source_start=S.replace(tzinfo=None),source_end=END)
 except BaseException:
  con.close();raise
 return con,expected
def compare(records,qs,cs,label):
 global max_abs
 con,e=run(records,qs,cs)
 try:
  got=rows(con,'metadata_price_features');got={ (r['query_id'],r['product_id']):r for r in got}
  exp={ (r['query_id'],r['product_id']):r for r in e['model_rows']}
  if got.keys()!=exp.keys():raise AssertionError('key mismatch')
  for key,r in exp.items():
   for field in o.NOMINAL:
    if got[key][field].encode('utf8')!=r[field]:raise AssertionError((label,key,field,got[key][field],r[field]))
   for field in o.NUMERIC:
    a,b=got[key][field],r[field]
    if isinstance(b,float):
     d=abs(a-b);max_abs=max(max_abs,d)
     if not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-12):raise AssertionError((label,key,field,a,b))
     if key[1]==18 and field=='log_price':tiny.append(dict(label=label,actual=a,oracle=b))
    elif a!=b:raise AssertionError((label,key,field,a,b))
  er={(r['anchor'].replace(tzinfo=None),r['product_id']):(r['category_id'],r['log_price']) for r in e['reference_rows']}
  gr={(r['anchor'],r['product_id']):(r['category_id'],r['log_price']) for r in rows(con,'metadata_price_reference')}
  if er.keys()!=gr.keys():raise AssertionError('fullR identity mismatch')
  for key,(cat,z) in er.items():
   if gr[key][0]!=cat or not math.isclose(gr[key][1],z,rel_tol=1e-9,abs_tol=1e-12):raise AssertionError('fullR value mismatch')
  pe={(r['query_id'],r['product_id']):r for r in e['source_provenance']}
  for r in rows(con,'metadata_price_provenance'):
   z=pe[r['query_id'],r['product_id']]
   if r['in_reference']!=z['actual_member']:raise AssertionError('membership mismatch')
   ts=z['latest'].replace(tzinfo=None) if z['latest'] else None
   if r['latest_timestamp']!=ts:raise AssertionError('latest timestamp mismatch')
   if r['dictionary_code_count']!=len(z['dictionary_codes']):raise AssertionError('dictionary support mismatch')
   dc=z['dictionary_codes'][0] if len(z['dictionary_codes'])==1 else None
   if r['dictionary_code']!=dc:raise AssertionError('dictionary scalar mismatch')
   first=z['dictionary_first_known']
   first=first.replace(tzinfo=None) if first else None
   if r['dictionary_first_known']!=first:raise AssertionError('dictionary availability mismatch')
   for logical,raw,amb in [('category_id','category_id','category_ambiguous'),('category_code','latest_code','latest_code_ambiguous'),('brand','latest_brand','latest_brand_ambiguous'),('price','latest_price','latest_price_ambiguous')]:
    state,value=z['field_states'][logical]
    if r[raw]!=value or r[amb]!=(state=='ambiguous'):raise AssertionError(('provenance independent-field mismatch',logical))
  nums,noms=actual.model_arrays(con,max_rows=1000)
  if nums.shape!=(len(exp),15) or noms.shape!=(len(exp),3):raise AssertionError('matrix shape')
  actual.validate_train_cardinality(noms)
  counts['cases']+=1;counts['model_rows']+=len(exp);counts['feature_comparisons']+=len(exp)*18
  counts['reference_rows']+=len(er);counts['provenance_rows']+=len(pe)
  return got
 finally:con.close()
baseline=compare(gold,queries,candidates,'gold')
# Golden independent truth checks avoid merely two implementations agreeing.
for i,expected_support in [(3,4),(4,4),(5,4),(6,4),(14,4),(16,4)]:
 if baseline['a',i]['category_peer_product_support']!=expected_support:
  raise AssertionError(('hand peer support',i,baseline['a',i]['category_peer_product_support'],expected_support))
if baseline['a',7]['category_peer_product_support'] is not None:raise AssertionError('unknown category must be NULL')
if baseline['a',10]['category_peer_product_support']!=0:raise AssertionError('known empty must be zero')
if baseline['a',3]['price_missing'] or not baseline['a',3]['price_zero']:raise AssertionError('clean0')
if not (baseline['a',6]['price_missing'] and baseline['a',6]['price_ambiguous']):raise AssertionError('ambiguity subtype')
if not baseline['a',13]['code_recovered']:raise AssertionError('dictionary recovery')
rng=random.Random(19009)
for seed in range(8):
 rr=[]
 for j in range(1,36):
  for hour in (0,23,25,100,167,168,192,215,216,217,239):
   r=event(j,seconds=0,c=rng.choice([None,0,1,2,3]),p=rng.choice([None,0.,-1.,.01,1.,99.,1e8]),code=rng.choice([None,'','а','b']),brand=rng.choice([None,'','x','state:missing']))
   r['event_time']=S+timedelta(hours=hour);r['user_id']=rng.randrange(1,10);rr.append(r)
   if rng.random()<.2:rr.append(dict(r,brand=None,user_id=99))
 cc=[dict(query_id=q['query_id'],product_id=j) for q in queries for j in range(1,18)]
 compare(rr,queries,cc,'random'+str(seed))
oneq=queries[:1];onec=[r for r in candidates if r['query_id']=='a']
base1=compare(gold,oneq,onec,'metamorphic_base')
for label, rr in [('reverse',list(reversed(gold))),('duplicate',gold+[dict(gold[1]) for _ in range(17)]),
 ('futurebad',gold+[event(21,seconds=0,c=0,p=float('-inf')),event(22,days=10,c=0,p=float('nan'))])]:
 result=compare(rr,oneq,list(reversed(onec)),label)
 if result!=base1:raise AssertionError('metamorphic output changed '+label)
 counts['metamorphic_cases']+=1
# Failclosed latest malformed candidate and outsideC active, before positive filter.
for bad in [float('nan'),float('inf'),float('-inf')]:
 for i in [1,2]:
  rr=[r for r in gold if not(r['product_id']==i and r['event_time']<T)]+[event(i,c=0,p=bad),event(i,c=0,p=None,u=999)]
  try:run(rr,oneq,onec,setup_expected=o.calculate(gold,oneq,onec,S))
  except ValueError as error:
   if 'Nonfinite price' not in str(error):raise AssertionError('wrong failclosed reason')
   counts['nonfinite_rejections']+=1
  else:raise AssertionError('nonfinite accepted')
# Corrupt actual tables after successful creation; no acceptance or realdata.
for change in ["price_missing=false WHERE product_id=6","brand_ambiguous=false WHERE product_id=6", "code_missing=true WHERE product_id=11", "category_peer_product_support=NULL WHERE product_id=1", "brand='unprefixed' WHERE product_id=1", "log_price='Infinity'::DOUBLE WHERE product_id=1"]:
 con,_=run(gold,oneq,onec)
 try:
  con.execute('UPDATE metadata_price_features SET '+change)
  try:actual.model_arrays(con)
  except ValueError:counts['fault_rejections']+=1
  else:raise AssertionError('corruption accepted '+change)
 finally:con.close()
compare([],[],[],'empty')
con,_=run(gold,oneq,onec)
try:
 con.execute('DELETE FROM metadata_pairs');con.execute('DELETE FROM metadata_queries')
 actual.create_metadata_price_features(con,actual.SPEC,source_start=S.replace(tzinfo=None),source_end=END)
 if any(con.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ['metadata_price_features','metadata_price_reference','metadata_price_provenance']):raise AssertionError('stale empty output')
finally:con.close()
nom=np.array([[('value:'+str(i)).encode(),b'state:missing',b'value:\xd1\x8f'] for i in range(4096)],dtype=object)
if actual.validate_train_cardinality(nom)['category_id_nominal']!=4096:raise AssertionError('4096 cap')
for wrong in [np.vstack((nom,np.array([[b'state:missing',b'state:missing',b'value:x']],dtype=object))),np.array([[b'\xff',b'value:x',b'value:y']],dtype=object)]:
 try:actual.validate_train_cardinality(wrong)
 except (ValueError,UnicodeDecodeError):counts['fault_rejections']+=1
 else:raise AssertionError('cardinality/UTF8 corruption accepted')
checkpins();signal.alarm(0)
usage=resource.getrusage(resource.RUSAGE_SELF)
result=dict(status='independent_tiny_purecore_checked',scope='exactfrozen009purecore_only_no_runner_realdata_fit_acceptance',pins=PINS,
 counts=counts,max_absolute_float_difference=max_abs,float_tolerance=dict(atol=1e-12,rtol=1e-9),tiny_price_sensitivity=tiny,
 wall_seconds=time.monotonic()-START,cpu_user_seconds=usage.ru_utime,cpu_system_seconds=usage.ru_stime,peak_rss_bytes=usage.ru_maxrss)
(Path(tempfile.gettempdir())/'tlab009-independent-core-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

```
