"""Check the current LaTeX table and OTTO plot against saved evidence, without data or training."""
import hashlib
import math
from datetime import date, timedelta
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/writeup/latex-report'


def check(root=ROOT):
    root = Path(root)
    report = root / "docs/writeup/latex-report"
    text = (report / 'main.tex').read_text(encoding='utf-8')
    values = json.loads((report / 'table-values.json').read_text(encoding='utf-8'))
    summary = json.loads((root / values['summary']).read_text(encoding='utf-8'))['primary']
    arms = values['arms']
    rows = [line for line in text.splitlines() if '&' in line and re.search(r'0\.\d{4}', line)]
    order = ('base', 'agent', 'dfs', 'Hp', 'F1')
    if len(rows) != len(order):
        raise ValueError('The REES46 table must contain the five checked rows')
    for arm, row in zip(order, rows):
        record = arms[arm]
        mean = sum(seed['mean'] for seed in record['seeds']) / len(record['seeds'])
        if abs(mean - record['mean']) > 1e-12:
            raise ValueError(f'{arm}: stored mean differs from seed means')
        if abs(mean - summary['metrics'][arm]['ndcg']) > 0.0000051:
            raise ValueError(f'{arm}: exact mean differs from published summary')
        if any(seed['queries'] != summary['queries'] for seed in record['seeds']):
            raise ValueError(f'{arm}: population differs from published summary')
        numbers = re.findall(r'[-+]?0\.\d{4}', row)
        expected = [f'{mean:.4f}']
        if arm != 'base':
            expected.append(f"{mean - arms['base']['mean']:+.4f}")
        if numbers != expected:
            raise ValueError(f'{arm}: displayed {numbers}, expected {expected}')
    # The plotting script obtains these values directly from the Kaggle receipts.
    import importlib.util
    spec = importlib.util.spec_from_file_location('report_figure', report / 'generate_figure.py')
    figure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(figure)
    figure.ROOT = root
    scores = figure.scores()
    if len(scores) != 4 or not all(a < b for a, b in zip(scores, scores[1:])):
        raise ValueError('OTTO receipts do not support three consecutive increases')
    gain = 100 * (scores[-1] / scores[0] - 1)
    if f'{gain:.1f}\\%' not in text:
        raise ValueError('OTTO relative improvement differs from receipts')
    omitted = check_saved_analyses(root, arms, summary)
    check_agent_test_ablation(root, arms, omitted, text)
    print('Saved tables, OTTO progression and available post-hoc summaries agree.')
    print(f'{len(omitted)} local artifact inputs were intentionally not read. This is a packaged-evidence consistency check, not a raw-data replay, bootstrap rerun, PDF inspection or independent experiment.')
    return omitted



def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, label, tolerance=1e-12):
    require(isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and math.isfinite(actual) and abs(actual - expected) <= tolerance,
            f'{label}: numeric mismatch')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'),
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'Invalid JSON number: {x}')))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(root, mapping, omitted):
    require(bool(mapping), 'Empty provenance map')
    for relative, expected in mapping.items():
        path = Path(relative)
        require(not path.is_absolute() and '..' not in path.parts, 'Nonportable provenance path')
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'Invalid SHA256')
        if path.parts[0] == 'artifacts':
            omitted.add(relative)
            continue
        require((root / path).is_file(), f'Missing packaged evidence: {relative}')
        require(digest(root / path) == expected, f'Hash mismatch: {relative}')


def seeds(rows):
    require(isinstance(rows, list) and len(rows) == 2, 'Both model seeds are required')
    require([r['seed_index'] for r in rows] == [0, 1], 'Expected ordered, unique seeds 0 and 1')
    return rows


def interval(row, key, clusters, plan, positive):
    b = row[key]
    require(type(clusters) is int and clusters > 0 and type(b['clusters']) is int
            and b['clusters'] == clusters, f'{key}: cluster population differs')
    require(b['draws'] == plan['draws'] and b['rng_seed'] == plan['rng_seed'], f'{key}: resampling differs from plan')
    close(b['mean_delta'], row['mean_delta'], key)
    bounds = b['ci95']
    require(isinstance(bounds, list) and len(bounds) == 2 and all(isinstance(x, (int, float))
            and math.isfinite(x) for x in bounds), f'{key}: invalid interval')
    lo, hi = bounds
    require(-1 <= lo <= hi <= 1, f'{key}: invalid interval order or metric bounds')
    if positive is not None:
        require(lo > 0 if positive else lo <= 0 <= hi, f'{key}: interval contradicts reported conclusion')


