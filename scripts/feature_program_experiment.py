"""Prospective fixed-procedure feature-program experiment; no fit permission.

Exact external approval, accepted source and independent output review are
required. A global four-slot claim prevents replacement fits or destinations.
"""
import time
ENTRY_MONOTONIC=time.monotonic()
from copy import deepcopy
import math
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
ROLE="fixed_procedure_feature_program_experiment"
CLAIM="artifacts/feature-program-study/four-fit.claim.json"
OWNER_CLAIM="artifacts/feature-program-study/fit-owner.claim.json"
ORACLE="tests/oracles/feature_program_model_audit.py"
CODE=("scripts/feature_program_experiment.py","scripts/model_data.py",
      "scripts/program_model_data.py","scripts/strong_control.py",
      "scripts/recovered_feature_source.py","scripts/ranking_metrics.py",ORACLE,"uv.lock")

IDS=('B','I1','I2','R1','R2')
LIMITS=dict(shared_cpu_seconds=7200,fit_wall_seconds=3600,verification_cpu_reserve=600,
    verification_wall_reserve=600,parent_launch_cpu_reserve=60,cleanup_wall_reserve=20,
    parent_rss_bytes=2**30,worker_rss_bytes=7*2**30,whole_job_rss_bytes=8*2**30,
    term_grace_seconds=5,kill_reap_seconds=5,log_bytes=2**20)


def _finite(value):return type(value) in (int,float) and math.isfinite(value)


def choose(candidates):
    """One global NDCG band; source/model/score authority belongs to the caller.

    All five allocated identities must be represented. Known failed/colliding
    arms retain their consumed slot and no eligible metrics. Missing/unattempted
    or integrity/API/unknown states are incomplete evidence and cause STOP.
    """
    if type(candidates) is not list or len(candidates)!=5:raise ValueError('All five original candidate identities required')
    by_id={}
    for c in candidates:
        if type(c) is not dict or not {'candidate_id','status','added_physical_columns','metrics'}<=set(c):
            raise ValueError('Candidate physical/status/metric schema differs')
        cid=c['candidate_id']
        if cid not in IDS or cid in by_id:raise ValueError('Duplicate or substituted allocated identity')
        if type(c['added_physical_columns']) is not int or c['added_physical_columns']!=(0 if cid=='B' else 3):
            raise ValueError('Tie complexity counts physical columns including masks')
        status=c['status']
        if status not in {'verified_success','resource_failed','allocation_collision'}:
            raise ValueError('Incomplete/integrity/API/unknown candidate causes STOP')
        if cid=='B' and status!='verified_success':raise ValueError('Accepted unchanged B must be available')
        if status!='verified_success':
            if c['metrics'] is not None:raise ValueError('Failed arms cannot supply eligible metrics')
        else:
            if type(c['metrics']) is not dict or type(c['metrics'].get('conditional_macro_query')) is not dict:
                raise ValueError('Verified full-Y conditional metrics required')
            for name in ['ndcg','recall']:
                value=c['metrics']['conditional_macro_query'].get(name)
                if not _finite(value) or not 0<=value<=1:raise ValueError('Missing/nonfinite/out-of-range development metric')
        by_id[cid]=c
    if set(by_id)!=set(IDS):raise ValueError('Original allocation cover differs')
    floor=by_id['B']['metrics']['conditional_macro_query']['recall']-.002
    feasible=[c for c in by_id.values() if c['status']=='verified_success'
        and c['metrics']['conditional_macro_query']['recall']>=floor]
    maximum=max(c['metrics']['conditional_macro_query']['ndcg'] for c in feasible)
    band=[c for c in feasible if c['metrics']['conditional_macro_query']['ndcg']>=maximum-1e-12]
    winner=min(band,key=lambda c:(c['added_physical_columns'],c['candidate_id']))
    return deepcopy(winner)


def frozen_model_parameters(control):
    """Construct exactly the inherited training procedure; no new tuning."""
    spec=control['selected_spec'];native=control['actual_model_parameters']
    for key in ['population','trained_iterations','scoring_prefix','depth','l2_leaf_reg']:
        if type(spec.get(key)) is not int or spec[key]<1:raise ValueError('Typed accepted procedure required')
    if spec['population'] not in (6000,26000) or not spec['scoring_prefix']<=spec['trained_iterations']:
        raise ValueError('Inherited population/trained/scoring contract differs')
    fixed=dict(loss_function='Logloss',iterations=spec['trained_iterations'],depth=spec['depth'],
        l2_leaf_reg=spec['l2_leaf_reg'],random_seed=2026,task_type='CPU',boosting_type='Plain',bootstrap_type='No',
        leaf_estimation_method='Newton',leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',
        random_strength=1,boost_from_average=False,use_best_model=False)
    for key,value in fixed.items():
        if type(native.get(key)) is not type(value) or native[key]!=value:
            raise ValueError('Accepted native procedure differs: '+key)
    # Accepted native LR is CatBoost's float32 conversion of declared.05.
    import struct
    effective=struct.unpack('!f',struct.pack('!f',.05))[0]
    if type(native.get('learning_rate')) is not float or not math.isclose(native['learning_rate'],effective,rel_tol=1e-8,abs_tol=1e-12):
        raise ValueError('Accepted native learning rate differs from declared.05')
    if (native.get('border_count')!=254 or native.get('nan_mode')!='Min' or native.get('rsm')!=1):
        raise ValueError('Inherited numeric representation parameters differ')
    return dict(fixed,learning_rate=.05,thread_count=2,border_count=254,nan_mode='Min',rsm=1,
                verbose=False,allow_writing_files=False)


class Budget:
    """Actual source prefix plus one fresh fit owner's absolute CPU counters.

    `self_cpu` and `children_cpu` are the accepted canonical resource readers.
    A worker's self report is never added to reaped CHILDREN a second time.
    """
    def __init__(self,source_paid_cpu,*,self_cpu,children_cpu,rss,started=ENTRY_MONOTONIC):
        if not _finite(source_paid_cpu) or not 0<=source_paid_cpu<=1800:
            raise ValueError('Known successful source+oracle actual CPU prefix required')
        self.source_paid_cpu=source_paid_cpu;self.self_cpu=self_cpu;self.children_cpu=children_cpu;self.rss=rss
        self.started=started;self.verifying=False;self.limits=deepcopy(LIMITS);self.outer_deadline=started+LIMITS['fit_wall_seconds']
        self.producer_deadline=self.outer_deadline-LIMITS['verification_wall_reserve']
    def cpu(self):
        a,b=self.self_cpu(),self.children_cpu()
        if not _finite(a) or not _finite(b) or a<0 or b<0:raise ValueError('Unknown canonical fit-owner resource usage')
        return self.source_paid_cpu+a+b
    def guard(self):
        if self.cpu()>LIMITS['shared_cpu_seconds']-(2 if self.verifying else LIMITS['verification_cpu_reserve']):
            raise TimeoutError('Shared actual7200 CPU producer allowance exhausted')
        if time.monotonic()>(self.outer_deadline-LIMITS['cleanup_wall_reserve'] if self.verifying else self.producer_deadline):raise TimeoutError('Fit owner original absolute wall deadline exhausted')
        peak=self.rss()
        if type(peak) is not int or peak<=0:raise ValueError('Unknown parent RSS')
        if peak>LIMITS['parent_rss_bytes']:raise MemoryError('Fit owner parent RSS exceeds1GiB')
    def allocation(self):
        self.guard()
        remaining=LIMITS['shared_cpu_seconds']-self.cpu()-(0 if self.verifying else LIMITS['verification_cpu_reserve'])-LIMITS['parent_launch_cpu_reserve']
        if self.verifying:remaining=min(LIMITS['verification_cpu_reserve'],remaining)
        deadline=(min(self.outer_deadline,time.monotonic()+LIMITS['verification_wall_reserve']) if self.verifying else self.producer_deadline)-LIMITS['cleanup_wall_reserve']
        if remaining<1 or deadline<=time.monotonic():raise TimeoutError('No supervised paid worker allowance remains')
        return dict(cpu_seconds=int(remaining),deadline_monotonic=deadline,rss_bytes=LIMITS['worker_rss_bytes'])


