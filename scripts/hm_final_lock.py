"""Validate the one predeclared H&M final experiment, without reading rows.

This is a local immutable JSON contract, not an execution ledger. Call these
checks before opening a data connection or fitting a model. The caller remains
responsible for exclusive operation receipts and byte checks of parquet/model
files. A collection/report attaches ``final_lock_sha256``; the lock itself is
never amended with hashes learned from the final targets.

``finalmanifest`` is the path to the produced collection's manifest.json.
``trainidentities`` are the five existing fit-input identity dictionaries.
See tests/test_hm_final_lock.py for a complete synthetic lock and request.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re

ROOT = Path(__file__).resolve().parents[1]
ANCHORS = ['2020-08-12', '2020-08-19', '2020-08-26', '2020-09-02', '2020-09-09']
FINAL = '2020-09-16'
HEX = re.compile(r'[0-9a-f]{64}\Z')
RESERVED = {'customer_id', 'article_id', 'label', 'query_weight', 'full_candidate_count', 'anchor'}
CONTRASTS = [
    dict(name='selected_minus_M_seed_mean', positive=['arm-02', 'arm-03'], negative=['arm-00', 'arm-01']),
    dict(name='selected_minus_M_seed2026', positive=['arm-02'], negative=['arm-00']),
    dict(name='selected_minus_M_seed2027', positive=['arm-03'], negative=['arm-01']),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _decode(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON property')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON constant')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def read_json(path):
    return _decode(Path(path).read_text(encoding='utf-8'))


def same(actual, expected):
    # Python equality treats 1, True and 1.0 as equal; the JSON contract does not.
    return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def keys(value, expected, message):
    require(isinstance(value, dict) and set(value) == set(expected.split()), message)


def sha(value):
    require(isinstance(value, str) and bool(HEX.fullmatch(value)), 'Full lowercase SHA256 required')


def artifact(value):
    require(isinstance(value, str) and bool(value) and '\\' not in value, 'Nonempty POSIX artifact path required')
    require(not Path(value).is_absolute() and '..' not in Path(value).parts, 'Project-relative artifact path required')
    path = (ROOT / value).resolve()
    allowed = (ROOT / 'artifacts').resolve()
    require(path != allowed and path.is_relative_to(allowed), 'Path must stay inside checkout artifacts/')
    return path


def reference(value):
    keys(value, 'path sha256', 'Reference requires path and sha256')
    sha(value['sha256'])
    require(isinstance(value['path'], str) and bool(value['path']) and '\\' not in value['path'], 'POSIX reference path required')
    require(not Path(value['path']).is_absolute() and '..' not in Path(value['path']).parts, 'Project-relative reference path required')
    path = (ROOT / value['path']).resolve()
    require(path.is_relative_to(ROOT.resolve()), 'Reference escapes checkout')
    require(path.is_file() and digest(path) == value['sha256'], 'Frozen reference byte identity changed')
    return path


def identity(manifest_path):
    value = read_json(manifest_path)
    return dict(anchor=value['anchor'], manifest_sha256=digest(manifest_path),
                qcy_identity=value['qcy_identity'], candidate_identity=value['candidate_identity'])


def feature_names(value):
    keys(value, 'numeric categorical', 'Features require ordered numeric and categorical lists')
    for names in value.values():
        require(isinstance(names, list) and all(isinstance(n, str) and bool(n.strip()) for n in names), 'Feature names must be string lists')
    names = value['numeric'] + value['categorical']
    require(bool(names) and len(set(names)) == len(names) and not set(names) & RESERVED, 'Unique non-outcome feature names required')


def runtime_identity():
    return dict(python=platform.python_version(), platform=platform.platform(),
                packages={name: importlib.metadata.version(name) for name in ('duckdb', 'numpy', 'pandas', 'catboost')},
                threads=4, duckdb_memory_limit='2GB')


def _schema(plan, contract):
    registry = contract.get('registry')
    require(isinstance(registry, list) and bool(registry), 'Nonempty feature registry required')
    specs = {}
    for entry in registry:
        require(isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry.get('kind') in ('numeric', 'categorical'), 'Malformed feature registry entry')
        require(entry['name'] not in specs, 'Duplicate registered feature')
        specs[entry['name']] = entry['kind']
    for features in plan['features'].values():
        require(all(specs.get(name) == kind for kind, names in features.items() for name in names), 'Locked feature is absent or has wrong schema kind')


@dataclass(frozen=True)
class Lock:
    path: Path
    sha256: str
    _json: str

    @property
    def data(self):
        # Returning a fresh tree prevents accidental mutation of the frozen plan.
        return json.loads(self._json)


def _guard(lock):
    require(isinstance(lock, Lock) and digest(lock.path) == lock.sha256, 'Decision lock bytes changed')
    value = lock.data
    reference(value['campaign'])
    for ref in value['provenance'].values():
        reference(ref)
    for ref in value['train_collections']:
        reference(ref)
    for name, expected in value['implementation']['code'].items():
        require(digest(ROOT / 'scripts' / name) == expected, 'Frozen implementation changed')
    require(same(runtime_identity(), value['implementation']['runtime']), 'Frozen runtime changed')
    return value


def load_lock(path):
    """Read and validate the frozen plan and its already-existing evidence files."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    value = _decode(raw.decode('utf-8'))
    keys(value, 'format campaign provenance database feature_digest implementation final train_collections features hyperparameters outputs contrasts', 'Unexpected final lock schema')
    require(value['format'] == 'hm-final-decision-lock-v1', 'Unsupported final lock format')
    reference(value['campaign'])
    keys(value['provenance'], 'manual selection confirmation', 'Three development provenance references required')
    for ref in value['provenance'].values():
        reference(ref)
    keys(value['database'], 'sha256 bytes', 'Database identity requires sha256 and bytes')
    sha(value['database']['sha256'])
    require(type(value['database']['bytes']) is int and value['database']['bytes'] > 0, 'Positive database byte size required')
    sha(value['feature_digest'])
    keys(value['implementation'], 'code runtime', 'Code and runtime identities required')
    code = value['implementation']['code']
    required = {'hm_experiment.py', 'hm_baseline.py', 'hm_feature_engine.py', 'hm_retrieval.py', 'hm_result_audit.py', 'hm_final_lock.py'}
    require(isinstance(code, dict) and required <= set(code), 'Final implementation pins are incomplete')
    for name, expected in code.items():
        require(isinstance(name, str) and bool(re.fullmatch(r'hm_[a-z_]+\.py', name)), 'Invalid source basename')
        sha(expected)
    require(isinstance(value['implementation']['runtime'], dict) and bool(value['implementation']['runtime']), 'Runtime identity required')
    expected_final = dict(anchor=FINAL, horizon_days=7, policy='C0-Q120', users=20000,
                          cohort_seed=2026, sampling_seed=2026, train_users=20000, negative_sample=20)
    require(value['final'] == expected_final and all(type(value['final'][k]) is type(v) for k, v in expected_final.items()), 'Final date/cohort/training policy differs from campaign')
    collections = value['train_collections']
    require(isinstance(collections, list) and len(collections) == 5, 'Exactly five frozen training collections required')
    paths = []
    for anchor, ref in zip(ANCHORS, collections):
        directory = artifact(ref['path']) if isinstance(ref, dict) and 'path' in ref else None
        path_ref = reference(ref)
        require(directory == path_ref and path_ref.name == 'manifest.json', 'Training reference must name artifact manifest.json')
        manifest = read_json(path_ref)
        _base_manifest(value, manifest, anchor)
        require(manifest['anchor'] == anchor, 'Training anchors must match the five frozen weeks in order')
        paths.append(path_ref)
    require(len(set(paths)) == 5, 'Duplicate training collection path')
    keys(value['features'], 'M selected', 'Exactly M and selected feature arms required')
    for features in value['features'].values():
        feature_names(features)
    m, selected = value['features']['M'], value['features']['selected']
    require(set(m['numeric']) <= set(selected['numeric']) and set(m['categorical']) <= set(selected['categorical']), 'Selected arm must retain M feature kinds')
    require(len(selected['numeric'] + selected['categorical']) == len(m['numeric'] + m['categorical']) + 12, 'Selected arm requires exactly twelve additional features')
    contracts = [read_json(reference(ref))['features'] for ref in collections]
    require(all(contract == contracts[0] for contract in contracts), 'Training feature schemas differ')
    _schema(value, contracts[0])
    params = value['hyperparameters']
    keys(params, 'iterations depth learning_rate l2_leaf_reg loss_function thread_count task_type verbose allow_writing_files', 'Unexpected fixed hyperparameter schema')
    require(type(params['iterations']) is int and params['iterations'] in (150, 500) and type(params['depth']) is int and params['depth'] in (6, 8), 'Manual grid capacity required')
    require(not (params['iterations'] == 150 and params['depth'] == 8), 'Capacity is outside the frozen manual grid')
    require(params['learning_rate'] == .05 and params['l2_leaf_reg'] == 10 and params['loss_function'] == 'Logloss' and type(params['thread_count']) is int and params['thread_count'] == 4 and params['task_type'] == 'CPU' and params['verbose'] is False and params['allow_writing_files'] is False, 'Fixed CatBoost parameters changed')
    keys(value['outputs'], 'collection fits audit', 'Collection, four fit and audit output paths required')
    fits = value['outputs']['fits']
    require(isinstance(fits, list) and len(fits) == 4, 'Exactly four ordered fit outputs required')
    all_outputs = [value['outputs']['collection'], *fits, value['outputs']['audit']]
    resolved = [artifact(p) for p in all_outputs]
    require(len(set(resolved)) == 6 and all(not a.is_relative_to(b) for a in resolved for b in resolved if a != b), 'Output paths must be distinct and disjoint')
    require(value['contrasts'] == CONTRASTS, 'Final contrasts must use per-user seed means and both seed pairs')
    lock = Lock(path, hashlib.sha256(raw).hexdigest(), json.dumps(value, ensure_ascii=False, allow_nan=False))
    _guard(lock)
    return lock


