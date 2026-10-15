"""TMP proposal: ONE V6-owned whole018 source/score/parity episode.

No invocation is authorized by these bytes. Root must issue an exact request,
driver SHA and bounded once operation after independent code review. The sole
fixed child calls ownerV2 then independent parityV1; it never launches a child.
All acceptance and complete-exit decisions remain outside this driver.
"""
import time
ENTRY_MONOTONIC = time.monotonic()
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import stat
import sys
from types import ModuleType

PROJECT = Path('/Users/mdpospelov/tlab-recsys-2026')
SELF = Path('/private/tmp/tlab-development-whole018-driver-v2.py')
REQUEST = 'artifacts/reproduction/requests/oct2019-development-oct22-source-to-scores-once.json'
REQUEST_SHA = '0d7d99a9a8fb2a1f9bfbf9375e57935f49f52ee48685ae92dbb7f66f5dc41ce9'
EXECUTION_ID = 'oct2019-development-oct22-source-to-scores-once'
OWNER = 'scripts/reproduce_development_slice.py'
OWNER_SHA = '7acd73cc7da976cf62d6fc9f623b7b89d8ed67607c8b57617017ef58620ef39a'
PARITY = 'scripts/development_day_parity.py'
PARITY_SHA = 'ae133b9f8725ba99883d604609a29a62201f070a6cd7a81ddf9460488e011baa'
V6 = 'docs/backlog-reviews/evidence/source-import-tiny-v5/original/supervisor-v6.py'
V6_SHA = '449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
HANDOFF_SHA = 'fd7304383e9c025d205a0b7f9060187f8062daa9baa2f9b0f86ea6a18323e05b'
OUT = 'artifacts/development-source-to-score-runs/' + EXECUTION_ID
LIMITS = dict(cpu_seconds=590, wall_seconds=890, rss_bytes=8 * 2**30)
OWNER_ADMISSION_CPU = 400
OWNER_ADMISSION_WALL = 650
PARITY_CPU = 150
PARITY_WALL = 200
PIPELINE_WORK_CPU = 550
PIPELINE_WORK_WALL = 850
PREFIX = Path('/private/tmp/tlab-development-oct22-source-to-scores-once')
CONSUMED = Path(str(PREFIX) + '-consumed.json')
LOG = Path(str(PREFIX) + '-pipeline.stdout-stderr.log')
PROCESS = Path(str(PREFIX) + '-process-receipt.json')
PIPELINE = Path(str(PREFIX) + '-pipeline-evidence.json')
PIPELINE_FAILURE = Path(str(PREFIX) + '-pipeline-failure.json')
DRIVER = Path(str(PREFIX) + '-driver-result.json')
ERROR = Path(str(PREFIX) + '-driver-failure.json')
NAMESPACE = (CONSUMED, LOG, PROCESS, PIPELINE, PIPELINE_FAILURE, DRIVER, ERROR)
CAP = 2**20


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(value):
    need(type(value) is str and len(value) == 64 and
         all(c in '0123456789abcdef' for c in value), 'External exact SHA256 required')
    return value


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()


def unique_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'Duplicate JSON member'); value[key] = item
        return value
    def reject(item):
        raise ValueError('Nonfinite JSON constant: ' + item)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    # Reject exponent-overflow floats as well as literal NaN/Infinity.
    encode(value)
    return value


def no_alias(path):
    need(path.is_absolute(), 'Absolute fixed physical path required')
    for part in (path, *path.parents):
        need(not part.is_symlink(), 'Symlink path forbidden: ' + str(part))


def snapshot(path, expected):
    sha(expected); no_alias(path)
    before = stable_stat(path)
    with path.open('rb') as handle:
        raw = handle.read(CAP + 1)
    need(0 < len(raw) <= CAP and stable_stat(path) == before and
         hashlib.sha256(raw).hexdigest() == expected,
         'Bounded original bytes changed: ' + str(path))
    return raw


