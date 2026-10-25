"""Small independent witnesses for cached H&M experiment contracts; no real fits."""
from dataclasses import dataclass
from datetime import date
import itertools
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import duckdb
import numpy as np
import pandas as pd

from scripts import hm_experiment as experiment
from scripts.hm_baseline import Collection, cohort_key, rank_collection


def setUpModule():
    (experiment.ROOT/'artifacts').mkdir(exist_ok=True)   # outputs must lie under artifacts/, which is gitignored


def sample_frame():
    rows=[]
    for user,negatives,positives in [('p',24,1),('empty',30,0),('allpositive',0,3)]:
        count=negatives+positives
        for i in range(count):
            rows.append((user,str(i).zfill(10),i<positives,count,1/count))
    return pd.DataFrame(rows,columns=['customer_id','article_id','label','full_candidate_count','query_weight'])


@dataclass(frozen=True)
class Definition:
    name:str
    dtype:str
    operation:str='fixture'


class SamplingTests(unittest.TestCase):
    def test_all_queries_positives_denominator_and_determinism_survive(self):
        full=sample_frame()
        selected=experiment.sample_training_rows(full,'2020-08-12',20)
        self.assertEqual(set(selected.customer_id),set(full.customer_id))
        self.assertEqual(int(selected.label.sum()),int(full.label.sum()))
        self.assertEqual(selected.groupby('customer_id').size().to_dict(),{'allpositive':3,'empty':20,'p':21})
        expected={'p':25,'empty':30,'allpositive':3}
        for user,count in expected.items():
            self.assertTrue((selected.loc[selected.customer_id==user,'full_candidate_count']==count).all())
            self.assertAlmostEqual(selected.loc[selected.customer_id==user,'fit_weight'].sum(),1)
        pd.testing.assert_frame_equal(selected,experiment.sample_training_rows(full,'2020-08-12',20))
        pd.testing.assert_frame_equal(full,sample_frame())
        np.testing.assert_array_equal(selected.loc[selected.label,'inclusion_probability'],1)

    def test_inverse_probability_loss_identity_exhaustively(self):
        # One positive and21 negatives; enumerate all21 possible uniform20-subsets.
        nneg=21
        full=pd.DataFrame({'customer_id':['u']*22,'article_id':[f'{i:010d}' for i in range(22)],
                           'label':[True]+[False]*21,'full_candidate_count':[22]*22,
                           'query_weight':[1/22]*22})
        sampled=experiment.sample_training_rows(full,'2020-08-12',20)
        positive_weight=float(sampled.loc[sampled.label,'fit_weight'].iloc[0])
        negative_weight=float(sampled.loc[~sampled.label,'fit_weight'].iloc[0])
        self.assertAlmostEqual(positive_weight,1/22)
        self.assertAlmostEqual(negative_weight,(21/20)/22)
        losses=np.array([.7]+[i/10 for i in range(1,22)])
        expectations=[]
        for selected in itertools.combinations(range(1,22),20):
            expectations.append(positive_weight*losses[0]+negative_weight*sum(losses[list(selected)]))
        self.assertAlmostEqual(sum(expectations)/len(expectations),float(losses.mean()),places=12)

    def test_full_mode_and_reject_truncated_preexisting_candidate_denominator(self):
        full=sample_frame()
        chosen=experiment.sample_training_rows(full,'2020-08-12',0)
        self.assertEqual(len(chosen),len(full))
        np.testing.assert_allclose(chosen.fit_weight,chosen.query_weight)
        with self.assertRaisesRegex(ValueError,'Full candidate'):
            experiment.sample_training_rows(full.iloc[1:].copy(),'2020-08-12',20)
        with self.assertRaises(ValueError):
            experiment.sample_training_rows(full,'2020-08-12',5)

    def test_nested_cohort_uses_history_order_not_labels(self):
        users=pd.DataFrame({'customer_id':[str(i) for i in range(30)]})
        users['cohort_hash']=users.customer_id.map(lambda u:cohort_key(u,2026))
        five=experiment.nested_users(users,5)
        twenty=experiment.nested_users(users,20)
        self.assertEqual(list(five.customer_id),list(twenty.head(5).customer_id))
        with self.assertRaises(ValueError):
            experiment.nested_users(users,31)
        users.loc[0,'cohort_hash']='tampered'
        with self.assertRaisesRegex(ValueError,'ordering'):
            experiment.nested_users(users,5)


