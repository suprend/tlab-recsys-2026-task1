"""Mutation checks for the portable saved-evidence verifier; no raw data or ML imports."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('report_check', ROOT / 'scripts/check_report.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
SENS = 'docs/writeup/sensitivity-2026-10-25/'
SEC = 'docs/writeup/secondary-2026-10-25/'


def required_files():
    paths = {'docs/writeup/latex-report/main.tex', 'docs/writeup/latex-report/table-values.json',
             'docs/writeup/latex-report/generate_figure.py', 'docs/otto-run/otto2-kaggle-scores.csv',
             'docs/otto3-run/otto3-kaggle-scores.csv', 'scripts/rees_sensitivity.py', 'scripts/rees_secondary.py'}
    for folder in (SENS, SEC):
        paths.update((folder+'plan.json', folder+'results.json'))
        plan = R.load(ROOT / folder / 'plan.json')
        paths.update(p for p in plan['input_sha256'] if not p.startswith('artifacts/'))
        paths.update(plan.get('dependency_sha256', {}))
    ablation = ROOT / R.AGENT_TEST_DIR
    if (ablation / 'plan.json').exists():
        paths.add(R.AGENT_TEST_DIR + '/plan.json')
        plan = R.load(ablation / 'plan.json')
        paths.update(p for p in plan['input_sha256'] if not p.startswith('artifacts/'))
        paths.update(plan['dependency_sha256'])
        if (ablation / 'results.json').exists():
            paths.add(R.AGENT_TEST_DIR + '/results.json')
    return paths


class PortableReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in required_files():
            dest = self.root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, dest)

    def edit(self, relative, change):
        path = self.root / relative
        value = R.load(path)
        change(value)
        path.write_text(json.dumps(value), encoding='utf-8')

    def relink_sensitivity(self):
        # Preserve provenance consistency in semantic-mutation tests, so the intended
        # semantic check, rather than the upstream file hash, is exercised.
        sha = R.digest(self.root / SENS / 'results.json')
        key = SENS + 'results.json'
        self.edit(SEC+'plan.json', lambda x: x['input_sha256'].__setitem__(key, sha))
        plan_sha = R.digest(self.root / SEC / 'plan.json')
        def update(x):
            x['inputs_sha256'][key] = sha
            x['plan_sha256'] = plan_sha
        self.edit(SEC+'results.json', update)

    def test_portable_package_without_raw_data(self):
        self.assertFalse((self.root/'artifacts').exists())
        self.assertFalse((self.root/'data').exists())
        omitted = R.check(self.root)
        expected = set()
        for folder in (SENS, SEC):
            expected.update(p for p in R.load(self.root / folder / 'plan.json')['input_sha256'] if p.startswith('artifacts/'))
        if (self.root / R.AGENT_TEST_DIR / 'results.json').exists():
            result = R.load(self.root / R.AGENT_TEST_DIR / 'results.json')
            expected.update(p for p in result['input_sha256'] if p.startswith('artifacts/'))
            expected.update(result['output_sha256'])
        self.assertEqual(omitted, expected)

    def test_duplicate_model_seed_is_rejected(self):
        self.edit(SEC+'results.json', lambda x: x['seeds'][1].__setitem__('seed_index', 0))
        with self.assertRaisesRegex(ValueError, 'unique seeds'):
            R.check(self.root)

    def test_missing_secondary_interval_is_rejected(self):
        self.edit(SEC+'results.json', lambda x: x['seeds'][0]['metrics']['recall']['user_cluster_bootstrap'].pop('ci95'))
        with self.assertRaises(KeyError):
            R.check(self.root)

    def test_nonpositive_interval_contradiction_is_rejected(self):
        self.edit(SEC+'results.json', lambda x: x['seeds'][0]['metrics']['purchase_ndcg']['user_cluster_bootstrap'].__setitem__('ci95', [-.01, .01]))
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            R.check(self.root)

    def test_plan_tampering_is_rejected(self):
        self.edit(SEC+'plan.json', lambda x: x['bootstrap'].__setitem__('draws', 100))
        with self.assertRaisesRegex(ValueError, 'Plan hash mismatch'):
            R.check(self.root)

    def test_dependency_tampering_is_rejected(self):
        with (self.root/'task1/model.py').open('a') as handle:
            handle.write('\n# mutation\n')
        with self.assertRaisesRegex(ValueError, 'Hash mismatch: task1/model.py'):
            R.check(self.root)

    def test_missing_secondary_code_hash_is_rejected(self):
        self.edit(SEC+'results.json', lambda x: x['code_sha256'].pop('scripts/rees_secondary.py'))
        with self.assertRaisesRegex(ValueError, 'both analysis scripts'):
            R.check(self.root)

    def test_analysis_code_tampering_is_rejected(self):
        with (self.root/'scripts/rees_secondary.py').open('a') as handle:
            handle.write('\n# mutation\n')
        with self.assertRaisesRegex(ValueError, 'Hash mismatch: scripts/rees_secondary.py'):
            R.check(self.root)

    def test_daily_count_mismatch_is_rejected(self):
        self.edit(SENS+'results.json', lambda x: x['test_2020'][0]['daily_and_leave_one_day_out'][0].__setitem__('queries', 1))
        self.relink_sensitivity()
        with self.assertRaisesRegex(ValueError, 'Daily counts'):
            R.check(self.root)

    def test_wrong_lodo_is_rejected(self):
        self.edit(SENS+'results.json', lambda x: x['test_2020'][0]['daily_and_leave_one_day_out'][0].__setitem__('leave_this_day_out_delta', .01))
        self.relink_sensitivity()
        with self.assertRaisesRegex(ValueError, 'LODO'):
            R.check(self.root)

    def test_dfs_interval_claim_is_checked(self):
        self.edit(SENS+'results.json', lambda x: x['dfs_validation']['2019']['seeds'][0]['user_cluster_bootstrap'].__setitem__('ci95', [.001, .01]))
        self.relink_sensitivity()
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            R.check(self.root)

    def test_inconsistent_purchase_population_is_rejected(self):
        def change(x):
            m=x['seeds'][1]['metrics']['purchase_recall'];m['queries']+=1
            m['share_of_main_queries']=m['queries']/97656
            m['excluded_no_purchase_queries']=97656-m['queries']
        self.edit(SEC+'results.json', change)
        with self.assertRaisesRegex(ValueError, 'Purchase populations'):
            R.check(self.root)

    def test_fractional_user_count_is_rejected(self):
        def change(x):
            m=x['seeds'][0]['metrics']['purchase_ndcg'];m['users']=43428.5
            m['user_cluster_bootstrap']['clusters']=43428.5
        self.edit(SEC+'results.json', change)
        with self.assertRaisesRegex(ValueError, 'user/query population'):
            R.check(self.root)

    def test_missing_packaged_input_is_not_silently_skipped(self):
        (self.root/'task1/runs/grid-2026-10-20/grid.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing packaged evidence'):
            R.check(self.root)

    def test_nonfinite_json_is_rejected(self):
        self.edit(SEC+'results.json', lambda x: x['seeds'][0]['metrics']['recall'].__setitem__('mean_delta', float('nan')))
        with self.assertRaisesRegex(ValueError, 'Invalid JSON number'):
            R.check(self.root)


class AgentTestAblationTests(unittest.TestCase):
    setUp = PortableReportTests.setUp
    edit = PortableReportTests.edit

    def fixture(self):
        directory = self.root / R.AGENT_TEST_DIR
        plan = R.load(directory / 'plan.json')
        values = R.load(self.root / 'docs/writeup/latex-report/table-values.json')['arms']
        result = {'format': 'rees-agent-test-ablation-result-v1', 'status': plan['status'],
                  'plan_sha256': R.digest(directory / 'plan.json'),
                  'plan_path': R.AGENT_TEST_DIR + '/plan.json',
                  'input_sha256': plan['input_sha256'], 'dependency_sha256': plan['dependency_sha256'],
                  'interpretation_limits': plan['interpretation_limits'],
                  'libraries': plan['historical_evidence']['libraries'],
                  'training': {'arm': 'Hag', 'features': 146,
                               'fits': plan['historical_evidence']['expected_fits'], 'seconds': 1500},
                  'seconds': 1520.5,
                  'output_sha256': {plan['output_dir'] + f'/test_Hag_s{i}.parquet': 'a' * 64 for i in range(2)},
                  'seeds': []}
        for i, pair in enumerate(plan['seeds']):
            base, hp = values['base']['seeds'][i]['mean'], values['Hp']['seeds'][i]['mean']
            hag = base - .001 if i == 0 else hp + .001
            row = {'seed_index': i, 'model_seed': pair[0], 'negative_sampling_seed': pair[1],
                   'queries': 97656, 'users': 79302, 'days': 14,
                   'means': {name: {'ndcg': value, 'recall': .2, 'purchase_ndcg': .1, 'purchase_recall': .2}
                             for name, value in [('base', base), ('Hag', hag), ('Hp', hp)]}, 'contrasts': {}}
            for name, a, b in [('Hag-base', base, hag), ('Hp-Hag', hag, hp)]:
                delta = b - a
                row['contrasts'][name] = {'reference_mean': a, 'new_mean': b, 'mean_delta': delta,
                                          'user_cluster_bootstrap': {'clusters': 79302, 'draws': 2000,
                                                                     'rng_seed': 20261025, 'mean_delta': delta,
                                                                     'ci95': [delta - .0002, delta + .0002]}}
            result['seeds'].append(row)
        (directory / 'results.json').write_text(json.dumps(result), encoding='utf-8')
        base = sum(row['means']['base']['ndcg'] for row in result['seeds']) / 2
        hag = sum(row['means']['Hag']['ndcg'] for row in result['seeds']) / 2
        gain = 100 * (hag / base - 1)
        self.display_values = [f'{hag:.4f}', f'{base:.4f}', f'{gain:.1f}\\%']
        self.display_text = ('% ' + R.AGENT_TEST_MARKER + '\n\n' +
                             f'Average \\textbf{{{hag:.4f}}} versus {base:.4f}; gain \\textbf{{{gain:.1f}\\%}}.')
        return plan, values

    def verify(self):
        values = R.load(self.root / 'docs/writeup/latex-report/table-values.json')['arms']
        omitted = set()
        R.check_agent_test_ablation(self.root, values, omitted, getattr(self, 'display_text', R.AGENT_TEST_MARKER))
        self.assertFalse((self.root / 'artifacts').exists())
        return omitted

    def alter_result(self, change):
        self.edit(R.AGENT_TEST_DIR + '/results.json', change)

    def test_portable_result_accepts_both_positive_and_negative_effects(self):
        plan, _ = self.fixture()
        omitted = self.verify()
        self.assertEqual(omitted, {p for p in plan['input_sha256'] if p.startswith('artifacts/')} |
                         {plan['output_dir'] + f'/test_Hag_s{i}.parquet' for i in range(2)})

    def test_report_marker_requires_published_result(self):
        path = self.root / R.AGENT_TEST_DIR / 'results.json'
        if path.exists(): path.unlink()
        with self.assertRaisesRegex(ValueError, 'missing agent test'):
            self.verify()
        values = R.load(self.root / 'docs/writeup/latex-report/table-values.json')['arms']
        R.check_agent_test_ablation(self.root, values, set(), '')

    def test_wrong_displayed_means_and_gain_rejected(self):
        self.fixture()
        original = self.display_text
        for i, (expected, wrong) in enumerate(zip(self.display_values, ['0.9999', '0.8888', '99.9\\%'])):
            with self.subTest(value=i):
                self.display_text = original.replace(expected, wrong, 1)
                with self.assertRaisesRegex(ValueError, 'displayed'):
                    self.verify()
        self.display_text = original
        self.verify()

    def test_missing_seed_rejected(self):
        self.fixture()
        self.alter_result(lambda x: x['seeds'].pop())
        with self.assertRaisesRegex(ValueError, 'Both model seeds'): self.verify()

    def test_plan_hash_rejected(self):
        self.fixture()
        self.alter_result(lambda x: x.__setitem__('plan_sha256', '0' * 64))
        with self.assertRaisesRegex(ValueError, 'plan hash'): self.verify()

    def test_population_mismatch_rejected(self):
        self.fixture()
        self.alter_result(lambda x: x['seeds'][0].__setitem__('users', 79301))
        with self.assertRaisesRegex(ValueError, 'population'): self.verify()

    def test_reversed_contrast_rejected(self):
        self.fixture()
        def change(x):
            c = x['seeds'][0]['contrasts']['Hag-base']
            c['mean_delta'] *= -1
            c['user_cluster_bootstrap']['mean_delta'] = c['mean_delta']
        self.alter_result(change)
        with self.assertRaisesRegex(ValueError, 'contrast direction'): self.verify()

    def test_reference_mean_change_rejected(self):
        self.fixture()
        self.alter_result(lambda x: x['seeds'][0]['means']['base'].__setitem__('ndcg', .5))
        with self.assertRaisesRegex(ValueError, 'reference mean'): self.verify()

    def test_missing_manifest_entry_rejected_even_with_relinked_plan(self):
        self.fixture()
        rel = R.AGENT_TEST_DIR
        plan = R.load(self.root / rel / 'plan.json')
        plan['dependency_sha256'].pop('scripts/rees_agent_test_ablation.py')
        (self.root / rel / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        def change(x):
            x['plan_sha256'] = R.digest(self.root / rel / 'plan.json')
            x['dependency_sha256'] = plan['dependency_sha256']
        self.alter_result(change)
        with self.assertRaisesRegex(ValueError, 'dependency manifest'): self.verify()

    def test_missing_artifact_manifest_entry_rejected_even_with_relinked_plan(self):
        self.fixture()
        rel = R.AGENT_TEST_DIR
        plan = R.load(self.root / rel / 'plan.json')
        key = next(k for k in plan['input_sha256'] if '/extra/' in k)
        plan['input_sha256'].pop(key)
        (self.root / rel / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        def change(x):
            x['plan_sha256'] = R.digest(self.root / rel / 'plan.json')
            x['input_sha256'] = plan['input_sha256']
        self.alter_result(change)
        with self.assertRaisesRegex(ValueError, 'input manifest'): self.verify()

    def test_runtime_dependency_tampering_rejected(self):
        self.fixture()
        with (self.root / 'scripts/rees_agent_test_ablation.py').open('a') as f:
            f.write('\n# mutation\n')
        with self.assertRaisesRegex(ValueError, 'Hash mismatch'): self.verify()

    def test_posthoc_status_required(self):
        self.fixture()
        self.alter_result(lambda x: x.__setitem__('status', 'confirmatory'))
        with self.assertRaisesRegex(ValueError, 'post-hoc status'): self.verify()

    def test_bootstrap_seed_mismatch_rejected(self):
        self.fixture()
        self.alter_result(lambda x: x['seeds'][1]['contrasts']['Hp-Hag']['user_cluster_bootstrap'].__setitem__('rng_seed', 7))
        with self.assertRaisesRegex(ValueError, 'resampling differs'): self.verify()


if __name__ == '__main__':
    unittest.main()
