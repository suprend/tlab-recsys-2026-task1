"""Reading rule of C_test (council/runs/note-inference-level-2026-10-22.md §1): next to the H1 verdict, a
descriptive t over the means of the four seeds, t = mean / (s / sqrt(4)) against t_{3,0.95} = 2.35. If the verdict
is 'уступает' or 'обыгрывает H+' and |t| < 2.35, the report adds CAVEAT; the verdict itself is not rewritten.

Reads only test.json written by read-test (REES46: council.plan read_test -> {'primary': ..., 'all_16_days': ...};
xfer: council.xfer.plan read_test -> {'h1', 'contrasts', 'mechanism', 'mean', ...}). No labels, no fits, no data/.
Per-seed means come from h1.by_pair and contrast by_pair / by_seed; without them they are rebuilt from the per-fit
'mean' of the same test.json (every fit is averaged over the same queries, so mean(b - a) = mean(b) - mean(a)).
The descriptive contrasts have no contract verdict: their t is printed with its own df and no caveat.

    .venv/bin/python -m council.posthoc_ctest_t [--dataset rees46 tinkoff sber] [--file path/to/test.json] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from council.design import BEATS, LOSES, MECHANISM

ROOT = Path(__file__).resolve().parents[1]
RUNS = {'rees46': 'council/runs/rees46-2020', 'tinkoff': 'council/runs/xfer-tinkoff', 'sber': 'council/runs/xfer-sber'}

T_RULE = 2.35      # t_{3,0.95} as recorded in the note before read-test (exact quantile 2.3534)
N_RULE = 4         # the rule is stated for the four C_test seeds of H1
T_CRIT = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015}  # one-sided 95%, informational for other df
CAVEAT = 'вердикт по правилу контракта; при поправке на 4 зерна граница не пройдена'
CAVEAT_REPEAT = 'повтор знака по 2 зёрнам: при нуле «знак повторился» ≈ 25%, а не 5% (note §2)'
TOL = 1e-9

# fallback seed pairs (a, b) of b - a by the per-fit 'mean' of test.json
REES46_H1 = [(f'ctest_Hrp_s{i}', f'ctest_ALLP_s{i}') for i in range(4)]
REES46_CONTRASTS = {'H+r⁺ − H+r': [(f'ctest_Hr_s{i}', f'ctest_Hrp_s{i}') for i in range(2)],
                    'ALL_P − H+r': [(f'ctest_Hr_s{i}', f'ctest_ALLP_s{i}') for i in range(2)]}
XFER_TEST_SEEDS = (7, 11, 13, 17)
XFER_H1 = [(f'test-Hrp-{s}', f'test-SEL-{s}') for s in XFER_TEST_SEEDS]


def seed_t(by_seed) -> dict:
    """mean, SD (ddof=1), t = mean / (s / sqrt(n)) and df = n - 1 of the per-seed means. s = 0: t = ±inf (0 when
    the mean is 0 too); fewer than two seeds: s and t are None."""
    v = [float(x) for x in by_seed]
    n = len(v)
    if n == 0:
        raise ValueError('no per-seed means')
    if not all(math.isfinite(x) for x in v):
        raise ValueError(f'non-finite per-seed means: {v}')
    m = sum(v) / n
    if n < 2:
        return {'n': n, 'mean': m, 's': None, 't': None, 'df': 0}
    s = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    if s > 0:
        t = m / (s / math.sqrt(n))
    else:
        t = math.copysign(math.inf, m) if m else 0.0
    return {'n': n, 'mean': m, 's': s, 't': t, 'df': n - 1}


def needs_caveat(verdict, t, n) -> bool:
    """Note §1: 'уступает' / 'обыгрывает H+' over 4 seeds with |t| < 2.35 (strict; |t| = 2.35 passes)."""
    return verdict in (BEATS, LOSES) and n == N_RULE and t is not None and abs(t) < T_RULE


def _from_means(means: dict | None, pairs) -> tuple[list[float] | None, list[str]]:
    """Per-seed b - a from the per-fit means; the fit names missing from 'mean' otherwise."""
    means = means or {}
    missing = [x for p in pairs for x in p if x not in means]
    if missing:
        return None, missing
    return [float(means[b]) - float(means[a]) for a, b in pairs], []


def _per_seed(block: dict, keys, means, pairs, where: str) -> dict:
    """Per-seed means of a block (first key present), else rebuilt from 'mean'; 'missing' explains what is absent."""
    for k in keys:
        if isinstance(block.get(k), list) and block[k]:
            return {'by_seed': [float(x) for x in block[k]], 'source': f'{where}.{k}'}
    if pairs:
        v, miss = _from_means(means, pairs)
        if v is not None:
            return {'by_seed': v, 'source': f'{where}: mean[b] − mean[a] из test.json'}
    else:
        miss = []
    need = ' или '.join(f'{where}.{k}' for k in keys)
    how = ('взять mean[b_s] − mean[a_s] из поля mean того же test.json (средние по тем же запросам, меток не читать)'
           + (f'; в mean нет {miss}' if miss else '') if pairs else 'пары зёрен этого контраста неизвестны')
    return {'by_seed': None, 'missing': f'нет {need}; {how}'}


def _row(what: str, kind: str, block: dict, keys, means, pairs, where: str, verdict=None, delta_key='d') -> dict:
    got = _per_seed(block, keys, means, pairs, where)
    row = {'what': what, 'kind': kind, 'verdict': verdict}
    if got['by_seed'] is None:
        row['missing'] = got['missing']
        return row
    st = seed_t(got['by_seed'])
    row |= st | {'by_seed': got['by_seed'], 'source': got['source']}
    rec = block.get(delta_key)
    if rec is not None and abs(float(rec) - st['mean']) > TOL * max(1.0, abs(float(rec))):
        row['mismatch'] = f'{where}.{delta_key} = {float(rec):.6g}, среднее по зёрнам = {st["mean"]:.6g}'
    if kind == 'h1':
        row['lower'], row['upper'] = block.get('lower'), block.get('upper')
        if st['n'] != N_RULE:
            row['note'] = f'правило §1 записано для {N_RULE} зёрен, здесь {st["n"]}'
        row['caveat'] = CAVEAT if needs_caveat(verdict, st['t'], st['n']) else None
    return row


def _h1(block: dict, means, pairs, where: str) -> dict:
    h = block.get('h1')
    if not isinstance(h, dict):
        return {'what': 'H1', 'kind': 'h1', 'verdict': None, 'missing': f'нет {where}.h1'}
    return _row('H1 (SEL − H+r⁺)', 'h1', h, ('by_pair', 'by_seed'), means, pairs, f'{where}.h1',
                verdict=h.get('verdict'), delta_key='delta')


def rows_rees46(block: dict, where: str) -> list[dict]:
    """One section of REES46 test.json: h1 and the two descriptive contrasts stored as top-level keys."""
    means = block.get('mean')
    out = [_h1(block, means, REES46_H1, where)]
    for what, val in block.items():
        if isinstance(val, dict) and 'd' in val:
            out.append(_row(what, 'contrast', val, ('by_pair', 'by_seed'), means, REES46_CONTRASTS.get(what),
                            f'{where}[{what}]'))
    return out


def rows_xfer(doc: dict, where: str = 'test.json') -> list[dict]:
    """xfer test.json: h1, contrasts (by_seed, a, b) and the mechanism repeat (2 seeds, note §2)."""
    means = doc.get('mean')
    out = [_h1(doc, means, XFER_H1, where)]
    for what, c in (doc.get('contrasts') or {}).items():
        pairs = list(zip(c['a'], c['b'])) if c.get('a') and c.get('b') else None
        out.append(_row(what, 'contrast', c, ('by_seed', 'by_pair'), means, pairs, f'{where}.contrasts[{what}]'))
    mech = doc.get('mechanism') or {}
    rep = mech.get('repeat')
    if isinstance(rep, dict):
        row = _row(f"механизм {mech.get('family')}: SEL − рука-близнец", 'mechanism', rep, ('by_seed',), means, None,
                   f'{where}.mechanism.repeat', delta_key='delta')
        row['verdict'] = mech.get('class')
        row['caveat'] = CAVEAT_REPEAT if mech.get('class') == MECHANISM else None
        out.append(row)
    return out


def analyze(doc: dict) -> dict:
    """test.json of either kind -> {section: [rows]}."""
    if 'primary' in doc or 'all_16_days' in doc:
        return {k: rows_rees46(doc[k], k) for k in ('primary', 'all_16_days') if isinstance(doc.get(k), dict)}
    if 'h1' in doc or 'contrasts' in doc:
        return {'test': rows_xfer(doc)}
    raise ValueError(f'не похоже на test.json read-test: ключи {sorted(doc)}')


def _f(x, fmt='+.6f') -> str:
    if x is None:
        return '—'
    if isinstance(x, float) and math.isinf(x):
        return '+inf' if x > 0 else '-inf'
    return format(x, fmt)


def format_row(r: dict) -> list[str]:
    head = f"{r['what']}"
    if 'missing' in r:
        return [f'{head}: не хватает полей — {r["missing"]}']
    crit = T_RULE if r['kind'] == 'h1' and r['df'] == N_RULE - 1 else T_CRIT.get(r['df'])
    verdict = r['verdict'] if r['verdict'] is not None else '— (описательно, вердикта нет)'
    line = (f"{head}: Δ̄={_f(r['mean'])} s={_f(r['s'], '.6f')} t={_f(r['t'], '+.2f')} df={r['df']}"
            f" (t_df,0.95={_f(crit, '.3f') if crit else '—'}) вердикт: {verdict}")
    if r['kind'] == 'h1':
        line += f" [lower={_f(r.get('lower'))}, upper={_f(r.get('upper'))}]"
    lines = [line, f"  по зёрнам: {', '.join(_f(v) for v in r['by_seed'])} ({r['source']})"]
    for k in ('note', 'mismatch'):
        if r.get(k):
            lines.append(f'  {k}: {r[k]}')
    if r['kind'] in ('h1', 'mechanism'):
        lines.append(f"  оговорка: {r['caveat']}" if r.get('caveat') else '  оговорка: не нужна')
    return lines


def report(name: str, doc: dict) -> list[str]:
    lines = []
    for section, rows in analyze(doc).items():
        lines.append(f'[{name} {section}]')
        for r in rows:
            lines += format_row(r)
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--dataset', nargs='*', choices=sorted(RUNS), default=list(RUNS))
    ap.add_argument('--file', type=Path, help='a test.json instead of the run folders')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    targets = [(str(a.file), a.file)] if a.file else [(d, ROOT / RUNS[d] / 'test.json') for d in a.dataset]
    result = {}
    for name, path in targets:
        if not path.is_file():
            print(f'[{name}] нет {path}: read-test ещё не записал test.json')
            continue
        doc = json.loads(path.read_text(encoding='utf-8'))
        if a.json:
            result[name] = analyze(doc)
        else:
            print('\n'.join(report(name, doc)))
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
