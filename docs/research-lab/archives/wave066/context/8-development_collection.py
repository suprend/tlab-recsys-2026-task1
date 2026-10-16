"""Additive development phases composed of unchanged <=3-day v1 protocols.

A phase is not one oversized pilot. Training checkpoint timing is an output
plan; selection/confirmation timing describes an already available input model.
Execution is gated by external producer and per-shard approvals. Produced
features still need independent collection acceptance before model training.
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


# Execution composes accepted v1 producers; it does not relax their contracts.
ROOT = Path(__file__).resolve().parents[1]
PRODUCER_CODE = ('uv.lock', 'scripts/temporal_contract.py', 'scripts/protocol_manifest.py',
                 'scripts/anchor_pilot.py', 'scripts/candidate_pilot.py', 'scripts/ranking_metrics.py',
                 'scripts/heuristic_baselines.py', 'scripts/manual_features.py', 'scripts/development_collection.py')
ANCHOR_CODE = {'uv.lock', 'scripts/anchor_pilot.py', 'scripts/temporal_contract.py', 'scripts/protocol_manifest.py'}
CANDIDATE_CODE = ANCHOR_CODE | {'scripts/candidate_pilot.py'}
FEATURE_CODE = set(PRODUCER_CODE) - {'scripts/development_collection.py'}


def _path(name):
    _relative_path(name)
    path = (ROOT / name).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _name(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def _digest(path, check=lambda: None):
    from scripts.protocol_manifest import sha256_file
    check()
    value = sha256_file(path)
    check()
    return value


def _atomic_json(path, value):
    import uuid
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(canonical_json(value) + '\n')
    temp.replace(path)


def prepare_execution_plan(phase_path, db_path, *, check=lambda: None):
    """Read actual files; returned hashes are proposals, never approvals."""
    from scripts.protocol_manifest import load_protocol
    phase_path, db_path = Path(phase_path).resolve(), Path(db_path).resolve()
    raw = _read_json(phase_path)
    base = load_protocol(_path(raw['base_protocol']))
    phase = validate_phase(raw, base)
    if phase['role'] == 'confirmation':
        raise ValueError('Confirmation runtime awaits actual selected-model and decision acceptance')
    authorize_phase_execution(phase, base)
    names = set(PRODUCER_CODE) | {_name(phase_path), _name(db_path), phase['base_protocol'],
                                  phase['feature_registry'], 'pyproject.toml'}
    pins = {name: _digest(_path(name), check) for name in sorted(names)}
    plan = build_collection_plan(phase, base, registry_sha256=pins[phase['feature_registry']],
                                 source_sha256=pins[_name(db_path)],
                                 code_hashes={name: pins[name] for name in PRODUCER_CODE})
    plan['execution_inputs'] = dict(phase_path=_name(phase_path), source_path=_name(db_path), fingerprints=pins)
    return plan


def verify_producer_approval(plan, approval):
    """Approval must come from the coordinator's code/plan review."""
    _keys(approval, {'version', 'approved', 'scope', 'collection_id', 'fingerprints'}, 'producer approval')
    if type(approval['version']) is not int or approval['version'] != 1 or approval['approved'] is not True:
        raise ValueError('Explicit reviewed producer approval required')
    if approval['scope'] != 'reviewed_producers_and_phase_plan':
        raise ValueError('Producer approval cannot masquerade as output acceptance')
    if approval['collection_id'] != plan['collection_id'] or approval['fingerprints'] != plan['execution_inputs']['fingerprints']:
        raise ValueError('Accepted producer, source, config or dependency fingerprint changed')


