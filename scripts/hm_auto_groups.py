"""Metadata-only frozen H&M v2 greedy semantic-group decisions.

Stage1 checks seven ordered arms on each development week. Stage2 checks M,
the accepted first group, and four marginal extensions. No SQL, parquet,
native model, customer-ID or customer-holdout access is performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import hm_auto_select as selection

ROOT = Path(__file__).resolve().parents[1]
DIMS = ['product_type_no', 'colour_group_code', 'department_no', 'garment_group_no', 'index_code']
WIDTHS = [11, 11, 12, 12, 12]
GROUP_METADATA = 'artifacts/hm-auto-v2/groups/manifest.json'
GROUP_SHA256 = '6feb442f86f2993eaf8cf79155edd12c37648efd64c88a90455e1f80409d255a'
PREFIX_DECISION = 'artifacts/hm-auto-v2/decisions/prefix/report.json'
FIRST_DECISION = 'artifacts/hm-auto-v2/decisions/group1/report.json'
COUNT_KEYS = ('queries', 'positive_queries', 'empty_target_queries', 'distinct_query_target_pairs')
POPULATION_KEYS = COUNT_KEYS + ('candidate_query_coverage_conditional',
    'candidate_target_coverage_micro', 'oracle_map_at_12_conditional')
require = selection.require


def checked_metrics(actual, expected):
    """Exact integer counts; finite bounded float metrics may differ by1e-12."""
    require(isinstance(actual, dict) and isinstance(expected, dict) and set(actual) == set(expected),
            'Audit/producer metric keys differ')
    for metrics in (actual, expected):
        require(set(COUNT_KEYS) <= set(metrics), 'Evaluation counts missing')
        require(all(type(metrics[key]) is int and metrics[key] >= 0 for key in COUNT_KEYS),
                'Evaluation counts must be exact nonnegative integers')
        require(metrics['queries'] == 20000 and 0 < metrics['positive_queries'] <= 20000 and
                metrics['empty_target_queries'] == 20000-metrics['positive_queries'] and
                metrics['distinct_query_target_pairs'] >= metrics['positive_queries'],
                'Evaluation population counts differ')
        require(all(selection.finite_number(value) and 0 <= value <= 1
                    for key, value in metrics.items() if key not in COUNT_KEYS), 'Finite bounded metrics required')
    require(selection.metrics_equal(actual,expected), 'Audit/producer metrics differ beyond tolerance')


def population_matches(actual, expected):
    require(set(POPULATION_KEYS) <= set(actual) and set(POPULATION_KEYS) <= set(expected),
            'Evaluation Q/C/Y metadata missing')
    require(all(actual[key] == expected[key] if key in COUNT_KEYS else abs(actual[key]-expected[key]) <= 1e-12
                for key in POPULATION_KEYS), 'Within-week evaluation Q/C/Y metadata differs')


def read(relative, records, expected=None):
    require(ROOT.resolve() == selection.ROOT.resolve(), 'Selector checkout roots differ')
    return selection.read_metadata(relative, records, expected)


def source(name, records, expected=None):
    require(Path(name).name == name and name.endswith('.py'), 'Plain source filename required')
    relative = 'scripts/'+name
    path = (ROOT/relative).resolve()
    require(path.is_relative_to(ROOT.resolve()) and path.stat().st_size <= 2*1024**2,
            'Bounded checkout source required')
    sha = selection.digest(path.read_bytes())
    require(expected is None or sha == expected, 'Frozen source SHA256 mismatch: '+name)
    require(relative not in records or records[relative] == sha, 'Source changed during decision')
    records[relative] = sha
    return sha


def audit_weeks(context, records, audit_paths, directories, bundles):
    """Validate actual independent audit/fit metadata before returning MAPs."""
    protocol, lock, historical = context['protocol'], context['lock'], context['historical']
    frozen = protocol['v1_frozen']
    pins = {Path(item['path']).parent.name[:10]: item['sha256'] for item in lock['train_collections']}
    expected_code = {name: frozen['source'][name] for name in ('hm_experiment.py', 'hm_baseline.py')}
    parameters = dict(lock['hyperparameters'], random_seed=2026)
    require(all(parameters[key] == value for key, value in dict(iterations=500, depth=8,
            l2_leaf_reg=10, random_seed=2026, task_type='GPU', thread_count=4).items()), 'Frozen GPU recipe differs')
    require(len(audit_paths) == 2 and len(directories) == 2, 'Two ordered development folds required')
    weeks, fits, shared = [], [], {}
    for fold, anchor in enumerate(selection.ANCHORS):
        audit = read(audit_paths[fold], records)
        require(audit.get('format') == 'hm-independent-result-audit-v1' and audit.get('status') == 'PASS'
                and audit.get('checker_sha256') == frozen['source']['hm_result_audit.py']
                and 'final_lock_sha256' not in audit, 'PASS frozen development audit required')
        require(audit.get('source_rebuild') == 'PASS: raw history-only SHA256 Q and full distinct weekly Y',
                'Independent source Q/Y rebuild required')
        collection = audit['collection']
        require(collection['anchor'] == anchor and collection['policy'] == 'C0-Q120'
                and collection['database_identity'] == lock['database'], 'Audit date/policy/database differs')
        collection_input = {key: collection[key] for key in ('anchor','manifest_sha256','qcy_identity','candidate_identity')}
        require(collection['manifest_sha256'] == pins[anchor], 'Frozen validation manifest differs')
        require(len(audit['fits']) == len(bundles) == len(directories[fold]), 'Exact ordered audit arm count required')
        inputs = population = None
        points = []
        for arm, (row, directory, vector) in enumerate(zip(audit['fits'], directories[fold], bundles)):
            require(type(row['arm']) is int and row['arm'] == arm and
                    Path(row['fit_directory']).resolve() == (ROOT/directory).resolve(), 'Audit arm path/order differs')
            relative = directory+'/report.json'
            report = read(relative, records, row['report_sha256'])
            require(report.get('format') == 'hm-experiment-fit-v1' and report.get('status') == 'completed'
                    and type(report.get('fit_count')) is int and report['fit_count'] == 1
                    and type(report.get('actual_trees')) is int and report['actual_trees'] == 500
                    and 'final_lock_sha256' not in report, 'Completed development500 fit required')
            reference = (lock['provenance']['manual']['sha256'] if fold == 0 and arm == 0 else
                         historical['fits'][0]['report_sha256'] if fold == 1 and arm == 0 else
                         historical['fits'][1]['report_sha256'] if fold == 1 and directory == selection.OLD_PVC[1] else None)
            require(reference is None or row['report_sha256'] == reference, 'Frozen reference report differs')
            require(report['features'] == dict(vector, contract_digest=lock['feature_digest']), 'Actual feature vector differs')
            require(selection.canonical(report['hyperparameters']) == selection.canonical(parameters)
                    and selection.canonical(report['runtime']) == selection.canonical(lock['implementation']['runtime'])
                    and all(type(report[key]) is int and report[key] == value for key, value in
                            dict(training_user_limit=20000, negative_sample=20, sampling_seed=2026).items()),
                    'Fit recipe/runtime differs')
            require(report['code'] == expected_code and set(row['code']) == set(expected_code) and
                    all(row['code'][name].get('recorded_sha256') == sha and
                        row['code'][name].get('current_source_matches') is True
                        for name,sha in expected_code.items()), 'Fit producer source differs')
            require(report['fit_identity'] == row['fit_identity'] == selection.fit_identity(report), 'Fit identity mismatch')
            require([item['anchor'] for item in report['inputs']] == protocol['development']['train_anchors'][fold]+[anchor]
                    and report['inputs'][-1] == collection_input, 'Development fold/input identity differs')
            for item in report['inputs']:
                require(set(item) == {'anchor','manifest_sha256','qcy_identity','candidate_identity'} and
                        all(isinstance(item[key],str) and selection.HEX.fullmatch(item[key])
                            for key in ('manifest_sha256','qcy_identity','candidate_identity')) and
                        item['manifest_sha256'] == pins[item['anchor']], 'Frozen train/validation identity differs')
                previous = shared.setdefault(item['anchor'], item)
                require(item == previous, 'Shared cross-fold Q/C/Y identity differs')
            inputs = report['inputs'] if inputs is None else inputs
            require(report['inputs'] == inputs, 'Within-week Q/C/Y inputs differ')
            metrics = row['metrics']
            checked_metrics(metrics, report['validation_metrics'])
            current_population = {key:metrics[key] for key in POPULATION_KEYS}
            population = current_population if population is None else population
            population_matches(current_population, population)
            points.append(metrics['map_at_12_conditional'])
            fits.append(dict(anchor=anchor, arm=arm, path=relative, report_sha256=records[relative],
                             fit_identity=report['fit_identity']))
        weeks.append(dict(anchor=anchor, collection=collection_input, population=population, maps=points,
                          audit=dict(path=audit_paths[fold], sha256=records[audit_paths[fold]])))
    return weeks, fits


def context_and_prefix(records):
    protocol = read(selection.PROTOCOL, records, selection.PROTOCOL_SHA)
    require(protocol['version'] == 2 and protocol['development']['anchors'] == selection.ANCHORS
            and protocol['prefix_diagnostic']['widths'] == selection.WIDTHS, 'Frozen v2 development protocol differs')
    group_rule = protocol['group_fallback']
    require(group_rule['dimensions'] == DIMS and group_rule['step1_fits'] == 10
            and group_rule['step2_fits_max'] == 8, 'Frozen group budget/order differs')
    expected_recipe = dict(iterations=500, depth=8, l2_leaf_reg=10, seed=2026, task_type='GPU',
                           training_users=20000, negative_sample=20, sampling_seed=2026)
    require(selection.canonical(protocol['development']['recipe']) == selection.canonical(expected_recipe), 'Development recipe differs')
    frozen = protocol['v1_frozen']
    for name, expected in frozen['source'].items():
        source(name, records, expected)
    source('hm_auto_select.py', records)
    source('hm_auto_groups.py', records)
    lock = read('configs/datasets/hm-final-lock.json', records, frozen['lock_sha256'])
    read('configs/datasets/hm-campaign.json', records, frozen['campaign_sha256'])
    historical = read('artifacts/hm-campaign/audits/confirmation/report.json', records,
                      lock['provenance']['confirmation']['sha256'])
    require(historical.get('status') == 'PASS' and historical.get('checker_sha256') == frozen['source']['hm_result_audit.py'],
            'Frozen historical confirmation differs')
    prefix_rule = protocol['prefix_diagnostic']
    selected = read('artifacts/hm-campaign/feature-selection/manifest.json', records, prefix_rule['source_selection_sha256'])
    manual = lock['features']['M']
    require(len(manual['numeric']) == 18 and len(manual['categorical']) == 5
            and selected['manual_names'] == manual['numeric']+manual['categorical']
            and selected['feature_contract_digest'] == lock['feature_digest']
            and selected['status'] == 'selected' and selected['selected_programs'] == prefix_rule['ranking']
            and len(set(prefix_rule['ranking'])) == len(prefix_rule['ranking']) == 12, 'Frozen M/PVC vectors differ')
    old = dict(numeric=manual['numeric']+prefix_rule['ranking'], categorical=manual['categorical'])
    require(lock['features']['selected'] == old, 'Frozen oldPVC12 vector differs')
    require(protocol['development']['references'] == ['artifacts/hm-campaign/gpu-manual-grid/manual_pilot500d8',
            'artifacts/hm-campaign/confirmation/M'], 'Frozen manual reference paths differ')
    bundles = [manual, old]
    for width in selection.WIDTHS:
        item = prefix_rule['files'][str(width)]
        require(item['path'] == f'artifacts/hm-auto-v2/prefix{width}_names.json' and item['width'] == width,
                'Prefix namefile path/width differs')
        require(read(item['path'],records,item['sha256']) == selected['manual_names']+prefix_rule['ranking'][:width],
                'Prefix names differ')
        bundles.append(dict(numeric=manual['numeric']+prefix_rule['ranking'][:width], categorical=manual['categorical']))
    context = dict(protocol=protocol, lock=lock, historical=historical, manual=manual, old=old)
    directories = [[protocol['development']['references'][fold],selection.OLD_PVC[fold]]+
                   [f'artifacts/hm-auto-v2/prefix{width}/{anchor}' for width in selection.WIDTHS]
                   for fold,anchor in enumerate(selection.ANCHORS)]
    prefix_paths = [f'artifacts/hm-auto-v2/audits/prefix-{anchor}/report.json' for anchor in selection.ANCHORS]
    weeks, _ = audit_weeks(context,records,prefix_paths,directories,bundles)
    baseline = [week['maps'][0] for week in weeks]
    choice = selection.choose([dict(name=f'prefix{width}',width=width,
        weekly_maps=[week['maps'][arm] for week in weeks]) for arm,width in enumerate(selection.WIDTHS,2)],baseline)
    decision = read(PREFIX_DECISION,records)
    require(decision.get('format') == 'hm-auto-prefix-decision-v2' and decision.get('status') == 'completed'
            and decision.get('phase') == 'prefix_diagnostic' and decision.get('chosen') is None
            and decision.get('next_action') == 'group_fallback' and choice['chosen'] is None,
            'Completed rejected-prefix decision required before group fallback')
    require(decision['candidates'] == choice['candidates'] and decision['baseline'] == dict(name='M',weekly_maps=baseline),
            'Prefix decision differs from independently audited point rule')
    require(decision['implementation_sha256'] == records['scripts/hm_auto_select.py'], 'Prefix selector source differs')
    for name, sha in decision['provenance'].items():
        require(name in records and records[name] == sha, 'Prefix decision provenance differs or is stale')
    required = set(records)-{'scripts/hm_auto_select.py','scripts/hm_auto_groups.py',PREFIX_DECISION}
    require(set(decision['provenance']) == required, 'Prefix decision provenance is incomplete')
    groups = read(GROUP_METADATA,records,GROUP_SHA256)
    require(groups['format'] == 'hm-auto-v2-semantic-groups-v1' and groups['config_sha256'] == selection.PROTOCOL_SHA
            and list(groups['groups']) == DIMS and groups['manual_names'] == selected['manual_names'], 'Frozen groups differ')
    study = read('artifacts/hm-campaign/feature-study/manifest.json',records,groups['source_study_sha256'])
    require(study['format'] == 'hm-feature-selection-study-v1' and study['status'] == 'prepared'
            and study['plan_digest'] == selection.canonical(study['plan'])
            and study['plan']['feature_contract_digest'] == lock['feature_digest'], 'Frozen study differs')
    pool = study['plan']['pool']
    require(len(pool) == len({item['name'] for item in pool}) == 58 and
            all(item['dimension'] in DIMS for item in pool), 'Frozen pool must contain58 distinct group programs')
    for dimension,width in zip(DIMS,WIDTHS):
        group = groups['groups'][dimension]
        names = sorted(item['name'] for item in pool if item['dimension'] == dimension)
        expected_file = f'artifacts/hm-auto-v2/groups/{dimension}_names.json'
        require(group['programs'] == names and group['width'] == len(names) == width
                and group['names_file'] == expected_file and not set(names).intersection(selected['manual_names']),
                'Exact group membership/width/path differs')
        require(read(expected_file,records,group['names_sha256']) == selected['manual_names']+names, 'Group namefile differs')
    context['groups'] = groups['groups']
    return context


def group_weeks(context, records, stage, first=None):
    groups,manual = context['groups'],context['manual']
    candidates = DIMS if stage == 1 else [dimension for dimension in DIMS if dimension != first]
    previous = [] if stage == 1 else groups[first]['programs']
    base = context['old'] if stage == 1 else dict(numeric=manual['numeric']+previous,categorical=manual['categorical'])
    bundles = [manual,base]
    for dimension in candidates:
        programs = previous+groups[dimension]['programs']
        require(len(set(programs)) == len(programs), 'Group programs overlap')
        bundles.append(dict(numeric=manual['numeric']+programs,categorical=manual['categorical']))
        if stage == 2:
            names_path = f'artifacts/hm-auto-v2/group2-names/{first}__{dimension}_names.json'
            require(read(names_path,records) == manual['numeric']+manual['categorical']+programs, 'Stage2 namefile differs')
    paths = [f'artifacts/hm-auto-v2/audits/group{stage}-{anchor}/report.json' for anchor in selection.ANCHORS]
    directories = []
    for fold,anchor in enumerate(selection.ANCHORS):
        current = selection.OLD_PVC[fold] if stage == 1 else f'artifacts/hm-auto-v2/group1/{first}/{anchor}'
        additions = [f'artifacts/hm-auto-v2/group1/{dimension}/{anchor}' if stage == 1 else
                     f'artifacts/hm-auto-v2/group2/{first}__{dimension}/{anchor}' for dimension in candidates]
        directories.append([context['protocol']['development']['references'][fold],current]+additions)
    weeks,fits = audit_weeks(context,records,paths,directories,bundles)
    baseline = [week['maps'][0 if stage == 1 else 1] for week in weeks]
    decision = selection.choose([dict(name=dimension,width=len(previous)+groups[dimension]['width'],
        weekly_maps=[week['maps'][arm] for week in weeks]) for arm,dimension in enumerate(candidates,2)],baseline)
    return weeks,fits,baseline,decision


def compose(context,records,stage,weeks,fits,baseline,decision,first=None):
    chosen = decision['chosen']
    selected = ([chosen] if chosen else []) if stage == 1 else [first]+([chosen] if chosen else [])
    programs = [name for dimension in selected for name in context['groups'][dimension]['programs']]
    manual = context['manual']['numeric']+context['manual']['categorical']
    result = dict(format='hm-auto-group-decision-v2',status='completed',stage=stage,chosen=chosen,
        selected_groups=selected,selected_programs=programs,selected_names=manual+programs,width=len(programs),
        baseline=dict(name='M' if stage == 1 else first,weekly_maps=baseline),
        candidates=decision['candidates'],weeks=weeks,fits=fits,
        next_action=('group_step2' if stage == 1 else 'symmetric_regularization') if selected else 'retain_M_no_test',
        reuse_exact_M=not selected,run_symmetric_L2=bool(selected) and stage == 2,preserve_untouched_customer_holdout=True,
        interpretation='Strict positive marginal point MAP on both development weeks; max-min, mean, fewer additions, name. Not proof of gain. No customer-holdout access.',
        implementation_sha256=records['scripts/hm_auto_groups.py'],provenance=dict(records))
    if stage == 1 and chosen:
        result['stage2_plan'] = [dict(name=dimension,width=len(programs)+context['groups'][dimension]['width'],
            names_file=f'artifacts/hm-auto-v2/group2-names/{chosen}__{dimension}_names.json',
            names=manual+programs+context['groups'][dimension]['programs']) for dimension in DIMS if dimension != chosen]
    return result


def group_decision(audit_paths,output,*,stage=1):
    require(type(stage) is int and stage in (1,2), 'Stage must be1 or2')
    records = {}
    context = context_and_prefix(records)
    first = None
    if stage == 2:
        first_records = dict(records)
        accepted = read(FIRST_DECISION,records)
        previous = group_weeks(context,first_records,1)
        expected = compose(context,first_records,1,*previous)
        require(selection.canonical(accepted) == selection.canonical(expected), 'Accepted first-group decision differs or is stale')
        first = accepted['chosen']
        require(first in DIMS, 'Stage2 requires one accepted first group')
        records.update(first_records)
    expected_paths = [f'artifacts/hm-auto-v2/audits/group{stage}-{anchor}/report.json' for anchor in selection.ANCHORS]
    require(len(audit_paths) == 2 and all(Path(actual).resolve() == (ROOT/expected).resolve()
            for actual,expected in zip(audit_paths,expected_paths)), 'Group audit path/order differs')
    result = compose(context,records,stage,*group_weeks(context,records,stage,first),first=first)
    require(all(selection.digest((ROOT/name).read_bytes()) == sha for name,sha in records.items()), 'Inputs changed during group decision')
    output = Path(output).resolve()
    allowed = (ROOT/'artifacts/hm-auto-v2').resolve()
    require(allowed.is_relative_to(ROOT.resolve()) and output != allowed and output.is_relative_to(allowed),
            'New output must be a child of artifacts/hm-auto-v2')
    output.mkdir(parents=True,exist_ok=False)
    with (output/'report.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=int,choices=(1,2),required=True)
    parser.add_argument('--audits',type=Path,nargs=2,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        result = group_decision(args.audits,args.output,stage=args.stage)
    except Exception as error:
        print(json.dumps(dict(status='failed',error_type=type(error).__name__,message=str(error)[:2048])))
        return 1
    print(json.dumps(dict(status=result['status'],selected_groups=result['selected_groups'],next_action=result['next_action'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
