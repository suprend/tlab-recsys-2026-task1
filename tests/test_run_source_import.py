"""Owner mechanics only: bounded synthetic bytes/fake child, no archive import."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

from scripts import run_source_import as m


class Owner(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.root_patch=patch.object(m,'ROOT',self.root);self.root_patch.start();self.addCleanup(self.root_patch.stop)
        for name in m.CODE:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('fixture '+name).encode())
        self.archive=self.root/'data/raw/local.csv.gz';self.archive.parent.mkdir(parents=True);self.archive.write_bytes(b'synthetic mocked archive bytes')
        self.profile=dict(scope='synthetic_typed9_import_fixture',compressed_sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.request=dict(version=1,scope='externally_reviewed_typed9_source_import',execution_id='tiny-1',archive='data/raw/local.csv.gz',profile=self.profile,
            output_directory='artifacts/source-import-runs/tiny-1',resources=dict(m.RESOURCE_FIXED,cpu_seconds=60,wall_seconds=60),
            fingerprints={name:hashlib.sha256((self.root/name).read_bytes()).hexdigest() for name in m.CODE})
        self.request_name='artifacts/reproduction/import-request.json';self.save_request();self.started=time.monotonic()
        self.reaped=False;self.childcalls=[];self.owner_cpu=.1
        self.mockusage=patch.object(m,'usage',side_effect=self.usage);self.mockusage.start();self.addCleanup(self.mockusage.stop)
    def usage(self,kind=m.resource.RUSAGE_SELF):return (.25,2**20) if kind==m.resource.RUSAGE_CHILDREN and self.reaped else (0,0) if kind==m.resource.RUSAGE_CHILDREN else (self.owner_cpu,2**20)
    def save_request(self):
        path=self.root/self.request_name;path.parent.mkdir(parents=True,exist_ok=True);raw=(m.canonical(self.request)+'\n').encode();path.write_bytes(raw);self.request_sha=hashlib.sha256(raw).hexdigest()
    def consume(self):return m.consume(self.request_name,self.request_sha,started=self.started)
    def env(self,check,**kwargs):
        check();return dict(python='3.12.14',platform='darwin',architecture='arm64',duckdb='1.5.6',lock_sha256=self.request['fingerprints']['uv.lock'],
            kernel_cpu=kwargs.get('kernel_cpu'),subprocess_probe=False,engine_settings=dict(threads=2,memory='2GB',spill_bytes=8*2**30))
    def fake_child(self,argv,log_path,budget,allocation):
        self.childcalls.append(argv);self.assertIn('-I',argv);self.assertEqual(argv[3],str(self.root/'scripts/run_source_import.py'))
        context_name=argv[5];context,context_ref=m.read_json(context_name,argv[7]);directory=self.root/context['directory'];kernel=directory/'kernel';kernel.mkdir()
        log_path.write_bytes(b'fake child no actual source/model/sql\n')
        outputs={}
        for name in ['import-evidence.json','events.duckdb','source.csv.gz','source.csv','validated.csv','import.consumed.json']:
            path=kernel/name;path.write_bytes(('bounded fake '+name).encode());outputs[m.relative(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        now=time.monotonic();consumed=m.exclusive(directory/'worker.consumed.json',dict(version=1,scope='consumed_typed9_import_worker',context=context_ref,
            request=context['request'],claim=context['claim'],started_monotonic=now,retry=False))
        env=self.env(budget.guard,kernel_cpu=dict(soft=allocation['cpu_seconds']-1,hard=allocation['cpu_seconds']))
        m.exclusive(directory/'worker-receipt.json',dict(version=1,status='source_import_worker_complete_unaccepted',execution_id='tiny-1',request=context['request'],claim=context['claim'],
            context=context_ref,consumed=consumed,outputs=outputs,spill_observation=dict(retained_bytes=0,retained_files=0,peak_measured=False),evidence=dict(path=m.relative(kernel/'import-evidence.json'),sha256=outputs[m.relative(kernel/'import-evidence.json')]),environment=env,
            started_monotonic=now,finished_monotonic=time.monotonic(),process_cpu_seconds=.2,process_peak_rss_bytes=2**20,descendant_cpu_seconds=0,fit_attempt_count=0,labels_created=False,source_acceptance_issued=False))
        self.reaped=True;return 0
    def execute_owner(self,child=None):
        with patch.object(m,'environment',side_effect=self.env),patch.object(m,'load_kernel',return_value=Mock()),patch.object(m,'supervise',side_effect=self.fake_child if child is None else child):
            return m.run_owner(self.request_name,self.request_sha,started=self.started)
    def failed(self):return self.root/self.request['output_directory']/'report.failed.json'
    def test_original_claim_precedes_any_paid_hash(self):
        with patch.object(m,'hash_file',side_effect=AssertionError('paid hash before consume')):
            body,request,claim,directory,budget=self.consume()
        self.assertTrue((self.root/claim['path']).exists());self.assertFalse(directory.exists());self.assertEqual(body,self.request)
    def test_wrong_external_request_sha_fails_before_claim(self):
        with self.assertRaisesRegex(ValueError,'Original metadata SHA'):m.consume(self.request_name,'0'*64,started=self.started)
        self.assertFalse((self.root/'artifacts/source-import-owner').exists())
    def test_same_execution_id_remains_consumed_even_changed_output_request(self):
        self.consume();self.request['archive']='data/raw/other.gz';(self.root/self.request['archive']).write_bytes(b'new');self.save_request()
        with self.assertRaises(FileExistsError):self.consume()
    def test_changing_output_root_is_not_retry(self):
        self.request['output_directory']='artifacts/source-import-runs/new-root';self.save_request()
        with self.assertRaisesRegex(ValueError,'Fixed original import output'):self.consume()
    def test_prior_child_usage_rejects_fresh_owner(self):
        self.reaped=True
        with self.assertRaisesRegex(ValueError,'Fresh dedicated'):self.consume()
    def test_existing_output_and_escape_symlink_refused(self):
        output=self.root/self.request['output_directory'];output.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'cannot be reused'):self.consume()
        (self.root/'data/raw/link.gz').symlink_to(self.archive);self.request['archive']='data/raw/link.gz';self.save_request()
        with self.assertRaisesRegex(ValueError,'Symlink'):self.consume()
    def test_exact_limits_reject_bool_cpu_and_changed_spill(self):
        for key,value in [('cpu_seconds',True),('spill_bytes',1)]:
            body=deepcopy(self.request);body['resources'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_request(body)
    def test_exact_code_closure_rejects_missing_or_extra(self):
        for pins in [{k:v for k,v in self.request['fingerprints'].items() if k!='uv.lock'},dict(self.request['fingerprints'],unexpected='0'*64)]:
            body=deepcopy(self.request);body['fingerprints']=pins
            with self.assertRaisesRegex(ValueError,'code closure'):m.validate_request(body)
    def test_budget_uses_absolute_owner_plus_reaped_cpu_and_original_clock(self):
        self.reaped=True;budget=m.Budget(self.request['resources'],self.started);self.assertEqual(budget.cpu(),.35)
        self.assertEqual(budget.allocation()['deadline_monotonic'],self.started+50)
        self.owner_cpu=59
        with self.assertRaises(TimeoutError):budget.guard(final=True)
    def test_expired_budget_cannot_create_claim(self):
        with self.assertRaises(TimeoutError):m.consume(self.request_name,self.request_sha,started=self.started-70)
        self.assertFalse((self.root/'artifacts/source-import-owner/claims/tiny-1.json').exists())
    def test_changed_code_after_claim_fails_before_child_and_cannot_repeat(self):
        (self.root/'scripts/source_import.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Original file changed'):self.execute_owner()
        self.assertTrue(self.failed().exists());self.assertEqual(self.childcalls,[])
        with self.assertRaisesRegex(ValueError,'cannot be reused'):self.execute_owner()
    def test_bounded_fake_child_full_owner_pending_external_exit_only(self):
        report=self.execute_owner();self.assertEqual(len(self.childcalls),1);self.assertTrue(report['worker_reaped']);self.assertEqual(report['actual_reaped_worker_cpu_seconds'],.25)
        self.assertEqual(report['status'],'completed_source_import_pending_external_source_acceptance');self.assertFalse(report['source_acceptance_issued']);self.assertTrue(report['full_owner_exit_acceptance_required'])
        self.assertFalse(self.failed().exists());self.assertEqual(report['fit_attempt_count'],0)
    def test_missing_receipt_fails_without_refill(self):
        def child(*args):self.reaped=True;args[1].write_bytes(b'failed fake child');return 0
        with self.assertRaises(ValueError):self.execute_owner(child)
        self.assertTrue(self.failed().exists());self.assertFalse((self.root/self.request['output_directory']/'report.json').exists())
    def test_child_error_preserves_primary_and_consumption(self):
        def child(*args):raise RuntimeError('primary child failure')
        with self.assertRaisesRegex(RuntimeError,'primary child failure'):self.execute_owner(child)
        self.assertTrue(self.failed().exists());self.assertTrue((self.root/'artifacts/source-import-owner/claims/tiny-1.json').exists())
    def test_unreaped_cost_or_job_peak_cannot_promote_receipt(self):
        def child(*args):self.fake_child(*args);self.reaped=False;return 0
        with self.assertRaisesRegex(ValueError,'actual reaped lifetime'):self.execute_owner(child)
        self.assertTrue(self.failed().exists())
    def test_changed_receipt_after_persistence_cannot_report_complete(self):
        def child(*args):
            self.fake_child(*args);path=self.root/self.request['output_directory']/'worker-receipt.json';body=json.loads(path.read_text());body['labels_created']=True;path.write_text(m.canonical(body));return 0
        with self.assertRaisesRegex(ValueError,'forbidden downstream'):self.execute_owner(child)
        self.assertTrue(self.failed().exists())
    def test_missing_output_partition_rejects_before_completion(self):
        def child(*args):
            self.fake_child(*args);path=self.root/self.request['output_directory']/'worker-receipt.json';body=json.loads(path.read_text());body['outputs'].pop(self.request['output_directory']+'/kernel/source.csv');path.write_text(m.canonical(body));return 0
        with self.assertRaisesRegex(ValueError,'output closure'):self.execute_owner(child)
        self.assertTrue(self.failed().exists())
    def test_late_original_archive_substitution_fails_terminal_pin(self):
        def child(*args):self.fake_child(*args);self.archive.write_bytes(b'changed after fake import');return 0
        with self.assertRaisesRegex(ValueError,'Original file changed'):self.execute_owner(child)
        self.assertTrue(self.failed().exists())
    def test_late_report_mutation_is_detected(self):
        original=m.exclusive
        def write(path,body):
            ref=original(path,body)
            if path.name=='report.json':path.write_bytes(b'{"changed":true}\n')
            return ref
        with patch.object(m,'exclusive',side_effect=write),self.assertRaisesRegex(ValueError,'Original file changed'):self.execute_owner()
        self.assertTrue(self.failed().exists())
    def test_private_worker_requires_actual_owner_parent_before_archive_work(self):
        body,request,claim,directory,budget=self.consume();directory.mkdir();pins=dict(body['fingerprints'],**{request['path']:request['sha256'],claim['path']:claim['sha256']})
        context=m.exclusive(directory/'worker-context.json',dict(version=1,scope='owned_typed9_source_import_worker',execution_id='tiny-1',request=request,claim=claim,directory=body['output_directory'],allocation=budget.allocation(),fingerprints=pins,owner_pid=999999))
        with self.assertRaisesRegex(ValueError,'actual original owner parent'):m.worker(context['path'],context['sha256'])
        self.assertFalse((directory/'kernel').exists());self.assertFalse((directory/'report.failed.json').exists())
    def test_namespace_init_sideeffect_is_rejected_before_kernel_import(self):
        (self.root/'scripts/__init__.py').write_text('raise RuntimeError("unlisted side effect")')
        with self.assertRaisesRegex(ValueError,'Unexpected scripts package'):m.load_kernel(lambda:None,expected_sha=self.request['fingerprints']['scripts/source_import.py'])

    def test_duplicate_JSON_keys_refuse_before_claim(self):
        raw=('{'+'"version":1,"version":1}').encode();(self.root/self.request_name).write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'Duplicate JSON'):m.consume(self.request_name,hashlib.sha256(raw).hexdigest(),started=self.started)
        self.assertFalse((self.root/'artifacts/source-import-owner').exists())
    def test_parent_persistent_guard_refuses_known_failure_marker(self):
        body,request,claim,directory,budget=self.consume();directory.mkdir();budget.directory=directory;(directory/'report.failed.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Known failed original'):budget.guard(final=True)

    def test_timestamp_valid_unpinned_bytecode_is_not_executed(self):
        import importlib._bootstrap_external as be
        import importlib.util
        source=self.root/'scripts/source_import.py';pinned=b"marker = 'PINNED'\n";other=b"marker = 'OTHER!'\n";self.assertEqual(len(pinned),len(other));source.write_bytes(pinned)
        cache=Path(importlib.util.cache_from_source(str(source)));cache.parent.mkdir();cache.write_bytes(be._code_to_timestamp_pyc(compile(other,str(source),'exec'),int(source.stat().st_mtime),len(pinned)))
        expected=hashlib.sha256(pinned).hexdigest();m.repin({'scripts/source_import.py':expected},lambda:None)
        self.assertEqual(m.load_kernel(lambda:None,expected_sha=expected).marker,'PINNED')
    def test_loader_rejects_changed_source_before_executing_it(self):
        source=self.root/'scripts/source_import.py';source.write_bytes(b"raise RuntimeError('must not execute')\n")
        with self.assertRaisesRegex(ValueError,'kernel source snapshot'):m.load_kernel(lambda:None,expected_sha='0'*64)
    def test_infeasible_allocation_refuses_before_claim(self):
        self.owner_cpu=44
        with self.assertRaisesRegex(ValueError,'No remaining bounded worker'):self.consume()
        self.assertFalse((self.root/'artifacts/source-import-owner/claims/tiny-1.json').exists())
    def test_CPU20_lower_endpoint_refuses_before_claim(self):
        self.request['resources']['cpu_seconds']=20;self.save_request()
        with self.assertRaisesRegex(ValueError,'original CPU/wall'):self.consume()
        self.assertFalse((self.root/'artifacts/source-import-owner/claims/tiny-1.json').exists())


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.patchroot=patch.object(m,'ROOT',self.root);self.patchroot.start();self.addCleanup(self.patchroot.stop)
        self.patchusage=patch.object(m,'usage',return_value=(.1,1024));self.patchusage.start();self.addCleanup(self.patchusage.stop)
        self.log=self.root/'worker.log';self.budget=Mock();self.budget.limits=dict(m.RESOURCE_FIXED);self.allocation=dict(deadline_monotonic=time.monotonic()+5)
    class Process:
        pid=12345
        def __init__(self,exit_code=0,live=False):self.returncode=exit_code;self.live=live;self.waited=0
        def poll(self):return self.returncode
        def wait(self,timeout=None):self.waited+=1;return self.returncode
    def test_normal_process_is_explicitly_waited_and_group_gone(self):
        process=self.Process()
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=ProcessLookupError):
            self.assertEqual(m.supervise(['fixed'],self.log,self.budget,self.allocation),0)
        self.assertGreaterEqual(process.waited,2);self.assertEqual(self.log.stat().st_mode&0o777,0o600)
    def test_primary_deadline_survives_successful_cleanup_and_reap(self):
        process=self.Process(exit_code=None,live=True)
        def kill(pid,sig):
            if not process.live:raise ProcessLookupError
            if sig:process.live=False;process.returncode=-15
        self.budget.guard.side_effect=TimeoutError('original deadline')
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(TimeoutError,'original deadline'):
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        self.assertGreaterEqual(process.waited,1);self.assertFalse(process.live)
    def test_cleanup_unknown_is_persisted_and_primary_preserved(self):
        process=self.Process(exit_code=None,live=True);process.wait=Mock(side_effect=m.subprocess.TimeoutExpired('fixed',5));self.budget.guard.side_effect=RuntimeError('primary guard failure')
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg'),self.assertRaisesRegex(RuntimeError,'primary guard failure') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        self.assertIn('Import process cleanup',str(caught.exception.__notes__));body=json.loads(Path(str(self.log)+'.cleanup-failed.json').read_text());self.assertEqual(body['status'],'unknown_owned_process_usage')
    def test_surviving_descendant_after_leader_exit_is_unknown_even_cleanup_succeeds(self):
        process=self.Process(exit_code=0,live=True)
        def kill(pid,sig):
            if not process.live:raise ProcessLookupError
            if sig:process.live=False
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(RuntimeError,'usage unknown'):
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        self.assertTrue(Path(str(self.log)+'.descendants-failed.json').exists());self.assertFalse(process.live)
    def test_nonzero_exit_is_not_silently_promoted(self):
        process=self.Process(exit_code=7)
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=ProcessLookupError),self.assertRaisesRegex(ValueError,'did not exit0'):
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
    def test_live_log_overflow_terminates_and_reaps(self):
        process=self.Process(exit_code=None,live=True)
        def launch(*args,**kwargs):self.log.write_bytes(b'x'*(2**20+1));return process
        def kill(pid,sig):
            if not process.live:raise ProcessLookupError
            if sig:process.live=False;process.returncode=-15
        with patch.object(m.subprocess,'Popen',side_effect=launch),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(RuntimeError,'log allowance'):
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        self.assertFalse(process.live)
    def test_worker_CPU_fence_setup_readback_without_real_limit_change(self):
        allocation=dict(cpu_seconds=20,deadline_monotonic=time.monotonic()+5,rss_bytes=7*2**30);budget=m.WorkerBudget(allocation);thread=Mock()
        with patch.object(m,'usage',side_effect=lambda kind=m.resource.RUSAGE_SELF:(0,0) if kind==m.resource.RUSAGE_CHILDREN else (.1,1024)),patch.object(m.resource,'getrlimit',side_effect=[(m.resource.RLIM_INFINITY,m.resource.RLIM_INFINITY),(19,20)]),patch.object(m.resource,'setrlimit') as setting,patch.object(m.threading,'Thread',return_value=thread):
            budget.start();setting.assert_called_once_with(m.resource.RLIMIT_CPU,(19,20));self.assertEqual(budget.kernel_cpu,dict(soft=19,hard=20));thread.start.assert_called_once()
    def test_worker_guard_absolute_CPU_deadline_and_prior_children(self):
        allocation=dict(cpu_seconds=20,deadline_monotonic=time.monotonic()+5,rss_bytes=7*2**30);budget=m.WorkerBudget(allocation)
        with patch.object(m,'usage',side_effect=lambda kind=m.resource.RUSAGE_SELF:(0,0) if kind==m.resource.RUSAGE_CHILDREN else (19,1024)),self.assertRaises(TimeoutError):budget.guard()
        with patch.object(m,'usage',side_effect=lambda kind=m.resource.RUSAGE_SELF:(0,1) if kind==m.resource.RUSAGE_CHILDREN else (.1,1024)),self.assertRaisesRegex(ValueError,'descendants'):budget.guard()
    def test_spill_counts_are_retained_bytes_and_do_not_claim_peak(self):
        spill=self.root/'kernel/spill';spill.mkdir(parents=True);(spill/'tiny').write_bytes(b'123')
        self.assertEqual(m.retained_spill(self.root,lambda:None),dict(retained_bytes=3,retained_files=1,peak_measured=False))
    def test_spill_symlink_is_rejected(self):
        spill=self.root/'kernel/spill';spill.mkdir(parents=True);(spill/'escape').symlink_to(self.log)
        with self.assertRaisesRegex(ValueError,'regular spill'):m.retained_spill(self.root,lambda:None)

    def test_final_guard_failure_keeps_unknown_descendant_usage_after_cleanup(self):
        process=self.Process(exit_code=0,live=True)
        def kill(pid,sig):
            if not process.live:raise ProcessLookupError
            if sig:process.live=False
        self.budget.guard.side_effect=TimeoutError('original final deadline')
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(TimeoutError,'original final deadline') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);report=json.loads((self.root/'report.failed.json').read_text())
        self.assertTrue(report['unknown_owned_process_usage']);self.assertFalse(process.live);self.assertTrue(Path(str(self.log)+'.descendants-failed.json').exists())
    def test_failed_unknown_marker_write_preserves_primary_and_unknown_flag(self):
        process=self.Process(exit_code=0,live=True)
        def kill(pid,sig):
            if not process.live:raise ProcessLookupError
            if sig:process.live=False
        self.budget.guard.side_effect=TimeoutError('original final deadline');original=m.exclusive
        def write(path,body):
            if str(path).endswith('.descendants-failed.json'):raise OSError('marker persistence failure')
            return original(path,body)
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),patch.object(m,'exclusive',side_effect=write),self.assertRaisesRegex(TimeoutError,'original final deadline') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertTrue(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage']);self.assertIn('Unknown usage persistence',str(caught.exception.__notes__))

    def test_cleanup_and_marker_failure_keep_unknown_in_primary(self):
        process=self.Process(exit_code=None,live=True);process.wait=Mock(side_effect=m.subprocess.TimeoutExpired('fixed',5));self.budget.guard.side_effect=TimeoutError('original deadline');original=m.exclusive
        def write(path,body):
            if str(path).endswith('.cleanup-failed.json'):raise OSError('marker persistence failed')
            return original(path,body)
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg'),patch.object(m,'exclusive',side_effect=write),self.assertRaisesRegex(TimeoutError,'original deadline') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertTrue(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage']);self.assertIn('Unknown usage persistence',str(caught.exception.__notes__))
    def test_failure_before_launch_does_not_invent_unknown_usage(self):
        with patch.object(m.subprocess,'Popen',side_effect=OSError('launch failed')),self.assertRaisesRegex(OSError,'launch failed') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertFalse(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage'])
    def test_known_reaped_nonzero_exit_does_not_invent_unknown_usage(self):
        process=self.Process(exit_code=7)
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=ProcessLookupError),self.assertRaisesRegex(ValueError,'did not exit0') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertFalse(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage'])

    def test_group_observation_error_remains_unknown_after_cleanup(self):
        process=self.Process(exit_code=0,live=True);first=True
        def kill(pid,sig):
            nonlocal first
            if sig==0 and first:first=False;raise OSError('original group observation failure')
            if not process.live:raise ProcessLookupError
            if sig:process.live=False
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(OSError,'original group observation failure') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertTrue(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage']);self.assertFalse(process.live)
    def test_cleanup_refreshes_leader_exit_after_original_guard_failure(self):
        process=self.Process(exit_code=None,live=True);actual_exit=False
        def poll():
            if actual_exit:process.returncode=0
            return process.returncode
        process.poll=poll
        def guard(**kwargs):
            nonlocal actual_exit
            actual_exit=True;raise TimeoutError('original deadline before leader reap')
        def kill(pid,sig):
            if not process.live:raise ProcessLookupError
            if sig:self.assertEqual(process.returncode,0);process.live=False
        self.budget.guard.side_effect=guard
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(TimeoutError,'original deadline before leader reap') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertTrue(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage']);self.assertFalse(process.live);self.assertGreaterEqual(process.waited,1)

    def test_leader_exit_after_cleanup_poll_does_not_clear_unknown_cost(self):
        process=self.Process(exit_code=None,live=True);actual_exit=False;cleanup_poll=False
        def poll():
            nonlocal cleanup_poll
            if cleanup_poll:return None
            cleanup_poll=True;return None
        process.poll=poll
        def guard(**kwargs):raise TimeoutError('original deadline before cleanup race')
        def kill(pid,sig):
            nonlocal actual_exit
            if not process.live:raise ProcessLookupError
            if sig==0:actual_exit=True
            else:process.live=False
        def wait(timeout=None):
            self.assertTrue(actual_exit);process.returncode=0;process.waited+=1;return 0
        process.wait=wait;self.budget.guard.side_effect=guard
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(TimeoutError,'original deadline before cleanup race') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertTrue(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage']);self.assertFalse(process.live);self.assertGreaterEqual(process.waited,1)
    def test_forced_live_group_cleanup_is_honestly_unverified(self):
        process=self.Process(exit_code=None,live=True)
        def kill(pid,sig):
            if not process.live:raise ProcessLookupError
            if sig:process.live=False;process.returncode=-15
        self.budget.guard.side_effect=TimeoutError('original deadline')
        with patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg',side_effect=kill),self.assertRaisesRegex(TimeoutError,'original deadline') as caught:
            m.supervise(['fixed'],self.log,self.budget,self.allocation)
        m.fail(self.root,caught.exception);self.assertTrue(json.loads((self.root/'report.failed.json').read_text())['unknown_owned_process_usage']);self.assertFalse(process.live)


class WorkerMechanics(unittest.TestCase):
    setUp=Owner.setUp
    usage=Owner.usage
    save_request=Owner.save_request
    consume=Owner.consume
    env=Owner.env
    # Inherits fixtures/tests but below methods add the actual adapter's pure
    # control path. Kernel/native/fence remain fake; no process is launched.
    def setup_worker(self):
        body,request,claim,directory,budget=self.consume();directory.mkdir();pins=dict(body['fingerprints']);pins.update({request['path']:request['sha256'],claim['path']:claim['sha256']})
        context=m.exclusive(directory/'worker-context.json',dict(version=1,scope='owned_typed9_source_import_worker',execution_id='tiny-1',request=request,claim=claim,directory=body['output_directory'],allocation=budget.allocation(),fingerprints=pins,owner_pid=m.os.getpid()))
        self.worker_directory=directory;self.worker_context=context
        return context
    def fake_kernel_import(self,archive,work_directory,profile,*,check):
        work_directory.mkdir();result=dict(version=1,status='import_kernel_complete_pending_external_source_acceptance',profile=profile,fit_attempt_count=0,labels_created=False)
        for name,key,raw in [('source.csv.gz','source',self.archive.read_bytes()),('source.csv','csv',b'raw fixture'),('validated.csv','validated_csv',b'"validated fixture"'),('events.duckdb','database',b'new fake DB')]:
            check();path=work_directory/name;path.write_bytes(raw);result[key]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        m.exclusive(work_directory/'import.consumed.json',dict(fake_kernel=True));m.exclusive(work_directory/'import-evidence.json',result);return result
    def execute_worker(self,kernel_call=None):
        context=self.setup_worker();budget=Mock();budget.kernel_cpu=dict(soft=41,hard=42);kernel=Mock();kernel.import_archive.side_effect=self.fake_kernel_import if kernel_call is None else kernel_call
        with patch.object(m,'ENTRY_MONOTONIC',time.monotonic()),patch.object(m.os,'getppid',return_value=m.os.getpid()),patch.object(m,'WorkerBudget',return_value=budget),patch.object(m,'environment',side_effect=self.env),patch.object(m,'load_kernel',return_value=kernel):
            m.worker(context['path'],context['sha256'])
        return budget,kernel
    def test_worker_adapter_retains_canonical_spool_and_original_context(self):
        budget,kernel=self.execute_worker();receipt=json.loads((self.worker_directory/'worker-receipt.json').read_text())
        self.assertEqual(len(receipt['outputs']),6);self.assertIn(self.request['output_directory']+'/kernel/validated.csv',receipt['outputs']);self.assertEqual(receipt['context'],self.worker_context)
        kernel.import_archive.assert_called_once();budget.start.assert_called_once();budget.stop.assert_called_once();self.assertFalse(receipt['labels_created'])
    def test_worker_canonical_mutation_rejects_before_own_receipt(self):
        def kernel(*args,**kwargs):
            result=self.fake_kernel_import(*args,**kwargs);(args[1]/'validated.csv').write_bytes(b'changed canonical');return result
        with self.assertRaisesRegex(ValueError,'physical identity'):self.execute_worker(kernel)
        self.assertTrue((self.worker_directory/'report.failed.json').exists());self.assertFalse((self.worker_directory/'worker-receipt.json').exists())
    def test_worker_receipt_late_mutation_rejects_terminal_repins(self):
        original=m.exclusive
        def write(path,body):
            ref=original(path,body)
            if path.name=='worker-receipt.json':path.write_bytes(b'{"late":true}')
            return ref
        with patch.object(m,'exclusive',side_effect=write),self.assertRaisesRegex(ValueError,'Original file changed'):self.execute_worker()
        self.assertTrue((self.worker_directory/'report.failed.json').exists())

    def test_preexisting_owner_failure_refuses_before_worker_consumption(self):
        context=self.setup_worker();(self.worker_directory/'report.failed.json').write_text('{}')
        kernel=Mock()
        with patch.object(m,'ENTRY_MONOTONIC',time.monotonic()),patch.object(m.os,'getppid',return_value=m.os.getpid()),patch.object(m,'load_kernel',return_value=kernel),self.assertRaisesRegex(ValueError,'Known failed original'):
            m.worker(context['path'],context['sha256'])
        kernel.import_archive.assert_not_called();self.assertFalse((self.worker_directory/'worker.consumed.json').exists());self.assertFalse((self.worker_directory/'worker-receipt.json').exists())
    def test_worker_persistent_guard_refuses_late_cleanup_marker(self):
        directory=self.root/self.request['output_directory'];directory.mkdir(parents=True);budget=m.WorkerBudget(dict(cpu_seconds=20,deadline_monotonic=time.monotonic()+5,rss_bytes=7*2**30),directory=directory)
        (directory/'worker.log.cleanup-failed.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Known failed original'):budget.guard()

    def test_duplicate_worker_consumption_does_not_poison_original_owner(self):
        context=self.setup_worker();original=b'{"existing":"original consumed worker"}';(self.worker_directory/'worker.consumed.json').write_bytes(original)
        with patch.object(m,'ENTRY_MONOTONIC',time.monotonic()),patch.object(m.os,'getppid',return_value=m.os.getpid()),self.assertRaises(FileExistsError):
            m.worker(context['path'],context['sha256'])
        self.assertFalse((self.worker_directory/'report.failed.json').exists());self.assertEqual((self.worker_directory/'worker.consumed.json').read_bytes(),original)
    def test_unauthenticated_worker_context_cannot_write_owner_failure(self):
        context=self.setup_worker()
        with patch.object(m,'ENTRY_MONOTONIC',time.monotonic()),patch.object(m.os,'getppid',return_value=999999),self.assertRaisesRegex(ValueError,'actual original owner parent'):
            m.worker(context['path'],context['sha256'])
        self.assertFalse((self.worker_directory/'report.failed.json').exists());self.assertFalse((self.worker_directory/'worker.consumed.json').exists())


if __name__=='__main__':unittest.main()
