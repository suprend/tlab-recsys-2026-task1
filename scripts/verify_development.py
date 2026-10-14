"""Independent, read-only protocol-v1/manual18 source verification.

External expectations are inputs, never manufactured or approved by this module.
Q/Y/C are exhaustive source relations; F values are explicitly sampled.
"""
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import hashlib
import json
import math
import resource
import sys
import threading
import time

import duckdb

from scripts.protocol_manifest import (_read_json, _keys, _hashes, _relative_path,
    canonical_json, validate_protocol, validate_run_manifest)

POLICY = 'protocol-v1-manual18-source-oracle-v1'
PRODUCER_CODE = {'uv.lock', 'scripts/temporal_contract.py', 'scripts/protocol_manifest.py',
    'scripts/anchor_pilot.py', 'scripts/candidate_pilot.py', 'scripts/ranking_metrics.py',
    'scripts/heuristic_baselines.py', 'scripts/manual_features.py', 'scripts/development_collection.py'}
CORE = [
    ('user_view_7d','user','view','count',168,None),
    ('user_cart_7d','user','cart','count',168,None),
    ('user_purchase_7d','user','purchase','count',168,None),
    ('user_distinct_viewed_items_7d','user','view','count_distinct',168,'product_id'),
    ('pair_view_7d','pair','view','count',168,None),
    ('pair_cart_7d','pair','cart','count',168,None),
    ('pair_purchase_7d','pair','purchase','count',168,None),
    ('pair_view_recency_seconds','pair','view','recency_seconds','observed','event_time'),
    ('pair_purchase_recency_seconds','pair','purchase','recency_seconds','observed','event_time'),
    ('item_view_24h','item','view','count',24,None),
    ('item_purchase_24h','item','purchase','count',24,None),
    ('item_distinct_viewers_7d','item','view','count_distinct',168,'user_id'),
    ('user_category_view_7d','user_category','view','count',168,None),
    ('user_category_view_share_7d','user_category','ratio','user_category_view_7d','user_view_7d',None),
    ('user_category_view_recency_seconds','user_category','view','recency_seconds','observed','event_time'),
    ('item_category_view_7d','item_category','view','count',168,None),
    ('category_view_7d','category','view','count',168,None),
    ('item_category_view_share_7d','item_category','ratio','item_category_view_7d','category_view_7d',None)]
REGISTRY = dict(version=1,name='manual18',history='strict_past_raw_event_rows',
    category_policy='latest_global_past_timestamp_null_mixture_ambiguous',
    category_counter_key='historical_event_category_id',known_key_empty_count=0,
    unknown_conditional_key=None,undefined_ratio=None,missing_recency=None,features=[
        dict(name=n,grain=g,operator='ratio',numerator=op,denominator=w) if e=='ratio' else
        dict(name=n,grain=g,event_type=e,operator=op,window=w,column=c) for n,g,e,op,w,c in CORE])
C_SCHEMA = [('query_id','VARCHAR'),('product_id','BIGINT'),('from_popular','BOOLEAN'),
    ('from_recent','BOOLEAN'),('popularity_distinct_users','BIGINT'),('popular_source_rank','BIGINT'),
    ('recent_source_rank','BIGINT'),('last_user_event_time','TIMESTAMP')]
Q_SCHEMA = [('query_id','VARCHAR'),('user_id','BIGINT'),('anchor','TIMESTAMP'),
    ('eligibility_events','BIGINT'),('history_events_7d','BIGINT'),('history_distinct_items_7d','BIGINT'),
    ('history_active_days_7d','BIGINT'),('last_history_time','TIMESTAMP'),
    ('history_coverage_7d','DOUBLE'),('label_is_mature','BOOLEAN')]
Y_SCHEMA = [('query_id','VARCHAR'),('product_id','BIGINT'),('first_purchase_time','TIMESTAMP'),
    ('raw_purchase_rows','BIGINT'),('same_second_purchase','BOOLEAN'),
    ('catalog_seen_before','BOOLEAN'),('pair_seen_before','BOOLEAN')]
METADATA = [('candidate_category_id','BIGINT'),('candidate_category_ambiguous','BOOLEAN'),
    ('candidate_category_missing','BOOLEAN'),('item_has_observed_history','BOOLEAN'),
    ('user_has_observed_history','BOOLEAN'),('item_observed_age_seconds','DOUBLE'),
    ('user_observed_age_seconds','DOUBLE')]
FLAGS = [n+'_missing' for n,g,e,op,w,c in CORE if e=='ratio' or op=='recency_seconds' or 'category' in g]
F_SCHEMA = C_SCHEMA + [('user_id','BIGINT'),('anchor','TIMESTAMP')] + METADATA + [
    (n,'DOUBLE' if op=='recency_seconds' else 'BIGINT') for n,g,e,op,w,c in CORE if e!='ratio'] + [
    ('source_coverage_24h','DOUBLE'),('source_coverage_168h','DOUBLE')] + [
    (n,'DOUBLE') for n,g,e,op,w,c in CORE if e=='ratio'] + [(n,'BOOLEAN') for n in FLAGS]


