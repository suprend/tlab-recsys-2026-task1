"""Bounded four-fit base41 search with fresh gate/workers and one budget.

New real execution requires exact external approval. Worker entry is tied to
an allocated/consumed parent slot, never a standalone free training command.
"""
import resource
import time
ENTRY_MONO=time.monotonic()
ENTRY_SELF=resource.getrusage(resource.RUSAGE_SELF)
ENTRY_CHILDREN=resource.getrusage(resource.RUSAGE_CHILDREN)

from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
ROLE='strong_baseline_search'
CLAIM='artifacts/fit-claims/tlab019-strong-grid.json'
ABLAT_PROOFS=('docs/backlog-reviews/tlab009-model-output-verification.md',
    'docs/backlog-reviews/tlab009-model-output-aggregate.json',
    'docs/backlog-reviews/tlab009-model-oracle-accepted-source.md',
    'docs/backlog-reviews/tlab009-model-oracle-review.md')


def helpers():
    from scripts import metadata_price_collection as c
    return c


def local(name):
    from scripts.protocol_manifest import _relative_path
    _relative_path(name);path=(ROOT/name).resolve();path.relative_to(ROOT.resolve());return path


def relative(path):return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
def read(path):return helpers()._read_json(path)
def write(path,body):return helpers()._atomic_json(path,body)
def sha(path):return helpers().sha256_file(path)
def digest(body):return hashlib.sha256(helpers().canonical_json(body).encode()).hexdigest()
def self_cpu():
    r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime
def child_cpu():
    r=resource.getrusage(resource.RUSAGE_CHILDREN);return r.ru_utime+r.ru_stime
def rss():
    r=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(r*1024 if sys.platform.startswith('linux') else r)


def specification():
    return dict(version=1,role=ROLE,grid=[dict(depth=d,l2_leaf_reg=l) for d in [4,6] for l in [3,30]],
        checkpoints=[50,150,300],iterations=300,seed=2026,
        limits=dict(cpu_seconds=3600,verification_cpu_reserve=300,parent_launch_cpu_reserve=60,wall_seconds=3600,
            verification_wall_reserve=360,cleanup_wall_reserve=20,gate_wall_seconds=600,parent_rss_bytes=2**30,
            worker_rss_bytes=7*2**30,term_grace_seconds=5,kill_reap_seconds=5,log_bytes=2**20),
        population=dict(full=26000,fallback=6000,selection=4000),policy=dict(no_refill=True,
            successful_300_before_scores=True,late_failure_whole_arm_ineligible=True,
            tie='global_max_minus_1e-12_then_fewer_trees_depth_incumbent_config_id',
            recall_floor=.5792133072407045,schema='base41'))


def load_spec(path):
    raw=Path(path).read_bytes();body=read(path)
    # Canonical encoding comparison also rejects bool/int equality tricks.
    if helpers().canonical_json(body)!=helpers().canonical_json(specification()):raise ValueError('Strong grid differs from frozen specification')
    if Path(path).read_bytes()!=raw:raise ValueError('Strong grid changed during snapshot')
    return body,hashlib.sha256(raw).hexdigest()


def verify_rejected_ablation(path,base_config,train_path,selection_path,*,check=lambda:None):
    from scripts import metadata_ablation as a
    c=helpers();approval=read(path)
    c._keys(approval,{'version','approved','scope','run_id','fingerprints'},'009 ablation source acceptance')
    if type(approval['version']) is not int or approval['version']!=1 or approval['approved'] is not True or approval['scope']!='reviewed_metadata_price_single_ablation':
        raise ValueError('Independent009 model acceptance required')
    c._hashes({'run_id':approval['run_id']},'009 ablation runID')
    directory=ROOT/'artifacts/metadata-ablation'/approval['run_id']
    if (directory/'report.failed.json').exists():raise ValueError('Known failed009 model receipt')
    names=[relative(directory/n) for n in ['run.json','report.json']]
    for name in names:
        if name not in approval['fingerprints']:raise ValueError('Missing009 manifest/report pin')
        c.verify_pins({name:approval['fingerprints'][name]},check)
    manifest,report=(read(local(n)) for n in names)
    refs=manifest['identity']['acceptance_refs']
    if refs['train']!=relative(train_path) or refs['selection']!=relative(selection_path):raise ValueError('009/base collections differ')
    expected,inputs=a.prepare_plan(base_config,train_path,selection_path,local(refs['metadata']),local(refs['control']),check=check)
    if manifest['identity']!=expected['identity'] or manifest['run_id']!=expected['run_id'] or approval['run_id']!=expected['run_id']:
        raise ValueError('009 model identity differs from actual complete source plan')
    if (report.get('status')!='complete_produced_unreviewed' or report.get('run_id')!=expected['run_id']
            or type(report.get('fit_attempt_count')) is not int or report['fit_attempt_count']!=1
            or report.get('decision')!=a.retention(report['metrics']) or report['decision']['retain_metadata_block'] is not False):
        raise ValueError('Only independently accepted rejected009/base41 choice supported')
    execution=manifest['execution_approval']
    required=c.merge_pins(expected['identity']['fingerprints'],{execution['path']:execution['sha256']},
        {n:approval['fingerprints'][n] for n in names})
    outputs=manifest['outputs']
    fixed={relative(directory/n) for n in ['Logloss.cbm','Logloss.json','Logloss-scores.npz']}
    if set(outputs)!=fixed or report['artifacts']!=outputs:raise ValueError('009 model output scope differs')
    required=c.merge_pins(required,outputs)
    for name in [a.CLAIM,*ABLAT_PROOFS]:
        if name not in approval['fingerprints']:raise ValueError('Missing009 claim/proof pin')
        required=c.merge_pins(required,{name:approval['fingerprints'][name]})
    if required!=approval['fingerprints']:raise ValueError('009 source acceptance must have exact actual203 scope')
    c.verify_pins(required,check)
    if c.canonical_json(read(local(execution['path'])))!=c.canonical_json(dict(version=1,approved=True,scope=a.ROLE,run_id=expected['run_id'],fingerprints=expected['identity']['fingerprints'])):
        raise ValueError('009 execution approval differs')
    claim=read(local(a.CLAIM))
    if c.canonical_json(claim)!=c.canonical_json(dict(version=1,scope=a.ROLE,run_id=expected['run_id'],allowed_fit_attempts=1,
        consumed_before='matrix_Pool_fit_preparation',output_directory=relative(directory))):
        raise ValueError('009 consumed claim differs')
    return inputs,c.merge_pins(required,{relative(path):sha(path)})


