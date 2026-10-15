"""Read-only consumer of a separately accepted source recovery.

The original producer remains failed. This verifies sealed exhaustive source
proof and its exact lineage; it never regenerates features or opens label rows.
Streaming pinned inputs is paid work owned by the caller's resource guard.
"""
import hashlib
import json
import math
from pathlib import Path
from scripts import feature_program_collection as source
from scripts import feature_program_source_recovery as admission
from scripts import run_feature_source_recovery as owner_rules
from scripts import strong_control as receipts

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = 'b8c3d08179a922d106e0e5e72e5a11d8eae27a1ab78a4f902a2b023a5c4131d6'
ACCEPTANCE_SHA256 = '5d6741bf5156b19b3076b999d4bded20fe561a6ef0f6a6338e6799263438b42f'
SCOPE = 'reviewed_recovered_selected_feature_program_source'
POLICY = 'artifacts/acceptance/tlab016-source-recovery.json'
POLICY_SHA256 = '1fa44af94e5b73ea0e5282b4b7de0dafb44faee554dc28e0a09e0cba05884a07'
PROOFS = (
    'docs/backlog-reviews/tlab016-recovered-source-aggregate.json',
    'docs/backlog-reviews/tlab016-recovered-source-verification.md',
    'docs/backlog-reviews/tlab016-recovered-source-oracle.md',
)


def need(value, message):
    if not value:
        raise ValueError(message)


def local(name):
    need(type(name) is str and name and not Path(name).is_absolute()
         and '..' not in Path(name).parts and '\\' not in name, 'Nonlocal source artifact')
    result = (ROOT / name).resolve()
    need(result.is_relative_to(ROOT.resolve()), 'Source artifact escapes project')
    return result


