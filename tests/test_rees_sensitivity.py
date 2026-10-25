"""Small exact examples for pairing, estimands, dates and immutable inputs."""
import itertools
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from scripts import rees_sensitivity as s


def frame(values=(0.1, 0.2, 0.3)):
    return pd.DataFrame({'qid': ['2020-02-08:1', '2020-02-09:1', '2020-02-09:2'], 'ndcg': values,
                         'anchor': ['2020-02-08', '2020-02-09', '2020-02-09'], 'half': ['B', 'B', 'A']})


class PairingTest(unittest.TestCase):
    def test_pairs_by_key_not_input_order(self):
        pair = s.pair_frames(frame(), frame((.2, .4, .5)).iloc[::-1])
        np.testing.assert_allclose(pair.delta, [.1, .2, .2])
        self.assertEqual(list(pair.user_id), ['1', '1', '2'])

    def test_missing_or_duplicate_queries_fail_before_filtering(self):
        for changed in (frame().iloc[:2], pd.concat([frame(), frame().iloc[:1]], ignore_index=True)):
            with self.subTest(), self.assertRaises(ValueError):
                s.pair_frames(frame(), changed, half='B')

    def test_bad_anchor_half_or_metric_rejected(self):
        for column, value in [('anchor', '2020-02-10'), ('half', 'A'), ('ndcg', float('nan')),
                              ('ndcg', float('inf')), ('ndcg', 1.1), ('qid', None)]:
            bad = frame()
            bad.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                s.pair_frames(frame(), bad)

    def test_half_selection_and_exclusion_preserve_pairing(self):
        pair = s.pair_frames(frame(), frame((.2, .4, .5)), half='B')
        self.assertEqual(len(pair), 2)
        self.assertAlmostEqual(pair.delta.mean(), .15)
        pair = s.pair_frames(frame(), frame((.2, .4, .5)), excluded=['2020-02-09'])
        self.assertEqual(len(pair), 1)
        self.assertAlmostEqual(pair.delta.mean(), .1)

    def test_exact_dates_not_only_date_count(self):
        pair = s.pair_frames(frame(), frame())
        s.check_dates(pair, ['2020-02-08', '2020-02-09'])
        with self.assertRaises(ValueError):
            s.check_dates(pair, ['2020-02-09', '2020-02-10'])


class ResamplingTest(unittest.TestCase):
    def test_unequal_clusters_resample_query_weighted_ratio(self):
        sums, counts, _ = s.cluster_totals([1., 0., 0., 0.], ['a', 'b', 'b', 'b'])
        indices = np.array(list(itertools.product(range(2), repeat=2)))
        actual = s.resampled_means(sums, counts, indices)
        np.testing.assert_allclose(actual, [1., .25, .25, 0.])
        self.assertNotEqual(actual[1], .5)  # Equal-weight users would change the estimand.
        self.assertAlmostEqual(s.bootstrap([1., 0., 0., 0.], ['a', 'b', 'b', 'b'], 100, 7)['mean_delta'], .25)

    def test_deterministic_and_singletons_match_query_bootstrap(self):
        delta = [.2, -.1, .3, .05]
        a = s.bootstrap(delta, ['a', 'b', 'c', 'd'], 500, 2026)
        self.assertEqual(a, s.bootstrap(delta, ['a', 'b', 'c', 'd'], 500, 2026))
        b = s.bootstrap(delta, [0, 1, 2, 3], 500, 2026)
        self.assertEqual(a['ci95'], b['ci95'])
        self.assertEqual(a['mean_delta'], b['mean_delta'])

    def test_leave_one_day_out_uses_remaining_query_counts(self):
        pair = s.pair_frames(frame(), frame((.2, .4, .6)))
        rows = s.day_diagnostics(pair)
        self.assertEqual([x['queries'] for x in rows], [1, 2])
        self.assertAlmostEqual(rows[0]['leave_this_day_out_delta'], .25)
        self.assertAlmostEqual(rows[1]['leave_this_day_out_delta'], .1)


class ProvenanceTest(unittest.TestCase):
    def test_input_mutation_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            p = root / 'input'
            p.write_text('original')
            hashes = {'input': s.digest(p)}
            s.check_hashes(root, hashes)
            p.write_text('changed')
            with self.assertRaises(ValueError):
                s.check_hashes(root, hashes)

    def test_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'result.json'
            target.write_text('existing')
            with self.assertRaises(FileExistsError):
                s.run(root, root / 'nonexistent-plan.json', target)
            self.assertEqual(target.read_text(), 'existing')

    def test_training_comparability_rejects_mismatched_sampling(self):
        extra = [f'agent_{i}' for i in range(30)]
        cfg = {'seed': 2026, 'neg_seed': 0, 'days': 'same', 'extra': extra}
        ref = {'name': 'Hag', 'cfg': cfg, 'features': 146, 'train_rows': 100, 'fit_queries': 101959}
        new = {'name': 'Hp', 'cfg': cfg | {'extra': ['dfs_p', 'dfs_c', 'dfs_b', 'dfs_u'] + extra},
               'features': 274, 'train_rows': 100}
        declared = {'Hag': {'name': 'Hag'}, 'Hp': {'name': 'Hp'}}
        s.check_training_pair(ref, new, declared, 0, '2019')
        for key, value in [('neg_seed', 99), ('cap', 100), ('days', 'different')]:
            bad = new | {'cfg': new['cfg'] | {key: value}}
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.check_training_pair(ref, bad, declared, 0, '2019')
        with self.assertRaises(ValueError):
            s.check_training_pair(ref, new | {'train_rows': 101}, declared, 0, '2019')


if __name__ == '__main__':
    unittest.main()
