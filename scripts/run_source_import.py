"""One externally reviewed local-gzip import attempt; no source acceptance.

The private worker is launched only by this owner. Tiny evidence does not grant
real source execution or attest the owner's unobserved process-exit tail.
"""
import resource
import time
ENTRY_MONOTONIC=time.monotonic()

from copy import deepcopy
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import tomllib
from types import ModuleType

ROOT=Path(__file__).resolve().parents[1]
CODE=('scripts/run_source_import.py','scripts/source_import.py','uv.lock','pyproject.toml')
REQUEST_KEYS={'version','scope','execution_id','archive','profile','output_directory','resources','fingerprints'}
RESOURCE_FIXED=dict(parent_rss_bytes=2**30,worker_rss_bytes=7*2**30,job_rss_bytes=8*2**30,
    threads=2,engine_memory='2GB',spill_bytes=8*2**30,parent_launch_cpu_reserve=15,
    final_cpu_reserve=2,cleanup_wall_reserve=10,log_bytes=2**20)
CONTEXT_KEYS={'version','scope','execution_id','request','claim','directory','allocation','fingerprints','owner_pid'}


def need(condition,message):
    if not condition:raise ValueError(message)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def same(a,b):return canonical(a)==canonical(b)
def sha_bytes(raw):return hashlib.sha256(raw).hexdigest()
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def sha_token(value):return type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None


def local(name,*,existing=False):
    need(type(name) is str and name and not name.startswith('/') and '\\' not in name,'Normalized project-relative path required')
    parts=name.split('/');need(all(p not in {'','.','..'} for p in parts),'Normalized project-relative path required')
    root=ROOT.resolve();path=root
    for part in parts:
        path=path/part;need(not path.is_symlink(),'Symlink path components forbidden')
    path.resolve().relative_to(root)
    if existing:need(path.is_file(),'Existing regular input file required')
    return path


def relative(path):return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
def reference(name,sha):
    local(name);need(sha_token(sha),'Original SHA256 required');return dict(path=name,sha256=sha)


def json_object(pairs):
    result={}
    for key,value in pairs:
        need(key not in result,'Duplicate JSON object key forbidden');result[key]=value
    return result


def markers(directory):
    if directory is not None:
        for name in ['report.failed.json','worker.log.cleanup-failed.json','worker.log.descendants-failed.json','kernel/report.failed.json']:
            need(not (directory/name).exists(),'Known failed original import cannot perform paid work')


