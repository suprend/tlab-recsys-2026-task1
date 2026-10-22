"""Half B of val 2019, read once for H9 and H11 after the owner's literal «да» (h9.md and h11.md, «Условное правило
для B»; the step spec is council/runs/night/2026-10-22-bughunt.md, finding «B-step spec», points 0–8).

Owner's yes, chat of 22.10.2026 (session 6f57ee67-3e16-4fa5-a412-e45c43c303a6): «да — чтение B 2019 для H9 и H11».
It is passed verbatim with --owner-yes and --owner-date and written into the result; the text must contain «да»,
«B 2019» and the hypothesis (H9 | H11), otherwise nothing is read. The H11 variant with large groups (--groups 10 |
15) needs a yes that names it too (группами по 10 | --groups 10 | L10); the yes above does not.

  h9   W (the stage-2 winner, `W` of h9-result.json) on seeds (2026, 0) and (7, 1) from models/<W>_s0/_s1.cbm against
       the B rows of grid_Hp_s0/_s1: «H+ не на плато», if ΔB of the two-seed means >= +0.0015 and the lower CI bound
       > 0, otherwise «без выигрыша»; d by seed is descriptive. No W (stage 1 passed nobody): B is not read.
  h11  G* (G_star.fits of h11-result.json: h11_g<r>_s0/_s1 of the last accepted group) and h11_step_s1 from their .cbm;
       step s0 = agent_night20_r6_base, all = pl19_Hag_s0/_s1, H = q2_d8/q3_d8_s1 (descriptive) from the B rows of
       their parquet. D_B = group - all, E_B = group - step, rules 2–5 in order (task1_side.h11_rule on the CI of B).
       G* stays as chosen on A. Rule 1 on A (no group accepted): B is not read and verdict 1 stays.

Interpretation of h9.md (written into the result as `interpretation`): its B rule is conditioned on the owner's yes
and on W, not on the A verdict «недонастроен» («W (два зерна) один раз скорится на B … Вердикт B заменяет вердикт A»).
So W that exists under the A verdict «без выигрыша» is scored on B as well, and the B verdict replaces the A one.

One run, in this order: the owner's yes; B not spent (no marker artifacts/side/<h>/B.started, no <h>-B-result.json
unless it says B_read = false); for H11 every other B read of H11, main or variant, in any order (prior_B; after one the yes must say «повторно»);
the A result (status ok, its code stamp = the current one, all files of task1_side.STAMPED); the plan from it (W, or G*
and rule != 1); the configs of the reused fits (task1_side.require_reused); every model from its runs.jsonl record
(config, full stamp) and its .cbm (trees, depth, l2, lr, rsm, seed, number of features), features from
model.feature_names_. Then under council.side.heavy_step('<h>-B', 'rees46-2019'): check_2019; the same checks again,
whose fingerprint (sha256 of the A result, runs.jsonl, every .cbm and this module) must equal the one before the lock;
the snapshot of task1_side; pass A over the val days 08–13.11 (`split_day`: the guard of task1_side, then each day
split by exp.half before any join; the B rows are dropped at once) and the recheck against <name>.A.parquet (max|Δ| = 0
over all METRICS for every model). A recheck that differs writes the result with status refused and B_read = false:
no marker, B untouched, a rerun allowed. Otherwise the marker (O_EXCL: from here B of this hypothesis is spent; any
exception writes status failed and is re-raised), pass B (the A rows dropped, B rows only predicted), per_query of B
(<name>.B.parquet), the B rows of the references by `WHERE half = 'B'`, the same queries for all, M.bootstrap_diff
(2000, seed 2026) on the per-query mean of the two seeds, the verdict. Nothing of B is printed before the verdict.

Reads: val days 08–13.11 of days6 and the extra tables, the .cbm of the new fits, <name>.A.parquet, artifacts/side/<h>/
runs.jsonl, <h>-result.json, artifacts/task1/v2/exp/runs.jsonl and the reference parquet (half B; nothing else).
Writes only artifacts/side/<h>/ (B.started, <name>.B.parquet) and council/runs/side/<h>-B-result.json through
council.side.Out; <h>-result.json (the A verdict) is not touched, its sha256 before and after goes into the result.
council/side/task1_side.py and council/side/__init__.py are imported, not changed (they are in the code stamp of the
passed path check). A real run needs this module, its tests and the files of task1_side.COMMITTED committed.

  TASK1_PERIOD=2019 .venv/bin/python -m council.side.task1_side_b h9 --dry \\
      --owner-yes 'да — чтение B 2019 для H9 и H11' --owner-date 2026-10-22
  TASK1_PERIOD=2019 .venv/bin/python -X faulthandler -m council.side.task1_side_b h9 \\
      --owner-yes 'да — чтение B 2019 для H9 и H11' --owner-date 2026-10-22 \\
      --owner-source 'chat 6f57ee67-3e16-4fa5-a412-e45c43c303a6'
  (the same with h11; H11 after H9, each under its own heavy lock)
"""
from __future__ import annotations