class VerificationError(ValueError):
    def __init__(self, gate, evidence):
        super().__init__(gate)
        self.evidence = evidence


def _need(condition, gate):
    if not condition:
        raise ValueError(gate)


def _time(value):
    # Only manifest UTC second strings; use naive UTC for DuckDB TIMESTAMP.
    from scripts.protocol_manifest import _utc
    return _utc(value).replace(tzinfo=None)


def _rss():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == 'darwin' else value * 1024


class _Budget:
    def __init__(self, seconds, rss_bytes):
        _need(type(seconds) in (int,float) and math.isfinite(seconds) and 0 < seconds <= 300, 'budget.wall')
        _need(type(rss_bytes) is int and 0 < rss_bytes <= 512*2**20, 'budget.rss')
        self.start, self.cpu = time.monotonic(), time.process_time()
        self.seconds, self.rss_bytes = seconds, rss_bytes
        self.expired = threading.Event()

    def check(self):
        if self.expired.is_set() or time.monotonic()-self.start >= self.seconds or time.process_time()-self.cpu >= self.seconds:
            raise TimeoutError('budget.deadline')
        if _rss() > self.rss_bytes:
            raise MemoryError('budget.rss')

    def summary(self):
        return dict(wall_seconds=time.monotonic()-self.start,cpu_seconds=time.process_time()-self.cpu,
                    process_peak_rss_bytes=_rss(),wall_cap_seconds=self.seconds,rss_cap_bytes=self.rss_bytes)


class _Inputs:
    def __init__(self, root, expectations, guard):
        self.root, self.guard = root, guard
        self.required, self.verified = set(), {}
        self.approval_path = self.path(expectations)
        self.approval_sha = self.digest(self.approval_path)
        self.approval = _read_json(self.approval_path)
        _keys(self.approval, {'version','approved','scope','collection_id','complete_attempt_report','fingerprints'}, 'expectations')
        _need(type(self.approval['version']) is int and self.approval['version']==1 and
              self.approval['approved'] is True and self.approval['scope']=='reviewed_development_collection', 'expectations.scope')
        self.pins = self.approval['fingerprints']
        _hashes(self.pins,'expectations fingerprints')

    def path(self, name):
        value = Path(name)
        if value.is_absolute():
            value = value.resolve().relative_to(self.root)
        name = value.as_posix()
        _relative_path(name)
        resolved = (self.root/name).resolve()
        _need(resolved.is_relative_to(self.root), 'paths.escape')
        return resolved

    def digest(self, path):
        h = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(1024*1024):
                self.guard(); h.update(block)
        self.guard()
        return h.hexdigest()

    def pin(self, name, expected=None):
        self.required.add(name)
        _need(name in self.pins and (expected is None or self.pins[name]==expected),'pins.missing_or_mismatch')
        path = self.path(name)
        if name not in self.verified:
            _need(self.digest(path)==self.pins[name], 'pins.changed')
            self.verified[name] = self.pins[name]
        return path

    def read(self, name):
        return _read_json(self.pin(name))

    def finish(self):
        _need(self.required==self.pins.keys(), 'pins.exact_scope')
        # Rehash at completion: verification is not a filesystem snapshot.
        for name,digest in self.verified.items():
            _need(self.digest(self.path(name))==digest,'pins.changed_during_verification')
        _need(self.digest(self.approval_path)==self.approval_sha,'expectations.changed')


