"""Night experiment harness: run a queue of model configurations on one loaded copy of the data.

Validation is split into halves by user: A (selection) and B (one confirmation per arm). Every run
stores per-query NDCG/Recall for the whole validation but logs and prints half A only; `compare` reports
paired differences on a half, and half B is read only for the frozen arms.

Config keys (defaults in DEFAULT): loss, iterations, depth, lr, l2, seed, neg (sampled negatives per
query), neg_mode ('random' | 'hard': half of the negatives are the top by cf_cv_cond_tdecay20, the rest
random), neg_seed, half_life (days; recency weight of train anchors, None = equal), train_frac (share
of train queries, for cheap proxy fits), drop (feature prefix groups), extra (feature tables from
artifacts/task1/v2/extra), days (directory of day tables).

Run: .venv/bin/python -m task1.exp queue.json   (a JSON list of {"name": ..., **config})
"""
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRanker, Pool

from task1 import model as M

OUT = M.ROOT / 'artifacts/task1/v2/exp'
DEFAULT = dict(loss='Logloss', iterations=500, depth=6, lr=0.08, l2=10, seed=2026, neg=50, neg_mode='random',
               neg_seed=0, half_life=None, train_frac=1.0, drop=[], extra=[], days=str(M.DAYS), threads=10)
_cache = {}


def half(user_id):
    """'A' or 'B' by a multiplicative hash of the user id."""
    return np.where(((np.asarray(user_id, dtype=np.uint64) * np.uint64(2654435761)) >> np.uint64(7)) % np.uint64(2) == 0, 'A', 'B')


def _read(split, days_dir):
    """Validation: every candidate. Train: a pool per query with all positives, 100 random negatives
    (rank rr) and the 30 hardest by cf_cv_cond_tdecay20 (rank hr); configs sample from it."""
    key = (split, days_dir)
    if key in _cache:
        return _cache[key]
    if len(_cache) >= 2:
        _cache.clear()
    files = [str(Path(days_dir) / f'{d}.parquet') for d in M.days(split)]
    cols = duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{files[0]}')").df().column_name.tolist()
    hard = 'cf_cv_cond_tdecay20' if 'cf_cv_cond_tdecay20' in cols else 'cf_cv_cond_tdecay'
    pool = 'WHERE label = 1 OR rr <= 100 OR hr <= 30' if split == 'train' else ''
    df = duckdb.sql(f"""SELECT * FROM (
      SELECT d.*, d.anchor::VARCHAR || ':' || d.user_id::VARCHAR qid,
        row_number() OVER (PARTITION BY d.anchor, d.user_id ORDER BY hash(d.product_id, d.user_id, 7)) rr,
        row_number() OVER (PARTITION BY d.anchor, d.user_id ORDER BY d.{hard} DESC, d.product_id) hr
      FROM read_parquet({files}) d) {pool}
      ORDER BY qid, product_id""").df()
    for c in df.columns:
        if df[c].dtype == np.float64:
            df[c] = df[c].astype(np.float32)
    _cache[key] = df
    return df


def with_extra(df, extra):
    """Left-join sandbox feature tables artifacts/task1/v2/extra/<name>/<day>.parquet by (anchor, keys)."""
    for name in extra:
        x = duckdb.sql(f"""SELECT * EXCLUDE (filename),
            regexp_extract(filename, '(\\d{{4}}-\\d{{2}}-\\d{{2}})\\.parquet$', 1)::DATE anchor
            FROM read_parquet('{M.EXTRA / name}/[0-9]*.parquet', filename=true)""").df()
        keys = ['anchor'] + [c for c in ('user_id', 'product_id') if c in x.columns]
        x['anchor'] = pd.to_datetime(x.anchor).astype(df.anchor.dtype)
        missing = set(df.anchor.unique()) - set(x.anchor.unique())
        if missing:
            raise ValueError(f'extra {name} lacks days {sorted(missing)[:3]}...')
        for c in x.columns:
            if x[c].dtype == np.float64:
                x[c] = x[c].astype(np.float32)
        n = len(df)
        df = df.merge(x, on=keys, how='left')
        if len(df) != n:
            raise ValueError(f'extra {name} has duplicate keys: {n} -> {len(df)} rows')
    return df


