"""Direct-list metadata oracle, independent of production SQL/LOO algebra."""
from copy import deepcopy
from datetime import datetime,timedelta
import math
import random
import unittest

import duckdb
import numpy as np
import scripts.metadata_price_features as m

S=datetime(2019,10,1)
T=datetime(2019,10,10)
P=T-timedelta(seconds=1)
# (timestamp,item,user,category,code,brand,price)
RECORDS=[
    (S,1,11,10,'old','old',9.),
    (P,1,99,20,'twenty','new',99.), # global other-user latest, category move
    (P,1,99,20,'twenty','new',99.), # duplicate cannot add reference weight
    (P,2,12,20,'twenty','value:literal',199.),
    (P,3,13,30,None,None,0.),
    (P,4,14,40,'forty','state:missing',-1.),
    (P,5,15,50,'fifty','x',None),
    (P,6,16,60,'sixty','x',4.),
    (P,6,17,None,'sixty',None,None), # field ambiguities independently retained
    (P,7,17,70,'seventy','a',7.),
    (P,7,18,70,'seventy','b',8.), # ambiguous brand/price, category clean
    (P,8,18,70,'seventy','x',10.), # outsideC, valid peer for invalid own price
    (S,9,19,90,'ninety','x',3.), # past candidate outside active7d reference
    (P,10,20,90,'ninety','x',8.), # only active peer, outsideC
    (P,11,21,110,'first','x',6.),
    (P,12,22,110,'second','x',7.), # dictionary conflict across products
    (S,13,23,130,'recovered','old',3.),
    (P,13,24,130,None,'new',4.), # recover past code, don't backfill brand/price
    (P,14,24,140,'fourteen','x',5.), # singleton reference
    (P,15,24,150,'x','x',5.),
    (P,15,25,151,'x','x',5.), # multi-known category
    (P,16,26,None,None,None,None), # allNULL fields
    (P,19,26,190,'c','x',0.),
    (P,19,27,190,'c','x',None), # observed zero + NULL is ambiguous, not clean0
    (T,1,11,999,'future','future',1e6), # timestamp peer not past
    (T+timedelta(days=1),13,11,130,'conflict','future',float('inf')),
    (S-timedelta(seconds=1),17,11,170,'outside-source','x',2.),
]
ITEMS=[1,2,3,4,5,6,7,9,11,13,14,15,16,17,18,19]


def oracle(records,item,t):
    past=[r for r in records if S<=r[0]<t]
    def resolve(rows,index):
        values={r[index] for r in rows}
        if len(values)==1 and None not in values:
            return next(iter(values)),False
        return None,len(values)>1
    snapshots={}
    active={r[1] for r in past if r[0]>=t-timedelta(days=7)}
    relevant=active|{item}
    for product in relevant:
        history=[r for r in past if r[1]==product]
        latest=max((r[0] for r in history),default=None)
        bucket=[r for r in history if r[0]==latest]
        if any(r[6] is not None and not math.isfinite(r[6]) for r in bucket):
            raise ValueError('nonfinite source')
        snapshots[product]=[resolve(bucket,i) for i in [3,4,5,6]]
    (category,cat_amb),(code,code_amb),(brand,brand_amb),(price,price_amb)=snapshots[item]
    named={r[4] for r in past if category is not None and r[3]==category and r[4] is not None}
    recovered=len(named)==1 and code!=next(iter(named))
    positive=price is not None and price>0
    z=math.log1p(price) if positive else None
    peers=[]
    if category is not None:
        for other in active:
            (oc,_),_,_,(op,_)=snapshots[other]
            if other!=item and oc==category and op is not None and op>0:
                peers.append(math.log1p(op))
    support=len(peers) if category is not None else None
    mean=math.fsum(peers)/len(peers) if peers else None
    difference=z-mean if z is not None and mean is not None else None
    def nominal(value,ambiguous=False):
        return 'value:'+str(value) if value is not None else 'state:ambiguous' if ambiguous else 'state:missing'
    return dict(category_id_nominal=nominal(category,cat_amb),
        category_code_by_id=nominal(next(iter(named)) if len(named)==1 else None,len(named)>1),
        brand=nominal(brand,brand_amb),brand_missing=brand is None,brand_ambiguous=brand_amb,
        code_missing=category is None or not named,code_ambiguous=len(named)>1,code_recovered=recovered,
        log_price=z,price_missing=price is None,price_ambiguous=price_amb,
        price_zero=price==0,price_negative=price is not None and price<0,
        category_peer_log_price_mean=mean,category_peer_product_support=support,
        category_log_price_difference=difference,category_peer_mean_missing=mean is None,
        category_price_difference_missing=difference is None)


