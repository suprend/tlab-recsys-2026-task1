"""Post-test analyses on validation only, pre-registered in task1/runs/grid-2026-10-20/spec.md.

grid: does automation replace the hand-made features? R = (F1 - F0) / (H - F0) on val half B with a paired
bootstrap CI, paired differences F1 - H and H+ - H (the latter per seed too), and the reading rules of the spec.
edge: depth 10 and YetiRank at depth 8 against q2_d8 on half A; arms that pass get a second seed and one look at B.
Decisions use unrounded values; numbers are rounded for output only. Every grid and edge run read must have the
config of the queue it was declared in (grid.json, edge2.json) with the stand's defaults; the H pair comes from
earlier queues and is not checked here.

Run: .venv/bin/python -m task1.posthoc   (prints the result and writes task1/runs/grid-2026-10-20/result.json)
"""
import json

import numpy as np

from task1 import exp
from task1 import model as M

DIR = M.ROOT / 'task1/runs/grid-2026-10-20'
H = ['q2_d8', 'q3_d8_s1']
ARMS = {'F0': 'grid_F0', 'F1': 'grid_F1', 'Hp': 'grid_Hp', 'F1dfs': 'grid_F1dfs', 'F1agent': 'grid_F1agent'}
FEATURES = {'grid_F0': 6, 'grid_F1': 200, 'grid_Hp': 274, 'grid_F1dfs': 134, 'grid_F1agent': 72,
            'grid_d10': 80, 'grid_yeti8': 80}
EDGE = ('grid_d10', 'grid_yeti8')


def runs(prefix):
    return [f'{prefix}_s0', f'{prefix}_s1']


def done(name):
    return (exp.OUT / f'{name}.parquet').exists()


def check_configs(names):
    """The last record of each run in runs.jsonl must carry the config declared in the queues and the expected
    number of features; a rerun under the same name would otherwise be read silently."""
    declared = {}
    for q in ('grid.json', 'edge2.json'):
        if (DIR / q).exists():
            declared |= {x['name']: {k: v for k, v in x.items() if k != 'name'} for x in json.loads((DIR / q).read_text())}
    last = {}
    for line in (exp.OUT / 'runs.jsonl').read_text().splitlines():
        r = json.loads(line)
        last[r['name']] = r
    for n in names:
        want = exp.DEFAULT | declared[n]
        got = last[n]['cfg']
        if {k: got.get(k) for k in want} != want:
            raise ValueError(f'{n}: config in runs.jsonl differs from its queue entry')
        if last[n]['features'] != FEATURES[n.rsplit('_', 1)[0]]:
            raise ValueError(f"{n}: {last[n]['features']} features, expected {FEATURES[n.rsplit('_', 1)[0]]}")


def diff(ref, new, on):
    """mean(new - ref) over the queries of one half with the paired bootstrap CI of exp.compare, unrounded."""
    a, b = exp.metrics(ref), exp.metrics(new)
    idx = a.index[a.half == on]
    d, lo, hi = M.bootstrap_diff(a.loc[idx, 'ndcg'], b.loc[idx, 'ndcg'])
    return float(d), float(lo), float(hi)


def ratio(f0, f1, h, n=2000, seed=2026):
    """mean(f1 - f0) / mean(h - f0) with a paired bootstrap over queries (the draws of M.bootstrap_diff)."""
    num, den = (f1 - f0).to_numpy(), (h - f0).to_numpy()
    rng = np.random.default_rng(seed)
    rs = []
    for _ in range(n):
        i = rng.integers(0, len(num), len(num))
        rs.append(num[i].mean() / den[i].mean())
    return float(num.mean() / den.mean()), float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))


def out(ref, new, d):
    return {'ref': ref, 'new': new, 'd': round(d[0], 5), 'ci': [round(d[1], 5), round(d[2], 5)]}


def grid():
    m = {'H': exp.metrics(H)} | {k: exp.metrics(runs(v)) for k, v in ARMS.items()}
    for k, v in m.items():
        if not v.index.equals(m['H'].index):
            raise ValueError(f'arm {k} differs from H in queries')
    idx = m['H'].index[m['H'].half == 'B']
    x = {k: v.loc[idx, 'ndcg'] for k, v in m.items()}
    raw = {'H-F0': diff(runs(ARMS['F0']), H, 'B'), 'F1-H': diff(H, runs(ARMS['F1']), 'B'),
           'Hp-H': diff(H, runs(ARMS['Hp']), 'B'),
           'Hp-H_by_seed': [diff(h, p, 'B') for h, p in zip(H, runs(ARMS['Hp']))]}
    for arm in ('F1', 'F1dfs', 'F1agent'):
        raw[f'R_{arm}'] = ratio(x['F0'], x[arm], x['H'])
    res = {'queries_B': len(idx), 'ndcg_B': {k: round(float(v.mean()), 5) for k, v in x.items()},
           'H-F0': out(runs(ARMS['F0']), H, raw['H-F0']), 'F1-H': out(H, runs(ARMS['F1']), raw['F1-H']),
           'Hp-H': out(H, runs(ARMS['Hp']), raw['Hp-H']),
           'Hp-H_by_seed': [out(h, p, d) for h, p, d in zip(H, runs(ARMS['Hp']), raw['Hp-H_by_seed'])]}
    for arm in ('F1', 'F1dfs', 'F1agent'):
        r, lo, hi = raw[f'R_{arm}']
        res[f'R_{arm}'] = {'r': round(r, 3), 'ci': [round(lo, 3), round(hi, 3)]}
    res['verdict'] = verdict(raw)
    return res


def verdict(raw):
    """The reading rules of the spec (the cases the plan of 20.10 left open were added before the run)."""
    r, (_, lo, hi) = raw['R_F1'][0], raw['F1-H']
    if raw['H-F0'][0] < 0.005:
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
    joint = all(d >= 0.0015 and lo > 0 for d, lo, _ in raw['Hp-H_by_seed'])
    hv = ('гипотеза: пошаговый приём терял совместный сигнал, проверять на январе–феврале' if joint
          else 'автоматика не дополняет ручные признаки на ≥ +0.0015 с CI > 0 на обоих зёрнах')
    return {'R': rv, 'H+': hv}


def edge():
    res = {}
    for arm in EDGE:
        s0, s1 = runs(arm)
        if not done(s0):
            continue
        check_configs([s0])
        a = diff('q2_d8', s0, 'A')
        rec = {'A': out('q2_d8', s0, a), 'passes_A': bool(a[0] >= 0.0008)}
        if not rec['passes_A']:
            rec['verdict'] = 'без выигрыша'
        elif done(s1):
            check_configs([s1])
            b = diff(H, [s0, s1], 'B')
            rec['B'] = out(H, [s0, s1], b)
            rec['verdict'] = 'база не на плато' if b[0] >= 0.0015 and b[1] > 0 else 'без выигрыша'
        else:
            rec['verdict'] = f'прошла A: нужен второй прогон {s1}, затем один взгляд на B'
        res[arm] = rec
    return res


def main():
    res = {'edge': edge()}
    names = [n for v in ARMS.values() for n in runs(v)]
    missing = [n for n in names if not done(n)]
    if missing:
        res['grid'] = {'missing': missing}
    else:
        check_configs(names)
        res['grid'] = grid()
        (DIR / 'result.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
