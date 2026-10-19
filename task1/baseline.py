"""Validate the hand-made baseline: heuristics, the full CatBoost model and leave-one-group-out ablations.

Train on the train split (50 sampled negatives per query), score every candidate of the validation split,
and compare per-query NDCG@20 with a paired bootstrap. Per-query metrics go to
artifacts/task1/v2/val/<name>.parquet for later comparisons (automatic features, other models).

Run: .venv/bin/python -m task1.baseline [--ablate]
"""
import argparse
import json
import time
from pathlib import Path

import duckdb

from task1.model import GROUPS, ROOT, base_features, bootstrap_diff, fit, load, per_query, predict, summary

OUT = ROOT / 'artifacts/task1/v2/val'
HEURISTICS = {  # higher score ranks first
    'pop': lambda d: -d.s_pop_rank.fillna(1e6) - d.i_actor_share_7d.fillna(0) * 1e-3,
    'coview': lambda d: d.cf_cv_cond_tdecay,
    'user_category': lambda d: d.uc_share_hl1d + 1e-3 * d.i_actor_share_7d.fillna(0),
}


def report(name, m, mp, ref=None, extra=None):
    row = {'name': name} | summary(m) | {'purchase_ndcg': round(float(mp.ndcg.mean()), 6)}
    if ref is not None:
        d, lo, hi = bootstrap_diff(ref.ndcg, m.ndcg.reindex(ref.index))
        row['d_ndcg_vs_full'] = [round(d, 5), round(lo, 5), round(hi, 5)]
    print(json.dumps(row | (extra or {})), flush=True)
    out = m.join(mp.add_prefix('purchase_'), how='left').reset_index()
    duckdb.sql(f"COPY (SELECT * FROM out) TO '{OUT / name}.parquet' (FORMAT PARQUET)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ablate', action='store_true')
    ap.add_argument('--iterations', type=int, default=500)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    train = load('train', neg_per_query=50)
    val = load('val')
    print(json.dumps({'train_rows': len(train), 'train_queries': train.qid.nunique(), 'val_rows': len(val),
                      'val_queries': val.qid.nunique(), 'load_s': round(time.time() - t0)}), flush=True)
    for name, h in HEURISTICS.items():
        s = h(val).to_numpy(dtype=float)
        report(f'h_{name}', per_query(val, s), per_query(val, s, purchase=True))

    features = base_features(train)
    t0 = time.time()
    model = fit(train, features, iterations=args.iterations)
    fit_s = time.time() - t0
    score = predict(model, val, features)
    full = per_query(val, score)
    report('full', full, per_query(val, score, purchase=True),
           extra={'features': len(features), 'fit_s': round(fit_s)})
    imp = sorted(zip(model.get_feature_importance(), features), reverse=True)
    print(json.dumps({'importance_top25': [(f, round(float(v), 2)) for v, f in imp[:25]]}), flush=True)
    if args.ablate:
        for g in GROUPS:
            fs = base_features(train, [g])
            if len(fs) == len(features):
                continue
            model = fit(train, fs, iterations=args.iterations)
            score = predict(model, val, fs)
            report(f'minus_{g.rstrip("_")}', per_query(val, score), per_query(val, score, purchase=True),
                   ref=full, extra={'features': len(fs)})


if __name__ == '__main__':
    main()