def means(row):
    for k in ('reference_mean', 'new_mean'):
        require(0 <= row[k] <= 1, f'{k}: outside metric range')
    close(row['new_mean'] - row['reference_mean'], row['mean_delta'], 'paired difference')
    require(type(row['users']) is int and type(row['queries']) is int
            and 0 < row['users'] <= row['queries'], 'Invalid user/query population')


def check_saved_analyses(root, arms, original):
    """Check published summaries and their packaged provenance, never open raw inputs."""
    omitted = set()
    sd = root / 'docs/writeup/sensitivity-2026-10-25'
    td = root / 'docs/writeup/secondary-2026-10-25'
    sp, sr, tp, tr = (load(p) for p in (sd/'plan.json', sd/'results.json', td/'plan.json', td/'results.json'))
    for plan, result, directory in ((sp, sr, sd), (tp, tr, td)):
        require(result['plan_sha256'] == digest(directory/'plan.json'), 'Plan hash mismatch')
        require(result['inputs_sha256'] == plan['input_sha256'], 'Plan/result input hashes differ')
        require(result['status'] == plan['status'] and 'post-hoc' in result['status'], 'Post-hoc status differs')
        require(bool(result['interpretation_limits']), 'Missing interpretation limits')
        hashes(root, plan['input_sha256'], omitted)
    require(sr['format'] == 'rees-sensitivity-v1' and tr['format'] == 'rees-secondary-v1', 'Unexpected result format')
    hashes(root, {'scripts/rees_sensitivity.py': sr['code_sha256']}, omitted)
    hashes(root, sr['summaries_sha256'], omitted)
    require(set(tr['code_sha256']) == {'scripts/rees_secondary.py', 'scripts/rees_sensitivity.py'},
            'Secondary code provenance must identify both analysis scripts')
    hashes(root, tr['code_sha256'], omitted)
    require(tr['dependency_sha256'] == tp['dependency_sha256'], 'Dependency maps differ')
    hashes(root, tp['dependency_sha256'], omitted)
    require(sp['test_2020']['seed_indices'] == tp['seed_indices'] == [0, 1], 'Plan seed set differs')
    require(sp['test_2020']['exclude_anchors'] == tp['exclude_anchors'] == ['2020-02-27', '2020-02-28'], 'Date exclusions differ')
    require(sp['expected_date_ranges']['test_2020'] == tp['expected_date_range'] == ['2020-02-14', '2020-02-29'], 'Test dates differ')
    require(sp['test_2020']['expected_queries'] == tp['expected_queries'] == original['queries'], 'Planned population differs')
    main = seeds(sr['test_2020'])
    n = original['queries']
    expected_dates = [(date(2020, 2, 14) + timedelta(days=i)).isoformat() for i in range(16)]
    expected_dates = [d for d in expected_dates if d not in tp['exclude_anchors']]
    for i, row in enumerate(main):
        require(row['queries'] == n and row['days'] == tp['expected_days'] == len(expected_dates), 'Main population differs')
        require(row['users'] == main[0]['users'], 'Main seed user counts differ')
        means(row)
        close(row['reference_mean'], arms['base']['seeds'][i]['mean'], 'Main baseline')
        close(row['new_mean'], arms['Hp']['seeds'][i]['mean'], 'Main Hp')
        for key, count in [('query_bootstrap', n), ('user_cluster_bootstrap', row['users']), ('day_cluster_bootstrap', row['days'])]:
            interval(row, key, count, sp, True)
        require(bool(row['day_cluster_caveat']), 'Missing day-cluster caveat')
        days = row['daily_and_leave_one_day_out']
        require([d['anchor'] for d in days] == expected_dates, 'Daily dates differ')
        require(all(isinstance(d['queries'], int) and d['queries'] > 0 for d in days), 'Invalid daily counts')
        require(sum(d['queries'] for d in days) == n, 'Daily counts differ from primary population')
        total = sum(d['queries'] * d['mean_delta'] for d in days)
        close(total / n, row['mean_delta'], 'Daily weighted mean')
        for d in days:
            require(d['mean_delta'] > 0 and d['leave_this_day_out_delta'] > 0, 'Daily/LODO conclusion differs')
            close(d['leave_this_day_out_delta'], (total - d['queries'] * d['mean_delta']) / (n - d['queries']), 'LODO')
    placebo = load(root / 'task1/runs/placebo-2026-10-21/result.json')
    require(set(sr['dfs_validation']) == set(sp['dfs_validation']['periods']) == {'2019', '2020'}, 'DFS periods differ')
    require(sp['dfs_validation']['seed_indices'] == [0, 1], 'DFS plan seeds differ')
    for period, group in sr['dfs_validation'].items():
        require(group['selection'] == ('validation half B' if period == '2019' else 'all validation'), 'DFS validation selection differs')
        rows = seeds(group['seeds'])
        for i, row in enumerate(rows):
            means(row)
            require(row['queries'] == placebo[period]['queries'] and row['days'] == 6, 'DFS population differs')
            require(row['users'] == rows[0]['users'], 'DFS seed users differ')
            for key, count in [('query_bootstrap', row['queries']), ('user_cluster_bootstrap', row['users'])]:
                interval(row, key, count, sp, False)
            for key, arm in [('reference_mean', 'Hag'), ('new_mean', 'Hp')]:
                close(row[key], placebo[period]['ndcg_by_seed'][arm][i], 'DFS source mean', .00000501)
        if period == '2020':
            require(rows[0]['mean_delta'] > 0 > rows[1]['mean_delta'], 'DFS 2020 signs differ from reported conclusion')
    metrics = ['recall', 'purchase_ndcg', 'purchase_recall']
    require(tp['secondary_metrics'] == metrics, 'Secondary metrics differ')
    secondary = seeds(tr['seeds'])
    purchase_population = None
    for i, row in enumerate(secondary):
        require(set(row['metrics']) == set(metrics), 'Incomplete secondary metrics')
        for metric in metrics:
            m = row['metrics'][metric]
            means(m)
            require(0 < m['queries'] <= n, 'Secondary population invalid')
            close(m['share_of_main_queries'], m['queries']/n, 'Secondary query share')
            require(m['excluded_no_purchase_queries'] == n - m['queries'], 'Secondary excluded count differs')
            if metric == 'recall':
                require((m['queries'], m['users']) == (n, main[i]['users']), 'Recall population differs')
            else:
                population = (m['queries'], m['users'])
                if purchase_population is None:
                    purchase_population = population
                require(population == purchase_population, 'Purchase populations differ across metrics/seeds')
            interval(m, 'user_cluster_bootstrap', m['users'], tp['bootstrap'], True)
        dist = row['ndcg_distribution']
        require(dist['queries'] == n, 'Distribution population differs')
        close(dist['mean_delta'], main[i]['mean_delta'], 'Distribution mean')
        groups = dist['groups']
        require(set(groups) == {'improved', 'worsened', 'unchanged'}, 'Missing distribution group')
        require(sum(g['queries'] for g in groups.values()) == n, 'Distribution counts do not sum')
        for name, g in groups.items():
            require(isinstance(g['queries'], int) and 0 <= g['queries'] <= n, 'Invalid distribution count')
            close(g['fraction'], g['queries']/n, 'Distribution fraction')
            close(g['contribution_to_overall_mean'], g['sum_delta']/n, 'Distribution contribution')
        require(groups['improved']['sum_delta'] > 0 > groups['worsened']['sum_delta'] and groups['unchanged']['sum_delta'] == 0, 'Distribution signs differ')
        close(sum(g['contribution_to_overall_mean'] for g in groups.values()), dist['mean_delta'], 'Contribution total')
        require([q['probability'] for q in dist['quantiles']] == tp['main_ndcg_distribution']['quantile_probabilities'], 'Quantile probabilities differ')
        qvalues = [q['delta'] for q in dist['quantiles']]
        require(all(math.isfinite(x) and -1 <= x <= 1 for x in qvalues) and qvalues == sorted(qvalues), 'Invalid quantile values')
    for metric in metrics:
        for key, arm in [('reference_mean', 'base'), ('new_mean', 'Hp')]:
            avg = sum(s['metrics'][metric][key] for s in secondary)/2
            close(avg, original['metrics'][arm][metric], 'Secondary published mean', .00000501)
    return omitted


