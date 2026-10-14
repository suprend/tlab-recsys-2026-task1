"""Full-month EDA. Raw records stay in ignored data/; exported tables are aggregates."""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import hashlib
import json
import time
from pathlib import Path

import duckdb

SCHEMA = {
    'event_time': 'TIMESTAMP', 'event_type': 'VARCHAR', 'product_id': 'BIGINT',
    'category_id': 'BIGINT', 'category_code': 'VARCHAR', 'brand': 'VARCHAR',
    'price': 'DECIMAL(12,2)', 'user_id': 'BIGINT', 'user_session': 'VARCHAR',
}
SOURCE_URL = 'https://data.rees46.com/datasets/marketplace/2019-Oct.csv.gz'


def encode(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=encode) + '\n')


def query(connection, name, sql, params=None):
    start = time.monotonic()
    print(f'[{name}] started', flush=True)
    cursor = connection.execute(sql, params or [])
    names = [column[0] for column in cursor.description]
    result = [dict(zip(names, row)) for row in cursor.fetchall()]
    print(f'[{name}] {time.monotonic()-start:.1f}s; {len(result)} aggregate rows', flush=True)
    return result


def connect(db, read_only=False, threads=4, memory='6GB'):
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(db), read_only=read_only)
    connection.execute(f"SET threads={int(threads)}")
    connection.execute(f"SET memory_limit='{memory}'")
    connection.execute('SET preserve_insertion_order=false')
    temp = db.parent.parent / 'tmp' / 'duckdb'
    temp.mkdir(parents=True, exist_ok=True)
    connection.execute('SET temp_directory=?', [str(temp)])
    connection.execute("SET max_temp_directory_size='80GB'")
    return connection


def ingest(source, db):
    if not source.is_file():
        raise FileNotFoundError(source)
    started = time.monotonic()
    checksum = hashlib.sha256()
    with source.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            checksum.update(chunk)
    fingerprint = checksum.hexdigest()
    manifest = source.with_name(source.name.replace('.csv.gz', '.download.json'))
    if manifest.exists():
        recorded = json.loads(manifest.read_text())
        if recorded.get('sha256') != fingerprint or recorded.get('compressed_bytes') != source.stat().st_size:
            raise ValueError('Source does not match the verified download manifest.')
    con = connect(db, memory='8GB')
    existing = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='events'").fetchone()[0]
    if existing:
        meta = con.execute('SELECT source_sha256 FROM ingest_metadata').fetchone()[0]
        if meta != fingerprint:
            raise ValueError('Existing database belongs to another source; choose a new --db path.')
        print('[ingest] using existing verified-source table', flush=True)
    else:
        print('[ingest] reading entire gzip with strict typed CSV parser', flush=True)
        schema_literal = '{' + ','.join(f"'{key}':'{value}'" for key, value in SCHEMA.items()) + '}'
        con.execute('BEGIN TRANSACTION')
        try:
            con.execute(f"""CREATE TABLE events AS SELECT * FROM read_csv(?,
                columns={schema_literal}, header=true, timestampformat='%Y-%m-%d %H:%M:%S UTC',
                nullstr='', ignore_errors=false, strict_mode=true)""", [str(source)])
            con.execute('CREATE TABLE ingest_metadata(source_sha256 VARCHAR, source_bytes BIGINT, source_url VARCHAR)')
            con.execute('INSERT INTO ingest_metadata VALUES (?,?,?)', [fingerprint, source.stat().st_size, SOURCE_URL])
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK')
            raise
        con.execute('CHECKPOINT')
    rows = con.execute('SELECT count(*) FROM events').fetchone()[0]
    con.close()
    print(f'[ingest] complete: {rows:,} rows; {time.monotonic()-started:.1f}s', flush=True)
    return {'sha256': fingerprint, 'compressed_bytes': source.stat().st_size, 'rows': rows}