# The orchestration below is prospective WIP until its exact code and observer
# receive independent review. It exposes no unapproved standalone fit function.
def _need(value,message):
    if not value:raise ValueError(message)


def _canonical(body):return json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def _digest(body):return hashlib.sha256(_canonical(body).encode()).hexdigest()
def _relative(path):return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
def _local(name):
    _need(type(name) is str and name and not Path(name).is_absolute() and '..' not in Path(name).parts and '\\' not in name,'Nonlocal experiment artifact')
    path=(ROOT/name).resolve();path.relative_to(ROOT.resolve());return path


def _read(path):
    with Path(path).open('rb') as handle:raw=handle.read(8*2**20+1)
    _need(len(raw)<=8*2**20,'Experiment receipt exceeds bounded metadata size')
    def pairs(values):
        result={}
        for key,value in values:
            _need(key not in result,'Duplicate experiment JSON key');result[key]=value
        return result
    body=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite experiment JSON')))
    return body,hashlib.sha256(raw).hexdigest()



def _read_ref(ref):
    _need(type(ref) is dict and set(ref)=={'path','sha256'},'Exact issuer reference required')
    body,digest=_read(_local(ref['path']))
    _need(type(ref['sha256']) is str and digest==ref['sha256'],'Parsed receipt snapshot differs from issuer reference')
    return body

def _sha(path,check=lambda:None):
    h=hashlib.sha256();check()
    with Path(path).open('rb') as handle:
        while part:=handle.read(4*2**20):check();h.update(part)
    check();return h.hexdigest()


def _pins(mapping,check=lambda:None):
    _need(type(mapping) is dict,'Exact fingerprint object required')
    for name,digest in mapping.items():
        _need(type(digest) is str and len(digest)==64,'Invalid pinned SHA256')
        _need(_sha(_local(name),check)==digest,'Pinned experiment source/output changed')



def _exclusive_json(path,body):
    """Exclusive persisted issuance; retain SHA of the exact written bytes."""
    raw=(_canonical(body)+'\n').encode('utf-8')
    with Path(path).open('xb') as handle:
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    descriptor=os.open(Path(path).parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()

def _write(path,body):
    from scripts import metadata_price_collection as mechanics
    mechanics._atomic_json(path,body)


def _self_cpu():
    r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime

def _children_cpu():
    r=resource.getrusage(resource.RUSAGE_CHILDREN);return r.ru_utime+r.ru_stime

def _rss():
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value*1024 if sys.platform.startswith('linux') else value)


def validate_selector(body):
    _need(type(body) is dict and body.get('candidate_ids')==list(IDS),'Frozen five-way selector candidates differ')
    expected=dict(version=1,role='prospective_bounded_feature_program_selection',candidate_ids=list(IDS),
        added_physical_columns={name:0 if name=='B' else 3 for name in IDS},
        shared_model_contract='accepted019_population_weights_settings_trained_iterations_and_scoring_prefix',
        objective=dict(metric='ndcg',k=20,estimand='conditional_macro_query',targets='full_Y_independent_of_C'),
        feasibility=dict(metric='recall',k=20,estimand='conditional_macro_query',reference='B',minimum_delta=-.002,boundary='inclusive'),
        tie=dict(global_maximum_absolute_band=1e-12,order=['fewer_added_physical_columns_including_masks','lexicographic_candidate_id']),
        failure=dict(known_resource_failure='paid_consumed_ineligible',integrity_api_or_unknown_usage='STOP',collision='consumed_ineligible',refill=False),
        primary_comparison=dict(chosen_candidate='W_may_equal_B',reference='B',freeze_before='reserved_query_targets_and_metrics_open',
            heldout_policy='same_frozen_models_programs_and_predictions_no_refit_or_adaptation'),
        strategy_comparison='best_two_I_minus_best_two_R_descriptive_screening_only',
        random_winner_interpretation='mixed_typed_automation_not_rule_guided_superiority',
        permissions=dict(new_fit_budget=0,actual_execution_approved=False))
    _need(_canonical(body)==_canonical(expected),'Prospective selector differs from published contract')
    return deepcopy(body)


def prepare_plan(source_acceptance,control_acceptance,selector_path,*,check=lambda:None):
    from scripts import recovered_feature_source as source
    from scripts import strong_control
    from scripts import metadata_price_collection as mechanics
    selector,selector_sha=_read(selector_path);validate_selector(selector)
    accepted=source.verify_source_acceptance(source_acceptance,check=check)
    control=strong_control.verify_control(control_acceptance,check=check)
    check();spec=deepcopy(control['selected_spec']);params=frozen_model_parameters(control)
    collections=accepted['collections'];selected=accepted['selected_union'];manifest=accepted['manifest']
    _need(set(collections)=={'train','selection'} and accepted['physical']==dict(status='independently_verified_all_rows',source_formula_acceptance=True),
          'Independent complete recovered source required')
    for role in ['train','selection']:
        _need(_relative(_local(control['acceptance_refs'][role]))==manifest['identity']['acceptance_refs'][role],
              'Source/control accepted base collections differ')
    _need(len(control['feature_names'])==41 and [v['name'] for v in accepted['pool']['identity']['base_model_schema']]==control['feature_names'],
          'Source/control B41 model schema differs')
    declared={r['slot']:r for r in accepted['allocation']['identity']['slots']}
    _need(set(declared)==set(IDS[1:]) and [declared[k]['bundle_id'] for k in IDS[1:]]==['L02','L06','L01','L05'],
          'Exact original four-slot allocation required')
    slots={};delta_types={field['name']:field['dtype'] for field in selected['physical_delta']}
    for name in IDS[1:]:
        arm=selected['arms'][name]
        _need(declared[name]['status']=='planned_unexecuted' and arm['status']=='planned_unexecuted' and len(arm['columns'])==3
            and len(set(arm['columns']))==3 and arm['model_feature_order']==[*control['feature_names'],*arm['columns']],
            'Each original slot must append exact3 physical columns in approved order')
        slots[name]=dict(candidate_id=name,bundle_id=arm['bundle_id'],columns=arm['columns'],
            physical_delta=[dict(name=n,dtype=delta_types[n]) for n in arm['columns']],feature_names=arm['model_feature_order'])
    first=manifest['outputs']['train'][0]['artifacts']['features']['schema']
    _need(len(first)==57 and all(part['artifacts']['features']['schema']==first for parts in manifest['outputs'].values() for part in parts),
          'Every accepted F57 source schema must agree')
    names=control['feature_names'];winner=control['winner']
    baseline=dict(candidate_id='B',status='verified_success',added_physical_columns=0,metrics=winner['metrics'],
        model_path=spec['model_path'],score_path=spec['score_path'],feature_names=names)
    paid=accepted['paid_source_cpu_seconds'];_need(_finite(paid) and 0<=paid<=1800,'Verified measured source lifetime required')
    pins=mechanics.merge_pins(accepted['pins'],control['pins'],
        {accepted['acceptance']['path']:accepted['acceptance']['sha256'],control['acceptance']['path']:control['acceptance']['sha256'],_relative(selector_path):selector_sha})
    for name in CODE:check();pins=mechanics.merge_pins(pins,{name:_sha(_local(name),check)})
    _need(_sha(selector_path,check)==selector_sha,'Selector changed during plan preparation')
    identity=dict(version=1,role=ROLE,limits=deepcopy(LIMITS),fingerprints=pins,
        source_run_id=manifest['run_id'],source_acceptance=_relative(source_acceptance),control_acceptance=_relative(control_acceptance),
        selector=selector,selector_path=_relative(selector_path),model_spec=spec,model_parameters=params,
        native_reference=control['actual_model_parameters'],baseline=baseline,feature_names=names,slots=slots,
        accepted_base_refs={r:manifest['identity']['acceptance_refs'][r] for r in ['train','selection']},
        collection_ids={r:collections[r]['plan']['collection_id'] for r in ['train','selection']},
        daily_features=accepted['daily_features'],expected_source_schema=first,paid_source_cpu_seconds=paid,
        environment=control['manifest']['identity']['environment'],
        interpretation='fixed_learner_conditional_feature_program_contrast_development_selection_not_heldout_quality',
        heldout_labels_opened=False,oracle_source=dict(path=ORACLE,sha256=pins[ORACLE]))
    return dict(run_id=_digest(identity),identity=identity)


