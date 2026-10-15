# Independent016 tiny audit archive

Historical exactfreeze script; machine paths made portable and the external freeze JSON embedded. Original doc bytes are archived in the publication note because only its status paragraph changed after review. No actualdata/Pool/fits; only selected12newphysicalcolumns across≤25inputrowfixtures. Extract/run at the reviewed code/doc version for exact pre/postfreeze reproduction.

```python
import sys,json,hashlib,time,resource
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timedelta
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd().resolve()))
import duckdb
from scripts import feature_programs as p
from scripts import manual_features as m
from scripts.protocol_manifest import load_protocol
START=time.monotonic();CPU=time.process_time();ROOT=Path(str(Path.cwd().resolve()));results=[]
FROZEN={'scripts/feature_programs.py': 'afaefd6b2a608870d952c0782d2ca9fcbd685f9650afe6229ee74772bab92bf7', 'tests/test_feature_programs.py': '18135cd1157d35ea374d9fa286c425051d886e78709b67b29eadbccfba2d194b', 'configs/features/automation-pool.json': 'ef34f45d244bb0458c2af7928c0dad7f57d178d397abee1a9e87e419457cbbb3', 'docs/experiments/feature-programs.md': 'dafdde7c45424d22b7d4df6b919417b1a000e7c28ad778d0981c82b9bce37666'}
def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FROZEN}
before=hashes();assert before==FROZEN
contract=json.loads((ROOT/'configs/features/automation-pool.json').read_text());base=json.loads((ROOT/'configs/features/manual-18.json').read_text())
canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
digest=lambda v:hashlib.sha256(canon(v).encode()).hexdigest()
def rejects(fn):
 try:fn()
 except ValueError as e:return str(e)
 raise AssertionError('mutant accepted')
def case(name,fn):
 try:results.append(dict(case=name,status='PASS',detail=fn()))
 except Exception as e:results.append(dict(case=name,status='FAIL',error=repr(e)))
with patch.object(duckdb,'connect',side_effect=AssertionError('symbolic generation opened SQL')):
 pool=p.generate_pool(contract,base);allocation=p.allocate_slots(pool)
assert [z['bundle_id'] for z in allocation['identity']['slots']]==['L02','L06','L01','L05']
SELECTED={z['bundle_id']:z for z in pool['identity']['bundles'] if z['bundle_id'] in {'L01','L02','L05','L06'}}
S=datetime(2019,10,1);T=datetime(2019,10,10)
# Independently literal source; no author fixture or expected helpers imported.
E=[(T-timedelta(hours=1),'view',10,1,100),(T-timedelta(hours=2),'cart',10,1,100),(T-timedelta(hours=2),'cart',10,1,100),(T-timedelta(hours=3),'purchase',10,1,100),(T-timedelta(days=8),'cart',10,2,100),(T-timedelta(hours=2),'view',20,2,200),(T-timedelta(hours=25),'purchase',20,2,200),(T,'cart',20,1,None),(T+timedelta(hours=1),'purchase',20,1,None)]
Q=[('U',1,T,True),('V',2,T,True),('EU',1,T+timedelta(days=1),True),('EV',2,T+timedelta(days=1),True)]
C=[('U',10),('U',20),('U',30),('V',10),('V',20)]
NAMES={
 'L01':['auto_user_view_count_24h','auto_user_cart_count_24h','auto_user_purchase_count_24h'],
 'L02':['auto_pair_view_count_24h','auto_pair_cart_count_24h','auto_pair_purchase_count_24h'],
 'L05':['auto_item_view_count_distinct_24h_user_id','auto_item_cart_count_distinct_168h_user_id','auto_item_purchase_count_distinct_24h_user_id'],
 'L06':['auto_pair_cart_recency_seconds_observed','auto_pair_cart_recency_seconds_observed_missing','auto_item_cart_count_24h']}
GOLD={
 'L01':[(1,2,1),(1,2,1),(1,2,1),(1,0,0),(1,0,0)],
 'L02':[(1,2,1),(0,0,0),(0,0,0),(0,0,0),(1,0,0)],
 'L05':[(1,1,1),(1,0,0),(0,0,0),(1,1,1),(1,0,0)],
 'L06':[(7200.,False,2),(None,True,0),(None,True,0),(691200.,False,2),(None,True,0)]}
def own_values(events,bundle,user,item,anchor):
 past=[e for e in events if S<=e[0]<anchor]
 def window(action,hours,grain):
  return [e for e in past if e[1]==action and e[0]>=anchor-timedelta(hours=hours) and (grain!='user' or e[3]==user) and (grain!='pair' or (e[3]==user and e[2]==item)) and (grain!='item' or e[2]==item)]
 if bundle in {'L01','L02'}:return tuple(len(window(a,24,'user' if bundle=='L01' else 'pair')) for a in ['view','cart','purchase'])
 if bundle=='L05':return tuple(len({e[3] for e in window(a,h,'item') if e[3] is not None}) for a,h in [('view',24),('cart',168),('purchase',24)])
 assert bundle=='L06'
 carts=[e[0] for e in past if e[1]=='cart' and e[3]==user and e[2]==item]
 return ((anchor-max(carts)).total_seconds() if carts else None,not bool(carts),len(window('cart',24,'item')))
def calculate(registry,events):
 assert len(events)+len(Q)+len(C)<=32
 config=load_protocol(ROOT/'configs/protocols/clock-48h.json');config['pilot']['end']='2019-10-12T00:00:00Z';config['query']['max_users_per_day']=2;config['budget']['max_anchors']=8
 con=duckdb.connect(':memory:')
 try:
  con.execute('SET threads=2');con.execute("SET memory_limit='256MB'");con.execute("SET max_temp_directory_size='0B'")
  con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)');con.executemany('INSERT INTO events VALUES(?,?,?,?,?)',events)
  if any(e[2]==2**60+1 for e in events):assert con.execute('SELECT product_id FROM events WHERE product_id>?',[2**60]).fetchone()[0]==2**60+1
  con.execute('CREATE TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)');con.executemany('INSERT INTO pilot_queries VALUES(?,?,?,?)',Q)
  con.execute('CREATE TABLE pilot_candidates(query_id VARCHAR,product_id BIGINT,from_popular BOOLEAN,from_recent BOOLEAN,popularity_distinct_users BIGINT,popular_source_rank BIGINT,recent_source_rank BIGINT,last_user_event_time TIMESTAMP)')
  con.executemany('INSERT INTO pilot_candidates VALUES(?,?,false,true,0,NULL,1,NULL)',C)
  accounting=m.create_manual_features(con,config,registry)
  schema=[(r[0],r[1]) for r in con.execute('DESCRIBE manual_features').fetchall()]
  names=[n for n,t in schema];rows={r[:2]:dict(zip(names,r)) for r in con.execute('SELECT * FROM manual_features ORDER BY query_id,product_id').fetchall()}
  return rows,schema,accounting
 finally:con.close()
def numeric(events,literal=False):
 baseline,base_schema,accounting=calculate(base,events)
 excluded={'query_id','user_id','product_id','anchor','candidate_category_id','last_user_event_time'}
 expected_model_schema=[dict(name=n,dtype=t) for n,t in base_schema if n not in excluded]+[dict(name='retrieval_last_event_age_seconds',dtype='DOUBLE'),dict(name='retrieval_last_event_missing',dtype='BOOLEAN')]
 assert expected_model_schema==pool['identity']['base_model_schema'] and len(expected_model_schema)==41
 actualcolumns=set();compared=0
 for slot in allocation['identity']['slots']:
  bid=slot['bundle_id'];bundle=SELECTED[bid];registry=p.registry_for_slot(pool,allocation,slot['slot']);rows,schema,acc=calculate(registry,events)
  assert set(rows)==set(C) and acc['feature_rows']==5 and len(acc['daily_state'])==2
  delta=[(n,t) for n,t in schema if n not in dict(base_schema)]
  assert delta==[(v['name'],v['dtype']) for v in bundle['physical_delta']] and len(delta)==3
  assert set(NAMES[bid])=={n for n,t in delta}
  assert {n:t for n,t in delta}==dict(zip(NAMES[bid],['DOUBLE','BOOLEAN','BIGINT'] if bid=='L06' else ['BIGINT']*3))
  assert bundle['model_feature_order']==[v['name'] for v in expected_model_schema]+[n for n,t in delta]
  actualcolumns.update(n for n,t in delta)
  for index,(qid,item) in enumerate(C):
   values=tuple(rows[qid,item][n] for n in NAMES[bid]);expected=own_values(events,bid,1 if qid=='U' else 2,item,T)
   assert values==expected,(bid,qid,item,values,expected)
   if literal:assert values==GOLD[bid][index]
   if bid=='L06':assert type(values[1]) is bool and (values[0] is None)==values[1]
   for name,t in base_schema:assert rows[qid,item][name]==baseline[qid,item][name],('base changed',bid,name)
   compared+=3
 assert len(actualcolumns)==12
 return dict(input_rows=len(events)+len(Q)+len(C),new_columns=len(actualcolumns),every_key_scalar_comparisons=compared,base_schema_numeric=41,unchanged_base_values=True)
case('selected12_full_literal_and_independent_list',lambda:numeric(E,True))
EXTRA=[(T-timedelta(hours=24),'view',10,1,None),(T-timedelta(hours=24,seconds=1),'view',10,1,None),(S-timedelta(seconds=1),'cart',30,1,None),(T-timedelta(minutes=30),'cart',10,None,None),(T-timedelta(minutes=20),'view',10,None,None),(T-timedelta(hours=4),'purchase',2**60+1,1,None),(T-timedelta(days=7),'cart',20,2,None)]
case('selected12_boundaries_NULL_projection_exact_BIGINT',lambda:numeric(E+EXTRA))
case('selected12_global_peers_and_future_permutation',lambda:numeric(list(reversed(E+[(T,'cart',10,1,None),(T+timedelta(hours=2),'view',30,2,None)]))))
def bad_contract(change):
 c=deepcopy(contract);change(c);return rejects(lambda:p.generate_pool(c,base))
for name,mutate in [
 ('version_bool',lambda c:c.update(version=True)),('window_float',lambda c:c['grammar']['windows_hours'].__setitem__(0,24.)),
 ('draws_bool',lambda c:c['allocation'].update(random_draws=True)),('maxcols_bool',lambda c:c['allocation'].update(max_new_columns=True)),
 ('missing_cart',lambda c:c['schema']['observed_actions'].remove('cart')),('unknown_clock',lambda c:c['context'].update(source_availability='unknown')),
 ('numeric_identity',lambda c:c['schema']['fields']['product_id'].update(role='numeric_measure')),('injected_operator',lambda c:c['grammar']['operators'].append('SUM(x);DROP TABLE events')),
 ('binding_float',lambda c:c['grammar']['action_count_bindings'][0].update(window=24.)),('extra_binding',lambda c:c['grammar']['action_count_bindings'].append(dict(grain='user',window=24))),
]:case('contract_'+name,lambda mutate=mutate:bad_contract(mutate))
def resealed_pool():
 x=deepcopy(pool);x['identity']['bundles'][0]['programs'][0]['window']=168;x['pool_id']=digest(x['identity'])
 return rejects(lambda:p.allocate_slots(x))
case('fresh_resealed_noncanonical_pool',resealed_pool)
def resealed_allocation():
 x=deepcopy(allocation);x['identity']['slots'][0]['bundle_id']='L03';x['allocation_id']=digest(x['identity'])
 return rejects(lambda:p.registry_for_slot(pool,x,'I1'))
case('fresh_resealed_allocation_replacement',resealed_allocation)
def renamed_alias():
 x=deepcopy(base);x['features'][1].update(name='renamed_user_cart24',window=24)
 return rejects(lambda:p.generate_pool(contract,x))
case('semantic_alias_survives_rename',renamed_alias)
def feature_mutant(kind):
 original=p._feature
 def mutation(grain,action,op,window,column=None):
  if kind=='retrieval' and (grain,action,op,window)==('item','purchase','count_distinct',24):window=168
  if kind=='coverage' and (grain,action,op,window)==('user','purchase','count',24):window=72
  if kind=='mask' and (grain,action,op,window)==('user','purchase','count',24):op,window,column='recency_seconds','observed','event_time'
  return original(grain,action,op,window,column)
 with patch.object(p,'_feature',side_effect=mutation):return rejects(lambda:p.generate_pool(contract,base))
for kind in ['retrieval','coverage','mask']:case('generated_mutant_'+kind,lambda kind=kind:feature_mutant(kind))
def collision():
 with patch.object(p.random.Random,'choices',return_value=['L02','L06']) as draw:
  x=p.allocate_slots(pool);assert draw.call_count==1 and draw.call_args.kwargs['k']==2
  ss=x['identity']['slots'];assert [s['status'] for s in ss[2:]]==['collision_consumed_no_refill']*2
  assert [s['duplicate_of'] for s in ss[2:]]==['I1','I2'] and sum(s['new_physical_columns'] for s in ss)==6
  assert all(s['fit_budget_slots_consumed']==1 and s['native_fits_started']==0 and s['execution_approved'] is False for s in ss)
  rejected=rejects(lambda:p.registry_for_slot(pool,x,'R1'))
  return dict(draw_calls_before_registry=1,no_redraw=True,colliding_slot_rejected=rejected)
case('forced_R_to_I_collisions_consumed_once',collision)
def caller_binding_observation():
 altered=deepcopy(base);altered['features'][1]['event_type']='purchase'
 x=p.generate_pool(contract,altered);assert x['pool_id']!=pool['pool_id'] and x['identity']['execution_approved'] is False
 return 'Noncanonical declared base with same18/41 accepted under a different pool_id; exact final019/base_registry binding is external and indispensable, not established by counts.'
case('declared_base_not_external_acceptance_observation',caller_binding_observation)
after=hashes();assert after==before
out=dict(before=before,after=after,cases=results,wall_seconds=time.monotonic()-START,cpu_seconds=time.process_time()-CPU,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,numeric_scope='only selected L02/L06/L01/L05:12 unique newphysicalcolumns;18/25/20 inputrows; baseline preservations only',no_data_Pool_model_fit=True)
(Path(__import__('tempfile').gettempdir())/'tlab016-programs-independent-results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if any(r['status']=='FAIL' for r in results):sys.exit(1)

```
