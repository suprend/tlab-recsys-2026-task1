"""Post-test analyses on validation only, pre-registered in task1/runs/grid-2026-10-20/spec.md.

grid: does automation replace the hand-made features? R = (F1 - F0) / (H - F0) on val half B with a paired
bootstrap CI, paired differences F1 - H and H+ - H (the latter per seed too), and the reading rules of the spec.
edge: depth 10 and YetiRank at depth 8 against q2_d8 on half A; arms that pass get a second seed and one look at B.

Run: .venv/bin/python -m task1.posthoc   (prints the result and writes task1/runs/grid-2026-10-20/result.json)
"""
import json

import numpy as np

from task1 import exp
from task1 import model as M

DIR = M.ROOT / 'task1/runs/grid-2026-10-20'
H = ['q2_d8', 'q3_d8_s1']
ARMS = {'F0': 'grid_F0', 'F1': 'grid_F1', 'Hp': 'grid_Hp', 'F1dfs': 'grid_F1dfs', 'F1agent': 'grid_F1agent'}
EDGE = ('grid_d10', 'grid_yeti8')


def runs(prefix):
    return [f'{prefix}_s0', f'{prefix}_s1']


def done(name):
    return (exp.OUT / f'{name}.parquet').exists()


def ratio(f0, f1, h, n=2000, seed=2026):
    """mean(f1 - f0) / mean(h - f0) with a paired bootstrap over queries (the draws of M.bootstrap_diff)."""
    num, den = (f1 - f0).to_numpy(), (h - f0).to_numpy()
    rng = np.random.default_rng(seed)
    rs = []
    for _ in range(n):
        i = rng.integers(0, len(num), len(num))
        rs.append(num[i].mean() / den[i].mean())
    return float(num.mean() / den.mean()), float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))


def grid():
    m = {'H': exp.metrics(H)} | {k: exp.metrics(runs(v)) for k, v in ARMS.items()}
    for k, v in m.items():
        if not v.index.equals(m['H'].index):
            raise ValueError(f'arm {k} differs from H in queries')
    idx = m['H'].index[m['H'].half == 'B']
    x = {k: v.loc[idx, 'ndcg'] for k, v in m.items()}
    out = {'queries_B': len(idx), 'ndcg_B': {k: round(float(v.mean()), 5) for k, v in x.items()},
           'H-F0': exp.compare(runs(ARMS['F0']), H, on='B')}
    for arm in ('F1', 'F1dfs', 'F1agent'):
        r, lo, hi = ratio(x['F0'], x[arm], x['H'])
        out[f'R_{arm}'] = {'r': round(r, 3), 'ci': [round(lo, 3), round(hi, 3)]}
    out['F1-H'] = exp.compare(H, runs(ARMS['F1']), on='B')
    out['Hp-H'] = exp.compare(H, runs(ARMS['Hp']), on='B')
    out['Hp-H_by_seed'] = [exp.compare(h, p, on='B') for h, p in zip(H, runs(ARMS['Hp']))]
    out['verdict'] = verdict(out)
    return out


def verdict(o):
    """The reading rules of the spec; the cases the plan of 20.10 left open were added before the run."""
    r, (lo, hi) = o['R_F1']['r'], o['F1-H']['ci']
    if o['H-F0']['d'] < 0.005:
        rv = 'R не толкуем: H − F0 < 0.005'
    elif r >= 0.8 and lo <= 0 <= hi:
        rv = 'автоматика заменяет ручные признаки'
    elif r >= 0.8 and lo > 0:
        rv = 'автоматика без ручных признаков сильнее ручной базы'
    elif r >= 0.8:
        rv = 'автоматика воспроизводит большую часть вклада ручных признаков, но уступает им'
    elif r < 0.5:
        rv = 'эта автоматика не воспроизводит ручные реляционные признаки'
    else:
        rv = 'автоматика воспроизводит ручные признаки частично'
    joint = o['Hp-H']['d'] >= 0.0015 and all(s['ci'][0] > 0 for s in o['Hp-H_by_seed'])
    hv = ('гипотеза: пошаговый приём терял совместный сигнал, проверять на январе–феврале' if joint
          else 'H+ не превосходит H на +0.0015 с CI > 0 на обоих зёрнах: автоматика не дополняет ручные признаки')
    return {'R': rv, 'H+': hv}


def edge():
    out = {}
    for arm in EDGE:
        s0, s1 = runs(arm)
        if not done(s0):
            continue
        a = exp.compare('q2_d8', s0, on='A')
        rec = {'A': a, 'passes_A': a['d'] >= 0.0008}
        if not rec['passes_A']:
            rec['verdict'] = 'без выигрыша'
        elif done(s1):
            b = exp.compare(H, [s0, s1], on='B')
            rec['B'] = b
            rec['verdict'] = 'база не на плато' if b['d'] >= 0.0015 and b['ci'][0] > 0 else 'без выигрыша'
        else:
            rec['verdict'] = f'прошла A: нужен второй прогон {s1}, затем один взгляд на B'
        out[arm] = rec
    return out


def main():
    res = {'edge': edge()}
    missing = [n for v in ARMS.values() for n in runs(v) if not done(n)]
    if missing:
        res['grid'] = {'missing': missing}
    else:
        res['grid'] = grid()
        (DIR / 'result.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
