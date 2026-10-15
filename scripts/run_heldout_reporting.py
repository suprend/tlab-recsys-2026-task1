"""Prospective reserved reporting owner helpers; CLI integration under review.

No invocation is performed by importing this module. The global claim precedes
paid historical439 authentication; failure consumes the original owner attempt.
"""
import time
ENTRY_MONOTONIC=time.monotonic()
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
for _namespace in ['scripts','tests','tests/oracles']:
    if (ROOT/_namespace/'__init__.py').exists():raise ValueError('Unpinned namespace initializer forbidden before owner imports')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import heldout_execution as x
from scripts import heldout_contract as h

CLAIM='artifacts/heldout-study/owner.claim.json'
OWNER='scripts/run_heldout_reporting.py'
POLICY='configs/heldout/reporting-only-v1.json'
SOURCE_INPUTS=dict(source='data/processed/october.duckdb',pool='configs/features/automation-pool.json',registry='configs/features/manual-18.json')
AUTHORITY_KEYS={'initial_execution','source_acceptance','prediction_acceptance','target_execution'}
CODE=(OWNER,'scripts/heldout_execution.py','scripts/heldout_reporting_worker.py','scripts/heldout_worker_context.py',
    'tests/oracles/heldout_source_worker.py','tests/oracles/heldout_prediction_worker.py','tests/oracles/heldout_metric_worker.py',
    'scripts/heldout_contract.py','scripts/feature_program_control.py','scripts/heldout_source.py',
    'scripts/heldout_predictions.py','scripts/heldout_evaluation.py','scripts/inference_data.py',
    'tests/oracles/heldout_source_audit.py','tests/oracles/heldout_prediction_audit.py','tests/oracles/heldout_metric_audit.py',
    'scripts/feature_programs.py','scripts/manual_features.py','scripts/anchor_pilot.py','scripts/candidate_pilot.py',
    'scripts/protocol_manifest.py','scripts/temporal_contract.py','scripts/train_baselines.py',
    'scripts/development_collection.py','scripts/ranking_metrics.py','scripts/strong_baseline.py',
    'uv.lock','pyproject.toml')
REQUEST_KEYS={'version','scope','owner_source','policy','model_acceptance','compute_evidence',
              'code_fingerprints','role_entries','authority_paths','source_inputs'}


def local(name):return x.local(ROOT,name)
def relative(path):return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
def now():return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def merge(*mappings):
    result={}
    for mapping in mappings:
        h.need(type(mapping) is dict,'Exact owner pin map required')
        for name,digest in mapping.items():
            x.ref(dict(path=name,sha256=digest));h.need(name not in result or result[name]==digest,'Conflicting original owner pin')
            result[name]=digest
    return result


def read_ref(reference,check):
    x.ref(reference);check();body,digest=x.read(local(reference['path']));check()
    h.need(digest==reference['sha256'],'Parsed owner metadata differs from original reference')
    return body


def pin_all(pins,check):
    for name,digest in pins.items():h.need(x.sha(local(name),check)==digest,'Original reserved owner input changed')


def write_once(directory,name,body):
    saved=x.exclusive(directory/name,body)
    return dict(path=relative(saved['path']),sha256=saved['sha256'])


def consume_owner(request_path,budget):
    """Small request snapshot only, then one project-wide fsynced consumed claim.

    Shape validation, code hashing and historical439 streaming follow this claim.
    A malformed parsed request consumes the allowance; another root cannot refill.
    """
    budget.guard();own,children,peak=budget.usage();h.need(children==0,'Fresh heldout owner must have no previous reaped children')
    path=Path(request_path).resolve();path.relative_to(ROOT.resolve());request,digest=x.read(path)
    reference=dict(path=relative(path),sha256=digest)
    directory=local('artifacts/heldout-invocations/'+uuid.uuid4().hex)
    body=dict(version=1,scope='reserved_reporting_owner_attempt',request=reference,
        owner_source=deepcopy(request.get('owner_source')) if type(request) is dict else None,
        output_directory=relative(directory),started_monotonic=budget.started,original_deadline_monotonic=budget.outer_deadline)
    saved=x.exclusive(local(CLAIM),body)
    claim=dict(path=CLAIM,sha256=saved['sha256']);directory.mkdir(parents=True,exist_ok=False)
    write_once(directory,'owner-consumption.json',body)
    return dict(request=deepcopy(request),request_ref=reference,owner_claim=claim,directory=directory)


def validate_request(body):
    h.keys(body,REQUEST_KEYS,'Reserved execution request')
    h.need(type(body['version']) is int and body['version']==1 and body['scope']=='prospective_reserved_reporting_owner','Typed owner request scope/version required')
    for name in ['owner_source','policy','model_acceptance','compute_evidence']:x.ref(body[name])
    h.need(body['owner_source']['path']==OWNER and body['policy']['path']==POLICY,'Fixed reviewed owner/policy path required')
    h.keys(body['source_inputs'],SOURCE_INPUTS,'Reserved source inputs')
    for name,path in SOURCE_INPUTS.items():x.ref(body['source_inputs'][name]);h.need(body['source_inputs'][name]['path']==path,'Fixed source/pool/registry path required')
    h.need(type(body['code_fingerprints']) is dict and set(body['code_fingerprints'])==set(CODE),'Exact reviewed executable dependency closure required')
    for name,digest in body['code_fingerprints'].items():x.ref(dict(path=name,sha256=digest))
    h.need(body['owner_source']['sha256']==body['code_fingerprints'][OWNER],'Request owner-source pin differs')
    h.keys(body['role_entries'],x.ROLES,'Six fixed worker entries')
    for role,path in x.ENTRY.items():
        entry=body['role_entries'][role];x.ref(entry)
        h.need(entry['path']==path and entry['sha256']==body['code_fingerprints'][path],'Only six fixed reviewed worker entries/pins allowed')
    h.keys(body['authority_paths'],AUTHORITY_KEYS,'External authority destinations')
    values=[]
    for name,path in body['authority_paths'].items():
        x.ref(dict(path=path,sha256='0'*64));h.need(path.startswith('artifacts/acceptance/') and path.endswith('.json'),'Fixed external acceptance namespace required');values.append(path)
    h.need(len(set(values))==4,'Four distinct external authority destinations required')
    resolved=[]
    for name in values:
        path=local(name);path.relative_to(ROOT.resolve()/'artifacts'/'acceptance')
        h.need(relative(path)==name,'Canonical physical external authority path required')
        resolved.append(path.as_posix().casefold())
    h.need(len(set(resolved))==4,'Four physically distinct external authority destinations required')
    return deepcopy(body)


