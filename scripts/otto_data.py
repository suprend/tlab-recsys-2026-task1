"""Data side of the OTTO port (docs/otto-design.md, §11 row ``otto_data.py``).

Commands (``.venv/bin/python -I scripts/otto_data.py <command> ...``; one JSON
line on stdout, exit 0/1, refusal without ``-I``):

``load``
    Raw files of ``data/raw-otto-kaggle`` -> day partitions from S5
    (``events_path(d)``), the receipt ``otto-verify.json`` next to the raw files
    (file sizes and SHA-256, the ts unit, S5, schema facts, Σn²(I_k), gate 0).
    §1, §2.1, §2.5, §5.7, §8.
``collect --role train|val|probe|kaggle``
    One fold collection (§2.2, §4, §11): ``prefix/``, ``frame.parquet``
    (candidates and features of base B), ``labels.parquet``, ``manifest.json``;
    ``population.json`` (dev population) for ``val``.
``collect-holdout``
    The holdout collection of F4 for every session of Q_4 (§2.5): ``prefix/``,
    ``frame.parquet``, ``sealed/labels.parquet``; opens W4 once.
``pop``, ``assemble``, ``fold-stats``, ``init-base``
    Pop lists of a collection (§4), the Kaggle file (§3, §9), descriptive fold
    statistics for gate 0 (§2.3) and the initial base B (§4).
``rehearse-frame --fold 3``
    The B frame over every session of Q_3 into a scratch directory, deleted after:
    time, peak RSS and peak spill, the memory rehearsal for F4/F5 (§12).

Library functions for otto_agent and otto_model: ``read_load``, ``history``,
``views``, ``cut_point``, ``training_sessions``, ``pop``, ``check_submission``.

Paths, the barrier and formats come only from ``otto_common``. Downloaded data is
read only from processes run with ``-I``; nothing is executed or imported from
the data directory.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import resource
import shutil
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts import otto_common as oc  # noqa: E402
from scripts.otto_common import require  # noqa: E402

# =============================================================================== constants

LOAD_FORMAT = 'otto-load-v1'
ASSEMBLE_FORMAT = 'otto-assemble-v1'

ZIP_FILE = 'otto-recommender-system.zip'
ZIP_SHA_FILE = 'otto.zip.sha256'
TRAIN_JSONL = 'train.jsonl'
TEST_JSONL = 'test.jsonl'
SAMPLE_CSV = 'sample_submission.csv'
FILE_SIZES = {ZIP_FILE: 2_080_714_974, TRAIN_JSONL: 11_307_535_945, TEST_JSONL: 402_090_304,
              SAMPLE_CSV: 183_898_350}                                       # §1, facts of 22.10

# README numbers of §1 checked by gate 0 with a 1 % tolerance (§8); test: sessions only.
README_FACTS = dict(train_sessions=12_900_000, train_events=216_700_000, train_clicks=194_700_000,
                    train_carts=16_900_000, train_orders=5_100_000, train_len_min=2, train_len_max=500,
                    train_len_median=6, train_len_mean=16.8, test_sessions=1_670_000)
README_TOLERANCE = 0.01
EARLY_SHARE_MAX = 0.001                  # events before S5 - 28 d (§2.1)
MS_FLOOR = 10**12                        # every ts >= 10^12: milliseconds (§1)
S_CEIL = 10**11                          # every ts < 10^11: seconds

CUT_SALT = ':otto-cut:2026'              # §2.2
TYPE_NAMES = oc.TYPES                    # code = index (TYPE_CODES)
NEUTRAL_EVENTS = ('view', 'cart', 'order')    # agent names of the three types (§5.6)

THREADS = 8                              # §12: load, collect
MEMORY_LIMIT = '20GB'
MAX_TEMP = '40GB'
FRAME_BATCH = 250_000                    # sessions per frame batch (memory only; result independent)
FETCH_ROWS = 100_000                     # rows per fetch when assemble streams the Kaggle file

HISTORY_DEPTH = 50                       # §4 (h)
POP_DEPTH = 20                           # §4 p_t
MAX_CANDIDATES = 110
ITEM_WINDOW_MAX_DAYS = 7                 # §2.4, §4: item windows of B not longer than 7 days
SOURCE_COLUMNS = ('h_rank', 'pop_rank_clicks', 'pop_rank_carts', 'pop_rank_orders')


# The base B of §4: name, formula, missing (otto-base-v1 through oc.make_base).
BASE_FEATURES = (
    ('s_len', 'events in the prefix', '-'),
    ('s_items', 'distinct aid in the prefix', '-'),
    ('s_carts', 'carts events in the prefix', '0'),
    ('s_orders', 'orders events in the prefix', '0'),
    ('s_dur', 'ts of the last minus ts of the first prefix event, s', '-'),
    ('p_clicks', 'clicks events of the aid in the prefix', '0'),
    ('p_carts', 'carts events of the aid in the prefix', '0'),
    ('p_orders', 'orders events of the aid in the prefix', '0'),
    ('p_last_pos', 'position of the last occurrence of the aid from the prefix end (1 = last event)',
     'NULL outside (h)'),
    ('p_last_age', 'ts of the last prefix event minus ts of the last occurrence of the aid, s', 'NULL outside (h)'),
    ('p_is_last', '1 if the aid is the last prefix event', '0'),
    ('h_rank', 'position in (h)', 'NULL outside (h)'),
    ('pop_rank_clicks', 'position in p_clicks', 'NULL outside p_clicks'),
    ('pop_rank_carts', 'position in p_carts', 'NULL outside p_carts'),
    ('pop_rank_orders', 'position in p_orders', 'NULL outside p_orders'),
    ('i_wk_clicks', 'distinct sessions of Q_k with clicks of the aid in the prefix', '0'),
    ('i_wk_carts', 'distinct sessions of Q_k with carts of the aid in the prefix', '0'),
    ('i_wk_orders', 'distinct sessions of Q_k with orders of the aid in the prefix', '0'),
    ('i_h7_carts', 'distinct sessions of H_k with carts of the aid in the 7 d before start(W_k)', '0'),
    ('i_h7_orders', 'distinct sessions of H_k with orders of the aid in the 7 d before start(W_k)', '0'),
    ('i_h7_all', 'events of the aid in H_k in the 7 d before start(W_k)', '0'),
)
CANDIDATE_POLICY = dict(
    history=dict(depth=HISTORY_DEPTH, order='distinct prefix aid by last occurrence (seq) desc, then aid asc'),
    popular=dict(depth=POP_DEPTH, types=list(TYPE_NAMES),
                 order='distinct sessions of Q_k with the type in the prefix desc, then aid asc'),
    union=['history', 'popular_clicks', 'popular_carts', 'popular_orders'],
    max=MAX_CANDIDATES,
)

ITEM_WINDOW = re.compile(r'i_h([0-9]+)_(clicks|carts|orders|all)')


# =============================================================================== small helpers

def _duckdb():
    import duckdb
    return duckdb


def _pd():
    import pandas as pd
    return pd


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _list_literal(paths):
    require(paths, 'No files to read')
    return '[' + ', '.join(_literal(p) for p in paths) + ']'


def connect(threads=THREADS, memory=MEMORY_LIMIT, temp=None, max_temp=MAX_TEMP, database=':memory:'):
    """DuckDB with the §12 limits; ``temp`` is the spill directory."""
    con = _duckdb().connect(str(database))
    try:
        con.execute(f'SET threads={int(threads)}')
        con.execute(f'SET memory_limit={_literal(memory)}')
        if temp is not None:
            con.execute(f'SET temp_directory={_literal(temp)}')
            con.execute(f'SET max_temp_directory_size={_literal(max_temp)}')
        con.execute('SET preserve_insertion_order=false')
    except BaseException:
        con.close()
        raise
    return con


def _scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def _spill_dir():
    """A fresh, not yet created spill path under artifacts/otto/.spill; DuckDB creates it on the
    first spill and removes it on close, callers that own the connection also remove it."""
    root = oc.artifacts_dir()/'.spill'
    root.mkdir(parents=True, exist_ok=True)
    return root/f'duckdb-{os.getpid()}-{uuid.uuid4().hex[:12]}'


def _dir_bytes(path):
    total = 0
    for item in Path(path).rglob('*') if Path(path).exists() else ():
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:                          # a spill file removed while walking
            pass
    return total


class _PeakBytes:
    """Polls the size of a directory in a thread; ``peak`` is the largest size seen (bytes)."""

    def __init__(self, path, every=0.5):
        self.path, self.every, self.peak = Path(path), every, 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.peak = max(self.peak, _dir_bytes(self.path))
            self._stop.wait(self.every)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, _dir_bytes(self.path))


def _code():
    """Code identity for load and collection manifests: files and missing sibling modules (strict=False)."""
    return oc.code_identity(strict=False)


def _peak_rss_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak/2**20 if sys.platform == 'darwin' else peak/2**10, 1)


def cut_hash(session):
    """h of §2.2: the first 16 hex digits of sha256(str(session) + ':otto-cut:2026') as an unsigned int."""
    return int(hashlib.sha256(f'{int(session)}{CUT_SALT}'.encode('utf-8')).hexdigest()[:16], 16)


def cut_point(session, n):
    """c = 1 + (h mod (n - 1)) for a session of n >= 2 events (§2.2)."""
    require(int(n) >= 2, 'A session needs at least 2 events to be cut')
    return 1 + cut_hash(session) % (int(n)-1)


_HEX_CAST = None


def hex_ubigint_sql(hex_expr, con=None):
    """SQL of the 16-hex prefix of ``hex_expr`` as UBIGINT (§1, «Нормализация»).

    The direct cast is used when DuckDB accepts it for 0xffffffffffffffff, otherwise the two-half form.
    """
    global _HEX_CAST
    if _HEX_CAST is None:
        probe = con or connect(1, '256MB')
        try:
            _HEX_CAST = _scalar(probe, "SELECT CAST('0x' || 'ffffffffffffffff' AS UBIGINT)") == 2**64-1
        except Exception:  # noqa: BLE001 - the fallback is part of the contract
            _HEX_CAST = False
        finally:
            if con is None:
                probe.close()
    if _HEX_CAST:
        return f"CAST('0x' || substr({hex_expr}, 1, 16) AS UBIGINT)"
    return (f"(CAST('0x' || substr({hex_expr}, 1, 8) AS UBIGINT) * CAST(4294967296 AS UBIGINT) "
            f"+ CAST('0x' || substr({hex_expr}, 9, 8) AS UBIGINT))")


def cut_sql(session='session', n='n', con=None):
    hexed = f"sha256(CAST({session} AS VARCHAR) || {_literal(CUT_SALT)})"
    return f'(1 + ({hex_ubigint_sql(hexed, con)} % CAST(({n}) - 1 AS UBIGINT)))'


def week_sql(d):
    """DuckDB twin of oc.week_of_day for a partition-day expression."""
    return f'LEAST(5, GREATEST(1, 5 + CAST(floor(({d}) / 7.0) AS BIGINT)))'


def _partition_files(days, purpose):
    """read_parquet globs of the requested day partitions after the barrier (oc.partition_glob)."""
    days = sorted(int(d) for d in days)
    return oc.partition_glob(days, purpose) if days else []


def _events_select(files):
    columns = ', '.join(oc.EVENT_COLUMNS)
    return f'SELECT {columns} FROM read_parquet({_list_literal(files)}, hive_partitioning=false)'


# =============================================================================== load (§1, §2.1, §2.5, §5.7, §8)

def _read_zip_sha(path):
    text = Path(path).read_text(encoding='utf-8').split()
    require(text and re.fullmatch(r'[0-9a-f]{64}', text[0]), f'{path.name} holds no SHA-256')
    return text[0]


def _verify_files(raw, check_contract):
    files = {}
    names = (TRAIN_JSONL, TEST_JSONL, SAMPLE_CSV)
    for name in names:
        require((raw/name).is_file(), f'{name} is missing in {raw}')
    if check_contract:
        for name, size in FILE_SIZES.items():
            actual = (raw/name).stat().st_size if (raw/name).is_file() else None
            require(actual == size, f'{name}: {actual} bytes, the contract says {size}')
        expected = _read_zip_sha(raw/ZIP_SHA_FILE)
        actual = oc.sha256_file(raw/ZIP_FILE)
        require(actual == expected, f'{ZIP_FILE}: SHA-256 {actual} != {ZIP_SHA_FILE} {expected}')
        files[ZIP_FILE] = dict(bytes=(raw/ZIP_FILE).stat().st_size, sha256=actual, matches=ZIP_SHA_FILE)
    elif (raw/ZIP_FILE).is_file():
        files[ZIP_FILE] = dict(bytes=(raw/ZIP_FILE).stat().st_size, sha256=oc.sha256_file(raw/ZIP_FILE))
    for name in names:
        files[name] = dict(bytes=(raw/name).stat().st_size, sha256=oc.sha256_file(raw/name))
    return files


def _read_jsonl_sql(path):
    """Events of a jsonl file with seq from the array index (WITH ORDINALITY, from 1).

    A session without events yields one row with a NULL event, so it is counted and refused.
    """
    columns = "{'session': 'BIGINT', 'events': 'STRUCT(aid BIGINT, ts BIGINT, \"type\" VARCHAR)[]'}"
    codes = ' '.join(f"WHEN {_literal(name)} THEN {code}" for code, name in enumerate(TYPE_NAMES))
    return f"""
        SELECT r.session AS session, u.e.aid AS aid, u.e.ts AS ts,
               CAST(CASE u.e."type" {codes} END AS UTINYINT) AS type,
               CAST(u.seq AS INTEGER) AS seq, u.e IS NULL AS empty
        FROM read_json({_literal(path)}, format='newline_delimited', columns={columns}) r,
             unnest(CASE WHEN r.events IS NULL OR len(r.events) = 0 THEN [NULL] ELSE r.events END)
                 WITH ORDINALITY AS u(e, seq)"""


def _length_facts(con, table):
    row = con.execute(f"""SELECT count(*), min(n), max(n), median(n), avg(n),
            quantile_disc(n, [0.1, 0.25, 0.5, 0.75, 0.9, 0.99])
        FROM (SELECT session, count(*) AS n FROM {table} GROUP BY session)""").fetchone()
    return dict(sessions=int(row[0]), len_min=int(row[1]), len_max=int(row[2]), len_median=float(row[3]),
                len_mean=float(row[4]), len_quantiles=dict(zip(('p10', 'p25', 'p50', 'p75', 'p90', 'p99'),
                                                               (int(x) for x in row[5]))))


def _type_counts(con, table, prefix):
    rows = dict(con.execute(f'SELECT type, count(*) FROM {table} GROUP BY type').fetchall())
    return {f'{prefix}_{name}': int(rows.get(code, 0)) for code, name in enumerate(TYPE_NAMES)}


def _session_shares(con, table):
    """Shares of sessions with a carts / orders event (descriptive similarity, §2.3)."""
    row = con.execute(f"""SELECT avg(c), avg(o) FROM (SELECT session, max(CASE WHEN type = 1 THEN 1 ELSE 0 END) c,
        max(CASE WHEN type = 2 THEN 1 ELSE 0 END) o FROM {table} GROUP BY session)""").fetchone()
    return dict(share_with_carts=float(row[0]), share_with_orders=float(row[1]))


def _readme_failures(facts):
    failures = []
    for key, expected in README_FACTS.items():
        actual = facts.get(key)
        if actual is None or abs(float(actual)-float(expected)) > README_TOLERANCE*abs(float(expected)):
            failures.append(f'{key}: {actual} vs README {expected} (±{README_TOLERANCE:.0%})')
    return failures


def _write_partitions(con, table, source, s5, written):
    """COPY each day of ``table`` into ``events_path(d)``; ``written`` collects the created days."""
    days = [int(d) for (d,) in con.execute(f'SELECT DISTINCT d FROM {table} ORDER BY d').fetchall()]
    if source == 'test':
        require(all(d >= 0 for d in days), 'Test events before S5')
    for d in days:
        target = oc.events_path(d)
        require(not target.exists(), f'{target} exists')
        target.mkdir(parents=True)
        written.append(d)
        con.execute(f"""COPY (SELECT {', '.join(oc.EVENT_COLUMNS)} FROM {table} WHERE d = {d})
            TO {_literal(target/'part-0.parquet')} (FORMAT parquet, COMPRESSION zstd)""")
    return days


def load(check_contract=True, threads=THREADS, memory=MEMORY_LIMIT, max_temp=MAX_TEMP):
    """Raw jsonl -> day partitions and the receipt otto-verify.json (§1, §2.1, §2.5, §5.7, §8 gate 0).

    ``check_contract=False`` (smoke slices only) records sizes, SHA-256 and README
    facts without comparing them with the contract; the receipt says so. It runs only
    when oc.ROOT is not this repository (a smoke root under /tmp or a test root).
    """
    _require_unchecked_outside(check_contract)
    started = time.monotonic()
    timings = {}
    raw = oc.raw_dir()
    receipt_path = oc.verify_path()
    require(not receipt_path.exists(), f'{receipt_path} exists: load runs once')
    require(not oc.existing_days(), 'Day partitions already exist: load runs once')
    code = _code()
    files = _verify_files(raw, check_contract)
    timings['verify_files'] = round(time.monotonic()-started, 1)
    oc.artifacts_dir().mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.load-', dir=oc.artifacts_dir()))
    written = []
    try:
        con = connect(threads, memory, temp=work/'spill', max_temp=max_temp, database=work/'stage.duckdb')
        try:
            t0 = time.monotonic()
            for name, table in ((TRAIN_JSONL, 'train_raw'), (TEST_JSONL, 'test_raw')):
                con.execute(f'CREATE TABLE {table} AS {_read_jsonl_sql(raw/name)}')
            timings['read_jsonl'] = round(time.monotonic()-t0, 1)
            raw_checks = {}
            for table, src in (('train_raw', 'train'), ('test_raw', 'test')):
                row = con.execute(f"""SELECT count(*) FILTER (WHERE empty),
                    count(*) FILTER (WHERE NOT empty AND (session IS NULL OR aid IS NULL OR ts IS NULL
                                                         OR seq IS NULL)),
                    count(*) FILTER (WHERE NOT empty AND type IS NULL),
                    count(*) FILTER (WHERE seq = 1), count(DISTINCT session), min(ts), max(ts)
                    FROM {table}""").fetchone()
                raw_checks[src] = dict(empty_sessions=int(row[0]), null_fields=int(row[1]), unknown_types=int(row[2]),
                                       lines=int(row[3]), distinct_sessions=int(row[4]),
                                       ts_min_raw=None if row[5] is None else int(row[5]),
                                       ts_max_raw=None if row[6] is None else int(row[6]))
            for src, checks in raw_checks.items():
                require(checks['null_fields'] == 0, f'{src}: events with NULL fields: {checks}')
                require(checks['unknown_types'] == 0, f'{src}: events with an unknown type: {checks}')
                require(checks['lines'] == checks['distinct_sessions'], f'{src}: repeated session lines: {checks}')
                require(checks['ts_min_raw'] is not None, f'{src}: no events')
            ts_min = min(c['ts_min_raw'] for c in raw_checks.values())
            ts_max = max(c['ts_max_raw'] for c in raw_checks.values())
            if ts_min >= MS_FLOOR:
                unit, divisor = 'ms', 1000
            elif ts_max < S_CEIL:
                unit, divisor = 's', 1
            else:
                raise oc.ContractError(f'Mixed ts units: min {ts_min}, max {ts_max} (§1)')
            require(raw_checks['train']['ts_max_raw'] < raw_checks['test']['ts_min_raw'],
                    f"max(ts train) {raw_checks['train']['ts_max_raw']} >= min(ts test) "
                    f"{raw_checks['test']['ts_min_raw']} in source units (§1)")
            ts_expr = f'ts // {divisor}' if divisor != 1 else 'ts'
            s5 = int(raw_checks['test']['ts_min_raw']) // divisor
            for src in ('train', 'test'):
                con.execute(f"""CREATE TABLE {src}_ev AS SELECT session, aid, ts, type, seq,
                    {oc.partition_sql('ts', s5, src)} AS d
                    FROM (SELECT session, aid, CAST({ts_expr} AS BIGINT) AS ts, type, seq FROM {src}_raw
                          WHERE NOT empty)""")
                con.execute(f'DROP TABLE {src}_raw')
            require(int(_scalar(con, 'SELECT min(ts) FROM test_ev')) == s5, 'S5 is the minimum test ts')
            t0 = time.monotonic()
            facts, checks = _load_facts(con, s5, raw_checks)
            timings['facts'] = round(time.monotonic()-t0, 1)
            parts = {}
            for src in ('train', 'test'):
                for d, n, lo, hi in con.execute(f'SELECT d, count(*), min(ts), max(ts) FROM {src}_ev '
                                                f'GROUP BY d ORDER BY d').fetchall():
                    parts[int(d)] = dict(source=src, rows=int(n), ts_min=int(lo), ts_max=int(hi))
            week_failures = _partition_week_failures(parts, s5)
            require(not week_failures, f'Partitions cross a week boundary: {week_failures[:5]}')
            t0 = time.monotonic()
            for src in ('train', 'test'):
                _write_partitions(con, f'{src}_ev', src, s5, written)
            timings['partitions'] = round(time.monotonic()-t0, 1)
            require(sorted(written) == sorted(parts), 'Written partitions differ from the counts')
        finally:
            con.close()
    except BaseException:
        for d in written:                                  # a failed load leaves no partition behind
            shutil.rmtree(oc.events_path(d), ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    partitions = []
    for d in sorted(parts):
        directory = oc.events_path(d)
        hashes = {p.name: oc.sha256_file(p) for p in sorted(directory.glob('*.parquet'))}
        partitions.append(dict(d=d, week=oc.week_of_day(d), **parts[d], files=hashes))
    failures = list(checks['failures'])
    if check_contract:
        failures += _readme_failures(facts)
    gate0 = dict(ok=not failures, failures=failures, readme_checked=bool(check_contract),
                 readme=README_FACTS, tolerance=README_TOLERANCE)
    timings['total'] = round(time.monotonic()-started, 1)
    body = dict(format=LOAD_FORMAT, checked=bool(check_contract), files=files, ts_unit=unit, ts_divisor=divisor,
                s5=s5, facts=facts, checks={k: v for k, v in checks.items() if k != 'failures'}, gate0=gate0,
                partitions=partitions, limits=dict(threads=int(threads), memory=memory, max_temp=max_temp),
                timings=timings, peak_rss_mb=_peak_rss_mb(), code=code, created_utc=oc.utc_now())
    receipt = dict(body, digest=oc.canonical_digest(body))
    oc.atomic_json(receipt_path, receipt)
    require(gate0['ok'] or not check_contract, f'Gate 0 failed (receipt written): {failures}')
    return receipt


def _load_facts(con, s5, raw_checks):
    """Schema facts and gate-0 checks of the normalized events (§1, §2.1, §2.3, §5.7, §8)."""
    facts = dict(s5=s5)
    train = _length_facts(con, 'train_ev')
    test = _length_facts(con, 'test_ev')
    facts.update({f'train_{k}': v for k, v in train.items()})
    facts.update({f'test_{k}': v for k, v in test.items()})
    facts['train_events'] = int(_scalar(con, 'SELECT count(*) FROM train_ev'))
    facts['test_events'] = int(_scalar(con, 'SELECT count(*) FROM test_ev'))
    facts.update(_type_counts(con, 'train_ev', 'train'))
    facts.update(_type_counts(con, 'test_ev', 'test'))
    facts['train_aids'] = int(_scalar(con, 'SELECT count(DISTINCT aid) FROM train_ev'))
    facts['test_aids'] = int(_scalar(con, 'SELECT count(DISTINCT aid) FROM test_ev'))
    facts['train_ts_min'], facts['train_ts_max'] = (int(x) for x in con.execute(
        'SELECT min(ts), max(ts) FROM train_ev').fetchone())
    facts['test_ts_min'], facts['test_ts_max'] = (int(x) for x in con.execute(
        'SELECT min(ts), max(ts) FROM test_ev').fetchone())
    facts['train_session_min'], facts['train_session_max'] = (int(x) for x in con.execute(
        'SELECT min(session), max(session) FROM train_ev').fetchone())
    facts['test_session_min'], facts['test_session_max'] = (int(x) for x in con.execute(
        'SELECT min(session), max(session) FROM test_ev').fetchone())
    facts['test_ids_after_train'] = facts['test_session_min'] > facts['train_session_max']
    facts['kaggle_week_seconds'] = facts['test_ts_max'] - s5 + 1
    facts['kaggle_week_is_7_days'] = facts['test_ts_max'] - s5 < 7*oc.DAY and facts['test_ts_max'] - s5 >= 6*oc.DAY
    facts.update({f'test_{k}': v for k, v in _session_shares(con, 'test_ev').items()})
    early = int(_scalar(con, f'SELECT count(*) FROM train_ev WHERE ts < {s5 - 28*oc.DAY}'))
    facts['train_events_before_w1'] = early
    facts['train_share_before_w1'] = early/facts['train_events'] if facts['train_events'] else 0.0
    facts['train_events_at_s5'] = int(_scalar(con, f'SELECT count(*) FROM train_ev WHERE ts >= {s5}'))
    missing = int(_scalar(con, 'SELECT count(*) FROM (SELECT DISTINCT aid FROM test_ev) t '
                               'WHERE NOT EXISTS (SELECT 1 FROM train_ev e WHERE e.aid = t.aid)'))
    overlap = int(_scalar(con, 'SELECT count(*) FROM (SELECT DISTINCT session FROM test_ev) t '
                               'WHERE EXISTS (SELECT 1 FROM train_ev e WHERE e.session = t.session)'))
    after_s5 = int(_scalar(con, f'SELECT count(*) FROM train_ev WHERE ts > {s5}'))
    # Σn²(I_k) upper bounds and raw Q_k sizes (§5.7, §12): per train session, events per week and first week.
    week = week_sql(oc.partition_sql('ts', s5, 'train'))
    con.execute(f"""CREATE TEMP TABLE sw AS SELECT session, min(w) AS fw,
        count(*) FILTER (WHERE w = 1) AS n1, count(*) FILTER (WHERE w = 2) AS n2,
        count(*) FILTER (WHERE w = 3) AS n3, count(*) FILTER (WHERE w = 4) AS n4
        FROM (SELECT session, {week} AS w FROM train_ev) GROUP BY session""")
    sum_n2, q_sizes = {}, {}
    for k in (2, 3, 4):
        before = ' + '.join(f'n{w}' for w in range(1, k))
        sum_n2[f'F{k}'] = int(_scalar(con, f"""SELECT coalesce(sum(CASE WHEN fw < {k} THEN ({before})*({before})
            WHEN fw = {k} THEN n{k}*n{k} ELSE 0 END), 0)::HUGEINT FROM sw"""))
    for k in (1, 2, 3, 4):
        q_sizes[f'W{k}'] = int(_scalar(con, f'SELECT count(*) FROM sw WHERE fw = {k}'))
    q_sizes['W5'] = facts['test_sessions']
    sum_n2['F5'] = int(_scalar(con, """SELECT (SELECT coalesce(sum((n1+n2+n3+n4)*(n1+n2+n3+n4)), 0) FROM sw)::HUGEINT
        + (SELECT coalesce(sum(n*n), 0) FROM (SELECT count(*) AS n FROM test_ev GROUP BY session))::HUGEINT"""))
    facts['sum_n2_upper'] = sum_n2
    facts['q_sessions_raw'] = q_sizes
    checks = dict(raw=raw_checks, test_aids_missing_in_train=missing, test_train_session_overlap=overlap,
                  train_events_after_s5=after_s5, test_empty_sessions=raw_checks['test']['empty_sessions'],
                  train_empty_sessions=raw_checks['train']['empty_sessions'])
    failures = []
    if missing:
        failures.append(f'{missing} test aids are not in train')
    if overlap:
        failures.append(f'{overlap} test sessions are also train sessions')
    if after_s5:
        failures.append(f'{after_s5} train events after S5')
    if raw_checks['test']['empty_sessions'] or raw_checks['train']['empty_sessions']:
        failures.append('sessions without events')
    if facts['train_share_before_w1'] > EARLY_SHARE_MAX:
        failures.append(f"share of train events before S5 - 28 d is {facts['train_share_before_w1']:.6f} > "
                        f'{EARLY_SHARE_MAX}')
    checks['failures'] = failures
    return facts, checks


def _partition_week_failures(parts, s5):
    """Each day partition holds only ts of its own day, hence of one week (§2.5).

    Train d = -1 also holds a train event with ts = S5 (§1, decision 21).
    """
    failures = []
    for d, part in parts.items():
        lo, hi = s5 + d*oc.DAY, s5 + (d+1)*oc.DAY
        if part['source'] == 'train':
            ok = d <= -1 and lo <= part['ts_min'] and part['ts_max'] < (s5 + 1 if d == -1 else hi)
        else:
            ok = d >= 0 and lo <= part['ts_min'] and part['ts_max'] < hi
        if not ok:
            failures.append(d)
    return failures


def _require_unchecked_outside(checked):
    """An unchecked load (checked:false) is a smoke or test load: never under this repository's ROOT."""
    require(checked or oc.ROOT.resolve() != ROOT.resolve(), 'unchecked load only outside the repo')


