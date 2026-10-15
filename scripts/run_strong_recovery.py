"""One zero-fit observer recovery; original failed invocation stays immutable.

An independent exact policy approval and a separately reviewed observer are
required. This owner cannot rerun a producer, fit, select new checkpoints, read
held-out labels or issue a replacement attempt. Old costs remain charged.
"""
import time
START=time.monotonic()
import resource
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid

RUN='9c6969c88857620b24d27da288c6aeb2544187d2cb64267db5e81f8c3599b080'
OLD='artifacts/strong-invocations/5e78c81130204e8dbd26232144a93867'
CLAIM='artifacts/fit-claims/tlab019-zero-fit-observer-recovery.json'
SCOPE='independent_strong_baseline_recovery_verifier'


def cpu():
    r=resource.getrusage(resource.RUSAGE_SELF);c=resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime+r.ru_stime+c.ru_utime+c.ru_stime


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(1024*1024):h.update(block)
    return h.hexdigest()


def finite(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def validate_policy(policy,old,request,context,producer):
    """Pure exact no-new-fit contract and conservative cost prefix."""
    expected={'version','scope','approved','run_id','old_invocation','controller_sha256',
        'entry_path','entry_sha256','fingerprints','diagnostic_cpu_seconds',
        'diagnostic_cpu_upper_seconds','old_external_cpu_upper_seconds','old_external_peak_rss_bytes'}
    if set(policy)!=expected or type(policy['version']) is not int or policy['version']!=1 or policy['approved'] is not True:
        raise ValueError('Exact external recovery policy required')
    if policy['scope']!='zero_fit_strong_observer_recovery' or policy['run_id']!=RUN or policy['old_invocation']!=OLD:
        raise ValueError('Recovery scope differs from the one failed original invocation')
    if (old['status']!='failed' or old['run_id']!=RUN or old['producer_calls']!=1 or old['verifier_calls']!=1
            or old['labels_reserved_opened'] is not False or old['error_type']!='RuntimeError'
            or old['error']!='Independent verifier failed; no promotion/refill'):
        raise ValueError('Recovery cannot erase another failure class')
    if (producer['status']!='complete_produced_unreviewed' or producer['run_id']!=RUN
            or producer['fit_attempt_count']!=4 or producer['actual_seen_looks']!=12
            or producer['unknown_live_fit'] is not False):raise ValueError('Original producer incomplete/unknown')
    if (request['run_id']!=RUN or context['run_id']!=RUN or request['producer_manifest']!=context['producer_manifest']
            or request['producer_report']!=context['producer_report']):raise ValueError('Original producer binding differs')
    if not finite(old['actual_reaped_children_cpu_seconds']) or not finite(producer['actual_reaped_children_cpu_seconds']):
        raise ValueError('Unknown reaped old CPU')
    failed_cpu=old['actual_reaped_children_cpu_seconds']-producer['actual_reaped_children_cpu_seconds']
    maximum=context['allocation']['cpu_seconds'];deadline=old['outer_deadline_monotonic']
    if (type(maximum) is not int or maximum!=300 or request['maximum_verifier_cpu_seconds']!=300
            or not finite(failed_cpu) or not 0<failed_cpu<300 or deadline!=request['outer_deadline_monotonic']
            or deadline!=producer['outer_deadline_monotonic'] or deadline!=22991.362354375):
        raise ValueError('Original allowance/absolute clock differs')
    measured=policy['diagnostic_cpu_seconds'];upper=policy['diagnostic_cpu_upper_seconds'];previous=policy['old_external_cpu_upper_seconds']
    if (not all(finite(x) for x in [measured,upper,previous,old['actual_total_cpu_seconds']])
            or not 0<measured<=upper<=5 or not old['actual_total_cpu_seconds']<=previous<=old['actual_total_cpu_seconds']+1):
        raise ValueError('Missing conservative external/diagnostic CPU boundary')
    peak=policy['old_external_peak_rss_bytes'];parent_peak=old['parent_peak_rss_bytes']
    if (type(peak) is not int or not 0<peak<=7*2**30 or type(parent_peak) is not int
            or not 0<parent_peak<=2**30 or peak+parent_peak>8*2**30):raise ValueError('Original conservative RSS proof differs')
    return dict(previous_cpu_upper_seconds=previous+upper,failed_verifier_cpu_seconds=failed_cpu,
        diagnostic_cpu_seconds=measured,diagnostic_cpu_upper_seconds=upper,
        maximum_recovery_cpu_seconds=maximum-failed_cpu-upper,outer_deadline_monotonic=deadline,
        original_conservative_rss_bytes=peak+parent_peak)


def validate_failure_tail(marker,final):
    allowed={'actual_parent_cpu_seconds','actual_total_cpu_seconds','seconds'}
    if set(marker)!=set(final):raise ValueError('Original failure receipt schemas changed')
    left={k:v for k,v in marker.items() if k not in allowed}
    right={k:v for k,v in final.items() if k not in allowed}
    if json.dumps(left,sort_keys=True,allow_nan=False)!=json.dumps(right,sort_keys=True,allow_nan=False):
        raise ValueError('Original failure identity/state changed')
    for key in allowed:
        if not finite(marker.get(key)) or not finite(final.get(key)) or marker[key]>final[key]:
            raise ValueError('Original final failure cost/clock regressed')


class Budget:
    def __init__(self,boundary,s):
        self.boundary=boundary;self.s=s;self.limits={'parent_launch_cpu_reserve':30}
    def guard(self):
        b=self.boundary
        if time.monotonic()>b['outer_deadline_monotonic']-20:raise TimeoutError('Original absolute deadline exhausted')
        if cpu()>b['maximum_recovery_cpu_seconds']-2:raise TimeoutError('Cumulative original observer allowance exhausted')
        if cpu()+b['previous_cpu_upper_seconds']>3600-2:raise TimeoutError('Original whole-study CPU exhausted')
        if self.s.rss()>2**30:raise MemoryError('Recovery owner RSS1GiB')

    def allocation(self):
        self.guard();b=self.boundary;used=cpu()
        # run_process's accepted live-parent monitor subtracts20 from this
        # setting. Reserve that full allowance plus2 for launch/finalization.
        reserve=self.limits['parent_launch_cpu_reserve']-20+2
        maximum=int(min(b['maximum_recovery_cpu_seconds']-used-reserve,
            3600-b['previous_cpu_upper_seconds']-used-reserve))
        if maximum<1:raise TimeoutError('No original observer allowance remains')
        return dict(cpu_seconds=maximum,deadline_monotonic=b['outer_deadline_monotonic']-20,rss_bytes=7*2**30)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,required=True)
    p.add_argument('--approval',required=True);args=p.parse_args();root=args.project_root.resolve();sys.path.insert(0,str(root))
    from scripts import strong_baseline as s
    from scripts import run_strong_control as control
    if s.ROOT.resolve()!=root:raise ValueError('Wrong project checkout')
    def local(name):
        value=Path(name)
        if type(name) is not str or value.is_absolute() or '..' in value.parts:raise ValueError('Nonlocal recovery path')
        result=(root/value).resolve();result.relative_to(root);return result
    approval_path=local(args.approval);policy=s.read(approval_path)
    if policy['controller_sha256']!=sha(__file__):raise ValueError('Recovery owner is not externally reviewed bytes')
    required=[OLD+'/'+n for n in ['report.json','report.failed.json','verification-request.json','verification-context.json',
        'verification.failed.json','verification.log','verification.json.attempt']]
    if type(policy['fingerprints']) is not dict or not set(required)<=set(policy['fingerprints']):raise ValueError('Failed original evidence pins incomplete')
    pins=dict(policy['fingerprints'])
    for name,digest in pins.items():
        if sha(local(name))!=digest:raise ValueError('Original/recovery evidence changed')
    old=s.read(local(OLD+'/report.json'));request=s.read(local(OLD+'/verification-request.json'))
    old_context=s.read(local(OLD+'/verification-context.json'));producer=s.read(local(request['producer_report']['path']))
    failed_report=s.read(local(OLD+'/report.failed.json'))
    # The old controller writes the failed marker, charges that persistence,
    # then writes its final report. Preserve both byte seals; the final SELF
    # and wall counters can consequently be slightly larger than the marker.
    validate_failure_tail(failed_report,old)
    failed=s.read(local(OLD+'/verification.failed.json'))
    if failed.get('status')!='failed' or failed.get('run_id')!=RUN or failed.get('fit_attempt_count')!=0 or failed.get('error_type')!='ValueError':
        raise ValueError('Recovery requires the documented observer-only failure')
    for ref in [request['producer_manifest'],request['producer_report']]:
        if pins.get(ref['path'])!=ref['sha256'] or sha(local(ref['path']))!=ref['sha256']:raise ValueError('Original producer byte seal changed')
    boundary=validate_policy(policy,old,request,old_context,producer);budget=Budget(boundary,s);budget.guard()
    entry=Path(policy['entry_path']).resolve()
    if not entry.is_relative_to(root/'tests/oracles') or entry.suffix!='.py' or sha(entry)!=policy['entry_sha256']:
        raise ValueError('Recovery observer path/hash differs')
    directory=root/'artifacts/strong-recoveries'/uuid.uuid4().hex;directory.mkdir(parents=True,exist_ok=False)
    report=dict(version=1,status='running',run_id=RUN,producer_calls=0,verifier_calls=0,fit_attempt_count=0,
        labels_reserved_opened=False,started_monotonic=START,outer_deadline_monotonic=boundary['outer_deadline_monotonic'],
        boundary=boundary,controller_source=dict(path=str(Path(__file__).resolve()),sha256=sha(__file__)))
    primary=None
    try:
        claim=local(CLAIM);claim.parent.mkdir(parents=True,exist_ok=True)
        with claim.open('x') as f:f.write(json.dumps(dict(version=1,scope='zero_fit_strong_observer_recovery',run_id=RUN,
            old_invocation=OLD,recovery_directory=s.relative(directory),allowed_fit_attempts=0,allowed_observer_attempts=1,
            approval=dict(path=s.relative(approval_path),sha256=sha(approval_path))),sort_keys=True)+'\n')
        recovery=dict(policy=dict(path=s.relative(approval_path),sha256=sha(approval_path)),claim=dict(path=CLAIM,sha256=sha(claim)),
            old_invocation=OLD,old_report=dict(path=OLD+'/report.json',sha256=sha(local(OLD+'/report.json'))),
            old_context=dict(path=OLD+'/verification-context.json',sha256=sha(local(OLD+'/verification-context.json'))),
            old_failed_verifier=dict(path=OLD+'/verification.failed.json',sha256=sha(local(OLD+'/verification.failed.json'))),
            boundary=boundary)
        allowance=budget.allocation();maximum=allowance['cpu_seconds']
        new_request=dict(version=1,scope='strong_baseline_recovery_verification_request',run_id=RUN,
            producer_report=request['producer_report'],producer_manifest=request['producer_manifest'],controller_source=report['controller_source'],
            outer_deadline_monotonic=boundary['outer_deadline_monotonic'],canonical_actual_cpu_seconds=boundary['previous_cpu_upper_seconds']+cpu(),
            maximum_verifier_cpu_seconds=maximum,verifier_rss_bytes=7*2**30,recovery=recovery)
        s.write(directory/'verification-request.json',new_request)
        context=dict(version=1,scope=SCOPE,run_id=RUN,project_root=str(root),invocation_directory=s.relative(directory),
            request_sha256=sha(directory/'verification-request.json'),producer_manifest=request['producer_manifest'],producer_report=request['producer_report'],
            allocation=allowance,expected_verifier_source=dict(path=str(entry),sha256=policy['entry_sha256']),issued_at_monotonic=time.monotonic(),
            output_path=s.relative(directory/'verification.json'),failed_output_path=s.relative(directory/'verification.failed.json'),recovery=recovery)
        budget.guard();s.write(directory/'verification-context.json',context);context_sha=sha(directory/'verification-context.json')
        argv=[sys.executable,str(entry),'--context',str(directory/'verification-context.json'),'--issued-context-sha256',context_sha]
        report.update(status='verifier_running',verifier_calls=1,verifier_launch=dict(argv=argv,issued_context_sha256=context_sha,allocation=allowance),
            verifier_approval=dict(path=s.relative(approval_path),sha256=sha(approval_path)))
        s.write(directory/'report.json',report)
        pins.update({s.relative(approval_path):sha(approval_path),CLAIM:sha(claim),s.relative(entry):policy['entry_sha256'],
            s.relative(Path(__file__).resolve()):sha(__file__),s.relative(directory/'verification-request.json'):sha(directory/'verification-request.json'),
            s.relative(directory/'verification-context.json'):context_sha})
        before=s.child_cpu();code=s.run_process(argv,directory/'verification.log',budget=budget,allocation=allowance)
        child_cpu=s.child_cpu()-before;budget.guard()
        if not finite(child_cpu) or child_cpu>maximum or code!=0 or (directory/'verification.failed.json').exists():
            raise RuntimeError('Recovery observer failed; consumed with no further replay or fit')
        result=s.read(directory/'verification.json');control.validate_verifier_result(result,context,context_sha,child_cpu)
        for name,digest in pins.items():
            budget.guard()
            if sha(local(name))!=digest:raise ValueError('Old/recovery evidence changed after observer')
        if (local(request['producer_report']['path']).parent/'report.failed.json').exists():raise ValueError('Producer failed after replay')
        job_rss=s.rss()+result['process_peak_rss_bytes']
        if job_rss>8*2**30:raise MemoryError('Recovery owner plus observer exceeds8GiB')
        report.update(status='recovery_verified_pending_external_acceptance',actual_reaped_verifier_cpu_seconds=child_cpu,
            verification_sha256=sha(directory/'verification.json'),final_source_pins=pins,
            conservative_study_peak_rss_bytes=max(boundary['original_conservative_rss_bytes'],job_rss))
    except BaseException as error:primary=error
    finally:
        report.update(actual_new_parent_cpu_seconds=s.self_cpu(),actual_new_reaped_children_cpu_seconds=s.child_cpu(),
            actual_new_total_cpu_seconds=cpu(),conservative_study_cpu_seconds=boundary['previous_cpu_upper_seconds']+cpu(),
            cumulative_original_verification_cpu_seconds=boundary['failed_verifier_cpu_seconds']+boundary['diagnostic_cpu_upper_seconds']+cpu(),
            seconds=time.monotonic()-START,finished_monotonic=time.monotonic(),parent_peak_rss_bytes=s.rss(),
            final_receipt_boundary='owner_SELF_plus_reaped_CHILDREN_once_external_time_charges_exit_tail')
        try:
            budget.guard()
            if report['cumulative_original_verification_cpu_seconds']>300 or report['conservative_study_cpu_seconds']>3600:
                raise TimeoutError('Cumulative original CPU allowance exceeded')
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Final guard: '+type(error).__name__)
        if primary is not None:report.update(status='failed',error_type=type(primary).__name__,error='Zero-fit recovery failed; no fit/refill/holdout permission')
        s.write(directory/'report.json',report)
        if primary is not None:s.write(directory/'report.failed.json',report)
    if primary is not None:raise primary
    print(json.dumps(dict(status=report['status'],directory=s.relative(directory),fit_attempt_count=0)),flush=True)


if __name__=='__main__':main()
