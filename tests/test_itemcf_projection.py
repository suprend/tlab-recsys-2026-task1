"""Native-free ItemCF contract tests plus independent set-audience oracle."""

from types import ModuleType
import itertools
import math
import random
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT/'scripts/itemcf_projection.py'


def load_projection():
    with SOURCE.open('rb') as stream:
        raw = stream.read(128*1024+1)
    assert len(raw) <= 128*1024
    module = ModuleType('itemcf_projection_under_test')
    module.__file__ = str(SOURCE)
    exec(compile(raw,str(SOURCE),'exec',dont_inherit=True),module.__dict__)
    return module


class ProjectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_projection()

    def project(self, user, candidates, history, postings, **limits):
        options = dict(max_members=1000, max_work=10000, check=lambda: None,
                       cache_pairs=0)
        options.update(limits)
        return self.module.project_itemcf(user, candidates, history, postings,
                                         **options)

    def test_older_than_21_candidate_own_vote_is_still_removed(self):
        history = tuple(range(1, 22))
        postings = {item: (99,) for item in history}
        postings[1] = (2, 3, 4, 99)
        postings[999] = (2, 3, 4, 99)
        row = self.project(99, (999,), history, postings)[0]
        self.assertEqual(row["history_n"], 20)
        self.assertEqual(row["pair_support_max"], 3)
        self.assertEqual(row["supported_pairs"], 1)
        self.assertEqual(row["defined_fraction"], 1 / 20)
        self.assertAlmostEqual(row["itemcf_max"], 3 / 13)
        self.assertAlmostEqual(row["itemcf_mean"], 3 / 260)

    def test_both_norms_and_common_vote_are_corrected(self):
        row = self.project(99, (10,), (20,),
                           {10: (2, 3, 4, 99), 20: (2, 3, 4, 99)})[0]
        self.assertAlmostEqual(row["itemcf_mean"], 3 / 13)
        self.assertEqual(row["pair_support_max"], 3)
        self.assertEqual(row["defined_fraction"], 1.0)
        self.assertFalse(row["candidate_cold"])

    def test_candidate_exclusion_refills_from_21st_history_item(self):
        history = tuple(range(1, 22))
        postings = {item: (5, 6, 7, 99) for item in history}
        postings[1] = postings[21] = (2, 3, 4, 99)
        row = self.project(99, (1,), history, postings)[0]
        self.assertEqual(row["history_n"], 20)
        self.assertEqual(row["supported_pairs"], 1)
        self.assertEqual(row["defined_fraction"], 1.0)
        self.assertAlmostEqual(row["itemcf_mean"], 3 / 260)
        self.assertAlmostEqual(row["itemcf_max"], 3 / 13)

    def test_empty_history_is_distinct_from_candidate_cold(self):
        rows = self.project(99, (10, 11), (), {10: (99,), 11: (2,)})
        for row in rows:
            self.assertEqual(row["itemcf_mean"], 0.0)
            self.assertEqual(row["history_n"], 0)
            self.assertIsNone(row["defined_fraction"])
            self.assertTrue(row["no_history"])
        self.assertTrue(rows[0]["candidate_cold"])
        self.assertFalse(rows[1]["candidate_cold"])
        self.assertEqual(self.project(99, (), (), {}), [])

    def test_known_zero_and_undefined_have_different_coverage(self):
        rows = self.project(99, (10, 11, 12), (20,),
                            {10: (2,), 11: (), 12: (99,), 20: (3, 99)})
        self.assertEqual([r["itemcf_mean"] for r in rows], [0.0, 0.0, 0.0])
        self.assertEqual([r["defined_fraction"] for r in rows], [1.0, 0.0, 0.0])
        self.assertEqual([r["candidate_cold"] for r in rows], [False, True, True])
        self.assertTrue(all(r["supported_pairs"] == 0 for r in rows))

    def test_below_threshold_is_defined_zero_with_nonzero_support(self):
        row = self.project(99, (10,), (20,),
                           {10: (2, 3, 99), 20: (2, 3, 99)})[0]
        self.assertEqual(row["pair_support_max"], 2)
        self.assertEqual(row["supported_pairs"], 0)
        self.assertEqual(row["defined_fraction"], 1.0)
        self.assertEqual(row["itemcf_max"], 0.0)

    def test_raw_cache_does_not_share_personalized_scores(self):
        postings = {10: (2, 3, 4, 99), 20: (2, 3, 4, 99)}
        cold_cache = self.project(99, (10, 20), (10, 20), postings)
        cached = self.project(99, (10, 20), (10, 20), postings, cache_pairs=1)
        other_user = self.project(55, (10, 20), (10, 20), postings, cache_pairs=1)
        self.assertEqual(cached, cold_cache)
        self.assertAlmostEqual(cached[0]["itemcf_mean"], 3 / 13)
        self.assertAlmostEqual(other_user[0]["itemcf_mean"], 4 / 14)
        self.assertEqual([r["product_id"] for r in cached], [10, 20])
        self.assertTrue(all(r["history_n"] == 1 for r in cached))

    def test_duplicate_or_invalid_ids_are_rejected(self):
        cases = [
            (99, (10, 10), (), {10: ()}),
            (99, (10,), (20, 20), {10: (), 20: ()}),
            (True, (), (), {}),
            (None, (), (), {}),
            (99, (None,), (), {}),
            (99, (True,), (), {}),
            (99, (10,), (), {10: (2, 2)}),
            (99, (10,), (), {10: (3, 2)}),
            (99, (10,), (), {10: (None,)}),
        ]
        for user, candidates, history, postings in cases:
            with self.subTest(user=user, candidates=candidates, history=history):
                with self.assertRaises(ValueError):
                    self.project(user, candidates, history, postings)

    def test_missing_postings_are_not_known_empty(self):
        with self.assertRaises(ValueError):
            self.project(99, (10,), (20,), {10: ()})
        row = self.project(99, (10,), (20,), {10: (), 20: ()})[0]
        self.assertEqual(row["defined_fraction"], 0.0)
        self.assertTrue(row["candidate_cold"])

    def test_finite_bounds_and_external_check_fail_without_result(self):
        with self.assertRaises(self.module.LimitExceeded):
            self.project(99, (10,), (), {10: (2,)}, max_members=0)
        with self.assertRaises(self.module.LimitExceeded):
            self.project(99, (10,), (), {10: ()}, max_work=1)
        with self.assertRaises(ValueError):
            self.project(99, (), (), {}, cache_pairs=4401)

        def stop():
            raise RuntimeError("caller stop")

        with self.assertRaisesRegex(RuntimeError, "caller stop"):
            self.project(99, (), (), {}, check=stop)


