from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import strong_control as c


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class StrongControlTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='strong-control-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();p=patch.object(c,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        self.basepins={}
        for i in range(206):self.basepins['inputs/p'+str(i)]=self.put('inputs/p'+str(i),'input'+str(i),raw=True)
        self.names=['f'+str(i) for i in range(41)]
        self.params=dict(loss_function='Logloss',iterations=300,depth=6,l2_leaf_reg=30,learning_rate=.05000000074505806,random_strength=1)
        identity=dict(fingerprints=self.basepins,feature_names=self.names,acceptance_refs=dict(train='inputs/p0',selection='inputs/p1',ablation='inputs/p2'),incumbent=dict(actual_model_parameters=dict(self.params,iterations=50)))
        self.run=digest(identity);self.d='artifacts/strong-baseline/'+self.run
        for key,value in [('RUN_ID',self.run),('PRODUCER',self.d)]:
            p=patch.object(c,key,value);p.start();self.addCleanup(p.stop)
        self.outputs={}
        for i in range(69):self.outputs[self.d+'/outputs/'+str(i)]=self.put(self.d+'/outputs/'+str(i),'saved'+str(i),raw=True)
        model,score=list(self.outputs)[:2]
        metrics={'conditional_macro_query':{'recall':.6,'ndcg':.45}}
        self.winner=dict(config_id='a'*64,incumbent=False,population=26000,trained_iterations=300,trees=150,depth=6,l2_leaf_reg=30,model_path=model,score_path=score,artifacts={model:self.outputs[model],score:self.outputs[score]},metrics=metrics)
        claim='claims/fit.json';execution='acceptance/execution.json';self.put(claim,{'fits':4});self.put(execution,{'approved':True})
        self.manifest=dict(run_id=self.run,identity=identity,outputs=self.outputs,budget_claim={'path':claim},execution_approval={'path':execution})
        self.put(self.d+'/run.json',self.manifest);self.put(self.d+'/plan.json',self.manifest);self.put(self.d+'/winner.json',self.winner)
        child=dict(exit_code=0,report=dict(status='complete_produced_unreviewed',outcome='arm_complete',feature_names=self.names,checkpoints=[self.winner],actual_model_parameters=self.params))
        self.report=dict(run_id=self.run,status='complete_produced_unreviewed',fit_attempt_count=4,actual_seen_looks=12,unknown_live_fit=False,winner=self.winner,feature_names=self.names,children=[child])
        self.put(self.d+'/report.json',self.report)
        original=dict(status='failed',run_id=self.run,fit_attempt_count=0,actual_parent_cpu_seconds=1.,actual_total_cpu_seconds=10.,seconds=12.,actual_reaped_children_cpu_seconds=9.)
        self.put(c.OLD+'/report.failed.json',original);self.put(c.OLD+'/report.json',dict(original,actual_parent_cpu_seconds=1.01,actual_total_cpu_seconds=10.01,seconds=12.01));self.put(c.OLD+'/verification.failed.json',dict(status='failed',run_id=self.run,fit_attempt_count=0))
        for n in ['verification-request.json','verification-context.json','verification.log','verification.json.attempt']:self.put(c.OLD+'/'+n,{'preserved':True})
        request=c.RECOVERY+'/verification-request.json';context=c.RECOVERY+'/verification-context.json'
        self.put(request,{'request':'same original outputs'});allocation=dict(cpu_seconds=100,deadline_monotonic=1000.,rss_bytes=7*2**30);self.put(context,{'allocation':allocation})
        finalpins={n:self.hash(n) for n in [request,context,*[c.OLD+'/'+n for n in ['report.json','report.failed.json','verification.failed.json','verification-request.json','verification-context.json','verification.log','verification.json.attempt']]]}
        for i in range(6):name='recovery-pins/'+str(i);finalpins[name]=self.put(name,'reviewed'+str(i),raw=True)
        evidence=dict(status='verified',observer_refits=0,saved_prefixes_replayed=12,successful_new_arms=4,allocated_new_arms=4,all_four_estimands_recomputed=True,full300_prefix_equivalence=True,winner={k:self.winner[k] for k in ['config_id','incumbent','population','trained_iterations','trees','depth','l2_leaf_reg','metrics']},proof_limits='reviewed historical receipt proof; actual fit weights not recovered from CBM')
        verification=dict(run_id=self.run,status='verified',fit_attempt_count=0,reaped_children_cpu_seconds=0,evidence=evidence,context_sha256=self.hash(context),request_sha256=self.hash(request),producer_manifest=dict(path=self.d+'/run.json',sha256=self.hash(self.d+'/run.json')),producer_report=dict(path=self.d+'/report.json',sha256=self.hash(self.d+'/report.json')),allocation=allocation,finished_monotonic=950.)
        self.put(c.RECOVERY+'/verification.json',verification)
        self.owner=dict(run_id=self.run,status='recovery_verified_pending_external_acceptance',producer_calls=0,verifier_calls=1,fit_attempt_count=0,labels_reserved_opened=False,final_source_pins=finalpins,verification_sha256=self.hash(c.RECOVERY+'/verification.json'),actual_new_total_cpu_seconds=20.,parent_peak_rss_bytes=1024,finished_monotonic=960.)
        self.put(c.RECOVERY+'/report.json',self.owner)
        external=dict(version=1,status='verified_full_lifetime',exit_code=0,run_id=self.run,owner_report=dict(path=c.RECOVERY+'/report.json',sha256=self.hash(c.RECOVERY+'/report.json')),verification=dict(path=c.RECOVERY+'/verification.json',sha256=self.hash(c.RECOVERY+'/verification.json')),actual_cpu_seconds=20.1,wall_seconds=25.,conservative_study_actual_cpu_seconds=40.,cumulative_original_verification_cpu_seconds=30.,original_absolute_deadline_monotonic=1001.,process_peak_rss_bytes=1024)
        self.put(c.RECOVERY+'/external-lifetime.json',external)
        for n in ['verification.log','external-lifetime.log']:self.put(c.RECOVERY+'/'+n,'exit0 reviewed',raw=True)
        for n in c.PROOFS:self.put(n,dict(run_id=self.run,status='accepted_development_control',actual_new_recovery_fits=0) if n.endswith('.json') else 'Immutable reviewed proof',raw=not n.endswith('.json'))
        pins={**self.basepins,**self.outputs,**finalpins}
        refs=[self.d+'/'+n for n in ['run.json','report.json','plan.json','winner.json']]+[claim,execution]+[c.RECOVERY+'/'+n for n in ['report.json','verification.json','verification.log','external-lifetime.log','external-lifetime.json']]+list(c.PROOFS)
        pins.update({n:self.hash(n) for n in refs});assert len(pins)==304
        selected={k:self.winner[k] for k in c.SELECTED if k!='scoring_prefix'};selected['scoring_prefix']=150
        self.acceptance=dict(version=1,approved=True,scope='reviewed_strong_baseline_control',run_id=self.run,selected_spec=selected,fingerprints=pins)
        self.path=self.root/'acceptance.json';self.anchor=patch.object(c,'ACCEPTANCE_SHA256','');self.anchor.start();self.addCleanup(self.anchor.stop);self.seal()
    def put(self,name,value,raw=False):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value if raw else json.dumps(value,sort_keys=True)+'\n');return self.hash(name)
    def hash(self,name):return hashlib.sha256((self.root/name).read_bytes()).hexdigest()
    def seal(self):
        self.put('acceptance.json',self.acceptance);c.ACCEPTANCE_SHA256=self.hash('acceptance.json')
    def mutate_receipt(self,name,value):
        self.acceptance['fingerprints'][name]=self.put(name,value);self.seal()
    def test_exact_closure_returns_raw_selected_child_and_trained_prefix_separately(self):
        result=c.verify_control(self.path)
        self.assertEqual(result['selected_spec']['trained_iterations'],300);self.assertEqual(result['selected_spec']['scoring_prefix'],150)
        self.assertEqual(result['actual_model_parameters'],self.params);self.assertIs(type(result['actual_model_parameters']['l2_leaf_reg']),int)
        self.assertEqual(result['feature_names'],self.names);self.assertEqual(len(result['pins']),304)
    def test_new_fresh_hash_cannot_replace_external_acceptance_anchor(self):
        self.acceptance['selected_spec']['scoring_prefix']=50;self.put('acceptance.json',self.acceptance)
        with self.assertRaisesRegex(ValueError,'Unreviewed historical'):c.verify_control(self.path)
    def test_bool_approval_and_extra_acceptance_field_rejected_even_with_test_anchor(self):
        self.acceptance['approved']=1;self.seal()
        with self.assertRaisesRegex(ValueError,'scope'):c.verify_control(self.path)
        self.acceptance['approved']=True;self.acceptance['new_fit']=True;self.seal()
        with self.assertRaisesRegex(ValueError,'schema'):c.verify_control(self.path)
    def test_same_size_missing_required_pin_and_unrelated_replacement_rejected(self):
        del self.acceptance['fingerprints'][c.PROOFS[1]];self.acceptance['fingerprints']['unrelated']=self.put('unrelated','text',raw=True);self.seal()
        with self.assertRaisesRegex(ValueError,'proof|closure'):c.verify_control(self.path)
    def test_known_failed_marker_rejects_before_streaming_model_or_source(self):
        self.put(c.RECOVERY+'/verification.failed.json',{'status':'failed'})
        with patch.object(c,'_sha',side_effect=AssertionError('streamed prior to failure')):
            with self.assertRaisesRegex(ValueError,'Known failed'):c.verify_control(self.path)
    def test_selected_spec_and_checkpoint_population_mismatch_rejected(self):
        self.acceptance['selected_spec']['population']=6000;self.seal()
        with self.assertRaisesRegex(ValueError,'Selected procedure'):c.verify_control(self.path)
    def test_original_failure_tail_may_only_increase_three_counters(self):
        name=c.OLD+'/report.json';body=json.loads((self.root/name).read_text());body['actual_reaped_children_cpu_seconds']=8.;self.mutate_receipt(name,body)
        with self.assertRaisesRegex(ValueError,'failed history'):c.verify_control(self.path)
    def test_guard_and_path_confinement_precede_streaming(self):
        def stop():raise TimeoutError('expired')
        with self.assertRaisesRegex(TimeoutError,'expired'):c.verify_control(self.path,check=stop)
        self.acceptance['fingerprints']['../outside']=self.acceptance['fingerprints'].pop('inputs/p10');self.seal()
        with self.assertRaisesRegex(ValueError,'Nonlocal'):c.verify_control(self.path)


if __name__=='__main__':unittest.main()
