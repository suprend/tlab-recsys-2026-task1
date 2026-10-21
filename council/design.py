"""Statistics of the council plan (contract `council/runs/rees46-2020/contract.md` §3.3, project §6, §7, §9).

Pure numpy/pandas. The module reads no files: it takes per-query metric arrays y[query x fit] (or per-pair Series)
and the design matrix, and returns estimates, p-values and verdicts.

Plan: Plackett-Burman N=24 folded over to 48 rows, 23 columns in the order F1-F12 (council families), T1-T4 (twins),
PL (placebo family), E1-E6 (empty columns); x in {-1/2, +1/2}, so a slope is the mean difference "with - without".
Row r (0-based) of `matrix()` is fit r + 1 of the plan (seed 1000 + r + 1 in prereg-2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

SEED = 2026
N_BOOT = 2000
PB24_GENERATOR = '+++++-+-++--++--+-+----'  # Plackett & Burman (1946), N = 24

FAMILIES = [f'F{i}' for i in range(1, 13)]
TWINS = [f'T{i}' for i in range(1, 5)]
PLACEBO = 'PL'
EMPTIES = [f'E{i}' for i in range(1, 7)]
COLUMNS = FAMILIES + TWINS + [PLACEBO] + EMPTIES

T_NOMINATE = -2.0      # D = {g: t_g < -2 and WY p (harm) < 0.1}
P_NOMINATE = 0.1
P_CALIBRATE = 0.05     # WY max-T p over the empty columns must be >= 0.05
T_CONFIRM = 1.64       # one-sided t of ALL_P \ D - ALL_P
T_MECHANISM = 2.0
POWER_GATE = 0.8
BETA_HARM = -0.0005
DELTA_MIN = 0.001
PAIRS_MIN = 3

BEATS, UNRESOLVED, LOSES, UNDECIDED = 'обыгрывает H+', 'не различено', 'уступает', 'не решено'
MECHANISM, FORM, NOT_DISTINGUISHED = 'механизм установлен', 'форма без механизма', 'не различено'
WAITING = 'ждёт C_val'  # not a class: t(beta_g - beta_twin) > 2 before the one C_val read


# --- the matrix -------------------------------------------------------------------------------------------------

def pb24() -> np.ndarray:
    """24 x 23 Plackett-Burman matrix of +-1: 23 cyclic shifts of the generator and a row of minuses."""
    g = np.array([1 if c == '+' else -1 for c in PB24_GENERATOR])
    return np.vstack([np.roll(g, i) for i in range(len(g))] + [-np.ones(len(g), dtype=int)])


def foldover(m: np.ndarray) -> np.ndarray:
    """The matrix stacked over its mirror (48 x 23 for PB24): main effects become free of two-factor interactions."""
    return np.vstack([m, -m])


def matrix() -> np.ndarray:
    """The 48 x 23 plan in +-1/2, columns in the order of `COLUMNS`."""
    return foldover(pb24()) / 2.0


def layout(n_families: int = 12, n_twins: int = 4) -> tuple[list[str], list[str]]:
    """Column names and the empty columns. F-columns past `n_families` and T-columns past `n_twins` are empty
    (their tables are not joined in any fit); E1-E6 are always empty. Returns (names, empty) in column order."""
    if not 0 <= n_families <= len(FAMILIES) or not 0 <= n_twins <= len(TWINS):
        raise ValueError(f'n_families must be in 0..12 and n_twins in 0..4, got {n_families}, {n_twins}')
    unused = set(FAMILIES[n_families:]) | set(TWINS[n_twins:]) | set(EMPTIES)
    return list(COLUMNS), [c for c in COLUMNS if c in unused]


def _slopes(x: np.ndarray) -> np.ndarray:
    """Rows of the OLS projection (with an intercept) that give the slopes: beta = P @ ybar, P is k x n_rows."""
    z = np.column_stack([np.ones(len(x)), x])
    return np.linalg.pinv(z)[1:]


# --- estimation -------------------------------------------------------------------------------------------------

@dataclass
class Estimate:
    beta: pd.Series        # OLS slopes on the per-fit means over queries
    se_boot: pd.Series     # SD of the slopes over the bootstrap replicas
    se_empty: float        # SD (ddof=1) of the slopes of the empty columns
    se: pd.Series          # sqrt(se_boot^2 + se_empty^2)
    t: pd.Series
    cov: pd.DataFrame      # bootstrap covariance of the slopes
    draws: np.ndarray      # n_boot x k bootstrap slopes, column order of `beta`
    empty: list[str]
    n_q: int
    seed: int


def _index(cols, names):
    return [names.index(c) if isinstance(c, str) else int(c) for c in cols]


def users_of(qids) -> np.ndarray:
    """user_id of each query id 'anchor:user_id' (the part after the last ':'; anchors may contain ':')."""
    qids = pd.Index(qids).astype(str)
    if not qids.str.contains(':').all():
        raise ValueError("query ids must look like 'anchor:user_id'")
    return np.asarray(qids.str.rsplit(':', n=1).str[1])


def _codes(groups, index, n: int) -> np.ndarray:
    """Cluster codes 0..G-1 of n queries. groups: None (every query is its own cluster - a deliberate choice, the
    contract resamples users), a Series indexed by query id (aligned to `index`) or an array in query order."""
    if groups is None:
        return np.arange(n)
    if isinstance(groups, pd.Series) and index is not None:
        groups = groups.reindex(index)
    groups = np.asarray(groups)
    if len(groups) != n:
        raise ValueError(f'groups has {len(groups)} values for {n} queries')
    codes, _ = pd.factorize(groups)
    if (codes < 0).any():
        raise ValueError('groups contain missing values')
    return codes


def _cluster_sums(v: np.ndarray, codes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-cluster sums of v (n x k) and cluster sizes."""
    g = int(codes.max()) + 1
    sums = np.zeros((g, v.shape[1]))
    np.add.at(sums, codes, v)
    return sums, np.bincount(codes, minlength=g).astype(float)


