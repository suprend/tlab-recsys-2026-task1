"""Sandbox of the H&M LLM feature agent (arm MA): export, probe, proposal harness.

Contract: docs/hm-agent-design.md, sections 1, 2 and 6 (agent A). The history is
exported once from the audited DB as day partitions ``tx/d=YYYY-MM-DD`` plus the
article attributes (no customers, no free text). A proposal runs in a new
in-memory DuckDB connection that knows only ``tx`` (a view over the partitions
before the anchor A, filtered again by ``t_dat < A``), ``articles`` (bought before
A), ``cand`` and ``users`` (the batch keys). External access is off except for
those day directories, Python replacement scans are off and the configuration
is locked, so future rows, labels, the DB and caller variables are unreachable;
``check_sql`` is a second layer. Output columns follow contract 1.4: level keys,
1-3 ``ag_*`` values cast to DOUBLE, NULL for no row, NULL, NaN, +-inf and float32
overflow, then a LEFT JOIN onto the batch keys.

Run as ``python -I scripts/hm_agent_sandbox.py export|probe``; both commands read
downloaded data and refuse to run without isolation. Outputs stay inside the
ignored artifacts/ tree; stdout carries one JSON line.
"""
from __future__ import annotations

from datetime import date
import functools
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import time
import weakref

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import hm_experiment as experiment  # noqa: E402
from scripts import hm_feature_engine as engine  # noqa: E402
from scripts import hm_kaggle as kaggle  # noqa: E402

EXPORT_FORMAT = 'hm-agent-export-v1'
SET_FORMAT = 'hm-agent-set-v1'
PROBE_FORMAT = 'hm-agent-probe-v1'
LEVELS = {'pair': ('customer_id', 'article_id'), 'customer': ('customer_id',), 'article': ('article_id',)}
KEYS = ('customer_id', 'article_id')
FIELDS = ('name', 'idea', 'level', 'sql')
MODULE = 'hm_agent_sandbox.py'
AGENT_CODE = (MODULE, 'hm_agent_loop.py', 'hm_agent_kaggle.py', 'hm_result_audit.py')
TX_SCHEMA = (('t_dat', 'DATE'), ('customer_id', 'VARCHAR'), ('article_id', 'VARCHAR'), ('price', 'DOUBLE'),
             ('sales_channel_id', 'VARCHAR'))
# Codes and names of the article attributes; prod_name and detail_desc (free text) are not exported.
ARTICLE_COLUMNS = (
    'article_id', 'product_code', 'product_type_no', 'product_type_name', 'product_group_name',
    'graphical_appearance_no', 'graphical_appearance_name', 'colour_group_code', 'colour_group_name',
    'perceived_colour_value_id', 'perceived_colour_value_name', 'perceived_colour_master_id',
    'perceived_colour_master_name', 'department_no', 'department_name', 'index_code', 'index_name',
    'index_group_no', 'index_group_name', 'section_no', 'section_name', 'garment_group_no', 'garment_group_name')
# Probe statistics: (code, name) per attribute; product_code gets its cardinality only.
ATTRIBUTES = (('product_code', None), ('product_type_no', 'product_type_name'), (None, 'product_group_name'),
              ('graphical_appearance_no', 'graphical_appearance_name'), ('colour_group_code', 'colour_group_name'),
              ('perceived_colour_value_id', 'perceived_colour_value_name'),
              ('perceived_colour_master_id', 'perceived_colour_master_name'), ('department_no', 'department_name'),
              ('index_code', 'index_name'), ('index_group_no', 'index_group_name'), ('section_no', 'section_name'),
              ('garment_group_no', 'garment_group_name'))
EXPORT_FIELDS = ('format', 'status', 'before', 'database', 'sources', 'tx', 'articles', 'code', 'digest')
SET_FIELDS = ('format', 'run', 'probe', 'proposals', 'attempts', 'columns', 'budget', 'digest')
PROBE_FILES = ('keys.parquet', 'sources.parquet', 'm23.parquet', 'stats.json')
TX_FILE = re.compile(r'tx/d=([0-9]{4}-[0-9]{2}-[0-9]{2})/[^/]+\.parquet')
ARTICLES_FILE = 'articles/articles.parquet'
PROBE_TIMEOUTS = {'pair': 20.0, 'customer': 20.0, 'article': 60.0}
MAX_ROWS = 20_000_000
MAX_VALUES = 3
RUN_TIMEOUT = 900
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
WALL_SECONDS = 3600.0
SANDBOX_PREFIX = 'tlab-hm-sbx-'
MEMORY_TEXT = re.compile(r'[0-9]+(\.[0-9]+)?\s*(KB|MB|GB|TB|KiB|MiB|GiB|TiB)')
# Second layer (1.3): whole words, any case.
FORBIDDEN = re.compile(
    r'\b(transactions|customers|frame|labels?|targets?|hm_\w+|_hm_\w+|'
    r'read_\w+|parquet_\w+|csv|json\w*|glob|getenv|query|query_table|duckdb_\w+|information_schema|pg_catalog|'
    r'sqlite_master|pragma\w*|current_setting|sniff_\w+|checkpoint|force_checkpoint|which_secret|'
    r'attach|detach|copy|export|import|install|load|set|reset|use|call|create|drop|insert|update|delete|alter|'
    r'random|setseed|uuid|gen_random_uuid|now|today|current_date|current_time|current_timestamp|get_current_time|'
    r'sample|tablesample)\b', re.I)
# Functions that raise with their own argument text (duckdb_functions(): error; strptime echoes its input;
# regexp_* echo a pattern built from data). Runtime messages are withheld anyway (error_feedback).
RAISING = re.compile(r'\b(error|strptime|regexp_\w+)\s*\(', re.I)
BATCH = re.compile(r'\b(cand|users)\b', re.I)
STATEMENT = re.compile(r'(select|with)\b', re.I)
ANCHOR = re.compile(r"\b(?i:date)\s*'\{A\}'")
DATE_LITERAL = re.compile(r"'\s*[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}")
# DuckDB messages quote data (conversion errors cite the value). sanitize_error replaces quoted
# literals and absolute paths, then digit runs split by short separators, then id-shaped runs:
# customer ids are 64 hex, article ids 10 digits.
QUOTED = re.compile(r"'(?:[^']|'')*'")
PATH = re.compile(r'(?:\b[A-Za-z]:[\\/]|(?<![\w.\-])[/~])[^\s\'",;()\[\]]+')
SPLIT_DIGITS = re.compile(r'[0-9](?:[\s.,:;_\-/]{0,2}[0-9]){8,}')
# Hex groups of 1-4 characters joined by single spaces, commas or dashes (12+ hex characters in total).
SPLIT_HEX = re.compile(r'\b[0-9a-fA-F]{1,4}(?:[ ,\-][0-9a-fA-F]{1,4})+\b')
# A hex token of 8+ characters with both a digit and a letter.
HEX_TOKEN = re.compile(r'\b(?=[0-9a-fA-F]*[0-9])(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{8,}\b')
# Five or more digits; line and column numbers stay shorter.
LONG_DIGITS = re.compile(r'[0-9]{5,}')
DOUBLE_QUOTED = re.compile(r'"([^"]*)"')
DIGIT_TOKEN = re.compile(r'\S*[0-9]\S*')
EDGE = '()[]{},;:.\'"!?'
SQL_TOKEN = re.compile(r'[^\s\'"(),;\[\]{}]+')
DECIMAL_TYPE = re.compile(r'(?i:decimal|numeric)\([0-9]{1,2},\s*[0-9]{1,2}\)')
HEXLIKE = re.compile(r'[0-9a-fA-F]{12,}')
DIGITS = re.compile(r'[0-9]{9,}')


class ProposalError(ValueError):
    """A proposal breaks the SQL rules or the output contract, fails or times out."""


