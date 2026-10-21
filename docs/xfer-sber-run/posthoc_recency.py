"""Post-hoc on dev (val-2020-08-19), descriptive: agent gain by user recency and by Kaggle test membership.

Run from the repo root: .venv/bin/python -I docs/xfer-sber-run/posthoc_recency.py > docs/xfer-sber-run/posthoc-recency.json
Reads only the dev fit metrics on val, the val frame and the unlabeled kaggle frame and fallback ids."""
import json, sys
sys.path.insert(0, 'scripts')
import duckdb
import xfer_common as xc

F = 'artifacts/xfer/sber/fits/dev/{}/metrics-val-2020-08-19.parquet'
VAL = 'artifacts/xfer/sber/collections/val-2020-08-19/frame.parquet'
KAG = 'artifacts/xfer/sber/collections/kaggle-2020-09-17/frame.parquet'
FALLBACK = 'artifacts/xfer/sber/collections/kaggle-2020-09-17/fallback.parquet'
con = duckdb.connect(); con.execute("SET threads=4")
def rec(f):
    return dict(con.execute(f"SELECT user_id, min(up_days_since_last) FROM read_parquet('{f}') GROUP BY user_id").fetchall())
def band(d):
    assert d is not None, 'every query has a repeat candidate'
    return '<7' if d < 7 else '7-30' if d < 30 else '>=30'
val, kag = rec(VAL), rec(KAG)
test_users = set(kag) | {u for (u,) in con.execute(f"SELECT user_id FROM read_parquet('{FALLBACK}')").fetchall()}
bands = ['<7', '7-30', '>=30']
mix = {b: sum(band(d) == b for d in kag.values()) / len(kag) for b in bands}
vmix = {b: sum(band(d) == b for d in val.values()) / len(val) for b in bands}
names = [f'{a}{s}' for a in ('B', 'BA', 'BApl') for s in (2026, 2027)]
m = {k: dict(zip(*[xc.read_parquet(F.format(k))[c].tolist() for c in ('user_id', 'value')])) for k in names}
out = dict(question='agent gain on val-2020-08-19 by recency of the last purchase (min up_days_since_last over '
           'candidates; bands d<7, 7<=d<30, d>=30) and by membership in the Kaggle test users',
           inputs={p: xc.sha256_file(p) for p in [F.format(k) for k in names] + [VAL, KAG, FALLBACK]},
           val_mix=vmix, kaggle_mix_scoring_users=mix, groups={}, test_split={}, kaggle_weighted={})
def stats(users):
    g = dict(queries=len(users))
    for s in (2026, 2027):
        pick = lambda k: {u: m[k][u] for u in users}
        g[f'B{s}'] = sum(pick(f'B{s}').values()) / len(users)
        g[f'D{s}'] = xc.bootstrap(pick(f'B{s}'), pick(f'BA{s}'))
        g[f'P{s}'] = xc.bootstrap(pick(f'BApl{s}'), pick(f'BA{s}'))
    return g
for b in bands:
    out['groups'][b] = stats([u for u in m['B2026'] if band(val[u]) == b])
out['test_split']['kaggle_test'] = stats([u for u in m['B2026'] if u in test_users])
out['test_split']['other'] = stats([u for u in m['B2026'] if u not in test_users])
cov = {}
for name, frame, users in (('val', VAL, val), ('kaggle', KAG, kag)):
    side = frame.replace('collections', 'sidecars').replace('frame.parquet', 'agent.parquet')
    rows = con.execute(f"SELECT user_id, avg((ag_up_gap_cv IS NOT NULL AND isfinite(ag_up_gap_cv))::INT), count(*) "
                       f"FROM read_parquet('{side}') GROUP BY user_id").fetchall()
    per = {b: [0.0, 0] for b in bands}
    for u, share, n in rows:
        per[band(users[u])][0] += share*n
        per[band(users[u])][1] += n
    cov[name] = {b: s/n for b, (s, n) in per.items()}
    cov[name]['all'] = sum(s for s, _ in per.values())/sum(n for _, n in per.values())
cov['val_reweighted_to_kaggle_mix'] = sum(mix[b]*cov['val'][b] for b in bands)
out['coverage'] = dict(column='ag_up_gap_cv', note='non-NULL share over sidecar rows, per recency band; '
                       'reweighting uses the user mix (rows per user are 200)', **cov)
for s in (2026, 2027):
    out['kaggle_weighted'][f'D{s}'] = sum(mix[b] * out['groups'][b][f'D{s}']['mean'] for b in bands)
print(json.dumps(out, ensure_ascii=False, indent=1))