def _lineage(inputs):
    a = inputs.approval
    names = [n for n in inputs.pins if n.endswith('/'+a['collection_id']+'/state.json')]
    _need(len(names)==1,'lineage.one_state')
    state_name = names[0]
    _need(inputs.path(state_name).is_relative_to(inputs.root/'artifacts'),'paths.artifacts')
    state,plan = inputs.read(state_name),inputs.read(state_name.removesuffix('state.json')+'plan.json')
    report = inputs.read(a['complete_attempt_report'])
    _need(all(x.get('collection_id')==a['collection_id'] for x in [state,plan,report]),'lineage.collection_id')
    _need(state.get('status')==report.get('status')=='complete_produced_unreviewed' and
          a['complete_attempt_report'] in state.get('attempts',[]),'lineage.complete_attempt')
    _keys(plan,{'collection_id','identity','execution_inputs'},'plan')
    identity,execution = plan['identity'],plan['execution_inputs']
    _keys(identity,{'version','status','phase','shard_protocols','registry_sha256','source_sha256','code_hashes'},'identity')
    _keys(execution,{'phase_path','source_path','fingerprints'},'execution')
    _need(type(identity['version']) is int and identity['version']==1 and identity['status']=='planned_not_executed','unsupported.identity')
    _need(hashlib.sha256(canonical_json(identity).encode()).hexdigest()==a['collection_id'],'lineage.identity_digest')
    phase = identity['phase']
    _keys(phase,{'version','name','role','base_protocol','feature_registry','range','label_available_before',
        'model_timing','final_holdout_start','shard_days','lock_required','budget'},'phase')
    _need(type(phase['version']) is int and phase['version']==1 and phase['role'] in {'train','selection'} and
          phase['lock_required'] is False,'unsupported.role')
    wanted = PRODUCER_CODE|{execution['phase_path'],execution['source_path'],phase['base_protocol'],phase['feature_registry'],'pyproject.toml'}
    _need(execution['fingerprints'].keys()==wanted,'lineage.execution_scope')
    for name,digest in execution['fingerprints'].items(): inputs.pin(name,digest)
    _need(identity['source_sha256']==execution['fingerprints'][execution['source_path']] and
          identity['registry_sha256']==execution['fingerprints'][phase['feature_registry']] and
          identity['code_hashes']=={n:execution['fingerprints'][n] for n in PRODUCER_CODE},'lineage.identity_binding')
    _need(inputs.read(execution['phase_path'])==phase,'lineage.phase_body')
    registry = inputs.read(phase['feature_registry'])
    _need(canonical_json(registry)==canonical_json(REGISTRY),'unsupported.registry_manual18')
    base = validate_protocol(inputs.read(phase['base_protocol']))
    _need(base['target']['include_anchor'] is True and base['target']['include_end'] is False and
          base['target']['horizon_hours']==24 and base['query']['eligibility_event_types']==['view','cart','purchase'] and
          base['candidates']['recent_event_types']==['view','cart','purchase'],'unsupported.clock_policy')
    _keys(phase['range'],{'start','end'},'phase range')
    _keys(phase['model_timing'],{'fit_data_cutoff','available_at'},'model timing')
    _keys(phase['budget'],{'max_queries','max_candidate_pairs','wall_seconds'},'phase budget')
    _need(isinstance(phase['name'],str) and bool(phase['name']),'phase.name')
    start,end = _time(phase['range']['start']),_time(phase['range']['end'])
    cutoff,final = _time(phase['label_available_before']),_time(phase['final_holdout_start'])
    fit,ready = [_time(phase['model_timing'][n]) for n in ['fit_data_cutoff','available_at']]
    _need(all(t.time()==datetime.min.time() for t in [start,end,cutoff,final]) and
          _time(base['source']['start'])<=start<end<=cutoff<=final<=_time(base['source']['end']),'phase.calendar')
    _need(fit<=ready and (cutoff==fit<ready if phase['role']=='train' else ready<=start),'phase.model_availability')
    _need(end+timedelta(seconds=base['target']['availability_delay_seconds'])<=cutoff,'phase.label_maturity')
    _need(type(phase['shard_days']) is int and 1<=phase['shard_days']<=3,'phase.shard_days')
    qcap=(end-start).days*base['query']['max_users_per_day']
    _need(type(phase['budget']['max_queries']) is int and phase['budget']['max_queries']==qcap and
          type(phase['budget']['max_candidate_pairs']) is int and phase['budget']['max_candidate_pairs']==qcap*base['candidates']['max_unique'] and
          type(phase['budget']['wall_seconds']) is int and 1<=phase['budget']['wall_seconds']<=3600,'phase.budget')
    shards = identity['shard_protocols']
    cursor = start
    for p in shards:
        validate_protocol(p)
        for key in ['version','status','timezone','source','query','target','candidates','history']:
            _need(p[key]==base[key],'phase.shard_policy')
        stop = min(end,cursor+timedelta(days=phase['shard_days']))
        _need(_time(p['pilot']['start'])==cursor and _time(p['pilot']['end'])==stop,'phase.exact_cover')
        shard_q=(stop-cursor).days*base['query']['max_users_per_day']
        _need(p['budget']==dict(max_anchors=shard_q,max_candidate_pairs=shard_q*base['candidates']['max_unique']),'phase.shard_budget')
        cursor = stop
    _need(cursor==end and len(shards)==len(state['shards']),'phase.exact_cover')
    refs=[]
    for index,(entry,p) in enumerate(zip(state['shards'],shards)):
        _need(type(entry['index']) is int and entry['index']==index and entry['protocol']==p,'phase.shard_order')
        _keys(entry,{'index','protocol','anchor','candidate','features','acceptance','producer_attempts'},'shard')
        _keys(entry['acceptance'],{'path','sha256'},'shard acceptance')
        approval = inputs.read(entry['acceptance']['path'])
        _keys(approval,{'version','approved','anchor_run_id','candidate_run_id','fingerprints'},'shard approval')
        inputs.pin(entry['acceptance']['path'],entry['acceptance']['sha256'])
        _need(approval.get('approved') is True and type(approval.get('version')) is int and approval['version']==1,'lineage.shard_approval')
        manifests={};reports={}
        for kind,labels in [('anchor',{'queries','labels','report'}),('candidate',{'candidates','query_coverage','report'}),('features',{'features','report'})]:
            seal=entry[kind];_keys(seal,{'directory','run_id','fingerprints'},'producer seal');directory=inputs.path(seal['directory'])
            _need(directory.is_relative_to(inputs.root/'artifacts'),'paths.artifacts')
            for name,digest in seal['fingerprints'].items(): inputs.pin(name,digest)
            mn=seal['directory']+'/run.json';rn=seal['directory']+'/report.json'
            m=validate_run_manifest(inputs.read(mn));r=inputs.read(rn)
            _need(m['run_id']==seal['run_id']==r.get('run_id') and r.get('status')=='complete','lineage.child_complete')
            _need(m['identity']['protocol']==p and not m['identity']['components'],'lineage.child_policy')
            _need(m['artifact_refs'].keys()==labels,'lineage.output_scope')
            output_paths={mn,rn}
            for label,name in m['artifact_refs'].items():
                _need(inputs.path(name).parent==directory and (label!='report' or name==rn),'paths.child_output')
                inputs.pin(name);output_paths.add(name)
            _need(seal['fingerprints'].keys()==output_paths,'lineage.seal_scope')
            code=m['identity']['code_hashes']; expected_code = (
                {'uv.lock','scripts/anchor_pilot.py','scripts/protocol_manifest.py','scripts/temporal_contract.py'} |
                ({'scripts/candidate_pilot.py'} if kind=='candidate' else set())) if kind!='features' else PRODUCER_CODE-{'scripts/development_collection.py'}
            _need(code=={n:identity['code_hashes'][n] for n in expected_code},'lineage.child_code')
            for group in [code,m['identity']['input_hashes']]:
                for name,digest in group.items():inputs.pin(name,digest)
            _need(m['identity']['input_hashes'].get(execution['source_path'])==identity['source_sha256'],'lineage.child_source')
            if kind=='anchor': _need(set(m['identity']['input_hashes'])=={execution['source_path']},'lineage.anchor_inputs')
            if kind=='features':
                # This project policy derives its exact scope from verified upstream
                # manifests/seals, never from the approval's self-declared keys.
                upstream={execution['source_path']:identity['source_sha256']}
                for upstream_kind in ['anchor','candidate']:
                    upstream_manifest=manifests[upstream_kind]
                    for group in ['code_hashes','input_hashes']:
                        upstream.update(upstream_manifest['identity'][group])
                    upstream.update({n:inputs.pins[n] for n in entry[upstream_kind]['fingerprints']})
                _need(len(upstream)==14 and approval['fingerprints']==upstream,'lineage.shard_approval_scope')
                _need(m['identity']['input_hashes'].get(phase['feature_registry'])==identity['registry_sha256'] and
                    canonical_json(r.get('registry'))==canonical_json(REGISTRY) and r.get('selection',{}).get('max_queries','absent') is None and
                    r.get('output_sha256')==inputs.pins[m['artifact_refs']['features']],'lineage.feature_registry')
                _need(canonical_json(r['selection'])==canonical_json(dict(version=1,source_candidate_run=entry['candidate']['run_id'],
                    query_order='sha256_query_id_then_query_id',max_queries=None,label_policy='not_read_for_selection_or_feature_materialization')),'lineage.feature_selection')
                selections=[n for n in m['identity']['input_hashes'] if n.endswith('.json') and inputs.read(n)==r['selection']]
                _need(len(selections)==1,'lineage.selection_definition')
                expected={**upstream,entry['acceptance']['path']:entry['acceptance']['sha256'],
                          phase['feature_registry']:identity['registry_sha256'],selections[0]:inputs.pins[selections[0]]}
                _need(m['identity']['input_hashes']==expected,'lineage.feature_inputs')
            manifests[kind]=m;reports[kind]=r
        am,cm,fm=[manifests[k] for k in ['anchor','candidate','features']]
        _need(reports['candidate'].get('anchor_run_id')==am['run_id'],'lineage.candidate_report_ids')
        _need(reports['features'].get('anchor_run_id')==am['run_id'] and
              reports['features'].get('candidate_run_id')==cm['run_id'],'lineage.feature_report_ids')
        anchor_inputs={execution['source_path']:identity['source_sha256']}
        anchor_inputs.update({n:inputs.pins[n] for n in entry['anchor']['fingerprints']})
        _need(cm['identity']['input_hashes']==anchor_inputs,'lineage.candidate_inputs')
        _need(approval.get('anchor_run_id')==am['run_id'] and approval.get('candidate_run_id')==cm['run_id'],'lineage.shard_ids')
        for name,digest in approval['fingerprints'].items():inputs.pin(name,digest)
        refs.append(dict(protocol=p,queries=am['artifact_refs']['queries'],labels=am['artifact_refs']['labels'],
                         candidates=cm['artifact_refs']['candidates'],features=fm['artifact_refs']['features']))
    _need(report.get('collection',{}).get('artifact_refs')=={k:[r[k] for r in refs] for k in ['queries','labels','candidates','features']},'lineage.aggregate_refs')
    _need(inputs.required==inputs.pins.keys(),'pins.exact_scope')
    return plan,refs,report


