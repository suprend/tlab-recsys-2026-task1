from copy import deepcopy
import importlib.util
import math
import struct
import unittest
from unittest.mock import patch

from scripts import feature_program_experiment as m
REAL_OBSERVER=m._observer


def candidates():
    return [dict(candidate_id=cid,status='verified_success',added_physical_columns=0 if cid=='B' else 3,
        metrics=dict(conditional_macro_query=dict(ndcg=.5 if cid=='B' else .1,recall=.6))) for cid in m.IDS]


class Selection(unittest.TestCase):
    def test_global_band_lexical_winner_need_not_itself_exceed_B_by_epsilon(self):
        cs=candidates();cs[1]['metrics']['conditional_macro_query']['ndcg']=.5+.75e-12
        cs[4]['metrics']['conditional_macro_query']['ndcg']=.5+1.5e-12
        winner=m.choose(cs)
        self.assertEqual(winner['candidate_id'],'I1')
        self.assertGreater(winner['metrics']['conditional_macro_query']['ndcg'],.5)
        self.assertLessEqual(winner['metrics']['conditional_macro_query']['ndcg']-.5,1e-12)
        # Input ordering cannot turn the global band into a pairwise comparator.
        self.assertEqual(m.choose(cs[::-1])['candidate_id'],'I1')
    def test_B_fewer_physical_columns_wins_global_epsilon_band(self):
        cs=candidates();cs[1]['metrics']['conditional_macro_query']['ndcg']=.5+.5e-12
        self.assertEqual(m.choose(cs)['candidate_id'],'B')
    def test_recall_boundary_inclusive_then_one_float_below_is_infeasible(self):
        cs=candidates();floor=.6-.002
        cs[1]['metrics']['conditional_macro_query']=dict(ndcg=.8,recall=floor)
        self.assertEqual(m.choose(cs)['candidate_id'],'I1')
        cs[1]['metrics']['conditional_macro_query']['recall']=math.nextafter(floor,-math.inf)
        self.assertEqual(m.choose(cs)['candidate_id'],'B')
    def test_random_arm_can_win_and_known_paid_failures_cannot_offer_metrics(self):
        cs=candidates();cs[3]['metrics']['conditional_macro_query']['ndcg']=.9
        self.assertEqual(m.choose(cs)['candidate_id'],'R1')
        cs[3].update(status='resource_failed',metrics=None)
        cs[4].update(status='allocation_collision',metrics=None)
        self.assertEqual(m.choose(cs)['candidate_id'],'B')
        cs[3]['metrics']=dict(conditional_macro_query=dict(ndcg=.99,recall=.6))
        with self.assertRaisesRegex(ValueError,'eligible metrics'):m.choose(cs)
    def test_nonfinite_missing_unknown_and_duplicate_evidence_stops(self):
        for value in [float('nan'),float('inf'),None,True,-.1,1.1]:
            cs=candidates();cs[1]['metrics']['conditional_macro_query']['ndcg']=value
            with self.subTest(value=value),self.assertRaises(ValueError):m.choose(cs)
        for status in ['unattempted','integrity_failure','API_failure','unknown_usage']:
            cs=candidates();cs[1]['status']=status
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,'STOP'):m.choose(cs)
        cs=candidates();cs[-1]['candidate_id']='I1'
        with self.assertRaises(ValueError):m.choose(cs)
        with self.assertRaises(ValueError):m.choose(candidates()[:-1])
    def test_mask_column_counts_are_strict_and_return_does_not_mutate_input(self):
        cs=candidates();cs[1]['added_physical_columns']=2
        with self.assertRaisesRegex(ValueError,'physical'):m.choose(cs)
        cs=candidates();cs[0]['added_physical_columns']=False
        with self.assertRaises(ValueError):m.choose(cs)
        cs=candidates();before=deepcopy(cs);chosen=m.choose(cs);chosen['metrics']['conditional_macro_query']['ndcg']=0
        self.assertEqual(cs,before)


