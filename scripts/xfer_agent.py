"""Agent half of the transfer experiment on Tinkoff and SberMarket (agent A).

Contract: docs/xfer-design.md section 3, section 6 of docs/xfer-tinkoff-design.md and
docs/xfer-sber-design.md. The protocol is the H&M one (docs/hm-agent-design.md,
sections 1, 2 and 5; code in scripts/hm_agent_sandbox.py and scripts/hm_agent_loop.py)
with the dataset parts taken from the adapter (scripts/xfer_common.py docstring):

- ``export``: a manifest of the partitions and views the adapter exposes at every
  anchor up to A_holdout, with SHA-256; nothing is copied.
- ``sandbox``: a new locked in-memory DuckDB connection per (anchor, keys) with the
  adapter's views, ``cand`` and ``users`` only; ``allowed_directories`` is limited to
  the allowed partitions, external access is off and the configuration is locked.
- ``check_sql``: the H&M rules plus ``adapter.sql_rules()`` (anchor form, time rules,
  extra forbidden words).
- ``probe``: stats.json (``adapter.probe_stats``), keys.parquet and probe.json for the
  probe collection the coordinator built with ``collect(A_probe, 'probe', ...)``.
- ``run``: 6 rounds x 5 proposals, at most 12 calls of claude-opus-5-5 through
  ``hm_agent_loop.ask_llm``; feedback is validity and coverage only, coarse numbers.
  The prompt is ``PROMPT_TEMPLATE.format(**prompt_substitutions(...))`` and every
  number of the substitutions must come from stats.json, base.json,
  PROMPT_CONSTANTS or the feedback formatter (``prompt_number_problems``).
- ``freeze``: configs/datasets/xfer-<x>-set.json with the prompt digest and code.
- ``sidecar``: agent.parquet aligned to the frame rows of a collection.
- ``leakcheck``: full history against the cut directory on the last train and the
  holdout anchor, and 2 000 users in one batch against 4 x 500.

Run as ``python -I scripts/xfer_agent.py <command> --dataset {tinkoff,sber} ...``;
one JSON line on stdout, exit 0/1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import weakref

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import xfer_common as xc  # noqa: E402
from scripts.hm_agent_loop import ask_llm, clean_error, parse_reply  # noqa: E402,F401

EXPORT_FORMAT = 'xfer-export-v1'
PROBE_FORMAT = 'xfer-probe-v1'
RUN_FORMAT = 'xfer-run-v1'
SET_FORMAT = 'xfer-set-v1'
LEAKCHECK_FORMAT = 'xfer-leakcheck-v1'
SIDECAR_REPORT = 'report.json'
KEYS_FILE = 'keys.parquet'
STATS_FILE = 'stats.json'
PROBE_FILES = (KEYS_FILE, STATS_FILE)

LEVELS = ('pair', 'user', 'item')
KEYS = ('user_id', 'item_id')
FIELDS = ('name', 'idea', 'level', 'sql')
STATUSES = ('valid', 'invalid', 'budget')
SET_FIELDS = ('format', 'dataset', 'run', 'run_sha256', 'probe', 'base_digest', 'prompt', 'prompt_digest', 'code',
              'proposals', 'attempts', 'columns', 'budget', 'digest', 'audit')

MODEL = 'claude-opus-5-5'
ROUNDS = 6
PROPOSALS = 5
MAX_CALLS = 12  # contract 3: at most 12 calls per set; more are refused
RETRIES_EXHAUSTED = 'retries_exhausted'
MAX_RETRIES = 2  # failed runs retried per probe, over the whole chain (H&M)
RUN_NAME = re.compile(r'run-[A-Za-z0-9][A-Za-z0-9._-]*')
OUTPUT_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')
OPERATOR_ABORT = 'KeyboardInterrupt'

# Probe limits per dataset (T: as H&M 1.4; S: doubled, docs/xfer-sber-design.md 6.3).
PROBE_LIMITS = {
    'tinkoff': dict(timeouts=dict(pair=20.0, user=20.0, item=60.0),
                    budget=dict(pair_user_seconds=90.0, item_seconds=180.0)),
    'sber': dict(timeouts=dict(pair=40.0, user=40.0, item=120.0),
                 budget=dict(pair_user_seconds=180.0, item_seconds=360.0)),
}
RUN_TIMEOUT = 900.0  # one proposal in sidecar and leakcheck runs (H&M working timeout)
MEMORY = '4GB'

MAX_ROWS = 20_000_000
MAX_VALUES = 3
NAME = re.compile(r'ag_[a-z][a-z0-9_]{1,38}')
VALUE_TYPE = re.compile(r'(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|BOOLEAN|DECIMAL\([0-9]+,\s*[0-9]+\))')
FLOAT32_MAX = 3.4028234663852886e38
MIN_DISTINCT = 2
MIN_NON_NULL = 100
RHO_LIMIT = 0.999
SAMPLE_ROWS = 100_000
MIN_SPEARMAN_ROWS = 1000
INVARIANCE_USERS = 1000
TOLERANCE = 1e-9
ERROR_CHARS = 400
LEAK_USERS = 2000
LEAK_BATCHES = 4
SIDECAR_BATCH_ROWS = 1_500_000  # frame rows per sidecar batch (whole users), well under MAX_ROWS
TIME_TYPE = re.compile(r'(TIMESTAMP.*|DATE)', re.I)
SANDBOX_PREFIX = 'tlab-xfer-sbx-'
MEMORY_TEXT = re.compile(r'[0-9]+(\.[0-9]+)?\s*(KB|MB|GB|TB|KiB|MiB|GiB|TiB)')
IDENT = re.compile(r'[a-z_][a-z0-9_]*')
RESERVED = frozenset(('user_id', 'item_id', 'label', 'weight', 'n_targets', 'rank', 'score'))

# H&M 1.3, verbatim: whole words, any case.
FORBIDDEN = re.compile(
    r'\b(transactions|customers|frame|labels?|targets?|hm_\w+|_hm_\w+|'
    r'read_\w+|parquet_\w+|csv|json\w*|glob|getenv|query|query_table|duckdb_\w+|information_schema|pg_catalog|'
    r'sqlite_master|pragma\w*|current_setting|sniff_\w+|checkpoint|force_checkpoint|which_secret|'
    r'attach|detach|copy|export|import|install|load|set|reset|use|call|create|drop|insert|update|delete|alter|'
    r'random|setseed|uuid|gen_random_uuid|now|today|current_date|current_time|current_timestamp|get_current_time|'
    r'sample|tablesample)\b', re.I)
# Stricter than H&M (coordinator, L1): every source of nondeterminism or session state.
NONDETERMINISTIC = re.compile(
    r'\b(uuid|uuidv4|uuidv7|gen_random_uuid|random|setseed|now|today|current_date|current_time|current_timestamp|'
    r'get_current_time|get_current_timestamp|transaction_timestamp|current_localtime|current_localtimestamp|'
    r'localtime|localtimestamp|txid_current|version|nextval|currval)\b', re.I)
RAISING = re.compile(r'\b(error|strptime|regexp_\w+)\s*\(', re.I)
BATCH = re.compile(r'\b(cand|users)\b', re.I)
STATEMENT = re.compile(r'(select|with)\b', re.I)
DATE_LITERAL = re.compile(r"'\s*[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}")
PLACEHOLDER = '{A}'

# Contract 3: a number of the prompt substitutions is a token of this expression.
NUMBER = re.compile(r'(?<![A-Za-z0-9_.@])\d+(?:\.\d+)?(?![A-Za-z0-9_])')
WARNING = ('All valid columns will enter the model without selection. Superfluous and noisy columns hurt: '
           'a few strong, non-redundant signals are needed. User-level columns work only through interactions.')
# Names that may not reach the agent. Brands and the competition: nowhere in the prompt. Raw file
# names: not in the substitutions (the templates list them among the forbidden table names).
NAMES_IN_PROMPT = re.compile(r'kaggle|tinkoff|sber|competition|сбер|тинькофф|купер|instamart', re.I)
NAMES_IN_SUBSTITUTIONS = re.compile(NAMES_IN_PROMPT.pattern + r'|data_train|test_users|sample_submission', re.I)
ID_HEX = re.compile(r'[0-9a-fA-F]{12,}')
ID_DIGITS = re.compile(r'[0-9]{9,}')
BUCKET = re.compile(r'0|2\^(-?\d+)–2\^(-?\d+)')
COLUMN_STATS = (('non_null_share', 'non-null', 'share'), ('non_null_share_recent', 'recent', 'share'),
                ('non_null_share_global', 'global', 'share'), ('distinct', 'distinct', 'bucket'),
                ('max_abs_spearman', 'max |rho|', 'rho'), ('nearest', 'nearest', 'name'))


class ProposalError(ValueError):
    """A proposal breaks the SQL rules or the output contract, fails or times out."""


# ---------------------------------------------------------------- small helpers

def _threads(value):
    if type(value) is not int or not 1 <= value <= 256:
        raise ValueError('Threads must be an integer from 1 to 256')
    return value


def _seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('A finite positive timeout is required')
    return float(value)


def _memory(value):
    if not isinstance(value, str) or not MEMORY_TEXT.fullmatch(value):
        raise ValueError('Memory must look like 4GB')
    return value


def _literal(text):
    return "'" + str(text).replace("'", "''") + "'"


def _ident(name):
    if not isinstance(name, str) or not IDENT.fullmatch(name):
        raise ValueError(f'Unexpected identifier {name!r}')
    return name


def _floats(values):
    import numpy as np
    return np.ma.filled(np.ma.asarray(values, dtype=np.float64), np.nan)


def _clip(text):
    return str(text)[:ERROR_CHARS]


def _stamp():
    return xc.utc_now().replace('-', '').replace(':', '')


def _output_name(name, default):
    name = default if name is None else name
    if not isinstance(name, str) or not OUTPUT_NAME.fullmatch(name):
        raise ValueError(f'Output names are [A-Za-z0-9._-]; got {name!r}')
    return name


def redact(value):
    """Id-shaped runs never reach a prompt (as H&M redact)."""
    return ID_DIGITS.sub('<digits>', ID_HEX.sub('<hex>', str(value)))


def _plain(value):
    """JSON-safe copy: numpy scalars become Python values, non-finite floats null."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if type(value).__module__ == 'numpy' and hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def log2_bucket(value):
    """'0' or '2^k–2^(k+1)' with 2^k <= value < 2^(k+1) (H&M log2_bucket)."""
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError('A log2 bucket needs a finite non-negative number')
    if value == 0:
        return '0'
    k = math.frexp(value)[1]-1
    return f'2^{k}–2^{k+1}'


def _is_bucket(text):
    match = BUCKET.fullmatch(text) if isinstance(text, str) else None
    return bool(match) and (text == '0' or int(match.group(2)) == int(match.group(1))+1)


def _share(value):
    return None if value is None else round(float(value), 2)


