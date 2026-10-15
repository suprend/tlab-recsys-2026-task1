from copy import deepcopy
from datetime import datetime
import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import numpy as np

from scripts import metadata_ablation as a
from scripts import metadata_price_collection as c
from scripts import model_data as d
from scripts import train_baselines as b
from scripts.protocol_manifest import canonical_json,sha256_file
from scripts.ranking_metrics import evaluate
import tests.test_train_baselines as bt


def data(count=5,mixed=True):
    base=bt.prepared();base.queries += [(f'empty{i}',100+i,datetime(2019,10,8),frozenset()) for i in range(5,count)]
    if not mixed:return base
    return d.ModelData(base.queries,base.group,base.items,base.x,base.y,base.feature_names,
        np.array([[b'value:1',b'value:code',b'value:brand']]*len(base.items),dtype=object),
        ['category_id_nominal','category_code_by_id','brand'],dict(synthetic=True))


class SingleFitBoundaryTests(unittest.TestCase):
    def test_exact_one_native_call_fixed_params_weights_and_explicit_threads(self):
        audit=Mock();audit.report={'fit_attempt_count':0}
        model=Mock();model.tree_count_=50
        with patch('catboost.Pool') as pool,patch('catboost.CatBoostClassifier',return_value=model) as estimator:
            result,population=a.fit_once(data(),bt.smoke(),audit)
        self.assertIs(result,model);self.assertEqual(audit.report['fit_attempt_count'],1)
        self.assertEqual(model.fit.call_count,1);self.assertNotIn('eval_set',model.fit.call_args.kwargs)
        params=estimator.call_args.kwargs
        self.assertEqual((params['iterations'],params['depth'],params['thread_count'],params['one_hot_max_size']),(50,6,2,4096))
        self.assertEqual(params['leaf_estimation_iterations'],10);self.assertFalse(params['use_best_model'])
        self.assertEqual(pool.call_args.kwargs['thread_count'],2)
        weights=pool.call_args.kwargs['weight']
        for group in range(4):self.assertAlmostEqual(float(weights[data().group==group].sum()),1.)
        self.assertEqual(population['encoded_train_cardinality']['brand'],1)

    def test_cardinality_failure_precedes_Pool_and_consumed_fit_failure_not_retried(self):
        audit=Mock();audit.report={'fit_attempt_count':0};train=data()
        with patch.object(a.m,'validate_train_cardinality',side_effect=ValueError('one-hot ceiling')),patch('catboost.Pool') as pool:
            with self.assertRaisesRegex(ValueError,'one-hot ceiling'):a.fit_once(train,bt.smoke(),audit)
            pool.assert_not_called();self.assertEqual(audit.report['fit_attempt_count'],0)
        model=Mock();model.fit.side_effect=RuntimeError('native fit failed')
        with patch('catboost.Pool'),patch('catboost.CatBoostClassifier',return_value=model):
            with self.assertRaisesRegex(RuntimeError,'native fit failed'):a.fit_once(train,bt.smoke(),audit)
        self.assertEqual(model.fit.call_count,1);self.assertEqual(audit.report['fit_attempt_count'],1)

    def test_retention_strict_ties_recall_floor_and_integrity_failures(self):
        def metric(ndcg,recall=a.RECALL_FLOOR):return dict(conditional_macro_query=dict(ndcg=ndcg,recall=recall))
        for ndcg in [a.NDCG_FLOOR,a.NDCG_FLOOR+a.NDCG_TOLERANCE]:
            self.assertFalse(a.retention(metric(ndcg))['retain_metadata_block'])
        self.assertTrue(a.retention(metric(a.NDCG_FLOOR+2e-12))['retain_metadata_block'])
        self.assertFalse(a.retention(metric(.99,a.RECALL_FLOOR-1e-12))['retain_metadata_block'])
        with self.assertRaisesRegex(ValueError,'Undefined'):a.retention(metric(np.nan))

    def test_saved_model_CTR_parameter_drift_and_checkpoint_gates(self):
        params={k:1 for k in ['loss_function','iterations','depth','learning_rate','l2_leaf_reg','random_seed','task_type',
            'boosting_type','bootstrap_type','leaf_estimation_method','leaf_estimation_iterations','leaf_estimation_backtracking',
            'random_strength','boost_from_average','use_best_model','border_count','nan_mode','rsm']}
        model=Mock();model.get_all_params.return_value={**params,'one_hot_max_size':4096}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.json'
            def save(*args,**kwargs):b._atomic_json(path,dict(oblivious_trees=[dict(splits=[dict(split_type='FloatFeature')])]*50))
            model.save_model.side_effect=save;a.validate_model(model,params,path)
            model.get_all_params.return_value={**params,'one_hot_max_size':4000}
            with self.assertRaisesRegex(ValueError,'parameters'):a.validate_model(model,params,path)
            model.get_all_params.return_value={**params,'one_hot_max_size':4096}
            def bad_save(*args,**kwargs):b._atomic_json(path,dict(oblivious_trees=[dict(splits=[dict(split_type='OnlineCtr')])]*50))
            model.save_model.side_effect=bad_save
            with self.assertRaisesRegex(ValueError,'CTR'):a.validate_model(model,params,path)


class ControlScopeTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.addCleanup(patch.stopall)
        for module in [a,c]:patch.object(module,'ROOT',self.root).start()
        source=self.root/'source';source.write_text('synthetic accepted source')
        identity=dict(config=dict(iterations=50),fingerprints={'source':sha256_file(source)})
        self.expected=dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity)
        self.directory=self.root/'artifacts/training'/self.expected['run_id'];self.directory.mkdir(parents=True)
        self.execution=self.root/'execution.json'
        b._atomic_json(self.execution,dict(version=1,approved=True,scope='cpu_smoke_two_fits',run_id=self.expected['run_id'],fingerprints=identity['fingerprints']))
        ref=dict(path='execution.json',sha256=sha256_file(self.execution))
        manifest={**deepcopy(self.expected),'fit_approval':ref};b._atomic_json(self.directory/'run.json',manifest)
        attempts=[]
        for method in ['Logloss','PairLogit']:
            outputs={}
            for suffix in ['.cbm','-scores.npz']:
                path=self.directory/(method+suffix);path.write_text('synthetic accepted output');outputs[str(path.relative_to(self.root))]=sha256_file(path)
            attempts.append(dict(method=method,status='complete',tree_count=50,checkpoint_iterations=50,artifacts=outputs,
                metrics=dict(conditional_macro_query=dict(ndcg=a.NDCG_FLOOR,recall=a.RECALL_FLOOR+.002))))
        self.report=dict(run_id=self.expected['run_id'],status='complete_produced_unreviewed',config=identity['config'],fit_attempt_count=2,fit_attempts=attempts)
        b._atomic_json(self.directory/'report.json',self.report)
        self.claim=self.root/'artifacts/fit-claims'/(self.expected['run_id']+'.json');self.claim.parent.mkdir()
        b._atomic_json(self.claim,dict(version=1,run_id=self.expected['run_id'],allowed_fit_attempts=2,fit_approval=ref,
            output_directory=str(self.directory.relative_to(self.root)),report=str((self.directory/'report.json').relative_to(self.root))))
        for name in a.PROOFS:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic independent accepted proof')
        files=[source,self.execution,self.claim,self.directory/'run.json',self.directory/'report.json',*[self.root/n for n in a.PROOFS]]
        self.pins={str(p.relative_to(self.root)):sha256_file(p) for p in files}
        for attempt in attempts:self.pins.update(attempt['artifacts'])
        self.path=self.root/'control.json';self.reseal()
        patch.object(b,'prepare_fit_plan',return_value=(deepcopy(self.expected),{},{})).start()

    def reseal(self):
        b._atomic_json(self.path,dict(version=1,approved=True,scope='reviewed_cpu_smoke_control',run_id=self.expected['run_id'],fingerprints=self.pins))

    def verify(self):return a.verify_control(self.path,self.root/'config',self.root/'train',self.root/'selection')

    def test_exact_control_scope_passes_but_missing_input_output_or_proof_rejected(self):
        result=self.verify();self.assertEqual(result['manifest']['run_id'],self.expected['run_id'])
        for name in ['source',a.PROOFS[0],str((self.directory/'Logloss.cbm').relative_to(self.root))]:
            original=dict(self.pins);self.pins.pop(name);self.reseal()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'scope|Missing'):self.verify()
            self.pins=original;self.reseal()

    def test_fresh_resealed_wrong_tree_count_or_claim_rejected_without_fit(self):
        self.report['fit_attempts'][0]['tree_count']=49
        b._atomic_json(self.directory/'report.json',self.report)
        name=str((self.directory/'report.json').relative_to(self.root));self.pins[name]=sha256_file(self.directory/'report.json');self.reseal()
        with self.assertRaisesRegex(ValueError,'50tree'):self.verify()
        self.report['fit_attempts'][0]['tree_count']=50;b._atomic_json(self.directory/'report.json',self.report)
        self.pins[name]=sha256_file(self.directory/'report.json')
        claim=b._read_json(self.claim);claim['allowed_fit_attempts']=3;b._atomic_json(self.claim,claim)
        self.pins[str(self.claim.relative_to(self.root))]=sha256_file(self.claim);self.reseal()
        with self.assertRaisesRegex(ValueError,'claim differs'):self.verify()

    def test_fresh_resealed_bool_claim_version_is_not_integer_one(self):
        claim=b._read_json(self.claim);claim['version']=True;b._atomic_json(self.claim,claim)
        self.pins[str(self.claim.relative_to(self.root))]=sha256_file(self.claim);self.reseal()
        with self.assertRaisesRegex(ValueError,'claim differs'):self.verify()


class ClaimAndRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.addCleanup(patch.stopall)
        for module in [a,c]:patch.object(module,'ROOT',self.root).start()
        self.source=self.root/'input.json';self.source.write_text('{}')
        identity=dict(fingerprints={'input.json':sha256_file(self.source)},config=bt.smoke(),
            numeric_features=data().feature_names,categorical_features=data().categorical_names)
        self.manifest=dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity)
        self.approval=self.root/'execution.json'
        b._atomic_json(self.approval,dict(version=1,approved=True,scope=a.ROLE,run_id=self.manifest['run_id'],fingerprints=identity['fingerprints']))
        self.train=data(6000);self.selection=data(4000);self.scores=np.zeros(len(self.selection.items))
        self.score_path=self.root/'control.npz';np.savez_compressed(self.score_path,group=self.selection.group,product_id=self.selection.items,raw_score=self.scores)
        self.metrics=a.asdict(evaluate(b.rankings(self.selection,self.scores),20))
        self.inputs=dict(train={'phase':'train'},selection={'phase':'selection'},export={'refs':{'train':['train-add.parquet'],'selection':['selection-add.parquet']}},
            control=dict(score_path=self.score_path,control=dict(metrics=self.metrics,actual_model_parameters={})))

    def reports(self):return [b._read_json(p) for p in (self.root/'artifacts/metadata-ablation').glob('*/report.json')]

    def execute(self,*,fit_error=None,prepare_error=None):
        model=Mock();model.predict.return_value=self.scores
        model.feature_names_=self.train.feature_names+self.train.categorical_names
        def save(path,*args,**kwargs):Path(path).write_text('synthetic model')
        model.save_model.side_effect=save
        def validate(*args):path=args[-1];Path(path).write_text('{}');return {}
        def fitting(train,config,audit):
            if fit_error is not None:raise fit_error
            audit.report['fit_attempt_count']+=1
            return model,dict(synthetic=True)
        with patch.object(a,'prepare_plan',return_value=(deepcopy(self.manifest),deepcopy(self.inputs))),\
            patch.object(b,'prepare_dataset',side_effect=[data(6000,False),data(4000,False)]),\
            patch.object(d,'prepare_model_data',side_effect=prepare_error or [data(6000,False),self.train,data(4000,False),self.selection]),\
            patch.object(a,'fit_once',side_effect=fitting) as fit,\
            patch.object(a,'validate_model',side_effect=validate),patch('catboost.Pool'),\
            contextlib.redirect_stdout(io.StringIO()):
            result=a.run(self.source,self.source,self.source,self.source,self.source,execution_approval=self.approval)
        return result,fit,model

    def test_claim_is_global_across_changed_plan_and_written_before_preparation(self):
        audit=Mock();audit.directory=self.root/'out';audit.report={}
        a.consume_claim(self.manifest,audit)
        changed=deepcopy(self.manifest);changed['run_id']='b'*64
        with self.assertRaises(FileExistsError):a.consume_claim(changed,audit)
        claim=b._read_json(self.root/a.CLAIM)
        self.assertEqual(claim['consumed_before'],'matrix_Pool_fit_preparation')

    def test_synthetic_runtime_exact_score_keys_metrics_and_no_refit_control(self):
        report,fit,model=self.execute()
        self.assertEqual(report['status'],'complete_produced_unreviewed');self.assertTrue(report['labels_loaded'])
        fit.assert_called_once();self.assertEqual(model.predict.call_args.kwargs['thread_count'],2)
        self.assertFalse(report['decision']['retain_metadata_block'])
        with self.assertRaises(FileExistsError):self.execute()

    def test_resource_preparation_failure_consumes_attempt_and_chooses_base_without_fit(self):
        with self.assertRaisesRegex(MemoryError,'synthetic memory'):
            self.execute(prepare_error=MemoryError('synthetic memory'))
        self.assertTrue((self.root/a.CLAIM).exists())
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed');self.assertEqual(report['decision']['feature_choice'],'base41')
        self.assertEqual(report['fit_attempt_count'],0)

    def test_integrity_or_API_failure_stops_without_resource_fallback_or_replacement(self):
        with self.assertRaisesRegex(ValueError,'synthetic key mismatch'):
            self.execute(prepare_error=ValueError('synthetic key mismatch'))
        report=self.reports()[0]
        self.assertIn('stop',report['decision']['feature_choice']);self.assertTrue((self.root/a.CLAIM).exists())

    def test_wrong_executionapproval_never_consumes_claim_or_loads_matrices(self):
        approval=b._read_json(self.approval);approval['approved']=False;b._atomic_json(self.approval,approval)
        with self.assertRaisesRegex(ValueError,'approval'):self.execute()
        self.assertFalse((self.root/a.CLAIM).exists())

    def test_saved_control_score_wrong_key_fails_before_new_fit(self):
        np.savez_compressed(self.score_path,group=self.selection.group,product_id=self.selection.items+1,raw_score=self.scores)
        with self.assertRaisesRegex(ValueError,'same selection keys'):self.execute()
        self.assertTrue((self.root/a.CLAIM).exists());self.assertEqual(self.reports()[0]['fit_attempt_count'],0)

    def test_terminal_resource_reclassifies_previous_retention_and_preserves_primary(self):
        original=c._atomic_json
        def writer(path,value):
            if path.name=='run.json':raise MemoryError('primary terminal manifest memory')
            return original(path,value)
        with patch.object(c,'_atomic_json',side_effect=writer),self.assertRaisesRegex(MemoryError,'primary terminal'):
            with a.AblationAudit(self.root/'artifacts/metadata-ablation',seconds=10,scope=a.ROLE) as audit:
                audit.manifest={'synthetic':True};audit.report.update(status='complete_produced_unreviewed',
                    decision=dict(retain_metadata_block=True,feature_choice='base41_plus_metadata18'))
        report=self.reports()[0]
        self.assertEqual(report['status'],'failed');self.assertEqual(report['decision']['feature_choice'],'base41')
        self.assertFalse(report['decision']['retain_metadata_block']);self.assertEqual(report['error_type'],'MemoryError')

    def test_terminal_writer_reclassifies_report_and_existing_failed_marker_to_STOP(self):
        original=c._atomic_json
        def writer(path,value):
            if path.name=='report.json' and value.get('status')=='complete_produced_unreviewed':raise OSError('primary terminal final writer')
            return original(path,value)
        with patch.object(c,'_atomic_json',side_effect=writer),self.assertRaisesRegex(OSError,'primary terminal'):
            with a.AblationAudit(self.root/'artifacts/metadata-ablation',seconds=10,scope=a.ROLE) as audit:
                audit.report.update(status='complete_produced_unreviewed',decision=dict(retain_metadata_block=True))
        for path in (self.root/'artifacts/metadata-ablation').glob('*/report*.json'):
            report=b._read_json(path);self.assertEqual(report['status'],'failed')
            self.assertIn('stop',report['decision']['feature_choice']);self.assertFalse(report['decision']['retain_metadata_block'])
            self.assertEqual(report['error_type'],'OSError')

    def test_secondary_policy_writer_failure_never_masks_primary_terminal_resource(self):
        original=c._atomic_json
        def writer(path,value):
            if path.name=='run.json':raise MemoryError('primary resource')
            if value.get('terminal_decision_receipt_tail'):raise OSError('secondary policy writer')
            return original(path,value)
        with patch.object(c,'_atomic_json',side_effect=writer),self.assertRaisesRegex(MemoryError,'primary resource'):
            with a.AblationAudit(self.root/'artifacts/metadata-ablation',seconds=10,scope=a.ROLE) as audit:
                audit.manifest={'synthetic':True};audit.report.update(status='complete_produced_unreviewed',decision=dict(retain_metadata_block=True))
        marker=next((self.root/'artifacts/metadata-ablation').glob('*/report.failed.json'))
        report=b._read_json(marker)
        self.assertEqual(report['decision']['feature_choice'],'base41');self.assertFalse(report['decision']['retain_metadata_block'])
        self.assertEqual(report['error_type'],'MemoryError');self.assertIn('secondary policy writer',report['secondary_errors'][0]['error'])


if __name__=='__main__':unittest.main()
