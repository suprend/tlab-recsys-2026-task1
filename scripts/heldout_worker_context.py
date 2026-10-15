"""Issuer-bound reserved worker lifecycle; no source/model/target calculation.

Adapters capture their earliest stdlib clock and authenticate the raw context
SHA before importing this module. Actual execution requires the reviewed outer
owner/authority chain; a caller-authored approved:true is not self-acceptance.
"""
from copy import deepcopy
import importlib
import importlib.metadata
import math
import os
from pathlib import Path
import resource
import signal
import sys
import threading
import time
import tomllib

from scripts import heldout_execution as x
from scripts import heldout_contract as h

ROOT=Path(__file__).resolve().parents[1]
CONTEXT_KEYS={'version','scope','run_id','role','request','owner_claim','plan','slot','entry','allocation',
    'issued_at_monotonic','inputs','authorities','expected_outputs','output_path','failed_path'}
GATE_SCOPES=dict(initial_execution='reserved_source_inference_execution',source_acceptance='reviewed_reserved_source',
    prediction_acceptance='reviewed_all_reserved_predictions_before_targets',target_execution='report_only_reserved_fullY')


def local(name):return x.local(ROOT,name)
def relative(path):return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
def same(first,second):return x.canonical(first)==x.canonical(second)


def observed(reference,seen):
    x.ref(reference);body,digest=x.read(local(reference['path']));x.need(digest==reference['sha256'],'Original worker metadata changed')
    x.need(reference['path'] not in seen or seen[reference['path']]==digest,'Conflicting worker authority bytes')
    seen[reference['path']]=digest;return body


def gate_names(role):
    names={'initial_execution'}
    if role in x.ROLES[2:]:names.add('source_acceptance')
    if role in x.ROLES[4:]:names.update({'prediction_acceptance','target_execution'})
    return names


class RoleBudget:
    def __init__(self,allocation,started):
        x.need(type(allocation) is dict and set(allocation)=={'cpu_seconds','deadline_monotonic','rss_bytes'},'Exact role allocation required')
        x.need(type(allocation['cpu_seconds']) is int and allocation['cpu_seconds']>=3,'Role needs finalization reserve inside CPU')
        x.need(x.finite(started) and started<=time.monotonic() and x.finite(allocation['deadline_monotonic']),'Known original role clock')
        x.need(type(allocation['rss_bytes']) is int and allocation['rss_bytes']==7*2**30,'Fixed role RSS ceiling required')
        self._allocation=deepcopy(allocation);self.started=started;self.expired=threading.Event();self.stop_event=threading.Event();self.connections=[];self.thread=None;self.reason=None;self.kernel_cpu=None
    @property
    def allocation(self):return deepcopy(self._allocation)
    def resources(self):
        own,children,peak=x.counters();x.need(x.finite(own) and x.finite(children) and type(peak) is int and peak>0,'Known worker resource counters required')
        return own,children,peak
    def check_values(self):
        own,children,peak=self.resources()
        x.need(children==0,'Forbidden or unknown worker descendants')
        if own>self.allocation['cpu_seconds']-2:raise TimeoutError('Original worker actual CPU allowance exhausted')
        if time.monotonic()>self.allocation['deadline_monotonic']:raise TimeoutError('Original worker absolute wall expired')
        if peak>self.allocation['rss_bytes']:raise MemoryError('Worker RSS7GiB exceeded')
    def guard(self):
        if self.expired.is_set():raise self.reason or TimeoutError('Original worker persistent expiry')
        self.check_values()
    def install_cpu_fence(self):
        # Dedicated worker only. No promise that all Unix kernels have identical
        # tick/termination precision; successful actual counters still decide.
        cap=self.allocation['cpu_seconds'];previous=resource.getrlimit(resource.RLIMIT_CPU)
        x.need(previous[1]==resource.RLIM_INFINITY or previous[1]>=cap,'Inherited hardCPU below issued role cap')
        resource.setrlimit(resource.RLIMIT_CPU,(cap-1,cap))
        actual=resource.getrlimit(resource.RLIMIT_CPU);x.need(actual==(cap-1,cap),'CPU fence setup/readback failed')
        self.kernel_cpu=dict(soft=actual[0],hard=actual[1]);return deepcopy(self.kernel_cpu)
    def start_monitor(self):
        x.need(self.thread is None,'Role monitor cannot restart')
        def monitor():
            while not self.stop_event.wait(.05):
                try:self.check_values()
                except BaseException as error:
                    self.reason=error;self.expired.set()
                    for con in tuple(self.connections):
                        try:con.interrupt()
                        except BaseException:pass
                    # The OS CPU fence supervises long native calls too. RSS is
                    # sampled, never presented as a hard allocation guarantee.
                    if isinstance(error,MemoryError):os.kill(os.getpid(),signal.SIGTERM)
                    return
        self.thread=threading.Thread(target=monitor,name='reserved-role-budget',daemon=True);self.thread.start()
    def watch(self,connection):self.guard();self.connections.append(connection)
    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1);x.need(not self.thread.is_alive(),'Role monitor cleanup unknown');self.thread=None