def _base_manifest(plan, manifest, anchor):
    require(manifest.get('format') == 'hm-experiment-collection-v1' and manifest.get('status') == 'completed', 'Completed collection required')
    expected = dict(anchor=anchor, horizon_days=7, cohort_seed=2026, policy='C0-Q120', requested_users=20000)
    require(same({k: manifest.get(k) for k in expected}, expected), 'Frozen collection date/policy/cohort mismatch')
    require(manifest.get('database') == plan['database'] and manifest.get('features', {}).get('digest') == plan['feature_digest'], 'Collection source/feature identity mismatch')
    require(manifest.get('code', {}).get('hm_feature_engine.py') == plan['implementation']['code']['hm_feature_engine.py'], 'Collection pure feature engine differs from lock')
    for field in ('qcy_identity', 'candidate_identity'):
        sha(manifest.get(field))
    files = manifest.get('files', {})
    require(set(files) == {'frame.parquet', 'users.parquet', 'targets.parquet'}, 'Complete cache artifact identities required')
    for expected in files.values():
        sha(expected)


def authorize_collect(lock, request, source_identity, feature_digest):
    """Authorize the sole final collection before any final target SQL."""
    plan = _guard(lock)
    keys(request, 'output anchor users policy cohort_seed horizon_days', 'Unexpected collection request')
    require(same(request, dict(output=plan['outputs']['collection'], **{k: plan['final'][k] for k in ('anchor', 'users', 'policy', 'cohort_seed', 'horizon_days')})), 'Collection request differs from lock')
    require(same(source_identity, plan['database']) and feature_digest == plan['feature_digest'], 'Final source/feature identity mismatch')
    require(not artifact(request['output']).exists(), 'Final collection output already exists; inspect receipt before retry')