def prepare_plan(grid_path,base_config,train_path,selection_path,ablation_acceptance,*,check=lambda:None):
    from scripts import train_baselines as b
    from scripts import metadata_ablation as a
    c=helpers();spec,spec_sha=load_spec(grid_path)
    inputs,pins=verify_rejected_ablation(ablation_acceptance,base_config,train_path,selection_path,check=check)
    names=b.numeric_feature_names(inputs['train']['feature_columns'])
    if len(names)!=41 or names!=b.numeric_feature_names(inputs['selection']['feature_columns']):raise ValueError('Frozen base41 schema differs')
    pins=c.merge_pins(pins,{relative(grid_path):spec_sha})
    for name in [*a.CODE,'scripts/strong_baseline.py']:pins=c.merge_pins(pins,{name:sha(local(name))});check()
    identity=dict(version=1,role=ROLE,spec=spec,fingerprints=pins,feature_names=names,
        acceptance_refs=dict(train=relative(train_path),selection=relative(selection_path),ablation=relative(ablation_acceptance)),
        base_config=relative(base_config),incumbent=inputs['control']['control'],incumbent_run_id=inputs['control']['manifest']['run_id'],
        collection_ids={r:inputs[r]['plan']['collection_id'] for r in ['train','selection']},environment=a.environment_snapshot(),
        clock_policy='retrospective_development_whole_decision_after_labels24_plus_compute_before_reserved25')
    return dict(run_id=digest(identity),identity=identity),inputs


class Budget:
    """One dedicated parent's SELF+reapedCHILDREN delta, never receipt sums."""
    def __init__(self,spec,*,started=ENTRY_MONO,self_started=None,children_started=None):
        self.limits=spec['limits'];self.started=started
        # Actual CLI is a fresh dedicated process: absolute counters include
        # interpreter/import CPU. Tests may inject a later baseline.
        self.self_started=0. if self_started is None else self_started
        self.children_started=0. if children_started is None else children_started
        self.outer_deadline=started+self.limits['wall_seconds']
        self.producer_deadline=self.outer_deadline-self.limits['verification_wall_reserve']
    def cpu(self):
        value=self_cpu()-self.self_started+child_cpu()-self.children_started
        if value<0:raise ValueError('Nonmonotonic actual parent/children CPU')
        return value
    def guard(self):
        if time.monotonic()>self.producer_deadline:raise TimeoutError('Producer absolute wall budget exhausted')
        if self.cpu()>self.limits['cpu_seconds']-self.limits['verification_cpu_reserve']:raise TimeoutError('Producer actual CPU budget exhausted')
        if rss()>self.limits['parent_rss_bytes']:raise MemoryError('Parent orchestration RSS ceiling1GiB')
    def allocation(self,mode):
        self.guard();remaining_cpu=self.limits['cpu_seconds']-self.cpu()-self.limits['verification_cpu_reserve']-self.limits['parent_launch_cpu_reserve']
        deadline=self.producer_deadline-self.limits['cleanup_wall_reserve']
        if mode=='gate':deadline=min(deadline,time.monotonic()+self.limits['gate_wall_seconds']-self.limits['cleanup_wall_reserve'])
        if remaining_cpu<1 or deadline<=time.monotonic():raise TimeoutError('No bounded worker allowance remains')
        return dict(cpu_seconds=int(remaining_cpu),deadline_monotonic=deadline,rss_bytes=self.limits['worker_rss_bytes'])