def stable_stat(path):
    value = path.stat()
    need(stat.S_ISREG(value.st_mode) and 0 < value.st_size <= CAP, 'Bounded regular metadata/source required')
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def exclusive(path, value):
    raw = encode(value)
    need(len(raw) <= CAP, 'Bounded driver evidence required')
    no_alias(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def usage():
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = float(own.ru_utime + own.ru_stime)
    waited = float(children.ru_utime + children.ru_stime)
    need(math.isfinite(cpu) and math.isfinite(waited) and min(cpu, waited) >= 0,
         'Known finite lifetime CPU required')
    return dict(self_cpu_seconds=cpu, waited_cpu_seconds=waited,
                waited_peak_rss_bytes=children.ru_maxrss,
                process_peak_rss_bytes=own.ru_maxrss * (1 if sys.platform == 'darwin' else 1024))


class PipelineBudget:
    """Fixed cooperative guards, never a new supervision or authority layer."""
    def __init__(self, started):
        need(type(started) is float and math.isfinite(started) and
             0 <= started <= ENTRY_MONOTONIC <= time.monotonic(), 'Original outer clock required')
        self.started = started
        self.parity_start = None

    def telemetry(self):
        value = usage()
        need(value['waited_cpu_seconds'] == 0 and value['waited_peak_rss_bytes'] == 0,
             'Fixed pipeline must never reap children')
        value['original_wall_seconds'] = time.monotonic() - self.started
        return value

    def check(self):
        value = self.telemetry()
        need(value['self_cpu_seconds'] < PIPELINE_WORK_CPU and
             value['original_wall_seconds'] < PIPELINE_WORK_WALL and
             value['process_peak_rss_bytes'] <= LIMITS['rss_bytes'],
             'Original whole episode work/tail reserve exhausted')
        if self.parity_start is not None:
            need(value['self_cpu_seconds'] - self.parity_start['self_cpu_seconds'] < PARITY_CPU and
                 value['original_wall_seconds'] - self.parity_start['original_wall_seconds'] < PARITY_WALL,
                 'Verifier phase cap exhausted within original episode')
        return value

    def admit_parity(self):
        value = self.check()
        need(value['self_cpu_seconds'] <= OWNER_ADMISSION_CPU and
             value['original_wall_seconds'] <= OWNER_ADMISSION_WALL,
             'Owner returned too late; parity reserve retained, no verifier launch')
        self.parity_start = value
        return value


def load_exact(path, expected, name):
    raw = snapshot(path, expected)
    need(name not in sys.modules, 'Fixed module name already loaded')
    module = ModuleType(name); module.__file__ = str(path); sys.modules[name] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def fixed_request(expected):
    need(expected == REQUEST_SHA, 'Exact Root-reviewed request candidate SHA required')
    body = unique_json(snapshot(PROJECT / REQUEST, expected))
    need(type(body) is dict and body.get('execution_id') == EXECUTION_ID and
         body.get('output_directory') == OUT, 'Exact original once request namespace required')
    need(body.get('code', {}).get(OWNER) == OWNER_SHA and
         body.get('reference_handoff', {}).get('sha256') == HANDOFF_SHA and
         body.get('environment', {}).get('external_supervisor') == dict(path=V6, sha256=V6_SHA),
         'Fixed owner, accepted V6 and Root narrow handoff required')
    b = body.get('resources', {})
    need(b == dict(total_cpu_seconds=600, total_wall_seconds=900, job_rss_bytes=8*2**30,
                   threads=2, engine_memory='2GB', spill_bytes=2*2**30,
                   final_tail_cpu_seconds=10, final_tail_wall_seconds=15),
         'Original whole resources/tails differ')
    return body


def identity(request_sha, driver_sha, started):
    return dict(version=1, scope='whole018_fixed_driver_boundary_only',
                execution_id=EXECUTION_ID, original_request=dict(path=REQUEST, sha256=request_sha),
                driver=dict(path=str(SELF), sha256=driver_sha), original_entry_monotonic=started,
                owner=dict(path=OWNER, sha256=OWNER_SHA), parity_checker=dict(path=PARITY, sha256=PARITY_SHA),
                supervisor=dict(path=V6, sha256=V6_SHA), outer_limits=LIMITS,
                total_episode_bounds=dict(cpu_seconds=600, wall_seconds=900, rss_bytes=8*2**30),
                source_acceptance_issued=False, independent_output_acceptance_issued=False,
                full_exit_acceptance_issued=False, driver_exit_tail_measured=False,
                no_automatic_retry=True)


def check_returned_owner(report, expected):
    need(type(report) is dict and report.get('original_request_sha256') == expected and
         report.get('execution_id') == EXECUTION_ID and
         report.get('status') == 'pending_independent_all_keyed_parity_and_full_exit_acceptance' and
         report.get('fit_attempt_count') == 0 and report.get('metric_looks') == 0 and
         report.get('query_targets_opened') is False and
         report.get('progress', {}).get('source_connection_closed') is True,
         'Owner did not return the fixed completed pending report')


def check_returned_parity(value, expected):
    need(type(value) is dict and value.get('scope') == 'independent_Oct22_all_keyed_mechanical_parity' and
         value.get('status') == 'parity_checks_passed_pending_Root_and_full_exit' and
         value.get('original_request_sha256') == expected and value.get('execution_id') == EXECUTION_ID and
         value.get('same_original_stage_budget_required') is True and value.get('query_count') == 2000 and
         value.get('all_query_count') == 4000 and value.get('all_pair_count') == 817149 and
         value.get('model_columns') == dict(B=41,W=44) and value.get('sampling') == 'none_all_rows_and_full_ranks',
         'Independent verifier returned incomplete required all-keyed evidence')
    rows = value.get('candidate_count')
    need(type(rows) is int and 0 <= rows <= 440000, 'Bounded complete parity row count required')
    need(type(value.get('score_checks')) is dict and set(value['score_checks']) == {'B','W'},
         'Both complete score/rank checks required')
    for result in value['score_checks'].values():
        error = result.get('max_abs_error')
        need(result.get('rows') == rows and result.get('complete_ranks_equal') is True and
             type(error) in (int,float) and math.isfinite(error) and 0 <= error <= 1e-12,
             'Finite float64 raw score and complete ranking parity required')
    need(type(value.get('model_representation_sha256')) is dict and
         set(value['model_representation_sha256']) == {'B','W'}, 'Both model representation hashes required')
    for digest in value['model_representation_sha256'].values(): sha(digest)
    sha(value.get('owner_report_sha256'))
    need(type(value.get('input_output_byte_bindings')) is dict and
         len(value['input_output_byte_bindings']) == 15,
         'Complete exact request/handoff/report/six-output/six-reference bindings required')
    need(all(type(value.get(k)) is int and value[k] == 0 for k in
             ('target_relations_opened','model_files_opened','fit_attempts','metrics_computed')) and
         all(value.get(k) is False for k in
             ('source_acceptance_issued','execution_authority_issued','external_exit_accepted')),
         'Independent parity authority/no-target boundaries required')


def pipeline_main(request_sha, driver_sha, started):
    budget = PipelineBudget(started)
    owner_return = parity = None
    try:
        budget.check(); snapshot(SELF, driver_sha); fixed_request(request_sha)
        consumed = unique_json(snapshot(CONSUMED, hashlib.sha256(encode(identity(request_sha, driver_sha, started))).hexdigest()))
        need(consumed == identity(request_sha, driver_sha, started), 'Original driver consumed marker differs')
        need(not (PROJECT / OUT).exists() and not (PROJECT / OUT).is_symlink(), 'Owner namespace already consumed')
        owner = load_exact(PROJECT / OWNER, OWNER_SHA, '_tlab018_fixed_owner_v2')
        budget.check()
        owner_return = owner.run_slice(REQUEST, request_sha, started_monotonic=started)
        check_returned_owner(owner_return, request_sha)
        before_parity = budget.admit_parity()
        checker = load_exact(PROJECT / PARITY, PARITY_SHA, '_tlab018_independent_parity_v2')
        budget.check()
        parity = checker.verify_request(REQUEST, request_sha, check=budget.check)
        after_parity = budget.check()
        check_returned_parity(parity, request_sha)
        for path, digest in ((SELF, driver_sha), (PROJECT / OWNER, OWNER_SHA),
                             (PROJECT / PARITY, PARITY_SHA), (PROJECT / V6, V6_SHA),
                             (PROJECT / REQUEST, request_sha)):
            budget.check(); snapshot(path, digest)
        exclusive(PIPELINE, dict(**identity(request_sha, driver_sha, started),
            status='owner_and_independent_parity_returned_pending_root_full_exit_acceptance',
            owner_report_path=OUT+'/report.json', owner_returned=True, parity=parity,
            before_parity=before_parity, after_parity=after_parity,
            owner_subcap_kind='successful_return_admission_not_interruptible_native_fence',
            final_telemetry=budget.check()))
        budget.check(); return 0
    except BaseException as exc:
        try:
            exclusive(PIPELINE_FAILURE, dict(**identity(request_sha, driver_sha, started),
                status='failed_consumed_no_retry', owner_returned=owner_return is not None,
                parity_returned=parity is not None, error_type=type(exc).__name__, error=str(exc)[:2048],
                cleanup_evidence=getattr(exc, 'supervisor_cleanup_evidence', None)))
        except BaseException as secondary:
            print('Pipeline failure persistence unknown: '+str(secondary)[:512], file=sys.stderr)
        print('Whole018 pipeline failed: '+type(exc).__name__+': '+str(exc)[:2048], file=sys.stderr)
        return 1


def fixed_command(request_sha, driver_sha, started):
    return [str(PROJECT / '.venv/bin/python'), '-I', '-B', str(SELF), '--pipeline',
            '--expected-request-sha', request_sha, '--expected-driver-sha', driver_sha,
            '--original-started-monotonic', repr(started)]


def runtime():
    need(sys.version_info[:2] == (3,12) and sys.flags.isolated == 1 and
         sys.flags.dont_write_bytecode == 1 and sys.platform == 'darwin' and os.uname().machine == 'arm64',
         'Fixed fresh isolated Darwin arm64 Python3.12 required')
    need(Path(sys.prefix).resolve() == (PROJECT / '.venv').resolve() and Path(__file__).resolve() == SELF,
         'Fixed project interpreter and TMP driver path required')


def require_normal_boundary(report):
    need(type(report) is dict and report.get('status') == 'verified_normal_exit' and
         report.get('reaped') is True and type(report.get('exit_code')) is int and
         report.get('exit_code') == 0 and report.get('unknown_active_work') is False,
         'Original V6 did not report known normal reap')


def outer_main(request_sha, driver_sha):
    consumed = False; report = None; attempted = False; receipt_written = False
    base = identity(request_sha, driver_sha, ENTRY_MONOTONIC)
    try:
        runtime()
        for path in NAMESPACE:
            no_alias(path); need(not path.exists(), 'Existing fixed driver namespace retained: '+str(path))
        exclusive(CONSUMED, base); consumed = True
        snapshot(SELF, driver_sha); body = fixed_request(request_sha)
        no_alias(PROJECT / OUT); need(not (PROJECT / OUT).exists(), 'Existing owner namespace retained')
        for name, digest in ((OWNER, OWNER_SHA), (PARITY, PARITY_SHA)):
            snapshot(PROJECT / name, digest)
        snapshot(PROJECT / body['reference_handoff']['path'], HANDOFF_SHA)
        supervisor = load_exact(PROJECT / V6, V6_SHA, '_tlab018_exact_supervisor_v6')
        current = usage()
        need(current['waited_cpu_seconds'] == 0 and current['waited_peak_rss_bytes'] == 0,
             'Fresh original outer supervisor required')
        argv = fixed_command(request_sha, driver_sha, ENTRY_MONOTONIC)
        attempted = True
        report = supervisor.supervise(argv, LOG, started=ENTRY_MONOTONIC, cwd=PROJECT, **LIMITS)
        exclusive(PROCESS, dict(**base, status='raw_process_receipt_pending_root_acceptance',
            supervision_attempted=attempted, command=argv, supervisor_report=report,
            supervisor_flags_reinterpreted=False))
        receipt_written = True; require_normal_boundary(report)
        need(not PIPELINE_FAILURE.exists() and PIPELINE.exists(), 'Missing or failed mandatory pipeline evidence')
        before = stable_stat(PIPELINE)
        with PIPELINE.open('rb') as handle:
            raw = handle.read(CAP + 1)
        need(len(raw) <= CAP and stable_stat(PIPELINE) == before, 'Bounded stable pipeline evidence')
        evidence = unique_json(raw)
        need(all(evidence.get(k) == v for k,v in base.items()) and
             evidence.get('status') == 'owner_and_independent_parity_returned_pending_root_full_exit_acceptance' and
             evidence.get('owner_returned') is True and type(evidence.get('parity')) is dict,
             'Mandatory owner/parity evidence detached from original episode')
        check_returned_parity(evidence['parity'], request_sha)
        exclusive(DRIVER, dict(**base, status='pending_root_output_and_complete_exit_acceptance',
            process_receipt=str(PROCESS), pipeline_evidence=dict(path=str(PIPELINE), sha256=hashlib.sha256(raw).hexdigest()),
            supervisor_flags_reinterpreted=False))
        return 0
    except BaseException as exc:
        cleanup = getattr(exc, 'supervisor_cleanup_evidence', None)
        if consumed:
            if not receipt_written:
                try:
                    exclusive(PROCESS, dict(**base, status='failed_or_unknown_process_boundary',
                        supervision_attempted=attempted, supervisor_report=report,
                        supervisor_exception_cleanup_evidence=cleanup, supervisor_flags_reinterpreted=False))
                except BaseException as secondary:
                    print('Process receipt persistence unknown: '+str(secondary)[:512], file=sys.stderr)
            try:
                exclusive(ERROR, dict(**base, status='failed_consumed_no_retry',
                    error_type=type(exc).__name__, error=str(exc)[:2048], supervision_attempted=attempted))
            except BaseException as secondary:
                print('Failure receipt persistence unknown: '+str(secondary)[:512], file=sys.stderr)
        print('Whole018 driver failed: '+type(exc).__name__+': '+str(exc)[:2048], file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description='Unissued fixed whole018 driver proposal')
    parser.add_argument('--expected-request-sha', required=True)
    parser.add_argument('--expected-driver-sha', required=True)
    parser.add_argument('--pipeline', action='store_true')
    parser.add_argument('--original-started-monotonic', type=float)
    args = parser.parse_args()
    sha(args.expected_request_sha); sha(args.expected_driver_sha)
    need(args.expected_request_sha == REQUEST_SHA, 'Exact Root-reviewed request candidate SHA required')
    runtime()
    if args.pipeline:
        need(args.original_started_monotonic is not None, 'Original outer clock required by fixed pipeline')
        return pipeline_main(args.expected_request_sha, args.expected_driver_sha, args.original_started_monotonic)
    need(args.original_started_monotonic is None, 'Outer entry owns original lifetime clock')
    return outer_main(args.expected_request_sha, args.expected_driver_sha)


if __name__ == '__main__':
    raise SystemExit(main())
