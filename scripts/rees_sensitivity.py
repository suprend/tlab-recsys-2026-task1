"""Post-hoc REES46 sensitivity from saved per-query metrics; no fitting or prediction.

Run from the repository root:
  .venv/bin/python scripts/rees_sensitivity.py
The output must not exist. Historical metrics and the fixed plan are read-only.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'docs/writeup/sensitivity-2026-10-25/plan.json'
OUTPUT = 'docs/writeup/sensitivity-2026-10-25/results.json'
SUMMARIES = ('task1/runs/replication-2020/test.json',
             'task1/runs/placebo-2026-10-21/result.json')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_frame(frame):
    """Validate every row before selection; infer the date/user from the explicit qid."""
    if not {'qid', 'ndcg'} <= set(frame.columns):
        raise ValueError('Missing qid or ndcg')
    if frame.empty or frame.qid.isna().any() or frame.qid.duplicated().any():
        raise ValueError('Empty frame, null qid or duplicate qid')
    parsed = frame.qid.str.extract(r'^(\d{4}-\d{2}-\d{2}):(\d+)$')
    if parsed.isna().any().any():
        raise ValueError('qid must be date:user_id')
    dates = pd.to_datetime(parsed[0], format='%Y-%m-%d', errors='raise').dt.strftime('%Y-%m-%d')
    if 'anchor' in frame:
        anchors = pd.to_datetime(frame.anchor, errors='raise').dt.strftime('%Y-%m-%d')
        if anchors.isna().any() or not np.array_equal(anchors, dates):
            raise ValueError('anchor disagrees with qid date')
    values = frame.ndcg.to_numpy(dtype=float)
    if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError('NDCG must be finite and in [0,1]')
    if 'half' in frame and (frame.half.isna().any() or not frame.half.isin(['A', 'B']).all()):
        raise ValueError('Invalid validation half')
    out = frame[['qid', 'ndcg'] + (['half'] if 'half' in frame else [])].copy()
    out['anchor'] = dates.to_numpy()
    out['user_id'] = parsed[1].to_numpy()
    return out.sort_values('qid', kind='stable').set_index('qid', drop=False)


def pair_frames(reference, new, half=None, excluded=()):
    """Require complete pairing before any filtering; never intersect missing key sets."""
    a, b = validate_frame(reference), validate_frame(new)
    if not a.index.equals(b.index):
        raise ValueError('Reference and new query keys differ')
    if ('half' in a) != ('half' in b):
        raise ValueError('Only one arm provides validation halves')
    if 'half' in a and not a.half.equals(b.half):
        raise ValueError('Validation halves differ between arms')
    if half is not None:
        if 'half' not in a or half not in ('A', 'B'):
            raise ValueError('Requested half unavailable')
        keep = a.half.eq(half)
        a, b = a[keep], b[keep]
    keep = ~a.anchor.isin(excluded)
    a, b = a[keep], b[keep]
    if a.empty:
        raise ValueError('Selection leaves no queries')
    out = a[['qid', 'anchor', 'user_id']].copy()
    out['reference'] = a.ndcg.astype(float)
    out['new'] = b.ndcg.astype(float)
    out['delta'] = out.new - out.reference
    return out


def cluster_totals(delta, labels):
    delta = np.asarray(delta, dtype=float)
    labels = np.asarray(labels)
    if delta.ndim != 1 or len(delta) != len(labels) or not len(delta) or not np.isfinite(delta).all():
        raise ValueError('Invalid paired differences or cluster labels')
    codes, unique = pd.factorize(labels, sort=True)
    if (codes < 0).any():
        raise ValueError('Missing cluster label')
    return np.bincount(codes, weights=delta), np.bincount(codes), unique


def resampled_means(sums, counts, indices):
    """Recompute the query-weighted mean after resampling whole clusters."""
    return sums[indices].sum(axis=1) / counts[indices].sum(axis=1)


def bootstrap(delta, labels, draws, seed):
    if draws < 2:
        raise ValueError('At least two draws required')
    sums, counts, unique = cluster_totals(delta, labels)
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for start in range(0, draws, 32):
        end = min(draws, start + 32)
        indices = rng.integers(0, len(unique), size=(end - start, len(unique)))
        means[start:end] = resampled_means(sums, counts, indices)
    return {'mean_delta': float(sums.sum() / counts.sum()),
            'ci95': np.percentile(means, [2.5, 97.5]).tolist(),
            'clusters': len(unique), 'draws': draws, 'rng_seed': seed}


def day_diagnostics(pair):
    days = pair.groupby('anchor', sort=True).delta.agg(['sum', 'count', 'mean'])
    if len(days) < 2:
        raise ValueError('Leave-one-day-out requires at least two days')
    total_sum, total_count = float(days['sum'].sum()), int(days['count'].sum())
    return [{'anchor': str(day), 'queries': int(row['count']), 'mean_delta': float(row['mean']),
             'leave_this_day_out_delta': float((total_sum - row['sum']) / (total_count - row['count']))}
            for day, row in days.iterrows()]


def describe(pair, draws, seed, days=False):
    result = {'queries': len(pair), 'users': pair.user_id.nunique(), 'days': pair.anchor.nunique(),
              'reference_mean': float(pair.reference.mean()), 'new_mean': float(pair.new.mean()),
              'mean_delta': float(pair.delta.mean()),
              'query_bootstrap': bootstrap(pair.delta, pair.qid, draws, seed),
              'user_cluster_bootstrap': bootstrap(pair.delta, pair.user_id, draws, seed)}
    if days:
        result['day_cluster_bootstrap'] = bootstrap(pair.delta, pair.anchor, draws, seed)
        result['day_cluster_caveat'] = 'Only 14 observed day clusters; a sensitivity analysis, not a precise new confirmatory test or a joint user/day correction.'
        result['daily_and_leave_one_day_out'] = day_diagnostics(pair)
    return result


def check_summary(pair, summary, ref, new, seed):
    if len(pair) != summary['queries']:
        raise ValueError('Population differs from published summary')
    for col, arm in (('reference', ref), ('new', new)):
        expected = summary['ndcg_by_seed'][arm][seed]
        if abs(float(pair[col].mean()) - expected) > 0.00000501:
            raise ValueError(f'{arm} seed {seed}: mean differs from published summary')



def check_dates(pair, bounds, excluded=()):
    expected = set(pd.date_range(*bounds).strftime('%Y-%m-%d')) - set(excluded)
    if set(pair.anchor) != expected:
        raise ValueError('Observed dates differ from fixed plan')


def check_training_pair(reference, new, declarations, seed_index, period):
    """Compare saved recipes and population counts, not unavailable row-level training IDs."""
    for record in (reference, new):
        declared = declarations[record['name']]
        if any(record['cfg'].get(k) != v for k, v in declared.items() if k != 'name'):
            raise ValueError('Recorded configuration differs from frozen declaration')
    a, b = (dict(record['cfg']) for record in (reference, new))
    ae, be = a.pop('extra'), b.pop('extra')
    for cfg in (a, b):
        cfg.setdefault('cap', None)
    if a != b:
        raise ValueError('Training recipes differ beyond feature membership')
    if (a['seed'], a['neg_seed']) != ((2026, 0), (7, 1))[seed_index]:
        raise ValueError('Unexpected training seed or negative-sampling seed')
    if len(ae) != 30 or len(set(ae)) != 30 or be != ['dfs_p', 'dfs_c', 'dfs_b', 'dfs_u'] + ae:
        raise ValueError('Hp is not exactly DFS plus the same agent tables')
    if (reference['features'], new['features']) != (146, 274):
        raise ValueError('Unexpected number of features')
    if reference['train_rows'] != new['train_rows'] or reference['train_rows'] <= 0:
        raise ValueError('Training row counts differ')
    cap = 101959 if period == '2020' else None
    if a['cap'] != cap:
        raise ValueError('Training cap differs from the historical recipe')
    if reference.get('fit_queries') != 101959 or (period == '2020' and new.get('fit_queries') != 101959):
        raise ValueError('Recorded training query count differs')
    return {'reference': reference['name'], 'new': new['name'], 'common_config': a,
            'train_rows': reference['train_rows'],
            'recorded_fit_queries': {'reference': reference.get('fit_queries'), 'new': new.get('fit_queries')},
            'limit': 'Matching recipes and recorded training counts; row-level training IDs are not compared.'}


def read_training_evidence(root, hashes):
    declarations, records = {}, {}
    for relative in ('task1/runs/grid-2026-10-20/grid.json',
                     'task1/runs/placebo-2026-10-21/queue-2019.json',
                     'task1/runs/placebo-2026-10-21/queue-2020.json'):
        if relative not in hashes:
            raise ValueError('Missing frozen declaration in plan')
        for record in json.loads((root / relative).read_text(encoding='utf-8')):
            if record['name'] in declarations:
                raise ValueError('Duplicate frozen declaration')
            declarations[record['name']] = record
    for period, directory in (('2019', 'v2'), ('2020', 'v2020')):
        relative = f'artifacts/task1/{directory}/exp/runs.jsonl'
        if relative not in hashes:
            raise ValueError('Missing saved training log in plan')
        wanted = {f'pl{period[2:]}_Hag_s{i}' for i in range(2)} | {
            f'grid_Hp_s{i}' if period == '2019' else f'pl20_Hp_s{i}' for i in range(2)}
        for line in (root / relative).read_text(encoding='utf-8').splitlines():
            record = json.loads(line)
            if record['name'] in wanted:
                if record['name'] in records:
                    raise ValueError('Ambiguous repeated training run name')
                records[record['name']] = record
        if not wanted <= records.keys():
            raise ValueError('Missing saved training run')
    return declarations, records


def load(root, relative):
    with duckdb.connect() as connection:
        return connection.execute('SELECT * FROM read_parquet(?)', [str(root / relative)]).df()


def check_hashes(root, hashes):
    for relative, expected in hashes.items():
        if digest(root / relative) != expected:
            raise ValueError(f'Input changed: {relative}')


def run(root, plan_path, output):
    root, plan_path, output = Path(root).resolve(), Path(plan_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'{output} already exists; original analysis output is not overwritten')
    started = time.monotonic()
    code_hash = digest(__file__)
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    hashes = plan['input_sha256']
    check_hashes(root, hashes)
    sources = {p: digest(root / p) for p in SUMMARIES}
    replication, placebo = (json.loads((root / p).read_text(encoding='utf-8')) for p in SUMMARIES)
    draws, seed = plan['draws'], plan['rng_seed']
    declarations, records = read_training_evidence(root, hashes)
    used = set()

    def read(path):
        if path not in hashes:
            raise ValueError(f'Input is not in the fixed plan: {path}')
        used.add(path)
        return load(root, path)

    test, dfs = [], {}
    previous_keys = None
    for index in plan['test_2020']['seed_indices']:
        a = read(f'artifacts/task1/v2020/replication/test_base_s{index}.parquet')
        b = read(f'artifacts/task1/v2020/replication/test_Hp_s{index}.parquet')
        all_days = pair_frames(a, b)
        pair = pair_frames(a, b, excluded=plan['test_2020']['exclude_anchors'])
        check_dates(all_days, plan['expected_date_ranges']['test_2020'])
        check_dates(pair, plan['expected_date_ranges']['test_2020'], plan['test_2020']['exclude_anchors'])
        if len(pair) != plan['test_2020']['expected_queries'] or pair.anchor.nunique() != 14:
            raise ValueError('Unexpected primary-test population or number of days')
        keys = (tuple(all_days.qid), tuple(pair.qid))
        if previous_keys is not None and keys != previous_keys:
            raise ValueError('Test seed populations differ')
        previous_keys = keys
        check_summary(pair, replication['primary'], 'base', 'Hp', index)
        check_summary(all_days, replication['all_days'], 'base', 'Hp', index)
        print(f'Analysing 2020 test seed {index}: {len(pair)} paired queries', flush=True)
        row = describe(pair, draws, seed, days=True)
        row.update(seed_index=index, all_days_restored={'queries': len(all_days),
                    'mean_delta': float(all_days.delta.mean()), 'reference_mean': float(all_days.reference.mean()),
                    'new_mean': float(all_days.new.mean())})
        test.append(row)
    for period in plan['dfs_validation']['periods']:
        rows, previous_keys = [], None
        for index in plan['dfs_validation']['seed_indices']:
            if period == '2019':
                ref = f'artifacts/task1/v2/exp/pl19_Hag_s{index}.parquet'
                new = f'artifacts/task1/v2/exp/grid_Hp_s{index}.parquet'
            elif period == '2020':
                ref = f'artifacts/task1/v2020/exp/pl20_Hag_s{index}.parquet'
                new = f'artifacts/task1/v2020/exp/pl20_Hp_s{index}.parquet'
            else:
                raise ValueError(f'Unexpected validation period: {period}')
            evidence = check_training_pair(records[Path(ref).stem], records[Path(new).stem], declarations, index, period)
            a, b = read(ref), read(new)
            all_pair = pair_frames(a, b)
            pair = pair_frames(a, b, half='B' if period == '2019' else None)
            check_dates(all_pair, plan['expected_date_ranges'][f'val_{period}'])
            check_dates(pair, plan['expected_date_ranges'][f'val_{period}'])
            # Validate the full halves as well as the selected population across model seeds.
            halves = tuple(validate_frame(a)['half'])
            keys = (tuple(all_pair.qid), tuple(pair.qid), halves)
            if previous_keys is not None and keys != previous_keys:
                raise ValueError('Validation seed populations or halves differ')
            previous_keys = keys
            check_summary(pair, placebo[period], 'Hag', 'Hp', index)
            print(f'Analysing {period} validation seed {index}: {len(pair)} paired queries', flush=True)
            rows.append(dict(seed_index=index, training_comparability=evidence, **describe(pair, draws, seed)))
        dfs[period] = {'selection': 'validation half B' if period == '2019' else 'all validation', 'seeds': rows}
    if used != {p for p in hashes if p.endswith('.parquet')}:
        raise ValueError('The fixed plan has unanalysed inputs')
    check_hashes(root, hashes)
    check_hashes(root, sources)
    if digest(__file__) != code_hash:
        raise ValueError('Analysis code changed during computation')
    if digest(plan_path) != plan_hash:
        raise ValueError('Plan changed during computation')
    result = {'format': 'rees-sensitivity-v1', 'status': plan['status'], 'plan_sha256': plan_hash,
              'code_sha256': code_hash, 'inputs_sha256': hashes, 'summaries_sha256': sources,
              'created_utc': datetime.now(timezone.utc).isoformat(), 'seconds': time.monotonic() - started,
              'libraries': {p: importlib.metadata.version(p) for p in ('numpy', 'pandas', 'duckdb')},
              'python': sys.version, 'estimand': plan['estimand'], 'test_2020': test, 'dfs_validation': dfs,
              'interpretation_limits': [plan['test_2020']['interpretation'], plan['dfs_validation']['interpretation'],
                                        'Separate marginal user and day sensitivities do not model all dependence jointly.',
                                        'Model seed repetitions are not independent runs of the feature-generating agent.']}
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        handle.write(payload)
    print(f'Post-hoc results saved to {output}; no training or predictions were performed.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--plan', type=Path, help='defaults to the fixed plan under --root')
    parser.add_argument('--output', type=Path, help='new output path; defaults to the result under --root')
    args = parser.parse_args()
    run(args.root, args.plan or args.root / PLAN, args.output or args.root / OUTPUT)


if __name__ == '__main__':
    main()
