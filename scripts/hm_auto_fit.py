"""Development-only H&M v2 cached fit: frozen GPU500d8 recipe with L2 10/50.

The fit core follows hm_experiment.py at v1 commit 280560f. Cache verification,
sampling, arrays, loss weights, metrics and private exports reuse that frozen
module directly, without changing its globals. This runner never authorizes
final/holdout collections. The caller must own an external 1860-second Job;
the timeout recorded here is a declaration, not process containment.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import math
from pathlib import Path
import sys
import time
import traceback

from scripts import hm_experiment as legacy
from scripts.hm_experiment import load_part, model_pool

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT
SEED = 2026
SOURCE_NAMES = ('hm_auto_fit.py', 'hm_experiment.py', 'hm_baseline.py',
                'hm_job.py', 'hm_feature_engine.py')


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON property')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON constant')
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=pairs, parse_constant=reject)


def fixed_parameters(l2_leaf_reg, iterations=500, depth=8, seed=SEED, task_type='GPU'):
    if type(l2_leaf_reg) is not int or l2_leaf_reg not in (10, 50):
        raise ValueError('V2 L2 must be exactly 10 or 50')
    if type(iterations) is not int or iterations != 500 or type(depth) is not int or depth != 8:
        raise ValueError('V2 fixes 500 trees and depth 8')
    if type(seed) is not int or seed not in (2026, 2027) or task_type != 'GPU':
        raise ValueError('V2 requires GPU and model seed 2026 or 2027')
    return dict(legacy.fixed_parameters(iterations, depth, seed, task_type), l2_leaf_reg=l2_leaf_reg)


def development_manifest(path):
    """Inspect metadata before mkdir, parquet access, SQL or Pool construction."""
    manifest = read_json(path / 'manifest.json')
    if 'final_lock_sha256' in manifest:
        raise ValueError('V2 development runner rejects any final_lock_sha256')
    anchor = date.fromisoformat(manifest['anchor'])
    if anchor >= date(2020, 9, 16):
        raise ValueError('V2 development runner rejects final/holdout dates')
    legacy.check_anchor(anchor)
    expected = dict(format='hm-experiment-collection-v1', status='completed',
                    horizon_days=7, cohort_seed=SEED, policy='C0-Q120', requested_users=20000)
    if not legacy.canonical_digest({k: manifest.get(k) for k in expected}) == legacy.canonical_digest(expected):
        raise ValueError('V2 requires completed C0-Q120/20k/seed2026/seven-day collections')
    return manifest


def new_output(path):
    path = Path(path).resolve()
    allowed = (ROOT / 'artifacts').resolve()
    if path == allowed or not path.is_relative_to(allowed):
        raise ValueError('V2 output must be a new directory inside checkout artifacts/')
    path.mkdir(parents=True, exist_ok=False)
    return path


def fit(train_paths, validation_path, output, feature_names, l2_leaf_reg,
        iterations=500, depth=8, seed=SEED, train_users=20000, negative_sample=20,
        wall_seconds=1800, task_type='GPU', external_job_timeout_seconds=1860):
    parameters = fixed_parameters(l2_leaf_reg, iterations, depth, seed, task_type)
    if type(train_users) is not int or train_users != 20000 or type(negative_sample) is not int or negative_sample != 20:
        raise ValueError('V2 fixes train_users=20000 and negative_sample=20')
    if (isinstance(external_job_timeout_seconds, bool) or
            not isinstance(external_job_timeout_seconds, (int, float)) or
            not math.isfinite(external_job_timeout_seconds) or external_job_timeout_seconds != 1860):
        raise ValueError('V2 requires an external Job timeout declaration of 1860 seconds')
    if isinstance(wall_seconds, bool) or not isinstance(wall_seconds, (int, float)) or not 0 < wall_seconds <= 1800:
        raise ValueError('V2 wall limit must be finite, positive and at most 1800 seconds')
    deadline = legacy.Deadline(wall_seconds)
    train_paths = [Path(p).resolve() for p in train_paths]
    validation_path = Path(validation_path).resolve()
    if not train_paths or len(set(train_paths)) != len(train_paths):
        raise ValueError('Distinct training collection paths required')
    manifests = [development_manifest(p) for p in train_paths]
    val_manifest = development_manifest(validation_path)
    anchors = [date.fromisoformat(m['anchor']) for m in manifests]
    val_anchor = date.fromisoformat(val_manifest['anchor'])
    if len(set(anchors)) != len(anchors) or any(a + timedelta(days=7) > val_anchor for a in anchors):
        raise ValueError('Training target periods must finish before validation anchor')
    for manifest in manifests:
        if any(manifest[k] != val_manifest[k] for k in ('policy', 'features', 'database')):
            raise ValueError('Collections must share policy, feature contract and database identity')
    if not isinstance(feature_names, list) or not all(isinstance(n, str) and n.strip() for n in feature_names):
        raise ValueError('A feature names JSON string list is required')
    numeric, categorical = legacy.choose_features(val_manifest, feature_names=feature_names)
    if len(numeric) + len(categorical) != len(feature_names):
        raise ValueError('Every feature requires a numeric or categorical registry kind')
    for path, manifest in zip(train_paths + [validation_path], manifests + [val_manifest]):
        if legacy.read_manifest(path, deadline) != manifest:
            raise ValueError('Collection manifest changed during preflight')
    output = new_output(output)
    report = dict(format='hm-experiment-fit-v1', status='running', fit_count=0,
                  selection='V2 development fixed GPU500d8/L2; no eval_set or early stopping',
                  training_user_limit=train_users, negative_sample=negative_sample, sampling_seed=SEED)
    con = timer = None
    try:
        report['resources'] = legacy.resource_preflight(output)
        report['resources'].update(external_job_timeout_seconds=external_job_timeout_seconds,
            native_training_deadline='External Job required; declaration is not enforcement by this runner',
            prediction_task_type='CPU', gpu_training_nondeterministic=True)
        import duckdb
        import numpy as np
        from catboost import CatBoostClassifier
        names = numeric + categorical
        report['features'] = dict(numeric=numeric, categorical=categorical,
                                  contract_digest=val_manifest['features']['digest'])
        report['inputs'] = [dict(anchor=m['anchor'], manifest_sha256=legacy.sha256_file(p/'manifest.json', deadline),
                                qcy_identity=m['qcy_identity'], candidate_identity=m['candidate_identity'])
                            for p, m in zip(train_paths + [validation_path], manifests + [val_manifest])]
        report['runtime'] = legacy.runtime_identity()
        report['code'] = {name: legacy.sha256_file(SOURCE_ROOT/'scripts'/name, deadline) for name in SOURCE_NAMES}
        report['hyperparameters'] = parameters
        report['fit_identity'] = legacy.canonical_digest(dict(inputs=report['inputs'], features=report['features'],
            hyperparameters=parameters, train_users=train_users, negative_sample=negative_sample,
            sampling_seed=SEED, code=report['code'], runtime=report['runtime']))
        con = duckdb.connect(':memory:')
        con.execute('SET threads=4')
        con.execute("SET memory_limit='2GB'")
        temp = output/'duckdb-temp'
        temp.mkdir()
        con.execute('SET temp_directory=?', [str(temp)])
        con.execute("SET max_temp_directory_size='8GB'")
        timer = deadline.interrupt_sql(con)
        training = []
        report['training_populations'] = []
        for path, manifest in zip(train_paths, manifests):
            deadline.check()
            frame, _, summary = load_part(con, path, manifest, names, train_users, negative_sample)
            numbers, cats = legacy.model_arrays(frame, numeric, categorical)
            training.append((numbers, cats, frame['label'].to_numpy(dtype=np.int8),
                             frame['fit_weight'].to_numpy(dtype=np.float64)))
            report['training_populations'].append(summary)
            del frame
        numbers = np.concatenate([p[0] for p in training])
        cats = np.concatenate([p[1] for p in training])
        labels = np.concatenate([p[2] for p in training])
        weights = np.concatenate([p[3] for p in training])
        del training
        if len(np.unique(labels)) != 2:
            raise ValueError('Training needs both naturally retrieved label classes')
        deadline.check()
        pool = model_pool(numbers, cats, numeric, categorical, labels, weights)
        model = CatBoostClassifier(**parameters)
        report['fit_count'] = 1
        # GPU rejects callbacks: only the caller's owned Job enforces native time.
        model.fit(pool)
        report['actual_trees'] = model.tree_count_
        if model.tree_count_ != iterations:
            raise RuntimeError('Fixed-tree GPU fit incomplete')
        resolved = model.get_all_params()
        report['resolved_model_parameters'] = resolved
        expected = dict(task_type='GPU', iterations=iterations, depth=depth,
                        l2_leaf_reg=l2_leaf_reg, random_seed=seed)
        if any(resolved.get(k) != value for k, value in expected.items()):
            raise RuntimeError('Resolved GPU model differs from requested backend/capacity/L2/seed')
        report['last_training_iteration'] = model.tree_count_
        deadline.check()
        model.save_model(str(output/'model.cbm'))
        del pool, numbers, cats, labels, weights
        frame, targets, summary = load_part(con, validation_path, val_manifest, names, None, None)
        numbers, cats = legacy.model_arrays(frame, numeric, categorical)
        validation = legacy.pilot.Collection(numbers, cats, frame['label'].to_numpy(),
            frame['query_weight'].to_numpy(), frame['customer_id'].to_numpy(),
            frame['article_id'].to_numpy(), targets, summary)
        deadline.check()
        scores = model.predict_proba(model_pool(numbers, cats, numeric, categorical), thread_count=4)[:, 1]
        report['validation_population'] = summary
        report['validation_metrics'] = legacy.pilot.rank_collection(validation, scores=scores)
        legacy.write_private_predictions(con, output, validation, scores)
        report['files'] = {name: legacy.sha256_file(output/name, deadline) for name in
                           ('model.cbm', 'query-metrics.parquet', 'predictions-top12.parquet')}
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = dict(type=type(exc).__name__, message=str(exc)[:2048],
                               traceback=traceback.format_exc(limit=12)[-8192:])
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds'] = round(time.monotonic() - deadline.started, 3)
        legacy.write_json(output/'report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('fit')
    command.add_argument('--train', type=Path, nargs='+', required=True)
    command.add_argument('--validation', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--feature-names-file', type=Path, required=True)
    command.add_argument('--l2-leaf-reg', type=int, choices=(10, 50), required=True)
    command.add_argument('--iterations', type=int, default=500)
    command.add_argument('--depth', type=int, default=8)
    command.add_argument('--seed', type=int, default=SEED)
    command.add_argument('--train-users', type=int, default=20000)
    command.add_argument('--negative-sample', type=int, default=20)
    command.add_argument('--wall-seconds', type=float, default=1800)
    command.add_argument('--task-type', choices=('GPU',), default='GPU')
    command.add_argument('--external-job-timeout-seconds', type=float, default=1860)
    args = parser.parse_args(argv)
    try:
        result = fit(args.train, args.validation, args.output, read_json(args.feature_names_file),
            args.l2_leaf_reg, args.iterations, args.depth, args.seed, args.train_users,
            args.negative_sample, args.wall_seconds, args.task_type, args.external_job_timeout_seconds)
    except Exception as exc:
        print(json.dumps(dict(status='failed', error_type=type(exc).__name__,
                              message=str(exc)[:2048], output=args.output.as_posix())))
        return 1
    print(json.dumps(dict(status=result['status'], output=args.output.resolve().as_posix())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
