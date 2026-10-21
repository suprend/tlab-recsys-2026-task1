"""Tinkoff adapter (dataset T) of the agent-transfer experiment.

Contract: docs/xfer-design.md (common) and docs/xfer-tinkoff-design.md; the
interface is the docstring of scripts/xfer_common.py. Time is the integer step
``t``; the history of an anchor A is every interaction with ``t < A``, the target
window is ``[A, A+30)``. Events are read only through ``history`` (adapter code),
``views`` (agent) and ``load`` (writing them); paths come from
``xfer_common.events_path``. Holdout labels go only through the seal writer of xfer_common.

Run as ``python -I scripts/xfer_tinkoff.py load|collect ...``; stdout carries one
JSON line, exit 0/1. Without ``-I`` the CLI refuses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import xfer_common as xc  # noqa: E402

DATASET = 'tinkoff'
W = 30
N = 5000
K = 20
TRAIN = (461, 491, 521, 551, 581, 611)
VAL = 641
HOLDOUT = 671
KAGGLE = 701
PROBE = 641
PROBE_USERS = 3000
BUCKET_ORIGIN = 11
BUCKET_STEP = 30
LEVELS = {'pair': ('user_id', 'item_id'), 'user': ('user_id',), 'item': ('item_id',)}
KEYS = ('user_id', 'item_id')
EV_SCHEMA = (('user_id', 'BIGINT'), ('item_id', 'BIGINT'), ('t', 'INTEGER'))
BATCH_SCHEMA = {'cand': (('user_id', 'BIGINT'), ('item_id', 'BIGINT')), 'users': (('user_id', 'BIGINT'),)}
EV_VIEW = 'ev'
SOURCE_PREFIX = 'src_'
LOAD_FORMAT = 'xfer-tinkoff-load-v1'
ASSEMBLE_FORMAT = 'xfer-tinkoff-assemble-v1'
RECEIPT = 'kaggle-verify.json'
TRAIN_CSV = 'data_train.csv'
TEST_CSV = 'test_users.csv'
BASELINE_CSV = 'baseline.csv'
CSV_FILES = (TRAIN_CSV, TEST_CSV, BASELINE_CSV)
TRAIN_HEADER = 'user_id,item_id,timestamp'
TEST_HEADER = 'user_id'
LOAD_REPORT = 'load.json'
PART_FILE = 'part-0.parquet'
# Schema facts of section 0, checked by load (counters only, never prompt material).
LOAD_FACTS = dict(rows=2801844, pairs=2801844, users=11047, items=3178, t_min=0, t_max=700, test_users=6688)
MAX_THREADS = 4
BATCH_USERS = 128
POP_WINDOW = 30
FLOAT_KINDS = ('trend', 'pop_share', 'user_rate', 'cooc_score', 'cooc_max', 'cooc_last', 'cooc_wsum', 'cooc_mean')
RECENT_ITEMS = 5
WSUM_DECAY = 0.8
SUBMISSION_HEADER = 'user_id,item_id'
# Probe time of the agent set (H&M budget with the T levels): pair+user together, item separately.
BUDGET = {'pair_user_seconds': 90.0, 'item_seconds': 180.0}

PROMPT_CONSTANTS = dict(k=K, w=W, n=N, iterations=xc.RECIPE['iterations'], depth=xc.RECIPE['depth'],
                        learning_rate=xc.RECIPE['learning_rate'], l2_leaf_reg=xc.RECIPE['l2_leaf_reg'],
                        border_count=xc.RECIPE['border_count'], rounds=6, proposals=5)

WARNING = ('All valid columns will enter the model without selection. Superfluous and noisy columns hurt: '
           'a few strong, non-redundant signals are needed. User-level columns work only through interactions.')

# The whole English prompt: dataset task plus the H&M sandbox rules with their numbers. Slots are
# str.format fields filled by prompt_substitutions(); literal braces are doubled.
PROMPT_TEMPLATE = """You are a feature engineer for a ranking model. Reply with JSON only.

TASK
An online store. The data are interactions (user, item, time step): time is an integer step of unknown unit,
and every (user, item) pair occurs at most once. For an anchor A the history is every interaction with t < A.
The label of a (user, item) pair is whether the user interacts with the item in [A, A+{w}); the task is to
recommend {k} items the user has not interacted with before A. The metric is binary NDCG@{k} over the users
with at least one new item in that window.

CANDIDATES
{candidates}

TRAINING
CatBoost Logloss, {iterations} trees, depth {depth}, learning rate {learning_rate}, L2 {l2_leaf_reg}, {border_count}
borders. Anchors every {w} steps with up to {n} users each; every candidate of a user enters with weight 1.

FEATURES ALREADY IN THE MODEL: base B (name [level]: formula; missing). A window of w steps is [A-w, A);
j is the candidate item, u the user.
{features}

TABLES (DuckDB; a query sees only these three)
{tables}

QUERY RULES
- Exactly one SELECT or WITH statement; ';' only at the very end; no comments (-- or /* */).
- Write the anchor only as {{A}}, literally with the braces; it becomes the integer anchor step,
  e.g. t >= {{A}} - 30. No other {{...}} placeholders.
- The column t always stands on the left of a comparison: t >= {{A}} - 30, never {{A}} - 30 <= t. Never compare
  t with a number (t < 400 is an error); write ages as {{A}} - t.
- Forbidden whole words, in any case: transactions, customers, frame, label, labels, target, targets, hm_*,
  _hm_*; read_*, parquet_*, csv, json*, glob, getenv, query, query_table, duckdb_*, information_schema,
  pg_catalog, sqlite_master, pragma*; attach, detach, copy, export, import, install, load, set, reset, use,
  call, create, drop, insert, update, delete, alter; random, setseed, uuid, gen_random_uuid, now, today,
  current_date, current_time, current_timestamp, get_current_time, sample, tablesample, current_setting,
  sniff_*, checkpoint, force_checkpoint, which_secret; ev_* and the names of the raw data; the functions
  error() and strptime().
- An item-level query must not mention cand or users: its values do not depend on the batch and are cached.

OUTPUT OF A QUERY
- level "pair": key columns user_id, item_id (pairs of cand); level "user": user_id (of users); level "item":
  item_id (of the items in ev). Keys are BIGINT, never NULL and unique. A key outside its set is an error, not
  a silent filter, so keep queries narrow.
- 1 to 3 value columns named by ^ag_[a-z][a-z0-9_]{{1,38}}$, unique among the accepted columns and different
  from every feature name above; integer, DECIMAL, FLOAT, DOUBLE or BOOLEAN. VARCHAR, DATE and TIMESTAMP values
  are errors. No other columns.
- Values are cast to DOUBLE and left-joined to the batch keys of the level. No row, NULL, a non-finite value or
  a float32 overflow mean "no data": NaN in the model, which CatBoost treats as the minimum. Put your own
  defaults with COALESCE.
- Batch invariance: a value depends only on ev and its own key; cand and users only filter. A window
  PARTITION BY user_id over cand is allowed (all candidates of a user are always in one batch); aggregates
  over cand across users are not. Windows need a full tie-break (..., item_id). Violations are caught
  mechanically.
- Limits on the probe: timeout 20 s for pair and user queries, 60 s for item queries; at most 20 million
  output rows. Budget of the whole set on the probe: valid pair and user proposals together at most 90 s,
  valid item proposals at most 180 s; a proposal that does not fit into what is left gets status budget.

VALIDITY
A proposal is accepted or rejected as a whole. It is invalid on an SQL error, a broken rule or a timeout; when
a column has fewer than 2 distinct non-NULL values or fewer than 100 non-NULL rows; when a column has
|Spearman rho| >= 0.999 with a base column, an accepted column or another column of the same proposal; or when
batch invariance fails.

PROBE STATISTICS (history before the probe anchor only)
{stats}

WARNING
""" + WARNING + """

EARLIER ATTEMPTS IN THIS RUN (validity and coverage on the probe; effects on labels are not shown)
{history}
Probe time budget left (rounded down to 10 s): pair+user about {budget_pair_user} s of 90 s; item about
{budget_item} s of 180 s.

