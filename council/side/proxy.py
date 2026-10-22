"""H6: a cheap proxy Π of the council plan on REES46 2020 (council/runs/side/proxy.md; night plan 22.10, hypothesis
10; docs/feature-council-design.md, «Ветка Π»; report «Следующие шаги» п. 2).

Question: can a cheap proxy replace a plan fit (400–870 s) in ranking the council families? Π follows the design's
branch Π and stage I of OpenFE: the margin of the base is fixed, a small CatBoost sees only the candidate columns.

  1. T_fit (2020-01-15..02-02) is cut into a head (the first 14 anchor days) and a tail (the last 5, 01-29..02-02).
     Labels of a head day end at the next midnight, so the tail starts after the last head label.
  2. Base H+r (roles.HPLUS, 274 features; the `plan` recipe: 300 trees, depth 8, lr 0.12, l2 10) on the head train
     pool (council.fit.pool with cap CAP queries, exp.sample_train with neg 50, neg_seed 0), out of fold: 4 folds of
     users (fold = ((user_id * 2654435761) mod 2^64 >> 9) mod 4), fold model k trained on the head rows of the other
     folds, seed 2026 + k. OOF margin (RawFormulaVal) for every head row; for a tail row the margin of the fold model
     of its user (trained on head days and other users only).
  3. 16 proxy fits, one per council column of the plan that is a table: F1..F12 (families) and T1..T4 (twins), from
     council/runs/rees46-2020/prereg-2.json. Π_g = CatBoostClassifier(PROXY) on the head rows with only the columns of
     table g, Pool(baseline = OOF margin).
  4. Tail: every candidate of every query of the 5 tail days (exp.read_day), score_0 = margin, score_g = margin +
     Π_g(raw). Δ_g = mean over tail queries of NDCG@20(score_g) - NDCG@20(score_0) (task1.model.per_query).
  5. Gate (plan): Spearman(Δ_g, β̂_g) over the 16 columns >= 0.6, β̂ from council/runs/rees46-2020/plan-result.json
     (read after the proxies are scored). Descriptive: Spearman with t_g, sign agreement where |β̂_g| >= 0.001,
     bootstrap CI of each Δ_g, seconds per proxy fit against the plan fit.

Reads: days6 and the extra tables (H+r and the 16 council tables) of the T_fit days only; prereg-2.json and
plan-result.json. Never S0, C_val, C_test, the broker or its reads journal; nothing is written to artifacts/task1,
council/runs/rees46-2020 or the council fit journal. Writes artifacts/side/proxy/ and council/runs/side/proxy.json.

Heavy: council.xfer.queue.heavy('side proxy', 'rees46-2020') holds /tmp/tlab-heavy.lock for the whole run and waits
while a REES46 fit, queue, memory or compute process runs (queue.FOREIGN); check() before each of the 20 fits and
each tail day; a foreign heavy process appearing mid-run stops the run (Busy). The REES46 queue does not take the
lock, so the plan's ПРОВЕРКА-HEAVY must precede every REES46 heavy step: lock_holder() is None (the holder
'side proxy' fails it) and
`! pgrep -fl '[c]ouncil/xfer/run.py.*(queue|compute|fit-one)|[c]ouncil\\.(fit|queue|memory)|[c]ouncil[./]side'`;
the last alternative matches only the script path, so run the script form `python -I council/side/proxy.py`,
not `-m`. Listing and mtime of artifacts/xfer and artifacts/task1 are taken once the lock is held and compared
before it is released (exit 3 on a change).

Run as a script (from the repository root):
  TASK1_PERIOD=2020 .venv/bin/python -I council/side/proxy.py --dry
  TASK1_PERIOD=2020 .venv/bin/python -I council/side/proxy.py > /tmp/tlab-side-proxy.log 2>&1
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
if os.environ.setdefault('TASK1_PERIOD', '2020') != '2020':
    raise SystemExit(f"TASK1_PERIOD={os.environ['TASK1_PERIOD']!r}: the proxy runs on REES46 2020")

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402

from council import side as S  # noqa: E402

NAME = 'proxy'
DATASET = 'rees46-2020'
SPAN = 'T_fit'
TAIL_DAYS = 5
FOLDS = 4
CAP = 40000
BASE_SEED = 2026
NEG_SEED = 0
RECIPE = 'plan'
PROXY = dict(iterations=100, depth=6, learning_rate=0.1, l2_leaf_reg=10, random_seed=2026, boost_from_average=False)
COLUMNS = [f'F{k}' for k in range(1, 13)] + [f'T{k}' for k in range(1, 5)]
GATE = 0.6
SIGN_MIN = 0.001
DRAWS = 2000
BOOT_SEED = 2026
FORMAT = 'side-proxy-v1'
PREREG2 = ROOT / 'council' / 'runs' / 'rees46-2020' / 'prereg-2.json'
PLAN_RESULT = ROOT / 'council' / 'runs' / 'rees46-2020' / 'plan-result.json'


# ---------------------------------------------------------------- spec (no data)

def split_days(days: list, tail: int = TAIL_DAYS, before=None) -> tuple[list, list]:
    """Head and tail of a list of anchor days; every day before `before` (the first day of S0)."""
    days = sorted(days)
    if len(days) <= tail + 1:
        raise S.Refused('too few days for a head and a tail')
    if before is not None and days[-1] >= before:
        raise S.Refused(f'{days[-1]} is not before {before}')
    return days[:-tail], days[-tail:]


def tables_of(prereg2: dict) -> dict:
    """Column of the plan -> extra table: F<k> -> council_<card>, T<k> -> council_<card>_tw."""
    from council.agents import table
    out = {f: table(card) for f, card in prereg2['families'].items()}
    out |= {t: table(v['card']) + '_tw' for t, v in prereg2['twins'].items()}
    missing = [c for c in COLUMNS if c not in out]
    if missing:
        raise S.Refused(f'prereg-2 lacks the columns {missing}')
    return {c: out[c] for c in COLUMNS}


def spec(prereg2_path: Path = PREREG2) -> dict:
    from council import roles
    head, tail = split_days(roles.days(SPAN), before=roles.days('S0')[0])
    pre = json.loads(Path(prereg2_path).read_text(encoding='utf-8'))
    cfg = {k: v for k, v in roles.RECIPES[RECIPE].items() if k != 'cap'}
    return {'format': FORMAT, 'dataset': DATASET, 'span': SPAN, 'head': [str(d) for d in head],
            'tail': [str(d) for d in tail], 'cap': CAP, 'folds': FOLDS, 'base_seed': BASE_SEED, 'neg_seed': NEG_SEED,
            'base_recipe': RECIPE, 'base_cfg': cfg, 'base_tables': list(roles.HPLUS),
            'base_features': roles.HPLUS_FEATURES, 'proxy': dict(PROXY), 'columns': COLUMNS,
            'tables': tables_of(pre), 'prereg2_sha256': hashlib.sha256(Path(prereg2_path).read_bytes()).hexdigest(),
            'beta_from': PLAN_RESULT.relative_to(ROOT).as_posix(), 'gate': {'spearman_min': GATE},
            'bootstrap': {'draws': DRAWS, 'seed': BOOT_SEED}, 'days_dir': str(roles.DAYS6)}


def spec_digest(s: dict) -> str:
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- the proxy on frames (data-agnostic)

def folds(user_ids, k: int = FOLDS):
    import numpy as np
    u = np.asarray(user_ids, dtype=np.uint64)
    return (((u * np.uint64(2654435761)) >> np.uint64(9)) % np.uint64(k)).astype(np.int64)


def base_params(cfg: dict, seed: int) -> dict:
    """CatBoostClassifier params of task1.exp.fit for a Logloss cfg, without files."""
    return dict(iterations=cfg['iterations'], depth=cfg['depth'], learning_rate=cfg['lr'], l2_leaf_reg=cfg['l2'],
                random_seed=seed, thread_count=cfg['threads'], verbose=0, loss_function='Logloss',
                allow_writing_files=False)


def _cats(features):
    from task1 import model as M
    return [c for c in M.CAT if c in features]


def oof(head, features: list, cfg: dict, *, k: int = FOLDS, seed: int = BASE_SEED, check_fn=lambda: None):
    """OOF margin of the base on the head rows and the k fold models (fold model j never saw fold j's users)."""
    import numpy as np
    from catboost import CatBoostClassifier, Pool
    f = folds(head['user_id'].to_numpy(), k)
    margin = np.full(len(head), np.nan)
    models, seconds = [], []
    for j in range(k):
        check_fn()
        t = time.monotonic()
        train = f != j
        if not train.any() or train.all():
            raise S.Refused(f'fold {j} is empty or holds every user')
        m = CatBoostClassifier(**base_params(cfg, seed + j))
        m.fit(Pool(head.loc[train, features], head.loc[train, 'label'], cat_features=_cats(features)))
        margin[~train] = m.predict(head.loc[~train, features], prediction_type='RawFormulaVal')
        models.append(m)
        seconds.append(round(time.monotonic() - t, 1))
    if not np.isfinite(margin).all():
        raise S.Refused('OOF margin is not finite')
    return margin, models, seconds


def margin_of(models: list, frame, features: list):
    """Margin of each row by the fold model of its user."""
    import numpy as np
    f = folds(frame['user_id'].to_numpy(), len(models))
    out = np.full(len(frame), np.nan)
    for j, m in enumerate(models):
        sel = f == j
        if sel.any():
            out[sel] = m.predict(frame.loc[sel, features], prediction_type='RawFormulaVal')
    return out


def proxy_fit(head, cols: list, margin, params: dict = PROXY, threads: int = 10):
    """Π_g: a small CatBoost on the columns of g only, boosting from the OOF margin."""
    from catboost import CatBoostClassifier, Pool
    m = CatBoostClassifier(**params, loss_function='Logloss', thread_count=threads, verbose=0,
                           allow_writing_files=False)
    m.fit(Pool(head[cols], head['label'], baseline=margin, cat_features=_cats(cols)))
    return m


def tail_scores(frame, models: list, features: list, proxies: dict):
    """Per query of one tail frame: NDCG@20 of the margin ('base') and of margin + Π_g for each g."""
    import pandas as pd
    from task1 import model as M
    margin = margin_of(models, frame, features)
    res = {'base': M.per_query(frame, margin)['ndcg']}
    for g, (m, cols) in proxies.items():
        res[g] = M.per_query(frame, margin + m.predict(frame[cols], prediction_type='RawFormulaVal'))['ndcg']
    return pd.DataFrame(res)


def bootstrap_mean(x, draws=DRAWS, seed=BOOT_SEED) -> dict:
    import numpy as np
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(draws)])
    lo, hi = (float(v) for v in np.quantile(means, [0.025, 0.975], method='linear'))
    return {'mean': float(x.mean()), 'ci': [lo, hi], 'covers_zero': bool(lo <= 0 <= hi)}