def verify_consumption(consumed,budget):
    h.keys(consumed,{'request','request_ref','owner_claim','directory'},'Original owner consumption')
    h.need(consumed['owner_claim']['path']==CLAIM,'Fixed project-wide consumed claim required')
    original_request=read_ref(consumed['request_ref'],budget.guard)
    h.need(h.canonical(original_request)==h.canonical(consumed['request']),'Owner request snapshot changed in memory')
    original=read_ref(consumed['owner_claim'],budget.guard)
    expected=dict(version=1,scope='reserved_reporting_owner_attempt',request=consumed['request_ref'],
        owner_source=deepcopy(original_request.get('owner_source')) if type(original_request) is dict else None,
        output_directory=relative(consumed['directory']),started_monotonic=budget.started,original_deadline_monotonic=budget.outer_deadline)
    h.need(h.canonical(original)==h.canonical(expected),'Original owner claim/lifetime association differs')
    h.need(expected['output_directory'].startswith('artifacts/heldout-invocations/'),'Fixed owner invocation namespace required')
    return original_request


def prepare_owner(consumed,budget):
    """Paid preparation under the already-consumed original absolute lifetime.

    No reserved Q/C/F, target, native model or fit is opened. Historical supplied
    artifact hashes are authenticated by the accepted guarded439 consumer once.
    """
    budget.guard();original_request=verify_consumption(consumed,budget)
    request_ref=consumed['request_ref'];claim=consumed['owner_claim'];directory=consumed['directory']
    preparation_ref=write_once(directory,'preparation.consumed.json',dict(version=1,scope='reserved_reporting_preparation_consumed',
        request=request_ref,owner_claim=claim,started_monotonic=budget.started,original_deadline_monotonic=budget.outer_deadline))
    request=validate_request(original_request)
    # Authority destinations are not bound approvals until independently issued.
    h.need(not any(local(path).exists() for path in request['authority_paths'].values()),'Prospective external gates must not be pre-issued')
    current=merge(request['code_fingerprints'],{request_ref['path']:request_ref['sha256'],claim['path']:claim['sha256'],preparation_ref['path']:preparation_ref['sha256']})
    pin_all(current,budget.guard)
    policy=read_ref(request['policy'],budget.guard);h.validate_policy(policy)
    evidence=read_ref(request['compute_evidence'],budget.guard)
    h.need(type(evidence) is list,'Decision compute evidence must be an explicit stage list')
    evidence_pins={}
    for item in evidence:
        h.need(type(item) is dict and 'receipt' in item,'Every compute stage needs original receipt')
        ref=item['receipt'];x.ref(ref);h.need(ref['path'] not in evidence_pins,'Distinct decision stage receipts required')
        evidence_pins[ref['path']]=ref['sha256']
    # The historical consumer is intentionally imported only after the claim and
    # current executable pins. It performs its own complete original439 stream.
    from scripts import feature_program_control as control
    verified=control.verify_choice(local(request['model_acceptance']['path']),check=budget.guard)
    h.need(verified['acceptance']==request['model_acceptance'],'Historical acceptance request detached')
    historical=verified['pins'];choice=verified['authenticated_choice']
    for ref in request['source_inputs'].values():h.need(historical.get(ref['path'])==ref['sha256'],'Source input outside paid historical439 closure')
    h.need(request['source_inputs']['pool']==choice['authority_refs']['pool'],'Symbolic pool authority differs from actual frozen choice')
    contract=read_ref(request['source_inputs']['pool'],budget.guard);registry=read_ref(request['source_inputs']['registry'],budget.guard)
    from scripts import feature_programs
    pool=feature_programs.generate_pool(contract,registry)
    budget.guard()
    original=merge(historical,current,evidence_pins,
        {request[name]['path']:request[name]['sha256'] for name in ['policy','model_acceptance','compute_evidence']})
    pin_all(evidence_pins,budget.guard)
    # Physical sealing is2026; simulated label availability and declared positive
    # compute interval are separately fixed by the accepted pure policy.
    lock=dict(version=1,scope='whole_reserved_decision_lock',policy=policy,choice=choice['candidate_id'],
        models=deepcopy(choice['models']),authority_refs=deepcopy(choice['authority_refs']),
        code_refs=[dict(path=name,sha256=request['code_fingerprints'][name]) for name in sorted(CODE)],sealed_at=now(),
        heldout_targets_opened=False,simulated_clock=dict(maximum_used_label_maturity=h.MATURITY,
            declared_compute_allowance_seconds=43200,decision_available_at=h.DECISION_AVAILABLE),compute_evidence=deepcopy(evidence))
    h.validate_lock(lock,authenticated_choice=choice)
    from scripts import heldout_source
    selected=heldout_source.selected_registry(pool,lock,authenticated_choice=choice)
    h.need(h.canonical(selected['base'])==h.canonical(registry),'Frozen selected base registry differs')
    lock_ref=write_once(directory,'decision-lock.json',lock);choice_ref=write_once(directory,'authenticated-choice.json',choice)
    identity=dict(version=1,scope='frozen_reserved_reporting_identity',request=request_ref,owner_claim=claim,
        choice=choice['candidate_id'],lock=lock_ref,authenticated_choice=choice_ref,source_inputs=deepcopy(request['source_inputs']),
        original_limits=deepcopy(x.LIMITS),role_caps=deepcopy(x.CAPS),fingerprints=merge(original,{ref['path']:ref['sha256'] for ref in [lock_ref,choice_ref]}),
        selected_extra_schema=selected['extra_schema'],source_formula_scope='chosen0or3_complete_core18_sampled',
        refits=0,adaptation=False)
    run_id=h.digest(identity)
    proposal=dict(run_id=run_id,identity=identity)
    proposal_ref=write_once(directory,'proposal.json',proposal)
    pins=merge(identity['fingerprints'],{proposal_ref['path']:proposal_ref['sha256']})
    plan=dict(run_id=run_id,choice=choice['candidate_id'],fingerprints=pins)
    # Metadata and failure/persistence tail remain part of this same owner budget.
    pin_all({ref['path']:ref['sha256'] for ref in [request_ref,claim,preparation_ref,lock_ref,choice_ref,proposal_ref]},budget.guard)
    budget.guard()
    return dict(request=request,request_ref=request_ref,owner_claim=claim,directory=directory,plan=plan,
        proposal=proposal,proposal_ref=proposal_ref,lock=lock,lock_ref=lock_ref,
        authenticated_choice=choice,choice_ref=choice_ref,selected=selected)


