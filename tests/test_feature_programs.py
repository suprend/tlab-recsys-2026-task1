"""Tiny typed-program tests; real data, labels, Pools and fits are absent."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import duckdb

from scripts import feature_programs as p
from scripts.manual_features import create_manual_features,load_registry
from scripts.protocol_manifest import load_protocol

ROOT=Path(__file__).resolve().parents[1]
S=datetime(2019,10,1);T=datetime(2019,10,10)
# event_time,action,item,user,category.9 event rows+4Q+5C=18 inputrows.
EVENTS=[(T-timedelta(hours=1),'view',10,1,100),
        (T-timedelta(hours=2),'cart',10,1,100),(T-timedelta(hours=2),'cart',10,1,100),
        (T-timedelta(hours=3),'purchase',10,1,100),(T-timedelta(days=8),'cart',10,2,100),
        (T-timedelta(hours=2),'view',20,2,200),(T-timedelta(hours=25),'purchase',20,2,200),
        (T,'cart',20,1,None),(T+timedelta(hours=1),'purchase',20,1,None)]
QUERIES=[('U',1,T,True),('V',2,T,True),('emptyU',1,T+timedelta(days=1),True),('emptyV',2,T+timedelta(days=1),True)]
CANDIDATES=[('U',10),('U',20),('U',30),('V',10),('V',20)]
GOLD={
 'L01':[(1,2,1),(1,2,1),(1,2,1),(1,0,0),(1,0,0)],
 'L02':[(1,2,1),(0,0,0),(0,0,0),(0,0,0),(1,0,0)],
 'L05':[(1,1,1),(1,0,0),(0,0,0),(1,1,1),(1,0,0)],
 'L06':[(7200.,False,2),(None,True,0),(None,True,0),(691200.,False,2),(None,True,0)]}


def reference(events,program,user,item,anchor):
    # Deliberately independent row iteration; no compiler expression/counter.
    rows=[]
    for time,action,i,u,category in events:
        if not S<=time<anchor or action!=program['event_type']:continue
        if program['grain'] in {'user','pair'} and u!=user:continue
        if program['grain'] in {'item','pair'} and i!=item:continue
        if program['operator']!='recency_seconds' and time<anchor-timedelta(hours=program['window']):continue
        rows.append((time,i,u))
    if program['operator']=='count':return len(rows)
    if program['operator']=='count_distinct':
        j=1 if program['column']=='product_id' else 2
        return len({r[j] for r in rows if r[j] is not None})
    return (anchor-max(r[0] for r in rows)).total_seconds() if rows else None


class FeatureProgramsTests(unittest.TestCase):
    def setUp(self):
        self.contract=json.loads((ROOT/'configs/features/automation-pool.json').read_text())
        self.base=load_registry(ROOT/'configs/features/manual-18.json')
        self.pool=p.generate_pool(self.contract,self.base);self.allocation=p.allocate_slots(self.pool)
        self.config=load_protocol(ROOT/'configs/protocols/clock-48h.json')
        self.config['pilot']['end']='2019-10-12T00:00:00Z'
        self.config['query']['max_users_per_day']=2
        self.config['budget']['max_anchors']=8

    def bundle(self,bundle_id):
        return next(b for b in self.pool['identity']['bundles'] if b['bundle_id']==bundle_id)

    def run_registry(self,registry,events=EVENTS,queries=QUERIES,candidates=CANDIDATES):
        self.assertLessEqual(len(events)+len(queries)+len(candidates),32)
        con=duckdb.connect(':memory:')
        try:
            con.execute('SET threads=2')
            con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
            if events:con.executemany('INSERT INTO events VALUES (?,?,?,?,?)',events)
            con.execute('CREATE TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
            if queries:con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,?)',queries)
            con.execute('CREATE TABLE pilot_candidates(query_id VARCHAR,product_id BIGINT)')
            if candidates:con.executemany('INSERT INTO pilot_candidates VALUES (?,?)',candidates)
            outcome=create_manual_features(con,self.config,registry)
            schema=con.execute('DESCRIBE manual_features').fetchall()
            cursor=con.execute('SELECT * FROM manual_features ORDER BY query_id,product_id')
            columns=[x[0] for x in cursor.description]
            return outcome,{r[:2]:dict(zip(columns,r)) for r in cursor.fetchall()},dict((x[0],x[1]) for x in schema)
        finally:con.close()

    def test_schema_generates_eight_closures_without_data_or_sql(self):
        with patch.object(duckdb,'connect',side_effect=AssertionError('generation opened SQL')):
            pool=p.generate_pool(self.contract,self.base)
            self.assertEqual([b['bundle_id'] for b in pool['identity']['bundles']],[f'L{i:02}' for i in range(1,9)])
            self.assertEqual([len(b['programs']) for b in pool['identity']['bundles']],[3]*5+[2]*3)
            self.assertTrue(all(len(b['physical_delta'])==3 for b in pool['identity']['bundles']))
            self.assertEqual(len(pool['identity']['base_model_schema']),41)
            self.assertFalse(pool['identity']['execution_approved'])
        self.assertEqual(self.base,load_registry(ROOT/'configs/features/manual-18.json'))

    def test_frozen_rng_draws_and_collision_no_refill(self):
        slots=self.allocation['identity']['slots']
        self.assertEqual([s['bundle_id'] for s in slots],['L02','L06','L01','L05'])
        self.assertEqual([s['new_physical_columns'] for s in slots],[3]*4)
        self.assertTrue(all(s['fit_budget_slots_consumed']==1 and s['native_fits_started']==0 for s in slots))
        # Exercise the same collision law without changing declared seed/pool.
        with patch.object(p.random.Random,'choices',return_value=['L02','L02']):
            collided=p.allocate_slots(self.pool)
            self.assertEqual([s['status'] for s in collided['identity']['slots']][2:],['collision_consumed_no_refill']*2)
            with self.assertRaisesRegex(ValueError,'colliding'):
                p.registry_for_slot(self.pool,collided,'R1')
        self.assertFalse(self.allocation['identity']['execution_approved'])

    def test_unsupported_schema_policy_operator_and_binding_fail_closed(self):
        mutations=[lambda c:c['schema']['observed_actions'].remove('cart'),
                   lambda c:c['schema']['fields']['user_id'].update(role='numeric_measure'),
                   lambda c:c['context'].update(source_availability='unknown_ingestion'),
                   lambda c:c['grammar']['operators'].append('sum'),
                   lambda c:c['grammar'].update(windows_hours=[24.,168]),
                   lambda c:c['grammar']['action_count_bindings'][0].update(window=72),
                   lambda c:c['allocation'].update(random_seed=2027),
                   lambda c:c['allocation'].update(max_fits=True),
                   lambda c:c.update(extra='hidden')]
        for mutate in mutations:
            c=deepcopy(self.contract);mutate(c)
            with self.subTest(c=c),self.assertRaises(ValueError):p.generate_pool(c,self.base)

    def test_renamed_semantic_alias_and_tampered_pool_allocation_rejected(self):
        base=deepcopy(self.base);base['features'][1].update(name='renamed_user_cart',window=24)
        with self.assertRaisesRegex(ValueError,'aliases'):p.generate_pool(self.contract,base)
        changed=deepcopy(self.pool);changed['identity']['bundles'][0]['programs'][0]['window']=168
        with self.assertRaisesRegex(ValueError,'digest'):p.allocate_slots(changed)
        changed=deepcopy(self.allocation);changed['identity']['slots'][0]['bundle_id']='L03'
        with self.assertRaisesRegex(ValueError,'frozen law'):p.registry_for_slot(self.pool,changed,'I1')
        with self.assertRaisesRegex(ValueError,'Unknown'):p.registry_for_slot(self.pool,self.allocation,'extra')

    def test_selected_twelve_physical_columns_full_literal_gold_and_direct_oracle(self):
        _,baseline,base_schema=self.run_registry(self.base)
        self.assertEqual(len(baseline),5)
        seen=set()
        for slot in self.allocation['identity']['slots']:
            bundle=self.bundle(slot['bundle_id']);registry=p.registry_for_slot(self.pool,self.allocation,slot['slot'])
            outcome,actual,schema=self.run_registry(registry)
            delta={k:v for k,v in schema.items() if k not in base_schema}
            self.assertEqual(delta,{x['name']:x['dtype'] for x in bundle['physical_delta']})
            self.assertEqual(outcome['feature_rows'],5);seen.update(delta)
            programs=bundle['programs'];order=[f['name'] for f in programs]
            if slot['bundle_id']=='L06':order=[order[0],order[0]+'_missing',order[1]]
            self.assertEqual([tuple(actual[key][n] for n in order) for key in CANDIDATES],GOLD[slot['bundle_id']])
            for qid,item in CANDIDATES:
                user=1 if qid=='U' else 2
                for f in programs:
                    expected=reference(EVENTS,f,user,item,T)
                    self.assertEqual(actual[qid,item][f['name']],expected)
                    if f['operator']=='recency_seconds':self.assertIs(actual[qid,item][f['name']+'_missing'],expected is None)
        self.assertEqual(len(seen),12)

    def test_boundary_null_large_integer_and_unknown_category_independent_expected(self):
        extras=[(T-timedelta(hours=24),'view',10,1,None),
                (T-timedelta(hours=24,seconds=1),'view',10,1,None),
                (S-timedelta(seconds=1),'cart',30,1,None),
                (T-timedelta(minutes=30),'cart',10,None,None),
                (T-timedelta(minutes=20),'view',10,None,None),
                (T-timedelta(hours=4),'purchase',2**60+1,1,None),
                (T-timedelta(days=7),'cart',20,2,None)]
        events=EVENTS+extras
        for slot in self.allocation['identity']['slots']:
            b=self.bundle(slot['bundle_id']);_,actual,_=self.run_registry(b['registry'],events)
            for qid,item in CANDIDATES:
                for f in b['programs']:
                    self.assertEqual(actual[qid,item][f['name']],reference(events,f,1 if qid=='U' else 2,item,T))
            self.assertTrue(actual['U',10]['candidate_category_missing'])
            # New unconditional counts remain defined despite unknown category.
            self.assertTrue(all(actual['U',10][f['name']] is not None for f in b['programs']))

    def test_global_peers_future_suffix_permutation_and_old_recency(self):
        future=[(T,'cart',10,1,None),(T+timedelta(hours=2),'view',30,2,None)]
        for slot in self.allocation['identity']['slots']:
            b=self.bundle(slot['bundle_id']);_,old,_=self.run_registry(b['registry'])
            _,new,_=self.run_registry(b['registry'],list(reversed(EVENTS+future)))
            names=[x['name'] for x in b['physical_delta']]
            self.assertEqual({k:tuple(v[n] for n in names) for k,v in old.items()},
                             {k:tuple(v[n] for n in names) for k,v in new.items()})
        name=self.bundle('L06')['programs'][0]['name']
        _,rows,_=self.run_registry(self.bundle('L06')['registry'])
        self.assertEqual(rows['V',10][name],8*86400)

    def test_empty_candidates_and_zero_queries_preserve_typed_schema(self):
        registry=p.registry_for_slot(self.pool,self.allocation,'I1')
        outcome,rows,schema=self.run_registry(registry,candidates=[])
        self.assertEqual(outcome['feature_rows'],0);self.assertEqual(rows,{})
        self.assertEqual(len(outcome['daily_state']),2)
        outcome,rows,empty_schema=self.run_registry(registry,queries=[],candidates=[])
        self.assertEqual(outcome['feature_rows'],0);self.assertEqual(rows,{})
        self.assertEqual(schema,empty_schema)


if __name__=='__main__':unittest.main()
