"""Boundaries use tiny synthetic data/mocks; no new native model fits."""
from copy import deepcopy
import json
import contextlib
import io
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

from scripts import strong_baseline as s
from scripts import metadata_price_collection as c
from scripts import model_data as d
from scripts import train_baselines as b
import tests.test_train_baselines as bt
import numpy as np


def candidate(key,score,trees=50,depth=6,incumbent=False,recall=.6):
    return dict(config_id=key,trees=trees,depth=depth,incumbent=incumbent,
        metrics=dict(conditional_macro_query=dict(ndcg=score,recall=recall)))


class ChoiceTests(unittest.TestCase):
    def test_global_tie_set_not_pairwise_nontransitive_chain(self):
        items=[candidate('low',.5-1.5e-12,50,4),candidate('middle',.5-.75e-12,150,4),candidate('high',.5,300,6)]
        self.assertEqual(s.choose(items)['config_id'],'middle')
        self.assertEqual(s.choose(items[::-1])['config_id'],'middle')

    def test_exact_ties_trees_depth_incumbent_then_id(self):
        items=[candidate('z',.7,300,4),candidate('a',.7,50,6),candidate('b',.7,50,4),candidate('old',.7,50,4,True)]
        self.assertEqual(s.choose(items)['config_id'],'old')
        self.assertEqual(s.choose([candidate('b',.7,50,4),candidate('a',.7,50,4)])['config_id'],'a')

    def test_recall_floor_no_feasible_and_nonfinite(self):
        floor=s.specification()['policy']['recall_floor']
        self.assertEqual(s.choose([candidate('bad',1.,recall=floor-1e-12),candidate('good',.1,recall=floor)])['config_id'],'good')
        with self.assertRaisesRegex(ValueError,'No feasible'):s.choose([candidate('bad',1.,recall=0)])
        with self.assertRaisesRegex(ValueError,'Invalid'):s.choose([candidate('bad',float('nan'))])

    def test_config_is_closed_and_bool_not_int(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'grid.json';s.write(path,s.specification());s.load_spec(path)
            body=s.specification();body['version']=True;s.write(path,body)
            with self.assertRaisesRegex(ValueError,'frozen'):s.load_spec(path)
            body=s.specification();body['grid'].append({'depth':8,'l2_leaf_reg':3});s.write(path,body)
            with self.assertRaisesRegex(ValueError,'frozen'):s.load_spec(path)


class BudgetTests(unittest.TestCase):
    def test_canonical_parent_and_reaped_children_once(self):
        with patch.object(s,'self_cpu',return_value=40.),patch.object(s,'child_cpu',return_value=200.),patch.object(s,'rss',return_value=1),patch.object(s.time,'monotonic',return_value=100.):
            budget=s.Budget(s.specification(),started=50)
            self.assertEqual(budget.cpu(),240.)
            allowance=budget.allocation('arm')
            self.assertEqual(allowance['cpu_seconds'],3000)
            self.assertEqual(allowance['deadline_monotonic'],3270)
            self.assertEqual(budget.allocation('gate')['deadline_monotonic'],680)

    def test_expired_cpu_rss_and_nonmonotonic_are_not_fresh_budget(self):
        with patch.object(s,'self_cpu',return_value=3301.),patch.object(s,'child_cpu',return_value=0.),patch.object(s,'rss',return_value=1),patch.object(s.time,'monotonic',return_value=100.):
            budget=s.Budget(s.specification(),started=0)
            with self.assertRaisesRegex(TimeoutError,'actual CPU'):budget.guard()
        with patch.object(s,'self_cpu',return_value=0.),patch.object(s,'child_cpu',return_value=0.),patch.object(s,'rss',return_value=2**30+1):
            budget=s.Budget(s.specification(),started=time.monotonic())
            with self.assertRaisesRegex(MemoryError,'1GiB'):budget.guard()
            budget.self_started=1.
            with self.assertRaisesRegex(ValueError,'Nonmonotonic'):budget.cpu()


class ContextTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        self.addCleanup(patch.stopall)
        for module in [s,c]:patch.object(module,'ROOT',self.root).start()
        source=self.root/'source';source.write_text('bounded synthetic source')
        identity=dict(role=s.ROLE,spec=s.specification(),fingerprints={'source':s.sha(source)})
        self.parent=dict(run_id=s.digest(identity),identity=identity)
        self.directory=self.root/'artifacts/strong-baseline'/self.parent['run_id'];self.directory.mkdir(parents=True)
        execution=self.root/'execution.json'
        s.write(execution,dict(version=1,approved=True,scope=s.ROLE,run_id=self.parent['run_id'],fingerprints=identity['fingerprints']))
        ref=dict(path='execution.json',sha256=s.sha(execution))
        self.parent.update(execution_approval=ref,budget_claim=s.parent_claim(self.parent,ref,self.directory))
        s.write(self.directory/'plan.json',self.parent)
        budget=Mock();budget.allocation.return_value=dict(cpu_seconds=100,deadline_monotonic=time.monotonic()+60,rss_bytes=7*2**30)
        self.slot,self.context,self.issued=s.allocate_slot(self.directory,self.parent,'arm',0,6000,budget)

    def reseal_slot(self,body):
        context=s.read(self.context);s.write(s.local(context['slot_path']),body)
        context['slot_sha256']=s.sha(s.local(context['slot_path']));s.write(self.context,context);self.issued=s.sha(self.context)

    def test_exact_bound_context_and_reserved_three_looks(self):
        parent,slot,context=s.verify_worker_context(self.context,issued_context_sha256=self.issued)
        self.assertEqual(slot['look_reservations'],[50,150,300]);self.assertEqual(parent['run_id'],self.parent['run_id'])
        with self.assertRaises(FileExistsError):s.parent_claim(self.parent,self.parent['execution_approval'],self.directory)
        budget=Mock();budget.allocation.return_value=self.slot['allocation']
        with self.assertRaises(FileExistsError):s.allocate_slot(self.directory,self.parent,'arm',0,6000,budget)

    def test_resealed_semantic_slot_tampering_rejected(self):
        cases=[('population',True),('population',2000),('look_reservations',[50,300]),('output_root','elsewhere'),('token','invalid'),('index',True),('version',True)]
        for key,value in cases:
            body=deepcopy(self.slot);body[key]=value;self.reseal_slot(body)
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):s.verify_worker_context(self.context,issued_context_sha256=self.issued)
        self.reseal_slot(self.slot);s.verify_worker_context(self.context,issued_context_sha256=self.issued)

    def test_unapproved_or_modified_parent_source_fails_before_native_work(self):
        parent=deepcopy(self.parent);parent['identity']['spec']['version']=True
        s.write(self.directory/'plan.json',parent)
        with self.assertRaisesRegex(ValueError,'identity'):s.verify_worker_context(self.context,issued_context_sha256=self.issued)
        s.write(self.directory/'plan.json',self.parent)
        claim=s.read(s.local(s.CLAIM));claim['allowed_fit_attempts']=5;s.write(s.local(s.CLAIM),claim)
        with self.assertRaisesRegex(ValueError,'changed'):s.verify_worker_context(self.context,issued_context_sha256=self.issued)

    def test_oversized_or_boolean_worker_allowance_rejected(self):
        for key,value in [('cpu_seconds',3241),('cpu_seconds',True),('rss_bytes',True),('deadline_monotonic',True),('deadline_monotonic',time.monotonic()+10000)]:
            body=deepcopy(self.slot);body['allocation'][key]=value;self.reseal_slot(body)
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):s.verify_worker_context(self.context,issued_context_sha256=self.issued)


    def test_valid_range_reseal_cannot_replace_issuer_population_or_allowance(self):
        original=self.issued
        for field,value in [('population',26000),('allocation',dict(cpu_seconds=3240,deadline_monotonic=time.monotonic()+3500,rss_bytes=7*2**30))]:
            body=deepcopy(self.slot);body[field]=value;self.reseal_slot(body)
            with self.assertRaisesRegex(ValueError,'issuer launch digest'):
                s.verify_worker_context(self.context,issued_context_sha256=original)
        self.reseal_slot(self.slot);s.verify_worker_context(self.context,issued_context_sha256=self.issued)

    def test_floating_look_reservation_is_not_integer(self):
        body=deepcopy(self.slot);body['look_reservations']=[50.0,150,300];self.reseal_slot(body)
        with self.assertRaisesRegex(ValueError,'strict integers'):s.verify_worker_context(self.context,issued_context_sha256=self.issued)


    def test_launch_receipt_preserves_exact_issuer_args_and_cannot_be_replaced(self):
        log=self.directory/'logs/arm-0.log';log.parent.mkdir()
        expected=s.expected_worker(self.parent,self.slot,s.read(self.context),self.context)
        argv=[sys.executable,'-m','scripts.strong_baseline','--worker-context',s.relative(self.context),'--issued-context-sha256',self.issued]
        ref=s.record_launch(log,self.parent,self.slot,self.context,self.issued,expected,argv)
        receipt=s.read(s.local(ref['path']))
        self.assertEqual(ref['sha256'],s.sha(s.local(ref['path'])))
        self.assertEqual(receipt['argv'],argv);self.assertEqual(receipt['slot'],self.slot)
        self.assertEqual(receipt['issued_context_sha256'],self.issued);self.assertEqual(receipt['worker_run_id'],expected['run_id'])
        with self.assertRaises(FileExistsError):s.record_launch(log,self.parent,self.slot,self.context,self.issued,expected,argv)