SOURCE_FIELDS={'version','scope','run_id','decision_lock','choice','source','days','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'}
PREDICTION_FIELDS={'version','scope','run_id','decision_lock','choice','source_acceptance','source_manifest','created_at','days','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'}
DAY_FIELDS={'anchor','queries','candidates','base_features','extra_features','query_count','candidate_count','mature_query_count'}


def closure(session):return merge(session.plan['fingerprints'],session.output_pins,session.authority_pins)


def issued_for(session,role):
    base=session.directory/role
    reference=dict(path=session.relative(base/'context.json'),sha256=session.authority_pins[session.relative(base/'context.json')])
    return read_ref(reference,session.budget.guard)


def role_receipt(session,role):
    record=next(row for row in session.states if row['role']==role)
    return read_ref(record['receipt'],session.budget.guard)


def role_output(session,role,name):
    path=session.relative(session.directory/role/name)
    h.need(path in session.output_pins,'Required original role output missing')
    return dict(path=path,sha256=session.output_pins[path])


def invoke_role(session,role,inputs):
    """One owned supervised process, exact reaped CHILDREN delta, no retry."""
    from scripts import strong_baseline
    import resource
    issued=session.issue(role,inputs);context=issued['context'];base=session.directory/role
    before=session.budget.usage()[1]
    exit_code=strong_baseline.run_process(issued['argv'],base/'worker.log',budget=session.budget,allocation=context['allocation'])
    after=session.budget.usage()[1];actual=after-before
    h.need(x.finite(actual),'Known reaped role CPU required')
    usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    peak=int(usage.ru_maxrss if sys.platform=='darwin' else usage.ru_maxrss*1024)
    h.need(0<peak<=x.LIMITS['worker_rss_bytes'] and peak+session.budget.usage()[2]<=x.LIMITS['job_rss_bytes'],'Reaped cumulative child/job peak exceeded')
    body,digest=x.read(local(context['output_path']));reference=dict(path=context['output_path'],sha256=digest)
    record=session.accept_receipt(body,reference,exit_code=exit_code,actual_reaped_cpu=actual)
    log=base/'worker.log';log_ref=dict(path=session.relative(log),sha256=x.sha(log,session.budget.guard))
    boundary=dict(version=1,scope='reserved_role_reaped_boundary',run_id=session.plan['run_id'],role=role,
        context=issued['context_ref'],receipt=reference,explicitly_reaped_exit_code=exit_code,
        actual_reaped_cpu_seconds=actual,cumulative_child_peak_rss_bytes=peak,
        parent_peak_rss_bytes=session.budget.usage()[2],reaped_at=now(),log=log_ref)
    saved=write_once(session.directory,role+'-reaped.json',boundary)
    session.authority_pins=merge(session.authority_pins,{saved['path']:saved['sha256'],log_ref['path']:log_ref['sha256']})
    session.budget.guard();session.marker_check()
    return record,saved


def await_external(session,prepared,name,expected):
    """Same-process wait is charged inside the original absolute deadline."""
    path=local(prepared['request']['authority_paths'][name])
    while True:
        session.budget.guard();session.marker_check()
        if path.exists():
            body,digest=x.read(path);reference=dict(path=relative(path),sha256=digest)
            required=expected(body)
            session.record_gate(name,reference,expected=required)
            return reference,deepcopy(body)
        time.sleep(.1)


def timestamp(body,earliest):
    value=body.get('sealed_at');parsed=h.utc(value)
    h.need(h.utc(earliest)<=parsed<=h.utc(now()),'Actual external authority clock differs')
    return value