def read_load():
    """The load receipt after format and digest checks; gate 0 must have passed.

    A receipt with checked:false (contract sizes and README not compared) is refused under
    this repository's ROOT, so a smoke receipt can never feed a collection here.
    """
    receipt = oc.read_json(oc.verify_path())
    require(receipt.get('format') == LOAD_FORMAT, 'Not an OTTO load receipt')
    body = {k: v for k, v in receipt.items() if k != 'digest'}
    require(oc.canonical_digest(body) == receipt.get('digest'), 'Load receipt digest mismatch')
    require(isinstance(receipt.get('checked'), bool), 'Load receipt without checked')
    _require_unchecked_outside(receipt['checked'])
    require(receipt['gate0']['ok'] or not receipt['checked'], f"Gate 0 failed: {receipt['gate0']['failures']}")
    return receipt


def s5():
    return int(read_load()['s5'])


# =============================================================================== weeks, history and views (§2, §5.3)

def fold_days(k):
    """(history days, fold days) of F_k from the partitions on disk; F5 folds the test days."""
    k = int(k)
    require(k in (2, 3, 4, 5), f'Unknown fold F{k}')
    train = oc.existing_days('train')
    require(train, 'Run load first')
    first = oc.week_first_day(k)
    history_days = [d for d in train if d < first]
    if k == oc.KAGGLE_WEEK:
        return history_days, oc.existing_days('test')
    lo, hi = oc.week_days(k)
    return history_days, [d for d in train if lo <= d <= hi]


