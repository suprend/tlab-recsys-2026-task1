import time
START = time.monotonic()  # Before all remaining imports; external exit remains Root's responsibility.
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import types

CLONE_LITERAL = Path('/tmp/tlab-public018-clean-20261015-once')
CLONE = CLONE_LITERAL.resolve()
RAW = '/Users/mdpospelov/tlab-recsys-2026/data/raw/2019-Oct.csv.gz'
OUTPUT = CLONE / 'artifacts/reproduction/public-frozen-bw-once'
OUT = Path('/tmp/tlab-public018-v6-20261015-once').resolve()
SPEC = Path('/tmp/tlab-public018-root-issued-spec-20261015-once.json')
V6 = Path('/Users/mdpospelov/tlab-recsys-2026/docs/backlog-reviews/evidence/source-import-tiny-v5/original/supervisor-v6.py')
V6_SHA = '449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
OP = 'public018-clean-20261015-once'
CAP = 1048576


def need(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    need(not path.is_symlink(), 'No metadata/source symlink')
    before = path.stat()
    need(0 < before.st_size <= CAP, 'Small metadata/source only')
    with path.open('rb') as handle:
        raw = handle.read(CAP + 1)
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k) for k in fields), 'Changed small input')
    return raw


def pin(path, digest):
    need(type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'Exact SHA required')
    raw = read(path)
    need(hashlib.sha256(raw).hexdigest() == digest, 'Input SHA differs')
    return raw


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def write(name, body):
    raw = (json.dumps(body, sort_keys=True, allow_nan=False) + '\n').encode()
    need(len(raw) <= CAP, 'Bounded receipt required')
    with (OUT / name).open('xb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def failure(primary, base, attempted, observation):
    try:
        write('failure.json', dict(base, status='failed_consumed_no_retry',
              supervision_attempted=attempted, raw_supervisor_report=observation, error_type=type(primary).__name__,
              error=str(primary)[:2048], supervisor_cleanup_evidence=getattr(primary, 'supervisor_cleanup_evidence', None)))
    except BaseException as secondary:
        try:
            primary.failure_receipt_persistence_error = secondary
            primary.add_note('Failure receipt persistence failed: ' + type(secondary).__name__)
        except BaseException:
            pass  # Never replace the primary or its original V6 cleanup attachment.


def public_path(relative):
    need(type(relative) is str and relative and not Path(relative).is_absolute(), 'Public relative path required')
    parts = Path(relative).parts
    need('..' not in parts and parts[0] not in ('data', 'artifacts', '.git'), 'Public source/config only')
    path = CLONE / relative
    need(path.resolve().is_relative_to(CLONE), 'Public path escaped checkout')
    need(all(not p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(CLONE)), 'No public path aliases')
    return path


def main():
    parser = argparse.ArgumentParser(description='Unissued public018 single-producer V6 transport proposal')
    parser.add_argument('--spec-sha256', required=True)
    parser.add_argument('--driver-sha256', required=True)
    args = parser.parse_args()
    created = attempted = False
    observation = None
    base = dict(operation_id=OP, spec_sha256=args.spec_sha256, driver_sha256=args.driver_sha256,
                started_monotonic=START, scientific_acceptance=False, execution_authority_issued=False)
    try:
        pin(Path(__file__), args.driver_sha256)
        raw = pin(SPEC, args.spec_sha256)
        spec = json.loads(raw, object_pairs_hook=unique)
        keys = {'version', 'approved', 'operation_id', 'driver_sha256', 'checkout_head', 'venv', 'recipe', 'code_refs', 'cli_limits', 'v6_limits'}
        need(type(spec) is dict and set(spec) == keys and type(spec['version']) is int and spec['version'] == 1, 'Exact issued spec schema required')
        need(spec['approved'] is True and spec['operation_id'] == OP and spec['driver_sha256'] == args.driver_sha256, 'Root-issued binding required')
        head = spec['checkout_head']
        need(type(head) is str and len(head) in (40, 64) and all(c in '0123456789abcdef' for c in head), 'Setup HEAD binding required')
        venv = spec['venv']
        need(type(venv) is str and venv not in ('', '.', '..') and Path(venv).name == venv, 'Fresh venv directory binding required')
        python = CLONE / venv / 'bin/python'
        need(CLONE.is_dir() and not CLONE_LITERAL.is_symlink() and python.is_file(), 'Separate clone/setup required')
        need(python.parent.resolve().is_relative_to(CLONE), 'Venv parent escaped checkout')
        need(all(not p.is_symlink() for p in python.parents if p.is_relative_to(CLONE)), 'No venv directory aliases')
        cli, limits = spec['cli_limits'], spec['v6_limits']
        need(type(cli) is dict and set(cli) == {'cpu_seconds', 'wall_seconds', 'rss_bytes', 'spill_bytes'}, 'Exact CLI limits required')
        need(type(limits) is dict and set(limits) == {'cpu_seconds', 'wall_seconds', 'rss_bytes'}, 'Exact V6 limits required')
        need(all(type(v) is int and 0 < v < 2**63 for v in (*cli.values(), *limits.values())), 'Positive finite integer limits required')
        need(5 < limits['cpu_seconds'] and 5 < limits['wall_seconds'] and cli['cpu_seconds'] < limits['cpu_seconds'] and cli['wall_seconds'] < limits['wall_seconds'], 'Whole supervisor margin required')
        need(not OUTPUT.exists() and not OUTPUT.is_symlink() and OUTPUT.parent.is_dir(), 'Exclusive fresh public output required')
        need(all(not p.is_symlink() for p in OUTPUT.parents if p.is_relative_to(CLONE)), 'No output directory aliases')
        OUT.mkdir(mode=0o700); created = True
        write('consumed.json', base)
        refs = spec['code_refs']
        need(type(refs) is dict and 0 < len(refs) <= 64 and 'scripts/reproduce_frozen_comparison.py' in refs and spec['recipe'] in refs, 'Exact reviewed public closure/recipe required')
        witness = {name: hashlib.sha256(pin(public_path(name), digest)).hexdigest() for name, digest in refs.items()}
        recipe = public_path(spec['recipe'])
        write('source-initial.json', dict(base, checkout_head_declared_by_Root_setup=head, code_refs=witness))
        module = types.ModuleType('_tlab_public018_original_v6'); module.__file__ = str(V6)
        sys.modules[module.__name__] = module
        exec(compile(pin(V6, V6_SHA), str(V6), 'exec', dont_inherit=True), module.__dict__)
        argv = [str(python), '-B', '-m', 'scripts.reproduce_frozen_comparison', '--raw', RAW,
                '--output', str(OUTPUT), '--recipe', str(recipe)]
        for flag, key in (('--cpu-seconds', 'cpu_seconds'), ('--wall-seconds', 'wall_seconds'), ('--rss-bytes', 'rss_bytes'), ('--spill-bytes', 'spill_bytes')):
            argv.extend((flag, str(cli[key])))
        attempted = True
        observation = module.supervise(argv, OUT / 'producer.log', started=START, cwd=CLONE, **limits)
        write('process.json', observation)  # Original raw V6 fields and flags, unchanged.
        need(type(observation) is dict and observation.get('status') == 'verified_normal_exit' and observation.get('reaped') is True and type(observation.get('exit_code')) is int and observation['exit_code'] == 0, 'Normal original reap required')
        need(observation.get('unknown_active_work') is False and observation.get('errors') == [] and observation.get('survivors_at_terminal_scan') == [] and observation.get('stop_reason') is None, 'Raw V6 failure/unknown retained')
        need(type(observation.get('observed_process_count')) is int and observation['observed_process_count'] == 1, 'One producer with zero observed descendants required')
        report = OUTPUT / 'report.json'
        need(report.is_file() and not report.is_symlink(), 'Public output report presence required')
        write('transport.json', dict(base, status='pending_Root_output_and_complete_external_exit_review', output_report=str(report), raw_process_receipt=str(OUT / 'process.json')))
        return 0
    except BaseException as primary:
        if created:
            failure(primary, base, attempted, observation)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
