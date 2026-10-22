"""Shared contract code of the OTTO port (docs/otto-design.md).

This module fixes what otto_data, otto_agent and otto_model share (contract §11,
row ``otto_common.py``): paths and ``events_path``, the holdout barrier and its
receipts, ``write_sealed``/``read_sealed``, the collection and base formats, the
pooled metric, ``bootstrap_ratio``, ``code_identity``, the reading rules and the
level thresholds. Everything else (load, folds and truncation, candidates,
sandbox, fits) belongs to the other modules. It imports nothing heavy at module
level and has no side effects on import. Every contract number it owns sits in
the constants block below.

Formats fixed here:

``artifacts/otto/load/events/d=<d>/`` and ``artifacts/otto/load/test/d=<d>/``
    Day partitions from S5 (§2.5): train d <= -1, Kaggle prefixes d >= 0. Rows
    carry EVENT_COLUMNS (``session, aid, ts, type, seq``; ``ts`` in seconds,
    ``seq`` the 1-based index in the source array). Only ``events_path(d)``
    builds a partition path; readers get paths through ``partition_paths``,
    which applies the barrier.
``artifacts/otto/collections/<role>-F<k>/`` (§11)
    ``prefix/`` (prefix partitions, EVENT_COLUMNS), ``frame.parquet``
    (``session, aid``, base features, source ranks; order ``session, aid``),
    ``labels.parquet`` (LABEL_COLUMNS) or, for the holdout, ``sealed/labels.parquet``,
    ``manifest.json`` (no label counts for the holdout) and, for ``holdout-F4``,
    ``population.json`` written by the power gate after the manifest.
``configs/datasets/otto-<kind>.json``
    base, set, prereg, deviations and the receipts holdout-open, holdout,
    holdout-open-2, holdout-2.
``type``
    Labels and ranked lists use the names in TYPES; an integer column is read as
    TYPE_CODES (0 clicks, 1 carts, 2 orders).

Parquet goes through DuckDB (``write_parquet``/``read_parquet``): pyarrow is not
installed.
"""
from __future__ import annotations

from decimal import Decimal
import math
import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.xfer_common import (  # noqa: E402  (pure helpers, §11)
    ContractError, atomic_json, canonical_digest, emit, isolated, kaggle_reading, read_json, read_parquet,
    require, run_cli, sha256_file, utc_now, write_parquet)

# =============================================================================== constants
# Every contract number and name owned by otto_common. The contract is
# docs/otto-design.md; section numbers refer to it.

# ---- imports allowed from older modules (§11: "Точный список фиксирует otto_common.py").
# new_output of xfer_common is not on the list: it is bound to artifacts/xfer; use ours.
ALLOWED_IMPORTS = {
    'scripts.xfer_common': ('ContractError', 'isolated', 'atomic_json', 'read_json', 'sha256_file',
                            'canonical_digest', 'require', 'utc_now', 'kaggle_reading', 'emit', 'run_cli',
                            'write_parquet', 'read_parquet'),
    'scripts.xfer_agent': ('log2_bucket', 'redact', 'FORBIDDEN', 'NONDETERMINISTIC', 'NUMBER'),
    'scripts.hm_agent_loop': ('ask_llm', 'parse_reply', 'clean_error'),
}
CODE_MODULES = ('scripts.otto_common', 'scripts.otto_data', 'scripts.otto_agent', 'scripts.otto_model')

# ---- paths
ARTIFACTS = ('artifacts', 'otto')
RAW_DIR = 'data/raw-otto-kaggle'
VERIFY_FILE = 'otto-verify.json'
CONFIG_PREFIX = 'otto'
CONFIG_KINDS = ('base', 'set', 'prereg', 'deviations', 'holdout-open', 'holdout', 'holdout-open-2', 'holdout-2')
OUTPUT_KINDS = ('load', 'base-dev', 'collections', 'export', 'calibration', 'probe', 'run', 'tables', 'sidecars',
                'leakcheck', 'smoke', 'fits', 'contrast', 'gate', 'holdout', 'kaggle')
_LOAD_TREES = {'train': 'events', 'test': 'test'}     # private: reached only through events_path/partition_*
_PARTITION_PREFIX = 'd='

# ---- time (§2.1, §2.5)
DAY = 86400
WEEK_DAYS = 7
TRAIN_WEEKS = (1, 2, 3, 4)
KAGGLE_WEEK = 5
BARRIER_DAY = -7                      # first day of W4; before prereg only d < BARRIER_DAY is read
PARTITION_SQL = 'CAST(floor(({ts} - {s5}) / 86400.0) AS BIGINT)'
TRAIN_PARTITION_SQL = 'LEAST(' + PARTITION_SQL + ', -1)'   # a train event with ts = S5 goes to d = -1 (§1)

# ---- folds, roles, series, seeds (§2.4)
FOLD_ROLE = {2: 'train', 3: 'val', 4: 'holdout', 5: 'kaggle'}
ROLES = ('train', 'val', 'probe', 'holdout', 'kaggle')
ROLE_FOLD = {'train': 2, 'val': 3, 'probe': 3, 'holdout': 4, 'kaggle': 5}
SEEDS = (2026, 2027)
STAGE_SEEDS = {1: (2026,), 2: (2026, 2027)}
ARMS = ('B', 'BA', 'BApl')
POP = 'Pop'
SERIES = {
    'dev': dict(train=2, eval=3, arms={1: (POP, 'B', 'BA', 'BApl')}),
    'holdout': dict(train=3, eval=4, arms={1: (POP, 'B', 'BA', 'BApl'), 2: ('B', 'BA', 'BApl')}),
    'final': dict(train=4, eval=5, arms={1: ('B', 'BA'), 2: ('B', 'BA')}),
}