def _final_manifest(lock, plan, finalmanifest):
    path = Path(finalmanifest).resolve()
    require(path == artifact(plan['outputs']['collection']) / 'manifest.json', 'Final collection path differs from lock')
    manifest = read_json(path)
    _base_manifest(plan, manifest, FINAL)
    contract = read_json(reference(plan['train_collections'][0]))['features']
    require(manifest['features'] == contract, 'Final feature schema differs from frozen training schema')
    _schema(plan, contract)
    require(manifest.get('final_lock_sha256') == lock.sha256, 'Final collection does not attach this decision lock')
    require(manifest.get('runtime') == plan['implementation']['runtime'], 'Final collection runtime differs from lock')
    _code_subset(plan, manifest.get('code'), {'hm_experiment.py', 'hm_baseline.py', 'hm_feature_engine.py', 'hm_retrieval.py'})
    return manifest, identity(path)


def _code_subset(plan, code, required):
    require(isinstance(code, dict) and required <= set(code) <= set(plan['implementation']['code']), 'Producer code identity is incomplete')
    require(all(expected == plan['implementation']['code'][name] for name, expected in code.items()), 'Producer code differs from lock')


def authorize_fit(lock, request, trainidentities, finalmanifest):
    """Return M or selected for exactly one of the four predeclared fits."""
    plan = _guard(lock)
    keys(request, 'output validation numeric categorical hyperparameters train_users negative_sample sampling_seed', 'Unexpected fit request')
    require(request['output'] in plan['outputs']['fits'], 'Fit output is not predeclared')
    number = plan['outputs']['fits'].index(request['output'])
    arm = 'M' if number < 2 else 'selected'
    features = plan['features'][arm]
    params = dict(plan['hyperparameters'], random_seed=(2026, 2027)[number % 2])
    expected = dict(output=plan['outputs']['fits'][number], validation=plan['outputs']['collection'],
                    **features, hyperparameters=params, train_users=20000, negative_sample=20, sampling_seed=2026)
    require(same(request, expected), 'Fit features/hyperparameters/training policy differ from lock')
    require(trainidentities == [identity(reference(ref)) for ref in plan['train_collections']], 'Five training identities differ from lock')
    _final_manifest(lock, plan, finalmanifest)
    require(not artifact(request['output']).exists(), 'Final fit output already exists; inspect receipt before retry')
    return arm


