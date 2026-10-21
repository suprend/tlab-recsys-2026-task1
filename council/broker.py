"""The only reader of the per-query metrics of council fits, with the gates of the contract (§3.2).

Every read is checked against the spec in the fit's record (roles.FITS/runs.jsonl), demands that all fits read
together have the same queries, and is logged to roles.RUNS/reads.jsonl (what, when, which fits) before the values are
returned. A read that fails a check returns nothing and logs nothing.

  y_select(names)      S0-select (half B of S0), fits T_fit -> S0; any number of reads
  noise_explore(names) S0-explore (half A), the two noise fits of §4.0 (H+r, plan, roles.NOISE_SEEDS); one read
  c_val(names)         C_val (train -> val, full_val); only with selection.json committed; one read; logs the
                       sha256 of selection.json
  c_test(names)        C_test (refit -> test, full_test); with a line `approved: <quote with «да»>` in
                       test-approved.md, C_val read, selection.json committed and unchanged since C_val, and the
                       marker test.started; primary=True leaves out roles.TEST_EXCLUDED
  start_test()         writes the marker test.started under the same gates (the fits of the test refuse without it)
  path_check(name)     the path check of §3.1 against pl20_Hp_s0: the largest absolute difference per metric only

Each returns a DataFrame indexed by qid with one column per fit (c_test also with `anchor`).
"""
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

import duckdb
import pandas as pd

from council import roles
from task1 import exp

METRICS = ('ndcg', 'recall', 'purchase_ndcg', 'purchase_recall')
PATH_REF = 'pl20_Hp_s0'
PATH_TOL = 1e-9


def git(*args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def head():
    try:
        return git('rev-parse', 'HEAD', cwd=roles.ROOT).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def committed(path):
    """True if `path` exists, is in HEAD of its repository and has no uncommitted changes."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        top = Path(git('rev-parse', '--show-toplevel', cwd=path.parent).strip()).resolve()
        rel = path.resolve().relative_to(top).as_posix()
        if git('status', '--porcelain', '--', rel, cwd=top).strip():
            return False
        git('cat-file', '-e', f'HEAD:{rel}', cwd=top)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False
    return True


def reads():
    path = roles.RUNS / 'reads.jsonl'
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def log(what, names, **extra):
    roles.RUNS.mkdir(parents=True, exist_ok=True)
    rec = {'what': what, 'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'names': list(names), 'commit': head()} | extra
    with (roles.RUNS / 'reads.jsonl').open('a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def once(what):
    if any(r['what'] == what for r in reads()):
        raise PermissionError(f'{what} has been read already ({roles.RUNS / "reads.jsonl"}); it is read once')


def records():
    path = roles.FITS / 'runs.jsonl'
    return {r['name']: r for r in map(json.loads, path.read_text().splitlines())} if path.exists() else {}


def specs(names, allowed, what):
    """name -> spec of each fit; PermissionError if a fit is missing or its spec is not allowed for this read."""
    names = list(names)
    if not names or len(set(names)) != len(names):
        raise ValueError(f'{what}: a non-empty list of distinct fit names')
    recs, out = records(), {}
    for n in names:
        if n not in recs or not (roles.FITS / f'{n}.parquet').exists():
            raise PermissionError(f'{what}: fit {n} is not done (file and record)')
        s = recs[n]['spec']
        if not all(s.get(k) == v for k, v in allowed.items()):
            raise PermissionError(f'{what}: fit {n} has {[(k, s.get(k)) for k in allowed]}; this read takes {allowed}')
        out[n] = s
    return out


def frame(names, metric, half=None):
    """qid x fit of one metric, with anchor and half; ValueError unless every fit has the same queries."""
    if metric not in METRICS:
        raise ValueError(f'metric {metric!r} not in {METRICS}')
    ms = [duckdb.sql(f"SELECT * FROM '{roles.FITS / n}.parquet'").df().set_index('qid').sort_index() for n in names]
    base = ms[0]
    for n, m in zip(names, ms):
        if not m.index.is_unique or not m.index.equals(base.index):
            raise ValueError(f'fit {n} differs in queries from {names[0]}')
        if not (m.anchor.astype(str).equals(base.anchor.astype(str)) and m.half.astype(str).equals(base.half.astype(str))):
            raise ValueError(f'fit {n} differs in anchors or halves from {names[0]}')
        if half is not None and (m.half != half).any():
            raise ValueError(f'fit {n} holds queries outside half {half}')
        if metric in ('ndcg', 'recall') and m[metric].isna().any():
            raise ValueError(f'fit {n}: {metric} is missing for some queries')
    out = pd.DataFrame({n: m[metric] for n, m in zip(names, ms)}, index=base.index)
    out.columns.name = None
    return out, base.anchor.astype(str)


def y_select(names, metric='ndcg'):
    """S0-select: fits T_fit -> S0 that kept half B (plan, confirmation, noise on S0-select)."""
    names = list(names)
    specs(names, {'fit': 'T_fit', 'eval': 'S0', 'keep_half': roles.SELECT}, 'y_select')
    out, _ = frame(names, metric, roles.SELECT)
    log('y_select', names, metric=metric, queries=len(out))
    return out


def noise_explore(names, metric='ndcg'):
    """S0-explore, once: the two noise fits of §4.0, H+r in plan, T_fit -> S0 half A, seeds roles.NOISE_SEEDS."""
    names = list(names)
    once('noise_explore')
    s = specs(names, {'fit': 'T_fit', 'eval': 'S0', 'keep_half': roles.EXPLORE, 'recipe': 'plan',
                      'extra': list(roles.HPLUS), 'placebo': None}, 'noise_explore')
    if sorted((x['seed'], x['neg_seed']) for x in s.values()) != sorted(map(tuple, roles.NOISE_SEEDS)):
        raise PermissionError(f'noise_explore: the two fits must have the seeds {roles.NOISE_SEEDS}')
    out, _ = frame(names, metric, roles.EXPLORE)
    log('noise_explore', names, metric=metric, queries=len(out))
    return out


def selection_committed(what):
    sel = roles.RUNS / 'selection.json'
    if not committed(sel):
        raise PermissionError(f'{what}: {sel} must exist, be in HEAD and have no uncommitted changes')


APPROVED = re.compile(r'^approved:[ \t]*(\S.*?)[ \t]*$', re.M)
YES = re.compile(r'(?i)(?<!\w)да(?!\w)')


def approved(what):
    """The owner's quote: a line `approved: <verbatim quote from the chat>` whose quote has the word «да»; a
    placeholder in angle brackets does not count."""
    path = roles.RUNS / 'test-approved.md'
    quotes = APPROVED.findall(path.read_text(encoding='utf-8')) if path.exists() else []
    if not any(YES.search(q) and not re.search(r'<[^>]*>', q) for q in quotes):
        raise PermissionError(f"{what}: {path} needs a line `approved: <the owner's verbatim quote with «да»>`")


def selection_sha():
    return hashlib.sha256((roles.RUNS / 'selection.json').read_bytes()).hexdigest()


def selection_as_read(what):
    """C_val must have been read, and selection.json must be byte for byte what it was at that read."""
    val = [r for r in reads() if r['what'] == 'c_val']
    if not val:
        raise PermissionError(f'{what}: C_val has not been read; the test comes after it')
    if selection_sha() != val[-1].get('selection_sha256'):
        raise PermissionError(f'{what}: selection.json differs from the one C_val was read with')


def c_val(names, metric='ndcg'):
    """C_val, once, after selection.json is committed: every arm of §4.5 in one call (train -> val, full_val)."""
    names = list(names)
    once('c_val')
    selection_committed('c_val')
    specs(names, {'fit': 'train', 'eval': 'val', 'keep_half': None, 'recipe': 'full_val'}, 'c_val')
    out, _ = frame(names, metric)
    log('c_val', names, metric=metric, queries=len(out), selection_sha256=selection_sha())
    return out


def start_test():
    """The marker test.started, written once before the first fit of the test, after the owner's «да»."""
    marker = roles.RUNS / 'test.started'
    approved('start_test')
    selection_committed('start_test')
    selection_as_read('start_test')
    if marker.exists():
        raise PermissionError(f'{marker} exists already')
    rec = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'commit': head()}
    marker.write_text(json.dumps(rec) + '\n')
    log('test.started', [])
    return rec


