"""H13: candidate coverage on REES46 2020 — do new candidate sources add recall at a fixed number of candidates?
(council/runs/side/coverage.md; night plan 22.10, hypothesis 7; report «Кандидаты», «Следующие шаги» п. 1).

About half of the targets are outside the six candidate sources (report «Кандидаты»). For each anchor day of the
tail of T_fit (2020-01-29..02-02: the last train days before S0; the broker reads the labels of S0)
this module rebuilds the six sources with the build's own SQL (task1.build.ANCHOR, imported) and adds three sources
built from the same 14-day window [t-14d, t), each ranked per user, touched products excluded, top KMAX kept:

  i2v  item2vec by sessions: PPMI (context smoothing 0.75) of the session co-view counts (sessions of 2..50 distinct
       viewed products, items in >= I2V_MIN_SESSIONS sessions, the I2V_MAX_ITEMS most frequent, pairs n >= 2),
       truncated SVD to I2V_DIM; user vector = sum of the item vectors of the 20 latest views weighted
       exp(-age / 1 day); score = cosine. (gensim is not installed; SVD of shifted-free PPMI is the matrix form of
       skip-gram with negative sampling, Levy & Goldberg 2014.)
  cp1  co-purchase, one step: P(B|A) = n_AB / (n_A + 5) over users with 2..50 carted/purchased products in the window,
       top CP_HOP per A; score(u, B) = sum over the 10 latest views A of exp(-age/1d) P(B|A).
  cp2  co-purchase, second step: score(u, C) = sum_A exp(-age/1d) sum_B P(B|A) P(C|B) (both hops top CP_HOP).

Per query (anchor, user): targets, hits and rows of every current source, of the union U and of each new source at
K in K_GRID, hits and rows outside U. Pooled numbers with a bootstrap over queries (DRAWS, seed 2026). Primary
(prereg): efficiency e = targets covered per 1000 added candidates; for N in PRIMARY at K = PRIMARY_K,
e(N \\ U) - e(weakest current source, its unique rows) with a 95% CI. Check: the union's hits and the targets of the
queries with a candidate equal those of the days6 table of the same day (the build's output), when that file exists.

DuckDB: an in-memory session, threads THREADS, memory_limit MEMORY, spill in /tmp/tlab-side-coverage-duckdb; the
database (task1.period.DB, rees46-2020.duckdb) is attached READ_ONLY as `src` (DuckDB will not give a
read_only=True connection the writable catalog the build's temp tables need; ATTACH ... (READ_ONLY) is the same
guarantee, and attach_db() checks duckdb_databases().readonly); work tables are temp tables.

Light step, no heavy lock. Before the start and before each anchor: council.xfer.queue.light_wait('probe', xfer
journals + side journal) (waits next to REES46 full_val/full_test fits, council.memory, compute, or a heavy step of
unknown or > 20 GB peak), then a wait while any queue.foreign() process runs `-m council.(queue|fit|memory)` (any
REES46 fit, also the plan and C_val queues, which take no lock). light-wait/light-start/light-end with the peak in
council/runs/side/queue.jsonl. REES46 heavy steps see this run through the plan's ПРОВЕРКА-HEAVY
`! pgrep -fl '[c]ouncil/xfer/run.py.*(queue|compute|fit-one)|[c]ouncil\\.(fit|queue|memory)|[c]ouncil[./]side'`,
whose last alternative matches the script path: run it as a script, not with -m.

Writes artifacts/side/coverage/per_query.parquet and council/runs/side/coverage.json only; listing and mtime of
artifacts/xfer and artifacts/task1 are taken after the first gate and compared after the last read (exit 3 on a
change). Reads no val, test, S0 or broker data.

Run as a script (from the repository root):
  TASK1_PERIOD=2020 .venv/bin/python -I council/side/coverage.py --dry
  TASK1_PERIOD=2020 .venv/bin/python -I council/side/coverage.py > /tmp/tlab-side-coverage.log 2>&1
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
if os.environ.setdefault('TASK1_PERIOD', '2020') != '2020':
    raise SystemExit(f"TASK1_PERIOD={os.environ['TASK1_PERIOD']!r}: the coverage runs on REES46 2020")

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from datetime import date, datetime  # noqa: E402

from council import side as S  # noqa: E402

NAME = 'coverage'
DATASET = 'rees46-2020'
SPAN = 'T_fit'
TAIL_DAYS = 5
THREADS = 4
MEMORY = '4GB'
DUCKDB_TMP = Path('/tmp/tlab-side-coverage-duckdb')
CURRENT = ('pop', 'cat', 'brand', 'coview', 'coview_agg', 'transition')     # sources 1-6 of task1.build
CURRENT_FLAG = {'pop': 'pop_rank IS NOT NULL', 'cat': 'cat_rank IS NOT NULL', 'brand': 'brand_rank IS NOT NULL',
                'coview': 'coalesce(src4, 0) = 1', 'coview_agg': 'cvagg_rank IS NOT NULL',
                'transition': 'tr_rank IS NOT NULL'}
NEW = ('i2v', 'cp1', 'cp2')
PRIMARY = ('i2v', 'cp2')
K_GRID = (10, 20, 50, 100, 200)
KMAX = max(K_GRID)
PRIMARY_K = 50
I2V_DIM = 64
I2V_MIN_SESSIONS = 5
I2V_MAX_ITEMS = 100000
I2V_MIN_PAIR = 2
I2V_ALPHA = 0.75
I2V_SEEDS = 20
CP_SEEDS = 10
CP_HOP = 20
CP_PRIOR = 5
SCORE_CHUNK = 512
DRAWS = 2000
BOOT_SEED = 2026
FORMAT = 'side-coverage-v1'
FS_TABLES = ('events', 'pair_first', 'item_static', 'item_brand_day')


# ---------------------------------------------------------------- spec (no data)

def tail_days(days: list, tail: int = TAIL_DAYS, before=None) -> list:
    days = sorted(days)
    if len(days) < tail:
        raise S.Refused('too few days')
    out = days[-tail:]
    if before is not None and out[-1] >= before:
        raise S.Refused(f'{out[-1]} is not before {before}')
    return out


def spec() -> dict:
    from council import roles
    from task1 import period as P
    days = tail_days(roles.days(SPAN), before=roles.days('S0')[0])
    return {'format': FORMAT, 'dataset': DATASET, 'span': SPAN, 'anchors': [str(d) for d in days],
            'db': str(P.DB), 'days6': str(roles.DAYS6), 'duckdb': {'threads': THREADS, 'memory_limit': MEMORY,
                                                                    'read_only': True, 'temp': str(DUCKDB_TMP)},
            'current': list(CURRENT), 'new': list(NEW), 'k_grid': list(K_GRID), 'primary': list(PRIMARY),
            'primary_k': PRIMARY_K,
            'i2v': {'dim': I2V_DIM, 'min_sessions': I2V_MIN_SESSIONS, 'max_items': I2V_MAX_ITEMS,
                    'min_pair': I2V_MIN_PAIR, 'alpha': I2V_ALPHA, 'seeds': I2V_SEEDS, 'session_items': [2, 50]},
            'cp': {'seeds': CP_SEEDS, 'hop': CP_HOP, 'prior': CP_PRIOR, 'user_items': [2, 50]},
            'bootstrap': {'draws': DRAWS, 'seed': BOOT_SEED},
            'decision': 'per N in primary: CI of e(N@K \\ U) - e(weakest current, unique) > 0 -> окупается; '
                        '< 0 -> не окупается; else не различено (e = targets per 1000 added candidates)'}


def spec_digest(s: dict) -> str:
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


def check_days(s: dict) -> None:
    from council import roles
    span = {str(d) for d in roles.days(SPAN)}
    first_s0 = str(roles.days('S0')[0])
    for d in s['anchors']:
        if d not in span or d >= first_s0:
            raise S.Refused(f'{d} is not a T_fit day before S0')


# ---------------------------------------------------------------- DuckDB

def attach_db(db: Path, tmp: Path = DUCKDB_TMP):
    """An in-memory session (threads, memory limit, spill under tmp) with the database attached read-only as `src`
    and the schema `fs` of views over it, as task1.build.connect lays them out. DuckDB refuses the writable catalog
    the build's temp tables need next to duckdb.connect(db, read_only=True), so the read-only open is the ATTACH's
    READ_ONLY (any write to src fails; the test checks it)."""
    import duckdb
    if not Path(db).exists():
        raise S.Refused(f'{db} does not exist')
    con = duckdb.connect(config={'threads': str(THREADS), 'memory_limit': MEMORY})
    Path(tmp).mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{_lit(tmp)}'")
    con.execute(f"ATTACH '{_lit(db)}' AS src (READ_ONLY)")
    if not con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name = 'src'").fetchone()[0]:
        raise S.Refused('the database is not attached read-only')
    con.execute('CREATE SCHEMA fs')
    for t in FS_TABLES:
        con.execute(f'CREATE VIEW fs.{t} AS SELECT * FROM src.{t}')
    return con


def _lit(x) -> str:
    return str(x).replace("'", "''")


def anchor_ts(day: str) -> str:
    return datetime.combine(date.fromisoformat(day), datetime.min.time()).isoformat(sep=' ')


CP_SQL = """
CREATE OR REPLACE TEMP TABLE cpu AS SELECT DISTINCT user_id, product_id FROM w WHERE event_type IN ('cart','purchase');
CREATE OR REPLACE TEMP TABLE cpn AS SELECT product_id, count(*) n FROM cpu GROUP BY 1;
CREATE OR REPLACE TEMP TABLE cpe AS
  WITH u2 AS (SELECT cpu.* FROM cpu JOIN (SELECT user_id FROM cpu GROUP BY 1 HAVING count(*) BETWEEN 2 AND 50) USING(user_id))
  SELECT x.product_id a, y.product_id b, count(*) n_ab
  FROM u2 x JOIN u2 y ON x.user_id = y.user_id AND x.product_id <> y.product_id GROUP BY 1, 2;