def run_process(argv,log_path,*,budget,allocation,grace=5,reap=5,max_log=2**20):
    """Owned isolated group; normal leader exit must leave no descendant.

    An unexpected surviving group has unknown descendant usage, even if
    cleanup succeeds. It is an integrity failure, never a resource fallback.
    """
    started_self=self_cpu();process=None;error=None;cleanup_errors=[]
    def group_alive():
        if process is None:return False
        try:os.killpg(process.pid,0);return True
        except ProcessLookupError:return False
    def cleanup():
        if process is None:return
        for sig,seconds in [(signal.SIGTERM,grace),(signal.SIGKILL,reap)]:
            deadline=time.monotonic()+seconds
            if group_alive():
                try:os.killpg(process.pid,sig)
                except ProcessLookupError:pass
            # Always wait the direct child, including after group lookup races.
            # Its process object must never be abandoned with returncode=None.
            try:process.wait(timeout=max(.001,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:pass
            while time.monotonic()<deadline:
                process.poll()
                if process.returncode is not None and not group_alive():return
                time.sleep(min(.02,max(0,deadline-time.monotonic())))
        raise RuntimeError('Owned group could not be verified gone/reaped; unknown usage STOP')
    with Path(log_path).open('xb') as log:
        try:
            process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=ROOT)
            while process.poll() is None:
                budget.guard()
                if time.monotonic()>allocation['deadline_monotonic']:raise TimeoutError('Worker absolute wall deadline')
                if self_cpu()-started_self>budget.limits['parent_launch_cpu_reserve']-20:raise TimeoutError('Live parent CPU reserve threatened')
                if log.tell()>max_log or Path(log_path).stat().st_size>max_log:raise RuntimeError('Worker log budget exceeded')
                time.sleep(.05)
            process.wait();budget.guard()
            if group_alive():raise RuntimeError('Forbidden surviving owned-group descendants; unknown usage STOP')
            if Path(log_path).stat().st_size>max_log:raise RuntimeError('Worker log budget exceeded')
            if process.returncode<0:raise RuntimeError('Worker signal exit has unknown failure cause: '+str(process.returncode))
            return process.returncode
        except BaseException as value:error=value;raise
        finally:
            try:cleanup()
            except Exception as extra:
                if error is None:error=extra
                cleanup_errors.append(repr(extra))
            if cleanup_errors:
                cleanup_error=RuntimeError('Owned worker cleanup not fully verified: '+repr(cleanup_errors))
                evidence=Path(str(log_path)+'.cleanup-failed.json')
                try:evidence.write_text(json.dumps(dict(primary=repr(error),cleanup_errors=cleanup_errors,pid=process.pid if process else None))+'\n')
                except Exception as secondary:cleanup_error.add_note('Cleanup evidence persistence failed: '+repr(secondary))
                if error is not None:
                    error.add_note(str(cleanup_error))
                    # If there was no original body exception, cleanup itself
                    # must still fail the otherwise successful invocation.
                    if sys.exc_info()[0] is None:raise error
                else:raise cleanup_error


def choose(candidates,*,floor=.5792133072407045):
    import math
    eligible=[]
    for item in candidates:
        score=item['metrics']['conditional_macro_query']
        if not math.isfinite(score['ndcg']) or not math.isfinite(score['recall']):raise ValueError('Invalid external selection metrics')
        if score['recall']>=floor:eligible.append(item)
    if not eligible:raise ValueError('No feasible frozen control; STOP/no refill')
    maximum=max(v['metrics']['conditional_macro_query']['ndcg'] for v in eligible)
    tied=[v for v in eligible if v['metrics']['conditional_macro_query']['ndcg']>=maximum-1e-12]
    return min(tied,key=lambda v:(v['trees'],v['depth'],not v['incumbent'],v['config_id']))


def parent_claim(plan,approval,directory):
    body=dict(version=1,scope=ROLE,run_id=plan['run_id'],allowed_fit_attempts=4,allowed_gate_attempts=1,
        allowed_look_slots=12,output_directory=relative(directory),execution_approval=approval,
        slot_paths=[relative(directory/'slots'/name) for name in ['gate.json',*[f'arm-{i}.json' for i in range(4)]]])
    path=local(CLAIM);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as handle:handle.write(helpers().canonical_json(body)+'\n')
    return dict(path=CLAIM,sha256=sha(path))


def allocate_slot(directory,parent,mode,index,population,budget):
    name='gate' if mode=='gate' else 'arm-'+str(index)
    slot_path=directory/'slots'/(name+'.json');context_path=directory/'slots'/(name+'-context.json')
    slot=dict(version=1,parent_run_id=parent['run_id'],mode=mode,index=index,population=population,token=uuid.uuid4().hex,
        allocation=budget.allocation(mode),look_reservations=[] if mode=='gate' else [50,150,300],
        context_path=relative(context_path),output_root=relative(directory/'workers'/name))
    slot_path.parent.mkdir(parents=True,exist_ok=True)
    with slot_path.open('x') as handle:handle.write(helpers().canonical_json(slot)+'\n')
    context=dict(version=1,parent_plan_path=relative(directory/'plan.json'),slot_path=relative(slot_path),slot_sha256=sha(slot_path))
    with context_path.open('x') as handle:handle.write(helpers().canonical_json(context)+'\n')
    return slot,context_path,sha(context_path)


def verify_worker_context(path,*,issued_context_sha256):
    c=helpers();c._hashes({'issued_context':issued_context_sha256},'issuer launch digest')
    if sha(path)!=issued_context_sha256:raise ValueError('Worker context changed from immutable issuer launch digest')
    context=read(path)
    c._keys(context,{'version','parent_plan_path','slot_path','slot_sha256'},'worker context')
    if type(context['version']) is not int or context['version']!=1:raise ValueError('Worker context version')
    parent=read(local(context['parent_plan_path']))
    c._keys(parent,{'run_id','identity','execution_approval','budget_claim'},'approved parent plan')
    if parent['identity']['role']!=ROLE or digest(parent['identity'])!=parent['run_id'] or c.canonical_json(parent['identity']['spec'])!=c.canonical_json(specification()):
        raise ValueError('Worker parent identity/spec mismatch')
    approval=parent['execution_approval'];c.verify_pins({approval['path']:approval['sha256']})
    expected=dict(version=1,approved=True,scope=ROLE,run_id=parent['run_id'],fingerprints=parent['identity']['fingerprints'])
    actual=read(local(approval['path']))
    if type(actual.get('version')) is not int or actual.get('approved') is not True or actual!=expected:raise ValueError('Worker requires exact external parent approval')
    claim_ref=parent['budget_claim']
    if claim_ref['path']!=CLAIM:raise ValueError('Worker project claim path differs')
    c.verify_pins({CLAIM:claim_ref['sha256']})
    directory=local(context['parent_plan_path']).parent
    expected_claim=dict(version=1,scope=ROLE,run_id=parent['run_id'],allowed_fit_attempts=4,allowed_gate_attempts=1,
        allowed_look_slots=12,output_directory=relative(directory),execution_approval=approval,
        slot_paths=[relative(directory/'slots'/n) for n in ['gate.json',*[f'arm-{i}.json' for i in range(4)]]])
    if helpers().canonical_json(read(local(CLAIM)))!=helpers().canonical_json(expected_claim):raise ValueError('Worker immutable global allowance differs')
    if context['slot_path'] not in expected_claim['slot_paths']:raise ValueError('Unallocated worker slot')
    c.verify_pins({context['slot_path']:context['slot_sha256']});slot=read(local(context['slot_path']))
    c._keys(slot,{'version','parent_run_id','mode','index','population','token','allocation','look_reservations','context_path','output_root'},'issued slot')
    if type(slot['version']) is not int or slot['version']!=1 or type(slot['population']) is not int:
        raise ValueError('Worker slot integer fields differ')
    if not isinstance(slot['token'],str) or len(slot['token'])!=32 or any(x not in '0123456789abcdef' for x in slot['token']):
        raise ValueError('Invalid issued slot token')
    if any(type(k) is not int for k in slot['look_reservations']):raise ValueError('Look reservations must be strict integers')
    mode,index=slot['mode'],slot['index']
    if mode=='gate':
        if index is not None or slot['population']!=26000 or slot['look_reservations']!=[]:raise ValueError('Gate scope differs')
        name='gate'
    elif mode=='arm':
        if type(index) is not int or not 0<=index<4 or slot['population'] not in [6000,26000] or slot['look_reservations']!=[50,150,300]:raise ValueError('Arm scope differs')
        name='arm-'+str(index)
    else:raise ValueError('Unknown worker role')
    if (context['slot_path']!=relative(directory/'slots'/(name+'.json')) or slot['context_path']!=relative(path)
            or slot['output_root']!=relative(directory/'workers'/name) or slot['parent_run_id']!=parent['run_id']):
        raise ValueError('Worker slot/context/output detached')
    allocation=slot['allocation'];c._keys(allocation,{'cpu_seconds','deadline_monotonic','rss_bytes'},'worker allocation')
    if (type(allocation['cpu_seconds']) is not int or not 1<=allocation['cpu_seconds']<=3240
            or type(allocation['rss_bytes']) is not int or allocation['rss_bytes']!=7*2**30 or type(allocation['deadline_monotonic']) not in (int,float)
            or not time.monotonic()<allocation['deadline_monotonic']<=time.monotonic()+3600):
        raise ValueError('Invalid issued worker budget')
    return parent,slot,context


def resource_failure(error):
    import duckdb
    return isinstance(error,(MemoryError,TimeoutError,duckdb.OutOfMemoryException))


def worker_main(path,*,issued_context_sha256):
    from dataclasses import asdict
    from catboost import CatBoostClassifier,Pool
    import numpy as np
    from scripts import model_data as d
    from scripts import train_baselines as b
    from scripts.ranking_metrics import evaluate
    c=helpers();parent,slot,context=verify_worker_context(path,issued_context_sha256=issued_context_sha256);allocation=slot['allocation']
    class WorkerAudit(c.ExecutionAudit):
        def guard(self):
            super().guard()
            if time.monotonic()>allocation['deadline_monotonic']:raise TimeoutError('Issued worker absolute deadline')
            if self_cpu()>allocation['cpu_seconds']:raise TimeoutError('Worker entry actual CPU allowance')
            if rss()>allocation['rss_bytes']:raise MemoryError('Worker RSS ceiling7GiB')
            if child_cpu()!=0:raise RuntimeError('Worker spawned forbidden OS subprocess')
        def __exit__(self,kind,error,traceback):
            self.report['entry_actual_cpu_seconds']=self_cpu()
            self.report['entry_reaped_children_cpu_seconds']=child_cpu()
            if error is not None:self.report['outcome']='resource_failure' if resource_failure(error) else 'integrity_or_API_failure'
            try:return super().__exit__(kind,error,traceback)
            except BaseException as terminal:
                self.report.update(status='failed',outcome='resource_failure' if resource_failure(terminal) else 'integrity_or_API_failure')
                try:write(self.directory/'report.json',self.report)
                except Exception as secondary:
                    try:(self.directory/'report.failed.json').write_text(helpers().canonical_json(self.report)+'\n')
                    except Exception:pass
                    terminal.add_note('Secondary worker failure persistence: '+repr(secondary))
                raise
    with WorkerAudit(ROOT/'artifacts/strong-worker-attempts',seconds=max(1,int(allocation['deadline_monotonic']-time.monotonic())),
        scope='strong_'+slot['mode']+'_worker',cpu_seconds=allocation['cpu_seconds']) as audit:
        consumed=local(context['slot_path']).with_suffix('.consumed.json')
        with consumed.open('x') as handle:handle.write(helpers().canonical_json(dict(version=1,parent_run_id=parent['run_id'],token=slot['token'],context_sha256=sha(path)))+'\n')
        expected=expected_worker(parent,slot,context,path);identity=expected['identity'];pins=identity['fingerprints']
        worker_id=expected['run_id'];directory=local(slot['output_root'])/worker_id
        if directory.exists():raise FileExistsError('Immutable worker preserved; no refill')
        directory.parent.mkdir(parents=True,exist_ok=True);audit.directory.rename(directory);audit.directory=directory;audit.ledger.directory=directory/'profiles'
        audit.manifest=dict(run_id=worker_id,identity=identity);audit.report.update(run_id=worker_id,parent_run_id=parent['run_id'],
            mode=slot['mode'],index=slot['index'],population=slot['population'],labels_loaded=True,outcome='preparing',
            look_reservations=[dict(trees=k,status='reserved_consumed') for k in slot['look_reservations']])
        audit.stage('verify_approved_actual_inputs',lambda:c.verify_pins(pins,audit.guard))
        refs=parent['identity']['acceptance_refs']
        collections={role:audit.stage('verify_'+role,lambda role=role:c.verify_collection_strict(local(refs[role]),check=audit.guard)) for role in ['train','selection']}
        for role in collections:
            if collections[role]['plan']['collection_id']!=parent['identity']['collection_ids'][role]:raise ValueError('Worker base collection changed')
        population=slot['population'];max_rows=population*220
        train=audit.stage('train_matrix',lambda:d.prepare_model_data(collections['train'],max_queries=population,max_rows=max_rows,check=audit.guard))
        if len(train.queries)!=population or train.feature_names!=parent['identity']['feature_names'] or train.categorical is not None:
            raise ValueError('Worker population/base41 schema mismatch')
        _,_,_,_,weights,summary=b.group_accounting(train)
        if np.unique(train.y).size!=2:raise ValueError('Observed train support needs both classes')
        pool=audit.stage('train_Pool',lambda:Pool(train.x,label=train.y,weight=weights,feature_names=train.feature_names,thread_count=2))
        audit.report.update(training=summary,preparation=train.preparation,feature_names=train.feature_names)
        if slot['mode']=='gate':audit.report.update(status='complete_produced_unreviewed',outcome='gate_pass')
        else:
            arm=parent['identity']['spec']['grid'][slot['index']]
            params=model_parameters(arm)
            model=CatBoostClassifier(**params);callback=b._BudgetCallback(audit.guard)
            def fit():
                audit.report['fit_attempt_count']=1;model.fit(pool,callbacks=[callback])
                if callback.failure is not None:raise callback.failure
                if model.tree_count_!=300 or model.feature_names_!=train.feature_names:raise ValueError('Incomplete300tree fit/schema')
            audit.stage('one_fixed300fit',fit)
            actual=validate_parameters(model,parent['identity']['incumbent']['actual_model_parameters'],arm)
            selection=audit.stage('selection_matrix',lambda:d.prepare_model_data(collections['selection'],max_queries=None,max_rows=880000,check=audit.guard))
            if len(selection.queries)!=4000 or selection.feature_names!=train.feature_names:raise ValueError('Selection fixed4000/base41 mismatch')
            full=directory/'full300.cbm';full_json=directory/'full300.json'
            audit.stage('save_full300',lambda:model.save_model(str(full)))
            audit.stage('save_full300_JSON',lambda:model.save_model(str(full_json),format='json'))
            validate_saved_full(full_json)
            outputs={relative(p):sha(p) for p in [full,full_json]};checkpoints=[]
            for look,k in zip(audit.report['look_reservations'],[50,150,300]):
                scores=audit.stage('predict_prefix'+str(k),lambda k=k:model.predict(selection.x,ntree_end=k,prediction_type='RawFormulaVal',thread_count=2))
                prefix=model.copy();prefix.shrink(k)
                model_path=directory/('prefix'+str(k)+'.cbm');score_path=directory/('prefix'+str(k)+'-scores.npz')
                audit.stage('save_prefix'+str(k),lambda:prefix.save_model(str(model_path)))
                loaded=CatBoostClassifier();loaded.load_model(str(model_path))
                replay=audit.stage('replay_saved_prefix'+str(k),lambda:loaded.predict(selection.x,prediction_type='RawFormulaVal',thread_count=2))
                if loaded.tree_count_!=k or not np.allclose(scores,replay,rtol=0,atol=1e-12):raise ValueError('Saved prefix fidelity failure')
                rows=audit.stage('rank_prefix'+str(k),lambda:b.rankings(selection,scores))
                look['status']='seen_evaluation_started';write(directory/'report.json',audit.report)
                metrics=audit.stage('external_fullY_prefix'+str(k),lambda:asdict(evaluate(rows,20)))
                audit.stage('save_scores'+str(k),lambda:np.savez_compressed(score_path,group=selection.group,product_id=selection.items,raw_score=np.asarray(scores)))
                artifacts={relative(p):sha(p) for p in [model_path,score_path]};outputs.update(artifacts)
                checkpoints.append(dict(config_id=digest(arm),incumbent=False,trees=k,trained_iterations=300,depth=arm['depth'],
                    l2_leaf_reg=arm['l2_leaf_reg'],population=population,metrics=metrics,artifacts=artifacts,model_path=relative(model_path),score_path=relative(score_path)))
                look.update(status='seen_complete',metrics=metrics);write(directory/'report.json',audit.report)
                del prefix,loaded,replay,rows
            audit.manifest['outputs']=outputs
            audit.report.update(outcome='arm_complete',status='complete_produced_unreviewed',checkpoints=checkpoints,actual_model_parameters=actual,artifacts=outputs)
        audit.stage('final_input_pins',lambda:c.verify_pins(pins,audit.guard))
    print(json.dumps(dict(status=audit.report['status'],outcome=audit.report['outcome'],report=relative(audit.directory/'report.json'))),flush=True)
    return audit.report


def expected_worker(parent,slot,context,path):
    c=helpers()
    pins=c.merge_pins(parent['identity']['fingerprints'],{context['parent_plan_path']:sha(local(context['parent_plan_path'])),
        context['slot_path']:context['slot_sha256'],relative(path):sha(path),CLAIM:parent['budget_claim']['sha256'],
        parent['execution_approval']['path']:parent['execution_approval']['sha256']})
    identity=dict(version=1,role='strong_'+slot['mode']+'_worker',parent_run_id=parent['run_id'],slot=slot,
        fingerprints=pins,context_sha256=sha(path))
    return dict(run_id=digest(identity),identity=identity)


def invoke_worker(directory,parent,slot,path,budget,*,issued_context_sha256):
    actual_parent,actual_slot,context=verify_worker_context(path,issued_context_sha256=issued_context_sha256)
    if helpers().canonical_json(actual_parent)!=helpers().canonical_json(parent) or helpers().canonical_json(actual_slot)!=helpers().canonical_json(slot):
        raise ValueError('Worker launch differs from parent in-memory issued scope')
    expected=expected_worker(parent,slot,context,path)
    output=local(slot['output_root'])/expected['run_id']
    log=directory/'logs'/('gate.log' if slot['mode']=='gate' else 'arm-'+str(slot['index'])+'.log')
    log.parent.mkdir(parents=True,exist_ok=True)
    argv=[sys.executable,'-m','scripts.strong_baseline','--worker-context',relative(path),'--issued-context-sha256',issued_context_sha256]
    launch_ref=record_launch(log,parent,slot,path,issued_context_sha256,expected,argv)
    code=run_process(argv,log,budget=budget,allocation=slot['allocation'],grace=5,reap=5)
    if sha(path)!=issued_context_sha256:raise ValueError('Issued context changed during worker execution')
    if (output/'report.failed.json').exists() or Path(str(log)+'.cleanup-failed.json').exists():raise ValueError('Known failed worker persistence/cleanup receipt')
    report=read(output/'report.json');manifest=read(output/'run.json')
    if helpers().canonical_json(manifest['identity'])!=helpers().canonical_json(expected['identity']) or manifest['run_id']!=expected['run_id'] or report.get('run_id')!=expected['run_id']:
        raise ValueError('Worker output/receipt detached from allocated scope')
    consumed=read(local(context['slot_path']).with_suffix('.consumed.json'))
    if helpers().canonical_json(consumed)!=helpers().canonical_json(dict(version=1,parent_run_id=parent['run_id'],token=slot['token'],context_sha256=sha(path))):
        raise ValueError('Worker slot was not consumed exactly once')
    if (type(report.get('fit_attempt_count')) is not int or report['fit_attempt_count'] not in ([0] if slot['mode']=='gate' else [0,1])
            or report.get('parent_run_id')!=parent['run_id'] or report.get('mode')!=slot['mode']
            or helpers().canonical_json(report.get('index'))!=helpers().canonical_json(slot['index'])
            or helpers().canonical_json(report.get('population'))!=helpers().canonical_json(slot['population'])):
        raise ValueError('Worker population/fit-count scope differs')
    if code==0:
        validate_complete_worker(parent,slot,expected,output,manifest,report,budget)
    elif (code!=1 or report['status']!='failed' or report.get('outcome')!='resource_failure'
            or report.get('error_type') not in {'MemoryError','TimeoutError','OutOfMemoryException'}):
        raise RuntimeError('Worker integrity/API/unknown failure; STOP/no refill')
    return dict(report=report,manifest=manifest,directory=relative(output),exit_code=code,
        report_sha256=sha(output/'report.json'),manifest_sha256=sha(output/'run.json'),launch_receipt=launch_ref)


def record_launch(log,parent,slot,context_path,issued_sha,expected,argv):
    """Exclusive durable copy of the exact in-memory issuance before spawn."""
    path=Path(log).with_suffix('.launch.json')
    body=dict(version=1,scope='strong_issued_worker_launch',parent_run_id=parent['run_id'],worker_run_id=expected['run_id'],
        context_path=relative(context_path),issued_context_sha256=issued_sha,slot=deepcopy(slot),argv=list(argv),
        cwd=str(ROOT.resolve()),log_path=relative(log))
    with path.open('x') as handle:handle.write(helpers().canonical_json(body)+'\n')
    return dict(path=relative(path),sha256=sha(path))


def validate_complete_worker(parent,slot,expected,directory,manifest,report,budget):
    c=helpers();gate=slot['mode']=='gate'
    c._keys(manifest,{'run_id','identity'} if gate else {'run_id','identity','outputs'},'complete worker manifest')
    if (report.get('status')!='complete_produced_unreviewed' or report.get('outcome')!=('gate_pass' if gate else 'arm_complete')
            or report.get('scope')!='strong_'+slot['mode']+'_worker' or report.get('feature_names')!=parent['identity']['feature_names']
            or report.get('training',{}).get('queries')!=slot['population']):
        raise ValueError('Incomplete worker model/schema/population receipt')
    if gate:
        if report.get('look_reservations')!=[] or report['fit_attempt_count']!=0:raise ValueError('Gate contains fit/look outputs')
        return
    if report['fit_attempt_count']!=1:raise ValueError('Arm requires one completed fit')
    arm=parent['identity']['spec']['grid'][slot['index']]
    actual=report.get('actual_model_parameters',{})
    class ReportModel:
        def get_all_params(self):return actual
    validate_parameters(ReportModel(),parent['identity']['incumbent']['actual_model_parameters'],arm)
    names=['full300.cbm','full300.json',*[name for k in [50,150,300] for name in [f'prefix{k}.cbm',f'prefix{k}-scores.npz']]]
    required={relative(directory/name) for name in names};outputs=manifest['outputs']
    if set(outputs)!=required or report.get('artifacts')!=outputs:raise ValueError('Arm requires exact eight model/score outputs')
    c._hashes(outputs,'arm outputs');c.verify_pins(outputs,budget.guard)
    if any(local(name).stat().st_size==0 for name in required):raise ValueError('Empty required model/score artifact')
    validate_saved_full(directory/'full300.json')
    checkpoints=report.get('checkpoints',[]);looks=report.get('look_reservations',[])
    if len(checkpoints)!=3 or len(looks)!=3:raise ValueError('Complete arm must contain three consumed/seen looks')
    for k,checkpoint,look in zip([50,150,300],checkpoints,looks):
        c._keys(checkpoint,{'config_id','incumbent','trees','trained_iterations','depth','l2_leaf_reg','population',
            'metrics','artifacts','model_path','score_path'},'complete checkpoint')
        fixed=dict(config_id=digest(arm),incumbent=False,trees=k,trained_iterations=300,**arm,population=slot['population'],
            model_path=relative(directory/f'prefix{k}.cbm'),score_path=relative(directory/f'prefix{k}-scores.npz'))
        if any(c.canonical_json(checkpoint[name])!=c.canonical_json(value) for name,value in fixed.items()):raise ValueError('Checkpoint differs from issued grid/population/procedure')
        required_checkpoint={fixed[name]:outputs[fixed[name]] for name in ['model_path','score_path']}
        if checkpoint['artifacts']!=required_checkpoint:raise ValueError('Checkpoint model/score artifact scope differs')
        if (type(look.get('trees')) is not int or look['trees']!=k or look.get('status')!='seen_complete'
                or look.get('metrics')!=checkpoint['metrics']):raise ValueError('Consumed/seen checkpoint ledger differs')
        metrics=checkpoint['metrics'];validate_metrics(metrics)


def validate_metrics(metrics):
    import math
    required={'k','query_count','mature_query_count','censored_query_count','nonempty_query_count','mature_user_count',
        'positive_user_count','nonempty_fraction','conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero'}
    helpers()._keys(metrics,required,'external fullY metrics')
    for name in required-{'nonempty_fraction','conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero'}:
        if type(metrics[name]) is not int or metrics[name]<0:raise ValueError('Metric counts must be strict nonnegative integers')
    if (metrics['k']!=20 or metrics['query_count']!=4000 or metrics['mature_query_count']!=4000 or metrics['censored_query_count']!=0
            or not 0<=metrics['nonempty_query_count']<=4000 or metrics['nonempty_fraction']!=metrics['nonempty_query_count']/4000):
        raise ValueError('Metric query/maturity population differs')
    for name in ['conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero']:
        helpers()._keys(metrics[name],{'recall','ndcg','average_precision','reciprocal_rank'},'external metric means')
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in metrics[name].values()):
            raise ValueError('Invalid external metric mean')


