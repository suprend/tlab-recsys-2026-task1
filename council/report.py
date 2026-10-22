"""Tables of the report "Совет над H+" (REES46 2020) and of the council on xfer (Tinkoff, SberMarket), and the
check of docs/task1-v2-report.md against them (plan council/runs/night/2026-10-22-plan.md, task E1).

Read-only. The module reads JSON and JSONL journals only, never a per-query table, a parquet file, a label or a
broker function, and writes nothing. Inputs of a dataset (D = council/runs/rees46-2020 or council/runs/xfer-<x>):
  D/prereg-0.json                             power gate and the SD t interval of the null rehearsal
  D/prereg-2.json                             xfer only: rehearsal.sd_t_interval of the actual layout (the one
                                              analyze calibrates with); REES46 calibrates with prereg-0's
  D/plan-result.json                          beta, SE, t, WY p, calibration, twins (council.plan.analyze,
                                              council.xfer.plan.estimate)
  D/selection.json                            SEL, D, twin arm, cut / cut_plan (xfer)
  REES46: D/queue-plan.json, queue-cval.json, queue-test.json  the fit names of each stage (`costs`)
  D/val.json                                  REES46 only: contrasts on C_val (council.plan.read_val)
  D/test.json                                 contrasts and H1 on C_test (council.plan.read_test,
                                              council.xfer.plan.read_test), only after the owner opened the test
  D/llm.jsonl                                 cost_usd and seconds per call, summed directly
  REES46: artifacts/task1/v2020/council/fits/runs.jsonl (seconds and peak_rss_gb of every fit; the last record
          of a name counts, as council.fit.records) and D/memory.jsonl (memory trials)
  xfer:   D/queue.jsonl (heavy `end` and light `light-end` events: seconds, ok, peak_gb; `peak` events: the peak
          of a fit record; `failed` and `stop` events: failures)
A missing file gives a waiting line in place of its table, never an error: `⟨ждёт <file>⟩`, with the words of
the report for two files (WAIT): `⟨ждёт plan-result⟩` and, for test.json, `⟨ждёт C_test, нужно «да»⟩` — or
`⟨ждёт C_test⟩` once the dataset's test-approved.md exists (`test_wait`).

Tables (TABLES; --table also takes PARTS, the pieces of `plan`):
  REES46  prereg, plan (beta + calibration + mechanism + selection), cval, cval-mean, test,
          costs (time and peak of the plan, C_val and C_test fits: the block `report:rees46:costs`),
          llm (calls, hours and $ by stage), fit-runs (every fit of runs.jsonl by phase and the memory trials)
  xfer    prereg, plan, test, llm, costs (queue.jsonl steps: count, hours, peak)

Rounding (the report uses the same): beta, SE, contrast and CI bounds, C_val means 4 decimals; t 2; WY p 3;
power 2; SD t 3; sigma_q 4; $ 2; GB 1; hours 1. Signed values (beta, t, contrasts) carry '+' or the minus sign
'−' (U+2212), as in the report; a value that rounds to zero is printed without a sign. Rounding is Python's
format spec ('{:.4f}'), applied once to the stored float. Exception: the beta and mechanism tables of a plan whose
median SE is below 5e-5 (СберМаркет, metric level ~1e-5) print beta, SE and SE_empty with 6 decimals (`plan_nd`); with the same nd the C_test tables
(H1, contrasts and their CI, mechanism repeat) and the «подтверждение D» row of the selection.

  python -m council.report rees46|tinkoff|sber            every table in its marked block, ready for the report
  python -m council.report rees46 --dry                   the inputs found and missing, then the tables, no markers
  python -m council.report rees46 --table plan            one table (a name of TABLES or PARTS)
  python -m council.report --check [--doc docs/task1-v2-report.md]

--check: every block `<!-- report:<dataset>:<table> -->` ... `<!-- /report -->` of the document is compared with
the table generated now. Three ordered lists must be equal: the numbers, the waiting lines `⟨ждёт …⟩`, and the
values of the closed vocabulary VOCAB (verdicts of design.h1, mechanism classes, пройдена/пройден/да/нет, SEL).
Other words and the layout are free. Exit 1 with a diff on a mismatch, an unknown dataset or table, an unclosed
block, or no block at all (after the dataset filter).
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs' / 'task1-v2-report.md'
REES46 = 'rees46'
XFER = ('tinkoff', 'sber')
DATASETS = (REES46,) + XFER
REES46_RUNS = 'council/runs/rees46-2020'
REES46_FITS = 'artifacts/task1/v2020/council/fits/runs.jsonl'
MINUS = '−'
DASH = '—'
POWER_GATE = 0.8          # council.design.POWER_GATE, repeated here: the module imports nothing of the council

# Tables printed by default, in report order; PARTS (the pieces of `plan`) are reachable by name too.
TABLES = {REES46: ('prereg', 'plan', 'cval', 'cval-mean', 'test', 'costs', 'llm', 'fit-runs'),
          'xfer': ('prereg', 'plan', 'test', 'llm', 'costs')}
PARTS = ('beta', 'calibration', 'mechanism', 'selection')
# The waiting line of a missing file; the report uses these words (plan of 22.10, §2), the rest is ⟨ждёт <file>⟩.
WAIT = {'plan-result.json': 'plan-result', 'test.json': 'C_test, нужно «да»'}
# The closed vocabulary of --check: council.design verdicts of h1 (BEATS, UNRESOLVED, LOSES, UNDECIDED) and
# mechanism classes (MECHANISM, FORM, NOT_DISTINGUISHED, WAITING), the yes/no words of this module and SEL values.
VOCAB = ('обыгрывает H+', 'не различено', 'уступает', 'не решено', 'механизм установлен', 'форма без механизма',
         'ждёт C_val', 'не пройдена', 'пройдена', 'не пройден', 'пройден', 'да', 'нет', 'ALL_P minus D', 'ALL_P')
LLM_NOTE = '$ — сумма cost_usd завершённых вызовов; лимит считает ещё резерв за прерванные (llm.dollars_spent).'
# REES46 stages of the `costs` table: caption (with {n} fits), the queue file that names the fits, the expected
# number of fits while that queue does not exist, the artifact that marks the stage as finished.
STAGES = (('план: {n} подгонок `plan`', 'queue-plan.json', 48, 'plan-result.json'),
          ('C_val: {n} новых подгонок `full_val`, H+r на 2026/0 — подгонка пути', 'queue-cval.json', 9, 'val.json'),
          ('C_test: {n} подгонок `full_test`', 'queue-test.json', 10, 'test.json'))


# ---------------------------------------------------------------- formatting

def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def num(x, nd: int, sign: bool = False) -> str:
    """x with nd decimals; sign: '+' for positive values; minus is U+2212; a rounded zero has no sign."""
    if not _finite(x):
        return DASH
    s = f'{x:+.{nd}f}' if sign else f'{x:.{nd}f}'
    if float(s) == 0:
        s = f'{0:.{nd}f}'
    return s.replace('-', MINUS)


def beta(x):
    return num(x, 4, sign=True)


def se(x):
    return num(x, 4)


def tval(x):
    return num(x, 2, sign=True)


def pval(x):
    return num(x, 3)


def usd(x):
    return num(x, 2)


def gb(x):
    return num(x, 1)


def hours(seconds):
    return num(seconds / 3600 if _finite(seconds) else None, 1)


def plan_nd(res: dict) -> int:
    """Decimals of beta and SE in the plan tables: 4, or 6 when the median SE of the plan columns is below 5e-5,
    where 4 decimals print every beta and SE of the plan as 0.0000."""
    ses = [b['se'] for b in (res.get('beta') or {}).values() if _finite(b.get('se'))]
    return 6 if ses and statistics.median(ses) < 5e-5 else 4


def ci(pair):
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return DASH
    return f'[{beta(pair[0])}, {beta(pair[1])}]'


def _cell(v) -> str:
    return DASH if v is None or v == '' else str(v).replace('|', '\\|').replace('\n', ' ')


def table(head: list[str], rows: list[list]) -> str:
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    lines += ['| ' + ' | '.join(_cell(c) for c in r) + ' |' for r in rows]
    return '\n'.join(lines)


def waiting(*files: str) -> str:
    return f"⟨ждёт {', '.join(WAIT.get(f, f) for f in files)}⟩"


def test_wait(src) -> str:
    """The waiting line of test.json: after the owner's «да» (test-approved.md exists) only the fits are awaited."""
    return '⟨ждёт C_test⟩' if src.file('test-approved.md').exists() else waiting('test.json')