import os
import sys

if os.environ.get('TASK1_PERIOD', '2019') != '2019':
    raise SystemExit(f"TASK1_PERIOD={os.environ['TASK1_PERIOD']!r}: B of H9 and H11 is REES46 2019 only")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from catboost import CatBoostClassifier  # noqa: E402

from council import side as S  # noqa: E402
from council.side import task1_side as T  # noqa: E402
from task1 import exp  # noqa: E402
from task1 import model as M  # noqa: E402

SELF = 'council/side/task1_side_b.py'
HALF_A, HALF_B = T.HALF_A, 'B'
B_QUERIES = 19361  # h11.md, «Данные и роли»
H9_B_GAIN = 0.0015  # h9.md: «Край настройки», on B
STEPS_B = ('h9', 'h11')
COMMITTED_B = (SELF, 'council/tests/test_side_task1_b.py') + T.COMMITTED
MARKER = 'B{}.started'  # artifacts/side/<h>/B.started, B-L10.started for a variant of H11
KEEP_B = ['qid', 'product_id', 'label', 'label_purchase', 'n_targets', 'n_targets_purchase']
TOL = 1e-6  # CatBoost keeps lr, l2 and rsm as float32
REPLACES = 'вердикт B заменяет вердикт A в отчёте'
H9_INTERPRETATION = (
    'h9.md, «Условное правило для B», по букве: при дословном «да» W (два зерна) один раз скорится на B; условие — '
    'наличие W (2-й этап состоялся), а не вердикт A «недонастроен». Поэтому и при вердикте A «без выигрыша» с W B '
    'читается, и вердикт B заменяет вердикт A. Без W (1-й этап не прошла ни одна рука) B не читается.')
H11_INTERPRETATION = ('h11.md, «Условное правило для B»: G* остаётся выбранным на A, приём групп на B заново не '
                      'проверяется; правила 2–5 по порядку на CI с B; при вердикте 1 на A B не читается.')
NOTES = {
    'h9': ('W выбрана на A из пяти рук: эффект выбора завышает d победителя на A; на B он не действует, но B '
           'одна и читается один раз. Разности меньше ≈0.001 по протоколу не считаются установленными.'),
    'h11': ('таблицы агента придуманы, когда агент видел A, и подстроены под A; G* выбран приёмом на A. Разности '
            'меньше ≈0.001 по протоколу не считаются установленными.'),
}
H11_B_TEXT = {
    2: 'на B групповой приём сохраняет часть сигнала, но меньше, чем всё сразу',
    3: 'на B групповой приём держит сигнал наравне со всем сразу и больше пошагового (G* выбран на A)',
    4: 'на B групповой приём выше всего сразу (G* выбран на A)',
    5: 'на B не различено',
}
DEVIATIONS = [
    'шаг B — отдельный модуль task1_side_b.py: task1_side.py и council/side/__init__.py не меняются (они в штампе '
    'пройденной проверки пути)',
    'H11 на B: номер правила — task1_side.h11_rule по CI с B; формулировки переписаны «на B» (тексты h11_rule 3–4 '
    'говорят «на A»)',
    'число запросов B сверяется с 19 361 описательно (warnings); шаг останавливает только расхождение запросов B '
    'новых моделей и опор',
    'замок — side <h>-B, журнал heavy — council/runs/side/queue.jsonl',
    'H11: на B скорятся только G* и h11_step_s1, а не все новые подгонки h11_g<r>_s<i> (h11.md:211) — консервативное '
    'сужение: остальные группы нужны только для приёма на A, правилам 2–5 их B не нужен',
    'два прохода по дням val под замком: сначала A (строки B дня сразу отбрасываются) и сверка max|Δ| = 0; маркер и '
    'проход B — только после неё; отказ сверки пишет результат с B_read = false и не тратит чтение',
    'штамп A-прогона сверяется целиком (все файлы task1_side.STAMPED), а не только task1/*',
]