class RoleExecution:
    def __init__(self,context,reference,consumed,pins,budget,owner_directory):
        self._context=deepcopy(context);self._reference=deepcopy(reference);self._consumed=deepcopy(consumed)
        self._pins=deepcopy(pins);self.budget=budget;self.role=context['role'];self.root=ROOT;self._owner_directory=owner_directory;self._terminal=False;self._finishing=False
    @property
    def context(self):return deepcopy(self._context)
    @property
    def reference(self):return deepcopy(self._reference)
    @property
    def consumed(self):return deepcopy(self._consumed)
    @property
    def pins(self):return deepcopy(self._pins)
    def markers(self):
        base=local(self._context['output_path']).parent
        x.need(not local(self._owner_directory+'/report.failed.json').exists(),'Known failed owner cannot run role')
        for name in ['report.failed.json','evidence.failed.json','worker.log.cleanup-failed.json']:
            x.need(not (base/name).exists(),'Known failed role cannot be promoted')
    def verify_pins(self,mapping=None):
        x.need(not self._terminal or self._finishing,'Consumed role cannot repeat paid verification');self.markers()
        for name,digest in (self.pins if mapping is None else mapping).items():
            x.need(x.sha(local(name),self.budget.guard)==digest,'Original worker authority/data/code changed')
        self.budget.guard();self.markers()
    def retain_pins(self,mapping):
        """Retain validated original nested refs before their paid streaming use.

        Adapters first derive exact paths/schema from issued producer vocabulary;
        this mechanical method does not itself confer semantic acceptance.
        """
        x.need(not self._terminal,'Consumed role cannot retain new paid inputs')
        x.need(type(mapping) is dict,'Exact nested pin map required');snapshot=deepcopy(mapping)
        for name,digest in snapshot.items():
            x.ref(dict(path=name,sha256=digest));local(name)
            x.need(name not in self._pins or self._pins[name]==digest,'Conflicting retained original pin')
        self._pins.update(snapshot);self.verify_pins(snapshot)
        return deepcopy(snapshot)
    def input_json(self,name):
        x.need(not self._terminal,'Consumed role cannot reopen inputs')
        x.need(name in self._context['inputs'],'Undeclared role JSON input');reference=self._context['inputs'][name]
        self.budget.guard();body,digest=x.read(local(reference['path']));x.need(digest==reference['sha256'],'Parsed role input changed');self.budget.guard();return body
    def environment(self):
        x.need(not self._terminal,'Consumed role cannot repeat environment preparation')
        self.budget.guard();raw=local('uv.lock').read_bytes();x.need(__import__('hashlib').sha256(raw).hexdigest()==self.pins['uv.lock'],'Current lock bytes differ')
        locked={p['name']:p.get('version') for p in tomllib.loads(raw.decode())['package']};packages={}
        for name in ['numpy','pandas','duckdb','catboost']:
            self.budget.guard();module=importlib.import_module(name);loaded=module.__version__;installed=importlib.metadata.version(name)
            x.need(type(loaded) is str and loaded==installed==locked.get(name),'Installed/loaded package differs from uv.lock');packages[name]=loaded
        x.need(sys.version_info[:2]==(3,12),'Locked Python3.12 required')
        result=dict(python=sys.version.split()[0],platform=sys.platform,packages=packages,kernel_cpu=deepcopy(self.budget.kernel_cpu),subprocess_probe=False)
        self.budget.guard();return result
    def finish(self,outputs,evidence,*,native_prediction_count,labels_loaded):
        x.need(not self._terminal,'Original role finalization already consumed');self._terminal=True;self._finishing=True
        try:
            x.need(type(outputs) is dict and set(outputs)==set(self._context['expected_outputs']),'Fixed role output set required')
            x.need(type(native_prediction_count) is int and native_prediction_count>=0,'Known actual native-call count')
            x.need(type(labels_loaded) is bool and labels_loaded is (self.role in x.ROLES[4:]),'Actual role label state differs')
            if self.role not in {'predictions','prediction_oracle'}:x.need(native_prediction_count==0,'Native call outside prediction role')
            x.ref(evidence);x.need(outputs.get(evidence['path'])==evidence['sha256'],'Evidence outside fixed output vocabulary')
            # Retain original caller snapshots before guarded hashes/callbacks.
            outputs=deepcopy(outputs);evidence=deepcopy(evidence)
            self.budget.stop();self.budget.guard();self.verify_pins();self.verify_pins(outputs)
            own,children,peak=self.budget.resources();now=time.monotonic()
            receipt=dict(version=1,scope='reserved_reporting_'+self.role,status='role_complete_unaccepted',run_id=self._context['run_id'],role=self.role,
                context=self.reference,execution_consumed=self.consumed,inputs=deepcopy(self._context['inputs']),outputs=deepcopy(outputs),evidence=deepcopy(evidence),
                fit_attempt_count=0,labels_loaded=labels_loaded,native_prediction_count=native_prediction_count,
                started_monotonic=self.budget.started,finished_monotonic=now,process_cpu_seconds=own,process_peak_rss_bytes=peak,descendant_cpu_seconds=children)
            path=local(self._context['output_path']);saved=x.exclusive(path,receipt)
            x.need(Path(saved['path']).resolve()==path,'Original receipt persistence path changed')
            receipt_snapshot={self._context['output_path']:saved['sha256']}
            x.ref(dict(path=self._context['output_path'],sha256=saved['sha256']))
            self.verify_pins();self.verify_pins(outputs);self.verify_pins(receipt_snapshot);self.budget.guard();self.markers()
            return deepcopy(receipt)
        except BaseException as error:self.fail(error);raise
        finally:self._finishing=False
    def fail(self,error):
        self._terminal=True;self._finishing=False
        try:self.budget.stop()
        except BaseException as secondary:error.add_note('Role monitor stop: '+type(secondary).__name__)
        failed=dict(version=1,status='failed',role=self.role,run_id=self._context['run_id'],context=self.reference,
            execution_consumed=self.consumed,error_type=type(error).__name__,error='STOP original consumed role; no refill/retry/adaptation')
        try:x.exclusive(local(self._context['failed_path']),failed)
        except BaseException as secondary:error.add_note('Role failure persistence: '+type(secondary).__name__)
        return failed