def authorize_audit(lock, finalmanifest, fitreports):
    """Check all four completed fit reports in locked order before audit SQL.

    fitreports are paths to report.json. The caller uses the returned audit path;
    the frozen contrasts can be copied with the subsequently known audit SHA.
    """
    plan = _guard(lock)
    _, val_identity = _final_manifest(lock, plan, finalmanifest)
    require(isinstance(fitreports, (list, tuple)) and len(fitreports) == 4, 'Audit requires four ordered fits')
    train = [identity(reference(ref)) for ref in plan['train_collections']]
    for number, supplied in enumerate(fitreports):
        path = Path(supplied).resolve()
        require(path == artifact(plan['outputs']['fits'][number]) / 'report.json', 'Audit fit order/path differs from lock')
        report = read_json(path)
        require(report.get('format') == 'hm-experiment-fit-v1' and report.get('status') == 'completed' and report.get('final_lock_sha256') == lock.sha256, 'Completed fit attaching this decision lock required')
        arm = 'M' if number < 2 else 'selected'
        require(report.get('features') == dict(plan['features'][arm], contract_digest=plan['feature_digest']), 'Final fit feature order differs from lock')
        require(report.get('hyperparameters') == dict(plan['hyperparameters'], random_seed=(2026, 2027)[number % 2]), 'Final fit hyperparameters differ from lock')
        require(report.get('training_user_limit') == 20000 and report.get('negative_sample') == 20 and report.get('sampling_seed') == 2026 and report.get('fit_count') == 1 and report.get('actual_trees') == plan['hyperparameters']['iterations'], 'Final training recipe/incomplete fit mismatch')
        require(report.get('inputs') == train + [val_identity], 'Final fit input identity differs from frozen collections')
        require(report.get('runtime') == plan['implementation']['runtime'], 'Final fit runtime differs from lock')
        _code_subset(plan, report.get('code'), {'hm_experiment.py', 'hm_baseline.py'})
    output = artifact(plan['outputs']['audit'])
    require(not output.exists(), 'Final audit output already exists; inspect receipt before retry')
    return output