def quality(con, output):
    results = {}
    results['summary'] = query(con, 'summary', """SELECT count(*) AS "rows",
        min(event_time) first_time_utc, max(event_time) last_time_utc,
        count(DISTINCT user_id) users, count(DISTINCT product_id) products,
        count(DISTINCT category_id) category_ids, count(DISTINCT category_code) category_codes,
        count(DISTINCT brand) brands,
        count(*) FILTER(WHERE event_time<'2019-10-01' OR event_time>='2019-11-01') outside_october,
        count(*) FILTER(WHERE event_type NOT IN ('view','cart','remove_from_cart','purchase')) unknown_event_types,
        count(*) FILTER(WHERE price<0) negative_prices,
        count(*) FILTER(WHERE price=0) zero_prices,
        min(price) min_price, max(price) max_price,
        quantile_cont(price,[.01,.5,.9,.99]) price_quantiles
        FROM events""")[0]
    results['missing'] = query(con, 'missing', 'SELECT ' + ','.join(
        f'count(*) FILTER(WHERE {column} IS NULL) {column}' for column in SCHEMA) + ' FROM events')[0]
    results['events'] = query(con, 'event mix', """SELECT event_type,count(*) events,
        count(DISTINCT user_id) users,count(DISTINCT product_id) products FROM events GROUP BY 1 ORDER BY events DESC""")
    results['daily'] = query(con, 'daily', """SELECT CAST(event_time AS DATE) AS day,event_type,
        count(*) events,count(DISTINCT user_id) users,
        count(*) FILTER(WHERE category_code IS NULL) missing_category_code,
        count(*) FILTER(WHERE brand IS NULL) missing_brand
        FROM events GROUP BY 1,2 ORDER BY 1,2""")
    results['duplicates'] = query(con, 'exact typed-row duplicates', """SELECT
        coalesce(sum(n-1),0) duplicate_surplus,coalesce(sum(n),0) affected_rows,
        coalesce(sum(n-1) FILTER(WHERE event_type='purchase'),0) purchase_duplicate_surplus,
        count(*) duplicate_groups FROM (
            SELECT event_time,event_type,product_id,category_id,category_code,brand,price,user_id,user_session,count(*) n
            FROM events GROUP BY ALL HAVING count(*)>1)""")[0]
    con.execute("""CREATE TEMP TABLE item_summary AS SELECT product_id,count(*) n_events,
        count(*) FILTER(WHERE event_type='purchase') n_purchases,
        min(event_time) first_seen, count(DISTINCT category_id) n_category_ids,
        count(DISTINCT category_code) n_category_codes,count(DISTINCT brand) n_brands,
        count(DISTINCT price) n_prices, min(price) min_price,max(price) max_price
        FROM events GROUP BY 1""")
    results['metadata_variation'] = query(con, 'metadata variation', """SELECT count(*) products,
        count(*) FILTER(WHERE n_category_ids>1) multiple_category_ids,
        count(*) FILTER(WHERE n_category_codes>1) multiple_category_codes,
        count(*) FILTER(WHERE n_brands>1) multiple_brands,
        count(*) FILTER(WHERE n_prices>1) changing_prices FROM item_summary""")[0]
    results['item_distribution'] = query(con, 'item distribution', """SELECT
        quantile_cont(n_events,[.5,.75,.9,.95,.99]) event_quantiles,
        count(*) FILTER(WHERE n_events=1) one_event_products,
        count(*) FILTER(WHERE n_purchases>0) purchased_products FROM item_summary""")[0]
    results['concentration'] = query(con, 'item concentration', """WITH ranked AS (
        SELECT *,row_number() OVER(ORDER BY n_events DESC,product_id) r,count(*) OVER() total_products FROM item_summary)
        SELECT sum(n_events) total_events,sum(n_events) FILTER(WHERE r<=100) top100_events,
        sum(n_events) FILTER(WHERE r<=ceil(total_products*.01)) top1pct_events FROM ranked""")[0]
    results['categories'] = query(con, 'category mix', """SELECT coalesce(split_part(category_code,'.',1),'[unknown]') category,
        count(*) events,count(*) FILTER(WHERE event_type='purchase') purchases,
        count(DISTINCT product_id) products FROM events GROUP BY 1 ORDER BY events DESC LIMIT 12""")
    con.execute("""CREATE TEMP TABLE session_summary AS SELECT user_id,user_session,count(*) n_events,
        min(event_time) first_time,max(event_time) last_time,
        count(DISTINCT CAST(event_time AS DATE)) n_days,
        bool_or(event_type='view') has_view,bool_or(event_type='cart') has_cart,
        bool_or(event_type='purchase') has_purchase FROM events
        WHERE user_id IS NOT NULL AND user_session IS NOT NULL GROUP BY 1,2""")
    results['sessions'] = query(con, 'sessions', """SELECT count(*) user_sessions,
        quantile_cont(n_events,[.5,.9,.99]) event_quantiles,
        quantile_cont(date_diff('second',first_time,last_time),[.5,.9,.99]) span_seconds_quantiles,
        count(*) FILTER(WHERE n_days>1) cross_day_sessions,
        count(*) FILTER(WHERE has_view) sessions_with_view,
        count(*) FILTER(WHERE has_cart) sessions_with_cart,
        count(*) FILTER(WHERE has_purchase) sessions_with_purchase,
        count(*) FILTER(WHERE has_purchase AND NOT has_cart) purchase_sessions_without_cart,
        count(*) FILTER(WHERE has_purchase AND NOT has_view) purchase_sessions_without_view,
        count(*) FILTER(WHERE has_view AND has_cart AND has_purchase) sessions_with_all_three
        FROM session_summary""")[0]
    results['session_identity'] = query(con, 'session identity', """SELECT count(*) session_ids,
        count(*) FILTER(WHERE n_users>1) ids_with_multiple_users FROM (
            SELECT user_session,count(*) n_users FROM session_summary GROUP BY 1)""")[0]
    results['timestamp_ties'] = query(con, 'timestamp ties', """SELECT count(*) tied_user_timestamp_groups,
        coalesce(sum(n),0) rows_in_tied_groups FROM (
        SELECT user_id,event_time,count(*) n FROM events
        WHERE user_id IS NOT NULL AND event_time IS NOT NULL GROUP BY 1,2 HAVING count(*)>1)""")[0]
    results['transitions'] = query(con, 'ordered session timestamp transitions', """WITH buckets AS (
        SELECT user_id,user_session,event_time,
            CASE WHEN count(DISTINCT event_type)=1 THEN min(event_type) END AS kind
        FROM events WHERE user_id IS NOT NULL AND user_session IS NOT NULL AND event_time IS NOT NULL
        GROUP BY user_id,user_session,event_time
        ), ordered AS (
        SELECT kind,lag(kind) OVER(PARTITION BY user_id,user_session ORDER BY event_time) previous_kind
        FROM buckets)
        SELECT previous_kind,kind,count(*) timestamp_bucket_pairs
        FROM ordered WHERE previous_kind IS NOT NULL AND kind IS NOT NULL GROUP BY 1,2 ORDER BY 1,2""")
    summary = results['summary']
    assert sum(row['events'] for row in results['daily']) == summary['rows']
    assert sum(row['events'] for row in results['events']) == summary['rows']
    assert results['concentration']['total_events'] == summary['rows']
    assert summary['outside_october'] == 0
    save_json(output / 'quality.json', results)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('data/raw/2019-Oct.csv.gz'))
    parser.add_argument('--db', type=Path, default=Path('data/processed/october.duckdb'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/eda-october'))
    parser.add_argument('--ingest-only', action='store_true')
    parser.add_argument('--quality-only', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    source = ingest(args.input.resolve(), args.db.resolve())
    if args.ingest_only:
        return
    args.output.mkdir(parents=True, exist_ok=True)
    con = connect(args.db.resolve(), read_only=True)
    quality_results = quality(con, args.output)
    con.close()
    user_results = None
    if not args.quality_only:
        from user_metrics import run
        con = connect(args.db.resolve(), read_only=True)
        user_results = run(con, args.output)
        con.close()
    save_json(args.output / 'run.json', {'source': source, 'duckdb_version': duckdb.__version__,
        'finished_utc': dt.datetime.now(dt.timezone.utc), 'seconds': time.monotonic()-start,
        'quality_complete': True, 'users_complete': user_results is not None})
    print('[EDA] aggregate results saved; no model trained', flush=True)


if __name__ == '__main__':
    main()
