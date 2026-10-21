"""The plan and the confirmation arms of the council rehearsal (council/runs/rees46-2020/contract.md, §3.3, §4).

  build        prereg-2.json and queue-plan.json from curation.json: 48 fits of `plan` (T_fit -> S0, half B)
  analyze      beta, calibration and twins on S0-select (broker.y_select) -> plan-result.json, selection.json
  cval         queue-cval.json: the C_val arms (full_val, train -> val)
  read-val     one C_val read (broker.c_val) -> val.json
  ctest        queue-test.json: the C_test arms (full_test, refit -> test); runs only after the owner's "да"
  read-test    broker.c_test -> test.json, H1 of §3.3

Run: TASK1_PERIOD=2020 .venv/bin/python -m council.plan <command>
"""
import argparse
import hashlib
import json
import sys

import numpy as np
import pandas as pd

from council import broker, design as D, roles

RUNS = roles.RUNS


def _load(name):
    return json.loads((RUNS / name).read_text())


def _save(name, obj):
    (RUNS / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=float) + '\n')


def _table(card_id):
    from council.agents import table
    return table(card_id)


def _reference_tables(curation):
    from council.agents import reference_kept
    return reference_kept(curation)


def arms(curation):
    """Extra-table lists of the arms. SEL = ALL_P (prereg-0: the power gate failed, subtraction is descriptive)."""
    fam = [_table(i) for i in curation['families']]
    rb = _reference_tables(curation)
    out = {'Hr': list(roles.HPLUS), 'Hrp': list(roles.HPLUS) + rb, 'ALLP': list(roles.HPLUS) + fam}
    out['Rb1'] = list(roles.HPLUS) + [t for t in rb if t.startswith('council_rb1_')]
    out['Rb2'] = list(roles.HPLUS) + [t for t in rb if t.startswith('council_rb2_')]
    return out


def build():
    cur = _load('curation.json')
    fams, twins = list(cur['families']), list(cur['twins'])
    names, empty = D.layout(len(fams), len(twins))
    x = D.matrix()
    col = {n: i for i, n in enumerate(D.COLUMNS)}
    placebo = {'columns': list(cur['placebo']), 'tables': [_table(i) for i in cur['placebo_families']]}
    queue = []
    for r in range(1, 49):
        row = x[r - 1]
        extra = list(roles.HPLUS)
        extra += [_table(f) for k, f in enumerate(fams) if row[col[f'F{k + 1}']] > 0]
        extra += [_table(f) + '_tw' for k, f in enumerate(twins) if row[col[f'T{k + 1}']] > 0]
        seed, neg = roles.plan_seed(r)
        queue.append({'name': f'plan_r{r:02d}', 'fit': 'T_fit', 'eval': 'S0', 'keep_half': roles.SELECT,
                      'recipe': 'plan', 'extra': extra, 'seed': seed, 'neg_seed': neg,
                      'placebo': placebo if row[col['PL']] > 0 else None})
    a = arms(cur)
    prereg = {
        'families': {f'F{k + 1}': f for k, f in enumerate(fams)},
        'twins': {f'T{k + 1}': {'family': f'F{fams.index(f) + 1}', 'card': f} for k, f in enumerate(twins)},
        'placebo': placebo, 'empty': empty, 'columns': D.COLUMNS,
        'matrix_sha256': hashlib.sha256(x.tobytes()).hexdigest(),
        'seeds': {q['name']: [q['seed'], q['neg_seed']] for q in queue},
        'arms': a, 'tables_over_hplus': {k: len(v) - len(roles.HPLUS) for k, v in a.items()},
        'curation_sha256': hashlib.sha256((RUNS / 'curation.json').read_bytes()).hexdigest(),
        'rule': 'SEL = ALL_P (prereg-0: power 0.52 < 0.8); calibration and beta descriptive; twins by design.mechanism',
        'twin_arm': 'ALL_P with the family of the largest t(beta_g - beta_twin) replaced by its twin, chosen by analyze',
        'h1': 'design.h1 on C_test, SEL vs H+r+ over seeds ' + json.dumps(roles.TEST_SEEDS),
    }
    _save('prereg-2.json', prereg)
    _save('queue-plan.json', queue)
    print(json.dumps({'runs': len(queue), 'families': len(fams), 'twins': len(twins), 'empty': empty,
                      'tables_over_hplus': prereg['tables_over_hplus']}))


