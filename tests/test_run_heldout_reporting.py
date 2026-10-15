"""Owner preparation seams with tiny synthetic files and mocked439 authenticator.

No historical data hash stream, reserved relation, process, native or fit runs.
"""
from copy import deepcopy
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import run_heldout_reporting as m
from scripts import feature_program_control as control
from scripts import feature_programs as programs
from tests.test_heldout_contract import fixture

PROJECT=Path(__file__).resolve().parents[1]


class OwnerFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.root_patch=patch.object(m,'ROOT',self.root);self.root_patch.start()
        self.resource_patch=patch.object(m.x,'counters',return_value=(.1,0,1024));self.resource_patch.start()
        self.budget=m.x.Budget(started=time.monotonic());self.consumer_calls=[]
        self.refs={}
        for name in m.CODE:self.write(name,{'synthetic_code_only':name})
        self.registry=json.loads((PROJECT/m.SOURCE_INPUTS['registry']).read_text());self.contract=json.loads((PROJECT/m.SOURCE_INPUTS['pool']).read_text())
        self.write(m.SOURCE_INPUTS['source'],{'not_a_database':'synthetic bytes only'});self.write(m.SOURCE_INPUTS['pool'],self.contract);self.write(m.SOURCE_INPUTS['registry'],self.registry)
        lock,self.choice,*_=fixture('R2');pool=programs.generate_pool(self.contract,self.registry);allocation=programs.allocate_slots(pool)
        bundle=next(b for b in pool['identity']['bundles'] if b['bundle_id']==next(s['bundle_id'] for s in allocation['identity']['slots'] if s['slot']=='R2'))
        self.choice['models']['B']['feature_names']=[field['name'] for field in pool['identity']['base_model_schema']]
        self.choice['models']['W']['feature_names']=list(bundle['model_feature_order'])
        self.choice['authority_refs']['pool']=self.reference(m.SOURCE_INPUTS['pool'])
        self.write('artifacts/test/model-acceptance.json',{'synthetic_authentication_stub':True})
        self.write(m.POLICY,m.h.POLICY)
        for row in lock['compute_evidence']:self.write(row['receipt']['path'],{'synthetic_compute_receipt':row['stage']});row['receipt']=self.reference(row['receipt']['path'])
        self.write('artifacts/test/compute-evidence.json',lock['compute_evidence'])
        self.request=dict(version=1,scope='prospective_reserved_reporting_owner',owner_source=self.reference(m.OWNER),policy=self.reference(m.POLICY),
            model_acceptance=self.reference('artifacts/test/model-acceptance.json'),compute_evidence=self.reference('artifacts/test/compute-evidence.json'),
            code_fingerprints={name:self.reference(name)['sha256'] for name in m.CODE},role_entries={role:self.reference(path) for role,path in m.x.ENTRY.items()},
            authority_paths={key:'artifacts/acceptance/'+key+'.json' for key in sorted(m.AUTHORITY_KEYS)},
            source_inputs={name:self.reference(path) for name,path in m.SOURCE_INPUTS.items()})
        self.request_path=self.write('artifacts/test/request.json',self.request)
        self.historical={ref['path']:ref['sha256'] for ref in self.request['source_inputs'].values()}
        self.historical.update({self.request['model_acceptance']['path']:self.request['model_acceptance']['sha256']})
        self.consumer_patch=patch.object(control,'verify_choice',self.verify_choice);self.consumer_patch.start()
    def tearDown(self):self.consumer_patch.stop();self.resource_patch.stop();self.root_patch.stop();self.temp.cleanup()
    def write(self,name,body):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(m.x.canonical(body)+'\n');return path
    def reference(self,name):return dict(path=name,sha256=m.x.sha(self.root/name))
    def verify_choice(self,path,*,check):
        self.assertTrue((self.root/m.CLAIM).exists());check();self.consumer_calls.append(path)
        return dict(acceptance=deepcopy(self.request['model_acceptance']),pins=deepcopy(self.historical),authenticated_choice=deepcopy(self.choice))
    def consume(self):return m.consume_owner(self.request_path,self.budget)


