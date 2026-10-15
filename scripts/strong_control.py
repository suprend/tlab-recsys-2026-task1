"""Read-only consumer of the one independently accepted historical 019 control.

This authenticates reviewed receipts; it does not regenerate feature/model proof,
open models or labels, or grant a fit. No planner/environment subprocess is used.
"""
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_SHA256 = 'a7cb383d9a75ac20ebd910fee384cb23eb8e255138df693a100942795e0ef692'
RUN_ID = '9c6969c88857620b24d27da288c6aeb2544187d2cb64267db5e81f8c3599b080'
PRODUCER = 'artifacts/strong-baseline/' + RUN_ID
RECOVERY = 'artifacts/strong-recoveries/0fbf6726e80d49e19353bfd245df056a'
OLD = 'artifacts/strong-invocations/5e78c81130204e8dbd26232144a93867'
PROOFS = (
    'docs/backlog-reviews/tlab019-strong-output-aggregate.json',
    'docs/backlog-reviews/tlab019-strong-output-verification.md',
    'docs/backlog-reviews/tlab019-strong-oracle-accepted-source.md',
)
SELECTED = {'config_id', 'incumbent', 'population', 'trained_iterations', 'depth',
            'l2_leaf_reg', 'model_path', 'score_path', 'scoring_prefix'}
MAX_JSON_BYTES = 8 * 2**20


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _local(name):
    _need(type(name) is str and name and not Path(name).is_absolute()
          and '..' not in Path(name).parts and '\\' not in name, 'Nonlocal control artifact')
    path = (ROOT / name).resolve()
    _need(path.is_relative_to(ROOT.resolve()), 'Control artifact escaped checkout')
    return path


def _sha(path, check):
    h = hashlib.sha256()
    check()
    with path.open('rb') as handle:
        while block := handle.read(4 * 2**20):
            check()
            h.update(block)
    check()
    return h.hexdigest()


def _read(path, check):
    check()
    with path.open('rb') as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    _need(len(raw) <= MAX_JSON_BYTES, 'Control JSON exceeds bounded receipt size')
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, 'Duplicate control JSON key')
            result[key] = value
        return result
    body = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite control JSON')))
    check()
    return body, hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _pins(value):
    _need(type(value) is dict, 'Control fingerprints must be an object')
    for name, digest in value.items():
        _local(name)
        _need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None,
              'Invalid control fingerprint')
    return value


def _merge(target, value):
    for name, digest in _pins(value).items():
        _need(name not in target or target[name] == digest, 'Conflicting control closure')
        target[name] = digest


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _int(value, expected):
    return type(value) is int and value == expected


def _metrics(expected, actual):
    if type(expected) is dict:
        _need(type(actual) is dict and set(expected) == set(actual), 'Winner metric schema differs')
        for key, value in expected.items():
            _metrics(value, actual[key])
    elif type(expected) is float:
        _need(type(actual) is float and math.isfinite(actual)
              and math.isclose(expected, actual, rel_tol=0, abs_tol=1e-12), 'Winner metric differs')
    else:
        _need(type(expected) is type(actual) and expected == actual, 'Winner evidence differs')


def _failure_tail(marker, final):
    allowed = {'actual_parent_cpu_seconds', 'actual_total_cpu_seconds', 'seconds'}
    _need(type(marker) is dict and type(final) is dict and set(marker) == set(final),
          'Original failed receipt schema changed')
    _need(_canonical({k: v for k, v in marker.items() if k not in allowed}) ==
          _canonical({k: v for k, v in final.items() if k not in allowed}),
          'Original failed history changed')
    for key in allowed:
        _need(_number(marker.get(key)) and _number(final.get(key)) and marker[key] <= final[key],
              'Original failed lifetime counter regressed')


