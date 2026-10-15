import gc,json,sys,unittest
from tests import test_heldout_source_worker as tests
warnings=[];original=sys.unraisablehook
sys.unraisablehook=lambda error:warnings.append(dict(type=error.exc_type.__name__,message=str(error.exc_value)))
try:
 case=tests.SourceWorker('test_close_error_prevents_evidence_persistence');result=unittest.TestResult();case.run(result);gc.collect()
 print(json.dumps(dict(author_test_errors=len(result.errors),author_test_failures=len(result.failures),unraisable=warnings),indent=2))
finally:sys.unraisablehook=original
