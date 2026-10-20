"""Replication of task 1 on January-February 2020 (TASK1_PERIOD=2020), pre-registered in
task1/runs/replication-2020/spec.md; arms, seeds, the cap, the excluded anchors and the data hashes are frozen in
spec.json there.

The recipe of task1.final, with these differences:
- arms: the four of task1/runs/final.json, base_4src_d8 (four sources at depth 8, which separates the sources from
  the depth) and F0, F1, H+ of the grid (task1/runs/grid-2026-10-20);
- the fit pool keeps the first `cap` queries by user hash (exp._read): as many as the 2019 refit had;
- per-query metrics are kept per seed with the anchor; the primary comparison drops the excluded anchors, the
  robustness one keeps every evaluation day;
- extra tables come from SQL under git: DFS from task1.dfs with the 2019 selection, the agent's tables from its
  night log. `--prepare` computes them in the sandbox of task1.extra, which sees only events before the anchor.

Exclusion rule: a day is broken if its views, carts or purchases are below half of the median of the 7 days
centred on it (fewer at the edges of the data); anchor t is dropped if day t or t-1 is broken. The anchors it
drops are frozen in spec.json; the run stops if the database gives others.

The test is opened once. Before its log is started a preflight checks every input without reading a label: day and
extra tables of all days, the feature count of every arm, the same queries in both day directories, the queries of
the refit. While the test runs nothing about it is printed: an arm writes its per-query metrics to files and reports
its size, memory and time; the comparison is printed when every arm is done. A run that stopped before that goes on
with --resume (same code and spec by content hash) or, after a technical fix, starts over with --restart REASON:
the arms written so far move aside unread and the reason goes into the result.

Prepare (no labels read): TASK1_PERIOD=2020 .venv/bin/python -m task1.replicate --prepare
Memory rehearsal, a fit on the capped refit only: TASK1_PERIOD=2020 .venv/bin/python -m task1.replicate --rehearse
Check the path, fit on train and score val: TASK1_PERIOD=2020 .venv/bin/python -m task1.replicate --eval val --iterations 30 --seeds 1
Test, once: TASK1_PERIOD=2020 .venv/bin/python -m task1.replicate --eval test
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
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from task1 import dfs, exp, posthoc
from task1 import model as M
from task1 import period as P
from task1.extra import compute

SPEC = M.ROOT / 'task1/runs/replication-2020/spec.json'
GRID_2019 = posthoc.DIR / 'result.json'
AGENT_LOG = M.ROOT / 'task1/runs/agent_night20/log.jsonl'
STAMPED = [SPEC, dfs.SELECTION, AGENT_LOG, GRID_2019]  # besides the code under task1/; rule 3 reads the last one
OUT = P.ART / 'replication'
KEYS = ('anchor', 'user_id', 'product_id')
METRICS = ('ndcg', 'recall', 'purchase_ndcg', 'purchase_recall')


def broken_days():
    """Days of the database whose views, carts or purchases are below half of the median of the 7 days around."""
    con = duckdb.connect(str(P.DB), read_only=True)
    rows = con.execute("""
        WITH day AS (SELECT event_time::DATE d, count(*) FILTER (event_type = 'view') nv,
                            count(*) FILTER (event_type = 'cart') nc, count(*) FILTER (event_type = 'purchase') np
                     FROM events GROUP BY 1),
        loc AS (SELECT *, median(nv) OVER w mv, median(nc) OVER w mc, median(np) OVER w mp FROM day
                WINDOW w AS (ORDER BY d ROWS BETWEEN 3 PRECEDING AND 3 FOLLOWING))
        SELECT d, nv < 0.5 * mv OR nc < 0.5 * mc OR np < 0.5 * mp FROM loc ORDER BY d""").fetchall()
    con.close()
    if (rows[-1][0] - rows[0][0]).days + 1 != len(rows):
        raise SystemExit('the database misses whole days; the rule is defined on consecutive days')
    return [str(d) for d, broken in rows if broken]


def excluded(broken):
    """Anchors of the refit and test splits whose label day or last history day is broken."""
    b = {date.fromisoformat(d) for d in broken}
    return [str(t) for s in ('refit', 'test') for t in M.days(s) if t in b or t - timedelta(1) in b]


def fit_split(split):
    return 'refit' if split == 'test' else 'train'


def check_frozen(spec):
    """The splits and the sandbox limit of task1/period.py and the downloaded files are those spec.json froze."""
    if {k: list(v) for k, v in P.SPLITS.items()} != spec['splits'] or P.SANDBOX_TIMEOUT_S != spec['sandbox_timeout_s']:
        raise SystemExit('task1/period.py differs from the splits or the sandbox limit frozen in spec.json')
    for name, frozen in spec['data'].items():
        receipt = json.loads((P.RAW / name.replace('.csv.gz', '.download.json')).read_text())
        if receipt['sha256'] != frozen['sha256'] or receipt.get('status') != 'verified':
            raise SystemExit(f'{P.RAW / name} is not the verified file spec.json froze')


def prepare(spec, threads):
    """Extra tables of every arm for the refit and test days (refit covers train and val)."""
    selected = json.loads(dfs.SELECTION.read_text())['selected']
    if selected != spec['dfs_selected']:
        raise SystemExit('task1/runs/dfs-select.json differs from the DFS columns frozen in spec.json')
    agent = {r['name']: r['sql'] for r in map(json.loads, AGENT_LOG.read_text().splitlines()) if 'sql' in r}
    generated = dfs.queries()
    names = {n for a in spec['arms'] for n in a['config'].get('extra', [])}
    top = {n for n in names if n.endswith('_top')}
    if top:
        names |= set(dfs.SELECTABLE)
    days6 = M.ROOT / spec['days6']
    for n in sorted(names - top):
        miss = [d for s in ('refit', 'test') for d in M.days(s) if not (M.EXTRA / n / f'{d}.parquet').exists()]
        if miss:
            t0 = time.time()
            compute(n, generated[n] if n in generated else agent[n], days=miss, threads=threads, days_dir=days6)
            print(json.dumps({'table': n, 'days': len(miss), 'seconds': round(time.time() - t0)}), flush=True)
    if top:
        print(json.dumps({'materialised': dfs.materialize(spec['dfs_selected'])}), flush=True)


def columns(path):
    return duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").df().column_name.tolist()


def preflight(spec, split):
    """Check the inputs of every arm for the fit split and `split` without reading a label. Returns the number of
    queries the arms fit on (the cap, or every query of the fit split if it has fewer) and a digest of the input
    files (path, size, modification time) that a resumed test must find unchanged."""
    fit = fit_split(split)
    days = {s: [str(d) for d in M.days(s)] for s in (fit, split)}
    every = sorted(set(days[fit]) | set(days[split]))
    dirs, seen = [], {}

    def day_files(where, label):
        """Columns of a directory of day files; every day present, every file with the columns of the first."""
        if where not in seen:
            paths = [where / f'{x}.parquet' for x in every]
            miss = [f.stem for f in paths if not f.exists()]
            if miss:
                raise SystemExit(f'{label} lacks {len(miss)} days, first {miss[0]}')
            cols = columns(paths[0])
            drift = [f.stem for f in paths if columns(f) != cols]
            if drift:
                raise SystemExit(f'{label}: the columns of {len(drift)} days differ from {every[0]}, first {drift[0]}')
            seen[where] = cols, [(str(f.relative_to(M.ROOT)) if f.is_relative_to(M.ROOT) else str(f),
                                  f.stat().st_size, f.stat().st_mtime_ns) for f in paths]
        return list(seen[where][0])

    for arm in spec['arms']:
        cfg = exp.DEFAULT | arm['config']
        d = M.ROOT / cfg['days']
        dirs += [d] if d not in dirs else []
        cols = day_files(d, f"{arm['name']}: day tables {d}")
        for name in cfg['extra']:
            cols += [c for c in day_files(M.EXTRA / name, f"{arm['name']}: extra {name}") if c not in KEYS]
        n = len(M.base_features(pd.DataFrame(columns=cols), cfg['drop']))
        if n != spec['features'][arm['name']]:
            raise SystemExit(f"{arm['name']}: {n} features, spec.json expects {spec['features'][arm['name']]}")
    top = sorted({n for a in spec['arms'] for n in a['config'].get('extra', []) if n.endswith('_top')})
    got = sorted(c for n in top for c in columns(M.EXTRA / n / f'{every[0]}.parquet') if c not in KEYS)
    if top and got != sorted(spec['dfs_selected']):
        raise SystemExit('the materialised DFS columns differ from spec.json; run --prepare')
    queries = lambda d, s: f"SELECT DISTINCT anchor, user_id FROM read_parquet({[str(d / f'{x}.parquet') for x in days[s]]})"
    for s in (fit, split):
        for d in dirs[1:]:
            a, b = queries(dirs[0], s), queries(d, s)
            if duckdb.sql(f"SELECT count(*) FROM (({a} EXCEPT {b}) UNION ALL ({b} EXCEPT {a}))").fetchone()[0]:
                raise SystemExit(f'{dirs[0]} and {d} have different queries on {s} days')
    total = duckdb.sql(f'SELECT count(*) FROM ({queries(dirs[0], fit)})').fetchone()[0]
    inputs = hashlib.sha256(json.dumps(sorted(f for _, fs in seen.values() for f in fs)).encode()).hexdigest()
    return min(total, spec['cap']), inputs


def peak_gb():
    """Peak resident memory of this process so far (ru_maxrss is in bytes on macOS, in KiB on Linux)."""
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (2**30 if sys.platform == 'darwin' else 2**20), 1)


def fit_arm(arm, spec, split, seed, over, expect):
    """One model of an arm on the capped pool of the fit split of `split`."""
    c = exp.DEFAULT | arm['config'] | over | {'seed': seed[0], 'neg_seed': seed[1]}
    c['days'] = str(M.ROOT / c['days'])
    tr = exp.sample_train(exp._read(fit_split(split), c['days'], cap=spec['cap']), c)
    exp._cache.clear()  # the pool is the largest frame here; F1 and H+ need the room for their extra columns
    tr = exp.with_extra(tr, c['extra'])
    features = M.base_features(tr, c['drop'])
    if len(features) != spec['features'][arm['name']]:
        raise SystemExit(f"{arm['name']}: {len(features)} features, spec.json expects {spec['features'][arm['name']]}")
    queries, rows = int(tr.qid.nunique()), len(tr)
    if queries != expect:
        raise SystemExit(f"{arm['name']}: fits on {queries} queries, the preflight expects {expect}")
    model = exp.fit(tr, features, c)
    return model, features, {'fit_queries': queries, 'train_rows': rows}


def run_arm(arm, spec, split, seeds, over, expect):
    """Fit one arm per seed, score every day of `split`; per-query metrics per seed and a record without metrics."""
    t0, models, fits = time.time(), [], []
    for seed in seeds:
        m, features, rec = fit_arm(arm, spec, split, seed, over, expect)
        models.append(m)
        fits.append(rec)
    days = M.ROOT / (exp.DEFAULT | arm['config'])['days']
    parts = [[] for _ in models]
    for d in M.days(split):
        ev = exp.with_extra(exp.read_day(d, days), arm['config'].get('extra', []))
        for i, m in enumerate(models):
            score = M.predict(m, ev, features)
            pq = M.per_query(ev, score).join(M.per_query(ev, score, purchase=True).add_prefix('purchase_'), how='left')
            parts[i].append(pq.assign(anchor=str(d)))
        del ev
    rec = {'arm': arm['name'], 'features': len(features), 'fits': fits, 'peak_rss_gb': peak_gb(),
           'seconds': round(time.time() - t0)}
    return [pd.concat(p).sort_index() for p in parts], rec


def rehearse(spec, name, iterations):
    """Fit one arm on the capped refit with few trees, score the largest refit day with it and report the peak
    memory. No label of a test day is read: the preflight reads their schemas and queries only."""
    arm = next((a for a in spec['arms'] if a['name'] == name), None)
    if arm is None:
        raise SystemExit(f'no arm {name} in spec.json')
    expect, _ = preflight(spec, 'test')
    t0 = time.time()
    model, features, rec = fit_arm(arm, spec, 'test', spec['seeds'][0], {'iterations': iterations}, expect)
    days = M.ROOT / (exp.DEFAULT | arm['config'])['days']
    rows = {d: duckdb.sql(f"SELECT count(*) FROM read_parquet('{days / f'{d}.parquet'}')").fetchone()[0]
            for d in M.days('refit')}
    big = max(rows, key=rows.get)
    M.predict(model, exp.with_extra(exp.read_day(big, days), arm['config'].get('extra', [])), features)
    print(json.dumps({'rehearse': name, 'iterations': iterations, 'features': len(features), **rec,
                      'scored_day': str(big), 'scored_rows': rows[big], 'peak_rss_gb': peak_gb(),
                      'seconds': round(time.time() - t0)}), flush=True)


def stamp(inputs):
    """Content hashes of what the results depend on: the code under task1/, the frozen spec, the DFS selection, the
    agent log and the 2019 grid result, all committed; the digest of the input files; the library versions."""
    files = sorted((M.ROOT / 'task1').glob('*.py')) + STAMPED
    rel = [str(f.relative_to(M.ROOT)) for f in files]
    missing = [r for r, f in zip(rel, files) if not f.exists()]
    if missing:
        raise SystemExit(f'missing {missing}; the result of the 2019 grid is committed before the test')
    dirty = subprocess.run(['git', 'status', '--porcelain', '--', *rel], cwd=M.ROOT, capture_output=True, text=True,
                           check=True).stdout
    if dirty:
        raise SystemExit(f'uncommitted changes; the test runs only with committed code and spec:\n{dirty}')
    return {'files': {r: hashlib.sha256(f.read_bytes()).hexdigest() for r, f in zip(rel, files)}, 'inputs': inputs,
            'libs': {m: importlib.metadata.version(m) for m in ('duckdb', 'catboost', 'numpy', 'pandas')}}


def lock_test():
    """An exclusive lock on OUT/test.lock, held while this process lives: a second test process stops."""
    import fcntl  # POSIX; the replication runs on macOS
    handle = open(OUT / 'test.lock', 'w')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('another test process is running') from None
    return handle


def open_test(resume, restart, inputs):
    """Append a start, resume or restart to the test log; refuse a second test and a resume with other code or
    inputs."""
    log_path = OUT / 'test.started'
    if (OUT / 'test.json').exists():
        raise SystemExit(f"the test was already evaluated: {OUT / 'test.json'}")
    log = [json.loads(x) for x in log_path.read_text().splitlines()] if log_path.exists() else []
    now = stamp(inputs)
    if not log:
        if resume or restart:
            raise SystemExit('no test run to resume or restart')
        if list(OUT.glob('test_*')):
            raise SystemExit(f'{OUT} holds test files without a test log')
        event = {'event': 'start'}
    elif resume:
        if now != log[-1]['stamp']:
            raise SystemExit('--resume needs the code, spec and inputs the run started with; after a fix use --restart REASON')
        event = {'event': 'resume'}
    elif restart:
        aside = OUT / f'aborted-{len(log)}'
        aside.mkdir()
        for f in OUT.glob('test_*'):
            f.rename(aside / f.name)
        event = {'event': 'restart', 'reason': restart, 'moved_to': aside.name}
    else:
        raise SystemExit(f'a test run was started ({log_path}): --resume continues it, --restart REASON starts it over')
    log.append(event | {'stamp': now, 'at': time.strftime('%Y-%m-%d %H:%M:%S')})
    write(log_path, ''.join(json.dumps(e) + '\n' for e in log))
    return log


def write(path, text):
    tmp = path.with_name(f'.{path.name}.tmp')
    tmp.write_text(text)
    os.replace(tmp, path)


def write_parquet(frame, path):
    tmp = path.with_name(f'.{path.name}.tmp')
    duckdb.sql(f"COPY (SELECT * FROM frame) TO '{tmp}' (FORMAT PARQUET)")
    os.replace(tmp, path)


def compare(runs, anchors, grid_2019):
    """Paired bootstraps over the queries of `anchors` (metrics averaged over seeds) and the rules of the spec."""
    keep = {a: [r[r.anchor.isin(anchors)] for r in rs] for a, rs in runs.items()}
    seed = {a: [r.ndcg for r in rs] for a, rs in keep.items()}
    mean = {a: sum(s) / len(s) for a, s in seed.items()}
    for a, m in mean.items():
        if not m.index.equals(mean['base'].index):
            raise SystemExit(f'arm {a} differs from base in queries')
    diff = lambda ref, new: tuple(float(x) for x in M.bootstrap_diff(ref, new))
    raw = {'base-base_4src_d8': diff(mean['base_4src_d8'], mean['base']),
           'agent-base': diff(mean['base'], mean['agent']), 'dfs-base': diff(mean['base'], mean['dfs']),
           'base-base_4src': diff(mean['base_4src'], mean['base']),
           'base_4src_d8-base_4src': diff(mean['base_4src'], mean['base_4src_d8'])}
    grid = {'H-F0': diff(mean['F0'], mean['base']), 'F1-H': diff(mean['base'], mean['F1']),
            'Hp-H_by_seed': [diff(h, p) for h, p in zip(seed['base'], seed['Hp'])],
            'R_F1': posthoc.ratio(mean['F0'], mean['F1'], mean['base'])}
    _, lo, hi = raw['base-base_4src_d8']
    rules = {'candidates': 'повторён' if lo > 0 else 'опровергнут' if hi < 0 else 'не повторён: CI накрывает 0'}
    for a in ('agent', 'dfs'):
        _, lo, hi = raw[f'{a}-base']
        rules[a] = ('опровергнут: прирост с CI > 0' if lo > 0 else 'повторён: прирост от +0.0008 исключён'
                    if hi < 0.0008 else 'не повторён: CI доходит до +0.0008')
    rules['grid'] = posthoc.verdict(grid)
    if grid_2019:
        rules['grid_same_as_2019'] = rules['grid'] == grid_2019
    r5 = lambda t: [round(x, 5) for x in t]
    metrics = {a: {m: round(float(pd.concat([r[m] for r in rs], axis=1).mean(axis=1).mean()), 5)
                   for m in METRICS if m in rs[0]} for a, rs in keep.items()}
    return {'anchors': len(anchors), 'queries': len(mean['base']), 'metrics': metrics,
            'ndcg_by_seed': {a: [round(float(s.mean()), 5) for s in ss] for a, ss in seed.items()},
            'diff': {k: r5(v) for k, v in raw.items()},
            'grid': {k: [r5(x) for x in v] if k == 'Hp-H_by_seed' else r5(v) for k, v in grid.items()},
            'rules': rules}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prepare', action='store_true', help='compute the extra tables for refit and test days')
    ap.add_argument('--rehearse', nargs='?', const='Hp', metavar='ARM',
                    help='fit one arm (default Hp) on the capped refit, --iterations trees (default 30); peak memory')
    ap.add_argument('--eval', choices=['val', 'test'])
    ap.add_argument('--resume', action='store_true', help='test only: continue a stopped run with the same code and spec')
    ap.add_argument('--restart', metavar='REASON', help='test only: start a stopped run over after a technical fix')
    ap.add_argument('--iterations', type=int, help='val and rehearsal only: fewer trees')
    ap.add_argument('--seeds', type=int, help='val only: the first N seed pairs')
    ap.add_argument('--threads', type=int, default=8, help='sandbox threads for --prepare')
    args = ap.parse_args()
    if P.PERIOD != '2020':
        raise SystemExit('the replication runs with TASK1_PERIOD=2020')
    test = args.eval == 'test'
    if test and (args.iterations or args.seeds):
        raise SystemExit('the test runs with the frozen spec only')
    if not test and (args.resume or args.restart):
        raise SystemExit('--resume and --restart belong to the test')
    spec = json.loads(SPEC.read_text())
    check_frozen(spec)
    if args.prepare:
        prepare(spec, args.threads)
    if args.rehearse:
        rehearse(spec, args.rehearse, args.iterations or 30)
    if not args.eval:
        return
    broken = broken_days()
    if excluded(broken) != spec['excluded']:
        raise SystemExit(f'the exclusion rule drops {excluded(broken)}, spec.json froze {spec["excluded"]}')
    over = {'iterations': args.iterations} if args.iterations else {}
    seeds = spec['seeds'][:args.seeds] if args.seeds else spec['seeds']
    expect, inputs = preflight(spec, args.eval)
    OUT.mkdir(parents=True, exist_ok=True)
    lock = lock_test() if test else None
    log = open_test(args.resume, args.restart, inputs) if test else None
    runs, info = {}, []
    for arm in spec['arms']:
        files = [OUT / f"{args.eval}_{arm['name']}_s{i}.parquet" for i in range(len(seeds))]
        done = OUT / f"{args.eval}_{arm['name']}.json"  # written after the arm's parquet files
        if test and done.exists():
            runs[arm['name']] = [duckdb.sql(f"SELECT * FROM '{f}'").df().set_index('qid') for f in files]
            rec = json.loads(done.read_text()) | {'resumed': True}
        else:
            runs[arm['name']], rec = run_arm(arm, spec, args.eval, seeds, over, expect)
            for f, r in zip(files, runs[arm['name']]):
                write_parquet(r.reset_index(), f)
            write(done, json.dumps(rec) + '\n')
        info.append(rec)
        shown = rec if test else rec | {'ndcg_by_seed': [round(float(r.ndcg.mean()), 5) for r in runs[arm['name']]]}
        print(json.dumps(shown), flush=True)
    grid_2019 = json.loads(GRID_2019.read_text())['grid']['verdict'] if test or GRID_2019.exists() else None
    days = [str(d) for d in M.days(args.eval)]
    res = {'spec': spec, 'run': {'eval': args.eval, 'over': over, 'seeds': seeds, 'log': log}, 'broken_days': broken,
           'fit_queries': expect, 'arms': info,
           'primary': compare(runs, [d for d in days if d not in spec['excluded']], grid_2019),
           'all_days': compare(runs, days, grid_2019), 'grid_2019': grid_2019}
    write(OUT / f'{args.eval}.json', json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({k: res[k] for k in ('primary', 'all_days')}, indent=1, ensure_ascii=False))
    del lock


if __name__ == '__main__':
    main()