REQUEST
This is round {round} of {rounds}. Propose {proposals} new features that are likely to improve the ranking
beyond base B and the accepted columns and that differ from earlier attempts. Answer with a JSON list only:
[{{"name": "short_snake_case", "idea": "one sentence", "level": "pair|user|item", "sql": "SELECT ..."}}]
"""

# check_sql additions of section 6.2 (dataset time rules); the agent's own layer holds the H&M list.
T_RIGHT = re.compile(r'(<=|>=|<>|!=|<|>|=)\s*t\b', re.I)
T_LITERAL = re.compile(r'\bt\s*(<=|>=|<>|!=|<|>|=)\s*-?\d', re.I)
FORBIDDEN_WORDS = ('data_train', 'test_users', 'baseline', r'ev_\w+')
FORBIDDEN = re.compile(r'\b(' + '|'.join(FORBIDDEN_WORDS) + r')\b', re.I)
BATCH_WORDS = re.compile(r'\b(cand|users)\b', re.I)
PLACEHOLDER = '{A}'
SOURCE_NAME = re.compile(r'[a-z][a-z0-9]{0,15}')
WINDOW_NAME = re.compile(r'(users|n_items)_([0-9]+)')
WINDOW_FEATURE = re.compile(r'(pop_share|item_new)_([0-9]+)')


# ---------------------------------------------------------------- small helpers

def _duckdb():
    import duckdb
    return duckdb


def _np():
    import numpy as np
    return np


def _pd():
    import pandas as pd
    return pd


def _step(value, name='anchor'):
    np = _np()
    xc.require(not isinstance(value, bool) and isinstance(value, (int, np.integer)), f'{name} must be an integer step')
    return int(value)


def _threads(value):
    xc.require(type(value) is int and 1 <= value <= MAX_THREADS, f'DuckDB threads must be 1..{MAX_THREADS}')
    return value


def _literal(text):
    return "'" + str(text).replace("'", "''") + "'"


def _connect(threads, database=':memory:', read_only=False):
    con = _duckdb().connect(str(database), read_only=read_only, config=dict(threads=_threads(threads)))
    con.execute('SET enable_progress_bar = false')
    return con


def bucket_start(t):
    """Partition key of step t: 0 for t < 11, else 11 + 30*floor((t-11)/30)."""
    t = _step(t, 't')
    xc.require(t >= 0, 'Steps are non-negative')
    return 0 if t < BUCKET_ORIGIN else BUCKET_ORIGIN + BUCKET_STEP*((t-BUCKET_ORIGIN)//BUCKET_STEP)


def bucket_end(start):
    return BUCKET_ORIGIN if start == 0 else start + BUCKET_STEP


def is_boundary(anchor):
    anchor = _step(anchor)
    return anchor == 0 or (anchor >= BUCKET_ORIGIN and (anchor-BUCKET_ORIGIN) % BUCKET_STEP == 0)


def _frame_input(value, columns):
    pd = _pd()
    frame = xc.read_parquet(value) if isinstance(value, (str, Path)) else value
    xc.require(isinstance(frame, pd.DataFrame), 'A DataFrame or a parquet path is required')
    missing = [c for c in columns if c not in frame.columns]
    xc.require(not missing, f'Missing columns {missing}')
    return frame


def content_digest(source, order_by='user_id, item_id'):
    """Digest of the content (schema and row values in key order) of a parquet file or DataFrame."""
    np = _np()
    con = _connect(1)
    try:
        if isinstance(source, (str, Path)):
            relation = f'read_parquet({_literal(source)})'
        else:
            con.register('digest_source', source)
            relation = 'digest_source'
        schema = [[row[0], row[1]] for row in con.execute(f'DESCRIBE SELECT * FROM {relation}').fetchall()]
        data = con.execute(f'SELECT * FROM {relation} ORDER BY {order_by}').fetchnumpy()
    finally:
        con.close()
    digest = hashlib.sha256(json.dumps(schema).encode('utf-8'))
    for name, _ in schema:
        column = data[name]
        mask = np.ma.getmaskarray(column)
        values = np.ma.filled(column, 0) if np.ma.isMaskedArray(column) else np.asarray(column)
        digest.update(np.ascontiguousarray(mask).tobytes())
        digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


# ---------------------------------------------------------------- anchors

def _check_windows(roles, series, w):
    """Windows of the roles and series must not overlap; every anchor is a bucket boundary."""
    for role, values in roles.items():
        for anchor in values:
            xc.require(is_boundary(anchor), f'{role} anchor {anchor} is not a bucket boundary')
    train = sorted(roles['train'])
    for left, right in zip(train, train[1:]):
        xc.require(left + w <= right, f'Train windows overlap: {left} + {w} > {right}')
    for anchor in train:
        xc.require(anchor + w <= min(roles['val']), f'Train window {anchor} overlaps val')
    xc.require(max(roles['val']) + w <= min(roles['holdout']), 'Val window overlaps holdout')
    xc.require(max(roles['holdout']) + w <= min(roles['kaggle']), 'Holdout window overlaps the kaggle anchor')
    for name, spec in series.items():
        anchors = [source['anchor'] for source in spec['sources']]
        xc.require(anchors == spec['train'], f'Series {name}: sources differ from train anchors')
        xc.require(len(set(anchors)) == len(anchors), f'Series {name}: repeated train anchor')
        for anchor in anchors:
            xc.require(anchor + w <= spec['eval'], f'Series {name}: window of {anchor} reaches eval {spec["eval"]}')


def anchors():
    """W, N, K, roles, series (train anchors with source collection and cap N, eval anchor), holdout, probe."""
    roles = dict(train=list(TRAIN), val=[VAL], holdout=[HOLDOUT], kaggle=[KAGGLE], probe=[PROBE])
    arms = [xc.POP, *xc.ARMS]

    def sources(pairs):
        return [dict(anchor=a, role=r, cap=N) for a, r in pairs]
    series = dict(
        dev=dict(train=list(TRAIN), sources=sources((a, 'train') for a in TRAIN), eval=VAL, eval_role='val',
                 population='all queries', arms=arms, after_holdout=False),
        holdout=dict(train=[*TRAIN, VAL], sources=sources([*((a, 'train') for a in TRAIN), (VAL, 'val')]),
                     eval=HOLDOUT, eval_role='holdout', population='all queries', arms=arms, after_holdout=False),
        final=dict(train=[*TRAIN[2:], VAL, HOLDOUT],
                   sources=sources([*((a, 'train') for a in TRAIN[2:]), (VAL, 'val'), (HOLDOUT, 'holdout')]),
                   eval=KAGGLE, eval_role='kaggle', population='test users', arms=['B', 'BA'], after_holdout=True))
    _check_windows(roles, series, W)
    return dict(W=W, N=N, K=K, roles=roles, series=series, holdout=HOLDOUT, probe=PROBE, probe_users=PROBE_USERS,
                kaggle_chunk=xc.KAGGLE_CHUNK[DATASET])


# ---------------------------------------------------------------- base: candidates and features

def initial_base():
    """The initial base of sections 3-4: candidate policy and 17 numeric features, no categorical."""
    candidates = dict(total=200, sources=[
        dict(name='pop30', kind='pop', window=30, depth=100),
        dict(name='cooc', kind='cooc', window=180, last=20, depth=100, decimals=9),
        dict(name='fill', kind='pop', window=None, depth=None)])
    names = ('users_7', 'users_30', 'users_90', 'users_all', 'trend', 'item_age', 'item_last',
             'n_items_all', 'n_items_30', 'user_recency', 'user_age',
             'cooc_score', 'cooc_rank', 'cooc_max', 'cooc_hits', 'pop30_rank', 'global_rank')
    sources = _policy(candidates)
    features = [{k: v for k, v in feature_definition(name, sources).items() if k in ('name', 'formula', 'missing')}
                for name in names]
    return xc.make_base(DATASET, candidates, features, [])


def _positive(value, name, optional=False):
    if optional and value is None:
        return None
    xc.require(type(value) is int and value > 0, f'{name} must be a positive integer')
    return value


def _policy(candidates):
    """Validated candidate policy: list of source dicts in union order."""
    xc.require(isinstance(candidates, dict) and set(candidates) == {'total', 'sources'},
               'Candidates need exactly total and sources')
    _positive(candidates['total'], 'total')
    xc.require(candidates['total'] >= K, f'total must be at least {K}')
    sources = candidates['sources']
    xc.require(isinstance(sources, list) and sources, 'At least one candidate source')
    seen = set()
    for source in sources:
        xc.require(isinstance(source, dict), 'A source is an object')
        name, kind = source.get('name'), source.get('kind')
        xc.require(isinstance(name, str) and SOURCE_NAME.fullmatch(name) and name not in seen,
                   f'Bad or repeated source name {name!r}')
        seen.add(name)
        if kind == 'pop':
            xc.require(set(source) == {'name', 'kind', 'window', 'depth'}, f'pop source {name}: name/kind/window/depth')
            _positive(source['window'], f'{name}.window', optional=True)
        elif kind == 'cooc':
            xc.require(set(source) == {'name', 'kind', 'window', 'last', 'depth', 'decimals'},
                       f'cooc source {name}: name/kind/window/last/depth/decimals')
            _positive(source['window'], f'{name}.window')
            _positive(source['last'], f'{name}.last')
            _positive(source['decimals'], f'{name}.decimals')
        else:
            raise xc.ContractError(f'Unknown source kind {kind!r}')
        _positive(source['depth'], f'{name}.depth', optional=True)
    first = sources[0]
    # Pop (section 5) is the first K unseen items by users_30: a first pop source over window 30
    # reaching depth >= K inside total >= K keeps Pop inside the candidates of every base.
    xc.require(first['kind'] == 'pop' and first['window'] == POP_WINDOW and
               (first['depth'] is None or first['depth'] >= K),
               f'The first source must be pop with window {POP_WINDOW} and depth >= {K} (Pop inside the candidates)')
    return sources


def feature_definition(name, sources):
    """Registry entry (name, formula, missing, level, kind, params) of a base feature name; error if unknown."""
    by_name = {s['name']: s for s in sources}

    def entry(level, kind, formula, missing, **params):
        return dict(name=name, formula=formula, missing=missing, level=level, kind=kind, params=params)
    if name == 'users_all':
        return entry('item', 'users', 'distinct users with an event on item j before A', 'never: j has an event before A',
                     window=None)
    match = WINDOW_NAME.fullmatch(name)
    if match and match.group(1) == 'users' and int(match.group(2)) > 0 and str(int(match.group(2))) == match.group(2):
        w = int(match.group(2))
        return entry('item', 'users', f'distinct users with an event on item j in [A-{w}, A)', '0', window=w)
    if name == 'trend':
        return entry('item', 'trend', 'users_7 / users_30', 'NULL when users_30 = 0')
    if name == 'item_age':
        return entry('item', 'item_age', 'A - first time step of item j before A', 'never')
    if name == 'item_last':
        return entry('item', 'item_last', 'A - last time step of item j before A', 'never')
    if name == 'n_items_all':
        return entry('user', 'n_items', 'distinct items of user u before A', 'never: a query has history', window=None)
    if match and match.group(1) == 'n_items' and int(match.group(2)) > 0 and str(int(match.group(2))) == match.group(2):
        w = int(match.group(2))
        return entry('user', 'n_items', f'distinct items of user u in [A-{w}, A)', '0', window=w)
    if name == 'user_recency':
        return entry('user', 'user_recency', 'A - last time step of user u before A', 'never')
    if name == 'user_age':
        return entry('user', 'user_age', 'A - first time step of user u before A', 'never')
    if name == 'user_rate':
        return entry('user', 'user_rate', 'n_items_all / max(user_age, 1)', 'never')
    match = WINDOW_FEATURE.fullmatch(name)
    if match and str(int(match.group(2))) == match.group(2) and int(match.group(2)) > 0:
        w = int(match.group(2))
        if match.group(1) == 'pop_share':
            return entry('item', 'pop_share', f'users_{w} / users_all', 'never: users_all >= 1', window=w)
        return entry('item', 'item_new', f'distinct users with an event on item j whose first event on any item '
                     f'is in [A-{w}, A)', '0', window=w)
    if name == 'global_rank':
        return entry('pair', 'global_rank', 'rank of j among the items with an event before A by users_all '
                     'descending, then item_id; the same for every user', 'never')
    head, _, tail = name.partition('_')
    source = by_name.get(head)
    if source is not None and tail == 'rank':
        return entry('pair', 'rank', f'position of j in candidate source {head}', f'NULL outside source {head}',
                     source=head)
    if source is None or source['kind'] != 'cooc':
        raise xc.ContractError(f'Unknown base feature {name!r}')
    of = f'L(u) of source {head}'
    if tail in ('score', 'max', 'hits'):
        text = dict(score=f'sum of sim(i, j) over i in {of}, rounded to {source["decimals"]} decimals',
                    max=f'max of sim(i, j) over i in {of}',
                    hits=f'number of i in {of} with sim(i, j) > 0')[tail]
        return entry('pair', f'cooc_{tail}', text, '0', source=head)
    if tail == 'wsum':
        return entry('pair', 'cooc_wsum', f'sum over positions p = 1..|L(u)| of {of} (p = 1 most recent) of '
                     f'{WSUM_DECAY}^(p-1) * sim(L_p, j)', '0', source=head, decay=WSUM_DECAY)
    if tail == 'mean':
        return entry('pair', 'cooc_mean', f'sum of sim(i, j) over i in {of}, rounded to {source["decimals"]} '
                     f'decimals, divided by the number of i in {of} with n(i) > 0',
                     f'NULL when no i in {of} has n(i) > 0', source=head)
    if tail == 'n_last':
        xc.require(RECENT_ITEMS <= source['last'], f'{name} needs {head}.last >= {RECENT_ITEMS}')
        return entry('pair', 'cooc_n_last', f'number of i among the {RECENT_ITEMS} most recent items of {of} with '
                     'sim(i, j) > 0', '0', source=head, m=RECENT_ITEMS)
    match = re.fullmatch(r'last([0-9]+)', tail)
    if match and str(int(match.group(1))) == match.group(1) and 1 <= int(match.group(1)) <= source['last']:
        m = int(match.group(1))
        return entry('pair', 'cooc_last', f'sum of sim(i, j) over the {m} most recent items of {of}', '0',
                     source=head, m=m)
    raise xc.ContractError(f'Unknown base feature {name!r}')


def _spec(base):
    """Checked base: candidate sources and feature definitions whose text equals the code's."""
    base = xc.check_base(base, DATASET)
    sources = _policy(base['candidates'])
    xc.require(base['categorical'] == [], 'T has no categorical features')
    features = []
    for feature in base['features']:
        definition = feature_definition(feature['name'], sources)
        xc.require(feature['formula'] == definition['formula'] and feature['missing'] == definition['missing'],
                   f'Base feature {feature["name"]}: formula or missing differs from the code')
        xc.require(not feature['name'].startswith(SOURCE_PREFIX), 'Base names may not start with src_')
        features.append(definition)
    return dict(total=base['candidates']['total'], sources=sources, features=features)


