"""Invented events only. No actual DB/Parquet, training, model or target access."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import json
import random
import tempfile
import unittest
from unittest import mock

import duckdb

from scripts.category_candidate_pilot import (create_policies, round_robin_capped, seal_candidates,
    evaluate_policies, paired_bootstrap, compare_original_baseline)
from scripts.category_candidate_pilot import run, export_target_changes
from scripts.protocol_manifest import load_protocol, sha256_file

ROOT = Path(__file__).resolve().parents[1]
T = datetime(2019, 10, 8)


class CategoryPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tlab-category-test-')
        self.directory = Path(self.temp.name)
        self.con = duckdb.connect(':memory:')
        self.con.execute('SET threads=2')
        self.con.execute("SET memory_limit='256MB'")
        self.con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
        self.records = [(T-timedelta(days=5), 'purchase', item, 10000+item, 900) for item in range(1, 201)]
        self.records += [(T-timedelta(days=4), 'purchase', 1, 10001, 900)] * 7
        self.records += [(T-timedelta(days=4), 'purchase', 2, 9999, 900),
            (T-timedelta(days=1), 'view', 1000, 1, 2),
            (T-timedelta(days=1), 'view', 1001, 1, 10),
            (T-timedelta(days=2), 'view', 1002, 1, 2),
            (T-timedelta(days=3), 'view', 1100, 50, 2),
            (T-timedelta(days=4), 'view', 1200, 60, 2),
            (T-timedelta(days=1), 'view', 1200, 60, 2),
            (T-timedelta(days=1), 'view', 1200, 60, None),
            (T-timedelta(days=1), 'view', 1201, 61, 2),
            (T-timedelta(days=1), 'view', 1201, 61, 10),
            (T-timedelta(days=1), 'view', 1202, 62, None),
            (T-timedelta(days=3), 'view', 1203, 63, 2),
            (T, 'view', 1203, 63, 999),
            (T-timedelta(days=3), 'view', 1300, 1, 2),
            (T-timedelta(hours=1), 'view', 1300, 1, 2),
            (T-timedelta(hours=1), 'view', 1300, 1, None),
            (T-timedelta(days=3), 'view', 1301, 1, 2),
            (T-timedelta(days=2), 'cart', 1301, 90, 10),
            (T-timedelta(days=1), 'view', 1400, 3, 2),
            (T-timedelta(days=1), 'view', 1401, 3, 10)]
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?)', self.records)
        self.con.execute('CREATE TEMP TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
        self.con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,true)', [('q1', 1, T), ('q2', 2, T), ('q3', 3, T)])
        self.config = load_protocol(ROOT/'configs/protocols/clock-48h.json')

    def tearDown(self):
        if self.con is not None:
            self.con.close()
        self.temp.cleanup()

    def build(self):
        return create_policies(self.con, self.config)

    def labels(self, values=None):
        self.con.execute('CREATE TEMP TABLE pilot_labels(query_id VARCHAR,product_id BIGINT,catalog_seen_before BOOLEAN,pair_seen_before BOOLEAN)')
        values = values if values is not None else [('q1',1100,True,False), ('q1',200,True,False), ('q1',99999,False,False)]
        if values:
            self.con.executemany('INSERT INTO pilot_labels VALUES (?,?,?,?)', values)

    def items(self, arm, query='q1'):
        return [r[0] for r in self.con.execute('SELECT product_id FROM cc_lists WHERE arm=? AND query_id=? ORDER BY position', [arm,query]).fetchall()]

    def test_next_unseen_round_robin_exact_root_example_and_source_exhaustion(self):
        self.assertEqual(round_robin_capped([[1,2,3],[1,4],[4,5]]), [1,4,5,2,3])
        self.assertEqual(round_robin_capped([[],[1,1],[]]), [1])
        self.assertEqual(round_robin_capped([[1,2],[1,2],[1,2]]), [1,2])

    def test_category_recovers_outside_old_C_without_Y_and_no_refill(self):
        self.build()  # There is no labels table.
        self.assertNotIn(1100, self.items('C0'))
        self.assertIn(1100, self.items('C1'))
        self.assertIn(200, self.items('C0'))
        self.assertNotIn(200, self.items('C1'))
        self.assertLess(len(self.items('C1')), 220)
        self.assertEqual(len(self.items('C0','q2')), 200)
        self.assertEqual(len(self.items('C1','q2')), 140)

    def test_distinct_customers_not_raw_purchase_rows_and_numeric_category_tie(self):
        self.build()
        popular = self.con.execute('SELECT product_id,popularity_distinct_users,popular_source_rank FROM pilot_candidates WHERE query_id=\'q2\' ORDER BY popular_source_rank LIMIT 2').fetchall()
        self.assertEqual(popular, [(2,2,1),(1,1,2)])
        self.assertEqual(self.con.execute("SELECT category_id,category_rank FROM cc_profiles WHERE query_id='q3' ORDER BY category_rank").fetchall(), [(2,1),(10,2)])

    def test_latest_global_bucket_NULL_mixture_conflict_missing_no_older_backoff(self):
        self.build()
        actual = self.con.execute('SELECT product_id,category_id,missing,ambiguous FROM cc_membership WHERE product_id BETWEEN 1200 AND 1203 ORDER BY product_id').fetchall()
        self.assertEqual(actual, [(1200,None,False,True),(1201,None,False,True),(1202,None,True,False),(1203,2,False,False)])
        self.assertNotIn(1200,self.items('C1'))
        self.assertNotIn(1201,self.items('C1'))

    def test_user_latest_view_bucket_excluded_with_support_and_not_current_reclassified(self):
        self.build()
        support = self.con.execute("SELECT view_products,known_products,missing_products,ambiguous_products FROM cc_support WHERE query_id='q1'").fetchone()
        self.assertEqual(support, (5,4,0,1))
        self.assertEqual(self.con.execute("SELECT product_support FROM cc_profiles WHERE query_id='q1' AND category_id=2").fetchone(), (3,))
        self.assertEqual(self.con.execute('SELECT category_id FROM cc_membership WHERE product_id=1301').fetchone(), (10,))

    def test_future_suffix_and_peer_permutation_preserve_all_lists_and_membership(self):
        self.build()
        before = self.con.execute('SELECT * FROM cc_lists ORDER BY ALL').fetchall()
        membership = self.con.execute('SELECT * FROM cc_membership ORDER BY ALL').fetchall()
        shuffled = self.records.copy()
        random.Random(9).shuffle(shuffled)
        self.con.execute('DELETE FROM events')
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?)', shuffled)
        self.con.execute("INSERT INTO events VALUES ('2019-10-08','purchase',999,1,2),('2019-10-09','view',1100,1,888)")
        self.build()
        self.assertEqual(before, self.con.execute('SELECT * FROM cc_lists ORDER BY ALL').fetchall())
        self.assertEqual(membership, self.con.execute('SELECT * FROM cc_membership ORDER BY ALL').fetchall())

    def test_matched_sizes_and_unique_round_robin_positions(self):
        self.build()
        self.assertEqual(self.con.execute('SELECT count(*)-count(DISTINCT (cohort,arm,query_id,product_id)) FROM cc_eval_lists').fetchone()[0],0)
        counts = self.con.execute("SELECT query_id,arm,count(*) FROM cc_eval_lists WHERE cohort='matched' GROUP BY query_id,arm ORDER BY query_id,arm").fetchall()
        for left,right in zip(counts[::2],counts[1::2]):
            self.assertEqual(left[2],right[2])
        self.assertEqual(self.con.execute("SELECT count(*) FROM cc_lists WHERE arm='C0'").fetchone()[0], self.con.execute('SELECT count(*) FROM pilot_candidates').fetchone()[0])

    def test_exact_cached_C0_parity_and_changed_row_fail_closed(self):
        self.build()
        path = self.directory/'original.parquet'
        self.con.execute('COPY pilot_candidates TO ? (FORMAT PARQUET)', [str(path)])
        fingerprint = sha256_file(path)
        compare_original_baseline(self.con,path,fingerprint)
        self.con.execute("DELETE FROM pilot_candidates WHERE query_id='q1' AND product_id=200")
        with self.assertRaisesRegex(ValueError,'C0 differs'):
            compare_original_baseline(self.con,path,fingerprint)

    def test_sealed_lists_keep_offC_fullY_emptyY_and_gained_lost_identity(self):
        self.build()
        sealed = seal_candidates(self.con,self.directory)
        self.labels()
        report = evaluate_policies(self.con,sealed)
        native = {r['arm']:r for r in report['cells'] if r['cohort']=='native'}
        self.assertEqual((native['C0']['queries'],native['C0']['positive_queries'],native['C0']['targets']), (3,1,3))
        self.assertEqual((native['C0']['hits'],native['C1']['hits']), (1,1))
        self.assertAlmostEqual(native['C1']['positive_query_macro_recall'], 1/3)
        change = next(r for r in report['changes'] if r['cohort']=='native')
        self.assertEqual((change['gained'],change['lost'],change['new_gained'],change['new_lost']), (1,1,1,1))
        with open(sealed['cc_eval_lists']['path'],'ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError,'Sealed candidate'):
            evaluate_policies(self.con,sealed)

    def test_empty_C_and_empty_positive_bootstrap_draws_are_not_zero_or_redrawn(self):
        self.con.execute('DELETE FROM events')
        self.build()
        sealed = seal_candidates(self.con,self.directory)
        self.labels()
        report = evaluate_policies(self.con,sealed)
        self.assertTrue(all(cell['emptyC']==3 and cell['targets']==3 and cell['hits']==0 for cell in report['cells']))
        bootstrap = paired_bootstrap(self.con, draws=1000)
        self.assertGreater(bootstrap['undefined_draws'],0)
        self.assertEqual(bootstrap['redrawn'],0)
        self.assertIsNone(bootstrap['native']['ci95'])
        self.assertEqual(bootstrap['native']['valid_draws']+bootstrap['undefined_draws'],1000)

    def test_censored_queries_and_duplicate_fullY_are_rejected(self):
        self.con.execute("UPDATE pilot_queries SET label_is_mature=false WHERE query_id='q2'")
        with self.assertRaisesRegex(ValueError,'all queries mature'):
            self.build()
        self.con.execute("UPDATE pilot_queries SET label_is_mature=true WHERE query_id='q2'")
        self.build()
        sealed = seal_candidates(self.con,self.directory)
        self.labels([('q1',1100,True,False)]*2)
        with self.assertRaisesRegex(ValueError,'Duplicate fullY'):
            evaluate_policies(self.con,sealed)

    def test_fullY_all_empty_is_undefined_and_no_target_insertion(self):
        self.build()
        sealed = seal_candidates(self.con,self.directory)
        self.labels([])
        report = evaluate_policies(self.con,sealed)
        self.assertTrue(all(cell['positive_query_macro_recall'] is None for cell in report['cells']))
        result = paired_bootstrap(self.con,draws=50)
        self.assertEqual(result['undefined_draws'],50)
        self.assertEqual(result['native']['valid_draws'],0)

    def test_changed_target_identities_and_all_query_counters_persist_after_close(self):
        self.con.execute("INSERT INTO events VALUES ('2019-10-01','cart',200,1,900)")
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?)',
            [(T-timedelta(hours=2),'view',item,1,2) for item in range(2000,2025)])
        self.build()
        sealed = seal_candidates(self.con,self.directory)
        self.labels([('q1',1100,True,False),('q1',200,True,True),('q1',99999,False,False)])
        evaluate_policies(self.con,sealed)
        artifacts = export_target_changes(self.con,self.directory)
        self.con.close()
        self.con = None
        reader = duckdb.connect(':memory:')
        try:
            identities = reader.execute("SELECT query_id,product_id,direction,new_pair FROM read_parquet(?) WHERE cohort='native' ORDER BY product_id",
                [artifacts['target-changes.parquet']['path']]).fetchall()
            self.assertEqual(identities,[('q1',200,'lost',False),('q1',1100,'gained',True)])
            counters = reader.execute('SELECT query_id,cohort,gained,lost,new_gained,new_lost FROM read_parquet(?) ORDER BY query_id,cohort',
                [artifacts['query-changes.parquet']['path']]).fetchall()
            self.assertEqual(counters,[('q1','matched',1,0,1,0),('q1','native',1,1,1,0),
                ('q2','matched',0,0,0,0),('q2','native',0,0,0,0),('q3','matched',0,0,0,0),('q3','native',0,0,0,0)])
            for item in artifacts.values():
                self.assertEqual(sha256_file(Path(item['path'])),item['sha256'])
                self.assertEqual(Path(item['path']).stat().st_size,item['bytes'])
        finally:
            reader.close()

    def invented_cli_inputs(self):
        """Fake provenance loader; only invented physical DB/parquet bodies."""
        project = self.directory/'invented-project'
        (project/'data').mkdir(parents=True)
        (project/'scripts').mkdir()
        for name in ('manual_features.py','protocol_manifest.py','anchor_pilot.py','temporal_contract.py'):
            (project/'scripts'/name).write_text('# invented metadata file, never imported\n')
        (project/'uv.lock').write_text('# invented metadata file\n')
        source = project/'data/events.duckdb'
        db = duckdb.connect(str(source))
        db.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
        db.executemany('INSERT INTO events VALUES (?,?,?,?,?)',self.records)
        db.close()
        self.build()
        self.labels()
        for table,name in (('pilot_queries','queries.parquet'),('pilot_labels','labels.parquet'),('pilot_candidates','baseline.parquet')):
            self.con.execute('COPY '+table+' TO ? (FORMAT PARQUET)',[str(project/name)])
        anchor_dir, baseline_dir = project/'anchor', project/'baseline'
        for directory,run_id in ((anchor_dir,'invented-anchor'),(baseline_dir,'invented-baseline')):
            directory.mkdir()
            (directory/'run.json').write_text('{}')
            (directory/'report.json').write_text(json.dumps(dict(status='complete',run_id=run_id)))
        fingerprints = {name:sha256_file(project/name) for name in ('data/events.duckdb','queries.parquet','labels.parquet')}
        anchor = dict(run_id='invented-anchor',identity=dict(protocol=self.config,input_hashes={'data/events.duckdb':fingerprints['data/events.duckdb']}),
                      artifact_refs=dict(queries='queries.parquet',labels='labels.parquet'))
        baseline = dict(run_id='invented-baseline',identity=dict(input_hashes=fingerprints),artifact_refs=dict(candidates='baseline.parquet'))
        return project,anchor_dir,baseline_dir,anchor,baseline,sha256_file(project/'baseline.parquet')

    def test_invented_CLI_plumbing_and_connect_failure_report(self):
        project,anchor_dir,baseline_dir,anchor,baseline,fingerprint = self.invented_cli_inputs()
        def manifest(path):
            return anchor if path.parent==anchor_dir else baseline
        with mock.patch('scripts.category_candidate_pilot.ROOT',project), mock.patch('scripts.category_candidate_pilot.load_run_manifest',side_effect=manifest):
            result = run(anchor_dir,baseline_dir,fingerprint,project/'output',cpu=30,wall=60,rss=512*2**20,spill=32*2**20)
            self.assertEqual(result['status'],'complete_coverage_only_pending_review')
            self.assertEqual(result['fits'],0)
            self.assertTrue((project/'output/candidate-seal.json').exists())
            self.assertEqual(set(result['target_change_artifacts']),{'target-changes.parquet','query-changes.parquet'})
            for item in result['target_change_artifacts'].values():
                self.assertEqual(sha256_file(Path(item['path'])),item['sha256'])
            with mock.patch('scripts.category_candidate_pilot.duckdb.connect',side_effect=RuntimeError('injected connect failure')):
                with self.assertRaisesRegex(RuntimeError,'injected connect failure'):
                    run(anchor_dir,baseline_dir,fingerprint,project/'failure-output',cpu=30,wall=60,rss=512*2**20,spill=32*2**20)
            failed = json.loads((project/'failure-output/report.json').read_text())
            self.assertEqual(failed['status'],'failed')
            self.assertEqual(failed['error_type'],'RuntimeError')


if __name__ == '__main__':
    unittest.main()