def _anchor(value):
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.isoformat() == value:
            return parsed
    raise ValueError('A date or YYYY-MM-DD string is required')


def _threads(value):
    if type(value) is not int or not 1 <= value <= 256:
        raise ValueError('Threads must be an integer from 1 to 256')
    return value


def _seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('A finite positive timeout is required')
    return float(value)


def _literal(text):
    return "'" + str(text).replace("'", "''") + "'"


def _native(exc):
    return type(exc).__module__.split('.')[0].lstrip('_') in kaggle.NATIVE_ERRORS


def _mask(text):
    return DIGITS.sub('<digits>', HEXLIKE.sub('<hex>', str(text)))


def sanitize_error(text, sql=''):
    """A DuckDB message safe for logs, prompts and Git.

    Single-quoted literals become '…'; double-quoted strings become "…" unless they
    are a token of ``sql`` (the agent's own column names stay readable); paths,
    split digit or hex runs, hex tokens and long digit runs are masked; then every
    remaining token with a digit becomes <v>, except ``LINE n:`` markers, DuckDB
    type names (INT32, DECIMAL(18,3)) and tokens written in ``sql``. Without
    ``sql`` every token with a digit outside those two forms is masked.
    """
    own = _sql_tokens(sql) | SCHEMA_NAMES | FIXED_TOKENS
    text = QUOTED.sub("'…'", str(text))
    text = DOUBLE_QUOTED.sub(lambda m: m.group(0) if m.group(1) in own else '"…"', text)
    text = PATH.sub('<path>', text)
    text = SPLIT_DIGITS.sub('<digits>', text)
    text = SPLIT_HEX.sub(_split_hex, text)
    text = LONG_DIGITS.sub(lambda m: m.group(0) if m.group(0) in FIXED_TOKENS else '<digits>',
                           HEX_TOKEN.sub('<hex>', text))
    text = _mask(text)
    return DIGIT_TOKEN.sub(lambda m: _digit_token(m, own), text)


SCHEMA_NAMES = frozenset((*(name for name, _ in TX_SCHEMA), *ARTICLE_COLUMNS, 'tx', 'articles', 'cand', 'users', '_x'))
# Fixed by code, not by data: the M23 names that `nearest` can report and the constants the
# validity and contract messages quote, with the probe timeouts (only probe errors reach the
# log). They stay readable in sanitized text.
FIXED_TOKENS = frozenset((*engine.PILOT_NUMERIC_FEATURES, *(str(v) for v in (
    RHO_LIMIT, MIN_DISTINCT, MIN_NON_NULL, MAX_ROWS, MAX_VALUES, INVARIANCE_USERS)),
    *(f'{v:g}' for v in PROBE_TIMEOUTS.values())))


def _sql_tokens(sql):
    if not isinstance(sql, str) or not sql:
        return frozenset()
    return frozenset(SQL_TOKEN.findall(sql))


@functools.lru_cache(maxsize=1)
def _type_names():
    import duckdb
    con = duckdb.connect(':memory:')
    try:
        return frozenset(row[0].upper() for row in con.execute('SELECT DISTINCT type_name FROM duckdb_types()').fetchall())
    finally:
        con.close()


def _digit_token(match, own):
    """Keep LINE markers, type names and pieces the agent wrote itself; anything else with a digit is <v>."""
    token = match.group(0)
    if re.fullmatch(r'[0-9]+:', token) and match.string[max(0, match.start()-5):match.start()] == 'LINE ':
        return token
    decimal = DECIMAL_TYPE.search(token)
    if decimal and not (token[:decimal.start()]+token[decimal.end():]).strip(EDGE):
        return token
    types = _type_names()
    for part in SQL_TOKEN.findall(token):
        core = part.strip(EDGE)
        if any(ch.isdigit() for ch in core) and core not in own and part not in own and core.upper() not in types:
            return '<v>'
    return token


def _split_hex(match):
    run = match.group(0)
    return '<hex>' if sum(ch not in ' ,-' for ch in run) >= 12 else run


def _clip(text):
    return str(text)[:ERROR_CHARS]


def _floats(values):
    import numpy as np
    return np.ma.filled(np.ma.asarray(values, dtype=np.float64), np.nan)


def _taken():
    return {definition.name for definition in engine.feature_registry()} | set(experiment.RESERVED)


def agent_code_identity(deadline=None):
    """The one ``code`` key set of contract 0: kaggle.code_identity() plus the agent modules and the audit.

    A missing module raises; nothing is skipped.
    """
    code = kaggle.code_identity(deadline)
    if Path(__file__).resolve() != (ROOT/'scripts'/MODULE).resolve():
        raise ImportError(f'{MODULE} was imported from outside this checkout')
    for name in AGENT_CODE:
        path = ROOT/'scripts'/name
        if not path.is_file():
            raise FileNotFoundError(f'scripts/{name} is missing; the code identity needs every agent module')
        code[name] = experiment.sha256_file(path, deadline)
    return code


def _database(database, deadline):
    source = Path(database).resolve()
    stat = source.stat()
    identity = dict(sha256=experiment.sha256_file(source, deadline), bytes=stat.st_size)
    return source, stat, identity, kaggle.database_sources(source, identity)


def _covers(manifest, cutoff):
    before = manifest['before']
    if before is not None and date.fromisoformat(before) < cutoff:
        raise ValueError(f'The export ends before {before}; history up to the anchor {cutoff.isoformat()} is missing')


# --- 1.3 SQL rules ---------------------------------------------------------------------------------------------

def check_sql(sql, level):
    """Second layer of 1.3: one SELECT/WITH, the anchor only as DATE '{A}', no forbidden word."""
    if level not in LEVELS:
        raise ProposalError('level must be pair, customer or article')
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
    rest = ANCHOR.sub(' ', body)
    if '{' in rest or '}' in rest:
        raise ProposalError("the anchor is written only as DATE '{A}'; no other {...} is allowed")
    if DATE_LITERAL.search(rest):
        raise ProposalError("date literals are not allowed; write dates relative to DATE '{A}'")
    hit = FORBIDDEN.search(rest) or RAISING.search(rest)
    if hit:
        raise ProposalError(f'forbidden table, function or command: {hit.group(0)}')
    if level == 'article':
        hit = BATCH.search(rest)
        if hit:
            raise ProposalError(f'an article query must not use {hit.group(0)}: its values are cached per process')


def _fields(proposal):
    if not isinstance(proposal, dict):
        raise ProposalError('a proposal is an object with name, idea, level and sql')
    for key in FIELDS:
        if not isinstance(proposal.get(key), str) or not proposal[key].strip():
            raise ProposalError(f'{key} must be a non-empty string')
    if proposal['level'] not in LEVELS:
        raise ProposalError('level must be pair, customer or article')
    return proposal['level'], proposal['sql']


# --- frozen set ----------------------------------------------------------------------------------------------

def set_digest(proposals):
    """Identity of the frozen set: canonical_digest([[id, level, sql, columns], ...])."""
    return experiment.canonical_digest([[p['id'], p['level'], p['sql'], list(p['columns'])] for p in proposals])