def source_columns(base):
    """Frame columns of the candidate sources (src_<name>), in union order."""
    return [SOURCE_PREFIX + s['name'] for s in _policy(base['candidates'])]


def coverage_sources(base=None):
    """Source-rank columns behind the coverage fields: recent = cooc sources, global = popularity sources."""
    if base is None:
        path = xc.config_path(DATASET, 'base')
        base = xc.read_base(path) if path.exists() else initial_base()
    sources = _policy(xc.check_base(base, DATASET)['candidates'])
    return {'recent': [SOURCE_PREFIX + s['name'] for s in sources if s['kind'] == 'cooc'],
            'global': [SOURCE_PREFIX + s['name'] for s in sources if s['kind'] == 'pop']}


# ---------------------------------------------------------------- load

def _csv_header(path):
    with Path(path).open('r', encoding='utf-8', newline='') as stream:
        return stream.readline().rstrip('\r\n')


def load(raw, output):
    """Raw CSV -> events DB, bucket partitions and the static DB under load/, then load.json."""
    raw, output = Path(raw), Path(output)
    paths = xc.events_path(DATASET)
    static = xc.static_path(DATASET)
    target = paths['db'].parent
    report_path = target/LOAD_REPORT
    xc.require(output.resolve() == target.resolve(), f'load writes only into {target}')
    xc.require(not any(p.exists() for p in (paths['db'], paths['parts'], static, report_path)),
               f'Load output already exists in {target}')
    code = xc.code_identity(DATASET)
    receipt_path = raw/RECEIPT
    receipt = xc.read_json(receipt_path)
    xc.require(receipt.get('status') == 'complete', 'The download receipt is not complete')
    listed = {entry['name']: entry for entry in receipt.get('files', [])}
    files = {}
    for name in CSV_FILES:
        entry = listed.get(name)
        xc.require(entry is not None, f'{name} is not in the receipt')
        path = raw/name
        size, sha = path.stat().st_size, xc.sha256_file(path)
        xc.require(size == entry['size'] and sha == entry['sha256'], f'{name} differs from the receipt')
        files[name] = dict(bytes=size, sha256=sha)
    xc.require(_csv_header(raw/TRAIN_CSV) == TRAIN_HEADER, f'{TRAIN_CSV} header must be {TRAIN_HEADER}')
    xc.require(_csv_header(raw/TEST_CSV) == TEST_HEADER, f'{TEST_CSV} header must be {TEST_HEADER}')
    target.mkdir(parents=True, exist_ok=True)
    tmp = target/f'.load-tmp-{os.getpid()}'
    tmp.mkdir()
    try:
        db, parts, static_tmp = tmp/xc.EVENTS_DB, tmp/xc.EVENTS_DIR, tmp/xc.STATIC_DB
        con = _connect(MAX_THREADS, db)
        try:
            con.execute(f'''CREATE TABLE events AS SELECT user_id, item_id, CAST("timestamp" AS INTEGER) AS t
                FROM read_csv({_literal(raw/TRAIN_CSV)}, header=true, delim=',', auto_detect=false,
                     columns={{'user_id': 'BIGINT', 'item_id': 'BIGINT', 'timestamp': 'BIGINT'}})
                ORDER BY t, user_id, item_id''')
            rows, users, items, t_min, t_max, nulls = con.execute('''SELECT count(*), count(DISTINCT user_id),
                count(DISTINCT item_id), min(t), max(t),
                count(*) FILTER (WHERE user_id IS NULL OR item_id IS NULL OR t IS NULL) FROM events''').fetchone()
            pairs = con.execute('SELECT count(*) FROM (SELECT DISTINCT user_id, item_id FROM events)').fetchone()[0]
            xc.require(nulls == 0 and rows > 0, 'Events need non-NULL user_id, item_id and t')
            parts.mkdir()
            partitions = []
            for start in range(0, bucket_start(t_max)+1):
                if start != bucket_start(start):
                    continue
                directory = parts/f'b={start}'
                directory.mkdir()
                file = directory/PART_FILE
                con.execute(f'''COPY (SELECT user_id, item_id, t FROM events WHERE t >= {start} AND t < {bucket_end(start)}
                    ORDER BY t, user_id, item_id) TO {_literal(file)} (FORMAT parquet)''')
                count = con.execute(f'SELECT count(*) FROM events WHERE t >= {start} AND t < {bucket_end(start)}'
                                    ).fetchone()[0]
                partitions.append(dict(bucket=start, end=bucket_end(start), rows=int(count),
                                       file=f'b={start}/{PART_FILE}'))
            xc.require(sum(p['rows'] for p in partitions) == rows, 'Partitions lose rows')
            con.execute('CHECKPOINT')
        finally:
            con.close()
        scon = _connect(MAX_THREADS, static_tmp)
        try:
            scon.execute(f'''CREATE TABLE test_users AS SELECT user_id FROM read_csv({_literal(raw/TEST_CSV)},
                header=true, delim=',', auto_detect=false, columns={{'user_id': 'BIGINT'}}) ORDER BY user_id''')
            scon.execute(f'ATTACH {_literal(db)} AS src (READ_ONLY)')
            test_rows, test_distinct, test_nulls, test_missing = scon.execute('''SELECT count(*),
                count(DISTINCT user_id), count(*) FILTER (WHERE user_id IS NULL),
                (SELECT count(*) FROM test_users u WHERE NOT EXISTS
                    (SELECT 1 FROM src.events e WHERE e.user_id = u.user_id)) FROM test_users''').fetchone()
            scon.execute('DETACH src')
            scon.execute('CHECKPOINT')
        finally:
            scon.close()
        facts = dict(rows=int(rows), pairs=int(pairs), users=int(users), items=int(items), t_min=int(t_min),
                     t_max=int(t_max), test_users=int(test_rows))
        checks = dict(nulls=int(nulls), test_users_distinct=int(test_distinct), test_users_nulls=int(test_nulls),
                      test_users_without_events=int(test_missing))
        xc.require(facts == LOAD_FACTS, f'Schema facts differ: {facts} != {LOAD_FACTS}')
        xc.require(checks == dict(nulls=0, test_users_distinct=facts['test_users'], test_users_nulls=0,
                                  test_users_without_events=0), f'Schema checks failed: {checks}')
        os.replace(db, paths['db'])
        os.replace(parts, paths['parts'])
        os.replace(static_tmp, static)
        tmp.rmdir()
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    for partition in partitions:
        partition['sha256'] = xc.sha256_file(paths['parts']/partition['file'])
    body = dict(format=LOAD_FORMAT, dataset=DATASET, receipt_sha256=xc.sha256_file(receipt_path), files=files,
                events_db_sha256=xc.sha256_file(paths['db']), static_db_sha256=xc.sha256_file(static),
                partitions=partitions, facts=facts, checks=checks, code=code, created_utc=xc.utc_now())
    report = dict(body, digest=xc.canonical_digest(body))
    xc.atomic_json(report_path, report)
    return report