def source_days(days,choice,session):
    h.need(type(days) is list and len(days)==7,'Exact seven source partitions required')
    h.need([row.get('anchor') for row in days]==list(h.DAYS),'Canonical complete source dates required')
    for row in days:
        h.keys(row,DAY_FIELDS,'Physical source day')
        h.integer(row['query_count'],0,2000,'Source Q');h.integer(row['candidate_count'],0,row['query_count']*220,'Source C')
        h.need(type(row['mature_query_count']) is int and row['mature_query_count']==row['query_count'],'Calendar source maturity differs')
        for key,file in [('queries','queries'),('candidates','candidates'),('base_features','base-features')]:
            h.need(row[key]==role_output(session,'source','day-'+row['anchor'][8:10]+'/'+file+'.parquet'),'Source day ref detached from issued output')
        if choice=='B':h.need(row['extra_features'] is None,'W=B must have no extras')
        else:h.need(row['extra_features']==role_output(session,'source','day-'+row['anchor'][8:10]+'/extra-features.parquet'),'Source extra ref detached')
    return deepcopy(days)


def unaccepted_manifest(session,role,name,fields,scope):
    reference=role_output(session,role,name);body=read_ref(reference,session.budget.guard)
    h.keys(body,fields,'Complete '+role+' manifest')
    h.need(type(body['version']) is int and body['version']==1 and body['scope']==scope and body['run_id']==session.plan['run_id'],'Role manifest identity differs')
    context=issued_for(session,role)
    for name in ['decision_lock','choice']:h.need(body[name]==context['inputs']['lock' if name=='decision_lock' else name],'Role original lock/choice ref differs')
    h.need(body['labels_loaded'] is (role=='targets_evaluation') and type(body['fit_attempt_count']) is int and body['fit_attempt_count']==0,'Manifest fit/label state differs')
    h.need(type(body['native_prediction_count']) is int and body['native_prediction_count']>=0,'Known manifest native count required')
    if role!='predictions':h.need(body['native_prediction_count']==0,'Native calls outside prediction role')
    expected={path:digest for path,digest in role_receipt(session,role)['outputs'].items() if path!=reference['path']}
    h.need(body['outputs']==expected,'Manifest omits or alters an allocated original output')
    validate_environment(session,role,body['environment'])
    if role=='source':h.need(body['source']==context['inputs']['source'],'Original source database ref differs')
    return reference,body


SOURCE_CORE_FIELDS={'version','status','scope','choice','checked_days','days','verified_outputs','source_Q_C_domain_complete',
    'chosen_columns','chosen_scalar_values','chosen_formula_values_complete','extra_proof_scope','base_proof_scope',
    'baseline_formula_values_complete','base_core18_sample_pairs','base_core18_comparisons','query_count','candidate_count',
    'mismatch_count','labels_loaded','target_relation_created','fit_attempt_count','native_prediction_count','proof_limits'}
SOURCE_CORE_DAY_FIELDS={'anchor','query_count','candidate_count','mature_query_count','empty_candidate_queries','chosen_columns',
    'chosen_scalar_values','source_Q_C_complete','metadata_ages_coverage_complete','chosen_formula_values_complete',
    'base_core18_sample_pairs','base_core18_comparisons','strata','base_proof_scope','baseline_formula_values_complete',
    'labels_loaded','target_relation_created','fit_attempt_count','native_prediction_count'}
SAMPLE_STRATA={'bottom_hash':4,'pair_view_support':1,'category_missing':1,'category_ambiguous':1,
    'past_pair_purchase_support':1,'old_recency_support':1}
SOURCE_PROOF_LIMITS='Pure caller-owned connection core; refs/source/code/lifetime are authenticated externally. Q/C and metadata/coverage/chosen0or3 values exhaustive; new-date core18 numeric values sampled. No files, models, Y, target capability, approval or resource allowance.'


