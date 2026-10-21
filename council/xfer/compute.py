"""Council tables like xfer sidecars (council/runs/xfer/contract.md §3, §3.4, §4): the SQL of every curated family,
twin and kept Rb proposal, computed with xa.agent_columns on the frame keys of every collection the fits read.

Collections: the train anchors and the S0 anchor (training rows of both series) and the C_test collection
(Dataset.collection('test'), its frame keys only). Each table of each collection ->
artifacts/council/xfer-<x>/sidecars/<collection>/<table>.parquet with user_id, item_id and the table's columns,
one row per frame row in (user_id, item_id) order, plus sidecars/<collection>/manifest.json
{format, dataset, collection, collection_manifest_sha256, tables: {table: {sql_sha256, level, columns, rows,
file_sha256, seconds, identity, collection_manifest_sha256}}, identity}. Rb columns: the output columns of the
table's probe in probes.json (the order xa.agent_columns checks). Nothing is written under the xfer artifacts; every path comes from ds.paths.

Order: every table first on the stress collection (the latest anchor, the longest history: the C_test
collection); a failure (time, memory, error) is recorded as failed_stress in council/runs/xfer-<x>/compute.json
and stops the stage before any other table (the curation is rebuilt without it). Then the missing
(collection, table) pairs; a present file is kept only if its manifest SQL sha equals the plan's (another sha:
the stage stops, the table belongs to another version) and the stamp holds: the identity of this code, the
collection manifest sha, the file sha and the frame rows; a stale table is computed again. failed_stress only
for a ProposalError, a DuckDB error or a MemoryError; other exceptions are raised without a record.

A heavy step: the whole stage runs inside queue.heavy('compute', ds.name).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from council.xfer import queue
from council.xfer import roles
from council.xfer import sandbox
from scripts import xfer_agent as xa
from scripts import xfer_common as xc

FORMAT = 'council-xfer-table-v1'
THREADS = 4
MEMORY = '20GB'                     # the xfer sidecar limit of deviation d1 (T); one heavy step at a time
BATCH_ROWS = 400_000                # frame rows per agent_columns call, whole users (xfer sidecar batches)
TIMEOUT = xa.RUN_TIMEOUT            # one table on one batch (the xfer sidecar timeout)
KEYS = ('user_id', 'item_id')


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _default(x):
    if hasattr(x, 'item'):
        return x.item()
    if hasattr(x, 'tolist'):
        return x.tolist()
    return str(x)


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(obj, indent=1, ensure_ascii=False, default=_default) + '\n')
    os.replace(tmp, path)


def _load(path: Path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


# ---------------------------------------------------------------- what to compute

def kept_reference(curation: dict) -> list[str]:
    """Rb tables of the arm (council.agents.reference_kept): reference_order minus reference_removed and the
    tables the width parity dropped."""
    if curation.get('reference_order') is None:
        raise SystemExit('curation.json has no reference_order: rebuild it with council.xfer.curate.stage')
    drop = set((curation.get('parity') or {}).get('reference_drop') or [])
    gone = drop | {x if isinstance(x, str) else x.get('table') for x in curation.get('reference_removed') or []}
    return [t for t in curation['reference_order'] if t not in gone]


def plan(curation: dict, cards: list[dict], references: dict) -> list[dict]:
    """The tables to compute, in order families, twins, kept Rb:
    [{'table': roles.family_table(id) | roles.twin_table(id) | rb table, 'level': xa level, 'sql': sandbox SQL
      (sandbox.to_sandbox for cards), 'columns': [ag_ names]}]. references: {table: {'sql', 'level', 'columns'}}
    of reference-rb1.json and reference-rb2.json with the columns of the table's probe (the output order of the
    SQL, which xa.agent_columns checks); only tables kept by the curation (agents.reference_kept rule:
    reference_order minus reference_removed and the parity cut). Column names may not repeat between tables."""
    by_id = {c['id']: c for c in cards}
    cols = curation.get('columns') or {}
    out = []
    for cid in curation['families']:
        c = by_id[cid]
        out.append(dict(table=roles.family_table(cid), level=c['level'], sql=sandbox.to_sandbox(c['sql']),
                        columns=list(cols[cid])))
    for cid in curation['twins']:
        c = by_id[cid]
        out.append(dict(table=roles.twin_table(cid), level=c['level'], sql=sandbox.to_sandbox(c['twin']['sql']),
                        columns=[n + roles.TWIN_SUFFIX for n in cols[cid]]))
    for t in kept_reference(curation):
        r = references[t]
        out.append(dict(table=t, level=r['level'], sql=r['sql'], columns=list(r['columns'])))
    names = [n for e in out for n in e['columns']]
    if len(names) != len(set(names)):
        raise SystemExit(f'column names repeat between tables: {sorted({n for n in names if names.count(n) > 1})}')
    return out


def collections(ds: roles.Dataset) -> list[tuple]:
    """[(phase, anchor, collection dir)]: every training anchor of both series (fit and select phases, each once),
    the S0 collection the dev fits score, and the C_test collection; the stress collection (C_test) first."""
    out = [('test', ds.test_anchor, Path(ds.collection('test')))]
    seen = {out[0][2]}
    pairs = list(ds.training_collections('select')) + list(ds.training_collections('test'))
    pairs.append((ds.s0_anchor, ds.collection('select')))
    for anchor, path in sorted(pairs, key=lambda x: xc.anchor_int(x[0])):
        path = Path(path)
        if path in seen:
            continue
        seen.add(path)
        out.append((ds.phase_of(anchor), anchor, path))
    return out


def frame_keys(collection) -> pd.DataFrame:
    """user_id, item_id of frame.parquet of a collection, ordered user_id, item_id (nothing else is read)."""
    return xa._frame_keys(collection)


# ---------------------------------------------------------------- one table

def compute_table(ds: roles.Dataset, anchor, keys: pd.DataFrame, entry: dict, cache: dict | None = None, *,
                  threads: int = THREADS, views: dict | None = None) -> tuple:
    """(DataFrame user_id, item_id + entry['columns'] in key order, info {seconds, rows}) of one table on one
    collection: xa.agent_columns(ds.name, anchor, keys batch, {'proposals': [entry as proposal], 'columns':
    entry['columns']}, purpose='sidecar', memory=MEMORY, cache=cache) over BATCH_ROWS batches of whole users
    (xa.sidecar_batches). views: the xfer views spec of the anchor (taken once per collection by the stage)."""
    proposal = dict(id=entry['table'], level=entry['level'], sql=entry['sql'], columns=list(entry['columns']))
    aset = {'proposals': [proposal], 'columns': list(entry['columns'])}
    keys = keys[list(KEYS)].reset_index(drop=True)
    parts, t0 = [], time.monotonic()
    for begin, stop in xa.sidecar_batches(keys, batch_rows=BATCH_ROWS):
        got, _ = xa.agent_columns(ds.name, anchor, keys.iloc[begin:stop], aset, threads=threads, timeout_s=TIMEOUT,
                                  cache=cache, purpose='sidecar', memory=MEMORY, views=views)
        parts.append(got)
    frame = (pd.concat(parts, ignore_index=True) if parts
             else pd.DataFrame({**{k: np.zeros(0, dtype=np.int64) for k in KEYS},
                                **{c: np.zeros(0) for c in entry['columns']}}))
    frame = frame[list(KEYS) + list(entry['columns'])]
    return frame, dict(seconds=round(time.monotonic() - t0, 3), rows=len(frame))


def _manifest_path(ds: roles.Dataset, collection: Path) -> Path:
    return ds.paths.sidecars / collection.name / xc.MANIFEST_FILE


def manifest(ds: roles.Dataset, collection) -> dict | None:
    """sidecars/<collection>/manifest.json of the council tables, or None."""
    return _load(_manifest_path(ds, Path(collection)))


def present(ds: roles.Dataset, collection, entry: dict, identity: dict | None = None,
            rows: int | None = None) -> bool:
    """True if the table of `entry` on the collection can be kept: its manifest entry names the plan's SQL sha,
    the identity of this code (when given), the current manifest sha of the collection, the file sha of the file
    on disk and the number of frame rows (when given). False when it is missing or stale (computed again);
    SystemExit if it exists (file or manifest entry) for another SQL."""
    collection = Path(collection)
    path = ds.paths.table(collection.name, entry['table'])
    got = ((manifest(ds, collection) or {}).get('tables') or {}).get(entry['table'])
    sha = _sha(entry['sql'])
    if got is not None and got.get('sql_sha256') != sha:
        raise SystemExit(f'{path}: the manifest names another SQL; the table belongs to another version')
    if got is None:
        if path.exists():
            raise SystemExit(f'{path} exists without a manifest entry: stop')
        return False
    if not path.exists():
        return False
    if identity is not None and got.get('identity') != identity:
        return False
    if got.get('collection_manifest_sha256') != xc.sha256_file(collection / xc.MANIFEST_FILE):
        return False
    if rows is not None and got.get('rows') != rows:
        return False
    return got.get('file_sha256') == xc.sha256_file(path)


def write_table(ds: roles.Dataset, collection, table: str, frame: pd.DataFrame, entry: dict, info: dict,
                identity: dict | None = None) -> dict:
    """Atomic write of roles.Paths.table(collection name, table) and its entry in the collection manifest
    {sql_sha256, level, columns, rows, file_sha256, seconds, identity, collection_manifest_sha256}; refuses
    (ValueError) to overwrite a file with another SQL sha or a file without a manifest entry. Returns the entry."""
    collection = Path(collection)
    if table != entry['table']:
        raise ValueError(f'table {table!r} differs from the entry {entry["table"]!r}')
    if list(frame.columns) != list(KEYS) + list(entry['columns']):
        raise ValueError(f'{table}: columns {list(frame.columns)} are not the keys + {entry["columns"]}')
    path = ds.paths.table(collection.name, table)
    mpath = _manifest_path(ds, collection)
    coll_sha = xc.sha256_file(collection / xc.MANIFEST_FILE)
    man = _load(mpath) or dict(format=FORMAT, dataset=ds.name, collection=collection.name,
                               collection_manifest_sha256=coll_sha, tables={}, identity=identity)
    if man.get('format') != FORMAT or man.get('dataset') != ds.name or man.get('collection') != collection.name:
        raise ValueError(f'{mpath} is not the council manifest of {ds.name}/{collection.name}')
    sha = _sha(entry['sql'])
    old = (man.get('tables') or {}).get(table)
    if old is not None and old.get('sql_sha256') != sha:
        raise ValueError(f'{path}: written for another SQL ({old.get("sql_sha256")[:12]}), refused')
    if old is None and path.exists():
        raise ValueError(f'{path} exists without a manifest entry, refused')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.tmp')
    xc.write_parquet(frame, tmp, order_by='user_id, item_id')
    os.replace(tmp, path)
    rec = dict(sql_sha256=sha, level=entry['level'], columns=list(entry['columns']), rows=int(len(frame)),
               file_sha256=xc.sha256_file(path), seconds=info.get('seconds'), identity=identity,
               collection_manifest_sha256=coll_sha)
    man['tables'][table] = rec
    man['collection_manifest_sha256'] = coll_sha
    if identity is not None:
        man['identity'] = identity
    _write_json(mpath, man)
    return rec


# ---------------------------------------------------------------- the stage

FAILURES = (xa.ProposalError, duckdb.Error, MemoryError)   # what a table may fail with; anything else is raised


def _inputs(ds: roles.Dataset) -> list[dict]:
    """The plan from curation.json, cards-final.json, reference-rb<k>.json and probes.json: the columns of an Rb
    table are the output columns of its probe (the order the SQL gives them), not the proposal's list."""
    curation = _load(ds.paths.run_file('curation.json'))
    final = _load(ds.paths.run_file('cards-final.json'))
    if not curation or not final or 'cards' not in final:
        raise SystemExit('curation.json and cards-final.json are needed')
    if not (curation.get('parity') or {}).get('ok'):
        raise SystemExit('curation.json: the width parity is not ok')
    probed = (_load(ds.paths.run_file('probes.json')) or {}).get('reference') or {}
    references = {}
    for k in (1, 2):
        for p in (_load(ds.paths.run_file(f'reference-rb{k}.json')) or {}).get('proposals') or []:
            got = probed.get(p['table']) or {}
            if got.get('sql') != p['sql'] or got.get('level') != p['level'] or not got.get('columns'):
                columns = None
            else:
                columns = list(got['columns'])
            references[p['table']] = dict(sql=p['sql'], level=p['level'], columns=columns)
    for t in kept_reference(curation):
        if t in references and references[t]['columns'] is None:
            raise SystemExit(f'Rb table {t}: no probe of its SQL with output columns in probes.json')
    return plan(curation, final['cards'], references)