# ---------------------------------------------------------------- history and views

def history(before, purpose, threads=xc.THREADS['collect']):
    """In-memory DuckDB with table ``events(user_id, item_id, t)`` holding only ``t < before``.

    ``before > A_holdout`` needs ``holdout_window_open(dataset, purpose)``. The caller closes it.
    """
    before = _step(before, 'before')
    xc.require(isinstance(purpose, str) and purpose.strip(), 'A purpose is required')
    threads = _threads(threads)
    if before > HOLDOUT:
        xc.require_window(DATASET, purpose)
    database = xc.events_path(DATASET)['db']
    xc.require(database.exists(), 'Run load first')
    con = _connect(threads)
    try:
        con.execute(f'ATTACH {_literal(database)} AS src (READ_ONLY)')
        con.execute(f'CREATE TABLE events AS SELECT user_id, item_id, t FROM src.events WHERE t < {before}')
        con.execute('DETACH src')
    except BaseException:
        con.close()
        raise
    return con


def views(A, purpose):
    """Agent views at A: allowed partition files (buckets ending by A), ``ev`` filtered by t < A, schemas, levels."""
    A = _step(A)
    xc.require(is_boundary(A) and A >= BUCKET_ORIGIN, f'Anchor {A} is not a bucket boundary')
    xc.require(isinstance(purpose, str) and purpose.strip(), 'A purpose is required')
    if A > HOLDOUT:
        xc.require_window(DATASET, purpose)
    parts = xc.events_path(DATASET)['parts']
    xc.require(parts.is_dir(), 'Run load first')
    directories, files = [], []
    for directory in sorted(parts.iterdir()):
        match = re.fullmatch(r'b=([0-9]+)', directory.name)
        if not directory.is_dir() or not match:
            continue
        start = int(match.group(1))
        xc.require(bucket_start(start) == start, f'Partition {directory.name} is not a bucket start')
        if bucket_end(start) <= A:
            directories.append((start, directory))
    directories.sort()
    for _, directory in directories:
        files.extend(sorted(directory.glob('*.parquet')))
    xc.require(files, f'No partitions before {A}')
    listed = ', '.join(_literal(f) for f in files)
    columns = ', '.join(name for name, _ in EV_SCHEMA)
    ev = f'SELECT {columns} FROM read_parquet([{listed}], hive_partitioning=false) WHERE t < {A}'
    return dict(anchor=A, files=[str(f) for f in files], directories=[str(d) for _, d in directories],
                buckets=[s for s, _ in directories], views={EV_VIEW: ev},
                schema={EV_VIEW: [list(c) for c in EV_SCHEMA]},
                batch={name: [list(c) for c in cols] for name, cols in BATCH_SCHEMA.items()},
                levels={level: list(keys) for level, keys in LEVELS.items()},
                items=f'SELECT DISTINCT item_id FROM ({ev})')


# ---------------------------------------------------------------- check_sql additions

def check_sql(sql, level):
    """Dataset rules of 6.2: anchor only as {A}, t on the left and never against a number, set words, item rule."""
    if level not in LEVELS:
        raise ValueError('level must be pair, user or item')
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError('sql must be a non-empty string')
    rest = sql.replace(PLACEHOLDER, ' ')
    if '{' in rest or '}' in rest:
        raise ValueError('the anchor is written only as {A}; no other {...} is allowed')
    hit = T_RIGHT.search(sql)
    if hit:
        raise ValueError(f't must stand on the left of a comparison: {hit.group(0)!r}')
    hit = T_LITERAL.search(sql)
    if hit:
        raise ValueError(f't may not be compared with a number: {hit.group(0)!r}; write it relative to {{A}}')
    hit = FORBIDDEN.search(rest)
    if hit:
        raise ValueError(f'forbidden name: {hit.group(0)}')
    if level == 'item':
        hit = BATCH_WORDS.search(rest)
        if hit:
            raise ValueError(f'an item query must not use {hit.group(0)}: its values are cached per process')


def substitute(sql, A):
    """The SQL with {A} replaced by the decimal anchor step (after check_sql)."""
    return sql.replace(PLACEHOLDER, str(_step(A)))


def sql_rules():
    return dict(forbidden=list(FORBIDDEN_WORDS), forbidden_pattern=FORBIDDEN.pattern, check=check_sql,
                substitute=substitute, placeholder=PLACEHOLDER, levels=list(LEVELS),
                t_right=T_RIGHT.pattern, t_literal=T_LITERAL.pattern, item_forbidden=['cand', 'users'])


# ---------------------------------------------------------------- history arrays and candidates

class _Past:
    """Distinct (user, item) pairs before A with their first and last step, as numpy arrays."""

    def __init__(self, con, A):
        np = _np()
        self.A = A
        data = con.execute('''SELECT user_id, item_id, min(t) AS t0, max(t) AS t1 FROM events
            GROUP BY user_id, item_id ORDER BY user_id, t1 DESC, item_id''').fetchnumpy()
        user = np.asarray(data['user_id'], dtype=np.int64)
        item = np.asarray(data['item_id'], dtype=np.int64)
        self.t0 = np.asarray(data['t0'], dtype=np.int64)
        self.t1 = np.asarray(data['t1'], dtype=np.int64)
        xc.require(len(user) > 0, f'No history before {A}')
        self.items = np.unique(item)
        self.n_items = len(self.items)
        self.ii = np.searchsorted(self.items, item)
        self.uids, self.starts, self.counts = np.unique(user, return_index=True, return_counts=True)
        self.ui = np.repeat(np.arange(len(self.uids)), self.counts)
        self._users_w, self._sim, self._n = {}, {}, {}

    # item level
    def users_w(self, w):
        np = _np()
        if w not in self._users_w:
            mask = slice(None) if w is None else self.t1 >= self.A - w
            self._users_w[w] = np.bincount(self.ii[mask], minlength=self.n_items).astype(np.int64)
        return self._users_w[w]

    def item_new(self, w):
        """Per item: distinct users of the item whose first step on any item is >= A - w."""
        np = _np()
        u_first, _ = self.user_first_last()
        mask = u_first[self.ui] >= self.A - w
        return np.bincount(self.ii[mask], minlength=self.n_items).astype(np.int64)

    def item_first_last(self):
        np = _np()
        first = np.full(self.n_items, np.iinfo(np.int64).max)
        last = np.full(self.n_items, np.iinfo(np.int64).min)
        np.minimum.at(first, self.ii, self.t0)
        np.maximum.at(last, self.ii, self.t1)
        return first, last

    def global_order(self, counts):
        """Item positions ordered by counts descending, item_id ascending."""
        np = _np()
        return np.lexsort((self.items, -counts))

    # user level
    def positions(self, users):
        np = _np()
        users = np.asarray(users, dtype=np.int64)
        pos = np.searchsorted(self.uids, users)
        found = (pos < len(self.uids)) & (self.uids[np.minimum(pos, len(self.uids)-1)] == users)
        return pos, found

    def user_n_items(self, w):
        np = _np()
        mask = slice(None) if w is None else self.t1 >= self.A - w
        return np.bincount(self.ui[mask], minlength=len(self.uids)).astype(np.int64)

    def user_first_last(self):
        np = _np()
        # within a user block t1 is sorted descending: the first row holds the last step
        return np.minimum.reduceat(self.t0, self.starts), self.t1[self.starts]

    def sim(self, window):
        """Cosine co-occurrence of items over distinct users in [A-window, A), zero diagonal; extra zero row."""
        np = _np()
        if window not in self._sim:
            from scipy import sparse
            mask = self.t1 >= self.A - window
            ui, ii = self.ui[mask], self.ii[mask]
            x = sparse.csr_matrix((np.ones(len(ui), dtype=np.float64), (ui, ii)),
                                  shape=(len(self.uids), self.n_items))
            co = (x.T @ x).toarray()
            n = np.diag(co).copy()
            denom = np.sqrt(np.outer(n, n))
            sim = np.zeros((self.n_items+1, self.n_items), dtype=np.float64)
            with np.errstate(divide='ignore', invalid='ignore'):
                sim[:-1] = np.where(co > 0, co/np.where(denom > 0, denom, 1.0), 0.0)
            np.fill_diagonal(sim[:-1], 0.0)
            self._sim[window] = sim
            self._n[window] = np.append(n, 0.0)
        return self._sim[window]

    def n(self, window):
        """n(i) of the window (distinct users of i in it); the extra last entry 0 is the padding row."""
        self.sim(window)
        return self._n[window]

    def batch(self, pos, found, last):
        """Seen matrix (B x items) and the last ``last`` items per user (padded with the zero row)."""
        np = _np()
        b = len(pos)
        seen = np.zeros((b, self.n_items), dtype=bool)
        recent = np.full((b, max(last, 1)), self.n_items, dtype=np.int64)
        for row in range(b):
            if not found[row]:
                continue
            s, c = self.starts[pos[row]], self.counts[pos[row]]
            block = self.ii[s:s+c]
            seen[row, block] = True
            take = min(c, last)
            recent[row, :take] = block[:take]
        return seen, recent