def analyze():
    pre = _load('prereg-2.json')
    queue = _load('queue-plan.json')
    names = [q['name'] for q in queue]
    y = broker.y_select(names)[names]
    groups = D.users_of(y.index)
    est = D.estimate(y.to_numpy(), D.matrix(), pre['empty'], groups=groups, names=D.COLUMNS)
    wy = D.wy_maxT(est)
    p0 = _load('prereg-0.json')
    cal = D.calibrate(est.t[pre['empty']], p0['rehearsal']['sd_t_interval'], float(wy['empty_max']))
    twins = {t: v['family'] for t, v in pre['twins'].items()}
    mech = D.mechanism(est, twins)
    fam_of = pre['families'] | {t: v['card'] + '_tw' for t, v in pre['twins'].items()} | {'PL': 'placebo'}
    res = {'queries': int(len(y)), 'users': int(len(set(groups))),
           'beta': {c: {'what': fam_of.get(c, 'empty'), 'beta': float(est.beta[c]), 'se': float(est.se[c]),
                        't': float(est.t[c])} for c in D.COLUMNS},
           'se_empty': float(est.se_empty), 'wy_harm': {k: float(v) for k, v in wy['harm'].items()},
           'wy_empty_max': float(wy['empty_max']), 'calibration': cal,
           'mechanism': mech['table'].reset_index(names='family').to_dict('records'), 'twin_arm_family': mech['arm']}
    _save('plan-result.json', res)
    arm = mech['arm']
    card = pre['families'][arm] if arm else None
    _save('selection.json', {'SEL': 'ALL_P', 'D': [], 'reason': 'prereg-0: power gate failed',
                             'twin_arm': {'family': arm, 'card': card,
                                          'replace': [_table(card), _table(card) + '_tw'] if card else None}})
    print(json.dumps({'calibration': cal['passed'], 'twin_arm': arm, 'card': card}))


def _spec(name, split, extra, seed):
    fit = {'val': 'train', 'test': 'refit'}[split]
    return {'name': name, 'fit': fit, 'eval': split, 'keep_half': None, 'recipe': f'full_{split}', 'extra': extra,
            'seed': seed[0], 'neg_seed': seed[1], 'placebo': None}


def twin_extra(a, sel):
    tw = sel['twin_arm']
    if not tw['card']:
        return None
    fam, twin = tw['replace']
    return [twin if t == fam else t for t in a['ALLP']]


def cval():
    a, sel = arms(_load('curation.json')), _load('selection.json')
    q = []
    for i, s in enumerate(roles.NOISE_SEEDS):
        for arm in ('Hr', 'Hrp', 'ALLP', 'TWIN'):
            extra = twin_extra(a, sel) if arm == 'TWIN' else a[arm]
            if extra is None or (arm == 'Hr' and i == 0):  # Hr s0 = path_Hr_full_val_s0 (prereg-0)
                continue
            q.append(_spec(f'cval_{arm}_s{i}', 'val', extra, s))
    for arm in ('Rb1', 'Rb2'):
        q.append(_spec(f'cval_{arm}_s0', 'val', a[arm], roles.NOISE_SEEDS[0]))
    _save('queue-cval.json', q)
    print(json.dumps([x['name'] for x in q]))


def _contrast(y, a, b, groups):
    """mean(b - a) over seed pairs, two-level bootstrap (users, then pairs), 2.5/97.5% and the per-pair means."""
    d = np.vstack([(y[bb] - y[aa]).to_numpy() for aa, bb in zip(a, b)])
    reps = D.two_level(d, groups=groups, n_boot=2000, seed=2026)
    return {'d': float(d.mean()), 'ci95': [float(np.percentile(reps, 2.5)), float(np.percentile(reps, 97.5))],
            'by_pair': [float(v) for v in d.mean(axis=1)]}


