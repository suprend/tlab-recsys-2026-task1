"""Standalone pure/mock verification; no native imports, subprocesses or real IO."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

resource.setrlimit(resource.RLIMIT_CPU, (30,30))
signal.alarm(60)
START = time.monotonic()
CPU_START = time.process_time()
SOURCE = Path('/tmp/tlab-development-whole018-driver-v2.py').read_bytes()
M = types.ModuleType('driver_under_pure_test')
M.__file__ = '/private/tmp/tlab-development-whole018-driver-v2.py'
exec(compile(SOURCE,M.__file__,'exec'),M.__dict__)
SHA = 'a'*64
DRIVER_SHA = 'b'*64


def telemetry(cpu=10.0, wall=20.0, child_cpu=0.0, child_rss=0, rss=1024):
    return dict(self_cpu_seconds=cpu, waited_cpu_seconds=child_cpu,
                waited_peak_rss_bytes=child_rss, process_peak_rss_bytes=rss)


def owner_report():
    return dict(original_request_sha256=SHA,execution_id=M.EXECUTION_ID,
        status='pending_independent_all_keyed_parity_and_full_exit_acceptance',
        fit_attempt_count=0,metric_looks=0,query_targets_opened=False,
        progress=dict(source_connection_closed=True))


def parity_report():
    return dict(scope='independent_Oct22_all_keyed_mechanical_parity',
        status='parity_checks_passed_pending_Root_and_full_exit',original_request_sha256=SHA,
        execution_id=M.EXECUTION_ID,same_original_stage_budget_required=True,
        query_count=2000,all_query_count=4000,all_pair_count=817149,candidate_count=12,
        model_columns=dict(B=41,W=44),sampling='none_all_rows_and_full_ranks',
        score_checks={r:dict(rows=12,max_abs_error=0.0,complete_ranks_equal=True) for r in ('B','W')},
        model_representation_sha256=dict(B=SHA,W=SHA),owner_report_sha256=SHA,
        input_output_byte_bindings={str(n):{} for n in range(15)},
        target_relations_opened=0,model_files_opened=0,fit_attempts=0,metrics_computed=0,
        source_acceptance_issued=False,execution_authority_issued=False,external_exit_accepted=False)


class BudgetTests(unittest.TestCase):
    def make(self,cpu=10.0,wall=20.0):
        self.enterContext(patch.object(M,'ENTRY_MONOTONIC',101.0))
        self.enterContext(patch.object(M.time,'monotonic',return_value=100.0+wall))
        self.current=telemetry(cpu)
        self.enterContext(patch.object(M,'usage',side_effect=lambda:copy.deepcopy(self.current)))
        return M.PipelineBudget(100.0)

    def test_original_clock_not_future_reset_or_nonfinite(self):
        self.make()
        for started in (102.0,float('nan'),100):
            with self.assertRaises(ValueError):M.PipelineBudget(started)

    def test_whole_cpu_wall_and_peak_guards(self):
        b=self.make();b.check()
        for name,value in [('self_cpu_seconds',550.0),('process_peak_rss_bytes',8*2**30+1)]:
            old=self.current[name];self.current[name]=value
            with self.assertRaises(ValueError):b.check()
            self.current[name]=old
        with patch.object(M.time,'monotonic',return_value=950.0):
            with self.assertRaises(ValueError):b.check()

    def test_unexpected_reaped_child_never_disappears(self):
        b=self.make()
        for name,value in [('waited_cpu_seconds',.01),('waited_peak_rss_bytes',1)]:
            self.current[name]=value
            with self.assertRaisesRegex(ValueError,'never reap'):b.check()
            self.current[name]=0

    def test_late_owner_stops_before_parity(self):
        b=self.make(cpu=400.01)
        with self.assertRaisesRegex(ValueError,'too late'):b.admit_parity()
        self.assertIsNone(b.parity_start)
        self.current['self_cpu_seconds']=399
        with patch.object(M.time,'monotonic',return_value=750.01):
            with self.assertRaisesRegex(ValueError,'too late'):b.admit_parity()

    def test_parity_delta_retains_original_whole_baseline(self):
        b=self.make(cpu=300,wall=600);b.admit_parity()
        self.current['self_cpu_seconds']=449.9;b.check()
        self.current['self_cpu_seconds']=450
        with self.assertRaisesRegex(ValueError,'phase cap'):b.check()
        self.current['self_cpu_seconds']=350
        with patch.object(M.time,'monotonic',return_value=900.0):
            with self.assertRaisesRegex(ValueError,'phase cap'):b.check()
        self.assertEqual(b.started,100.0)


class InterfaceTests(unittest.TestCase):
    def test_external_request_sha_cannot_select_other_request(self):
        with patch.object(M,'snapshot',side_effect=AssertionError('Must reject before IO')):
            with self.assertRaisesRegex(ValueError,'candidate SHA'):M.fixed_request(SHA)

    def test_preserved_V1_duplicate_parity_key_red_V2_green(self):
        old=types.ModuleType('preserved_failed_v1')
        old.__file__='/private/tmp/tlab-development-whole018-driver-v1.py'
        raw=Path(old.__file__).read_bytes()
        exec(compile(raw,old.__file__,'exec'),old.__dict__)
        with self.assertRaisesRegex(TypeError,'parity'):
            dict(**old.identity(SHA,DRIVER_SHA,100.0),parity=parity_report())
        result=dict(**M.identity(SHA,DRIVER_SHA,100.0),parity=parity_report())
        self.assertEqual(result['parity_checker']['sha256'],M.PARITY_SHA)
        self.assertEqual(result['parity']['query_count'],2000)

    def test_closed_command_preserves_original_clock_and_relative_request(self):
        argv=M.fixed_command(SHA,DRIVER_SHA,123.25)
        self.assertEqual(argv[:3],[str(M.PROJECT/'.venv/bin/python'),'-I','-B'])
        self.assertEqual(argv[-2:],['--original-started-monotonic','123.25'])
        self.assertNotIn('--request',argv)
        self.assertFalse(M.REQUEST.startswith('/'))

    def test_one_supervise_no_process_or_dynamic_callback_framework(self):
        tree=ast.parse(SOURCE)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertEqual(sum(n.func.attr=='supervise' for n in calls),1)
        self.assertFalse(any(n.func.attr in {'Popen','poll','wait','wait4','supervise_direct_child'} for n in calls))
        self.assertNotIn('subprocess',[n.names[0].name for n in ast.walk(tree) if isinstance(n,ast.Import)])

    def test_parity_evidence_complete_and_no_grants(self):
        M.check_returned_parity(parity_report(),SHA)
        for key,value in [('query_count',1999),('all_query_count',2000),('all_pair_count',12),
                          ('sampling','sample'),('external_exit_accepted',True),('fit_attempts',1)]:
            result=parity_report();result[key]=value
            with self.assertRaises(ValueError):M.check_returned_parity(result,SHA)
        for key,value in [('max_abs_error',1.1e-12),('complete_ranks_equal',False),('rows',11)]:
            result=parity_report();result['score_checks']['W'][key]=value
            with self.assertRaises(ValueError):M.check_returned_parity(result,SHA)

    def test_json_duplicates_overflow_and_nonfinite_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'):
            with self.assertRaises(ValueError):M.unique_json(raw)

    def test_metadata_snapshot_cap_stability_and_exact_sha(self):
        with tempfile.TemporaryDirectory(prefix='tlab-pure-driver-') as name:
            p=Path(name).resolve()/'small.json';p.write_bytes(b'{}')
            self.assertEqual(M.snapshot(p,hashlib.sha256(b'{}').hexdigest()),b'{}')
            with self.assertRaises(ValueError):M.snapshot(p,SHA)
            p.write_bytes(b'x'*(M.CAP+1))
            with self.assertRaisesRegex(ValueError,'Bounded regular'):M.snapshot(p,SHA)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory(prefix='tlab-pure-pipeline-'))
        self.root=Path(self.tmp).resolve()
        self.enterContext(patch.object(M,'PROJECT',self.root))
        for attr in ('CONSUMED','PIPELINE','PIPELINE_FAILURE'):
            self.enterContext(patch.object(M,attr,self.root/(attr+'.json')))
        self.enterContext(patch.object(M,'ENTRY_MONOTONIC',101.0))
        self.enterContext(patch.object(M.time,'monotonic',return_value=120.0))
        self.cpu=10.0
        self.enterContext(patch.object(M,'usage',side_effect=lambda:telemetry(self.cpu)))
        self.events=[]
        self.owner_error=None;self.checker_error=None
        def owner(request,expected,*,started_monotonic):
            self.events.append(('owner',request,expected,started_monotonic))
            if self.owner_error:raise self.owner_error
            return owner_report()
        def verify(request,expected,*,check):
            self.events.append(('parity',request,expected,check.__self__.started));check()
            if self.checker_error:raise self.checker_error
            return parity_report()
        self.owner=types.SimpleNamespace(run_slice=owner)
        self.checker=types.SimpleNamespace(verify_request=verify)
        def loader(path,digest,name):
            if path==self.root/M.OWNER:return self.owner
            if path==self.root/M.PARITY:return self.checker
            raise AssertionError('Unexpected module')
        self.enterContext(patch.object(M,'load_exact',side_effect=loader))
        self.enterContext(patch.object(M,'fixed_request',return_value={}))
        self.enterContext(patch.object(M,'snapshot',side_effect=lambda path,digest:
            M.encode(M.identity(SHA,DRIVER_SHA,100.0)) if path==M.CONSUMED else b'{}'))

    def test_owner_then_independent_checker_with_same_original_identity(self):
        self.assertEqual(M.pipeline_main(SHA,DRIVER_SHA,100.0),0)
        self.assertEqual([x[0] for x in self.events],['owner','parity'])
        for row in self.events:self.assertEqual(row[1:],(M.REQUEST,SHA,100.0))
        body=json.loads(M.PIPELINE.read_bytes())
        self.assertEqual(body['original_entry_monotonic'],100.0)
        self.assertFalse(body['source_acceptance_issued']);self.assertFalse(body['full_exit_acceptance_issued'])

    def test_owner_failure_never_calls_checker(self):
        self.owner_error=RuntimeError('native mocked failure')
        self.assertEqual(M.pipeline_main(SHA,DRIVER_SHA,100.0),1)
        self.assertEqual([x[0] for x in self.events],['owner'])
        self.assertFalse(M.PIPELINE.exists());self.assertTrue(M.PIPELINE_FAILURE.exists())

    def test_late_owner_never_calls_checker(self):
        original=self.owner.run_slice
        def late(*args,**kwargs):
            result=original(*args,**kwargs);self.cpu=400.01;return result
        self.owner.run_slice=late
        self.assertEqual(M.pipeline_main(SHA,DRIVER_SHA,100.0),1)
        self.assertEqual([x[0] for x in self.events],['owner'])

    def test_checker_failure_preserved_and_no_success(self):
        self.checker_error=ValueError('key mismatch')
        self.assertEqual(M.pipeline_main(SHA,DRIVER_SHA,100.0),1)
        body=json.loads(M.PIPELINE_FAILURE.read_bytes())
        self.assertTrue(body['owner_returned']);self.assertFalse(body['parity_returned'])
        self.assertFalse(M.PIPELINE.exists())

    def test_existing_owner_namespace_not_reused(self):
        (self.root/M.OUT).mkdir(parents=True)
        self.assertEqual(M.pipeline_main(SHA,DRIVER_SHA,100.0),1)
        self.assertEqual(self.events,[])


class OuterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory(prefix='tlab-pure-outer-'))
        self.root=Path(self.tmp).resolve()
        self.enterContext(patch.object(M,'PROJECT',self.root))
        paths=[]
        for attr in ('CONSUMED','LOG','PROCESS','PIPELINE','PIPELINE_FAILURE','DRIVER','ERROR'):
            p=self.root/(attr+'.json');paths.append(p);self.enterContext(patch.object(M,attr,p))
        self.enterContext(patch.object(M,'NAMESPACE',tuple(paths)))
        self.enterContext(patch.object(M,'runtime',return_value=None))
        self.enterContext(patch.object(M,'snapshot',return_value=b'{}'))
        self.enterContext(patch.object(M,'fixed_request',return_value={'reference_handoff':{'path':'metadata/handoff.json'}}))
        self.enterContext(patch.object(M,'usage',return_value=telemetry()))
        self.report=dict(status='verified_normal_exit',reaped=True,exit_code=0,unknown_active_work=False,
            scope='synthetic_harness_process_supervision',worker_ledger_verified=False,supervisor_exit_tail_measured=False)
        self.calls=[];self.make_evidence=True;self.raise_cleanup=None
        def supervise(argv,log,**kwargs):
            self.calls.append((argv,log,kwargs))
            if self.raise_cleanup:
                error=RuntimeError('owned unknown');error.supervisor_cleanup_evidence=self.raise_cleanup;raise error
            if self.make_evidence:
                M.exclusive(M.PIPELINE,dict(**M.identity(SHA,DRIVER_SHA,M.ENTRY_MONOTONIC),
                    status='owner_and_independent_parity_returned_pending_root_full_exit_acceptance',
                    owner_returned=True,parity=parity_report()))
            return copy.deepcopy(self.report)
        self.enterContext(patch.object(M,'load_exact',return_value=types.SimpleNamespace(supervise=supervise)))

    def test_one_supervision_global_limits_raw_flags_preserved(self):
        self.assertEqual(M.outer_main(SHA,DRIVER_SHA),0);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][2],dict(started=M.ENTRY_MONOTONIC,cwd=self.root,**M.LIMITS))
        receipt=json.loads(M.PROCESS.read_bytes())
        self.assertEqual(receipt['supervisor_report'],self.report)
        self.assertFalse(receipt['supervisor_flags_reinterpreted'])
        self.assertFalse(json.loads(M.DRIVER.read_bytes())['full_exit_acceptance_issued'])

    def test_normal_reap_without_mandatory_parity_stops(self):
        self.make_evidence=False
        self.assertEqual(M.outer_main(SHA,DRIVER_SHA),1)
        self.assertFalse(M.DRIVER.exists());self.assertTrue(M.ERROR.exists())

    def test_failed_or_unknown_boundary_stops(self):
        for key,value in [('status','failed_unknown_cleanup'),('reaped',False),('exit_code',1),('unknown_active_work',True)]:
            candidate=copy.deepcopy(self.report);candidate[key]=value
            with self.assertRaises(ValueError):M.require_normal_boundary(candidate)

    def test_exception_cleanup_unknown_preserved_not_success(self):
        self.raise_cleanup=dict(reaped=False,status='failed_unknown_launch',cleanup_nested_unknown=True)
        self.assertEqual(M.outer_main(SHA,DRIVER_SHA),1)
        receipt=json.loads(M.PROCESS.read_bytes())
        self.assertEqual(receipt['supervisor_exception_cleanup_evidence'],self.raise_cleanup)
        self.assertFalse(M.DRIVER.exists())

    def test_existing_namespace_no_launch_or_overwrite(self):
        M.CONSUMED.write_bytes(b'old failure')
        self.assertEqual(M.outer_main(SHA,DRIVER_SHA),1)
        self.assertEqual(self.calls,[]);self.assertEqual(M.CONSUMED.read_bytes(),b'old failure')
        self.assertFalse(M.ERROR.exists())


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    value=dict(version=1,scope='pure_mock_whole018_driver_only',tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),success=result.wasSuccessful(),
        body_cpu_seconds=time.process_time()-CPU_START,body_wall_seconds=time.monotonic()-START,
        full_process_self=M.usage(),
        native_calls=0,children_started=0,actual_data_or_models_opened=False,project_writes=False)
    path=Path('/tmp/tlab-development-whole018-driver-v2-author-pure-final-receipt.json')
    with path.open('xb') as handle:handle.write(M.encode(value))
    raise SystemExit(0 if result.wasSuccessful() else 1)
