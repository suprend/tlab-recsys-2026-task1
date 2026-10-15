"""Narrow, frozen accounting-delta checks; no application launch."""
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
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import builtins

started, cpu_start = time.monotonic(), time.process_time()
manifest_path = Path('/tmp/tlab-full-source-import-driver-independent-inputs-v3/input-freeze.json')
manifest_raw = manifest_path.read_bytes()
assert hashlib.sha256(manifest_raw).hexdigest() == 'd6f456eec8b166ca0124b106c9f41ac2d1906aabea1add20b099a882a157ffca'
files = json.loads(manifest_raw)['files']
raws = {}
def freshness():
    for name, entry in files.items():
        current = Path(name).read_bytes()
        snapshot = Path(entry['snapshot_path']).read_bytes()
        assert current == snapshot and len(current) == entry['bytes']
        assert hashlib.sha256(current).hexdigest() == entry['sha256']
        raws[name] = snapshot
freshness()
violations = []
def forbidden(label):
    def call(*args, **kwargs):
        violations.append(label)
        raise AssertionError('Forbidden actual operation: '+label)
    return call
real_import = builtins.__import__
def safe_import(name, *args, **kwargs):
    if name.split('.')[0] in {'ctypes','duckdb','sqlite3','catboost','numpy','pandas','run_source_import','source_import'}:
        return forbidden('import '+name)()
    return real_import(name, *args, **kwargs)
def snapshot_read(path):
    if str(path) not in raws: return forbidden('unfrozen read '+str(path))()
    return raws[str(path)]

observations = {}
class AccountingTests(unittest.TestCase):
    def test_only_outer_limits_assignment_changed_no_other_ast_delta(self):
        old = ast.parse(raws['/tmp/tlab-full-source-import-external-driver-v2.py'])
        new = ast.parse(raws['/tmp/tlab-full-source-import-external-driver-v3.py'])
        self.assertEqual(len(old.body), len(new.body))
        changes = []
        for before, after in zip(old.body, new.body):
            if ast.dump(before) != ast.dump(after):
                self.assertIsInstance(before, ast.Assign)
                self.assertIsInstance(after, ast.Assign)
                self.assertEqual(ast.dump(before.targets[0]), "Name(id='LIMITS', ctx=Store())")
                self.assertEqual(ast.dump(before.targets[0]), ast.dump(after.targets[0]))
                changes.append('LIMITS')
        self.assertEqual(changes, ['LIMITS'])
        self.assertEqual(d.LIMITS, dict(cpu_seconds=7190,wall_seconds=10790,rss_bytes=8*2**30))
        observations['source_delta'] = changes

    def test_outer_plus_single_outside_reserve_equals_original_inner_cap(self):
        freeze = json.loads(raws['/tmp/tlab-full-source-import-external-driver-v3-freeze.json'])
        request = json.loads(raws['/tmp/tlab-full-source-import-request-proposal.json'])
        self.assertEqual(request['resources']['cpu_seconds'],7200)
        self.assertEqual(request['resources']['wall_seconds'],10800)
        self.assertEqual(request['resources']['job_rss_bytes'],8*2**30)
        self.assertEqual(d.LIMITS,freeze['outer_limits'])
        for key in ['cpu_seconds','wall_seconds']:
            self.assertEqual(freeze['root_outside_entry_reserve'][key],10)
            self.assertEqual(freeze['root_metadata_stage_limit'][key],5)
            self.assertEqual(d.LIMITS[key]+freeze['root_outside_entry_reserve'][key],freeze['original_combined_ceiling'][key])
            self.assertEqual(freeze['original_combined_ceiling'][key],request['resources'][key])
            self.assertLessEqual(freeze['root_metadata_stage_limit'][key],freeze['root_outside_entry_reserve'][key])
        self.assertEqual(freeze['v6_internal_reserves_already_inside_outer'],dict(cpu_seconds=2,wall_seconds=5))
        receipt=d.receipt(None,None,False)
        self.assertEqual(receipt['outer_limits'],d.LIMITS)
        self.assertFalse(receipt['external_full_exit_acceptance_issued'])
        self.assertFalse(receipt['driver_exit_tail_measured'])
        self.assertTrue(freeze['actual_external_lifetime_sum_not_yet_measured'])
        self.assertTrue(freeze['root_external_time_l_receipts_and_combined_cap_check_required'])
        self.assertFalse(freeze['execution_granted'])
        observations['accounting'] = dict(outer=d.LIMITS,outside_reserve=freeze['root_outside_entry_reserve'],staging_maximum=freeze['root_metadata_stage_limit'],original_combined_ceiling=freeze['original_combined_ceiling'],internal_V6_reserves_already_in_outer=freeze['v6_internal_reserves_already_inside_outer'],future_actual_sums_not_claimed_measured=True)

    def test_existing_guard_applies_trimmed_outer_bounds_under_mocks(self):
        children = SimpleNamespace(ru_utime=0,ru_stime=0,ru_maxrss=0)
        def call(cpu, elapsed):
            own = SimpleNamespace(ru_utime=cpu,ru_stime=0,ru_maxrss=1)
            with patch.object(d.resource,'getrusage',side_effect=[own,children]),patch.object(d.time,'monotonic',return_value=d.ENTRY_MONOTONIC+elapsed):
                d.guard()
        call(7184.9,10784.9)
        with self.assertRaisesRegex(ValueError,'CPU'):call(7185,0)
        with self.assertRaisesRegex(ValueError,'wall'):call(0,10785)