def summarize(per_query, beta: dict, columns=COLUMNS, draws=DRAWS) -> dict:
    """Δ_g with CI, Spearman with β̂ and t, sign agreement, the gate."""
    from scipy import stats
    deltas = {g: bootstrap_mean(per_query[g] - per_query['base'], draws) for g in columns}
    d = [deltas[g]['mean'] for g in columns]
    b = [beta[g]['beta'] for g in columns]
    t = [beta[g]['t'] for g in columns]
    rho = stats.spearmanr(d, b)
    rho_t = stats.spearmanr(d, t)
    big = [g for g in columns if abs(beta[g]['beta']) >= SIGN_MIN]
    agree = [g for g in big if (deltas[g]['mean'] > 0) == (beta[g]['beta'] > 0)]
    r = float(rho.statistic)
    passed = bool(r == r and r >= GATE)
    return {'queries': int(len(per_query)), 'delta': deltas, 'beta': {g: beta[g]['beta'] for g in columns},
            'spearman_beta': {'rho': r, 'p': float(rho.pvalue)},
            'spearman_t': {'rho': float(rho_t.statistic), 'p': float(rho_t.pvalue)},
            'sign': {'min_abs_beta': SIGN_MIN, 'columns': big, 'agree': agree},
            'gate': {'rule': f'Spearman(delta, beta) >= {GATE}', 'passed': passed},
            'decision': 'Π проходит гейт' if passed else 'Π не проходит гейт'}