@dataclasses.dataclass
class Step:
    """One B read: the context of task1_side (paths, hooks, stamp) and the owner's yes."""
    ctx: T.Ctx
    owner_yes: str
    owner_date: str
    owner_source: str | None = None
    expected_b: int | None = B_QUERIES


# ---------------------------------------------------------------- the owner's yes, single use

def check_owner(text: str, when: str, h: str, groups: int = 5) -> str:
    """The yes must contain «да», «B 2019» and H9 | H11 (a variant of H11 with large groups also its name)."""
    if h not in STEPS_B:
        raise S.Refused(f'{h}: B is read for H9 and H11 only')
    t = (text or '').strip()
    need = {'да': re.search(r'(?<!\w)да(?!\w)', t, re.I),
            'B 2019': re.search(r'(?<!\w)[BВ] 2019(?!\d)', t),
            h.upper(): re.search(rf'(?<!\w){h.upper()}(?!\w)', t)}
    if h == 'h11' and groups != 5:
        need[f'группы по {groups}'] = re.search(rf'(?<!\w)(по\s+{groups}|--groups\s+{groups}|L{groups})(?!\w)', t)
    missing = [k for k, v in need.items() if not v]
    if missing:
        raise S.Refused(f'the owner\'s yes {t!r} does not name {missing}: B of {h} is not read')
    try:
        d = date.fromisoformat(when)
    except (TypeError, ValueError):
        raise S.Refused(f'--owner-date {when!r}: YYYY-MM-DD')
    if d > date.today():
        raise S.Refused(f'--owner-date {when}: in the future')
    return t


def tag(ctx: T.Ctx) -> str:
    return f'-L{ctx.groups}' if ctx.h == 'h11' and ctx.groups != 5 else ''


def marker_name(ctx: T.Ctx) -> str:
    return MARKER.format(tag(ctx))


def result_b_name(ctx: T.Ctx) -> str:
    return T.result_name(ctx).replace('-result.json', '-B-result.json')


def b_spent(marker: Path, result: Path) -> bool:
    """B is spent by a marker, or by a result that does not say B_read = false (a refusal before the marker)."""
    if marker.exists():
        return True
    return result.exists() and json.loads(result.read_text(encoding='utf-8')).get('B_read') is not False


def refuse_if_used(ctx: T.Ctx) -> None:
    m, r = T.wpath(ctx, marker_name(ctx)), T.wpath(ctx, result_b_name(ctx), runs=True)
    if b_spent(m, r):
        raise S.Refused(f'{m.name} or {r.name} exists: B of {ctx.h} has been read once already')


def prior_b(ctx: T.Ctx, yes: str):
    """H11: every other B read of H11 (main, L10, L15), in any order; after one of them the yes must say «повторно»."""
    if ctx.h != 'h11':
        return None
    info = {}
    for g in (5, 10, 15):
        if g == ctx.groups:
            continue
        t = f'-L{g}' if g != 5 else ''
        m = T.wpath(ctx, MARKER.format(t))
        r = T.wpath(ctx, f'h11{t}-B-result.json', runs=True)
        one = {'marker': str(m) if m.exists() else None, 'file': str(r) if r.exists() else None}
        if r.exists():
            rr = json.loads(r.read_text(encoding='utf-8'))
            one |= {'status': rr.get('status'), 'verdict_B': rr.get('verdict_B'), 'B_read': rr.get('B_read')}
        one['read'] = b_spent(m, r)
        info[f'groups{g}'] = one
    info['read'] = any(v['read'] for v in info.values())
    if info['read'] and not re.search(r'(?<!\w)повторно(?!\w)', yes, re.I):
        raise S.Refused('another B read of H11 exists; this one needs a yes that says «повторно»')
    return info


def mark(step: Step) -> dict:
    """Create the single-use marker atomically; an existing one refuses."""
    ctx = step.ctx
    p = T.wpath(ctx, marker_name(ctx))
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {'step': ctx.h, 'groups': ctx.groups, 'owner_yes': step.owner_yes, 'owner_date': step.owner_date,
           'owner_source': step.owner_source, 'pid': os.getpid(), 'started': S.now()}
    try:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise S.Refused(f'{p} exists: B of {ctx.h} has been read once already')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec


# ---------------------------------------------------------------- preconditions from the A result

def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def a_result(ctx: T.Ctx) -> tuple:
    p = ctx.out.runs / T.result_name(ctx)
    if not p.exists():
        raise S.Refused(f'{p.name}: no A result; B is read only after the A run')
    r = json.loads(p.read_text(encoding='utf-8'))
    if r.get('status') != 'ok' or r.get('step') != ctx.h:
        raise S.Refused(f'{p.name}: step {r.get("step")!r}, status {r.get("status")!r}; B needs status ok')
    if ctx.h == 'h11' and r.get('groups') != ctx.groups:
        raise S.Refused(f'{p.name}: groups {r.get("groups")}, asked {ctx.groups}')
    if r.get('code') != ctx.stamp:
        raise S.Refused(f'{p.name}: the code stamp of the A run differs from the current code')
    return p, r


def plan(ctx: T.Ctx, res: dict) -> dict:
    """New fits to score (name -> expected config) and the reference fits whose B is read, from the A result."""
    if ctx.h == 'h9':
        w = res.get('W')
        if not w:
            raise S.Refused('h9-result.json has no W (stage 1 passed nobody): B is not read')
        axis = dict(T.H9_ARMS).get(w)
        if axis is None:
            raise S.Refused(f'W {w!r} is not an arm of h9.md')
        new = {f'{w}_s{i}': T.config(ctx, T.HP | T.SEEDS[i] | axis) for i in (0, 1)}
        return {'new': new, 'refs': list(T.HP_REF), 'W': w, 'axis': axis}
    if res.get('rule') == 1 or not res.get('accepted'):
        raise S.Refused('h11: verdict 1 on A (no group accepted): B is not read, verdict 1 stays')
    acc = [r['round'] for r in res['rounds'] if r['accepted']]
    gs = T.groups_of(ctx.groups)
    tables = [t for t in T.AGENT if t in {x for r in acc for x in gs[r - 1]}]
    fits = [T.h11_name(ctx.groups, max(acc), i) for i in (0, 1)]
    if len(acc) != res['accepted'] or res['G_star'] != {'fits': fits, 'tables': tables}:
        raise S.Refused(f'h11: G_star {res["G_star"]} does not follow from the accepted rounds {acc}')
    new = {f: T.config(ctx, T.H | T.SEEDS[i] | {'extra': tables}) for i, f in enumerate(fits)}
    new['h11_step_s1'] = T.config(ctx, T.R6BASE | T.SEEDS[1])
    return {'new': new, 'refs': [T.STEP_REF] + T.ALL_REF + T.H_REF, 'G_star': fits, 'accepted': len(acc)}


def load_model(ctx: T.Ctx, name: str, cfg: dict) -> dict:
    """The last runs.jsonl record (config, full code stamp) and the saved .cbm (trees, depth, l2, lr, rsm, seed,
    features)."""
    rec = T.last_records(ctx).get(name)
    if rec is None:
        raise S.Refused(f'{name}: no record in runs.jsonl')
    if rec['cfg'] != cfg:
        raise S.Refused(f'{name}: the recorded config differs from the expected one')
    if rec['code'] != ctx.stamp:
        raise S.Refused(f'{name}: fit with another code stamp')
    if rec['model'] != f'models/{name}.cbm':
        raise S.Refused(f'{name}: model {rec["model"]!r}')
    mp, ap = T.wpath(ctx, 'models', f'{name}.cbm'), T.wpath(ctx, f'{name}.A.parquet')
    if not mp.exists() or not ap.exists():
        raise S.Refused(f'{name}: no saved model or A file')
    m = CatBoostClassifier()
    m.load_model(str(mp))
    p = m.get_all_params()
    close = lambda a, b: abs(float(a) - float(b)) < TOL
    checks = {'trees': m.tree_count_ == cfg['iterations'], 'depth': p.get('depth') == cfg['depth'],
              'l2': close(p.get('l2_leaf_reg'), cfg['l2']), 'lr': close(p.get('learning_rate'), cfg['lr']),
              'rsm': close(p.get('rsm', 1), cfg.get('rsm', 1)), 'seed': p.get('random_seed') == cfg['seed'],
              'loss': p.get('loss_function') == 'Logloss', 'features': len(m.feature_names_) == rec['features']}
    bad = [k for k, v in checks.items() if not v]
    if bad:
        raise S.Refused(f'{name}: the saved model differs from its record in {bad}')
    return {'name': name, 'cfg': cfg, 'model': m, 'features': list(m.feature_names_),
            'sha256': sha256(mp), 'features_n': rec['features']}


