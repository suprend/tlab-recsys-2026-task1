"""Bounded frozen-source independent CODE probes. No application launch."""
import ast
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import time
import traceback
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import builtins

START_WALL = time.monotonic()
START_CPU = time.process_time()
MANIFESTS = {
    '/tmp/tlab-full-source-import-driver-independent-inputs-v1/input-freeze.json': 'accc729f368f63ea1751aa4c07f410809fd2f3c55809f0318997d6e2369e5c46',
    '/tmp/tlab-full-source-import-driver-independent-inputs-v2/input-freeze.json': '26468fca1538a126cb06aa245fd51427d8647eee24fc49f079b6536b3e75492a',
}
FILES = {}
RAW = {}
for name, digest in MANIFESTS.items():
    data = Path(name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    for original, entry in json.loads(data)['files'].items():
        raw = Path(entry['snapshot_path']).read_bytes()
        assert len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256']
        if original in FILES:
            assert FILES[original]['sha256'] == entry['sha256']
        FILES[original] = entry
        RAW[original] = raw

def freshness():
    results = {}
    for original, entry in FILES.items():
        current = Path(original).read_bytes()
        snapshot = Path(entry['snapshot_path']).read_bytes()
        okay = (hashlib.sha256(current).hexdigest() == entry['sha256']
                and snapshot == current and len(current) == entry['bytes'])
        assert okay, original
        results[original] = entry['sha256']
    return results

PRE = freshness()
VIOLATIONS = []
def forbidden(label):
    def call(*args, **kwargs):
        VIOLATIONS.append(label)
        raise AssertionError('Forbidden actual operation: '+label)
    return call

def load_driver(version):
    name = '/tmp/tlab-full-source-import-external-driver-'+version+'.py'
    module = ModuleType('independent_driver_'+version)
    module.__file__ = name
    sys.modules[module.__name__] = module
    exec(compile(RAW[name], name, 'exec', dont_inherit=True), module.__dict__)
    return module

owner_name = '/Users/mdpospelov/tlab-recsys-2026/scripts/run_source_import.py'
owner_tree = ast.parse(RAW[owner_name], owner_name)
owner_nodes = [node for node in owner_tree.body
               if isinstance(node, ast.FunctionDef) and node.name in {'need', 'local'}]
assert {node.name for node in owner_nodes} == {'need', 'local'}
OWNER_NAMESPACE = {'ROOT': Path('/Users/mdpospelov/tlab-recsys-2026')}
exec(compile(ast.Module(body=owner_nodes, type_ignores=[]), owner_name, 'exec', dont_inherit=True), OWNER_NAMESPACE)

V1 = load_driver('v1')
V2 = load_driver('v2')
OBSERVATIONS = {}

class IndependentTests(unittest.TestCase):
    def test_actual_owner_interface_original_red_same_function_repaired_green(self):
        local = OWNER_NAMESPACE['local']
        argv1, argv2 = V1.command(), V2.command()
        arg1, arg2 = argv1[5], argv2[5]
        with patch.object(Path, 'resolve', lambda value: value), patch.object(Path, 'is_symlink', return_value=False):
            try:
                local(arg1, existing=False)
            except ValueError as exc:
                self.assertEqual(str(exc), 'Normalized project-relative path required')
                OBSERVATIONS['original_v1_red'] = dict(error_type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc(), command=argv1)
            else:
                self.fail('Original V1 interface defect did not reproduce')
            actual = local(arg2, existing=False)
        self.assertEqual(actual, V2.REQUEST)
        self.assertEqual(arg2, 'artifacts/reproduction/requests/oct2019-full-018-20261015-once.json')
        self.assertEqual(argv2[:5], argv1[:5])
        self.assertEqual(argv2[6:], argv1[6:])
        OBSERVATIONS['repaired_v2_green'] = dict(command=argv2, resolved=str(actual), filesystem_observation_mocked=True, owner_imported=False)

    def test_only_command_ast_changes_absolute_snapshot_and_caps_retained(self):
        trees = [ast.parse(RAW['/tmp/tlab-full-source-import-external-driver-'+v+'.py']) for v in ['v1','v2']]
        old, new = trees
        changed = []
        self.assertEqual(len(old.body), len(new.body))
        for left, right in zip(old.body, new.body):
            if ast.dump(left) != ast.dump(right):
                self.assertIsInstance(left, ast.FunctionDef)
                self.assertEqual(left.name, right.name)
                changed.append(left.name)
        self.assertEqual(changed, ['command'])
        self.assertEqual(V1.REQUEST, V2.REQUEST)
        self.assertTrue(V2.REQUEST.is_absolute())
        self.assertEqual(V1.REQUEST_SHA, V2.REQUEST_SHA)
        self.assertEqual(V2.LIMITS, dict(cpu_seconds=7200, wall_seconds=10800, rss_bytes=8*2**30))
        OBSERVATIONS['source_delta'] = changed

    def test_interrupt_and_systemexit_preserve_original_cleanup_with_one_attempt(self):
        for cls in [KeyboardInterrupt, SystemExit]:
            for reaped in [True, False]:
                with self.subTest(exception=cls.__name__, reaped=reaped):
                    exc = cls('primary-interruption')
                    exc.supervisor_cleanup_evidence = dict(reaped=reaped, ownership_phase='reaped' if reaped else 'lost', retained_wait4_result=[123, 0, 1.25] if reaped else None, cleanup_nested_unknown=not reaped, actual_cpu=1.25 if reaped else None)
                    calls, writes = [], {}
                    def fake_supervise(*args, **kwargs):
                        calls.append((args, kwargs))
                        raise exc
                    def record(path, body):
                        if path in writes: raise FileExistsError(str(path))
                        writes[path] = json.loads(json.dumps(body))
                    with patch.object(V2, 'reject_existing_outputs'), patch.object(V2, 'preflight', return_value=V2.command()), patch.object(V2, 'load_supervisor', return_value=SimpleNamespace(supervise=fake_supervise)), patch.object(V2, 'guard'), patch.object(V2, 'exclusive_json', side_effect=record), patch.object(V2.sys, 'stderr', io.StringIO()):
                        result = V2.main()
                    self.assertEqual(result, 1)
                    self.assertEqual(len(calls), 1)
                    body = writes[V2.PROCESS_RECEIPT]
                    self.assertEqual(body['supervisor_exception_cleanup_evidence'], exc.supervisor_cleanup_evidence)
                    self.assertFalse(body['external_full_exit_acceptance_issued'])
                    self.assertFalse(body['source_acceptance_issued'])
                    self.assertIn(V2.DRIVER_ERROR, writes)
                    self.assertNotIn(V2.DRIVER_STDOUT, writes)

    def test_exclusive_serializer_uses_exclusive_create_and_rejects_bad_json_before_open(self):
        opened, saved = [], {}
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def write(self, raw): saved['raw'] = raw
            def flush(self): saved['flushed'] = True
            def fileno(self): return 123
        def fake_open(path, flags, mode):
            opened.append((path, flags, mode))
            return 123
        target = Path('/tmp/pure-output-never-created.json')
        with patch.object(V2.os, 'open', side_effect=fake_open), patch.object(V2.os, 'fdopen', return_value=Stream()), patch.object(V2.os, 'fsync') as sync:
            V2.exclusive_json(target, {'status':'pending', 'value':1})
            self.assertEqual(opened, [(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)])
            self.assertEqual(json.loads(saved['raw']), {'status':'pending','value':1})
            sync.assert_called_once_with(123)
            with self.assertRaises(ValueError): V2.exclusive_json(target, {'value':float('nan')})
            self.assertEqual(len(opened), 1)

    def test_fresh_child_and_outer_resource_limits_fail_closed_under_mocks(self):
        own = SimpleNamespace(ru_utime=.1, ru_stime=.1, ru_maxrss=25*2**20)
        zero = SimpleNamespace(ru_utime=0, ru_stime=0, ru_maxrss=0)
        def run(own_usage, child_usage, elapsed):
            with patch.object(V2.resource, 'getrusage', side_effect=[own_usage,child_usage]), patch.object(V2.time, 'monotonic', return_value=V2.ENTRY_MONOTONIC+elapsed):
                V2.guard()
        run(own, zero, .1)
        for changed in [dict(ru_utime=.1,ru_stime=0,ru_maxrss=0), dict(ru_utime=0,ru_stime=0,ru_maxrss=1)]:
            with self.assertRaises(ValueError): run(own, SimpleNamespace(**changed), .1)
        with self.assertRaises(ValueError): run(SimpleNamespace(ru_utime=7195,ru_stime=0,ru_maxrss=1), zero,.1)
        with self.assertRaises(ValueError): run(own,zero,10795)
        with self.assertRaises(ValueError): run(SimpleNamespace(ru_utime=0,ru_stime=0,ru_maxrss=8*2**30+1),zero,.1)

real_import = builtins.__import__
def safe_import(name, *args, **kwargs):
    if name.split('.')[0] in {'ctypes','duckdb','sqlite3','catboost','numpy','pandas','run_source_import','source_import'}:
        return forbidden('import '+name)()
    return real_import(name, *args, **kwargs)

real_read_bytes = Path.read_bytes
def snapshot_read(path):
    name = str(path)
    if name not in RAW:
        return forbidden('unfrozen source read '+name)()
    return RAW[name]

log = io.StringIO()
with ExitStack() as stack:
    stack.enter_context(patch.object(builtins, '__import__', side_effect=safe_import))
    stack.enter_context(patch.object(Path, 'read_bytes', snapshot_read))
    for module, attribute in [(subprocess,'Popen'),(os,'system'),(os,'fork'),(os,'posix_spawn'),(os,'posix_spawnp'),(os,'kill'),(os,'wait4'),(resource,'setrlimit'),(socket,'create_connection')]:
        if hasattr(module, attribute): stack.enter_context(patch.object(module, attribute, side_effect=forbidden(module.__name__+'.'+attribute)))
    stack.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden('socket.connect')))
    # Author fixture loads only pinned snapshots through the read-only map.
    author = ModuleType('independent_frozen_author_suite_v2')
    author.__file__ = '/tmp/tlab-full-source-import-external-driver-v2-tests.py'
    sys.modules[author.__name__] = author
    exec(compile(RAW[author.__file__], author.__file__, 'exec', dont_inherit=True), author.__dict__)
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(author),unittest.defaultTestLoader.loadTestsFromTestCase(IndependentTests)])
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)