def _rank_from_order(valid_sorted, order, shape):
    """Ranks 1.. over valid entries in sorted order, scattered back; inf elsewhere."""
    np = _np()
    cum = np.cumsum(valid_sorted, axis=1).astype(np.float64)
    ranks = np.where(valid_sorted, cum, np.inf)
    out = np.empty(shape, dtype=np.float64)
    np.put_along_axis(out, order, ranks, axis=1)
    return out


def rank_by_score(scores, valid):
    """Per row, rank of valid columns by score descending, then column (item_id) ascending; inf if invalid."""
    np = _np()
    key = np.where(valid, -scores, np.inf)
    order = np.argsort(key, axis=1, kind='stable')
    return _rank_from_order(np.take_along_axis(valid, order, axis=1), order, scores.shape)


def _pop_ranks(past, seen, window):
    np = _np()
    order = past.global_order(past.users_w(window))
    order = np.broadcast_to(order, seen.shape)
    unseen_sorted = ~np.take_along_axis(seen, order, axis=1)
    return _rank_from_order(unseen_sorted, order, seen.shape)


def _build(past, users, spec, require_history=True):
    """Candidate rows, source ranks and base features of ``users`` at past.A, in (user_id, item_id) order."""
    np, pd = _np(), _pd()
    A = past.A
    users = np.unique(np.asarray(list(users), dtype=np.int64))
    pos, found = past.positions(users)
    if require_history:
        xc.require(bool(found.all()), f'{int((~found).sum())} users have no history before {A}')
    sources, total = spec['sources'], spec['total']
    features = spec['features']
    lasts = [s['last'] for s in sources if s['kind'] == 'cooc'] or [1]
    users_all = past.users_w(None)
    global_rank = np.empty(past.n_items, dtype=np.int64)
    global_rank[past.global_order(users_all)] = np.arange(1, past.n_items+1)
    first, last_step = past.item_first_last()
    u_first, u_last = past.user_first_last()
    item_values, user_values = {}, {}
    for f in features:
        if f['level'] == 'item':
            if f['kind'] == 'users':
                item_values[f['name']] = past.users_w(f['params']['window'])
            elif f['kind'] == 'trend':
                u7, u30 = past.users_w(7).astype(np.float64), past.users_w(30).astype(np.float64)
                with np.errstate(divide='ignore', invalid='ignore'):
                    item_values[f['name']] = np.where(u30 > 0, u7/np.where(u30 > 0, u30, 1.0), np.nan)
            elif f['kind'] == 'item_age':
                item_values[f['name']] = A - first
            elif f['kind'] == 'item_last':
                item_values[f['name']] = A - last_step
            elif f['kind'] == 'pop_share':
                item_values[f['name']] = (past.users_w(f['params']['window']).astype(np.float64)
                                          / past.users_w(None).astype(np.float64))
            elif f['kind'] == 'item_new':
                item_values[f['name']] = past.item_new(f['params']['window'])
        elif f['level'] == 'user':
            if f['kind'] == 'n_items':
                user_values[f['name']] = past.user_n_items(f['params']['window'])
            elif f['kind'] == 'user_recency':
                user_values[f['name']] = A - u_last
            elif f['kind'] == 'user_age':
                user_values[f['name']] = A - u_first
            elif f['kind'] == 'user_rate':
                user_values[f['name']] = (past.user_n_items(None).astype(np.float64)
                                          / np.maximum(A - u_first, 1).astype(np.float64))
    pair_kinds = {}
    for f in features:
        if f['level'] == 'pair' and f['kind'].startswith('cooc_'):
            pair_kinds.setdefault(f['params']['source'], set()).add((f['kind'], f['params'].get('m')))
    chunks = []
    for lo in range(0, len(users), BATCH_USERS):
        b_users, b_pos, b_found = users[lo:lo+BATCH_USERS], pos[lo:lo+BATCH_USERS], found[lo:lo+BATCH_USERS]
        seen, recent = past.batch(b_pos, b_found, max(lasts))
        ranks, pair = {}, {}
        for s in sources:
            if s['kind'] == 'pop':
                r = _pop_ranks(past, seen, s['window'])
            else:
                mine = recent[:, :s['last']]
                g = past.sim(s['window'])[mine]
                score = np.round(g.sum(axis=1), s['decimals'])
                for kind, m in pair_kinds.get(s['name'], ()):
                    if kind == 'cooc_score':
                        value = score
                    elif kind == 'cooc_max':
                        value = g.max(axis=1)
                    elif kind == 'cooc_hits':
                        value = (g > 0).sum(axis=1)
                    elif kind == 'cooc_last':
                        value = g[:, :m].sum(axis=1)
                    elif kind == 'cooc_n_last':
                        value = (g[:, :m] > 0).sum(axis=1)
                    elif kind == 'cooc_wsum':
                        value = np.einsum('blj,l->bj', g, WSUM_DECAY ** np.arange(g.shape[1], dtype=np.float64))
                    else:
                        known = (past.n(s['window'])[mine] > 0).sum(axis=1).astype(np.float64)
                        with np.errstate(divide='ignore', invalid='ignore'):
                            value = np.where(known[:, None] > 0, score/np.where(known > 0, known, 1.0)[:, None], np.nan)
                    pair[(s['name'], kind, m)] = value
                del g
                r = rank_by_score(score, ~seen & (score > 0))
            if s['depth'] is not None:
                r[r > s['depth']] = np.inf
            ranks[s['name']] = r
        taken = np.zeros(seen.shape, dtype=bool)
        count = np.zeros(len(b_users), dtype=np.int64)
        reach = {}
        for s in sources:
            masked = np.where(taken, np.inf, ranks[s['name']])
            order = np.argsort(masked, axis=1, kind='stable')
            sorted_ranks = np.take_along_axis(masked, order, axis=1)
            valid = np.isfinite(sorted_ranks)
            cap = total - count
            keep = valid & (np.cumsum(valid, axis=1) <= cap[:, None])
            n_keep = keep.sum(axis=1)
            exhausted = valid.sum(axis=1) <= cap
            last_kept = sorted_ranks[np.arange(len(b_users)), np.maximum(n_keep-1, 0)]
            reach[s['name']] = np.where(exhausted, np.inf, np.where(n_keep > 0, last_kept, 0.0))
            kept = np.zeros(seen.shape, dtype=bool)
            np.put_along_axis(kept, order, keep, axis=1)
            taken |= kept
            count += n_keep
        rows, cols = np.nonzero(taken)
        chunk = {'user_id': b_users[rows], 'item_id': past.items[cols]}
        for f in features:
            name = f['name']
            if f['level'] == 'item':
                chunk[name] = item_values[name][cols]
            elif f['level'] == 'user':
                chunk[name] = user_values[name][b_pos[rows]]
            elif f['kind'] == 'global_rank':
                chunk[name] = global_rank[cols]
            elif f['kind'] == 'rank':
                chunk[name] = ranks[f['params']['source']][rows, cols]
            else:
                chunk[name] = pair[(f['params']['source'], f['kind'], f['params'].get('m'))][rows, cols]
        for s in sources:
            r = ranks[s['name']][rows, cols]
            chunk[SOURCE_PREFIX + s['name']] = np.where(r <= reach[s['name']][rows], r, np.inf)
        chunks.append(chunk)
    columns = ['user_id', 'item_id', *[f['name'] for f in features], *[SOURCE_PREFIX + s['name'] for s in sources]]
    data = {c: np.concatenate([chunk[c] for chunk in chunks]) if chunks else np.array([]) for c in columns}
    frame = pd.DataFrame({'user_id': data['user_id'].astype(np.int64), 'item_id': data['item_id'].astype(np.int64)})
    nullable_int = {f['name'] for f in features if f['kind'] == 'rank'} | {SOURCE_PREFIX + s['name'] for s in sources}
    for f in features:
        name = f['name']
        if name in nullable_int:
            continue
        if f['kind'] in FLOAT_KINDS:
            frame[name] = data[name].astype(np.float64)
        else:
            frame[name] = data[name].astype(np.int64)
    for name in sorted(nullable_int, key=columns.index):
        values = data[name]
        finite = np.isfinite(values)
        frame[name] = pd.arrays.IntegerArray(np.where(finite, values, 0).astype(np.int64), ~finite)
    return frame[columns]


