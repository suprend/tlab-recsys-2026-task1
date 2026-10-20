"""The one test command: refit every frozen arm on train + validation and score the test days once.

task1/runs/final.json (written at the end of the night run, before any test label is read):
  {"reference": "hand", "seeds": [[2026, 0], [7, 1]],
   "arms": [{"name": "hand", "config": {...exp config...}}, {"name": "agent", "config": {..., "extra": [...]}}, ...]}
For every arm and seed pair (seed, neg_seed) the model is fit on the refit split (anchors 10-15..11-13; labels
of 11-13 end at 11-14 00:00) and scores every candidate of the evaluation split. Per-query metrics are
averaged over seeds; each arm is compared with the reference by a paired bootstrap over queries.
Extra feature tables are computed for the evaluation days first (sandbox, task1.extra), DFS tables are
re-materialised from the frozen column list.

Check the whole path without test: .venv/bin/python -m task1.final --eval val   (fit on train, score val)
Test, once:                         .venv/bin/python -m task1.final --eval test
"""
import argparse
import json
import time
from pathlib import Path

import duckdb
import pandas as pd

from task1 import dfs, exp
from task1 import model as M
from task1.extra import compute

FINAL = M.ROOT / 'task1/runs/final.json'
OUT = M.ROOT / 'artifacts/task1/v2/final'


def ensure_extra(names, split, days_dir):
    """Compute missing evaluation days of the arms' extra tables."""
    need = set()
    for n in names:
        miss = [d for d in M.days(split) if not (M.EXTRA / n / f'{d}.parquet').exists()]
        if not miss:
            continue
        if n.startswith('dfs_') and n.endswith('_top'):
            need.add(n)
            continue
        compute(n, (M.EXTRA / n / 'feature.sql').read_text(), days=miss, days_dir=days_dir)
    if need:
        for n in dfs.SELECTABLE:
            miss = [d for d in M.days(split) if not (M.EXTRA / n / f'{d}.parquet').exists()]
            if miss:
                compute(n, dfs.queries()[n], days=miss, days_dir=days_dir)
        dfs.materialize()


def read_day(d, days_dir, extra):
    """All candidates of one anchor day with the arm's extra columns (queries never cross days)."""
    df = duckdb.sql(f"""SELECT *, anchor::VARCHAR || ':' || user_id::VARCHAR qid
                        FROM read_parquet('{days_dir}/{d}.parquet') ORDER BY qid, product_id""").df()
    for c in df.columns:
        if df[c].dtype == 'float64':
            df[c] = df[c].astype('float32')
    return exp.with_extra(df, extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eval', choices=['val', 'test'], required=True)
    ap.add_argument('--spec', default=str(FINAL), help='another spec, for a quick check of the path on val')
    args = ap.parse_args()
    spec = json.loads(Path(args.spec).read_text())
    if args.eval == 'test' and Path(args.spec) != FINAL:
        raise SystemExit('test is evaluated only with the frozen task1/runs/final.json')
    started = OUT / f'{args.eval}.started'
    if args.eval == 'test' and started.exists():
        raise SystemExit(f'test was already evaluated (or started): {started}')
    uses_dfs = any(n.startswith('dfs_') for a in spec['arms'] for n in a['config'].get('extra', []))
    if uses_dfs and json.loads(dfs.SELECTION.read_text())['selected'] != spec.get('dfs_selected'):
        raise SystemExit('task1/runs/dfs-select.json differs from the DFS columns frozen in final.json')
    fit_split = 'refit' if args.eval == 'test' else 'train'
    OUT.mkdir(parents=True, exist_ok=True)
    started.write_text(time.strftime('%Y-%m-%d %H:%M:%S') + '\n')
    per_arm, summary = {}, []
    for arm in spec['arms']:
        cfg = exp.DEFAULT | arm['config']
        cfg['days'] = str(M.ROOT / cfg['days'])
        ensure_extra(cfg['extra'], args.eval, cfg['days'])
        models, t0 = [], time.time()
        for seed, neg_seed in spec['seeds']:
            c = cfg | {'seed': seed, 'neg_seed': neg_seed}
            tr = exp.with_extra(exp.sample_train(exp._read(fit_split, c['days']), c), c['extra'])
            features = M.base_features(tr, c['drop'])
            models.append(exp.fit(tr, features, c))
            del tr
        runs = [[] for _ in models]
        for d in M.days(args.eval):
            ev = read_day(d, cfg['days'], cfg['extra'])
            for i, m in enumerate(models):
                score = M.predict(m, ev, features)
                runs[i].append(M.per_query(ev, score).join(
                    M.per_query(ev, score, purchase=True).add_prefix('purchase_'), how='left'))
        runs = [pd.concat(r) for r in runs]
        mean = sum(runs) / len(runs)
        per_arm[arm['name']] = mean
        name = f"{args.eval}_{arm['name']}"
        res = mean.reset_index()
        duckdb.sql(f"COPY (SELECT * FROM res) TO '{OUT / name}.parquet' (FORMAT PARQUET)")
        summary.append({'arm': arm['name'], 'features': len(features), 'queries': len(mean),
                        'ndcg': round(float(mean.ndcg.mean()), 5), 'recall': round(float(mean.recall.mean()), 5),
                        'purchase_ndcg': round(float(mean.purchase_ndcg.mean()), 5),
                        'seeds': [round(float(r.ndcg.mean()), 5) for r in runs], 'seconds': round(time.time() - t0)})
        print(json.dumps(summary[-1]), flush=True)
    ref = per_arm[spec['reference']]
    for s in summary:
        if s['arm'] == spec['reference']:
            continue
        b = per_arm[s['arm']]
        for metric in ('ndcg', 'purchase_ndcg'):
            idx = ref.index[ref[metric].notna().to_numpy()]
            d, lo, hi = M.bootstrap_diff(ref.loc[idx, metric], b.loc[idx, metric])
            s[f'd_{metric}_vs_{spec["reference"]}'] = [round(d, 5), round(lo, 5), round(hi, 5)]
    (OUT / f'{args.eval}.json').write_text(json.dumps({'spec': spec, 'results': summary}, indent=1) + '\n')
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == '__main__':
    main()