AGENT_TEST_DIR = 'docs/writeup/agent-test-ablation-2026-10-25'
AGENT_TEST_MARKER = 'AGENT_TEST_ABLATION'
AGENT_RUNTIME = {'task1/exp.py', 'task1/model.py', 'task1/period.py', 'task1/replicate.py',
                 'task1/dfs.py', 'task1/extra.py', 'task1/posthoc.py'}
AGENT_DEPENDENCIES = AGENT_RUNTIME | {'scripts/rees_agent_test_ablation.py',
                                     'scripts/rees_sensitivity.py', 'scripts/rees_secondary.py', 'uv.lock'}


def check_agent_test_ablation(root, arms, omitted, text):
    """Check the optional published post-hoc result, never load its local parquet inputs."""
    directory = root / AGENT_TEST_DIR
    result_path = directory / 'results.json'
    if not result_path.exists():
        require(AGENT_TEST_MARKER not in text, 'Report cites missing agent test ablation result')
        return
    plan = load(directory / 'plan.json')
    result = load(result_path)
    spec_path = 'task1/runs/replication-2020/spec.json'
    summary_path = 'task1/runs/replication-2020/test.json'
    reference_path = 'docs/writeup/sensitivity-2026-10-25/plan.json'
    spec, original, reference = (load(root / p) for p in (spec_path, summary_path, reference_path))
    require(result['plan_sha256'] == digest(directory / 'plan.json'), 'Agent test plan hash mismatch')
    require(result['plan_path'] == AGENT_TEST_DIR + '/plan.json', 'Agent test plan path differs')
    require(plan['format'] == 'rees-agent-test-ablation-plan-v1'
            and result['format'] == 'rees-agent-test-ablation-result-v1', 'Agent test format differs')
    status = 'post-hoc analysis of an already opened test, not confirmatory'
    require(plan['status'] == result['status'] == status, 'Agent test post-hoc status differs')
    require(bool(plan['interpretation_limits']) and result['interpretation_limits'] == plan['interpretation_limits'],
            'Agent test interpretation limits differ')
    hp = next(a for a in spec['arms'] if a['name'] == 'Hp')
    require(hp['config']['extra'][:4] == ['dfs_p', 'dfs_c', 'dfs_b', 'dfs_u'], 'Original DFS membership differs')
    extras = hp['config']['extra'][4:]
    require(len(extras) == len(set(extras)) == 30 and all(x.startswith('agent_night20_') for x in extras),
            'Agent test needs exactly thirty agent tables')
    arm = {'name': 'Hag', 'config': dict(hp['config'], extra=extras)}
    seed_pairs = [[2026, 0], [7, 1]]
    excluded = ['2020-02-27', '2020-02-28']
    bootstrap = {'draws': 2000, 'rng_seed': 20261025}
    expected = {'source_spec': spec_path, 'source_summary': summary_path, 'arm': arm,
                'features': 146, 'seeds': seed_pairs, 'cap': 140680,
                'expected_queries': 97656, 'expected_users': 79302, 'expected_days': 14,
                'exclude_anchors': excluded, 'bootstrap': bootstrap, 'contrasts': ['Hag-base', 'Hp-Hag']}
    for key, value in expected.items():
        require(plan[key] == value, f'Agent test plan {key} differs')
    require(spec['seeds'] == seed_pairs and spec['excluded'] == excluded and spec['cap'] == 140680,
            'Original training specification differs')
    require(spec['splits']['refit'] == ['2020-01-15', '2020-02-13']
            and spec['splits']['test'] == ['2020-02-14', '2020-02-29'], 'Agent test date ranges differ')
    recipe = dict(loss='Logloss', iterations=500, depth=8, lr=.08, l2=10, seed=2026,
                  neg=50, neg_mode='random', neg_seed=0, half_life=None, train_frac=1.0,
                  drop=[], threads=10, **{k: v for k, v in arm['config'].items() if k != 'depth'})
    require(plan['expected_recipe'] == recipe, 'Agent test training recipe differs')
    days = [(date(2020, 1, 15) + timedelta(days=i)).isoformat() for i in range(46)]
    refs = {f'artifacts/task1/v2020/replication/test_{a}_s{i}.parquet' for a in ('base', 'Hp') for i in range(2)}
    inputs = {f"{arm['config']['days']}/{d}.parquet" for d in days}
    inputs |= {f'artifacts/task1/v2020/extra/{name}/{d}.parquet' for name in extras for d in days}
    inputs |= refs | {spec_path, summary_path, reference_path}
    require(set(plan['input_sha256']) == inputs, 'Agent test input manifest is incomplete or unexpected')
    require(set(plan['dependency_sha256']) == AGENT_DEPENDENCIES, 'Agent test dependency manifest is incomplete or unexpected')
    for key in ('input_sha256', 'dependency_sha256'):
        require(result[key] == plan[key], f'Agent test {key} differs from plan')
        hashes(root, plan[key], omitted)
    for path in refs:
        require(plan['input_sha256'][path] == reference['input_sha256'][path], 'Agent test reference hash differs')
    stamp = original['run']['log'][-1]['stamp']
    require(original['spec'] == spec and original['run']['seeds'] == seed_pairs and original['run']['over'] == {},
            'Original test recipe differs')
    for path in AGENT_RUNTIME:
        require(plan['dependency_sha256'][path] == stamp['files'][path], 'Agent test runtime differs from original')
    fits = [{'fit_queries': 140680, 'train_rows': 7136760}] * 2
    expected_evidence = {'original_input_metadata_sha256': stamp['inputs'], 'libraries': stamp['libs'], 'expected_fits': fits}
    require(plan['historical_evidence'] == expected_evidence, 'Agent test historical evidence differs')
    require(result['libraries'] == stamp['libs'], 'Agent test libraries differ')
    old_arms = {a['arm']: a for a in original['arms']}
    require(old_arms['base']['fits'] == old_arms['Hp']['fits'] == fits, 'Original fit populations differ')
    training = result['training']
    require(training['arm'] == 'Hag' and training['features'] == 146 and training['fits'] == fits,
            'Agent test training population or features differ')
    require(type(training['seconds']) is int and training['seconds'] >= 0, 'Invalid agent test training duration')
    require(isinstance(result['seconds'], (int, float)) and math.isfinite(result['seconds'])
            and result['seconds'] >= 0, 'Invalid agent test elapsed duration')
    output = Path(plan['output_dir'])
    require(not output.is_absolute() and '..' not in output.parts and output.parts[:2] == ('artifacts', 'task1')
            and len(output.parts) > 2 and not output.is_relative_to('artifacts/task1/v2020/replication'),
            'Agent test output is not isolated')
    expected_outputs = {(output / f'test_Hag_s{i}.parquet').as_posix() for i in range(2)}
    require(set(result['output_sha256']) == expected_outputs, 'Agent test output manifest differs')
    hashes(root, result['output_sha256'], omitted)
    metrics = {'ndcg', 'recall', 'purchase_ndcg', 'purchase_recall'}
    for i, row in enumerate(seeds(result['seeds'])):
        require((row['model_seed'], row['negative_sampling_seed']) == tuple(seed_pairs[i]), 'Agent test seed pair differs')
        require(type(row['queries']) is int and type(row['users']) is int and type(row['days']) is int
                and (row['queries'], row['users'], row['days']) == (97656, 79302, 14), 'Agent test population differs')
        require(set(row['means']) == {'base', 'Hag', 'Hp'}, 'Agent test mean arms differ')
        for name, values in row['means'].items():
            require(set(values) == metrics, 'Agent test metric set differs')
            for value in values.values():
                require(isinstance(value, (int, float)) and not isinstance(value, bool)
                        and math.isfinite(value) and 0 <= value <= 1, 'Invalid agent test metric')
        for name in ('base', 'Hp'):
            close(row['means'][name]['ndcg'], arms[name]['seeds'][i]['mean'], 'Agent test reference mean')
        require(set(row['contrasts']) == {'Hag-base', 'Hp-Hag'}, 'Agent test contrasts differ')
        for name, a, b in [('Hag-base', 'base', 'Hag'), ('Hp-Hag', 'Hag', 'Hp')]:
            contrast = row['contrasts'][name]
            close(contrast['reference_mean'], row['means'][a]['ndcg'], 'Agent test contrast reference')
            close(contrast['new_mean'], row['means'][b]['ndcg'], 'Agent test contrast new')
            close(contrast['mean_delta'], contrast['new_mean'] - contrast['reference_mean'], 'Agent test contrast direction')
            interval(contrast, 'user_cluster_bootstrap', row['users'], bootstrap, None)

    if AGENT_TEST_MARKER in text:
        lines = text.splitlines()
        markers = [i for i, line in enumerate(lines) if line.strip() == '% ' + AGENT_TEST_MARKER]
        require(len(markers) == 1, 'Expected one agent test display marker')
        paragraph = next((line for line in lines[markers[0] + 1:] if line.strip()), '')
        averages = {name: sum(row['means'][name]['ndcg'] for row in result['seeds']) / 2
                    for name in ('Hag', 'base')}
        require(averages['base'] > 0, 'Cannot display relative gain against zero baseline')
        expected_means = [f"{averages[name]:.4f}" for name in ('Hag', 'base')]
        displayed_means = re.findall(r'(?<![\d.])[-+]?\d+\.\d{4}(?!\d)', paragraph)
        require(displayed_means == expected_means, 'Agent test displayed means differ')
        gain = 100 * (averages['Hag'] / averages['base'] - 1)
        displayed_gain = re.findall(r'(?<![\d.])[-+]?\d+\.\d+\\%', paragraph)
        require(displayed_gain == [f'{gain:.1f}\\%'], 'Agent test displayed relative gain differs')
        # Russian prose about CI signs and interpretation is reviewed independently.


if __name__ == '__main__':
    check()