# ---------------------------------------------------------------- collect

def _targets(con, A):
    """T(u, A): items of the window [A, A+W) not seen before A, for users with history before A."""
    return con.execute(f'''WITH past AS (SELECT DISTINCT user_id, item_id FROM events WHERE t < {A}),
        hist AS (SELECT DISTINCT user_id FROM past),
        future AS (SELECT DISTINCT user_id, item_id FROM events WHERE t >= {A} AND t < {A + W})
        SELECT f.user_id, f.item_id FROM future f
        WHERE f.user_id IN (SELECT user_id FROM hist)
          AND NOT EXISTS (SELECT 1 FROM past p WHERE p.user_id = f.user_id AND p.item_id = f.item_id)
        ORDER BY f.user_id, f.item_id''').df()


def _ordered_users(con, relation, limit=None):
    order = xc.QUERY_ORDER_SQL.format(column='user_id')
    tail = f' LIMIT {int(limit)}' if limit is not None else ''
    return [int(u) for (u,) in con.execute(
        f'SELECT user_id FROM (SELECT DISTINCT user_id FROM {relation}) ORDER BY {order}, user_id{tail}').fetchall()]


def test_users():
    """Kaggle test users from static.duckdb (no time, read freely)."""
    con = _connect(1, xc.static_path(DATASET), read_only=True)
    try:
        return [int(u) for (u,) in con.execute('SELECT user_id FROM test_users ORDER BY user_id').fetchall()]
    finally:
        con.close()


def collect(A, role, base, output, users=None):
    """Collection of ``role`` at A into the new directory ``output`` (format of xfer_common); its manifest."""
    np, pd = _np(), _pd()
    A = _step(A)
    xc.require(role in xc.ROLES, f'Unknown role {role!r}')
    xc.require(A in anchors()['roles'][role], f'{A} is not an anchor of role {role}')
    spec = _spec(base)
    if role == 'probe':
        xc.require(users is not None and len(users) > 0, 'A probe needs its user pool')
    else:
        xc.require(users is None, f'Role {role} takes its users from the data')
    output = Path(output)
    xc.require(not output.exists(), f'{output} exists; a collection goes to a new directory')
    if role == 'holdout':
        xc.require(output.resolve() == xc.current_holdout_collection(DATASET, A).resolve(),
                   'The holdout collection goes only to the current holdout collection path')
        purpose = 'collect-holdout'
    else:
        purpose = f'collect-{role}'
    code = xc.code_identity(DATASET)
    targets = None
    counts = {}
    if role in ('train', 'val', 'holdout'):
        con = history(A + W, purpose)
        try:
            targets = _targets(con, A)
            con.register('target_pairs', targets)
            eligible = con.execute('SELECT count(DISTINCT user_id) FROM target_pairs').fetchone()[0]
            queries = _ordered_users(con, 'target_pairs', N if role == 'train' else None)
        finally:
            con.close()
        targets = targets[targets['user_id'].isin(queries)]
        if role == 'train':
            counts['eligible_queries'] = int(eligible)
        counts['queries'] = len(queries)
    elif role == 'kaggle':
        queries = test_users()
    else:
        queries = sorted({int(u) for u in users})
    con = history(A, purpose)
    try:
        frame = _build(_Past(con, A), queries, spec)
    finally:
        con.close()
    output = xc.new_output(output)
    frame_path = output/xc.FRAME_FILE
    xc.write_parquet(frame, frame_path, order_by='user_id, item_id')
    counts.update(users=int(frame['user_id'].nunique()), rows=int(len(frame)))
    for column in source_columns(base):
        counts[column] = int(frame[column].notna().sum())
    labels = n_targets = None
    if targets is not None:
        positive = targets.assign(label=1)
        labels = frame[['user_id', 'item_id']].merge(positive, on=['user_id', 'item_id'], how='left')
        labels['label'] = labels['label'].fillna(0).astype(np.int8)
        n_targets = (targets.groupby('user_id').size().rename('n_targets').reset_index()
                     .astype({'n_targets': np.int64}))
        xc.require(set(n_targets['user_id']) == set(queries), 'Every query needs targets')
        xc.require(bool((n_targets['n_targets'] >= 1).all()), 'n_targets >= 1')
    sealed_hashes = None
    if role in ('train', 'val'):
        xc.write_parquet(labels, output/'labels.parquet', order_by='user_id, item_id')
        xc.write_parquet(n_targets, output/'targets.parquet', order_by='user_id')
        counts.update(positives=int(labels['label'].sum()), targets=int(n_targets['n_targets'].sum()))
    elif role == 'holdout':
        def writer(directory):
            xc.write_parquet(labels, Path(directory)/'labels.parquet', order_by='user_id, item_id')
            xc.write_parquet(n_targets, Path(directory)/'targets.parquet', order_by='user_id')
        sealed_hashes = xc.write_sealed(output, writer)
    extra = dict(frame_digest=content_digest(frame_path), features=xc.base_feature_names(base),
                 sources=source_columns(base), W=W, history_before=A)
    if role == 'probe':
        extra['users_digest'] = xc.canonical_digest(queries)
    return xc.write_manifest(output, DATASET, role, A, counts, base, code, sealed=sealed_hashes, extra=extra)


def training_rows(frame, labels, A, seed=xc.SAMPLE_SEED):
    """T trains on every candidate with weight 1 (no negative sampling); rows in (user_id, item_id) order."""
    np = _np()
    _step(A)
    _step(seed, 'seed')
    frame = _frame_input(frame, KEYS)
    labels = _frame_input(labels, (*KEYS, 'label'))
    merged = frame.merge(labels[[*KEYS, 'label']], on=list(KEYS), how='left', validate='one_to_one')
    xc.require(not merged['label'].isna().any(), 'Every frame row needs a label')
    merged['label'] = merged['label'].astype(np.int8)
    merged['weight'] = 1.0
    return merged.sort_values(list(KEYS), kind='stable').reset_index(drop=True)


# ---------------------------------------------------------------- Pop, metric

def pop(A, users, k=K):
    """Pop lists (section 5): k unseen items of I(A) by users_30 descending, item_id ascending."""
    np, pd = _np(), _pd()
    A = _step(A)
    k = _positive(k, 'k')
    con = history(A, 'pop')
    try:
        past = _Past(con, A)
    finally:
        con.close()
    users = np.unique(np.asarray(list(users), dtype=np.int64))
    pos, found = past.positions(users)
    out = []
    for lo in range(0, len(users), BATCH_USERS):
        seen, _ = past.batch(pos[lo:lo+BATCH_USERS], found[lo:lo+BATCH_USERS], 1)
        r = _pop_ranks(past, seen, 30)
        rows, cols = np.nonzero(r <= k)
        out.append(pd.DataFrame(dict(user_id=users[lo:lo+BATCH_USERS][rows], item_id=past.items[cols],
                                     rank=r[rows, cols].astype(np.int64))))
    frame = pd.concat(out, ignore_index=True) if out else pd.DataFrame(dict(user_id=[], item_id=[], rank=[]))
    return frame.sort_values(['user_id', 'rank'], kind='stable').reset_index(drop=True)


def metric(ranked, targets, labels):
    """Binary NDCG@K per query of ``targets``; relevance = pairs with label 1 in ``labels``; missing list = 0.

    Every ranked item with rank <= K needs a label row of its user (a candidate); an unlabelled item
    is refused, because its relevance is unknown. Ranked users must be queries of ``targets``.
    """
    np, pd = _np(), _pd()
    ranked = _frame_input(ranked, ('user_id', 'item_id', 'rank'))
    targets = _frame_input(targets, ('user_id', 'n_targets'))
    labels = _frame_input(labels, (*KEYS, 'label'))
    xc.require(not targets['user_id'].duplicated().any(), 'targets repeat a user')
    xc.require(bool((targets['n_targets'] >= 1).all()), 'n_targets must be >= 1')
    xc.require(not ranked.duplicated(['user_id', 'rank']).any(), 'A rank repeats for a user')
    xc.require(not ranked.duplicated(['user_id', 'item_id']).any(), 'An item repeats for a user')
    ranks = ranked['rank'].to_numpy()
    xc.require(len(ranks) == 0 or (np.all(ranks == np.floor(ranks)) and ranks.min() >= 1), 'Ranks are integers >= 1')
    xc.require(not labels.duplicated(list(KEYS)).any(), 'labels repeat a pair')
    top = ranked[ranked['rank'] <= K]
    xc.require(bool(top['user_id'].isin(targets['user_id']).all()), 'ranked has users outside the queries')
    joined = top.merge(labels[[*KEYS, 'label']], on=list(KEYS), how='left')
    xc.require(not joined['label'].isna().any(), 'A ranked item has no label (not a candidate)')
    hits = joined[joined['label'] == 1]
    gain = 1.0/np.log2(hits['rank'].to_numpy(dtype=np.float64)+1.0)
    dcg = pd.Series(gain, index=hits['user_id'].to_numpy()).groupby(level=0).sum()
    n_hits = hits.groupby('user_id').size()
    discounts = np.cumsum(1.0/np.log2(np.arange(2, K+2)))
    out = targets[['user_id', 'n_targets']].copy()
    n = out['n_targets'].to_numpy()
    xc.require(bool((out['user_id'].map(n_hits).fillna(0).to_numpy() <= n).all()), 'More hits than targets')
    idcg = discounts[np.minimum(n, K)-1]
    out['value'] = out['user_id'].map(dcg).fillna(0.0).to_numpy()/idcg
    return out[['user_id', 'value']].sort_values('user_id', kind='stable').reset_index(drop=True)


