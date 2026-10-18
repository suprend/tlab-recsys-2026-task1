"""Choose a frozen H&M v2 prefix from two independent development audits.

Only bounded JSON metadata, names and source bytes are read. No imports or
access to DuckDB, parquet, models, customer IDs or holdout targets are needed.
The pure choose() function also supports group widths and a marginal baseline;
this CLI intentionally implements only the predeclared prefix diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 'configs/datasets/hm-auto-v2.json'
PROTOCOL_SHA = '84f3e2db341358a72ae7938c90af0696f5926b91faba746f61b801a7f7cd8b8b'
ANCHORS = ['2020-09-02', '2020-09-09']
WIDTHS = [1, 3, 6]
OLD_PVC = ['artifacts/hm-campaign/generated/selected', 'artifacts/hm-campaign/confirmation/selected']
HEX = re.compile('[0-9a-f]{64}\\Z')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8'))


def finite_number(value):
    return type(value) is int or type(value) is float and math.isfinite(value)


def metrics_equal(actual, expected):
    """Same metric keys; exact integer counts and finite rates within 1e-12.

    The fractional tolerance matches frozen hm_result_audit.close. Audited
    points remain the selection input; this helper only checks compatibility
    with the producer's independently computed aggregates.
    """
    if not isinstance(actual, dict) or not isinstance(expected, dict) or set(actual) != set(expected):
        return False
    counts = {'queries', 'positive_queries', 'empty_target_queries', 'distinct_query_target_pairs'}
    for name, value in actual.items():
        other = expected[name]
        if name in counts:
            if type(value) is not int or type(other) is not int or value != other:
                return False
        elif not finite_number(value) or not finite_number(other) or abs(value-other) > 1e-12:
            return False
    return True


def choose(candidates, baseline):
    """Return chosen name plus every point/rejection, without reading any files.

    baseline is two weekly MAPs of the current bundle. Each candidate has name,
    width (number of additions), and weekly_maps. Widths may differ for groups.
    Strict positive marginal deltas on both weeks precede max-min/mean/width/name.
    """
    def maps(values):
        require(isinstance(values, (list, tuple)) and len(values) == 2 and
                all(finite_number(v) and 0 <= v <= 1 for v in values), 'Two finite weekly MAPs in [0,1] required')
        return list(values)
    baseline = maps(baseline)
    require(isinstance(candidates, (list, tuple)), 'Candidate list required')
    points, names = [], set()
    for item in candidates:
        name, width = item['name'], item['width']
        require(isinstance(name, str) and bool(name.strip()) and name not in names, 'Unique candidate names required')
        require(type(width) is int and width > 0, 'Positive addition width required')
        names.add(name)
        weekly = maps(item['weekly_maps'])
        deltas = [a-b for a, b in zip(weekly, baseline)]
        points.append(dict(name=name, width=width, weekly_maps=weekly, weekly_deltas=deltas,
            minimum_delta=min(deltas), mean_delta=sum(deltas)/2, eligible=all(d > 0 for d in deltas),
            rejections=[dict(week_index=i, reason='nonpositive point delta') for i, d in enumerate(deltas) if d <= 0]))
    eligible = [p for p in points if p['eligible']]
    winner = min(eligible, key=lambda p: (-p['minimum_delta'], -p['mean_delta'], p['width'], p['name'])) if eligible else None
    return dict(chosen=winner['name'] if winner else None, candidates=sorted(points, key=lambda p: p['name']))


def read_metadata(relative, records, expected=None):
    path = (ROOT/relative).resolve()
    require(path.is_relative_to(ROOT.resolve()) and path.suffix == '.json', 'Checkout JSON metadata required')
    require(path.stat().st_size <= 2*1024**2, 'Metadata JSON exceeds 2MiB bound')
    raw = path.read_bytes()
    sha = digest(raw)
    require(expected is None or sha == expected, 'Frozen metadata SHA256 mismatch: '+str(relative))
    name = path.relative_to(ROOT.resolve()).as_posix()
    require(name not in records or records[name] == sha, 'Metadata changed during read: '+name)
    records[name] = sha
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON property')
            value[key] = item
        return value
    def number(value):
        result = float(value)
        require(math.isfinite(result), 'Nonfinite JSON number')
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON constant')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_float=number, parse_constant=reject)


def fit_identity(report):
    return canonical(dict(inputs=report['inputs'], features=report['features'],
        hyperparameters=report['hyperparameters'], train_users=report['training_user_limit'],
        negative_sample=report['negative_sample'], sampling_seed=report['sampling_seed'],
        code=report['code'], runtime=report['runtime']))


def prefix_decision(audit_paths, output):
    implementation_sha = digest(Path(__file__).read_bytes())
    records = {}
    protocol = read_metadata(PROTOCOL, records, PROTOCOL_SHA)
    development, prefix = protocol['development'], protocol['prefix_diagnostic']
    require(protocol['version'] == 2 and development['anchors'] == ANCHORS and prefix['widths'] == WIDTHS,
            'Frozen v2 prefix protocol differs')
    recipe = dict(iterations=500, depth=8, l2_leaf_reg=10, seed=2026, task_type='GPU',
                  training_users=20000, negative_sample=20, sampling_seed=2026)
    require(canonical(development['recipe']) == canonical(recipe), 'Development recipe differs')
    frozen = protocol['v1_frozen']
    for name, expected in frozen['source'].items():
        require(Path(name).name == name and HEX.fullmatch(expected), 'Malformed frozen source identity')
        relative = 'scripts/'+name
        actual = digest((ROOT/relative).read_bytes())
        require(actual == expected, 'Frozen source SHA256 mismatch: '+name)
        records[relative] = actual
    checker = frozen['source']['hm_result_audit.py']
    lock = read_metadata('configs/datasets/hm-final-lock.json', records, frozen['lock_sha256'])
    read_metadata('configs/datasets/hm-campaign.json', records, frozen['campaign_sha256'])
    selected = read_metadata('artifacts/hm-campaign/feature-selection/manifest.json', records,
                             prefix['source_selection_sha256'])
    historical = read_metadata('artifacts/hm-campaign/audits/confirmation/report.json', records,
                               lock['provenance']['confirmation']['sha256'])
    require(historical.get('status') == 'PASS' and historical.get('checker_sha256') == checker,
            'Frozen historical confirmation audit differs')
    manifest_pins = {Path(item['path']).parent.name[:10]: item['sha256'] for item in lock['train_collections']}
    require(selected['status'] == 'selected' and selected['selected_programs'] == prefix['ranking'] and
            len(prefix['ranking']) == 12 and len(set(prefix['ranking'])) == 12, 'Frozen PVC ranking differs')
    manual, old = lock['features']['M'], lock['features']['selected']
    require(len(manual['numeric']) == 18 and len(manual['categorical']) == 5 and
            selected['manual_names'] == manual['numeric']+manual['categorical'] and
            old == dict(numeric=manual['numeric']+prefix['ranking'], categorical=manual['categorical']),
            'Frozen M23/PVC12 vectors differ')
    require(lock['feature_digest'] == selected['feature_contract_digest'], 'Frozen feature contract differs')
    hyperparameters = dict(lock['hyperparameters'], random_seed=2026)
    require(all(hyperparameters[k] == v for k, v in dict(iterations=500, depth=8, l2_leaf_reg=10,
            random_seed=2026, task_type='GPU', thread_count=4).items()), 'Frozen GPU reference recipe differs')
    bundles = [manual, old]
    for width in WIDTHS:
        item = prefix['files'][str(width)]
        require(item['width'] == width and item['path'] == f'artifacts/hm-auto-v2/prefix{width}_names.json',
                'Prefix names path/width differs')
        names = read_metadata(item['path'], records, item['sha256'])
        require(names == selected['manual_names']+prefix['ranking'][:width], 'Prefix feature names differ')
        bundles.append(dict(numeric=manual['numeric']+prefix['ranking'][:width], categorical=manual['categorical']))
    require(len(audit_paths) == 2, 'Exactly two ordered prefix audits required')
    require(len(development['references']) == 2, 'Two frozen manual reference paths required')
    weeks, all_fit_provenance, shared_inputs = [], [], {}
    for fold, anchor in enumerate(ANCHORS):
        relative = f'artifacts/hm-auto-v2/audits/prefix-{anchor}/report.json'
        require(Path(audit_paths[fold]).resolve() == (ROOT/relative).resolve(), 'Prefix audit path/order differs')
        audit = read_metadata(relative, records)
        require(audit.get('format') == 'hm-independent-result-audit-v1' and audit.get('status') == 'PASS' and
                audit.get('checker_sha256') == checker and 'final_lock_sha256' not in audit,
                'PASS frozen development checker audit required')
        require(audit.get('source_rebuild') == 'PASS: raw history-only SHA256 Q and full distinct weekly Y',
                'Independent source Q/Y rebuild required')
        collection = audit['collection']
        require(collection['anchor'] == anchor and collection['policy'] == 'C0-Q120' and
                collection['database_identity'] == lock['database'], 'Audit date/policy/database differs')
        for key in ('manifest_sha256', 'qcy_identity', 'candidate_identity'):
            require(isinstance(collection[key], str) and HEX.fullmatch(collection[key]), 'Malformed collection identity')
        collection_input = {key: collection[key] for key in ('anchor', 'manifest_sha256', 'qcy_identity', 'candidate_identity')}
        require(collection['manifest_sha256'] == manifest_pins[anchor], 'Frozen validation manifest SHA differs')
        require(len(audit['fits']) == 5, 'Exactly five ordered audit arms required')
        directories = [development['references'][fold], OLD_PVC[fold]] + [
            f'artifacts/hm-auto-v2/prefix{width}/{anchor}' for width in WIDTHS]
        require(directories[0] == ['artifacts/hm-campaign/gpu-manual-grid/manual_pilot500d8',
                'artifacts/hm-campaign/confirmation/M'][fold], 'Frozen manual reference path differs')
        points, inputs, populations = [], None, None
        for arm, (row, directory, features) in enumerate(zip(audit['fits'], directories, bundles)):
            require(type(row['arm']) is int and row['arm'] == arm and
                    Path(row['fit_directory']).resolve() == (ROOT/directory).resolve(), 'Audit arm path/order differs')
            report_path = directory+'/report.json'
            reference_sha = (lock['provenance']['manual']['sha256'] if fold == 0 and arm == 0 else
                             historical['fits'][arm]['report_sha256'] if fold == 1 and arm < 2 else None)
            require(reference_sha is None or row['report_sha256'] == reference_sha, 'Frozen reference report SHA differs')
            report = read_metadata(report_path, records, row['report_sha256'])
            require(report.get('format') == 'hm-experiment-fit-v1' and report.get('status') == 'completed' and
                    report.get('fit_count') == 1 and report.get('actual_trees') == 500 and
                    'final_lock_sha256' not in report, 'Completed development500 fit required')
            require(report['features'] == dict(features, contract_digest=lock['feature_digest']), 'Actual feature vector differs')
            require(canonical(report['hyperparameters']) == canonical(hyperparameters) and
                    report['training_user_limit'] == 20000 and report['negative_sample'] == 20 and
                    report['sampling_seed'] == 2026 and report['runtime'] == lock['implementation']['runtime'],
                    'Fit recipe/runtime differs from frozen reference')
            expected_code = {name: frozen['source'][name] for name in ('hm_experiment.py', 'hm_baseline.py')}
            require(report['code'] == expected_code and set(row['code']) == set(expected_code) and
                    all(row['code'][name] == dict(recorded_sha256=value, current_source_matches=True)
                        for name, value in expected_code.items()), 'Fit producer source differs')
            require(report['fit_identity'] == row['fit_identity'] == fit_identity(report), 'Fit identity mismatch')
            require([v['anchor'] for v in report['inputs']] == development['train_anchors'][fold]+[anchor] and
                    report['inputs'][-1] == collection_input, 'Development fold/input identity differs')
            for value in report['inputs']:
                require(set(value) == {'anchor', 'manifest_sha256', 'qcy_identity', 'candidate_identity'} and
                        all(isinstance(value[k], str) and HEX.fullmatch(value[k])
                            for k in ('manifest_sha256', 'qcy_identity', 'candidate_identity')) and
                        value['manifest_sha256'] == manifest_pins[value['anchor']], 'Frozen input identity differs')
            if inputs is None:
                inputs = report['inputs']
                for value in inputs:
                    old_input = shared_inputs.setdefault(value['anchor'], value)
                    require(value == old_input, 'Shared cross-fold Q/C/Y identity differs')
            require(report['inputs'] == inputs, 'Within-week train/validation Q/C/Y differs')
            metrics = row['metrics']
            require(metrics_equal(metrics, report['validation_metrics']), 'Audit/producer metrics differ')
            require(type(metrics['queries']) is int and metrics['queries'] == 20000 and
                    type(metrics['positive_queries']) is int and 0 < metrics['positive_queries'] <= 20000,
                    'Development query counts differ')
            population = {key: metrics[key] for key in ('queries', 'positive_queries', 'empty_target_queries',
                'distinct_query_target_pairs', 'candidate_query_coverage_conditional',
                'candidate_target_coverage_micro', 'oracle_map_at_12_conditional')}
            if populations is None:
                populations = population
            require(population == populations, 'Within-week evaluation Q/C/Y metadata differs')
            point = metrics['map_at_12_conditional']
            require(finite_number(point) and 0 <= point <= 1, 'Finite MAP in [0,1] required')
            points.append(point)
            all_fit_provenance.append(dict(anchor=anchor, arm=arm, path=report_path,
                report_sha256=records[report_path], fit_identity=report['fit_identity']))
        weeks.append(dict(anchor=anchor, collection=collection_input, population=populations, maps=points,
                          audit=dict(path=relative, sha256=records[relative])))
    baseline = [week['maps'][0] for week in weeks]
    decision = choose([dict(name=f'prefix{width}', width=width,
        weekly_maps=[week['maps'][arm] for week in weeks]) for arm, width in enumerate(WIDTHS, 2)], baseline)
    report = dict(format='hm-auto-prefix-decision-v2', status='completed', phase='prefix_diagnostic',
        chosen=decision['chosen'], next_action='symmetric_regularization' if decision['chosen'] else 'group_fallback',
        baseline=dict(name='M', weekly_maps=baseline), oldPVC12_weekly_maps=[w['maps'][1] for w in weeks],
        candidates=decision['candidates'], weeks=weeks, fits=all_fit_provenance,
        interpretation='Fixed prior PVC ranking; width diagnostic. Point eligibility is not a gain/quality test; development CIs are descriptive after search.',
        implementation_sha256=implementation_sha, provenance=dict(records))
    # Check freshness after the complete metadata computation and before mkdir.
    require(all(digest((ROOT/name).read_bytes()) == sha for name, sha in records.items()), 'Frozen inputs changed during decision')
    require(digest(Path(__file__).read_bytes()) == implementation_sha, 'Selector source changed during decision')
    output = Path(output).resolve()
    allowed = (ROOT/'artifacts/hm-auto-v2').resolve()
    require(output != allowed and output.is_relative_to(allowed), 'New output must be a child of artifacts/hm-auto-v2/')
    output.mkdir(parents=True, exist_ok=False)
    with (output/'report.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix-audits', type=Path, nargs=2, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = prefix_decision(args.prefix_audits, args.output)
    except Exception as error:
        print(json.dumps(dict(status='failed', error_type=type(error).__name__, message=str(error)[:2048])))
        return 1
    print(json.dumps(dict(status=result['status'], chosen=result['chosen'], next_action=result['next_action'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
