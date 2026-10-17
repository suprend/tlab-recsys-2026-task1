"""One data-free all-eight representation certificate, not feature quality."""
import sys
sys.dont_write_bytecode = True
import json
import hashlib
import time
import resource
import signal
import traceback
import importlib.abc
from pathlib import Path
from datetime import datetime, timedelta

ENTRY = time.monotonic()
OUT = Path(__file__).resolve().parent
ROOT = Path('/Users/mdpospelov/tlab-recsys-2026')
T = datetime(2019, 10, 10)
START = T - timedelta(hours=200)
END = T + timedelta(hours=48)
CASES = ('original', 'row_reverse', 'excluded_peers_future', 'sensitivity')
WORLD_ACTIONS = {'H1': ('view','cart','view','cart','view','cart'),
                 'H2': ('cart','view','view','cart','view','cart')}
AREA_GOLD = {case: {'H1': 3, 'H2': 1} for case in CASES[:3]}
AREA_GOLD['sensitivity'] = {'H1': 1, 'H2': -1}

# Independent interface/literal order, declared before any producer output.
# Source is the B41 contract, not the generated bundle's emitted order.
BASE = (
 ('from_popular','BOOLEAN',False),('from_recent','BOOLEAN',True),
 ('popularity_distinct_users','BIGINT',0),('popular_source_rank','BIGINT',None),
 ('recent_source_rank','BIGINT',1),('candidate_category_ambiguous','BOOLEAN',False),
 ('candidate_category_missing','BOOLEAN',False),('item_has_observed_history','BOOLEAN',True),
 ('user_has_observed_history','BOOLEAN',True),('item_observed_age_seconds','DOUBLE',21600),
 ('user_observed_age_seconds','DOUBLE',21600),('user_view_7d','BIGINT',3),
 ('user_cart_7d','BIGINT',3),('user_purchase_7d','BIGINT',0),
 ('user_distinct_viewed_items_7d','BIGINT',1),('pair_view_7d','BIGINT',3),
 ('pair_cart_7d','BIGINT',3),('pair_purchase_7d','BIGINT',0),
 ('pair_view_recency_seconds','DOUBLE',7200),('pair_purchase_recency_seconds','DOUBLE',None),
 ('item_view_24h','BIGINT',3),('item_purchase_24h','BIGINT',0),
 ('item_distinct_viewers_7d','BIGINT',1),('user_category_view_7d','BIGINT',3),
 ('user_category_view_recency_seconds','DOUBLE',7200),('item_category_view_7d','BIGINT',3),
 ('category_view_7d','BIGINT',3),('source_coverage_24h','DOUBLE',1),
 ('source_coverage_168h','DOUBLE',1),('user_category_view_share_7d','DOUBLE',1),
 ('item_category_view_share_7d','DOUBLE',1),('pair_view_recency_seconds_missing','BOOLEAN',False),
 ('pair_purchase_recency_seconds_missing','BOOLEAN',True),
 ('user_category_view_7d_missing','BOOLEAN',False),
 ('user_category_view_share_7d_missing','BOOLEAN',False),
 ('user_category_view_recency_seconds_missing','BOOLEAN',False),
 ('item_category_view_7d_missing','BOOLEAN',False),('category_view_7d_missing','BOOLEAN',False),
 ('item_category_view_share_7d_missing','BOOLEAN',False),
 ('retrieval_last_event_age_seconds','DOUBLE',3600),('retrieval_last_event_missing','BOOLEAN',False))
