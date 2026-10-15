from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import run_feature_source_recovery as m


def boundary():
    return dict(old_source_cpu_upper_seconds=107.42,old_source_active_wall_seconds=155.77,
        owner_and_oracle_cpu_seconds=792,owner_and_oracle_wall_seconds=1044,original_source_cpu_cap=900,
        original_source_wall_cap=1200,original_oracle_cpu_cap=900,original_oracle_wall_cap=1200,
        shared_study_cpu_cap=7200,original_absolute_deadline='unavailable_not_reconstructed',failure_consumes_oracle=True)


def admitted():return dict(run_id='a'*64,pairs=2,queries=3,days=15,outputs={'q.parquet':'b'*64,'f.parquet':'c'*64},source_claim=dict(path='source.claim.json',sha256='d'*64))


def evidence(context,context_sha,oracle_claim=None):
    a=admitted()
    return dict(version=1,status='verified',run_id=context['run_id'],source_proof_scope='all_selected12_values_and_accepted_QC_domain',
        formula_values_complete=True,fit_attempt_count=0,checked_pairs=2,checked_physical_columns=12,checked_scalar_values=24,
        mismatch_count=0,checked_columns=12,checked_days=15,mismatch_rows=0,baseline_all45_preserved=True,labels_loaded=False,
        independent_expected_values=True,baseline_source_formula_scope='preservation_only_prior_manual18_source_proof_unchanged',
        recency_absolute_tolerance_seconds=1e-9,context_sha256=context_sha,request=context['request'],
        producer_manifest=context['producer_manifest'],producer_report=context['producer_report'],oracle_source=context['oracle_source'],
        shared_budget=context['shared_budget'],source_claim=a['source_claim'],source_parent_receipt=context['shared_budget']['source_parent_receipt'],
        verified_outputs=a['outputs'],oracle_claim=oracle_claim or dict(path=m.CLAIM,sha256='4'*64),source_recovery=dict(policy=context['recovery_policy'],failed_lifetime_receipt=context['shared_budget']['source_parent_receipt'],
            source_claim=a['source_claim'],producer_regenerated=False,original_producer_status='failed'),
        process_cpu_seconds=0.,process_peak_rss_bytes=1000,started_monotonic=100.,finished_monotonic=100.,
        phase_coverage=dict(train=dict(expected_queries=2,expected_pairs=1,checked_queries=2,checked_pairs=1),
                            selection=dict(expected_queries=1,expected_pairs=1,checked_queries=1,checked_pairs=1)))


