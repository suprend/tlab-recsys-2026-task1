"""Finite tiny018 CODE verification: invented events/fake scores; no actual inputs."""
import time
ENTRY=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(59,60))
import signal
signal.alarm(120)
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT=Path('/Users/mdpospelov/tlab-recsys-2026')
DRAFT=Path('/tmp/tlab-reproduce-development-slice-v1.py')
TMP=tempfile.TemporaryDirectory(prefix='tlab018-tiny-code-')
FIXTURE=Path(TMP.name)
(FIXTURE/'empty-pyc').mkdir()
sys.pycache_prefix=str(FIXTURE/'empty-pyc')
sys.path.insert(0,str(PROJECT))
import duckdb
import numpy as np
import pandas as pd
from scripts import anchor_pilot,candidate_pilot,manual_features,feature_programs,heldout_source,inference_data,heldout_predictions,protocol_manifest
adapter=ModuleType('proposal_adapter')
adapter.__file__=str(DRAFT)
sys.modules[adapter.__name__]=adapter
exec(compile(DRAFT.read_bytes(),str(DRAFT),'exec',dont_inherit=True),adapter.__dict__)
CORES=SimpleNamespace(anchors=anchor_pilot,retrieval=candidate_pilot,compiler=manual_features,
 programs=feature_programs,schema=heldout_source,inference=inference_data,
 predictions=heldout_predictions,protocol=protocol_manifest,np=np,pd=pd)
MODEL_CALLS=[]
STAGES=[]

def guard():
    usage=resource.getrusage(resource.RUSAGE_SELF)
    if usage.ru_utime+usage.ru_stime>=60 or time.monotonic()-ENTRY>=120:
        raise RuntimeError('Original tiny CODE verification lifetime exceeded')
    peak=usage.ru_maxrss*(1024 if sys.platform.startswith('linux') else 1)
    if peak>512*2**20:raise RuntimeError('Original tiny512MiB process peak exceeded')

def stage(name,operation):
    guard();start=time.monotonic()
    try:return operation()
    finally:STAGES.append(dict(name=name,wall_seconds=time.monotonic()-start));guard()

class FakeModel:
    def __init__(self,spec):
        self.spec=deepcopy(spec);self.tree_count_=300;self.feature_names_=list(spec['feature_names'])
    def get_cat_feature_indices(self):return []
    def get_text_feature_indices(self):return []
    def get_embedding_feature_indices(self):return []
    def get_all_params(self):return deepcopy(self.spec['effective_parameters'])
    def predict(self,x,**kwargs):
        MODEL_CALLS.append(dict(shape=x.shape,kwargs=kwargs,synthetic_fake_model=True))
        return np.nan_to_num(x,nan=0.).sum(axis=1,dtype=np.float64)

class TinyAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        guard()
        cls.base=json.loads((PROJECT/'configs/protocols/clock-48h.json').read_bytes())
        cls.registry=json.loads((PROJECT/'configs/features/manual-18.json').read_bytes())
        contract=json.loads((PROJECT/'configs/features/automation-pool.json').read_bytes())
        cls.pool=feature_programs.generate_pool(contract,cls.registry)
        cls.models=deepcopy(json.loads(Path('/tmp/tlab-development-source-to-score-model-source-bindings-proposal.json').read_bytes())['models'])
        for role,digit in [('B','0'),('W','1')]:cls.models[role]['model']=dict(path='synthetic/'+role+'.cbm',sha256=digit*64)
        cls.patchq=patch.object(adapter,'REQUIRED_QUERIES',2);cls.patchq.start()
        cls.patchn=patch.object(adapter,'MAX_ROWS',64);cls.patchn.start()
        cls.patchroot=patch.object(inference_data,'ROOT',FIXTURE);cls.patchroot.start()
        cls.config=adapter.one_day_protocol(cls.base)
        db=FIXTURE/'invented-events-only.duckdb'
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
        cls.con.execute('SET threads=2');cls.con.execute("SET memory_limit='64MB'");cls.con.execute("SET max_temp_directory_size='0B'")
        (FIXTURE/'out').mkdir()
        def export(name,sql):
            path=FIXTURE/'out'/adapter.OUTPUT_NAMES[name]
            if path.exists():raise FileExistsError(str(path))
            cls.con.execute('COPY ('+sql+') TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(path)])
            return path.relative_to(FIXTURE).as_posix()
        def load_model(ref):
            role=next(r for r in cls.models if cls.models[r]['model']==ref)
            return FakeModel(cls.models[role])
        cls.result=adapter.build_and_score(cls.con,config=cls.config,pool=cls.pool,models=cls.models,cores=CORES,
            load_model=load_model,export=export,check=guard,stage=stage)
        guard()

    @classmethod
    def tearDownClass(cls):
        cls.con.close();cls.patchroot.stop();cls.patchn.stop();cls.patchq.stop();guard()

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
        with self.assertRaises(duckdb.CatalogException):self.con.execute(missing)

    def test_explicit_B45_projection_handles_interleaved_chosen48(self):
        combined=[row[0] for row in self.con.execute('DESCRIBE manual_features').fetchall()]
        base=[row[0] for row in self.con.execute("DESCRIBE SELECT * FROM read_parquet(?)",[str(FIXTURE/self.result['outputs']['base_features'])]).fetchall()]
        extra=[row[0] for row in self.con.execute("DESCRIBE SELECT * FROM read_parquet(?)",[str(FIXTURE/self.result['outputs']['extra_features'])]).fetchall()]
        self.assertEqual(len(combined),48);self.assertEqual(len(base),45)
        self.assertNotEqual(combined[:45],base)
        self.assertEqual(extra,['query_id','product_id',*[n for n,t in adapter.EXTRAS]])
        self.assertEqual(self.con.execute('SELECT '+','.join(adapter.quote(n) for n,t in adapter.EXTRAS)+' FROM reproduction_extra').fetchall(),[(1,1,0)])

    def test_raw48_base_is_rejected_by_actual_inference_loader(self):
        wrong=FIXTURE/'out'/'wrong-combined48.parquet'
        self.con.execute('COPY manual_features TO ? (FORMAT PARQUET)',[str(wrong)])
        with self.assertRaisesRegex(ValueError,'Immutable B41 feature order differs'):
            inference_data.load_inference_data([self.result['outputs']['queries']],[wrong.relative_to(FIXTURE).as_posix()],
                expected_feature_names=self.models['B']['feature_names'],max_queries=2,max_rows=64,check=guard)

    def test_empty_C_query_exact_large_IDs_and_all_keyed_score_exports(self):
        q=self.con.execute('SELECT query_id,user_id,label_is_mature FROM read_parquet(?) ORDER BY query_id',[str(FIXTURE/self.result['outputs']['queries'])]).fetchall()
        self.assertEqual(len(q),2);self.assertEqual({row[1] for row in q},{self.u,self.u+1});self.assertTrue(all(row[2] for row in q))
        for role in ['B','W']:
            rows=self.con.execute('SELECT query_id,product_id,raw_score FROM read_parquet(?)',[str(FIXTURE/self.result['outputs'][role])]).fetchall()
            self.assertEqual(len(rows),1);self.assertEqual(rows[0][1],self.a);self.assertTrue(math_isfinite(rows[0][2]))
            diff=self.con.execute('''SELECT count(*) FROM((SELECT query_id,product_id FROM pilot_candidates EXCEPT ALL SELECT query_id,product_id FROM read_parquet(?))
                UNION ALL(SELECT query_id,product_id FROM read_parquet(?) EXCEPT ALL SELECT query_id,product_id FROM pilot_candidates))''',
                [str(FIXTURE/self.result['outputs'][role])]*2).fetchone()[0]
            self.assertEqual(diff,0)

    def test_exact_fixed_two_fake_prediction_calls_and_no_fit(self):
        self.assertEqual(len(MODEL_CALLS),2)
        self.assertEqual([r['shape'] for r in MODEL_CALLS],[(1,41),(1,44)])
        self.assertTrue(all(r['kwargs']==dict(prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2) for r in MODEL_CALLS))
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
        with patch.object(anchor_pilot,'create_queries',side_effect=lambda *a,**k:calls.append(True)):
            with self.assertRaisesRegex(ValueError,'One fixed Oct22 population required'):
                adapter.build_and_score(self.con,config=wrong,pool=self.pool,models=self.models,cores=CORES,
                    load_model=lambda r:None,export=lambda *a:None,check=guard,stage=stage)
            wrongmodels=deepcopy(self.models);wrongmodels['W']['feature_names'][-2:]=wrongmodels['W']['feature_names'][-2:][::-1]
            with self.assertRaisesRegex(ValueError,'Immutable B41'):
                adapter.build_and_score(self.con,config=self.config,pool=self.pool,models=wrongmodels,cores=CORES,
                    load_model=lambda r:None,export=lambda *a:None,check=guard,stage=stage)
        self.assertEqual(calls,[])


def math_isfinite(x):
    import math
    return math.isfinite(x)

if __name__=='__main__':
    result=None
    try:
        result=unittest.TextTestRunner(verbosity=2,stream=sys.stdout).run(unittest.defaultTestLoader.loadTestsFromTestCase(TinyAdapterTests))
    finally:
        usage=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
        peak=usage.ru_maxrss*(1024 if sys.platform.startswith('linux') else 1)
        receipt=dict(scope='bounded018_tiny_CODE_verification_only',tests_run=result.testsRun if result else None,
            success=result.wasSuccessful() if result else False,errors=len(result.errors) if result else None,
            failures=len(result.failures) if result else None,observed_wall_seconds=time.monotonic()-ENTRY,
            process_cpu_seconds=usage.ru_utime+usage.ru_stime,process_peak_rss_bytes=peak,
            children_cpu_seconds=children.ru_utime+children.ru_stime,children_peak_rss=children.ru_maxrss,
            limits=dict(cpu_seconds=60,wall_seconds=120,process_peak_rss_bytes=512*2**20,threads=2),
            invented_events=8,maximum_fixture_queries=2,maximum_fixture_candidates=1,
            native_ML_calls=0,fake_prediction_calls=len(MODEL_CALLS),fit_attempt_count=0,
            actual_data_models_opened=False,queryY_relations_created=False,
            stage_count=len(STAGES),fixture_directory=str(FIXTURE),unseen_exit_tail_measured=False)
        target=Path('/tmp/tlab-reproduce-development-slice-v1-author-tiny-test-receipt.json')
        with target.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
        print(json.dumps(receipt,sort_keys=True))
        if result is not None and result.wasSuccessful():guard()
    raise SystemExit(0 if result is not None and result.wasSuccessful() else 1)