def run_core(head, features: list, table_cols: dict, tail_frames, cfg: dict, *, check_fn=lambda: None,
             proxy_params: dict = PROXY, k: int = FOLDS):
    """OOF base, 16 proxies, tail scores. tail_frames: an iterable of (day, frame) loaded lazily.
    Returns (per-query frame with 'day', timings)."""
    import pandas as pd
    margin, models, base_seconds = oof(head, features, cfg, k=k, check_fn=check_fn)
    proxies, proxy_seconds = {}, {}
    for g, cols in table_cols.items():
        check_fn()
        t = time.monotonic()
        proxies[g] = (proxy_fit(head, cols, margin, proxy_params, cfg['threads']), cols)
        proxy_seconds[g] = round(time.monotonic() - t, 1)
    parts, tail_seconds = [], {}
    for day, frame in tail_frames:
        check_fn()
        t = time.monotonic()
        part = tail_scores(frame, models, features, proxies)
        part['day'] = str(day)
        parts.append(part)
        tail_seconds[str(day)] = round(time.monotonic() - t, 1)
        del frame
    per_query = pd.concat(parts).rename_axis('qid').reset_index()
    return per_query, {'base_folds': base_seconds, 'proxies': proxy_seconds, 'tail_days': tail_seconds}


# ---------------------------------------------------------------- data (real run only)

def join_tables(df, tables: list):
    """exp.with_extra table by table; returns the frame and table -> its new columns."""
    from task1 import exp
    of = {}
    for t in tables:
        before = set(df.columns)
        df = exp.with_extra(df, [t])
        of[t] = [c for c in df.columns if c not in before]
        if not of[t]:
            raise S.Refused(f'table {t} added no column')
    return df, of


