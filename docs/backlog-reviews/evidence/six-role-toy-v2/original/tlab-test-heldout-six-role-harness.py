"""Pure harness contracts only: no fit, native object or worker process launch."""
from copy import deepcopy
import importlib.util
import json
import os
import py_compile
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path('/tmp/tlab-run-heldout-six-role-toy.py')
spec = importlib.util.spec_from_file_location('tlab_six_role_harness', PATH)
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)


def freeze():
    return dict(version=1, scope='synthetic_six_role_harness_code_only_no_execution_authority',
        isolated_root='/tmp/tlab heldout six role integration 20261015',
        harness_files={name:h.sha(name) for name in h.HARNESS_FILES}, production_files={name:h.sha(h.PROJECT/name) for name in h.public_files()},
        python=str(h.PROJECT/'.venv/bin/python'), runtime=dict(venv=str(h.PROJECT/'.venv'),
            pyvenv_config=str(h.PROJECT/'.venv/pyvenv.cfg'), pyvenv_config_sha256=h.sha(h.PROJECT/'.venv/pyvenv.cfg')),
        disclosures=deepcopy(h.DISCLOSURES))


def periods():
    estimands = ['conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero']
    metric = {name:dict(recall=.5,ndcg=.25,average_precision=.25,reciprocal_rank=.5) for name in estimands}
    bootstrap = {name:dict(estimand=name,metric='ndcg',seed=2026,replicates=200,estimate=0,
        samples=[0.0]*199+[None],undefined_draws=1,interval_95=[0.0,0.0]) for name in estimands}
    body = dict(metrics=dict(B=deepcopy(metric),W=deepcopy(metric)),ndcg_W_minus_B=dict.fromkeys(estimands,0),paired_user_bootstrap=bootstrap)
    return dict(confirmation25_reporting_only=deepcopy(body),final26_31_frozen=deepcopy(body))