class ProcedureAndBudget(unittest.TestCase):
    def control(self):
        spec=dict(population=26000,trained_iterations=300,scoring_prefix=150,depth=6,l2_leaf_reg=30)
        native=dict(loss_function='Logloss',iterations=300,depth=6,l2_leaf_reg=30,random_seed=2026,task_type='CPU',
            boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,
            leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False,
            learning_rate=struct.unpack('!f',struct.pack('!f',.05))[0],border_count=254,nan_mode='Min',rsm=1)
        return dict(selected_spec=spec,actual_model_parameters=native)
    def test_trained_iterations_not_replaced_by_scoring_prefix(self):
        control=self.control();params=m.frozen_model_parameters(control)
        self.assertEqual(params['iterations'],300);self.assertEqual(control['selected_spec']['scoring_prefix'],150)
        self.assertEqual(params['thread_count'],2);self.assertEqual(params['learning_rate'],.05)
        self.assertFalse(params['use_best_model']);self.assertNotIn('eval_set',params)
        control['selected_spec']['scoring_prefix']=301
        with self.assertRaises(ValueError):m.frozen_model_parameters(control)
    def test_native_int_and_bool_settings_cannot_be_silently_coerced(self):
        for key,value in [('l2_leaf_reg',30.),('random_strength',1.),('boost_from_average',0),('iterations',True),('learning_rate',.1)]:
            control=self.control();control['actual_model_parameters'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.frozen_model_parameters(control)
    def budget(self,prefix=100,self_used=10,children=20,peak=1):
        return m.Budget(prefix,self_cpu=lambda:self_used,children_cpu=lambda:children,rss=lambda:peak,started=0)
    def test_actual_source_prefix_and_reaped_children_charged_once_before_allocation(self):
        b=self.budget()
        with patch.object(m.time,'monotonic',return_value=100):slot=b.allocation()
        self.assertEqual(b.cpu(),130);self.assertEqual(slot['cpu_seconds'],6410)
        self.assertEqual(slot['deadline_monotonic'],2980)
        self.assertLessEqual(b.cpu()+slot['cpu_seconds']+(m.LIMITS['parent_launch_cpu_reserve']-20)+20,6600)
        with patch.object(m.time,'monotonic',return_value=100):larger_reserved_prefix=self.budget(prefix=1800).allocation()
        self.assertEqual(slot['cpu_seconds']-larger_reserved_prefix['cpu_seconds'],1700)
    def test_unknown_cost_expired_clock_resource_and_parent_RSS_stop(self):
        for value in [None,True,float('nan'),-1,1801]:
            with self.subTest(prefix=value),self.assertRaises(ValueError):self.budget(prefix=value)
        with patch.object(m.time,'monotonic',return_value=3001):
            with self.assertRaisesRegex(TimeoutError,'wall'):self.budget().allocation()
        with patch.object(m.time,'monotonic',return_value=100):
            with self.assertRaises(ValueError):self.budget(children=-1).allocation()
            with self.assertRaises(TimeoutError):self.budget(self_used=6600).allocation()
            with self.assertRaises(MemoryError):self.budget(peak=2**30+1).allocation()


class AuthorityAndAdapter(unittest.TestCase):
    def test_issuer_reference_parses_exact_authenticated_snapshot(self):
        import tempfile,json,hashlib
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)):
            path=Path(tmp)/'slot.json';path.write_text('{"cpu_seconds":100}')
            original=hashlib.sha256(path.read_bytes()).hexdigest();ref=dict(path='slot.json',sha256=original)
            self.assertEqual(m._read_ref(ref),dict(cpu_seconds=100))
            path.write_text('{"cpu_seconds":6540}')
            with self.assertRaisesRegex(ValueError,'snapshot differs'):m._read_ref(ref)
    def test_issuer_context_snapshot_cannot_be_resealed_by_an_earlier_hash_read(self):
        import tempfile,hashlib,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'context.json';path.write_text('{"version":1,"parent_plan":{},"slot":{}}')
            digest=hashlib.sha256(path.read_bytes()).hexdigest();path.write_text('{"version":1,"parent_plan":{},"slot":{},"swapped":true}')
            with patch.object(m,'_sha',return_value=digest):
                with self.assertRaisesRegex(ValueError,'issuer snapshot'):m.verify_worker_context(path,issued_context_sha256=digest)
    def test_published_selector_bytes_match_prospective_contract(self):
        import json
        from pathlib import Path
        selector=json.loads((Path(m.__file__).resolve().parents[1]/'configs/features/automation-selection.json').read_text())
        self.assertEqual(m.validate_selector(selector),selector)
        bad=deepcopy(selector);bad['tie']['order']=['fewer_trees','cpu_time']
        with self.assertRaisesRegex(ValueError,'published contract'):m.validate_selector(bad)
    def test_typed_three_column_adapter_and_matrix_witness_on_native_tiny_F57(self):
        from tests.test_program_model_data import ProgramModelDataTests
        from scripts import program_model_data as loader,train_baselines as base
        import numpy as np
        fixture=ProgramModelDataTests('test_every_B_query_key_target_value_preserved_and_only_three_columns_added')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        names=[field['name'] for field in fixture.delta];types={field['name']:field['dtype'] for field in fixture.delta}
        typed=[dict(name=n,dtype=types[n]) for n in names]
        merged=loader.append_program_features(fixture.data,['export.parquet'],extra_columns=typed,expected_source_schema=fixture.schema)
        self.assertEqual(merged.feature_names,[*fixture.data.feature_names,*names]);np.testing.assert_array_equal(merged.x[:,:41],fixture.data.x)
        _,_,_,_,weights,_=base.group_accounting(merged)
        proof=m.matrix_proof(merged,weights=weights);self.assertEqual(proof,m.matrix_proof(merged,weights=weights))
        self.assertEqual(proof['query_count'],3);self.assertEqual(proof['arrays']['x']['shape'],[2,44])
        before=m.matrix_proof(merged);merged.x[0,-1]=1
        self.assertNotEqual(before,m.matrix_proof(merged))
        with self.assertRaisesRegex(ValueError,'physical delta'):
            loader.append_program_features(fixture.data,['export.parquet'],extra_columns=names,expected_source_schema=fixture.schema)
    def test_allclose_alone_cannot_prove_saved_prefix_ranking_fidelity(self):
        from datetime import datetime
        import numpy as np
        from scripts import train_baselines as base
        data=base.Prepared([('q',1,datetime(2019,10,23),frozenset({1}))],np.array([0,0],np.int32),
            np.array([1,2],np.int64),np.zeros((2,1),np.float32),np.array([1,0],np.int8),['f'])
        original=np.array([0.,0.]);saved=np.array([-5e-13,0.])
        self.assertTrue(np.allclose(original,saved,rtol=0,atol=1e-12))
        self.assertNotEqual(base.rankings(data,original),base.rankings(data,saved))