def _check_set(record):
    if not isinstance(record, dict) or record.get('format') != SET_FORMAT:
        raise ValueError(f'An agent set of format {SET_FORMAT} is required')
    missing = [key for key in SET_FIELDS if key not in record]
    if missing:
        raise ValueError(f'The agent set lacks {", ".join(missing)}')
    for key, kind in (('run', dict), ('probe', dict), ('proposals', list), ('attempts', list), ('columns', list),
                      ('budget', dict), ('digest', str)):
        if not isinstance(record[key], kind):
            raise ValueError(f'Agent set field {key} must be a {kind.__name__}')
    if not record['proposals']:
        raise ValueError('The agent set has no proposals')
    taken, seen, last = _taken(), [], (0, 0)
    for proposal in record['proposals']:
        pid = proposal.get('id') if isinstance(proposal, dict) else None
        if not isinstance(pid, str):
            raise ValueError('Every proposal needs a string id')
        try:
            level, sql = _fields(proposal)
            check_sql(sql, level)
        except ProposalError as exc:
            raise ProposalError(f'{pid}: {exc}') from None
        number, index = proposal.get('round'), proposal.get('index')
        if type(number) is not int or type(index) is not int or min(number, index) < 1 or pid != f'r{number}p{index}':
            raise ValueError(f'{pid}: the id must be r<round>p<index> with positive integer round and index')
        if (number, index) <= last:
            raise ValueError(f'{pid}: proposals must follow increasing (round, index)')
        last = (number, index)
        columns = proposal.get('columns')
        if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_VALUES:
            raise ValueError(f'{pid}: 1 to {MAX_VALUES} columns are required')
        for name in columns:
            if not isinstance(name, str) or not NAME.fullmatch(name) or name in taken or name in seen:
                raise ValueError(f'{pid}: column {name!r} breaks the naming contract or repeats')
            seen.append(name)
        seconds = proposal.get('probe_seconds')
        if not (isinstance(seconds, str) and _is_bucket(seconds)) and (
                isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds)
                or seconds < 0):
            raise ValueError(f'{pid}: probe_seconds must be a finite non-negative number or a log2 bucket')
    if record['columns'] != seen:
        raise ValueError('The set columns must list the proposal columns in order')
    if record['digest'] != set_digest(record['proposals']):
        raise ValueError('The agent set differs from its digest')
    return record


def _is_bucket(text):
    match = BUCKET.fullmatch(text)
    return bool(match) and (text == '0' or int(match.group(2)) == int(match.group(1))+1)


def read_agent_set(path):
    """hm-agent-set.json with its schema, SQL rules, column names and digest checked."""
    return _check_set(kaggle.read_json(path))


# --- 1.1 export ----------------------------------------------------------------------------------------------

def _check_tables(con):
    have = {row[0]: row[1] for row in con.execute('DESCRIBE transactions').fetchall()}
    if any(have.get(name) != kind for name, kind in TX_SCHEMA):
        raise ValueError('transactions must have ' + ', '.join(f'{n} {k}' for n, k in TX_SCHEMA))
    have = {row[0]: row[1] for row in con.execute('DESCRIBE articles').fetchall()}
    if any(have.get(name) != 'VARCHAR' for name in ARTICLE_COLUMNS):
        raise ValueError('articles must hold the exported attributes as VARCHAR')
    if con.execute('SELECT count(*) FROM transactions WHERE t_dat IS NULL').fetchone()[0]:
        raise ValueError('Every transaction needs a day')
    missing, repeated = con.execute('''SELECT count(*) FILTER (WHERE article_id IS NULL),
        count(article_id)-count(DISTINCT article_id) FROM articles''').fetchone()
    if missing or repeated:
        raise ValueError('articles need unique non-NULL article_id')


def _tx_summary(con, output, cutoff, deadline):
    files = sorted(p for p in (output/'tx').rglob('*') if p.is_file() or p.is_symlink())
    relative = [p.relative_to(output).as_posix() for p in files]
    if not files or any(p.is_symlink() or not TX_FILE.fullmatch(r) for p, r in zip(files, relative)):
        raise ValueError('The partitioned write left an unexpected layout under tx/')
    paths = [str(p) for p in files]
    written = con.execute('SELECT * FROM read_parquet(?, hive_partitioning=false) LIMIT 0', [paths]).description
    if [(d[0], str(d[1])) for d in written] != list(TX_SCHEMA):
        raise ValueError('Exported transactions must keep the five typed columns')
    counted = {row[0]: row[1:] for row in con.execute('''SELECT filename, count(*), min(t_dat), max(t_dat)
        FROM read_parquet(?, filename=true, hive_partitioning=false) GROUP BY filename''', [paths]).fetchall()}
    entries, days = {}, set()
    for path, rel in zip(paths, relative):
        day = date.fromisoformat(TX_FILE.fullmatch(rel).group(1))
        rows, low, high = counted.get(path, (0, None, None))
        if not rows or low != day or high != day or (cutoff is not None and day >= cutoff):
            raise ValueError('Every exported file must hold rows of its own day, before the cut')
        entries[rel] = dict(sha256=experiment.sha256_file(path, deadline), rows=int(rows))
        days.add(day)
    return dict(rows=sum(entry['rows'] for entry in entries.values()), days=len(days), first=min(days).isoformat(),
                last=max(days).isoformat(), files=entries)


def export_history(database, output, before=None, threads=4):
    """1.1: tx/d=YYYY-MM-DD/*.parquet, articles/articles.parquet and export.json from the audited DB.

    With ``before`` only rows with t_dat < before are written (the leakcheck cut).
    One writer thread keeps the insertion order, so the same rows give the same
    bytes and the same digest.
    """
    cutoff = None if before is None else _anchor(before)
    threads = _threads(threads)
    deadline = experiment.Deadline(WALL_SECONDS)
    code = agent_code_identity(deadline)
    source, stat, identity, sources = _database(database, deadline)
    output = kaggle.new_output(output)
    report = dict(format=EXPORT_FORMAT, status='running', before=None if cutoff is None else cutoff.isoformat())
    temp = output/'duckdb-temp'
    con = timer = None
    try:
        experiment.resource_preflight(output)
        con = kaggle.database_connection(source, temp, threads)
        timer = deadline.interrupt_sql(con)
        _check_tables(con)
        where = '' if cutoff is None else f"WHERE t_dat < DATE '{cutoff.isoformat()}'"
        expected = con.execute(f'SELECT count(*) FROM transactions {where}').fetchone()[0]
        if not expected:
            raise ValueError('No transactions to export')
        columns = ', '.join(name for name, _ in TX_SCHEMA)
        con.execute('SET threads=1')
        con.execute('SET preserve_insertion_order=true')
        con.execute(f'''COPY (SELECT {columns}, strftime(t_dat, '%Y-%m-%d') AS d FROM transactions {where}
            ORDER BY {columns}) TO {_literal(output/'tx')} (FORMAT PARQUET, PARTITION_BY (d))''')
        (output/'articles').mkdir()
        con.execute(f'''COPY (SELECT {', '.join(ARTICLE_COLUMNS)} FROM articles ORDER BY article_id)
            TO {_literal(output/ARTICLES_FILE)} (FORMAT PARQUET)''')
        con.execute(f'SET threads={threads}')
        deadline.check()
        tx = _tx_summary(con, output, cutoff, deadline)
        if tx['rows'] != expected:
            raise ValueError('Exported rows differ from the database')
        articles = con.execute('SELECT count(*) FROM read_parquet(?)', [str(output/ARTICLES_FILE)]).fetchone()[0]
        after = source.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Source database changed during the export')
        deadline.check()
        record = dict(format=EXPORT_FORMAT, status='completed', before=report['before'], database=identity,
                      sources=sources, tx=tx,
                      articles=dict(rows=articles, sha256=experiment.sha256_file(output/ARTICLES_FILE, deadline)),
                      code=code)
        record['digest'] = experiment.canonical_digest(record)
        report = record
    except Exception as exc:
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
        error = kaggle.failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        shutil.rmtree(temp, ignore_errors=True)
        kaggle.atomic_json(output/'export.json', report)
    for path in output.rglob('*'):
        if path.is_file():
            path.chmod(0o444)  # the export is read by hash; nothing rewrites it in place
    return report