class OwnedProcessTests(unittest.TestCase):
    def budget(self):
        budget=Mock();budget.limits=s.specification()['limits'];return budget

    def test_success_and_import_failure_are_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            allocation=dict(deadline_monotonic=time.monotonic()+5)
            self.assertEqual(s.run_process([sys.executable,'-c','print("ok")'],Path(tmp)/'ok.log',budget=self.budget(),allocation=allocation),0)
            code=s.run_process([sys.executable,'-c','import nonexistent_tlab_dependency'],Path(tmp)/'bad.log',budget=self.budget(),allocation=allocation)
            self.assertEqual(code,1);self.assertIn('ModuleNotFoundError',(Path(tmp)/'bad.log').read_text())

    def test_busy_ignores_TERM_then_KILL_and_reap(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'busy.log';code='import os,signal\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nprint(os.getpid(),flush=True)\nwhile True: pass'
            before=s.child_cpu()
            with self.assertRaisesRegex(TimeoutError,'absolute wall'):
                s.run_process([sys.executable,'-c',code],log,budget=self.budget(),allocation=dict(deadline_monotonic=time.monotonic()+.2),grace=.05,reap=.5)
            pid=int(log.read_text().strip())
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            self.assertGreater(s.child_cpu(),before)

    def test_log_cap_even_after_fast_exit_and_live_parent_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError,'log budget'):
                s.run_process([sys.executable,'-c','print("x"*20000)'],Path(tmp)/'log.log',budget=self.budget(),allocation=dict(deadline_monotonic=time.monotonic()+5),max_log=32)
            budget=self.budget();budget.guard.side_effect=TimeoutError('parent shared deadline')
            with self.assertRaisesRegex(TimeoutError,'parent shared'):
                s.run_process([sys.executable,'-c','import time;time.sleep(10)'],Path(tmp)/'wait.log',budget=budget,allocation=dict(deadline_monotonic=time.monotonic()+5),grace=.05,reap=.5)

    def test_cleanup_evidence_failure_preserves_primary(self):
        process=Mock();process.pid=123;process.poll.return_value=None;process.wait.side_effect=__import__('subprocess').TimeoutExpired('worker',.01)
        with tempfile.TemporaryDirectory() as tmp,patch.object(s.subprocess,'Popen',return_value=process),patch.object(s.os,'killpg'),patch.object(Path,'write_text',side_effect=OSError('disk failed')):
            budget=self.budget();budget.guard.side_effect=ValueError('primary integrity')
            with self.assertRaisesRegex(ValueError,'primary integrity') as caught:
                s.run_process(['synthetic'],Path(tmp)/'log',budget=budget,allocation=dict(deadline_monotonic=time.monotonic()+5),grace=.001,reap=.001)
            self.assertTrue(any('cleanup' in n.lower() for n in caught.exception.__notes__))


    def test_normal_leader_exit_with_surviving_descendant_is_failure_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'orphan.log'
            code='import subprocess,sys;child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);print(child.pid,flush=True)'
            with self.assertRaisesRegex(RuntimeError,'surviving owned-group descendants'):
                s.run_process([sys.executable,'-c',code],log,budget=self.budget(),allocation=dict(deadline_monotonic=time.monotonic()+5),grace=.1,reap=1)
            pid=int(log.read_text().strip())
            # launchd adopts/reaps an orphan; bounded cleanup must have stopped
            # it. A surviving zombie is unknown usage and is a failed marker,
            # never success. No unbounded wait or synthetic ML work here.
            deadline=time.monotonic()+1
            while time.monotonic()<deadline:
                try:os.kill(pid,0)
                except ProcessLookupError:break
                time.sleep(.02)
            else:self.assertTrue(Path(str(log)+'.cleanup-failed.json').exists())


    def test_parent_guard_failure_always_reaps_direct_child(self):
        native=s.subprocess.Popen;created=[]
        def spawn(*args,**kwargs):
            process=native(*args,**kwargs);created.append(process);return process
        with tempfile.TemporaryDirectory() as tmp,patch.object(s.subprocess,'Popen',side_effect=spawn):
            budget=self.budget();budget.guard.side_effect=ValueError('guard before first poll')
            with self.assertRaisesRegex(ValueError,'guard before first poll'):
                s.run_process([sys.executable,'-c','import time;time.sleep(30)'],Path(tmp)/'guard.log',budget=budget,
                    allocation=dict(deadline_monotonic=time.monotonic()+5),grace=.1,reap=1)
            self.assertEqual(len(created),1);self.assertIsNotNone(created[0].returncode)
            with self.assertRaises(ProcessLookupError):os.kill(created[0].pid,0)


