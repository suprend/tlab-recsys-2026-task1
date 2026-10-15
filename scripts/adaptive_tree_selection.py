"""Two new development fits; choose each prefix using full-Y validation NDCG.

Train/selection only. This is exploratory after the historical final was opened.
The old fixed-300 public reproduction is deliberately unchanged. Cooperative
limits exclude interpreter startup/exit; an agent run needs external supervision.
"""
from copy import deepcopy
from dataclasses import asdict
import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SHA = 'ad27d69662e85a647c34c5853b64213a0526bf509e84f4dd639a7e93acf02a85'
REPORT_SHA = 'e62b1f47d6db808f6f5235f63a1b207970ac2f8487c09d9273902c4fbc864a9b'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def positive_layout(queries, groups):
    """Keep every full-Y-positive query, including empty-C and off-C positives."""
    selected = [i for i, query in enumerate(queries) if query[3]]
    need(selected, 'Validation has no positive full-target queries')
    remap = {old: new for new, old in enumerate(selected)}
    rows, compact = [], []
    for row, group in enumerate(groups):
        if int(group) in remap:
            rows.append(row)
            compact.append(remap[int(group)])
    return [queries[i] for i in selected], rows, compact


def _choose_curve(staged_scores, metric, *, maximum, check, tolerance=1e-12):
    """Complete-range argmax; earliest tree in the GLOBAL maximum's tie band.

    The caller supplies predictions for prefixes1..maximum. The production
    caller fixes the metric to full-Y conditional macro-query NDCG@20.
    No patience/early stopping or claim of optimality outside this range.
    """
    need(type(maximum) is int and maximum > 0, 'Positive tree ceiling required')
    need(tolerance == 1e-12, 'Frozen tie tolerance differs')
    curve = []
    for tree, scores in enumerate(staged_scores, 1):
        check()
        need(tree <= maximum, 'Staged iterator returned too many prefixes')
        value = metric(scores)
        need(type(value) is float and math.isfinite(value), 'Undefined/nonfinite primary metric')
        curve.append(value)
        check()
    need(len(curve) == maximum, 'Staged iterator did not cover every allowed tree')
    peak = max(curve)
    return next(i + 1 for i, value in enumerate(curve) if value >= peak - tolerance), curve


def select_best_tree(model, validation, *, maximum=None, check=lambda: None):
    """Reusable selector for future fits: full-Y conditional query NDCG@20.

    The model is already trained; maximum is a search/resource ceiling, never
    a selected tree count. Recall is reported separately, not a hidden floor.
    """
    import numpy as np
    from scripts import train_baselines as b
    from scripts.ranking_metrics import evaluate
    maximum = model.tree_count_ if maximum is None else maximum
    need(type(maximum) is int and maximum == model.tree_count_, 'Full trained range required')
    queries, rows, groups = positive_layout(validation.queries, validation.group)
    small = b.Prepared(queries, np.asarray(groups, dtype=np.int32), validation.items[rows],
                       validation.x[rows], validation.y[rows], validation.feature_names)
    # All-positive queries can have no C at all: every ranking is exactly empty.
    staged = (model.staged_predict(small.x, prediction_type='RawFormulaVal', ntree_start=0,
              ntree_end=maximum, eval_period=1, thread_count=2) if rows else ([] for _ in range(maximum)))
    def primary(scores):
        return evaluate(b.rankings(small, scores), 20).conditional_macro_query.ndcg
    best, curve = _choose_curve(staged, primary, maximum=maximum, check=check)
    return best, curve, dict(fullY_positive_queries=len(queries), candidate_rows=len(rows))


def verify_model(model, recipe, arm, count, same):
    need(type(model.tree_count_) is int and model.tree_count_ == count, 'Model tree count differs')
    need(model.feature_names_ == recipe['feature_names'][arm], 'Model feature order differs')
    need(model.get_cat_feature_indices() == model.get_text_feature_indices()
         == model.get_embedding_feature_indices() == [], 'Numeric-only model required')
    expected = deepcopy(recipe['effective_parameters'])
    expected['iterations'] = 1200  # shrink retains the training metadata.
    same(expected, model.get_all_params())