def run(grid_path,base_config,train_path,selection_path,ablation_acceptance,*,execution_approval,started_monotonic=ENTRY_MONO):
    c=helpers();spec,_=load_spec(grid_path);budget=Budget(spec,started=started_monotonic)
    directory=ROOT/'artifacts/strong-baseline'/('attempt-'+uuid.uuid4().hex);directory.mkdir(parents=True,exist_ok=False)
    report=dict(version=1,status='running',scope=ROLE,fit_attempt_count=0,children=[],unknown_live_fit=False,
        outer_deadline_monotonic=budget.outer_deadline,producer_deadline_monotonic=budget.producer_deadline,
        outer_deadline_utc=datetime.fromtimestamp(time.time()+budget.outer_deadline-time.monotonic(),tz=timezone.utc).isoformat(),
        cpu_accounting='fresh_parent_absolute_SELF_plus_reaped_CHILDREN_not_worker_receipt_sums',
        retrospective_development=True,reserved_targets_opened=False)
    write(directory/'report.json',report);parent=None;error=None
    try:
        plan,inputs=prepare_plan(grid_path,base_config,train_path,selection_path,ablation_acceptance,check=budget.guard)
        approval=read(execution_approval)
        if (type(approval.get('version')) is not int or approval.get('approved') is not True or approval!=dict(version=1,approved=True,
            scope=ROLE,run_id=plan['run_id'],fingerprints=plan['identity']['fingerprints'])):
            raise ValueError('Exact external strong-search execution approval required')
        identified=directory.parent/plan['run_id']
        if identified.exists():raise FileExistsError('Immutable strong search preserved; no refill')
        directory.rename(identified);directory=identified
        approval_ref=dict(path=relative(execution_approval),sha256=sha(execution_approval))
        claim=parent_claim(plan,approval_ref,directory)
        parent={**deepcopy(plan), 'execution_approval':approval_ref,'budget_claim':claim}
        write(directory/'plan.json',parent)
        report.update(run_id=plan['run_id'],budget_claim=claim,spec=spec,feature_names=plan['identity']['feature_names'])
        gate,path,issued_sha=allocate_slot(directory,parent,'gate',None,26000,budget)
        gate_result=invoke_worker(directory,parent,gate,path,budget,issued_context_sha256=issued_sha);report['children'].append(gate_result)
        population=26000 if gate_result['exit_code']==0 else 6000
        report.update(population=population,population_decision='gate_pass_full26000' if population==26000 else 'recognized_gate_resource_failure_fresh6000')
        control=inputs['control']['control'];artifacts=control['artifacts']
        incumbent=dict(config_id='incumbent-'+inputs['control']['manifest']['run_id'],incumbent=True,trees=50,trained_iterations=50,
            depth=6,l2_leaf_reg=3,population=6000,metrics=control['metrics'],artifacts=artifacts,
            model_path=next(p for p in artifacts if p.endswith('.cbm')),score_path=next(p for p in artifacts if p.endswith('.npz')))
        candidates=[incumbent]
        for index in range(4):
            try:slot,path,issued_sha=allocate_slot(directory,parent,'arm',index,population,budget)
            except TimeoutError:
                report['unattempted_remaining_arms']=list(range(index,4));break
            report['unknown_live_fit']=True;write(directory/'report.json',report)
            result=invoke_worker(directory,parent,slot,path,budget,issued_context_sha256=issued_sha)
            report['unknown_live_fit']=False;report['children'].append(result)
            report['fit_attempt_count']=sum(v['report']['fit_attempt_count'] for v in report['children'])
            if result['exit_code']==0:candidates.extend(result['report']['checkpoints'])
            write(directory/'report.json',report)
        winner=choose(candidates)
        report.update(winner=winner,eligible_outputs=len(candidates),selection_law=spec['policy']['tie'],
            new_reserved_look_slots=3*sum(v['report']['mode']=='arm' for v in report['children']),
            actual_seen_looks=sum(sum(x['status'].startswith('seen') for x in v['report']['look_reservations']) for v in report['children']))
        c.verify_pins(c.merge_pins(plan['identity']['fingerprints'],{approval_ref['path']:approval_ref['sha256'],CLAIM:claim['sha256']}),budget.guard)
        if report['fit_attempt_count']>4 or report['new_reserved_look_slots']>12:raise ValueError('Frozen fit/look caps exceeded')
        worker_peak=max(v['report']['process_peak_rss_bytes'] for v in report['children'])
        if rss()+worker_peak>8*2**30:raise MemoryError('Conservative simultaneous parent+worker RSS bound exceeds8GiB')
        write(directory/'winner.json',winner)
        report.update(status='complete_produced_unreviewed',worker_peak_rss_bytes=worker_peak,
            simultaneous_rss_conservative_upper_bound=rss()+worker_peak)
        outputs=seal_outputs(directory)
        write(directory/'run.json',dict(**parent,outputs=outputs))
        budget.guard()
    except BaseException as value:error=value
    finally:error=finalize_parent(directory,report,budget,error)
    if error is not None:raise error
    return report