def validate_native(actual,parent):
    """Strict inherited numeric CPU procedure; loaded LR serialization tolerant."""
    proxy=dict(selected_spec=parent['identity']['model_spec'],actual_model_parameters=actual)
    frozen_model_parameters(proxy)
    _need(actual.get('eval_metric')=='Logloss' and actual.get('auto_class_weights')=='None'
          and actual.get('grow_policy')=='SymmetricTree' and actual.get('feature_border_type')=='GreedyLogSum',
          'Unchanged inherited native defaults required')
    return deepcopy(actual)


def verify_environment(expected):
    """Loaded/installed/locked versions and supported host, with no subprocess."""
    import os,tomllib
    from importlib.metadata import version
    import catboost,duckdb,numpy,pandas
    packages=tomllib.loads((ROOT/'uv.lock').read_text())['package']
    loaded={name:module.__version__ for name,module in [('catboost',catboost),('duckdb',duckdb),('numpy',numpy),('pandas',pandas)]}
    _need(expected['loaded_packages']==loaded and expected['python']==sys.version,'Inherited loaded environment changed')
    for name,value in loaded.items():_need([p['version'] for p in packages if p['name']==name]==[value] and version(name)==value,'Loaded/installed/locked version differs')
    uname=os.uname()
    if sys.platform=='darwin':
        # os.uname is in process; avoid platform.platform's diagnosed uname/file children.
        import plistlib,struct
        product=plistlib.loads(Path('/System/Library/CoreServices/SystemVersion.plist').read_bytes())['ProductVersion']
        _need(uname.machine=='arm64' and struct.calcsize('P')==8 and expected['platform']=='macOS-'+product+'-arm64-arm-64bit',
              'Current study requires the inherited in-process DarwinARM64 product version')
    else:raise ValueError('Current historical study does not claim other host support')
    return dict(python=sys.version,loaded_packages=loaded,os_sysname=uname.sysname,os_release=uname.release,os_machine=uname.machine,
                subprocesses_started=0,scope='loaded_versions_and_reviewed_host_family_no_platform_platform')


def verify_worker_context(path,*,issued_context_sha256):
    context,context_sha=_read(path);_need(type(issued_context_sha256) is str and context_sha==issued_context_sha256,'Context differs from original issuer snapshot');_need(set(context)=={'version','parent_plan','slot'} and type(context['version']) is int and context['version']==1,'Exact worker context required')
    parent=_read_ref(context['parent_plan']);identity=parent['identity']
    _need(set(parent)=={'run_id','identity','execution_approval','budget_claim'} and identity['role']==ROLE and _digest(identity)==parent['run_id'],
          'Approved exact parent identity required')
    _need(_canonical(identity['limits'])==_canonical(LIMITS),'Parent limits differ')
    validate_selector(identity['selector']);approval=parent['execution_approval'];body=_read_ref(approval)
    _need(_canonical(body)==_canonical(dict(version=1,approved=True,scope=ROLE,run_id=parent['run_id'],fingerprints=identity['fingerprints'])),
          'Exact external fit approval required')
    claim=parent['budget_claim'];_need(claim['path']==CLAIM,'Global immutable four-fit claim required');original=_read_ref(claim);directory=_local(context['parent_plan']['path']).parent
    expected=dict(version=1,scope=ROLE,run_id=parent['run_id'],allowed_fit_attempts=4,allowed_metric_looks=4,allowed_observer_attempts=1,oracle_source=identity['oracle_source'],no_refill=True,
        output_directory=_relative(directory),execution_approval=approval,slot_paths=[_relative(directory/'slots'/(n+'.json')) for n in IDS[1:]])
    _need(_canonical(original)==_canonical(expected) and context['slot']['path'] in expected['slot_paths'],'Original complete allocation claim differs')
    slot=_read_ref(context['slot']);cid=slot['candidate_id']
    _need(set(slot)=={'version','parent_run_id','candidate_id','token','allocation','context_path','output_root','look_reservations'}
        and type(slot['version']) is int and slot['version']==1 and cid in IDS[1:]
        and context['slot']['path']==_relative(directory/'slots'/(cid+'.json')) and slot['parent_run_id']==parent['run_id']
        and slot['context_path']==_relative(path) and slot['output_root']==_relative(directory/'workers'/cid),
        'Worker belongs to exact original issued slot/output')
    _need(type(slot['token']) is str and len(slot['token'])==32 and all(c in '0123456789abcdef' for c in slot['token']),'Invalid issued token')
    _need(_canonical(slot['look_reservations'])==_canonical([identity['model_spec']['scoring_prefix']]),'Exactly one inherited prefix look allowed')
    a=slot['allocation'];_need(set(a)=={'cpu_seconds','deadline_monotonic','rss_bytes'} and type(a['cpu_seconds']) is int and 1<=a['cpu_seconds']<=6540
        and type(a['rss_bytes']) is int and a['rss_bytes']==7*2**30 and _finite(a['deadline_monotonic'])
        and time.monotonic()<a['deadline_monotonic']<=time.monotonic()+3600,'Issued absolute worker allowance differs')
    _need(identity['model_parameters']==frozen_model_parameters(dict(selected_spec=identity['model_spec'],actual_model_parameters=identity['native_reference'])),
          'Inherited fixed training procedure changed')
    return parent,slot,context


def _resource_failure(error):
    import duckdb
    return isinstance(error,(MemoryError,TimeoutError,duckdb.OutOfMemoryException))



def matrix_proof(data,*,weights=None,check=lambda:None):
    """Canonical bounded-chunk input witness; actual fit usage needs code proof."""
    import numpy as np
    fields={}
    for name in ['x','group','items','y']:
        value=getattr(data,name);h=hashlib.sha256()
        for start in range(0,len(value),65536):
            check();part=np.array(value[start:start+65536],copy=True,order='C')
            if name=='x':part[np.isnan(part)]=np.float32(np.nan)
            h.update(memoryview(part).cast('B'))
        fields[name]=dict(shape=list(value.shape),dtype=value.dtype.str,sha256=h.hexdigest())
    if weights is not None:
        h=hashlib.sha256()
        for start in range(0,len(weights),65536):check();h.update(memoryview(np.ascontiguousarray(weights[start:start+65536])).cast('B'))
        fields['weights']=dict(shape=list(weights.shape),dtype=weights.dtype.str,sha256=h.hexdigest())
    queries=[dict(query_id=q,user_id=u,anchor=a.isoformat(),targets=sorted(targets)) for q,u,a,targets in data.queries]
    check();return dict(version=1,feature_names=list(data.feature_names),queries_sha256=_digest(queries),query_count=len(queries),
        arrays=fields,scope='canonical_input_value_witness_not_native_fit_weight_recovery')