# ---- sha256 orders (§2.4, §5.4); hex in lower case, ties by session
ORDER_SALT = ':2026'
PROBE_SALT = ':probe:2026'
ORDER_SQL = "sha256(CAST({column} AS VARCHAR) || ':2026')"
PROBE_ORDER_SQL = "sha256(CAST({column} AS VARCHAR) || ':probe:2026')"

# ---- sizes written before data (§2.4, §5.4, §6, §8)
DEV_POPULATION = 300_000
PROBE_POOL = 20_000
HOLDOUT_POPULATION_CAP = 1_000_000
POWER_HALF_WIDTH = 0.0015
N_T = 50_000
NEGATIVES = 30
SCORE_BATCH = 50_000
SIDECAR_BATCH = 50_000

# ---- metric (§3)
TYPES = ('clicks', 'carts', 'orders')
TYPE_CODES = {'clicks': 0, 'carts': 1, 'orders': 2}
WEIGHTS = {'clicks': 0.10, 'carts': 0.30, 'orders': 0.60}
TOP_K = 20
SUBMISSION_HEADER = 'session_type,labels'
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 2026
CI_QUANTILES = (0.025, 0.975)

# ---- formats (§4, §11)
BASE_FORMAT = 'otto-base-v1'
COLLECTION_FORMAT = 'otto-collection-v1'
DEVIATIONS_FORMAT = 'otto-deviations-v1'
POPULATION_FORMAT = 'otto-population-v1'
EVENT_COLUMNS = ('session', 'aid', 'ts', 'type', 'seq')
LABEL_COLUMNS = ('session', 'type', 'aid')
RANKED_COLUMNS = ('session', 'type', 'aid', 'rank')
FRAME_KEYS = ('session', 'aid')
FRAME_FILE = 'frame.parquet'
LABELS_FILE = 'labels.parquet'
MANIFEST_FILE = 'manifest.json'
POPULATION_FILE = 'population.json'
PREFIX_DIR = 'prefix'
_SEALED = 'sealed'                                   # private: reached only through write_sealed/read_sealed
_SEALED_FILES = (LABELS_FILE,)
HOLDOUT_FORBIDDEN_WORDS = ('label', 'positive', 'target', 'suffix', 'hit', 'recall')   # holdout counts/extra keys
HOLDOUT_FILES = (FRAME_FILE, PREFIX_DIR+'/')          # allowlist of a holdout collection outside sealed/

# ---- receipts (§2.5): minimal schemas checked whenever a receipt opens something
HOLDOUT_OPEN_FORMAT = 'otto-holdout-open-v1'
HOLDOUT_OPEN_2_FORMAT = 'otto-holdout-open-2-v1'

# ---- barrier purposes (§2.5)
COLLECT_HOLDOUT = 'collect-holdout'
SEALED_PURPOSES = {'holdout': ('holdout-open',), 'holdout-2': ('holdout-open-2', 'holdout'), 'final': ('holdout',)}
_PRIVATE = ('_SEALED', '_SEALED_FILES', '_LOAD_TREES', '_PARTITION_PREFIX')

# ---- reading (§10)
VERDICT_TRANSFER = ('всё, что предложил агент (с dev-сигналом), без отбора координатором повышает качество базы на OTTO',
                    'вредит', 'не различено', 'не решено')
VERDICT_CONTENT = ('прирост колонок агента несёт их содержание', 'плацебо лучше', 'не отличимо от плацебо',
                   'не решено')
ONE_SEED = 'не решено (одно зерно)'
STAGE1_NOTE = 'на зерне 2026 CI(D) выше нуля; вердикт по правилу — после этапа 2'
NOT_COMPUTED = 'не вычислен'
LEVEL_THRESHOLDS = (            # (upper bound exclusive, reading) on private BA
    ('0.575', 'ниже публичного ноутбука на правилах'),
    ('0.580', 'на уровне публичного ноутбука на правилах'),
    ('0.590', 'пайплайн работает: уровень серебра по чужим отчётам'),
    (None, 'весомо: между серебром и 3-м местом по чужим отчётам'),
)
LEVEL_REFERENCES = dict(public_notebook=0.575, silver=0.583, third_place=0.6038, teams=2580)  # not verified
LEVEL_ONE_SEED = 'один seed'

_SCRIPTS = Path(__file__).resolve().parent


# =============================================================================== paths and outputs

def artifacts_dir():
    return ROOT.joinpath(*ARTIFACTS)


def output_dir(kind, *parts):
    """artifacts/otto/<kind>/<parts>; the load partition trees are refused (events_path, partition_* only)."""
    require(kind in OUTPUT_KINDS, f'Unknown output kind {kind!r}')
    path = artifacts_dir().joinpath(kind, *[str(p) for p in parts])
    trees = [_load_tree(source).resolve() for source in _LOAD_TREES]
    require(not any(path.resolve().is_relative_to(tree) for tree in trees),
            'Partition trees are reached only through events_path and partition_paths/partition_glob')
    return path


def _load_tree(source):
    return artifacts_dir()/'load'/_LOAD_TREES[source]


def config_path(kind):
    require(kind in CONFIG_KINDS, f'Unknown config kind {kind!r}')
    return ROOT/'configs'/'datasets'/f'{CONFIG_PREFIX}-{kind}.json'


def raw_dir():
    return ROOT/RAW_DIR


def verify_path():
    """The load receipt otto-verify.json next to the raw files (not in Git, §1)."""
    return raw_dir()/VERIFY_FILE


