"""Reserved-reporting lifecycle primitives; not an executable reporting owner.

Six fixed-role contexts, persistent consumption, typed receipts and gate order.
The additive CLI/source/prediction/metric workers and actual budget request still
require separate review. No data/model/target operation is implemented here.
"""
import time
ENTRY_MONOTONIC=time.monotonic()
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys

ROLES=('source','source_oracle','predictions','prediction_oracle','targets_evaluation','metric_oracle')
ENTRY={name:'scripts/heldout_reporting_worker.py' for name in ['source','predictions','targets_evaluation']}
ENTRY.update(source_oracle='tests/oracles/heldout_source_worker.py',
    prediction_oracle='tests/oracles/heldout_prediction_worker.py',metric_oracle='tests/oracles/heldout_metric_worker.py')
CAPS=dict(zip(ROLES,[(900,1200),(900,1200),(600,900),(600,900),(300,600),(300,600)]))
LIMITS=dict(cpu_seconds=4200,wall_seconds=7200,parent_rss_bytes=2**30,worker_rss_bytes=7*2**30,
    job_rss_bytes=8*2**30,parent_launch_cpu_reserve=60,cleanup_wall_reserve=20,final_cpu_reserve=2)
GATES={'source':'reserved_source_inference_execution','predictions':'reviewed_reserved_source',
       'targets_evaluation':'report_only_reserved_fullY'}
INPUT_KEYS=dict(source={'lock','choice','source','pool','registry'},
    source_oracle={'lock','choice','source','pool','registry','source_manifest','source_receipt'},
    predictions={'lock','choice','source_acceptance','source_manifest'},
    prediction_oracle={'lock','choice','source_acceptance','source_manifest','prediction_manifest','prediction_receipt'},
    targets_evaluation={'lock','choice','source_acceptance','source_manifest','prediction_acceptance','prediction_inventory','target_intent'},
    metric_oracle={'lock','choice','source_acceptance','source_manifest','prediction_acceptance','prediction_inventory','target_intent','evaluation_manifest','evaluation_receipt'})