class ParameterAndTerminalTests(unittest.TestCase):
    def test_fixed300_params_no_evalset_and_grid_only_changes(self):
        first=s.model_parameters({'depth':4,'l2_leaf_reg':30})
        self.assertEqual((first['iterations'],first['thread_count'],first['learning_rate']),(300,2,.05))
        self.assertNotIn('eval_set',first);self.assertFalse(first['use_best_model'])
        model=Mock();actual={**first,'border_count':254,'nan_mode':'Min','rsm':1}
        model.get_all_params.return_value=actual;s.validate_parameters(model,actual,{'depth':4,'l2_leaf_reg':30})
        other=deepcopy(actual);other['learning_rate']=.1;model.get_all_params.return_value=other
        with self.assertRaisesRegex(ValueError,'drift'):s.validate_parameters(model,actual,{'depth':4,'l2_leaf_reg':30})

    def test_saved_full_tree_and_no_CTR_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'full.json';body=dict(oblivious_trees=[dict(splits=[dict(split_type='FloatFeature')])]*300)
            s.write(path,body);s.validate_saved_full(path)
            body['oblivious_trees'][0]['splits'][0]['split_type']='OnlineCtr';s.write(path,body)
            with self.assertRaisesRegex(ValueError,'CTR'):s.validate_saved_full(path)
            s.write(path,dict(oblivious_trees=[]))
            with self.assertRaisesRegex(ValueError,'300trees'):s.validate_saved_full(path)

    def finalize(self,root,primary=None,write_error=None,guard_error=None):
        budget=Mock();budget.started=time.monotonic();budget.outer_deadline=time.monotonic()+100
        budget.limits=s.specification()['limits'];budget.cpu.return_value=10.
        if guard_error:budget.guard.side_effect=guard_error
        report=dict(status='complete_produced_unreviewed')
        if write_error:
            with patch.object(s,'write',side_effect=write_error):error=s.finalize_parent(root,report,budget,primary)
        else:error=s.finalize_parent(root,report,budget,primary)
        return error,report

    def test_terminal_writes_and_guard_cannot_leave_accepted_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);error,report=self.finalize(root)
            self.assertIsNone(error);self.assertEqual(report['status'],'complete_produced_unreviewed')
            error,report=self.finalize(root,write_error=OSError('persist failed'))
            self.assertIsInstance(error,OSError);self.assertEqual(report['status'],'failed');self.assertTrue((root/'report.failed.json').exists())
            self.assertEqual(json.loads((root/'report.failed.json').read_text())['status'],'failed')
            first=ValueError('body primary');error,report=self.finalize(root,primary=first,guard_error=TimeoutError('late deadline'))
            self.assertIs(error,first);self.assertTrue(any('late deadline' in n for n in first.__notes__))

    def test_resource_taxonomy_excludes_native_unknown_and_integrity(self):
        import duckdb
        for error in [MemoryError(),TimeoutError(),duckdb.OutOfMemoryException('out')]:self.assertTrue(s.resource_failure(error))
        for error in [ValueError(),RuntimeError('native'),OSError()]:self.assertFalse(s.resource_failure(error))