class BudgetAndEvidence(unittest.TestCase):
    class Metrics:
        def __init__(self,parent=1,children=0,peak=1):self.parent=parent;self.children=children;self.peak=peak
        def self_cpu(self):return self.parent
        def child_cpu(self):return self.children
        def rss(self):return self.peak
    def test_single_unused_oracle_allowance_retains_old_cost_and_full_live_parent_reserve(self):
        b=m.Budget(boundary(),self.Metrics(),started=0)
        with patch.object(m.time,'monotonic',return_value=100):slot=b.allocation()
        self.assertEqual(slot['cpu_seconds'],779);self.assertEqual(slot['deadline_monotonic'],1024)
        self.assertAlmostEqual(b.cpu(),108.42)
        self.assertLessEqual(b.new_cpu()+slot['cpu_seconds']+10+2,792)
        self.assertLessEqual(107.42+b.new_cpu()+slot['cpu_seconds']+10+2,900)
    def test_fresh_deadline_unknown_usage_and_RSS_fail_without_counter_reset(self):
        with patch.object(m.time,'monotonic',return_value=1025):
            with self.assertRaises(TimeoutError):m.Budget(boundary(),self.Metrics(),started=0).allocation()
        with patch.object(m.time,'monotonic',return_value=100):
            for metrics,kind in [(self.Metrics(children=-1),ValueError),(self.Metrics(parent=True),ValueError),
                (self.Metrics(peak=2**30+1),MemoryError),(self.Metrics(parent=791),TimeoutError),
                (self.Metrics(parent=785),TimeoutError)]:
                with self.subTest(kind=kind,values=metrics.__dict__),self.assertRaises(kind):
                    m.Budget(boundary(),metrics,started=0).allocation()
    def context(self):
        return dict(run_id='a'*64,request=dict(path='request.json',sha256='b'*64),producer_manifest=dict(path='run.json',sha256='c'*64),
            producer_report=dict(path='report.json',sha256='d'*64),oracle_source=dict(path='oracle.py',sha256='e'*64),
            shared_budget=dict(source_parent_receipt=dict(path='failed-prefix.json',sha256='f'*64)),
            recovery_policy=dict(path='policy.json',sha256='1'*64),allocation=dict(cpu_seconds=700,deadline_monotonic=1024,rss_bytes=7*2**30),issued_at_monotonic=100.)
    def validate(self,e,context=None,actual=0.):
        with patch.object(m.time,'monotonic',return_value=101):m.validate_evidence(e,context or self.context(),'2'*64,admitted(),actual,oracle_claim=dict(path=m.CLAIM,sha256='4'*64))
    def test_exact_physical_fullY_free_proof_and_failed_source_history_are_bound(self):
        context=self.context();e=evidence(context,'2'*64);self.validate(e)
        for key,value in [('fit_attempt_count',1),('labels_loaded',True),('checked_scalar_values',23),
            ('context_sha256','3'*64),('checked_days',14),('formula_values_complete',False)]:
            bad=deepcopy(e);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(bad)
        bad=deepcopy(e);bad['source_recovery']['producer_regenerated']=True
        with self.assertRaises(ValueError):self.validate(bad)
    def test_phase_bag_cover_resource_and_time_cannot_be_faked(self):
        e=evidence(self.context(),'2'*64)
        bad=deepcopy(e);bad['phase_coverage']['selection']['checked_pairs']=0
        with self.assertRaises(ValueError):self.validate(bad)
        bad=deepcopy(e);bad['phase_coverage']['train']['expected_queries']=True
        with self.assertRaises(ValueError):self.validate(bad)
        bad=deepcopy(e);bad['process_cpu_seconds']=1.
        with self.assertRaises(TimeoutError):self.validate(bad,actual=0.)
        bad=deepcopy(e);bad['finished_monotonic']=1025.
        with self.assertRaises(ValueError):self.validate(bad)
        bad=deepcopy(e);bad['process_peak_rss_bytes']=7*2**30+1
        with self.assertRaises(MemoryError):self.validate(bad)


class VerifiedModule(unittest.TestCase):
    def test_mandatory_pinned_snapshot_executes_same_verified_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'scripts/helper.py';path.parent.mkdir();path.write_text('answer=42\n')
            pins={'scripts/helper.py':m.sha(path)}
            self.assertEqual(m.verified_module(root,'scripts.helper',pins).answer,42)
            with self.assertRaisesRegex(ValueError,'pin omitted'):m.verified_module(root,'scripts.helper',{})
            path.write_text('raise AssertionError("must not execute changed helper")\n')
            with self.assertRaisesRegex(ValueError,'snapshot changed'):m.verified_module(root,'scripts.helper',pins)


