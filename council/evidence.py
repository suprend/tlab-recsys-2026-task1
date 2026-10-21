"""Evidence without targets and the curator code of the council (council/runs/rees46-2020/contract.md,
section 3.4 steps 3 and 6, section 2 width parity).

probe(card_or_sql)      sandbox runs on the probe days: validity, NONDETERMINISTIC, seconds, rows, keys, columns,
                        coverage on the candidate rows of days6, batch invariance (user and pair level),
                        within-query rho and R2 against the base of days6 and the 34 tables of H+.
twin_check(card, twin)  coverage within +-10% and |rho_wq(card, twin)| <= 0.8, else TWIN-BROKEN.
parity(probe)           non-NULL share of every day inside [0.5 min, 2 max] of the other days.
machine_red(probe)      reasons of a red machine test (invalid, NONDETERMINISTIC, batch, error).
curate(cards, probes, reference_width, critiques)
                        steps 1-6 of the curator and the width parity of section 2.
validate_card(card)     the card schema of section 3.4.

Reads of days6 are positive: the keys and the columns whose names start with task1.model.GROUPS. Nothing
else of a day table is selected.

NULL policy of rho_wq and R2_wq (decided here, before any numbers):
- Values are ranked (average ties, as a share of the non-NULL rows of the sample) before anything else.
- rho_wq: pairwise complete. Rows where both columns are non-NULL; inside each query (anchor, user_id) both
  ranks are centred on the mean of those rows; queries with fewer than two such rows drop out; Pearson of the
  centred ranks. Undefined (None) with fewer than MIN_ROWS effective rows or no within-query variance.
- R2_wq: rows where the card column is non-NULL; a reference NULL becomes 0 and the reference gets a NULL
  indicator column (only if its NULL share among those rows is strictly between 0 and 1); the response and
  every regressor are centred inside each query; OLS by the normal equations (minimum-norm solution);
  R2 = explained / total centred sum of squares. Computed on the first R2_QUERIES queries of the sample.
- A user-level query (keys = user_id only) is constant inside a query, so its within-query statistics are
  void. Its columns use mode 'between': one row per query, the card value against the query mean of every
  reference rank, ranked again across queries; plain Spearman and R2 with an intercept.
- i_cat_l1 (VARCHAR) is not a reference: only numeric columns of the base enter (79 of the 80).
"""
import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from council import roles
from scripts.xfer_agent import NONDETERMINISTIC  # the same expression as the transfer agent
from task1 import extra as X
from task1.model import EXTRA as _EXTRA, GROUPS

FORMAT = 'council-probe-v1'
CARD_FORMAT = 'council-card-probe-v1'
VERSION = 2                       # bump when a statistic changes: cached probes of another version are recomputed

# Paths and the reference set, module globals so that tests can patch them.
DAYS6 = roles.DAYS6
EXTRA = _EXTRA
PROBES = roles.PROBES
TABLES = list(roles.HPLUS)

SAMPLE_QUERIES = 3000             # rho_wq sample per day, by hash(user_id)
R2_QUERIES = 1000                 # R2_wq on the first queries of that sample
CROSS_QUERIES = 1000              # values kept for card-card statistics (twins, duplicates inside the council)
MIN_ROWS = 1000                   # effective rows of a within-query statistic
MIN_QUERIES = 100                 # queries of a between-query statistic
TOLERANCE = 1e-9                  # batch invariance, relative
CTX_CACHE = 3                     # day contexts kept in memory
CHUNK = 16                        # reference columns per vectorised step
RANK_THREADS = 10
MEMORY = '4GB'                    # DuckDB limit of the own connections (it spills beyond)
BLOCK = 50_000                     # rows per block of the normal equations
MAX_ANSWER_CELLS = 600_000_000     # rows x columns of one day's answer: beyond it task1.extra fetches it into pandas
                                   # and dies; a change of the cap needs a VERSION bump (cached probes)

# Curator thresholds (contract 3.4 step 6).
MAX_SECONDS = 60.0
MIN_COVERAGE = 0.005
R2_DUP = 0.9
RHO_DUP = 0.95
TWIN_COVERAGE = 0.10
TWIN_RHO = 0.8
PER_LENS = 3
MAX_FAMILIES = 12
TWINS = 4
PLACEBO = 4
PARITY_TOL = 0.1
LENSES = ('G1', 'G2', 'G3', 'G4')

KEYS = ('user_id', 'product_id')
CARD_FIELDS = ('id', 'lens', 'name', 'mechanism', 'sign', 'stratum', 'null_stratum', 'sql', 'twin', 'rival')
CARD_ID = re.compile(r'G([1-4])-([0-9]+)')
SLUG = re.compile(r'[a-z][a-z0-9_]*')
COLUMN = re.compile(r'f_x_c([1-4])_[a-z0-9_]+')
TOKEN = re.compile(r'\bf_x_\w+', re.I)
TWIN_HOW = ('time_shuffle', 'neighbour_shuffle', 'seeds_removed')
NUMERIC = re.compile(r'(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|REAL|BOOLEAN|DECIMAL.*)', re.I)

_CTX = {}


# ---------------------------------------------------------------- sandbox

def sandbox(t, threads=8, half=None):
    """task1.extra.sandbox; with half in {0, 1} `active_users` keeps only users with hash(user_id) % 2 == half."""
    con = X.sandbox(t, threads)
    if half is not None:
        con.execute(f"DELETE FROM active_users WHERE hash(user_id) % 2 <> {int(half)}")
    return con


class _Capped:
    """A sandbox connection for task1.extra.run_query that sizes the answer before anything else reads it:
    an answer over MAX_ANSWER_CELLS is a FeatureError instead of a crash of the process."""

    def __init__(self, con, t):
        self._con, self._t = con, t

    def execute(self, query, *args):
        if query == 'DESCRIBE _x':
            n = self._con.execute('SELECT count(*) FROM _x').fetchone()[0]
            w = len(self._con.execute('DESCRIBE _x').fetchall())
            if n * w > MAX_ANSWER_CELLS:
                raise X.FeatureError(f'answer of {n} rows x {w} columns on {self._t[:10]}, over '
                                     f'{MAX_ANSWER_CELLS} cells: not restricted to candidates')
        return self._con.execute(query, *args)

    def __getattr__(self, name):
        return getattr(self._con, name)