def _cluster_counts(rng, g: int, c: int) -> np.ndarray:
    """c x g multiplicities of g clusters drawn with replacement, c replicas."""
    idx = rng.integers(0, g, (c, g)) + (np.arange(c) * g)[:, None]
    return np.bincount(idx.ravel(), minlength=c * g).reshape(c, g).astype(float)


def _boot_slopes(b: np.ndarray, codes: np.ndarray, n_boot: int, seed: int, chunk: int = 100) -> np.ndarray:
    """Bootstrap of the mean of per-query slope contributions b (n_q x k) by clusters (users): all queries of a
    drawn user enter together, and the same users enter all 48 rows because b already combines the rows."""
    sums, sizes = _cluster_sums(b, codes)
    rng = np.random.default_rng(seed)
    out = np.empty((n_boot, b.shape[1]))
    for start in range(0, n_boot, chunk):
        c = min(chunk, n_boot - start)
        counts = _cluster_counts(rng, len(sizes), c)
        out[start:start + c] = (counts @ sums) / (counts @ sizes)[:, None]
    return out


def design_effect(d, groups) -> float:
    """Design effect of clustering for a per-query difference d (e.g. y1 - y2 of the two noise fits of §4.0):
    the cluster-robust variance of mean(d) over its iid variance, sum_g (S_g - n_g dbar)^2 / sum_q (d_q - dbar)^2.
    The input of `rehearse(deff=...)`."""
    index = d.index if isinstance(d, pd.Series) else None
    d = np.asarray(d, dtype=float)
    sums, sizes = _cluster_sums(d[:, None] - d.mean(), _codes(groups, index, len(d)))
    return float((sums[:, 0] ** 2).sum() / ((d - d.mean()) ** 2).sum())


