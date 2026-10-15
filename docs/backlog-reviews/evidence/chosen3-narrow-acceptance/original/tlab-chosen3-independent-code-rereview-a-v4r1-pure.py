"""One bounded focused pure run: exact V3 red + immutable V4r1 15-method green."""
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import ast,ctypes,hashlib,io,json,resource,subprocess,sys,time,traceback,unittest
started=time.monotonic();start_usage=resource.getrusage(resource.RUSAGE_SELF);root=Path('/tmp/tlab-chosen3-independent-code-rereview-a-v4r1-inputs');source=root/'tlab-chosen3-six-role-candidate-v4r1.py';tests=root/'tlab-test-chosen3-six-role-candidate-v4r1.py';raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()=='4eca34e06847250db06844335d66c28b2fbbb01e685f2c8c798fd9d0d8ea2655';module=ModuleType('chosen3_v4r1_frozen_author_pure');module.__file__=str(tests);original_read_bytes=Path.read_bytes
snapshot_reads={'/tmp/tlab-chosen3-six-role-candidate-v4r1.py':raw,'/tmp/tlab-chosen3-v4-complete-json-fixture.json':(root/'tlab-chosen3-v4-complete-json-fixture.json').read_bytes()}
def pinned_read(path):return snapshot_reads[str(path)] if str(path) in snapshot_reads else original_read_bytes(path)
with patch.object(Path,'read_bytes',pinned_read):exec(compile(tests.read_bytes(),str(tests),'exec',dont_inherit=True),module.__dict__)
forbidden_attempts=[]
def forbidden(*a,**kw):forbidden_attempts.append('real process/native/resource');raise AssertionError('Forbidden real process/native/resource operation')
real_open=Path.open
def guarded_open(path,*a,**kw):
 if path.suffix.lower() in {'.cbm','.duckdb','.db','.npz','.parquet','.gz'}:forbidden_attempts.append(str(path));raise AssertionError('Forbidden binary/model/data open')
 return real_open(path,*a,**kw)
oldraw=(root/'tlab-chosen3-six-role-candidate-v3.py').read_bytes();old=ModuleType('chosen3_original_v3_red');old.__file__='/tmp/tlab-chosen3-six-role-candidate-v3.py';assert hashlib.sha256(oldraw).hexdigest()=='b40060a970546ea749291695bd60585b06ad7f1facdbf2388e6bfb1371f43a6d';exec(compile(oldraw,old.__file__,'exec',dont_inherit=True),old.__dict__)
output=io.StringIO();old_red=None;overlap=[]
with patch.object(subprocess,'Popen',side_effect=forbidden),patch.object(ctypes,'CDLL',side_effect=forbidden),patch.object(resource,'setrlimit',side_effect=forbidden),patch.object(Path,'open',guarded_open),patch.object(Path,'read_bytes',pinned_read):
 case=module.Chosen3Contracts('test_complete_verify_results_returns_summary_from_full_production_JSON_scene')
 with patch.object(module,'c',old):
  try:case.test_complete_verify_results_returns_summary_from_full_production_JSON_scene()
  except TypeError as error:
   assert 'metric_delta_required_nonzero' in str(error);old_red={'expected_error':str(error),'traceback':traceback.format_exc(),'reached_original_constructor':any(frame.filename==old.__file__ and frame.lineno==266 for frame in traceback.extract_tb(error.__traceback__))};assert old_red['reached_original_constructor']
  else:raise AssertionError('Original V3 must retain expected constructor red')
 result=unittest.TextTestRunner(stream=output,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
for node in ast.walk(ast.parse(raw)):
 if isinstance(node,ast.Call) and any(k.arg is None and isinstance(k.value,ast.Name) and k.value.id=='DISCLOSURES' for k in node.keywords):
  bad={k.arg for k in node.keywords if k.arg is not None}&set(module.c.DISCLOSURES)
  if bad:overlap.append((node.lineno,sorted(bad)))
assert overlap==[];end=resource.getrusage(resource.RUSAGE_SELF);cpu=end.ru_utime+end.ru_stime-start_usage.ru_utime-start_usage.ru_stime;wall=time.monotonic()-started;assert cpu<2 and wall<5;assert forbidden_attempts==[]
ledger={'scope':'one immutableV4r1 focused pure repair check; original actual V3 stays FAILED','source_sha256':hashlib.sha256(raw).hexdigest(),'tests_sha256':hashlib.sha256(tests.read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256(snapshot_reads['/tmp/tlab-chosen3-v4-complete-json-fixture.json']).hexdigest(),'originalV3_expected_red':old_red,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),'AST_DISCLOSURES_explicit_keyword_overlaps':overlap,'cpu_seconds':cpu,'wall_seconds':wall,'python':sys.version.split()[0],'forbidden_attempts':forbidden_attempts,'actual_new_native_process_backend_helper_calls':0,'actual_model_DB_NPZ_reads_or_hashes':0,'actual_application_root_writes_or_refills':0,'actual_failed_operation_promoted':False,'fixture_limits':'positive virtual scene omits actual outer failed markers, four gate placeholders; binary hashes/native/metric import/resources mocked'}
Path('/tmp/tlab-chosen3-independent-code-rereview-a-v4r1-pure.log').write_text(output.getvalue());Path('/tmp/tlab-chosen3-independent-code-rereview-a-v4r1-original-v3-red.log').write_text(old_red['traceback']);Path('/tmp/tlab-chosen3-independent-code-rereview-a-v4r1-pure-results.json').write_text(json.dumps(ledger,indent=2)+'\n');print(json.dumps({k:v for k,v in ledger.items() if k!='originalV3_expected_red'},indent=2));print(json.dumps({'originalV3_expected_red':old_red['expected_error'],'reached_line266':old_red['reached_original_constructor']},indent=2));raise SystemExit(not result.wasSuccessful())
