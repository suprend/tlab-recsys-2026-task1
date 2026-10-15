"""Selected-union source features; no model, label relation or fit permission.

Draft: a source-only producer. Independent formula acceptance is distinct from
physical inspection; final019 model settings are bound by a later fit runner.
"""
import time
ENTRY_MONOTONIC=time.monotonic()
import os
import resource
import math
import uuid

from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re

import duckdb

from scripts import feature_programs as programs
from scripts import metadata_price_collection as mechanics
from scripts import manual_features as compiler
from scripts import train_baselines as base
from scripts.protocol_manifest import canonical_json,sha256_file,_read_json,_unique_object,_reject_constant

ROOT=Path(__file__).resolve().parents[1]
ROLE='selected_feature_program_source_collection'
LIMITS=dict(producer_actual_cpu_seconds=900,producer_wall_seconds=1200,rss_bytes=8*2**30,
            threads=2,max_queries_per_day=2000,max_pairs_per_day=440000,
            shared_study_actual_cpu_seconds=7200,independent_source_oracle_cpu_allocation=900)
CODE=(*mechanics.CODE,'scripts/feature_programs.py','scripts/feature_program_collection.py')


def _snapshot(path):
    raw=Path(path).read_bytes()
    value=json.loads(raw,object_pairs_hook=_unique_object,parse_constant=_reject_constant)
    return value,hashlib.sha256(raw).hexdigest()


def _quote(name):
    if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',name):
        raise ValueError('Unsafe declared column')
    return '"'+name+'"'


def selected_union(pool,allocation):
    """Generate selected11cores+mask once, never calculate the other4bundles."""
    if allocation!=programs.allocate_slots(pool):raise ValueError('Noncanonical program allocation')
    bundles={b['bundle_id']:b for b in pool['identity']['bundles']}
    union=deepcopy(pool['identity']['base_registry']);union['name']='selected_union12'
    added={};delta={};arms={}
    for slot in allocation['identity']['slots']:
        if slot['status']!='planned_unexecuted':
            arms[slot['slot']]=dict(status=slot['status'],columns=[],bundle_id=slot['bundle_id'])
            continue
        bundle=bundles[slot['bundle_id']]
        for feature in bundle['programs']:
            name=feature['name']
            if name in added and added[name]!=feature:raise ValueError('Shared program name has different semantics')
            added[name]=deepcopy(feature)
        for field in bundle['physical_delta']:
            if field['name'] in delta and delta[field['name']]!=field['dtype']:
                raise ValueError('Shared output type differs')
            delta[field['name']]=field['dtype']
        arms[slot['slot']]=dict(status='planned_unexecuted',bundle_id=bundle['bundle_id'],
            columns=[f['name'] for f in bundle['physical_delta']],model_feature_order=bundle['model_feature_order'])
    if len(added)!=11 or len(delta)!=12 or [s['bundle_id'] for s in allocation['identity']['slots']]!=['L02','L06','L01','L05']:
        raise ValueError('The exact reviewed current selected union is11cores+1mask, no replacement')
    union['features'].extend(added.values());union=compiler.validate_registry(union)
    return dict(registry=union,physical_delta=[dict(name=n,dtype=t) for n,t in delta.items()],arms=arms)


