import unittest

from scripts.ranking_metrics import QueryRanking, evaluate, paired_user_bootstrap, score_query


class RankingMetricsTests(unittest.TestCase):
    def test_full_targets_define_denominators_even_outside_catalog_and_shortlist(self):
        # Only 'seen' was retrieved. 'cold' and 'missed' must remain in full Y.
        query = QueryRanking("q", "u", ["seen"], {"seen", "cold", "missed"})
        result = score_query(query, 20)
        self.assertEqual(result.target_count, 3)
        self.assertEqual(result.returned_count, 1)
        self.assertEqual(result.hits, 1)
        self.assertAlmostEqual(result.metrics.recall, 1 / 3)
        self.assertAlmostEqual(result.metrics.ndcg, 0.46927872602275644)
        self.assertAlmostEqual(result.metrics.average_precision, 1 / 3)
        self.assertEqual(result.metrics.reciprocal_rank, 1)
        self.assertEqual(score_query(query, 3).metrics, result.metrics)

    def test_shortlist_is_not_filled_and_empty_candidates_are_misses(self):
        short = score_query(QueryRanking("short", "u", ["other"], {"positive"}), 20)
        empty = score_query(QueryRanking("empty", "u", [], {"positive"}), 20)
        for result in (short, empty):
            self.assertEqual(result.hits, 0)
            self.assertEqual(result.metrics.recall, 0)
            self.assertEqual(result.metrics.ndcg, 0)
        self.assertEqual(short.returned_count, 1)
        self.assertEqual(empty.returned_count, 0)

    def test_multiple_hits_and_cutoff_have_hand_computed_precision(self):
        query = QueryRanking("q", "u", ["noise", "b", "a", "c"], {"a", "b", "c"})
        at_two = score_query(query, 2)
        self.assertAlmostEqual(at_two.metrics.recall, 1 / 3)
        self.assertAlmostEqual(at_two.metrics.ndcg, 0.38685280723454163)
        self.assertAlmostEqual(at_two.metrics.average_precision, 1 / 6)
        self.assertEqual(at_two.metrics.reciprocal_rank, 0.5)
        at_three = score_query(query, 3)
        self.assertAlmostEqual(at_three.metrics.recall, 2 / 3)
        self.assertAlmostEqual(at_three.metrics.average_precision, 7 / 18)

    def test_single_target_ap_equals_rr_and_input_order_defines_tie_policy(self):
        # The caller resolves tied scores; the evaluator consumes precisely that order.
        first = score_query(QueryRanking("q", "u", ["a", "b"], ["a", "a"]), 2)
        second = score_query(QueryRanking("q", "u", ["b", "a"], {"a"}), 2)
        self.assertEqual(first.target_count, 1)
        self.assertEqual(first.metrics.ndcg, 1)
        self.assertAlmostEqual(second.metrics.ndcg, 0.6309297535714575)
        self.assertEqual(second.metrics.average_precision, second.metrics.reciprocal_rank)
        self.assertEqual(second.metrics.average_precision, 0.5)

    def test_empty_mature_targets_and_censoring_remain_distinct(self):
        rows = [
            QueryRanking("hit", "a", ["x"], {"x"}),
            QueryRanking("miss", "a", [], {"x"}),
            QueryRanking("zero", "b", ["x"], set()),
            QueryRanking("censored", "c", ["x"], None, mature=False),
        ]
        report = evaluate(rows, 20)
        self.assertEqual((report.query_count, report.mature_query_count,
                          report.nonempty_query_count, report.censored_query_count), (4, 3, 2, 1))
        self.assertEqual((report.mature_user_count, report.positive_user_count), (2, 1))
        self.assertAlmostEqual(report.nonempty_fraction, 2 / 3)
        self.assertEqual(report.conditional_macro_query.ndcg, 0.5)
        self.assertAlmostEqual(report.all_query_zero.ndcg, 1 / 3)
        self.assertAlmostEqual(report.all_query_zero.ndcg,
                               report.nonempty_fraction * report.conditional_macro_query.ndcg)
        self.assertEqual(report.conditional_user_macro.ndcg, 0.5)
        self.assertEqual(report.all_user_macro_zero.ndcg, 0.25)
        self.assertIsNone(score_query(rows[2], 20).metrics.ndcg)
        self.assertEqual(score_query(rows[2], 20).target_count, 0)
        self.assertIsNone(score_query(rows[3], 20).target_count)

    def test_query_macro_and_user_macro_are_different_estimands(self):
        rows = [QueryRanking(f"a{i}", "a", ["x"], {"x"}) for i in range(3)]
        rows += [QueryRanking("b", "b", [], {"x"})]
        report = evaluate(rows, 1)
        self.assertEqual(report.conditional_macro_query.recall, 0.75)
        self.assertEqual(report.conditional_user_macro.recall, 0.5)

    def test_all_empty_and_all_censored_report_missing_denominators(self):
        empty = evaluate([QueryRanking("q", "u", [], set())], 1)
        self.assertEqual(empty.nonempty_fraction, 0)
        self.assertIsNone(empty.conditional_macro_query.ndcg)
        self.assertIsNone(empty.conditional_user_macro.ndcg)
        self.assertEqual(empty.all_query_zero.ndcg, 0)
        self.assertEqual(empty.all_user_macro_zero.ndcg, 0)
        for rows in ([], [QueryRanking("q", "u", [], None, mature=False)]):
            result = evaluate(rows, 1)
            self.assertIsNone(result.nonempty_fraction)
            self.assertIsNone(result.all_query_zero.recall)
            self.assertIsNone(result.all_user_macro_zero.recall)

    def test_invalid_ranks_k_and_missing_full_labels_are_rejected(self):
        for ranked in (["x", "x"], ["a", "b", "a"], {"a", "b"}, "ab"):
            with self.subTest(ranked=ranked), self.assertRaises(ValueError):
                QueryRanking("q", "u", ranked, {"x"})
        query = QueryRanking("q", "u", [], {"x"})
        for k in (0, -1, 1.5, True):
            with self.subTest(k=k), self.assertRaises(ValueError):
                score_query(query, k)
        with self.assertRaises(ValueError):
            QueryRanking("q", "u", [], None)
        with self.assertRaises(ValueError):
            QueryRanking("q", "u", [], {"x"}, mature=False)
        with self.assertRaises(ValueError):
            evaluate([query, query], 1)


