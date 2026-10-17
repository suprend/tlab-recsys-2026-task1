"""Two seed2027 fits on accepted historical frozen exports; never raw regeneration.

Import is stdlib-only. Root owns any real run and whole-process supervision.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import asdict
import gc
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

SCOPE = 'historical_d35cfb6_frozen_exports_seed2027_not_current_raw_pipeline'
REPORT_SHA = 'e62b1f47d6db808f6f5235f63a1b207970ac2f8487c09d9273902c4fbc864a9b'
ARMS = ('B', 'W')
POPULATIONS = {'train': (26000, 5317058), 'selection': (4000, 817149)}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def parse(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            need(key not in out, 'Duplicate JSON field')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def witness(path):
    digest, size = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return dict(sha256=digest.hexdigest(), bytes=size)


def snapshot(path, maximum):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum + 1)
    need(len(raw) <= maximum, 'Bounded snapshot exceeded')
    return raw, dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def check_live_modules(bound):
    for name, module in bound.items():
        need(sys.modules.get(name) is module, 'Bound module replaced: ' + name)
        parent, _, leaf = name.rpartition('.')
        if parent:
            need(getattr(sys.modules[parent], leaf, None) is module, 'Bound package alias replaced: ' + name)


def arm_recipes(recipe):
    result = {}
    for arm in ARMS:
        constructor = deepcopy(recipe['constructor_parameters'])
        effective = deepcopy(recipe['effective_parameters'])
        constructor.update(iterations=1200, random_seed=2027)
        effective.update(iterations=1200, random_seed=2027)
        result[arm] = dict(arm=arm, constructor=constructor, effective=effective,
                           features=recipe['feature_names'][arm], scope=SCOPE)
    need(result['W']['features'][:41] == result['B']['features']
         and len(result['B']['features']) == 41 and len(result['W']['features']) == 44,
         'Frozen B41/W44 closure differs')
    return result


def exact_prepared(data, prepared_type):
    """Transport only: preserve every array, query/fullY object and column order."""
    if type(data) is prepared_type:
        return data
    return prepared_type(data.queries, data.group, data.items, data.x, data.y, data.feature_names)


def inventory(original, producer):
    phases = {}
    for phase, start, stop in [('train', 8, 21), ('selection', 22, 24)]:
        rows = original['data_exports'][phase]
        need([row['manifest']['path'] for row in rows] ==
             [f'{phase}/2019-10-{day:02}/manifest.json' for day in range(start, stop)],
             'Only train8-20/selection22-23 are permitted')
        phases[phase] = []
        for row in rows:
            day = Path(row['manifest']['path']).parent.name
            need(set(row['exports']) == {'queries', 'candidates', 'base', 'extra', 'labels'}, 'Five export kinds required')
            files = {}
            for kind, pin in row['exports'].items():
                rel = Path(pin['path'])
                need(rel.parts == (phase, day, kind + '.parquet'), 'Export path escapes exact calendar')
                files[kind] = producer / rel
            files['_refs'] = {kind: dict(path=Path(pin['path']).name,
                sha256=pin['sha256'], bytes=pin['bytes']) for kind, pin in row['exports'].items()}
            files['_manifest'] = dict(path=producer / row['manifest']['path'],
                witness={key: row['manifest'][key] for key in ('sha256', 'bytes')})
            phases[phase].append(files)
    return phases


def verify_model(model, spec, count, same):
    need(type(model.tree_count_) is int and model.tree_count_ == count, 'Tree count differs')
    need(model.feature_names_ == spec['features'], 'Feature order differs')
    need(model.get_cat_feature_indices() == model.get_text_feature_indices()
         == model.get_embedding_feature_indices() == [], 'Numeric-only model required')
    same(spec['effective'], model.get_all_params())


def execute_pair(api, recipe, original, phases, output, check):
    """Narrow orchestration seam; test injection never selected by CLI arguments."""
    specs = arm_recipes(recipe)
    # Persist BOTH immutable recipes before preparing data or invoking fit/selector.
    for arm in ARMS:
        write(output / (arm + '.recipe.json'), specs[arm])
    write(output / 'both-recipes-sealed.json', {arm: witness(output / (arm + '.recipe.json')) for arm in ARMS})
    prepared, identities = {}, {}
    for arm in ARMS:
        prepared[arm], identities[arm] = {}, {}
        for phase, queries, rows in [('train', 26000, 5720000), ('selection', None, 880000)]:
            check()
            data = api.r.prepare_matrix(phases[phase], recipe, arm,
                max_queries=queries, max_rows=rows, check=check)
            data = exact_prepared(data, api.b.Prepared)
            need(type(data) is api.b.Prepared, 'Exact current Prepared type required')
            expected_q, expected_rows = POPULATIONS[phase]
            need(len(data.queries) == expected_q and len(data.group) == expected_rows,
                 'Frozen full population differs; no subsampling is permitted')
            ident = api.r.matrix_identity(data, check)
            if phase == 'train':
                weights = api.b.group_accounting(data)[-2]
                ident['weights'] = api.r.array_ref(weights, check)
            need(ident == original['comparison'][arm][phase], 'Historical accepted matrix identity differs')
            if arm == 'W':
                api.r.require_shared_base(ident, identities['B'][phase], phase)
            prepared[arm][phase], identities[arm][phase] = data, ident
    results = {}
    for arm in ARMS:
        check()
        spec = specs[arm]
        # Recipe snapshots are immutable; no adaptation after observing B.
        need(parse((output / (arm + '.recipe.json')).read_bytes()) == spec, 'Sealed arm recipe changed')
        api.reserve_fit()
        write(output / (arm + '.fit-consumed.json'), dict(arm=arm, seed=2027, ceiling=1200, retry=False))
        model = api.Classifier(**spec['constructor'])
        fitted = api.fit(model, prepared[arm]['train'], prepared[arm]['selection'], max_iterations=1200, check=check)
        need(fitted.trained_ceiling == 1200 and len(fitted.validation_curve) == 1200, 'Incomplete prefix range')
        full, selected, k = fitted.full_model, fitted.selected_model, fitted.selected_trees
        verify_model(full, spec, 1200, api.same)
        verify_model(selected, spec, k, api.same)
        full_path, selected_path = output / (arm + '.full.cbm'), output / (arm + '.selected.cbm')
        full.save_model(str(full_path), format='cbm')
        selected.save_model(str(selected_path), format='cbm')
        full_ref, selected_ref = witness(full_path), witness(selected_path)
        loaded = api.Classifier()
        loaded.load_model(str(selected_path), format='cbm')
        verify_model(loaded, spec, k, api.same)
        val = prepared[arm]['selection']
        scores = []
        rankings = []
        for candidate, kwargs in [(full, {'ntree_end': k}), (selected, {}), (loaded, {})]:
            check()
            current = api.np.asarray(candidate.predict(val.x, prediction_type='RawFormulaVal', thread_count=2, **kwargs), dtype=api.np.float64)
            need(current.shape == (len(val.group),) and api.np.all(api.np.isfinite(current)), 'Scores shape/nonfinite failure')
            scores.append(current)
            rankings.append(api.b.rankings(val, current))
        need(all(api.np.allclose(scores[0], other, rtol=0, atol=1e-12) for other in scores[1:])
             and rankings[0] == rankings[1] == rankings[2], 'Full/copy/reload exact ranking parity differs')
        evaluation = asdict(api.evaluate(rankings[2], 20))
        need(abs(evaluation['conditional_macro_query']['ndcg'] - fitted.validation_curve[k - 1]) <= 1e-12,
             'Full-cohort metric differs from positive-only curve')
        with (output / (arm + '.selected-scores.npz')).open('xb') as stream:
            api.np.savez_compressed(stream, group=val.group, items=val.items, scores=scores[2])
        need(witness(full_path) == full_ref and witness(selected_path) == selected_ref, 'Model changed during parity')
        for phase in ('train', 'selection'):
            unchanged = api.r.matrix_identity(prepared[arm][phase], check)
            if phase == 'train':
                unchanged['weights'] = api.r.array_ref(api.b.group_accounting(prepared[arm][phase])[-2], check)
            need(unchanged == identities[arm][phase], 'Prepared input mutated during fit/scoring')
        results[arm] = dict(train=identities[arm]['train'], selection=identities[arm]['selection'],
            selected_trees=k, curve=list(fitted.validation_curve), evaluation=evaluation,
            support=fitted.validation_support, training_accounting=fitted.training_accounting,
            full_model=full_ref, selected_model=selected_ref, parity_prediction_calls=3,
            parity_score_values=3 * len(val.group), persisted_score_values=len(val.group))
        del full, selected, loaded, fitted, model, scores, rankings
        gc.collect()
    results['comparison'] = dict(
        delta_ndcg=results['W']['evaluation']['conditional_macro_query']['ndcg'] - results['B']['evaluation']['conditional_macro_query']['ndcg'],
        delta_recall=results['W']['evaluation']['conditional_macro_query']['recall'] - results['B']['evaluation']['conditional_macro_query']['recall'],
        matched_k={str(k): {arm: results[arm]['curve'][k-1] for arm in ARMS} for k in (300,600,1200)},
        interpretation='paired seed2027 reused-development screening; not independent final/generalization')
    results['comparison']['finite_criterion_met'] = results['comparison']['delta_ndcg'] > 0 and results['comparison']['delta_recall'] >= 0
    results['accounting'] = dict(fits=2, positive_prefix_streams=2, dependent_prefix_points=2400,
        full_parity_prediction_calls=6, parity_score_values=sum(results[arm]['parity_score_values'] for arm in ARMS),
        persisted_score_values=sum(results[arm]['persisted_score_values'] for arm in ARMS),
        source_scope=SCOPE, no_final_access=True)
    return results


def load_module(name, path, expected):
    raw, actual = snapshot(path, 512 * 1024)
    need(actual == expected, 'Source snapshot differs: ' + name)
    need(name not in sys.modules, 'Fresh process/module required: ' + name)
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), name.rpartition('.')[0]
    sys.modules[name] = module
    if '.' in name:
        setattr(sys.modules[name.rpartition('.')[0]], name.rpartition('.')[2], module)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def run(request_path, expected_sha, output):
    sys.dont_write_bytecode = True
    raw, request_ref = snapshot(request_path, 128 * 1024)
    need(request_ref['sha256'] == expected_sha, 'Request differs')
    request = parse(raw)
    need(request['scope'] == SCOPE and request['seed'] == 2027 and request['ceiling'] == 1200,
         'Only historical frozen-export seed2027 replication supported')
    root, producer = Path(request['project_root']), Path(request['producer_root'])
    output = Path(output)
    need(not output.exists() and not output.is_symlink() and output.parent.is_dir(), 'Fresh output required')
    need(output.resolve() != producer.resolve() and producer.resolve() not in output.resolve().parents, 'Do not modify historical exports')
    # This fresh closure is separate from original producer dependencies/receipts.
    live_modules = {}
    def source_check():
        need(request['scripts_namespace_package_no_initializer'] is True
             and not (root / 'scripts/__init__.py').exists(), 'Unexpected scripts initializer')
        for path, expected in request['source_closure'].items():
            need(witness(path) == expected, 'Current source closure changed: ' + path)
        check_live_modules(live_modules)
    source_check()
    need(witness(__file__) == request['source_closure'][str(Path(__file__).resolve())], 'Caller is not bound')
    need(request['accepted_report']['sha256'] == REPORT_SHA, 'Only accepted historical report supported')
    report_path = producer / 'report.json'
    report_raw, report_ref = snapshot(report_path, 128 * 1024)
    need(report_ref == request['accepted_report'], 'Original report changed')
    original = parse(report_raw)
    sys.path.insert(0, str(root))
    need('scripts' not in sys.modules, 'Fresh scripts namespace required')
    package = ModuleType('scripts')
    package.__path__ = [str(root / 'scripts')]
    sys.modules['scripts'] = package
    public_path = root / 'scripts/reproduce_frozen_comparison.py'
    r = load_module('scripts.reproduce_frozen_comparison', public_path, request['source_closure'][str(public_path)])
    live_modules['scripts.reproduce_frozen_comparison'] = r
    recipe, _, _ = r.validate_recipe(root / 'configs/reproduction/frozen-bw-oct2019.json', lambda: None)
    required = {str(root / name) for name in recipe['dependencies']}
    required.update(str(root / name) for name in ('scripts/reproduce_frozen_comparison.py',
        'scripts/development_training.py', 'scripts/adaptive_tree_selection.py', 'configs/reproduction/frozen-bw-oct2019.json'))
    required.add(str(Path(__file__).resolve()))
    need(set(request['source_closure']) == required, 'Incomplete or unexpected current source closure')
    limits = request['cooperative_limits']
    need(limits == dict(cpu=3500, wall=2700, rss=12 * 2**30, spill=8 * 2**30), 'Finite producer limits differ')
    need(request['whole_operation_limits'] == dict(cpu=4200, wall=3600), 'Whole-operation envelope differs')
    budget = r.Budget(**limits)
    def check():
        budget.check()
        source_check()
        if output.exists():
            need(sum(p.stat().st_size for p in output.iterdir() if p.is_file()) <= 2 * 2**30, 'New-output cap exceeded')
    phases = inventory(original, producer)
    r.verify_exports(phases['train'] + phases['selection'], check)
    bound = r.SourceBinding(recipe, check)
    bound.load_cores()
    live_modules.update({'scripts.' + name: module for name, module in bound.loaded.items()})
    selector_path = root / 'scripts/adaptive_tree_selection.py'
    helper_path = root / 'scripts/development_training.py'
    selector = load_module('scripts.adaptive_tree_selection', selector_path, request['source_closure'][str(selector_path)])
    live_modules['scripts.adaptive_tree_selection'] = selector
    helper = load_module('scripts.development_training', helper_path, request['source_closure'][str(helper_path)])
    live_modules['scripts.development_training'] = helper
    from scripts import train_baselines as b
    from scripts.heldout_predictions import _same
    from scripts.ranking_metrics import evaluate
    import numpy as np
    from catboost import CatBoostClassifier
    api = SimpleNamespace(r=r, b=b, np=np, fit=helper.fit_development, reserve_fit=budget.reserve_fit,
        Classifier=CatBoostClassifier, same=_same, evaluate=evaluate)
    output.mkdir(mode=0o700)
    write(output / 'request.json', request)
    try:
        results = execute_pair(api, recipe, original, phases, output, check)
        check()
        r.verify_exports(phases['train'] + phases['selection'], check)
        need(witness(report_path) == request['accepted_report'], 'Original report changed during run')
        write(output / 'produced-unreviewed.json', dict(scope=SCOPE, results=results,
            current_source_closure=request['source_closure'], historical_report=request['accepted_report'],
            producer_statement_not_independent_acceptance=True, resources=budget.telemetry()))
        check()
    except BaseException as error:
        r.fail_preserving(error, output, budget)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--expected-request-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.request, args.expected_request_sha, args.output)