def prepare_plan(train_acceptance,selection_acceptance,contract_path,base_registry_path,*,check=lambda:None):
    """Readonly lineage/definitions; execution/claims/source formulas separate."""
    contract,contract_sha=_snapshot(contract_path);registry,registry_sha=_snapshot(base_registry_path)
    pool=programs.generate_pool(contract,registry);allocation=programs.allocate_slots(pool)
    union=selected_union(pool,allocation)
    train=mechanics.verify_collection_strict(train_acceptance,check=check)
    selection=mechanics.verify_collection_strict(selection_acceptance,check=check)
    base.validate_training_phases(train,selection,dict(wall_seconds=LIMITS['producer_wall_seconds']))
    if train['feature_columns']!=selection['feature_columns']:
        raise ValueError('Accepted base schemas differ')
    model_schema=[f['name'] for f in pool['identity']['base_model_schema']]
    if base.numeric_feature_names(train['feature_columns'])!=model_schema:
        raise ValueError('Declared B41 order differs from actual accepted base')
    for collection in [train,selection]:
        if collection['plan']['identity']['registry_sha256']!=registry_sha:
            raise ValueError('Program base registry is not the exact accepted manual18')
        for protocol in collection['plan']['identity']['shard_protocols']:
            if (protocol['timezone']!='UTC' or protocol['history']['duplicates']!='raw'
                    or protocol['history']['ties']!='global_read_before_update'
                    or protocol['history']['metadata']!='last_strict_past_ambiguity_preserved'
                    or protocol['candidates']['popular_window_hours']!=168
                    or protocol['candidates']['popular_unit']!='distinct_users'
                    or protocol['candidates']['popular_event_type']!='purchase'):
                raise ValueError('Declared generator context differs from actual source/protocol/retrieval')
    pins=mechanics.merge_pins(train['pins'],selection['pins'],
        {mechanics.relative(contract_path):contract_sha,mechanics.relative(base_registry_path):registry_sha})
    for name in CODE:
        check();pins=mechanics.merge_pins(pins,{name:sha256_file(mechanics.local(name))})
    if sha256_file(contract_path)!=contract_sha or sha256_file(base_registry_path)!=registry_sha:
        raise ValueError('Definition snapshot changed during plan preparation')
    identity=dict(version=1,role=ROLE,limits=deepcopy(LIMITS),fingerprints=pins,
        acceptance_refs=dict(train=mechanics.relative(train_acceptance),selection=mechanics.relative(selection_acceptance),
                             contract=mechanics.relative(contract_path),base_registry=mechanics.relative(base_registry_path)),
        collections={role:c['plan']['collection_id'] for role,c in [('train',train),('selection',selection)]},
        pool=pool,allocation=allocation,selected_union=union,base_feature_columns=train['feature_columns'],
        purpose='source_values_only_no_model_or_training_population_choice',
        partition='all_accepted_Q_C_by_UTC_day_no_new_sampling',
        label_policy='no_Y_relation_or_targets_parsed_Y_file_hashes_mechanical_only',
        later_fit_requires=['reviewed009_base41_decision203','reviewed019_model_control_and_score_proof',
            '019_population_weights_trained_iterations_scoring_prefix','exact_pool_allocation_three_columns_each_arm',
            'retrospective_and_physical_decision_clocks','actual_shared7200_remaining_budget_and_global_four_fit_claim'])
    return dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity),dict(train=train,selection=selection)


def _generated_schema(registry):
    """Mechanical compiler emission description, not expected feature values."""
    grains={}
    for feature in registry['features']:
        if feature['operator']!='ratio':grains.setdefault(feature['grain'],[]).append(feature)
    result=[]
    for fs in grains.values():
        result.extend((f['name'],'DOUBLE' if f['operator']=='recency_seconds' else 'BIGINT') for f in fs)
    windows=sorted({f['window'] for f in registry['features'] if f['operator']!='ratio' and type(f['window']) is int})
    result.extend(('source_coverage_'+str(w)+'h','DOUBLE') for w in windows)
    result.extend((f['name'],'DOUBLE') for f in registry['features'] if f['operator']=='ratio')
    result.extend((f['name']+'_missing','BOOLEAN') for f in registry['features']
        if f['operator'] in {'ratio','recency_seconds'} or 'category_id' in compiler.GRAINS[f['grain']])
    return result


def _expected_schema(old_schema,base_registry,union_registry):
    old_generated={n for n,t in _generated_schema(base_registry)}
    prefix=[(n,t) for n,t in old_schema if n not in old_generated]
    expected=prefix+_generated_schema(union_registry)
    if len(old_schema)!=45 or len(expected)!=57 or len({n for n,t in expected})!=57:
        raise ValueError('Expected exact old45+new12 physical schema')
    return expected


def _differences(con,left,right,columns):
    fields=','.join(_quote(n) for n in columns)
    return con.execute('SELECT count(*) FROM ((SELECT '+fields+' FROM '+left+
        ' EXCEPT ALL SELECT '+fields+' FROM '+right+') UNION ALL (SELECT '+fields+' FROM '+right+
        ' EXCEPT ALL SELECT '+fields+' FROM '+left+'))').fetchone()[0]