def read_export(export):
    """export.json of a completed export with its digest, exact file set and every file hash re-checked."""
    root = Path(export).resolve()
    record = kaggle.read_json(root/'export.json')
    if not isinstance(record, dict) or record.get('format') != EXPORT_FORMAT or record.get('status') != 'completed':
        raise ValueError(f'A completed {EXPORT_FORMAT} export.json is required')
    if set(record) != set(EXPORT_FIELDS):
        raise ValueError('export.json must hold exactly the contract fields')
    if experiment.canonical_digest({k: v for k, v in record.items() if k != 'digest'}) != record['digest']:
        raise ValueError('export.json differs from its digest')
    cutoff = None if record['before'] is None else _anchor(record['before'])
    tx, articles = record['tx'], record['articles']
    files = tx.get('files') if isinstance(tx, dict) else None
    if not isinstance(files, dict) or not files or not isinstance(articles, dict):
        raise ValueError('export.json needs tx files and articles')
    days = set()
    for rel, entry in files.items():
        match = TX_FILE.fullmatch(rel)
        if not match or not isinstance(entry, dict) or type(entry.get('rows')) is not int or entry['rows'] < 1:
            raise ValueError('export.json lists an unexpected tx file')
        day = date.fromisoformat(match.group(1))
        if cutoff is not None and day >= cutoff:
            raise ValueError('A cut export lists a day at or after its cut')
        days.add(day)
    if (sum(e['rows'] for e in files.values()), len(days), min(days).isoformat(), max(days).isoformat()) != (
            tx.get('rows'), tx.get('days'), tx.get('first'), tx.get('last')):
        raise ValueError('export.json tx totals differ from its files')
    present = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('An export holds no symbolic links')
        if path.is_file():
            present.add(path.relative_to(root).as_posix())
    if present != set(files) | {ARTICLES_FILE, 'export.json'}:
        raise ValueError(f'Export files differ from export.json: {len(present-set(files))-2} extra or '
                         f'{len(set(files)-present)} missing')
    for rel, entry in files.items():
        if experiment.sha256_file(root/rel) != entry['sha256']:
            raise ValueError('Export bytes changed')
    if experiment.sha256_file(root/ARTICLES_FILE) != articles.get('sha256'):
        raise ValueError('Export bytes changed')
    return record


# --- 1.2 sandbox ---------------------------------------------------------------------------------------------

def sandbox(export, anchor, keys_path, threads=4, memory='4GB'):
    """1.2: a new locked in-memory connection with tx, articles, cand and users only."""
    import duckdb
    cutoff = _anchor(anchor)
    threads = _threads(threads)
    if not isinstance(memory, str) or not MEMORY_TEXT.fullmatch(memory):
        raise ValueError('Memory must look like 4GB')
    root = Path(export).resolve()
    manifest = read_export(root)
    days = {}
    for rel in sorted(manifest['tx']['files']):
        day = date.fromisoformat(TX_FILE.fullmatch(rel).group(1))
        if day < cutoff:
            days.setdefault(day, []).append(str(root/rel))
    if not days:
        raise ValueError('The export holds no history before the anchor')
    keys_path = Path(keys_path).resolve()
    if not keys_path.is_file():
        raise ValueError('The batch keys parquet is missing')
    files = [path for day in sorted(days) for path in days[day]]
    directories = [str(root/'tx'/f'd={day.isoformat()}')+'/' for day in sorted(days)]
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
        listing = ', '.join(_literal(path) for path in files)
        columns = ', '.join(name for name, _ in TX_SCHEMA)
        con.execute(f'''CREATE VIEW tx AS SELECT {columns} FROM read_parquet([{listing}], hive_partitioning=false)
            WHERE t_dat < DATE '{cutoff.isoformat()}' ''')
        con.execute(f'''CREATE TABLE articles AS SELECT {', '.join('a.'+c for c in ARTICLE_COLUMNS)}
            FROM read_parquet(?) a SEMI JOIN (SELECT DISTINCT article_id FROM tx) t USING (article_id)
            ORDER BY a.article_id''', [str(root/ARTICLES_FILE)])
        con.execute('''CREATE TABLE cand AS SELECT customer_id, article_id FROM read_parquet(?)
            ORDER BY customer_id, article_id''', [str(keys_path)])
        if [(r[0], r[1]) for r in con.execute('DESCRIBE cand').fetchall()] != [(k, 'VARCHAR') for k in KEYS]:
            raise ValueError('Batch keys must be VARCHAR customer_id, article_id')
        nulls, repeated = con.execute('''SELECT count(*) FILTER (WHERE customer_id IS NULL OR article_id IS NULL),
            count(*)-count(DISTINCT (customer_id, article_id)) FROM cand''').fetchone()
        if nulls or repeated:
            raise ValueError('Batch keys must be unique non-NULL pairs')
        con.execute('CREATE TABLE users AS SELECT DISTINCT customer_id FROM cand ORDER BY customer_id')
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


def _proposal_failure(exc):
    """DuckDB errors a query can cause (SQL, conversion, out of memory, access outside the sandbox).

    I/O, internal, fatal, connection and transaction errors of DuckDB, and every
    non-DuckDB exception, are technical failures and propagate unchanged.
    """
    import duckdb
    technical = (duckdb.IOException, duckdb.InternalError, duckdb.FatalException, duckdb.ConnectionException,
                 duckdb.SerializationException, duckdb.TransactionException, duckdb.InterruptException)
    return isinstance(exc, duckdb.Error) and not isinstance(exc, technical)


# Runtime DuckDB errors may quote data, so they reach the agent only as a fixed text per class.
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


def error_feedback(exc, sql=''):
    """The only text a failed proposal may carry back to the agent, the logs and Git.

    Parser, binder and catalog errors are raised while planning, before any row
    is read: their message stays, through sanitize_error as a second guard.
    Every other DuckDB error of a proposal gets a fixed text per class, with no
    message content.
    """
    import duckdb
    name = type(exc).__name__
    if isinstance(exc, (duckdb.ParserException, duckdb.SyntaxException, duckdb.BinderException,
                        duckdb.CatalogException)):
        return f'{name}: {sanitize_error(str(exc), sql)}'
    return f'{name}: {RUNTIME_TEXT.get(name, RUNTIME_DEFAULT)}'


def _require_sandbox(con):
    try:
        locked, external = con.execute(
            "SELECT current_setting('lock_configuration'), current_setting('enable_external_access')").fetchone()
    except Exception:
        locked = external = None
    if locked is not True or external is not False:
        raise ValueError('Proposals run only in a locked sandbox connection')


class _Limit:
    """Interrupt one proposal after its time limit or at the command's wall deadline."""

    def __init__(self, con, seconds, deadline=None, sql=''):
        self.con, self.seconds, self.wall, self.sql = con, seconds, False, sql
        self.fired = threading.Event()
        limit = seconds
        if deadline is not None:
            left = deadline.expires-time.monotonic()
            if left <= 0:
                raise TimeoutError(kaggle.WALL_LIMIT)
            if left < limit:
                limit, self.wall = left, True
        self.timer = threading.Timer(limit, self._fire)
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
        if self.wall:
            return TimeoutError(kaggle.WALL_LIMIT)
        return ProposalError(f'timeout after {self.seconds:g} s')

    def error(self, exc):
        """The exception to raise instead of ``exc``; DuckDB messages never pass through."""
        import duckdb
        if self.fired.is_set():
            return self.timeout()
        if _proposal_failure(exc):
            return ProposalError(error_feedback(exc, self.sql))
        if isinstance(exc, duckdb.Error):
            # Technical: same class for the caller's handling, without the message.
            return type(exc)(f'{type(exc).__name__}: {TECHNICAL_TEXT}')
        return exc