def validate_source_core(core,days,choice):
    """Keep daily metadata/coverage and sampled B18 proof scope explicit."""
    h.keys(core,SOURCE_CORE_FIELDS,'Complete independent source evidence')
    h.need(type(core['version']) is int and core['version']==1 and core['scope']=='independent_reserved_source_core' and
        core['status']=='source_core_checked_pending_external_acceptance' and core['choice']==choice and
        core['verified_outputs']==days and core['checked_days']==list(h.DAYS),'Independent source oracle scope/inventory differs')
    columns=0 if choice=='B' else 3
    h.need(core['extra_proof_scope']==('no_extras_W_equals_B' if choice=='B' else 'all_selected3_values_every_C_row') and
        core['proof_limits']==SOURCE_PROOF_LIMITS,'Independent source proof limits differ')
    h.need(type(core['days']) is list and len(core['days'])==7,'Independent daily source evidence absent')
    for name in ['source_Q_C_domain_complete','chosen_formula_values_complete']:h.need(core[name] is True,'Independent complete source proof absent')
    all_rows=[core]+core['days']
    for row in all_rows:
        h.need(row['baseline_formula_values_complete'] is False and row['base_proof_scope']=='all_structure_metadata_coverage_core18_sampled','Baseline sampled scope promoted')
        for name in ['labels_loaded','target_relation_created']:h.need(row[name] is False,'Source oracle touched targets')
        for name in ['fit_attempt_count','native_prediction_count']:h.need(type(row[name]) is int and row[name]==0,'Independent source native/fit count differs')
    h.need(type(core['mismatch_count']) is int and core['mismatch_count']==0,'Independent source mismatch count differs')
    for row,day in zip(core['days'],days):
        h.keys(row,SOURCE_CORE_DAY_FIELDS,'Independent daily source scope')
        h.need(row['anchor']==day['anchor'],'Independent source day omitted/reordered')
        for name in ['query_count','candidate_count','mature_query_count']:
            h.need(type(row[name]) is int and row[name]==day[name],'Independent daily source count differs')
        for name in ['source_Q_C_complete','metadata_ages_coverage_complete','chosen_formula_values_complete']:
            h.need(row[name] is True,'Independent daily source/metadata/coverage proof absent')
        h.integer(row['empty_candidate_queries'],0,day['query_count'],'Empty-C query evidence')
        if not day['candidate_count']:h.need(row['empty_candidate_queries']==day['query_count'],'Empty-C source queries lost')
        h.need(type(row['chosen_columns']) is int and row['chosen_columns']==columns and
            type(row['chosen_scalar_values']) is int and row['chosen_scalar_values']==columns*day['candidate_count'],'Independent daily chosen closure differs')
        h.integer(row['base_core18_sample_pairs'],min(4,day['candidate_count']),min(9,day['candidate_count']),'Daily sampled B18 pairs')
        h.need(type(row['base_core18_comparisons']) is int and row['base_core18_comparisons']==18*row['base_core18_sample_pairs'],'Sampled B18 scalar comparison count differs')
        h.keys(row['strata'],SAMPLE_STRATA,'All declared sample strata')
        for name,limit in SAMPLE_STRATA.items():
            stratum=row['strata'][name];h.keys(stratum,{'available_pairs','sampled_pairs'},'Sample stratum counts')
            h.integer(stratum['available_pairs'],0,day['candidate_count'],'Available sample pairs')
            h.need(type(stratum['sampled_pairs']) is int and stratum['sampled_pairs']==min(limit,stratum['available_pairs']),'Stratified sample selection count differs')
            if name=='bottom_hash':h.need(stratum['available_pairs']==day['candidate_count'],'Bottom-hash sample domain differs')
        h.need(row['base_core18_sample_pairs']<=sum(v['sampled_pairs'] for v in row['strata'].values()),'Sample union exceeds selected strata')
    for name,expected in [('query_count',sum(d['query_count'] for d in days)),('candidate_count',sum(d['candidate_count'] for d in days)),
            ('chosen_columns',columns),('chosen_scalar_values',columns*sum(d['candidate_count'] for d in days)),
            ('base_core18_sample_pairs',sum(d['base_core18_sample_pairs'] for d in core['days'])),
            ('base_core18_comparisons',sum(d['base_core18_comparisons'] for d in core['days']))]:
        h.need(type(core[name]) is int and core[name]==expected,'Independent aggregate source count differs: '+name)
    return deepcopy(core)


def source_acceptance_expected(session,prepared,manifest_reference,manifest,body):
    h.keys(body,{'version','approved','scope','run_id','fingerprints','days','proof_limits','sealed_at'},'External source acceptance')
    core=oracle_core(session,'source_oracle');days=source_days(manifest['days'],prepared['plan']['choice'],session)
    validate_source_core(core,days,prepared['plan']['choice'])
    boundary=read_ref(dict(path=session.relative(session.directory/'source_oracle-reaped.json'),sha256=session.authority_pins[session.relative(session.directory/'source_oracle-reaped.json')]),session.budget.guard)
    sealed=timestamp(body,boundary['reaped_at'])
    return dict(version=1,approved=True,scope='reviewed_reserved_source',run_id=session.plan['run_id'],fingerprints=closure(session),
        days=days,proof_limits=core['proof_limits'],sealed_at=sealed)


ORACLE_FIELDS={'version','scope','run_id','context','execution_consumed','decision_lock','choice','inputs','core','environment'}
EVALUATION_FIELDS={'version','scope','run_id','decision_lock','choice','source_acceptance','source_manifest',
    'prediction_acceptance','prediction_inventory','target_execution','target_policy','actual_target_intent',
    'target_stage_opened_at','target_stage_started_monotonic','fullY_started_at','fullY_started_monotonic',
    'periods','private_outputs','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'}


def validate_environment(session,role,body):
    import tomllib
    h.keys(body,{'python','platform','packages','kernel_cpu','subprocess_probe'},'Observed role environment')
    h.need(body['python']==sys.version.split()[0] and body['platform']==sys.platform and body['subprocess_probe'] is False,'Observed Python/host/probe differs')
    locked={item['name']:item.get('version') for item in tomllib.loads(local('uv.lock').read_text())['package']}
    h.keys(body['packages'],{'numpy','pandas','duckdb','catboost'},'Observed loaded packages')
    for name,value in body['packages'].items():h.need(type(value) is str and value==locked.get(name),'Observed role package differs from lock')
    cap=issued_for(session,role)['allocation']['cpu_seconds'];h.keys(body['kernel_cpu'],{'soft','hard'},'Installed CPU fence')
    h.need(type(body['kernel_cpu']['soft']) is int and type(body['kernel_cpu']['hard']) is int and
        body['kernel_cpu']==dict(soft=cap-1,hard=cap),'Observed original role CPU fence differs')


def oracle_core(session,role):
    body=read_ref(role_output(session,role,'evidence.json'),session.budget.guard);h.keys(body,ORACLE_FIELDS,'Independent oracle wrapper')
    receipt=role_receipt(session,role);context=issued_for(session,role)
    h.need(type(body['version']) is int and body['version']==1 and body['scope']=='unaccepted_reserved_'+role+'_evidence' and
        body['run_id']==session.plan['run_id'],'Independent evidence wrapper identity differs')
    h.need(body['context']==receipt['context'] and body['execution_consumed']==receipt['execution_consumed'] and
        body['inputs']==context['inputs'] and body['decision_lock']==context['inputs']['lock'] and body['choice']==context['inputs']['choice'],
        'Independent wrapper original authority differs')
    validate_environment(session,role,body['environment'])
    core=body['core'];h.need(type(core) is dict and not set(core)&{'private_replayed_scores','private_targets','private_rankings'},'Only stripped aggregate oracle evidence allowed')
    return deepcopy(core)


