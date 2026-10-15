"""Proposed pure contracts. SOURCE ONLY: not executed in this preparation."""
from copy import deepcopy
import ast
import builtins
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch

PATH=Path('/tmp/tlab-chosen3-six-role-candidate-v4r1.py')
EXPECTED_SOURCE_SHA='4eca34e06847250db06844335d66c28b2fbbb01e685f2c8c798fd9d0d8ea2655'
module=ModuleType('chosen3_candidate_pure_contract');module.__file__=str(PATH)
source_raw=PATH.read_bytes();assert hashlib.sha256(source_raw).hexdigest()==EXPECTED_SOURCE_SHA
exec(compile(source_raw,str(PATH),'exec',dont_inherit=True),module.__dict__)
c=module


def specs():
    b=dict(feature_names=['base_'+str(i) for i in range(41)],model=dict(path='fixture-reused/B.cbm',sha256='b'*64),
        effective_parameters=dict(iterations=300),trained_iterations=300,scoring_prefix=300,population=26000)
    w=deepcopy(b);w['feature_names']+=c.EXTRAS;w['model']=dict(path='fixture-setup/W.cbm',sha256='c'*64)
    return b,w


def periods(delta):
    # Complete production Evaluation shape; this fixture tests shape, not numerical oracle correctness.
    metrics=dict(k=20,query_count=0 if delta is None else 2,mature_query_count=0 if delta is None else 2,
        censored_query_count=0,nonempty_query_count=0 if delta is None else 1,mature_user_count=0 if delta is None else 2,
        positive_user_count=0 if delta is None else 1,nonempty_fraction=None if delta is None else .5)
    metrics.update({name:dict.fromkeys(['recall','ndcg','average_precision','reciprocal_rank'],None if delta is None else .5) for name in c.ESTIMANDS})
    w=deepcopy(metrics)
    if delta is not None:
        for name in c.ESTIMANDS:w[name]['ndcg']+=delta
    bootstrap={name:dict(metric='ndcg',estimand=name,replicates=200,seed=2026,user_count=0 if delta is None else 2,
        estimate=delta,samples=[delta]*200,undefined_draws=200 if delta is None else 0,interval_95=None if delta is None else [delta,delta]) for name in c.ESTIMANDS}
    p=dict(anchors=['2019-10-25T00:00:00Z'],metrics=dict(B=deepcopy(metrics),W=w),ndcg_W_minus_B=dict.fromkeys(c.ESTIMANDS,delta),paired_user_bootstrap=bootstrap,
        support=dict(query_count=metrics['query_count'],candidate_pairs=0 if delta is None else 3,target_pairs=metrics['nonempty_query_count'],retrieved_target_pairs=metrics['nonempty_query_count'],positive_empty_C_queries=0))
    return dict(confirmation25_reporting_only=deepcopy(p),final26_31_frozen=deepcopy(p))