def read_val():
    q = _load('queue-cval.json')
    names = ['path_Hr_full_val_s0'] + [x['name'] for x in q]
    y = broker.c_val(names)
    groups = D.users_of(y.index)
    n = {arm: [f'cval_{arm}_s{i}' for i in range(2)] for arm in ('Hrp', 'ALLP', 'TWIN')}
    n['Hr'] = ['path_Hr_full_val_s0', 'cval_Hr_s1']
    have = set(y.columns)
    res = {'queries': int(len(y)), 'mean': {c: float(y[c].mean()) for c in y.columns}, 'contrasts': {}}
    for what, (a, b) in {'SEL − H+r⁺ (главный, описательно)': ('Hrp', 'ALLP'),
                          'H+r⁺ − H+r (кривая объёма)': ('Hr', 'Hrp'),
                          'ALL_P − H+r (вклад совета)': ('Hr', 'ALLP'),
                          'SEL − рука-близнец (механизм)': ('TWIN', 'ALLP')}.items():
        if set(n[a] + n[b]) <= have:
            res['contrasts'][what] = _contrast(y, n[a], n[b], groups)
    if {'cval_Rb1_s0', 'cval_Rb2_s0'} <= have:
        res['contrasts']['H+Rb2 − H+Rb1 (дисперсия генерации)'] = _contrast(y, ['cval_Rb1_s0'], ['cval_Rb2_s0'], groups)
    if {'cval_Rb1_s0', 'path_Hr_full_val_s0'} <= have:
        res['contrasts']['H+Rb1 − H+r (зерно 0)'] = _contrast(y, ['path_Hr_full_val_s0'], ['cval_Rb1_s0'], groups)
        res['contrasts']['H+Rb2 − H+r (зерно 0)'] = _contrast(y, ['path_Hr_full_val_s0'], ['cval_Rb2_s0'], groups)
    sel = _load('selection.json')
    if sel['twin_arm']['family'] and 'SEL − рука-близнец (механизм)' in res['contrasts']:
        pre = _load('prereg-2.json')
        est_t = _load('plan-result.json')
        twin_d = res['contrasts']['SEL − рука-близнец (механизм)']['d']
        res['mechanism_c_val'] = {sel['twin_arm']['family']: twin_d}
        row = [m for m in est_t['mechanism'] if m['family'] == sel['twin_arm']['family']][0]
        res['mechanism_class'] = ('механизм установлен' if row['t'] > D.T_MECHANISM and twin_d > 0 else
                                  'форма без механизма' if row['t'] <= D.T_MECHANISM and row['beta'] > 0
                                  and row['t_family'] > D.T_MECHANISM else 'не различено')
        res['twin_card'] = pre['families'][sel['twin_arm']['family']]
    _save('val.json', res)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=float))


def ctest():
    a = arms(_load('curation.json'))
    q = [_spec(f'ctest_{arm}_s{i}', 'test', a[arm], s) for arm in ('Hrp', 'ALLP')
         for i, s in enumerate(roles.TEST_SEEDS)]
    q += [_spec(f'ctest_Hr_s{i}', 'test', a['Hr'], s) for i, s in enumerate(roles.TEST_SEEDS[:2])]
    _save('queue-test.json', q)
    print(json.dumps([x['name'] for x in q]))


def read_test():
    q = [x['name'] for x in _load('queue-test.json')]
    out = {}
    for primary in (True, False):
        y = broker.c_test(q, primary=primary).drop(columns='anchor')
        groups = D.users_of(y.index)
        ref = [y[f'ctest_Hrp_s{i}'] for i in range(4)]
        new = [y[f'ctest_ALLP_s{i}'] for i in range(4)]
        h = D.h1(ref, new, groups=groups)
        key = 'primary' if primary else 'all_16_days'
        out[key] = {'queries': int(len(y)), 'mean': {c: float(y[c].mean()) for c in y.columns},
                    'h1': {k: v for k, v in h.items()},
                    'H+r⁺ − H+r': _contrast(y, ['ctest_Hr_s0', 'ctest_Hr_s1'], ['ctest_Hrp_s0', 'ctest_Hrp_s1'], groups),
                    'ALL_P − H+r': _contrast(y, ['ctest_Hr_s0', 'ctest_Hr_s1'], ['ctest_ALLP_s0', 'ctest_ALLP_s1'],
                                             groups)}
    _save('test.json', out)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=float))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('command', choices=['build', 'analyze', 'cval', 'read-val', 'ctest', 'read-test'])
    cmd = ap.parse_args(argv).command
    {'build': build, 'analyze': analyze, 'cval': cval, 'read-val': read_val, 'ctest': ctest,
     'read-test': read_test}[cmd]()


if __name__ == '__main__':
    sys.exit(main())