class WorkerBoundaryTests(ContextTests):
    def worker(self,*,prepare_error=None,late_error=None):
        # Return native-looking tiny arrays under a mocked query-population
        # boundary. Estimator is a mock: this performs zero CatBoost fits.
        base=bt.prepared();train=d.ModelData(base.queries+[('empty'+str(i),100+i,base.queries[0][2],frozenset()) for i in range(5,6000)],
            base.group,base.items,base.x,base.y,base.feature_names,None,[],{})
        selection=d.ModelData(base.queries+[('empty'+str(i),100+i,base.queries[0][2],frozenset()) for i in range(5,4000)],
            base.group,base.items,base.x,base.y,base.feature_names,None,[],{})
        parent=deepcopy(self.parent);parent['identity'].update(feature_names=base.feature_names,
            acceptance_refs=dict(train='train.json',selection='selection.json'),collection_ids=dict(train='train-id',selection='selection-id'),
            incumbent=dict(actual_model_parameters={**s.model_parameters({'depth':4,'l2_leaf_reg':3}),'border_count':254,'nan_mode':'Min','rsm':1}))
        # Rebuild the complete external scope after extending synthetic identity.
        parent['run_id']=s.digest(parent['identity']);parent['identity']['fingerprints']={}
        parent['run_id']=s.digest(parent['identity'])
        ref=parent['execution_approval'];s.write(s.local(ref['path']),dict(version=1,approved=True,scope=s.ROLE,run_id=parent['run_id'],fingerprints={}))
        ref['sha256']=s.sha(s.local(ref['path']));parent['budget_claim']['sha256']=s.sha(s.local(s.CLAIM))
        s.write(self.directory/'plan.json',parent)
        slot=deepcopy(self.slot);slot['parent_run_id']=parent['run_id'];self.reseal_slot(slot)
        context=s.read(self.context);self.synthetic_context=(parent,slot,context)
        events=[];model=Mock();model.tree_count_=300;model.feature_names_=base.feature_names
        model.get_all_params.return_value=parent['identity']['incumbent']['actual_model_parameters']
        def fit(*args,**kwargs):events.append('fit300')
        def predict(*args,**kwargs):
            events.append('predict'+str(kwargs.get('ntree_end','replay')))
            if late_error and kwargs.get('ntree_end')==150:raise late_error
            return np.zeros(len(base.items))
        def save(path,format=None):
            if format=='json':s.write(Path(path),dict(oblivious_trees=[dict(splits=[dict(split_type='FloatFeature')])]*300))
            else:Path(path).write_text('synthetic native model')
        model.fit.side_effect=fit;model.predict.side_effect=predict;model.save_model.side_effect=save
        def copy():
            clone=Mock();clone.save_model.side_effect=save
            return clone
        model.copy.side_effect=copy
        def loader():
            clone=Mock();clone.predict.side_effect=predict
            def load(path):clone.tree_count_=int(Path(path).stem.removeprefix('prefix'))
            clone.load_model.side_effect=load;return clone
        calls=iter([model,*[loader() for _ in range(3)]])
        collections={key:dict(plan=dict(collection_id=key+'-id')) for key in ['train','selection']}
        def collection(path,**kwargs):return collections[Path(path).stem]
        with (patch.object(s,'verify_worker_context',return_value=(parent,slot,context)),patch.object(s,'child_cpu',return_value=0),
            patch.object(c,'verify_pins'),patch.object(c,'verify_collection_strict',side_effect=collection),
            patch.object(d,'prepare_model_data',side_effect=prepare_error or [train,selection]),
            patch('catboost.Pool') as pool,patch('catboost.CatBoostClassifier',side_effect=lambda **kwargs:next(calls)) as native,
            contextlib.redirect_stdout(io.StringIO())):
            if prepare_error or late_error:
                with self.assertRaises(type(prepare_error or late_error)):s.worker_main(self.context,issued_context_sha256=self.issued)
                result=None
            else:result=s.worker_main(self.context,issued_context_sha256=self.issued)
        expected=s.expected_worker(parent,slot,context,self.context)
        directory=s.local(slot['output_root'])/expected['run_id']
        return result,s.read(directory/'report.json'),model,pool,native,events,directory

    def test_success_full300_before_three_prefixes_and_one_fit(self):
        result,report,model,pool,native,events,directory=self.worker()
        self.assertEqual(model.fit.call_count,1);self.assertNotIn('eval_set',model.fit.call_args.kwargs)
        self.assertEqual(events[0],'fit300');self.assertEqual([x['trees'] for x in report['checkpoints']],[50,150,300])
        self.assertEqual([x['trained_iterations'] for x in report['checkpoints']],[300]*3)
        self.assertEqual(report['fit_attempt_count'],1);self.assertEqual(pool.call_args.kwargs['thread_count'],2)
        self.assertEqual(report['status'],'complete_produced_unreviewed')
        with patch.object(s,'verify_worker_context',return_value=self.synthetic_context),self.assertRaises(FileExistsError),contextlib.redirect_stdout(io.StringIO()):s.worker_main(self.context,issued_context_sha256=self.issued)

    def test_late_failure_keeps_seen_look_but_whole_arm_failed(self):
        result,report,model,pool,native,events,directory=self.worker(late_error=MemoryError('late native RSS'))
        self.assertEqual(report['status'],'failed');self.assertEqual(report['outcome'],'resource_failure')
        self.assertEqual(report['look_reservations'][0]['status'],'seen_complete')
        self.assertEqual(report['look_reservations'][1]['status'],'reserved_consumed')
        self.assertEqual(report['fit_attempt_count'],1);self.assertNotIn('checkpoints',report)

    def test_preparation_integrity_failure_consumes_slot_without_fit(self):
        result,report,model,pool,native,events,directory=self.worker(prepare_error=ValueError('key cover'))
        self.assertEqual(report['status'],'failed');self.assertEqual(report['outcome'],'integrity_or_API_failure')
        self.assertEqual(report['fit_attempt_count'],0);model.fit.assert_not_called();pool.assert_not_called()
        self.assertTrue(self.context.with_name('arm-0.consumed.json').exists())