def _tens(seconds):
    """Probe seconds as shown or frozen: down to a multiple of 10 s."""
    return int(max(float(seconds), 0.0) // 10 * 10)


def limits(dataset):
    """Probe timeouts and budget: the adapter's sql_rules() values when it gives them, else PROBE_LIMITS."""
    table = PROBE_LIMITS[xc.check_dataset(dataset)]
    rules = xc.adapter(dataset).sql_rules()
    timeouts = rules.get('timeouts') if isinstance(rules, dict) else None
    budget = rules.get('budget') if isinstance(rules, dict) else None
    result = dict(timeouts={k: _seconds(v) for k, v in (timeouts or table['timeouts']).items()},
                  budget={k: _seconds(v) for k, v in (budget or table['budget']).items()})
    if set(result['timeouts']) != set(LEVELS) or set(result['budget']) != {'pair_user_seconds', 'item_seconds'}:
        raise ValueError('Probe limits need timeouts per level and pair_user_seconds, item_seconds')
    return result


def _anchor_json(anchor):
    return anchor if type(anchor) is int else xc.anchor_text(anchor)


def budget_key(level):
    return 'item_seconds' if level == 'item' else 'pair_user_seconds'


def _after_holdout(dataset, anchor):
    return xc.anchor_int(anchor) > xc.anchor_int(xc.adapter(dataset).anchors()['holdout'])


def _sql_sha(sql):
    return hashlib.sha256(sql.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------- check_sql

def _extra(rules):
    words = rules.get('forbidden') if isinstance(rules, dict) else None
    if isinstance(words, re.Pattern):
        return words
    if isinstance(words, str):
        words = [words]
    words = [w for w in (words or ()) if w]
    if not words:
        return None
    return re.compile(r'\b(?:' + '|'.join(f'(?:{w})' for w in words) + r')\b', re.I)


def sql_rules(dataset):
    rules = xc.adapter(dataset).sql_rules()
    if not isinstance(rules, dict) or not callable(rules.get('check')):
        raise ValueError('sql_rules() must give forbidden and a callable check')
    return dict(forbidden=_extra(rules), check=rules['check'])


def check_sql(dataset, sql, level, rules=None):
    """H&M 1.3 (one SELECT/WITH, no comments, forbidden words, item level without cand/users)
    plus the dataset rules of ``adapter.sql_rules()``; the anchor is only the placeholder {A}."""
    rules = sql_rules(dataset) if rules is None else rules
    if level not in LEVELS:
        raise ProposalError('level must be pair, user or item')
    if not isinstance(sql, str) or not sql.strip():
        raise ProposalError('sql must be a non-empty string')
    body = sql.strip()
    if body.endswith(';'):
        body = body[:-1].rstrip()
    if ';' in body:
        raise ProposalError('exactly one statement is allowed; ";" may only end it')
    if '--' in body or '/*' in body:
        raise ProposalError('comments are not allowed')
    if not STATEMENT.match(body):
        raise ProposalError('the statement must start with SELECT or WITH')
    rest = body.replace(PLACEHOLDER, ' ')
    if '{' in rest or '}' in rest:
        raise ProposalError('the anchor is written only as the placeholder {A}; no other {...} is allowed')
    if DATE_LITERAL.search(rest):
        raise ProposalError('date literals are not allowed; write times relative to {A}')
    hit = (FORBIDDEN.search(rest) or NONDETERMINISTIC.search(rest) or RAISING.search(rest)
           or (rules['forbidden'] and rules['forbidden'].search(rest)))
    if hit:
        raise ProposalError(f'forbidden table, function or command: {hit.group(0)}')
    if level == 'item':
        hit = BATCH.search(rest)
        if hit:
            raise ProposalError(f'an item query must not use {hit.group(0)}: its values are cached per process')
    try:
        rules['check'](sql, level)
    except ProposalError:
        raise
    except ValueError as exc:
        raise ProposalError(str(exc)) from None


def _fields(proposal):
    if not isinstance(proposal, dict):
        raise ProposalError('a proposal is an object with name, idea, level and sql')
    for key in FIELDS:
        if not isinstance(proposal.get(key), str) or not proposal[key].strip():
            raise ProposalError(f'{key} must be a non-empty string')
    if proposal['level'] not in LEVELS:
        raise ProposalError('level must be pair, user or item')
    return proposal['level'], proposal['sql']


# ---------------------------------------------------------------- views and sandbox

def _spec(raw):
    """views() output checked: files, views, schema, levels (pair = user + item keys), items."""
    if not isinstance(raw, dict):
        raise ValueError('views() must return a dict')
    files = [str(Path(f).resolve()) for f in raw.get('files') or []]
    if not files or len(set(files)) != len(files):
        raise ValueError('views() must list distinct allowed files')
    for path in files:
        if not Path(path).is_file() or "'" in path:
            raise ValueError(f'views() lists a missing or unquotable file: {path}')
    views = raw.get('views')
    if not isinstance(views, dict) or not views or not all(isinstance(s, str) and s.strip() for s in views.values()):
        raise ValueError('views() must give name -> SELECT')
    for name in views:
        _ident(name)
        if name in ('cand', 'users', '_x'):
            raise ValueError(f'View name {name} is reserved by the sandbox')
    levels = raw.get('levels')
    if not isinstance(levels, dict) or set(levels) != set(LEVELS):
        raise ValueError('views() levels must be pair, user and item')
    levels = {k: tuple(_ident(c) for c in v) for k, v in levels.items()}
    if len(levels['pair']) != 2 or levels['pair'] != levels['user']+levels['item']:
        raise ValueError('Level keys must be pair = user + item')
    items = raw.get('items')
    if not isinstance(items, str) or not items.strip():
        raise ValueError('views() must give the items SELECT')
    time_columns = raw.get('time_columns')
    if time_columns is not None and (not isinstance(time_columns, dict) or not set(time_columns) <= set(views)):
        raise ValueError('views() time_columns must map view names to their event-time column')
    return dict(files=files, views=dict(views), schema=raw.get('schema') or {}, levels=levels, items=items,
                time_columns=None if time_columns is None else {k: _ident(v) for k, v in time_columns.items()})


def _views(dataset, anchor, purpose):
    """The adapter's views at A; the holdout window is checked first for A > A_holdout."""
    if _after_holdout(dataset, anchor):
        xc.require_window(dataset, purpose)
    return _spec(xc.adapter(dataset).views(anchor, purpose))


def _spec_digest(spec):
    return xc.canonical_digest(dict(files=spec['files'], views=spec['views'], items=spec['items'],
                                    levels={k: list(v) for k, v in spec['levels'].items()}))


def sandbox(dataset, A, keys, threads=3, purpose='agent', memory=MEMORY, views=None):
    """A new locked in-memory connection with the adapter's views, cand and users only (H&M 1.2).

    ``keys`` is a parquet file of ``user_id, item_id``. ``views`` is ``adapter.views(A,
    purpose)`` unless given (the leakcheck passes rerooted copies). For A > A_holdout
    the holdout window is required in any case.
    """
    import duckdb
    if _after_holdout(dataset, A):
        xc.require_window(dataset, purpose)
    spec = _spec(xc.adapter(dataset).views(A, purpose)) if views is None else views
    threads = _threads(threads)
    memory = _memory(memory)
    keys_path = Path(keys).resolve()
    if not keys_path.is_file():
        raise ValueError('The batch keys parquet is missing')
    user_key, item_key = spec['levels']['pair']
    directories = sorted({str(Path(f).parent)+'/' for f in spec['files']})
    temp = Path(tempfile.mkdtemp(prefix=SANDBOX_PREFIX)).resolve()
    con = duckdb.connect(':memory:')
    weakref.finalize(con, shutil.rmtree, str(temp), True)
    try:
        con.execute(f'SET threads={threads}')
        con.execute('SET memory_limit=?', [memory])
        con.execute('SET enable_progress_bar=false')
        con.execute('SET python_enable_replacements=false')
        con.execute('SET autoinstall_known_extensions=false')
        con.execute('SET autoload_known_extensions=false')
        con.execute('SET temp_directory=?', [str(temp)])
        con.execute("SET max_temp_directory_size='8GB'")
        con.execute('SET allowed_directories=?', [directories])
        for name, sql in spec['views'].items():
            con.execute(f'CREATE VIEW {name} AS {sql}')
        con.execute(f'''CREATE TABLE cand AS SELECT CAST(user_id AS BIGINT) AS {user_key},
            CAST(item_id AS BIGINT) AS {item_key} FROM read_parquet(?) ORDER BY 1, 2''', [str(keys_path)])
        nulls, repeated = con.execute(f'''SELECT count(*) FILTER (WHERE {user_key} IS NULL OR {item_key} IS NULL),
            count(*)-count(DISTINCT ({user_key}, {item_key})) FROM cand''').fetchone()
        if nulls or repeated:
            raise ValueError('Batch keys must be unique non-NULL pairs')
        con.execute(f'CREATE TABLE users AS SELECT DISTINCT {user_key} FROM cand ORDER BY 1')
        con.execute('SET enable_external_access=false')
        con.execute('SET lock_configuration=true')
    except BaseException:
        con.close()
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return con


def _close(con):
    """Close a sandbox and remove its spill directory."""
    try:
        temp = con.execute("SELECT current_setting('temp_directory')").fetchone()[0]
    except Exception:
        temp = None
    con.close()
    if temp:
        path = Path(temp)
        if path.name.startswith(SANDBOX_PREFIX) and path.parent == Path(tempfile.gettempdir()).resolve():
            shutil.rmtree(path, ignore_errors=True)


def _require_sandbox(con):
    try:
        locked, external = con.execute(
            "SELECT current_setting('lock_configuration'), current_setting('enable_external_access')").fetchone()
    except Exception:
        locked = external = None
    if locked is not True or external is not False:
        raise ValueError('Proposals run only in a locked sandbox connection')


# ---------------------------------------------------------------- the harness (H&M 1.4)

RUNTIME_TEXT = {
    'ConversionException': 'a value could not be converted at run time',
    'InvalidInputException': 'invalid input at run time',
    'OutOfRangeException': 'a value was out of range at run time',
    'TypeMismatchException': 'a type mismatch at run time',
    'NotImplementedException': 'an unsupported operation at run time',
    'ConstraintException': 'a constraint failed at run time',
    'PermissionException': 'access outside the sandbox was refused',
    'OutOfMemoryException': 'the query ran out of memory',
    'DependencyException': 'a dependency failed at run time',
    'SequenceException': 'a sequence failed at run time',
    'InvalidTypeException': 'an invalid type at run time',
}
RUNTIME_DEFAULT = 'the query failed at run time'
TECHNICAL_TEXT = 'technical DuckDB failure while running a proposal; the DuckDB message is withheld'


def _proposal_failure(exc):
    import duckdb
    technical = (duckdb.IOException, duckdb.InternalError, duckdb.FatalException, duckdb.ConnectionException,
                 duckdb.SerializationException, duckdb.TransactionException, duckdb.InterruptException)
    return isinstance(exc, duckdb.Error) and not isinstance(exc, technical)


def error_feedback(exc, sql=''):
    """Planning errors keep their message through clean_error; every other DuckDB error a fixed text."""
    import duckdb
    name = type(exc).__name__
    if isinstance(exc, (duckdb.ParserException, duckdb.SyntaxException, duckdb.BinderException,
                        duckdb.CatalogException)):
        return f'{name}: {clean_error(str(exc), sql)}'
    return f'{name}: {RUNTIME_TEXT.get(name, RUNTIME_DEFAULT)}'


class _Limit:
    """Interrupt one proposal after its time limit."""

    def __init__(self, con, seconds, sql=''):
        self.con, self.seconds, self.sql = con, seconds, sql
        self.fired = threading.Event()
        self.timer = threading.Timer(seconds, self._fire)
        self.timer.daemon = True

    def _fire(self):
        self.fired.set()
        self.con.interrupt()

    def __enter__(self):
        self.timer.start()
        return self

    def __exit__(self, *exc):
        self.timer.cancel()
        return False

    def timeout(self):
        return ProposalError(f'timeout after {self.seconds:g} s')

    def error(self, exc):
        import duckdb
        if self.fired.is_set():
            return self.timeout()
        if _proposal_failure(exc):
            return ProposalError(error_feedback(exc, self.sql))
        if isinstance(exc, duckdb.Error):
            return type(exc)(f'{type(exc).__name__}: {TECHNICAL_TEXT}')
        return exc


def _check_output(con, spec, level, sql):
    """H&M 1.4 on _x: level keys (cand types, non-NULL, unique, in their set), 1-3 ag_* numeric values."""
    keys = spec['levels'][level]
    cand_types = {row[0]: row[1] for row in con.execute('DESCRIBE cand').fetchall()}
    described = [(row[0], row[1]) for row in con.execute('DESCRIBE _x').fetchall()]
    names, kinds = [n for n, _ in described], dict(described)
    if any(not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)', sql) for name in names if name not in keys):
        raise ProposalError('every output column must be named in the SQL (alias each value AS ag_...); '
                            'a column name not written in the SQL was produced')
    if len(set(names)) != len(names):
        raise ProposalError('output column names repeat')
    missing = [key for key in keys if key not in kinds]
    if missing:
        raise ProposalError(f'level {level} needs the key columns {", ".join(keys)}; missing {", ".join(missing)}')
    for key in keys:
        if kinds[key] != cand_types[key]:
            raise ProposalError(f'key {key} must be {cand_types[key]}, not {kinds[key]}')
    values = [name for name in names if name not in keys]
    if not 1 <= len(values) <= MAX_VALUES:
        raise ProposalError(f'one to {MAX_VALUES} value columns are required besides the keys, got {len(values)}')
    for name in values:
        if not NAME.fullmatch(name):
            raise ProposalError(f'column {name} is not a key of this level and does not match '
                                '^ag_[a-z][a-z0-9_]{1,38}$')
        if not VALUE_TYPE.fullmatch(kinds[name]):
            raise ProposalError(f'column {name} has type {kinds[name]}; integer, DECIMAL, FLOAT, DOUBLE or BOOLEAN '
                                'is required (times as differences to {A})')
    nulls = ' OR '.join(f'{key} IS NULL' for key in keys)
    distinct = keys[0] if len(keys) == 1 else f'({", ".join(keys)})'
    rows, null_rows, repeated = con.execute(
        f'SELECT count(*), count(*) FILTER (WHERE {nulls}), count(*)-count(DISTINCT {distinct}) FROM _x').fetchone()
    if rows > MAX_ROWS:
        raise ProposalError(f'output rows exceed the limit of {MAX_ROWS}')
    if null_rows:
        raise ProposalError('some rows have NULL keys')
    if repeated:
        raise ProposalError('duplicate keys: one row per key is required')
    if level == 'item':
        universe, label = f'({spec["items"]}) AS u({keys[0]})', 'the items known at the anchor'
    else:
        universe, label = {'pair': 'cand u', 'user': 'users u'}[level], {'pair': 'cand', 'user': 'users'}[level]
    match = ' AND '.join(f'u.{key} = x.{key}' for key in keys)
    outside = con.execute(f'SELECT count(*) FROM _x x WHERE NOT EXISTS (SELECT 1 FROM {universe} WHERE {match})'
                          ).fetchone()[0]
    if outside:
        raise ProposalError(f'some keys lie outside {label}')
    return values, int(rows)


def _finite(name):
    value = f'CAST(x."{name}" AS DOUBLE)'
    return f'CASE WHEN isfinite({value}) AND abs({value}) <= {FLOAT32_MAX!r} THEN {value} END AS "{name}"'


def _fetch(con, spec, level, names, shape):
    keys = spec['levels'][level]
    user_key, item_key = spec['levels']['pair']
    casts = ', '.join(_finite(name) for name in names)
    if shape == 'table':
        order = ', '.join(f'x.{key}' for key in keys)
        return con.execute(f'SELECT {order}, {casts} FROM _x x ORDER BY {order}').fetch_df()
    join = ' AND '.join(f'x.{key} = c.{key}' for key in keys)
    head = f'c.{user_key} AS user_id, c.{item_key} AS item_id, ' if shape == 'pairs' else ''
    query = f'SELECT {head}{casts} FROM cand c LEFT JOIN _x x ON {join} ORDER BY c.{user_key}, c.{item_key}'
    if shape == 'pairs':
        return con.execute(query).fetch_df()
    fetched = con.execute(query).fetchnumpy()
    return {name: _floats(fetched[name]) for name in names}


def _execute(con, spec, level, sql, anchor, timeout_s, shape='pairs'):
    """CREATE TEMP TABLE _x AS <sql with {A}>, checks, DOUBLE values in the requested shape.

    ``pairs``: cand keys (as user_id, item_id) + values; ``values``: value arrays in cand
    order; ``table``: the level keys + values of _x. Returns (result, value names, rows).
    """
    import duckdb
    body = sql.strip()
    if body.endswith(';'):
        body = body[:-1].rstrip()
    statement = 'CREATE TEMP TABLE _x AS\n'+body.replace(PLACEHOLDER, xc.anchor_text(anchor))
    parsed = failure = None
    try:
        parsed = con.extract_statements(statement)
    except duckdb.Error as exc:
        failure = ProposalError(error_feedback(exc, sql))
    if failure is not None:
        raise failure
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.CREATE:
        raise ProposalError('exactly one SELECT statement is allowed')
    limit = _Limit(con, timeout_s, sql)
    failure = None
    try:
        with limit:
            con.execute('DROP TABLE IF EXISTS _x')
            con.execute(statement)
            names, rows = _check_output(con, spec, level, sql)
            result = _fetch(con, spec, level, names, shape)
        if limit.fired.is_set():
            raise limit.timeout()
    except Exception as exc:
        failure = limit.error(exc)
        if failure is exc:
            raise
    finally:
        try:
            con.execute('DROP TABLE IF EXISTS _x')
        except Exception:
            pass
    if failure is not None:
        raise failure
    return result, names, rows


def run_proposal(dataset, con, spec, proposal, anchor, timeout_s):
    """One proposal in a sandbox: cand keys + its value columns as DOUBLE."""
    level, sql = _fields(proposal)
    check_sql(dataset, sql, level)
    _require_sandbox(con)
    return _execute(con, spec, level, sql, anchor, _seconds(timeout_s), 'pairs')[0]


# ---------------------------------------------------------------- agent columns for keys

def _key_frame(keys):
    import pandas as pd
    if not isinstance(keys, pd.DataFrame) or not set(KEYS) <= set(keys.columns):
        raise ValueError('Keys must be a DataFrame with user_id and item_id')
    frame = keys[list(KEYS)].reset_index(drop=True)
    for name in KEYS:
        if frame[name].isna().any() or not pd.api.types.is_integer_dtype(frame[name]):
            raise ValueError(f'{name} keys must be non-NULL integers')
    if not len(frame):
        raise ValueError('At least one key is required')
    return frame


def _stage_keys(frame, path, threads):
    """keys.parquet sorted by the keys; returns the input position of every sorted row."""
    import duckdb
    import numpy as np
    import pandas as pd
    staged = pd.DataFrame({'user_id': frame['user_id'].to_numpy(dtype=np.int64),
                           'item_id': frame['item_id'].to_numpy(dtype=np.int64),
                           'pos': np.arange(len(frame), dtype=np.int64)})
    con = duckdb.connect(':memory:')
    try:
        con.execute(f'SET threads={threads}')
        con.execute('SET python_enable_replacements=false')
        con.register('_xfer_keys', staged)
        repeated = con.execute('SELECT count(*)-count(DISTINCT (user_id, item_id)) FROM _xfer_keys').fetchone()[0]
        if repeated:
            raise ValueError('Keys must be unique (user_id, item_id) pairs')
        con.execute(f'''COPY (SELECT user_id, item_id FROM _xfer_keys ORDER BY user_id, item_id)
            TO {_literal(path)} (FORMAT PARQUET)''')
        order = con.execute('SELECT pos FROM _xfer_keys ORDER BY user_id, item_id').fetchnumpy()['pos']
    finally:
        con.close()
    return np.asarray(order, dtype=np.int64)


def _check_order(con, spec, frame, order):
    import numpy as np
    user_key, item_key = spec['levels']['pair']
    got = con.execute(f'SELECT {user_key}, {item_key} FROM cand ORDER BY 1, 2').fetchnumpy()
    for name, key in zip(KEYS, (user_key, item_key)):
        if not np.array_equal(np.asarray(got[key], dtype=np.int64), frame[name].to_numpy(dtype=np.int64)[order]):
            raise RuntimeError('Sandbox keys differ from the staged batch keys')


def agent_columns(dataset, anchor, keys, agent_set, *, threads=4, timeout_s=RUN_TIMEOUT, cache=None,
                  purpose='sidecar', memory=MEMORY, views=None):
    """Values of every frozen proposal for the given keys: keys in input order + set columns (float64).

    With a ``cache`` dict, item-level tables are kept under (views digest, anchor,
    proposal id, sha256 of the SQL). A failing proposal raises ProposalError with its id.
    """
    import numpy as np
    import pandas as pd
    threads = _threads(threads)
    timeout = _seconds(timeout_s)
    if cache is not None and not isinstance(cache, dict):
        raise ValueError('The cache must be a dict or None')
    spec = _views(dataset, anchor, purpose) if views is None else views
    rules = sql_rules(dataset)
    frame = _key_frame(keys)
    out = {name: np.full(len(frame), np.nan) for name in agent_set['columns']}
    info = dict(keys=len(frame), anchor=xc.anchor_text(anchor), seconds={}, rows={}, cached=[])
    scratch = Path(tempfile.mkdtemp(prefix='tlab-xfer-keys-')).resolve()
    con = None
    digest = _spec_digest(spec)
    try:
        keys_path = scratch/KEYS_FILE
        order = _stage_keys(frame, keys_path, threads)
        con = sandbox(dataset, anchor, keys_path, threads=threads, purpose=purpose, memory=memory, views=spec)
        _check_order(con, spec, frame, order)
        items = None
        item_key = spec['levels']['item'][0]
        for proposal in agent_set['proposals']:
            pid, level, sql = proposal['id'], proposal['level'], proposal['sql']
            started = time.monotonic()
            try:
                check_sql(dataset, sql, level, rules)
                if level == 'item' and cache is not None:
                    key = (digest, xc.anchor_text(anchor), pid, _sql_sha(sql))
                    entry = cache.get(key)
                    if entry is None:
                        table, names, rows = _execute(con, spec, level, sql, anchor, timeout, 'table')
                        entry = dict(index=pd.Index(table[item_key].to_numpy(dtype=np.int64)),
                                     values=table[names].to_numpy(dtype=np.float64, na_value=np.nan),
                                     columns=list(names), rows=rows)
                        cache[key] = entry
                    else:
                        info['cached'].append(pid)
                    names, rows = entry['columns'], entry['rows']
                    _frozen(proposal, names)
                    if items is None:
                        items = frame['item_id'].to_numpy(dtype=np.int64)
                    positions = entry['index'].get_indexer(items)
                    hit = positions >= 0
                    for j, name in enumerate(names):
                        out[name][hit] = entry['values'][positions[hit], j]
                else:
                    values, names, rows = _execute(con, spec, level, sql, anchor, timeout, 'values')
                    _frozen(proposal, names)
                    for name in names:
                        out[name][order] = values[name]
            except ProposalError as exc:
                raise ProposalError(f'{pid}: {exc}') from None
            info['seconds'][pid] = round(time.monotonic()-started, 3)
            info['rows'][pid] = int(rows)
    finally:
        if con is not None:
            _close(con)
        shutil.rmtree(scratch, ignore_errors=True)
    result = frame.copy()
    for name in agent_set['columns']:
        result[name] = out[name]
    return result, info


def _frozen(proposal, names):
    if list(names) != list(proposal['columns']):
        raise ProposalError(f'value columns {", ".join(names)} differ from the frozen {", ".join(proposal["columns"])}')


# ---------------------------------------------------------------- export

def _anchor_list(anchors):
    holdout = xc.anchor_int(anchors['holdout'])
    found = {}
    for values in (anchors.get('roles') or {}).values():
        for anchor in values:
            found.setdefault(xc.anchor_text(anchor), anchor)
    found.setdefault(xc.anchor_text(anchors['probe']), anchors['probe'])
    found.setdefault(xc.anchor_text(anchors['holdout']), anchors['holdout'])
    return sorted((a for a in found.values() if xc.anchor_int(a) <= holdout), key=xc.anchor_int)


def _relative(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(Path(xc.ROOT).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def export(dataset, name=None):
    """export.json: per anchor up to A_holdout the allowed files and views; every file hashed once."""
    adapter = xc.adapter(dataset)
    anchors = adapter.anchors()
    record = dict(format=EXPORT_FORMAT, dataset=dataset, holdout=_anchor_json(anchors['holdout']), anchors={}, files={})
    for anchor in _anchor_list(anchors):
        spec = _views(dataset, anchor, 'export')
        record['anchors'][xc.anchor_text(anchor)] = dict(
            files=[_relative(f) for f in spec['files']],
            views={k: _sql_sha(v) for k, v in spec['views'].items()}, items_sha256=_sql_sha(spec['items']),
            schema=_plain(spec['schema']), levels={k: list(v) for k, v in spec['levels'].items()})
        for path in spec['files']:
            rel = _relative(path)
            if rel not in record['files']:
                record['files'][rel] = dict(sha256=xc.sha256_file(path), bytes=Path(path).stat().st_size)
    record['code'] = xc.code_identity(dataset)
    record['created_utc'] = xc.utc_now()
    record['digest'] = xc.canonical_digest({k: v for k, v in record.items() if k not in ('created_utc',)})
    out = xc.new_output(xc.output_dir(dataset, 'export', _output_name(name, f'export-{_stamp()}')))
    xc.atomic_json(out/'export.json', record)
    return dict(record, path=str(out))


def check_export(dataset, export_dir, anchor):
    """The export's record for ``anchor`` matches the current views and file bytes."""
    record = xc.read_json(Path(export_dir)/'export.json')
    xc.require(record.get('format') == EXPORT_FORMAT and record.get('dataset') == dataset, 'Not an export of this set')
    body = {k: v for k, v in record.items() if k not in ('created_utc', 'digest')}
    xc.require(xc.canonical_digest(body) == record.get('digest'), 'export.json differs from its digest')
    entry = record['anchors'].get(xc.anchor_text(anchor))
    xc.require(entry is not None, f'The export has no anchor {anchor}')
    spec = _views(dataset, anchor, 'export')
    xc.require([_relative(f) for f in spec['files']] == entry['files'], 'Allowed files differ from the export')
    xc.require({k: _sql_sha(v) for k, v in spec['views'].items()} == entry['views'], 'Views differ from the export')
    for path in spec['files']:
        xc.require(xc.sha256_file(path) == record['files'][_relative(path)]['sha256'], f'Partition changed: {path}')
    return record['digest']


# ---------------------------------------------------------------- probe

def _frame_keys(collection):
    """user_id, item_id of frame.parquet, checked unique and in (user_id, item_id) order."""
    import numpy as np
    frame = xc.read_parquet(Path(collection)/xc.FRAME_FILE, columns=list(KEYS))
    users = frame['user_id'].to_numpy(dtype=np.int64)
    items = frame['item_id'].to_numpy(dtype=np.int64)
    if len(frame) and not bool(np.all((users[1:] > users[:-1]) | ((users[1:] == users[:-1]) & (items[1:] > items[:-1])))):
        raise ValueError('frame.parquet rows must be unique and in (user_id, item_id) order')
    return frame.astype({'user_id': 'int64', 'item_id': 'int64'})


def _collection_identity(collection):
    collection = Path(collection).resolve()
    return dict(name=collection.name, path=_relative(collection),
                manifest_sha256=xc.sha256_file(collection/xc.MANIFEST_FILE))


def prepare_probe(dataset, collection, name=None, export_dir=None, threads=None):
    """probe/<name>/: keys.parquet, stats.json (adapter.probe_stats on the pool) and probe.json."""
    threads = _threads(xc.THREADS['probe'] if threads is None else threads)
    adapter = xc.adapter(dataset)
    anchor = adapter.anchors()['probe']
    base = xc.read_base(dataset)
    collection = Path(collection).resolve()
    manifest = xc.read_collection(collection, dataset=dataset, role='probe', base=base)
    xc.require(xc.anchor_text(manifest['anchor']) == xc.anchor_text(anchor),
               f'The probe collection must be at the probe anchor {anchor}')
    exported = None if export_dir is None else check_export(dataset, export_dir, anchor)
    xc.require(not dataset_runs(dataset), f'{dataset} already has a run; a new probe would start a new run family')
    pool = [int(u) for u in adapter.probe_pool()]
    xc.require(pool and len(set(pool)) == len(pool), 'The probe pool must be distinct users')
    keys = _frame_keys(collection)
    xc.require(set(keys['user_id'].tolist()) <= set(pool), 'Probe frame users must come from the probe pool')
    sources = adapter.coverage_sources()
    frame_columns = list(xc.read_parquet(collection/xc.FRAME_FILE).columns)
    for column in [*sources.get('recent', []), *sources.get('global', []), *xc.base_feature_names(base)]:
        xc.require(column in frame_columns, f'frame.parquet lacks {column}')
    out = xc.new_output(xc.output_dir(dataset, 'probe', _output_name(name, collection.name)))
    report = dict(format=PROBE_FORMAT, status='running', dataset=dataset, anchor=_anchor_json(anchor))
    try:
        xc.write_parquet(keys, out/KEYS_FILE, order_by='user_id, item_id')
        stats = adapter.probe_stats(anchor, pool)
        xc.require(isinstance(stats, dict) and stats, 'probe_stats() must give a non-empty dict')
        xc.atomic_json(out/STATS_FILE, stats)
        report.update(status='completed', users=len(pool), frame_users=int(keys['user_id'].nunique()),
                      rows=len(keys), collection=_collection_identity(collection), base_digest=base['digest'],
                      coverage_sources={k: list(sources.get(k, [])) for k in ('recent', 'global')},
                      limits=limits(dataset), threads=threads, export_digest=exported,
                      files={n: xc.sha256_file(out/n) for n in PROBE_FILES}, code=xc.code_identity(dataset),
                      created_utc=xc.utc_now())
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}'[:2000])
        raise
    finally:
        xc.atomic_json(out/'probe.json', report)
    return dict(report, path=str(out))


_PROBE_CACHE = {}


def read_probe(dataset, probe):
    """probe.json of a completed probe with its files, its collection and the frozen base checked."""
    probe = Path(probe).resolve()
    record = xc.read_json(probe/'probe.json')
    xc.require(record.get('format') == PROBE_FORMAT and record.get('status') == 'completed'
               and record.get('dataset') == dataset, f'A completed {PROBE_FORMAT} probe of {dataset} is required')
    for name in PROBE_FILES:
        xc.require(xc.sha256_file(probe/name) == record['files'][name], f'Probe file changed: {name}')
    collection = Path(xc.ROOT)/record['collection']['path']
    xc.require(xc.sha256_file(collection/xc.MANIFEST_FILE) == record['collection']['manifest_sha256'],
               'The probe collection changed')
    xc.require(xc.read_base(dataset)['digest'] == record['base_digest'], 'base.json differs from the probe')
    xc.require(xc.anchor_text(record['anchor']) == xc.anchor_text(xc.adapter(dataset).anchors()['probe']),
               'The probe anchor differs from anchors()')
    return record, collection


def _load_probe(dataset, probe, threads):
    """Probe keys, coverage masks, base numeric columns, the Spearman sample and the query-ordered cohort."""
    import duckdb
    import numpy as np
    probe = Path(probe).resolve()
    record, collection = read_probe(dataset, probe)
    key = (str(probe), xc.sha256_file(probe/'probe.json'))
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    base = xc.read_base(dataset)
    xc.require(not any(NAME.fullmatch(n) or n in RESERVED for n in xc.base_feature_names(base)),
               'Base feature names may not look like agent columns (ag_*) or reserved names')
    numeric = [n for n in xc.base_feature_names(base) if n not in set(base['categorical'])]
    sources = record['coverage_sources']
    keys_path = str(probe/KEYS_FILE)
    con = duckdb.connect(':memory:')
    try:
        con.execute(f'SET threads={threads}')
        con.execute('SET python_enable_replacements=false')
        keys = con.execute('SELECT user_id, item_id FROM read_parquet(?) ORDER BY user_id, item_id',
                           [keys_path]).fetchnumpy()

        def any_present(columns):
            return ' OR '.join(f'"{c}" IS NOT NULL' for c in columns) if columns else 'false'
        casts = ''.join(f', TRY_CAST("{n}" AS DOUBLE) AS "{n}"' for n in numeric)
        frame = con.execute(f'''SELECT user_id, item_id, ({any_present(sources['recent'])}) AS _recent,
            ({any_present(sources['global'])}) AS _global{casts} FROM read_parquet(?)
            ORDER BY user_id, item_id''', [str(collection/xc.FRAME_FILE)]).fetchnumpy()
        sample = con.execute(f'''SELECT pos FROM (SELECT user_id, item_id,
            row_number() OVER (ORDER BY user_id, item_id)-1 AS pos FROM read_parquet(?))
            ORDER BY sha256(CAST(user_id AS VARCHAR) || '|' || CAST(item_id AS VARCHAR)), pos LIMIT ?''',
                             [keys_path, SAMPLE_ROWS]).fetchnumpy()['pos']
        order = xc.QUERY_ORDER_SQL.format(column='user_id')
        cohort = con.execute(f'''SELECT user_id FROM (SELECT DISTINCT user_id FROM read_parquet(?))
            ORDER BY {order}, user_id''', [keys_path]).fetchnumpy()['user_id']
    finally:
        con.close()
    users = np.asarray(keys['user_id'], dtype=np.int64)
    items = np.asarray(keys['item_id'], dtype=np.int64)
    if not (np.array_equal(np.asarray(frame['user_id'], dtype=np.int64), users) and
            np.array_equal(np.asarray(frame['item_id'], dtype=np.int64), items)):
        raise ValueError('keys.parquet and the probe frame must hold the same keys')
    data = dict(anchor=record['anchor'], keys_path=probe/KEYS_FILE, user_id=users, item_id=items,
                recent=np.asarray(_floats(frame['_recent'].astype(float)) == 1),
                global_=np.asarray(_floats(frame['_global'].astype(float)) == 1),
                base=np.column_stack([_floats(frame[n]) for n in numeric]) if numeric else np.empty((len(users), 0)),
                base_names=numeric, sample=np.asarray(sample, dtype=np.int64),
                cohort=np.asarray(cohort, dtype=np.int64),
                limits=record['limits'])
    _PROBE_CACHE.clear()
    _PROBE_CACHE[key] = data
    return data


def _align(frame, spec, level, users, items):
    """Values of a level-keyed frame on the given pairs: (value names, float64 matrix, NaN where absent)."""
    import numpy as np
    import pandas as pd
    keys = spec['levels'][level]
    names = [column for column in frame.columns if column not in keys]
    if level == 'pair':
        index = pd.MultiIndex.from_arrays([frame[k].to_numpy(dtype=np.int64) for k in keys])
        target = pd.MultiIndex.from_arrays([users, items])
    else:
        index = pd.Index(frame[keys[0]].to_numpy(dtype=np.int64))
        target = pd.Index(users if level == 'user' else items)
    if not index.is_unique:
        raise ValueError('Aligned values need unique keys')
    positions = index.get_indexer(target)
    matrix = np.full((len(positions), len(names)), np.nan)
    if names and len(frame):
        values = frame[names].to_numpy(dtype=np.float64, na_value=np.nan)
        hit = positions >= 0
        matrix[hit] = values[positions[hit]]
    with np.errstate(invalid='ignore'):
        matrix[~np.isfinite(matrix)] = np.nan
    return names, matrix


def _prior_columns(prior_values, spec, data):
    """Accepted values (frames as evaluate_proposal returned them) aligned on the probe keys."""
    import pandas as pd
    levels = {tuple(v): k for k, v in spec['levels'].items()}
    columns = {}
    for frame in prior_values or []:
        if not isinstance(frame, pd.DataFrame):
            raise ValueError('prior_values must be a list of DataFrames')
        present = tuple(k for k in spec['levels']['pair'] if k in frame.columns)
        level = levels.get(present)
        if level is None:
            raise ValueError('A prior frame needs the keys of its level')
        names, matrix = _align(frame, spec, level, data['user_id'], data['item_id'])
        for j, name in enumerate(names):
            if not isinstance(name, str) or not NAME.fullmatch(name) or name in columns:
                raise ValueError('Prior columns must be unique ag_* names')
            columns[name] = matrix[:, j]
    return columns


def _spearman(a, b):
    import numpy as np
    import pandas as pd
    both = ~(np.isnan(a) | np.isnan(b))
    if both.sum() < MIN_SPEARMAN_ROWS:
        return None
    ra = pd.Series(a[both]).rank(method='average').to_numpy()
    rb = pd.Series(b[both]).rank(method='average').to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _column(j, names, values, prior, data):
    """Coarse coverage, size and nearest column of one value column; reasons it is invalid (H&M)."""
    import numpy as np
    name, column = names[j], values[:, j]
    present = ~np.isnan(column)
    count = int(present.sum())
    distinct = int(np.unique(column[present]).size)

    def share(mask):
        return _share(present[mask].mean()) if mask.any() else None
    sample = data['sample']
    reference = [(other, data['base'][sample, i]) for i, other in enumerate(data['base_names'])]
    reference += [(other, prior[other][sample]) for other in prior]
    reference += [(other, values[sample, k]) for k, other in enumerate(names) if k != j]
    best = nearest = None
    for other, series in reference:
        rho = _spearman(column[sample], series)
        if rho is not None and (best is None or abs(rho) > best):
            best, nearest = abs(rho), other
    summary = dict(name=name, non_null_share=_share(count/len(column)), non_null_share_recent=share(data['recent']),
                   non_null_share_global=share(data['global_']), distinct=log2_bucket(distinct),
                   max_abs_spearman=None if best is None else round(best, 1), nearest=nearest)
    problems = []
    if name in prior:
        problems.append(f'{name}: already accepted')
    if distinct < MIN_DISTINCT:
        problems.append(f'{name}: fewer than {MIN_DISTINCT} distinct non-NULL values')
    if count < MIN_NON_NULL:
        problems.append(f'{name}: fewer than {MIN_NON_NULL} non-NULL rows')
    if best is not None and best >= RHO_LIMIT:
        problems.append(f'{name}: |Spearman| with {nearest} reaches {RHO_LIMIT}')
    return summary, problems


def _mismatches(x, y):
    import numpy as np
    with np.errstate(invalid='ignore'):
        same = (np.isnan(x) & np.isnan(y)) | (np.abs(x-y) <= TOLERANCE*(1+np.abs(x)))
    return int((~same).sum())


def _invariance(dataset, spec, anchor, level, sql, names, values, data, threads, memory):
    """The first 1000 probe users in query order: the full probe run against two half batches."""
    import pandas as pd
    cohort = list(data['cohort'][:INVARIANCE_USERS])
    half = (len(cohort)+1)//2
    users, items = data['user_id'], data['item_id']
    timeout = data['limits']['timeouts'][level]
    differ = 0
    with tempfile.TemporaryDirectory(prefix='tlab-xfer-batch-') as scratch:
        for number, part in enumerate((cohort[:half], cohort[half:]), 1):
            if not part:
                continue
            mask = pd.Series(users).isin(set(part)).to_numpy()
            path = Path(scratch).resolve()/f'half-{number}.parquet'
            _stage_keys(pd.DataFrame({'user_id': users[mask], 'item_id': items[mask]}), path, threads)
            con = sandbox(dataset, anchor, path, threads=threads, purpose='probe', memory=memory, views=spec)
            try:
                table, got, _ = _execute(con, spec, level, sql, anchor, timeout, 'table')
            except ProposalError as exc:
                return f'batch invariance: the run on half {number} failed ({exc})'
            finally:
                _close(con)
            if got != names:
                return 'batch invariance: value columns differ between batches'
            differ += _mismatches(values[mask], _align(table, spec, level, users[mask], items[mask])[1])
    if differ:
        return (f'batch invariance: values of the first {len(cohort)} probe users differ between '
                'the full probe and its two halves')
    return None


def _record(proposal):
    source = proposal if isinstance(proposal, dict) else {}
    record = {key: source.get(key) for key in ('id', 'round', 'index', *FIELDS)}
    record.update(status='invalid', error=None, seconds=None, rows=None, columns=[])
    return record


def evaluate_proposal(dataset, probe, proposal, prior_values, threads=3, memory=MEMORY):
    """H&M section 2 record of one proposal on the probe, and its values (level keys + ag_*) when valid.

    Every number in the record is coarse; the exact seconds of a valid proposal ride on
    the returned frame (attrs['probe_seconds']) for the loop's budget only.
    """
    threads = _threads(threads)
    data = _load_probe(dataset, probe, threads)
    anchor = data['anchor']
    spec = _views(dataset, anchor, 'probe')
    prior = _prior_columns(prior_values, spec, data)
    record = _record(proposal)
    try:
        level, sql = _fields(proposal)
        check_sql(dataset, sql, level)
        con = sandbox(dataset, anchor, data['keys_path'], threads=threads, purpose='probe', memory=memory, views=spec)
        try:
            started = time.monotonic()
            table, names, rows = _execute(con, spec, level, sql, anchor, data['limits']['timeouts'][level], 'table')
            seconds = time.monotonic()-started
        finally:
            _close(con)
    except ProposalError as exc:
        record['error'] = _clip(exc)
        return record, None
    record.update(seconds=log2_bucket(seconds), rows=log2_bucket(rows))
    values = _align(table, spec, level, data['user_id'], data['item_id'])[1]
    reasons = []
    for j in range(len(names)):
        summary, problems = _column(j, names, values, prior, data)
        record['columns'].append(summary)
        reasons += problems
    problem = _invariance(dataset, spec, anchor, level, sql, names, values, data, threads, memory)
    if problem:
        reasons.append(problem)
    if reasons:
        record['error'] = _clip('; '.join(reasons))
        return record, None
    record['status'] = 'valid'
    table.attrs['probe_seconds'] = round(seconds, 3)
    return record, table


# ---------------------------------------------------------------- prompt and feedback

def _bucket(value):
    return value if _is_bucket(value) else 'n/a'


def _coarse(value, digits):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 'n/a'
    return f'{round(float(value), digits):.{digits}f}'


def _text(value, lines=False):
    if value is None:
        return ''
    text = redact(value)
    if lines:
        return '\n'.join(line.rstrip() for line in text.strip().splitlines())
    return ' '.join(text.split())


def _column_names(record):
    return [column['name'] for column in record.get('columns') or []]


def _attempt_lines(record):
    status = record.get('status')
    facts = [f'{_bucket(record[key])} {unit}' for key, unit in (('seconds', 's'), ('rows', 'rows'))
             if record.get(key) is not None]
    lines = [f"{_text(record.get('id'))} {_text(record.get('name'))} [{_text(record.get('level'))}]: {status}" +
             (f" ({', '.join(facts)})" if facts else '')]
    lines.append(f"  idea: {_text(record.get('idea'))}")
    if status != 'valid' and record.get('error'):
        lines.append(f"  reason: {_text(record['error'])}")
    forms = dict(share=lambda v: _coarse(v, 2), bucket=_bucket, rho=lambda v: _coarse(v, 1), name=_text)
    for column in record.get('columns') or []:
        if isinstance(column, dict):
            parts = [f'{label} {forms[form](column[key])}' for key, label, form in COLUMN_STATS if key in column]
            lines.append(f"  {_text(column.get('name'))}: {', '.join(parts)}")
    lines.append('  sql: ' + _text(record.get('sql'), lines=True).replace('\n', '\n    '))
    return lines


def format_feedback(history):
    """The ``history`` substitution: the accepted columns and every earlier attempt with validity and
    coarse coverage only (H&M section 2); '' before the first attempt. The section heading, the round
    and the budget line belong to the template."""
    if not history:
        return ''
    accepted = [name for record in history if record.get('status') == 'valid' for name in _column_names(record)]
    lines = ['Agent columns accepted earlier in this run, also in the model: ' +
             (', '.join(_text(name) for name in accepted) if accepted else '(none)')]
    for record in history:
        lines.extend(_attempt_lines(record))
    # the agent's own words are echoed back; names it must not see are masked, not refused
    return NAMES_IN_SUBSTITUTIONS.sub('<name>', redact('\n'.join(lines)))


def feedback_budget(left):
    """The probe seconds left as passed to prompt_substitutions: rounded down to 10 s."""
    return {key: _tens(value) for key, value in left.items()}


def feedback_outputs(text, round_index, rounds, budget):
    """Everything the feedback formatter puts into the substitutions: the history text,
    the round counters and the budget left in tens (the whitelist of the number test)."""
    return [text, f'round {round_index} of {rounds}', json.dumps(budget, sort_keys=True)]


def _leaves(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


def prompt_number_problems(substitutions, stats, base, constants, feedback):
    """Numbers of the substitutions (contract 3 regex) found in none of stats.json, base.json,
    PROMPT_CONSTANTS and the feedback formatter output: [(slot, token), ...]; [] when clean.

    A token passes when it appears as a token there or equals one of their numeric values.
    The template text is not tested.
    """
    tokens, values = set(), set()

    def add_text(text):
        for token in NUMBER.findall(text):
            tokens.add(token)
            values.add(float(token))
    for source in (stats, base, constants):
        for leaf in _leaves(source):
            if isinstance(leaf, bool) or leaf is None:
                continue
            if isinstance(leaf, (int, float)):
                if math.isfinite(leaf):
                    values.update((float(leaf), abs(float(leaf))))
                add_text(json.dumps(leaf))
                add_text(str(leaf))
            else:
                add_text(str(leaf))
    for part in ([feedback] if isinstance(feedback, str) else feedback):
        add_text(str(part))
    problems = []
    for slot, value in substitutions.items():
        text = value if isinstance(value, str) else json.dumps(_plain(value), ensure_ascii=False)
        for token in NUMBER.findall(text):
            if token not in tokens and float(token) not in values:
                problems.append((str(slot), token))
    return problems


def prompt_identity(dataset):
    """Digest of the template and PROMPT_CONSTANTS (run.json, set, prereg check)."""
    adapter = xc.adapter(dataset)
    template, constants = adapter.PROMPT_TEMPLATE, adapter.PROMPT_CONSTANTS
    xc.require(isinstance(template, str) and isinstance(constants, dict), 'PROMPT_TEMPLATE and PROMPT_CONSTANTS needed')
    return dict(template_sha256=hashlib.sha256(template.encode('utf-8')).hexdigest(),
                constants_digest=xc.canonical_digest(constants),
                digest=xc.canonical_digest(dict(template=template, constants=constants)))


def prompt_digest(dataset):
    """The set's ``prompt_digest``: canonical digest of PROMPT_TEMPLATE and PROMPT_CONSTANTS (xfer_model prereg)."""
    return prompt_identity(dataset)['digest']


def render_prompt(dataset, stats, base, history, round_index, rounds, left):
    """PROMPT_TEMPLATE.format(**prompt_substitutions(...)) after the number test of the substitutions."""
    adapter = xc.adapter(dataset)
    budget_limits = limits(dataset)['budget']
    feedback = format_feedback(history)
    budget = feedback_budget({key: left[key] for key in budget_limits})
    substitutions = adapter.prompt_substitutions(stats, base, feedback, round_index, budget)
    if not isinstance(substitutions, dict):
        raise ValueError('prompt_substitutions() must give a dict')
    problems = prompt_number_problems(substitutions, stats, base, adapter.PROMPT_CONSTANTS,
                                      feedback_outputs(feedback, round_index, rounds, budget))
    if problems:
        shown = ', '.join(f'{slot}:{token}' for slot, token in problems[:10])
        raise ValueError(f'Prompt substitutions carry numbers outside stats, base, constants and feedback: {shown}')
    prompt = adapter.PROMPT_TEMPLATE.format(**substitutions)
    if WARNING not in ' '.join(prompt.split()):
        raise ValueError('The prompt lacks the contract warning verbatim')
    for slot, value in substitutions.items():
        hit = NAMES_IN_SUBSTITUTIONS.search(value if isinstance(value, str) else json.dumps(_plain(value)))
        if hit:
            raise ValueError(f'The prompt slot {slot} names {hit.group(0)!r}')
    hit = NAMES_IN_PROMPT.search(prompt)
    if hit:
        raise ValueError(f'The prompt names {hit.group(0)!r}')
    return prompt


# ---------------------------------------------------------------- run

def column_problem(level, names, taken, reserved):
    """Contract 1.4 for the columns of a valid proposal; None when they may join the set."""
    if level not in LEVELS:
        return 'level must be pair, user or item'
    if not 1 <= len(names) <= MAX_VALUES:
        return 'a proposal has 1 to 3 value columns'
    if len(set(names)) != len(names):
        return 'value column names repeat'
    for name in names:
        if not isinstance(name, str) or not NAME.fullmatch(name):
            return f'column {name} does not match ^ag_[a-z][a-z0-9_]{{1,38}}$'
        if name in reserved:
            return f'column {name} is a base feature or reserved name'
        if name in taken:
            return f'column {name} is already accepted'
    return None


def probe_seconds(values):
    seconds = getattr(values, 'attrs', {}).get('probe_seconds')
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        return None
    return float(seconds)


def settle(record, proposal, values, taken, reserved):
    """The loop's JSON-safe copy of one evaluate_proposal record (H&M settle)."""
    if not isinstance(record, dict) or record.get('status') not in STATUSES:
        raise RuntimeError('evaluate returned no record with status valid, invalid or budget')
    record = _plain(record)
    record.update({key: proposal[key] for key in ('id', 'round', 'index', *FIELDS)})
    columns = record.get('columns') or []
    if not isinstance(columns, list) or not all(isinstance(c, dict) and isinstance(c.get('name'), str) for c in columns):
        raise RuntimeError('evaluate returned columns without names')
    record['columns'] = columns
    record['error'] = None if record.get('error') is None else _clip(record['error'])
    if record['status'] != 'valid':
        return record
    if not _is_bucket(record.get('seconds')):
        raise RuntimeError('A valid record needs its probe seconds as a log2 bucket')
    names = _column_names(record)
    if values is None or not set(names) <= set(getattr(values, 'columns', ())):
        raise RuntimeError('A valid record needs probe values with its columns')
    if probe_seconds(values) is None:
        raise RuntimeError("A valid record needs finite non-negative values.attrs['probe_seconds']")
    problem = column_problem(record['level'], names, taken, reserved)
    if problem:
        record.update(status='invalid', error=problem)
    return record


def _run_name(path):
    path = Path(path)
    if not RUN_NAME.fullmatch(path.name):
        raise ValueError(f'A run directory is named run-<id> ([A-Za-z0-9._-]); got {path.name!r}')


def dataset_runs(dataset):
    """Every run directory of the dataset, whatever its probe: {run dir: run.json record}.

    A ``run-*`` directory without a readable xfer run.json counts as a failed run with no
    error type: it blocks a new run and cannot be retried.
    """
    root = xc.output_dir(dataset, 'run')
    runs = {}
    if not root.exists():
        return runs
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not RUN_NAME.fullmatch(path.name):
            continue
        try:
            record = xc.read_json(path/'run.json')
        except (OSError, ValueError):
            record = None
        if not isinstance(record, dict) or record.get('format') != RUN_FORMAT:
            record = dict(status='failed', error=None, retry_of=None, unreadable=True)
        runs[path.resolve()] = record
    return runs


def run_family(dataset, output, probe_sha256, retry_of=None, reason=None):
    """One run per dataset (contract 3): a new run only where the dataset has none, or as the
    declared retry of a failed run on the same probe, at most MAX_RETRIES over the chain."""
    output = Path(output).resolve()
    _run_name(output)
    if (retry_of is None) != (reason is None):
        raise ValueError('--retry-of and --reason go together')
    runs = {path: record for path, record in dataset_runs(dataset).items() if path != output}
    if retry_of is None:
        if runs:
            raise ValueError(f'{dataset} already has a run ({min(runs).name}); a new run is only a declared retry '
                             'of a failed one (--retry-of, --reason)')
        return None
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('A retry needs a non-empty --reason')
    previous = Path(retry_of).resolve()
    if previous not in runs:
        raise ValueError(f'--retry-of must name a run of {dataset}')
    status = runs[previous].get('status')
    if status != 'failed':
        raise ValueError(f'{previous.name} is not failed (status {status}); only a failed run is retried')
    kind = (runs[previous].get('error') or {}).get('type')
    if not isinstance(kind, str):
        raise ValueError(f'{previous.name} records no error type; only a technical failure is retried')
    if kind == OPERATOR_ABORT:
        raise ValueError(f'{previous.name} was stopped by the operator; an abort is not retried')
    if (runs[previous].get('probe') or {}).get('probe_sha256') != probe_sha256:
        raise ValueError(f'A retry runs on the probe of {previous.name}')
    for path, record in sorted(runs.items()):
        if record.get('status') == 'completed':
            raise ValueError(f'{path.name} completed on {dataset}; no further run is made')
        if record.get('retry_of') == str(previous):
            raise ValueError(f'{previous.name} was already retried by {path.name}')
    if sum(1 for record in runs.values() if record.get('retry_of') is not None) >= MAX_RETRIES:
        raise ValueError(f'{dataset} already has {MAX_RETRIES} retries')
    return str(previous)


def write_values(values, path):
    xc.write_parquet(values.reset_index(drop=True), path)
    return dict(rows=int(len(values)), sha256=xc.sha256_file(path))


def _append(path, record):
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n')


class _RunLock:
    def __init__(self, dataset):
        root = xc.output_dir(dataset, 'run')
        root.mkdir(parents=True, exist_ok=True)
        self.path = root/'.run.lock'

    def __enter__(self):
        try:
            os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise ValueError(f'Another run holds {self.path}') from None
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


def probe_identity(dataset, probe):
    probe = Path(probe).resolve()
    record, _ = read_probe(dataset, probe)
    return dict(path=_relative(probe), anchor=record['anchor'], users=record['users'], rows=record['rows'],
                collection=record['collection'], probe_sha256=xc.sha256_file(probe/'probe.json'),
                stats_sha256=record['files'][STATS_FILE], base_digest=record['base_digest'])


def run_loop(dataset, probe, name=None, rounds=ROUNDS, proposals=PROPOSALS, model=MODEL, max_calls=MAX_CALLS,
             threads=None, ask=None, evaluate=None, retry_of=None, reason=None):
    """Rounds of LLM proposals checked on the probe (H&M run_loop); returns the run.json record."""
    threads = xc.THREADS['agent'] if threads is None else threads
    for label, value in (('rounds', rounds), ('proposals', proposals), ('max_calls', max_calls), ('threads', threads)):
        if type(value) is not int or value < 1:
            raise ValueError(f'{label} must be a positive integer')
    if max_calls > MAX_CALLS:
        raise ValueError(f'max_calls above {MAX_CALLS} is refused')
    if model != MODEL:
        raise ValueError(f'The model is {MODEL}')
    ask = ask_llm if ask is None else ask
    evaluate = evaluate_proposal if evaluate is None else evaluate
    output = xc.output_dir(dataset, 'run', _output_name(name, f'run-{_stamp()}'))
    _run_name(output)
    identity = probe_identity(dataset, probe)
    run_family(dataset, output, identity['probe_sha256'], retry_of, reason)
    probe = Path(probe).resolve()
    stats = xc.read_json(probe/STATS_FILE)
    base = xc.read_base(dataset)
    budget_limits = dict(limits(dataset)['budget'])
    render_prompt(dataset, stats, base, [], 1, rounds, budget_limits)  # refuses before any output or call
    reserved = frozenset(xc.base_feature_names(base)) | RESERVED
    code = xc.code_identity(dataset)
    used = dict.fromkeys(budget_limits, 0.0)
    with _RunLock(dataset):
        retried = run_family(dataset, output, identity['probe_sha256'], retry_of, reason)
        out = xc.new_output(output)
        (out/'values').mkdir()
        log = out/'log.jsonl'
        log.touch()
        report = dict(format=RUN_FORMAT, dataset=dataset, status='running', id=out.name.removeprefix('run-'),
                      model=model, retry_of=retried, reason=None if retried is None else reason.strip(),
                      llm_command=None, rounds=rounds, proposals_per_round=proposals, max_calls=max_calls,
                      threads=threads, probe=identity, base_digest=base['digest'], prompt=prompt_identity(dataset),
                      budget=dict(limits=budget_limits, used=dict(used)), calls=0, cost_usd=0.0,
                      cost_unknown_calls=0, rounds_run=0, stop=None, attempts=0, valid=0, columns=[], call_log=[],
                      prompts={}, values={}, probe_seconds={}, code=code, started_at_utc=xc.utc_now())
        xc.atomic_json(out/'run.json', report)
    try:
        history, prior = [], []
        for number in range(1, rounds+1):
            if report['calls'] >= max_calls:
                report['stop'] = 'max_calls'
                break
            left = {key: budget_limits[key]-used[key] for key in budget_limits}
            prompt = render_prompt(dataset, stats, base, history, number, rounds, left)
            (out/f'prompt-r{number}.txt').write_text(prompt, encoding='utf-8', newline='\n')
            report['prompts'][f'r{number}'] = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            report['rounds_run'] = number
            attempts, items = [], None
            for attempt in (1, 2):  # the second call only after a failed or unparsable one
                if report['calls'] >= max_calls:
                    break
                report['calls'] += 1
                call, meta = dict(round=number, attempt=attempt), None
                try:
                    reply, meta = ask(prompt, model)
                    items = parse_reply(json.dumps(reply))
                    call['status'] = 'ok'
                except Exception as exc:
                    meta = getattr(exc, 'meta', meta)
                    call.update(status='failed', error=clean_error(f'{type(exc).__name__}: {exc}'))
                meta = _plain(meta) if isinstance(meta, dict) else {}
                if meta.get('command') is not None and report['llm_command'] is None:
                    report['llm_command'] = meta['command']
                cost = meta.get('cost_usd')
                cost = float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) and \
                    math.isfinite(cost) and cost >= 0 else None
                call.update(seconds=meta.get('seconds'), cost_usd=cost, init=meta.get('init'))
                if cost is None:
                    report['cost_unknown_calls'] += 1
                else:
                    report['cost_usd'] = round(report['cost_usd']+cost, 6)
                if items is not None:
                    call.update(proposals=len(items), kept=min(len(items), proposals))
                report['call_log'].append(call)
                attempts.append(dict(call, text=meta.get('text'),
                                     meta={k: v for k, v in meta.items() if k not in ('text', 'init', 'command')}))
                xc.atomic_json(out/'run.json', report, exist_ok=True)
                if items is not None:
                    break
            kept = (items or [])[:proposals]
            xc.atomic_json(out/f'reply-r{number}.json', dict(round=number, llm_command=report['llm_command'],
                                                             attempts=attempts, kept=len(kept)))
            if items is None:
                report.update(stop=RETRIES_EXHAUSTED, failed_round=number)
                if len(attempts) == 2:
                    raise RuntimeError(f'Round {number}: the call and its retry both failed or were unparsable')
                raise RuntimeError(f'Round {number}: the call failed or was unparsable and max_calls leaves '
                                   'no call for its retry')
            for index, item in enumerate(kept, 1):
                proposal = dict(id=f'r{number}p{index}', round=number, index=index, **item)
                loadavg = list(os.getloadavg())
                try:
                    record, values = evaluate(dataset, probe, dict(proposal), list(prior), threads=threads)
                except ProposalError as exc:
                    record, values = dict(status='invalid', error=f'ProposalError: {exc}', seconds=None,
                                          rows=None, columns=[]), None
                taken = {n for earlier in history if earlier['status'] == 'valid' for n in _column_names(earlier)}
                record = settle(record, proposal, values, taken, reserved)
                record['loadavg'] = loadavg
                if record['status'] == 'valid':
                    key, seconds = budget_key(record['level']), probe_seconds(values)
                    if used[key]+seconds > budget_limits[key]:
                        record.update(status='budget',
                                      error=f'over the probe budget: {key} has too little time left for this query')
                    else:
                        used[key] += seconds
                        report['probe_seconds'][record['id']] = seconds
                        report['values'][record['id']] = write_values(values, out/'values'/f"{record['id']}.parquet")
                        prior.append(values)
                _append(log, record)
                history.append(record)
                valid = [earlier for earlier in history if earlier['status'] == 'valid']
                report.update(attempts=len(history), valid=len(valid),
                              columns=[n for earlier in valid for n in _column_names(earlier)],
                              budget=dict(limits=budget_limits, used=dict(used)))
                xc.atomic_json(out/'run.json', report, exist_ok=True)
        report.update(status='completed', stop=report['stop'] or 'rounds', log_sha256=xc.sha256_file(log),
                      finished_at_utc=xc.utc_now())
        xc.atomic_json(out/'run.json', report, exist_ok=True)
        return dict(report, path=str(out))
    except BaseException as exc:
        report.update(status='failed', finished_at_utc=xc.utc_now(),
                      error=dict(type=type(exc).__name__, message=clean_error(f'{type(exc).__name__}: {exc}', limit=2048),
                                 traceback=clean_error(traceback.format_exc(limit=12), limit=8192)))
        xc.atomic_json(out/'run.json', report, exist_ok=True)
        raise


# ---------------------------------------------------------------- freeze and the set

def set_digest(proposals):
    """Identity of the frozen set: canonical_digest([[id, level, sql, columns], ...])."""
    return xc.canonical_digest([[p['id'], p['level'], p['sql'], list(p['columns'])] for p in proposals])


def check_set(dataset, record, base=None):
    """An xfer set with its schema, SQL rules, column names and digest checked."""
    xc.require(isinstance(record, dict) and record.get('format') == SET_FORMAT, f'An agent set of {SET_FORMAT} is required')
    xc.require(record.get('dataset') == dataset, 'Agent set of another dataset')
    missing = [key for key in SET_FIELDS if key not in record]
    xc.require(not missing, f'The agent set lacks {", ".join(missing)}')
    xc.require(isinstance(record['proposals'], list) and record['proposals'], 'The agent set has no proposals')
    if base is not None:
        xc.require(record['base_digest'] == base['digest'], 'The agent set was made on another base')
        reserved = frozenset(xc.base_feature_names(base)) | RESERVED
    else:
        reserved = RESERVED
    rules = sql_rules(dataset)
    seen, last = [], (0, 0)
    for proposal in record['proposals']:
        pid = proposal.get('id') if isinstance(proposal, dict) else None
        xc.require(isinstance(pid, str), 'Every proposal needs a string id')
        try:
            level, sql = _fields(proposal)
            check_sql(dataset, sql, level, rules)
        except ProposalError as exc:
            raise ProposalError(f'{pid}: {exc}') from None
        number, index = proposal.get('round'), proposal.get('index')
        xc.require(type(number) is int and type(index) is int and min(number, index) >= 1 and pid == f'r{number}p{index}',
                   f'{pid}: the id must be r<round>p<index>')
        xc.require((number, index) > last, f'{pid}: proposals must follow increasing (round, index)')
        last = (number, index)
        columns = proposal.get('columns')
        xc.require(isinstance(columns, list) and 1 <= len(columns) <= MAX_VALUES, f'{pid}: 1 to 3 columns required')
        for name in columns:
            xc.require(isinstance(name, str) and NAME.fullmatch(name) and name not in reserved and name not in seen,
                       f'{pid}: column {name!r} breaks the naming contract or repeats')
            seen.append(name)
    xc.require(record['columns'] == seen, 'The set columns must list the proposal columns in order')
    xc.require(record['digest'] == set_digest(record['proposals']), 'The agent set differs from its digest')
    xc.require(isinstance(record['prompt'], dict) and record['prompt_digest'] == record['prompt'].get('digest'),
               'prompt_digest differs from the prompt identity')
    return record


def read_set(dataset, path=None, base=None):
    path = xc.config_path(dataset, 'set') if path is None else Path(path)
    return check_set(dataset, xc.read_json(path), base)


def freeze(dataset, run_dir):
    """configs/datasets/xfer-<x>-set.json from a completed run: every valid proposal in (round, index) order."""
    run_dir = Path(run_dir).resolve()
    _run_name(run_dir)
    xc.require(run_dir.parent == xc.output_dir(dataset, 'run').resolve(),
               f'Only a run under {xc.output_dir(dataset, "run")} is frozen')
    run = xc.read_json(run_dir/'run.json')
    xc.require(isinstance(run, dict) and run.get('format') == RUN_FORMAT and run.get('status') == 'completed'
               and run.get('dataset') == dataset, 'Only a completed xfer run of this dataset is frozen')
    completed = {p for p, r in dataset_runs(dataset).items() if r.get('status') == 'completed'}
    completed.add(run_dir)
    xc.require(len(completed) == 1, f'More than one completed run of {dataset}; the one-run rule leaves nothing to choose')
    log = run_dir/'log.jsonl'
    xc.require(xc.sha256_file(log) == run.get('log_sha256'), 'log.jsonl differs from the one the run completed with')
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()]
    order = [(r['round'], r['index']) for r in records]
    xc.require(len(records) == run.get('attempts') and order == sorted(order) and len(set(order)) == len(order)
               and all(r['id'] == f"r{r['round']}p{r['index']}" for r in records),
               'log.jsonl records are not unique and in (round, index) order')
    base = xc.read_base(dataset)
    xc.require(base['digest'] == run['base_digest'], 'base.json changed since the run')
    reserved = frozenset(xc.base_feature_names(base)) | RESERVED
    budget_limits = run['budget']['limits']
    exact = run.get('probe_seconds')
    xc.require(isinstance(exact, dict), 'run.json holds no probe_seconds')
    proposals, taken, used = [], set(), dict.fromkeys(budget_limits, 0.0)
    for record in records:
        xc.require(record.get('status') in STATUSES, f"{record['id']}: unknown status")
        if record['status'] != 'valid':
            continue
        names = _column_names(record)
        problem = column_problem(record['level'], names, taken, reserved)
        xc.require(problem is None, f"{record['id']}: {problem}")
        xc.require(_is_bucket(record.get('seconds')), f"{record['id']}: probe seconds are not a log2 bucket")
        seconds = exact.get(record['id'])
        xc.require(isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds)
                   and seconds >= 0, f"{record['id']}: run.json holds no exact probe seconds for it")
        used[budget_key(record['level'])] += seconds
        taken.update(names)
        proposals.append(dict(id=record['id'], round=record['round'], index=record['index'], name=record['name'],
                              idea=record['idea'], level=record['level'], sql=record['sql'], columns=names,
                              probe_seconds=record['seconds']))
    xc.require(proposals, 'The run has no valid proposal; there is nothing to freeze')
    xc.require(set(exact) == {p['id'] for p in proposals}, 'run.json probe_seconds and the valid proposals differ')
    for key, limit in budget_limits.items():
        xc.require(used[key] <= limit, f'Valid proposals exceed the probe budget {key}')
    probe = run['probe']
    value = dict(format=SET_FORMAT, dataset=dataset,
                 run=dict(id=run['id'], model=run['model'], rounds=run['rounds_run'],
                          proposals_per_round=run['proposals_per_round'], calls=run['calls'],
                          cost_usd=run['cost_usd'], log_sha256=run['log_sha256']),
                 probe=dict(anchor=probe['anchor'], users=probe['users'], collection=probe['collection'],
                            probe_sha256=probe['probe_sha256'], stats_sha256=probe['stats_sha256']),
                 run_sha256=xc.sha256_file(run_dir/'run.json'),
                 base_digest=run['base_digest'], prompt=run['prompt'], prompt_digest=run['prompt']['digest'],
                 code=run['code'], proposals=proposals,
                 attempts=[dict(id=r['id'], status=r['status'], error=r.get('error')) for r in records],
                 columns=[n for p in proposals for n in p['columns']],
                 budget={key: _tens(used[key]) for key in budget_limits},
                 digest=set_digest(proposals), audit=None)
    check_set(dataset, value, base)
    output = xc.config_path(dataset, 'set')
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=False)+'\n'
    if output.exists():
        if output.read_text(encoding='utf-8') != text:
            raise FileExistsError(f'{output.name} exists with other content; it is not overwritten')
        return dict(value, path=str(output))
    xc.atomic_json(output, value)
    return dict(value, path=str(output))