def validate_day(con,*,old_table,output_table,queries_table,base_registry,union,source_start,check=lambda:None):
    """Every physical row/B preservation/ranges; NOT source-formula acceptance."""
    old_schema=[tuple(r[:2]) for r in con.execute('DESCRIBE '+old_table).fetchall()]
    actual_schema=[tuple(r[:2]) for r in con.execute('DESCRIBE '+output_table).fetchall()]
    expected=_expected_schema(old_schema,base_registry,union['registry'])
    if actual_schema!=expected:raise ValueError('Physical schema/order differs from old45+selected12')
    queries=con.execute('SELECT count(*),count(DISTINCT query_id),count(DISTINCT(user_id,anchor)) FROM '+queries_table).fetchone()
    old_count=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM '+old_table).fetchone()
    count=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM '+output_table).fetchone()
    if (queries[0]!=queries[1] or queries[0]!=queries[2] or queries[0]>2000
            or old_count[0]!=old_count[1] or count!=old_count or count[0]>440000):
        raise ValueError('Daily exact Q/C identity or resource cap differs')
    if _differences(con,old_table,output_table,[n for n,t in old_schema]):
        raise ValueError('Some baseline physical field or candidate row changed')
    if con.execute('SELECT count(*) FROM '+output_table+' f LEFT JOIN '+queries_table+
        ' q USING(query_id) WHERE q.query_id IS NULL OR f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor').fetchone()[0]:
        raise ValueError('Output Q/user/anchor differs from accepted domain')
    for feature in union['registry']['features'][len(base_registry['features']):]:
        check();name=_quote(feature['name'])
        if feature['operator']=='recency_seconds':
            mask=_quote(feature['name']+'_missing')
            bad=con.execute('SELECT count(*) FROM '+output_table+' WHERE '+mask+' IS DISTINCT FROM ('+name+' IS NULL) OR ('+
                name+' IS NOT NULL AND (NOT isfinite('+name+') OR '+name+'<=0 OR '+name+'>epoch(anchor)-epoch(?::TIMESTAMP)))',[source_start]).fetchone()[0]
        else:bad=con.execute('SELECT count(*) FROM '+output_table+' WHERE '+name+' IS NULL OR '+name+'<0').fetchone()[0]
        if bad:raise ValueError('New feature type/range/NULL boundary differs: '+feature['name'])
    check()
    return dict(queries=queries[0],pairs=count[0],new_physical_columns=12,baseline_all_fields_preserved=True,
                source_formula_acceptance=False,schema=[list(r) for r in actual_schema])


def _atomic(path,value):
    mechanics._atomic_json(path,value)


def _paths(collection,kind):
    return [str(mechanics.local(n)) for n in collection['refs'][kind]]