# ---------------------------------------------------------------- inputs

@dataclass(frozen=True)
class Source:
    dataset: str
    runs: Path                 # the council/runs directory of the dataset
    fits: Path | None          # REES46 runs.jsonl of council.fit
    queue: Path | None         # xfer queue.jsonl

    @property
    def xfer(self) -> bool:
        return self.dataset in XFER

    def file(self, name: str) -> Path:
        return self.runs / name

    def json(self, name: str):
        p = self.file(name)
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def source(dataset: str, root: Path = ROOT) -> Source:
    if dataset == REES46:
        return Source(dataset, root / REES46_RUNS, root / REES46_FITS, None)
    if dataset in XFER:
        runs = root / 'council' / 'runs' / f'xfer-{dataset}'
        return Source(dataset, runs, None, runs / 'queue.jsonl')
    raise SystemExit(f'unknown dataset {dataset!r}: one of {", ".join(DATASETS)}')


def jsonl(path: Path | None) -> list[dict]:
    """Records of a journal; a broken line (a killed writer) is skipped with a warning, as council.llm does."""
    if path is None or not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding='utf-8').splitlines()):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            print(f'warning: {path}: line {i + 1} is broken and skipped', file=sys.stderr)
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


# ---------------------------------------------------------------- tables

def t_prereg(src: Source) -> str:
    p0 = src.json('prereg-0.json')
    if p0 is None:
        return waiting('prereg-0.json')
    reh = p0.get('rehearsal') or {}
    power = p0.get('power', reh.get('power'))
    gate = p0.get('gate', reh.get('gate'))
    interval, where = reh.get('sd_t_interval') or [None, None], ''
    if src.xfer:
        p2 = src.json('prereg-2.json') or {}
        if (p2.get('rehearsal') or {}).get('sd_t_interval'):
            interval, where = p2['rehearsal']['sd_t_interval'], ' (prereg-2)'
        else:
            where = ' (prereg-0, раскладка 12/4)'
    rows = [['|S0-select|, ожидается', p0.get('select_queries_expected')],
            ['запросов S0-explore', p0.get('explore_queries')],
            ['σ_q', num(p0.get('sigma_q'), 4)],
            ['мощность плана', num(power, 2)],
            [f'гейт мощности (≥ {POWER_GATE})', DASH if gate is None else ('пройден' if gate else 'не пройден')],
            [f'интервал SD t пустых (2.5–97.5%){where}', f'[{num(interval[0], 3)}, {num(interval[1], 3)}]']]
    if src.xfer:
        rows += [['пути совпали без допуска', DASH if p0.get('path_ok') is None else
                  ('да' if p0['path_ok'] else 'нет, допуск записан')],
                 ['пик пути и шума, ГБ', gb(p0.get('peak_gb'))]]
    return table(['Величина', 'Значение'], rows)


