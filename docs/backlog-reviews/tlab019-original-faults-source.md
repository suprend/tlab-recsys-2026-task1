# Historical019 audit source: original-faults

Aggregate/synthetic evidence archive. Paths below are normalized for privacy; this preserves the historical observer, not a new execution approval. Original freeze references belong to the version reviewed by that pass. No real019 model fit was run by these checks.

```python
import sys,json,time,resource,hashlib,tempfile,os,signal
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch,Mock
sys.path.insert(0,'project root')
from scripts import strong_baseline as s
from scripts import metadata_price_collection as c
import tests.test_strong_baseline as fixtures
START=time.monotonic();CPU=time.process_time();results=[];ROOT=Path('project root')
FILES={'scripts/strong_baseline.py':'c44189641210bb26a22c038cdfcdf61522e5baa74981251f776e971d5f9b423e','tests/test_strong_baseline.py':'3daf102bf61836623bb9b2092f5ab508b1ca036f47b977b96ee6f8fea4b8276e','configs/models/strong-grid.json':'d32daac420f447444d987969cdd49ac1cad427bbd7357114d148c02085aed66e','docs/experiments/strong-baseline.md':'fe3317bbdcd89e52ff70491c8f852e2d3a880e81c18eb3e7293eb245acb1be7f'}
def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES}
before=hashes();assert before==FILES
def case(name,fn):
 try:results.append(dict(case=name,status='PASS',detail=fn()))
 except Exception as e:results.append(dict(case=name,status='FAIL',error=repr(e)))
def context_fault(kind):
 f=fixtures.ContextTests('test_exact_bound_context_and_reserved_three_looks');f.setUp()
 try:
  good=s.verify_worker_context(f.context)[1]
  original_approval=(f.root/'execution.json').read_bytes();original_claim=s.local(s.CLAIM).read_bytes();body=deepcopy(f.slot)
  if kind=='population':body['population']=26000
  if kind=='allowance':body['allocation']['cpu_seconds']=3240;body['allocation']['deadline_monotonic']=time.monotonic()+3500
  if kind=='look_float':body['look_reservations']=[50.,150,300]
  f.reseal_slot(body)
  observed=s.verify_worker_context(f.context)[1]
  assert observed==body and (f.root/'execution.json').read_bytes()==original_approval and s.local(s.CLAIM).read_bytes()==original_claim
  return dict(fresh_resealed_valid_domain_tamper_accepted_before_data=True,original_population=good['population'],observed_population=observed['population'],original_cpu=good['allocation']['cpu_seconds'],observed_cpu=observed['allocation']['cpu_seconds'],look_types=[type(v).__name__ for v in observed['look_reservations']],external_approval_and_claim_unchanged=True)
 finally:f.doCleanups()
for k in ['population','allowance','look_float']:case('issued_context_'+k,lambda k=k:context_fault(k))
def leak():
 with tempfile.TemporaryDirectory(prefix='tlab019-process-fault-',dir='/tmp') as tmp:
  log=Path(tmp)/'worker.log';budget=Mock();budget.limits=s.specification()['limits']
  code="import subprocess,sys,os\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(2)'])\nprint(os.getpid(),p.pid,flush=True)"
  owner=child=None
  try:
   exitcode=s.run_process([sys.executable,'-c',code],log,budget=budget,allocation=dict(deadline_monotonic=time.monotonic()+5),grace=.02,reap=.2)
   owner,child=map(int,log.read_text().split());os.kill(child,0);os.killpg(owner,0)
   assert exitcode==0
   return dict(returncode=exitcode,descendant_still_alive=True,owned_group_still_alive=True,reviewer_cleanup_sent_SIGKILL=True,worker_program_has_no_model_data=True)
  finally:
   if owner is not None:
    try:os.killpg(owner,signal.SIGKILL)
    except ProcessLookupError:pass
   if child is not None:
    try:os.kill(child,signal.SIGKILL)
    except ProcessLookupError:pass
case('direct_child_exits_live_descendant_leaks',leak)
def fake_receipt(kind):
 f=fixtures.ContextTests('test_exact_bound_context_and_reserved_three_looks');f.setUp()
 try:
  context=s.read(f.context);expected=s.expected_worker(f.parent,f.slot,context,f.context);directory=s.local(f.slot['output_root'])/expected['run_id'];directory.mkdir(parents=True)
  consumed=s.local(context['slot_path']).with_suffix('.consumed.json');s.write(consumed,dict(version=1,parent_run_id=f.parent['run_id'],token=f.slot['token'],context_sha256=s.sha(f.context)))
  checkpoints=[dict(config_id=s.digest(s.specification()['grid'][0]),incumbent=False,trees=k,trained_iterations=300,depth=4,l2_leaf_reg=3,population=6000,metrics=dict(conditional_macro_query=dict(ndcg=.7,recall=.6)),artifacts={},model_path='missing.cbm',score_path='missing.npz') for k in [50,150,300]]
  if kind=='scope':
   for cp in checkpoints:cp.update(depth=1,l2_leaf_reg=99,population=26000,trained_iterations=50,incumbent=True,config_id='forged')
  report=dict(run_id=expected['run_id'],parent_run_id=f.parent['run_id'],mode='arm',index=0,population=6000,fit_attempt_count=1,status='complete_produced_unreviewed',outcome='arm_complete',checkpoints=checkpoints,look_reservations=[],process_peak_rss_bytes=1)
  manifest={**expected,'outputs':{}}
  s.write(directory/'run.json',manifest);s.write(directory/'report.json',report)
  with patch.object(s,'run_process',return_value=0):answer=s.invoke_worker(f.directory,f.parent,f.slot,f.context,Mock())
  assert answer['exit_code']==0
  return dict(accepted_complete_worker=True,missing_all_model_score_outputs=True,checkpoint_scope_forged=kind=='scope',look_reservations_empty=True,fit_calls=0)
 finally:f.doCleanups()
for k in ['empty_outputs','scope']:case('worker_receipt_'+k,lambda k=k:fake_receipt(k))
def budget_arithmetic():
 with patch.object(s,'self_cpu',return_value=40.),patch.object(s,'child_cpu',return_value=200.),patch.object(s,'rss',return_value=1),patch.object(s.time,'monotonic',return_value=100.):
  b=s.Budget(s.specification(),started=50);assert b.cpu()==240 and b.allocation('arm')['cpu_seconds']==3000 and b.outer_deadline==3650 and b.producer_deadline==3290
  return dict(total=240,child_allowance=3000,parent_reserve=60,verification_reserve=300,one_outer_deadline=True)
case('CPU_nonoverlapping_remaining_allocation',budget_arithmetic)
def canonical_ties():
 cs=[dict(config_id=k,trees=t,depth=4,incumbent=False,metrics=dict(conditional_macro_query=dict(ndcg=v,recall=.6))) for k,t,v in [('a',50,.5-1.5e-12),('b',150,.5-.75e-12),('c',300,.5)]]
 assert s.choose(cs)['config_id']=='b' and s.choose(list(reversed(cs)))['config_id']=='b'
 return 'global maximum tie set preserved'
case('nontransitive_near_tie',canonical_ties)
assert before==hashes()
out=dict(before=before,after=hashes(),cases=results,wall_seconds=time.monotonic()-START,self_cpu_seconds=time.process_time()-CPU,child_cpu_cumulative=resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime+resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,scope='synthetic metadata/mocks/one tiny OS process group only; no actual data/Pool/model/native fits')
Path('tlab019-independent-results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if any(v['status']=='FAIL' for v in results):sys.exit(1)

```
