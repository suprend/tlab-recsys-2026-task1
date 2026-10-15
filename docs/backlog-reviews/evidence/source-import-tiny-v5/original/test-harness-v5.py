"""Pure harness wiring/fixtures; no child, native supervisor or SQL runs."""
from pathlib import Path
from types import ModuleType,SimpleNamespace
import dis,hashlib,json,sys,tempfile,unittest
from unittest.mock import Mock,patch
p=Path('/tmp/tlab-source-import-integration-harness-v5.py');m=ModuleType('harness_v2');m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec',dont_inherit=True),m.__dict__)

class Harness(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()/'new tiny root';self.sha=hashlib.sha256(p.read_bytes()).hexdigest();self.reaped=False;m._HANDLES.clear();m._ACTIVE_SOURCE_OWNER=None
  self.patches=[patch.object(m,'FIXTURE_ROOT',self.root),patch.object(m,'guarded'),patch.object(m,'usage',side_effect=self.usage)]
  for obj in self.patches:obj.start();self.addCleanup(obj.stop)
 def usage(self,kind=m.resource.RUSAGE_SELF):return (.2,2000) if kind==m.resource.RUSAGE_CHILDREN and self.reaped else (0,0) if kind==m.resource.RUSAGE_CHILDREN else (.1,1000)
 def setup_fixture(self):m.consume_root();return m.prepare(self.sha)
 def context(self):
  refs=self.setup_fixture();return m.exclusive(self.root/'.review/driver-context.json',dict(version=1,scope='reviewed_eight_row_source_import_driver',owner_pid=m.os.getpid(),entry=dict(path=str(self.root/'.review/source-harness.py'),sha256=self.sha),requests=refs,limits=m.LIMITS,original_started_monotonic=m.time.monotonic()))
 def test_exact_four_public_sourcecopies_plus_sharedhelper_and_driver(self):
  refs=self.setup_fixture();self.assertEqual(set(refs),{'tiny-positive','tiny-wrong-sha'});self.assertEqual((self.root/'.review/supervisor.py').read_bytes(),m.SHARED_SUPERVISOR[0].read_bytes());self.assertEqual(hashlib.sha256((self.root/'.review/source-harness.py').read_bytes()).hexdigest(),self.sha)
  request=json.loads(Path(refs['tiny-positive']['path']).read_text());self.assertEqual(set(request['fingerprints']),set(m.SOURCES));self.assertEqual(request['profile']['expected_rows'],4);self.assertEqual(request['resources']['cpu_seconds'],60);self.assertEqual(request['resources']['wall_seconds'],60)
 def test_fixed_root_consumed_no_refill(self):
  self.setup_fixture()
  with self.assertRaisesRegex(ValueError,'already consumed'):m.consume_root()
 def test_original_copies_repin_detects_mutation(self):
  self.setup_fixture();(self.root/'scripts/source_import.py').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'Copied harness dependency'):m.copies(lambda:None)
 def test_fixture_profiles_preserve_production_identity(self):
  refs=self.setup_fixture();a=m.read(refs['tiny-positive']['path']);b=m.read(refs['tiny-wrong-sha']['path']);self.assertEqual(a['profile']['scope'],'synthetic_typed9_import_fixture');self.assertNotEqual(a['profile']['compressed_sha256'],'0'*64);self.assertEqual(b['profile']['compressed_sha256'],'0'*64)
  kernel=m.compiled(self.root/'scripts/source_import.py',m.SOURCES['scripts/source_import.py'][1]);self.assertEqual(kernel.PRODUCTION_PROFILE['compressed_sha256'],'8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147')
 def test_compiled_verified_snapshot_ignores_timestamp_cache(self):
  import importlib.util,importlib._bootstrap_external as be
  source=Path(self.tmp.name)/'kernel.py';pinned=b"marker='PINNED'\n";other=b"marker='OTHER!'\n";source.write_bytes(pinned);cache=Path(importlib.util.cache_from_source(str(source)));cache.parent.mkdir();cache.write_bytes(be._code_to_timestamp_pyc(compile(other,str(source),'exec'),int(source.stat().st_mtime),len(pinned)))
  self.assertEqual(m.compiled(source,hashlib.sha256(pinned).hexdigest()).marker,'PINNED')
 def test_driver_authentication_error_is_readonly(self):
  context=self.context()
  with patch.object(m,'__file__',str(self.root/'.review/source-harness.py')),patch.object(m.os,'getppid',return_value=999999),self.assertRaisesRegex(ValueError,'actual original supervisor parent'):m.driver(context['path'],context['sha256'])
  self.assertFalse((self.root/'driver.consumed.json').exists());self.assertFalse((self.root/'driver.failed.json').exists())
 def test_driver_context_original_hash_is_required_before_consumption(self):
  context=self.context()
  with self.assertRaisesRegex(ValueError,'context differs'):m.driver(context['path'],'0'*64)
  self.assertFalse((self.root/'driver.consumed.json').exists())
 def test_owner_case_direct_argv_pins_isolated_script_and_original_sha(self):
  refs=self.setup_fixture();argv=m.owner_argv(refs['tiny-positive']);self.assertEqual(argv[1:3],['-I','-B']);self.assertEqual(argv[3],str(self.root/'scripts/run_source_import.py'));self.assertEqual(argv[-1],refs['tiny-positive']['sha256'])
 def test_wrongsha_native_admission_negative_proof(self):
  directory=self.root/'artifacts/source-import-runs/tiny-wrong-sha';kernel=directory/'kernel';kernel.mkdir(parents=True);(directory/'report.failed.json').write_text(json.dumps(dict(status='failed_original_source_import',source_acceptance_issued=False,unknown_owned_process_usage=False)))
  (kernel/'import.consumed.json').write_text('{}');(kernel/'report.failed.json').write_text(json.dumps(dict(status='failed_import_kernel',error_type='ValueError')));(kernel/'source.csv.gz').write_bytes(b'tiny');(directory/'worker.log').write_text('ValueError: Original compressed SHA/size differs\n');(self.root/'tiny-wrong-sha-request.json').write_text(json.dumps(dict(archive='data/raw/tiny.csv.gz',profile=dict(scope='synthetic_typed9_import_fixture',compressed_sha256='0'*64))));archive=self.root/'data/raw/tiny.csv.gz';archive.parent.mkdir(parents=True);archive.write_bytes(b'tiny');positive=m.exclusive(self.root/'tiny-positive-request.json',dict(archive='data/raw/tiny.csv.gz',profile=dict(scope='synthetic_typed9_import_fixture',compressed_sha256=hashlib.sha256(b'tiny').hexdigest(),compressed_bytes=4,expected_rows=4)))
  self.assertTrue(m.wrong_proof(positive_reference=positive)['failed_before_native_DB']);(kernel/'events.duckdb').write_bytes(b'forbidden')
  with self.assertRaisesRegex(ValueError,'native/decompression'):m.wrong_proof(positive_reference=positive)
 def test_shared_supervisor_source_is_pinned_not_selfapproved(self):
  source=Path(self.tmp.name)/'changed-supervisor.py';source.write_bytes(b'changed')
  with patch.object(m,'SHARED_SUPERVISOR',(source,'0'*64)):
   m.consume_root()
   with self.assertRaisesRegex(ValueError,'driver/supervisor bytes differ'):m.prepare(self.sha)
  self.assertTrue((self.root/'harness.consumed.json').exists());self.assertFalse((self.root/'.review/driver-context.json').exists())
 def test_external_harness_sha_checked_before_real_limits_and_launch(self):
  with patch.object(m.resource,'setrlimit') as fence,patch.object(m.subprocess,'Popen') as launch,self.assertRaisesRegex(ValueError,'harness SHA'):m.run('0'*64)
  fence.assert_not_called();launch.assert_not_called()

