"""Standalone finite verification fence; not a collectable test module."""
import time
ENTRY=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(59,60))
import signal
signal.alarm(120)
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path('/tmp/tlab-reproduction-portable-public-v1')
sys.path.insert(0,str(ROOT))
path=ROOT/'tests/test_reproduce_development_slice.py'
pre=dict(limits=resource.getrlimit(resource.RLIMIT_CPU),alarm_handler=signal.getsignal(signal.SIGALRM),
         cache_prefix=sys.pycache_prefix,sys_path=list(sys.path))
spec=importlib.util.spec_from_file_location('portable_test_under_verification',path)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
post=dict(limits=resource.getrlimit(resource.RLIMIT_CPU),alarm_handler=signal.getsignal(signal.SIGALRM),
          cache_prefix=sys.pycache_prefix,sys_path=list(sys.path))
assert pre==post,'Test import mutated standalone verification state'
assert not any(name in sys.modules for name in ['duckdb','numpy','pandas','catboost']), 'Test import loaded native packages'
result=None
try:
    result=unittest.TextTestRunner(verbosity=2,stream=sys.stdout).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    assert module.adapter.REQUIRED_QUERIES==2000 and module.adapter.MAX_ROWS==440000, 'Scoped core patches not restored'
    assert module.adapter.__name__=='scripts.reproduce_development_slice'
    assert str(module.PROJECT)==str(ROOT)
    if 'scripts.inference_data' in sys.modules:assert sys.modules['scripts.inference_data'].ROOT==ROOT,'Scoped inference ROOT not restored'
finally:
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    peak=own.ru_maxrss*(1024 if sys.platform.startswith('linux') else 1)
    receipt=dict(scope='portable_public_test_transport_verification_only',tests_run=result.testsRun if result else None,
        success=result.wasSuccessful() if result else False,failures=len(result.failures) if result else None,errors=len(result.errors) if result else None,
        process_cpu_seconds=own.ru_utime+own.ru_stime,observed_wall_seconds=time.monotonic()-ENTRY,process_peak_rss_bytes=peak,
        children_cpu_seconds=child.ru_utime+child.ru_stime,children_peak_rss=child.ru_maxrss,
        test_import_changed_fence_alarm_cache_or_path=pre!=post,test_import_loaded_native_packages=False,
        normal_scripts_import=True,PROJECT_from_test_parents=True,patches_scoped_and_restored=True,
        portable_test_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        actual_data_or_models_opened=False,fit_attempt_count=0,native_ML_calls=0,fake_prediction_calls=2,
        invented_events=8,queries=2,candidates=1,limits=dict(cpu_seconds=60,wall_seconds=120,process_peak_rss_bytes=512*2**20),
        public_copy=str(ROOT),source_copy_modules=14,driver_unseen_exit_tail_measured=False)
    target=Path('/tmp/tlab-portable-development-slice-verification-v1-receipt.json')
    with target.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(receipt,sort_keys=True))
    assert own.ru_utime+own.ru_stime<=60 and time.monotonic()-ENTRY<=120 and peak<=512*2**20
    assert child.ru_utime+child.ru_stime==0 and child.ru_maxrss==0
raise SystemExit(0 if result is not None and result.wasSuccessful() else 1)