def t_beta(src: Source) -> str:
    res = src.json('plan-result.json')
    if res is None:
        return waiting('plan-result.json')
    wy = res.get('wy_harm') or {}
    nd = plan_nd(res)
    rows = [[c, b.get('what'), num(b.get('beta'), nd, sign=True), num(b.get('se'), nd), tval(b.get('t')),
             pval(wy.get(c))] for c, b in (res.get('beta') or {}).items()]
    head = (f"S0-select: запросов {res.get('queries')}, пользователей {res.get('users')}; "
            f"SE_empty = {num(res.get('se_empty'), nd)}. WY p — односторонний (вред), max-T по семействам и PL.")
    return head + '\n\n' + table(['Столбец', 'Что', 'β', 'SE', 't', 'WY p'], rows)


def t_calibration(src: Source) -> str:
    res = src.json('plan-result.json')
    if res is None:
        return waiting('plan-result.json')
    cal = res.get('calibration') or {}
    lo, hi = (list(cal.get('interval') or [None, None]) + [None, None])[:2]
    passed = cal.get('passed')
    rows = [[num(cal.get('sd_t'), 3), f'[{num(lo, 3)}, {num(hi, 3)}]', pval(cal.get('p_wy_empty')),
             DASH if passed is None else ('пройдена' if passed else 'не пройдена')]]
    out = table(['SD t пустых', 'интервал репетиции', 'WY p (max |t| пустых)', 'калибровка'], rows)
    if src.xfer and 'D' in res:
        out += f"\n\nD (номинированы планом): {', '.join(res['D']) or 'пусто'}; вычитание: {res.get('subtraction', DASH)}"
    return out