def model_parameters(arm):
    return dict(loss_function='Logloss',iterations=300,**arm,learning_rate=.05,random_seed=2026,thread_count=2,
        task_type='CPU',boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,
        leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,verbose=False,
        allow_writing_files=False,use_best_model=False)


def validate_parameters(model,control,arm):
    actual=model.get_all_params()
    keys=['loss_function','learning_rate','random_seed','task_type','boosting_type','bootstrap_type',
        'leaf_estimation_method','leaf_estimation_iterations','leaf_estimation_backtracking','random_strength',
        'boost_from_average','use_best_model','border_count','nan_mode','rsm']
    if any(actual.get(k)!=control.get(k) for k in keys) or any(actual.get(k)!=v for k,v in {**arm,'iterations':300}.items()):
        raise ValueError('Actual strong fit parameters drift from frozen control/grid')
    return actual


def validate_saved_full(path):
    body=read(path)
    if len(body.get('oblivious_trees',[]))!=300:raise ValueError('Saved full model lacks300trees')
    if body.get('features_info',{}).get('ctrs') or any(split.get('split_type')!='FloatFeature'
        for tree in body['oblivious_trees'] for split in (tree.get('splits') or [])):
        raise ValueError('Base41 model contains nonnumeric/CTR split')


def seal_outputs(directory):
    paths=[directory/'winner.json',directory/'plan.json']
    for name in ['slots','logs','workers']:
        paths.extend(p for p in (directory/name).rglob('*') if p.is_file() and 'temp' not in p.relative_to(directory/name).parts)
    return {relative(p):sha(p) for p in sorted(paths)}


