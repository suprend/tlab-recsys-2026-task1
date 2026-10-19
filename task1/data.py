"""Import REES46 October + November 2019 into one DuckDB for task 1 (new-item target).

Tables:
  events          all events of both months, exact duplicate rows removed, ordered by event_time
  pair_first      (user_id, product_id, first_ts, first_cp_ts) over the whole data; consumers must read it
                  only as of t: rows with first_ts < t, and first_cp_ts treated as NULL unless < t
  item_static     product_id -> category_id of its first event and the top-level part of the first
                  category_code seen for that category (as-of safe: fixed once the product appears)
  item_brand_day  last non-null brand of a product within each UTC day; brand as of t is the latest
                  day before t
  ingest_metadata source files and their SHA-256

Run: .venv/bin/python -m task1.data
"""
import hashlib
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
DB = ROOT / 'data/processed/rees46.duckdb'
MONTHS = ['2019-Oct', '2019-Nov']
SCHEMA = {
    'event_time': 'TIMESTAMP', 'event_type': 'VARCHAR', 'product_id': 'BIGINT',
    'category_id': 'BIGINT', 'category_code': 'VARCHAR', 'brand': 'VARCHAR',
    'price': 'DECIMAL(12,2)', 'user_id': 'BIGINT', 'user_session': 'VARCHAR',
}


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def derive(con):
    """Create pair_first, item_static and item_brand_day from `events` (also used by task1.leakcheck)."""
    con.execute("""CREATE TABLE pair_first AS SELECT user_id, product_id, min(event_time) first_ts,
        min(event_time) FILTER (event_type IN ('cart','purchase')) first_cp_ts
        FROM events GROUP BY ALL ORDER BY first_ts""")
    con.execute("""CREATE TABLE item_static AS
        WITH c AS (SELECT category_id, arg_min(category_code, (event_time, category_code)) FILTER (category_code IS NOT NULL) code
                   FROM events GROUP BY 1)
        SELECT p.product_id, p.category_id, nullif(split_part(c.code, '.', 1), '') l1
        FROM (SELECT product_id, arg_min(category_id, (event_time, category_id)) category_id FROM events GROUP BY 1) p
        LEFT JOIN c USING(category_id)""")
    con.execute("""CREATE TABLE item_brand_day AS SELECT product_id, event_time::DATE d, arg_max(brand, event_time) brand
        FROM events WHERE brand IS NOT NULL GROUP BY 1, 2""")


def main():
    if DB.exists():
        raise SystemExit(f'{DB} exists; remove it explicitly to rebuild')
    sources = []
    for m in MONTHS:
        path = RAW / f'{m}.csv.gz'
        manifest = json.loads((RAW / f'{m}.download.json').read_text())
        digest = sha256(path)
        if digest != manifest['sha256'] or path.stat().st_size != manifest['compressed_bytes']:
            raise SystemExit(f'{path} does not match {m}.download.json')
        sources.append((m, str(path), digest, manifest['source']))
        print(m, 'verified', digest, flush=True)

    tmp = ROOT / 'data/tmp/duckdb'
    tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("SET threads=10; SET memory_limit='24GB'")
    con.execute(f"SET temp_directory='{tmp}'")
    schema = '{' + ','.join(f"'{k}':'{v}'" for k, v in SCHEMA.items()) + '}'
    files = '[' + ','.join(f"'{s[1]}'" for s in sources) + ']'
    con.execute(f"""CREATE TABLE events AS SELECT DISTINCT * FROM read_csv({files}, columns={schema}, header=true,
        timestampformat='%Y-%m-%d %H:%M:%S UTC', nullstr='', ignore_errors=false, strict_mode=true)
        ORDER BY event_time, user_id, product_id""")
    print('events', con.execute('SELECT count(*), min(event_time), max(event_time) FROM events').fetchone(), flush=True)
    derive(con)
    con.execute('CREATE TABLE ingest_metadata(month VARCHAR, path VARCHAR, sha256 VARCHAR, source_url VARCHAR)')
    con.executemany('INSERT INTO ingest_metadata VALUES (?,?,?,?)', sources)
    multi = con.execute("SELECT count(*) FROM (SELECT product_id FROM events GROUP BY 1 HAVING count(DISTINCT category_id) > 1)").fetchone()[0]
    print('pair_first', con.execute('SELECT count(*) FROM pair_first').fetchone()[0],
          'item_static', con.execute('SELECT count(*) FROM item_static').fetchone()[0],
          'products with >1 category', multi, flush=True)
    con.execute('CHECKPOINT')
    con.close()


if __name__ == '__main__':
    main()
