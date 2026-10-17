"""Fixed-C heuristics with full-Y evaluation; production requires accepted fingerprints.

Recent-source-first orders the existing recent20 source. Last-view7d observes
views for ALL fixed candidate pairs, including candidates absent from recent20.
No ranking changes C, inserts positives, removes purchases or imputes old views.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from itertools import combinations
import json
from pathlib import Path
import time

import duckdb

from scripts.anchor_pilot import (RunDeadline, StageLedger, directory_bytes,
    peak_rss_bytes, save_json, utc)
from scripts.candidate_pilot import validate_queries
from scripts.protocol_manifest import (canonical_json, load_run_manifest,
    sha256_file, validate_protocol)
from scripts.ranking_metrics import (ESTIMANDS, QueryRanking, evaluate,
    paired_user_bootstrap)
from scripts.temporal_contract import label_is_mature, target_window

ROOT = Path(__file__).resolve().parents[1]
RANKERS = ('popularity', 'recent_source_first', 'last_view7d')
SPEC = {
    'version': 1, 'k': 20, 'window': '[t-7d,t)',
    'popularity': 'popularity_distinct_users DESC, product_id ASC',
    'recent_source_first': 'recent_source_rank ASC NULLS LAST, popularity DESC, product_id ASC; existing recent20 only',
    'last_view7d': 'max(view event_time) DESC NULLS LAST for all C pairs, popularity DESC, product_id ASC',
    'target': 'full independent Y; no positive insertion; censored excluded',
    'history_support': 'observed candidate-pair view in 7d only; not full user history',
}


@dataclass(frozen=True, slots=True)
class Candidate:
    product_id: int
    popularity: int
    recent_rank: int | None = None
    last_view: datetime | None = None


def rank_candidates(candidates, method):
    """Pure deterministic permutation of the exact supplied candidate IDs."""
    if method not in RANKERS:
        raise ValueError('Unknown ranker')
    rows = list(candidates)
    if len({c.product_id for c in rows}) != len(rows):
        raise ValueError('Duplicate candidate product IDs')
    for c in rows:
        if (type(c.product_id) is not int or type(c.popularity) is not int or c.popularity < 0
                or (c.recent_rank is not None and (type(c.recent_rank) is not int or c.recent_rank < 1))):
            raise ValueError('Invalid candidate ID/popularity/source rank')
        if c.last_view is not None and (not isinstance(c.last_view, datetime)
                or c.last_view.tzinfo is None or c.last_view.utcoffset() != timedelta(0)):
            raise ValueError('last_view must be explicit UTC')
    def key(c):
        fallback = (-c.popularity, c.product_id)
        if method == 'popularity':
            return fallback
        if method == 'recent_source_first':
            return (c.recent_rank is None, c.recent_rank or 0, *fallback)
        # Ordinal arithmetic preserves microseconds without float epoch rounding.
        stamp = c.last_view
        ticks = ((stamp.toordinal() * 86400 + stamp.hour * 3600 + stamp.minute * 60
                  + stamp.second) * 1000000 + stamp.microsecond) if stamp else 0
        return (stamp is None, -ticks, *fallback)
    return tuple(c.product_id for c in sorted(rows, key=key))


def validate_inputs(con, config):
    config = validate_protocol(config)
    validate_queries(con, config)
    if con.execute('SELECT count(*) FROM pilot_queries').fetchone()[0] > 6000:
        raise ValueError('Hard query budget exceeded')
    for anchor, declared in con.execute('SELECT anchor,label_is_mature FROM pilot_queries').fetchall():
        target = target_window(anchor.replace(tzinfo=timezone.utc), timedelta(hours=config['target']['horizon_hours']),
            include_anchor=config['target']['include_anchor'], include_end=config['target']['include_end'])
        expected = label_is_mature(target, available_before=utc(config['source']['end']),
            availability_delay=timedelta(seconds=config['target']['availability_delay_seconds']))
        if declared != expected:
            raise ValueError('Label maturity declaration contradicts protocol')
    n, unique = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM pilot_candidates').fetchone()
    bad = con.execute('''SELECT count(*) FROM pilot_candidates c LEFT JOIN pilot_queries q USING(query_id)
        WHERE q.query_id IS NULL OR c.product_id IS NULL OR c.popularity_distinct_users IS NULL
        OR c.popularity_distinct_users<0 OR (c.recent_source_rank IS NOT NULL AND c.recent_source_rank<1)''').fetchone()[0]
    overflow = con.execute('''SELECT count(*) FROM (SELECT query_id,count(*) n FROM pilot_candidates
        GROUP BY query_id HAVING n>?)''', [config['candidates']['max_unique']]).fetchone()[0]
    if bad or overflow or n != unique or n > min(1320000, config['budget']['max_candidate_pairs']):
        raise ValueError('Invalid fixed candidate population/budget')
    n, unique = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM pilot_labels').fetchone()
    bad = con.execute('''SELECT count(*) FROM pilot_labels l LEFT JOIN pilot_queries q USING(query_id)
        WHERE q.query_id IS NULL OR NOT q.label_is_mature OR l.product_id IS NULL
        OR l.catalog_seen_before IS NULL OR l.pair_seen_before IS NULL
        OR (l.pair_seen_before AND NOT l.catalog_seen_before)''').fetchone()[0]
    if bad or n != unique:
        raise ValueError('Invalid full binary targets')
    bad = con.execute('''SELECT count(*) FROM pilot_labels l JOIN pilot_candidates c USING(query_id,product_id)
        WHERE NOT l.catalog_seen_before''').fetchone()[0]
    if bad:
        raise ValueError('Candidate target contradicts catalog coverage')


def add_last_views(con, config, *, stage=lambda name, operation: operation()):
    """Bound scans by distinct anchor and selected fixed pairs; no user×catalog."""
    validate_inputs(con, config)
    con.execute('CREATE OR REPLACE TEMP TABLE heuristic_views(query_id VARCHAR,product_id BIGINT,last_view TIMESTAMP)')
    plans = []
    for (anchor,) in con.execute('SELECT DISTINCT anchor FROM pilot_queries ORDER BY anchor').fetchall():
        con.execute('''CREATE OR REPLACE TEMP TABLE heuristic_day_pairs AS SELECT c.query_id,q.user_id,c.product_id
            FROM pilot_candidates c JOIN pilot_queries q USING(query_id) WHERE q.anchor=?''', [anchor])
        sql = '''SELECT c.query_id,c.product_id,max(e.event_time) last_view FROM events e
            JOIN heuristic_day_pairs c ON e.user_id=c.user_id AND e.product_id=c.product_id
            WHERE e.event_type='view' AND e.event_time>=? AND e.event_time<? GROUP BY c.query_id,c.product_id'''
        params = [anchor - timedelta(days=7), anchor]
        plans.append({'anchor': anchor, 'scan_start': params[0], 'scan_end_exclusive': anchor,
            'selected_pairs': con.execute('SELECT count(*) FROM heuristic_day_pairs').fetchone()[0],
            'explain_estimate_only': '\n'.join(row[1] for row in con.execute('EXPLAIN '+sql, params).fetchall())})
        stage('last_views_'+anchor.strftime('%Y-%m-%d'), lambda: con.execute('INSERT INTO heuristic_views '+sql, params))
    con.execute('''CREATE OR REPLACE TEMP TABLE heuristic_candidates AS SELECT c.*,v.last_view
        FROM pilot_candidates c LEFT JOIN heuristic_views v USING(query_id,product_id)''')
    return plans


def make_rankings(con):
    """Retain every Q, including mature-empty C/Y and censored Q."""
    queries = con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM pilot_queries ORDER BY query_id').fetchall()
    labels = defaultdict(set)
    for qid, product in con.execute('SELECT query_id,product_id FROM pilot_labels').fetchall():
        labels[qid].add(product)
    candidates = defaultdict(list)
    cursor = con.execute('''SELECT query_id,product_id,popularity_distinct_users,recent_source_rank,last_view
        FROM heuristic_candidates ORDER BY query_id,product_id''')
    while batch := cursor.fetchmany(10000):
        for qid, product, popularity, recent, last in batch:
            candidates[qid].append(Candidate(product, popularity, recent,
                last.replace(tzinfo=timezone.utc) if last is not None else None))
    result = {name: [] for name in RANKERS}
    for qid, user, anchor, mature in queries:
        pool = candidates[qid]
        expected = {c.product_id for c in pool}
        for name in RANKERS:
            ordered = rank_candidates(pool, name)
            if len(ordered) != len(expected) or set(ordered) != expected:
                raise ValueError('Ranker changed fixed C')
            result[name].append(QueryRanking(qid, user, ordered, labels[qid] if mature else None, mature))
    return result


def report_rankings(con, rankings, *, replicates=1000, seed=2026,
                    stage=lambda name, operation: operation()):
    """Query slices keep full Y; label slices count hits using original rankings."""
    query_ids = defaultdict(set)
    for qid, day in con.execute('SELECT query_id,CAST(anchor AS DATE) FROM pilot_queries').fetchall():
        query_ids['day:'+str(day)].add(qid)
    for qid, support in con.execute('''SELECT q.query_id,bool_or(c.last_view IS NOT NULL)
        FROM pilot_queries q LEFT JOIN heuristic_candidates c USING(query_id) GROUP BY q.query_id''').fetchall():
        query_ids['any_C_pair_view7d' if support else 'no_C_pair_view7d'].add(qid)
    label_slices = {key: set() for key in ('repeat', 'new_pair', 'catalog_seen', 'catalog_cold')}
    for qid, pid, repeat, catalog in con.execute('SELECT query_id,product_id,pair_seen_before,catalog_seen_before FROM pilot_labels').fetchall():
        for key in ('repeat' if repeat else 'new_pair', 'catalog_seen' if catalog else 'catalog_cold'):
            label_slices[key].add((qid, pid))
            query_ids['any_target:'+key].add(qid)
    targets, retrieved, catalog = con.execute('''SELECT count(*),count(c.product_id),
        count(*) FILTER(WHERE l.catalog_seen_before) FROM pilot_labels l
        LEFT JOIN pilot_candidates c USING(query_id,product_id)''').fetchone()
    ceiling_macro = con.execute('''SELECT avg(retrieved*1.0/n) FROM (
        SELECT l.query_id,count(*) n,count(c.product_id) retrieved FROM pilot_labels l
        LEFT JOIN pilot_candidates c USING(query_id,product_id) GROUP BY l.query_id)''').fetchone()[0]
    result = {'retrieval_ceiling': {'unit': 'full-Y target pair', 'all_targets': targets,
        'candidate_targets': retrieved, 'catalog_targets': catalog,
        'candidate_recall_micro': retrieved/targets if targets else None,
        'catalog_recall_micro': catalog/targets if targets else None,
        'candidate_recall_positive_query_macro': ceiling_macro},
        'k': 20, 'slice_units': {'query': 'overlapping Q subsets; full Y remains denominator',
        'label': 'target (query,product) micro recall@20; original ranks and complete full-Y main metrics'},
        'evaluations': {}, 'query_slices': {}, 'label_slices': {}, 'paired_user_bootstrap': [],
        'history_support_definition': SPEC['history_support'],
        'CI_limitations': 'User clusters do not capture common time shocks; small positive support is not promotion evidence.'}
    for name, rows in rankings.items():
        result['evaluations'][name] = asdict(evaluate(rows, 20))
        result['query_slices'][name] = {key: asdict(evaluate([r for r in rows if r.query_id in ids], 20))
            for key, ids in sorted(query_ids.items())}
        hits = {(r.query_id, pid) for r in rows if r.mature for pid in r.ranked_items[:20] if pid in r.targets}
        result['label_slices'][name] = {key: {'unit': 'target pair', 'target_count': len(ids),
            'hit_count': len(hits & ids), 'recall_at20': len(hits & ids)/len(ids) if ids else None}
            for key, ids in sorted(label_slices.items())}
    for left, right in combinations(RANKERS, 2):
        for metric in ('ndcg', 'recall'):
            for estimand in ESTIMANDS:
                summary = asdict(stage('bootstrap_'+left+'_'+right+'_'+metric+'_'+estimand,
                    lambda: paired_user_bootstrap(rankings[left], rankings[right], 20, metric=metric,
                        estimand=estimand, replicates=replicates, seed=seed)))
                summary.pop('samples')
                summary.update(left=left, right=right, defined_draws=replicates-summary['undefined_draws'])
                result['paired_user_bootstrap'].append(summary)
    return result


def verify_accepted_inputs(candidate_directory, acceptance, *, check=lambda: None):
    """Coordinator approval pins actual contents, including output artifacts.

    Every expected upstream code/config/input hash is checked against disk;
    004 must consume exactly the independently generated 003 Q/Y artifacts.
    Acceptance is an explicit coordinator artifact, never inferred from a path.
    """
    if set(acceptance) != {'version', 'approved', 'candidate_run_id', 'anchor_run_id', 'fingerprints'} or type(acceptance['version']) is not int or acceptance['version'] != 1 or acceptance['approved'] is not True:
        raise ValueError('Explicit coordinator approval required')
    pins = acceptance['fingerprints']
    if not isinstance(pins, dict) or not pins:
        raise ValueError('Accepted fingerprints required')
    verified = {}
    def verify(path, expected=None):
        path = Path(path).resolve()
        name = path.relative_to(ROOT.resolve()).as_posix()
        pin = pins.get(name)
        if not isinstance(pin, str) or len(pin) != 64 or (expected is not None and pin != expected):
            raise ValueError('Missing/mismatched accepted fingerprint: '+name)
        check()
        actual = sha256_file(path)
        check()
        if actual != pin:
            raise ValueError('Content fingerprint changed: '+name)
        verified[name] = actual
        return path
    candidate_directory = candidate_directory.resolve()
    cm_path = verify(candidate_directory/'run.json')
    cm = load_run_manifest(cm_path)
    cr_path = verify(candidate_directory/'report.json')
    cr = json.loads(cr_path.read_text())
    if cm['run_id'] != acceptance['candidate_run_id'] or cr.get('status') != 'complete' or cr.get('run_id') != cm['run_id']:
        raise ValueError('Only matching complete accepted candidate runs')
    anchor_id = acceptance['anchor_run_id']
    if cr.get('anchor_run_id') != anchor_id:
        raise ValueError('Candidate anchor lineage mismatch')
    # Find the actual upstream anchor manifest among recorded inputs, not by run-directory naming.
    anchor_paths = [ROOT/p for p in cm['identity']['input_hashes'] if p.endswith('/run.json')]
    if len(anchor_paths) != 1:
        raise ValueError('Expected one anchor manifest input')
    am_path = verify(anchor_paths[0], cm['identity']['input_hashes'][anchor_paths[0].relative_to(ROOT).as_posix()])
    am = load_run_manifest(am_path)
    ar = json.loads(verify(am_path.parent/'report.json').read_text())
    if am['run_id'] != anchor_id or ar.get('run_id') != anchor_id or ar.get('status') != 'complete':
        raise ValueError('Only matching complete accepted independent anchor runs')
    if am['identity']['protocol'] != cm['identity']['protocol']:
        raise ValueError('Upstream protocols differ')
    for manifest in (am, cm):
        for group in ('code_hashes', 'input_hashes'):
            for name, digest in manifest['identity'][group].items():
                verify(ROOT/name, digest)
    required_anchor = {'uv.lock', 'scripts/anchor_pilot.py', 'scripts/protocol_manifest.py', 'scripts/temporal_contract.py'}
    if not required_anchor <= set(am['identity']['code_hashes']) or not required_anchor | {'scripts/candidate_pilot.py'} <= set(cm['identity']['code_hashes']):
        raise ValueError('Missing upstream code fingerprints')
    files = {name: verify(ROOT/am['artifact_refs'][name]) for name in ('queries', 'labels')}
    files['candidates'] = verify(ROOT/cm['artifact_refs']['candidates'])
    for name in ('queries', 'labels'):
        relative = files[name].relative_to(ROOT).as_posix()
        if cm['identity']['input_hashes'].get(relative) != verified[relative]:
            raise ValueError('004 did not consume exact003 '+name)
    source = am['identity']['input_hashes']
    if len(source) != 1:
        raise ValueError('Expected exactly one source DB')
    db = verify(ROOT/next(iter(source)), next(iter(source.values())))
    return cm['identity']['protocol'], files, db, verified


def run(candidate_directory, acceptance_path, output_root, *, seconds=1800, replicates=1000):
    if not 0 < seconds <= 1800 or type(replicates) is not int or not 1 <= replicates <= 1000:
        raise ValueError('Invalid bounded run budget')
    started = time.monotonic()
    deadline = RunDeadline(seconds, started_at=started)
    output_root = output_root.resolve()
    output_root.relative_to((ROOT/'artifacts/heuristic-baselines').resolve())
    # Persist failures before any expensive provenance scans, even if not yet identified.
    directory = output_root/('attempt-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    directory.mkdir(parents=True, exist_ok=False)
    temp = directory/'temp'
    temp.mkdir()
    report = {'status': 'running', 'spec': SPEC, 'stages': [], 'limits': {'seconds': seconds,
        'threads': 2, 'engine_memory': '2GB', 'spill': '2GB', 'rss_bytes': 6*2**30,
        'rss_enforcement': 'cooperative stage/check gates, not an OS kill'}}
    ledger = StageLedger(temp, deadline=deadline)
    report['stages'] = ledger.rows
    con = timer = None
    primary_error = None
    def guard():
        deadline.check()
        if peak_rss_bytes() > 6*2**30:
            raise MemoryError('Process high-water RSS exceeded6GiB')
    def stage(name, operation):
        def checked():
            guard()
            value = operation()
            guard()
            return value
        return ledger(name, checked)
    try:
        acceptance = json.loads(acceptance_path.read_text())
        report['acceptance_schema_version'] = 1
        report['requested_candidate_directory'] = str(candidate_directory)
        report['accepted_declarations'] = acceptance
        report['acceptance_sha256'] = stage('fingerprint_acceptance', lambda: sha256_file(acceptance_path))
        config, files, db, hashes = stage('verify_accepted_provenance',
            lambda: verify_accepted_inputs(candidate_directory, acceptance, check=guard))
        code = {p: sha256_file(ROOT/p) for p in ['uv.lock', 'scripts/heuristic_baselines.py',
            'scripts/ranking_metrics.py', 'scripts/anchor_pilot.py', 'scripts/candidate_pilot.py',
            'scripts/protocol_manifest.py', 'scripts/temporal_contract.py']}
        import hashlib
        identity = {'spec': SPEC, 'protocol': config, 'accepted_inputs': hashes, 'code_hashes': code,
            'bootstrap': {'replicates': replicates, 'seed': 2026}, 'acceptance_sha256': report['acceptance_sha256']}
        run_id = hashlib.sha256(canonical_json(identity).encode()).hexdigest()
        report.update(run_id=run_id, identity=identity)
        save_json(directory/'identity.json', identity)
        identified = output_root/run_id
        directory.rename(identified)
        directory = identified
        temp = directory/'temp'
        ledger.directory = temp
        con = duckdb.connect(str(db), read_only=True)
        timer = deadline.interrupt_timer(con)
        ledger.connection = con
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='2GB'")
        con.execute('SET temp_directory=?', [str(temp)])
        for name, path in files.items():
            stage('load_'+name, lambda name=name, path=path: con.execute(
                f'CREATE TEMP TABLE pilot_{name} AS SELECT * FROM read_parquet(?)', [str(path)]))
        report['scan_plans'] = stage('materialize_last_views', lambda: add_last_views(con, config, stage=stage))
        report['row_counts'] = {table: con.execute('SELECT count(*) FROM '+table).fetchone()[0]
            for table in ('pilot_queries', 'pilot_labels', 'pilot_candidates', 'heuristic_views', 'heuristic_candidates')}
        rankings = stage('rank_fixed_C', lambda: make_rankings(con))
        metrics = stage('evaluate_full_Y', lambda: report_rankings(con, rankings, replicates=replicates, stage=stage))
        # Ordered all-C output, including positions past20; raw identifiers stay ignored.
        output = directory/'rankings.jsonl'
        def export():
            with output.open('w') as handle:
                for method, rows in rankings.items():
                    for row in rows:
                        guard()
                        handle.write(json.dumps({'ranker': method, 'query_id': row.query_id,
                            'ordered_all_C': row.ranked_items})+'\n')
        stage('export_all_C_rankings', export)
        report['ranking_output_counts'] = {'query_records': sum(len(rows) for rows in rankings.values()),
            'ordered_pairs': sum(len(row.ranked_items) for rows in rankings.values() for row in rows)}
        report['scorer_columns'] = {'existing': ['popularity_distinct_users', 'recent_source_rank'],
            'derived': ['last_view7d_timestamp'], 'derived_count': 1}
        report['artifact_hashes'] = {'rankings.jsonl': stage('fingerprint_rankings', lambda: sha256_file(output))}
        guard()
        report.update(status='complete', metrics=metrics)
    except BaseException as error:
        primary_error = error
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if timer is not None:
            timer.cancel()
        cleanup_error = None
        try:
            if con is not None:
                con.close()
        except BaseException as error:
            cleanup_error = error
            report.update(status='failed', cleanup_errors=[dict(operation='close_connection',
                          error_type=type(error).__name__, error=str(error))])
            if primary_error is None:
                report.update(error_type=type(error).__name__, error=str(error))
        profiles = [row['engine_profile'] for row in ledger.rows if 'engine_profile' in row]
        report['engine_peak_buffer_memory_bytes'] = max((p.get('system_peak_buffer_memory') or 0 for p in profiles), default=0)
        report['engine_peak_spill_bytes'] = max((p.get('system_peak_temp_dir_size') or 0 for p in profiles), default=0)
        report.update(seconds=time.monotonic()-started, process_peak_rss_bytes=peak_rss_bytes(),
            temp_disk_bytes_after_close=directory_bytes(temp))
        save_json(directory/'report.json', report)
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-run', type=Path, required=True)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=ROOT/'artifacts/heuristic-baselines')
    args = parser.parse_args()
    run(args.candidate_run, args.acceptance, args.output_root)


if __name__ == '__main__':
    main()
