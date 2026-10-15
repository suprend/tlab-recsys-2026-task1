"""Label-blind daily Q/C/B45/chosen3 core; no execution approval or file IO.

Caller supplies a private bounded connection and authenticated lock/pool/choice.
Source formula review, resource owner and exports are separate future gates.
Only the fixed heldout_raw_events relation is read; generic Y builders are absent.
"""
from copy import deepcopy
from datetime import timedelta
import re

from scripts import heldout_contract as h
from scripts import anchor_pilot as anchors
from scripts import candidate_pilot as retrieval
from scripts import manual_features as compiler
from scripts import feature_programs as programs
from scripts.protocol_manifest import validate_protocol

HEADER=[('query_id','VARCHAR'),('product_id','BIGINT'),('from_popular','BOOLEAN'),('from_recent','BOOLEAN'),
        ('popularity_distinct_users','BIGINT'),('popular_source_rank','BIGINT'),('recent_source_rank','BIGINT'),
        ('last_user_event_time','TIMESTAMP'),('user_id','BIGINT'),('anchor','TIMESTAMP'),
        ('candidate_category_id','BIGINT'),('candidate_category_ambiguous','BOOLEAN'),('candidate_category_missing','BOOLEAN'),
        ('item_has_observed_history','BOOLEAN'),('user_has_observed_history','BOOLEAN'),
        ('item_observed_age_seconds','DOUBLE'),('user_observed_age_seconds','DOUBLE')]


