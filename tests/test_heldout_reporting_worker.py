"""Adapter transport tests; authority/native/runtime are explicitly fake."""
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import duckdb
import numpy as np
from scripts import heldout_contract as h
from scripts import heldout_execution as x
from tests.test_heldout_source import definitions,ROWS
from tests.test_heldout_predictions import NativeFake

from scripts import heldout_reporting_worker as m


class FakeBudget:
    def __init__(self):self.calls=0
    def guard(self):self.calls+=1
    def watch(self,con):self.guard()


class FakeExecution:
    """No production acceptance, global claim, runtime fence or actual CBM."""
    def __init__(self,root,inputs,role='source'):
        self.root=root;self.context=dict(run_id='a'*64,role=role,inputs=deepcopy(inputs),authorities={},output_path='artifacts/adapter-toy/'+role+'/receipt.json');self.pins={r['path']:r['sha256'] for r in inputs.values()};self.budget=FakeBudget()
        (root/Path(self.context['output_path']).parent).mkdir(parents=True,exist_ok=True)
    def file(self,name,body):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);raw=body if type(body) is bytes else (x.canonical(body)+'\n').encode();path.write_bytes(raw)
        ref=dict(path=name,sha256=hashlib.sha256(raw).hexdigest());self.pins[name]=ref['sha256'];return ref
    def input_json(self,name):
        ref=self.context['inputs'][name];body,sha=x.read(self.root/ref['path']);x.need(sha==ref['sha256'],'Synthetic input changed');return body
    def retain_pins(self,mapping):
        for name,sha in mapping.items():x.need(name not in self.pins or self.pins[name]==sha,'Synthetic conflict')
        self.pins.update(deepcopy(mapping))
        for name,sha in mapping.items():x.need(x.sha(self.root/name)==sha,'Synthetic nested bytes changed')


