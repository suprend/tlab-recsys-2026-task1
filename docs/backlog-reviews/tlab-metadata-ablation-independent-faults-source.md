# Independent synthetic model-data/ablation audit archive

Historical exact-version audit, with only machine paths made portable. Extract dependent archived helpers into the system temporary directory before use. Initial model-data overflow assertion mismatch and initial terminal-decision faults remain evidence for their original versions. Archiving claims no new execution or actual fitting.

```python
import sys,json,time,resource,hashlib,tempfile,contextlib,io
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path.cwd().resolve()))
from scripts import metadata_ablation as a
from scripts import metadata_price_collection as c
from scripts import train_baselines as b
from scripts import model_data as d
import tests.test_metadata_ablation as fixture
import numpy as np
START=time.monotonic();CPU=time.process_time();results=[]
ROOT=Path(str(Path.cwd().resolve()));FILES=['scripts/metadata_ablation.py','tests/test_metadata_ablation.py','docs/experiments/metadata-ablation.md']
def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
before=hashes()
def run(name,operation):
 try:results.append(dict(case=name,status='PASS',detail=operation()))
 except Exception as e:results.append(dict(case=name,status='FAIL',error=repr(e)))
def rejects(op,typ=ValueError):
 try:op()
 except typ as e:return str(e)
 raise AssertionError('mutant accepted')
@contextlib.contextmanager
def controls():
 f=fixture.ControlScopeTests('test_exact_control_scope_passes_but_missing_input_output_or_proof_rejected');f.setUp()
 try:yield f
 finally:f.doCleanups()
def omit_scope():
 with controls() as f:
  a.verify_control(f.path,f.root/'config',f.root/'train',f.root/'selection')
  for name in ['source',a.PROOFS[2],str((f.directory/'PairLogit-scores.npz').relative_to(f.root))]:
   old=deepcopy(f.pins);f.pins.pop(name);f.reseal();rejects(lambda:a.verify_control(f.path,f.root/'config',f.root/'train',f.root/'selection'));f.pins=old;f.reseal()
  return 'fresh-resealed source/proof/PairLogit output omissions rejected'
run('control_rederive_scope_fresh_omissions',omit_scope)
def malformed_approval(field,value):
 with controls() as f:
  body=b._read_json(f.path);body[field]=value;b._atomic_json(f.path,body)
  return rejects(f.verify)
for field,value in [('version',True),('version',1.0),('approved',1)]:run('control_strict_'+field+'_'+str(value),lambda field=field,value=value:malformed_approval(field,value))
def control_executiontype():
 with controls() as f:
  body=b._read_json(f.execution);body['version']=True;b._atomic_json(f.execution,body)
  man=b._read_json(f.directory/'run.json');man['fit_approval']['sha256']=b.sha256_file(f.execution);b._atomic_json(f.directory/'run.json',man)
  claim=b._read_json(f.claim);claim['fit_approval']=man['fit_approval'];b._atomic_json(f.claim,claim)
  for p in [f.execution,f.directory/'run.json',f.claim]:f.pins[str(p.relative_to(f.root))]=b.sha256_file(p)
  f.reseal();return rejects(f.verify)
run('fresh_resealed_execution_boolversion',control_executiontype)
def runtime(*,fault=None):
 f=fixture.ClaimAndRuntimeTests('test_synthetic_runtime_exact_score_keys_metrics_and_no_refit_control');f.setUp()
 try:
  # Independently force a legitimate positive metric outcome in this synthetic
  # transformation fixture. No actual accepted control/model/source is loaded.
  for dataset in [f.train,f.selection]:
   dataset.queries=[(qid,user,anchor,frozenset({30}) if qid=='missed' else frozenset() if qid=='emptyC' else targets) for qid,user,anchor,targets in dataset.queries]
   dataset.y=np.array([int(item in dataset.queries[g][3]) for g,item in zip(dataset.group,dataset.items)],dtype=np.int8)
  f.inputs['control']['control']['metrics']=a.asdict(a.evaluate(b.rankings(f.selection,f.scores),20))
  f.manifest['identity']['numeric_features']=f.train.feature_names
  # Full planning is mocked: this harness audits run ordering/finalization,
  # not source acceptance. Real FeaturesData is permitted; Pool/fit mocked.
  legacytrain=deepcopy(f.train);legacyselection=deepcopy(f.selection)
  legacytrain.categorical=None;legacyselection.categorical=None
  model=Mock();model.feature_names_=f.train.feature_names+f.train.categorical_names;model.predict.return_value=f.scores
  model.save_model.side_effect=lambda p,*args,**kw:Path(p).write_text('synthetic')
  fits=[];matrix_calls=[];real_write=c._atomic_json
  def prepare(collection,**kw):
   assert (f.root/a.CLAIM).exists(),'matrix before global claim'
   matrix_calls.append(dict(mixed='metadata_paths' in kw,role=collection['phase']))
   if fault=='matrix_integrity':raise ValueError('PRIMARY matrix integrity')
   if fault=='matrix_memory':raise MemoryError('PRIMARY matrix memory')
   result=deepcopy(f.train if collection['phase']=='train' else f.selection)
   if 'metadata_paths' not in kw:result.categorical=None
   if fault=='base_difference':result.x=result.x.copy();result.x[0,0]+=1
   return result
  def fit(train,config,audit):fits.append(1);audit.report['fit_attempt_count']+=1;return model,dict(synthetic=True)
  def validate(model,params,path):Path(path).write_text('{}');return {}
  def writing(path,body):
   if fault=='terminal_resource' and Path(path).name=='run.json':raise MemoryError('TERMINAL resource during manifest')
   if fault=='terminal_write' and Path(path).name=='report.json' and body.get('status')=='complete_produced_unreviewed':raise OSError('TERMINAL final receipt')
   return real_write(path,body)
  if fault=='score_keys':np.savez_compressed(f.score_path,group=f.selection.group,product_id=f.selection.items+1,raw_score=f.scores)
  if fault=='score_metrics':f.inputs['control']['control']['metrics']['conditional_macro_query']['recall']=0.
  approval=b._read_json(f.approval)
  if fault=='bad_approval':approval['approved']=1;b._atomic_json(f.approval,approval)
  err=None;returned=None
  with patch.object(a,'prepare_plan',return_value=(deepcopy(f.manifest),deepcopy(f.inputs))),patch.object(b,'prepare_dataset',side_effect=[legacytrain,legacyselection]),patch.object(d,'prepare_model_data',side_effect=prepare),patch.object(a,'fit_once',side_effect=fit),patch.object(a,'validate_model',side_effect=validate),patch('catboost.Pool'),patch.object(c,'_atomic_json',side_effect=writing),contextlib.redirect_stdout(io.StringIO()):
   try:returned=a.run(f.source,f.source,f.source,f.source,f.source,execution_approval=f.approval)
   except BaseException as e:err=e
  reports=list((f.root/'artifacts/metadata-ablation').glob('*/report.json'));report=b._read_json(reports[0]);markers=list((f.root/'artifacts/metadata-ablation').glob('*/report.failed.json'))
  if markers:report=b._read_json(markers[0])
  details=dict(error=repr(err),status=report['status'],decision=report.get('decision'),fit_calls=len(fits),matrix_calls=len(matrix_calls),claim_exists=(f.root/a.CLAIM).exists(),known_failed_marker=bool(markers))
  if fault is None:assert err is None and report['decision']['retain_metadata_block'] and len(fits)==1
  elif fault in {'matrix_integrity','base_difference','score_keys','score_metrics'}:assert err is not None and not fits and 'stop' in report['decision']['feature_choice']
  elif fault=='matrix_memory':assert isinstance(err,MemoryError) and report['decision']['feature_choice']=='base41' and not fits
  elif fault=='bad_approval':assert err is not None and not fits and not matrix_calls and not details['claim_exists']
  elif fault in {'terminal_resource','terminal_write'}:
   assert err is not None and report['status']=='failed' and len(fits)==1
   details['contradictory_retention_on_failed_run']=report['decision'].get('retain_metadata_block') is True
  return details
 finally:f.doCleanups()
for fault in [None,'matrix_integrity','matrix_memory','base_difference','score_keys','score_metrics','bad_approval','terminal_resource','terminal_write']:run('runtime_'+str(fault),lambda fault=fault:runtime(fault=fault))
assert before==hashes()
out=dict(before=before,after=hashes(),cases=results,wall_seconds=time.monotonic()-START,cpu_seconds=time.process_time()-CPU,maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,scope='synthetic/mocked only; zero real matrices/Pool/native fit/source/approval')
(Path(__import__('tempfile').gettempdir())/'tlab-metadata-ablation-independent-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
if any(r['status']=='FAIL' for r in results):sys.exit(1)

```
