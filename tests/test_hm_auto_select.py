"""Metadata-only synthetic selection witnesses, on D:; no ML/data imports."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import hm_auto_select as selector


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    return selector.digest(path.read_bytes())


class ChoiceTests(unittest.TestCase):
    def test_strict_zero_negative_and_marginal_baseline(self):
        points = [dict(name='zero', width=1, weekly_maps=[.25, .625]),
                  dict(name='negative', width=3, weekly_maps=[.375, .375])]
        result = selector.choose(points, [.25, .5])
        self.assertIsNone(result['chosen'])
        self.assertTrue(all(not item['eligible'] and item['rejections'] for item in result['candidates']))
        groups = [dict(name='group11', width=11, weekly_maps=[.375, .625]),
                  dict(name='group12', width=12, weekly_maps=[.5, .75])]
        self.assertEqual(selector.choose(groups, [.25, .5])['chosen'], 'group12')
        # Marginal improvement is against the current bundle, not original M.
        self.assertIsNone(selector.choose(groups, [.5, .75])['chosen'])
        self.assertIsNone(selector.choose([], [.25, .5])['chosen'])

    def test_maxmin_then_mean_then_width_then_name_are_deterministic(self):
        items = [dict(name='large_mean_small_min', width=1, weekly_maps=[.0625, .875]),
                 dict(name='minimum', width=6, weekly_maps=[.125, .25]),
                 dict(name='mean', width=6, weekly_maps=[.125, .375]),
                 dict(name='width', width=3, weekly_maps=[.125, .375]),
                 dict(name='alpha', width=3, weekly_maps=[.125, .375])]
        for length, expected in ((2, 'minimum'), (3, 'mean'), (4, 'width'), (5, 'alpha')):
            self.assertEqual(selector.choose(items[:length], [0, 0])['chosen'], expected)
        self.assertEqual(selector.choose(items, [0, 0]), selector.choose(list(reversed(items)), [0, 0]))

    def test_nonfinite_bool_invalid_width_and_duplicate_names_are_rejected(self):
        base = dict(name='prefix', width=1, weekly_maps=[.5, .5])
        for value in (float('nan'), float('inf'), True, -.01, 1.01):
            with self.subTest(value=value), self.assertRaises(ValueError):
                selector.choose([dict(base, weekly_maps=[value, .5])], [.25, .25])
        for width in (0, -1, True, 1.0):
            with self.subTest(width=width), self.assertRaises(ValueError):
                selector.choose([dict(base, width=width)], [.25, .25])
        with self.assertRaises(ValueError):
            selector.choose([base, base], [.25, .25])


class MetricsCompatibilityTests(unittest.TestCase):
    def test_same_keys_exact_typed_counts_and_finite_fractional_tolerance(self):
        metrics = dict(queries=20000, positive_queries=1000, empty_target_queries=19000,
                       distinct_query_target_pairs=3000, map_at_12_conditional=.28)
        self.assertTrue(selector.metrics_equal(dict(metrics,
            map_at_12_conditional=math.nextafter(.28, 1)), metrics))
        self.assertFalse(selector.metrics_equal(dict(metrics, map_at_12_conditional=.28+2e-12), metrics))
        self.assertFalse(selector.metrics_equal(dict(metrics, extra=0), metrics))
        for key in ('queries', 'positive_queries', 'empty_target_queries', 'distinct_query_target_pairs'):
            for value in (float(metrics[key]), True, metrics[key]+1):
                with self.subTest(key=key, value=value):
                    self.assertFalse(selector.metrics_equal(dict(metrics, **{key: value}), metrics))
                    self.assertFalse(selector.metrics_equal(metrics, dict(metrics, **{key: value})))
        for value in (float('nan'), float('inf'), True, None):
            with self.subTest(value=value):
                self.assertFalse(selector.metrics_equal(dict(metrics, map_at_12_conditional=value), metrics))
                self.assertFalse(selector.metrics_equal(metrics, dict(metrics, map_at_12_conditional=value)))


class PrefixMetadataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='hm-prefix-metadata-', dir='D:/' if Path('D:/').is_dir() else None)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        root_patch = patch.object(selector, 'ROOT', self.root)
        root_patch.start(); self.addCleanup(root_patch.stop)
        self.manual = dict(numeric=[f'x{i}' for i in range(18)], categorical=[f'c{i}' for i in range(5)])
        self.ranking = [f'g{i}' for i in range(12)]
        self.feature_digest = sha('features')
        self.runtime = dict(python='fixture', packages={'catboost': 'fixture'}, threads=4)
        self.database = dict(sha256=sha('database'), bytes=1)
        self.parameters = dict(iterations=500, depth=8, learning_rate=.05, l2_leaf_reg=10,
            loss_function='Logloss', thread_count=4, task_type='GPU', verbose=False,
            allow_writing_files=False, devices='0', gpu_ram_part=.5, pinned_memory_size='256mb',
            bootstrap_type='Bayesian', bagging_temperature=1, border_count=128, boosting_type='Plain')
        self.inputs = {anchor: dict(anchor=anchor, manifest_sha256=sha(anchor+'manifest'),
            qcy_identity=sha(anchor+'QY'), candidate_identity=sha(anchor+'C'))
            for anchor in ['2020-08-12', '2020-08-19', '2020-08-26', *selector.ANCHORS]}
        self.sources = {}
        for name in ('hm_experiment.py', 'hm_baseline.py', 'hm_job.py', 'hm_feature_engine.py', 'hm_result_audit.py'):
            path = self.root/'scripts'/name
            path.parent.mkdir(exist_ok=True)
            path.write_text('# synthetic source '+name+'\n', encoding='utf-8', newline='\n')
            self.sources[name] = selector.digest(path.read_bytes())
        self.report_code = {name: self.sources[name] for name in ('hm_experiment.py', 'hm_baseline.py')}
        self.references = ['artifacts/hm-campaign/gpu-manual-grid/manual_pilot500d8',
                           'artifacts/hm-campaign/confirmation/M']
        self.audits, self.paths, self.reports = [], [], []
        weekly_maps = [[.25, .20, .28, .30, .26], [.50, .45, .52, .51, .49]]
        trains = [['2020-08-12', '2020-08-19', '2020-08-26'],
                  ['2020-08-12', '2020-08-19', '2020-08-26', '2020-09-02']]
        for fold, anchor in enumerate(selector.ANCHORS):
            collection = dict(self.inputs[anchor], policy='C0-Q120', database_identity=self.database)
            audit = dict(format='hm-independent-result-audit-v1', status='PASS',
                checker_sha256=self.sources['hm_result_audit.py'], collection=collection,
                source_rebuild='PASS: raw history-only SHA256 Q and full distinct weekly Y', fits=[])
            directories = [self.references[fold], selector.OLD_PVC[fold]]+[
                f'artifacts/hm-auto-v2/prefix{k}/{anchor}' for k in selector.WIDTHS]
            self.reports.append([])
            for arm, (directory, width) in enumerate(zip(directories, [0, 12, 1, 3, 6])):
                metrics = dict(queries=20000, positive_queries=1000, empty_target_queries=19000,
                    distinct_query_target_pairs=3000, candidate_query_coverage_conditional=.25,
                    candidate_target_coverage_micro=.1, oracle_map_at_12_conditional=.75,
                    map_at_12_conditional=weekly_maps[fold][arm])
                features = dict(numeric=self.manual['numeric']+self.ranking[:width],
                                categorical=self.manual['categorical'], contract_digest=self.feature_digest)
                report = dict(format='hm-experiment-fit-v1', status='completed', fit_count=1, actual_trees=500,
                    training_user_limit=20000, negative_sample=20, sampling_seed=2026,
                    features=features, inputs=[self.inputs[a] for a in trains[fold]+[anchor]],
                    runtime=self.runtime, code=self.report_code,
                    hyperparameters=dict(self.parameters, random_seed=2026), validation_metrics=metrics)
                report['fit_identity'] = selector.fit_identity(report)
                path = self.root/directory/'report.json'
                report_sha = write(path, report)
                self.reports[fold].append(path)
                audit['fits'].append(dict(arm=arm, fit_directory=(self.root/directory).as_posix(),
                    report_sha256=report_sha, fit_identity=report['fit_identity'], metrics=metrics,
                    code={name: dict(recorded_sha256=value, current_source_matches=True)
                          for name, value in self.report_code.items()}))
            self.audits.append(audit)
            path = self.root/f'artifacts/hm-auto-v2/audits/prefix-{anchor}/report.json'
            self.paths.append(path)
            write(path, audit)
        old_confirmation = dict(status='PASS', checker_sha256=self.sources['hm_result_audit.py'],
                                fits=self.audits[1]['fits'][:2])
        historical_sha = write(self.root/'artifacts/hm-campaign/audits/confirmation/report.json', old_confirmation)
        lock = dict(features=dict(M=self.manual, selected=dict(numeric=self.manual['numeric']+self.ranking,
            categorical=self.manual['categorical'])), feature_digest=self.feature_digest,
            hyperparameters=self.parameters, implementation=dict(runtime=self.runtime), database=self.database,
            provenance=dict(manual=dict(sha256=self.audits[0]['fits'][0]['report_sha256']),
                            confirmation=dict(sha256=historical_sha)),
            train_collections=[dict(path=f'artifacts/hm-campaign/collections/{a}-c0q120/manifest.json',
                                   sha256=value['manifest_sha256']) for a, value in self.inputs.items()])
        lock_sha = write(self.root/'configs/datasets/hm-final-lock.json', lock)
        campaign_sha = write(self.root/'configs/datasets/hm-campaign.json', dict(frozen=True))
        selection = dict(status='selected', selected_programs=self.ranking,
            manual_names=self.manual['numeric']+self.manual['categorical'], feature_contract_digest=self.feature_digest)
        selection_sha = write(self.root/'artifacts/hm-campaign/feature-selection/manifest.json', selection)
        files = {}
        for width in selector.WIDTHS:
            path = f'artifacts/hm-auto-v2/prefix{width}_names.json'
            files[str(width)] = dict(path=path, width=width,
                sha256=write(self.root/path, selection['manual_names']+self.ranking[:width]))
        protocol = dict(version=2, v1_frozen=dict(source=self.sources, lock_sha256=lock_sha,
            campaign_sha256=campaign_sha), development=dict(anchors=selector.ANCHORS, train_anchors=trains,
            references=self.references, recipe=dict(iterations=500, depth=8, l2_leaf_reg=10, seed=2026,
            task_type='GPU', training_users=20000, negative_sample=20, sampling_seed=2026)),
            prefix_diagnostic=dict(widths=selector.WIDTHS, files=files, source_selection_sha256=selection_sha,
                                   ranking=self.ranking))
        protocol_sha = write(self.root/selector.PROTOCOL, protocol)
        pin_patch = patch.object(selector, 'PROTOCOL_SHA', protocol_sha)
        pin_patch.start(); self.addCleanup(pin_patch.stop)
        self.output = self.root/'artifacts/hm-auto-v2/decisions/prefix'

    def change_audit(self, fold, change):
        change(self.audits[fold])
        write(self.paths[fold], self.audits[fold])

    def change_report(self, fold, arm, change, resign=True):
        path = self.reports[fold][arm]
        report = json.loads(path.read_text(encoding='utf-8'))
        change(report)
        if resign:
            report['fit_identity'] = selector.fit_identity(report)
        report_sha = write(path, report)
        self.audits[fold]['fits'][arm].update(report_sha256=report_sha, fit_identity=report['fit_identity'],
                                             metrics=deepcopy(report['validation_metrics']))
        write(self.paths[fold], self.audits[fold])

    def decide(self):
        return selector.prefix_decision(self.paths, self.output)

    def test_exact_metadata_flow_winner_provenance_and_exclusive_output(self):
        report = self.decide()
        self.assertEqual(report['chosen'], 'prefix1')
        self.assertEqual(report['next_action'], 'symmetric_regularization')
        self.assertEqual(len(report['candidates']), 3)
        self.assertEqual(len(report['fits']), 10)
        self.assertIn('width diagnostic', report['interpretation'])
        self.assertIn(selector.PROTOCOL, report['provenance'])
        for name, value in report['provenance'].items():
            self.assertEqual(value, selector.digest((self.root/name).read_bytes()))
        rejected = next(item for item in report['candidates'] if item['name'] == 'prefix6')
        self.assertEqual(rejected['rejections'][0]['week_index'], 1)
        self.assertEqual(json.loads((self.output/'report.json').read_text(encoding='utf-8')), report)
        with self.assertRaises(FileExistsError):
            self.decide()
        self.assertFalse(list(self.root.rglob('*.parquet')))
        self.assertFalse(list(self.root.rglob('*.cbm')))

    def test_invalid_status_checker_arm_order_and_audit_path_are_rejected(self):
        original = deepcopy(self.audits[0])
        for change in (lambda a: a.update(status='FAIL'), lambda a: a.update(checker_sha256='0'*64),
                       lambda a: a['fits'].reverse(), lambda a: a['fits'].pop()):
            self.audits[0] = deepcopy(original)
            self.change_audit(0, change)
            with self.assertRaises(ValueError):
                self.decide()
            self.assertFalse(self.output.exists())
        self.audits[0] = original; write(self.paths[0], original)
        with self.assertRaises(ValueError):
            selector.prefix_decision(list(reversed(self.paths)), self.output)

    def test_no_strictly_positive_prefix_returns_explicit_group_fallback(self):
        for fold, point in enumerate((.25, .50)):
            for arm in (2, 3, 4):
                self.change_report(fold, arm, lambda r: r['validation_metrics'].update(map_at_12_conditional=point))
        report = self.decide()
        self.assertIsNone(report['chosen'])
        self.assertEqual(report['next_action'], 'group_fallback')
        self.assertTrue(all(not p['eligible'] and len(p['rejections']) == 2 for p in report['candidates']))

    def test_wrong_report_sha_and_fit_identity_fail(self):
        self.change_audit(0, lambda a: a['fits'][2].update(report_sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.decide()
        self.change_report(0, 2, lambda r: r.update(fit_identity='0'*64), resign=False)
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.decide()
        self.assertFalse(self.output.exists())

    def test_one_ulp_audited_map_is_accepted_and_used_for_actual_choice_points(self):
        audited = math.nextafter(.28, 1)
        self.change_audit(0, lambda a: a['fits'][2]['metrics'].update(map_at_12_conditional=audited))
        report = self.decide()
        prefix = next(p for p in report['candidates'] if p['name'] == 'prefix1')
        self.assertEqual(prefix['weekly_maps'][0], audited)
        self.assertEqual(prefix['weekly_deltas'][0], audited-.25)
        self.assertEqual(json.loads(self.reports[0][2].read_text(encoding='utf-8'))['validation_metrics']
                         ['map_at_12_conditional'], .28)

    def test_audited_map_difference_above_tolerance_rejected_before_output(self):
        self.change_audit(0, lambda a: a['fits'][2]['metrics'].update(map_at_12_conditional=.28+2e-12))
        with self.assertRaisesRegex(ValueError, 'Audit/producer metrics differ'):
            self.decide()
        self.assertFalse(self.output.exists())

    def test_mismatched_features_recipe_runtime_and_fold_rejected_even_after_resigning(self):
        original = self.reports[0][2].read_bytes()
        for change in (lambda r: r['features']['numeric'].reverse(),
                       lambda r: r['hyperparameters'].update(l2_leaf_reg=50),
                       lambda r: r['runtime'].update(threads=2),
                       lambda r: r['inputs'][0].update(anchor='2020-08-13')):
            self.reports[0][2].write_bytes(original)
            self.change_report(0, 2, change)
            with self.assertRaises(ValueError):
                self.decide()
            self.assertFalse(self.output.exists())

    def test_nonfinite_overflow_duplicate_json_and_frozen_protocol_tampering_rejected(self):
        original = self.paths[0].read_text(encoding='utf-8')
        for token in ('NaN', '1e999', 'Infinity'):
            self.paths[0].write_text(original.replace('"map_at_12_conditional": 0.28',
                '"map_at_12_conditional": '+token), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                self.decide()
        self.paths[0].write_text('{"status":"PASS","status":"FAIL"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.decide()
        self.paths[0].write_text(original, encoding='utf-8')
        with (self.root/selector.PROTOCOL).open('a', encoding='utf-8') as stream:
            stream.write(' ')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.decide()
        self.assertFalse(self.output.exists())

    def test_within_week_qcy_and_population_mismatch_rejected(self):
        original = self.reports[0][2].read_bytes()
        self.change_report(0, 2, lambda r: r['inputs'][-1].update(candidate_identity=sha('wrongC')))
        with self.assertRaisesRegex(ValueError, 'fold/input identity'):
            self.decide()
        self.reports[0][2].write_bytes(original)
        self.change_report(0, 2, lambda r: r['validation_metrics'].update(positive_queries=1001,
                                                                        empty_target_queries=18999))
        with self.assertRaisesRegex(ValueError, 'Q/C/Y metadata'):
            self.decide()
        self.assertFalse(self.output.exists())

    def test_names_hash_and_frozen_source_changes_are_rejected(self):
        names = self.root/'artifacts/hm-auto-v2/prefix1_names.json'
        original = names.read_bytes()
        names.write_text('["wrong"]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.decide()
        names.write_bytes(original)
        with (self.root/'scripts/hm_result_audit.py').open('a', encoding='utf-8') as stream:
            stream.write('# changed\n')
        with self.assertRaisesRegex(ValueError, 'source SHA256 mismatch'):
            self.decide()
        self.assertFalse(self.output.exists())

    def test_freshness_detects_audit_changed_after_choice_before_mkdir(self):
        original = selector.choose
        def mutate(*args):
            result = original(*args)
            with self.paths[1].open('a', encoding='utf-8') as stream:
                stream.write(' ')
            return result
        with patch.object(selector, 'choose', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during decision'):
                self.decide()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