def read(path, check):
    # One bounded byte snapshot is both parsed and hashed.
    return receipts._read(Path(path), check)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def merge(target, mapping):
    need(type(mapping) is dict, 'Source fingerprints must be an object')
    for name, digest in mapping.items():
        local(name)
        need(type(digest) is str and len(digest) == 64
             and all(c in '0123456789abcdef' for c in digest), 'Malformed source digest')
        need(name not in target or target[name] == digest, 'Conflicting source closure')
        target[name] = digest


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def verify_source_acceptance(path, *, check=lambda: None):
    """Return accepted daily F57 bindings and conservative paid source prefix.

    No cache/skip-hash mode or writer is supplied. All original107 input pins and
    immutable export bytes are verified; this does not recalculate source values
    or repeat the failed whole-phase F57 materialization. Models consume only
    each selected arm's exact three-column delta over the unchanged B41.
    """
    path = Path(path).resolve()
    need(path.is_relative_to(ROOT.resolve()), 'Source acceptance outside project')
    acceptance, acceptance_sha = read(path, check)
    need(acceptance_sha == ACCEPTANCE_SHA256, 'Unreviewed recovered-source acceptance bytes')
    need(type(acceptance) is dict and set(acceptance) ==
         {'version', 'approved', 'scope', 'run_id', 'fingerprints', 'source_proof'},
         'Exact recovered-source acceptance schema required')
    need(type(acceptance['version']) is int and acceptance['version'] == 1
         and acceptance['approved'] is True and acceptance['scope'] == SCOPE
         and acceptance['run_id'] == RUN_ID, 'Wrong recovered-source authority')
    pins = {}; merge(pins, acceptance['fingerprints'])
    def ref(name):
        need(name in pins, 'Missing source authority pin')
        return dict(path=name, sha256=pins[name])
    def receipt(name):
        body, digest = read(local(name), check)
        need(ref(name)['sha256'] == digest, 'Changed source receipt bytes')
        return body
    proof = acceptance['source_proof']
    need(type(proof) is dict and set(proof) ==
         {'oracle_source', 'aggregate_evidence', 'parent_completion_receipt', 'recovery_policy'},
         'Exact external source proof references required')
    need(proof['recovery_policy'] == dict(path=POLICY, sha256=POLICY_SHA256), 'Wrong issued recovery policy')
    for value in proof.values():
        need(type(value) is dict and set(value) == {'path', 'sha256'}
             and value == ref(value['path']), 'Source proof not bound to exact closure')
    policy = receipt(POLICY)
    manifest = receipt(policy['producer_manifest']['path'])
    report = receipt(policy['producer_report']['path'])
    prefix = receipt(policy['failed_lifetime_receipt']['path'])
    boundary = admission.validate_policy(policy, manifest, report, prefix)
    declared = admission.validate_failed_source(manifest, report, prefix)
    need(declared['run_id'] == RUN_ID, 'Wrong failed historical producer')
    claim = receipt('artifacts/feature-program-study/independent-oracle.claim.json')
    directory = claim['invocation_directory']
    need(type(directory) is str and directory.startswith('artifacts/feature-program-source-oracle/')
         and len(Path(directory).parts) == 3, 'Wrong recovery namespace')
    owner = receipt(directory + '/report.json')
    context = receipt(directory + '/context.json')
    request = receipt(directory + '/request.json')
    launch = receipt(directory + '/launch.json')
    evidence = receipt(directory + '/evidence.json')
    external = receipt(directory + '/external-lifetime.json')
    aggregate = receipt(PROOFS[0])
    need(proof['parent_completion_receipt'] == ref(directory + '/external-lifetime.json')
         and proof['aggregate_evidence'] == ref(PROOFS[0])
         and proof['oracle_source'] == policy['oracle_source'], 'Wrong source proof scope')
    failed = [directory + '/' + name for name in
              ('report.failed.json', 'evidence.failed.json', 'oracle.log.cleanup-failed.json')]
    for name in failed:
        need(not local(name).exists(), 'Known failed source oracle')
    need(type(owner['version']) is int and owner['version'] == 1
         and owner['status'] == 'recovered_source_verified_pending_external_acceptance'
         and owner['run_id'] == RUN_ID and owner['producer_calls'] == 0
         and type(owner['producer_calls']) is int and owner['source_calculations'] == 0
         and type(owner['source_calculations']) is int and owner['oracle_calls'] == 1 and type(owner['oracle_calls']) is int
         and owner['fit_attempt_count'] == 0 and type(owner['fit_attempt_count']) is int
         and owner['labels_loaded'] is False, 'Source recovery did not complete without regeneration')
    expected_claim = dict(version=1, scope='once_only_selected12_source_oracle', run_id=RUN_ID,
                          allowed_observer_attempts=1, allowed_source_calculations=0,
                          allowed_fit_attempts=0, policy=ref(POLICY), invocation_directory=directory)
    need(canonical(claim) == canonical(expected_claim), 'Unused-oracle claim differs')
    need(context['request'] == ref(directory + '/request.json')
         and context['oracle_execution_approval'] == ref(POLICY)
         and context['recovery_policy'] == ref(POLICY)
         and owner['policy'] == ref(POLICY) and launch['policy'] == ref(POLICY)
         and owner['evidence'] == ref(directory + '/evidence.json')
         and launch['claim'] == ref('artifacts/feature-program-study/independent-oracle.claim.json'),
         'Recovery authority/context differs')
    need(request == dict(scope=admission.ORACLE_SCOPE, run_id=RUN_ID,
                         producer_manifest=policy['producer_manifest'], producer_report=policy['producer_report'],
                         oracle_source=policy['oracle_source'], shared_budget=context['shared_budget'],
                         recovery_policy=ref(POLICY)), 'Recovery request differs')
    need(owner['oracle_launch'] == dict(argv=launch['argv'],
         issued_context_sha256=ref(directory + '/context.json')['sha256'], allocation=context['allocation'])
         and launch['issued_context_sha256'] == ref(directory + '/context.json')['sha256']
         and launch['allocation'] == context['allocation'] and owner['launch'] == launch,
         'Issuer launch evidence differs')
    owner_rules.validate_evidence(evidence, context, ref(directory + '/context.json')['sha256'],
                                 declared, owner['actual_reaped_oracle_cpu_seconds'], oracle_claim=launch['claim'])
    need(external['version'] == 1 and type(external['version']) is int
         and external['status'] == 'verified_full_lifetime' and external['exit_code'] == 0
         and type(external['exit_code']) is int and external['run_id'] == RUN_ID,
         'Successful external source lifetime required')
    need(external['owner_report'] == ref(directory + '/report.json')
         and external['evidence'] == ref(directory + '/evidence.json')
         and external['policy'] == ref(POLICY), 'External source lifetime detached')
    for name in ('actual_cpu_seconds', 'wall_seconds', 'charged_source_oracle_cpu_seconds',
                 'active_computation_wall_seconds'):
        need(number(external[name]), 'Unknown full source lifetime')
    need(owner['actual_new_total_cpu_seconds'] <= external['actual_cpu_seconds'] <= boundary['owner_and_oracle_cpu_seconds']
         and owner['seconds'] <= external['wall_seconds'] <= boundary['owner_and_oracle_wall_seconds']
         and external['charged_source_oracle_cpu_seconds'] == boundary['old_source_cpu_upper_seconds'] + external['actual_cpu_seconds']
         and external['charged_source_oracle_cpu_seconds'] <= 900
         and external['active_computation_wall_seconds'] == boundary['old_source_active_wall_seconds'] + external['wall_seconds']
         and external['active_computation_wall_seconds'] <= 1200
         and external['original_absolute_deadline'] == 'unavailable_not_reconstructed',
         'Source budget reset or missing full exit tail')
    need(type(external['process_peak_rss_bytes']) is int and 0 < external['process_peak_rss_bytes'] <= 7 * 2**30
         and external['process_peak_rss_bytes'] + owner['parent_peak_rss_bytes'] <= 8 * 2**30,
         'Unknown or excessive source job RSS')
    need(aggregate['status'] == 'accepted_recovered_source' and aggregate['run_id'] == RUN_ID
         and aggregate['checked_pairs'] == declared['pairs'] and aggregate['checked_scalar_values'] == declared['pairs'] * 12
         and aggregate['original_producer_status'] == 'failed' and aggregate['producer_regenerated'] is False,
         'External aggregate source scope differs')
    expected = {}
    for mapping in (manifest['identity']['fingerprints'], declared['outputs'], owner['final_source_pins']):
        merge(expected, mapping)
    extra = [policy['producer_manifest']['path'], policy['producer_report']['path'], manifest['execution_approval']['path']]
    extra += [directory + '/' + name for name in ('report.json', 'evidence.json', 'oracle.log', 'external-lifetime.json', 'external-lifetime.log')]
    extra += list(PROOFS)
    for name in extra:
        merge(expected, {name: ref(name)['sha256']})
    need(expected == pins, 'Exact recovered-source proof closure differs')
    need(hashlib.sha256(canonical(manifest['identity']).encode()).hexdigest() == RUN_ID,
         'Original source identity digest differs')
    refs = manifest['identity']['acceptance_refs']
    plan, collections = source.prepare_plan(*(local(refs[name]) for name in
                         ('train', 'selection', 'contract', 'base_registry')), check=check)
    need(plan['run_id'] == RUN_ID and canonical(plan['identity']) == canonical(manifest['identity']),
         'Actual source plan/collection lineage differs')
    for name, digest in pins.items():
        need(receipts._sha(local(name), check) == digest, 'Accepted source input/output changed')
    for name in failed:
        need(not local(name).exists(), 'Late failed source oracle')
    need(receipts._sha(path, check) == acceptance_sha, 'Source acceptance changed during verification')
    check()
    return dict(manifest=manifest, report=report, collections=collections, pins=pins,
                pool=manifest['identity']['pool'], allocation=manifest['identity']['allocation'],
                selected_union=manifest['identity']['selected_union'],
                daily_features={role: [part['artifacts']['features']['path'] for part in parts]
                                for role, parts in manifest['outputs'].items()},
                paid_source_cpu_seconds=external['charged_source_oracle_cpu_seconds'],
                source_proof=proof, physical=dict(status='independently_verified_all_rows', source_formula_acceptance=True),
                acceptance=dict(path=path.relative_to(ROOT.resolve()).as_posix(), sha256=acceptance_sha))