CREATE OR REPLACE TEMP TABLE cpp AS SELECT e.a, e.b, e.n_ab / (n.n + {PRIOR}.0) p
  FROM cpe e JOIN cpn n ON n.product_id = e.a
  QUALIFY row_number() OVER (PARTITION BY e.a ORDER BY e.n_ab DESC, e.b) <= {HOP};
CREATE OR REPLACE TEMP TABLE cpseed AS SELECT user_id, product_id a, exp(-epoch({T} - last_ts) / 86400) d
  FROM rv WHERE k <= {SEEDS};
CREATE OR REPLACE TEMP TABLE cps AS
  SELECT 'cp1' src, s.user_id, p.b product_id, sum(s.d * p.p) score FROM cpseed s JOIN cpp p ON p.a = s.a GROUP BY 2, 3
  UNION ALL
  SELECT 'cp2' src, s.user_id, q.b product_id, sum(s.d * p.p * q.p) score
  FROM cpseed s JOIN cpp p ON p.a = s.a JOIN cpp q ON q.a = p.b GROUP BY 2, 3;
INSERT INTO nsrc SELECT user_id, product_id, src,
  row_number() OVER (PARTITION BY src, user_id ORDER BY round(score, 12) DESC, product_id) rk
  FROM cps c WHERE NOT EXISTS (SELECT 1 FROM touched x WHERE x.user_id = c.user_id AND x.product_id = c.product_id)
  QUALIFY rk <= {KMAX};