def new_output(path):
    """Create a new output directory under artifacts/otto; an existing one is refused."""
    path = Path(path).resolve()
    allowed = artifacts_dir().resolve()
    require(path != allowed and path.is_relative_to(allowed), f'Outputs must live under {allowed}')
    path.mkdir(parents=True, exist_ok=False)
    return path


# =============================================================================== weeks and day partitions

def partition_day(ts, s5, source='train'):
    """Partition key d = floor((ts - S5) / 86400); train is min(d, -1), test must be d >= 0 (§2.5)."""
    require(source in _LOAD_TREES, f'Unknown source {source!r}')
    d = (int(ts) - int(s5)) // DAY          # Python // floors toward minus infinity
    if source == 'train':
        return min(d, -1)
    require(d >= 0, f'Test event before S5: ts={ts}, S5={s5}')
    return d


def partition_sql(ts, s5, source='train'):
    """DuckDB twin of partition_day for a ts expression and an integer S5.

    For ``test`` the SQL does not clamp; ``load`` itself checks d >= 0 for test rows.
    """
    require(source in _LOAD_TREES, f'Unknown source {source!r}')
    template = TRAIN_PARTITION_SQL if source == 'train' else PARTITION_SQL
    return template.format(ts=ts, s5=int(s5))


def week_of_day(d):
    """Week of a partition: W1..W4 for train (d <= -29 in W1), 5 for every test day."""
    return min(KAGGLE_WEEK, max(1, KAGGLE_WEEK + int(d)//WEEK_DAYS))


def week_first_day(k):
    """First partition of W_k: -7·(5-k). H_k is exactly the partitions d < week_first_day(k)."""
    require(k in TRAIN_WEEKS or k == KAGGLE_WEEK, f'Unknown week {k!r}')
    return -WEEK_DAYS*(KAGGLE_WEEK-k)


def week_days(k):
    """Inclusive (lo, hi) partition range of W_k; lo is None for W1, hi is None for W5."""
    first = week_first_day(k)
    lo = None if k == 1 else first
    hi = None if k == KAGGLE_WEEK else first+WEEK_DAYS-1
    return lo, hi


def week_start(k, s5):
    """start(W_k) = S5 - (5-k)·7·86400 in seconds."""
    return int(s5)+week_first_day(k)*DAY


def week_end(k, s5):
    """end(W_k) = start(W_{k+1}); W5 nominally ends 7 days after S5."""
    return week_start(k, s5)+WEEK_DAYS*DAY


# =============================================================================== git receipts and the barrier

def _git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, check=False)


def committed_clean(path):
    """True when the file at ``path`` equals its blob in HEAD (``git hash-object`` vs ``HEAD:<rel>``)."""
    path = Path(path)
    if not path.is_file():
        return False
    rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    head = _git('rev-parse', '--verify', '--quiet', f'HEAD:{rel}')
    if head.returncode != 0:
        return False
    work = _git('hash-object', '--', rel)
    return work.returncode == 0 and work.stdout.strip() == head.stdout.strip()


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def check_receipt(kind, data):
    """Minimal schema of the receipts that open something (§2.5); returns data or refuses."""
    if kind == 'holdout-open':
        require(data.get('format') == HOLDOUT_OPEN_FORMAT, f'holdout-open: format must be {HOLDOUT_OPEN_FORMAT}')
        require(isinstance(data.get('quote'), str) and data['quote'].strip(), 'holdout-open: empty owner quote')
        gate1 = data.get('gate1')
        require(isinstance(gate1, dict) and isinstance(gate1.get('ok'), bool), 'holdout-open: gate1.ok missing')
    elif kind == 'holdout-open-2':
        require(data.get('format') == HOLDOUT_OPEN_2_FORMAT, f'holdout-open-2: format must be {HOLDOUT_OPEN_2_FORMAT}')
        scores = data.get('scores')
        require(isinstance(scores, dict) and scores and all(_hex64(v) for v in scores.values()),
                'holdout-open-2: scores must map files to SHA-256')
    return data


def receipt(kind):
    """A committed clean config or receipt, read and schema-checked; refuses otherwise."""
    path = config_path(kind)
    require(committed_clean(path), f'{path.name} is not committed clean')
    return check_receipt(kind, read_json(path))


def _receipts_ok(kinds):
    """All receipts committed clean (False otherwise); a committed malformed receipt refuses."""
    if not all(committed_clean(config_path(kind)) for kind in kinds):
        return False
    for kind in kinds:
        receipt(kind)
    return True


def deviations():
    """Records of otto-deviations.json; an existing file must be committed clean."""
    if not config_path('deviations').exists():
        return []
    data = receipt('deviations')
    require(data.get('format') == DEVIATIONS_FORMAT, 'Bad deviations file')
    return list(data.get('records', []))


def holdout_collection_name(deviation_id=None):
    name = collection_name('holdout')
    return name if deviation_id is None else f'{name}-{deviation_id}'


def current_holdout_collection():
    """The holdout collection in force: the latest collect-holdout deviation's rebuild or the original."""
    records = [r for r in deviations() if r.get('step') == COLLECT_HOLDOUT]
    return output_dir('collections', holdout_collection_name(records[-1]['id'] if records else None))


def _holdout_dirs():
    """Names of every holdout-F4* directory, with or without a manifest."""
    root = output_dir('collections')
    name = collection_name('holdout')
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p.name == name or p.name.startswith(name+'-')))