def worker_main(path,*,issued_context_sha256):
    """One consumed slot, one fixed fit, one inherited-prefix metric look."""
    parent,slot,context=verify_worker_context(path,issued_context_sha256=issued_context_sha256)
    allocation=slot['allocation'];identity=parent['identity'];cid=slot['candidate_id'];arm=identity['slots'][cid]
    def guard():
        _need(_children_cpu()==0,'Worker spawned forbidden subprocess or has unknown descendants')
        if _self_cpu()>allocation['cpu_seconds']:raise TimeoutError('Worker absolute entry CPU allowance exhausted')
        if time.monotonic()>allocation['deadline_monotonic']:raise TimeoutError('Original issued worker deadline exhausted')
        if _rss()>allocation['rss_bytes']:raise MemoryError('Worker RSS exceeds7GiB')
    guard();consumed=_local(context['slot']['path']).with_suffix('.consumed.json')
    consumed_body=dict(version=1,parent_run_id=parent['run_id'],candidate_id=cid,token=slot['token'],context_sha256=issued_context_sha256,
        allowed_fit_attempts=1,allowed_metric_looks=1)
    consumed_sha=_exclusive_json(consumed,consumed_body)
    worker_identity=dict(version=1,role=ROLE+'_worker',parent_plan=context['parent_plan'],slot=context['slot'],
        issued_context=dict(path=_relative(path),sha256=issued_context_sha256),consumed=dict(path=_relative(consumed),sha256=consumed_sha),
        candidate=arm,procedure=identity['model_spec'])
    worker_id=_digest(worker_identity);directory=_local(slot['output_root'])/worker_id;directory.mkdir(parents=True,exist_ok=False)
    manifest=dict(run_id=worker_id,identity=worker_identity,outputs={})
    look=dict(prefix=identity['model_spec']['scoring_prefix'],status='reserved_consumed')
    report=dict(version=1,status='running',scope=ROLE+'_worker',run_id=worker_id,parent_run_id=parent['run_id'],
        candidate_id=cid,bundle_id=arm['bundle_id'],added_columns=arm['columns'],physical_delta=arm['physical_delta'],feature_names=arm['feature_names'],
        fit_attempt_count=0,look_reservations=[look],labels_loaded=False,started_monotonic=ENTRY_MONOTONIC,
        allocation=allocation,outcome='preparing',stages=[])
    primary=None
    def stage(name,operation):
        guard();before=_self_cpu();started=time.monotonic();item=dict(stage=name,status='running');report['stages'].append(item)
        _write(directory/'report.json',report)
        try:
            value=operation();guard();item['status']='complete';return value
        except BaseException as error:item.update(status='failed',error_type=type(error).__name__);raise
        finally:
            item.update(cpu_seconds=_self_cpu()-before,seconds=time.monotonic()-started);_write(directory/'report.json',report)
    _write(directory/'report.json',report)
    try:
        from dataclasses import asdict
        from catboost import CatBoostClassifier,Pool
        import numpy as np
        from scripts import model_data,program_model_data,train_baselines as base
        from scripts import metadata_price_collection as mechanics
        from scripts.ranking_metrics import evaluate
        report['environment']=stage('verify_loaded_runtime_without_subprocess',lambda:verify_environment(identity['environment']))
        stage('verify_approved_source_bytes',lambda:_pins(identity['fingerprints'],guard))
        refs=identity['accepted_base_refs'];collections={role:stage('verify_accepted_'+role,
            lambda role=role:mechanics.verify_collection_strict(_local(refs[role]),check=guard)) for role in ['train','selection']}
        for role,col in collections.items():_need(col['plan']['collection_id']==identity['collection_ids'][role],'Worker accepted base collection changed')
        population=identity['model_spec']['population'];report['labels_loaded']=True
        train=stage('fixed_B41_train_matrix',lambda:model_data.prepare_model_data(collections['train'],max_queries=population,max_rows=population*220,check=guard))
        _need(len(train.queries)==population and train.feature_names==identity['feature_names'] and train.categorical is None,'Inherited complete train population/B41 differs')
        train=stage('append_only_accepted_three_train_columns',lambda:program_model_data.append_program_features(train,identity['daily_features']['train'],
            extra_columns=arm['physical_delta'],expected_source_schema=identity['expected_source_schema'],check=guard))
        _need(train.feature_names==arm['feature_names'],'Exact B41+3 feature order differs')
        _,_,_,_,weights,summary=base.group_accounting(train)
        _need(np.unique(train.y).size==2,'Two-class training support required')
        report.update(training=summary,train_preparation=train.preparation,train_matrix_proof=matrix_proof(train,weights=weights,check=guard))
        pool=stage('fixed_query_mass_native_Pool',lambda:Pool(train.x,label=train.y,weight=weights,feature_names=train.feature_names,thread_count=2))
        model=CatBoostClassifier(**identity['model_parameters']);callback=base._BudgetCallback(guard)
        def fit():
            report['fit_attempt_count']=1;_write(directory/'report.json',report)
            model.fit(pool,callbacks=[callback])
            if callback.failure is not None:raise callback.failure
            _need(model.tree_count_==identity['model_spec']['trained_iterations'] and model.feature_names_==arm['feature_names'],
                  'Incomplete inherited trained iterations/model feature schema')
        stage('one_fixed_procedure_fit',fit)
        actual=stage('verify_native_inherited_parameters',lambda:validate_native(model.get_all_params(),parent))
        # Release native training preparation before constructing selection.
        del pool,weights,train
        selection=stage('fixed_B41_selection_matrix',lambda:model_data.prepare_model_data(collections['selection'],max_queries=None,max_rows=880000,check=guard))
        _need(len(selection.queries)==4000 and selection.feature_names==identity['feature_names'],'All4000 original selection queries required')
        selection=stage('append_only_accepted_three_selection_columns',lambda:program_model_data.append_program_features(selection,identity['daily_features']['selection'],
            extra_columns=arm['physical_delta'],expected_source_schema=identity['expected_source_schema'],check=guard))
        report['selection_preparation']=selection.preparation
        report['selection_matrix_proof']=matrix_proof(selection,check=guard)
        full=directory/'full.cbm';full_json=directory/'full.json';prefix_path=directory/'prefix.cbm';scores_path=directory/'scores.npz'
        stage('save_complete_model',lambda:model.save_model(str(full)))
        stage('save_complete_native_JSON',lambda:model.save_model(str(full_json),format='json'))
        body,_=_read(full_json)
        _need(len(body.get('oblivious_trees',[]))==identity['model_spec']['trained_iterations'] and not body.get('features_info',{}).get('ctrs')
            and all(split['split_type']=='FloatFeature' for tree in body['oblivious_trees'] for split in tree.get('splits',[]) or []),
            'Saved numeric complete model contains incomplete/nonnumeric structure')
        prefix=model.copy();prefix.shrink(identity['model_spec']['scoring_prefix'])
        stage('save_inherited_scoring_prefix',lambda:prefix.save_model(str(prefix_path)))
        scores=stage('one_prefix_raw_predictions',lambda:model.predict(selection.x,ntree_end=identity['model_spec']['scoring_prefix'],prediction_type='RawFormulaVal',thread_count=2))
        loaded=CatBoostClassifier();stage('load_saved_prefix',lambda:loaded.load_model(str(prefix_path)))
        replay=stage('replay_saved_prefix',lambda:loaded.predict(selection.x,prediction_type='RawFormulaVal',thread_count=2))
        _need(loaded.tree_count_==identity['model_spec']['scoring_prefix'] and loaded.feature_names_==arm['feature_names']
            and np.allclose(scores,replay,rtol=0,atol=1e-12),'Saved prefix prediction/schema fidelity failed')
        rows=stage('rank_every_selection_query_full_targets',lambda:base.rankings(selection,scores))
        _need(rows==stage('saved_prefix_exact_all_query_ranking_fidelity',lambda:base.rankings(selection,replay)),
              'Saved prefix changes deterministic rankings despite bounded raw score tolerance')
        look['status']='seen_evaluation_started';_write(directory/'report.json',report)
        metrics=stage('one_external_fullY_four_estimands',lambda:asdict(evaluate(rows,20)))
        from scripts.strong_baseline import validate_metrics
        validate_metrics(metrics)
        stage('save_exact_sorted_scores',lambda:np.savez_compressed(scores_path,group=selection.group,product_id=selection.items,raw_score=np.asarray(scores,dtype=np.float64)))
        outputs={_relative(p):_sha(p,guard) for p in [full,full_json,prefix_path,scores_path]}
        look.update(status='seen_complete',metrics=metrics);manifest['outputs']=outputs
        report.update(status='complete_produced_unreviewed',outcome='arm_complete',actual_model_parameters=actual,metrics=metrics,
            artifacts=outputs,model_path=_relative(prefix_path),full_model_path=_relative(full),score_path=_relative(scores_path))
        stage('final_original_input_pins',lambda:_pins(identity['fingerprints'],guard))
        dynamic={ref['path']:ref['sha256'] for ref in [context['parent_plan'],context['slot'],parent['execution_approval'],parent['budget_claim']]}
        dynamic[_relative(path)]=issued_context_sha256;dynamic[_relative(consumed)]=worker_identity['consumed']['sha256']
        stage('final_issued_dynamic_authority_pins',lambda:_pins(dynamic,guard))
    except BaseException as error:primary=error
    finally:
        try:guard()
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Terminal guard: '+type(error).__name__)
        report.update(actual_entry_cpu_seconds=_self_cpu(),actual_reaped_children_cpu_seconds=_children_cpu(),
            process_peak_rss_bytes=_rss(),finished_monotonic=time.monotonic(),receipt_boundary='before_minimal_terminal_persistence_parent_reaping_charges_tail')
        report['seconds']=report['finished_monotonic']-ENTRY_MONOTONIC
        if primary is not None:report.update(status='failed',outcome='resource_failure' if _resource_failure(primary) else 'integrity_or_API_failure',
            error_type=type(primary).__name__,error='Consumed worker failed; no refill or additional metric look')
        try:
            _write(directory/'run.json',manifest);_write(directory/'report.json',report)
        except BaseException as error:
            primary=primary or error;report.update(status='failed',outcome='integrity_or_API_failure',error_type=type(primary).__name__)
        if primary is not None:
            try:(directory/'report.failed.json').write_text(_canonical(report)+'\n')
            except BaseException as error:primary.add_note('Failure marker persistence: '+type(error).__name__)
    if primary is not None:raise primary
    print(_canonical(dict(status=report['status'],report=_relative(directory/'report.json'))),flush=True)
    return report


