import itertools
import unittest

import numpy as np
import pandas as pd

from council import design as D


def simulate(beta, n_q=2000, sigma=0.05, seed=0, offset=True):
    """y = mu_q + x beta + e for the 48 rows of the plan; beta: column name -> value."""
    rng = np.random.default_rng(seed)
    b = np.array([beta.get(c, 0.0) for c in D.COLUMNS])
    y = D.matrix() @ b + sigma * rng.standard_normal((n_q, 48))
    if offset:
        y = y + rng.uniform(0.0, 0.5, (n_q, 1))
    return y


def pairs(means, n_q=3000, sigma=0.03, seed=0):
    """ref and new lists of per-query Series, new - ref has the given mean per pair."""
    rng = np.random.default_rng(seed)
    idx = pd.Index(np.arange(n_q) * 7 + 3, name='qid')
    base = pd.Series(rng.uniform(0, 0.4, n_q), index=idx)
    ref, new = [], []
    for m in means:
        r = base + sigma * rng.standard_normal(n_q)
        n = base + m + sigma * rng.standard_normal(n_q)
        ref.append(r)
        new.append(n.sample(frac=1.0, random_state=1))  # order of queries must not matter
    return ref, new


def clustered(n_users, size, rho, n_cols, sigma=0.05, seed=0):
    """Noise n_q x n_cols with a user effect of share rho in every column; users hold `size` consecutive queries."""
    rng = np.random.default_rng(seed)
    users = np.repeat(np.arange(n_users), size)
    e = np.sqrt(1 - rho) * rng.standard_normal((len(users), n_cols))
    e += np.sqrt(rho) * rng.standard_normal((n_users, n_cols))[users]
    return sigma * e, users


class Matrix(unittest.TestCase):
    def test_pb24_orthogonal_and_balanced(self):
        m = D.pb24()
        self.assertEqual(m.shape, (24, 23))
        self.assertTrue(set(np.unique(m)) == {-1, 1})
        np.testing.assert_array_equal(m.T @ m, 24 * np.eye(23))
        np.testing.assert_array_equal(m.sum(axis=0), 0)

    def test_foldover_frees_main_effects_from_two_factor_products(self):
        f = D.foldover(D.pb24())
        self.assertEqual(f.shape, (48, 23))
        np.testing.assert_array_equal(f.T @ f, 48 * np.eye(23))
        np.testing.assert_array_equal(f.sum(axis=0), 0)
        for i, j, k in itertools.product(range(23), repeat=3):
            if j < k:
                self.assertEqual(int((f[:, i] * f[:, j] * f[:, k]).sum()), 0, (i, j, k))
        np.testing.assert_array_equal(D.matrix(), f / 2)

    def test_layout(self):
        names, empty = D.layout(12)
        self.assertEqual(len(names), 23)
        self.assertEqual(len(set(names)), 23)
        self.assertEqual(names[:12], D.FAMILIES)
        self.assertEqual(names[16], 'PL')
        self.assertEqual(empty, D.EMPTIES)
        _, empty = D.layout(9)
        self.assertEqual(empty, ['F10', 'F11', 'F12'] + D.EMPTIES)
        _, empty = D.layout(9, n_twins=3)
        self.assertEqual(empty, ['F10', 'F11', 'F12', 'T4'] + D.EMPTIES)
        with self.assertRaises(ValueError):
            D.layout(13)