def sample_train(df, cfg):
    rng = np.random.default_rng(cfg['neg_seed'])
    if cfg['train_frac'] < 1:
        q = df.qid.unique()
        keep = q[(pd.util.hash_array(q.astype(object)) % 1000) < cfg['train_frac'] * 1000]
        df = df[df.qid.isin(keep)]
    if cfg['neg'] > 100 or (cfg['neg_mode'] == 'hard' and cfg['neg'] // 2 > 30):
        raise ValueError('the train pool holds 100 random and 30 hard negatives per query')
    r = np.where(df.rr.to_numpy() <= 100, rng.random(len(df)), np.inf)
    if cfg['neg_mode'] == 'hard':
        r = np.where(df.hr.to_numpy() <= cfg['neg'] // 2, -0.5, r)
    r = np.where(df.label.to_numpy() == 1, -1.0, r)
    k = pd.Series(r, index=df.index).groupby(df.qid.to_numpy()).rank(method='first')
    keep = (k <= cfg['neg'] + df.groupby('qid').label.transform('sum')) & np.isfinite(r)
    return df[keep.to_numpy()]


def fit(train, features, cfg):
    params = dict(iterations=cfg['iterations'], depth=cfg['depth'], learning_rate=cfg['lr'],
                  l2_leaf_reg=cfg['l2'], random_seed=cfg['seed'], thread_count=cfg['threads'], verbose=0)
    weight = None
    if cfg['half_life']:
        age = (train.anchor.max() - train.anchor).dt.days.to_numpy()
        weight = np.power(0.5, age / cfg['half_life'])
    ranking = cfg['loss'] != 'Logloss'
    pool = Pool(train[features], train.label, cat_features=[c for c in M.CAT if c in features],
                group_id=train.qid if ranking else None,
                weight=None if ranking else weight, group_weight=weight if ranking else None)
    m = (CatBoostRanker(loss_function=cfg['loss'], **params) if ranking
         else CatBoostClassifier(loss_function='Logloss', **params))
    m.fit(pool)
    return m


def run(name, **over):
    cfg = DEFAULT | over
    t0 = time.time()
    train = with_extra(sample_train(_read('train', cfg['days']), cfg), cfg['extra'])
    val = with_extra(_read('val', cfg['days']), cfg['extra'])
    features = M.base_features(train, cfg['drop'])
    t1 = time.time()
    m = fit(train, features, cfg)
    t2 = time.time()
    score = M.predict(m, val, features)
    t3 = time.time()
    pq = M.per_query(val, score)
    pp = M.per_query(val, score, purchase=True)
    users = val.drop_duplicates('qid').set_index('qid').user_id
    pq['half'] = half(users.reindex(pq.index).to_numpy())
    res = pq.join(pp.add_prefix('purchase_'), how='left').reset_index()
    OUT.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY (SELECT * FROM res) TO '{OUT / name}.parquet' (FORMAT PARQUET)")
    a = res[res.half == 'A']  # selection sees half A only; half B is read by `compare(..., on='B')`
    rec = {'name': name, 'cfg': cfg, 'features': len(features), 'train_rows': len(train),
           'ndcg_A': round(float(a.ndcg.mean()), 6), 'recall_A': round(float(a.recall.mean()), 6),
           'purchase_ndcg_A': round(float(a.purchase_ndcg.mean()), 6),
           'seconds': {'prepare': round(t1 - t0), 'fit': round(t2 - t1), 'predict': round(t3 - t2)}}
    with (OUT / 'runs.jsonl').open('a') as f:
        f.write(json.dumps(rec) + '\n')
    print(json.dumps({k: rec[k] for k in ('name', 'ndcg_A', 'recall_A', 'purchase_ndcg_A', 'seconds')}), flush=True)
    return rec


def metrics(name):
    return duckdb.sql(f"SELECT * FROM '{OUT / name}.parquet'").df().set_index('qid')


def compare(ref, new, on='A', metric='ndcg'):
    """Paired bootstrap of new - ref over the queries of one half ('A', 'B' or 'all')."""
    a, b = metrics(ref), metrics(new)
    idx = a.index if on == 'all' else a.index[a.half == on]
    d, lo, hi = M.bootstrap_diff(a.loc[idx, metric], b.loc[idx, metric])
    return {'ref': ref, 'new': new, 'half': on, 'd': round(d, 5), 'ci': [round(lo, 5), round(hi, 5)]}


def main():
    queue = json.loads(Path(sys.argv[1]).read_text())
    for item in queue:
        item = dict(item)
        run(item.pop('name'), **item)


if __name__ == '__main__':
    main()