def check_days(s: dict) -> None:
    from council import roles
    span = {str(d) for d in roles.days(SPAN)}
    first_s0 = str(roles.days('S0')[0])
    for d in s['head'] + s['tail']:
        if d not in span or d >= first_s0:
            raise S.Refused(f'{d} is not a T_fit day before S0')
    if max(s['head']) >= min(s['tail']):
        raise S.Refused('the head must end before the tail')
    if 'sealed' in Path(s['days_dir']).resolve().as_posix():
        raise S.Refused('the days directory lies in a closed (label-holding) directory')


def load_head(s: dict):
    """The head train pool with H+r and the 16 council tables; the H+r feature list; g -> its columns."""
    from datetime import date
    from council import fit as CF
    from council import roles
    from task1 import exp
    from task1 import model as M
    cfg = exp.DEFAULT | s['base_cfg'] | {'seed': s['base_seed'], 'neg_seed': s['neg_seed'], 'extra': []}
    head = [date.fromisoformat(d) for d in s['head']]
    df = exp.sample_train(CF.pool(head, roles.DAYS6, s['cap']), cfg)
    df, _ = join_tables(df, s['base_tables'])
    features = M.base_features(df)
    if len(features) != s['base_features']:
        raise S.Refused(f"H+r has {len(features)} features, expected {s['base_features']}")
    df, of = join_tables(df, [s['tables'][g] for g in s['columns']])
    cols = {g: of[s['tables'][g]] for g in s['columns']}
    return df.reset_index(drop=True), features, cols, cfg


def tail_frames(s: dict, tables: list):
    from datetime import date
    from council import roles
    from task1 import exp
    for d in s['tail']:
        df = exp.read_day(date.fromisoformat(d), roles.DAYS6)
        df, _ = join_tables(df, tables)
        yield d, df.reset_index(drop=True)


def read_beta(path: Path = PLAN_RESULT) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))['beta']


# ---------------------------------------------------------------- run

def run(out: S.Out, s: dict, *, wait=True, heavy_kw=None, protected=S.PROTECTED, check_fn=S.check,
        proxy_params: dict = PROXY) -> dict:
    check_days(s)
    t0 = time.time()
    with S.heavy_step(NAME, DATASET, out, wait=wait, **(heavy_kw or {})):
        before = S.protected_snapshot(protected)       # under the lock: a REES46 step waited for may have written
        check_fn()
        t = time.monotonic()
        head, features, cols, cfg = load_head(s)
        load_seconds = round(time.monotonic() - t, 1)
        head_rows, head_queries = len(head), int(head['qid'].nunique())
        tables = s['base_tables'] + [s['tables'][g] for g in s['columns']]
        per_query, seconds = run_core(head, features, cols, tail_frames(s, tables), cfg, check_fn=check_fn,
                                      proxy_params=proxy_params)
        del head
        seconds['load_head'] = load_seconds
        out.write_frame(per_query, 'per_query.parquet')
        verdict = S.protected_verdict(before, protected)
    summary = summarize(per_query, read_beta(), s['columns'])
    result = {'format': FORMAT, 'status': 'ok' if verdict['unchanged'] else 'refused', 'spec': s,
              'spec_digest': spec_digest(s), 'head_rows': head_rows, 'head_queries': head_queries,
              'columns_per_table': {g: len(c) for g, c in cols.items()}, **summary, 'seconds': seconds,
              'seconds_total': round(time.time() - t0, 1), 'peak_rss_gb': S.peak_rss_gb(), 'protected': verdict,
              'code': S.code_identity(__file__), 'finished': S.now()}
    out.write_json(result, f'{NAME}.json', runs=True)
    if not verdict['unchanged']:
        raise SystemExit(S.PROTECTED_EXIT)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description='H6: cheap proxy Π on the T_fit tail of REES46 2020 '
                                             '(council/runs/side/proxy.md)')
    ap.add_argument('--dry', action='store_true', help='print the spec and paths; read no data, take no lock')
    ap.add_argument('--no-wait', action='store_true', help='refuse instead of waiting for the heavy lock')
    args = ap.parse_args(argv)
    s = spec()
    check_days(s)
    out = S.Out(NAME)
    if args.dry:
        S.print_json({'dry': True, 'spec': s, 'spec_digest': spec_digest(s), 'heavy': f'side {NAME}',
                      'fits': {'base_oof': FOLDS, 'proxies': len(COLUMNS)},
                      'outputs': [str(out.path('per_query.parquet')), str(out.path(f'{NAME}.json', runs=True))],
                      'journal': str(out.journal), 'protected': [str(p) for p in S.PROTECTED],
                      'beta_exists': PLAN_RESULT.exists()})
        return 0
    res = run(out, s, wait=not args.no_wait)
    S.print_json({k: res[k] for k in ('status', 'decision', 'spearman_beta', 'seconds_total', 'peak_rss_gb')})
    return 0


if __name__ == '__main__':
    sys.exit(main())