def _schema(con,table,expected):
    actual=[(r[0],r[1]) for r in con.execute('DESCRIBE '+table).fetchall()]
    _need(actual==expected,'schema.'+table)


def _equivalent(con,a,b,gate):
    for left,right in [(a,b),(b,a)]:
        _need(con.execute(f'SELECT count(*) FROM ({left} EXCEPT ALL {right})').fetchone()[0]==0,gate)


def _qyc(con,p,cutoff,check):
    S,E=[_time(p['source'][k]) for k in ['start','end']]
    day,end=[_time(p['pilot'][k]) for k in ['start','end']]
    spec,cs=p['query'],p['candidates']
    # Each query belongs to exactly one enumerated source day, including empty days.
    _need(con.execute('SELECT count(*) FROM q WHERE anchor<? OR anchor>=? OR anchor<>date_trunc(\'day\',anchor)',[day,end]).fetchone()[0]==0,'Q.anchor_range')
    while day<end:
        check();b=max(S,day-timedelta(days=7));be=day-timedelta(hours=spec['eligibility_hours'])
        serial=day.strftime('%Y-%m-%dT%H:%M:%SZ');seed=spec['sample_seed']
        coverage=max(0,(min(day,E)-b).total_seconds())/(7*86400)
        mature=day+timedelta(hours=24,seconds=p['target']['availability_delay_seconds'])<=min(E,cutoff)
        _need(mature,'Q.maturity')
        con.execute('''CREATE OR REPLACE TEMP TABLE oq AS SELECT sha256(?||user_id::VARCHAR) query_id,user_id,?::TIMESTAMP anchor,
          count(*) FILTER(WHERE event_time>=? AND event_type IN ('view','cart','purchase')) eligibility_events,
          count(*) FILTER(WHERE event_time>=?) history_events_7d,count(DISTINCT product_id) FILTER(WHERE event_time>=?) history_distinct_items_7d,
          count(DISTINCT event_time::DATE) FILTER(WHERE event_time>=?) history_active_days_7d,
          max(event_time) FILTER(WHERE event_time>=?) last_history_time,?::DOUBLE history_coverage_7d,true label_is_mature
          FROM source.events WHERE user_id IS NOT NULL AND event_time>=? AND event_time<? GROUP BY user_id HAVING eligibility_events>0
          ORDER BY sha256(?||user_id::VARCHAR),user_id LIMIT ?''',
          [f'query|{seed}|{serial}|',day,be,b,b,b,b,coverage,min(b,be),day,f'sample|{seed}|{serial}|',spec['max_users_per_day']])
        _equivalent(con,f"SELECT * FROM q WHERE anchor=TIMESTAMP '{day}'",'SELECT * FROM oq','Q.source_relation')
        con.execute('''CREATE OR REPLACE TEMP TABLE oy0 AS SELECT q.query_id,e.product_id,min(e.event_time) first_purchase_time,
          count(*) raw_purchase_rows,bool_or(e.event_time=q.anchor) same_second_purchase FROM oq q JOIN source.events e ON e.user_id=q.user_id
          WHERE e.event_type='purchase' AND e.product_id IS NOT NULL AND e.event_time>=? AND e.event_time<? GROUP BY q.query_id,e.product_id''',[day,day+timedelta(days=1)])
        con.execute('''CREATE OR REPLACE TEMP TABLE oy AS SELECT z.*,
          EXISTS(SELECT 1 FROM source.events e WHERE e.product_id=z.product_id AND e.event_time>=? AND e.event_time<?) catalog_seen_before,
          EXISTS(SELECT 1 FROM source.events e WHERE e.user_id=q.user_id AND e.product_id=z.product_id AND e.event_time>=? AND e.event_time<?) pair_seen_before
          FROM oy0 z JOIN oq q USING(query_id)''',[S,day,S,day])
        _equivalent(con,'SELECT y.* FROM y JOIN oq USING(query_id)','SELECT * FROM oy','Y.source_relation')
        con.execute('''CREATE OR REPLACE TEMP TABLE op AS SELECT product_id,count(DISTINCT user_id)::BIGINT popularity_distinct_users
          FROM source.events WHERE event_time>=? AND event_time<? AND event_type='purchase' AND product_id IS NOT NULL AND user_id IS NOT NULL GROUP BY product_id''',
          [day-timedelta(hours=cs['popular_window_hours']),day])
        con.execute('''CREATE OR REPLACE TEMP TABLE optop AS SELECT *,row_number() OVER(ORDER BY popularity_distinct_users DESC,product_id) popular_source_rank
          FROM op ORDER BY popularity_distinct_users DESC,product_id LIMIT ?''',[cs['popular_limit']])
        con.execute('''CREATE OR REPLACE TEMP TABLE ortop AS SELECT q.query_id,e.product_id,max(e.event_time) last_user_event_time,
          row_number() OVER(PARTITION BY q.query_id ORDER BY max(e.event_time) DESC,e.product_id) recent_source_rank
          FROM source.events e JOIN oq q ON e.user_id=q.user_id WHERE e.event_time>=? AND e.event_time<? AND e.product_id IS NOT NULL
          AND e.event_type IN ('view','cart','purchase') GROUP BY q.query_id,e.product_id QUALIFY recent_source_rank<=?''',
          [day-timedelta(hours=cs['recent_window_hours']),day,cs['recent_limit']])
        con.execute('''CREATE OR REPLACE TEMP TABLE oc AS WITH keys AS (
          SELECT q.query_id,p.product_id FROM oq q CROSS JOIN optop p UNION SELECT query_id,product_id FROM ortop)
          SELECT k.query_id,k.product_id,p.product_id IS NOT NULL from_popular,r.product_id IS NOT NULL from_recent,
          coalesce(g.popularity_distinct_users,0)::BIGINT popularity_distinct_users,p.popular_source_rank,r.recent_source_rank,r.last_user_event_time
          FROM keys k LEFT JOIN optop p USING(product_id) LEFT JOIN ortop r USING(query_id,product_id) LEFT JOIN op g USING(product_id)''')
        _equivalent(con,'SELECT c.* FROM c JOIN oq USING(query_id)','SELECT * FROM oc','C.source_relation')
        _need(con.execute('SELECT count(*) FROM (SELECT query_id,count(*) n FROM oc GROUP BY query_id HAVING n>?)',[cs['max_unique']]).fetchone()[0]==0,'C.query_cap')
        check();day+=timedelta(days=1)