class OwnerLifecycle(unittest.TestCase):
    """Actual owner/claim/filesystem; worker/observer/authority are explicit fakes."""
    def setUp(self):
        import tempfile,json,hashlib
        from pathlib import Path
        self.Path=Path;self.json=json;tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        def change(obj,name,value):
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        change(m,'ROOT',self.root);change(m.time,'monotonic',lambda:m.ENTRY_MONOTONIC+100)
        change(m,'_self_cpu',lambda:1.);change(m,'_children_cpu',lambda:0.);change(m,'_rss',lambda:64)
        self.source=self.root/'source.json';self.control=self.root/'control.json';self.selector=self.root/'selector.json';self.approval=self.root/'approval.json'
        for path in [self.source,self.control,self.selector]:path.write_text('{}\n')
        (self.root/'input').write_bytes(b'approved tiny input')
        names=['f'+str(i) for i in range(41)];self.metrics=dict(conditional_macro_query=dict(ndcg=.5,recall=.6))
        identity=dict(source_run_id='d'*64,role=m.ROLE,limits=deepcopy(m.LIMITS),fingerprints={'input':m._sha(self.root/'input')},
            paid_source_cpu_seconds=177.72,baseline=dict(candidate_id='B',status='verified_success',added_physical_columns=0,metrics=deepcopy(self.metrics)),
            model_spec=dict(population=26000,trained_iterations=300,scoring_prefix=300,depth=6,l2_leaf_reg=30),
            slots={cid:dict(candidate_id=cid,bundle_id=bundle,columns=['auto_'+cid.lower()+str(i) for i in range(3)],
                physical_delta=[dict(name='auto_'+cid.lower()+str(i),dtype='BIGINT') for i in range(3)],
                feature_names=names+['auto_'+cid.lower()+str(i) for i in range(3)]) for cid,bundle in zip(m.IDS[1:],['L02','L06','L01','L05'])},
            oracle_source=dict(path='tests/oracles/fake.py',sha256='a'*64))
        self.plan=dict(identity=identity,run_id=m._digest(identity));self.plan_calls=[];self.worker_calls=[];self.observer_calls=[];self.failure_slot=None
        def prepare(*args,**kwargs):
            self.plan_calls.append(True);self.assertTrue((self.root/m.OWNER_CLAIM).exists());return deepcopy(self.plan)
        change(m,'prepare_plan',prepare)
        native=m._write
        def write(path,body):
            native(path,body)
            if path.name=='proposal.json':
                self.approval.write_text(m._canonical(dict(version=1,approved=True,scope=m.ROLE,run_id=body['run_id'],fingerprints=body['identity']['fingerprints']))+'\n')
        change(m,'_write',write);change(m,'_invoke_worker',self.fake_worker);change(m,'_observer',self.fake_observer)
    def fake_worker(self,directory,parent,slot,path,issued,budget):
        cid=slot['candidate_id'];self.worker_calls.append(cid);self.assertTrue((self.root/m.CLAIM).exists())
        context=m._read(path)[0];out=directory/'workers'/cid/'fixture';out.mkdir(parents=True)
        isfailed=cid==self.failure_slot;metrics=deepcopy(self.metrics)
        report=dict(candidate_id=cid,fit_attempt_count=0 if isfailed else 1,look_reservations=[dict(status='reserved_consumed' if isfailed else 'seen_complete')],
            process_peak_rss_bytes=int(7.1*2**30) if isfailed else 128,status='failed' if isfailed else 'complete_produced_unreviewed',
            outcome='resource_failure' if isfailed else 'arm_complete')
        if isfailed:m._write(out/'report.failed.json',report)
        candidate=dict(candidate_id=cid,status='resource_failed' if isfailed else 'verified_success',added_physical_columns=3,metrics=None if isfailed else metrics)
        for name in ['run.json','report.json']:m._write(out/name,report)
        launch=directory/'logs'/(cid+'.launch.json');m._exclusive_json(launch,{'synthetic':True})
        ref=lambda p:dict(path=m._relative(p),sha256=m._sha(p))
        return dict(slot=context['slot'],context=ref(path),exit_code=1 if isfailed else 0,actual_reaped_cpu_seconds=0.,
            report=ref(out/'report.json'),manifest=ref(out/'run.json'),launch=ref(launch),worker_report=report,candidate=candidate)
    def fake_observer(self,directory,parent,producer,budget):
        self.observer_calls.append(True);budget.verifying=True;claim=m._read(self.root/m.CLAIM)[0]
        self.assertEqual(claim['allowed_observer_attempts'],1);self.assertEqual(claim['allowed_fit_attempts'],4)
        self.assertEqual(producer['source_paid_cpu_seconds'],177.72)
        out=directory/'observer';out.mkdir();m._write(out/'evidence.json',dict(status='synthetic_not_a_real_proof'))
        return dict(authority_pins={},process_peak_rss_bytes=128,paired_bootstrap={},proof_limits='Synthetic owner-plumbing test; no actual proof or fits')
    def run_owner(self):return m.run_owner(self.source,self.control,self.selector,self.approval)
    def test_exact_four_original_slots_one_observer_and_repeat_stops_before_paid_plan(self):
        report=self.run_owner();self.assertEqual(self.worker_calls,list(m.IDS[1:]));self.assertEqual(self.observer_calls,[True])
        self.assertEqual(report['fit_attempt_count'],4);self.assertEqual(report['sum_metric_looks'],4)
        self.assertEqual(report['status'],'model_outputs_verified_pending_external_acceptance');self.assertEqual(report['winner']['candidate_id'],'B')
        self.assertAlmostEqual(report['charged_study_cpu_seconds'],178.72)
        with self.assertRaises(FileExistsError):self.run_owner()
        self.assertEqual(self.plan_calls,[True]);self.assertEqual(self.worker_calls,list(m.IDS[1:]))
    def test_failed_paid_preflight_consumes_owner_attempt_and_persists_failure(self):
        def failure(*args,**kwargs):self.plan_calls.append(True);raise TimeoutError('synthetic paid input preflight')
        with patch.object(m,'prepare_plan',side_effect=failure):
            with self.assertRaisesRegex(TimeoutError,'paid input'):self.run_owner()
            with self.assertRaises(FileExistsError):self.run_owner()
        self.assertEqual(self.plan_calls,[True]);self.assertEqual(self.worker_calls,[]);self.assertTrue((self.root/m.OWNER_CLAIM).exists())
        files=list((self.root/'artifacts/feature-program-invocations').glob('*/report.failed.json'));self.assertEqual(len(files),2)
    def test_known_failed_original_slot_retained_paid_without_replacement(self):
        self.failure_slot='I1';report=self.run_owner()
        self.assertEqual(self.worker_calls,list(m.IDS[1:]));self.assertEqual(report['fit_attempt_count'],3)
        self.assertEqual(report['candidates'][1]['status'],'resource_failed');self.assertIsNone(report['candidates'][1]['metrics'])
        self.assertEqual(report['winner']['candidate_id'],'B')
    def test_late_oracle_failed_marker_after_pin_checks_never_returns_pending_success(self):
        native=m._sha;fired=[]
        def poison(path,check=lambda:None):
            result=native(path,check)
            if self.observer_calls and Path(path).name=='run.json' and not fired:
                fired.append(True);directory=next((self.root/'artifacts/feature-program-invocations').iterdir())
                (directory/'observer/evidence.failed.json').write_text('{"status":"failed"}')
            return result
        from pathlib import Path
        with patch.object(m,'_sha',side_effect=poison):
            with self.assertRaisesRegex(RuntimeError,'Late known'):self.run_owner()
        self.assertEqual(fired,[True]);failed=next((self.root/'artifacts/feature-program-invocations').glob('*/report.failed.json'))
        self.assertEqual(self.json.loads(failed.read_text())['status'],'failed')

    def test_late_successful_worker_failure_marker_never_returns_eligible_study(self):
        native=self.fake_observer
        def poison(directory,parent,producer,budget):
            result=native(directory,parent,producer,budget);worker=self.root/producer['children'][0]['report']['path']
            worker.with_name('report.failed.json').write_text('{"status":"failed"}')
            return result
        with patch.object(m,'_observer',side_effect=poison):
            with self.assertRaisesRegex(RuntimeError,'successful worker'):self.run_owner()
        failed=next((self.root/'artifacts/feature-program-invocations').glob('*/report.failed.json'))
        self.assertEqual(self.json.loads(failed.read_text())['status'],'failed')
    def test_missing_child_receipt_preserves_unknown_fit_and_look_counts(self):
        def missing(directory,parent,slot,path,issued,budget):
            report=self.json.loads((directory/'report.json').read_text())
            self.assertTrue(report['unknown_live_fit']);self.assertTrue(report['unknown_metric_looks']);self.assertEqual(report['active_slot']['candidate_id'],'I1')
            (directory/'synthetic-fit-start-witness').write_text('A child may have started; no actual native fit')
            raise RuntimeError('synthetic missing child receipt')
        with patch.object(m,'_invoke_worker',side_effect=missing):
            with self.assertRaisesRegex(RuntimeError,'missing child'):self.run_owner()
        failed=next((self.root/'artifacts/feature-program-invocations').glob('*/report.failed.json'))
        report=self.json.loads(failed.read_text());self.assertTrue(report['unknown_live_fit']);self.assertTrue(report['unknown_metric_looks'])
        self.assertIsNone(report['fit_attempt_count']);self.assertIsNone(report['sum_metric_looks'])
        self.assertEqual(report['known_fit_attempt_lower_bound'],0);self.assertEqual(report['known_metric_look_lower_bound'],0)