def t_mechanism(src: Source) -> str:
    res = src.json('plan-result.json')
    if res is None:
        return waiting('plan-result.json')
    nd = plan_nd(res)
    rows = [[m.get('family'), m.get('twin'), *(num(m.get(k), nd, sign=True) for k in ('beta', 'beta_twin', 'diff')),
             num(m.get('se'), nd), tval(m.get('t')), tval(m.get('t_family')), m.get('class')]
            for m in res.get('mechanism') or []]
    out = table(['Семейство', 'Близнец', 'β_g', 'β_twin', 'β_g − β_twin', 'SE', 't', 't_g', 'Класс до C_val'
                 if not src.xfer else 'Класс до C_test'], rows)
    return out + f"\n\nРука-близнец: {res.get('twin_arm_family') or 'нет'}"


def t_selection(src: Source) -> str:
    sel = src.json('selection.json')
    if sel is None:
        return waiting('selection.json')
    tw = sel.get('twin_arm') or {}
    rows = [['SEL', sel.get('SEL')], ['D', ', '.join(sel.get('D') or []) or 'пусто'],
            ['причина', sel.get('reason')], ['рука-близнец', tw.get('family') or 'нет'],
            ['карточка близнеца', tw.get('card')]]
    if src.xfer:
        rows.insert(2, ['номинированы', ', '.join(sel.get('nominated') or []) or 'пусто'])
        c = sel.get('confirmation')
        if c:
            nd = plan_nd(src.json('plan-result.json') or {})
            rows.append(['подтверждение D', f"Δ = {num(c.get('delta'), nd, sign=True)}, SE = {num(c.get('se'), nd)}, "
                                            f"t = {tval(c.get('t'))}, {'да' if c.get('confirmed') else 'нет'}"])
        if sel.get('cut'):
            rows.append(['срезаны руки', ', '.join(sel['cut'])])
        if 'cut_plan' in sel:
            rows.append(['план не запускался (cut_plan)', 'да' if sel['cut_plan'] else 'нет'])
    return table(['Поле', 'Значение'], rows)


def _contrast_rows(contrasts: dict, nd: int = 4) -> list[list]:
    rows = []
    b = lambda x: num(x, nd, sign=True)  # noqa: E731
    for what, c in (contrasts or {}).items():
        by = c.get('by_pair', c.get('by_seed')) or []
        pair = c.get('ci95')
        cell = f'[{b(pair[0])}, {b(pair[1])}]' if isinstance(pair, (list, tuple)) and len(pair) == 2 else DASH
        rows.append([what, b(c.get('d')), cell, ', '.join(b(v) for v in by)])
    return rows


def contrast_table(contrasts: dict, nd: int = 4) -> str:
    """REES46 contrasts carry by_pair (pairs of seeds), xfer ones by_seed; nd as plan_nd of the dataset's plan."""
    by_seed = any('by_seed' in c and 'by_pair' not in c for c in (contrasts or {}).values())
    head = ['Контраст', 'Δ', '95% CI', 'по зёрнам' if by_seed else 'по парам зёрен']
    return table(head, _contrast_rows(contrasts, nd))


def t_plan(src: Source) -> str:
    """beta, calibration, twins and the selection of the plan: one block of the report."""
    if not src.file('plan-result.json').exists():
        sel = src.json('selection.json')
        if sel and sel.get('cut_plan'):
            return 'План не запускался (cut_plan): SEL = ALL_P без плана и без руки-близнеца.\n\n' + t_selection(src)
        return waiting('plan-result.json')
    return '\n\n'.join(RENDER[p](src) for p in PARTS)


