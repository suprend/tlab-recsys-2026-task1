"""Sandbox for extra features written as SQL (by a human or by the agent).

A feature query runs once per anchor day t and may read only two tables:
  hist          events strictly before t (event_time, event_type, product_id, category_id,
                category_code, brand, price, user_id, user_session)
  active_users  user_id of everyone with an event in [t-48h, t); use it only to make
                user-level or pair-level queries cheaper
The placeholder {t} is the anchor timestamp literal, e.g. TIMESTAMP '{t}' - INTERVAL 3 DAY.
The query returns key columns (user_id and/or product_id) plus value columns named f_x_*,
one row per key. Values are stored as DOUBLE; only keys present in the day's candidates are kept.

Isolation by construction: the query runs in its own DuckDB connection that holds only `hist` and
`active_users`. `hist` is a view over the day files of EVENTS (events partitioned by date, written once
from the database by `export_events`) for the days before t; no database is attached, external access
is off except for exactly those day directories, and the configuration is locked. Events at or after t,
labels, queries and candidates are therefore unreachable; candidate keys are applied afterwards in a
second connection that reads them from the day table. FORBIDDEN is a second layer.

Run test days for accepted features: .venv/bin/python -m task1.extra NAME [NAME ...] --splits test
"""
import argparse
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import duckdb

from task1.build import DB
from task1.model import EXTRA, ROOT, days as split_days

DAYS = ROOT / 'artifacts/task1/v2/days6'
EVENTS = ROOT / 'artifacts/task1/v2/events_by_day'
FORBIDDEN = re.compile(
    r'\b(rees46|fs|src|labels|queries|candidates|n_targets|events|pair_first|item_static|item_brand_day|'
    r'read_\w+|parquet_\w+|json_\w+|pragma_\w+|\w*_execute\w*|glob|getenv|query|query_table|duckdb_\w+|'
    r'information_schema|pg_catalog|sqlite_master|'
    r'attach|detach|copy|export|import|install|load|pragma|set|reset|use|call|create|drop|insert|update|delete|alter)\b',
    re.I)
TIMEOUT_S = 120
MEMORY = '8GB'


class FeatureError(ValueError):
    pass


def check_sql(sql):
    body = sql.replace('{t}', '')
    hit = FORBIDDEN.search(body)
    if hit:
        raise FeatureError(f'query references a forbidden table or command: {hit.group(0)}')
    if ';' in body.strip().rstrip(';'):
        raise FeatureError('only one statement is allowed')


COLUMNS = 'event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session'


def export_events(out=EVENTS):
    """Write the events of the database as one directory of parquet files per date (d=YYYY-MM-DD)."""
    con = duckdb.connect()
    con.execute("SET threads=6; SET preserve_insertion_order=false")
    con.execute(f"ATTACH '{DB}' AS r (READ_ONLY)")
    con.execute(f"""COPY (SELECT {COLUMNS}, event_time::DATE d FROM r.events) TO '{out}'
                    (FORMAT PARQUET, PARTITION_BY (d), OVERWRITE_OR_IGNORE)""")
    con.close()


def sandbox(t, threads=8):
    """A connection that knows only `hist` (events before t, from the day files) and `active_users`."""
    day = t[:10]
    dirs = sorted(p for p in EVENTS.glob('d=*') if p.name[2:] < day)
    files = [str(f) for p in dirs for f in sorted(p.glob('*.parquet'))]
    if not files:
        raise FeatureError(f'no event files before {day} in {EVENTS}')
    con = duckdb.connect()
    con.execute(f"SET threads={threads}; SET memory_limit='{MEMORY}'")
    con.execute(f"SET temp_directory='{tempfile.mkdtemp(prefix='tlab-sbx-')}'")  # else <cwd>/.tmp is allowed
    con.execute(f"SET allowed_directories={[str(p) + '/' for p in dirs]}")
    con.execute(f"""CREATE VIEW hist AS SELECT {COLUMNS} FROM read_parquet({files}, hive_partitioning=false)
                    WHERE event_time < TIMESTAMP '{t}'""")
    con.execute(f"""CREATE TABLE active_users AS SELECT DISTINCT user_id FROM hist
                    WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 48 HOUR""")
    con.execute("SET enable_external_access=false; SET lock_configuration=true")
    return con