def need(condition,message):
    if not condition:raise ValueError(message)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def finite(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def ref(value):
    need(type(value) is dict and set(value)=={'path','sha256'},'Exact artifact reference required')
    name=value['path'];need(type(name) is str and name and not name.startswith('/') and
        all(p not in {'','.','..'} for p in name.split('/')) and '\\' not in name,'Normalized local reference required')
    need(type(value['sha256']) is str and len(value['sha256'])==64 and all(c in '0123456789abcdef' for c in value['sha256']),'SHA256 required')


def local(root,name):
    ref(dict(path=name,sha256='0'*64));path=(root/name).resolve();path.relative_to(root.resolve());return path


def read(path):
    with Path(path).open('rb') as stream:raw=stream.read(8*2**20+1)
    need(len(raw)<=8*2**20,'Bounded metadata exceeded')
    def unique(pairs):
        body={}
        for key,value in pairs:need(key not in body,'Duplicate JSON key');body[key]=value
        return body
    body=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    # parse_constant rejects literal Infinity/NaN, but 1e999 overflows silently.
    def finite_tree(value):
        if type(value) is float:need(math.isfinite(value),'Nonfinite JSON exponent overflow')
        elif type(value) is dict:
            for child in value.values():finite_tree(child)
        elif type(value) is list:
            for child in value:finite_tree(child)
    finite_tree(body)
    return body,hashlib.sha256(raw).hexdigest()


def sha(path,check=lambda:None):
    value=hashlib.sha256();check()
    with Path(path).open('rb') as stream:
        while part:=stream.read(2**20):check();value.update(part)
    check();return value.hexdigest()


def exclusive(path,body):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);raw=(canonical(body)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return dict(path=path,sha256=hashlib.sha256(raw).hexdigest())


def atomic(path,body):
    path=Path(path);part=path.with_name(path.name+'.writing')
    with part.open('x') as stream:stream.write(canonical(body)+'\n');stream.flush();os.fsync(stream.fileno())
    os.replace(part,path)


def counters():
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    peak=own.ru_maxrss if sys.platform=='darwin' else own.ru_maxrss*1024
    return own.ru_utime+own.ru_stime,child.ru_utime+child.ru_stime,int(peak)


class Budget:
    """One fresh absolute lifetime; no source prefix or worker cost is added twice."""
    def __init__(self,*,started=ENTRY_MONOTONIC):
        need(finite(started) and started<=time.monotonic(),'Original monotonic start required')
        self.started=started;self.outer_deadline=started+LIMITS['wall_seconds'];self.limits=deepcopy(LIMITS)
    def usage(self):
        own,children,peak=counters()
        need(finite(own) and finite(children) and type(peak) is int and peak>0,'Known absolute owner resources required')
        return own,children,peak
    def cpu(self):
        own,children,_=self.usage();return own+children
    def guard(self):
        own,children,peak=self.usage()
        if own+children>LIMITS['cpu_seconds']-LIMITS['final_cpu_reserve']:raise TimeoutError('Original shared heldout CPU exhausted')
        if time.monotonic()>self.outer_deadline-LIMITS['cleanup_wall_reserve']:raise TimeoutError('Original shared heldout wall exhausted')
        if peak>LIMITS['parent_rss_bytes']:raise MemoryError('Heldout parent RSS1GiB exceeded')
    def allocation(self,role):
        need(role in ROLES,'Unknown heldout role');self.guard();cpu_cap,wall_cap=CAPS[role]
        remaining=LIMITS['cpu_seconds']-self.cpu()-LIMITS['parent_launch_cpu_reserve']-LIMITS['final_cpu_reserve']
        cpu=min(cpu_cap,remaining);deadline=min(self.outer_deadline-LIMITS['cleanup_wall_reserve'],time.monotonic()+wall_cap)
        if cpu<1 or deadline<=time.monotonic():raise TimeoutError('No original role allowance remains')
        return dict(cpu_seconds=int(cpu),deadline_monotonic=deadline,rss_bytes=LIMITS['worker_rss_bytes'])


def validate_role_inputs(role,body):
    need(role in INPUT_KEYS and type(body) is dict and set(body)==INPUT_KEYS[role],'Exact role input vocabulary required')
    for value in body.values():ref(value)
    if role in ROLES[:4]:need(not any('target' in name or 'label' in name for name in body),'Label-blind role cannot receive targets')


def expected_paths(directory,role,choice):
    """Fixed output vocabulary only; file contents require independent semantics."""
    need(role in ROLES and choice in {'B','I1','I2','R1','R2'},'Frozen role/choice required')
    prefix=directory+'/'+role;names=[]
    if role=='source':
        for day in range(25,32):
            names.extend(f'day-{day}/{kind}.parquet' for kind in ['queries','candidates','base-features'])
            if choice!='B':names.append(f'day-{day}/extra-features.parquet')
        names.append('source-manifest.json')
    elif role=='predictions':
        for day in range(25,32):
            names.append(f'day-{day}/B.npz')
            if choice!='B':names.append(f'day-{day}/W.npz')
        names.append('prediction-manifest.json')
    elif role=='targets_evaluation':names=['full-targets.parquet','private-rankings.jsonl','evaluation.json']
    else:names=['evidence.json']
    return [prefix+'/'+name for name in names]


class Session:
    """Persistent role state, not a source/metric or external acceptance issuer.

    Constructor receives a *previously authenticated* frozen plan snapshot.
    Authenticating438/whole lock and the outer CLI are separate unfinished work.
    External gate content must be semantically checked by that future owner;
    record_gate requires its independently expected exact byte content.
    """
    def __init__(self,root,directory,plan,request,owner_claim,budget):
        self.root=Path(root).resolve();self.directory=local(self.root,directory);self.directory.mkdir(parents=True,exist_ok=True)
        need(type(plan) is dict and set(plan)=={'run_id','choice','fingerprints'},'Exact authenticated lifecycle plan required')
        need(type(plan['run_id']) is str and len(plan['run_id'])==64 and all(c in '0123456789abcdef' for c in plan['run_id']) and plan['choice'] in {'B','I1','I2','R1','R2'},'Plan identity/choice required')
        for name,value in plan['fingerprints'].items():ref(dict(path=name,sha256=value))
        for value in [request,owner_claim]:ref(value)
        self.plan=deepcopy(plan);self.request=deepcopy(request);self.claim=deepcopy(owner_claim);self.budget=budget
        self.states=[];self.gates={};self.active=None;self.authority_pins={};self.output_pins={}
        self.report=dict(version=1,status='prepared_lifecycle_only',run_id=plan['run_id'],roles=[],active_role=None,
            unknown_active_work=False,reserved_targets_may_have_been_opened=False,fit_attempt_count=0)
        # Existing session metadata prevents accidental same-directory recreation.
        exclusive(self.directory/'session.created.json',dict(plan=plan,request=request,owner_claim=owner_claim,
            original_start=budget.started,original_deadline=budget.outer_deadline))
        self.persist()
    def persist(self):atomic(self.directory/'report.json',self.report)
    def relative(self,path):return Path(path).resolve().relative_to(self.root).as_posix()
    def check_pins(self,pins):
        for name,value in pins.items():need(sha(local(self.root,name),self.budget.guard)==value,'Original authority/output bytes changed')
    def marker_check(self):
        need(not (self.directory/'report.failed.json').exists(),'Failed owner cannot be promoted')
        for role in ROLES:
            base=self.directory/role
            for name in ['report.failed.json','evidence.failed.json','worker.log.cleanup-failed.json']:
                need(not (base/name).exists(),'Known failed role/cleanup cannot be promoted')
    def record_gate(self,gate,reference,*,expected):
        need(gate in {'initial_execution','source_acceptance','prediction_acceptance','target_execution'},'Unknown external authority gate')
        need(gate not in self.gates and self.active is None,'Repeated/active external authority gate')
        after={'initial_execution':0,'source_acceptance':2,'prediction_acceptance':4,'target_execution':4}[gate]
        need(len(self.states)==after,'External authority out of fixed role order')
        if gate=='target_execution':need('prediction_acceptance' in self.gates,'Target grant before all-prediction seal')
        ref(reference);body,actual=read(local(self.root,reference['path']))
        need(actual==reference['sha256'] and canonical(body)==canonical(expected),'External authority differs from independently expected snapshot')
        need(type(body.get('version')) is int and body['version']==1 and body.get('approved') is True,'Typed external approved authority required')
        need(body.get('run_id')==self.plan['run_id'],'Authority run differs')
        scopes={'initial_execution':'reserved_source_inference_execution','source_acceptance':'reviewed_reserved_source',
                'prediction_acceptance':'reviewed_all_reserved_predictions_before_targets','target_execution':'report_only_reserved_fullY'}
        need(body.get('scope')==scopes[gate],'External authority scope differs')
        self.budget.guard();self.marker_check();self.gates[gate]=deepcopy(reference);self.authority_pins[reference['path']]=actual
        self.report['gates']=deepcopy(self.gates);self.persist()
    def issue(self,role,inputs):
        self.budget.guard();self.marker_check()
        need(self.active is None and len(self.states)<6 and role==ROLES[len(self.states)],'No role skip/replacement/retry')
        required={'source':'initial_execution','predictions':'source_acceptance','targets_evaluation':'target_execution'}.get(role)
        if required:need(required in self.gates,'Required external gate absent')
        if role=='targets_evaluation':need('prediction_acceptance' in self.gates,'All-seven prediction seal absent')
        validate_role_inputs(role,inputs);self.check_pins(self.authority_pins)
        entry=ENTRY[role];need(entry in self.plan['fingerprints'],'Fixed reviewed entry pin required')
        need(sha(local(self.root,entry),self.budget.guard)==self.plan['fingerprints'][entry],'Fixed worker entry changed')
        for name,value in inputs.items():need(self.plan['fingerprints'].get(value['path'],self.output_pins.get(value['path'],self.authority_pins.get(value['path'])))==value['sha256'],'Role input outside authenticated closure')
        base=self.directory/role;base.mkdir(exist_ok=False);allocation=self.budget.allocation(role)
        original=dict(version=1,scope='reserved_role_slot',role=role,ordinal=len(self.states),run_id=self.plan['run_id'],
            allocation=allocation,entry=dict(path=entry,sha256=self.plan['fingerprints'][entry]))
        slot=exclusive(base/'slot.json',original);slot_ref=dict(path=self.relative(slot['path']),sha256=slot['sha256'])
        prefix=self.relative(self.directory)
        context=dict(version=1,scope='issued_reserved_reporting_role',run_id=self.plan['run_id'],role=role,
            request=self.request,owner_claim=self.claim,plan=deepcopy(self.plan),slot=slot_ref,entry=original['entry'],allocation=allocation,
            issued_at_monotonic=time.monotonic(),inputs=deepcopy(inputs),expected_outputs=expected_paths(prefix,role,self.plan['choice']),
            output_path=self.relative(base/'receipt.json'),failed_path=self.relative(base/'report.failed.json'))
        saved=exclusive(base/'context.json',context);context_ref=dict(path=self.relative(saved['path']),sha256=saved['sha256'])
        argv=[str(self.root/'.venv/bin/python'),str(local(self.root,entry)),'--context',str(saved['path']),'--issued-context-sha256',saved['sha256']]
        launch=exclusive(base/'launch.json',dict(argv=argv,issued_context_sha256=saved['sha256'],original_slot=original,
            context=context_ref,entry=original['entry'],allocation=allocation))
        self.active=dict(context=deepcopy(context),context_ref=context_ref,slot=deepcopy(original),slot_ref=slot_ref,
            launch_ref=dict(path=self.relative(launch['path']),sha256=launch['sha256']),argv=argv)
        self.report.update(active_role=role,unknown_active_work=True,status='role_issued',
            reserved_targets_may_have_been_opened=self.report['reserved_targets_may_have_been_opened'] or role=='targets_evaluation')
        self.persist();return deepcopy(self.active)
    def accept_receipt(self,body,reference,*,exit_code,actual_reaped_cpu):
        need(self.active is not None,'No issued role');issued=self.active;context=issued['context'];role=context['role']
        exact={'version','scope','status','run_id','role','context','execution_consumed','inputs','outputs','evidence',
            'fit_attempt_count','labels_loaded','native_prediction_count','started_monotonic','finished_monotonic',
            'process_cpu_seconds','process_peak_rss_bytes','descendant_cpu_seconds'}
        need(type(body) is dict and set(body)==exact,'Exact complete child receipt required')
        need(type(exit_code) is int and exit_code==0,'Reaped exit0 required')
        need(type(body['version']) is int and body['version']==1 and body['scope']=='reserved_reporting_'+role and
            body['status']=='role_complete_unaccepted' and body['run_id']==self.plan['run_id'] and body['role']==role,'Child status/scope differs')
        need(body['context']==issued['context_ref'] and body['inputs']==context['inputs'],'Child authority/input association differs')
        need(type(body['fit_attempt_count']) is int and body['fit_attempt_count']==0 and body['labels_loaded'] is (role in ROLES[4:]),'Fit/target state differs')
        need(type(body['native_prediction_count']) is int and body['native_prediction_count']>=0,'Known native-call count required')
        if role not in {'predictions','prediction_oracle'}:need(body['native_prediction_count']==0,'Native call outside prediction role')
        need(body['descendant_cpu_seconds']==0 and type(body['descendant_cpu_seconds']) in (int,float),'Forbidden/unknown descendants')
        need(finite(actual_reaped_cpu) and finite(body['process_cpu_seconds']) and body['process_cpu_seconds']<=actual_reaped_cpu+1e-6
            and actual_reaped_cpu<=context['allocation']['cpu_seconds'],'Reaped actual CPU/body/issued cap differs')
        start,end=body['started_monotonic'],body['finished_monotonic'];need(finite(start) and finite(end) and
            context['issued_at_monotonic']<=start<=end<=context['allocation']['deadline_monotonic'] and end<=time.monotonic(),'Child original clock differs')
        peak=body['process_peak_rss_bytes'];need(type(peak) is int and 0<peak<=context['allocation']['rss_bytes'],'Child RSS7GiB exceeded/unknown')
        need(self.budget.usage()[2]+peak<=LIMITS['job_rss_bytes'],'Conservative whole-job RSS8GiB exceeded')
        need(type(body['outputs']) is dict and set(body['outputs'])==set(context['expected_outputs']),'Exact allocated output vocabulary required')
        for name,value in body['outputs'].items():ref(dict(path=name,sha256=value))
        ref(body['execution_consumed']);ref(body['evidence']);ref(reference)
        consumed_path=self.directory/role/'execution.consumed.json';need(body['execution_consumed']['path']==self.relative(consumed_path),'Child consumption destination differs')
        consumed,actual=read(consumed_path);need(actual==body['execution_consumed']['sha256'] and canonical(consumed)==canonical(dict(version=1,scope='reserved_child_execution_consumed',
            role=role,run_id=self.plan['run_id'],context=issued['context_ref'],slot=issued['slot_ref'])),'Child exclusive consumption association differs')
        need(reference['path']==context['output_path'],'Receipt destination changed')
        on_disk,actual=read(local(self.root,reference['path']));need(actual==reference['sha256'] and canonical(on_disk)==canonical(body),'Receipt body differs from immutable bytes')
        mandatory={issued['context_ref']['path']:issued['context_ref']['sha256'],issued['slot_ref']['path']:issued['slot_ref']['sha256'],
            issued['launch_ref']['path']:issued['launch_ref']['sha256'],body['execution_consumed']['path']:body['execution_consumed']['sha256'],
            body['evidence']['path']:body['evidence']['sha256'],reference['path']:reference['sha256']}
        need(body['evidence']['path'] in body['outputs'],'Evidence outside allocated output set')
        self.check_pins(mandatory);self.check_pins(body['outputs']);self.check_pins(self.authority_pins);self.marker_check();self.budget.guard()
        self.output_pins.update(body['outputs']);self.authority_pins.update(mandatory)
        record=dict(role=role,receipt=deepcopy(reference),actual_reaped_cpu_seconds=actual_reaped_cpu,
            child_reported_cpu_seconds=body['process_cpu_seconds'],process_peak_rss_bytes=peak,native_prediction_count=body['native_prediction_count'])
        self.states.append(record);self.active=None;self.report.update(roles=deepcopy(self.states),active_role=None,unknown_active_work=False,status='role_complete_unaccepted')
        self.persist();return deepcopy(record)
    def finish(self):
        try:
            need(self.active is None and len(self.states)==6 and set(self.gates)=={'initial_execution','source_acceptance','prediction_acceptance','target_execution'},'Six roles and four external gates required')
            self.marker_check();self.check_pins(self.output_pins);self.check_pins(self.authority_pins);self.check_pins(self.plan['fingerprints']);self.marker_check();self.budget.guard()
            self.report.update(status='finalizing');self.persist()
            self.marker_check();self.budget.guard();own,children,peak=self.budget.usage()
            self.report.update(status='verified_reporting_pending_external_lifetime_acceptance',actual_parent_cpu_seconds=own,
                actual_reaped_children_cpu_seconds=children,actual_total_cpu_seconds=own+children,parent_peak_rss_bytes=peak,
                seconds=time.monotonic()-self.budget.started,external_exit_tail_acceptance_required=True)
            self.persist()
            # Both persistence calls can expose late mutations; original snapshots
            # remain the authority. Final markers follow the last guarded stream.
            self.check_pins(self.output_pins);self.check_pins(self.authority_pins);self.check_pins(self.plan['fingerprints'])
            self.budget.guard();self.marker_check()
            return deepcopy(self.report)
        except BaseException as error:
            self.fail(error);raise
    def fail(self,error):
        self.report.update(status='failed',error_type=type(error).__name__,
            error='STOP original consumed reserved study; no refill/refit/target adaptation')
        # If a child receipt was missing, preserve active/unknown state rather than
        # inventing exact zero target/native work.
        try:self.persist()
        except BaseException as secondary:error.add_note('Failure summary persistence: '+type(secondary).__name__)
        try:exclusive(self.directory/'report.failed.json',self.report)
        except BaseException as secondary:error.add_note('Failure marker persistence: '+type(secondary).__name__)
        return deepcopy(self.report)
