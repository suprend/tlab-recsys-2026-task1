"""council.posthoc_ctest_t on synthetic test.json: t over the four seed means against 2.35 at the edges (just below
and at the bound, s = 0, both signs), the caveat only for 'уступает' / 'обыгрывает H+', both read-test formats
(REES46 primary / all_16_days, xfer h1 / contrasts / mechanism), the fallback through the per-fit 'mean', the
report of missing fields, and a guard that the module reads JSON only."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from council import design as D
from council import posthoc_ctest_t as P


def seeds_with_t(t: float, mean: float = 0.001) -> list[float]:
    """Four per-seed means with the given mean and t = mean / (s/2): mean ± a, a = s * sqrt(3) / 2."""
    s = abs(mean) * 2 / abs(t)
    a = s * math.sqrt(3) / 2
    return [mean + a, mean + a, mean - a, mean - a]


def h1(by_pair, verdict):
    m = sum(by_pair) / len(by_pair)
    return {'delta': m, 'lower': m - 1e-4, 'upper': m + 1e-4, 'pairs_positive': sum(v > 0 for v in by_pair),
            'n_pairs': len(by_pair), 'by_pair': by_pair, 'verdict': verdict, 'n_boot': 2000, 'seed': 2026}


class SeedT(unittest.TestCase):
    def test_t_and_df(self):
        r = P.seed_t([1.0, 2.0, 3.0, 4.0])
        s = math.sqrt(sum((x - 2.5) ** 2 for x in (1, 2, 3, 4)) / 3)
        self.assertEqual(r['df'], 3)
        self.assertAlmostEqual(r['s'], s)
        self.assertAlmostEqual(r['t'], 2.5 / (s / 2))

    def test_helper_hits_requested_t(self):
        for t in (2.349, 2.35, -2.351, 10.0):
            self.assertAlmostEqual(P.seed_t(seeds_with_t(t, 0.001 if t > 0 else -0.001))['t'], t, places=9)

    def test_s_zero(self):
        self.assertEqual(P.seed_t([0.002] * 4)['t'], math.inf)
        self.assertEqual(P.seed_t([-0.002] * 4)['t'], -math.inf)
        self.assertEqual(P.seed_t([0.0] * 4)['t'], 0.0)
        self.assertEqual(P.seed_t([0.0] * 4)['s'], 0.0)

    def test_one_seed_and_bad_input(self):
        self.assertIsNone(P.seed_t([0.1])['t'])
        with self.assertRaises(ValueError):
            P.seed_t([])
        with self.assertRaises(ValueError):
            P.seed_t([0.1, float('nan')])


class Caveat(unittest.TestCase):
    def test_edges_around_bound(self):
        for verdict in (D.BEATS, D.LOSES):
            self.assertTrue(P.needs_caveat(verdict, 2.3499, 4))
            self.assertTrue(P.needs_caveat(verdict, -2.3499, 4))
            self.assertFalse(P.needs_caveat(verdict, 2.35, 4))     # strict: |t| = 2.35 passes the bound
            self.assertFalse(P.needs_caveat(verdict, -2.3501, 4))
            self.assertFalse(P.needs_caveat(verdict, math.inf, 4))
            self.assertTrue(P.needs_caveat(verdict, 0.0, 4))

    def test_other_verdicts_and_seed_counts(self):
        for verdict in (D.UNRESOLVED, D.UNDECIDED, None):
            self.assertFalse(P.needs_caveat(verdict, 0.5, 4))
        self.assertFalse(P.needs_caveat(D.LOSES, 0.5, 2))        # the rule is stated for 4 seeds

    def test_sign_disagreement_still_reads_abs(self):
        # 'уступает' with a positive t below the bound: caveat by |t|, the sign is reported as is
        row = P.analyze({'h1': h1(seeds_with_t(1.0, 0.0005), D.LOSES)})['test'][0]
        self.assertGreater(row['t'], 0)
        self.assertEqual(row['caveat'], P.CAVEAT)


class Rees46(unittest.TestCase):
    def doc(self, by_pair, verdict, with_pairs=True):
        names = [f'ctest_{a}_s{i}' for a in ('Hrp', 'ALLP') for i in range(4)] + ['ctest_Hr_s0', 'ctest_Hr_s1']
        mean = {n: 0.15 for n in names}
        for i, v in enumerate(by_pair):
            mean[f'ctest_ALLP_s{i}'] = 0.15 + v
        mean['ctest_Hr_s0'] = mean['ctest_Hr_s1'] = 0.1498
        c = {'d': 0.0002, 'ci95': [-1e-4, 5e-4], 'by_pair': [0.0002, 0.0002]}
        block = {'queries': 100, 'mean': mean, 'h1': h1(by_pair, verdict),
                 'H+r⁺ − H+r': dict(c), 'ALL_P − H+r': {'d': 0.0, 'ci95': [0, 0], 'by_pair': [0.0, 0.0]}}
        if not with_pairs:
            del block['h1']['by_pair']
            for k in ('H+r⁺ − H+r', 'ALL_P − H+r'):
                del block[k]['by_pair']
        return {'primary': block, 'all_16_days': json.loads(json.dumps(block))}

    def test_loses_below_bound_gets_caveat(self):
        res = P.analyze(self.doc(seeds_with_t(-2.3, -0.0004), D.LOSES))
        self.assertEqual(set(res), {'primary', 'all_16_days'})
        row = res['primary'][0]
        self.assertAlmostEqual(row['t'], -2.3, places=9)
        self.assertEqual(row['df'], 3)
        self.assertEqual(row['caveat'], P.CAVEAT)
        self.assertNotIn('mismatch', row)

    def test_beats_above_bound_no_caveat(self):
        row = P.analyze(self.doc(seeds_with_t(2.4, 0.0012), D.BEATS))['primary'][0]
        self.assertIsNone(row['caveat'])

    def test_contrasts_descriptive(self):
        rows = P.analyze(self.doc(seeds_with_t(3.0), D.UNRESOLVED))['primary']
        c = {r['what']: r for r in rows if r['kind'] == 'contrast'}
        self.assertEqual(set(c), {'H+r⁺ − H+r', 'ALL_P − H+r'})
        self.assertEqual(c['H+r⁺ − H+r']['df'], 1)
        self.assertEqual(c['H+r⁺ − H+r']['t'], math.inf)          # s = 0, positive
        self.assertEqual(c['ALL_P − H+r']['t'], 0.0)               # s = 0, zero mean
        self.assertIsNone(c['H+r⁺ − H+r']['verdict'])

    def test_fallback_from_mean(self):
        by = seeds_with_t(-2.0, -0.0004)
        res = P.analyze(self.doc(by, D.LOSES, with_pairs=False))['primary']
        row = res[0]
        self.assertIn('mean[b] − mean[a]', row['source'])
        for got, want in zip(row['by_seed'], by):
            self.assertAlmostEqual(got, want, places=12)
        self.assertAlmostEqual(row['t'], -2.0, places=6)
        self.assertEqual(row['caveat'], P.CAVEAT)
        c = {r['what']: r for r in res if r['kind'] == 'contrast'}
        self.assertAlmostEqual(c['H+r⁺ − H+r']['mean'], 0.0002, places=12)

    def test_missing_fields_reported(self):
        doc = self.doc(seeds_with_t(-2.0), D.LOSES, with_pairs=False)
        del doc['primary']['mean']['ctest_ALLP_s3']
        row = P.analyze(doc)['primary'][0]
        self.assertIn('missing', row)
        self.assertIn('by_pair', row['missing'])
        self.assertIn('ctest_ALLP_s3', row['missing'])
        self.assertIn('нет', P.format_row(row)[0])

    def test_mismatch_flagged(self):
        doc = self.doc(seeds_with_t(3.0), D.BEATS)
        doc['primary']['h1']['delta'] += 1.0
        self.assertIn('mismatch', P.analyze(doc)['primary'][0])


class Xfer(unittest.TestCase):
    def doc(self, by_seed, verdict, mech_class=D.NOT_DISTINGUISHED, drop=False):
        mean = {}
        for s, v in zip(P.XFER_TEST_SEEDS, by_seed):
            mean[f'test-Hrp-{s}'] = 0.2
            mean[f'test-SEL-{s}'] = 0.2 + v
        for s in (7, 11):
            mean[f'test-Hr-{s}'] = 0.199
        d = {'test': 'повторный', 'queries': 50, 'users': 20, 'mean': mean, 'h1': h1(by_seed, verdict),
             'contrasts': {'SEL − H+r': {'d': 0.001 + sum(by_seed[:2]) / 2, 'ci95': [0, 0],
                                         'by_seed': [0.001 + by_seed[0], 0.001 + by_seed[1]],
                                         'a': ['test-Hr-7', 'test-Hr-11'], 'b': ['test-SEL-7', 'test-SEL-11']}},
             'mechanism': {'family': 'F3', 'card': 'G1', 't_select': 2.5, 'diff': 0.001,
                           'repeat': {'delta': 0.0003, 'lower': 0.0001, 'upper': 0.0005,
                                      'by_seed': [0.0002, 0.0004], 'repeated': True}, 'class': mech_class}}
        if drop:
            del d['h1']['by_pair']
            del d['contrasts']['SEL − H+r']['by_seed']
        return d

    def test_rows_and_caveats(self):
        rows = P.analyze(self.doc(seeds_with_t(-1.0, -0.0003), D.LOSES))['test']
        self.assertEqual([r['kind'] for r in rows], ['h1', 'contrast', 'mechanism'])
        self.assertEqual(rows[0]['caveat'], P.CAVEAT)
        self.assertEqual(rows[1]['df'], 1)
        self.assertIsNone(rows[2]['caveat'])

    def test_mechanism_established_gets_repeat_caveat(self):
        rows = P.analyze(self.doc(seeds_with_t(5.0), D.BEATS, mech_class=D.MECHANISM))['test']
        self.assertIsNone(rows[0]['caveat'])
        self.assertEqual(rows[2]['caveat'], P.CAVEAT_REPEAT)

    def test_fallback_by_a_b(self):
        by = seeds_with_t(2.2)
        rows = P.analyze(self.doc(by, D.BEATS, drop=True))['test']
        self.assertAlmostEqual(rows[0]['t'], 2.2, places=6)
        self.assertEqual(rows[0]['caveat'], P.CAVEAT)
        self.assertAlmostEqual(rows[1]['mean'], 0.001 + sum(by[:2]) / 2, places=9)

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            P.analyze({'queries': 1})


class Cli(unittest.TestCase):
    def test_file_report_and_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'test.json'
            p.write_text(json.dumps(Xfer().doc(seeds_with_t(-2.3, -0.0004), D.LOSES), ensure_ascii=False),
                         encoding='utf-8')
            lines = P.report('x', json.loads(p.read_text(encoding='utf-8')))
            self.assertTrue(any('df=3' in x and D.LOSES in x for x in lines))
            self.assertTrue(any(P.CAVEAT in x for x in lines))
            self.assertEqual(P.main(['--file', str(p)]), 0)
            self.assertEqual(P.main(['--file', str(Path(tmp) / 'nope.json')]), 0)

    def test_reads_json_only(self):
        src = Path(P.__file__).read_text(encoding='utf-8')
        for bad in ('parquet', 'duckdb', 'sealed', 'read_csv', 'broker', "'data/", '"data/', 'open('):
            self.assertNotIn(bad, src, f'posthoc_ctest_t.py mentions {bad}')


if __name__ == '__main__':
    unittest.main()
