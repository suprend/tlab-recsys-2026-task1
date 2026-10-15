"""Portable tiny SQL/core regressions; no actual inputs, models or runtime grants."""
import ast
from copy import deepcopy
import json
import math
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import reproduce_development_slice as adapter

PROJECT=Path(__file__).resolve().parents[1]


class FakeModel:
    def __init__(self,spec,np,calls):
        self.spec=deepcopy(spec);self.tree_count_=300;self.feature_names_=list(spec['feature_names'])
        self.np=np;self.calls=calls
    def get_cat_feature_indices(self):return []
    def get_text_feature_indices(self):return []
    def get_embedding_feature_indices(self):return []
    def get_all_params(self):return deepcopy(self.spec['effective_parameters'])
    def predict(self,x,**kwargs):
        self.calls.append(dict(shape=x.shape,kwargs=kwargs,synthetic_fake_model=True))
        return self.np.nan_to_num(x,nan=0.).sum(axis=1,dtype=self.np.float64)


class ReproduceDevelopmentSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory(prefix='reproduce-development-slice-')
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.root=Path(cls.fixture.name)
        cls.model_calls=[]
        cls.stages=[]
        from scripts import anchor_pilot,candidate_pilot,manual_features,feature_programs,heldout_source,inference_data,heldout_predictions,protocol_manifest
        import duckdb
        import numpy as np
        import pandas as pd
        cls.duckdb=duckdb
        cls.inference=inference_data
        cls.anchors=anchor_pilot
        cls.cores=SimpleNamespace(anchors=anchor_pilot,retrieval=candidate_pilot,compiler=manual_features,programs=feature_programs,schema=heldout_source,inference=inference_data,predictions=heldout_predictions,protocol=protocol_manifest,np=np,pd=pd)
        cls.base=json.loads((PROJECT/'configs/protocols/clock-48h.json').read_bytes())
        cls.registry=json.loads((PROJECT/'configs/features/manual-18.json').read_bytes())
        contract=json.loads((PROJECT/'configs/features/automation-pool.json').read_bytes())
        cls.pool=feature_programs.generate_pool(contract,cls.registry)
        params=dict(loss_function='Logloss',iterations=300,depth=6,l2_leaf_reg=30,task_type='CPU',random_seed=2026,
            boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,
            leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False,
            border_count=254,nan_mode='Min',rsm=1,learning_rate=struct.unpack('!f',struct.pack('!f',.05))[0])
        base_names=[name for name,dtype in feature_programs._model_schema(cls.registry)]
        selected=feature_programs.allocate_slots(cls.pool)
        chosen=next(row['bundle_id'] for row in selected['identity']['slots'] if row['slot']=='R2')
        chosen_names=next(row['model_feature_order'] for row in cls.pool['identity']['bundles'] if row['bundle_id']==chosen)
        cls.models={role:dict(model=dict(path='synthetic/'+role+'.cbm',sha256=digit*64),feature_names=list(names),
            trained_iterations=300,scoring_prefix=300,population=26000,effective_parameters=deepcopy(params))
            for role,digit,names in [('B','0',base_names),('W','1',chosen_names)]}
        cls.patchq=patch.object(adapter,'REQUIRED_QUERIES',2);cls.patchq.start();cls.addClassCleanup(cls.patchq.stop)
        cls.patchn=patch.object(adapter,'MAX_ROWS',64);cls.patchn.start();cls.addClassCleanup(cls.patchn.stop)
        cls.patchroot=patch.object(inference_data,'ROOT',cls.root);cls.patchroot.start();cls.addClassCleanup(cls.patchroot.stop)
        cls.config=adapter.one_day_protocol(cls.base)
        db=cls.root/'invented-events-only.duckdb'
        con=duckdb.connect(str(db))
        con.execute('SET threads=2');con.execute("SET memory_limit='64MB'");con.execute("SET max_temp_directory_size='0B'")
        con.execute('''CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,category_id BIGINT,
            category_code VARCHAR,brand VARCHAR,price DECIMAL(12,2),user_id BIGINT,user_session VARCHAR)''')
        u=2**60+1;a=2**60+11;b=2**60+12
        cls.u=u;cls.a=a
        cls.rows=[('2019-10-01 12:00:00','view',a,9,'category.path','brand','1.00',u,'s'),
          ('2019-10-20 12:00:00','view',a,9,'category.path','brand','1.00',u,'s'),
          ('2019-10-21 11:00:00','view',a,9,'category.path','brand','1.00',u,'s'),
          ('2019-10-21 11:00:00','view',a,9,'category.path','brand','1.00',u,'s'),
          ('2019-10-21 12:00:00','cart',a,9,'category.path','brand','1.00',u,'s'),
          ('2019-10-21 13:00:00','view',None,None,None,None,None,u+1,'empty-item'),
          ('2019-10-22 00:00:00','purchase',b,9,'category.path','brand','2.00',u+1,'future-anchor'),
          ('2019-10-25 00:00:00','purchase',b,9,'category.path','brand','2.00',u,'reserved-raw-suffix')]
        con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',cls.rows)
        con.close()
        cls.con=duckdb.connect(str(db),read_only=True)
        cls.addClassCleanup(cls.con.close)
        cls.con.execute('SET threads=2');cls.con.execute("SET memory_limit='64MB'");cls.con.execute("SET max_temp_directory_size='0B'")
        (cls.root/'out').mkdir()
        def export(name,sql):
            path=cls.root/'out'/adapter.OUTPUT_NAMES[name]
            if path.exists():raise FileExistsError(str(path))
            cls.con.execute('COPY ('+sql+') TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(path)])
            return path.relative_to(cls.root).as_posix()
        def load_model(ref):
            role=next(r for r in cls.models if cls.models[r]['model']==ref)
            return FakeModel(cls.models[role],np,cls.model_calls)
        cls.result=adapter.build_and_score(cls.con,config=cls.config,pool=cls.pool,models=cls.models,cores=cls.cores,
            load_model=load_model,export=export,check=lambda:None,stage=cls.stage)

    @classmethod
    def stage(cls,name,operation):
        cls.stages.append(name)
        return operation()

    def test_typed9_events_only_input_completes_without_ingest_metadata_or_Y(self):
        self.assertEqual(self.con.execute('SELECT count(*) FROM events').fetchone()[0],8)
        self.assertEqual(len(self.con.execute('DESCRIBE events').fetchall()),9)
        self.assertEqual(self.result['query_count'],2)
        self.assertEqual(self.result['candidate_count'],1)
        names={row[0] for row in self.con.execute('SHOW TABLES').fetchall()}
        self.assertFalse(names&{'ingest_metadata','pilot_labels','pilot_target_windows'})
        self.assertEqual(self.result['fit_attempt_count'],0)
        self.assertEqual(self.result['metric_looks'],0)
        self.assertFalse(self.result['query_target_relation_created'])
        self.assertFalse(self.result['source_acceptance_issued'])

    def test_original_wrapper_metadata_assumption_is_real_consumer_failure(self):
        raw=(PROJECT/'scripts/anchor_pilot.py').read_bytes()
        run=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='run')
        sqls=[n.args[0].value for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
              and n.func.attr=='execute' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str)]
        missing=next(sql for sql in sqls if 'FROM ingest_metadata' in sql)
        with self.assertRaises(self.duckdb.CatalogException):self.con.execute(missing)

    def test_explicit_B45_projection_handles_interleaved_chosen48(self):
        combined=[row[0] for row in self.con.execute('DESCRIBE manual_features').fetchall()]
        base=[row[0] for row in self.con.execute("DESCRIBE SELECT * FROM read_parquet(?)",[str(self.root/self.result['outputs']['base_features'])]).fetchall()]
        extra=[row[0] for row in self.con.execute("DESCRIBE SELECT * FROM read_parquet(?)",[str(self.root/self.result['outputs']['extra_features'])]).fetchall()]
        self.assertEqual(len(combined),48);self.assertEqual(len(base),45)
        self.assertNotEqual(combined[:45],base)
        self.assertEqual(extra,['query_id','product_id',*[n for n,t in adapter.EXTRAS]])
        self.assertEqual(self.con.execute('SELECT '+','.join(adapter.quote(n) for n,t in adapter.EXTRAS)+' FROM reproduction_extra').fetchall(),[(1,1,0)])

    def test_raw48_base_is_rejected_by_actual_inference_loader(self):
        wrong=self.root/'out'/'wrong-combined48.parquet'
        self.con.execute('COPY manual_features TO ? (FORMAT PARQUET)',[str(wrong)])
        with self.assertRaisesRegex(ValueError,'Immutable B41 feature order differs'):
            self.inference.load_inference_data([self.result['outputs']['queries']],[wrong.relative_to(self.root).as_posix()],
                expected_feature_names=self.models['B']['feature_names'],max_queries=2,max_rows=64,check=lambda:None)

    def test_empty_C_query_exact_large_IDs_and_all_keyed_score_exports(self):
        q=self.con.execute('SELECT query_id,user_id,label_is_mature FROM read_parquet(?) ORDER BY query_id',[str(self.root/self.result['outputs']['queries'])]).fetchall()
        self.assertEqual(len(q),2);self.assertEqual({row[1] for row in q},{self.u,self.u+1});self.assertTrue(all(row[2] for row in q))
        for role in ['B','W']:
            rows=self.con.execute('SELECT query_id,product_id,raw_score FROM read_parquet(?)',[str(self.root/self.result['outputs'][role])]).fetchall()
            self.assertEqual(len(rows),1);self.assertEqual(rows[0][1],self.a);self.assertTrue(math_isfinite(rows[0][2]))
            diff=self.con.execute('''SELECT count(*) FROM((SELECT query_id,product_id FROM pilot_candidates EXCEPT ALL SELECT query_id,product_id FROM read_parquet(?))
                UNION ALL(SELECT query_id,product_id FROM read_parquet(?) EXCEPT ALL SELECT query_id,product_id FROM pilot_candidates))''',
                [str(self.root/self.result['outputs'][role])]*2).fetchone()[0]
            self.assertEqual(diff,0)

    def test_exact_fixed_two_fake_prediction_calls_and_no_fit(self):
        self.assertEqual(len(self.model_calls),2)
        self.assertEqual([r['shape'] for r in self.model_calls],[(1,41),(1,44)])
        self.assertTrue(all(r['kwargs']==dict(prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2) for r in self.model_calls))
        self.assertEqual(self.result['native_prediction_calls'],2)

    def test_full_original_global_groups_must_be_rekeyed_before_day_filter(self):
        qids=['a_23','b_22','c_23','d_22']
        actual=adapter.rekey_reference_scores(qids,[0,1,3],[8,9,10],[.1,.2,.3],['b_22','d_22'])
        self.assertEqual(actual,[('b_22',9,.2),('d_22',10,.3)])
        wrong=list(zip(['b_22','d_22'],[8,9],[.1,.2]))
        self.assertNotEqual(actual,wrong)

    def test_reference_transport_rejects_duplicates_nonfinite_and_boolean_keys(self):
        bad=[(['q'],[True],[8],[.1],['q']),(['q'],[0],[True],[.1],['q']),
             (['q'],[0],[8],[float('nan')],['q']),(['q'],[0,0],[8,8],[.1,.2],['q'])]
        for args in bad:
            with self.subTest(args=args),self.assertRaises(ValueError):adapter.rekey_reference_scores(*args)

    def test_non_oct22_or_wrong_selected_feature_order_stops_before_query_creation(self):
        wrong=deepcopy(self.config);wrong['pilot']=dict(start='2019-10-23T00:00:00Z',end='2019-10-24T00:00:00Z')
        calls=[]
        with patch.object(self.anchors,'create_queries',side_effect=lambda *a,**k:calls.append(True)):
            with self.assertRaisesRegex(ValueError,'One fixed Oct22 population required'):
                adapter.build_and_score(self.con,config=wrong,pool=self.pool,models=self.models,cores=self.cores,
                    load_model=lambda r:None,export=lambda *a:None,check=lambda:None,stage=self.stage)
            wrongmodels=deepcopy(self.models);wrongmodels['W']['feature_names'][-2:]=wrongmodels['W']['feature_names'][-2:][::-1]
            with self.assertRaisesRegex(ValueError,'Immutable B41'):
                adapter.build_and_score(self.con,config=self.config,pool=self.pool,models=wrongmodels,cores=self.cores,
                    load_model=lambda r:None,export=lambda *a:None,check=lambda:None,stage=self.stage)
        self.assertEqual(calls,[])


def math_isfinite(value):return math.isfinite(value)


if __name__=='__main__':unittest.main()
