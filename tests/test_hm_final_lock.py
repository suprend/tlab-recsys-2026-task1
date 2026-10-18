"""Pure stdlib final-gate fixtures; never open the real H&M database."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import hm_final_lock as gate


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


class FinalLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.patcher = patch.object(gate, 'ROOT', self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.database = dict(sha256='a' * 64, bytes=123)
        self.runtime = dict(python='3.12.14', packages={'fixture': '1.0'}, threads=4)
        runtime_patch = patch.object(gate, 'runtime_identity', return_value=deepcopy(self.runtime))
        runtime_patch.start()
        self.addCleanup(runtime_patch.stop)
        self.code = {}
        for name in ('hm_experiment.py', 'hm_baseline.py', 'hm_feature_engine.py', 'hm_retrieval.py', 'hm_result_audit.py', 'hm_final_lock.py'):
            path = self.root / 'scripts' / name
            path.parent.mkdir(exist_ok=True)
            path.write_text('# frozen synthetic code\n', encoding='utf-8')
            self.code[name] = gate.digest(path)
        def ref(name):
            path = self.root / name
            write(path, {'synthetic': name})
            return dict(path=name, sha256=gate.digest(path))
        self.plan = dict(
            format='hm-final-decision-lock-v1', campaign=ref('configs/campaign.json'),
            provenance={k: ref('artifacts/development/' + k + '.json') for k in ('manual', 'selection', 'confirmation')},
            database=self.database, feature_digest='b' * 64,
            implementation=dict(code=self.code, runtime=self.runtime),
            final=dict(anchor=gate.FINAL, horizon_days=7, policy='C0-Q120', users=20000,
                       cohort_seed=2026, sampling_seed=2026, train_users=20000, negative_sample=20),
            train_collections=[], features=dict(M=dict(numeric=['x'], categorical=['c']),
                selected=dict(numeric=['x'] + ['g' + str(i) for i in range(12)], categorical=['c'])),
            hyperparameters=dict(iterations=500, depth=6, learning_rate=.05, l2_leaf_reg=10,
                loss_function='Logloss', thread_count=4, task_type='CPU', verbose=False, allow_writing_files=False),
            outputs=dict(collection='artifacts/final/collection',
                fits=['artifacts/final/' + a for a in ('M2026', 'M2027', 'selected2026', 'selected2027')],
                audit='artifacts/final/audit'), contrasts=deepcopy(gate.CONTRASTS))
        for anchor in gate.ANCHORS:
            name = 'artifacts/training/' + anchor + '/manifest.json'
            write(self.root / name, self.manifest(anchor))
            self.plan['train_collections'].append(dict(path=name, sha256=gate.digest(self.root / name)))
        self.lockpath = self.root / 'configs/final-lock.json'
        self.save_lock()

    def manifest(self, anchor):
        return dict(format='hm-experiment-collection-v1', status='completed', anchor=anchor,
            horizon_days=7, cohort_seed=2026, policy='C0-Q120', requested_users=20000,
            database=self.database, features=dict(digest='b' * 64, registry=[
                dict(name=name, kind=kind) for kind, names in dict(numeric=['x'] + ['g' + str(i) for i in range(12)], categorical=['c']).items() for name in names]),
            files={n: 'c' * 64 for n in ('frame.parquet', 'users.parquet', 'targets.parquet')},
            qcy_identity='d' * 64, candidate_identity='e' * 64,
            runtime=self.runtime, code=self.code)

    def save_lock(self):
        write(self.lockpath, self.plan)
        return gate.load_lock(self.lockpath)

    def collect_request(self):
        return dict(output=self.plan['outputs']['collection'], **{k: self.plan['final'][k]
            for k in ('anchor', 'users', 'policy', 'cohort_seed', 'horizon_days')})

    def final_manifest(self, lock):
        path = self.root / self.plan['outputs']['collection'] / 'manifest.json'
        write(path, dict(self.manifest(gate.FINAL), final_lock_sha256=lock.sha256))
        return path

    def trainidentities(self):
        return [gate.identity(self.root / ref['path']) for ref in self.plan['train_collections']]

    def fit_request(self, number):
        arm = 'M' if number < 2 else 'selected'
        return dict(output=self.plan['outputs']['fits'][number], validation=self.plan['outputs']['collection'],
            **self.plan['features'][arm], hyperparameters=dict(self.plan['hyperparameters'], random_seed=(2026, 2027)[number % 2]),
            train_users=20000, negative_sample=20, sampling_seed=2026)

    def fit_reports(self, lock, manifest):
        paths = []
        for number in range(4):
            request = self.fit_request(number)
            path = self.root / request['output'] / 'report.json'
            report = dict(format='hm-experiment-fit-v1', status='completed', final_lock_sha256=lock.sha256,
                features=dict(numeric=request['numeric'], categorical=request['categorical'], contract_digest='b' * 64),
                hyperparameters=request['hyperparameters'], training_user_limit=20000, negative_sample=20,
                sampling_seed=2026, fit_count=1, actual_trees=500,
                inputs=self.trainidentities() + [gate.identity(manifest)], runtime=self.runtime,
                code={k: self.code[k] for k in ('hm_experiment.py', 'hm_baseline.py')})
            write(path, report)
            paths.append(path)
        return paths

    def test_complete_four_fit_contract_and_seed_mean_contrasts(self):
        lock = gate.load_lock(self.lockpath)
        gate.authorize_collect(lock, self.collect_request(), self.database, 'b' * 64)
        manifest = self.final_manifest(lock)
        for number, arm in enumerate(('M', 'M', 'selected', 'selected')):
            self.assertEqual(gate.authorize_fit(lock, self.fit_request(number), self.trainidentities(), manifest), arm)
        paths = self.fit_reports(lock, manifest)
        self.assertEqual(gate.authorize_audit(lock, manifest, paths), self.root / 'artifacts/final/audit')
        self.assertEqual(lock.data['contrasts'][0]['positive'], ['arm-02', 'arm-03'])

    def test_gpu_lock_keeps_four_seed_arms_and_rejects_recipe_or_cpu_substitution(self):
        extras=dict(devices='0',gpu_ram_part=.5,pinned_memory_size='256mb',bootstrap_type='Bayesian',
                    bagging_temperature=1,border_count=128,boosting_type='Plain')
        self.plan['hyperparameters'].update(task_type='GPU',**extras)
        lock=self.save_lock()
        manifest=self.final_manifest(lock)
        for number,arm in enumerate(('M','M','selected','selected')):
            self.assertEqual(gate.authorize_fit(lock,self.fit_request(number),self.trainidentities(),manifest),arm)
        paths=self.fit_reports(lock,manifest)
        self.assertEqual(gate.authorize_audit(lock,manifest,paths),self.root/'artifacts/final/audit')
        cpu_request=self.fit_request(0)
        cpu_request['hyperparameters']={k:v for k,v in cpu_request['hyperparameters'].items() if k not in extras}
        cpu_request['hyperparameters']['task_type']='CPU'
        with self.assertRaises(ValueError): gate.authorize_fit(lock,cpu_request,self.trainidentities(),manifest)
        original=deepcopy(self.plan['hyperparameters'])
        for key,value in (('devices','1'),('gpu_ram_part',.9),('pinned_memory_size','512mb'),
                          ('bootstrap_type','MVS'),('bagging_temperature',0),('border_count',254),('boosting_type','Ordered')):
            self.plan['hyperparameters']=dict(original,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError): self.save_lock()
        self.plan['hyperparameters']=original

    def test_active_gpu_campaign_rejects_cpu_lock_and_accepts_matching_gpu(self):
        campaign=self.root/self.plan['campaign']['path']
        write(campaign,{'execution':{'task_type':'GPU'}})
        self.plan['campaign']['sha256']=gate.digest(campaign)
        with self.assertRaisesRegex(ValueError,'active campaign backend'):
            self.save_lock()
        self.plan['hyperparameters'].update(task_type='GPU',devices='0',gpu_ram_part=.5,
            pinned_memory_size='256mb',bootstrap_type='Bayesian',bagging_temperature=1,border_count=128,boosting_type='Plain')
        lock=self.save_lock()
        self.assertEqual(lock.data['hyperparameters']['task_type'],'GPU')


    def test_duplicate_json_and_nonfinite_constants_rejected(self):
        for text in ('{"format":1,"format":2}', '{"outer":{"x":1,"x":2}}', '{"x":NaN}', '{"x":Infinity}'):
            self.lockpath.write_text(text, encoding='utf-8')
            with self.assertRaises(ValueError):
                gate.load_lock(self.lockpath)

    def test_unknown_properties_and_wrong_fixed_protocol_rejected(self):
        for key, value in (('unexpected', True), ('final', dict(self.plan['final'], anchor='2020-09-09')),
                           ('final', dict(self.plan['final'], cohort_seed=2027)), ('contrasts', list(reversed(gate.CONTRASTS)))):
            original = deepcopy(self.plan)
            self.plan[key] = value
            with self.assertRaises(ValueError):
                self.save_lock()
            self.plan = original

    def test_training_order_duplicates_and_modified_bytes_rejected(self):
        original = deepcopy(self.plan)
        self.plan['train_collections'].reverse()
        with self.assertRaises(ValueError): self.save_lock()
        self.plan = deepcopy(original)
        self.plan['train_collections'][1] = self.plan['train_collections'][0]
        with self.assertRaises(ValueError): self.save_lock()
        self.plan = original
        lock = self.save_lock()
        (self.root / self.plan['train_collections'][0]['path']).write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError): gate.authorize_collect(lock, self.collect_request(), self.database, 'b' * 64)

    def test_immutable_lock_data_and_changed_lock_file(self):
        lock = gate.load_lock(self.lockpath)
        lock.data['final']['users'] = 1
        self.assertEqual(lock.data['final']['users'], 20000)
        self.lockpath.write_text(self.lockpath.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        with self.assertRaises(ValueError): gate.authorize_collect(lock, self.collect_request(), self.database, 'b' * 64)

    def test_source_code_and_development_provenance_drift_rejected(self):
        lock = gate.load_lock(self.lockpath)
        for path in (self.root / 'scripts/hm_experiment.py', self.root / self.plan['provenance']['confirmation']['path']):
            previous = path.read_bytes()
            path.write_bytes(previous + b' ')
            with self.assertRaises(ValueError): gate.authorize_collect(lock, self.collect_request(), self.database, 'b' * 64)
            path.write_bytes(previous)
        with patch.object(gate, 'runtime_identity', return_value=dict(self.runtime, threads=2)):
            with self.assertRaises(ValueError): gate.authorize_collect(lock, self.collect_request(), self.database, 'b' * 64)

    def test_portable_disjoint_artifact_paths_required(self):
        for name in ('../outside', 'D:/absolute/final', 'artifacts\\final', 'scripts/output', 'artifacts'):
            with self.subTest(path=name):
                self.plan['outputs']['collection'] = name
                with self.assertRaises(ValueError): self.save_lock()
        self.plan['outputs']['collection'] = self.plan['outputs']['fits'][0]
        with self.assertRaises(ValueError): self.save_lock()
        self.plan['outputs']['collection'] = 'artifacts/final'
        with self.assertRaises(ValueError): self.save_lock()

    def test_feature_order_kind_duplicates_and_bundle_size_frozen(self):
        for mutate in (lambda f: f['M']['numeric'].append('label'),
                       lambda f: f['M']['categorical'].append('x'),
                       lambda f: f['selected']['numeric'].pop(),
                       lambda f: f['selected']['categorical'].clear()):
            original = deepcopy(self.plan['features'])
            mutate(self.plan['features'])
            with self.assertRaises(ValueError): self.save_lock()
            self.plan['features'] = original

    def test_unknown_feature_and_schema_drift_rejected_before_collection(self):
        original = deepcopy(self.plan)
        self.plan['features']['M']['numeric'] = ['unknown']
        self.plan['features']['selected']['numeric'][0] = 'unknown'
        with self.assertRaises(ValueError): self.save_lock()
        self.plan = original
        ref = self.plan['train_collections'][1]
        path = self.root / ref['path']
        manifest = gate.read_json(path)
        manifest['features']['registry'][0]['kind'] = 'categorical'
        write(path, manifest)
        ref['sha256'] = gate.digest(path)
        with self.assertRaises(ValueError): self.save_lock()

    def test_collection_request_source_and_existing_output_fail_closed(self):
        lock = gate.load_lock(self.lockpath)
        for key, value in (('anchor', '2020-09-17'), ('users', 5000), ('policy', 'C1-Q120'), ('output', 'artifacts/unfrozen')):
            request = dict(self.collect_request(), **{key: value})
            with self.assertRaises(ValueError): gate.authorize_collect(lock, request, self.database, 'b' * 64)
        with self.assertRaises(ValueError): gate.authorize_collect(lock, self.collect_request(), dict(self.database, bytes=124), 'b' * 64)
        with self.assertRaises(ValueError): gate.authorize_collect(lock, self.collect_request(), self.database, 'f' * 64)
        (self.root / self.plan['outputs']['collection']).mkdir(parents=True)
        with self.assertRaises(ValueError): gate.authorize_collect(lock, self.collect_request(), self.database, 'b' * 64)

    def test_fit_wrong_training_recipe_seed_feature_order_and_identity_fail(self):
        lock = gate.load_lock(self.lockpath)
        manifest = self.final_manifest(lock)
        for key, value in (('sampling_seed', 2027), ('train_users', 5000), ('negative_sample', 0),
                           ('numeric', ['wrong']), ('hyperparameters', dict(self.plan['hyperparameters'], random_seed=2027))):
            request = dict(self.fit_request(0), **{key: value})
            with self.assertRaises(ValueError): gate.authorize_fit(lock, request, self.trainidentities(), manifest)
        with self.assertRaises(ValueError): gate.authorize_fit(lock, self.fit_request(0), list(reversed(self.trainidentities())), manifest)
        (self.root / self.plan['outputs']['fits'][0]).mkdir(parents=True)
        with self.assertRaises(ValueError): gate.authorize_fit(lock, self.fit_request(0), self.trainidentities(), manifest)

    def test_final_manifest_lock_runtime_source_schema_and_path_rejected(self):
        lock = gate.load_lock(self.lockpath)
        manifest = self.final_manifest(lock)
        original = gate.read_json(manifest)
        for key, value in (('final_lock_sha256', 'f' * 64), ('anchor', '2020-09-09'), ('runtime', {}), ('code', {}), ('candidate_identity', 'short')):
            write(manifest, dict(original, **{key: value}))
            with self.assertRaises(ValueError): gate.authorize_fit(lock, self.fit_request(0), self.trainidentities(), manifest)
        write(manifest, original)
        with self.assertRaises(ValueError): gate.authorize_fit(lock, self.fit_request(0), self.trainidentities(), self.lockpath)

    def test_historical_training_producer_wrapper_is_allowed(self):
        ref = self.plan['train_collections'][0]
        path = self.root / ref['path']
        manifest = gate.read_json(path)
        manifest['code'] = dict(manifest['code'], **{'hm_experiment.py': 'f' * 64})
        manifest['runtime'] = dict(self.runtime, threads=2)
        write(path, manifest)
        ref['sha256'] = gate.digest(path)
        lock = self.save_lock()
        final = self.final_manifest(lock)
        self.assertEqual(gate.read_json(path)['runtime']['threads'],2)
        self.assertEqual(gate.read_json(final)['runtime']['threads'],4)
        self.assertEqual(lock.data['hyperparameters']['thread_count'],4)
        self.assertEqual(gate.authorize_fit(lock, self.fit_request(0), self.trainidentities(), final), 'M')

    def test_audit_requires_all_fits_exact_order_seed_and_frozen_final_identity(self):
        lock = gate.load_lock(self.lockpath)
        manifest = self.final_manifest(lock)
        paths = self.fit_reports(lock, manifest)
        for supplied in (paths[:3], list(reversed(paths))):
            with self.assertRaises(ValueError): gate.authorize_audit(lock, manifest, supplied)
        original = gate.read_json(paths[0])
        for key, value in (('actual_trees', 499), ('runtime', {}), ('code', {}), ('final_lock_sha256', 'f' * 64), ('inputs', [])):
            write(paths[0], dict(original, **{key: value}))
            with self.assertRaises(ValueError): gate.authorize_audit(lock, manifest, paths)
        write(paths[0], original)
        (self.root / self.plan['outputs']['audit']).mkdir(parents=True)
        with self.assertRaises(ValueError): gate.authorize_audit(lock, manifest, paths)


if __name__ == '__main__':
    unittest.main()
