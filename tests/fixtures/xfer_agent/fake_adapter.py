"""Synthetic adapter for tests/test_xfer_agent.py (interface of the xfer_common docstring).

Events (user_id, item_id, t) with t in [0, 90) live in buckets of 10 steps:
``load/events/b=<start>/part-0.parquet`` under the patched ``xc.ROOT``. Anchors:
train 40, 50; val and probe 60; holdout 70; kaggle 80. Item 9999 (the canary) occurs only
at t >= 60. ``LEAKY = True`` drops the time filter of the view (a broken adapter).
"""
import numpy as np
import pandas as pd

from scripts import xfer_common as xc

DATASET = 'tinkoff'
STEP = 10
T_MAX = 90
USERS = 120
ITEMS = 40
CANARY = 9999
POOL = 60
LEAKY = False
FILES_FOR = {}  # anchor -> anchor whose partitions views() lists (a broken partition cut)
EXTRA = ''  # appended to the stats slot: a stray number for the whitelist test
SECRET_SQL = '__never_in_any_view__'

WARNING = ('All valid columns will enter the model without selection. Superfluous and noisy columns hurt: '
           'a few strong, non-redundant signals are needed. User-level columns work only through interactions.')
PROMPT_CONSTANTS = dict(k=5, w=10, rounds=6, proposals=5)
PROMPT_TEMPLATE = """Feature engineer task. Reply with JSON only.
Recommend {k} items over a window of {w} steps. The anchor is written {{A}}.
FEATURES
{features}
STATS
{stats}
WARNING
""" + WARNING + """
EARLIER ATTEMPTS
{history}
Budget left: pair+user {budget_pair_user} s of 90 s; item {budget_item} s of 180 s.
This is round {round} of {rounds}; propose {proposals} features.
"""


def build(seed=7):
    """Write the bucket partitions; returns the events frame."""
    rng = np.random.default_rng(seed)
    rows = []
    for user in range(1, USERS+1):
        for t in sorted(rng.choice(T_MAX, size=30, replace=False)):
            rows.append((user, int(rng.integers(1, ITEMS+1)), int(t)))
        if user % 3 == 0:
            rows.append((user, CANARY, int(rng.integers(60, T_MAX))))
    events = pd.DataFrame(rows, columns=['user_id', 'item_id', 't']).astype('int64')
    events['t'] = events['t'].astype('int32')
    parts = xc.events_path(DATASET)['parts']
    for start in range(0, T_MAX, STEP):
        directory = parts/f'b={start}'
        directory.mkdir(parents=True, exist_ok=True)
        chunk = events[(events['t'] >= start) & (events['t'] < start+STEP)]
        xc.write_parquet(chunk, directory/'part-0.parquet', order_by='user_id, t')
    return events


def anchors():
    return dict(W=STEP, N=100, K=5, roles=dict(train=[40, 50], val=[60], holdout=[70], kaggle=[80], probe=[60]),
                series={}, holdout=70, probe=60)


def _files(A):
    parts = xc.events_path(DATASET)['parts']
    files = []
    upto = FILES_FOR.get(A, A)
    for start in range(0, T_MAX, STEP):
        if start+STEP <= upto:
            files.extend(sorted((parts/f'b={start}').glob('*.parquet')))
    return [str(f.resolve()) for f in files]


def views(A, purpose):
    if A > anchors()['holdout']:
        xc.require_window(DATASET, purpose)
    files = _files(A)
    listed = ', '.join("'" + f + "'" for f in files)
    ev = f'SELECT user_id, item_id, t FROM read_parquet([{listed}], hive_partitioning=false)'
    if not LEAKY:
        ev += f' WHERE t < {A}'
    return dict(files=files, views={'ev': ev}, schema={'ev': [['user_id', 'BIGINT'], ['item_id', 'BIGINT'],
                                                              ['t', 'INTEGER']]},
                levels={'pair': ['user_id', 'item_id'], 'user': ['user_id'], 'item': ['item_id']},
                items='SELECT DISTINCT item_id FROM ev')


def check_sql(sql, level):
    import re
    if re.search(r'(<=|>=|<>|!=|<|>|=)\s*t\b', sql, re.I):
        raise ValueError('t must stand on the left of a comparison')
    if re.search(r'\bt\s*(<=|>=|<>|!=|<|>|=)\s*-?\d', sql, re.I):
        raise ValueError('t may not be compared with a number')


def sql_rules():
    return dict(forbidden=['data_train', r'ev_\w+'], check=check_sql)


def probe_pool():
    """Users with history before the probe anchor, the first POOL in query order."""
    import duckdb
    con = duckdb.connect()
    try:
        users = con.execute('SELECT DISTINCT user_id FROM read_parquet(?)', [_files(60)]).fetchnumpy()['user_id']
    finally:
        con.close()
    return xc.cap_queries([int(u) for u in users], POOL)


def probe_stats(A, users):
    return dict(users=len(users), window_steps=STEP, items=ITEMS, mean_events_per_user=3.5)


def coverage_sources():
    return {'recent': ['rank_recent'], 'global': ['rank_pop']}


def prompt_substitutions(stats, base, history, round_index, budget):
    subs = {key: str(value) for key, value in PROMPT_CONSTANTS.items()}
    features = '\n'.join(f"- {f['name']}: {f['formula']}" for f in base['features'])
    subs.update(features=features, stats='\n'.join(f'{k}: {v}' for k, v in stats.items()) + EXTRA,
                history=history or '(none yet)', round=str(round_index),
                budget_pair_user=str(budget['pair_user_seconds']), budget_item=str(budget['item_seconds']))
    return subs