class PairedBootstrapTests(unittest.TestCase):
    def setUp(self):
        # A has 3 queries, B has 1. Sampling A+B gives query macro 3/4,
        # not the user macro 1/2. Sampling A+A or B+B gives 1 or 0.
        self.left = [QueryRanking(f"a{i}", "a", ["x"], {"x"}) for i in range(3)]
        self.left += [QueryRanking("b", "b", [], {"x"})]
        self.right = [QueryRanking(row.query_id, row.user_id, [], row.targets) for row in self.left]

    def test_cluster_draws_preserve_query_macro_and_seed(self):
        result = paired_user_bootstrap(self.left, self.right, 1, metric="recall", replicates=80, seed=7)
        repeat = paired_user_bootstrap(self.left, reversed(self.right), 1, metric="recall", replicates=80, seed=7)
        self.assertEqual(result, repeat)
        self.assertEqual(result.estimate, 0.75)
        self.assertEqual(set(result.samples), {0.0, 0.75, 1.0})
        self.assertEqual(result.undefined_draws, 0)
        self.assertEqual(result.interval_95, (0.0, 1.0))
        user = paired_user_bootstrap(self.left, self.right, 1, metric="recall",
                                     estimand="conditional_user_macro", replicates=80, seed=7)
        self.assertEqual(user.estimate, 0.5)
        self.assertEqual(set(user.samples), {0.0, 0.5, 1.0})

    def test_difference_uses_one_paired_multiplicity(self):
        identical = paired_user_bootstrap(self.left, list(reversed(self.left)), 1, replicates=100, seed=13)
        self.assertEqual(set(identical.samples), {0.0})
        self.assertEqual(identical.interval_95, (0.0, 0.0))
        opposite = [QueryRanking(row.query_id, row.user_id,
                                 [] if row.user_id == "a" else ["x"], row.targets) for row in self.left]
        result = paired_user_bootstrap(self.left, opposite, 1, replicates=80, seed=7)
        self.assertEqual(result.estimate, 0.5)
        self.assertEqual(set(result.samples), {-1.0, 0.5, 1.0})

    def test_zero_positive_draws_are_explicit_and_not_redrawn(self):
        rows = [QueryRanking("positive", "a", ["x"], {"x"}),
                QueryRanking("empty", "b", [], set()),
                QueryRanking("censored", "c", [], None, mature=False)]
        result = paired_user_bootstrap(rows, rows, 1, replicates=100, seed=7)
        self.assertEqual(result.user_count, 2)
        self.assertEqual(len(result.samples), 100)
        self.assertGreater(result.undefined_draws, 0)
        self.assertEqual(result.undefined_draws, result.samples.count(None))
        self.assertEqual(set(result.samples), {None, 0.0})
        self.assertEqual(result.interval_95, (0.0, 0.0))
        zero = paired_user_bootstrap(rows, rows, 1, estimand="all_query_zero", replicates=100, seed=7)
        self.assertEqual(zero.undefined_draws, 0)
        self.assertEqual(set(zero.samples), {0.0})
        all_empty = paired_user_bootstrap(rows[1:2], rows[1:2], 1, replicates=5)
        self.assertEqual(all_empty.undefined_draws, 5)
        self.assertIsNone(all_empty.estimate)
        self.assertIsNone(all_empty.interval_95)
        absent = paired_user_bootstrap([], [], 1, replicates=5)
        self.assertEqual(absent.user_count, 0)
        self.assertEqual(absent.samples, (None,) * 5)

    def test_zero_conventions_preserve_query_and_user_denominators(self):
        left = [QueryRanking("a-hit", "a", ["x"], {"x"}),
                QueryRanking("a-empty", "a", [], set()),
                QueryRanking("b-miss", "b", [], {"x"})]
        right = [QueryRanking(row.query_id, row.user_id, [], row.targets) for row in left]
        query = paired_user_bootstrap(left, right, 1, estimand="all_query_zero", replicates=80, seed=7)
        user = paired_user_bootstrap(left, right, 1, estimand="all_user_macro_zero", replicates=80, seed=7)
        self.assertAlmostEqual(query.estimate, 1 / 3)
        self.assertEqual(set(query.samples), {0.0, 1 / 3, 0.5})
        self.assertEqual(user.estimate, 0.25)
        self.assertEqual(set(user.samples), {0.0, 0.25, 0.5})

    def test_pair_population_labels_and_bootstrap_budget_must_match(self):
        bad_pairs = [self.right[:-1],
                     [QueryRanking("a0", "a", [], {"different"}), *self.right[1:]],
                     [QueryRanking("a0", "other-user", [], {"x"}), *self.right[1:]],
                     [QueryRanking("a0", "a", [], None, mature=False), *self.right[1:]]]
        for right in bad_pairs:
            with self.subTest(right=right), self.assertRaises(ValueError):
                paired_user_bootstrap(self.left, right, 1)
        for repeats in (0, -1, 1001, 1.5, True):
            with self.subTest(repeats=repeats), self.assertRaises(ValueError):
                paired_user_bootstrap(self.left, self.right, 1, replicates=repeats)
        for options in ({"metric": "unknown"}, {"estimand": "unknown"}, {"seed": None}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                paired_user_bootstrap(self.left, self.right, 1, **options)


if __name__ == "__main__":
    unittest.main()