def estimate(y, x=None, empty=None, *, groups, n_boot: int = N_BOOT, seed: int = SEED, names=None) -> Estimate:
    """beta, SE and t of the plan.

    y: n_q x 48 per-query metric of the 48 fits (rows of `x` in the same order); ndarray or DataFrame.
    x: 48 x k in +-1/2 (default `matrix()`); empty: names or indices of the empty columns (default E1-E6).
    groups (required, keyword): user id per query - a Series by query id or an array in query order
    (`users_of(qids)`); groups=None, every query its own cluster, only as a deliberate choice (synthetic tests).

    beta = OLS (with intercept) on the column means of y. SE_boot: one bootstrap of users shared by all 48 rows,
    OLS on every replica - computed as the bootstrap mean of the per-query contributions P @ y_q, which is the same
    OLS because it is linear in the means. SE_empty = SD of the empty slopes; SE = sqrt(SE_boot^2 + SE_empty^2);
    t = beta / SE. A per-query offset mu_q drops out with the intercept.
    """
    index = y.index if isinstance(y, pd.DataFrame) else None
    y = np.asarray(y, dtype=float)
    x = matrix() if x is None else np.asarray(x, dtype=float)
    if y.ndim != 2 or y.shape[1] != x.shape[0]:
        raise ValueError(f'y must be n_q x {x.shape[0]}, got {y.shape}')
    if not np.isfinite(y).all():
        raise ValueError('y has non-finite values: all fits must cover the same queries')
    names = list(names) if names is not None else (list(COLUMNS) if x.shape[1] == len(COLUMNS)
                                                   else [f'x{j}' for j in range(x.shape[1])])
    empty = [names[j] for j in _index(EMPTIES if empty is None else empty, names)]
    if len(empty) < 2:
        raise ValueError('SE_empty needs at least two empty columns')
    p = _slopes(x)
    b = y @ p.T
    beta = b.mean(axis=0)
    draws = _boot_slopes(b, _codes(groups, index, len(y)), n_boot, seed)
    se_boot = draws.std(axis=0, ddof=1)
    se_empty = float(np.std(beta[_index(empty, names)], ddof=1))
    se = np.sqrt(se_boot ** 2 + se_empty ** 2)
    s = lambda v: pd.Series(v, index=names)
    return Estimate(beta=s(beta), se_boot=s(se_boot), se_empty=se_empty, se=s(se), t=s(beta / se),
                    cov=pd.DataFrame(np.cov(draws, rowvar=False), index=names, columns=names), draws=draws,
                    empty=empty, n_q=len(y), seed=seed)


def present_families(est: Estimate) -> list[str]:
    return [c for c in FAMILIES if c in est.beta.index and c not in est.empty]


def wy_maxT(est: Estimate, harm=None, seed: int = SEED) -> dict:
    """Westfall-Young single-step max-T p-values.

    Null draws: t*_b = (beta*_b - beta_hat + eta_b) / SE, where beta*_b are the bootstrap replicas of `estimate`
    (centred on beta_hat, so true effects of the other columns do not enter the null) and eta_b ~ N(0, SE_empty^2)
    independently per column. The bootstrap of queries carries the query noise and its correlation between columns,
    but not the fit-to-fit (seed) noise that SE_empty adds to SE; without eta the null t* would be narrower than the
    SE it is divided by, and the p-values anti-conservative. The seed noise of the slopes is independent between
    columns because the folded PB24 is orthogonal and every fit has its own seed. Rows are not permuted: real
    family effects would then enter the null, and sign flips do not exist for a single design.

    Returns {'empty': two-sided adjusted p of each empty column over max|t*| of the empties, 'empty_max': the p of
    the largest |t| (the calibration value), 'harm': one-sided adjusted p over min t* of the `harm` columns
    (default: present families and PL, the placebo is a positive control of the screen)}. p = (1 + #) / (1 + B).
    eta comes from a child of SeedSequence(seed), a stream separate from the bootstrap of `estimate` (which uses
    default_rng(seed) itself) even when both take seed 2026.
    """
    harm = present_families(est) + [PLACEBO] if harm is None else list(harm)
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])
    eta = rng.standard_normal(est.draws.shape) * est.se_empty
    tstar = pd.DataFrame((est.draws - est.beta.to_numpy() + eta) / est.se.to_numpy(), columns=est.beta.index)
    nb = len(tstar)
    null_e = tstar[est.empty].abs().max(axis=1).to_numpy()
    null_h = tstar[harm].min(axis=1).to_numpy()
    p_empty = pd.Series({c: (1 + (null_e >= abs(est.t[c])).sum()) / (1 + nb) for c in est.empty})
    p_harm = pd.Series({c: (1 + (null_h <= est.t[c]).sum()) / (1 + nb) for c in harm})
    return {'empty': p_empty, 'empty_max': float(p_empty.min()), 'harm': p_harm}


