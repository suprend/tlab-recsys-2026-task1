"""Only small synthetic files; no native model or actual accepted input access."""
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import sys
import numpy as np
import duckdb

from tests.oracles import feature_program_model_audit as a
BASE=['f'+str(i) for i in range(39)]+['retrieval_last_event_age_seconds','retrieval_last_event_missing']
DELTA=[dict(name='auto_count',dtype='BIGINT'),dict(name='auto_age',dtype='DOUBLE'),dict(name='auto_age_missing',dtype='BOOLEAN')]

# Synthetic durable-launch fixture, no source/model/native ML calls.
import hashlib
from pathlib import Path

def populate_workers(a,obj,*,resource_failure=False):
 i=dict(model_spec=dict(scoring_prefix=2),slots={cid:dict(candidate_id=cid,bundle_id=cid,columns=['auto_x','auto_y','auto_z'],physical_delta=[dict(name=n,dtype='BIGINT') for n in ['auto_x','auto_y','auto_z']],feature_names=['f']*41+['auto_x','auto_y','auto_z']) for cid in a.SLOTS})
 obj.identity=i;obj.manifest=dict(outputs={});m=obj.manifest['outputs'];D=obj.directory;root=obj.root
 def rel(p):return str(p.relative_to(root))
 def write(p,b):
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(a.canonical(b)+'\n');ref=dict(path=rel(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest());m[ref['path']]=ref['sha256'];return ref
 plan=write(D/'plan.json',{});write(D/'winner.json',{})
 obj.report=dict(run_id='a'*64,started_monotonic=1.,original_absolute_deadline_monotonic=3601.,producer_finished_monotonic=30.,parent_peak_rss_bytes=1024,actual_reaped_children_cpu_seconds=4.,fit_attempt_count=4,sum_metric_looks=4,children=[])
 for index,cid in enumerate(a.SLOTS):
  allocation=dict(cpu_seconds=10,deadline_monotonic=200.,rss_bytes=7*2**30)
  slot=dict(version=1,parent_run_id='a'*64,candidate_id=cid,token=str(index)*32,allocation=allocation,context_path=rel(D/'slots'/(cid+'-context.json')),output_root=rel(D/'workers'/cid),look_reservations=[2])
  sr=write(D/'slots'/(cid+'.json'),slot);cr=write(D/'slots'/(cid+'-context.json'),dict(version=1,parent_plan=plan,slot=sr))
  consumed=write(D/'slots'/(cid+'.consumed.json'),dict(version=1,parent_run_id='a'*64,candidate_id=cid,token=slot['token'],context_sha256=cr['sha256'],allowed_fit_attempts=1,allowed_metric_looks=1))
  wi=dict(version=1,role=a.ROLE+'_worker',parent_plan=plan,slot=sr,issued_context=cr,consumed=consumed,candidate=i['slots'][cid],procedure=i['model_spec']);wid=a.digest(wi);out=D/'workers'/cid/wid;out.mkdir(parents=True)
  metric=dict(conditional_macro_query=dict(ndcg=.5,recall=.6))
  outputs={}
  for name in ('full.cbm','full.json','prefix.cbm','scores.npz'):
   p=out/name;p.write_bytes(b'dummy');outputs[rel(p)]=hashlib.sha256(b'dummy').hexdigest();m[rel(p)]=outputs[rel(p)]
  report=dict(version=1,status='complete_produced_unreviewed',scope=a.ROLE+'_worker',run_id=wid,parent_run_id='a'*64,candidate_id=cid,bundle_id=cid,
   added_columns=i['slots'][cid]['columns'],physical_delta=i['slots'][cid]['physical_delta'],feature_names=i['slots'][cid]['feature_names'],fit_attempt_count=1,
   look_reservations=[dict(prefix=2,status='seen_complete',metrics=metric)],labels_loaded=True,started_monotonic=10.,allocation=allocation,outcome='arm_complete',stages=[],
   actual_entry_cpu_seconds=.5,actual_reaped_children_cpu_seconds=0.,process_peak_rss_bytes=1024,finished_monotonic=11.,receipt_boundary='before_tail',seconds=1.,
   environment={},training={},train_preparation={},train_matrix_proof={},selection_preparation={},selection_matrix_proof={},actual_model_parameters={},metrics=metric,artifacts=outputs,
   model_path=rel(out/'prefix.cbm'),full_model_path=rel(out/'full.cbm'),score_path=rel(out/'scores.npz'))
  candidate=dict(candidate_id=cid,status='verified_success',added_physical_columns=3,metrics=metric,model_path=report['model_path'],score_path=report['score_path'],feature_names=report['feature_names'])
  failed=resource_failure and cid=='R2'
  if failed:
   report.update(status='failed',outcome='resource_failure',error_type='MemoryError',error='preserved resource failure',process_peak_rss_bytes=7*2**30+1)
   write(out/'report.failed.json',report);candidate=dict(candidate_id=cid,status='resource_failed',added_physical_columns=3,metrics=None)
  rr=write(out/'report.json',report);mr=write(out/'run.json',dict(run_id=wid,identity=wi,outputs=outputs))
  launch=dict(version=1,scope=a.ROLE,parent_run_id='a'*64,candidate_id=cid,argv=[a.sys.executable,str(root/'scripts/feature_program_experiment.py'),'--worker','--context',str(root/cr['path']),'--issued-context-sha256',cr['sha256']],cwd=str(root),context=cr,slot=sr,allocation=allocation,log_path=rel(D/'logs'/(cid+'.log')),issued_at_monotonic=9.)
  lr=write(D/'logs'/(cid+'.launch.json'),launch);p=D/'logs'/(cid+'.log');p.write_bytes(b'');m[rel(p)]=hashlib.sha256(b'').hexdigest()
  obj.report['children'].append(dict(slot=sr,context=cr,exit_code=1 if failed else 0,actual_reaped_cpu_seconds=.7,report=rr,manifest=mr,launch=lr,worker_report=report,candidate=candidate))
 return write


# Tiny issuer/producer authority snapshots, no actual accepted files.
import hashlib
from pathlib import Path

def build_binding(a,root):
 root=root.resolve();D=root/'artifacts/feature-program-invocations'/('c'*32);inv=D/'observer';inv.mkdir(parents=True)
 def rel(p):return str(p.relative_to(root))
 def write(p,value):
  p.parent.mkdir(parents=True,exist_ok=True);raw=(a.canonical(value)+'\n').encode();p.write_bytes(raw);return dict(path=rel(p),sha256=hashlib.sha256(raw).hexdigest())
 entry=root/'tests/oracles/feature_program_model_audit.py';entry.parent.mkdir(parents=True);entry.write_bytes(b'synthetic observer snapshot')
 source=dict(path=rel(entry),sha256=hashlib.sha256(entry.read_bytes()).hexdigest());started=a.START-10
 ks={'version','role','limits','fingerprints','source_run_id','source_acceptance','control_acceptance','selector','selector_path','model_spec','model_parameters','native_reference','baseline','feature_names','slots','accepted_base_refs','collection_ids','daily_features','expected_source_schema','paid_source_cpu_seconds','environment','interpretation','heldout_labels_opened','oracle_source','owner_attempt_claim'}
 identity={k:None for k in ks};identity.update(version=1,role=a.ROLE,heldout_labels_opened=False,oracle_source=source,fingerprints={source['path']:source['sha256']},paid_source_cpu_seconds=100.)
 rid=a.digest(identity)
 approval=write(root/'approval.json',dict(version=1,approved=True,scope=a.ROLE,run_id=rid,fingerprints=identity['fingerprints']))
 claim=write(root/a.CLAIM,dict(version=1,scope=a.ROLE,run_id=rid,allowed_fit_attempts=4,allowed_metric_looks=4,allowed_observer_attempts=1,oracle_source=source,no_refill=True,output_directory=rel(D),execution_approval=approval,slot_paths=[rel(D/'slots'/(cid+'.json')) for cid in a.SLOTS]))
 parent=dict(run_id=rid,identity=identity,execution_approval=approval,budget_claim=claim);plan=write(D/'plan.json',parent)
 manifest=write(D/'run.json',dict(parent,outputs={plan['path']:plan['sha256']}))
 report=write(D/'producer-report.json',dict(version=1,scope=a.ROLE,run_id=rid,status='producer_complete_pending_independent_observer',fit_attempt_count=4,sum_metric_looks=4,children=[],candidates=[],winner={},source_paid_cpu_seconds=100.,actual_parent_cpu_seconds=1.,actual_reaped_children_cpu_seconds=2.,charged_study_cpu_seconds=103.,started_monotonic=started,producer_finished_monotonic=a.START-1,original_absolute_deadline_monotonic=started+3600,parent_peak_rss_bytes=1,heldout_labels_opened=False,active_slot=None,unknown_live_fit=False,unknown_metric_looks=False))
 request=write(inv/'request.json',dict(version=1,scope=a.SCOPE,run_id=rid,producer_manifest=manifest,producer_report=report,execution_approval=approval,budget_claim=claim,oracle_source=source,shared_budget=dict(limit_cpu_seconds=7200,charged_prefix_cpu_seconds=103.,unknown_cost=False,source_paid_cpu_seconds=100.,owner_parent_cpu_seconds=1.,owner_reaped_children_cpu_seconds=2.),original_owner=dict(started_monotonic=started,absolute_deadline_monotonic=started+3600),permissions=dict(observer_calls=1,refits=0,source_regenerations=0)))
 allocation=dict(cpu_seconds=600,deadline_monotonic=a.START+100,rss_bytes=7*2**30)
 context=write(inv/'context.json',dict(version=1,scope=a.SCOPE,run_id=rid,project_root=str(root),invocation_directory=rel(inv),request=request,producer_manifest=manifest,producer_report=report,oracle_source=source,allocation=allocation,issued_at_monotonic=a.START-1,output_path=rel(inv/'evidence.json'),failed_output_path=rel(inv/'evidence.failed.json')))
 once=write(inv/'once.claim.json',dict(version=1,scope=a.SCOPE,run_id=rid,observer_calls=1,original_four_fit_claim=claim,request=request,context_sha256=context['sha256']))
 write(inv/'launch.json',dict(version=1,scope=a.SCOPE,run_id=rid,argv=[a.sys.executable,str(entry),'--context',str(inv/'context.json'),'--issued-context-sha256',context['sha256']],cwd=str(root),context_sha256=context['sha256'],request=request,allocation=allocation,claim=once))
 return dict(root=root,context=root/context['path'],sha=context['sha256'],entry=entry,write=write,approval=approval)


class PureTests(unittest.TestCase):
 def test_fullY_and_four_estimands_handgold(self):
  q=[('a',1,datetime(2020,1,1),{10,99}),('b',1,datetime(2020,1,1),set()),('c',2,datetime(2020,1,1),{77})]
  m,v,u=a.summarize(q,[(11,10),(),()])
  self.assertEqual(m['conditional_macro_query']['recall'],.25)
  self.assertEqual(m['all_query_zero']['recall'],1/6)
  self.assertEqual(m['conditional_user_macro']['recall'],.25)
  self.assertEqual(m['all_user_macro_zero']['recall'],.125)
  self.assertAlmostEqual(m['conditional_macro_query']['ndcg'],(1/np.log2(3))/(1+1/np.log2(3))/2)
  self.assertEqual(m['conditional_macro_query']['average_precision'],.125)
  self.assertEqual(m['conditional_macro_query']['reciprocal_rank'],.25)
  boot=a.paired_bootstrap(v,v,u)
  self.assertEqual(set(boot),set(a.ESTIMANDS))
  for b in boot.values():self.assertEqual(set(x for x in b['samples'] if x is not None),{0.});self.assertEqual(b['replicates'],200)
 def test_global_band_and_recall_boundary_no_chaining(self):
  def c(cid,n,r=.5):return dict(candidate_id=cid,status='verified_success',added_physical_columns=0 if cid=='B' else 3,metrics=dict(conditional_macro_query=dict(ndcg=n,recall=r)))
  cs=[c('B',.1),c('I1',.5),c('I2',.5+1.8e-12),c('R1',.5+.9e-12),c('R2',.8,.4979)]
  self.assertEqual(a.select(cs)['candidate_id'],'I2')
  cs[-1]=c('R2',.8,.498);self.assertEqual(a.select(cs)['candidate_id'],'R2')
  cs=[c(k,.5) for k in a.IDS];self.assertEqual(a.select(cs)['candidate_id'],'B')
  cs[-1]['status']='resource_failed';cs[-1]['metrics']=None;self.assertEqual(a.select(cs)['candidate_id'],'B')
  cs[-1]['metrics']={}
  with self.assertRaises(ValueError):a.select(cs)
 def test_strict_json_types_and_float32_contract(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
   with self.assertRaises(ValueError):a.parse(raw)
  for x,y in [(1,True),(1,1.),(.05,.05000000074505806)]:
   with self.assertRaises(ValueError):a.same(x,y)
  import struct
  v=struct.unpack('!f',struct.pack('!f',.05))[0];a.native_same(v,.05000000075)
  with self.assertRaises(ValueError):a.native_same(v,.051)
 def test_matrix_witness_nan_canonical_keys_and_weights(self):
  q=[('q',9007199254740993,datetime(2020,1,1),frozenset({8,7})),('zero',2,datetime(2020,1,1),frozenset({9}))]
  x=np.array([[np.nan,1.],[2.,3.]],dtype=np.float32)
  d=a.Matrix(q,np.array([0,0],np.int32),np.array([9007199254740993,8],np.int64),x,np.array([0,1],np.int8),['a','b'])
  weights,s=a.group_weights(d);np.testing.assert_array_equal(weights,[.5,.5]);self.assertEqual(s['empty_candidate_groups'],1)
  first=a.matrix_proof(d,weights=weights);d.x.view(np.uint32)[0,0]=0x7fc01234
  self.assertEqual(first,a.matrix_proof(d,weights=weights));self.assertEqual(first['arrays']['items']['dtype'],'<i8')
  d.items[0]-=1;self.assertNotEqual(first,a.matrix_proof(d,weights=weights))
 def test_rank_tie_exact_bigint_and_nonfinite_reject(self):
  d=a.Matrix([('q',1,datetime(2020,1,1),set()),('zero',2,datetime(2020,1,1),set())],np.array([0,0],np.int32),np.array([9007199254740993,9007199254740992],np.int64),None,None,[])
  self.assertEqual(a.rankings(d,np.array([0.,0.])),[(9007199254740992,9007199254740993),()])
  with self.assertRaises(ValueError):a.rankings(d,np.array([0.,np.inf]))

class SqlTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
  self.con=duckdb.connect();self.addCleanup(self.con.close);self.con.execute('SET threads=2')
  t=datetime(2020,1,1)
  self.con.execute('CREATE TABLE q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN,_group BIGINT)')
  self.con.executemany('INSERT INTO q VALUES(?,?,?,?,?)',[('a',9007199254740993,t,True,0),('b',2,t,True,0),('zero',3,t,True,0)])
  fields=['query_id VARCHAR','user_id BIGINT','product_id BIGINT','anchor TIMESTAMP','candidate_category_id BIGINT','last_user_event_time TIMESTAMP']+[n+' DOUBLE' for n in BASE[:-2]]
  self.con.execute('CREATE TABLE f('+','.join(fields)+')')
  self.con.executemany('INSERT INTO f VALUES('+','.join('?' for _ in fields)+')',[
   ('a',9007199254740993,9007199254740993,t,None,t-timedelta(seconds=50),*([0.]*39)),('b',2,42,t,None,None,*([None]*39))])
  self.con.execute('CREATE TABLE c AS SELECT query_id,product_id FROM f')
  self.con.execute('CREATE TABLE y(query_id VARCHAR,product_id BIGINT)');self.con.execute("INSERT INTO y VALUES('a',9007199254740993),('zero',999)")
  self.con.execute('CREATE TABLE e AS SELECT f.*,3::BIGINT auto_count,50.0::DOUBLE auto_age,false::BOOLEAN auto_age_missing,'+','.join(str(i)+'::BIGINT auto_unused'+str(i) for i in range(9))+' FROM f')
  self.con.execute("UPDATE e SET auto_count=0,auto_age=NULL,auto_age_missing=true WHERE query_id='b'")
  self.save();self.col=dict(phase=dict(role='selection'),refs=dict(queries=['q.parquet'],features=['f.parquet'],candidates=['c.parquet'],labels=['y.parquet']))
 def save(self):
  for n in ('q','c','f','y','e'):self.con.execute('COPY '+n+' TO ? (FORMAT PARQUET)',[str(self.root/(n+'.parquet'))])
 def load(self,extra=True,cap=None):
  return a.read_matrix(self.con,self.col,BASE,local=lambda p:self.root/p,cap=cap,extra_paths=['e.parquet'] if extra else None,delta=DELTA if extra else ())
 def test_independent_SQL_fullQ_emptyC_exact_ids_and_three(self):
  b=self.load(False);m=self.load()
  self.assertEqual(m.items.tolist(),[9007199254740993,42]);self.assertEqual(m.group.tolist(),[0,1]);self.assertEqual(m.y.tolist(),[1,0]);self.assertEqual(len(m.queries),3)
  self.assertEqual(m.queries[-1][-1],frozenset({999}));self.assertEqual(m.x.shape,(2,44));np.testing.assert_array_equal(m.x[:,:41],b.x)
  self.assertEqual(m.x[0,39],50.);self.assertTrue(np.isnan(m.x[1,39]));self.assertEqual(m.x[:,40].tolist(),[0.,1.]);self.assertEqual(m.x[:,41].tolist(),[3.,0.]);self.assertTrue(np.isnan(m.x[1,42]))
 def test_labelblind_bottomSHA_and_duplicate_missing_future_faults(self):
  before=self.load(cap=2);self.con.execute('DELETE FROM y');self.con.execute("INSERT INTO y VALUES('b',42)");self.save();after=self.load(cap=2)
  self.assertEqual([q[:3] for q in before.queries],[q[:3] for q in after.queries]);np.testing.assert_array_equal(before.x,after.x);np.testing.assert_array_equal(before.items,after.items)
  self.con.execute('INSERT INTO c SELECT * FROM c LIMIT 1');self.save()
  with self.assertRaises(ValueError):self.load()
 def test_mask_inf_and_missing_extra_faults(self):
  self.con.execute("UPDATE e SET auto_age_missing=false WHERE query_id='b'");self.save()
  with self.assertRaises(ValueError):self.load()
  self.con.execute("UPDATE e SET auto_age='inf'::DOUBLE WHERE query_id='b'");self.save()
  with self.assertRaises(ValueError):self.load()
  self.con.execute("DELETE FROM e WHERE query_id='b'");self.save()
  with self.assertRaises(ValueError):self.load()
 def test_microsecond_age_uses_interval_not_large_epoch_cancellation(self):
  self.con.execute("UPDATE f SET last_user_event_time=anchor-INTERVAL 1 MICROSECOND WHERE query_id='a'");self.save();d=self.load()
  self.assertEqual(d.x[0,39],np.float32(1e-6))
 def test_empty_C_preserves_full_Y_and_queries(self):
  for n in ('c','f','e'):self.con.execute('DELETE FROM '+n)
  self.save();d=self.load();self.assertEqual(d.x.shape,(0,44));self.assertEqual(len(d.queries),3);self.assertEqual(d.queries[-1][-1],{999})


class LifecycleTests(unittest.TestCase):
 def bare(self,root):
  root=root.resolve();obj=a.Audit.__new__(a.Audit);obj.root=root;obj.path=root/'context.json';obj.path.write_bytes(b'{}');obj.context_sha=hashlib.sha256(b'{}').hexdigest()
  obj.directory=root/'job';obj.directory.mkdir();obj.inv=obj.directory/'observer';obj.inv.mkdir();obj.output=obj.inv/'evidence.json';obj.failed=obj.inv/'evidence.failed.json'
  obj.context=dict(run_id='a'*64);obj.source=dict(path='entry.py',sha256=hashlib.sha256(b'entry').hexdigest());(root/'entry.py').write_bytes(b'entry')
  obj.identity=dict(fingerprints={});obj.manifest=dict(outputs={});obj.observed={};obj.worker_data={};obj.con=None;obj.timer=None
  import threading
  obj.stopped=threading.Event();obj.expired=threading.Event();obj.allocation=dict(cpu_seconds=600,rss_bytes=7*2**30,deadline_monotonic=a.time.monotonic()+100)
  obj.phase='synthetic';return obj
 def test_primary_close_failure_and_late_authority_marker_no_false_success(self):
  with tempfile.TemporaryDirectory() as t:
   obj=self.bare(Path(t));obj.binding=lambda:None;obj.execute=lambda:dict(status='verified');obj.con=types.SimpleNamespace(close=lambda:(_ for _ in ()).throw(OSError('close')))
   with self.assertRaises(OSError):obj.run()
   self.assertFalse(obj.output.exists());self.assertTrue(obj.failed.exists())
  with tempfile.TemporaryDirectory() as t:
   obj=self.bare(Path(t));obj.binding=lambda:None;obj.execute=lambda:dict(status='verified');original=obj.persist
   def persist(path,value):
    original(path,value)
    if path==obj.output:(obj.directory/'report.failed.json').write_text('{}')
   obj.persist=persist
   with self.assertRaises(ValueError):obj.run()
   self.assertTrue(obj.failed.exists())
 def test_secondary_counter_failure_preserves_primary(self):
  with tempfile.TemporaryDirectory() as t:
   obj=self.bare(Path(t));obj.binding=lambda:(_ for _ in ()).throw(ValueError('PRIMARY'));obj.cpu=lambda:(_ for _ in ()).throw(OSError('counter'))
   with self.assertRaisesRegex(ValueError,'PRIMARY'):obj.run()
   self.assertTrue(obj.failed.exists());self.assertEqual(a.parse(obj.failed.read_bytes())['error_type'],'ValueError')
 def test_original_context_snapshot_parse_once(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'ctx';raw=b'{"version":1,"scope":"wrong"}';path.write_bytes(raw)
   seen=[];original=a.parse
   def parse(data):seen.append(data);return original(data)
   with patch.object(a,'parse',parse),patch.object(Path,'read_bytes',return_value=b'{"version":999}'):
    with self.assertRaises(ValueError):a.Audit(path,hashlib.sha256(raw).hexdigest())
   self.assertEqual(seen,[raw])
 def test_resource_guard_absolute_cpu_and_descendant(self):
  with tempfile.TemporaryDirectory() as t:
   obj=self.bare(Path(t))
   with patch.object(obj,'cpu',return_value=601):
    with self.assertRaises(TimeoutError):obj.guard()
   with patch.object(a.resource,'getrusage',return_value=types.SimpleNamespace(ru_utime=.1,ru_stime=0)):
    with patch.object(obj,'cpu',return_value=0),patch.object(obj,'rss',return_value=1):
     with self.assertRaises(ValueError):obj.guard()




class WorkerAuthorityTests(LifecycleTests):
 # Explicitly suppress inherited lifecycle discovery: separate unique tests.
 test_primary_close_failure_and_late_authority_marker_no_false_success=None
 test_secondary_counter_failure_preserves_primary=None
 test_original_context_snapshot_parse_once=None
 test_resource_guard_absolute_cpu_and_descendant=None
 def fixture(self,root,failed=False):
  obj=self.bare(root);writer=populate_workers(a,obj,resource_failure=failed);return obj,writer
 def test_all_four_durable_workers_and_recognized_resource_failure(self):
  with tempfile.TemporaryDirectory() as t:
   obj,_=self.fixture(Path(t),True);obj.workers();self.assertEqual(set(obj.worker_proofs),set(a.SLOTS));self.assertEqual(obj.worker_proofs['R2']['status'],'preserved_paid_resource_failure')
 def test_fresh_resealed_issued_argv_mutant_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   obj,write=self.fixture(Path(t));child=obj.report['children'][0];launch=a.parse((obj.root/child['launch']['path']).read_bytes());launch['argv'][-1]='0'*64
   child['launch']=write(obj.root/child['launch']['path'],launch)
   with self.assertRaises(ValueError):obj.workers()
 def test_late_failed_worker_and_whole_job_cap_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   obj,write=self.fixture(Path(t));child=obj.report['children'][0];(obj.root/child['report']['path']).with_name('report.failed.json').write_text('{}')
   with self.assertRaises(ValueError):obj.workers()
  with tempfile.TemporaryDirectory() as t:
   obj,write=self.fixture(Path(t),True);child=obj.report['children'][-1];r=child['worker_report'];r['process_peak_rss_bytes']=8*2**30
   child['report']=write(obj.root/child['report']['path'],r)
   with self.assertRaises(ValueError):obj.workers()



class SavedModelTests(unittest.TestCase):
 def test_mock_native_prefix_full_npz_and_drift(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();obj=a.Audit.__new__(a.Audit);obj.root=root;obj.guard=lambda:None
   params=dict(loss_function='Logloss',iterations=3,depth=4,l2_leaf_reg=3,random_seed=2026,task_type='CPU',boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False,
    learning_rate=.05000000074505806,border_count=254,nan_mode='Min',rsm=1,eval_metric='Logloss',auto_class_weights='None',grow_policy='SymmetricTree',feature_border_type='GreedyLogSum')
   obj.identity=dict(model_spec=dict(scoring_prefix=2,trained_iterations=3),model_parameters=dict(params),native_reference=params)
   q=[('q',1,datetime(2020,1,1),frozenset({7}))];d=a.Matrix(q,np.array([0,0],np.int32),np.array([7,8],np.int64),np.zeros((2,44),np.float32),np.array([1,0],np.int8),['f'+str(i) for i in range(44)])
   np.savez(root/'scores.npz',group=d.group,product_id=d.items,raw_score=np.array([0.,0.],np.float64))
   (root/'full.json').write_text(a.canonical(dict(oblivious_trees=[{}, {}, {}],features_info=dict(float_features=[dict(flat_feature_index=i,feature_id=n) for i,n in enumerate(d.feature_names)]))))
   obj.read=lambda p:(a.parse(p.read_bytes()),hashlib.sha256(p.read_bytes()).hexdigest())
   state=dict(drift=False,params=params)
   class Fake:
    def load_model(self,p):self.tree_count_=2 if Path(p).name=='prefix.cbm' else 3;self.feature_names_=d.feature_names
    def get_cat_feature_indices(self):return []
    def get_all_params(self):return state['params']
    def predict(self,x,**kwargs):
     self_test.assertEqual(kwargs['thread_count'],2)
     return np.array([0.,1e-13 if state['drift'] else 0.])
   self_test=self
   with patch.dict(sys.modules,{'catboost':types.SimpleNamespace(CatBoostClassifier=Fake)}):
    m,_,_=obj.model_scores(d,'prefix.cbm','scores.npz',actual=params,full_path='full.cbm',json_path='full.json');self.assertEqual(m['conditional_macro_query']['ndcg'],1.)
    state['drift']=True
    with self.assertRaisesRegex(ValueError,'fidelity'):obj.model_scores(d,'prefix.cbm','scores.npz',actual=params)
    state['drift']=False;bad=dict(params,l2_leaf_reg=30)
    with self.assertRaises(ValueError):obj.model_scores(d,'prefix.cbm','scores.npz',actual=bad)



class BindingTests(unittest.TestCase):
 def test_native_tiny_same_snapshot_context_and_approval_types(self):
  with tempfile.TemporaryDirectory() as t:
   f=build_binding(a,Path(t))
   with patch.object(a,'__file__',str(f['entry'])):
    observer=a.Audit(f['context'],f['sha']);observer.binding()
    self.assertEqual(observer.report['fit_attempt_count'],4)
    original=observer.ref(observer.manifest['execution_approval']);original['approved']=1
    f['write'](f['root']/f['approval']['path'],original)
    # Fresh local hash does not replace the exact issued approval reference.
    with self.assertRaises(ValueError):observer.binding()
 def test_context_original_issuer_hash_rejects_fresh_reseal(self):
  with tempfile.TemporaryDirectory() as t:
   f=build_binding(a,Path(t));c=a.parse(f['context'].read_bytes());c['allocation']['cpu_seconds']=601;f['write'](f['context'],c)
   with patch.object(a,'__file__',str(f['entry'])):
    with self.assertRaises(ValueError):a.Audit(f['context'],f['sha'])



class ExecutionConsumptionTests(unittest.TestCase):
 def test_original_lost_receipt_context_cannot_repeat_any_paid_pin_pass(self):
  with tempfile.TemporaryDirectory() as t:
   f=build_binding(a,Path(t));passes=[]
   with patch.object(a,'__file__',str(f['entry'])):
    first=a.Audit(f['context'],f['sha']);original=first.pins
    def paid(values):passes.append(values);original(values)
    first.pins=paid;first.binding();self.assertEqual(len(passes),2)
    ref=first.execution_consumed;raw=(first.root/ref['path']).read_bytes()
    self.assertEqual(ref['sha256'],hashlib.sha256(raw).hexdigest())
    self.assertEqual(a.parse(raw),dict(version=1,scope=a.SCOPE+'_execution_consumed',run_id=first.context['run_id'],context_sha256=f['sha'],request=first.context['request'],original_four_fit_claim=first.manifest['budget_claim'],oracle_source=first.source,observer_calls=1,refits=0,source_regenerations=0))
    second=a.Audit(f['context'],f['sha']);second.pins=lambda values:(_ for _ in ()).throw(AssertionError('paid work repeated'))
    with self.assertRaises(FileExistsError):second.binding()
    self.assertEqual((first.root/ref['path']).read_bytes(),raw)
 def test_paid_pin_failure_still_consumes_execution(self):
  with tempfile.TemporaryDirectory() as t:
   f=build_binding(a,Path(t))
   with patch.object(a,'__file__',str(f['entry'])):
    first=a.Audit(f['context'],f['sha']);first.pins=lambda values:(_ for _ in ()).throw(TimeoutError('paid fault'))
    with self.assertRaises(TimeoutError):first.binding()
    self.assertTrue((first.inv/'execution.consumed.json').exists())
    second=a.Audit(f['context'],f['sha'])
    with self.assertRaises(FileExistsError):second.binding()
 def test_own_late_failed_marker_prevents_success_and_known_marker_afterwrite(self):
  with tempfile.TemporaryDirectory() as t:
   obj=LifecycleTests().bare(Path(t));obj.binding=lambda:None
   def execute():obj.failed.write_text('{"status":"failed"}');return dict(status='verified')
   obj.execute=execute
   with self.assertRaises(ValueError):obj.run()
   self.assertFalse(obj.output.exists())
  with tempfile.TemporaryDirectory() as t:
   obj=LifecycleTests().bare(Path(t));obj.binding=lambda:None;obj.execute=lambda:dict(status='verified');original=obj.persist
   def persist(path,value):
    result=original(path,value)
    if path==obj.output:obj.failed.write_text('{"status":"failed"}')
    return result
   obj.persist=persist
   with self.assertRaises(ValueError):obj.run()
 def test_success_producer_unknown_flags_fail_strictly_before_consumption(self):
  for key,value in [('active_slot',{}),('unknown_live_fit',0),('unknown_metric_looks',True)]:
   with self.subTest(key=key),tempfile.TemporaryDirectory() as t:
    f=build_binding(a,Path(t));c=a.parse(f['context'].read_bytes());p=f['root']/c['producer_report']['path'];report=a.parse(p.read_bytes());report[key]=value
    # Reseal the producer ref consistently through request/context. This is an
    # authority-schema probe, not an original issuer hash mismatch.
    rr=f['write'](p,report);request=a.parse((f['root']/c['request']['path']).read_bytes());request['producer_report']=rr;c['request']=f['write'](f['root']/c['request']['path'],request);c['producer_report']=rr;new=f['write'](f['context'],c)
    with patch.object(a,'__file__',str(f['entry'])):
     obj=a.Audit(f['context'],new['sha256'])
     with self.assertRaises(ValueError):obj.binding()
     self.assertFalse((obj.inv/'execution.consumed.json').exists())

if __name__=='__main__':unittest.main()
