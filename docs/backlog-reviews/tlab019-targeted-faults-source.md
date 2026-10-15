# Historical019 audit source: targeted-faults

Aggregate/synthetic evidence archive. Paths below are normalized for privacy; this preserves the historical observer, not a new execution approval. Original freeze references belong to the version reviewed by that pass. No real019 model fit was run by these checks.

```python
import sys,json,time,resource,hashlib,tempfile,os,signal,subprocess
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch,Mock
sys.path.insert(0,'project root')
from scripts import strong_baseline as s
from scripts import metadata_price_collection as c
import tests.test_strong_baseline as fixtures
START=time.monotonic();CPU=time.process_time();BASECHILD=s.child_cpu();results=[];ROOT=Path('project root')
FILES={'scripts/strong_baseline.py':'53808ef3b98e0175d628b93ffe3cd0c6997940a132732d03490be78964daff14','tests/test_strong_baseline.py':'1921dcbff87fb2f43e2f3e2662630c77bd4785e86f7e8d95e2ff9d2baf1a3eb7','configs/models/strong-grid.json':'d32daac420f447444d987969cdd49ac1cad427bbd7357114d148c02085aed66e','docs/experiments/strong-baseline.md':'aae39f6fcb6a705bb575e9033b7caf179b9dab3ac06f7f0038632ac7ce073560'}
def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES}
before=hashes();assert before==FILES
original_paths=['tlab019-code-review.md','tlab019-independent-faults.py','tlab019-independent-results.json','tlab-verify019-outputs.py']
original={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in original_paths}
def case(name,fn):
 try:results.append(dict(case=name,status='PASS',detail=fn()))
 except BaseException as e:results.append(dict(case=name,status='FAIL',error=repr(e)))
def rejected(fn):
 try:fn()
 except (ValueError,FileNotFoundError,TypeError) as e:return type(e).__name__+': '+str(e)
 raise AssertionError('Mutant accepted')
def ctx(kind):
 f=fixtures.ContextTests('test_exact_bound_context_and_reserved_three_looks');f.setUp()
 try:
  issued=f.issued;good=s.verify_worker_context(f.context,issued_context_sha256=issued)[1];body=deepcopy(f.slot)
  if kind=='population':body['population']=26000
  elif kind=='allowance':body['allocation']['cpu_seconds']=3240;body['allocation']['deadline_monotonic']=time.monotonic()+3500
  else:body['look_reservations']=[50.,150,300]
  f.reseal_slot(body)
  detail=rejected(lambda:s.verify_worker_context(f.context,issued_context_sha256=issued if kind!='look_float' else f.issued))
  calls=[]
  if kind!='look_float':
   with patch.object(s,'run_process',side_effect=lambda *a,**kw:calls.append(a)):
    rejected(lambda:s.invoke_worker(f.directory,f.parent,f.slot,f.context,Mock(),issued_context_sha256=issued))
   assert not calls
  return dict(rejected_before_spawn=True,reason=detail)
 finally:f.doCleanups()
for k in ['population','allowance','look_float']:case('original_issued_context_'+k,lambda k=k:ctx(k))
def orphan():
 with tempfile.TemporaryDirectory(prefix='tlab019-recheck-process-',dir='/tmp') as tmp:
  log=Path(tmp)/'worker.log';budget=Mock();budget.limits=s.specification()['limits'];native=s.subprocess.Popen;spawned=[];owner=child=None
  def create(*a,**kw):p=native(*a,**kw);spawned.append(p);return p
  code="import subprocess,sys,os\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(2)'])\nprint(os.getpid(),p.pid,flush=True)"
  caught=None
  try:
   with patch.object(s.subprocess,'Popen',side_effect=create):
    try:s.run_process([sys.executable,'-c',code],log,budget=budget,allocation=dict(deadline_monotonic=time.monotonic()+5),grace=.03,reap=.3)
    except RuntimeError as e:caught=e
   owner,child=map(int,log.read_text().split());assert caught and 'surviving owned-group' in str(caught) and spawned[0].returncode==0
   try:os.killpg(owner,0);residual=True
   except ProcessLookupError:residual=False
   if residual:assert Path(str(log)+'.cleanup-failed.json').exists()
   return dict(rejected=True,direct_child_reaped=True,residual_requires_unknown_usage_marker=residual,primary_preserved=True)
  finally:
   for pid,group in [(owner,True),(child,False)]:
    if pid is not None:
     try:(os.killpg if group else os.kill)(pid,signal.SIGKILL)
     except ProcessLookupError:pass
   for p in spawned:
    try:p.wait(timeout=1)
    except subprocess.TimeoutExpired:raise AssertionError('Reviewer child unreaped')
case('original_normal_leader_live_descendant',orphan)
def direct_cleanup():
 with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
  budget=Mock();budget.limits=s.specification()['limits'];primary=ValueError('PRIMARY integrity');budget.guard.side_effect=primary;created=[];native=s.subprocess.Popen
  def spawn(*a,**kw):p=native(*a,**kw);created.append(p);return p
  with patch.object(s.subprocess,'Popen',side_effect=spawn):
   try:s.run_process([sys.executable,'-c','import time;time.sleep(2)'],Path(tmp)/'log',budget=budget,allocation=dict(deadline_monotonic=time.monotonic()+5),grace=.03,reap=.3)
   except ValueError as e:assert e is primary
   else:raise AssertionError('Error lost')
  assert created and created[0].returncode is not None
  try:os.kill(created[0].pid,0)
  except ProcessLookupError:return dict(first_error_preserved=True,direct_child_reaped=True)
  raise AssertionError('Child survives')
case('parent_error_direct_child_reaped_primary_preserved',direct_cleanup)
# Independent receipt construction: no production metric/model builders or fitted model.
def receipt(mutant):
 with tempfile.TemporaryDirectory(prefix='tlab019-rereview-receipt-',dir='/tmp') as tmp,patch.object(s,'ROOT',Path(tmp)),patch.object(c,'ROOT',Path(tmp)):
  root=Path(tmp);wd=root/'receipt';wd.mkdir();names=['x'+str(i) for i in range(41)]
  arm=dict(depth=4,l2_leaf_reg=3);params=dict(loss_function='Logloss',iterations=300,depth=4,l2_leaf_reg=3,learning_rate=.05,random_seed=2026,thread_count=2,task_type='CPU',boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False,border_count=254,nan_mode='Min',rsm=1)
  parent=dict(identity=dict(spec=dict(grid=[arm]),feature_names=names,incumbent=dict(actual_model_parameters=params)))
  slot=dict(mode='arm',index=0,population=6000)
  files=['full300.cbm','full300.json',*[f'prefix{k}{suffix}' for k in [50,150,300] for suffix in ['.cbm','-scores.npz']]]
  for n in files:(wd/n).write_text('nonempty synthetic bytes')
  s.write(wd/'full300.json',dict(oblivious_trees=[dict(splits=[dict(split_type='FloatFeature')]) for _ in range(300)]))
  outputs={s.relative(wd/n):s.sha(wd/n) for n in files}
  metrics=dict(k=20,query_count=4000,mature_query_count=4000,censored_query_count=0,nonempty_query_count=73,mature_user_count=3995,positive_user_count=73,nonempty_fraction=73/4000)
  for e in ['conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero']:metrics[e]={n:.2 for n in ['recall','ndcg','average_precision','reciprocal_rank']}
  cps=[]
  for k in [50,150,300]:
   mp=s.relative(wd/f'prefix{k}.cbm');sp=s.relative(wd/f'prefix{k}-scores.npz');cps.append(dict(config_id=s.digest(arm),incumbent=False,trees=k,trained_iterations=300,depth=4,l2_leaf_reg=3,population=6000,metrics=deepcopy(metrics),artifacts={p:outputs[p] for p in [mp,sp]},model_path=mp,score_path=sp))
  manifest=dict(run_id='synthetic',identity={},outputs=deepcopy(outputs));report=dict(status='complete_produced_unreviewed',outcome='arm_complete',scope='strong_arm_worker',feature_names=deepcopy(names),training=dict(queries=6000),fit_attempt_count=1,actual_model_parameters=params,artifacts=deepcopy(outputs),checkpoints=cps,look_reservations=[dict(trees=k,status='seen_complete',metrics=deepcopy(metrics)) for k in [50,150,300]])
  if mutant=='empty_outputs':manifest['outputs']={};report['artifacts']={}
  elif mutant=='forged_scope':
   for cp in cps:cp.update(depth=1,l2_leaf_reg=99,population=26000,trained_iterations=50,incumbent=True,config_id='forged')
  elif mutant=='missing_looks':report['look_reservations']=[]
  elif mutant=='extra_output':
   p=wd/'extra.cbm';p.write_text('extra');manifest['outputs'][s.relative(p)]=s.sha(p);report['artifacts']=deepcopy(manifest['outputs'])
  elif mutant=='missing_model':(wd/'prefix150.cbm').unlink()
  elif mutant=='empty_model':(wd/'prefix150.cbm').write_text('');manifest['outputs'][s.relative(wd/'prefix150.cbm')]=s.sha(wd/'prefix150.cbm');report['artifacts']=deepcopy(manifest['outputs'])
  elif mutant=='float_checkpoint':cps[0]['trees']=50.
  elif mutant=='float_look':report['look_reservations'][0]['trees']=50.
  elif mutant=='native_CTR':
   s.write(wd/'full300.json',dict(oblivious_trees=[dict(splits=[dict(split_type='OnlineCtr')])]*300));manifest['outputs'][s.relative(wd/'full300.json')]=s.sha(wd/'full300.json');report['artifacts']=deepcopy(manifest['outputs'])
  elif mutant=='wrong_name':report['feature_names'][0]='changed'
  elif mutant=='bad_parameter':report['actual_model_parameters']=dict(params,learning_rate=.1)
  elif mutant=='bad_metric':
   cps[0]['metrics']['conditional_macro_query']['ndcg']=2.;report['look_reservations'][0]['metrics']=deepcopy(cps[0]['metrics'])
  elif mutant=='look_unseen':report['look_reservations'][1]['status']='reserved_consumed'
  verify=lambda:s.validate_complete_worker(parent,slot,{},wd,manifest,report,Mock())
  if mutant=='healthy':verify();return dict(accepted_mechanical_only=True,required_outputs=8,features=41,native_fits=0)
  return dict(rejected=True,reason=rejected(verify))
for k in ['healthy','empty_outputs','forged_scope','missing_looks','extra_output','missing_model','empty_model','float_checkpoint','float_look','native_CTR','wrong_name','bad_parameter','bad_metric','look_unseen']:case('receipt_'+k,lambda k=k:receipt(k))
def launch_boundary(kind):
 f=fixtures.ContextTests('test_exact_bound_context_and_reserved_three_looks');f.setUp()
 try:
  calls=[];original=f.issued
  if kind=='pre_memory_scope':
   body=deepcopy(f.slot);body['population']=26000;f.reseal_slot(body)
   with patch.object(s,'run_process',side_effect=lambda *a,**kw:calls.append(a)):
    why=rejected(lambda:s.invoke_worker(f.directory,f.parent,f.slot,f.context,Mock(),issued_context_sha256=f.issued))
   assert not calls
  else:
   def change(*a,**kw):
    calls.append(a);context=s.read(f.context);context['slot_sha256']='0'*64;s.write(f.context,context);return 0
   with patch.object(s,'run_process',side_effect=change):why=rejected(lambda:s.invoke_worker(f.directory,f.parent,f.slot,f.context,Mock(),issued_context_sha256=original))
   assert len(calls)==1 and '--issued-context-sha256' in calls[0][0]
  return dict(rejected=True,reason=why,native_fits=0)
 finally:f.doCleanups()
for k in ['pre_memory_scope','post_spawn_context']:case('issuer_boundary_'+k,lambda k=k:launch_boundary(k))
assert before==hashes();after_original={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in original_paths};assert original==after_original
out=dict(before=before,after=hashes(),preserved_original_evidence=original,cases=results,wall_seconds=time.monotonic()-START,self_cpu_seconds=time.process_time()-CPU,reaped_children_cpu_seconds=s.child_cpu()-BASECHILD,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,scope='Synthetic JSON/nonempty placeholder artifacts and tiny OS processes only; no source/parquet/Pool/nativefit/model load/predict')
Path('tlab019-independent-rereview-results-v2.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));assert all(v['status']=='PASS' for v in results)

```