POST = freshness()
elapsed, cpu = time.monotonic()-START_WALL, time.process_time()-START_CPU
assert elapsed <= 5 and cpu <= 2, (elapsed,cpu)
assert not VIOLATIONS, VIOLATIONS
output = dict(status='PASS' if result.wasSuccessful() else 'FAIL', methods=result.testsRun, author_methods=16, independent_methods=5, failures=len(result.failures), errors=len(result.errors), observations=OBSERVATIONS, guard_violations=VIOLATIONS, actual_owner_imported=False, actual_supervisor_or_backend_called=False, application_processes=0, actual_archive_DB_model_reads=0, project_or_consumed_root_writes=0, cpu_seconds=cpu, wall_seconds=elapsed, body_measurement_not_external_whole_lifetime=True, input_hashes_pre=PRE,input_hashes_post=POST)
prefix = Path('/tmp/tlab-full-source-import-driver-independent-pure-v1-v2')
with prefix.with_suffix('.log').open('x') as stream: stream.write(log.getvalue())
with prefix.with_suffix('.json').open('x') as stream: json.dump(output,stream,sort_keys=True,indent=2);stream.write('\n')
print(json.dumps({key:output[key] for key in ['status','methods','author_methods','independent_methods','failures','errors','cpu_seconds','wall_seconds','guard_violations']}))
if not result.wasSuccessful():
    print(log.getvalue())
    raise SystemExit(1)
