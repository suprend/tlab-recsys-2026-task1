"""Independent row oracle and bounded synthetic end-to-end acceptance tests."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from scripts import heuristic_baselines as h
from scripts.protocol_manifest import build_run_manifest, load_protocol, sha256_file, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
T = datetime(2019, 10, 8)
UTC = timezone.utc


def config():
    return load_protocol(ROOT/'configs/protocols/clock-48h.json')


def tables(con):
    con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT)')
    con.execute('CREATE TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
    con.execute('CREATE TABLE pilot_candidates(query_id VARCHAR,product_id BIGINT,popularity_distinct_users BIGINT,recent_source_rank BIGINT)')
    con.execute('CREATE TABLE pilot_labels(query_id VARCHAR,product_id BIGINT,pair_seen_before BOOLEAN,catalog_seen_before BOOLEAN)')


def fixture(con):
    tables(con)
    con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,?)', [
        ('positive', 1, T, True), ('empty', 2, T, True), ('emptyC', 3, T, True)])
    con.executemany('INSERT INTO pilot_candidates VALUES (?,?,?,?)', [
        ('positive', 10, 9, None), ('positive', 20, 2, 1), ('positive', 30, 2, None),
        ('positive', 40, 0, None), ('positive', 50, 1, None), ('empty', 10, 9, None)])
    con.executemany('INSERT INTO pilot_labels VALUES (?,?,?,?)', [
        ('positive', 10, True, True), ('positive', 999, False, False), ('emptyC', 500, False, True)])
    con.executemany('INSERT INTO events VALUES (?,?,?,?)', [
        (T-timedelta(days=1), 'purchase', 20, 1),  # recent source does not mean a view
        (T-timedelta(days=2), 'view', 10, 1),
        (T-timedelta(hours=1), 'view', 30, 1),    # view absent from recent20 is still scored
        (T-timedelta(days=7), 'view', 40, 1),    # inclusive lower bound
        (T-timedelta(days=7, seconds=1), 'view', 50, 1),
        (T, 'view', 20, 1),                    # all peers excluded
        (T+timedelta(seconds=1), 'view', 50, 1),
        (T-timedelta(minutes=1), 'view', 10, 99)])


class RankerTests(unittest.TestCase):
    def test_hand_golden_ties_and_exact_C(self):
        rows = [h.Candidate(30, 2), h.Candidate(20, 2, 1), h.Candidate(10, 9)]
        self.assertEqual(h.rank_candidates(rows, 'popularity'), (10, 20, 30))
        self.assertEqual(h.rank_candidates(rows, 'recent_source_first'), (20, 10, 30))
        self.assertEqual(h.rank_candidates([], 'last_view7d'), ())
        stamp = T.replace(tzinfo=UTC)
        rows = [h.Candidate(20, 1, None, stamp), h.Candidate(10, 1, None, stamp), h.Candidate(30, 99)]
        self.assertEqual(h.rank_candidates(rows, 'last_view7d'), (10, 20, 30))
        for method in h.RANKERS:
            self.assertEqual(set(h.rank_candidates(rows, method)), {10, 20, 30})

    def test_reject_duplicates_and_malformed_fields(self):
        cases = [[h.Candidate(1, 1), h.Candidate(1, 1)], [h.Candidate(1, -1)],
                 [h.Candidate(True, 1)], [h.Candidate(1, 1, 0)], [h.Candidate(1, 1, None, T)]]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                h.rank_candidates(rows, 'popularity')
        with self.assertRaises(ValueError):
            h.rank_candidates([], 'unknown')

    def test_microsecond_ordering(self):
        self.assertEqual(h.rank_candidates([
            h.Candidate(10, 99, None, T.replace(tzinfo=UTC)),
            h.Candidate(20, 1, None, T.replace(tzinfo=UTC)+timedelta(microseconds=1))], 'last_view7d'), (20, 10))


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(':memory:')
        self.con.execute('SET threads=2')
        fixture(self.con)
        self.addCleanup(self.con.close)

    def test_views_all_C_full_targets_and_slice_units(self):
        plans = h.add_last_views(self.con, config())
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]['selected_pairs'], 6)
        rows = h.make_rankings(self.con)
        by_id = {name: {r.query_id: r for r in values} for name, values in rows.items()}
        self.assertEqual(by_id['popularity']['positive'].ranked_items, (10, 20, 30, 50, 40))
        self.assertEqual(by_id['recent_source_first']['positive'].ranked_items, (20, 10, 30, 50, 40))
        self.assertEqual(by_id['last_view7d']['positive'].ranked_items, (30, 10, 40, 20, 50))
        self.assertEqual(by_id['last_view7d']['emptyC'].ranked_items, ())
        self.assertEqual(by_id['last_view7d']['positive'].targets, {10, 999})
        report = h.report_rankings(self.con, rows, replicates=12)
        scores = report['evaluations']['last_view7d']
        self.assertEqual(scores['query_count'], 3)
        self.assertEqual(scores['nonempty_fraction'], 2/3)
        self.assertAlmostEqual(scores['conditional_macro_query']['recall'], 1/4)
        self.assertAlmostEqual(scores['all_query_zero']['recall'], 1/6)
        self.assertEqual(scores['conditional_user_macro']['recall'], 1/4)
        self.assertEqual(scores['all_user_macro_zero']['recall'], 1/6)
        cold = report['label_slices']['last_view7d']['catalog_cold']
        self.assertEqual(cold, {'unit': 'target pair', 'target_count': 1, 'hit_count': 0, 'recall_at20': 0})
        self.assertEqual(report['label_slices']['last_view7d']['repeat']['recall_at20'], 1)
        sliced = report['query_slices']['last_view7d']['any_target:repeat']
        self.assertEqual(sliced['conditional_macro_query']['recall'], 1/2)  # full Y, not repeat-only Y
        self.assertEqual(report['retrieval_ceiling']['all_targets'], 3)
        self.assertEqual(report['retrieval_ceiling']['candidate_recall_micro'], 1/3)
        self.assertEqual(report['retrieval_ceiling']['candidate_recall_positive_query_macro'], 1/4)
        self.assertEqual(len(report['paired_user_bootstrap']), 24)
        self.assertTrue(all(r['user_count'] == 3 and r['defined_draws']+r['undefined_draws'] == 12
                            for r in report['paired_user_bootstrap']))

    def test_independent_row_oracle_randomized_and_permutation_future_invariance(self):
        rng = random.Random(71)
        events = [(T-timedelta(seconds=rng.randint(-100, 800000)), rng.choice(['view', 'cart', 'purchase']),
                   rng.choice([10, 20, 30, 40, 50, 60]), rng.choice([1, 2, 99])) for _ in range(140)]
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?)', events)
        all_events = self.con.execute('SELECT * FROM events').fetchall()
        pairs = self.con.execute('SELECT * FROM pilot_candidates').fetchall()
        # Independent literal row iteration and comparator, no production helper.
        last = {}
        for qid, product, pop, recent in pairs:
            user = 1 if qid == 'positive' else 2
            eligible = [e[0] for e in all_events if e[3] == user and e[2] == product
                        and e[1] == 'view' and T-timedelta(days=7) <= e[0] < T]
            last[qid, product] = max(eligible) if eligible else None
        h.add_last_views(self.con, config())
        actual = h.make_rankings(self.con)
        for method, rankings in actual.items():
            for query in rankings:
                pool = [p for p in pairs if p[0] == query.query_id]
                if method == 'popularity':
                    key = lambda p: (-p[2], p[1])
                elif method == 'recent_source_first':
                    key = lambda p: (p[3] is None, p[3] or 0, -p[2], p[1])
                else:
                    key = lambda p: (last[p[0], p[1]] is None,
                        -(last[p[0], p[1]]-datetime(1970, 1, 1)).total_seconds() if last[p[0], p[1]] else 0, -p[2], p[1])
                self.assertEqual(query.ranked_items, tuple(p[1] for p in sorted(pool, key=key)))
        # Replace input row order, duplicate raw peers, add same-second/future events.
        rng.shuffle(all_events)
        self.con.execute('DELETE FROM events')
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?)', all_events+all_events[:10]+[
            (T, 'view', 50, 1), (T+timedelta(days=7), 'view', 20, 1)])
        h.add_last_views(self.con, config())
        self.assertEqual(actual, h.make_rankings(self.con))

    def test_shortlist_cutoff_and_positive_outside_C_hand_golden(self):
        self.con.execute('DELETE FROM pilot_candidates')
        self.con.execute('DELETE FROM pilot_labels')
        self.con.executemany('INSERT INTO pilot_candidates VALUES (?,?,?,NULL)',
            [('positive', product, 100-product) for product in range(1, 24)])
        self.con.executemany('INSERT INTO pilot_labels VALUES (?,?,false,true)',
            [('positive', product) for product in (1, 23, 99)])
        h.add_last_views(self.con, config())
        rows = h.make_rankings(self.con)
        report = h.report_rankings(self.con, rows, replicates=3)
        metrics = report['evaluations']['popularity']['conditional_macro_query']
        self.assertAlmostEqual(metrics['recall'], 1/3)
        self.assertAlmostEqual(metrics['ndcg'], 0.46927872602275644)
        positive = next(q for q in rows['popularity'] if q.query_id == 'positive')
        self.assertEqual(len(positive.ranked_items), 23)
        self.assertEqual(positive.ranked_items[-1], 23)  # exported all C, even past cutoff
        self.assertNotIn(99, positive.ranked_items)

    def test_empty_population_and_zero_positive_cohorts(self):
        self.con.execute('DELETE FROM pilot_labels')
        h.add_last_views(self.con, config())
        report = h.report_rankings(self.con, h.make_rankings(self.con), replicates=4)
        for summary in report['paired_user_bootstrap']:
            if summary['estimand'].startswith('conditional'):
                self.assertEqual(summary['defined_draws'], 0)
                self.assertIsNone(summary['interval_95'])
        self.assertEqual(report['label_slices']['popularity']['repeat']['target_count'], 0)
        self.assertIsNone(report['label_slices']['popularity']['repeat']['recall_at20'])
        self.con.execute('DELETE FROM pilot_candidates')
        self.con.execute('DELETE FROM pilot_queries')
        self.assertEqual(h.add_last_views(self.con, config()), [])
        report = h.report_rankings(self.con, h.make_rankings(self.con), replicates=2)
        self.assertEqual(report['evaluations']['popularity']['query_count'], 0)
        self.assertTrue(all(r['user_count'] == 0 for r in report['paired_user_bootstrap']))

    def test_distinct_anchor_windows_not_one_global_cutoff(self):
        self.con.execute("INSERT INTO pilot_queries VALUES ('next',1,?,true)", [T+timedelta(days=1)])
        self.con.execute("INSERT INTO pilot_candidates VALUES ('next',20,2,NULL)")
        self.con.execute("INSERT INTO events VALUES (?,'view',20,1)", [T+timedelta(hours=1)])
        h.add_last_views(self.con, config())
        views = dict(self.con.execute('SELECT query_id,last_view FROM heuristic_views WHERE product_id=20').fetchall())
        self.assertNotIn('positive', views)
        self.assertEqual(views['next'], T+timedelta(hours=1))

    def test_maturity_duplicate_orphan_and_target_integrity_rejections(self):
        mutations = [
            "UPDATE pilot_queries SET label_is_mature=false WHERE query_id='empty'",
            "INSERT INTO pilot_candidates VALUES ('positive',10,9,NULL)",
            "INSERT INTO pilot_candidates VALUES ('orphan',10,9,NULL)",
            "INSERT INTO pilot_labels VALUES ('positive',10,true,true)",
            "INSERT INTO pilot_labels VALUES ('orphan',10,true,true)",
            "UPDATE pilot_labels SET catalog_seen_before=false WHERE product_id=10",
            "UPDATE pilot_queries SET anchor=anchor+INTERVAL '1 hour' WHERE query_id='empty'",
        ]
        for sql in mutations:
            with self.subTest(sql=sql):
                self.con.execute('BEGIN')
                self.con.execute(sql)
                with self.assertRaises(ValueError):
                    h.validate_inputs(self.con, config())
                self.con.execute('ROLLBACK')

    def test_censored_seam_keeps_Q_and_uses_no_partial_Y(self):
        # v1 protocol deliberately permits only mature pilots; seam remains censor-safe.
        self.con.execute("UPDATE pilot_queries SET label_is_mature=false WHERE query_id='empty'")
        self.con.execute('CREATE TABLE heuristic_candidates AS SELECT *,NULL::TIMESTAMP last_view FROM pilot_candidates')
        rows = h.make_rankings(self.con)
        empty = next(q for q in rows['popularity'] if q.query_id == 'empty')
        self.assertFalse(empty.mature)
        self.assertIsNone(empty.targets)
        report = h.report_rankings(self.con, rows, replicates=3)
        self.assertEqual(report['evaluations']['popularity']['censored_query_count'], 1)
        self.assertEqual(report['evaluations']['popularity']['mature_query_count'], 2)


class ProvenanceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.patch = patch.object(h, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.anchor = self.root/'artifacts/anchor-pilot/source'
        self.candidate = self.root/'artifacts/candidate-pilot/pool'
        self.anchor.mkdir(parents=True)
        self.candidate.mkdir(parents=True)
        (self.root/'scripts').mkdir()
        names = ['uv.lock', 'scripts/heuristic_baselines.py', 'scripts/ranking_metrics.py',
                 'scripts/anchor_pilot.py', 'scripts/candidate_pilot.py',
                 'scripts/protocol_manifest.py', 'scripts/temporal_contract.py']
        for name in names:
            (self.root/name).write_text('synthetic code pin '+name)
        self.db = self.root/'source.duckdb'
        con = duckdb.connect(str(self.db))
        fixture(con)
        for table, directory in [('queries', self.anchor), ('labels', self.anchor), ('candidates', self.candidate)]:
            con.execute(f'COPY pilot_{table} TO ? (FORMAT PARQUET)', [str(directory/(table+'.parquet'))])
        con.close()
        common = {name: sha256_file(self.root/name) for name in names if name not in
                  ['scripts/heuristic_baselines.py', 'scripts/ranking_metrics.py', 'scripts/candidate_pilot.py']}
        am = build_run_manifest(config(), code_hashes=common,
            input_hashes={'source.duckdb': sha256_file(self.db)}, components=[],
            artifact_refs={name: (self.anchor/(name+'.parquet')).relative_to(self.root).as_posix()
                           for name in ('queries', 'labels')}, created_at='2026-10-15T00:00:00Z')
        write_run_manifest(am, self.anchor/'run.json')
        (self.anchor/'report.json').write_text(json.dumps({'status': 'complete', 'run_id': am['run_id']}))
        inputs = {'source.duckdb': sha256_file(self.db)}
        for name in ['run.json', 'report.json', 'queries.parquet', 'labels.parquet']:
            path = self.anchor/name
            inputs[path.relative_to(self.root).as_posix()] = sha256_file(path)
        cm = build_run_manifest(config(), code_hashes={**common,
            'scripts/candidate_pilot.py': sha256_file(self.root/'scripts/candidate_pilot.py')},
            input_hashes=inputs, components=[], artifact_refs={
                'candidates': (self.candidate/'candidates.parquet').relative_to(self.root).as_posix()},
            created_at='2026-10-15T00:00:00Z')
        write_run_manifest(cm, self.candidate/'run.json')
        (self.candidate/'report.json').write_text(json.dumps({'status': 'complete', 'run_id': cm['run_id'],
                                                             'anchor_run_id': am['run_id']}))
        pins = {path.relative_to(self.root).as_posix(): sha256_file(path)
                for path in self.root.rglob('*') if path.is_file()}
        self.acceptance = {'version': 1, 'approved': True, 'anchor_run_id': am['run_id'],
                           'candidate_run_id': cm['run_id'], 'fingerprints': pins}
        self.acceptance_path = self.root/'acceptance.json'
        self.acceptance_path.write_text(json.dumps(self.acceptance))

    def test_synthetic_accepted_end_to_end_persists_costs_identity_all_C(self):
        report = h.run(self.candidate, self.acceptance_path, self.root/'artifacts/heuristic-baselines', replicates=3)
        self.assertEqual(report['status'], 'complete')
        directory = self.root/'artifacts/heuristic-baselines'/report['run_id']
        stored = json.loads((directory/'report.json').read_text())
        self.assertEqual(stored['row_counts']['pilot_candidates'], 6)
        self.assertEqual(stored['ranking_output_counts'], {'query_records': 9, 'ordered_pairs': 18})
        self.assertGreater(stored['engine_peak_buffer_memory_bytes'], 0)
        self.assertIn('uv.lock', stored['identity']['code_hashes'])
        self.assertEqual(stored['metrics']['evaluations']['popularity']['query_count'], 3)
        self.assertTrue(any('engine_profile' in row for row in stored['stages']))
        self.assertTrue(all(row['status'] == 'complete' for row in stored['stages']))
        self.assertTrue(all(row['process_peak_rss_bytes'] > 0 for row in stored['stages']))
        records = [json.loads(line) for line in (directory/'rankings.jsonl').read_text().splitlines()]
        self.assertEqual(len(records), 9)
        for method in h.RANKERS:
            rows = [r for r in records if r['ranker'] == method]
            self.assertEqual(sum(len(r['ordered_all_C']) for r in rows), 6)
            self.assertEqual({r['query_id'] for r in rows}, {'positive', 'empty', 'emptyC'})
        self.assertEqual(sha256_file(directory/'rankings.jsonl'), stored['artifact_hashes']['rankings.jsonl'])

    def test_tampered_artifact_code_report_and_missing_pins_reject(self):
        for name in ['artifacts/anchor-pilot/source/queries.parquet',
                     'artifacts/anchor-pilot/source/labels.parquet',
                     'artifacts/candidate-pilot/pool/candidates.parquet',
                     'scripts/anchor_pilot.py', 'uv.lock',
                     'artifacts/candidate-pilot/pool/report.json', 'source.duckdb']:
            path = self.root/name
            original = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(original+b'changed')
                with self.assertRaises(ValueError):
                    h.verify_accepted_inputs(self.candidate, self.acceptance)
                path.write_bytes(original)
        for key in ('approved', 'version'):
            altered = deepcopy(self.acceptance)
            altered[key] = False if key == 'approved' else 2
            with self.assertRaises(ValueError):
                h.verify_accepted_inputs(self.candidate, altered)
        altered = deepcopy(self.acceptance)
        del altered['fingerprints']['artifacts/candidate-pilot/pool/candidates.parquet']
        with self.assertRaises(ValueError):
            h.verify_accepted_inputs(self.candidate, altered)

    def test_pinned_but_wrong_lineage_or_incomplete_reject(self):
        path = self.candidate/'report.json'
        report = json.loads(path.read_text())
        for updates in [{'status': 'failed'}, {'anchor_run_id': 'wrong'}]:
            path.write_text(json.dumps({**report, **updates}))
            pins = deepcopy(self.acceptance)
            pins['fingerprints'][path.relative_to(self.root).as_posix()] = sha256_file(path)
            with self.assertRaises(ValueError):
                h.verify_accepted_inputs(self.candidate, pins)

    def test_candidate_must_consume_original_independent_Q_artifact(self):
        path = self.candidate/'run.json'
        cm = json.loads(path.read_text())
        identity = cm['identity']
        original = self.anchor/'queries.parquet'
        alternate = self.candidate/'queries-copy.parquet'
        alternate.write_bytes(original.read_bytes())
        inputs = deepcopy(identity['input_hashes'])
        del inputs[original.relative_to(self.root).as_posix()]
        inputs[alternate.relative_to(self.root).as_posix()] = sha256_file(alternate)
        rebuilt = build_run_manifest(identity['protocol'], code_hashes=identity['code_hashes'],
            input_hashes=inputs, components=identity['components'], artifact_refs=cm['artifact_refs'],
            created_at=cm['created_at'])
        write_run_manifest(rebuilt, path)
        report_path = self.candidate/'report.json'
        report = json.loads(report_path.read_text())
        report['run_id'] = rebuilt['run_id']
        report_path.write_text(json.dumps(report))
        self.acceptance['candidate_run_id'] = rebuilt['run_id']
        for item in (path, report_path, alternate):
            self.acceptance['fingerprints'][item.relative_to(self.root).as_posix()] = sha256_file(item)
        with self.assertRaisesRegex(ValueError, 'exact003 queries'):
            h.verify_accepted_inputs(self.candidate, self.acceptance)

    def test_late_stage_failure_preserves_counts_but_no_complete_metrics(self):
        output = self.root/'artifacts/heuristic-baselines'
        with patch.object(h, 'make_rankings', side_effect=TimeoutError('persistent deadline')), self.assertRaises(TimeoutError):
            h.run(self.candidate, self.acceptance_path, output, replicates=2)
        report = json.loads(next(output.glob('*/report.json')).read_text())
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['row_counts']['pilot_candidates'], 6)
        self.assertIn('identity', report)
        self.assertNotIn('metrics', report)
        self.assertEqual(report['stages'][-1]['stage'], 'rank_fixed_C')
        self.assertEqual(report['stages'][-1]['status'], 'failed')

    def test_failed_provenance_saves_partial_cost_no_metrics(self):
        self.acceptance['approved'] = False
        self.acceptance_path.write_text(json.dumps(self.acceptance))
        output = self.root/'artifacts/heuristic-baselines'
        with self.assertRaises(ValueError):
            h.run(self.candidate, self.acceptance_path, output, replicates=2)
        reports = list(output.glob('*/report.json'))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text())
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('metrics', report)
        self.assertGreater(report['seconds'], 0)
        self.assertEqual(report['accepted_declarations']['approved'], False)
        self.assertEqual(report['stages'][-1]['status'], 'failed')

    def test_resource_failure_saves_partial_report_without_complete_metrics(self):
        output = self.root/'artifacts/heuristic-baselines'
        with patch.object(h, 'peak_rss_bytes', return_value=7*2**30), self.assertRaises(MemoryError):
            h.run(self.candidate, self.acceptance_path, output, replicates=2)
        report = json.loads(next(output.glob('*/report.json')).read_text())
        self.assertEqual(report['error_type'], 'MemoryError')
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('metrics', report)
        for kwargs in [{'seconds': 1801}, {'replicates': 1001}]:
            with self.assertRaises(ValueError):
                h.run(self.candidate, self.acceptance_path, output, **kwargs)


if __name__ == '__main__':
    unittest.main()