def begin_role(context_path,issued_context_sha256,expected_role,started_monotonic):
    """Small original-authority admission then consume BEFORE paid data streams.

    Adapter bootstrap must first verify the original raw context SHA and cheap
    project code snapshots before importing this module. No actual operation is
    authorized merely by constructing synthetic objects in a unit test.
    """
    path=Path(context_path).resolve();path.relative_to(ROOT.resolve());context,actual=x.read(path)
    x.need(actual==issued_context_sha256,'Parent-issued context SHA differs')
    x.need(type(context) is dict and set(context)==CONTEXT_KEYS,'Exact issuer context vocabulary required')
    role=context['role'];x.need(role==expected_role and role in x.ROLES,'Fixed adapter role differs')
    x.need(type(context['version']) is int and context['version']==1 and context['scope']=='issued_reserved_reporting_role','Typed issued worker scope')
    reference=dict(path=relative(path),sha256=actual);seen={reference['path']:actual}
    request=observed(context['request'],seen);claim=observed(context['owner_claim'],seen);slot=observed(context['slot'],seen)
    x.need(set(claim)=={'version','scope','request','owner_source','output_directory','started_monotonic','original_deadline_monotonic'} and
        type(claim['version']) is int and claim['version']==1 and claim['scope']=='reserved_reporting_owner_attempt','Original owner claim shape/scope')
    x.need(context['owner_claim']['path']=='artifacts/heldout-study/owner.claim.json' and claim['request']==context['request'],'Original global owner attempt detached')
    base=claim['output_directory']+'/'+role
    x.need(reference['path']==base+'/context.json' and context['slot']['path']==base+'/slot.json' and
        context['output_path']==base+'/receipt.json' and context['failed_path']==base+'/report.failed.json','Original role destinations changed')
    x.need(type(claim['started_monotonic']) in (int,float) and x.finite(claim['started_monotonic']) and
        claim['original_deadline_monotonic']==claim['started_monotonic']+x.LIMITS['wall_seconds'],'Original owner clock detached')
    x.need(type(request) is dict and set(request)=={'version','scope','owner_source','policy','model_acceptance','compute_evidence',
        'code_fingerprints','role_entries','authority_paths','source_inputs'} and type(request['version']) is int and
        request['version']==1 and request['scope']=='prospective_reserved_reporting_owner','Original owner request vocabulary/scope')
    x.need(request['owner_source']==claim['owner_source'] and request['owner_source']['path']=='scripts/run_heldout_reporting.py','Original owner source detached')
    entry=context['entry'];x.ref(entry);x.need(entry['path']==x.ENTRY[role] and request['role_entries'][role]==entry,'Arbitrary worker entry forbidden')
    plan=context['plan'];x.need(type(plan) is dict and set(plan)=={'run_id','choice','fingerprints'} and plan['run_id']==context['run_id'],'Original lifecycle projection differs')
    pins=deepcopy(plan['fingerprints']);x.need(type(pins) is dict and pins.get(entry['path'])==entry['sha256'],'Original fixed entry pin absent')
    for name,digest in pins.items():x.ref(dict(path=name,sha256=digest))
    for name,digest in request['code_fingerprints'].items():x.need(pins.get(name)==digest,'Original current-code closure detached')
    for name in ['scripts/heldout_worker_context.py','scripts/heldout_execution.py','scripts/heldout_contract.py',entry['path'],'uv.lock','pyproject.toml']:
        x.need(name in request['code_fingerprints'],'Mandatory worker bootstrap/code pin omitted')
    x.need(pins.get(context['request']['path'])==context['request']['sha256'] and
        pins.get(context['owner_claim']['path'])==context['owner_claim']['sha256'],'Original request/claim outside plan closure')
    allocation=context['allocation'];budget=RoleBudget(allocation,started_monotonic)
    x.need(allocation['cpu_seconds']<=x.CAPS[role][0] and allocation['deadline_monotonic']<=claim['original_deadline_monotonic']-20 and
        x.finite(context['issued_at_monotonic']) and claim['started_monotonic']<=context['issued_at_monotonic']<=started_monotonic and
        allocation['deadline_monotonic']<=context['issued_at_monotonic']+x.CAPS[role][1],'Original role cap/clock differs')
    expected_slot=dict(version=1,scope='reserved_role_slot',role=role,ordinal=x.ROLES.index(role),run_id=context['run_id'],allocation=allocation,entry=entry)
    x.need(same(slot,expected_slot),'Issuer original slot detached')
    launch,launch_sha=x.read(local(base+'/launch.json'));seen[base+'/launch.json']=launch_sha
    expected_argv=[str(ROOT/'.venv/bin/python'),str(local(entry['path'])),'--context',str(path),'--issued-context-sha256',actual]
    x.need(same(launch,dict(argv=expected_argv,issued_context_sha256=actual,original_slot=slot,context=reference,entry=entry,allocation=allocation)),'Durable launch detached from issuer argv')
    x.need(set(context['authorities'])==gate_names(role),'Exact issued role authority subset required')
    for gate,reference_gate in context['authorities'].items():
        authority=observed(reference_gate,seen)
        x.need(type(authority.get('version')) is int and authority['version']==1 and authority.get('approved') is True and
            authority.get('scope')==GATE_SCOPES[gate] and authority.get('run_id')==context['run_id'],'Original external role authority differs')
        x.need(request['authority_paths'][gate]==reference_gate['path'],'Authority destination differs from original request')
        if gate=='initial_execution':x.need(same(authority.get('fingerprints'),pins),'Initial execution closure detached')
    x.validate_role_inputs(role,context['inputs'])
    for ref_input in context['inputs'].values():observed_value=ref_input; x.ref(observed_value)
    x.need(context['expected_outputs']==x.expected_paths(claim['output_directory'],role,plan['choice']),'Allocated fixed output vocabulary differs')
    # One proposal closes the full identity without a circular self-hash.
    proposal_name=claim['output_directory']+'/proposal.json'
    proposal=observed(dict(path=proposal_name,sha256=pins[proposal_name]),seen)
    x.need(type(proposal) is dict and set(proposal)=={'run_id','identity'} and proposal['run_id']==context['run_id'],'Exact original owner proposal differs')
    identity=proposal['identity']
    x.need(type(identity) is dict and set(identity)=={'version','scope','request','owner_claim','choice','lock','authenticated_choice',
        'source_inputs','original_limits','role_caps','fingerprints','selected_extra_schema','source_formula_scope','refits','adaptation'},'Exact frozen full identity required')
    x.need(h.digest(identity)==context['run_id'] and identity['request']==context['request'] and identity['owner_claim']==context['owner_claim'] and
        identity['choice']==plan['choice'] and same(identity['original_limits'],x.LIMITS),'Full immutable owner identity detached')
    projection=deepcopy(identity['fingerprints']);x.need(proposal_name not in projection,'Circular proposal pin forbidden')
    projection[proposal_name]=pins[proposal_name];x.need(same(projection,pins),'Exact full identity/proposal projection differs')
    for reference_identity in [identity['lock'],identity['authenticated_choice']]:
        x.ref(reference_identity);x.need(identity['fingerprints'].get(reference_identity['path'])==reference_identity['sha256'],'Original lock/choice outside full identity closure')
    x.need(type(identity.get('version')) is int and identity['version']==1 and identity.get('scope')=='frozen_reserved_reporting_identity'
        and type(identity.get('refits')) is int and identity['refits']==0 and identity.get('adaptation') is False
        and same(identity['role_caps'],x.CAPS),'Frozen full reporting identity scope differs')
    expected_inputs=dict(lock=identity['lock'],choice=identity['authenticated_choice'])
    if role in {'source','source_oracle'}:expected_inputs.update(identity['source_inputs'])
    if role in x.ROLES[2:]:expected_inputs['source_acceptance']=context['authorities']['source_acceptance']
    if role in x.ROLES[4:]:
        expected_inputs['prediction_acceptance']=context['authorities']['prediction_acceptance']
        prediction_seal=observed(context['authorities']['prediction_acceptance'],seen)
        target_seal=observed(context['authorities']['target_execution'],seen)
        expected_inputs['prediction_inventory']=prediction_seal['inventory'];expected_inputs['target_policy']=target_seal['target_policy']
    for name,value in expected_inputs.items():x.need(context['inputs'].get(name)==value,'Role input differs from original identity/authority')
    for name,subpath in {'source_manifest':'source/source-manifest.json','source_receipt':'source/receipt.json',
        'prediction_manifest':'predictions/prediction-manifest.json','prediction_receipt':'predictions/receipt.json',
        'evaluation_manifest':'targets_evaluation/evaluation.json','evaluation_receipt':'targets_evaluation/receipt.json'}.items():
        if name in context['inputs']:x.need(context['inputs'][name]['path']==claim['output_directory']+'/'+subpath,'Unaccepted producer input outside allocated original role destination')
    # Retain the full original pin vocabulary BEFORE exclusive consumption;
    # conflicts are metadata failures, never silent post-consumption exceptions.
    all_pins=deepcopy(pins)
    for name,digest in seen.items():x.need(name not in all_pins or all_pins[name]==digest,'Conflicting original authority pin');all_pins[name]=digest
    for item in context['inputs'].values():
        x.need(item['path'] not in all_pins or all_pins[item['path']]==item['sha256'],'Conflicting role input ref');all_pins[item['path']]=item['sha256']
    # No source/model hash, native import, target relation or package probe has
    # happened before this exclusive admission. No repeat enters paid work.
    budget.guard();x.need(budget.resources()[1]==0,'Fresh worker has prior descendants')
    consumed=x.exclusive(local(base+'/execution.consumed.json'),dict(version=1,scope='reserved_child_execution_consumed',role=role,run_id=context['run_id'],context=reference,slot=context['slot']))
    consumed_ref=dict(path=relative(consumed['path']),sha256=consumed['sha256']);all_pins[consumed_ref['path']]=consumed_ref['sha256']
    result=RoleExecution(context,reference,consumed_ref,all_pins,budget,claim['output_directory'])
    try:result.markers();budget.install_cpu_fence();budget.start_monitor()
    except BaseException as error:result.fail(error);raise
    return result