EXTRA = {
 'L01':(('auto_user_view_count_24h','BIGINT',3),('auto_user_cart_count_24h','BIGINT',3),('auto_user_purchase_count_24h','BIGINT',0)),
 'L02':(('auto_pair_view_count_24h','BIGINT',3),('auto_pair_cart_count_24h','BIGINT',3),('auto_pair_purchase_count_24h','BIGINT',0)),
 'L03':(('auto_item_view_count_168h','BIGINT',3),('auto_item_cart_count_168h','BIGINT',3),('auto_item_purchase_count_168h','BIGINT',0)),
 'L04':(('auto_user_view_count_distinct_24h_product_id','BIGINT',1),('auto_user_cart_count_distinct_168h_product_id','BIGINT',1),('auto_user_purchase_count_distinct_168h_product_id','BIGINT',0)),
 'L05':(('auto_item_view_count_distinct_24h_user_id','BIGINT',1),('auto_item_cart_count_distinct_168h_user_id','BIGINT',1),('auto_item_purchase_count_distinct_24h_user_id','BIGINT',0)),
 'L06':(('auto_pair_cart_recency_seconds_observed','DOUBLE',3600),('auto_item_cart_count_24h','BIGINT',3),('auto_pair_cart_recency_seconds_observed_missing','BOOLEAN',False)),
 'L07':(('auto_user_cart_recency_seconds_observed','DOUBLE',3600),('auto_user_purchase_count_distinct_24h_product_id','BIGINT',0),('auto_user_cart_recency_seconds_observed_missing','BOOLEAN',False)),
 'L08':(('auto_item_cart_recency_seconds_observed','DOUBLE',3600),('auto_item_cart_count_distinct_24h_user_id','BIGINT',1),('auto_item_cart_recency_seconds_observed_missing','BOOLEAN',False))}
# Source-free row-list interpretation is separate from compiler/registry code.
COUNT_SPEC = {
 'user_view_7d':('view',168,False), 'user_cart_7d':('cart',168,False),
 'user_purchase_7d':('purchase',168,False),'user_distinct_viewed_items_7d':('view',168,True),
 'pair_view_7d':('view',168,False),'pair_cart_7d':('cart',168,False),
 'pair_purchase_7d':('purchase',168,False),'item_view_24h':('view',24,False),
 'item_purchase_24h':('purchase',24,False),'item_distinct_viewers_7d':('view',168,True),
 'user_category_view_7d':('view',168,False),'item_category_view_7d':('view',168,False),
 'category_view_7d':('view',168,False)}

class NoML(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'catboost','torch','tensorflow','sklearn','tsfresh'}:
            raise AssertionError('Forbidden ML import: '+fullname)
sys.meta_path.insert(0, NoML())

def digest(path):
    b=Path(path).read_bytes()
    return dict(path=str(path),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())

def write(name, value):
    p=OUT/name
    if p.exists(): raise RuntimeError('Immutable output already exists: '+str(p))
    p.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
    return digest(p)

def rss():
    n=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(n if sys.platform=='darwin' else n*1024)

def guard():
    r=resource.getrusage(resource.RUSAGE_SELF)
    if r.ru_utime+r.ru_stime>8.5: raise TimeoutError('Child cooperative8.5 CPU cap')
    if time.monotonic()-ENTRY>18: raise TimeoutError('Child cooperative18 wall cap')
    if rss()>512*2**20: raise MemoryError('Observed512MiB RSS cap')
    if sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())>5*2**20:
        raise MemoryError('5MiB output cap')

def fixture(world, case):
    rows=[(T-timedelta(hours=6-j),action,201,101,301)
          for j,action in enumerate(WORLD_ACTIONS[world])]
    if case=='row_reverse': rows.reverse()
    elif case=='excluded_peers_future':
        rows += [(T,'view',201,101,None),(T,'cart',201,101,999),
                 (T+timedelta(hours=1),'purchase',201,101,999)]
    elif case=='sensitivity':
        rows=[(T-timedelta(minutes=30),a,i,u,c) if t==T-timedelta(hours=2) else (t,a,i,u,c)
              for t,a,i,u,c in rows]
    return rows

def literal_gold(case,bundle):
    result=list(BASE)+list(EXTRA[bundle])
    if case=='sensitivity':
        result=[(n,k,1800 if n in {'pair_view_recency_seconds',
             'user_category_view_recency_seconds','retrieval_last_event_age_seconds'} else v) for n,k,v in result]
    return result

