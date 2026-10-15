"""Prepared single engineering check. Root must issue the separate20/30 grant."""
import time
START_CPU, START_WALL = time.process_time(), time.monotonic()
import sys, os, resource, signal, json, hashlib
from pathlib import Path

WORK = Path(__file__).resolve().parent
COPY, FIXTURES = WORK / 'checkout', WORK / 'fixtures'
MANIFEST = WORK / 'manifest.json'
RESULT, CONSUMED = WORK / 'result.json', WORK / 'consumed.json'
MANIFEST_SHA = '217a7635a46713a3b396f868c214fd6d2fcab5e49a0b4640ebc1e85ac7d6fc5e'
REAL_PROJECT = Path('/Users/mdpospelov/tlab-recsys-2026')
SITE = REAL_PROJECT / '.venv/lib/python3.12/site-packages'
resource.setrlimit(resource.RLIMIT_CPU, (17, 18))

def interrupted(signum, frame):
    raise RuntimeError('Integration CPU/wall fence reached')

signal.signal(signal.SIGXCPU, interrupted)
signal.signal(signal.SIGALRM, interrupted)
signal.alarm(25)
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert not RESULT.exists() and not CONSUMED.exists() and not FIXTURES.exists()
with CONSUMED.open('x') as stream:
    json.dump(dict(scope='single_V3_import13_existing14_engineering_attempt', retry=False,
                   proposed_total_cpu=20, proposed_total_wall=30, scientific_proof=False), stream)
FIXTURES.mkdir(mode=0o700)
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '2'

violations = []
class GuardViolation(BaseException):
    pass

def deny(kind, detail):
    violations.append(dict(kind=kind, detail=str(detail)))
    raise GuardViolation(kind + ': ' + str(detail))

READ_DIRS = tuple(p.resolve() for p in (WORK, SITE, Path(sys.base_prefix),
                 Path('/System/Library'), Path('/usr/lib'), Path('/usr/share/zoneinfo'),
                 Path('/var/db/timezone/zoneinfo')))
READ_FILES = {Path('/dev/null').resolve(), Path('/etc/localtime').resolve()}

def inside(path, root):
    return path == root or root in path.parents

def file_access(value, write=False):
    if isinstance(value, int):
        return  # inherited stdin/stdout/stderr descriptors, not path opens.
    path = Path(os.fsdecode(value)).resolve()
    if inside(path, REAL_PROJECT / 'data') or inside(path, REAL_PROJECT / 'artifacts'):
        deny('real_project_data_or_artifact_access', path)
    allowed = inside(path, WORK) if write else (path in READ_FILES or any(inside(path, root) for root in READ_DIRS))
    if not allowed:
        deny('outside_owned_write' if write else 'outside_runtime_read', path)

def audit(event, args):
    if event == 'open':
        mode, flags = args[1], args[2]
        write = isinstance(mode, str) and any(letter in mode for letter in 'wax+')
        write = write or isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        file_access(args[0], write)
    elif event in ('os.listdir', 'os.scandir'):
        file_access(args[0] if args else '.', False)
    elif event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn',
                   'os.posix_spawnp', 'os.exec', 'pty.spawn') or event.startswith('socket.'):
        deny('process_or_network_attempt', event)
    elif event == 'import' and (args[0] == 'catboost' or args[0].startswith('catboost.')):
        deny('CatBoost_import_attempt', args[0])

sys.addaudithook(audit)
sys.path.insert(0, str(SITE))  # -S bypasses .pth/sitecustomize; no package installation.
sys.path.insert(0, str(COPY))

def cost():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return dict(cpu_seconds=time.process_time() - START_CPU, wall_seconds=time.monotonic() - START_WALL,
                peak_rss_bytes=int(peak if sys.platform == 'darwin' else peak * 1024),
                scope='harness entry through sample; full startup/exit/Root readback external')

