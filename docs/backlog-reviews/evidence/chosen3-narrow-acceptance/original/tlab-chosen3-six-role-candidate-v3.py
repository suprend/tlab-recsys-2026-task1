"""SOURCE-ONLY candidate. Import defines helpers; no fit/DB/worker at import.

An issued exact freeze and a separate Root finite decision are required before
any CLI use. The original completed B-only namespace is strictly read-only.
"""
import time
ENTRY_MONOTONIC = time.monotonic()
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import sys
import types

SELF = Path('/tmp/tlab-chosen3-six-role-candidate-v3.py')
TEST = Path('/tmp/tlab-test-chosen3-six-role-candidate-v3.py')
BASE = Path('/tmp/tlab-run-heldout-six-role-toy.py')
SUPERVISOR = Path('/tmp/tlab-heldout-harness-processes.py')
ROOT = Path('/tmp/tlab chosen3 W44 integration 20261015')
PROJECT = Path('/Users/mdpospelov/tlab-recsys-2026')
EXTRAS = ['auto_item_view_count_distinct_24h_user_id',
          'auto_item_cart_count_distinct_168h_user_id',
          'auto_item_purchase_count_distinct_24h_user_id']
ESTIMANDS = {'conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero'}
METRIC_METADATA = {'k','query_count','mature_query_count','censored_query_count',
    'nonempty_query_count','mature_user_count','positive_user_count','nonempty_fraction'}
SETUP_OUTPUTS = ['fixture-reused/B.cbm','fixture-reused/original-B-spec.json',
    'fixture-reused/B-spec.json','fixture-reused/reuse-provenance.json',
    'fixture-setup/model-spec.json','fixture-setup/W.cbm','fixture-setup/W-model-spec.json','fixture-setup/result.json']
DISCLOSURES = dict(scope='synthetic_chosen3_R2_L05_integration_only',
    historical_authentication_exercised=False,historical_consumer_stub=True,synthetic_gate_issuer=True,
    actual_W_training_rows=8,protocol_population_literal=26000,new_setup_fit_attempt_count=1,
    reused_B_new_fit_attempt_count=0,original_B_synthetic_fit_attempt_count=1,study_fit_attempt_count=0,
    W_equals_B=False,metric_delta_required_nonzero=False,real_recommendation_quality_claim=False,
    fresh_source_bootstrap_proven=False,production_resource_sufficiency_proven=False)


def need(value,message):
    if not value:raise ValueError(message)


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while part:=stream.read(2**20):result.update(part)
    return result.hexdigest()


def snapshot(path,expected=None):
    with Path(path).open('rb') as stream:raw=stream.read(8*2**20+1)
    need(len(raw)<=8*2**20,'Bounded JSON required')
    digest=hashlib.sha256(raw).hexdigest()
    if expected is not None:need(digest==expected,'Original issued JSON bytes changed')
    def unique(pairs):
        body={}
        for key,value in pairs:need(key not in body,'Duplicate JSON key');body[key]=value
        return body
    def reject(_):raise ValueError('Nonfinite JSON')
    body=json.loads(raw,object_pairs_hook=unique,parse_constant=reject)
    json.dumps(body,allow_nan=False)
    return body,digest


def read(path,expected=None):
    return snapshot(path,expected)[0]


def merge_pin(pins,name,digest):
    need(pins.get(name,digest)==digest,'Conflicting original evidence pin')
    pins[name]=digest


def repin(root,pins):
    for name,digest in pins.items():need(sha(root/name)==digest,'Original validated evidence bytes changed')


def write_pinned(base,path,body):
    digest=hashlib.sha256((base.canonical(body)+'\n').encode()).hexdigest()
    base.exclusive(path,body)
    need(sha(path)==digest,'Written original receipt bytes changed')
    return digest


