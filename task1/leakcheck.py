"""Leak test: features built from a database cut at the anchor must equal features from the full one.

For anchor t it writes a database with only the events before t (plus the derived tables, rebuilt by
task1.data.derive), builds the day twice — features from the full database and from the cut one, labels
and queries always from the full one — and compares every column row by row.

Run: .venv/bin/python -m task1.leakcheck 2019-10-22 [2019-11-20 ...]
"""
import sys
import tempfile
from datetime import date
from pathlib import Path

import duckdb

from task1 import build
from task1.data import derive


def cut_db(t, path):
    con = duckdb.connect(str(path))
    con.execute("SET threads=10; SET memory_limit='20GB'")
    con.execute(f"ATTACH '{build.DB}' AS src (READ_ONLY)")
    con.execute(f"CREATE TABLE events AS SELECT * FROM src.events WHERE event_time < TIMESTAMP '{t}'")
    derive(con)
    con.close()


def check(day, tmp):
    t = f'{day.isoformat()} 00:00:00'
    db = tmp / f'cut-{day}.duckdb'
    cut_db(t, db)
    full = build.build_day(build.connect(), day, out=tmp / 'full')
    cut = build.build_day(build.connect(features_db=db), day, out=tmp / 'cut')
    con = duckdb.connect()
    a = con.execute(f"SELECT * FROM '{tmp}/full/{day}.parquet' ORDER BY user_id, product_id").df()
    b = con.execute(f"SELECT * FROM '{tmp}/cut/{day}.parquet' ORDER BY user_id, product_id").df()
    bad = []
    if a.shape != b.shape or list(a.columns) != list(b.columns):
        bad.append(f'shape {a.shape} vs {b.shape}')
    else:
        for c in a.columns:
            x, y = a[c], b[c]
            if x.dtype.kind == 'f' or y.dtype.kind == 'f':
                x, y = x.astype(float), y.astype(float)
                diff = ~(((x - y).abs() <= 1e-9 * (1 + x.abs())) | (x.isna() & y.isna()))
            else:
                diff = ~((x == y) | (x.isna() & y.isna()))
            if diff.any():
                bad.append(f'{c}: {int(diff.sum())} rows differ')
    print(day, 'rows full', full['pairs'], 'cut', cut['pairs'], 'OK' if not bad else 'LEAK: ' + '; '.join(bad))
    return not bad


def main():
    days = [date.fromisoformat(d) for d in sys.argv[1:]]
    with tempfile.TemporaryDirectory(prefix='tlab-leak-') as d:
        ok = all([check(day, Path(d)) for day in days])
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