def _formula(con,row,S,E,check):
    u,i,t=row['user_id'],row['product_id'],row['anchor'];b=t-timedelta(days=7)
    ue=con.execute('SELECT product_id,event_time,event_type,category_id FROM source.events WHERE user_id=? AND event_time>=? AND event_time<?',[u,S,t]).fetchall()
    check()
    ie=con.execute('SELECT user_id,event_time,event_type,category_id FROM source.events WHERE product_id=? AND event_time>=? AND event_time<?',[i,S,t]).fetchall()
    check()
    latest=max((e[1] for e in ie),default=None)
    cats={e[3] for e in ie if e[1]==latest};category=next(iter(cats)) if len(cats)==1 and None not in cats else None
    rec=lambda es:(t-max(e[1] for e in es)).total_seconds() if es else None
    U=lambda kind:[e for e in ue if e[2]==kind and e[1]>=b]
    P=lambda kind:[e for e in U(kind) if e[0]==i]
    values={}
    for kind in ['view','cart','purchase']:
        values['user_'+kind+'_7d']=len(U(kind));values['pair_'+kind+'_7d']=len(P(kind))
    values['user_distinct_viewed_items_7d']=len({e[0] for e in U('view') if e[0] is not None})
    for kind in ['view','purchase']:
        values['pair_'+kind+'_recency_seconds']=rec([e for e in ue if e[0]==i and e[2]==kind])
        values['item_'+kind+'_24h']=sum(e[2]==kind and e[1]>=t-timedelta(days=1) for e in ie)
    values['item_distinct_viewers_7d']=len({e[0] for e in ie if e[2]=='view' and e[1]>=b and e[0] is not None})
    values['user_category_view_7d']=sum(e[2]=='view' and e[3]==category and e[1]>=b for e in ue) if category is not None else None
    values['user_category_view_recency_seconds']=rec([e for e in ue if e[2]=='view' and e[3]==category]) if category is not None else None
    values['item_category_view_7d']=sum(e[2]=='view' and e[3]==category and e[1]>=b for e in ie) if category is not None else None
    values['category_view_7d']=con.execute("SELECT count(*) FROM source.events WHERE category_id=? AND event_type='view' AND event_time>=? AND event_time<?",[category,max(S,b),t]).fetchone()[0] if category is not None else None
    values['user_category_view_share_7d']=values['user_category_view_7d']/values['user_view_7d'] if category is not None and values['user_view_7d'] else None
    values['item_category_view_share_7d']=values['item_category_view_7d']/values['category_view_7d'] if values['category_view_7d'] else None
    expected={**values,'candidate_category_id':category,'candidate_category_missing':category is None,
        'candidate_category_ambiguous':len(cats)>1,'item_has_observed_history':bool(ie),'user_has_observed_history':bool(ue),
        'item_observed_age_seconds':(t-min(e[1] for e in ie)).total_seconds() if ie else None,
        'user_observed_age_seconds':(t-min(e[1] for e in ue)).total_seconds() if ue else None}
    for hours in [24,168]:
        expected['source_coverage_'+str(hours)+'h']=max(0,(min(t,E)-max(S,t-timedelta(hours=hours))).total_seconds())/(hours*3600)
    expected.update({n:values[n.removesuffix('_missing')] is None for n in FLAGS})
    for name,value in expected.items():
        actual=row[name]
        if value is None: ok=actual is None
        elif type(value) in (bool,int):ok=type(actual) is type(value) and actual==value
        else:ok=type(actual) in (int,float) and math.isfinite(actual) and math.isclose(actual,value,rel_tol=1e-12,abs_tol=1e-12)
        _need(ok,'F.formula.'+name)
    check()


