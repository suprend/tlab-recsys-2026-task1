"""Strict, provisional pilot configurations and reproducible run identities.

Validation does not approve an experimental protocol or verify claimed file
hashes. Executors must fingerprint their actual inputs. Artifact paths and
creation time are provenance, and do not change the experiment identity.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from scripts.temporal_contract import label_is_mature, target_window

EVENTS = {'view', 'cart', 'purchase'}


def _keys(value, expected, context):
    if not isinstance(value, dict):
        raise ValueError(f'{context}: expected an object')
    missing, extra = set(expected) - value.keys(), value.keys() - set(expected)
    if missing or extra:
        raise ValueError(f'{context}: missing={sorted(missing)}, unknown={sorted(extra)}')


def _constant(value, expected, context):
    if type(value) is not type(expected) or value != expected:
        raise ValueError(f'{context}: expected {expected!r}')


def _integer(value, context, *, minimum=1, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{context}: integer out of allowed range')


def _utc(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        raise ValueError('Timestamp must be a second-resolution UTC ISO string ending in Z')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def _event_types(value, context):
    if not isinstance(value, list) or not value or any(not isinstance(v, str) or v not in EVENTS for v in value) or len(set(value)) != len(value):
        raise ValueError(f'{context}: expected distinct supported event types')


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f'Non-finite JSON value: {value}')


def _read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def validate_protocol(config):
    _keys(config, {'version', 'status', 'timezone', 'source', 'pilot', 'query', 'target', 'candidates', 'history', 'budget'}, 'protocol')
    _constant(config['version'], 1, 'version')
    _constant(config['status'], 'provisional_pilot', 'status')
    _constant(config['timezone'], 'UTC', 'timezone')
    source, pilot = config['source'], config['pilot']
    for label, bounds in [('source', source), ('pilot', pilot)]:
        _keys(bounds, {'start', 'end'}, label)
    source_start, source_end = _utc(source['start']), _utc(source['end'])
    pilot_start, pilot_end = _utc(pilot['start']), _utc(pilot['end'])
    if not source_start <= pilot_start < pilot_end <= source_end:
        raise ValueError('Pilot bounds must lie within source [start,end)')
    if any(t.time() != datetime.min.time() for t in [pilot_start, pilot_end]):
        raise ValueError('Daily clock pilot bounds must be UTC midnights')

    max_source_hours = int((source_end - source_start).total_seconds() // 3600)
    query = config['query']
    _keys(query, {'kind', 'hour_utc', 'eligibility_hours', 'eligibility_event_types', 'sampling', 'sample_seed', 'max_users_per_day'}, 'query')
    _constant(query['kind'], 'daily_clock', 'query.kind')
    _constant(query['hour_utc'], 0, 'query.hour_utc')
    _constant(query['sampling'], 'sha256_user_day_seed_before_labels', 'query.sampling')
    _integer(query['eligibility_hours'], 'eligibility_hours', maximum=max_source_hours)
    _integer(query['sample_seed'], 'sample_seed', minimum=0)
    _integer(query['max_users_per_day'], 'max_users_per_day', maximum=2000)
    _event_types(query['eligibility_event_types'], 'eligibility_event_types')

    target = config['target']
    _keys(target, {'event_type', 'horizon_hours', 'include_anchor', 'include_end', 'relevance', 'maturity', 'availability_delay_seconds'}, 'target')
    _constant(target['event_type'], 'purchase', 'target.event_type')
    _constant(target['relevance'], 'distinct_binary_products', 'target.relevance')
    _constant(target['maturity'], 'full_horizon', 'target.maturity')
    _integer(target['horizon_hours'], 'horizon_hours', maximum=max_source_hours)
    _integer(target['availability_delay_seconds'], 'availability_delay_seconds', minimum=0)
    if type(target['include_anchor']) is not bool or type(target['include_end']) is not bool:
        raise ValueError('Target endpoint policies must be explicit booleans')
    last_query = pilot_end - timedelta(days=1)
    last_target = target_window(last_query, timedelta(hours=target['horizon_hours']),
                                include_anchor=target['include_anchor'], include_end=target['include_end'])
    if not label_is_mature(last_target, available_before=source_end,
                          availability_delay=timedelta(seconds=target['availability_delay_seconds'])):
        raise ValueError('Pilot includes an immature target horizon')

    candidates = config['candidates']
    _keys(candidates, {'catalog', 'popular_limit', 'popular_window_hours', 'popular_event_type', 'popular_unit', 'recent_limit', 'recent_window_hours', 'recent_event_types', 'max_unique', 'deduplicate'}, 'candidates')
    _constant(candidates['catalog'], 'products_seen_strictly_before_query', 'catalog')
    _constant(candidates['popular_event_type'], 'purchase', 'popular_event_type')
    _constant(candidates['popular_unit'], 'distinct_users', 'popular_unit')
    _constant(candidates['deduplicate'], 'product_id', 'deduplicate')
    candidate_caps = {'popular_limit': 200, 'popular_window_hours': max_source_hours,
                      'recent_limit': 20, 'recent_window_hours': max_source_hours, 'max_unique': 220}
    for key, cap in candidate_caps.items():
        _integer(candidates[key], key, maximum=cap)
    _event_types(candidates['recent_event_types'], 'recent_event_types')
    if candidates['max_unique'] > candidates['popular_limit'] + candidates['recent_limit']:
        raise ValueError('Candidate budget exceeds the two declared source limits')
    required_hours = max(query['eligibility_hours'], candidates['popular_window_hours'], candidates['recent_window_hours'])
    if pilot_start - timedelta(hours=required_hours) < source_start:
        raise ValueError('Pilot starts before its required lookback is observable')

    history = config['history']
    _keys(history, {'duplicates', 'ties', 'metadata'}, 'history')
    _constant(history['duplicates'], 'raw', 'history.duplicates')
    _constant(history['ties'], 'global_read_before_update', 'history.ties')
    _constant(history['metadata'], 'last_strict_past_ambiguity_preserved', 'history.metadata')
    budget = config['budget']
    _keys(budget, {'max_anchors', 'max_candidate_pairs'}, 'budget')
    for key in budget:
        _integer(budget[key], key)
    days = (pilot_end - pilot_start).days
    if budget['max_anchors'] < days * query['max_users_per_day']:
        raise ValueError('Anchor budget is smaller than the declared daily sampling cap')
    if budget['max_candidate_pairs'] < budget['max_anchors'] * candidates['max_unique']:
        raise ValueError('Candidate-pair budget is smaller than the declared upper bound')
    return deepcopy(config)


def load_protocol(path):
    return validate_protocol(_read_json(path))


def write_protocol(config, path):
    Path(path).write_text(canonical_json(validate_protocol(config)) + '\n')


def sha256_file(path):
    """Fingerprint an explicitly requested file without loading it into RAM."""
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _relative_path(value):
    if not isinstance(value, str) or not value or not re.fullmatch(r'[A-Za-z0-9_./-]+', value):
        raise ValueError('Artifact/code/input keys must be project-relative paths')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or value == '.':
        raise ValueError('Path must stay within the project')


def _hashes(value, context):
    if not isinstance(value, dict) or not value:
        raise ValueError(f'{context}: at least one file hash is required')
    for path, digest in value.items():
        _relative_path(path)
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError(f'{context}: expected lowercase SHA-256')


def _components(value, pilot_start):
    if not isinstance(value, list):
        raise ValueError('components must be a list')
    names = set()
    for component in value:
        _keys(component, {'name', 'fit_cutoff', 'available_at', 'refresh_policy'}, 'component')
        name = component['name']
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('Component names must be nonempty and unique')
        names.add(name)
        fit_cutoff, available_at = _utc(component['fit_cutoff']), _utc(component['available_at'])
        if available_at < fit_cutoff:
            raise ValueError('Component available_at precedes its fit data cutoff')
        if available_at > pilot_start:
            raise ValueError('Component available_at is newer than the first pilot query')
        _constant(component['refresh_policy'], 'frozen_parameters_past_history', 'component.refresh_policy')


def build_run_manifest(config, *, code_hashes, input_hashes, components, artifact_refs, created_at):
    protocol = validate_protocol(config)
    _hashes(code_hashes, 'code_hashes')
    _hashes(input_hashes, 'input_hashes')
    if 'uv.lock' not in code_hashes:
        raise ValueError('Code hashes must include uv.lock for dependency provenance')
    _components(components, _utc(protocol['pilot']['start']))
    if not isinstance(artifact_refs, dict):
        raise ValueError('artifact_refs must be an object')
    for label, path in artifact_refs.items():
        if not isinstance(label, str) or not label:
            raise ValueError('Artifact names must be nonempty strings')
        _relative_path(path)
    _utc(created_at)
    identity = deepcopy(dict(version=1, protocol=protocol, code_hashes=code_hashes,
                             input_hashes=input_hashes, components=components))
    run_id = hashlib.sha256(canonical_json(identity).encode()).hexdigest()
    return dict(version=1, run_id=run_id, identity=identity,
                artifact_refs=deepcopy(artifact_refs), created_at=created_at)


def validate_run_manifest(manifest):
    _keys(manifest, {'version', 'run_id', 'identity', 'artifact_refs', 'created_at'}, 'manifest')
    _constant(manifest['version'], 1, 'manifest.version')
    identity = manifest['identity']
    _keys(identity, {'version', 'protocol', 'code_hashes', 'input_hashes', 'components'}, 'identity')
    _constant(identity['version'], 1, 'identity.version')
    rebuilt = build_run_manifest(identity['protocol'], code_hashes=identity['code_hashes'],
                                 input_hashes=identity['input_hashes'], components=identity['components'],
                                 artifact_refs=manifest['artifact_refs'], created_at=manifest['created_at'])
    if manifest['run_id'] != rebuilt['run_id']:
        raise ValueError('Run identity digest does not match its contents')
    return rebuilt


def load_run_manifest(path):
    return validate_run_manifest(_read_json(path))


def write_run_manifest(manifest, path):
    Path(path).write_text(canonical_json(validate_run_manifest(manifest)) + '\n')