# ---------------------------------------------------------------- sidecar

def _collection_for_prereg(dataset, collection, prereg, base):
    """A collection of this base and of the prereg code (or of the last deviation)."""
    manifest = xc.read_collection(collection, dataset=dataset)
    xc.require(manifest['base_digest'] == base['digest'], f'Collection {Path(collection).name} built on another base')
    codes = [prereg.get('code'), xc.latest_code(dataset, prereg)]
    xc.require(manifest.get('code') in codes, f'Collection {Path(collection).name} built by code other than the prereg')
    return manifest


def sidecar_batches(keys, batch_users=None, batch_rows=SIDECAR_BATCH_ROWS):
    """Contiguous [start, stop) row ranges of whole users over keys in (user_id, item_id) order.

    ``batch_users`` fixes the users per batch; otherwise users are added until a batch
    reaches ``batch_rows`` rows. Every batch stays within MAX_ROWS.
    """
    import numpy as np
    for label, value in (('batch_users', batch_users), ('batch_rows', batch_rows)):
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError(f'{label} must be a positive integer')
    users = keys['user_id'].to_numpy(dtype=np.int64)
    if not len(users):
        return []
    bounds = [*np.flatnonzero(np.r_[True, users[1:] != users[:-1]]).tolist(), len(users)]
    ranges = []
    if batch_users is not None:
        for i in range(0, len(bounds)-1, batch_users):
            ranges.append((bounds[i], bounds[min(i+batch_users, len(bounds)-1)]))
    else:
        begin = 0
        for stop in bounds[1:]:
            if stop-begin >= batch_rows or stop == len(users):
                ranges.append((begin, stop))
                begin = stop
    for begin, stop in ranges:
        xc.require(stop-begin <= MAX_ROWS, f'A sidecar batch of {stop-begin} rows exceeds {MAX_ROWS}')
    return ranges


