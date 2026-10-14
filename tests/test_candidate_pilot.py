"""Small independent retrieval oracle, before labels are ever joined."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import random
import unittest

import duckdb

from scripts.candidate_pilot import build_candidates, create_candidates, coverage_report, verify_catalog
from scripts.protocol_manifest import load_protocol

ROOT=Path(__file__).resolve().parents[1]
T=datetime(2019,10,8)
RECORDS=[
    (datetime(2019,10,2),'purchase',10,1),
    (datetime(2019,10,2),'purchase',10,1),
    (datetime(2019,10,3),'purchase',10,2),
    (datetime(2019,10,4),'purchase',20,2),
    (datetime(2019,10,5),'purchase',30,3),
    (datetime(2019,10,2),'purchase',10,20),
    (datetime(2019,10,7,23,59,59),'view',30,10),
    (datetime(2019,10,7,23,59,59),'view',20,10),
    (datetime(2019,10,7,23,59,59),'view',20,10),
    (datetime(2019,10,7,23),'view',10,10),
    (datetime(2019,10,1),'view',50,10),
    (datetime(2019,9,30,23,59,59),'purchase',60,10),
    (T,'purchase',999,10),
]


def oracle(records,queries,popular_limit,recent_limit):
    """Python set/count oracle, with literal half-open windows and tie order."""
    result={}
    for qid,user,t in queries:
        past=[r for r in records if t-timedelta(days=7)<=r[0]<t]
        buyers=defaultdict(set)
        for _,kind,item,u in past:
            if kind=='purchase':buyers[item].add(u)
        popular=sorted(buyers,key=lambda item:(-len(buyers[item]),item))[:popular_limit]
        last={}
        for ts,kind,item,u in past:
            if u==user and kind in ['view','cart','purchase']:
                last[item]=max(ts,last.get(item,ts))
        recent=sorted(last,key=lambda item:(-last[item].timestamp(),item))[:recent_limit]
        for item in set(popular)|set(recent):
            result[(qid,item)]=(item in popular,item in recent,len(buyers[item]),
                popular.index(item)+1 if item in popular else None,
                recent.index(item)+1 if item in recent else None,
                last[item] if item in recent else None)
    return result


class CandidatePilotTests(unittest.TestCase):
    def setUp(self):
        self.config=load_protocol(ROOT/'configs/protocols/clock-48h.json')
        self.config['candidates'].update(popular_limit=2,recent_limit=2,max_unique=4)
        self.con=duckdb.connect(':memory:')
        self.con.execute('SET threads=2')
        self.con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT)')
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?)',RECORDS)
        self.con.execute('CREATE TEMP TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
        self.queries=[('q10',10,T),('q20',20,T),('q30',30,T)]
        self.con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,true)',self.queries)
        self.con.execute('CREATE TEMP TABLE pilot_labels(query_id VARCHAR,product_id BIGINT,catalog_seen_before BOOLEAN,pair_seen_before BOOLEAN)')
        self.con.executemany('INSERT INTO pilot_labels VALUES (?,?,?,?)',[
            ('q10',10,True,True),('q10',30,True,True),('q10',999,False,False),('q20',20,True,False)])

    def tearDown(self):
        self.con.close()

    def actual(self):
        return {(r[0],r[1]):tuple(r[2:]) for r in self.con.execute('SELECT * FROM pilot_candidates').fetchall()}

    def test_union_matches_independent_oracle_with_raw_duplicates_and_ties(self):
        result=build_candidates(self.con,self.config)
        self.assertEqual(self.actual(),oracle(RECORDS,self.queries,2,2))
        self.assertEqual(result['candidate_rows'],7)  #3+2+2, without refill
        self.assertEqual(self.actual()[('q10',10)][2],3)  #three buyers, four purchase rows
        self.assertEqual(self.actual()[('q10',20)][:2],(True,True))
        self.assertEqual(self.actual()[('q10',20)][4],1)  #same timestamp:product20 before30
        self.assertNotIn(('q10',999),self.actual())

    def test_full_target_denominators_keep_cold_and_unretrieved_items(self):
        result=build_candidates(self.con,self.config)
        r=result['daily_coverage'][0]
        self.assertEqual((r['queries'],r['positive_queries'],r['all_targets'],r['retrieved_targets']), (3,2,4,3))
        self.assertEqual(r['catalog_targets'],3)
        self.assertAlmostEqual(r['candidate_recall_positive_macro'],((2/3)+1)/2)
        self.assertEqual(r['informative_ranking_queries'],2)
        q=self.con.execute("SELECT candidate_count,target_count,retrieved_targets FROM pilot_coverage WHERE query_id='q30'").fetchone()
        self.assertEqual(q,(2,0,0))

    def test_generator_does_not_need_or_read_labels(self):
        self.con.execute('DROP TABLE pilot_labels')
        create_candidates(self.con,self.config)
        self.assertEqual(self.actual(),oracle(RECORDS,self.queries,2,2))

    def test_future_events_and_peer_permutations_preserve_fixed_query_candidates(self):
        create_candidates(self.con,self.config)
        before=self.actual()
        shuffled=RECORDS.copy()
        random.Random(71).shuffle(shuffled)
        self.con.execute('DELETE FROM events')
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?)',shuffled)
        self.con.execute("INSERT INTO events VALUES ('2019-10-08','purchase',777,10),('2019-10-09','purchase',888,20)")
        create_candidates(self.con,self.config)
        self.assertEqual(before,self.actual())

    def test_lower_boundary_is_included_and_preboundary_excluded(self):
        self.config['candidates'].update(recent_limit=20,max_unique=22)
        create_candidates(self.con,self.config)
        self.assertIn(('q10',50),self.actual())
        self.assertNotIn(('q10',60),self.actual())
        self.assertNotIn(('q10',999),self.actual())

    def test_past_bought_products_are_retained(self):
        create_candidates(self.con,self.config)
        self.assertEqual(self.actual()[('q20',10)][:2],(True,True))

    def test_no_popularity_leaves_recent_only_without_invented_fallback(self):
        self.con.execute("DELETE FROM events WHERE event_type='purchase'")
        result=build_candidates(self.con,self.config)
        self.assertEqual(result['candidate_rows'],2)
        self.assertTrue(all(not r[0] and r[1] for r in self.actual().values()))
        self.assertEqual(result['daily_coverage'][0]['empty_candidate_queries'],2)

    def test_empty_sources_preserve_queries_and_full_targets_as_misses(self):
        self.con.execute('DELETE FROM events')
        result=build_candidates(self.con,self.config)
        r=result['daily_coverage'][0]
        self.assertEqual((r['queries'],r['empty_candidate_queries'],r['all_targets'],r['retrieved_targets']), (3,3,4,0))
        self.assertEqual(r['candidate_recall_positive_macro'],0)
        self.assertEqual(self.actual(),{})

    def test_catalog_verifier_rejects_injected_future_product(self):
        create_candidates(self.con,self.config)
        self.con.execute("INSERT INTO pilot_candidates VALUES ('q10',999,false,true,0,NULL,1,'2019-10-08')")
        with self.assertRaisesRegex(ValueError,'strict-past'):
            verify_catalog(self.con,self.config)

    def test_invalid_query_identity_and_future_anchor_are_rejected(self):
        self.con.execute("INSERT INTO pilot_queries VALUES ('q10',100,'2019-10-08',true)")
        with self.assertRaisesRegex(ValueError,'unique'):
            create_candidates(self.con,self.config)
        self.con.execute("DELETE FROM pilot_queries WHERE user_id=100")
        self.con.execute("UPDATE pilot_queries SET anchor='2019-10-11' WHERE query_id='q10'")
        with self.assertRaisesRegex(ValueError,'UTC anchors'):
            create_candidates(self.con,self.config)

    def test_duplicate_or_partial_censored_labels_are_rejected_after_generation(self):
        create_candidates(self.con,self.config)
        before=self.actual()
        self.con.execute("INSERT INTO pilot_labels VALUES ('q20',20,true,false)")
        with self.assertRaisesRegex(ValueError,'unique binary'):
            coverage_report(self.con)
        self.con.execute("DELETE FROM pilot_labels WHERE query_id='q20'")
        self.con.execute("UPDATE pilot_queries SET label_is_mature=false WHERE query_id='q10'")
        with self.assertRaisesRegex(ValueError,'mature'):
            coverage_report(self.con)
        self.assertEqual(before,self.actual())

    def test_unknown_label_maturity_and_source_catalog_contradiction_are_rejected(self):
        self.con.execute("UPDATE pilot_queries SET label_is_mature=NULL WHERE query_id='q30'")
        with self.assertRaisesRegex(ValueError,'nonnull'):
            create_candidates(self.con,self.config)
        self.con.execute("UPDATE pilot_queries SET label_is_mature=true WHERE query_id='q30'")
        create_candidates(self.con,self.config)
        self.con.execute("UPDATE pilot_labels SET catalog_seen_before=false WHERE query_id='q20'")
        with self.assertRaisesRegex(ValueError,'catalog diagnosis'):
            coverage_report(self.con)

    def test_smaller_union_cap_requires_explicit_future_policy(self):
        self.config['candidates']['max_unique']=3
        with self.assertRaisesRegex(ValueError,'no-refill union'):
            create_candidates(self.con,self.config)

    def test_censoring_does_not_become_empty_negative(self):
        self.con.execute("UPDATE pilot_queries SET label_is_mature=false WHERE query_id='q30'")
        build_candidates(self.con,self.config)
        row=self.con.execute("SELECT target_count,retrieved_targets FROM pilot_coverage WHERE query_id='q30'").fetchone()
        self.assertEqual(row,(None,None))


if __name__=='__main__':unittest.main()
