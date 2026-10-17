"""One bounded literal-only verifier check; no primary, backend or real data imports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

oracle = load('independent_io_literal', HERE/'oracle.py')
stats = load('independent_stats_literal', HERE/'oracle_stats.py')

def row(q, user, target=(), prior=(), **arms):
    return dict(query_id=q, user_id=user, targets=set(target), prior=set(prior),
                arms={a: frozenset(arms.get(a, ())) for a in oracle.ARMS})

def four_rows():
    return [row('a', 10, (1, 2), (1,), C0=(1,), cos=(1, 2), count=(2,), matched_popular=(1,), matched_cos=(2,)),
            row('b', 10, (3,), (), count=(3,), matched_cos=(3,)),
            row('c', 20, (4, 5, 6, 7), (4, 8), C0=(4,), cos=(4,), matched_cos=(4,)),
            row('d', 30, (), (), C0=(999,))]


class LiteralChecks(unittest.TestCase):
    def test_unequal_query_mass_full_new_repeat_and_oracle(self):
        result = stats.calculate(four_rows(), draws=3)['summary']
        self.assertEqual(result['frame'], dict(queries=4, users=3, positive_queries=3, zero_target_queries=1, target_mass=7))
        full = result['arms']['cos']['full']
        self.assertAlmostEqual(full['macro_recall'], 5/12, places=14)
        self.assertAlmostEqual(full['micro_recall'], 3/7, places=14)
        self.assertEqual(full['hit_any'], 2)
        self.assertEqual(full['hit_any_over_positive_queries'], 2/3)
        self.assertEqual(full['hit_any_over_all_queries'], .5)
        self.assertAlmostEqual(result['contrasts']['cos-C0']['full']['estimate'], 1/6, places=14)
        self.assertEqual(result['slices']['new'], dict(positive_queries=3, target_mass=5))
        self.assertEqual(result['slices']['repeat'], dict(positive_queries=2, target_mass=2))
        self.assertAlmostEqual(result['arms']['cos']['new']['macro_recall'], 1/3, places=14)
        self.assertEqual(result['arms']['cos']['repeat']['macro_recall'], 1)
        ceiling = stats.calculate([row('z', -7, range(100), (), count=range(20))], draws=1)['summary']['arms']['count']['full']
        self.assertEqual(ceiling['macro_recall'], .2)
        self.assertEqual(ceiling['oracle_ndcg20'], 1)

    def test_shared_complete_user_draws_multiplicity_and_undefined_type7(self):
        class LiteralRNG:
            def __init__(self):
                self.values, self.bounds = iter([0, 0, 1, 2, 2, 2, 1, 1, 0]), []
            def randrange(self, bound):
                self.bounds.append(bound)
                return next(self.values)
        rng = LiteralRNG()
        with patch.object(stats.random, 'Random', return_value=rng) as factory:
            result = stats.calculate(four_rows(), draws=3)
        factory.assert_called_once_with(61061)
        self.assertEqual(rng.bounds, [3]*9)
        private, public = result['_bootstrap'], result['summary']
        self.assertEqual(private['user_ids'], [10, 20, 30])
        self.assertEqual(private['draw_denominators']['full'], [5, 0, 4])
        self.assertEqual(private['draw_contrasts']['cos-C0']['full'], [.2, None, .125])
        expected = hashlib.sha256(b''.join(n.to_bytes(4, 'big') for n in [2, 1, 0])).hexdigest()
        self.assertEqual(private['multiplicity_sha256'][0], expected)
        primary = public['contrasts']['cos-C0']['full']
        self.assertEqual((primary['defined_draws'], primary['undefined_draws']), (2, 1))
        self.assertIsNone(primary['ci95'])
        secondary = public['contrasts']['count-C0']['full']['ci95']
        self.assertAlmostEqual(secondary[0], .130625, places=14)
        self.assertAlmostEqual(secondary[1], .344375, places=14)
        self.assertEqual(public['continuation']['decision'], 'inconclusive')

    def test_six_arm_literal_reconstruction_and_k_zero(self):
        q = dict(global_rank=0, query_id='fictional', user_id=1, anchor=oracle.DATES[0])
        support = [[100, 3, 3, 3]]
        core = dict(seeds=[100], source=dict(count=[200], cosine=[200]),
                    ranked_source={n: [dict(rank=1, product_id=200, score=v, support=support)] for n, v in [('count', 9/13), ('cosine', 3/13)]},
                    domain=[dict(product_id=200, support=support, count=9/13, cosine=3/13, in_C0=False)],
                    rejection=[dict(seed=100, degree=3, reason='admitted', support_below3=0)], profile_edge_visits=6,
                    distinct_top20_sets=False, query_id='fictional', C_count=[1, 100, 200], C_cos=[1, 100, 200])
        candidate = dict(q, C0=[1, 2, 100], P180=[1], R20=[100], core_result=core,
                         controls=dict(B=[1, 100], T=[2], k=1, matched_popular=[1, 100, 2], matched_count=[1, 100, 200], matched_cosine=[1, 100, 200]), prior_pair_count=0)
        arms, visits = oracle.reconstruct(candidate, q)
        self.assertEqual(visits, 6)
        self.assertEqual(arms['C0'], frozenset((1, 2, 100)))
        self.assertEqual(arms['cos'], frozenset((1, 100, 200)))
        candidate['C0'] = [1, 100]
        candidate['controls'].update(T=[], k=0, matched_popular=[1, 100], matched_count=[1, 100], matched_cosine=[1, 100])
        arms, _ = oracle.reconstruct(candidate, q)
        self.assertEqual(arms['matched_popular'], arms['matched_cos'])
        candidate['controls']['k'] = 1
        with self.assertRaisesRegex(ValueError, 'cardinality'):
            oracle.reconstruct(candidate, q)
        with self.assertRaises(ValueError):
            oracle.sequence([True], 1)

    def test_private_count_and_change_identity_comparison_detects_wrong_target(self):
        q = row('fictional', 4, (1, 9), (1,), C0=(1,), cos=(9,), matched_cos=(9,), matched_popular=(1,))
        q['anchor'] = oracle.DATES[0]
        parts = (q['targets'], q['targets']-q['prior'], q['targets']&q['prior'])
        audit = dict(query_id=q['query_id'], user_id=4, anchor=q['anchor'], target_mass=[2, 1, 1],
                     hits={a: [len(y & q['arms'][a]) for y in parts] for a in oracle.ARMS}, candidate_sizes={a: len(q['arms'][a]) for a in oracle.ARMS})
        changes = [dict(query_id='fictional', product_id=9, contrast='cos-C0', direction='gained', new_pair=True),
                   dict(query_id='fictional', product_id=1, contrast='cos-C0', direction='lost', new_pair=False),
                   dict(query_id='fictional', product_id=1, contrast='count-C0', direction='lost', new_pair=False),
                   dict(query_id='fictional', product_id=9, contrast='cos-count', direction='gained', new_pair=True),
                   dict(query_id='fictional', product_id=9, contrast='matched_cos-matched_popular', direction='gained', new_pair=True),
                   dict(query_id='fictional', product_id=1, contrast='matched_cos-matched_popular', direction='lost', new_pair=False)]
        with tempfile.TemporaryDirectory(prefix='literal-', dir=HERE) as name:
            a, b = Path(name)/'audit.jsonl', Path(name)/'changes.jsonl'
            a.write_bytes(oracle.encode(audit));b.write_bytes(b''.join(oracle.encode(r) for r in changes))
            result = oracle.compare_private([q], a, b, lambda: None)
            self.assertEqual(result['private_queries_checked'], 1)
            self.assertEqual(result['private_target_change_rows_checked'], 6)
            changes[0]['product_id'] = 90;b.write_bytes(b''.join(oracle.encode(r) for r in changes))
            with self.assertRaisesRegex(ValueError, 'identities'):
                oracle.compare_private([q], a, b, lambda: None)


    def test_primary_schema_adapter_against_one_positive_query_literal(self):
        records = [row('literal', 1, (1,), (), cos=(1,), matched_cos=(1,))]
        independent = stats.calculate(records, draws=2000)
        primary = dict(summary=dict(queries=1, users=1, cohorts={}, contrasts={}),
                       bootstrap=dict(draws=2000, seed=61061, frame_users=1, intervals={}, sampler='declared'),
                       continuation=True, decision='propose_optional_continuation', inference_scope='declared',
                       status='EXPLORATORY_AGGREGATE_UNVERIFIED', reused_historical_cohort=True,
                       achieved_ranking_quality=False, causal_or_generalization_claim=False,
                       primary_normalization_claim=False, automatic_new_model=False,
                       analysis_sha256=oracle.ANALYSIS_SHA, rng='declared')
        for cohort in oracle.COHORTS:
            positive = cohort != 'repeat'
            primary['summary']['cohorts'][cohort] = dict(target_mass=int(positive), positive_queries=int(positive), arms={})
            for arm in oracle.ARMS:
                hit = int(positive and arm in ('cos', 'matched_cos'))
                primary['summary']['cohorts'][cohort]['arms'][arm] = dict(hits=hit, micro_recall=float(hit) if positive else None,
                    macro_recall=float(hit) if positive else None, hit_any_queries=hit,
                    hit_any_positive=float(hit) if positive else None, hit_any_all=float(hit), oracle_ndcg20=float(hit) if positive else None)
            primary['summary']['contrasts'][cohort] = {}
            primary['bootstrap']['intervals'][cohort] = {}
            for contrast, _, _ in oracle.PAIRS:
                value = (0.0 if contrast == 'count-C0' else 1.0) if positive else None
                primary['summary']['contrasts'][cohort][contrast] = value
                primary['bootstrap']['intervals'][cohort][contrast] = dict(ci95=[value, value] if positive else None,
                    defined_draws=2000 if positive else 0, undefined_draws=0 if positive else 2000,
                    conditional_on_defined=not(cohort == 'full' and contrast == 'cos-C0'))
        result = oracle.compare_summary(independent, primary)
        self.assertEqual(result['maximum_absolute_error'], 0.0)
        primary['summary']['cohorts']['full']['arms']['cos']['macro_recall'] = .9
        with self.assertRaisesRegex(ValueError, 'Numerical'):
            oracle.compare_summary(independent, primary)


if __name__ == '__main__':
    signal.alarm(6)
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    wall, cpu = time.monotonic(), time.process_time()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LiteralChecks))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss = int(rss if sys.platform == 'darwin' else rss*1024)
    print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                         success=result.wasSuccessful(), cpu_prefix=time.process_time()-cpu,
                         wall_prefix=time.monotonic()-wall, rss_bytes=rss, actual_data_reads=0,
                         native_imports=0, fits=0, predictions=0), sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and rss <= 256*2**20 else 1)
