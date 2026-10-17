"""Invented literal estimands only; no files, producer, backend or real targets."""
import unittest
from unittest.mock import patch

import estimands as e


def row(q, user, targets=(), prior=(), **arms):
    return dict(query_id=q, user_id=user, targets=set(targets), prior=set(prior),
                arms={a: set(arms.get(a, ())) for a in e.ARMS})


class EstimandTests(unittest.TestCase):
    def test_macro_micro_empty_Y_and_empty_C_have_different_denominators(self):
        self.assertEqual(e.ARMS, ('C0', 'count', 'cos', 'matched_popular', 'matched_count', 'matched_cos'))
        result = e.summarize([row('a', 1, [1], cos=[1]), row('b', 2, range(10, 19)),
                              row('c', 3, cos=[77])])
        full = result['cohorts']['full']
        self.assertEqual((result['queries'], full['positive_queries'], full['target_mass']), (3, 2, 10))
        cos = full['arms']['cos']
        self.assertEqual(cos['macro_recall'], .5)
        self.assertEqual(cos['micro_recall'], .1)
        self.assertEqual((cos['hit_any_positive'], cos['hit_any_all']), (.5, 1/3))
        self.assertEqual(full['arms']['C0']['macro_recall'], 0)
        self.assertEqual(result['contrasts']['full']['cos-C0'], .5)

    def test_new_repeat_use_full_target_slices_including_off_candidate(self):
        result = e.summarize([row('a', 1, [1, 2, 99], [1, 88], C0=[1], cos=[1, 2]),
                              row('b', 2, [3])])
        new, repeat = (result['cohorts'][c] for c in ('new', 'repeat'))
        self.assertEqual((new['target_mass'], new['positive_queries']), (3, 2))
        self.assertEqual((new['arms']['cos']['micro_recall'], new['arms']['cos']['macro_recall']), (1/3, .25))
        self.assertEqual((repeat['target_mass'], repeat['positive_queries']), (1, 1))
        self.assertEqual(result['contrasts']['repeat']['cos-C0'], 0)
        self.assertEqual(result['contrasts']['new']['cos-C0'], .25)

    def test_matched_k_zero_row_stays_in_same_positive_denominator(self):
        result = e.summarize([row('a', 1, [1], matched_popular=[2], matched_cos=[1]),
                              row('b', 2, [3], matched_popular=[3], matched_cos=[3])])
        self.assertEqual(result['contrasts']['full'][e.MATCHED], .5)
        self.assertEqual(result['cohorts']['full']['positive_queries'], 2)

    def test_full_candidate_recall_and_oracle20_h20_m100_gold(self):
        full = e.summarize([row('a', 1, range(1, 101), C0=range(1, 11),
                                count=range(1, 21), cos=range(1, 26))])['cohorts']['full']['arms']
        self.assertEqual(full['cos']['macro_recall'], .25)
        self.assertEqual(full['count']['oracle_ndcg20'], 1)
        self.assertAlmostEqual(full['C0']['oracle_ndcg20'], 4.543559338088346 / 7.040268381923513, places=14)

    def test_type7_independent_literal_interpolation_and_undefined(self):
        self.assertEqual(e.type7([30, 0, 20, 10], .25), 7.5)
        self.assertAlmostEqual(e.type7([0, 10, 20, 30], .025), .75, places=14)
        self.assertAlmostEqual(e.type7([0, 10, 20, 30], .975), 29.25, places=14)
        self.assertEqual(e.type7([42], .975), 42)
        self.assertIsNone(e.type7([], .5))
        with self.assertRaises(ValueError):
            e.type7([float('nan')], .5)

    def test_cluster_multiplicity_all_days_empty_user_frame_and_undefined_draw(self):
        records = [row('a', 10, [1], cos=[1], count=[1]), row('b', 10, [2]),
                   row('c', 20, [3]), row('d', 30)]
        class Draws:
            def __init__(self):
                self.choices, self.bounds = iter([0, 0, 1, 2, 2, 2, 1, 1, 0]), []
            def randrange(self, bound):
                self.bounds.append(bound)
                return next(self.choices)
        stub = Draws()
        with patch.object(e, 'Random', return_value=stub) as factory:
            result = e.cluster_bootstrap(records, draws=3)
        factory.assert_called_once_with(61061)
        self.assertEqual(stub.bounds, [3] * 9)
        self.assertEqual(result['frame_users'], 3)
        primary = result['intervals']['full'][e.PRIMARY]
        self.assertEqual((primary['defined_draws'], primary['undefined_draws']), (2, 1))
        self.assertIsNone(primary['ci95'])
        secondary = result['intervals']['full']['count-C0']
        self.assertAlmostEqual(secondary['ci95'][0], .25375, places=14)
        self.assertAlmostEqual(secondary['ci95'][1], .39625, places=14)
        self.assertTrue(secondary['conditional_on_defined'])
        self.assertEqual(result['intervals']['repeat'][e.PRIMARY]['defined_draws'], 0)

    def test_all_empty_Y_stays_undefined_not_zero(self):
        result = e.analyze([row('a', 1), row('b', 2)], draws=3)
        self.assertIsNone(result['summary']['contrasts']['full'][e.PRIMARY])
        self.assertEqual(result['bootstrap']['intervals']['full'][e.PRIMARY]['undefined_draws'], 3)
        self.assertEqual(result['decision'], 'inconclusive')
        self.assertFalse(result['continuation'])

    def test_equal_cluster_multiplicities_use_ascending_user_sum_order(self):
        records = [row('a', 10, [1], cos=[1]), row('b', 20, [2], C0=[2]),
                   row('c', 30, range(10), cos=[0])]
        choices = iter([0, 2, 1, 0, 1, 2])
        with patch.object(e, 'Random') as factory:
            factory.return_value.randrange.side_effect = lambda _: next(choices)
            ci = e.cluster_bootstrap(records, draws=2)['intervals']['full'][e.PRIMARY]['ci95']
        self.assertEqual(ci, [1/30, 1/30])

    def test_continuation_requires_native_primary_lower_and_matched_point(self):
        good = row('a', 1, [1], cos=[1], matched_popular=[2], matched_cos=[1])
        self.assertTrue(e.analyze([good], draws=2)['continuation'])
        good['arms']['matched_popular'] = {1}
        self.assertFalse(e.analyze([good], draws=2)['continuation'])
        count_only = row('a', 1, [1], count=[1], matched_cos=[1])
        self.assertFalse(e.analyze([count_only], draws=2)['continuation'])

    def test_bad_ID_duplicate_query_and_guard_are_rejected(self):
        with self.assertRaises(ValueError):
            e.summarize([row('a', True)])
        with self.assertRaises(ValueError):
            e.summarize([row('a', 1), row('a', 2)])
        def exhausted():
            raise RuntimeError('guard')
        with self.assertRaisesRegex(RuntimeError, 'guard'):
            e.analyze([row('a', 1)], draws=2, check=exhausted)


if __name__ == '__main__':
    unittest.main()