class OwnerPreparationTests(OwnerFixture,unittest.TestCase):
    def test_claim_precedes_paid_authentication_and_lock_proposal_projection_hashes(self):
        consumed=self.consume();self.assertEqual(self.consumer_calls,[]);result=m.prepare_owner(consumed,self.budget)
        self.assertEqual(len(self.consumer_calls),1);self.assertEqual(result['plan']['run_id'],m.h.digest(result['proposal']['identity']))
        self.assertEqual(set(result['proposal']),{'run_id','identity'});m.h.validate_lock(result['lock'],authenticated_choice=self.choice)
        self.assertLessEqual(m.h.utc(result['lock']['sealed_at']),m.h.utc(m.now()));self.assertEqual(len(result['selected']['extra_schema']),3)
        self.assertIn(result['proposal_ref']['path'],result['plan']['fingerprints']);self.assertNotIn(result['proposal_ref']['path'],result['proposal']['identity']['fingerprints'])
        claim,_=m.x.read(self.root/m.CLAIM);self.assertEqual(set(claim),{'version','scope','request','owner_source','output_directory','started_monotonic','original_deadline_monotonic'})
        self.assertEqual(claim['scope'],'reserved_reporting_owner_attempt')
    def test_second_output_root_or_request_cannot_refill_global_claim(self):
        self.consume();other=self.write('artifacts/test/alternate-request.json',self.request)
        with self.assertRaises(FileExistsError):m.consume_owner(other,self.budget)
        self.assertEqual(self.consumer_calls,[])
    def test_malformed_parsed_request_consumes_before_failed_preparation(self):
        self.write('artifacts/test/request.json',{'wrong':'shape'});consumed=self.consume()
        with self.assertRaises(ValueError):m.prepare_owner(consumed,self.budget)
        self.assertTrue((self.root/m.CLAIM).exists());self.assertEqual(self.consumer_calls,[])
    def test_mutated_original_request_is_not_resealed_by_preparation(self):
        consumed=self.consume();self.write('artifacts/test/request.json',{'changed':True})
        with self.assertRaises(ValueError):m.prepare_owner(consumed,self.budget)
        self.assertEqual(self.consumer_calls,[])
    def test_changed_owner_or_transitive_code_rejected_before_paid_authentication(self):
        consumed=self.consume();self.write('scripts/temporal_contract.py',{'changed':True})
        with self.assertRaisesRegex(ValueError,'input changed'):m.prepare_owner(consumed,self.budget)
        self.assertEqual(self.consumer_calls,[])
    def test_arbitrary_entry_and_missing_dependency_and_bool_version_reject(self):
        for kind in ['entry','code','bool']:
            request=deepcopy(self.request)
            if kind=='entry':request['role_entries']['source']['path']='arbitrary.py'
            elif kind=='code':request['code_fingerprints'].pop('scripts/ranking_metrics.py')
            else:request['version']=True
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.validate_request(request)
    def test_preissued_authority_cannot_create_a_fresh_plan(self):
        consumed=self.consume();self.write(self.request['authority_paths']['initial_execution'],{'approved':True})
        with self.assertRaisesRegex(ValueError,'pre-issued'):m.prepare_owner(consumed,self.budget)
        self.assertEqual(self.consumer_calls,[])
    def test_wrong_original_source_hash_or_pool_authority_rejects(self):
        consumed=self.consume();self.historical[m.SOURCE_INPUTS['source']]='b'*64
        with self.assertRaisesRegex(ValueError,'historical439'):m.prepare_owner(consumed,self.budget)
    def test_compute_receipt_bytes_are_bound_not_assumed_from_self_authored_list(self):
        consumed=self.consume();evidence=json.loads((self.root/'artifacts/test/compute-evidence.json').read_text());self.write(evidence[0]['receipt']['path'],{'changed':True})
        with self.assertRaisesRegex(ValueError,'input changed'):m.prepare_owner(consumed,self.budget)
    def test_overlarge_declared_compute_allowance_rejects(self):
        consumed=self.consume();original=m.read_ref
        def reader(ref,check):
            value=original(ref,check)
            if ref==self.request['compute_evidence']:value[0]['declared_unmeasured_wall_upper_seconds']=43201
            return value
        with patch.object(m,'read_ref',reader),self.assertRaisesRegex(ValueError,'allowance'):m.prepare_owner(consumed,self.budget)
    def test_prior_child_usage_is_not_erased_by_new_budget_object(self):
        with patch.object(m.x,'counters',return_value=(.1,.01,1024)),self.assertRaisesRegex(ValueError,'previous reaped children'):self.consume()
        self.assertFalse((self.root/m.CLAIM).exists())
    def test_guard_before_claim_does_not_invent_consumption_or_paid_work(self):
        with patch.object(self.budget,'guard',side_effect=TimeoutError('stop')),self.assertRaises(TimeoutError):self.consume()
        self.assertFalse((self.root/m.CLAIM).exists());self.assertEqual(self.consumer_calls,[])
    def test_reference_paths_and_four_distinct_authority_destinations_fail_closed(self):
        request=deepcopy(self.request);request['authority_paths']['target_execution']=request['authority_paths']['initial_execution']
        with self.assertRaises(ValueError):m.validate_request(request)
        request=deepcopy(self.request);request['source_inputs']['source']['path']='../outside.db'
        with self.assertRaises(ValueError):m.validate_request(request)
    def test_detached_owner_claim_or_reset_lifetime_rejected_before_paid_consumer(self):
        consumed=self.consume();changed=deepcopy(consumed)
        changed['directory']=self.root/'artifacts/heldout-invocations/alternate'
        with self.assertRaisesRegex(ValueError,'association'):m.prepare_owner(changed,self.budget)
        changed=deepcopy(consumed);changed['request']['version']=2
        with self.assertRaisesRegex(ValueError,'memory'):m.prepare_owner(changed,self.budget)
        with patch.object(self.budget,'started',self.budget.started+.01),self.assertRaisesRegex(ValueError,'association'):m.prepare_owner(consumed,self.budget)
        self.assertEqual(self.consumer_calls,[])
    def test_failed_paid_authentication_cannot_retry_same_consumed_preparation(self):
        consumed=self.consume();original=self.verify_choice
        def fail(path,*,check):original(path,check=check);raise ValueError('original authentication failure')
        with patch.object(control,'verify_choice',fail),self.assertRaisesRegex(ValueError,'original authentication'):m.prepare_owner(consumed,self.budget)
        with self.assertRaises(FileExistsError):m.prepare_owner(consumed,self.budget)
        self.assertEqual(len(self.consumer_calls),1)
    def test_inside_root_symlink_gate_aliases_reject_before_paid_authentication(self):
        target=self.root/'artifacts/acceptance/shared';target.mkdir(parents=True)
        request=deepcopy(self.request)
        for index,name in enumerate(sorted(m.AUTHORITY_KEYS)):
            alias=self.root/'artifacts/acceptance'/('alias'+str(index));alias.symlink_to(target,target_is_directory=True)
            request['authority_paths'][name]='artifacts/acceptance/alias'+str(index)+'/gate.json'
        self.write('artifacts/test/request.json',request);consumed=self.consume()
        with self.assertRaisesRegex(ValueError,'Canonical physical|physically distinct'):m.prepare_owner(consumed,self.budget)
        self.assertEqual(self.consumer_calls,[])
    def test_conflicting_original_pin_maps_do_not_silently_overwrite(self):
        with self.assertRaisesRegex(ValueError,'Conflicting'):m.merge({'file':'a'*64},{'file':'b'*64})



    def test_one_inside_root_gate_alias_rejected_before_paid_authentication(self):
        target=self.root/'artifacts/acceptance/physical';target.mkdir(parents=True)
        alias=self.root/'artifacts/acceptance/alias';alias.symlink_to(target,target_is_directory=True)
        request=deepcopy(self.request);request['authority_paths']['initial_execution']='artifacts/acceptance/alias/initial.json'
        self.write('artifacts/test/request.json',request);consumed=self.consume()
        with self.assertRaisesRegex(ValueError,'Canonical physical'):m.prepare_owner(consumed,self.budget)
        self.assertEqual(self.consumer_calls,[])


