"""Read-only H&M source audit; row-level DuckDB cache stays local and private.

The JSON/Markdown reports contain aggregates only. This is an offline data audit,
not permission to use held-out outcomes for model or feature selection.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import time

import duckdb


SCHEMAS = {
    'transactions': {
        't_dat': 'DATE', 'customer_id': 'VARCHAR', 'article_id': 'VARCHAR',
        'price': 'DOUBLE', 'sales_channel_id': 'VARCHAR',
    },
    'customers': {
        'customer_id': 'VARCHAR', 'FN': 'DOUBLE', 'Active': 'DOUBLE',
        'club_member_status': 'VARCHAR', 'fashion_news_frequency': 'VARCHAR',
        'age': 'DOUBLE', 'postal_code': 'VARCHAR',
    },
    'articles': dict.fromkeys([
        'article_id', 'product_code', 'prod_name', 'product_type_no',
        'product_type_name', 'product_group_name', 'graphical_appearance_no',
        'graphical_appearance_name', 'colour_group_code', 'colour_group_name',
        'perceived_colour_value_id', 'perceived_colour_value_name',
        'perceived_colour_master_id', 'perceived_colour_master_name',
        'department_no', 'department_name', 'index_code', 'index_name',
        'index_group_no', 'index_group_name', 'section_no', 'section_name',
        'garment_group_no', 'garment_group_name', 'detail_desc',
    ], 'VARCHAR'),
}
FILES = {'transactions': 'transactions_train.csv', 'customers': 'customers.csv',
         'articles': 'articles.csv'}
CUTOFFS = tuple(dt.date.fromisoformat(s) for s in (
    '2020-08-12', '2020-08-19', '2020-08-26',
    '2020-09-02', '2020-09-09', '2020-09-16'))
EXPECTED_ROWS = {'transactions': 31_788_324, 'customers': 1_371_980, 'articles': 105_542}


def ident(value):
    return '"' + value.replace('"', '""') + '"'


def rows(con, sql, params=None):
    cur = con.execute(sql, params or [])
    names = [x[0] for x in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def validate_header(path, schema):
    """Reject schema drift before DuckDB reads data; do not echo source records."""
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        header = next(csv.reader(stream), [])
    if len(header) != len(set(header)) or set(header) != set(schema):
        raise ValueError(f'{path.name}: CSV header does not match the H&M schema')
    return header


def load_sources(con, raw_dir):
    sources = {}
    for table, schema in SCHEMAS.items():
        path = raw_dir / FILES[table]
        header = validate_header(path, schema)
        stat = path.stat()
        # CSV field order may vary. Explicit columns map matches the actual header.
        columns = '{' + ','.join("'" + name + "':'" + schema[name] + "'" for name in header) + '}'
        con.execute(f'CREATE TABLE {ident(table)} AS SELECT * FROM read_csv(?, '
                    f'header=true, auto_detect=false, columns={columns}, '
                    "delim=',', quote='\"', escape='\"', strict_mode=true)", [str(path)])
        after = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f'{path.name}: source changed during ingestion')
        sources[table] = {'file': path.name, 'bytes': stat.st_size,
                          'mtime_ns': stat.st_mtime_ns, 'columns': header}
    return sources


def table_audit(con, table):
    schema = SCHEMAS[table]
    missing = ', '.join(
        f'count(*) FILTER (WHERE {ident(c)} IS NULL) AS {ident(c)}' for c in schema)
    result = {'rows': con.execute(f'SELECT count(*) FROM {ident(table)}').fetchone()[0],
              'reference_full_dataset_rows': EXPECTED_ROWS[table],
              'missing': rows(con, f'SELECT {missing} FROM {ident(table)}')[0]}
    result['matches_reference_rows'] = result['rows'] == EXPECTED_ROWS[table]
    result['ids'] = {}
    for key in ('customer_id', 'article_id'):
        if key not in schema:
            continue
        pattern = '[0-9a-f]{64}' if key == 'customer_id' else '[0-9]+'
        result['ids'][key] = rows(con, f'''SELECT
            count(DISTINCT {key}) AS distinct_nonnull,
            count(*) FILTER (WHERE {key} IS NULL OR trim({key})='') AS missing_or_empty,
            count(*) FILTER (WHERE {key} IS NOT NULL AND NOT regexp_full_match({key}, ?)) AS malformed,
            count(*) FILTER (WHERE {key} LIKE '0%') AS leading_zero_rows
            FROM {ident(table)}''', [pattern])[0]
        result['ids'][key]['width_counts'] = rows(con, f'''SELECT length({key}) AS width,
            count(*) AS rows FROM {ident(table)} GROUP BY 1 ORDER BY 1''')
    # Exact duplicates are counted, never removed from the transaction table.
    all_cols = ', '.join(ident(c) for c in schema)
    result['exact_duplicates'] = rows(con, f'''SELECT
        coalesce(sum(n-1),0)::BIGINT AS extra_rows, count(*) AS repeated_groups,
        coalesce(sum(n),0)::BIGINT AS rows_in_repeated_groups FROM
        (SELECT count(*) AS n FROM {ident(table)} GROUP BY {all_cols} HAVING count(*)>1)''')[0]
    if table != 'transactions':
        key = 'customer_id' if table == 'customers' else 'article_id'
        result['duplicate_keys'] = rows(con, f'''SELECT count(*) AS keys,
            coalesce(sum(n-1),0)::BIGINT AS extra_rows FROM
            (SELECT count(*) AS n FROM {ident(table)} WHERE {key} IS NOT NULL
             GROUP BY {key} HAVING count(*)>1)''')[0]
    return result


def history_distribution(con):
    return rows(con, '''WITH h AS (SELECT customer_id, count(*) AS purchase_rows,
        count(DISTINCT article_id) AS distinct_articles, count(DISTINCT t_dat) AS purchase_days,
        date_diff('day',min(t_dat),max(t_dat)) AS observed_span_days
        FROM transactions WHERE customer_id IS NOT NULL GROUP BY customer_id),
        metrics AS (SELECT unnest(['purchase_rows','distinct_articles','purchase_days','observed_span_days']) AS metric,
        unnest([purchase_rows,distinct_articles,purchase_days,observed_span_days]) AS value FROM h)
        SELECT metric,count(*) AS users,min(value) AS minimum,avg(value) AS mean,
        approx_quantile(value,0.5) AS approx_p50,approx_quantile(value,0.9) AS approx_p90,
        approx_quantile(value,0.99) AS approx_p99,max(value) AS maximum
        FROM metrics GROUP BY metric ORDER BY metric''')


def cohort_audit(con, cutoff):
    end = cutoff + dt.timedelta(days=7)
    # Per-user aggregation avoids an all-customer x all-item or event-pair join.
    result = rows(con, '''WITH h AS (SELECT customer_id,
        count(*) FILTER(WHERE t_dat < ?::DATE) AS prior_rows,
        count(*) FILTER(WHERE t_dat >= ?::DATE-INTERVAL 30 DAY AND t_dat < ?::DATE) AS prior30,
        count(*) FILTER(WHERE t_dat >= ?::DATE-INTERVAL 90 DAY AND t_dat < ?::DATE) AS prior90,
        count(*) FILTER(WHERE t_dat >= ?::DATE AND t_dat < ?::DATE) AS label_rows,
        count(DISTINCT article_id) FILTER(WHERE t_dat >= ?::DATE AND t_dat < ?::DATE) AS label_articles
        FROM transactions WHERE customer_id IS NOT NULL AND t_dat < ?::DATE GROUP BY customer_id)
        SELECT count(*) FILTER(WHERE label_rows>0) AS positive_users,
        count(*) FILTER(WHERE label_rows>0 AND prior_rows=0) AS cold_positive_users,
        count(*) FILTER(WHERE label_rows>0 AND prior30>0) AS positive_with_prior30d,
        count(*) FILTER(WHERE label_rows>0 AND prior90>0) AS positive_with_prior90d,
        count(*) FILTER(WHERE prior90>0) AS active_prior90d_users,
        count(*) FILTER(WHERE prior90>0 AND label_rows=0) AS active_prior90d_no_purchase_users,
        coalesce(sum(label_rows),0)::BIGINT AS label_purchase_rows,
        coalesce(sum(label_articles),0)::BIGINT AS distinct_user_article_labels,
        avg(label_articles) FILTER(WHERE label_rows>0) AS mean_labels_per_positive_user
        FROM h''', [cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, end, cutoff, end, end])[0]
    result['cutoff'] = cutoff.isoformat()
    result['target_end_exclusive'] = end.isoformat()
    maximum = con.execute('SELECT max(t_dat) FROM transactions').fetchone()[0]
    result['target_observation_complete_by_max_date'] = maximum is not None and maximum >= end-dt.timedelta(days=1)
    denom = result['active_prior90d_users']
    result['active_prior90d_positive_rate'] = result['positive_with_prior90d']/denom if denom else None
    return result


def analyze(con, sources):
    tables = {t: table_audit(con, t) for t in SCHEMAS}
    date_range = rows(con, '''SELECT min(t_dat) AS minimum,max(t_dat) AS maximum,
        count(*) FILTER(WHERE t_dat IS NULL) AS missing_dates,
        count(*) FILTER(WHERE price IS NOT NULL AND (NOT isfinite(price) OR price<0)) AS invalid_prices
        FROM transactions''')[0]
    fk = {}
    for key, target in (('customer_id', 'customers'), ('article_id', 'articles')):
        fk[key] = rows(con, f'''SELECT count(*) AS orphan_transaction_rows,
            count(DISTINCT t.{key}) AS orphan_distinct_nonnull_ids FROM transactions t
            WHERE NOT EXISTS(SELECT 1 FROM {target} m WHERE m.{key}=t.{key})''')[0]
    aggregates = {}
    for grain, expr in (('daily', 't_dat'), ('calendar_weekly', "date_trunc('week',t_dat)::DATE")):
        aggregates[grain] = rows(con, f'''SELECT {expr} AS period_start,count(*) AS purchase_rows,
            count(DISTINCT customer_id) AS purchasing_users,count(DISTINCT article_id) AS purchased_articles
            FROM transactions GROUP BY 1 ORDER BY 1''')
    metadata_unique = all(tables[t]['duplicate_keys']['keys']==0 for t in ('customers','articles'))
    ids_valid = all(x['missing_or_empty']==0 and x['malformed']==0
                    for t in tables.values() for x in t['ids'].values())
    return {'format': 'hm-aggregate-eda-v1', 'sources': sources, 'tables': tables,
            'date_range': date_range, 'foreign_keys': fk, 'aggregates': aggregates,
            'customers_without_transactions': con.execute('''SELECT count(*) FROM customers c
                WHERE NOT EXISTS(SELECT 1 FROM transactions t WHERE t.customer_id=c.customer_id)''').fetchone()[0],
            'history_distribution': history_distribution(con),
            'weekly_cohorts': [cohort_audit(con,c) for c in CUTOFFS],
            'validation': {'metadata_keys_unique': metadata_unique, 'id_format_valid': ids_valid,
                           'foreign_keys_complete': all(v['orphan_transaction_rows']==0 for v in fk.values()),
                           'dates_complete': date_range['missing_dates']==0,
                           'prices_valid': date_range['invalid_prices']==0},
            'caveats': [
                'Raw identical transaction rows are retained: multiple units/purchases cannot be distinguished from ingestion duplicates.',
                'Only JSON and Markdown are safe aggregate reports; audit.duckdb contains private row-level data and must stay outside Git.',
                'Offline EDA includes final-week aggregates; these must not guide feature/model selection. Final outcome metrics remain sealed.',
                'Customer mutable snapshot fields (FN, Active, membership/news status) are not approved as point-in-time training features.',
                'Article semantic metadata is an undated snapshot; historical availability is not guaranteed. Sales channel codes are uninterpreted.',
                'Article IDs stay VARCHAR without padding; width counts expose possible numeric serialization in upstream mirrors.',
                'Weekly windows are left-inclusive/right-exclusive; history is strictly before cutoff. Calendar weekly aggregates start Monday.',
                'Observed-date completeness checks only the maximum date, not the existence of every expected day.',
                'History distribution quantiles are approximate; empty-string non-ID metadata values are not counted as NULL.',
            ]}


def render_markdown(report):
    lines = ['# H&M offline data audit', '', 'Read-only input inspection; aggregate results only.', '',
             '| Table | Actual rows | Reference rows | Exact duplicate extras |',
             '| --- | ---: | ---: | ---: |']
    for name, table in report['tables'].items():
        lines.append(f"| {name} | {table['rows']} | {table['reference_full_dataset_rows']} | {table['exact_duplicates']['extra_rows']} |")
    dates = report['date_range']
    lines += ['', f"Transaction dates: {dates['minimum']} to {dates['maximum']}.", '',
              '## Weekly cohort feasibility', '',
              '| Cutoff | Positive users | Cold positive | Prior 30d positive | Prior 90d active | Prior 90d positive rate |',
              '| --- | ---: | ---: | ---: | ---: | ---: |']
    for c in report['weekly_cohorts']:
        rate = c['active_prior90d_positive_rate']
        rate_text = f'{rate:.4%}' if rate is not None else 'n/a'
        lines.append(f"| {c['cutoff']} | {c['positive_users']} | {c['cold_positive_users']} | {c['positive_with_prior30d']} | {c['active_prior90d_users']} | {rate_text} |")
    lines += ['', 'Validation: ' + json.dumps(report['validation'], sort_keys=True), '',
              'Full missingness, IDs, FK, distributions and daily/weekly aggregates: `summary.json`.', '', '## Interpretation limits', '']
    lines.extend('- ' + c for c in report['caveats'])
    return '\n'.join(lines) + '\n'


def run(raw_dir, output):
    raw_dir, output = Path(raw_dir).resolve(), Path(output).absolute()
    # Never adopt or overwrite a previous run, including a symlink to one.
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    con = duckdb.connect(str(output / 'audit.duckdb'))
    try:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='4GB'")
        con.execute('SET preserve_insertion_order=false')
        temp = output / 'temp'
        temp.mkdir()
        con.execute('SET temp_directory=?', [str(temp)])
        con.execute("SET max_temp_directory_size='32GB'")
        report = analyze(con, load_sources(con, raw_dir))
        report['elapsed_seconds'] = round(time.monotonic()-started,3)
        with (output/'summary.json').open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2,default=str,allow_nan=False)
            stream.write('\n')
        with (output/'report.md').open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(render_markdown(report))
        return report
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('artifacts')/('hm-eda-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    args = parser.parse_args()
    try:
        report = run(args.raw_dir,args.output)
    except Exception as error:
        # Native CSV errors can embed source IDs/records. Keep the CLI log private-data free.
        parser.exit(1,f'H&M EDA failed ({type(error).__name__}); inputs unchanged. Use a new output directory after fixing source/schema/resource issues.\n')
    print(f"H&M EDA complete: {args.output.absolute().as_posix()}/report.md")
    return 0 if all(report['validation'].values()) else 2


if __name__=='__main__':
    raise SystemExit(main())