def _candidate_from_worker(report,identity):
    cid=report['candidate_id']
    if report['status']=='failed':
        _need(report['outcome']=='resource_failure','Integrity/API/unknown worker failure causes STOP')
        return dict(candidate_id=cid,status='resource_failed',added_physical_columns=3,metrics=None)
    _need(report['status']=='complete_produced_unreviewed' and report['outcome']=='arm_complete' and report['fit_attempt_count']==1,
          'One completed fixed fit required')
    arm=identity['slots'][cid]
    _need(report['feature_names']==arm['feature_names'] and report['physical_delta']==arm['physical_delta']
          and report['added_columns']==arm['columns'] and report['bundle_id']==arm['bundle_id'],
          'Worker exact original arm/typed physical columns differ')
    validate_native(report['actual_model_parameters'],dict(identity=identity))
    looks=report['look_reservations']
    _need(len(looks)==1 and _canonical(looks[0])==_canonical(dict(prefix=identity['model_spec']['scoring_prefix'],status='seen_complete',metrics=report['metrics'])),
          'Exactly one consumed and completed inherited-prefix look required')
    from scripts.strong_baseline import validate_metrics
    validate_metrics(report['metrics'])
    return dict(candidate_id=cid,status='verified_success',added_physical_columns=3,metrics=report['metrics'],
                model_path=report['model_path'],score_path=report['score_path'],feature_names=report['feature_names'])


def _allocate_worker(directory,parent,cid,budget):
    token=uuid.uuid4().hex;path=directory/'slots'/(cid+'.json');context_path=directory/'slots'/(cid+'-context.json')
    slot=dict(version=1,parent_run_id=parent['run_id'],candidate_id=cid,token=token,allocation=budget.allocation(),
        context_path=_relative(context_path),output_root=_relative(directory/'workers'/cid),look_reservations=[parent['identity']['model_spec']['scoring_prefix']])
    slot_sha=_exclusive_json(path,slot)
    context=dict(version=1,parent_plan=dict(path=_relative(directory/'plan.json'),sha256=_sha(directory/'plan.json')),
                 slot=dict(path=_relative(path),sha256=slot_sha))
    context_sha=_exclusive_json(context_path,context)
    return slot,context_path,context_sha