def source_evidence(choice='R2'):
    """Literal metadata fixture, not a source/formula execution or acceptance."""
    columns=0 if choice=='B' else 3;days=[];reports=[]
    for index,anchor in enumerate(m.h.DAYS):
        count=0 if index==6 else 3
        ref=lambda stem:dict(path='artifacts/toy/source/day-'+anchor[8:10]+'/'+stem+'.parquet',sha256='a'*64)
        days.append(dict(anchor=anchor,queries=ref('queries'),candidates=ref('candidates'),base_features=ref('base-features'),
            extra_features=None if choice=='B' else ref('extra-features'),query_count=2,candidate_count=count,mature_query_count=2))
        reports.append(dict(anchor=anchor,query_count=2,candidate_count=count,mature_query_count=2,empty_candidate_queries=2 if not count else 0,
            chosen_columns=columns,chosen_scalar_values=columns*count,source_Q_C_complete=True,metadata_ages_coverage_complete=True,
            chosen_formula_values_complete=True,base_core18_sample_pairs=count,base_core18_comparisons=18*count,
            strata={name:dict(available_pairs=count if name=='bottom_hash' else 0,sampled_pairs=min(limit,count) if name=='bottom_hash' else 0) for name,limit in m.SAMPLE_STRATA.items()},
            base_proof_scope='all_structure_metadata_coverage_core18_sampled',baseline_formula_values_complete=False,
            labels_loaded=False,target_relation_created=False,fit_attempt_count=0,native_prediction_count=0))
    total=sum(row['candidate_count'] for row in days)
    core=dict(version=1,status='source_core_checked_pending_external_acceptance',scope='independent_reserved_source_core',choice=choice,
        checked_days=list(m.h.DAYS),days=reports,verified_outputs=deepcopy(days),source_Q_C_domain_complete=True,chosen_columns=columns,
        chosen_scalar_values=columns*total,chosen_formula_values_complete=True,
        extra_proof_scope='no_extras_W_equals_B' if choice=='B' else 'all_selected3_values_every_C_row',
        base_proof_scope='all_structure_metadata_coverage_core18_sampled',baseline_formula_values_complete=False,
        base_core18_sample_pairs=total,base_core18_comparisons=18*total,query_count=14,candidate_count=total,mismatch_count=0,
        labels_loaded=False,target_relation_created=False,fit_attempt_count=0,native_prediction_count=0,proof_limits=m.SOURCE_PROOF_LIMITS)
    return days,core


