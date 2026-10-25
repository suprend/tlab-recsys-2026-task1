"""Synthetic byte/JSON contracts on D:; no customer data, SQL or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import hm_auto_holdout_lock as gate
from scripts import hm_auto_regularization as regularization
from scripts import hm_auto_select as selection


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    return selection.digest(path.read_bytes())


class HoldoutLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hm-customer-lock-', dir='D:/' if Path('D:/').is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for module in (gate, selection, regularization):
            change = patch.object(module, 'ROOT', self.root)
            change.start(); self.addCleanup(change.stop)
        self.runtime = dict(python='fixture', platform='fixture', packages={'fixture': '1'},
                            threads=4, duckdb_memory_limit='2GB')
        runtime_patch = patch.object(gate, 'runtime_identity', return_value=self.runtime)
        runtime_patch.start(); self.addCleanup(runtime_patch.stop)
        self.code = {}
        for name in gate.CODE_NAMES:
            target = self.root/'scripts'/name; target.parent.mkdir(exist_ok=True)
            target.write_bytes(('synthetic source '+name).encode())
            self.code[name] = selection.digest(target.read_bytes())
        old = {name: sha for name, sha in self.code.items() if not name.startswith('hm_auto_')}
        self.protocol = dict(v1_frozen=dict(source=old), development=dict(
            train_anchors=[gate.ANCHORS[:3], gate.ANCHORS[:4]]))
        protocol_sha = write(self.root/selection.PROTOCOL, self.protocol)
        pin = patch.object(selection, 'PROTOCOL_SHA', protocol_sha)
        pin.start(); self.addCleanup(pin.stop)
        self.manual = dict(numeric=[f'n{i}' for i in range(18)], categorical=[f'c{i}' for i in range(5)])
        self.programs = ['auto_index_code_count7', 'auto_index_code_recency90']
        self.features = dict(M=self.manual, E=dict(numeric=self.manual['numeric']+self.programs,
                                                   categorical=self.manual['categorical']))
        self.contract = dict(digest='f'*64, registry=[dict(name=name, kind=kind)
            for kind, names in self.features['E'].items() for name in names])
        self.params = gate.legacy.fixed_parameters(500, 8, 2026, task_type='GPU')
        self.params.pop('random_seed')
        self.database = self.binary('artifacts/fixture.duckdb', b'not a database')
        self.trains, self.identities, old_cohorts = [], {}, []
        for anchor in gate.ANCHORS:
            folder = f'artifacts/hm-campaign/collections/{anchor}-c0q120'
            files = self.files(folder, ('frame.parquet', 'users.parquet', 'targets.parquet'))
            manifest = dict(format='hm-experiment-collection-v1', status='completed', anchor=anchor,
                horizon_days=7, cohort_seed=2026, policy='C0-Q120', requested_users=20000,
                database={key:self.database[key] for key in ('sha256','bytes')},
                code={'hm_feature_engine.py':self.code['hm_feature_engine.py'], 'historical_producer':'allowed'},
                features=self.contract, files=files,
                qcy_identity=selection.canonical({key:files[key] for key in ('users.parquet','targets.parquet')}),
                candidate_identity=selection.digest(anchor.encode()))
            manifest_sha = write(self.root/folder/'manifest.json', manifest)
            users = self.binary(folder+'/users.parquet')
            self.trains.append(dict(anchor=anchor, manifest=dict(path=folder+'/manifest.json',sha256=manifest_sha),users=users))
            old_cohorts.append(dict(anchor=anchor, path=(self.root/users['path']).as_posix(), users=20000,
                covered_by_reconstruction=True, sha256=users['sha256'], bytes=users['bytes']))
            self.identities[anchor] = dict(anchor=anchor,manifest_sha256=manifest_sha,
                qcy_identity=manifest['qcy_identity'],candidate_identity=manifest['candidate_identity'])
        reservation_files = {name:self.binary('artifacts/hm-auto-v2/reservation/'+name, name.encode())
            for name in ('reserved-users.parquet','excluded-users.parquet')}
        self.reservation = dict(format='hm-auto-v2-customer-reservation-v1',status='completed',
            no_test_targets_or_features=True,cutoff='2020-09-16',history_days=90,
            config=dict(sha256=protocol_sha),source=dict(sha256=self.code['hm_auto_reserve.py']),
            database=dict(sha256=self.database['sha256'],bytes=self.database['bytes'],opened_read_only=True),
            files={name:{key:pin[key] for key in ('sha256','bytes')} for name,pin in reservation_files.items()},
            counts_history_only=dict(reserved_users=20000,overlap_users=0,actual_old_cohorts=old_cohorts,
                reserved_ordered_ids_sha256='a'*64,excluded_ordered_ids_sha256='b'*64))
        reservation_sha = write(self.root/gate.RESERVATION_PATH,self.reservation)
        reserve_pin = patch.object(gate,'RESERVATION_SHA',reservation_sha)
        reserve_pin.start();self.addCleanup(reserve_pin.stop)
        self.group = dict(status='completed',stage=2,width=2,run_symmetric_L2=True,
            selected_programs=self.programs,selected_names=self.manual['numeric']+self.manual['categorical']+self.programs)
        group_sha = write(self.root/regularization.GROUP_DECISION,self.group)
        self.l2_plan = dict(format='hm-auto-l2-plan-v2',protocol=dict(path=selection.PROTOCOL,sha256=protocol_sha),
            selection=dict(path=regularization.GROUP_DECISION,sha256=group_sha),
            sources={name:self.code[name] for name in regularization.SOURCES},features=self.features,folds=[])
        self.provenance = {selection.PROTOCOL:protocol_sha,regularization.GROUP_DECISION:group_sha}
        cells=[]
        points={arm:{l2:[] for l2 in (10,50)} for arm in ('M','E')}
        for fold,anchor in enumerate(selection.ANCHORS):
            item=dict(anchor=anchor,M50=f'artifacts/hm-auto-v2/l2/M50/{anchor}',
                E50=f'artifacts/hm-auto-v2/l2/E50/{anchor}',audit=f'artifacts/hm-auto-v2/audits/l2-{anchor}/report.json')
            audit=dict(format='hm-independent-result-audit-v1',status='PASS',
                checker_sha256=self.code['hm_result_audit.py'],
                source_rebuild='PASS: raw history-only SHA256 Q and full distinct weekly Y',
                collection=dict(self.identities[anchor],policy='C0-Q120',
                    database_identity={key:self.database[key] for key in ('sha256','bytes')}),fits=[])
            for index,(arm,l2) in enumerate(regularization.CELLS):
                relative=(f'artifacts/hm-auto-v2/reused/{arm}/{anchor}/report.json' if l2==10 else item[arm+'50']+'/report.json')
                point={('M',10):.25,('E',10):.5,('M',50):.375,('E',50):.625}[(arm,l2)]+fold*.125
                points[arm][l2].append(point)
                metrics=dict(queries=20000,positive_queries=1000,empty_target_queries=19000,
                    distinct_query_target_pairs=3000,candidate_query_coverage_conditional=.25,
                    candidate_target_coverage_micro=.1,oracle_map_at_12_conditional=.875,map_at_12_conditional=point)
                code=({name:self.code[name] for name in ('hm_experiment.py','hm_baseline.py')} if l2==10 else
                      {name:self.code[name] for name in regularization.NEW_FIT_SOURCES})
                report=dict(format='hm-experiment-fit-v1',status='completed',fit_count=1,actual_trees=500,
                    training_user_limit=20000,negative_sample=20,sampling_seed=2026,
                    features=dict(self.features[arm],contract_digest=self.contract['digest']),
                    hyperparameters=dict(self.params,l2_leaf_reg=l2,random_seed=2026),runtime=self.runtime,code=code,
                    inputs=[self.identities[a] for a in gate.ANCHORS[:3+fold]+[anchor]],validation_metrics=metrics)
                report['fit_identity']=selection.fit_identity(report)
                sha=write(self.root/relative,report);self.provenance[relative]=sha
                if l2==10:item[arm+'10']=dict(path=relative,sha256=sha)
                cells.append(dict(anchor=anchor,arm=arm,l2_leaf_reg=l2,audited_map=point,path=relative,
                    report_sha256=sha,fit_identity=report['fit_identity']))
                audit['fits'].append(dict(arm=index,fit_directory=(self.root/relative).parent.as_posix(),
                    report_sha256=sha,fit_identity=report['fit_identity'],metrics=metrics,
                    code={name:dict(recorded_sha256=sha,current_source_matches=True) for name,sha in code.items()}))
            self.provenance[item['audit']]=write(self.root/item['audit'],audit)
            self.l2_plan['folds'].append(item)
        self.l2_path='artifacts/hm-auto-v2/plans/l2.json'
        l2_sha=write(self.root/self.l2_path,self.l2_plan);self.provenance[self.l2_path]=l2_sha
        self.l2_decision=dict(format='hm-auto-l2-decision-v2',status='completed',phase='symmetric_regularization',
            plan=dict(path=self.l2_path,sha256=l2_sha),selection=self.l2_plan['selection'],
            **regularization.choose_l2(points),cells=cells,implementation_sha256=self.code['hm_auto_regularization.py'],
            provenance=self.provenance)
        self.decision_path='artifacts/hm-auto-v2/decisions/l2/report.json'
        decision_sha=write(self.root/self.decision_path,self.l2_decision)
        self.value=dict(format='hm-auto-holdout-lock-v2',protocol=self.l2_plan['protocol'],
            l2_plan=dict(path=self.l2_path,sha256=l2_sha),l2_decision=dict(path=self.decision_path,sha256=decision_sha),
            reservation=dict(manifest=dict(path=gate.RESERVATION_PATH,sha256=reservation_sha),files=reservation_files,
                reserved_ordered_ids_sha256='a'*64,excluded_ordered_ids_sha256='b'*64),
            train_collections=self.trains,database=self.database,features=self.features,
            hyperparameters={arm:dict(self.params,l2_leaf_reg=50) for arm in ('M','E')},
            training=deepcopy(gate.TRAINING),cohort=deepcopy(gate.COHORT),
            implementation=dict(code=self.code,runtime=self.runtime),outputs=deepcopy(gate.OUTPUTS),inference=deepcopy(gate.INFERENCE))
        self.lock_path=self.root/gate.LOCK_PATH
        self.sha=write(self.lock_path,self.value)
        # The frozen validator has its own full replay tests. This fixture
        # isolates the new gate's byte/identity checks from that large chain.
        self.context=dict(plan=self.l2_plan,selection=self.group,records=dict(self.provenance),
            context=dict(manual=self.manual,lock=dict(feature_digest=self.contract['digest'],
                hyperparameters=self.params,database={key:self.database[key] for key in ('sha256','bytes')})))
        replay_patch=patch.object(regularization,'validate_plan',return_value=self.context)
        self.replay=replay_patch.start();self.addCleanup(replay_patch.stop)

    def binary(self,relative,raw=None):
        target=self.root/relative
        if raw is not None:
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        return dict(path=relative,sha256=selection.digest(target.read_bytes()),bytes=target.stat().st_size)

    def files(self,folder,names):
        return {name:self.binary(folder+'/'+name,(folder+name).encode())['sha256'] for name in names}

    def load(self):return gate.load_lock(self.lock_path,self.sha)

    def save(self):self.sha=write(self.lock_path,self.value)

    def collection(self):
        folder=gate.OUTPUTS['collection'];files=self.files(folder,('frame.parquet','users.parquet','targets.parquet'))
        manifest=dict(format='hm-auto-holdout-collection-v2',status='completed',holdout_lock_sha256=self.sha,
            anchor='2020-09-16',horizon_days=7,policy='C0-Q120',requested_users=20000,cohort=gate.COHORT,
            database={key:self.database[key] for key in ('sha256','bytes')},features=self.contract,
            reservation_manifest_sha256=gate.RESERVATION_SHA,reserved_ordered_ids_sha256='a'*64,excluded_ordered_ids_sha256='b'*64,
            id_checks=dict(reserved_users=20000,excluded_overlap_users=0,training_overlap_users=0),
            code=self.code,runtime=self.runtime,files=files,candidate_identity='c'*64,
            qcy_identity=selection.canonical({key:files[key] for key in ('users.parquet','targets.parquet')}))
        write(self.root/folder/'manifest.json',manifest)
        return self.root/folder

    def fit_reports(self,plan,collection):
        manifest,identity=gate.collection_manifest(plan.data,plan.sha256,collection)
        for index,relative in enumerate(gate.OUTPUTS['fits']):
            arm,seed=('M' if index<2 else 'E'),2026+index%2
            report=dict(format='hm-auto-holdout-fit-v2',status='completed',fit_count=1,actual_trees=500,
                holdout_lock_sha256=self.sha,holdout_arm=arm,reservation_manifest_sha256=gate.RESERVATION_SHA,cohort=gate.COHORT,
                training_user_limit=20000,negative_sample=20,sampling_seed=2026,
                hyperparameters=dict(self.value['hyperparameters'][arm],random_seed=seed),
                resolved_model_parameters=dict(self.value['hyperparameters'][arm],random_seed=seed),
                features=dict(self.features[arm],contract_digest=self.contract['digest']),code=self.code,runtime=self.runtime,
                inputs=gate.train_identities(plan.data)+[identity],
                files=self.files(relative,('model.cbm','query-metrics.parquet','predictions-top12.parquet')))
            report['fit_identity']=gate.fit_identity(report)
            write(self.root/relative/'report.json',report)
        return [self.root/p for p in gate.OUTPUTS['fits']]

    def test_valid_metadata_then_collection_four_slots_and_audit(self):
        plan=self.load();self.replay.assert_called_with(self.root/self.l2_path,self.value['l2_plan']['sha256'])
        gate.authorize_collect(plan,self.root/self.database['path'],self.root/gate.OUTPUTS['collection'])
        self.assertFalse((self.root/gate.OUTPUTS['collection']).exists())
        collection=self.collection()
        for index,(arm,seed) in enumerate((('M',2026),('M',2027),('E',2026),('E',2027))):
            result=gate.authorize_fit(plan,arm,seed,[(self.root/p['manifest']['path']).parent for p in self.trains],
                collection,self.root/gate.OUTPUTS['fits'][index])
            self.assertEqual(result['fit_index'],index);self.assertEqual(result['hyperparameters']['l2_leaf_reg'],50)
            self.assertEqual(result['hyperparameters']['random_seed'],seed)
        fits=self.fit_reports(plan,collection)
        gate.authorize_audit(plan,collection,fits,self.root/gate.OUTPUTS['audit'])
        self.assertFalse((self.root/gate.OUTPUTS['audit']).exists())

    def test_explicit_sha_duplicate_json_and_mutated_plan_fail(self):
        for sha in (None,'','0'*64):
            with self.subTest(sha=sha),self.assertRaises(ValueError):gate.load_lock(self.lock_path,sha)
        plan=self.load();plan.data['training']['negative_sample']=21
        with self.assertRaisesRegex(ValueError,'mutated'):gate.authorize_collect(plan,self.root/self.database['path'],self.root/gate.OUTPUTS['collection'])
        self.lock_path.write_text('{"format":1,"format":2}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Duplicate'):gate.load_lock(self.lock_path,selection.digest(self.lock_path.read_bytes()))

    def test_source_runtime_and_19_pin_inventory_are_exact(self):
        for change in (lambda v:v['implementation']['runtime'].update(threads=2),
                       lambda v:v['implementation']['code'].pop('hm_auto_holdout_audit.py'),
                       lambda v:v['implementation']['code'].update({'hm_experiment.py':'0'*64})):
            saved=deepcopy(self.value);change(self.value);self.save()
            with self.assertRaises(ValueError):self.load()
            self.value=saved;self.save()
        (self.root/'scripts/hm_auto_holdout.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'source changed'):self.load()

    def test_ineligible_or_nonempty_claim_cannot_bypass_replayed_selection(self):
        self.l2_decision['candidate_eligible']=False
        self.value['l2_decision']['sha256']=write(self.root/self.decision_path,self.l2_decision);self.save()
        with patch.object(gate,'byte_pin',side_effect=AssertionError('must fail before B byte reads')):
            with self.assertRaisesRegex(ValueError,'eligible L2'):self.load()
        self.l2_decision['candidate_eligible']=True
        self.value['l2_decision']['sha256']=write(self.root/self.decision_path,self.l2_decision);self.save()
        self.context['selection']=dict(self.group,selected_programs=['other'])
        with patch.object(gate,'byte_pin',side_effect=AssertionError('must fail before B byte reads')):
            with self.assertRaisesRegex(ValueError,'replayed accepted expansion'):self.load()

    def test_zero_width_is_rejected_even_with_eligible_l2_claim(self):
        self.group['width']=0
        group_sha=write(self.root/regularization.GROUP_DECISION,self.group)
        self.l2_plan['selection']['sha256']=group_sha
        self.value['l2_plan']['sha256']=write(self.root/self.l2_path,self.l2_plan)
        self.context['records'][regularization.GROUP_DECISION]=group_sha
        self.context['records'][self.l2_path]=self.value['l2_plan']['sha256']
        self.l2_decision['plan']=deepcopy(self.value['l2_plan'])
        self.l2_decision['selection']=deepcopy(self.l2_plan['selection'])
        self.value['l2_decision']['sha256']=write(self.root/self.decision_path,self.l2_decision);self.save()
        with patch.object(gate,'byte_pin',side_effect=AssertionError('must fail before B byte reads')):
            with self.assertRaisesRegex(ValueError,'Nonempty'):self.load()

    def test_cohort_fake_seed_feature_order_recipe_and_output_changes_fail(self):
        changes=(lambda v:v['cohort'].update(cohort_seed=2026),lambda v:v['training'].update(model_seeds=[2027,2026]),
            lambda v:v['features']['E']['numeric'].reverse(),lambda v:v['hyperparameters']['E'].update(l2_leaf_reg=10),
            lambda v:v['outputs'].update(collection='artifacts/hm-campaign/final'),
            lambda v:v['inference']['bootstrap'].update(draws=1000))
        for change in changes:
            saved=deepcopy(self.value);change(self.value);self.save()
            with self.assertRaises(ValueError):self.load()
            self.value=saved;self.save()

    def test_rehashed_l2_audit_still_requires_checker_counts_source_and_qcy(self):
        relative=self.l2_plan['folds'][0]['audit'];target=self.root/relative
        original_audit=json.loads(target.read_text(encoding='utf-8'))
        original_decision=deepcopy(self.l2_decision)
        changes=(lambda a:a.update(status='FAIL'),lambda a:a.update(checker_sha256='0'*64),
            lambda a:a['fits'][0].update(arm=True),lambda a:a['fits'][0]['metrics'].update(queries=20000.0),
            lambda a:a['fits'][0]['code']['hm_experiment.py'].update(current_source_matches=False),
            lambda a:a['collection'].update(qcy_identity='0'*64))
        for change in changes:
            audit=deepcopy(original_audit);change(audit);sha=write(target,audit)
            self.l2_decision=deepcopy(original_decision);self.l2_decision['provenance'][relative]=sha
            self.context['records']=dict(self.l2_decision['provenance'])
            self.value['l2_decision']['sha256']=write(self.root/self.decision_path,self.l2_decision);self.save()
            with patch.object(gate,'byte_pin',side_effect=AssertionError('must fail before B byte reads')):
                with self.subTest(change=change),self.assertRaises(ValueError):self.load()

    def test_nonfinite_lock_and_path_escape_fail_without_outputs(self):
        raw=self.lock_path.read_text(encoding='utf-8')
        self.lock_path.write_text(raw.replace('"gpu_ram_part": 0.5','"gpu_ram_part": 1e999'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Nonfinite'):
            gate.load_lock(self.lock_path,selection.digest(self.lock_path.read_bytes()))
        self.save();self.value['database']['path']='../outside.duckdb';self.save()
        with self.assertRaises(ValueError):self.load()
        self.assertFalse((self.root/gate.OUTPUTS['collection']).exists())

    def test_reservation_and_supervised_users_bytes_must_match_certificate(self):
        for target in (self.value['reservation']['files']['reserved-users.parquet']['path'],self.trains[0]['users']['path']):
            file=self.root/target;raw=file.read_bytes();file.write_bytes(raw+b'changed')
            with self.assertRaisesRegex(ValueError,'byte identity'):self.load()
            file.write_bytes(raw)
        self.value['train_collections'][0]['users']['sha256']='0'*64;self.save()
        with self.assertRaisesRegex(ValueError,'exclusion certificate'):self.load()

    def test_invalid_request_and_output_fail_before_database_hash(self):
        plan=self.load();original=gate.byte_pin
        with patch.object(gate,'byte_pin',side_effect=lambda ref,records: (_ for _ in ()).throw(AssertionError('DB read'))
                          if ref['path']==self.database['path'] else original(ref,records)):
            with self.assertRaises(ValueError):gate.authorize_collect(plan,self.root/'wrong.duckdb',self.root/gate.OUTPUTS['collection'])
        target=self.root/gate.OUTPUTS['collection'];target.mkdir(parents=True)
        with self.assertRaises(ValueError):gate.authorize_collect(plan,self.root/self.database['path'],target)

    def test_database_bytes_checked_only_by_collect(self):
        target=self.root/self.database['path'];target.write_bytes(b'changed database')
        plan=self.load()
        with self.assertRaisesRegex(ValueError,'byte identity'):gate.authorize_collect(plan,target,self.root/gate.OUTPUTS['collection'])

    def test_fit_denies_wrong_seed_training_order_collection_marker_and_existing_output(self):
        plan=self.load();collection=self.collection();trains=[(self.root/item['manifest']['path']).parent for item in self.trains]
        for arm,seed,paths,out in (('M',True,trains,gate.OUTPUTS['fits'][0]),('M',2028,trains,gate.OUTPUTS['fits'][0]),
            ('M',2026,list(reversed(trains)),gate.OUTPUTS['fits'][0]),('M',2026,trains,gate.OUTPUTS['fits'][2])):
            with self.assertRaises(ValueError):gate.authorize_fit(plan,arm,seed,paths,collection,self.root/out)
        file=collection/'manifest.json';manifest=json.loads(file.read_text(encoding='utf-8'));manifest['cohort_seed']=2026;write(file,manifest)
        with self.assertRaisesRegex(ValueError,'collection lock'):gate.authorize_fit(plan,'M',2026,trains,collection,self.root/gate.OUTPUTS['fits'][0])

    def test_produced_qcy_and_inventory_hash_are_verified(self):
        plan=self.load();collection=self.collection();file=collection/'manifest.json'
        manifest=json.loads(file.read_text(encoding='utf-8'));manifest['qcy_identity']='0'*64;write(file,manifest)
        with self.assertRaisesRegex(ValueError,'Q/C/Y'):gate.collection_manifest(plan.data,self.sha,collection)
        self.collection();(collection/'targets.parquet').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'byte identity'):gate.collection_manifest(plan.data,self.sha,collection)

    def test_audit_requires_four_ordered_completed_fit_identities(self):
        plan=self.load();collection=self.collection();fits=self.fit_reports(plan,collection)
        for paths in (fits[:3],list(reversed(fits))):
            with self.assertRaises(ValueError):gate.authorize_audit(plan,collection,paths,self.root/gate.OUTPUTS['audit'])
        file=fits[2]/'report.json';report=json.loads(file.read_text(encoding='utf-8'))
        for change in (lambda r:r.update(holdout_arm='M'),lambda r:r.update(actual_trees=True),
                       lambda r:r['hyperparameters'].update(l2_leaf_reg=10),lambda r:r.update(fit_identity='0'*64),
                       lambda r:r['resolved_model_parameters'].update(task_type='CPU')):
            bad=deepcopy(report);change(bad);write(file,bad)
            with self.assertRaisesRegex(ValueError,'fit identity/recipe'):gate.authorize_audit(plan,collection,fits,self.root/gate.OUTPUTS['audit'])

    def test_replay_failure_and_post_read_freshness_abort(self):
        self.replay.side_effect=ValueError('replayed group chain differs')
        with self.assertRaisesRegex(ValueError,'replayed group'):self.load()
        self.replay.side_effect=None
        original=gate.l2_evidence
        def mutate(*args):
            result=original(*args)
            with (self.root/self.decision_path).open('a',encoding='utf-8') as stream:stream.write(' ')
            return result
        with patch.object(gate,'l2_evidence',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'changed during validation'):self.load()


if __name__=='__main__':unittest.main()
