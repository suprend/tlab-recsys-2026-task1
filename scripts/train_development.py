"""Fit one new development model and select its prefix on separate validation.

Limits are cooperative process observations, not hard whole-process-tree limits.
External supervision must include interpreter startup, blocking calls and cleanup.
Historical frozen/smoke trainers have separate contracts and are unchanged.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import resource
import sys
import time


CODE = ('scripts/train_development.py', 'scripts/development_training.py',
        'scripts/adaptive_tree_selection.py', 'pyproject.toml')


def require(ok, message):
    if not ok:
        raise ValueError(message)


class Budget:
    """SELF CPU/peak RSS and elapsed wall since run entry; checks can overshoot."""
    def __init__(self, cpu, wall, rss):
        self.start_wall, self.start_cpu = time.monotonic(), time.process_time()
        self.cpu, self.wall, self.rss = cpu, wall, rss

    def observation(self):
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return dict(cpu_seconds=time.process_time()-self.start_cpu,
                    wall_seconds=time.monotonic()-self.start_wall,
                    process_peak_rss_bytes=int(peak if sys.platform == 'darwin' else peak*1024))

    def check(self):
        actual = self.observation()
        if actual['cpu_seconds'] > self.cpu or actual['wall_seconds'] > self.wall:
            raise TimeoutError('Cooperative development CPU/wall limit exceeded')
        if actual['process_peak_rss_bytes'] > self.rss:
            raise MemoryError('Cooperative development SELF peak RSS limit exceeded')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('train-acceptance', 'validation-acceptance', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    for name in ('max-iterations', 'train-query-cap', 'max-matrix-rows', 'depth',
                 'random-seed', 'cpu-seconds', 'wall-seconds', 'rss-bytes'):
        p.add_argument('--'+name, type=int, required=True)
    for name in ('learning-rate', 'l2-leaf-reg'):
        p.add_argument('--'+name, type=float, required=True)
    return p


def validate_args(args):
    for name in ('max_iterations', 'cpu_seconds', 'wall_seconds', 'rss_bytes'):
        require(type(getattr(args, name)) is int and getattr(args, name) > 0,
                'Explicit positive integer required: '+name)
    for name, lower, upper in (('train_query_cap', 1, 6000),
                               ('max_matrix_rows', 1, 1320000), ('depth', 1, 16),
                               ('random_seed', 0, 2**31-1)):
        require(type(getattr(args, name)) is int and lower <= getattr(args, name) <= upper,
                'Unsupported bounded parameter: '+name)
    require(math.isfinite(args.learning_rate) and 0 < args.learning_rate <= 1,
            'Learning rate must be finite in (0,1]')
    require(math.isfinite(args.l2_leaf_reg) and args.l2_leaf_reg >= 0,
            'L2 must be finite and nonnegative')
    require(args.train_acceptance.resolve() != args.validation_acceptance.resolve(),
            'Separate train and validation acceptances required')


def load_runtime():
    # Ordinary import/discovery of this CLI does not import the ML/data backend.
    from types import SimpleNamespace
    import numpy as np
    from catboost import CatBoostClassifier
    from scripts import train_baselines as b
    from scripts.development_training import fit_development
    return SimpleNamespace(np=np, Classifier=CatBoostClassifier, b=b, fit=fit_development)


def input_pins(b, train, validation, check):
    pins = {}
    for group in (train['pins'], validation['pins']):
        for name, digest in group.items():
            require(name not in pins or pins[name] == digest, 'Accepted input pins conflict: '+name)
            pins[name] = digest
    for name in sorted(set(b.CODE) | set(CODE)):
        check()
        actual = b.sha256_file(b._local(name))
        require(name not in pins or pins[name] == actual, 'Accepted source changed: '+name)
        pins[name] = actual
        check()
    return pins


def recheck_pins(b, pins, check):
    for name, digest in pins.items():
        check()
        require(b.sha256_file(b._local(name)) == digest, 'Input changed during development fit: '+name)
        check()


def score_parity(runtime, result, validation, selected_path, check):
    np = runtime.np
    check()
    loaded = runtime.Classifier()
    loaded.load_model(str(selected_path))
    check()
    require(type(loaded.tree_count_) is int and loaded.tree_count_ == result.selected_trees
            and loaded.feature_names_ == validation.feature_names,
            'Reloaded selected tree count/feature order differs')
    require(loaded.get_cat_feature_indices() == loaded.get_text_feature_indices()
            == loaded.get_embedding_feature_indices() == [], 'Reloaded model must be numeric')
    scores = []
    for model, end in ((result.full_model, result.selected_trees),
                       (result.selected_model, 0), (loaded, 0)):
        check()
        values = (model.predict(validation.x, prediction_type='RawFormulaVal',
                  ntree_start=0, ntree_end=end, thread_count=2) if len(validation.group)
                  else np.empty(0, dtype=np.float64))
        values = np.asarray(values, dtype=np.float64)
        require(values.shape == (len(validation.group),) and np.isfinite(values).all(),
                'Every validation candidate needs a finite score')
        scores.append(values)
        check()
    differences = [float(np.max(np.abs(values-scores[0]))) if len(values) else 0.0
                   for values in scores[1:]]
    require(all(value <= 1e-12 for value in differences), 'Selected/reloaded versus full-prefix scores differ')
    rankings = []
    for values in scores:
        check()
        rankings.append(runtime.b.rankings(validation, values))
        check()
    require(rankings[0] == rankings[1] == rankings[2], 'Selected/reloaded versus full-prefix rankings differ')
    return scores, dict(tolerance=1e-12, selected_max_abs_difference=differences[0],
                        reloaded_max_abs_difference=differences[1], candidate_rows=len(validation.group),
                        all_validation_query_rankings_identical=True)


def run(args):
    budget = Budget(args.cpu_seconds, args.wall_seconds, args.rss_bytes)
    validate_args(args)
    budget.check()
    literal = args.output.expanduser().absolute()
    require(not literal.exists() and not literal.is_symlink(), 'Existing output must be preserved')
    runtime = load_runtime()
    b, check = runtime.b, budget.check
    check()
    output = literal.resolve()
    output.mkdir(mode=0o700, exist_ok=False)
    report = dict(version=1, status='running', fit_attempt_count=0,
                  fit_attempt_count_semantics='conservative helper attempt; failure may precede native fit',
                  scope='new single-model development; validation selection, not independent quality/CV',
                  cooperative_limits=dict(cpu_seconds=args.cpu_seconds, wall_seconds=args.wall_seconds,
                                          rss_bytes=args.rss_bytes),
                  resource_scope='SELF CPU/peak RSS; run-entry wall; no hard tree/startup/cleanup containment')
    try:
        b._atomic_json(output/'report.json', report)
        train_collection = b.verify_collection(args.train_acceptance, check=check)
        validation_collection = b.verify_collection(args.validation_acceptance, check=check)
        b.validate_training_phases(train_collection, validation_collection, {'wall_seconds': args.wall_seconds})
        require(train_collection['feature_columns'] == validation_collection['feature_columns'],
                'Train and validation feature schemas differ')
        pins = input_pins(b, train_collection, validation_collection, check)
        report['environment'] = b.environment_snapshot(platform_format='kernel')
        check()
        train = b.prepare_dataset(train_collection, max_queries=args.train_query_cap,
                                  max_rows=args.max_matrix_rows, check=check)
        validation = b.prepare_dataset(validation_collection, max_queries=None,
                                       max_rows=args.max_matrix_rows, check=check)
        parameters = dict(iterations=args.max_iterations, depth=args.depth,
                          learning_rate=args.learning_rate, l2_leaf_reg=args.l2_leaf_reg,
                          random_seed=args.random_seed, task_type='CPU', thread_count=2,
                          loss_function='Logloss', use_best_model=False, allow_writing_files=False,
                          boosting_type='Plain', bootstrap_type='No', verbose=False)
        identity = dict(version=1, role='single_model_development', parameters=parameters,
                        max_iterations=args.max_iterations, train_query_cap=args.train_query_cap,
                        max_matrix_rows=args.max_matrix_rows, fingerprints=pins,
                        train_collection_id=train_collection['plan']['collection_id'],
                        validation_collection_id=validation_collection['plan']['collection_id'],
                        selection='all validation Q/fullY; conditional macro-query NDCG@20; global 1e-12 band/fewer trees',
                        training_subset='bottom SHA256(query_id), then query_id, before labels')
        report.update(recipe_sha256=hashlib.sha256(b.canonical_json(identity).encode()).hexdigest(),
                      training_population=b.group_accounting(train)[-1],
                      validation_population=b.group_accounting(validation)[-1], feature_names=train.feature_names)
        b._atomic_json(output/'recipe.json', identity)
        recheck_pins(b, pins, check)
        model = runtime.Classifier(**parameters)
        check()
        report['fit_attempt_count'] = 1
        b._atomic_json(output/'report.json', report)
        result = runtime.fit(model, train, validation, max_iterations=args.max_iterations, check=check)
        for name, model in (('full.cbm', result.full_model), ('selected.cbm', result.selected_model)):
            check()
            model.save_model(str(output/name))
            check()
        scores, parity = score_parity(runtime, result, validation, output/'selected.cbm', check)
        with (output/'validation-scores.npz').open('xb') as stream:
            runtime.np.savez_compressed(stream, group=validation.group, product_id=validation.items,
                                       full_prefix_raw_score=scores[0], selected_raw_score=scores[1],
                                       reloaded_raw_score=scores[2])
        check()
        report.update(trained_ceiling=result.trained_ceiling, selected_trees=result.selected_trees,
                      validation_curve=list(result.validation_curve), validation_support=result.validation_support,
                      training_accounting=result.training_accounting, constructor_parameters=parameters,
                      full_model_parameters=result.full_model.get_all_params(),
                      selected_model_parameters=result.selected_model.get_all_params(), score_parity=parity)
        report['artifacts'] = {}
        for name in ('recipe.json', 'full.cbm', 'selected.cbm', 'validation-scores.npz'):
            check()
            report['artifacts'][name] = b.sha256_file(output/name)
            check()
        recheck_pins(b, pins, check)
        check()
        report.update(status='complete_produced_unreviewed', observations=budget.observation())
        b._atomic_json(output/'report.json', report)
        recheck_pins(b, pins, check)
        check()
        return report
    except BaseException as error:
        try:
            report.update(status='failed', error_type=type(error).__name__)
            try:
                report.update(error=str(error), observations=budget.observation())
            except BaseException as telemetry:
                try: error.add_note('Failure telemetry also failed: '+repr(telemetry))
                except BaseException: pass
            b._atomic_json(output/'report.json', report)
        except BaseException as secondary:
            try: error.add_note('Failure report preparation/write also failed: '+repr(secondary))
            except BaseException: pass
        raise


def main(argv=None):
    result = run(parser().parse_args(argv))
    print(json.dumps({key: result[key] for key in ('status', 'selected_trees', 'trained_ceiling', 'fit_attempt_count')}))
    return result


if __name__ == '__main__':
    main()
