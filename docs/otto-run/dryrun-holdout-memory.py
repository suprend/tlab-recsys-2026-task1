"""Dry run of holdout() after the label read, on FAKE labels: memory of metric, bootstrap and ceiling on F4.
Never touches the sealed directory. Fake labels = F3 labels remapped onto F4 population sessions."""
import json, resource, sys, time
from pathlib import Path
ROOT = Path.home()/'tlab-recsys-2026'
sys.path.insert(0, str(ROOT/'scripts'))
import otto_common as oc, otto_model as om
import duckdb, numpy as np, pandas as pd

def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30
log = {}
t0 = time.monotonic()
ctx = om.Context.contract()
coll = ctx.collection(4)
pop = oc.read_population(coll)
pop_arr = np.asarray(list(pop), dtype=np.int64)
fake = Path('/tmp/tlab-otto-dryrun/fake-labels.parquet')
con = duckdb.connect(); con.execute('SET threads=4')
con.register('p', pd.DataFrame({'s': pop_arr, 'i': np.arange(len(pop_arr))}))
con.execute(f"""COPY (WITH f AS (SELECT session, type, aid, dense_rank() OVER (ORDER BY session) - 1 AS j
    FROM read_parquet('{ROOT}/artifacts/otto/collections/val-F3/labels.parquet')),
    n AS (SELECT max(j)+1 AS m FROM f),
    r AS (SELECT p.s AS session, f.type, f.aid FROM p, n JOIN f ON f.j = p.i % n.m)
    SELECT DISTINCT session, type, aid FROM r) TO '{fake}' (FORMAT parquet)""")
con.close()
log['fake_rows'] = duckdb.sql(f"select count(*), count(distinct session) from '{fake}'").fetchone()
log['t_fake'] = round(time.monotonic()-t0, 1)
values = {}
for arm in ('B', 'BA', 'BApl'):
    d = ROOT/f'artifacts/otto/fits/holdout-{arm}2026/eval'
    t = time.monotonic()
    values[arm] = oc.metric(d/om.RANKED_FILE, fake, sessions=pop, threads=ctx.threads)
    log[f'metric_{arm}'] = dict(s=round(time.monotonic()-t, 1), rss=round(rss(), 2), score=values[arm]['score'])
rep = json.loads((ROOT/'artifacts/otto/fits/holdout-B2026/eval/report.json').read_text())
t = time.monotonic(); pm = om.pop_metric(ctx.threads, rep, fake, pop)
log['pop'] = dict(s=round(time.monotonic()-t, 1), rss=round(rss(), 2))
for name, (a, b) in dict(D=('B', 'BA'), P=('BApl', 'BA'), L=('B', 'BApl')).items():
    t = time.monotonic(); r = oc.bootstrap_ratio(values[a], values[b])
    log[f'boot_{name}'] = dict(s=round(time.monotonic()-t, 1), rss=round(rss(), 2), ci=r.get('ci'))
con = om.connect(ctx)
try:
    om.register_sessions(con, 'population', pop)
    for arm in ('B', 'BA'):
        t = time.monotonic()
        om.arm_view(con, ctx, coll, arm, name='cv')
        c = om.ceiling(con, 'cv', fake, 'population')
        log[f'ceiling_{arm}'] = dict(s=round(time.monotonic()-t, 1), rss=round(rss(), 2), value=c)
finally:
    con.close()
log['total_s'] = round(time.monotonic()-t0, 1); log['peak_rss_gb'] = round(rss(), 2)
print(json.dumps(log, default=str, indent=1))