def _verify_run(directory, *, protocol, kind, plan, check):
    """Check identity, every declared dependency, and complete physical outputs.

    This is mechanical integrity, not independent semantic acceptance of Q/Y/C/F.
    """
    from scripts.protocol_manifest import load_run_manifest
    directory = Path(directory).resolve()
    directory.relative_to(ROOT.resolve() / 'artifacts')
    manifest = load_run_manifest(directory / 'run.json')
    report = _read_json(directory / 'report.json')
    if report.get('status') != 'complete' or report.get('run_id') != manifest['run_id']:
        raise ValueError('Incomplete producer output: ' + kind)
    if manifest['identity']['protocol'] != protocol or report.get('protocol', protocol) != protocol:
        raise ValueError('Producer protocol differs from exact planned shard')
    required = {'anchor': ANCHOR_CODE, 'candidate': CANDIDATE_CODE, 'features': FEATURE_CODE}[kind]
    code = manifest['identity']['code_hashes']
    if code.keys() != required:
        raise ValueError('Unexpected producer code lineage: ' + kind)
    for name, digest in code.items():
        if digest != plan['identity']['code_hashes'][name]:
            raise ValueError('Producer code differs from accepted plan: ' + name)
    inputs = manifest['identity']['input_hashes']
    source = plan['execution_inputs']['source_path']
    if inputs.get(source) != plan['identity']['source_sha256']:
        raise ValueError('Producer source lineage mismatch')
    if kind == 'anchor' and set(inputs) != {source}:
        raise ValueError('Anchor must derive independent Q/Y only from source')
    for group in (code, inputs):
        for name, digest in group.items():
            if _digest(_path(name), check) != digest:
                raise ValueError('Producer dependency changed: ' + name)
    output_names = {'anchor': {'queries', 'labels', 'report'},
                    'candidate': {'candidates', 'query_coverage', 'report'},
                    'features': {'features', 'report'}}[kind]
    if manifest['artifact_refs'].keys() != output_names:
        raise ValueError('Missing or unexpected producer output references')
    files = [directory / 'run.json', directory / 'report.json']
    for label, name in manifest['artifact_refs'].items():
        path = _path(name)
        if path.parent != directory or (label == 'report' and path != directory / 'report.json'):
            raise ValueError('Output reference escapes its immutable producer run')
        files.append(path)
    seal = dict(directory=_name(directory), run_id=manifest['run_id'],
                fingerprints={_name(p): _digest(p, check) for p in sorted(set(files))})
    if kind == 'features':
        if report.get('selection', {}).get('max_queries', 'absent') is not None:
            raise ValueError('Collection requires full candidate features, not a diagnostic subset')
        registry = plan['identity']['phase']['feature_registry']
        if inputs.get(registry) != plan['identity']['registry_sha256']:
            raise ValueError('Feature registry lineage mismatch')
        if report.get('output_sha256') != seal['fingerprints'][manifest['artifact_refs']['features']]:
            raise ValueError('Feature output hash differs from producer report')
    return manifest, report, seal


def _check_cached(entry, protocol, kind, plan, check):
    manifest, report, actual = _verify_run(_path(entry['directory']), protocol=protocol, kind=kind, plan=plan, check=check)
    if actual != entry:
        raise ValueError('Cached output changed since original production seal: ' + kind)
    return manifest, report


def _verify_candidate_lineage(anchor_manifest, candidate_manifest, candidate_report):
    from scripts.protocol_manifest import sha256_file
    if candidate_report.get('anchor_run_id') != anchor_manifest['run_id']:
        raise ValueError('Candidate Q/Y lineage mismatch')
    anchor_directory = _path(anchor_manifest['artifact_refs']['report']).parent
    expected = {name: sha256_file(_path(name)) for name in [
        _name(anchor_directory / 'run.json'), _name(anchor_directory / 'report.json'),
        anchor_manifest['artifact_refs']['queries'], anchor_manifest['artifact_refs']['labels']]}
    source = anchor_manifest['identity']['input_hashes']
    if candidate_manifest['identity']['input_hashes'] != {**source, **expected}:
        raise ValueError('Candidate did not consume the exact independent Q/Y shard')