"""

I2V_VOCAB_SQL = """
CREATE OR REPLACE TEMP TABLE voc AS SELECT product_id, (row_number() OVER (ORDER BY n DESC, product_id) - 1)::INT vid
  FROM ns WHERE n >= {MIN_SESSIONS} QUALIFY vid < {MAX_ITEMS};
"""
I2V_PAIRS_SQL = """
WITH s2 AS (SELECT sv.s, v.vid FROM sv JOIN voc v USING(product_id)
            JOIN (SELECT s FROM sv GROUP BY s HAVING count(*) BETWEEN 2 AND 50) USING(s))
SELECT x.vid i, y.vid j, count(*)::DOUBLE n FROM s2 x JOIN s2 y ON x.s = y.s AND x.vid <> y.vid
GROUP BY 1, 2 HAVING count(*) >= {MIN_PAIR}
"""
I2V_SEEDS_SQL = """
SELECT r.user_id, v.vid, exp(-epoch({T} - r.last_ts) / 86400) d FROM rv r JOIN voc v USING(product_id)
WHERE r.k <= {SEEDS}
"""
I2V_TOUCHED_SQL = 'SELECT x.user_id, v.vid FROM touched x JOIN voc v USING(product_id)'


def _sub(sql: str, t: str, **kw) -> str:
    sql = sql.replace('{T}', f"TIMESTAMP '{t}'")
    for k, v in kw.items():
        sql = sql.replace('{' + k + '}', str(v))
    return sql


def embeddings(con, dim: int = I2V_DIM):
    """Item vectors (L2-normalized rows) of the vocabulary `voc` from the PPMI of the session co-view pairs; None
    when the vocabulary is too small."""
    import numpy as np
    from scipy import sparse
    from scipy.sparse.linalg import svds
    con.execute(_sub(I2V_VOCAB_SQL, '', MIN_SESSIONS=I2V_MIN_SESSIONS, MAX_ITEMS=I2V_MAX_ITEMS))
    v = con.execute('SELECT count(*) FROM voc').fetchone()[0]
    if v < 3:
        return None
    p = con.execute(_sub(I2V_PAIRS_SQL, '', MIN_PAIR=I2V_MIN_PAIR)).fetchnumpy()
    if not len(p['n']):
        return None
    m = sparse.csr_matrix((p['n'], (p['i'], p['j'])), shape=(v, v))
    del p
    total = m.sum()
    rows = np.asarray(m.sum(axis=1)).ravel()
    ctx = np.asarray(m.sum(axis=0)).ravel() ** I2V_ALPHA
    ctx_p = ctx / ctx.sum()
    coo = m.tocoo()
    pmi = np.log(coo.data / total) - np.log(rows[coo.row] / total) - np.log(ctx_p[coo.col])
    keep = pmi > 0
    ppmi = sparse.csr_matrix((pmi[keep], (coo.row[keep], coo.col[keep])), shape=(v, v))
    k = min(dim, v - 2)
    if k < 1 or ppmi.nnz == 0:
        return None
    u, s, _ = svds(ppmi.astype(np.float64), k=k, random_state=0)
    e = u * np.sqrt(s)
    norm = np.linalg.norm(e, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return (e / norm).astype(np.float32)


def i2v_rows(con, t: str, emb):
    """(user_id, product_id, src, rk) of the i2v source: top KMAX cosine items per user, touched excluded."""
    import numpy as np
    import pandas as pd
    empty = pd.DataFrame({'user_id': pd.Series(dtype='int64'), 'product_id': pd.Series(dtype='int64'),
                          'src': pd.Series(dtype='object'), 'rk': pd.Series(dtype='int64')})
    if emb is None:
        return empty
    seeds = con.execute(_sub(I2V_SEEDS_SQL, t, SEEDS=I2V_SEEDS)).df()
    if seeds.empty:
        return empty
    touched = con.execute(I2V_TOUCHED_SQL).df()
    pid = con.execute('SELECT vid, product_id FROM voc ORDER BY vid').df()['product_id'].to_numpy()
    users = np.sort(seeds['user_id'].unique())
    pos = {u: i for i, u in enumerate(users)}
    uvec = np.zeros((len(users), emb.shape[1]), dtype=np.float64)
    np.add.at(uvec, seeds['user_id'].map(pos).to_numpy(), emb[seeds['vid'].to_numpy()] * seeds['d'].to_numpy()[:, None])
    norm = np.linalg.norm(uvec, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    uvec = (uvec / norm).astype(np.float32)
    t_rows = touched['user_id'].map(pos)
    keep = t_rows.notna().to_numpy()
    t_u, t_v = t_rows[keep].astype(int).to_numpy(), touched['vid'].to_numpy()[keep]
    k = min(KMAX, emb.shape[0])
    parts = []
    for start in range(0, len(users), SCORE_CHUNK):
        stop = min(start + SCORE_CHUNK, len(users))
        sc = uvec[start:stop] @ emb.T
        sel = (t_u >= start) & (t_u < stop)
        sc[t_u[sel] - start, t_v[sel]] = -np.inf
        top = np.argpartition(-sc, k - 1, axis=1)[:, :k] if k < sc.shape[1] else np.tile(np.arange(sc.shape[1]),
                                                                                         (stop - start, 1))
        for r in range(stop - start):
            cand = top[r][np.isfinite(sc[r, top[r]])]
            order = np.lexsort((pid[cand], -np.round(sc[r, cand].astype(np.float64), 6)))
            cand = cand[order][:KMAX]
            parts.append(pd.DataFrame({'user_id': users[start + r], 'product_id': pid[cand], 'src': 'i2v',
                                       'rk': np.arange(1, len(cand) + 1)}))
    return pd.concat(parts, ignore_index=True) if parts else empty


def per_query_sql() -> str:
    """One row per query of the anchor: targets, current-source hits/rows (all and unique), union, new sources."""
    flags = ', '.join(f'({CURRENT_FLAG[s]})::INT f_{s}' for s in CURRENT)
    nsum = ' + '.join(f'f_{s}' for s in CURRENT)
    lab_new = ', '.join(f"min(n.rk) FILTER (n.src = '{s}') r_{s}" for s in NEW)
    cols = ['q.user_id', 'q.n_targets']
    cols += [f'coalesce(h.hits_{s}, 0) hits_{s}' for s in CURRENT]
    cols += [f'coalesce(h.uhits_{s}, 0) uhits_{s}' for s in CURRENT]
    cols += ['coalesce(h.hits_U, 0) hits_U']
    cols += [f'coalesce(c.rows_{s}, 0) rows_{s}' for s in CURRENT]
    cols += [f'coalesce(c.urows_{s}, 0) urows_{s}' for s in CURRENT]
    cols += ['coalesce(c.rows_U, 0) rows_U']
    for s in NEW:
        for k in K_GRID:
            cols += [f'coalesce(h.hits_{s}_{k}, 0) hits_{s}_{k}', f'coalesce(h.nhits_{s}_{k}, 0) nhits_{s}_{k}',
                     f'coalesce(r.rows_{s}_{k}, 0) rows_{s}_{k}', f'coalesce(r.nrows_{s}_{k}, 0) nrows_{s}_{k}']
    hits = [f'sum(f_{s}) hits_{s}' for s in CURRENT] + [f'sum(f_{s}) FILTER (n_src = 1) uhits_{s}' for s in CURRENT]
    hits += ['sum(in_u) hits_U']
    for s in NEW:
        for k in K_GRID:
            hits += [f'count(*) FILTER (r_{s} <= {k}) hits_{s}_{k}',
                     f'count(*) FILTER (r_{s} <= {k} AND in_u = 0) nhits_{s}_{k}']
    crows = [f'sum(f_{s}) rows_{s}' for s in CURRENT] + [f'sum(f_{s}) FILTER (n_src = 1) urows_{s}' for s in CURRENT]
    nrows = []
    for s in NEW:
        for k in K_GRID:
            nrows += [f"count(*) FILTER (n.src = '{s}' AND n.rk <= {k}) rows_{s}_{k}",
                      f"count(*) FILTER (n.src = '{s}' AND n.rk <= {k} AND c.user_id IS NULL) nrows_{s}_{k}"]
    return f"""