# ---------------------------------------------------------------- the pass over val

def split_day(days_dir, d: date) -> tuple:
    """One val day split into its half A and half B rows before anything is joined or scored; the guard of
    task1_side (val anchors 08–13.11, no sealed directory) runs before the file is opened."""
    T.guard_days('val', days_dir, [d])
    df = exp.read_day(d, str(days_dir))
    h = exp.half(df['user_id'].to_numpy())
    a = df[h == HALF_A].reset_index(drop=True)
    b = df[h == HALF_B].reset_index(drop=True)
    del df
    return a, b


def per_query(frame, score, half: str):
    """As task1_side.score_a and exp.run: NDCG/Recall, then the purchase metrics joined."""
    pq = M.per_query(frame, score)
    pq['half'] = half
    return pq.join(M.per_query(frame, score, purchase=True).add_prefix('purchase_'), how='left')


def score_a_rows(mod: dict, rows):
    """Per-query metrics of half A rows (the recheck against <name>.A.parquet)."""
    val = exp.with_extra(rows, mod['cfg']['extra'])
    return per_query(val, M.predict(mod['model'], val, mod['features']), HALF_A)


def predict_b_rows(mod: dict, rows):
    """Predictions of half B rows with the columns per_query needs; no metric here."""
    val = exp.with_extra(rows, mod['cfg']['extra'])
    out = val[KEEP_B].copy()
    out['score'] = M.predict(mod['model'], val, mod['features'])
    return out


def days_of(models: list):
    days = {m['cfg']['days'] for m in models}
    if len(days) != 1:
        raise S.Refused(f'models read different day tables: {sorted(days)}')
    return days.pop()


def pass_a(models: list) -> dict:
    """The first pass over the val days: name -> per-query metrics of half A; the B rows of a day are dropped."""
    days_dir, parts = days_of(models), {m['name']: [] for m in models}
    for d in M.days('val'):
        a, b = split_day(days_dir, d)
        del b
        for m in models:
            parts[m['name']].append(score_a_rows(m, a))
        del a
    return {n: pd.concat(v).sort_index() for n, v in parts.items()}


def pass_b(models: list) -> dict:
    """The second pass, after the recheck and the marker: name -> [B predictions by day]; the A rows are dropped."""
    days_dir, parts = days_of(models), {m['name']: [] for m in models}
    for d in M.days('val'):
        a, b = split_day(days_dir, d)
        del a
        for m in models:
            parts[m['name']].append(predict_b_rows(m, b))
        del b
    return parts


def max_abs(saved, new) -> dict:
    """max|Δ| per metric of two per-query frames of the same half (NaN must sit in the same places)."""
    if not saved.index.equals(new.index):
        return {'same_queries': False, 'queries_saved': int(len(saved)), 'queries_new': int(len(new)),
                'max_abs': None}
    mx = {}
    for c in T.METRICS:
        x, y = saved[c].to_numpy(dtype=float), new[c].to_numpy(dtype=float)
        if not (np.isnan(x) == np.isnan(y)).all():
            mx[c] = float('inf')
        else:
            k = ~np.isnan(x)
            mx[c] = float(np.abs(x[k] - y[k]).max()) if k.any() else 0.0
    return {'same_queries': True, 'queries': int(len(saved)), 'max_abs': mx}


def recheck_passed(rc: dict) -> bool:
    return all(r['same_queries'] and all(v == 0 for v in r['max_abs'].values()) for r in rc.values())


# ---------------------------------------------------------------- half B, after the recheck

def metrics_b(parts: list):
    f = pd.concat(parts, ignore_index=True)
    return per_query(f, f['score'].to_numpy(), HALF_B).sort_index()


def ref_b(ctx: T.Ctx, name: str):
    """Per-query metrics of half B of a reused fit, from its parquet in artifacts/task1/v2/exp (only after «да»)."""
    q = str(ctx.ref_dir / f'{name}.parquet').replace("'", "''")
    df = duckdb.sql(f"SELECT qid, {', '.join(T.METRICS)} FROM read_parquet('{q}') WHERE half = '{HALF_B}'").df()
    return df.set_index('qid').sort_index()


