"""Models of the agent-transfer experiment: fit (B, BA, BApl), contrast, gate, holdout, score.

Contract: docs/xfer-design.md, sections 1, 2, 4, 5 and 6, with the dataset documents
docs/xfer-tinkoff-design.md and docs/xfer-sber-design.md. Shared paths, formats,
the recipe, the permutation, the bootstrap and the reading rules live in
scripts/xfer_common.py; dataset logic (anchors, training rows, metric, Pop, the
Kaggle file) comes from the adapter through ``xc.adapter(dataset)``.

Run as ``python -I scripts/xfer_model.py <command> --dataset {tinkoff,sber} ...``;
stdout carries one JSON line, exit 0/1. Outputs under artifacts/xfer/<x>/:

``fits/<series>/<arm><seed>/``      report.json, model.cbm, scores-<collection>.parquet
                                    (user_id, item_id, score; RawFormulaVal) and, on
                                    val only, metrics-<collection>.parquet (user_id, value).
                                    A directory whose report says ``failed`` is renamed to
                                    ``<dir>.failed-<stamp>`` by the retry; a completed one is
                                    never touched.
``base-dev/<iter>/``                the same for a base iteration (arm B, dev, seed 2026)
``fits/contrast/<stamp>/``          contrast.json
``gate/stage<k>-<stamp>/``          gate.json
``holdout/<stamp>/``                result.json (copied to configs/datasets/xfer-<x>-holdout.json)
``kaggle/<arm><seed>/``             the adapter's assemble output (only after gate 2 passed)
``kaggle/reading-<stamp>/``         reading.json
Configs written for the coordinator to commit: xfer-<x>-prereg.json,
xfer-<x>-holdout-open.json and xfer-<x>-holdout.json.

Sealed holdout labels are read only by ``holdout(collection)`` (purpose holdout,
committed open receipt) and ``final_labels(collection)`` (purpose final,
committed result receipt).

Kaggle scoring chunks: KAGGLE_CHUNK users in ascending user_id over the users of
the kaggle frame (coordinator decision of 21.10).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import xfer_common as xc  # noqa: E402

KEYS = ['user_id', 'item_id']
FIT_FORMAT = 'xfer-fit-v1'
CONTRAST_FORMAT = 'xfer-contrast-v1'
GATE_FORMAT = 'xfer-gate-v1'
OPEN_FORMAT = 'xfer-holdout-open-v1'
RESULT_FORMAT = 'xfer-holdout-result-v1'
PREREG_FORMAT = 'xfer-prereg-v1'
READING_FORMAT = 'xfer-kaggle-reading-v1'
LEAKCHECK_FORMAT = 'xfer-leakcheck-v1'
REPORT_FILE = 'report.json'
GATE_FILE = 'gate.json'
MODEL_FILE = 'model.cbm'
PARITY = (0.5, 2.0)
DUCKDB_THREADS = xc.THREADS['collect']
MISSING_CATEGORY = '__MISSING__'
CONTRACT_DOC = 'docs/xfer-design.md'
DATASET_DOCS = {'tinkoff': 'docs/xfer-tinkoff-design.md', 'sber': 'docs/xfer-sber-design.md'}
DATASET_LABEL = {'tinkoff': 'Tinkoff', 'sber': 'СберМаркет'}
BASE_DEV_SEED = 2026
NO_AGENT = 'BA не построена: набор агента пуст'

GATE_RULE = dict(
    stage1=['leakcheck OK (report under leakcheck/, completed, result OK, this set, last train and holdout '
            'anchors on the current collections)',
            'finite B, BA and BApl scores on val and on the holdout frame',
            'finite share of every agent column on the holdout frame within [0.5*min, 2*max] of its shares on '
            'the training rows of the holdout series, per anchor',
            'dev metric of every B, BA and BApl fit >= Pop on val'],
    stage2=['finite scores on the kaggle frame',
            'finite-share parity on the kaggle frame against the training rows of the final series'],
    arms=dict(B=['finite', 'floor'], BA=['finite', 'floor', 'leakcheck', 'parity'],
              BApl=['finite', 'floor', 'leakcheck', 'parity']),
    stage2_arms=dict(B=['finite'], BA=['finite', 'parity'], BApl=['finite', 'parity']),
    parity=list(PARITY), opened='xfer_common.gate_arms(status)')
READING_RULE = dict(
    holdout='per seed D_s = BA_s - B_s and P_s = BA_s - BApl_s, paired bootstrap over queries '
            '(xfer_common.bootstrap); verdicts xfer_common.verdict_transfer / verdict_content; '
            'seed-mean D, P and BApl - B descriptive',
    kaggle='xfer_common.kaggle_reading on private scores, BA against B; descriptive')
PERMUTATION_RULE = ('numpy.random.default_rng([20261021, seed, anchor_int, chunk]).permutation(n) over the agent '
                    'block in user_id, item_id order: training - the rows of the anchor used in the fit, chunk 0; '
                    'val/holdout frames - all frame rows, chunk 0; kaggle - per chunk of KAGGLE_CHUNK users in '
                    'ascending user_id, chunk = 0-based index')


# ---------------------------------------------------------------- small helpers

class ArgumentError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError(message)


@contextlib.contextmanager
def quiet_stdout():
    """CatBoost and DuckDB messages go to stderr: stdout carries only the JSON line."""
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        os.dup2(2, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)


def stamp():
    return _dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def rel(path):
    return Path(path).resolve().relative_to(xc.ROOT.resolve()).as_posix()


def quote_name(name):
    return '"' + str(name).replace('"', '""') + '"'


def sql_path(path):
    return str(path).replace("'", "''")


def connect():
    import duckdb
    return duckdb.connect(config=dict(threads=DUCKDB_THREADS))


def recipe_for(seed):
    return dict(xc.RECIPE, random_seed=int(seed))


def recipe_without_seed():
    return {k: v for k, v in xc.RECIPE.items() if k != 'random_seed'}


def normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def query_targets(targets):
    return targets.loc[targets['n_targets'] >= 1, ['user_id', 'n_targets']].reset_index(drop=True)


def query_users(targets):
    return sorted({int(u) for u in query_targets(targets)['user_id']})


def keys_digest(frame):
    import numpy as np
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(frame['user_id'].to_numpy(dtype=np.int64)).tobytes())
    digest.update(np.ascontiguousarray(frame['item_id'].to_numpy(dtype=np.int64)).tobytes())
    return digest.hexdigest()


def rows_digest(block):
    """Training rows of one anchor: user_id, item_id, label, weight in (user_id, item_id) order."""
    import numpy as np
    digest = hashlib.sha256(keys_digest(block).encode())
    digest.update(np.ascontiguousarray(block['label'].to_numpy(dtype=np.int8)).tobytes())
    digest.update(np.ascontiguousarray(block['weight'].to_numpy(dtype=np.float64)).tobytes())
    return digest.hexdigest()


def ever_committed(path):
    """True when Git history has any commit touching ``path`` (even if it is deleted now)."""
    target = Path(path).resolve().relative_to(xc.ROOT.resolve()).as_posix()
    run = subprocess.run(['git', '-C', str(xc.ROOT), 'log', '--format=%H', '--', target],
                         capture_output=True, text=True, check=False)
    xc.require(run.returncode == 0, f'git log failed for {target}: {run.stderr.strip()[:200]}')
    return bool(run.stdout.strip())


def rel_or_absolute(path):
    """ROOT-relative posix path, or the absolute posix path outside ROOT (as xfer_agent._relative)."""
    path = Path(path).resolve()
    try:
        return path.relative_to(Path(xc.ROOT).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def collection_identity(path):
    """The collection identity xfer_agent writes into the leakcheck report (xfer_agent._collection_identity)."""
    path = Path(path).resolve()
    return dict(name=path.name, path=rel_or_absolute(path), manifest_sha256=xc.sha256_file(path/xc.MANIFEST_FILE))


# ---------------------------------------------------------------- sealed labels (the only two readers)

def holdout(collection):
    """Holdout labels and targets for the ``holdout`` command (committed open receipt)."""
    paths = xc.read_sealed(collection, 'holdout')
    return xc.read_parquet(paths['labels']), xc.read_parquet(paths['targets'])


def final_labels(collection):
    """Holdout labels and targets for the final series (committed result receipt)."""
    paths = xc.read_sealed(collection, 'final')
    return xc.read_parquet(paths['labels']), xc.read_parquet(paths['targets'])


def open_labels(collection):
    labels_file, targets_file = xc.LABEL_FILES
    return xc.read_parquet(Path(collection)/labels_file), xc.read_parquet(Path(collection)/targets_file)


# ---------------------------------------------------------------- context

class Context:
    """Dataset, adapter, anchors, base and (outside base-dev) the prereg and the agent set."""

    def __init__(self, dataset, base_dev=False, base=None, collections=None):
        self.dataset = xc.check_dataset(dataset)
        self.adapter = xc.adapter(dataset)
        self.anchors = self.adapter.anchors()
        self.N = self.anchors['N']
        self.K = int(self.anchors['K'])
        self.base_dev = base_dev
        self.collections = Path(collections) if collections is not None else None
        if base_dev:
            self.prereg = None
            self.prereg_sha256 = None
            self.base = xc.check_base(base, dataset)
            self.set_sha256 = None
            self.columns = []
            try:
                self.code = xc.code_identity(dataset)
            except ImportError as exc:  # base iterations may run before every shared module exists
                self.code = dict(error=f'{type(exc).__name__}: {exc}')
        else:
            self.prereg = xc.require_prereg(dataset)
            self.prereg_sha256 = xc.sha256_file(xc.config_path(dataset, 'prereg'))
            self.base = xc.read_base(dataset)
            xc.require(self.base['dataset'] == dataset, 'Base of another dataset')
            xc.require(self.base['digest'] == self.prereg['base_digest'], 'base.json digest differs from prereg')
            xc.require(normalized(self.anchors) == self.prereg['anchors'], 'Adapter anchors differ from prereg')
            xc.require(normalized(xc.RECIPE) == self.prereg['recipe'], 'Recipe differs from prereg')
            self.set_sha256 = self.prereg['set_sha256']
            agent_set = xc.read_json(xc.config_path(dataset, 'set'))
            self.columns = list(agent_set['columns']) if 'columns' in agent_set else None
            self.code = xc.code_identity(dataset)
        names = xc.base_feature_names(self.base)
        self.categorical = list(self.base['categorical'])
        self.numeric = [n for n in names if n not in self.categorical]
        self.base_names = names

    def series(self, name):
        spec = self.anchors['series'].get(name)
        xc.require(spec is not None, f'Unknown series {name!r}')
        return spec

    def role_of(self, anchor):
        for role in ('train', 'val', 'holdout'):
            if any(xc.anchor_text(a) == xc.anchor_text(anchor) for a in self.anchors['roles'].get(role, [])):
                return role
        raise xc.ContractError(f'Anchor {anchor} has no training role')

    def collection(self, role, anchor):
        if self.collections is not None:
            return self.collections/xc.collection_name(role, anchor)
        if role == 'holdout':  # the collection in force (deviation rebuilds included)
            return xc.current_holdout_collection(self.dataset, anchor)
        return xc.output_dir(self.dataset, 'collections', xc.collection_name(role, anchor))

    def check_collection(self, path, role):
        manifest = xc.read_collection(path, self.dataset, role, self.base)
        if self.prereg is not None:
            allowed = [self.prereg['code'], xc.latest_code(self.dataset, self.prereg)]
            xc.require(manifest['code'] in allowed, f'Collection {Path(path).name} code differs from prereg')
            xc.require(manifest['base_digest'] == self.prereg['base_digest'],
                       f'Collection {Path(path).name} base digest differs from prereg')
        return manifest

    def sidecar(self, collection):
        directory = xc.sidecar_dir(self.dataset, collection)
        manifest = xc.read_sidecar(directory, collection, self.set_sha256)
        if self.columns is None:
            self.columns = list(manifest['columns'])
        xc.require(self.columns, NO_AGENT)
        xc.require(list(manifest['columns']) == self.columns, f'Sidecar {directory.name} columns differ from the set')
        clash = set(self.columns) & (set(self.base_names) | set(KEYS) | {'label', 'weight', 'score'})
        xc.require(not clash, f'Agent columns clash with frame columns: {sorted(clash)}')
        return directory, manifest


# ---------------------------------------------------------------- rows

def frame_rows(con, collection, names, users=None, user_range=None):
    """Frame rows (keys and ``names``) ordered user_id, item_id; optionally restricted to users."""
    projection = ', '.join(quote_name(c) for c in KEYS+list(names))
    where = ''
    params = []
    if users is not None:
        import pandas as pd
        con.register('_xm_users', pd.DataFrame({'user_id': list(users)}, dtype='int64'))
        where = ' WHERE user_id IN (SELECT user_id FROM _xm_users)'
    elif user_range is not None:
        where = ' WHERE user_id BETWEEN ? AND ?'
        params = [int(user_range[0]), int(user_range[1])]
    try:
        return con.execute(f"SELECT {projection} FROM read_parquet('{sql_path(collection)}'){where} "
                           f'ORDER BY user_id, item_id', params).df()
    finally:
        if users is not None:
            con.unregister('_xm_users')


def check_sidecar_rows(con, collection, directory, manifest):
    """Whole-file check: the sidecar has one row per frame row, frame keys are unique."""
    frame = Path(collection)/xc.FRAME_FILE
    side = Path(directory)/xc.SIDECAR_FILE
    rows, distinct = con.execute(f"SELECT count(*), count(DISTINCT (user_id, item_id)) "
                                 f"FROM read_parquet('{sql_path(frame)}')").fetchone()
    side_rows = con.execute(f"SELECT count(*) FROM read_parquet('{sql_path(side)}')").fetchone()[0]
    xc.require(rows == distinct, f'Frame keys of {Path(collection).name} are not unique')
    xc.require(rows == side_rows == int(manifest['rows']), f'Sidecar rows differ from frame rows of {Path(collection).name}')


def with_agent(con, frame, directory, columns, users=None, user_range=None):
    """Attach the agent columns of the sidecar to ``frame``; keys must match row by row."""
    import numpy as np
    block = frame_rows(con, Path(directory)/xc.SIDECAR_FILE, columns, users, user_range)
    xc.require(len(block) == len(frame)
               and np.array_equal(block['user_id'].to_numpy(), frame['user_id'].to_numpy())
               and np.array_equal(block['item_id'].to_numpy(), frame['item_id'].to_numpy()),
               'Sidecar rows do not align with the frame keys')
    out = frame.reset_index(drop=True).copy()
    for column in columns:
        out[column] = block[column].to_numpy()
    return out


def finite_counts(frame, columns):
    """Per agent column: rows with a finite value (NULL, NaN and +-inf count as missing)."""
    import numpy as np
    block = agent_block(frame, columns)
    return {c: int(np.isfinite(block[:, i]).sum()) for i, c in enumerate(columns)}


def finite_shares(frame, columns):
    counts = finite_counts(frame, columns)
    return {c: counts[c]/len(frame) if len(frame) else 0.0 for c in columns}


def permute_agent(frame, columns, seed, anchor, chunk):
    """Row i of the agent block gets the values of row perm[i]; keys and the rest stay."""
    perm = xc.permutation(seed, anchor, chunk, len(frame))
    moved = frame[columns].iloc[perm].reset_index(drop=True)
    out = frame.reset_index(drop=True).copy()
    for column in columns:
        out[column] = moved[column].to_numpy()
    return out


def training_block(ctx, con, series, anchor, arm, seed):
    """Training rows of one anchor: capped queries -> adapter.training_rows -> features (+agent block)."""
    import numpy as np
    role = ctx.role_of(anchor)
    path = ctx.collection(role, anchor)
    manifest = ctx.check_collection(path, role)
    if role == 'holdout':
        xc.require(series == 'final', 'Only the final series trains on the holdout anchor')
        labels, targets = final_labels(path)
    else:
        labels, targets = open_labels(path)
    del manifest
    pool = query_users(targets)
    capped = xc.cap_queries(pool, ctx.N)
    frame = frame_rows(con, path/xc.FRAME_FILE, ctx.base_names, capped)
    agent = arm != 'B'
    if agent:
        directory, side = ctx.sidecar(path)
        check_sidecar_rows(con, path, directory, side)
        frame = with_agent(con, frame, directory, ctx.columns, capped)
    chosen = set(capped)
    lab = labels[labels['user_id'].isin(chosen)].sort_values(KEYS).reset_index(drop=True)
    rows = ctx.adapter.training_rows(frame[KEYS+ctx.base_names].copy(), lab, anchor, seed=xc.SAMPLE_SEED)
    rows = rows[KEYS+['label', 'weight']].reset_index(drop=True)
    xc.require(not rows.duplicated(KEYS).any(), f'training_rows repeated a key at {anchor}')
    block = frame.merge(rows, on=KEYS, how='inner', validate='one_to_one')
    xc.require(len(block) == len(rows), f'training_rows returned keys outside the frame at {anchor}')
    block = block.sort_values(KEYS, kind='mergesort').reset_index(drop=True)
    block['label'] = block['label'].astype(np.int8)
    block['weight'] = block['weight'].astype(np.float64)
    xc.require(bool(np.isfinite(block['weight']).all() and (block['weight'] > 0).all()),
               f'Training weights must be finite and positive at {anchor}')
    shares = finite_shares(block, ctx.columns) if agent else None
    permuted = None
    if arm == 'BApl':
        block = permute_agent(block, ctx.columns, seed, anchor, 0)
        permuted = dict(anchor=anchor, chunk=0, rows=len(block))
    population = dict(anchor=anchor, role=role, collection=path.name,
                      manifest_sha256=xc.sha256_file(path/xc.MANIFEST_FILE), query_pool=len(pool),
                      queries=len(capped), users=int(block['user_id'].nunique()), rows=len(block),
                      rows_sha256=rows_digest(block))
    inputs = dict(collection=(path.name, population['manifest_sha256']),
                  sidecar=(path.name, xc.sha256_file(Path(xc.sidecar_dir(ctx.dataset, path))/xc.MANIFEST_FILE))
                  if agent else None)
    return block, population, shares, permuted, inputs


# ---------------------------------------------------------------- model

def category_values(series):
    """Categorical values as strings, per value: an integral float 3.0 becomes '3', NULL a marker."""
    import numpy as np
    import pandas as pd
    if pd.api.types.is_bool_dtype(series):
        series = series.astype('Int64')
    if pd.api.types.is_numeric_dtype(series):
        values = series.to_numpy(dtype=np.float64, na_value=np.nan)
        out = np.full(len(values), MISSING_CATEGORY, dtype=object)
        finite = np.isfinite(values)
        integral = finite & (values == np.floor(values)) & (np.abs(values) < 2**63)
        out[integral] = values[integral].astype(np.int64).astype(str)
        rest = finite & ~integral
        out[rest] = values[rest].astype(str)
        return out

    def one(value):
        if value is None or value is pd.NA or (isinstance(value, float) and value != value):
            return MISSING_CATEGORY
        if isinstance(value, (bool, np.bool_)):
            return str(int(value))
        if isinstance(value, (float, np.floating)) and float(value).is_integer():
            return str(int(value))
        if isinstance(value, (int, np.integer)):
            return str(int(value))
        return str(value)
    return np.asarray([one(v) for v in series.to_numpy(dtype=object)], dtype=object)


def agent_block(frame, columns):
    """Agent columns as float32; NULL, NaN, +-inf and float32 overflow become NaN (H&M agent_block)."""
    import numpy as np
    if not columns:
        return np.empty((len(frame), 0), dtype=np.float32)
    values = frame[list(columns)].to_numpy(dtype=np.float64, na_value=np.nan)
    with np.errstate(over='ignore', invalid='ignore'):
        block = values.astype(np.float32)
    block[~np.isfinite(block)] = np.nan
    return block


def matrices(ctx, frame, columns):
    import numpy as np
    if ctx.numeric:
        numbers = frame[ctx.numeric].to_numpy(dtype=np.float64, na_value=np.nan)
        xc.require(not np.isinf(numbers).any(), 'Base numeric features must not be infinite')
        numbers = numbers.astype(np.float32)
    else:
        numbers = np.empty((len(frame), 0), dtype=np.float32)
    numbers = np.ascontiguousarray(np.hstack([numbers, agent_block(frame, columns)]))
    if ctx.categorical:
        cats = np.column_stack([category_values(frame[c]) for c in ctx.categorical]).astype(object)
    else:
        cats = np.empty((len(frame), 0), dtype=object)
    return numbers, cats


def make_pool(numbers, cats, numeric_names, cat_names, label=None, weight=None):
    from catboost import FeaturesData, Pool
    data = FeaturesData(num_feature_data=numbers if numeric_names else None,
                        cat_feature_data=cats if cat_names else None,
                        num_feature_names=list(numeric_names) if numeric_names else None,
                        cat_feature_names=list(cat_names) if cat_names else None)
    return Pool(data, label=label, weight=weight)


def predict(ctx, model, frame, columns):
    numbers, cats = matrices(ctx, frame, columns)
    pool = make_pool(numbers, cats, ctx.numeric+list(columns), ctx.categorical)
    return model.predict(pool, prediction_type=xc.PREDICTION_TYPE, thread_count=xc.RECIPE['thread_count'])


def top_k(scores, k):
    """user_id, item_id, rank: the k best rows per user by score desc, item_id asc."""
    import numpy as np
    users = scores['user_id'].to_numpy()
    items = scores['item_id'].to_numpy()
    values = scores['score'].to_numpy(dtype=np.float64)
    order = np.lexsort((items, -values, users))
    ranked = scores.iloc[order][KEYS].reset_index(drop=True)
    ranked['rank'] = ranked.groupby('user_id', sort=False).cumcount()+1
    return ranked[ranked['rank'] <= k].reset_index(drop=True)


def per_query(values, targets):
    """adapter.metric output -> {user_id: value}, one finite value per query of targets."""
    import numpy as np
    users = query_users(targets)
    out = {int(u): float(v) for u, v in zip(values['user_id'], values['value'])}
    xc.require(sorted(out) == users and len(out) == len(values), 'Metric must give one value per query')
    xc.require(bool(np.isfinite(list(out.values())).all()), 'Metric values must be finite')
    return out


def metric_of(ctx, ranked, targets, labels):
    """adapter.metric on the queries only (n_targets >= 1), ranked rows of other users dropped."""
    queries = query_targets(targets)
    ranked = ranked[ranked['user_id'].isin(set(queries['user_id']))][['user_id', 'item_id', 'rank']]
    return per_query(ctx.adapter.metric(ranked.reset_index(drop=True), queries, labels), queries)


def evaluate(ctx, scores, targets, labels):
    return metric_of(ctx, top_k(scores, ctx.K), targets, labels)


def pop_metric(ctx, anchor, targets, labels):
    return metric_of(ctx, ctx.adapter.pop(anchor, query_users(targets), ctx.K), targets, labels)


def mean(values):
    return float(sum(values.values())/len(values)) if values else None


# ---------------------------------------------------------------- scoring

def score_rows(ctx, con, path, arm, seed, anchor, model, users=None, user_range=None, chunk=0, directory=None):
    """Scores of the frame rows (all, or one user range) with the agent block (permuted for BApl)."""
    frame = frame_rows(con, path/xc.FRAME_FILE, ctx.base_names, users, user_range)
    columns = ctx.columns if arm != 'B' else []
    counts = None
    if arm != 'B':
        frame = with_agent(con, frame, directory, columns, users, user_range)
        counts = finite_counts(frame, columns)
        if arm == 'BApl':
            frame = permute_agent(frame, columns, seed, anchor, chunk)
    scores = frame[KEYS].copy()
    scores['score'] = predict(ctx, model, frame, columns) if len(frame) else []
    return scores, counts, len(frame)


def score_chunked(ctx, con, path, arm, seed, anchor, model, chunk_users, directory=None):
    """Kaggle scoring: chunks of ``chunk_users`` users in ascending user_id; BApl permutes per chunk."""
    import pandas as pd
    users = [int(u) for (u,) in con.execute(f"SELECT DISTINCT user_id FROM read_parquet('"
                                             f"{sql_path(path/xc.FRAME_FILE)}') ORDER BY 1").fetchall()]
    xc.require(int(chunk_users) >= 1, 'Chunk size must be positive')
    parts, counts, permuted, rows = [], {}, [], 0
    for index, start in enumerate(range(0, len(users), int(chunk_users))):
        chunk = users[start:start+int(chunk_users)]
        scores, found, n = score_rows(ctx, con, path, arm, seed, anchor, model, user_range=(chunk[0], chunk[-1]),
                                      chunk=index, directory=directory)
        xc.require(set(scores['user_id'].unique()) <= set(chunk), 'Chunk rows outside the chunk users')
        parts.append(scores)
        rows += n
        for c, v in (found or {}).items():
            counts[c] = counts.get(c, 0)+v
        if arm == 'BApl':
            permuted.append(dict(anchor=anchor, chunk=index, rows=n))
    scores = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=KEYS+['score'])
    shares = {c: v/rows if rows else 0.0 for c, v in counts.items()} if arm != 'B' else None
    return scores, shares, permuted, dict(chunk_users=int(chunk_users), chunks=len(parts), users=len(users))


# ---------------------------------------------------------------- fit

def fit_dir(dataset, series, arm, seed):
    return xc.output_dir(dataset, 'fits', series, f'{arm}{seed}')


def clear_failed(output):
    """A retry moves a failed fit aside as <dir>.failed-<stamp>; anything else is refused."""
    output = Path(output)
    if not output.exists():
        return None
    report = output/REPORT_FILE
    xc.require(report.exists(), f'{output} exists without a report; it is not a failed fit')
    status = xc.read_json(report).get('status')
    xc.require(status == 'failed', f'{output} has status {status!r}; only a failed fit is retried')
    moved = output.with_name(f'{output.name}.failed-{stamp()}')
    output.rename(moved)
    return moved


def fit(ctx, series, arm, seed, output):
    """One fit of ``arm`` on the training anchors of ``series`` and the scores of its eval collection."""
    import numpy as np
    from catboost import CatBoostClassifier
    spec = ctx.series(series)
    xc.require(arm in spec['arms'], f'Arm {arm} is not in series {series}')
    xc.require(ctx.base_dev or int(seed) in xc.SEEDS, f'Seed {seed} is not preregistered')
    agent = arm != 'B'
    xc.require(not agent or ctx.columns is None or ctx.columns, NO_AGENT)
    output = xc.new_output(output)
    started = time.monotonic()
    timings = {}
    recipe = recipe_for(seed)
    report = dict(format=FIT_FORMAT, status='running', dataset=ctx.dataset, series=series, arm=arm, seed=int(seed),
                  base_dev=ctx.base_dev, prereg_sha256=ctx.prereg_sha256, recipe=recipe, code=ctx.code,
                  threads=dict(catboost=recipe['thread_count'], duckdb=DUCKDB_THREADS), created_utc=xc.utc_now())
    con = connect()
    try:
        parts, populations, train_shares, permuted = [], [], {}, []
        inputs = dict(collections={}, sidecars={})
        for anchor in sorted(spec['train'], key=xc.anchor_int):
            block, population, shares, perm, used = training_block(ctx, con, series, anchor, arm, seed)
            numbers, cats = matrices(ctx, block, ctx.columns if agent else [])
            parts.append((numbers, cats, block['label'].to_numpy(dtype=np.int8),
                          block['weight'].to_numpy(dtype=np.float64)))
            populations.append(population)
            inputs['collections'][used['collection'][0]] = used['collection'][1]
            if agent:
                train_shares[xc.anchor_text(anchor)] = shares
                inputs['sidecars'][used['sidecar'][0]] = used['sidecar'][1]
            if perm:
                permuted.append(perm)
            del block
        timings['load_seconds'] = round(time.monotonic()-started, 3)
        columns = list(ctx.columns) if agent else []
        numbers = np.ascontiguousarray(np.concatenate([p[0] for p in parts]))
        cats = np.concatenate([p[1] for p in parts])
        labels = np.concatenate([p[2] for p in parts])
        weights = np.concatenate([p[3] for p in parts])
        del parts
        xc.require(len(np.unique(labels)) == 2, 'Training needs both label classes')
        numeric_names = ctx.numeric+columns
        report['features'] = dict(numeric=ctx.numeric, agent=columns, categorical=ctx.categorical)
        report['identity'] = dict(dataset=ctx.dataset, series=series, recipe=recipe_without_seed(),
                                  training_populations=populations, base_digest=ctx.base['digest'],
                                  set_sha256=ctx.set_sha256)
        report['identity_digest'] = xc.canonical_digest(normalized(report['identity']))
        tick = time.monotonic()
        model = CatBoostClassifier(**recipe)
        model.fit(make_pool(numbers, cats, numeric_names, ctx.categorical, labels, weights))
        timings['fit_seconds'] = round(time.monotonic()-tick, 3)
        del numbers, cats, labels, weights
        xc.require(model.tree_count_ == recipe['iterations'], 'Fixed-tree fit incomplete')
        xc.require(list(model.feature_names_) == numeric_names+ctx.categorical, 'Fitted feature vector differs')
        model.save_model(str(output/MODEL_FILE))

        tick = time.monotonic()
        anchor, role = spec['eval'], spec['eval_role']
        path = ctx.collection(role, anchor)
        manifest_sha = xc.sha256_file(path/xc.MANIFEST_FILE)
        ctx.check_collection(path, role)
        inputs['collections'][path.name] = manifest_sha
        directory = None
        if agent:
            directory, side = ctx.sidecar(path)
            check_sidecar_rows(con, path, directory, side)
            inputs['sidecars'][path.name] = xc.sha256_file(directory/xc.MANIFEST_FILE)
        evaluation = dict(collection=path.name, role=role, anchor=anchor, manifest_sha256=manifest_sha)
        if role == 'kaggle':
            scores, shares, chunk_perm, chunking = score_chunked(ctx, con, path, arm, seed, anchor, model,
                                                                 xc.KAGGLE_CHUNK[ctx.dataset], directory)
            permuted += chunk_perm
            evaluation['chunking'] = chunking
        else:
            scores, counts, n = score_rows(ctx, con, path, arm, seed, anchor, model, directory=directory)
            shares = {c: v/n if n else 0.0 for c, v in counts.items()} if agent else None
            if arm == 'BApl':
                permuted.append(dict(anchor=anchor, chunk=0, rows=n))
        scores = scores.sort_values(KEYS, kind='mergesort').reset_index(drop=True)
        name = f'scores-{path.name}.parquet'
        xc.write_parquet(scores, output/name, order_by='user_id, item_id')
        evaluation.update(rows=len(scores), users=int(scores['user_id'].nunique()), keys_sha256=keys_digest(scores),
                          scores_file=name, scores_sha256=xc.sha256_file(output/name),
                          finite=bool(np.isfinite(scores['score'].to_numpy(dtype=np.float64)).all()))
        if role == 'val':
            import pandas as pd
            labels_frame, targets = open_labels(path)
            values = evaluate(ctx, scores, targets, labels_frame)
            metric_name = f'metrics-{path.name}.parquet'
            xc.write_parquet(pd.DataFrame(dict(user_id=list(values), value=list(values.values()))),
                             output/metric_name, order_by='user_id')
            evaluation.update(metric=mean(values), queries=len(values), metrics_file=metric_name,
                              metrics_sha256=xc.sha256_file(output/metric_name))
            if ctx.base_dev:
                evaluation['pop_metric'] = mean(pop_metric(ctx, anchor, targets, labels_frame))
        timings['score_seconds'] = round(time.monotonic()-tick, 3)
        report['eval'] = evaluation
        if agent:
            report['agent_nonnull'] = dict(definition='share of finite values', train=train_shares, eval=shares)
        if arm == 'BApl':
            report['permutation'] = dict(rule=PERMUTATION_RULE, permuted=normalized(permuted))
        report['inputs'] = inputs
        report['files'] = {MODEL_FILE: xc.sha256_file(output/MODEL_FILE), name: evaluation['scores_sha256']}
        if 'metrics_file' in evaluation:
            report['files'][evaluation['metrics_file']] = evaluation['metrics_sha256']
        report['status'] = 'completed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        raise
    finally:
        con.close()
        timings['total_seconds'] = round(time.monotonic()-started, 3)
        report['timings'] = timings
        xc.atomic_json(output/REPORT_FILE, normalized(report))
    return report


def summary(report, output, retried=None):
    out = dict(output=rel(output), arm=report['arm'], seed=report['seed'], series=report['series'],
               training_populations=[dict(anchor=p['anchor'], queries=p['queries'], rows=p['rows'])
                                     for p in report['identity']['training_populations']],
               eval=dict((k, report['eval'][k]) for k in ('collection', 'rows', 'finite') if k in report['eval']))
    for key in ('metric', 'pop_metric', 'queries'):
        if key in report['eval']:
            out['eval'][key] = report['eval'][key]
    if retried is not None:
        out['moved_failed'] = rel(retried)
    return out


# ---------------------------------------------------------------- reading fits

def load_fit(ctx, series, arm, seed):
    directory = fit_dir(ctx.dataset, series, arm, seed)
    path = directory/REPORT_FILE
    xc.require(path.exists(), f'No fit report {path}')
    report = xc.read_json(path)
    xc.require(report.get('format') == FIT_FORMAT and report.get('status') == 'completed', f'Fit {path} not completed')
    xc.require((report['dataset'], report['series'], report['arm'], report['seed'], report['base_dev']) ==
               (ctx.dataset, series, arm, int(seed), False), f'Fit {path} is not {series} {arm}{seed}')
    xc.require(report['prereg_sha256'] == ctx.prereg_sha256, f'Fit {path} ran under another prereg')
    for name, digest in report['files'].items():
        xc.require(xc.sha256_file(directory/name) == digest, f'Fit file changed: {directory/name}')
    return directory, report


def load_fits(ctx, series, arms):
    return {(arm, seed): load_fit(ctx, series, arm, seed) for arm in arms for seed in xc.SEEDS}


def check_pairing(fits):
    """Identical training rows, recipes except random_seed, base, set, code and eval rows."""
    reports = [r for _, r in fits.values()]
    xc.require(reports, 'No fits to pair')
    for r in reports:
        xc.require(xc.canonical_digest(r['identity']) == r['identity_digest'], 'Fit identity digest mismatch')
        xc.require({k: v for k, v in r['recipe'].items() if k != 'random_seed'} == r['identity']['recipe'],
                   'Fit recipe differs from its identity')
        xc.require(r['recipe']['random_seed'] == r['seed'], 'Fit recipe seed differs from its seed')
        xc.require(all('rows_sha256' in p for p in r['identity']['training_populations']),
                   'Fit identity lacks the training row digests')
    xc.require(len({r['identity_digest'] for r in reports}) == 1, 'Fits are not paired: identities differ')
    xc.require(len({xc.canonical_digest(r['code']) for r in reports}) == 1, 'Fits are not paired: code differs')
    evals = {(r['eval']['collection'], r['eval']['manifest_sha256'], r['eval']['rows'], r['eval']['keys_sha256'])
             for r in reports}
    xc.require(len(evals) == 1, 'Fits are not paired: eval rows differ')
    return reports[0]['identity_digest']


def read_scores(directory, report):
    path = Path(directory)/report['eval']['scores_file']
    xc.require(xc.sha256_file(path) == report['eval']['scores_sha256'], f'Score file changed: {path}')
    scores = xc.read_parquet(path)
    xc.require(keys_digest(scores) == report['eval']['keys_sha256'], f'Score keys changed: {path}')
    return scores


def read_metrics(directory, report):
    path = Path(directory)/report['eval']['metrics_file']
    xc.require(xc.sha256_file(path) == report['eval']['metrics_sha256'], f'Metric file changed: {path}')
    frame = xc.read_parquet(path)
    return {int(u): float(v) for u, v in zip(frame['user_id'], frame['value'])}


def seed_mean(per_seed):
    users = sorted(per_seed[0])
    for values in per_seed:
        xc.require(sorted(values) == users, 'Seeds must share the queries')
    return {u: sum(v[u] for v in per_seed)/len(per_seed) for u in users}


def contrasts(values, reference, alternatives):
    """Per seed and seed-mean bootstrap of alternative - reference (descriptive)."""
    out = {}
    for alt in alternatives:
        per_seed = {str(s): xc.bootstrap(values[(reference, s)], values[(alt, s)]) for s in xc.SEEDS}
        mean_ref = seed_mean([values[(reference, s)] for s in xc.SEEDS])
        mean_alt = seed_mean([values[(alt, s)] for s in xc.SEEDS])
        out[f'{alt}-{reference}'] = dict(per_seed=per_seed, seed_mean=xc.bootstrap(mean_ref, mean_alt))
    return out


def readings(values, dataset):
    """Holdout reading from per-query metrics {(arm, seed): {user: value}} of B, BA and BApl."""
    d = [xc.bootstrap(values[('B', s)], values[('BA', s)]) for s in xc.SEEDS]
    p = [xc.bootstrap(values[('BApl', s)], values[('BA', s)]) for s in xc.SEEDS]
    means = {arm: seed_mean([values[(arm, s)] for s in xc.SEEDS]) for arm in xc.ARMS}
    return dict(D={str(s): b for s, b in zip(xc.SEEDS, d)}, P={str(s): b for s, b in zip(xc.SEEDS, p)},
                verdict_transfer=xc.verdict_transfer([b['ci'] for b in d], DATASET_LABEL[dataset]),
                verdict_content=xc.verdict_content([b['ci'] for b in p]),
                descriptive=dict(D=xc.bootstrap(means['B'], means['BA']), P=xc.bootstrap(means['BApl'], means['BA']),
                                 BApl_minus_B=xc.bootstrap(means['B'], means['BApl'])))


# ---------------------------------------------------------------- contrast

def contrast(ctx):
    spec = ctx.series('dev')
    fits = load_fits(ctx, 'dev', xc.ARMS)
    identity = check_pairing(fits)
    anchor = spec['eval']
    path = ctx.collection(spec['eval_role'], anchor)
    labels, targets = open_labels(path)
    values = {key: read_metrics(directory, report) for key, (directory, report) in fits.items()}
    pop = pop_metric(ctx, anchor, targets, labels)
    output = xc.new_output(xc.output_dir(ctx.dataset, 'fits', 'contrast', stamp()))
    result = dict(format=CONTRAST_FORMAT, dataset=ctx.dataset, series='dev', descriptive=True,
                  prereg_sha256=ctx.prereg_sha256, identity_digest=identity, queries=len(pop),
                  metrics={f'{a}{s}': mean(values[(a, s)]) for a, s in fits}, pop=mean(pop),
                  contrasts=contrasts(values, 'B', ['BA', 'BApl']), code=ctx.code, created_utc=xc.utc_now())
    xc.atomic_json(output/'contrast.json', normalized(result))
    return dict(output=rel(output), metrics=result['metrics'], pop=result['pop'],
                contrasts={k: dict(per_seed={s: v['ci'] for s, v in c['per_seed'].items()}, seed_mean=c['seed_mean']['ci'])
                           for k, c in result['contrasts'].items()})


# ---------------------------------------------------------------- gate

def parity_ok(share, shares):
    """Finite share within [0.5*min, 2*max] of the training shares (contract section 5)."""
    return bool(shares) and PARITY[0]*min(shares) <= share <= PARITY[1]*max(shares)


def parity(train, target, columns):
    out = {}
    for column in columns:
        shares = [train[a][column] for a in sorted(train)]
        out[column] = dict(share=target[column], min=min(shares), max=max(shares),
                           ok=parity_ok(target[column], shares))
    return dict(ok=bool(columns) and all(v['ok'] for v in out.values()), columns=out)


def agent_shares(fits, agent_arms):
    """Shares recorded by the agent fits; they must agree (same rows in every fit)."""
    found = {xc.canonical_digest(r['agent_nonnull']) for (arm, _), (_, r) in fits.items() if arm in agent_arms}
    xc.require(len(found) == 1, 'Agent fits disagree on finite shares')
    return next(r['agent_nonnull'] for (arm, _), (_, r) in fits.items() if arm in agent_arms)


def leakcheck_check(ctx, path):
    """Leakcheck report of xfer_agent: where it lives, what it says and which collections it checked."""
    path = Path(path)
    path = (path if path.is_absolute() else xc.ROOT/path).resolve()
    root = xc.output_dir(ctx.dataset, 'leakcheck').resolve()
    out = dict(path=rel_or_absolute(path), sha256=None, ok=False, problems=[])
    if not path.is_relative_to(root) or path == root:
        out['problems'].append('report is not under leakcheck/')
    if not path.is_file():
        out['problems'].append('report file is missing')
        return out
    out['sha256'] = xc.sha256_file(path)
    data = xc.read_json(path)
    expected = dict(format=LEAKCHECK_FORMAT, status='completed', result='OK', dataset=ctx.dataset)
    for key, value in expected.items():
        if data.get(key) != value:
            out['problems'].append(f'{key} is {data.get(key)!r}, expected {value!r}')
    if data.get('ok') is not True:
        out['problems'].append('ok is not true')
    if data.get('set_sha256') != ctx.prereg['set_sha256']:
        out['problems'].append('set_sha256 differs from prereg')
    last_train = max(ctx.anchors['roles']['train'], key=xc.anchor_int)
    hold = ctx.anchors['holdout']
    wanted = {xc.anchor_text(last_train): ctx.collection('train', last_train),
              xc.anchor_text(hold): ctx.collection('holdout', hold)}
    anchors = data.get('anchors') or {}
    if set(anchors) != set(wanted):
        out['problems'].append(f'anchors {sorted(anchors)} differ from {sorted(wanted)}')
    for anchor, collection in wanted.items():
        record = anchors.get(anchor) or {}
        if not (collection/xc.MANIFEST_FILE).is_file() or record.get('collection') != collection_identity(collection):
            out['problems'].append(f'anchor {anchor}: collection identity differs from {collection.name}')
    out['ok'] = not out['problems']
    return out


def finite_scores(fits):
    import numpy as np
    out = {}
    for (arm, seed), (directory, report) in fits.items():
        scores = read_scores(directory, report)
        out[f'{arm}{seed}'] = bool(np.isfinite(scores['score'].to_numpy(dtype=np.float64)).all())
    return out


def stage1_status(checks):
    """Per-arm status from the stage 1 checks: B needs finite and floor; BA/BApl also leakcheck and parity."""
    def ok(arm):
        good = all(checks['finite'][part][f'{arm}{s}'] for part in checks['finite'] for s in xc.SEEDS)
        good = good and all(checks['floor'][f'{arm}{s}']['ok'] for s in xc.SEEDS)
        return bool(good and (arm == 'B' or (checks['leakcheck']['ok'] and checks['parity']['ok'])))
    return {arm: ok(arm) for arm in xc.ARMS}


def stage2_status(checks, arms):
    return {arm: bool(all(checks['finite']['final'][f'{arm}{s}'] for s in xc.SEEDS)
                      and (arm == 'B' or checks['parity']['ok'])) for arm in arms}


def stage1_checks(ctx, leakcheck):
    """Every stage 1 check from the files: fits (hashed), score and metrics files, the leakcheck report.

    The gate writes them; holdout-open recomputes them and refuses a gate.json that differs.
    """
    dev = load_fits(ctx, 'dev', xc.ARMS)
    hold = load_fits(ctx, 'holdout', xc.ARMS)
    check_pairing(dev)
    check_pairing(hold)
    leak = leakcheck_check(ctx, leakcheck)
    finite = dict(dev=finite_scores(dev), holdout=finite_scores(hold))
    shares = agent_shares(hold, ('BA', 'BApl'))
    par = parity(shares['train'], shares['eval'], list(shares['eval']))
    spec = ctx.series('dev')
    labels, targets = open_labels(ctx.collection(spec['eval_role'], spec['eval']))
    pop = mean(pop_metric(ctx, spec['eval'], targets, labels))
    floor = {}
    for (a, s), (directory, report) in dev.items():
        value = mean(read_metrics(directory, report))  # hashed metrics file, not the report's number
        floor[f'{a}{s}'] = dict(metric=value, pop=pop, ok=bool(value >= pop))
    checks = dict(leakcheck=leak, finite=finite, parity=par, floor=floor)
    return normalized(checks), dev, hold


def run_gate(ctx, stage, leakcheck=None):
    if stage == 1:
        xc.require(leakcheck is not None, 'Gate 1 needs --leakcheck')
        checks, dev, hold = stage1_checks(ctx, leakcheck)
        status = stage1_status(checks)
        score_files = {rel(d/r['eval']['scores_file']): r['eval']['scores_sha256'] for d, r in hold.values()}
        fits = list(dev.values())+list(hold.values())
    else:
        spec = ctx.series('final')
        final = load_fits(ctx, 'final', spec['arms'])
        check_pairing(final)
        finite = dict(final=finite_scores(final))
        agent_arms = [a for a in spec['arms'] if a != 'B']
        par = None
        if agent_arms:
            shares = agent_shares(final, agent_arms)
            par = parity(shares['train'], shares['eval'], list(shares['eval']))
        checks = dict(finite=finite, parity=par)
        status = stage2_status(checks, spec['arms'])
        score_files = {rel(d/r['eval']['scores_file']): r['eval']['scores_sha256'] for d, r in final.values()}
        fits = list(final.values())
    reports = {rel(d/REPORT_FILE): xc.sha256_file(d/REPORT_FILE) for d, _ in fits}
    output = xc.new_output(xc.output_dir(ctx.dataset, 'gate', f'stage{stage}-{stamp()}'))
    result = dict(format=GATE_FORMAT, dataset=ctx.dataset, stage=int(stage), ok=all(status.values()), status=status,
                  checks=checks, score_files=score_files, fit_reports=reports, prereg_sha256=ctx.prereg_sha256,
                  code=ctx.code, created_utc=xc.utc_now())
    xc.atomic_json(output/GATE_FILE, normalized(result))
    return dict(output=rel(output/GATE_FILE), stage=int(stage), gate_ok=result['ok'], status=status)


# ---------------------------------------------------------------- holdout

def verify_hashes(hashes, what):
    for name, digest in hashes.items():
        path = xc.ROOT/name
        xc.require(path.is_file() and xc.sha256_file(path) == digest, f'{what} changed since the gate: {name}')


def holdout_open(ctx, gate_path, quote):
    path = xc.config_path(ctx.dataset, 'holdout-open')
    xc.require(not path.exists(), f'{path.name} already exists')
    xc.require(not ever_committed(path), f'{path.name} was committed before; holdout opens once')
    xc.require(isinstance(quote, str) and quote.strip(), 'The quote of the user is required')
    gate_path = Path(gate_path).resolve()
    root = xc.output_dir(ctx.dataset, 'gate').resolve()
    xc.require(gate_path.name == GATE_FILE and gate_path.parent.parent == root
               and gate_path.parent.name.startswith('stage1-'), 'The gate must be gate/stage1-*/gate.json')
    record = xc.read_json(gate_path)
    xc.require(record.get('format') == GATE_FORMAT and record.get('dataset') == ctx.dataset and record.get('stage') == 1,
               'Not a stage 1 gate report of this dataset')
    xc.require(record['prereg_sha256'] == ctx.prereg_sha256, 'Gate ran under another prereg')
    status = stage1_status(record['checks'])
    xc.require(status == record['status'] and record['ok'] == all(status.values()),
               'Gate status differs from its checks')
    verify_hashes(record['score_files'], 'Score file')
    verify_hashes(record['fit_reports'], 'Fit report')
    leak = record['checks']['leakcheck']
    xc.require(leak.get('sha256') is not None and leak.get('path'), 'Gate records no leakcheck report')
    leak_path = Path(leak['path'])
    leak_path = leak_path if leak_path.is_absolute() else xc.ROOT/leak_path
    xc.require(leak_path.is_file() and xc.sha256_file(leak_path) == leak['sha256'],
               f"Leakcheck report changed since the gate: {leak['path']}")
    checks, dev, hold = stage1_checks(ctx, leak_path)
    reports = {rel(d/REPORT_FILE): xc.sha256_file(d/REPORT_FILE) for d, _ in list(dev.values())+list(hold.values())}
    xc.require(reports == record['fit_reports'], 'Gate fit reports differ from the fits in force')
    scores = {rel(d/r['eval']['scores_file']): r['eval']['scores_sha256'] for d, r in hold.values()}
    xc.require(scores == record['score_files'], 'Gate score files differ from the holdout fits in force')
    differ = sorted(k for k in checks if checks[k] != record['checks'].get(k))
    xc.require(not differ, f'Gate checks differ from a recomputation: {differ}')
    xc.require(stage1_status(checks) == status, 'Gate status differs from a recomputation')
    receipt = dict(format=OPEN_FORMAT, dataset=ctx.dataset, gate=dict(path=rel(gate_path), sha256=xc.sha256_file(gate_path)),
                   gate_ok=record['ok'], status=status, arms=xc.gate_arms(status),
                   score_files=record['score_files'], fit_reports=record['fit_reports'],
                   prereg_sha256=xc.sha256_file(xc.config_path(ctx.dataset, 'prereg')), opened_utc=xc.utc_now(),
                   quote=quote)
    xc.atomic_json(path, receipt)
    return dict(output=rel(path), arms=receipt['arms'], gate_ok=receipt['gate_ok'])


def earlier_results(dataset):
    root = xc.output_dir(dataset, 'holdout')
    found = sorted(root.glob('*/*.json')) if root.exists() else []
    if xc.config_path(dataset, 'holdout').exists():
        found.append(xc.config_path(dataset, 'holdout'))
    return found


def check_rerun(dataset):
    """Existing holdout/* runs (crashed before JSON) need the latest deviation: step holdout naming them."""
    root = xc.output_dir(dataset, 'holdout')
    existing = sorted(rel(p) for p in root.iterdir() if p.is_dir()) if root.exists() else []
    if not existing:
        return []
    records = xc.deviations(dataset)
    xc.require(records and records[-1].get('step') == 'holdout', f'Earlier holdout runs {existing} need a deviation')
    named = set(records[-1].get('supersedes', []))
    xc.require(set(existing) <= named, f'The latest holdout deviation does not name {sorted(set(existing)-named)}')
    xc.require(xc.committed_clean(xc.config_path(dataset, 'deviations')), 'The deviations file must be committed')
    return existing


def holdout_command(ctx):
    receipt_path = xc.config_path(ctx.dataset, 'holdout-open')
    result_path = xc.config_path(ctx.dataset, 'holdout')
    xc.require(xc.committed_clean(receipt_path), 'holdout needs the committed open receipt')
    xc.require(not ever_committed(result_path), f'{result_path.name} was committed before; holdout runs once')
    earlier = earlier_results(ctx.dataset)
    xc.require(not earlier, f'An earlier holdout result exists: {[str(p) for p in earlier]}')
    reruns = check_rerun(ctx.dataset)
    receipt = xc.read_json(receipt_path)
    xc.require(receipt.get('format') == OPEN_FORMAT and receipt['dataset'] == ctx.dataset, 'Bad open receipt')
    xc.require(receipt['prereg_sha256'] == ctx.prereg_sha256, 'Open receipt names another prereg')
    arms = list(receipt['arms'])
    xc.require(arms == xc.gate_arms(receipt['status']), 'Open receipt arms differ from its status')
    spec = ctx.series('holdout')
    anchor = spec['eval']
    fits = load_fits(ctx, 'holdout', [a for a in xc.ARMS if a in arms])
    scores = {}
    for key, (directory, report) in fits.items():
        name = rel(directory/report['eval']['scores_file'])
        xc.require(receipt['score_files'].get(name) == report['eval']['scores_sha256'],
                   f'Score file {name} is not the one hashed in the open receipt')
        report_name = rel(directory/REPORT_FILE)
        xc.require(receipt['fit_reports'].get(report_name) == xc.sha256_file(directory/REPORT_FILE),
                   f'Fit report {report_name} is not the one hashed in the open receipt')
        scores[key] = read_scores(directory, report)
    identity = check_pairing(fits) if fits else None
    if scores:
        import numpy as np
        first = next(iter(scores.values()))
        for frame in scores.values():
            xc.require(np.array_equal(frame['user_id'].to_numpy(), first['user_id'].to_numpy()) and
                       np.array_equal(frame['item_id'].to_numpy(), first['item_id'].to_numpy()),
                       'Holdout score rows differ between fits')
    path = ctx.collection(spec['eval_role'], anchor)
    manifest_sha = xc.sha256_file(path/xc.MANIFEST_FILE)
    for _, report in fits.values():
        xc.require(report['eval']['manifest_sha256'] == manifest_sha, 'Fits scored another holdout collection')
    output = xc.new_output(xc.output_dir(ctx.dataset, 'holdout', stamp()))
    labels, targets = holdout(path)
    values = {key: evaluate(ctx, frame, targets, labels) for key, frame in scores.items()}
    pop = pop_metric(ctx, anchor, targets, labels)
    result = dict(format=RESULT_FORMAT, dataset=ctx.dataset, anchor=anchor, collection=path.name,
                  open_receipt_sha256=xc.sha256_file(receipt_path), prereg_sha256=ctx.prereg_sha256, arms=arms,
                  identity_digest=identity, queries=len(pop), reruns_superseded=reruns,
                  metrics=dict({f'{a}{s}': mean(v) for (a, s), v in values.items()}, Pop=mean(pop)))
    if all(a in arms for a in xc.ARMS):
        result.update(readings(values, ctx.dataset))
    else:
        result['verdict_transfer'] = result['verdict_content'] = xc.NOT_COMPUTED
    result.update(code=ctx.code, created_utc=xc.utc_now())
    result = normalized(result)
    xc.atomic_json(output/'result.json', result)
    xc.atomic_json(result_path, result)
    return dict(output=rel(output/'result.json'), receipt=rel(result_path), metrics=result['metrics'],
                verdict_transfer=result['verdict_transfer'], verdict_content=result['verdict_content'])


# ---------------------------------------------------------------- score, reading, prereg

def score(ctx):
    """Gate 2 first; the Kaggle files are assembled only when it passes, otherwise exit 1."""
    spec = ctx.series('final')
    gate = run_gate(ctx, 2)
    xc.require(gate['gate_ok'], f"Gate 2 failed {gate['status']}; nothing assembled; see {gate['output']}")
    fits = load_fits(ctx, 'final', spec['arms'])
    check_pairing(fits)
    files = {}
    for (arm, seed), (directory, report) in fits.items():
        output = xc.new_output(xc.output_dir(ctx.dataset, 'kaggle', f'{arm}{seed}'))/f'{arm}{seed}.csv'
        receipt = ctx.adapter.assemble(read_scores(directory, report), output)
        files[f'{arm}{seed}'] = dict(output=rel(output), receipt=normalized(receipt))
    return dict(files=files, gate=gate)


def reading(ctx, private):
    text = str(private)
    data = json.loads(text) if text.lstrip().startswith('{') else xc.read_json(text)
    scores = {k: float(v) for k, v in data.items()}
    ba = [scores[f'BA{s}'] for s in xc.SEEDS if f'BA{s}' in scores]
    b = [scores[f'B{s}'] for s in xc.SEEDS if f'B{s}' in scores]
    result = dict(format=READING_FORMAT, dataset=ctx.dataset, private=scores, reading=xc.kaggle_reading(ba, b),
                  descriptive=True, created_utc=xc.utc_now())
    output = xc.new_output(xc.output_dir(ctx.dataset, 'kaggle', f'reading-{stamp()}'))
    xc.atomic_json(output/'reading.json', result)
    return dict(output=rel(output/'reading.json'), reading=result['reading'])


def current_prompt_digest(dataset):
    """Digest of the prompt template and PROMPT_CONSTANTS, as xfer_agent records it in the set."""
    agent = importlib.import_module('scripts.xfer_agent')
    xc.require(hasattr(agent, 'prompt_digest'), 'xfer_agent.prompt_digest(dataset) is required for prereg')
    return agent.prompt_digest(dataset)


def prereg(dataset):
    path = xc.config_path(dataset, 'prereg')
    xc.require(not path.exists(), f'{path.name} already exists')
    collections = xc.output_dir(dataset, 'collections')
    holdouts = sorted(p.name for p in collections.glob('holdout-*')) if collections.exists() else []
    xc.require(not holdouts, f'Holdout collections exist before prereg: {holdouts}')
    fits = xc.output_dir(dataset, 'fits')
    agent_fits = sorted(rel(p) for p in fits.glob('*/BA*')) if fits.exists() else []
    xc.require(not agent_fits, f'BA/BApl fits exist before prereg: {agent_fits}')
    for doc in (CONTRACT_DOC, DATASET_DOCS[dataset]):
        xc.require(xc.committed_clean(xc.ROOT/doc), f'{doc} must be committed clean')
    base_path, set_path = xc.config_path(dataset, 'base'), xc.config_path(dataset, 'set')
    xc.require(xc.committed_clean(base_path) and xc.committed_clean(set_path), 'base.json and the set must be committed')
    base = xc.read_base(base_path)
    xc.require(base['dataset'] == dataset, 'Base of another dataset')
    agent_set = xc.read_json(set_path)
    xc.require('prompt_digest' in agent_set, 'The set carries no prompt_digest')
    xc.require(current_prompt_digest(dataset) == agent_set['prompt_digest'],
               'Prompt template or PROMPT_CONSTANTS differ from the set')
    code = xc.code_identity(dataset)
    set_code = agent_set.get('code') or {}
    changed = sorted(k for k in set(code) | set(set_code) if code.get(k) != set_code.get(k))
    anchors = xc.adapter(dataset).anchors()
    record = dict(format=PREREG_FORMAT, dataset=dataset, base_sha256=xc.sha256_file(base_path),
                  set_sha256=xc.sha256_file(set_path), base_digest=base['digest'],
                  contract=dict(path=CONTRACT_DOC, sha256=xc.sha256_file(xc.ROOT/CONTRACT_DOC)),
                  dataset_doc=dict(path=DATASET_DOCS[dataset], sha256=xc.sha256_file(xc.ROOT/DATASET_DOCS[dataset])),
                  code=code, code_changed_since_set=changed, prompt_digest=agent_set['prompt_digest'],
                  arms=dict(models=list(xc.ARMS), pop=xc.POP, series={k: v.get('arms') for k, v in anchors['series'].items()}),
                  seeds=list(xc.SEEDS), sample_seed=xc.SAMPLE_SEED, anchors=normalized(anchors), N=anchors['N'],
                  K=anchors['K'], recipe=normalized(xc.RECIPE), prediction_type=xc.PREDICTION_TYPE,
                  threads=dict(xc.THREADS, model_duckdb=DUCKDB_THREADS), kaggle_chunk=xc.KAGGLE_CHUNK[dataset],
                  kaggle_chunk_order='ascending user_id over the kaggle frame users',
                  permutation=PERMUTATION_RULE, bootstrap=dict(draws=xc.BOOTSTRAP_DRAWS, seed=xc.BOOTSTRAP_SEED),
                  reading=READING_RULE, gate=GATE_RULE, created_utc=xc.utc_now())
    xc.atomic_json(path, normalized(record))
    return dict(output=rel(path), code_changed_since_set=changed)