WITH cf AS (SELECT user_id, product_id, {flags} FROM candidates),
cf2 AS (SELECT *, {nsum} n_src FROM cf),
ln AS (SELECT l.user_id, l.product_id, {lab_new} FROM labels l LEFT JOIN nsrc n USING(user_id, product_id) GROUP BY 1, 2),
lab AS (SELECT l.user_id, {', '.join(f'coalesce(c.f_{s}, 0) f_{s}' for s in CURRENT)},
        coalesce(c.n_src, 0) n_src, (c.user_id IS NOT NULL)::INT in_u, {', '.join(f'ln.r_{s}' for s in NEW)}
        FROM labels l LEFT JOIN cf2 c USING(user_id, product_id) JOIN ln USING(user_id, product_id)),
h AS (SELECT user_id, {', '.join(hits)} FROM lab GROUP BY 1),
c AS (SELECT user_id, {', '.join(crows)}, count(*) rows_U FROM cf2 GROUP BY 1),
r AS (SELECT n.user_id, {', '.join(nrows)} FROM nsrc n LEFT JOIN candidates c USING(user_id, product_id) GROUP BY 1)
SELECT {', '.join(cols)} FROM queries q LEFT JOIN h USING(user_id) LEFT JOIN c USING(user_id)
LEFT JOIN r USING(user_id) ORDER BY q.user_id
"""


def days6_check(day: str, days6: Path):
    """(hits, targets) of the days6 table of the day: sum(label) and the sum of n_targets over its queries."""
    import duckdb
    f = Path(days6) / f'{day}.parquet'
    if not f.exists():
        return None
    con = duckdb.connect(config={'threads': str(THREADS), 'memory_limit': MEMORY})
    try:
        h, t = con.execute(f"""SELECT sum(label), (SELECT sum(n) FROM (SELECT user_id, any_value(n_targets) n
            FROM read_parquet('{_lit(f)}') GROUP BY 1)) FROM read_parquet('{_lit(f)}')""").fetchone()
        return int(h or 0), int(t or 0)
    finally:
        con.close()


def anchor_queries(con, day: str):
    """The per-query frame of one anchor day (task1.build.set_anchor, then the new sources)."""
    from task1 import build
    t = anchor_ts(day)
    timings = {}
    t0 = time.monotonic()
    build.set_anchor(con, t)
    timings['current'] = round(time.monotonic() - t0, 1)
    con.execute('CREATE OR REPLACE TEMP TABLE nsrc (user_id BIGINT, product_id BIGINT, src VARCHAR, rk BIGINT)')
    t0 = time.monotonic()
    con.execute(_sub(CP_SQL, t, PRIOR=CP_PRIOR, HOP=CP_HOP, SEEDS=CP_SEEDS, KMAX=KMAX))
    timings['cp'] = round(time.monotonic() - t0, 1)
    t0 = time.monotonic()
    emb = embeddings(con)
    rows = i2v_rows(con, t, emb)
    con.register('_i2v_rows', rows)
    try:
        con.execute('INSERT INTO nsrc SELECT user_id, product_id, src, rk FROM _i2v_rows')
    finally:
        con.unregister('_i2v_rows')
    timings['i2v'] = round(time.monotonic() - t0, 1)
    t0 = time.monotonic()
    pq = con.execute(per_query_sql()).df()
    timings['aggregate'] = round(time.monotonic() - t0, 1)
    pq.insert(0, 'anchor', day)
    vocab = int(con.execute('SELECT count(*) FROM voc').fetchone()[0])
    return pq, {'seconds': timings, 'i2v_vocab': vocab, 'i2v_dim': None if emb is None else int(emb.shape[1])}


REES46_HEAVY = re.compile(r'-m\s+council\.(queue|fit|memory)\b')


def rees46_heavy(procs=None, own=None) -> list:
    """(pid, command) of the foreign processes running `-m council.(queue|fit|memory)` (queue.foreign, filtered)."""
    from council.xfer import queue as Q
    return [(pid, cmd) for pid, cmd in Q.foreign(procs, own) if REES46_HEAVY.search(cmd)]


def wait_rees46(out: S.Out, *, wait=True, procs_fn=None, sleep=time.sleep, poll=60.0, own=None, **_) -> None:
    """Block while a REES46 queue, fit or memory process runs (journal 'light-wait' once); wait=False: Busy."""
    from council.xfer import queue as Q
    noted = False
    while True:
        found = rees46_heavy(procs_fn() if procs_fn else None, own)
        if not found:
            return
        if not wait:
            raise Q.Busy(f'REES46 heavy processes run: {[p for p, _ in found]}')
        if not noted:
            S.journal(out, {'event': 'light-wait', 'what': f'probe side {NAME}', 'dataset': DATASET,
                            'reason': f'rees46 heavy: {[p for p, _ in found]}'})
            noted = True
        sleep(poll)


def gate(out: S.Out, *, wait=True, gate_kw=None) -> None:
    """The probe gate of council.xfer.queue, then no REES46 queue/fit/memory process."""
    kw = gate_kw or {}
    S.light_gate_wait(NAME, DATASET, out, wait=wait, **kw)
    wait_rees46(out, wait=wait, **kw)


# ---------------------------------------------------------------- statistics

def _sums(frame, cols, weights=None):
    import numpy as np
    x = frame[cols].to_numpy(dtype=np.float64)
    return x.sum(axis=0) if weights is None else weights @ x


def pooled(pq) -> dict:
    """Point estimates over all queries: recall of every source, union, unique; sizes per query; efficiencies."""
    n_t = float(pq['n_targets'].sum())
    nq = len(pq)
    out = {'queries': nq, 'targets': int(n_t), 'union': {'recall': pq['hits_U'].sum() / n_t,
                                                         'rows_per_query': pq['rows_U'].sum() / nq}}
    cur = {}
    for s in CURRENT:
        ur = pq[f'urows_{s}'].sum()
        cur[s] = {'recall': pq[f'hits_{s}'].sum() / n_t, 'rows_per_query': pq[f'rows_{s}'].sum() / nq,
                  'unique_recall': pq[f'uhits_{s}'].sum() / n_t, 'unique_rows_per_query': ur / nq,
                  'unique_eff_per_1000': 1000 * pq[f'uhits_{s}'].sum() / ur if ur else None}
    out['current'] = cur
    new = {}
    for s in NEW:
        new[s] = {}
        for k in K_GRID:
            nr = pq[f'nrows_{s}_{k}'].sum()
            new[s][str(k)] = {'recall': pq[f'hits_{s}_{k}'].sum() / n_t,
                              'rows_per_query': pq[f'rows_{s}_{k}'].sum() / nq,
                              'added_recall': pq[f'nhits_{s}_{k}'].sum() / n_t,
                              'added_rows_per_query': nr / nq,
                              'added_eff_per_1000': 1000 * pq[f'nhits_{s}_{k}'].sum() / nr if nr else None}
    out['new'] = new
    eff = {s: v['unique_eff_per_1000'] for s, v in cur.items() if v['unique_eff_per_1000'] is not None}
    out['weakest_current'] = min(eff, key=eff.get) if eff else None
    return out


def primary(pq, weakest: str, draws=DRAWS, seed=BOOT_SEED) -> dict:
    """For N in PRIMARY: e(N@K outside U) - e(weakest, unique), bootstrap over queries (shared draws)."""
    import numpy as np
    k = PRIMARY_K
    cols = [f'uhits_{weakest}', f'urows_{weakest}'] + [c for s in PRIMARY for c in (f'nhits_{s}_{k}', f'nrows_{s}_{k}')]
    x = pq[cols].to_numpy(dtype=np.float64)
    rng = np.random.default_rng(seed)
    n = len(pq)
    boots = np.empty((draws, len(cols)))
    for i in range(draws):
        boots[i] = np.bincount(rng.integers(0, n, n), minlength=n) @ x
    full = x.sum(axis=0)

    def eff(h, r):
        with np.errstate(divide='ignore', invalid='ignore'):
            return 1000 * np.asarray(h) / np.asarray(r)
    base, base_b = eff(full[0], full[1]), eff(boots[:, 0], boots[:, 1])
    out = {}
    for j, s in enumerate(PRIMARY):
        h, r = 2 + 2 * j, 3 + 2 * j
        d, d_b = eff(full[h], full[r]) - base, eff(boots[:, h], boots[:, r]) - base_b
        d_b = d_b[np.isfinite(d_b)]
        if not len(d_b) or not np.isfinite(d):
            out[s] = {'k': k, 'diff': None, 'ci': None, 'decision': 'не различено', 'reason': 'no added rows'}
            continue
        lo, hi = (float(v) for v in np.quantile(d_b, [0.025, 0.975], method='linear'))
        dec = 'окупается' if lo > 0 else 'не окупается' if hi < 0 else 'не различено'
        out[s] = {'k': k, 'against': weakest, 'eff_new': float(eff(full[h], full[r])), 'eff_weakest': float(base),
                  'diff': float(d), 'ci': [lo, hi], 'draws': int(len(d_b)), 'decision': dec}
    return out


# ---------------------------------------------------------------- run

def run(out: S.Out, s: dict, *, wait=True, gate_kw=None, protected=S.PROTECTED, db=None, days6=None,
        draws=DRAWS, tmp: Path = DUCKDB_TMP) -> dict:
    import pandas as pd
    check_days(s)
    t0 = time.time()
    gate(out, wait=wait, gate_kw=gate_kw)
    before = S.protected_snapshot(protected)       # after the gate: a REES46 step waited for may have written
    S.journal(out, {'event': 'light-start', 'what': f'probe side {NAME}', 'dataset': DATASET, 'pid': os.getpid()})
    ok = False
    days, parts = {}, []
    try:
        con = attach_db(Path(db or s['db']), tmp)
        try:
            for day in s['anchors']:
                gate(out, wait=wait, gate_kw=gate_kw)
                pq, info = anchor_queries(con, day)
                chk = days6_check(day, Path(days6 or s['days6']))
                mine = (int(pq['hits_U'].sum()), int(pq.loc[pq['rows_U'] > 0, 'n_targets'].sum()))
                info.update(queries=len(pq), targets=int(pq['n_targets'].sum()), hits_U=mine[0],
                            targets_with_candidates=mine[1],
                            days6=None if chk is None else {'hits': chk[0], 'targets': chk[1], 'match': chk == mine})
                days[day] = info
                parts.append(pq)
        finally:
            con.close()
        verdict = S.protected_verdict(before, protected)
        ok = True
    finally:
        S.journal(out, {'event': 'light-end', 'what': f'probe side {NAME}', 'dataset': DATASET, 'ok': ok,
                        'seconds': round(time.time() - t0, 1), 'peak_gb': S.peak_rss_gb()})
    pq = pd.concat(parts, ignore_index=True)
    out.write_frame(pq, 'per_query.parquet')
    summary = pooled(pq)
    prim = primary(pq, summary['weakest_current'], draws=draws) if summary['weakest_current'] else {}
    matches = [d['days6']['match'] for d in days.values() if d['days6'] is not None]
    result = {'format': FORMAT, 'status': 'ok' if verdict['unchanged'] else 'refused', 'spec': s,
              'spec_digest': spec_digest(s), 'days': days, 'pooled': summary, 'primary': prim,
              'build_match': all(matches) if matches else None, 'seconds': round(time.time() - t0, 1),
              'peak_rss_gb': S.peak_rss_gb(), 'protected': verdict, 'code': S.code_identity(__file__),
              'finished': S.now()}
    out.write_json(result, f'{NAME}.json', runs=True)
    if not verdict['unchanged']:
        raise SystemExit(S.PROTECTED_EXIT)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description='H13: candidate coverage by source on the T_fit tail of REES46 2020 '
                                             '(council/runs/side/coverage.md)')
    ap.add_argument('--dry', action='store_true', help='print the spec and paths; open no database')
    ap.add_argument('--no-wait', action='store_true', help='refuse instead of waiting at the probe gate')
    args = ap.parse_args(argv)
    s = spec()
    check_days(s)
    out = S.Out(NAME)
    if args.dry:
        S.print_json({'dry': True, 'spec': s, 'spec_digest': spec_digest(s),
                      'gate': 'light_wait(probe) + no -m council.(queue|fit|memory)',
                      'db_exists': Path(s['db']).exists(),
                      'outputs': [str(out.path('per_query.parquet')), str(out.path(f'{NAME}.json', runs=True))],
                      'journal': str(out.journal), 'protected': [str(p) for p in S.PROTECTED]})
        return 0
    res = run(out, s, wait=not args.no_wait)
    S.print_json({'status': res['status'], 'union_recall': res['pooled']['union']['recall'],
                  'primary': res['primary'], 'build_match': res['build_match'], 'seconds': res['seconds']})
    return 0


if __name__ == '__main__':
    sys.exit(main())
