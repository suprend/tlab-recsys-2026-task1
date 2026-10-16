"""Typed, strict-past manual aggregates over fixed query/candidate pairs.

The registry declares semantics; the compiler only emits a small validated SQL
vocabulary. Event category IDs remain attached to their historical events.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import timedelta, timezone
import json
from pathlib import Path
import re

from scripts.anchor_pilot import _dict_rows, _no_budget_check, naive_utc, utc
from scripts.candidate_pilot import validate_queries
from scripts.protocol_manifest import validate_protocol
from scripts.temporal_contract import history_window, source_coverage

ROOT = Path(__file__).resolve().parents[1]

GRAINS = {
    'user': ['user_id'], 'item': ['product_id'], 'pair': ['user_id', 'product_id'],
    'user_category': ['user_id', 'category_id'],
    'item_category': ['product_id', 'category_id'], 'category': ['category_id'],
}
HEADER = dict(version=1, history='strict_past_raw_event_rows',
              category_policy='latest_global_past_timestamp_null_mixture_ambiguous',
              category_counter_key='historical_event_category_id', known_key_empty_count=0,
              unknown_conditional_key=None, undefined_ratio=None, missing_recency=None)


def _keys(value, expected):
    if not isinstance(value, dict) or value.keys() != set(expected):
        raise ValueError('Registry fields must match the declared schema exactly')


def validate_registry(registry):
    _keys(registry, {*HEADER, 'name', 'features'})
    for key, expected in HEADER.items():
        if type(registry[key]) is not type(expected) or registry[key] != expected:
            raise ValueError(f'Unsupported registry policy: {key}')
    if not isinstance(registry['name'], str) or not registry['name']:
        raise ValueError('Registry name must be nonempty')
    features = registry['features']
    if not isinstance(features, list) or not 1 <= len(features) <= 64:
        raise ValueError('Registry must contain1–64 features')
    names = {}
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError('Feature must be an object')
        ratio = feature.get('operator') == 'ratio'
        _keys(feature, {'name', 'grain', 'operator', 'numerator', 'denominator'} if ratio
              else {'name', 'grain', 'operator', 'event_type', 'window', 'column'})
        name = feature['name']
        reserved = {'query_id', 'user_id', 'product_id', 'anchor', 'label_is_mature',
                    'from_popular', 'from_recent', 'popularity_distinct_users', 'popular_source_rank',
                    'recent_source_rank', 'last_user_event_time', 'candidate_category_id',
                    'candidate_category_ambiguous', 'candidate_category_missing',
                    'item_has_observed_history', 'user_has_observed_history',
                    'item_observed_age_seconds', 'user_observed_age_seconds'}
        if (not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name)
                or name in names or name in reserved or name.startswith('source_coverage_') or name.endswith('_missing')):
            raise ValueError('Feature names must be unique safe identifiers')
        if not isinstance(feature['grain'], str) or feature['grain'] not in GRAINS:
            raise ValueError('Unsupported grain')
        names[name] = feature
        if ratio:
            continue
        if not isinstance(feature['event_type'], str) or feature['event_type'] not in {'view', 'cart', 'purchase'}:
            raise ValueError('Unsupported event type')
        op, window, column = feature['operator'], feature['window'], feature['column']
        if not isinstance(op, str):
            raise ValueError('Operator must be a string')
        if op == 'recency_seconds':
            if window != 'observed' or column != 'event_time':
                raise ValueError('Recency must use full observed strict-past event_time')
        elif op in {'count', 'count_distinct'}:
            if type(window) is not int or not 1 <= window <= 744:
                raise ValueError('Count window must be1–744 hours')
            if (op == 'count' and column is not None) or (op == 'count_distinct' and (not isinstance(column, str) or column not in {'user_id', 'product_id'})):
                raise ValueError('Unsupported count column')
        else:
            raise ValueError('Unsupported operator')
    for feature in features:
        if feature['operator'] != 'ratio':
            continue
        if not isinstance(feature['numerator'], str) or not isinstance(feature['denominator'], str):
            raise ValueError('Ratio supports must be named features')
        numerator, denominator = names.get(feature['numerator']), names.get(feature['denominator'])
        if numerator is None or denominator is None:
            raise ValueError('Ratio supports must exist in the registry')
        expected = {'user_category': ('user_category', 'user'),
                    'item_category': ('item_category', 'category')}.get(feature['grain'])
        if expected is None or (numerator['grain'], denominator['grain']) != expected:
            raise ValueError('Ratio grains are not a nested count share')
        if (numerator['operator'] != 'count' or denominator['operator'] != 'count'
                or numerator['event_type'] != denominator['event_type'] or numerator['window'] != denominator['window']):
            raise ValueError('Shares require matching event type/window count supports')
    return deepcopy(registry)


def load_registry(path):
    # Same JSON parser protections as protocol files: duplicate keys/nonfinite
    # values cannot silently change the specification being fingerprinted.
    from scripts.protocol_manifest import _read_json
    return validate_registry(_read_json(path))


def _direct_stage(name, operation):
    return operation()


def _expression(feature, anchor):
    event = feature['event_type']  # validated fixed vocabulary, not arbitrary SQL
    if feature['operator'] == 'recency_seconds':
        return f"epoch(?::TIMESTAMP-max(e.event_time) FILTER(WHERE e.event_type='{event}'))", [anchor]
    start = anchor - timedelta(hours=feature['window'])
    predicate = f"e.event_type='{event}' AND e.event_time>=?"
    agg = 'count(*)' if feature['operator'] == 'count' else f"count(DISTINCT e.{feature['column']})"
    return f'{agg} FILTER(WHERE {predicate})::BIGINT', [start]


def _grain_sql(grain, features, anchor, source_start):
    keys = GRAINS[grain]
    expressions, params = [], []
    for feature in features:
        expression, arguments = _expression(feature, anchor)
        expressions.append(expression + ' AS "' + feature['name'] + '"')
        params.extend(arguments)
    observed = any(f['window'] == 'observed' for f in features)
    start = source_start if observed else max(source_start, anchor - timedelta(hours=max(f['window'] for f in features)))
    if grain in {'user', 'pair', 'user_category'}:
        join = 'SEMI JOIN manual_day_users u USING(user_id)'
    elif grain in {'item', 'item_category'}:
        join = 'SEMI JOIN manual_day_items i USING(product_id)'
    else:
        join = 'SEMI JOIN (SELECT DISTINCT category_id FROM manual_metadata WHERE category_id IS NOT NULL) m USING(category_id)'
    nonnull = ' AND e.category_id IS NOT NULL' if 'category_id' in keys else ''
    sql = f'''SELECT {','.join('e.'+key for key in keys)}, {','.join(expressions)}
        FROM events e {join} WHERE e.event_time>=? AND e.event_time<?{nonnull}
        GROUP BY {','.join('e.'+key for key in keys)}'''
    return sql, [*params, start, anchor]


def create_manual_features(con, config, registry, *, stage=_direct_stage, budget_check=_no_budget_check):
    """One SQL batch per validated identical UTC anchor; no labels are read."""
    config, registry = validate_protocol(config), validate_registry(registry)
    budget_check()
    validate_queries(con, config)
    duplicates = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM pilot_candidates').fetchone()
    orphan = con.execute('''SELECT count(*) FROM pilot_candidates c LEFT JOIN pilot_queries q USING(query_id)
        WHERE q.query_id IS NULL OR c.product_id IS NULL''').fetchone()[0]
    if duplicates[0] != duplicates[1] or orphan or duplicates[0] > config['budget']['max_candidate_pairs']:
        raise ValueError('Candidate identity or budget invalid')
    by_grain = defaultdict(list)
    for feature in registry['features']:
        if feature['operator'] != 'ratio':
            by_grain[feature['grain']].append(feature)
    windows = sorted({f['window'] for f in registry['features'] if f['operator'] != 'ratio' and type(f['window']) is int})
    source_start = naive_utc(utc(config['source']['start']))
    anchors = [r[0] for r in con.execute('SELECT DISTINCT anchor FROM pilot_queries ORDER BY anchor').fetchall()]
    if not anchors:
        anchors = [naive_utc(utc(config['pilot']['start']))]  # typed zero-row schema, no fabricated queries
    rows = []
    initialized = False
    for anchor in anchors:
        budget_check()
        day = anchor.strftime('%Y-%m-%d')
        con.execute('CREATE OR REPLACE TEMP TABLE manual_day_queries AS SELECT * FROM pilot_queries WHERE anchor=?', [anchor])
        con.execute('''CREATE OR REPLACE TEMP TABLE manual_day_pairs AS SELECT c.*,q.user_id,q.anchor
            FROM pilot_candidates c JOIN manual_day_queries q USING(query_id)''')
        con.execute('CREATE OR REPLACE TEMP TABLE manual_day_users AS SELECT DISTINCT user_id FROM manual_day_queries')
        con.execute('CREATE OR REPLACE TEMP TABLE manual_day_items AS SELECT DISTINCT product_id FROM manual_day_pairs')
        stage('metadata_' + day, lambda: con.execute('''CREATE OR REPLACE TEMP TABLE manual_metadata AS
            WITH state AS (SELECT e.product_id,min(e.event_time) first_seen,max(e.event_time) last_seen
                FROM events e SEMI JOIN manual_day_items i USING(product_id)
                WHERE e.event_time>=? AND e.event_time<? GROUP BY e.product_id)
            SELECT s.product_id,s.first_seen,s.last_seen,
                CASE WHEN count(DISTINCT e.category_id)=1 AND count(*) FILTER(WHERE e.category_id IS NULL)=0
                    THEN min(e.category_id) END category_id,
                (count(DISTINCT e.category_id)>1 OR (count(DISTINCT e.category_id)>0
                    AND count(*) FILTER(WHERE e.category_id IS NULL)>0)) category_ambiguous
            FROM state s JOIN events e ON e.product_id=s.product_id AND e.event_time=s.last_seen
            GROUP BY s.product_id,s.first_seen,s.last_seen''', [source_start,anchor]))
        stage('user_first_seen_' + day, lambda: con.execute('''CREATE OR REPLACE TEMP TABLE manual_user_state AS
            SELECT e.user_id,min(e.event_time) first_seen FROM events e SEMI JOIN manual_day_users u USING(user_id)
            WHERE e.event_time>=? AND e.event_time<? GROUP BY e.user_id''', [source_start,anchor]))
        for grain, features in by_grain.items():
            sql, params = _grain_sql(grain, features, anchor, source_start)
            stage(grain + '_' + day, lambda grain=grain, sql=sql, params=params:
                  con.execute('CREATE OR REPLACE TEMP TABLE manual_' + grain + ' AS ' + sql, params))
        joins, columns = [], []
        for grain, features in by_grain.items():
            alias = 'g_' + grain
            conditions = []
            for key in GRAINS[grain]:
                conditions.append(f'{alias}.{key}=' + ('m.category_id' if key == 'category_id' else 'p.' + key))
            joins.append(f'LEFT JOIN manual_{grain} {alias} ON ' + ' AND '.join(conditions))
            for feature in features:
                value = alias + '."' + feature['name'] + '"'
                if feature['operator'] in {'count', 'count_distinct'}:
                    value = f'coalesce({value},0)'
                if 'category_id' in GRAINS[grain]:
                    value = f'CASE WHEN m.category_id IS NOT NULL THEN {value} END'
                columns.append(value + ' AS "' + feature['name'] + '"')
        coverage, coverage_params = [], []
        for hours in windows:
            window = history_window(anchor.replace(tzinfo=timezone.utc), timedelta(hours=hours))
            fraction = source_coverage(window, source_start=utc(config['source']['start']), source_end=utc(config['source']['end'])).fraction
            coverage.append('?::DOUBLE AS source_coverage_' + str(hours) + 'h')
            coverage_params.append(fraction)
        inner = f'''SELECT p.*,m.category_id candidate_category_id,
            coalesce(m.category_ambiguous,false) candidate_category_ambiguous,
            (m.category_id IS NULL) candidate_category_missing,
            (m.first_seen IS NOT NULL) item_has_observed_history,
            (u.first_seen IS NOT NULL) user_has_observed_history,
            epoch(p.anchor-m.first_seen) item_observed_age_seconds,
            epoch(p.anchor-u.first_seen) user_observed_age_seconds,
            {','.join(columns+coverage)} FROM manual_day_pairs p
            LEFT JOIN manual_metadata m USING(product_id) LEFT JOIN manual_user_state u USING(user_id)
            {' '.join(joins)}'''
        derived = [f'"{f["numerator"]}"*1.0/nullif("{f["denominator"]}",0) AS "{f["name"]}"'
                   for f in registry['features'] if f['operator'] == 'ratio']
        with_derived = 'SELECT b.*' + (',' + ','.join(derived) if derived else '') + ' FROM (' + inner + ') b'
        flags = ['"' + f['name'] + '" IS NULL AS "' + f['name'] + '_missing"' for f in registry['features']
                 if f['operator'] in {'ratio', 'recency_seconds'} or 'category_id' in GRAINS[f['grain']]]
        sql = 'SELECT d.*' + (',' + ','.join(flags) if flags else '') + ' FROM (' + with_derived + ') d'
        stage('join_features_' + day, lambda: con.execute('CREATE OR REPLACE TEMP TABLE manual_day_features AS ' + sql, coverage_params))
        if not initialized:
            con.execute('CREATE OR REPLACE TEMP TABLE manual_features AS SELECT * FROM manual_day_features WHERE false')
            initialized = True
        con.execute('INSERT INTO manual_features SELECT * FROM manual_day_features')
        rows.append({'anchor': anchor, 'pairs': con.execute('SELECT count(*) FROM manual_day_pairs').fetchone()[0],
                     'users': con.execute('SELECT count(*) FROM manual_day_users').fetchone()[0],
                     'items': con.execute('SELECT count(*) FROM manual_day_items').fetchone()[0]})
        budget_check()
    if not initialized:
        # Empty Q still produces a usable, typed output through a zero-row batch
        # in callers; fail explicitly rather than leave an old table in place.
        raise ValueError('No query anchors; empty-feature schema has no materialized batch')
    actual = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM manual_features').fetchone()
    if actual[0] != duplicates[0] or actual[0] != actual[1]:
        raise AssertionError('Feature joins changed fixed candidate identity')
    for f in registry['features']:
        if f['operator'] == 'ratio':
            invalid = con.execute(f'SELECT count(*) FROM manual_features WHERE "{f["name"]}"<0 OR "{f["name"]}">1').fetchone()[0]
        elif f['operator'] == 'recency_seconds':
            invalid = con.execute(f'SELECT count(*) FROM manual_features WHERE "{f["name"]}"<=0').fetchone()[0]
        else:
            invalid = con.execute(f'SELECT count(*) FROM manual_features WHERE "{f["name"]}"<0').fetchone()[0]
        if invalid:
            raise AssertionError('Feature semantic range violated: ' + f['name'])
    budget_check()
    return {'feature_rows': actual[0], 'core_features': len(registry['features']), 'daily_state': rows,
            'missing': _dict_rows(con.execute('SELECT ' + ','.join(
                f'count(*) FILTER(WHERE "{f["name"]}" IS NULL) AS "{f["name"]}"' for f in registry['features']) + ' FROM manual_features'))[0]}



def run(candidate_directory, registry_path, output_root, *, acceptance_path, max_queries=None, seconds=3600):
    """Verify accepted contents before a label-independent subset or full C run."""
    import datetime as dt
    import hashlib
    import time
    import uuid
    import duckdb
    from scripts.anchor_pilot import RunDeadline, StageLedger, directory_bytes, peak_rss_bytes, save_json
    from scripts.heuristic_baselines import verify_accepted_inputs
    from scripts.protocol_manifest import (build_run_manifest, canonical_json, sha256_file, write_run_manifest)

    started = time.monotonic()
    deadline = RunDeadline(seconds, started_at=started)
    root = ROOT.resolve()
    output_root = output_root.resolve()
    output_root.relative_to(root / 'artifacts')
    # The attempt exists before any source hash, registry read or connection.
    directory = output_root / ('attempt-' + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    temp = directory / 'temp'
    temp.mkdir()
    ledger = StageLedger(temp, deadline=deadline)
    report = dict(status='running', identity_status='preparation', stages=ledger.rows,
                  limits=dict(threads=2, duckdb_memory='2GB', max_spill='2GB', wall_seconds=seconds,
                              process_rss_stage_ceiling_bytes=8 * 2**30,
                              rss_enforcement='cooperative stage checks, not an OS kill'))
    con = timer = manifest = None
    def guard():
        deadline.check()
        if peak_rss_bytes() > 8 * 2**30:
            raise MemoryError('Process high-water RSS exceeded8GiB')
    def stage(name, operation):
        def checked():
            guard()
            value = operation()
            guard()
            return value
        return ledger(name, checked)
    def fingerprint(path):
        guard()
        digest = sha256_file(path)
        guard()
        return digest
    try:
        if max_queries is not None and (type(max_queries) is not int or not 1 <= max_queries <= 6000):
            raise ValueError('Diagnostic max_queries must be1–6000, or None for full input')
        candidate_directory, registry_path, acceptance_path = candidate_directory.resolve(), registry_path.resolve(), acceptance_path.resolve()
        registry_path.relative_to(root)
        acceptance_path.relative_to(root)
        registry = stage('load_registry', lambda: load_registry(registry_path))
        acceptance = stage('load_acceptance', lambda: json.loads(acceptance_path.read_text()))
        config, files, db, verified = stage('verify_accepted_provenance',
            lambda: verify_accepted_inputs(candidate_directory, acceptance, check=guard))
        # Check remaining declared pins too, including diagnostic output coverage.
        for name, digest in acceptance['fingerprints'].items():
            if name in verified:
                continue
            path = (root / name).resolve()
            path.relative_to(root)
            actual = stage('verify_extra_pin_' + str(len(verified)), lambda path=path: fingerprint(path))
            if actual != digest:
                raise ValueError('Accepted extra content fingerprint changed: ' + name)
            verified[name] = actual
        selection = dict(version=1, source_candidate_run=acceptance['candidate_run_id'],
                         query_order='sha256_query_id_then_query_id', max_queries=max_queries,
                         label_policy='not_read_for_selection_or_feature_materialization')
        selection_json = canonical_json(selection) + '\n'
        selection_id = hashlib.sha256(selection_json.encode()).hexdigest()
        selection_path = output_root / 'selections' / (selection_id + '.json')
        selection_path.parent.mkdir(parents=True, exist_ok=True)
        if selection_path.exists():
            if selection_path.read_text() != selection_json:
                raise ValueError('Existing selection specification changed')
        else:
            selection_path.write_text(selection_json)
        inputs = dict(verified)
        for path in [registry_path, acceptance_path, selection_path]:
            inputs[path.relative_to(root).as_posix()] = stage('fingerprint_' + path.name,
                                                          lambda path=path: fingerprint(path))
        code = stage('fingerprint_current_code', lambda: {name: fingerprint(root / name) for name in [
            'uv.lock', 'scripts/manual_features.py', 'scripts/heuristic_baselines.py', 'scripts/ranking_metrics.py',
            'scripts/candidate_pilot.py', 'scripts/anchor_pilot.py', 'scripts/protocol_manifest.py', 'scripts/temporal_contract.py']})
        manifest = build_run_manifest(config, code_hashes=code, input_hashes=inputs, components=[], artifact_refs={},
                                      created_at=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        identified = output_root / manifest['run_id']
        if identified.exists():
            raise FileExistsError('Existing identified run is preserved: ' + manifest['run_id'])
        directory.rename(identified)
        directory = identified
        temp = directory / 'temp'
        ledger.directory = temp
        report.update(run_id=manifest['run_id'], identity_status='identified',
                      candidate_run_id=acceptance['candidate_run_id'], anchor_run_id=acceptance['anchor_run_id'],
                      selection=selection, registry=registry, duckdb_version=duckdb.__version__,
                      accepted_fingerprint_count=len(verified))
        manifest['artifact_refs']['report'] = (directory / 'report.json').relative_to(root).as_posix()
        def open_source():
            nonlocal con
            con = duckdb.connect(str(db), read_only=True)
        stage('open_source_read_only', open_source)
        timer = deadline.interrupt_timer(con)
        ledger.connection = con
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='2GB'")
        con.execute('SET temp_directory=?', [str(temp)])
        con.execute('SET preserve_insertion_order=false')
        query_sql = 'CREATE TEMP TABLE pilot_queries AS SELECT * FROM read_parquet(?)'
        args = [str(files['queries'])]
        if max_queries is not None:
            query_sql += ' ORDER BY sha256(query_id),query_id LIMIT ?'
            args.append(max_queries)
        stage('load_selected_queries', lambda: con.execute(query_sql, args))
        stage('load_fixed_candidates', lambda: con.execute('''CREATE TEMP TABLE pilot_candidates AS
            SELECT c.* FROM read_parquet(?) c SEMI JOIN pilot_queries q USING(query_id)''', [str(files['candidates'])]))
        report['selected_queries'] = con.execute('SELECT count(*) FROM pilot_queries').fetchone()[0]
        report.update(create_manual_features(con, config, registry, stage=stage, budget_check=guard))
        path = directory / 'features.parquet'
        stage('export_features', lambda: con.execute('''COPY (
            SELECT * FROM manual_features ORDER BY query_id,product_id) TO ? (FORMAT PARQUET,COMPRESSION ZSTD)''', [str(path)]))
        manifest['artifact_refs']['features'] = path.relative_to(root).as_posix()
        report['artifact_bytes'] = path.stat().st_size
        report['output_sha256'] = stage('fingerprint_features', lambda: fingerprint(path))
        report['feature_columns'] = [r[0] for r in con.execute('DESCRIBE manual_features').fetchall()]
        guard()
        report['status'] = 'complete'
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if timer is not None:
            timer.cancel()
        if con is not None:
            con.close()
        report.update(seconds=time.monotonic() - started, process_peak_rss_bytes=peak_rss_bytes(),
                      temp_disk_bytes_after_close=directory_bytes(temp))
        save_json(directory / 'report.json', report)
        if manifest is not None and report.get('identity_status') == 'identified':
            write_run_manifest(manifest, directory / 'run.json')
        print(json.dumps(dict(status=report['status'], run_id=report.get('run_id'),
                              seconds=report['seconds'], report=str(directory / 'report.json'))), flush=True)
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-run', required=True, type=Path)
    parser.add_argument('--acceptance', required=True, type=Path)
    parser.add_argument('--registry', type=Path, default=ROOT / 'configs/features/manual-18.json')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'artifacts/manual-features')
    parser.add_argument('--max-queries', type=int, default=None)
    args = parser.parse_args()
    run(args.candidate_run, args.registry, args.output_root, acceptance_path=args.acceptance, max_queries=args.max_queries)


if __name__ == '__main__':
    main()