@contextlib.contextmanager
def capped_extra():
    """task1.extra.compute under the same cap: its sandbox connections are _Capped while the block runs."""
    plain = X.sandbox
    X.sandbox = lambda t, threads=8: _Capped(plain(t, threads), t)
    try:
        yield
    finally:
        X.sandbox = plain


def _run(sql, t, threads, half=None):
    """(keys, values, frame, seconds of the query) of one sandbox run."""
    con = sandbox(t, threads, half)
    try:
        t0 = time.perf_counter()
        keys, values, x = X.run_query(_Capped(con, t), sql, t)
        return keys, values, x, time.perf_counter() - t0
    finally:
        con.close()


def _numeric(x, keys, values):
    """Keys as int64 and values as float64; values that are not numbers are an error (as task1.extra.compute)."""
    out = pd.DataFrame({k: x[k].astype(np.int64) for k in keys})
    for c in values:
        v = pd.to_numeric(x[c], errors='coerce')
        bad = int((v.isna() & x[c].notna()).sum())
        if bad:
            raise X.FeatureError(f'{bad} values of {c} are not numeric')
        out[c] = v.astype(np.float64)
    return out


def _level(keys):
    return 'pair' if len(keys) == 2 else ('user' if keys == ['user_id'] else 'product')


# ---------------------------------------------------------------- statistics

def _pct(m):
    """Column ranks as a share of the non-NULL rows (average ties); NaN stays NaN."""
    m = np.asarray(m, dtype=np.float64)
    if m.ndim == 1:
        return pd.Series(m).rank(method='average', pct=True).to_numpy()
    if not m.shape[1]:
        return m.copy()

    def one(j):
        return pd.Series(m[:, j]).rank(method='average', pct=True).to_numpy()
    with ThreadPoolExecutor(min(RANK_THREADS, m.shape[1])) as ex:
        return np.column_stack(list(ex.map(one, range(m.shape[1]))))


def _starts(q):
    """Start index of every group of a sorted code array."""
    q = np.asarray(q)
    if not len(q):
        return np.zeros(0, dtype=np.int64)
    return np.flatnonzero(np.r_[True, q[1:] != q[:-1]])


def rho_grouped(a, R, starts, min_rows):
    """Pearson of a (n,) with every column of R (n, J) after centring inside groups, pairwise complete;
    NaN where undefined. Rows must be sorted by group; starts from _starts."""
    a = np.asarray(a, dtype=np.float64)
    R = np.asarray(R)
    if R.ndim == 1:
        R = R[:, None]
    J = R.shape[1]
    out = np.full(J, np.nan)
    if not len(a) or not J:
        return out
    ma = np.isfinite(a)
    a0 = np.where(ma, a, 0.0)
    for j0 in range(0, J, CHUNK):
        Rc = np.asarray(R[:, j0:j0 + CHUNK], dtype=np.float64)
        M = ma[:, None] & np.isfinite(Rc)
        Mf = M.astype(np.float64)
        r0 = np.where(M, Rc, 0.0)
        aa = a0[:, None] * Mf

        def S(Z):
            return np.add.reduceat(Z, starts, axis=0)
        n, sa, sr = S(Mf), S(aa), S(r0)
        sar, saa, srr = S(aa * r0), S(aa * aa), S(r0 * r0)
        keep = n > 1
        with np.errstate(divide='ignore', invalid='ignore'):
            inv = np.where(keep, 1.0 / n, 0.0)
            c = np.where(keep, sar - sa * sr * inv, 0.0).sum(0)
            va = np.where(keep, saa - sa * sa * inv, 0.0).sum(0)
            vr = np.where(keep, srr - sr * sr * inv, 0.0).sum(0)
            eff = np.where(keep, n, 0.0).sum(0)
            rho = c / np.sqrt(va * vr)
        ok = (eff >= min_rows) & (va > 1e-12 * np.maximum(eff, 1)) & (vr > 1e-12 * np.maximum(eff, 1))
        out[j0:j0 + Rc.shape[1]] = np.where(ok, np.clip(rho, -1, 1), np.nan)
    return out


