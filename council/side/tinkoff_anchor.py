"""H8: Tinkoff, anchor 611 as the evaluation anchor — does BA - B differ between users like the Kaggle test and the
rest? (council/runs/side/tinkoff-611.md; night plan 22.10, hypothesis 9; report «Перенос», «Следующие шаги» п. 5).

Post-hoc on val-641 (docs/xfer-tinkoff.md): D = BA - B is about zero on the Kaggle test users and positive on the
others; the difference of the groups was never tested. Here the last train anchor of the dev series, 611, becomes the
evaluation anchor: B and BA of the xfer recipe are trained on the earlier train anchors (461, 491, 521, 551, 581; the
cap N, the training rows, the sidecars and the recipe of scripts/xfer_model, imported only) with both xfer seeds, and
scored on every candidate of every query of train-611. Groups: the query users of 611 that are in the Kaggle test user
list (static.duckdb table test_users: user ids only, no labels) and the rest.

Reads: the xfer train collections 461…611 (frames, open labels and targets of the train role), their agent sidecars,
the user id list of the Kaggle test. Never: val, holdout or kaggle collections and labels, anything of the council
broker. Writes: artifacts/side/tinkoff-611/<arm><seed>/ (report.json, scores.parquet, metrics.parquet) and
council/runs/side/tinkoff-611.json; nothing under artifacts/xfer (xm.fit / xm.fit_dir are not used).

Heavy: the fits run inside council.xfer.queue.heavy('side tinkoff-611', 'tinkoff') with check() before each fit; the
listing and mtime of artifacts/xfer and artifacts/task1 are taken once the lock is held and compared before it is
released (exit 3 on a change). A completed <arm><seed> with the same spec digest, side code and xfer code identity is
reused, so an interrupted run resumes.

Run as a script (from the repository root; -I keeps council/side off sys.path; the script path is what
`[c]ouncil[./]side` of the plan's ПРОВЕРКА-HEAVY pgrep
'[c]ouncil/xfer/run.py.*(queue|compute|fit-one)|[c]ouncil\\.(fit|queue|memory)|[c]ouncil[./]side' matches):
  .venv/bin/python -I council/side/tinkoff_anchor.py --dry
  .venv/bin/python -I council/side/tinkoff_anchor.py > /tmp/tlab-side-tinkoff-611.log 2>&1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402

from council import side as S  # noqa: E402

NAME = 'tinkoff-611'
DATASET = 'tinkoff'
SERIES = 'dev'                      # the xfer series whose train anchors are cut at EVAL_ANCHOR
EVAL_ANCHOR = 611
ROLE = 'train'                      # every anchor read here has the train role
ARMS = ('B', 'BA')
DRAWS = 2000
BOOT_SEED = 2026
FORMAT = 'side-tinkoff-611-v1'
VERDICTS = {'reproduced': 'воспроизводится: D_rest - D_kaggle > 0 на обоих зёрнах',
            'reversed': 'обратная: D_rest - D_kaggle < 0 на обоих зёрнах',
            'not distinguished': 'не различено'}


# ---------------------------------------------------------------- spec (no data)

def split_anchors(train_anchors, eval_anchor=EVAL_ANCHOR) -> list:
    """The train anchors strictly before eval_anchor; eval_anchor must be a train anchor and two earlier remain."""
    train = sorted(int(a) for a in train_anchors)
    if int(eval_anchor) not in train:
        raise S.Refused(f'{eval_anchor} is not a train anchor of {train}')
    earlier = [a for a in train if a < int(eval_anchor)]
    if len(earlier) < 2:
        raise S.Refused(f'fewer than two train anchors before {eval_anchor}')
    return earlier


def spec() -> dict:
    """Everything the run will do, from the adapter's constants and the xfer recipe (nothing read)."""
    from scripts import xfer_common as xc
    anchors = xc.adapter(DATASET).anchors()
    dev = anchors['series'][SERIES]
    train = split_anchors(dev['train'])
    return {'format': FORMAT, 'dataset': DATASET, 'series_cut': SERIES, 'train_anchors': train,
            'eval_anchor': EVAL_ANCHOR, 'eval_role': ROLE, 'cap_queries_per_anchor': anchors['N'], 'K': anchors['K'],
            'arms': list(ARMS), 'seeds': list(xc.SEEDS), 'recipe': dict(xc.RECIPE),
            'groups': 'query users of 611 in static.duckdb test_users (Kaggle test user ids) vs the rest',
            'bootstrap': {'draws': DRAWS, 'seed': BOOT_SEED, 'paired': 'xfer_common.bootstrap per group',
                          'difference': 'independent resampling within each group, D_rest - D_kaggle'},
            'decision': VERDICTS}