def sd_t(t_empty) -> float:
    """SD (ddof=1) of the t-values of the empty columns: the same statistic in the data and in the rehearsal."""
    return float(np.std(np.asarray(t_empty, dtype=float), ddof=1))


def calibrate(t_empty, interval, p_wy_empty: float) -> dict:
    """Calibration passes if the SD of the empty t lies inside the 2.5-97.5% interval of the null rehearsal and the
    WY max-T p over the empties is >= 0.05. Otherwise SEL = ALL_P."""
    sd = sd_t(t_empty)
    lo, hi = interval
    return {'passed': bool(lo <= sd <= hi and p_wy_empty >= P_CALIBRATE), 'sd_t': sd,
            'interval': (float(lo), float(hi)), 'p_wy_empty': float(p_wy_empty)}


def nominate(t, p_wy_harm, families) -> list[str]:
    """D = {g in families: t_g < -2 and WY p (harm) < 0.1}, in the order of `families` (PL is never in D)."""
    return [g for g in families if g != PLACEBO and t[g] < T_NOMINATE and p_wy_harm[g] < P_NOMINATE]


# --- rehearsal --------------------------------------------------------------------------------------------------

_erfc = np.vectorize(math.erfc, otypes=[float])


def _phi(z):
    return 0.5 * _erfc(-np.asarray(z, dtype=float) / math.sqrt(2.0))


def _summary(t, p_harm, p_empty_max, names, empty, harm, families, target):
    """Per-simulation nomination, SD of the empty t and the calibration value."""
    col = {c: j for j, c in enumerate(names)}
    tf = t[:, [col[c] for c in harm]]
    nom = (tf < T_NOMINATE) & (p_harm < P_NOMINATE)
    fam = [harm.index(c) for c in families]
    sd = np.std(t[:, [col[c] for c in empty]], axis=1, ddof=1)
    hit = nom[:, harm.index(target)] if target is not None else None
    return {'any_family': nom[:, fam].any(axis=1), 'sd_t': sd, 'p_empty_max': p_empty_max, 'target': hit}


def _simulate_analytic(rng, n_sim, n_q, sigma, beta_true, x, names, empty, harm, sigma_fit=0.0, deff=1.0):
    """Closed form of the plan statistics under y_rq = mu_q + sum beta x + e_rq, e ~ N(0, sigma_q^2).

    The fit means are ybar_r = x beta + N(0, s^2 + sigma_fit^2), s^2 = sum sigma_q^2 / n_q^2 (mu_q drops with the
    intercept; sigma_fit is an optional fit-level shift that the query bootstrap does not see, 0 in the contract). The
    bootstrap SE of slope g tends to s * ||P_g|| (the sample variance of P e_q over n_q queries; its relative error
    ~ sqrt(2 / n_q) and the Monte Carlo error of 2000 replicas ~1.6% are small next to the 5 d.f. of SE_empty), so
    it is used without resampling. The WY null t* then has unit variance and, the plan being orthogonal with equal
    ||P_g||, independent columns: p_harm = 1 - (1 - Phi(t))^k, p_empty = 1 - (2 Phi(max|t_E|) - 1)^m, the limits of
    `wy_maxT` with infinitely many draws.

    Clustering by users multiplies s^2 by the design effect: the noise of the fit means and the user bootstrap SE
    grow together, so the shape of t under the null (and the SD-of-t interval) is unchanged and only power drops."""
    p = _slopes(x)
    norms = np.sqrt((p ** 2).sum(axis=1))
    s = math.sqrt(float(np.sum(sigma ** 2)) * deff) / n_q
    ybar = x @ beta_true + math.sqrt(s ** 2 + sigma_fit ** 2) * rng.standard_normal((n_sim, len(x)))
    beta = ybar @ p.T
    col = {c: j for j, c in enumerate(names)}
    ie, ih = [col[c] for c in empty], [col[c] for c in harm]
    se_empty = np.std(beta[:, ie], axis=1, ddof=1)
    t = beta / np.sqrt((s * norms) ** 2 + se_empty[:, None] ** 2)
    p_harm = 1.0 - (1.0 - _phi(t[:, ih])) ** len(ih)
    p_empty = 1.0 - (2.0 * _phi(np.abs(t[:, ie]).max(axis=1)) - 1.0) ** len(ie)
    return t, p_harm, p_empty


