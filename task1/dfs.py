"""Deterministic feature generation (DFS-style grid) as the second automation arm.

Entities: product, its category, its brand, the user. For every entity, window (1, 3, 7, 14 days before t)
and event type (view, cart, purchase): log(1 + events) and log(1 + distinct users), plus smoothed
cart-per-view and purchase-per-view rates of distinct users. 32 columns per entity, 128 in total. Each
entity is one sandbox query (task1.extra), so the same isolation and leak guarantees hold as for the agent.
Pair-level user x category aggregates are not generated: in the sandbox they have to be enumerated for
every active user (~0.5M) instead of the ranked ones, which exceeds the time limit.

Selection never reads validation: a CatBoost fit on train anchors up to 11-03 with base + the generated
item, category and brand columns, LossFunctionChange on train anchors 11-04..11-07, the top --k with positive
importance go to the extra tables `dfs_<entity>_top` (list frozen in task1/runs/dfs-select.json). User-level
columns are generated but not selectable: constant within a query, they cannot reorder candidates, yet
Logloss importance credits them for predicting the number of positives; most are also binary (distinct
users of one user). Validation half A then sees exactly two fits (two seeds).

Run: .venv/bin/python -m task1.dfs --compute
     .venv/bin/python -m task1.dfs --select 20 --config '{...frozen base config...}'
"""
import argparse
import json
import time

import duckdb
import pandas as pd
from catboost import Pool

from task1 import exp
from task1 import model as M
from task1.extra import compute

WINDOWS = (1, 3, 7, 14)
EVENTS = ('view', 'cart', 'purchase')
ENTITIES = {'p': 'product_id', 'c': 'category_id', 'b': 'brand', 'u': 'user_id'}


def aggregates(prefix):
    cols = []
    for d in WINDOWS:
        f = f"event_time >= TIMESTAMP '{{t}}' - INTERVAL {d} DAY"
        for ev in EVENTS:
            cols.append(f"ln(1 + count(*) FILTER (event_type = '{ev}' AND {f})) f_x_dfs_{prefix}_{ev}_n_{d}d")
            cols.append(f"ln(1 + count(DISTINCT user_id) FILTER (event_type = '{ev}' AND {f})) f_x_dfs_{prefix}_{ev}_u_{d}d")
        users = lambda ev: f"count(DISTINCT user_id) FILTER (event_type = '{ev}' AND {f})"
        cols.append(f"({users('cart')} + 1.0) / ({users('view')} + 20.0) f_x_dfs_{prefix}_cart_per_view_{d}d")
        cols.append(f"({users('purchase')} + 1.0) / ({users('view')} + 20.0) f_x_dfs_{prefix}_buy_per_view_{d}d")
    return ',\n  '.join(cols)


def queries():
    w = "w AS (SELECT * FROM hist WHERE event_time >= TIMESTAMP '{t}' - INTERVAL 14 DAY)"
    pe = lambda col: (f"pe AS (SELECT product_id, arg_max({col}, (event_time, {col})) e FROM w "
                      f"WHERE {col} IS NOT NULL GROUP BY 1)")
    out = {'dfs_p': f"WITH {w}\nSELECT product_id,\n  {aggregates('p')}\nFROM w GROUP BY 1",
           'dfs_u': f"WITH {w}\nSELECT user_id,\n  {aggregates('u')}\nFROM w WHERE user_id IN (SELECT user_id FROM active_users) GROUP BY 1"}
    for k in ('c', 'b'):
        col = ENTITIES[k]
        out[f'dfs_{k}'] = (f"WITH {w}, {pe(col)},\n ea AS (SELECT {col} e,\n  {aggregates(k)}\nFROM w WHERE {col} IS NOT NULL GROUP BY 1)\n"
                           f"SELECT pe.product_id, ea.* EXCLUDE (e) FROM pe JOIN ea USING(e)")
    return out


SELECTABLE = ('dfs_p', 'dfs_c', 'dfs_b')  # dfs_u is constant within a query: Logloss importance credits it
SELECTION = M.ROOT / 'task1/runs/dfs-select.json'   # for predicting how many positives a query has


def select(k, cfg):
    """Pick the top-k generated columns on train only and materialise them; the list is frozen in SELECTION."""
    cfg = exp.DEFAULT | cfg
    tr = exp.with_extra(exp.sample_train(exp._read('train', cfg['days']), cfg), SELECTABLE)
    gen = [c for c in tr.columns if c.startswith('f_x_dfs_')]
    feats = M.base_features(tr, cfg['drop'])
    cut = pd.Timestamp('2019-11-04')
    fit_part, hold = tr[tr.anchor < cut], tr[tr.anchor >= cut]
    t0 = time.time()
    m = exp.fit(fit_part, feats, cfg)
    hp = Pool(hold[feats], hold.label, cat_features=[c for c in M.CAT if c in feats],
              group_id=hold.qid if cfg['loss'] != 'Logloss' else None)
    imp = dict(zip(feats, m.get_feature_importance(hp, type='LossFunctionChange')))
    top = [c for c in sorted(gen, key=lambda c: -imp[c]) if imp[c] > 0][:k]
    res = {'k': k, 'generated': len(gen), 'selected': top, 'select_s': round(time.time() - t0),
           'importance': {c: round(float(imp[c]), 6) for c in top}, 'config': cfg}
    res['tables'] = materialize(top)
    SELECTION.write_text(json.dumps(res, indent=1) + '\n')
    return res


def materialize(top=None):
    """Copy the selected columns of every computed day (train, val and, once computed, test) into
    EXTRA/<name>_top. Test days: `python -m task1.extra dfs_p dfs_c dfs_b --splits test`, then --materialize."""
    top = top or json.loads(SELECTION.read_text())['selected']
    tables = []
    for n in SELECTABLE:  # one table per entity
        src = M.EXTRA / n
        cols = [c for c in duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{src}/[0-9]*.parquet')").df().column_name
                if c in top]
        sub = M.EXTRA / f'{n}_top'
        for f in sub.glob('*.parquet'):
            f.unlink()
        if not cols:
            continue
        sub.mkdir(parents=True, exist_ok=True)
        for f in src.glob('[0-9]*.parquet'):
            duckdb.sql(f"COPY (SELECT product_id, {', '.join(cols)} FROM read_parquet('{f}')) TO '{sub / f.name}' (FORMAT PARQUET)")
        tables.append(f'{n}_top')
    return tables


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--compute', action='store_true')
    ap.add_argument('--select', type=int)
    ap.add_argument('--materialize', action='store_true')
    ap.add_argument('--config', default='{"days": "artifacts/task1/v2/days6"}')
    ap.add_argument('--threads', type=int, default=8)
    args = ap.parse_args()
    cfg = json.loads(args.config)
    if args.compute:
        for name, sql in queries().items():
            t0 = time.time()
            cols = compute(name, sql, ('train', 'val'), args.threads, days_dir=M.ROOT / cfg['days'])
            print(json.dumps({'name': name, 'columns': len(cols), 'seconds': round(time.time() - t0)}), flush=True)
    if args.select:
        print(json.dumps(select(args.select, cfg)), flush=True)
    if args.materialize:
        print(materialize())


if __name__ == '__main__':
    main()