def _put(ds: roles.Dataset, table: str, rec: dict) -> dict:
    """compute.json re-read and one table's record replaced (another writer's records stay)."""
    path = ds.paths.run_file('compute.json')
    state = _load(path) or {}
    state[table] = rec
    _write_json(path, state)
    return state


def _error(ex) -> str:
    return f'{type(ex).__name__}: {str(ex)[:500]}'


def stage(ds: roles.Dataset, threads: int = THREADS) -> dict:
    """The compute stage (module docstring) under queue.heavy; reads curation.json, cards-final.json, probes.json
    and the Rb references from council/runs/xfer-<x>/ inside the lock; writes the tables, the manifests and
    compute.json {table: {sql_sha256, status: stress_ok | failed_stress | done, collections: [...], error,
    identity}} (re-read before every write); returns it. failed_stress: a ProposalError, a DuckDB error or a
    MemoryError on the stress collection; any other exception is raised without a record."""
    with queue.heavy('compute', ds.name, log=ds.paths.queue_log):
        entries = _inputs(ds)
        state_path = ds.paths.run_file('compute.json')
        ident = sandbox.identity(ds)
        colls = collections(ds)
        _, s_anchor, s_path = colls[0]
        keys_of, views_of, caches = {}, {}, {}

        def keys(path):
            if path not in keys_of:
                keys_of[path] = frame_keys(path)
            return keys_of[path]

        def kept(path, e):
            return present(ds, path, e, identity=ident, rows=len(keys(path)))

        def run(anchor, path, e):
            if path not in views_of:
                views_of[path] = sandbox.views_spec(ds, anchor, 'sidecar')
                caches[path] = {}
            frame, info = compute_table(ds, anchor, keys(path), e, caches[path], threads=threads,
                                        views=views_of[path])
            write_table(ds, path, e['table'], frame, e, info, identity=ident)

        for e in entries:                                  # 1. every table on the stress collection
            sha = _sha(e['sql'])
            old = (_load(state_path) or {}).get(e['table']) or {}
            if old.get('status') == 'failed_stress' and old.get('sql_sha256') == sha:
                raise SystemExit(f"{e['table']} failed on the stress collection ({old.get('error')}): "
                                 'rebuild the curation without it')
            if not kept(s_path, e):
                try:
                    run(s_anchor, s_path, e)
                except FAILURES as ex:
                    _put(ds, e['table'], dict(sql_sha256=sha, status='failed_stress', collections=[s_path.name],
                                              error=_error(ex), identity=ident))
                    raise SystemExit(f"{e['table']} failed on the stress collection {s_path.name}: {_error(ex)}; "
                                     'rebuild the curation without it') from None
            if not (old.get('status') == 'done' and old.get('sql_sha256') == sha and old.get('identity') == ident):
                _put(ds, e['table'], dict(sql_sha256=sha, status='stress_ok', collections=[s_path.name], error=None,
                                          identity=ident))
        for e in entries:                                  # 2. the missing (collection, table) pairs
            sha = _sha(e['sql'])
            done = []
            for _, anchor, path in colls:
                if not kept(path, e):
                    try:
                        run(anchor, path, e)
                    except FAILURES as ex:
                        _put(ds, e['table'], dict(sql_sha256=sha, status='stress_ok', collections=done,
                                                  error=f'{path.name}: {_error(ex)}', identity=ident))
                        raise
                done.append(path.name)
            _put(ds, e['table'], dict(sql_sha256=sha, status='done', collections=done, error=None, identity=ident))
        return _load(state_path) or {}