def holdout_window_open(purpose):
    """Whether the holdout window is open for ``purpose`` (§2.5; xfer-design §1.1).

    ``collect-holdout``: committed clean prereg whose base and set SHA match the
    committed base and set, no holdout-F4* directory yet (unless the latest
    deviation names step collect-holdout and supersedes every existing one by
    name) and no open receipt. ``holdout``: committed open receipt. ``holdout-2``:
    committed stage-2 open receipt and committed stage-1 result. ``final``:
    committed result receipt otto-holdout.json.
    """
    if purpose in SEALED_PURPOSES:
        return _receipts_ok(SEALED_PURPOSES[purpose])
    require(purpose == COLLECT_HOLDOUT, f'Unknown holdout purpose {purpose!r}')
    prereg, base, agent_set = (config_path(k) for k in ('prereg', 'base', 'set'))
    if not all(committed_clean(p) for p in (prereg, base, agent_set)):
        return False
    record = read_json(prereg)
    if record.get('base_sha256') != sha256_file(base) or record.get('set_sha256') != sha256_file(agent_set):
        return False
    if config_path('holdout-open').exists():
        return False
    existing = _holdout_dirs()
    if existing:
        records = deviations()
        if not records or records[-1].get('step') != COLLECT_HOLDOUT:
            return False
        if not set(existing) <= set(records[-1].get('supersedes', [])):
            return False
    return True


def require_window(purpose):
    require(holdout_window_open(purpose), f'Holdout window closed for purpose={purpose!r}')


def partition_open(d, purpose):
    """Barrier on one day partition (§2.5).

    d < -7 (H_4, folds F2 and F3): always. W4 (d in [-7, -1]): ``collect-holdout``
    with its window open, or ``final`` with the result receipt. Test (d >= 0):
    ``final`` with the result receipt only. Any other purpose sees only d < -7.
    """
    d = int(d)
    if d < BARRIER_DAY:
        return True
    if d < 0 and purpose == COLLECT_HOLDOUT:
        return holdout_window_open(COLLECT_HOLDOUT)
    if purpose == 'final':
        return holdout_window_open('final')
    return False


def events_path(d):
    """The only builder of a day-partition path: events/d=<d> for d < 0, test/d=<d> for d >= 0.

    No barrier: only ``load`` (writing) may call it; readers use partition_paths/partition_glob.
    """
    d = int(d)
    return _load_tree('train' if d < 0 else 'test')/f'{_PARTITION_PREFIX}{d}'


def existing_days(source=None):
    """Partition days present on disk (directory names only, no data read), ascending."""
    sources = list(_LOAD_TREES) if source is None else [source]
    days = []
    for name in sources:
        root = _load_tree(name)
        if root.exists():
            days += [int(p.name[len(_PARTITION_PREFIX):]) for p in root.iterdir()
                     if p.is_dir() and p.name.startswith(_PARTITION_PREFIX)]
    return sorted(days)


def partition_paths(days, purpose):
    """Directories of the requested day partitions after the barrier; one closed day refuses all."""
    days = [int(d) for d in days]
    closed = [d for d in days if not partition_open(d, purpose)]
    require(not closed, f'Partitions closed for purpose={purpose!r}: d={closed[:5]}')
    return [events_path(d) for d in days]


def partition_glob(days, purpose):
    """read_parquet globs ``<partition>/*.parquet`` of the requested days after the barrier."""
    return [str(path/'*.parquet') for path in partition_paths(days, purpose)]


# =============================================================================== sealed labels

def write_sealed(collection, writer):
    """Create ``<collection>/sealed``, let ``writer(dir)`` write labels.parquet, then seal 0400.

    Returns the SHA-256 of the sealed file (hashes carry no labels).
    """
    sealed = Path(collection)/_SEALED
    sealed.mkdir(mode=0o700, exist_ok=False)
    writer(sealed)
    names = sorted(p.name for p in sealed.iterdir())
    require(names == sorted(_SEALED_FILES), f'Sealed directory must hold exactly {_SEALED_FILES}, got {names}')
    hashes = {}
    for name in _SEALED_FILES:
        path = sealed/name
        hashes[name] = sha256_file(path)
        path.chmod(0o400)
    sealed.chmod(0o500)
    return hashes


def read_sealed(collection, purpose):
    """Path of the sealed holdout labels after the receipt check (§2.5).

    ``holdout``: committed open receipt; ``holdout-2``: committed stage-2 open
    receipt and committed stage-1 result; ``final``: committed result receipt.
    """
    require(purpose in SEALED_PURPOSES, f'Unknown sealed purpose {purpose!r}')
    collection = Path(collection)
    manifest = read_json(collection/MANIFEST_FILE)
    require(manifest.get('format') == COLLECTION_FORMAT and manifest.get('role') == 'holdout',
            'Only holdout collections are sealed')
    for kind in SEALED_PURPOSES[purpose]:
        require(committed_clean(config_path(kind)), f'read_sealed({purpose!r}) needs committed {kind} receipt')
        receipt(kind)
    paths = {name: collection/_SEALED/name for name in _SEALED_FILES}
    for name, path in paths.items():
        require(sha256_file(path) == manifest['sealed'][name], f'Sealed file changed: {path}')
    return dict(labels=paths[LABELS_FILE])


# =============================================================================== base

def make_base(candidates, features, categorical=()):
    """otto-base-v1: candidate policy, features (name/formula/missing), empty categorical list (§4)."""
    names = [f['name'] for f in features]
    require(len(names) == len(set(names)), 'Duplicate base feature names')
    require(all(set(f) == {'name', 'formula', 'missing'} for f in features), 'Features need name/formula/missing')
    require(not any(n.startswith('ag_') for n in names), 'ag_* names belong to the agent')
    require(list(categorical) == [], 'The OTTO base has no categorical features (§4)')
    body = dict(format=BASE_FORMAT, candidates=candidates, features=list(features), categorical=[])
    return dict(body, digest=canonical_digest(body))


