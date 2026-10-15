"""Admission for one UNUSED oracle over a failed source job's immutable exports.

No regeneration, model, feature compiler execution, acceptance writer or physical
whole-phase materializer is provided here. Final source approval is separate.
"""
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib,json,math,re
from pathlib import Path
from scripts import feature_program_collection as source
from scripts import metadata_price_collection as mechanics
from scripts.protocol_manifest import canonical_json,sha256_file
ROOT=Path(__file__).resolve().parents[1]
POLICY_SCOPE='recover_failed_selected12_source_with_unused_oracle'
ORACLE_SCOPE='independent_recovered_selected_feature_program_source_oracle'
ORIGINAL_CODE='b3e05d85d97afc26d8cbda8627d3bfffc46ad6a037d03beb1c0c6d5d807ef84f'

def need(v,message):
    if not v:raise ValueError(message)
def finite(v):return type(v) in (int,float) and math.isfinite(v) and v>=0

def validate_source_claim(body):
 static=dict(version=1,scope='once_only_selected12_source_preparation',declared_shared_study_actual_cpu_seconds=7200,source_cpu_allocation=900,source_wall_allocation=1200,oracle_cpu_allocation=900,fit_attempts_authorized_here=0,unknown_cost_policy='STOP_no_refill',accounting='fresh_absolute_SELF_plus_successful_parent_tail_receipt_later_shared_prefix')
 need(type(body) is dict and set(body)==set(static)|{'attempt_token','created_actual_utc'} and all(canonical_json(body[k])==canonical_json(v) for k,v in static.items()),'Source once-claim contract differs')
 need(type(body['attempt_token']) is str and re.fullmatch(r'attempt-[0-9a-f]{32}',body['attempt_token']) is not None and type(body['created_actual_utc']) is str,'Source claim audit identity')
 created=datetime.fromisoformat(body['created_actual_utc']);need(created.tzinfo is not None and created.utcoffset()==timedelta(0),'Source claim UTC audit timestamp')