class Estimation(unittest.TestCase):
    planted = {'F1': 0.004, 'F2': -0.003, 'PL': -0.002, 'T1': 0.001}

    def test_recovers_planted_beta(self):
        n_q, sigma = 3000, 0.05
        est = D.estimate(simulate(self.planted, n_q, sigma), groups=None, n_boot=500)
        truth = pd.Series({c: self.planted.get(c, 0.0) for c in D.COLUMNS})
        self.assertTrue(((est.beta - truth).abs() < 4 * est.se_boot).all())
        self.assertGreater(est.t['F1'], 3)
        self.assertLess(est.t['F2'], -3)
        self.assertLess(est.t['PL'], -2)
        analytic = sigma / np.sqrt(12 * n_q)
        np.testing.assert_allclose(est.se_boot.to_numpy(), analytic, rtol=0.15)
        np.testing.assert_allclose(est.se.to_numpy(), np.sqrt(est.se_boot ** 2 + est.se_empty ** 2))
        self.assertAlmostEqual(est.se_empty, float(np.std(est.beta[D.EMPTIES], ddof=1)))
        self.assertEqual(est.cov.shape, (23, 23))

    def test_query_offset_drops_out(self):
        a = D.estimate(simulate(self.planted, 500, seed=3, offset=True), groups=None, n_boot=50)
        b = D.estimate(simulate(self.planted, 500, seed=3, offset=False), groups=None, n_boot=50)
        np.testing.assert_allclose(a.beta, b.beta, atol=1e-12)
        np.testing.assert_allclose(a.se_boot, b.se_boot, atol=1e-12)

    def test_groups_of_one_equal_query_bootstrap(self):
        y = simulate(self.planted, 400, seed=5)
        a = D.estimate(y, groups=None, n_boot=100)
        b = D.estimate(y, groups=np.arange(400) + 10, n_boot=100)
        np.testing.assert_allclose(a.draws, b.draws)
        c = D.estimate(y, groups=np.arange(400) // 2, n_boot=100)
        self.assertFalse(np.allclose(a.draws, c.draws))

    def test_deterministic_by_seed(self):
        y = simulate(self.planted, 400, seed=6)
        a, b = D.estimate(y, groups=None, n_boot=200), D.estimate(y, groups=None, n_boot=200)
        np.testing.assert_array_equal(a.draws, b.draws)
        self.assertEqual(D.wy_maxT(a)['harm'].tolist(), D.wy_maxT(b)['harm'].tolist())
        c = D.estimate(y, groups=None, n_boot=200, seed=7)
        self.assertFalse(np.array_equal(a.draws, c.draws))

    def test_groups_are_required(self):
        y = simulate({}, 100)
        with self.assertRaises(TypeError):
            D.estimate(y, n_boot=10)
        ref, new = pairs([0.0] * 2, n_q=100)
        with self.assertRaises(TypeError):
            D.h1(ref, new)
        with self.assertRaises(TypeError):
            D.confirm(ref, new)
        with self.assertRaises(ValueError):
            D.estimate(y, groups=np.arange(99), n_boot=10)

    def test_users_of(self):
        users = D.users_of(['2020-02-03:17', '2020-02-04 00:00:00:17', '2020-02-03:5'])
        self.assertEqual(list(users), ['17', '17', '5'])
        with self.assertRaises(ValueError):
            D.users_of(['17'])

    def test_user_bootstrap_widens_se_and_aligns_by_qid(self):
        size, rho = 4, 0.5
        e, users = clustered(1000, size, rho, 48, seed=9)
        qids = [f'2020-02-0{3 + i % 5}:{u}' for i, u in enumerate(users)]
        y = pd.DataFrame(e, index=qids)
        flat = D.estimate(y, groups=None, n_boot=600)
        by_user = D.estimate(y, groups=D.users_of(y.index), n_boot=600)
        ratio = float((by_user.se_boot / flat.se_boot).mean())
        self.assertAlmostEqual(ratio, np.sqrt(1 + (size - 1) * rho), delta=0.15)
        shuffled = pd.Series(D.users_of(y.index), index=y.index).sample(frac=1.0, random_state=0)
        np.testing.assert_allclose(D.estimate(y, groups=shuffled, n_boot=600).draws, by_user.draws)
        self.assertAlmostEqual(D.design_effect(y[0] - y[1], users), 1 + (size - 1) * rho, delta=0.35)
        self.assertAlmostEqual(D.design_effect(y[0] - y[1], None), 1.0)

    def test_rejects_ragged_input(self):
        y = simulate({}, 100)
        y[3, 5] = np.nan
        with self.assertRaises(ValueError):
            D.estimate(y, groups=None, n_boot=10)
        with self.assertRaises(ValueError):
            D.estimate(np.zeros((10, 47)), groups=None, n_boot=10)


class Calibration(unittest.TestCase):
    def test_empties_calibrate_on_null_and_fail_on_planted_empty(self):
        n_q, sigma = 2000, 0.05
        interval = D.rehearse(n_q, sigma)['sd_t_interval']
        est = D.estimate(simulate({}, n_q, sigma, seed=11), groups=None, n_boot=1000)
        wy = D.wy_maxT(est)
        cal = D.calibrate(est.t[est.empty], interval, wy['empty_max'])
        self.assertTrue(cal['passed'], cal)
        bad = D.estimate(simulate({'E1': 0.004, 'E4': -0.004}, n_q, sigma, seed=11), groups=None, n_boot=1000)
        cal = D.calibrate(bad.t[bad.empty], interval, D.wy_maxT(bad)['empty_max'])
        self.assertFalse(cal['passed'], cal)

    def test_wy_controls_false_nominations_on_null(self):
        r = D.rehearse(200, 0.05, n_sim=300, beta_harm=-0.004, exact=True, n_boot=200, seed=1)
        self.assertLess(r['false_rate'], 0.1)
        self.assertLess(r['calib_fail_rate'], 0.15)

    def test_wy_null_has_unit_scale(self):
        est = D.estimate(simulate({'F1': 0.01, 'F2': -0.01}, 1500, seed=2), groups=None, n_boot=2000)
        wy = D.wy_maxT(est)
        # a family far beyond the null is significant; with eta the empty p are conservative, not tiny
        self.assertLess(wy['harm']['F2'], 0.01)
        self.assertGreater(wy['harm']['F1'], 0.5)
        self.assertGreaterEqual(wy['empty_max'], 0.05)

    def test_wy_noise_stream_is_separate_from_bootstrap(self):
        est = D.estimate(simulate({'F2': -0.004}, 800, seed=12), groups=None, n_boot=300)
        wy = D.wy_maxT(est)
        eta = np.random.default_rng(np.random.SeedSequence(D.SEED).spawn(1)[0]).standard_normal(est.draws.shape)
        tstar = (est.draws - est.beta.to_numpy() + eta * est.se_empty) / est.se.to_numpy()
        harm = D.present_families(est) + ['PL']
        null_h = pd.DataFrame(tstar, columns=est.beta.index)[harm].min(axis=1).to_numpy()
        self.assertAlmostEqual(wy['harm']['F2'], (1 + (null_h <= est.t['F2']).sum()) / (1 + len(null_h)))
        same = np.random.default_rng(D.SEED).standard_normal(5)
        self.assertFalse(np.allclose(eta.ravel()[:5], same))

    def test_clustered_rehearsal(self):
        kw = dict(n_q=400, sigma_q=0.05, beta_harm=-0.004, seed=5)
        fast = D.rehearse(n_sim=4000, deff=2.5, **kw)
        slow = D.rehearse(n_sim=300, exact=True, n_boot=300, deff=2.5, cluster_size=4, **kw)
        self.assertGreater(fast['power'], 0.2)
        self.assertLess(fast['power'], 0.9)
        self.assertAlmostEqual(fast['power'], slow['power'], delta=0.12)
        self.assertAlmostEqual(fast['sd_t_median'], slow['sd_t_median'], delta=0.05)
        flat = D.rehearse(n_sim=4000, **kw)
        self.assertGreater(flat['power'], fast['power'])
        self.assertEqual(D.rehearse(n_sim=500, cluster_size=4, rho=0.5, **kw)['power'],
                         D.rehearse(n_sim=500, deff=2.5, **kw)['power'])
        with self.assertRaises(ValueError):
            D.rehearse(n_sim=5, exact=True, deff=2.0, **kw)

    def test_analytic_rehearsal_matches_pipeline(self):
        kw = dict(n_q=300, sigma_q=0.05, beta_harm=-0.0025, seed=4)
        fast = D.rehearse(n_sim=4000, **kw)
        slow = D.rehearse(n_sim=300, exact=True, n_boot=300, **kw)
        self.assertGreater(fast['power'], 0.2)
        self.assertLess(fast['power'], 0.9)
        self.assertAlmostEqual(fast['power'], slow['power'], delta=0.12)
        self.assertAlmostEqual(fast['sd_t_median'], slow['sd_t_median'], delta=0.05)

    def test_power_grows_with_less_noise(self):
        powers = [D.rehearse(15700, s, n_sim=2000)['power'] for s in (0.3, 0.1, 0.03, 0.01)]
        self.assertEqual(powers, sorted(powers))
        self.assertGreater(powers[-1], 0.95)
        self.assertLess(powers[0], 0.1)
        self.assertEqual(D.rehearse(15700, 0.1), D.rehearse(15700, 0.1))

    def test_fit_level_noise_moves_sd_t(self):
        base = D.rehearse(2000, 0.05)
        shifted = D.rehearse(2000, 0.05, sigma_fit=0.005)
        self.assertGreater(shifted['sd_t_median'], base['sd_t_interval'][1])


class Selection(unittest.TestCase):
    def test_nominate(self):
        t = pd.Series({'F1': -3.0, 'F2': -2.5, 'F3': -1.0, 'PL': -4.0})
        p = pd.Series({'F1': 0.02, 'F2': 0.2, 'F3': 0.01, 'PL': 0.001})
        self.assertEqual(D.nominate(t, p, ['F1', 'F2', 'F3', 'PL']), ['F1'])

    def test_confirm(self):
        ref, new = pairs([0.003, 0.003], seed=1)
        out = D.confirm(ref, new, groups=None, n_boot=500)
        self.assertTrue(out['confirmed'], out)
        self.assertGreater(out['t'], 1.64)
        ref, new = pairs([0.0, 0.0], seed=2)
        self.assertFalse(D.confirm(ref, new, groups=None, n_boot=500)['confirmed'])

    def test_mechanism(self):
        beta = {'F1': 0.004, 'T1': 0.0, 'F2': 0.004, 'T2': 0.004, 'F3': 0.0, 'T3': 0.0, 'F4': 0.006, 'T4': 0.0}
        est = D.estimate(simulate(beta, 3000, 0.05, seed=8), groups=None, n_boot=1000)
        twins = {'T1': 'F1', 'T2': 'F2', 'T3': 'F3', 'T4': 'F4'}
        m = D.mechanism(est, twins)
        cls = m['table']['class']
        self.assertEqual(cls['F1'], D.WAITING)
        self.assertEqual(cls['F2'], D.FORM)
        self.assertEqual(cls['F3'], D.NOT_DISTINGUISHED)
        self.assertEqual(m['arm'], 'F4')
        self.assertEqual(D.mechanism(est, twins, exclude=['F4'])['arm'], 'F1')
        done = D.mechanism(est, twins, c_val={'F4': 0.0007})['table']['class']
        self.assertEqual(done['F4'], D.MECHANISM)
        self.assertEqual(done['F1'], D.NOT_DISTINGUISHED)
        done = D.mechanism(est, twins, c_val={'F4': -0.0002})['table']['class']
        self.assertEqual(done['F4'], D.NOT_DISTINGUISHED)
        row = m['table'].loc['F1']
        cov = est.cov
        var = cov.loc['F1', 'F1'] + cov.loc['T1', 'T1'] - 2 * cov.loc['F1', 'T1'] + 2 * est.se_empty ** 2
        self.assertAlmostEqual(row['t'], (est.beta['F1'] - est.beta['T1']) / np.sqrt(var))


class H1(unittest.TestCase):
    def test_verdicts(self):
        cases = [([0.004, 0.003, 0.005, 0.004], D.BEATS),
                 ([-0.003, -0.004, -0.003, -0.002], D.LOSES),
                 ([0.0, 0.0, 0.0, 0.0], D.UNRESOLVED),
                 ([0.0006, 0.0005, 0.0006, 0.0005], D.UNDECIDED)]
        for means, verdict in cases:
            ref, new = pairs(means, n_q=4000, sigma=0.01, seed=3)
            out = D.h1(ref, new, groups=None)
            self.assertEqual(out['verdict'], verdict, (means, out))
            self.assertEqual(out['n_pairs'], 4)
        self.assertEqual({D.BEATS, D.UNRESOLVED, D.LOSES, D.UNDECIDED},
                         {'обыгрывает H+', 'не различено', 'уступает', 'не решено'})

    def test_counts_and_bounds(self):
        ref, new = pairs([0.004, 0.003, -0.001, 0.004], n_q=2000, seed=4)
        out = D.h1(ref, new, n_boot=500, groups=None)
        self.assertEqual(out['pairs_positive'], 3)
        self.assertLess(out['lower'], out['delta'])
        self.assertGreater(out['upper'], out['delta'])
        self.assertAlmostEqual(out['delta'], float(np.mean(out['by_pair'])))

    def test_user_clusters_widen_h1_interval(self):
        e, users = clustered(1000, 5, 0.6, 8, sigma=0.03, seed=7)
        idx = pd.Index([f'2020-02-14:{u}x{i}' for i, u in enumerate(users)])
        ref = [pd.Series(e[:, k], index=idx) for k in range(4)]
        new = [pd.Series(e[:, 4 + k] + 0.0005, index=idx) for k in range(4)]
        flat = D.h1(ref, new, groups=None, n_boot=800)
        by_user = D.h1(ref, new, groups=pd.Series(users, index=idx), n_boot=800)
        self.assertGreater(by_user['upper'] - by_user['lower'], 1.3 * (flat['upper'] - flat['lower']))

    def test_deterministic_and_checks_queries(self):
        ref, new = pairs([0.001] * 4, n_q=1000, seed=5)
        self.assertEqual(D.h1(ref, new, n_boot=300, groups=None), D.h1(ref, new, n_boot=300, groups=None))
        self.assertNotEqual(D.h1(ref, new, n_boot=300, groups=None)['lower'],
                            D.h1(ref, new, n_boot=300, seed=1, groups=None)['lower'])
        with self.assertRaises(ValueError):
            D.h1(ref, [s.iloc[:-1] for s in new], groups=None)
        with self.assertRaises(ValueError):
            D.h1(ref[:3], new, groups=None)


if __name__ == '__main__':
    unittest.main()
