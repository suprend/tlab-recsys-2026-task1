"""Bounded two-fit CPU smoke with externally accepted data and full-Y metrics.

Smoke establishes execution, not a well-tuned baseline or confirmatory winner.
Raw IDs are join keys only; all selection queries and full targets are retained.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import re
import time
import uuid

import duckdb
import numpy as np

from scripts.anchor_pilot import RunDeadline, StageLedger, peak_rss_bytes
from scripts.development_collection import _atomic_json, _read_json, _keys, validate_phase, shard_protocols
from scripts.protocol_manifest import canonical_json, sha256_file, _utc as utc
from scripts.ranking_metrics import QueryRanking, evaluate, paired_user_bootstrap

ROOT = Path(__file__).resolve().parents[1]
CODE = ('uv.lock', 'scripts/train_baselines.py', 'scripts/development_collection.py',
        'scripts/protocol_manifest.py', 'scripts/temporal_contract.py', 'scripts/anchor_pilot.py',
        'scripts/ranking_metrics.py')


def _local(name):
    from scripts.protocol_manifest import _relative_path
    _relative_path(name)
    path = (ROOT / name).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _relative(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def validate_smoke(config):
    _keys(config, {'version', 'role', 'training_query_cap', 'max_matrix_rows', 'max_pairs',
                  'wall_seconds', 'iterations', 'depth', 'learning_rate', 'l2_leaf_reg',
                  'random_seed', 'k', 'bootstrap_replicates'}, 'CPU smoke config')
    if type(config['version']) is not int or config['version'] != 1 or config['role'] != 'cpu_smoke':
        raise ValueError('Only predeclared two-fit CPU smoke supported')
    bounds = dict(training_query_cap=(1, 6000), max_matrix_rows=(1, 1320000), max_pairs=(1, 2000000),
                  wall_seconds=(1, 3600), iterations=(1, 100), depth=(1, 8), random_seed=(0, 2**31-1),
                  k=(1, 100), bootstrap_replicates=(1, 1000))
    for key, (low, high) in bounds.items():
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError('Invalid bounded smoke parameter: ' + key)
    for key, low, high in [('learning_rate', 0, 1), ('l2_leaf_reg', 0, 100)]:
        if type(config[key]) not in (int, float) or not np.isfinite(config[key]) or not low < config[key] <= high:
            raise ValueError('Invalid finite smoke parameter: ' + key)
    return config


def verify_collection(acceptance_path, *, check=lambda: None):
    """Read explicit external pins before any physical data is used for fit."""
    acceptance_path = Path(acceptance_path).resolve()
    approval = _read_json(acceptance_path)
    _keys(approval, {'version', 'approved', 'scope', 'collection_id', 'complete_attempt_report', 'fingerprints'}, 'collection acceptance')
    if type(approval['version']) is not int or approval['version'] != 1 or approval['approved'] is not True or approval['scope'] != 'reviewed_development_collection':
        raise ValueError('Independent reviewed collection acceptance required')
    pins = approval['fingerprints']
    from scripts.protocol_manifest import _hashes
    _hashes(pins, 'collection acceptance')
    required, verified = set(), set()
    def verify(name, expected=None):
        required.add(name)
        if name not in pins or (expected is not None and pins[name] != expected):
            raise ValueError('Missing/mismatched collection acceptance pin: ' + name)
        if name in verified:
            return _local(name)
        check()
        if sha256_file(_local(name)) != pins[name]:
            raise ValueError('Accepted collection content changed: ' + name)
        check()
        verified.add(name)
        return _local(name)
    report_name = approval['complete_attempt_report']
    report = _read_json(verify(report_name))
    if report.get('status') != 'complete_produced_unreviewed' or report.get('collection_id') != approval['collection_id']:
        raise ValueError('Collection is incomplete or differs from reviewed output')
    # Plan/state are found among pins, then their exact names are constrained by collection ID.
    state_names = [n for n in pins if n.endswith('/' + approval['collection_id'] + '/state.json')]
    if len(state_names) != 1:
        raise ValueError('Expected one reviewed collection state')
    state_name = state_names[0]
    _local(state_name).parent.relative_to(ROOT.resolve() / 'artifacts')
    plan_name = state_name.removesuffix('state.json') + 'plan.json'
    state, plan = _read_json(verify(state_name)), _read_json(verify(plan_name))
    if (state.get('status') != 'complete_produced_unreviewed' or state.get('collection_id') != approval['collection_id']
            or plan.get('collection_id') != approval['collection_id'] or report_name not in state.get('attempts', [])):
        raise ValueError('Reviewed collection state/plan/report mismatch')
    identity = plan['identity']
    if hashlib.sha256(canonical_json(identity).encode()).hexdigest() != plan['collection_id']:
        raise ValueError('Collection plan digest changed')
    _keys(plan, {'collection_id', 'identity', 'execution_inputs'}, 'collection plan')
    _keys(identity, {'version', 'status', 'phase', 'shard_protocols', 'registry_sha256',
                     'source_sha256', 'code_hashes'}, 'collection identity')
    if type(identity['version']) is not int or identity['version'] != 1 or identity['status'] != 'planned_not_executed':
        raise ValueError('Unexpected collection plan identity schema')
    phase = identity['phase']
    execution = plan['execution_inputs']
    _keys(execution, {'phase_path', 'source_path', 'fingerprints'}, 'execution inputs')
    from scripts.development_collection import PRODUCER_CODE
    expected_inputs = set(PRODUCER_CODE) | {execution['phase_path'], execution['source_path'],
        phase['base_protocol'], phase['feature_registry'], 'pyproject.toml'}
    if execution['fingerprints'].keys() != expected_inputs:
        raise ValueError('Execution input scope differs from required producer bundle')
    for name, digest in execution['fingerprints'].items():
        verify(name, digest)
    if identity['source_sha256'] != execution['fingerprints'][execution['source_path']]:
        raise ValueError('Collection source identity is not bound to actual execution input')
    if identity['registry_sha256'] != execution['fingerprints'][phase['feature_registry']]:
        raise ValueError('Collection registry identity is not bound to actual execution input')
    if identity['code_hashes'] != {name: execution['fingerprints'][name] for name in PRODUCER_CODE}:
        raise ValueError('Collection code identity is not bound to actual producer bundle')
    if _read_json(_local(execution['phase_path'])) != phase:
        raise ValueError('Collection phase identity differs from actual pinned phase body')
    from scripts.protocol_manifest import load_protocol
    base = load_protocol(_local(phase['base_protocol']))
    validate_phase(phase, base)
    if identity['shard_protocols'] != shard_protocols(phase, base):
        raise ValueError('Collection shard configs differ from validated phase exact cover')
    if phase['role'] not in {'train', 'selection'} or phase['lock_required']:
        raise ValueError('Smoke cannot open confirmation or final holdout')
    if len(state['shards']) != len(identity['shard_protocols']):
        raise ValueError('Reviewed collection has incomplete shard cover')
    refs = {name: [] for name in ['queries', 'labels', 'candidates', 'features']}
    from scripts.development_collection import (_check_cached, _verify_candidate_lineage, _verify_feature_lineage)
    for index, (entry, protocol) in enumerate(zip(state['shards'], identity['shard_protocols'])):
        if entry['index'] != index or entry['protocol'] != protocol:
            raise ValueError('Reviewed shard order/protocol mismatch')
        verify(entry['acceptance']['path'], entry['acceptance']['sha256'])
        checked_children = {}
        for kind, outputs in [('anchor', ['queries', 'labels']), ('candidate', ['candidates']), ('features', ['features'])]:
            seal = entry[kind]
            for name, digest in seal['fingerprints'].items():
                verify(name, digest)
            # Reuse the accepted producer gate: exact mandatory code/input/
            # output sets and prior seals, not a partial second implementation.
            manifest, child_report = _check_cached(seal, protocol, kind, plan, check)
            checked_children[kind] = (manifest, child_report)
            if manifest['run_id'] != seal['run_id'] or manifest['identity']['protocol'] != protocol:
                raise ValueError('Reviewed producer run identity mismatch')
            if manifest['identity']['input_hashes'].get(execution['source_path']) != identity['source_sha256']:
                raise ValueError('Reviewed producer source differs from bound collection source')
            for group in ['code_hashes', 'input_hashes']:
                for name, digest in manifest['identity'][group].items():
                    verify(name, digest)
                    if group == 'code_hashes' and identity['code_hashes'].get(name) != digest:
                        raise ValueError('Reviewed producer code differs from bound collection code')
            for output in outputs:
                verify(manifest['artifact_refs'][output])
                refs[output].append(manifest['artifact_refs'][output])
        _verify_candidate_lineage(checked_children['anchor'][0], *checked_children['candidate'])
        _verify_feature_lineage(entry, *checked_children['features'])
    if refs != report['collection']['artifact_refs']:
        raise ValueError('Reviewed output refs differ from exact shard cover')
    if pins.keys() != required:
        raise ValueError('Collection approval pins differ from exact required lineage scope')
    return dict(phase=phase, refs=refs, feature_columns=report['collection']['feature_columns'],
                pins={**pins, _relative(acceptance_path): sha256_file(acceptance_path)}, plan=plan)


def validate_training_phases(train, selection, config):
    t, s = train['phase'], selection['phase']
    if t['role'] != 'train' or s['role'] != 'selection':
        raise ValueError('Expected train and selection collections only')
    for key in ['base_protocol', 'feature_registry', 'model_timing', 'final_holdout_start']:
        if t[key] != s[key]:
            raise ValueError('Training/selection semantics differ: ' + key)
    if train['plan']['identity']['source_sha256'] != selection['plan']['identity']['source_sha256']:
        raise ValueError('Training/selection sources differ')
    if train['plan']['identity']['registry_sha256'] != selection['plan']['identity']['registry_sha256']:
        raise ValueError('Training/selection feature registries differ')
    fit, ready = utc(t['model_timing']['fit_data_cutoff']), utc(t['model_timing']['available_at'])
    if utc(t['label_available_before']) != fit or not fit < ready <= utc(s['range']['start']):
        raise ValueError('Checkpoint availability/maturity does not precede selection')
    if config['wall_seconds'] > (ready - fit).total_seconds():
        raise ValueError('Compute budget exceeds declared checkpoint availability gap')
    for a, b in zip(train['plan']['identity']['shard_protocols'][:1], selection['plan']['identity']['shard_protocols'][:1]):
        for key in ['source', 'query', 'target', 'candidates', 'history']:
            if a[key] != b[key]:
                raise ValueError('Train/selection v1 policy differs: ' + key)


def numeric_feature_names(columns):
    excluded = {'query_id', 'user_id', 'product_id', 'anchor', 'candidate_category_id', 'last_user_event_time'}
    if any(not isinstance(c, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', c) for c in columns):
        raise ValueError('Unsafe/duplicate feature columns')
    if not excluded <= set(columns):
        raise ValueError('Expected complete manual feature schema')
    result = [c for c in columns if c not in excluded] + ['retrieval_last_event_age_seconds', 'retrieval_last_event_missing']
    if len(columns) != len(set(columns)) or len(result) != len(set(result)):
        raise ValueError('Unsafe/duplicate feature columns')
    return result


@dataclass
class Prepared:
    queries: list  # (query_id, user_id, anchor, full target frozenset)
    group: np.ndarray
    items: np.ndarray
    x: np.ndarray
    y: np.ndarray
    feature_names: list


def prepare_dataset(collection, *, max_queries, max_rows, check=lambda: None):
    """Query sampling precedes labels; zeros never cause future target insertion."""
    if max_queries is not None and (type(max_queries) is not int or not 1 <= max_queries <= 6000):
        raise ValueError('Query cap must be1–6000 or None')
    if type(max_rows) is not int or not 1 <= max_rows <= 1320000:
        raise ValueError('Invalid matrix row cap')
    names = numeric_feature_names(collection['feature_columns'])
    con = duckdb.connect(':memory:')
    try:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='2GB'")
        for name in ['queries', 'labels', 'features']:
            con.read_parquet([str(_local(p)) for p in collection['refs'][name]]).create_view('all_' + name)
        check()
        limit = '' if max_queries is None else ' LIMIT ' + str(int(max_queries))
        con.execute('''CREATE TEMP TABLE chosen AS SELECT *, row_number() OVER(ORDER BY query_id)-1 group_index FROM
                      (SELECT * FROM all_queries ORDER BY sha256(query_id),query_id''' + limit + ')')
        if con.execute('''SELECT count(*) FROM chosen WHERE label_is_mature IS DISTINCT FROM true
                          OR query_id IS NULL OR user_id IS NULL OR anchor IS NULL''').fetchone()[0]:
            raise ValueError('Only mature complete training/evaluation queries')
        if con.execute('SELECT count(*),count(DISTINCT query_id),count(DISTINCT (user_id,anchor)) FROM chosen').fetchone() != (con.execute('SELECT count(*) FROM chosen').fetchone()[0],)*3:
            raise ValueError('Duplicate query/user-day')
        con.execute('''CREATE TEMP VIEW chosen_features AS SELECT f.*,q.group_index FROM all_features f JOIN chosen q USING(query_id)''')
        n, unique = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM chosen_features').fetchone()
        if n > max_rows:
            raise ValueError('Matrix row cap exceeded before allocation')
        if n != unique:
            raise ValueError('Duplicate candidate feature rows')
        if con.execute('''SELECT count(*) FROM chosen_features f JOIN chosen q USING(query_id)
                          WHERE f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor
                          OR f.product_id IS NULL OR f.last_user_event_time>=q.anchor''').fetchone()[0]:
            raise ValueError('Feature key/strict-past retrieval mismatch')
        # Full Y stays separate, including targets missing from C.
        target_rows = con.execute('''SELECT l.query_id,l.product_id FROM all_labels l JOIN chosen q USING(query_id)
                                    ORDER BY l.query_id,l.product_id''').fetchall()
        targets = {}
        for qid, item in target_rows:
            if item in targets.setdefault(qid, set()):
                raise ValueError('Duplicate full target')
            targets[qid].add(item)
        queries = [(qid, user, anchor, frozenset(targets.get(qid, ()))) for qid, user, anchor in
                   con.execute('SELECT query_id,user_id,anchor FROM chosen ORDER BY group_index').fetchall()]
        fields = [f'CAST(f."{name}" AS FLOAT) AS "{name}"' for name in names[:-2]]
        fields += ['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds',
                   'CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
        check()
        rows = con.execute('''SELECT f.group_index,f.product_id,CAST(l.product_id IS NOT NULL AS TINYINT) y,''' + ','.join(fields) + '''
                    FROM chosen_features f LEFT JOIN all_labels l USING(query_id,product_id)
                    ORDER BY f.group_index,f.product_id''').fetchnumpy()
        def numeric(array, dtype):
            if np.ma.isMaskedArray(array):
                return np.asarray(array.astype(dtype).filled(np.nan), dtype=dtype)
            return np.asarray(array, dtype=dtype)
        x = np.column_stack([numeric(rows[name], np.float32) for name in names])
        if np.isinf(x).any():
            raise ValueError('Infinite feature after float32 conversion')
        result = Prepared(queries, np.asarray(rows['group_index'], dtype=np.int32),
                          np.asarray(rows['product_id'], dtype=np.int64), x,
                          np.asarray(rows['y'], dtype=np.int8), names)
        check()
        return result
    finally:
        con.close()


def group_accounting(data):
    if data.x.shape != (len(data.group), len(data.feature_names)) or len(data.items) != len(data.group) or len(data.y) != len(data.group):
        raise ValueError('Prepared shapes disagree')
    if len(data.group) and (np.any(np.diff(data.group) < 0) or data.group[0] < 0 or data.group[-1] >= len(data.queries)):
        raise ValueError('Groups must be contiguous, sorted and refer to retained Q')
    if np.any((data.y != 0) & (data.y != 1)):
        raise ValueError('Only binary relevance supported')
    counts = np.bincount(data.group, minlength=len(data.queries))
    positive = np.bincount(data.group, weights=data.y, minlength=len(data.queries)).astype(np.int64)
    negative = counts - positive
    informative = (positive > 0) & (negative > 0)
    weights = np.divide(1.0, counts[data.group], out=np.empty(len(data.group), dtype=np.float64))
    summary = dict(queries=len(data.queries), candidate_rows=len(data.group), nonempty_candidate_groups=int((counts>0).sum()),
                   empty_candidate_groups=int((counts==0).sum()), informative_groups=int(informative.sum()),
                   all_negative_groups=int(((counts>0)&(positive==0)).sum()),
                   all_positive_groups=int(((counts>0)&(negative==0)).sum()),
                   positive_fullY_queries=sum(bool(q[3]) for q in data.queries), retrieved_positive_rows=int(positive.sum()),
                   zero_gradient_pairwise_groups=int((~informative).sum()), matrix_bytes=data.x.nbytes,
                   row_weight_sum=float(weights.sum()))
    return counts, positive, negative, informative, weights, summary


def explicit_pairs(data, *, max_pairs):
    counts, positive, negative, informative, weights, summary = group_accounting(data)
    total = sum(int(p)*int(n) for p,n in zip(positive, negative))
    if total > max_pairs:
        raise ValueError('Explicit pair cap exceeded before allocation')
    if total == 0:
        raise ValueError('No informative training pairs; do not invent a negative')
    retained = informative[data.group]
    selected_y, selected_groups = data.y[retained], data.group[retained]
    pairs = np.empty((total, 2), dtype=np.int32)
    pair_weights = np.empty(total, dtype=np.float64)
    cursor = 0
    for group in np.flatnonzero(informative):
        start, stop = np.searchsorted(selected_groups, [group, group+1])
        indices = np.arange(start, stop)
        p, n = indices[selected_y[indices] == 1], indices[selected_y[indices] == 0]
        mass = 1.0 / (len(p)*len(n))
        for winner in p:
            size = len(n)
            pairs[cursor:cursor+size, 0] = winner
            pairs[cursor:cursor+size, 1] = n
            pair_weights[cursor:cursor+size] = mass
            cursor += size
    return retained, pairs, pair_weights, summary


def rankings(data, scores):
    scores = np.asarray(scores)
    if scores.shape != (len(data.group),) or not np.isfinite(scores).all():
        raise ValueError('Predictions must be finite and cover exactly C')
    result = []
    # A single lexicographic ordering avoids scanning all rows once per query.
    order = np.lexsort((data.items, -scores, data.group))
    offset = 0
    for group, (qid, user, anchor, targets) in enumerate(data.queries):
        stop = offset
        while stop < len(order) and data.group[order[stop]] == group:
            stop += 1
        items = tuple(int(i) for i in data.items[order[offset:stop]])
        result.append(QueryRanking(qid, user, items, targets))
        offset = stop
    if offset != len(order):
        raise ValueError('Prediction group coverage mismatch')
    return result


def predict_scores(model, data, method):
    if not len(data.group):
        return np.empty(0, dtype=np.float64)
    return model.predict(data.x, prediction_type='RawFormulaVal', thread_count=2) if method == 'Logloss' else model.predict(data.x, thread_count=2)


class _BudgetCallback:
    def __init__(self, check):
        self.check = check
        self.failure = None

    def after_iteration(self, info):
        try:
            self.check()
            return True
        except Exception as error:
            self.failure = error
            return False


def fit_smoke_model(data, method, config, *, check=lambda: None):
    from catboost import CatBoostClassifier, CatBoostRanker, Pool
    config = validate_smoke(config)
    counts, positive, negative, informative, row_weights, summary = group_accounting(data)
    if not len(data.group) or np.unique(data.y).size != 2:
        raise ValueError('Training needs both observed labels and nonempty C')
    params = dict(iterations=config['iterations'], depth=config['depth'], learning_rate=config['learning_rate'],
                  l2_leaf_reg=config['l2_leaf_reg'], random_seed=config['random_seed'], thread_count=2,
                  task_type='CPU', boosting_type='Plain', bootstrap_type='No', verbose=False,
                  allow_writing_files=False, use_best_model=False)
    if method == 'Logloss':
        pool = Pool(data.x, label=data.y, weight=row_weights, feature_names=data.feature_names, thread_count=2)
        model = CatBoostClassifier(loss_function=method, **params)
        summary.update(trained_rows=len(data.group), explicit_pairs=0)
    elif method == 'PairLogit':
        mask, pairs, pair_weights, summary = explicit_pairs(data, max_pairs=config['max_pairs'])
        pool = Pool(data.x[mask], label=data.y[mask], group_id=data.group[mask], pairs=pairs,
                    pairs_weight=pair_weights, feature_names=data.feature_names, thread_count=2)
        model = CatBoostRanker(loss_function=method, **params)
        summary.update(trained_rows=int(mask.sum()), explicit_pairs=len(pairs), pair_weight_sum=float(pair_weights.sum()))
    else:
        raise ValueError('Unknown smoke objective')
    check()
    callback = _BudgetCallback(check)
    model.fit(pool, callbacks=[callback])  # No eval_set, native OD or best-model selection.
    if callback.failure is not None:
        raise callback.failure
    check()
    if model.tree_count_ != config['iterations']:
        raise ValueError('Fit did not reach the fixed, predeclared final checkpoint')
    return model, summary


def environment_snapshot(*, platform_format='legacy'):
    """Verify locked dependencies and report Python/platform metadata.

    Legacy preserves platform.platform() text. Kernel uses only os.uname()
    sysname/release/machine, or sys.platform when that API is absent.
    """
    import platform
    import sys
    import tomllib
    import catboost
    from importlib.metadata import version
    packages = tomllib.loads((ROOT / 'uv.lock').read_text())['package']
    actual = dict(catboost=catboost.__version__, duckdb=duckdb.__version__, numpy=np.__version__)
    for name, value in actual.items():
        locked = [p['version'] for p in packages if p['name'] == name]
        if locked != [value] or version(name) != value:
            raise ValueError('Loaded/installed dependency differs from lock: ' + name)
    if platform_format == 'legacy':
        host = platform.platform()
    elif platform_format == 'kernel':
        import os
        if hasattr(os, 'uname'):
            uname = os.uname()
            host = f'{uname.sysname}-{uname.release}-{uname.machine}'
        else:
            host = sys.platform
    else:
        raise ValueError('Unknown environment platform format: ' + str(platform_format))
    return dict(python=sys.version, platform=host, loaded_packages=actual)


def _config_snapshot(path):
    import json
    from scripts.protocol_manifest import _unique_object, _reject_constant
    raw = Path(path).read_bytes()
    config = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    return validate_smoke(config), hashlib.sha256(raw).hexdigest()


def prepare_fit_plan(config_path, train_acceptance, selection_acceptance, *, check=lambda: None):
    """This prepares a reviewable experiment, without approving or running it."""
    config_path = Path(config_path).resolve()
    config, config_sha = _config_snapshot(config_path)
    train = verify_collection(train_acceptance, check=check)
    selection = verify_collection(selection_acceptance, check=check)
    validate_training_phases(train, selection, config)
    if train['feature_columns'] != selection['feature_columns']:
        raise ValueError('Training and selection feature schema differs')
    pins = {}
    for group in [train['pins'], selection['pins']]:
        for name, digest in group.items():
            if name in pins and pins[name] != digest:
                raise ValueError('Train/selection accepted inputs conflict')
            pins[name] = digest
    for name in [*CODE, _relative(config_path), 'pyproject.toml']:
        check()
        actual = sha256_file(_local(name))
        if name == _relative(config_path) and actual != config_sha:
            raise ValueError('Config changed during fit-plan preparation')
        if name in pins and pins[name] != actual:
            raise ValueError('Accepted data code changed during fit-plan preparation: ' + name)
        pins[name] = actual
        check()
    identity = dict(version=1, role='cpu_smoke_two_fits', config=config, fingerprints=pins,
                    train_collection_id=train['plan']['collection_id'],
                    selection_collection_id=selection['plan']['collection_id'],
                    query_selection='train_bottom_sha256_query_id_then_id_before_labels',
                    score_ties='raw_score_desc_product_id_asc',
                    checkpoint='predeclared_fixed_final_iteration_no_eval_set_no_native_OD',
                    transform='numeric_manual_context_retrieval_v1_float32_NaN_rawIDs_excluded')
    return dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(), identity=identity), train, selection


def run(config_path, train_acceptance, selection_acceptance, output_root, *, fit_approval_path):
    """One immutable experiment identity permits exactly two model fit attempts."""
    started = time.monotonic()
    output_root = Path(output_root).resolve()
    output_root.relative_to(ROOT.resolve() / 'artifacts')
    directory = output_root / ('attempt-' + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'profiles').mkdir()
    deadline = RunDeadline(3600, started_at=started)
    ledger = StageLedger(directory / 'profiles', deadline=deadline)
    report = dict(version=1, status='running', stages=ledger.rows, fit_attempts=[],
                  purpose='execution smoke, not tuned control or confirmatory promotion',
                  availability='historical simulation; actual elapsed time recorded separately')
    _atomic_json(directory / 'report.json', report)
    manifest = None
    def guard():
        deadline.check()
        if peak_rss_bytes() > 8*2**30:
            raise MemoryError('CPU smoke cooperative RSS ceiling exceeded8GiB')
    def stage(name, operation):
        def checked():
            guard()
            result = operation()
            guard()
            return result
        return ledger(name, checked)
    try:
        config = validate_smoke(_read_json(config_path))
        deadline = RunDeadline(config['wall_seconds'], started_at=started)
        ledger.deadline = deadline
        manifest, train_collection, selection_collection = stage('verify_accepted_data_and_prepare_plan',
            lambda: prepare_fit_plan(config_path, train_acceptance, selection_acceptance, check=guard))
        if config != manifest['identity']['config']:
            raise ValueError('Config changed between initial parse and verified fit plan')
        config = validate_smoke(manifest['identity']['config'])
        guard()
        report['environment'] = stage('verify_loaded_environment_against_lock', environment_snapshot)
        approval = _read_json(fit_approval_path)
        expected = dict(version=1, approved=True, scope='cpu_smoke_two_fits', run_id=manifest['run_id'],
                        fingerprints=manifest['identity']['fingerprints'])
        _keys(approval, expected.keys(), 'fit approval')
        if type(approval['version']) is not int or approval['approved'] is not True or approval != expected:
            raise ValueError('Explicit reviewed two-fit experiment approval differs from actual plan')
        manifest['fit_approval'] = dict(path=_relative(fit_approval_path), sha256=sha256_file(fit_approval_path))
        identified = output_root / manifest['run_id']
        if identified.exists():
            raise FileExistsError('Existing experiment preserved; retries need reviewed budget recovery')
        # One project-wide atomic consumption claim, independent of CLI output.
        # It deliberately survives failed/preempted runs and needs reviewed
        # budget recovery; changing the destination cannot mint two more fits.
        import os
        claims = ROOT / 'artifacts/fit-claims'
        claims.mkdir(parents=True, exist_ok=True)
        claim_path = claims / (manifest['run_id'] + '.json')
        claim = dict(version=1, run_id=manifest['run_id'], fit_approval=manifest['fit_approval'],
                     allowed_fit_attempts=2, output_directory=_relative(identified),
                     report=_relative(identified / 'report.json'))
        try:
            fd = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise FileExistsError('Approved fit identity already consumed; reviewed budget recovery required') from error
        with os.fdopen(fd, 'w') as file:
            file.write(canonical_json(claim) + '\n')
            file.flush()
            os.fsync(file.fileno())
        report['fit_budget_claim'] = _relative(claim_path)
        directory.rename(identified)
        directory = identified
        ledger.directory = directory / 'profiles'
        _atomic_json(directory / 'run.json', manifest)
        report.update(run_id=manifest['run_id'], config=config,
                      model_timing=train_collection['phase']['model_timing'])
        train = stage('prepare_label_independent_train_subset', lambda: prepare_dataset(train_collection,
            max_queries=config['training_query_cap'], max_rows=config['max_matrix_rows'], check=guard))
        selection = stage('prepare_all_selection_queries', lambda: prepare_dataset(selection_collection,
            max_queries=None, max_rows=config['max_matrix_rows'], check=guard))
        report['training_population'] = group_accounting(train)[-1]
        report['selection_population'] = group_accounting(selection)[-1]
        report['feature_names'] = train.feature_names
        if train.feature_names != selection.feature_names:
            raise ValueError('Prepared feature schemas differ')
        # Validate both populations before spending either fit slot.
        if np.unique(train.y).size != 2:
            raise ValueError('No two-class training support')
        explicit_pairs(train, max_pairs=config['max_pairs'])
        results = {}
        for method in ['Logloss', 'PairLogit']:
            entry = dict(method=method, status='started', checkpoint_iterations=config['iterations'])
            report['fit_attempts'].append(entry)
            _atomic_json(directory / 'report.json', report)
            model, population = stage('fit_' + method, lambda: fit_smoke_model(train, method, config, check=guard))
            scores = stage('predict_' + method, lambda: predict_scores(model, selection, method))
            rows = stage('rank_full_C_' + method, lambda: rankings(selection, scores))
            metrics = stage('external_full_Y_evaluation_' + method, lambda: asdict(evaluate(rows, config['k'])))
            path = directory / (method + '.cbm')
            model.save_model(str(path))
            score_path = directory / (method + '-scores.npz')
            np.savez_compressed(score_path, group=selection.group, product_id=selection.items, raw_score=np.asarray(scores))
            entry.update(status='complete', training=population, metrics=metrics, tree_count=model.tree_count_,
                         actual_model_parameters=model.get_all_params(),
                         artifacts={_relative(p): sha256_file(p) for p in [path, score_path]})
            results[method] = rows
            del model
            guard()
        comparison = stage('paired_user_uncertainty_screening_only', lambda: asdict(paired_user_bootstrap(
            results['PairLogit'], results['Logloss'], config['k'], replicates=config['bootstrap_replicates'],
            seed=config['random_seed'])))
        report['comparison'] = comparison
        report['comparison']['interpretation'] = 'PairLogit minus Logloss; smoke screening, no promotion or selected winner'
        # Detect mutations during fits as well as at preparation.
        for name, digest in {**manifest['identity']['fingerprints'], manifest['fit_approval']['path']: manifest['fit_approval']['sha256']}.items():
            guard()
            if sha256_file(_local(name)) != digest:
                raise ValueError('Input changed during model execution: ' + name)
        guard()
        report['status'] = 'complete_produced_unreviewed'
        return report
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        for entry in report['fit_attempts']:
            if entry['status'] == 'started':
                entry.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report.update(seconds=time.monotonic()-started, process_peak_rss_bytes=peak_rss_bytes(),
                      fit_attempt_count=len(report['fit_attempts']))
        _atomic_json(directory / 'report.json', report)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'configs/models/cpu-smoke.json')
    parser.add_argument('--train-acceptance', type=Path, required=True)
    parser.add_argument('--selection-acceptance', type=Path, required=True)
    parser.add_argument('--fit-approval', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=ROOT/'artifacts/training')
    args = parser.parse_args()
    result = run(args.config, args.train_acceptance, args.selection_acceptance, args.output_root,
                 fit_approval_path=args.fit_approval)
    print(canonical_json({key: result[key] for key in ['status', 'run_id', 'seconds', 'fit_attempt_count']}))


if __name__ == '__main__':
    main()