def _check_output(con, level, sql):
    """1.4 on _x: level keys (VARCHAR, non-NULL, unique, inside their set) and 1-3 ag_* numeric values.

    Messages carry only names written in ``sql``, types, the level and constants;
    never values or counts of rows (a count can encode a value).
    """
    keys = LEVELS[level]
    described = [(row[0], row[1]) for row in con.execute('DESCRIBE _x').fetchall()]
    names, kinds = [n for n, _ in described], dict(described)
    # PIVOT and similar can name columns after data; such names are never echoed.
    if any(not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)', sql) for name in names if name not in keys):
        raise ProposalError('every output column must be named in the SQL (alias each value AS ag_...); '
                            'a column name not written in the SQL was produced')
    if len(set(names)) != len(names):
        raise ProposalError('output column names repeat')
    missing = [key for key in keys if key not in kinds]
    if missing:
        raise ProposalError(f'level {level} needs the key columns {", ".join(keys)}; missing {", ".join(missing)}')
    for key in keys:
        if kinds[key] != 'VARCHAR':
            raise ProposalError(f'key {key} must be VARCHAR, not {kinds[key]}')
    values = [name for name in names if name not in keys]
    if not 1 <= len(values) <= MAX_VALUES:
        raise ProposalError(f'one to {MAX_VALUES} value columns are required besides the keys, got {len(values)}')
    taken = _taken()
    for name in values:
        if not NAME.fullmatch(name):
            raise ProposalError(f'column {name} is not a key of this level and does not match '
                                '^ag_[a-z][a-z0-9_]{1,38}$')
        if name in taken:
            raise ProposalError(f'column {name} is a registered feature or a reserved name')
        if not VALUE_TYPE.fullmatch(kinds[name]):
            raise ProposalError(f'column {name} has type {kinds[name]}; integer, DECIMAL, FLOAT, DOUBLE or BOOLEAN '
                                'is required (dates as days before DATE \'{A}\')')
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
    universe = {'pair': 'cand', 'customer': 'users', 'article': 'articles'}[level]
    match = ' AND '.join(f'u.{key} = x.{key}' for key in keys)
    outside = con.execute(f'SELECT count(*) FROM _x x WHERE NOT EXISTS (SELECT 1 FROM {universe} u WHERE {match})'
                          ).fetchone()[0]
    if outside:
        raise ProposalError(f'some keys lie outside {universe}')
    return values, int(rows)


def _finite(name):
    value = f'CAST(x."{name}" AS DOUBLE)'
    return f'CASE WHEN isfinite({value}) AND abs({value}) <= {FLOAT32_MAX!r} THEN {value} END AS "{name}"'


def _fetch(con, level, names, shape):
    import numpy as np
    keys = LEVELS[level]
    casts = ', '.join(_finite(name) for name in names)
    if shape == 'table':
        order = ', '.join(f'x.{key}' for key in keys)
        return con.execute(f'SELECT {order}, {casts} FROM _x x ORDER BY {order}').fetch_df()
    join = ' AND '.join(f'x.{key} = c.{key}' for key in keys)
    head = 'c.customer_id, c.article_id, ' if shape == 'pairs' else ''
    query = f'SELECT {head}{casts} FROM cand c LEFT JOIN _x x ON {join} ORDER BY c.customer_id, c.article_id'
    if shape == 'pairs':
        return con.execute(query).fetch_df()
    fetched = con.execute(query).fetchnumpy()
    return {name: _floats(fetched[name]) for name in names}


def _execute(con, level, sql, cutoff, timeout_s, deadline=None, shape='pairs'):
    """The harness of 1.4: CREATE TEMP TABLE _x AS <sql>, checks, DOUBLE values in the requested shape.

    ``pairs``: cand keys + values; ``values``: the value arrays in cand order;
    ``table``: the level keys + values of _x. Returns (result, value names, rows of _x).
    """
    import duckdb
    body = sql.strip()
    if body.endswith(';'):
        body = body[:-1].rstrip()
    statement = 'CREATE TEMP TABLE _x AS\n'+body.replace('{A}', cutoff.isoformat())
    parsed = failure = None
    try:
        parsed = con.extract_statements(statement)
    except duckdb.Error as exc:
        failure = ProposalError(error_feedback(exc, sql))
    if failure is not None:
        raise failure  # outside the handler: the DuckDB message is not kept as __context__
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.CREATE:
        raise ProposalError('exactly one SELECT statement is allowed')
    limit = _Limit(con, timeout_s, deadline, sql)
    failure = None
    try:
        with limit:
            con.execute('DROP TABLE IF EXISTS _x')
            con.execute(statement)
            names, rows = _check_output(con, level, sql)
            result = _fetch(con, level, names, shape)
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
        raise failure  # outside the handler: the original exception is not kept as __context__
    return result, names, rows


def run_proposal(con, proposal, anchor, timeout_s):
    """One proposal in a sandbox: cand keys in order + its value columns as DOUBLE (1.4)."""
    level, sql = _fields(proposal)
    check_sql(sql, level)
    cutoff = _anchor(anchor)
    timeout = _seconds(timeout_s)
    _require_sandbox(con)
    return _execute(con, level, sql, cutoff, timeout, None, 'pairs')[0]


# --- agent columns for a batch of keys -----------------------------------------------------------------------

def _key_frame(keys):
    import pandas as pd
    if not isinstance(keys, pd.DataFrame) or not set(KEYS) <= set(keys.columns):
        raise ValueError('Keys must be a DataFrame with customer_id and article_id')
    frame = keys[list(KEYS)].reset_index(drop=True)
    for name in KEYS:
        if frame[name].isna().any() or pd.api.types.infer_dtype(frame[name], skipna=False) != 'string':
            raise ValueError(f'{name} keys must be non-NULL strings')
    if not len(frame):
        raise ValueError('At least one key is required')
    return frame


def _stage_keys(frame, path, threads):
    """keys.parquet sorted by the keys; returns the input position of every sorted row."""
    import duckdb
    import numpy as np
    import pandas as pd
    staged = pd.DataFrame({'customer_id': frame['customer_id'].to_numpy(dtype=object),
                           'article_id': frame['article_id'].to_numpy(dtype=object),
                           'pos': np.arange(len(frame), dtype=np.int64)})
    con = duckdb.connect(':memory:')
    try:
        con.execute(f'SET threads={threads}')
        con.execute('SET python_enable_replacements=false')
        con.execute('SET temp_directory=?', [str(Path(path).parent/'duckdb-temp')])
        con.register('_hm_keys', staged)
        repeated = con.execute('SELECT count(*)-count(DISTINCT (customer_id, article_id)) FROM _hm_keys').fetchone()[0]
        if repeated:
            raise ValueError('Keys must be unique (customer_id, article_id) pairs')
        con.execute(f'''COPY (SELECT customer_id, article_id FROM _hm_keys ORDER BY customer_id, article_id)
            TO {_literal(path)} (FORMAT PARQUET)''')
        order = con.execute('SELECT pos FROM _hm_keys ORDER BY customer_id, article_id').fetchnumpy()['pos']
    finally:
        con.close()
    return np.asarray(order, dtype=np.int64)


def _check_order(con, frame, order):
    import numpy as np
    got = con.execute('SELECT customer_id, article_id FROM cand ORDER BY customer_id, article_id').fetchnumpy()
    for name in KEYS:
        if not np.array_equal(np.asarray(got[name], dtype=object), frame[name].to_numpy(dtype=object)[order]):
            raise RuntimeError('Sandbox keys differ from the staged batch keys')


def _frozen(proposal, names):
    if list(names) != list(proposal['columns']):
        raise ProposalError(f'value columns {", ".join(names)} differ from the frozen {", ".join(proposal["columns"])}')


