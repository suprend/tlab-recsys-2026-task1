"""Synthetic authority/lifecycle fixtures; never use actual inputs or native APIs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import heldout_execution as x
from scripts import heldout_worker_context as w


class Fixture:
    def __init__(self,root):
        self.root=root
        def file(name,body):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(body if type(body) is bytes else (x.canonical(body)+'\n').encode())
            return dict(path=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.file=file;started=time.monotonic()-1
        names=set(x.ENTRY.values())|{'scripts/heldout_worker_context.py','scripts/heldout_execution.py','scripts/heldout_contract.py','scripts/run_heldout_reporting.py','uv.lock','pyproject.toml'}
        code={name:file(name,b'# isolated synthetic code\n')['sha256'] for name in names}
        lock=file('fixture/lock.json',{'synthetic':True});choice=file('fixture/choice.json',{'synthetic':True})
        inputs={name:file('fixture/'+name+'.json',{'synthetic':name}) for name in ['source','pool','registry']}
        authority_paths={name:'artifacts/acceptance/'+name+'.json' for name in w.GATE_SCOPES}
        request=file('fixture/request.json',dict(version=1,scope='prospective_reserved_reporting_owner',owner_source=dict(path='scripts/run_heldout_reporting.py',sha256=code['scripts/run_heldout_reporting.py']),policy=lock,model_acceptance=choice,compute_evidence=lock,code_fingerprints=code,role_entries={role:dict(path=x.ENTRY[role],sha256=code[x.ENTRY[role]]) for role in x.ROLES},authority_paths=authority_paths,source_inputs=inputs))
        directory='artifacts/heldout-study/synthetic-attempt'
        claim=file('artifacts/heldout-study/owner.claim.json',dict(version=1,scope='reserved_reporting_owner_attempt',request=request,owner_source=dict(path='scripts/run_heldout_reporting.py',sha256=code['scripts/run_heldout_reporting.py']),output_directory=directory,started_monotonic=started,original_deadline_monotonic=started+x.LIMITS['wall_seconds']))
        pins=dict(code);pins.update({ref['path']:ref['sha256'] for ref in [lock,choice,request,claim,*inputs.values()]})
        identity=dict(version=1,scope='frozen_reserved_reporting_identity',request=request,owner_claim=claim,choice='R2',lock=lock,authenticated_choice=choice,source_inputs=inputs,original_limits=x.LIMITS,role_caps=x.CAPS,fingerprints=pins,selected_extra_schema=[],source_formula_scope='synthetic',refits=0,adaptation=False)
        run=x.digest(identity);proposal_ref=file(directory+'/proposal.json',dict(run_id=run,identity=identity));pins=deepcopy(pins);pins[proposal_ref['path']]=proposal_ref['sha256']
        plan=dict(run_id=run,choice='R2',fingerprints=pins)
        self.session=x.Session(root,directory,plan,request,claim,x.Budget(started=started))
        initial=dict(version=1,approved=True,scope='reserved_source_inference_execution',run_id=run,fingerprints=pins)
        grant=file(authority_paths['initial_execution'],initial);self.session.record_gate('initial_execution',grant,expected=initial)
        self.issued=self.session.issue('source',dict(lock=lock,choice=choice,**inputs));self.path=root/self.issued['context_ref']['path'];self.sha=self.issued['context_ref']['sha256']
    def begin(self):return w.begin_role(self.path,self.sha,'source',time.monotonic())
    def outputs(self,execution):
        outputs={name:self.file(name,{'synthetic_output':name})['sha256'] for name in execution.context['expected_outputs']}
        name=next(name for name in outputs if name.endswith('source-manifest.json'))
        return outputs,dict(path=name,sha256=outputs[name])


class Admission(unittest.TestCase):
    _saved_fence = w.RoleBudget.install_cpu_fence
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        for obj,name,value in [(w,'ROOT',self.root),(x,'counters',lambda:(1.0,0.0,2**20)),(w.RoleBudget,'install_cpu_fence',lambda obj:setattr(obj,'kernel_cpu',{'soft':899,'hard':900})),(w.RoleBudget,'start_monitor',lambda obj:None)]:
            context=patch.object(obj,name,value);context.start();self.addCleanup(context.stop)
        self.f=Fixture(self.root)
    def test_issued_role_consumption_and_original_authority_pins(self):
        run=self.f.begin();self.assertEqual(run.context['authorities'],self.f.session.gates);self.assertEqual(run.role,'source')
        body,_=x.read(self.root/run.consumed['path']);self.assertEqual(body['context'],self.f.issued['context_ref']);run.verify_pins()
        self.assertIn(self.f.issued['launch_ref']['path'],run.pins);self.assertIn(self.f.issued['slot_ref']['path'],run.pins)
    def test_same_context_repeat_stops_before_paid_hash(self):
        self.f.begin()
        with patch.object(x,'sha',side_effect=AssertionError('repeat paid stream')),self.assertRaises(FileExistsError):self.f.begin()
    def test_context_original_issuer_sha_prevents_fresh_reseal(self):
        body,_=x.read(self.f.path);body['allocation']['cpu_seconds']=800;self.f.path.write_text(x.canonical(body))
        with self.assertRaisesRegex(ValueError,'Parent-issued'):self.f.begin()
        self.assertFalse((self.f.path.parent/'execution.consumed.json').exists())
    def test_durable_launch_slot_substitution_rejected_before_consumption(self):
        path=self.root/self.f.issued['launch_ref']['path'];body,_=x.read(path);body['original_slot']['allocation']['cpu_seconds']=800;path.write_text(x.canonical(body))
        with self.assertRaisesRegex(ValueError,'Durable launch'):self.f.begin()
        self.assertFalse((self.f.path.parent/'execution.consumed.json').exists())
    def test_returned_snapshots_do_not_alias_original_authorities(self):
        run=self.f.begin();run.context['allocation']['cpu_seconds']=100000;run.pins.clear();run.reference['path']='evil';run.consumed.clear()
        run.budget.allocation['cpu_seconds']=100000;self.assertEqual(run.context['allocation']['cpu_seconds'],900);run.verify_pins()
    def test_observed_nonzero_descendant_counter_is_rejected(self):
        with patch.object(x,'counters',return_value=(1.0,.125,2**20)),self.assertRaisesRegex(ValueError,'descendants'):self.f.begin()
        self.assertFalse((self.f.path.parent/'execution.consumed.json').exists())
    def test_cpu_fence_setup_failure_is_consumed_and_persisted(self):
        with patch.object(w.RoleBudget,'install_cpu_fence',side_effect=OSError('fixture fence')),self.assertRaises(OSError):self.f.begin()
        self.assertTrue((self.f.path.parent/'execution.consumed.json').exists());self.assertTrue((self.f.path.parent/'report.failed.json').exists())
    def test_successful_receipt_keeps_fixed_outputs_and_cannot_finalize_twice(self):
        run=self.f.begin();outputs,evidence=self.f.outputs(run);body=run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
        self.assertEqual(body['status'],'role_complete_unaccepted');self.assertEqual(body['outputs'],outputs)
        with patch.object(x,'sha',side_effect=AssertionError('repeat paid stream')),self.assertRaisesRegex(ValueError,'already consumed'):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
        with self.assertRaisesRegex(ValueError,'Consumed'):run.input_json('choice')
    def test_bad_finish_input_also_stops_and_persists_failure(self):
        run=self.f.begin()
        with self.assertRaisesRegex(ValueError,'Fixed role output'):run.finish({},dict(path='bad',sha256='0'*64),native_prediction_count=0,labels_loaded=False)
        self.assertTrue((self.f.path.parent/'report.failed.json').exists())
        with self.assertRaisesRegex(ValueError,'already consumed'):run.finish({}, {},native_prediction_count=0,labels_loaded=False)
    def test_output_mutation_during_receipt_persistence_rejects(self):
        run=self.f.begin();outputs,evidence=self.f.outputs(run);original=x.exclusive
        def mutate(path,body):
            result=original(path,body)
            if Path(path).name=='receipt.json':(self.root/evidence['path']).write_text('changed fixture')
            return result
        with patch.object(x,'exclusive',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed'):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
        self.assertTrue((self.f.path.parent/'report.failed.json').exists())
    def test_authority_mutation_during_receipt_persistence_rejects(self):
        run=self.f.begin();outputs,evidence=self.f.outputs(run);original=x.exclusive
        def mutate(path,body):
            result=original(path,body)
            if Path(path).name=='receipt.json':(self.root/self.f.issued['context']['authorities']['initial_execution']['path']).write_text('changed authority')
            return result
        with patch.object(x,'exclusive',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed'):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
        self.assertTrue((self.f.path.parent/'report.failed.json').exists())
    def test_last_guard_failed_marker_cannot_promote_receipt(self):
        run=self.f.begin();outputs,evidence=self.f.outputs(run);original=run.budget.guard
        def guard():
            original()
            if (self.f.path.parent/'receipt.json').exists():(self.f.path.parent/'evidence.failed.json').write_text('{}')
        with patch.object(run.budget,'guard',side_effect=guard),self.assertRaisesRegex(ValueError,'failed role'):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
    def test_original_failure_is_preserved_when_failure_writer_also_fails(self):
        run=self.f.begin();error=RuntimeError('original fixture')
        with patch.object(x,'exclusive',side_effect=OSError('secondary writer')):run.fail(error)
        self.assertIn('OSError',str(error.__notes__));self.assertEqual(str(error),'original fixture')
    def test_consumed_terminal_role_cannot_repeat_paid_verify(self):
        run=self.f.begin();run.fail(RuntimeError('fixture'))
        with patch.object(x,'sha',side_effect=AssertionError('repeat hash')),self.assertRaisesRegex(ValueError,'Consumed role'):run.verify_pins()

    def test_fresh_issuer_context_still_requires_exact_proposal_projection(self):
        body,_=x.read(self.f.path);extra=self.f.file('fixture/extra.json',{})
        body['plan']['fingerprints'][extra['path']]=extra['sha256']
        initial=body['authorities']['initial_execution'];gate,_=x.read(self.root/initial['path']);gate['fingerprints']=body['plan']['fingerprints']
        body['authorities']['initial_execution']=self.f.file(initial['path'],gate)
        self.f.path.write_text(x.canonical(body)+'\n');self.f.sha=hashlib.sha256(self.f.path.read_bytes()).hexdigest()
        launch_path=self.root/self.f.issued['launch_ref']['path'];launch,_=x.read(launch_path)
        launch['argv'][-1]=self.f.sha;launch['issued_context_sha256']=self.f.sha;launch['context']['sha256']=self.f.sha
        launch_path.write_text(x.canonical(launch)+'\n')
        with self.assertRaisesRegex(ValueError,'projection differs'):self.f.begin()
        self.assertFalse((self.f.path.parent/'execution.consumed.json').exists())
    def test_environment_compares_loaded_installed_and_locked_versions(self):
        from types import SimpleNamespace
        run=self.f.begin();versions=dict(numpy='1',pandas='2',duckdb='3',catboost='4')
        raw='\n'.join('[[package]]\nname = "'+name+'"\nversion = "'+version+'"' for name,version in versions.items()).encode()
        (self.root/'uv.lock').write_bytes(raw);run._pins['uv.lock']=hashlib.sha256(raw).hexdigest()
        with patch.object(w.importlib,'import_module',side_effect=lambda name:SimpleNamespace(__version__=versions[name])),patch.object(w.importlib.metadata,'version',side_effect=lambda name:versions[name]):
            result=run.environment();self.assertEqual(result['packages'],versions);self.assertFalse(result['subprocess_probe']);self.assertEqual(result['kernel_cpu']['hard'],900)
        with patch.object(w.importlib,'import_module',return_value=SimpleNamespace(__version__='wrong')),patch.object(w.importlib.metadata,'version',return_value='wrong'),self.assertRaisesRegex(ValueError,'uv.lock'):run.environment()
    def test_fence_readback_failure_rejects(self):
        run=w.RoleBudget(dict(cpu_seconds=20,deadline_monotonic=time.monotonic()+10,rss_bytes=7*2**30),time.monotonic())
        # Patch shadows the admission fixture's no-op install method explicitly.
        original=type(self)._saved_fence
        with patch.object(w.resource,'getrlimit',side_effect=[(w.resource.RLIM_INFINITY,w.resource.RLIM_INFINITY),(20,20)]),patch.object(w.resource,'setrlimit'),self.assertRaisesRegex(ValueError,'readback'):
            original(run)

    def test_receipt_byte_mutation_during_persistence_cannot_return_success(self):
        run=self.f.begin();outputs,evidence=self.f.outputs(run);original=x.exclusive
        def mutate(path,body):
            result=original(path,body)
            if Path(path).name=='receipt.json':
                changed=deepcopy(body);changed['process_cpu_seconds']=.5;Path(path).write_text(x.canonical(changed)+'\n')
            return result
        with patch.object(x,'exclusive',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed'):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
        self.assertTrue((self.f.path.parent/'report.failed.json').exists())
    def test_nested_original_pin_is_retained_before_stream_and_repinned_after_write(self):
        run=self.f.begin();ref=self.f.file('fixture/nested.json',{'unaccepted_synthetic':True});mapping={ref['path']:ref['sha256']};original=x.sha
        def inspect(path,check=lambda:None):
            if Path(path)==self.root/ref['path']:self.assertEqual(run.pins[ref['path']],ref['sha256'])
            return original(path,check)
        with patch.object(x,'sha',side_effect=inspect):run.retain_pins(mapping)
        mapping.clear();outputs,evidence=self.f.outputs(run);writer=x.exclusive
        def mutate(path,body):
            result=writer(path,body)
            if Path(path).name=='receipt.json':(self.root/ref['path']).write_text('changed nested')
            return result
        with patch.object(x,'exclusive',side_effect=mutate),self.assertRaisesRegex(ValueError,'changed'):run.finish(outputs,evidence,native_prediction_count=0,labels_loaded=False)
    def test_nested_pin_conflict_rejects_before_any_paid_stream(self):
        run=self.f.begin();name=next(iter(run.pins));before=run.pins
        with patch.object(x,'sha',side_effect=AssertionError('conflict paid hash')),self.assertRaisesRegex(ValueError,'Conflicting'):run.retain_pins({name:'f'*64})
        self.assertEqual(run.pins,before)
    def test_nested_retention_after_terminal_denied_before_stream(self):
        run=self.f.begin();run.fail(RuntimeError('fixture'))
        with patch.object(x,'sha',side_effect=AssertionError('terminal paid hash')),self.assertRaisesRegex(ValueError,'Consumed role'):run.retain_pins({'fixture/new':'0'*64})


class Budget(unittest.TestCase):
    def create(self):return w.RoleBudget(dict(cpu_seconds=20,deadline_monotonic=time.monotonic()+10,rss_bytes=7*2**30),time.monotonic())
    def test_absolute_cpu_wall_rss_and_persistent_expiry(self):
        for values,kind in [((19.,0.,2**20),TimeoutError),((1.,0.,7*2**30+1),MemoryError),((1.,.1,2**20),ValueError)]:
            run=self.create()
            with patch.object(x,'counters',return_value=values),self.assertRaises(kind):run.guard()
        run=self.create();run.expired.set();run.reason=TimeoutError('persistent')
        with patch.object(x,'counters',return_value=(0.,0.,1)),self.assertRaisesRegex(TimeoutError,'persistent'):run.guard()
    def test_fence_exact_setup_readback_and_inherited_limit(self):
        run=self.create()
        with patch.object(w.resource,'getrlimit',side_effect=[(w.resource.RLIM_INFINITY,w.resource.RLIM_INFINITY),(19,20)]),patch.object(w.resource,'setrlimit') as setter:
            self.assertEqual(run.install_cpu_fence(),{'soft':19,'hard':20});setter.assert_called_once_with(w.resource.RLIMIT_CPU,(19,20))
        with patch.object(w.resource,'getrlimit',return_value=(10,10)),self.assertRaisesRegex(ValueError,'Inherited'):run.install_cpu_fence()
    def test_monitor_expiry_interrupts_watched_engine(self):
        class Connection:
            def __init__(self):self.interrupted=False
            def interrupt(self):self.interrupted=True
        run=self.create();con=Connection();run.connections.append(con)
        with patch.object(run,'check_values',side_effect=TimeoutError('fixture')):
            run.start_monitor();self.assertTrue(run.expired.wait(1));run.stop()
        self.assertTrue(con.interrupted)

    def test_real_unix_cpu_fence_readback_in_isolated_tiny_child(self):
        # A synthetic helper/API probe, not a data/model worker or hard-cap proof.
        import subprocess
        import sys
        code="from scripts import heldout_worker_context as w; import time,json; b=w.RoleBudget(dict(cpu_seconds=20,deadline_monotonic=time.monotonic()+10,rss_bytes=7*2**30),time.monotonic()); print(json.dumps(b.install_cpu_fence())); b.guard()"
        child=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=3,cwd=Path(w.__file__).resolve().parents[1])
        self.assertEqual(child.returncode,0,child.stderr);self.assertEqual(json.loads(child.stdout),{'soft':19,'hard':20})


if __name__=='__main__':unittest.main()