def validate_failed_source(manifest,report,prefix):
    """Pure declared-map/failure/cost gate; no source/physical acceptance."""
    identity=manifest['identity'];run_id=manifest['run_id']
    need(type(run_id) is str and re.fullmatch('[0-9a-f]{64}',run_id) is not None and hashlib.sha256(canonical_json(identity).encode()).hexdigest()==run_id,'Failed source identity digest')
    need(identity['role']==source.ROLE and identity['limits']==source.LIMITS and identity['fingerprints'].get('scripts/feature_program_collection.py')==ORIGINAL_CODE,'Wrong original producer or limits')
    need(report['status']=='failed' and report['run_id']==run_id and report['scope']==source.ROLE and report['limits']==source.LIMITS and type(report['fit_attempt_count']) is int and report['fit_attempt_count']==0 and report['labels_loaded'] is False and report['source_formula_acceptance'] is False,'Source-only known failure required')
    stages=report['stages']
    need(type(stages) is list and len(stages)>1 and all(s['status']=='complete' for s in stages[:-1]),'Incomplete earlier source stage')
    last=stages[-1]
    need(last['stage']=='every_export_physical_consistency' and last['status']=='failed' and last['error_type']==report['error_type']=='OutOfMemoryException' and last['error']==report['error'] and 'max_temp_directory_size' in report['error'],'Only documented final wide-inspector OOM can recover')
    need(report['source_claim']==manifest['source_claim'] and manifest['source_claim']['path']=='artifacts/feature-program-study/source.claim.json','Original once-only source claim')
    outputs=manifest['outputs'];need(type(outputs) is dict and set(outputs)=={'train','selection'},'Exact failed output phase map')
    model=identity['pool']['identity']['base_model_schema']
    need(type(model) is list and len(model)==41 and len({v['name'] for v in model})==41,'Frozen B41 schema')
    derived={'retrieval_last_event_age_seconds','retrieval_last_event_missing'}
    typed={v['name']:v['dtype'] for v in model if v['name'] not in derived}
    need(len(typed)==39 and all(t in {'BOOLEAN','BIGINT','DOUBLE'} for t in typed.values()),'Physical B39 model types')
    headers=dict(query_id='VARCHAR',product_id='BIGINT',last_user_event_time='TIMESTAMP',user_id='BIGINT',anchor='TIMESTAMP',candidate_category_id='BIGINT')
    need(not set(typed)&set(headers),'Header/model schema collision');typed.update(headers)
    names=identity['base_feature_columns'];need(type(names) is list and len(names)==45 and all(type(n) is str for n in names) and len(set(names))==45 and set(names)==set(typed),'Physical ordered B45 names')
    expected_schema=source._expected_schema([(n,typed[n]) for n in names],identity['pool']['identity']['base_registry'],identity['selected_union']['registry'])
    qn=pn=days=0;out={};phases={}
    for role,parts in outputs.items():
        need(type(parts) is list and parts,'Missing declared source days');previous=None
        for part in parts:
            need(set(part)=={'anchor','artifacts','boundary'} and set(part['artifacts'])=={'queries','features'},'Daily declaration keys')
            anchor=mechanics._utc(part['anchor']);need(anchor.hour==anchor.minute==anchor.second==anchor.microsecond==0 and (previous is None or anchor==previous+timedelta(days=1)),'Contiguous UTC daily declarations');previous=anchor
            for kind,a in part['artifacts'].items():
                need(set(a)=={'path','sha256','bytes','rows','schema'} and type(a['bytes']) is int and a['bytes']>0 and type(a['rows']) is int and a['rows']>=0,'Typed declared artifact descriptor')
                need(a['path']==f'artifacts/feature-program-collection/{run_id}/{role}/{anchor:%Y-%m-%d}/{kind}.parquet' and a['path'] not in out and re.fullmatch('[0-9a-f]{64}',a['sha256']) is not None,'Failed export namespace/hash');out[a['path']]=a['sha256']
            q,f=part['artifacts']['queries'],part['artifacts']['features'];need(q['rows']<=2000 and f['rows']<=440000 and f['schema']==[list(v) for v in expected_schema],'Declared daily caps/schema')
            b=part['boundary'];need(b==dict(queries=q['rows'],pairs=f['rows'],new_physical_columns=12,baseline_all_fields_preserved=True,source_formula_acceptance=False,schema=[list(v) for v in expected_schema]),'Declared physical boundary differs')
            qn+=q['rows'];pn+=f['rows'];days+=1
        phases[role]=dict(status='complete_produced_unreviewed',queries=sum(d['artifacts']['queries']['rows'] for d in parts),pairs=sum(d['artifacts']['features']['rows'] for d in parts),days=parts)
    need(report['phases']==phases,'Failed report did not finish every declared daily export')
    need(set(prefix)=={'version','status','scope','run_id','producer'} and type(prefix['version']) is int and prefix['version']==1 and prefix['status']=='verified_failed_source_lifetime' and prefix['scope']=='failed_source_lifetime_only_no_formula_acceptance' and prefix['run_id']==run_id,'Only failed source lifetime prefix')
    paid=prefix['producer'];need(set(paid)=={'exit_code','actual_cpu_seconds','actual_cpu_upper_seconds','wall_seconds','peak_rss_bytes','manifest','report'} and type(paid['exit_code']) is int and paid['exit_code']==1,'Failed original exit evidence')
    need(all(finite(paid[k]) for k in ['actual_cpu_seconds','actual_cpu_upper_seconds','wall_seconds']) and paid['actual_cpu_seconds']<=paid['actual_cpu_upper_seconds']<=900 and paid['wall_seconds']<=1200 and type(paid['peak_rss_bytes']) is int and 0<paid['peak_rss_bytes']<=8*2**30,'Failed original resource cost unknown or over cap')
    for k,body in [('actual_cpu_seconds','process_cpu_user_system_seconds'),('wall_seconds','seconds'),('peak_rss_bytes','process_peak_rss_bytes')]:need(finite(report.get(body)) and report[body]<=paid[k]+(0 if body=='process_peak_rss_bytes' else 1e-6),'Failed lifetime lower bound')
    need(paid['manifest']['path']==f'artifacts/feature-program-collection/{run_id}/run.json' and paid['report']['path']==f'artifacts/feature-program-collection/{run_id}/report.json','Failed prefix detached from source')
    return dict(run_id=run_id,outputs=out,pairs=pn,queries=qn,days=days,source_claim=manifest['source_claim'])