def row_list_oracle(rows,case,bundle):
    # This fixture has one nominal user/item/category. Check that premise.
    past=[r for r in rows if START<=r[0]<T]
    assert all(r[2:]==(201,101,301) for r in past)
    assert len(past)==6
    value={}
    for name,(action,hours,distinct) in COUNT_SPEC.items():
        selected=[r for r in past if r[1]==action and r[0]>=T-timedelta(hours=hours)]
        value[name]=len({r[2] if 'user_' in name else r[3] for r in selected}) if distinct else len(selected)
    for action,name in [('view','pair_view_recency_seconds'),('purchase','pair_purchase_recency_seconds'),
                         ('view','user_category_view_recency_seconds')]:
        times=[r[0] for r in past if r[1]==action]
        value[name]=(T-max(times)).total_seconds() if times else None
    value.update(user_category_view_share_7d=value['user_category_view_7d']/value['user_view_7d'],
                 item_category_view_share_7d=value['item_category_view_7d']/value['category_view_7d'])
    for n in [n for n in value if n.endswith('_seconds') or 'category' in n]:
        value[n+'_missing']=value[n] is None
    value.update(from_popular=False,from_recent=True,popularity_distinct_users=0,popular_source_rank=None,
                 recent_source_rank=1,candidate_category_ambiguous=False,candidate_category_missing=False,
                 item_has_observed_history=bool(past),user_has_observed_history=bool(past),
                 item_observed_age_seconds=(T-min(r[0] for r in past)).total_seconds(),
                 user_observed_age_seconds=(T-min(r[0] for r in past)).total_seconds(),
                 retrieval_last_event_age_seconds=(T-max(r[0] for r in past)).total_seconds(),
                 retrieval_last_event_missing=not bool(past))
    for h in (24,168):
        value['source_coverage_'+str(h)+'h']=max(0,(min(T,END)-max(T-timedelta(hours=h),START)).total_seconds())/(h*3600)
    for name,kind,literal in EXTRA[bundle]:
        if name.endswith('_missing'): value[name]=False
        elif '_recency_' in name:
            value[name]=(T-max(r[0] for r in past if r[1]=='cart')).total_seconds()
        else:
            action=next(a for a in ('view','cart','purchase') if '_'+a+'_' in name)
            h=24 if '_24h' in name else 168
            subset=[r for r in past if r[1]==action and r[0]>=T-timedelta(hours=h)]
            value[name]=len({r[2] if name.startswith('auto_user_') else r[3] for r in subset}) if '_distinct_' in name else len(subset)
    result=[(n,k,value[n]) for n,k,_ in literal_gold(case,bundle)]
    assert result==literal_gold(case,bundle), ('Independent list/literal mismatch',case,bundle,result)
    return result

def area(rows):
    kept=[r for r in rows if T-timedelta(hours=168)<=r[0]<T]
    return sum((a[1]=='view')*(b[1]=='cart')-(a[1]=='cart')*(b[1]=='view')
               for a in kept for b in kept if a[0]<b[0])

def projection(con, order, np):
    fields=[]
    for n in order:
        if n=='retrieval_last_event_age_seconds':
            fields.append('CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds')
        elif n=='retrieval_last_event_missing':
            fields.append('CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing')
        else: fields.append('CAST(f."'+n+'" AS FLOAT) AS "'+n+'"')
    cur=con.execute('SELECT '+','.join(fields)+' FROM manual_features f ORDER BY f.query_id,f.product_id')
    assert [c[0] for c in cur.description]==order
    assert [str(c[1]) for c in cur.description]==['FLOAT']*44
    parts=cur.fetchnumpy(); arrays=[]
    for n in order:
        a=parts[n]
        if np.ma.isMaskedArray(a): a=a.astype(np.float32).filled(np.nan)
        arrays.append(np.asarray(a,dtype=np.float32))
    return np.column_stack(arrays)