# ---------------------------------------------------------------- probe

def probe_pool():
    """Users with history before the probe anchor, first PROBE_USERS in query order (DuckDB sha256)."""
    con = history(PROBE, 'probe', threads=xc.THREADS['probe'])
    try:
        return _ordered_users(con, 'events', PROBE_USERS)
    finally:
        con.close()


def _round(value, digits=2):
    if value is None:
        return None
    value = round(float(value), digits)
    return int(value) if value.is_integer() else value


def probe_stats(A, users, base=None):
    """Label-free aggregates of the history before A (section 6.4) for stats.json."""
    np = _np()
    A = _step(A)
    if base is None:
        base = xc.read_base(DATASET)
    spec = _spec(base)
    quantiles = (10, 25, 50, 75, 90, 99)
    q_list = '[' + ', '.join(str(q/100) for q in quantiles) + ']'
    con = history(A, 'probe', threads=xc.THREADS['probe'])
    try:
        windows = {}
        for label, cond in (('last_7_steps', f't >= {A} - 7'), ('last_30_steps', f't >= {A} - 30'),
                            ('last_90_steps', f't >= {A} - 90'), ('last_180_steps', f't >= {A} - 180'),
                            ('all_history', 'TRUE')):
            rows, n_users, n_items = con.execute(f'''SELECT count(*), count(DISTINCT user_id),
                count(DISTINCT item_id) FROM events WHERE {cond}''').fetchone()
            windows[label] = dict(events=int(rows), users=int(n_users), items=int(n_items))

        def per(key, cond):
            n, mean, qs, most = con.execute(f'''SELECT count(*), avg(n), quantile_cont(n, {q_list}), max(n)
                FROM (SELECT {key}, count(*) AS n FROM events WHERE {cond} GROUP BY {key})''').fetchone()
            return dict(count=int(n), mean=_round(mean), **{f'p{q}': _round(v) for q, v in zip(quantiles, qs or [None]*6)},
                        max=None if most is None else int(most))
        per_user_all = per('user_id', 'TRUE')
        per_user_30 = per('user_id', f't >= {A} - 30')
        repeat = con.execute(f'''SELECT avg(CASE WHEN steps >= 2 THEN 1 ELSE 0 END) FROM (SELECT user_id,
            count(DISTINCT t) AS steps FROM events WHERE t >= {A} - 30 GROUP BY user_id)''').fetchone()[0]
        per_item_all = per('item_id', 'TRUE')
        frame = _build(_Past(con, A), users, spec)
    finally:
        con.close()
    n_users = frame['user_id'].nunique()
    added, earlier = {}, np.zeros(len(frame), dtype=bool)
    for source in spec['sources']:
        present = frame[SOURCE_PREFIX + source['name']].notna().to_numpy()
        added[source['name']] = _round((present & ~earlier).sum()/n_users)
        earlier |= present
    return dict(
        events_by_window=windows,
        events_per_user_all_history=per_user_all,
        events_per_user_last_30_steps=per_user_30,
        users_with_2_or_more_steps_last_30_steps_share=_round(repeat, 4),
        events_per_item_all_history=per_item_all,
        candidates=dict(users=int(n_users), per_user_mean=_round(len(frame)/n_users),
                        added_per_user_mean_by_source=added))


# ---------------------------------------------------------------- prompt

def _render_number(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        xc.require(math.isfinite(value), 'Prompt numbers are finite')
        return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
    return ' '.join(str(value).split())


def _tree(value, depth=0):
    """Indented plain-text rendering of stats.json in its own key order."""
    pad, lines = '  '*depth, []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f'{pad}{key}:')
                lines.extend(_tree(item, depth+1))
            else:
                lines.append(f'{pad}{key}: {_render_number(item)}')
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f'{pad}-')
                lines.extend(_tree(item, depth+1))
            else:
                lines.append(f'{pad}- {_render_number(item)}')
    else:
        lines.append(pad + _render_number(value))
    return lines


def _candidates_text(candidates):
    sources = _policy(candidates)
    lines = ['For a user u at anchor A every source lists items with an event before A that u has not interacted '
             'with before A; ties go to the smaller item_id.']
    for s in sources:
        depth = '' if s['depth'] is None else f'; the first {s["depth"]}'
        if s['kind'] == 'pop':
            window = 'before A' if s['window'] is None else f'in [A-{s["window"]}, A)'
            lines.append(f'- {s["name"]}: items by distinct users {window}, descending{depth}.')
        else:
            lines.append(
                f'- {s["name"]}: E = interactions in [A-{s["window"]}, A); n(i) = distinct users of i in E; '
                f'co(i, j) = distinct users with both i and j in E; sim(i, j) = co(i, j) / sqrt(n(i) n(j)); '
                f'L(u) = the last {s["last"]} distinct items of u before A by time step descending, then item_id; '
                f'score(j) = sum of sim(i, j) over i in L(u), rounded to {s["decimals"]} decimals; items with a '
                f'positive score by score descending{depth}.')
    lines.append(f'Union: the sources in this order, each skipping items already taken, up to {candidates["total"]} '
                 'candidates per user (all unseen items when fewer). Each source position is a feature below.')
    return '\n'.join(lines)


def _features_text(base):
    spec = _spec(base)
    return '\n'.join(f'- {f["name"]} [{f["level"]}]: {f["formula"]}; missing: {f["missing"]}' for f in spec['features'])


def _tables_text():
    ev = ', '.join(f'{n} {t}' for n, t in EV_SCHEMA)
    lines = [f'{EV_VIEW}({ev})', '  every interaction with t < A; each (user_id, item_id) pair occurs at most once']
    for name, text in (('cand', 'the candidate pairs of the current batch, keys only'),
                       ('users', 'the distinct users of cand')):
        cols = ', '.join(f'{n} {t}' for n, t in BATCH_SCHEMA[name])
        lines.append(f'{name}({cols}): {text}')
    lines.append('There is no user or item attribute table.')
    return '\n'.join(lines)