class MetadataPriceTests(unittest.TestCase):
    def setUp(self):
        self.con=duckdb.connect(':memory:')
        self.con.execute('SET threads=2')
        self.con.execute('''CREATE TABLE events(event_time TIMESTAMP,product_id BIGINT,user_id BIGINT,
            category_id BIGINT,category_code VARCHAR,brand VARCHAR,price DOUBLE)''')
        self.records=list(RECORDS)
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?)',self.records)
        self.con.execute('CREATE TABLE metadata_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)')
        self.con.execute("INSERT INTO metadata_queries VALUES ('q',11,?)",[T])
        self.con.execute('''CREATE TABLE metadata_pairs(query_id VARCHAR,product_id BIGINT,
            candidate_category_id BIGINT,candidate_category_ambiguous BOOLEAN,candidate_category_missing BOOLEAN)''')
        rows=[]
        for item in ITEMS:
            history=[r for r in self.records if S<=r[0]<T and r[1]==item]
            latest=max((r[0] for r in history),default=None)
            values={r[3] for r in history if r[0]==latest}
            category=next(iter(values)) if len(values)==1 and None not in values else None
            rows.append(('q',item,category,len(values)>1,category is None))
        self.con.executemany('INSERT INTO metadata_pairs VALUES (?,?,?,?,?)',rows)

    def tearDown(self):self.con.close()

    def create(self):
        return m.create_metadata_price_features(self.con,m.SPEC,source_start=S,source_end=datetime(2019,11,1))

    def rows(self):
        c=self.con.execute('SELECT * FROM metadata_price_features ORDER BY query_id,product_id')
        names=[r[0] for r in c.description]
        return {r[1]:dict(zip(names,r)) for r in c.fetchall()}

    def test_all_pairs_match_direct_list_oracle_and_fixed_schema(self):
        result=self.create()
        self.assertEqual((result['queries'],result['pairs']),(1,len(ITEMS)))
        actual=self.rows()
        self.assertEqual(list(next(iter(actual.values()))),['query_id','product_id',*m.NOMINAL,*m.NUMERIC])
        for item,row in actual.items():
            for key,value in oracle(self.records,item,T).items():
                with self.subTest(item=item,feature=key):
                    if isinstance(value,float):self.assertAlmostEqual(row[key],value,places=12)
                    else:self.assertEqual(row[key],value)

    def test_piecewise_nullable_loo_unknown_empty_nonmember_singleton(self):
        self.create();r=self.rows()
        self.assertEqual(r[1]['category_peer_product_support'],1)
        self.assertAlmostEqual(r[1]['category_peer_log_price_mean'],math.log1p(199))
        self.assertEqual(r[7]['category_peer_product_support'],1)
        self.assertAlmostEqual(r[7]['category_peer_log_price_mean'],math.log1p(10))
        self.assertIsNone(r[7]['category_log_price_difference'])
        self.assertEqual(r[9]['category_peer_product_support'],1) # not N-1
        self.assertEqual(r[14]['category_peer_product_support'],0)
        self.assertIsNone(r[14]['category_peer_log_price_mean'])
        self.assertEqual(r[3]['category_peer_product_support'],0)
        self.assertIsNone(r[16]['category_peer_product_support'])

    def test_latest_independent_fields_and_dictionary_provenance(self):
        self.create();r=self.rows()
        self.assertEqual(r[1]['category_id_nominal'],'value:20')
        self.assertEqual(r[1]['brand'],'value:new')
        self.assertTrue(r[6]['price_ambiguous']);self.assertTrue(r[6]['brand_ambiguous'])
        self.assertTrue(r[7]['price_ambiguous']);self.assertEqual(r[7]['category_id_nominal'],'value:70')
        self.assertEqual(r[13]['category_code_by_id'],'value:recovered');self.assertTrue(r[13]['code_recovered'])
        raw=self.con.execute('SELECT latest_code,dictionary_code,dictionary_first_known FROM metadata_price_provenance WHERE product_id=13').fetchone()
        self.assertEqual(raw,(None,'recovered',S))
        self.assertTrue(r[11]['code_ambiguous']);self.assertFalse(r[11]['code_missing'])

    def test_zero_negative_and_missing_are_distinct_from_ambiguity(self):
        self.create();r=self.rows()
        self.assertTrue(r[3]['price_zero']);self.assertFalse(r[3]['price_missing']);self.assertFalse(r[3]['price_ambiguous'])
        self.assertTrue(r[4]['price_negative']);self.assertFalse(r[4]['price_missing'])
        self.assertTrue(r[5]['price_missing']);self.assertFalse(r[5]['price_ambiguous'])
        self.assertTrue(r[7]['price_missing']);self.assertTrue(r[7]['price_ambiguous'])
        self.assertFalse(r[7]['price_zero']);self.assertFalse(r[7]['price_negative'])
        self.assertTrue(r[19]['price_missing']);self.assertTrue(r[19]['price_ambiguous']);self.assertFalse(r[19]['price_zero'])

    def test_suffix_peers_permutations_and_duplicate_reference_invariance(self):
        self.create();expected=self.rows()
        self.con.execute('DELETE FROM events WHERE event_time>=?',[T])
        rows=[(T,1,999,20,'conflict','changed',float('nan')),
              (T+timedelta(days=2),2,888,20,'changed',None,float('-inf'))]
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?)',rows)
        self.create();self.assertEqual(self.rows(),expected)
        self.con.execute('INSERT INTO events SELECT * FROM events WHERE product_id=2 AND event_time<?',[T])
        self.create();self.assertEqual(self.rows(),expected)
        self.con.execute('CREATE OR REPLACE TABLE events AS SELECT * FROM events ORDER BY user_id DESC,event_time DESC')
        self.create();self.assertEqual(self.rows(),expected)

    def test_relevant_latest_nonfinite_rejected_even_invalid_or_outside_candidates(self):
        for bad in [float('nan'),float('inf'),float('-inf')]:
            with self.subTest(bad=bad):
                self.con.execute('UPDATE events SET price=? WHERE product_id=8',[bad])
                with self.assertRaisesRegex(ValueError,'Nonfinite price'):self.create()
        self.con.execute('UPDATE events SET price=10 WHERE product_id=8')
        # Older invalid price is not latest; it cannot invalidate a past snapshot.
        self.con.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',[S,8,18,70,'seventy','x',float('inf')])
        self.create()

    def test_float32_bytes_namespace_masks_and_unseen_values(self):
        self.create();numeric,nominal=m.model_arrays(self.con)
        self.assertEqual(numeric.dtype,np.float32);self.assertEqual(nominal.dtype,object)
        self.assertEqual(numeric.shape,(len(ITEMS),15));self.assertEqual(nominal.shape,(len(ITEMS),3))
        self.assertIn(b'value:state:missing',nominal[:,2]);self.assertIn(b'value:value:literal',nominal[:,2])
        self.assertFalse(np.isinf(numeric).any());self.assertTrue(np.isnan(numeric).any())
        counts=m.validate_train_cardinality(nominal)
        self.assertEqual(counts['brand'],len(set(nominal[:,2])))

    def test_corrupted_masks_flags_and_nominal_fail_closed(self):
        self.create()
        self.con.execute('UPDATE metadata_price_features SET category_peer_mean_missing=false WHERE product_id=14')
        with self.assertRaisesRegex(ValueError,'mask'):m.model_arrays(self.con)
        self.create();self.con.execute('UPDATE metadata_price_features SET brand=NULL WHERE product_id=14')
        with self.assertRaisesRegex(ValueError,'nominal'):m.model_arrays(self.con)
        self.create();self.con.execute("UPDATE metadata_price_features SET log_price='Infinity'::DOUBLE WHERE product_id=14")
        with self.assertRaisesRegex(ValueError,'Nonfinite'):m.model_arrays(self.con)

    def test_category_gate_checks_values_and_ambiguity_not_just_keys(self):
        self.con.execute('UPDATE metadata_pairs SET candidate_category_id=999 WHERE product_id=1')
        with self.assertRaisesRegex(ValueError,'005'):self.create()
        self.con.execute('UPDATE metadata_pairs SET candidate_category_id=20 WHERE product_id=1')
        self.con.execute('UPDATE metadata_pairs SET candidate_category_ambiguous=false WHERE product_id=6')
        with self.assertRaisesRegex(ValueError,'005'):self.create()

    def test_key_cap_orphan_duplicate_and_nondaily_queries_rejected(self):
        with self.assertRaises(ValueError):
            m.create_metadata_price_features(self.con,m.SPEC,source_start=S,source_end=T+timedelta(days=1),max_pairs=1)
        self.con.execute("INSERT INTO metadata_pairs VALUES ('q',1,20,false,false)")
        with self.assertRaises(ValueError):self.create()
        self.con.execute('DELETE FROM metadata_pairs WHERE product_id=1')
        self.con.execute("INSERT INTO metadata_pairs VALUES ('orphan',1,20,false,false)")
        with self.assertRaises(ValueError):self.create()
        self.con.execute("DELETE FROM metadata_pairs WHERE query_id='orphan'")
        self.con.execute('UPDATE metadata_queries SET anchor=anchor+INTERVAL 1 SECOND')
        with self.assertRaises(ValueError):self.create()

    def test_empty_outputs_are_typed_and_replace_previous_run(self):
        self.create();self.con.execute('DELETE FROM metadata_pairs');self.con.execute('DELETE FROM metadata_queries')
        result=self.create();self.assertEqual((result['queries'],result['pairs']),(0,0))
        numeric,nominal=m.model_arrays(self.con)
        self.assertEqual(numeric.shape,(0,15));self.assertEqual(nominal.shape,(0,3))
        self.assertEqual(self.con.execute('SELECT count(*) FROM metadata_price_reference').fetchone()[0],0)

    def test_actual_encoded_cardinality_including_sentinels_cap(self):
        nominal=np.array([[b'value:'+str(i).encode(),b'state:missing',b'value:a'] for i in range(4096)],dtype=object)
        self.assertEqual(m.validate_train_cardinality(nominal)['category_id_nominal'],4096)
        too_many=np.vstack([nominal,np.array([[b'state:missing',b'state:missing',b'value:a']],dtype=object)])
        with self.assertRaisesRegex(ValueError,'cardinality'):m.validate_train_cardinality(too_many)
        invalid=nominal.copy();invalid[0,0]='value:a'
        with self.assertRaisesRegex(ValueError,'bytes'):m.validate_train_cardinality(invalid)

    def test_randomized_all_pairs_direct_oracle_two_days_and_window_boundary(self):
        rng=random.Random(2026)
        records=[]
        for item in range(1,41):
            for hour in [0,24,48,72,168,192,215]:
                category=rng.choice([None,10,20,30])
                row=(S+timedelta(hours=hour),item,rng.randrange(1,6),category,
                     rng.choice([None,'a','b']),rng.choice([None,'x','y']),rng.choice([None,0.,-1.,1.,9.,99.]))
                records.append(row)
                if rng.randrange(3)==0:
                    records.append(row[:2]+(99,)+row[3:5]+(None,row[6]))
        self.con.execute('DELETE FROM events');self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?)',records)
        self.con.execute('DELETE FROM metadata_queries');self.con.execute('DELETE FROM metadata_pairs')
        for qid,t in [('a',T),('b',T+timedelta(days=1))]:
            self.con.execute('INSERT INTO metadata_queries VALUES (?,11,?)',[qid,t])
            for item in range(1,41):
                history=[r for r in records if S<=r[0]<t and r[1]==item]
                latest=max((r[0] for r in history),default=None)
                cats={r[3] for r in history if r[0]==latest}
                c=next(iter(cats)) if len(cats)==1 and None not in cats else None
                self.con.execute('INSERT INTO metadata_pairs VALUES (?,?,?,?,?)',[qid,item,c,len(cats)>1,c is None])
        self.create()
        cursor=self.con.execute('SELECT * FROM metadata_price_features ORDER BY query_id,product_id')
        names=[r[0] for r in cursor.description]
        for row in cursor.fetchall():
            actual=dict(zip(names,row))
            t=T if row[0]=='a' else T+timedelta(days=1)
            for name,value in oracle(records,row[1],t).items():
                with self.subTest(query=row[0],item=row[1],feature=name):
                    if isinstance(value,float):self.assertAlmostEqual(actual[name],value,places=12)
                    else:self.assertEqual(actual[name],value)
        # Exactly the inclusive lower endpoint contributes active eligibility;
        # one second earlier doesn't. Neither changes current snapshot policy.
        self.con.execute('DELETE FROM events');self.con.execute('DELETE FROM metadata_pairs')
        self.con.execute("DELETE FROM metadata_queries WHERE query_id='b'")
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?)',[
            (T-timedelta(days=7),101,11,100,'c','x',9.),
            (T-timedelta(days=7,seconds=1),102,11,100,'c','x',99.)])
        self.con.executemany('INSERT INTO metadata_pairs VALUES (?,?,?,?,?)',[('a',101,100,False,False),('a',102,100,False,False)])
        self.create()
        self.assertEqual(self.con.execute('SELECT product_id,category_peer_product_support FROM metadata_price_features ORDER BY product_id').fetchall(),[(101,0),(102,1)])
        m.model_arrays(self.con)

    def test_price_brand_and_conditional_support_mask_corruption_rejected(self):
        for change in ["price_missing=true WHERE product_id=1", "brand_missing=false WHERE product_id=6",
                       "category_peer_product_support=NULL WHERE product_id=1", "code_recovered=true WHERE product_id=11"]:
            self.create();self.con.execute('UPDATE metadata_price_features SET '+change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'mask|Recovered'):m.model_arrays(self.con)

    def test_fixed_spec_rejects_schema_or_nested_type_drift(self):
        self.assertEqual(m.validate_spec(m.SPEC),m.SPEC)
        for change in ['numeric_columns','reference_hours','gate']:
            value=deepcopy(m.SPEC)
            if change=='numeric_columns':value[change].reverse()
            elif change=='reference_hours':value[change]=24
            else:value[change]['threads']=True
            with self.assertRaises(ValueError):m.validate_spec(value)




class MetadataGateTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import json
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patch=patch.object(m,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        for name in [*m.GATE_CODE,'pyproject.toml']:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture '+name)
        self.spec_path=self.root/'configs/features/metadata-price.json';self.spec_path.parent.mkdir(parents=True)
        self.spec_path.write_text(json.dumps(m.SPEC))
        self.acceptance=self.root/'accepted.json';self.acceptance.write_text('{}')
        self.approval=self.root/'gate.json'
        self.source=self.root/'source.duckdb'
        c=duckdb.connect(str(self.source));c.execute('''CREATE TABLE events(event_time TIMESTAMP,
            product_id BIGINT,user_id BIGINT,category_id BIGINT,category_code VARCHAR,brand VARCHAR,price DOUBLE)''')
        c.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?)',[(S,1,11,10,'code','a',9.),(S,2,12,10,'code','b',99.),
            (T-timedelta(seconds=1),1,11,10,'code','a',9.),(T-timedelta(seconds=1),2,12,10,'code','b',99.)])
        c.execute('CREATE TABLE q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)')
        c.executemany('INSERT INTO q VALUES (?,?,?)',[(f'q{day}-{i}',1000+day*200+i,T+timedelta(days=day)) for day in [0,1] for i in range(70)])
        c.execute('''CREATE TABLE f AS SELECT query_id,1::BIGINT product_id,10::BIGINT candidate_category_id,
            false candidate_category_ambiguous,false candidate_category_missing FROM q''')
        c.execute('COPY q TO ? (FORMAT PARQUET)',[str(self.root/'q.parquet')]);c.execute('COPY f TO ? (FORMAT PARQUET)',[str(self.root/'f.parquet')]);c.close()
        self.collection=dict(phase=dict(role='train',lock_required=False),pins={},refs=dict(queries=['q.parquet'],features=['f.parquet']),
            plan=dict(collection_id='c'*64,execution_inputs=dict(source_path='source.duckdb'),
                identity=dict(shard_protocols=[dict(source=dict(start='2019-10-01T00:00:00Z',end='2019-11-01T00:00:00Z'))])))
        self.verify=patch('scripts.train_baselines.verify_collection',side_effect=lambda *args,**kwargs:deepcopy(self.collection))
        self.verify.start();self.addCleanup(self.verify.stop)

    def approve(self):
        import json
        plan,_=m.prepare_gate_plan(self.acceptance,self.spec_path)
        self.approval.write_text(json.dumps(dict(version=1,approved=True,scope=m.GATE_ROLE,
            run_id=plan['run_id'],fingerprints=plan['identity']['fingerprints'])))
        return plan

    def run_gate(self):
        return m.run_gate(self.acceptance,self.spec_path,gate_approval_path=self.approval)

    def reports(self):
        import json
        return [json.loads(p.read_text()) for p in (self.root/'artifacts/metadata-price').glob('*/report.json')]

    def test_actual_tiny_gate_exports_keys_reference_schema_and_cpu_no_labels_no_fits(self):
        plan=self.approve();report=self.run_gate()
        self.assertEqual(report['status'],'complete_produced_unreviewed')
        self.assertEqual(report['fit_attempt_count'],0);self.assertFalse(report['labels_loaded'])
        self.assertEqual(report['query_selection']['queries'],100)
        self.assertEqual([x['queries'] for x in report['query_selection']['by_day']],[50,50])
        self.assertEqual(report['matrix']['numeric_shape'],[100,15]);self.assertEqual(report['matrix']['nominal_shape'],[100,3])
        self.assertGreaterEqual(report['process_cpu_user_system_seconds'],0)
        self.assertTrue(all('process_cpu_user_system_seconds' in r for r in report['stages']))
        import json
        manifest=json.loads((self.root/'artifacts/metadata-price'/plan['run_id']/'run.json').read_text())
        self.assertEqual(manifest['outputs'],report['artifacts'])
        self.assertEqual(set(manifest['outputs']),{'queries','features','provenance','reference'})
        with self.assertRaises(FileExistsError):self.run_gate()
        self.assertEqual([r['status'] for r in self.reports()].count('complete_produced_unreviewed'),1)

    def test_round_robin_balanced13days_unequal_and_labels_not_loaded(self):
        c=duckdb.connect(':memory:');self.addCleanup(c.close)
        c.execute('CREATE TABLE mp_all_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)')
        c.executemany('INSERT INTO mp_all_queries VALUES (?,?,?)',[(f'{day}:{i}',day*100+i,T+timedelta(days=day)) for day in range(13) for i in range(20)])
        result=m.choose_gate_queries(c)
        self.assertEqual([r['queries'] for r in result['by_day']],[8]*9+[7]*4)
        first=result['query_key_sha256']
        c.execute('CREATE TABLE labels(query_id VARCHAR,target BIGINT)');c.execute("INSERT INTO labels VALUES ('0:1',999)")
        self.assertEqual(m.choose_gate_queries(c)['query_key_sha256'],first)
        c.execute('DELETE FROM mp_all_queries');c.executemany('INSERT INTO mp_all_queries VALUES (?,?,?)',[
            (f'{day}:{i}',day*100+i,T+timedelta(days=day)) for day,size in enumerate([1,3,120]) for i in range(size)])
        result=m.choose_gate_queries(c)
        self.assertEqual([r['queries'] for r in result['by_day']],[1,3,96])
        import hashlib
        import json
        ordered=[]
        for day,size in enumerate([1,3,120]):
            ids=sorted((f'{day}:{i}' for i in range(size)),key=lambda q:(hashlib.sha256(q.encode()).hexdigest(),q))
            ordered.extend((rank,day,q) for rank,q in enumerate(ids))
        expected=sorted(q for _,_,q in sorted(ordered)[:100])
        actual=[r[0] for r in c.execute('SELECT query_id FROM metadata_queries ORDER BY query_id').fetchall()]
        self.assertEqual(actual,expected)
        self.assertEqual(result['query_key_sha256'],hashlib.sha256(m.canonical_json(expected).encode()).hexdigest())

    def test_train_only_exact_approval_schema_and_actual_helper_pins(self):
        import json
        self.collection['phase']['role']='selection'
        with self.assertRaisesRegex(ValueError,'train'):m.prepare_gate_plan(self.acceptance,self.spec_path)
        self.collection['phase']['role']='train'
        for mode in ['missing','extra','digest','approved_type','version_type']:
            self.approve();approval=json.loads(self.approval.read_text())
            if mode=='missing':approval['fingerprints'].pop('uv.lock')
            elif mode=='extra':approval['fingerprints']['extra.py']='a'*64
            elif mode=='digest':approval['fingerprints']['uv.lock']='b'*64
            elif mode=='approved_type':approval['approved']=1
            else:approval['version']=True
            self.approval.write_text(json.dumps(approval))
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'approval'):self.run_gate()
            self.assertFalse(any((self.root/'artifacts/metadata-price').glob('*/features.parquet')))
        self.collection['pins']={'uv.lock':'0'*64}
        with self.assertRaisesRegex(ValueError,'Accepted'):m.prepare_gate_plan(self.acceptance,self.spec_path)

    def test_spec_snapshot_drift_and_body_change_refused_before_source(self):
        from unittest.mock import patch
        import json
        self.approve()
        body=deepcopy(m.SPEC);body['reference_hours']=24;self.spec_path.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError,'spec'):self.run_gate()
        self.spec_path.write_text(json.dumps(m.SPEC))
        original=m._json_snapshot
        def changed(path):
            result=original(path)
            if path.resolve()==self.spec_path.resolve():path.write_text(json.dumps(m.SPEC)+' ')
            return result
        with patch.object(m,'_json_snapshot',side_effect=changed),self.assertRaisesRegex(ValueError,'changed'):m.prepare_gate_plan(self.acceptance,self.spec_path)

    def test_failure_before_open_and_cpu_counter_failure_preserve_audit(self):
        from unittest.mock import patch
        self.approve()
        with patch('duckdb.connect',side_effect=OSError('open fault')),self.assertRaisesRegex(OSError,'open fault'):self.run_gate()
        self.assertEqual(self.reports()[-1]['status'],'failed')
        with patch.object(m,'_process_cpu_seconds',side_effect=OSError('CPU counter fault')),self.assertRaisesRegex(OSError,'CPU counter fault'):self.run_gate()
        failed=[r for r in self.reports() if r.get('cpu_measurement_error')]
        self.assertEqual(len(failed),1);self.assertEqual(failed[0]['status'],'failed');self.assertIsNone(failed[0]['process_cpu_user_system_seconds'])

    def test_terminal_pin_change_prevents_complete_and_preserves_partial_exports(self):
        from unittest.mock import patch
        self.approve();original=m.model_arrays
        def changed(*args,**kwargs):
            result=original(*args,**kwargs)
            (self.root/'uv.lock').write_text('changed during SQL')
            return result
        with patch.object(m,'model_arrays',side_effect=changed),self.assertRaisesRegex(ValueError,'changed during'):self.run_gate()
        report=self.reports()[0];self.assertEqual(report['status'],'failed')
        self.assertTrue((self.root/report['artifacts']['features']['path']).exists())

    def test_output_schema_reference_provenance_faults_and_pair_cap_before_allocation(self):
        from unittest.mock import patch
        self.approve();original=m.create_metadata_price_features
        def corrupted(con,*args,**kwargs):
            result=original(con,*args,**kwargs)
            con.execute('DELETE FROM metadata_price_reference')
            return result
        with patch.object(m,'create_metadata_price_features',side_effect=corrupted),self.assertRaisesRegex(ValueError,'membership'):self.run_gate()
        self.assertFalse(any((self.root/'artifacts/metadata-price').glob('*/features.parquet')))

    def test_pair_cap_before_snapshot_arrays_or_export(self):
        from unittest.mock import patch
        c=duckdb.connect(str(self.source))
        c.execute('''CREATE OR REPLACE TABLE expanded AS SELECT q.query_id,r.product_id::BIGINT product_id,
            10::BIGINT candidate_category_id,false candidate_category_ambiguous,false candidate_category_missing
            FROM q CROSS JOIN range(1,222) r(product_id)''')
        c.execute('COPY expanded TO ? (FORMAT PARQUET)',[str(self.root/'expanded.parquet')]);c.close()
        self.collection['refs']['features']=['expanded.parquet']
        self.approve()
        with patch.object(m,'model_arrays',side_effect=AssertionError('allocation should not run')),self.assertRaisesRegex(ValueError,'budget'):self.run_gate()
        self.assertFalse(any((self.root/'artifacts/metadata-price').glob('*/features.parquet')))

    def test_missing_provenance_column_rejected_before_model_arrays(self):
        from unittest.mock import patch
        self.approve();original=m.create_metadata_price_features
        def corrupted(con,*args,**kwargs):
            result=original(con,*args,**kwargs)
            con.execute('ALTER TABLE metadata_price_provenance DROP COLUMN latest_code')
            return result
        with patch.object(m,'create_metadata_price_features',side_effect=corrupted),self.assertRaisesRegex(ValueError,'schema'):self.run_gate()
        self.assertFalse(any((self.root/'artifacts/metadata-price').glob('*/features.parquet')))

    def test_timeout_before_preparation_persists_attempt_no_export(self):
        from unittest.mock import patch
        self.approve()
        with patch.object(m.RunDeadline,'check',side_effect=TimeoutError('deadline fault')),self.assertRaisesRegex(TimeoutError,'deadline fault'):self.run_gate()
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed');self.assertEqual(report['error_type'],'TimeoutError')
        self.assertFalse(any((self.root/'artifacts/metadata-price').glob('*/features.parquet')))

    def test_close_time_overrun_is_failed_audit_and_raises(self):
        from unittest.mock import patch
        self.approve();real_connect=duckdb.connect;real_clock=m.time.monotonic
        offset=[0.]
        class Connection:
            def __init__(self,con):self.con=con
            def __getattr__(self,name):return getattr(self.con,name)
            def close(self):
                self.con.close();offset[0]+=700
        with patch('duckdb.connect',side_effect=lambda *a,**kw:Connection(real_connect(*a,**kw))),patch.object(m.time,'monotonic',side_effect=lambda:real_clock()+offset[0]):
            with self.assertRaisesRegex(TimeoutError,'deadline'):self.run_gate()
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed');self.assertGreater(report['seconds'],700)
        self.assertEqual(report['error_type'],'TimeoutError');self.assertTrue(report['terminal_errors'])

    def test_close_rss_overrun_is_failed_audit_and_raises(self):
        from unittest.mock import patch
        self.approve();real_connect=duckdb.connect;real_rss=m.peak_rss_bytes
        closed=[False]
        class Connection:
            def __init__(self,con):self.con=con
            def __getattr__(self,name):return getattr(self.con,name)
            def close(self):
                self.con.close();closed[0]=True
        with patch('duckdb.connect',side_effect=lambda *a,**kw:Connection(real_connect(*a,**kw))),patch.object(m,'peak_rss_bytes',side_effect=lambda:8*2**30+1 if closed[0] else real_rss()):
            with self.assertRaisesRegex(MemoryError,'RSS'):self.run_gate()
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed');self.assertEqual(report['process_peak_rss_bytes'],8*2**30+1)
        self.assertEqual(report['error_type'],'MemoryError')

    def test_close_error_preserves_failed_audit_and_root_cause(self):
        from unittest.mock import patch
        self.approve();real_connect=duckdb.connect
        class Connection:
            def __init__(self,con):self.con=con
            def __getattr__(self,name):return getattr(self.con,name)
            def close(self):
                self.con.close();raise OSError('close fault')
        with patch('duckdb.connect',side_effect=lambda *a,**kw:Connection(real_connect(*a,**kw))),self.assertRaisesRegex(OSError,'close fault'):self.run_gate()
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed');self.assertEqual(report['error_type'],'OSError')


if __name__=='__main__':unittest.main()
