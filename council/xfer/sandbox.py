"""The card sandbox, the probe data and the probes of the council on xfer (council/runs/xfer/contract.md §3.4, §8).

Sandbox = the xfer agent sandbox: xa.check_sql(dataset, sql, level) (one SELECT/WITH, the placeholder {A}, no date
literals or comments, xa.FORBIDDEN, xa.NONDETERMINISTIC, adapter.sql_rules()['check']; S also refuses text
fields), views of adapter.views(A, purpose), batch tables cand and users, levels pair/user/item of adapter.LEVELS.
A probe runs one SQL the way xfer probes a proposal (xa.sandbox over the probe keys, xa._execute in the 'table'
shape, xa._align onto the keys, xa._invariance): the output names of a card are learned from the run, while
xa.agent_columns needs them beforehand (`_frozen`), so it serves the reference columns here and compute.py.
xfer writes nothing to disk on these calls.

Names: a card writes f_x_c<lens>_<slug> (1-3 value columns, xa.MAX_VALUES); the sandbox runs the SQL with
roles.sandbox_column names ag_c<lens>_<slug>; a twin adds _tw; Rb columns are ag_rb<k>_<slug>. Keys of every
frame of the council are (user_id, item_id); S maps product_id through views()['keys'] inside xfer.

Card (council JSON): the REES46 fields of council.evidence.CARD_FIELDS plus `level` (one of xa.LEVELS, shared by
the twin): CARD_FIELDS below.

Probe data (only frame.parquet and manifest.json of a collection, no target column): two anchors, Dataset.probe_anchors =
[the probe collection anchor, the last train anchor]. For each: keys and base columns from frame.parquet and
manifest.json of the collection (Dataset.collection('probe') / Dataset.collection('fit', last); of the manifest
only anchor, base_digest, features and the frame hash are read, §8.9); users = the first Dataset.probe_users users
by xc.query_order_key; the reference columns = base + the xfer agent set computed by the council with
xa.agent_columns on those keys -> roles.Paths.probe_ref(anchor), a light step (§13.1: queue.light_wait 'probe'
and a lock of its own per anchor). The user
set of the train frame is conditional on a target in its window (prereg-1 records the limitation). No probe runs
on the C_test frame. Rows of the probe data are ordered by (query order of the user, item_id): q (the query index)
is sorted, and the first R2_QUERIES / CROSS_QUERIES queries are the first in query order (REES46: hash order).

Probe of one SQL: a dict in the schema of council.evidence.probe, so that evidence.machine_red, parity,
column_stats, rho_grouped and r2_grouped work unchanged:
  {format, version, sha256, key, sql, level, days (anchor texts), references (names), check, nondeterministic,
   error, keys, columns, per_day: {anchor: {seconds, rows, keys, columns, level, candidate_rows, coverage,
   batch: {invariant, reason} | None, sample, stats}}, values (file name), seconds_median, coverage,
   batch_invariant, max_abs_rho, nearest, r2, parity, identity}
cached in artifacts/council/xfer-<x>/probes/<sha256(level + sql)[:16]>.json with .values.parquet (anchor,
user_id, item_id, columns; the first evidence.CROSS_QUERIES queries per anchor). The stored probes keep the real
anchors; whatever goes to an LLM passes mask_anchors() first (§8.9, the analogue of agents.mask_days).
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Callable

import duckdb
import numpy as np
import pandas as pd

from council import evidence as ev
from council.xfer import queue
from council.xfer import roles
from scripts import xfer_agent as xa
from scripts import xfer_common as xc

FORMAT = 'council-xfer-probe-v1'
CARD_FORMAT = 'council-xfer-card-probe-v1'
VERSION = 1
CARD_FIELDS = ('id', 'lens', 'name', 'level', 'mechanism', 'sign', 'stratum', 'null_stratum', 'sql', 'twin', 'rival')
KEYS = ('user_id', 'item_id')
THREADS = 4                         # light step (contract §4): threads=4, DuckDB 4 GB
MEMORY = '4GB'
INVARIANCE_USERS = 1000             # xa.INVARIANCE_USERS: the batch test on two halves of these users
GATE_POLL = 30.0                    # seconds between two looks at the probe gate (§8.7)

LEVEL_KEYS = {'pair': ['user_id', 'item_id'], 'user': ['user_id'], 'item': ['item_id']}
TOKEN = re.compile(r'\bf_x_\w+', re.I)
CARD_COLUMN = re.compile(r'f_x_c([1-4])_([a-z0-9_]+)')
MAX_SLUG = 36                       # roles.CARD_COLUMN
MAX_SLUG_TWIN = MAX_SLUG - len(roles.TWIN_SUFFIX)
MASK = 'probe_day_{}'               # the anchors of the probes as an LLM sees them

_DATA: dict = {}                    # probe data per (dataset, probe dir, threads): computed only the first time


# ---------------------------------------------------------------- small helpers

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _default(x):
    if hasattr(x, 'item'):
        return x.item()
    if hasattr(x, 'tolist'):
        return x.tolist()
    if isinstance(x, (set, frozenset, tuple)):
        return sorted(x, key=str)
    return str(x)


def _plain(x):
    return json.loads(json.dumps(x, default=_default))


def _write_json(path: Path, data, sort_keys: bool = True) -> None:
    """Atomic JSON (the probe cache: sorted keys as council.evidence; the run files: insertion order)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=sort_keys, default=_default)
        if not sort_keys:
            fh.write('\n')
    os.replace(tmp, path)


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.tmp')
    xc.write_parquet(frame, tmp)
    os.replace(tmp, path)