def verify_control(path, *, check=lambda: None):
    """Verify exact historical304 closure and return immutable control bindings.

    Streaming every pinned byte can be costly; the caller owns and charges its
    deadline/CPU/RSS through check and outer process supervision. This function
    performs no acceptance writes and has no skip-hash or caller-anchor override.
    """
    path = Path(path).resolve()
    _need(path.is_relative_to(ROOT.resolve()), 'Acceptance outside checkout')
    acceptance, acceptance_sha = _read(path, check)
    _need(acceptance_sha == ACCEPTANCE_SHA256, 'Unreviewed historical control acceptance bytes')
    _need(type(acceptance) is dict and set(acceptance) ==
          {'version', 'approved', 'scope', 'run_id', 'selected_spec', 'fingerprints'},
          'Exact control acceptance schema required')
    _need(_int(acceptance['version'], 1) and acceptance['approved'] is True
          and acceptance['scope'] == 'reviewed_strong_baseline_control'
          and acceptance['run_id'] == RUN_ID, 'Historical control scope differs')
    pins = dict(_pins(acceptance['fingerprints']))
    _need(len(pins) == 304, 'Historical control needs exact304 fingerprints')
    def receipt(name):
        _need(name in pins, 'Missing control receipt pin')
        body, digest = _read(_local(name), check)
        _need(pins[name] == digest, 'Control receipt bytes changed')
        return body
    m = receipt(PRODUCER + '/run.json')
    report = receipt(PRODUCER + '/report.json')
    plan = receipt(PRODUCER + '/plan.json')
    winner = receipt(PRODUCER + '/winner.json')
    owner = receipt(RECOVERY + '/report.json')
    verification = receipt(RECOVERY + '/verification.json')
    context = receipt(RECOVERY + '/verification-context.json')
    external = receipt(RECOVERY + '/external-lifetime.json')
    old = receipt(OLD + '/report.json')
    marker = receipt(OLD + '/report.failed.json')
    old_failed = receipt(OLD + '/verification.failed.json')
    aggregate = receipt(PROOFS[0])
    for directory in (PRODUCER, RECOVERY):
        _need(not _local(directory + '/report.failed.json').exists(), 'Known failed accepted control')
    _need(not _local(RECOVERY + '/verification.failed.json').exists(), 'Known failed accepted observer')
    _need(all(body['run_id'] == RUN_ID for body in (m, report, owner, verification, external, aggregate)),
          'Control run identity differs')
    identity = m['identity']
    _need(hashlib.sha256(_canonical(identity).encode()).hexdigest() == RUN_ID,
          'Producer identity digest differs')
    _need(report['status'] == 'complete_produced_unreviewed' and _int(report['fit_attempt_count'], 4)
          and _int(report['actual_seen_looks'], 12) and report['unknown_live_fit'] is False,
          'Original four-fit producer incomplete')
    _need(owner['status'] == 'recovery_verified_pending_external_acceptance'
          and _int(owner['producer_calls'], 0) and _int(owner['verifier_calls'], 1)
          and _int(owner['fit_attempt_count'], 0) and owner['labels_reserved_opened'] is False,
          'Successful zero-fit recovery required')
    _need(verification['status'] == 'verified' and _int(verification['fit_attempt_count'], 0)
          and verification['reaped_children_cpu_seconds'] == 0
          and type(verification['reaped_children_cpu_seconds']) in (int, float), 'Observer incomplete/unknown children')
    evidence = verification['evidence']
    _need(evidence['status'] == 'verified' and _int(evidence['observer_refits'], 0)
          and _int(evidence['saved_prefixes_replayed'], 12) and _int(evidence['successful_new_arms'], 4)
          and _int(evidence['allocated_new_arms'], 4) and evidence['all_four_estimands_recomputed'] is True
          and evidence['full300_prefix_equivalence'] is True, 'Independent output proof incomplete')
    _need(aggregate['status'] == 'accepted_development_control' and aggregate['actual_new_recovery_fits'] == 0,
          'External aggregate proof scope differs')
    _failure_tail(marker, old)
    _need(old['status'] == 'failed' and old_failed['status'] == 'failed'
          and old_failed['run_id'] == RUN_ID and _int(old_failed['fit_attempt_count'], 0),
          'Original failed history not preserved')
    for key in ('run_id', 'identity', 'execution_approval', 'budget_claim'):
        _need(_canonical(plan[key]) == _canonical(m[key]), 'Original plan/manifest differs')
    _need(_canonical(winner) == _canonical(report['winner']), 'Winner file/report differs')
    selected = dict(winner)
    selected = {key: selected[key] for key in SELECTED if key != 'scoring_prefix'}
    selected['scoring_prefix'] = winner['trees']
    _need(type(acceptance['selected_spec']) is dict and set(acceptance['selected_spec']) == SELECTED
          and _canonical(selected) == _canonical(acceptance['selected_spec']), 'Selected procedure differs')
    _need(type(winner['incumbent']) is bool and type(winner['population']) is int
          and winner['population'] in (6000, 26000) and type(winner['trained_iterations']) is int
          and type(winner['trees']) is int and 1 <= winner['trees'] <= winner['trained_iterations'],
          'Invalid frozen population/iteration/prefix')
    for key in ('config_id', 'incumbent', 'population', 'trained_iterations', 'trees', 'depth', 'l2_leaf_reg'):
        _metrics(winner[key], evidence['winner'][key])
    _metrics(winner['metrics'], evidence['winner']['metrics'])
    names = identity['feature_names']
    _need(type(names) is list and len(names) == len(set(names)) == 41
          and all(type(name) is str for name in names) and names == report['feature_names'], 'Frozen B41 differs')
    if winner['incumbent']:
        params = identity['incumbent']['actual_model_parameters']
    else:
        chosen = []
        for child in report['children']:
            body = child['report']
            for cp in body.get('checkpoints', []):
                if cp['model_path'] == winner['model_path'] and cp['score_path'] == winner['score_path']:
                    _need(child['exit_code'] == 0 and type(child['exit_code']) is int
                          and body['status'] == 'complete_produced_unreviewed'
                          and body['outcome'] == 'arm_complete' and body['feature_names'] == names,
                          'Chosen child is not eligible')
                    _need(_canonical({k: v for k, v in cp.items() if k != 'comparison'}) == _canonical(winner),
                          'Chosen checkpoint differs from winner')
                    chosen.append(body['actual_model_parameters'])
        _need(len(chosen) == 1, 'Exactly one chosen original child required')
        params = chosen[0]
    _need(type(params) is dict and params['loss_function'] == 'Logloss'
          and _int(params['iterations'], winner['trained_iterations'])
          and params['depth'] == winner['depth'] and params['l2_leaf_reg'] == winner['l2_leaf_reg'],
          'Chosen raw native parameters differ')
    refs = identity['acceptance_refs']
    _need(type(refs) is dict and set(refs) == {'train', 'selection', 'ablation'}
          and all(type(name) is str and name in pins for name in refs.values()), 'Input acceptance references differ')
    # Rebuild the published closure; right count alone cannot authenticate scope.
    expected = {}
    _need(len(identity['fingerprints']) == 206 and len(m['outputs']) == 69, 'Original closure dimensions differ')
    for mapping in (identity['fingerprints'], m['outputs'], owner['final_source_pins']):
        _merge(expected, mapping)
    extra = [PRODUCER + '/' + n for n in ('run.json', 'report.json', 'plan.json', 'winner.json')]
    extra += [m['budget_claim']['path'], m['execution_approval']['path']]
    extra += [RECOVERY + '/' + n for n in ('report.json', 'verification.json', 'verification.log',
                                         'external-lifetime.log', 'external-lifetime.json')]
    extra += list(PROOFS)
    for name in extra:
        _need(name in pins, 'Missing exact external proof output')
        _merge(expected, {name: pins[name]})
    _need(expected == pins, 'Historical control exact closure differs')
    _need(owner['verification_sha256'] == pins[RECOVERY + '/verification.json']
          and verification['context_sha256'] == pins[RECOVERY + '/verification-context.json']
          and verification['request_sha256'] == pins[RECOVERY + '/verification-request.json']
          and verification['producer_manifest'] == dict(path=PRODUCER + '/run.json', sha256=pins[PRODUCER + '/run.json'])
          and verification['producer_report'] == dict(path=PRODUCER + '/report.json', sha256=pins[PRODUCER + '/report.json'])
          and verification['allocation'] == context['allocation'], 'Recovery receipt/context binding differs')
    _need(external['status'] == 'verified_full_lifetime' and _int(external['version'], 1)
          and _int(external['exit_code'], 0), 'Successful external lifetime receipt required')
    for key, name in (('owner_report', 'report.json'), ('verification', 'verification.json')):
        _need(external[key] == dict(path=RECOVERY + '/' + name, sha256=pins[RECOVERY + '/' + name]),
              'External lifetime detached from receipts')
    _need(all(_number(external[k]) for k in ('actual_cpu_seconds', 'wall_seconds',
          'conservative_study_actual_cpu_seconds', 'cumulative_original_verification_cpu_seconds'))
          and external['actual_cpu_seconds'] >= owner['actual_new_total_cpu_seconds']
          and external['conservative_study_actual_cpu_seconds'] <= 3600
          and external['cumulative_original_verification_cpu_seconds'] <= 300
          and owner['finished_monotonic'] <= external['original_absolute_deadline_monotonic']
          and verification['finished_monotonic'] <= context['allocation']['deadline_monotonic'],
          'External lifetime violates original cost/clock')
    _need(type(external['process_peak_rss_bytes']) is int and external['process_peak_rss_bytes'] > 0
          and external['process_peak_rss_bytes'] + owner['parent_peak_rss_bytes'] <= 8 * 2**30,
          'External conservative job RSS differs')
    for name, digest in pins.items():
        _need(_sha(_local(name), check) == digest, 'Pinned accepted control input/output changed')
    # A late marker/context/acceptance change must not yield a successful return.
    for name in (PRODUCER + '/report.failed.json', RECOVERY + '/report.failed.json',
                 RECOVERY + '/verification.failed.json'):
        _need(not _local(name).exists(), 'Late failed accepted control')
    _need(_sha(path, check) == acceptance_sha, 'Acceptance changed during verification')
    check()
    return dict(manifest=m, report=report, winner=winner, selected_spec=selected,
                actual_model_parameters=params, feature_names=names, acceptance_refs=refs,
                pins=pins, acceptance=dict(path=str(path.relative_to(ROOT.resolve())), sha256=acceptance_sha),
                external_lifetime=external, proof_limits=evidence['proof_limits'])