class SourceProofBoundary(unittest.TestCase):
    def test_complete_R2_and_W_equals_B_keep_empty_C_queries_and_sample_scope(self):
        for choice in ['B','R2']:
            days,core=source_evidence(choice);self.assertEqual(m.validate_source_core(core,days,choice),core)
            self.assertFalse(core['baseline_formula_values_complete']);self.assertEqual(core['days'][-1]['empty_candidate_queries'],2)
    def test_each_daily_complete_scope_and_no_target_flags_required(self):
        for name in ['source_Q_C_complete','metadata_ages_coverage_complete','chosen_formula_values_complete','labels_loaded','target_relation_created','baseline_formula_values_complete']:
            days,core=source_evidence();core['days'][3][name]=not core['days'][3][name]
            with self.subTest(field=name),self.assertRaises(ValueError):m.validate_source_core(core,days,'R2')
    def test_bool_counts_and_omitted_or_reordered_days_reject(self):
        for mode in ['bool','missing','reordered','aggregate']:
            days,core=source_evidence()
            if mode=='bool':core['days'][1]['chosen_columns']=True
            elif mode=='missing':core['days'].pop()
            elif mode=='reordered':core['days'][0],core['days'][1]=core['days'][1],core['days'][0]
            else:core['query_count']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_source_core(core,days,'R2')
    def test_sampled_B18_cannot_be_promoted_or_comparisons_overstated(self):
        for mode in ['scope','pairs','comparisons','stratum','aggregate','empty']:
            days,core=source_evidence()
            if mode=='scope':core['base_proof_scope']='all_numeric_exhaustive'
            elif mode=='pairs':core['days'][0]['base_core18_sample_pairs']=4
            elif mode=='comparisons':core['days'][0]['base_core18_comparisons']+=1
            elif mode=='stratum':core['days'][0]['strata']['category_missing']['sampled_pairs']=1
            elif mode=='aggregate':core['base_core18_comparisons']+=1
            else:core['days'][-1]['empty_candidate_queries']=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_source_core(core,days,'R2')
    def test_native_count_depends_on_nonempty_C_not_number_of_queries(self):
        days,_=source_evidence();self.assertEqual(m.native_calls(days,'B'),6);self.assertEqual(m.native_calls(days,'R2'),12)
        for row in days:row['candidate_count']=0
        self.assertEqual(m.native_calls(days,'R2'),0)


