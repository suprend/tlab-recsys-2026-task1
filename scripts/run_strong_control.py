"""Single fresh owner for proposal, approved producer, and one verifier.

No model fit is authorized by this wrapper itself. Explicit external exact
producer and verifier approvals are required. All SELF/CHILDREN is counted
once from process entry; the same outer monotonic deadline survives phases.
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


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as handle:
        while block:=handle.read(1024*1024):value.update(block)
    return value.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,required=True)
    parser.add_argument('--producer-approval',required=True)
    parser.add_argument('--verifier-approval',required=True)
    args=parser.parse_args();root=args.project_root.resolve();sys.path.insert(0,str(root))
    from scripts import strong_baseline as s
    from scripts import metadata_price_collection as c
    if s.ROOT.resolve()!=root:raise ValueError('Imported producer from wrong checkout')
    spec=s.specification();budget=s.Budget(spec,started=START)
    directory=root/'artifacts/strong-invocations'/uuid.uuid4().hex;directory.mkdir(parents=True,exist_ok=False)
    report=dict(version=1,status='running',started_monotonic=START,outer_deadline_monotonic=budget.outer_deadline,
        accounting='absolute_SELF_plus_reaped_CHILDREN_once_includes_readonly_proposal_and_producer',
        controller_source=dict(path=str(Path(__file__).resolve()),sha256=sha(__file__)),
        entry_clock='earliest_stdlib_monotonic_after_interpreter_start_absolute_CPU_includes_interpreter',
        argv=sys.argv,producer_calls=0,verifier_calls=0,labels_reserved_opened=False)
    s.write(directory/'report.json',report);primary=None
    paths=[root/n for n in ['configs/models/strong-grid.json','configs/models/cpu-smoke.json',
        'artifacts/acceptance/tlab017-train-collection.json','artifacts/acceptance/tlab017-selection-collection.json',
        'artifacts/acceptance/tlab009-ablation-verified.json']]
    def wait(path,guard):
        while not path.exists():
            guard()
            if (directory/'abort.json').exists():raise RuntimeError('External review aborted invocation; no refill')
            time.sleep(.25)
        guard();return s.read(path)
    try:
        budget.guard();plan,inputs=s.prepare_plan(*paths,check=budget.guard);del inputs
        s.write(directory/'proposal.json',plan)
        report.update(status='waiting_exact_producer_approval',run_id=plan['run_id'],proposal_cpu_seconds=budget.cpu(),
            proposal_seconds=time.monotonic()-START,proposal_sha256=s.sha(directory/'proposal.json'))
        s.write(directory/'report.json',report)
        print(json.dumps(dict(status=report['status'],directory=s.relative(directory),run_id=plan['run_id'])),flush=True)
        approval_path=s.local(args.producer_approval);approval=wait(approval_path,budget.guard)
        expected=dict(version=1,approved=True,scope=s.ROLE,run_id=plan['run_id'],fingerprints=plan['identity']['fingerprints'])
        if c.canonical_json(approval)!=c.canonical_json(expected):raise ValueError('External producer approval differs from actual proposal')
        report.update(status='producer_running',producer_calls=1);s.write(directory/'report.json',report)
        produced=s.run(*paths,execution_approval=approval_path,started_monotonic=START)
        if produced['status']!='complete_produced_unreviewed':raise ValueError('No complete producer receipt')
        run_directory=root/'artifacts/strong-baseline'/plan['run_id']
        if (run_directory/'report.failed.json').exists():raise ValueError('Known failed producer')
        request=dict(version=1,scope='strong_baseline_verification_request',run_id=plan['run_id'],
            producer_report=dict(path=s.relative(run_directory/'report.json'),sha256=s.sha(run_directory/'report.json')),
            producer_manifest=dict(path=s.relative(run_directory/'run.json'),sha256=s.sha(run_directory/'run.json')),
            controller_source=report['controller_source'],outer_deadline_monotonic=budget.outer_deadline,
            canonical_actual_cpu_seconds=budget.cpu(),maximum_verifier_cpu_seconds=min(300,max(0,3600-budget.cpu()-60)),
            verifier_rss_bytes=7*2**30)
        s.write(directory/'verification-request.json',request)
        report.update(status='waiting_exact_verifier_approval',request_sha256=s.sha(directory/'verification-request.json'))
        s.write(directory/'report.json',report)
        print(json.dumps(dict(status=report['status'],directory=s.relative(directory),run_id=plan['run_id'])),flush=True)
        class FinalBudget(s.Budget):
            def guard(self):
                if time.monotonic()>self.outer_deadline-20:raise TimeoutError('Final controller absolute wall deadline')
                if self.cpu()>self.limits['cpu_seconds']-20:raise TimeoutError('Final controller actual CPU cleanup reserve')
                if s.rss()>self.limits['parent_rss_bytes']:raise MemoryError('Controller RSS exceeds1GiB')
        final_budget=FinalBudget(spec,started=START)
        verifier_approval_path=s.local(args.verifier_approval);verifier=wait(verifier_approval_path,final_budget.guard)
        c._keys(verifier,{'version','approved','scope','run_id','request_sha256','controller_sha256','entry_path','entry_sha256'},'verifier external approval')
        if (type(verifier['version']) is not int or verifier['version']!=1 or verifier['approved'] is not True
                or verifier['scope']!='independent_strong_baseline_verifier' or verifier['run_id']!=plan['run_id']
                or verifier['request_sha256']!=s.sha(directory/'verification-request.json')
                or verifier['controller_sha256']!=report['controller_source']['sha256']):raise ValueError('Verifier approval detached')
        entry=Path(verifier['entry_path']).resolve()
        if entry.suffix!='.py' or sha(entry)!=verifier['entry_sha256']:raise ValueError('Verifier code hash/path differs')
        allowance=dict(cpu_seconds=int(min(300,3600-final_budget.cpu()-60)),
            deadline_monotonic=final_budget.outer_deadline-20,rss_bytes=7*2**30)
        if allowance['cpu_seconds']<1 or allowance['deadline_monotonic']<=time.monotonic():raise TimeoutError('No verification allowance remains')
        context=dict(version=1,scope='independent_strong_baseline_verifier',run_id=plan['run_id'],
            project_root=str(root),invocation_directory=s.relative(directory),request_sha256=s.sha(directory/'verification-request.json'),
            producer_manifest=request['producer_manifest'],producer_report=request['producer_report'],allocation=allowance,
            expected_verifier_source=dict(path=str(entry),sha256=verifier['entry_sha256']),
            issued_at_monotonic=time.monotonic(),output_path=s.relative(directory/'verification.json'),
            failed_output_path=s.relative(directory/'verification.failed.json'))
        s.write(directory/'verification-context.json',context)
        context_sha=s.sha(directory/'verification-context.json')
        source_pins={str(Path(__file__).resolve()):report['controller_source']['sha256'],str(entry):verifier['entry_sha256'],
            str(approval_path):s.sha(approval_path),str(verifier_approval_path):s.sha(verifier_approval_path),
            str(directory/'verification-context.json'):context_sha,str(directory/'verification-request.json'):s.sha(directory/'verification-request.json'),
            str(run_directory/'run.json'):request['producer_manifest']['sha256'],str(run_directory/'report.json'):request['producer_report']['sha256']}
        report.update(status='verifier_running',verifier_calls=1,verifier_approval=dict(path=s.relative(verifier_approval_path),sha256=s.sha(verifier_approval_path)))
        s.write(directory/'report.json',report)
        verifier_argv=[sys.executable,str(entry),'--context',str(directory/'verification-context.json'),'--issued-context-sha256',context_sha]
        report['verifier_launch']=dict(argv=verifier_argv,issued_context_sha256=context_sha,allocation=allowance)
        s.write(directory/'report.json',report)
        child_before=s.child_cpu()
        code=s.run_process(verifier_argv,
            directory/'verification.log',budget=final_budget,allocation=allowance)
        actual_verifier_cpu=s.child_cpu()-child_before
        if actual_verifier_cpu<0 or actual_verifier_cpu>allowance['cpu_seconds']:raise TimeoutError('Reaped verifier CPU exceeds issued allowance')
        if code!=0 or (directory/'verification.failed.json').exists():raise RuntimeError('Independent verifier failed; no promotion/refill')
        result=s.read(directory/'verification.json')
        validate_verifier_result(result,context,context_sha,actual_verifier_cpu)
        for name,digest in source_pins.items():
            if sha(name)!=digest:raise ValueError('Invocation source/producer/context changed after verifier: '+name)
        if (run_directory/'report.failed.json').exists() or (directory/'report.failed.json').exists():raise ValueError('Known final producer/invocation failure marker')
        report['final_source_pins']=source_pins
        report['actual_reaped_verifier_cpu_seconds']=actual_verifier_cpu
        final_budget.guard()
        observed_peak=s.rss()+max(child['report']['process_peak_rss_bytes'] for child in produced['children'])
        if observed_peak>8*2**30:raise MemoryError('Controller plus worker observed conservative peak exceeds8GiB')
        report.update(status='verified_produced_pending_external_acceptance',producer_report_sha256=s.sha(run_directory/'report.json'),
            verification_sha256=s.sha(directory/'verification.json'),conservative_production_job_rss_bytes=observed_peak,
            final_verifier_job_rss_bytes=s.rss()+result['process_peak_rss_bytes'])
        if report['final_verifier_job_rss_bytes']>8*2**30:raise MemoryError('Controller plus verifier observed peak exceeds8GiB')
    except BaseException as error:primary=error
    finally:
        try:
            report.update(actual_parent_cpu_seconds=s.self_cpu(),actual_reaped_children_cpu_seconds=s.child_cpu(),
                actual_total_cpu_seconds=budget.cpu(),seconds=time.monotonic()-START,parent_peak_rss_bytes=s.rss(),
                final_persistence_boundary='before_two_small_receipt_writes_external_shell_wall_separately_recorded')
            if report['actual_total_cpu_seconds']>3600 or report['seconds']>3600:raise TimeoutError('Whole invocation exceeds shared CPU/wall cap')
            if s.rss()>2**30:raise MemoryError('Whole controller lifetime RSS exceeds1GiB')
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Final accounting failure: '+repr(error))
        if primary is not None:report.update(status='failed',error_type=type(primary).__name__,error=str(primary),error_notes=getattr(primary,'__notes__',[]))
        try:s.write(directory/'report.json',report)
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Invocation receipt failure: '+repr(error))
        if primary is not None:
            report.update(status='failed',error_type=type(primary).__name__,error=str(primary))
            try:(directory/'report.failed.json').write_text(c.canonical_json(report)+'\n')
            except BaseException as error:primary.add_note('Invocation failed marker failure: '+repr(error))
        # Charge first receipt and guard again; external ledger covers only
        # the final few bytes of failure/success receipt and interpreter exit.
        final_self,final_children=s.self_cpu(),s.child_cpu()
        report.update(actual_parent_cpu_seconds=final_self,actual_reaped_children_cpu_seconds=final_children,
            actual_total_cpu_seconds=final_self+final_children,seconds=time.monotonic()-START)
        if report['actual_total_cpu_seconds']>3600 or report['seconds']>3600:
            error=TimeoutError('Post-receipt whole invocation cap exceeded')
            if primary is None:primary=error
            else:primary.add_note(str(error))
            report.update(status='failed',error_type=type(primary).__name__,error=str(primary))
            try:(directory/'report.failed.json').write_text(c.canonical_json(report)+'\n')
            except BaseException as error:primary.add_note('Post-receipt marker failure: '+repr(error))
        try:s.write(directory/'report.json',report)
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Final invocation receipt failure: '+repr(error))
            report.update(status='failed',error_type=type(primary).__name__,error=str(primary))
            try:(directory/'report.failed.json').write_text(c.canonical_json(report)+'\n')
            except BaseException as secondary:primary.add_note('Final failure marker error: '+repr(secondary))
    if primary is not None:raise primary
    print(json.dumps(dict(status=report['status'],directory=s.relative(directory),actual_cpu_seconds=report['actual_total_cpu_seconds'],seconds=report['seconds'])),flush=True)


def validate_verifier_result(result,context,context_sha,actual_child_cpu):
    from scripts import metadata_price_collection as c
    c._keys(result,{'version','status','scope','run_id','context_sha256','request_sha256','producer_manifest','producer_report',
        'verifier_source','allocation','fit_attempt_count','process_cpu_seconds','reaped_children_cpu_seconds','process_peak_rss_bytes',
        'started_monotonic','finished_monotonic','seconds','evidence'},'independent verifier receipt')
    expected=dict(version=1,status='verified',scope=context['scope'],run_id=context['run_id'],context_sha256=context_sha,
        request_sha256=context['request_sha256'],producer_manifest=context['producer_manifest'],producer_report=context['producer_report'],
        verifier_source=context['expected_verifier_source'],allocation=context['allocation'],fit_attempt_count=0)
    for name,value in expected.items():
        if c.canonical_json(result[name])!=c.canonical_json(value):raise ValueError('Independent verifier receipt binding differs: '+name)
    for name in ['process_cpu_seconds','reaped_children_cpu_seconds','started_monotonic','finished_monotonic','seconds']:
        if type(result[name]) not in (int,float) or not math.isfinite(result[name]) or result[name]<0:raise ValueError('Invalid verifier cost/clock: '+name)
    if (result['process_cpu_seconds']>context['allocation']['cpu_seconds'] or result['process_cpu_seconds']>actual_child_cpu+1e-6
            or result['reaped_children_cpu_seconds']!=0 or type(result['process_peak_rss_bytes']) is not int
            or not 0<result['process_peak_rss_bytes']<=context['allocation']['rss_bytes']):raise ValueError('Verifier resource/descendant allowance differs')
    if (not context['issued_at_monotonic']<=result['started_monotonic']<=result['finished_monotonic']<=context['allocation']['deadline_monotonic']
            or result['finished_monotonic']>time.monotonic() or abs(result['seconds']-(result['finished_monotonic']-result['started_monotonic']))>1e-6):
        raise ValueError('Verifier absolute clock differs')
    if not isinstance(result['evidence'],dict) or not result['evidence']:raise ValueError('Missing independent verifier evidence')


if __name__=='__main__':main()