def daily_protocol(anchor):
    h.need(anchor in h.DAYS,'Only frozen reserved UTC anchors permitted')
    day=h.utc(anchor);end=(day+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    body=dict(version=1,status='provisional_pilot',timezone='UTC',
        source=dict(start=h.POLICY['source']['start'],end=h.POLICY['source']['end']),pilot=dict(start=anchor,end=end),
        query=dict(kind='daily_clock',hour_utc=0,eligibility_hours=48,eligibility_event_types=['view','cart','purchase'],
                   sampling='sha256_user_day_seed_before_labels',sample_seed=2026,max_users_per_day=2000),
        target=dict(event_type='purchase',horizon_hours=24,include_anchor=True,include_end=False,
                    relevance='distinct_binary_products',maturity='full_horizon',availability_delay_seconds=0),
        candidates=dict(catalog='products_seen_strictly_before_query',popular_limit=200,popular_window_hours=168,
            popular_event_type='purchase',popular_unit='distinct_users',recent_limit=20,recent_window_hours=168,
            recent_event_types=['view','cart','purchase'],max_unique=220,deduplicate='product_id'),
        history=dict(duplicates='raw',ties='global_read_before_update',metadata='last_strict_past_ambiguity_preserved'),
        budget=dict(max_anchors=2000,max_candidate_pairs=440000))
    return validate_protocol(body)


def generated_schema(registry):
    """Compiler emission vocabulary only; not independent source-formula proof."""
    grains={}
    for feature in registry['features']:
        if feature['operator']!='ratio':grains.setdefault(feature['grain'],[]).append(feature)
    result=[]
    for features in grains.values():
        result.extend((f['name'],'DOUBLE' if f['operator']=='recency_seconds' else 'BIGINT') for f in features)
    windows=sorted({f['window'] for f in registry['features'] if f['operator']!='ratio' and type(f['window']) is int})
    result.extend(('source_coverage_'+str(w)+'h','DOUBLE') for w in windows)
    result.extend((f['name'],'DOUBLE') for f in registry['features'] if f['operator']=='ratio')
    result.extend((f['name']+'_missing','BOOLEAN') for f in registry['features']
        if f['operator'] in {'ratio','recency_seconds'} or 'category_id' in compiler.GRAINS[f['grain']])
    return result


def selected_registry(pool,lock,*,authenticated_choice):
    h.validate_lock(lock,authenticated_choice=authenticated_choice)
    # Reconstruct only symbolic definitions; never union/materialize all arms.
    allocation=programs.allocate_slots(pool)
    base=compiler.validate_registry(pool['identity']['base_registry'])
    names=[n for n,t in programs._model_schema(base)]
    h.need(names==lock['models']['B']['feature_names'],'Authenticated B41 differs from fixed pool')
    if lock['choice']=='B':return dict(base=base,registry=deepcopy(base),extra_schema=[],bundle_id=None)
    slot=next(row for row in allocation['identity']['slots'] if row['slot']==lock['choice'])
    h.need(slot['status']=='planned_unexecuted','Chosen collision has no legal physical closure')
    bundle=next(row for row in pool['identity']['bundles'] if row['bundle_id']==slot['bundle_id'])
    delta=[(field['name'],field['dtype']) for field in bundle['physical_delta']]
    h.need(len(delta)==3 and bundle['model_feature_order']==lock['models']['W']['feature_names'],
           'Exact chosen three-column closure/order differs from authenticated W')
    registry=programs.registry_for_slot(pool,allocation,lock['choice'])
    return dict(base=base,registry=registry,extra_schema=delta,bundle_id=bundle['bundle_id'])


def _quote(name):
    h.need(type(name) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,63}',name) is not None,'Unsafe declared feature name')
    return '"'+name+'"'


def _difference(con,left,right,columns):
    fields=','.join(_quote(n) for n in columns)
    return con.execute('SELECT count(*) FROM((SELECT '+fields+' FROM '+left+' EXCEPT ALL SELECT '+fields+' FROM '+right+') UNION ALL(SELECT '+fields+' FROM '+right+' EXCEPT ALL SELECT '+fields+' FROM '+left+'))').fetchone()[0]


def build_day(con,anchor,pool,lock,*,authenticated_choice,check=lambda:None,stage=lambda name,operation:operation()):
    """Creates only TEMP Q/C/F views/tables on caller's private connection.

    Never receives a Y reference. The caller must guard/budget/import/authenticate
    before entry; checks are repeated around each reused helper stage.
    Returns aggregate metadata, not source/model acceptance or target capability.
    """
    check();h.validate_policy(lock['policy']);config=daily_protocol(anchor)
    selected=selected_registry(pool,lock,authenticated_choice=authenticated_choice)
    check()
    h.need(con.execute("SELECT current_setting('threads')").fetchone()[0]==2,'Private source connection must use explicit two threads')
    raw={r[0]:r[1] for r in con.execute('DESCRIBE heldout_raw_events').fetchall()}
    expected=dict(event_time='TIMESTAMP',event_type='VARCHAR',product_id='BIGINT',user_id='BIGINT',category_id='BIGINT')
    h.need(all(raw.get(k)==v for k,v in expected.items()),'Typed raw event identity/time/category required')
    # UTC strings are validated constants; no caller identifier or SQL is emitted.
    lower=h.utc(config['source']['start']).strftime('%Y-%m-%d %H:%M:%S')
    upper=h.utc(anchor).strftime('%Y-%m-%d %H:%M:%S')
    con.execute("CREATE OR REPLACE TEMP VIEW events AS SELECT event_time,event_type,product_id,user_id,category_id FROM heldout_raw_events WHERE event_time>=TIMESTAMP '"+lower+"' AND event_time<TIMESTAMP '"+upper+"'")
    def guarded(name,operation):
        check();result=stage(name,operation);check();return result
    query=anchors.create_queries(con,config,stage=guarded,budget_check=check)
    # All current25..31 horizons mature under explicit Nov1 coverage assumption.
    target_end=h.utc(anchor)+timedelta(hours=config['target']['horizon_hours'],seconds=config['target']['availability_delay_seconds'])
    mature=target_end<=h.utc(config['source']['end'])
    guarded('calendar_maturity',lambda:con.execute('UPDATE pilot_queries SET label_is_mature=?',[mature]))
    retrieval.create_candidates(con,config,stage=guarded)
    retrieval.verify_catalog(con,config,stage=guarded)
    compiler.create_manual_features(con,config,selected['registry'],stage=guarded,budget_check=check)
    check()
    base_schema=HEADER+generated_schema(selected['base']);actual=[tuple(r[:2]) for r in con.execute('DESCRIBE manual_features').fetchall()]
    wanted=HEADER+generated_schema(selected['registry'])
    h.need(actual==wanted and len(base_schema)==45 and len(actual)==45+len(selected['extra_schema']),'Exact daily physical closure/schema differs')
    con.execute('CREATE OR REPLACE TEMP VIEW heldout_base_features AS SELECT '+','.join(_quote(n) for n,t in base_schema)+' FROM manual_features')
    if selected['extra_schema']:
        con.execute('CREATE OR REPLACE TEMP VIEW heldout_extra_features AS SELECT query_id,product_id,'+','.join(_quote(n) for n,t in selected['extra_schema'])+' FROM manual_features')
    else:
        con.execute('DROP VIEW IF EXISTS heldout_extra_features')
    q=con.execute('SELECT count(*),count(DISTINCT query_id),count(DISTINCT(user_id,anchor)),count(*) FILTER(WHERE label_is_mature IS DISTINCT FROM ? OR anchor IS DISTINCT FROM ?::TIMESTAMP) FROM pilot_queries',[mature,h.utc(anchor).replace(tzinfo=None)]).fetchone()
    c=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM pilot_candidates').fetchone()
    f=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM heldout_base_features').fetchone()
    h.need(q[0]==q[1]==q[2] and q[3]==0 and q[0]<=2000 and c[0]==c[1]==f[0]==f[1]<=440000,'Daily unique Q/C/F or maturity/cap differs')
    h.need(_difference(con,'pilot_candidates','heldout_base_features',['query_id','product_id'])==0,'Candidate/fullF key multiset changed')
    orphan=con.execute('SELECT count(*) FROM heldout_base_features f LEFT JOIN pilot_queries q USING(query_id) WHERE q.query_id IS NULL OR f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor').fetchone()[0]
    h.need(orphan==0,'Output Q identity/orphan differs')
    for name,dtype in selected['extra_schema']:
        check();column=_quote(name)
        if dtype=='BIGINT':bad=con.execute('SELECT count(*) FROM heldout_extra_features WHERE '+column+' IS NULL OR '+column+'<0').fetchone()[0]
        elif dtype=='DOUBLE':
            bad=con.execute('SELECT count(*) FROM manual_features WHERE '+_quote(name+'_missing')+' IS DISTINCT FROM ('+column+' IS NULL) OR ('+column+' IS NOT NULL AND (NOT isfinite('+column+') OR '+column+'<=0 OR '+column+'>epoch(anchor)-epoch(?::TIMESTAMP)))',[h.utc(config['source']['start']).replace(tzinfo=None)]).fetchone()[0]
        else:bad=con.execute('SELECT count(*) FROM heldout_extra_features WHERE '+column+' IS NULL').fetchone()[0]
        h.need(bad==0,'Chosen extra type/range/mask differs')
    check()
    return dict(anchor=anchor,query_count=q[0],candidate_count=c[0],mature_query_count=q[0] if mature else 0,
                bundle_id=selected['bundle_id'],base_schema=[list(r) for r in base_schema],extra_schema=[list(r) for r in selected['extra_schema']],
                eligible_user_count=query['population'][0]['eligible_users'],source_formula_acceptance=False,
                target_relation_created=False,physical_daily_key_cover=True,reporting_policy='same_frozen_choice_no_refit_no_adaptation')
