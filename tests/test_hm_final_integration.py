"""Draft wiring witnesses only: two synthetic users, no real data/model fits.

The cohort limit is capped to the tiny fixture only inside the FakeML flow.
The strict lock continues to request the real frozen 20,000-user recipe.
"""
from copy import deepcopy
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import duckdb
import numpy as np
import pandas as pd

from scripts import hm_final_lock as gate
from tests import test_hm_final_lock as lock_fixtures

write = lock_fixtures.write

DRAFT = Path(__file__).resolve().parent
PROJECT = DRAFT.parents[2] if DRAFT.name == 'final-support-draft' else DRAFT.parent


def module(name):
    source = DRAFT/(name+'.py') if (DRAFT/(name+'.py')).exists() else PROJECT/'scripts'/(name+'.py')
    spec = importlib.util.spec_from_file_location('draft_' + name, source)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


experiment = module('hm_experiment')
audit = module('hm_result_audit')


class DraftIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = lock_fixtures.FinalLockTests('test_complete_four_fit_contract_and_seed_mean_contrasts')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.plan = self.fixture.plan
        self.patchers = []
        for target, attribute, value in ((experiment, 'ROOT', self.root), (audit, 'ROOT', self.root),
                                         (experiment, 'runtime_identity', lambda: deepcopy(self.fixture.runtime))):
            p = patch.object(target, attribute, value)
            p.start(); self.addCleanup(p.stop)
        # These tiny C: temp fixtures use kilobytes, not the production spill budget.
        disk = patch.object(experiment.shutil,'disk_usage',return_value=SimpleNamespace(free=20*1024**3))
        disk.start(); self.addCleanup(disk.stop)
        for name in self.fixture.code:
            source = DRAFT / name if (DRAFT / name).exists() else PROJECT / 'scripts' / name
            target = self.root / 'scripts' / name
            target.write_bytes(source.read_bytes())
            self.fixture.code[name] = gate.digest(target)
        self.database = self.root / 'synthetic.duckdb'
        con = duckdb.connect(str(self.database))
        con.execute('CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR)')
        con.execute("""INSERT INTO transactions VALUES ('2020-09-15','u1','0000000000'),
            ('2020-09-15','u2','0000000001'),('2020-09-16','u1','0000000000'),
            ('2020-09-17','u1','off-candidate'),('2020-09-23','u2','right-boundary-excluded')""")
        con.close()
        self.fixture.database.update(sha256=gate.digest(self.database), bytes=self.database.stat().st_size)
        self.registry = [dict(name=name, kind=kind) for kind, names in self.plan['features']['selected'].items() for name in names]
        self.contract = dict(registry=self.registry, digest=self.plan['feature_digest'],
            feature_sets={'manual_pilot': ['x', 'c'], 'strong_manual': ['x', 'c']})
        for ref in self.plan['train_collections']:
            path = self.root / ref['path']
            self.make_cache(path.parent)
            m = gate.read_json(path)
            m.update(database=deepcopy(self.fixture.database), features=self.contract,
                     code=dict(self.fixture.code, **{'hm_experiment.py': 'f'*64}),
                     files={name: gate.digest(path.parent/name) for name in ('frame.parquet','users.parquet','targets.parquet')})
            m['qcy_identity'] = experiment.canonical_digest({name:m['files'][name] for name in ('users.parquet','targets.parquet')})
            m['candidate_identity'] = self.candidate_identity
            write(path,m)
            ref['sha256'] = gate.digest(path)
        self.lock = self.fixture.save_lock()

    def make_cache(self, folder):
        con = duckdb.connect(':memory:')
        con.execute("""CREATE TEMP TABLE candidates AS SELECT u customer_id,lpad(i::VARCHAR,10,'0') article_id,
            (u='u1' AND i=0) AS label,120::INTEGER full_candidate_count,1.0/120 query_weight,
            1.0::DOUBLE x,'category'::VARCHAR c FROM (VALUES ('u1'),('u2')) t(u) CROSS JOIN range(120) r(i)""")
        extras = ','.join(f'1.0::DOUBLE g{i}' for i in range(12))
        con.sql('SELECT *,' + extras + ' FROM candidates ORDER BY customer_id,article_id').write_parquet(str(folder/'frame.parquet'))
        con.sql("SELECT u customer_id,sha256(u || ':2026') cohort_hash,120::INTEGER full_candidate_count FROM (VALUES ('u1'),('u2')) t(u)").write_parquet(str(folder/'users.parquet'))
        con.sql("SELECT * FROM (VALUES ('u1','0000000000'),('u1','off-candidate')) t(customer_id,article_id)").write_parquet(str(folder/'targets.parquet'))
        con.execute('CREATE TEMP TABLE hm_candidates AS SELECT customer_id,article_id FROM candidates')
        self.candidate_identity = experiment.candidate_digest(con,experiment.Deadline(30))
        con.close()

    def synthetic_modules(self):
        def retrieval(con,anchor,users,seed):
            con.execute("CREATE TEMP TABLE hm_r_users AS SELECT * FROM (VALUES ('u1'),('u2')) t(customer_id)")
            con.execute("""CREATE TEMP TABLE hm_r_candidates AS SELECT 'C0-Q120' AS policy, customer_id,
                lpad(i::VARCHAR,10,'0') AS article_id,'global' AS source,i+1 AS source_rank,i+1 AS candidate_rank
                FROM hm_r_users CROSS JOIN range(120) r(i)""")
        def features(con,anchor,candidates_table):
            frame=con.execute('SELECT customer_id,article_id FROM hm_candidates ORDER BY customer_id,article_id').fetchdf()
            for name in self.plan['features']['selected']['numeric']: frame[name]=1.
            frame['c']='category'
            return SimpleNamespace(frame=frame,registry=self.registry,feature_sets=self.contract['feature_sets'],digest=self.plan['feature_digest'])
        return {'scripts.hm_retrieval':SimpleNamespace(create_candidates=retrieval),
                'scripts.hm_feature_engine':SimpleNamespace(build_features=features,feature_manifest=lambda:dict(digest=self.plan['feature_digest']))}

    def collect(self):
        output=self.root/self.plan['outputs']['collection']
        with patch.dict('sys.modules',self.synthetic_modules()):
            result=experiment.collect(self.database,output,gate.FINAL,20000,'C0-Q120',30,self.fixture.lockpath)
        self.assertEqual(result['final_lock_sha256'],self.lock.sha256)
        return output

    def test_default_final_guards_still_reject_without_sql_or_pool(self):
        out=self.root/'artifacts/no-lock'
        with patch.object(experiment,'connection_for',side_effect=AssertionError('SQL opened')):
            with self.assertRaisesRegex(ValueError,'2020-09-09'):
                experiment.collect(self.database,out,gate.FINAL,20000,'C0-Q120',30)
        self.assertFalse(out.exists())
        final=self.collect()
        with self.assertRaisesRegex(ValueError,'2020-09-09'):
            experiment.read_manifest(final,experiment.Deadline(30))
        with patch.object(duckdb,'connect',side_effect=AssertionError('SQL opened')):
            with self.assertRaisesRegex(ValueError,'locked final anchor'):
                audit.audit(final,[],self.root/'artifacts/default-audit',wall_seconds=30)

    def test_wrong_locked_requests_fail_before_output_sql_or_pool(self):
        with patch.dict('sys.modules',self.synthetic_modules()),patch.object(experiment,'connection_for',side_effect=AssertionError('SQL opened')):
            with self.assertRaises(ValueError):
                experiment.collect(self.database,self.root/self.plan['outputs']['collection'],gate.FINAL,5000,'C0-Q120',30,self.fixture.lockpath)
        self.assertFalse((self.root/self.plan['outputs']['collection']).exists())
        final=self.collect()
        trains=[self.root/ref['path'] for ref in self.plan['train_collections']]
        with patch.object(duckdb,'connect',side_effect=AssertionError('SQL opened')),patch.object(experiment,'model_pool',side_effect=AssertionError('Pool created')):
            with self.assertRaises(ValueError):
                experiment.fit([p.parent for p in trains],final,self.root/self.plan['outputs']['fits'][0],feature_names=['x','c'],
                    iterations=500,depth=6,seed=2027,train_users=20000,negative_sample=20,wall_seconds=30,decision_lock=self.fixture.lockpath)
        self.assertFalse((self.root/self.plan['outputs']['fits'][0]).exists())
        with patch.object(duckdb,'connect',side_effect=AssertionError('SQL opened')):
            with self.assertRaises(ValueError):
                audit.audit(final,[],self.root/self.plan['outputs']['audit'],wall_seconds=30,decision_lock=self.fixture.lockpath)
        self.assertFalse((self.root/self.plan['outputs']['audit']).exists())

    def test_final_cannot_be_used_as_training_even_with_lock(self):
        final=self.collect()
        with patch.object(duckdb,'connect',side_effect=AssertionError('SQL opened')):
            with self.assertRaisesRegex(ValueError,'2020-09-09'):
                experiment.fit([final],final,self.root/self.plan['outputs']['fits'][0],feature_names=['x','c'],
                    iterations=500,depth=6,seed=2026,train_users=20000,negative_sample=20,wall_seconds=30,decision_lock=self.fixture.lockpath)
        self.assertFalse((self.root/self.plan['outputs']['fits'][0]).exists())

    def test_tiny_fake_model_four_fit_flow_and_audit_exclude_posthoc_contrasts(self):
        final=self.collect()
        original_nested=experiment.nested_users
        calls=[]
        progress=io.StringIO()
        class FakeClassifier:
            def __init__(self,**params): self.params=params; self.tree_count_=params['iterations']
            def fit(self,pool,callbacks):
                calls.append(self.params)
                for iteration in (49,50,self.params['iterations']):
                    if not callbacks[0].after_iteration(SimpleNamespace(iteration=iteration)):
                        raise RuntimeError('Unexpected fixture deadline stop')
                return self
            def save_model(self,path): Path(path).write_bytes(b'synthetic model never parsed')
            def predict_proba(self,pool,thread_count):
                if thread_count != 4: raise AssertionError('Inference thread budget differs')
                scores=np.linspace(.99,.01,pool.num_row())
                return np.column_stack((1-scores,scores))
        fits=[]
        for number in range(4):
            request=self.fixture.fit_request(number)
            output=self.root/request['output']; fits.append(output)
            with (redirect_stderr(progress),patch('catboost.CatBoostClassifier',FakeClassifier),
                  patch.object(experiment,'model_pool',side_effect=lambda numbers,*args,**kwargs:SimpleNamespace(num_row=lambda:len(numbers))),
                  patch.object(experiment,'nested_users',side_effect=lambda users,limit=None:original_nested(users,min(limit,len(users)) if limit is not None else None))):
                report=experiment.fit([self.root/ref['path'].rsplit('/',1)[0] for ref in self.plan['train_collections']],final,output,
                    feature_names=request['numeric']+request['categorical'],iterations=500,depth=6,
                    seed=request['hyperparameters']['random_seed'],train_users=20000,negative_sample=20,wall_seconds=30,decision_lock=self.fixture.lockpath)
            arm='M' if number<2 else 'selected'
            self.assertEqual(report['final_arm'],arm)
            self.assertEqual(report['final_lock_sha256'],self.lock.sha256)
            self.assertEqual(report['last_training_iteration'],500)
            original_payload=dict(inputs=report['inputs'],features=report['features'],hyperparameters=report['hyperparameters'],
                train_users=20000,negative_sample=20,sampling_seed=2026,code=report['code'],runtime=report['runtime'])
            self.assertNotEqual(experiment.canonical_digest(original_payload),report['fit_identity'])
            self.assertEqual(experiment.canonical_digest(dict(original_payload,final_lock_sha256=self.lock.sha256,final_arm=arm)),report['fit_identity'])
        self.assertEqual(len(calls),4)
        emitted=[json.loads(line) for line in progress.getvalue().splitlines()]
        self.assertEqual([row['iteration'] for row in emitted],[50,500]*4)
        self.assertTrue(all(set(row)=={'iteration','elapsed_seconds'} for row in emitted))
        self.assertTrue(progress.getvalue().isascii())
        self.assertTrue(all(params['thread_count']==4 for params in calls))
        # The unlocked development fit still hashes exactly its historical fields.
        training=[self.root/ref['path'].rsplit('/',1)[0] for ref in self.plan['train_collections']]
        with (redirect_stderr(progress),patch('catboost.CatBoostClassifier',FakeClassifier),
              patch.object(experiment,'model_pool',side_effect=lambda numbers,*args,**kwargs:SimpleNamespace(num_row=lambda:len(numbers)))):
            dev=experiment.fit(training[:3],training[3],self.root/'artifacts/dev-fit',
                feature_names=['x','c'],iterations=150,depth=6,seed=2026,train_users=2,negative_sample=20,wall_seconds=30)
        self.assertNotIn('final_lock_sha256',dev)
        self.assertNotIn('final_arm',dev)
        self.assertEqual(dev['fit_identity'],experiment.canonical_digest(dict(inputs=dev['inputs'],features=dev['features'],
            hyperparameters=dev['hyperparameters'],train_users=2,negative_sample=20,sampling_seed=2026,code=dev['code'],runtime=dev['runtime'])))
        output=self.root/self.plan['outputs']['audit']
        first_report=gate.read_json(fits[0]/'report.json')
        write(fits[0]/'report.json',dict(first_report,final_arm='selected'))
        with patch.object(duckdb,'connect',side_effect=AssertionError('SQL opened')):
            with self.assertRaisesRegex(ValueError,'arm differs'):
                audit.audit(final,fits,output,self.database,30,self.fixture.lockpath)
        self.assertFalse(output.exists())
        write(fits[0]/'report.json',first_report)
        with (patch.object(audit,'heuristic_predictions',side_effect=AssertionError('Undeclared heuristic')),
              patch.object(audit,'paired_bootstrap',side_effect=AssertionError('Undeclared contrast'))):
            report=audit.audit(final,fits,output,self.database,30,self.fixture.lockpath)
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['heuristics']['status'],'excluded')
        self.assertEqual(report['comparisons'],[])
        self.assertEqual(report['fit_vs_recency'],[])
        self.assertEqual(report['frozen_contrasts'],self.plan['contrasts'])
        self.assertEqual(len(report['fits']),4)
        for number in range(4): self.assertTrue((output/f'arm-{number:02d}-query-metrics.parquet').is_file())

    def test_native_fit_failure_preserves_bounded_private_diagnostic_and_raises(self):
        final=self.collect()
        original_nested=experiment.nested_users
        native_message='Synthetic native training failure: bad buffer or interrupted worker'
        class FailingClassifier:
            def __init__(self,**params): pass
            def fit(self,pool,callbacks):
                if not callbacks[0].after_iteration(SimpleNamespace(iteration=50)):
                    raise AssertionError('Unexpected deadline state')
                with patch.object(experiment.time,'monotonic',return_value=float('inf')):
                    if callbacks[0].after_iteration(SimpleNamespace(iteration=51)):
                        raise AssertionError('Expired callback continued training')
                raise RuntimeError(native_message)
        output=self.root/self.plan['outputs']['fits'][0]
        with (redirect_stderr(io.StringIO()),patch('catboost.CatBoostClassifier',FailingClassifier),
              patch.object(experiment,'model_pool',side_effect=lambda numbers,*args,**kwargs:SimpleNamespace(num_row=lambda:len(numbers))),
              patch.object(experiment,'nested_users',side_effect=lambda users,limit=None:original_nested(users,min(limit,len(users)) if limit is not None else None))):
            with self.assertRaisesRegex(RuntimeError,'Synthetic native training failure'):
                experiment.fit([self.root/ref['path'].rsplit('/',1)[0] for ref in self.plan['train_collections']],final,output,
                    feature_names=['x','c'],iterations=500,depth=6,seed=2026,train_users=20000,
                    negative_sample=20,wall_seconds=30,decision_lock=self.fixture.lockpath)
        report=gate.read_json(output/'report.json')
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['fit_count'],1)
        self.assertEqual(report['last_training_iteration'],51)
        self.assertEqual(report['error']['type'],'RuntimeError')
        self.assertEqual(report['error']['message'],native_message)
        self.assertIn(native_message,report['error']['traceback'])
        self.assertIn('Traceback',report['error']['traceback'])
        self.assertLessEqual(len(report['error']['message']),2048)
        self.assertLessEqual(len(report['error']['traceback']),8192)
        self.assertNotIn('validation_metrics',report)
        self.assertFalse((output/'model.cbm').exists())

    def test_four_gpu_final_fits_omit_callbacks_preserve_cpu_prediction_and_pass_existing_audit(self):
        self.plan['hyperparameters']=dict(experiment.fixed_parameters(500,6,2026,'GPU'))
        self.plan['hyperparameters'].pop('random_seed')
        self.lock=self.fixture.save_lock()
        final=self.collect()
        original_nested=experiment.nested_users
        calls=[]
        class GPUClassifier:
            def __init__(self,**params): self.params=params; self.tree_count_=params['iterations']
            # Deliberately no callbacks argument: the real GPU backend rejects it.
            def fit(self,pool): calls.append(self.params); return self
            def get_all_params(self): return dict(self.params,fixture_resolved=True)
            def save_model(self,path): Path(path).write_bytes(b'GPU fixture never parsed')
            def predict_proba(self,pool,thread_count):
                if thread_count!=4: raise AssertionError('CPU inference thread budget changed')
                scores=np.linspace(.99,.01,pool.num_row())
                return np.column_stack((1-scores,scores))
        fits=[]
        for number in range(4):
            request=self.fixture.fit_request(number)
            output=self.root/request['output'];fits.append(output)
            with (patch('catboost.CatBoostClassifier',GPUClassifier),
                  patch.object(experiment,'model_pool',side_effect=lambda numbers,*args,**kwargs:SimpleNamespace(num_row=lambda:len(numbers))),
                  patch.object(experiment,'nested_users',side_effect=lambda users,limit=None:original_nested(users,min(limit,len(users)) if limit is not None else None))):
                result=experiment.fit([self.root/ref['path'].rsplit('/',1)[0] for ref in self.plan['train_collections']],final,output,
                    feature_names=request['numeric']+request['categorical'],iterations=500,depth=6,
                    seed=request['hyperparameters']['random_seed'],train_users=20000,negative_sample=20,wall_seconds=30,
                    decision_lock=self.fixture.lockpath,task_type='GPU',external_job_timeout_seconds=60)
            self.assertEqual(result['actual_trees'],500)
            self.assertEqual(result['last_training_iteration'],500)
            self.assertEqual(result['resolved_model_parameters']['task_type'],'GPU')
            self.assertTrue(result['resources']['gpu_training_nondeterministic'])
            self.assertEqual(result['resources']['prediction_task_type'],'CPU')
            self.assertNotIn('external_job_timeout_seconds',result['hyperparameters'])
        self.assertEqual([p['random_seed'] for p in calls],[2026,2027,2026,2027])
        report=audit.audit(final,fits,self.root/self.plan['outputs']['audit'],self.database,30,self.fixture.lockpath)
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['frozen_contrasts'][0]['positive'],['arm-02','arm-03'])

    def test_incomplete_gpu_fit_cannot_claim_last_iteration_or_success(self):
        final=self.collect()
        original_nested=experiment.nested_users
        class PartialGPU:
            def __init__(self,**params): self.tree_count_=499
            def fit(self,pool): pass
        output=self.root/'artifacts/partial-gpu'
        training=[self.root/ref['path'].rsplit('/',1)[0] for ref in self.plan['train_collections'][:3]]
        validation=self.root/self.plan['train_collections'][3]['path'].rsplit('/',1)[0]
        with (patch('catboost.CatBoostClassifier',PartialGPU),
              patch.object(experiment,'model_pool',side_effect=lambda numbers,*args,**kwargs:SimpleNamespace(num_row=lambda:len(numbers))),
              patch.object(experiment,'nested_users',side_effect=lambda users,limit=None:original_nested(users,min(limit,len(users)) if limit is not None else None))):
            with self.assertRaisesRegex(RuntimeError,'GPU fit incomplete'):
                experiment.fit(training,validation,output,feature_names=['x','c'],iterations=500,depth=6,
                    train_users=20000,negative_sample=20,wall_seconds=30,task_type='GPU',external_job_timeout_seconds=60)
        report=gate.read_json(output/'report.json')
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['actual_trees'],499)
        self.assertNotIn('last_training_iteration',report)
        self.assertNotIn('resolved_model_parameters',report)
        self.assertFalse((output/'model.cbm').exists())

    def test_resolved_gpu_backend_mismatch_fails_before_validation_and_model_export(self):
        original_nested=experiment.nested_users
        class WrongBackend:
            def __init__(self,**params): self.tree_count_=500
            def fit(self,pool): pass
            def get_all_params(self): return {'task_type':'CPU'}
        output=self.root/'artifacts/wrong-gpu-backend'
        training=[self.root/ref['path'].rsplit('/',1)[0] for ref in self.plan['train_collections'][:3]]
        validation=self.root/self.plan['train_collections'][3]['path'].rsplit('/',1)[0]
        with (patch('catboost.CatBoostClassifier',WrongBackend),
              patch.object(experiment,'model_pool',side_effect=lambda numbers,*args,**kwargs:SimpleNamespace(num_row=lambda:len(numbers))),
              patch.object(experiment,'nested_users',side_effect=lambda users,limit=None:original_nested(users,min(limit,len(users)) if limit is not None else None))):
            with self.assertRaisesRegex(RuntimeError,'different backend'):
                experiment.fit(training,validation,output,feature_names=['x','c'],iterations=500,depth=6,
                    train_users=20000,negative_sample=20,wall_seconds=30,task_type='GPU',external_job_timeout_seconds=60)
        report=gate.read_json(output/'report.json')
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['resolved_model_parameters']['task_type'],'CPU')
        self.assertNotIn('validation_metrics',report)
        self.assertNotIn('last_training_iteration',report)
        self.assertFalse((output/'model.cbm').exists())


if __name__=='__main__':
    unittest.main()