def spec_digest(s: dict) -> str:
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- statistics

def paired(reference: dict, alternative: dict, draws=DRAWS, seed=BOOT_SEED) -> dict:
    """mean(alternative - reference) with the paired bootstrap of xfer (xfer_common.bootstrap)."""
    from scripts import xfer_common as xc
    return xc.bootstrap(reference, alternative, draws=draws, seed=seed)


def difference(d_rest, d_kaggle, draws=DRAWS, seed=BOOT_SEED) -> dict:
    """mean(d_rest) - mean(d_kaggle), queries resampled within each group; linear 2.5/97.5 quantiles."""
    import numpy as np
    a, b = np.asarray(d_rest, dtype=float), np.asarray(d_kaggle, dtype=float)
    if not len(a) or not len(b):
        raise S.Refused('a group of queries is empty')
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for i in range(draws):
        means[i] = a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
    lo, hi = (float(x) for x in np.quantile(means, [0.025, 0.975], method='linear'))
    return {'mean': float(a.mean() - b.mean()), 'ci': [lo, hi], 'covers_zero': bool(lo <= 0 <= hi),
            'draws': draws, 'seed': seed}


def group_contrast(b: dict, ba: dict, kaggle_users, draws=DRAWS, seed=BOOT_SEED) -> dict:
    """D = BA - B per query (user_id -> metric), overall, per group and the difference of the groups."""
    if set(b) != set(ba):
        raise S.Refused('B and BA are not scored on the same queries')
    users = sorted(b)
    kag = {u for u in users if u in kaggle_users}
    rest = [u for u in users if u not in kag]
    kag = sorted(kag)
    out = {'queries': len(users), 'kaggle_like': len(kag), 'rest': len(rest),
           'overall': paired(b, ba, draws, seed),
           'B_mean': {'kaggle_like': _mean([b[u] for u in kag]), 'rest': _mean([b[u] for u in rest])}}
    out['D_kaggle_like'] = paired({u: b[u] for u in kag}, {u: ba[u] for u in kag}, draws, seed)
    out['D_rest'] = paired({u: b[u] for u in rest}, {u: ba[u] for u in rest}, draws, seed)
    out['D_rest_minus_D_kaggle'] = difference([ba[u] - b[u] for u in rest], [ba[u] - b[u] for u in kag], draws, seed)
    return out


def _mean(x):
    return float(sum(x) / len(x)) if x else None


def decide(per_seed: dict) -> str:
    """'reproduced' when the CI of D_rest - D_kaggle lies above 0 on every seed, 'reversed' below 0 on every seed,
    else 'not distinguished'."""
    cis = [c['D_rest_minus_D_kaggle']['ci'] for c in per_seed.values()]
    if cis and all(lo > 0 for lo, _ in cis):
        return 'reproduced'
    if cis and all(hi < 0 for _, hi in cis):
        return 'reversed'
    return 'not distinguished'


# ---------------------------------------------------------------- data (real run only)

_CTX = {}


def _context():
    """xm.Context('tinkoff'): committed prereg, base and agent set, code identity of the frozen xfer stamp."""
    if 'ctx' not in _CTX:
        from scripts import xfer_model as xm
        _CTX['ctx'] = xm.Context(DATASET)
    return _CTX['ctx']