def agent_columns(export, anchor, keys, agent_set, *, threads=4, timeout_s=RUN_TIMEOUT, cache=None, deadline=None):
    """Values of every frozen proposal for the given keys: keys in input order + S.columns as float64.

    The keys go to keys.parquet in a scratch directory; the DataFrame never enters
    the sandbox. With a ``cache`` dict, article-level tables are kept under
    (export digest, anchor, proposal id, sha256 of the SQL); ``cache=None``
    computes everything. A proposal failure raises ProposalError with its id;
    the deadline raises TimeoutError('Declared wall limit exceeded').
    """
    import numpy as np
    import pandas as pd
    cutoff = _anchor(anchor)
    threads = _threads(threads)
    timeout = _seconds(timeout_s)
    if cache is not None and not isinstance(cache, dict):
        raise ValueError('The cache must be a dict or None')
    if deadline is not None:
        deadline.check()
    root = Path(export).resolve()
    manifest = read_export(root)
    _covers(manifest, cutoff)
    agent = _check_set(agent_set) if isinstance(agent_set, dict) else read_agent_set(agent_set)
    frame = _key_frame(keys)
    out = {name: np.full(len(frame), np.nan) for name in agent['columns']}
    info = dict(keys=len(frame), export_digest=manifest['digest'], set_digest=agent['digest'],
                anchor=cutoff.isoformat(), seconds={}, rows={}, non_null={}, cached=[])
    scratch = Path(tempfile.mkdtemp(prefix='tlab-hm-keys-')).resolve()
    con = None
    try:
        keys_path = scratch/'keys.parquet'
        order = _stage_keys(frame, keys_path, threads)
        con = sandbox(root, cutoff, keys_path, threads=threads)
        _check_order(con, frame, order)
        articles = None
        for proposal in agent['proposals']:
            if deadline is not None:
                deadline.check()
            pid, level, sql = proposal['id'], proposal['level'], proposal['sql']
            started = time.monotonic()
            try:
                if level == 'article' and cache is not None:
                    key = (manifest['digest'], cutoff.isoformat(), pid, hashlib.sha256(sql.encode('utf-8')).hexdigest())
                    entry = cache.get(key)
                    if entry is None:
                        table, names, rows = _execute(con, level, sql, cutoff, timeout, deadline, 'table')
                        entry = dict(index=pd.Index(table['article_id'].to_numpy(dtype=object)),
                                     values=table[names].to_numpy(dtype=np.float64, na_value=np.nan),
                                     columns=list(names), rows=rows)
                        cache[key] = entry
                    else:
                        info['cached'].append(pid)
                    names, rows = entry['columns'], entry['rows']
                    _frozen(proposal, names)
                    if articles is None:
                        articles = frame['article_id'].to_numpy(dtype=object)
                    positions = entry['index'].get_indexer(articles)
                    hit = positions >= 0
                    for j, name in enumerate(names):
                        out[name][hit] = entry['values'][positions[hit], j]
                else:
                    values, names, rows = _execute(con, level, sql, cutoff, timeout, deadline, 'values')
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
    for name in agent['columns']:
        result[name] = out[name]
        info['non_null'][name] = int(np.isfinite(out[name]).sum())
    return result, info


# --- 2. probe ------------------------------------------------------------------------------------------------

def _round(value):
    return None if value is None else round(float(value), 6)


def _share(value):
    """A share in a proposal record: 2 decimals (section 2)."""
    return None if value is None else round(float(value), 2)


def log2_bucket(value):
    """The record form of a count or of seconds: '0' or '2^k–2^(k+1)' with 2^k <= value < 2^(k+1).

    Exact rows, distinct counts and probe seconds never reach a record, the log or the
    prompt (section 2); k comes from frexp, so the bucket is exact for any positive float.
    """
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError('A log2 bucket needs a finite non-negative number')
    if value == 0:
        return '0'
    k = math.frexp(value)[1]-1
    return f'2^{k}\u20132^{k+1}'


BUCKET = re.compile(r'0|2\^(-?\d+)\u20132\^(-?\d+)')


def _stats(con, cutoff):
    """Label-free aggregates before the anchor (1.5 item 6); no ids, digests or label-week numbers."""
    anchor = cutoff.isoformat()
    past = f"t_dat < DATE '{anchor}'"

    def window(days):
        return f"t_dat >= DATE '{anchor}' - INTERVAL {days} DAY AND {past}"
    first, last = con.execute(f'SELECT min(t_dat), max(t_dat) FROM transactions WHERE {past}').fetchone()
    windows = {}
    for label, condition in (('7_days', window(7)), ('28_days', window(28)), ('90_days', window(90)),
                             ('365_days', window(365)), ('all_history', past)):
        rows, customers, articles = con.execute(f'''SELECT count(*), count(DISTINCT customer_id),
            count(DISTINCT article_id) FROM transactions WHERE {condition}''').fetchone()
        windows[label] = dict(rows=int(rows), customers=int(customers), articles=int(articles))
    customers, mean, quantiles, most, repeat = con.execute(f'''SELECT count(*), avg(n),
        quantile_cont(n, [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]), max(n), avg(CASE WHEN days >= 2 THEN 1 ELSE 0 END)
        FROM (SELECT customer_id, count(*) AS n, count(DISTINCT t_dat) AS days FROM transactions
              WHERE {window(90)} GROUP BY customer_id)''').fetchone()
    purchases = dict(customers=int(customers), mean=_round(mean),
                     **{f'p{q}': _round(v) for q, v in zip((10, 25, 50, 75, 90, 99), quantiles or [None]*6)},
                     max=None if most is None else int(most))
    low, quantiles, high = con.execute(f'''SELECT min(price), quantile_cont(price, [0.01, 0.1, 0.25, 0.5, 0.75, 0.9,
        0.99]), max(price) FROM transactions WHERE {past}''').fetchone()
    price = dict(min=_round(low), **{name: _round(v) for name, v in zip(('p01', 'p10', 'p25', 'p50', 'p75', 'p90', 'p99'),
                                                                     quantiles or [None]*7)}, max=_round(high))
    channels = con.execute(f'''SELECT sales_channel_id, count(*) FROM transactions WHERE {past}
        GROUP BY 1 ORDER BY 1''').fetchall()
    total = sum(n for _, n in channels)
    bought = f'SELECT DISTINCT article_id FROM transactions WHERE {past}'
    attributes = {}
    for code, name in ATTRIBUTES:
        target = code or name
        entry = dict(cardinality=int(con.execute(f'''SELECT count(DISTINCT a.{target}) FROM articles a
            SEMI JOIN ({bought}) b USING (article_id)''').fetchone()[0]))
        if code != 'product_code':
            fields = ', '.join(f'a.{c}' for c in (code, name) if c)
            top = con.execute(f'''SELECT {fields}, count(*) AS n FROM transactions t JOIN articles a USING (article_id)
                WHERE {window(28)} GROUP BY ALL ORDER BY n DESC, {fields} LIMIT 10''').fetchall()
            entry['top_28_days'] = [[*row[:-1], int(row[-1])] for row in top]
        attributes[target] = entry
    users, rows, recent, global_rows = con.execute('''SELECT count(DISTINCT customer_id), count(*),
        count(*) FILTER (WHERE source = 'recent'), count(*) FILTER (WHERE source = 'global') FROM hm_candidates''').fetchone()
    return dict(anchor=anchor, history=dict(first_day=first.isoformat(), last_day=last.isoformat()), windows=windows,
                purchases_per_customer_90_days=purchases,
                customers_with_2_or_more_purchase_days_90_days_share=_round(repeat),
                price_all_history=price,
                sales_channel_share={str(channel): _round(n/total) for channel, n in channels},
                attributes=attributes,
                candidates=dict(users=int(users), rows=int(rows), recent_per_user_mean=_round(recent/users),
                                global_share=_round(global_rows/rows)))


def _refuse_ids(stats):
    text = json.dumps(stats, ensure_ascii=False, allow_nan=False)
    if HEXLIKE.search(text) or DIGITS.search(text):
        raise ValueError('stats.json would carry an id-shaped string; it holds aggregates only')


