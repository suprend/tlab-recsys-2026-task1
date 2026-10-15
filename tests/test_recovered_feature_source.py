from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import recovered_feature_source as c


class RecoveredSourceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        self.patches=[]
        def change(obj,name,value):
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        change(c,'ROOT',self.root)
        self.d='artifacts/feature-program-source-oracle/'+'b'*32
        identity=dict(fingerprints={'inputs/base':self.put('inputs/base','accepted',raw=True)},
                      acceptance_refs=dict(train='train',selection='selection',contract='contract',base_registry='registry'),
                      pool={'typed':'pool'},allocation={'slots':'fixed'},selected_union={'columns':'selected12'})
        run=hashlib.sha256(c.canonical(identity).encode()).hexdigest();change(c,'RUN_ID',run)
        self.run=run;self.m=dict(run_id=run,identity=identity,execution_approval=dict(path='old/execution.json'),
                               outputs={'train':[{'artifacts':{'features':{'path':'exports/train.parquet'}}}],
                                        'selection':[{'artifacts':{'features':{'path':'exports/selection.parquet'}}}]})
        self.old=dict(status='failed',run_id=run,error_type='OutOfMemoryException')
        for name,value in [('old/run.json',self.m),('old/report.json',self.old),('old/execution.json',{'approved':True}),
                           ('old/source.claim.json',{'once':True}),('old/prefix.json',{'old':107.42})]:self.put(name,value)
        self.declared=dict(run_id=run,outputs={name:self.put(name,'immutable synthetic rows',raw=True) for name in
                          ['exports/train.parquet','exports/selection.parquet']},pairs=4,queries=3,days=2,source_claim=self.ref('old/source.claim.json'))
        self.b=dict(owner_and_oracle_cpu_seconds=792,owner_and_oracle_wall_seconds=1044,
                    old_source_cpu_upper_seconds=107.42,old_source_active_wall_seconds=155.77)
        self.policy=dict(producer_manifest=self.ref('old/run.json'),producer_report=self.ref('old/report.json'),
                         failed_lifetime_receipt=self.ref('old/prefix.json'),oracle_source=dict(path='oracle.py',sha256=self.put('oracle.py','# reviewed',raw=True)))
        self.put(c.POLICY,self.policy);change(c,'POLICY_SHA256',self.hash(c.POLICY))
        claim=dict(version=1,scope='once_only_selected12_source_oracle',run_id=run,allowed_observer_attempts=1,
                   allowed_source_calculations=0,allowed_fit_attempts=0,policy=self.ref(c.POLICY),invocation_directory=self.d)
        self.put('artifacts/feature-program-study/independent-oracle.claim.json',claim)
        shared={'limit_cpu_seconds':7200,'charged_prefix_cpu_seconds':107.42,'unknown_cost':False,'source_parent_receipt':self.ref('old/prefix.json')}
        request=dict(scope=c.admission.ORACLE_SCOPE,run_id=run,producer_manifest=self.policy['producer_manifest'],
                     producer_report=self.policy['producer_report'],oracle_source=self.policy['oracle_source'],shared_budget=shared,recovery_policy=self.ref(c.POLICY))
        self.put(self.d+'/request.json',request)
        allocation=dict(cpu_seconds=779,deadline_monotonic=100000000.,rss_bytes=7*2**30)
        context=dict(run_id=run,request=self.ref(self.d+'/request.json'),oracle_execution_approval=self.ref(c.POLICY),
                     recovery_policy=self.ref(c.POLICY),shared_budget=shared,allocation=allocation)
        self.put(self.d+'/context.json',context)
        launch=dict(argv=['python','oracle.py'],issued_context_sha256=self.hash(self.d+'/context.json'),allocation=allocation,
                    policy=self.ref(c.POLICY),claim=self.ref('artifacts/feature-program-study/independent-oracle.claim.json'))
        self.put(self.d+'/launch.json',launch);self.put(self.d+'/evidence.json',dict(status='verified',checked_scalar_values=48))
        finalpins={n:self.hash(n) for n in [c.POLICY,'old/run.json','old/report.json','old/source.claim.json','old/prefix.json','oracle.py',
                   'artifacts/feature-program-study/independent-oracle.claim.json',*[self.d+'/'+v for v in ['context.json','request.json','launch.json']]]}
        self.owner=dict(version=1,status='recovered_source_verified_pending_external_acceptance',run_id=run,producer_calls=0,
                        source_calculations=0,oracle_calls=1,fit_attempt_count=0,labels_loaded=False,policy=self.ref(c.POLICY),
                        evidence=self.ref(self.d+'/evidence.json'),launch=launch,oracle_launch={k:launch[k] for k in ['argv','issued_context_sha256','allocation']},
                        actual_reaped_oracle_cpu_seconds=10.,actual_new_total_cpu_seconds=10.1,seconds=11.,parent_peak_rss_bytes=1024,
                        final_source_pins=finalpins)
        self.put(self.d+'/report.json',self.owner)
        self.external=dict(version=1,status='verified_full_lifetime',exit_code=0,run_id=run,owner_report=self.ref(self.d+'/report.json'),
                           evidence=self.ref(self.d+'/evidence.json'),policy=self.ref(c.POLICY),actual_cpu_seconds=10.2,wall_seconds=11.1,
                           charged_source_oracle_cpu_seconds=107.42+10.2,active_computation_wall_seconds=155.77+11.1,
                           original_absolute_deadline='unavailable_not_reconstructed',process_peak_rss_bytes=2048)
        self.put(self.d+'/external-lifetime.json',self.external)
        for n in ['oracle.log','external-lifetime.log']:self.put(self.d+'/'+n,'exit0',raw=True)
        aggregate=dict(status='accepted_recovered_source',run_id=run,checked_pairs=4,checked_scalar_values=48,
                       original_producer_status='failed',producer_regenerated=False)
        for name in c.PROOFS:self.put(name,aggregate if name.endswith('.json') else 'Immutable proof',raw=not name.endswith('.json'))
        pins={**identity['fingerprints'],**self.declared['outputs'],**finalpins}
        extra=['old/run.json','old/report.json','old/execution.json']+[self.d+'/'+n for n in
               ['report.json','evidence.json','oracle.log','external-lifetime.json','external-lifetime.log']]+list(c.PROOFS)
        pins.update({name:self.hash(name) for name in extra})
        proof=dict(oracle_source=self.policy['oracle_source'],aggregate_evidence=self.ref(c.PROOFS[0]),
                   parent_completion_receipt=self.ref(self.d+'/external-lifetime.json'),recovery_policy=self.ref(c.POLICY))
        self.acceptance=dict(version=1,approved=True,scope=c.SCOPE,run_id=run,fingerprints=pins,source_proof=proof)
        self.path=self.root/'acceptance.json';change(c,'ACCEPTANCE_SHA256','');self.seal()
        # Formula and original107-plan verification are already reviewed delegates;
        # isolate this new receipt consumer's authority/closure/failure boundary.
        self.admit=patch.object(c.admission,'validate_failed_source',return_value=self.declared);self.admit.start();self.addCleanup(self.admit.stop)
        self.policygate=patch.object(c.admission,'validate_policy',return_value=self.b);self.policygate.start();self.addCleanup(self.policygate.stop)
        self.evidencegate=patch.object(c.owner_rules,'validate_evidence');self.evidencegate.start();self.addCleanup(self.evidencegate.stop)
        self.collections={'train':{'accepted':True},'selection':{'accepted':True}}
        self.planner=patch.object(c.source,'prepare_plan',return_value=(dict(run_id=run,identity=identity),self.collections));self.planner.start();self.addCleanup(self.planner.stop)
    def put(self,name,value,raw=False):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value if raw else json.dumps(value,sort_keys=True)+'\n');return self.hash(name)
    def hash(self,name):return hashlib.sha256((self.root/name).read_bytes()).hexdigest()
    def ref(self,name):return dict(path=name,sha256=self.hash(name))
    def seal(self):
        self.put('acceptance.json',self.acceptance);c.ACCEPTANCE_SHA256=self.hash('acceptance.json')
    def changed_receipt(self,name,value):
        self.acceptance['fingerprints'][name]=self.put(name,value);self.seal()
    def test_success_preserves_original_failure_and_returns_daily_only_without_source_materialization(self):
        result=c.verify_source_acceptance(self.path)
        self.assertEqual(result['report']['status'],'failed');self.assertEqual(result['paid_source_cpu_seconds'],117.62)
        self.assertEqual(result['daily_features'],{'train':['exports/train.parquet'],'selection':['exports/selection.parquet']})
        self.assertIs(result['collections'],self.collections);self.assertTrue(result['physical']['source_formula_acceptance'])
        c.owner_rules.validate_evidence.assert_called_once();c.source.prepare_plan.assert_called_once()
    def test_fresh_reseal_without_external_anchor_rejected(self):
        self.acceptance['approved']=False;self.put('acceptance.json',self.acceptance)
        with self.assertRaisesRegex(ValueError,'Unreviewed'):c.verify_source_acceptance(self.path)
    def test_bool_version_and_approval_are_not_integer_authority(self):
        for key,value in [('version',True),('approved',1)]:
            with self.subTest(key=key):
                old=self.acceptance[key];self.acceptance[key]=value;self.seal()
                with self.assertRaisesRegex(ValueError,'authority'):c.verify_source_acceptance(self.path)
                self.acceptance[key]=old
    def test_same_cardinality_missing_proof_pin_rejected(self):
        self.acceptance['fingerprints'].pop(c.PROOFS[1]);self.acceptance['fingerprints']['unrelated']=self.put('unrelated','x',raw=True);self.seal()
        with self.assertRaisesRegex(ValueError,'authority pin'):c.verify_source_acceptance(self.path)
    def test_known_failure_precedes_large_pin_or_planner_work(self):
        self.put(self.d+'/evidence.failed.json',{'status':'failed'})
        with patch.object(c.receipts,'_sha',side_effect=AssertionError('large hash')):
            with self.assertRaisesRegex(ValueError,'Known failed'):c.verify_source_acceptance(self.path)
        c.source.prepare_plan.assert_not_called()
    def test_late_marker_rejected_after_hashing(self):
        original=c.receipts._sha
        def poison(path,check):
            result=original(path,check)
            if path.name=='base':self.put(self.d+'/report.failed.json',{'status':'failed'})
            return result
        with patch.object(c.receipts,'_sha',side_effect=poison):
            with self.assertRaisesRegex(ValueError,'Late failed'):c.verify_source_acceptance(self.path)
    def test_external_exit_tail_and_paid_prefix_cannot_reset(self):
        self.external['actual_cpu_seconds']=9.;self.changed_receipt(self.d+'/external-lifetime.json',self.external)
        self.acceptance['source_proof']['parent_completion_receipt']=self.ref(self.d+'/external-lifetime.json');self.seal()
        with self.assertRaisesRegex(ValueError,'budget reset'):c.verify_source_acceptance(self.path)
    def test_launch_context_issuer_binding_rejects_resealed_slot(self):
        owner=deepcopy(self.owner);owner['oracle_launch']['issued_context_sha256']='c'*64
        self.changed_receipt(self.d+'/report.json',owner)
        with self.assertRaisesRegex(ValueError,'Issuer launch'):c.verify_source_acceptance(self.path)
    def test_guard_and_nonlocal_pins_fail_before_data(self):
        with self.assertRaisesRegex(TimeoutError,'expired'):c.verify_source_acceptance(self.path,check=lambda:(_ for _ in ()).throw(TimeoutError('expired')))
        self.acceptance['fingerprints']['../outside']='a'*64;self.seal()
        with self.assertRaisesRegex(ValueError,'Nonlocal'):c.verify_source_acceptance(self.path)
    def test_unpinned_changed_export_detected_without_formula_rerun(self):
        self.put('exports/train.parquet','tampered',raw=True)
        with self.assertRaisesRegex(ValueError,'input/output changed'):c.verify_source_acceptance(self.path)
    def test_original_plan_binding_mismatch_rejected(self):
        with patch.object(c.source,'prepare_plan',return_value=({'run_id':'f'*64,'identity':{}},self.collections)):
            with self.assertRaisesRegex(ValueError,'lineage'):c.verify_source_acceptance(self.path)


if __name__=='__main__':unittest.main()
