"""Substantive loss populations, full-Y evaluation and external data acceptance."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import numpy as np

from scripts import train_baselines as b
from scripts.protocol_manifest import sha256_file, load_run_manifest, canonical_json
from scripts.ranking_metrics import evaluate
import tests.test_development_collection as development_tests

ROOT=Path(__file__).resolve().parents[1]


def prepared():
    queries=[('negative',1,datetime(2019,10,8),frozenset()),
             ('allpositive',2,datetime(2019,10,8),frozenset({10,11})),
             ('mixed',3,datetime(2019,10,8),frozenset({20})),
             ('missed',4,datetime(2019,10,8),frozenset({999})),
             ('emptyC',5,datetime(2019,10,8),frozenset({111}))]
    return b.Prepared(queries,np.array([0,0,1,1,2,2,2,3,3],dtype=np.int32),
        np.array([3,5,10,11,20,21,22,30,31],dtype=np.int64),
        np.array([[1,8],[3,2],[2,3],[6,1],[4,6],[0,9],[8,4],[5,2],[2,np.nan]],dtype=np.float32),
        np.array([0,0,1,1,1,0,0,0,0],dtype=np.int8),['count','age'])


def smoke():
    config=b._read_json(ROOT/'configs/models/cpu-smoke.json')
    config.update(iterations=1,depth=2,bootstrap_replicates=12)
    return config


class TrainingMathTests(unittest.TestCase):
    def test_equal_query_mass_all_mature_BCE_and_explicit_pair_mass(self):
        data=prepared()
        counts,p,n,informative,weights,summary=b.group_accounting(data)
        np.testing.assert_array_equal(counts,[2,2,3,2,0])
        self.assertEqual(summary['all_negative_groups'],2)
        self.assertEqual(summary['all_positive_groups'],1)
        self.assertEqual(summary['empty_candidate_groups'],1)
        self.assertEqual(summary['zero_gradient_pairwise_groups'],4)
        self.assertEqual(summary['positive_fullY_queries'],4)
        for group in range(4):self.assertAlmostEqual(weights[data.group==group].sum(),1)
        retained,pairs,pairweights,report=b.explicit_pairs(data,max_pairs=10)
        np.testing.assert_array_equal(pairs,[[0,1],[0,2]])
        np.testing.assert_array_equal(data.y[retained][pairs[:,0]],[1,1])
        np.testing.assert_array_equal(data.y[retained][pairs[:,1]],[0,0])
        np.testing.assert_allclose(pairweights,[0.5,0.5])
        self.assertAlmostEqual(pairweights.sum(),1)
        self.assertEqual(int(retained.sum()),3)

    def test_pair_cap_and_no_signal_reject_before_inventing_examples(self):
        data=prepared()
        with self.assertRaisesRegex(ValueError,'before allocation'):b.explicit_pairs(data,max_pairs=1)
        data.y[:]=0
        with self.assertRaisesRegex(ValueError,'No informative'):b.explicit_pairs(data,max_pairs=10)
        data=prepared();data.group[2]=3
        with self.assertRaisesRegex(ValueError,'contiguous'):b.group_accounting(data)

    def test_full_targets_empty_C_and_deterministic_score_ties(self):
        data=prepared()
        rows=b.rankings(data,np.zeros(len(data.group)))
        self.assertEqual(rows[0].ranked_items,(3,5))
        self.assertEqual(rows[3].targets,{999})
        self.assertEqual(rows[4].ranked_items,())
        result=evaluate(rows,20)
        self.assertEqual((result.query_count,result.nonempty_query_count),(5,4))
        self.assertAlmostEqual(result.conditional_macro_query.ndcg,0.5)
        self.assertAlmostEqual(result.all_query_zero.ndcg,0.4)
        for scores in [np.zeros(8),np.array([np.nan]*9)]:
            with self.assertRaisesRegex(ValueError,'Predictions'):b.rankings(data,scores)

    def test_real_CPU_fits_both_objectives_no_evalset_and_fixed_checkpoint(self):
        from catboost import Pool
        data=prepared()
        for method in ['Logloss','PairLogit']:
            with self.subTest(method=method):
                with patch('catboost.Pool',wraps=Pool) as constructor:
                    model,summary=b.fit_smoke_model(data,method,smoke())
                    self.assertEqual(constructor.call_args.kwargs['thread_count'],2)
                values=model.predict(data.x,prediction_type='RawFormulaVal') if method=='Logloss' else model.predict(data.x)
                self.assertEqual(np.asarray(values).shape,(9,))
                self.assertTrue(np.isfinite(values).all())
                self.assertEqual(model.tree_count_,1)
                self.assertEqual(model.get_all_params()['task_type'],'CPU')
                self.assertFalse(model.get_all_params()['use_best_model'])
                self.assertEqual(summary['trained_rows'],9 if method=='Logloss' else 3)

    def test_iteration_resource_callback_aborts_without_accepting_short_checkpoint(self):
        calls=[]
        def guard():
            calls.append(1)
            if len(calls)>1:raise TimeoutError('synthetic iteration budget')
        with self.assertRaisesRegex(TimeoutError,'iteration budget'):
            b.fit_smoke_model(prepared(),'Logloss',smoke(),check=guard)

    def test_numeric_features_exclude_all_raw_IDs_and_convert_retrieval_time(self):
        columns=['query_id','user_id','product_id','anchor','candidate_category_id','last_user_event_time',
                 'user_view_7d','candidate_category_missing']
        names=b.numeric_feature_names(columns)
        self.assertEqual(names,['user_view_7d','candidate_category_missing',
                               'retrieval_last_event_age_seconds','retrieval_last_event_missing'])

    def test_empty_C_prediction_skips_native_call_and_retains_all_queries(self):
        from unittest.mock import Mock
        data=prepared()
        data.group=data.group[:0];data.items=data.items[:0];data.y=data.y[:0];data.x=data.x[:0]
        model=Mock();model.predict.side_effect=AssertionError('empty native prediction')
        scores=b.predict_scores(model,data,'PairLogit')
        result=evaluate(b.rankings(data,scores),20)
        self.assertEqual(result.query_count,5)
        self.assertEqual(result.conditional_macro_query.ndcg,0)
        self.assertEqual(result.all_query_zero.recall,0)

    def test_both_native_prediction_apis_have_explicit_two_thread_budget(self):
        from unittest.mock import Mock
        for method in ['Logloss','PairLogit']:
            model=Mock();model.predict.return_value=np.zeros(9)
            b.predict_scores(model,prepared(),method)
            self.assertEqual(model.predict.call_args.kwargs['thread_count'],2)
            if method=='Logloss':self.assertEqual(model.predict.call_args.kwargs['prediction_type'],'RawFormulaVal')

    def test_checkpoint_phase_and_compute_gap_reject_unavailable_or_confirmation_input(self):
        base=b._read_json(ROOT/'configs/protocols/clock-48h.json')
        phase=b._read_json(ROOT/'configs/development/train.json')
        train=dict(phase=phase,plan=dict(identity=dict(source_sha256='a'*64,registry_sha256='b'*64,
                                                    shard_protocols=[base])))
        selection=deepcopy(train)
        selection['phase']=b._read_json(ROOT/'configs/development/selection.json')
        b.validate_training_phases(train,selection,smoke())
        for mutation in [lambda s:s['phase'].update(role='confirmation'),
                         lambda s:s['phase']['range'].update(start='2019-10-21T00:00:00Z'),
                         lambda s:s['plan']['identity'].update(source_sha256='c'*64)]:
            bad=deepcopy(selection);mutation(bad)
            with self.assertRaises(ValueError):b.validate_training_phases(train,bad,smoke())
        narrow_train,narrow_selection=deepcopy(train),deepcopy(selection)
        for collection in [narrow_train,narrow_selection]:
            collection['phase']['model_timing']['available_at']='2019-10-21T00:00:01Z'
        with self.assertRaisesRegex(ValueError,'Compute budget'):
            b.validate_training_phases(narrow_train,narrow_selection,smoke())


class TrainingDataTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.addCleanup(patch.stopall)
        patch.object(b,'ROOT',self.root).start()
        con=duckdb.connect(':memory:')
        try:
            con.execute('CREATE TABLE q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
            con.executemany('INSERT INTO q VALUES (?,?,?,true)',[(q[0],q[1],q[2]) for q in prepared().queries])
            con.execute('CREATE TABLE y(query_id VARCHAR,product_id BIGINT)')
            con.executemany('INSERT INTO y VALUES (?,?)',[(q[0],i) for q in prepared().queries for i in q[3]])
            con.execute('''CREATE TABLE f(query_id VARCHAR,user_id BIGINT,product_id BIGINT,anchor TIMESTAMP,
                        candidate_category_id BIGINT,last_user_event_time TIMESTAMP,user_view_7d BIGINT)''')
            con.executemany('INSERT INTO f VALUES (?,?,?,?,?,?,?)',[
                (prepared().queries[g][0],int(g)+1,int(item),datetime(2019,10,8),100,datetime(2019,10,7),int(j))
                for j,(g,item) in enumerate(zip(prepared().group,prepared().items))])
            self.refs={}
            for table,name in [('q','queries'),('y','labels'),('f','features')]:
                path=self.root/(name+'.parquet')
                con.execute(f'COPY {table} TO ? (FORMAT PARQUET)',[str(path)])
                self.refs[name]=[path.name]
            self.collection=dict(refs=self.refs,feature_columns=[r[0] for r in con.execute('DESCRIBE f').fetchall()])
        finally:con.close()

    def test_real_parquet_prepare_keeps_fullY_outside_C_and_float32_missing_semantics(self):
        data=b.prepare_dataset(self.collection,max_queries=None,max_rows=20)
        self.assertEqual(data.x.dtype,np.float32)
        self.assertEqual(len(data.queries),5)
        self.assertEqual(len(data.items),9)
        q={q[0]:q[3] for q in data.queries}
        self.assertEqual(q['missed'],{999})
        self.assertEqual(q['emptyC'],{111})
        self.assertNotIn(999,data.items)
        self.assertNotIn(111,data.items)
        self.assertTrue((data.x[:,-2]==86400).all())
        self.assertEqual(int(data.y.sum()),3)

    def test_sampled_queries_do_not_change_when_labels_change(self):
        first=b.prepare_dataset(self.collection,max_queries=2,max_rows=20)
        con=duckdb.connect(':memory:')
        try:
            con.execute('CREATE TABLE l(query_id VARCHAR,product_id BIGINT)')
            con.execute("INSERT INTO l VALUES ('missed',30)")
            con.execute('COPY l TO ? (FORMAT PARQUET)',[str(self.root/'changed.parquet')])
        finally:con.close()
        changed=deepcopy(self.collection);changed['refs']['labels']=['changed.parquet']
        second=b.prepare_dataset(changed,max_queries=2,max_rows=20)
        self.assertEqual([q[0] for q in first.queries],[q[0] for q in second.queries])
        np.testing.assert_array_equal(first.items,second.items)
        np.testing.assert_array_equal(first.x,second.x)
        with self.assertRaisesRegex(ValueError,'before allocation'):
            b.prepare_dataset(self.collection,max_queries=None,max_rows=1)


class SmokeRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        p=patch.object(b,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        self.config=self.root/'config.json';b._atomic_json(self.config,smoke())
        import shutil
        shutil.copyfile(ROOT/'uv.lock',self.root/'uv.lock')
        identity=dict(config=smoke(),fingerprints={'config.json':sha256_file(self.config)})
        import hashlib
        self.manifest=dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity)
        self.approval=self.root/'approval.json'
        b._atomic_json(self.approval,dict(version=1,approved=True,scope='cpu_smoke_two_fits',
            run_id=self.manifest['run_id'],fingerprints=identity['fingerprints']))
        self.collection=dict(phase=dict(model_timing=dict(fit_data_cutoff='2019-10-21T00:00:00Z',
            available_at='2019-10-22T00:00:00Z')))

    def execute(self, output_name='models', plan_hook=None):
        plan_hook = plan_hook or (lambda *args,**kwargs:(deepcopy(self.manifest),self.collection,self.collection))
        with patch.object(b,'prepare_fit_plan',side_effect=plan_hook), \
             patch.object(b,'prepare_dataset',side_effect=lambda *args,**kwargs:prepared()):
            return b.run(self.config,self.root/'train.json',self.root/'selection.json',self.root/'artifacts'/output_name,
                         fit_approval_path=self.approval)

    def test_two_actual_tiny_fits_export_metrics_and_immutable_retry_spends_no_new_fit(self):
        result=self.execute()
        self.assertEqual(result['status'],'complete_produced_unreviewed')
        self.assertEqual(result['fit_attempt_count'],2)
        self.assertEqual([r['method'] for r in result['fit_attempts']],['Logloss','PairLogit'])
        for entry in result['fit_attempts']:
            self.assertEqual(entry['status'],'complete')
            self.assertEqual(entry['metrics']['query_count'],5)
            for name,digest in entry['artifacts'].items():
                self.assertEqual(sha256_file(self.root/name),digest)
        with patch.object(b,'fit_smoke_model',side_effect=AssertionError('no free retry fit')):
            with self.assertRaisesRegex(FileExistsError,'budget recovery'):self.execute()
        reports=list((self.root/'artifacts/models').glob('attempt-*/report.json'))
        self.assertEqual(b._read_json(reports[0])['fit_attempt_count'],0)

    def test_changed_destination_cannot_execute_same_approved_identity_twice(self):
        self.execute('first')
        with patch.object(b,'fit_smoke_model',side_effect=AssertionError('no second pair of fits')):
            with self.assertRaisesRegex(FileExistsError,'already consumed'):
                self.execute('second')
        claims=list((self.root/'artifacts/fit-claims').glob('*.json'))
        self.assertEqual(len(claims),1)
        self.assertEqual(b._read_json(claims[0])['allowed_fit_attempts'],2)

    def test_failed_first_fit_consumes_identity_across_destinations_and_retains_audit(self):
        with patch.object(b,'fit_smoke_model',side_effect=TimeoutError('failed first fit')):
            with self.assertRaisesRegex(TimeoutError,'failed first fit'):self.execute('first')
        reports=list((self.root/'artifacts/first').glob('*/report.json'))
        failed=b._read_json(reports[0])
        self.assertEqual(failed['fit_attempt_count'],1)
        self.assertEqual(failed['fit_attempts'][0]['status'],'failed')
        with patch.object(b,'fit_smoke_model',side_effect=AssertionError('new fit prohibited')):
            with self.assertRaisesRegex(FileExistsError,'already consumed'):self.execute('second')

    def test_config_swap_between_initial_parse_and_approved_plan_refuses_before_claim(self):
        import hashlib
        def replace_config(*args,**kwargs):
            config=smoke();config['iterations']=2
            b._atomic_json(self.config,config)
            identity=dict(config=config,fingerprints={'config.json':sha256_file(self.config)})
            manifest=dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity)
            b._atomic_json(self.approval,dict(version=1,approved=True,scope='cpu_smoke_two_fits',
                run_id=manifest['run_id'],fingerprints=identity['fingerprints']))
            return manifest,self.collection,self.collection
        with patch.object(b,'fit_smoke_model',side_effect=AssertionError('config mismatch must not fit')):
            with self.assertRaisesRegex(ValueError,'between initial parse'):
                self.execute(plan_hook=replace_config)
        self.assertFalse((self.root/'artifacts/fit-claims').exists())

    def test_snapshot_config_change_during_plan_is_not_rebaselined_to_fresh_hash(self):
        import shutil
        for name in [*b.CODE,'pyproject.toml']:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,path)
        collection=dict(phase={},pins={},feature_columns=[],plan={'collection_id':'a'*64})
        snapshot=b._config_snapshot
        def swap(path):
            config,digest=snapshot(path)
            changed={**config,'iterations':2};b._atomic_json(path,changed)
            return config,digest
        with patch.object(b,'_config_snapshot',side_effect=swap), \
             patch.object(b,'verify_collection',return_value=collection), \
             patch.object(b,'validate_training_phases'):
            with self.assertRaisesRegex(ValueError,'during fit-plan preparation'):
                b.prepare_fit_plan(self.config,self.root/'train.json',self.root/'selection.json')

    def test_environment_must_match_loaded_installed_and_locked_versions(self):
        lock=self.root/'uv.lock'
        lock.write_text('[[package]]\nname="catboost"\nversion="0.0"\n')
        with patch.object(b,'fit_smoke_model',side_effect=AssertionError('wrong environment must not fit')):
            with self.assertRaisesRegex(ValueError,'differs from lock'):self.execute()

    def test_wrong_fit_scope_refuses_before_either_model_and_saves_failure_audit(self):
        approval=b._read_json(self.approval);approval['scope']='output_acceptance'
        b._atomic_json(self.approval,approval)
        with patch.object(b,'fit_smoke_model',side_effect=AssertionError('fit forbidden')):
            with self.assertRaisesRegex(ValueError,'two-fit experiment approval'):self.execute()
        reports=list((self.root/'artifacts/models').glob('attempt-*/report.json'))
        report=b._read_json(reports[0])
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['fit_attempt_count'],0)


class CollectionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        fixture=development_tests.DevelopmentRuntimeTests('test_actual_producers_wait_for_external_review_then_resume_full_features_and_cache')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        fixture.execute();fixture.approve_shards();fixture.execute()
        self.root=fixture.root
        p=patch.object(b,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        state=fixture.read_state();plan=fixture.plan
        names={str(fixture.directory.relative_to(self.root))+'/state.json',
               str(fixture.directory.relative_to(self.root))+'/plan.json',state['attempts'][-1]}
        names.update(plan['execution_inputs']['fingerprints'])
        for entry in state['shards']:
            names.add(entry['acceptance']['path'])
            for kind in ['anchor','candidate','features']:
                names.update(entry[kind]['fingerprints'])
                manifest=load_run_manifest(self.root/entry[kind]['directory']/'run.json')
                names.update(manifest['identity']['code_hashes'])
                names.update(manifest['identity']['input_hashes'])
        self.path=self.root/'artifacts/acceptance/collection.json'
        self.approval=dict(version=1,approved=True,scope='reviewed_development_collection',
            collection_id=plan['collection_id'],complete_attempt_report=state['attempts'][-1],
            fingerprints={name:sha256_file(self.root/name) for name in sorted(names)})
        b._atomic_json(self.path,self.approval)

    def test_exact_external_acceptance_accepts_then_missing_or_extra_scope_rejects(self):
        collection=b.verify_collection(self.path)
        self.assertEqual(collection['phase']['role'],'train')
        self.assertEqual(len(collection['refs']['features']),2)
        approval=deepcopy(self.approval)
        key=next(n for n in approval['fingerprints'] if n.endswith('features.parquet'))
        del approval['fingerprints'][key]
        b._atomic_json(self.path,approval)
        with self.assertRaisesRegex(ValueError,'Missing/mismatched'):b.verify_collection(self.path)
        approval=deepcopy(self.approval)
        extra=self.root/'extra.txt';extra.write_text('unrelated')
        approval['fingerprints']['extra.txt']=sha256_file(extra)
        b._atomic_json(self.path,approval)
        with self.assertRaisesRegex(ValueError,'exact required lineage'):b.verify_collection(self.path)

    def test_changed_source_and_unapproved_collection_refuse_fit_inputs(self):
        approval=deepcopy(self.approval);approval['approved']=False
        b._atomic_json(self.path,approval)
        with self.assertRaisesRegex(ValueError,'acceptance required'):b.verify_collection(self.path)
        b._atomic_json(self.path,self.approval)
        self.fixture.db.write_bytes(self.fixture.db.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'content changed'):b.verify_collection(self.path)

    def test_fresh_resealed_plan_cannot_detach_claims_from_actual_input_bundle(self):
        import hashlib
        original_plan=deepcopy(self.fixture.plan)
        original_state=self.fixture.read_state()
        original_report=b._read_json(self.root/self.approval['complete_attempt_report'])
        extra=self.root/'extra.txt';extra.write_text('unrelated execution input')
        cases=[
            (lambda p:p['identity'].update(source_sha256='d'*64),'source identity'),
            (lambda p:p['identity'].update(registry_sha256='e'*64),'registry identity'),
            (lambda p:p['identity']['code_hashes'].update({'scripts/manual_features.py':'f'*64}),'code identity'),
            (lambda p:p['identity']['phase'].update(name='fresh-but-unbound-name'),'phase identity'),
            (lambda p:p['execution_inputs']['fingerprints'].update({'extra.txt':sha256_file(extra)}),'input scope')]
        for index,(mutate,error) in enumerate(cases):
            with self.subTest(error=error):
                plan=deepcopy(original_plan);mutate(plan)
                plan['collection_id']=hashlib.sha256(canonical_json(plan['identity']).encode()).hexdigest()
                directory=self.root/'artifacts'/('reseed-'+str(index))/plan['collection_id']
                directory.mkdir(parents=True)
                state=deepcopy(original_state);state['collection_id']=plan['collection_id']
                report=deepcopy(original_report);report['collection_id']=plan['collection_id']
                report_path=self.root/'artifacts'/('fault-report-'+str(index)+'.json')
                report_name=str(report_path.relative_to(self.root))
                state['attempts'][-1]=report_name
                b._atomic_json(directory/'plan.json',plan)
                b._atomic_json(directory/'state.json',state)
                b._atomic_json(report_path,report)
                approval=deepcopy(self.approval)
                approval.update(collection_id=plan['collection_id'],complete_attempt_report=report_name)
                for name in list(approval['fingerprints']):
                    if name in {str((self.fixture.directory/'state.json').relative_to(self.root)),
                                str((self.fixture.directory/'plan.json').relative_to(self.root)),
                                self.approval['complete_attempt_report']}:
                        del approval['fingerprints'][name]
                for path in [directory/'state.json',directory/'plan.json',report_path]:
                    approval['fingerprints'][str(path.relative_to(self.root))]=sha256_file(path)
                if error=='input scope':approval['fingerprints']['extra.txt']=sha256_file(extra)
                b._atomic_json(self.path,approval)
                with self.assertRaisesRegex(ValueError,error):b.verify_collection(self.path)

    def test_fresh_resealed_child_cannot_omit_registry_code_or_accepted_QYC_dependency(self):
        from scripts.protocol_manifest import write_run_manifest
        import hashlib
        state_path=self.fixture.directory/'state.json'
        original_state=state_path.read_bytes()
        state=b._read_json(state_path)
        entry=state['shards'][0]
        manifest_path=self.root/entry['features']['directory']/'run.json'
        report_path=manifest_path.parent/'report.json'
        original_manifest,original_report=manifest_path.read_bytes(),report_path.read_bytes()
        cases=[('input_hashes',self.fixture.phase['feature_registry'],'Feature registry lineage'),
               ('code_hashes','scripts/manual_features.py','Unexpected producer code lineage'),
               ('input_hashes',entry['acceptance']['path'],'exact accepted Q/Y/C lineage')]
        for group,key,error in cases:
            with self.subTest(dependency=key):
                state=b._read_json(state_path)
                manifest=load_run_manifest(manifest_path)
                del manifest['identity'][group][key]
                manifest['run_id']=hashlib.sha256(canonical_json(manifest['identity']).encode()).hexdigest()
                write_run_manifest(manifest,manifest_path)
                report=b._read_json(report_path);report['run_id']=manifest['run_id']
                b._atomic_json(report_path,report)
                seal=state['shards'][0]['features'];seal['run_id']=manifest['run_id']
                for path in [manifest_path,report_path]:
                    seal['fingerprints'][str(path.relative_to(self.root))]=sha256_file(path)
                b._atomic_json(state_path,state)
                approval=deepcopy(self.approval)
                for path in [manifest_path,report_path,state_path]:
                    approval['fingerprints'][str(path.relative_to(self.root))]=sha256_file(path)
                b._atomic_json(self.path,approval)
                try:
                    with self.assertRaisesRegex(ValueError,error):b.verify_collection(self.path)
                finally:
                    manifest_path.write_bytes(original_manifest)
                    report_path.write_bytes(original_report)
                    state_path.write_bytes(original_state)


if __name__=='__main__':unittest.main()