class ObserverAuthorityLifecycle(OwnerLifecycle):
    # Inherited setup is intentional; execute only the newly defined cases once.
    test_exact_four_original_slots_one_observer_and_repeat_stops_before_paid_plan=None
    test_failed_paid_preflight_consumes_owner_attempt_and_persists_failure=None
    test_known_failed_original_slot_retained_paid_without_replacement=None
    test_late_oracle_failed_marker_after_pin_checks_never_returns_pending_success=None
    test_late_successful_worker_failure_marker_never_returns_eligible_study=None
    test_missing_child_receipt_preserves_unknown_fit_and_look_counts=None
    def setUp(self):
        super().setUp();self.native_observer=m._observer
        # m._observer is patched by the parent setup; recover the actual method
        # from the source module's globals retained before patching below.
        self.native_observer=REAL_OBSERVER
        entry=self.root/self.plan['identity']['oracle_source']['path'];entry.parent.mkdir(parents=True);entry.write_text('# explicit fake child, no native jobs\n')
        self.plan['identity']['oracle_source']['sha256']=m._sha(entry)
    def fake_native_child(self,argv,log,**kwargs):
        context_path=self.Path(argv[argv.index('--context')+1]);context=m._read(context_path)[0]
        producer=m._read(self.root/context['producer_report']['path'])[0]
        evidence=dict(version=1,status='verified',scope=m.ROLE+'_independent_model_output_observer',run_id=context['run_id'],source_run_id='d'*64,
            context_sha256=m._sha(context_path),request=context['request'],producer_manifest=context['producer_manifest'],producer_report=context['producer_report'],
            oracle_source=context['oracle_source'],fit_attempt_count=0,observer_refits=0,source_regenerations=0,allocated_slots=4,checked_slots=list(m.IDS[1:]),
            candidate_records=producer['candidates'],winner=producer['winner'],worker_proofs={child['worker_report']['candidate_id']:{name:child[name] for name in ['report','manifest','slot','context','launch']} for child in producer['children']},
            process_cpu_seconds=0.,reaped_children_cpu_seconds=0,process_peak_rss_bytes=128,started_monotonic=context['issued_at_monotonic'],finished_monotonic=context['issued_at_monotonic'],
            paired_bootstrap={},proof_limits='Synthetic parent-authority test only; not a real independent proof')
        request=m._read(self.root/context['request']['path'])[0]
        consumed=self.root/context['invocation_directory']/'execution.consumed.json'
        digest=m._exclusive_json(consumed,dict(version=1,scope=context['scope']+'_execution_consumed',run_id=context['run_id'],
            context_sha256=evidence['context_sha256'],request=context['request'],original_four_fit_claim=request['budget_claim'],
            oracle_source=context['oracle_source'],observer_calls=1,refits=0,source_regenerations=0))
        evidence['execution_consumed']=dict(path=m._relative(consumed),sha256=digest)
        m._write(self.root/context['output_path'],evidence);self.Path(log).write_text('explicit fake child\n')
        if getattr(self,'mutate_request',False):
            request=self.root/context['request']['path'];request.write_bytes(request.read_bytes()+b' ')
        return 0
    def test_original_request_mutation_rejects_after_fake_child_exit(self):
        from scripts import strong_baseline as lifecycle
        self.mutate_request=True
        with patch.object(m,'_observer',side_effect=self.native_observer),patch.object(lifecycle,'run_process',side_effect=self.fake_native_child):
            with self.assertRaisesRegex(ValueError,'Pinned experiment'):self.run_owner()
        failed=next((self.root/'artifacts/feature-program-invocations').glob('*/report.failed.json'))
        self.assertEqual(self.json.loads(failed.read_text())['status'],'failed')
    def test_terminal_request_mutation_after_observer_return_rejects(self):
        from scripts import strong_baseline as lifecycle
        original=self.native_observer;returned=[];native=m._sha
        def checked(*args,**kwargs):
            result=original(*args,**kwargs);returned.append(True);return result
        poisoned=[]
        def poison(path,check=lambda:None):
            digest=native(path,check)
            if returned and self.Path(path).name=='producer-report.json' and not poisoned:
                poisoned.append(True);request=self.Path(path).parent/'observer/request.json';request.write_bytes(request.read_bytes()+b' ')
            return digest
        with patch.object(m,'_observer',side_effect=checked),patch.object(lifecycle,'run_process',side_effect=self.fake_native_child),patch.object(m,'_sha',side_effect=poison):
            with self.assertRaisesRegex(ValueError,'Pinned experiment'):self.run_owner()
        self.assertEqual(poisoned,[True])