def _merge_parts(parts, target, columns, threads, memory, scratch):
    """One ordered COPY of the batch parts into agent.parquet (insertion order kept)."""
    import duckdb
    con = duckdb.connect(':memory:')
    try:
        con.execute(f'SET threads={threads}')
        con.execute('SET memory_limit=?', [_memory(memory)])
        con.execute('SET temp_directory=?', [str(scratch)])
        con.execute('SET preserve_insertion_order=true')
        listing = ', '.join(_literal(p) for p in parts)
        names = ', '.join(['user_id', 'item_id', *[f'CAST("{c}" AS DOUBLE) AS "{c}"' for c in columns]])
        con.execute(f'COPY (SELECT {names} FROM read_parquet([{listing}], hive_partitioning=false)) '
                    f'TO {_literal(target)} (FORMAT PARQUET)')
    finally:
        con.close()


def _verify_sidecar(path, collection, columns, rows, threads, memory, scratch):
    """agent.parquet by DuckDB, without loading it: columns and types, row count, keys strictly
    increasing in file order and every key a frame key (so the rows are the frame rows in order)."""
    import duckdb
    con = duckdb.connect(':memory:')
    try:
        con.execute(f'SET threads={threads}')
        con.execute('SET memory_limit=?', [_memory(memory)])
        con.execute('SET temp_directory=?', [str(scratch)])
        agent, frame = _literal(path), _literal(Path(collection)/xc.FRAME_FILE)
        described = [(r[0], r[1]) for r in con.execute(f'DESCRIBE SELECT * FROM read_parquet({agent})').fetchall()]
        expected = [('user_id', 'BIGINT'), ('item_id', 'BIGINT'), *[(c, 'DOUBLE') for c in columns]]
        xc.require(described == expected, f'agent.parquet columns {described} differ from {expected}')
        count, disorder = con.execute(f'''SELECT count(*), count(*) FILTER (WHERE NOT (user_id > pu OR
            (user_id = pu AND item_id > pi))) FROM (SELECT user_id, item_id,
            lag(user_id) OVER (ORDER BY file_row_number) AS pu, lag(item_id) OVER (ORDER BY file_row_number) AS pi
            FROM read_parquet({agent}, file_row_number=true))''').fetchone()
        xc.require(count == rows, f'agent.parquet holds {count} rows, the frame {rows}')
        xc.require(disorder == 0, 'agent.parquet keys are not strictly increasing in file order')
        stray = con.execute(f'SELECT count(*) FROM read_parquet({agent}) a ANTI JOIN read_parquet({frame}) f '
                            'USING (user_id, item_id)').fetchone()[0]
        xc.require(stray == 0, 'agent.parquet holds keys outside the frame')
    finally:
        con.close()