def native_calls(days,choice):return sum(int(row['candidate_count']>0) for row in days)*(1 if choice=='B' else 2)


PREDICTION_CORE_FIELDS={'status','days','native_prediction_count','fit_attempt_count','labels_loaded','proof_scope'}
PREDICTION_CORE_DAY_FIELDS={'status','anchor','queries','candidate_pairs','native_prediction_count','fit_attempt_count','outcome_relations_opened','proof_scope'}


def validate_prediction_core(core,days,choice):
    """Require the complete all-seven observer verdict before any inventory write."""
    h.keys(core,PREDICTION_CORE_FIELDS,'Complete independent all-seven prediction evidence')
    h.need(core['status']=='independent_all_seven_scores_match_pending_owner_acceptance' and
        core['proof_scope']=='all7_independent_matrix_native_scores_rank_order_with_external_byte_lifetime_authority',
        'Independent all-seven replay status/proof differs')
    expected=native_calls(days,choice)
    h.need(core['labels_loaded'] is False and type(core['fit_attempt_count']) is int and core['fit_attempt_count']==0 and
        type(core['native_prediction_count']) is int and core['native_prediction_count']==expected,'Independent all-seven native/label/fit count differs')
    h.need(type(core['days']) is list and len(core['days'])==7,'Independent seven-date replay absent')
    for row,day in zip(core['days'],days):
        h.keys(row,PREDICTION_CORE_DAY_FIELDS,'Complete independent daily prediction evidence')
        h.need(row['anchor']==day['anchor'] and row['status']=='independent_daily_scores_match_pending_all_date_and_owner_acceptance' and
            row['proof_scope']=='independent_Q_C_F_numeric_projection_native_state_all_rawscores_complete_rank_order_no_byte_or_lifetime_authentication',
            'Independent daily replay status/calendar/proof differs')
        for name,expected_count in [('queries',day['query_count']),('candidate_pairs',day['candidate_count']),
                ('native_prediction_count',(1 if choice=='B' else 2) if day['candidate_count'] else 0),('fit_attempt_count',0),('outcome_relations_opened',0)]:
            h.need(type(row[name]) is int and row[name]==expected_count,'Independent daily typed count differs: '+name)
    return deepcopy(core)


def finish_prediction_inventory(session,prepared,source_snapshot,source_manifest_reference):
    reference,body=unaccepted_manifest(session,'predictions','prediction-manifest.json',PREDICTION_FIELDS,'unaccepted_reserved_predictions')
    context=issued_for(session,'predictions')
    h.need(body['source_acceptance']==source_snapshot['acceptance']==context['inputs']['source_acceptance'] and
        body['source_manifest']==source_manifest_reference==context['inputs']['source_manifest'],'Original prediction source differs')
    h.utc(body['created_at']);h.need(h.utc(body['created_at'])<=h.utc(now()),'Future prediction creation time')
    expected=native_calls(source_snapshot['days'],prepared['plan']['choice'])
    h.need(body['native_prediction_count']==expected and role_receipt(session,'predictions')['native_prediction_count']==expected,'Production native-call count differs')
    core=oracle_core(session,'prediction_oracle')
    validate_prediction_core(core,source_snapshot['days'],prepared['plan']['choice'])
    h.need(role_receipt(session,'prediction_oracle')['native_prediction_count']==expected,'Independent role native total differs')
    boundary=dict(version=1,scope='all_reserved_prediction_reaped_boundary',run_id=session.plan['run_id'],
        producer=next(row['receipt'] for row in session.states if row['role']=='predictions'),
        oracle=next(row['receipt'] for row in session.states if row['role']=='prediction_oracle'),
        prediction_manifest=reference,output_verification=role_output(session,'prediction_oracle','evidence.json'),
        native_calls_each_role=expected,reaped_at=now(),fingerprints=closure(session),heldout_targets_opened=False)
    boundary_ref=write_once(session.directory,'prediction-boundary.json',boundary)
    inventory=dict(version=1,scope='all_reserved_predictions_before_targets',decision_lock_sha256=h.digest(prepared['lock']),
        created_at=body['created_at'],source_acceptance=source_snapshot['acceptance'],days=deepcopy(body['days']),
        output_verification=role_output(session,'prediction_oracle','evidence.json'),lifetime_receipt=boundary_ref,heldout_targets_opened=False)
    h.validate_prediction_inventory(inventory,prepared['lock'],authenticated_source=source_snapshot)
    for row in inventory['days']:
        for role in ('B','W'):
            file='B.npz' if role=='B' or prepared['plan']['choice']=='B' else 'W.npz'
            h.need(row['predictions'][role]['artifact']==role_output(session,'predictions','day-'+row['anchor'][8:10]+'/'+file),'Prediction artifact outside issued role/day vocabulary')
    inventory_ref=write_once(session.directory,'all-predictions-inventory.json',inventory)
    session.authority_pins=merge(session.authority_pins,{ref['path']:ref['sha256'] for ref in [boundary_ref,inventory_ref]})
    return inventory,inventory_ref,boundary_ref


