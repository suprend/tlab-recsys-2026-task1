"""PROPOSAL ONLY: one fixed018 owner under the already accepted V6 supervisor.

Import defines helpers only. This file issues no grant and must not be launched
until Root independently accepts the exact request, code and operation plan.
"""
import time
ENTRY_MONOTONIC = time.monotonic()
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from types import ModuleType

PROJECT = Path('/Users/mdpospelov/tlab-recsys-2026')
REQUEST = PROJECT/'artifacts/reproduction/requests/oct2019-full-018-20261015-once.json'
REQUEST_SHA = '17edb3954caed6cd409765e870ef8ec547bfc407e30f0e47f5d1df92f553219c'
SUPERVISOR = Path('/tmp/tlab-heldout-harness-processes.py')
SUPERVISOR_SHA = '449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
EXECUTION_ID = 'oct2019-full-018-20261015-once'
LIMITS = dict(cpu_seconds=7190, wall_seconds=10790, rss_bytes=8*2**30)
OWNER_FINGERPRINTS = {
    'scripts/run_source_import.py': '5df50bb2577b4515c5d80a5eaf4a6f2bf18abe344039d1cd22a51a872e1c7653',
    'scripts/source_import.py': '7d7ed34b336294bd18d822b9798a7b644f45dc72f8c1f6edeb6d518b55284236',
    'uv.lock': '4675021f74063889ffb596325b9e608a3a5776a29f967d052b86923e40485eab',
    'pyproject.toml': '416cef16f91689db9f244c9c178c86bebb0f7e8140b2081372bd2324148a816a',
}
PREFIX = '/tmp/tlab-full-source018-20261015-once'
PROCESS_LOG = Path(PREFIX+'-owner.stdout-stderr.log')
PROCESS_RECEIPT = Path(PREFIX+'-process-receipt.json')
DRIVER_STDOUT = Path(PREFIX+'-driver.stdout.json')
DRIVER_ERROR = Path(PREFIX+'-driver.error.json')
OUTPUTS = (PROCESS_LOG, PROCESS_RECEIPT, DRIVER_STDOUT, DRIVER_ERROR)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def raw_snapshot(path, expected):
    with Path(path).open('rb') as stream:
        raw = stream.read(2**20+1)
    need(len(raw) <= 2**20 and hashlib.sha256(raw).hexdigest() == expected,
         'Bounded original source/request bytes changed: '+str(path))
    return raw


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'Duplicate JSON member')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON constant '+value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def no_alias(path):
    need(path.is_absolute(), 'Absolute fixed path required')
    for part in (path, *path.parents):
        need(not part.is_symlink(), 'Project path symlinks forbidden: '+str(part))


def guard():
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    need(children.ru_utime + children.ru_stime == 0 and children.ru_maxrss == 0,
         'Fresh original supervisor process required')
    need(own.ru_utime + own.ru_stime < LIMITS['cpu_seconds']-5,
         'Original outer CPU launch reserve exhausted')
    need(time.monotonic()-ENTRY_MONOTONIC < LIMITS['wall_seconds']-5,
         'Original outer wall launch reserve exhausted')
    need(own.ru_maxrss <= LIMITS['rss_bytes'], 'Outer sampled peak already exceeds budget')


def command():
    return [str(PROJECT/'.venv/bin/python'), '-I', '-B',
            str(PROJECT/'scripts/run_source_import.py'), '--request', REQUEST.relative_to(PROJECT).as_posix(),
            '--expected-request-sha', REQUEST_SHA]


def reject_existing_outputs():
    for path in OUTPUTS:
        need(not path.exists() and not path.is_symlink(), 'Fixed TMP output already consumed: '+str(path))