def _daily_config(collection,day):
    config=deepcopy(collection['plan']['identity']['shard_protocols'][0])
    config['pilot']=dict(start=day.strftime('%Y-%m-%dT%H:%M:%SZ'),end=(day+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    config['budget']['max_anchors']=LIMITS['max_queries_per_day']
    config['budget']['max_candidate_pairs']=LIMITS['max_pairs_per_day']
    return config


def _bind_temp_day(con,collection,day):
    # Queries include empty-C users; event aggregation domain is never inferred
    # from the output F. C remains the exact accepted keyed candidate relation.
    con.execute('CREATE OR REPLACE TEMP TABLE pilot_queries AS SELECT * FROM read_parquet(?) WHERE anchor=?',
                [_paths(collection,'queries'),day])
    con.execute('CREATE OR REPLACE TEMP TABLE pilot_candidates AS SELECT c.* FROM read_parquet(?) c SEMI JOIN pilot_queries q USING(query_id)',
                [_paths(collection,'candidates')])
    con.execute('CREATE OR REPLACE TEMP TABLE program_old_features AS SELECT f.* FROM read_parquet(?) f SEMI JOIN pilot_queries q USING(query_id)',
                [_paths(collection,'features')])


def inspect_physical(manifest,collections,*,check=lambda:None,deadline=None):
    """Full typed rows/B projection; a legal wrong new count can still pass.

    This intentionally does not approve source formulas or create acceptance.
    """
    identity=manifest['identity'];union=identity['selected_union']
    base_registry=identity['pool']['identity']['base_registry'];outputs=manifest['outputs']
    if set(outputs)!=set(collections):raise ValueError('Exact output phase cover differs')
    check();con=duckdb.connect(':memory:');timer=None
    try:
        if deadline is not None:timer=deadline.interrupt_timer(con)
        con.execute('SET threads=2');con.execute("SET memory_limit='2GB'");con.execute("SET max_temp_directory_size='0B'")
        for role,collection in collections.items():
            phase=collection['phase'];start=mechanics._utc(phase['range']['start']).replace(tzinfo=None)
            end=mechanics._utc(phase['range']['end']).replace(tzinfo=None)
            expected=[(start+timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ') for i in range((end-start).days)]
            days=outputs[role]
            if [d['anchor'] for d in days]!=expected:raise ValueError('Exact daily output partition differs')
            for d in days:
                check();day=mechanics._utc(d['anchor']).replace(tzinfo=None)
                if set(d)!=set(['anchor','artifacts','boundary']) or set(d['artifacts'])!={'queries','features'}:
                    raise ValueError('Exact artifact descriptor schema differs')
                _bind_temp_day(con,collection,day)
                for kind,table in [('queries','program_export_queries'),('features','program_export_features')]:
                    artifact=d['artifacts'][kind]
                    if set(artifact)!={'path','sha256','bytes','rows','schema'}:raise ValueError('Artifact field schema differs')
                    if type(artifact['bytes']) is not int or artifact['bytes']<0 or type(artifact['rows']) is not int or artifact['rows']<0:
                        raise ValueError('Artifact bytes/rows must be strict nonnegative integers')
                    expected_path='artifacts/feature-program-collection/'+manifest['run_id']+'/'+role+'/'+day.strftime('%Y-%m-%d')+'/'+kind+'.parquet'
                    if artifact['path']!=expected_path:raise ValueError('Output namespace differs')
                    path=mechanics.local(artifact['path'])
                    if sha256_file(path)!=artifact['sha256'] or path.stat().st_size!=artifact['bytes']:
                        raise ValueError('Actual Parquet bytes differ')
                    con.execute('CREATE OR REPLACE TEMP TABLE '+table+' AS SELECT * FROM read_parquet(?)',[str(path)])
                    schema=[list(r[:2]) for r in con.execute('DESCRIBE '+table).fetchall()]
                    rows=con.execute('SELECT count(*) FROM '+table).fetchone()[0]
                    if schema!=artifact['schema'] or rows!=artifact['rows']:raise ValueError('Actual Parquet schema/count differs')
                qs=[r[0] for r in con.execute('DESCRIBE pilot_queries').fetchall()]
                if _differences(con,'pilot_queries','program_export_queries',qs):raise ValueError('Every Q field must equal accepted Q')
                observed=validate_day(con,old_table='program_old_features',output_table='program_export_features',
                    queries_table='pilot_queries',base_registry=base_registry,union=union,
                    source_start=mechanics._utc(collection['plan']['identity']['shard_protocols'][0]['source']['start']).replace(tzinfo=None),check=check)
                if observed!=d['boundary']:raise ValueError('Actual boundary differs from declared summary')
            # Per-day equality alone would miss an accepted Q or C outside the
            # declared anchor partition. Prove whole phase cover independently.
            for name,kind in [('program_all_accepted_queries','queries'),('program_all_accepted_candidates','candidates')]:
                con.execute('CREATE OR REPLACE TEMP TABLE '+name+' AS SELECT * FROM read_parquet(?)',[_paths(collection,kind)])
            for name,kind in [('program_all_export_queries','queries'),('program_all_export_features','features')]:
                paths=[str(mechanics.local(d['artifacts'][kind]['path'])) for d in days]
                con.execute('CREATE OR REPLACE TEMP TABLE '+name+' AS SELECT * FROM read_parquet(?)',[paths])
            query_columns=[r[0] for r in con.execute('DESCRIBE program_all_accepted_queries').fetchall()]
            if _differences(con,'program_all_accepted_queries','program_all_export_queries',query_columns):
                raise ValueError('Whole accepted Q phase is not exactly covered')
            if _differences(con,'program_all_accepted_candidates','program_all_export_features',['query_id','product_id']):
                raise ValueError('Whole accepted C phase is not exactly covered')
            for table,keys in [('program_all_export_queries','query_id'),('program_all_export_features','(query_id,product_id)')]:
                count,distinct=con.execute('SELECT count(*),count(DISTINCT '+keys+') FROM '+table).fetchone()
                if count!=distinct:raise ValueError('Whole phase duplicate output key')
        check();return dict(status='physical_consistency_passed',source_formula_acceptance=False)
    finally:
        if timer is not None:timer.cancel()
        con.close()


def verify_source_acceptance(path,*,check=lambda:None):
    """Consume a separately reviewed source proof, never a fresh producer hash.

    The immutable proof pins include the whole physical map, independent oracle
    source and aggregate evidence, and a successful measured parent receipt.
    Their authority comes from independent review; physical inspection alone is
    insufficient. This function does not issue approvals.
    """
    approval=_read_json(path)
    mechanics._keys(approval,{'version','approved','scope','run_id','fingerprints','source_proof'},'selected-program acceptance')
    if type(approval['version']) is not int or approval['version']!=1 or approval['approved'] is not True or approval['scope']!='reviewed_selected_feature_program_source':
        raise ValueError('Unreviewed source acceptance role')
    if type(approval['run_id']) is not str or not re.fullmatch(r'[0-9a-f]{64}',approval['run_id']):raise ValueError('Invalid accepted runID')
    directory=ROOT/'artifacts/feature-program-collection'/approval['run_id']
    if (directory/'report.failed.json').exists():raise ValueError('Known failed collection')
    manifest=_read_json(directory/'run.json');report=_read_json(directory/'report.json')
    refs=manifest['identity']['acceptance_refs']
    planned,collections=prepare_plan(*(mechanics.local(refs[n]) for n in ['train','selection','contract','base_registry']),check=check)
    if manifest['run_id']!=planned['run_id'] or report.get('run_id')!=planned['run_id'] or manifest['identity']!=planned['identity'] or approval['run_id']!=planned['run_id']:
        raise ValueError('Actual source plan differs')
    if report['status']!='complete_produced_unreviewed' or report['labels_loaded'] is not False or type(report['fit_attempt_count']) is not int or report['fit_attempt_count']!=0:
        raise ValueError('Source producer did not complete without labels/fits')
    if report.get('limits')!=LIMITS or report.get('source_formula_acceptance') is not False:raise ValueError('Source report limits/proof boundary differs')
    for name,cap in [('seconds',1200),('process_cpu_user_system_seconds',900),('process_peak_rss_bytes',8*2**30)]:
        v=report.get(name)
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=cap:raise ValueError('Unknown or over-budget successful source measurement')
    execution=manifest['execution_approval'];expected=dict(version=1,approved=True,scope=ROLE,run_id=manifest['run_id'],fingerprints=manifest['identity']['fingerprints'])
    if canonical_json(_read_json(mechanics.local(execution['path'])))!=canonical_json(expected):raise ValueError('Detached execution approval')
    claim=manifest['source_claim'];mechanics._keys(claim,{'path','sha256'},'source claim pin')
    if claim['path']!='artifacts/feature-program-study/source.claim.json' or report.get('source_claim')!=claim:raise ValueError('Source ownership namespace/report differs')
    ownership=_read_json(mechanics.local(claim['path']))
    static=dict(version=1,scope='once_only_selected12_source_preparation',declared_shared_study_actual_cpu_seconds=7200,
        source_cpu_allocation=900,source_wall_allocation=1200,oracle_cpu_allocation=900,fit_attempts_authorized_here=0,
        unknown_cost_policy='STOP_no_refill',accounting='fresh_absolute_SELF_plus_successful_parent_tail_receipt_later_shared_prefix')
    mechanics._keys(ownership,set(static)|{'attempt_token','created_actual_utc'},'shared source ownership')
    if any(canonical_json(ownership[k])!=canonical_json(v) for k,v in static.items()) or type(ownership['attempt_token']) is not str or not re.fullmatch(r'attempt-[0-9a-f]{32}',ownership['attempt_token']):
        raise ValueError('Source ownership/budget contract differs')
    proof=approval['source_proof']
    mechanics._keys(proof,{'oracle_source','aggregate_evidence','parent_receipt'},'independent source proof')
    for v in proof.values():mechanics._keys(v,{'path','sha256'},'independent source proof pin')
    evidence=_read_json(mechanics.local(proof['aggregate_evidence']['path']));receipt=_read_json(mechanics.local(proof['parent_receipt']['path']))
    if (evidence.get('status')!='verified' or evidence.get('run_id')!=manifest['run_id'] or evidence.get('formula_values_complete') is not True
            or evidence.get('source_proof_scope')!='all_selected12_values_and_accepted_QC_domain'
            or evidence.get('oracle_source')!=proof['oracle_source'] or type(evidence.get('fit_attempt_count')) is not int or evidence['fit_attempt_count']!=0):
        raise ValueError('Independent aggregate source proof differs')
    expected_outputs={a['path']:a['sha256'] for days in manifest['outputs'].values() for d in days for a in d['artifacts'].values()}
    pairs=sum(d['artifacts']['features']['rows'] for days in manifest['outputs'].values() for d in days)
    for key in ['checked_pairs','checked_physical_columns','checked_scalar_values','mismatch_count']:
        if type(evidence.get(key)) is not int:raise ValueError('Independent proof counts must be strict integers')
    if (evidence.get('verified_outputs')!=expected_outputs or evidence.get('checked_pairs')!=pairs
            or type(evidence.get('checked_pairs')) is not int or evidence.get('checked_physical_columns')!=12
            or evidence.get('checked_scalar_values')!=pairs*12 or evidence.get('mismatch_count')!=0):
        raise ValueError('Independent proof does not bind the full output map/value scope')
    if (receipt.get('status')!='verified' or receipt.get('run_id')!=manifest['run_id'] or type(receipt.get('observer_exit_code')) is not int or receipt['observer_exit_code']!=0
            or receipt.get('oracle_source')!=proof['oracle_source'] or receipt.get('evidence')!=proof['aggregate_evidence']
            or type(receipt.get('actual_cpu_seconds')) not in (int,float) or not math.isfinite(receipt['actual_cpu_seconds'])
            or not 0<=receipt['actual_cpu_seconds']<=1800):
        raise ValueError('Independent parent completion/cost proof differs')
    for role in ['producer','oracle']:
        cost=receipt.get(role)
        if (not isinstance(cost,dict) or type(cost.get('exit_code')) is not int or cost['exit_code']!=0
                or type(cost.get('actual_cpu_seconds')) not in (int,float) or not math.isfinite(cost['actual_cpu_seconds'])
                or not 0<=cost['actual_cpu_seconds']<=900 or type(cost.get('wall_seconds')) not in (int,float)
                or not math.isfinite(cost['wall_seconds']) or not 0<=cost['wall_seconds']<=1200
                or type(cost.get('peak_rss_bytes')) is not int or not 0<cost['peak_rss_bytes']<=8*2**30):
            raise ValueError('Known successful source/oracle lifetime cost required')
    producer_refs={n:dict(path=mechanics.relative(directory/(n+'.json')),sha256=sha256_file(directory/(n+'.json'))) for n in ['run','report']}
    if (receipt['producer'].get('manifest')!=producer_refs['run'] or receipt['producer'].get('report')!=producer_refs['report']
            or receipt['producer']['actual_cpu_seconds']+1e-6<report['process_cpu_user_system_seconds']
            or receipt['producer']['wall_seconds']+1e-6<report['seconds']
            or receipt['producer']['peak_rss_bytes']<report['process_peak_rss_bytes']
            or receipt['oracle'].get('oracle_source')!=proof['oracle_source'] or receipt['oracle'].get('evidence')!=proof['aggregate_evidence']):
        raise ValueError('Lifetime cost receipt detached from actual producer/oracle')
    if receipt['actual_cpu_seconds']!=math.fsum(receipt[k]['actual_cpu_seconds'] for k in ['producer','oracle']):
        raise ValueError('Shared source budget prefix must charge both full lifetimes once')
    expected_phases={role:dict(status='complete_produced_unreviewed',queries=sum(d['artifacts']['queries']['rows'] for d in ds),
        pairs=sum(d['artifacts']['features']['rows'] for d in ds),days=ds) for role,ds in manifest['outputs'].items()}
    if report.get('phases')!=expected_phases:raise ValueError('Actual report phase/daily output scope differs')
    outputpins=expected_outputs
    required=mechanics.merge_pins(planned['identity']['fingerprints'],{execution['path']:execution['sha256'],claim['path']:claim['sha256']},outputpins,
        {mechanics.relative(directory/n):sha256_file(directory/n) for n in ['run.json','report.json']},
        {v['path']:v['sha256'] for v in proof.values()})
    if approval['fingerprints']!=required:raise ValueError('Independent acceptance pin set differs')
    mechanics.verify_pins(required,check);physical=inspect_physical(manifest,collections,check=check)
    mechanics.verify_pins(required,check)
    if (directory/'report.failed.json').exists():raise ValueError('Known late failed collection')
    return dict(manifest=manifest,report=report,collections=collections,pins=mechanics.merge_pins(required,{mechanics.relative(path):sha256_file(path)}),physical=physical)


class SourceAudit(mechanics.ExecutionAudit):
    """Fresh single-process source allocation, including imports and planning.

    Parent receipt must charge the minimal persistence/exit tail. Later model
    phases consume that measured source+oracle prefix from the same7200 study.
    """
    def __init__(self):
        super().__init__(ROOT/'artifacts/feature-program-collection',seconds=1200,scope=ROLE,cpu_seconds=900)
        self.started=ENTRY_MONOTONIC;self.cpu_started=0.
        self.deadline=mechanics.RunDeadline(1200,started_at=self.started);self.ledger.deadline=self.deadline
    def guard(self):
        super().guard()
        child=resource.getrusage(resource.RUSAGE_CHILDREN)
        if child.ru_utime+child.ru_stime!=0:raise ValueError('Source allocation must run fresh without children')


def _consume_source_claim(audit):
    path=ROOT/'artifacts/feature-program-study/source.claim.json';path.parent.mkdir(parents=True,exist_ok=True)
    body=dict(version=1,scope='once_only_selected12_source_preparation',attempt_token=audit.directory.name,
        declared_shared_study_actual_cpu_seconds=7200,source_cpu_allocation=900,source_wall_allocation=1200,
        oracle_cpu_allocation=900,fit_attempts_authorized_here=0,unknown_cost_policy='STOP_no_refill',
        accounting='fresh_absolute_SELF_plus_successful_parent_tail_receipt_later_shared_prefix',
        created_actual_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
    # The once-only source ownership is separate from the later four-fit claim.
    with path.open('x') as handle:
        handle.write(canonical_json(body)+'\n');handle.flush();os.fsync(handle.fileno())
    audit.report['source_claim']=dict(path=mechanics.relative(path),sha256=sha256_file(path))
    return audit.report['source_claim']


def run_source(train_acceptance,selection_acceptance,contract_path,base_registry_path,*,execution_approval):
    """One claimed source process waits for exact external proposal approval.

    No source calculation, label relation, Pool, prediction or fit before the
    approval. Readonly lineage planning is paid inside the same source900CPU.
    """
    with SourceAudit() as audit:
        claim=audit.stage('consume_once_source_allocation',lambda:_consume_source_claim(audit))
        manifest,collections=audit.stage('reviewed_lineage_and_symbolic_plan',lambda:prepare_plan(
            train_acceptance,selection_acceptance,contract_path,base_registry_path,check=audit.guard))
        _atomic(audit.directory/'proposal.json',manifest)
        audit.report.update(status='waiting_exact_source_execution_approval',run_id=manifest['run_id'],limits=deepcopy(LIMITS))
        _atomic(audit.directory/'report.json',audit.report)
        print(json.dumps(dict(status=audit.report['status'],directory=mechanics.relative(audit.directory),run_id=manifest['run_id'])),flush=True)
        while not Path(execution_approval).exists():
            audit.guard()
            if (audit.directory/'abort.json').exists():raise RuntimeError('External source review aborted; no refill')
            time.sleep(.25)
        audit.guard();audit.identify(manifest,execution_approval);audit.manifest['source_claim']=claim
        outputs={};union=manifest['identity']['selected_union'];base_registry=manifest['identity']['pool']['identity']['base_registry']
        source=collections['train']['plan']['execution_inputs']['source_path']
        def open_source():
            audit.connection=duckdb.connect(str(mechanics.local(source)),read_only=True);audit.attach(audit.connection)
        audit.stage('open_source_read_only',open_source);con=audit.connection
        audit.report.update(status='producing',phases={},labels_loaded=False,fit_attempt_count=0,
            source_formula_acceptance=False,study_cost_policy='source_and_independent_oracle_and_future_four_fits_share7200_actualCPU')
        for role,collection in collections.items():
            phase=collection['phase'];day=mechanics._utc(phase['range']['start']).replace(tzinfo=None)
            end=mechanics._utc(phase['range']['end']).replace(tzinfo=None);days=[]
            source_start=mechanics._utc(collection['plan']['identity']['shard_protocols'][0]['source']['start']).replace(tzinfo=None)
            while day<end:
                audit.guard();tag=role+'_'+day.strftime('%Y-%m-%d')
                audit.stage(tag+'_accepted_Q_C_and_oldF',lambda:_bind_temp_day(con,collection,day))
                qn=con.execute('SELECT count(*) FROM pilot_queries').fetchone()[0]
                cn=con.execute('SELECT count(*) FROM pilot_candidates').fetchone()[0]
                if qn>2000 or cn>440000:raise ValueError('Daily pre-allocation Q/C cap exceeded')
                audit.stage(tag+'_selected_union_compile',lambda:compiler.create_manual_features(con,_daily_config(collection,day),union['registry'],
                    stage=lambda n,op:audit.stage(tag+'_'+n,op),budget_check=audit.guard))
                boundary=audit.stage(tag+'_oldB_all_fields_and_new_ranges',lambda:validate_day(con,old_table='program_old_features',
                    output_table='manual_features',queries_table='pilot_queries',base_registry=base_registry,union=union,source_start=source_start,check=audit.guard))
                directory=audit.directory/role/day.strftime('%Y-%m-%d');directory.mkdir(parents=True,exist_ok=False);artifacts={}
                for name,table,order in [('queries','pilot_queries','query_id'),('features','manual_features','query_id,product_id')]:
                    path=directory/(name+'.parquet')
                    audit.stage(tag+'_export_'+name,lambda path=path,table=table,order=order:con.execute(
                        'COPY(SELECT * FROM '+table+' ORDER BY '+order+') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)]))
                    artifacts[name]=dict(path=mechanics.relative(path),sha256=sha256_file(path),bytes=path.stat().st_size,
                        rows=con.execute('SELECT count(*) FROM '+table).fetchone()[0],schema=[list(r[:2]) for r in con.execute('DESCRIBE '+table).fetchall()])
                days.append(dict(anchor=day.strftime('%Y-%m-%dT%H:%M:%SZ'),artifacts=artifacts,boundary=boundary));day+=timedelta(days=1)
                audit.report['phases'][role]=dict(status='producing',days=days);_atomic(audit.directory/'report.json',audit.report)
            outputs[role]=days
            audit.report['phases'][role]=dict(status='complete_produced_unreviewed',queries=sum(d['boundary']['queries'] for d in days),
                pairs=sum(d['boundary']['pairs'] for d in days),days=days)
        audit.manifest['outputs']=outputs
        audit.stage('every_export_physical_consistency',lambda:inspect_physical(audit.manifest,collections,check=audit.guard,deadline=audit.deadline))
        audit.stage('terminal_all_input_repin',lambda:mechanics.verify_pins(mechanics.merge_pins(manifest['identity']['fingerprints'],
            {audit.manifest['execution_approval']['path']:audit.manifest['execution_approval']['sha256'],claim['path']:claim['sha256']}),audit.guard))
        audit.report['status']='complete_produced_unreviewed'
    return audit.report


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--train-acceptance',required=True)
    parser.add_argument('--selection-acceptance',required=True);parser.add_argument('--contract',required=True)
    parser.add_argument('--base-registry',required=True);parser.add_argument('--execution-approval',required=True)
    args=parser.parse_args()
    result=run_source(*(mechanics.local(getattr(args,n)) for n in ['train_acceptance','selection_acceptance','contract','base_registry']),
        execution_approval=mechanics.local(args.execution_approval))
    print(json.dumps(dict(status=result['status'],run_id=result['run_id'],fit_attempt_count=0,source_formula_acceptance=False)),flush=True)


if __name__=='__main__':main()
