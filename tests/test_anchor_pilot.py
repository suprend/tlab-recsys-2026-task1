"""Independent small-record oracle for anchor population and label semantics."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import random
import tempfile
from unittest.mock import patch
import json
import shutil
import unittest

import duckdb

from scripts.anchor_pilot import RunDeadline, StageLedger, build_pilot, create_labels, run, stable_key, utc
from scripts.protocol_manifest import load_protocol

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def time(value):
    return datetime.fromisoformat('2019-10-' + value)


RECORDS = [
    (time('01T00:00:00'), 'view', 1, 10),
    (time('07T23:59:59'), 'view', 2, 10),
    (time('08T00:00:00'), 'purchase', 3, 10),
    (time('08T00:00:00'), 'purchase', 3, 10),  # raw duplicate, one binary target
    (time('08T12:00:00'), 'purchase', 2, 10),
    (time('09T00:00:00'), 'purchase', 4, 10),
    (time('01T00:00:00'), 'view', 7, 20),  # included on Oct8, expired on Oct9
    (time('07T00:00:00'), 'view', 8, 30),
    (time('08T00:00:00'), 'view', 9, 40),  # query sees state BEFORE this timestamp
    (time('09T23:59:59'), 'view', 10, 50),
    (time('06T00:00:00'), 'view', 11, 60),  # exact48h lower boundary on Oct8
]


def oracle(records, hours, cap, seed, include_start=True, include_end=False):
    """Direct row iteration, independent of production windows/SQL/helpers."""
    queries, targets = {}, {}
    for day in range(8, 11):
        t = datetime(2019, 10, day)
        past = [r for r in records if t - timedelta(hours=hours) <= r[0] < t]
        users = sorted(set(r[3] for r in past), key=lambda user: (
            hashlib.sha256(f'sample|{seed}|2019-10-{day:02d}T00:00:00Z|{user}'.encode()).hexdigest(), user))[:cap]
        for user in users:
            q = (user, t)
            history = [r for r in records if r[3] == user and t - timedelta(days=7) <= r[0] < t]
            queries[q] = (sum(r[3] == user for r in past), len(history), len(set(r[2] for r in history)))
            future = [r for r in records if r[3] == user and r[1] == 'purchase'
                      and (r[0] > t or (include_start and r[0] == t))
                      and (r[0] < t + timedelta(days=1) or (include_end and r[0] == t + timedelta(days=1)))]
            for product in set(r[2] for r in future):
                matching = [r for r in future if r[2] == product]
                targets[(user, t, product)] = (
                    len(matching), any(r[0] == t for r in matching),
                    any(r[2] == product and r[0] < t for r in records),
                    any(r[3] == user and r[2] == product and r[0] < t for r in records))
    return queries, targets


class AnchorPilotTests(unittest.TestCase):
    def setUp(self):
        self.config = load_protocol(ROOT / 'configs/protocols/clock-7d.json')
        self.con = duckdb.connect(':memory:')
        self.con.execute('SET threads=2')
        self.con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT)')
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?)', RECORDS)

    def tearDown(self):
        self.con.close()

    def actual(self):
        queries = {(r[0], r[1]): tuple(r[2:]) for r in self.con.execute('''SELECT user_id,anchor,
            eligibility_events,history_events_7d,history_distinct_items_7d FROM pilot_queries''').fetchall()}
        targets = {(r[0], r[1], r[2]): tuple(r[3:]) for r in self.con.execute('''SELECT q.user_id,q.anchor,l.product_id,
            l.raw_purchase_rows,l.same_second_purchase,l.catalog_seen_before,l.pair_seen_before
            FROM pilot_labels l JOIN pilot_queries q USING(query_id)''').fetchall()}
        return queries, targets

    def test_binary_targets_and_past_eligibility_match_independent_oracle(self):
        result = build_pilot(self.con, self.config)
        self.assertEqual(self.actual(), oracle(RECORDS, 168, 2000, 2026))
        first = result['daily_outcomes'][0]
        self.assertEqual((first['queries'], first['positive_queries'], first['mature_empty_queries']), (4, 1, 3))
        self.assertEqual((first['distinct_targets'], first['raw_purchase_rows'], first['cold_targets']), (2, 3, 1))
        self.assertEqual(first['same_second_targets'], 1)
        self.assertEqual(first['repeat_pair_targets'], 1)
        self.assertEqual(result['population'][0]['eligible_users'], 4)
        self.assertTrue(all('SEQ_SCAN' in p['explain_estimate_only'] for p in result['scan_plans']))

    def test_first_day_gold_counts_match_separate_sql_oracle(self):
        build_pilot(self.con, self.config)
        independent = duckdb.connect(':memory:')
        try:
            independent.execute('CREATE TABLE e(t TIMESTAMP,kind VARCHAR,item BIGINT,u BIGINT)')
            independent.executemany('INSERT INTO e VALUES (?,?,?,?)', RECORDS)
            expected_q = independent.execute('''SELECT u,count(*),count(DISTINCT item)
                FROM e WHERE t>='2019-10-01' AND t<'2019-10-08' GROUP BY u ORDER BY u''').fetchall()
            actual_q = self.con.execute("SELECT user_id,history_events_7d,history_distinct_items_7d FROM pilot_queries WHERE anchor='2019-10-08' ORDER BY user_id").fetchall()
            self.assertEqual(actual_q, expected_q)
            expected_y = independent.execute('''WITH selected(u) AS (VALUES (10),(20),(30),(60))
                SELECT e.u,e.item,count(*) FROM e JOIN selected USING(u)
                WHERE kind='purchase' AND t>='2019-10-08' AND t<'2019-10-09'
                GROUP BY e.u,e.item ORDER BY e.u,e.item''').fetchall()
            actual_y = self.con.execute('''SELECT q.user_id,l.product_id,l.raw_purchase_rows
                FROM pilot_labels l JOIN pilot_queries q USING(query_id)
                WHERE q.anchor='2019-10-08' ORDER BY 1,2''').fetchall()
            self.assertEqual(actual_y, expected_y)
        finally:
            independent.close()

    def test_population48h_changes_only_past_eligibility(self):
        self.config['query']['eligibility_hours'] = 48
        result = build_pilot(self.con, self.config)
        self.assertEqual(self.actual(), oracle(RECORDS, 48, 2000, 2026))
        first_users = self.con.execute("SELECT user_id FROM pilot_queries WHERE anchor='2019-10-08' ORDER BY user_id").fetchall()
        self.assertEqual(first_users, [(10,), (30,), (60,)])
        self.assertEqual(result['daily_outcomes'][0]['queries'], 3)
        self.assertEqual(self.con.execute('SELECT min(history_coverage_7d) FROM pilot_queries').fetchone()[0], 1)

    def test_same_timestamp_permutation_preserves_queries_and_binary_labels(self):
        build_pilot(self.con, self.config)
        before = self.actual()
        self.con.execute('DELETE FROM events')
        records = RECORDS.copy()
        random.Random(71).shuffle(records)
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?)', records)
        build_pilot(self.con, self.config)
        self.assertEqual(before, self.actual())

    def test_future_purchase_changes_label_but_not_earlier_query_population(self):
        build_pilot(self.con, self.config)
        before_q, before_y = self.actual()
        self.con.execute("INSERT INTO events VALUES ('2019-10-08 15:00:00','purchase',99,30)")
        build_pilot(self.con, self.config)
        after_q, after_y = self.actual()
        day = time('08T00:00:00')
        self.assertEqual({k:v for k,v in before_q.items() if k[1]==day},
                         {k:v for k,v in after_q.items() if k[1]==day})
        self.assertNotIn((30, day, 99), before_y)
        self.assertIn((30, day, 99), after_y)
        self.assertEqual(after_y[(30, day, 99)][2:], (False, False))

    def test_bottom_hash_sampling_matches_fixed_serialization_and_ignores_future_buyers(self):
        self.config['query']['max_users_per_day'] = 1
        self.config['query']['sample_seed'] = 53
        build_pilot(self.con, self.config)
        self.assertEqual(self.actual(), oracle(RECORDS, 168, 1, 53))
        day = time('08T00:00:00')
        expected = hashlib.sha256(b'sample|53|2019-10-08T00:00:00Z|10').hexdigest()
        self.assertEqual(stable_key('sample', 10, day.replace(tzinfo=UTC), 53), expected)

    def test_censored_queries_survive_and_are_not_called_empty_negatives(self):
        build_pilot(self.con, self.config)
        daily = create_labels(self.con, target_config=self.config['target'],
            source_start=utc(self.config['source']['start']), source_end=utc('2019-10-09T00:00:00Z'))
        self.assertEqual(daily[0]['censored_queries'], 0)  # [Oct8,Oct9) fully observed
        self.assertGreater(daily[1]['censored_queries'], 0)
        self.assertEqual(daily[1]['mature_empty_queries'], 0)
        self.assertEqual(daily[1]['positive_queries'], 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM pilot_labels l JOIN pilot_queries q USING(query_id) WHERE q.anchor>='2019-10-09'").fetchone()[0], 0)

    def test_endpoint_policy_is_executed_in_sql(self):
        for include_start, include_end in [(False, False), (True, True), (False, True)]:
            config = deepcopy(self.config)
            config['target']['include_anchor'] = include_start
            config['target']['include_end'] = include_end
            with self.subTest(start=include_start, end=include_end):
                build_pilot(self.con, config)
                self.assertEqual(self.actual(), oracle(RECORDS, 168, 2000, 2026, include_start, include_end))

    def test_empty_source_preserves_valid_empty_tables(self):
        self.con.execute('DELETE FROM events')
        result = build_pilot(self.con, self.config)
        self.assertEqual(result['daily_outcomes'], [])
        self.assertTrue(all(r['sampled_queries']==0 and r['eligible_users']==0 for r in result['population']))
        self.assertEqual(self.con.execute('SELECT count(*) FROM pilot_labels').fetchone()[0], 0)


class DeadlineTests(unittest.TestCase):
    def test_expiry_during_python_stage_fails_closed_after_operation(self):
        now=[10.0]
        deadline=RunDeadline(2,clock=lambda:now[0])
        with tempfile.TemporaryDirectory() as directory:
            ledger=StageLedger(Path(directory),deadline=deadline)
            with self.assertRaisesRegex(TimeoutError,'deadline'):
                ledger('python_stage',lambda:now.__setitem__(0,12.0))
            self.assertEqual(ledger.rows[0]['status'],'failed')

    def test_expired_flag_between_statements_prevents_new_sql_even_if_engine_accepts_it(self):
        deadline=RunDeadline(100,clock=lambda:10)
        con=duckdb.connect(':memory:')
        try:
            deadline.expired.set()  #timer callback persists this state
            self.assertEqual(con.execute('SELECT 1').fetchone()[0],1)
            with tempfile.TemporaryDirectory() as directory:
                ledger=StageLedger(Path(directory),con,deadline)
                with self.assertRaisesRegex(TimeoutError,'deadline'):
                    ledger('must_not_run',lambda:con.execute('CREATE TABLE forbidden AS SELECT 1'))
                self.assertEqual(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='forbidden'").fetchone()[0],0)
        finally:
            con.close()

    def test_invalid_deadline_and_nonstage_daily_checks(self):
        for value in [0,-1,float('inf'),float('nan'),True]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                RunDeadline(value)
        con=duckdb.connect(':memory:')
        try:
            config=load_protocol(ROOT/'configs/protocols/clock-7d.json')
            def expired():raise TimeoutError('synthetic expiry')
            with self.assertRaisesRegex(TimeoutError,'synthetic expiry'):
                build_pilot(con,config,budget_check=expired)
        finally:
            con.close()

    def test_failed_executor_preserves_partial_report_and_does_not_mark_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            for name in ['uv.lock','scripts/anchor_pilot.py','scripts/temporal_contract.py','scripts/protocol_manifest.py']:
                destination=root/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,destination)
            db=root/'data/source.duckdb'
            db.parent.mkdir()
            con=duckdb.connect(str(db))
            con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT)')
            con.execute('CREATE TABLE ingest_metadata(source_sha256 VARCHAR)')
            con.close()
            def expire(con,config,*,stage,budget_check):
                def interrupted():raise TimeoutError('synthetic between-stage expiry')
                stage('interrupted_fixture',interrupted)
            with patch('scripts.anchor_pilot.ROOT',root),patch('scripts.anchor_pilot.build_pilot',side_effect=expire):
                with self.assertRaisesRegex(TimeoutError,'synthetic between-stage expiry'):
                    run(ROOT/'configs/protocols/clock-7d.json',db,root/'artifacts/pilot')
            reports=list((root/'artifacts/pilot').glob('*/report.json'))
            self.assertEqual(len(reports),1)
            report=json.loads(reports[0].read_text())
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['stages'][0]['status'],'failed')
            self.assertFalse((reports[0].parent/'queries.parquet').exists())
            self.assertTrue((reports[0].parent/'run.json').exists())


if __name__ == '__main__':
    unittest.main()
