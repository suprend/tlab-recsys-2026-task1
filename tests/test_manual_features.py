"""Full18-feature direct-row oracle, including changing/ambiguous metadata."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import random
import json
from unittest.mock import patch

import scripts.manual_features as m
import tests.test_heuristic_baselines as fixture_tests
import unittest

import duckdb

from scripts.manual_features import create_manual_features,load_registry,validate_registry
from scripts.protocol_manifest import load_protocol

ROOT=Path(__file__).resolve().parents[1]
S=datetime(2019,10,1)
T=datetime(2019,10,8)
RECORDS=[
    (S,'view',1,10,100,'shared.code'),
    (S,'view',1,21,100,'shared.code'),
    (S,'view',1,21,100,'shared.code'),
    (datetime(2019,10,7,23),'view',1,10,100,'shared.code'),
    (datetime(2019,10,7,23),'view',1,10,100,'shared.code'),
    (datetime(2019,10,7,12),'view',1,20,100,'shared.code'),
    (T,'purchase',1,10,999,'future.code'),
    (datetime(2019,10,7,22),'cart',2,10,200,None),
    (datetime(2019,10,6),'view',2,20,200,None),
    (datetime(2019,10,2),'purchase',3,10,300,'three'),
    (datetime(2019,10,7,23),'cart',3,11,300,'three'),
    (datetime(2019,10,7,23),'view',5,20,500,'five'),
    (datetime(2019,10,7,23),'view',5,20,500,'five'),
    (datetime(2019,10,7,23),'view',6,20,None,'six'),
    (datetime(2019,10,7,23),'view',7,20,700,'seven'),
    (datetime(2019,10,7,23),'view',7,21,None,'seven'),
    (datetime(2019,10,7,23),'view',8,20,800,'eight'),
    (datetime(2019,10,7,23),'view',8,21,801,'eight'),
    (datetime(2019,10,6),'view',9,10,900,'old'),
    (datetime(2019,10,6,1),'view',9,10,900,'old'),
    (datetime(2019,10,7,23),'cart',9,99,901,'new'),
    (datetime(2019,10,7,23),'view',10,20,901,'new'),
    (datetime(2019,9,30,23,59,59),'view',1,10,100,'pre-source'),
]


def oracle(records,user,item,t):
    past=[r for r in records if S<=r[0]<t]
    item_history=[r for r in past if r[2]==item]
    latest=max((r[0] for r in item_history),default=None)
    cats={r[4] for r in item_history if r[0]==latest}
    category=next(iter(cats)) if len(cats)==1 and None not in cats else None
    recent=[r for r in past if r[0]>=t-timedelta(days=7)]
    def count(rows,kind):return sum(r[1]==kind for r in rows)
    def recency(rows,kind):
        last=max((r[0] for r in rows if r[1]==kind),default=None)
        return (t-last).total_seconds() if last is not None else None
    u=[r for r in recent if r[3]==user]
    pair=[r for r in recent if r[3]==user and r[2]==item]
    pair_full=[r for r in past if r[3]==user and r[2]==item]
    item24=[r for r in past if r[2]==item and r[0]>=t-timedelta(days=1)]
    values={}
    for kind in ['view','cart','purchase']:
        values['user_'+kind+'_7d']=count(u,kind)
        values['pair_'+kind+'_7d']=count(pair,kind)
    values['user_distinct_viewed_items_7d']=len({r[2] for r in u if r[1]=='view'})
    for kind in ['view','purchase']:
        values['pair_'+kind+'_recency_seconds']=recency(pair_full,kind)
        values['item_'+kind+'_24h']=count(item24,kind)
    values['item_distinct_viewers_7d']=len({r[3] for r in recent if r[2]==item and r[1]=='view'})
    usercat=[r for r in recent if r[3]==user and r[4]==category]
    itemcat=[r for r in recent if r[2]==item and r[4]==category]
    cat=[r for r in recent if r[4]==category]
    known=category is not None
    values['user_category_view_7d']=count(usercat,'view') if known else None
    values['user_category_view_share_7d']=(count(usercat,'view')/count(u,'view')) if known and count(u,'view') else None
    values['user_category_view_recency_seconds']=recency([r for r in past if r[3]==user and r[4]==category],'view') if known else None
    values['item_category_view_7d']=count(itemcat,'view') if known else None
    values['category_view_7d']=count(cat,'view') if known else None
    values['item_category_view_share_7d']=count(itemcat,'view')/count(cat,'view') if known and count(cat,'view') else None
    return values,category,(len(cats)>1)


class ManualFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.config=load_protocol(ROOT/'configs/protocols/clock-48h.json')
        self.registry=load_registry(ROOT/'configs/features/manual-18.json')
        self.con=duckdb.connect(':memory:')
        self.con.execute('SET threads=2')
        self.con.execute('''CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,
            user_id BIGINT,category_id BIGINT,category_code VARCHAR)''')
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',RECORDS)
        self.con.execute('CREATE TEMP TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
        self.con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,true)', [('q10',10,T),('q11',11,T)])
        self.con.execute('CREATE TEMP TABLE pilot_candidates(query_id VARCHAR,product_id BIGINT)')
        self.pairs=[('q10',i) for i in [1,2,3,5,6,7,8,9]]+[('q11',i) for i in [1,2,3]]
        self.con.executemany('INSERT INTO pilot_candidates VALUES (?,?)',self.pairs)

    def tearDown(self):self.con.close()

    def actual(self):
        cursor=self.con.execute('SELECT * FROM manual_features ORDER BY query_id,product_id')
        cols=[c[0] for c in cursor.description]
        return {(r[cols.index('query_id')],r[cols.index('product_id')]):dict(zip(cols,r)) for r in cursor.fetchall()}

    def test_all18_features_match_independent_full_row_oracle(self):
        result=create_manual_features(self.con,self.config,self.registry)
        self.assertEqual((result['feature_rows'],result['core_features']),(11,18))
        for (qid,item),actual in self.actual().items():
            expected,category,ambiguous=oracle(RECORDS,10 if qid=='q10' else 11,item,T)
            self.assertEqual(len(expected),18)
            for name,value in expected.items():
                with self.subTest(q=qid,item=item,feature=name):self.assertEqual(actual[name],value)
            self.assertEqual(actual['candidate_category_id'],category)
            self.assertEqual(actual['candidate_category_ambiguous'],ambiguous)

    def test_separate_sql_oracle_for_expiring_distinct_and_raw_counts(self):
        create_manual_features(self.con,self.config,self.registry)
        independent=duckdb.connect(':memory:')
        try:
            independent.execute('CREATE TABLE e(t TIMESTAMP,kind VARCHAR,item BIGINT,u BIGINT,c BIGINT,code VARCHAR)')
            independent.executemany('INSERT INTO e VALUES (?,?,?,?,?,?)',RECORDS)
            expected=independent.execute('''SELECT
                count(*) FILTER(WHERE u=10 AND kind='view'),
                count(DISTINCT u) FILTER(WHERE item=1 AND kind='view')
                FROM e WHERE t>='2019-10-01' AND t<'2019-10-08' ''').fetchone()
            row=self.actual()[('q10',1)]
            self.assertEqual((row['user_view_7d'],row['item_distinct_viewers_7d']),expected)
            self.con.execute("UPDATE pilot_queries SET anchor='2019-10-09'")
            create_manual_features(self.con,self.config,self.registry)
            expected=independent.execute("SELECT count(DISTINCT u) FROM e WHERE item=1 AND kind='view' AND t>='2019-10-02' AND t<'2019-10-09'").fetchone()[0]
            self.assertEqual(self.actual()[('q10',1)]['item_distinct_viewers_7d'],expected)
        finally:
            independent.close()

    def test_null_mixture_and_all_null_metadata_are_distinct(self):
        create_manual_features(self.con,self.config,self.registry)
        rows=self.actual()
        self.assertFalse(rows[('q10',5)]['candidate_category_missing'])
        self.assertTrue(rows[('q10',6)]['candidate_category_missing'])
        self.assertFalse(rows[('q10',6)]['candidate_category_ambiguous'])
        self.assertTrue(rows[('q10',7)]['candidate_category_ambiguous'])
        self.assertTrue(rows[('q10',8)]['candidate_category_ambiguous'])
        self.assertIsNone(rows[('q10',7)]['user_category_view_7d'])

    def test_named_code_is_not_required_and_known_empty_count_is_zero(self):
        create_manual_features(self.con,self.config,self.registry)
        row=self.actual()[('q10',2)]
        self.assertEqual(row['candidate_category_id'],200)
        self.assertEqual(row['user_category_view_7d'],0)
        self.assertEqual(row['user_category_view_share_7d'],0)
        self.assertIsNone(row['user_category_view_recency_seconds'])
        self.assertTrue(row['user_category_view_recency_seconds_missing'])

    def test_denominator_zero_stays_missing_with_support_and_flag(self):
        create_manual_features(self.con,self.config,self.registry)
        row=self.actual()[('q11',1)]
        self.assertEqual(row['user_view_7d'],0)
        self.assertEqual(row['user_category_view_7d'],0)
        self.assertIsNone(row['user_category_view_share_7d'])
        self.assertTrue(row['user_category_view_share_7d_missing'])

    def test_category_changes_do_not_reclassify_historical_events(self):
        create_manual_features(self.con,self.config,self.registry)
        row=self.actual()[('q10',9)]
        self.assertEqual(row['candidate_category_id'],901)
        self.assertEqual(row['item_category_view_7d'],0)
        self.assertEqual(row['category_view_7d'],1)
        self.assertEqual(row['item_category_view_share_7d'],0)
        self.assertEqual(row['user_category_view_7d'],0)

    def test_distinct_expiry_keeps_multiplicity_and_recency_uses_observed_prefix(self):
        self.con.execute("UPDATE pilot_queries SET anchor='2019-10-09'")
        # Source has a real purchase at Oct8 exactly; it is now past, although
        # its changed metadata intentionally affects category-conditional values.
        create_manual_features(self.con,self.config,self.registry)
        rows=self.actual()
        self.assertEqual(rows[('q10',1)]['item_distinct_viewers_7d'],2)
        self.assertEqual(rows[('q10',3)]['pair_purchase_7d'],1)
        self.con.execute("UPDATE pilot_queries SET anchor='2019-10-10'")
        create_manual_features(self.con,self.config,self.registry)
        row=self.actual()[('q10',3)]
        self.assertEqual(row['pair_purchase_7d'],0)  #Oct2 outside [Oct3,Oct10)
        self.assertEqual(row['pair_purchase_recency_seconds'],8*86400)

    def test_future_suffix_and_peer_permutation_preserve_every_feature(self):
        create_manual_features(self.con,self.config,self.registry)
        before=self.actual()
        shuffled=RECORDS.copy()
        random.Random(71).shuffle(shuffled)
        self.con.execute('DELETE FROM events')
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',shuffled)
        self.con.execute("INSERT INTO events VALUES ('2019-10-08','view',1,999,12345,'future')")
        create_manual_features(self.con,self.config,self.registry)
        self.assertEqual(before,self.actual())

    def test_later_clean_metadata_does_not_backfill_earlier_anchor(self):
        self.con.execute("INSERT INTO events VALUES ('2019-10-08 12:00:00','cart',7,99,700,'clean')")
        self.con.execute("INSERT INTO pilot_queries VALUES ('q10day2',10,'2019-10-09',true)")
        self.con.execute("INSERT INTO pilot_candidates VALUES ('q10day2',7)")
        create_manual_features(self.con,self.config,self.registry)
        rows=self.actual()
        self.assertTrue(rows[('q10',7)]['candidate_category_ambiguous'])
        self.assertFalse(rows[('q10day2',7)]['candidate_category_ambiguous'])
        self.assertEqual(rows[('q10day2',7)]['candidate_category_id'],700)

    def test_empty_candidates_and_queries_have_zero_row_typed_schema(self):
        self.con.execute('DELETE FROM pilot_candidates')
        result=create_manual_features(self.con,self.config,self.registry)
        self.assertEqual(result['feature_rows'],0)
        self.con.execute('DELETE FROM pilot_queries')
        result=create_manual_features(self.con,self.config,self.registry)
        self.assertEqual(result['feature_rows'],0)
        self.assertIn('item_category_view_share_7d',[r[0] for r in self.con.execute('DESCRIBE manual_features').fetchall()])

    def test_registry_rejects_unknown_fields_unsafe_names_and_non_nested_ratio(self):
        for mutate in [lambda r:r.update(surprise=True),
                       lambda r:r['features'][0].update(name='evil;DROP_TABLE'),
                       lambda r:r['features'][0].update(name='query_id'),
                       lambda r:r['features'][0].update(name='source_coverage_168h'),
                       lambda r:r['features'][0].update(window=True),
                       lambda r:r['features'][0].update(event_type={}),
                       lambda r:r['features'][-1].update(denominator='user_view_7d')]:
            r=deepcopy(self.registry);mutate(r)
            with self.assertRaises(ValueError):validate_registry(r)

    def test_invalid_anchor_and_expired_budget_fail_closed(self):
        self.con.execute("UPDATE pilot_queries SET anchor='2019-10-08 01:00:00' WHERE query_id='q10'")
        with self.assertRaisesRegex(ValueError,'UTC anchors'):
            create_manual_features(self.con,self.config,self.registry)
        def expired():raise TimeoutError('fixture expired')
        with self.assertRaisesRegex(TimeoutError,'fixture expired'):
            create_manual_features(self.con,self.config,self.registry,budget_check=expired)


class ManualRunnerTests(unittest.TestCase):
    def setUp(self):
        original_fixture=fixture_tests.fixture
        def with_categories(con):
            original_fixture(con)
            con.execute('ALTER TABLE events ADD COLUMN category_id BIGINT DEFAULT 100')
        with patch.object(fixture_tests,'fixture',side_effect=with_categories):
            fixture_tests.ProvenanceRunnerTests.setUp(self)
        active=patch.object(m,'ROOT',self.root)
        active.start();self.addCleanup(active.stop)
        (self.root/'scripts/manual_features.py').write_text((ROOT/'scripts/manual_features.py').read_text())
        self.registry_path=self.root/'configs/features/manual-18.json'
        self.registry_path.parent.mkdir(parents=True)
        self.registry_path.write_text((ROOT/'configs/features/manual-18.json').read_text())
        self.output=self.root/'artifacts/manual-features'

    def execute(self,**kwargs):
        return m.run(self.candidate,self.registry_path,self.output,acceptance_path=self.acceptance_path,**kwargs)

    def reports(self):
        return [json.loads(p.read_text()) for p in self.output.glob('*/report.json')]

    def test_synthetic_sealed_run_persists_identity_costs_and_feature_output(self):
        report=self.execute()
        self.assertEqual(report['status'],'complete')
        self.assertEqual((report['selected_queries'],report['feature_rows'],report['core_features']),(3,6,18))
        self.assertTrue(all(r['status']=='complete' for r in report['stages']))
        self.assertIn('verify_accepted_provenance',[r['stage'] for r in report['stages']])
        output=self.output/report['run_id']/'features.parquet'
        con=duckdb.connect(':memory:')
        try:self.assertEqual(con.execute('SELECT count(*) FROM read_parquet(?)',[str(output)]).fetchone()[0],6)
        finally:con.close()
        self.assertEqual(report['output_sha256'],fixture_tests.sha256_file(output))

    def test_label_independent_diagnostic_limit_changes_run_identity(self):
        full=self.execute()
        subset=self.execute(max_queries=1)
        self.assertEqual(subset['selected_queries'],1)
        self.assertNotEqual(full['run_id'],subset['run_id'])
        self.assertEqual(subset['selection']['label_policy'],'not_read_for_selection_or_feature_materialization')

    def test_valid_replaced_C_is_rejected_instead_of_silently_refingerprinted(self):
        cfile=self.candidate/'candidates.parquet'
        con=duckdb.connect(':memory:')
        try:
            con.execute('CREATE TABLE changed AS SELECT * FROM read_parquet(?)',[str(cfile)])
            con.execute('UPDATE changed SET popularity_distinct_users=popularity_distinct_users+1')
            con.execute('COPY changed TO ? (FORMAT PARQUET)',[str(cfile)])
        finally:con.close()
        with self.assertRaisesRegex(ValueError,'fingerprint changed'):
            self.execute()
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['identity_status'],'preparation')
        self.assertFalse(list(self.output.glob('*/features.parquet')))

    def test_changed_upstream_code_is_rejected_and_partial_report_saved(self):
        path=self.root/'scripts/candidate_pilot.py'
        path.write_text(path.read_text()+chr(10)+'# changed upstream code'+chr(10))
        with self.assertRaisesRegex(ValueError,'fingerprint changed'):
            self.execute()
        self.assertEqual(self.reports()[0]['status'],'failed')
        self.assertFalse(list(self.output.glob('*/features.parquet')))

    def test_first_guard_timeout_still_has_a_partial_attempt_report(self):
        with patch('scripts.anchor_pilot.RunDeadline.check',side_effect=TimeoutError('early fixture expiry')):
            with self.assertRaisesRegex(TimeoutError,'early fixture expiry'):
                self.execute()
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['error_type'],'TimeoutError')
        self.assertFalse(list(self.output.glob('*/features.parquet')))

    def test_connection_failure_keeps_identified_failure_report(self):
        with patch('duckdb.connect',side_effect=OSError('fixture open failure')):
            with self.assertRaisesRegex(OSError,'fixture open failure'):
                self.execute()
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['identity_status'],'identified')
        self.assertEqual(report['stages'][-1]['stage'],'open_source_read_only')
        self.assertEqual(report['stages'][-1]['status'],'failed')


if __name__=='__main__':unittest.main()
