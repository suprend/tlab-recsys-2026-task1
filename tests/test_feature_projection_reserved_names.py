"""Literal registry/projection regressions for compiler and loader namespaces."""
from copy import deepcopy
from pathlib import Path
import unittest

from scripts.manual_features import load_registry, validate_registry
from scripts.train_baselines import numeric_feature_names

ROOT = Path(__file__).resolve().parents[1]
KEYS = ['query_id', 'user_id', 'product_id', 'anchor',
        'candidate_category_id', 'last_user_event_time']
# Independent literal B41 order: no names are taken from the implementation.
B41 = [
    'from_popular', 'from_recent', 'popularity_distinct_users',
    'popular_source_rank', 'recent_source_rank',
    'candidate_category_ambiguous', 'candidate_category_missing',
    'item_has_observed_history', 'user_has_observed_history',
    'item_observed_age_seconds', 'user_observed_age_seconds',
    'user_view_7d', 'user_cart_7d', 'user_purchase_7d',
    'user_distinct_viewed_items_7d', 'pair_view_7d', 'pair_cart_7d',
    'pair_purchase_7d', 'pair_view_recency_seconds',
    'pair_purchase_recency_seconds', 'item_view_24h', 'item_purchase_24h',
    'item_distinct_viewers_7d', 'user_category_view_7d',
    'user_category_view_recency_seconds', 'item_category_view_7d',
    'category_view_7d', 'source_coverage_24h', 'source_coverage_168h',
    'user_category_view_share_7d', 'item_category_view_share_7d',
    'pair_view_recency_seconds_missing', 'pair_purchase_recency_seconds_missing',
    'user_category_view_7d_missing', 'user_category_view_share_7d_missing',
    'user_category_view_recency_seconds_missing', 'item_category_view_7d_missing',
    'category_view_7d_missing', 'item_category_view_share_7d_missing',
    'retrieval_last_event_age_seconds', 'retrieval_last_event_missing',
]


class ReservedProjectionTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(ROOT / 'configs/features/manual-18.json')

    def renamed(self, old, new):
        registry = deepcopy(self.registry)
        next(f for f in registry['features'] if f['name'] == old)['name'] = new
        return registry

    def test_registry_rejects_direct_retrieval_age_and_generated_missing_collision(self):
        for old, new in [
            ('pair_cart_7d', 'retrieval_last_event_age_seconds'),
            ('pair_cart_7d', 'retrieval_last_event_missing'),
            ('pair_view_recency_seconds', 'retrieval_last_event'),
            ('user_category_view_recency_seconds', 'retrieval_last_event'),
        ]:
            with self.subTest(old=old, new=new), self.assertRaisesRegex(ValueError, 'unique safe'):
                validate_registry(self.renamed(old, new))

    def test_existing_retrieval_physical_names_and_duplicate_unsafe_names_reject(self):
        for name in ['from_popular', 'from_recent', 'popularity_distinct_users',
                     'popular_source_rank', 'recent_source_rank', 'last_user_event_time',
                     'query_id', 'user_view_7d', 'unsafe"name', 'source_coverage_168h']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_registry(self.renamed('pair_cart_7d', name))

    def test_full_emitted_closure_allows_noncolliding_root_and_canonical_registry(self):
        self.assertEqual(validate_registry(self.registry), self.registry)
        # A plain pair count with this root emits no missing flag and is safe.
        valid = self.renamed('pair_cart_7d', 'retrieval_last_event')
        self.assertEqual(validate_registry(valid), valid)
        valid = self.renamed('pair_view_recency_seconds', 'custom_recency_seconds')
        self.assertEqual(validate_registry(valid), valid)

    def test_projection_checks_final_names_after_appending_both_retrieval_fields(self):
        for name in ['retrieval_last_event_age_seconds', 'retrieval_last_event_missing']:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unsafe/duplicate'):
                numeric_feature_names(KEYS + [name])
        for names in [['ordinary', 'ordinary'], ['unsafe"name'], ['1starts_with_digit'],
                      ['dotted.name'], ['non_ascii_я'], [None], [[]], ['query_id']]:
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, 'Unsafe/duplicate'):
                numeric_feature_names(KEYS + names)

    def test_literal_b41_order_and_unique_counts_remain_exact(self):
        physical = KEYS + B41[:-2]
        actual = numeric_feature_names(physical)
        self.assertEqual(actual, B41)
        self.assertEqual(len(actual), 41)
        self.assertEqual(len(set(actual)), 41)


if __name__ == '__main__':
    unittest.main()
