from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest,json,hashlib,importlib.util,time,contextlib,io
import duckdb
import tests.test_feature_program_collection as fixture_module
from scripts import feature_program_collection as source
from scripts import feature_program_source_recovery as recovery
from scripts.protocol_manifest import canonical_json,sha256_file
PROJECT=Path(source.__file__).resolve().parents[1]
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixture_module.CollectionTests(methodName='test_real_tiny_selected_union_preservesB_and_allQ_noY_relation')
  with patch.object(fixture_module,'EVENTS',fixture_module.EVENTS[:-1]):self.fixture.setUp()
  self.addCleanup(self.fixture.doCleanups)
  # Oracle inputs32 =8events+6acceptedQ+4C+4oldB+6exportQ+4newF. Keep emptyC Q and
  # outside-candidate events; avoid inflating a nominal tiny fixture.
  con=duckdb.connect()
  try:
   for role in ['train','selection']:
    for kind in ['candidates','features']:
     path=self.fixture.root/self.fixture.collections[role]['refs'][kind][0]
     con.execute('CREATE OR REPLACE TABLE filtered AS SELECT * FROM read_parquet(?) WHERE product_id=10',[str(path)])
     temp=self.fixture.root/(role+'-'+kind+'-filtered.parquet');con.execute('COPY filtered TO ?(FORMAT PARQUET)',[str(temp)]);path.write_bytes(temp.read_bytes())
     self.fixture.plan['identity']['fingerprints'][str(path.relative_to(self.fixture.root))]=sha256_file(path)
  finally:con.close()
  t=self.fixture;self.root=t.root;self.script=self.root/'scripts/feature_program_collection.py';self.script.parent.mkdir();self.script.write_bytes((PROJECT/'scripts/feature_program_collection.py').read_bytes())
  t.plan['identity']['base_feature_columns']=[n for n,typ in t.plan['identity']['base_feature_columns']]
  t.plan['identity']['fingerprints']['scripts/feature_program_collection.py']=recovery.ORIGINAL_CODE
  t.plan['run_id']=hashlib.sha256(canonical_json(t.plan['identity']).encode()).hexdigest()
  t.approval.write_text(canonical_json(dict(version=1,approved=True,scope=source.ROLE,run_id=t.plan['run_id'],fingerprints=t.plan['identity']['fingerprints'])))
  with patch.object(source,'inspect_physical',side_effect=duckdb.OutOfMemoryException('max_temp_directory_size final wide inspection')):
   with self.assertRaises(duckdb.OutOfMemoryException):t.produce()
  self.directory=t.directory();self.manifest=source._read_json(self.directory/'run.json');self.report=source._read_json(self.directory/'report.json');run=self.manifest['run_id']
  self.prefix=dict(version=1,status='verified_failed_source_lifetime',scope='failed_source_lifetime_only_no_formula_acceptance',run_id=run,producer=dict(exit_code=1,actual_cpu_seconds=self.report['process_cpu_user_system_seconds']+.01,actual_cpu_upper_seconds=self.report['process_cpu_user_system_seconds']+.02,wall_seconds=self.report['seconds']+.01,peak_rss_bytes=self.report['process_peak_rss_bytes'],manifest=self.ref(self.directory/'run.json'),report=self.ref(self.directory/'report.json')))
  self.prefixpath=self.root/'failed-lifetime.json';self.prefixpath.write_text(canonical_json(self.prefix))
  self.entry=self.root/'tests/oracles/feature_program_recovery_audit.py';self.entry.parent.mkdir(parents=True);self.entry.write_bytes((PROJECT/'tests/oracles/feature_program_recovery_audit.py').read_bytes())
  self.admission=self.root/'scripts/feature_program_source_recovery.py';self.admission.write_bytes((PROJECT/'scripts/feature_program_source_recovery.py').read_bytes())
  self.owner=self.root/'scripts/run_feature_source_recovery.py';self.owner.write_text('# synthetic owner only\n')
  self.boundary=dict(old_source_cpu_upper_seconds=self.prefix['producer']['actual_cpu_upper_seconds'],old_source_active_wall_seconds=self.prefix['producer']['wall_seconds'],owner_and_oracle_cpu_seconds=792,owner_and_oracle_wall_seconds=1044,original_source_cpu_cap=900,original_source_wall_cap=1200,original_oracle_cpu_cap=900,original_oracle_wall_cap=1200,shared_study_cpu_cap=7200,original_absolute_deadline='unavailable_not_reconstructed',failure_consumes_oracle=True)
  pins={a['path']:a['sha256'] for ds in self.manifest['outputs'].values() for d in ds for a in d['artifacts'].values()}
  self.policy=dict(version=1,approved=True,scope=recovery.POLICY_SCOPE,run_id=run,owner_source=self.ref(self.owner),oracle_source=self.ref(self.entry),producer_manifest=self.prefix['producer']['manifest'],producer_report=self.prefix['producer']['report'],failed_lifetime_receipt=self.ref(self.prefixpath),source_claim=self.manifest['source_claim'],boundary=self.boundary,fingerprints=pins)
  for name in ['owner_source','oracle_source','producer_manifest','producer_report','failed_lifetime_receipt','source_claim']:
   v=self.policy[name];pins[v['path']]=v['sha256']
  pins['scripts/feature_program_collection.py']=recovery.ORIGINAL_CODE;pins['scripts/feature_program_source_recovery.py']=sha256_file(self.admission);pins['scripts/strong_baseline.py']=sha256_file(PROJECT/'scripts/strong_baseline.py')
  (self.root/'scripts/strong_baseline.py').write_bytes((PROJECT/'scripts/strong_baseline.py').read_bytes())
  self.policyfile=self.root/'policy.json';self.policyfile.write_text(canonical_json(self.policy))
  for obj,name,value in [(recovery,'ROOT',self.root),(recovery,'__file__',str(self.admission)),(source,'__file__',str(self.script))]:
   p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
 def ref(self,p):return dict(path=str(p.relative_to(self.root)),sha256=sha256_file(p))
 def test_only_failed_cost_and_declared_map_admitted_no_source_proof(self):
  out=recovery.validate_failed_source(self.manifest,self.report,self.prefix);self.assertEqual((out['queries'],out['pairs'],out['days']),(6,4,2));self.assertEqual(recovery.validate_policy(self.policy,self.manifest,self.report,self.prefix),self.boundary)
 def test_other_stage_or_partial_outputs_or_fit_cannot_recover(self):
  for target,key,value in [(self.report,'fit_attempt_count',1),(self.report,'labels_loaded',True),(self.report['stages'][-1],'stage','compile'),(self.report['stages'][0],'status','failed')]:
   old=target[key];target[key]=value
   try:
    with self.assertRaises(ValueError):recovery.validate_failed_source(self.manifest,self.report,self.prefix)
   finally:target[key]=old
  changed=deepcopy(self.manifest);changed['outputs']['train']=[]
  with self.assertRaises(ValueError):recovery.validate_failed_source(changed,self.report,self.prefix)
 def test_real_name_transport_and_bad_physical_names(self):
  self.assertTrue(all(type(n) is str for n in self.manifest['identity']['base_feature_columns']))
  bad=deepcopy(self.manifest);bad['identity']['base_feature_columns'][0]='unknown';bad['run_id']=hashlib.sha256(canonical_json(bad['identity']).encode()).hexdigest();r=deepcopy(self.report);r['run_id']=bad['run_id']
  with self.assertRaisesRegex(ValueError,'B45'):recovery.validate_failed_source(bad,r,self.prefix)
 def test_failed_lifetime_lowerbounds_and_unknown_usage(self):
  for name,value in [('actual_cpu_seconds',0),('wall_seconds',0),('peak_rss_bytes',1),('exit_code',0)]:
   bad=deepcopy(self.prefix);bad['producer'][name]=value
   with self.assertRaises(ValueError):recovery.validate_failed_source(self.manifest,self.report,bad)
 def test_policy_cannot_expand_clock_cpu_or_remove_output_pin(self):
  for name,value in [('owner_and_oracle_cpu_seconds',900),('owner_and_oracle_wall_seconds',1200),('original_absolute_deadline',12345),('failure_consumes_oracle',False)]:
   bad=deepcopy(self.policy);bad['boundary'][name]=value
   with self.assertRaises(ValueError):recovery.validate_policy(bad,self.manifest,self.report,self.prefix)
  bad=deepcopy(self.policy);bad['fingerprints'].pop(next(iter(bad['fingerprints'])))
  with self.assertRaises(ValueError):recovery.validate_policy(bad,self.manifest,self.report,self.prefix)
 def reseal_failed_outputs(self):
  self.report['phases']={role:dict(status='complete_produced_unreviewed',queries=sum(d['artifacts']['queries']['rows'] for d in ds),pairs=sum(d['artifacts']['features']['rows'] for d in ds),days=ds) for role,ds in self.manifest['outputs'].items()}
  for name,body in [('run.json',self.manifest),('report.json',self.report)]:
   (self.directory/name).write_text(canonical_json(body))
  self.prefix['producer'].update(manifest=self.ref(self.directory/'run.json'),report=self.ref(self.directory/'report.json'));self.prefixpath.write_text(canonical_json(self.prefix))
  self.policy.update(producer_manifest=self.prefix['producer']['manifest'],producer_report=self.prefix['producer']['report'],failed_lifetime_receipt=self.ref(self.prefixpath))
  for ds in self.manifest['outputs'].values():
   for d in ds:
    for a in d['artifacts'].values():self.policy['fingerprints'][a['path']]=a['sha256']
  for name in ['producer_manifest','producer_report','failed_lifetime_receipt']:
   ref=self.policy[name];self.policy['fingerprints'][ref['path']]=ref['sha256']
  self.policyfile.write_text(canonical_json(self.policy))
 def test_legal_wrong_selected_count_fresh_reseal_rejected_by_raw_oracle(self):
  a=self.manifest['outputs']['train'][0]['artifacts']['features'];path=self.root/a['path'];con=duckdb.connect()
  try:
   con.execute('CREATE TABLE changed AS SELECT * FROM read_parquet(?)',[str(path)]);con.execute('UPDATE changed SET auto_pair_view_count_24h=auto_pair_view_count_24h+1');other=self.root/'altered.parquet';con.execute('COPY changed TO ?(FORMAT PARQUET)',[str(other)])
  finally:con.close()
  path.write_bytes(other.read_bytes());a.update(sha256=sha256_file(path),bytes=path.stat().st_size);self.reseal_failed_outputs()
  with self.assertRaisesRegex(ValueError,'source formulas'):self.run_oracle()
  failed=self.root/'artifacts/feature-program-source-oracle/synthetic/evidence.failed.json';self.assertEqual(json.loads(failed.read_text())['status'],'failed')
 def test_original_once_claim_full_contract_rejected_after_fresh_reseal(self):
  path=self.root/self.manifest['source_claim']['path'];body=json.loads(path.read_text());body['source_wall_allocation']=999;path.write_text(canonical_json(body));ref=self.ref(path)
  self.manifest['source_claim']=ref;self.report['source_claim']=ref;self.policy['source_claim']=ref;self.policy['fingerprints'][ref['path']]=ref['sha256'];self.reseal_failed_outputs()
  with self.assertRaisesRegex(ValueError,'once-claim contract'):self.run_oracle()
 def test_missing_admission_or_original_code_pin_rejected_before_helper_execution(self):
  for name in ['scripts/feature_program_source_recovery.py','scripts/feature_program_collection.py','scripts/strong_baseline.py']:
   bad=deepcopy(self.policy);bad['fingerprints'].pop(name)
   with self.assertRaises(ValueError):recovery.validate_policy(bad,self.manifest,self.report,self.prefix)
 def run_oracle(self):
  run=self.manifest['run_id'];directory=self.root/'artifacts/feature-program-source-oracle/synthetic';directory.mkdir(parents=True)
  shared=dict(limit_cpu_seconds=7200,charged_prefix_cpu_seconds=self.boundary['old_source_cpu_upper_seconds'],unknown_cost=False,source_parent_receipt=self.ref(self.prefixpath));policyref=self.ref(self.policyfile)
  request=dict(scope=recovery.ORACLE_SCOPE,run_id=run,producer_manifest=self.policy['producer_manifest'],producer_report=self.policy['producer_report'],oracle_source=self.policy['oracle_source'],shared_budget=shared,recovery_policy=policyref)
  requestpath=directory/'request.json';requestpath.write_text(canonical_json(request));allocation=dict(cpu_seconds=760,deadline_monotonic=time.monotonic()+60,rss_bytes=7*2**30)
  context=dict(version=1,scope=recovery.ORACLE_SCOPE,run_id=run,project_root=str(self.root),invocation_directory=str(directory.relative_to(self.root)),request=self.ref(requestpath),oracle_execution_approval=policyref,producer_manifest=self.policy['producer_manifest'],producer_report=self.policy['producer_report'],oracle_source=self.policy['oracle_source'],allocation=allocation,shared_budget=shared,issued_at_monotonic=time.monotonic(),output_path=str((directory/'evidence.json').relative_to(self.root)),failed_output_path=str((directory/'evidence.failed.json').relative_to(self.root)),recovery_policy=policyref)
  contextpath=directory/'context.json';contextpath.write_text(canonical_json(context));issued=sha256_file(contextpath)
  claim=self.root/'artifacts/feature-program-study/independent-oracle.claim.json';claim.write_text(canonical_json(dict(version=1,scope='once_only_selected12_source_oracle',run_id=run,allowed_observer_attempts=1,allowed_source_calculations=0,allowed_fit_attempts=0,policy=policyref,invocation_directory=context['invocation_directory'])))
  sp=importlib.util.spec_from_file_location('fixture_recovery_oracle',self.entry);o=importlib.util.module_from_spec(sp);sp.loader.exec_module(o)
  (directory/'report.json').write_text(canonical_json(dict(status='oracle_running',run_id=run,producer_calls=0,oracle_calls=1,fit_attempt_count=0,oracle_launch=dict(issued_context_sha256=issued,allocation=allocation,argv=[__import__('sys').executable,str(self.entry),'--context',str(contextpath),'--issued-context-sha256',issued]))))
  with patch.object(source.compiler,'create_manual_features',side_effect=AssertionError('Producer regeneration forbidden')):
   with contextlib.redirect_stdout(io.StringIO()):result=o.Audit(contextpath,issued).run()
  return result,directory
 def test_actual_tiny_unused_oracle_no_regeneration_source_and_physical_fullproof(self):
  old_report=(self.directory/'report.json').read_bytes();result,directory=self.run_oracle()
  self.assertTrue(result['formula_values_complete']);self.assertEqual(result['checked_pairs'],4);self.assertEqual(result['checked_scalar_values'],48);self.assertEqual(result['source_recovery']['original_producer_status'],'failed');self.assertFalse(result['source_recovery']['producer_regenerated']);self.assertEqual((self.directory/'report.json').read_bytes(),old_report)
  self.assertFalse((directory/'evidence.failed.json').exists())
if __name__=='__main__':unittest.main()
