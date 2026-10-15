from copy import deepcopy
from pathlib import Path
import hashlib,json,tempfile,unittest
from unittest.mock import patch
from scripts import feature_program_control as c


def setup(root):
 d='artifacts/synthetic-model';names=['f'+str(i) for i in range(41)];params=dict(loss_function='Logloss',depth=6,l2_leaf_reg=30,iterations=300,task_type='CPU')
 def write(name,body):
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(c.h.canonical(body)+'\n');return dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 def reference(name):return dict(path=name,sha256=hashlib.sha256((root/name).read_bytes()).hexdigest())
 required=['inputs/B.cbm','inputs/oracle.py','inputs/ownerclaim.json','inputs/control.json','inputs/source.json','inputs/selector.json','configs/features/automation-pool.json']
 inp={n:write(n,dict(synthetic=n))['sha256'] for n in required}
 for j in range(374-len(inp)):
  n=f'inputs/{j:03d}.json';inp[n]=write(n,dict(synthetic=j))['sha256']
 wpath=d+'/workers/R2/prefix.cbm';extra=['auto1','auto2','auto3'];delta=[dict(name=n,dtype='BIGINT') for n in extra]
 spec=dict(candidate_id='R2',bundle_id='L05',model=None,scores=None,feature_names=names+extra,population=26000,trained_iterations=300,scoring_prefix=300,depth=6,l2_leaf_reg=30,physical_delta=delta,native_effective_parameters=params)
 winner=dict(candidate_id='R2',model_path=wpath,feature_names=names+extra)
 ident=dict(fingerprints=inp,slots={'R2':dict(bundle_id='L05',feature_names=names+extra,physical_delta=delta)},
            baseline=dict(model_path='inputs/B.cbm'),feature_names=names,native_reference=params,
            control_acceptance='inputs/control.json',source_acceptance='inputs/source.json',selector_path='inputs/selector.json')
 rid=c.h.digest(ident)
 out={}
 out[d+'/winner.json']=write(d+'/winner.json',winner)['sha256'];out[d+'/plan.json']=write(d+'/plan.json',dict(synthetic=True))['sha256'];out[wpath]=write(wpath,dict(not_a_native_model=True))['sha256']
 children=[]
 for cid in ['I1','I2','R1','R2']:
  n=d+'/workers/'+cid+'/report.json';out[n]=write(n,dict(synthetic=True))['sha256'];children.append(dict(report=reference(n),worker_report=dict(candidate_id=cid)))
 for j in range(46-len(out)):
  n=d+f'/outputs/{j:03d}.json';out[n]=write(n,dict(synthetic=j))['sha256']
 manifest=dict(run_id=rid,identity=ident,outputs=out);write(d+'/run.json',manifest)
 producer=dict(run_id=rid,fit_attempt_count=4,sum_metric_looks=4,active_slot=None,unknown_live_fit=False,unknown_metric_looks=False,heldout_labels_opened=False,winner=winner);write(d+'/producer-report.json',producer)
 write(d+'/proposal.json',dict(run_id=rid,identity=ident))
 observer=dict(run_id=rid,status='verified',fit_attempt_count=0,observer_refits=0,source_regenerations=0,checked_slots=['I1','I2','R1','R2'])
 eref=write(d+'/observer/evidence.json',observer)
 authority={d+'/run.json':reference(d+'/run.json')['sha256'],d+'/producer-report.json':reference(d+'/producer-report.json')['sha256'],'inputs/oracle.py':inp['inputs/oracle.py'],'inputs/ownerclaim.json':inp['inputs/ownerclaim.json'],eref['path']:eref['sha256']}
 for n in ['context','request','once','launch','consumed','approval','claim']:
  key=d+'/observer/'+n+'.json';authority[key]=write(key,dict(synthetic=n))['sha256']
 assert len(authority)==12
 report=dict(run_id=rid,status='model_outputs_verified_pending_external_acceptance',fit_attempt_count=4,sum_metric_looks=4,observer_calls=1,
             active_slot=None,unknown_live_fit=False,unknown_metric_looks=False,heldout_labels_opened=False,winner=winner,children=children,observer=dict(evidence=eref,authority_pins=authority))
 rref=write(d+'/report.json',report)
 life=dict(owner_report=rref,explicitly_reaped_exit_code=0,production_and_oracle_cpu_upper_seconds=1694.75,charged_owner_wall_upper_seconds=882.31,conservative_job_peak_rss_bytes=1000)
 lref=write(d+'/external-lifetime.json',life);admission=dict(total_study_with_admission_cpu_upper_seconds=1704.75,refits=0,oracle_retries=0);aref=write(d+'/external-admission.json',admission)
 write(d+'/external-time.log',dict(synthetic_time_only=True))
 for n in c.PROOFS:write(n,dict(synthetic_proof=True))
 extra_keys=[d+'/'+n for n in ['proposal.json','run.json','report.json','producer-report.json','winner.json','external-time.log','external-lifetime.json','external-admission.json']]+c.PROOFS
 fps=c._merge(inp,out,authority,{n:reference(n)['sha256'] for n in extra_keys});assert len(fps)==438
 spec['model']=reference(wpath);spec['scores']=reference(d+'/outputs/000.json')
 a=dict(version=1,approved=True,scope=c.SCOPE,run_id=rid,fingerprints=fps,selected_spec=spec,external_lifetime=lref,external_admission=aref,proof_limits='Synthetic authority mechanics only',heldout_targets_opened=False,source_failed_invocation_preserved=True)
 ap='artifacts/acceptance/synthetic.json';af=write(ap,a)
 return dict(root=root,d=d,a=a,path=root/ap,sha=af['sha256'],run_id=rid,write=write,reference=reference,manifest=manifest,report=report,life=life)