def t_cval(src: Source) -> str:
    val = src.json('val.json')
    if val is None:
        return waiting('val.json')
    out = f"C_val: запросов {val.get('queries')}. Описательно, двухуровневый бутстрап (пользователи, пары зёрен)."
    out += '\n\n' + contrast_table(val.get('contrasts'))
    if 'mechanism_class' in val:
        fam = ', '.join(f'{k} {beta(v)}' for k, v in (val.get('mechanism_c_val') or {}).items())
        out += f"\n\nМеханизм ({val.get('twin_card')}; SEL − близнец на C_val: {fam}): {val['mechanism_class']}"
    return out


def t_cval_mean(src: Source) -> str:
    val = src.json('val.json')
    if val is None:
        return waiting('val.json')
    return table(['Подгонка', 'NDCG@20 на C_val'], [[k, se(v)] for k, v in (val.get('mean') or {}).items()])


def _h1_row(name: str, h: dict, nd: int = 4) -> list:
    return [name, *(num(h.get(k), nd, sign=True) for k in ('delta', 'lower', 'upper')),
            f"{h.get('pairs_positive')}/{h.get('n_pairs')}", h.get('verdict')]


def t_test(src: Source) -> str:
    test = src.json('test.json')
    if test is None:
        return test_wait(src)
    nd = plan_nd(src.json('plan-result.json') or {})
    b = lambda x: num(x, nd, sign=True)  # noqa: E731
    slices = {'': test} if 'h1' in test else {k: v for k, v in test.items() if isinstance(v, dict) and 'h1' in v}
    names = {'': 'C_test', 'primary': 'C_test (основной)', 'all_16_days': 'C_test (все 16 дней)'}
    h1 = table(['Срез', 'Δ1', 'нижняя 5%', 'верхняя 95%', 'пар с Δ > 0', 'вердикт'],
               [_h1_row(names.get(k, k), v['h1'], nd) for k, v in slices.items()])
    lead = f"{test['test']} " if isinstance(test.get('test'), str) else ''   # REES46 test.json has no phrase
    out = [f"{lead}Запросов: "
           + ', '.join(f"{names.get(k, k)} {v.get('queries')}" for k, v in slices.items()), h1]
    for k, v in slices.items():
        contrasts = v.get('contrasts') if 'contrasts' in v else {
            what: c for what, c in v.items() if isinstance(c, dict) and 'ci95' in c}
        if contrasts:
            out.append(f'{names.get(k, k)}, контрасты (описательно):\n\n' + contrast_table(contrasts, nd))
    m = test.get('mechanism')
    if m:
        rep = m.get('repeat') or {}
        out.append(f"Механизм {m.get('family')} ({m.get('card')}): t на S0-select {tval(m.get('t_select'))}, "
                   f"SEL − близнец на C_test {b(rep.get('delta'))} [{b(rep.get('lower'))}, "
                   f"{b(rep.get('upper'))}], класс: {m.get('class')}")
    return '\n\n'.join(out)


def t_llm(src: Source) -> str:
    """LLM calls by stage: finished calls, the sum of their seconds and of cost_usd, read directly per row."""
    path = src.file('llm.jsonl')
    if not path.exists():
        return waiting('llm.jsonl')
    recs = jsonl(path)
    by, order = {}, []
    for r in recs:
        if not r.get('call') and not _finite(r.get('cost_usd')):
            continue                                   # a started record: no call result yet
        st = r.get('stage') or '?'
        if st not in by:
            by[st] = [0, 0.0, 0.0]
            order.append(st)
        by[st][0] += bool(r.get('call'))
        by[st][1] += float(r['seconds']) if _finite(r.get('seconds')) else 0.0
        by[st][2] += float(r['cost_usd']) if _finite(r.get('cost_usd')) else 0.0
    rows = [[st, by[st][0], hours(by[st][1]), usd(by[st][2])] for st in order]
    total = [sum(v[i] for v in by.values()) for i in range(3)]
    rows.append(['всего', total[0], hours(total[1]), usd(total[2])])
    out = table(['Стадия LLM', 'Вызовов', 'Часы', '$'], rows) + '\n\n' + LLM_NOTE
    started = {r.get('call_id') for r in recs if r.get('started')}
    ended = {r.get('call_id') for r in recs if r.get('call_id') and not r.get('started')}
    if started - ended:
        out += f'\n\nНачато без записи результата (идут или оборваны): {len(started - ended)}.'
    return out