def finalize_parent(directory,report,budget,error):
    """Terminal failures cannot leave a consumable complete receipt.

    Preserve the first body/cleanup error; all measurement/writer errors are
    attached and force a separate failed marker. Controller measures tail.
    """
    primary=error;secondary=[]
    def fail(value,stage):
        nonlocal primary
        if primary is None:primary=value
        else:primary.add_note(stage+': '+repr(value))
        secondary.append(dict(stage=stage,error_type=type(value).__name__,error=str(value)))
    requested=report.get('status')
    for stage,operation in [('terminal_guard',budget.guard),('measurements',lambda:report.update(
        seconds=time.monotonic()-budget.started,actual_parent_cpu_seconds=self_cpu(),
        actual_reaped_children_cpu_seconds=child_cpu(),actual_total_cpu_seconds=budget.cpu(),parent_peak_rss_bytes=rss(),
        verification_handoff=dict(absolute_deadline_monotonic=budget.outer_deadline,
            remaining_cpu_seconds=max(0,budget.limits['cpu_seconds']-budget.cpu()),
            remaining_wall_seconds=max(0,budget.outer_deadline-time.monotonic()),
            maximum_verifier_cpu_seconds=min(300,max(0,budget.limits['cpu_seconds']-budget.cpu())),cleanup_reserve_seconds=20),
        receipt_boundary='before_minimal_final_persistence_external_invocation_ledger_covers_tail'))]:
        try:operation()
        except BaseException as value:fail(value,stage)
    def persist():
        if primary is not None:report.update(status='failed',error_type=type(primary).__name__,error=str(primary),
            decision='STOP_no_model_promotion_no_refill',error_notes=getattr(primary,'__notes__',[]),terminal_errors=secondary)
        try:write(directory/'report.json',report)
        except BaseException as value:fail(value,'report_persistence')
    report['status']='finalizing' if primary is None else 'failed';persist()
    if primary is None:report['status']=requested
    persist()
    try:budget.guard()
    except BaseException as value:fail(value,'post_receipt_guard')
    if primary is not None:
        persist()
        try:(directory/'report.failed.json').write_text(helpers().canonical_json(report)+'\n')
        except BaseException as value:fail(value,'failed_marker_persistence')
    return primary


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-context',type=Path)
    parser.add_argument('--issued-context-sha256')
    for name in ['grid','base-config','train','selection','ablation','execution-approval']:parser.add_argument('--'+name,type=Path)
    parser.add_argument('--started-monotonic',type=float,default=ENTRY_MONO)
    args=parser.parse_args()
    if args.worker_context:
        if args.issued_context_sha256 is None:parser.error('Worker requires issuer-bound launch digest')
        return worker_main(local(str(args.worker_context)),issued_context_sha256=args.issued_context_sha256)
    if args.issued_context_sha256 is not None:parser.error('Issuer digest is only valid for worker entry')
    if any(getattr(args,k) is None for k in ['grid','base_config','train','selection','ablation','execution_approval']):parser.error('Parent requires all explicit input/approval paths')
    if not 0<=time.monotonic()-args.started_monotonic<=300:parser.error('Invalid external invocation clock')
    report=run(args.grid,args.base_config,args.train,args.selection,args.ablation,
        execution_approval=args.execution_approval,started_monotonic=args.started_monotonic)
    print(json.dumps(dict(status=report['status'],run_id=report['run_id'],winner=report['winner']['config_id'])),flush=True)


if __name__=='__main__':main()