def run_query(con, sql, t):
    """Execute the feature query inside a sandbox connection; returns (keys, values, DataFrame)."""
    timer = threading.Timer(TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        con.execute(f"CREATE TEMP TABLE _x AS {sql.strip().rstrip(';').replace('{t}', t)}")
    except Exception as e:
        raise FeatureError(f'{type(e).__name__} on {t[:10]}: {str(e)[:400]}') from None
    finally:
        timer.cancel()
    names = [r[0] for r in con.execute("DESCRIBE _x").fetchall()]
    keys = [c for c in ('user_id', 'product_id') if c in names]
    values = [c for c in names if c.startswith('f_x_')]
    if not keys or not values or len(keys) + len(values) != len(names):
        raise FeatureError(f'expected user_id/product_id keys plus f_x_* columns, got {names}')
    k = ', '.join(keys)
    nulls, dup = con.execute(f"""SELECT count(*) FILTER ({' OR '.join(f'{c} IS NULL' for c in keys)}),
                                 count(*) - count(DISTINCT ({k})) FROM _x""").fetchone()
    if nulls or dup:
        raise FeatureError(f'{nulls} NULL and {dup} duplicate keys on {t[:10]}')
    return keys, values, con.execute("SELECT * FROM _x").df()


def compute(name, sql, splits=('train', 'val'), threads=8, days=None, days_dir=DAYS):
    """Materialise feature `name` for every day of the given splits (or the explicit `days`);
    returns its value columns. Output: EXTRA/name/<day>.parquet with keys BIGINT and values DOUBLE."""
    check_sql(sql)
    out = EXTRA / name
    out.mkdir(parents=True, exist_ok=True)
    (out / 'feature.sql').write_text(sql.strip() + '\n')
    cols = None
    for d in sorted(days or {d for s in splits for d in split_days(s)}):
        cand = Path(days_dir) / f'{d}.parquet'
        if not cand.exists():
            raise FeatureError(f'no day table {cand}')
        t = datetime.combine(d, datetime.min.time()).isoformat(sep=' ')
        con = sandbox(t, threads)
        try:
            keys, values, x = run_query(con, sql, t)
        finally:
            con.close()
        if cols and values != cols:
            raise FeatureError(f'columns differ between days: {values} vs {cols}')
        w = duckdb.connect()
        w.execute(f"SET threads={threads}")
        w.register('x', x)
        k = ', '.join(keys)
        sel = ', '.join([f'{c}::BIGINT {c}' for c in keys] + [f'TRY_CAST({c} AS DOUBLE) {c}' for c in values])
        bad = w.execute(f"SELECT count(*) FROM x WHERE {' OR '.join(f'({c} IS NOT NULL AND TRY_CAST({c} AS DOUBLE) IS NULL)' for c in values)}").fetchone()[0]
        if bad:
            raise FeatureError(f'{bad} values are not numeric on {d}')
        tmp = out / f'.{d}.parquet'
        w.execute(f"""COPY (SELECT {sel} FROM x SEMI JOIN (SELECT DISTINCT {k} FROM read_parquet('{cand}')) c USING({k})
                       ORDER BY {k}) TO '{tmp}' (FORMAT PARQUET)""")
        w.close()
        tmp.rename(out / f'{d}.parquet')
        cols = values
    return cols


def main():
    ap = argparse.ArgumentParser(description='Compute saved features (EXTRA/NAME/feature.sql) for more days.')
    ap.add_argument('names', nargs='+')
    ap.add_argument('--splits', nargs='+', default=['test'])
    ap.add_argument('--days-dir', default=str(DAYS))
    ap.add_argument('--threads', type=int, default=8)
    args = ap.parse_args()
    for name in args.names:
        t0 = time.time()
        cols = compute(name, (EXTRA / name / 'feature.sql').read_text(), args.splits, args.threads, days_dir=args.days_dir)
        print(name, cols, f'{time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
