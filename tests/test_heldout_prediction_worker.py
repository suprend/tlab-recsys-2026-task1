"""Synthetic NPZ/fake-native adapter tests; no native model/prediction/fit."""
from copy import deepcopy
from datetime import datetime,timedelta
import json,struct,zipfile,io
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import duckdb,numpy as np
from scripts import heldout_execution as x,heldout_contract as h
from tests import test_heldout_source_worker as fixtures
from tests.oracles import heldout_prediction_worker as m

class PredictionFixture(fixtures.Fixture):
 def __init__(self,root,choice_name='B'):
  super().__init__(root,choice_name);self.native_calls=[]
  modelrefs={}
  for side in ('B','W'):
   modelref=self.lock['models'][side]['model'];path=root/modelref['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic no-native CBM placeholder');modelrefs[side]=self.reference(modelref['path']);self.lock['models'][side]['model']=deepcopy(modelrefs[side])
  self.choice['models']=deepcopy(self.lock['models']);self.refs['lock']=self.write(self.refs['lock']['path'],self.lock);self.refs['choice']=self.write(self.refs['choice']['path'],self.choice)
  self.source['decision_lock']=self.refs['lock'];self.source['choice']=self.refs['choice'];self.refs['source_manifest']=self.write(self.refs['source_manifest']['path'],self.source)
  outputs={};days=[];epoch=datetime(1970,1,1);con=duckdb.connect(':memory:')
  try:
   for original in self.source['days']:
    q=con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM read_parquet(?) ORDER BY query_id',[str(root/original['queries']['path'])]).fetchall();lookup={r[0]:i for i,r in enumerate(q)}
    c=con.execute('SELECT query_id,product_id,from_popular FROM read_parquet(?) ORDER BY query_id,product_id',[str(root/original['candidates']['path'])]).fetchall()
    arrays=dict(query_ids=np.asarray([r[0] for r in q],dtype='U64'),user_ids=np.asarray([r[1] for r in q],dtype=np.int64),anchors=np.asarray([(r[2]-epoch)//timedelta(microseconds=1) for r in q],dtype=np.int64),calendar_maturity=np.asarray([r[3] for r in q],dtype=np.bool_),group=np.asarray([lookup[r[0]] for r in c],dtype=np.int32),items=np.asarray([r[1] for r in c],dtype=np.int64),scores=np.asarray([float(r[2]) for r in c],dtype=np.float64))
    descriptors={}
    for side in ('B','W'):
     stem='B' if choice_name=='B' else side;name=self.directory+'/predictions/day-'+original['anchor'][8:10]+'/'+stem+'.npz';path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
     sidearrays=dict(arrays);sidearrays['scores']=arrays['scores']+(0.5 if side=='W' and choice_name!='B' else 0.0);np.savez(path,**sidearrays);ref=self.reference(name);outputs[name]=ref['sha256']
     descriptors[side]=dict(artifact=ref,model=modelrefs[side],rows=len(c),queries=len(q),scoring_prefix=300,feature_names=self.lock['models'][side]['feature_names'])
    day=deepcopy(original);day['predictions']=descriptors;days.append(day)
  finally:con.close()
  calls=sum(d['candidate_count']>0 for d in days)*(1 if choice_name=='B' else 2)
  body=dict(version=1,scope='unaccepted_reserved_predictions',run_id=self.run,decision_lock=self.refs['lock'],choice=self.refs['choice'],source_acceptance=self.refs['source_acceptance'],source_manifest=self.refs['source_manifest'],created_at=(h.utc(self.lock['sealed_at'])+timedelta(seconds=2)).strftime('%Y-%m-%dT%H:%M:%SZ'),days=days,outputs=outputs,labels_loaded=False,fit_attempt_count=0,native_prediction_count=calls,environment={'synthetic_versions':True});self.prediction=body
  self.refs['prediction_manifest']=self.write(self.directory+'/predictions/prediction-manifest.json',body);allout=dict(outputs);allout[self.refs['prediction_manifest']['path']]=self.refs['prediction_manifest']['sha256']
  self.refs['prediction_receipt']=self.write(self.directory+'/predictions/receipt.json',dict(status='role_complete_unaccepted',scope='reserved_reporting_predictions',role='predictions',run_id=self.run,inputs={k:self.refs[k] for k in ['lock','choice','source_acceptance','source_manifest']},outputs=allout,labels_loaded=False,fit_attempt_count=0,native_prediction_count=calls))
 def native(self):
  f=self;spec=deepcopy(self.lock['models']['B'])
  class Model:
   tree_count_=300;feature_names_=spec['feature_names']
   def load_model(self,path):
    side='W' if Path(path).resolve()==(f.root/f.lock['models']['W']['model']['path']).resolve() and f.lock['choice']!='B' else 'B'
    self.side=side;self.feature_names_=f.lock['models'][side]['feature_names'];return self
   def get_all_params(self):return deepcopy(spec['effective_parameters'])
   def get_cat_feature_indices(self):return []
   def get_text_feature_indices(self):return []
   def get_embedding_feature_indices(self):return []
   def predict(self,a,**kw):f.native_calls.append(kw);return np.asarray(a[:,0]+(0.5 if getattr(self,'side','B')=='W' else 0.0),dtype=np.float64)
  return Model()

class PredictionWorker(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);p=patch.object(m,'ROOT',self.root);p.start();self.addCleanup(p.stop);self.f=PredictionFixture(self.root);self.r=fixtures.FakeRole(self.f,m,'prediction_oracle')
 def test_whole7_independent_core_with_fake_native_exact_reuse_and_private_strip(self):
  with patch('catboost.CatBoostClassifier',side_effect=self.f.native):result=m.perform(self.r)
  expected=sum(d['candidate_count']>0 for d in self.f.source['days']);self.assertEqual(len(self.f.native_calls),expected);self.assertEqual(result['native_prediction_count'],expected);self.assertFalse(result['labels_loaded'])
  evidence=json.loads((self.root/result['evidence']['path']).read_text());self.assertEqual(len(evidence['core']['days']),7);self.assertNotIn('private_replayed_scores',json.dumps(evidence));self.assertTrue(all(k==dict(prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2) for k in self.f.native_calls))
 def test_nonB_exact_chosen3_two_fake_native_calls_per_nonempty_day(self):
  self.tmp_other=tempfile.TemporaryDirectory();self.addCleanup(self.tmp_other.cleanup);self.root=Path(self.tmp_other.name).resolve();m.ROOT=self.root;self.f=PredictionFixture(self.root,'I1');self.r=fixtures.FakeRole(self.f,m,'prediction_oracle')
  with patch('catboost.CatBoostClassifier',side_effect=self.f.native):result=m.perform(self.r)
  self.assertEqual(result['native_prediction_count'],2*sum(d['candidate_count']>0 for d in self.f.source['days']));self.assertEqual(len(self.f.native_calls),result['native_prediction_count'])
 def descriptor(self):return self.f.prediction['days'][0]['predictions']['B'],self.f.prediction['days'][0]
 def rewrite(self,transform):
  descriptor,day=self.descriptor();path=self.root/descriptor['artifact']['path']
  with np.load(path,allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
  transform(arrays);np.savez(path,**arrays);descriptor['artifact']=self.f.reference(descriptor['artifact']['path']);self.r._pins=deepcopy(self.f.pins)
  return descriptor,day
 def test_exact_bigint_and_anchor_microseconds_transport(self):
  d,day=self.descriptor();body=m.saved_npz(self.r,d,day);self.assertIn(fixtures.BIG,[q[1] for q in body['queries']]);second=self.f.prediction['days'][1];later=m.saved_npz(self.r,second['predictions']['B'],second);self.assertIn(fixtures.BIG,later['items'].tolist());self.assertTrue(all(q[2]==datetime(2019,10,25) for q in body['queries']))
 def test_huge_declared_header_shape_rejects_BEFORE_numpy_load(self):
  d,day=self.descriptor();path=self.root/d['artifact']['path']
  with zipfile.ZipFile(path) as archive:members={n:archive.read(n) for n in archive.namelist()}
  raw=members['scores.npy'];version=raw[6:8];width=2 if version==b'\x01\x00' else 4;length=int.from_bytes(raw[8:8+width],'little');header=raw[8+width:8+width+length].decode('latin1');header=header.replace(str(day['candidate_count'])+',','999999999999,');encoded=header.encode('latin1');members['scores.npy']=raw[:8]+len(encoded).to_bytes(width,'little')+encoded
  with zipfile.ZipFile(path,'w') as archive:
   for key,value in members.items():archive.writestr(key,value)
  d['artifact']=self.f.reference(d['artifact']['path']);self.r._pins=deepcopy(self.f.pins)
  with patch.object(np,'load',side_effect=AssertionError('allocation must not happen')),self.assertRaisesRegex(ValueError,'BEFORE allocation'):m.saved_npz(self.r,d,day)
 def test_object_dtype_wrong_int_transport_and_nonfinite_reject(self):
  for key,value in [('items',lambda n:np.zeros(n,dtype=np.float64)),('query_ids',lambda n:np.zeros(n,dtype=object)),('scores',lambda n:np.full(n,np.inf,dtype=np.float64))]:
   # Restore fixture each variant; all raw source fixtures have only3 events.
   if key!='items':self.tmp2=tempfile.TemporaryDirectory();self.addCleanup(self.tmp2.cleanup);self.root=Path(self.tmp2.name);m.ROOT=self.root;self.f=PredictionFixture(self.root);self.r=fixtures.FakeRole(self.f,m,'prediction_oracle')
   d,day=self.rewrite(lambda a:a.update({key:value(len(a[key]))}))
   with self.assertRaises(ValueError):m.saved_npz(self.r,d,day)
 def test_duplicate_zip_member_and_payload_truncation_reject(self):
  d,day=self.descriptor();path=self.root/d['artifact']['path']
  with zipfile.ZipFile(path,'a') as z:
   import warnings
   with warnings.catch_warnings():warnings.simplefilter('ignore');z.writestr('scores.npy',b'x')
  d['artifact']=self.f.reference(d['artifact']['path']);self.r._pins=deepcopy(self.f.pins)
  with self.assertRaisesRegex(ValueError,'unique seven'):m.saved_npz(self.r,d,day)
 def test_bad_native_effective_params_or_score_drift_stops(self):
  model=self.f.native();model.tree_count_=299
  with patch('catboost.CatBoostClassifier',return_value=model),self.assertRaisesRegex(ValueError,'Native tree'):m.perform(self.r)
  self.assertFalse(self.r.finished);self.assertEqual(self.f.native_calls,[])
 def test_changed_model_bytes_after_fake_predict_rejected_after_close(self):
  model=self.f.native();original=model.predict
  def changed(a,**kw):
   scores=original(a,**kw);(self.root/self.f.lock['models']['B']['model']['path']).write_bytes(b'late change');return scores
  model.predict=changed
  with patch('catboost.CatBoostClassifier',return_value=model),self.assertRaisesRegex(ValueError,'bytes changed'):m.perform(self.r)
  self.assertFalse(self.r.finished)
 def test_truncated_member_payload_rejected_BEFORE_numpy_load(self):
  d,day=self.descriptor();path=self.root/d['artifact']['path']
  with zipfile.ZipFile(path) as z:members={n:z.read(n) for n in z.namelist()}
  members['scores.npy']=members['scores.npy'][:-1]
  with zipfile.ZipFile(path,'w') as z:
   for n,v in members.items():z.writestr(n,v)
  d['artifact']=self.f.reference(d['artifact']['path']);self.r._pins=deepcopy(self.f.pins)
  with patch.object(np,'load',side_effect=AssertionError('must not allocate')),self.assertRaisesRegex(ValueError,'payload size'):m.saved_npz(self.r,d,day)
 def test_wrong_source_manifest_output_path_rejected_before_model_load(self):
  bad=self.f.source;bad['days'][0]['queries']['path']='fixture/escape.parquet';self.f.refs['source_manifest']=self.f.write(self.f.refs['source_manifest']['path'],bad);self.r=fixtures.FakeRole(self.f,m,'prediction_oracle')
  with patch('catboost.CatBoostClassifier',side_effect=AssertionError('must not load')),self.assertRaisesRegex(ValueError,'destination'):m.perform(self.r)

if __name__=='__main__':unittest.main()