def validate_policy(policy,manifest,report,prefix):
    """Exact code-bound policy; own source bytes only, no data or budget reset."""
    need(set(policy)=={'version','approved','scope','run_id','owner_source','oracle_source','producer_manifest','producer_report','failed_lifetime_receipt','source_claim','boundary','fingerprints'} and type(policy['version']) is int and policy['version']==1 and policy['approved'] is True and policy['scope']==POLICY_SCOPE,'Exact source recovery policy required')
    declared=validate_failed_source(manifest,report,prefix);need(policy['run_id']==declared['run_id'],'Recovery run differs')
    for n in ['owner_source','oracle_source','producer_manifest','producer_report','failed_lifetime_receipt','source_claim']:
        ref=policy[n];need(type(ref) is dict and set(ref)=={'path','sha256'} and type(ref['path']) is str and not Path(ref['path']).is_absolute() and '..' not in Path(ref['path']).parts and re.fullmatch('[0-9a-f]{64}',ref['sha256']) is not None,'Recovery authority ref schema')
    need(policy['owner_source']['path']=='scripts/run_feature_source_recovery.py' and policy['oracle_source']['path']=='tests/oracles/feature_program_recovery_audit.py','Reviewed recovery entry paths')
    need(policy['producer_manifest']==prefix['producer']['manifest'] and policy['producer_report']==prefix['producer']['report'] and policy['source_claim']==manifest['source_claim'],'Policy original references differ')
    b=policy['boundary'];need(set(b)=={'old_source_cpu_upper_seconds','old_source_active_wall_seconds','owner_and_oracle_cpu_seconds','owner_and_oracle_wall_seconds','original_source_cpu_cap','original_source_wall_cap','original_oracle_cpu_cap','original_oracle_wall_cap','shared_study_cpu_cap','original_absolute_deadline','failure_consumes_oracle'},'Recovery boundary exact keys')
    fixed=dict(original_source_cpu_cap=900,original_source_wall_cap=1200,original_oracle_cpu_cap=900,original_oracle_wall_cap=1200,shared_study_cpu_cap=7200,original_absolute_deadline='unavailable_not_reconstructed',failure_consumes_oracle=True)
    need(all(canonical_json(b[k])==canonical_json(v) for k,v in fixed.items()),'Recovery changed original caps or clock claim')
    need(b['old_source_cpu_upper_seconds']==prefix['producer']['actual_cpu_upper_seconds'] and b['old_source_active_wall_seconds']==prefix['producer']['wall_seconds'],'Failed prefix paid boundary differs')
    need(type(b['owner_and_oracle_cpu_seconds']) is int and 1<=b['owner_and_oracle_cpu_seconds']<=792 and type(b['owner_and_oracle_wall_seconds']) is int and 1<=b['owner_and_oracle_wall_seconds']<=1044 and b['old_source_cpu_upper_seconds']+b['owner_and_oracle_cpu_seconds']<=900 and b['old_source_active_wall_seconds']+b['owner_and_oracle_wall_seconds']<=1200,'Recovery resets source/oracle allowance')
    pins=policy['fingerprints'];need(type(pins) is dict and all(pins.get(p)==h for p,h in declared['outputs'].items()),'Policy must pin every immutable failed export')
    for n in ['owner_source','oracle_source','producer_manifest','producer_report','failed_lifetime_receipt','source_claim']:need(pins.get(policy[n]['path'])==policy[n]['sha256'],'Policy authority closure missing')
    need(pins.get('scripts/feature_program_collection.py')==ORIGINAL_CODE,'Original failed producer bytes not pinned')
    admission_path='scripts/feature_program_source_recovery.py'
    need(pins.get(admission_path)==sha256_file(Path(__file__).resolve()),'Mandatory admission code pin absent or changed')
    need(type(pins.get('scripts/strong_baseline.py')) is str and re.fullmatch('[0-9a-f]{64}',pins['scripts/strong_baseline.py']) is not None,'Mandatory reviewed lifecycle code pin')
    for name,digest in manifest['identity']['fingerprints'].items():
        if name.endswith('.py'):need(pins.get(name)==digest,'Mandatory original executable input pin missing')
    return deepcopy(b)

def load_recovery_inputs(policy_path,*,check=lambda:None):
    """Paid oracle rederivation of107 input pins; no wide physical inspection."""
    policy,policy_sha=source._snapshot(policy_path);mechanics.verify_pins(policy['fingerprints'],check)
    manifest=source._read_json(mechanics.local(policy['producer_manifest']['path']));report=source._read_json(mechanics.local(policy['producer_report']['path']));prefix=source._read_json(mechanics.local(policy['failed_lifetime_receipt']['path']))
    boundary=validate_policy(policy,manifest,report,prefix)
    refs=manifest['identity']['acceptance_refs'];plan,collections=source.prepare_plan(*(mechanics.local(refs[k]) for k in ['train','selection','contract','base_registry']),check=check)
    need(plan['run_id']==manifest['run_id'] and canonical_json(plan['identity'])==canonical_json(manifest['identity']),'Actual failed source plan differs')
    execution=manifest['execution_approval'];mechanics.verify_pins({execution['path']:execution['sha256']},check)
    need(canonical_json(source._read_json(mechanics.local(execution['path'])))==canonical_json(dict(version=1,approved=True,scope=source.ROLE,run_id=plan['run_id'],fingerprints=plan['identity']['fingerprints'])),'Original source execution approval differs')
    claim=source._read_json(mechanics.local(manifest['source_claim']['path']))
    validate_source_claim(claim)
    for role,col in collections.items():
        start=mechanics._utc(col['phase']['range']['start']);end=mechanics._utc(col['phase']['range']['end'])
        expected=[(start+timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ') for i in range((end-start).days)]
        need([v['anchor'] for v in manifest['outputs'][role]]==expected,'Missing accepted daily phase partition')
    need(sha256_file(policy_path)==policy_sha,'Recovery policy changed during rederivation')
    pins=mechanics.merge_pins(plan['identity']['fingerprints'],policy['fingerprints'],{mechanics.relative(policy_path):policy_sha,execution['path']:execution['sha256']})
    mechanics.verify_pins(pins,check)
    return dict(policy=policy,boundary=boundary,manifest=manifest,report=report,prefix=prefix,collections=collections,pins=pins)
