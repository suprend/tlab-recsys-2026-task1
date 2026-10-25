import unittest
import json
import duckdb
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from scripts import rees_secondary as R


def frame():
    return pd.DataFrame({'qid': ['2020-02-14:1', '2020-02-15:1', '2020-02-15:2'],
                         'ndcg': [.2, .3, .4], 'recall': [.3, .4, .5],
                         'purchase_ndcg': [np.nan, .1, .2],
                         'purchase_recall': [np.nan, .2, .3]})


class SecondaryTests(unittest.TestCase):
    def test_reordering_preserves_pairing(self):
        a, b = R.pair(frame(), frame().iloc[::-1])
        self.assertEqual(list(a.qid), list(b.qid))
        np.testing.assert_equal(a.recall.to_numpy(), b.recall.to_numpy())

    def test_missing_query_rejected(self):
        with self.assertRaisesRegex(ValueError, 'keys differ'):
            R.pair(frame(), frame().iloc[:-1])

    def test_mask_disagreement_rejected_before_filter(self):
        b = frame(); b.loc[0, ['purchase_ndcg', 'purchase_recall']] = .3
        with self.assertRaisesRegex(ValueError, 'between arms'):
            R.pair(frame(), b)

    def test_purchase_metric_masks_must_match(self):
        a = frame(); a.loc[0, 'purchase_recall'] = 0
        with self.assertRaisesRegex(ValueError, 'different applicability'):
            R.validate(a)

    def test_nonfinite_or_out_of_range_rejected(self):
        for metric, value in [('recall', np.nan), ('recall', np.inf),
                              ('purchase_ndcg', -1), ('purchase_recall', 1.01)]:
            a = frame(); a.loc[1, metric] = value
            with self.subTest(metric=metric, value=value), self.assertRaises(ValueError):
                R.validate(a)

    def test_purchase_missing_is_not_zero(self):
        b = frame(); b.loc[1:, 'purchase_ndcg'] += .1
        a, b = R.pair(frame(), b)
        result = R.metric_summary(a, b, 'purchase_ndcg', 20, 42)
        self.assertEqual(result['queries'], 2)
        self.assertEqual(result['excluded_no_purchase_queries'], 1)
        self.assertAlmostEqual(result['reference_mean'], .15)
        self.assertAlmostEqual(result['mean_delta'], .1)

    def test_empty_purchase_population_rejected(self):
        a = frame(); a[['purchase_ndcg', 'purchase_recall']] = np.nan
        a, b = R.pair(a, a)
        with self.assertRaisesRegex(ValueError, 'No applicable'):
            R.metric_summary(a, b, 'purchase_ndcg', 20, 42)

    def test_seed_population_mask_rejected(self):
        a = R.validate(frame()); signature = R.check_seed_population(a, None)
        b = frame(); b.loc[0, ['purchase_ndcg', 'purchase_recall']] = .1
        with self.assertRaisesRegex(ValueError, 'between seeds'):
            R.check_seed_population(R.validate(b), signature)

    def test_distribution_contributions_use_all_queries(self):
        d = np.array([.2, -.1, 0, 0])
        result = R.distribution(d)
        groups = result['groups']
        self.assertEqual(groups['unchanged']['queries'], 2)
        self.assertEqual(groups['improved']['fraction'], .25)
        self.assertAlmostEqual(groups['improved']['contribution_to_overall_mean'], .05)
        self.assertAlmostEqual(groups['worsened']['contribution_to_overall_mean'], -.025)
        self.assertAlmostEqual(sum(g['contribution_to_overall_mean'] for g in groups.values()), d.mean())

    def test_exact_ties_not_thresholded(self):
        groups = R.distribution([0, 1e-15, -1e-15])['groups']
        self.assertEqual([g['queries'] for g in groups.values()], [1, 1, 1])

    def test_full_synthetic_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dates = pd.date_range('2020-02-14', '2020-02-29').strftime('%Y-%m-%d')
            data = pd.DataFrame({'qid': [f'{d}:{i}' for i, d in enumerate(dates)],
                                 'anchor': dates, 'ndcg': .2, 'recall': .3,
                                 'purchase_ndcg': [.1, np.nan] * 8,
                                 'purchase_recall': [.2, np.nan] * 8})
            hashes = {}
            for seed in (0, 1):
                for arm in ('base', 'Hp'):
                    values = data.copy()
                    if arm == 'Hp':
                        values[['ndcg', 'recall', 'purchase_ndcg', 'purchase_recall']] += .1
                    rel = f'artifacts/task1/v2020/replication/test_{arm}_s{seed}.parquet'
                    dest = root / rel; dest.parent.mkdir(parents=True, exist_ok=True)
                    with duckdb.connect() as conn:
                        conn.register('values_frame', values)
                        conn.execute('COPY values_frame TO ? (FORMAT PARQUET)', [str(dest)])
                    hashes[rel] = R.S.digest(dest)
            original = {'primary': {'metrics': {
                'base': {'recall': .3, 'purchase_ndcg': .1, 'purchase_recall': .2},
                'Hp': {'recall': .4, 'purchase_ndcg': .2, 'purchase_recall': .3}}}}
            prior = {'test_2020': [{'seed_index': i, 'queries': 14, 'users': 14,
                                   'reference_mean': .2, 'new_mean': .3, 'mean_delta': .1}
                                  for i in (0, 1)]}
            for rel, value in ((R.SUMMARY, original), (R.PREVIOUS, prior)):
                dest = root / rel; dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(value)); hashes[rel] = R.S.digest(dest)
            plan = {'status': 'synthetic', 'input_sha256': hashes, 'dependency_sha256': {},
                    'secondary_metrics': list(R.METRICS), 'seed_indices': [0, 1],
                    'expected_date_range': ['2020-02-14', '2020-02-29'],
                    'exclude_anchors': ['2020-02-27', '2020-02-28'],
                    'expected_queries': 14, 'expected_days': 14,
                    'main_ndcg_distribution': {'quantile_probabilities': list(R.QUANTILES)},
                    'bootstrap': {'draws': 20, 'rng_seed': 42}, 'interpretation_limits': []}
            plan_path = root / 'plan.json'; plan_path.write_text(json.dumps(plan))
            output = root / 'result.json'
            result = R.run(root, plan_path, output)
            self.assertEqual(result['seeds'][0]['metrics']['purchase_ndcg']['queries'], 7)
            self.assertAlmostEqual(result['seeds'][1]['metrics']['recall']['mean_delta'], .1)
            self.assertEqual(result['seeds'][0]['ndcg_distribution']['groups']['improved']['queries'], 14)
            self.assertTrue(output.is_file())

    def test_existing_output_refused_before_source_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'exists.json'; output.write_text('preserve')
            with self.assertRaises(FileExistsError):
                R.run(tmp, Path(tmp) / 'missing-plan.json', output)
            self.assertEqual(output.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
