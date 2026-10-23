"""Agent half of the OTTO port (agent A): docs/otto-design.md §5 and §11.

Protocol of xfer and H&M (scripts/xfer_agent.py) with the OTTO replacements:

- ``export``: views and partition files of F2 and F3 with SHA-256; nothing is copied.
- ``calibrate``: the neutral self-join of I_3 at L = 5 and 20 and the high-cardinality
  aggregation; T_tb = 3·t_20 up to 60 s, clamped to [1200, 1800] s (§5.4).
- ``sandbox``: a new locked in-memory DuckDB per (fold, keys) with the views of
  ``otto_data.views`` (hist, sess), cand, sessions and the accepted tables tb_*;
  allowed_directories are the H_k partitions, the collection prefix/ and the table cache.
- ``check_sql``: the H&M and xfer rules, {S}/{E} only, ts on the left and never against a
  number, the OTTO words (§5.3); kinds table, source and feature (§5.1).
- ``probe``: stats.json from I_3 only, keys of the pool frame and probe.json (§5.4).
- ``run``: 6 rounds x 5 proposals, at most 12 calls; phase S (tables, sources) in rounds
  1-2, then the candidates freeze to B plus the first 6 valid sources (BA, §5.2) and phase
  F (tables, features). Feedback: validity and coverage, coarse recall on the probe labels
  read only by the feedback formatter (§5.5). The prompt is neutral (§5.6).
- ``freeze``: configs/datasets/otto-set.json from the completed run; the journal goes to
  docs/otto-run/<run>/ (§5.8).
- ``sidecar``: the BA frame (session, aid, the B features, ag_src_*, ag_*) of a collection
  under sidecars/<collection>/<name>/, in batches of 50 000 sessions in sha256 order (§5.7).
- ``leakcheck``: every agent column with hist of H_k against hist over every partition
  d < -7 filtered by ts < {S}; 2 000 sessions in one batch against 4 x 500 (§5.8).

Tables are computed once per fold and data and cached under tables/F<k>/ by (fold,
proposal id, sha256 of the SQL, a fingerprint of the views and the keys of the tables they
read). Run as ``python -I scripts/otto_agent.py <command> ...``; one JSON line, exit 0/1.
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

from scripts import otto_common as oc  # noqa: E402
from scripts import otto_data as od  # noqa: E402
from scripts.hm_agent_loop import ask_llm, clean_error  # noqa: E402
from scripts.xfer_agent import FORBIDDEN, NONDETERMINISTIC, NUMBER, log2_bucket, redact  # noqa: E402

require = oc.require
ContractError = oc.ContractError

# =============================================================================== constants

EXPORT_FORMAT = 'otto-export-v1'
CALIBRATION_FORMAT = 'otto-calibration-v1'
PROBE_FORMAT = 'otto-probe-v1'
RUN_FORMAT = 'otto-run-v1'
SET_FORMAT = oc.SET_FORMAT
TABLE_FORMAT = 'otto-table-v1'
SIDECAR_FORMAT = oc.SIDECAR_FORMAT
LEAKCHECK_FORMAT = oc.LEAKCHECK_FORMAT

PROBE_FOLD = 3
KINDS = ('table', 'source', 'feature')
KIND_LEVELS = {'table': ('item_pair',), 'source': ('pair',), 'feature': ('pair', 'session', 'item')}
LEVEL_KEYS = {'item_pair': ('item', 'item2'), 'pair': ('session', 'item'), 'session': ('session',),
              'item': ('item',)}
FIELDS = ('name', 'idea', 'kind', 'level', 'sql')
STATUSES = ('valid', 'invalid', 'budget')

# §5.2: rounds, calls, phases and the resource limits the agent knows from the prompt
MODEL = 'claude-opus-5-5'
ROUNDS = 6
PROPOSALS = 5
MAX_CALLS = 12
S_ROUNDS = 2
PHASE_KINDS = {'S': ('table', 'source'), 'F': ('table', 'feature')}
MAX_SOURCES = 6
SOURCE_ROWS = 40
BA_MAX = 200
TABLE_ROWS_PER_ITEM = 50
TABLE_MAX_ROWS = 100_000_000
MAX_VALUES = 3
MAX_ROWS = 20_000_000              # feature output rows (as xfer)
RETRIES_EXHAUSTED = 'retries_exhausted'
MAX_RETRIES = 2
OPERATOR_ABORT = 'KeyboardInterrupt'

# §5.4: probe timeouts, budgets and threads; calibration of table
PROBE_TIMEOUTS = {'source': 60.0, 'pair': 60.0, 'session': 60.0, 'item': 120.0}
PROBE_BUDGETS = {'pair_session_seconds': 900.0, 'item_seconds': 600.0}
TABLE_BUDGET_FACTOR = 4
PROBE_THREADS = {'table': 8, 'other': 3}
T_TB_MIN, T_TB_MAX, T_TB_FACTOR, T_TB_STEP = 1200, 1800, 3, 60
CALIBRATION_WINDOWS = (5, 20)
CALIBRATION_KEY = '(a.session * 1000003 + a.seq * 1009 + b.seq) % 2147483648'
CALIBRATION_THREADS = oc.DUCKDB_THREADS

# §5.3, §12: DuckDB limits of the sandbox and the harness
MEMORY = oc.DUCKDB_MEMORY
MAX_TEMP = oc.DUCKDB_MAX_TEMP
HELPER_MEMORY = '4GB'          # in-memory helpers on one batch or the probe pool (ba_union, Scorer, frame_rows)
SANDBOX_PREFIX = 'tlab-otto-sbx-'

# §5.7: sidecars
SIDECAR_THREADS = oc.DUCKDB_THREADS
BATCH_TIMEOUT = 900.0
PROPOSAL_CAP = 4*3600.0
TABLE_TIMEOUT_MIN = 3600.0
# Tables are computed in one DuckDB thread: a parallel hash aggregate sums DOUBLE in a varying order,
# and a top-N cut over those sums flips at ties (leakcheck lc-F3, r2p5: 3 606 pairs at 8 vs 3 threads).
TABLE_THREADS = 1
TABLE_MEMORY = oc.DUCKDB_MEMORY      # fixed too: an external aggregate may add partial sums in another order
TABLE_TIMEOUT_FACTOR = 1.5
RETRY_FACTOR = 2
SIDECAR_REPORT = oc.SIDECAR_REPORT
SIDECAR_PROGRESS = 'progress.json'
SIDECAR_FAILURE_FORMAT = 'otto-sidecar-failure-v1'
SIDECAR_STEP = 'sidecar'            # step of the otto-deviations.json record that doubles the limits

# §5.4 validity (H&M), §5.8 leakcheck
MIN_DISTINCT = 2
MIN_NON_NULL = 100
RHO_LIMIT = 0.999
SAMPLE_ROWS = 100_000
MIN_SPEARMAN_ROWS = 1000
INVARIANCE_SESSIONS = 1000
MIN_SOURCE_SESSIONS = 1000         # a source brings new candidates to at least this many probe sessions
PERMUTATION_SEED = 20260305        # the invariance halves run on sess with session ids permuted by this seed
INVARIANCE_PARTS = 2
LEAK_SESSIONS = 2000
LEAK_BATCHES = 4
TOLERANCE = 1e-9
ERROR_CHARS = 400
FLOAT32_MAX = oc.FLOAT32_MAX

# §5.5: feedback precision
RECALL_DIGITS = 2
GAIN_DIGITS = 3

NAME = re.compile(r'[a-z][a-z0-9_]{1,24}')                 # tb_<name>, ag_src_<name>_rank
VALUE_NAME = re.compile(r'ag_[a-z][a-z0-9_]{1,38}')
TABLE_VALUE = re.compile(r'tv_[a-z][a-z0-9_]{1,38}')
AGENT_PREFIX = oc.AGENT_PREFIX
SOURCE_PREFIX = oc.SOURCE_PREFIX
SOURCE_COLUMNS = ('rank', 'score')
VALUE_TYPE = re.compile(r'(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|BOOLEAN|DECIMAL\([0-9]+,\s*[0-9]+\))')
MEMORY_TEXT = re.compile(r'[0-9]+(\.[0-9]+)?\s*(KB|MB|GB|TB|KiB|MiB|GiB|TiB)')
IDENT = re.compile(r'[a-z_][a-z0-9_]*')
OUTPUT_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')
RUN_NAME = re.compile(r'run-[A-Za-z0-9][A-Za-z0-9._-]*')

# check_sql (§5.3): xfer FORBIDDEN and NONDETERMINISTIC (imported) plus these
_CMP_TEXT = r'(<=|>=|<>|!=|==|<|>|=)'
OTTO_FORBIDDEN = re.compile(r'\b(train|test|jsonl|ndjson|sample_submission|otto|label\w*|suffix\w*|'
                            r'hash\w*|sha\d*|md5\w*|crc\d*|pg_\w+|summarize|describe|show|getvariable)\b', re.I)
# the session id is never singled out: no comparison of session with a number, no session % n (addressed oracle)
_QUALIFIED_SESSION = r'(?:[a-z_][a-z0-9_]*\s*\.\s*)?session\b'
SESSION_LITERAL = re.compile(r'\bsession\s*' + _CMP_TEXT + r'\s*[-+(\s]*[0-9]|[0-9]\s*' + _CMP_TEXT + r'\s*'
                             + _QUALIFIED_SESSION + r'|\bsession\s+(not\s+)?(between|in)\s*[-+(\s]*[0-9]|'
                             r'\bsession\s*%|%\s*\(?\s*' + _QUALIFIED_SESSION, re.I)
RAISING = re.compile(r'\b(error|strptime|regexp_\w+)\s*\(', re.I)
STATEMENT = re.compile(r'(select|with)\b', re.I)
DATE_LITERAL = re.compile(r"'\s*[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}")
LONG_NUMBER = re.compile(r'(?<![A-Za-z0-9_.])[0-9]{9,}')
LONG_DIGITS = 9
PLACEHOLDERS = ('{S}', '{E}')
_CMP = _CMP_TEXT
_QUALIFIED_TS = r'(?:[a-z_][a-z0-9_]*\s*\.\s*)?ts\b'
TS_RIGHT = re.compile(_CMP + r'\s*' + _QUALIFIED_TS, re.I)
TS_LITERAL = re.compile(r'\bts\s*' + _CMP + r'\s*[-+(\s]*[0-9]', re.I)
TS_RANGE_LITERAL = re.compile(r'\bts\s+(not\s+)?(between|in)\s*[-+(\s]*[0-9]', re.I)
TS_RANGE_RIGHT = re.compile(r'\bbetween\s+' + _QUALIFIED_TS, re.I)
PATH_LITERAL = re.compile(r"""(['"])[^'"]*?([/\\]|\.(parquet|csv|tsv|json|jsonl|txt|db|duckdb|sqlite|arrow|"""
                          r"""ndjson|feather|zip|gz|zst|xlsx?)\b)[^'"]*\1""", re.I)
BATCH_WORDS = re.compile(r'\b(cand|sessions)\b', re.I)
TABLE_WORDS = re.compile(r'\b(cand|sessions|sess)\b', re.I)   # a table is item x item over hist only
TABLE_REF = re.compile(r'\btb_([a-z][a-z0-9_]*)\b', re.I)

# §5.6: the prompt never names the data set; the base names are neutralised
NAMES_IN_PROMPT = re.compile(r'(?<![A-Za-z])(otto|kaggle|competition|clicks?|carts|orders)(?![A-Za-z])', re.I)
NEUTRAL_WORDS = (('clicks', 'view'), ('carts', 'cart'), ('orders', 'order'), ('aids', 'items'), ('aid', 'item'))
WARNING = ('All valid sources and columns will enter the model without selection. Superfluous and noisy columns '
           'hurt: a few strong, non-redundant signals are needed. Session-level columns work only through '
           'interactions.')
BUCKET = re.compile(r'0|2\^(-?\d+)–2\^(-?\d+)')
COLUMN_STATS = (('non_null_share', 'non-null', 'share'), ('distinct', 'distinct', 'bucket'),
                ('max_abs_spearman', 'max |rho|', 'rho'), ('nearest', 'nearest', 'name'))


class ProposalError(ValueError):
    """A proposal breaks the SQL rules or the output contract, fails or times out."""


# =============================================================================== small helpers

def _duckdb():
    import duckdb
    return duckdb


def _np():
    import numpy as np
    return np


def _pd():
    import pandas as pd
    return pd


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


_literal = oc.sql_literal
_list_literal = oc.sql_list          # the file list as otto_data writes it into its views


def _helper_con():
    """In-memory DuckDB of the helpers on one batch or the probe pool (ba_union, Scorer, frame reads)."""
    return od.connect(4, HELPER_MEMORY)


def _ident(name):
    if not isinstance(name, str) or not IDENT.fullmatch(name):
        raise ValueError(f'Unexpected identifier {name!r}')
    return name


def _clip(text):
    return str(text)[:ERROR_CHARS]


def _stamp():
    return oc.utc_now().replace('-', '').replace(':', '')


def _output_name(name, default):
    name = default if name is None else name
    if not isinstance(name, str) or not OUTPUT_NAME.fullmatch(name):
        raise ValueError(f'Output names are [A-Za-z0-9._-]; got {name!r}')
    return name


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


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


def _relative(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(Path(oc.ROOT).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_bucket(text):
    match = BUCKET.fullmatch(text) if isinstance(text, str) else None
    return bool(match) and (text == '0' or int(match.group(2)) == int(match.group(1))+1)


def _tens(seconds):
    """Seconds as shown or frozen: down to a multiple of 10 s."""
    return int(max(float(seconds), 0.0) // 10 * 10)


def _share(value):
    return None if value is None else round(float(value), 2)


def _floats(values):
    np = _np()
    return np.ma.filled(np.ma.asarray(values, dtype=np.float64), np.nan)


def _spill_dir():
    """A fresh spill directory of oc.spill_dir, created (the agent also writes its own scratch files there)."""
    path = oc.spill_dir()
    path.mkdir(parents=True)
    return path.resolve()


def neutral(text):
    """Base names and formulas in the agent's words: clicks -> view, carts -> cart, orders -> order, aid -> item."""
    text = str(text)
    for old, new in NEUTRAL_WORDS:
        text = re.sub(rf'(?<![A-Za-z]){old}(?![A-Za-z])', new, text)
    return text


def mask_names(text):
    """Names the agent must not see, masked in echoed text (its own words included)."""
    return NAMES_IN_PROMPT.sub('<name>', neutral(text))


def substitute(sql, start, end):
    """The SQL with {S} and {E} replaced by the integer week bounds in seconds (after check_sql)."""
    return sql.replace('{S}', str(int(start))).replace('{E}', str(int(end)))


def _body(sql):
    body = sql.strip()
    if body.endswith(';'):
        body = body[:-1].rstrip()
    return body


# =============================================================================== check_sql (§5.1, §5.3)

def check_sql(sql, kind, level, tables=()):
    """H&M/xfer rules plus the OTTO ones; ``tables`` are the names of earlier accepted tables.

    One SELECT/WITH, no comments, {S} and {E} only, no date or long integer literal, ts on the
    left of a comparison and never against a number, the forbidden words, no path in a string,
    no cand or sessions in a table or an item feature, tb_* only of earlier tables.
    Returns the referenced table names in order of first use.
    """
    if kind not in KINDS:
        raise ProposalError('kind must be table, source or feature')
    if level not in KIND_LEVELS[kind]:
        raise ProposalError(f'a {kind} has level {" or ".join(KIND_LEVELS[kind])}')
    if not isinstance(sql, str) or not sql.strip():
        raise ProposalError('sql must be a non-empty string')
    body = _body(sql)
    if ';' in body:
        raise ProposalError('exactly one statement is allowed; ";" may only end it')
    if '--' in body or '/*' in body:
        raise ProposalError('comments are not allowed')
    if not STATEMENT.match(body):
        raise ProposalError('the statement must start with SELECT or WITH')
    rest = body
    for placeholder in PLACEHOLDERS:
        rest = rest.replace(placeholder, ' ')
    if '{' in rest or '}' in rest:
        raise ProposalError('times are written only as {S} and {E}; no other {...} is allowed')
    if '$' in rest:
        raise ProposalError('"$" is not allowed (no dollar-quoted strings or parameters)')
    if DATE_LITERAL.search(rest):
        raise ProposalError('date literals are not allowed; write times relative to {S} or {E}')
    hit = LONG_NUMBER.search(rest)
    if hit:
        raise ProposalError(f'integer literals of {LONG_DIGITS} or more digits are not allowed; '
                            'write times relative to {S} or {E}')
    for pattern, text in ((TS_RIGHT, 'ts must stand on the left of a comparison'),
                          (TS_RANGE_RIGHT, 'ts must stand on the left of a comparison'),
                          (TS_LITERAL, 'ts may not be compared with a number; write it relative to {S} or {E}'),
                          (TS_RANGE_LITERAL, 'ts may not be compared with a number; write it relative to {S} or {E}')):
        hit = pattern.search(body)
        if hit:
            raise ProposalError(f'{text}: {hit.group(0).strip()!r}')
    hit = (FORBIDDEN.search(rest) or NONDETERMINISTIC.search(rest) or RAISING.search(rest)
           or OTTO_FORBIDDEN.search(rest))
    if hit:
        raise ProposalError(f'forbidden table, function or command: {hit.group(0)}')
    if PATH_LITERAL.search(rest):
        raise ProposalError('string literals may not hold paths or file names')
    hit = SESSION_LITERAL.search(rest)
    if hit:
        raise ProposalError(f'session may not be compared with a number or taken modulo: {hit.group(0).strip()!r}')
    if kind == 'table' or level == 'item':
        hit = (TABLE_WORDS if kind == 'table' else BATCH_WORDS).search(rest)
        if hit:
            what = 'a table' if kind == 'table' else 'an item query'
            if kind == 'table':
                raise ProposalError(f'a table must not use {hit.group(0)}: it reads hist only (item x item)')
            raise ProposalError(f'{what} must not use {hit.group(0)}: its values do not depend on the batch')
    known = list(tables)
    used = []
    for match in TABLE_REF.finditer(rest):
        name = match.group(1).lower()
        if name not in known:
            raise ProposalError(f'tb_{name} is not a table accepted earlier in this run')
        if name not in used:
            used.append(name)
    return used


def _fields(proposal):
    if not isinstance(proposal, dict):
        raise ProposalError('a proposal is an object with name, idea, kind, level and sql')
    for key in FIELDS:
        if not isinstance(proposal.get(key), str) or not proposal[key].strip():
            raise ProposalError(f'{key} must be a non-empty string')
    kind, level = proposal['kind'], proposal['level']
    if kind not in KINDS:
        raise ProposalError('kind must be table, source or feature')
    if level not in KIND_LEVELS[kind]:
        raise ProposalError(f'a {kind} has level {" or ".join(KIND_LEVELS[kind])}')
    if kind in ('table', 'source') and not NAME.fullmatch(proposal['name']):
        raise ProposalError(f'the name of a {kind} must match ^[a-z][a-z0-9_]{{1,24}}$')
    return kind, level, proposal['sql']


def source_columns(name):
    return [f'{SOURCE_PREFIX}{name}_{suffix}' for suffix in SOURCE_COLUMNS]


def parse_proposals(text):
    """The first JSON list of the reply: objects with exactly name, idea, kind, level and sql (strings)."""
    if not isinstance(text, str):
        raise ValueError('The reply is not text')
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\[', text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if not isinstance(value, list) or not value:
            raise ValueError('The reply holds no proposals')
        out = []
        for position, item in enumerate(value, 1):
            if not isinstance(item, dict) or set(item) != set(FIELDS):
                raise ValueError(f'Proposal {position} must be an object with exactly {", ".join(FIELDS)}')
            if not all(isinstance(item[key], str) for key in FIELDS):
                raise ValueError(f'Proposal {position}: every field must be a string')
            out.append({key: item[key] for key in FIELDS})
        return out
    raise ValueError('The reply has no JSON list')


def ask_proposals(prompt, model):
    """One isolated call through hm_agent_loop.ask_llm; the reply text is parsed with the five OTTO fields.

    ask_llm parses the H&M four fields and refuses an OTTO reply as unparsable only after
    its isolation checks; that refusal carries the reply text, which is parsed here.
    """
    try:
        _, meta = ask_llm(prompt, model)
    except Exception as exc:  # noqa: BLE001 - only the unparsable-reply refusal is taken over
        meta = getattr(exc, 'meta', None)
        if not (str(exc).startswith('Unparsable reply') and isinstance(meta, dict)
                and isinstance(meta.get('text'), str)):
            raise
    try:
        return parse_proposals(meta['text']), meta
    except ValueError as exc:
        error = ValueError(f'Unparsable reply: {exc}')
        error.meta = meta
        raise error from None


# =============================================================================== views (otto_data) and the harness

def fold_spec(k, purpose, collection=None):
    """``otto_data.views`` of F_k with its digest; hist and sess are otto_data's neutral SELECT texts."""
    raw = od.views(k, purpose, collection=collection)
    for name in ('hist', 'sess'):
        require(isinstance(raw['views'].get(name), str) and raw['views'][name].strip(), f'views() lacks {name}')
        for path in raw['files'][name]:
            require("'" not in str(path), f'Unquotable path: {path}')
    spec = dict(raw, collection=None if collection is None else str(Path(collection).resolve()))
    spec['digest'] = _spec_digest(spec)
    return spec


def _spec_digest(spec):
    return oc.canonical_digest(dict(fold=spec['fold'], start=spec['start'], end=spec['end'],
                                    views={k: spec['views'][k] for k in ('hist', 'sess')},
                                    directories=spec['directories']))


def full_history_spec(spec):
    """Leakcheck variant (§5.8): hist over every train partition d < -7, filtered by ts < {S}; sess unchanged."""
    days = [d for d in oc.existing_days('train') if d < oc.BARRIER_DAY]
    files = oc.partition_glob(days, 'leakcheck')
    old = _list_literal(spec['files']['hist'])
    text = spec['views']['hist']
    require(text.count(old) == 1, 'The hist view of otto_data must name its file list exactly once')
    hist = f"SELECT * FROM ({text.replace(old, _list_literal(files))}) WHERE ts < {int(spec['start'])}"
    out = dict(spec, views=dict(spec['views'], hist=hist), files=dict(spec['files'], hist=files),
               directories=dict(spec['directories'], hist=sorted({str(Path(f).parent) for f in files})))
    out['digest'] = _spec_digest(out)
    out['degenerate'] = sorted(files) == sorted(spec['files']['hist'])
    return out


def harness(spec, threads=4, memory='4GB', temp=None):
    """A plain DuckDB with hist and sess for harness code only (no agent SQL ever runs here)."""
    con = od.connect(threads, memory, temp=temp, max_temp=MAX_TEMP)
    try:
        for name in ('hist', 'sess'):
            con.execute(f'CREATE VIEW {name} AS {spec["views"][name]}')
    except BaseException:
        con.close()
        raise
    return con


_FINGERPRINTS = {}
_KNOWN = {}


def views_fingerprint(spec, threads=4, memory='4GB'):
    """Order-free content digest of hist and sess: rows and the sum of hash(session, item, ts, event, seq)."""
    if spec['digest'] in _FINGERPRINTS:
        return _FINGERPRINTS[spec['digest']]
    con = harness(spec, threads, memory)
    try:
        parts = {name: [str(v) for v in con.execute(
            f'SELECT count(*), coalesce(sum(hash(session, item, ts, event, seq)), 0)::HUGEINT FROM {name}').fetchone()]
            for name in ('hist', 'sess')}
    finally:
        con.close()
    _FINGERPRINTS[spec['digest']] = oc.canonical_digest(dict(fold=spec['fold'], start=spec['start'], **parts))
    return _FINGERPRINTS[spec['digest']]


def known_items(spec, threads=4, memory='4GB'):
    """Items of I_k (hist and sess), ascending int64."""
    np = _np()
    if spec['digest'] not in _KNOWN:
        con = harness(spec, threads, memory)
        try:
            items = con.execute('SELECT item FROM hist UNION SELECT item FROM sess ORDER BY 1').fetchnumpy()['item']
        finally:
            con.close()
        _KNOWN[spec['digest']] = np.asarray(items, dtype=np.int64)
    return _KNOWN[spec['digest']]


# =============================================================================== sandbox (§5.3)

def sandbox(spec, keys=None, *, tables=None, threads=3, memory=None, max_temp=None, writable=None):
    """A new locked in-memory connection: hist, sess, cand(session, item), sessions(session) and tb_* only.

    ``keys`` is a parquet file of ``session, aid`` (cand is empty without it); ``tables`` maps
    accepted table names to their cached parquet files. allowed_directories are the H_k
    partitions, the prefix/ directory of the collection, the directories of those tables and
    ``writable`` (the harness writes a new table there); then external access is off and the
    configuration is locked.
    """
    duckdb = _duckdb()
    threads = _threads(threads)
    memory = _memory(MEMORY if memory is None else memory)
    max_temp = _memory(MAX_TEMP if max_temp is None else max_temp)
    tables = dict(tables or {})
    directories = [*spec['directories']['hist'], *spec['directories']['sess']]
    directories += [str(Path(path).parent) for path in tables.values()]
    if writable is not None:
        directories.append(str(writable))
    allowed = sorted({d.rstrip('/')+'/' for d in directories})
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
        con.execute('SET max_temp_directory_size=?', [max_temp])
        con.execute('SET allowed_directories=?', [allowed])
        for name in ('hist', 'sess'):
            con.execute(f'CREATE VIEW {name} AS {spec["views"][name]}')
        for name, path in tables.items():
            require(NAME.fullmatch(name), f'Bad table name {name!r}')
            con.execute(f'CREATE VIEW tb_{name} AS SELECT * FROM read_parquet({_literal(path)})')
        if keys is None:
            con.execute('CREATE TABLE cand (session BIGINT, item BIGINT)')
        else:
            con.execute('''CREATE TABLE cand AS SELECT CAST(session AS BIGINT) AS session, CAST(aid AS BIGINT) AS item
                FROM read_parquet(?) ORDER BY 1, 2''', [str(Path(keys).resolve())])
            nulls, repeated = con.execute('''SELECT count(*) FILTER (WHERE session IS NULL OR item IS NULL),
                count(*) - count(DISTINCT (session, item)) FROM cand''').fetchone()
            require(not nulls and not repeated, 'Batch keys must be unique non-NULL pairs')
        con.execute('CREATE TABLE sessions AS SELECT DISTINCT session FROM cand ORDER BY 1')
        con.execute('SET enable_external_access=false')
        con.execute('SET lock_configuration=true')
    except BaseException:
        con.close()
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return con


def close(con):
    """Close a sandbox and remove its spill directory."""
    try:
        temp = con.execute("SELECT current_setting('temp_directory')").fetchone()[0]
    except Exception:  # noqa: BLE001
        temp = None
    con.close()
    if temp:
        path = Path(temp)
        if path.name.startswith(SANDBOX_PREFIX) and path.parent == Path(tempfile.gettempdir()).resolve():
            shutil.rmtree(path, ignore_errors=True)


def require_sandbox(con):
    try:
        locked, external = con.execute(
            "SELECT current_setting('lock_configuration'), current_setting('enable_external_access')").fetchone()
    except Exception:  # noqa: BLE001
        locked = external = None
    if locked is not True or external is not False:
        raise ValueError('Proposals run only in a locked sandbox connection')


# =============================================================================== the harness of one proposal

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
    """A DuckDB error of the proposal's own SQL: everything but disk, connection and a foreign interrupt.

    Internal, fatal, serialization and transaction errors of the throwaway sandbox count as the
    proposal's (fixed text, the run goes on); only the infrastructure stops the run.
    """
    duckdb = _duckdb()
    infrastructure = (duckdb.IOException, duckdb.ConnectionException, duckdb.InterruptException)
    return isinstance(exc, duckdb.Error) and not isinstance(exc, infrastructure)


def error_feedback(exc, sql=''):
    """Planning errors keep their message through clean_error; every other DuckDB error a fixed text."""
    duckdb = _duckdb()
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
        duckdb = _duckdb()
        if self.fired.is_set():
            return self.timeout()
        if isinstance(exc, ProposalError):
            return exc
        if _proposal_failure(exc):
            return ProposalError(error_feedback(exc, self.sql))
        if isinstance(exc, duckdb.Error):
            return type(exc)(f'{type(exc).__name__}: {TECHNICAL_TEXT}')
        return exc


def _check_output(con, kind, level, sql):
    """§5.1 on _x: keys of the level (BIGINT, non-NULL, unique, in their set), value columns, limits."""
    keys = LEVEL_KEYS[level]
    described = [(row[0], row[1]) for row in con.execute('DESCRIBE _x').fetchall()]
    names, kinds = [n for n, _ in described], dict(described)
    if any(not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)', sql) for name in names if name not in keys):
        raise ProposalError('every output column must be named in the SQL (alias each value); '
                            'a column name not written in the SQL was produced')
    if len(set(names)) != len(names):
        raise ProposalError('output column names repeat')
    missing = [key for key in keys if key not in kinds]
    if missing:
        raise ProposalError(f'level {level} needs the key columns {", ".join(keys)}; missing {", ".join(missing)}')
    for key in keys:
        if kinds[key] != 'BIGINT':
            raise ProposalError(f'key {key} must be BIGINT, not {kinds[key]}')
    values = [name for name in names if name not in keys]
    if kind == 'source':
        if values != ['score']:
            raise ProposalError('a source has exactly one value column, score')
    elif not 1 <= len(values) <= MAX_VALUES:
        raise ProposalError(f'one to {MAX_VALUES} value columns are required besides the keys, got {len(values)}')
    for name in values:
        if kind == 'table' and not TABLE_VALUE.fullmatch(name):
            raise ProposalError(f'table column {name} does not match ^tv_[a-z][a-z0-9_]{{1,38}}$')
        if kind == 'feature' and (not VALUE_NAME.fullmatch(name) or name.startswith(SOURCE_PREFIX)):
            raise ProposalError(f'column {name} does not match ^ag_[a-z][a-z0-9_]{{1,38}}$ or starts with '
                                f'{SOURCE_PREFIX}, which the harness names')
        if not VALUE_TYPE.fullmatch(kinds[name]):
            raise ProposalError(f'column {name} has type {kinds[name]}; integer, DECIMAL, FLOAT, DOUBLE or BOOLEAN '
                                'is required (times as differences to {S} or {E})')
    nulls = ' OR '.join(f'{key} IS NULL' for key in keys)
    distinct = keys[0] if len(keys) == 1 else f'({", ".join(keys)})'
    rows, null_rows, repeated = con.execute(
        f'SELECT count(*), count(*) FILTER (WHERE {nulls}), count(*) - count(DISTINCT {distinct}) FROM _x').fetchone()
    if null_rows:
        raise ProposalError('some rows have NULL keys')
    if repeated:
        raise ProposalError('duplicate keys: one row per key is required')
    if kind == 'table':
        if rows > TABLE_MAX_ROWS:
            raise ProposalError(f'a table holds at most {TABLE_MAX_ROWS} rows')
        if not rows:
            raise ProposalError('the table is empty')
        widest = con.execute('SELECT coalesce(max(n), 0) FROM (SELECT count(*) AS n FROM _x GROUP BY item)'
                             ).fetchone()[0]
        if widest > TABLE_ROWS_PER_ITEM:
            raise ProposalError(f'a table holds at most {TABLE_ROWS_PER_ITEM} rows per item')
        return values, int(rows)
    if rows > MAX_ROWS:
        raise ProposalError(f'output rows exceed the limit of {MAX_ROWS}')
    if kind == 'source':
        widest, bad = con.execute(f'''SELECT coalesce(max(n), 0), (SELECT count(*) FROM _x WHERE score IS NULL
            OR NOT isfinite(CAST(score AS DOUBLE)) OR abs(CAST(score AS DOUBLE)) > {FLOAT32_MAX!r})
            FROM (SELECT count(*) AS n FROM _x GROUP BY session)''').fetchone()
        if widest > SOURCE_ROWS:
            raise ProposalError(f'a source gives at most {SOURCE_ROWS} rows per session')
        if bad:
            raise ProposalError('score must be a finite non-NULL number within the FLOAT range on every row')
    if level in ('pair', 'session'):
        universe, label = ('cand', 'cand') if (kind, level) == ('feature', 'pair') else ('sessions', 'sessions')
        match = ' AND '.join(f'u.{key} = x.{key}' for key in (keys if universe == 'cand' else ('session',)))
        outside = con.execute(f'SELECT count(*) FROM _x x WHERE NOT EXISTS (SELECT 1 FROM {universe} u WHERE {match})'
                              ).fetchone()[0]
        if outside:
            raise ProposalError(f'some keys lie outside {label}')
    return values, int(rows)


def _finite(name):
    value = f'CAST(x."{name}" AS DOUBLE)'
    return f'CASE WHEN isfinite({value}) AND abs({value}) <= {FLOAT32_MAX!r} THEN {value} END AS "{name}"'


def _known_check(frame, column, known):
    np = _np()
    values = frame[column].to_numpy(dtype=np.int64)
    if len(values) and not bool(np.isin(values, known).all()):
        raise ProposalError(f'some {column} keys are not items known in hist or sess')


def execute(con, kind, level, sql, start, end, timeout_s, known=None, table_path=None):
    """CREATE TEMP TABLE _x AS <sql with {S}, {E}>, the output checks, then the result.

    source: frame session, item, score, rank (score desc, then item); feature: the level keys
    and the values as DOUBLE (NULL outside float32 and non-finite); table: the harness COPYs
    _x to ``table_path`` (item, item2, tv_* as DOUBLE). Returns (result, value names, rows, seconds).
    """
    duckdb = _duckdb()
    require_sandbox(con)
    body = _body(sql)
    statement = 'CREATE TEMP TABLE _x AS\n'+substitute(body, start, end)
    try:
        parsed = con.extract_statements(statement)
    except duckdb.Error as exc:
        raise ProposalError(error_feedback(exc, sql)) from None
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.CREATE:
        raise ProposalError('exactly one SELECT statement is allowed')
    limit = _Limit(con, _seconds(timeout_s), sql)
    failure = None
    started = time.monotonic()
    try:
        with limit:
            con.execute('DROP TABLE IF EXISTS _x')
            con.execute(statement)
            names, rows = _check_output(con, kind, level, sql)
            keys = LEVEL_KEYS[level]
            order = ', '.join(f'x.{key}' for key in keys)
            casts = ', '.join(_finite(name) for name in names)
            if kind == 'table':
                require(table_path is not None, 'A table needs its output path')
                con.execute(f'COPY (SELECT {order}, {casts} FROM _x x ORDER BY {order}) TO {_literal(table_path)} '
                            '(FORMAT parquet)')
                result = None
            elif kind == 'source':
                result = con.execute('''SELECT session, item, CAST(score AS DOUBLE) AS score,
                    row_number() OVER (PARTITION BY session ORDER BY CAST(score AS DOUBLE) DESC, item) AS rank
                    FROM _x ORDER BY session, item''').fetch_df()
            else:
                result = con.execute(f'SELECT {order}, {casts} FROM _x x ORDER BY {order}').fetch_df()
        if limit.fired.is_set():
            raise limit.timeout()
    except Exception as exc:  # noqa: BLE001
        failure = limit.error(exc)
        if failure is exc and not isinstance(exc, ProposalError):
            raise
    finally:
        try:
            con.execute('DROP TABLE IF EXISTS _x')
        except Exception:  # noqa: BLE001
            pass
    if failure is not None:
        raise failure
    seconds = time.monotonic()-started
    if known is not None and kind == 'source':
        _known_check(result, 'item', known)
    if known is not None and kind == 'feature' and level == 'item':
        _known_check(result, 'item', known)
    return result, names, rows, seconds


def _stage_keys(frame, path):
    """keys parquet (session, aid) sorted, unique."""
    pd = _pd()
    np = _np()
    keys = pd.DataFrame({'session': frame['session'].to_numpy(dtype=np.int64),
                         'aid': frame['aid'].to_numpy(dtype=np.int64)})
    require(not keys.duplicated().any(), 'Keys must be unique (session, aid) pairs')
    oc.write_parquet(keys, path, order_by='session, aid')
    return Path(path)


# =============================================================================== tables: cache (§5.1)

def table_key(fold, pid, sql, fingerprint, depends):
    """Cache identity: fold, proposal id, sha256 of the SQL, the data fingerprint, the tables read and
    TABLE_THREADS and TABLE_MEMORY."""
    return oc.canonical_digest(dict(fold=int(fold), id=pid, sql_sha256=_sha(sql), data=fingerprint,
                                    depends=[[name, key] for name, key in depends], threads=TABLE_THREADS,
                                    memory=TABLE_MEMORY))


def table_dir(fold, pid, key):
    return oc.output_dir('tables', f'F{int(fold)}', f'{pid}-{key[:16]}')


def read_table(path):
    """table.json of a completed cached table with its parquet hash checked; None when absent."""
    path = Path(path)
    if not (path/'table.json').is_file():
        return None
    record = oc.read_json(path/'table.json')
    require(record.get('format') == TABLE_FORMAT and record.get('status') == 'completed',
            f'{path.name}: not a completed table')
    require(oc.sha256_file(path/'table.parquet') == record['sha256'], f'{path.name}: table.parquet changed')
    return dict(record, path=str(path/'table.parquet'))


def compute_table(spec, proposal, tables, *, timeout_s, threads, memory=None, fingerprint=None, fresh=None):
    """The table of ``proposal`` on F_k, from the cache or computed once in a sandbox.

    ``tables`` maps earlier accepted table names to their entries (path, key). Returns the
    entry with ``cached``. A failure raises ProposalError and leaves no cache entry.
    ``fresh``: a directory for a computation outside the cache (the leakcheck variant
    recomputes every table, so a nondeterministic table shows up); the caller removes it.
    """
    name, sql = proposal['name'], proposal['sql']
    used = check_sql(sql, 'table', proposal['level'], tables=list(tables))
    fingerprint = views_fingerprint(spec) if fingerprint is None else fingerprint
    key = table_key(spec['fold'], proposal['id'], sql, fingerprint, [(n, tables[n]['key']) for n in used])
    if fresh is None:
        final = table_dir(spec['fold'], proposal['id'], key)
        entry = read_table(final)
        if entry is not None:
            return dict(entry, cached=True)
        require(not final.exists(), f'{final} exists without a completed table.json; remove it to recompute')
    else:
        final = Path(fresh)/f"{proposal['id']}-{key[:16]}"
        require(not final.exists(), f'{final} exists')
    partial = oc.new_output(final.with_name(f'.partial-{final.name}-{os.getpid()}'))
    try:
        con = sandbox(spec, None, tables={n: tables[n]['path'] for n in used}, threads=TABLE_THREADS,
                      memory=TABLE_MEMORY, writable=partial)  # ``threads``, ``memory`` unused: see TABLE_THREADS
        try:
            _, names, rows, seconds = execute(con, 'table', proposal['level'], sql, spec['start'], spec['end'],
                                              timeout_s, table_path=partial/'table.parquet')
        finally:
            close(con)
        record = dict(format=TABLE_FORMAT, status='completed', fold=spec['fold'], id=proposal['id'], name=name,
                      key=key, sql_sha256=_sha(sql), data=fingerprint, views_digest=spec['digest'],
                      depends=[[n, tables[n]['key']] for n in used], columns=names, rows=rows, threads=TABLE_THREADS,
                      memory=TABLE_MEMORY,
                      seconds=round(seconds, 3), sha256=oc.sha256_file(partial/'table.parquet'),
                      created_utc=oc.utc_now())
        oc.atomic_json(partial/'table.json', record)
        os.rename(partial, final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return dict(record, path=str(final/'table.parquet'), cached=False)


# =============================================================================== B features on any keys

def _policy(base):
    policy = base['candidates']
    return int(policy['history']['depth']), int(policy['popular']['depth']), int(policy['max'])


class BaseFeatures:
    """B features of a fold for arbitrary (session, aid) keys through otto_data's own SQL (§4).

    ``od.b_tables`` builds the fold tables once over the whole sess (the fold prefixes) and hist
    of ``otto_data.views``, coded by ``od.coded_events_sql``; ``frame(keys)`` runs
    ``od.b_feature_sql`` (the SQL of frame.parquet) on the keys. ``check_b_twin`` compares the B
    rows with frame.parquet, so a drift between the views and the collection is refused.
    """

    KEYS = 'agent_bk'                  # not p, s, pa, hh or bs_*: names of b_feature_sql

    def __init__(self, spec, base, columns, threads=4, memory='4GB'):
        self.spec, self.columns = spec, list(columns)
        self.temp = _spill_dir()
        self.con = harness(spec, threads, memory, temp=self.temp)
        try:
            self.con.execute(f'CREATE TEMP VIEW b_prefix AS {od.coded_events_sql("sess")}')
            self.con.execute(f'CREATE TEMP VIEW b_hist AS {od.coded_events_sql("hist")}')
            self.b = od.b_tables(self.con, base, int(spec['start']), prefix='b_prefix', hist='b_hist')
            names = [c['name'] for c in self.columns]
            require(self.b['columns'] == names, f'B columns of otto_data {self.b["columns"]} differ from the frame {names}')
            types = {c['name']: c['type'] for c in self.columns}
            require(all(self.b['types'][n] == types[n] for n in names), 'B column types differ from the frame')
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self.temp, ignore_errors=True)

    def frame(self, keys):
        """session, aid and the B columns (frame types) for the keys, in (session, aid) order."""
        pd = _pd()
        np = _np()
        con = self.con
        con.register('bk_input', pd.DataFrame({'session': keys['session'].to_numpy(dtype=np.int64),
                                               'aid': keys['aid'].to_numpy(dtype=np.int64)}))
        try:
            con.execute(f'CREATE OR REPLACE TEMP TABLE {self.KEYS} AS SELECT DISTINCT session, aid FROM bk_input')
        finally:
            con.unregister('bk_input')
        con.execute(f'CREATE OR REPLACE TEMP TABLE bf AS {od.b_feature_sql(self.b, self.KEYS)}')
        frame = con.execute('SELECT * FROM bf ORDER BY session, aid').fetch_df()
        require(len(frame) == len(keys), 'Some keys have no prefix in sess; their B features cannot be built')
        return frame

    def write_part(self, block, columns, path):
        """parquet part: session, aid, the B columns of the last ``frame`` call (frame types) and the agent
        ``columns`` of ``block`` as FLOAT (oc.agent_float_sql: non-finite or beyond FLOAT -> NULL),
        ordered by session, aid."""
        con = self.con
        con.register('agent_block', block[['session', 'aid', *columns]])
        try:
            agent = ''.join(f', {oc.agent_float_sql(f"a.{_ident(c)}")} AS {c}' for c in columns)
            names = ', '.join(f'b.{_ident(c["name"])}' for c in self.columns)
            con.execute(f"""COPY (SELECT b.session, b.aid, {names}{agent} FROM bf b JOIN agent_block a
                ON a.session = b.session AND a.aid = b.aid ORDER BY b.session, b.aid)
                TO {_literal(path)} (FORMAT parquet, COMPRESSION zstd)""")
        finally:
            con.unregister('agent_block')
        return Path(path)


def frame_columns(path):
    """B columns of a collection frame (name, DuckDB type), without session and aid."""
    con = _helper_con()
    try:
        described = con.execute(f'DESCRIBE SELECT * FROM read_parquet({_literal(path)})').fetchall()
    finally:
        con.close()
    require([r[0] for r in described[:2]] == list(oc.FRAME_KEYS), 'frame.parquet must start with session, aid')
    return [dict(name=r[0], type=r[1]) for r in described[2:]]


def same_cells(left, right, columns):
    """Per column: cells where exactly one side is NULL or |x-y| > 1e-9*(1+|x|) (H&M)."""
    np = _np()
    counts = {}
    for name in columns:
        x = left[name].to_numpy(dtype=np.float64, na_value=np.nan)
        y = right[name].to_numpy(dtype=np.float64, na_value=np.nan)
        x_null, y_null = ~np.isfinite(x), ~np.isfinite(y)
        with np.errstate(invalid='ignore', over='ignore'):
            close_ = np.abs(x-y) <= TOLERANCE*(1+np.abs(x))
        counts[name] = int((~((x_null & y_null) | (~x_null & ~y_null & close_))).sum())
    return counts


def check_b_twin(computed, frame_rows, columns):
    """The recomputed B columns equal frame.parquet on the B rows; refuses otherwise."""
    pd = _pd()
    merged = frame_rows.merge(computed, on=list(oc.FRAME_KEYS), how='left', suffixes=('', '__twin'),
                              validate='one_to_one', indicator='_twin')
    require(bool((merged['_twin'] == 'both').all()), 'B twin: some B rows were not recomputed')
    twin = pd.DataFrame({c: merged[f'{c}__twin'] for c in columns})
    bad = {c: n for c, n in same_cells(merged[columns], twin, columns).items() if n}
    require(not bad, f'B twin differs from frame.parquet: {bad}; otto_data and otto_agent disagree')


# =============================================================================== candidates BA (§5.2)

def ba_union(b_keys, sources, limit=BA_MAX):
    """BA keys: every B key, then agent items not in B up to ``limit`` per session.

    ``sources``: [(name, frame session, aid, score, rank)] in acceptance order. Agent items
    are taken by (smallest rank over the sources holding them, smallest acceptance index
    among the sources with that rank, aid). Returns session, aid, in_b and
    ag_src_<name>_rank/_score of every source holding the row, ordered by session, aid.
    """
    pd = _pd()
    np = _np()
    con = _helper_con()
    try:
        con.register('b_input', pd.DataFrame({'session': b_keys['session'].to_numpy(dtype=np.int64),
                                              'aid': b_keys['aid'].to_numpy(dtype=np.int64)}))
        con.execute('CREATE TEMP TABLE b AS SELECT DISTINCT session, aid FROM b_input')
        parts = []
        for index, (name, frame) in enumerate(sources):
            require(NAME.fullmatch(name), f'Bad source name {name!r}')
            con.register(f'src_{index}_input', frame[['session', 'aid', 'score', 'rank']])
            con.execute(f'''CREATE TEMP TABLE src_{index} AS SELECT CAST(session AS BIGINT) AS session,
                CAST(aid AS BIGINT) AS aid, CAST(score AS DOUBLE) AS score, CAST(rank AS BIGINT) AS rank
                FROM src_{index}_input''')
            parts.append(f'SELECT session, aid, rank, {index} AS acc FROM src_{index}')
        if parts:
            con.execute(f"""CREATE TEMP TABLE agent AS SELECT session, aid FROM (
                SELECT a.session, a.aid, row_number() OVER (PARTITION BY a.session ORDER BY a.r, a.acc, a.aid) AS ord,
                       coalesce(nb.n, 0) AS nb
                FROM (SELECT session, aid, min(rank) AS r, arg_min(acc, rank * 1000 + acc) AS acc
                      FROM ({' UNION ALL '.join(parts)}) GROUP BY session, aid) a
                LEFT JOIN (SELECT session, count(*) AS n FROM b GROUP BY session) nb USING (session)
                WHERE NOT EXISTS (SELECT 1 FROM b WHERE b.session = a.session AND b.aid = a.aid))
                WHERE ord <= {int(limit)} - nb""")
        else:
            con.execute('CREATE TEMP TABLE agent (session BIGINT, aid BIGINT)')
        joins, cols = [], []
        for index, (name, _) in enumerate(sources):
            rank_col, score_col = source_columns(name)
            joins.append(f'LEFT JOIN src_{index} s{index} ON s{index}.session = u.session AND s{index}.aid = u.aid')
            cols.append(f's{index}.rank AS "{rank_col}", s{index}.score AS "{score_col}"')
        select = ', '.join(['u.session', 'u.aid', 'u.in_b', *cols])
        return con.execute(f"""SELECT {select} FROM (SELECT session, aid, true AS in_b FROM b
            UNION ALL SELECT session, aid, false FROM agent) u {' '.join(joins)} ORDER BY u.session, u.aid""").fetch_df()
    finally:
        con.close()


# =============================================================================== the agent block of a set on a batch

def dependents(agent_set, table_name):
    """Ids of the set proposals that read tb_<table_name>, directly or through other tables."""
    names, out = {table_name}, []
    for proposal in agent_set['proposals']:
        if set(proposal.get('depends') or []) & names:
            out.append(proposal['id'])
            if proposal['kind'] == 'table':
                names.add(proposal['name'])
    return out


def set_tables(spec, agent_set, *, timeout_s, threads, memory=None, fingerprint=None, fresh=None):
    """Every table of the set on F_k in set order (cache first, or all recomputed into ``fresh``).
    A failing table refuses with its dependents."""
    tables = {}
    for proposal in agent_set['proposals']:
        if proposal['kind'] != 'table':
            continue
        try:
            entry = compute_table(spec, proposal, tables, timeout_s=timeout_s, threads=threads, memory=memory,
                                  fingerprint=fingerprint, fresh=fresh)
        except ProposalError as exc:
            fallen = dependents(agent_set, proposal['name'])
            raise ProposalError(f"{proposal['id']}: {exc}; dependent proposals fall with it: "
                                f"{', '.join(fallen) or 'none'}") from None
        require(entry['columns'] == proposal['columns'], f"{proposal['id']}: table columns differ from the set")
        tables[proposal['name']] = entry
    return tables


class _Clock:
    """Seconds per proposal over the batches of one fold (every sidecar of the collection), against
    PROPOSAL_CAP (x the retry factor)."""

    def __init__(self, cap):
        self.cap, self.used, self.spent = cap, {}, {}

    def load(self, pid, seconds):
        """Seconds of earlier batches (sidecar.json, progress.json, abandoned sidecars)."""
        self.used[pid] = self.used.get(pid, 0.0)+seconds

    def left(self, pid, batch_timeout):
        left = self.cap - self.used.get(pid, 0.0)
        if left <= 0:
            raise ProposalError(f'{pid}: over {self.cap:g} s on this fold')
        return min(batch_timeout, left)

    def add(self, pid, seconds):
        """Seconds spent now, a failed or timed-out run included (``spent`` holds what this process added)."""
        self.used[pid] = self.used.get(pid, 0.0)+seconds
        self.spent[pid] = self.spent.get(pid, 0.0)+seconds


def agent_block(spec, b_keys, agent_set, tables, *, threads, memory=None, batch_timeout=BATCH_TIMEOUT,
                clock=None, known=None, scratch=None):
    """The agent columns of one batch: sources on the B keys, BA union, features on the BA keys.

    Returns a frame session, aid, in_b and the set columns in set order (DOUBLE), ordered by
    session, aid, and the seconds per proposal. Any failure raises ProposalError with the id.
    """
    pd = _pd()
    np = _np()
    clock = _Clock(float('inf')) if clock is None else clock
    known = known_items(spec) if known is None else known
    paths = {name: entry['path'] for name, entry in tables.items()}
    own = scratch is None
    scratch = Path(tempfile.mkdtemp(prefix='otto-agent-keys-')) if own else Path(scratch)
    seconds = {}
    try:
        sources = [p for p in agent_set['proposals'] if p['kind'] == 'source']
        features = [p for p in agent_set['proposals'] if p['kind'] == 'feature']
        found = []
        if sources:
            con = sandbox(spec, _stage_keys(b_keys, scratch/'keys-b.parquet'), tables=paths, threads=threads,
                          memory=memory)
            try:
                for proposal in sources:
                    pid = proposal['id']
                    sec, started = None, time.monotonic()
                    try:
                        check_sql(proposal['sql'], 'source', proposal['level'], tables=list(paths))
                        result, _, _, sec = execute(con, 'source', proposal['level'], proposal['sql'], spec['start'],
                                                    spec['end'], clock.left(pid, batch_timeout), known=known)
                    except ProposalError as exc:
                        raise ProposalError(f'{pid}: {exc}') from None
                    finally:                       # a timeout or failure spends its seconds too
                        clock.add(pid, time.monotonic()-started if sec is None else sec)
                    seconds[pid] = round(sec, 3)
                    found.append((proposal['name'], result.rename(columns={'item': 'aid'})))
            finally:
                close(con)
        frame = ba_union(b_keys, found)
        if features:
            con = sandbox(spec, _stage_keys(frame, scratch/'keys-ba.parquet'), tables=paths, threads=threads,
                          memory=memory)
            try:
                for proposal in features:
                    pid = proposal['id']
                    sec, started = None, time.monotonic()
                    try:
                        check_sql(proposal['sql'], 'feature', proposal['level'], tables=list(paths))
                        result, names, _, sec = execute(con, 'feature', proposal['level'], proposal['sql'],
                                                        spec['start'], spec['end'], clock.left(pid, batch_timeout),
                                                        known=known)
                    except ProposalError as exc:
                        raise ProposalError(f'{pid}: {exc}') from None
                    finally:                       # a timeout or failure spends its seconds too
                        clock.add(pid, time.monotonic()-started if sec is None else sec)
                    if names != proposal['columns']:
                        raise ProposalError(f'{pid}: value columns {names} differ from the frozen {proposal["columns"]}')
                    seconds[pid] = round(sec, 3)
                    matrix = align(result, proposal['level'], frame['session'].to_numpy(dtype=np.int64),
                                   frame['aid'].to_numpy(dtype=np.int64))[1]
                    for j, name in enumerate(names):
                        frame[name] = matrix[:, j]
            finally:
                close(con)
        columns = agent_set['columns']
        for name in columns:
            if name not in frame.columns:
                frame[name] = np.nan
        out = frame[['session', 'aid', 'in_b', *columns]].copy()
        for name in columns:
            out[name] = pd.to_numeric(out[name], errors='coerce').astype('float64')
        return out, seconds
    finally:
        if own:
            shutil.rmtree(scratch, ignore_errors=True)


def align(frame, level, sessions, items):
    """Values of a level-keyed frame on the given (session, aid) rows: (names, float64 matrix, NaN where absent)."""
    np = _np()
    pd = _pd()
    keys = LEVEL_KEYS[level]
    names = [c for c in frame.columns if c not in keys]
    if level == 'pair':
        index = pd.MultiIndex.from_arrays([frame[k].to_numpy(dtype=np.int64) for k in keys])
        target = pd.MultiIndex.from_arrays([sessions, items])
    else:
        index = pd.Index(frame[keys[0]].to_numpy(dtype=np.int64))
        target = pd.Index(sessions if level == 'session' else items)
    require(index.is_unique, 'Aligned values need unique keys')
    positions = index.get_indexer(target)
    matrix = np.full((len(positions), len(names)), np.nan)
    if names and len(frame):
        values = frame[names].to_numpy(dtype=np.float64, na_value=np.nan)
        hit = positions >= 0
        matrix[hit] = values[positions[hit]]
    with np.errstate(invalid='ignore'):
        matrix[~np.isfinite(matrix)] = np.nan
    return names, matrix


# =============================================================================== journal and small file helpers

def journal_dir():
    """docs/otto-run/ (§5.8): prompts, replies, log.jsonl, run.json, calibration, leakcheck."""
    return Path(oc.ROOT)/'docs'/'otto-run'


def _journal_json(name, value):
    """Copy of a record into docs/otto-run/; an existing file with other content is refused."""
    path = journal_dir()/name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
    if path.exists():
        require(path.read_text(encoding='utf-8') == text, f'{path} exists with other content')
        return path
    oc.atomic_json(path, value)
    return path


def _timed(con, sql, cap):
    """(first value, seconds, timed_out) of a harness query interrupted after ``cap`` seconds."""
    duckdb = _duckdb()
    fired = threading.Event()

    def fire():
        fired.set()
        con.interrupt()
    timer = threading.Timer(cap, fire)
    timer.daemon = True
    started = time.monotonic()
    timer.start()
    try:
        value = con.execute(sql).fetchone()[0]
    except duckdb.Error:
        if fired.is_set():
            return None, time.monotonic()-started, True
        raise
    finally:
        timer.cancel()
    seconds = time.monotonic()-started
    return (None, seconds, True) if fired.is_set() else (value, seconds, False)


# =============================================================================== calibration of table (§5.4)

def table_timeout(t20, timed_out=False):
    """(T_tb, limitation): 3·t_20 rounded up to 60 s and clamped to [1200, 1800] s (§5.4).

    t_20 above 1800 s (or an interrupted aggregation) gives 1800 s and a recorded limitation.
    """
    if timed_out or t20 is None or float(t20) > T_TB_MAX:
        return T_TB_MAX, (f't_20 above {T_TB_MAX} s: T_tb = {T_TB_MAX} s; tables with a window wider than '
                          f'{max(CALIBRATION_WINDOWS)} will probably not fit on the probe')
    value = math.ceil(T_TB_FACTOR*float(t20)/T_TB_STEP)*T_TB_STEP
    return int(min(max(value, T_TB_MIN), T_TB_MAX)), None


def _join(window):
    return f'FROM e a JOIN e b ON a.session = b.session AND b.seq > a.seq AND b.seq <= a.seq + {int(window)}'


def calibrate(name=None, collection=None, threads=CALIBRATION_THREADS, memory=None, cap=float(T_TB_MAX)):
    """The neutral self-join of I_3 at L = 5 and 20 and the high-cardinality aggregation (§5.4).

    Writes calibration/<name>/calibration.json and docs/otto-run/calibration-<name>.json.
    """
    memory = MEMORY if memory is None else memory
    collection = Path(collection if collection is not None else oc.collection_dir('probe')).resolve()
    spec = fold_spec(PROBE_FOLD, 'calibration', collection)
    name = _output_name(name, f'cal-{_stamp()}')
    out = oc.output_dir('calibration', name)
    require(not out.exists(), f'{out} exists; every output is new')
    require(not (journal_dir()/f'calibration-{name}.json').exists(), f'calibration-{name}.json exists in the journal')
    temp = _spill_dir()
    con = harness(spec, _threads(threads), _memory(memory), temp=temp)
    try:
        # through seq: the load's seq has gaps after the aid filter of the fold; I_3 is renumbered per session
        con.execute('''CREATE TEMP TABLE e AS SELECT session, row_number() OVER (PARTITION BY session ORDER BY seq, src)
            AS seq FROM (SELECT session, seq, 0 AS src FROM hist UNION ALL SELECT session, seq, 1 FROM sess)''')
        sessions, total, quantiles, top = con.execute(
            'SELECT count(*), sum(n2), quantile_disc(n2, [0.5, 0.9, 0.99]), max(n2) FROM '
            '(SELECT session, count(*) * count(*) AS n2 FROM e GROUP BY session)').fetchone()
        pairs, seconds, interrupted = {}, {}, {}
        for window in CALIBRATION_WINDOWS:
            value, sec, timed_out = _timed(con, f'SELECT count(*) {_join(window)}', cap)
            pairs[str(window)] = None if value is None else int(value)
            seconds[f'join_{window}'] = round(sec, 1)
            interrupted[f'join_{window}'] = timed_out
        window = max(CALIBRATION_WINDOWS)
        _, t20, timed_out = _timed(con, f'SELECT count(*) FROM (SELECT {CALIBRATION_KEY} AS g, count(*) AS n '
                                        f'{_join(window)} GROUP BY g)', cap)
        seconds[f'aggregation_{window}'] = round(t20, 1)
        interrupted[f'aggregation_{window}'] = timed_out
    finally:
        con.close()
        shutil.rmtree(temp, ignore_errors=True)
    t_tb, limitation = table_timeout(None if timed_out else t20, timed_out)
    sessions = int(sessions)
    record = dict(format=CALIBRATION_FORMAT, fold=PROBE_FOLD, collection=_relative(collection),
                  views_digest=spec['digest'], fingerprint=views_fingerprint(spec), sessions=sessions,
                  n2=dict(p50=int(quantiles[0] or 0), p90=int(quantiles[1] or 0), p99=int(quantiles[2] or 0),
                          max=int(top or 0), sum=int(total or 0)),
                  pairs=pairs, pairs_per_session={k: None if v is None or not sessions else round(v/sessions, 2)
                                                  for k, v in pairs.items()},
                  seconds=seconds, interrupted=interrupted, cap_seconds=float(cap),
                  t_20=None if timed_out else round(t20, 1), t_tb=t_tb, limitation=limitation,
                  rule=f'T_tb = clamp(ceil({T_TB_FACTOR}*t_20/{T_TB_STEP})*{T_TB_STEP}, {T_TB_MIN}, {T_TB_MAX}) s',
                  threads=threads, memory=memory, created_utc=oc.utc_now())
    oc.new_output(out)
    oc.atomic_json(out/'calibration.json', record)
    _journal_json(f'calibration-{name}.json', record)
    return dict(record, path=str(out/'calibration.json'))


def read_calibration(path=None):
    """A calibration record: the given file or the only calibration under artifacts/otto/calibration."""
    if path is None:
        root = oc.output_dir('calibration')
        found = sorted(root.glob('*/calibration.json')) if root.exists() else []
        require(len(found) == 1, f'Name the calibration: {len(found)} found')
        path = found[0]
    record = oc.read_json(path)
    require(record.get('format') == CALIBRATION_FORMAT and record.get('fold') == PROBE_FOLD, 'Not a calibration of F3')
    expected, _ = table_timeout(record.get('t_20'), record.get('t_20') is None)
    require(record.get('t_tb') == expected, 'Calibration T_tb does not follow its t_20')
    return dict(record, path=str(Path(path).resolve()), sha256=oc.sha256_file(path))


# =============================================================================== probe (§5.4)

KEYS_FILE = 'keys.parquet'
STATS_FILE = 'stats.json'
PROBE_FILE = 'probe.json'


def _neutral_counts(con, table, where=''):
    rows = con.execute(f'SELECT event, count(*), count(DISTINCT session), count(DISTINCT item) FROM {table} '
                       f'{where} GROUP BY event ORDER BY event').fetchall()
    found = {r[0]: dict(events=int(r[1]), sessions=int(r[2]), items=int(r[3])) for r in rows}
    return {name: found.get(name, dict(events=0, sessions=0, items=0)) for name in oc.NEUTRAL_EVENTS}


def _quantile_dict(con, expr, source):
    q = con.execute(f'SELECT quantile_disc({expr}, [0.5, 0.9, 0.99]), max({expr}) FROM {source}').fetchone()
    values = list(q[0] or [0, 0, 0])
    return dict(p50=int(values[0]), p90=int(values[1]), p99=int(values[2]), max=int(q[1] or 0))


def probe_stats(spec, frame_path, calibration, threads=4, memory='4GB'):
    """stats.json (§5.4): I_3 only, neutral names; n² and pairs per session from the calibration."""
    temp = _spill_dir()
    con = harness(spec, threads, memory, temp=temp)
    start = int(spec['start'])
    try:
        stats = {f'history_{days}d': _neutral_counts(con, 'hist', f'WHERE ts >= {start - days*oc.DAY}')
                 for days in (7, 14)}
        stats['prefixes'] = _neutral_counts(con, 'sess')
        stats['prefix_sessions'] = int(con.execute('SELECT count(DISTINCT session) FROM sess').fetchone()[0])
        stats['prefix_length'] = _quantile_dict(con, 'n', '(SELECT session, count(*) AS n FROM sess GROUP BY session)')
        shares = con.execute(f"""SELECT avg(c), avg(o) FROM (SELECT session,
            max(CASE WHEN event = {_literal(oc.NEUTRAL_EVENTS[1])} THEN 1 ELSE 0 END) AS c,
            max(CASE WHEN event = {_literal(oc.NEUTRAL_EVENTS[2])} THEN 1 ELSE 0 END) AS o FROM sess GROUP BY session)
            """).fetchone()
        stats[f'share_prefixes_with_{oc.NEUTRAL_EVENTS[1]}'] = round(float(shares[0] or 0), 3)
        stats[f'share_prefixes_with_{oc.NEUTRAL_EVENTS[2]}'] = round(float(shares[1] or 0), 3)
        stats['events_per_item'] = _quantile_dict(
            con, 'n', '(SELECT item, count(*) AS n FROM (SELECT item FROM hist UNION ALL SELECT item FROM sess) '
                      'GROUP BY item)')
        mean = con.execute(f'SELECT count(*) / count(DISTINCT session) FROM read_parquet({_literal(frame_path)})'
                           ).fetchone()[0]
        stats['base_candidates_per_session'] = round(float(mean or 0), 1)
    finally:
        con.close()
        shutil.rmtree(temp, ignore_errors=True)
    stats['events_squared_per_session'] = dict(calibration['n2'])
    stats['event_pairs_per_session'] = {f'within_{k}': v for k, v in calibration['pairs_per_session'].items()}
    return stats


def prepare_probe(name=None, collection=None, val=None, calibration=None, threads=4, memory='4GB'):
    """probe/<name>/: keys.parquet (B keys of the pool), stats.json and probe.json (§5.4)."""
    base = oc.read_base()
    collection = Path(collection if collection is not None else oc.collection_dir('probe')).resolve()
    manifest = oc.read_collection(collection, role='probe', base=base)
    require(manifest['fold'] == PROBE_FOLD, 'The probe lives on F3')
    val = Path(val if val is not None else oc.collection_dir('val')).resolve()
    val_manifest = oc.read_collection(val, role='val', base=base)
    population = set(oc.read_population(val))
    frame_path = collection/oc.FRAME_FILE
    keys = oc.read_parquet(frame_path, columns=list(oc.FRAME_KEYS))
    pool = oc.first_in_order(keys['session'].unique().tolist(), None, key=oc.probe_key)
    require(not set(pool) & population, 'The probe pool overlaps the dev population')
    require(manifest.get('pool_digest') == oc.canonical_digest(pool), 'The probe frame is not the recorded pool')
    require(val_manifest.get('probe_pool_digest') == manifest['pool_digest'],
            'The dev population was drawn outside another pool')
    cal = read_calibration(calibration)
    spec = fold_spec(PROBE_FOLD, 'probe', collection)
    fingerprint = views_fingerprint(spec)
    require(cal['fingerprint'] == fingerprint, 'The calibration was measured on other I_3 data')
    stats = probe_stats(spec, frame_path, cal, threads, memory)
    out = oc.new_output(oc.output_dir('probe', _output_name(name, f'probe-{_stamp()}')))
    _stage_keys(keys, out/KEYS_FILE)
    oc.atomic_json(out/STATS_FILE, stats)
    record = dict(format=PROBE_FORMAT, fold=PROBE_FOLD, collection=_relative(collection),
                  manifest_sha256=oc.sha256_file(collection/oc.MANIFEST_FILE), val=_relative(val),
                  population_digest=oc.canonical_digest(sorted(population)), pool_size=len(pool),
                  pool_digest=manifest['pool_digest'], rows=int(len(keys)), base_digest=base['digest'],
                  views_digest=spec['digest'], fingerprint=fingerprint,
                  calibration=dict(path=_relative(cal['path']), sha256=cal['sha256'], t_tb=cal['t_tb'],
                                   limitation=cal['limitation']),
                  files={n: oc.sha256_file(out/n) for n in (KEYS_FILE, STATS_FILE)}, created_utc=oc.utc_now())
    oc.atomic_json(out/PROBE_FILE, record)
    return dict(record, path=str(out))


def _from_root(text):
    path = Path(text)
    return path if path.is_absolute() else Path(oc.ROOT)/path


def read_probe(path):
    """probe.json with its files, the collection manifest and the calibration hash checked."""
    path = Path(path).resolve()
    record = oc.read_json(path/PROBE_FILE)
    require(record.get('format') == PROBE_FORMAT and record.get('fold') == PROBE_FOLD, 'Not an OTTO probe')
    for name, digest in record['files'].items():
        require(oc.sha256_file(path/name) == digest, f'Probe file changed: {name}')
    collection = _from_root(record['collection'])
    require(oc.sha256_file(collection/oc.MANIFEST_FILE) == record['manifest_sha256'], 'Probe collection changed')
    require(oc.sha256_file(_from_root(record['calibration']['path'])) == record['calibration']['sha256'],
            'Calibration changed since the probe')
    return record


def probe_identity(path):
    path = Path(path).resolve()
    record = read_probe(path)
    return dict(path=_relative(path), collection=record['collection'], pool_size=record['pool_size'],
                rows=record['rows'], probe_sha256=oc.sha256_file(path/PROBE_FILE),
                stats_sha256=record['files'][STATS_FILE], base_digest=record['base_digest'],
                t_tb=record['calibration']['t_tb'], calibration_sha256=record['calibration']['sha256'])


class ProbeData:
    """Everything the evaluation needs from a probe; the labels are not here (Scorer only)."""

    def __init__(self, path):
        np = _np()
        self.path = Path(path).resolve()
        self.record = read_probe(self.path)
        self.collection = _from_root(self.record['collection'])
        self.spec = fold_spec(PROBE_FOLD, 'probe', self.collection)
        require(self.spec['digest'] == self.record['views_digest'], 'Probe views differ from probe.json')
        self.fingerprint = self.record['fingerprint']
        self.t_tb = float(self.record['calibration']['t_tb'])
        self.keys_path = self.path/KEYS_FILE
        frame_path = self.collection/oc.FRAME_FILE
        self.base_columns = frame_columns(frame_path)
        frame = oc.read_parquet(frame_path)
        frame = frame.sort_values(list(oc.FRAME_KEYS), kind='mergesort').reset_index(drop=True)
        self.frame = frame
        self.keys = frame[list(oc.FRAME_KEYS)].copy()
        require(len(self.keys) == self.record['rows'], 'Probe keys differ from the frame')
        self.base_names = [c['name'] for c in self.base_columns]
        self.base_values = frame[self.base_names].to_numpy(dtype=np.float64, na_value=np.nan)
        self.pool = oc.first_in_order(self.keys['session'].unique().tolist(), None, key=oc.probe_key)
        self.cohort = self.pool[:INVARIANCE_SESSIONS]
        self.known = known_items(self.spec)
        self.stats = oc.read_json(self.path/STATS_FILE)


def probe_labels(collection):
    """Labels of the probe pool, for the feedback formatter only; any collection but probe-F3 is refused."""
    collection = Path(collection)
    manifest = oc.read_collection(collection)
    require(manifest.get('role') == 'probe' and manifest.get('fold') == PROBE_FOLD,
            f'The feedback reads only the probe labels of F{PROBE_FOLD}, not {manifest.get("role")}-F{manifest.get("fold")}')
    labels = oc.read_parquet(collection/oc.LABELS_FILE, columns=list(oc.LABEL_COLUMNS))
    pool = set(oc.read_parquet(collection/oc.FRAME_FILE, columns=['session'])['session'])
    require(set(labels['session']) <= pool, 'Probe labels outside the pool')
    return labels


# =============================================================================== coarse recall (§5.5)

def _gain_text(value):
    return f'{round(float(value), GAIN_DIGITS)+0.0:.{GAIN_DIGITS}f}'


def _recall_text(value):
    return f'{round(float(value), RECALL_DIGITS)+0.0:.{RECALL_DIGITS}f}'


class Scorer:
    """Recall on the probe labels: denominators sum over sessions of min(20, |G|) per type."""

    def __init__(self, labels):
        pd = _pd()
        np = _np()
        self.con = _helper_con()
        frame = pd.DataFrame({'session': labels['session'].to_numpy(dtype=np.int64),
                              'type': labels['type'].astype(str).to_numpy(),
                              'aid': labels['aid'].to_numpy(dtype=np.int64)})
        self.con.register('lab_input', frame)
        self.con.execute('CREATE TABLE lab AS SELECT DISTINCT session, type, aid FROM lab_input')
        self.con.unregister('lab_input')
        rows = self.con.execute(f'''SELECT type, sum(least({oc.TOP_K}, n)) FROM (SELECT session, type, count(*) AS n
            FROM lab GROUP BY ALL) GROUP BY type''').fetchall()
        self.den = {t: 0 for t in od.TYPE_NAMES}
        self.den.update({t: int(n) for t, n in rows})

    def close(self):
        self.con.close()

    def _share(self, hits):
        return {oc.NEUTRAL_EVENTS[code]: (hits.get(t, 0)/self.den[t] if self.den[t] else 0.0)
                for code, t in enumerate(od.TYPE_NAMES)}

    def recall(self, keys):
        """Candidates (session, aid): the share of labels covered, per neutral type."""
        pd = _pd()
        np = _np()
        self.con.register('rc_input', pd.DataFrame({'session': keys['session'].to_numpy(dtype=np.int64),
                                                    'aid': keys['aid'].to_numpy(dtype=np.int64)}))
        try:
            rows = self.con.execute(f'''SELECT type, sum(least({oc.TOP_K}, n)) FROM (
                SELECT l.session, l.type, count(*) AS n FROM lab l SEMI JOIN rc_input c
                ON c.session = l.session AND c.aid = l.aid GROUP BY ALL) GROUP BY type''').fetchall()
        finally:
            self.con.unregister('rc_input')
        return self._share({t: int(n) for t, n in rows})

    def ranked(self, sessions, aids, values):
        """R@20 per neutral type when every session's candidates are ranked by ``values`` alone.

        The better direction per type; NULL last; ties to the smaller aid.
        """
        pd = _pd()
        np = _np()
        frame = pd.DataFrame({'session': np.asarray(sessions, dtype=np.int64), 'aid': np.asarray(aids, dtype=np.int64),
                              'v': np.asarray(values, dtype=np.float64)})
        self.con.register('rk_input', frame)
        best = {}
        try:
            for order in ('DESC', 'ASC'):
                rows = self.con.execute(f'''SELECT l.type, count(*) FROM (SELECT session, aid,
                    row_number() OVER (PARTITION BY session ORDER BY CASE WHEN isfinite(v) THEN v END {order} NULLS LAST,
                    aid) AS r FROM rk_input) x JOIN lab l ON l.session = x.session AND l.aid = x.aid
                    WHERE x.r <= {oc.TOP_K} GROUP BY l.type''').fetchall()
                for name, share in self._share({t: int(n) for t, n in rows}).items():
                    best[name] = max(best.get(name, 0.0), share)
        finally:
            self.con.unregister('rk_input')
        return best


# =============================================================================== validity (§5.4, H&M)

def _spearman(a, b):
    np = _np()
    pd = _pd()
    both = ~(np.isnan(a) | np.isnan(b))
    if both.sum() < MIN_SPEARMAN_ROWS:
        return None
    ra = pd.Series(a[both]).rank(method='average').to_numpy()
    rb = pd.Series(b[both]).rank(method='average').to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _sample(n):
    np = _np()
    if n <= SAMPLE_ROWS:
        return np.arange(n)
    return np.sort(np.random.default_rng(oc.SEEDS[0]).choice(n, SAMPLE_ROWS, replace=False))


def column_summary(name, column, reference):
    """Coverage, distinct bucket and the nearest reference column (|Spearman| on the sample); problems."""
    np = _np()
    present = ~np.isnan(column)
    count = int(present.sum())
    distinct = int(np.unique(column[present]).size)
    sample = _sample(len(column))
    best = nearest = None
    for other, series in reference:
        rho = _spearman(column[sample], series[sample])
        if rho is not None and (best is None or abs(rho) > best):
            best, nearest = abs(rho), other
    summary = dict(name=name, non_null_share=_share(count/len(column)) if len(column) else None,
                   distinct=log2_bucket(distinct), max_abs_spearman=None if best is None else round(best, 1),
                   nearest=nearest)
    problems = []
    if distinct < MIN_DISTINCT:
        problems.append(f'{name}: fewer than {MIN_DISTINCT} distinct non-NULL values')
    if count < MIN_NON_NULL:
        problems.append(f'{name}: fewer than {MIN_NON_NULL} non-NULL rows')
    if best is not None and best >= RHO_LIMIT:
        problems.append(f'{name}: |Spearman| with {nearest} reaches {RHO_LIMIT}')
    return summary, problems


def as_float32(values):
    """float64 copy of the values as the model sees them (FLOAT in the BA frame); non-finite -> NaN."""
    np = _np()
    with np.errstate(over='ignore', invalid='ignore'):
        out = np.asarray(values, dtype=np.float64).astype(np.float32).astype(np.float64)
    out[~np.isfinite(out)] = np.nan
    return out


def _mismatches(x, y):
    np = _np()
    with np.errstate(invalid='ignore'):
        same = (np.isnan(x) & np.isnan(y)) | (np.abs(x-y) <= TOLERANCE*(1+np.abs(x)))
    return int((~same).sum())


def source_mismatches(left, right):
    """Rows present on one side only plus scores that differ (session, aid, score frames)."""
    np = _np()
    merged = left[['session', 'aid', 'score']].merge(right[['session', 'aid', 'score']], on=['session', 'aid'],
                                                     how='outer', suffixes=('_l', '_r'), indicator=True)
    only = int((merged['_merge'] != 'both').sum())
    both = merged[merged['_merge'] == 'both']
    return only + _mismatches(both['score_l'].to_numpy(dtype=np.float64), both['score_r'].to_numpy(dtype=np.float64))


def column_problem(names, taken):
    """Names of a feature proposal: 1-3 unique ag_* names, not ag_src_*, not a base or accepted column."""
    if not 1 <= len(names) <= MAX_VALUES:
        return f'a feature has 1 to {MAX_VALUES} value columns'
    if len(set(names)) != len(names):
        return 'value column names repeat'
    for name in names:
        if not VALUE_NAME.fullmatch(name) or name.startswith(SOURCE_PREFIX):
            return f'column {name} breaks the naming contract'
        if name in taken:
            return f'column {name} is already accepted'
    return None


# =============================================================================== run state and evaluation (§5.1, §5.2, §5.4)

def budget_limits(t_tb):
    """Probe budgets of a run: tables 4·T_tb, sources and pair/session features 900 s, item features 600 s."""
    return dict(table_seconds=float(TABLE_BUDGET_FACTOR*t_tb),
                pair_session_seconds=PROBE_BUDGETS['pair_session_seconds'],
                item_seconds=PROBE_BUDGETS['item_seconds'])


def budget_key(kind, level):
    if kind == 'table':
        return 'table_seconds'
    return 'item_seconds' if (kind, level) == ('feature', 'item') else 'pair_session_seconds'


def probe_timeout(kind, level, t_tb):
    if kind == 'table':
        return float(t_tb)
    return PROBE_TIMEOUTS['source' if kind == 'source' else level]


def phase_of(round_index):
    return 'S' if round_index <= S_ROUNDS else 'F'


class RunState:
    """Phase, accepted tables, sources and agent columns, and the probe keys they live on."""

    def __init__(self, data, workdir, base):
        self.data, self.base = data, base
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.phase = 'S'
        self.tables = {}                       # name -> table cache entry
        self.sources = []                      # [(name, frame session, aid, score, rank)] in acceptance order
        self.keys, self.keys_path = data.keys, data.keys_path
        self.base_values = data.base_values
        self.values = {}                       # model column -> float64 over self.keys
        self.candidates = None
        self._best_b = None
        self._twin = None
        self._permuted = self._permuted_keys = None

    def twin(self):
        if self._twin is None:
            self._twin = BaseFeatures(self.data.spec, self.base, self.data.base_columns)
        return self._twin

    def base_on(self, keys):
        """B columns on any probe keys (the twin of otto_data's formulas, checked on the B rows): float64 matrix."""
        np = _np()
        computed = self.twin().frame(keys)
        check_b_twin(computed, self.data.frame, self.data.base_names)
        return computed[self.data.base_names].to_numpy(dtype=np.float64, na_value=np.nan)

    def permuted(self):
        if self._permuted is None:
            self._permuted = PermutedSess(self.data.spec)
        return self._permuted

    def permuted_run(self, tables):
        """(spec, keys file) of the scored pass: the probe keys with permuted sessions."""
        permuted = self.permuted()
        permuted.check_tables(tables)
        if self._permuted_keys is None:
            self._permuted_keys = _stage_keys(permuted.keys(self.keys), permuted.dir/'keys.parquet')
        return permuted, self._permuted_keys

    def close(self):
        if self._twin is not None:
            self._twin.close()
            self._twin = None
        if self._permuted is not None:
            self._permuted.close()
            self._permuted = self._permuted_keys = None

    def reference(self):
        refs = [(name, self.base_values[:, i]) for i, name in enumerate(self.data.base_names)]
        return refs + list(self.values.items())

    def union(self, extra=None):
        return ba_union(self.data.keys, self.sources + ([extra] if extra is not None else []))

    def table_paths(self, names):
        return {name: self.tables[name]['path'] for name in names}

    def best_b(self, scorer):
        """Best single B column per neutral type on the current keys (R@20)."""
        if self._best_b is None:
            best = {}
            sessions, aids = self.keys['session'].to_numpy(), self.keys['aid'].to_numpy()
            for i, name in enumerate(self.data.base_names):
                for kind, value in scorer.ranked(sessions, aids, self.base_values[:, i]).items():
                    if kind not in best or value > best[kind][1]:
                        best[kind] = (name, value)
            self._best_b = best
        return self._best_b

    def freeze_candidates(self):
        """End of phase S: keys become BA = B plus the accepted sources (§5.2); the probe frame is rebuilt."""
        np = _np()
        require(self.phase == 'S', 'The candidates are frozen once')
        frame = self.union()
        keys = frame[['session', 'aid']]
        self.base_values = self.base_on(keys)
        self.close()
        self.keys = keys.reset_index(drop=True)
        self.keys_path = _stage_keys(self.keys, self.workdir/'keys-ba.parquet')
        self.values = {name: as_float32(frame[name].to_numpy(dtype=np.float64, na_value=np.nan))
                       for name in frame.columns if name.startswith(SOURCE_PREFIX)}
        path = self.workdir/'candidates.parquet'
        oc.write_parquet(frame, path, order_by='session, aid')
        self.candidates = dict(sources=[name for name, _ in self.sources], rows=int(len(frame)),
                               agent_rows=int((~frame['in_b']).sum()), sha256=oc.sha256_file(path))
        self.phase = 'F'
        self._best_b = None
        return self.candidates


def _record(proposal):
    source = proposal if isinstance(proposal, dict) else {}
    record = {key: source.get(key) for key in ('id', 'round', 'index', *FIELDS)}
    record.update(status='invalid', error=None, seconds=None, rows=None, columns=[], depends=[])
    return record


class PermutedSess:
    """The probe's sess under a bijection of its session ids (no addressed oracle, §5.3-§5.4).

    The sorted ids of sess map to a permutation of the same ids (PERMUTATION_SEED): neither
    order nor residues survive. sess, cand and sessions of a run see the mapped ids; hist
    holds no session of the target week (otto_data folds) and tb_* are item x item tables
    that read hist only (check_sql refuses sess, cand and sessions in a table), so nothing
    else carries the real ids. The scored pass of every source and feature runs here and its
    result is mapped back before coverage, the checks and the Scorer: a selection by literal
    ids or by the arithmetic of ids lands on random sessions. The two halves of batch
    invariance run on the real ids, so such a selection also differs on the cohort.
    """

    def __init__(self, spec):
        np = _np()
        pd = _pd()
        files = spec['files']['sess']
        old = _list_literal(files)
        text = spec['views']['sess']
        require(text.count(old) == 1, 'The sess view of otto_data must name its file list exactly once')
        self.dir = _spill_dir()
        target = self.dir/'sess'/'sess.parquet'
        target.parent.mkdir()
        source = f'read_parquet({old}, hive_partitioning=false)'
        con = od.connect(4, HELPER_MEMORY, temp=self.dir/'spill')
        try:
            kind = {row[0]: row[1] for row in con.execute(f'DESCRIBE SELECT * FROM {source}').fetchall()}['session']
            ids = np.asarray([s for (s,) in con.execute(f'SELECT DISTINCT session FROM {source} ORDER BY 1').fetchall()],
                             dtype=np.int64)
            mapped = np.random.default_rng(PERMUTATION_SEED).permutation(ids)
            con.register('perm_map', pd.DataFrame({'src': ids, 'dst': mapped}))
            rest = ', '.join(f'x.{c}' for c in oc.EVENT_COLUMNS if c != 'session')
            con.execute(f"""COPY (SELECT CAST(m.dst AS {kind}) AS session, {rest} FROM {source} x
                JOIN perm_map m ON m.src = x.session) TO {_literal(target)} (FORMAT parquet)""")
        except BaseException:
            con.close()
            self.close()
            raise
        con.close()
        self.forward = pd.Series(mapped, index=ids)
        self.backward = pd.Series(ids, index=mapped)
        self.spec = dict(spec, views=dict(spec['views'], sess=text.replace(old, _list_literal([target]))),
                         files=dict(spec['files'], sess=[str(target)]),
                         directories=dict(spec['directories'], sess=[str(target.parent)]))

    def check_tables(self, tables):
        """tb_* are item x item: a session column there would keep the real ids beside the mapped ones."""
        con = _helper_con()
        try:
            for name, path in dict(tables or {}).items():
                columns = [row[0] for row in con.execute(
                    f'DESCRIBE SELECT * FROM read_parquet({_literal(path)})').fetchall()]
                require('session' not in columns, f'Table {name} carries session; tables are item x item')
        finally:
            con.close()

    def keys(self, keys):
        """The keys with mapped sessions (same row order)."""
        return keys.assign(session=self.forward.reindex(keys['session'].to_numpy()).to_numpy())

    def back(self, frame):
        """A result of mapped sessions with the real ones."""
        real = self.backward.reindex(frame['session'].to_numpy()).to_numpy()
        require(not _pd().isna(real).any(), 'A result names a session outside the permuted sess')
        order = ['session'] + [c for c in ('aid', 'item') if c in frame.columns][:1]
        return (frame.assign(session=real.astype('int64')).sort_values(order, kind='mergesort')
                .reset_index(drop=True))

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def _run_on(data, keys, kind, level, sql, tables, timeout):
    """One sandbox run on the given keys; returns the result frame."""
    with tempfile.TemporaryDirectory(prefix='otto-agent-batch-') as scratch:
        path = _stage_keys(keys, Path(scratch).resolve()/'keys.parquet')
        con = sandbox(data.spec, path, tables=tables, threads=PROBE_THREADS['other'])
        try:
            return execute(con, kind, level, sql, data.spec['start'], data.spec['end'], timeout, known=data.known)[0]
        finally:
            close(con)


def _halves(data):
    cohort = list(data.cohort)
    half = (len(cohort)+1)//INVARIANCE_PARTS
    return [part for part in (cohort[:half], cohort[half:]) if part]


def _source_invariance(data, state, sql, tables, full):
    """The cohort in two halves on the real session ids against the scored pass (permuted ids, mapped back)."""
    differ = 0
    for number, part in enumerate(_halves(data), 1):
        mask = state.keys['session'].isin(set(part)).to_numpy()
        try:
            got = _run_on(data, state.keys[mask], 'source', 'pair', sql, tables, PROBE_TIMEOUTS['source'])
        except ProposalError as exc:
            return f'batch invariance: the run on half {number} failed ({exc})'
        got = got.rename(columns={'item': 'aid'})
        differ += source_mismatches(full[full['session'].isin(set(part))], got)
    if differ:
        return (f'batch invariance: rows or scores of the first {len(data.cohort)} probe sessions differ between '
                'the scored pass on permuted session ids and its two halves on the real ones')
    return None


def _feature_invariance(data, state, level, sql, tables, values, names):
    if level == 'item':
        return None                              # an item query never reads cand or sessions (check_sql)
    differ = 0
    for number, part in enumerate(_halves(data), 1):
        mask = state.keys['session'].isin(set(part)).to_numpy()
        keys = state.keys[mask]                            # real ids; the scored pass ran on permuted ones
        try:
            got = _run_on(data, keys, 'feature', level, sql, tables, PROBE_TIMEOUTS[level])
        except ProposalError as exc:
            return f'batch invariance: the run on half {number} failed ({exc})'
        got_names, matrix = align(got, level, keys['session'].to_numpy(), keys['aid'].to_numpy())
        if got_names != names:
            return 'batch invariance: value columns differ between batches'
        differ += _mismatches(values[mask], as_float32(matrix))
    if differ:
        return (f'batch invariance: values of the first {len(data.cohort)} probe sessions differ between '
                'the scored pass on permuted session ids and its two halves on the real ones')
    return None


def _evaluate_table(data, state, proposal, record, depends):
    name = proposal['name']
    if name in state.tables:
        raise ProposalError(f'a table named {name} is already accepted')
    entry = compute_table(data.spec, proposal, {n: state.tables[n] for n in depends},
                          timeout_s=probe_timeout('table', 'item_pair', data.t_tb), threads=PROBE_THREADS['table'],
                          fingerprint=data.fingerprint)
    record.update(status='valid', seconds=log2_bucket(entry['seconds']), rows=log2_bucket(entry['rows']),
                  columns=[dict(name=c) for c in entry['columns']])
    return record, dict(kind='table', seconds=float(entry['seconds']), entry=entry)


def _evaluate_source(data, state, proposal, record, depends, scorer):
    """A source on the B keys: limits, coverage (new pairs outside B and the accepted sources in at least
    MIN_SOURCE_SESSIONS probe sessions), its rank and
    score columns as the model sees them on BA = B plus the accepted sources plus this one (distinct, coverage,
    |Spearman| with every B column and every accepted source column), no repeat of an accepted source,
    batch invariance; then recall and gain."""
    np = _np()
    name = proposal['name']
    if len(state.sources) >= MAX_SOURCES:
        raise ProposalError(f'{MAX_SOURCES} sources are already accepted; no further source enters the candidates')
    if name in [n for n, _ in state.sources]:
        raise ProposalError(f'a source named {name} is already accepted')
    tables = state.table_paths(depends)
    permuted, keys_path = state.permuted_run(tables)        # the scored pass sees permuted session ids
    con = sandbox(permuted.spec, keys_path, tables=tables, threads=PROBE_THREADS['other'])
    try:
        result, _, rows, seconds = execute(con, 'source', 'pair', proposal['sql'], data.spec['start'], data.spec['end'],
                                           PROBE_TIMEOUTS['source'], known=data.known)
    finally:
        close(con)
    frame = permuted.back(result.rename(columns={'item': 'aid'}))     # real ids before coverage and the Scorer
    record.update(seconds=log2_bucket(seconds), rows=log2_bucket(rows))
    rank_name, score_name = source_columns(name)
    pool = len(data.pool)
    current = state.union()
    union = state.union((name, frame))
    known = frame.merge(current[['session', 'aid']], on=['session', 'aid'], how='left', indicator=True)
    new_share = float((known['_merge'] == 'left_only').mean()) if len(frame) else 0.0
    # coverage counts sessions where the source brings a pair into BA that B and the accepted sources lack
    entered = union[union[rank_name].notna()].merge(current[['session', 'aid']], on=['session', 'aid'], how='left',
                                                    indicator=True)
    covered = int(entered.loc[entered['_merge'] == 'left_only', 'session'].nunique())
    record['coverage'] = dict(candidates_per_session=log2_bucket(rows/pool if pool else 0),
                              new_item_share=log2_bucket(new_share),
                              sessions_covered=log2_bucket(covered/pool if pool else 0))
    problems = []
    if covered < MIN_SOURCE_SESSIONS:
        problems.append(f'the source brings new candidates to fewer than {MIN_SOURCE_SESSIONS} probe sessions')
    base_values = state.base_on(union[['session', 'aid']])
    reference = [(other, base_values[:, i]) for i, other in enumerate(data.base_names)]
    reference += [(c, as_float32(union[c].to_numpy(dtype=np.float64, na_value=np.nan))) for c in union.columns
                  if c.startswith(SOURCE_PREFIX) and c not in (rank_name, score_name)]
    record['columns'] = []
    for column in (rank_name, score_name):
        summary, issues = column_summary(column, as_float32(union[column].to_numpy(dtype=np.float64, na_value=np.nan)),
                                         reference)
        record['columns'].append(summary)
        problems += issues
    for other, earlier in state.sources:
        same_rows = len(earlier) == len(frame) and source_mismatches(earlier.assign(score=0.0), frame.assign(score=0.0)) == 0
        if same_rows:
            merged = earlier.merge(frame, on=['session', 'aid'], suffixes=('_a', '_b'))
            rho = _spearman(merged['score_a'].to_numpy(dtype=np.float64), merged['score_b'].to_numpy(dtype=np.float64))
            if (merged['rank_a'] == merged['rank_b']).all() or (rho is not None and abs(rho) >= RHO_LIMIT):
                problems.append(f'the same candidates in the same order as source {other}')
    problem = _source_invariance(data, state, proposal['sql'], tables, frame)
    if problem:
        problems.append(problem)
    if problems:
        record['error'] = _clip('; '.join(problems))
        return record, None
    before, after = scorer.recall(current), scorer.recall(union)
    record['recall'] = {k: _recall_text(v) for k, v in scorer.recall(frame).items()}
    record['gain'] = {k: _gain_text(after[k]-before[k]) for k in after}
    record['status'] = 'valid'
    return record, dict(kind='source', seconds=float(seconds), values=frame)


def _evaluate_feature(data, state, proposal, record, depends, scorer):
    level = proposal['level']
    tables = state.table_paths(depends)
    permuted, keys_path = state.permuted_run(tables)        # the scored pass sees permuted session ids
    con = sandbox(permuted.spec, keys_path, tables=tables, threads=PROBE_THREADS['other'])
    try:
        result, names, rows, seconds = execute(con, 'feature', level, proposal['sql'], data.spec['start'],
                                               data.spec['end'], PROBE_TIMEOUTS[level], known=data.known)
    finally:
        close(con)
    if level != 'item':
        result = permuted.back(result)                     # real ids before the checks and the Scorer
    record.update(seconds=log2_bucket(seconds), rows=log2_bucket(rows))
    taken = set(data.base_names) | set(state.values)
    problem = column_problem(names, taken)
    if problem:
        raise ProposalError(problem)
    sessions, aids = state.keys['session'].to_numpy(), state.keys['aid'].to_numpy()
    values = as_float32(align(result, level, sessions, aids)[1])          # validity on what the model sees
    problems = []
    for j, name in enumerate(names):
        reference = state.reference() + [(other, values[:, k]) for k, other in enumerate(names) if k != j]
        summary, issues = column_summary(name, values[:, j], reference)
        record['columns'].append(summary)
        problems += issues
    problem = _feature_invariance(data, state, level, proposal['sql'], tables, values, names)
    if problem:
        problems.append(problem)
    if problems:
        record['error'] = _clip('; '.join(problems))
        return record, None
    for j, summary in enumerate(record['columns']):
        summary['recall'] = {k: _recall_text(v) for k, v in scorer.ranked(sessions, aids, values[:, j]).items()}
    record['status'] = 'valid'
    return record, dict(kind='feature', seconds=float(seconds), values=result, names=names, matrix=values)


def evaluate_proposal(data, state, proposal, scorer):
    """The record of one proposal on the probe and its payload when valid (§5.1-§5.5).

    Every number in the record is coarse (log2 buckets, recall 0.01, gain 0.001); the exact
    probe seconds ride on the payload for the budget only.
    """
    record = _record(proposal)
    try:
        kind, level, sql = _fields(proposal)
        if kind not in PHASE_KINDS[state.phase]:
            raise ProposalError(f'phase {state.phase} accepts only {" and ".join(PHASE_KINDS[state.phase])} '
                                f'proposals, not {kind}')
        depends = check_sql(sql, kind, level, tables=list(state.tables))
        record['depends'] = depends
        if kind == 'table':
            return _evaluate_table(data, state, proposal, record, depends)
        if kind == 'source':
            return _evaluate_source(data, state, proposal, record, depends, scorer)
        return _evaluate_feature(data, state, proposal, record, depends, scorer)
    except ProposalError as exc:
        record['error'] = _clip(exc)
        return record, None


def accept(state, record, payload):
    """A valid proposal joins the run state (after the budget check of the loop)."""
    kind = record['kind']
    if kind == 'table':
        state.tables[record['name']] = payload['entry']
    elif kind == 'source':
        state.sources.append((record['name'], payload['values']))
    else:
        for j, name in enumerate(payload['names']):
            state.values[name] = payload['matrix'][:, j]


# =============================================================================== prompt (§5.6)

# N_t of the smoke run (§12, step 3, before the agent loop): oc.N_T or the halved fallback; the prompt
# carries the one the prereg will record (otto_model.prereg_rules reads the same smoke.json)
SMOKE_FORMAT = 'otto-smoke-v1'
SMOKE_N_T = (oc.N_T, oc.N_T//2)


def smoke_n_t(path=None):
    """(N_t, record of the smoke.json it comes from): the given file or the only smoke/*/smoke.json."""
    if path is None:
        root = oc.output_dir('smoke')
        found = sorted(root.glob('*/smoke.json')) if root.exists() else []
        require(len(found) == 1, f'Name the smoke result (--smoke): {len(found)} found; the smoke run precedes the agent')
        path = found[0]
    path = Path(path).resolve()
    data = oc.read_json(path)
    require(isinstance(data, dict) and data.get('format') == SMOKE_FORMAT, f'{path} is not a smoke result')
    n_t = data.get('N_t')
    require(type(n_t) is int and n_t in SMOKE_N_T, f'Smoke N_t {n_t!r} is not one of {SMOKE_N_T}')
    return n_t, dict(path=_relative(path), sha256=oc.sha256_file(path), N_t=n_t)


# Every number of the prompt that is not in stats.json, otto-base.json or the feedback (§5.6);
# T_tb joins from the calibration (prompt_constants). The ranker recipe is oc.RECIPE (§6).
PROMPT_CONSTANTS = dict(
    weights={oc.NEUTRAL_EVENTS[code]: oc.WEIGHTS[t] for code, t in enumerate(od.TYPE_NAMES)}, top_k=oc.TOP_K,
    rounds=ROUNDS, proposals=PROPOSALS, s_rounds=S_ROUNDS, f_first_round=S_ROUNDS+1,
    max_sources=MAX_SOURCES, source_rows=SOURCE_ROWS, ba_max=BA_MAX, table_rows_per_item=TABLE_ROWS_PER_ITEM,
    table_max_rows=TABLE_MAX_ROWS, max_values=MAX_VALUES, max_rows=MAX_ROWS, name_chars=24, value_chars=38,
    negatives=oc.NEGATIVES, loss=oc.RECIPE['loss_function'], trees=oc.RECIPE['iterations'], depth=oc.RECIPE['depth'],
    learning_rate=oc.RECIPE['learning_rate'], l2=oc.RECIPE['l2_leaf_reg'], borders=oc.RECIPE['border_count'],
    history_days={f'F{k}': oc.history_days(k) for k in (2, 3, 4, oc.KAGGLE_WEEK)},
    probe_history_days=oc.history_days(PROBE_FOLD),
    train_shorter_days=oc.WEEK_DAYS, day_seconds=oc.DAY, min_source_sessions=MIN_SOURCE_SESSIONS,
    timeout_source=int(PROBE_TIMEOUTS['source']), timeout_pair=int(PROBE_TIMEOUTS['pair']),
    timeout_session=int(PROBE_TIMEOUTS['session']), timeout_item=int(PROBE_TIMEOUTS['item']),
    budget_pair_session=int(PROBE_BUDGETS['pair_session_seconds']), budget_item=int(PROBE_BUDGETS['item_seconds']),
    table_budget_factor=TABLE_BUDGET_FACTOR, min_distinct=MIN_DISTINCT, min_non_null=MIN_NON_NULL,
    rho_limit=RHO_LIMIT, invariance_sessions=INVARIANCE_SESSIONS, invariance_half=INVARIANCE_SESSIONS//2,
    pool=oc.PROBE_POOL, recall_step=0.01, gain_step=0.001, example_days=7,
)

PROMPT_TEMPLATE = """You are a feature engineer for a ranking model. Reply with JSON only.

TASK
Sessions of an online shop. An event is (session, item, ts, event) with event in {{view, cart, order}}; ts is in
seconds. Each session of the target week is cut at a point that does not depend on its events: the prefix is
known, the rest is hidden. For every session and every event type t the model ranks candidate items, and the
first {top_k} count. Labels: view - the first viewed item after the cut; cart - items put into the cart after the
cut; order - items ordered after the cut. R_t = sum over sessions of |top {top_k} with labels of type t| divided by
the sum over sessions of min({top_k}, |labels of type t|). Score = {weight_view}*R_view + {weight_cart}*R_cart +
{weight_order}*R_order. The feedback below carries a coarse recall on a validation sample (described there).

CANDIDATES OF THE BASE B (always kept)
{candidates}

FEATURES ALREADY IN THE MODEL: base B (name: formula; missing). The history H is every event before the start
{{S}} of the target week; prefixes are the known parts of the target-week sessions.
{features}

TRAINING
CatBoost {loss}, {trees} trees, depth {depth}, learning rate {learning_rate}, L2 {l2}, {borders} borders; one model
per event type; the first {n_t} sessions with a label of the type, all positives and up to {negatives} negatives per
session; no tuning. History depth before the target week: {history_days_text} days for the four weeks in order; the
validation sample below lies in the second of them (history depth {probe_history_days} days). The training week of
each run is {train_shorter_days} days shorter than the week it is evaluated on, and a window longer than the
available history is silently truncated there.

TABLES (DuckDB; a query sees only these)
{tables}

THREE KINDS OF PROPOSALS (field "kind")
- "table" (level "item_pair"): an item x item helper table computed once on the whole history, for example items
  that go together. Keys item, item2 (BIGINT); 1 to {max_values} value columns named ^tv_[a-z][a-z0-9_]{{1,{value_chars}}}$;
  at most {table_rows_per_item} rows per item and {table_max_rows} rows in total. The field "name" must match
  ^[a-z][a-z0-9_]{{1,{name_chars}}}$; an accepted table is visible to later proposals of this run as tb_<name>
  (read only). A table never enters the model itself; it reads hist only (not sess, cand or sessions).
- "source" (level "pair"): a candidate source. Keys session, item (BIGINT) for sessions of the batch, items that
  occur in hist or sess; exactly one value column score; at most {source_rows} rows per session; on the validation
  sample it must add candidates that the base does not have to at least {min_source_sessions} sessions. The harness ranks
  the rows by score descending, then item, and adds ag_src_<name>_rank and ag_src_<name>_score to the model.
- "feature" (level "pair", "session" or "item"): value columns for the model. Level pair: keys session, item of
  cand; level session: session of sessions; level item: item. 1 to {max_values} value columns named
  ^ag_[a-z][a-z0-9_]{{1,{value_chars}}}$, not starting with ag_src_, unique among accepted columns.
- A proposal may read only tb_* tables accepted earlier in this run.

PHASES
- Rounds 1 to {s_rounds} (phase S): only table and source. After round {s_rounds} the candidates freeze: the base
  candidates of each session always stay, then up to {ba_max} per session are filled with items of the valid
  sources (at most the first {max_sources} valid sources) that are not base candidates, by the smallest rank over
  the sources, then the earliest accepted source, then item.
- Rounds {f_first_round} to {rounds} (phase F): only table and feature, on the frozen candidates.
- There is no selection by effect: every valid source and column enters the model.

QUERY RULES
- Exactly one SELECT or WITH statement; ';' only at the very end; no comments (-- or /* */).
- Times only through {{S}} (start of the target week) and {{E}} (its end), literally with the braces, for example
  ts >= {{S}} - {example_days}*{day_seconds}. No other {{...}} placeholders, no date literals, no integer literal of nine or
  more digits.
- ts always stands on the left of a comparison and is never compared with a plain number; write ages as {{S}} - ts.
- Forbidden whole words, in any case: label*, suffix*, frame, target, targets; read_*, parquet_*, csv, json*,
  glob, getenv, getvariable, query, query_table, duckdb_*, information_schema, pg_*, sqlite_master, pragma*,
  summarize, describe, show; attach, detach, copy, export, import, install, load, set, reset, use, call, create,
  drop, insert, update, delete, alter; random, setseed, uuid, now, today, current_date, current_time,
  current_timestamp, sample, tablesample, current_setting, checkpoint; hash*, sha*, md5*, crc*; the functions
  error(), strptime() and regexp_*(). No "$" anywhere. No string literal may hold a path or a file name.
- session is never compared with a number and never taken modulo: no rule may single out sessions by their id.
- Keys are BIGINT, never NULL, unique; a key outside its set is an error. Values must be integer, DECIMAL, FLOAT,
  DOUBLE or BOOLEAN; they are cast to DOUBLE, NULL or non-finite means missing. Every output column is named in
  the SQL.
- Batch invariance: a value depends only on hist, sess, tb_* and its own key; cand and sessions only filter.
  PARTITION BY session over cand is allowed (all candidates of a session are always in one batch). Windows need a
  full tie-break.

VALIDATION SAMPLE (probe)
{pool} sessions of a validation week. Timeouts per proposal: table {table_timeout} s; source {timeout_source} s;
feature pair {timeout_pair} s, session {timeout_session} s, item {timeout_item} s. Budget of the run: tables
{table_budget} s, sources and pair or session features {budget_pair_session} s, item features {budget_item} s; a
proposal that does not fit into what is left gets status budget.
Validity: a proposal is accepted or rejected as a whole. It is invalid on an SQL error, a broken rule or a timeout;
when a column has fewer than {min_distinct} distinct non-NULL values or fewer than {min_non_null} non-NULL rows (a
source: rows and scores); when a column has |Spearman rho| >= {rho_limit} with a base column, an accepted column or
another column of the same proposal; or when the first {invariance_sessions} probe sessions give other values in two
batches of {invariance_half}.
Feedback: buckets 2^k-2^(k+1) of time, rows and coverage; for a source the recall of its candidates per event type
(step {recall_step}) and the gain of the candidate ceiling (step {gain_step}); for a feature column R_t@{top_k} when the
candidates are ranked by that column alone (better direction), next to the best single base column.

STATISTICS OF THE VALIDATION WEEK AND ITS HISTORY (no hidden events)
{stats}

WARNING
""" + WARNING + """

EARLIER ATTEMPTS IN THIS RUN
{history}
Budget left (rounded down to 10 s): tables about {left_table} s; sources and pair or session features about
{left_pair_session} s; item features about {left_item} s.

REQUEST
This is round {round} of {rounds} (phase {phase}: {phase_kinds} only). Propose {proposals} new proposals that are likely
to improve the score beyond base B and the accepted ones and that differ from earlier attempts. Answer with a JSON
list only:
[{{"name": "short_snake_case", "idea": "one sentence", "kind": "{phase_kind_choice}", "level": "...", "sql": "SELECT ..."}}]
"""


def prompt_constants(t_tb, n_t):
    """PROMPT_CONSTANTS with the calibrated table timeout and budget and N_t of the smoke run (§12)."""
    require(type(n_t) is int and n_t in SMOKE_N_T, f'N_t must be one of {SMOKE_N_T}')
    return dict(PROMPT_CONSTANTS, table_timeout=int(t_tb), table_budget=int(TABLE_BUDGET_FACTOR*t_tb), n_t=n_t)


def prompt_identity():
    return dict(template_sha256=_sha(PROMPT_TEMPLATE), constants_digest=oc.canonical_digest(PROMPT_CONSTANTS),
                digest=oc.canonical_digest(dict(template=PROMPT_TEMPLATE, constants=PROMPT_CONSTANTS)))


def _number(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _tree(value, depth=0):
    pad = '  '*depth
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f'{pad}{key}:')
                lines.extend(_tree(item, depth+1))
            else:
                lines.append(f'{pad}{key}: {_number(item)}')
    elif isinstance(value, list):
        for item in value:
            lines.extend(_tree(item, depth+1) if isinstance(item, (dict, list)) else [f'{pad}- {_number(item)}'])
    else:
        lines.append(pad+_number(value))
    return lines


def _candidates_text(base):
    history_depth, pop_depth, limit = _policy(base)
    return '\n'.join([
        f'- (h) history: the distinct items of the prefix by their last occurrence, latest first, then item; the first '
        f'{history_depth}.',
        f'- (p_t) popular of type t in view, cart, order: the {pop_depth} items with the most distinct prefixes of the '
        'target week that hold an event of type t with them; ties to the smaller item; one list per week.',
        f'- Union: (h), then p_view, p_cart, p_order without repeats, at most {limit} per session.'])


def _features_text(base):
    return '\n'.join(f"- {neutral(f['name'])}: {neutral(f['formula'])}; missing: {neutral(f['missing'])}"
                     for f in base['features'])


def _tables_text():
    cols = 'session BIGINT, item BIGINT, ts BIGINT, event VARCHAR, seq INTEGER'
    return '\n'.join([
        f'hist({cols}): the history H, every event before {{S}}; seq is the index of the event in its session',
        f'sess({cols}): the prefixes of every session of the target week (all sessions, not only the batch)',
        'cand(session BIGINT, item BIGINT): the candidate pairs of the current batch, keys only',
        'sessions(session BIGINT): the sessions of the current batch',
        'tb_<name>(item BIGINT, item2 BIGINT, tv_* DOUBLE): tables accepted earlier in this run'])


def prompt_substitutions(stats, base, history, round_index, left, t_tb, n_t):
    require(isinstance(stats, dict) and stats, 'stats.json must be a non-empty object')
    require(type(round_index) is int and 1 <= round_index <= ROUNDS, 'Bad round index')
    constants = prompt_constants(t_tb, n_t)
    phase = phase_of(round_index)
    subs = {key: _number(value) for key, value in constants.items() if not isinstance(value, dict)}
    subs.update({f'weight_{k}': f'{v:.2f}' for k, v in constants['weights'].items()})
    subs.update(history_days_text=', '.join(_number(v) for v in constants['history_days'].values()),
                candidates=_candidates_text(base), features=_features_text(base), tables=_tables_text(),
                stats='\n'.join(_tree(stats)), history=history.strip() if history and history.strip() else '(none yet)',
                round=str(round_index), phase=phase, phase_kinds=' and '.join(PHASE_KINDS[phase]),
                phase_kind_choice='|'.join(PHASE_KINDS[phase]),
                left_table=str(_tens(left['table_seconds'])), left_pair_session=str(_tens(left['pair_session_seconds'])),
                left_item=str(_tens(left['item_seconds'])))
    return subs


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
    """Numbers (xfer NUMBER regex) of the substitutions found in none of stats.json, otto-base.json,
    the prompt constants and the feedback formatter output: [(slot, token)]."""
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
    for part in ([feedback] if isinstance(feedback, str) else feedback):
        add_text(str(part))
    problems = []
    for slot, value in substitutions.items():
        text = value if isinstance(value, str) else json.dumps(_plain(value), ensure_ascii=False)
        for token in NUMBER.findall(text):
            if token not in tokens and float(token) not in values:
                problems.append((str(slot), token))
    return problems


def render_prompt(stats, base, history_text, round_index, left, t_tb, n_t):
    """PROMPT_TEMPLATE after the number test of the substitutions and the name test of the whole prompt."""
    substitutions = prompt_substitutions(stats, base, history_text, round_index, left, t_tb, n_t)
    budget = [str(_tens(left[k])) for k in ('table_seconds', 'pair_session_seconds', 'item_seconds')]
    feedback = [history_text or '', f'round {round_index} of {ROUNDS}', *budget]
    problems = prompt_number_problems(substitutions, stats, base, prompt_constants(t_tb, n_t), feedback)
    if problems:
        shown = ', '.join(f'{slot}:{token}' for slot, token in problems[:10])
        raise ValueError(f'Prompt substitutions carry numbers outside stats, base, constants and feedback: {shown}')
    prompt = PROMPT_TEMPLATE.format(**substitutions)
    if WARNING not in ' '.join(prompt.split()):
        raise ValueError('The prompt lacks the contract warning verbatim')
    hit = NAMES_IN_PROMPT.search(prompt)
    if hit:
        raise ValueError(f'The prompt names {hit.group(0)!r}')
    return prompt


# =============================================================================== feedback (§5.5)

def _text(value, lines=False):
    if value is None:
        return ''
    text = redact(value)
    if lines:
        return '\n'.join(line.rstrip() for line in text.strip().splitlines())
    return ' '.join(text.split())


def _bucket(value):
    return value if _is_bucket(value) else 'n/a'


def _coarse(value, digits):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 'n/a'
    return f'{round(float(value), digits):.{digits}f}'


def _per_type(values):
    return ', '.join(f'{k} {v}' for k, v in (values or {}).items())


def _attempt_lines(record):
    facts = [f'{_bucket(record[key])} {unit}' for key, unit in (('seconds', 's'), ('rows', 'rows'))
             if record.get(key) is not None]
    lines = [f"{_text(record.get('id'))} {_text(record.get('name'))} [{_text(record.get('kind'))}/"
             f"{_text(record.get('level'))}]: {record.get('status')}" + (f" ({', '.join(facts)})" if facts else '')]
    lines.append(f"  idea: {_text(record.get('idea'))}")
    if record.get('status') != 'valid' and record.get('error'):
        lines.append(f"  reason: {_text(record['error'])}")
    coverage = record.get('coverage')
    if coverage:
        lines.append(f"  candidates per session {_bucket(coverage.get('candidates_per_session'))}, share of new items "
                     f"{_bucket(coverage.get('new_item_share'))}, share of sessions covered "
                     f"{_bucket(coverage.get('sessions_covered'))}")
    valid = record.get('status') == 'valid'           # label-derived numbers only for a valid proposal
    if valid and record.get('recall'):
        lines.append(f"  recall of its candidates: {_per_type(record['recall'])}")
    if valid and record.get('gain'):
        lines.append(f"  gain of the candidate ceiling: {_per_type(record['gain'])}")
    forms = dict(share=lambda v: _coarse(v, 2), bucket=_bucket, rho=lambda v: _coarse(v, 1), name=_text)
    for column in record.get('columns') or []:
        parts = [f'{label} {forms[form](column[key])}' for key, label, form in COLUMN_STATS if key in column]
        if valid and column.get('recall'):
            parts.append(f"R@{oc.TOP_K} {_per_type(column['recall'])}")
        lines.append(f"  {_text(column.get('name'))}" + (f": {', '.join(parts)}" if parts else ''))
    lines.append('  sql: ' + _text(record.get('sql'), lines=True).replace('\n', '\n    '))
    return lines


def format_feedback(history, state=None, best_b=None):
    """The ``history`` substitution: accepted tables, sources and columns, the best single base column
    (phase F) and every earlier attempt with validity, coarse coverage and coarse recall (§5.5)."""
    if not history:
        return ''
    valid = [r for r in history if r.get('status') == 'valid']
    tables = [r['name'] for r in valid if r.get('kind') == 'table']
    sources = [r['name'] for r in valid if r.get('kind') == 'source']
    columns = [c['name'] for r in valid if r.get('kind') != 'table' for c in r.get('columns') or []]
    lines = ['Accepted tables (tb_<name>): ' + (', '.join(tables) or '(none)'),
             'Accepted sources: ' + (', '.join(sources) or '(none)'),
             'Agent columns accepted earlier in this run, also in the model: ' + (', '.join(columns) or '(none)')]
    if state is not None and state.candidates is not None:
        lines.append(f"The candidates are frozen with the sources {', '.join(state.candidates['sources']) or '(none)'}.")
    if best_b:
        lines.append(f'Best single base column, R@{oc.TOP_K} on the current candidates: ' +
                     ', '.join(f'{k} {name} {_recall_text(v)}' for k, (name, v) in best_b.items()))
    for record in history:
        lines.extend(_attempt_lines(record))
    return mask_names('\n'.join(lines))


# =============================================================================== run (§5.2)

def _run_name(path):
    if not RUN_NAME.fullmatch(Path(path).name):
        raise ValueError(f'A run directory is named run-<id> ([A-Za-z0-9._-]); got {Path(path).name!r}')


def runs():
    """Every run directory: {path: run.json record}; an unreadable one counts as failed without an error type."""
    root = oc.output_dir('run')
    found = {}
    if not root.exists():
        return found
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not RUN_NAME.fullmatch(path.name):
            continue
        try:
            record = oc.read_json(path/'run.json')
        except (OSError, ValueError):
            record = None
        if not isinstance(record, dict) or record.get('format') != RUN_FORMAT:
            record = dict(status='failed', error=None, retry_of=None, unreadable=True)
        found[path.resolve()] = record
    return found


def run_family(output, probe_sha256, retry_of=None, reason=None):
    """One run (H&M, xfer): a new run only when there is none, or as the declared retry of a failed one."""
    output = Path(output).resolve()
    _run_name(output)
    if (retry_of is None) != (reason is None):
        raise ValueError('--retry-of and --reason go together')
    others = {path: record for path, record in runs().items() if path != output}
    if retry_of is None:
        if others:
            raise ValueError(f'A run exists ({min(others).name}); a new run is only a declared retry of a failed one')
        return None
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('A retry needs a non-empty --reason')
    previous = Path(retry_of).resolve()
    if previous not in others:
        raise ValueError('--retry-of must name an existing run')
    record = others[previous]
    if record.get('status') != 'failed':
        raise ValueError(f'{previous.name} is not failed; only a failed run is retried')
    kind = (record.get('error') or {}).get('type')
    if not isinstance(kind, str):
        raise ValueError(f'{previous.name} records no error type; only a technical failure is retried')
    if kind == OPERATOR_ABORT:
        raise ValueError(f'{previous.name} was stopped by the operator; an abort is not retried')
    if (record.get('probe') or {}).get('probe_sha256') != probe_sha256:
        raise ValueError(f'A retry runs on the probe of {previous.name}')
    for path, other in sorted(others.items()):
        if other.get('status') == 'completed':
            raise ValueError(f'{path.name} completed; no further run is made')
        if other.get('retry_of') == str(previous):
            raise ValueError(f'{previous.name} was already retried by {path.name}')
    if sum(1 for other in others.values() if other.get('retry_of') is not None) >= MAX_RETRIES:
        raise ValueError(f'{MAX_RETRIES} retries were already made')
    return str(previous)


class _RunLock:
    def __init__(self):
        root = oc.output_dir('run')
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


def _append(path, record):
    with Path(path).open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n')


def settle(record, proposal, payload):
    """The loop's JSON-safe copy of one evaluation record."""
    if not isinstance(record, dict) or record.get('status') not in STATUSES:
        raise RuntimeError('evaluate returned no record with status valid, invalid or budget')
    record = _plain(record)
    record.update({key: proposal[key] for key in ('id', 'round', 'index', *FIELDS)})
    record['error'] = None if record.get('error') is None else _clip(record['error'])
    if record['status'] == 'valid':
        seconds = (payload or {}).get('seconds')
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) \
                or seconds < 0:
            raise RuntimeError('A valid record needs finite non-negative probe seconds')
        if not _is_bucket(record.get('seconds')):
            raise RuntimeError('A valid record needs its probe seconds as a log2 bucket')
    return record


LABEL_FIELDS = ('recall', 'gain')


def without_labels(record):
    """A record without the label-derived numbers (recall, gain, R@20): only a valid proposal shows them."""
    record = {k: v for k, v in record.items() if k not in LABEL_FIELDS}
    record['columns'] = [{k: v for k, v in c.items() if k != 'recall'} for c in record.get('columns') or []]
    return record


def _budget_key_of(item):
    try:
        kind, level, _ = _fields(item)
    except ProposalError:
        return None
    return budget_key(kind, level)


def budget_record(proposal, key):
    """Status budget of a proposal that was not run: its budget key has no probe time left."""
    record = _record(proposal)
    record.update(status='budget', error=f'no probe budget left: {key} is used up; the proposal was not run')
    return record


def _save_payload(out, record, payload):
    if record['kind'] == 'table':
        entry = payload['entry']
        return dict(kind='table', path=_relative(entry['path']), key=entry['key'], sha256=entry['sha256'],
                    rows=entry['rows'], columns=entry['columns'])
    path = out/'values'/f"{record['id']}.parquet"
    oc.write_parquet(payload['values'].reset_index(drop=True), path)
    return dict(kind=record['kind'], rows=int(len(payload['values'])), sha256=oc.sha256_file(path))


def run_loop(probe, name=None, rounds=ROUNDS, proposals=PROPOSALS, model=MODEL, max_calls=MAX_CALLS, ask=None,
             evaluate=None, retry_of=None, reason=None, smoke=None):
    """6 rounds x 5 proposals on the probe with phases S and F (§5.2); returns the run.json record.

    N_t of the prompt comes from the smoke result (``smoke`` or the only one). A proposal whose
    budget key has no time left is not run (status budget); a valid proposal that does not fit
    into what is left becomes budget and keeps no recall. The journal goes to docs/otto-run/<run>/
    when the run ends, completed or failed.
    """
    for label, value in (('rounds', rounds), ('proposals', proposals), ('max_calls', max_calls)):
        if type(value) is not int or value < 1:
            raise ValueError(f'{label} must be a positive integer')
    if max_calls > MAX_CALLS or rounds > ROUNDS or proposals > PROPOSALS:
        raise ValueError(f'At most {ROUNDS} rounds, {PROPOSALS} proposals and {MAX_CALLS} calls')
    if model != MODEL:
        raise ValueError(f'The model is {MODEL}')
    ask = ask_proposals if ask is None else ask
    evaluate = evaluate_proposal if evaluate is None else evaluate
    output = oc.output_dir('run', _output_name(name, f'run-{_stamp()}'))
    _run_name(output)
    identity = probe_identity(probe)
    run_family(output, identity['probe_sha256'], retry_of, reason)
    data = ProbeData(probe)
    base = oc.read_base()
    require(base['digest'] == data.record['base_digest'], 'otto-base.json changed since the probe')
    limits = budget_limits(data.t_tb)
    n_t, smoke_record = smoke_n_t(smoke)
    render_prompt(data.stats, base, '', 1, limits, data.t_tb, n_t)      # refuses before any output or call
    code = oc.code_identity(strict=False)
    used = dict.fromkeys(limits, 0.0)
    with _RunLock():
        retried = run_family(output, identity['probe_sha256'], retry_of, reason)
        out = oc.new_output(output)
        (out/'values').mkdir()
        log = out/'log.jsonl'
        log.touch()
        report = dict(format=RUN_FORMAT, status='running', id=out.name.removeprefix('run-'), model=model,
                      retry_of=retried, reason=None if retried is None else reason.strip(), llm_command=None,
                      rounds=rounds, proposals_per_round=proposals, max_calls=max_calls, probe=identity,
                      base_digest=base['digest'], prompt=prompt_identity(), t_tb=data.t_tb, n_t=n_t, smoke=smoke_record,
                      budget=dict(limits=limits, used=dict(used)), calls=0, cost_usd=0.0, cost_unknown_calls=0,
                      rounds_run=0, stop=None, attempts=0, valid=0, phase='S', candidates=None, tables={},
                      sources=[], columns=[], call_log=[], prompts={}, values={}, probe_seconds={}, code=code,
                      started_at_utc=oc.utc_now())
        oc.atomic_json(out/'run.json', report)
    scorer = state = None
    try:
        scorer = Scorer(probe_labels(data.collection))
        state = RunState(data, out, base)
        history = []
        for number in range(1, rounds+1):
            if report['calls'] >= max_calls:
                report['stop'] = 'max_calls'
                break
            left = {key: limits[key]-used[key] for key in limits}
            best = state.best_b(scorer) if state.phase == 'F' else None
            prompt = render_prompt(data.stats, base, format_feedback(history, state, best), number, left, data.t_tb,
                                   n_t)
            (out/f'prompt-r{number}.txt').write_text(prompt, encoding='utf-8', newline='\n')
            report['prompts'][f'r{number}'] = _sha(prompt)
            report['rounds_run'] = number
            attempts, items = [], None
            for attempt in (1, 2):                 # the second call only after a failed or unparsable one
                if report['calls'] >= max_calls:
                    break
                report['calls'] += 1
                call, meta = dict(round=number, attempt=attempt), None
                try:
                    reply, meta = ask(prompt, model)
                    items = parse_proposals(json.dumps(reply))
                    call['status'] = 'ok'
                except Exception as exc:  # noqa: BLE001 - recorded, then retried once
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
                oc.atomic_json(out/'run.json', report, exist_ok=True)
                if items is not None:
                    break
            kept = (items or [])[:proposals]
            oc.atomic_json(out/f'reply-r{number}.json', dict(round=number, llm_command=report['llm_command'],
                                                             attempts=attempts, kept=len(kept)))
            if items is None:
                report.update(stop=RETRIES_EXHAUSTED, failed_round=number)
                raise RuntimeError(f'Round {number}: the call failed or was unparsable and no retry is left'
                                   if len(attempts) < 2 else
                                   f'Round {number}: the call and its retry both failed or were unparsable')
            for index, item in enumerate(kept, 1):
                proposal = dict(id=f'r{number}p{index}', round=number, index=index, **item)
                loadavg = list(os.getloadavg())
                key = _budget_key_of(item)
                if key is not None and limits[key]-used[key] <= 0:
                    record, payload = budget_record(proposal, key), None
                else:
                    record, payload = evaluate(data, state, dict(proposal), scorer)
                record = settle(record, proposal, payload)
                record['loadavg'] = loadavg
                if record['status'] == 'valid':
                    key, seconds = budget_key(record['kind'], record['level']), float(payload['seconds'])
                    if used[key]+seconds > limits[key]:
                        record = without_labels(record)
                        record.update(status='budget', error=f'over the probe budget: {key} has too little time left')
                    else:
                        used[key] += seconds
                        report['probe_seconds'][record['id']] = round(seconds, 3)
                        report['values'][record['id']] = _save_payload(out, record, payload)
                        accept(state, record, payload)
                        if record['kind'] == 'table':
                            report['tables'][record['name']] = report['values'][record['id']]
                        elif record['kind'] == 'source':
                            report['sources'].append(record['name'])
                _append(log, record)
                history.append(record)
                valid = [r for r in history if r['status'] == 'valid']
                report.update(attempts=len(history), valid=len(valid),
                              columns=[c['name'] for r in valid if r['kind'] != 'table' for c in r['columns']],
                              budget=dict(limits=limits, used=dict(used)))
                oc.atomic_json(out/'run.json', report, exist_ok=True)
            if number == S_ROUNDS and state.phase == 'S':
                report.update(candidates=state.freeze_candidates(), phase='F')
                oc.atomic_json(out/'run.json', report, exist_ok=True)
        if state.phase == 'S':
            report.update(candidates=state.freeze_candidates(), phase='F')
        report.update(status='completed', stop=report['stop'] or 'rounds', log_sha256=oc.sha256_file(log),
                      finished_at_utc=oc.utc_now())
        oc.atomic_json(out/'run.json', report, exist_ok=True)
        journal = _copy_journal(out)
        return dict(report, path=str(out), journal=str(journal))
    except BaseException as exc:
        report.update(status='failed', finished_at_utc=oc.utc_now(),
                      error=dict(type=type(exc).__name__,
                                 message=clean_error(f'{type(exc).__name__}: {exc}', limit=2048),
                                 traceback=clean_error(traceback.format_exc(limit=12), limit=8192)))
        oc.atomic_json(out/'run.json', report, exist_ok=True)
        try:
            _copy_journal(out)
        except Exception:  # noqa: BLE001 - the run's own error is the one to raise
            pass
        raise
    finally:
        if scorer is not None:
            scorer.close()
        if state is not None:
            state.close()


# =============================================================================== the set (freeze, §5.2, §5.8)

SET_FIELDS = ('format', 'run', 'probe', 'run_sha256', 'base_digest', 'prompt', 'prompt_digest', 't_tb', 'code',
              'candidates', 'proposals', 'attempts', 'columns', 'tables', 'budget', 'digest', 'audit')


def set_digest(proposals):
    return oc.canonical_digest([[p['id'], p['kind'], p['level'], p['name'], p['sql'], list(p['columns']),
                                 list(p['depends'])] for p in proposals])


def proposal_columns(kind, name, names):
    """Columns a proposal gives: tv_* of a table, ag_src_<name>_rank/_score of a source, ag_* of a feature."""
    return source_columns(name) if kind == 'source' else list(names)


def check_set(record, base=None):
    """An OTTO set: schema, SQL rules with the tables accepted earlier, phases, names, order and digest."""
    require(isinstance(record, dict) and record.get('format') == SET_FORMAT, f'An agent set of {SET_FORMAT} is required')
    missing = [key for key in SET_FIELDS if key not in record]
    require(not missing, f'The agent set lacks {", ".join(missing)}')
    require(isinstance(record['proposals'], list) and record['proposals'], 'The agent set has no proposals')
    if base is not None:
        require(record['base_digest'] == base['digest'], 'The agent set was made on another base')
        reserved = set(oc.base_feature_names(base))
    else:
        reserved = set()
    tables, sources, columns, last = [], [], [], (0, 0)
    for proposal in record['proposals']:
        pid = proposal.get('id') if isinstance(proposal, dict) else None
        require(isinstance(pid, str), 'Every proposal needs a string id')
        try:
            kind, level, sql = _fields(proposal)
            depends = check_sql(sql, kind, level, tables=tables)
        except ProposalError as exc:
            raise ProposalError(f'{pid}: {exc}') from None
        number, index = proposal.get('round'), proposal.get('index')
        require(type(number) is int and type(index) is int and min(number, index) >= 1 and pid == f'r{number}p{index}',
                f'{pid}: the id must be r<round>p<index>')
        require((number, index) > last, f'{pid}: proposals must follow increasing (round, index)')
        last = (number, index)
        require(kind in PHASE_KINDS[phase_of(number)], f'{pid}: a {kind} in phase {phase_of(number)}')
        require(proposal.get('depends') == depends, f'{pid}: depends must list the tb_* it reads in order')
        names = proposal.get('columns')
        require(isinstance(names, list) and all(isinstance(n, str) for n in names), f'{pid}: columns must be names')
        if kind == 'table':
            require(proposal['name'] not in tables, f'{pid}: table name repeats')
            require(1 <= len(names) <= MAX_VALUES and len(set(names)) == len(names)
                    and all(TABLE_VALUE.fullmatch(n) for n in names), f'{pid}: table columns break the contract')
            tables.append(proposal['name'])
            continue
        if kind == 'source':
            require(proposal['name'] not in sources, f'{pid}: source name repeats')
            require(names == source_columns(proposal['name']), f'{pid}: source columns are ag_src_<name>_rank, _score')
            sources.append(proposal['name'])
            require(len(sources) <= MAX_SOURCES, f'More than {MAX_SOURCES} sources')
        else:
            problem = column_problem(names, set(columns) | reserved)
            require(problem is None, f'{pid}: {problem}')
        require(not set(names) & (set(columns) | reserved), f'{pid}: columns repeat')
        columns.extend(names)
    require(record['columns'] == columns, 'The set columns must list the model columns in proposal order')
    require(record['tables'] == tables, 'The set tables must list the table names in order')
    require(isinstance(record['candidates'], dict) and record['candidates'].get('sources') == sources,
            'The frozen candidates must name the set sources in order')
    require(record['digest'] == set_digest(record['proposals']), 'The agent set differs from its digest')
    require(isinstance(record['prompt'], dict) and record['prompt_digest'] == record['prompt'].get('digest'),
            'prompt_digest differs from the prompt identity')
    check_audit(record['audit'], record)
    return record


# =============================================================================== the SQL audit (§5.8)

AUDIT_FORMAT = 'otto-audit-v1'
AUDIT_VERDICTS = ('clean', 'leak')
AUDIT_LABELS = ('common', 'schema-specific')
# what the independent read-only auditor answers, each in its own words (§5.5, §5.8, §0)
AUDIT_POINTS = {
    'hidden_encoding': 'can a proposal encode facts about single sessions or labels in the coarse feedback fields',
    'addressed_oracle': 'does a proposal single out sessions or items (literal ids, narrow filters, tiny coverage) '
                        'so that its recall or gain reports on a few labels',
    'recognizability': 'per proposal, from memory without search: a common recommender technique or specific to '
                       'this schema (descriptive only)',
}
AUDIT_FIELDS = ('path', 'sha256', 'set_digest', 'verdict', 'recognizability', 'points')


def check_audit(audit, record):
    """None (not audited yet) or the audit record of the set: verdict, a label per proposal, every point."""
    if audit is None:
        return None
    require(isinstance(audit, dict) and sorted(audit) == sorted(AUDIT_FIELDS),
            f'The set audit has exactly {", ".join(AUDIT_FIELDS)}')
    require(audit['set_digest'] == record['digest'], 'The audit was made on another set')
    require(audit['verdict'] in AUDIT_VERDICTS, f'Audit verdict must be one of {AUDIT_VERDICTS}')
    ids = [p['id'] for p in record['proposals']]
    labels = audit['recognizability']
    require(isinstance(labels, dict) and sorted(labels) == sorted(ids) and all(v in AUDIT_LABELS for v in labels.values()),
            f'Audit recognizability labels every proposal with one of {AUDIT_LABELS}')
    require(audit['points'] == sorted(AUDIT_POINTS), 'The audit answers every audit point')
    require(isinstance(audit['sha256'], str) and len(audit['sha256']) == 64, 'Audit sha256 missing')
    return audit


def audit(report):
    """Record the SQL audit in the uncommitted set: ``report`` is the auditor's JSON in docs/otto-run/.

    The report carries format otto-audit-v1, the set digest, a verdict (clean or leak), a
    recognizability label per proposal and an answer per AUDIT_POINTS. The set digest does
    not cover the audit; the prereg records the set file with it. Sidecars need verdict clean.
    """
    path = Path(report).resolve()
    require(path.is_relative_to(journal_dir().resolve()) and path.is_file(), 'The audit report lives in docs/otto-run/')
    data = oc.read_json(path)
    require(isinstance(data, dict) and data.get('format') == AUDIT_FORMAT, f'An audit report of {AUDIT_FORMAT} is required')
    points = data.get('points')
    require(isinstance(points, dict) and sorted(points) == sorted(AUDIT_POINTS)
            and all(isinstance(v, str) and v.strip() for v in points.values()),
            f'The audit answers {", ".join(AUDIT_POINTS)} in words')
    output = oc.config_path('set')
    require(not oc.committed_clean(output), 'The set is committed; the audit goes before its commit')
    base = oc.read_base()
    record = read_set(base=base)
    require(record['audit'] is None, 'The set already carries an audit')
    value = dict(record, audit=dict(path=_relative(path), sha256=oc.sha256_file(path), set_digest=data.get('set_digest'),
                                    verdict=data.get('verdict'), recognizability=data.get('recognizability'),
                                    points=sorted(points)))
    check_set(value, base)
    oc.atomic_json(output, value, exist_ok=True)
    return dict(value, path=str(output))


def read_set(path=None, base=None):
    return check_set(oc.read_json(oc.config_path('set') if path is None else path), base)


def _copy_journal(run_dir):
    """Prompts, replies, log.jsonl and run.json of the run under docs/otto-run/<run>/ (same content or refuse)."""
    target = journal_dir()/run_dir.name
    target.mkdir(parents=True, exist_ok=True)
    files = sorted([*run_dir.glob('prompt-r*.txt'), *run_dir.glob('reply-r*.json'), run_dir/'log.jsonl',
                    run_dir/'run.json'])
    for path in files:
        dest = target/path.name
        if dest.exists():
            require(dest.read_bytes() == path.read_bytes(), f'{dest} exists with other content')
        else:
            shutil.copyfile(path, dest)
    return target


def freeze(run_dir):
    """configs/datasets/otto-set.json from the completed run: every valid proposal in (round, index) order."""
    run_dir = Path(run_dir).resolve()
    _run_name(run_dir)
    require(run_dir.parent == oc.output_dir('run').resolve(), f'Only a run under {oc.output_dir("run")} is frozen')
    run = oc.read_json(run_dir/'run.json')
    require(isinstance(run, dict) and run.get('format') == RUN_FORMAT and run.get('status') == 'completed',
            'Only a completed run is frozen')
    completed = {p for p, r in runs().items() if r.get('status') == 'completed'} | {run_dir}
    require(len(completed) == 1, 'More than one completed run; the one-run rule leaves nothing to choose')
    log = run_dir/'log.jsonl'
    require(oc.sha256_file(log) == run.get('log_sha256'), 'log.jsonl differs from the one the run completed with')
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()]
    order = [(r['round'], r['index']) for r in records]
    require(len(records) == run.get('attempts') and order == sorted(order) and len(set(order)) == len(order),
            'log.jsonl records are not unique and in (round, index) order')
    base = oc.read_base()
    require(base['digest'] == run['base_digest'], 'otto-base.json changed since the run')
    candidates = run.get('candidates')
    require(isinstance(candidates, dict) and oc.sha256_file(run_dir/'candidates.parquet') == candidates['sha256'],
            'The frozen candidates of the run changed')
    limits, exact = run['budget']['limits'], run.get('probe_seconds') or {}
    used = dict.fromkeys(limits, 0.0)
    proposals = []
    for record in records:
        require(record.get('status') in STATUSES, f"{record['id']}: unknown status")
        if record['status'] != 'valid':
            continue
        seconds = exact.get(record['id'])
        require(isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds)
                and seconds >= 0, f"{record['id']}: run.json holds no exact probe seconds for it")
        used[budget_key(record['kind'], record['level'])] += seconds
        names = proposal_columns(record['kind'], record['name'], [c['name'] for c in record['columns']])
        proposal = dict(id=record['id'], round=record['round'], index=record['index'], name=record['name'],
                        idea=record['idea'], kind=record['kind'], level=record['level'], sql=record['sql'],
                        columns=names, depends=list(record.get('depends') or []), probe_seconds=record['seconds'])
        if record['kind'] == 'table':
            proposal['probe_table'] = {k: run['values'][record['id']][k] for k in ('key', 'rows', 'sha256')}
        proposals.append(proposal)
    require(proposals, 'The run has no valid proposal; there is nothing to freeze')
    require(set(exact) == {p['id'] for p in proposals}, 'run.json probe_seconds and the valid proposals differ')
    for key, limit in limits.items():
        require(used[key] <= limit, f'Valid proposals exceed the probe budget {key}')
    probe = run['probe']
    value = dict(format=SET_FORMAT,
                 run=dict(id=run['id'], model=run['model'], rounds=run['rounds_run'],
                          proposals_per_round=run['proposals_per_round'], calls=run['calls'],
                          cost_usd=run['cost_usd'], log_sha256=run['log_sha256']),
                 probe=probe, run_sha256=oc.sha256_file(run_dir/'run.json'), base_digest=run['base_digest'],
                 prompt=run['prompt'], prompt_digest=run['prompt']['digest'], t_tb=run['t_tb'], code=run['code'],
                 candidates=candidates, proposals=proposals,
                 attempts=[dict(id=r['id'], status=r['status'], error=r.get('error')) for r in records],
                 columns=[n for p in proposals if p['kind'] != 'table' for n in p['columns']],
                 tables=[p['name'] for p in proposals if p['kind'] == 'table'],
                 budget={key: _tens(used[key]) for key in limits}, digest=set_digest(proposals), audit=None)
    check_set(value, base)
    output = oc.config_path('set')
    if output.exists():
        existing = oc.read_json(output)                # the audit is added later; the rest must be the same
        require(isinstance(existing, dict) and dict(existing, audit=None) == value,
                f'{output.name} exists with other content; not overwritten')
        value = existing
    else:
        oc.atomic_json(output, value)
    journal = _copy_journal(run_dir)
    return dict(value, path=str(output), journal=str(journal))


# =============================================================================== sidecars (§5.7)

def sidecar_gate():
    """Sidecars after the committed prereg; the committed set must carry its audit (§5.7, §5.8)."""
    oc.require_prereg(check_code=True)
    agent_set = read_set(base=oc.read_base())
    require(agent_set['audit'] is not None, 'The set has no audit record; sidecars follow the audit')
    require(agent_set['audit']['verdict'] == 'clean', 'The audit found a leak; no sidecar is built')
    return agent_set


def view_purpose(fold):
    return 'final' if int(fold) == oc.KAGGLE_WEEK else 'sidecar'


def table_timeout_on(fold, t_tb, factor=1):
    """max(3600, 1.5·T_tb·Σn²(I_k)/Σn²(I_3)) s with the load's upper bounds (§5.7), times the retry factor."""
    facts = od.read_load()['facts']['sum_n2_upper']
    ratio = float(facts[f'F{int(fold)}'])/float(facts[f'F{PROBE_FOLD}'])
    return max(TABLE_TIMEOUT_MIN, TABLE_TIMEOUT_FACTOR*float(t_tb)*ratio)*factor


def retry_factor(deviation, collection_name):
    """1, or 2 under a recorded deviation of step ``sidecar`` naming this collection (§5.7).

    The doubled limits are the table timeout and the 4 h per proposal; the 900 s per batch is
    fixed (a batch timeout is fixed by a smaller batch). The deviation is used once: a sidecar
    or a failure record that already carries it refuses (§5.7: the timeout is raised once).
    """
    if deviation is None:
        return 1
    records = [r for r in oc.deviations() if r.get('id') == deviation]
    require(records, f'Deviation {deviation!r} is not recorded')
    record = records[-1]
    require(record.get('step') == SIDECAR_STEP, f'Deviation {deviation!r} is not of step {SIDECAR_STEP!r}')
    require(record.get('collection') == collection_name, f'Deviation {deviation!r} names another collection')
    return RETRY_FACTOR


def _deviation_users(deviation, collection_name, name):
    """Completed sidecars and failure records that carry the deviation, every collection; the failures of
    this very sidecar (same collection and name: its resume continues the same attempt) do not count."""
    root = oc.output_dir('sidecars')
    if deviation is None or not root.exists():
        return []
    found = [p for p in root.glob(f'*/*/{SIDECAR_REPORT}') if oc.read_json(p).get('deviation') == deviation]
    for path in root.glob('.failed-*.json'):
        data = oc.read_json(path)
        if data.get('deviation') == deviation and (data.get('collection'), data.get('name')) != (collection_name, name):
            found.append(path)
    return sorted(found)


class _FileLock:
    """An exclusive lock file (O_EXCL); a second holder refuses."""

    def __init__(self, path, what):
        self.path, self.what = Path(path), what
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ContractError(f'Another {self.what} holds {self.path}{self._holder()}') from None
        try:
            os.write(fd, f'{os.getpid()}\n'.encode())
        finally:
            os.close(fd)
        return self

    def _holder(self):
        """The pid written in the lock and whether it still runs (a dead one leaves a stale lock)."""
        try:
            pid = int(self.path.read_text(encoding='utf-8').split()[0])
        except (OSError, ValueError, IndexError):
            return ' (no pid in it)'
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return f' (pid {pid} is dead; remove the lock if no other run holds it)'
        except PermissionError:
            pass
        return f' (pid {pid})'

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


def _frame_sessions(frame_path):
    con = _helper_con()
    try:
        return [int(s) for (s,) in con.execute(
            f'SELECT DISTINCT session FROM read_parquet({_literal(frame_path)}) ORDER BY 1').fetchall()]
    finally:
        con.close()


def frame_rows(frame_path, sessions):
    """Rows of frame.parquet for the sessions, ordered by session, aid."""
    pd = _pd()
    con = _helper_con()
    try:
        con.register('wanted', pd.DataFrame({'session': sorted(int(s) for s in sessions)}, dtype='int64'))
        return con.execute(f'''SELECT f.* FROM read_parquet({_literal(frame_path)}) f SEMI JOIN wanted w
            ON w.session = f.session ORDER BY f.session, f.aid''').fetch_df()
    finally:
        con.close()


class FrameBatches:
    """frame.parquet split once into batches of ``batch`` sessions in the given order (one scan of the frame);
    ``rows(b)`` reads batch b ordered by session, aid. ``close`` removes the split."""

    def __init__(self, frame_path, ordered, batch, threads, memory):
        pd = _pd()
        np = _np()
        self.batch = int(batch)
        self.count = -(-len(ordered)//self.batch)
        self.dir = _spill_dir()
        con = od.connect(threads, memory, temp=self.dir/'spill', max_temp=MAX_TEMP)
        try:
            con.register('batch_map', pd.DataFrame({'session': np.asarray(ordered, dtype=np.int64),
                                                    'b': np.arange(len(ordered), dtype=np.int64)//self.batch}))
            con.execute(f'''COPY (SELECT f.*, m.b FROM read_parquet({_literal(frame_path)}) f
                JOIN batch_map m ON m.session = f.session)
                TO {_literal(self.dir/'parts')} (FORMAT parquet, PARTITION_BY (b))''')
        except BaseException:
            con.close()
            self.close()
            raise
        con.close()

    def rows(self, b):
        directory = self.dir/'parts'/f'b={int(b)}'
        files = sorted(str(p) for p in directory.glob('*.parquet'))
        require(files, f'Batch {b} has no frame rows')
        con = _helper_con()
        try:
            return con.execute(f'SELECT * FROM read_parquet({_list_literal(files)}, hive_partitioning=false) '
                               'ORDER BY session, aid').fetch_df()
        finally:
            con.close()

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def sidecar_records(collection, set_digest):
    """Completed sidecars of the collection after ``oc.sidecar_parts`` (the reader of otto_model): their
    sidecar.json records and the sessions they hold. A stale sidecar (another set or manifest) refuses."""
    collection = Path(collection)
    found = oc.sidecar_parts(collection, set_digest)
    if found is None:
        return [], set()
    records = [oc.read_json(oc.sidecar_dir(collection.name, entry['name'])/SIDECAR_REPORT)
               for entry in found['sidecars']]
    return records, set(found['sessions'])


def _final_training_expected():
    """prereg_sha256 and n_t the final-training record must carry: the prereg in force and its N_t."""
    path = oc.config_path('prereg')
    prereg = oc.read_json(path)
    return dict(prereg_sha256=oc.sha256_file(path), n_t=int(prereg.get('N_t', oc.N_T)))


def sidecar_sessions(collection, manifest, final_training=None):
    """Sessions of a collection that need the BA frame (§5.7) and the final-training record they come from.

    train, val, kaggle: every frame session. holdout: the population (power gate) or, with
    ``final_training`` ('auto' = the single final-training record of the collection, or the path
    of a sessions.json of otto_model final-sessions), the training sessions of final.
    """
    collection = Path(collection)
    role = manifest['role']
    require(role != 'probe', 'The probe gets no sidecar')
    if role != 'holdout':
        require(final_training is None, '--final-training belongs to the holdout collection')
        return _frame_sessions(collection/oc.FRAME_FILE), None
    if final_training is None:
        return oc.holdout_population(collection)['sessions'], None
    if final_training == 'auto':
        path, record = oc.final_training_record(collection.name, **_final_training_expected())
    else:
        path = Path(final_training)
        record = oc.read_final_training(path, collection=collection.name, **_final_training_expected())
    values = [int(v) for v in record['sessions']]
    require(values, 'The final training sessions are empty')
    frame = set(_frame_sessions(collection/oc.FRAME_FILE))
    require(set(values) <= frame, 'Final training sessions outside the holdout frame')
    return values, dict(path=_relative(path), sha256=oc.sha256_file(path), digest=record['digest'],
                        training_digest=record['training_digest'])


_PID = re.compile(r'(r\d+p\d+): ')


def _failure(root, collection, name, identity, progress, batch_index, exc, deviation, factor):
    """sidecars/.failed-<collection>-<name>-<n>.json: the BA-not-done record of §5.7 (status, batch, proposal)."""
    hit = _PID.match(str(exc))
    record = dict(format=SIDECAR_FAILURE_FORMAT, status='failed', collection=collection.name, name=name,
                  batch=batch_index, proposal=hit.group(1) if hit else None, error_type=type(exc).__name__,
                  message=_clip(clean_error(f'{type(exc).__name__}: {exc}')),
                  parts_done=len(progress['parts']) if progress else 0,
                  proposal_seconds=dict(progress['proposal_seconds']) if progress else {},
                  set_digest=identity['set_digest'],
                  sessions_digest=identity['sessions_digest'], deviation=deviation, factor=factor,
                  created_utc=oc.utc_now())
    number = len(list(root.glob(f'.failed-{collection.name}-{name}-*.json')))+1
    path = root/f'.failed-{collection.name}-{name}-{number}.json'
    oc.atomic_json(path, record)
    return path


def _abandoned_seconds(root, collection_name, name, set_digest):
    """Seconds per proposal of the unfinished sidecars of the collection under other names (same set): the
    progress.json of every other .partial-*, and the last .failed-* record of a name whose partial is gone."""
    seconds, seen, failed = {}, set(), {}
    for path in sorted(root.glob(f'.partial-*/{SIDECAR_PROGRESS}')):
        progress = oc.read_json(path)
        if (progress.get('collection'), progress.get('set_digest')) != (collection_name, set_digest):
            continue
        seen.add(progress.get('name'))
        if progress.get('name') != name:
            for pid, sec in (progress.get('proposal_seconds') or {}).items():
                seconds[pid] = seconds.get(pid, 0.0)+float(sec)
    for path in sorted(root.glob('.failed-*.json')):
        record = oc.read_json(path)
        other = record.get('name')
        if ((record.get('collection'), record.get('set_digest')) != (collection_name, set_digest) or other == name
                or other in seen):
            continue
        if other not in failed or record.get('parts_done', 0) >= failed[other].get('parts_done', 0):
            failed[other] = record
    for record in failed.values():
        for pid, sec in (record.get('proposal_seconds') or {}).items():
            seconds[pid] = seconds.get(pid, 0.0)+float(sec)
    return seconds


def sidecar(collection, name=None, threads=SIDECAR_THREADS, memory=None, batch=oc.SIDECAR_BATCH,
            final_training=None, deviation=None, agent_set=None):
    """The BA frame of a collection: sidecars/<collection>/<name>/part-*.parquet and sidecar.json.

    Columns: session, aid, every B column of frame.parquet (frame types, recomputed by the
    twin and checked against the frame on the B rows), then the set columns as FLOAT.
    Sessions already in another sidecar of the collection are left out; the rows of a part
    are ordered by session, aid; parts follow the sha256 order of their sessions.

    Progress is kept in sidecars/.partial-<collection>-<name>/ (progress.json after every
    batch): a failure writes sidecars/.failed-<collection>-<name>-<n>.json and keeps the
    parts; the same command again resumes after the last part. The 4 h per proposal counts
    every sidecar of the collection (one fold), the abandoned ones under other names included.
    One sidecar per collection at a time.
    """
    started = time.monotonic()
    memory = MEMORY if memory is None else memory
    agent_set = sidecar_gate() if agent_set is None else check_set(agent_set)
    base = oc.read_base()
    require(agent_set['base_digest'] == base['digest'], 'The set was made on another base')
    collection = Path(collection).resolve()
    manifest = oc.read_collection(collection, base=base)
    role = manifest['role']
    require(collection == Path(oc.collection_dir(role)).resolve(), f'{collection} is not the {role} collection in force')
    manifest_sha = oc.sha256_file(collection/oc.MANIFEST_FILE)
    fold = int(manifest['fold'])
    factor = retry_factor(deviation, collection.name)
    require(type(batch) is int and batch >= 1, 'batch >= 1')
    name = _output_name(name, f'sidecar-{_stamp()}')
    final = oc.sidecar_dir(collection.name, name)
    require(not final.exists(), f'{final} exists; every output is new')
    root = oc.output_dir('sidecars')
    with _FileLock(root/f'.lock-{collection.name}', f'sidecar of {collection.name}'):
        partial = root/f'.partial-{collection.name}-{name}'
        users = _deviation_users(deviation, collection.name, name)
        if users:
            raise ContractError(f'Deviation {deviation!r} was already used ({users[0].name}); the limit is raised once')
        records, done = sidecar_records(collection, agent_set['digest'])
        wanted, training = sidecar_sessions(collection, manifest, final_training)
        sessions = [s for s in wanted if s not in done]
        require(sessions, 'Every requested session already has a sidecar')
        ordered = oc.first_in_order(sessions, None)
        identity = dict(collection=collection.name, name=name, manifest_sha256=manifest_sha,
                        set_digest=agent_set['digest'], sessions=len(ordered),
                        sessions_digest=oc.sessions_digest(ordered), batch=batch,
                        tables=dict(threads=TABLE_THREADS, memory=TABLE_MEMORY))
        if partial.exists():
            progress = oc.read_json(partial/SIDECAR_PROGRESS)
            require({k: progress.get(k) for k in identity} == identity,
                    f'{partial.name} belongs to another sidecar (set, sessions or batch differ); choose another name')
            for part, info in progress['parts'].items():
                require(oc.sha256_file(partial/part) == info['sha256'], f'{partial.name}: part changed: {part}')
            progress['resumed'] = progress.get('resumed', 0)+1
        else:
            oc.new_output(partial)
            progress = dict(identity, parts={}, proposal_seconds={}, resumed=0)
        before = _abandoned_seconds(root, collection.name, name, agent_set['digest'])
        for record in records:
            for pid, sec in (record.get('proposal_seconds') or {}).items():
                before[pid] = before.get(pid, 0.0)+float(sec)
        clock = _Clock(PROPOSAL_CAP*factor)
        for source in (before, progress['proposal_seconds']):
            for pid, sec in source.items():
                clock.load(pid, float(sec))
        spec = fold_spec(fold, view_purpose(fold), None if fold == oc.KAGGLE_WEEK else collection)
        table_timeout = table_timeout_on(fold, agent_set['t_tb'], factor)
        twin = batches = None
        index = mark = None                        # mark: clock.spent before the batch not yet in progress
        try:
            tables = set_tables(spec, agent_set, timeout_s=table_timeout, threads=threads, memory=memory)
            known = known_items(spec)
            columns = frame_columns(collection/oc.FRAME_FILE)
            names = [c['name'] for c in columns]
            twin = BaseFeatures(spec, base, columns, threads=threads, memory=memory)
            batches = FrameBatches(collection/oc.FRAME_FILE, ordered, batch, threads, memory)
            for index in range(batches.count):
                part_name = f'part-{index:05d}.parquet'
                if part_name in progress['parts']:
                    continue
                b_rows = batches.rows(index)
                mark = dict(clock.spent)
                block, used = agent_block(spec, b_rows[['session', 'aid']], agent_set, tables, threads=threads,
                                          memory=memory, batch_timeout=BATCH_TIMEOUT, clock=clock, known=known)
                computed = twin.frame(block[['session', 'aid']])
                check_b_twin(computed, b_rows, names)
                path = twin.write_part(block, agent_set['columns'], partial/part_name)
                progress['parts'][part_name] = dict(sha256=oc.sha256_file(path), rows=int(len(block)),
                                                    sessions=int(block['session'].nunique()))
                for pid, sec in used.items():
                    progress['proposal_seconds'][pid] = round(progress['proposal_seconds'].get(pid, 0.0)+sec, 3)
                mark = None
                oc.atomic_json(partial/SIDECAR_PROGRESS, progress, exist_ok=True)
            index = None
            parts = progress['parts']
            report = dict(format=SIDECAR_FORMAT, collection=collection.name, role=role, fold=fold,
                          manifest_sha256=manifest_sha, set_digest=agent_set['digest'], sessions=len(ordered),
                          sessions_digest=identity['sessions_digest'], table_build=identity['tables'], rows=sum(p['rows'] for p in parts.values()),
                          parts=parts, columns=['session', 'aid', *names, *agent_set['columns']],
                          agent_columns=agent_set['columns'], batch=batch,
                          final_training=training,
                          t_tb=agent_set['t_tb'], table_timeout=round(table_timeout, 1), batch_timeout=BATCH_TIMEOUT,
                          proposal_cap=PROPOSAL_CAP*factor,
                          tables={n: dict(key=e['key'], cached=e['cached'], seconds=e['seconds'])
                                  for n, e in tables.items()},
                          proposal_seconds=progress['proposal_seconds'], seconds_before=before,
                          resumed=progress['resumed'], deviation=deviation, factor=factor, threads=threads,
                          memory=memory, code=oc.code_identity(strict=False),
                          seconds=round(time.monotonic()-started, 1), created_utc=oc.utc_now())
            (partial/SIDECAR_PROGRESS).unlink(missing_ok=True)
            oc.atomic_json(partial/SIDECAR_REPORT, report)
            final.parent.mkdir(parents=True, exist_ok=True)
            os.rename(partial, final)
            try:                                   # the reader of otto_model must accept it as written
                found = oc.sidecar_parts(collection, agent_set['digest'])
                require(found is not None and set(ordered) <= set(found['sessions']),
                        'oc.sidecar_parts does not see the sessions of the new sidecar')
            except BaseException:
                os.rename(final, partial)
                raise
        except BaseException as exc:
            if mark is not None:                   # seconds of the failed batch (a timeout included) count
                for pid, sec in clock.spent.items():
                    if sec > mark.get(pid, 0.0):
                        progress['proposal_seconds'][pid] = round(
                            progress['proposal_seconds'].get(pid, 0.0)+sec-mark.get(pid, 0.0), 3)
            if partial.exists():                   # resumable: progress.json back, no report
                (partial/SIDECAR_REPORT).unlink(missing_ok=True)
                oc.atomic_json(partial/SIDECAR_PROGRESS, progress, exist_ok=True)
            _failure(root, collection, name, identity, progress, index, exc, deviation, factor)
            raise
        finally:
            if twin is not None:
                twin.close()
            if batches is not None:
                batches.close()
    return dict(report, path=str(final))


# =============================================================================== leakcheck (§5.8)

def _blocks(spec, collection, agent_set, tables, sessions, *, batch, threads, memory, known):
    """The agent block of ``sessions`` in sha256-ordered batches of ``batch``; one frame by session, aid."""
    pd = _pd()
    frames = []
    for index in range(0, len(sessions), batch):
        part = sessions[index:index+batch]
        b_rows = frame_rows(Path(collection)/oc.FRAME_FILE, part)
        frames.append(agent_block(spec, b_rows[['session', 'aid']], agent_set, tables, threads=threads, memory=memory,
                                  known=known)[0])
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=['session', 'aid'])
    return frame.sort_values(['session', 'aid'], kind='mergesort').reset_index(drop=True)


def compare_blocks(left, right, columns):
    """Keys on one side only and per-column cell mismatches on the common keys."""
    merged = left.merge(right, on=['session', 'aid'], how='outer', suffixes=('', '__other'), indicator=True)
    keys = int((merged['_merge'] != 'both').sum())
    both = merged[merged['_merge'] == 'both']
    other = both[[f'{c}__other' for c in columns]].rename(columns=lambda c: c[:-len('__other')])
    cells = same_cells(both[columns], other, columns)
    return dict(keys_one_side=keys, cells={c: n for c, n in cells.items() if n})


def prefix_check(collection, threads=4, memory='4GB'):
    """F3 only (§5.8, sess): the prefixes of every fold session rebuilt from the W3 partitions by otto_data's
    truncation rule against <collection>/prefix/: rows, sessions and sum(hash(EVENT_COLUMNS)) each side."""
    collection = Path(collection)
    columns = ', '.join(oc.EVENT_COLUMNS)
    prefix = sorted(str(p) for p in (collection/oc.PREFIX_DIR).rglob('*.parquet'))
    require(prefix, f'{collection.name} holds no prefix partitions')
    temp = _spill_dir()
    con = od.connect(threads, memory, temp=temp, max_temp=MAX_TEMP)
    try:
        od.build_fold(con, PROBE_FOLD, 'leakcheck', od.s5())
        fingerprint = 'SELECT count(*), count(DISTINCT session), coalesce(sum(hash({c})), 0)::HUGEINT FROM ({q})'
        rebuilt = con.execute(fingerprint.format(c=columns, q=f'SELECT {columns} FROM fold WHERE pos <= c')).fetchone()
        stored = con.execute(fingerprint.format(c=columns, q=f'SELECT {columns} FROM read_parquet('
                                                f'{_list_literal(prefix)}, hive_partitioning=false)')).fetchone()
    finally:
        con.close()
        shutil.rmtree(temp, ignore_errors=True)
    rebuilt, stored = [[str(v) for v in row] for row in (rebuilt, stored)]
    return dict(rows=[rebuilt[0], stored[0]], sessions=[rebuilt[1], stored[1]], ok=rebuilt == stored)


def leakcheck(fold, name=None, agent_set=None, sessions=None, threads=SIDECAR_THREADS, memory=None,
              batch=oc.SIDECAR_BATCH, leak_sessions=LEAK_SESSIONS):
    """Every agent column with hist of H_k against hist over every partition d < -7 filtered by ts < {S},
    and 2000 sessions in one batch against 4 x 500 (§5.8). Writes leakcheck/<name>/report.json (ok, fold).

    The full variant recomputes every table outside the cache (a nondeterministic table shows up).
    On F4 (degenerate: the same partitions) both variants run on the batch cohort only. On F3 the
    prefixes of the collection are rebuilt from the W3 partitions and compared (prefix_check)."""
    fold = int(fold)
    require(fold in (3, 4), 'The leakcheck runs on F3 (dev population) and F4 (holdout population)')
    started = time.monotonic()
    memory = MEMORY if memory is None else memory
    base = oc.read_base()
    agent_set = read_set(base=base) if agent_set is None else check_set(agent_set, base)
    if fold == 4:
        oc.require_prereg(check_code=True)
        collection = oc.collection_dir('holdout')
    else:
        collection = oc.collection_dir('val')
    collection = Path(collection).resolve()
    oc.read_collection(collection, base=base)
    if sessions is not None:
        population = sorted({int(s) for s in sessions})
    elif fold == 4:                                  # the evaluation population of the power gate (decision 22)
        population = oc.holdout_population(collection)['sessions']
    else:
        population = oc.read_population(collection)
    require(population, 'No sessions to check')
    name = _output_name(name, f'leakcheck-F{fold}-{_stamp()}')
    path = oc.leakcheck_path(name)
    out = path.parent
    require(not out.exists(), f'{out} exists; every output is new')
    require(not (journal_dir()/f'{name}.json').exists(), f'{name}.json exists in the journal')
    ordered = oc.first_in_order(population, None)
    spec = fold_spec(fold, 'leakcheck', collection)
    full = full_history_spec(spec)
    timeout = table_timeout_on(fold, agent_set['t_tb'])
    columns = agent_set['columns']
    report = dict(format=LEAKCHECK_FORMAT, ok=False, fold=fold, collection=collection.name, sessions=len(ordered),
                  sessions_digest=oc.sessions_digest(ordered), set_digest=agent_set['digest'],
                  degenerate=full['degenerate'], history=dict(normal=len(spec['files']['hist']),
                                                              full=len(full['files']['hist'])),
                  columns=columns, error=None, prefix_check=None)
    fresh = _spill_dir()
    try:
        known = known_items(spec)
        tables = set_tables(spec, agent_set, timeout_s=timeout, threads=threads, memory=memory)
        # F4: the variant reads the same partitions; both run on the batch cohort only (§5.8: degenerate as in T)
        checked = ordered[:leak_sessions] if full['degenerate'] else ordered
        normal = _blocks(spec, collection, agent_set, tables, checked, batch=batch, threads=threads, memory=memory,
                         known=known)
        full_tables = set_tables(full, agent_set, timeout_s=timeout, threads=threads, memory=memory, fresh=fresh)
        other = _blocks(full, collection, agent_set, full_tables, checked, batch=batch, threads=threads,
                        memory=memory, known=known_items(full))
        report['history_check'] = dict(sessions=len(checked), **compare_blocks(normal, other, columns))
        cohort = ordered[:leak_sessions]
        size = max(1, -(-len(cohort)//LEAK_BATCHES))
        one = _blocks(spec, collection, agent_set, tables, cohort, batch=max(1, len(cohort)), threads=threads,
                      memory=memory, known=known)
        four = _blocks(spec, collection, agent_set, tables, cohort, batch=size, threads=threads, memory=memory,
                       known=known)
        report['batch_check'] = dict(sessions=len(cohort), batches=-(-len(cohort)//size),
                                     **compare_blocks(one, four, columns))
        if fold == PROBE_FOLD:
            report['prefix_check'] = prefix_check(collection, threads=threads, memory=memory)
        report['ok'] = all(not c['keys_one_side'] and not c['cells']
                           for c in (report['history_check'], report['batch_check'])) and \
            (report['prefix_check'] or dict(ok=True))['ok']
    except ProposalError as exc:
        report['error'] = _clip(exc)
    finally:
        shutil.rmtree(fresh, ignore_errors=True)
    report.update(seconds=round(time.monotonic()-started, 1), code=oc.code_identity(strict=False),
                  created_utc=oc.utc_now())
    report = _plain(report)
    oc.new_output(out)
    oc.atomic_json(path, report)
    _journal_json(f'{name}.json', report)
    return dict(report, path=str(path))


# =============================================================================== export

def export(name=None):
    """Views and partition files of F2 and F3 with SHA-256 (nothing is copied)."""
    folds = {}
    for k in (2, 3):
        spec = fold_spec(k, 'export')
        hist = sorted(p for pattern in spec['files']['hist'] for p in Path(pattern).parent.glob('*.parquet'))
        sess = sorted(Path(p) for p in spec['files']['sess'])
        folds[f'F{k}'] = dict(start=spec['start'], end=spec['end'], views=spec['views'], schema=spec['schema'],
                              views_digest=spec['digest'],
                              hist={_relative(p): oc.sha256_file(p) for p in hist},
                              sess={_relative(p): oc.sha256_file(p) for p in sess})
    out = oc.new_output(oc.output_dir('export', _output_name(name, f'export-{_stamp()}')))
    record = dict(format=EXPORT_FORMAT, folds=folds, digest=oc.canonical_digest(folds), created_utc=oc.utc_now())
    oc.atomic_json(out/'export.json', record)
    return dict(record, path=str(out))


# =============================================================================== CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(f'usage: {message}')


def _parser():
    parser = _Parser(prog='otto_agent.py', description='Agent half of the OTTO port')
    sub = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
    p = sub.add_parser('export')
    p.add_argument('--name')
    p = sub.add_parser('calibrate')
    p.add_argument('--name')
    p.add_argument('--collection', type=Path)
    p.add_argument('--threads', type=int, default=CALIBRATION_THREADS)
    p.add_argument('--memory')
    p = sub.add_parser('probe')
    p.add_argument('--name')
    p.add_argument('--collection', type=Path)
    p.add_argument('--val', type=Path)
    p.add_argument('--calibration', type=Path)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--memory', default='4GB')
    p = sub.add_parser('run')
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--name', help='run-<id>')
    p.add_argument('--max-calls', type=int, default=MAX_CALLS)
    p.add_argument('--retry-of', type=Path)
    p.add_argument('--reason')
    p.add_argument('--smoke', type=Path, help='smoke.json of otto_model (default: the only smoke/*/smoke.json)')
    p = sub.add_parser('freeze')
    p.add_argument('--run', type=Path, required=True)
    p = sub.add_parser('audit')
    p.add_argument('--report', type=Path, required=True, help='the auditor\'s JSON in docs/otto-run/')
    p = sub.add_parser('sidecar')
    p.add_argument('--collection', type=Path, required=True)
    p.add_argument('--name')
    p.add_argument('--threads', type=int, default=SIDECAR_THREADS)
    p.add_argument('--memory')
    p.add_argument('--batch', type=int, default=oc.SIDECAR_BATCH)
    p.add_argument('--final-training', nargs='?', const='auto',
                   help='holdout: the training sessions of final, from sessions.json of otto_model final-sessions '
                        '(the path, or without a value the single record of the collection)')
    p.add_argument('--deviation')
    p = sub.add_parser('leakcheck')
    p.add_argument('--fold', type=int, required=True, choices=(3, 4))
    p.add_argument('--name')
    p.add_argument('--threads', type=int, default=SIDECAR_THREADS)
    p.add_argument('--memory')
    p.add_argument('--batch', type=int, default=oc.SIDECAR_BATCH)
    return parser


def _handle(argv):
    oc.isolated()
    args = _parser().parse_args(argv)
    if args.command == 'export':
        result = export(args.name)
        return dict(command='export', path=result['path'], digest=result['digest'])
    if args.command == 'calibrate':
        result = calibrate(args.name, args.collection, args.threads, args.memory)
        return dict(command='calibrate', path=result['path'], t_20=result['t_20'], t_tb=result['t_tb'],
                    limitation=result['limitation'])
    if args.command == 'probe':
        result = prepare_probe(args.name, args.collection, args.val, args.calibration, args.threads, args.memory)
        return dict(command='probe', path=result['path'], pool=result['pool_size'], rows=result['rows'],
                    t_tb=result['calibration']['t_tb'])
    if args.command == 'run':
        result = run_loop(args.probe, args.name, max_calls=args.max_calls, retry_of=args.retry_of, reason=args.reason,
                          smoke=args.smoke)
        return dict(command='run', path=result['path'], calls=result['calls'], cost_usd=result['cost_usd'],
                    rounds=result['rounds_run'], stop=result['stop'], attempts=result['attempts'],
                    valid=result['valid'], sources=result['sources'], columns=len(result['columns']))
    if args.command == 'freeze':
        result = freeze(args.run)
        return dict(command='freeze', path=result['path'], proposals=len(result['proposals']),
                    columns=len(result['columns']), digest=result['digest'], journal=result['journal'])
    if args.command == 'audit':
        result = audit(args.report)
        return dict(command='audit', path=result['path'], verdict=result['audit']['verdict'],
                    digest=result['digest'])
    if args.command == 'sidecar':
        result = sidecar(args.collection, args.name, args.threads, args.memory, args.batch, args.final_training,
                         args.deviation)
        return dict(command='sidecar', path=result['path'], sessions=result['sessions'], rows=result['rows'],
                    columns=len(result['agent_columns']))
    result = leakcheck(args.fold, args.name, threads=args.threads, memory=args.memory, batch=args.batch)
    return dict(command='leakcheck', path=result['path'], passed=result['ok'], fold=result['fold'])


def main(argv=None):
    return oc.run_cli(_handle, argv)


if __name__ == '__main__':
    raise SystemExit(main())