def reference(user, candidates, history, audiences):
    rows = []
    for candidate in candidates:
        kept = [item for item in history if item != candidate][:20]
        external_candidate = set(audiences[candidate]) - {user}
        scores, supports, defined = [], [], 0
        for item in kept:
            external_history = set(audiences[item]) - {user}
            common = len(external_candidate.intersection(external_history))
            supports.append(common)
            if external_candidate and external_history:
                defined += 1
                cosine = common / math.sqrt(len(external_candidate) * len(external_history))
                scores.append(cosine * common / (common + 10) if common >= 3 else 0.0)
            else:
                scores.append(0.0)
        rows.append(dict(product_id=candidate, itemcf_mean=sum(scores) / len(kept) if kept else 0.0,
                         itemcf_max=max(scores, default=0.0), history_n=len(kept),
                         supported_pairs=sum(common >= 3 for common in supports),
                         pair_support_max=max(supports, default=0),
                         defined_fraction=defined / len(kept) if kept else None,
                         no_history=not kept, candidate_cold=not external_candidate))
    return rows


class IndependentAudienceOracle(unittest.TestCase):
    comparisons = 0

    @classmethod
    def setUpClass(cls):
        cls.target = load_projection()

    def compare(self, candidates, history, audiences, cache_pairs):
        postings = {item: tuple(sorted(users)) for item, users in audiences.items()}
        actual = self.target.project_itemcf(0, candidates, history, postings,
                                          max_members=100, max_work=10000,
                                          check=lambda: None, cache_pairs=cache_pairs)
        expected = reference(0, candidates, history, audiences)
        self.assertEqual(len(actual), len(expected))
        for left, right in zip(actual, expected):
            self.assertEqual(set(left), set(right))
            for key in right:
                if type(right[key]) is float:
                    self.assertLessEqual(abs(left[key] - right[key]), 1e-15, key)
                else:
                    self.assertEqual(left[key], right[key], key)
        type(self).comparisons += 1

    def test_all_single_pair_audiences_over_five_users(self):
        users = range(5)
        subsets = [frozenset(user for user in users if mask & (1 << user)) for mask in range(32)]
        for left, right in itertools.product(subsets, repeat=2):
            self.compare((10,), (20,), {10: left, 20: right}, 0)

    def test_multi_item_projection_with_large_ids_and_raw_cache(self):
        rng = random.Random(2026)
        large = 2**63 - 1
        for case in range(256):
            audiences = {item: frozenset(user for user in range(5) if rng.getrandbits(1))
                         for item in (large, 10, 20, 30)}
            self.compare((large, 10), (large, 10, 20, 30), audiences, case % 5)


if __name__ == '__main__':
    unittest.main()