def _features(con,p,check):
    fields=','.join(n for n,_ in C_SCHEMA)
    _equivalent(con,f'SELECT {fields} FROM f',f'SELECT {fields} FROM c','F.exact_C_rowset')
    _need(con.execute('''SELECT count(*) FROM f LEFT JOIN q USING(query_id) WHERE q.query_id IS NULL OR
       f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor''').fetchone()[0]==0,'F.query_keys')
    for n,g,e,op,w,c in CORE:
        condition=f'"{n}"<0' if op!='recency_seconds' else f'"{n}"<=0'
        if e=='ratio':condition+=f' OR "{n}">1'
        if op=='recency_seconds' or e=='ratio':condition+=f' OR ("{n}" IS NOT NULL AND NOT isfinite("{n}"))'
        if n+'_missing' in FLAGS:condition+=f' OR "{n}_missing" IS DISTINCT FROM ("{n}" IS NULL)'
        elif 'category' not in g:condition+=f' OR "{n}" IS NULL'
        _need(con.execute('SELECT count(*) FROM f WHERE '+condition).fetchone()[0]==0,'F.range_null.'+n)
    strata={}
    # Each stratum is reported even when absent; no empty-stratum "pass".
    conditions={'pair_view_support':'pair_view_7d>0','category_missing':'candidate_category_missing',
                'category_ambiguous':'candidate_category_ambiguous','positive_pair_support':'pair_purchase_7d>0',
                'old_recency_support':'pair_view_recency_seconds>604800 OR pair_purchase_recency_seconds>604800'}
    samples={}
    for name,predicate in [('bottom_hash','true'),*conditions.items()]:
        limit=4 if name=='bottom_hash' else 1
        selected=con.execute(f'''SELECT * FROM f WHERE {predicate} QUALIFY row_number() OVER(PARTITION BY anchor
          ORDER BY sha256(query_id||'|'||product_id::VARCHAR),query_id,product_id)<=?''',[limit]).fetchall()
        columns=[z[0] for z in con.description]
        strata[name]={'sampled_pairs':len(selected),'available_pairs':con.execute('SELECT count(*) FROM f WHERE '+predicate).fetchone()[0]}
        for values in selected:
            row=dict(zip(columns,values));samples[row['query_id'],row['product_id']]=row
    S,E=[_time(p['source'][k]) for k in ['start','end']]
    for row in samples.values():check();_formula(con,row,S,E,check)
    return len(samples),strata