def prediction_acceptance_expected(session,inventory_ref,boundary_ref,body):
    h.keys(body,{'version','approved','scope','run_id','fingerprints','inventory','sealed_at'},'External prediction acceptance')
    boundary=read_ref(boundary_ref,session.budget.guard);sealed=timestamp(body,boundary['reaped_at'])
    return dict(version=1,approved=True,scope='reviewed_all_reserved_predictions_before_targets',run_id=session.plan['run_id'],
        fingerprints=closure(session),inventory=inventory_ref,sealed_at=sealed)


def create_target_policy(session,prepared,prediction_ref,prediction_body,inventory):
    value=dict(prediction_acceptance=prediction_ref,prediction_inventory_sha256=h.digest(inventory),
        decision_lock_sha256=h.digest(prepared['lock']),periods=['confirmation25_reporting_only','final26_31_frozen'],
        no_adaptation=True,earliest_opened_at=prediction_body['sealed_at'])
    ref=write_once(session.directory,'target-policy.json',value)
    session.authority_pins=merge(session.authority_pins,{ref['path']:ref['sha256']})
    return value,ref


def target_acceptance_expected(session,policy,policy_ref,body):
    h.keys(body,{'version','approved','scope','run_id','fingerprints','target_policy','sealed_at'},'External target execution authority')
    sealed=timestamp(body,policy['earliest_opened_at'])
    return dict(version=1,approved=True,scope='report_only_reserved_fullY',run_id=session.plan['run_id'],
        fingerprints=closure(session),target_policy=policy_ref,sealed_at=sealed)



def verify_evaluation(session,prepared,source_snapshot,inventory,prediction_acceptance,prediction_body,target_body,policy_ref):
    reference,body=unaccepted_manifest(session,'targets_evaluation','evaluation.json',EVALUATION_FIELDS,'unaccepted_reserved_fullY_reporting')
    context=issued_for(session,'targets_evaluation')
    for name in ['source_acceptance','source_manifest','prediction_acceptance','prediction_inventory','target_policy']:
        h.need(body[name]==context['inputs'][name],'Original evaluation input differs: '+name)
    h.need(body['target_execution']==context['authorities']['target_execution'] and body['target_policy']==policy_ref,'Original late target grant differs')
    intent=h.validate_target_intent(body['actual_target_intent'],prepared['lock'],inventory,
        authenticated_prediction_acceptance=prediction_acceptance)
    admission=body['target_stage_opened_at'];h.need(admission==intent['opened_at'],'Actual target stage/intent clocks differ')
    h.need(h.utc(admission)>max(h.utc(prediction_body['sealed_at']),h.utc(target_body['sealed_at'])) and
        h.utc(admission)<=h.utc(body['fullY_started_at'])<=h.utc(now()),'Actual target/fullY UTC chronology differs')
    begin,end=body['target_stage_started_monotonic'],body['fullY_started_monotonic']
    receipt=role_receipt(session,'targets_evaluation')
    h.need(x.finite(begin) and x.finite(end) and context['issued_at_monotonic']<=receipt['started_monotonic']<=begin<=end<=receipt['finished_monotonic'],
        'Actual target/fullY original monotonic chronology differs')
    h.keys(body['private_outputs'],{'targets','rankings'},'Original private evaluation outputs')
    h.need(body['private_outputs']['targets']==role_output(session,'targets_evaluation','full-targets.parquet') and
        body['private_outputs']['rankings']==role_output(session,'targets_evaluation','private-rankings.jsonl'),'Private target/ranking output refs differ')
    h.keys(body['periods'],{'confirmation25_reporting_only','final26_31_frozen'},'Both fixed reporting windows')
    for name,days in [('confirmation25_reporting_only',source_snapshot['days'][:1]),('final26_31_frozen',source_snapshot['days'][1:])]:
        period=body['periods'][name]
        h.need(period['anchors']==[day['anchor'] for day in days] and
            period['support']['query_count']==sum(day['query_count'] for day in days) and
            period['support']['candidate_pairs']==sum(day['candidate_count'] for day in days),'Complete evaluation window domain differs')
    return reference,body


def verify_metric_evidence(session,evaluation,prediction_body,target_body):
    from tests.oracles import heldout_metric_audit
    core=oracle_core(session,'metric_oracle')
    h.keys(core,{'status','periods','fullY_pairs','fit_attempt_count','native_prediction_count','bootstrap_replicates_per_estimand','proof_scope',
        'oracle_target_stage_opened_at','oracle_target_stage_started_monotonic','oracle_fullY_started_at','oracle_fullY_started_monotonic',
        'private_ranking_rows_checked'},'Complete independent metric/private-output evidence')
    h.need(core['status']=='independent_core_values_match_pending_owner_acceptance' and
        type(core['fit_attempt_count']) is int and core['fit_attempt_count']==0 and
        type(core['native_prediction_count']) is int and core['native_prediction_count']==0 and
        type(core['bootstrap_replicates_per_estimand']) is int and core['bootstrap_replicates_per_estimand']==200 and
        core['proof_scope']=='raw_fullY_all_queries_all_scores_four_estimands_every_fixed_user_draw_no_lifetime_or_byte_authentication',
        'Independent fullY/metric audit scope differs')
    heldout_metric_audit.compare(evaluation['periods'],core['periods'])
    support=[period['support'] for period in evaluation['periods'].values()]
    h.need(type(core['fullY_pairs']) is int and core['fullY_pairs']==sum(row['target_pairs'] for row in support),
        'Independent fullY complete target count differs')
    h.need(type(core['private_ranking_rows_checked']) is int and core['private_ranking_rows_checked']==2*sum(row['query_count'] for row in support),
        'Independent private ranking all-query comparison absent')
    admission=core['oracle_target_stage_opened_at'];full=core['oracle_fullY_started_at']
    h.need(h.utc(admission)>max(h.utc(prediction_body['sealed_at']),h.utc(target_body['sealed_at'])) and
        h.utc(admission)<=h.utc(full)<=h.utc(now()),'Actual independent target/fullY UTC chronology differs')
    begin,end=core['oracle_target_stage_started_monotonic'],core['oracle_fullY_started_monotonic']
    context=issued_for(session,'metric_oracle');receipt=role_receipt(session,'metric_oracle')
    h.need(x.finite(begin) and x.finite(end) and context['issued_at_monotonic']<=receipt['started_monotonic']<=begin<=end<=receipt['finished_monotonic'],
        'Actual independent target/fullY original monotonic chronology differs')
    return deepcopy(core)


