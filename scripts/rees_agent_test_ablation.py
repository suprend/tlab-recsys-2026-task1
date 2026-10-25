"""Post-hoc Hag test ablation; no search/tuning and no overwrite of old results.

TASK1_PERIOD=2020 .venv/bin/python -m scripts.rees_agent_test_ablation
  --prepare-plan --plan PATH --output-dir NEW_ARTIFACT_DIRECTORY
Inspect the created plan, then repeat without --prepare-plan to fit.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

from scripts import rees_sensitivity as S
from scripts import rees_secondary as Q

ROOT = Path(__file__).resolve().parents[1]
SPEC = 'task1/runs/replication-2020/spec.json'
SUMMARY = 'task1/runs/replication-2020/test.json'
REFERENCE_PLAN = 'docs/writeup/sensitivity-2026-10-25/plan.json'
RUNTIME = ('task1/exp.py', 'task1/model.py', 'task1/period.py', 'task1/replicate.py',
           'task1/dfs.py', 'task1/extra.py', 'task1/posthoc.py')
DEPENDENCIES = RUNTIME + ('scripts/rees_agent_test_ablation.py',
                         'scripts/rees_sensitivity.py', 'scripts/rees_secondary.py', 'uv.lock')
LIBRARIES = ('duckdb', 'catboost', 'numpy', 'pandas')
BOOTSTRAP = {'draws': 2000, 'rng_seed': 20261025}
SEEDS = [[2026, 0], [7, 1]]
EXCLUDED = ['2020-02-27', '2020-02-28']
STATUS = 'post-hoc analysis of an already opened test, not confirmatory'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def derive_arm(spec):
    if spec['seeds'] != SEEDS or spec['excluded'] != EXCLUDED or spec['cap'] != 140680:
        raise ValueError('Historical seeds, exclusions or training cap differ')
    hp = next(a for a in spec['arms'] if a['name'] == 'Hp')
    extras = hp['config']['extra']
    if extras[:4] != ['dfs_p', 'dfs_c', 'dfs_b', 'dfs_u']:
        raise ValueError('Hp does not start with the four expected DFS tables')
    agent = extras[4:]
    if len(agent) != 30 or len(set(agent)) != 30 or any(not n.startswith('agent_night20_') for n in agent):
        raise ValueError('Expected exactly the thirty frozen agent tables')
    arm = deepcopy(hp)
    arm['name'] = 'Hag'
    arm['config']['extra'] = agent
    new_spec = deepcopy(spec)
    new_spec['arms'] = [arm]
    new_spec['features'] = {'Hag': 146}
    return arm, new_spec


def modules():
    if os.environ.get('TASK1_PERIOD') != '2020':
        raise ValueError('Set TASK1_PERIOD=2020 before starting Python')
    from task1 import exp, replicate, period
    if period.PERIOD != '2020':
        raise ValueError('Task modules were imported with a different period')
    return exp, replicate


def metric_paths():
    return [f'artifacts/task1/v2020/replication/test_{arm}_s{i}.parquet'
            for arm in ('base', 'Hp') for i in range(2)]


def input_paths(arm, replicate):
    days = sorted({str(d) for split in ('refit', 'test') for d in replicate.M.days(split)})
    paths = [f"{arm['config']['days']}/{d}.parquet" for d in days]
    paths += [f'artifacts/task1/v2020/extra/{name}/{d}.parquet'
              for name in arm['config']['extra'] for d in days]
    return sorted(paths + metric_paths() + [SPEC, SUMMARY, REFERENCE_PLAN])


def historical_checks(spec, original, replicate):
    if original['spec'] != spec or original['run']['seeds'] != SEEDS or original['run']['over']:
        raise ValueError('Original test recipe differs from the frozen specification')
    stamp = original['run']['log'][-1]['stamp']
    for p in RUNTIME:
        if digest(ROOT / p) != stamp['files'][p]:
            raise ValueError(f'Runtime differs from the original test: {p}')
    libs = {p: importlib.metadata.version(p) for p in LIBRARIES}
    if libs != stamp['libs']:
        raise ValueError('Libraries differ from the original test')
    reference_hashes = read_json(ROOT / REFERENCE_PLAN)['input_sha256']
    for p in metric_paths():
        if digest(ROOT / p) != reference_hashes[p]:
            raise ValueError(f'Historical metric file differs from prior audit: {p}')
    replicate.check_frozen(spec)
    expect, signature = replicate.preflight(spec, 'test')
    if expect != 140680 or signature != stamp['inputs']:
        raise ValueError('Historical input metadata or capped training population changed')
    info = {a['arm']: a for a in original['arms']}
    expected = [{'fit_queries': 140680, 'train_rows': 7136760}] * 2
    if info['base']['fits'] != expected or info['Hp']['fits'] != expected:
        raise ValueError('Historical arms have different training populations')
    return {'original_input_metadata_sha256': signature, 'libraries': libs,
            'expected_fits': expected}


def output_path(path):
    path = Path(path).resolve()
    allowed = (ROOT / 'artifacts/task1').resolve()
    if not path.is_relative_to(allowed) or path == allowed:
        raise ValueError('Output must be a new directory below artifacts/task1')
    if path.exists():
        raise FileExistsError('Output directory exists; no resume or overwrite is allowed')
    return path


def prepare_plan(plan_path, output):
    plan_path = Path(plan_path).resolve()
    if not plan_path.is_relative_to(ROOT):
        raise ValueError('Plan must be inside the repository')
    if plan_path.exists():
        raise FileExistsError('Plan exists; it is not overwritten')
    output = output_path(output)
    exp, replicate = modules()
    spec, original = read_json(ROOT / SPEC), read_json(ROOT / SUMMARY)
    arm, new_spec = derive_arm(spec)
    evidence = historical_checks(spec, original, replicate)
    expect, _ = replicate.preflight(new_spec, 'test')
    if expect != 140680:
        raise ValueError('New arm training population differs')
    paths = input_paths(arm, replicate)
    print(f'Hashing {len(paths)} frozen inputs before the new fit', flush=True)
    plan = {'format': 'rees-agent-test-ablation-plan-v1', 'status': STATUS,
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'output_dir': output.relative_to(ROOT).as_posix(),
            'source_spec': SPEC, 'source_summary': SUMMARY, 'arm': arm,
            'features': 146, 'seeds': SEEDS, 'cap': 140680,
            'expected_queries': 97656, 'expected_users': 79302, 'expected_days': 14,
            'exclude_anchors': EXCLUDED, 'bootstrap': BOOTSTRAP,
            'contrasts': ['Hag-base', 'Hp-Hag'],
            'expected_recipe': exp.DEFAULT | arm['config'],
            'historical_evidence': evidence,
            'input_sha256': {p: digest(ROOT / p) for p in paths},
            'dependency_sha256': {p: digest(ROOT / p) for p in DEPENDENCIES},
            'interpretation_limits': [
                'The test and related validation results were already seen before this plan.',
                'No tuning or new feature search; the only change is removing DFS from frozen Hp.',
                'Intervals are marginal paired user-cluster sensitivities for each contrast and model seed.',
                'Two model seeds are not independent repetitions of the feature-generating agent.',
                'An interval including zero does not establish equivalence or absence of benefit.']}
    write_new(plan_path, plan)
    print(f'Plan saved to {plan_path}; inspect before running. No model fitted.', flush=True)
    return plan


def check_hashes(mapping):
    for p, expected in mapping.items():
        relative = Path(p)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Plan paths must be repository-relative')
        if digest(ROOT / p) != expected:
            raise ValueError(f'Frozen file changed: {p}')


def validate_plan(plan, arm, exp, replicate, output):
    expected = {'format': 'rees-agent-test-ablation-plan-v1', 'status': STATUS,
                'source_spec': SPEC, 'source_summary': SUMMARY,
                'arm': arm, 'features': 146, 'seeds': SEEDS, 'cap': 140680,
                'expected_queries': 97656, 'expected_users': 79302, 'expected_days': 14,
                'exclude_anchors': EXCLUDED, 'bootstrap': BOOTSTRAP,
                'contrasts': ['Hag-base', 'Hp-Hag'],
                'expected_recipe': exp.DEFAULT | arm['config'],
                'output_dir': output.relative_to(ROOT).as_posix()}
    for k, value in expected.items():
        if plan.get(k) != value:
            raise ValueError(f'Plan has an unexpected {k}')
    if set(plan['input_sha256']) != set(input_paths(arm, replicate)):
        raise ValueError('Plan input manifest is incomplete or has extra inputs')
    if set(plan['dependency_sha256']) != set(DEPENDENCIES):
        raise ValueError('Plan dependency manifest is incomplete or has extra code')


def compare_frames(base, hp, hag, spec, original, seed_index, previous_signature=None):
    base, hp = Q.pair(base, hp)
    _, hag = Q.pair(base.reset_index(drop=True), hag)
    signature = Q.check_seed_population(base, previous_signature)
    S.check_dates(base, spec['splits']['test'])
    S.check_dates(hag, spec['splits']['test'])
    pair = S.pair_frames(base.reset_index(drop=True), hp.reset_index(drop=True))
    S.check_summary(pair, original['all_days'], 'base', 'Hp', seed_index)
    keep = ~base.anchor.isin(EXCLUDED)
    base, hp, hag = base[keep], hp[keep], hag[keep]
    if len(base) != 97656 or base.anchor.nunique() != 14 or base.user_id.nunique() != 79302:
        raise ValueError('Primary test population differs')
    S.check_summary(S.pair_frames(base.reset_index(drop=True), hp.reset_index(drop=True)),
                    original['primary'], 'base', 'Hp', seed_index)
    contrasts = {}
    for name, a, b in (('Hag-base', base, hag), ('Hp-Hag', hag, hp)):
        delta = b.ndcg.to_numpy() - a.ndcg.to_numpy()
        contrasts[name] = {'reference_mean': float(a.ndcg.mean()), 'new_mean': float(b.ndcg.mean()),
                           'mean_delta': float(delta.mean()),
                           'user_cluster_bootstrap': S.bootstrap(delta, a.user_id, BOOTSTRAP['draws'], BOOTSTRAP['rng_seed'])}
    return {'seed_index': seed_index, 'model_seed': SEEDS[seed_index][0],
            'negative_sampling_seed': SEEDS[seed_index][1], 'queries': len(base),
            'users': int(base.user_id.nunique()), 'days': int(base.anchor.nunique()),
            'means': {name: {metric: float(f[metric].mean()) for metric in ('ndcg', 'recall', 'purchase_ndcg', 'purchase_recall')}
                      for name, f in (('base', base), ('Hag', hag), ('Hp', hp))},
            'contrasts': contrasts}, signature


def run(plan_path, output):
    plan_path = Path(plan_path).resolve()
    if not plan_path.is_relative_to(ROOT):
        raise ValueError('Plan must be inside the repository')
    output = output_path(output)
    plan_hash = digest(plan_path)
    plan = read_json(plan_path)
    exp, replicate = modules()
    spec, original = read_json(ROOT / SPEC), read_json(ROOT / SUMMARY)
    arm, new_spec = derive_arm(spec)
    validate_plan(plan, arm, exp, replicate, output)
    print('Checking frozen input and code hashes', flush=True)
    check_hashes(plan['input_sha256'])
    check_hashes(plan['dependency_sha256'])
    if historical_checks(spec, original, replicate) != plan['historical_evidence']:
        raise ValueError('Historical comparability differs from plan')
    expect, _ = replicate.preflight(new_spec, 'test')
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / 'started.json', {'created_utc': datetime.now(timezone.utc).isoformat(),
                                      'plan_sha256': plan_hash, 'plan': plan})
    started = time.monotonic()
    previous_cwd = Path.cwd()
    try:
        os.chdir(output)  # Isolate CatBoost temporary files from the historical run.
        print('Fitting the fixed Hag arm with both historical seed pairs', flush=True)
        frames, info = replicate.run_arm(arm, new_spec, 'test', SEEDS, {}, expect)
    finally:
        os.chdir(previous_cwd)
    if info['features'] != 146 or info['fits'] != plan['historical_evidence']['expected_fits']:
        raise ValueError('Actual feature count or training populations differ from plan')
    outputs = {}
    for i, f in enumerate(frames):
        path = output / f'test_Hag_s{i}.parquet'
        if path.exists():
            raise FileExistsError(path)
        replicate.write_parquet(f.reset_index(), path)
        outputs[path.relative_to(ROOT).as_posix()] = digest(path)
    write_new(output / 'training.json', info)
    print('Models completed; computing the two planned paired contrasts', flush=True)
    rows, signature = [], None
    for i, f in enumerate(frames):
        base = S.load(ROOT, f'artifacts/task1/v2020/replication/test_base_s{i}.parquet')
        hp = S.load(ROOT, f'artifacts/task1/v2020/replication/test_Hp_s{i}.parquet')
        row, signature = compare_frames(base, hp, f.reset_index(), spec, original, i, signature)
        rows.append(row)
    check_hashes(plan['input_sha256'])
    check_hashes(plan['dependency_sha256'])
    if digest(plan_path) != plan_hash:
        raise ValueError('Plan changed during execution')
    result = {'format': 'rees-agent-test-ablation-result-v1', 'status': plan['status'],
              'created_utc': datetime.now(timezone.utc).isoformat(), 'plan_sha256': plan_hash,
              'plan_path': plan_path.relative_to(ROOT).as_posix(),
              'input_sha256': plan['input_sha256'], 'dependency_sha256': plan['dependency_sha256'],
              'output_sha256': outputs, 'libraries': plan['historical_evidence']['libraries'],
              'python': sys.version, 'training': info, 'seconds': time.monotonic() - started,
              'seeds': rows, 'interpretation_limits': plan['interpretation_limits']}
    write_new(output / 'results.json', result)
    print(f'Results saved to {output / "results.json"}', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--prepare-plan', action='store_true')
    args = parser.parse_args()
    (prepare_plan if args.prepare_plan else run)(args.plan, args.output_dir)


if __name__ == '__main__':
    main()