def _phase(name: str, sep: str = '_') -> str:
    """The phase of a fit name: REES46 'plan_r01' -> 'plan'; xfer '{phase}-{arm}-{seed}' with sep '-'."""
    return str(name).split(sep, 1)[0] or '?'


def _fit_records(src: Source) -> dict:
    """name -> the last record of a fit in runs.jsonl (council.fit.records: the last record counts)."""
    return {r['name']: r for r in jsonl(src.fits) if 'name' in r}


def _seconds(rec: dict) -> float:
    return sum(v for v in (rec.get('seconds') or {}).values() if _finite(v))


def _peak(values) -> float | None:
    found = [float(v) for v in values if _finite(v)]
    return max(found) if found else None


def t_costs_rees46(src: Source) -> str:
    """Time and peak memory of the plan, C_val and C_test fits, each shown once its stage is finished (the
    artifact of STAGES exists); the fits are the names of the stage's queue file."""
    recs = _fit_records(src)
    rows = []
    for caption, queue, expected, done in STAGES:
        q = src.json(queue)
        names = [s.get('name') for s in q] if isinstance(q, list) else None
        n = len(names) if names is not None else expected
        if not src.file(done).exists() or names is None:
            w = (test_wait(src) if done == 'test.json' and not src.file(done).exists() else
                 waiting(done if not src.file(done).exists() else queue))
            rows.append([caption.format(n=n), w, w])
            continue
        have = [recs[x] for x in names if x in recs]
        peak = _peak(r.get('peak_rss_gb') for r in have)
        time = f'{hours(sum(_seconds(r) for r in have))} ч' if have else DASH
        if len(have) != len(names):
            time += f' (записей {len(have)} из {len(names)})'
        rows.append([caption.format(n=n), time, DASH if peak is None else f'{gb(peak)} ГБ'])
    return table(['Этап', 'Время', 'Пик памяти'], rows)


def t_fits(src: Source) -> str:
    """Every council fit of runs.jsonl by phase (name prefix) and the memory trials: count, hours, peak GB."""
    if not src.fits.exists():
        return waiting('runs.jsonl')
    by, order = {}, []
    for name, r in _fit_records(src).items():
        ph = _phase(name)
        if ph not in by:
            by[ph] = [0, 0.0, []]
            order.append(ph)
        by[ph][0] += 1
        by[ph][1] += _seconds(r)
        by[ph][2].append(r.get('peak_rss_gb'))
    rows = [[ph, by[ph][0], hours(by[ph][1]), gb(_peak(by[ph][2]))] for ph in order]
    rows.append(['всего', sum(v[0] for v in by.values()), hours(sum(v[1] for v in by.values())),
                 gb(_peak(p for v in by.values() for p in v[2]))])
    for m in jsonl(src.file('memory.jsonl')):
        rows.append([f"проба памяти {m.get('arm')} ({m.get('recipe')})", 1, hours(_seconds(m)), gb(m.get('peak_rss_gb'))])
    return table(['Подгонки', 'Число', 'Часы', 'Пик, ГБ'], rows)


def t_costs_xfer(src: Source) -> str:
    """Steps of queue.jsonl: heavy `end` events by kind (fits by phase), light `light-end` events by their first
    two words; seconds summed, the peak of a fit taken from its `peak` event (the fit record), else from `end`."""
    if not src.queue.exists():
        return waiting('queue.jsonl')
    recs = jsonl(src.queue)
    fit_peak = {}
    for r in recs:
        if r.get('event') == 'peak' and _finite(r.get('peak_gb')):
            fit_peak[r.get('what')] = max(fit_peak.get(r.get('what'), 0.0), float(r['peak_gb']))
    by, order, failed = {}, [], 0
    for r in recs:
        ev, what = r.get('event'), str(r.get('what') or '')
        failed += ev in ('failed', 'stop')       # council/xfer/queue.py: a fit's `end` is ok, then `failed`
        if ev not in ('end', 'light-end'):
            continue
        words = what.split()
        if ev == 'end':
            key = f'{words[0]}: {_phase(words[1], "-")}' if len(words) > 1 and words[0] == 'fit' else (words[0] if words else '?')
        else:
            key = ' '.join(words[:2]) or '?'
        if key not in by:
            by[key] = [0, 0.0, [], ev == 'end']
            order.append(key)
        by[key][0] += 1
        failed += not r.get('ok')
        by[key][1] += float(r['seconds']) if _finite(r.get('seconds')) else 0.0
        by[key][2].append(fit_peak[what] if what in fit_peak else r.get('peak_gb'))
    rows = [[k, by[k][0], hours(by[k][1]), gb(_peak(by[k][2]))] for k in order]
    heavy = [by[k] for k in order if by[k][3]]
    rows.append(['тяжёлые шаги: всего', sum(v[0] for v in heavy), hours(sum(v[1] for v in heavy)),
                 gb(_peak(p for v in heavy for p in v[2]))])
    out = table(['Шаг', 'Число', 'Часы', 'Пик, ГБ'], rows)
    return out + (f'\n\nОшибок и остановов (end/light-end не ok, failed, stop): {failed}.' if failed else '')


