"""What the council plan reveals without a new read of the targets (plan council/runs/night/2026-10-22-plan.md,
task E2-lite). Descriptive only: no claim, no verdict, every number with its n.

Read-only. The module reads JSON and JSONL journals only (`_read_json` refuses any other suffix); it imports nothing
of the council and never calls a function that reads scores or targets. Inputs of a dataset
(D = council/runs/rees46-2020 or council/runs/xfer-<x>):
  D/prereg-0.json     rehearsal.se_boot: the query-bootstrap SE of a slope of the null rehearsal, sigma_fit = 0
                      (council/design.py:375 `rehearse`; xfer writer council/xfer/plan.py:341, REES46 file committed)
  D/prereg-1.json     cards[].{id, lens, sign} (council/agents.py:1039 prereg1); fallback D/cards-final.json cards[]
  D/prereg-2.json     families {F_k: card id}, empty [columns] (council/plan.py:80, council/xfer/plan.py:436);
                      fallback D/curation.json families (F_k = families[k - 1])
  D/plan-result.json  beta {column: {what, beta, se, t}}, se_empty (council/plan.py:115,
                      council/xfer/plan.py:496); se = sqrt(se_boot^2 + se_empty^2) (council/design.py:157)
  D/val.json          REES46 only: contrasts {'ALL_P − H+r (вклад совета)': {d, ci95, by_pair}}
                      (council/plan.py:159, 182-205); the xfer contract has no C_val
  fit records         REES46 artifacts/task1/v2020/council/fits/runs.jsonl (council/fit.py:272),
                      xfer artifacts/council/xfer-<x>/fits/runs.jsonl (council/xfer/fit.py:564): scanned for an
                      importance map, which neither writer stores today
A missing input gives `⟨ждёт <file>⟩` in place of its block, never an error.

  H3   does the council know the sign of its families? Over the present F-columns (empty F and PL excluded), overall
       and per lens G1-G4: the share of beta-hat > 0 against 1/2 (one-sided binomial p), the columns with t > 2 and
       t < -2, and Spearman of the card sign (+1 / -1) against beta-hat with an exact (n <= 8) or Monte Carlo
       permutation p. When every card has the same sign the block is degenerate (H3 cannot be tested: only the
       share of beta-hat > 0 is left); with mixed signs the permutation p of Spearman is the reference, and the
       agreement of signs is read against the base share of beta-hat > 0, not against 1/2.
  H2   seed noise beyond the query bootstrap. se_boot = sqrt(mean over the empty columns of se_c^2 - se_empty^2)
       from plan-result (se_c = sqrt(se_boot_c^2 + se_empty^2), council/design.py:188; the empty columns only,
       the families carry their own effects); SE_seed = sqrt(max(se_empty^2 - se_boot^2, 0)), its share of the
       variance of the empty slopes and se_empty / se_boot; the chi-square 95% interval of se_empty over n_empty - 1
       degrees of freedom carries into SE_seed. prereg-0 rehearsal.se_boot is a separate line, the forecast of the
       rehearsal, also scaled by sqrt(select_queries_expected / queries).
  H1'  the ratio d(C_val) / sum of beta-hat (S0-select): ALL_P − H+r on C_val (train -> full_val, 2 seed pairs)
       over the sum of the family slopes of the plan (T_fit -> S0-select); it mixes non-additivity of the families
       with the transfer between the two set-ups. No bootstrap interval: val.json keeps two per-pair means and the
       95% interval of the contrast, plan-result keeps no covariance of the slopes and no per-query values exist in
       JSON. An approximate delta-method interval (se_d = width of ci95 / 3.92, SE of the sum without covariances),
       the ratio per pair and the numerator interval over the fixed sum are given. Not applicable on xfer (its
       contract has no C_val).
  H14  CatBoost importance against beta-hat, if an importance map {feature: value} is stored in the fit records
       (runs.jsonl) or in a file of IMPORTANCE_FILES; card columns f_x_c<lens>_<slug> are matched also under the
       xfer sandbox name ag_c<lens>_<slug> (council/xfer/plan.py:179-181).
  H5'  (beta inside stratum against null_stratum) is not done here: it needs the per-query S0-select values (the
       cache of the plan read), which no JSON artifact holds.

  python -m council.reveal rees46|tinkoff|sber            markdown to stdout
  python -m council.reveal rees46 --write                 also D/reveal.json (the only file the module writes)
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
REES46 = 'rees46'
XFER = ('tinkoff', 'sber')
DATASETS = (REES46,) + XFER
READABLE = ('.json', '.jsonl')
LENSES = ('G1', 'G2', 'G3', 'G4')
SIGN = {'+': 1, '-': -1, '−': -1}
SEED = 2026
N_PERM = 10000
EXACT_MAX = 8                      # exact permutation distribution up to 8! = 40320 orderings
VAL_KEY = 'ALL_P − H+r'            # the start of the C_val contrast key of council/plan.py:185
OUT_NAME = 'reveal.json'
IMPORTANCE_FILES = ()              # extra files of the runs directory scanned by H14, by name
CARD_PREFIX, SANDBOX_PREFIX = 'f_x_c', 'ag_c'   # council/xfer/roles.py:113-114


# ---------------------------------------------------------------- inputs

def runs_dir(dataset: str, root: Path = ROOT) -> Path:
    if dataset == REES46:
        return root / 'council' / 'runs' / 'rees46-2020'
    if dataset in XFER:
        return root / 'council' / 'runs' / f'xfer-{dataset}'
    raise SystemExit(f'unknown dataset {dataset!r}: one of {", ".join(DATASETS)}')


def fit_records_path(dataset: str, root: Path = ROOT) -> Path:
    if dataset == REES46:
        return root / 'artifacts/task1/v2020/council/fits/runs.jsonl'
    return root / f'artifacts/council/xfer-{dataset}/fits/runs.jsonl'


def _read_json(path: Path):
    """The one reader of the module: a .json file -> object, a .jsonl file -> list of records (broken lines
    skipped); None if the file is missing. Any other suffix is refused."""
    path = Path(path)
    if path.suffix not in READABLE:
        raise ValueError(f'{path.name}: the module reads {READABLE} only')
    if not path.exists():
        return None
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.json':
        return json.loads(text)
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def waiting(*files: str) -> str:
    return f"⟨ждёт {', '.join(files)}⟩"


class Inputs:
    def __init__(self, dataset: str, root: Path = ROOT, fits: Path | None = None):
        self.dataset = dataset
        self.runs = runs_dir(dataset, root)
        self.fits = fits if fits is not None else fit_records_path(dataset, root)
        self._cache = {}

    def get(self, name: str):
        if name not in self._cache:
            self._cache[name] = _read_json(self.runs / name)
        return self._cache[name]


# ---------------------------------------------------------------- helpers

def families(inp: Inputs) -> dict | None:
    """{F_k: card id} of the plan: prereg-2 families, else curation.json families in order."""
    pre = inp.get('prereg-2.json')
    if pre and pre.get('families'):
        return dict(pre['families'])
    cur = inp.get('curation.json')
    if cur and cur.get('families'):
        return {f'F{k + 1}': c for k, c in enumerate(cur['families'])}
    return None


def cards(inp: Inputs) -> tuple[dict | None, str | None]:
    """{card id: card} with sign and lens: prereg-1.json, else cards-final.json; and the file used."""
    for name in ('prereg-1.json', 'cards-final.json'):
        d = inp.get(name)
        if isinstance(d, dict) and isinstance(d.get('cards'), list) and d['cards']:
            return {c['id']: c for c in d['cards']}, name
    return None, None


def sign_of(card: dict) -> int | None:
    s = str(card.get('sign', '')).strip().lower()
    s = {'plus': '+', 'positive': '+', 'minus': '-', 'negative': '-'}.get(s, s[:1])
    return SIGN.get(s)


def lens_of(cid: str, card: dict) -> str:
    return card.get('lens') or cid.split('-')[0]


def present_families(fam: dict, plan: dict, empty) -> list[str]:
    beta = plan.get('beta', {})
    return [f for f in fam if f in beta and f not in set(empty or []) and beta[f].get('what') != 'empty']


def spearman(x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    return float(np.corrcoef(stats.rankdata(x), stats.rankdata(y))[0, 1])


def permutation_p(x, y, n_perm: int = N_PERM, seed: int = SEED) -> float | None:
    """Two-sided permutation p of Spearman: exact over all orderings for n <= EXACT_MAX, else n_perm Monte Carlo
    shuffles, p = (1 + #{|rho*| >= |rho|}) / (1 + B)."""
    rho = spearman(x, y)
    if rho is None:
        return None
    rx, ry = stats.rankdata(np.asarray(x, float)), stats.rankdata(np.asarray(y, float))
    eps = 1e-12
    if len(rx) <= EXACT_MAX:
        perms = [np.array(p) for p in itertools.permutations(range(len(rx)))]
        null = np.array([np.corrcoef(rx[p], ry)[0, 1] for p in perms])
        return float((np.abs(null) >= abs(rho) - eps).mean())
    rng = np.random.default_rng(seed)
    null = np.array([np.corrcoef(rng.permutation(rx), ry)[0, 1] for _ in range(n_perm)])
    return float((1 + (np.abs(null) >= abs(rho) - eps).sum()) / (1 + n_perm))


def _signs_block(rows: list[dict]) -> dict:
    x = [r['sign'] for r in rows]
    y = [r['beta'] for r in rows]
    n = len(rows)
    pos = sum(1 for v in y if v > 0)
    out = {'n': n, 'n_beta_positive': pos, 'share_positive': pos / n if n else None,
           'p_share_vs_half': float(stats.binomtest(pos, n, 0.5, alternative='greater').pvalue) if n else None,
           'n_t_above_2': sum(1 for r in rows if r['t'] > 2), 'n_t_below_minus_2': sum(1 for r in rows if r['t'] < -2),
           'degenerate': len(set(x)) <= 1, 'spearman': spearman(x, y), 'perm_p': permutation_p(x, y)}
    if not out['degenerate']:
        out['agree'] = sum(1 for r in rows if r['beta'] * r['sign'] > 0)
    return out


# ---------------------------------------------------------------- H3

def h3(inp: Inputs) -> dict:
    plan, fam = inp.get('plan-result.json'), families(inp)
    by_id, source = cards(inp)
    missing = [f for f, ok in (('plan-result.json', plan), ('prereg-2.json', fam), ('prereg-1.json', by_id)) if not ok]
    if missing:
        return {'waiting': waiting(*missing)}
    rows, unknown = [], []
    for f in present_families(fam, plan, _empty(inp, plan)):
        cid = fam[f]
        card = by_id.get(cid)
        s = sign_of(card) if card else None
        if s is None:
            unknown.append(f)
            continue
        rows.append({'column': f, 'card': cid, 'lens': lens_of(cid, card), 'sign': s,
                     'beta': float(plan['beta'][f]['beta']), 't': float(plan['beta'][f]['t'])})
    signs = sorted({r['sign'] for r in rows})
    out = {'cards_from': source, 'families': rows, 'no_sign': unknown, 'degenerate': len(signs) <= 1,
           'all': _signs_block(rows),
           'by_lens': {g: _signs_block([r for r in rows if r['lens'] == g]) for g in LENSES
                       if any(r['lens'] == g for r in rows)}}
    if out['degenerate']:
        mark = {1: '«+»', -1: '«−»'}[signs[0]] if signs else '(нет карточек со знаком)'
        out['note'] = f'H3 не проверяема: все знаки {mark}; ниже только доля β̂ > 0'
    else:
        out['note'] = (f"знаки смешаны: опора — перестановочный p Spearman; совпадение знаков сравнивать с базовой "
                       f"долей β̂ > 0 = {out['all']['share_positive']:.2f}, а не с 1/2")
    return out


# ---------------------------------------------------------------- H2

def _empty(inp: Inputs, plan: dict) -> list[str]:
    pre = inp.get('prereg-2.json') or {}
    if pre.get('empty'):
        return list(pre['empty'])
    return [c for c, v in plan.get('beta', {}).items() if v.get('what') == 'empty']


def h2(inp: Inputs) -> dict:
    plan, p0 = inp.get('plan-result.json'), inp.get('prereg-0.json')
    if not plan:
        return {'waiting': waiting('plan-result.json')}
    se_empty = float(plan['se_empty'])
    empty = [c for c in _empty(inp, plan) if c in plan['beta']]
    k = len(empty)
    if k < 2:
        return {'waiting': waiting('plan-result.json: два пустых столбца или больше')}
    se_boot = math.sqrt(max(float(np.mean([float(plan['beta'][c]['se']) ** 2 - se_empty ** 2 for c in empty])), 0.0))
    df = k - 1
    lo = se_empty * math.sqrt(df / stats.chi2.ppf(0.975, df))
    hi = se_empty * math.sqrt(df / stats.chi2.ppf(0.025, df))
    seed = lambda e, b: math.sqrt(max(e * e - b * b, 0.0))
    reh = ((p0 or {}).get('rehearsal') or {}).get('se_boot')
    n_exp, n_q = (p0 or {}).get('select_queries_expected'), plan.get('queries')
    out = {'se_empty': se_empty, 'n_empty': k, 'df': df, 'empty': empty, 'se_empty_ci95': [lo, hi],
           'se_boot': se_boot, 'ratio_empty_to_boot': se_empty / se_boot if se_boot else None,
           'se_seed': seed(se_empty, se_boot), 'se_seed_ci95': [seed(lo, se_boot), seed(hi, se_boot)],
           'share_of_variance_seed': seed(se_empty, se_boot) ** 2 / se_empty ** 2 if se_empty else None,
           'rehearsal_se_boot': float(reh) if reh is not None else None,
           'rehearsal_se_boot_scaled': (float(reh) * math.sqrt(n_exp / n_q) if reh is not None and n_exp and n_q
                                        else None),
           'rehearsal_scale': f'√({n_exp} / {n_q})' if n_exp and n_q else None}
    if reh is None:
        out['rehearsal_waiting'] = waiting('prereg-0.json')
    return out


# ---------------------------------------------------------------- H1'

def h1p(inp: Inputs) -> dict:
    if inp.dataset in XFER:
        return {'status': 'не применимо', 'why': 'в контракте xfer нет C_val'}
    plan, fam = inp.get('plan-result.json'), families(inp)
    val = inp.get('val.json')
    missing = [f for f, ok in (('plan-result.json', plan), ('prereg-2.json', fam), ('val.json', val)) if not ok]
    if missing:
        return {'waiting': waiting(*missing)}
    key = next((k for k in val.get('contrasts', {}) if k.startswith(VAL_KEY)), None)
    if key is None:
        return {'waiting': waiting(f'val.json: контраст «{VAL_KEY}»')}
    c = val['contrasts'][key]
    cols = present_families(fam, plan, _empty(inp, plan))
    sum_beta = float(sum(plan['beta'][f]['beta'] for f in cols))
    se_sum = math.sqrt(sum(float(plan['beta'][f]['se']) ** 2 for f in cols))
    d = float(c['d'])
    ci = list(c.get('ci95') or [])
    ratio = d / sum_beta if sum_beta else None
    approx = None
    if ratio is not None and len(ci) == 2 and abs(sum_beta) >= 2 * se_sum:   # else the first order fails
        se_d = abs(ci[1] - ci[0]) / 3.92
        se_r = math.sqrt(se_d ** 2 + ratio ** 2 * se_sum ** 2) / abs(sum_beta)
        approx = {'se_d': se_d, 'se_ratio': se_r, 'ci95': [ratio - 1.96 * se_r, ratio + 1.96 * se_r]}
    return {'title': 'отношение d(C_val) / Σβ̂ (S0-select)', 'contrast': key, 'd': d, 'd_ci95': ci,
            'by_pair': list(c.get('by_pair') or []), 'columns': cols, 'n_families': len(cols), 'sum_beta': sum_beta,
            'se_sum_beta_no_cov': se_sum, 'ratio': ratio,
            'ratio_by_pair': [v / sum_beta for v in c.get('by_pair') or []] if sum_beta else None,
            'ratio_numerator_ci95': sorted(v / sum_beta for v in ci) if sum_beta and ci else None,
            'ratio_ci95_delta_approx': approx,
            'sum_beta_within_2se': bool(abs(sum_beta) < 2 * se_sum),
            'differs': ('числитель: train → full_val, C_val, 2 пары зёрен; знаменатель: T_fit → plan, S0-select, '
                        '48 подгонок; отношение смешивает неаддитивность семейств и перенос между постановками'),
            'why_no_ci': ('бутстрапа нет: в val.json две средние по парам зёрен и ci95 разности, в plan-result нет '
                          'ковариации β и по-запросных значений; интервал по дельта-методу приближённый '
                          '(se_d = ширина ci95 / 3.92, SE Σβ̂ без ковариаций)')}


# ---------------------------------------------------------------- H14

def _importance_maps(obj, out: list) -> None:
    """Every {feature: number} dict stored under a key containing 'importance', at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if 'importance' in str(k).lower() and isinstance(v, dict) and v and all(
                    isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values()):
                out.append({str(a): float(b) for a, b in v.items()})
            else:
                _importance_maps(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _importance_maps(v, out)


def column_names(column: str) -> tuple[str, ...]:
    """A card column and its xfer sandbox name: f_x_c<lens>_<slug> -> ag_c<lens>_<slug> (council/xfer/plan.py:179)."""
    if column.startswith(CARD_PREFIX):
        return column, SANDBOX_PREFIX + column[len(CARD_PREFIX):]
    return (column,)


def h14(inp: Inputs, files=IMPORTANCE_FILES) -> dict:
    scanned, maps, broken = [], [], []
    for p in [inp.fits] + [inp.runs / name for name in files]:
        try:
            obj = _read_json(p)
        except ValueError:
            broken.append(p.name)
            continue
        if obj is None:
            continue
        scanned.append(p.name)
        _importance_maps(obj, maps)
    if not maps:
        return {'status': 'нет данных', 'scanned': scanned, 'unreadable': broken,
                'why': ('нет данных: записи подгонок (council/fit.py:272, council/xfer/fit.py:564) не хранят '
                        'importance')}
    plan, fam, cur = inp.get('plan-result.json'), families(inp), inp.get('curation.json')
    missing = [f for f, ok in (('plan-result.json', plan), ('prereg-2.json', fam), ('curation.json', cur)) if not ok]
    if missing:
        return {'status': 'importance есть', 'maps': len(maps), 'waiting': waiting(*missing)}
    rows = []
    for f in present_families(fam, plan, _empty(inp, plan)):
        columns = cur.get('columns', {}).get(fam[f], [])
        per_map = []
        for m in maps:
            hit = [next(n for n in column_names(c) if n in m) for c in columns
                   if any(n in m for n in column_names(c))]
            if hit:
                per_map.append(sum(m[n] for n in hit))
        if per_map:
            rows.append({'column': f, 'card': fam[f], 'importance': float(np.mean(per_map)),
                         'beta': float(plan['beta'][f]['beta'])})
    x, y = [r['importance'] for r in rows], [r['beta'] for r in rows]
    return {'status': 'importance есть', 'maps': len(maps), 'families': rows, 'n': len(rows),
            'spearman': spearman(x, y), 'perm_p': permutation_p(x, y)}


# ---------------------------------------------------------------- output

def reveal(dataset: str, root: Path = ROOT, fits: Path | None = None) -> dict:
    inp = Inputs(dataset, root, fits)
    return {'dataset': dataset, 'runs': inp.runs.relative_to(root).as_posix() if inp.runs.is_relative_to(root)
            else str(inp.runs), 'H3': h3(inp), 'H2': h2(inp), "H1'": h1p(inp), 'H14': h14(inp),
            'note': 'описательно: без новых чтений меток, без выводов; n мало'}


def _f(v, d: int = 4) -> str:
    if v is None:
        return '—'
    if isinstance(v, bool):
        return 'да' if v else 'нет'
    if isinstance(v, int):
        return str(v)
    if not math.isfinite(v):
        return str(v)
    s = f'{v:.{d}f}'
    return s.replace('-', '−')


def _sign_line(name: str, b: dict, mixed: bool) -> str:
    cells = [name, b['n'], b['n_beta_positive'], _f(b['share_positive'], 2), _f(b['p_share_vs_half'], 3),
             b['n_t_above_2'], b['n_t_below_minus_2']]
    if mixed:
        cells += [b.get('agree', '—'), _f(b['spearman'], 2), _f(b['perm_p'], 3)]
    return '| ' + ' | '.join(str(c) for c in cells) + ' |'


def markdown(res: dict) -> str:
    out = [f"# Раскрытие совета без новых меток: {res['dataset']} (`{res['runs']}`)", '', f"_{res['note']}_", '']
    h = res['H3']
    out += ['## H3. Знает ли совет знак своих семейств', '']
    if 'waiting' in h:
        out.append(h['waiting'])
    else:
        mixed = not h['degenerate']
        out += [f"**{h['note']}.**", '', f"Знаки карточек — `{h['cards_from']}`; β̂ — `plan-result.json`.", '',
                '| семейство | карточка | линза | знак | β̂ | t |', '|---|---|---|---|---|---|']
        out += [f"| {r['column']} | {r['card']} | {r['lens']} | {'+' if r['sign'] > 0 else '−'} | {_f(r['beta'], 6)} | "
                f"{_f(r['t'], 2)} |" for r in h['families']]
        if h['no_sign']:
            out.append(f"\nБез знака в карточке: {', '.join(h['no_sign'])}.")
        head = ['срез', 'n', 'β̂ > 0', 'доля β̂ > 0', 'p: доля β̂ > 0 против 1/2 (одностор.)', 't > 2', 't < −2']
        if mixed:
            head += ['знак совпал', 'Spearman', 'p перестановок']
        out += ['', '| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head), _sign_line('все', h['all'], mixed)]
        out += [_sign_line(g, b, mixed) for g, b in h['by_lens'].items()]
    out.append('')
    h = res['H2']
    out += ['## H2. Шум зерна сверх бутстрапа запросов', '']
    if 'waiting' in h:
        out.append(h['waiting'])
    else:
        ci, sci = h['se_empty_ci95'], h['se_seed_ci95']
        reh = (_f(h['rehearsal_se_boot'], 6) + (f" (× {h['rehearsal_scale']} = {_f(h['rehearsal_se_boot_scaled'], 6)})"
                                                if h['rehearsal_se_boot_scaled'] is not None else '')
               if h['rehearsal_se_boot'] is not None else h.get('rehearsal_waiting', '—'))
        out += ['| величина | значение |', '|---|---|',
                f"| SE пустых столбцов (n = {h['n_empty']}, df = {h['df']}) | {_f(h['se_empty'], 6)} "
                f"[{_f(ci[0], 6)}; {_f(ci[1], 6)}] |",
                f"| SE бутстрапа = √mean(se_c² − SE_empty²) по пустым | {_f(h['se_boot'], 6)} |",
                f"| SE пустых / SE бутстрапа | {_f(h['ratio_empty_to_boot'], 2)} |",
                f"| SE_seed = √max(SE_empty² − SE_boot², 0) | {_f(h['se_seed'], 6)} "
                f"[{_f(sci[0], 6)}; {_f(sci[1], 6)}] |",
                f"| доля дисперсии пустых от зерна | {_f(h['share_of_variance_seed'], 2)} |",
                f"| прогноз репетиции, prereg-0 rehearsal.se_boot | {reh} |",
                '', 'Интервал SE пустых — χ² с n − 1 степенями свободы; переносится на SE_seed.']
    out.append('')
    h = res["H1'"]
    out += ["## H1'. Отношение d(C_val) / Σβ̂ (S0-select)", '']
    if h.get('status') == 'не применимо':
        out.append(f"не применимо ({h['why']}).")
    elif 'waiting' in h:
        out.append(h['waiting'])
    else:
        ci = h['d_ci95'] or [None, None]
        rci = h['ratio_numerator_ci95'] or [None, None]
        ap = (h['ratio_ci95_delta_approx'] or {}).get('ci95') or [None, None]
        out += ['| величина | значение |', '|---|---|',
                f"| {h['contrast']} | {_f(h['d'], 6)} [{_f(ci[0], 6)}; {_f(ci[1], 6)}] |",
                f"| по парам зёрен | {', '.join(_f(v, 6) for v in h['by_pair'])} |",
                f"| Σβ̂ ({h['n_families']} семейств) | {_f(h['sum_beta'], 6)} "
                f"(SE без ковариаций {_f(h['se_sum_beta_no_cov'], 6)}) |",
                f"| {h['title']} | {_f(h['ratio'], 2)} |",
                (f"| приближённо, дельта-метод, 95% | [{_f(ap[0], 2)}; {_f(ap[1], 2)}] |" if h['ratio_ci95_delta_approx']
                 else "| приближённо, дельта-метод, 95% | — (знаменатель не отличим от нуля, дельта-метод неприменим) |"),
                f"| по парам | {', '.join(_f(v, 2) for v in h['ratio_by_pair'] or [])} |",
                f"| интервал числителя / Σβ̂ | [{_f(rci[0], 2)}; {_f(rci[1], 2)}] |",
                f"| модуль Σβ̂ < 2 SE (знаменатель не отличим от нуля) | {_f(h['sum_beta_within_2se'])} |", '',
                f"Различия: {h['differs']}.", '', f"CI: {h['why_no_ci']}."]
    out.append('')
    h = res['H14']
    out += ['## H14. Importance против β̂', '']
    if h['status'] == 'нет данных':
        out.append(f"«нет данных» — {h['why'].removeprefix('нет данных: ')} "
                   f"(просмотрено: {', '.join(h['scanned']) or 'ничего'}).")
    elif 'waiting' in h:
        out.append(f"Карт importance: {h['maps']}. {h['waiting']}")
    else:
        out += [f"Карт importance: {h['maps']}; n = {h['n']}; Spearman {_f(h['spearman'], 2)}, "
                f"p перестановок {_f(h['perm_p'], 3)}."]
    return '\n'.join(out).rstrip() + '\n'


def main(argv=None, root: Path = ROOT, fits: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('dataset', choices=DATASETS)
    ap.add_argument('--write', action='store_true', help=f'also write {OUT_NAME} into the runs directory')
    a = ap.parse_args(argv)
    res = reveal(a.dataset, root, fits)
    sys.stdout.write(markdown(res))
    if a.write:
        path = runs_dir(a.dataset, root) / OUT_NAME
        if not path.parent.is_dir():
            print(f'\nне записано: нет каталога {path.parent}')
            return 0
        path.write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'\nзаписано: {path.relative_to(root).as_posix()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