def ndcg_of(frames: dict, names):
    names = [names] if isinstance(names, str) else list(names)
    ms = [frames[n]['ndcg'] for n in names]
    if not all(s.index.equals(ms[0].index) for s in ms):
        raise SystemExit(f'fits {names} differ in B queries')
    s = sum(ms) / len(ms)
    if s.isna().any():
        raise SystemExit(f'{names}: NDCG is missing for some B queries')
    return s


def boot_b(frames: dict, ref, new) -> dict:
    """mean(new - ref) on B, per-query mean over seeds, M.bootstrap_diff (2000, seed 2026), unrounded."""
    a, b = ndcg_of(frames, ref), ndcg_of(frames, new)
    if not a.index.equals(b.index):
        raise SystemExit(f'{ref} and {new} differ in B queries')
    d, lo, hi = M.bootstrap_diff(a, b, **T.BOOT)
    return {'ref': ref, 'new': new, 'half': HALF_B, 'd': float(d), 'ci': [float(lo), float(hi)],
            'queries': int(len(a))}


def compare_h9(frames: dict, pl: dict) -> dict:
    w = [f"{pl['W']}_s{i}" for i in (0, 1)]
    mean = boot_b(frames, T.HP_REF, w)
    flat = mean['d'] < H9_B_GAIN or mean['ci'][0] <= 0
    return {'W': pl['W'], 'axis': pl['axis'], 'mean': mean,
            'by_seed': [boot_b(frames, T.HP_REF[i], w[i]) for i in (0, 1)], 'by_seed_reading': 'описательно',
            'verdict_B': (f"H+ на B без выигрыша по оси {pl['W']}" if flat else
                          f"H+ не на плато: ось {pl['W']} даёт на B ΔB >= +{H9_B_GAIN} при CI > 0")}


def compare_h11(frames: dict, pl: dict, res_a: dict, size: int) -> dict:
    group, step, all_ = pl['G_star'], [T.STEP_REF, 'h11_step_s1'], T.ALL_REF
    raw = {'D': boot_b(frames, all_, group), 'E': boot_b(frames, step, group)}
    rule, text = T.h11_rule(raw, res_a['accepted'], size)
    return {'groups': size, 'arms': {'H': T.H_REF, 'step': step, 'all': all_, 'group': group}, **raw,
            'to_H': {'step': boot_b(frames, T.H_REF, step), 'all': boot_b(frames, T.H_REF, all_),
                     'group': boot_b(frames, T.H_REF, group), 'reading': 'описательно'},
            'rule': rule, 'rule_text_h11_rule': text, 'verdict_B': H11_B_TEXT[rule]}


def half_b(step: Step, pl: dict, res_a: dict, models: list, b_parts: dict) -> tuple:
    """Per-query B of the new fits (written to <name>.B.parquet) and of the references; then the comparisons."""
    ctx = step.ctx
    frames = {}
    for m in models:
        frames[m['name']] = metrics_b(b_parts.pop(m['name']))
        T.wpath(ctx, f"{m['name']}.B.parquet")
        ctx.out.write_frame(frames[m['name']].reset_index(), f"{m['name']}.B.parquet")
    for r in pl['refs']:
        frames[r] = ref_b(ctx, r)
    first = next(iter(frames.values())).index
    same = {n: bool(f.index.equals(first)) for n, f in frames.items()}
    body = {'B_queries': int(len(first)), 'B_queries_expected': step.expected_b,
            'B_queries_match': None if step.expected_b is None else len(first) == step.expected_b,
            'same_B_queries': same}
    if not all(same.values()):
        return 'refused', body | {'reason': 'запросы B новых моделей и опор не совпали: сравнения не считались'}
    if body['B_queries_match'] is False:
        body['warnings'] = [f'запросов B {len(first)}, ожидалось {step.expected_b} (h11.md)']
    cmp = compare_h9(frames, pl) if ctx.h == 'h9' else compare_h11(frames, pl, res_a, ctx.groups)
    return 'ok', body | cmp | {'replaces': REPLACES}


# ---------------------------------------------------------------- run, dry