def check_base(base):
    require(base.get('format') == BASE_FORMAT, 'Not an OTTO base')
    body = {k: v for k, v in base.items() if k != 'digest'}
    require(canonical_digest(body) == base.get('digest'), 'Base digest mismatch')
    return base


def read_base(path=None):
    return check_base(read_json(config_path('base') if path is None else path))


def base_feature_names(base):
    return [f['name'] for f in base['features']]


# =============================================================================== collections

def collection_name(role, fold=None):
    require(role in ROLES, f'Unknown role {role!r}')
    fold = ROLE_FOLD[role] if fold is None else int(fold)
    require(ROLE_FOLD[role] == fold, f'Role {role} lives on F{ROLE_FOLD[role]}, not F{fold}')
    return f'{role}-F{fold}'


def collection_dir(role, fold=None):
    if role == 'holdout':
        require(fold in (None, ROLE_FOLD['holdout']), 'The holdout lives on F4')
        return current_holdout_collection()
    return output_dir('collections', collection_name(role, fold))


def _collection_files(collection):
    """SHA-256 of every file under a collection except manifest, sealed/, population.json and dot files."""
    collection = Path(collection)
    files = {}
    for path in sorted(collection.rglob('*')):
        rel = path.relative_to(collection)
        if not path.is_file() or rel.parts[0] in (_SEALED, MANIFEST_FILE, POPULATION_FILE):
            continue
        if any(part.startswith('.') for part in rel.parts):
            continue
        files[rel.as_posix()] = sha256_file(path)
    return files