class Cases(unittest.TestCase):
 setUp=Harness.setUp;usage=Harness.usage;setup_fixture=Harness.setup_fixture
 class Process:
  pid=123
  def __init__(self,case,code=0):self.case=case;self.code=code;self.returncode=None;self.waits=0
  def wait(self,timeout=None):self.waits+=1;self.returncode=self.code;self.case.reaped=True;return self.code
  def send_signal(self,sig):self.code=-int(sig)
 def test_known_positive_and_expected_negative_exits_are_recorded_once(self):
  refs=self.setup_fixture();process=self.Process(self,code=1)
  with patch.object(m.subprocess,'Popen',return_value=process):record=m.run_owner_case(refs['tiny-positive'],ordinal=2)
  self.assertEqual(record['exit_code'],1);self.assertEqual(record['actual_full_owner_inclusive_cpu_seconds'],.2);self.assertFalse(record['unknown_owned_process_usage']);self.assertEqual(m._HANDLES,[]);self.assertEqual(process.waits,1)
 def test_launch_failure_has_no_invented_old_handle(self):
  refs=self.setup_fixture()
  with patch.object(m.subprocess,'Popen',side_effect=OSError('launch failure')),self.assertRaisesRegex(OSError,'launch failure'):m.run_owner_case(refs['tiny-positive'],ordinal=1)
  self.assertEqual(m._HANDLES,[])
 def test_only_predeclared_three_case_ordinals(self):
  with patch.object(m.subprocess,'Popen') as launch,self.assertRaisesRegex(ValueError,'three-case'):m.run_owner_case({},ordinal=4)
  launch.assert_not_called()
 def test_wait_timeout_remains_failed_unknown_even_after_reap(self):
  refs=self.setup_fixture();process=self.Process(self);original=process.wait
  def wait(timeout=None):
   if process.waits==0:process.waits+=1;raise m.subprocess.TimeoutExpired('fake',timeout)
   return original(timeout)
  process.wait=wait
  with patch.object(m.subprocess,'Popen',return_value=process),self.assertRaises(m.subprocess.TimeoutExpired) as caught:m.run_owner_case(refs['tiny-positive'],ordinal=1)
  self.assertTrue(caught.exception.unknown_owned_process_usage);self.assertEqual(m._HANDLES,[])

