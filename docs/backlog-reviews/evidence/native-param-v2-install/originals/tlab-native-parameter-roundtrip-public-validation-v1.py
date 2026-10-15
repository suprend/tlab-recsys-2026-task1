"""Standalone finite verification; no fences or path edits in portable tests."""
import time
ENTRY=time.monotonic()
import resource
import signal
resource.setrlimit(resource.RLIMIT_CPU,(15,15));signal.alarm(20)
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

OUT=Path('/private/tmp/tlab-native-parameter-roundtrip-public-validation-v1')
PUBLIC=OUT/'public'
MANIFEST=Path('/tmp/tlab-native-parameter-roundtrip-public-inputs-v1.json')
MANIFEST_SHA='28e0bab70e83ca6c964726acf8210fb9e531cedfdb558e1d266d608eb5fcf273'
PROJECT=Path('/Users/mdpospelov/tlab-recsys-2026')
COUNTS=dict(CatBoost_import_attempts=0,DuckDB_operation_attempts=0,protected_artifact_open_attempts=0)


def need(value,message):
    if not value:raise AssertionError(message)


def guard():
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    value=dict(self_CPU_seconds=own.ru_utime+own.ru_stime,original_wall_seconds=time.monotonic()-ENTRY,
        self_peak_RSS_bytes=own.ru_maxrss,children_CPU_seconds=child.ru_utime+child.ru_stime,
        children_peak_RSS=child.ru_maxrss)
    need(value['self_CPU_seconds']<14 and value['original_wall_seconds']<19 and
         value['self_peak_RSS_bytes']<=512*2**20,'Public-copy verification budget exhausted')
    need(value['children_CPU_seconds']==value['children_peak_RSS']==0,'No verification children allowed')
    return value


def write(name,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    need(len(raw)<1048576,'Bounded verification receipt required')
    with (OUT/name).open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())


