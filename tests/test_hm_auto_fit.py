"""Tiny cached-data/FakeML witnesses; no native CatBoost fit or production data.

Only the test's runner-local load_part binding caps the 20k request to two
fixture users. The production runner and frozen legacy globals are unchanged.
All temporary files are on D:.
"""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import duckdb
import numpy as np

from scripts import hm_auto_fit as runner
from scripts import hm_experiment as legacy


def write(path, value):
    path.write_text(json.dumps(value, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


class CachedFitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hm-v2-unit-', dir='D:/')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root/'artifacts'/'fit'
        root_patch = patch.object(runner, 'ROOT', self.root)
        root_patch.start(); self.addCleanup(root_patch.stop)
        self.train = self.cache('train', '2020-08-12')
        self.validation = self.cache('validation', '2020-09-02')
        self.calls = []

    def cache(self, name, anchor):
        folder = self.root/name
        folder.mkdir()
        con = duckdb.connect(':memory:')
        try:
            con.sql("""SELECT u customer_id,lpad(i::VARCHAR,3,'0') article_id,
                (u='positive' AND i=1) AS label,120::INTEGER full_candidate_count,
                1.0/120 AS query_weight,i::DOUBLE x,'kind'::VARCHAR c
                FROM (VALUES ('positive'),('empty')) t(u) CROSS JOIN range(120) r(i)
                ORDER BY customer_id,article_id""").write_parquet(str(folder/'frame.parquet'))
            con.sql("""SELECT u customer_id,sha256(u || ':2026') cohort_hash,
                120::INTEGER full_candidate_count FROM (VALUES ('positive'),('empty')) t(u)
                ORDER BY cohort_hash,customer_id""").write_parquet(str(folder/'users.parquet'))
            con.sql("""SELECT * FROM (VALUES ('positive','001'),('positive','off-C'))
                t(customer_id,article_id) ORDER BY customer_id,article_id""").write_parquet(str(folder/'targets.parquet'))
            con.execute('CREATE TEMP TABLE hm_candidates AS SELECT customer_id,article_id FROM read_parquet(?)',
                        [str(folder/'frame.parquet')])
            candidate_identity = legacy.candidate_digest(con, legacy.Deadline(30))
        finally:
            con.close()
        files = {name: legacy.sha256_file(folder/name) for name in
                 ('frame.parquet', 'users.parquet', 'targets.parquet')}
        manifest = dict(format='hm-experiment-collection-v1', status='completed',
            anchor=anchor, horizon_days=7, cohort_seed=2026, policy='C0-Q120', requested_users=20000,
            database=dict(sha256='a'*64, bytes=1), files=files,
            qcy_identity=legacy.canonical_digest({k: files[k] for k in ('users.parquet', 'targets.parquet')}),
            candidate_identity=candidate_identity,
            features=dict(digest='synthetic-contract', registry=[dict(name='x', kind='numeric'),
                dict(name='c', kind='categorical')], feature_sets={'manual_pilot': ['x', 'c']}))
        write(folder/'manifest.json', manifest)
        return folder

    def change_manifest(self, folder, **values):
        manifest = runner.read_json(folder/'manifest.json')
        manifest.update(values)
        write(folder/'manifest.json', manifest)

    def fake_fit(self, l2=10, output=None, resolved=None, actual_trees=500, failure=None, seed=2026):
        calls = self.calls
        class FakeClassifier:
            def __init__(self, **params):
                self.params = params
                self.tree_count_ = actual_trees
                calls.append(params)
            def fit(self, pool):
                # No callbacks, eval_set, early stopping, or label-free training.
                if failure:
                    raise RuntimeError(failure)
                if set(pool.labels) != {0, 1}:
                    raise AssertionError('Training classes lost')
                self.training_weights = pool.weights
                return self
            def get_all_params(self):
                return dict(self.params, **(resolved or {}))
            def save_model(self, path):
                Path(path).write_bytes(b'FakeML model; never loaded by native CatBoost')
            def predict_proba(self, pool, thread_count):
                if thread_count != 4:
                    raise AssertionError('Prediction thread budget changed')
                scores = 1 - pool.numbers[:, 0] / 1000
                return np.column_stack((1-scores, scores))
        def pool(numbers, cats, numeric, categorical, labels=None, weights=None):
            return SimpleNamespace(numbers=numbers, labels=labels, weights=weights)
        def tiny_load(con, path, manifest, names, train_users=None, negative_sample=None):
            return legacy.load_part(con, path, manifest, names,
                                    2 if train_users is not None else None, negative_sample)
        with (patch.dict('sys.modules', {'catboost': SimpleNamespace(CatBoostClassifier=FakeClassifier)}),
              patch.object(runner, 'model_pool', side_effect=pool),
              patch.object(runner, 'load_part', side_effect=tiny_load)):
            return runner.fit([self.train], self.validation, output or self.output, ['c', 'x'], l2,
                              seed=seed, wall_seconds=30)

    def test_l2_reaches_gpu_constructor_resolved_params_and_fit_identity(self):
        legacy_parameters_before = legacy.fixed_parameters(500, 8, 2026, 'GPU')
        first = self.fake_fit(10)
        second = self.fake_fit(50, self.root/'artifacts'/'l2-50')
        self.assertEqual([c['l2_leaf_reg'] for c in self.calls], [10, 50])
        self.assertNotEqual(first['fit_identity'], second['fit_identity'])
        self.assertEqual(legacy.fixed_parameters(500, 8, 2026, 'GPU'), legacy_parameters_before)
        for report, l2 in ((first, 10), (second, 50)):
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(report['hyperparameters']['l2_leaf_reg'], l2)
            self.assertEqual(report['resolved_model_parameters']['l2_leaf_reg'], l2)
            self.assertEqual(report['actual_trees'], 500)
            self.assertEqual(report['last_training_iteration'], 500)
            self.assertEqual(report['fit_count'], 1)
            self.assertEqual(set(report['code']), set(runner.SOURCE_NAMES))
            for name, digest in report['code'].items():
                self.assertEqual(digest, legacy.sha256_file(runner.SOURCE_ROOT/'scripts'/name))
            payload = dict(inputs=report['inputs'], features=report['features'],
                hyperparameters=report['hyperparameters'], train_users=20000, negative_sample=20,
                sampling_seed=2026, code=report['code'], runtime=report['runtime'])
            self.assertEqual(legacy.canonical_digest(payload), report['fit_identity'])
            altered = deepcopy(payload)
            del altered['code']['hm_auto_fit.py']
            self.assertNotEqual(legacy.canonical_digest(altered), report['fit_identity'])
            self.assertEqual(report['features']['numeric'], ['x'])
            self.assertEqual(report['features']['categorical'], ['c'])

    def test_full_truth_empty_query_metrics_and_private_exports_use_hand_answer(self):
        report = self.fake_fit()
        # '001' is ranked second; off-C remains in the full two-item truth.
        metrics = report['validation_metrics']
        self.assertEqual(metrics['map_at_12_conditional'], .25)
        self.assertEqual(metrics['map_at_12_all_queries_empty_zero'], .125)
        self.assertEqual(metrics['recall_at_12_conditional'], .5)
        self.assertEqual(metrics['candidate_target_coverage_micro'], .5)
        self.assertEqual(metrics['queries'], 2)
        self.assertEqual(report['training_populations'][0]['fit_rows'], 41)
        self.assertEqual(report['training_populations'][0]['positive_rows'], 1)
        self.assertAlmostEqual(report['training_populations'][0]['weighted_positive_mass'], 1/120)
        self.assertAlmostEqual(report['training_populations'][0]['weighted_negative_mass'], 239/120)
        con = duckdb.connect(':memory:')
        try:
            rows = con.execute('SELECT customer_id,ap12 FROM read_parquet(?) ORDER BY customer_id',
                               [str(self.output/'query-metrics.parquet')]).fetchall()
            self.assertEqual(rows, [('empty', 0), ('positive', .25)])
            ranking = con.execute("SELECT article_id FROM read_parquet(?) WHERE customer_id='positive' ORDER BY rank",
                                  [str(self.output/'predictions-top12.parquet')]).fetchall()
            self.assertEqual(ranking[:2], [('000',), ('001',)])
        finally:
            con.close()

    def test_legacy_auditor_accepts_new_code_pins_and_recomputes_saved_metrics(self):
        # A separate module instance avoids changing the frozen auditor globals.
        spec = importlib.util.spec_from_file_location('v2_audit_witness',
                    runner.SOURCE_ROOT/'scripts/hm_result_audit.py')
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        audit.ROOT = self.root
        (self.root/'scripts').mkdir()
        for name in runner.SOURCE_NAMES:
            (self.root/'scripts'/name).write_bytes((runner.SOURCE_ROOT/'scripts'/name).read_bytes())
        self.change_manifest(self.validation, code={'hm_feature_engine.py':
            legacy.sha256_file(runner.SOURCE_ROOT/'scripts/hm_feature_engine.py')})
        self.fake_fit(50)
        result = audit.audit(self.validation, [self.output], self.root/'artifacts'/'audit', wall_seconds=30)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['fits'][0]['metrics']['map_at_12_conditional'], .25)
        self.assertTrue(all(pin['current_source_matches']
                            for pin in result['fits'][0]['code'].values()))

    def test_rehashed_but_wrong_labels_fail_before_pool(self):
        con = duckdb.connect(':memory:')
        altered = self.train/'altered.parquet'
        try:
            con.execute("""CREATE TEMP TABLE altered AS SELECT * REPLACE(
                (customer_id='positive' AND article_id='000') AS label)
                FROM read_parquet(?)""", [str(self.train/'frame.parquet')])
            con.sql('SELECT * FROM altered').write_parquet(str(altered))
        finally:
            con.close()
        altered.replace(self.train/'frame.parquet')
        manifest = runner.read_json(self.train/'manifest.json')
        manifest['files']['frame.parquet'] = legacy.sha256_file(self.train/'frame.parquet')
        write(self.train/'manifest.json', manifest)
        with patch.object(runner, 'model_pool', side_effect=AssertionError('Pool reached')):
            with self.assertRaisesRegex(ValueError, 'labels are inconsistent'):
                self.fake_fit()
        report = runner.read_json(self.output/'report.json')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['fit_count'], 0)

    def test_final_dates_and_any_lock_marker_rejected_before_output_sql_or_pool(self):
        for folder in (self.train, self.validation):
            original = runner.read_json(folder/'manifest.json')
            for values in (dict(anchor='2020-09-16'), dict(anchor='2020-09-23'),
                           dict(final_lock_sha256='b'*64), dict(final_lock_sha256=None)):
                with self.subTest(folder=folder.name, values=values):
                    self.change_manifest(folder, **values)
                    with (patch.object(runner, 'new_output', side_effect=AssertionError('mkdir reached')),
                          patch.object(duckdb, 'connect', side_effect=AssertionError('SQL reached')),
                          patch.object(runner, 'model_pool', side_effect=AssertionError('Pool reached'))):
                        with self.assertRaisesRegex(ValueError, 'final'):
                            runner.fit([self.train], self.validation, self.output, ['x'], 10)
                    self.assertFalse(self.output.exists())
                    write(folder/'manifest.json', original)

    def test_overlap_duplicate_anchor_and_source_mismatch_fail_before_mkdir_sql(self):
        for change, message in ((dict(anchor='2020-08-30'), 'target periods'),
                                (dict(anchor='2020-09-02'), 'target periods'),
                                (dict(database=dict(sha256='b'*64, bytes=1)), 'share policy')):
            original = runner.read_json(self.train/'manifest.json')
            self.change_manifest(self.train, **change)
            with (patch.object(runner, 'new_output', side_effect=AssertionError('mkdir reached')),
                  patch.object(duckdb, 'connect', side_effect=AssertionError('SQL reached'))):
                with self.assertRaisesRegex(ValueError, message):
                    runner.fit([self.train], self.validation, self.output, ['x'], 10)
            write(self.train/'manifest.json', original)
        with self.assertRaisesRegex(ValueError, 'Distinct'):
            runner.fit([self.train, self.train/'.'], self.validation, self.output, ['x'], 10)
        self.assertFalse(self.output.exists())

    def test_cache_byte_corruption_fails_before_output_and_pool(self):
        with (self.train/'frame.parquet').open('ab') as stream:
            stream.write(b'tampered')
        with patch.object(runner, 'new_output', side_effect=AssertionError('mkdir reached')):
            with self.assertRaisesRegex(ValueError, 'byte identity'):
                runner.fit([self.train], self.validation, self.output, ['x'], 10)

    def test_native_failure_and_incomplete_or_wrong_recipe_never_report_success(self):
        for number, arguments in enumerate((dict(failure='synthetic native buffer failure'),
                dict(actual_trees=499), dict(resolved=dict(task_type='CPU')),
                dict(resolved=dict(l2_leaf_reg=10)), dict(resolved=dict(random_seed=2027)))):
            output = self.root/'artifacts'/f'failed-{number}'
            with self.subTest(arguments=arguments), self.assertRaises(RuntimeError):
                self.fake_fit(50, output, **arguments)
            report = runner.read_json(output/'report.json')
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['fit_count'], 1)
            self.assertNotIn('validation_metrics', report)
            self.assertEqual(report['error']['type'], 'RuntimeError')
            self.assertIn(report['error']['message'], report['error']['traceback'])
            self.assertFalse((output/'model.cbm').exists())
        self.assertIn('synthetic native buffer failure',
                      runner.read_json(self.root/'artifacts/failed-0/report.json')['error']['message'])

    def test_exclusive_output_and_seed_2027_keep_sampler_2026(self):
        report = self.fake_fit(seed=2027)
        self.assertEqual(report['hyperparameters']['random_seed'], 2027)
        self.assertEqual(report['sampling_seed'], 2026)
        with self.assertRaises(FileExistsError):
            self.fake_fit()