class Lifecycle(unittest.TestCase):
    def setUp(self):
        from scripts import strong_baseline as strong
        import scripts
        self.s=strong;self.scripts=scripts;tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        p=patch.object(strong,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        owner_path=self.root/'scripts/run_feature_source_recovery.py';owner_path.parent.mkdir();owner_path.write_bytes(Path(m.__file__).read_bytes())
        sp=importlib.util.spec_from_file_location('owner_fixture',owner_path);self.owner=importlib.util.module_from_spec(sp)
        with patch.object(m.time,'monotonic',return_value=100):sp.loader.exec_module(self.owner)
        self.owner_path=owner_path
        adapter=types.ModuleType('scripts.feature_program_source_recovery');adapter.__file__=str(self.root/'scripts/feature_program_source_recovery.py')
        Path(adapter.__file__).write_text('# synthetic admission only\n')
        adapter.validate_policy=lambda *args:boundary();adapter.validate_failed_source=lambda *args:admitted()
        adapter.load_recovery_inputs=lambda *args:(_ for _ in ()).throw(AssertionError('parent must never load source'))
        p=patch.dict(sys.modules,{'scripts.feature_program_source_recovery':adapter});p.start();self.addCleanup(p.stop)
        p=patch.object(scripts,'feature_program_source_recovery',adapter,create=True);p.start();self.addCleanup(p.stop)
        entry=self.root/'tests/oracles/feature_program_recovery_audit.py';entry.parent.mkdir(parents=True);entry.write_text('# synthetic observer\n')
        def put(name,value):
            path=self.root/name;path.write_text(json.dumps(value,sort_keys=True)+'\n');return dict(path=name,sha256=m.sha(path))
        self.old_manifest=put('old-run.json',dict(run_id='a'*64));self.old_report=put('old-report.json',dict(status='failed'))
        self.prefix=put('failed-prefix.json',dict(producer=dict(peak_rss_bytes=3627925504)))
        claim=put('source.claim.json',dict(source_calculations=1))
        refs=dict(owner_source=dict(path=str(owner_path.relative_to(self.root)),sha256=m.sha(owner_path)),
            oracle_source=dict(path=str(entry.relative_to(self.root)),sha256=m.sha(entry)),producer_manifest=self.old_manifest,
            producer_report=self.old_report,failed_lifetime_receipt=self.prefix,source_claim=claim)
        self.policy=dict(version=1,approved=True,scope='recover_failed_selected12_source_with_unused_oracle',run_id='a'*64,
            boundary=boundary(),fingerprints={r['path']:r['sha256'] for r in refs.values()},**refs)
        for name in ['scripts/feature_program_source_recovery.py','scripts/strong_baseline.py']:
            if name.endswith('strong_baseline.py'):
                (self.root/name).write_bytes(Path(strong.__file__).read_bytes())
                p=patch.object(strong,'__file__',str(self.root/name));p.start();self.addCleanup(p.stop)
            self.policy['fingerprints'][name]=m.sha(self.root/name)
        (self.root/'export.parquet').write_bytes(b'small synthetic export bytes')
        self.policy['fingerprints']['export.parquet']=m.sha(self.root/'export.parquet')
        put('approval.json',self.policy);self.calls=[];self.adapter=adapter
    def fake_loader(self,root,name,pins):
        key=name.replace('.','/')+'.py'
        if key not in pins:raise ValueError('Mandatory lifecycle/admission code pin omitted')
        return self.s if name.endswith('strong_baseline') else self.adapter
    def fake_oracle(self,argv,log,**kwargs):
        self.calls.append(argv);Path(log).write_text('synthetic oracle\n')
        path=Path(argv[argv.index('--context')+1]);context=json.loads(path.read_text());e=evidence(context,m.sha(path),dict(path=m.CLAIM,sha256=m.sha(self.root/m.CLAIM)))
        (self.root/context['output_path']).write_text(json.dumps(e,sort_keys=True)+'\n');return 0
    def invoke(self,side_effect=None):
        with patch.object(self.owner.sys,'argv',[str(self.owner_path),'--project-root',str(self.root),'--approval','approval.json']),\
            patch.object(self.owner.time,'monotonic',return_value=100),patch.object(self.s,'run_process',side_effect=side_effect or self.fake_oracle),\
            patch.object(self.s,'child_cpu',return_value=0.),\
            patch.object(self.owner,'verified_module',side_effect=self.fake_loader):self.owner.main()
    def test_mock_owner_lifecycle_isolates_prior_suite_children_cpu(self):
        # Earlier tests may reap real children in this shared unittest process.
        # This fixture launches a fake oracle and represents a fresh owner.
        with patch.object(self.s, 'child_cpu', return_value=0.125):
            self.invoke()
            self.assertEqual(self.s.child_cpu(), 0.125)
        self.assertEqual(len(self.calls), 1)
    def test_one_oracle_no_source_calculation_old_failure_preserved_and_no_retry(self):
        before={name:(self.root/name).read_bytes() for name in ['old-run.json','old-report.json','source.claim.json']}
        self.invoke();self.assertEqual(len(self.calls),1)
        report=json.loads(next((self.root/'artifacts/feature-program-source-oracle').glob('*/report.json')).read_text())
        self.assertEqual(report['status'],'recovered_source_verified_pending_external_acceptance')
        self.assertEqual((report['producer_calls'],report['source_calculations'],report['fit_attempt_count']),(0,0,0))
        self.assertTrue(all((self.root/n).read_bytes()==b for n,b in before.items()))
        with self.assertRaises(FileExistsError):self.invoke()
        self.assertEqual(len(self.calls),1)
    def test_failed_unused_oracle_consumes_claim_and_keeps_failure_evidence(self):
        def fail(*args,**kwargs):raise RuntimeError('synthetic oracle failure')
        with self.assertRaisesRegex(RuntimeError,'synthetic oracle failure'):self.invoke(fail)
        report=json.loads(next((self.root/'artifacts/feature-program-source-oracle').glob('*/report.failed.json')).read_text())
        self.assertEqual(report['status'],'failed')
        with self.assertRaises(FileExistsError):self.invoke()
        self.assertEqual(self.calls,[])
    def test_changed_export_paid_preparation_consumes_attempt_and_persists_failure(self):
        (self.root/'export.parquet').write_bytes(b'changed export')
        with self.assertRaisesRegex(ValueError,'pin changed'):self.invoke()
        self.assertTrue((self.root/m.CLAIM).exists());self.assertEqual(self.calls,[])
        failed=next((self.root/'artifacts/feature-program-source-oracle').glob('*/report.failed.json'))
        self.assertEqual(json.loads(failed.read_text())['oracle_calls'],0)
        with self.assertRaises(FileExistsError):self.invoke()
    def test_late_failed_marker_after_replay_cannot_return_success(self):
        original=self.owner.sha;trigger=[False]
        def fault(path):
            value=original(path)
            if Path(path).name=='old-run.json' and self.calls and not trigger[0]:
                trigger[0]=True
                directory=next((self.root/'artifacts/feature-program-source-oracle').iterdir())
                (directory/'evidence.failed.json').write_text('{"status":"failed"}')
            return value
        with patch.object(self.owner,'sha',side_effect=fault):
            with self.assertRaisesRegex(RuntimeError,'Late known'):self.invoke()
        self.assertTrue(trigger[0])
        failed=next((self.root/'artifacts/feature-program-source-oracle').glob('*/report.failed.json'))
        self.assertEqual(json.loads(failed.read_text())['status'],'failed')
    def test_missing_admission_pin_aborts_before_helper_call_claim_or_launch(self):
        self.policy['fingerprints'].pop('scripts/feature_program_source_recovery.py')
        (self.root/'approval.json').write_text(json.dumps(self.policy,sort_keys=True)+'\n')
        with self.assertRaisesRegex(ValueError,'pin omitted'):self.invoke()
        self.assertEqual(self.calls,[]);self.assertFalse((self.root/m.CLAIM).exists())
    def test_changed_original_export_authority_aborts_before_claim_or_launch(self):
        (self.root/'old-report.json').write_text('changed')
        with self.assertRaises(ValueError):self.invoke()
        self.assertEqual(self.calls,[]);self.assertFalse((self.root/m.CLAIM).exists())


if __name__=='__main__':unittest.main()