def raw_module(path,digest,name):
    with Path(path).open('rb') as stream:raw=stream.read(2**20+1)
    need(len(raw)<=2**20 and hashlib.sha256(raw).hexdigest()==digest,'Original helper source bytes changed')
    module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def load(freeze_path,issued_sha256):
    need(type(issued_sha256) is str and re.fullmatch('[a-f0-9]{64}',issued_sha256) is not None,'Issued freeze SHA required')
    f=read(freeze_path,issued_sha256)
    need(f['version']==1 and f['scope']=='source_only_chosen3_R2_L05_candidate_no_execution_authority','Candidate scope differs')
    need(f['execution_authority'] is False and f['disclosures']==DISCLOSURES,'Synthetic disclosures differ')
    need(Path(__file__).resolve()==SELF.resolve(),'Candidate canonical TMP identity differs')
    need(set(f['harness_files'])=={str(SELF),str(TEST),str(BASE),str(SUPERVISOR)},'Exact candidate/helper/test closure required')
    for name,digest in f['harness_files'].items():need(sha(name)==digest,'Frozen candidate/helper bytes changed')
    need(Path(f['isolated_root']).resolve()==ROOT.resolve(),'Original chosen3 namespace cannot be replaced/refilled')
    base=raw_module(BASE,f['harness_files'][str(BASE)],'tlab_chosen3_original_base')
    need(set(f['production_files'])==set(base.public_files()) and len(f['production_files'])==31,'Exact public31 closure required')
    return base,f


def fresh_child():
    children=resource.getrusage(resource.RUSAGE_CHILDREN)
    need(children.ru_utime+children.ru_stime==0,'Fresh process with no prior reaped children required')
    need(not any(n=='scripts' or n.startswith('scripts.') or n=='tests' or n.startswith('tests.') for n in sys.modules),'Fresh project namespace required')


def matched_specs(b,w):
    need(len(b['feature_names'])==41 and w['feature_names']==b['feature_names']+EXTRAS,'Exact B41 plus L05 chosen3 required')
    need(b['model']!=w['model'] and b['model']['sha256']!=w['model']['sha256'],'Distinct B41/W44 model bytes required')
    need(b['effective_parameters']==w['effective_parameters'],'Observed common effective parameters differ')
    for spec in [b,w]:need(spec['population']==26000 and spec['trained_iterations']==spec['scoring_prefix']==300,'Synthetic procedure differs')


def copy_reused_B(base,root,f):
    """Future setup only: exact synthetic B copy; never write to original root."""
    origin=f['reused_B'];old=Path(origin['root']).resolve()
    need(old!=root and old==Path('/tmp/tlab heldout six role integration 20261015').resolve(),'Only the completed original synthetic B may be reused')
    receipt=read(origin['external_receipt']['path'],origin['external_receipt']['sha256'])
    need(receipt['state']=='succeeded' and receipt['external_exit_code']==0 and receipt['fit_attempt_count']==1 and receipt['synthetic_training_rows']==8 and receipt['feature_count']==41,'Original B paid setup external boundary absent')
    setup=read(old/'setup-supervision.json',origin['setup_supervision_sha256'])
    need(setup['status']=='verified_normal_exit' and setup['exit_code']==0 and setup['reviewed_freeze_sha256']==origin['whole_freeze']['sha256'],'Original B internal boundary absent')
    read(origin['whole_freeze']['path'],origin['whole_freeze']['sha256'])
    for name,digest in origin['bound_outputs'].items():
        need(receipt['bound_outputs'][name]==digest and setup['bound_outputs'][name]==digest and sha(old/name)==digest,'Original B setup output pin differs')
    b=read(old/'fixture-setup/model-spec.json',origin['bound_outputs']['fixture-setup/model-spec.json'])
    need(b['model']==dict(path='fixture-setup/B.cbm',sha256=origin['bound_outputs']['fixture-setup/B.cbm']) and len(b['feature_names'])==41,'Original B model identity differs')
    destination=root/'fixture-reused';destination.mkdir(exist_ok=False)
    for old_name,new_name in [('B.cbm','B.cbm'),('model-spec.json','original-B-spec.json')]:
        source=old/'fixture-setup'/old_name
        with source.open('rb') as src,(destination/new_name).open('xb') as dst:shutil.copyfileobj(src,dst,2**20)
        need(sha(destination/new_name)==origin['bound_outputs']['fixture-setup/'+old_name],'Copied original B bytes differ')
    derived=deepcopy(b);derived['model']['path']='fixture-reused/B.cbm'
    base.exclusive(destination/'B-spec.json',derived)
    base.exclusive(destination/'reuse-provenance.json',dict(scope='exact_previously_paid_synthetic_B_copy_only',source=origin,
        original_spec_sha256=sha(destination/'original-B-spec.json'),copied_model_sha256=sha(destination/'B.cbm'),new_B_fit_attempt_count=0))