def preparation_failure(consumed,error):
    if consumed is None:return
    body=dict(version=1,status='failed_preparation',request=consumed['request_ref'],owner_claim=consumed['owner_claim'],
        error_type=type(error).__name__,error='STOP original consumed owner; no retry/refill/adaptation',
        fit_attempt_count=0,reserved_targets_may_have_been_opened=False)
    try:write_once(consumed['directory'],'report.failed.json',body)
    except BaseException as secondary:error.add_note('Owner preparation failure persistence: '+type(secondary).__name__)


def run_owner(request_path):
    """The sole production sequence: paid plan, four external gates, six roles."""
    budget=x.Budget(started=ENTRY_MONOTONIC);consumed=session=None
    try:
        consumed=consume_owner(request_path,budget);prepared=prepare_owner(consumed,budget)
        session=x.Session(ROOT,relative(prepared['directory']),prepared['plan'],prepared['request_ref'],prepared['owner_claim'],budget)
        initial=lambda body:dict(version=1,approved=True,scope='reserved_source_inference_execution',run_id=session.plan['run_id'],fingerprints=session.plan['fingerprints'])
        await_external(session,prepared,'initial_execution',initial)
        common=dict(lock=prepared['lock_ref'],choice=prepared['choice_ref'])
        source_inputs=dict(common,**prepared['request']['source_inputs'])
        invoke_role(session,'source',source_inputs)
        source_manifest_ref,source_manifest=unaccepted_manifest(session,'source','source-manifest.json',SOURCE_FIELDS,'unaccepted_reserved_source')
        source_days(source_manifest['days'],prepared['plan']['choice'],session)
        source_receipt=next(row['receipt'] for row in session.states if row['role']=='source')
        invoke_role(session,'source_oracle',dict(source_inputs,source_manifest=source_manifest_ref,source_receipt=source_receipt))
        source_ref,source_body=await_external(session,prepared,'source_acceptance',
            lambda body:source_acceptance_expected(session,prepared,source_manifest_ref,source_manifest,body))
        source_snapshot=dict(acceptance=source_ref,days=deepcopy(source_body['days']))
        prediction_inputs=dict(common,source_acceptance=source_ref,source_manifest=source_manifest_ref)
        invoke_role(session,'predictions',prediction_inputs)
        prediction_manifest_ref=role_output(session,'predictions','prediction-manifest.json')
        prediction_receipt=next(row['receipt'] for row in session.states if row['role']=='predictions')
        invoke_role(session,'prediction_oracle',dict(prediction_inputs,prediction_manifest=prediction_manifest_ref,prediction_receipt=prediction_receipt))
        inventory,inventory_ref,boundary_ref=finish_prediction_inventory(session,prepared,source_snapshot,source_manifest_ref)
        prediction_ref,prediction_body=await_external(session,prepared,'prediction_acceptance',
            lambda body:prediction_acceptance_expected(session,inventory_ref,boundary_ref,body))
        prediction_acceptance=dict(reference=prediction_ref,inventory_sha256=h.digest(inventory),decision_lock_sha256=h.digest(prepared['lock']))
        policy,policy_ref=create_target_policy(session,prepared,prediction_ref,prediction_body,inventory)
        target_ref,target_body=await_external(session,prepared,'target_execution',
            lambda body:target_acceptance_expected(session,policy,policy_ref,body))
        target_inputs=dict(prediction_inputs,prediction_acceptance=prediction_ref,prediction_inventory=inventory_ref,target_policy=policy_ref)
        invoke_role(session,'targets_evaluation',target_inputs)
        evaluation_ref,evaluation=verify_evaluation(session,prepared,source_snapshot,inventory,prediction_acceptance,prediction_body,target_body,policy_ref)
        evaluation_receipt=next(row['receipt'] for row in session.states if row['role']=='targets_evaluation')
        invoke_role(session,'metric_oracle',dict(target_inputs,evaluation_manifest=evaluation_ref,evaluation_receipt=evaluation_receipt))
        verified=verify_metric_evidence(session,evaluation,prediction_body,target_body)
        session.report.update(aggregate_periods=deepcopy(evaluation['periods']),independent_fullY_pairs=verified['fullY_pairs'],
            decision_lock=prepared['lock_ref'],source_acceptance=source_ref,prediction_acceptance=prediction_ref,target_execution=target_ref,
            fit_attempt_count=0,reporting_policy='confirmation25_reporting_only_and_final26_31_frozen_no_adaptation',
            full_owner_exit_tail_acceptance_required=True)
        return session.finish()
    except BaseException as error:
        if session is not None:
            if session.report.get('status')!='failed':session.fail(error)
        else:preparation_failure(consumed,error)
        raise


def main():
    import argparse
    parser=argparse.ArgumentParser(description='One consumed frozen reserved-reporting owner; requires reviewed exact request/gates.')
    parser.add_argument('--request',required=True)
    args=parser.parse_args();run_owner(args.request)


if __name__=='__main__':main()
