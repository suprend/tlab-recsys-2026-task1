"""Post-hoc: how many empty columns of the plan would pass the nomination threshold if each were a candidate itself
(leave-one-empty-out SE_empty), on REES46, Tinkoff and SberMarket. Prereg: council/runs/posthoc/phantom-fwer.md.

Reads only the saved JSON of the plan (plan-result.json, prereg-2.json, selection.json); no labels, no fits, no data/.
Does not change any contract verdict. The exact WY p cannot be recomputed (the bootstrap replicas are not saved);
the independent-columns limit of design._simulate_analytic is reported instead and marked as an approximation.

    .venv/bin/python -m council.posthoc_phantom_fwer [--write council/runs/posthoc/phantom-fwer-result.json]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from scipy import stats

from council.design import P_NOMINATE, T_NOMINATE

ROOT = Path(__file__).resolve().parents[1]
RUNS = {'rees46': 'council/runs/rees46-2020', 'tinkoff': 'council/runs/xfer-tinkoff', 'sber': 'council/runs/xfer-sber'}
TOL = 1e-9


def _load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_run(run_dir) -> dict:
    """The saved plan of one dataset: beta/se/t per column, se_empty, the empty columns, the families present,
    wy_harm and the recorded nomination (plan-result D, else selection nominated, else None)."""
    run_dir = Path(run_dir)
    plan = _load_json(run_dir / 'plan-result.json')
    pre = _load_json(run_dir / 'prereg-2.json')
    sel_path = run_dir / 'selection.json'
    sel = _load_json(sel_path) if sel_path.exists() else {}
    cols = plan['beta']
    if 'D' in plan:
        d_saved, d_from = list(plan['D']), 'plan-result.D'
    elif 'nominated' in sel:
        d_saved, d_from = list(sel['nominated']), 'selection.nominated'
    else:
        d_saved, d_from = None, None
    return {
        'run': run_dir.as_posix(),
        'beta': {c: float(v['beta']) for c, v in cols.items()},
        'se': {c: float(v['se']) for c, v in cols.items()},
        't': {c: float(v['t']) for c, v in cols.items()},
        'se_empty': float(plan['se_empty']),
        'empty': list(pre['empty']),
        'families': [f for f in pre['families'] if f not in set(pre['empty'])],
        'wy_harm': {c: float(p) for c, p in plan.get('wy_harm', {}).items()},
        'D_saved': d_saved, 'D_from': d_from,
    }


def sd(values) -> float:
    v = [float(x) for x in values]
    if len(v) < 2:
        raise ValueError('SD needs at least two values')
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def check_se_empty(run: dict) -> float:
    """se_empty of plan-result must be the SD (ddof=1) of the empty betas of prereg-2; returns the relative gap."""
    recomputed = sd(run['beta'][c] for c in run['empty'])
    gap = abs(recomputed - run['se_empty']) / max(abs(run['se_empty']), 1e-300)
    if gap > TOL:
        raise SystemExit(f"{run['run']}: se_empty {run['se_empty']} != SD of the empty betas {recomputed}")
    return gap


def se_boot(run: dict, c: str) -> float:
    """SE_boot of a column, recovered from se = sqrt(se_boot^2 + se_empty^2) (per-column SE_boot is not saved)."""
    return math.sqrt(max(run['se'][c] ** 2 - run['se_empty'] ** 2, 0.0))


def wy_approx(t: float, k: int) -> float:
    """One-sided harm WY p in the independent-columns limit (design._simulate_analytic): 1 - (1 - Phi(t))^k."""
    return float(1.0 - (1.0 - stats.norm.cdf(t)) ** k)


def leave_one_out(run: dict) -> list[dict]:
    empty = run['empty']
    k = len(run['wy_harm']) + 1  # the WY harm family of this dataset plus the candidate
    rows = []
    for c in empty:
        others = [run['beta'][e] for e in empty if e != c]
        se_e = sd(others)
        sb = se_boot(run, c)
        t = run['beta'][c] / math.sqrt(sb ** 2 + se_e ** 2)
        p = wy_approx(t, k)
        rows.append({
            'column': c, 'beta': run['beta'][c], 'se_boot': sb, 'se_empty_loo': se_e,
            'share_se_empty_loo': se_e ** 2 / (sb ** 2 + se_e ** 2), 't_loo': t, 't_saved': run['t'][c],
            'harm_t': t < T_NOMINATE, 'abs_t': abs(t) > -T_NOMINATE,
            'wy_harm_approx': p, 'nominated_approx': bool(t < T_NOMINATE and p < P_NOMINATE),
            'saved_harm_t': run['t'][c] < T_NOMINATE, 'saved_abs_t': abs(run['t'][c]) > -T_NOMINATE,
        })
    return rows


def reference_rates(m: int) -> dict:
    """Per null column: P(t < -2) and P(|t| > 2) under N(0,1) and under t with m - 2 df (SD of m - 1 empties)."""
    df = m - 2
    thr = -T_NOMINATE
    return {'df_t': df,
            'normal': {'harm': float(stats.norm.cdf(-thr)), 'abs': float(2 * stats.norm.cdf(-thr))},
            't': {'harm': float(stats.t.cdf(-thr, df)), 'abs': float(2 * stats.t.cdf(-thr, df))}}


def scaled_rates(run: dict) -> dict:
    """Third reference (review 22.10): per empty column with share = se_empty^2 / se^2 (saved se), the null t has
    SD ~ sqrt(share) when SE_empty estimates the whole null spread of beta: P(t < -2) = Phi(-2/sqrt(share)) and
    t_{m-2}(-2/sqrt(share)); |t| > 2 doubles them. Both earlier references are upper bounds when SE_seed ~ 0."""
    m = len(run['empty'])
    out = {'share': {}, 'normal': {'harm': [], 'abs': []}, 't': {'harm': [], 'abs': []}}
    thr = -T_NOMINATE
    for c in run['empty']:
        share = run['se_empty'] ** 2 / run['se'][c] ** 2
        z = -thr / math.sqrt(share)
        out['share'][c] = share
        for base, cdf in (('normal', float(stats.norm.cdf(z))), ('t', float(stats.t.cdf(z, m - 2)))):
            out[base]['harm'].append(cdf)
            out[base]['abs'].append(2 * cdf)
    return out


def poisson_binomial(rates) -> list[float]:
    """pmf of the number of successes of independent Bernoulli(rates)."""
    pmf = [1.0]
    for r in rates:
        nxt = [0.0] * (len(pmf) + 1)
        for j, p in enumerate(pmf):
            nxt[j] += p * (1 - r)
            nxt[j + 1] += p * r
        pmf = nxt
    return pmf


def quantile(pmf, q: float = 0.95) -> int:
    acc = 0.0
    for j, p in enumerate(pmf):
        acc += p
        if acc >= q - 1e-12:
            return j
    return len(pmf) - 1


def upper_tail(pmf, observed: int) -> float:
    return float(sum(pmf[observed:]))


def classify(observed: int, q_normal: int, q_t: int) -> str:
    if observed <= q_normal:
        return 'не противоречит номиналу'
    if observed <= q_t:
        return 'в пределах t-хвоста'
    return 'превышение номинала'


def analyze(runs: dict) -> dict:
    """runs: dataset name -> run directory. Returns the result of the prereg (per dataset and pooled)."""
    bases = ('normal', 't', 'normal_scaled', 't_scaled')
    per, pooled_rates = {}, {b: {'harm': [], 'abs': []} for b in bases}
    counts = {'harm_t': 0, 'abs_t': 0, 'nominated_approx': 0, 'saved_harm_t': 0, 'saved_abs_t': 0}
    n = 0
    for name, path in runs.items():
        run = load_run(path)
        gap = check_se_empty(run)
        rows = leave_one_out(run)
        m = len(run['empty'])
        ref = reference_rates(m)
        for base in ('normal', 't'):
            for side in ('harm', 'abs'):
                pooled_rates[base][side] += [ref[base][side]] * m
        sc = scaled_rates(run)
        for base in ('normal', 't'):
            for side in ('harm', 'abs'):
                pooled_rates[base + '_scaled'][side] += sc[base][side]
        c = {key: sum(r[key] for r in rows) for key in counts}
        for key in counts:
            counts[key] += c[key]
        n += m
        t_loo = [r['t_loo'] for r in rows]
        per[name] = {
            'run': run['run'], 'empty': run['empty'], 'm': m, 'k_wy': len(run['wy_harm']) + 1,
            'se_empty_saved': run['se_empty'], 'se_empty_check_rel_gap': gap,
            'columns': rows, 'counts': c,
            'any_nominated_approx': c['nominated_approx'] > 0,
            'sd_t_loo': sd(t_loo), 'sd_t_saved': sd(r['t_saved'] for r in rows),
            'reference': ref,
            'expected': {base: {side: m * ref[base][side] for side in ('harm', 'abs')} for base in ('normal', 't')},
            'p_any_harm': {base: 1 - (1 - ref[base]['harm']) ** m for base in ('normal', 't')},
            'reference_scaled': {'share': sc['share'],
                                 'expected': {b: {side: sum(sc[b][side]) for side in ('harm', 'abs')}
                                              for b in ('normal', 't')}},
        }
    pooled = {'n_candidates': n, 'counts': counts}
    for side, key in (('harm', 'harm_t'), ('abs', 'abs_t')):
        out = {}
        for base in bases:
            pmf = poisson_binomial(pooled_rates[base][side])
            out[base] = {'expected': sum(pooled_rates[base][side]), 'q95': quantile(pmf),
                         'p_at_least_observed': upper_tail(pmf, counts[key])}
        out['observed'] = counts[key]
        out['outcome'] = classify(counts[key], out['normal']['q95'], out['t']['q95'])
        pooled[side] = out
    pooled['datasets_with_false_nomination_approx'] = [k for k, v in per.items() if v['any_nominated_approx']]
    return {
        'what': 'post-hoc leave-one-empty-out: empty columns as nomination candidates (prereg phantom-fwer.md)',
        'status': 'post-hoc, после плана, до/независимо от C_test; на вердикты контракта не влияет',
        'rule': {'nominate': f't < {T_NOMINATE} and WY p (harm) < {P_NOMINATE}',
                 'primary': 't_loo < -2 (t part of the threshold, necessary condition)',
                 'secondary': 'WY p approximated by 1 - (1 - Phi(t))^k, k = |wy_harm| + 1; exact WY not recomputable',
                 'symmetric': '|t_loo| > 2',
                 't_loo': 'beta_i / sqrt(se_boot_i^2 + SD(ddof=1) of the other empty betas ^2)',
                 'se_boot_i': 'sqrt(se_i^2 - se_empty^2) from plan-result'},
        'datasets': per, 'pooled': pooled,
        'review_22_10': ('normal and t are both upper bounds, not a bracket: SE_empty contains the query noise, '
                         'and with SE_seed ~ 0 (REES46, Sber) the null t has SD ~ 0.68 (design.rehearse); only '
                         'Tinkoff (seed share 0.89) is near the t reference. normal_scaled / t_scaled use '
                         'share = se_empty^2 / se^2 per column. The outcome rule (normal, t) is unchanged. '
                         'Poisson-binomial assumes 22 independent candidates; within a dataset t_loo share the '
                         'denominator, so the spread is larger and q95 understated.'),
        'not_saved': ['bootstrap replicas beta* (Estimate.draws): exact WY p of a leave-one-out candidate',
                      'per-column se_boot (recovered from se and se_empty, exact up to float rounding)',
                      'the 48 per-fit means y (needed for orthogonal phantom columns of the literature version)'],
    }


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--write', type=Path, help='write the result JSON here')
    a = ap.parse_args(argv)
    res = analyze({k: ROOT / v for k, v in RUNS.items()})
    for k, v in res['datasets'].items():
        v['run'] = Path(v['run']).relative_to(ROOT).as_posix() if Path(v['run']).is_absolute() else v['run']
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.write:
        a.write.parent.mkdir(parents=True, exist_ok=True)
        a.write.write_text(text + '\n', encoding='utf-8')
    print(text)
    return res


if __name__ == '__main__':
    main()