def _invoke_worker(directory,parent,slot,path,issued_sha,budget):
    from scripts import strong_baseline as lifecycle
    cid=slot['candidate_id'];log=directory/'logs'/(cid+'.log')
    argv=[sys.executable,str(_local('scripts/feature_program_experiment.py')),'--worker','--context',str(path),'--issued-context-sha256',issued_sha]
    context,actual_context_sha=_read(path);_need(actual_context_sha==issued_sha,'Original issued worker context changed before launch');launch=dict(version=1,scope=ROLE,parent_run_id=parent['run_id'],candidate_id=cid,argv=argv,cwd=str(ROOT),
        context=dict(path=_relative(path),sha256=issued_sha),slot=context['slot'],allocation=slot['allocation'],log_path=_relative(log),issued_at_monotonic=time.monotonic())
    launch_sha=_exclusive_json(log.with_suffix('.launch.json'),launch)
    before=_children_cpu();code=lifecycle.run_process(argv,log,budget=budget,allocation=slot['allocation'])
    reaped=_children_cpu()-before;budget.guard()
    _need(_finite(reaped) and reaped>=0,'Unknown worker reaped CPU')
    consumed=_local(context['slot']['path']).with_suffix('.consumed.json');consumed_body,consumed_sha=_read(consumed)
    worker_identity=dict(version=1,role=ROLE+'_worker',parent_plan=context['parent_plan'],slot=context['slot'],
        issued_context=dict(path=_relative(path),sha256=issued_sha),consumed=dict(path=_relative(consumed),sha256=consumed_sha),
        candidate=parent['identity']['slots'][cid],procedure=parent['identity']['model_spec'])
    worker_id=_digest(worker_identity);output=_local(slot['output_root'])/worker_id
    report,report_sha=_read(output/'report.json');manifest,manifest_sha=_read(output/'run.json')
    _need(manifest['run_id']==worker_id and _canonical(manifest['identity'])==_canonical(worker_identity)
          and report['run_id']==worker_id and report['parent_run_id']==parent['run_id'] and report['candidate_id']==cid,
          'Worker manifest/report identity detached from durable launch')
    _need(type(report['fit_attempt_count']) is int and report['fit_attempt_count'] in (0,1)
        and report['actual_reaped_children_cpu_seconds']==0 and type(report['actual_reaped_children_cpu_seconds']) in (int,float)
        and _finite(report['actual_entry_cpu_seconds']) and 0<=report['actual_entry_cpu_seconds']<=reaped+1e-6
        and type(report['process_peak_rss_bytes']) is int and 0<report['process_peak_rss_bytes']<=8*2**30
        and _finite(report['started_monotonic']) and _finite(report['finished_monotonic'])
        and report['started_monotonic']<=report['finished_monotonic']<=time.monotonic(),
        'Worker actual usage/clock/count unknown or over ceiling')
    _need(_sha(path)==issued_sha and _sha(consumed)==consumed_sha,'Issued context/consumption changed after worker exit')
    _need(_canonical(consumed_body)==_canonical(dict(version=1,parent_run_id=parent['run_id'],candidate_id=cid,token=slot['token'],
        context_sha256=issued_sha,allowed_fit_attempts=1,allowed_metric_looks=1)),'Original per-slot consumption proof differs')
    if report['status']=='complete_produced_unreviewed':
        _need(report['actual_entry_cpu_seconds']<=slot['allocation']['cpu_seconds'] and reaped<=slot['allocation']['cpu_seconds']
            and launch['issued_at_monotonic']<=report['started_monotonic']<=report['finished_monotonic']<=slot['allocation']['deadline_monotonic']
            and report['process_peak_rss_bytes']<=7*2**30,'Successful worker exceeded its original issued CPU/clock/RSS allowance')
        _need(code==0 and not (output/'report.failed.json').exists(),'Known failed arm cannot be eligible')
        expected={_relative(output/name) for name in ['full.cbm','full.json','prefix.cbm','scores.npz']}
        _need(set(manifest['outputs'])==expected and report['artifacts']==manifest['outputs'],'Exactly four saved arm outputs required')
        _need(report['full_model_path']==_relative(output/'full.cbm') and report['model_path']==_relative(output/'prefix.cbm')
            and report['score_path']==_relative(output/'scores.npz'),'Saved model/score paths detached')
        _pins(manifest['outputs'],budget.guard)
    else:_need(code!=0 and report['status']=='failed' and report['outcome']=='resource_failure','Unknown/integrity/API worker failure causes STOP')
    candidate=_candidate_from_worker(report,parent['identity'])
    return dict(slot=context['slot'],context=dict(path=_relative(path),sha256=issued_sha),exit_code=code,
        actual_reaped_cpu_seconds=reaped,report=dict(path=_relative(output/'report.json'),sha256=report_sha),
        manifest=dict(path=_relative(output/'run.json'),sha256=manifest_sha),launch=dict(path=_relative(log.with_suffix('.launch.json')),sha256=launch_sha),
        worker_report=report,candidate=candidate)



def _equivalent(expected,actual):
    """Exact schemas/types/keys, bounded metric arithmetic serialization only."""
    if type(expected) is not type(actual):return False
    if type(expected) is dict:return set(expected)==set(actual) and all(_equivalent(v,actual[k]) for k,v in expected.items())
    if type(expected) is list:return len(expected)==len(actual) and all(_equivalent(a,b) for a,b in zip(expected,actual))
    if type(expected) is float:return math.isfinite(expected) and math.isfinite(actual) and abs(expected-actual)<=1e-12
    return expected==actual


def _known_late_failure(directory,children=(),sealed_outputs=None):
    for name in ['report.failed.json','observer/evidence.failed.json','observer/oracle.log.cleanup-failed.json']:
        if (directory/name).exists():raise RuntimeError('Late known failed model study/observer cannot return pending success')
    sealed_outputs={} if sealed_outputs is None else sealed_outputs
    for child in children:
        cid=child['worker_report']['candidate_id'];worker=_local(child['report']['path']).parent
        if (directory/'logs'/(cid+'.log.cleanup-failed.json')).exists():
            raise RuntimeError('Late unknown child cleanup failure causes study STOP')
        marker=worker/'report.failed.json'
        if marker.exists():
            if child['candidate']['status']=='verified_success':
                raise RuntimeError('Late known failed successful worker cannot be eligible')
            expected=sealed_outputs.get(_relative(marker))
            if expected is None or _sha(marker)!=expected:
                raise RuntimeError('New or changed resource-failure marker outside sealed evidence')