class HarnessContracts(unittest.TestCase):
    def test_setup_builder_resolved_private_tmp_alias_uses_original_lexical_pin_before_native_work(self):
        """Exercise actual build admission; stop at mocked consumption before any fit/fence."""
        from types import ModuleType
        builder=ModuleType('tlab_builder_alias_contract');builder.__file__=str(h.BUILDER.resolve())
        raw=h.BUILDER.read_bytes();exec(compile(raw,str(h.BUILDER),'exec',dont_inherit=True),builder.__dict__)
        self.assertEqual(Path(builder.__file__).resolve(),h.BUILDER.resolve())
        class StopAtConsumed(BaseException):pass
        with tempfile.TemporaryDirectory(prefix='tlab setup alias contract ',dir='/tmp') as base:
            root=Path(base)/'isolated setup root';root.mkdir();pins={str(h.BUILDER):h.sha(h.BUILDER)}
            path=Path(base)/'freeze.json';path.write_text(json.dumps(dict(isolated_root=str(root),harness_files=pins)))
            seen=[]
            def stop(path,body):seen.append((path,body));raise StopAtConsumed()
            with patch.object(builder.resource,'getrusage',return_value=SimpleNamespace(ru_utime=0,ru_stime=0)),patch.object(builder.resource,'setrlimit',side_effect=AssertionError('No actual fence/native/fit allowed')),patch.object(builder,'exclusive',side_effect=stop):
                with self.assertRaises(StopAtConsumed):builder.build(root,path,h.sha(path))
            self.assertEqual(len(seen),1);self.assertEqual(seen[0][1]['fit_attempt_count'],1)
            self.assertEqual(seen[0][0],root.resolve()/'fixture-setup/attempt.consumed.json')
            builder.__file__=str(Path(base)/'other-builder.py')
            with patch.object(builder.resource,'getrusage',return_value=SimpleNamespace(ru_utime=0,ru_stime=0)),patch.object(builder,'exclusive',side_effect=AssertionError('Wrong builder identity must fail before consumption')):
                with self.assertRaisesRegex(ValueError,'setup source identity'):builder.build(root,path,h.sha(path))
    def test_source_literal_exact_BIGINT_duplicate_ties_and_NULLs(self):
        rows=h.toy_events();self.assertEqual(len(rows),11);self.assertEqual(rows[1],rows[2])
        self.assertEqual(rows[0][2],None);self.assertEqual(rows[0][3],2**60+1);self.assertIs(type(rows[0][3]),int)
        self.assertEqual(rows[4][0],rows[5][0]);self.assertEqual(rows[5][-1],None)
        self.assertLess(max(row[0] for row in rows),'2019-10-29')
    def test_supervisor_module_dynamic_import_has_no_process_or_native_execution(self):
        module=h.processes(h.sha(h.PROCESSES));self.assertEqual(module._UNREAPED,{})
        self.assertTrue(callable(module.supervise));self.assertEqual(module.BSDInfo.start_sec.offset,120)
    def test_pinned_supervisor_source_executes_even_with_valid_wrong_timestamp_size_pyc(self):
        with tempfile.TemporaryDirectory(prefix='tlab pinned source cache ',dir='/tmp') as base:
            source=Path(base)/'supervisor.py';source.write_bytes(b'MARKER="OTHER!"\n');os.utime(source,(1700000000,1700000000))
            py_compile.compile(str(source),doraise=True);source.write_bytes(b'MARKER="PINNED"\n');os.utime(source,(1700000000,1700000000))
            with patch.object(h,'PROCESSES',source):
                digest=h.sha(source);self.assertEqual(h.processes(digest).MARKER,'PINNED')
                source.write_bytes(b'MARKER="EDITED"\n')
                with self.assertRaisesRegex(ValueError,'source bytes changed'):h.processes(digest)
    def test_frozen_public_copy_has_only_declared_CODE_and_public_configs(self):
        f=freeze();self.assertEqual(h.verify_harness(f),f)
        self.assertEqual(len(h.public_files()),len(set(h.public_files())))
        with tempfile.TemporaryDirectory(prefix='tlab copy contracts ',dir='/tmp') as base:
            root=Path(base)/'new isolated copy';h.create_copy(root,f)
            self.assertFalse((root/'data').exists());self.assertFalse((root/'artifacts').exists())
            self.assertTrue((root/'.venv').is_symlink());self.assertEqual((root/'.venv').resolve(),(h.PROJECT/'.venv').resolve())
            for name,digest in f['production_files'].items():self.assertEqual(h.sha(root/name),digest)
            with self.assertRaisesRegex(ValueError,'Exclusive'):h.create_copy(root,f)
    def test_frozen_harness_and_dependency_mutation_reject(self):
        f=freeze();f['harness_files'][str(PATH)]='0'*64
        with self.assertRaisesRegex(ValueError,'harness bytes'):h.verify_harness(f)
        f=freeze();f['production_files'].pop('scripts/ranking_metrics.py')
        with self.assertRaisesRegex(ValueError,'closure'):h.verify_harness(f)
        f=freeze();f['harness_files'].pop(str(h.PROCESSES))
        with self.assertRaisesRegex(ValueError,'five-file'):h.verify_harness(f)
    def test_original_freeze_transport_SHA_not_self_authored_contents_is_authority(self):
        with tempfile.TemporaryDirectory(prefix='tlab freeze transport ') as base:
            path=Path(base)/'freeze.json';path.write_text(json.dumps(freeze()));digest=h.sha(path)
            h.load_freeze(path,digest)
            path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'freeze bytes changed'):h.load_freeze(path,digest)
            with self.assertRaisesRegex(ValueError,'SHA required'):h.load_freeze(path,True)
    def test_original_freeze_is_parsed_from_same_snapshot_not_separate_hash_then_reread(self):
        with tempfile.TemporaryDirectory(prefix='tlab freeze bound snapshot ',dir='/tmp') as base:
            path=Path(base)/'freeze.json';f=freeze();path.write_text(json.dumps(f));digest=h.sha(path);original_sha=h.sha
            def swap_after_hash(candidate):
                result=original_sha(candidate)
                if Path(candidate)==path:path.write_text(json.dumps(dict(f,isolated_root='/tmp/alternate isolated root')))
                return result
            with patch.object(h,'sha',side_effect=swap_after_hash):parsed=h.load_freeze(path,digest)
            self.assertEqual(parsed['isolated_root'],f['isolated_root'])
    def test_alternate_root_cannot_refill_original_reviewed_finite_harness(self):
        with tempfile.TemporaryDirectory(prefix='tlab reviewed namespace ',dir='/tmp') as base:
            path=Path(base)/'freeze.json';path.write_text(json.dumps(freeze()));alternate=Path(base)/'different isolated root'
            with patch.object(h,'processes',side_effect=AssertionError('No process launcher may be consulted')), self.assertRaisesRegex(ValueError,'cannot be replaced'):
                h.supervise('setup',alternate,path,h.sha(path))
            self.assertFalse(alternate.exists())
    def test_mandatory_synthetic_disclosures_cannot_claim_real_authentication(self):
        f=freeze();f['disclosures']['historical_authentication_exercised']=True
        with self.assertRaisesRegex(ValueError,'disclosure'):h.verify_harness(f)
        self.assertEqual(h.DISCLOSURES['actual_training_rows'],8);self.assertEqual(h.DISCLOSURES['protocol_population_literal'],26000)
    def test_copy_checks_original_source_before_import_or_private_copy(self):
        f=freeze();f['production_files']['scripts/run_heldout_reporting.py']='0'*64
        with tempfile.TemporaryDirectory(prefix='tlab changed copy ',dir='/tmp') as base:
            root=Path(base)/'isolated root'
            with self.assertRaisesRegex(ValueError,'production bytes'):h.create_copy(root,f)
            self.assertTrue(root.is_dir());self.assertFalse((root/'data').exists())
            with self.assertRaisesRegex(ValueError,'Exclusive'):h.create_copy(root,freeze())
    def test_outside_root_and_root_alias_rejected(self):
        for name in ['/Users/mdpospelov/not allowed','/tmp','/tmp/no-spaces']:
            with self.subTest(name=name),self.assertRaises(ValueError):h.safe_root(name)
    def test_complete_W_B_vectors_zero_deltas_all_draws_and_undefined_retained(self):
        p=periods();self.assertEqual(h.validate_deltas(p),8)
        for period in p.values():
            for bootstrap in period['paired_user_bootstrap'].values():
                bootstrap.update(estimate=None,samples=[None]*200,undefined_draws=200,interval_95=None)
            period['ndcg_W_minus_B']=dict.fromkeys(period['ndcg_W_minus_B'],None)
        self.assertEqual(h.validate_deltas(p),8)
    def test_nonzero_metric_sample_or_missing_estimand_cannot_pass_B_reuse(self):
        for mode in ['metric','delta','sample','omitted','undefined','count','interval']:
            p=periods();period=p['final26_31_frozen'];name='conditional_macro_query';b=period['paired_user_bootstrap'][name]
            if mode=='metric':period['metrics']['W'][name]['ndcg']=.3
            elif mode=='delta':period['ndcg_W_minus_B'][name]=.01
            elif mode=='sample':b['samples'][0]=.01
            elif mode=='omitted':period['ndcg_W_minus_B'].pop(name)
            elif mode=='undefined':b['undefined_draws']=0
            elif mode=='count':b['samples'].pop()
            else:b['interval_95']=[0.,.1]
            with self.subTest(mode=mode),self.assertRaises(ValueError):h.validate_deltas(p)
    def test_second_resolution_real_UTC_no_fabricated_future(self):
        from datetime import datetime,timezone
        value=h.utc_now();self.assertEqual(len(value),20);self.assertNotIn('.',value)
        self.assertLessEqual(datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc),datetime.now(timezone.utc))
    def test_strict_harness_JSON_rejects_duplicate_or_nonfinite(self):
        with tempfile.TemporaryDirectory(prefix='tlab JSON contracts ') as base:
            path=Path(base)/'bad.json'
            for raw in ['{"a":1,"a":2}','{"a":NaN}','{"a":1e999}']:
                path.write_text(raw)
                with self.subTest(raw=raw),self.assertRaises(ValueError):h.read(path)
    def test_initial_test_gate_waits_original_zero_completed_roles_and_calls_real_checker(self):
        with tempfile.TemporaryDirectory(prefix='tlab gate contracts ') as base:
            root=Path(base);path=root/'artifacts/acceptance/initial.json';calls=[];trace=[]
            owner=SimpleNamespace(local=lambda name:root/name,closure=lambda session:session.plan['fingerprints'])
            session=SimpleNamespace(states=[],active=None,plan=dict(run_id='a'*64,fingerprints={'copied.py':'b'*64}))
            prepared=dict(request=dict(authority_paths=dict(initial_execution=str(path.relative_to(root)))))
            def checker(session,prepared,name,expected):
                body=h.read(path);self.assertEqual(body,expected(body));calls.append(name);return body
            def expected(body):return dict(version=1,approved=True,scope='reserved_source_inference_execution',run_id='a'*64,fingerprints={'copied.py':'b'*64})
            callback=h.issuer(owner,checker,trace);callback(session,prepared,'initial_execution',expected)
            self.assertEqual(calls,['initial_execution']);self.assertTrue(trace[0]['self_issued_synthetic'])
            with self.assertRaisesRegex(ValueError,'reissued'):callback(session,prepared,'initial_execution',expected)
    def test_source_test_gate_cannot_arrive_before_two_actually_completed_roles(self):
        with tempfile.TemporaryDirectory(prefix='tlab early gate ') as base:
            root=Path(base);owner=SimpleNamespace(local=lambda name:root/name);calls=[]
            session=SimpleNamespace(states=[dict(role='source')],active=None)
            prepared=dict(request=dict(authority_paths=dict(source_acceptance='artifacts/acceptance/source.json')))
            with self.assertRaisesRegex(ValueError,'actual reaped'):h.issuer(owner,lambda *args:calls.append(args),[])(session,prepared,'source_acceptance',lambda body:body)
            self.assertEqual(calls,[]);self.assertFalse((root/'artifacts').exists())
    def test_two_finite_supervisor_stages_bind_original_freeze_and_never_refill(self):
        """Mocked process boundary only; dummy model bytes are never native-loaded."""
        with tempfile.TemporaryDirectory(prefix='tlab two stage contract ',dir='/tmp') as base:
            root=Path(base)/'isolated native fixture';f=freeze();f['isolated_root']=str(root)
            path=Path(base)/'freeze.json';path.write_text(json.dumps(f));digest=h.sha(path);calls=[]
            def fake_supervise(argv,log,**kwargs):
                calls.append(argv);Path(log).write_text('MOCKED PROCESS ONLY\n')
                if len(calls)==1:
                    (root/'fixture-setup').mkdir();(root/'fixture-setup/B.cbm').write_bytes(b'NO NATIVE MODEL')
                    h.exclusive(root/'fixture-setup/model-spec.json',dict(synthetic='not native'))
                    h.exclusive(root/'fixture-setup/result.json',dict(status='setup_complete_pending_external_exit_tail',fit_attempt_count=1,training_rows=8,child_cpu_seconds=.3))
                else:
                    h.exclusive(root/'integration-result.json',dict(**h.DISCLOSURES,status='six_roles_complete_pending_supervisor_exit_tail',unknown_active_work=False,actual_total_cpu_seconds=.4))
                return dict(status='verified_normal_exit',exit_code=0,wait4_child_cpu_seconds=.5,actual_total_cpu_seconds=None,
                    cpu_upper_seconds=3,elapsed_seconds=1,elapsed_upper_seconds=6,observed_job_peak_rss_bytes=100,unknown_active_work=False)
            with patch.object(h,'processes',return_value=SimpleNamespace(supervise=fake_supervise)):
                h.supervise('setup',root,path,digest);h.supervise('integration',root,path,digest)
                with self.assertRaises(FileExistsError):h.supervise('integration',root,path,digest)
            self.assertEqual(len(calls),2);self.assertIn('--child',calls[1]);self.assertNotIn('--child',calls[0])
            for argv in calls:self.assertEqual(argv[argv.index('--issued-freeze-sha256')+1],digest)
            ledger=h.read(root/'harness-ledger.json');self.assertFalse(ledger['exact_supervisor_exit_tail_measured']);self.assertEqual(ledger['total_job_cpu_upper_seconds'],6)
            self.assertFalse((root/'integration-supervision.failed.json').exists())
    def test_failed_unknown_boundary_preserves_consumption_and_never_creates_success_ledger(self):
        with tempfile.TemporaryDirectory(prefix='tlab stage failure contract ',dir='/tmp') as base:
            root=Path(base)/'isolated failure fixture';f=freeze();f['isolated_root']=str(root)
            path=Path(base)/'freeze.json';path.write_text(json.dumps(f));calls=[]
            def fake_supervise(*args,**kwargs):
                calls.append(args);return dict(status='failed_unknown_cleanup',exit_code=None,unknown_active_work=True)
            with patch.object(h,'processes',return_value=SimpleNamespace(supervise=fake_supervise)):
                with self.assertRaisesRegex(ValueError,'Consumed synthetic stage failed'):h.supervise('setup',root,path,h.sha(path))
                with self.assertRaisesRegex(ValueError,'Exclusive'):h.supervise('setup',root,path,h.sha(path))
            self.assertEqual(len(calls),1);self.assertTrue((root/'setup-supervisor.consumed.json').exists())
            self.assertEqual(h.read(root/'setup-supervision.failed.json')['status'],'failed_consumed_no_retry');self.assertFalse((root/'harness-ledger.json').exists())
    def test_primary_cancellation_retains_supervisor_cleanup_evidence_in_consumed_failure(self):
        with tempfile.TemporaryDirectory(prefix='tlab cancellation contract ',dir='/tmp') as base:
            root=Path(base)/'isolated cancelled fixture';f=freeze();f['isolated_root']=str(root)
            path=Path(base)/'freeze.json';path.write_text(json.dumps(f));primary=KeyboardInterrupt('original cancellation')
            primary.supervisor_cleanup_evidence=dict(status='failed',reaped=True,direct_child_inclusive_cpu=3,cleanup_nested_unknown=True)
            with patch.object(h,'processes',return_value=SimpleNamespace(supervise=unittest.mock.Mock(side_effect=primary))):
                with self.assertRaises(KeyboardInterrupt) as caught:h.supervise('setup',root,path,h.sha(path))
            self.assertIs(caught.exception,primary);body=h.read(root/'setup-supervision.failed.json')
            self.assertEqual(body['process_cleanup_evidence'],primary.supervisor_cleanup_evidence);self.assertTrue(body['unknown_active_work'])
            self.assertFalse((root/'harness-ledger.json').exists())


if __name__ == '__main__':unittest.main(verbosity=2)