# ---------------------------------------------------------------- CLI

def parser():
    p = Parser(prog='xfer_model.py', description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='command', required=True)

    def command(name):
        c = sub.add_parser(name)
        c.add_argument('--dataset', choices=xc.DATASETS, required=True)
        return c
    c = command('fit')
    c.add_argument('--series', choices=('dev', 'holdout', 'final'))
    c.add_argument('--arm', choices=xc.ARMS)
    c.add_argument('--seed', type=int)
    c.add_argument('--base-dev', action='store_true')
    c.add_argument('--base')
    c.add_argument('--output')
    c.add_argument('--collections')
    command('contrast')
    c = command('gate')
    c.add_argument('--stage', type=int, choices=(1, 2), required=True)
    c.add_argument('--leakcheck')
    c = command('holdout-open')
    c.add_argument('--gate', required=True)
    c.add_argument('--quote', required=True)
    command('holdout')
    command('score')
    c = command('reading')
    c.add_argument('--private', required=True)
    command('prereg')
    return p


def cmd_fit(args):
    if args.base_dev:
        xc.require(args.base and args.output, 'Base-dev needs --base and --output')
        xc.require(args.series in (None, 'dev') and args.arm in (None, 'B') and args.seed in (None, BASE_DEV_SEED),
                   'Base-dev is arm B, series dev, seed 2026')
        ctx = Context(args.dataset, base_dev=True, base=xc.read_json(args.base), collections=args.collections)
        output = Path(args.output)
        if not output.is_absolute():
            output = xc.output_dir(args.dataset, 'base-dev', args.output)
        report = fit(ctx, 'dev', 'B', BASE_DEV_SEED, output)
        return summary(report, output)
    xc.require(args.series and args.arm and args.seed is not None, 'fit needs --series, --arm and --seed')
    xc.require(not args.base and not args.collections and not args.output, 'Only base-dev takes --base/--output/--collections')
    ctx = Context(args.dataset)
    output = fit_dir(args.dataset, args.series, args.arm, args.seed)
    moved = clear_failed(output)
    return summary(fit(ctx, args.series, args.arm, args.seed, output), output, moved)


COMMANDS = {
    'fit': cmd_fit,
    'contrast': lambda a: contrast(Context(a.dataset)),
    'gate': lambda a: run_gate(Context(a.dataset), a.stage, a.leakcheck),
    'holdout-open': lambda a: holdout_open(Context(a.dataset), a.gate, a.quote),
    'holdout': lambda a: holdout_command(Context(a.dataset)),
    'score': lambda a: score(Context(a.dataset)),
    'reading': lambda a: reading(Context(a.dataset), a.private),
    'prereg': lambda a: prereg(a.dataset),
}


def handle(argv=None):
    xc.isolated()
    args = parser().parse_args(argv)
    with quiet_stdout():
        return dict(command=args.command, dataset=args.dataset, **COMMANDS[args.command](args))


def main(argv=None):
    return xc.run_cli(handle, argv)


if __name__ == '__main__':
    raise SystemExit(main())