def history(k, purpose, threads=4, memory=MEMORY_LIMIT):
    """In-memory DuckDB with the view ``hist`` (EVENT_COLUMNS) of H_k only; the caller closes it.

    H_k is exactly the partitions d < start(W_k) (§2.2, §2.5); F5 needs purpose 'final'.
    The spill directory is created by DuckDB on demand and removed when the caller closes.
    """
    require(isinstance(purpose, str) and purpose.strip(), 'A purpose is required')
    days, _ = fold_days(k)
    files = _partition_files(days, purpose)
    con = connect(threads, memory, temp=_spill_dir())
    try:
        con.execute(f'CREATE VIEW hist AS {_events_select(files)}')
    except BaseException:
        con.close()
        raise
    return con


def _neutral_select(files):
    names = ' '.join(f'WHEN {code} THEN {_literal(name)}' for code, name in enumerate(NEUTRAL_EVENTS))
    return (f'SELECT session, aid AS item, ts, CASE type {names} END AS event, seq '
            f'FROM read_parquet({_list_literal(files)}, hive_partitioning=false)')


VIEW_SCHEMA = [['session', 'BIGINT'], ['item', 'BIGINT'], ['ts', 'BIGINT'], ['event', 'VARCHAR'],
               ['seq', 'INTEGER']]