def read_json(name,expected=None,*,maximum=65536):
    path=local(name,existing=True);need(path.stat().st_size<=maximum,'Bounded JSON metadata required');raw=path.read_bytes()
    need(len(raw)<=maximum,'Bounded JSON metadata required');digest=sha_bytes(raw)
    if expected is not None:need(sha_token(expected) and digest==expected,'Original metadata SHA differs')
    body=json.loads(raw,object_pairs_hook=json_object,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON forbidden')))
    need(type(body) is dict,'JSON object required');return body,reference(name,digest)


def exclusive(path,body):
    raw=(canonical(body)+'\n').encode();fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return reference(relative(path),sha_bytes(raw))


def hash_file(path,check):
    h=hashlib.sha256();size=0;check()
    with Path(path).open('rb') as stream:
        while part:=stream.read(2**20):check();h.update(part);size+=len(part)
    check();return h.hexdigest(),size


def repin(pins,check):
    for name,digest in deepcopy(pins).items():
        need(sha_token(digest),'Typed pin SHA required');need(hash_file(local(name,existing=True),check)[0]==digest,'Original file changed: '+name)


def usage(kind=resource.RUSAGE_SELF):
    r=resource.getrusage(kind);cpu=r.ru_utime+r.ru_stime;peak=int(r.ru_maxrss*(1024 if sys.platform.startswith('linux') else 1))
    need(finite(cpu) and cpu>=0 and type(peak) is int and peak>=0,'Known resource usage required');return cpu,peak


def validate_request(body):
    need(type(body) is dict and set(body)==REQUEST_KEYS,'Exact import request vocabulary required')
    need(type(body['version']) is int and body['version']==1 and body['scope']=='externally_reviewed_typed9_source_import','Original reviewed source request required')
    eid=body['execution_id'];need(type(eid) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',eid),'Bounded execution ID required')
    need(body['output_directory']=='artifacts/source-import-runs/'+eid,'Fixed original import output required')
    archive=local(body['archive'],existing=True);need(not body['archive'].startswith('artifacts/source-import-'),'Archive may not be a prior import output')
    local(body['output_directory']);need(type(body['profile']) is dict,'Explicit typed9 source profile required')
    limits=body['resources'];need(type(limits) is dict and set(limits)==set(RESOURCE_FIXED)|{'cpu_seconds','wall_seconds'},'Exact original resource plan required')
    need(same({k:limits[k] for k in RESOURCE_FIXED},RESOURCE_FIXED),'Frozen engine/process resource limits differ')
    for name,lower,upper in [('cpu_seconds',21,7200),('wall_seconds',20,14400)]:
        need(type(limits[name]) is int and lower<=limits[name]<=upper,'Bounded typed original CPU/wall allowance required')
    pins=body['fingerprints'];need(type(pins) is dict and set(pins)==set(CODE) and all(sha_token(v) for v in pins.values()),'Exact owner/kernel/environment code closure required')
    for name in pins:local(name,existing=True)
    return deepcopy(body)


class Budget:
    def __init__(self,limits,started):
        self.limits=deepcopy(limits);need(finite(started) and started<=time.monotonic(),'Earliest original start required');self.started=started
        self.deadline=started+limits['wall_seconds'];self.worker_deadline=self.deadline-limits['cleanup_wall_reserve'];self.directory=None
    def cpu(self):return usage()[0]+usage(resource.RUSAGE_CHILDREN)[0]
    def guard(self,*,final=False):
        markers(self.directory)
        if time.monotonic()>(self.deadline if final else self.worker_deadline):raise TimeoutError('Original import wall allowance exhausted')
        if self.cpu()>self.limits['cpu_seconds']-self.limits['final_cpu_reserve']:raise TimeoutError('Original actual import CPU allowance exhausted')
        if usage()[1]>self.limits['parent_rss_bytes']:raise MemoryError('Import parent sampled peak RSS exceeded')
    def allocation(self):
        self.guard();remaining=int(self.limits['cpu_seconds']-self.cpu()-self.limits['parent_launch_cpu_reserve']-self.limits['final_cpu_reserve'])
        need(remaining>=3,'No remaining bounded worker CPU allowance');return dict(cpu_seconds=remaining,deadline_monotonic=self.worker_deadline,rss_bytes=self.limits['worker_rss_bytes'])


def consume(request_name,expected_sha,*,started):
    # Only bounded metadata/path validation precedes this fixed claim. No input
    # archive read/hash occurs until a claimed original attempt exists.
    body,request_ref=read_json(request_name,expected_sha);body=validate_request(body)
    need(usage(resource.RUSAGE_CHILDREN)==(0,0),'Fresh dedicated import owner required')
    eid=body['execution_id'];claim_name='artifacts/source-import-owner/claims/'+eid+'.json';claim_path=local(claim_name)
    directory=local(body['output_directory']);need(not directory.exists(),'Existing import output cannot be reused')
    claim_path.parent.mkdir(parents=True,mode=0o700,exist_ok=True);local(claim_name)
    directory.parent.mkdir(parents=True,mode=0o700,exist_ok=True);local(body['output_directory'])
    budget=Budget(body['resources'],started);budget.allocation()
    claim=exclusive(claim_path,dict(version=1,scope='consumed_original_typed9_import',request=request_ref,
        execution_id=eid,output_directory=body['output_directory'],owner_pid=os.getpid(),started_monotonic=started,deadline_monotonic=budget.deadline,retry=False))
    return body,request_ref,claim,directory,budget


def load_kernel(check,*,expected_sha):
    """Execute the exact original authenticated source, never cached bytecode."""
    check();need(sha_token(expected_sha),'Original pinned kernel SHA required')
    need(not (ROOT/'scripts'/'__init__.py').exists(),'Unexpected scripts package initialization forbidden')
    path=local('scripts/source_import.py',existing=True)
    with path.open('rb') as stream:raw=stream.read(2**20+1)
    need(len(raw)<=2**20 and sha_bytes(raw)==expected_sha,'Original kernel source snapshot differs')
    check();code=compile(raw,str(path),'exec',dont_inherit=True)
    module=ModuleType('typed9_import_kernel');module.__file__=str(path);module.__package__=''
    exec(code,module.__dict__);check();return module


def environment(check,*,loaded=False,kernel_cpu=None):
    check();need(sys.version_info[:2]==(3,12),'Supported locked Python3.12 required')
    need(sys.platform=='darwin' and os.uname().machine=='arm64','Reviewed initial import target is Darwinarm64')
    raw=local('uv.lock',existing=True).read_bytes();locked={v['name']:v.get('version') for v in tomllib.loads(raw.decode())['package']}
    version=importlib.metadata.version('duckdb');need(version==locked.get('duckdb'),'Installed DuckDB differs from original lock')
    if loaded:
        import duckdb
        need(duckdb.__version__==version,'Loaded DuckDB differs from installed locked version')
    check();return dict(python=sys.version.split()[0],platform=sys.platform,architecture=os.uname().machine,duckdb=version,
        lock_sha256=sha_bytes(raw),kernel_cpu=deepcopy(kernel_cpu),subprocess_probe=False,engine_settings=dict(threads=2,memory='2GB',spill_bytes=8*2**30))


class WorkerBudget:
    def __init__(self,allocation,*,directory=None):
        need(type(allocation) is dict and set(allocation)=={'cpu_seconds','deadline_monotonic','rss_bytes'},'Exact worker allocation required')
        need(type(allocation['cpu_seconds']) is int and allocation['cpu_seconds']>=3 and finite(allocation['deadline_monotonic']) and
             type(allocation['rss_bytes']) is int and allocation['rss_bytes']==7*2**30,'Bounded typed worker allocation required')
        self.allocation=deepcopy(allocation);self.directory=directory;self.stop_event=threading.Event();self.thread=None;self.kernel_cpu=None
    def guard(self):
        markers(self.directory)
        cpu,peak=usage();need(usage(resource.RUSAGE_CHILDREN)==(0,0),'Import worker descendants forbidden')
        if cpu>self.allocation['cpu_seconds']-2:raise TimeoutError('Original import worker CPU exhausted')
        if time.monotonic()>self.allocation['deadline_monotonic']:raise TimeoutError('Original import worker deadline expired')
        if peak>self.allocation['rss_bytes']:raise MemoryError('Import worker sampled peak RSS exceeded')
    def start(self):
        self.guard();cap=self.allocation['cpu_seconds'];previous=resource.getrlimit(resource.RLIMIT_CPU)
        need(previous[1]==resource.RLIM_INFINITY or previous[1]>=cap,'Inherited hard CPU fence below reviewed allocation')
        resource.setrlimit(resource.RLIMIT_CPU,(cap-1,cap));actual=resource.getrlimit(resource.RLIMIT_CPU)
        need(actual==(cap-1,cap),'Kernel CPU fence readback differs');self.kernel_cpu=dict(soft=actual[0],hard=actual[1])
        def monitor():
            while not self.stop_event.wait(.05):
                try:self.guard()
                except BaseException:
                    # Callback checks alone cannot stop blocked native SQL.
                    # Abrupt termination preserves partials; parent owns reap.
                    os.kill(os.getpid(),signal.SIGTERM);return
        self.thread=threading.Thread(target=monitor,name='typed9-import-fence',daemon=True);self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1);need(not self.thread.is_alive(),'Worker monitor cleanup unknown')


def supervise(argv,log_path,budget,allocation):
    """One isolated group; unknown usage survives every error/cleanup path."""
    process=None;primary=None;unknown_usage=False;launch_cpu=usage()[0]
    def unknown(suffix,status,error=None,**details):
        nonlocal unknown_usage
        unknown_usage=True
        target=primary if primary is not None else error
        if target is not None:target.unknown_owned_process_usage=True
        try:
            path=Path(str(log_path)+suffix)
            if not path.exists():exclusive(path,dict(version=1,status=status,pid=process.pid if process else None,retry=False,**details))
        except BaseException as secondary:
            secondary.unknown_owned_process_usage=True
            if target is None:raise
            target.add_note('Unknown usage persistence: '+type(secondary).__name__)
    def alive():
        if process is None:return False
        try:os.killpg(process.pid,0);return True
        except ProcessLookupError:return False
        except BaseException as error:
            unknown('.cleanup-failed.json','unknown_group_observation',error,error_type=type(error).__name__)
            raise
    def cleanup():
        if process is None:return
        for sig in (signal.SIGTERM,signal.SIGKILL):
            # Refresh Popen's leader state before sending a group signal. A
            # previous guard may have failed just as the leader exited.
            exited=process.poll() is not None;living=alive()
            if exited and living:unknown('.descendants-failed.json','unknown_descendant_usage')
            if living:
                # A leader may exit after poll and before this group signal.
                # Successful cleanup cannot prove that no orphan CPU was lost.
                if not exited:unknown('.descendants-failed.json','unverified_descendant_usage_during_forced_group_cleanup')
                try:os.killpg(process.pid,sig)
                except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
            if process.returncode is not None:
                living=alive()
                if not living:return
                unknown('.descendants-failed.json','unknown_descendant_usage')
        raise RuntimeError('Import owned group not verified gone/reaped; usage unknown')
    fd=os.open(log_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as log:
        try:
            process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=ROOT)
            while process.poll() is None:
                budget.guard()
                if time.monotonic()>allocation['deadline_monotonic']:raise TimeoutError('Import child original deadline expired')
                if usage()[0]-launch_cpu>budget.limits['parent_launch_cpu_reserve']-2:raise TimeoutError('Import parent launch CPU reserve exhausted')
                if Path(log_path).stat().st_size>budget.limits['log_bytes']:raise RuntimeError('Import worker log allowance exceeded')
                time.sleep(.05)
            process.wait();descendants=alive();terminal_error=None
            if descendants:unknown_usage=True
            try:budget.guard(final=True)
            except BaseException as error:terminal_error=error
            if descendants:unknown('.descendants-failed.json','unknown_descendant_usage',terminal_error)
            if terminal_error is not None:raise terminal_error
            if descendants:raise RuntimeError('Forbidden surviving import worker descendants; usage unknown')
            need(Path(log_path).stat().st_size<=budget.limits['log_bytes'],'Import worker log allowance exceeded')
            need(process.returncode==0,'Import worker did not exit0: '+str(process.returncode));return process.returncode
        except BaseException as error:
            primary=error
            if unknown_usage:primary.unknown_owned_process_usage=True
            raise
        finally:
            try:cleanup()
            except BaseException as error:
                unknown('.cleanup-failed.json','unknown_owned_process_usage',error,cleanup_error_type=type(error).__name__)
                if primary is not None:primary.add_note('Import process cleanup: '+type(error).__name__)
                else:raise
            finally:
                if unknown_usage:
                    if primary is not None:primary.unknown_owned_process_usage=True
                    elif sys.exc_info()[0] is None:
                        error=RuntimeError('Unknown owned process usage after cleanup');error.unknown_owned_process_usage=True;raise error


def fail(directory,error,*,request=None,claim=None):
    if directory is None or not directory.exists():return
    try:
        own,peak=usage();children,child_peak=usage(resource.RUSAGE_CHILDREN)
        exclusive(directory/'report.failed.json',dict(version=1,status='failed_original_source_import',request=request,claim=claim,
        error_type=type(error).__name__,retry=False,source_acceptance_issued=False,full_lifetime_accepted=False,
        observed_monotonic=time.monotonic(),observed_process_cpu_seconds=own,observed_reaped_children_cpu_seconds=children,
        observed_process_peak_rss_bytes=peak,observed_reaped_children_peak_rss_bytes=child_peak,
        unknown_owned_process_usage=(getattr(error,'unknown_owned_process_usage',False) is True or any((directory/name).exists() for name in ['worker.log.cleanup-failed.json','worker.log.descendants-failed.json']))))
    except BaseException as secondary:error.add_note('Import failure persistence: '+type(secondary).__name__)


def retained_spill(directory,check):
    root=directory/'kernel'/'spill';total=count=0;check()
    if root.exists():
        need(root.is_dir() and not root.is_symlink(),'Owned spill directory required')
        for base,dirs,files in os.walk(root,followlinks=False):
            check()
            for name in dirs:need(not (Path(base)/name).is_symlink(),'Spill symlinks forbidden')
            for name in files:
                check();path=Path(base)/name;need(path.is_file() and not path.is_symlink(),'Owned regular spill files required');total+=path.stat().st_size;count+=1
    check();return dict(retained_bytes=total,retained_files=count,peak_measured=False)


def worker(context_name,expected_sha):
    started=ENTRY_MONOTONIC;directory=None;budget=None;request_ref=claim_ref=None;owns_execution=False
    try:
        context,context_ref=read_json(context_name,expected_sha)
        need(set(context)==CONTEXT_KEYS and type(context['version']) is int and context['version']==1 and context['scope']=='owned_typed9_source_import_worker','Exact issued worker context required')
        for name in ['request','claim']:
            ref=context[name];need(type(ref) is dict and set(ref)=={'path','sha256'},'Original issued authority ref required')
        request_ref=context['request'];claim_ref=context['claim'];body,_=read_json(request_ref['path'],request_ref['sha256']);body=validate_request(body)
        claim,_=read_json(claim_ref['path'],claim_ref['sha256']);eid=body['execution_id']
        directory=local(body['output_directory']);need(context['execution_id']==eid and context['directory']==body['output_directory'],'Original issued worker identity differs')
        need(context_name==body['output_directory']+'/worker-context.json' and directory.is_dir(),'Fixed original context path required')
        markers(directory)
        expected_claim=dict(version=1,scope='consumed_original_typed9_import',request=request_ref,execution_id=eid,output_directory=body['output_directory'],
            owner_pid=context['owner_pid'],started_monotonic=claim.get('started_monotonic'),deadline_monotonic=claim.get('deadline_monotonic'),retry=False)
        need(type(context['owner_pid']) is int and context['owner_pid']>0 and context['owner_pid']==os.getppid(),'Private worker requires its actual original owner parent')
        need(same(claim,expected_claim) and finite(claim['started_monotonic']) and claim['started_monotonic']<=started and
             claim['deadline_monotonic']==claim['started_monotonic']+body['resources']['wall_seconds'],'Original consumed owner association differs')
        need(claim_ref['path']=='artifacts/source-import-owner/claims/'+eid+'.json','Fixed original claim namespace required')
        pins=dict(body['fingerprints']);pins.update({request_ref['path']:request_ref['sha256'],claim_ref['path']:claim_ref['sha256']})
        need(same(context['fingerprints'],pins),'Exact original worker authority/code closure required')
        allocation=context['allocation'];need(finite(allocation.get('deadline_monotonic')) and allocation['deadline_monotonic']==claim['deadline_monotonic']-body['resources']['cleanup_wall_reserve'],'Original absolute worker deadline differs')
        need(type(allocation.get('cpu_seconds')) is int and allocation['cpu_seconds']<=body['resources']['cpu_seconds']-body['resources']['parent_launch_cpu_reserve']-body['resources']['final_cpu_reserve'],'Worker CPU exceeds original request')
        consumed=exclusive(directory/'worker.consumed.json',dict(version=1,scope='consumed_typed9_import_worker',context=context_ref,request=request_ref,claim=claim_ref,started_monotonic=started,retry=False));owns_execution=True
        budget=WorkerBudget(allocation,directory=directory);budget.start();pins[context_ref['path']]=context_ref['sha256'];pins[consumed['path']]=consumed['sha256'];repin(pins,budget.guard)
        env=environment(budget.guard,loaded=True,kernel_cpu=budget.kernel_cpu)
        kernel=load_kernel(budget.guard,expected_sha=body['fingerprints']['scripts/source_import.py']);kernel.validate_profile(body['profile'])
        result=kernel.import_archive(local(body['archive'],existing=True),directory/'kernel',body['profile'],check=budget.guard)
        need(result['status']=='import_kernel_complete_pending_external_source_acceptance' and result['fit_attempt_count']==0 and result['labels_created'] is False,'Kernel result scope differs')
        evidence_name=body['output_directory']+'/kernel/import-evidence.json';evidence,evidence_ref=read_json(evidence_name,maximum=2**20)
        need(same(evidence,result),'Kernel returned/persisted original evidence differs')
        outputs={evidence_ref['path']:evidence_ref['sha256']}
        for name,key in [('events.duckdb','database'),('source.csv.gz','source'),('source.csv','csv'),('validated.csv','validated_csv')]:
            path=directory/'kernel'/name;digest,size=hash_file(path,budget.guard)
            need((digest,size)==(result[key]['sha256'],result[key]['bytes']),'Kernel output physical identity differs');outputs[relative(path)]=digest
        consumed_name=relative(directory/'kernel'/'import.consumed.json');outputs[consumed_name]=hash_file(local(consumed_name),budget.guard)[0]
        need(not (directory/'kernel'/'report.failed.json').exists(),'Known failed kernel cannot complete')
        spill=retained_spill(directory,budget.guard)
        need(spill['retained_bytes']<=body['resources']['spill_bytes'],'Retained spill exceeds original engine setting')
        repin(pins,budget.guard);repin(outputs,budget.guard);budget.stop();budget.guard();cpu,peak=usage()
        receipt=exclusive(directory/'worker-receipt.json',dict(version=1,status='source_import_worker_complete_unaccepted',execution_id=eid,
            request=request_ref,claim=claim_ref,context=context_ref,consumed=consumed,outputs=outputs,evidence=evidence_ref,environment=env,spill_observation=spill,
            started_monotonic=started,finished_monotonic=time.monotonic(),process_cpu_seconds=cpu,process_peak_rss_bytes=peak,descendant_cpu_seconds=usage(resource.RUSAGE_CHILDREN)[0],
            fit_attempt_count=0,labels_created=False,source_acceptance_issued=False))
        repin(pins,budget.guard);repin(outputs,budget.guard);repin({receipt['path']:receipt['sha256']},budget.guard)
        need(not (directory/'report.failed.json').exists() and not (directory/'kernel'/'report.failed.json').exists(),'Late failed import cannot complete');budget.guard()
    except BaseException as error:
        if budget is not None:
            try:budget.stop()
            except BaseException as secondary:error.add_note('Worker monitor cleanup: '+type(secondary).__name__)
        if owns_execution:fail(directory,error,request=request_ref,claim=claim_ref)
        raise


def run_owner(request_name,expected_sha,*,started=ENTRY_MONOTONIC):
    directory=None;request_ref=claim_ref=None;budget=None;owns_directory=False
    try:
        body,request_ref,claim_ref,directory,budget=consume(request_name,expected_sha,started=started)
        directory.mkdir(mode=0o700,parents=False,exist_ok=False);owns_directory=True;budget.directory=directory;budget.guard()
        pins=dict(body['fingerprints']);pins.update({request_ref['path']:request_ref['sha256'],claim_ref['path']:claim_ref['sha256']});repin(pins,budget.guard)
        kernel=load_kernel(budget.guard,expected_sha=body['fingerprints']['scripts/source_import.py']);kernel.validate_profile(body['profile'])
        env=environment(budget.guard);allocation=budget.allocation()
        context=exclusive(directory/'worker-context.json',dict(version=1,scope='owned_typed9_source_import_worker',execution_id=body['execution_id'],request=request_ref,claim=claim_ref,
            directory=body['output_directory'],allocation=allocation,fingerprints=pins,owner_pid=os.getpid()))
        pins[context['path']]=context['sha256'];before_cpu=usage(resource.RUSAGE_CHILDREN)[0]
        code=supervise([sys.executable,'-I','-B',str(local('scripts/run_source_import.py',existing=True)),'--worker-context',context['path'],'--expected-context-sha',context['sha256']],directory/'worker.log',budget,allocation)
        budget.guard(final=True);child_cpu,child_peak=usage(resource.RUSAGE_CHILDREN);actual_child_cpu=child_cpu-before_cpu
        need(finite(actual_child_cpu) and 0<=actual_child_cpu<=allocation['cpu_seconds'],'Actual reaped child CPU exceeds allocation')
        reaped_ref=exclusive(directory/'worker-reaped.json',dict(version=1,scope='observed_reaped_source_import_worker',context=context,
            actual_exit_code=code,worker_reaped=True,owned_group_gone=True,reaped_at_monotonic=time.monotonic(),
            actual_reaped_cpu_seconds=actual_child_cpu,actual_reaped_peak_rss_bytes=child_peak))
        pins[reaped_ref['path']]=reaped_ref['sha256']
        need(child_peak<=allocation['rss_bytes'] and child_peak+usage()[1]<=body['resources']['job_rss_bytes'],'Conservative parent+reaped child peak RSS exceeds job allowance')
        receipt,receipt_ref=read_json(relative(directory/'worker-receipt.json'),maximum=2**20)
        need(set(receipt)=={'version','status','execution_id','request','claim','context','consumed','outputs','evidence','environment','started_monotonic','finished_monotonic',
            'process_cpu_seconds','process_peak_rss_bytes','descendant_cpu_seconds','fit_attempt_count','labels_created','source_acceptance_issued','spill_observation'},'Exact worker receipt vocabulary required')
        need(type(receipt['version']) is int and receipt['version']==1 and receipt['status']=='source_import_worker_complete_unaccepted' and receipt['execution_id']==body['execution_id'],'Original worker result differs')
        need(same(receipt['request'],request_ref) and same(receipt['claim'],claim_ref) and same(receipt['context'],context),'Original worker association differs')
        need(type(receipt['fit_attempt_count']) is int and receipt['fit_attempt_count']==0 and receipt['labels_created'] is False and receipt['source_acceptance_issued'] is False and type(receipt['descendant_cpu_seconds']) in (int,float) and receipt['descendant_cpu_seconds']==0,'Import worker attempted forbidden downstream work/descendants')
        need(finite(receipt['process_cpu_seconds']) and 0<=receipt['process_cpu_seconds']<=actual_child_cpu and type(receipt['process_peak_rss_bytes']) is int and 0<receipt['process_peak_rss_bytes']<=child_peak,'Worker receipt exceeds actual reaped lifetime')
        need(finite(receipt['started_monotonic']) and finite(receipt['finished_monotonic']) and started<=receipt['started_monotonic']<=receipt['finished_monotonic']<=time.monotonic(),'Original worker clocks invalid')
        expected_outputs={body['output_directory']+'/kernel/'+name for name in ['import-evidence.json','events.duckdb','source.csv.gz','source.csv','validated.csv','import.consumed.json']}
        need(type(receipt['outputs']) is dict and set(receipt['outputs'])==expected_outputs,'Exact source-import output closure required')
        need(same(receipt['evidence'],reference(body['output_directory']+'/kernel/import-evidence.json',receipt['outputs'][body['output_directory']+'/kernel/import-evidence.json'])),'Original kernel evidence ref differs')
        expected_consumed_name=body['output_directory']+'/worker.consumed.json';consumed,consumed_ref=read_json(expected_consumed_name)
        need(same(receipt['consumed'],consumed_ref) and same(consumed,dict(version=1,scope='consumed_typed9_import_worker',context=context,request=request_ref,claim=claim_ref,started_monotonic=receipt['started_monotonic'],retry=False)),'Original worker consumption differs')
        spill=retained_spill(directory,lambda:budget.guard(final=True))
        need(same(receipt['spill_observation'],spill) and spill['retained_bytes']<=body['resources']['spill_bytes'],'Retained worker spill observation differs')
        expected_env=deepcopy(env);expected_env['kernel_cpu']=dict(soft=allocation['cpu_seconds']-1,hard=allocation['cpu_seconds'])
        need(same(receipt['environment'],expected_env),'Actual worker locked environment/fence differs')
        pins[body['archive']]=body['profile']['compressed_sha256']
        pins.update(receipt['outputs']);pins[consumed_ref['path']]=consumed_ref['sha256'];pins[receipt_ref['path']]=receipt_ref['sha256'];pins[relative(directory/'worker.log')]=hash_file(directory/'worker.log',lambda:budget.guard(final=True))[0]
        repin(pins,lambda:budget.guard(final=True));need(not (directory/'report.failed.json').exists() and not (directory/'kernel'/'report.failed.json').exists(),'Known failed original import cannot report completion')
        report=dict(version=1,status='completed_source_import_pending_external_source_acceptance',execution_id=body['execution_id'],request=request_ref,claim=claim_ref,worker_context=context,
            worker_receipt=receipt_ref,worker_reaped_boundary=reaped_ref,kernel_evidence=receipt['evidence'],fingerprints=pins,environment=env,worker_environment=receipt['environment'],limits=body['resources'],
            actual_worker_exit_code=code,worker_reaped=True,actual_reaped_worker_cpu_seconds=actual_child_cpu,actual_reaped_worker_peak_rss_bytes=child_peak,
            original_started_monotonic=started,observed_finished_monotonic=time.monotonic(),observed_owner_and_reaped_children_cpu_seconds=budget.cpu(),observed_parent_peak_rss_bytes=usage()[1],
            source_acceptance_issued=False,full_owner_exit_acceptance_required=True,fit_attempt_count=0,labels_created=False,retry=False)
        report_ref=exclusive(directory/'report.json',report);repin(pins,lambda:budget.guard(final=True));repin({report_ref['path']:report_ref['sha256']},lambda:budget.guard(final=True));budget.guard(final=True)
        need(not (directory/'report.failed.json').exists() and not (directory/'kernel'/'report.failed.json').exists(),'Late failed import cannot return completion');return deepcopy(report)
    except BaseException as error:
        if owns_directory:fail(directory,error,request=request_ref,claim=claim_ref)
        elif claim_ref is not None:
            try:exclusive(local(claim_ref['path']+'.failed.json'),dict(version=1,status='failed_owner_output_creation',claim=claim_ref,request=request_ref,error_type=type(error).__name__,retry=False))
            except BaseException as secondary:error.add_note('Claim failure persistence: '+type(secondary).__name__)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--request');group.add_argument('--worker-context')
    parser.add_argument('--expected-request-sha');parser.add_argument('--expected-context-sha');args=parser.parse_args()
    if args.request:
        need(args.expected_request_sha is not None and args.expected_context_sha is None,'Explicit reviewed request SHA required');run_owner(args.request,args.expected_request_sha)
    else:
        need(args.expected_context_sha is not None and args.expected_request_sha is None,'Owner-issued context SHA required');worker(args.worker_context,args.expected_context_sha)


if __name__=='__main__':main()
