"""Read-only independent engineering probes; tiny fixtures only, no native ML."""
from copy import deepcopy
import hashlib,json,io
from pathlib import Path
import tempfile,time,unittest,zipfile
from unittest.mock import patch
import numpy as np
from scripts import heldout_execution as x,heldout_worker_context as common
from tests import test_heldout_source_worker as sf
from tests import test_heldout_prediction_worker as pf
from tests import test_heldout_metric_worker as mf
from tests.oracles import heldout_source_worker as s,heldout_prediction_worker as p,heldout_metric_worker as m
ROOT=Path('/Users/mdpospelov/tlab-recsys-2026')
FREEZE=Path('/tmp/tlab-heldout-oracle-adapters-freeze-v2.json')

class Independent(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
  for module in [s,p,m,common]:
   q=patch.object(module,'ROOT',self.root);q.start();self.addCleanup(q.stop)
 def test_source_receipt_input_omission_fresh_reseal_stops_before_raw_connection(self):
  f=sf.Fixture(self.root);receipt=json.loads((self.root/f.refs['source_receipt']['path']).read_text());receipt['inputs'].pop('registry');f.refs['source_receipt']=f.write(f.refs['source_receipt']['path'],receipt);run=sf.FakeRole(f,s,'source_oracle')
  with patch.object(s,'open_connection',side_effect=AssertionError('raw/source row ingress')),self.assertRaisesRegex(ValueError,'input map'):s.perform(run)
  self.assertFalse(run.finished)
 def test_npz_bool_zero_shape_is_not_integer_and_rejects_before_allocation(self):
  f=pf.PredictionFixture(self.root);run=sf.FakeRole(f,p,'prediction_oracle');day=f.prediction['days'][-1];desc=deepcopy(day['predictions']['B']);self.assertEqual(day['candidate_count'],0)
  path=self.root/desc['artifact']['path']
  with zipfile.ZipFile(path) as z:parts={name:z.read(name) for name in z.namelist()}
  raw=io.BytesIO();np.lib.format.write_array_header_1_0(raw,dict(descr='<f8',fortran_order=False,shape=(False,)));parts['scores.npy']=raw.getvalue()
  with zipfile.ZipFile(path,'w') as z:
   for name,value in parts.items():z.writestr(name,value)
  desc['artifact']=f.reference(desc['artifact']['path']);run=sf.FakeRole(f,p,'prediction_oracle')
  with patch.object(np,'load',side_effect=AssertionError('unsafe allocation')),self.assertRaisesRegex(ValueError,'BEFORE allocation'):p.saved_npz(run,desc,day)
 def observed_metric(self,f):
  original=m.open_connection;ingress=[]
  def open_connection(*args,**kwargs):
   con,scratch=original(*args,**kwargs)
   class Observed:
    def __getattr__(self,key):return getattr(con,key)
    def execute(self,sql,*args,**kwargs):
     if 'full-targets.parquet' in sql or 'SELECT q.query_id,e.product_id FROM heldout_raw_events e' in sql:
      ingress.append(sql);raise AssertionError('unexpected private row ingress')
     return con.execute(sql,*args,**kwargs)
   return Observed(),scratch
  return open_connection,ingress
 def test_last_day_decoder_failure_blocks_both_produced_and_raw_target_rows(self):
  f=mf.MetricFixture(self.root);run=sf.FakeRole(f,m,'metric_oracle');saved=m.saved_npz;opener,ingress=self.observed_metric(f)
  def last_fail(execution,descriptor,day):
   if day['anchor'].startswith('2019-10-31'):raise ValueError('last-day decoder fixture')
   return saved(execution,descriptor,day)
  with patch.object(m,'open_connection',side_effect=opener),patch.object(m,'saved_npz',side_effect=last_fail),self.assertRaisesRegex(ValueError,'last-day'):m.perform(run)
  self.assertEqual(ingress,[]);self.assertFalse(run.finished)
 def test_same_utc_second_oracle_admission_rejects_before_private_rows(self):
  f=mf.MetricFixture(self.root);run=sf.FakeRole(f,m,'metric_oracle');seal=json.loads((self.root/f.refs['target_execution']['path']).read_text())['sealed_at'];opener,ingress=self.observed_metric(f)
  with patch.object(m,'open_connection',side_effect=opener),patch.object(m,'utc_now',return_value=seal),self.assertRaisesRegex(ValueError,'opening must follow'):m.perform(run)
  self.assertEqual(ingress,[])
 def test_float_equal_bigint_private_ranking_is_not_exact_integer(self):
  f=mf.MetricFixture(self.root);ref=f.evaluation['private_outputs']['rankings'];path=self.root/ref['path'];rows=path.read_text().splitlines();first=json.loads(rows[0]);first['user_id']=float(first['user_id']);rows[0]=json.dumps(first);path.write_text('\n'.join(rows)+'\n')
  ref=f.reference(ref['path']);f.evaluation['private_outputs']['rankings']=ref;f.evaluation['outputs'][ref['path']]=ref['sha256'];f.refs['evaluation_manifest']=f.write(f.refs['evaluation_manifest']['path'],f.evaluation)
  receipt=json.loads((self.root/f.refs['evaluation_receipt']['path']).read_text());receipt['outputs'][ref['path']]=ref['sha256'];receipt['outputs'][f.refs['evaluation_manifest']['path']]=f.refs['evaluation_manifest']['sha256'];f.refs['evaluation_receipt']=f.write(f.refs['evaluation_receipt']['path'],receipt);run=sf.FakeRole(f,m,'metric_oracle')
  with self.assertRaisesRegex(ValueError,'private-ranking'):m.perform(run)
  self.assertFalse(run.finished)
 def test_original_evidence_sha_crosses_real_shared_finalizer(self):
  f=sf.Fixture(self.root);fake=sf.FakeRole(f,s,'source_oracle');context=fake.context;prefix=str(Path(fake.reference['path']).parent);context.update(output_path=prefix+'/receipt.json',failed_path=prefix+'/report.failed.json')
  budget=common.RoleBudget(dict(cpu_seconds=900,deadline_monotonic=time.monotonic()+30,rss_bytes=7*2**30),time.monotonic())
  run=common.RoleExecution(context,fake.reference,fake.consumed,fake.pins,budget,f.directory);original=x.exclusive
  def mutate(path,body):
   saved=original(path,body)
   if Path(path).name=='evidence.json':
    changed=deepcopy(body);changed['core']['labels_loaded']=True;Path(path).write_text(x.canonical(changed)+'\n')
   return saved
  with patch.object(x,'counters',return_value=(1.,0.,2**20)),patch.object(run,'environment',return_value={'explicit_synthetic_environment':True}),patch.object(x,'exclusive',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed'):s.perform(run)
  self.assertTrue((self.root/context['failed_path']).exists());self.assertFalse((self.root/context['output_path']).exists())

def check_freeze():
 body=json.loads(FREEZE.read_text())
 for name,meta in body['files'].items():
  raw=(ROOT/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==meta['sha256'],name;assert len(raw)==meta['bytes'];assert not any(line.rstrip()!=line for line in raw.splitlines()),name
 for name,sha in body['accepted_core_helper_hashes_unchanged'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name

if __name__=='__main__':
 check_freeze();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Independent);result=unittest.TextTestRunner(verbosity=2).run(suite);check_freeze();raise SystemExit(0 if result.wasSuccessful() else 1)
