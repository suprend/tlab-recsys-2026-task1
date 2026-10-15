"""Synthetic adapter plumbing only; three raw events, no native models/authority."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib,json
from pathlib import Path
import tempfile,time,unittest
from unittest.mock import patch
import duckdb
from scripts import heldout_execution as x, heldout_contract as h, heldout_source as producer
from tests.test_heldout_source import definitions
from tests import test_heldout_predictions as native_fixture

from tests.oracles import heldout_source_worker as m
BIG=2**60

class FakeBudget:
 def __init__(self):self.connections=[];self.checks=0
 def guard(self):self.checks+=1
 def watch(self,con):self.connections.append(con)

class FakeRole:
 def __init__(self,fixture,module,role):
  self.f=fixture;self.root=fixture.root;self.module=module;self.role=role;self.budget=FakeBudget();self._pins=deepcopy(fixture.pins);self.retain_count=0;self.failed=[];self.finished=False
  inputs={k:fixture.refs[k] for k in x.INPUT_KEYS[role]};base=fixture.directory+'/'+role
  self._context=dict(run_id=fixture.run,role=role,inputs=inputs,authorities={k:fixture.refs[k] for k in ['initial_execution']+(['source_acceptance'] if role!='source_oracle' else [])+(['prediction_acceptance','target_execution'] if role=='metric_oracle' else [])},expected_outputs=[base+'/evidence.json'])
  self.reference=fixture.write(base+'/context.json',{'synthetic_context':role});self.consumed=fixture.write(base+'/execution.consumed.json',{'synthetic_consumption':role})
 @property
 def context(self):return deepcopy(self._context)
 @property
 def pins(self):return deepcopy(self._pins)
 def retain_pins(self,mapping):
  copied=deepcopy(mapping)
  for n,d in copied.items():
   if n in self._pins and self._pins[n]!=d:raise ValueError('pin conflict')
  self._pins.update(copied);self.retain_count+=1
 def verify_pins(self,mapping=None):
  self.budget.guard()
  for n,d in (self._pins if mapping is None else mapping).items():
   if hashlib.sha256((self.root/n).read_bytes()).hexdigest()!=d:raise ValueError('Original bytes changed')
 def input_json(self,name):
  ref=self._context['inputs'][name];raw=(self.root/ref['path']).read_bytes()
  if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Input bytes changed')
  return json.loads(raw)
 def environment(self):return {'synthetic_versions':True}
 def markers(self):
  if (self.root/self.reference['path']).parent.joinpath('evidence.failed.json').exists():raise ValueError('Known failed')
 def fail(self,error):self.failed.append(type(error).__name__)
 def finish(self,outputs,evidence,**kwargs):
  self.verify_pins();self.markers();self.finished=True
  for con in self.budget.connections:
   try:con.execute('SELECT 1')
   except duckdb.ConnectionException:continue
   raise AssertionError('connection still open at finish')
  return dict(status='synthetic_complete',outputs=outputs,evidence=evidence,**kwargs)

class Fixture:
 def __init__(self,root,choice_name='B'):
  self.root=root;self.directory='artifacts/heldout-study/synthetic';self.refs={};self.pins={}
  self.pool,self.lock,self.choice=definitions(choice_name);self.lock['sealed_at']=(datetime.now(timezone.utc)-timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ');f=native_fixture.FrozenPredictionTests();f.reset(choice_name)
  for spec in self.lock['models'].values():spec['effective_parameters'].update(f.lock['models']['B']['effective_parameters'])
  self.choice['models']=deepcopy(self.lock['models'])
  for key,body in [('lock',self.lock),('choice',self.choice),('pool',self.pool),('registry',{'synthetic':True})]:self.refs[key]=self.write('fixture/'+key+'.json',body)
  raw=[(datetime(2019,10,24,23),'view',1,BIG,9),(datetime(2019,10,24,22),'purchase',2,2,8),(datetime(2019,10,25,1),'purchase',BIG,BIG,9)]
  p=root/'data/processed/october.duckdb';p.parent.mkdir(parents=True);con=duckdb.connect(str(p));con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)');con.executemany('INSERT INTO events VALUES (?,?,?,?,?)',raw);con.close();self.refs['source']=self.reference('data/processed/october.duckdb')
  identity=dict(source_inputs={'source':self.refs['source']});self.run=h.digest(identity);self.write(self.directory+'/proposal.json',dict(run_id=self.run,identity=identity))
  self.refs['initial_execution']=self.write('fixture/initial.json',dict(synthetic=True))
  con=duckdb.connect(':memory:');con.execute('SET threads=2');con.execute("SET memory_limit='128MB'");con.execute("SET max_temp_directory_size='0B'");con.execute('CREATE TABLE heldout_raw_events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)');con.executemany('INSERT INTO heldout_raw_events VALUES (?,?,?,?,?)',raw)
  days=[];outputs={}
  try:
   for anchor in h.DAYS:
    result=producer.build_day(con,anchor,self.pool,self.lock,authenticated_choice=self.choice);day=dict(anchor=anchor,extra_features=None,query_count=result['query_count'],candidate_count=result['candidate_count'],mature_query_count=result['mature_query_count'])
    tables=[('queries','pilot_queries','queries'),('candidates','pilot_candidates','candidates'),('base_features','heldout_base_features','base-features')]
    if choice_name!='B':tables.append(('extra_features','heldout_extra_features','extra-features'))
    for key,table,stem in tables:
     name=self.directory+'/source/day-'+anchor[8:10]+'/'+stem+'.parquet';path=root/name;path.parent.mkdir(parents=True,exist_ok=True);con.execute("COPY "+table+" TO '"+str(path)+"' (FORMAT PARQUET)");day[key]=self.reference(name);outputs[name]=day[key]['sha256']
    days.append(day)
  finally:con.close()
  body=dict(version=1,scope='unaccepted_reserved_source',run_id=self.run,decision_lock=self.refs['lock'],choice=self.refs['choice'],source=self.refs['source'],days=days,outputs=outputs,labels_loaded=False,fit_attempt_count=0,native_prediction_count=0,environment={'synthetic_versions':True})
  self.refs['source_manifest']=self.write(self.directory+'/source/source-manifest.json',body);self.source=body
  allout=dict(outputs);allout[self.refs['source_manifest']['path']]=self.refs['source_manifest']['sha256']
  self.refs['source_receipt']=self.write(self.directory+'/source/receipt.json',dict(status='role_complete_unaccepted',scope='reserved_reporting_source',role='source',run_id=self.run,inputs={k:self.refs[k] for k in ['lock','choice','source','pool','registry']},outputs=allout,labels_loaded=False,fit_attempt_count=0,native_prediction_count=0))
  self.refs['source_acceptance']=self.write('fixture/source-acceptance.json',dict(approved=True,scope='reviewed_reserved_source',run_id=self.run,days=days,fingerprints=outputs,sealed_at=(h.utc(self.lock['sealed_at'])+timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')))
 def reference(self,name):
  ref=dict(path=name,sha256=hashlib.sha256((self.root/name).read_bytes()).hexdigest());self.pins[name]=ref['sha256'];return ref
 def write(self,name,body):
  path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(x.canonical(body)+'\n');return self.reference(name)

class SourceWorker(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.patch=patch.object(m,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop);self.f=Fixture(self.root);self.r=FakeRole(self.f,m,'source_oracle')
 def test_actual_tiny_source_core_through_closed_readonly_adapter(self):
  result=m.perform(self.r);self.assertTrue(self.r.finished);self.assertEqual(result['native_prediction_count'],0);self.assertFalse(result['labels_loaded']);e=json.loads((self.root/result['evidence']['path']).read_text())
  self.assertEqual(set(e),{'version','scope','run_id','context','execution_consumed','decision_lock','choice','inputs','core','environment'});self.assertFalse(e['core']['baseline_formula_values_complete']);self.assertEqual(e['core']['chosen_columns'],0)
  self.assertGreater(self.r.retain_count,0)
 def test_changed_nested_source_bytes_reject_and_never_finish(self):
  ref=self.f.source['days'][0]['queries'];(self.root/ref['path']).write_bytes(b'corrupt')
  with self.assertRaises(ValueError):m.perform(self.r)
  self.assertFalse(self.r.finished)
 def test_joint_domain_omission_resealed_synthetic_output_reject(self):
  # Tiny producer tables may be resealed, but independent raw Q still rejects.
  ref=self.f.source['days'][0]['queries'];con=duckdb.connect(':memory:');con.execute('CREATE TABLE q AS SELECT * FROM read_parquet(?)',[str(self.root/ref['path'])]);con.execute('DELETE FROM q');con.execute("COPY q TO '"+str(self.root/ref['path'])+"' (FORMAT PARQUET,OVERWRITE_OR_IGNORE)");con.close()
  self.f.source['days'][0]['queries']=self.f.reference(ref['path']);self.f.source['outputs'][ref['path']]=self.f.source['days'][0]['queries']['sha256'];self.f.refs['source_manifest']=self.f.write(self.f.refs['source_manifest']['path'],self.f.source)
  receipt=json.loads((self.root/self.f.refs['source_receipt']['path']).read_text());receipt['outputs'][ref['path']]=self.f.source['outputs'][ref['path']];receipt['outputs'][self.f.refs['source_manifest']['path']]=self.f.refs['source_manifest']['sha256'];self.f.refs['source_receipt']=self.f.write(self.f.refs['source_receipt']['path'],receipt);self.r=FakeRole(self.f,m,'source_oracle')
  with self.assertRaisesRegex(ValueError,'Exact source relation'):m.perform(self.r)
 def test_primary_body_exception_survives_cleanup_exception(self):
  class Bad:
   def close(self):raise OSError('secondary close')
  error=ValueError('primary');m.close_resources(self.r,Bad(),None,error);self.assertIn('OSError',str(error.__notes__));self.assertEqual(str(error),'primary')
 def test_close_error_prevents_evidence_persistence(self):
  original=m.close_resources
  def fail_after_real_cleanup(*args,**kwargs):
   original(*args,**kwargs)
   raise OSError('synthetic failure after real cleanup')
  with patch.object(m,'close_resources',side_effect=fail_after_real_cleanup):
   with self.assertRaises(OSError):m.perform(self.r)
  self.assertFalse(self.r.finished);self.assertFalse((self.root/self.r.context['expected_outputs'][0]).exists())
  self.assertFalse(list((self.root/self.r.reference['path']).parent.glob('oracle-scratch-*')))
  for con in self.r.budget.connections:
   with self.assertRaises(duckdb.ConnectionException):con.execute('SELECT 1')
 def test_bootstrap_wrong_issuer_before_project_import_or_context_use(self):
  path=self.root/'bad.json';path.write_text('{}')
  with patch.object(m,'_modules',side_effect=AssertionError('early import')):
   with self.assertRaisesRegex(ValueError,'Original context'):m.bootstrap(['--context',str(path),'--issued-context-sha256','0'*64])
 def test_exclusive_evidence_cannot_overwrite_and_knownfailed_blocks(self):
  m.perform(self.r)
  with self.assertRaises(FileExistsError):m.perform(self.r)
 def test_systemexit_after_admission_is_failed_even_with_zero_code(self):
  class Helper:
   @staticmethod
   def begin_role(*args):return self.r
  with patch.object(m,'bootstrap',return_value=(self.root/'context.json','a'*64)),patch.object(m,'_modules',return_value=(Helper,x,h)),patch.object(m,'perform',side_effect=SystemExit(0)),patch('sys.stderr'):
   self.assertEqual(m.main([]),1)
  self.assertEqual(self.r.failed,['SystemExit'])
 def test_main_primary_failure_calls_fail_and_never_success(self):
  class Helper:
   @staticmethod
   def begin_role(*args):return self.r
  with patch.object(m,'bootstrap',return_value=(self.root/'context.json','a'*64)),patch.object(m,'_modules',return_value=(Helper,x,h)),patch.object(m,'perform',side_effect=ValueError('private value must not print')),patch('sys.stderr'):
   self.assertEqual(m.main([]),1)
  self.assertEqual(self.r.failed,['ValueError'])


class Bootstrap(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();p=patch.object(m,'ROOT',self.root);p.start();self.addCleanup(p.stop)
  required={m.ENTRY,m.CORE,'scripts/heldout_worker_context.py','scripts/heldout_execution.py','scripts/heldout_contract.py'};code={}
  for name in required:
   path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'# synthetic pinned code only');code[name]=hashlib.sha256(path.read_bytes()).hexdigest()
  request=self.root/'request.json';request.write_text(json.dumps({'code_fingerprints':code}));ref=dict(path='request.json',sha256=hashlib.sha256(request.read_bytes()).hexdigest());pins=dict(code);pins[ref['path']]=ref['sha256']
  self.path=self.root/'context.json';self.path.write_text(json.dumps(dict(role=m.ROLE,entry=dict(path=m.ENTRY,sha256=code[m.ENTRY]),plan=dict(fingerprints=pins),request=ref)));self.sha=hashlib.sha256(self.path.read_bytes()).hexdigest();self.args=['--context',str(self.path),'--issued-context-sha256',self.sha]
 def test_cheap_allcode_boundary_before_any_project_import(self):
  with patch.object(m,'_modules',side_effect=AssertionError('no imports yet')):self.assertEqual(m.bootstrap(self.args),(self.path,self.sha))
  (self.root/m.CORE).write_text('changed')
  with patch.object(m,'_modules',side_effect=AssertionError('no imports yet')),self.assertRaisesRegex(ValueError,'Cheap original code'):m.bootstrap(self.args)
 def test_original_context_parse_uses_verified_bytes_only(self):
  original=m.bounded_bytes;seen=[]
  def read(path,maximum):
   raw=original(path,maximum)
   if Path(path)==self.path:seen.append(path);self.path.write_text('{}')
   return raw
  with patch.object(m,'bounded_bytes',side_effect=read):self.assertEqual(m.bootstrap(self.args),(self.path,self.sha))
  self.assertEqual(len(seen),1) # helper begin_role will independently reject changed bytes.
 def test_duplicate_nonfinite_overflow_and_missing_issuer_rejected(self):
  for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}']:
   with self.assertRaises(ValueError):m.strict_json(raw)
  with patch('sys.stderr'),self.assertRaises(SystemExit):m.bootstrap(['--context',str(self.path)])
 def test_unpinned_initializer_and_escaped_context_rejected(self):
  (self.root/'scripts/__init__.py').write_text('unexpected')
  with self.assertRaisesRegex(ValueError,'initializer'):m.bootstrap(self.args)
  with self.assertRaises(ValueError):m.bootstrap(['--context','/nonlocal-context','--issued-context-sha256','a'*64])

if __name__=='__main__':unittest.main()