def c_test(names, metric='ndcg', primary=True):
    """C_test (refit -> test, full_test): qid x fit with `anchor`; primary=True leaves out roles.TEST_EXCLUDED."""
    names = list(names)
    approved('c_test')
    selection_committed('c_test')
    selection_as_read('c_test')
    if not (roles.RUNS / 'test.started').exists():
        raise PermissionError(f"c_test: the marker {roles.RUNS / 'test.started'} is missing")
    specs(names, {'fit': 'refit', 'eval': 'test', 'keep_half': None, 'recipe': 'full_test'}, 'c_test')
    out, anchor = frame(names, metric)
    out.insert(0, 'anchor', anchor)
    if primary:
        out = out[~out.anchor.isin(roles.TEST_EXCLUDED)]
    log('c_test', names, metric=metric, primary=primary, queries=len(out))
    return out


def path_check(name, ref=PATH_REF):
    """§3.1: the fit `name` (fit.path_spec) against the placebo run `ref` of task1 on the same queries. Returns the
    largest absolute difference per metric and ok (every one <= 1e-9, same queries and halves); no metric itself."""
    specs([name], {'fit': 'train', 'eval': 'val', 'keep_half': None, 'recipe': 'full_val', 'seed': 2026,
                   'neg_seed': 0, 'extra': list(roles.HPLUS), 'placebo': None}, 'path_check')
    a = duckdb.sql(f"SELECT * FROM '{roles.FITS / name}.parquet'").df().set_index('qid').sort_index()
    b = duckdb.sql(f"SELECT * FROM '{exp.OUT / ref}.parquet'").df().set_index('qid').sort_index()
    same = a.index.equals(b.index) and a.half.astype(str).equals(b.half.astype(str))
    diff = {}
    if same:
        for c in METRICS:
            x, y = a[c].to_numpy(dtype=float), b[c].to_numpy(dtype=float)
            if not ((x != x) == (y != y)).all():
                diff[c] = float('inf')
            else:
                d = abs(x - y)[x == x]
                diff[c] = float(d.max()) if len(d) else 0.0
    res = {'name': name, 'ref': ref, 'queries': [len(a), len(b)], 'same_queries': bool(same), 'max_abs_diff': diff,
           'ok': bool(same) and all(v <= PATH_TOL for v in diff.values())}
    log('path_check', [name, ref], ok=res['ok'])
    return res