def check():
    sample = cost()
    if sample['cpu_seconds'] >= 17 or sample['wall_seconds'] >= 25 or sample['peak_rss_bytes'] > 512 * 2**20:
        raise RuntimeError('Integration original CPU/wall/RSS cap exceeded')
    if violations:
        raise GuardViolation('A forbidden attempt was observed; acceptance prohibited')

def witness(path):
    check(); raw = Path(path).read_bytes(); check()
    return dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))

status, error, tests_run, engine_connections, loaded = 'failed', None, 0, 0, []
failures = []
try:
    assert witness(MANIFEST)['sha256'] == MANIFEST_SHA
    manifest = json.loads(MANIFEST.read_bytes())
    for name, expected in manifest['files'].items():
        assert witness(COPY / name) == expected, 'Prepared input changed: ' + name
    import tempfile
    tempfile.tempdir = str(FIXTURES)
    # A real engine connection; only native filesystem policy is added. Existing
    # test SQL, data, result interfaces and resource settings remain unchanged.
    import duckdb
    original_connect = duckdb.connect
    def owned_memory_connect(*args, **kwargs):
        global engine_connections
        database = kwargs.get('database', args[0] if args else ':memory:')
        if database != ':memory:':
            deny('non_memory_engine_database', database)
        con = original_connect(*args, **kwargs)
        try:
            escaped = str(FIXTURES).replace("'", "''")
            con.execute("SET allowed_directories = ['" + escaped + "']")
            con.execute('SET enable_external_access = false')
        except BaseException:
            con.close()
            raise
        engine_connections += 1
        return con
    duckdb.connect = owned_memory_connect
    from scripts import reproduce_frozen_comparison as entry
    recipe, raw_recipe, recipe_ref = entry.validate_recipe(COPY / 'configs/reproduction/frozen-bw-oct2019.json', check)
    binding = entry.SourceBinding(recipe, check)
    binding.load_cores()
    loaded = sorted(binding.loaded)
    assert len(loaded) == 13
    binding.check(); check()
    import unittest
    from tests import test_reproduce_frozen_comparison as test_module
    class BoundedResult(unittest.TextTestResult):
        def startTest(self, test):
            check(); super().startTest(test)
        def stopTest(self, test):
            super().stopTest(test); check()
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_module)
    assert suite.countTestCases() == 14
    result = unittest.TextTestRunner(verbosity=2, failfast=True, resultclass=BoundedResult).run(suite)
    tests_run = result.testsRun
    failures = [(str(case), text) for case, text in result.failures + result.errors]
    assert result.wasSuccessful() and tests_run == 14, 'Existing fourteen-method integration did not pass'
    binding.check()
    for name, expected in manifest['files'].items():
        assert witness(COPY / name) == expected, 'Copied input changed at close: ' + name
    assert not any(name == 'catboost' or name.startswith('catboost.') for name in sys.modules)
    check(); status = 'passed_engineering_only_pending_Root_full_exit_readback'
except BaseException as primary:
    error = dict(type=type(primary).__name__, message=str(primary))
finally:
    body = dict(version=1, status=status, error=error, tests_run=tests_run, failures=failures,
                full_core_modules=loaded, core_count=len(loaded), native_memory_connections=engine_connections,
                native_policy='owned fixture allowlist + enable_external_access=false', guard_violations=violations,
                cost=cost(), actual_CatBoost_imported=any(n == 'catboost' or n.startswith('catboost.') for n in sys.modules),
                actual_ML_operations=0, scientific_model_proof=False, clean_environment_proof=False,
                new_engineering_operation=True, prior_author_allowance_refilled=False,
                external_full_exit_accepted=False, retry=False)
    with RESULT.open('x') as stream:
        json.dump(body, stream, indent=2, sort_keys=True)
    print(json.dumps(body)); signal.alarm(0)
raise SystemExit(0 if status.startswith('passed_engineering_only') else 1)