def fit_eval(arm: str, seed: int, out: S.Out, s: dict) -> dict:
    """One fit of arm/seed on the train anchors before 611 and its per-query metric on train-611 (user -> value).
    A completed directory is reused only with the same spec digest, side code and xfer code identity."""
    import numpy as np
    from catboost import CatBoostClassifier
    from scripts import xfer_common as xc
    from scripts import xfer_model as xm
    key = f'{arm}{seed}'
    report_path = out.path(key, 'report.json')
    digest = spec_digest(s)
    if report_path.exists():
        rep = json.loads(report_path.read_text(encoding='utf-8'))
        if rep.get('status') == 'completed' and rep.get('spec_digest') == digest \
                and rep.get('code') == S.code_identity(__file__) and rep.get('xfer_code') == _context().code:
            m = xc.read_parquet(out.path(key, 'metrics.parquet'))
            return {int(u): float(v) for u, v in zip(m['user_id'], m['value'])}
    ctx = _context()
    if arm not in ARMS or int(seed) not in xc.SEEDS:
        raise S.Refused(f'{arm}{seed} is not an arm/seed of this run')
    for a in s['train_anchors'] + [s['eval_anchor']]:
        if ctx.role_of(a) != ROLE:
            raise S.Refused(f'anchor {a} is not a {ROLE} anchor')
    agent = arm != 'B'
    columns = list(ctx.columns) if agent else []
    t0 = time.monotonic()
    con = xm.connect()
    report = {'format': FORMAT, 'status': 'running', 'arm': arm, 'seed': int(seed), 'spec_digest': digest,
              'code': S.code_identity(__file__), 'xfer_code': ctx.code, 'started': S.now()}
    try:
        parts, populations = [], []
        for a in s['train_anchors']:
            block, population, _, _, _ = xm.training_block(ctx, con, SERIES, a, arm, seed)
            numbers, cats = xm.matrices(ctx, block, columns)
            parts.append((numbers, cats, block['label'].to_numpy(dtype=np.int8),
                          block['weight'].to_numpy(dtype=np.float64)))
            populations.append(population)
            del block
        numbers = np.ascontiguousarray(np.concatenate([p[0] for p in parts]))
        cats = np.concatenate([p[1] for p in parts])
        labels = np.concatenate([p[2] for p in parts])
        weights = np.concatenate([p[3] for p in parts])
        del parts
        t1 = time.monotonic()
        recipe = xm.recipe_for(seed)
        model = CatBoostClassifier(**recipe)
        model.fit(xm.make_pool(numbers, cats, ctx.numeric + columns, ctx.categorical, labels, weights))
        del numbers, cats, labels, weights
        if model.tree_count_ != recipe['iterations']:
            raise S.Refused('fixed-tree fit incomplete')
        t2 = time.monotonic()
        path = ctx.collection(ROLE, s['eval_anchor'])
        ctx.check_collection(path, ROLE)
        directory = None
        if agent:
            directory, side = ctx.sidecar(path)
            xm.check_sidecar_rows(con, path, directory, side)
        scores, counts, n = xm.score_rows(ctx, con, path, arm, seed, s['eval_anchor'], model, directory=directory)
        frame_labels, targets = xm.open_labels(path)
        values = xm.evaluate(ctx, scores, targets, frame_labels)
        import pandas as pd
        out.write_frame(scores.sort_values(xm.KEYS, kind='mergesort').reset_index(drop=True), key, 'scores.parquet')
        out.write_frame(pd.DataFrame({'user_id': list(values), 'value': list(values.values())}),
                        key, 'metrics.parquet')
        report.update(status='completed', training_populations=populations, eval_collection=path.name,
                      eval_rows=int(n), queries=len(values), metric=xm.mean(values),
                      agent_finite_eval={c: v / n for c, v in (counts or {}).items()} if agent and n else None,
                      seconds={'load': round(t1 - t0, 1), 'fit': round(t2 - t1, 1),
                               'score': round(time.monotonic() - t2, 1)}, peak_rss_gb=S.peak_rss_gb())
        return values
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}'[:2000])
        raise
    finally:
        con.close()
        out.write_json(report, key, 'report.json')