class ContractTests(unittest.TestCase):
    def test_gpu_recipe_is_explicit_and_requires_external_job_before_output_or_data(self):
        gpu=experiment.fixed_parameters(500,8,2026,'GPU')
        self.assertEqual(gpu,dict(iterations=500,depth=8,learning_rate=.05,l2_leaf_reg=10,
            loss_function='Logloss',random_seed=2026,thread_count=4,task_type='GPU',verbose=False,
            allow_writing_files=False,devices='0',gpu_ram_part=.5,pinned_memory_size='256mb',
            bootstrap_type='Bayesian',bagging_temperature=1,border_count=128,boosting_type='Plain'))
        self.assertNotIn('devices',experiment.fixed_parameters(500,8,2026))
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'not-created'
            for timeout in (None,0,-1,float('nan'),float('inf'),True):
                with self.subTest(timeout=timeout),patch.object(experiment,'new_private_output',side_effect=AssertionError('mkdir reached')):
                    with self.assertRaises(ValueError):
                        experiment.fit([Path(temp)/'missing-train'],Path(temp)/'missing-validation',output,
                            task_type='GPU',external_job_timeout_seconds=timeout)
                self.assertFalse(output.exists())

    def test_post_manual_runtime_model_sql_and_inference_share_four_thread_budget(self):
        self.assertEqual(experiment.fixed_parameters(500,8,2026)['thread_count'],4)
        self.assertEqual(experiment.runtime_identity()['threads'],4)
        statements=[]
        fake=SimpleNamespace(execute=lambda *args:statements.append(args))
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            with patch.dict('sys.modules',{'duckdb':SimpleNamespace(connect=lambda *args,**kwargs:fake)}):
                experiment.connection_for(output/'synthetic.db',output)
            self.assertIn(('SET threads=4',),statements)
            with patch.object(experiment.shutil,'disk_usage',return_value=SimpleNamespace(free=20*1024**3)):
                self.assertEqual(experiment.resource_preflight(output)['threads'],4)

    def test_collect_final_guard_occurs_before_output_or_source_access(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'must-not-exist'
            with self.assertRaisesRegex(ValueError,'2020-09-09'):
                experiment.collect(Path(temp)/'missing.db',out,'2020-09-10',10,'C0-Q120')
            self.assertFalse(out.exists())
        self.assertEqual(experiment.check_anchor('2020-09-09'),date(2020,9,9))
        for seconds in (0,-1,float('inf'),float('nan')):
            with self.assertRaises(ValueError):
                experiment.Deadline(seconds)

    def test_feature_registry_dataclasses_and_outcome_rejection(self):
        result=SimpleNamespace(frame=pd.DataFrame({'customer_id':['u'],'article_id':['a'],
                                                   'numeric':[1.0],'cat':['x']}),
                               registry=(Definition('numeric','float64'),Definition('cat','string','categorical')),
                               feature_sets={'manual_pilot':('numeric','cat'),'strong_manual':('numeric','cat')},
                               digest='fixture-registry')
        contract=experiment.feature_contract(result)
        self.assertEqual(experiment.choose_features({'features':contract}),(['numeric'],['cat']))
        result.frame['label']=True
        with self.assertRaisesRegex(ValueError,'Outcome'):
            experiment.feature_contract(result)

    def test_pool_construction_numeric_float32_and_categorical_strings(self):
        frame=pd.DataFrame({'x':[1.,2.],'c':['one',None]})
        numeric,cats=experiment.model_arrays(frame,['x'],['c'])
        self.assertEqual(numeric.dtype,np.dtype('float32'))
        self.assertEqual(cats.dtype,np.dtype('object'))
        pool=experiment.model_pool(numeric,cats,['x'],['c'],np.array([1,0]),np.array([.5,.5]))
        self.assertEqual(pool.num_row(),2)
        self.assertEqual(pool.get_cat_feature_indices(),[1])
        self.assertEqual(pool.get_feature_names(),['x','c'])

    def test_full_truth_and_empty_queries_survive_metrics_adapter(self):
        c=Collection(np.zeros((3,1),dtype=np.float32),np.empty((3,0),dtype=object),
                     np.array([1,0,0]),np.array([.5,.5,1]),np.array(['positive','positive','empty']),
                     np.array(['in','other','x']),{'positive':{'in','missing-from-C'},'empty':set()}, {})
        metrics=rank_collection(c,scores=np.array([.9,.1,.5]))
        self.assertEqual(metrics['positive_queries'],1)
        self.assertEqual(metrics['queries'],2)
        self.assertEqual(metrics['map_at_12_conditional'],.5)
        self.assertEqual(metrics['map_at_12_all_queries_empty_zero'],.25)
        self.assertEqual(metrics['candidate_target_coverage_micro'],.5)


class CollectionFixtureTests(unittest.TestCase):
    def test_cached_parquet_full_truth_labels_no_purchase_and_collision(self):
        with tempfile.TemporaryDirectory(dir=experiment.ROOT/'artifacts') as temp:
            root=Path(temp)
            (root/'scripts').mkdir()
            for filename in ('hm_retrieval.py','hm_feature_engine.py','hm_baseline.py'):
                (root/'scripts'/filename).write_text('# synthetic hash witness\n',encoding='utf-8')
            database=root/'synthetic.duckdb'
            con=duckdb.connect(str(database))
            con.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR)')
            con.execute("INSERT INTO transactions VALUES ('2020-08-11','u1','0000000000'),('2020-08-11','u2','0000000001'),('2020-08-12','u1','0000000000'),('2020-08-13','u1','off-candidate'),('2020-08-19','u2','excluded-right-boundary')")
            con.close()
            before=experiment.sha256_file(database)
            def retrieval(c,anchor,users,seed):
                c.execute("CREATE TEMP TABLE hm_r_users AS SELECT unnest(['u1','u2']) customer_id")
                c.execute("""CREATE TEMP TABLE hm_r_candidates AS SELECT 'C0-Q120' AS policy,
                    u.customer_id,lpad(i::VARCHAR,10,'0') AS article_id,'global' AS source,
                    i+1 AS source_rank,i+1 AS candidate_rank FROM hm_r_users u CROSS JOIN range(120) r(i)""")
            def features(c,anchor,candidates_table):
                frame=c.execute('SELECT customer_id,article_id,1.0::DOUBLE x FROM hm_candidates ORDER BY customer_id,article_id').fetchdf()
                return SimpleNamespace(frame=frame,registry=(Definition('x','float64'),),
                    feature_sets={'manual_pilot':('x',),'strong_manual':('x',)},digest='fixed')
            modules={'scripts.hm_retrieval':SimpleNamespace(create_candidates=retrieval),
                     'scripts.hm_feature_engine':SimpleNamespace(build_features=features)}
            out=root/'artifacts'/'collection'
            with patch.object(experiment,'ROOT',root),patch.dict('sys.modules',modules):
                report=experiment.collect(database,out,'2020-08-12',2,'C0-Q120',30)
                self.assertEqual(report['status'],'completed')
                self.assertEqual(report['population']['target_pairs'],2)
                self.assertEqual(report['population']['positive_rows'],1)
                self.assertEqual(report['population']['selected_queries'],2)
                with self.assertRaises(FileExistsError):
                    experiment.collect(database,out,'2020-08-12',2,'C0-Q120',30)
            self.assertEqual(experiment.sha256_file(database),before)
            con=duckdb.connect(':memory:')
            try:
                manifest=experiment.read_manifest(out,experiment.Deadline(30))
                frame,targets,pop=experiment.load_part(con,out,manifest,['x'],negative_sample=20)
                self.assertEqual(targets,{'u1':{'0000000000','off-candidate'},'u2':set()})
                self.assertEqual(pop['selected_queries'],2)
                self.assertEqual(pop['full_candidate_rows'],240)
                self.assertEqual(len(frame),41)
                self.assertEqual(int(frame.label.sum()),1)
                self.assertTrue((frame.full_candidate_count==120).all())
                self.assertNotIn('off-candidate',set(frame.article_id))
            finally:
                con.close()
            with (out/'frame.parquet').open('ab') as stream:
                stream.write(b'tamper')
            with self.assertRaisesRegex(ValueError,'byte identity'):
                experiment.read_manifest(out,experiment.Deadline(30))

    def test_actual_retrieval_and_feature_engine_integrate_on_synthetic_db(self):
        with tempfile.TemporaryDirectory(dir=experiment.ROOT/'artifacts') as temp:
            root=Path(temp)
            database=root/'synthetic.duckdb'
            con=duckdb.connect(str(database))
            con.execute('''CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR,
                price DOUBLE,sales_channel_id VARCHAR)''')
            con.execute('''CREATE TABLE articles(article_id VARCHAR,product_code VARCHAR,
                product_type_no VARCHAR,product_type_name VARCHAR,colour_group_code VARCHAR,
                department_no VARCHAR,index_code VARCHAR,garment_group_no VARCHAR)''')
            con.execute("""INSERT INTO articles SELECT lpad(i::VARCHAR,10,'0'),(i//2)::VARCHAR,
                (i%2)::VARCHAR,'known',(i%3)::VARCHAR,'department','index','garment'
                FROM range(130) r(i)""")
            con.execute("""INSERT INTO transactions SELECT DATE '2020-08-11','u1',article_id,0.2,'2' FROM articles""")
            con.execute("""INSERT INTO transactions VALUES ('2020-08-11','u2','0000000001',0.3,'2'),
                ('2020-08-12','u1','0000000000',0.2,'2'),('2020-08-13','u1','9999999999',0.2,'2')""")
            con.close()
            report=experiment.collect(database,root/'collection','2020-08-12',2,'C0-Q120',30)
            self.assertEqual(report['status'],'completed')
            self.assertEqual(report['population']['candidate_rows'],240)
            self.assertEqual(report['population']['target_pairs'],2)
            self.assertEqual(len(report['features']['feature_sets']['strong_plus_generated']),87)
            con=duckdb.connect(':memory:')
            try:
                numeric,categorical=experiment.choose_features(report,'strong')
                frame,targets,summary=experiment.load_part(con,root/'collection',report,numeric+categorical)
                numbers,cats=experiment.model_arrays(frame,numeric,categorical)
                self.assertEqual(numbers.shape,(240,29))
                self.assertEqual(cats.shape,(240,5))
                self.assertEqual(targets,{'u1':{'0000000000','9999999999'},'u2':set()})
            finally:
                con.close()

    def test_insufficient_disk_fails_before_connection(self):
        with patch.object(experiment.shutil,'disk_usage',return_value=SimpleNamespace(free=1024)):
            with self.assertRaisesRegex(OSError,'10GiB'):
                experiment.resource_preflight(Path('.'))


if __name__=='__main__':
    unittest.main()