class Outer(unittest.TestCase):
 setUp=Harness.setUp;usage=Harness.usage
 def helper(self,result):
  helper=Mock()
  def supervise(*args,**kwargs):
   receipt=dict(status='tiny_driver_complete_pending_outer_full_exit',scope='exact_three_source_owner_cases',synthetic_input_rows=8,actual_real_source_rows=0,workers=2,owners=[dict(exit_code=code,reaped=True,unknown_owned_process_usage=False) for code in [0,1,1]],source_acceptance_issued=False,fit_attempt_count=0,labels_created=False,positive=dict(exact_typed9=True),duplicate_outputs_unchanged=True,duplicate_claim_rejected=True,wrong_sha=dict(failed_before_native_DB=True,wrong_compressed_sha_rejected=True))
   m.exclusive(self.root/'driver-report.json',receipt);return result
  helper.supervise.side_effect=supervise;return helper
 def execute(self,result):
  helper=self.helper(result);original=m.compiled
  def compile_file(path,expected):return helper if str(path).endswith('/supervisor.py') else original(path,expected)
  with patch.object(m.resource,'setrlimit'),patch.object(m.resource,'getrlimit',return_value=(199,200)),patch.object(m,'compiled',side_effect=compile_file),patch.object(m,'copies'):
   report=m.run(self.sha)
  return report,helper
 def test_one_fresh_shared_supervisor_invocation_wraps_driver(self):
  report,helper=self.execute(dict(status='verified_normal_exit',exit_code=0,reaped=True,unknown_active_work=False));self.assertTrue(report['driver_ledger_verified']);self.assertFalse(report['source_acceptance_issued']);helper.supervise.assert_called_once();argv=helper.supervise.call_args.args[0];self.assertIn('--driver-context',argv);self.assertEqual(helper.supervise.call_args.kwargs['cpu_seconds'],200);self.assertEqual(helper.supervise.call_args.kwargs['wall_seconds'],240)
 def test_unknown_shared_supervision_cannot_be_promoted(self):
  with self.assertRaisesRegex(ValueError,'known normal driver exit'):self.execute(dict(status='failed_unknown_cleanup',exit_code=0,reaped=True,unknown_active_work=True))
  self.assertTrue((self.root/'harness.failed.json').exists());self.assertFalse((self.root/'harness-report.json').exists())
 def test_driver_direct_negative_exit_cannot_be_accepted_by_outer(self):
  with self.assertRaisesRegex(ValueError,'known normal driver exit'):self.execute(dict(status='verified_normal_exit',exit_code=1,reaped=True,unknown_active_work=False))
  self.assertFalse((self.root/'harness-report.json').exists())