def views(k, purpose, collection=None):
    """Agent views of F_k (§5.3): ``hist`` over the H_k partitions, ``sess`` over the fold prefixes.

    ``sess`` comes only from ``<collection>/prefix/`` (F2 train-F2, F3 val-F3, F4 the
    holdout collection after collect-holdout); at F5 from the test partitions.
    Returns allowed directories, files, SELECT texts with neutral names and schemas.
    """
    k = int(k)
    days, fold = fold_days(k)
    hist_files = _partition_files(days, purpose)
    if k == oc.KAGGLE_WEEK:
        sess_files = _partition_files(fold, purpose)
        sess_dirs = sorted(str(Path(f).parent) for f in sess_files)
    else:
        if collection is None:
            collection = oc.collection_dir({2: 'train', 3: 'val', 4: 'holdout'}[k])
        collection = Path(collection)
        manifest = oc.read_collection(collection, verify=True)
        require(manifest['fold'] == k, f'{collection.name} is not a collection of F{k}')
        prefix = collection/oc.PREFIX_DIR
        sess_files = sorted(str(p) for p in prefix.rglob('*.parquet'))
        require(sess_files, f'{prefix} holds no prefix partitions')
        sess_dirs = [str(prefix)]
    s5_ = s5()
    return dict(fold=k, start=oc.week_start(k, s5_), end=oc.week_end(k, s5_),
                directories=dict(hist=sorted({str(Path(f).parent) for f in hist_files}), sess=sess_dirs),
                files=dict(hist=hist_files, sess=sess_files),
                views=dict(hist=_neutral_select(hist_files), sess=_neutral_select(sess_files)),
                schema=dict(hist=VIEW_SCHEMA, sess=VIEW_SCHEMA, cand=[['session', 'BIGINT'], ['item', 'BIGINT']],
                            sessions=[['session', 'BIGINT']]),
                events=dict(zip(NEUTRAL_EVENTS, TYPE_NAMES)))


# =============================================================================== folds and truncation (§2.2)

def fold_files(k, purpose):
    """(H_k files, W_k files) of F_k after the barrier: the barrier is checked here, when resolved."""
    hist_days, days = fold_days(k)
    return _partition_files(hist_days, purpose), _partition_files(days, purpose)


def build_fold(con, k, purpose, s5_, files=None):
    """Create in ``con``: view ``hist`` (H_k), table ``fold`` (session, aid, ts, type, seq, pos, n, c) and
    table ``labels`` (session, type, aid). Returns label-free counts.

    F_k, k = 2..4: sessions whose first event lies in W_k (no event in H_k), events of W_k only
    (later partitions are not read), aid filter against H_k and sessions of < 2 events dropped
    before the cut; prefix = pos <= c in seq order. F5: every test session, c = n, no labels.
    ``files``: the result of ``fold_files(k, purpose)`` resolved earlier (collect-holdout resolves
    the W4 files while the window is open, then creates the collection, which closes it, then reads).
    """
    k = int(k)
    hist_files, week_files = fold_files(k, purpose) if files is None else files
    con.execute(f'CREATE OR REPLACE VIEW hist AS {_events_select(hist_files)}')
    week = _events_select(week_files)
    counts = {}
    if k == oc.KAGGLE_WEEK:
        con.execute(f"""CREATE TEMP TABLE fold AS SELECT *, n AS c FROM (SELECT *,
            row_number() OVER (PARTITION BY session ORDER BY seq) AS pos,
            count(*) OVER (PARTITION BY session) AS n FROM ({week}))""")
        con.execute('CREATE TEMP TABLE labels (session BIGINT, type VARCHAR, aid BIGINT)')
        counts['sessions'] = int(_scalar(con, 'SELECT count(DISTINCT session) FROM fold'))
        counts['prefix_events'] = int(_scalar(con, 'SELECT count(*) FROM fold'))
        return counts
    con.execute('CREATE TEMP TABLE h_sessions AS SELECT DISTINCT session FROM hist')
    con.execute('CREATE TEMP TABLE h_aids AS SELECT DISTINCT aid FROM hist')
    con.execute(f"""CREATE TEMP TABLE q_raw AS SELECT w.* FROM ({week}) w
        WHERE NOT EXISTS (SELECT 1 FROM h_sessions h WHERE h.session = w.session)""")
    counts['q_sessions_raw'] = int(_scalar(con, 'SELECT count(DISTINCT session) FROM q_raw'))
    counts['q_events_raw'] = int(_scalar(con, 'SELECT count(*) FROM q_raw'))
    con.execute("""CREATE TEMP TABLE q_f AS SELECT q.* FROM q_raw q
        WHERE EXISTS (SELECT 1 FROM h_aids a WHERE a.aid = q.aid)""")
    counts['dropped_aid_events'] = counts['q_events_raw'] - int(_scalar(con, 'SELECT count(*) FROM q_f'))
    after_filter = int(_scalar(con, 'SELECT count(DISTINCT session) FROM q_f'))
    # c is computed once per session (sha256 per session, not per event), then joined to the events
    con.execute(f"""CREATE TEMP TABLE cuts AS SELECT session, n, {cut_sql('session', 'n', con)} AS c
        FROM (SELECT session, count(*) AS n FROM q_f GROUP BY session HAVING count(*) >= 2)""")
    con.execute("""CREATE TEMP TABLE fold AS SELECT q.session, q.aid, q.ts, q.type, q.seq,
            row_number() OVER (PARTITION BY q.session ORDER BY q.seq) AS pos, x.n, x.c
        FROM q_f q JOIN cuts x USING (session)""")
    con.execute('DROP TABLE cuts')
    con.execute('DROP TABLE q_raw')
    con.execute('DROP TABLE q_f')
    counts['sessions'] = int(_scalar(con, 'SELECT count(DISTINCT session) FROM fold'))
    counts['dropped_short_sessions'] = after_filter - counts['sessions']
    counts['dropped_empty_sessions'] = counts['q_sessions_raw'] - after_filter
    counts['prefix_events'] = int(_scalar(con, 'SELECT count(*) FROM fold WHERE pos <= c'))
    counts['fold_events'] = int(_scalar(con, 'SELECT count(*) FROM fold'))
    con.execute(f"""CREATE TEMP TABLE labels AS
        SELECT session, 'clicks' AS type, arg_min(aid, pos) AS aid FROM fold WHERE pos > c AND type = 0
            GROUP BY session
        UNION ALL SELECT DISTINCT session, 'carts', aid FROM fold WHERE pos > c AND type = 1
        UNION ALL SELECT DISTINCT session, 'orders', aid FROM fold WHERE pos > c AND type = 2""")
    # gate 0 on the fold (§8): prefix >= 1, suffix >= 1, labels only known aids
    bad = con.execute("""SELECT count(*) FILTER (WHERE c < 1 OR c > n - 1), count(*) FILTER (WHERE n < 2)
        FROM (SELECT DISTINCT session, n, c FROM fold)""").fetchone()
    require(bad == (0, 0), f'F{k}: a cut outside [1, n - 1] or a short session: {bad}')
    unknown = int(_scalar(con, 'SELECT count(*) FROM labels l WHERE NOT EXISTS '
                               '(SELECT 1 FROM h_aids a WHERE a.aid = l.aid)'))
    require(unknown == 0, f'F{k}: {unknown} labels with an aid unknown to H_{k}')
    return counts


def _fold_purpose(role):
    return oc.COLLECT_HOLDOUT if role == 'holdout' else ('final' if role == 'kaggle' else f'collect-{role}')


# =============================================================================== base B (§4)

def initial_base():
    """otto-base-v1 of §4 (candidate policy and the 21 features)."""
    features = [dict(name=n, formula=f, missing=m) for n, f, m in BASE_FEATURES]
    return oc.make_base(CANDIDATE_POLICY, features)


def _policy(base):
    policy = base['candidates']
    history_depth = int(policy['history']['depth'])
    pop_depth = int(policy['popular']['depth'])
    limit = int(policy['max'])
    require(list(policy['popular']['types']) == list(TYPE_NAMES), 'p_t covers clicks, carts, orders in order')
    require(list(policy['union']) == CANDIDATE_POLICY['union'], 'Union order is (h), p_clicks, p_carts, p_orders')
    require(1 <= history_depth and 1 <= pop_depth and 1 <= limit, 'Depths must be positive')
    return history_depth, pop_depth, limit