def _observer(directory,parent,producer_report,budget):
    from scripts import strong_baseline as lifecycle
    budget.verifying=True;budget.guard();allocation=budget.allocation()
    fresh=directory/'observer';fresh.mkdir(exist_ok=False)
    parent_cpu,children_cpu=_self_cpu(),_children_cpu()
    prefix=budget.source_paid_cpu+parent_cpu+children_cpu
    manifest_ref=dict(path=_relative(directory/'run.json'),sha256=_sha(directory/'run.json'))
    report_ref=dict(path=_relative(directory/'producer-report.json'),sha256=_sha(directory/'producer-report.json'))
    oracle=parent['identity']['oracle_source'];scope=ROLE+'_independent_model_output_observer'
    request=dict(version=1,scope=scope,run_id=parent['run_id'],producer_manifest=manifest_ref,producer_report=report_ref,
        execution_approval=parent['execution_approval'],budget_claim=parent['budget_claim'],oracle_source=oracle,
        shared_budget=dict(limit_cpu_seconds=7200,charged_prefix_cpu_seconds=prefix,unknown_cost=False,
            source_paid_cpu_seconds=budget.source_paid_cpu,owner_parent_cpu_seconds=parent_cpu,owner_reaped_children_cpu_seconds=children_cpu),
        original_owner=dict(started_monotonic=budget.started,absolute_deadline_monotonic=budget.outer_deadline),
        permissions=dict(observer_calls=1,refits=0,source_regenerations=0))
    _write(fresh/'request.json',request)
    request_ref=dict(path=_relative(fresh/'request.json'),sha256=_sha(fresh/'request.json'))
    context=dict(version=1,scope=scope,run_id=parent['run_id'],project_root=str(ROOT),invocation_directory=_relative(fresh),request=request_ref,
        producer_manifest=manifest_ref,producer_report=report_ref,oracle_source=oracle,allocation=allocation,issued_at_monotonic=time.monotonic(),
        output_path=_relative(fresh/'evidence.json'),failed_output_path=_relative(fresh/'evidence.failed.json'))
    _write(fresh/'context.json',context);issued=_sha(fresh/'context.json')
    argv=[sys.executable,str(_local(oracle['path'])),'--context',str(fresh/'context.json'),'--issued-context-sha256',issued]
    once=fresh/'once.claim.json'
    once_sha=_exclusive_json(once,dict(version=1,scope=scope,run_id=parent['run_id'],observer_calls=1,
        original_four_fit_claim=parent['budget_claim'],request=request_ref,context_sha256=issued))
    launch=dict(version=1,scope=scope,run_id=parent['run_id'],argv=argv,cwd=str(ROOT),context_sha256=issued,
        request=request_ref,allocation=allocation,claim=dict(path=_relative(once),sha256=once_sha))
    launch_sha=_exclusive_json(fresh/'launch.json',launch)
    before=_children_cpu();code=lifecycle.run_process(argv,fresh/'oracle.log',budget=budget,allocation=allocation)
    used=_children_cpu()-before;budget.guard()
    _need(code==0 and not (fresh/'evidence.failed.json').exists(),'Independent model output observer failed; no replacement/refit')
    evidence,evidence_sha=_read(fresh/'evidence.json')
    expected=dict(version=1,status='verified',scope=scope,run_id=parent['run_id'],source_run_id=parent['identity']['source_run_id'],
        context_sha256=issued,request=request_ref,producer_manifest=manifest_ref,producer_report=report_ref,oracle_source=oracle,
        fit_attempt_count=0,observer_refits=0,source_regenerations=0,allocated_slots=4,checked_slots=list(IDS[1:]),
        candidate_records=producer_report['candidates'],winner=producer_report['winner'])
    for key,value in expected.items():_need(key in evidence and _equivalent(value,evidence[key]),'Independent model evidence binding differs: '+key)
    execution=evidence['execution_consumed']
    _need(type(execution) is dict and execution.get('path')==_relative(fresh/'execution.consumed.json'),
          'Original child execution-consumption namespace differs')
    expected_execution=dict(version=1,scope=scope+'_execution_consumed',run_id=parent['run_id'],context_sha256=issued,
        request=request_ref,original_four_fit_claim=parent['budget_claim'],oracle_source=oracle,
        observer_calls=1,refits=0,source_regenerations=0)
    _need(_canonical(_read_ref(execution))==_canonical(expected_execution),'Original child execution-consumption authority differs')
    _need(set(evidence['worker_proofs'])==set(IDS[1:]),'Every original model slot needs independent proof')
    for child in producer_report['children']:
        proof=evidence['worker_proofs'][child['worker_report']['candidate_id']]
        for name in ['report','manifest','slot','context','launch']:
            _need(proof[name]==child[name],'Independent worker proof detached from original '+name)
    _need(type(evidence.get('proof_limits')) is str and bool(evidence['proof_limits']) and type(evidence.get('paired_bootstrap')) is dict,
          'Independent proof limits and descriptive paired comparison required')
    _need(_finite(used) and 0<=used<=allocation['cpu_seconds'] and _finite(evidence['process_cpu_seconds']) and 0<=evidence['process_cpu_seconds']<=used+1e-6
        and evidence['reaped_children_cpu_seconds']==0 and type(evidence['reaped_children_cpu_seconds']) in (int,float)
        and type(evidence['process_peak_rss_bytes']) is int and 0<evidence['process_peak_rss_bytes']<=7*2**30
        and context['issued_at_monotonic']<=evidence['started_monotonic']<=evidence['finished_monotonic']<=allocation['deadline_monotonic']
        and evidence['finished_monotonic']<=time.monotonic(),'Independent model oracle resource/clock proof differs')
    _need(_sha(fresh/'context.json',budget.guard)==issued and _read_ref(manifest_ref)['run_id']==parent['run_id']
          and _canonical(_read_ref(report_ref))==_canonical(producer_report),'Original producer/oracle context changed')
    _need(_sha(fresh/'evidence.json',budget.guard)==evidence_sha and _sha(once,budget.guard)==once_sha
          and _sha(fresh/'launch.json',budget.guard)==launch_sha,'Parsed model evidence/once/launch snapshot changed')
    authority={ref['path']:ref['sha256'] for ref in [request_ref,manifest_ref,report_ref,oracle,parent['execution_approval'],parent['budget_claim'],parent['identity']['owner_attempt_claim'],execution]}
    authority.update({_relative(fresh/'context.json'):issued,_relative(fresh/'evidence.json'):evidence_sha,
        _relative(once):once_sha,_relative(fresh/'launch.json'):launch_sha})
    _pins(authority,budget.guard)
    return dict(authority_pins=authority,evidence=dict(path=_relative(fresh/'evidence.json'),sha256=evidence_sha),context=dict(path=_relative(fresh/'context.json'),sha256=issued),
        request=request_ref,launch=dict(path=_relative(fresh/'launch.json'),sha256=launch_sha),actual_reaped_cpu_seconds=used,
        process_peak_rss_bytes=evidence['process_peak_rss_bytes'],paired_bootstrap=evidence['paired_bootstrap'],proof_limits=evidence['proof_limits'])


