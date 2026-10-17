"""Real synthetic child production retains empty development calendar days."""
from copy import deepcopy
import unittest

import tests.test_development_collection as fixtures


class DevelopmentEmptyDaysTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing bounded two-day fixture, including typed source
        # schema, explicit complete source interval, producer pins and approvals.
        self.fixture = fixtures.DevelopmentRuntimeTests(
            'test_actual_producers_wait_for_external_review_then_resume_full_features_and_cache')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.replace_events([('2019-10-08 12:00:00', 'view', 10, 1, 100, 'a')])

    def replace_events(self, rows):
        import duckdb
        fixture = self.fixture
        con = duckdb.connect(str(fixture.db))
        try:
            con.execute('DELETE FROM events')
            if rows:
                con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)', rows)
        finally:
            con.close()
        # Source replacement changes the collection identity; stale approvals
        # must not be reused even in a synthetic fixture.
        fixture.plan = fixture.d.prepare_execution_plan(fixture.phase_path, fixture.db)
        fixture.directory = fixture.output / fixture.plan['collection_id']
        fixture.d._atomic_json(fixture.producer, dict(
            version=1, approved=True, scope='reviewed_producers_and_phase_plan',
            collection_id=fixture.plan['collection_id'],
            fingerprints=fixture.plan['execution_inputs']['fingerprints']))

    def produce_and_resume(self):
        fixture = self.fixture
        first = fixture.execute()
        self.assertEqual(first['status'], 'waiting_for_shard_review')
        self.assertEqual([pending['index'] for pending in first['pending']],
                         list(range(len(fixture.plan['identity']['shard_protocols']))))
        self.assertTrue(all('features' not in entry for entry in fixture.read_state()['shards']))
        fixture.approve_shards()
        complete = fixture.execute()
        self.assertEqual(complete['status'], 'complete_produced_unreviewed')
        self.assertEqual(complete['collection']['daily_anchors'], [
            '2019-10-08T00:00:00Z', '2019-10-09T00:00:00Z'])
        counts = complete['collection']['counts']
        self.assertEqual(counts['candidates'], counts['features'])
        return complete

    def anchor_reports(self):
        fixture = self.fixture
        return [fixture.d._read_json(fixture.root / entry['anchor']['directory'] / 'report.json')
                for entry in fixture.read_state()['shards']]

    def test_one_event_preserves_zero_first_day_then_one_query(self):
        complete = self.produce_and_resume()
        first, second = self.anchor_reports()
        self.assertEqual(first['population'][0]['anchor'], '2019-10-08T00:00:00Z')
        self.assertEqual(first['population'][0]['sampled_queries'], 0)
        self.assertEqual(first['daily_outcomes'], [])
        self.assertEqual(second['population'][0]['sampled_queries'], 1)
        self.assertEqual(second['daily_outcomes'][0]['queries'], 1)
        self.assertEqual(complete['collection']['counts'], dict(
            queries=1, labels=0, candidates=1, features=1))
        self.assertEqual(self.fixture.execute()['collection'], complete['collection'])

    def test_empty_first_day_does_not_drop_positive_fullY_outside_candidates(self):
        self.replace_events([
            ('2019-10-08 12:00:00', 'view', 10, 1, 100, 'a'),
            ('2019-10-09 12:00:00', 'purchase', 20, 1, 200, 'b')])
        complete = self.produce_and_resume()
        self.assertEqual(complete['collection']['counts'], dict(
            queries=1, labels=1, candidates=1, features=1))
        first, second = self.anchor_reports()
        self.assertEqual(first['population'][0]['sampled_queries'], 0)
        self.assertEqual(first['daily_outcomes'], [])
        self.assertEqual(second['daily_outcomes'][0]['distinct_targets'], 1)
        import duckdb
        con = duckdb.connect(':memory:')
        try:
            refs = complete['collection']['artifact_refs']
            targets = con.execute('SELECT product_id FROM read_parquet(?)',
                [str(self.fixture.root / refs['labels'][1])]).fetchall()
            candidates = con.execute('SELECT product_id FROM read_parquet(?)',
                [str(self.fixture.root / refs['candidates'][1])]).fetchall()
        finally:
            con.close()
        self.assertEqual(targets, [(20,)])
        self.assertEqual(candidates, [(10,)])

    def test_all_empty_phase_keeps_both_calendar_days_and_typed_empty_outputs(self):
        self.replace_events([])
        complete = self.produce_and_resume()
        self.assertEqual(complete['collection']['counts'], dict(
            queries=0, labels=0, candidates=0, features=0))
        self.assertTrue(complete['collection']['feature_columns'])
        for report in self.anchor_reports():
            self.assertEqual(len(report['population']), 1)
            self.assertEqual(report['population'][0]['sampled_queries'], 0)
            self.assertEqual(report['daily_outcomes'], [])
        self.assertEqual(self.fixture.execute()['collection'], complete['collection'])

    def test_zero_and_nonzero_days_inside_one_shard_keep_exact_calendar(self):
        fixture = self.fixture
        fixture.phase['shard_days'] = 2
        fixture.d._atomic_json(fixture.phase_path, fixture.phase)
        self.replace_events([('2019-10-08 12:00:00', 'view', 10, 1, 100, 'a')])
        complete = self.produce_and_resume()
        report, = self.anchor_reports()
        self.assertEqual([day['sampled_queries'] for day in report['population']], [0, 1])
        self.assertEqual([day['anchor'] for day in report['daily_outcomes']], ['2019-10-09T00:00:00Z'])
        self.assertEqual(complete['collection']['counts'], dict(
            queries=1, labels=0, candidates=1, features=1))

    def test_empty_day_does_not_allow_missing_duplicate_or_physically_absent_shards(self):
        self.produce_and_resume()
        fixture = self.fixture
        state = fixture.read_state()
        for shards in [state['shards'][:1], [state['shards'][0], state['shards'][0]]]:
            with self.subTest(indices=[entry['index'] for entry in shards]):
                with self.assertRaisesRegex(ValueError, 'shard cover'):
                    fixture.d.aggregate_collection(fixture.plan, {**state, 'shards': shards})
        entry = state['shards'][0]
        manifest = fixture.d._read_json(fixture.root / entry['anchor']['directory'] / 'run.json')
        path = fixture.root / manifest['artifact_refs']['queries']
        missing = path.with_suffix('.temporarily-absent')
        path.rename(missing)
        try:
            with self.assertRaises(FileNotFoundError):
                fixture.d.aggregate_collection(fixture.plan, deepcopy(state))
        finally:
            missing.rename(path)


if __name__ == '__main__':
    unittest.main()