def run(result):
    # Every independent expected row is sealed before importing the producer.
    expected={}
    for case in CASES:
        for world in WORLD_ACTIONS:
            rows=fixture(world,case)
            result['area_evaluations']+=1
            actual_area=area(rows)
            assert actual_area==AREA_GOLD[case][world]
            for b in EXTRA:
                expected[case,world,b]=row_list_oracle(rows,case,b)
    sealed={'cases':{case:{'area':AREA_GOLD[case],
        'bundles':{b:[list(x) for x in expected[case,'H1',b]] for b in EXTRA}} for case in CASES},
        'note':'Independent hand literals and row-list interpretation; before producer imports/results.'}
    result['expected_before_producer']=write('expected-before-producer.json',sealed)
    sys.path.insert(0,str(ROOT))
    import duckdb
    import numpy as np
    from scripts import feature_programs as programs
    from scripts import manual_features as compiler
    from scripts import train_baselines as baseline
    config=json.loads((ROOT/'configs/protocols/clock-48h.json').read_text())
    config['source']={'start':START.strftime('%Y-%m-%dT%H:%M:%SZ'),'end':END.strftime('%Y-%m-%dT%H:%M:%SZ')}
    config['pilot']={'start':T.strftime('%Y-%m-%dT%H:%M:%SZ'),'end':(T+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}
    config['query']['max_users_per_day']=1
    config['budget']={'max_anchors':1,'max_candidate_pairs':220}
    base=compiler.load_registry(ROOT/'configs/features/manual-18.json')
    contract=json.loads((ROOT/'configs/features/automation-pool.json').read_text())
    pool=programs.generate_pool(contract,base)
    allocation=programs.allocate_slots(pool)
    result['generation']={'explicit_calls':1,'allocation_calls':1,'internal_validation_regeneration_calls':1,
                          'pool_id':pool['pool_id'],'allocation_id':allocation['allocation_id'],
                          'slots':[s['bundle_id'] for s in allocation['identity']['slots']],
                          'search_redraw_or_repair':0}
    assert [(x['name'],x['dtype']) for x in pool['identity']['base_model_schema']]==[(n,k) for n,k,v in BASE]
    assert [b['bundle_id'] for b in pool['identity']['bundles']]==list(EXTRA)
    projected={}; observed={}
    for case in CASES:
        for world in WORLD_ACTIONS:
            guard()
            con=duckdb.connect(':memory:')
            try:
                con.execute('SET threads=1'); con.execute("SET memory_limit='128MiB'")
                con.execute("SET max_temp_directory_size='0B'")
                con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
                con.executemany('INSERT INTO events VALUES (?,?,?,?,?)',fixture(world,case))
                con.execute('CREATE TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
                con.execute('INSERT INTO pilot_queries VALUES (?,?,?,?)',['invented-q',101,T,True])
                con.execute('''CREATE TABLE pilot_candidates(query_id VARCHAR,product_id BIGINT,from_popular BOOLEAN,
                    from_recent BOOLEAN,popularity_distinct_users BIGINT,popular_source_rank BIGINT,
                    recent_source_rank BIGINT,last_user_event_time TIMESTAMP)''')
                last=T-timedelta(seconds=1800 if case=='sensitivity' else 3600)
                con.execute('INSERT INTO pilot_candidates VALUES (?,?,?,?,?,?,?,?)',['invented-q',201,False,True,0,None,1,last])
                for bundle in pool['identity']['bundles']:
                    guard(); b=bundle['bundle_id']; gold=expected[case,world,b]
                    order=[n for n,k,v in gold]
                    assert bundle['model_feature_order']==order
                    assert [(d['name'],d['dtype']) for d in bundle['physical_delta']]==[(n,k) for n,k,v in EXTRA[b]]
                    result['registry_evaluations']+=1
                    production=compiler.create_manual_features(con,config,bundle['registry'],budget_check=guard)
                    assert production['feature_rows']==1
                    schema={r[0]:r[1] for r in con.execute('DESCRIBE manual_features').fetchall()}
                    assert len(schema)==48
                    assert all(schema[n]==kind for n,kind,v in gold if not n.startswith('retrieval_last_'))
                    # Actual production base naming, independently fixed B41 order.
                    base_physical=[n for n in schema if not n.startswith('auto_')]
                    assert baseline.numeric_feature_names(base_physical)==[n for n,k,v in BASE]
                    raw_fields=[n for n,k,v in gold if not n.startswith('retrieval_last_')]
                    raw=con.execute('SELECT '+','.join('"'+n+'"' for n in raw_fields)+' FROM manual_features').fetchall()
                    assert raw==[tuple(v for n,k,v in gold if not n.startswith('retrieval_last_'))]
                    result['raw_closure_literal_cells']+=len(raw_fields)
                    matrix=projection(con,order,np)
                    literal=np.array([[np.nan if v is None else v for n,k,v in gold]],dtype=np.float32)
                    assert matrix.shape==(1,44) and matrix.dtype==np.float32
                    np.testing.assert_array_equal(np.isnan(matrix),np.isnan(literal))
                    np.testing.assert_array_equal(matrix[~np.isnan(literal)],literal[~np.isnan(literal)])
                    result['projected_literal_cells']+=44
                    projected[case,world,b]=matrix
                    observed[case,world,b]=[None if np.isnan(x) else float(x) for x in matrix[0]]
                    tables={r[0] for r in con.execute('SHOW TABLES').fetchall()}
                    assert not tables&{'pilot_labels','all_labels','chosen_labels'}
                    guard()
            finally: con.close()
    for case in CASES:
        for b in EXTRA:
            a=projected[case,'H1',b]; z=projected[case,'H2',b]
            np.testing.assert_array_equal(a,z)
            result['cross_world_cells'][case]+=44
            for world in WORLD_ACTIONS:
                if case in CASES[1:3]:
                    np.testing.assert_array_equal(projected[case,world,b],projected['original',world,b])
                    result['within_world_invariance_cells']+=44
                elif case=='sensitivity':
                    col=[n for n,k,v in BASE].index('pair_view_recency_seconds')
                    assert projected['original',world,b][0,col]==7200
                    assert projected[case,world,b][0,col]==1800
                    result['sensitivity_checks']+=1
    assert result['registry_evaluations']==64 and result['area_evaluations']==8
    assert set(result['cross_world_cells'].values())=={352}
    result['complete_projected_rows']={case:{world:{b:observed[case,world,b] for b in EXTRA} for world in WORLD_ACTIONS} for case in CASES}
    result['schema_order_types']={b:[[n,k] for n,k,v in literal_gold('original',b)] for b in EXTRA}
    result['areas']=AREA_GOLD
    result['source_projection']={'last_user_event_time_seconds_before_T':{'original':3600,'row_reverse':3600,'excluded_peers_future':3600,'sensitivity':1800},
                                 'provided_fixed_candidates':True,'retrieval_recomputed':False,
                                 'projection_seam':'Exact label-free FLOAT expressions from model_data/train_baselines; not full Y-aware loaders.'}
    result['forbidden_module_imports']=[n for n in sys.modules if n.split('.')[0] in {'catboost','torch','tensorflow','sklearn','tsfresh'}]
    assert not result['forbidden_module_imports']
    guard()

if __name__=='__main__':
    signal.signal(signal.SIGALRM,lambda a,b: (_ for _ in ()).throw(TimeoutError('Child18s alarm')))
    signal.alarm(18)
    result={'status':'STARTED','registry_evaluations':0,'area_evaluations':0,
            'raw_closure_literal_cells':0,'projected_literal_cells':0,
            'cross_world_cells':{case:0 for case in CASES},'within_world_invariance_cells':0,
            'sensitivity_checks':0,'fits':0,'model_loads':0,'predictions':0,'real_data_reads':0,
            'historical_first_unchanged':digest('/tmp/tlab-wave099-B-FIRST.md'),
            'schema_and_literals_frozen_in_script':digest(__file__)}
    try:
        run(result);result['status']='COMPLETE_PRODUCED_UNREVIEWED'
    except BaseException as e:
        result['status']='FAILED';result['error_type']=type(e).__name__;result['error']=str(e)
        traceback.print_exc()
    finally:
        r=resource.getrusage(resource.RUSAGE_SELF)
        result['resource_prefix']={'cpu_seconds':r.ru_utime+r.ru_stime,'wall_seconds':time.monotonic()-ENTRY,
                                   'max_rss_bytes':rss(),'note':'Before final JSON write and interpreter shutdown; parent receipt covers reaped process.'}
        write('result.json',result)
        print(json.dumps({k:result[k] for k in ('status','registry_evaluations','area_evaluations','cross_world_cells','resource_prefix')}),flush=True)
    raise SystemExit(0 if result['status']=='COMPLETE_PRODUCED_UNREVIEWED' else 1)
