"""Post-hoc secondary metrics from saved REES46 predictions; never fits a model."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import numpy as np

try:
    from scripts import rees_sensitivity as S
except ModuleNotFoundError:
    import rees_sensitivity as S

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'docs/writeup/secondary-2026-10-25/plan.json'
OUTPUT = 'docs/writeup/secondary-2026-10-25/results.json'
SUMMARY = 'task1/runs/replication-2020/test.json'
PREVIOUS = 'docs/writeup/sensitivity-2026-10-25/results.json'
METRICS = ('recall', 'purchase_ndcg', 'purchase_recall')
QUANTILES = (0, .01, .1, .25, .5, .75, .9, .99, 1)


def validate(frame):
    out = S.validate_frame(frame)
    if not set(METRICS) <= set(frame.columns):
        raise ValueError('Missing secondary metric')
    by_qid = frame.set_index('qid')
    for metric in METRICS:
        values = by_qid.loc[out.index, metric].to_numpy(dtype=float)
        missing = np.isnan(values)
        if metric == 'recall' and missing.any():
            raise ValueError('Recall has missing values')
        present = values[~missing]
        if not np.isfinite(present).all() or ((present < 0) | (present > 1)).any():
            raise ValueError('Secondary metric must be finite and in [0,1] when defined')
        out[metric] = values
    if not out.purchase_ndcg.isna().equals(out.purchase_recall.isna()):
        raise ValueError('Purchase metrics have different applicability masks')
    return out


def pair(reference, new):
    a, b = validate(reference), validate(new)
    if not a.index.equals(b.index):
        raise ValueError('Query keys differ before filtering')
    if not a.purchase_ndcg.isna().equals(b.purchase_ndcg.isna()):
        raise ValueError('Purchase applicability differs between arms')
    return a, b


def population_signature(frame):
    return tuple(frame.qid), tuple(frame.purchase_ndcg.notna())


def check_seed_population(frame, previous):
    current = population_signature(frame)
    if previous is not None and current != previous:
        raise ValueError('Query population or purchase applicability differs between seeds')
    return current


def metric_summary(a, b, metric, draws, rng_seed):
    keep = a[metric].notna()
    if not keep.equals(b[metric].notna()):
        raise ValueError('Metric applicability differs')
    if not keep.any():
        raise ValueError('No applicable metric queries')
    ref, new = a.loc[keep, metric], b.loc[keep, metric]
    delta = new.to_numpy() - ref.to_numpy()
    return {'queries': int(keep.sum()), 'share_of_main_queries': float(keep.mean()), 'excluded_no_purchase_queries': int((~keep).sum()),
            'users': int(a.loc[keep, 'user_id'].nunique()),
            'reference_mean': float(ref.mean()), 'new_mean': float(new.mean()),
            'mean_delta': float(delta.mean()),
            'user_cluster_bootstrap': S.bootstrap(delta, a.loc[keep, 'user_id'], draws, rng_seed)}


def distribution(delta, quantiles=QUANTILES):
    d = np.asarray(delta, dtype=float)
    if d.ndim != 1 or not len(d) or not np.isfinite(d).all():
        raise ValueError('Invalid paired NDCG differences')
    result = {'queries': len(d), 'mean_delta': float(d.mean()), 'groups': {}}
    for name, keep in [('improved', d > 0), ('worsened', d < 0), ('unchanged', d == 0)]:
        total = float(d[keep].sum())
        result['groups'][name] = {'queries': int(keep.sum()), 'fraction': float(keep.mean()),
                                  'sum_delta': total, 'contribution_to_overall_mean': total / len(d)}
    groups = result['groups'].values()
    if sum(g['queries'] for g in groups) != len(d):
        raise ValueError('Distribution categories do not partition the population')
    if not np.isclose(sum(g['contribution_to_overall_mean'] for g in result['groups'].values()), d.mean(), atol=1e-14, rtol=0):
        raise ValueError('Signed contributions do not sum to overall mean')
    result['quantiles'] = [{'probability': q, 'delta': float(v)}
                           for q, v in zip(quantiles, np.quantile(d, quantiles))]
    result['interpretation'] = 'Exact numerical ties; query-level changes, not users or satisfaction. Descriptive only.'
    return result


def run(root, plan_path, output):
    root, plan_path, output = Path(root).resolve(), Path(plan_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Output already exists; historical results are never overwritten')
    start = time.monotonic()
    code = {str(Path(__file__).resolve()): S.digest(__file__),
            str(Path(S.__file__).resolve()): S.digest(S.__file__)}
    plan_hash = S.digest(plan_path)
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if tuple(plan['secondary_metrics']) != METRICS or tuple(plan['main_ndcg_distribution']['quantile_probabilities']) != QUANTILES:
        raise ValueError('Unexpected metrics or descriptive quantiles')
    test = plan
    if test['seed_indices'] != [0, 1]:
        raise ValueError('Both historical model seeds are required')
    hashes = plan['input_sha256']
    S.check_hashes(root, hashes)
    S.check_hashes(root, plan['dependency_sha256'])
    for path in (SUMMARY, PREVIOUS):
        if path not in hashes:
            raise ValueError('Missing pinned source summary')
    original = json.loads((root / SUMMARY).read_text())
    previous = json.loads((root / PREVIOUS).read_text())
    previous_seeds = {x['seed_index']: x for x in previous['test_2020']}
    rows, seed_signature, used = [], None, set()
    for seed_index in test['seed_indices']:
        paths = [f'artifacts/task1/v2020/replication/test_{arm}_s{seed_index}.parquet' for arm in ('base', 'Hp')]
        if not set(paths) <= hashes.keys():
            raise ValueError('Missing pinned parquet source')
        used.update(paths)
        a, b = pair(*(S.load(root, p) for p in paths))
        S.check_dates(a, test['expected_date_range'])
        seed_signature = check_seed_population(a, seed_signature)
        keep = ~a.anchor.isin(test['exclude_anchors'])
        a, b = a[keep], b[keep]
        S.check_dates(a, test['expected_date_range'], test['exclude_anchors'])
        if len(a) != test['expected_queries'] or a.anchor.nunique() != test['expected_days']:
            raise ValueError('Primary query count differs')
        prior = previous_seeds[seed_index]
        if len(a) != prior['queries'] or a.user_id.nunique() != prior['users']:
            raise ValueError('Population differs from prior sensitivity analysis')
        for frame, key in ((a, 'reference_mean'), (b, 'new_mean')):
            if abs(float(frame.ndcg.mean()) - prior[key]) > 1e-12:
                raise ValueError('NDCG source mean differs from prior analysis')
        print(f'Analysing secondary metrics for seed {seed_index}', flush=True)
        metrics = {m: metric_summary(a, b, m, plan['bootstrap']['draws'], plan['bootstrap']['rng_seed']) for m in METRICS}
        if abs(float((b.ndcg - a.ndcg).mean()) - prior['mean_delta']) > 1e-12:
            raise ValueError('Main mean delta differs from prior sensitivity analysis')
        rows.append({'seed_index': seed_index, 'metrics': metrics,
                     'ndcg_distribution': distribution(b.ndcg.to_numpy() - a.ndcg.to_numpy(), plan['main_ndcg_distribution']['quantile_probabilities'])})
    if used != {p for p in hashes if p.endswith('.parquet')}:
        raise ValueError('Unanalysed parquet inputs in plan')
    for metric in METRICS:
        for key, arm in (('reference_mean', 'base'), ('new_mean', 'Hp')):
            mean = np.mean([r['metrics'][metric][key] for r in rows])
            if abs(mean - original['primary']['metrics'][arm][metric]) > .00000501:
                raise ValueError('Secondary mean differs from original rounded summary')
    S.check_hashes(root, hashes)
    S.check_hashes(root, plan['dependency_sha256'])
    if S.digest(plan_path) != plan_hash or any(S.digest(p) != h for p, h in code.items()):
        raise ValueError('Plan or implementation changed during computation')
    result = {'format': 'rees-secondary-v1', 'status': plan['status'], 'plan_sha256': plan_hash,
              'code_sha256': {'scripts/rees_secondary.py': code[str(Path(__file__).resolve())],
                              'scripts/rees_sensitivity.py': code[str(Path(S.__file__).resolve())]},
              'inputs_sha256': hashes, 'dependency_sha256': plan['dependency_sha256'], 'created_utc': datetime.now(timezone.utc).isoformat(),
              'seconds': time.monotonic() - start, 'python': sys.version,
              'libraries': {p: importlib.metadata.version(p) for p in ('numpy', 'pandas', 'duckdb')},
              'seeds': rows, 'interpretation_limits': plan['interpretation_limits']}
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        handle.write(payload)
    print(f'Saved post-hoc secondary analysis to {output}; no training or predictions.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    run(args.root, args.plan or args.root / PLAN, args.output or args.root / OUTPUT)


if __name__ == '__main__':
    main()