def _feature_sql(name, item_windows):
    fixed = {
        's_len': 's.s_len', 's_items': 's.s_items', 's_carts': 's.s_carts', 's_orders': 's.s_orders',
        's_dur': 's.s_dur',
        'p_clicks': 'coalesce(pa.p_clicks, 0)', 'p_carts': 'coalesce(pa.p_carts, 0)',
        'p_orders': 'coalesce(pa.p_orders, 0)',
        'p_last_pos': 'CASE WHEN hh.h_rank IS NOT NULL THEN s.c - pa.lp + 1 END',
        'p_last_age': 'CASE WHEN hh.h_rank IS NOT NULL THEN s.last_ts - pa.lts END',
        'p_is_last': 'CASE WHEN c.aid = s.last_aid THEN 1 ELSE 0 END',
        'h_rank': 'hh.h_rank',
        'pop_rank_clicks': 'p0.rnk', 'pop_rank_carts': 'p1.rnk', 'pop_rank_orders': 'p2.rnk',
        'i_wk_clicks': 'coalesce(iw.i_wk_clicks, 0)', 'i_wk_carts': 'coalesce(iw.i_wk_carts, 0)',
        'i_wk_orders': 'coalesce(iw.i_wk_orders, 0)',
    }
    if name in fixed:
        return fixed[name]
    match = ITEM_WINDOW.fullmatch(name)
    require(match is not None, f'Unknown base feature {name!r}: add its formula to otto_data first')
    days = int(match.group(1))
    require(1 <= days <= ITEM_WINDOW_MAX_DAYS, f'{name}: item windows of B are 1..{ITEM_WINDOW_MAX_DAYS} days')
    item_windows.add((days, match.group(2)))
    return f'coalesce(ih.{name}, 0)'


def _item_history_sql(windows, start):
    if not windows:
        return None
    longest = max(days for days, _ in windows)
    parts = []
    for days, kind in sorted(windows):
        lo = start - days*oc.DAY
        if kind == 'all':
            parts.append(f'count(*) FILTER (WHERE ts >= {lo}) AS i_h{days}_all')
        else:
            parts.append(f'count(DISTINCT session) FILTER (WHERE ts >= {lo} AND type = {oc.TYPE_CODES[kind]}) '
                         f'AS i_h{days}_{kind}')
    # lower bound only: H_k is bounded above by its partitions (a train event at ts = S5 is in H_5)
    return f'SELECT aid, {", ".join(parts)} FROM hist WHERE ts >= {start - longest*oc.DAY} GROUP BY aid'


RANK_FEATURES = ('h_rank', 'p_last_pos', 'pop_rank_clicks', 'pop_rank_carts', 'pop_rank_orders')


def _feature_type(name):
    """Narrow storage types of the frame (§12 memory): ranks USMALLINT, the flag UTINYINT, the rest INTEGER.

    A checked CAST: a value outside the type fails the collection instead of wrapping.
    """
    if name in RANK_FEATURES:
        return 'USMALLINT'
    if name == 'p_is_last':
        return 'UTINYINT'
    return 'INTEGER'


def _batches(con, sessions_table, batch):
    """(lo, hi) of consecutive runs of ``batch`` sessions in ascending order; [(0, -1)] when empty."""
    require(int(batch) >= 1, 'batch >= 1')
    rows = con.execute(f"""SELECT min(session), max(session) FROM (SELECT session,
            (row_number() OVER (ORDER BY session) - 1) // {int(batch)} AS b FROM {sessions_table})
        GROUP BY b ORDER BY b""").fetchall()
    return [(int(lo), int(hi)) for lo, hi in rows] or [(0, -1)]