def t_costs(src: Source) -> str:
    return t_costs_xfer(src) if src.xfer else t_costs_rees46(src)


RENDER = {'prereg': t_prereg, 'plan': t_plan, 'beta': t_beta, 'calibration': t_calibration,
          'mechanism': t_mechanism, 'selection': t_selection, 'cval': t_cval, 'cval-mean': t_cval_mean,
          'test': t_test, 'llm': t_llm, 'costs': t_costs, 'fit-runs': t_fits}


def table_names(dataset: str) -> tuple[str, ...]:
    """Every table name of a dataset: the default ones and PARTS."""
    return (TABLES[REES46] if dataset == REES46 else TABLES['xfer']) + PARTS


def render(dataset: str, name: str, root: Path = ROOT) -> str:
    if name not in table_names(dataset):
        raise KeyError(f'{dataset} has no table {name!r}')
    return RENDER[name](source(dataset, root))


def tables(dataset: str, root: Path = ROOT) -> dict[str, str]:
    """name -> markdown text of every default table of a dataset, in report order."""
    src = source(dataset, root)
    return {name: RENDER[name](src) for name in TABLES[REES46 if dataset == REES46 else 'xfer']}


def inventory(dataset: str, root: Path = ROOT) -> str:
    src = source(dataset, root)
    names = ['prereg-0.json', 'prereg-2.json', 'plan-result.json', 'selection.json', 'test.json', 'llm.jsonl']
    if not src.xfer:
        names[4:4] = ['val.json'] + [s[1] for s in STAGES]
        names.append('memory.jsonl')
    files = [src.file(n) for n in names] + [src.queue if src.xfer else src.fits]
    lines = [f'Входы {dataset} (только чтение):']
    for f in files:
        rel = f.relative_to(root) if f.is_relative_to(root) else f
        if not f.exists():
            lines.append(f'- {rel}: нет')
        elif f.suffix == '.jsonl':
            lines.append(f'- {rel}: {len(jsonl(f))} записей')
        else:
            lines.append(f'- {rel}: есть')
    return '\n'.join(lines)


def blocks(dataset: str, root: Path = ROOT, only: str | None = None) -> str:
    """Tables in their report markers: every default table, or the one named `only`."""
    items = {only: render(dataset, only, root)} if only is not None else tables(dataset, root)
    return '\n\n'.join(f'<!-- report:{dataset}:{name} -->\n{text}\n<!-- /report -->' for name, text in items.items())


# ---------------------------------------------------------------- --check

BLOCK = re.compile(r'<!--\s*report:([\w-]+):([\w-]+)\s*-->(.*?)<!--\s*/report\s*-->', re.S)
OPEN = re.compile(r'<!--\s*report:([\w-]+):([\w-]+)\s*-->')
WAITING = re.compile(r'⟨ждёт[^⟩]*⟩')
VOCAB_RE = re.compile(r'(?<!\w)(' + '|'.join(re.escape(v) for v in sorted(VOCAB, key=len, reverse=True)) + r')(?!\w)')
SPLIT = re.compile(r'[\s|\[\](),;/:=<>«»"\'`*$%≈≥≤]+')
NUMBER = re.compile(r'[+\-−]?\d+(?:\.\d+)?')


