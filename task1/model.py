"""Train CatBoost on day tables and evaluate NDCG@20 / Recall@20 against the full target set.

Splits: train anchors Oct 8-20, validation Oct 22-25 (model fit on train only),
test Oct 26-31 (final model refit on Oct 8-25 with settings chosen on validation;
labels of Oct 25 end at Oct 26 00:00, so the refit sees nothing from the test window).
"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRanker, Pool

ROOT = Path(__file__).resolve().parents[1]
DAYS = ROOT / 'artifacts/task1/days'
EXTRA = ROOT / 'artifacts/task1/extra'
K = 20
SPLITS = {
    'train': ('2019-10-08', '2019-10-20'),
    'val': ('2019-10-22', '2019-10-25'),
    'refit': ('2019-10-08', '2019-10-25'),
    'test': ('2019-10-26', '2019-10-31'),
}


def days(split):
    a, b = (date.fromisoformat(x) for x in SPLITS[split])
    return [a + timedelta(n) for n in range((b - a).days + 1)]


def base_features(df):
    return [c for c in df.columns if c.startswith('f_')]


def load(split, extra=(), neg_per_query=None, seed=0):
    """Load day tables; optionally join extra feature tables (artifacts/task1/extra/<name>/<day>.parquet)."""
    parts = []
    for d in days(split):
        df = duckdb.read_parquet(str(DAYS / f'{d}.parquet')).df()
        for name in extra:
            x = duckdb.read_parquet(str(EXTRA / name / f'{d}.parquet')).df()
            df = df.merge(x, on=[c for c in ('user_id', 'product_id') if c in x.columns], how='left')
        if neg_per_query:
            rng = np.random.default_rng(seed + d.toordinal())
            r = rng.random(len(df))
            df['_r'] = np.where(df.label == 1, -1.0, r)
            df = df[df.groupby('user_id')['_r'].rank(method='first') <= neg_per_query + df.groupby('user_id').label.transform('sum')]
            df = df.drop(columns='_r')
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df['qid'] = df.anchor.astype(str) + ':' + df.user_id.astype(str)
    return df.sort_values(['qid', 'product_id'], kind='stable').reset_index(drop=True)


def fit(df, features, loss='Logloss', iterations=500, depth=6, lr=0.08, l2=10, seed=2026, threads=10, verbose=0):
    params = dict(iterations=iterations, depth=depth, learning_rate=lr, l2_leaf_reg=l2,
                  random_seed=seed, thread_count=threads, verbose=verbose)
    pool = Pool(df[features], df.label, group_id=df.qid if loss != 'Logloss' else None)
    model = (CatBoostClassifier(loss_function='Logloss', **params) if loss == 'Logloss'
             else CatBoostRanker(loss_function=loss, **params))
    model.fit(pool)
    return model


def predict(model, df, features):
    if isinstance(model, CatBoostClassifier):
        return model.predict_proba(df[features])[:, 1]
    return model.predict(df[features])


IDCG = np.cumsum(1 / np.log2(np.arange(2, K + 2)))


def per_query(df, score):
    """NDCG@K and Recall@K per query; targets outside candidates count via n_targets."""
    d = pd.DataFrame({'qid': df.qid.values, 'pid': df.product_id.values, 's': score,
                      'y': df.label.values, 'n': df.n_targets.values})
    d = d.sort_values(['qid', 's', 'pid'], ascending=[True, False, True], kind='stable')
    d['rank'] = d.groupby('qid').cumcount()
    top = d[d['rank'] < K]
    g = top.assign(gain=top.y / np.log2(top['rank'] + 2)).groupby('qid').agg(dcg=('gain', 'sum'), hits=('y', 'sum'), n=('n', 'first'))
    g['ndcg'] = g.dcg / IDCG[np.minimum(g.n, K) - 1]
    g['recall'] = g.hits / g.n
    return g[['ndcg', 'recall']]


def bootstrap_diff(a, b, n=2000, seed=2026):
    """Paired bootstrap over queries for mean(b - a)."""
    diff = (b - a).to_numpy()
    rng = np.random.default_rng(seed)
    means = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(n)])
    return diff.mean(), np.percentile(means, 2.5), np.percentile(means, 97.5)


def summary(m):
    return {k: round(float(v), 6) for k, v in m.mean().items()} | {'queries': len(m)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eval', choices=['val', 'test'], default='val')
    ap.add_argument('--extra', nargs='*', default=[])
    ap.add_argument('--loss', default='Logloss')
    ap.add_argument('--iterations', type=int, default=500)
    ap.add_argument('--depth', type=int, default=6)
    ap.add_argument('--lr', type=float, default=0.08)
    ap.add_argument('--neg', type=int, default=50)
    args = ap.parse_args()
    train = load('train' if args.eval == 'val' else 'refit', args.extra, args.neg)
    test = load(args.eval, args.extra)
    features = base_features(train)
    model = fit(train, features, args.loss, args.iterations, args.depth, args.lr)
    m = per_query(test, predict(model, test, features))
    print(json.dumps(summary(m) | {'features': len(features), 'train_rows': len(train)}))


if __name__ == '__main__':
    main()