def r2_grouped(y, R, q, min_rows):
    """R2 of y on the columns of R inside groups q (sorted): rows with y non-NULL, NULL -> 0 plus an indicator,
    everything centred inside groups, minimum-norm OLS. None where undefined. Normal equations are summed over
    row blocks of whole groups, so memory stays at one block."""
    y = np.asarray(y, dtype=np.float64)
    R = np.asarray(R)
    if R.ndim == 1:
        R = R[:, None]
    rows = np.flatnonzero(np.isfinite(y))
    if len(rows) < 2 or not R.shape[1]:
        return None
    y, q = y[rows], np.asarray(q)[rows]
    starts = _starts(q)
    counts = np.diff(np.r_[starts, len(y)])
    if counts[counts > 1].sum() < min_rows:
        return None
    nulls = np.zeros(R.shape[1])
    for b0 in range(0, len(rows), BLOCK):
        nulls += (~np.isfinite(R[rows[b0:b0 + BLOCK]])).sum(0)
    ind = np.flatnonzero((nulls > 0) & (nulls < len(rows)))
    k = R.shape[1] + len(ind)
    xtx, xty, yty = np.zeros((k, k)), np.zeros(k), 0.0
    edges = list(starts[::max(1, len(starts) * BLOCK // len(rows))]) + [len(rows)]
    for b0, b1 in zip(edges[:-1], edges[1:]):
        if b1 <= b0:
            continue
        Rb = np.asarray(R[rows[b0:b1]], dtype=np.float64)
        nan = ~np.isfinite(Rb)
        D = np.concatenate([np.where(nan, 0.0, Rb), nan[:, ind].astype(np.float64)], axis=1)
        del Rb, nan
        st = _starts(q[b0:b1])
        cn = np.diff(np.r_[st, b1 - b0])
        D -= np.repeat(np.add.reduceat(D, st, axis=0) / cn[:, None], cn, axis=0)
        yb = y[b0:b1] - np.repeat(np.add.reduceat(y[b0:b1], st) / cn, cn)
        xtx += D.T @ D
        xty += D.T @ yb
        yty += float(yb @ yb)
    if yty <= 1e-12 * len(y):
        return None
    beta = np.linalg.lstsq(xtx, xty, rcond=None)[0]
    return float(np.clip(beta @ xty / yty, 0.0, 1.0))


def _query_level(m, starts):
    """Query mean of every column over its non-NULL rows (NaN if none), ranked again across queries."""
    m = np.asarray(m, dtype=np.float64)
    if m.ndim == 1:
        m = m[:, None]
    fin = np.isfinite(m)
    s = np.add.reduceat(np.where(fin, m, 0.0), starts, axis=0)
    n = np.add.reduceat(fin.astype(np.float64), starts, axis=0)
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = np.where(n > 0, s / n, np.nan)
    return _pct(mean)


def column_stats(a, R, names, q, mode, r2_rows=None):
    """rho to every reference, max |rho|, nearest and R2 of one card column (raw values a on sorted rows q)."""
    starts = _starts(q)
    if mode == 'between':
        ya = _query_level(a, starts)[:, 0]
        Rq = _query_level(R, starts)
        one = np.zeros(1, dtype=np.int64)
        rho = rho_grouped(ya, Rq, one, MIN_QUERIES)
        r2 = r2_grouped(ya, Rq, np.zeros(len(ya)), MIN_QUERIES)
    else:
        ya = _pct(a)
        rho = rho_grouped(ya, R, starts, MIN_ROWS)
        n = len(ya) if r2_rows is None else r2_rows
        r2 = r2_grouped(ya[:n], R[:n], q[:n], MIN_ROWS)
    finite = np.isfinite(rho)
    best = int(np.argmax(np.where(finite, np.abs(rho), -1))) if finite.any() else None
    return dict(mode=mode,
                max_abs_rho=None if best is None else round(float(abs(rho[best])), 4),
                nearest=None if best is None else names[best],
                r2=None if r2 is None else round(r2, 4),
                rho={n: round(float(v), 4) for n, v in zip(names, rho) if np.isfinite(v)})


# ---------------------------------------------------------------- day context

def _con(threads=4):
    con = duckdb.connect()
    con.execute(f"SET threads={int(threads)}; SET enable_progress_bar=false; SET memory_limit='{MEMORY}'")
    return con


def _describe(con, path):
    return [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()]


def base_columns(schema):
    """Numeric feature columns of a day table by positive selection: names starting with GROUPS."""
    return [c for c, t in schema if c.startswith(GROUPS) and NUMERIC.fullmatch(str(t))]


def _context(day, threads=10):
    """Sample of <= SAMPLE_QUERIES queries of a day (order hash(user_id), user_id), with the ranks of the
    references (base of days6 and the tables of TABLES); rows sorted by query and product."""
    key = (str(DAYS6), str(EXTRA), tuple(TABLES), day, SAMPLE_QUERIES)
    if key in _CTX:
        return _CTX[key]
    f = Path(DAYS6) / f'{day}.parquet'
    con = _con(threads)
    blocks = []
    try:
        base = base_columns(_describe(con, f))
        con.execute(f"""CREATE TEMP TABLE s AS
            WITH q AS (SELECT anchor, user_id, row_number() OVER (ORDER BY hash(user_id), user_id, anchor) - 1 qn
                       FROM (SELECT DISTINCT anchor, user_id FROM read_parquet('{f}'))
                       QUALIFY qn < {int(SAMPLE_QUERIES)})
            SELECT row_number() OVER (ORDER BY q.qn, c.product_id) - 1 rn, q.qn, c.anchor, c.user_id, c.product_id
                   {''.join(f', c."{b}"' for b in base)}
            FROM read_parquet('{f}') c JOIN q ON c.anchor = q.anchor AND c.user_id = q.user_id""")
        keys = con.execute("SELECT qn, anchor, user_id, product_id FROM s ORDER BY rn").df()
        names = list(base)
        blocks.append(('s', base, None, None))
        for tab in TABLES:
            tf = Path(EXTRA) / tab / f'{day}.parquet'
            if not tf.exists():
                raise X.FeatureError(f'reference table {tab} lacks {day}')
            cols = [c for c, _ in _describe(con, tf)]
            tk = [k for k in KEYS if k in cols]
            vals = [c for c in cols if c.startswith('f_x_')]
            clash = set(vals) & set(names)
            if clash:
                raise X.FeatureError(f'reference columns repeat: {sorted(clash)[:3]}')
            names += vals
            blocks.append((tab, vals, tf, tk))
        ranks = np.empty((len(keys), len(names)), dtype=np.float32)
        j0 = 0
        for tab, vals, tf, tk in blocks:   # one table at a time: memory stays at one join
            if tf is None:
                x = con.execute(f"SELECT {', '.join(f'"{v}"' for v in vals)} FROM s ORDER BY rn").df()
            else:
                k = ', '.join(tk)
                on = ' AND '.join(f's.{c} = t.{c}' for c in tk)
                x = con.execute(f"""SELECT {', '.join(f't."{v}"' for v in vals)} FROM s LEFT JOIN
                    (SELECT * FROM read_parquet('{tf}') SEMI JOIN (SELECT DISTINCT {k} FROM s) USING ({k})) t ON {on}
                    ORDER BY s.rn""").df()

            def one(j, x=x, j0=j0):
                v = x.iloc[:, j].to_numpy(dtype=np.float64, na_value=np.nan)
                v = np.where(np.isfinite(v), v, np.nan)
                ranks[:, j0 + j] = pd.Series(v).rank(method='average', pct=True).to_numpy()
            with ThreadPoolExecutor(RANK_THREADS) as ex:
                list(ex.map(one, range(len(vals))))
            j0 += len(vals)
    finally:
        con.close()
    ctx = dict(day=day, names=names, keys=keys[['anchor', 'user_id', 'product_id']],
               q=keys.qn.to_numpy(dtype=np.int64), ranks=ranks, n_queries=int(keys.qn.nunique()))
    while len(_CTX) >= CTX_CACHE:
        _CTX.pop(next(iter(_CTX)))
    _CTX[key] = ctx
    return ctx


def _prefix(q, queries):
    """Rows of the first `queries` queries (q sorted, codes 0..)."""
    return int(np.searchsorted(q, queries, side='left'))


# ---------------------------------------------------------------- probe

def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    with os.fdopen(fd, 'w') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _to_parquet(df, path):
    con = _con()
    try:
        con.register('df_', df)
        con.execute(f"COPY (SELECT * FROM df_) TO '{path}' (FORMAT PARQUET)")
    finally:
        con.close()


def _read_parquet(path):
    con = _con()
    try:
        return con.execute(f"SELECT * FROM read_parquet('{path}')").df()
    finally:
        con.close()


def _coverage(x, keys, values, day, threads):
    """Candidate rows of the day and the non-NULL (finite) share of every value column among them."""
    f = Path(DAYS6) / f'{day}.parquet'
    con = _con(threads)
    try:
        con.register('x', x)
        on = ' AND '.join(f'c.{k} = x.{k}' for k in keys)
        cnt = ', '.join(f'count(*) FILTER (WHERE isfinite(x."{v}"))' for v in values)
        row = con.execute(f"""SELECT count(*), {cnt} FROM (SELECT anchor, user_id, product_id FROM read_parquet('{f}')) c
                              LEFT JOIN x ON {on}""").fetchone()
    finally:
        con.close()
    n = int(row[0])
    return n, {v: (row[i + 1] / n if n else 0.0) for i, v in enumerate(values)}


def _batch(sql, t, day, keys, values, x, threads):
    """Batch invariance: the full answer against the union of the answers on the two hash halves of
    active_users, on the candidate keys of the level. Each candidate user takes the half it belongs to."""
    halves, seconds = [], []
    for h in (0, 1):
        k2, v2, x2, s = _run(sql, t, threads, half=h)
        seconds.append(round(s, 3))
        if k2 != keys or v2 != values:
            return dict(invariant=False, reason=f'columns differ: half {h} returns {k2 + v2}, the full run '
                        f'{keys + values}', seconds=seconds)
        halves.append(_numeric(x2, k2, v2))
    f = Path(DAYS6) / f'{day}.parquet'
    con = _con(threads)
    try:
        con.register('full_', x)
        con.register('h0', halves[0])
        con.register('h1', halves[1])
        k = ', '.join(keys)
        same = ' AND '.join(f'((a."{v}" IS NULL AND b."{v}" IS NULL) OR '
                            f'(isnan(a."{v}") AND isnan(b."{v}")) OR (a."{v}" = b."{v}") OR '
                            f'abs(a."{v}" - b."{v}") <= {TOLERANCE} * greatest(1, abs(a."{v}")))'
                            for v in values)
        on_a = ' AND '.join(f'c.{c} = a.{c}' for c in keys)
        on_b = ' AND '.join(f'c.{c} = b.{c}' for c in keys)
        pa, pb = f'a.{keys[0]} IS NOT NULL', f'b.{keys[0]} IS NOT NULL'
        checked, key_diff, value_diff = con.execute(f"""
            WITH c AS (SELECT DISTINCT {k} FROM read_parquet('{f}')),
                 u AS (SELECT * FROM h0 WHERE hash(user_id) % 2 = 0 UNION ALL SELECT * FROM h1 WHERE hash(user_id) % 2 = 1)
            SELECT count(*), count(*) FILTER (WHERE ({pa}) <> ({pb})),
                   count(*) FILTER (WHERE {pa} AND {pb} AND NOT coalesce({same}, false))
            FROM c LEFT JOIN full_ a ON {on_a} LEFT JOIN u b ON {on_b}""").fetchone()
    finally:
        con.close()
    reasons = []
    if key_diff:
        reasons.append(f'keys differ: {key_diff} candidate keys are answered in one run only')
    if value_diff:
        reasons.append(f'values differ: {value_diff} candidate keys have other values in their half')
    return dict(invariant=not reasons, checked=int(checked), key_mismatches=int(key_diff),
                value_mismatches=int(value_diff), reason='; '.join(reasons) or None, seconds=seconds)


def _probe_day(sql, day, threads):
    t = f'{day} 00:00:00'
    keys, values, raw, seconds = _run(sql, t, threads)
    x = _numeric(raw, keys, values)
    del raw
    rec = dict(seconds=round(seconds, 3), rows=len(x), keys=keys, columns=values, level=_level(keys))
    rec['candidate_rows'], rec['coverage'] = _coverage(x, keys, values, day, threads)
    rec['coverage'] = {c: round(v, 6) for c, v in rec['coverage'].items()}
    rec['batch'] = _batch(sql, t, day, keys, values, x, threads) if 'user_id' in keys else None
    ctx = _context(day, threads)
    aligned = ctx['keys'][list(keys)].merge(x, how='left', on=list(keys))
    if len(aligned) != len(ctx['keys']):
        raise X.FeatureError('duplicate keys in the answer')
    mode = 'between' if rec['level'] == 'user' else 'within'
    r2_rows = _prefix(ctx['q'], R2_QUERIES)
    rec['sample'] = dict(queries=ctx['n_queries'], rows=len(aligned), r2_rows=r2_rows, references=len(ctx['names']))
    rec['stats'] = {c: column_stats(aligned[c].to_numpy(dtype=np.float64), ctx['ranks'], ctx['names'], ctx['q'],
                                    mode, r2_rows) for c in values}
    cut = _prefix(ctx['q'], CROSS_QUERIES)
    kept = ctx['keys'].iloc[:cut].copy()
    kept['anchor'] = pd.to_datetime(kept['anchor']).dt.strftime('%Y-%m-%d')
    for c in values:
        kept[c] = aligned[c].to_numpy(dtype=np.float32)[:cut]
    return rec, kept


def _summary(p):
    """Aggregates over days: coverage mean, median seconds, batch, max |rho|, nearest, max R2."""
    days = [d for d in p['days'] if d in p['per_day']]
    cols = p['columns'] or []
    sec = [p['per_day'][d]['seconds'] for d in days]
    p['seconds_median'] = float(np.median(sec)) if sec else None
    p['coverage'] = {c: round(float(np.mean([p['per_day'][d]['coverage'][c] for d in days])), 6) for c in cols}
    batches = [p['per_day'][d]['batch'] for d in days]
    p['batch_invariant'] = (None if p['level'] == 'product' or not batches
                            else all(b['invariant'] for b in batches))
    p['max_abs_rho'], p['nearest'], p['r2'] = {}, {}, {}
    for c in cols:
        best, near, r2 = None, None, None
        for d in days:
            s = p['per_day'][d]['stats'][c]
            if s['max_abs_rho'] is not None and (best is None or s['max_abs_rho'] > best):
                best, near = s['max_abs_rho'], s['nearest']
            if s['r2'] is not None and (r2 is None or s['r2'] > r2):
                r2 = s['r2']
        p['max_abs_rho'][c], p['nearest'][c], p['r2'][c] = best, near, r2
    p['parity'] = parity(p)
    return p


def probe_path(sql):
    return Path(PROBES) / f'{_sha(sql)[:16]}.json'


def probe(card_or_sql, days=roles.PROBE_DAYS, threads=10):
    """Evidence without targets of one SQL (a dict, cached in PROBES/<sha256(sql)[:16]>.json) or of a card
    (validation, the probe of its SQL and of its twin, twin_check)."""
    if isinstance(card_or_sql, dict):
        return _probe_card(card_or_sql, days, threads)
    sql = card_or_sql
    days = [str(d)[:10] for d in days]
    path = probe_path(sql)
    if path.exists():
        cached = json.loads(path.read_text())
        if (cached.get('format') == FORMAT and cached.get('version') == VERSION and cached.get('days') == days
                and cached.get('references') == TABLES):
            return cached
    p = dict(format=FORMAT, version=VERSION, sha256=_sha(sql), key=path.stem, sql=sql, days=days,
             references=TABLES, sample_queries=SAMPLE_QUERIES, r2_queries=R2_QUERIES, threads=threads,
             check=None, nondeterministic=None, error=None, keys=None, level=None, columns=None, per_day={},
             values=None)
    try:
        X.check_sql(sql)
    except X.FeatureError as e:
        p['check'] = str(e)
    hit = NONDETERMINISTIC.search(sql)
    if hit:
        p['nondeterministic'] = hit.group(0)
    frames = []
    if not p['check'] and not p['nondeterministic']:
        for d in days:
            try:
                rec, kept = _probe_day(sql, d, threads)
            except X.FeatureError as e:
                p['error'] = f'{d}: {e}'
                break
            if p['columns'] is None:
                p['keys'], p['level'], p['columns'] = rec['keys'], rec['level'], rec['columns']
            elif rec['keys'] != p['keys'] or rec['columns'] != p['columns']:
                p['error'] = f'{d}: keys or columns differ between days: {rec["keys"] + rec["columns"]}'
                break
            p['per_day'][d] = rec
            frames.append(kept)
    if frames and not p['error']:
        vpath = path.with_suffix('.values.parquet')
        tmp = vpath.with_name('.' + vpath.name)
        vpath.parent.mkdir(parents=True, exist_ok=True)
        _to_parquet(pd.concat(frames, ignore_index=True), tmp)
        os.replace(tmp, vpath)
        p['values'] = vpath.name
    _summary(p)
    _write_json(path, p)
    return p


def _probe_card(card, days, threads):
    problems = validate_card(card)
    out = dict(format=CARD_FORMAT, id=card.get('id'), problems=problems, card=None, twin=None, twin_check=None)
    if not isinstance(card.get('sql'), str) or not isinstance((card.get('twin') or {}).get('sql'), str):
        return out
    p = probe(card['sql'], days, threads)
    tw = probe(card['twin']['sql'], days, threads)
    out['card'], out['twin'] = p, tw
    if p['columns'] is not None:
        digit = CARD_ID.fullmatch(str(card.get('id'))).group(1) if CARD_ID.fullmatch(str(card.get('id'))) else None
        if not 1 <= len(p['columns']) <= 4:
            problems.append(f'{len(p["columns"])} value columns, 1-4 allowed')
        for c in p['columns']:
            m = COLUMN.fullmatch(c)
            if not m or m.group(1) != digit:
                problems.append(f'column {c} is not f_x_c{digit}_<slug>')
    if p['columns'] is not None and tw['columns'] is not None:
        if tw['columns'] != [c + '_tw' for c in p['columns']]:
            problems.append(f'twin columns {tw["columns"]} are not the card columns + _tw')
        if tw['keys'] != p['keys']:
            problems.append(f'twin keys {tw["keys"]} differ from the card keys {p["keys"]}')
    out['twin_check'] = twin_check(p, tw)
    return out


# ---------------------------------------------------------------- verdicts

def machine_red(p):
    """Reasons the machine test of a SQL probe is red; [] when green."""
    out = []
    if p.get('check'):
        out.append(f'invalid: {p["check"]}')
    if p.get('nondeterministic'):
        out.append(f'NONDETERMINISTIC: {p["nondeterministic"]}')
    if p.get('error'):
        out.append(f'error: {p["error"]}')
    if not out and not p.get('per_day'):
        out.append('error: no day was probed')
    if p.get('batch_invariant') is False:
        bad = {d: r['batch']['reason'] for d, r in p.get('per_day', {}).items()
               if r.get('batch') and not r['batch']['invariant']}
        out.append(f'batch: the answer depends on the batch of active_users ({json.dumps(bad, sort_keys=True)})')
    return out


def parity(p):
    """Non-NULL share of every column per day inside [0.5 min, 2 max] of the other days."""
    days = [d for d in p.get('days', []) if d in p.get('per_day', {})]
    cols = {}
    for c in p.get('columns') or []:
        shares = {d: p['per_day'][d]['coverage'][c] for d in days}
        outside = []
        for d, s in shares.items():
            others = [v for e, v in shares.items() if e != d]
            if others and not (0.5 * min(others) <= s <= 2 * max(others)):
                outside.append(d)
        cols[c] = dict(shares=shares, outside=outside)
    return dict(ok=all(not v['outside'] for v in cols.values()), days=len(days), columns=cols)


def _values(p):
    if not p.get('values'):
        return None
    return _read_parquet(Path(PROBES) / p['values'])


def cross(pa, pb):
    """Card-card statistics on the stored sample rows: rho_wq of every column pair, max |rho| and R2 of each
    side on the columns of the other. Mode 'between' when either side is user-level."""
    va, vb = _values(pa), _values(pb)
    if va is None or vb is None:
        return None
    k = ['anchor', 'user_id', 'product_id']
    ca, cb = list(pa['columns']), list(pb['columns'])
    m = va[k + ca].merge(vb[k + cb].rename(columns={c: c + '\x00b' for c in cb}), on=k, how='inner')
    m = m.sort_values(['anchor', 'user_id', 'product_id'], kind='stable').reset_index(drop=True)
    q = m.groupby(['anchor', 'user_id'], sort=False).ngroup().to_numpy()
    q = pd.factorize(q)[0]
    starts = _starts(q)
    A = m[ca].to_numpy(dtype=np.float64)
    B = m[[c + '\x00b' for c in cb]].to_numpy(dtype=np.float64)
    between = 'user' in (pa.get('level'), pb.get('level'))
    if between:
        A, B = _query_level(A, starts), _query_level(B, starts)
        starts, q, low = np.zeros(1, dtype=np.int64), np.zeros(len(A), dtype=np.int64), MIN_QUERIES
    else:
        A, B, low = _pct(A), _pct(B), MIN_ROWS
    rho = {a: {} for a in ca}
    best = None
    for i, a in enumerate(ca):
        r = rho_grouped(A[:, i], B, starts, low)
        for j, b in enumerate(cb):
            rho[a][b] = None if not np.isfinite(r[j]) else round(float(r[j]), 4)
            if rho[a][b] is not None and (best is None or abs(rho[a][b]) > best):
                best = abs(rho[a][b])
    r2_ab = {a: r2_grouped(A[:, i], B, q, low) for i, a in enumerate(ca)}
    r2_ba = {b: r2_grouped(B[:, j], A, q, low) for j, b in enumerate(cb)}
    return dict(mode='between' if between else 'within', rows=len(m), rho=rho, max_abs_rho=best,
                r2_a_on_b=r2_ab, r2_b_on_a=r2_ba)


def twin_check(card_probe, twin_probe):
    """Twin shape: coverage within +-10% of the card column and |rho_wq(card, twin)| <= 0.8 on the same
    rows; else TWIN-BROKEN with the reasons."""
    reasons = []
    for side, p in (('card', card_probe), ('twin', twin_probe)):
        red = machine_red(p)
        if red:
            reasons.append(f'{side} machine test red: {red[0]}')
    cols = card_probe.get('columns') or []
    if not reasons and twin_probe.get('columns') != [c + '_tw' for c in cols]:
        reasons.append(f'twin columns {twin_probe.get("columns")} are not {[c + "_tw" for c in cols]}')
    detail = {}
    if not reasons:
        cr = cross(card_probe, twin_probe)
        for c in cols:
            cov, cov_tw = card_probe['coverage'][c], twin_probe['coverage'][c + '_tw']
            r = None if cr is None else cr['rho'][c][c + '_tw']
            detail[c] = dict(coverage=cov, coverage_twin=cov_tw, rho=r)
            if abs(cov_tw - cov) > TWIN_COVERAGE * cov:
                reasons.append(f'{c}: coverage {cov:.4f}, twin {cov_tw:.4f}, outside +-{TWIN_COVERAGE:.0%}')
            if r is None:
                reasons.append(f'{c}: rho_wq with the twin is undefined')
            elif abs(r) > TWIN_RHO:
                reasons.append(f'{c}: |rho_wq| with the twin {abs(r):.3f} > {TWIN_RHO}')
    return dict(verdict='ok' if not reasons else 'TWIN-BROKEN', reasons=reasons, columns=detail)


# ---------------------------------------------------------------- card schema

def validate_card(card):
    """Problems of a card against the schema of contract 3.4; [] when valid."""
    if not isinstance(card, dict):
        return ['a card is a JSON object']
    out = []
    missing = [f for f in CARD_FIELDS if f not in card]
    extra = [f for f in card if f not in CARD_FIELDS]
    if missing:
        out.append(f'missing fields {missing}')
    if extra:
        out.append(f'unknown fields {extra}')
    m = CARD_ID.fullmatch(str(card.get('id', '')))
    if not m:
        out.append(f'id {card.get("id")!r} is not G<1-4>-<n>')
    elif card.get('lens') != f'G{m.group(1)}':
        out.append(f'lens {card.get("lens")!r} differs from the id {card.get("id")}')
    if not isinstance(card.get('name'), str) or not SLUG.fullmatch(card.get('name', '')):
        out.append('name is not a snake_case slug')
    if card.get('sign') not in ('+', '-'):
        out.append('sign is not + or -')
    for f in ('mechanism', 'stratum', 'null_stratum', 'sql'):
        if not isinstance(card.get(f), str) or not card.get(f).strip():
            out.append(f'{f} is empty')
    twin, rival = card.get('twin'), card.get('rival')
    if not isinstance(twin, dict) or set(twin) != {'how', 'sql'}:
        out.append('twin is not {how, sql}')
        twin = {}
    elif twin.get('how') not in TWIN_HOW:
        out.append(f'twin.how is not one of {TWIN_HOW}')
    if not isinstance(rival, dict) or set(rival) != {'explanation', 'stratum'} or not all(
            isinstance(v, str) and v.strip() for v in rival.values()):
        out.append('rival is not {explanation, stratum} with text')
    digit = m.group(1) if m else None
    names = []
    for side, sql in (('sql', card.get('sql')), ('twin.sql', twin.get('sql'))):
        if not isinstance(sql, str) or not sql.strip():
            if side == 'twin.sql':
                out.append('twin.sql is empty')
            continue
        try:
            X.check_sql(sql)
        except X.FeatureError as e:
            out.append(f'{side}: {e}')
        hit = NONDETERMINISTIC.search(sql)
        if hit:
            out.append(f'{side}: NONDETERMINISTIC {hit.group(0)}')
        if not re.search(r'\b(user_id|product_id)\b', sql):
            out.append(f'{side}: no user_id/product_id key')
        tokens = sorted({t.lower() for t in TOKEN.findall(sql)})
        if side == 'sql':
            names = tokens
            if not 1 <= len(names) <= 4:
                out.append(f'sql names {len(names)} f_x_ columns, 1-4 allowed')
            for n in names:
                c = COLUMN.fullmatch(n)
                if not c or c.group(1) != digit or n.endswith('_tw'):
                    out.append(f'column {n} is not f_x_c{digit}_<slug>')
        else:
            tw = {t for t in tokens if t.endswith('_tw')}
            if tw != {n + '_tw' for n in names}:
                out.append(f'twin columns {sorted(tw)} are not the card columns + _tw')
            other = set(tokens) - tw - set(names)
            if other:
                out.append(f'twin.sql names other f_x_ columns {sorted(other)}')
    return out


# ---------------------------------------------------------------- curator

def _order(card_id):
    m = CARD_ID.fullmatch(str(card_id))
    return (int(m.group(1)), int(m.group(2))) if m else (9, 10 ** 9)


def _widths(reference_width):
    if reference_width is None:
        return [], 0
    if isinstance(reference_width, (int, np.integer)):
        return None, int(reference_width)
    items = [(str(t), int(w)) for t, w in (reference_width.items() if isinstance(reference_width, dict)
                                           else reference_width)]
    return items, sum(w for _, w in items)


def _step1(p):
    """Reason step 1 removes a SQL probe (invalid, red, slow, thin, parity across days broken), or None."""
    red = machine_red(p)
    if red:
        return 'machine test red: ' + red[0]
    if p.get('seconds_median') is None or p['seconds_median'] > MAX_SECONDS:
        return f'median seconds {p.get("seconds_median")} > {MAX_SECONDS:.0f}'
    if not p.get('coverage') or min(p['coverage'].values()) < MIN_COVERAGE:
        return f'coverage {min((p.get("coverage") or {None: 0.0}).values()):.4%} < {MIN_COVERAGE:.1%}'
    if not p['parity']['ok']:
        bad = {c: v['outside'] for c, v in p['parity']['columns'].items() if v['outside']}
        return f'non-NULL parity across days broken: {bad}'
    return None


def _dup_hplus(p):
    """Reason step 2 removes a SQL probe as a duplicate of H+ (R2_wq >= 0.9 or max|rho_wq| >= 0.95), or None."""
    for c in p['columns']:
        if (p['r2'][c] is not None and p['r2'][c] >= R2_DUP) or (
                p['max_abs_rho'][c] is not None and p['max_abs_rho'][c] >= RHO_DUP):
            return f'duplicate of H+: {c} R2_wq {p["r2"][c]}, max|rho_wq| {p["max_abs_rho"][c]} ({p["nearest"][c]})'
    return None


def _dup_cross(cr):
    """(max|rho|, max R2) when two probes duplicate each other, else None."""
    if cr is None:
        return None
    r2 = max([v for v in list(cr['r2_a_on_b'].values()) + list(cr['r2_b_on_a'].values()) if v is not None],
             default=None)
    if (cr['max_abs_rho'] is not None and cr['max_abs_rho'] >= RHO_DUP) or (r2 is not None and r2 >= R2_DUP):
        return cr['max_abs_rho'], r2
    return None


def _filter_reference(reference_probes, cross_fn):
    """Steps 1 and 2 for the reference arm (contract 2: the same contract as the council). The order is kept;
    inside Rb1 u Rb2 the earlier table stays."""
    removed, kept = [], []
    for table, p in reference_probes.items():
        why = _step1(p)
        step = 1
        if why is None:
            why, step = _dup_hplus(p), 2
        if why is None:
            for other in kept:
                dup = _dup_cross(cross_fn(p, reference_probes[other]))
                if dup:
                    why = f'duplicate of {other}: max|rho_wq| {dup[0]}, R2_wq {dup[1]}'
                    break
        if why:
            removed.append(dict(table=table, step=step, reason=why))
        else:
            kept.append(table)
    return [(t, len(reference_probes[t]['columns'])) for t in kept], removed


def curate(cards, probes, reference_width=None, critiques=(), cross_fn=None, reference_probes=None):
    """The curator code (contract 3.4 step 6 and the width parity of section 2); no targets are read.

    cards             card dicts.
    probes            {card id: probe(card)}: {'card': SQL probe, 'twin': SQL probe, 'problems': [...]}.
    reference_probes  {table: probe(sql)} of the reference arm in its order: Rb1 tables by proposal, then Rb2
                      (cutting from the end removes Rb2 first). Steps 1 and 2 apply to it before parity, the
                      same as to the council; parity uses the width after this filter.
    reference_width   only without reference_probes (tests): [(table, columns), ...] in the same order, or an
                      int; the result then carries a warning that the reference arm was not filtered.
    critiques         [{'card': id, 'type': ...}, ...]; type WITHDRAWN = the author withdrew the card. LEAK
                      vetoes only with a red machine test (already step 1); other types do not remove a card.
    cross_fn          probe-probe statistics, default cross().

    Steps: 1 removal, 2 duplicates (to H+ by R2/rho of the probe; inside the council the card with fewer
    columns stays, ties by lens G1..G4 and number), 3 quotas (round robin over lenses by number, <= 3 per
    lens, <= 12), parity of section 2 (cuts the lowest-priority families or the end of the reference order;
    if the cut overshoots the tolerance, the other side is cut), then 4 twins and 5 placebo on the families
    that remain. Deterministic: only sorting by ids and hashes.

    Raises SystemExit when no family is left, when the reference width is 0, or when parity is not reached."""
    cross_fn = cross_fn or cross
    warnings = []
    if reference_probes is not None:
        if reference_width is not None:
            warnings.append('reference_width ignored: the widths come from reference_probes')
        items, reference_removed = _filter_reference(reference_probes, cross_fn)
    else:
        warnings.append('reference arm not filtered: no reference_probes (steps 1 and 2 not applied to Rb)')
        items, reference_removed = _widths(reference_width)[0], []
    w_r = _widths(reference_width)[1] if items is None else sum(w for _, w in items)
    if w_r <= 0:
        raise SystemExit(f'curate: the reference width is 0 after the filter ({reference_removed})')

    removed = []
    by_id = {}
    for card in sorted(cards, key=lambda c: _order(c.get('id'))):
        by_id[card.get('id')] = card
    withdrawn = {c.get('card') for c in critiques if str(c.get('type', '')).upper() == 'WITHDRAWN'}
    alive = []
    for cid, card in by_id.items():
        pr = probes.get(cid)
        why = None
        if pr is None or pr.get('card') is None:
            why = 'no probe'
        elif validate_card(card) or pr.get('problems'):
            why = 'invalid: ' + '; '.join((validate_card(card) + list(pr.get('problems') or []))[:3])
        else:
            why = _step1(pr['card'])
        if why is None and cid in withdrawn:
            why = 'withdrawn by the author'
        if why:
            removed.append(dict(id=cid, step=1, reason=why))
        else:
            alive.append(cid)

    # 2. duplicates: to H+ ...
    kept = []
    for cid in alive:
        why = _dup_hplus(probes[cid]['card'])
        if why:
            removed.append(dict(id=cid, step=2, reason=why))
        else:
            kept.append(cid)
    # ... and inside the council
    pref = sorted(kept, key=lambda c: (len(probes[c]['card']['columns']),) + _order(c))
    survivors = []
    for cid in pref:
        dup = None
        for other in survivors:
            d = _dup_cross(cross_fn(probes[cid]['card'], probes[other]['card']))
            if d:
                dup = (other,) + d
                break
        if dup:
            removed.append(dict(id=cid, step=2, reason=f'duplicate of {dup[0]}: max|rho_wq| {dup[1]}, R2_wq {dup[2]}'))
        else:
            survivors.append(cid)

    # 3. quotas: round robin over lenses, by card number
    queues = {lens: sorted([c for c in survivors if by_id[c]['lens'] == lens], key=_order) for lens in LENSES}
    families, taken = [], {lens: 0 for lens in LENSES}
    while len(families) < MAX_FAMILIES and any(queues[lens] and taken[lens] < PER_LENS for lens in LENSES):
        for lens in LENSES:
            if len(families) < MAX_FAMILIES and queues[lens] and taken[lens] < PER_LENS:
                families.append(queues[lens].pop(0))
                taken[lens] += 1
    for lens in LENSES:
        for cid in queues[lens]:
            removed.append(dict(id=cid, step=3, reason=f'quota: {PER_LENS} per lens, {MAX_FAMILIES} in all'))

    if not families:
        raise SystemExit(f'curate: no family survives steps 1-3 ({len(removed)} cards removed)')

    # 6. width parity (section 2), before twins and placebo so that both come from the final families
    width = {c: len(probes[c]['card']['columns']) for c in families}
    w_c = sum(width.values())
    par = dict(w_council=w_c, w_reference=w_r, cut=[], council_removed=[], reference_drop=[])
    rest = None if items is None else list(items)

    def within():
        return abs(w_c - w_r) <= PARITY_TOL * w_r

    def cut_council():
        nonlocal w_c
        par['cut'].append('council')
        while families and w_c - w_r > PARITY_TOL * w_r:
            cid = families.pop()
            w_c -= width[cid]
            par['council_removed'].append(cid)
            removed.append(dict(id=cid, step=6, reason='width parity with the reference arm'))

    def cut_reference():
        nonlocal w_r
        if rest is None:
            raise SystemExit(f'curate: the reference arm must lose {w_r - w_c} columns, but only its width is known')
        par['cut'].append('reference')
        while rest and w_r - w_c > PARITY_TOL * w_r:
            t, w = rest.pop()
            w_r -= w
            par['reference_drop'].append(t)

    for _ in range(2):           # the larger side first; if the cut overshoots, the other side once
        if within():
            break
        cut_council() if w_c > w_r else cut_reference()
    par['w_council_after'], par['w_reference_after'] = w_c, w_r
    par['ok'] = within() and w_r > 0
    if not par['ok']:
        raise SystemExit(f'curate: width parity not reached: council {w_c}, reference {w_r}, cuts {par["cut"]}')
    if not families:
        raise SystemExit('curate: no family left after the width parity')

    # 4. twins: one per lens, the first family of the lens with a working twin; else the next lens round
    checks = {}
    for c in families:
        tc = probes[c].get('twin_check')
        if tc is None and probes[c].get('twin') is not None:
            tc = twin_check(probes[c]['card'], probes[c]['twin'])
        checks[c] = tc or dict(verdict='TWIN-BROKEN', reasons=['no twin probe'])
    twins = []
    for i, lens in enumerate(LENSES):
        if len(twins) >= TWINS:
            break
        for k in range(len(LENSES)):
            lens_k = LENSES[(i + k) % len(LENSES)]
            pick = next((c for c in families if by_id[c]['lens'] == lens_k and c not in twins
                         and checks[c]['verdict'] == 'ok'), None)
            if pick:
                twins.append(pick)
                break

    # 5. placebo: the first columns of the first 4 families in sha256(name) order
    by_hash = sorted(families, key=lambda c: (_sha(by_id[c]['name']), c))[:PLACEBO]
    placebo = [probes[c]['card']['columns'][0] for c in by_hash]

    return dict(families=families, columns={c: probes[c]['card']['columns'] for c in families},
                width=sum(width[c] for c in families), twins=twins,
                twin_checks={c: checks[c]['verdict'] for c in families}, placebo=placebo,
                placebo_families=by_hash, removed=removed, parity=par, reference_removed=reference_removed,
                reference=[t for t, _ in (rest or [])] if rest is not None else None, warnings=warnings,
                critiques={c: sorted({str(x.get('type')) for x in critiques if x.get('card') == c}) for c in families})