class Transport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.run=FakeExecution(self.root,{})
        self.when=datetime(2019,10,25);self.body=SimpleNamespace(queries=[('a',2**60,self.when)],calendar_maturity=np.ones(1,dtype=np.bool_),group=np.zeros(1,dtype=np.int32),items=np.array([2**60+1],dtype=np.int64),scores=np.array([.5],dtype=np.float64))
        self.day=dict(anchor='2019-10-25T00:00:00Z',query_count=1,candidate_count=1)
    def save(self):
        ref=m.save_scores(self.run,'artifacts/toy/score.npz',self.body);self.run.pins[ref['path']]=ref['sha256'];return dict(artifact=ref,model=dict(path='synthetic.cbm',sha256='b'*64),rows=1,queries=1,scoring_prefix=300,feature_names=['fake']*41)
    def test_exact_bigint_triples_and_simple_arrays_roundtrip(self):
        descriptor=self.save();body=m.read_scores(self.run,descriptor,self.day)
        self.assertEqual(body['queries'],self.body.queries);self.assertEqual(body['items'].tolist(),[2**60+1]);np.testing.assert_array_equal(body['scores'],[.5])
        self.assertEqual(body['group'].dtype,np.dtype('int32'))
    def test_no_silent_qid_unicode_truncation(self):
        self.body.queries=[('q'*65,1,self.when)]
        with self.assertRaisesRegex(ValueError,'truncation'):self.save()
        self.assertFalse((self.root/'artifacts/toy/score.npz').exists())
    def test_exclusive_score_output_no_retry(self):
        self.save()
        with self.assertRaisesRegex(ValueError,'already consumed'):self.save()
    def rewrite(self,descriptor,change):
        path=self.root/descriptor['artifact']['path']
        with np.load(path,allow_pickle=False) as body:arrays={name:body[name] for name in body.files}
        change(arrays)
        with path.open('wb') as stream:np.savez(stream,**arrays)
        descriptor['artifact']['sha256']=x.sha(path);self.run.pins[descriptor['artifact']['path']]=descriptor['artifact']['sha256']
    def test_float_id_object_dtype_and_nonfinite_scores_fail(self):
        for mode in ['float','object','infinite']:
            if (self.root/'artifacts/toy/score.npz').exists():(self.root/'artifacts/toy/score.npz').unlink()
            desc=self.save()
            def change(arrays):
                if mode=='float':arrays['items']=arrays['items'].astype(np.float64)
                elif mode=='object':arrays['query_ids']=arrays['query_ids'].astype(object)
                else:arrays['scores'][0]=np.inf
            self.rewrite(desc,change)
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.read_scores(self.run,desc,self.day)
    def test_small_header_declaring_huge_shape_rejects_before_numpy_allocation(self):
        descriptor=self.save();path=self.root/descriptor['artifact']['path']
        with zipfile.ZipFile(path) as archive:members={name:archive.read(name) for name in archive.namelist()}
        buffer=io.BytesIO();np.lib.format.write_array_header_1_0(buffer,dict(descr='<i8',fortran_order=False,shape=(2**40,)));members['items.npy']=buffer.getvalue()
        with zipfile.ZipFile(path,'w') as archive:
            for name,raw in members.items():archive.writestr(name,raw)
        descriptor['artifact']['sha256']=x.sha(path);self.run.pins[descriptor['artifact']['path']]=descriptor['artifact']['sha256']
        with patch.object(np,'load',side_effect=AssertionError('unsafe allocation')),self.assertRaisesRegex(ValueError,'before allocation'):m.read_scores(self.run,descriptor,self.day)
    def test_wrong_anchor_duplicate_user_and_group_outside_Q_reject(self):
        for mode in ['anchor','group']:
            if (self.root/'artifacts/toy/score.npz').exists():(self.root/'artifacts/toy/score.npz').unlink()
            descriptor=self.save()
            self.rewrite(descriptor,lambda a:a['anchors' if mode=='anchor' else 'group'].__setitem__(0,0 if mode=='anchor' else 2))
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.read_scores(self.run,descriptor,self.day)
    def test_undeclared_member_rejects_before_np_load(self):
        descriptor=self.save();path=self.root/descriptor['artifact']['path']
        with zipfile.ZipFile(path,'a') as archive:archive.writestr('Y.npy',b'poison')
        descriptor['artifact']['sha256']=x.sha(path);self.run.pins[descriptor['artifact']['path']]=descriptor['artifact']['sha256']
        with patch.object(np,'load',side_effect=AssertionError('No Y/allocation')),self.assertRaisesRegex(ValueError,'unique NPZ'):m.read_scores(self.run,descriptor,self.day)

    def bootstrap_fixture(self):
        names={'scripts/heldout_reporting_worker.py','scripts/heldout_worker_context.py','scripts/heldout_execution.py','scripts/heldout_contract.py','uv.lock','pyproject.toml'}
        code={name:self.run.file(name,b'# synthetic boot only')['sha256'] for name in names}
        request=self.run.file('fixture/bootstrap-request.json',dict(code_fingerprints=code))
        context=self.run.file('fixture/bootstrap-context.json',dict(role='source',request=request))
        return self.root/context['path'],context['sha256'],request,code
    def test_bootstrap_original_issuer_and_code_before_project_import(self):
        path,sha,request,code=self.bootstrap_fixture()
        with patch.object(m,'ROOT',self.root):
            try:self.assertEqual(m.bootstrap(path,sha),'source')
            finally:
                if str(self.root) in m.sys.path:m.sys.path.remove(str(self.root))
            with self.assertRaisesRegex(ValueError,'issuer SHA'):m.bootstrap(path,'0'*64)
            (self.root/'scripts/heldout_contract.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'code changed'):m.bootstrap(path,sha)
    def test_unlisted_namespace_initializer_rejects_before_project_import(self):
        path,sha,request,code=self.bootstrap_fixture()
        with patch.object(m,'ROOT',self.root):
            try:self.assertEqual(m.bootstrap(path,sha),'source')
            finally:
                if str(self.root) in m.sys.path:m.sys.path.remove(str(self.root))
            for folder in ['scripts','tests','tests/oracles']:
                initializer=self.root/folder/'__init__.py';initializer.parent.mkdir(parents=True,exist_ok=True);initializer.write_text('raise AssertionError("never execute initializer")')
                with self.subTest(folder=folder),self.assertRaisesRegex(ValueError,'Unpinned namespace'):m.bootstrap(path,sha)
                initializer.unlink()
    def test_bootstrap_rejects_arbitrary_oracle_role(self):
        path,sha,request,code=self.bootstrap_fixture();body=json.loads(path.read_text());body['role']='source_oracle';path.write_text(x.canonical(body));sha=x.sha(path)
        with patch.object(m,'ROOT',self.root),self.assertRaisesRegex(ValueError,'production adapter'):m.bootstrap(path,sha)
    def test_bootstrap_symlink_escape_rejected_before_read(self):
        path,sha,request,code=self.bootstrap_fixture();target=self.root/'scripts/heldout_contract.py';target.unlink();target.symlink_to('/dev/null')
        with patch.object(m,'ROOT',self.root),self.assertRaises(ValueError):m.bootstrap(path,sha)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.run=FakeExecution(self.root,{})
        self.pool,self.lock,self.choice=definitions('R2')
        fixed=dict(random_seed=2026,boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False,border_count=254,nan_mode='Min',rsm=1,learning_rate=struct.unpack('!f',struct.pack('!f',.05))[0])
        for role,model in self.lock['models'].items():
            model['effective_parameters'].update(fixed);model['model']=self.run.file('fixture/'+role+'.cbm',b'FAKE NATIVE ONLY')
        self.choice['models']=deepcopy(self.lock['models'])
        repo=Path(h.__file__).resolve().parents[1]
        for name,body in [('lock',self.lock),('choice',self.choice),('pool',json.loads((repo/'configs/features/automation-pool.json').read_text())),('registry',json.loads((repo/'configs/features/manual-18.json').read_text()))]:
            self.run.context['inputs'][name]=self.run.file('fixture/'+name+'.json',body)
        database=self.root/'fixture/source.duckdb';con=duckdb.connect(str(database));con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)');con.executemany('INSERT INTO events VALUES (?,?,?,?,?)',ROWS+[(datetime(2019,10,25),'purchase',99,1,100)]);con.close()
        self.raw=dict(path='fixture/source.duckdb',sha256=x.sha(database));self.run.pins[self.raw['path']]=self.raw['sha256'];self.run.context['inputs']['source']=self.raw
        proposal=self.run.file('artifacts/adapter-toy/proposal.json',dict(identity=dict(source_inputs=dict(source=self.raw))))
        self.run.pins[proposal['path']]=proposal['sha256'];self.environment={'synthetic_fake_runtime':True}
    def source(self):
        from scripts import anchor_pilot
        with patch.object(anchor_pilot,'create_labels',side_effect=AssertionError('No generic Y builder')),patch.object(anchor_pilot,'build_pilot',side_effect=AssertionError('No generic pipeline')):
            outputs,ref,calls,labels=m.source_role(self.run,self.environment)
        self.source_manifest,_=x.read(self.root/ref['path']);self.source_ref=ref;self.run.retain_pins(outputs)
        self.source_seal=self.run.file('fixture/source-seal.json',dict(days=self.source_manifest['days'],fingerprints=outputs,sealed_at='2026-10-15T12:00:30Z'))
        return outputs,ref,calls,labels
    def predictions(self):
        from scripts import inference_data
        self.run.context.update(role='predictions',output_path='artifacts/adapter-toy/predictions/receipt.json')
        (self.root/Path(self.run.context['output_path']).parent).mkdir(exist_ok=True)
        self.run.context['inputs']={name:self.run.context['inputs'][name] for name in ['lock','choice']};self.run.context['inputs'].update(source_manifest=self.source_ref,source_acceptance=self.source_seal)
        specs={str(self.root/value['model']['path']):(role,value) for role,value in self.lock['models'].items()}
        class FakeLoader:
            def load_model(self,path):
                role,value=specs[path];self.fake=NativeFake(value,0 if role=='B' else .5)
            def __getattr__(self,name):return getattr(self.fake,name)
        with patch('catboost.CatBoostClassifier',side_effect=FakeLoader),patch.object(inference_data,'ROOT',self.root),patch.object(m,'utc_now',return_value='2026-10-15T12:01:00Z'):
            outputs,ref,calls,labels=m.predictions_role(self.run,self.environment)
        self.pred_manifest,_=x.read(self.root/ref['path']);self.pred_ref=ref;self.run.retain_pins(outputs);return outputs,ref,calls,labels
    def target_inputs(self):
        inv=dict(version=1,scope='all_reserved_predictions_before_targets',decision_lock_sha256=h.digest(self.lock),created_at=self.pred_manifest['created_at'],source_acceptance=self.source_seal,days=self.pred_manifest['days'],output_verification=dict(path='fixture/fake-oracle.json',sha256='a'*64),lifetime_receipt=dict(path='fixture/fake-lifetime.json',sha256='b'*64),heldout_targets_opened=False)
        inventory=self.run.file('fixture/inventory.json',inv);prediction=self.run.file('fixture/prediction-seal.json',dict(inventory=inventory,fingerprints=deepcopy(self.pred_manifest['outputs']),sealed_at='2026-10-15T12:02:00Z'))
        policy=self.run.file('fixture/target-policy.json',dict(prediction_acceptance=prediction,prediction_inventory_sha256=h.digest(inv),decision_lock_sha256=h.digest(self.lock),periods=['confirmation25_reporting_only','final26_31_frozen'],no_adaptation=True,earliest_opened_at='2026-10-15T12:02:00Z'))
        target=self.run.file('fixture/target-seal.json',dict(sealed_at='2026-10-15T12:02:30Z'))
        self.run.context.update(role='targets_evaluation',output_path='artifacts/adapter-toy/targets_evaluation/receipt.json');(self.root/Path(self.run.context['output_path']).parent).mkdir(exist_ok=True)
        self.run.context['inputs'].update(prediction_acceptance=prediction,prediction_inventory=inventory,target_policy=policy);self.run.context['authorities']=dict(target_execution=target)
    def test_native_tiny_source_Q10_C8_B45_chosen3_and_independent_source_core(self):
        outputs,ref,calls,labels=self.source();self.assertEqual((len(outputs),calls,labels),(29,0,False))
        self.assertEqual(len(self.source_manifest['days']),7);self.assertEqual(self.source_manifest['days'][-1]['query_count'],0)
        con=duckdb.connect(':memory:');self.addCleanup(con.close);con.execute('SET threads=2');con.execute("ATTACH '"+str(self.root/self.raw['path'])+"' AS raw (READ_ONLY)");con.execute('CREATE VIEW heldout_raw_events AS SELECT * FROM raw.main.events')
        from tests.oracles import heldout_source_audit as oracle
        def load_day(con,day):
            refs={}
            for key in ['queries','candidates','base_features','extra_features']:
                name='toy_'+key;con.execute('CREATE OR REPLACE VIEW '+name+" AS SELECT * FROM read_parquet('"+str(self.root/day[key]['path'])+"')");refs[key]=name
            return refs
        result=oracle.audit_source(con,self.lock,authenticated_choice=self.choice,days=self.source_manifest['days'],load_day=load_day)
        self.assertFalse(result['labels_loaded']);self.assertFalse(result['baseline_formula_values_complete'])
    def test_all_three_tiny_transports_fakenative_fullY_and_actual_SQLclock(self):
        self.source();_,_,calls,labels=self.predictions();expected=2*sum(day['candidate_count']>0 for day in self.pred_manifest['days']);self.assertEqual((calls,labels),(expected,False))
        self.target_inputs()
        with patch.object(m,'utc_now',return_value='2026-10-15T12:03:00Z'):outputs,ref,calls,labels=m.targets_role(self.run,self.environment)
        body,_=x.read(self.root/ref['path']);self.assertEqual((len(outputs),calls,labels),(3,0,True));self.assertEqual(body['actual_target_intent']['opened_at'],body['target_stage_opened_at'])
        self.assertGreaterEqual(body['fullY_started_monotonic'],body['target_stage_started_monotonic']);self.assertEqual(len(body['periods']),2)
        con=duckdb.connect(':memory:');self.addCleanup(con.close);pairs=con.execute("SELECT * FROM read_parquet('"+str(self.root/body['private_outputs']['targets']['path'])+"')").fetchall();self.assertTrue(pairs)
        rows=[json.loads(line) for line in (self.root/body['private_outputs']['rankings']['path']).read_text().splitlines()]
        self.assertEqual(len(rows),2*sum(day['query_count'] for day in self.source_manifest['days']));self.assertTrue(all(row['mature'] is True for row in rows))
    def test_last_day_bad_saved_header_precedes_target_admission_and_raw_fullY(self):
        self.source();self.predictions();self.target_inputs();inventory=self.run.input_json('prediction_inventory');path=self.root/inventory['days'][-1]['predictions']['W']['artifact']['path'];path.write_bytes(b'broken zip')
        # The real helper would reject altered pinned bytes even earlier; fakepins
        # here intentionally reach the physical decoder barrier without authority.
        with patch.object(self.run,'retain_pins',lambda mapping:self.run.pins.update(mapping)),patch.object(m,'connection',side_effect=AssertionError('No source/target operation')),self.assertRaises(zipfile.BadZipFile):m.targets_role(self.run,self.environment)
    def test_source_cleanup_error_keeps_original_body_error(self):
        class Broken:
            def close(self):raise OSError('secondary close')
        error=RuntimeError('primary fixture')
        with patch('duckdb.connect',return_value=Broken()),self.assertRaisesRegex(RuntimeError,'primary') as caught:
            with m.connection(self.run):raise error
        self.assertIs(caught.exception,error);self.assertIn('OSError',str(error.__notes__))

    def test_W_equal_B_exports_one_artifact_and_one_fake_native_call_per_nonempty_day(self):
        old_b=deepcopy(self.lock['models']['B']);self.pool,self.lock,self.choice=definitions('B');self.lock['models']={'B':old_b,'W':deepcopy(old_b)};self.choice['models']=deepcopy(self.lock['models'])
        for name,body in [('lock',self.lock),('choice',self.choice)]:self.run.context['inputs'][name]=self.run.file('fixture/'+name+'.json',body)
        source_outputs,_,_,_=self.source();self.assertEqual(len(source_outputs),22)
        outputs,_,calls,_=self.predictions();self.assertEqual(len(outputs),8)
        self.assertEqual(calls,sum(row['candidate_count']>0 for row in self.pred_manifest['days']))
        for day in self.pred_manifest['days']:self.assertEqual(day['predictions']['B'],day['predictions']['W'])
    def test_outer_adapter_body_failure_calls_fail_once_without_refill(self):
        from unittest.mock import Mock
        from scripts import heldout_worker_context as common
        failure=RuntimeError('original body failure');execution=SimpleNamespace(verify_pins=Mock(),environment=Mock(return_value={}),fail=Mock())
        with patch.object(m,'bootstrap',return_value='source'),patch.object(common,'begin_role',return_value=execution) as begin,patch.object(m,'source_role',side_effect=failure) as production,self.assertRaises(RuntimeError) as caught:
            m.run_worker('synthetic-context','0'*64)
        self.assertIs(caught.exception,failure);self.assertEqual(begin.call_count,1);self.assertEqual(production.call_count,1);execution.fail.assert_called_once_with(failure)


if __name__=='__main__':unittest.main()