def prepare(step: Step) -> dict:
    """Everything before the B read: the yes, single use, the A result, the plan, the references, the models, and
    the fingerprint (sha256 of the A result, runs.jsonl, every .cbm and this module) to compare under the lock."""
    ctx = step.ctx
    T.require_2019()
    check_owner(step.owner_yes, step.owner_date, ctx.h, ctx.groups)
    refuse_if_used(ctx)
    prior = prior_b(ctx, step.owner_yes)
    a_path, res_a = a_result(ctx)
    pl = plan(ctx, res_a)
    reused = T.require_reused(ctx, pl['refs'])
    models = [load_model(ctx, n, c) for n, c in pl['new'].items()]
    finger = {'A': sha256(a_path), 'runs': sha256(T.wpath(ctx, 'runs.jsonl')),
              'models': {m['name']: m['sha256'] for m in models}, 'code_B': sha256(T.ROOT / SELF), 'prior_B': prior}
    return {'a_path': a_path, 'res_a': res_a, 'plan': pl, 'reused': reused, 'models': models, 'prior_B': prior,
            'finger': finger}


def finish(step: Step, pre: dict, t0: float, status: str, body: dict, rc: dict, protected: dict, started) -> dict:
    """Write <h>-B-result.json; B_read says whether the marker was set (a refusal before it does not spend B)."""
    ctx = step.ctx
    a_after = sha256(pre['a_path'])
    stamp_same = ctx.stamp_fn() == ctx.stamp and sha256(T.ROOT / SELF) == pre['finger']['code_B']
    reasons = [body['reason']] if status != 'ok' else []
    if protected['n_incident']:
        reasons.append('изменение под artifacts/task1/v2 или task1/runs')
    if a_after != pre['finger']['A']:
        reasons.append(f'{pre["a_path"].name} изменился')
    if not stamp_same:
        reasons.append('код изменился во время шага')
    status = 'refused' if reasons else 'ok'
    res_a = pre['res_a']
    result = {'step': f'{ctx.h}-B', 'status': status, 'B_read': started is not None,
              'groups': ctx.groups if ctx.h == 'h11' else None, 'owner_yes': step.owner_yes,
              'owner_date': step.owner_date, 'owner_source': step.owner_source, 'marker': started,
              'prior_B': pre['prior_B'], 'eval': 'val half B 2019-11-08..13, один раз',
              'interpretation': H9_INTERPRETATION if ctx.h == 'h9' else H11_INTERPRETATION,
              'A': {'file': pre['a_path'].name, 'verdict_A': res_a.get('verdict'), 'rule_A': res_a.get('rule'),
                    'sha256_before': pre['finger']['A'], 'sha256_after': a_after,
                    'untouched': a_after == pre['finger']['A']},
              'models': {m['name']: {'sha256': m['sha256'], 'features': m['features_n']} for m in pre['models']},
              'path_A_recheck': rc, 'A_recheck_passed': recheck_passed(rc), **body,
              'note': NOTES[ctx.h], 'reasons': reasons, 'deviations': DEVIATIONS, 'reused': pre['reused'],
              'protected': protected, 'code': ctx.stamp, 'code_B': {SELF: pre['finger']['code_B']},
              'commit': ctx.commit, 'peak_rss_gb': S.peak_rss_gb(), 'seconds_total': round(time.time() - t0, 1),
              'finished': S.now()}
    T.wpath(ctx, result_b_name(ctx), runs=True)
    ctx.out.write_json(result, result_b_name(ctx), runs=True)
    if protected['n_incident']:
        raise SystemExit(S.PROTECTED_EXIT)
    if status != 'ok':
        raise SystemExit(f'{ctx.h}-B refused: {reasons}')
    return result


def failed(step: Step, started: dict, e: BaseException) -> None:
    """After the marker: any exception leaves <h>-B-result.json with status failed (B is spent) and is re-raised."""
    ctx = step.ctx
    try:
        ctx.out.write_json({'step': f'{ctx.h}-B', 'status': 'failed', 'B_read': True, 'error': repr(e),
                            'marker': started, 'owner_yes': step.owner_yes, 'owner_date': step.owner_date,
                            'code': ctx.stamp, 'commit': ctx.commit, 'finished': S.now()},
                           result_b_name(ctx), runs=True)
    except Exception:
        pass


