"""One fit of the council rehearsal by a JSON spec (council/runs/rees46-2020/contract.md §3.1), in its own process.

The spec names the spans of roles.SPANS to fit on and to score, a recipe of roles.RECIPES on top of exp.DEFAULT, the
extra tables, the seeds, an optional placebo and, for S0, the half of the users to keep:

  {"name": "plan_r07", "fit": "T_fit", "eval": "S0", "keep_half": "B", "recipe": "plan",
   "extra": ["dfs_p", ...], "seed": 1007, "neg_seed": 7,
   "placebo": {"columns": ["f_x_a", ...], "tables": ["council_g1_1", ...]} | null}

The recipe is task1.placebo.run's: the pool of exp._read over an explicit list of days (all positives, 100 random and
30 hard negatives per query, the first `cap` queries in the order hash(user_id, 2026), user_id, anchor), exp.sample_train,
exp.with_extra, exp.fit, then each scored day on its own with every candidate (exp.read_day), M.predict, M.per_query
(and purchases) and exp.half. Placebo: the tables of `placebo.tables` are joined too, each column of `placebo.columns`
is copied to f_x_plc_<column without f_x_> and moved by task1.placebo.permute_within_days with the campaign's seeds
(roles.PLACEBO_SEED, 0); the joined columns of a placebo table that is not in `extra` are dropped.

Writes roles.FITS/<name>.parquet (qid, anchor, half, ndcg, recall, purchase_ndcg, purchase_recall) atomically, never over
an existing file, then a record without metrics to roles.FITS/runs.jsonl. Nothing about the metrics is printed.

  TASK1_PERIOD=2020 .venv/bin/python -m council.fit --spec spec.json
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from council import roles
from task1 import exp, placebo
from task1 import model as M

KEYS = ('name', 'fit', 'eval', 'keep_half', 'recipe', 'extra', 'seed', 'neg_seed', 'placebo')
OPTIONAL = {'keep_half': None, 'placebo': None}
FIT_OF = {'S0': 'T_fit', 'val': 'train', 'test': 'refit'}  # the span each scored span is fitted on
HALVES = (roles.EXPLORE, roles.SELECT)
COLUMNS = ['qid', 'anchor', 'half', 'ndcg', 'recall', 'purchase_ndcg', 'purchase_recall']
PLC = 'f_x_plc_'
TASK1_CODE = ('task1/exp.py', 'task1/model.py', 'task1/extra.py', 'task1/placebo.py', 'task1/period.py')
NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*')
TABLE = re.compile(r'[A-Za-z0-9_]+')


def _str_list(x, what, name):
    if not isinstance(x, list) or not all(isinstance(v, str) for v in x) or len(set(x)) != len(x):
        raise ValueError(f'{name}: {what} must be a list of distinct strings')
    return list(x)


def _table(t, name):
    if not TABLE.fullmatch(t) or 'sealed' in t:
        raise ValueError(f'{name}: extra table {t!r} is refused (a plain table name outside sealed directories)')
    path = M.EXTRA / t
    if 'sealed' in path.resolve().as_posix():
        raise ValueError(f'{name}: a path into a sealed directory is refused')
    if not path.is_dir():
        raise ValueError(f'{name}: extra table {t} does not exist under {M.EXTRA}')


def validate(spec):
    """The normalized spec (every key, in KEYS order), or ValueError before anything is read."""
    if not isinstance(spec, dict):
        raise ValueError('a spec is a JSON object')
    name = spec.get('name')
    if not isinstance(name, str) or not NAME.fullmatch(name) or 'sealed' in name:
        raise ValueError(f'name {name!r}: letters, digits, _ . - only')
    unknown = sorted(set(spec) - set(KEYS))
    missing = sorted(set(KEYS) - set(OPTIONAL) - set(spec))
    if unknown or missing:
        raise ValueError(f'{name}: unknown keys {unknown}, missing keys {missing}')
    s = {k: spec.get(k, OPTIONAL.get(k)) for k in KEYS}
    if not isinstance(s['eval'], str) or s['eval'] not in FIT_OF or s['fit'] != FIT_OF[s['eval']]:
        raise ValueError(f"{name}: fit {s['fit']!r} -> eval {s['eval']!r}; allowed {FIT_OF}")
    if s['fit'] not in roles.SPANS or s['eval'] not in roles.SPANS or roles.days(s['fit'])[-1] >= roles.days(s['eval'])[0]:
        raise ValueError(f"{name}: the fit span must end before the scored span")
    if s['eval'] == 'S0':
        if s['keep_half'] not in HALVES:
            raise ValueError(f'{name}: eval S0 needs keep_half in {HALVES}')
    elif s['keep_half'] is not None:
        raise ValueError(f"{name}: keep_half is for S0 only, got {s['keep_half']!r} on {s['eval']}")
    if s['recipe'] not in roles.RECIPES:
        raise ValueError(f"{name}: recipe {s['recipe']!r} not in {sorted(roles.RECIPES)}")
    for k in ('seed', 'neg_seed'):
        if not isinstance(s[k], int) or isinstance(s[k], bool) or s[k] < 0:
            raise ValueError(f'{name}: {k} must be a non-negative integer')
    s['extra'] = _str_list(s['extra'], 'extra', name)
    pl = s['placebo']
    if pl is not None:
        if not isinstance(pl, dict) or set(pl) != {'columns', 'tables'}:
            raise ValueError(f'{name}: placebo is null or {{"columns": [...], "tables": [...]}}')
        cols, tables = _str_list(pl['columns'], 'placebo.columns', name), _str_list(pl['tables'], 'placebo.tables', name)
        if not cols or not tables or not all(c.startswith('f_x_') and not c.startswith(PLC) for c in cols):
            raise ValueError(f'{name}: placebo needs tables and f_x_ columns (not {PLC}*)')
        s['placebo'] = {'columns': cols, 'tables': tables}
    for t in s['extra'] + (s['placebo']['tables'] if s['placebo'] else []):
        _table(t, name)
    if 'sealed' in Path(roles.DAYS6).resolve().as_posix():
        raise ValueError(f'{name}: a path into a sealed directory is refused')
    if s['eval'] == 'test' and not (roles.RUNS / 'test.started').exists():
        raise ValueError(f"{name}: eval 'test' needs the marker {roles.RUNS / 'test.started'} (broker.start_test)")
    return s


def config(s):
    """The exp config of a normalized spec: exp.DEFAULT, the recipe, the seeds, the extra tables, days6."""
    return exp.DEFAULT | roles.RECIPES[s['recipe']] | {
        'seed': s['seed'], 'neg_seed': s['neg_seed'], 'extra': list(s['extra']), 'days': str(roles.DAYS6)}


def path_spec():
    """The path check of §3.1: H+r in full_val with (2026, 0), train -> val; compare with pl20_Hp_s0 (broker.path_check)."""
    return {'name': 'path_Hr_full_val_s0', 'fit': 'train', 'eval': 'val', 'keep_half': None, 'recipe': 'full_val',
            'extra': list(roles.HPLUS), 'seed': 2026, 'neg_seed': 0, 'placebo': None}


def pool(days, days_dir, cap=None):
    """The train pool of exp._read for an explicit list of anchor days: the same SQL, ranks, order and float32."""
    files = [str(Path(days_dir) / f'{d}.parquet') for d in days]
    cols = duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{files[0]}')").df().column_name.tolist()
    hard = 'cf_cv_cond_tdecay20' if 'cf_cv_cond_tdecay20' in cols else 'cf_cv_cond_tdecay'
    src = f'read_parquet({files})'
    if cap:
        src = (f'(SELECT * FROM {src} SEMI JOIN (SELECT anchor, user_id FROM (SELECT DISTINCT anchor, user_id FROM {src}) '
               f'ORDER BY hash(user_id, 2026), user_id, anchor LIMIT {int(cap)}) q USING (anchor, user_id))')
    df = duckdb.sql(f"""SELECT * FROM (
      SELECT d.*, d.anchor::VARCHAR || ':' || d.user_id::VARCHAR qid,
        row_number() OVER (PARTITION BY d.anchor, d.user_id ORDER BY hash(d.product_id, d.user_id, 7)) rr,
        row_number() OVER (PARTITION BY d.anchor, d.user_id ORDER BY d.{hard} DESC, d.product_id) hr
      FROM {src} d) WHERE label = 1 OR rr <= 100 OR hr <= 30
      ORDER BY qid, product_id""").df()
    for c in df.columns:
        if df[c].dtype == np.float64:
            df[c] = df[c].astype(np.float32)
    return df


def plc_name(col):
    return PLC + col.removeprefix('f_x_')


def join(df, s):
    """exp.with_extra of the spec's tables, then the placebo columns; returns the frame and the number of columns
    the placebo added. Tables are joined one by one (as exp.with_extra does) to know the columns of each."""
    before = list(df.columns)
    pl = s['placebo']
    only = [t for t in (pl['tables'] if pl else []) if t not in s['extra']]
    of_table = {}
    for t in s['extra'] + only:
        n = len(df.columns)
        df = exp.with_extra(df, [t])
        of_table[t] = list(df.columns[n:])
    if list(df.columns[:len(before)]) != before:
        raise ValueError('the join renamed or moved a column of the day tables')
    if not pl:
        return df, 0
    joined = {c for t in pl['tables'] for c in of_table[t]}
    lost = [c for c in pl['columns'] if c not in joined]
    if lost:
        raise ValueError(f'placebo columns {lost[:3]} are not columns of the placebo tables')
    new = [plc_name(c) for c in pl['columns']]
    if set(new) & set(df.columns):
        raise ValueError(f'placebo columns {sorted(set(new) & set(df.columns))[:3]} already exist')
    df = df.assign(**{n: df[c] for n, c in zip(new, pl['columns'])})
    df = placebo.permute_within_days(df, new, roles.PLACEBO_SEED, 0)
    return df.drop(columns=[c for t in only for c in of_table[t]]), len(new)


FIT_CODE = ('council/fit.py', 'council/roles.py')  # the council code a fit runs; the other modules never reach it


def code_stamp():
    files = list(FIT_CODE) + list(TASK1_CODE)
    out = {}
    for f in files:
        try:
            out[f] = hashlib.sha256((roles.ROOT / f).read_bytes()).hexdigest()[:16]
        except FileNotFoundError:
            raise SystemExit(f'code stamp: {f} disappeared while the stamp was taken; the code is being edited') from None
    return out


def _files(directory, days):
    """Number, total size and latest mtime (ns) of the day files of `days` in `directory` that exist."""
    st = [f.stat() for f in (Path(directory) / f'{d}.parquet' for d in days) if f.exists()]
    return {'files': len(st), 'bytes': sum(x.st_size for x in st), 'mtime_ns': max((x.st_mtime_ns for x in st), default=0)}


def data_stamp(spec):
    """Fingerprint of the data a normalized spec reads: for days6 and every extra and placebo table, the day files of
    the fit and scored spans (number, total size, latest mtime). A fit must start and end with the same one."""
    days = roles.days(spec['fit']) + roles.days(spec['eval'])
    tables = list(spec['extra']) + [t for t in (spec['placebo'] or {}).get('tables', []) if t not in spec['extra']]
    return {'days6': _files(roles.DAYS6, days), 'tables': {t: _files(M.EXTRA / t, days) for t in tables}}


def git_head():
    """HEAD and whether the stamped files differ from it; (None, None) outside a git checkout."""
    try:
        run_ = lambda *a: subprocess.run(['git', *a], cwd=roles.ROOT, capture_output=True, text=True, check=True).stdout
        return run_('rev-parse', 'HEAD').strip(), bool(run_('status', '--porcelain', '--', *code_stamp()).strip())
    except (OSError, subprocess.CalledProcessError):
        return None, None


def _rel(p):
    p = Path(p)
    return p.relative_to(roles.ROOT).as_posix() if p.is_relative_to(roles.ROOT) else p.as_posix()


def run(spec, commit=None, stamp=None, dirty=None, data=None):
    """One fit; returns the record written to roles.FITS/runs.jsonl. `stamp` and `data`: the code stamp and the data
    fingerprint the fit must start and end with (the queue's); by default those at the start."""
    s = validate(spec)
    name, cfg = s['name'], config(s)
    out = roles.FITS / f'{name}.parquet'
    if out.exists():
        raise ValueError(f'{name}: {out} exists; fits are never overwritten')
    stamp = stamp or code_stamp()
    if code_stamp() != stamp:
        raise SystemExit(f'{name}: the code differs from the stamp of the queue')
    data = data or data_stamp(s)
    if data_stamp(s) != data:
        raise SystemExit(f'{name}: the data differ from the fingerprint of the queue')
    t0 = time.time()
    train = exp.sample_train(pool(roles.days(s['fit']), cfg['days'], cfg['cap']), cfg)
    train, permuted = join(train, s)
    features = M.base_features(train, cfg['drop'])
    if s['extra'] == roles.HPLUS and not s['placebo'] and len(features) != roles.HPLUS_FEATURES:
        raise ValueError(f'{name}: H+r has {len(features)} features, expected {roles.HPLUS_FEATURES}')
    train_rows, fit_queries = len(train), int(train.qid.nunique())
    t1 = time.time()
    m = exp.fit(train, features, cfg)
    del train
    t2 = time.time()
    parts = []
    for d in roles.days(s['eval']):
        df, _ = join(exp.read_day(d, cfg['days']), s)
        missing = [c for c in features if c not in df.columns]
        if missing:
            raise ValueError(f'{name}: {d} lacks features {missing[:3]}')
        score = M.predict(m, df, features)
        pq = M.per_query(df, score)
        users = df.drop_duplicates('qid').set_index('qid').user_id
        pq['half'] = exp.half(users.reindex(pq.index).to_numpy())
        pq = pq.join(M.per_query(df, score, purchase=True).add_prefix('purchase_'), how='left')
        pq['anchor'] = str(d)
        if s['keep_half']:
            pq = pq[pq.half == s['keep_half']]
        parts.append(pq)
        del df
    t3 = time.time()
    res = pd.concat(parts).sort_index().rename_axis('qid').reset_index()[COLUMNS]
    res['half'] = res.half.astype(str)
    if code_stamp() != stamp:
        raise SystemExit(f'{name}: the code changed during the fit; nothing was written')
    if data_stamp(s) != data:
        raise SystemExit(f'{name}: the data changed during the fit; nothing was written')
    roles.FITS.mkdir(parents=True, exist_ok=True)
    tmp = roles.FITS / f'.{name}.parquet.tmp'
    duckdb.sql(f"COPY (SELECT * FROM res) TO '{tmp}' (FORMAT PARQUET)")
    try:
        os.link(tmp, out)  # fails if the file appeared meanwhile: no overwrite
    finally:
        tmp.unlink()
    rec = {'name': name, 'spec': s, 'cfg': cfg | {'days': _rel(cfg['days'])}, 'features': len(features),
           'placebo_columns': permuted, 'train_rows': train_rows, 'fit_queries': fit_queries, 'eval_queries': len(res),
           'peak_rss_gb': placebo.peak_gb(), 'libraries': placebo.libraries(), 'code': stamp, 'data': data, 'commit': commit,
           'dirty': dirty, 'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0)),
           'seconds': {'prepare': round(t1 - t0), 'fit': round(t2 - t1), 'predict': round(t3 - t2),
                       'write': round(time.time() - t3)}}
    with (roles.FITS / 'runs.jsonl').open('a') as f:
        f.write(json.dumps(rec) + '\n')
    print(json.dumps({k: rec[k] for k in ('name', 'features', 'placebo_columns', 'fit_queries', 'train_rows',
                                          'eval_queries', 'peak_rss_gb', 'seconds')}), flush=True)
    return rec


def records():
    """name -> the last record of each fit in roles.FITS/runs.jsonl."""
    path = roles.FITS / 'runs.jsonl'
    return {r['name']: r for r in map(json.loads, path.read_text().splitlines())} if path.exists() else {}


def done(spec, data=None):
    """True if the fit of a normalized spec is done with this spec (and, given `data`, this data fingerprint);
    SystemExit if its file exists without a record, with another spec or another fingerprint (council.queue stops)."""
    if not (roles.FITS / f"{spec['name']}.parquet").exists():
        return False
    rec = records().get(spec['name'])
    if rec is None or rec.get('spec') != spec:
        raise SystemExit(f"{spec['name']}: a file exists without a record or with another spec; move it aside")
    if data is not None and rec.get('data') != data:
        raise SystemExit(f"{spec['name']}: done on other data than the queue's fingerprint; move it aside")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description='one council fit by a JSON spec (contract §3.1)')
    ap.add_argument('--spec', required=True, help='a JSON file with one spec')
    ap.add_argument('--stamp', help='JSON code stamp the fit must run with (set by council.queue)')
    ap.add_argument('--data', help='JSON data fingerprint the fit must run with (set by council.queue)')
    args = ap.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text())
    commit, dirty = git_head()
    try:
        run(spec, commit, json.loads(args.stamp) if args.stamp else None, dirty,
            json.loads(args.data) if args.data else None)
    except ValueError as e:
        raise SystemExit(f'council.fit: {e}') from None


if __name__ == '__main__':
    main(sys.argv[1:])
