"""Placebo control and decomposition of H+ in task 1, pre-registered in task1/runs/placebo-2026-10-21/spec.md.

H+ is the base H (80 hand-made features) with all the automation of the grid (task1/runs/grid-2026-10-20): the DFS
tables dfs_p, dfs_c, dfs_b, dfs_u and the 30 tables agent_night20_*, 194 columns. The placebo Hpl is H+ with those
194 columns permuted jointly within each anchor day; the key-level placebo Hpk moves the values of every table to
other entities of its join key; Hag and Hdfs add only the agent tables or only the DFS tables.

run: the recipe of task1.exp.run (the same pool, sampling, fit, day-by-day scoring and per-query file in exp.OUT, a
record in exp.OUT/runs.jsonl) with two config keys exp.run does not have:
  cap      fit on the first `cap` queries of the train split in the order of exp._read (2020: as many as 2019 train);
  permute  'within_day': every column the join of the extra tables added is moved by one row permutation per anchor
           day (permute_within_days); 'by_key': the columns of each table move to other users, other products or
           other rows of the query, by the table's join key (permute_by_key). Either is applied after the join, on the
           train frame and on each validation day separately.
Without them a run gives exp.run's per-query metrics (tests/test_task1_placebo.py). The pool leaves exp's cache after
sampling, as in task1.replicate. Nothing about the metrics is printed or recorded: `read` opens the per-query files
once, when every run is done. Only the train and val splits are read, never refit or test. A queue starts only when
the code, the spec and the queues are committed; every record carries the commit and the start time.

read: paired bootstraps per seed of D = H+ - Hpl (the rule), Dk = H+ - Hpk (the same rule, secondary), Hpl - H,
Hpk - H, Hpk - Hpl and Hag - H, Hdfs - H with their shares of H+ - H (descriptive) on 2019 val half B and 2020 val;
writes result.json next to the spec. It reads only with the code, tests, spec and queues committed and the code the
runs were stamped with, so the rules cannot change after the runs.

  .venv/bin/python -m task1.placebo run task1/runs/placebo-2026-10-21/queue-2019.json
  TASK1_PERIOD=2020 .venv/bin/python -m task1.placebo run task1/runs/placebo-2026-10-21/queue-2020.json
  .venv/bin/python -m task1.placebo read
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from task1 import exp, posthoc
from task1 import model as M
from task1 import period as P

DIR = M.ROOT / 'task1/runs/placebo-2026-10-21'
RESULT = DIR / 'result.json'
ROW, KEY = 'within_day', 'by_key'  # the values of `permute`: Hpl and Hpk
TAG = 20261021  # the first word of every permutation seed
KEY_TAG = 2  # the second word of every key-level seed
CODE = ('task1/exp.py', 'task1/model.py', 'task1/period.py', 'task1/posthoc.py', 'task1/placebo.py')  # the stamp
TESTS = 'tests/test_task1_placebo.py'  # committed with the code, not in the stamp
LIBS = ('pandas', 'numpy', 'duckdb', 'catboost', 'pyarrow')
CONFIG = {'cap', 'permute'}  # the config keys run has beyond exp.DEFAULT
LEVEL_OF_KEY = {('user_id',): 'user', ('product_id',): 'product', ('user_id', 'product_id'): 'pair'}
LEVEL_ORDER = ('user', 'product', 'pair')
_A = 'agent_night20_'
LEVELS = {  # the level of each table of H+ by its join key, read from the schemas on 20.10 (both periods alike)
    'user': ['dfs_u'],
    'product': ['dfs_p', 'dfs_c', 'dfs_b'] + [_A + t for t in (
        'r1p1_first_touch_conversion', 'r1p3_buyer_price_profile', 'r1p4_new_reach', 'r1p5_cp_staleness',
        'r2p1_cmp_session_win_lift', 'r2p4_revisit_consideration', 'r2p5_view_dwell_time',
        'r3p1_view_session_last_choice', 'r3p2_intraday_momentum_12h', 'r3p5_category_search_depth',
        'r4p1_acq_regularity_7d', 'r4p2_cat_acq_concentration', 'r4p3_weekday_seasonality_14d')],
    'pair': [_A + t for t in (
        'r1p2_coacq_cf', 'r2p2_cp_category_complement', 'r2p3_acq_seed_coview_cf', 'r3p3_user_user_cf_acq',
        'r3p4_brand_cat_price_sibling', 'r4p4_cat_to_item_transition', 'r4p5_brand_switch_transition',
        'r5p1_cf_xday_new_acq_transition', 'r5p2_cf_next_view_adjacency', 'r5p3_cf_converting_session_coview',
        'r5p4_uc_nextday_continuation', 'r5p5_cf_considered_seed_coview', 'r6p1_older_view_seed_coview',
        'r6p2_dwell_seed_coview', 'r6p3_abandoned_cart_seed_coview', 'r6p4_user_level_cooccurrence_cf',
        'r6p5_fresh_2d_coview_graph')]}

OUT = {'2019': M.ROOT / 'artifacts/task1/v2/exp', '2020': M.ROOT / 'artifacts/task1/v2020/exp'}  # exp.OUT per period
QUEUE = {p: DIR / f'queue-{p}.json' for p in OUT}
ARMS = ('H', 'Hp', 'Hpl', 'Hpk', 'Hag', 'Hdfs')
REUSED = {'H': ['q2_d8', 'q3_d8_s1'], 'Hp': ['grid_Hp_s0', 'grid_Hp_s1']}  # 2019 H and H+, not refitted
DECLARED_H = {'q2_d8': {'days': 'artifacts/task1/v2/days6', 'depth': 8},  # their queues predate the grid
              'q3_d8_s1': {'days': 'artifacts/task1/v2/days6', 'depth': 8, 'seed': 7, 'neg_seed': 1}}
FEATURES = {'H': 80, 'Hp': 274, 'Hpl': 274, 'Hpk': 274, 'Hag': 146, 'Hdfs': 208}
PERMUTED = {'Hpl': 194, 'Hpk': 194}
FIT_QUERIES = {'2019': 101959, '2020': 101959}  # every query of the 2019 train split; 2020 is capped to as many
GRID_RESULT = posthoc.DIR / 'result.json'
READING = {'content': 'прирост H+ несёт содержание колонок, а не их число',
           'placebo': 'H+ не отличим от плацебо', 'placebo_better': 'плацебо лучше H+', 'undecided': 'не решено'}
CLAIM = {'content': READING['content'],
         'placebo': 'H+ не отличим от плацебо: утверждение о H+ снимается для обоих периодов',
         'placebo_better': 'плацебо лучше H+: утверждение о H+ снимается для обоих периодов',
         'undecided': 'не решено'}
AGAINST = {'placebo', 'placebo_better'}  # the readings that count against content
READING_KEYS = {'content': 'H+ лучше плацебо по ключам', 'placebo': 'H+ не отличим от плацебо по ключам',
                'placebo_better': 'плацебо по ключам лучше H+', 'undecided': 'не решено'}
CAVEAT = 'вывод о содержании не устойчив к плацебо по ключам'
CAVEAT_KEYS = 'плацебо по ключам находит содержание, построчное плацебо — нет'


def movable(df, cols):
    """Stop unless cols are distinct numeric f_x_ columns of df: keys, labels and hand-made features never move."""
    cols = list(cols)
    bad = [c for c in cols if c not in df.columns or not c.startswith('f_x_') or c in M.META
           or not pd.api.types.is_numeric_dtype(df[c])]
    if not cols or bad or len(set(cols)) != len(cols):
        raise ValueError(f'only joined numeric f_x_ columns are permuted; refused {bad[:3] or cols[:3]}')
    return cols


def day_of(t):
    t = pd.Timestamp(t)
    if t != t.normalize():
        raise ValueError(f'anchor {t} is not a day')
    return t


def permute_within_days(df, cols, seed, neg_seed):
    """df with the values of `cols` moved jointly by one random row permutation per anchor day; every other column
    stays as it was. Within a day the rows are ordered by (user_id, product_id); the row at position i takes the values
    of the row at position perm[i], perm = default_rng([TAG, seed, neg_seed, ordinal of the day]).permutation(rows of
    the day). The result depends on the seeds, the day and the rows of the day, not on the order of df."""
    cols = movable(df, cols)
    out = df.copy(deep=False)
    if not len(df):
        return out
    days, day = np.unique(df['anchor'].to_numpy(), return_inverse=True)
    user, item = df['user_id'].to_numpy(), df['product_id'].to_numpy()
    order = np.lexsort((item, user, day))
    d, u, i = day[order], user[order], item[order]
    if ((d[1:] == d[:-1]) & (u[1:] == u[:-1]) & (i[1:] == i[:-1])).any():
        raise ValueError('rows are not unique by (anchor, user_id, product_id)')
    src = np.empty(len(df), dtype=np.int64)
    for rows in np.split(order, np.flatnonzero(np.diff(d)) + 1):
        t = day_of(days[day[rows[0]]])
        src[rows] = rows[np.random.default_rng([TAG, int(seed), int(neg_seed), t.toordinal()]).permutation(len(rows))]
    for c in cols:
        out[c] = df[c].to_numpy()[src]
    return out


def permute_by_key(df, levels, seed, neg_seed):
    """df with the columns of each level moved to other entities of that level within each anchor day; every other
    column stays as it was. levels: {'user': cols, 'product': cols, 'pair': cols}, any of them.
      user     one permutation pi_u of the day's distinct user_id, shared by all user columns: every row of user u takes
               the values of user pi_u(u). The values must be the same on all rows of a user in a day.
      product  one permutation pi_p of the day's distinct product_id, shared by all product columns: every row of
               product p takes the whole vector of product pi_p(p). The values must be constant per (day, product).
      pair     the rows of each query (anchor, user_id) are permuted, jointly over all pair columns.
    Rows with a NULL user_id or product_id keep the values of the levels keyed by it. The users, products and rows of
    a day are taken in sorted order; default_rng([TAG, KEY_TAG, seed, neg_seed, ordinal of the day]) draws pi_u, then
    pi_p, then one uniform number per row with both keys, whose order within the query is the pair permutation. The
    result depends on the seeds, the day and its rows, not on the order of df."""
    if not set(levels) <= set(LEVEL_ORDER):
        raise ValueError(f'levels {sorted(levels)}: only {LEVEL_ORDER}')
    movable(df, [c for v in levels.values() for c in v])
    out = df.copy(deep=False)
    if not len(df):
        return out
    days, day = np.unique(df['anchor'].to_numpy(), return_inverse=True)
    user = pd.factorize(df['user_id'], sort=True)[0]  # -1: NULL
    item = pd.factorize(df['product_id'], sort=True)[0]
    order = np.lexsort((item, user, day))
    d, u, i = day[order], user[order], item[order]
    if ((d[1:] == d[:-1]) & (u[1:] == u[:-1]) & (i[1:] == i[:-1]) & (u[1:] >= 0) & (i[1:] >= 0)).any():
        raise ValueError('rows are not unique by (anchor, user_id, product_id)')
    src = {lv: np.arange(len(df)) for lv in LEVEL_ORDER}  # the row whose values a row takes
    first = {lv: np.arange(len(df)) for lv in ('user', 'product')}  # the first row of the row's user or product
    for rows in np.split(order, np.flatnonzero(np.diff(d)) + 1):
        t = day_of(days[day[rows[0]]])
        rng = np.random.default_rng([TAG, KEY_TAG, int(seed), int(neg_seed), t.toordinal()])
        for lv, code in (('user', user), ('product', item)):
            r = rows[code[rows] >= 0]
            _, head, inv = np.unique(code[r], return_index=True, return_inverse=True)
            perm = rng.permutation(len(head))
            first[lv][r] = r[head[inv]]
            src[lv][r] = r[head[perm[inv]]]
        r = rows[(user[rows] >= 0) & (item[rows] >= 0)]
        src['pair'][r] = r[np.lexsort((rng.random(len(r)), user[r]))]
    for lv in ('user', 'product'):
        for c in levels.get(lv, []):
            v = df[c].to_numpy()
            w = v[first[lv]]
            if not ((v == w) | (np.isnan(v) & np.isnan(w))).all():
                raise ValueError(f'{c}: the values of the {lv} level differ between rows of one {lv} in a day')
    for lv, cols in levels.items():
        for c in cols:
            out[c] = df[c].to_numpy()[src[lv]]
    return out


def table_levels(extra, day):
    """table -> (level, value columns) by the join key in the schema of the table's file for `day`, the files
    exp.with_extra reads: user_id alone is the user level, product_id alone the product level, both the pair level.
    A table with another key stops the run."""
    out = {}
    for name in extra:
        cols = duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{M.EXTRA / name / f'{day}.parquet'}')").df()
        cols = cols.column_name.tolist()
        key = tuple(c for c in ('user_id', 'product_id') if c in cols)
        if key not in LEVEL_OF_KEY:
            raise ValueError(f'{name}: the join key {key} maps to no level')
        out[name] = LEVEL_OF_KEY[key], [c for c in cols if c not in key]
    return out


def join(df, cfg):
    """exp.with_extra; for a placebo config every column the join added is then permuted, within days or by key.
    Returns the frame, the columns the join added and, for the key-level placebo, level -> tables."""
    before = list(df.columns)
    out = exp.with_extra(df, cfg['extra'])
    if list(out.columns[:len(before)]) != before:
        raise ValueError('the join renamed or moved a column of the day tables')
    added = list(out.columns[len(before):])
    if cfg.get('permute') == ROW:
        return permute_within_days(out, added, cfg['seed'], cfg['neg_seed']), added, None
    if cfg.get('permute') != KEY:
        return out, added, None
    tables = table_levels(cfg['extra'], day_of(df.anchor.min()).strftime('%Y-%m-%d'))
    if [c for t in cfg['extra'] for c in tables[t][1]] != added:
        raise ValueError('the schemas of the extra tables do not give the joined columns')
    levels = {lv: [c for t in cfg['extra'] if tables[t][0] == lv for c in tables[t][1]] for lv in LEVEL_ORDER}
    out = permute_by_key(out, {lv: c for lv, c in levels.items() if c}, cfg['seed'], cfg['neg_seed'])
    return out, added, {lv: [t for t in cfg['extra'] if tables[t][0] == lv] for lv in LEVEL_ORDER}


def peak_gb():
    """Peak resident memory of this process so far (ru_maxrss is in bytes on macOS, in KiB on Linux)."""
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (2**30 if sys.platform == 'darwin' else 2**20), 1)


def code_stamp():
    return {f: hashlib.sha256((M.ROOT / f).read_bytes()).hexdigest()[:16] for f in CODE}


def libraries():
    """Versions of the libraries the fit and the metrics depend on; None for one that is not installed."""
    out = {}
    for name in LIBS:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def validate(name, cfg):
    """Stop on a config run cannot carry out as declared: an unknown key, an unknown permute, permute without extra
    tables, or a path into a sealed directory."""
    unknown = sorted(set(cfg) - set(exp.DEFAULT) - CONFIG)
    if unknown or cfg.get('permute') not in (None, ROW, KEY) or (cfg.get('permute') and not cfg['extra']):
        raise ValueError(f'{name}: unknown config keys {unknown} or permute {cfg.get("permute")!r} '
                         f'with {len(cfg["extra"])} extra tables')
    paths = [str(cfg['days'])] + [str(M.EXTRA / e) for e in cfg['extra']]
    if any('sealed' in x for x in paths):
        raise ValueError(f'{name}: a path into a sealed directory is refused')


def git(*args):
    return subprocess.run(['git', *args], cwd=M.ROOT, capture_output=True, text=True, check=True).stdout


def committed():
    """HEAD, once the code, the tests, the spec and the queues are committed: the runs start after the
    pre-registration and the reading follows it. result.json, written by `read`, is not part of the check."""
    rel = DIR.relative_to(M.ROOT).as_posix()
    dirty = git('status', '--porcelain', '--', *CODE, TESTS, rel, f':(exclude){rel}/result.json')
    if dirty:
        raise SystemExit(f'commit the spec, the queues, the code and the tests before the runs and the reading:\n{dirty}')
    return git('rev-parse', 'HEAD').strip()


def run(name, commit=None, stamp=None, **over):
    """One arm with exp.run's recipe and the optional `cap` and `permute`. Writes exp.OUT/<name>.parquet (per-query
    metrics and half, as exp.run) and a record without metrics to exp.OUT/runs.jsonl. `stamp` is the code stamp the
    run must end with (the queue's, taken at its start; by default the stamp at the start of the run): if the code
    changed meanwhile, nothing is written."""
    cfg = exp.DEFAULT | over
    validate(name, cfg)
    stamp = stamp or code_stamp()
    t0 = time.time()
    train = exp.sample_train(exp._read('train', cfg['days'], cfg.get('cap')), cfg)
    exp._cache.clear()  # as in task1.replicate: the pool is the largest frame, the joins need the room
    train, added, levels = join(train, cfg)
    features = M.base_features(train, cfg['drop'])
    train_rows, fit_queries = len(train), int(train.qid.nunique())
    t1 = time.time()
    m = exp.fit(train, features, cfg)
    del train
    used = [features.index(c) for c in added if c in features]
    imp = m.get_feature_importance()
    share = round(float(imp[used].sum() / imp.sum()), 4) if used else None  # descriptive, outside the rules
    t2 = time.time()
    parts = []  # as exp.run: a day of validation at a time
    for d in M.days('val'):
        val, _, val_levels = join(exp.read_day(d, cfg['days']), cfg)
        if val_levels != levels:
            raise ValueError(f'{d}: the tables by level differ from the train frame: {val_levels}')
        score = M.predict(m, val, features)
        pq = M.per_query(val, score)
        users = val.drop_duplicates('qid').set_index('qid').user_id
        pq['half'] = exp.half(users.reindex(pq.index).to_numpy())
        parts.append(pq.join(M.per_query(val, score, purchase=True).add_prefix('purchase_'), how='left'))
        del val
    t3 = time.time()
    res = pd.concat(parts).sort_index().reset_index()
    if code_stamp() != stamp:
        raise SystemExit(f'{name}: the code changed during the run; nothing was written')
    exp.OUT.mkdir(parents=True, exist_ok=True)
    tmp = exp.OUT / f'.{name}.parquet.tmp'
    duckdb.sql(f"COPY (SELECT * FROM res) TO '{tmp}' (FORMAT PARQUET)")
    os.replace(tmp, exp.OUT / f'{name}.parquet')
    rec = {'name': name, 'cfg': cfg, 'features': len(features), 'train_rows': train_rows, 'fit_queries': fit_queries,
           'permuted': len(added) if cfg.get('permute') else 0, 'levels': levels, 'added_importance': share,
           'peak_rss_gb': peak_gb(), 'libraries': libraries(),
           'code': stamp, 'commit': commit, 'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0)),
           'seconds': {'prepare': round(t1 - t0), 'fit': round(t2 - t1), 'predict': round(t3 - t2)}}
    with (exp.OUT / 'runs.jsonl').open('a') as f:
        f.write(json.dumps(rec) + '\n')
    print(json.dumps({k: rec[k] for k in ('name', 'features', 'permuted', 'fit_queries', 'train_rows', 'peak_rss_gb',
                                          'seconds')}), flush=True)
    return rec


def last_records(out):
    """name -> the last record of each run in out/runs.jsonl."""
    path = out / 'runs.jsonl'
    return {r['name']: r for r in map(json.loads, path.read_text().splitlines())} if path.exists() else {}


def all_records(out):
    path = out / 'runs.jsonl'
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def run_queue(path, commit=None):
    """Run a queue of this period in order. The whole queue is validated first. A run whose file and record exist
    with the declared config is skipped (a stopped queue goes on); a file without a record or with another config
    stops the queue. The code stamp is taken once: a record of an earlier run of this check (pl*, either period) with
    another stamp stops the queue, and every run must end with that stamp."""
    queue = json.loads(Path(path).read_text())
    stamp = code_stamp()
    prefix = f'pl{P.PERIOD[2:]}_'
    if Path.cwd().resolve() != M.ROOT.resolve():
        raise SystemExit(f'run from {M.ROOT}: the queues name the day directories relative to it, as exp.run reads them')
    for x in queue:
        days = Path(x['days']) if Path(x['days']).is_absolute() else M.ROOT / x['days']
        if not x['name'].startswith(prefix) or not days.resolve().is_relative_to(P.ART.resolve()):
            raise SystemExit(f"{x['name']}: not a run of TASK1_PERIOD={P.PERIOD} ({prefix}*, days under {P.ART})")
    if len({x['name'] for x in queue}) != len(queue):
        raise SystemExit(f'{path}: duplicate run names')
    for x in queue:
        try:
            validate(x['name'], exp.DEFAULT | {k: v for k, v in x.items() if k != 'name'})
        except ValueError as e:
            raise SystemExit(f'{path}: {e}') from None
    other = sorted({r['name'] for out in OUT.values() for r in all_records(out)
                    if r['name'].startswith('pl') and r.get('code') != stamp})
    if other:
        raise SystemExit(f'runs of this check with another version of the code: {other}; the runs share one code')
    for x in queue:
        over = {k: v for k, v in x.items() if k != 'name'}
        if (exp.OUT / f"{x['name']}.parquet").exists():
            rec = last_records(exp.OUT).get(x['name'])
            if rec is None or rec['cfg'] != exp.DEFAULT | over:
                raise SystemExit(f"{x['name']}: a file exists without a record or with another config; move it aside")
            print(json.dumps({'name': x['name'], 'skipped': 'done with the declared config'}), flush=True)
            continue
        run(x['name'], commit, stamp, **over)


def names(period, arm):
    if period == '2019' and arm in REUSED:
        return REUSED[arm]
    return [f'pl{period[2:]}_{arm}_s{i}' for i in range(2)]


def declared():
    """name -> the config each run of the check was declared with, without the stand's defaults."""
    strip = lambda x: {k: v for k, v in x.items() if k != 'name'}
    grid = {x['name']: strip(x) for x in json.loads((posthoc.DIR / 'grid.json').read_text())}
    out = DECLARED_H | {n: grid[n] for n in REUSED['Hp']}
    for q in QUEUE.values():
        out |= {x['name']: strip(x) for x in json.loads(q.read_text())}
    return out


def check(period, decl, recs):
    """Stop unless every run of the period carries its declared config (exactly), its number of features and, for
    the new runs, the permuted columns, the fit queries of the spec and a commit, and Hpk the levels of the spec; all
    runs of a period train on as many rows, and the arms of a seed share its seeds. Returns the records of the new
    runs."""
    new, rows, seeds = [], set(), [set(), set()]
    for arm in ARMS:
        for i, n in enumerate(names(period, arm)):
            r = recs[n]
            if r['cfg'] != exp.DEFAULT | decl[n]:
                raise SystemExit(f'{n}: the config in runs.jsonl differs from its declaration')
            if r['features'] != FEATURES[arm]:
                raise SystemExit(f"{n}: {r['features']} features, expected {FEATURES[arm]}")
            rows.add(r['train_rows'])
            seeds[i].add((r['cfg']['seed'], r['cfg']['neg_seed']))
            if n not in REUSED.get(arm, []):
                want = PERMUTED.get(arm, 0), FIT_QUERIES[period]
                if (r.get('permuted'), r.get('fit_queries')) != want or not r.get('commit'):
                    raise SystemExit(f"{n}: permuted {r.get('permuted')} columns, fit on {r.get('fit_queries')} "
                                     f"queries, commit {r.get('commit')}; expected {want[0]}, {want[1]} and a commit")
                if r.get('levels') != (LEVELS if arm == 'Hpk' else None):
                    raise SystemExit(f'{n}: the tables by level differ from the spec: {r.get("levels")}')
                new.append(r)
    if len(rows) != 1:
        raise SystemExit(f'{period}: the runs train on different numbers of rows {sorted(rows)}')
    if any(len(s) != 1 for s in seeds) or seeds[0] == seeds[1]:
        raise SystemExit(f'{period}: the arms of a seed differ in seeds {seeds}')
    return new


def boot(ref, new):
    """mean(new - ref) with the paired bootstrap CI of M.bootstrap_diff (2000 resamples, seed 2026), unrounded."""
    return tuple(float(v) for v in M.bootstrap_diff(ref, new))


def reading(d_by_seed):
    """The rule of the spec on D = H+ - Hpl (or Dk = H+ - Hpk) of the two seeds of one period."""
    if all(d > 0 and lo > 0 for d, lo, _ in d_by_seed):
        return 'content'
    if all(hi < 0 for _, _, hi in d_by_seed):
        return 'placebo_better'
    if all(lo <= 0 <= hi for _, lo, hi in d_by_seed):
        return 'placebo'
    return 'undecided'


def claim(readings):
    """The common reading of the two periods. When they differ the difference is said and the claim is 'не решено',
    unless both readings count against content."""
    a, b = readings['2019'], readings['2020']
    if a == b:
        return {'claim': CLAIM[a], 'periods': 'согласны'}
    split = f'расходятся: 2019 val B — «{READING[a]}», 2020 val — «{READING[b]}»'
    if {a, b} <= AGAINST:  # both against content: indistinguishable in one, worse in the other
        return {'claim': CLAIM['placebo'], 'periods': split}
    return {'claim': CLAIM['undecided'], 'periods': split}


def compare(x):
    """x: arm -> per-seed NDCG@20 Series over the same queries. Unrounded differences, shares and the reading."""
    by_seed = lambda ref, new: [boot(r, n) for r, n in zip(x[ref], x[new])]
    mean = {a: sum(s) / len(s) for a, s in x.items()}
    pairs = {'D': ('Hpl', 'Hp'), 'Dk': ('Hpk', 'Hp'), 'P': ('H', 'Hpl'), 'Pk': ('H', 'Hpk'), 'Hpk-Hpl': ('Hpl', 'Hpk'),
             'Hp-H': ('H', 'Hp'), 'Hag-H': ('H', 'Hag'), 'Hdfs-H': ('H', 'Hdfs')}
    raw = {k: by_seed(*v) for k, v in pairs.items()}
    raw['share'] = {a: [posthoc.ratio(h, s, p) for h, s, p in zip(x['H'], x[a], x['Hp'])] for a in ('Hag', 'Hdfs')}
    raw['mean_of_seeds'] = {k: boot(mean[r], mean[n]) for k, (r, n) in pairs.items()}
    raw['reading'] = reading(raw['D'])
    raw['reading_keys'] = reading(raw['Dk'])
    return raw


def render(x, raw, seeds):
    r5 = lambda t: {'d': round(t[0], 5), 'ci': [round(t[1], 5), round(t[2], 5)]}
    r3 = lambda t: {'r': round(t[0], 3), 'ci': [round(t[1], 3), round(t[2], 3)]}
    out = {'queries': len(x['H'][0]), 'ndcg_by_seed': {a: [round(float(s.mean()), 5) for s in v] for a, v in x.items()}}
    for k in ('D', 'Dk', 'P', 'Pk', 'Hpk-Hpl', 'Hp-H', 'Hag-H', 'Hdfs-H'):
        out[k] = [{'seed': s} | r5(t) for s, t in zip(seeds, raw[k])]
    out['share'] = {a: [{'seed': s} | r3(t) for s, t in zip(seeds, v)] for a, v in raw['share'].items()}
    out['share']['sum'] = [round(a[0] + d[0], 3) for a, d in zip(raw['share']['Hag'], raw['share']['Hdfs'])]
    out['mean_of_seeds'] = {k: r5(t) for k, t in raw['mean_of_seeds'].items()}
    out['reading'] = READING[raw['reading']]
    out['reading_keys'] = READING_KEYS[raw['reading_keys']]
    # content by D while Dk fails rule 1 on a seed
    # content by D while Dk fails rule 1 on a seed; placebo by D while Dk reads content
    out['caveat'] = (CAVEAT if raw['reading'] == 'content' and raw['reading_keys'] != 'content'
                     else CAVEAT_KEYS if raw['reading'] == 'placebo' and raw['reading_keys'] == 'content' else None)
    return out


def read():
    """Check every run, compare per period, print and write result.json. Stops without reading a metric while the
    code, tests, spec or queues are not committed, while a run is missing or when the code differs from the code of
    the runs; never replaces a result.json that says something else."""
    head = committed()
    decl, recs = declared(), {p: last_records(o) for p, o in OUT.items()}
    missing = [n for p in OUT for a in ARMS for n in names(p, a)
               if n not in recs[p] or not (OUT[p] / f'{n}.parquet').exists()]
    if missing:
        raise SystemExit(f'not every run is done, nothing was read: {missing}')
    new = [r for p in OUT for r in check(p, decl, recs[p])]
    stamps = {json.dumps(r['code'], sort_keys=True) for r in new}
    if len(stamps) != 1:
        raise SystemExit(f'the new runs ran on {len(stamps)} versions of the code')
    if code_stamp() != new[0]['code']:
        raise SystemExit('the code differs from the code of the runs: the rules are read as they were run')
    libs = {json.dumps(r.get('libraries'), sort_keys=True) for r in new}
    if len(libs) != 1 or new[0].get('libraries') is None:
        raise SystemExit(f'the new runs ran on {len(libs)} sets of library versions')
    if libraries() != new[0]['libraries']:
        raise SystemExit('the library versions differ from those of the runs: the bootstrap may draw differently')
    res, raws = {}, {}
    for p, out in OUT.items():
        m = {a: [duckdb.sql(f"SELECT * FROM '{out / n}.parquet'").df().set_index('qid') for n in names(p, a)]
             for a in ARMS}
        base = m['H'][0]
        if any(not s.index.equals(base.index) for v in m.values() for s in v):
            raise SystemExit(f'{p}: the runs differ in queries')
        idx = base.index[base.half == 'B'] if p == '2019' else base.index
        x = {a: [s.loc[idx, 'ndcg'] for s in v] for a, v in m.items()}
        if any(s.isna().any() for v in x.values() for s in v):
            raise SystemExit(f'{p}: NDCG is missing for some queries')
        seeds = [[recs[p][n]['cfg']['seed'], recs[p][n]['cfg']['neg_seed']] for n in names(p, 'Hpl')]
        raws[p] = compare(x)
        res[p] = {'eval': 'val B 2019-11-08..13' if p == '2019' else 'val 2020-02-08..13',
                  'runs': {a: names(p, a) for a in ARMS}} | render(x, raws[p], seeds)
    grid = [{k: v for k, v in g.items() if k in ('d', 'ci')}
            for g in json.loads(GRID_RESULT.read_text())['grid']['Hp-H_by_seed']]
    if grid != [{k: v for k, v in g.items() if k != 'seed'} for g in res['2019']['Hp-H']]:
        raise SystemExit('H+ - H of the 2019 runs read here differs from the grid result')
    res |= claim({p: raws[p]['reading'] for p in OUT})
    res['caveats'] = {p: res[p]['caveat'] for p in OUT if res[p]['caveat']}
    res['fits'] = {r['name']: {k: r[k] for k in ('features', 'permuted', 'fit_queries', 'train_rows',
                                                 'added_importance', 'peak_rss_gb', 'seconds', 'commit', 'started')}
                   for r in new}
    res['levels'] = LEVELS
    res['code'] = new[0]['code']
    res['libraries'] = new[0]['libraries']
    res['spec_sha256'] = hashlib.sha256((DIR / 'spec.md').read_bytes()).hexdigest()
    if RESULT.exists():  # the same result read again (at another time or commit) leaves the file as it is
        old = json.loads(RESULT.read_text())
        old.pop('read', None)
        if old != json.loads(json.dumps(res, ensure_ascii=False)):
            raise SystemExit(f'{RESULT} exists and says something else; it is not replaced')
        print(RESULT.read_text(), end='')
        return
    res['read'] = {'commit': head, 'at': time.strftime('%Y-%m-%d %H:%M:%S')}
    text = json.dumps(res, indent=1, ensure_ascii=False) + '\n'
    tmp = RESULT.with_name(f'.{RESULT.name}.tmp')
    tmp.write_text(text)
    os.replace(tmp, RESULT)
    print(text, end='')


def main():
    ap = argparse.ArgumentParser(description='placebo control and decomposition of H+ (task 1)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('run', help='run a queue of this TASK1_PERIOD').add_argument('queue')
    sub.add_parser('read', help='read both periods once every run is done; writes result.json')
    args = ap.parse_args()
    if args.cmd == 'run':
        run_queue(args.queue, committed())
    else:
        read()


if __name__ == '__main__':
    main()
