# Historical019 audit source: launch-checks

Aggregate/synthetic evidence archive. Paths below are normalized for privacy; this preserves the historical observer, not a new execution approval. Original freeze references belong to the version reviewed by that pass. No real019 model fit was run by these checks.

```python
import sys,json,hashlib,time,tempfile,resource
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,'project root')
from scripts import strong_baseline as s
import tests.test_strong_baseline as fixtures
ROOT=Path('project root');FILES={'scripts/strong_baseline.py':'10dffd789dded9a578b397b95a7b209285857459c0c92c8c925d1dfca6df3147','tests/test_strong_baseline.py':'1f9527c9fba10d88999f7984472bd7b820890e9ee9a4bf00db6ac6b456117ee8','configs/models/strong-grid.json':'d32daac420f447444d987969cdd49ac1cad427bbd7357114d148c02085aed66e','docs/experiments/strong-baseline.md':'95a7cf972fca056160f5f8b88902c2297edc4f7f56766b16430b3c068602bf10'}
def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
before=hashes();assert before==FILES;results=[];START=time.monotonic();CPU=time.process_time()
def case(n,f):
 try:results.append(dict(case=n,status='PASS',detail=f()))
 except BaseException as e:results.append(dict(case=n,status='FAIL',error=repr(e)))
def flow():
 f=fixtures.ContextTests('test_exact_bound_context_and_reserved_three_looks');f.setUp()
 try:
  context=s.read(f.context);expected=s.expected_worker(f.parent,f.slot,context,f.context);wd=s.local(f.slot['output_root'])/expected['run_id'];wd.mkdir(parents=True)
  report=dict(run_id=expected['run_id'],parent_run_id=f.parent['run_id'],mode='arm',index=0,population=6000,fit_attempt_count=0,status='failed',outcome='resource_failure',error_type='MemoryError')
  s.write(wd/'report.json',report);s.write(wd/'run.json',expected);s.write(s.local(context['slot_path']).with_suffix('.consumed.json'),dict(version=1,parent_run_id=f.parent['run_id'],token=f.slot['token'],context_sha256=f.issued))
  argv=[]
  def launch(args,log,**kwargs):
   receipt=Path(log).with_suffix('.launch.json');assert receipt.exists();argv.append(list(args));Path(log).write_text('mocked worker resource failure');return 1
  with patch.object(s,'run_process',side_effect=launch):result=s.invoke_worker(f.directory,f.parent,f.slot,f.context,Mock(),issued_context_sha256=f.issued)
  ref=result['launch_receipt'];lp=s.local(ref['path']);assert s.sha(lp)==ref['sha256'];body=s.read(lp)
  expected_body=dict(version=1,scope='strong_issued_worker_launch',parent_run_id=f.parent['run_id'],worker_run_id=expected['run_id'],context_path=s.relative(f.context),issued_context_sha256=f.issued,slot=f.slot,argv=[sys.executable,'-m','scripts.strong_baseline','--worker-context',s.relative(f.context),'--issued-context-sha256',f.issued],cwd=str(f.root),log_path=s.relative(f.directory/'logs/arm-0.log'))
  assert body==expected_body and argv==[expected_body['argv']]
  s.write(f.directory/'winner.json',dict(synthetic=True));assert s.relative(lp) in s.seal_outputs(f.directory)
  with patch.object(s,'run_process',side_effect=AssertionError('must not respawn')):
   try:s.invoke_worker(f.directory,f.parent,f.slot,f.context,Mock(),issued_context_sha256=f.issued)
   except FileExistsError:pass
   else:raise AssertionError('launch overwritten')
  return dict(record_before_spawn=True,returned_exact_pin=True,parent_seal_contains_launch=True,duplicate_does_not_spawn=True)
 finally:f.doCleanups()
case('durable_original_issuance_return_binding_parent_seal_and_no_respawn',flow)
def persistence_error():
 f=fixtures.ContextTests('test_exact_bound_context_and_reserved_three_looks');f.setUp()
 try:
  with patch.object(s,'record_launch',side_effect=OSError('launch persistence PRIMARY')),patch.object(s,'run_process',side_effect=AssertionError('spawn forbidden')):
   try:s.invoke_worker(f.directory,f.parent,f.slot,f.context,Mock(),issued_context_sha256=f.issued)
   except OSError as e:assert str(e)=='launch persistence PRIMARY'
   else:raise AssertionError('write error lost')
  return dict(no_spawn=True,no_fit=True)
 finally:f.doCleanups()
case('launch_write_error_stops_before_worker',persistence_error)
def copied():
 f=fixtures.ContextTests('test_exact_bound_context_and_reserved_three_looks');f.setUp()
 try:
  log=f.directory/'logs/arm-0.log';log.parent.mkdir();context=s.read(f.context);expected=s.expected_worker(f.parent,f.slot,context,f.context);argv=['python','original']
  ref=s.record_launch(log,f.parent,f.slot,f.context,f.issued,expected,argv);original=s.local(ref['path']).read_bytes();f.slot['population']=26000;argv[1]='changed';assert s.local(ref['path']).read_bytes()==original and s.read(s.local(ref['path']))['slot']['population']==6000
  return dict(original_slot_and_argv_retained=True)
 finally:f.doCleanups()
case('durable_payload_retains_original_inputs',copied)
assert hashes()==before;out=dict(before=before,after=hashes(),cases=results,wall_seconds=time.monotonic()-START,self_cpu_seconds=time.process_time()-CPU,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,native_fits=0,scope='tiny JSON/mock worker only; no data/Pool/model/predict/actual subprocess');Path('tlab019-launch-independent-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));assert all(x['status']=='PASS' for x in results)

```