def _verify_feature_lineage(entry, manifest, report):
    approval = _read_json(_path(entry['acceptance']['path']))
    if _digest(_path(entry['acceptance']['path'])) != entry['acceptance']['sha256']:
        raise ValueError('Feature acceptance content changed')
    expected = {**approval['fingerprints'], entry['acceptance']['path']: entry['acceptance']['sha256']}
    inputs = manifest['identity']['input_hashes']
    if any(inputs.get(name) != digest for name, digest in expected.items()):
        raise ValueError('Feature output did not consume the exact accepted Q/Y/C lineage')
    if (report.get('candidate_run_id') != entry['candidate']['run_id']
            or report.get('anchor_run_id') != entry['anchor']['run_id']
            or report.get('selection', {}).get('source_candidate_run') != entry['candidate']['run_id']):
        raise ValueError('Feature report candidate/anchor lineage mismatch')


def aggregate_collection(plan, state, *, check=lambda: None, ledger=None):
    """Verify exact shard cover and Q/Y/C/F relations without concatenating F."""
    import duckdb
    from scripts.anchor_pilot import naive_utc
    stage = ledger or (lambda name, operation: operation())
    planned = plan['identity']['shard_protocols']
    if len(state['shards']) != len(planned):
        raise ValueError('Incomplete shard cover')
    refs = {name: [] for name in ['queries', 'labels', 'candidates', 'features']}
    expected_daily, reported = [], dict(queries=0, labels=0, candidates=0, features=0)
    feature_columns = None
    for index, (entry, protocol) in enumerate(zip(state['shards'], planned)):
        if entry['index'] != index or entry['protocol'] != protocol or not {'anchor', 'candidate', 'features', 'acceptance'} <= entry.keys():
            raise ValueError('Incomplete, duplicated or mismatched shard cover')
        am, ar = _check_cached(entry['anchor'], protocol, 'anchor', plan, check)
        cm, cr = _check_cached(entry['candidate'], protocol, 'candidate', plan, check)
        fm, fr = _check_cached(entry['features'], protocol, 'features', plan, check)
        _verify_candidate_lineage(am, cm, cr)
        _verify_feature_lineage(entry, fm, fr)
        for name, manifest in [('queries', am), ('labels', am), ('candidates', cm), ('features', fm)]:
            refs[name].append(manifest['artifact_refs'][name])
        for day in ar['daily_outcomes']:
            expected_daily.append(day['anchor'])
            reported['queries'] += day['queries']
            reported['labels'] += day['distinct_targets']
        reported['candidates'] += sum(day['candidate_rows'] for day in cr['daily_coverage'])
        reported['features'] += fr['feature_rows']
        if fr['selected_queries'] != sum(d['queries'] for d in ar['daily_outcomes']):
            raise ValueError('Feature query population differs from Q')
        if feature_columns is not None and fr['feature_columns'] != feature_columns:
            raise ValueError('Feature schema differs across shards')
        feature_columns = fr['feature_columns']
    phase = plan['identity']['phase']
    expected = []
    day = utc(phase['range']['start'])
    while day < utc(phase['range']['end']):
        expected.append(day.strftime('%Y-%m-%dT%H:%M:%SZ'))
        day += timedelta(days=1)
    if expected_daily != expected:
        raise ValueError('Missing or duplicate daily report coverage')
    con = duckdb.connect(':memory:')
    timer = None
    try:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='2GB'")
        if ledger is not None:
            ledger.connection = con
            con.execute('SET temp_directory=?', [str(ledger.directory)])
            if ledger.deadline is not None:
                timer = ledger.deadline.interrupt_timer(con)
        for name, paths in refs.items():
            check()
            con.read_parquet([str(_path(p)) for p in paths]).create_view(name)
        if [row[0] for row in con.execute('DESCRIBE features').fetchall()] != feature_columns:
            raise ValueError('Physical feature schema differs from complete producer reports')
        def query(sql, args=None):
            check()
            value = stage('aggregate_' + str(len(stages)), lambda: con.execute(sql, args or []).fetchone())
            stages.append(sql)
            check()
            return value
        stages = []
        actual = {name: query(f'SELECT count(*) FROM {name}')[0] for name in refs}
        if actual != reported:
            raise ValueError('Actual collection counts disagree with complete producer reports')
        if actual['queries'] > phase['budget']['max_queries'] or actual['candidates'] > phase['budget']['max_candidate_pairs']:
            raise ValueError('Actual collection exceeds declared caps')
        if query('SELECT count(*),count(DISTINCT query_id),count(DISTINCT (user_id,anchor)) FROM queries') != (actual['queries'],) * 3:
            raise ValueError('Duplicate Q or user-day across shards')
        if query('''SELECT count(*) FROM queries WHERE query_id IS NULL OR user_id IS NULL OR anchor IS NULL
                    OR label_is_mature IS DISTINCT FROM true OR anchor<CAST(? AS TIMESTAMP) OR anchor>=CAST(? AS TIMESTAMP)
                    OR anchor<>date_trunc('day',anchor)''', [naive_utc(utc(phase['range']['start'])), naive_utc(utc(phase['range']['end']))])[0]:
            raise ValueError('Invalid, censored or out-of-phase Q')
        for name in ['labels', 'candidates', 'features']:
            if query(f'SELECT count(*),count(DISTINCT (query_id,product_id)) FROM {name}') != (actual[name],) * 2:
                raise ValueError('Duplicate ' + name + ' pair across shards')
            if query(f'''SELECT count(*) FROM {name} x LEFT JOIN queries q USING(query_id)
                         WHERE q.query_id IS NULL OR x.product_id IS NULL''')[0]:
                raise ValueError('Orphan or null pair: ' + name)
        if query('''SELECT count(*) FROM ((SELECT query_id,product_id FROM candidates EXCEPT
                      SELECT query_id,product_id FROM features) UNION ALL
                     (SELECT query_id,product_id FROM features EXCEPT SELECT query_id,product_id FROM candidates))''')[0]:
            raise ValueError('Features do not cover exactly C')
        fixed = ['query_id', 'product_id', 'from_popular', 'from_recent', 'popularity_distinct_users',
                 'popular_source_rank', 'recent_source_rank', 'last_user_event_time']
        columns = ','.join(fixed)
        if query(f'''SELECT count(*) FROM ((SELECT {columns} FROM candidates EXCEPT SELECT {columns} FROM features)
                       UNION ALL (SELECT {columns} FROM features EXCEPT SELECT {columns} FROM candidates))''')[0]:
            raise ValueError('Feature materialization altered fixed retrieval columns')
        if query('''SELECT count(*) FROM features f JOIN queries q USING(query_id)
                    WHERE f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor''')[0]:
            raise ValueError('Feature query metadata mismatch')
        return dict(counts=actual, daily_anchors=expected, artifact_refs=refs, feature_columns=feature_columns,
                    scope='mechanical_integrity_only_pending_independent_semantic_acceptance')
    finally:
        if timer is not None:
            timer.cancel()
        if ledger is not None:
            ledger.connection = None
        con.close()