def _con(threads: int):
    con = duckdb.connect()
    con.execute(f"SET threads={int(threads)}; SET enable_progress_bar=false; SET memory_limit='{MEMORY}'")
    return con


def _q(path) -> str:
    return str(path).replace("'", "''")


def identity(ds: roles.Dataset) -> dict:
    """roles.identity(ds): xc.code_identity and the council stamp (contract §3 rule 3)."""
    return roles.identity(ds)


def views_spec(ds: roles.Dataset, anchor, purpose: str = 'probe') -> dict:
    """The checked xfer views spec of the anchor (adapter.views through xa._views)."""
    return xa._views(ds.name, anchor, purpose)


def agent_set(ds: roles.Dataset) -> dict:
    """The frozen xfer agent set as xa.agent_columns wants it: {'proposals': [{id, level, sql, columns}], 'columns'}."""
    record = xa.read_set(ds.name)
    return {'proposals': [{k: p[k] for k in ('id', 'level', 'sql', 'columns')} for p in record['proposals']],
            'columns': list(record['columns'])}


def base_names(ds: roles.Dataset, manifest: dict) -> list[str]:
    """Base feature names of a collection without the categorical ones (as xa._load_probe); the collection must be
    built on the frozen base of the dataset."""
    base = xc.read_base(ds.name)
    xc.require(manifest.get('base_digest') == base['digest'], 'the collection is built on another base')
    _require_plain_names(xc.base_feature_names(base))
    names = list(manifest.get('features') or xc.base_feature_names(base))
    categorical = set(base.get('categorical') or [])
    return [n for n in names if n not in categorical]


def _require_plain_names(names) -> None:
    """As xa._load_probe: no base feature may look like an agent column (ag_*) or carry a reserved name."""
    bad = [n for n in names if xa.NAME.fullmatch(n) or n in xa.RESERVED]
    xc.require(not bad, f'Base feature names may not look like agent columns (ag_*) or reserved names: {bad}')


def keys_digest(keys: pd.DataFrame) -> str:
    """sha256 of the (user_id, item_id) int64 pairs in row order."""
    pairs = np.ascontiguousarray(keys[list(KEYS)].to_numpy(dtype=np.int64))
    return hashlib.sha256(pairs.tobytes()).hexdigest()


def set_digest(aset: dict) -> str:
    """sha256 of the agent set as the reference columns use it (proposal id, level, SQL, columns; columns)."""
    return _sha(json.dumps(aset, sort_keys=True, ensure_ascii=False))