class Driver(unittest.TestCase):
 setUp=Harness.setUp;usage=Harness.usage;setup_fixture=Harness.setup_fixture;context=Harness.context
 def execute_driver(self,codes=None,mutation=None):
  context=self.context();calls=[]
  def owner(reference,*,ordinal):
   calls.append(ordinal);eid='tiny-wrong-sha' if ordinal==3 else 'tiny-positive';directory=self.root/'artifacts/source-import-runs'/eid;directory.mkdir(parents=True,exist_ok=True)
   if ordinal in (1,3):
    (directory/'worker.consumed.json').write_text('{}');claim=self.root/'artifacts/source-import-owner/claims'/('tiny-positive.json');claim.parent.mkdir(parents=True,exist_ok=True);claim.write_text('{}')
   if ordinal==1:(directory/'report.json').write_text(json.dumps(dict(observed_owner_and_reaped_children_cpu_seconds=.1)))
   if ordinal==2:(self.root/'duplicate.log').write_text('ValueError: Existing import output cannot be reused\n')
   if mutation:mutation(ordinal)
   code=[0,1,1][ordinal-1] if codes is None else codes[ordinal-1]
   return dict(ordinal=ordinal,exit_code=code,reaped=True,unknown_owned_process_usage=False,actual_full_owner_inclusive_cpu_seconds=.2)
  with patch.object(m,'__file__',str(self.root/'.review/source-harness.py')),patch.object(m.os,'getppid',return_value=m.os.getpid()),patch.object(m,'run_owner_case',side_effect=owner),patch.object(m,'positive_proof',return_value=dict(exact_typed9=True)),patch.object(m,'wrong_proof',return_value=dict(failed_before_native_DB=True,wrong_compressed_sha_rejected=True)),patch.object(m,'snapshot',return_value={'stable':'original'}):
   result=m.driver(context['path'],context['sha256'])
  return result,calls
 def test_driver_exact_three_cases_accepts_known_negative_exits(self):
  report,calls=self.execute_driver();self.assertEqual(calls,[1,2,3]);self.assertEqual(report['synthetic_input_rows'],8);self.assertEqual(report['workers'],2);self.assertFalse(report['source_acceptance_issued']);self.assertFalse((self.root/'driver.failed.json').exists())
 def test_driver_positive_failure_stops_before_later_cases(self):
  with self.assertRaisesRegex(ValueError,'Positive owner'):self.execute_driver(codes=[1,1,1])
  self.assertTrue((self.root/'driver.failed.json').exists());self.assertFalse((self.root/'driver-report.json').exists());self.assertFalse((self.root/'artifacts/source-import-runs/tiny-wrong-sha').exists())
 def test_unknown_case_failure_never_becomes_completed_driver(self):
  def fail(ordinal):
   if ordinal==3:
    error=RuntimeError('unknown original case');error.unknown_owned_process_usage=True;raise error
  with self.assertRaisesRegex(RuntimeError,'unknown original case'):self.execute_driver(mutation=fail)
  self.assertTrue(m.read(self.root/'driver.failed.json')['unknown_owned_process_usage']);self.assertFalse((self.root/'driver-report.json').exists())
 def test_late_driver_receipt_mutation_is_rejected(self):
  original=m.exclusive
  def write(path,body):
   reference=original(path,body)
   if path.name=='driver-report.json':path.write_bytes(b'{"changed":true}')
   return reference
  with patch.object(m,'exclusive',side_effect=write),self.assertRaisesRegex(ValueError,'Original driver report changed'):self.execute_driver()
  self.assertTrue((self.root/'driver.failed.json').exists())