class CompleteReceiptTests(unittest.TestCase):
    def setUp(self):
        ContextTests.setUp(self)
        self.parent['identity']['feature_names']=['base']
        arm=self.parent['identity']['spec']['grid'][0]
        params={**s.model_parameters(arm),'border_count':254,'nan_mode':'Min','rsm':1}
        self.parent['identity']['incumbent']=dict(actual_model_parameters=params)
        self.output=self.directory/'receipt'
        self.output.mkdir()
        names=['full300.cbm','full300.json',*[n for k in [50,150,300] for n in [f'prefix{k}.cbm',f'prefix{k}-scores.npz']]]
        for name in names:(self.output/name).write_text('synthetic required artifact')
        s.write(self.output/'full300.json',dict(oblivious_trees=[dict(splits=[dict(split_type='FloatFeature')])]*300))
        outputs={s.relative(self.output/n):s.sha(self.output/n) for n in names}
        base=bt.prepared();base.queries += [('empty'+str(i),100+i,base.queries[0][2],frozenset()) for i in range(5,4000)]
        from dataclasses import asdict
        from scripts.ranking_metrics import evaluate
        metrics=asdict(evaluate(b.rankings(base,np.zeros(len(base.items))),20))
        self.manifest=dict(run_id='synthetic',identity={},outputs=outputs)
        checkpoints=[]
        for k in [50,150,300]:
            model_path=s.relative(self.output/f'prefix{k}.cbm');score_path=s.relative(self.output/f'prefix{k}-scores.npz')
            checkpoints.append(dict(config_id=s.digest(arm),incumbent=False,trees=k,trained_iterations=300,**arm,population=6000,
                model_path=model_path,score_path=score_path,artifacts={n:outputs[n] for n in [model_path,score_path]},metrics=deepcopy(metrics)))
        self.report=dict(status='complete_produced_unreviewed',outcome='arm_complete',scope='strong_arm_worker',
            feature_names=['base'],training=dict(queries=6000),fit_attempt_count=1,actual_model_parameters=params,
            artifacts=deepcopy(outputs),checkpoints=checkpoints,look_reservations=[dict(trees=k,status='seen_complete',metrics=deepcopy(metrics)) for k in [50,150,300]])
        self.budget=Mock()

    def verify(self):s.validate_complete_worker(self.parent,self.slot,{},self.output,self.manifest,self.report,self.budget)

    def test_complete_scope_passes_but_empty_artifact_map_rejected(self):
        self.verify();self.manifest['outputs']={};self.report['artifacts']={}
        with self.assertRaisesRegex(ValueError,'eight'):self.verify()

    def test_resealed_wrong_checkpoint_scope_and_float_trees_rejected(self):
        original=deepcopy(self.report)
        for key,value in [('population',26000),('depth',1),('l2_leaf_reg',99),('trained_iterations',50),('incumbent',True),('config_id','forged'),('trees',50.0)]:
            self.report=deepcopy(original);self.report['checkpoints'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'issued grid'):self.verify()

    def test_missing_look_model_or_wrong_feature_schema_rejected(self):
        original=deepcopy(self.report);self.report['look_reservations']=[]
        with self.assertRaisesRegex(ValueError,'three'):self.verify()
        self.report=deepcopy(original);self.report['feature_names']=['wrong']
        with self.assertRaisesRegex(ValueError,'schema'):self.verify()
        self.report=deepcopy(original);(self.output/'prefix150.cbm').unlink()
        with self.assertRaises(FileNotFoundError):self.verify()

    def test_metric_nonfinite_is_rejected(self):
        self.report['checkpoints'][0]['metrics']['conditional_macro_query']['ndcg']=float('nan')
        self.report['look_reservations'][0]['metrics']=self.report['checkpoints'][0]['metrics']
        with self.assertRaisesRegex(ValueError,'Invalid external metric'):self.verify()


class ParentPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve();self.addCleanup(patch.stopall)
        for module in [s,c]:patch.object(module,'ROOT',self.root).start()
        source=self.root/'source';source.write_text('source');self.grid=self.root/'grid.json';s.write(self.grid,s.specification())
        identity=dict(role=s.ROLE,spec=s.specification(),fingerprints={'source':s.sha(source)},feature_names=['base'],incumbent={})
        self.plan=dict(run_id=s.digest(identity),identity=identity);self.approval=self.root/'execution.json'
        s.write(self.approval,dict(version=1,approved=True,scope=s.ROLE,run_id=self.plan['run_id'],fingerprints=identity['fingerprints']))
        model=self.root/'old.cbm';model.write_text('old');scores=self.root/'old.npz';scores.write_text('old')
        control=dict(metrics=candidate('old',.6)['metrics'],artifacts={'old.cbm':s.sha(model),'old.npz':s.sha(scores)})
        self.inputs=dict(control=dict(control=control,manifest=dict(run_id='old')))

    def execute(self,gate_code=0,arm_failure=None,unknown_gate=None):
        populations=[]
        def invoke(directory,parent,slot,path,budget,**kwargs):
            populations.append((slot['mode'],slot['population']))
            if unknown_gate and slot['mode']=='gate':raise unknown_gate
            code=gate_code if slot['mode']=='gate' else (1 if slot['index']==arm_failure else 0)
            report=dict(mode=slot['mode'],fit_attempt_count=0 if slot['mode']=='gate' else 1,process_peak_rss_bytes=1,
                look_reservations=[] if slot['mode']=='gate' else [dict(status='seen_complete')]*3)
            if slot['mode']=='arm':report['checkpoints']=[dict(candidate('arm'+str(slot['index']),.7,trees=k),trained_iterations=300,population=slot['population']) for k in [50,150,300]]
            return dict(exit_code=code,report=report,manifest={})
        with patch.object(s,'prepare_plan',return_value=(self.plan,self.inputs)),patch.object(s,'invoke_worker',side_effect=invoke),patch.object(c,'verify_pins'):
            result=s.run(self.grid,self.grid,self.grid,self.grid,self.grid,execution_approval=self.approval)
        return result,populations

    def test_full_gate_fixes_all_new_populations_and_old_control_not_refit(self):
        report,populations=self.execute()
        self.assertEqual(populations,[('gate',26000)]+[('arm',26000)]*4)
        self.assertEqual(report['fit_attempt_count'],4);self.assertEqual(report['actual_seen_looks'],12)
        self.assertEqual(report['winner']['trained_iterations'],300);self.assertEqual(report['winner']['trees'],50)

    def test_recognized_gate_failure_only_fresh6000_and_late_arm_ineligible(self):
        report,populations=self.execute(gate_code=1,arm_failure=0)
        self.assertEqual(populations,[('gate',26000)]+[('arm',6000)]*4)
        self.assertEqual(report['fit_attempt_count'],4);self.assertEqual(report['eligible_outputs'],10)
        self.assertNotEqual(report['winner']['config_id'],'arm0')

    def test_unknown_gate_stops_before_any_arm_and_failed_marker(self):
        with self.assertRaisesRegex(RuntimeError,'unreaped'):self.execute(unknown_gate=RuntimeError('unreaped usage'))
        directory=self.root/'artifacts/strong-baseline'/self.plan['run_id']
        self.assertTrue((directory/'report.failed.json').exists());self.assertEqual(s.read(directory/'report.json')['status'],'failed')


if __name__=='__main__':unittest.main()