def _simulate_exact(rng, n_sim, n_q, sigma, beta_true, x, names, empty, harm, n_boot, sigma_fit=0.0, size=1,
                    rho=0.0):
    """The real pipeline (`estimate` with a user bootstrap, `wy_maxT`) on simulated y; for validation on small n_q.
    Users hold `size` consecutive queries; a user effect u_{user,r} with share rho of the variance makes the noise of
    one fit correlated within a user (design effect 1 + (size - 1) rho)."""
    t, ph, pe = [], [], []
    mean = x @ beta_true
    users = np.arange(n_q) // size
    for _ in range(n_sim):
        e = math.sqrt(1 - rho) * rng.standard_normal((n_q, len(x)))
        if rho:
            e += math.sqrt(rho) * rng.standard_normal((users[-1] + 1, len(x)))[users]
        y = mean + sigma[:, None] * e + sigma_fit * rng.standard_normal(len(x))
        seed = int(rng.integers(2 ** 31))
        est = estimate(y, x, empty, groups=users, n_boot=n_boot, seed=seed, names=names)
        wy = wy_maxT(est, harm=harm, seed=seed)
        t.append(est.t.to_numpy())
        ph.append(wy['harm'][harm].to_numpy())
        pe.append(wy['empty_max'])
    return np.array(t), np.array(ph), np.array(pe)


def rehearse(n_q: int, sigma_q, n_sim: int = 2000, beta_harm: float = BETA_HARM, n_families: int = 12,
             n_twins: int = 4, seed: int = SEED, exact: bool = False, n_boot: int = 200,
             sigma_fit: float = 0.0, deff: float | None = None, cluster_size: float = 1.0, rho: float = 0.0) -> dict:
    """Null rehearsal of the contract (§3.3, §4.0): y_rq = mu_q + sum_g beta_g x_rg + e_rq, e_rq ~ N(0, sigma_q^2),
    sigma_q a scalar (SD(y1 - y2)/sqrt 2 of the two noise fits) or one value per query; mu_q is omitted, it drops
    out with the intercept. `sigma_fit` (default 0, as in the contract) adds a common shift N(0, sigma_fit^2) per
    fit: noise of a whole fit that the query bootstrap misses. Without it SE_empty ~ SE_boot and the SD of the
    empty t centres near 0.68; real fit-level noise pushes it towards 1 and outside the interval.

    Clustering (the contract bootstraps users): `deff` is the design effect of user clusters, measured on the two
    noise fits as `design_effect(y1 - y2, users)`; if None it is 1 + (cluster_size - 1) * rho (mean queries per
    user, intra-user correlation of a fit's noise). The closed form multiplies the noise variance by deff, which is
    what the user bootstrap sees (n_q / deff effective queries). `exact=True` simulates users of round(cluster_size)
    queries with a user effect of share rho (from deff when given) and passes them to `estimate` as groups.

    Two sets of `n_sim` simulations: null (all beta = 0) and harm (F1 at `beta_harm`, the rest 0). Returns
      power        share of harm simulations where F1 is nominated (t < -2 and WY p < 0.1);
      sd_t_interval 2.5-97.5% of the SD of the empty t over the null simulations (the calibration interval);
      false_rate   share of null simulations where any family is nominated;
      calib_fail_rate share of null simulations failing `calibrate` with that interval.
    `exact=False` uses the closed form of `_simulate_analytic` (milliseconds at any n_q); `exact=True` runs the
    real `estimate` + `wy_maxT` with `n_boot` replicas per simulation (for small checks of the closed form).
    """
    x = matrix()
    names, empty = layout(n_families, n_twins)
    families = [c for c in FAMILIES if c not in empty]
    if not families:
        raise ValueError('the rehearsal needs at least one family')
    harm = families + [PLACEBO]
    sigma = np.broadcast_to(np.asarray(sigma_q, dtype=float), (n_q,)).copy()
    size = max(1, int(round(cluster_size)))
    if deff is None:
        deff = 1.0 + (cluster_size - 1.0) * rho
    elif exact:
        if size == 1 and deff != 1.0:
            raise ValueError('exact rehearsal with deff != 1 needs cluster_size > 1')
        rho = (deff - 1.0) / (size - 1) if size > 1 else 0.0
    if exact and not 0.0 <= rho <= 1.0:
        raise ValueError(f'rho must be in [0, 1], got {rho}')
    null_rng, harm_rng = (np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(2))
    beta0 = np.zeros(len(names))
    beta1 = beta0.copy()
    beta1[names.index(families[0])] = beta_harm

    def run(rng, beta_true):
        if exact:
            return _simulate_exact(rng, n_sim, n_q, sigma, beta_true, x, names, empty, harm, n_boot, sigma_fit,
                                   size, rho)
        return _simulate_analytic(rng, n_sim, n_q, sigma, beta_true, x, names, empty, harm, sigma_fit, deff)

    null = _summary(*run(null_rng, beta0), names, empty, harm, families, None)
    hurt = _summary(*run(harm_rng, beta1), names, empty, harm, families, families[0])
    lo, hi = np.percentile(null['sd_t'], [2.5, 97.5])
    fail = ~((null['sd_t'] >= lo) & (null['sd_t'] <= hi) & (null['p_empty_max'] >= P_CALIBRATE))
    return {'power': float(hurt['target'].mean()), 'sd_t_interval': (float(lo), float(hi)),
            'sd_t_median': float(np.median(null['sd_t'])), 'false_rate': float(null['any_family'].mean()),
            'calib_fail_rate': float(fail.mean()), 'gate': bool(hurt['target'].mean() >= POWER_GATE),
            'n_q': n_q, 'n_sim': n_sim, 'beta_harm': beta_harm, 'exact': exact, 'seed': seed, 'sigma_fit': sigma_fit,
            'deff': float(deff),
            'se_boot': math.sqrt(float(np.sum(sigma ** 2)) * deff) / n_q * float(np.sqrt((_slopes(x) ** 2).sum(1)).mean())}


