"""Invented graph/SQL fixtures only; no Root-bound request or real inputs."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import duckdb
import discovery as d

A = datetime(2019, 10, 8)


def query(user=999):
    return d.Query(d.qid_for(user, A), user, A)


def seed_graph(profiles):
    return d.graph_from_edges((u,i) for u,items in profiles.items() for i in items)


class DiscoveryTests(unittest.TestCase):
    def test_global_Q100_ascii_hash_identity_and_timezone(self):
        rows = [(d.qid_for(u,a),u,a) for a in d.ANCHORS for u in range(1,2001)]
        first, permuted = d.freeze_queries(rows), d.freeze_queries(rows[::-1])
        self.assertEqual(first, permuted); self.assertEqual(len(first),100)
        expected = sorted(rows, key=lambda r:(hashlib.sha256(b'tlab-hyp061-q100-v1\0'+r[0].encode('ascii')).digest(),r[0].encode('ascii')))[:100]
        self.assertEqual([q.query_id for q in first], [r[0] for r in expected])
        decoded = sorted(rows, key=lambda r:hashlib.sha256(b'tlab-hyp061-q100-v1\0'+bytes.fromhex(r[0])).digest())[:100]
        self.assertNotEqual({q.query_id for q in first},{r[0] for r in decoded})
        aware = datetime(2019,10,8,3,tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(d.qid_for(-2,aware), hashlib.sha256(b'query|2026|2019-10-08T00:00:00Z|-2').hexdigest())
        with self.assertRaises(ValueError):
            d.freeze_queries(rows[:-1])

    def test_whole32_33_duplicate_edges_and_excluded_self(self):
        p = {1:(100,200),2:(100,200),0:tuple([100,200,*range(1000,1030)])}
        g32 = seed_graph(p)
        self.assertEqual(len(g32.profiles[0]),32)
        self.assertEqual(d.discover(g32,999,[100],{100})['source']['count'],[200])
        p[0] = (*p[0],1030)
        g33 = seed_graph(p)
        self.assertNotIn(0,g33.profiles)
        self.assertEqual(d.discover(g33,999,[100],{100})['source']['count'],[])
        self.assertEqual(g33.degrees[100],2)
        # A raw degree33 query user was already excluded; no second decrement.
        p[3] = (100,200)
        g = seed_graph(p)
        self.assertEqual(d.discover(g,0,[100],{100})['domain'][0]['support'],[[100,3,3,3]])
        duplicated = [(u,i) for u,items in p.items() for i in items for _ in range(2)]+[(None,100),(5,None)]
        self.assertEqual(d.graph_from_edges(duplicated).identity,g.identity)

    def test_audience513_removed_to512_before_guard(self):
        profiles = {0:(100,)}
        profiles.update({u:((100,200) if u<=3 else (100,)) for u in range(1,513)})
        g = seed_graph(profiles)
        self.assertEqual(g.degrees[100],513)
        yes = d.discover(g,0,[100],{100})
        self.assertEqual(yes['source']['count'],[200]); self.assertEqual(yes['rejection'][0]['degree'],512)
        no = d.discover(g,999,[100],{100})
        self.assertEqual(no['source']['count'],[]); self.assertEqual(no['rejection'][0]['reason'],'audience_guard')

    def test_heavy_audience_is_not_iterated_before_guard(self):
        class NoIterationPosting:
            def __len__(self):
                return 1000000
            def __iter__(self):
                raise AssertionError('Heavy posting must not be iterated')
        posting = NoIterationPosting()
        graph = d.Graph({}, {100:posting}, {100:1000000}, 'invented', {})
        result = d.discover(graph,999,[100],{100})
        self.assertEqual(result['source'],dict(count=[],cosine=[]))
        self.assertEqual(result['rejection'],[dict(seed=100,degree=1000000,reason='audience_guard')])
        self.assertEqual(result['profile_edge_visits'],0)
        bad = d.Graph({}, {100:posting}, {100:999999}, 'invented', {})
        with self.assertRaisesRegex(ValueError,'Incomplete seed audience'):
            d.discover(bad,999,[100],{100})

    def test_candidate_only_self_changes_global_norm_not_support(self):
        g = seed_graph({0:(200,),1:(100,200),2:(100,200),3:(100,200)})
        result = d.discover(g,0,[100],{100})
        row = result['domain'][0]
        self.assertEqual(row['support'],[[100,3,3,3]])
        self.assertEqual(row['count'],9/13)
        self.assertAlmostEqual(row['cosine'],(9/13)/3,places=15)
        self.assertNotEqual(row['cosine'],(9/13)/(12**0.5))

    def test_support2_3_and_self_witness_removed(self):
        g = seed_graph({0:(100,200),1:(100,200),2:(100,200)})
        self.assertEqual(d.discover(g,0,[100],{100})['domain'],[])
        result = d.discover(g,999,[100],{100})
        self.assertEqual(result['domain'][0]['support'][0][1],3)
        self.assertEqual(result['domain'][0]['count'],9/13)
        self.assertEqual(result['rejection'][0]['support_below3'],0)

    def test_confirmed_empty_and_no_fifth_seed_refill(self):
        empty = d.graph_from_edges([])
        result = d.discover(empty,0,[],set())
        self.assertEqual(result['source'],dict(count=[],cosine=[]))
        g = seed_graph({1:(500,600),2:(500,600),3:(500,600)})
        result = d.discover(g,0,[10,20,30,40,500],{10,20,30,40,500})
        self.assertEqual(result['seeds'],[10,20,30,40])
        self.assertEqual(result['source']['count'],[])
        self.assertTrue(all(r['reason']=='seed_view_empty' for r in result['rejection']))

    def test_incomplete_visited_adjacency_is_error_including_self(self):
        g = seed_graph({0:(100,200),1:(100,200),2:(100,200),3:(100,200)})
        bad = d.Graph({u:p for u,p in g.profiles.items() if u!=0},g.audience,g.degrees,g.identity,g.statistics)
        with self.assertRaisesRegex(ValueError,'Incomplete profile'):
            d.discover(bad,0,[100],{100})
        with self.assertRaises(TypeError):
            del g.profiles[0]

    def test_count_cosine_gold_reorders_but_same_two_endpoint_sets(self):
        p = {u:tuple([100]+([200] if u<=4 else [300] if u<=7 else [])) for u in range(1,101)}
        p.update({u:(200,) for u in range(101,197)})
        g = seed_graph(p); result = d.discover(g,999,[100],{100})
        self.assertEqual(result['source']['count'],[200,300]); self.assertEqual(result['source']['cosine'],[300,200])
        self.assertFalse(result['distinct_top20_sets'])
        rows = {r['product_id']:r for r in result['domain']}
        self.assertAlmostEqual(rows[200]['count'],8/7,places=15)
        self.assertAlmostEqual(rows[200]['cosine'],8/700,places=15)
        self.assertAlmostEqual(rows[300]['cosine'],9/(13*(300**0.5)),places=15)
        self.assertEqual(result['profile_edge_visits'],sum(len(g.profiles[u]) for u in g.audience[100]))

    def test_positive_multiseed_sum_gold_not_max_or_first(self):
        result = d.discover(seed_graph({u:(100,101,200) for u in (1,2,3)}),999,[101,100],{100,101})
        self.assertEqual(result['source'],dict(count=[200],cosine=[200]))
        self.assertEqual({r['product_id'] for r in result['domain']},{100,101,200})
        row = next(r for r in result['domain'] if r['product_id']==200)
        self.assertFalse(row['in_C0'])
        self.assertEqual(row['support'],[[101,3,3,3],[100,3,3,3]])
        self.assertEqual(row['count'],18/13)
        self.assertAlmostEqual(row['cosine'],6/13,places=15)
        self.assertEqual(result['profile_edge_visits'],18)

    def test_twentyone_endpoints_make_sets_different_on_same_graph(self):
        endpoints = tuple(range(200,221))
        p = {1:(100,*endpoints),2:(100,*endpoints),3:(100,*endpoints),4:(100,200)}
        p.update({u:(100,) for u in range(5,101)})
        p.update({u:(200,) for u in range(101,197)})
        result = d.discover(seed_graph(p),999,[100],{100})
        self.assertEqual(len(result['domain']),21)
        self.assertEqual(len(result['source']['count']),20); self.assertEqual(len(result['source']['cosine']),20)
        self.assertIn(200,result['source']['count']); self.assertNotIn(200,result['source']['cosine'])
        self.assertTrue(result['distinct_top20_sets'])

    def test_original_C0_excluded_before_top20_including_P181_200(self):
        q = query(); endpoints = tuple(range(10,31))
        g = seed_graph({1:(1,*endpoints),2:(1,*endpoints),3:(1,*endpoints),4:(1,*range(10,30))})
        products = [*range(1000,1180),*range(10,30)]
        rows = [(q.query_id,i,True,False,r,None,None) for r,i in enumerate(products,1)]
        rows.append((q.query_id,1,False,True,None,1,A-timedelta(seconds=1)))
        C0,P,R = d.original_sources(q,rows)
        result = d.discover(g,q.user_id,R,C0)
        self.assertEqual(result['source']['count'],[30]); self.assertEqual(result['source']['cosine'],[30])
        native = d.candidate_union(P,R,result['source']['count'])
        self.assertEqual(len(native),182); self.assertIn(30,native)
        self.assertTrue(set(range(10,30)).isdisjoint(native))

    def test_overlap_underfill_no_refill_and_two_new_endpoints(self):
        g = seed_graph({1:(10,20,30),2:(10,20,30),3:(10,20,30)})
        result = d.discover(g,999,[10],{10,40})
        self.assertEqual(set(result['source']['count']),{20,30}); self.assertEqual(len(result['source']['count']),2)
        native = d.candidate_union([10,40],[10],result['source']['count'])
        self.assertEqual(native[:2],[10,40]); self.assertEqual(len(native),4)

    def test_signed_hash_ties_exact_ids_and_collision_fallback(self):
        endpoints = [-2,0,2,2**63-1,-2**63]
        g = seed_graph({u:(100,*endpoints) for u in (1,2,3)})
        expected = sorted(endpoints,key=lambda i:(hashlib.sha256(str(i).encode('ascii')).digest(),i))
        self.assertEqual(d.discover(g,999,[100],{100})['source']['count'],expected)
        with patch.object(d.hashlib,'sha256',side_effect=lambda raw:SimpleNamespace(digest=lambda:b'\0'*32)):
            self.assertEqual(d.discover(g,999,[100],{100})['source']['count'],sorted(endpoints))
        with self.assertRaises(ValueError):
            d.graph_from_edges([(True,1)])

    def test_R20_timestamp_then_signedID_and_source_flag_validation(self):
        q = query(); stamp = A-timedelta(seconds=1)
        rows = [(q.query_id,i,False,True,None,r,stamp) for r,i in enumerate((-2,0,2),1)]
        self.assertEqual(d.original_sources(q,rows)[2],[-2,0,2])
        bad = [(q.query_id,2,False,True,None,1,stamp),(q.query_id,-2,False,True,None,2,stamp)]
        with self.assertRaisesRegex(ValueError,'Canonical R'):
            d.original_sources(q,bad)
        with self.assertRaises(ValueError):
            d.original_sources(q,[(q.query_id,1,False,True,None,1,A)])
        unequal = [(q.query_id,20,False,True,None,1,A-timedelta(seconds=1)),
                   (q.query_id,-2,False,True,None,2,A-timedelta(seconds=2))]
        self.assertEqual(d.original_sources(q,unequal)[2],[20,-2])
        wrong = [(q.query_id,-2,False,True,None,1,A-timedelta(seconds=2)),
                 (q.query_id,20,False,True,None,2,A-timedelta(seconds=1))]
        with self.assertRaisesRegex(ValueError,'Canonical R'):
            d.original_sources(q,wrong)

    def test_R20_literal_sevenday_lower_boundary(self):
        q = query()
        accepted = (q.query_id,1,False,True,None,1,datetime(2019,10,1,0,0,0))
        rejected = (q.query_id,1,False,True,None,1,datetime(2019,9,30,23,59,59))
        self.assertEqual(d.original_sources(q,[accepted])[2],[1])
        with self.assertRaisesRegex(ValueError,'Strict-past7d'):
            d.original_sources(q,[rejected])

    def test_primary_secondary_survive_receipt_write_failure(self):
        with tempfile.TemporaryDirectory(prefix='hyp061-failure-invented-',dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder); request_path = root/'invented-request.json'
            fake = dict(path=str(root/'never-read.duckdb'),bytes=0,sha256='0'*64)
            request = dict(version=1,db=fake,queries=[None]*3,candidates=[None]*3,bridge_ref=fake,source_rows=1,
                limits=dict(cpu_seconds=10,wall_seconds=20,rss_bytes=512*2**20,spill_bytes=32*2**20,output_bytes=8*2**20,admitted_edges=1000000))
            request_path.write_text(json.dumps(request))
            primary = RuntimeError('retained-primary-marker'); actual_ref = d.file_ref; calls = []
            def ref(path,check):
                calls.append(str(path))
                if len(calls) <= 2:
                    return actual_ref(path,check)
                if len(calls) == 3:
                    raise primary
                raise OSError('secondary-late-pin-marker')
            def receipt_failure(path,body,check=lambda extra=0:None):
                self.assertEqual(Path(path).name,'report.json')
                self.assertIn('secondary-late-pin-marker',' '.join(primary.__notes__))
                raise OSError('receipt-write-marker')
            with patch.object(d,'file_ref',side_effect=ref), patch.object(d,'write_json',side_effect=receipt_failure):
                with self.assertRaises(RuntimeError) as caught:
                    d.run(request_path,root/'output')
            self.assertIs(caught.exception,primary)
            self.assertEqual(len(calls),4)  # Initial DB failure; late pins stop at first failure.
            notes = '\n'.join(primary.__notes__)
            self.assertIn('secondary-late-pin-marker',notes); self.assertIn('late pins fail-fast',notes)
            self.assertIn('receipt-write-marker',notes); self.assertFalse((root/'output'/'report.json').exists())

    def test_SQL_complete_window_future_peer_null_duplicate_invariance(self):
        con = duckdb.connect(':memory:',config={'threads':'2','memory_limit':'32MB','max_temp_directory_size':'0B'})
        try:
            con.execute('CREATE TABLE discovery_events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT)')
            left = A-timedelta(days=7)
            rows = [(left,'view',10,1),(left,'view',10,1),(A-timedelta(seconds=1),'view',20,2),
                    (A,'view',30,3),(A+timedelta(seconds=1),'view',40,4),(left-timedelta(seconds=1),'view',50,5),
                    (left,'cart',60,6),(left,'view',None,7),(left,'view',70,None)]
            con.executemany('INSERT INTO discovery_events VALUES (?,?,?,?)',rows)
            before = d.extract_graph(con,A)
            self.assertEqual(dict(before.profiles),{1:(10,),2:(20,)})
            con.execute("INSERT INTO discovery_events VALUES(TIMESTAMP '2019-10-30','view',999,999)")
            self.assertEqual(d.extract_graph(con,A).identity,before.identity)
        finally:
            con.close()

    def test_SQL_degree_is_whole_profile_and_cap_preallocation(self):
        con = duckdb.connect(':memory:',config={'threads':'2','memory_limit':'32MB','max_temp_directory_size':'0B'})
        try:
            con.execute('CREATE TABLE discovery_events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT)')
            con.executemany('INSERT INTO discovery_events VALUES (?,?,?,?)',[(A-timedelta(seconds=1),'view',i,u) for u,n in ((1,32),(2,33)) for i in range(n)])
            g = d.extract_graph(con,A)
            self.assertEqual(len(g.profiles[1]),32); self.assertNotIn(2,g.profiles)
            self.assertEqual(g.statistics['raw_edges'],65); self.assertEqual(g.statistics['admitted_edges'],32)
            with self.assertRaisesRegex(ValueError,'Admitted edge cap'):
                d.extract_graph(con,A,edge_cap=31)
        finally:
            con.close()

    def test_standalone100Q_on_invented_typed9_and_parquet_inputs(self):
        with tempfile.TemporaryDirectory(prefix='hyp061-invented-',dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder); db = root/'invented.duckdb'
            con = duckdb.connect(str(db),config={'threads':'2','memory_limit':'64MB'})
            con.execute('CREATE TABLE events('+','.join(n+' '+t for n,t in d.SOURCE_COLUMNS)+')')
            con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',[(A-timedelta(days=4),'view',i,None,None,None,None,u,'fixture') for u in (3001,3002,3003) for i in (100,200)])
            qp,cp = [],[]
            for anchor in d.ANCHORS:
                stamp = anchor.strftime('%Y-%m-%dT00:00:00Z')
                con.execute("CREATE OR REPLACE TEMP TABLE fixture_q AS SELECT sha256('query|2026|"+stamp+"|'||CAST(i AS VARCHAR)) query_id,i::BIGINT user_id,TIMESTAMP '"+anchor.isoformat()+"' anchor FROM range(1,2001) t(i)")
                con.execute("INSERT INTO events SELECT anchor-INTERVAL '1 second','cart',100,NULL,NULL,NULL,NULL,user_id,'fixture' FROM fixture_q")
                qpath,cpath = root/(stamp[:10]+'-q.parquet'),root/(stamp[:10]+'-c.parquet')
                con.execute('COPY fixture_q TO ? (FORMAT PARQUET)',[str(qpath)])
                con.execute("COPY (SELECT query_id,100::BIGINT product_id,false from_popular,true from_recent,NULL::BIGINT popular_source_rank,1::BIGINT recent_source_rank,anchor-INTERVAL '1 second' last_user_event_time FROM fixture_q) TO ? (FORMAT PARQUET)",[str(cpath)])
                qp.append(qpath);cp.append(cpath)
            rows = con.execute('SELECT count(*) FROM events').fetchone()[0];con.close()
            bridge = root/'invented-identity-only.json';bridge.write_text('{"scope":"invented fixture, no runtime authority"}')
            desc = lambda p:dict(path=str(p),**d.file_ref(p,lambda:None))
            request = dict(version=1,db=desc(db),queries=list(map(desc,qp)),candidates=list(map(desc,cp)),bridge_ref=desc(bridge),source_rows=rows,
                limits=dict(cpu_seconds=10,wall_seconds=20,rss_bytes=512*2**20,spill_bytes=32*2**20,output_bytes=8*2**20,admitted_edges=1000000))
            request_path = root/'invented-request.json';request_path.write_text(json.dumps(request))
            output = root/'output';self.assertEqual(d.run(request_path,output),0)
            report = json.loads((output/'report.json').read_text())
            self.assertEqual(len(report['per_query']),100);self.assertEqual(report['event_passes_reserved'],3)
            self.assertEqual(report['profile_edge_visits'],600) # Shared traversal, not1200 for two scores.
            self.assertEqual(report['mechanism_thresholds'],dict(nonempty_queries=100,distinct_set_queries=0))
            self.assertEqual(report['physical_io'],'UNKNOWN');self.assertEqual(report['fits'],0)
            self.assertEqual(len(report['outputs']),101)
            for row in report['per_query']:
                artifact = json.loads((output/(row['query_id']+'.json')).read_text())
                self.assertEqual(artifact['source'],dict(count=[200],cosine=[200]))
                self.assertEqual(artifact['C_count'],[100,200])


if __name__ == '__main__':
    signal.alarm(30); resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    started,cpu = time.monotonic(),time.process_time()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiscoveryTests))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss; rss = int(rss if sys.platform=='darwin' else rss*1024)
    record = dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                  wall_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,rss_bytes=rss,
                  fits=0,real_inputs_read=0,duckdb=duckdb.__version__,success=result.wasSuccessful() and rss<=512*2**20)
    record['exit_code'] = 0 if record['success'] else 1
    print(json.dumps(record,sort_keys=True),flush=True); sys.exit(record['exit_code'])
