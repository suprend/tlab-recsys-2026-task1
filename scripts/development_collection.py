"""Additive development phases composed of unchanged <=3-day v1 protocols.

A phase is not one oversized pilot. Training checkpoint timing is an output
plan; selection/confirmation timing describes an already available input model.
This module validates plans and outer manifests; it never opens final holdout.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path

from scripts.protocol_manifest import _read_json, _relative_path, _utc as utc, canonical_json, validate_protocol
from scripts.temporal_contract import label_is_mature, target_window

ROLES = {'train', 'selection', 'confirmation'}


def _keys(value, expected, label):
    if not isinstance(value, dict) or value.keys() != set(expected):
        raise ValueError(label + ': unknown or missing fields')


def _midnight(value):
    result = utc(value)
    if result.hour or result.minute or result.second:
        raise ValueError('Phase boundaries must be UTC midnights')
    return result


def validate_phase(phase, base_protocol):
    base_protocol = validate_protocol(base_protocol)
    _keys(phase, {'version', 'name', 'role', 'base_protocol', 'feature_registry', 'range',
                  'label_available_before', 'model_timing', 'final_holdout_start',
                  'shard_days', 'lock_required', 'budget'}, 'phase')
    if type(phase['version']) is not int or phase['version'] != 1:
        raise ValueError('Unsupported phase version')
    if not isinstance(phase['name'], str) or not phase['name']:
        raise ValueError('Phase needs a name')
    if not isinstance(phase['role'], str) or phase['role'] not in ROLES:
        raise ValueError('Only development roles are supported, not final test')
    for name in ['base_protocol', 'feature_registry']:
        _relative_path(phase[name])
    _keys(phase['range'], {'start', 'end'}, 'range')
    start, end = _midnight(phase['range']['start']), _midnight(phase['range']['end'])
    source_start, source_end = utc(base_protocol['source']['start']), utc(base_protocol['source']['end'])
    final_start = _midnight(phase['final_holdout_start'])
    available = _midnight(phase['label_available_before'])
    if not source_start <= start < end <= final_start <= source_end:
        raise ValueError('Development range overlaps final holdout or lies outside source')
    if not end <= available <= final_start:
        raise ValueError('Label availability must finish before reserved final holdout')
    if type(phase['shard_days']) is not int or not 1 <= phase['shard_days'] <= 3:
        raise ValueError('Each unchanged v1 shard is limited to1–3days')
    _keys(phase['model_timing'], {'fit_data_cutoff', 'available_at'}, 'model_timing')
    fit, ready = utc(phase['model_timing']['fit_data_cutoff']), utc(phase['model_timing']['available_at'])
    if fit > ready:
        raise ValueError('Model cannot be available before fit data cutoff')
    if phase['role'] == 'train':
        if available != fit or ready <= fit:
            raise ValueError('Train output model requires label cutoff agreement and a positive availability gap')
    elif ready > start:
        raise ValueError('Input checkpoint is unavailable at the first evaluation query')
    if type(phase['lock_required']) is not bool or phase['lock_required'] != (phase['role'] == 'confirmation'):
        raise ValueError('Only confirmation is locked, and confirmation cannot be unlocked')
    _keys(phase['budget'], {'max_queries', 'max_candidate_pairs', 'wall_seconds'}, 'budget')
    days = (end - start).days
    queries = days * base_protocol['query']['max_users_per_day']
    pairs = queries * base_protocol['candidates']['max_unique']
    for name, expected in [('max_queries', queries), ('max_candidate_pairs', pairs)]:
        if type(phase['budget'][name]) is not int or phase['budget'][name] != expected:
            raise ValueError('Outer phase budget must match declared daily caps: ' + name)
    if type(phase['budget']['wall_seconds']) is not int or not 1 <= phase['budget']['wall_seconds'] <= 3600:
        raise ValueError('Phase wall budget must be1–3600seconds')
    target = base_protocol['target']
    last = target_window(end - timedelta(days=1), timedelta(hours=target['horizon_hours']),
                         include_anchor=target['include_anchor'], include_end=target['include_end'])
    if not label_is_mature(last, available_before=available,
                          availability_delay=timedelta(seconds=target['availability_delay_seconds'])):
        raise ValueError('Last phase label has not matured by declared availability')
    return deepcopy(phase)


def shard_protocols(phase, base_protocol):
    """Contiguous exact cover; every resulting protocol passes the v1 validator."""
    phase = validate_phase(phase, base_protocol)
    start, end = utc(phase['range']['start']), utc(phase['range']['end'])
    result = []
    while start < end:
        stop = min(end, start + timedelta(days=phase['shard_days']))
        shard = deepcopy(base_protocol)
        shard['pilot'] = {'start': start.strftime('%Y-%m-%dT%H:%M:%SZ'), 'end': stop.strftime('%Y-%m-%dT%H:%M:%SZ')}
        count = (stop - start).days * shard['query']['max_users_per_day']
        shard['budget'] = {'max_anchors': count, 'max_candidate_pairs': count * shard['candidates']['max_unique']}
        result.append(validate_protocol(shard))
        start = stop
    if sum(s['budget']['max_anchors'] for s in result) != phase['budget']['max_queries']:
        raise AssertionError('Shard cover does not reconcile with outer cap')
    return result


def validate_phase_set(phases, base_protocol):
    if not isinstance(phases, list) or len(phases) != 3:
        raise ValueError('Expected one train, selection and confirmation phase')
    roles = {}
    for p in phases:
        value = validate_phase(p, base_protocol)
        if value['role'] in roles:
            raise ValueError('Duplicate phase role')
        roles[value['role']] = value
    if set(roles) != ROLES:
        raise ValueError('Incomplete phase roles')
    train, selection, confirmation = [roles[k] for k in ['train', 'selection', 'confirmation']]
    for key in ['base_protocol', 'feature_registry', 'model_timing', 'final_holdout_start']:
        if not train[key] == selection[key] == confirmation[key]:
            raise ValueError('Phase semantics disagree: ' + key)
    if utc(train['label_available_before']) > utc(selection['range']['start']):
        raise ValueError('Train labels overlap model selection')
    if utc(selection['range']['end']) > utc(confirmation['range']['start']):
        raise ValueError('Selection overlaps confirmation')
    if utc(selection['label_available_before']) > utc(confirmation['range']['start']):
        raise ValueError('Selection labels are unavailable before confirmation')
    return roles


def authorize_phase_execution(phase, base_protocol, lock=None):
    """A lock freezes the strong control and selected branch, before confirmation.

    Schema validation alone does not approve or verify real model artifacts.
    Executors must verify actual fingerprints against the accepted lock.
    """
    phase = validate_phase(phase, base_protocol)
    if not phase['lock_required']:
        if lock is not None:
            raise ValueError('Development selection cannot masquerade as locked confirmation')
        return
    _keys(lock, {'version', 'approved', 'frozen_before', 'strong_baseline_sha256', 'selected_branch_sha256'}, 'lock')
    if type(lock['version']) is not int or lock['version'] != 1 or lock['approved'] is not True:
        raise ValueError('Explicit reviewed confirmation lock required')
    if utc(lock['frozen_before']) < utc(phase['model_timing']['available_at']):
        raise ValueError('Lock predates checkpoint availability')
    if utc(lock['frozen_before']) > utc(phase['range']['start']):
        raise ValueError('Lock was frozen after first confirmation query')
    for key in ['strong_baseline_sha256', 'selected_branch_sha256']:
        value = lock[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Lock needs actual strong control and selected branch SHA-256')


def load_phase(path, base_protocol):
    return validate_phase(_read_json(path), base_protocol)


def build_collection_plan(phase, base_protocol, *, registry_sha256, source_sha256, code_hashes):
    """Outer planned identity contains shard configs, never fake measured counts."""
    phase = validate_phase(phase, base_protocol)
    from scripts.protocol_manifest import _hashes
    _hashes({'registry': registry_sha256, 'source': source_sha256}, 'phase_inputs')
    _hashes(code_hashes, 'code_hashes')
    if not {'uv.lock', 'scripts/development_collection.py'} <= code_hashes.keys():
        raise ValueError('Collection plan needs dependency lock and collection module fingerprints')
    identity = dict(version=1, status='planned_not_executed', phase=phase,
                    shard_protocols=shard_protocols(phase, base_protocol),
                    registry_sha256=registry_sha256, source_sha256=source_sha256, code_hashes=deepcopy(code_hashes))
    return dict(collection_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(), identity=identity)