def main():
    need(sys.flags.isolated==1 and sys.flags.dont_write_bytecode==1,'Standalone isolated verification required')
    need(not OUT.exists() and not OUT.is_symlink(),'Verification namespace already consumed')
    OUT.mkdir(mode=0o700);write('consumed.json',dict(scope='one_metadata_public_copy_validation',status='consumed_no_retry'))
    rows=None;result=None
    try:
        raw=MANIFEST.read_bytes();need(hashlib.sha256(raw).hexdigest()==MANIFEST_SHA,'Frozen public source map changed')
        rows=json.loads(raw)['source_only_public_copy_inputs']
        need(len(rows)==20,'Exact source-only public copy set required')
        PUBLIC.mkdir(mode=0o700)
        for relative,row in rows.items():
            guard();source=Path(row['source_path']);raw=source.read_bytes()
            need(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'Public-copy source changed')
            target=PUBLIC/relative;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with target.open('xb') as handle:handle.write(raw)
        cache=OUT/'pycache';cache.mkdir(mode=0o700);sys.pycache_prefix=str(cache)
        sys.path.insert(0,str(PUBLIC))  # Standalone test-copy selection only.
        real_import=builtins.__import__
        def import_guard(name,*args,**kwargs):
            if name.split('.')[0]=='catboost':
                COUNTS['CatBoost_import_attempts']+=1;raise AssertionError('No CatBoost import in metadata validation')
            return real_import(name,*args,**kwargs)
        def forbidden_database(*args,**kwargs):
            COUNTS['DuckDB_operation_attempts']+=1;raise AssertionError('No DuckDB operation in metadata validation')
        def protected(file):
            if isinstance(file,(str,bytes,os.PathLike)):
                p=Path(os.fsdecode(file))
                return (p.suffix.lower() in {'.cbm','.npz','.duckdb'} or
                        p.is_relative_to(PROJECT/'artifacts') or p.is_relative_to(PROJECT/'data'))
            return False
        real_open=builtins.open;real_io_open=io.open
        def guarded_open(file,*args,**kwargs):
            if protected(file):
                COUNTS['protected_artifact_open_attempts']+=1;raise AssertionError('No actual artifact/data/model reads')
            return real_open(file,*args,**kwargs)
        def guarded_io_open(file,*args,**kwargs):
            if protected(file):
                COUNTS['protected_artifact_open_attempts']+=1;raise AssertionError('No actual artifact/data/model reads')
            return real_io_open(file,*args,**kwargs)
        with patch.object(builtins,'__import__',side_effect=import_guard):
            import duckdb
            from contextlib import ExitStack
            with ExitStack() as stack:
                for name in ('connect','execute','sql','query','read_parquet','read_csv','from_df'):
                    if hasattr(duckdb,name):stack.enter_context(patch.object(duckdb,name,side_effect=forbidden_database))
                stack.enter_context(patch.object(builtins,'open',side_effect=guarded_open))
                stack.enter_context(patch.object(io,'open',side_effect=guarded_io_open))
                from tests import test_native_parameter_roundtrip as portable
                from tests import test_heldout_prediction_audit as previous
                from scripts import heldout_predictions as production
                from tests.oracles import heldout_prediction_audit as oracle
                need(Path(production.__file__).resolve()==PUBLIC/'scripts/heldout_predictions.py' and
                     Path(oracle.__file__).resolve()==PUBLIC/'tests/oracles/heldout_prediction_audit.py',
                     'Normal imported implementations escaped the exact public copy')
                class ImportBoundaryOnly(unittest.TestCase):
                    def test_existing_import_allowlist_method_only(self):
                        # Existing setUp/audit allocate SQL fixtures; this narrow
                        # body-only check runs its actual AST import allowlist.
                        case=previous.PredictionOracleTests('test_no_file_opener_and_no_production_matrix_or_scoring_import')
                        case.audit=lambda: None
                        case.test_no_file_opener_and_no_production_matrix_or_scoring_import()
                suite=unittest.TestSuite([
                    unittest.defaultTestLoader.loadTestsFromTestCase(portable.NativeParameterRoundtripTests),
                    unittest.defaultTestLoader.loadTestsFromTestCase(ImportBoundaryOnly)])
                guard();result=unittest.TextTestRunner(verbosity=2).run(suite);guard()
                need(result.wasSuccessful() and result.testsRun==8,'Portable regression or import allowlist failed')
                need(all(value==0 for value in COUNTS.values()),'Forbidden native/data operation attempted')
        need('catboost' not in sys.modules,'No actual CatBoost package loaded')
        for relative,row in rows.items():
            guard();need(hashlib.sha256((PUBLIC/relative).read_bytes()).hexdigest()==row['sha256'],
                         'Public source/test/fixture changed during validation')
            need(hashlib.sha256(Path(row['source_path']).read_bytes()).hexdigest()==row['sha256'],
                 'Original source changed during validation')
        receipt=dict(version=1,scope='portable_parameter_roundtrip_metadata_validation_only',status='PASS',
            tests=8,new_portable_methods=7,existing_import_whitelist_method=1,normal_imports=True,
            locked_native_packages_imported=sorted(name for name in ('numpy','pandas','duckdb') if name in sys.modules),
            native_operations=COUNTS,native_model_loads=0,predictions=0,fits=0,source_DB_Y_opens=0,
            actual_project_writes=False,accepted_implementation_bytes_unchanged=True,
            public_copy_sha256s={k:v['sha256'] for k,v in rows.items()},telemetry=guard(),
            full_exit_profile_pending=True,source_or_runtime_acceptance_issued=False)
        write('receipt.json',receipt);guard();return 0
    except BaseException as error:
        try:write('failure.json',dict(status='failed_consumed_no_retry',type=type(error).__name__,error=str(error),
            counts=COUNTS,telemetry=guard()))
        except BaseException as secondary:print('Failure receipt unknown: '+str(secondary),file=sys.stderr)
        print('Public metadata validation failed: '+type(error).__name__+': '+str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