class MetricProofBoundary(unittest.TestCase):
    """Consumer fault tests with literal aggregate reports; no target SQL."""
    def setUp(self):
        from types import SimpleNamespace
        self.evaluation=dict(periods={name:dict(support=dict(query_count=q,target_pairs=y),numeric=.5) for name,q,y in
            [('confirmation25_reporting_only',2,1),('final26_31_frozen',12,3)]})
        self.core=dict(status='independent_core_values_match_pending_owner_acceptance',periods=deepcopy(self.evaluation['periods']),fullY_pairs=4,
            fit_attempt_count=0,native_prediction_count=0,bootstrap_replicates_per_estimand=200,
            proof_scope='raw_fullY_all_queries_all_scores_four_estimands_every_fixed_user_draw_no_lifetime_or_byte_authentication',
            oracle_target_stage_opened_at='2026-10-15T12:02:01Z',oracle_target_stage_started_monotonic=110.,
            oracle_fullY_started_at='2026-10-15T12:02:02Z',oracle_fullY_started_monotonic=111.,private_ranking_rows_checked=28)
        self.session=SimpleNamespace();self.pred=dict(sealed_at='2026-10-15T12:01:30Z');self.target=dict(sealed_at='2026-10-15T12:02:00Z')
        self.patches=[patch.object(m,'oracle_core',side_effect=lambda *args:deepcopy(self.core)),
            patch.object(m,'issued_for',return_value=dict(issued_at_monotonic=90.)),
            patch.object(m,'role_receipt',return_value=dict(started_monotonic=100.,finished_monotonic=200.)),
            patch.object(m,'now',return_value='2026-10-15T12:10:00Z')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def verify(self):return m.verify_metric_evidence(self.session,self.evaluation,self.pred,self.target)
    def test_complete_independent_rows_and_clock_evidence(self):self.assertEqual(self.verify(),self.core)
    def test_missing_private_rows_wrong_count_and_bool_count_rejected(self):
        for mode in ['missing','wrong','bool']:
            original=deepcopy(self.core)
            if mode=='missing':self.core.pop('private_ranking_rows_checked')
            elif mode=='wrong':self.core['private_ranking_rows_checked']=27
            else:self.core['private_ranking_rows_checked']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.verify()
            self.core=original
    def test_independent_target_clock_before_child_or_after_receipt_rejects(self):
        for begin,end in [(95.,111.),(95.,96.),(110.,201.),(112.,111.)]:
            self.core.update(oracle_target_stage_started_monotonic=begin,oracle_fullY_started_monotonic=end)
            with self.subTest(begin=begin,end=end),self.assertRaisesRegex(ValueError,'monotonic chronology'):self.verify()
    def test_same_second_target_seal_and_future_or_reversed_fullY_clock_reject(self):
        for admission,full in [('2026-10-15T12:02:00Z','2026-10-15T12:02:02Z'),
                ('2026-10-15T12:02:01Z','2026-10-15T12:02:00Z'),('2026-10-15T12:02:01Z','2026-10-15T12:11:00Z')]:
            self.core.update(oracle_target_stage_opened_at=admission,oracle_fullY_started_at=full)
            with self.subTest(admission=admission,full=full),self.assertRaisesRegex(ValueError,'UTC chronology'):self.verify()
    def test_numeric_tolerance_does_not_allow_wrong_metric_or_target_support(self):
        self.core['periods']['final26_31_frozen']['numeric']+=1e-14;self.verify()
        self.core['periods']['final26_31_frozen']['numeric']+=.01
        with self.assertRaisesRegex(ValueError,'numeric mismatch'):self.verify()
        self.core['periods']=deepcopy(self.evaluation['periods']);self.core['fullY_pairs']=3
        with self.assertRaisesRegex(ValueError,'target count'):self.verify()





class TargetAdmissionBoundary(unittest.TestCase):
    """Pure validation seam; real metadata ingress independently probed elsewhere."""
    def setUp(self):
        from types import SimpleNamespace
        from tests.test_heldout_contract import r
        self.lock,self.choice,self.inventory,self.source,self.intent,self.acceptance=fixture('R2')
        self.intent['opened_at']='2026-10-15T12:02:01Z';self.policy=r('target-policy.json');self.target=r('target-gate.json')
        self.inputs=dict(source_acceptance=self.source['acceptance'],source_manifest=r('source-manifest.json'),prediction_acceptance=self.acceptance['reference'],prediction_inventory=r('inventory.json'),target_policy=self.policy)
        self.private={'full-targets.parquet':r('full-targets.parquet'),'private-rankings.jsonl':r('private-rankings.jsonl')}
        periods={}
        for name,days in [('confirmation25_reporting_only',self.source['days'][:1]),('final26_31_frozen',self.source['days'][1:])]:
            periods[name]=dict(anchors=[d['anchor'] for d in days],support=dict(query_count=sum(d['query_count'] for d in days),candidate_pairs=sum(d['candidate_count'] for d in days)))
        self.body=dict(**self.inputs,target_execution=self.target,actual_target_intent=self.intent,target_stage_opened_at=self.intent['opened_at'],
            target_stage_started_monotonic=110.,fullY_started_at='2026-10-15T12:02:02Z',fullY_started_monotonic=111.,periods=periods,
            private_outputs=dict(targets=self.private['full-targets.parquet'],rankings=self.private['private-rankings.jsonl']))
        self.session=SimpleNamespace();self.prepared=dict(lock=self.lock)
        self.pred=dict(sealed_at='2026-10-15T12:01:30Z');self.target_body=dict(sealed_at='2026-10-15T12:02:00Z')
        self.patches=[patch.object(m,'unaccepted_manifest',side_effect=lambda *args:(r('evaluation.json'),deepcopy(self.body))),
            patch.object(m,'issued_for',return_value=dict(inputs=self.inputs,authorities=dict(target_execution=self.target),issued_at_monotonic=90.)),
            patch.object(m,'role_receipt',return_value=dict(started_monotonic=100.,finished_monotonic=200.)),
            patch.object(m,'role_output',side_effect=lambda session,role,name:self.private[name]),
            patch.object(m,'now',return_value='2026-10-15T12:10:00Z')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def verify(self):return m.verify_evaluation(self.session,self.prepared,self.source,self.inventory,self.acceptance,self.pred,self.target_body,self.policy)
    def test_actual_producer_clock_within_child_lifetime_accepts(self):self.assertEqual(self.verify()[1],self.body)
    def test_original_independent_red_admission_before_child_start_now_rejects(self):
        for begin,end in [(95.,111.),(95.,96.)]:
            self.body.update(target_stage_started_monotonic=begin,fullY_started_monotonic=end)
            with self.subTest(begin=begin,end=end),self.assertRaisesRegex(ValueError,'monotonic chronology'):self.verify()
    def test_target_admission_at_seal_second_and_future_SQL_clock_reject(self):
        self.body['target_stage_opened_at']=self.intent['opened_at']='2026-10-15T12:02:00Z'
        with self.assertRaises(ValueError):self.verify()
        self.body['target_stage_opened_at']=self.intent['opened_at']='2026-10-15T12:02:01Z';self.body['fullY_started_at']='2026-10-15T12:11:00Z'
        with self.assertRaisesRegex(ValueError,'UTC chronology'):self.verify()
    def test_private_output_ref_and_complete_final_window_support_bound(self):
        self.body['private_outputs']['rankings']=self.private['full-targets.parquet']
        with self.assertRaisesRegex(ValueError,'Private target/ranking'):self.verify()
        self.body['private_outputs']['rankings']=self.private['private-rankings.jsonl'];self.body['periods']['final26_31_frozen']['support']['query_count']-=1
        with self.assertRaisesRegex(ValueError,'window domain'):self.verify()





class PredictionProofBoundary(unittest.TestCase):
    """Full observer scope must be checked, not only plausible daily subtotals."""
    def setUp(self):
        self.days,_=source_evidence();self.days[-1].update(query_count=0,mature_query_count=0)
        self.core=dict(status='independent_all_seven_scores_match_pending_owner_acceptance',days=[],native_prediction_count=12,fit_attempt_count=0,labels_loaded=False,
            proof_scope='all7_independent_matrix_native_scores_rank_order_with_external_byte_lifetime_authority')
        for day in self.days:
            self.core['days'].append(dict(status='independent_daily_scores_match_pending_all_date_and_owner_acceptance',anchor=day['anchor'],queries=day['query_count'],
                candidate_pairs=day['candidate_count'],native_prediction_count=2 if day['candidate_count'] else 0,fit_attempt_count=0,outcome_relations_opened=0,
                proof_scope='independent_Q_C_F_numeric_projection_native_state_all_rawscores_complete_rank_order_no_byte_or_lifetime_authentication'))
    def verify(self):return m.validate_prediction_core(self.core,self.days,'R2')
    def test_complete_all_seven_observer_scope_preserves_zero_query_partition(self):self.assertEqual(self.verify(),self.core)
    def test_failed_or_missing_top_verdict_rejects_despite_valid_daily_rows(self):
        original=deepcopy(self.core)
        for mode in ['failed','missing','labels','fit','native','scope']:
            self.core=deepcopy(original)
            if mode=='failed':self.core['status']='failed'
            elif mode=='missing':self.core.pop('status')
            elif mode=='labels':self.core['labels_loaded']=True
            elif mode=='fit':self.core['fit_attempt_count']=4
            elif mode=='native':self.core['native_prediction_count']=99
            else:self.core['proof_scope']='wrong'
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.verify()
    def test_nested_private_payload_and_extra_or_missing_daily_fields_reject(self):
        for mode in ['private','missing','scope']:
            original=deepcopy(self.core)
            if mode=='private':self.core['days'][0]['private_targets']={'never_allowed':[]}
            elif mode=='missing':self.core['days'][0].pop('proof_scope')
            else:self.core['days'][0]['proof_scope']='unreviewed'
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.verify()
            self.core=original
    def test_boolean_zero_statistics_cannot_impersonate_empty_last_day(self):
        for name in ['queries','candidate_pairs','native_prediction_count','fit_attempt_count','outcome_relations_opened']:
            original=deepcopy(self.core);self.core['days'][-1][name]=False
            with self.subTest(field=name),self.assertRaisesRegex(ValueError,'typed count'):self.verify()
            self.core=original
    def test_missing_or_reordered_last_day_and_allseven_total_reject(self):
        original=deepcopy(self.core)
        for mode in ['missing','reordered','total']:
            self.core=deepcopy(original)
            if mode=='missing':self.core['days'].pop()
            elif mode=='reordered':self.core['days'][0],self.core['days'][1]=self.core['days'][1],self.core['days'][0]
            else:self.core['native_prediction_count']=False
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.verify()


if __name__=='__main__':unittest.main()
