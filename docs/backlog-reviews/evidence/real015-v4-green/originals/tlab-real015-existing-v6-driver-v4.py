"""Fixed real015 process binding; prospective only, no gate/acceptance issuer.

ONE accepted V6 -> controller -> unchanged owner CLI -> its six owned workers.
Root manually reads actual metadata and issues the four existing gates. No
owner import, Session construction, monkeypatch, native/model/data operation,
438/439 preflight, retry, dynamic backend or new lifetime is implemented here.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import types

START = time.monotonic()
ROOT = Path('/Users/mdpospelov/tlab-recsys-2026')
SELF = Path('/tmp/tlab-real015-existing-v6-driver-v4.py')
PYTHON = ROOT/'.venv/bin/python'
OWNER = ROOT/'scripts/run_heldout_reporting.py'
OWNER_SHA = '169b92aebf94a40b6ae76243e1821e983d4dc88657d120fe385155768a4d5cac'
REQUEST = ROOT/'artifacts/heldout-study/tlab015-native-metadata-v4/request.json'
REQUEST_SHA = 'de1eacf7283d564ea5dae8a1f38a9938c4d6f4bc560dcbe79af9d659fa40101b'
V6 = Path('/tmp/tlab-heldout-harness-processes.py')
V6_SHA = '449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
OUT = Path('/tmp/tlab-real015-observer-environment-recovery-20261015')
CLAIM = ROOT/'artifacts/heldout-study/owner.claim.json'
ROLES = ('source','source_oracle','predictions','prediction_oracle','targets_evaluation','metric_oracle')
GATES = {
 'initial_execution':'artifacts/acceptance/tlab015-reserved-initial-execution-v1.json',
 'source_acceptance':'artifacts/acceptance/tlab015-reserved-source-v1.json',
 'prediction_acceptance':'artifacts/acceptance/tlab015-reserved-predictions-v1.json',
 'target_execution':'artifacts/acceptance/tlab015-reserved-target-execution-v1.json'}


def need(value, message):
    if not value: raise ValueError(message)


def read(path, cap=262144):
    need(not path.is_symlink(), 'No symlink metadata/source')
    before=path.stat(); need(0 < before.st_size <= cap, 'Bounded small metadata/code required')
    raw=path.read_bytes(); after=path.stat()
    need(len(raw)==before.st_size and (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_ctime_ns,before.st_size)==
         (after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns,after.st_size), 'Small bytes changed while reading')
    return raw


def pin(path, digest):
    need(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest), 'Issued SHA required')
    raw=read(path); need(hashlib.sha256(raw).hexdigest()==digest, 'Fixed source/request SHA differs'); return raw


def body(raw):
    def unique(pairs):
        answer={}
        for k,v in pairs: need(k not in answer,'Duplicate JSON key'); answer[k]=v
        return answer
    def bad(value): raise ValueError('Nonfinite JSON')
    def finite(value):
        n=float(value);need(math.isfinite(n),'Nonfinite JSON exponent');return n
    return json.loads(raw,object_pairs_hook=unique,parse_constant=bad,parse_float=finite)


def write(name, value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    need(len(raw)<=262144,'Bounded observer receipt')
    with (OUT/name).open('xb') as f: f.write(raw);f.flush();os.fsync(f.fileno())


def failure_receipt(name, primary, fields):
    """Retain raw V6 facts; secondary audit failure never masks the primary."""
    try:
        fields['supervisor_exception_cleanup_evidence']=getattr(primary,'supervisor_cleanup_evidence',None)
        write(name,fields)
    except BaseException as secondary:
        # Keep the actual secondary exception separately, including serialization
        # failures. Annotation itself is best effort; the caller's bare raise
        # must always preserve the original BaseException and its attachment.
        try: primary.failure_receipt_persistence_error=secondary
        except BaseException: pass
        try: primary.add_note(name+' persistence failed: '+type(secondary).__name__)
        except BaseException: pass


def check_fixed(issued):
    need(Path(__file__).absolute()==SELF and Path(sys.executable).resolve()==PYTHON.resolve(), 'Fixed driver/interpreter path')
    pin(SELF,issued);pin(OWNER,OWNER_SHA)
    request=body(pin(REQUEST,REQUEST_SHA))
    need(request.get('scope')=='prospective_reserved_reporting_owner' and request.get('authority_paths')==GATES,
         'Original fixed real015 request/gates')
    need(not CLAIM.exists() and not any((ROOT/name).exists() for name in GATES.values()),
         'Original claim/four gates must be absent before actual owner launch')
    return request


def environment():
    # A new prefix plus -B prevents reads of old project pyc and new pyc writes.
    # Owner's unchanged worker CLI inherits these explicit settings.
    return dict(PATH='/usr/bin:/bin:/usr/sbin:/sbin',LANG='C',LC_ALL='C',
        PYTHONCOERCECLOCALE='0',PYTHONUTF8='1',
        PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONPYCACHEPREFIX=str(OUT/'pristine-pycache'),
        TMPDIR=str(OUT/'native-temp'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',NUMEXPR_NUM_THREADS='2')


def validate_child_environment(actual):
    """Exact curated mapping plus one bounded Darwin runtime encoding key.

    The exception admits no Python/locale/path change. Its three unsigned
    32-bit hexadecimal fields must use 0x prefixes; the first is this real UID,
    which must equal the effective UID. No runtime key is required or rewritten.
    """
    curated=environment()
    need(type(actual) is dict and all(type(k) is str and type(v) is str for k,v in actual.items()),
         'Exact string environment mapping required')
    need(all(actual.get(k)==v for k,v in curated.items()), 'Missing or changed curated environment')
    extra=set(actual)-set(curated)
    need(not extra or (sys.platform=='darwin' and extra=={'__CF_USER_TEXT_ENCODING'}),
         'Unexpected child environment keys')
    if extra:
        value=actual['__CF_USER_TEXT_ENCODING']
        parts=value.split(':')
        need(len(value)<=32 and len(parts)==3 and all(3<=len(p)<=10 and p.startswith('0x')
             and all(c in '0123456789abcdefABCDEF' for c in p[2:]) for p in parts),
             'Malformed Darwin CF runtime encoding')
        uid=os.getuid();euid=os.geteuid()
        need(uid==euid and int(parts[0][2:],16)==uid, 'Darwin CF runtime UID differs')
    return True


def controller(issued):
    check_fixed(issued)
    need(validate_child_environment(dict(os.environ)) and (OUT/'pristine-pycache').is_dir(), 'Exact inherited pristine child environment')
    write('controller.consumed.json',dict(status='consumed_once',request_sha256=REQUEST_SHA,driver_sha256=issued,
        original_stage_caps=dict(cpu_seconds=4200,wall_seconds=7200,rss_bytes=8*2**30),gates_issued=0))
    process=None; reaped=False
    try:
        with (OUT/'owner.log').open('xb') as log:
            process=subprocess.Popen([str(PYTHON),'-B',str(OWNER),'--request',str(REQUEST)],
                cwd=ROOT,env=environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            pid,status,usage=os.wait4(process.pid,0)  # exclusive owner reap; never poll/wait twice
            need(pid==process.pid,'Original owner wait4 identity');reaped=True
            code=os.waitstatus_to_exitcode(status);process.returncode=code
        result=dict(status='owner_failed_pending_V6_cleanup',owner_exit_code=code,owner_explicitly_reaped=True,
            inclusive_owner_cpu_seconds=usage.ru_utime+usage.ru_stime,owner_wait4_maxrss_bytes=usage.ru_maxrss,
            gates_issued=0,source_acceptance_issued=False,execution_authority_issued=False,full_exit_accepted=False)
        if code==0:
            claim_raw=read(CLAIM);claim=body(claim_raw);directory=ROOT/claim['output_directory']
            need(directory.resolve().is_relative_to((ROOT/'artifacts/heldout-invocations').resolve()), 'Owner output namespace')
            report_raw=read(directory/'report.json',8*2**20);report=body(report_raw)
            need(claim['request']==dict(path=REQUEST.relative_to(ROOT).as_posix(),sha256=REQUEST_SHA)
                 and claim['owner_source']==dict(path=OWNER.relative_to(ROOT).as_posix(),sha256=OWNER_SHA), 'Owner claim original binding')
            need(report.get('status')=='verified_reporting_pending_external_lifetime_acceptance'
                 and report.get('unknown_active_work') is False and report.get('active_role') is None
                 and report.get('fit_attempt_count')==0 and [r.get('role') for r in report.get('roles',[])]==list(ROLES)
                 and set(report.get('gates',{}))==set(GATES) and not (directory/'report.failed.json').exists(), 'Complete pending owner ledger required')
            result.update(status='six_role_owner_complete_pending_Root_readback_and_full_exit',owner_directory=claim['output_directory'],
                          owner_claim_sha256=hashlib.sha256(claim_raw).hexdigest(),owner_report_sha256=hashlib.sha256(report_raw).hexdigest())
        write('controller-result.json',result)
        need(code==0,'Original owner nonzero exit; no retry/refill')
        return result
    except BaseException as exc:
        failure_receipt('controller.failed.json',exc,dict(status='failed_consumed_no_retry',error_type=type(exc).__name__,
            owner_started=process is not None,owner_reaped=reaped,unknown_active_work=True,
            cleanup_owner='accepted_outer_V6_observed_cohort',gates_issued=0,full_exit_accepted=False))
        raise


def outer(issued):
    check_fixed(issued)
    OUT.mkdir(mode=0o700)  # fixed exclusive namespace; no new ID or automatic retry
    (OUT/'pristine-pycache').mkdir();(OUT/'native-temp').mkdir()
    write('observer.consumed.json',dict(status='consumed_once',request_sha256=REQUEST_SHA,driver_sha256=issued,
        supervisor_sha256=V6_SHA,caps=dict(cpu_seconds=4190,wall_seconds=7190,rss_bytes=8*2**30),
        Root_external_reserve=dict(cpu_seconds=10,wall_seconds=10),gates_issued=0,execution_authority_issued=False))
    module=types.ModuleType('accepted_V6_real015');module.__file__=str(V6);sys.modules[module.__name__]=module
    exec(compile(pin(V6,V6_SHA),str(V6),'exec',dont_inherit=True),module.__dict__)
    os.environ.clear();os.environ.update(environment())
    try:
        observation=module.supervise([str(PYTHON),'-B',str(SELF),'--controller','--issued-driver-sha256',issued],
            OUT/'cohort.log',started=START,cpu_seconds=4190,wall_seconds=7190,rss_bytes=8*2**30,cwd=ROOT)
        write('V6-observation.json',observation)
        need(observation.get('status')=='verified_normal_exit' and observation.get('exit_code')==0
             and observation.get('unknown_active_work') is False,'V6 process boundary failed; preserve original attempt')
    except BaseException as exc:
        failure_receipt('observer.failed.json',exc,dict(status='failed_consumed_no_retry',error_type=type(exc).__name__,
            unknown_active_work=True,full_exit_accepted=False,execution_authority_issued=False))
        raise
    # Root must independently read all actual role/gate evidence and the full
    # external terminal. Neither this return nor V6's internal tail is acceptance.
    return observation


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controller',action='store_true')
    parser.add_argument('--issued-driver-sha256',required=True);args=parser.parse_args()
    (controller if args.controller else outer)(args.issued_driver_sha256)


if __name__=='__main__': main()