class ParameterTests(unittest.TestCase):
    def test_closed_recipe_and_deadline_contract_fail_without_inputs_or_output(self):
        for kwargs in (dict(l2_leaf_reg=0), dict(l2_leaf_reg=True), dict(l2_leaf_reg=10.0),
                dict(iterations=150), dict(depth=6), dict(seed=2025), dict(task_type='CPU'),
                dict(train_users=5000), dict(negative_sample=0), dict(wall_seconds=0),
                dict(wall_seconds=float('nan')), dict(wall_seconds=float('inf')),
                dict(external_job_timeout_seconds=None), dict(external_job_timeout_seconds=1800),
                dict(external_job_timeout_seconds=True)):
            arguments = dict(l2_leaf_reg=10)
            arguments.update(kwargs)
            with self.subTest(kwargs=kwargs), patch.object(runner, 'development_manifest', side_effect=AssertionError('input read')):
                with self.assertRaises(ValueError):
                    runner.fit(['missing'], 'missing-validation', 'missing-output', ['x'], **arguments)

    def test_cli_requires_names_and_l2_and_passes_all_explicit_recipe_arguments(self):
        with tempfile.TemporaryDirectory(prefix='hm-v2-cli-', dir='D:/') as temp:
            names = Path(temp)/'names.json'
            write(names, ['x'])
            arguments = ['fit', '--train', 'train', '--validation', 'validation', '--output', 'out',
                         '--feature-names-file', str(names), '--l2-leaf-reg', '50', '--seed', '2027']
            with patch.object(runner, 'fit', return_value=dict(status='completed')) as called, redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(arguments), 0)
            self.assertEqual(called.call_args.args[3:], (['x'], 50, 500, 8, 2027, 20000, 20, 1800, 'GPU', 1860))
            for missing in ('--feature-names-file', '--l2-leaf-reg'):
                reduced = arguments.copy(); index = reduced.index(missing); del reduced[index:index+2]
                with (self.subTest(missing=missing), redirect_stdout(io.StringIO()),
                      redirect_stderr(io.StringIO()), self.assertRaises(SystemExit)):
                    runner.main(reduced)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory(prefix='hm-v2-json-', dir='D:/') as temp:
            path = Path(temp)/'input.json'
            for value in ('{"anchor":"2020-09-02","anchor":"2020-09-16"}', '{"x":NaN}'):
                path.write_text(value, encoding='utf-8')
                with self.assertRaises(ValueError):
                    runner.read_json(path)


if __name__ == '__main__':
    unittest.main()