class DurableIssuance(unittest.TestCase):
    def test_exclusive_json_fsyncs_file_and_directory_and_retains_written_snapshot(self):
        import tempfile,json,hashlib
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'claim.json'
            native=m.os.fsync;seen=[]
            def sync(fd):seen.append(fd);return native(fd)
            with patch.object(m.os,'fsync',side_effect=sync):digest=m._exclusive_json(path,{'once':True})
            self.assertEqual(digest,hashlib.sha256(path.read_bytes()).hexdigest());self.assertEqual(len(seen),2)
            with self.assertRaises(FileExistsError):m._exclusive_json(path,{'once':False})
            self.assertEqual(json.loads(path.read_text()),{'once':True})


class NativeWorkerBoundary(unittest.TestCase):
    def test_native_matrices_weights_keys_prefix_and_one_look_with_explicit_fake_model(self):
        """Native Q/F/Y transport; no actual CatBoost fit or native model file."""
        import json,sys
        from pathlib import Path
        import numpy as np
        import catboost
        from tests.test_program_model_data import ProgramModelDataTests
        from scripts import metadata_price_collection as mechanics
        fixture=ProgramModelDataTests('test_every_B_query_key_target_value_preserved_and_only_three_columns_added')
        fixture.setUp();self.addCleanup(fixture.doCleanups);root=fixture.root;con=fixture.con
        # Exactly inherited6000 Q for this generic legacy-control fixture;4000 selection.
        # Only two candidate rows: the other queries exercise emptyC/fullY domains.
        con.execute("INSERT INTO q SELECT 'extra'||lpad(i::VARCHAR,5,'0'),10000+i,TIMESTAMP '2019-10-25',true FROM range(5997) r(i)")
        con.execute('COPY q TO ? (FORMAT PARQUET)',[str(root/'train-q.parquet')])
        con.execute('COPY (SELECT * FROM q ORDER BY query_id LIMIT 4000) TO ? (FORMAT PARQUET)',[str(root/'selection-q.parquet')])
        cols=fixture.collection['feature_columns']
        collections={role:dict(phase=dict(role=role),feature_columns=cols,
            refs=dict(queries=[role+'-q.parquet'],features=['f.parquet'],labels=['y.parquet']),
            plan=dict(collection_id=role+'-fixed')) for role in ['train','selection']}
        control=ProcedureAndBudget().control();control['selected_spec']['population']=6000
        native=dict(control['actual_model_parameters'],eval_metric='Logloss',auto_class_weights='None',grow_policy='SymmetricTree',feature_border_type='GreedyLogSum')
        names=fixture.data.feature_names;delta=fixture.delta;added=[f['name'] for f in delta]
        # Fixture source uses legitimate auto_test_* fields; no production source proof is claimed.
        arm=dict(candidate_id='I1',bundle_id='fixture',columns=added,physical_delta=delta,feature_names=[*names,*added])
        (root/'input').write_text('bound synthetic input')
        def ref(name,value):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,sort_keys=True)+'\n')
            return dict(path=name,sha256=m._sha(path))
        parentref=ref('plan.json',{'synthetic':'parent'});slotref=ref('slot.json',{'synthetic':'slot'})
        approval=ref('approval.json',{'synthetic':'authority'});claim=ref('claim.json',{'synthetic':'fourfits'})
        context=dict(version=1,parent_plan=parentref,slot=slotref);contextref=ref('context.json',context)
        identity=dict(model_spec=control['selected_spec'],model_parameters=m.frozen_model_parameters(control),native_reference=native,
            feature_names=names,slots={'I1':arm},fingerprints={'input':m._sha(root/'input')},accepted_base_refs={'train':'train','selection':'selection'},
            collection_ids={r:r+'-fixed' for r in collections},daily_features={r:['export.parquet'] for r in collections},
            expected_source_schema=fixture.schema,environment={'synthetic':'runtime'})
        parent=dict(run_id='a'*64,identity=identity,execution_approval=approval,budget_claim=claim)
        slot=dict(candidate_id='I1',token='b'*32,allocation=dict(cpu_seconds=1000,deadline_monotonic=m.ENTRY_MONOTONIC+1000,rss_bytes=7*2**30),output_root='worker')
        calls=[];pools=[];models=[]
        class FakePool:
            def __init__(self,x,**kwargs):self.x=x;self.kwargs=kwargs;pools.append(self)
        class FakeModel:
            def __init__(self,**kwargs):self.kwargs=kwargs;self.tree_count_=0;self.feature_names_=[];models.append(self)
            def fit(self,pool,**kwargs):
                calls.append((pool,kwargs));self.tree_count_=self.kwargs['iterations'];self.feature_names_=list(pool.kwargs['feature_names']);return self
            def get_all_params(self):return deepcopy(native)
            def save_model(self,path,format=None):
                body={'oblivious_trees':[{'splits':[]} for _ in range(self.tree_count_)],'features_info':{}} if format=='json' else dict(synthetic=True,trees=self.tree_count_,features=self.feature_names_)
                Path(path).write_text(json.dumps(body))
            def copy(self):
                copied=FakeModel(**self.kwargs);copied.tree_count_=self.tree_count_;copied.feature_names_=self.feature_names_.copy();return copied
            def shrink(self,k):self.tree_count_=k
            def load_model(self,path):
                body=json.loads(Path(path).read_text());self.tree_count_=body['trees'];self.feature_names_=body['features'];return self
            def predict(self,x,**kwargs):return np.arange(len(x),0,-1,dtype=np.float64)
        with patch.object(m,'ROOT',root),patch.object(m.time,'monotonic',return_value=m.ENTRY_MONOTONIC+100),            patch.object(m,'_self_cpu',return_value=1.),patch.object(m,'_children_cpu',return_value=0.),patch.object(m,'_rss',return_value=64),            patch.object(m,'verify_worker_context',return_value=(parent,slot,context)),            patch.object(m,'verify_environment',return_value={'synthetic':'loaded runtime boundary intentionally stubbed'}),            patch.object(mechanics,'verify_collection_strict',side_effect=lambda path,**kwargs:collections[path.name]),            patch.object(catboost,'CatBoostClassifier',FakeModel),patch.object(catboost,'Pool',FakePool):
            report=m.worker_main(root/'context.json',issued_context_sha256=contextref['sha256'])
        self.assertEqual(len(calls),1);self.assertEqual(set(calls[0][1]),{'callbacks'})
        self.assertEqual(models[0].kwargs['iterations'],300);self.assertFalse(models[0].kwargs['use_best_model']);self.assertEqual(models[0].kwargs['thread_count'],2)
        pool=pools[0];self.assertEqual(pool.x.shape,(2,44));self.assertEqual(pool.kwargs['label'].tolist(),[1,0])
        self.assertEqual(pool.kwargs['weight'].tolist(),[1.,1.]);self.assertEqual(pool.kwargs['feature_names'],names+added)
        self.assertEqual(report['fit_attempt_count'],1);self.assertEqual(len(report['look_reservations']),1)
        self.assertEqual(report['look_reservations'][0]['prefix'],150);self.assertEqual(report['metrics']['query_count'],4000)
        self.assertEqual(report['train_matrix_proof']['query_count'],6000);self.assertEqual(report['selection_matrix_proof']['query_count'],4000)
        self.assertEqual(set(Path(p).name for p in report['artifacts']),{'full.cbm','full.json','prefix.cbm','scores.npz'})
        with np.load(root/report['score_path'],allow_pickle=False) as data:
            self.assertEqual(set(data.files),{'group','product_id','raw_score'});self.assertEqual(data['group'].dtype,np.int32)
            self.assertEqual(data['product_id'].dtype,np.int64);self.assertEqual(int(data['product_id'][0]),9007199254740993)
            self.assertEqual(data['raw_score'].dtype,np.float64)


if __name__=='__main__':unittest.main()