def run(request_path, expected_sha, output):
    # Bounded request/public source reads precede cooperative Budget construction.
    with request_path.open('rb') as stream:
        raw = stream.read(128 * 1024 + 1)
    need(len(raw) <= 128 * 1024 and hashlib.sha256(raw).hexdigest() == expected_sha, 'Request differs')
    request = json.loads(raw)
    public_path = ROOT / 'scripts/reproduce_frozen_comparison.py'
    with public_path.open('rb') as stream:
        public_raw = stream.read(128 * 1024 + 1)
    need(len(public_raw) <= 128 * 1024 and hashlib.sha256(public_raw).hexdigest() == PUBLIC_SHA,
         'Protected public loader differs')
    need('scripts.reproduce_frozen_comparison' not in sys.modules, 'Fresh process required')
    import scripts
    r = ModuleType('scripts.reproduce_frozen_comparison')
    r.__file__, r.__package__ = str(public_path), 'scripts'
    sys.modules[r.__name__] = r
    scripts.reproduce_frozen_comparison = r
    exec(compile(public_raw, str(public_path), 'exec', dont_inherit=True), r.__dict__)
    need(r.parse_json(raw) == request, 'Request parse differs')
    need(request['study'] == dict(max_iterations=1200, metric='conditional_macro_query.ndcg@20',
         tie_tolerance=1e-12, arms=['B', 'W'], max_fits=2, max_validation_checkpoints=2400), 'Study differs')
    limits = request['producer_cooperative_limits']
    need(limits == dict(cpu=3440, wall=2640, rss=12 * 2**30, spill=16 * 2**30), 'Limits differ')
    budget = r.Budget(**limits)
    check = budget.check
    need(not output.is_symlink() and not output.exists(), 'Literal output must be new and not a symlink')
    output = output.resolve()
    output.relative_to(ROOT / 'artifacts/reproduction')
    need(output == (ROOT / request['output_path']).resolve(), 'Closed output namespace differs')
    producer = ROOT / 'artifacts/reproduction/public-frozen-bw-once'
    need(output != producer and producer not in output.parents, 'Fresh study output required')
    output.mkdir(exist_ok=False)
    r.write_new(output / 'consumed.json', dict(request_sha256=expected_sha, max_fits=2,
                max_validation_checkpoints=2400, retry=False, independent_acceptance_issued=False))
    try:
        r.write_snapshot(output / 'request.json', raw, dict(sha256=expected_sha, bytes=len(raw)), check)
        driver = r.file_ref(__file__, check)
        need(driver == request['driver'], 'Initial study command differs')
        need(request['recipe_path'] == 'configs/reproduction/frozen-bw-oct2019.json', 'Recipe path differs')
        recipe, recipe_raw, recipe_ref = r.validate_recipe(ROOT / request['recipe_path'], check)
        sources = r.SourceBinding(recipe, check)
        def source_check():
            sources.check()
            need(r.file_ref(__file__, check) == driver, 'Initial study command changed')
        report_path = producer / 'report.json'
        report_raw, report_ref = r.snapshot_file(report_path, check, maximum=128 * 1024)
        need(report_ref == request['accepted_report'] and report_ref['sha256'] == REPORT_SHA, 'Accepted producer report differs')
        original = r.parse_json(report_raw)
        need(original['command_source'] == sources.command and original['dependencies'] == sources.witnesses,
             'Accepted source closure differs')
        phases = {}
        for phase, start, end in [('train', 8, 21), ('selection', 22, 24)]:
            inventory = original['data_exports'][phase]
            need([row['manifest']['path'] for row in inventory] ==
                 [f'{phase}/2019-10-{day:02}/manifest.json' for day in range(start, end)], 'Development calendar differs')
            phases[phase] = []
            for row in inventory:
                files = {}
                for kind, pin in row['exports'].items():
                    relative = Path(pin['path'])
                    need(relative.parts == (phase, Path(row['manifest']['path']).parent.name, kind + '.parquet'), 'Export path differs')
                    files[kind] = producer / relative
                need(set(files) == {'queries', 'candidates', 'base', 'extra', 'labels'}, 'Export kinds differ')
                files['_refs'] = {kind: dict(path=Path(pin['path']).name, sha256=pin['sha256'], bytes=pin['bytes'])
                                  for kind, pin in row['exports'].items()}
                files['_manifest'] = dict(path=producer / row['manifest']['path'],
                    witness={key: row['manifest'][key] for key in ('sha256', 'bytes')})
                phases[phase].append(files)
        files_all = phases['train'] + phases['selection']
        r.verify_exports(files_all, check)
        sources.load_cores()
        import numpy as np
        from catboost import CatBoostClassifier, Pool
        from scripts import train_baselines as b
        from scripts.heldout_predictions import _same
        from scripts.ranking_metrics import evaluate
        r.write_snapshot(output / 'recipe.json', recipe_raw, recipe_ref, check)
        r.write_snapshot(output / 'accepted-report.json', report_raw, report_ref, check)
        models, summaries = {}, {}
        constructor = deepcopy(recipe['constructor_parameters'])
        constructor['iterations'] = 1200
        for arm in ('B', 'W'):
            source_check()
            train = r.prepare_matrix(phases['train'], recipe, arm, max_queries=26000, max_rows=5720000, check=check)
            counts, positive, negative, informative, weights, accounting = b.group_accounting(train)
            identity = r.matrix_identity(train, check)
            identity['weights'] = r.array_ref(weights, check)
            need(identity == original['comparison'][arm]['train'], 'Accepted training matrix differs')
            if arm == 'W':
                r.require_shared_base(identity, summaries['B']['train'], 'train')
            need(np.any(train.y == 0) and np.any(train.y == 1), 'Binary training support required')
            pool = Pool(train.x, label=train.y, weight=weights, feature_names=train.feature_names, thread_count=2)
            model = CatBoostClassifier(**constructor)
            callback = b._BudgetCallback(check)
            budget.reserve_fit()
            r.write_new(output / (arm + '.fit-consumed.json'), dict(arm=arm, attempt=budget.fit_attempts,
                        constructor_parameters=constructor, train=identity, accounting=accounting))
            source_check()
            r.verify_exports(phases['train'], check)
            model.fit(pool, callbacks=[callback])
            if callback.failure is not None:
                raise callback.failure
            check()
            source_check()
            r.verify_exports(phases['train'], check)
            verify_model(model, recipe, arm, 1200, _same)
            path = output / (arm + '.full-1200.cbm')
            model.save_model(str(path), format='cbm')
            models[arm] = dict(path=path, witness=r.file_ref(path, check))
            summaries[arm] = dict(train=identity, accounting=accounting)
            del model, pool, train, counts, positive, negative, informative, weights
            gc.collect()
        need(budget.fit_attempts == 2, 'Exactly two completed fits required before validation feedback')
        fits_complete_path = output / 'both-fits-complete.json'
        r.write_new(fits_complete_path, dict(completed_fits=2, full_models={arm: info['witness']
                    for arm, info in models.items()}, validation_checkpoints_started=0,
                    telemetry=budget.telemetry(), producer_statement_not_independent_proof=True))
        fits_complete_ref = r.file_ref(fits_complete_path, check)
        for arm in ('B', 'W'):
            source_check()
            selection = r.prepare_matrix(phases['selection'], recipe, arm, max_queries=None, max_rows=880000, check=check)
            identity = r.matrix_identity(selection, check)
            need(identity == original['comparison'][arm]['selection'], 'Accepted selection matrix differs')
            if arm == 'W':
                r.require_shared_base(identity, summaries['B']['selection'], 'selection')
            model_info = models[arm]
            need(r.file_ref(model_info['path'], check) == model_info['witness'], 'Full model changed before load')
            model = CatBoostClassifier()
            model.load_model(str(model_info['path']), format='cbm')
            verify_model(model, recipe, arm, 1200, _same)
            r.write_new(output / (arm + '.validation-consumed.json'), dict(max_checkpoints=1200,
                        both_fits_complete=fits_complete_ref, final_used=False))
            source_check()
            r.verify_exports(phases['selection'], check)
            best, curve, projection = select_best_tree(model, selection, maximum=1200, check=check)
            need(projection['fullY_positive_queries'] == original['comparison'][arm]['evaluation']['nonempty_query_count'],
                 'Positive query cover differs')
            source_check()
            r.verify_exports(phases['selection'], check)
            need(r.file_ref(model_info['path'], check) == model_info['witness'], 'Full model changed during staged stream')
            r.write_new(output / (arm + '.curve.json'), dict(ndcg=curve, selected_trees=best,
                        maximum_ndcg=max(curve), tie_tolerance=1e-12, projection=projection,
                        full_model=model_info['witness'], metric='conditional_macro_query.ndcg@20'))
            full_scores = np.asarray(model.predict(selection.x, ntree_end=best,
                                     prediction_type='RawFormulaVal', thread_count=2), dtype=np.float64)
            full_ranked = b.rankings(selection, full_scores)
            selected = model.copy()
            selected.shrink(best, ntree_start=0)
            verify_model(selected, recipe, arm, best, _same)
            path = output / (arm + '.selected.cbm')
            selected.save_model(str(path), format='cbm')
            selected_ref = r.file_ref(path, check)
            del selected, model
            gc.collect()
            selected = CatBoostClassifier()
            need(r.file_ref(path, check) == selected_ref, 'Selected model changed before reload')
            selected.load_model(str(path), format='cbm')
            verify_model(selected, recipe, arm, best, _same)
            replay = np.asarray(selected.predict(selection.x, prediction_type='RawFormulaVal', thread_count=2), dtype=np.float64)
            ranked = b.rankings(selection, replay)
            need(np.allclose(full_scores, replay, rtol=0, atol=1e-12) and ranked == full_ranked,
                 'Selected serialized model differs from the full-model prefix')
            evaluation = asdict(evaluate(ranked, 20))
            need(abs(evaluation['conditional_macro_query']['ndcg'] - curve[best - 1]) <= 1e-12,
                 'Positive-only curve differs from full-cohort primary metric')
            score_path = output / (arm + '.selected-scores.npz')
            with score_path.open('xb') as stream:
                np.savez_compressed(stream, group=selection.group, items=selection.items, scores=replay)
            need(r.file_ref(model_info['path'], check) == model_info['witness'] and r.file_ref(path, check) == selected_ref,
                 'Produced model changed during validation')
            summaries[arm].update(selection=identity, selected_trees=best, full_model=model_info['witness'],
                selected_model=selected_ref, scores=r.file_ref(score_path, check), evaluation=evaluation,
                curve=r.file_ref(output / (arm + '.curve.json'), check), validation_checkpoints=len(curve),
                max_raw_score_difference=float(np.max(np.abs(full_scores - replay))))
            del selected, selection, full_scores, replay, full_ranked, ranked, curve
            gc.collect()
            check()
        source_check()
        r.verify_exports(files_all, check)
        need(r.file_ref(report_path, check) == report_ref, 'Original accepted producer report changed')
        need(r.file_ref(fits_complete_path, check) == fits_complete_ref, 'Fit completion statement changed')
        for arm in ('B', 'W'):
            for suffix, key in [('full-1200.cbm', 'full_model'), ('selected.cbm', 'selected_model'),
                                ('selected-scores.npz', 'scores'), ('curve.json', 'curve')]:
                need(r.file_ref(output / (arm + '.' + suffix), check) == summaries[arm][key], 'Owned result changed')
        for path, pin in [(output / 'request.json', dict(sha256=expected_sha, bytes=len(raw))),
                          (output / 'recipe.json', recipe_ref), (output / 'accepted-report.json', report_ref)]:
            need(r.file_ref(path, check) == pin, 'Owned input snapshot changed')
        report = dict(status='complete_produced_pending_independent_review', arms=summaries,
            fit_attempts=budget.fit_attempts, dependent_validation_checkpoints=2400, exploratory=True,
            heldout_confirmed=False, final_used=False, native_early_stopping=False,
            best_within_range=[1, 1200], telemetry=budget.telemetry(), driver=driver,
            request_sha256=expected_sha, accepted_report=report_ref, dependencies=sources.witnesses,
            both_fits_complete=fits_complete_ref,
            same_tree_differences='Derivable from the two saved curves; no extra evaluations or fits',
            independent_acceptance_issued=False, full_external_tail_accepted=False)
        r.write_new(output / 'report.json', report)
        check()
        source_check()
        return report
    except BaseException as error:
        try:
            r.fail_preserving(error, output, budget)
        except BaseException as secondary:
            r.secondary_note(error, 'Failure handler', secondary)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--expected-request-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.request, args.expected_request_sha, args.output)