class ChoiceConsumer(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.f=setup(Path(self.tmp.name).resolve());self.root=self.f['root']
  for name,value in [('ROOT',self.root),('ACCEPTANCE_SHA256',self.f['sha']),('RUN_ID',self.f['run_id'])]:
   p=patch.object(c,name,value);p.start();self.addCleanup(p.stop)
 def verify(self,**kw):return c.verify_choice(self.f['path'],**kw)
 def reseal_acceptance(self):c.ACCEPTANCE_SHA256=self.f['write']('artifacts/acceptance/synthetic.json',self.f['a'])['sha256']
 def test_exact438_returns_only_frozen_B_W_authority_no_model_API(self):
  result=self.verify();ch=result['authenticated_choice'];self.assertEqual(ch['candidate_id'],'R2');self.assertEqual(len(ch['models']['B']['feature_names']),41);self.assertEqual(len(ch['models']['W']['feature_names']),44);self.assertEqual(len(result['pins']),439);self.assertFalse(result['model_prediction_replay'])
 def test_changed_acceptance_not_new_authority(self):
  self.f['a']['approved']=False;self.f['write']('artifacts/acceptance/synthetic.json',self.f['a'])
  with self.assertRaisesRegex(ValueError,'anchor'):self.verify()
 def test_missing_proof_replaced_with_extra_same_count_rejects(self):
  a=self.f['a'];a['fingerprints'].pop(c.PROOFS[0]);a['fingerprints']['unrelated.json']='a'*64;self.reseal_acceptance()
  with self.assertRaises(ValueError):self.verify()
 def test_missing_known_failure_marker_never_supplies_choice(self):
  for name in ['report.failed.json','observer/evidence.failed.json','workers/I1/report.failed.json','logs/I2.log.cleanup-failed.json']:
   p=self.root/self.f['d']/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
   with self.assertRaises(ValueError):self.verify()
   p.unlink()
 def test_guard_before_metadata_and_first_paid_hash(self):
  with self.assertRaises(TimeoutError):self.verify(check=lambda:(_ for _ in ()).throw(TimeoutError('prepaid stop')))
  with patch.object(c,'_pins',side_effect=TimeoutError('stream sentinel')):
   with self.assertRaisesRegex(TimeoutError,'stream sentinel'):self.verify()
 def test_changed_input_detected_by_full_stream(self):
  (self.root/'inputs/001.json').write_text('changed')
  with self.assertRaisesRegex(ValueError,'changed'):self.verify()
 def test_late_acceptance_mutation_and_late_worker_marker_reject(self):
  original=c._pins
  for kind in ['authority','marker']:
   def paid(mapping,check):
    original(mapping,check)
    if len(mapping)==438:
     if kind=='authority':self.f['path'].write_text(self.f['path'].read_text()+' ')
     else:(self.root/self.f['d']/'workers/I1/report.failed.json').write_text('{}')
   with patch.object(c,'_pins',side_effect=paid):
    with self.assertRaises(ValueError):self.verify()
   if kind=='authority':self.f['write']('artifacts/acceptance/synthetic.json',self.f['a'])
 def test_bool_version_rejected_even_when_fixture_authority_reanchored(self):
  self.f['a']['version']=True;self.reseal_acceptance()
  with self.assertRaises(ValueError):self.verify()
 def test_escaped_symlink_and_noncanonical_local_paths_reject(self):
  outside=Path(self.tmp.name).parent/'not-in-choice-project.json'
  with self.assertRaises((ValueError,FileNotFoundError)):c._local('../'+outside.name)
  p=self.root/'escape.json';p.symlink_to('/dev/null')
  with self.assertRaises(ValueError):c._local('escape.json')
 def test_new_scope_or_targets_opened_cannot_relabel_history(self):
  for name,value in [('scope','some_other_scope'),('heldout_targets_opened',True),('source_failed_invocation_preserved',False)]:
   before=self.f['a'][name];self.f['a'][name]=value;self.reseal_acceptance()
   with self.assertRaises(ValueError):self.verify()
   self.f['a'][name]=before

if __name__=='__main__':unittest.main()
