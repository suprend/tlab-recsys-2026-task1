"""Post-hoc Boruta-style rule: which families lie beyond all empty columns of the plan (below the minimum, above the
maximum, beyond max |beta| of the empties), compared with the recorded nomination. Prereg:
council/runs/posthoc/beyond-empties.md.

Reads only the saved JSON of the plan (plan-result.json, prereg-2.json, selection.json); no labels, no fits, no data/.
Does not change any contract verdict.

    .venv/bin/python -m council.posthoc_beyond_empties [--write council/runs/posthoc/beyond-empties-result.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scipy import stats

from council.design import P_NOMINATE, T_NOMINATE
from council.posthoc_phantom_fwer import ROOT, RUNS, check_se_empty, load_run


def beyond(values: dict, families, empty) -> dict:
    """Families below min / above max / beyond max |.| of the empties, in the order of `families`."""
    e = [values[c] for c in empty]
    lo, hi, amax = min(e), max(e), max(abs(x) for x in e)
    return {'below_min': [g for g in families if values[g] < lo],
            'above_max': [g for g in families if values[g] > hi],
            'beyond_abs': [g for g in families if abs(values[g]) > amax],
            'empty_min': lo, 'empty_max': hi, 'empty_abs_max': amax}


def null_level(k: int, m: int) -> dict:
    """Under exchangeability of null families and m empties: per family P(above max) = 1/(m+1) (same for below min
    and for beyond |.|, the latter if the null is also sign-symmetric); P(any of k above max) = k/(k+m)."""
    return {'per_family': 1 / (m + 1), 'any_of_k': k / (k + m), 'expected_count': k / (m + 1)}


def contract_nomination(run: dict) -> list[str]:
    """design.nominate on the saved t and wy_harm: t < -2 and WY p (harm) < 0.1, PL excluded."""
    return [g for g in run['families'] if g in run['wy_harm']
            and run['t'][g] < T_NOMINATE and run['wy_harm'][g] < P_NOMINATE]


def outcome(below: list[str], nominated: list[str]) -> str:
    b, d = set(below), set(nominated)
    if b == d:
        return 'совпадение'
    if d < b:
        return 'правило шире'
    if b < d:
        return 'правило уже'
    return 'расходятся'


def analyze_run(run: dict) -> dict:
    fams, empty = run['families'], run['empty']
    by_beta = beyond(run['beta'], fams, empty)
    by_t = beyond(run['t'], fams, empty)
    m = len(empty)
    crit = float(stats.t.ppf(0.975, m - 1))
    t_e = {g: run['beta'][g] / run['se_empty'] for g in fams}
    rule = contract_nomination(run)
    recorded = run['D_saved']
    ref = recorded if recorded is not None else rule
    disagree = {key: sorted(set(by_beta[key]) ^ set(by_t[key]), key=fams.index)
                for key in ('below_min', 'above_max', 'beyond_abs')}
    return {
        'run': run['run'], 'families': fams, 'empty': empty, 'm': m, 'k': len(fams),
        'beta': by_beta, 't': by_t, 'beta_vs_t_disagree': disagree,
        'null_level': null_level(len(fams), m),
        't_se_empty_only': {'crit_two_sided_975': crit, 'df': m - 1,
                            'values': t_e, 'beyond': [g for g in fams if abs(t_e[g]) > crit]},
        'nomination_recorded': recorded, 'nomination_recorded_from': run['D_from'],
        'nomination_by_rule': rule,
        'outcome_below_min_vs_nomination': outcome(by_beta['below_min'], ref),
        'outcome_reference': 'recorded' if recorded is not None else 'rule (nomination not recorded)',
    }


def analyze(runs: dict) -> dict:
    per = {}
    for name, path in runs.items():
        run = load_run(path)
        check_se_empty(run)
        per[name] = analyze_run(run)
    return {
        'what': 'post-hoc Boruta-style rule: families beyond all empty columns (prereg beyond-empties.md)',
        'status': 'post-hoc, после плана, до/независимо от C_test; на вердикты контракта не влияет',
        'rule': {'below_min': 'beta_g < min beta_E (harm direction)', 'above_max': 'beta_g > max beta_E',
                 'beyond_abs': '|beta_g| > max |beta_E|', 'repeat': 'same on saved t',
                 'variant': 't_E = beta_g / SE_empty vs t_{m-1, 0.975}'},
        'datasets': per,
    }


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--write', type=Path, help='write the result JSON here')
    a = ap.parse_args(argv)
    res = analyze({k: ROOT / v for k, v in RUNS.items()})
    for v in res['datasets'].values():
        v['run'] = Path(v['run']).relative_to(ROOT).as_posix()
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if a.write:
        a.write.parent.mkdir(parents=True, exist_ok=True)
        a.write.write_text(text + '\n', encoding='utf-8')
    print(text)
    return res


if __name__ == '__main__':
    main()