def prepare_probe(database, export, anchor, users, output, threads=3):
    """Section 2 probe: the first ``users`` customers with a purchase in [A-90d, A) by
    sha256(id||':2026'), id, their C0-Q120 candidates and M23 values, stats.json, probe.json."""
    cutoff = experiment.check_anchor(_anchor(anchor))
    if type(users) is not int or users < 1:
        raise ValueError('Users must be a positive integer')
    threads = _threads(threads)
    deadline = experiment.Deadline(WALL_SECONDS)
    code = agent_code_identity(deadline)
    source, stat, identity, sources = _database(database, deadline)
    manifest = read_export(export)
    if manifest['before'] is not None:
        raise ValueError('The probe needs the complete export, without --before')
    if manifest['database'] != identity or manifest['sources'] != sources:
        raise ValueError('Export and database must be the same audited bytes')
    output = kaggle.new_output(output)
    report = dict(format=PROBE_FORMAT, status='running', anchor=cutoff.isoformat(), users=users,
                  cohort_seed=experiment.SEED, policy=kaggle.POLICY, export_digest=manifest['digest'])
    temp = output/'duckdb-temp'
    con = timer = None
    try:
        report['resources'] = dict(experiment.resource_preflight(output), threads=threads)
        report.update(database=identity, sources=sources, runtime=experiment.runtime_identity(), code=code)
        con = kaggle.database_connection(source, temp, threads)
        timer = deadline.interrupt_sql(con)
        kaggle.create_item_ranks(con, cutoff)
        con.execute('''CREATE TEMP TABLE probe_users AS SELECT customer_id FROM (SELECT DISTINCT customer_id
            FROM hm_k_history) ORDER BY sha256(customer_id || ?), customer_id LIMIT ?''', [f':{experiment.SEED}', users])
        found = con.execute('SELECT count(*) FROM probe_users').fetchone()[0]
        if found != users:
            raise ValueError(f'{found} customers bought in the 90 days before the anchor; the probe needs {users}')
        kaggle.create_chunk_candidates(con, 'probe_users', users)
        deadline.check()
        built = engine.build_features(con, cutoff.isoformat(), candidates_table='hm_candidates')
        numeric = list(engine.PILOT_NUMERIC_FEATURES)
        report['features'] = dict(digest=experiment.feature_contract(built)['digest'], numeric=numeric)
        con.register('_hm_probe_frame', built.frame[[*KEYS, *numeric]])
        try:
            bad = con.execute('''SELECT count(*) FROM (
                (SELECT customer_id, article_id FROM hm_candidates EXCEPT SELECT customer_id, article_id FROM _hm_probe_frame)
                UNION ALL
                (SELECT customer_id, article_id FROM _hm_probe_frame EXCEPT SELECT customer_id, article_id FROM hm_candidates))'''
                              ).fetchone()[0]
            rows = con.execute('SELECT count(*) FROM _hm_probe_frame').fetchone()[0]
            if bad or rows != 120*users:
                raise ValueError('The feature frame must hold exactly the candidate keys')
            numbers = ', '.join(f'CAST("{n}" AS DOUBLE) AS "{n}"' for n in numeric)
            con.sql(f'SELECT customer_id, article_id, {numbers} FROM _hm_probe_frame ORDER BY customer_id, article_id'
                    ).write_parquet(str(output/'m23.parquet'))
        finally:
            con.unregister('_hm_probe_frame')
        del built
        con.sql('SELECT customer_id, article_id FROM hm_candidates ORDER BY customer_id, article_id'
                ).write_parquet(str(output/'keys.parquet'))
        con.sql('SELECT customer_id, article_id, source FROM hm_candidates ORDER BY customer_id, article_id'
                ).write_parquet(str(output/'sources.parquet'))
        stats = _stats(con, cutoff)
        _refuse_ids(stats)
        kaggle.atomic_json(output/'stats.json', stats)
        report['rows'] = int(rows)
        report['files'] = {name: experiment.sha256_file(output/name, deadline) for name in PROBE_FILES}
        after = source.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Source database changed while the probe was built')
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        error = kaggle.failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        shutil.rmtree(temp, ignore_errors=True)
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
        kaggle.atomic_json(output/'probe.json', report)
    return report


# --- 2. one proposal on the probe ----------------------------------------------------------------------------

def _load_probe(probe, manifest, threads):
    import duckdb
    import numpy as np
    record = kaggle.read_json(probe/'probe.json')
    if not isinstance(record, dict) or record.get('format') != PROBE_FORMAT or record.get('status') != 'completed':
        raise ValueError(f'A completed {PROBE_FORMAT} probe.json is required')
    if record.get('export_digest') != manifest['digest']:
        raise ValueError('The probe was not built from this export')
    files = record.get('files')
    if not isinstance(files, dict) or any(files.get(name) != experiment.sha256_file(probe/name) for name in PROBE_FILES):
        raise ValueError('Probe files differ from probe.json')
    anchor, users = _anchor(record.get('anchor')), record.get('users')
    if type(users) is not int or users < 1:
        raise ValueError('probe.json needs a positive integer users')
    numeric = list(engine.PILOT_NUMERIC_FEATURES)
    keys_path, sources_path, m23_path = (str(probe/name) for name in PROBE_FILES[:3])
    order = 'ORDER BY customer_id, article_id'
    con = duckdb.connect(':memory:')
    try:
        con.execute(f'SET threads={threads}')
        con.execute('SET python_enable_replacements=false')
        keys = con.execute(f'SELECT customer_id, article_id FROM read_parquet(?) {order}', [keys_path]).fetchnumpy()
        sources = con.execute(f'SELECT customer_id, article_id, source FROM read_parquet(?) {order}',
                              [sources_path]).fetchnumpy()
        m23 = con.execute(f'SELECT * FROM read_parquet(?) {order}', [m23_path]).fetchnumpy()
        sample = con.execute(f'''SELECT pos FROM (SELECT customer_id, article_id,
            row_number() OVER ({order})-1 AS pos FROM read_parquet(?))
            ORDER BY sha256(customer_id || '|' || article_id), pos LIMIT ?''', [keys_path, SAMPLE_ROWS]).fetchnumpy()['pos']
        cohort = con.execute('''SELECT customer_id FROM (SELECT DISTINCT customer_id FROM read_parquet(?))
            ORDER BY sha256(customer_id || ?), customer_id''', [keys_path, f':{experiment.SEED}']).fetchnumpy()['customer_id']
    finally:
        con.close()
    customers = np.asarray(keys['customer_id'], dtype=object)
    articles = np.asarray(keys['article_id'], dtype=object)
    if list(m23) != [*KEYS, *numeric]:
        raise ValueError('m23.parquet must hold the keys and the 18 M23 numeric columns')
    for table in (sources, m23):
        if not (np.array_equal(np.asarray(table['customer_id'], dtype=object), customers) and
                np.array_equal(np.asarray(table['article_id'], dtype=object), articles)):
            raise ValueError('Probe files must share the same keys')
    if len(customers) != record.get('rows') or len(cohort) != users:
        raise ValueError('Probe rows or users differ from probe.json')
    source = np.asarray(sources['source'], dtype=object)
    return dict(anchor=anchor, keys_path=probe/'keys.parquet', customer_id=customers, article_id=articles,
                recent=source == 'recent', global_=source == 'global',
                m23=np.column_stack([_floats(m23[name]) for name in numeric]), m23_names=numeric,
                sample=np.asarray(sample, dtype=np.int64), cohort=np.asarray(cohort, dtype=object))