def _keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield str(key)
            yield from _keys(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            yield from _keys(inner)


def write_manifest(collection, role, counts, base, code, sealed=None, extra=None):
    """Write manifest.json of a collection (§11); the holdout carries no label counts."""
    collection = Path(collection)
    name = collection_name(role)
    fold = ROLE_FOLD[role]
    require(collection.name == name or collection.name.startswith(f'{name}-'),
            f'Collection directory {collection.name} does not match {name}')
    if role == 'holdout':
        keys = list(_keys(counts)) + list(_keys(extra or {}))
        bad = sorted(k for k in keys if any(w in k.lower() for w in HOLDOUT_FORBIDDEN_WORDS))
        require(not bad, f'Holdout manifest may not carry {bad}')
        require(sealed is not None and sorted(sealed) == sorted(_SEALED_FILES), 'Holdout manifest needs sealed hashes')
        sealed_dir = collection/_SEALED
        require(sealed_dir.is_dir() and sorted(p.name for p in sealed_dir.iterdir()) == sorted(_SEALED_FILES),
                f'Holdout {_SEALED}/ must hold exactly {_SEALED_FILES}')
        for name in _SEALED_FILES:
            require(sha256_file(sealed_dir/name) == sealed[name], f'Sealed hash does not match {name}')
        outside = sorted(rel for rel in (p.relative_to(collection).as_posix() for p in collection.rglob('*')
                                         if p.is_file() and p.relative_to(collection).parts[0] != _SEALED)
                         if rel != FRAME_FILE and not rel.startswith(PREFIX_DIR+'/'))
        require(not outside, f'Holdout collection may hold only {HOLDOUT_FILES} besides {_SEALED}/: {outside[:5]}')
    else:
        require(sealed is None, f'{role} collections are not sealed')
    files = _collection_files(collection)
    require(FRAME_FILE in files, 'Collection needs frame.parquet')
    if role in ('train', 'val', 'holdout'):
        require(any(f.startswith(f'{PREFIX_DIR}/') for f in files), f'{role} collection needs {PREFIX_DIR}/')
    if role in ('train', 'val', 'probe'):
        require(LABELS_FILE in files, f'{role} collection needs {LABELS_FILE}')
    if role == 'kaggle':
        require(LABELS_FILE not in files, 'kaggle collection carries no labels')
    manifest = dict(format=COLLECTION_FORMAT, role=role, fold=fold, counts=counts, files=files,
                    base_digest=base['digest'], code=code, created_utc=utc_now())
    if sealed is not None:
        manifest['sealed'] = sealed
    if extra:
        require(not set(extra) & set(manifest), 'extra may not override manifest fields')
        manifest.update(extra)
    atomic_json(collection/MANIFEST_FILE, manifest)
    return manifest


def read_collection(collection, role=None, base=None, verify=True):
    """Manifest of a collection after format, role, base and file-hash checks (not sealed/)."""
    collection = Path(collection)
    manifest = read_json(collection/MANIFEST_FILE)
    require(manifest.get('format') == COLLECTION_FORMAT, f'Not an OTTO collection: {collection}')
    require(role is None or manifest['role'] == role, f'Collection role {manifest["role"]} != {role}')
    require(base is None or manifest['base_digest'] == base['digest'], f'Collection {collection} built on another base')
    if verify:
        for name, digest in manifest['files'].items():
            require(sha256_file(collection/name) == digest, f'Collection file changed: {collection/name}')
    return manifest


def write_population(collection, sessions, rule):
    """population.json: the evaluation population of a collection, sessions ascending (§8, §11)."""
    collection = Path(collection)
    require((collection/MANIFEST_FILE).exists(), 'population.json follows the collection manifest')
    values = [int(s) for s in sessions]
    require(values, 'Empty population')
    ordered = sorted(set(values))
    require(len(ordered) == len(values), 'Duplicate sessions in population')
    body = dict(format=POPULATION_FORMAT, collection=collection.name, n=len(ordered), rule=rule, sessions=ordered)
    atomic_json(collection/POPULATION_FILE, dict(body, digest=canonical_digest(body)))
    return body


def read_population(collection, expected_digest=None):
    """Sessions of population.json; ``expected_digest`` (e.g. from a gate report) must match when given."""
    data = read_json(Path(collection)/POPULATION_FILE)
    require(data.get('format') == POPULATION_FORMAT, 'Not a population file')
    body = {k: v for k, v in data.items() if k != 'digest'}
    require(canonical_digest(body) == data.get('digest'), 'Population digest mismatch')
    require(expected_digest is None or data['digest'] == expected_digest, 'Population is not the expected one')
    require(data['collection'] == Path(collection).name, 'Population of another collection')
    return data['sessions']


# =============================================================================== orders

def order_key(session):
    """Python twin of ORDER_SQL: lowercase hex sha256 of str(session)+':2026'."""
    import hashlib
    return hashlib.sha256(f'{int(session)}{ORDER_SALT}'.encode('utf-8')).hexdigest()


def probe_key(session):
    """Python twin of PROBE_ORDER_SQL."""
    import hashlib
    return hashlib.sha256(f'{int(session)}{PROBE_SALT}'.encode('utf-8')).hexdigest()


def first_in_order(sessions, n, key=order_key):
    """The first n sessions in (key, session) order; all of them when n is None or larger."""
    ordered = sorted({int(s) for s in sessions}, key=lambda s: (key(s), s))
    return ordered if n is None else ordered[:n]


# =============================================================================== code identity and prereg

def _module_target(name, scripts_dir):
    """(files, found) for a dotted ``scripts.*`` name: the module file plus package __init__ files."""
    parts = name.split('.')[1:]
    files = []
    for i in range(1, len(parts)):
        init = scripts_dir.joinpath(*parts[:i])/'__init__.py'
        if init.is_file():
            files.append(init)
    if not parts:
        return files, True                                   # the namespace package scripts itself
    base = scripts_dir.joinpath(*parts)
    if base.with_suffix('.py').is_file():
        return files+[base.with_suffix('.py')], True
    if (base/'__init__.py').is_file():
        return files+[base/'__init__.py'], True
    return files, base.is_dir()


def _static_imports(path, module, scripts_dir):
    """Dotted scripts.* names a module imports anywhere in its AST (absolute, relative, import_module)."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    package = module.split('.') if Path(path).name == '__init__.py' else module.split('.')[:-1]
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split('.')[0] == 'scripts']
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package)-(node.level-1)] if node.level-1 <= len(package) else []
                target = base+(node.module.split('.') if node.module else [])
            else:
                target = node.module.split('.')
            if not target or target[0] != 'scripts':
                continue
            found.append('.'.join(target))
            for alias in node.names:
                candidate = '.'.join(target+[alias.name])
                files, ok = _module_target(candidate, scripts_dir)
                if ok or target == ['scripts']:          # from scripts import x: x must be a module
                    found.append(candidate)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            fname = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ''
            arg = node.args[0].value
            if fname in ('import_module', '__import__') and isinstance(arg, str) and arg.split('.')[0] == 'scripts':
                found.append(arg)
    return found


def code_identity(strict=False):
    """SHA-256 of the static closure of scripts.* imports from CODE_MODULES (§7).

    The closure is read from the source (AST: absolute and relative imports,
    importlib.import_module and __import__ with a literal name, subpackages of
    scripts/), so it does not depend on what the process has imported. Returns
    dict(files={'scripts/....py': sha256}, missing=[dotted names not found]).
    ``strict=True`` (prereg, require_prereg) refuses when anything is missing.
    """
    scripts_dir = _SCRIPTS
    files, missing, seen = {}, set(), set()
    queue = list(CODE_MODULES)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        targets, ok = _module_target(name, scripts_dir)
        if not ok:
            missing.add(name)
        for path in targets:
            rel = path.relative_to(scripts_dir.parent)
            key = rel.as_posix()
            if key in files:
                continue
            files[key] = sha256_file(path)
            dotted = '.'.join(rel.with_suffix('').parts)
            dotted = dotted[:-len('.__init__')] if dotted.endswith('.__init__') else dotted
            queue += _static_imports(path, dotted, scripts_dir)
    result = dict(files=dict(sorted(files.items())), missing=sorted(missing))
    require(not (strict and missing), f'Code modules missing: {result["missing"]}')
    return result


def latest_code(prereg):
    records = [r for r in deviations() if r.get('code')]
    return records[-1]['code'] if records else prereg['code']


def require_prereg(check_code=True):
    """Committed prereg whose base, set and code match the tree (or the last deviation), §7."""
    prereg = receipt('prereg')
    for kind in ('base', 'set'):
        path = config_path(kind)
        require(committed_clean(path) and sha256_file(path) == prereg[f'{kind}_sha256'], f'{kind} differs from prereg')
    if check_code:
        require(code_identity(strict=True)['files'] == latest_code(prereg), 'Code differs from prereg and deviations')
    return prereg


# =============================================================================== metric (§3)

def _view(con, name, value, columns):
    """A DuckDB view ``name`` with ``columns`` over a pandas frame or a parquet path."""
    if isinstance(value, (str, Path)):
        source = "read_parquet('{}')".format(str(value).replace("'", "''"))
    else:
        missing = [c for c in columns if c not in value.columns]
        require(not missing, f'{name} lacks columns {missing}')
        con.register(f'{name}_input', value)
        source = f'{name}_input'
    con.execute(f'CREATE TEMP VIEW {name}_raw AS SELECT {", ".join(columns)} FROM {source}')
    kinds = {row[0]: row[1] for row in con.execute(f'DESCRIBE {name}_raw').fetchall()}
    names = ', '.join(f"'{t}'" for t in TYPES)
    if kinds['type'] in ('TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT', 'UTINYINT', 'USMALLINT', 'UINTEGER', 'UBIGINT'):
        # integer codes TYPE_CODES: 0 clicks, 1 carts, 2 orders
        type_sql = f'CASE WHEN type BETWEEN 0 AND {len(TYPES)-1} THEN ([{names}])[type + 1] END'
    else:                                     # names (VARCHAR, ENUM of a pandas category)
        type_sql = f'CASE WHEN CAST(type AS VARCHAR) IN ({names}) THEN CAST(type AS VARCHAR) END'
    rest = ', '.join(c for c in columns if c != 'type')
    con.execute(f'CREATE TEMP VIEW {name} AS SELECT {rest}, {type_sql} AS type FROM {name}_raw')


def _scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def _score(recalls):
    total = 0.0
    for t in TYPES:
        total += WEIGHTS[t]*recalls[t]
    return total


def metric(ranked, labels, *, sessions, threads=4):
    """OTTO Recall@20 pooled over sessions (§3).

    ``ranked``: ``session, type, aid, rank`` with rank 1..20; a repeated aid or rank
    within one (session, type) list is refused. ``labels``: ``session, type, aid``,
    at most one clicks aid per session. Either may be a pandas frame or a parquet
    path. ``sessions`` (required, keyword-only): the evaluation population; rows of
    other sessions are ignored and a population session without ranked rows
    scores 0.

    Per type t: hits_s = |P_s,t ∩ G_s,t|, den_s = min(20, |G_s,t|),
    R_t = Σ hits / Σ den (a ratio of sums; sessions without labels of t add 0/0),
    Score = 0.10·R_clicks + 0.30·R_carts + 0.60·R_orders. R_t is NaN when the
    population has no label of type t.

    Returns dict(sessions=int64 array ascending, hits={t: array}, den={t: array},
    recall={t: float}, score=float).
    """
    import duckdb
    import numpy as np
    import pandas as pd

    con = duckdb.connect()
    try:
        con.execute(f'SET threads={int(threads)}')
        _view(con, 'r', ranked, RANKED_COLUMNS)
        _view(con, 'l', labels, LABEL_COLUMNS)
        bad = _scalar(con, f'SELECT count(*) FROM r WHERE session IS NULL OR aid IS NULL OR rank IS NULL '
                           f'OR type IS NULL OR rank < 1 OR rank > {TOP_K} OR rank <> floor(rank)')
        require(bad == 0, f'ranked: {bad} rows with a NULL, an unknown type or a rank outside 1..{TOP_K}')
        for key in ('aid', 'rank'):
            dup = _scalar(con, f'SELECT count(*) FROM (SELECT session, type, {key} FROM r GROUP BY ALL '
                               f'HAVING count(*) > 1)')
            require(dup == 0, f'ranked: repeated {key} within a list ({dup} cases)')
        bad = _scalar(con, 'SELECT count(*) FROM l WHERE session IS NULL OR aid IS NULL OR type IS NULL')
        require(bad == 0, f'labels: {bad} rows with a NULL or an unknown type')
        dup = _scalar(con, 'SELECT count(*) FROM (SELECT session, type, aid FROM l GROUP BY ALL HAVING count(*) > 1)')
        require(dup == 0, f'labels: {dup} repeated (session, type, aid)')
        many = _scalar(con, "SELECT count(*) FROM (SELECT session FROM l WHERE type = 'clicks' GROUP BY session "
                            "HAVING count(*) > 1)")
        require(many == 0, f'labels: {many} sessions with more than one clicks label')
        require(sessions is not None, 'metric needs the evaluation population (sessions=...)')
        values = np.asarray(list(sessions), dtype=np.int64)
        require(len(np.unique(values)) == len(values), 'Duplicate sessions in the population')
        con.register('pop_input', pd.DataFrame({'session': values}))
        con.execute('CREATE TEMP TABLE pop AS SELECT session FROM pop_input')
        per_type = ', '.join(
            f"coalesce(sum(hits) FILTER (WHERE type = '{t}'), 0)::BIGINT AS hits_{t}, "
            f"coalesce(sum(den) FILTER (WHERE type = '{t}'), 0)::BIGINT AS den_{t}" for t in TYPES)
        frame = con.execute(f"""
            WITH h AS (SELECT session, type, count(*) AS hits, 0 AS den FROM r JOIN l USING (session, type, aid)
                       GROUP BY ALL),
                 g AS (SELECT session, type, 0 AS hits, least(count(*), {TOP_K}) AS den FROM l GROUP BY ALL),
                 hg AS (SELECT * FROM h UNION ALL SELECT * FROM g),
                 s AS (SELECT session, {per_type} FROM hg GROUP BY session)
            SELECT pop.session, {', '.join(f'coalesce(hits_{t}, 0) AS hits_{t}, coalesce(den_{t}, 0) AS den_{t}'
                                           for t in TYPES)}
            FROM pop LEFT JOIN s USING (session) ORDER BY pop.session""").df()
    finally:
        con.close()
    out = dict(sessions=frame['session'].to_numpy(dtype=np.int64), hits={}, den={}, recall={})
    for t in TYPES:
        hits = frame[f'hits_{t}'].to_numpy(dtype=np.int64)
        den = frame[f'den_{t}'].to_numpy(dtype=np.int64)
        out['hits'][t], out['den'][t] = hits, den
        total = int(den.sum())
        out['recall'][t] = float(hits.sum())/total if total else float('nan')
    out['score'] = _score(out['recall'])
    return out


# =============================================================================== bootstrap of the ratio (§3)

def _quantiles(values):
    import numpy as np
    lower, upper = (float(x) for x in np.quantile(values, CI_QUANTILES, method='linear'))
    return [lower, upper]


def bootstrap_ratio(reference, alternative, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    """Paired bootstrap CI of Score(alternative) - Score(reference) with pooled R_t (§3).

    Both arguments are ``metric`` results on the same population and labels.
    Sessions are sorted by id; a fresh default_rng(seed) draws, per iteration,
    ``idx = rng.integers(0, n, n)`` shared by both arms and all three types; R_t is
    recomputed as Σ hits / Σ den on the resample. Percentiles 2.5 and 97.5,
    method 'linear'. Per-type differences of R_t ride on the same draws.
    """
    import numpy as np

    sessions = np.asarray(reference['sessions'], dtype=np.int64)
    require(np.array_equal(sessions, np.asarray(alternative['sessions'], dtype=np.int64)),
            'Paired arms need the identical population')
    require(len(sessions) > 0, 'Empty population')
    require(bool(np.all(np.diff(sessions) > 0)), 'Sessions must be sorted and unique')
    for t in TYPES:
        require(np.array_equal(reference['den'][t], alternative['den'][t]), f'Arms disagree on the labels of {t}')
        require(int(np.sum(reference['den'][t])) > 0, f'No labels of type {t} in the population')
    n = len(sessions)
    ref = np.stack([np.asarray(reference['hits'][t], dtype=np.int64) for t in TYPES], axis=1)
    alt = np.stack([np.asarray(alternative['hits'][t], dtype=np.int64) for t in TYPES], axis=1)
    den = np.stack([np.asarray(reference['den'][t], dtype=np.int64) for t in TYPES], axis=1)

    def recalls(hits, denominator):
        return {t: float(hits[j])/float(denominator[j]) for j, t in enumerate(TYPES)}

    point_ref = recalls(ref.sum(axis=0), den.sum(axis=0))
    point_alt = recalls(alt.sum(axis=0), den.sum(axis=0))
    rng = np.random.default_rng(seed)
    diffs = np.empty(draws)
    type_diffs = np.empty((draws, len(TYPES)))
    for i in range(draws):
        counts = np.bincount(rng.integers(0, n, n), minlength=n)   # Σ x[idx] == counts @ x, exact on integers
        d = counts @ den
        require(bool(np.all(d > 0)), 'A resample without labels of some type')
        r_ref, r_alt = recalls(counts @ ref, d), recalls(counts @ alt, d)
        diffs[i] = _score(r_alt)-_score(r_ref)
        type_diffs[i] = [r_alt[t]-r_ref[t] for t in TYPES]
    lower, upper = _quantiles(diffs)
    return dict(sessions=n, draws=draws, seed=seed,
                reference=dict(recall=point_ref, score=_score(point_ref)),
                alternative=dict(recall=point_alt, score=_score(point_alt)),
                diff=_score(point_alt)-_score(point_ref), ci=[lower, upper], covers_zero=bool(lower <= 0 <= upper),
                types={t: dict(diff=point_alt[t]-point_ref[t], ci=_quantiles(type_diffs[:, j]))
                       for j, t in enumerate(TYPES)})


# =============================================================================== reading rules (§10)

def _read(cis, labels):
    if all(ci[0] > 0 for ci in cis):
        return labels[0]
    if all(ci[1] < 0 for ci in cis):
        return labels[1]
    if all(ci[0] <= 0 <= ci[1] for ci in cis):
        return labels[2]
    return labels[3]


def _ci(ci):
    require(len(ci) == 2 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in ci) and ci[0] <= ci[1],
            f'Bad CI {ci!r}')
    return [float(ci[0]), float(ci[1])]


def _verdict(cis, stage, labels):
    require(stage in STAGE_SEEDS, f'Unknown stage {stage!r}')
    if cis is None:                                     # BA or BApl failed gate 1 (§8)
        return NOT_COMPUTED
    require(isinstance(cis, dict), 'CIs come as {seed: [lower, upper]}')
    cis = {int(seed): _ci(ci) for seed, ci in cis.items()}
    require(sorted(cis) == sorted(STAGE_SEEDS[stage]), f'Stage {stage} needs CIs of seeds {STAGE_SEEDS[stage]}')
    if stage == 1:
        return ONE_SEED
    return _read([cis[seed] for seed in STAGE_SEEDS[stage]], labels)


def verdict_transfer(cis, stage):
    """Verdict 1 from {seed: CI of D = BA - B}; stage 1 is not decided, None is 'не вычислен'."""
    return _verdict(cis, stage, VERDICT_TRANSFER)


def verdict_content(cis, stage):
    """Verdict 2 from {seed: CI of P = BA - BApl}; stage 1 is not decided, None is 'не вычислен'."""
    return _verdict(cis, stage, VERDICT_CONTENT)


def stage1_note(ci_d):
    """The only stage-1 wording allowed beside the verdicts, or None."""
    return STAGE1_NOTE if _ci(ci_d)[0] > 0 else None


def level_reading(private):
    """Level of the Kaggle private score (§10): mean of the given files (one per seed).

    Means are taken in decimal arithmetic from the published values, so a mean of
    two five-digit scores falls on the right side of a threshold.
    """
    values = [Decimal(repr(float(v))) for v in private]
    require(values, 'No private scores')
    mean = sum(values)/len(values)
    reading = next(text for bound, text in LEVEL_THRESHOLDS if bound is None or mean < Decimal(bound))
    result = dict(value=float(mean), seeds=len(values), reading=reading)
    if len(values) == 1:
        result['note'] = LEVEL_ONE_SEED
    return result

