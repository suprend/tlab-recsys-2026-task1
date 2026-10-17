"""Bounded development anchors and purchase labels, independent of candidates.

Run with ``python -m scripts.anchor_pilot --config ...`` from the project root.
Only aggregate reports belong in Git; user/product-level artifacts stay ignored.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import resource
import sys
import threading
import time

import duckdb

from scripts.protocol_manifest import build_run_manifest, load_protocol, sha256_file, validate_protocol, write_run_manifest
from scripts.temporal_contract import history_window, label_is_mature, source_coverage, target_window

UTC = timezone.utc
DIAGNOSTIC_HISTORY = timedelta(days=7)
ROOT = Path(__file__).resolve().parents[1]


def utc(value):
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)


def naive_utc(value):
    """DuckDB source TIMESTAMP is a UTC wall clock, as guaranteed by ingestion."""
    return value.astimezone(UTC).replace(tzinfo=None)


def as_utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def stable_key(kind, user_id, anchor, seed):
    payload = f'{kind}|{seed}|{as_utc(anchor).strftime("%Y-%m-%dT%H:%M:%SZ")}|{user_id}'
    return hashlib.sha256(payload.encode('ascii')).hexdigest()


def _dict_rows(cursor):
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _json_default(value):
    if isinstance(value, datetime):
        return as_utc(value).strftime('%Y-%m-%dT%H:%M:%SZ')
    raise TypeError(type(value).__name__)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=_json_default, allow_nan=False) + '\n')


def peak_rss_bytes():
    # Darwin returns bytes, Linux KiB. It is a process high-water mark, not an
    # additive per-stage allocation or the DuckDB memory_limit.
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw if sys.platform == 'darwin' else raw * 1024)


def directory_bytes(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


class RunDeadline:
    """A persistent deadline: SQL interrupt alone is not a between-query guard."""
    def __init__(self, seconds, *, started_at=None, clock=None):
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Deadline seconds must be finite and positive')
        self.clock = clock or time.monotonic
        self.expires_at = (self.clock() if started_at is None else started_at) + seconds
        self.expired = threading.Event()

    def check(self):
        if self.expired.is_set() or self.clock() >= self.expires_at:
            self.expired.set()
            raise TimeoutError('Wall deadline exhausted')

    def interrupt_timer(self, connection):
        def expire():
            self.expired.set()  # survives gaps with no active SQL
            connection.interrupt()
        timer = threading.Timer(max(0.0, self.expires_at - self.clock()), expire)
        timer.daemon = True
        timer.start()
        return timer


def _no_budget_check():
    pass


class StageLedger:
    def __init__(self, directory, connection=None, deadline=None):
        self.directory = directory
        self.connection = connection
        self.deadline = deadline
        self.rows = []

    def __call__(self, name, operation):
        started = time.monotonic()
        entry = {'stage': name, 'status': 'running'}
        self.rows.append(entry)
        profile_path = self.directory / (name + '.profile.json')
        try:
            if self.deadline is not None:
                self.deadline.check()
            if self.connection is not None:
                self.connection.execute("SET enable_profiling='json'")
                self.connection.execute('SET profiling_output=?', [str(profile_path)])
            result = operation()
            if self.deadline is not None:
                self.deadline.check()
            entry['status'] = 'complete'
            return result
        except Exception as error:
            entry.update(status='failed', error_type=type(error).__name__, error=str(error))
            raise
        finally:
            if self.connection is not None:
                self.connection.execute('PRAGMA disable_profiling')
            if profile_path.exists():
                profile = json.loads(profile_path.read_text())
                entry['engine_profile'] = {key: profile.get(key) for key in [
                    'latency', 'cumulative_rows_scanned', 'system_peak_buffer_memory', 'system_peak_temp_dir_size']}
            entry.update(seconds=time.monotonic() - started, process_peak_rss_bytes=peak_rss_bytes(),
                         temp_disk_bytes_at_stage_end=directory_bytes(self.directory))


def _direct_stage(name, operation):
    return operation()


def create_queries(con, config, *, stage=_direct_stage, budget_check=_no_budget_check):
    """Past-only daily eligibility and deterministic bottom-hash sampling.

    The common history7d diagnostics have the same meaning in both populations.
    The daily eligible table is dropped before the next day; only sampled Q is
    retained. SQL estimates and actual population/state sizes are separate.
    """
    config = validate_protocol(config)
    con.execute('''CREATE OR REPLACE TEMP TABLE pilot_queries (
        query_id VARCHAR, user_id BIGINT, anchor TIMESTAMP,
        eligibility_events BIGINT, history_events_7d BIGINT,
        history_distinct_items_7d BIGINT, history_active_days_7d BIGINT,
        last_history_time TIMESTAMP, history_coverage_7d DOUBLE, label_is_mature BOOLEAN)''')
    population, plans = [], []
    anchor, end = utc(config['pilot']['start']), utc(config['pilot']['end'])
    while anchor < end:
        budget_check()
        spec = config['query']
        eligibility = history_window(anchor, timedelta(hours=spec['eligibility_hours']))
        history = history_window(anchor, DIAGNOSTIC_HISTORY)
        source_start = utc(config['source']['start'])
        scan_start = max(source_start, min(eligibility.start, history.start))
        coverage = source_coverage(history, source_start=source_start, source_end=utc(config['source']['end'])).fraction
        allowed = ','.join('?' for _ in spec['eligibility_event_types'])
        sql = f'''SELECT user_id,
            count(*) FILTER(WHERE event_time >= ? AND event_type IN ({allowed})) eligibility_events,
            count(*) FILTER(WHERE event_time >= ?) history_events_7d,
            count(DISTINCT product_id) FILTER(WHERE event_time >= ?) history_distinct_items_7d,
            count(DISTINCT CAST(event_time AS DATE)) FILTER(WHERE event_time >= ?) history_active_days_7d,
            max(event_time) FILTER(WHERE event_time >= ?) last_history_time
            FROM events WHERE event_time >= ? AND event_time < ? AND user_id IS NOT NULL
            GROUP BY user_id HAVING eligibility_events > 0'''
        params = [naive_utc(eligibility.start), *spec['eligibility_event_types'],
                  *([naive_utc(history.start)] * 4), naive_utc(scan_start), naive_utc(anchor)]
        plan = con.execute('EXPLAIN ' + sql, params).fetchall()
        plans.append({'anchor': anchor, 'scan_start': scan_start, 'scan_end_exclusive': anchor,
                      'explain_estimate_only': '\n'.join(row[1] for row in plan)})
        day = anchor.strftime('%Y-%m-%d')
        stage('eligibility_' + day, lambda: con.execute('CREATE OR REPLACE TEMP TABLE pilot_eligible AS ' + sql, params))
        eligible_count = con.execute('SELECT count(*) FROM pilot_eligible').fetchone()[0]
        prefix = f'sample|{spec["sample_seed"]}|{anchor.strftime("%Y-%m-%dT%H:%M:%SZ")}|'
        # sha256 over fixed ASCII serialization, not Python's process-salted hash.
        sampled = stage('sample_' + day, lambda: con.execute('''SELECT * FROM pilot_eligible
            ORDER BY sha256(? || CAST(user_id AS VARCHAR)), user_id LIMIT ?''',
            [prefix, spec['max_users_per_day']]).fetchall())
        rows = [(stable_key('query', row[0], anchor, spec['sample_seed']), row[0], naive_utc(anchor), *row[1:], coverage, None)
                for row in sampled]
        if rows:
            con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
        population.append({'anchor': anchor, 'eligible_users': eligible_count, 'sampled_queries': len(rows),
                           'active_eligibility_keys': eligible_count})
        con.execute('DROP TABLE pilot_eligible')
        budget_check()
        anchor += timedelta(days=1)
    n = con.execute('SELECT count(*) FROM pilot_queries').fetchone()[0]
    if n > config['budget']['max_anchors']:
        raise ValueError('Actual query count exceeds declared budget')
    return {'population': population, 'scan_plans': plans}


def create_labels(con, *, target_config, source_start, source_end, stage=_direct_stage, budget_check=_no_budget_check):
    """Distinct purchase Y. Censoring is kept on Q and never called a negative.

    Full-history first sightings are used only to diagnose target catalog/pair
    coverage, after sampling. They do not select users or modify target labels.
    """
    con.execute('''CREATE OR REPLACE TEMP TABLE pilot_target_windows (
        query_id VARCHAR, user_id BIGINT, anchor TIMESTAMP, target_end TIMESTAMP,
        include_anchor BOOLEAN, include_end BOOLEAN)''')
    windows = []
    for query_id, user_id, raw_anchor in con.execute('SELECT query_id,user_id,anchor FROM pilot_queries').fetchall():
        budget_check()
        anchor = as_utc(raw_anchor)
        target = target_window(anchor, timedelta(hours=target_config['horizon_hours']),
                               include_anchor=target_config['include_anchor'], include_end=target_config['include_end'])
        mature = label_is_mature(target, available_before=source_end,
                                availability_delay=timedelta(seconds=target_config['availability_delay_seconds']))
        con.execute('UPDATE pilot_queries SET label_is_mature=? WHERE query_id=?', [mature, query_id])
        if mature:
            windows.append((query_id, user_id, naive_utc(anchor), naive_utc(target.end),
                            target.include_start, target.include_end))
    budget_check()
    if windows:
        con.executemany('INSERT INTO pilot_target_windows VALUES (?,?,?,?,?,?)', windows)
        first, last = min(row[2] for row in windows), max(row[3] for row in windows)
        stage('purchase_labels', lambda: con.execute('''CREATE OR REPLACE TEMP TABLE pilot_labels AS
            SELECT q.query_id,e.product_id,min(e.event_time) first_purchase_time,
                   count(*) raw_purchase_rows,bool_or(e.event_time=q.anchor) same_second_purchase
            FROM events e JOIN pilot_target_windows q ON e.user_id=q.user_id
              AND (e.event_time>q.anchor OR (q.include_anchor AND e.event_time=q.anchor))
              AND (e.event_time<q.target_end OR (q.include_end AND e.event_time=q.target_end))
            WHERE e.event_type='purchase' AND e.event_time>=? AND e.event_time<=?
              AND e.product_id IS NOT NULL GROUP BY q.query_id,e.product_id''', [first, last]))
        max_anchor = max(row[2] for row in windows)
        stage('target_first_sightings', lambda: con.execute('''CREATE OR REPLACE TEMP TABLE pilot_target_first_seen AS
            SELECT e.product_id,min(e.event_time) first_seen FROM events e
            SEMI JOIN (SELECT DISTINCT product_id FROM pilot_labels) l USING(product_id)
            WHERE e.event_time>=? AND e.event_time<? GROUP BY e.product_id''',
            [naive_utc(source_start), max_anchor]))
        stage('target_pair_history', lambda: con.execute('''CREATE OR REPLACE TEMP TABLE pilot_target_pair_seen AS
            SELECT q.query_id,l.product_id,min(e.event_time) first_pair_seen
            FROM pilot_labels l JOIN pilot_queries q USING(query_id)
            JOIN events e ON e.user_id=q.user_id AND e.product_id=l.product_id AND e.event_time<q.anchor
            WHERE e.event_time>=? AND e.event_time<? GROUP BY q.query_id,l.product_id''',
            [naive_utc(source_start), max_anchor]))
        con.execute('ALTER TABLE pilot_labels ADD COLUMN catalog_seen_before BOOLEAN')
        con.execute('ALTER TABLE pilot_labels ADD COLUMN pair_seen_before BOOLEAN')
        con.execute('''UPDATE pilot_labels l SET catalog_seen_before=EXISTS (
            SELECT 1 FROM pilot_target_first_seen f JOIN pilot_queries q ON q.query_id=l.query_id
            WHERE f.product_id=l.product_id AND f.first_seen<q.anchor),
            pair_seen_before=EXISTS (SELECT 1 FROM pilot_target_pair_seen p
            WHERE p.query_id=l.query_id AND p.product_id=l.product_id)''')
    else:
        con.execute('''CREATE OR REPLACE TEMP TABLE pilot_labels (
            query_id VARCHAR,product_id BIGINT,first_purchase_time TIMESTAMP,
            raw_purchase_rows BIGINT,same_second_purchase BOOLEAN,
            catalog_seen_before BOOLEAN,pair_seen_before BOOLEAN)''')
    return _dict_rows(con.execute('''SELECT q.anchor,count(*) queries,
        count(*) FILTER(WHERE NOT q.label_is_mature) censored_queries,
        count(*) FILTER(WHERE q.label_is_mature) mature_queries,
        count(*) FILTER(WHERE q.label_is_mature AND coalesce(y.n,0)=0) mature_empty_queries,
        count(*) FILTER(WHERE q.label_is_mature AND y.n>0) positive_queries,
        coalesce(sum(y.n),0)::BIGINT distinct_targets,
        coalesce(sum(y.raw_n),0)::BIGINT raw_purchase_rows,
        coalesce(sum(y.cold),0)::BIGINT cold_targets,
        coalesce(sum(y.repeat_n),0)::BIGINT repeat_pair_targets,
        coalesce(sum(y.same_n),0)::BIGINT same_second_targets,
        count(*) FILTER(WHERE y.same_n>0) same_second_positive_queries
        FROM pilot_queries q LEFT JOIN (
            SELECT query_id,count(*) n,sum(raw_purchase_rows) raw_n,
              count(*) FILTER(WHERE NOT catalog_seen_before) cold,
              count(*) FILTER(WHERE pair_seen_before) repeat_n,
              count(*) FILTER(WHERE same_second_purchase) same_n
            FROM pilot_labels GROUP BY query_id) y USING(query_id)
        GROUP BY q.anchor ORDER BY q.anchor'''))


def history_summary(con):
    return _dict_rows(con.execute('''SELECT anchor,
        CASE WHEN history_events_7d=0 THEN '0' WHEN history_events_7d=1 THEN '1' WHEN history_events_7d<=4 THEN '2-4' ELSE '5+' END history_events_bin,
        count(*) queries,count(*) FILTER(WHERE label_is_mature) mature_queries,
        count(*) FILTER(WHERE label_is_mature AND query_id IN (SELECT query_id FROM pilot_labels)) positive_queries,
        min(history_events_7d) minimum_events,max(history_events_7d) maximum_events
        FROM pilot_queries GROUP BY 1,2 ORDER BY 1,2'''))


def build_pilot(con, config, *, stage=_direct_stage, budget_check=_no_budget_check):
    config = validate_protocol(config)
    budget_check()
    result = create_queries(con, config, stage=stage, budget_check=budget_check)
    result['daily_outcomes'] = create_labels(con, target_config=config['target'],
        source_start=utc(config['source']['start']), source_end=utc(config['source']['end']), stage=stage, budget_check=budget_check)
    budget_check()
    result['history_strata'] = history_summary(con)
    budget_check()
    for row in result['daily_outcomes']:
        if row['queries'] != row['censored_queries'] + row['mature_queries']:
            raise AssertionError('Maturity accounting mismatch')
        if row['mature_queries'] != row['mature_empty_queries'] + row['positive_queries']:
            raise AssertionError('Outcome accounting mismatch')
    return result


def run(config_path, db_path, output_root, *, seconds=1800):
    started = time.monotonic()
    deadline = RunDeadline(seconds, started_at=started)
    config = load_protocol(config_path)
    deadline.check()
    db_path, output_root = db_path.resolve(), output_root.resolve()
    relative_db = db_path.relative_to(ROOT).as_posix()
    output_root.relative_to(ROOT / 'artifacts')  # identifiers/labels stay ignored
    def fingerprint(path):
        deadline.check()
        digest = sha256_file(path)
        deadline.check()
        return digest
    hashes = {p: fingerprint(ROOT / p) for p in ['uv.lock', 'scripts/anchor_pilot.py',
              'scripts/temporal_contract.py', 'scripts/protocol_manifest.py']}
    db_hash = fingerprint(db_path)
    manifest = build_run_manifest(config, code_hashes=hashes, input_hashes={relative_db: db_hash},
                                 components=[], artifact_refs={}, created_at=datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))
    directory = output_root / manifest['run_id']
    directory.mkdir(parents=True, exist_ok=False)
    temp = directory / 'temp'
    temp.mkdir()
    ledger = StageLedger(temp, deadline=deadline)
    report = {'status': 'running', 'run_id': manifest['run_id'], 'protocol': config,
              'duckdb_version': duckdb.__version__, 'stages': ledger.rows,
              'limits': {'threads': 2, 'duckdb_memory': '2GB', 'max_spill': '2GB', 'wall_seconds': seconds},
              'rss_definition': 'process high-water mark; includes engine and Python, not additive across stages',
              'spill_definition': 'temp files present at stage end; not peak spill or cumulative written bytes'}
    con = duckdb.connect(str(db_path), read_only=True)
    ledger.connection = con
    manifest['artifact_refs']['report'] = (directory / 'report.json').relative_to(ROOT).as_posix()
    timer = deadline.interrupt_timer(con)
    primary_error = None
    try:
        deadline.check()
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='2GB'")
        con.execute('SET temp_directory=?', [str(temp)])
        con.execute('SET preserve_insertion_order=false')
        report['ingest_metadata'] = _dict_rows(con.execute('SELECT * FROM ingest_metadata'))
        report['source_schema'] = _dict_rows(con.execute('DESCRIBE events'))
        deadline.check()
        result = build_pilot(con, config, stage=ledger, budget_check=deadline.check)
        report.update(result)
        for table, name in [('pilot_queries', 'queries'), ('pilot_labels', 'labels')]:
            path = directory / (name + '.parquet')
            order = 'query_id,product_id' if table == 'pilot_labels' else 'query_id'
            ledger('export_' + name, lambda table=table, path=path, order=order: con.execute(
                f'COPY (SELECT * FROM {table} ORDER BY {order}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)', [str(path)]))
            manifest['artifact_refs'][name] = path.relative_to(ROOT).as_posix()
        manifest['artifact_refs']['report'] = (directory / 'report.json').relative_to(ROOT).as_posix()
        deadline.check()
        report['status'] = 'complete'
    except BaseException as error:
        primary_error = error
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        timer.cancel()
        cleanup_error = None
        try:
            con.close()
        except BaseException as error:
            cleanup_error = error
            report.update(status='failed', cleanup_errors=[dict(operation='close_connection',
                          error_type=type(error).__name__, error=str(error))])
            if primary_error is None:
                report.update(error_type=type(error).__name__, error=str(error))
        report.update(seconds=time.monotonic() - started, process_peak_rss_bytes=peak_rss_bytes(),
                      temp_disk_bytes_after_close=directory_bytes(temp))
        save_json(directory / 'report.json', report)
        write_run_manifest(manifest, directory / 'run.json')
        print(json.dumps({'status': report['status'], 'run_id': manifest['run_id'],
                          'seconds': report['seconds'], 'report': str(directory / 'report.json')}), flush=True)
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--db', type=Path, default=ROOT / 'data/processed/october.duckdb')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'artifacts/anchor-pilot')
    args = parser.parse_args()
    run(args.config, args.db, args.output_root)


if __name__ == '__main__':
    main()