def _align(frame, level, customers, articles):
    """Values of a level-keyed frame on the given pairs: (value names, float64 matrix, NaN where absent)."""
    import numpy as np
    import pandas as pd
    keys = LEVELS[level]
    names = [column for column in frame.columns if column not in keys]
    if level == 'pair':
        index = pd.MultiIndex.from_arrays([frame[k].to_numpy(dtype=object) for k in keys])
        target = pd.MultiIndex.from_arrays([customers, articles])
    else:
        index = pd.Index(frame[keys[0]].to_numpy(dtype=object))
        target = pd.Index(customers if level == 'customer' else articles)
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


def _prior_columns(prior_values, data):
    """Accepted values (frames as evaluate_proposal returned them) aligned on the probe keys."""
    import pandas as pd
    if prior_values is None:
        prior_values = []
    if not isinstance(prior_values, (list, tuple)):
        raise ValueError('prior_values must be a list of DataFrames')
    levels = {('customer_id', 'article_id'): 'pair', ('customer_id',): 'customer', ('article_id',): 'article'}
    columns = {}
    for frame in prior_values:
        if not isinstance(frame, pd.DataFrame):
            raise ValueError('prior_values must be a list of DataFrames')
        level = levels.get(tuple(key for key in KEYS if key in frame.columns))
        if level is None:
            raise ValueError('A prior frame needs the keys of its level')
        names, matrix = _align(frame, level, data['customer_id'], data['article_id'])
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
    """Coarse coverage, size and nearest column of one value column; reasons it is invalid.

    Only coarsened numbers leave this function (section 2): shares to 2 decimals, distinct
    as a log2 bucket, |rho| to 1 decimal. No value quantile is computed or stored: a step
    column over customers would carry purchase rows through p01/p50/p99 (review 21.10).
    """
    import numpy as np
    name, column = names[j], values[:, j]
    present = ~np.isnan(column)
    count = int(present.sum())
    distinct = int(np.unique(column[present]).size)

    def share(mask):
        return _share(present[mask].mean()) if mask.any() else None
    sample = data['sample']
    reference = [(other, data['m23'][sample, i]) for i, other in enumerate(data['m23_names'])]
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


def _invariance(root, cutoff, level, sql, names, values, data, threads):
    """The first 1000 probe customers: the full probe run against two half batches (section 2)."""
    import pandas as pd
    cohort = list(data['cohort'][:INVARIANCE_USERS])
    half = (len(cohort)+1)//2
    customers, articles = data['customer_id'], data['article_id']
    differ = 0
    with tempfile.TemporaryDirectory(prefix='tlab-hm-batch-') as scratch:
        for number, part in enumerate((cohort[:half], cohort[half:]), 1):
            if not part:
                continue
            mask = pd.Series(customers).isin(set(part)).to_numpy()
            path = Path(scratch).resolve()/f'half-{number}.parquet'
            _stage_keys(pd.DataFrame({'customer_id': customers[mask], 'article_id': articles[mask]}), path, threads)
            con = sandbox(root, cutoff, path, threads=threads)
            try:
                table, got, _ = _execute(con, level, sql, cutoff, PROBE_TIMEOUTS[level], None, 'table')
            except ProposalError as exc:
                return f'batch invariance: the run on half {number} failed ({exc})'
            finally:
                _close(con)
            if got != names:
                return 'batch invariance: value columns differ between batches'
            differ += _mismatches(values[mask], _align(table, level, customers[mask], articles[mask])[1])
    if differ:
        return (f'batch invariance: values of the first {len(cohort)} probe customers differ between '
                'the full probe and its two halves')
    return None


def _record(proposal):
    source = proposal if isinstance(proposal, dict) else {}
    record = {key: source.get(key) for key in ('id', 'round', 'index', *FIELDS)}
    record.update(status='invalid', error=None, seconds=None, rows=None, columns=[])
    return record


def evaluate_proposal(probe, export, proposal, prior_values, threads=3):
    """Section 2 record of one proposal on the probe, and its values (level keys + ag_*) when valid.

    Contract violations, SQL errors, timeouts and the validity rules give a record
    with status 'invalid'; ProposalError is not raised. Any other exception is a
    technical failure. The budget status is the loop's.

    Every number in the record is coarse: shares to 2 decimals, rows, distinct and
    seconds as log2 buckets, |rho| to 1 decimal, no value quantiles. A valid frame
    carries the exact probe seconds for the loop's budget in attrs['probe_seconds'].
    """
    threads = _threads(threads)
    root = Path(export).resolve()
    manifest = read_export(root)
    data = _load_probe(Path(probe).resolve(), manifest, threads)
    cutoff = data['anchor']
    _covers(manifest, cutoff)
    prior = _prior_columns(prior_values, data)
    record = _record(proposal)
    try:
        level, sql = _fields(proposal)
        check_sql(sql, level)
        con = sandbox(root, cutoff, data['keys_path'], threads=threads)
        try:
            started = time.monotonic()
            table, names, rows = _execute(con, level, sql, cutoff, PROBE_TIMEOUTS[level], None, 'table')
            seconds = time.monotonic()-started
        finally:
            _close(con)
    except ProposalError as exc:
        record['error'] = _clip(exc)
        return record, None
    # The record holds log2 buckets only; the exact probe seconds of a valid proposal travel
    # to the loop's budget on the returned frame (table.attrs['probe_seconds']), never in the record.
    record.update(seconds=log2_bucket(seconds), rows=log2_bucket(rows))
    values = _align(table, level, data['customer_id'], data['article_id'])[1]
    reasons = []
    for j in range(len(names)):
        summary, problems = _column(j, names, values, prior, data)
        record['columns'].append(summary)
        reasons += problems
    problem = _invariance(root, cutoff, level, sql, names, values, data, threads)
    if problem:
        reasons.append(problem)
    if reasons:
        record['error'] = _clip('; '.join(reasons))
        return record, None
    record['status'] = 'valid'
    table.attrs['probe_seconds'] = round(seconds, 3)
    return record, table


# --- CLI -----------------------------------------------------------------------------------------------------

def main(argv=None):
    parser = kaggle.Parser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('export', help='day-partitioned history and article attributes for the sandbox')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--before')
    command.add_argument('--threads', type=int, default=4)
    command = sub.add_parser('probe', help='probe keys, sources, M23 values and label-free statistics')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--export', type=Path, required=True)
    command.add_argument('--anchor', required=True)
    command.add_argument('--users', type=int, default=5000)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--threads', type=int, default=3)
    try:
        args = parser.parse_args(argv)
    except kaggle.UsageError as exc:
        tokens = sys.argv[1:] if argv is None else list(argv)
        print(json.dumps(dict(status='failed', command=next((t for t in tokens if t in sub.choices), None),
                              error_type='UsageError', message=str(exc)[:500])))
        return 1
    try:
        if not kaggle.isolated():
            raise RuntimeError(f'{args.command} reads downloaded data; run it as python -I scripts/{MODULE}')
        if args.command == 'export':
            result = export_history(args.database, args.output, args.before, args.threads)
            tx = result['tx']
            print(json.dumps(dict(status=result['status'], before=result['before'], rows=tx['rows'], days=tx['days'],
                                  files=len(tx['files']), articles=result['articles']['rows'], digest=result['digest'])))
        else:
            result = prepare_probe(args.database, args.export, args.anchor, args.users, args.output, args.threads)
            print(json.dumps(dict(status=result['status'], anchor=result['anchor'], users=result['users'],
                                  rows=result['rows'], export_digest=result['export_digest'],
                                  features_digest=result['features']['digest'])))
    except Exception as exc:
        message = str(exc)[:500]
        if _native(exc):
            # Native errors can quote data rows; export.json or probe.json keep the detail.
            message = 'Native library error; see the output manifest or report if one was written'
        print(json.dumps(dict(status='failed', command=args.command, error_type=type(exc).__name__, message=message)))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