def mask_anchors(ds: roles.Dataset, obj):
    """obj (a probe, a card probe, problems) with the probe anchors as probe_day_1, probe_day_2: dict keys and
    strings equal to an anchor text, and the anchor as a token inside strings, also glued by a hyphen (probe-641,
    ref-2020-08-05.parquet) or followed by a time (2020-08-05T00:00:00) (§8.9; T anchors are step numbers, so
    the replacement is structural, never on the JSON text; 641 inside 6410 or 1.641 is left alone)."""
    texts = [xc.anchor_text(a) for a in ds.probe_anchors]
    names = {t: MASK.format(i) for i, t in enumerate(texts, 1)}
    token = re.compile(r'(?<![\w.])(' + '|'.join(re.escape(t) for t in sorted(texts, key=len, reverse=True))
                       + r')(?!(?!T\d)\w|\.\d)')

    def one(x):
        if isinstance(x, dict):
            return {(names.get(k, k) if isinstance(k, str) else k): one(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [one(v) for v in x]
        if isinstance(x, str):
            return names.get(x) or token.sub(lambda m: names[m.group(1)], x)
        return x
    return one(_plain(obj))


# ---------------------------------------------------------------- probe data

def probe_users(users, n: int) -> list[int]:
    """The first n distinct users in (xc.query_order_key, user_id) order (xc.cap_queries)."""
    return xc.cap_queries([int(u) for u in users], n)


def _collection_of(ds: roles.Dataset, anchor) -> Path:
    if xc.anchor_text(anchor) == xc.anchor_text(ds.probe_anchor):
        return ds.collection('probe')
    return ds.collection('fit', anchor)


def probe_frame(ds: roles.Dataset, anchor, threads: int = THREADS) -> pd.DataFrame:
    """Keys and numeric base columns of the probe users at `anchor`, read from frame.parquet of its collection
    (probe anchor: the probe collection; last train anchor: that train collection), ordered user_id, item_id.
    Of manifest.json only anchor, files[frame.parquet], base_digest and features are read."""
    collection = Path(_collection_of(ds, anchor))
    manifest = xc.read_json(collection / xc.MANIFEST_FILE)
    manifest = {k: manifest.get(k) for k in ('anchor', 'files', 'base_digest', 'features')}
    xc.require(xc.anchor_text(manifest['anchor']) == xc.anchor_text(anchor),
               f'{collection.name}: the manifest anchor is not {anchor}')
    frame_file = collection / xc.FRAME_FILE
    xc.require(xc.sha256_file(frame_file) == (manifest['files'] or {}).get(xc.FRAME_FILE),
               f'{collection.name}: frame.parquet differs from its manifest')
    names = base_names(ds, manifest)
    _require_plain_names(names)
    con = _con(threads)
    try:
        src = f"read_parquet('{_q(frame_file)}')"
        schema = {r[0]: r[1] for r in con.execute(f'DESCRIBE SELECT * FROM {src}').fetchall()}
        numeric = [n for n in names if n in schema and ev.NUMERIC.fullmatch(str(schema[n]))]
        users = con.execute(f'SELECT DISTINCT user_id FROM {src}').fetchnumpy()['user_id']
        cohort = pd.DataFrame({'user_id': np.asarray(probe_users(users, ds.probe_users), dtype=np.int64)})
        con.register('cohort_', cohort)
        casts = ''.join(f', TRY_CAST(f."{n}" AS DOUBLE) AS "{n}"' for n in numeric)
        frame = con.execute(f"""SELECT CAST(f.user_id AS BIGINT) AS user_id, CAST(f.item_id AS BIGINT) AS item_id{casts}
            FROM {src} f SEMI JOIN cohort_ c ON f.user_id = c.user_id ORDER BY f.user_id, f.item_id""").df()
    finally:
        con.close()
    return frame.astype({'user_id': 'int64', 'item_id': 'int64'})


@contextlib.contextmanager
def reference_step(what: str, ds: roles.Dataset, lock: Path):
    """The reference columns of a probe anchor: a light step (contract §13.1; 3000 probe users, DuckDB 4 GB,
    threads=4). Takes a blocking flock on `lock` first (one writer per anchor), then waits under it for
    queue.light_gate('probe') over the queue journals of both datasets, so the gate answer is fresh when the body
    starts; journals light-start and light-end (ok, seconds, peak) in the queue journal of the dataset."""
    journals = [roles.paths(x, ds.paths.root).queue_log for x in roles.DATASETS]
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, 'a+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            queue.light_wait('probe', journals, log=ds.paths.queue_log, dataset=ds.name)
            t0 = time.time()
            queue.journal(ds.paths.queue_log, {'event': 'light-start', 'what': what, 'dataset': ds.name,
                                               'pid': os.getpid()})
            ok = False
            try:
                yield
                ok = True
            finally:
                queue.journal(ds.paths.queue_log, {'event': 'light-end', 'what': what, 'dataset': ds.name, 'ok': ok,
                                                   'seconds': round(time.time() - t0, 1),
                                                   'peak_gb': queue.peak_rss_gb()})
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def reference(ds: roles.Dataset, anchor, frame: pd.DataFrame, threads: int = THREADS,
              views: dict | None = None) -> pd.DataFrame:
    """frame + the xfer agent set columns at `anchor` (xa.agent_columns, purpose 'probe', the frozen set of
    configs/datasets/xfer-<x>-set.json), cached in roles.Paths.probe_ref(anchor); the cache is reused only if
    its keys and column list match. Computing it is a light step (reference_step, §13.1). Writes only under
    artifacts/council/xfer-<x>/probes/."""
    aset = agent_set(ds)
    columns = list(frame.columns) + [c for c in aset['columns'] if c not in frame.columns]
    path = ds.paths.probe_ref(anchor)
    stamp_path = path.with_suffix('.json')
    stamp = dict(format=FORMAT, identity=_plain(identity(ds)), agent_set_sha256=set_digest(aset),
                 keys_sha256=keys_digest(frame), columns=columns)

    def cached():
        if not path.exists() or not stamp_path.exists():
            return None
        if json.loads(stamp_path.read_text(encoding='utf-8')) != stamp:
            return None
        got = xc.read_parquet(path)
        same = (list(got.columns) == columns and len(got) == len(frame)
                and all(np.array_equal(got[k].to_numpy(dtype=np.int64), frame[k].to_numpy(dtype=np.int64))
                        for k in KEYS))
        return got if same else None
    got = cached()
    if got is not None:
        return got
    with reference_step(f'probe reference {xc.anchor_text(anchor)}', ds, path.with_suffix('.lock')):
        got = cached()               # another process may have written it while this one waited
        if got is not None:
            return got
        values, _ = xa.agent_columns(ds.name, anchor, frame[list(KEYS)], aset, threads=threads, cache={},
                                     purpose='probe', memory=MEMORY,
                                     views=views if views is not None else views_spec(ds, anchor))
        out = frame.copy()
        for c in aset['columns']:
            out[c] = values[c].to_numpy(dtype=np.float64)
        out = out[columns]
        _write_parquet(out, path)
        _write_json(stamp_path, stamp)
    return out


def _ranks(ref: pd.DataFrame, names: list[str]) -> np.ndarray:
    """Percent ranks (average ties, share of the non-NULL rows) of every reference column, float32."""
    out = np.empty((len(ref), len(names)), dtype=np.float32)
    for j, n in enumerate(names):
        v = ref[n].to_numpy(dtype=np.float64, na_value=np.nan)
        v = np.where(np.isfinite(v), v, np.nan)
        out[:, j] = pd.Series(v).rank(method='average', pct=True).to_numpy()
    return out


def probe_data(ds: roles.Dataset, threads: int = THREADS) -> list[dict]:
    """One dict per anchor of Dataset.probe_anchors: {anchor, keys (DataFrame user_id, item_id), cohort (users in
    query order), ref (DataFrame of reference columns aligned with keys), names (reference names), q (query index
    per row), ranks (reference ranks as evidence.column_stats wants them), views (xa views spec of the anchor),
    limits (xa.limits(ds.name))}. A light step only the first time (reference_step)."""
    key = (ds.name, str(ds.paths.probes), int(threads))
    if key in _DATA:
        return _DATA[key]
    out = []
    limits = xa.limits(ds.name)
    for anchor in ds.probe_anchors:
        views = views_spec(ds, anchor)
        frame = probe_frame(ds, anchor, threads)
        ref = reference(ds, anchor, frame, threads, views=views)
        cohort = np.asarray(probe_users(frame['user_id'].unique(), None), dtype=np.int64)
        position = pd.Series(np.arange(len(cohort), dtype=np.int64), index=cohort)
        qpos = position.reindex(ref['user_id'].to_numpy()).to_numpy(dtype=np.int64)
        order = np.lexsort((ref['item_id'].to_numpy(dtype=np.int64), qpos))
        ref = ref.iloc[order].reset_index(drop=True)
        names = [c for c in ref.columns if c not in KEYS]
        keys = ref[list(KEYS)].copy()
        out.append(dict(anchor=anchor, keys=keys, cohort=cohort, ref=ref[names], names=names,
                        q=qpos[order], ranks=_ranks(ref, names), views=views, limits=limits,
                        keys_sha256=keys_digest(keys), agent_set_sha256=set_digest(agent_set(ds))))
    xc.require(all(d['names'] == out[0]['names'] for d in out), 'the reference columns differ between probe anchors')
    _DATA[key] = out
    return out


# ---------------------------------------------------------------- names, check, card schema

def to_sandbox(sql: str) -> str:
    """A card SQL with every f_x_c<lens>_<slug>[_tw] replaced by roles.sandbox_column; ValueError on an f_x_ name
    of another form. SQL names are case-insensitive: the token is lowered first."""
    return TOKEN.sub(lambda m: roles.sandbox_column(m.group(0).lower()), sql)


def check(ds: roles.Dataset, sql: str, level: str) -> str | None:
    """None if xa.check_sql(ds.name, to_sandbox(sql), level) passes, else its message."""
    try:
        xa.check_sql(ds.name, to_sandbox(sql), level)
    except ValueError as e:          # xa.ProposalError is a ValueError, so is a bad f_x_ name
        return str(e)
    return None


def validate_card(ds: roles.Dataset, card: dict) -> list[str]:
    """Problems of a card against CARD_FIELDS and the xfer rules ([] = valid): id G<1-4>-<n> with its lens, slug
    name, level in xa.LEVELS, sign, non-empty texts, twin {how, sql} with how in evidence.TWIN_HOW, rival; sql and
    twin.sql pass check() and name the keys of the level (adapter.LEVELS); 1..xa.MAX_VALUES columns
    f_x_c<lens>_<slug> (slug <= 33: every card has a twin, which adds _tw); twin columns = card columns + _tw. The
    `validate` injected into curate.curate."""
    if not isinstance(card, dict):
        return ['a card is a JSON object']
    out = []
    missing = [f for f in CARD_FIELDS if f not in card]
    extra = [f for f in card if f not in CARD_FIELDS]
    if missing:
        out.append(f'missing fields {missing}')
    if extra:
        out.append(f'unknown fields {extra}')
    m = roles.CARD_ID.fullmatch(str(card.get('id', '')))
    if not m:
        out.append(f'id {card.get("id")!r} is not G<1-4>-<n>')
    elif card.get('lens') != f'G{m.group(1)}':
        out.append(f'lens {card.get("lens")!r} differs from the id {card.get("id")}')
    if not isinstance(card.get('name'), str) or not roles.SLUG.fullmatch(card.get('name', '')):
        out.append('name is not a snake_case slug')
    level = card.get('level')
    if level not in xa.LEVELS:
        out.append(f'level {level!r} is not one of {list(xa.LEVELS)}')
    if card.get('sign') not in ('+', '-'):
        out.append('sign is not + or -')
    for f in ('mechanism', 'stratum', 'null_stratum', 'sql'):
        if not isinstance(card.get(f), str) or not card.get(f).strip():
            out.append(f'{f} is empty')
    twin, rival = card.get('twin'), card.get('rival')
    if not isinstance(twin, dict) or set(twin) != {'how', 'sql'}:
        out.append('twin is not {how, sql}')
        twin = {}
    elif twin.get('how') not in ev.TWIN_HOW:
        out.append(f'twin.how is not one of {ev.TWIN_HOW}')
    if not isinstance(rival, dict) or set(rival) != {'explanation', 'stratum'} or not all(
            isinstance(v, str) and v.strip() for v in rival.values()):
        out.append('rival is not {explanation, stratum} with text')
    digit = m.group(1) if m else None
    level_keys = []
    if level in xa.LEVELS:
        level_keys = list((getattr(ds.adapter, 'LEVELS', None) or LEVEL_KEYS).get(level) or [])
    names = []
    for side, sql in (('sql', card.get('sql')), ('twin.sql', twin.get('sql'))):
        if not isinstance(sql, str) or not sql.strip():
            if side == 'twin.sql':
                out.append('twin.sql is empty')
            continue
        if level in xa.LEVELS:
            why = check(ds, sql, level)
            if why:
                out.append(f'{side}: {why}')
        hit = xa.NONDETERMINISTIC.search(sql)
        if hit:
            out.append(f'{side}: NONDETERMINISTIC {hit.group(0)}')
        absent = [k for k in level_keys if not re.search(rf'\b{re.escape(k)}\b', sql)]
        if absent:
            out.append(f'{side}: no {"/".join(absent)} key of level {level}')
        tokens = sorted({t.lower() for t in TOKEN.findall(sql)})
        if side == 'sql':
            names = tokens
            if not 1 <= len(names) <= xa.MAX_VALUES:
                out.append(f'sql names {len(names)} f_x_ columns, 1-{xa.MAX_VALUES} allowed')
            for n in names:
                c = CARD_COLUMN.fullmatch(n)
                if not c or c.group(1) != digit or n.endswith(roles.TWIN_SUFFIX):
                    out.append(f'column {n} is not f_x_c{digit}_<slug>')
                elif len(c.group(2)) > MAX_SLUG_TWIN:
                    out.append(f'column {n}: slug of {len(c.group(2))} characters, at most {MAX_SLUG_TWIN} '
                               f'(the twin adds {roles.TWIN_SUFFIX})')
        else:
            tw = {t for t in tokens if t.endswith(roles.TWIN_SUFFIX)}
            if tw != {n + roles.TWIN_SUFFIX for n in names}:
                out.append(f'twin columns {sorted(tw)} are not the card columns + {roles.TWIN_SUFFIX}')
            other = set(tokens) - tw - set(names)
            if other:
                out.append(f'twin.sql names other f_x_ columns {sorted(other)}')
    return out


# ---------------------------------------------------------------- one SQL on one anchor

def run_sql(ds: roles.Dataset, data: dict, sql: str, level: str, threads: int = THREADS) -> tuple[pd.DataFrame, dict]:
    """(values on data['keys'] in key order, info {seconds, rows, columns}) of one sandbox SQL at data['anchor']:
    xa.check_sql, xa.sandbox over the probe keys (purpose 'probe'), xa._execute in the 'table' shape with the level
    timeout of data['limits'], xa._align onto the keys (the path of an xfer probe); xa.ProposalError propagates."""
    xa.check_sql(ds.name, sql, level)
    spec, anchor = data['views'], data['anchor']
    timeout = data['limits']['timeouts'][level]
    keys = data['keys']
    with tempfile.TemporaryDirectory(prefix='tlab-council-probe-') as scratch:
        path = Path(scratch).resolve() / 'keys.parquet'
        xa._stage_keys(keys, path, threads)
        con = xa.sandbox(ds.name, anchor, path, threads=threads, purpose='probe', memory=MEMORY, views=spec)
        try:
            t0 = time.monotonic()
            table, names, rows = xa._execute(con, spec, level, sql, anchor, timeout, 'table')
            seconds = time.monotonic() - t0
        finally:
            xa._close(con)
    _, matrix = xa._align(table, spec, level, keys['user_id'].to_numpy(dtype=np.int64),
                          keys['item_id'].to_numpy(dtype=np.int64))
    values = pd.DataFrame(matrix, columns=list(names))
    return values, dict(seconds=round(seconds, 3), rows=int(rows), columns=list(names))


def batch_invariance(ds: roles.Dataset, data: dict, sql: str, level: str, values: pd.DataFrame,
                     threads: int = THREADS) -> dict | None:
    """{invariant, reason}: values on all keys against values on the two halves (in query order, a hash order) of
    the first INVARIANCE_USERS cohort users (xa._invariance, tolerance xa.TOLERANCE); None for item level."""
    if level == 'item':
        return None
    keys = data['keys']
    view = dict(cohort=np.asarray(data['cohort'][:INVARIANCE_USERS], dtype=np.int64),
                user_id=keys['user_id'].to_numpy(dtype=np.int64), item_id=keys['item_id'].to_numpy(dtype=np.int64),
                limits=data['limits'])
    names = list(values.columns)
    reason = xa._invariance(ds.name, data['views'], data['anchor'], level, sql, names,
                            values[names].to_numpy(dtype=np.float64), view, threads, MEMORY)
    return dict(invariant=reason is None, reason=reason)


def _prefix(q, queries):
    return int(np.searchsorted(q, queries, side='left'))


def _probe_anchor(ds, d, sql, level, threads):
    values, info = run_sql(ds, d, sql, level, threads)
    cols = info['columns']
    n = len(d['keys'])
    rec = dict(seconds=info['seconds'], rows=info['rows'], keys=list(LEVEL_KEYS[level]), columns=cols, level=level)
    rec['candidate_rows'] = n
    rec['coverage'] = {c: round(float(np.isfinite(values[c].to_numpy(dtype=np.float64)).sum() / n) if n else 0.0, 6)
                       for c in cols}
    rec['batch'] = batch_invariance(ds, d, sql, level, values, threads)
    mode = 'between' if level == 'user' else 'within'
    r2_rows = _prefix(d['q'], ev.R2_QUERIES)
    rec['sample'] = dict(queries=int(len(np.unique(d['q']))), rows=n, r2_rows=r2_rows, references=len(d['names']))
    rec['stats'] = {c: ev.column_stats(values[c].to_numpy(dtype=np.float64), d['ranks'], d['names'], d['q'],
                                       mode, r2_rows) for c in cols}
    cut = _prefix(d['q'], ev.CROSS_QUERIES)
    kept = pd.DataFrame({'anchor': xc.anchor_text(d['anchor']),
                         'user_id': d['keys']['user_id'].to_numpy(dtype=np.int64)[:cut],
                         'item_id': d['keys']['item_id'].to_numpy(dtype=np.int64)[:cut]})
    for c in cols:
        kept[c] = values[c].to_numpy(dtype=np.float32)[:cut]
    return rec, kept


def _summary(p: dict) -> dict:
    """Aggregates over anchors (council.evidence._summary; batch None at item level)."""
    days = [d for d in p['days'] if d in p['per_day']]
    cols = p['columns'] or []
    sec = [p['per_day'][d]['seconds'] for d in days]
    p['seconds_median'] = float(np.median(sec)) if sec else None
    p['coverage'] = {c: round(float(np.mean([p['per_day'][d]['coverage'][c] for d in days])), 6) for c in cols}
    batches = [p['per_day'][d]['batch'] for d in days]
    p['batch_invariant'] = (None if p['level'] == 'item' or not batches or any(b is None for b in batches)
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
    p['parity'] = ev.parity(p)
    return p


def probe_path(ds: roles.Dataset, sql: str, level: str) -> Path:
    """roles.Paths.probes / f'{sha256(level + newline + sql)[:16]}.json'."""
    return ds.paths.probes / f'{_sha(level + chr(10) + sql)[:16]}.json'


TIMEOUT_TEXT = 'timeout after'      # xa._Limit.timeout(): a timed out run is not a property of the SQL alone


def _stamp(ds: roles.Dataset, data: list[dict]) -> dict:
    """What a cached probe must have been made on: the code identity, the keys of every anchor, the agent set."""
    return dict(identity=_plain(identity(ds)),
                keys_sha256={xc.anchor_text(d['anchor']): d.get('keys_sha256') for d in data},
                agent_set_sha256=data[0].get('agent_set_sha256') if data else None)


def probe(ds: roles.Dataset, sql: str, level: str, data: list[dict] | None = None, threads: int = THREADS) -> dict:
    """The probe dict of the module docstring for one sandbox SQL on every probe anchor; cached by probe_path
    (format, version, anchors, references, sql, level, identity, keys digests and agent set digest must match).

    A check failure, a nondeterministic function or a ProposalError of the run (the SQL's own failure) leaves
    per_day partial, is reported in check/nondeterministic/error and is cached. A timeout (a run or a batch half)
    is reported but not cached. Technical failures (DuckDB errors xa does not attribute to the SQL, I/O, building
    the sandbox, an interrupt) are raised and nothing is written."""
    data = probe_data(ds, threads) if data is None else data
    days = [xc.anchor_text(d['anchor']) for d in data]
    references = list(data[0]['names']) if data else []
    stamp = _stamp(ds, data)
    path = probe_path(ds, sql, level)
    if path.exists():
        cached = json.loads(path.read_text(encoding='utf-8'))
        if (cached.get('format') == FORMAT and cached.get('version') == VERSION and cached.get('days') == days
                and cached.get('references') == references and cached.get('sql') == sql
                and cached.get('level') == level and all(cached.get(k) == v for k, v in stamp.items())):
            return cached
    p = dict(format=FORMAT, version=VERSION, sha256=_sha(sql), key=path.stem, sql=sql, level=level, days=days,
             references=references, check=None, nondeterministic=None, error=None, keys=None, columns=None,
             per_day={}, values=None, **stamp)
    p['check'] = check(ds, sql, level)
    hit = xa.NONDETERMINISTIC.search(sql)
    if hit:
        p['nondeterministic'] = hit.group(0)
    frames, transient = [], False
    if not p['check'] and not p['nondeterministic']:
        for d, text in zip(data, days):
            try:
                rec, kept = _probe_anchor(ds, d, sql, level, threads)
            except xa.ProposalError as e:
                p['error'] = f'{text}: {e}'
                transient = str(e).startswith(TIMEOUT_TEXT)
                break
            if TIMEOUT_TEXT in str((rec.get('batch') or {}).get('reason') or ''):
                transient = True
            if p['columns'] is None:
                p['keys'], p['columns'] = rec['keys'], rec['columns']
            elif rec['keys'] != p['keys'] or rec['columns'] != p['columns']:
                p['error'] = f'{text}: keys or columns differ between anchors: {rec["keys"] + rec["columns"]}'
                break
            p['per_day'][text] = rec
            frames.append(kept)
    if frames and not p['error'] and not transient:
        vpath = path.with_suffix('.values.parquet')
        _write_parquet(pd.concat(frames, ignore_index=True), vpath)
        p['values'] = vpath.name
    _summary(p)
    p = _plain(p)
    if not transient:
        _write_json(path, p)
    return p


def probe_card(ds: roles.Dataset, card: dict, data: list[dict] | None = None, threads: int = THREADS) -> dict:
    """{format: CARD_FORMAT, id, problems (validate_card + output column checks), card: probe(sql), twin:
    probe(twin.sql), twin_check: twin_check(card probe, twin probe)}."""
    problems = validate_card(ds, card)
    out = dict(format=CARD_FORMAT, id=card.get('id'), problems=problems, card=None, twin=None, twin_check=None)
    level = card.get('level')
    if (not isinstance(card.get('sql'), str) or not isinstance((card.get('twin') or {}).get('sql'), str)
            or level not in xa.LEVELS):
        return out
    try:
        sql, twin_sql = to_sandbox(card['sql']), to_sandbox(card['twin']['sql'])
    except ValueError:
        return out                   # validate_card already names the f_x_ column
    p = probe(ds, sql, level, data, threads)
    tw = probe(ds, twin_sql, level, data, threads)
    out['card'], out['twin'] = p, tw
    m = roles.CARD_ID.fullmatch(str(card.get('id')))
    digit = m.group(1) if m else None
    if p['columns'] is not None:
        if not 1 <= len(p['columns']) <= xa.MAX_VALUES:
            problems.append(f'{len(p["columns"])} value columns, 1-{xa.MAX_VALUES} allowed')
        for c in p['columns']:
            cm = roles.CARD_COLUMN.fullmatch(c)
            if not cm or cm.group(1) != digit or c.endswith(roles.TWIN_SUFFIX):
                problems.append(f'column {c} is not {roles.SANDBOX_PREFIX}{digit}_<slug>')
    if p['columns'] is not None and tw['columns'] is not None:
        if tw['columns'] != [c + roles.TWIN_SUFFIX for c in p['columns']]:
            problems.append(f'twin columns {tw["columns"]} are not the card columns + {roles.TWIN_SUFFIX}')
        if tw['keys'] != p['keys']:
            problems.append(f'twin keys {tw["keys"]} differ from the card keys {p["keys"]}')
    out['twin_check'] = twin_check(ds, p, tw)
    return out


# ---------------------------------------------------------------- card-card statistics

def _values(ds: roles.Dataset, p: dict):
    if not p.get('values'):
        return None
    path = ds.paths.probes / p['values']
    if not path.exists():
        return None
    return xc.read_parquet(path)


def cross(ds: roles.Dataset, pa: dict, pb: dict) -> dict | None:
    """Copy of council.evidence.cross with the values loaded from roles.Paths.probes and the key item_id:
    {mode, rows, rho, max_abs_rho, r2_a_on_b, r2_b_on_a}; None if either side has no stored values."""
    va, vb = _values(ds, pa), _values(ds, pb)
    if va is None or vb is None:
        return None
    k = ['anchor', 'user_id', 'item_id']
    ca, cb = list(pa['columns']), list(pb['columns'])
    m = va[k + ca].merge(vb[k + cb].rename(columns={c: c + '\x00b' for c in cb}), on=k, how='inner')
    m = m.sort_values(k, kind='stable').reset_index(drop=True)
    q = m.groupby(['anchor', 'user_id'], sort=False).ngroup().to_numpy()
    q = pd.factorize(q)[0]
    starts = ev._starts(q)
    A = m[ca].to_numpy(dtype=np.float64)
    B = m[[c + '\x00b' for c in cb]].to_numpy(dtype=np.float64)
    between = 'user' in (pa.get('level'), pb.get('level'))
    if between:
        A, B = ev._query_level(A, starts), ev._query_level(B, starts)
        starts, q, low = np.zeros(1, dtype=np.int64), np.zeros(len(A), dtype=np.int64), ev.MIN_QUERIES
    else:
        A, B, low = ev._pct(A), ev._pct(B), ev.MIN_ROWS
    rho = {a: {} for a in ca}
    best = None
    for i, a in enumerate(ca):
        r = ev.rho_grouped(A[:, i], B, starts, low)
        for j, b in enumerate(cb):
            rho[a][b] = None if not np.isfinite(r[j]) else round(float(r[j]), 4)
            if rho[a][b] is not None and (best is None or abs(rho[a][b]) > best):
                best = abs(rho[a][b])
    r2_ab = {a: ev.r2_grouped(A[:, i], B, q, low) for i, a in enumerate(ca)}
    r2_ba = {b: ev.r2_grouped(B[:, j], A, q, low) for j, b in enumerate(cb)}
    return dict(mode='between' if between else 'within', rows=len(m), rho=rho, max_abs_rho=best,
                r2_a_on_b=r2_ab, r2_b_on_a=r2_ba)


def twin_check(ds: roles.Dataset, card_probe: dict, twin_probe: dict) -> dict:
    """council.evidence.twin_check with cross() of this module (the REES46 one reads the REES46 probe store):
    {verdict: 'ok' | 'TWIN-BROKEN', reasons, columns}; thresholds evidence.TWIN_COVERAGE, evidence.TWIN_RHO."""
    reasons = []
    for side, p in (('card', card_probe), ('twin', twin_probe)):
        red = ev.machine_red(p)
        if red:
            reasons.append(f'{side} machine test red: {red[0]}')
    cols = card_probe.get('columns') or []
    if not reasons and twin_probe.get('columns') != [c + roles.TWIN_SUFFIX for c in cols]:
        reasons.append(f'twin columns {twin_probe.get("columns")} are not {[c + roles.TWIN_SUFFIX for c in cols]}')
    detail = {}
    if not reasons:
        cr = cross(ds, card_probe, twin_probe)
        for c in cols:
            cov, cov_tw = card_probe['coverage'][c], twin_probe['coverage'][c + roles.TWIN_SUFFIX]
            r = None if cr is None else cr['rho'][c][c + roles.TWIN_SUFFIX]
            detail[c] = dict(coverage=cov, coverage_twin=cov_tw, rho=r)
            if abs(cov_tw - cov) > ev.TWIN_COVERAGE * cov:
                reasons.append(f'{c}: coverage {cov:.4f}, twin {cov_tw:.4f}, outside +-{ev.TWIN_COVERAGE:.0%}')
            if r is None:
                reasons.append(f'{c}: rho_wq with the twin is undefined')
            elif abs(r) > ev.TWIN_RHO:
                reasons.append(f'{c}: |rho_wq| with the twin {abs(r):.3f} > {ev.TWIN_RHO}')
    return dict(verdict='ok' if not reasons else 'TWIN-BROKEN', reasons=reasons, columns=detail)


# ---------------------------------------------------------------- the stage

def _proposals(reference_sets: dict | None) -> list[dict]:
    """Rb proposals in the reference order: Rb1 by proposal, then Rb2. reference_sets: {k: [proposal]} (run.py)
    or {k: {'proposals': [...]}}."""
    out = []
    for k in sorted(reference_sets or {}):
        s = reference_sets[k]
        out += list(s.get('proposals') or []) if isinstance(s, dict) else list(s or [])
    return out


def wait_gate(gate: Callable[[], list] | None, poll: float = GATE_POLL, sleep=time.sleep) -> int:
    """Wait (poll seconds) while gate() gives reasons; returns how many times it waited. gate None: no wait."""
    waits = 0
    while gate is not None:
        reasons = gate()
        if not reasons:
            break
        if waits == 0:
            print('probes wait: ' + '; '.join(map(str, reasons)), flush=True)
        waits += 1
        sleep(poll)
    return waits


def _put(path: Path, section: str | None, key: str | None, value) -> dict:
    """probes.json re-read from disk and one entry replaced (entries another writer added meanwhile stay)."""
    store = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    store.setdefault('cards', {})
    store.setdefault('reference', {})
    if section is not None:
        store[section][key] = value
    _write_json(path, store, sort_keys=False)
    return store


def probe_stage(ds: roles.Dataset, cards: list[dict], reference_sets: dict | None = None,
                gate: Callable[[], list] | None = None, threads: int = THREADS, *, poll: float = GATE_POLL,
                sleep=time.sleep) -> dict:
    """Probes of every card (probe_card) and of every Rb proposal ({table: probe}); writes
    council/runs/xfer-<x>/probes.json = {'cards': {id: card probe}, 'reference': {table: probe}} and returns it.
    Entries of cards or tables not given here (e.g. the wave1 version of a withdrawn card) are kept; a given one
    is replaced. A light step: gate() (e.g. queue.light_gate('probe', ...)) is asked before every probe of a
    card or an Rb proposal, and the stage waits while it gives reasons (§8.7)."""
    path = ds.paths.run_file('probes.json')
    data = probe_data(ds, threads)
    for card in cards:
        wait_gate(gate, poll, sleep)
        _put(path, 'cards', str(card.get('id')), _plain(probe_card(ds, card, data, threads)))
    for prop in _proposals(reference_sets):
        wait_gate(gate, poll, sleep)
        _put(path, 'reference', prop['table'], probe(ds, prop['sql'], prop['level'], data, threads))
    return _put(path, None, None, None)