def sidecar(dataset, collection, threads=None, memory=MEMORY, batch_users=None, timeout_s=RUN_TIMEOUT,
            batch_rows=SIDECAR_BATCH_ROWS):
    """sidecars/<collection>/agent.parquet: every frozen proposal on every frame row, in frame order.

    Batches are contiguous runs of whole users (about ``batch_rows`` rows); each is written
    to its own part and freed, then one ordered COPY joins the parts. Item tables are
    cached across batches.
    """
    import numpy as np
    threads = _threads(xc.THREADS['sidecar'] if threads is None else threads)
    prereg = xc.require_prereg(dataset)
    base = xc.read_base(dataset)
    set_path = xc.config_path(dataset, 'set')
    agent = read_set(dataset, set_path, base)
    set_sha256 = xc.sha256_file(set_path)
    xc.require(set_sha256 == prereg['set_sha256'], 'The agent set differs from the prereg')
    xc.require(agent.get('audit') is not None, 'The agent set has no SQL audit yet (audit is null)')
    collection = Path(collection).resolve()
    manifest = _collection_for_prereg(dataset, collection, prereg, base)
    anchor = manifest['anchor']
    if manifest.get('role') == 'holdout':
        current = xc.current_holdout_collection(dataset, anchor).resolve()
        xc.require(collection == current, f'{collection.name} is superseded; the holdout collection in force is '
                   f'{current.name}')
    if _after_holdout(dataset, anchor):
        xc.require_window(dataset, 'sidecar')
    final = xc.sidecar_dir(dataset, collection)
    xc.require(not final.exists(), f'{final} exists; a sidecar is never rewritten')
    keys = _frame_keys(collection)
    columns = agent['columns']
    ranges = sidecar_batches(keys, batch_users, batch_rows)
    xc.require(ranges, 'The collection frame has no rows')
    partial = xc.new_output(final.with_name(f'.partial-{final.name}-{os.getpid()}'))
    try:
        spec = _views(dataset, anchor, 'sidecar')
        parts_dir = partial/'parts'
        parts_dir.mkdir()
        cache, parts, seconds = {}, [], {}
        non_null = np.zeros(len(columns), dtype=np.int64)
        for number, (begin, stop) in enumerate(ranges):
            rows = keys.iloc[begin:stop].reset_index(drop=True)
            values, info = agent_columns(dataset, anchor, rows, agent, threads=threads, timeout_s=timeout_s,
                                         cache=cache, purpose='sidecar', memory=memory, views=spec)
            for name in KEYS:
                xc.require(np.array_equal(values[name].to_numpy(dtype=np.int64), rows[name].to_numpy(dtype=np.int64)),
                           f'Sidecar batch {number}: rows differ from the frame rows')
            block = values[[*KEYS, *columns]].astype({c: 'float64' for c in columns})
            non_null += np.isfinite(block[columns].to_numpy(dtype=np.float64)).sum(axis=0)
            part = parts_dir/f'part-{number:05d}.parquet'
            xc.write_parquet(block, part)
            parts.append(part)
            for pid, sec in info['seconds'].items():
                seconds[pid] = round(seconds.get(pid, 0.0)+sec, 3)
            del values, block, rows
        target = partial/xc.SIDECAR_FILE
        _merge_parts(parts, target, columns, threads, memory, partial)
        shutil.rmtree(parts_dir)
        _verify_sidecar(target, collection, columns, len(keys), threads, memory, partial)
        xc.atomic_json(partial/SIDECAR_REPORT, dict(
            anchor=anchor, rows=len(keys), users=int(keys['user_id'].nunique()), batches=len(ranges),
            batch_rows=batch_rows if batch_users is None else None, batch_users=batch_users, seconds=seconds,
            non_null={c: int(n) for c, n in zip(columns, non_null)}, threads=threads, set_digest=agent['digest'],
            views_digest=_spec_digest(spec), created_utc=xc.utc_now()))
        sidecar_manifest = xc.write_sidecar_manifest(partial, dataset, collection, set_sha256, columns, len(keys),
                                                     xc.latest_code(dataset, prereg))
        os.rename(partial, final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return dict(sidecar_manifest, path=str(final))


# ---------------------------------------------------------------- leakcheck

def _table_dir(path):
    path = Path(path)
    return path.parent.parent if '=' in path.parent.name else path.parent


def _place(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def _reroot(spec, dest, future=()):
    """A copy of ``spec`` reading its files from ``dest`` (same layout under the common root).

    ``future`` files (partitions starting before A_holdout but not allowed at A) are
    appended to the last allowed file of their table, so the view's own filter is
    the only thing between them and the agent. Returns (spec, injected tables).
    """
    import duckdb
    files = [Path(f) for f in spec['files']]
    future = [Path(f) for f in future]
    root = Path(os.path.commonpath([str(f.parent) for f in files+future]))
    dest = Path(dest).resolve()
    xc.require("'" not in str(dest), 'Leakcheck scratch path must be quotable')
    mapping = {f: dest/f.relative_to(root) for f in files}
    targets = {}
    for f in files:
        targets.setdefault(_table_dir(f), []).append(f)
    merged = {}
    for f in future:
        table = _table_dir(f)
        xc.require(table in targets, f'No allowed file of {table.name} to carry its future rows')
        merged.setdefault(max(targets[table], key=str), []).append(f)
    for f in files:
        if f in merged:
            mapping[f].parent.mkdir(parents=True, exist_ok=True)
            sources = [f, *sorted(merged[f], key=str)]
            con = duckdb.connect(':memory:')
            try:
                schemas = {str(p): con.execute(f'DESCRIBE SELECT * FROM read_parquet({_literal(p)})').fetchall()
                           for p in sources}
                first = schemas[str(f)]
                for path, schema in schemas.items():
                    xc.require([r[:2] for r in schema] == [r[:2] for r in first],
                               f'Leakcheck: {Path(path).name} of {_table_dir(f).name} differs in columns or types '
                               'from the allowed file; no upcast is made')
                listing = ', '.join(_literal(p) for p in sources)
                con.execute(f'''COPY (SELECT * FROM read_parquet([{listing}], hive_partitioning=false))
                    TO {_literal(mapping[f])} (FORMAT PARQUET)''')
            finally:
                con.close()
        else:
            _place(f, mapping[f])
    old, new = str(root), str(dest)
    texts = dict(spec['views'], _items=spec['items'])
    xc.require(any(old in text for text in texts.values()),
               'views() must reference its partitions by path for the leakcheck cut')
    rerooted = {name: text.replace(old, new) for name, text in texts.items()}
    xc.require(not any(old in text for text in rerooted.values()), 'Rerooting left a path to the original partitions')
    items = rerooted.pop('_items')
    return dict(spec, files=[str(mapping[f]) for f in files], views=rerooted, items=items), len(merged)


def time_columns(spec):
    """Event-time column names: views()['time_columns'] when the adapter gives them, else the schema
    columns of TIMESTAMP or DATE type and any column named t."""
    if spec.get('time_columns'):
        names = set(spec['time_columns'].values())
    else:
        names = {name for columns in (spec.get('schema') or {}).values() for name, kind in columns
                 if TIME_TYPE.fullmatch(str(kind)) or name == 't'}
    xc.require(names, 'Leakcheck needs the event-time column of the views (time_columns or schema)')
    return names


def file_times(files, names, anchor):
    """Partition files read directly (no view): rows, rows at or after the anchor, files without time."""
    import duckdb
    result = dict(files=0, static_files=0, rows=0, rows_at_or_after=0)
    con = duckdb.connect(':memory:')
    try:
        con.execute('SET python_enable_replacements=false')
        for path in files:
            source = f'read_parquet({_literal(path)}, hive_partitioning=false)'
            kinds = {r[0]: r[1] for r in con.execute(f'DESCRIBE SELECT * FROM {source}').fetchall()}
            present = sorted(n for n in names if n in kinds)
            if not present:
                result['static_files'] += 1
                continue
            late = ' OR '.join(f'"{n}" >= CAST(? AS {kinds[n]})' for n in present)
            rows, after = con.execute(f'SELECT count(*), count(*) FILTER (WHERE {late}) FROM {source}',
                                      [xc.anchor_text(anchor)]*len(present)).fetchone()
            result['files'] += 1
            result['rows'] += int(rows)
            result['rows_at_or_after'] += int(after)
    finally:
        con.close()
    return result


def cell_mismatches(left, right, columns):
    """Per column: cells where exactly one side is NULL or |x-y| > 1e-9*(1+|x|) (H&M)."""
    import numpy as np
    counts = {}
    for name in columns:
        x = left[name].to_numpy(dtype=np.float64, na_value=np.nan)
        y = right[name].to_numpy(dtype=np.float64, na_value=np.nan)
        x_null, y_null = ~np.isfinite(x), ~np.isfinite(y)
        with np.errstate(invalid='ignore', over='ignore'):
            close = np.abs(x-y) <= TOLERANCE*(1+np.abs(x))
        counts[name] = int((~((x_null & y_null) | (~x_null & ~y_null & close))).sum())
    return counts


def _align_rows(keys, values, columns):
    merged = keys[list(KEYS)].reset_index(drop=True).merge(values[[*KEYS, *columns]], on=list(KEYS), how='left',
                                                          validate='one_to_one', indicator='_xfer_match')
    xc.require(len(merged) == len(keys) and bool((merged['_xfer_match'] == 'both').all()),
               'Agent values must cover exactly the given keys')
    return merged.drop(columns='_xfer_match')


def leak_keys(collection, users):
    """Frame keys of the first ``users`` users of the collection in query order, and those users."""
    keys = _frame_keys(collection)
    selected = xc.cap_queries(keys['user_id'].unique().tolist(), users)
    rows = keys[keys['user_id'].isin(set(selected))].reset_index(drop=True)
    return rows, selected


def leakcheck(dataset, users=LEAK_USERS, name=None, threads=None, memory=MEMORY, timeout_s=RUN_TIMEOUT):
    """Contract 3 leakcheck on the last train anchor and the holdout anchor (counts only, never values).

    Per anchor: the production sandbox, the cut directory (only partitions allowed at A)
    and the full history (partitions starting before A_holdout; the not-allowed ones are
    appended into an allowed file, so only the view filter removes them) on the first
    ``users`` users in query order; then those users in 4 batches against one.
    """
    import pandas as pd
    threads = _threads(xc.THREADS['sidecar'] if threads is None else threads)
    if type(users) is not int or users < 1:
        raise ValueError('users must be a positive integer')
    prereg = xc.require_prereg(dataset)
    base = xc.read_base(dataset)
    set_path = xc.config_path(dataset, 'set')
    agent = read_set(dataset, set_path, base)
    columns = agent['columns']
    anchors = xc.adapter(dataset).anchors()
    holdout = anchors['holdout']
    last_train = max(anchors['roles']['train'], key=xc.anchor_int)
    collections = [(last_train, xc.output_dir(dataset, 'collections', xc.collection_name('train', last_train))),
                   (holdout, xc.current_holdout_collection(dataset, holdout))]
    manifests = {}
    for anchor, path in collections:
        manifest = _collection_for_prereg(dataset, path, prereg, base)
        xc.require(xc.anchor_text(manifest['anchor']) == xc.anchor_text(anchor), f'{path.name}: anchor differs')
        manifests[path] = manifest
    full_files = _views(dataset, holdout, 'leakcheck')['files']
    out = xc.new_output(xc.output_dir(dataset, 'leakcheck', _output_name(name, f'leakcheck-{_stamp()}')))
    report = dict(format=LEAKCHECK_FORMAT, dataset=dataset, status='running', ok=False, users=users,
                  batches=LEAK_BATCHES,
                  tolerance='two NULLs equal, else |x-y| <= 1e-9*(1+|x|); NULL = missing, NaN or +-inf',
                  values='never recorded; counts only', set_sha256=xc.sha256_file(set_path),
                  set_digest=agent['digest'], code=xc.latest_code(dataset, prereg), anchors={})
    try:
        for anchor, path in collections:
            keys, selected = leak_keys(path, users)
            spec = _views(dataset, anchor, 'leakcheck')
            future = sorted(set(full_files)-set(spec['files']))

            names = time_columns(spec)
            # the cut, read without any view: nothing at or after A may sit in an allowed partition
            cut_times = file_times(spec['files'], names, anchor)
            xc.require(cut_times['files'] > 0, f'Leakcheck at {anchor}: no allowed partition carries a time column')
            future_times = file_times(future, names, anchor)
            if anchor == last_train:
                xc.require(future, f'Leakcheck at the last train anchor {anchor}: no partition starts between it and '
                           'A_holdout, so nothing would be injected')
                xc.require(future_times['rows_at_or_after'] > 0, f'Leakcheck at {anchor}: the injected partitions '
                           'hold no rows at or after the anchor')

            def run(rows, views, cache=None):
                values = agent_columns(dataset, anchor, rows, agent, threads=threads, timeout_s=timeout_s, cache=cache,
                                       purpose='leakcheck', memory=memory, views=views)[0]
                return _align_rows(rows, values, columns)

            def in_batches(views, cache):
                size = math.ceil(len(selected)/LEAK_BATCHES)
                parts = []
                for start in range(0, len(selected), size):
                    part = keys[keys['user_id'].isin(set(selected[start:start+size]))].reset_index(drop=True)
                    parts.append(run(part, views, cache))
                return _align_rows(keys, pd.concat(parts, ignore_index=True), columns), len(parts)
            production = run(keys, spec)
            with tempfile.TemporaryDirectory(prefix='cut-', dir=out) as scratch:
                cut_spec, _ = _reroot(spec, Path(scratch)/'cut')
                full_spec, injected = _reroot(spec, Path(scratch)/'full', future)
                cut = run(keys, cut_spec)
                full = run(keys, full_spec)
            leak = cell_mismatches(full, cut, columns)
            drift = cell_mismatches(production, cut, columns)
            batched, batches = in_batches(spec, None)
            invariance = cell_mismatches(production, batched, columns)
            cached_run, _ = in_batches(spec, {})  # one item cache over the batches, as the sidecar runs
            cached = cell_mismatches(production, cached_run, columns)
            bad = (sum(leak.values())+sum(drift.values())+sum(invariance.values())+sum(cached.values())
                   + cut_times['rows_at_or_after'])
            report['anchors'][xc.anchor_text(anchor)] = dict(
                collection=_collection_identity(path), users=len(selected), rows=len(keys), columns=len(columns),
                time_columns=sorted(names), allowed_files=len(spec['files']),
                cut_rows_at_or_after_anchor=cut_times['rows_at_or_after'], future_files=len(future),
                future_injected_tables=injected, injected_rows=future_times['rows'],
                injected_rows_at_or_after_anchor=future_times['rows_at_or_after'], degenerate=not future,
                invariance_batches=batches, leak_mismatches=leak, production_mismatches=drift,
                invariance_mismatches=invariance, cached_mismatches=cached, ok=bad == 0,
                result='OK' if bad == 0 else 'LEAK')
        report['ok'] = len(report['anchors']) == len(collections) and all(a['ok'] for a in report['anchors'].values())
        report['result'] = 'OK' if report['ok'] else 'LEAK'
        report['status'] = 'completed'
        report['finished_at_utc'] = xc.utc_now()
    except Exception as exc:
        report.update(status='failed', ok=False, error=f'{type(exc).__name__}: {exc}'[:2000])
        raise
    finally:
        xc.atomic_json(out/'report.json', report)
    if report['result'] != 'OK':
        raise ValueError(f'leakcheck: LEAK at {", ".join(a for a, r in report["anchors"].items() if r["result"] != "OK")}; '
                         f'see {out/"report.json"}')
    return dict(report, path=str(out))


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(f'usage: {message}')


def _parser():
    parser = _Parser(prog='xfer_agent.py', description='Agent half of the transfer experiment')
    sub = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)

    def command(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--dataset', required=True, choices=xc.DATASETS)
        return p
    p = command('export', 'manifest of partitions and views per anchor up to A_holdout')
    p.add_argument('--name')
    p = command('probe', 'stats.json and probe.json for the probe collection')
    p.add_argument('--collection', type=Path, required=True)
    p.add_argument('--name')
    p.add_argument('--export', type=Path)
    p.add_argument('--threads', type=int, default=xc.THREADS['probe'])
    p = command('run', 'the agent loop on the probe')
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--name', help='run-<id>')
    p.add_argument('--max-calls', type=int, default=MAX_CALLS)
    p.add_argument('--threads', type=int, default=xc.THREADS['agent'])
    p.add_argument('--retry-of', type=Path)
    p.add_argument('--reason')
    p = command('freeze', 'configs/datasets/xfer-<x>-set.json from a completed run')
    p.add_argument('--run', type=Path, required=True)
    p = command('sidecar', 'agent.parquet for one collection')
    p.add_argument('--collection', type=Path, required=True)
    p.add_argument('--threads', type=int, default=xc.THREADS['sidecar'])
    p.add_argument('--memory', default=MEMORY)
    p.add_argument('--batch-users', type=int)
    p.add_argument('--batch-rows', type=int, default=SIDECAR_BATCH_ROWS)
    p = command('leakcheck', 'full history against the cut, one batch against four')
    p.add_argument('--users', type=int, default=LEAK_USERS)
    p.add_argument('--name')
    p.add_argument('--threads', type=int, default=xc.THREADS['sidecar'])
    p.add_argument('--memory', default=MEMORY)
    return parser


def _handle(argv):
    args = _parser().parse_args(argv)
    xc.isolated()
    dataset = args.dataset
    if args.command == 'export':
        result = export(dataset, args.name)
        return dict(command='export', path=result['path'], anchors=len(result['anchors']), files=len(result['files']),
                    digest=result['digest'])
    if args.command == 'probe':
        result = prepare_probe(dataset, args.collection, args.name, args.export, args.threads)
        return dict(command='probe', path=result['path'], anchor=result['anchor'], users=result['users'],
                    rows=result['rows'])
    if args.command == 'run':
        result = run_loop(dataset, args.probe, args.name, max_calls=args.max_calls, threads=args.threads,
                          retry_of=args.retry_of, reason=args.reason)
        return dict(command='run', path=result['path'], calls=result['calls'], cost_usd=result['cost_usd'],
                    rounds=result['rounds_run'], stop=result['stop'], attempts=result['attempts'],
                    valid=result['valid'], columns=len(result['columns']))
    if args.command == 'freeze':
        result = freeze(dataset, args.run)
        return dict(command='freeze', path=result['path'], proposals=len(result['proposals']),
                    columns=len(result['columns']), digest=result['digest'])
    if args.command == 'sidecar':
        result = sidecar(dataset, args.collection, args.threads, args.memory, args.batch_users, batch_rows=args.batch_rows)
        return dict(command='sidecar', path=result['path'], rows=result['rows'], columns=len(result['columns']))
    result = leakcheck(dataset, args.users, args.name, args.threads, args.memory)
    return dict(command='leakcheck', path=result['path'], result=result['result'])


def main(argv=None):
    return xc.run_cli(_handle, argv)


if __name__ == '__main__':
    raise SystemExit(main())