def _tens(seconds):
    xc.require(not isinstance(seconds, bool) and isinstance(seconds, (int, float)) and math.isfinite(seconds),
               'Budget seconds must be finite numbers')
    return int(max(float(seconds), 0.0) // 10 * 10)


def prompt_substitutions(stats, base, history, round_index, budget):
    """Slot values of PROMPT_TEMPLATE; ``history`` is the feedback text rendered by xfer_agent,
    ``budget`` the probe seconds left as dict(pair_user_seconds=..., item_seconds=...)."""
    xc.require(isinstance(stats, dict) and stats, 'stats.json must be a non-empty object')
    xc.require(type(round_index) is int and 1 <= round_index <= PROMPT_CONSTANTS['rounds'], 'Bad round index')
    xc.require(isinstance(budget, dict) and set(budget) == set(BUDGET), f'Budget needs {sorted(BUDGET)}')
    xc.require(history is None or isinstance(history, str), 'History is text')
    base = xc.check_base(base, DATASET)
    subs = {key: _render_number(value) for key, value in PROMPT_CONSTANTS.items()}
    subs.update(candidates=_candidates_text(base['candidates']), features=_features_text(base), tables=_tables_text(),
                stats='\n'.join(_tree(stats)), history=history.strip() if history and history.strip() else '(none yet)',
                round=str(round_index), budget_pair_user=str(_tens(budget['pair_user_seconds'])),
                budget_item=str(_tens(budget['item_seconds'])))
    return subs


def render_prompt(stats, base, history, round_index, budget):
    return PROMPT_TEMPLATE.format(**prompt_substitutions(stats, base, history, round_index, budget))


def prompt_digest():
    """Identity of the fixed prompt parts: the template and PROMPT_CONSTANTS."""
    return xc.canonical_digest(dict(template=PROMPT_TEMPLATE, constants=PROMPT_CONSTANTS))


# ---------------------------------------------------------------- assemble

def pair_keys(users, items):
    """One int64 key per (user_id, item_id) pair (ids are below 2**31)."""
    np = _np()
    users, items = np.asarray(users, dtype=np.int64), np.asarray(items, dtype=np.int64)
    xc.require(bool(((users >= 0) & (users < 2**31) & (items >= 0) & (items < 2**31)).all()), 'Ids out of range')
    return users*(2**31) + items


def check_submission(path, users, universe, seen, k=K, scores=None, fill=None):
    """Re-read a submission: header, LF, k distinct known unseen items per test user, nothing else.

    ``universe`` holds the known item ids, ``seen`` the pair_keys of the history pairs. With ``scores``
    (user_id, item_id, score) and ``fill`` (the fallback item order) the order is re-checked too: every
    user's rows, in file order, are the top scored items by score descending, then item_id, followed
    by the first unseen, unscored items of ``fill``.
    """
    np = _np()
    raw = Path(path).read_bytes()
    xc.require(b'\r' not in raw, 'Submission lines must end with LF')
    text = raw.decode('utf-8')
    xc.require(text.endswith('\n'), 'Submission must end with a newline')
    lines = text[:-1].split('\n')
    xc.require(lines[0] == SUBMISSION_HEADER, f'Header must be {SUBMISSION_HEADER}')
    body = lines[1:]
    xc.require(all(re.fullmatch(r'[0-9]+,[0-9]+', line) for line in body), 'Malformed submission line')
    pairs = np.asarray([[int(x) for x in line.split(',')] for line in body], dtype=np.int64).reshape(-1, 2)
    u, i = pairs[:, 0], pairs[:, 1]
    users = np.unique(np.asarray(list(users), dtype=np.int64))
    xc.require(bool(np.isin(u, users).all()), 'A row carries a user outside the test users')
    xc.require(bool(np.isin(i, np.asarray(list(universe), dtype=np.int64)).all()), 'An item is outside I(701)')
    keys = pair_keys(u, i)
    xc.require(not np.isin(keys, np.asarray(seen, dtype=np.int64)).any(), 'An item was already seen by the user')
    xc.require(len(np.unique(keys)) == len(keys), 'A pair repeats')
    present, counts = np.unique(u, return_counts=True)
    xc.require(len(present) == len(users) and bool((present == users).all()), 'Every test user needs rows')
    xc.require(bool((counts == k).all()), f'{int((counts != k).sum())} users do not have exactly {k} rows')
    if scores is not None:
        xc.require(fill is not None, 'The order check needs the fill order')
        expected = _expected_lists(scores, users, seen, fill, k)
        got = {}
        for user, item in zip(u.tolist(), i.tolist()):
            got.setdefault(user, []).append(item)
        wrong = [user for user in users.tolist() if got[user] != expected[user]]
        xc.require(not wrong, f'{len(wrong)} users are out of the expected order, e.g. {wrong[:3]}')
    return dict(rows=int(len(keys)), users=int(len(users)))


def _expected_lists(scores, users, seen, fill, k):
    """Per user: scored items by score descending, item_id ascending, then unseen unscored items of fill."""
    np = _np()
    seen = np.sort(np.asarray(seen, dtype=np.int64))
    fill = np.asarray(list(fill), dtype=np.int64)
    table = scores[['user_id', 'item_id', 'score']].astype({'user_id': np.int64, 'item_id': np.int64})
    expected = {}
    for user, group in table.groupby('user_id', sort=True):
        group = group.sort_values(['score', 'item_id'], ascending=[False, True], kind='stable')
        expected[int(user)] = group['item_id'].head(k).tolist()
    scored = {int(user): set(group.tolist()) for user, group in table.groupby('user_id')['item_id']}
    for user in [int(x) for x in users]:
        items = expected.setdefault(user, [])
        if len(items) < k:
            keys = pair_keys(np.full(len(fill), user), fill)
            at = np.minimum(np.searchsorted(seen, keys), max(len(seen)-1, 0))
            unseen = fill[~((seen[at] == keys) if len(seen) else np.zeros(len(fill), dtype=bool))]
            taken = scored.get(user, set())
            items.extend([int(x) for x in unseen if int(x) not in taken][:k-len(items)])
    return expected


def assemble(scores, output):
    """Kaggle file from ``user_id, item_id, score`` of the kaggle frame; ``output`` is the target .csv path."""
    np, pd = _np(), _pd()
    output = Path(output)
    xc.require(output.suffix == '.csv', 'The output is a .csv path')
    allowed = (xc.ROOT/'artifacts'/'xfer').resolve()
    xc.require(output.parent.resolve().is_relative_to(allowed), f'Outputs must live under {allowed}')
    part = output.with_name(output.name + '.part')
    receipt = output.with_suffix('.json')
    xc.require(not any(p.exists() for p in (output, part, receipt)), f'{output.name} or its .part/.json exists')
    scores = _frame_input(scores, ('user_id', 'item_id', 'score'))[['user_id', 'item_id', 'score']].copy()
    code = xc.code_identity(DATASET)
    xc.require(bool(np.isfinite(scores['score'].to_numpy(dtype=np.float64)).all()), 'Scores must be finite')
    xc.require(not scores.duplicated(['user_id', 'item_id']).any(), 'Scores repeat a pair')
    targets = test_users()
    target_set = set(targets)
    xc.require(set(scores['user_id'].astype(np.int64)) <= target_set, 'Scores carry users outside the test users')
    con = history(KAGGLE, 'assemble')
    try:
        past = _Past(con, KAGGLE)
    finally:
        con.close()
    universe = past.items
    seen_keys = pair_keys(past.uids[past.ui], past.items[past.ii])
    xc.require(bool(np.isin(scores['item_id'].to_numpy(dtype=np.int64), universe).all()),
               'Scores carry items outside I(701)')
    xc.require(not np.isin(pair_keys(scores['user_id'], scores['item_id']), seen_keys).any(),
               'Scores carry items the user has seen')
    ranked = scores.sort_values(['user_id', 'score', 'item_id'], ascending=[True, False, True], kind='stable')
    ranked = ranked.groupby('user_id', sort=True).head(K)
    lists = {u: [] for u in targets}
    for u, i in zip(ranked['user_id'].astype(np.int64).tolist(), ranked['item_id'].astype(np.int64).tolist()):
        lists[u].append(i)
    fallback = [u for u in targets if len(lists[u]) < K]
    if fallback:
        order = past.items[past.global_order(past.users_w(None))].tolist()
        pos, found = past.positions(fallback)
        for u, p, f in zip(fallback, pos, found):
            have = set(lists[u])
            if f:
                s, c = past.starts[p], past.counts[p]
                have |= set(int(i) for i in past.items[past.ii[s:s+c]])
            for i in order:
                if len(lists[u]) >= K:
                    break
                if i not in have:
                    lists[u].append(int(i))
                    have.add(int(i))
    with part.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(SUBMISSION_HEADER + '\n')
        for u in targets:
            for i in lists[u]:
                stream.write(f'{u},{i}\n')
    checked = check_submission(part, targets, universe, seen_keys, scores=scores,
                               fill=past.items[past.global_order(past.users_w(None))].tolist())
    os.replace(part, output)
    body = dict(format=ASSEMBLE_FORMAT, dataset=DATASET, file=output.name, sha256=xc.sha256_file(output),
                rows=checked['rows'], users=checked['users'], fallback_users=len(fallback),
                scores_digest=content_digest(scores), scores_rows=int(len(scores)), code=code,
                created_utc=xc.utc_now())
    xc.atomic_json(receipt, body)
    return body


# ---------------------------------------------------------------- CLI

def _read_users(path):
    text = Path(path).read_text(encoding='utf-8').strip()
    values = json.loads(text) if text.startswith('[') else [line for line in text.split() if line]
    return [int(v) for v in values]


def _handler(argv):
    xc.isolated()
    parser = argparse.ArgumentParser(prog='xfer_tinkoff.py')
    parser.add_argument('--dataset', default=DATASET, choices=[DATASET])
    commands = parser.add_subparsers(dest='command', required=True)
    p_load = commands.add_parser('load')
    p_load.add_argument('--dataset', default=DATASET, choices=[DATASET])
    p_load.add_argument('--raw', default=None)
    p_load.add_argument('--output', default=None)
    p_collect = commands.add_parser('collect')
    p_collect.add_argument('--dataset', default=DATASET, choices=[DATASET])
    p_collect.add_argument('--role', required=True, choices=list(xc.ROLES))
    p_collect.add_argument('--anchor', required=True, type=int)
    p_collect.add_argument('--base', required=True)
    p_collect.add_argument('--output', required=True)
    p_collect.add_argument('--users-file', default=None)
    args = parser.parse_args(argv)
    if args.command == 'load':
        raw = Path(args.raw) if args.raw else xc.raw_dir(DATASET)
        output = Path(args.output) if args.output else xc.output_dir(DATASET, 'load')
        report = load(raw, output)
        return dict(command='load', output=str(output), facts=report['facts'], partitions=len(report['partitions']),
                    digest=report['digest'])
    base = xc.read_base(args.base)
    xc.require(not Path(args.output).exists(), f'{args.output} exists; a collection goes to a new directory')
    users = _read_users(args.users_file) if args.users_file else None
    if args.role == 'probe' and users is None:
        users = probe_pool()
    manifest = collect(args.anchor, args.role, base, Path(args.output), users=users)
    return dict(command='collect', output=str(Path(args.output).resolve()), role=manifest['role'],
                anchor=manifest['anchor'], counts=manifest['counts'], frame_digest=manifest['frame_digest'])


def main(argv=None):
    return xc.run_cli(_handler, argv)


if __name__ == '__main__':
    sys.exit(main())