log=io.StringIO()
with ExitStack() as guards:
    guards.enter_context(patch.object(builtins,'__import__',side_effect=safe_import))
    guards.enter_context(patch.object(Path,'read_bytes',snapshot_read))
    for module,attribute in [(subprocess,'Popen'),(os,'system'),(os,'fork'),(os,'posix_spawn'),(os,'posix_spawnp'),(os,'kill'),(os,'wait4'),(resource,'setrlimit'),(socket,'create_connection')]:
        if hasattr(module,attribute): guards.enter_context(patch.object(module,attribute,side_effect=forbidden(module.__name__+'.'+attribute)))
    guards.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden('socket.connect')))
    author=ModuleType('independent_V3_accounting_selected_author_fixtures')
    author.__file__='/tmp/tlab-full-source-import-external-driver-v3-tests.py'
    sys.modules[author.__name__]=author
    exec(compile(raws[author.__file__],author.__file__,'exec',dont_inherit=True),author.__dict__)
    d=author.d
    selected=['test_one_successful_call_with_original_global_limits_and_entry_clock','test_complete_preflight_accepts_exact_closed_request_and_current_code_pins','test_preflight_rejects_changed_resources_destinations_and_fingerprint_set']
    suite=unittest.TestSuite([author.DriverPureTests(name) for name in selected]+[unittest.defaultTestLoader.loadTestsFromTestCase(AccountingTests)])
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)

freshness()
elapsed,cpu=time.monotonic()-started,time.process_time()-cpu_start
assert elapsed<=5 and cpu<=2
assert not violations
out=dict(status='PASS' if result.wasSuccessful() else 'FAIL',methods=result.testsRun,selected_author_methods=3,independent_accounting_methods=3,failures=len(result.failures),errors=len(result.errors),guard_violations=violations,observations=observations,cpu_seconds=cpu,wall_seconds=elapsed,body_timing_not_external_whole_lifetime=True,freshness_input_count=len(files),input_hashes={p:e['sha256'] for p,e in files.items()},actual_owner_or_backend_calls=0,application_processes=0,archive_DB_model_reads=0,project_or_consumed_root_writes=0,execution_grant=False)
prefix=Path('/tmp/tlab-full-source-import-driver-independent-accounting-pure-v3')
with prefix.with_suffix('.json').open('x') as stream:json.dump(out,stream,sort_keys=True,indent=2);stream.write('\n')
with prefix.with_suffix('.log').open('x') as stream:stream.write(log.getvalue())
print(json.dumps({key:out[key] for key in ['status','methods','failures','errors','guard_violations','cpu_seconds','wall_seconds','freshness_input_count']}))
if not result.wasSuccessful():
    print(log.getvalue())
    raise SystemExit(1)