def run_owner(source_acceptance,control_acceptance,selector_path,approval_path):
    """Proposal and wait remain inside this fresh measured owner's allowance."""
    budget=Budget(1800,self_cpu=_self_cpu,children_cpu=_children_cpu,rss=_rss)
    _need(_children_cpu()==0,'Fresh dedicated owner requires no prior descendants')
    directory=ROOT/'artifacts/feature-program-invocations'/uuid.uuid4().hex;directory.mkdir(parents=True,exist_ok=False)
    report=dict(version=1,status='preparing',scope=ROLE,started_monotonic=budget.started,original_absolute_deadline_monotonic=budget.outer_deadline,
        children=[],fit_attempt_count=0,sum_metric_looks=0,observer_calls=0,heldout_labels_opened=False,
        active_slot=None,unknown_live_fit=False,unknown_metric_looks=False)
    primary=None;parent=None;source_prefix_verified=False;observer=None;sealed_outputs={}
    try:
        _write(directory/'report.json',report)
        owner_claim_path=_local(OWNER_CLAIM);owner_claim_path.parent.mkdir(parents=True,exist_ok=True)
        owner_claim=dict(version=1,scope=ROLE+'_owner_attempt',allowed_owner_attempts=1,
            owner_source=dict(path='scripts/feature_program_experiment.py',sha256=_sha(__file__)),
            source_acceptance=dict(path=_relative(source_acceptance),sha256=_read(source_acceptance)[1]),
            control_acceptance=dict(path=_relative(control_acceptance),sha256=_read(control_acceptance)[1]),
            selector=dict(path=_relative(selector_path),sha256=_read(selector_path)[1]),output_directory=_relative(directory),
            started_monotonic=budget.started,original_absolute_deadline_monotonic=budget.outer_deadline)
        owner_claim_sha=_exclusive_json(owner_claim_path,owner_claim)
        owner_ref=dict(path=OWNER_CLAIM,sha256=owner_claim_sha);report['owner_attempt_claim']=owner_ref
        report['status']='paid_preparation';_write(directory/'report.json',report)
        plan=prepare_plan(source_acceptance,control_acceptance,selector_path,check=budget.guard)
        plan['identity']['owner_attempt_claim']=owner_ref;plan['identity']['fingerprints'][OWNER_CLAIM]=owner_ref['sha256'];plan['run_id']=_digest(plan['identity'])
        budget.source_paid_cpu=plan['identity']['paid_source_cpu_seconds'];source_prefix_verified=True;budget.guard()
        _write(directory/'proposal.json',plan);report.update(status='awaiting_exact_execution_approval',run_id=plan['run_id'])
        _write(directory/'report.json',report)
        print(_canonical(dict(status=report['status'],run_id=plan['run_id'],proposal=_relative(directory/'proposal.json'),approval_path=_relative(approval_path))),flush=True)
        while not approval_path.exists():budget.guard();time.sleep(.25)
        approval,approval_sha=_read(approval_path)
        expected=dict(version=1,approved=True,scope=ROLE,run_id=plan['run_id'],fingerprints=plan['identity']['fingerprints'])
        _need(_canonical(approval)==_canonical(expected),'External fit approval differs from full actual proposal')
        execution=dict(path=_relative(approval_path),sha256=approval_sha)
        claim_body=dict(version=1,scope=ROLE,run_id=plan['run_id'],allowed_fit_attempts=4,allowed_metric_looks=4,
            allowed_observer_attempts=1,oracle_source=plan['identity']['oracle_source'],no_refill=True,output_directory=_relative(directory),
            execution_approval=execution,slot_paths=[_relative(directory/'slots'/(n+'.json')) for n in IDS[1:]])
        claim=_local(CLAIM);claim.parent.mkdir(parents=True,exist_ok=True)
        claim_sha=_exclusive_json(claim,claim_body)
        parent=dict(**plan,execution_approval=execution,budget_claim=dict(path=CLAIM,sha256=claim_sha))
        _write(directory/'plan.json',parent)
        for name in ['slots','logs','workers']:(directory/name).mkdir()
        report['status']='running';_write(directory/'report.json',report)
        candidates=[deepcopy(plan['identity']['baseline'])]
        for cid in IDS[1:]:
            slot,context_path,issued=_allocate_worker(directory,parent,cid,budget)
            report.update(active_slot=dict(candidate_id=cid,context=dict(path=_relative(context_path),sha256=issued),allocation=slot['allocation']),
                unknown_live_fit=True,unknown_metric_looks=True)
            _write(directory/'report.json',report)
            child=_invoke_worker(directory,parent,slot,context_path,issued,budget);report['children'].append(child)
            report['fit_attempt_count']+=child['worker_report']['fit_attempt_count']
            report['sum_metric_looks']+=sum(look['status'].startswith('seen_') for look in child['worker_report']['look_reservations'])
            report.update(active_slot=None,unknown_live_fit=False,unknown_metric_looks=False)
            candidates.append(child['candidate']);_write(directory/'report.json',report)
        _need(len(report['children'])==4 and report['fit_attempt_count']<=4 and report['sum_metric_looks']<=4,'Original four-fit/look allowance exceeded or incomplete')
        winner=choose(candidates);_write(directory/'winner.json',winner)
        parent_cpu,children_cpu=_self_cpu(),_children_cpu();finished=time.monotonic()
        producer_report=dict(version=1,scope=ROLE,run_id=plan['run_id'],status='producer_complete_pending_independent_observer',
            fit_attempt_count=report['fit_attempt_count'],sum_metric_looks=report['sum_metric_looks'],children=report['children'],candidates=candidates,winner=winner,
            source_paid_cpu_seconds=budget.source_paid_cpu,actual_parent_cpu_seconds=parent_cpu,actual_reaped_children_cpu_seconds=children_cpu,
            charged_study_cpu_seconds=budget.source_paid_cpu+parent_cpu+children_cpu,started_monotonic=budget.started,producer_finished_monotonic=finished,
            original_absolute_deadline_monotonic=budget.outer_deadline,parent_peak_rss_bytes=_rss(),heldout_labels_opened=False,
            active_slot=None,unknown_live_fit=False,unknown_metric_looks=False)
        _write(directory/'producer-report.json',producer_report)
        files=[directory/'plan.json',directory/'winner.json']
        for name in ['slots','logs','workers']:files.extend(p for p in (directory/name).rglob('*') if p.is_file())
        outputs={_relative(p):_sha(p,budget.guard) for p in sorted(files)};sealed_outputs=outputs
        producer=dict(**parent,outputs=outputs);_write(directory/'run.json',producer)
        report.update(status='independent_output_verification',candidates=candidates,winner=winner,observer_calls=1)
        _write(directory/'report.json',report)
        observer=_observer(directory,parent,producer_report,budget)
        _pins(plan['identity']['fingerprints'],budget.guard);_pins(outputs,budget.guard)
        _need(_sha(approval_path)==approval_sha and _sha(claim)==parent['budget_claim']['sha256'],'Original model authority changed after observer')
        _known_late_failure(directory,report['children'],sealed_outputs)
        peak=max([observer['process_peak_rss_bytes'],*[x['worker_report']['process_peak_rss_bytes'] for x in report['children']]])+_rss()
        if peak>8*2**30:raise MemoryError('Conservative model owner/child RSS exceeds8GiB')
        report.update(status='model_outputs_verified_pending_external_acceptance',observer=observer,conservative_job_peak_rss_bytes=peak,
            producer_manifest=dict(path=_relative(directory/'run.json'),sha256=_sha(directory/'run.json')),
            producer_report=dict(path=_relative(directory/'producer-report.json'),sha256=_sha(directory/'producer-report.json')))
    except BaseException as error:primary=error
    finally:
        try:
            budget.guard();_known_late_failure(directory,report['children'],sealed_outputs)
            if observer is not None:_pins(observer['authority_pins'],budget.guard)
            _known_late_failure(directory,report['children'],sealed_outputs)
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Final owner guard: '+type(error).__name__)
        parent_cpu,children_cpu=_self_cpu(),_children_cpu();finished=time.monotonic()
        if not all(_finite(v) and v>=0 for v in [parent_cpu,children_cpu,finished]):
            primary=primary or ValueError('Unknown terminal owner resource/clock usage')
        report.update(actual_parent_cpu_seconds=parent_cpu,actual_reaped_children_cpu_seconds=children_cpu,
            actual_new_owner_cpu_seconds=parent_cpu+children_cpu,charged_study_cpu_seconds=budget.source_paid_cpu+parent_cpu+children_cpu if source_prefix_verified else None,
            source_paid_cpu_seconds=budget.source_paid_cpu if source_prefix_verified else None,source_prefix_verified=source_prefix_verified,
            conservative_source_prefix_reserve_seconds=1800,seconds=finished-budget.started,finished_monotonic=finished,parent_peak_rss_bytes=_rss(),
            receipt_boundary='canonical_absolute_SELF_plus_reaped_CHILDREN_once_external_full_lifetime_seal_required')
        if report['unknown_live_fit']:
            report['known_fit_attempt_lower_bound']=report['fit_attempt_count'];report['fit_attempt_count']=None
        if report['unknown_metric_looks']:
            report['known_metric_look_lower_bound']=report['sum_metric_looks'];report['sum_metric_looks']=None
        if primary is not None:report.update(status='failed',error_type=type(primary).__name__,error='STOP original consumed study; no refill/refit/heldout promotion')
        try:_write(directory/'report.json',report)
        except BaseException as error:primary=primary or error;report.update(status='failed',error_type=type(primary).__name__)
        if primary is not None:
            try:(directory/'report.failed.json').write_text(_canonical(report)+'\n')
            except BaseException as error:primary.add_note('Owner failure marker persistence: '+type(error).__name__)
    if primary is not None:raise primary
    print(_canonical(dict(status=report['status'],directory=_relative(directory),run_id=report['run_id'])),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--context');p.add_argument('--issued-context-sha256')
    p.add_argument('--source-acceptance');p.add_argument('--control-acceptance');p.add_argument('--selector',default='configs/features/automation-selection.json');p.add_argument('--approval')
    args=p.parse_args();sys.path.insert(0,str(ROOT))
    if args.worker:
        _need(args.context is not None and args.issued_context_sha256 is not None and args.source_acceptance is None and args.control_acceptance is None and args.approval is None,
              'Worker must use only its original issued context')
        return worker_main(_local(args.context) if not Path(args.context).is_absolute() else Path(args.context),issued_context_sha256=args.issued_context_sha256)
    _need(all([args.source_acceptance,args.control_acceptance,args.approval]) and args.context is None and args.issued_context_sha256 is None,'Owner requires accepted source/control and exact external execution approval path')
    return run_owner(_local(args.source_acceptance),_local(args.control_acceptance),_local(args.selector),_local(args.approval))


if __name__=='__main__':main()