class Chosen3Contracts(unittest.TestCase):
    def test_complete_verify_results_returns_summary_from_full_production_JSON_scene(self):
        """In-memory positive scene only. The actual V3 outer trial remains FAILED."""
        fixture_path=Path('/tmp/tlab-chosen3-v4-complete-json-fixture.json')
        raw=fixture_path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),'47476d48fd73ce4e64603703c53e32fb35f17f161c1a799a96741f8b130951af')
        fixture=json.loads(raw);root=Path(fixture['original_application_root']);directory=root/fixture['owner_directory']
        self.assertEqual(fixture['actual_original_outer_trial_status'],'failed_consumed_outer_summary_constructor')
        records=fixture['records'];declared=fixture['declared_binary_and_code_hashes_for_mock_only'];compares=[];hash_lookups=[]
        roles=('source','source_oracle','predictions','prediction_oracle','targets_evaluation','metric_oracle')
        entries={name:'scripts/heldout_reporting_worker.py' for name in ['source','predictions','targets_evaluation']}
        entries.update(source_oracle='tests/oracles/heldout_source_worker.py',prediction_oracle='tests/oracles/heldout_prediction_worker.py',metric_oracle='tests/oracles/heldout_metric_worker.py')
        owner=SimpleNamespace(CLAIM='artifacts/heldout-study/owner.claim.json',x=SimpleNamespace(ROLES=roles,ENTRY=entries))
        def snapshot(path,expected=None):
            name=str(Path(path).relative_to(root));row=records[name];encoded=row['raw_json_utf8'].encode()
            self.assertEqual(hashlib.sha256(encoded).hexdigest(),row['sha256'])
            if expected is not None:self.assertEqual(row['sha256'],expected)
            return json.loads(encoded),row['sha256']
        def sha(path):
            name=str(Path(path).relative_to(root));hash_lookups.append(name)
            # Binary/model/source hashes are declared values, never byte reads.
            return records[name]['sha256'] if name in records else declared[name]
        def rglob(path,pattern):
            if path==root and pattern=='*failed.json':return []  # Positive test scene; real failed markers stay intact.
            self.assertEqual(path,directory);self.assertEqual(pattern,'*.json')
            return [root/name for name in records if (root/name).is_relative_to(directory)]
        def glob(path,pattern):
            self.assertEqual(pattern,'oracle-scratch-*');self.assertIn(path.name,roles);return []
        def exists(path):
            self.assertEqual(path.name,'spill');self.assertIn(path.parent.name,roles);return False
        def compare_values(actual,expected):
            if type(expected) is dict:
                self.assertEqual(set(actual),set(expected))
                for key,value in expected.items():compare_values(actual[key],value)
            elif type(expected) is list:
                self.assertEqual(len(actual),len(expected))
                for first,second in zip(actual,expected):compare_values(first,second)
            elif type(expected) is float:
                self.assertIs(type(actual),float);self.assertTrue(math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12))
            else:self.assertIs(type(actual),type(expected));self.assertEqual(actual,expected)
        def metric_compare(actual,expected):compares.append(True);compare_values(actual,expected)
        original_import=builtins.__import__
        def imported(name,*args,**kwargs):
            if name=='tests.oracles':return SimpleNamespace(heldout_metric_audit=SimpleNamespace(compare=metric_compare))
            return original_import(name,*args,**kwargs)
        with ExitStack() as stack:
            for target,name,value in [(c,'snapshot',snapshot),(c,'sha',sha),(Path,'rglob',rglob),(Path,'glob',glob),(Path,'exists',exists),(builtins,'__import__',imported)]:stack.enter_context(patch.object(target,name,value))
            stack.enter_context(patch.object(c.resource,'getrusage',return_value=SimpleNamespace(ru_utime=.1,ru_stime=.05)))
            summary=c.verify_results(None,root,owner,deepcopy(fixture['report']),1,deepcopy(fixture['gates']),dict(production_files=fixture['production_files']))
        self.assertEqual(compares,[True]);self.assertEqual(summary['status'],'chosen3_six_roles_complete_pending_supervisor_exit_tail')
        self.assertEqual(summary['candidate_pairs'],25);self.assertEqual(summary['chosen_scalar_values'],75)
        self.assertEqual(summary['native_calls_each_prediction_role'],10);self.assertEqual(summary['actual_roles'],list(roles))
        self.assertFalse(summary['metric_delta_required_nonzero']);self.assertTrue(summary['external_exit_tail_acceptance_required'])
        self.assertEqual(summary['evidence_fingerprints']['fixture-setup/W.cbm'],declared['fixture-setup/W.cbm'])
        self.assertTrue(any(name.endswith('.cbm') for name in hash_lookups))  # Mocked only, proves the full pin loop ran.
    def test_all_DISCLOSURES_expansions_have_no_duplicate_explicit_keywords(self):
        tree=ast.parse(source_raw);expanded=0;overlaps=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and any(k.arg is None and isinstance(k.value,ast.Name) and k.value.id=='DISCLOSURES' for k in node.keywords):
                expanded+=1;bad={k.arg for k in node.keywords if k.arg is not None}&set(c.DISCLOSURES)
                if bad:overlaps.append((node.lineno,sorted(bad)))
        self.assertGreater(expanded,0);self.assertEqual(overlaps,[])
    def _setup_fault(self,when,retry=False):
        root=c.ROOT.resolve();before_root_exists=c.ROOT.exists();files={str(root/name):b'virtual non-native output' for name in c.SETUP_OUTPUTS};writes={};launches=[]
        original=dict(version=1,**c.DISCLOSURES,status='W44_setup_complete_pending_external_exit_tail',fit_attempt_count=1,training_rows=8,feature_count=44,child_cpu_seconds=.5)
        result_name=str(root/'fixture-setup/result.json');files[result_name]=json.dumps(original).encode();original_pin=hashlib.sha256(files[result_name]).hexdigest()
        def mutate():
            changed=dict(original,actual_W_training_rows=999,fit_attempt_count=99);files[result_name]=json.dumps(changed).encode()
        def snapshot(path,expected=None):
            raw=files[str(path)];digest=hashlib.sha256(raw).hexdigest()
            if expected is not None:self.assertEqual(digest,expected)
            body=json.loads(raw)
            if str(path)==result_name and when=='after_read':mutate()
            return body,digest
        def sha(path):return hashlib.sha256(files[str(path)]).hexdigest()
        def canonical(body):return json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False)
        def exclusive(path,body):
            key=str(path)
            if key in files:raise FileExistsError(key)
            writes[key]=deepcopy(body);files[key]=(canonical(body)+'\n').encode()
            if key==str(root/'setup-supervision.json') and when=='after_receipt':mutate()
        observation=dict(status='verified_normal_exit',exit_code=0,reaped=True,unknown_active_work=False,cpu_upper_seconds=2.5,elapsed_upper_seconds=5.5,wait4_child_cpu_seconds=.6)
        def supervise(*args,**kwargs):launches.append(args);return deepcopy(observation)
        base=SimpleNamespace(safe_root=lambda path:Path(path).resolve(),create_copy=lambda *args:None,exclusive=exclusive,canonical=canonical,processes=lambda *args:SimpleNamespace(supervise=supervise))
        freeze=dict(python='/virtual/python',harness_files={str(c.SUPERVISOR):'4'*64})
        with ExitStack() as stack:
            for owner,name,value in [(c,'load',lambda *args:(base,freeze)),(c,'fresh_child',lambda:None),(c,'copy_reused_B',lambda *args:None),(c,'snapshot',snapshot),(c,'sha',sha),(Path,'exists',lambda path:str(path) in files)]:stack.enter_context(patch.object(owner,name,value))
            with self.assertRaisesRegex(ValueError,'validated evidence bytes changed'):c.supervise('setup',root,'/virtual/freeze.json','1'*64)
            failure=writes[str(root/'setup-supervision.failed.json')]
            self.assertEqual(failure['returned_process_observation']['wait4_child_cpu_seconds'],.6)
            self.assertEqual(failure['returned_process_observation']['bound_outputs']['fixture-setup/result.json'],original_pin)
            if retry:
                preserved=files[str(root/'setup-supervision.failed.json')]
                with self.assertRaises(FileExistsError):c.supervise('setup',root,'/virtual/freeze.json','1'*64)
                self.assertEqual(files[str(root/'setup-supervision.failed.json')],preserved)
        self.assertEqual(len(launches),1);self.assertEqual(c.ROOT.exists(),before_root_exists)
        return writes,root,original_pin
    def test_validated_setup_result_cannot_adopt_replacement_hash(self):
        writes,root,_=self._setup_fault('after_read')
        self.assertNotIn(str(root/'setup-supervision.json'),writes)
    def test_result_replacement_during_receipt_write_fails_terminal_repin(self):
        writes,root,original_pin=self._setup_fault('after_receipt')
        self.assertEqual(writes[str(root/'setup-supervision.json')]['bound_outputs']['fixture-setup/result.json'],original_pin)
        self.assertIn(str(root/'setup-supervision.failed.json'),writes)
    def test_failed_snapshot_attempt_cannot_retry_or_replace_failure(self):
        self._setup_fault('after_read',retry=True)
    def test_setup_supervision_snapshot_replacement_stops_before_integration_launch(self):
        root=c.ROOT.resolve();before_root_exists=c.ROOT.exists();files={str(root/name):b'virtual non-native output' for name in c.SETUP_OUTPUTS};launches=[]
        sha=lambda path:hashlib.sha256(files[str(path)]).hexdigest()
        setup=dict(status='verified_normal_exit',exit_code=0,reviewed_freeze_sha256='1'*64,cpu_upper_seconds=2.5,bound_outputs={name:sha(root/name) for name in c.SETUP_OUTPUTS})
        key=str(root/'setup-supervision.json');files[key]=json.dumps(setup).encode()
        def snapshot(path,expected=None):
            raw=files[str(path)];body=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
            if str(path)==key:files[key]=json.dumps(dict(body,cpu_upper_seconds=999)).encode()
            return body,digest
        base=SimpleNamespace(safe_root=lambda path:Path(path).resolve(),processes=lambda *args:launches.append(args))
        freeze=dict(python='/virtual/python',harness_files={str(c.SUPERVISOR):'4'*64})
        with patch.object(c,'load',return_value=(base,freeze)),patch.object(c,'fresh_child'),patch.object(c,'snapshot',side_effect=snapshot),patch.object(c,'sha',side_effect=sha),patch.object(Path,'exists',lambda path:str(path) in files):
            with self.assertRaisesRegex(ValueError,'validated evidence bytes changed'):c.supervise('integration',root,'/virtual/freeze.json','1'*64)
        self.assertEqual(launches,[]);self.assertEqual(c.ROOT.exists(),before_root_exists)
    def test_metric_metadata_matches_actual_production_Evaluation_fields(self):
        tree=ast.parse((c.PROJECT/'scripts/ranking_metrics.py').read_bytes())
        evaluation=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Evaluation')
        actual_fields={n.target.id for n in evaluation.body if isinstance(n,ast.AnnAssign)}
        p=periods(0.0);self.assertEqual(set(p['confirmation25_reporting_only']['metrics']['B']),actual_fields)
        self.assertEqual(actual_fields,c.ESTIMANDS|c.METRIC_METADATA);c.metric_shape(p)
        del p['confirmation25_reporting_only']['metrics']['B']['query_count']
        with self.assertRaises(ValueError):c.metric_shape(p)
    def test_exact_selected44_closure_and_distinct_model_required(self):
        b,w=specs();c.matched_specs(b,w)
        for mode in ['prefix','suffix','same_model','parameters']:
            bad=deepcopy(w)
            if mode=='prefix':bad['feature_names'][0]='changed'
            elif mode=='suffix':bad['feature_names'][41:]=list(reversed(c.EXTRAS))
            elif mode=='same_model':bad['model']=deepcopy(b['model'])
            else:bad['effective_parameters']['iterations']=301
            with self.subTest(mode=mode),self.assertRaises(ValueError):c.matched_specs(b,bad)
    def test_two_models_per_nonempty_date_without_fourteen_literal(self):
        self.assertEqual(c.native_call_count([dict(candidate_count=n) for n in [0,2,0,22,0,0,0]]),4)
        self.assertEqual(c.native_call_count([dict(candidate_count=0)]*7),0)
    def test_zero_nonzero_negative_and_undefined_metric_differences_allowed(self):
        for delta in [0.0,.125,-.125,None]:
            with self.subTest(delta=delta):c.metric_shape(periods(delta))
    def test_missing_fixed_draw_or_invented_undefined_count_rejects(self):
        for mode in ['draw','undefined']:
            p=periods(0.0);b=p['final26_31_frozen']['paired_user_bootstrap'][next(iter(c.ESTIMANDS))]
            if mode=='draw':b['samples'].pop()
            else:b['undefined_draws']=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):c.metric_shape(p)
    def test_source_scalar_total_derived_from_actual_candidate_pairs(self):
        days=[dict(candidate_count=n,chosen_columns=3,chosen_scalar_values=3*n,chosen_formula_values_complete=True) for n in [0,2,23,0,0,0,0]]
        proof=dict(choice='R2',chosen_columns=3,chosen_scalar_values=75,chosen_formula_values_complete=True,mismatch_count=0,
            extra_proof_scope='all_selected3_values_every_C_row',baseline_formula_values_complete=False,days=days)
        c.chosen_proof(proof,25)
        with self.assertRaises(ValueError):c.chosen_proof(proof,24)
        proof['days'][1]['chosen_scalar_values']=5
        with self.assertRaises(ValueError):c.chosen_proof(proof,25)
    def test_source_exhaustiveness_cannot_promote_B18(self):
        proof=dict(choice='R2',chosen_columns=3,chosen_scalar_values=3,chosen_formula_values_complete=True,mismatch_count=0,
            extra_proof_scope='all_selected3_values_every_C_row',baseline_formula_values_complete=True,days=[])
        with self.assertRaises(ValueError):c.chosen_proof(proof,1)
    def test_issued_freeze_SHA_format_rejects_before_any_read(self):
        with patch.object(c,'read',side_effect=AssertionError('No read under invalid issued SHA')):
            with self.assertRaises(ValueError):c.load('/unused',True)
    def test_raw_helper_executes_same_pinned_read_object(self):
        raw=b'MARKER="pinned"\n'
        class Stream:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def read(self,*_):return raw
        with patch.object(Path,'open',return_value=Stream()):
            loaded=c.raw_module('/tmp/literal-fixture.py',hashlib.sha256(raw).hexdigest(),'chosen3_literal_marker')
            self.assertEqual(loaded.MARKER,'pinned')
            with self.assertRaises(ValueError):c.raw_module('/tmp/literal-fixture.py','0'*64,'chosen3_literal_wrong')


if __name__=='__main__':unittest.main(verbosity=2)