def run_phase(phase_path, db_path, output_root, *, producer_approval_path, shard_acceptance_dir):
    """Produce Q/Y/C, wait for external review, resume F; never self-accept.

    Each invocation has an attempt audit. Compute budget is cumulative across
    resumes; time between invocations waiting for review is explicitly excluded.
    A leftover exclusive lock after process death requires cost/output review.
    """
    import os
    import time
    import uuid
    from scripts import anchor_pilot, candidate_pilot, manual_features
    from scripts.anchor_pilot import RunDeadline, StageLedger, peak_rss_bytes
    from scripts.heuristic_baselines import verify_accepted_inputs
    started = time.monotonic()
    root = Path(output_root).resolve()
    root.relative_to(ROOT.resolve() / 'artifacts')
    attempt = root / ('attempt-' + uuid.uuid4().hex)
    attempt.mkdir(parents=True, exist_ok=False)
    (attempt / 'profiles').mkdir()
    deadline = RunDeadline(3600, started_at=started)
    ledger = StageLedger(attempt / 'profiles', deadline=deadline)
    report = dict(version=1, status='running', stages=ledger.rows,
                  acceptance_scope='produced outputs are not independently accepted',
                  wall_accounting='cumulative invocation elapsed including preparation; between-invocation review wait excluded')
    _atomic_json(attempt / 'report.json', report)
    state = directory = lock = None
    owns_lock = False
    prior_compute = 0.0
    def guard():
        deadline.check()
        if peak_rss_bytes() > 8 * 2**30:
            raise MemoryError('Collection cooperative process RSS ceiling exceeded8GiB')
    def stage(name, operation):
        def checked():
            guard()
            result = operation()
            guard()
            return result
        return ledger(name, checked)
    def persist():
        _atomic_json(directory / 'state.json', state)
    def produce(entry, protocol, kind, operation, output):
        if kind in entry:
            return stage('verify_cached_' + kind + '_' + str(entry['index']),
                         lambda: _check_cached(entry[kind], protocol, kind, plan, guard))
        # Unsealed failed v1 runs are immutable too. A fresh child namespace
        # preserves partial evidence while allowing an ordinary resume.
        child_root = output / ('invocation-' + uuid.uuid4().hex)
        entry.setdefault('producer_attempts', []).append(dict(kind=kind, output_root=_name(child_root)))
        persist()
        child = stage('produce_' + kind + '_' + str(entry['index']), lambda: operation(child_root))
        manifest, child_report, seal = stage('seal_' + kind + '_' + str(entry['index']),
            lambda: _verify_run(child_root / child['run_id'], protocol=protocol, kind=kind, plan=plan, check=guard))
        entry[kind] = seal
        persist()
        return manifest, child_report
    try:
        plan = stage('prepare_phase_plan', lambda: prepare_execution_plan(phase_path, db_path, check=guard))
        approval_path = Path(producer_approval_path).resolve()
        _name(approval_path)
        approval = stage('read_producer_approval', lambda: _read_json(approval_path))
        verify_producer_approval(plan, approval)
        approval_sha = _digest(approval_path, guard)
        directory = root / plan['collection_id']
        directory.mkdir(parents=True, exist_ok=True)
        lock = directory / '.runtime.lock'
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        owns_lock = True
        os.close(fd)
        if (directory / 'state.json').exists():
            loaded = _read_json(directory / 'state.json')
            if loaded['collection_id'] != plan['collection_id'] or loaded['producer_approval_sha256'] != approval_sha or _read_json(directory / 'plan.json') != plan:
                raise ValueError('Cached collection plan/approval lineage differs')
            prior_compute = loaded['compute_seconds']
            if not isinstance(prior_compute, (int, float)) or not 0 <= prior_compute < plan['identity']['phase']['budget']['wall_seconds']:
                raise TimeoutError('Cumulative phase compute budget exhausted or invalid')
            state = loaded
        else:
            _atomic_json(directory / 'plan.json', plan)
            state = dict(version=1, collection_id=plan['collection_id'], producer_approval_sha256=approval_sha,
                         compute_seconds=0.0, status='preparing', attempts=[],
                         shards=[dict(index=i, protocol=p) for i, p in enumerate(plan['identity']['shard_protocols'])])
        deadline = RunDeadline(plan['identity']['phase']['budget']['wall_seconds'] - prior_compute, started_at=started)
        ledger.deadline = deadline
        report.update(collection_id=plan['collection_id'], prior_compute_seconds=prior_compute,
                      phase_wall_budget=plan['identity']['phase']['budget']['wall_seconds'])
        state['status'] = 'running'
        persist()
        guard()
        if len(state['shards']) != len(plan['identity']['shard_protocols']):
            raise ValueError('Cached shard cover is incomplete')
        pending = []
        approvals = {}
        for entry, protocol in zip(state['shards'], plan['identity']['shard_protocols']):
            if entry['protocol'] != protocol or entry['index'] != len(approvals) + len(pending):
                raise ValueError('Cached shard order/protocol mismatch')
            shard = directory / 'shards' / str(entry['index'])
            shard.mkdir(parents=True, exist_ok=True)
            config = shard / 'protocol.json'
            if config.exists() and _read_json(config) != protocol:
                raise ValueError('Cached shard protocol changed')
            if not config.exists():
                _atomic_json(config, protocol)
            remaining = lambda: deadline.expires_at - time.monotonic()
            am, ar = produce(entry, protocol, 'anchor',
                lambda output: anchor_pilot.run(config, Path(db_path), output, seconds=remaining()), shard / 'anchor')
            cm, cr = produce(entry, protocol, 'candidate',
                lambda output: candidate_pilot.run(_path(entry['anchor']['directory']), output, seconds=remaining()), shard / 'candidate')
            _verify_candidate_lineage(am, cm, cr)
            approval_file = Path(shard_acceptance_dir).resolve() / (cm['run_id'] + '.json')
            _name(approval_file)
            if not approval_file.exists():
                pending.append(dict(index=entry['index'], anchor_run=entry['anchor']['directory'],
                                    candidate_run=entry['candidate']['directory'], expected_approval=_name(approval_file)))
                continue
            accepted = stage('read_shard_acceptance_' + str(entry['index']), lambda: _read_json(approval_file))
            result = stage('verify_external_shard_acceptance_' + str(entry['index']),
                lambda: verify_accepted_inputs(_path(entry['candidate']['directory']), accepted, check=guard))
            if result[0] != protocol or _name(result[2]) != plan['execution_inputs']['source_path']:
                raise ValueError('Accepted shard differs from planned source/protocol')
            for name, digest in accepted['fingerprints'].items():
                if _digest(_path(name), guard) != digest:
                    raise ValueError('Accepted extra output changed: ' + name)
            seal = dict(path=_name(approval_file), sha256=_digest(approval_file, guard))
            if 'acceptance' in entry and entry['acceptance'] != seal:
                raise ValueError('Cached shard acceptance changed')
            entry['acceptance'] = seal
            approvals[entry['index']] = approval_file
            persist()
        if pending:
            report.update(status='waiting_for_shard_review', pending=pending)
        else:
            for entry, protocol in zip(state['shards'], plan['identity']['shard_protocols']):
                output = directory / 'shards' / str(entry['index']) / 'features'
                fm, fr = produce(entry, protocol, 'features',
                    lambda output: manual_features.run(_path(entry['candidate']['directory']),
                        _path(plan['identity']['phase']['feature_registry']), output,
                        acceptance_path=approvals[entry['index']], seconds=remaining()), output)
                _verify_feature_lineage(entry, fm, fr)
            report['collection'] = stage('verify_complete_collection',
                lambda: aggregate_collection(plan, state, check=guard, ledger=ledger))
            report['status'] = 'complete_produced_unreviewed'
        return report
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        elapsed = time.monotonic() - started
        report.update(seconds=elapsed, cumulative_compute_seconds=prior_compute + elapsed,
                      process_peak_rss_bytes=peak_rss_bytes())
        if state is not None and owns_lock:
            state.update(status=report['status'], compute_seconds=prior_compute + elapsed)
            state['attempts'].append(_name(attempt / 'report.json'))
            persist()
        _atomic_json(attempt / 'report.json', report)
        if owns_lock:
            lock.unlink()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True, type=Path)
    parser.add_argument('--db', type=Path, default=ROOT / 'data/processed/october.duckdb')
    parser.add_argument('--producer-approval', required=True, type=Path)
    parser.add_argument('--shard-acceptance-dir', required=True, type=Path)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'artifacts/development')
    args = parser.parse_args()
    result = run_phase(args.phase, args.db, args.output_root, producer_approval_path=args.producer_approval,
                       shard_acceptance_dir=args.shard_acceptance_dir)
    print(canonical_json({key: result[key] for key in ['collection_id', 'status', 'cumulative_compute_seconds']}))


if __name__ == '__main__':
    main()