def preflight():
    need(len(sys.argv) == 1, 'Fixed driver takes no arguments')
    need(sys.version_info[:2] == (3, 12), 'Fresh Python3.12 required')
    need(sys.flags.isolated == 1 and sys.flags.dont_write_bytecode == 1,
         'Driver must itself run with -I -B')
    need(sys.platform == 'darwin' and os.uname().machine == 'arm64',
         'Accepted owner runtime is Darwin arm64')
    need(Path(sys.prefix).resolve() == (PROJECT/'.venv').resolve(),
         'Prepared project virtual environment required')
    reject_existing_outputs()
    for path in (REQUEST, PROJECT/'artifacts/source-import-runs'/EXECUTION_ID,
                 PROJECT/'artifacts/source-import-owner/claims'/(EXECUTION_ID+'.json')):
        no_alias(path)
    for path in (PROJECT/'artifacts/source-import-runs'/EXECUTION_ID,
                 PROJECT/'artifacts/source-import-owner/claims'/(EXECUTION_ID+'.json')):
        need(not path.exists(), 'Original inner output/claim already consumed: '+str(path))
    guard()
    raw = raw_snapshot(REQUEST, REQUEST_SHA)
    body = unique_json(raw)
    need(body['execution_id'] == EXECUTION_ID and body['output_directory'] ==
         'artifacts/source-import-runs/'+EXECUTION_ID, 'Fixed original owner destinations differ')
    need(body['fingerprints'] == OWNER_FINGERPRINTS, 'Accepted owner closure differs')
    for key, expected in [('cpu_seconds',7200), ('wall_seconds',10800), ('job_rss_bytes',8*2**30)]:
        need(type(body['resources'][key]) is int and body['resources'][key] == expected,
             'Original inner resources differ')
    for name, expected in OWNER_FINGERPRINTS.items():
        guard()
        no_alias(PROJECT/name)
        raw_snapshot(PROJECT/name, expected)
    guard()
    return command()


def load_supervisor():
    raw = raw_snapshot(SUPERVISOR, SUPERVISOR_SHA)
    module = ModuleType('tlab_full_source018_reviewed_supervisor_v6')
    module.__file__ = str(SUPERVISOR)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(SUPERVISOR), 'exec', dont_inherit=True), module.__dict__)
    return module


def exclusive_json(path, body):
    raw = (json.dumps(body, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)+'\n').encode()
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def receipt(supervisor_report, cleanup_evidence, attempted):
    return dict(version=1, scope='external_full_source018_process_boundary_only',
                request=dict(path=str(REQUEST), sha256=REQUEST_SHA),
                supervisor=dict(path=str(SUPERVISOR), sha256=SUPERVISOR_SHA),
                command=command(), outer_limits=LIMITS.copy(),
                entry_monotonic=ENTRY_MONOTONIC,
                supervision_attempted=attempted,
                supervisor_report=supervisor_report,
                supervisor_exception_cleanup_evidence=cleanup_evidence,
                supervisor_flags_reinterpreted=False,
                nested_owner_worker_ledger_accepted=False,
                source_acceptance_issued=False,
                external_full_exit_acceptance_issued=False,
                driver_exit_tail_measured=False)


def main():
    report = None
    attempted = False
    receipt_written = False
    namespace_clear = False
    try:
        reject_existing_outputs()
        namespace_clear = True
        argv = preflight()
        supervisor = load_supervisor()
        guard()
        attempted = True
        report = supervisor.supervise(argv, PROCESS_LOG, started=ENTRY_MONOTONIC,
                                      cwd=PROJECT, **LIMITS)
        exclusive_json(PROCESS_RECEIPT, receipt(report, None, attempted))
        receipt_written = True
        need(type(report) is dict and report.get('status') == 'verified_normal_exit'
             and report.get('reaped') is True and type(report.get('exit_code')) is int
             and report['exit_code'] == 0 and report.get('unknown_active_work') is False,
             'Original supervisor did not return a known normal process boundary')
        exclusive_json(DRIVER_STDOUT, dict(version=1,
                       status='process_returned_pending_external_owner_output_and_full_exit_acceptance',
                       process_receipt=str(PROCESS_RECEIPT), process_log=str(PROCESS_LOG),
                       source_acceptance_issued=False, driver_exit_tail_measured=False))
        return 0
    except BaseException as exc:
        cleanup = getattr(exc, 'supervisor_cleanup_evidence', None)
        errors = []
        if namespace_clear and not receipt_written:
            try:
                exclusive_json(PROCESS_RECEIPT, receipt(report, cleanup, attempted))
            except BaseException as secondary:
                errors.append(type(secondary).__name__+': '+str(secondary)[:4096])
        try:
            if not namespace_clear:
                raise FileExistsError('Existing TMP namespace retained without new receipts')
            exclusive_json(DRIVER_ERROR, dict(version=1, status='failed',
                exception_type=type(exc).__name__, error=str(exc)[:4096],
                process_receipt=str(PROCESS_RECEIPT), supervision_attempted=attempted,
                original_outputs_not_overwritten=True, persistence_errors=errors,
                no_automatic_retry=True, source_acceptance_issued=False))
        except BaseException as secondary:
            errors.append(type(secondary).__name__+': '+str(secondary)[:4096])
        print('Full-source018 driver failed: '+type(exc).__name__+': '+str(exc)[:4096]
              + ('; persistence errors: '+repr(errors) if errors else ''), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