def build_frame(con, k, base, s5_, sessions_table='frame_sessions', batch=FRAME_BATCH, out=None):
    """Candidates and features of B for the sessions of ``sessions_table`` (§4) as parquet parts.

    Needs ``hist`` and ``fold`` from ``build_fold``. Only prefixes (pos <= c) and H_k are read.
    Each batch of ``batch`` consecutive sessions goes straight to ``out/part-<i>.parquet``,
    sorted by (session, aid) inside the batch; batches are increasing session ranges, so the
    parts in order are the frame in global order without a global sort. Columns: session, aid,
    base features in base order, then source ranks not among them.
    Returns dict(columns, parts).
    """
    require(out is not None, 'build_frame writes parquet parts into a directory')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    history_depth, pop_depth, limit = _policy(base)
    names = oc.base_feature_names(base)
    windows = set()
    exprs = [(n, _feature_sql(n, windows)) for n in names]
    exprs += [(n, _feature_sql(n, windows)) for n in SOURCE_COLUMNS if n not in names]
    start = oc.week_start(k, s5_)
    con.execute('CREATE OR REPLACE TEMP VIEW pfx AS SELECT session, aid, ts, type, seq, pos FROM fold WHERE pos <= c')
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pt AS SELECT type, aid, rnk FROM (
        SELECT type, aid, row_number() OVER (PARTITION BY type ORDER BY ns DESC, aid) AS rnk
        FROM (SELECT type, aid, count(DISTINCT session) AS ns FROM pfx GROUP BY type, aid))
        WHERE rnk <= {pop_depth}""")
    con.execute("""CREATE OR REPLACE TEMP TABLE item_wk AS SELECT aid,
        count(DISTINCT session) FILTER (WHERE type = 0) AS i_wk_clicks,
        count(DISTINCT session) FILTER (WHERE type = 1) AS i_wk_carts,
        count(DISTINCT session) FILTER (WHERE type = 2) AS i_wk_orders FROM pfx GROUP BY aid""")
    item_h = _item_history_sql(windows, start)
    con.execute(f'CREATE OR REPLACE TEMP TABLE item_h AS {item_h}' if item_h else
                'CREATE OR REPLACE TEMP TABLE item_h AS SELECT CAST(NULL AS BIGINT) AS aid WHERE false')
    select = ',\n               '.join(f'CAST({sql} AS {_feature_type(name)}) AS {name}' for name, sql in exprs)
    parts = []
    for index, (lo, hi) in enumerate(_batches(con, sessions_table, batch)):
        con.execute(f"""CREATE OR REPLACE TEMP TABLE bs AS SELECT session FROM {sessions_table}
            WHERE session BETWEEN {lo} AND {hi}""")
        query = f"""
        WITH p AS (SELECT x.* FROM pfx x SEMI JOIN bs USING (session) WHERE x.session BETWEEN {lo} AND {hi}),
        s AS (SELECT session, count(*) AS s_len, count(DISTINCT aid) AS s_items,
                     count(*) FILTER (WHERE type = 1) AS s_carts, count(*) FILTER (WHERE type = 2) AS s_orders,
                     arg_max(ts, pos) - arg_min(ts, pos) AS s_dur, max(pos) AS c,
                     arg_max(aid, pos) AS last_aid, arg_max(ts, pos) AS last_ts
              FROM p GROUP BY session),
        pa AS (SELECT session, aid, count(*) FILTER (WHERE type = 0) AS p_clicks,
                      count(*) FILTER (WHERE type = 1) AS p_carts, count(*) FILTER (WHERE type = 2) AS p_orders,
                      max(pos) AS lp, arg_max(ts, pos) AS lts
               FROM p GROUP BY session, aid),
        hh AS (SELECT session, aid, h_rank FROM (SELECT session, aid,
                      row_number() OVER (PARTITION BY session ORDER BY lp DESC, aid) AS h_rank FROM pa)
               WHERE h_rank <= {history_depth}),
        u AS (SELECT session, aid, h_rank AS r, 0 AS src FROM hh
              UNION ALL SELECT bs.session, pt.aid, pt.rnk, pt.type + 1 FROM bs CROSS JOIN pt),
        k AS (SELECT session, aid, min(src * 1000000 + r) AS key FROM u GROUP BY session, aid),
        c AS (SELECT session, aid FROM (SELECT session, aid,
                     row_number() OVER (PARTITION BY session ORDER BY key, aid) AS ord FROM k)
              WHERE ord <= {limit})
        SELECT c.session, c.aid,
               {select}
        FROM c JOIN s USING (session)
             LEFT JOIN pa USING (session, aid)
             LEFT JOIN hh USING (session, aid)
             LEFT JOIN pt p0 ON p0.type = 0 AND p0.aid = c.aid
             LEFT JOIN pt p1 ON p1.type = 1 AND p1.aid = c.aid
             LEFT JOIN pt p2 ON p2.type = 2 AND p2.aid = c.aid
             LEFT JOIN item_wk iw ON iw.aid = c.aid
             LEFT JOIN item_h ih ON ih.aid = c.aid
        ORDER BY c.session, c.aid"""
        part = out/f'part-{index:05d}.parquet'
        con.execute(f'COPY ({query}) TO {_literal(part)} (FORMAT parquet, COMPRESSION zstd)')
        parts.append(part)
    con.execute('DROP TABLE IF EXISTS bs')
    return dict(columns=[name for name, _ in exprs], parts=parts)


def _concat_parts(con, parts, target):
    """One parquet file from the parts in their order: a streaming COPY with insertion order kept."""
    con.execute('SET preserve_insertion_order=true')
    try:
        con.execute(f"""COPY (SELECT * FROM read_parquet({_list_literal([str(p) for p in parts])},
            hive_partitioning=false)) TO {_literal(target)} (FORMAT parquet, COMPRESSION zstd)""")
    finally:
        con.execute('SET preserve_insertion_order=false')
    for part in parts:
        Path(part).unlink()
    return Path(target)


def _frame_counts(con, path):
    row = con.execute(f"""SELECT count(*), sum(n), max(n), min(n) FROM (SELECT session, count(*) AS n
        FROM read_parquet({_literal(path)}) GROUP BY session)""").fetchone()
    sessions, rows = int(row[0]), int(row[1] or 0)
    return dict(frame_rows=rows, frame_sessions_with_candidates=sessions,
                candidates_max=int(row[2] or 0), candidates_min=int(row[3] or 0),
                candidates_mean=round(rows/sessions, 3) if sessions else 0.0)


# =============================================================================== sessions of a collection

def _ordered(con, source, salt_sql, n=None, exclude=None):
    where = f'WHERE session NOT IN (SELECT session FROM {exclude})' if exclude else ''
    limit = f'LIMIT {int(n)}' if n is not None else ''
    return [int(s) for (s,) in con.execute(
        f"""SELECT session FROM (SELECT DISTINCT session FROM {source}) {where}
            ORDER BY {salt_sql.format(column='session')}, session {limit}""").fetchall()]


def training_sessions(labels, n=oc.N_T, threads=4, memory=MEMORY_LIMIT):
    """First n sessions with a label of each type in sha256 order (§6); labels: frame or parquet path."""
    spill = _spill_dir()
    try:
        con = connect(threads, memory, temp=spill)
        try:
            if isinstance(labels, (str, Path)):
                con.execute(f'CREATE TEMP VIEW lab AS SELECT * FROM read_parquet({_literal(labels)})')
            else:
                con.register('lab', labels)
            return _training_from(con, 'lab', n)
        finally:
            con.close()
    finally:
        shutil.rmtree(spill, ignore_errors=True)


def _training_from(con, table, n):
    out = {}
    for t in TYPE_NAMES:
        con.execute(f"CREATE OR REPLACE TEMP TABLE lt AS SELECT DISTINCT session FROM {table} WHERE type = '{t}'")
        out[t] = _ordered(con, 'lt', oc.ORDER_SQL, n)
    con.execute('DROP TABLE IF EXISTS lt')
    return out


def _register_sessions(con, name, sessions):
    pd = _pd()
    con.register(f'{name}_input', pd.DataFrame({'session': sorted({int(s) for s in sessions})}, dtype='int64'))
    con.execute(f'CREATE OR REPLACE TEMP TABLE {name} AS SELECT session FROM {name}_input')
    con.unregister(f'{name}_input')


# =============================================================================== collect (§2.2, §2.4, §4, §11)

def collect(role, base, output=None, threads=THREADS, memory=MEMORY_LIMIT, n_train=oc.N_T,
            dev_population=oc.DEV_POPULATION, probe_pool=oc.PROBE_POOL, batch=FRAME_BATCH):
    """Build the collection of ``role`` (train F2, val F3, probe F3, kaggle F5) into a new directory.

    Frame sessions: train — the union of the first ``n_train`` labelled sessions per type
    (§6); val — the dev population (first ``dev_population`` of Q_3 outside the probe pool)
    plus that union; probe — the pool (first ``probe_pool`` of Q_3 in probe order);
    kaggle — every test session. ``prefix/`` holds the prefixes of every session of the fold.
    The holdout goes through ``collect_holdout`` only.
    """
    require(role in ('train', 'val', 'probe', 'kaggle'), f'collect builds train, val, probe or kaggle, not {role!r}')
    return _collect(role, base, output, threads, memory, n_train, dev_population, probe_pool, batch)


def collect_holdout(base=None, threads=THREADS, memory=MEMORY_LIMIT, batch=FRAME_BATCH):
    """collect-holdout (§2.5): opens W4 once after prereg; every session of Q_4, labels sealed.

    The base is the committed otto-base.json whose SHA the prereg names (checked by the window);
    the code must match the prereg (require_prereg(check_code=True)).
    """
    oc.require_window(oc.COLLECT_HOLDOUT)
    oc.require_prereg(check_code=True)
    committed = oc.read_base()
    if base is not None:
        require(base.get('digest') == committed['digest'], 'collect-holdout uses the committed base only')
    return _collect('holdout', committed, None, threads, memory, None, None, None, batch)


def _frame_sessions(con, role, counts, extra, n_train, dev_population, probe_pool):
    """Table frame_sessions of the role; returns (training, population)."""
    training = population = None
    if role in ('kaggle', 'holdout'):
        con.execute('CREATE TEMP TABLE frame_sessions AS SELECT DISTINCT session FROM fold')
    elif role == 'probe':
        pool = _ordered(con, 'fold', oc.PROBE_ORDER_SQL, probe_pool)
        _register_sessions(con, 'frame_sessions', pool)
        con.execute('DELETE FROM labels WHERE session NOT IN (SELECT session FROM frame_sessions)')
        extra['pool_digest'] = oc.canonical_digest(pool)
        extra['pool_size'] = len(pool)
    else:
        training = _training_from(con, 'labels', n_train)
        frame_sessions = set().union(*training.values())
        if role == 'val':
            pool = _ordered(con, 'fold', oc.PROBE_ORDER_SQL, probe_pool)
            _register_sessions(con, 'pool', pool)
            population = _ordered(con, 'fold', oc.ORDER_SQL, dev_population, exclude='pool')
            frame_sessions |= set(population)
            extra['probe_pool_digest'] = oc.canonical_digest(pool)
        _register_sessions(con, 'frame_sessions', frame_sessions)
        extra['training_sessions'] = {t: len(v) for t, v in training.items()}
        extra['training_digest'] = oc.canonical_digest(training)
    return training, population


def _collect(role, base, output, threads, memory, n_train, dev_population, probe_pool, batch):
    started = time.monotonic()
    oc.check_base(base)
    load_receipt = read_load()
    s5_ = int(load_receipt['s5'])
    k = oc.ROLE_FOLD[role]
    purpose = _fold_purpose(role)
    if role == 'holdout':
        oc.require_window(oc.COLLECT_HOLDOUT)
        oc.require_prereg(check_code=True)
        target = oc.current_holdout_collection()
        require(output is None or Path(output).resolve() == target.resolve(),
                'The holdout collection goes only to the current holdout collection path')
    elif role == 'kaggle':
        oc.require_window('final')
        oc.require_prereg(check_code=True)
        target = Path(output) if output is not None else oc.collection_dir(role)
    else:
        target = Path(output) if output is not None else oc.collection_dir(role)
    require(not target.exists(), f'{target} exists; a collection goes to a new directory')
    code = oc.code_identity(strict=True) if role in ('holdout', 'kaggle') else _code()
    files = fold_files(k, purpose)               # the barrier: W4 globs resolve only while the window is open
    if role == 'holdout':
        target = oc.new_output(target)           # the window closes before W4 is read: a crash keeps it closed
        require(not oc.holdout_window_open(oc.COLLECT_HOLDOUT), 'The holdout directory did not close the window')
    oc.artifacts_dir().mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.frame-', dir=oc.artifacts_dir()))
    spill = _spill_dir()
    try:
        con = connect(threads, memory, temp=spill)
        try:
            counts = build_fold(con, k, purpose, s5_, files=files)
            extra = dict(fold_rule='§2.2', s5=s5_, start=oc.week_start(k, s5_), end=oc.week_end(k, s5_),
                         load_digest=load_receipt['digest'])
            training, population = _frame_sessions(con, role, counts, extra, n_train, dev_population, probe_pool)
            t0 = time.monotonic()
            built = build_frame(con, k, base, s5_, 'frame_sessions', batch, out=work)
            frame_seconds = round(time.monotonic()-t0, 1)
            if role != 'holdout':
                target = oc.new_output(target)
            if role != 'kaggle':
                d_sql = oc.partition_sql('ts', s5_, 'train')
                con.execute(f"""COPY (SELECT {', '.join(oc.EVENT_COLUMNS)}, {d_sql} AS d FROM fold WHERE pos <= c)
                    TO {_literal(target/oc.PREFIX_DIR)} (FORMAT parquet, PARTITION_BY (d), COMPRESSION zstd)""")
            _concat_parts(con, built['parts'], target/oc.FRAME_FILE)
            frame = _frame_counts(con, target/oc.FRAME_FILE)
            fs = int(_scalar(con, 'SELECT count(*) FROM frame_sessions'))
            require(frame.pop('frame_sessions_with_candidates') == fs, 'Frame sessions without candidates')
            counts.update(frame, frame_sessions=fs)
            label_sql = 'SELECT session, type, aid FROM labels ORDER BY session, type, aid'
            sealed = None
            if role in ('train', 'val', 'probe'):
                con.execute(f'COPY ({label_sql}) TO {_literal(target/oc.LABELS_FILE)} (FORMAT parquet)')
                for t, n in con.execute('SELECT type, count(*) FROM labels GROUP BY type ORDER BY type').fetchall():
                    counts[f'labels_{t}'] = int(n)
                counts['labelled_sessions'] = int(_scalar(con, 'SELECT count(DISTINCT session) FROM labels'))
            elif role == 'holdout':
                def writer(directory):
                    con.execute(f'COPY ({label_sql}) TO {_literal(Path(directory)/oc.LABELS_FILE)} (FORMAT parquet)')
                sealed = oc.write_sealed(target, writer)
        finally:
            con.close()
    finally:
        shutil.rmtree(spill, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
    extra.update(columns=built['columns'], features=oc.base_feature_names(base), sources=list(SOURCE_COLUMNS),
                 frame_seconds=frame_seconds, seconds=round(time.monotonic()-started, 1), peak_rss_mb=_peak_rss_mb(),
                 limits=dict(threads=int(threads), memory=memory, batch=int(batch)))
    if role == 'holdout':
        for key in HOLDOUT_SUFFIX_COUNTS:
            counts.pop(key, None)                # with prefix_events they would give the suffix size
        extra = {key: value for key, value in extra.items()
                 if not any(w in key.lower() for w in oc.HOLDOUT_FORBIDDEN_WORDS)}
    manifest = oc.write_manifest(target, role, counts, base, code, sealed=sealed, extra=extra)
    if role == 'val':
        oc.write_population(target, population,
                            rule=f'first {dev_population} sessions of Q_3 in sha256 order outside the probe pool')
    return dict(manifest, path=str(target))


HOLDOUT_SUFFIX_COUNTS = ('fold_events', 'q_events_raw', 'dropped_aid_events')


# =============================================================================== frame rehearsal (§12)

def rehearse_frame(k=3, base=None, threads=THREADS, memory=MEMORY_LIMIT, max_temp=MAX_TEMP, batch=FRAME_BATCH,
                   keep=False):
    """The B frame over every session of Q_k (k = 2, 3: open folds) into a scratch directory.

    Measures what F4 (all of Q_4) and F5 (all test sessions) will need: wall time per step,
    peak RSS of the process, peak size of the spill directory and of the frame. Nothing is
    written to collections; the scratch directory is deleted unless ``keep``.
    """
    k = int(k)
    require(k in (2, 3), 'rehearse-frame runs on the open folds F2 and F3')
    base = initial_base() if base is None else base
    oc.check_base(base)
    load_receipt = read_load()
    s5_ = int(load_receipt['s5'])
    started = time.monotonic()
    oc.artifacts_dir().mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.rehearse-', dir=oc.artifacts_dir()))
    spill = _spill_dir()
    seconds = {}
    try:
        with _PeakBytes(spill) as peak_spill, _PeakBytes(work) as peak_work:
            con = connect(threads, memory, temp=spill, max_temp=max_temp)
            try:
                t0 = time.monotonic()
                counts = build_fold(con, k, f'rehearse-F{k}', s5_)
                con.execute('CREATE TEMP TABLE frame_sessions AS SELECT DISTINCT session FROM fold')
                seconds['fold'] = round(time.monotonic()-t0, 1)
                rss_fold = _peak_rss_mb()
                t0 = time.monotonic()
                built = build_frame(con, k, base, s5_, 'frame_sessions', batch, out=work/'parts')
                seconds['frame'] = round(time.monotonic()-t0, 1)
                t0 = time.monotonic()
                frame_path = _concat_parts(con, built['parts'], work/oc.FRAME_FILE)
                seconds['concat'] = round(time.monotonic()-t0, 1)
                frame = _frame_counts(con, frame_path)
                frame_bytes = frame_path.stat().st_size
            finally:
                con.close()
    finally:
        shutil.rmtree(spill, ignore_errors=True)
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
    seconds['total'] = round(time.monotonic()-started, 1)
    q = load_receipt['facts'].get('q_sessions_raw', {})
    per_session = frame['frame_rows']/frame['frame_sessions_with_candidates'] if frame['frame_rows'] else 0.0
    return dict(fold=k, sessions=counts['sessions'], prefix_events=counts['prefix_events'], **frame,
                frame_bytes=frame_bytes, columns=len(built['columns']), batches=len(built['parts']),
                seconds=seconds, peak_rss_mb=_peak_rss_mb(), peak_rss_after_fold_mb=rss_fold,
                peak_spill_mb=round(peak_spill.peak/2**20, 1), peak_scratch_mb=round(peak_work.peak/2**20, 1),
                limits=dict(threads=int(threads), memory=memory, max_temp=max_temp, batch=int(batch)),
                projected_rows=dict(F4=round(per_session*q.get('W4', 0)), F5=round(per_session*q.get('W5', 0))),
                kept=str(work) if keep else None)


# =============================================================================== Pop (§4)

def pop(frame, output=None, k=oc.TOP_K, threads=4, memory=MEMORY_LIMIT):
    """Pop lists from the source ranks of a frame: (h) by h_rank, then p_t without repeats, first k.

    ``frame``: a pandas frame or a parquet path with session, aid and SOURCE_COLUMNS.
    Without ``output``: a pandas frame ``session, type, aid, rank`` ordered by session, type
    order, rank (small frames). With ``output``: written there by COPY (no pandas), returns
    dict(path, rows).
    """
    spill = _spill_dir()
    try:
        con = connect(threads, memory, temp=spill)
        try:
            if isinstance(frame, (str, Path)):
                con.execute(f'CREATE TEMP VIEW f AS SELECT session, aid, {", ".join(SOURCE_COLUMNS)} '
                            f'FROM read_parquet({_literal(frame)})')
            else:
                con.register('f', frame[['session', 'aid', *SOURCE_COLUMNS]])
            parts = []
            for code, t in enumerate(TYPE_NAMES):
                parts.append(f"""SELECT session, '{t}' AS type, {code} AS tc, aid,
                    CASE WHEN h_rank IS NOT NULL THEN 0 ELSE 1 END AS grp, coalesce(h_rank, pop_rank_{t}) AS r
                    FROM f WHERE h_rank IS NOT NULL OR pop_rank_{t} IS NOT NULL""")
            query = f"""SELECT CAST(session AS BIGINT) AS session, type, CAST(aid AS BIGINT) AS aid,
                    CAST(rank AS BIGINT) AS rank FROM (
                SELECT session, type, tc, aid, row_number() OVER (PARTITION BY session, type ORDER BY grp, r, aid)
                    AS rank FROM ({' UNION ALL '.join(parts)}))
                WHERE rank <= {int(k)} ORDER BY session, tc, rank"""
            if output is None:
                return con.execute(query).df()
            output = Path(output)
            require(not output.exists(), f'{output} exists')
            con.execute(f'COPY ({query}) TO {_literal(output)} (FORMAT parquet, COMPRESSION zstd)')
            rows = int(_scalar(con, f'SELECT count(*) FROM read_parquet({_literal(output)})'))
            return dict(path=str(output), rows=rows)
        finally:
            con.close()
    finally:
        shutil.rmtree(spill, ignore_errors=True)


# =============================================================================== assemble (§3, §9)

def check_submission(path, sessions, known, sample_rows=None):
    """Re-read a submission: header, 3 rows per session in the given set, 20 distinct known aids each."""
    path = Path(path)
    sessions = {int(s) for s in sessions}
    known = known if isinstance(known, (set, frozenset)) else {int(a) for a in known}
    seen = {}
    rows = 0
    with path.open('r', encoding='utf-8', newline='') as stream:
        header = stream.readline()
        require(header == oc.SUBMISSION_HEADER + '\n', f'Header must be {oc.SUBMISSION_HEADER!r} with LF')
        for number, line in enumerate(stream, start=2):
            require(line.endswith('\n') and not line.endswith('\r\n'), f'Line {number}: LF line ends only')
            key, sep, value = line[:-1].partition(',')
            require(sep == ',', f'Line {number}: no comma')
            session, _, kind = key.partition('_')
            require(session.isdigit() and kind in TYPE_NAMES, f'Line {number}: bad session_type {key!r}')
            session = int(session)
            require(session in sessions, f'Line {number}: session {session} is not a test session')
            require(kind not in seen.setdefault(session, set()), f'Line {number}: repeated {key}')
            seen[session].add(kind)
            aids = value.split(' ')
            require(len(aids) == oc.TOP_K, f'Line {number}: {len(aids)} aids, need {oc.TOP_K}')
            require(all(a.isdigit() for a in aids), f'Line {number}: a non-integer aid')
            values = [int(a) for a in aids]
            require(len(set(values)) == oc.TOP_K, f'Line {number}: repeated aid')
            unknown = [a for a in values if a not in known]
            require(not unknown, f'Line {number}: unknown aids {unknown[:3]}')
            rows += 1
    missing = sessions - set(seen)
    require(not missing, f'{len(missing)} test sessions missing, e.g. {sorted(missing)[:3]}')
    short = [s for s, kinds in seen.items() if len(kinds) != len(TYPE_NAMES)]
    require(not short, f'{len(short)} sessions without all three rows')
    require(rows == len(TYPE_NAMES)*len(sessions), f'{rows} rows for {len(sessions)} sessions')
    if sample_rows is not None:
        require(rows == int(sample_rows), f'{rows} rows, sample_submission has {sample_rows}')
    return dict(rows=rows, sessions=len(sessions))


def assemble(ranked, output, sessions, known, fill, sample_rows=None, threads=4, memory=MEMORY_LIMIT):
    """Kaggle file from ranked lists (session, type, aid, rank; up to 20 per list), topped up from ``fill``
    (Pop lists of the same shape) without repeats; writes ``.part``, re-reads, renames; receipt ``.json``.

    ``ranked`` and ``fill``: parquet paths (or small pandas frames). Needs the committed prereg
    whose code matches the tree; the receipt carries code_identity(strict=True).
    """
    output = Path(output)
    receipt_path = output.with_suffix('.json')
    oc.require_prereg(check_code=True)
    code = oc.code_identity(strict=True)
    require(not output.exists() and not receipt_path.exists(), f'{output} or its receipt exists')
    part = output.with_name(output.name + '.part')
    require(not part.exists(), f'{part} exists')
    spill = _spill_dir()
    try:
        con = connect(threads, memory, temp=spill)
        try:
            for name, value in (('m', ranked), ('fl', fill)):
                if isinstance(value, (str, Path)):
                    con.execute(f'CREATE TEMP VIEW {name}_in AS SELECT * FROM read_parquet({_literal(value)})')
                else:
                    con.register(f'{name}_in', value)
                con.execute(f"""CREATE TEMP TABLE {name} AS SELECT CAST(session AS BIGINT) AS session,
                    CAST(type AS VARCHAR) AS type, CAST(aid AS BIGINT) AS aid, CAST(rank AS BIGINT) AS rank
                    FROM {name}_in""")
            bad = _scalar(con, f"""SELECT count(*) FROM m WHERE rank < 1 OR rank > {oc.TOP_K}
                OR type NOT IN ({', '.join(_literal(t) for t in TYPE_NAMES)})""")
            require(bad == 0, f'ranked: {bad} rows with an unknown type or a rank outside 1..{oc.TOP_K}')
            for key in ('aid', 'rank'):
                dup = _scalar(con, f'SELECT count(*) FROM (SELECT session, type, {key} FROM m GROUP BY ALL '
                                   f'HAVING count(*) > 1)')
                require(dup == 0, f'ranked: repeated {key} within a list ({dup})')
            _register_sessions(con, 'ts_', sessions)
            con.execute(f"""CREATE TEMP TABLE pairs AS SELECT s.session, t.type, t.tc FROM ts_ s CROSS JOIN
                (SELECT * FROM (VALUES {', '.join(f"('{t}', {c})" for c, t in enumerate(TYPE_NAMES))}) v(type, tc)) t""")
            con.execute(f"""CREATE TEMP TABLE merged AS
                WITH a AS (SELECT session, type, aid, rank AS key FROM m SEMI JOIN ts_ USING (session)
                           UNION ALL
                           SELECT f.session, f.type, f.aid, 1000 + f.rank FROM fl f SEMI JOIN ts_ USING (session)
                           WHERE NOT EXISTS (SELECT 1 FROM m WHERE m.session = f.session AND m.type = f.type
                                                               AND m.aid = f.aid)),
                     b AS (SELECT session, type, aid, min(key) AS key FROM a GROUP BY ALL)
                SELECT session, type, aid, key FROM (SELECT *, row_number() OVER (PARTITION BY session, type
                    ORDER BY key, aid) AS r FROM b) WHERE r <= {oc.TOP_K}""")
            filled = int(_scalar(con, f"""SELECT count(DISTINCT p.session) FROM pairs p LEFT JOIN
                (SELECT session, type, count(*) AS n FROM m GROUP BY ALL) x USING (session, type)
                WHERE coalesce(x.n, 0) < {oc.TOP_K}"""))
            try:
                with part.open('w', encoding='utf-8', newline='\n') as stream:
                    stream.write(oc.SUBMISSION_HEADER + '\n')
                    result = con.execute("""SELECT p.session, p.type,
                            string_agg(CAST(x.aid AS VARCHAR), ' ' ORDER BY x.key, x.aid)
                        FROM pairs p LEFT JOIN merged x USING (session, type) GROUP BY p.session, p.type, p.tc
                        ORDER BY p.session, p.tc""")
                    while rows := result.fetchmany(FETCH_ROWS):
                        stream.writelines(f'{session}_{kind},{aids or ""}\n' for session, kind, aids in rows)
            except BaseException:
                part.unlink(missing_ok=True)
                raise
        finally:
            con.close()
    finally:
        shutil.rmtree(spill, ignore_errors=True)
    try:
        checked = check_submission(part, sessions, known, sample_rows=sample_rows)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    os.replace(part, output)
    body = dict(format=ASSEMBLE_FORMAT, file=output.name, sha256=oc.sha256_file(output), bytes=output.stat().st_size,
                rows=checked['rows'], sessions=checked['sessions'], filled_sessions=filled, code=code,
                created_utc=oc.utc_now())
    oc.atomic_json(receipt_path, body)
    return body


def kaggle_targets(threads=4, memory=MEMORY_LIMIT):
    """Sessions, known aids and the row count of the Kaggle file after the F5 checks (§3, §9).

    The kaggle frame, the test partitions and sample_submission.csv (same SHA-256 as in the load
    receipt) must name the same set of sessions, with exactly one row per session and type in the
    sample. Known aids are the aids of H_5 (every train partition).
    """
    receipt = read_load()
    collection = oc.collection_dir('kaggle')
    oc.read_collection(collection, role='kaggle')
    frame = collection/oc.FRAME_FILE
    sample = oc.raw_dir()/SAMPLE_CSV
    expected = receipt['files'][SAMPLE_CSV]['sha256']
    require(oc.sha256_file(sample) == expected, f'{SAMPLE_CSV} differs from the load receipt')
    train_days, test_days = fold_days(oc.KAGGLE_WEEK)
    spill = _spill_dir()
    try:
        con = connect(threads, memory, temp=spill)
        try:
            sessions = {int(s) for (s,) in con.execute(
                f'SELECT DISTINCT session FROM read_parquet({_literal(frame)})').fetchall()}
            test_sessions = {int(s) for (s,) in con.execute(
                f'SELECT DISTINCT session FROM ({_events_select(_partition_files(test_days, "final"))})').fetchall()}
            require(sessions == test_sessions, 'The kaggle frame does not cover exactly the test sessions')
            con.execute(f"""CREATE TEMP TABLE sample AS SELECT session_type,
                    TRY_CAST(split_part(session_type, '_', 1) AS BIGINT) AS session,
                    split_part(session_type, '_', 2) AS type
                FROM read_csv({_literal(sample)}, header=true, delim=',', quote='', escape='',
                              columns={{'session_type': 'VARCHAR', 'labels': 'VARCHAR'}})""")
            rows, keys, bad = con.execute(f"""SELECT count(*), count(DISTINCT session_type),
                count(*) FILTER (WHERE session IS NULL OR type NOT IN ({', '.join(_literal(t) for t in TYPE_NAMES)})
                                 OR session_type != CAST(session AS VARCHAR) || '_' || type)
                FROM sample""").fetchone()
            require(bad == 0, f'{SAMPLE_CSV}: {bad} rows with a bad session_type')
            require(rows == keys, f'{SAMPLE_CSV}: repeated session_type rows')
            sample_sessions = {int(s) for (s,) in con.execute('SELECT DISTINCT session FROM sample').fetchall()}
            require(rows == len(TYPE_NAMES)*len(sample_sessions), f'{SAMPLE_CSV}: not three rows per session')
            require(sample_sessions == test_sessions,
                    f'{SAMPLE_CSV} sessions differ from the test sessions: '
                    f'{len(sample_sessions - test_sessions)} extra, {len(test_sessions - sample_sessions)} missing')
            known = {int(a) for (a,) in con.execute(
                f'SELECT DISTINCT aid FROM ({_events_select(_partition_files(train_days, "final"))})').fetchall()}
        finally:
            con.close()
    finally:
        shutil.rmtree(spill, ignore_errors=True)
    return dict(sessions=sorted(sessions), known=known, sample_rows=int(rows), frame=frame)


# =============================================================================== descriptive fold statistics (§2.3)

def fold_stats(k, threads=4, memory='4GB'):
    """Label-free description of F2 or F3 against test (gate 0, §2.3): prefix lengths and shares."""
    k = int(k)
    require(k in (2, 3), 'fold-stats describes F2 and F3 only (F4 is behind the barrier)')
    receipt = read_load()
    spill = _spill_dir()
    try:
        con = connect(threads, memory, temp=spill)
        try:
            counts = build_fold(con, k, f'fold-stats-F{k}', int(receipt['s5']))
            con.execute('CREATE TEMP VIEW pfx AS SELECT * FROM fold WHERE pos <= c')
            lengths = _length_facts(con, 'pfx')
            shares = _session_shares(con, 'pfx')
        finally:
            con.close()
    finally:
        shutil.rmtree(spill, ignore_errors=True)
    counts = {key: v for key, v in counts.items()}
    test = {key[5:]: receipt['facts'][key] for key in receipt['facts']
            if key.startswith('test_len') or key.startswith('test_share') or key == 'test_sessions'}
    return dict(fold=k, counts=counts, prefix=dict(lengths, **shares), test=test)


# =============================================================================== CLI

def _handler(argv):
    oc.isolated()
    parser = argparse.ArgumentParser(prog='otto_data.py')
    commands = parser.add_subparsers(dest='command', required=True)
    names = ('load', 'collect', 'collect-holdout', 'pop', 'assemble', 'fold-stats', 'rehearse-frame', 'init-base')
    for name in names:
        sub = commands.add_parser(name)
        if name in ('load', 'collect', 'collect-holdout', 'fold-stats', 'rehearse-frame'):
            sub.add_argument('--threads', type=int, default=THREADS if name != 'fold-stats' else 4)
            sub.add_argument('--memory', default=MEMORY_LIMIT if name != 'fold-stats' else '4GB')
        if name in ('collect', 'collect-holdout', 'rehearse-frame'):
            sub.add_argument('--batch', type=int, default=FRAME_BATCH)
        if name == 'collect':
            sub.add_argument('--role', required=True, choices=['train', 'val', 'probe', 'kaggle'])
            sub.add_argument('--base', default=None, help='otto-base JSON (default: configs/datasets/otto-base.json)')
        if name == 'pop':
            sub.add_argument('--collection', required=True)
            sub.add_argument('--output', required=True)
        if name == 'assemble':
            sub.add_argument('--ranked', required=True)
            sub.add_argument('--output', required=True)
        if name == 'fold-stats':
            sub.add_argument('--fold', type=int, required=True, choices=[2, 3])
        if name == 'rehearse-frame':
            sub.add_argument('--fold', type=int, default=3, choices=[2, 3])
            sub.add_argument('--max-temp', default=MAX_TEMP)
            sub.add_argument('--base', default=None, help='otto-base JSON (default: the initial base B of §4)')
            sub.add_argument('--keep', action='store_true', help='keep the scratch frame under artifacts/otto')
        if name == 'init-base':
            sub.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if args.command == 'load':
        receipt = load(threads=args.threads, memory=args.memory)
        return dict(command='load', receipt=str(oc.verify_path()), s5=receipt['s5'], ts_unit=receipt['ts_unit'],
                    partitions=len(receipt['partitions']), gate0=receipt['gate0']['ok'], timings=receipt['timings'],
                    peak_rss_mb=_peak_rss_mb(), digest=receipt['digest'])
    if args.command == 'collect':
        base = oc.read_base(args.base)
        manifest = collect(args.role, base, threads=args.threads, memory=args.memory, batch=args.batch)
        return dict(command='collect', role=args.role, path=manifest['path'], counts=manifest['counts'],
                    peak_rss_mb=_peak_rss_mb())
    if args.command == 'collect-holdout':
        manifest = collect_holdout(threads=args.threads, memory=args.memory, batch=args.batch)
        return dict(command='collect-holdout', path=manifest['path'], counts=manifest['counts'],
                    peak_rss_mb=_peak_rss_mb())
    if args.command == 'rehearse-frame':
        base = oc.read_base(args.base) if args.base else None
        return dict(command='rehearse-frame', **rehearse_frame(args.fold, base, threads=args.threads,
                                                               memory=args.memory, max_temp=args.max_temp,
                                                               batch=args.batch, keep=args.keep))
    if args.command == 'pop':
        collection = Path(args.collection)
        manifest = oc.read_collection(collection)
        output = Path(args.output)
        require(not output.exists(), f'{output} exists')
        require(output.resolve().is_relative_to(oc.artifacts_dir().resolve()), 'Pop lists go under artifacts/otto')
        output.parent.mkdir(parents=True, exist_ok=True)
        written = pop(collection/oc.FRAME_FILE, output)
        return dict(command='pop', role=manifest['role'], output=written['path'], rows=written['rows'])
    if args.command == 'assemble':
        output = Path(args.output)
        require(output.resolve().is_relative_to(oc.output_dir('kaggle').resolve()), 'Kaggle files go under kaggle/')
        targets = kaggle_targets()
        work = Path(tempfile.mkdtemp(prefix='.assemble-', dir=oc.artifacts_dir()))
        try:
            fill = pop(targets['frame'], work/'pop.parquet')
            output.parent.mkdir(parents=True, exist_ok=True)
            body = assemble(args.ranked, output, targets['sessions'], targets['known'], fill['path'],
                            sample_rows=targets['sample_rows'])
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return dict(command='assemble', **body)
    if args.command == 'fold-stats':
        return dict(command='fold-stats', **fold_stats(args.fold, threads=args.threads, memory=args.memory))
    output = Path(args.output)
    require(output.resolve() != oc.config_path('base').resolve() or not output.exists(), f'{output} exists')
    base = initial_base()
    oc.atomic_json(output, base)
    return dict(command='init-base', output=str(output), digest=base['digest'])


def main(argv=None):
    return oc.run_cli(_handler, argv)


if __name__ == '__main__':
    sys.exit(main())
