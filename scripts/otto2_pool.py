"""OTTO-2: BA rankers trained on labelled sessions pooled over several folds (exploratory, not the contract).

``.venv/bin/python -I scripts/otto2_pool.py fit --name NAME --source K:N [--source K:N ...]
[--seed 2026] [--negatives N] [--iterations N] [--depth N] [--learning-rate X]``
    Per source fold K (2, 3, 4): the first N labelled sessions per type in sha256 order
    among the sessions the BA sidecar of that collection covers (N = ``all`` for every one);
    training rows as ``otto_model.training_rows`` (positives and up to ``negatives``
    negatives); one YetiRank model per type over all sources (groups keyed by fold and
    session). F4 labels only through ``read_sealed(..., 'final')`` (``fold_labels``).
``.venv/bin/python -I scripts/otto2_pool.py evaluate --name NAME --fold 3|5``
    Top-20 per type with the Pop top-up (``otto_model.score_population``): on F3 the dev
    population with metrics (refused when F3 was a training source); on F5 every test
    session, ranked lists only.

Everything is written under ``artifacts/otto/otto2-pool/<name>/``; OTTO-1 receipts, fits and
gates are not changed. The committed prereg context gives features, frozen agent columns,
recipe and sidecars; N_t and the training folds are what changes here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts import otto_common as oc  # noqa: E402
from scripts import otto_model as om  # noqa: E402

OUTPUT_ROOT = 'otto2-pool'
ARM = 'BA'
REPORT = 'report.json'
FOLD_KEY = 10**10                       # group id = fold * FOLD_KEY + session (sessions repeat across folds)
CHUNK = 50_000                          # training sessions per training_rows query


def output_root(name):
    return oc.artifacts_dir()/OUTPUT_ROOT/oc.output_name(name)


def parse_source(text):
    fold, _, n = text.partition(':')
    fold = int(fold)
    oc.require(fold in (2, 3, 4), f'Training folds are 2, 3, 4: got {fold}')
    return fold, (None if n in ('', 'all') else int(n))


def chosen_sessions(con, covered, n):
    """First n labelled sessions per type in sha256 order among ``covered`` (all of them when n is None)."""
    om.register_sessions(con, 'covered', covered)
    limit = '' if n is None else f'LIMIT {int(n)}'
    out = {}
    for j, t in enumerate(oc.TYPES):
        rows = con.execute(f"""SELECT session FROM (SELECT DISTINCT session FROM lab WHERE tc = {j})
            SEMI JOIN covered USING (session)
            ORDER BY {oc.ORDER_SQL.format(column='session')}, session {limit}""").fetchall()
        out[t] = [int(r[0]) for r in rows]
    return out


def fold_views(ctx, con, k):
    """Labels ``lab`` and the BA frame ``fr`` of fold k on ``con``; returns (collection, labels source, columns)."""
    collection = ctx.collection(k)
    labels_path, labels_source = om.fold_labels(ctx, k, 'final' if k == 4 else None)
    om.labels_view(con, labels_path)
    _, agent = om.arm_view(con, ctx, collection, ARM)
    return collection, labels_source, list(ctx.features) + agent


def training_block(ctx, con, k, t, sessions, columns):
    """Training rows of type t over ``sessions`` of fold k in chunks of CHUNK sessions (float32 x, int8 y, groups)."""
    import numpy as np
    xs, ys, gs, dropped = [], [], [], 0
    for start in range(0, len(sessions), CHUNK):
        block, lost = om.training_rows(con, 'fr', 'lab', t, sessions[start:start+CHUNK], columns, ctx.negatives)
        xs.append(om.feature_matrix(block, columns))
        ys.append(block['label'].to_numpy(dtype=np.int8))
        gs.append(block['session'].to_numpy(dtype=np.int64) + k*FOLD_KEY)
        dropped += int(lost)
        del block
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(gs), dropped


def fit(name, sources, seed=oc.SEEDS[0], negatives=None, recipe=None):
    """One model per type over the pooled sources; one type in memory at a time, sources read in chunks."""
    import numpy as np
    from catboost import CatBoost, Pool
    folds = [k for k, _ in sources]
    oc.require(len(set(folds)) == len(folds), f'Each source fold once: got {folds}')
    oc.require(all(n is not None and n <= oc.N_T for k, n in sources if k == 2),
               f'F2 sidecars cover the first {oc.N_T} labelled sessions per type only: give 2:N with N <= {oc.N_T}')
    sources = sorted(sources)
    ctx = om.Context.contract()
    output = oc.new_output(output_root(name))
    started = time.monotonic()
    report = dict(format='otto2-pool-fit-v1', status='running', arm=ARM, seed=int(seed),
                  sources=[dict(fold=k, n=n) for k, n in sources], prereg_sha256=ctx.prereg_sha256,
                  set_digest=ctx.set_digest, code=oc.code_identity()['files'],
                  script_sha256=oc.sha256_file(Path(__file__)), created_utc=oc.utc_now())
    try:
        if negatives is not None:
            ctx.negatives = int(negatives)
        ctx.recipe_overrides.update(recipe or {})
        report.update(recipe=ctx.recipe(seed), negatives=ctx.negatives, chunk=CHUNK)
        chosen, columns = {}, None
        for k, n in sources:
            con = om.connect(ctx)
            try:
                collection, labels_source, cols = fold_views(ctx, con, k)
                oc.require(columns is None or cols == columns, 'Sources differ in columns')
                columns = cols
                record = om.ba_frame(ctx, collection)
                oc.require(record is not None, f'No BA frame for {collection.name}')
                chosen[k] = chosen_sessions(con, record['sessions'], n)
            finally:
                con.close()
            report.setdefault('training', []).append(dict(
                fold=k, collection=collection.name, labels=labels_source,
                per_type={t: dict(sessions=len(chosen[k][t]), sessions_digest=oc.canonical_digest(chosen[k][t]))
                          for t in oc.TYPES}))
        report['features'] = dict(base=list(ctx.features), agent=columns[len(ctx.features):])
        files = {}
        for t in oc.TYPES:
            parts = []
            for (k, _), record in zip(sources, report['training']):
                con = om.connect(ctx)
                try:
                    fold_views(ctx, con, k)
                    x, y, g, dropped = training_block(ctx, con, k, t, chosen[k][t], columns)
                finally:
                    con.close()
                record['per_type'][t].update(dropped=dropped, rows=int(len(y)), positives=int(y.sum()))
                parts.append((x, y, g))
            x = np.concatenate([p[0] for p in parts])
            y = np.concatenate([p[1] for p in parts])
            g = np.concatenate([p[2] for p in parts])
            del parts
            oc.require(int(np.count_nonzero(np.diff(g))) + 1 == len(np.unique(g)), f'{t}: groups are not contiguous')
            tick = time.monotonic()
            model = CatBoost(ctx.recipe(seed))
            model.fit(Pool(x, label=y, group_id=g, feature_names=columns), verbose=False)
            oc.require(model.tree_count_ == ctx.recipe(seed)['iterations'], f'{t}: fit incomplete')
            path = output/om.MODEL_FILE.format(type=t)
            model.save_model(str(path))
            files[path.name] = oc.sha256_file(path)
            report.setdefault('fit', {})[t] = dict(rows=int(len(y)), groups=int(len(np.unique(g))),
                                                   seconds=round(time.monotonic()-tick, 3))
            del x, y, g, model
        report.update(files=files, status='completed')
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        raise
    finally:
        ctx.close()
        report['seconds'] = round(time.monotonic()-started, 3)
        oc.atomic_json(output/REPORT, report)
    return report


class Average:
    """Mean raw score of several models of one type (a seed or data ensemble)."""

    def __init__(self, models):
        self.models = models

    def predict(self, pool, **kwargs):
        import numpy as np
        return np.mean([np.asarray(m.predict(pool, **kwargs), dtype=np.float64) for m in self.models], axis=0)


def model_report(directory, prereg_sha256):
    """Fit report of an otto2-pool, otto2-dev or OTTO-1 BA fit under this prereg, after its model-file digests."""
    directory = Path(directory)
    report = oc.read_json(directory/REPORT)
    oc.require(report.get('status') == 'completed', f'Fit {directory} not completed')
    oc.require(report.get('arm') == ARM, f'Fit {directory} is {report.get("arm")}, not {ARM}')
    oc.require(report.get('prereg_sha256') == prereg_sha256, f'Fit {directory} ran under another prereg')
    for file, digest in report['files'].items():
        oc.require(oc.sha256_file(directory/file) == digest, f'Model file changed: {directory/file}')
    folds = [s['fold'] for s in report['sources']] if 'sources' in report else [report['train_fold']]
    return report, folds


def evaluate(name, fold, model_dirs=None, batch=None):
    root = output_root(name)
    model_dirs = [Path(d) for d in (model_dirs or [root])]
    oc.require(len({d.resolve() for d in model_dirs}) == len(model_dirs), 'Each fit directory once')
    ctx = om.Context.contract()
    reports = [model_report(d, ctx.prereg_sha256) for d in model_dirs]
    fold = int(fold)
    oc.require(fold in (3, 5), 'Evaluation folds are 3 (dev population) and 5 (Kaggle)')
    oc.require(fold != 3 or all(3 not in folds for _, folds in reports),
               'F3 was a training source: its dev population is not an evaluation set')
    agents = {json.dumps(r['features']) for r, _ in reports}
    oc.require(len(agents) == 1, 'The models differ in features')
    fit_report = reports[0][0]
    seed = fit_report['seed']
    output = oc.new_output(root/f'eval-F{fold}')
    started = time.monotonic()
    report = dict(format='otto2-pool-eval-v1', status='running', fold=fold,
                  models={om.rel(d): oc.sha256_file(d/REPORT) for d in model_dirs}, created_utc=oc.utc_now())
    parts = output/'parts'
    con = om.connect(ctx)
    try:
        collection = ctx.collection(fold)
        population = oc.read_population(collection) if fold == 3 else om.collection_sessions(con, collection)
        om.require_ba_coverage(ctx, collection, population, 'population')
        report['collection'] = collection.name
        report['population'] = dict(n=len(population), digest=oc.sessions_digest(population))
        report['pop'] = om.make_pop(ctx, collection, output/om.POP_FILE)
        _, agent = om.arm_view(con, ctx, collection, ARM)
        oc.require(agent == fit_report['features']['agent'], 'Agent columns differ from the fit')
        columns = list(ctx.features) + agent
        oc.require(columns[:len(ctx.features)] == fit_report['features']['base'], 'Base features differ from the fit')
        om.pop_view(con, output/om.POP_FILE)
        loaded = [om.load_models(d, r) for d, (r, _) in zip(model_dirs, reports)]
        models = {t: Average([m[t] for m in loaded]) for t in oc.TYPES}
        parts.mkdir()

        def sink(b, lists):
            oc.write_parquet(lists, parts/f'part-{b:06d}.parquet')
        stats = om.score_population(ctx, con, 'fr', population, models, columns, agent, ARM, seed, fold, 'popv', sink,
                                    batch=batch)
        con.execute(f"""COPY (SELECT session, {om.type_name_sql()} AS type, aid, rank FROM
            read_parquet({om.sql_str(parts/'*.parquet')}) ORDER BY session, tc, rank)
            TO {om.sql_str(output/om.RANKED_FILE)} (FORMAT parquet)""")
        shutil.rmtree(parts)
        report.update(rows=stats['rows'], finite=stats['finite'], topped_sessions=stats['topped'],
                      short_lists=stats['short'],
                      ranked=dict(file=om.RANKED_FILE, sha256=oc.sha256_file(output/om.RANKED_FILE)))
        if fold == 3:
            labels_path = collection/oc.LABELS_FILE
            value = oc.metric(output/om.RANKED_FILE, labels_path, sessions=population, threads=ctx.threads)
            report.update(recall=value['recall'], score=value['score'])
            om.register_sessions(con, 'ceiling_population', population)
            report['ceiling'] = om.ceiling(con, 'fr', labels_path, 'ceiling_population')
        report['status'] = 'completed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        raise
    finally:
        con.close()
        ctx.close()
        shutil.rmtree(parts, ignore_errors=True)
        report['seconds'] = round(time.monotonic()-started, 3)
        oc.atomic_json(output/REPORT, report)
    return report


def main(argv=None):
    oc.isolated()
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    f = sub.add_parser('fit')
    f.add_argument('--name', required=True)
    f.add_argument('--source', action='append', required=True, type=parse_source)
    f.add_argument('--seed', type=int, default=oc.SEEDS[0])
    f.add_argument('--negatives', type=int)
    f.add_argument('--iterations', type=int)
    f.add_argument('--depth', type=int)
    f.add_argument('--learning-rate', type=float)
    e = sub.add_parser('evaluate')
    e.add_argument('--name', required=True)
    e.add_argument('--fold', type=int, required=True)
    e.add_argument('--models', action='append', help='fit directories to average (default: the fit NAME)')
    a = p.parse_args(argv)
    with om.quiet_stdout():
        if a.command == 'fit':
            recipe = {k: v for k, v in (('iterations', a.iterations), ('depth', a.depth),
                                        ('learning_rate', a.learning_rate)) if v is not None}
            out = fit(a.name, a.source, a.seed, a.negatives, recipe)
            out = {k: out[k] for k in ('status', 'training', 'fit', 'seconds')}
        else:
            out = evaluate(a.name, a.fold, a.models)
            out = {k: out.get(k) for k in ('status', 'recall', 'score', 'rows', 'seconds')}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
