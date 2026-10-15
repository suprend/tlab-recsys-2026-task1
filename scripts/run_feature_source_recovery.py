"""Use the one unused source oracle; never regenerate failed source outputs.

Original source failure stays immutable. Independent exact policy/code review
and a separately measured external lifetime seal are required for acceptance.
"""
import time
START=time.monotonic()
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import types
import uuid

SCOPE='independent_recovered_selected_feature_program_source_oracle'
CLAIM='artifacts/feature-program-study/independent-oracle.claim.json'


def finite(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(1024*1024):h.update(block)
    return h.hexdigest()


def snapshot(path):
    with Path(path).open('rb') as f:raw=f.read(2**20+1)
    if len(raw)>2**20:raise ValueError('Recovery policy exceeds bounded metadata size')
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise ValueError('Duplicate recovery policy key')
            out[key]=value
        return out
    body=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite policy')))
    return body,hashlib.sha256(raw).hexdigest()


def verified_module(root,name,pins):
    """Execute the mandatory pinned snapshot, never unverified helper bytes."""
    relative=name.replace('.','/')+'.py';path=root/relative
    expected=pins.get(relative)
    if type(expected) is not str or len(expected)!=64:
        raise ValueError('Mandatory lifecycle/admission code pin omitted')
    with path.open('rb') as handle:raw=handle.read(2**20+1)
    if len(raw)>2**20 or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('Mandatory lifecycle/admission code snapshot changed')
    module=types.ModuleType(name);module.__file__=str(path);module.__package__=name.rpartition('.')[0]
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


class Budget:
    """One fresh owner plus reaped oracle; old failed lifetime is paid once."""
    def __init__(self,boundary,s,*,started=START):
        self.b=boundary;self.s=s;self.started=started
        self.outer_deadline=started+boundary['owner_and_oracle_wall_seconds']
        # Accepted supervisor uses this value−20 as its live-parent CPU limit.
        self.limits={'parent_launch_cpu_reserve':30}
    def new_cpu(self):
        a,b=self.s.self_cpu(),self.s.child_cpu()
        if not finite(a) or not finite(b):raise ValueError('Unknown fresh owner/child CPU')
        return a+b
    def cpu(self):return self.b['old_source_cpu_upper_seconds']+self.new_cpu()
    def guard(self):
        if self.new_cpu()>self.b['owner_and_oracle_cpu_seconds']-2:
            raise TimeoutError('Unused oracle cumulative CPU allowance exhausted')
        if time.monotonic()>self.outer_deadline-20:raise TimeoutError('Fresh unused oracle absolute deadline exhausted')
        peak=self.s.rss()
        if type(peak) is not int or not 0<peak<=2**30:raise MemoryError('Oracle owner RSS1GiB/unknown')
        if self.cpu()>900 or self.cpu()>7200:raise TimeoutError('Original source/common study CPU exceeded')
    def allocation(self):
        self.guard();reserve=self.limits['parent_launch_cpu_reserve']-20+2
        maximum=int(self.b['owner_and_oracle_cpu_seconds']-self.new_cpu()-reserve)
        if maximum<1:raise TimeoutError('No unused oracle allowance remains')
        return dict(cpu_seconds=maximum,deadline_monotonic=self.outer_deadline-20,rss_bytes=7*2**30)


def validate_evidence(e,context,context_sha,admitted,actual_child_cpu,*,oracle_claim):
    """Physical/authority/count boundary; independent formulas belong to oracle."""
    expected=dict(version=1,status='verified',run_id=context['run_id'],source_proof_scope='all_selected12_values_and_accepted_QC_domain',
        formula_values_complete=True,fit_attempt_count=0,checked_pairs=admitted['pairs'],checked_physical_columns=12,
        checked_scalar_values=admitted['pairs']*12,mismatch_count=0,checked_columns=12,checked_days=admitted['days'],
        mismatch_rows=0,baseline_all45_preserved=True,labels_loaded=False,independent_expected_values=True,
        baseline_source_formula_scope='preservation_only_prior_manual18_source_proof_unchanged',recency_absolute_tolerance_seconds=1e-9,
        context_sha256=context_sha,request=context['request'],producer_manifest=context['producer_manifest'],
        producer_report=context['producer_report'],oracle_source=context['oracle_source'],shared_budget=context['shared_budget'],
        source_claim=admitted['source_claim'],source_parent_receipt=context['shared_budget']['source_parent_receipt'],
        verified_outputs=admitted['outputs'],oracle_claim=oracle_claim,source_recovery=dict(policy=context['recovery_policy'],
            failed_lifetime_receipt=context['shared_budget']['source_parent_receipt'],source_claim=admitted['source_claim'],
            producer_regenerated=False,original_producer_status='failed'))
    for key,value in expected.items():
        if key not in e or json.dumps(e[key],sort_keys=True,allow_nan=False)!=json.dumps(value,sort_keys=True,allow_nan=False):
            raise ValueError('Oracle evidence binding/count differs: '+key)
    for key in ['process_cpu_seconds','started_monotonic','finished_monotonic']:
        if not finite(e.get(key)):raise ValueError('Unknown oracle resource/clock field')
    if (not finite(actual_child_cpu) or actual_child_cpu>context['allocation']['cpu_seconds']
            or e['process_cpu_seconds']>actual_child_cpu+1e-6):raise TimeoutError('Actual reaped oracle CPU exceeds allowance/body')
    if (type(e.get('process_peak_rss_bytes')) is not int or not 0<e['process_peak_rss_bytes']<=7*2**30):
        raise MemoryError('Oracle RSS exceeded/unknown')
    if not context['issued_at_monotonic']<=e['started_monotonic']<=e['finished_monotonic']<=context['allocation']['deadline_monotonic']:
        raise ValueError('Oracle clock detached from original fresh owner allowance')
    if e['finished_monotonic']>time.monotonic():raise ValueError('Oracle future clock')
    covers=e.get('phase_coverage')
    if type(covers) is not dict or set(covers)!={'train','selection'}:raise ValueError('Both accepted source phases required')
    queries=pairs=0
    for cover in covers.values():
        if type(cover) is not dict or set(cover)!={'expected_queries','expected_pairs','checked_queries','checked_pairs'}:
            raise ValueError('Exact phase-coverage receipt required')
        if any(type(v) is not int or v<0 for v in cover.values()):raise ValueError('Strict phase-coverage counts required')
        if cover['expected_queries']!=cover['checked_queries'] or cover['expected_pairs']!=cover['checked_pairs']:
            raise ValueError('Every accepted Q/C must be covered')
        queries+=cover['checked_queries'];pairs+=cover['checked_pairs']
    if queries!=admitted['queries'] or pairs!=admitted['pairs']:raise ValueError('Phase counts differ from admitted full output map')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,required=True)
    p.add_argument('--approval',required=True);args=p.parse_args();root=args.project_root.resolve();sys.path.insert(0,str(root))
    def local(name):
        if type(name) is not str or Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('Nonlocal recovery artifact')
        path=(root/name).resolve();path.relative_to(root);return path
    approval_path=local(args.approval);policy,policy_sha=snapshot(approval_path)
    if policy['owner_source']!=dict(path=Path(__file__).resolve().relative_to(root).as_posix(),sha256=sha(__file__)):
        raise ValueError('Owner differs from exact external policy')
    pins=policy['fingerprints']
    if type(pins) is not dict:raise ValueError('Mandatory recovery code fingerprints required')
    # Source modules import other reviewed original modules. Check all cheap
    # Python pins first; no export, database or Parquet stream occurs here.
    for name,digest in pins.items():
        if type(name) is str and name.endswith('.py') and sha(local(name))!=digest:
            raise ValueError('Reviewed source code pin changed before helper import')
    s=verified_module(root,'scripts.strong_baseline',pins)
    admission=verified_module(root,'scripts.feature_program_source_recovery',pins)
    if s.ROOT.resolve()!=root or Path(admission.__file__).resolve()!=root/'scripts/feature_program_source_recovery.py':
        raise ValueError('Wrong source-recovery checkout')
    manifest=snapshot(local(policy['producer_manifest']['path']))[0]
    source_report=snapshot(local(policy['producer_report']['path']))[0]
    prefix=snapshot(local(policy['failed_lifetime_receipt']['path']))[0]
    boundary=admission.validate_policy(policy,manifest,source_report,prefix)
    admitted=admission.validate_failed_source(manifest,source_report,prefix)
    budget=Budget(boundary,s);budget.guard()
    if s.child_cpu()!=0:raise ValueError('Unexpected pre-oracle descendants; unknown usage STOP')
    pins=dict(policy['fingerprints'])
    for ref in [policy[k] for k in ['producer_manifest','producer_report','failed_lifetime_receipt','source_claim','owner_source','oracle_source']]:
        if pins.get(ref['path'])!=ref['sha256']:raise ValueError('Authority/history code pin omitted')
    for module in [s,admission]:
        name=s.relative(Path(module.__file__).resolve())
        if pins.get(name)!=sha(module.__file__):raise ValueError('Reviewed lifecycle/admission source pin omitted')
    entry=local(policy['oracle_source']['path'])
    if not entry.is_relative_to(root/'tests/oracles') or entry.suffix!='.py':raise ValueError('Oracle entry confinement')
    directory=root/'artifacts/feature-program-source-oracle'/uuid.uuid4().hex;directory.mkdir(parents=True,exist_ok=False)
    report=dict(version=1,status='running',run_id=policy['run_id'],producer_calls=0,source_calculations=0,fit_attempt_count=0,
        oracle_calls=0,labels_loaded=False,started_monotonic=START,outer_deadline_monotonic=budget.outer_deadline,
        boundary=boundary,owner_source=policy['owner_source'],oracle_source=policy['oracle_source'])
    primary=None;context_sha=None
    try:
        claim_path=local(CLAIM);claim_path.parent.mkdir(parents=True,exist_ok=True)
        claim=dict(version=1,scope='once_only_selected12_source_oracle',run_id=policy['run_id'],allowed_observer_attempts=1,
            allowed_source_calculations=0,allowed_fit_attempts=0,policy=dict(path=s.relative(approval_path),sha256=policy_sha),
            invocation_directory=s.relative(directory))
        with claim_path.open('x') as f:f.write(json.dumps(claim,sort_keys=True)+'\n')
        policy_ref=dict(path=s.relative(approval_path),sha256=policy_sha)
        report['policy']=policy_ref;report['status']='paid_preparation';s.write(directory/'report.json',report)
        pins[s.relative(approval_path)]=policy_sha
        # Only cheap authority/metadata admission precedes the claim. Every
        # export byte stream below is paid preparation and consumes this attempt.
        for name,digest in pins.items():
            budget.guard()
            if sha(local(name))!=digest:raise ValueError('Original source/recovery pin changed')
        shared=dict(limit_cpu_seconds=7200,charged_prefix_cpu_seconds=boundary['old_source_cpu_upper_seconds'],
            unknown_cost=False,source_parent_receipt=policy['failed_lifetime_receipt'])
        request=dict(scope=SCOPE,run_id=policy['run_id'],producer_manifest=policy['producer_manifest'],producer_report=policy['producer_report'],
            oracle_source=policy['oracle_source'],shared_budget=shared,recovery_policy=policy_ref)
        s.write(directory/'request.json',request)
        allocation=budget.allocation()
        context=dict(version=1,scope=SCOPE,run_id=policy['run_id'],project_root=str(root),invocation_directory=s.relative(directory),
            request=dict(path=s.relative(directory/'request.json'),sha256=sha(directory/'request.json')),
            oracle_execution_approval=policy_ref,producer_manifest=policy['producer_manifest'],producer_report=policy['producer_report'],
            oracle_source=policy['oracle_source'],allocation=allocation,shared_budget=shared,issued_at_monotonic=time.monotonic(),
            output_path=s.relative(directory/'evidence.json'),failed_output_path=s.relative(directory/'evidence.failed.json'),recovery_policy=policy_ref)
        s.write(directory/'context.json',context);context_sha=sha(directory/'context.json')
        argv=[sys.executable,str(entry),'--context',str(directory/'context.json'),'--issued-context-sha256',context_sha]
        launch=dict(version=1,scope=SCOPE,run_id=policy['run_id'],argv=argv,cwd=str(root),issued_context_sha256=context_sha,
            allocation=allocation,claim=dict(path=CLAIM,sha256=sha(claim_path)),policy=policy_ref)
        with (directory/'launch.json').open('x') as f:f.write(json.dumps(launch,sort_keys=True)+'\n')
        pins.update({CLAIM:sha(claim_path),s.relative(approval_path):policy_sha,
            s.relative(directory/'request.json'):sha(directory/'request.json'),s.relative(directory/'context.json'):context_sha,
            s.relative(directory/'launch.json'):sha(directory/'launch.json')})
        if sha(approval_path)!=policy_sha:raise ValueError('Issued policy changed before oracle launch')
        budget.guard();report.update(status='oracle_running',oracle_calls=1,launch=launch,
            oracle_launch=dict(argv=argv,issued_context_sha256=context_sha,allocation=allocation),oracle_approval=policy_ref);s.write(directory/'report.json',report)
        before=s.child_cpu();code=s.run_process(argv,directory/'oracle.log',budget=budget,allocation=allocation)
        actual_child_cpu=s.child_cpu()-before;budget.guard()
        if code!=0 or (directory/'evidence.failed.json').exists():raise RuntimeError('Unused source oracle failed; no second attempt or regeneration')
        evidence=s.read(directory/'evidence.json');validate_evidence(evidence,context,context_sha,admitted,actual_child_cpu,oracle_claim=launch['claim'])
        for name,digest in pins.items():
            budget.guard()
            if sha(local(name))!=digest:raise ValueError('Original/recovery evidence changed during oracle')
        if any((directory/name).exists() for name in ['evidence.failed.json','report.failed.json','oracle.log.cleanup-failed.json']):
            raise RuntimeError('Late known source oracle failure; no successful pending receipt')
        job_peak=s.rss()+evidence['process_peak_rss_bytes']
        if job_peak>8*2**30:raise MemoryError('Owner plus source oracle exceeds8GiB')
        report.update(status='recovered_source_verified_pending_external_acceptance',actual_reaped_oracle_cpu_seconds=actual_child_cpu,
            evidence=dict(path=s.relative(directory/'evidence.json'),sha256=sha(directory/'evidence.json')),
            final_source_pins=pins,conservative_job_peak_rss_bytes=job_peak,
            conservative_study_peak_rss_bytes=max(job_peak,prefix['producer']['peak_rss_bytes']))
    except BaseException as error:primary=error
    finally:
        parent_cpu,children_cpu=s.self_cpu(),s.child_cpu();new_cpu=parent_cpu+children_cpu;finished=time.monotonic()
        report.update(actual_new_parent_cpu_seconds=parent_cpu,actual_new_reaped_children_cpu_seconds=children_cpu,
            actual_new_total_cpu_seconds=new_cpu,charged_source_oracle_cpu_seconds=boundary['old_source_cpu_upper_seconds']+new_cpu,
            seconds=finished-START,finished_monotonic=finished,parent_peak_rss_bytes=s.rss(),
            active_computation_wall_seconds=boundary['old_source_active_wall_seconds']+finished-START,
            original_absolute_deadline='unavailable_not_reconstructed',
            receipt_boundary='absolute_SELF_plus_reaped_CHILDREN_once_external_lifetime_seal_required_for_exit_tail')
        try:
            budget.guard()
            if any((directory/name).exists() for name in ['evidence.failed.json','report.failed.json','oracle.log.cleanup-failed.json']):
                raise RuntimeError('Late known source oracle failure before persistence')
            if context_sha is not None and sha(directory/'context.json')!=context_sha:
                raise ValueError('Issued oracle context changed before persistence')
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Final guard: '+type(error).__name__)
        if primary is not None:report.update(status='failed',error_type=type(primary).__name__,error='Source oracle recovery failed; claim consumed without replacement')
        s.write(directory/'report.json',report)
        if primary is not None:s.write(directory/'report.failed.json',report)
    if primary is not None:raise primary
    print(json.dumps(dict(status=report['status'],directory=s.relative(directory),source_calculations=0,fit_attempt_count=0)),flush=True)


if __name__=='__main__':main()