def verify(project_root, expectations_path, *, seconds=300, rss_bytes=512*2**20):
    """Verify existing externally pinned collection; never produce acceptance.

    Failure raises VerificationError carrying aggregate partial evidence. No
    users/items/query IDs or source rows appear in evidence, including errors.
    """
    started=time.monotonic();cpu=time.process_time();con=timer=None;budget=None;failure=None
    evidence=dict(version=1,policy=POLICY,status='failed',completed=[],fits=0,
        scope=dict(QYC='exhaustive_source_relations',F_rowset='exhaustive_exact_C',F_values='deterministic_sample_only'))
    try:
        budget=_Budget(seconds,rss_bytes);budget.check()
        root=Path(project_root).resolve(strict=True)
        inputs=_Inputs(root,expectations_path,budget.check)
        plan,refs,report=_lineage(inputs);evidence['completed'].append('lineage')
        evidence['collection_id']=plan['collection_id'];evidence['expectations_sha256']=inputs.approval_sha
        evidence['verifier_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        import tomllib
        from importlib.metadata import version
        lock=tomllib.loads(inputs.pin('uv.lock').read_text())
        versions={item['version'] for item in lock['package'] if item['name']=='duckdb'}
        _need(versions=={duckdb.__version__} and version('duckdb')==duckdb.__version__,'runtime.duckdb_version')
        for module_name,code_name in [('scripts.protocol_manifest','scripts/protocol_manifest.py'),('scripts.temporal_contract','scripts/temporal_contract.py')]:
            validator_file=Path(sys.modules[module_name].__file__)
            _need(inputs.digest(validator_file)==plan['identity']['code_hashes'][code_name],'runtime.manifest_validator_pin')
        evidence['duckdb_version']=duckdb.__version__
        evidence['python_version']=sys.version.split()[0];evidence['platform']=sys.platform
        con=duckdb.connect(':memory:');con.execute('SET threads=2');con.execute("SET memory_limit='128MB'")
        con.execute("SET max_temp_directory_size='0B'")
        def interrupt():
            budget.expired.set()
            if con is not None:
                try:con.interrupt()
                except Exception:pass  # Cleanup can race a fired SQL timer.
        timer=threading.Timer(max(.001,seconds-(time.monotonic()-budget.start)),interrupt);timer.daemon=True;timer.start()
        source=inputs.pin(plan['execution_inputs']['source_path'])
        con.execute("ATTACH '"+str(source).replace("'","''")+"' AS source (READ_ONLY)")
        columns={r[0]:r[1] for r in con.execute('DESCRIBE source.events').fetchall()}
        _need(all(columns.get(n)==t for n,t in [('event_time','TIMESTAMP'),('event_type','VARCHAR'),
            ('product_id','BIGINT'),('user_id','BIGINT'),('category_id','BIGINT')]),'schema.source_events')
        totals={k:0 for k in ['queries','labels','candidates','features']};sample_count=0;all_strata=[]
        population=dict(mature_empty_Y_queries=0,empty_C_queries=0,fullY_outside_C=0)
        for index,r in enumerate(refs):
            budget.check()
            for key,table,schema in [('queries','q',Q_SCHEMA),('labels','y',Y_SCHEMA),('candidates','c',C_SCHEMA),('features','f',F_SCHEMA)]:
                con.read_parquet(str(inputs.pin(r[key]))).create_view(table,replace=True)
                _schema(con,table,schema)
                count=con.execute('SELECT count(*) FROM '+table).fetchone()[0];totals[key]+=count
            _need(con.execute('SELECT count(*)-count(DISTINCT query_id) FROM q').fetchone()[0]==0,'Q.unique')
            for table in ['y','c','f']:
                _need(con.execute('SELECT count(*)-count(DISTINCT(query_id,product_id)) FROM '+table).fetchone()[0]==0,table+'.unique')
                _need(con.execute('SELECT count(*) FROM '+table+' LEFT JOIN q USING(query_id) WHERE q.query_id IS NULL').fetchone()[0]==0,table+'.orphan')
            _qyc(con,r['protocol'],_time(plan['identity']['phase']['label_available_before']),budget.check)
            population['mature_empty_Y_queries']+=con.execute('SELECT count(*) FROM q WHERE NOT EXISTS(SELECT 1 FROM y WHERE y.query_id=q.query_id)').fetchone()[0]
            population['empty_C_queries']+=con.execute('SELECT count(*) FROM q WHERE NOT EXISTS(SELECT 1 FROM c WHERE c.query_id=q.query_id)').fetchone()[0]
            population['fullY_outside_C']+=con.execute('SELECT count(*) FROM y LEFT JOIN c USING(query_id,product_id) WHERE c.product_id IS NULL').fetchone()[0]
            evidence['completed'].append('shard_'+str(index)+'_QYC')
            samples,strata=_features(con,r['protocol'],budget.check);sample_count+=samples
            all_strata.append(dict(shard=index,strata=strata))
            evidence['completed'].append('shard_'+str(index)+'_F')
        _need(totals==report['collection'].get('counts'),'collection.report_counts')
        _need(report['collection'].get('feature_columns')==[n for n,t in F_SCHEMA],'collection.report_schema')
        phase=plan['identity']['phase']
        _need(totals['queries']<=phase['budget']['max_queries'] and totals['candidates']<=phase['budget']['max_candidate_pairs'],'collection.phase_cap')
        inputs.finish();budget.check()
        evidence.update(counts=totals,population=population,sample_pairs=sample_count,formula_checks=sample_count*18,
            sampled_metadata_support_checks=sample_count*(len(F_SCHEMA)-len(C_SCHEMA)-2-18),sampling=all_strata,
            numeric_tolerance=dict(relative=1e-12,absolute=1e-12),acceptance_written=False)
    except Exception as error:
        failure=(_public_gate(error,budget),error)
    finally:
        def record(gate,error):
            nonlocal failure
            if failure is None:failure=(gate,error)
            else:evidence.setdefault('finalization_failures',[]).append(gate)
        if timer is not None:
            try:timer.cancel()
            except Exception as error:record('cleanup.timer',error)
        if con is not None:
            try:con.close()
            except Exception as error:record('cleanup.close',error)
            finally:con=None
        # Cleanup, counters and the final budget check precede success promotion.
        if budget is not None:
            try:budget.check()
            except Exception as error:record(_public_gate(error,budget),error)
        try:
            evidence['resources']=budget.summary() if budget is not None else _fallback_resources(started,cpu)
        except Exception as error:
            record('resources.summary',error)
            evidence['resources']=_fallback_resources(started,cpu)
        if budget is not None:
            try:budget.check()
            except Exception as error:record(_public_gate(error,budget),error)
    if failure is not None:
        evidence['status']='failed';evidence['failure_gate']=failure[0]
        raise VerificationError(failure[0],evidence) from failure[1]
    evidence['status']='verified'
    return evidence


def _public_gate(error,budget):
    gate='budget.deadline' if budget is not None and budget.expired.is_set() else str(error) if isinstance(error,(ValueError,TimeoutError,MemoryError)) and not isinstance(error,duckdb.Error) else 'verification.input_or_engine_error'
    if not gate or any(ch in gate for ch in [' ','/','\\','\n',':']):return 'verification.invalid_input'
    return gate


def _fallback_resources(started,cpu):
    values={'measurement_status':'partial_unavailable'}
    for name,operation in [('wall_seconds',lambda:time.monotonic()-started),
                           ('cpu_seconds',lambda:time.process_time()-cpu),('process_peak_rss_bytes',_rss)]:
        try:
            value=operation();values[name]=value if math.isfinite(value) else None
        except Exception:values[name]=None
    return values


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',required=True)
    parser.add_argument('--expectations',required=True,help='External reviewed collection acceptance, relative to project root')
    parser.add_argument('--evidence-out',help='New project-relative evidence file; never overwritten')
    parser.add_argument('--seconds',type=float,default=300)
    args=parser.parse_args(argv)
    code=0
    try:result=verify(args.project_root,args.expectations,seconds=args.seconds)
    except VerificationError as error:result=error.evidence;code=1
    if args.evidence_out:
        try:
            _relative_path(args.evidence_out)
            root=Path(args.project_root).resolve(strict=True);path=(root/args.evidence_out).resolve()
            _need(path.is_relative_to(root),'paths.escape')
            with path.open('x') as stream:stream.write(canonical_json(result)+'\n')
        except Exception:
            result={**result,'status':'failed','failure_gate':'evidence.exclusive_write'};code=1
    print(canonical_json(result))
    return code


if __name__=='__main__':
    raise SystemExit(main())