def reused_spec(root,f):
    original=read(root/'fixture-reused/original-B-spec.json',f['reused_B']['bound_outputs']['fixture-setup/model-spec.json'])
    expected=deepcopy(original);expected['model']['path']='fixture-reused/B.cbm'
    actual=read(root/'fixture-reused/B-spec.json')
    need(actual==expected and sha(root/actual['model']['path'])==actual['model']['sha256'],'Reused B projection/model changed')
    return actual


def setup_fit(root,freeze_path,issued):
    base,f=load(freeze_path,issued);root=base.safe_root(root);need(root==ROOT.resolve(),'Original chosen3 root required');fresh_child()
    setup=root/'fixture-setup';setup.mkdir(exist_ok=False)
    base.exclusive(setup/'attempt.consumed.json',dict(version=1,**DISCLOSURES,fit_attempt_count=1,started_monotonic=ENTRY_MONOTONIC))
    try:
        resource.setrlimit(resource.RLIMIT_CPU,(59,60));need(resource.getrlimit(resource.RLIMIT_CPU)==(59,60),'Setup CPU fence readback failed')
        b=reused_spec(root,f);sys.path.insert(0,str(root))
        from scripts import feature_programs,strong_baseline,heldout_predictions
        pool=feature_programs.generate_pool(read(root/'configs/features/automation-pool.json'),read(root/'configs/features/manual-18.json'))
        allocation=feature_programs.allocate_slots(pool)
        slot=next(row for row in allocation['identity']['slots'] if row['slot']=='R2')
        need(slot['bundle_id']=='L05' and slot['status']=='planned_unexecuted','Exact frozen R2=L05 slot required')
        bundle=next(row for row in pool['identity']['bundles'] if row['bundle_id']=='L05')
        names=bundle['model_feature_order'];need(names==b['feature_names']+EXTRAS,'Public selected44 schema differs')
        for name,digest in f['production_files'].items():need(sha(root/name)==digest,'Copied public source changed')
        for name,module in list(sys.modules.items()):
            if name.startswith(('scripts.','tests.')) and getattr(module,'__file__',None):need(Path(module.__file__).resolve().is_relative_to(root),'Setup project import escaped copied root')
        import numpy as np
        from catboost import CatBoostClassifier,Pool
        matrix=np.zeros((8,44),dtype=np.float32)
        matrix[:,41:]=np.array([[r%2,(r//2)%2,(r//4)%2] for r in range(8)],dtype=np.float32)
        labels=np.array([r%2 for r in range(8)],dtype=np.int64)
        model=CatBoostClassifier(**strong_baseline.model_parameters(dict(depth=6,l2_leaf_reg=30)))
        model.fit(Pool(matrix,labels,feature_names=names))
        path=setup/'W.cbm';need(not path.exists(),'Exclusive W model required');model.save_model(str(path))
        loaded=CatBoostClassifier();loaded.load_model(str(path))
        w=dict(model=dict(path='fixture-setup/W.cbm',sha256=sha(path)),feature_names=names,
            trained_iterations=300,scoring_prefix=300,population=26000,effective_parameters=deepcopy(loaded.get_all_params()))
        heldout_predictions.verify_model(loaded,w);matched_specs(b,w)
        borders=loaded.get_borders();need(any(borders.get(index,[]) for index in [41,42,43]),'Predetermined synthetic W must split on a chosen input')
        own=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu=own.ru_utime+own.ru_stime;peak=int(own.ru_maxrss if sys.platform=='darwin' else own.ru_maxrss*1024)
        need(children.ru_utime+children.ru_stime==0 and cpu<60 and time.monotonic()-ENTRY_MONOTONIC<120 and 0<peak<=2**30,'Setup finite boundary exceeded')
        base.exclusive(setup/'model-spec.json',b)  # Original fixture_request reads this B projection.
        base.exclusive(setup/'W-model-spec.json',w)
        base.exclusive(setup/'result.json',dict(version=1,**DISCLOSURES,status='W44_setup_complete_pending_external_exit_tail',
            fit_attempt_count=1,training_rows=8,feature_count=44,child_cpu_seconds=cpu,child_peak_rss_bytes=peak,
            elapsed_seconds=time.monotonic()-ENTRY_MONOTONIC,native_prediction_count=0,chosen_suffix_split=True))
    except BaseException as error:
        try:base.exclusive(setup/'failed.json',dict(version=1,**DISCLOSURES,status='failed_consumed_no_retry',error_type=type(error).__name__))
        except BaseException as secondary:error.add_note('Setup failure persistence: '+type(secondary).__name__)
        raise


def metric_shape(periods):
    need(set(periods)=={'confirmation25_reporting_only','final26_31_frozen'},'Both fixed reporting windows required')
    for body in periods.values():
        need(set(body['metrics'])=={'B','W'} and set(body['ndcg_W_minus_B'])==ESTIMANDS and set(body['paired_user_bootstrap'])==ESTIMANDS,'Complete B/W estimands required')
        need(set(body['metrics']['B'])==set(body['metrics']['W'])==ESTIMANDS|METRIC_METADATA,'Complete per-model metric vectors and metadata required')
        for estimand in ESTIMANDS:
            bootstrap=body['paired_user_bootstrap'][estimand]
            need(bootstrap['replicates']==200 and bootstrap['seed']==2026 and len(bootstrap['samples'])==200,'Every fixed paired-user draw required')
            need(bootstrap['undefined_draws']==sum(v is None for v in bootstrap['samples']),'Undefined paired draws differ')
    # Zero, nonzero and undefined deltas are all legal; original oracle checks values.


def native_call_count(days):
    return 2*sum(day['candidate_count']>0 for day in days)


def chosen_proof(proof,pairs):
    need(proof['choice']=='R2' and proof['chosen_columns']==3 and proof['chosen_scalar_values']==3*pairs and proof['chosen_formula_values_complete'] is True and proof['mismatch_count']==0 and proof['extra_proof_scope']=='all_selected3_values_every_C_row' and proof['baseline_formula_values_complete'] is False,'Complete chosen3 and sampled B18 scope required')
    need(sum(d['candidate_count'] for d in proof['days'])==pairs and all(d['chosen_columns']==3 and d['chosen_scalar_values']==3*d['candidate_count'] and d['chosen_formula_values_complete'] is True for d in proof['days']),'Every day chosen3 cardinality required')


def verify_results(base,root,owner,report,calls,gates,f):
    need(calls==1 and report['status']=='verified_reporting_pending_external_lifetime_acceptance','Original owner terminal state absent')
    need([r['role'] for r in report['roles']]==list(owner.x.ROLES) and len(gates)==4,'Exactly six real roles/four synthetic gates required')
    pins={}
    def refs(value):
        if type(value) is dict:
            if 'fingerprints' in value:
                for name,digest in value['fingerprints'].items():merge_pin(pins,name,digest)
            if set(value)=={'path','sha256'}:merge_pin(pins,value['path'],value['sha256'])
            for v in value.values():refs(v)
        elif type(value) is list:
            for v in value:refs(v)
    def checked(path):
        body,digest=snapshot(path);refs(body);merge_pin(pins,str(path.relative_to(root)),digest)
        return body
    claim=checked(root/owner.CLAIM);directory=root/claim['output_directory']
    need(not list(root.rglob('*failed.json')),'Failed marker forbids success')
    source=checked(directory/'source/source-manifest.json');pairs=sum(d['candidate_count'] for d in source['days']);native=native_call_count(source['days'])
    need(pairs>0 and source['days'][0]['query_count']>0 and source['days'][0]['candidate_count']==0 and source['days'][-1]['query_count']==source['days'][-1]['candidate_count']==0,'Required nonempty/empty source support absent')
    need(all(d['extra_features'] is not None for d in source['days']),'Seven chosen3 partitions required')
    proof=checked(directory/'source_oracle/evidence.json')['core']
    chosen_proof(proof,pairs)
    b=checked(root/'fixture-setup/model-spec.json');w=checked(root/'fixture-setup/W-model-spec.json');matched_specs(b,w)
    prediction=checked(directory/'predictions/prediction-manifest.json')
    for day in prediction['days']:
        first,second=day['predictions']['B'],day['predictions']['W']
        need(first['model']==b['model'] and second['model']==w['model'] and first['feature_names']==b['feature_names'] and second['feature_names']==w['feature_names'] and first['artifact']!=second['artifact'],'Separate native B41/W44 descriptors required')
    for index,role in enumerate(owner.x.ROLES):
        receipt=checked(directory/role/'receipt.json');boundary=checked(directory/(role+'-reaped.json'));context=checked(directory/role/'context.json');launch=checked(directory/role/'launch.json')
        need(boundary['explicitly_reaped_exit_code']==0 and receipt['labels_loaded'] is (index>=4) and receipt['fit_attempt_count']==0 and receipt['descendant_cpu_seconds']==0,'Original finite reaped role boundary differs')
        need(receipt['native_prediction_count']==(native if role in {'predictions','prediction_oracle'} else 0),'Two actual native models per nonempty date required')
        entry=owner.x.ENTRY[role];need(context['entry']['path']==entry and launch['argv'][1]==str(root/entry),'Actual fixed CLI differs')
        need(not list((directory/role).glob('oracle-scratch-*')),'Original oracle scratch not closed')
        spill=directory/role/'spill';need(not spill.exists() or not any(spill.iterdir()),'Producer spill retains material')
    evaluation=checked(directory/'targets_evaluation/evaluation.json');metric=checked(directory/'metric_oracle/evidence.json')['core'];metric_shape(evaluation['periods'])
    from tests.oracles import heldout_metric_audit
    heldout_metric_audit.compare(evaluation['periods'],metric['periods'])
    need(report['aggregate_periods']==evaluation['periods'] and metric['bootstrap_replicates_per_estimand']==200 and metric['private_ranking_rows_checked']==2*sum(d['query_count'] for d in source['days']),'Actual independent nonzero-capable metric path absent')
    need(evaluation['periods']['confirmation25_reporting_only']['support']['target_pairs']==1 and evaluation['periods']['confirmation25_reporting_only']['support']['candidate_pairs']==0,'Empty-C positive/deduplicated target lost')
    for path in [root/'fixture-history/request.json',root/owner.CLAIM,directory/'proposal.json']+list(directory.rglob('*.json')):
        checked(path)
    repin(root,pins)
    for name,digest in f['production_files'].items():need(sha(root/name)==digest,'Copied public bytes changed')
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(version=1,**DISCLOSURES,status='chosen3_six_roles_complete_pending_supervisor_exit_tail',
        actual_roles=list(owner.x.ROLES),chosen_bundle='L05',chosen_columns=3,chosen_scalar_values=3*pairs,
        candidate_pairs=pairs,native_calls_each_prediction_role=native,metrics_independently_recomputed=True,
        metric_delta_required_nonzero=False,actual_parent_cpu_seconds=own.ru_utime+own.ru_stime,
        actual_reaped_children_cpu_seconds=child.ru_utime+child.ru_stime,
        actual_total_cpu_seconds=own.ru_utime+own.ru_stime+child.ru_utime+child.ru_stime,
        elapsed_seconds=time.monotonic()-ENTRY_MONOTONIC,evidence_fingerprints=pins,gate_trace=gates,
        external_exit_tail_acceptance_required=True,unknown_active_work=False)


def integration(root,freeze_path,issued):
    base,f=load(freeze_path,issued);root=base.safe_root(root);need(root==ROOT.resolve(),'Original chosen3 root required');fresh_child()
    base.exclusive(root/'integration-controller.consumed.json',dict(version=1,**DISCLOSURES,started_monotonic=ENTRY_MONOTONIC))
    try:
        sys.path.insert(0,str(root));from scripts import run_heldout_reporting as owner
        need(owner.ROOT==root,'Original owner ROOT escaped copied root')
        for name,digest in f['production_files'].items():need(sha(root/name)==digest,'Copied public bytes changed before owner')
        request,choice,pins=base.fixture_request(root,owner)
        w=read(root/'fixture-setup/W-model-spec.json');matched_specs(choice['models']['B'],w)
        choice['candidate_id']='R2';choice['models']['W']=w;pins[w['model']['path']]=w['model']['sha256']
        from scripts import feature_program_control as control
        real_history=control.verify_choice;real_await=owner.await_external;calls=0;gates=[]
        def synthetic_history(path,*,check):
            nonlocal calls
            need(calls==0,'Synthetic history is once-only');calls+=1;check()
            need(path==root/request['model_acceptance']['path'] and (root/owner.CLAIM).exists(),'Synthetic history before consumed owner')
            return dict(acceptance=deepcopy(request['model_acceptance']),pins=deepcopy(pins),authenticated_choice=deepcopy(choice))
        control.verify_choice=synthetic_history;owner.await_external=base.issuer(owner,real_await,gates)
        try:report=owner.run_owner(root/'fixture-history/request.json')
        finally:control.verify_choice=real_history;owner.await_external=real_await
        for name,module in list(sys.modules.items()):
            if name.startswith(('scripts.','tests.')) and getattr(module,'__file__',None):
                path=Path(module.__file__).resolve();need(path.is_relative_to(root) and str(path.relative_to(root)) in owner.CODE,'Project import escaped pinned copied code')
        result=verify_results(base,root,owner,report,calls,gates,f)
        repin(root,result['evidence_fingerprints'])
        result_pin=write_pinned(base,root/'integration-result.json',result)
        repin(root,dict(result['evidence_fingerprints'],**{'integration-result.json':result_pin}))
    except BaseException as error:
        try:base.exclusive(root/'integration.failed.json',dict(version=1,**DISCLOSURES,status='failed_consumed_no_retry',error_type=type(error).__name__,unknown_active_work=True))
        except BaseException as secondary:error.add_note('Integration failure persistence: '+type(secondary).__name__)
        raise


def supervise(stage,root,freeze_path,issued):
    base,f=load(freeze_path,issued);root=base.safe_root(root);need(root==ROOT.resolve() and stage in {'setup','integration'},'Fixed finite chosen3 namespace/stage required');fresh_child()
    consumed=root/(stage+'-supervisor.consumed.json');previously_consumed=consumed.exists();observation=None;stage_inputs={};setup=None;setup_pin=None
    try:
        if stage=='setup':
            base.create_copy(root,f)
            base.exclusive(consumed,dict(version=1,**DISCLOSURES,stage=stage,reviewed_freeze_sha256=issued,automatic_retry=False))
            copy_reused_B(base,root,f)
        else:
            setup,setup_pin=snapshot(root/'setup-supervision.json');need(setup['status']=='verified_normal_exit' and setup['exit_code']==0 and setup['reviewed_freeze_sha256']==issued,'Original paid W44 setup prerequisite absent')
            need(set(setup['bound_outputs'])==set(SETUP_OUTPUTS),'Exact original new setup output closure required')
            stage_inputs=dict(setup['bound_outputs']);merge_pin(stage_inputs,'setup-supervision.json',setup_pin);repin(root,stage_inputs)
            need(not list(root.rglob('*failed.json')),'Failed marker forbids integration')
            base.exclusive(consumed,dict(version=1,**DISCLOSURES,stage=stage,reviewed_freeze_sha256=issued,automatic_retry=False))
        argv=[f['python'],'-I','-B',str(SELF),'--child',stage,'--root',str(root),'--freeze',str(Path(freeze_path).resolve()),'--issued-freeze-sha256',issued]
        observation=base.processes(f['harness_files'][str(SUPERVISOR)]).supervise(argv,root/(stage+'-process.log'),started=ENTRY_MONOTONIC,cpu_seconds=60,wall_seconds=120,rss_bytes=2**30 if stage=='setup' else 2*2**30,cwd=root)
        observation.update(version=1,stage=stage,scope=DISCLOSURES['scope'],reviewed_freeze_sha256=issued,counter_rule='SELF_plus_one_inclusive_wait4; role_subtotals_cross_checks_only')
        normal=(observation['status']=='verified_normal_exit' and observation['exit_code']==0 and observation['unknown_active_work'] is False and observation['cpu_upper_seconds']<=60 and observation['elapsed_upper_seconds']<=120)
        if not normal:
            base.exclusive(root/(stage+'-supervision.json'),observation)
            raise ValueError('Consumed chosen3 process boundary failed')
        repin(root,stage_inputs)
        names=SETUP_OUTPUTS if stage=='setup' else ['integration-result.json']
        result,result_pin=snapshot(root/names[-1]);expected='W44_setup_complete_pending_external_exit_tail' if stage=='setup' else 'chosen3_six_roles_complete_pending_supervisor_exit_tail'
        need(result['status']==expected and all(result[k]==v for k,v in DISCLOSURES.items()),'Original scoped result absent')
        if stage=='setup':need(result['fit_attempt_count']==1 and result['training_rows']==8 and result['feature_count']==44,'Original counted W44 setup result differs')
        subtotal=result['child_cpu_seconds'] if stage=='setup' else result['actual_total_cpu_seconds']
        need(observation['wait4_child_cpu_seconds']+.05>=subtotal,'Inclusive wait4 CPU cross-check failed')
        observation['bound_outputs']={name:sha(root/name) for name in names[:-1]};merge_pin(observation['bound_outputs'],names[-1],result_pin)
        repin(root,observation['bound_outputs']);repin(root,stage_inputs)
        supervision_pin=write_pinned(base,root/(stage+'-supervision.json'),observation)
        terminal=dict(stage_inputs)
        for name,digest in observation['bound_outputs'].items():merge_pin(terminal,name,digest)
        merge_pin(terminal,stage+'-supervision.json',supervision_pin);repin(root,terminal)
        if stage=='integration':
            ledger=dict(version=1,**DISCLOSURES,status='synthetic_chosen3_test_verified_pending_external_supervisor_tails',
                setup_supervision_sha256=setup_pin,integration_supervision_sha256=supervision_pin,integration_result_sha256=result_pin,
                additional_job_cpu_upper_seconds=setup['cpu_upper_seconds']+observation['cpu_upper_seconds'],original_B_setup_cost_not_charged_again=True,
                exact_supervisor_exit_tail_measured=False,unknown_active_work=False)
            repin(root,terminal);ledger_pin=write_pinned(base,root/'harness-ledger.json',ledger)
            merge_pin(terminal,'harness-ledger.json',ledger_pin);repin(root,terminal)
    except BaseException as error:
        if not previously_consumed and consumed.exists():
            try:base.exclusive(root/(stage+'-supervision.failed.json'),dict(version=1,**DISCLOSURES,status='failed_consumed_no_retry',stage=stage,error_type=type(error).__name__,unknown_active_work=True,returned_process_observation=deepcopy(observation),process_cleanup_evidence=deepcopy(getattr(error,'supervisor_cleanup_evidence',None))))
            except BaseException as secondary:error.add_note('Supervision failure persistence: '+type(secondary).__name__)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Source-only candidate; requires separately reviewed exact finite Root agreement')
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--stage',choices=['setup','integration']);mode.add_argument('--child',choices=['setup','integration'])
    parser.add_argument('--root',required=True);parser.add_argument('--freeze',required=True);parser.add_argument('--issued-freeze-sha256',required=True);args=parser.parse_args()
    if args.stage:supervise(args.stage,args.root,args.freeze,args.issued_freeze_sha256)
    elif args.child=='setup':setup_fit(args.root,args.freeze,args.issued_freeze_sha256)
    else:integration(args.root,args.freeze,args.issued_freeze_sha256)