def numbers(text: str) -> list[Decimal]:
    """The numbers of a text in order: whole tokens between separators ('F12', 'G3-4', 'Rb1' and dates are not
    numbers); U+2212 is a minus; '+0.0010' == '0.001'."""
    out = []
    for tok in SPLIT.split(text):
        tok = tok.rstrip('.')
        if NUMBER.fullmatch(tok):
            try:
                out.append(Decimal(tok.replace(MINUS, '-').lstrip('+')))
            except InvalidOperation:
                pass
    return out


def waits(text: str) -> list[str]:
    return WAITING.findall(text)


def vocab(text: str) -> list[str]:
    """The VOCAB values of a text in order, longest match first, outside the waiting lines."""
    return VOCAB_RE.findall(WAITING.sub(' ', text))


def check(doc: Path, root: Path = ROOT, dataset: str | None = None) -> tuple[bool, list[str]]:
    """(ok, messages): every marked block of the document against the generated table."""
    text = doc.read_text(encoding='utf-8')
    found = list(BLOCK.finditer(text))
    msgs, ok, cache, n_checked = [], True, {}, 0
    if len(OPEN.findall(text)) != len(found):
        ok = False
        msgs.append(f'{doc}: {len(OPEN.findall(text))} opening markers, {len(found)} closed blocks')
    for m in found:
        ds, name, body = m.group(1), m.group(2), m.group(3).strip('\n')
        if dataset is not None and ds != dataset:
            continue
        line = text.count('\n', 0, m.start()) + 1
        if ds not in DATASETS or name not in table_names(ds):
            ok = False
            msgs.append(f'{doc}:{line}: unknown block report:{ds}:{name}')
            continue
        if (ds, name) not in cache:
            cache[ds, name] = render(ds, name, root)
        gen = cache[ds, name]
        n_checked += 1
        bad = []
        for kind, f in (('numbers', numbers), ('waiting lines', waits), ('vocabulary', vocab)):
            have, want = f(body), f(gen)
            if have != want:
                k = next((i for i, (a, b) in enumerate(zip(have, want)) if a != b), min(len(have), len(want)))
                bad.append(f'{kind}: {len(have)} in the document, {len(want)} generated; first difference at '
                           f'{k + 1}: {have[k] if k < len(have) else "none"} != {want[k] if k < len(want) else "none"}')
        if not bad:
            msgs.append(f'ok report:{ds}:{name} (line {line}, {len(numbers(gen))} numbers, {len(waits(gen))} waiting, '
                        f'{len(vocab(gen))} vocabulary)')
            continue
        ok = False
        msgs.append(f'MISMATCH report:{ds}:{name} (line {line}): ' + '; '.join(bad))
        msgs.extend(difflib.unified_diff(body.splitlines(), gen.splitlines(), f'{doc.name}:{line}',
                                         f'generated report:{ds}:{name}', lineterm=''))
    if n_checked == 0 and ok:
        ok = False
        msgs.append(f'{doc}: no report blocks' + (f' of {dataset}' if dataset else ''))
    return ok, msgs


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('dataset', nargs='?', choices=DATASETS)
    ap.add_argument('--dry', action='store_true', help='inputs found and missing, then the tables without markers')
    ap.add_argument('--table', help='one table of the dataset')
    ap.add_argument('--check', action='store_true', help='compare the report blocks of --doc with the artifacts')
    ap.add_argument('--doc', type=Path, default=DOC)
    ap.add_argument('--root', type=Path, default=ROOT, help='repository root of the artifacts (tests)')
    a = ap.parse_args(argv)
    if a.check:
        ok, msgs = check(a.doc, a.root, a.dataset)
        print('\n'.join(msgs))
        print('check: ok' if ok else 'check: FAILED')
        return 0 if ok else 1
    if a.dataset is None:
        ap.error('a dataset or --check is required')
    if a.table is not None and a.table not in table_names(a.dataset):
        ap.error(f'table {a.table!r} not in {", ".join(table_names(a.dataset))}')
    if a.dry:
        out = [inventory(a.dataset, a.root)]
        items = tables(a.dataset, a.root) if a.table is None else {a.table: render(a.dataset, a.table, a.root)}
        out += [f'### {a.dataset}: {n}\n\n{t}' for n, t in items.items()]
        print('\n\n'.join(out))
    else:
        print(blocks(a.dataset, a.root, a.table))
    return 0


if __name__ == '__main__':
    sys.exit(main())