def run(step: Step) -> dict:
    ctx = step.ctx
    pre = prepare(step)
    t0 = time.time()
    started = None
    with S.heavy_step(f'{T.OUT_NAME[ctx.h]}{tag(ctx)}-B', T.DATASET, ctx.out, wait=ctx.wait, **ctx.heavy_kw):
        ctx.check_fn()
        if prepare(step)['finger'] != pre['finger']:
            raise S.Refused('the A result, runs.jsonl, a model or this module changed while waiting for the lock: '
                            'B is not read')
        before = T.snapshot(ctx.snapshot_roots)
        a_new = pass_a(pre['models'])
        rc = {m['name']: max_abs(T.metrics_a(ctx, m['name']), a_new[m['name']]) for m in pre['models']}
        del a_new
        if recheck_passed(rc):
            started = mark(step)
            try:
                b_parts = pass_b(pre['models'])
                status, body = half_b(step, pre['plan'], pre['res_a'], pre['models'], b_parts)
                del b_parts
                protected = T.snapshot_verdict(before, ctx.snapshot_roots)
            except BaseException as e:
                failed(step, started, e)
                raise
        else:
            status, body = 'refused', {'reason': 'повтор A не совпал с сохранённым <name>.A.parquet: B не читался, '
                                                 'маркер не ставился'}
            protected = T.snapshot_verdict(before, ctx.snapshot_roots)
    return finish(step, pre, t0, status, body, rc, protected, started)


def dry(step: Step) -> dict:
    """The checks before the lock without reading a day or a B row: no marker, nothing written."""
    pre = prepare(step)
    ctx = step.ctx
    return {'dry': True, 'step': f'{ctx.h}-B', 'owner_yes': step.owner_yes, 'owner_date': step.owner_date,
            'A': {'file': pre['a_path'].name, 'verdict_A': pre['res_a'].get('verdict')},
            'interpretation': H9_INTERPRETATION if ctx.h == 'h9' else H11_INTERPRETATION,
            'new': {m['name']: {'features': m['features_n'], 'sha256': m['sha256']} for m in pre['models']},
            'refs': pre['plan']['refs'], 'reused': pre['reused'], 'prior_B': pre['prior_B'], 'commit': commit_state(),
            'marker': str(T.wpath(ctx, marker_name(ctx))), 'result': str(T.wpath(ctx, result_b_name(ctx), runs=True)),
            'heavy': f'side {T.OUT_NAME[ctx.h]}{tag(ctx)}-B', 'deviations': DEVIATIONS}


def commit_state() -> dict:
    dirty = T.git('status', '--porcelain', '--', *COMMITTED_B)
    return {'clean': not dirty.strip(), 'dirty': dirty.splitlines(), 'head': T.git('rev-parse', 'HEAD').strip()}


def committed() -> str:
    st = commit_state()
    if not st['clean']:
        raise SystemExit('commit this module, its tests and the files of task1_side.COMMITTED first:\n'
                         + '\n'.join(st['dirty']))
    return st['head']


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='one read of half B of val 2019 for H9 and H11 (owner\'s yes)')
    ap.add_argument('step', choices=list(STEPS_B))
    ap.add_argument('--owner-yes', required=True, help='the owner\'s literal yes, verbatim')
    ap.add_argument('--owner-date', required=True, help='the date of the yes, YYYY-MM-DD')
    ap.add_argument('--owner-source', default=None, help='where the yes was given (chat, session)')
    ap.add_argument('--groups', type=int, choices=[5, 10, 15], default=5, help='h11: the variant read on A')
    ap.add_argument('--dry', action='store_true', help='checks only: no day, no B row, no marker')
    ap.add_argument('--no-wait', action='store_true', help='refuse instead of waiting for the heavy lock')
    args = ap.parse_args(argv)
    T.require_2019()
    if args.groups != 5 and args.step != 'h11':
        ap.error('--groups is an option of h11')
    try:
        yes = check_owner(args.owner_yes, args.owner_date, args.step, args.groups)
        out = T.make_out(args.step)
        commit = None if args.dry else committed()
        ctx = T.Ctx(args.step, out, commit=commit, groups=args.groups, wait=not args.no_wait)
        step = Step(ctx, yes, args.owner_date, args.owner_source)
        if args.dry:
            S.print_json(dry(step))
            return 0
        res = run(step)
    except S.Refused as e:
        raise SystemExit(f'refused: {e}')
    S.print_json({k: res.get(k) for k in ('step', 'status', 'verdict_B', 'B_queries', 'A_recheck_passed',
                                          'peak_rss_gb', 'seconds_total')})
    return 0


if __name__ == '__main__':
    sys.exit(main())
