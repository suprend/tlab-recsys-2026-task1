"""Pure/mocked metadata and signature tests; no native/backend/process/owner calls."""
import ast
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch

SOURCE = Path('/tmp/tlab-full-source-import-external-driver-v1.py')
MODULE = ModuleType('full_source_driver_under_pure_test')
MODULE.__file__ = str(SOURCE)
sys.modules[MODULE.__name__] = MODULE
exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec', dont_inherit=True), MODULE.__dict__)
d = MODULE


def normal():
    return dict(status='verified_normal_exit', reaped=True, exit_code=0,
                unknown_active_work=False, worker_ledger_verified=False,
                arbitrary_descendant_containment=False,
                supervisor_exit_tail_measured=False,
                scope='synthetic_harness_process_supervision', errors=[])


class DriverPureTests(unittest.TestCase):
    def run_mock(self, report=None, error=None, preflight_error=None, existing=False):
        writes = {}
        calls = []
        sup = SimpleNamespace()
        def supervise(argv, log_path, *, started, cpu_seconds, wall_seconds, rss_bytes, cwd):
            calls.append(dict(argv=argv, log_path=log_path, started=started,
                              cpu_seconds=cpu_seconds, wall_seconds=wall_seconds,
                              rss_bytes=rss_bytes, cwd=cwd))
            if error:
                raise error
            return report
        sup.supervise = supervise
        def record(path, body):
            if path in writes:
                raise FileExistsError(str(path))
            writes[path] = json.loads(json.dumps(body, allow_nan=False))
        with patch.object(d, 'reject_existing_outputs', side_effect=FileExistsError('consumed') if existing else None), \
             patch.object(d, 'preflight', side_effect=preflight_error, return_value=d.command()), \
             patch.object(d, 'load_supervisor', return_value=sup), \
             patch.object(d, 'guard'), patch.object(d, 'exclusive_json', side_effect=record), \
             patch.object(d.sys, 'stderr', io.StringIO()):
            code = d.main()
        return code, writes, calls

    def test_exact_command_has_bound_interpreter_isolation_owner_request_and_sha(self):
        self.assertEqual(d.command(), [str(d.PROJECT/'.venv/bin/python'), '-I', '-B',
            str(d.PROJECT/'scripts/run_source_import.py'), '--request', str(d.REQUEST),
            '--expected-request-sha', d.REQUEST_SHA])

    def test_one_successful_call_with_original_global_limits_and_entry_clock(self):
        source = normal()
        before = deepcopy(source)
        code, writes, calls = self.run_mock(source)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], dict(argv=d.command(), log_path=d.PROCESS_LOG,
            started=d.ENTRY_MONOTONIC, cpu_seconds=7200, wall_seconds=10800,
            rss_bytes=8*2**30, cwd=d.PROJECT))
        self.assertEqual(writes[d.PROCESS_RECEIPT]['supervisor_report'], before)
        self.assertEqual(source, before)
        self.assertFalse(writes[d.PROCESS_RECEIPT]['source_acceptance_issued'])
        self.assertFalse(writes[d.PROCESS_RECEIPT]['external_full_exit_acceptance_issued'])
        self.assertFalse(writes[d.PROCESS_RECEIPT]['nested_owner_worker_ledger_accepted'])
        self.assertIn(d.DRIVER_STDOUT, writes)
        self.assertNotIn(d.DRIVER_ERROR, writes)

    def test_failed_or_unknown_or_unreaped_report_retained_exact_no_retry(self):
        for update in [dict(status='failed_unknown_cleanup', unknown_active_work=True),
                       dict(reaped=False), dict(exit_code=1), dict(exit_code=True),
                       dict(unknown_active_work=True)]:
            with self.subTest(update=update):
                source=normal(); source.update(update)
                code,writes,calls=self.run_mock(source)
                self.assertEqual(code,1)
                self.assertEqual(len(calls),1)
                self.assertEqual(writes[d.PROCESS_RECEIPT]['supervisor_report'],source)
                self.assertIn(d.DRIVER_ERROR,writes)
                self.assertNotIn(d.DRIVER_STDOUT,writes)

    def test_supervisor_exception_cleanup_evidence_including_reap_retained(self):
        for reaped in [True, False]:
            with self.subTest(reaped=reaped):
                exc=RuntimeError('original failed')
                exc.supervisor_cleanup_evidence=dict(reaped=reaped,exit_code=1 if reaped else None,
                    cleanup_nested_unknown=True,actual_cpu=2.5 if reaped else None,
                    errors=['original primary'],ownership_phase='reaped' if reaped else 'lost')
                code,writes,calls=self.run_mock(error=exc)
                self.assertEqual(code,1)
                self.assertEqual(len(calls),1)
                self.assertEqual(writes[d.PROCESS_RECEIPT]['supervisor_exception_cleanup_evidence'],
                                 exc.supervisor_cleanup_evidence)
                self.assertIsNone(writes[d.PROCESS_RECEIPT]['supervisor_report'])

    def test_preflight_failure_no_supervisor_call_and_failed_receipt(self):
        code,writes,calls=self.run_mock(preflight_error=ValueError('request mismatch'))
        self.assertEqual(code,1)
        self.assertEqual(calls,[])
        self.assertFalse(writes[d.PROCESS_RECEIPT]['supervision_attempted'])
        self.assertIsNone(writes[d.PROCESS_RECEIPT]['supervisor_report'])

    def test_preexisting_namespace_no_new_receipt_and_no_launch(self):
        code,writes,calls=self.run_mock(existing=True)
        self.assertEqual(code,1)
        self.assertEqual(writes,{})
        self.assertEqual(calls,[])

    def test_request_snapshot_hashes_same_bounded_raw_bytes(self):
        raw=b'{}\n'
        with patch.object(d.Path,'open',return_value=io.BytesIO(raw)):
            self.assertEqual(d.raw_snapshot(Path('/fake/source'),hashlib.sha256(raw).hexdigest()),raw)
        with patch.object(d.Path,'open',return_value=io.BytesIO(raw)):
            with self.assertRaises(ValueError): d.raw_snapshot(Path('/fake/source'),'0'*64)
        with patch.object(d.Path,'open',return_value=io.BytesIO(b'x'*(2**20+1))):
            with self.assertRaises(ValueError): d.raw_snapshot(Path('/fake/source'),'0'*64)

    def test_duplicate_and_nonfinite_request_json_rejected(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):d.unique_json(raw)

    def test_supervisor_raw_compilation_uses_snapshot_and_never_loader(self):
        raw=b'marker = "snapshot"\ndef supervise(argv, log_path, *, started, cpu_seconds, wall_seconds, rss_bytes, cwd):\n    raise AssertionError("must not call")\n'
        with patch.object(d,'raw_snapshot',return_value=raw) as read:
            value=d.load_supervisor()
        read.assert_called_once_with(d.SUPERVISOR,d.SUPERVISOR_SHA)
        self.assertEqual(value.marker,'snapshot')
        self.assertEqual(value.__file__,str(d.SUPERVISOR))

    def test_actual_v6_signature_covers_the_only_call_keywords_without_import(self):
        raw=d.SUPERVISOR.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),d.SUPERVISOR_SHA)
        tree=ast.parse(raw)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='supervise')
        self.assertEqual([a.arg for a in fn.args.args],['argv','log_path'])
        self.assertEqual([a.arg for a in fn.args.kwonlyargs],
                         ['started','cpu_seconds','wall_seconds','rss_bytes','cwd'])

    def preflight_mock(self, change=None, existing_claim=False):
        body=dict(execution_id=d.EXECUTION_ID,
                  output_directory='artifacts/source-import-runs/'+d.EXECUTION_ID,
                  fingerprints=d.OWNER_FINGERPRINTS.copy(),
                  resources=dict(cpu_seconds=7200,wall_seconds=10800,job_rss_bytes=8*2**30))
        if change:change(body)
        reads=[]
        def read(path,expected):
            reads.append((path,expected))
            return json.dumps(body).encode() if path==d.REQUEST else b'mocked_source'
        claim=d.PROJECT/'artifacts/source-import-owner/claims'/(d.EXECUTION_ID+'.json')
        with patch.object(d.sys,'argv',['driver']),patch.object(d.sys,'version_info',(3,12,14)), \
             patch.object(d.sys,'flags',SimpleNamespace(isolated=1,dont_write_bytecode=1)), \
             patch.object(d.sys,'platform','darwin'),patch.object(d.sys,'prefix',str(d.PROJECT/'.venv')), \
             patch.object(d.os,'uname',return_value=SimpleNamespace(machine='arm64')), \
             patch.object(d.Path,'resolve',lambda self:self), \
             patch.object(d.Path,'is_symlink',return_value=False), \
             patch.object(d.Path,'exists',lambda self: existing_claim and self==claim), \
             patch.object(d,'guard'),patch.object(d,'raw_snapshot',side_effect=read):
            result=d.preflight()
        return result,reads

    def test_complete_preflight_accepts_exact_closed_request_and_current_code_pins(self):
        argv,reads=self.preflight_mock()
        self.assertEqual(argv,d.command())
        self.assertEqual(reads,[(d.REQUEST,d.REQUEST_SHA)]+
                         [(d.PROJECT/name,sha) for name,sha in d.OWNER_FINGERPRINTS.items()])

    def test_preflight_rejects_changed_resources_destinations_and_fingerprint_set(self):
        mutations=[lambda b:b['resources'].update(cpu_seconds=True),
                   lambda b:b['resources'].update(wall_seconds=10801),
                   lambda b:b.update(output_directory='artifacts/source-import-runs/another'),
                   lambda b:b['fingerprints'].update(extra='0'*64)]
        for mutation in mutations:
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                self.preflight_mock(mutation)

    def test_preflight_rejects_original_project_claim_before_snapshot_or_launch(self):
        with self.assertRaises(ValueError):self.preflight_mock(existing_claim=True)

    def test_outer_clock_before_nonclock_imports(self):
        body=ast.parse(SOURCE.read_bytes()).body
        executable=[node for node in body if not (isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant))]
        self.assertIsInstance(executable[0],ast.Import)
        self.assertEqual(executable[0].names[0].name,'time')
        self.assertIsInstance(executable[1],ast.Assign)
        self.assertEqual(executable[1].targets[0].id,'ENTRY_MONOTONIC')


if __name__=='__main__': unittest.main(verbosity=2)
