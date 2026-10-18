"""Invented tiny custom-Q fixtures only; real reservation/DB never opened."""
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import duckdb
import numpy as np
import pandas as pd

from scripts import hm_auto_holdout as holdout
from scripts import hm_retrieval as frozen_retrieval


def customer(value):
    return hashlib.sha256(value.encode()).hexdigest()


class CustomCandidateTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)
        self.con.execute('SET threads=2')
        self.con.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR,price DOUBLE)')
        self.con.execute('''CREATE TABLE articles(article_id VARCHAR,product_code VARCHAR,
            product_type_no VARCHAR,product_type_name VARCHAR,colour_group_code VARCHAR,
            department_no VARCHAR,garment_group_no VARCHAR,index_code VARCHAR)''')
        self.users = [customer(name) for name in ('global','reserved','other')]
        global_user,reserved,other = self.users
        self.rows = [('2020-08-01',global_user,f'{i:010d}',1.) for i in range(140)]
        self.rows += [('2020-09-15',reserved,f'{i:010d}',2.) for i in range(125,140)]
        self.rows += [('2020-09-14',reserved,f'{i:010d}',2.) for i in range(110,125)]
        self.rows += [('2020-09-14',other,f'{i:010d}',3.) for i in range(5)]
        self.rows += [('2020-09-16',reserved,'9999999999',4.)]
        self.con.executemany('INSERT INTO transactions VALUES (?,?,?,?)',self.rows)
        self.con.executemany('INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)',
            [(f'{i:010d}',str(i//3),'1','Type','2','3','4','5') for i in range(140)])
        self.con.execute('CREATE TEMP TABLE hm_holdout_reserved(customer_id VARCHAR)')
        self.con.execute('INSERT INTO hm_holdout_reserved VALUES (?)',[reserved])

    def test_explicit_Q_matches_frozen_C0_without_hash_reselection(self):
        frozen_retrieval.create_candidates(self.con,'2020-09-16',3,2026)
        expected = self.con.execute('''SELECT customer_id,article_id,source,source_rank,candidate_rank
            FROM hm_r_candidates WHERE policy='C0-Q120' AND customer_id=? ORDER BY candidate_rank''',[self.users[1]]).fetchall()
        actual = holdout.create_reserved_candidates(self.con,expected_users=1).fetchall()
        self.assertEqual(actual,expected)
        self.assertEqual({row[0] for row in actual},{self.users[1]})
        self.assertEqual(len(actual),120)
        self.assertEqual(sum(row[2]=='recent' for row in actual),20)
        self.assertTrue(any(self.con.execute('SELECT buyers7 FROM hm_holdout_items WHERE article_id=?',[row[1]]).fetchone()[0]==0 for row in actual))
        self.assertNotIn('9999999999',{row[1] for row in actual})

    def test_independent_python_order_and_future_independence(self):
        first = holdout.create_reserved_candidates(self.con,expected_users=1).fetchall()
        cutoff = date(2020,9,16)
        history = [(date.fromisoformat(d),u,a) for d,u,a,_ in self.rows if cutoff-timedelta(days=90)<=date.fromisoformat(d)<cutoff]
        buyers = {a:{u for d,u,b in history if b==a and d>=cutoff-timedelta(days=7)} for _,_,a in history}
        global_order = sorted(buyers,key=lambda a:(-len(buyers[a]),a))
        latest = {}
        for day,user,article in history:
            if user==self.users[1]:latest[article]=max(latest.get(article,day),day)
        recent = sorted(latest,key=lambda a:(-latest[a].toordinal(),a))[:20]
        expected = recent+[a for a in global_order[:200] if a not in recent][:120-len(recent)]
        self.assertEqual([row[1] for row in first],expected)
        self.con.execute('DELETE FROM transactions WHERE t_dat>=?::DATE', ['2020-09-16'])
        self.con.executemany('INSERT INTO transactions VALUES (?,?,?,?)',
            [('2020-09-16',self.users[1],f'{i:010d}',99.) for i in range(140)])
        # New connection avoids reusing producer-owned TEMP tables.
        other = duckdb.connect()
        try:
            other.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR,price DOUBLE)')
            other.executemany('INSERT INTO transactions VALUES (?,?,?,?)',self.con.execute('SELECT * FROM transactions').fetchall())
            other.execute('CREATE TEMP TABLE hm_holdout_reserved(customer_id VARCHAR)')
            other.execute('INSERT INTO hm_holdout_reserved VALUES (?)',[self.users[1]])
            self.assertEqual(holdout.create_reserved_candidates(other,expected_users=1).fetchall(),first)
        finally:other.close()

    def test_duplicate_or_future_only_customer_is_rejected(self):
        self.con.execute('INSERT INTO hm_holdout_reserved VALUES (?)',[self.users[1]])
        with self.assertRaisesRegex(ValueError,'unique'):holdout.create_reserved_candidates(self.con,expected_users=2)
        self.con.execute('DELETE FROM hm_holdout_reserved')
        self.con.execute('INSERT INTO hm_holdout_reserved VALUES (?)',[customer('future-only')])
        self.con.execute("INSERT INTO transactions VALUES ('2020-09-16',?,'0000000001',1.)",[customer('future-only')])
        with self.assertRaisesRegex(ValueError,'pre-cutoff'):holdout.create_reserved_candidates(self.con,expected_users=1)

    def test_history_left_boundary_and_feature_engine_have_no_outcomes(self):
        from scripts.hm_feature_engine import build_features
        self.con.executemany('INSERT INTO transactions VALUES (?,?,?,?)',
            [('2020-06-18',self.users[2],'0000000200',2.),
             ('2020-06-17',self.users[2],'0000000201',3.)])
        holdout.create_reserved_candidates(self.con,expected_users=1)
        articles = {row[0] for row in self.con.execute('SELECT article_id FROM hm_holdout_items').fetchall()}
        self.assertIn('0000000200',articles)
        self.assertNotIn('0000000201',articles)
        built = build_features(self.con,'2020-09-16')
        self.assertEqual(len(built.frame),120)
        self.assertEqual(set(built.frame.customer_id),{self.users[1]})
        self.assertNotIn('label',built.frame.columns)
        self.assertNotIn('9999999999',set(built.frame.article_id))

    def test_empty_future_queries_and_full_distinct_half_open_Y_are_preserved(self):
        from scripts.hm_feature_engine import build_features
        self.con.execute('INSERT INTO hm_holdout_reserved VALUES (?)',[self.users[2]])
        self.con.executemany('INSERT INTO transactions VALUES (?,?,?,?)',
            [('2020-09-16',self.users[1],'9999999999',1.),
             ('2020-09-23',self.users[1],'0000000139',1.)])
        holdout.create_reserved_candidates(self.con,expected_users=2)
        built=build_features(self.con,'2020-09-16')
        self.con.register('_hm_holdout_feature_frame',built.frame)
        holdout.attach_outcomes(self.con)
        self.assertEqual(self.con.execute('SELECT customer_id,article_id FROM hm_exp_targets').fetchall(),
                         [(self.users[1],'9999999999')])
        self.assertEqual(self.con.execute('SELECT count(DISTINCT customer_id),count(*),count(*) FILTER(WHERE label) FROM hm_exp_frame').fetchone(),
                         (2,240,0))


class LockedFlowTests(unittest.TestCase):
    """Gate stubs authorize only invented fixtures; no real GPU/native models."""
    def setUp(self):
        CustomCandidateTests.setUp(self)
        temp=tempfile.TemporaryDirectory(prefix='hm-customer-fixture-',dir='D:/')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        rootpatch=patch.object(holdout,'ROOT',self.root);rootpatch.start();self.addCleanup(rootpatch.stop)
        source=self.root/'scripts/hm_auto_holdout.py';source.parent.mkdir()
        source.write_bytes(Path(holdout.__file__).read_bytes())
        self.con.execute("INSERT INTO transactions VALUES ('2020-09-16',?,'0000000139',1.)",[self.users[1]])
        self.dbpath=self.root/'fixture.duckdb'
        disk=duckdb.connect(str(self.dbpath))
        disk.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR,price DOUBLE)')
        disk.executemany('INSERT INTO transactions VALUES (?,?,?,?)',self.con.execute('SELECT * FROM transactions').fetchall())
        disk.execute('''CREATE TABLE articles(article_id VARCHAR,product_code VARCHAR,product_type_no VARCHAR,
            product_type_name VARCHAR,colour_group_code VARCHAR,department_no VARCHAR,garment_group_no VARCHAR,index_code VARCHAR)''')
        disk.executemany('INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)',self.con.execute('SELECT * FROM articles').fetchall())
        disk.close()
        holdout.create_reserved_candidates(self.con,expected_users=1)
        from scripts.hm_feature_engine import build_features
        contract=holdout.legacy.feature_contract(build_features(self.con,'2020-09-16'))
        self.reservation_dir=self.root/'artifacts/hm-auto-v2/reservation'
        self.reservation_dir.mkdir(parents=True)
        self.con.execute('CREATE TEMP TABLE fixture_reserved(customer_id VARCHAR,cohort_hash VARCHAR,reservation_rank BIGINT)')
        self.con.execute('INSERT INTO fixture_reserved VALUES (?,?,1)',[self.users[1],hashlib.sha256((self.users[1]+':'+holdout.SALT).encode()).hexdigest()])
        self.con.execute('COPY fixture_reserved TO ? (FORMAT PARQUET)',[str(self.reservation_dir/'reserved-users.parquet')])
        self.con.execute('CREATE TEMP TABLE fixture_excluded(customer_id VARCHAR)')
        self.con.execute('INSERT INTO fixture_excluded VALUES (?)',[self.users[0]])
        self.con.execute('COPY fixture_excluded TO ? (FORMAT PARQUET)',[str(self.reservation_dir/'excluded-users.parquet')])
        self.train_paths=[];trains=[];old=[]
        for anchor in ('2020-08-12','2020-08-19','2020-08-26','2020-09-02','2020-09-09','2020-09-16'):
            path=self.root/f'artifacts/hm-campaign/collections/{anchor}-c0q120';path.mkdir(parents=True)
            self.con.execute('''CREATE OR REPLACE TEMP TABLE fixture_old AS SELECT ?::VARCHAR customer_id,
                sha256(? || ':2026') cohort_hash,120::INTEGER full_candidate_count''',[self.users[0],self.users[0]])
            self.con.execute('COPY fixture_old TO ? (FORMAT PARQUET)',[str(path/'users.parquet')])
            pin=self.pin(path/'users.parquet');old.append(dict(anchor=anchor,**pin,users=1,covered_by_reconstruction=True))
            if anchor=='2020-09-16':continue
            for name in ('frame.parquet','targets.parquet'):(path/name).write_bytes(b'opaque synthetic training stub')
            files={name:holdout.legacy.sha256_file(path/name) for name in ('frame.parquet','users.parquet','targets.parquet')}
            manifest=dict(format='hm-experiment-collection-v1',status='completed',anchor=anchor,cohort_seed=2026,
                policy='C0-Q120',features=contract,database=dict(sha256=holdout.legacy.sha256_file(self.dbpath),bytes=self.dbpath.stat().st_size),
                files=files,qcy_identity=hashlib.sha256((anchor+'QY').encode()).hexdigest(),candidate_identity=hashlib.sha256((anchor+'C').encode()).hexdigest())
            self.write(path/'manifest.json',manifest)
            self.train_paths.append(path)
            trains.append(dict(anchor=anchor,manifest=dict(path=(path/'manifest.json').relative_to(self.root).as_posix(),
                sha256=holdout.legacy.sha256_file(path/'manifest.json')),users=pin))
        def ids_sha(values):
            result=hashlib.sha256()
            for value in values:
                raw=value.encode();result.update(len(raw).to_bytes(4,'big'));result.update(raw)
            return result.hexdigest()
        reservation=dict(format='hm-auto-v2-customer-reservation-v1',status='completed',no_test_targets_or_features=True,
            counts_history_only=dict(excluded_users=1,actual_old_cohorts=old))
        self.write(self.reservation_dir/'manifest.json',reservation)
        relative='artifacts/hm-auto-v2/customer-test'
        parameters=holdout.legacy.fixed_parameters(500,8,2026,'GPU');parameters.pop('random_seed')
        data=dict(cohort=dict(kind='reserved_customer_holdout',anchor='2020-09-16',horizon_days=7,users=1,
            history_days=90,salt=holdout.SALT,policy='C0-Q120'),
            database=dict(path=self.dbpath.relative_to(self.root).as_posix(),sha256=holdout.legacy.sha256_file(self.dbpath),bytes=self.dbpath.stat().st_size),
            reservation=dict(manifest=dict(path=(self.reservation_dir/'manifest.json').relative_to(self.root).as_posix(),
                sha256=holdout.legacy.sha256_file(self.reservation_dir/'manifest.json')),
                files={name:self.pin(self.reservation_dir/name) for name in ('reserved-users.parquet','excluded-users.parquet')},
                reserved_ordered_ids_sha256=ids_sha([self.users[1]]),excluded_ordered_ids_sha256=ids_sha([self.users[0]])),
            train_collections=trains,features=dict(M=dict(numeric=['ui_tx90'],categorical=['product_type_no']),
                E=dict(numeric=['ui_tx90','auto_index_code_share28'],categorical=['product_type_no'])),
            hyperparameters=dict(M=parameters,E=dict(parameters,l2_leaf_reg=50)),
            training=dict(train_users=1,negative_sample=20,sampling_seed=2026,model_seeds=[2026,2027]),
            implementation=dict(code={'hm_auto_holdout.py':holdout.legacy.sha256_file(source)},runtime=holdout.legacy.runtime_identity()),
            outputs=dict(collection=relative+'/collection',fits=[relative+'/fits/'+arm+str(seed) for arm in ('M','E') for seed in (2026,2027)]))
        lock=self.root/'synthetic-contract.json';self.write(lock,data)
        self.plan=SimpleNamespace(data=data,path=lock,sha256=holdout.legacy.sha256_file(lock))
        self.collection=self.root/data['outputs']['collection']
        def load(path,sha):
            if Path(path)!=lock or sha!=self.plan.sha256:raise ValueError('Unapproved fixture lock')
            return self.plan
        def authorize_collect(plan,database,output):
            if plan is not self.plan or Path(database)!=self.dbpath or Path(output)!=self.collection:raise ValueError('Unapproved fixture collection')
        def authorize_fit(plan,arm,seed,train,collection,output):
            expected=self.root/f'{relative}/fits/{arm}{seed}'
            if (plan is not self.plan or arm not in ('M','E') or seed not in (2026,2027) or train!=self.train_paths
                    or collection!=self.collection or Path(output)!=expected):raise ValueError('Unapproved fixture fit')
            return dict(features=data['features'][arm],hyperparameters=dict(data['hyperparameters'][arm],random_seed=seed),
                        fit_index=(0 if arm=='M' else 2)+(seed-2026))
        self.gate=SimpleNamespace(load_lock=load,authorize_collect=authorize_collect,authorize_fit=authorize_fit)
        gatepatch=patch.object(holdout,'gate_module',return_value=self.gate);gatepatch.start();self.addCleanup(gatepatch.stop)

    @staticmethod
    def write(path,value):
        Path(path).write_text(json.dumps(value,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

    def pin(self,path):
        return dict(path=path.relative_to(self.root).as_posix(),sha256=holdout.legacy.sha256_file(path),bytes=path.stat().st_size)

    def collect(self):
        return holdout.collect(self.dbpath,self.collection,self.plan.path,self.plan.sha256,wall_seconds=30)

    def test_collection_and_custom_loader_keep_full_off_candidate_Y(self):
        report=self.collect()
        self.assertEqual(report['format'],holdout.COLLECTION_FORMAT)
        self.assertNotIn('cohort_seed',report)
        self.assertEqual(report['id_checks'],dict(reserved_users=1,excluded_overlap_users=0,training_overlap_users=0))
        self.assertEqual(report['population']['target_pairs'],2)
        self.assertEqual(report['population']['positive_rows'],1)
        self.assertLess(report['construction_order'].index('feature_engine'),report['construction_order'].index('fullY'))
        con=duckdb.connect()
        try:
            frame,targets,summary=holdout.load_holdout(con,self.collection,report,['ui_tx90','product_type_no'],self.plan,holdout.deadline_for(30))
            self.assertEqual(len(frame),120)
            self.assertEqual(targets[self.users[1]],{'0000000139','9999999999'})
            self.assertEqual(summary['target_pairs'],2)
            score=np.arange(120,dtype=float)
            numbers,cats=holdout.model_arrays(frame,['ui_tx90'],['product_type_no'])
            collection=holdout.legacy.pilot.Collection(numbers,cats,frame.label.to_numpy(),frame.query_weight.to_numpy(),
                frame.customer_id.to_numpy(),frame.article_id.to_numpy(),targets,summary)
            self.assertEqual(holdout.legacy.pilot.rank_collection(collection,scores=score)['map_at_12_conditional'],.5)
        finally:con.close()
        with self.assertRaises(FileExistsError):self.collect()

    def test_wrong_lock_blocks_before_output_and_candidate_access(self):
        with patch.object(holdout,'new_output',side_effect=AssertionError('must not create output')):
            with self.assertRaisesRegex(ValueError,'Unapproved fixture lock'):
                holdout.collect(self.dbpath,self.collection,self.plan.path,'0'*64)
            with self.assertRaisesRegex(ValueError,'Unapproved fixture lock'):
                holdout.fit('M',2026,self.train_paths,self.collection,self.root/'unused',self.plan.path,'0'*64)
        self.assertFalse(self.collection.exists())

    def test_reserved_overlap_rejected_before_any_feature_or_target_creation(self):
        path=self.reservation_dir/'excluded-users.parquet'
        self.con.execute('INSERT INTO fixture_excluded VALUES (?)',[self.users[1]])
        self.con.execute('COPY fixture_excluded TO ? (FORMAT PARQUET)',[str(path)])
        self.plan.data['reservation']['files']['excluded-users.parquet']=self.pin(path)
        # Even before outcome access, the pinned exclusion cardinality is now wrong.
        with self.assertRaisesRegex(ValueError,'Excluded customer IDs differ'):
            self.collect()
        self.assertFalse((self.collection/'targets.parquet').exists())
        self.assertEqual(json.loads((self.collection/'manifest.json').read_text())['status'],'failed')

    def test_custom_loader_refuses_bad_Q_and_cache_bytes(self):
        report=self.collect()
        path=self.collection/'users.parquet'
        self.con.execute('CREATE TEMP TABLE wrong_cached_users AS SELECT * FROM read_parquet(?)',[str(path)])
        self.con.execute("UPDATE wrong_cached_users SET cohort_hash='wrong'")
        self.con.execute('COPY wrong_cached_users TO ? (FORMAT PARQUET)',[str(path)])
        with self.assertRaisesRegex(ValueError,'cache bytes'):
            holdout.read_holdout_manifest(self.collection,self.plan,holdout.deadline_for(30))
        report['files']['users.parquet']=holdout.legacy.sha256_file(path)
        report['qcy_identity']=holdout.legacy.canonical_digest({name:report['files'][name] for name in ('users.parquet','targets.parquet')})
        con=duckdb.connect()
        try:
            with self.assertRaisesRegex(ValueError,'explicit reserved Q'):
                holdout.load_holdout(con,self.collection,report,['ui_tx90'],self.plan,holdout.deadline_for(30))
        finally:con.close()

    def fake_training(self,con,path,manifest,names,train_users,negative_sample):
        frame=pd.DataFrame(dict(customer_id=[self.users[0]]*2,article_id=['0000000000','0000000001'],
            label=[True,False],query_weight=[.5,.5],full_candidate_count=[2,2],fit_weight=[.5,.5],
            ui_tx90=[1.,2.],auto_index_code_share28=[.25,.5],product_type_no=['1','1']))
        return frame,{},dict(anchor=manifest['anchor'],selected_queries=1,fit_rows=2)

    def fit_fake(self,arm='M',seed=2026,trees=500):
        class FakeModel:
            def __init__(self,**params):self.params=params;self.tree_count_=trees
            def fit(self,pool):
                if len(np.unique(pool.labels))!=2:raise AssertionError('two training classes required')
            def get_all_params(self):return self.params
            def save_model(self,path):Path(path).write_bytes(b'synthetic nonnative model fixture')
            def predict_proba(self,pool,thread_count):
                if thread_count!=4:raise AssertionError('prediction threads differ')
                scores=np.linspace(.01,.99,pool.rows)
                return np.column_stack((1-scores,scores))
        def fake_pool(numbers,cats,numeric,categorical,labels=None,weights=None):
            return SimpleNamespace(rows=len(numbers),labels=labels,weights=weights)
        output=self.root/f'artifacts/hm-auto-v2/customer-test/fits/{arm}{seed}'
        with patch.object(holdout,'load_part',side_effect=self.fake_training),patch.object(holdout,'model_class',return_value=FakeModel),\
             patch.object(holdout,'model_pool',side_effect=fake_pool):
            return holdout.fit(arm,seed,self.train_paths,self.collection,output,self.plan.path,self.plan.sha256,wall_seconds=30)

    def test_four_fit_recipes_and_extended_identity_with_real_tiny_validation(self):
        self.collect()
        identities=[]
        for arm,seed in [('M',2026),('M',2027),('E',2026),('E',2027)]:
            report=self.fit_fake(arm,seed)
            self.assertEqual(report['format'],holdout.FIT_FORMAT)
            self.assertEqual(report['actual_trees'],500)
            self.assertEqual(report['hyperparameters']['l2_leaf_reg'],10 if arm=='M' else 50)
            self.assertEqual(report['hyperparameters']['random_seed'],seed)
            self.assertEqual(report['validation_metrics']['map_at_12_conditional'],.5)
            self.assertEqual(report['validation_population']['target_pairs'],2)
            self.assertEqual(report['fit_identity'],holdout.fit_identity(report))
            from scripts import hm_auto_holdout_lock as gate
            self.assertEqual(report['fit_identity'],gate.fit_identity(report))
            identities.append(report['fit_identity'])
        self.assertEqual(len(set(identities)),4)

    def test_incomplete_native_fit_and_budget_fail_closed(self):
        self.collect()
        with self.assertRaisesRegex(ValueError,'complete500'):
            self.fit_fake(trees=499)
        path=self.root/'artifacts/hm-auto-v2/customer-test/fits/M2026/report.json'
        self.assertEqual(json.loads(path.read_text())['status'],'failed')
        self.assertFalse((path.parent/'predictions-top12.parquet').exists())
        for seconds in (True,0,1801,float('nan')):
            with self.assertRaises(ValueError):holdout.deadline_for(seconds)

    def test_bounded_strict_metadata_parser(self):
        path=self.root/'bad-json.json'
        for text in ('{"a":1,"a":2}','{"a":NaN}','{"a":1e999}'):
            path.write_text(text,encoding='utf-8')
            with self.assertRaises(ValueError):holdout.read_json(path)


if __name__=='__main__':
    unittest.main()