class RepairRegressions(unittest.TestCase):
 setUp=Harness.setUp;usage=Harness.usage;setup_fixture=Harness.setup_fixture;context=Harness.context
 def test_timeout_partials_do_not_prove_wrong_compressed_sha(self):
  directory=self.root/'artifacts/source-import-runs/tiny-wrong-sha';kernel=directory/'kernel';kernel.mkdir(parents=True);(directory/'report.failed.json').write_text(json.dumps(dict(status='failed_original_source_import',source_acceptance_issued=False,unknown_owned_process_usage=False)))
  (kernel/'report.failed.json').write_text(json.dumps(dict(status='failed_import_kernel',error_type='TimeoutError')))
  with self.assertRaisesRegex(ValueError,'specific compressed-hash rejection'):m.wrong_proof()
 def test_signaled_duplicate_does_not_prove_expected_refusal(self):
  with self.assertRaisesRegex(ValueError,'expected normal Python failure exit'):m.duplicate_proof(-9)
 def test_per_owner_wait_and_cleanup_share_one_original70second_envelope(self):
  refs=self.setup_fixture();clock={'now':0.};calls=[]
  class Process:
   pid=12345;returncode=None
   def wait(self,timeout=None):calls.append(timeout);clock['now']+=timeout;raise m.subprocess.TimeoutExpired('FAKE',timeout)
   def send_signal(self,sig):pass
  process=Process()
  with patch.object(m.time,'monotonic',side_effect=lambda:clock['now']),patch.object(m.subprocess,'Popen',return_value=process),self.assertRaises(m.subprocess.TimeoutExpired):m.run_owner_case(refs['tiny-positive'],ordinal=1)
  self.assertEqual(calls,[60.,5,5]);self.assertLessEqual(clock['now'],70.);self.assertEqual(m.active_handle_ids(),[12345])
 def test_handle_survives_both_append_and_recovery_allocation_failures(self):
  refs=self.setup_fixture()
  class Broken(list):
   def append(self,process):raise MemoryError('original append failure')
   def insert(self,index,process):raise MemoryError('recovery also failed')
  class Process:
   pid=12345;returncode=None
   def wait(self,timeout=None):raise m.subprocess.TimeoutExpired('FAKE',timeout)
   def send_signal(self,sig):pass
  process=Process()
  with patch.object(m,'_HANDLES',Broken()),patch.object(m.subprocess,'Popen',return_value=process),self.assertRaisesRegex(MemoryError,'original append failure') as caught:m.run_owner_case(refs['tiny-positive'],ordinal=1)
  self.assertIs(m._ACTIVE_SOURCE_OWNER,process);self.assertEqual(m.active_handle_ids(),[12345]);self.assertTrue(caught.exception.unknown_owned_process_usage)
 def test_interrupt_after_popen_local_assignment_recovers_original_handle(self):
  refs=self.setup_fixture();instructions={i.offset:i for i in dis.get_instructions(m.run_owner_case)}
  class Process:
   pid=12345;returncode=None
   def wait(self,timeout=None):raise m.subprocess.TimeoutExpired('FAKE_ONLY',timeout)
   def send_signal(self,sig):pass
  process=Process();state={'triggered':False}
  def trace(frame,event,arg):
   if frame.f_code is m.run_owner_case.__code__:
    if event=='call':frame.f_trace_opcodes=True
    elif event=='opcode' and not state['triggered']:
     instruction=instructions.get(frame.f_lasti)
     if instruction and instruction.opname=='STORE_GLOBAL' and instruction.argval=='_ACTIVE_SOURCE_OWNER':
      self.assertIs(frame.f_locals['process'],process);state['triggered']=True;raise KeyboardInterrupt('actual post-Popen/pre-scalar interruption')
    return trace
   return None
  with patch.object(m.subprocess,'Popen',return_value=process):
   previous=sys.gettrace();calling_frame=sys._getframe();old_opcode=calling_frame.f_trace_opcodes;calling_frame.f_trace_opcodes=True
   try:
    sys.settrace(trace)
    with self.assertRaisesRegex(KeyboardInterrupt,'post-Popen/pre-scalar') as caught:m.run_owner_case(refs['tiny-positive'],ordinal=1)
   finally:sys.settrace(previous);calling_frame.f_trace_opcodes=old_opcode
  self.assertTrue(state['triggered']);self.assertTrue(caught.exception.unknown_owned_process_usage);self.assertIs(m._ACTIVE_SOURCE_OWNER,process);self.assertEqual(m.active_handle_ids(),[12345])
 def test_exact_raw_validated_receipt_snapshot_is_retained(self):
  self.root.mkdir();path=self.root/'driver.json';path.write_text('{"workers":2}');body,reference=m.read_snapshot(path);path.write_text('{"workers":999}')
  self.assertEqual(body['workers'],2)
  with self.assertRaisesRegex(ValueError,'validated receipt bytes changed'):m.receipt_pins([reference])

class FixtureRegressions(unittest.TestCase):
 setUp=Harness.setUp;usage=Harness.usage;setup_fixture=Harness.setup_fixture
 def test_original_positive_fixture_sha_is_required_after_same_size_replacement(self):
  refs=self.setup_fixture();archive=self.root/'data/raw/tiny.csv.gz';archive.write_bytes(b'x'*archive.stat().st_size)
  with self.assertRaisesRegex(ValueError,'physical fixture SHA changed'):m.fixture_identity(refs['tiny-positive'])
 def test_unbounded_replacement_refuses_before_reading_its_bytes(self):
  refs=self.setup_fixture();archive=self.root/'data/raw/tiny.csv.gz';archive.write_bytes(b'x'*3000)
  with patch.object(m,'hashed',side_effect=AssertionError('oversize fixture must not be streamed')),self.assertRaisesRegex(ValueError,'physical fixture byte count changed'):m.fixture_identity(refs['tiny-positive'])

if __name__=='__main__':unittest.main(verbosity=2)