# --- confirmation, mechanism and H1 -------------------------------------------------------------------------------

def _pair_diffs(ref, new) -> tuple[np.ndarray, pd.Index]:
    """pairs x queries matrix of new - ref and the query index; every Series must cover the same queries."""
    ref, new = list(ref), list(new)
    if not ref or len(ref) != len(new):
        raise ValueError(f'need the same non-zero number of pairs, got {len(ref)} and {len(new)}')
    idx = ref[0].index
    if not idx.is_unique:
        raise ValueError('query index is not unique')
    rows = []
    for a, b in zip(ref, new):
        if len(a) != len(idx) or len(b) != len(idx) or not (a.index.isin(idx).all() and b.index.isin(idx).all()):
            raise ValueError('the arms are not on the same queries')
        rows.append(b.reindex(idx).to_numpy(dtype=float) - a.reindex(idx).to_numpy(dtype=float))
    d = np.vstack(rows)
    if not np.isfinite(d).all():
        raise ValueError('non-finite per-query values')
    return d, idx


def two_level(d: np.ndarray, *, groups, index=None, n_boot: int = N_BOOT, seed: int = SEED,
              chunk: int = 50) -> np.ndarray:
    """Two-level bootstrap of the mean of d (pairs x queries): users with replacement, all queries of a drawn user
    together and the same users in every pair, then pairs with replacement; returns the n_boot replicas of the mean
    difference. groups (required, keyword): user per query as in `estimate` (None = queries, tests only)."""
    n_pairs, n = d.shape
    sums, sizes = _cluster_sums(d.T, _codes(groups, index, n))
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for start in range(0, n_boot, chunk):
        c = min(chunk, n_boot - start)
        counts = _cluster_counts(rng, len(sizes), c)
        by_pair = (counts @ sums) / (counts @ sizes)[:, None]
        pick = rng.integers(0, n_pairs, (c, n_pairs))
        out[start:start + c] = np.take_along_axis(by_pair, pick, axis=1).mean(axis=1)
    return out


