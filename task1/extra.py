"""Sandbox for extra features written as SQL (by a human or by the agent).

A feature query runs once per anchor day t and may read only two tables:
  hist          events strictly before t (event_time, event_type, product_id, category_id,
                category_code, brand, price, user_id, user_session)
  active_users  user_id of everyone with an event in [t-48h, t); use it only to make
                user-level or pair-level queries cheaper
The placeholder {t} is the anchor timestamp literal, e.g. TIMESTAMP '{t}' - INTERVAL 3 DAY.
The query returns key columns (user_id and/or product_id) plus value columns named f_x_*,
one row per key. The sandbox then keeps only the keys that are scored at t.

Neither table depends on the future: the ranked users (tomorrow's buyers), candidates and
labels are not reachable from the query, so a feature cannot learn who buys tomorrow.
"""
import re
import threading
from datetime import datetime

from task1.build import connect, set_anchor
from task1.model import EXTRA, days

FORBIDDEN = re.compile(r'\b(src|labels|queries|candidates|popular|recent|n_targets|events|'
                       r'read_parquet|read_csv|read_json|attach|copy|install|load|pragma|set)\b', re.I)
TIMEOUT_S = 120


class FeatureError(ValueError):
    pass


def check_sql(sql):
    body = sql.replace('{t}', '')
    hit = FORBIDDEN.search(body)
    if hit:
        raise FeatureError(f'query references a forbidden table or command: {hit.group(0)}')
    if ';' in body.strip().rstrip(';'):
        raise FeatureError('only one statement is allowed')


def compute(name, sql, splits=('refit', 'test'), con=None, threads=8):
    """Materialise feature `name` for every day of the given splits; returns its column names."""
    check_sql(sql)
    con = con or connect(threads)
    out = EXTRA / name
    out.mkdir(parents=True, exist_ok=True)
    cols = None
    for d in sorted({d for s in splits for d in days(s)}):
        t = datetime.combine(d, datetime.min.time()).isoformat(sep=' ')
        set_anchor(con, t)
        con.execute(f"""CREATE OR REPLACE TEMP TABLE active_users AS SELECT DISTINCT user_id FROM hist
                        WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 48 HOUR""")
        timer = threading.Timer(TIMEOUT_S, con.interrupt)
        timer.start()
        try:
            con.execute(f"CREATE OR REPLACE TEMP TABLE _x AS {sql.strip().rstrip(';').replace('{t}', t)}")
        except Exception as e:
            raise FeatureError(f'{type(e).__name__} on {d}: {str(e)[:400]}') from None
        finally:
            timer.cancel()
        names = [r[0] for r in con.execute("DESCRIBE _x").fetchall()]
        keys = [c for c in ('user_id', 'product_id') if c in names]
        values = [c for c in names if c.startswith('f_x_')]
        if not keys or len(keys) + len(values) != len(names) or not values:
            raise FeatureError(f'expected user_id/product_id keys plus f_x_* columns, got {names}')
        if cols and values != cols:
            raise FeatureError('columns differ between days')
        dup = con.execute(f"SELECT count(*) - count(DISTINCT ({','.join(keys)})) FROM _x").fetchone()[0]
        if dup:
            raise FeatureError(f'{dup} duplicate keys on {d}')
        con.execute(f"""COPY (SELECT x.* FROM _x x SEMI JOIN (SELECT DISTINCT {','.join(keys)} FROM candidates) c
                        USING({','.join(keys)})) TO '{out / f'{d}.parquet'}' (FORMAT PARQUET)""")
        cols = values
    (out / 'feature.sql').write_text(sql.strip() + '\n')
    return cols