def kaggle_users() -> set:
    """User ids of the Kaggle test (static.duckdb, table test_users), opened read-only. Ids only, no labels."""
    import duckdb
    from scripts import xfer_common as xc
    con = duckdb.connect(str(xc.static_path(DATASET)), read_only=True)
    try:
        return {int(u) for (u,) in con.execute('SELECT user_id FROM test_users').fetchall()}
    finally:
        con.close()


# ---------------------------------------------------------------- run

def run(out: S.Out, s: dict, *, fit_eval_fn=fit_eval, users_fn=kaggle_users, check_fn=S.check, wait=True,
        heavy_kw=None, protected=S.PROTECTED, draws=DRAWS) -> dict:
    """Fits under the heavy lock (check before each), group contrasts per seed, the decision; the result goes to
    council/runs/side/tinkoff-611.json. The protected snapshot is taken once the lock is held and compared before it
    is released; SystemExit(PROTECTED_EXIT) when a protected tree changed."""
    t0 = time.time()
    values = {}
    with S.heavy_step(NAME, DATASET, out, wait=wait, **(heavy_kw or {})):
        before = S.protected_snapshot(protected)       # under the lock: a REES46 step waited for may have written
        for seed in s['seeds']:
            for arm in s['arms']:
                check_fn()
                values[(arm, seed)] = fit_eval_fn(arm, seed, out, s)
        users = users_fn()
        verdict = S.protected_verdict(before, protected)
    per_seed = {str(seed): group_contrast(values[('B', seed)], values[('BA', seed)], users, draws=draws)
                for seed in s['seeds']}
    decision = decide(per_seed)
    result = {'format': FORMAT, 'status': 'ok' if verdict['unchanged'] else 'refused', 'spec': s,
              'spec_digest': spec_digest(s), 'per_seed': per_seed, 'decision': decision,
              'decision_text': VERDICTS[decision], 'kaggle_users_listed': len(users), 'protected': verdict,
              'seconds': round(time.time() - t0, 1), 'peak_rss_gb': S.peak_rss_gb(),
              'code': S.code_identity(__file__), 'finished': S.now()}
    out.write_json(result, f'{NAME}.json', runs=True)
    if not verdict['unchanged']:
        raise SystemExit(S.PROTECTED_EXIT)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description='H8: Tinkoff anchor 611 as evaluation, B/BA x 2 seeds, groups of '
                                             'Kaggle test users and the rest (council/runs/side/tinkoff-611.md)')
    ap.add_argument('--dry', action='store_true', help='print the spec and paths; read no data, take no lock')
    ap.add_argument('--no-wait', action='store_true', help='refuse instead of waiting for the heavy lock')
    args = ap.parse_args(argv)
    s = spec()
    out = S.Out(NAME)
    if args.dry:
        S.print_json({'dry': True, 'spec': s, 'spec_digest': spec_digest(s), 'heavy': f'side {NAME}',
                      'outputs': [str(out.art), str(out.path(f'{NAME}.json', runs=True))],
                      'journal': str(out.journal), 'protected': [str(p) for p in S.PROTECTED],
                      'reads': ['artifacts/xfer/tinkoff/collections/train-{461..611}', 'their agent sidecars',
                                'artifacts/xfer/tinkoff/load/static.duckdb: test_users (read_only)']})
        return 0
    res = run(out, s, wait=not args.no_wait)
    S.print_json({k: res[k] for k in ('status', 'decision', 'decision_text', 'seconds', 'peak_rss_gb')})
    return 0


if __name__ == '__main__':
    sys.exit(main())