def confirm(y_all, y_minus, *, groups, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """Confirmation of D: y_all, y_minus are per-pair Series (2 fresh seed pairs) of ALL_P and ALL_P \\ D on
    S0-select. Delta = ALL_P \\ D - ALL_P; t = Delta / SD of the two-level bootstrap (users x pairs); confirmed if
    t > 1.64. groups: users of the queries (Series by query id or array in the order of y_all[0])."""
    d, idx = _pair_diffs(y_all, y_minus)
    reps = two_level(d, groups=groups, index=idx, n_boot=n_boot, seed=seed)
    delta, se = float(d.mean()), float(reps.std(ddof=1))
    t = delta / se if se > 0 else math.copysign(math.inf, delta) if delta else 0.0
    return {'delta': delta, 'se': se, 't': t, 'confirmed': bool(t > T_CONFIRM),
            'by_pair': [float(v) for v in d.mean(axis=1)]}


def mechanism(est: Estimate, twins: dict, c_val: dict | None = None, exclude=()) -> dict:
    """Twin contrasts of §7. twins: twin column -> family column (e.g. {'T1': 'F3'}). exclude: families out of SEL
    (D); the twin arm replaces the remaining family with the largest t(beta_g - beta_twin).

    SE of beta_g - beta_twin = sqrt(V_gg + V_tt - 2 V_gt + 2 SE_empty^2): V the bootstrap covariance (same replicas
    as `estimate`), plus the seed noise of each slope (independent between columns in the orthogonal plan).

    c_val: None before the C_val read, else family -> (SEL - twin arm) on C_val. Class: t > 2 and c_val[g] > 0 ->
    'механизм установлен'; t <= 2, beta_g > 0 and t_g > 2 -> 'форма без механизма'; otherwise 'не различено'
    ('ждёт C_val' for t > 2 while c_val is None)."""
    rows = {}
    for tw, g in twins.items():
        if tw in est.empty or g in est.empty:
            raise ValueError(f'{tw} or {g} is an empty column')
        diff = float(est.beta[g] - est.beta[tw])
        var = float(est.cov.loc[g, g] + est.cov.loc[tw, tw] - 2 * est.cov.loc[g, tw]) + 2 * est.se_empty ** 2
        t = diff / math.sqrt(var)
        if t > T_MECHANISM:
            cls = WAITING if c_val is None else (MECHANISM if (c_val.get(g) or 0) > 0 else NOT_DISTINGUISHED)
        elif est.beta[g] > 0 and est.t[g] > T_MECHANISM:
            cls = FORM
        else:
            cls = NOT_DISTINGUISHED
        rows[g] = {'twin': tw, 'beta': float(est.beta[g]), 'beta_twin': float(est.beta[tw]), 'diff': diff,
                   'se': math.sqrt(var), 't': t, 't_family': float(est.t[g]), 'class': cls}
    table = pd.DataFrame.from_dict(rows, orient='index')
    left = table.drop(index=[g for g in exclude if g in table.index])
    return {'table': table, 'arm': None if left.empty else str(left['t'].idxmax())}


def h1(ref, new, *, groups, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """H1 of §9 on C_test: ref = H+r+ and new = SEL, lists of per-query Series by seed pair (4 pairs) on the same
    queries (groups: their users). Delta1 = mean of new - ref; two-level bootstrap (users, then pairs), one-sided
    95% bounds = 5% and 95% percentiles.
    'обыгрывает H+': lower > 0, Delta1 >= 0.001 and Delta > 0 on >= 3 pairs; 'уступает': upper < 0;
    'не различено': [lower, upper] covers 0; otherwise 'не решено'. Decisions on unrounded values."""
    d, idx = _pair_diffs(ref, new)
    reps = two_level(d, groups=groups, index=idx, n_boot=n_boot, seed=seed)
    delta = float(d.mean())
    lower, upper = (float(v) for v in np.percentile(reps, [5, 95]))
    by_pair = d.mean(axis=1)
    positive = int((by_pair > 0).sum())
    if lower > 0 and delta >= DELTA_MIN and positive >= PAIRS_MIN:
        verdict = BEATS
    elif upper < 0:
        verdict = LOSES
    elif lower <= 0 <= upper:
        verdict = UNRESOLVED
    else:
        verdict = UNDECIDED
    return {'delta': delta, 'lower': lower, 'upper': upper, 'pairs_positive': positive, 'n_pairs': len(by_pair),
            'by_pair': [float(v) for v in by_pair], 'verdict': verdict, 'n_boot': n_boot, 'seed': seed}
