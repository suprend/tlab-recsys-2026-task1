"""Shared contract code of the agent-transfer experiment on Tinkoff and SberMarket.

Contract: docs/xfer-design.md (common) with docs/xfer-tinkoff-design.md and
docs/xfer-sber-design.md. This module fixes what the four executors share:
paths and output directories, the collection and base.json formats, the adapter
interface, code identity, the holdout window and seal, the bootstrap and the
reading rules. It imports nothing heavy at module level and has no side effects
on import.

Adapter interface (``scripts/xfer_tinkoff.py``, ``scripts/xfer_sber.py``); every
frame uses the column names ``user_id`` and ``item_id`` (S maps product_id to
item_id), anchors are ints on T and ISO dates (``YYYY-MM-DD`` strings) on S:

``load(raw, output) -> dict``
    Raw files -> ``load/events.duckdb``, ``load/events/`` partitions,
    ``load/static.duckdb`` and ``load/load.json``. ``output`` is
    ``output_dir(dataset, 'load')``.
``history(before, purpose, threads=4) -> duckdb connection``
    In-memory connection whose dataset views expose only history strictly
    before ``before``. For ``before > A_holdout`` it first requires
    ``holdout_window_open(dataset, purpose)``. The caller closes it.
``anchors() -> dict``
    ``W``, ``N``, ``K``, ``roles`` (role -> list of anchors), ``series``
    (series -> dict(train=[anchors], eval=anchor, eval_role=role, arms=[...])),
    ``holdout`` (A_holdout) and ``probe`` (probe anchor).
``collect(A, role, base, output, users=None) -> dict``
    Writes a collection (format below) into the new directory ``output`` and
    returns its manifest. Holdout labels go through ``write_sealed``.
``pop(A, users, k) -> DataFrame[user_id, item_id, rank]``
``views(A, purpose) -> dict``
    ``files`` (allowed partition paths), ``views`` (name -> SELECT over
    read_parquet of those files, already filtered strictly before A),
    ``schema`` (name -> [[column, type], ...]), ``levels`` (level -> key
    columns), ``items`` (SELECT of allowed item keys at A).
``sql_rules() -> dict``
    ``forbidden`` (extra forbidden words), ``check(sql, level)`` (callable that
    raises ValueError on a violation; dataset time rules).
``training_rows(frame, labels, A, seed=SAMPLE_SEED) -> DataFrame``
    Rows of a training anchor after the dataset's negative sampling, with
    ``label`` and ``weight``; ``frame`` is already restricted to the capped
    queries (``cap_queries``). Row order ``user_id, item_id``.
``metric(ranked, targets, labels) -> DataFrame[user_id, value]``
    One value per query of ``targets`` (``n_targets >= 1``); ``ranked`` is
    ``user_id, item_id, rank``; a query without ranked rows scores 0.
``assemble(scores, output) -> dict``
    Kaggle file from ``user_id, item_id, score`` of the kaggle frame.
``PROMPT_CONSTANTS`` (dict) and ``PROMPT_TEMPLATE`` (str).
    The template is the whole English prompt (dataset task and the H&M sandbox
    rules) with ``str.format`` slots; xfer_agent fills it with
    ``prompt_substitutions(...)`` and runs the number test on substitutions only.
``prompt_substitutions(stats, base, history, round_index, budget) -> dict``
    Slot values: task constants from PROMPT_CONSTANTS, candidate policy and base
    formulas from ``base``, view schemas, ``stats`` (stats.json of the probe),
    and ``history`` (feedback text rendered by xfer_agent).
``probe_pool() -> list[int]``
    Users with history before the probe anchor, first P in query order.
``probe_stats(A, users) -> dict``
    Label-free aggregates of history before A for stats.json.
``coverage_sources() -> dict(recent=[...], global=[...])``
    Source-rank columns of the frame behind the H&M coverage fields.

Sidecars (xfer_agent -> xfer_model): ``sidecars/<collection name>/agent.parquet``
with ``user_id, item_id`` and the agent columns in frozen order, one row per
frame row in frame order, plus manifest.json (``write_sidecar_manifest``).

Parquet goes through DuckDB (``write_parquet``/``read_parquet``): pyarrow is not
installed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

DATASETS = ('tinkoff', 'sber')
ADAPTERS = {'tinkoff': 'scripts.xfer_tinkoff', 'sber': 'scripts.xfer_sber'}
SHARED_MODULES = ('scripts.xfer_common', 'scripts.xfer_agent', 'scripts.xfer_model')
RAW = {'tinkoff': 'data/raw-tinkoff-kaggle', 'sber': 'data/raw-sbermarket-kaggle'}

SEEDS = (2026, 2027)
SAMPLE_SEED = 2026
PERMUTATION_SEED = 20261021
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 2026
QUERY_SALT = ':2026'
KAGGLE_CHUNK = {'tinkoff': 2000, 'sber': 15000}
THREADS = {'catboost': 8, 'collect': 4, 'sidecar': 4, 'probe': 3, 'agent': 3}
RECIPE = dict(iterations=500, depth=8, learning_rate=0.05, l2_leaf_reg=10, loss_function='Logloss',
              bootstrap_type='Bayesian', bagging_temperature=1, border_count=128, boosting_type='Plain',
              thread_count=THREADS['catboost'], task_type='CPU', verbose=False, allow_writing_files=False)
PREDICTION_TYPE = 'RawFormulaVal'

ROLES = ('train', 'val', 'holdout', 'kaggle', 'probe')
ARMS = ('B', 'BA', 'BApl')
POP = 'Pop'
OUTPUT_KINDS = ('load', 'base-dev', 'collections', 'export', 'probe', 'run', 'sidecars', 'leakcheck',
                'fits', 'gate', 'holdout', 'kaggle')
CONFIG_KINDS = ('base', 'set', 'prereg', 'deviations', 'holdout-open', 'holdout')

BASE_FORMAT = 'xfer-base-v1'
COLLECTION_FORMAT = 'xfer-collection-v1'
DEVIATIONS_FORMAT = 'xfer-deviations-v1'
SEALED = 'sealed'
SEALED_FILES = ('labels.parquet', 'targets.parquet')
LABEL_FILES = SEALED_FILES
FRAME_FILE = 'frame.parquet'
MANIFEST_FILE = 'manifest.json'
EVENTS_DB = 'events.duckdb'
EVENTS_DIR = 'events'
STATIC_DB = 'static.duckdb'
QUERY_ORDER_SQL = "sha256(CAST({column} AS VARCHAR) || ':2026')"

VERDICT_TRANSFER = ('колонки агента без отбора повышают качество базы на {dataset}', 'колонки агента вредят базе',
                    'не различено', 'не решено')
VERDICT_CONTENT = ('прирост несёт содержание колонок агента, а не их число', 'плацебо лучше',
                   'не отличимо от плацебо', 'не решено')
NOT_COMPUTED = 'не вычислен'


class ContractError(RuntimeError):
    """A contract guard refused the operation."""


def require(condition, message):
    if not condition:
        raise ContractError(message)


# ---------------------------------------------------------------- process and output

def isolated():
    """Refuse unless Python runs with -I (downloaded data is read only that way)."""
    require(sys.flags.isolated, 'Run with python -I')


def check_dataset(dataset):
    require(dataset in DATASETS, f'Unknown dataset {dataset!r}')
    return dataset


def dataset_dir(dataset):
    return ROOT/'artifacts'/'xfer'/check_dataset(dataset)


def output_dir(dataset, kind, *parts):
    require(kind in OUTPUT_KINDS, f'Unknown output kind {kind!r}')
    return dataset_dir(dataset).joinpath(kind, *[str(p) for p in parts])


def config_path(dataset, kind):
    require(kind in CONFIG_KINDS, f'Unknown config kind {kind!r}')
    return ROOT/'configs'/'datasets'/f'xfer-{check_dataset(dataset)}-{kind}.json'


def raw_dir(dataset):
    return ROOT/RAW[check_dataset(dataset)]


def new_output(path):
    """Create a new output directory under artifacts/xfer; an existing one is refused."""
    path = Path(path).resolve()
    allowed = (ROOT/'artifacts'/'xfer').resolve()
    require(path != allowed and path.is_relative_to(allowed), f'Outputs must live under {allowed}')
    path.mkdir(parents=True, exist_ok=False)
    return path


def atomic_json(path, value, exist_ok=False):
    path = Path(path)
    require(exist_ok or not path.exists(), f'Refusing to overwrite {path}')
    tmp = path.with_name(f'.{path.name}.tmp-{os.getpid()}')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=False)+'\n',
                   encoding='utf-8', newline='\n')
    os.replace(tmp, path)
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def emit(result, ok=True):
    """One JSON line on stdout; returns the exit code."""
    payload = dict(ok=bool(ok), **result)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, allow_nan=False, default=str)+'\n')
    sys.stdout.flush()
    return 0 if ok else 1


def run_cli(handler, argv=None):
    """Run ``handler(argv) -> dict``; exceptions become a failed JSON line and exit 1."""
    try:
        return emit(handler(argv))
    except Exception as exc:  # noqa: BLE001 - every failure is one JSON line
        return emit(dict(error=f'{type(exc).__name__}: {exc}'[:2000]), ok=False)


def utc_now():
    return _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------- digests and identity

def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def query_order_key(user_id):
    """Python reference of QUERY_ORDER_SQL: lowercase hex sha256 of str(user_id)+':2026'."""
    return hashlib.sha256(f'{int(user_id)}{QUERY_SALT}'.encode('utf-8')).hexdigest()


def cap_queries(users, n):
    """The first n users in (sha256 order key, user_id) order; all when fewer."""
    ordered = sorted({int(u) for u in users}, key=lambda u: (query_order_key(u), u))
    return ordered if n is None else ordered[:n]


def anchor_int(anchor):
    """Integer form of an anchor: the step on T, date.toordinal() on S."""
    if isinstance(anchor, int):
        return anchor
    return _dt.date.fromisoformat(str(anchor)).toordinal()


def anchor_text(anchor):
    return str(anchor) if not isinstance(anchor, _dt.date) else anchor.isoformat()


def adapter(dataset):
    """Import only the requested adapter (the other one stays out of sys.modules)."""
    return importlib.import_module(ADAPTERS[check_dataset(dataset)])


def code_identity(dataset):
    """SHA-256 of every scripts/ module the set's code loads, after importing a fixed list.

    The fixed list (shared modules and the dataset's adapter) makes the key set the
    same from every command. The other dataset's adapter must not be loaded.
    """
    check_dataset(dataset)
    for name in SHARED_MODULES:
        importlib.import_module(name)
    adapter(dataset)
    other = [ADAPTERS[d] for d in DATASETS if d != dataset]
    require(not any(name in sys.modules for name in other),
            f'Other adapter loaded in a {dataset} process: {other}')
    scripts = (ROOT/'scripts').resolve()
    files = {}
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if not path:
            continue
        path = Path(path).resolve()
        if path.suffix == '.py' and path.parent == scripts:
            files[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    return dict(sorted(files.items()))


# ---------------------------------------------------------------- git receipts

def _git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, check=False)


def committed_clean(path):
    """True when ``path`` is tracked by Git and equal to HEAD (worktree and index)."""
    path = Path(path)
    if not path.exists():
        return False
    rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    if _git('ls-files', '--error-unmatch', '--', rel).returncode != 0:
        return False
    return _git('diff', '--quiet', 'HEAD', '--', rel).returncode == 0


def deviations(dataset):
    path = config_path(dataset, 'deviations')
    if not path.exists():
        return []
    data = read_json(path)
    require(data.get('format') == DEVIATIONS_FORMAT and data.get('dataset') == dataset, f'Bad deviations file {path}')
    return list(data.get('records', []))


def _holdout_manifests(dataset):
    root = output_dir(dataset, 'collections')
    if not root.exists():
        return []
    return sorted(p for p in root.glob('holdout-*/'+MANIFEST_FILE))


def holdout_window_open(dataset, purpose):
    """Whether code may read events at or after A_holdout (docs/xfer-design.md, 1.1).

    ``collect-holdout``: committed clean prereg whose base and set SHA match the
    committed base.json and set, no holdout collection yet (unless the latest
    deviation names step collect-holdout and supersedes every existing one) and no
    open receipt. Any other purpose: the committed holdout result receipt.
    """
    check_dataset(dataset)
    if purpose != 'collect-holdout':
        return committed_clean(config_path(dataset, 'holdout'))
    prereg, base, agent_set = (config_path(dataset, k) for k in ('prereg', 'base', 'set'))
    if not all(committed_clean(p) for p in (prereg, base, agent_set)):
        return False
    record = read_json(prereg)
    if record.get('base_sha256') != sha256_file(base) or record.get('set_sha256') != sha256_file(agent_set):
        return False
    if config_path(dataset, 'holdout-open').exists():
        return False
    existing = [p.parent.relative_to(ROOT).as_posix() for p in _holdout_manifests(dataset)]
    if existing:
        records = deviations(dataset)
        if not records or records[-1].get('step') != 'collect-holdout':
            return False
        if not set(existing) <= set(records[-1].get('supersedes', [])):
            return False
        if not committed_clean(config_path(dataset, 'deviations')):
            return False
    return True


def require_window(dataset, purpose):
    require(holdout_window_open(dataset, purpose),
            f'Holdout window closed for {dataset} purpose={purpose!r}')


def holdout_collection_name(anchor, deviation_id=None):
    name = f'holdout-{anchor_text(anchor)}'
    return name if deviation_id is None else f'{name}-{deviation_id}'


def current_holdout_collection(dataset, anchor):
    """The holdout collection in force: the latest deviation's replacement or the original."""
    records = [r for r in deviations(dataset) if r.get('step') == 'collect-holdout']
    name = holdout_collection_name(anchor, records[-1]['id'] if records else None)
    return output_dir(dataset, 'collections', name)


# ---------------------------------------------------------------- events, static, seal

def events_path(dataset):
    """The only builder of the events path: dict(db=..., parts=...)."""
    root = output_dir(dataset, 'load')
    return dict(db=root/EVENTS_DB, parts=root/EVENTS_DIR)


def static_path(dataset):
    return output_dir(dataset, 'load')/STATIC_DB


def write_sealed(collection, writer):
    """Create ``<collection>/sealed``, let ``writer(dir)`` write labels and targets, then seal 0400.

    Returns the SHA-256 of the two files (hashes carry no labels).
    """
    sealed = Path(collection)/SEALED
    sealed.mkdir(mode=0o700, exist_ok=False)
    writer(sealed)
    names = sorted(p.name for p in sealed.iterdir())
    require(names == sorted(SEALED_FILES), f'Sealed directory must hold exactly {SEALED_FILES}, got {names}')
    hashes = {}
    for name in SEALED_FILES:
        path = sealed/name
        hashes[name] = sha256_file(path)
        path.chmod(0o400)
    sealed.chmod(0o500)
    return hashes


def read_sealed(collection, purpose):
    """Paths of the sealed labels and targets after the receipt check.

    ``holdout`` needs the committed open receipt, ``final`` the committed result.
    """
    collection = Path(collection)
    manifest = read_json(collection/MANIFEST_FILE)
    dataset = manifest['dataset']
    require(manifest['role'] == 'holdout', 'Only holdout collections are sealed')
    kind = {'holdout': 'holdout-open', 'final': 'holdout'}.get(purpose)
    require(kind is not None, f'Unknown sealed purpose {purpose!r}')
    require(committed_clean(config_path(dataset, kind)), f'read_sealed({purpose!r}) needs committed {kind} receipt')
    paths = {name: collection/SEALED/name for name in SEALED_FILES}
    for name, path in paths.items():
        require(sha256_file(path) == manifest['sealed'][name], f'Sealed file changed: {path}')
    return dict(labels=paths['labels.parquet'], targets=paths['targets.parquet'])


def write_parquet(frame, path, order_by=None):
    """Write a pandas frame to parquet through DuckDB (pyarrow is not installed)."""
    import duckdb
    con = duckdb.connect()
    try:
        con.register('frame_to_write', frame)
        order = f' ORDER BY {order_by}' if order_by else ''
        target = str(path).replace("'", "''")
        con.execute(f"COPY (SELECT * FROM frame_to_write{order}) TO '{target}' (FORMAT parquet)")
    finally:
        con.close()
    return Path(path)


def read_parquet(path, columns=None):
    """Read a parquet file into pandas through DuckDB."""
    import duckdb
    con = duckdb.connect()
    try:
        cols = ', '.join(f'"{c}"' for c in columns) if columns else '*'
        target = str(path).replace("'", "''")
        return con.execute(f"SELECT {cols} FROM read_parquet('{target}')").df()
    finally:
        con.close()


# ---------------------------------------------------------------- base.json

def make_base(dataset, candidates, features, categorical):
    """base.json body: candidate policy, features (name/formula/missing) and categorical list."""
    check_dataset(dataset)
    names = [f['name'] for f in features]
    require(len(names) == len(set(names)), 'Duplicate base feature names')
    require(all(set(f) == {'name', 'formula', 'missing'} for f in features), 'Features need name/formula/missing')
    require(set(categorical) <= set(names), 'Categorical features must be base features')
    body = dict(format=BASE_FORMAT, dataset=dataset, candidates=candidates, features=list(features),
                categorical=list(categorical))
    return dict(body, digest=canonical_digest(body))


def check_base(base, dataset=None):
    require(base.get('format') == BASE_FORMAT, 'Not an xfer base')
    require(dataset is None or base.get('dataset') == dataset, 'Base of another dataset')
    body = {k: v for k, v in base.items() if k != 'digest'}
    require(canonical_digest(body) == base.get('digest'), 'Base digest mismatch')
    return base


def read_base(path_or_dataset):
    path = config_path(path_or_dataset, 'base') if path_or_dataset in DATASETS else Path(path_or_dataset)
    return check_base(read_json(path))


def base_feature_names(base):
    return [f['name'] for f in base['features']]


# ---------------------------------------------------------------- collections

def collection_name(role, anchor):
    require(role in ROLES, f'Unknown role {role!r}')
    return f'{role}-{anchor_text(anchor)}'


def write_manifest(collection, dataset, role, anchor, counts, base, code, sealed=None, extra=None):
    """Write manifest.json; holdout counts may not carry labels, positives or targets."""
    collection = Path(collection)
    require(role in ROLES, f'Unknown role {role!r}')
    if role == 'holdout':
        forbidden = {'labels', 'positives', 'targets', 'n_targets', 'positive_rows'}
        require(not forbidden & set(counts), f'Holdout manifest may not carry {forbidden & set(counts)}')
        require(sealed is not None, 'Holdout manifest needs sealed hashes')
        require(not any((collection/n).exists() for n in LABEL_FILES), 'Holdout labels outside sealed/')
    files = {}
    for path in sorted(collection.iterdir()):
        if path.is_file() and path.name != MANIFEST_FILE and not path.name.startswith('.'):
            files[path.name] = sha256_file(path)
    require(FRAME_FILE in files, 'Collection needs frame.parquet')
    if role in ('train', 'val'):
        require(all(n in files for n in LABEL_FILES), 'Train/val collections need labels and targets')
    if role in ('kaggle', 'probe'):
        require(not any(n in files for n in LABEL_FILES), f'{role} collections carry no labels')
    manifest = dict(format=COLLECTION_FORMAT, dataset=dataset, role=role, anchor=anchor, counts=counts,
                    files=files, base_digest=base['digest'], code=code, created_utc=utc_now())
    if sealed is not None:
        manifest['sealed'] = sealed
    if extra:
        manifest.update(extra)
    atomic_json(collection/MANIFEST_FILE, manifest)
    return manifest


def read_collection(collection, dataset=None, role=None, base=None, verify=True):
    """Manifest of a collection after format, role, base and file-hash checks (not sealed/)."""
    collection = Path(collection)
    manifest = read_json(collection/MANIFEST_FILE)
    require(manifest.get('format') == COLLECTION_FORMAT, f'Not a collection: {collection}')
    require(dataset is None or manifest['dataset'] == dataset, 'Collection of another dataset')
    require(role is None or manifest['role'] == role, f'Collection role {manifest["role"]} != {role}')
    require(base is None or manifest['base_digest'] == base['digest'], f'Collection {collection} built on another base')
    if verify:
        for name, digest in manifest['files'].items():
            require(sha256_file(collection/name) == digest, f'Collection file changed: {collection/name}')
    return manifest


# ---------------------------------------------------------------- agent sidecars

SIDECAR_FORMAT = 'xfer-sidecar-v1'
SIDECAR_FILE = 'agent.parquet'


def sidecar_dir(dataset, collection):
    """sidecars/<collection name>/ for a collection directory."""
    return output_dir(dataset, 'sidecars', Path(collection).name)


def write_sidecar_manifest(directory, dataset, collection, set_sha256, columns, rows, code):
    """Sidecar = agent.parquet with user_id, item_id and the agent columns in frozen order,
    one row per frame row in frame order (user_id, item_id)."""
    directory = Path(directory)
    manifest = dict(format=SIDECAR_FORMAT, dataset=dataset, collection=Path(collection).name,
                    collection_manifest_sha256=sha256_file(Path(collection)/MANIFEST_FILE),
                    set_sha256=set_sha256, columns=list(columns), rows=int(rows),
                    file_sha256=sha256_file(directory/SIDECAR_FILE), code=code, created_utc=utc_now())
    atomic_json(directory/MANIFEST_FILE, manifest)
    return manifest


def read_sidecar(directory, collection, set_sha256=None):
    directory = Path(directory)
    manifest = read_json(directory/MANIFEST_FILE)
    require(manifest.get('format') == SIDECAR_FORMAT, f'Not a sidecar: {directory}')
    require(manifest['collection'] == Path(collection).name, 'Sidecar of another collection')
    require(manifest['collection_manifest_sha256'] == sha256_file(Path(collection)/MANIFEST_FILE),
            'Sidecar built on another collection manifest')
    require(set_sha256 is None or manifest['set_sha256'] == set_sha256, 'Sidecar of another agent set')
    require(sha256_file(directory/SIDECAR_FILE) == manifest['file_sha256'], 'Sidecar file changed')
    return manifest


# ---------------------------------------------------------------- prereg guard

def latest_code(dataset, prereg):
    records = [r for r in deviations(dataset) if r.get('code')]
    return records[-1]['code'] if records else prereg['code']


def require_prereg(dataset, check_code=True):
    """Committed prereg whose base, set and code match the tree (or the last deviation)."""
    path = config_path(dataset, 'prereg')
    require(committed_clean(path), f'Prereg {path} is not committed clean')
    prereg = read_json(path)
    for kind in ('base', 'set'):
        p = config_path(dataset, kind)
        require(committed_clean(p) and sha256_file(p) == prereg[f'{kind}_sha256'], f'{kind} differs from prereg')
    if check_code:
        require(code_identity(dataset) == latest_code(dataset, prereg), 'Code differs from prereg and deviations')
    return prereg


# ---------------------------------------------------------------- placebo permutation

def permutation(seed, anchor, chunk, n):
    """perm for BApl: default_rng([20261021, seed, anchor_int, chunk]).permutation(n)."""
    import numpy as np
    return np.random.default_rng([PERMUTATION_SEED, int(seed), anchor_int(anchor), int(chunk)]).permutation(int(n))


# ---------------------------------------------------------------- bootstrap and reading

def bootstrap(reference, alternative, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    """Paired bootstrap of mean(alternative - reference) over queries sorted by user_id.

    ``reference`` and ``alternative`` map user_id -> per-query metric on identical
    queries. A fresh default_rng(seed) per call; linear quantiles 2.5 and 97.5.
    """
    import numpy as np
    require(set(reference) == set(alternative), 'Paired arms need identical queries')
    users = sorted(reference)
    require(users, 'No queries')
    diff = np.asarray([alternative[u]-reference[u] for u in users], dtype=float)
    rng = np.random.default_rng(seed)
    n = len(users)
    means = np.empty(draws)
    for i in range(draws):
        means[i] = diff[rng.integers(0, n, size=n)].mean()
    lower, upper = (float(x) for x in np.quantile(means, [0.025, 0.975], method='linear'))
    return dict(queries=n, draws=draws, seed=seed, mean=float(diff.mean()), ci=[lower, upper],
                covers_zero=bool(lower <= 0 <= upper))


def _read(cis, labels):
    if all(ci[0] > 0 for ci in cis):
        return labels[0]
    if all(ci[1] < 0 for ci in cis):
        return labels[1]
    if all(ci[0] <= 0 <= ci[1] for ci in cis):
        return labels[2]
    return labels[3]


def verdict_transfer(cis, dataset_label):
    """Verdict 1 from the per-seed CIs of D = BA - B."""
    require(len(cis) == len(SEEDS), 'One CI per seed')
    return _read(cis, (VERDICT_TRANSFER[0].format(dataset=dataset_label),) + VERDICT_TRANSFER[1:])


def verdict_content(cis):
    """Verdict 2 from the per-seed CIs of P = BA - BApl."""
    require(len(cis) == len(SEEDS), 'One CI per seed')
    return _read(cis, VERDICT_CONTENT)


def kaggle_reading(ba, b):
    """H&M rule on private scores (lists, one per seed); descriptive only."""
    if len(ba) < 2 or len(b) < 2:
        return 'один seed — не читается'
    gap = sum(ba)/len(ba) - sum(b)/len(b)
    spread = max(max(ba)-min(ba), max(b)-min(b))
    if min(ba) > max(b) and gap > spread:
        return 'BA выше B на обоих зёрнах'
    if max(ba) < min(b) and -gap > spread:
        return 'BA ниже B'
    return 'не различено'


def gate_arms(status):
    """Arms opened by gate 1 status: dict(B=bool, BA=bool, BApl=bool)."""
    if not status.get('B', False):
        return [POP]
    if not (status.get('BA', False) and status.get('BApl', False)):
        return [POP, 'B']
    return [POP, 'B', 'BA', 'BApl']
