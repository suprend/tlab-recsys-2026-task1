from pathlib import Path
import importlib.util,json,tempfile,unittest,hashlib,contextlib,io,time
from copy import deepcopy
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import patch
import duckdb
from scripts import feature_programs as p,manual_features as compiler
from scripts.protocol_manifest import load_protocol,canonical_json,sha256_file
from tests.test_feature_programs import EVENTS,T,S,reference
from scripts import feature_program_collection as f
ROOT=Path(__file__).resolve().parents[1]

class CollectionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.addCleanup(patch.stopall)
  patch.object(f,'ROOT',self.root).start();patch.object(f.mechanics,'ROOT',self.root).start()
  self.base=compiler.load_registry(ROOT/'configs/features/manual-18.json');self.contract=json.loads((ROOT/'configs/features/automation-pool.json').read_text());self.pool=p.generate_pool(self.contract,self.base);self.allocation=p.allocate_slots(self.pool);self.union=f.selected_union(self.pool,self.allocation)
  self.config=load_protocol(ROOT/'configs/protocols/clock-48h.json');self.config['pilot']['end']='2019-10-13T00:00:00Z';self.config['query']['max_users_per_day']=3;self.config['budget']['max_anchors']=15
  self.source=self.root/'source.duckdb';con=duckdb.connect(str(self.source));con.execute('SET threads=2')
  con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)');con.executemany('INSERT INTO events VALUES(?,?,?,?,?)',EVENTS)
  self.collections={}
  for role,day in [('train',T),('selection',T+timedelta(days=2))]:
   con.execute('CREATE OR REPLACE TEMP TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
   con.executemany('INSERT INTO pilot_queries VALUES(?,?,?,?)',[(role+'A',1,day,True),(role+'B',2,day,True),(role+'empty',3,day,True)])
   con.execute('CREATE OR REPLACE TEMP TABLE pilot_candidates(query_id VARCHAR,product_id BIGINT,from_popular BOOLEAN,from_recent BOOLEAN,popularity_distinct_users BIGINT,popular_source_rank BIGINT,recent_source_rank BIGINT,last_user_event_time TIMESTAMP)')
   con.executemany('INSERT INTO pilot_candidates VALUES(?,?,?,?,?,?,?,?)',[(role+q,i,True,False,1,j,None,None) for j,(q,i) in enumerate([('A',10),('A',20),('B',10),('B',20)],1)])
   compiler.create_manual_features(con,self.config,self.base)
   refs={}
   for name,table in [('queries','pilot_queries'),('candidates','pilot_candidates'),('features','manual_features')]:
    path=self.root/(role+'_'+name+'.parquet');con.execute('COPY '+table+' TO ? (FORMAT PARQUET)',[str(path)]);refs[name]=[path.name]
   refs['labels']=['POISON_missing_targets_DO_NOT_READ.parquet']
   schema=[tuple(z[:2]) for z in con.execute('DESCRIBE manual_features').fetchall()];self.assertEqual(len(schema),45)
   self.collections[role]=dict(refs=refs,feature_columns=schema,phase=dict(role=role,range=dict(start=day.strftime('%Y-%m-%dT%H:%M:%SZ'),end=(day+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))),
      plan=dict(collection_id=(('a' if role=='train' else 'b')*64),execution_inputs=dict(source_path='source.duckdb'),identity=dict(shard_protocols=[deepcopy(self.config)])))
  con.close()
  pins={path.name:sha256_file(path) for path in self.root.glob('*.parquet')};pins[self.source.name]=sha256_file(self.source)
  identity=dict(version=1,role=f.ROLE,limits=deepcopy(f.LIMITS),fingerprints=pins,acceptance_refs={k:'approval.json' for k in ['train','selection','contract','base_registry']},pool=self.pool,allocation=self.allocation,selected_union=self.union,base_feature_columns=self.collections['train']['feature_columns'])
  identity=json.loads(canonical_json(identity)) # Transport fixture must match actual JSON list schemas.
  self.plan=dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity)
  self.approval=self.root/'approval.json';self.approval.write_text(canonical_json(dict(version=1,approved=True,scope=f.ROLE,run_id=self.plan['run_id'],fingerprints=pins)))
  self.preparer=patch.object(f,'prepare_plan',side_effect=lambda *a,**k:(deepcopy(self.plan),deepcopy(self.collections)));self.preparer.start()
  patch.object(f.SourceAudit,'guard',lambda audit:None).start() # Only tiny runner plumbing; resource boundary tested separately.

 def produce(self):
  with contextlib.redirect_stdout(io.StringIO()):return f.run_source(self.approval,self.approval,self.approval,self.approval,execution_approval=self.approval)
 def directory(self):return self.root/'artifacts/feature-program-collection'/self.plan['run_id']
 def test_real_tiny_selected_union_preservesB_and_allQ_noY_relation(self):
  result=self.produce();self.assertEqual(result['status'],'complete_produced_unreviewed');self.assertEqual(result['fit_attempt_count'],0);self.assertFalse(result['labels_loaded'])
  manifest=f._read_json(self.directory()/'run.json');self.assertEqual([len(x) for x in manifest['outputs'].values()],[1,1])
  con=duckdb.connect(':memory:')
  try:
   for role,col in self.collections.items():
    path=f.mechanics.local(manifest['outputs'][role][0]['artifacts']['features']['path']);con.read_parquet(str(path)).create_view('actual',replace=True)
    rows=con.execute('SELECT * FROM actual ORDER BY query_id,product_id').fetchall();names=[x[0] for x in con.description]
    self.assertEqual(len(rows),4);self.assertEqual(len(names),57);self.assertEqual(result['phases'][role]['queries'],3)
    anchor=T if role=='train' else T+timedelta(days=2)
    for row in rows:
     v=dict(zip(names,row));user=1 if v['query_id'].endswith('A') else 2
     for program in self.union['registry']['features'][18:]:
      expected=reference(EVENTS,program,user,v['product_id'],anchor);self.assertEqual(v[program['name']],expected)
  finally:con.close()
  with self.assertRaises(FileExistsError):self.produce()

 def test_legal_wrong_new_count_passes_physical_only_and_oldB_change_rejects(self):
  self.produce();m=f._read_json(self.directory()/'run.json');d=m['outputs']['train'][0];path=f.mechanics.local(d['artifacts']['features']['path']);con=duckdb.connect(':memory:')
  try:
   con.execute('CREATE TABLE altered AS SELECT * FROM read_parquet(?)',[str(path)]);name=self.union['physical_delta'][0]['name'];con.execute('UPDATE altered SET "'+name+'"="'+name+'"+1 WHERE query_id=?',['trainA'])
   changed=self.root/'changed.parquet';con.execute('COPY altered TO ?(FORMAT PARQUET)',[str(changed)]);path.write_bytes(changed.read_bytes());d['artifacts']['features'].update(sha256=sha256_file(path),bytes=path.stat().st_size)
   outcome=f.inspect_physical(m,self.collections);self.assertFalse(outcome['source_formula_acceptance'])
   con.execute('UPDATE altered SET from_popular=false');con.execute('COPY altered TO ?(FORMAT PARQUET)',[str(changed)]);path.write_bytes(changed.read_bytes());d['artifacts']['features'].update(sha256=sha256_file(path),bytes=path.stat().st_size)
   with self.assertRaisesRegex(ValueError,'baseline physical'):f.inspect_physical(m,self.collections)
  finally:con.close()

 def test_failed_wrong_approval_consumes_source_claim_without_source_SQL(self):
  self.approval.write_text('{}')
  with patch.object(f.duckdb,'connect',side_effect=AssertionError('source SQL beforeapproval')):
   with self.assertRaisesRegex(ValueError,'executionapproval'):self.produce()
  self.assertTrue((self.root/'artifacts/feature-program-study/source.claim.json').exists())
  reports=list((self.root/'artifacts/feature-program-collection').glob('*/report.json'));self.assertEqual(f._read_json(reports[0])['status'],'failed')

 def test_output_typed_schema_query_allfields_and_missing_day_reject(self):
  self.produce();m=f._read_json(self.directory()/'run.json')
  bad=deepcopy(m);bad['outputs']['selection']=[]
  with self.assertRaisesRegex(ValueError,'partition'):f.inspect_physical(bad,self.collections)
  bad=deepcopy(m);bad['outputs']['train'][0]['artifacts']['features']['schema'][0][1]='BIGINT'
  with self.assertRaisesRegex(ValueError,'schema/count'):f.inspect_physical(bad,self.collections)


 def seal_tiny(self):
  directory=self.directory();m=f._read_json(directory/'run.json');out={a['path']:a['sha256'] for ds in m['outputs'].values() for d in ds for a in d['artifacts'].values()}
  source=self.root/'tiny_independent_oracle.py';source.write_text('# independent row-iteration reference fixture, no executable approval writer\n')
  source_ref=dict(path=source.name,sha256=sha256_file(source));evidence=self.root/'tiny_evidence.json'
  value=dict(status='verified',run_id=m['run_id'],source_proof_scope='all_selected12_values_and_accepted_QC_domain',formula_values_complete=True,
   oracle_source=source_ref,fit_attempt_count=0,verified_outputs=out,checked_pairs=8,checked_physical_columns=12,checked_scalar_values=96,mismatch_count=0)
  evidence.write_text(canonical_json(value));eref=dict(path=evidence.name,sha256=sha256_file(evidence))
  parent=self.root/'tiny_parent_receipt.json';report=f._read_json(directory/'report.json')
  producer=dict(exit_code=0,actual_cpu_seconds=report['process_cpu_user_system_seconds']+.01,wall_seconds=report['seconds']+.01,peak_rss_bytes=report['process_peak_rss_bytes'],manifest=dict(path=f.mechanics.relative(directory/'run.json'),sha256=sha256_file(directory/'run.json')),report=dict(path=f.mechanics.relative(directory/'report.json'),sha256=sha256_file(directory/'report.json')))
  oracle=dict(exit_code=0,actual_cpu_seconds=.01,wall_seconds=.02,peak_rss_bytes=1024,oracle_source=source_ref,evidence=eref)
  parent.write_text(canonical_json(dict(status='verified',run_id=m['run_id'],observer_exit_code=0,oracle_source=source_ref,evidence=eref,actual_cpu_seconds=producer['actual_cpu_seconds']+.01,producer=producer,oracle=oracle)))
  proof=dict(oracle_source=source_ref,aggregate_evidence=eref,parent_receipt=dict(path=parent.name,sha256=sha256_file(parent)))
  required=f.mechanics.merge_pins(self.plan['identity']['fingerprints'],out,
   {m['execution_approval']['path']:m['execution_approval']['sha256'],m['source_claim']['path']:m['source_claim']['sha256']},
   {f.mechanics.relative(directory/n):sha256_file(directory/n) for n in ['run.json','report.json']},{v['path']:v['sha256'] for v in proof.values()})
  accepted=self.root/'accepted_source.json';accepted.write_text(canonical_json(dict(version=1,approved=True,scope='reviewed_selected_feature_program_source',run_id=m['run_id'],fingerprints=required,source_proof=proof)))
  return accepted

 def test_fixed_independent_proof_accepts_then_legal_changed_value_fresh_reseal_rejects(self):
  self.produce();accepted=self.seal_tiny();self.assertEqual(f.verify_source_acceptance(accepted)['physical']['status'],'physical_consistency_passed')
  directory=self.directory();m=f._read_json(directory/'run.json');a=m['outputs']['train'][0]['artifacts']['features'];path=f.mechanics.local(a['path']);con=duckdb.connect(':memory:')
  try:
   name=self.union['physical_delta'][0]['name'];con.execute('CREATE TABLE wrong AS SELECT * FROM read_parquet(?)',[str(path)]);con.execute('UPDATE wrong SET "'+name+'"="'+name+'"+1')
   change=self.root/'freshwrong.parquet';con.execute('COPY wrong TO ?(FORMAT PARQUET)',[str(change)]);path.write_bytes(change.read_bytes())
  finally:con.close()
  a.update(sha256=sha256_file(path),bytes=path.stat().st_size);(directory/'run.json').write_text(canonical_json(m))
  v=f._read_json(accepted);v['fingerprints'][a['path']]=a['sha256'];v['fingerprints'][f.mechanics.relative(directory/'run.json')]=sha256_file(directory/'run.json');accepted.write_text(canonical_json(v))
  with self.assertRaisesRegex(ValueError,'full output map'):f.verify_source_acceptance(accepted)

 def test_known_failed_marker_and_nonlocal_runID_reject_before_rederivation(self):
  self.produce();accepted=self.seal_tiny();(self.directory()/'report.failed.json').write_text('{}')
  with patch.object(f,'prepare_plan',side_effect=AssertionError('read after knownfailed')):
   with self.assertRaisesRegex(ValueError,'Known failed'):f.verify_source_acceptance(accepted)
  v=f._read_json(accepted);v['run_id']='../../outside';accepted.write_text(canonical_json(v))
  with self.assertRaisesRegex(ValueError,'Invalid accepted runID'):f.verify_source_acceptance(accepted)

 def test_outside_partition_emptyC_query_cannot_be_silently_omitted(self):
  self.produce();manifest=f._read_json(self.directory()/'run.json');q=self.root/self.collections['train']['refs']['queries'][0];con=duckdb.connect(':memory:')
  try:
   con.execute('CREATE TABLE changed AS SELECT * FROM read_parquet(?)',[str(q)]);con.execute("INSERT INTO changed VALUES('outside-empty',4,'2019-10-11',true)")
   p=self.root/'outside.parquet';con.execute('COPY changed TO ?(FORMAT PARQUET)',[str(p)]);q.write_bytes(p.read_bytes())
  finally:con.close()
  with self.assertRaisesRegex(ValueError,'Whole accepted Q'):f.inspect_physical(manifest,self.collections)

 def test_fresh_resealed_report_runID_must_equal_bound_source_run(self):
  self.produce();accepted=self.seal_tiny();reportpath=self.directory()/'report.json';report=f._read_json(reportpath);report['run_id']='f'*64;reportpath.write_text(canonical_json(report))
  a=f._read_json(accepted);parentpath=self.root/a['source_proof']['parent_receipt']['path'];parent=f._read_json(parentpath)
  parent['producer']['report']['sha256']=sha256_file(reportpath);parentpath.write_text(canonical_json(parent))
  a['source_proof']['parent_receipt']['sha256']=sha256_file(parentpath);a['fingerprints'][f.mechanics.relative(reportpath)]=sha256_file(reportpath);a['fingerprints'][f.mechanics.relative(parentpath)]=sha256_file(parentpath);accepted.write_text(canonical_json(a))
  with self.assertRaisesRegex(ValueError,'Actual source plan differs'):f.verify_source_acceptance(accepted)

 def test_fresh_resealed_parent_lifetime_cannot_understate_wall_or_RSS(self):
  self.produce();accepted=self.seal_tiny();original=f._read_json(accepted);parentpath=self.root/original['source_proof']['parent_receipt']['path'];originalparent=f._read_json(parentpath)
  for name,value in [('wall_seconds',0),('peak_rss_bytes',1)]:
   with self.subTest(name=name):
    parent=deepcopy(originalparent);parent['producer'][name]=value;parentpath.write_text(canonical_json(parent))
    a=deepcopy(original);a['source_proof']['parent_receipt']['sha256']=sha256_file(parentpath);a['fingerprints'][f.mechanics.relative(parentpath)]=sha256_file(parentpath);accepted.write_text(canonical_json(a))
    with self.assertRaisesRegex(ValueError,'Lifetime cost receipt detached'):f.verify_source_acceptance(accepted)

class SourceResources(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name).resolve();self.addCleanup(patch.stopall)
  patch.object(f,'ROOT',self.root).start()
 def test_absoluteCPU_import_prefix_is_not_reset_at_audit_creation(self):
  with patch.object(f.mechanics,'cpu_time',return_value=900.01):
   audit=f.SourceAudit()
   self.assertEqual(audit.cpu_started,0.)
   with self.assertRaisesRegex(TimeoutError,'CPU'):audit.guard()
 def test_unknown_subprocess_usage_is_not_accepted_as_zero(self):
  original=f.resource.getrusage
  def usage(kind):return SimpleNamespace(ru_utime=.1,ru_stime=0) if kind==f.resource.RUSAGE_CHILDREN else original(kind)
  with patch.object(f.resource,'getrusage',side_effect=usage):
   audit=f.SourceAudit()
   with self.assertRaisesRegex(ValueError,'without children'):audit.guard()

if __name__=='__main__':unittest.main(verbosity=2)
