"""Metadata-only original-v2 symmetric L2 decision for an accepted expansion.

Requires an immutable prospective plan and a fully replayed nonempty group2
decision. This validator cannot admit a width0 probe or authorize customer-test
access. It never reads DB, parquet, models, IDs or customer-holdout targets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import hm_auto_groups as groups
from scripts import hm_auto_select as selection

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('hm_auto_fit.py', 'hm_auto_select.py', 'hm_auto_groups.py',
           'hm_auto_reserve.py', 'hm_auto_regularization.py')
NEW_FIT_SOURCES = ('hm_auto_fit.py', 'hm_experiment.py', 'hm_baseline.py',
                   'hm_job.py', 'hm_feature_engine.py')
GROUP_DECISION = 'artifacts/hm-auto-v2/decisions/group2/report.json'
OUTPUT = 'artifacts/hm-auto-v2/decisions/l2'
CELLS = (('M', 10), ('E', 10), ('M', 50), ('E', 50))
require = selection.require


def choose_l2(points):
    """Tune each arm by unweighted mean of two audited MAPs; exact ties ->10."""
    require(isinstance(points, dict) and set(points) == {'M', 'E'}, 'Exactly M and E required')
    chosen, means, tuned = {}, {}, {}
    for arm in ('M', 'E'):
        require(isinstance(points[arm], dict) and set(points[arm]) == {10, 50}, 'Exactly L2 10/50 required')
        for values in points[arm].values():
            require(isinstance(values, (list, tuple)) and len(values) == 2 and
                    all(selection.finite_number(v) and 0 <= v <= 1 for v in values),
                    'Two finite weekly MAPs in [0,1] required')
        means[arm] = {str(l2): sum(points[arm][l2])/2 for l2 in (10, 50)}
        chosen[arm] = 50 if means[arm]['50'] > means[arm]['10'] else 10
        tuned[arm] = list(points[arm][chosen[arm]])
    deltas = {str(l2): [e-m for e, m in zip(points['E'][l2], points['M'][l2])] for l2 in (10, 50)}
    tuned_deltas = [e-m for e, m in zip(tuned['E'], tuned['M'])]
    return dict(chosen_l2=chosen, mean_weekly_map=means, tuned_weekly_maps=tuned,
        tuned_weekly_deltas=tuned_deltas, candidate_eligible=all(d > 0 for d in tuned_deltas),
        diagnostics=dict(delta_l2_10=deltas['10'], delta_l2_50=deltas['50'],
                         interaction_D=[b-a for a, b in zip(deltas['10'], deltas['50'])]),
        customer_holdout_authorized=False)


def portable(value):
    require(isinstance(value, str) and value and '\\' not in value and
            not Path(value).is_absolute() and '..' not in Path(value).parts,
            'Portable project-relative path required')
    return value


def read_ref(ref, records):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and
            isinstance(ref['sha256'], str) and selection.HEX.fullmatch(ref['sha256']),
            'Exact path/SHA256 reference required')
    return groups.read(portable(ref['path']), records, ref['sha256'])


def accepted_expansion(ref, records):
    """Replay precisely the frozen group2 decision, with its original provenance."""
    require(ref['path'] == GROUP_DECISION, 'Accepted group2 decision path required')
    replay = {}
    context = groups.context_and_prefix(replay)
    first_records = dict(replay)
    first = groups.read(groups.FIRST_DECISION, replay)
    previous = groups.group_weeks(context, first_records, 1)
    expected = groups.compose(context, first_records, 1, *previous)
    require(selection.canonical(first) == selection.canonical(expected), 'Accepted group1 decision differs or is stale')
    require(first['chosen'] in groups.DIMS, 'Nonempty group1 required; width0 probes are not admitted')
    replay.update(first_records)
    second = groups.group_weeks(context, replay, 2, first['chosen'])
    expected = groups.compose(context, replay, 2, *second, first=first['chosen'])
    decision = read_ref(ref, records)
    require(selection.canonical(decision) == selection.canonical(expected), 'Accepted group2 decision differs or is stale')
    require(decision['stage'] == 2 and type(decision['width']) is int and decision['width'] > 0 and
            decision['run_symmetric_L2'] is True and decision['next_action'] == 'symmetric_regularization' and
            decision['selected_groups'] and decision['selected_programs'], 'Original v2 requires a nonempty accepted expansion')
    for name, sha in replay.items():
        require(name not in records or records[name] == sha, 'Replayed selection provenance changed')
        records[name] = sha
    return context, decision


def validate_plan(path, expected_sha, *, before_fits=False):
    """Validate the prospective contract; before_fits also requires new outputs."""
    require(ROOT.resolve() == groups.ROOT.resolve() == selection.ROOT.resolve(), 'Metadata checkout roots differ')
    require(isinstance(expected_sha, str) and selection.HEX.fullmatch(expected_sha), 'Explicit full plan SHA256 required')
    records = {}
    plan_path = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    plan = groups.read(plan_path, records, expected_sha)
    require(set(plan) == {'format', 'protocol', 'selection', 'sources', 'features', 'names_files', 'folds', 'output'} and
            plan['format'] == 'hm-auto-l2-plan-v2', 'Unexpected original-v2 L2 plan schema')
    require(plan['protocol'] == dict(path=selection.PROTOCOL, sha256=selection.PROTOCOL_SHA), 'Original84f protocol required')
    read_ref(plan['protocol'], records)
    require(set(plan['sources']) == set(SOURCES), 'All five current v2 source pins required')
    for name, sha in plan['sources'].items():
        require(isinstance(sha, str) and selection.HEX.fullmatch(sha), 'Full current source SHA256 required')
        groups.source(name, records, sha)
    context, decision = accepted_expansion(plan['selection'], records)
    manual = context['manual']
    features = dict(M=manual, E=dict(numeric=manual['numeric']+decision['selected_programs'],
                                    categorical=manual['categorical']))
    require(plan['features'] == features and set(plan['names_files']) == {'M', 'E'}, 'Planned M/E model vectors differ')
    require(read_ref(plan['names_files']['M'], records) == manual['numeric']+manual['categorical'] and
            read_ref(plan['names_files']['E'], records) == decision['selected_names'] ==
            manual['numeric']+manual['categorical']+decision['selected_programs'], 'Planned logical names differ')
    require(isinstance(plan['folds'], list) and len(plan['folds']) == 2, 'Two ordered development folds required')
    future = []
    selected_groups = decision['selected_groups']
    for fold, (item, anchor) in enumerate(zip(plan['folds'], selection.ANCHORS)):
        require(set(item) == {'anchor', 'M10', 'E10', 'M50', 'E50', 'audit'} and item['anchor'] == anchor,
                'Exact development fold schema/order required')
        m_path = context['protocol']['development']['references'][fold]+'/report.json'
        e_dir = (f'artifacts/hm-auto-v2/group1/{selected_groups[0]}/{anchor}' if len(selected_groups) == 1 else
                 f'artifacts/hm-auto-v2/group2/{selected_groups[0]}__{selected_groups[1]}/{anchor}')
        for arm, relative in (('M', m_path), ('E', e_dir+'/report.json')):
            matches = [fit for fit in decision['fits'] if fit['anchor'] == anchor and fit['path'] == relative]
            require(len(matches) == 1 and item[arm+'10'] == dict(path=relative, sha256=matches[0]['report_sha256']),
                    'Exact accepted M/E10 fit reference required')
            read_ref(item[arm+'10'], records)
            expected = f'artifacts/hm-auto-v2/l2/{arm}50/{anchor}'
            require(item[arm+'50'] == expected, 'Predeclared L2=50 output differs')
            future.append(ROOT/expected)
        require(item['audit'] == f'artifacts/hm-auto-v2/audits/l2-{anchor}/report.json', 'Predeclared L2 audit path differs')
        future.append((ROOT/item['audit']).parent)
    require(plan['output'] == OUTPUT, 'Predeclared L2 decision output differs')
    future.append(ROOT/OUTPUT)
    allowed = (ROOT/'artifacts/hm-auto-v2').resolve()
    require(allowed.is_relative_to(ROOT.resolve()) and all(path.resolve() != allowed and
            path.resolve().is_relative_to(allowed) for path in future), 'L2 outputs must remain in checkout artifacts/hm-auto-v2')
    if before_fits:
        require(all(not path.exists() for path in future), 'Prospective L2 fit/audit/decision outputs must all be absent')
    require(all(selection.digest((ROOT/name).read_bytes()) == sha for name, sha in records.items()), 'Plan inputs changed during validation')
    return dict(plan=plan, plan_path=plan_path, plan_sha256=expected_sha, context=context,
                selection=decision, records=records, customer_holdout_authorized=False)


def regularization_decision(plan_path, plan_sha, audit_paths, output):
    validated = validate_plan(plan_path, plan_sha)
    plan, context, records = validated['plan'], validated['context'], validated['records']
    require(len(audit_paths) == 2 and all(Path(actual).resolve() == (ROOT/item['audit']).resolve()
        for actual, item in zip(audit_paths, plan['folds'])), 'L2 audit path/order differs')
    require(Path(output).resolve() == (ROOT/plan['output']).resolve(), 'L2 decision output differs from plan')
    frozen = context['protocol']['v1_frozen']['source']
    pins = {Path(ref['path']).parent.name[:10]: ref['sha256'] for ref in context['lock']['train_collections']}
    points = {arm: {l2: [] for l2 in (10, 50)} for arm in ('M', 'E')}
    cells, weeks, shared = [], [], {}
    for fold, item in enumerate(plan['folds']):
        anchor = item['anchor']
        audit = groups.read(item['audit'], records)
        require(audit.get('format') == 'hm-independent-result-audit-v1' and audit.get('status') == 'PASS' and
                audit.get('checker_sha256') == frozen['hm_result_audit.py'] and 'final_lock_sha256' not in audit and
                audit.get('source_rebuild') == 'PASS: raw history-only SHA256 Q and full distinct weekly Y',
                'PASS frozen source-rebuilt development audit required')
        collection = audit['collection']
        require(collection['anchor'] == anchor and collection['policy'] == 'C0-Q120' and
                collection['database_identity'] == context['lock']['database'] and
                collection['manifest_sha256'] == pins[anchor], 'L2 audit collection differs')
        collection_input = {key: collection[key] for key in ('anchor', 'manifest_sha256', 'qcy_identity', 'candidate_identity')}
        require(len(audit['fits']) == 4, 'Four ordered M10/E10/M50/E50 audit arms required')
        population = inputs = None
        for index, (row, (arm, l2)) in enumerate(zip(audit['fits'], CELLS)):
            relative = item[arm+'10']['path'] if l2 == 10 else item[arm+'50']+'/report.json'
            require(type(row['arm']) is int and row['arm'] == index and
                    Path(row['fit_directory']).resolve() == (ROOT/relative).parent.resolve(), 'L2 audit arm path/order differs')
            if l2 == 10:
                require(row['report_sha256'] == item[arm+'10']['sha256'], 'Reused L2=10 report SHA differs')
            producer = groups.read(relative, records, row['report_sha256'])
            require(producer.get('format') == 'hm-experiment-fit-v1' and producer.get('status') == 'completed' and
                    type(producer.get('fit_count')) is int and producer['fit_count'] == 1 and
                    type(producer.get('actual_trees')) is int and producer['actual_trees'] == 500 and
                    'final_lock_sha256' not in producer, 'Completed fixed500 development fit required')
            require(producer['features'] == dict(plan['features'][arm], contract_digest=context['lock']['feature_digest']),
                    'L2 fit model feature vector differs')
            parameters = dict(context['lock']['hyperparameters'], random_seed=2026, l2_leaf_reg=l2)
            require(selection.canonical(producer['hyperparameters']) == selection.canonical(parameters) and
                    selection.canonical(producer['runtime']) == selection.canonical(context['lock']['implementation']['runtime']) and
                    all(type(producer[key]) is int and producer[key] == value for key, value in
                        dict(training_user_limit=20000, negative_sample=20, sampling_seed=2026).items()), 'L2 fit recipe/runtime differs')
            expected_code = ({name: frozen[name] for name in ('hm_experiment.py', 'hm_baseline.py')} if l2 == 10 else
                {name: plan['sources'][name] if name == 'hm_auto_fit.py' else frozen[name] for name in NEW_FIT_SOURCES})
            require(producer['code'] == expected_code and set(row['code']) == set(expected_code) and
                    all(row['code'][name].get('recorded_sha256') == sha and
                        row['code'][name].get('current_source_matches') is True for name, sha in expected_code.items()),
                    'L2 fit producer code differs')
            require(producer['fit_identity'] == row['fit_identity'] == selection.fit_identity(producer), 'L2 fit identity mismatch')
            require([value['anchor'] for value in producer['inputs']] == context['protocol']['development']['train_anchors'][fold]+[anchor]
                    and producer['inputs'][-1] == collection_input, 'L2 development fold/input differs')
            for value in producer['inputs']:
                require(set(value) == {'anchor', 'manifest_sha256', 'qcy_identity', 'candidate_identity'} and
                        all(isinstance(value[key], str) and selection.HEX.fullmatch(value[key])
                            for key in ('manifest_sha256', 'qcy_identity', 'candidate_identity')) and
                        value['manifest_sha256'] == pins[value['anchor']], 'L2 frozen input identity differs')
                previous = shared.setdefault(value['anchor'], value)
                require(previous == value, 'Shared L2 cross-fold Q/C/Y differs')
            inputs = producer['inputs'] if inputs is None else inputs
            require(producer['inputs'] == inputs, 'Within-week L2 Q/C/Y inputs differ')
            metrics = row['metrics']
            groups.checked_metrics(metrics, producer['validation_metrics'])
            current = {key: metrics[key] for key in groups.POPULATION_KEYS}
            population = current if population is None else population
            groups.population_matches(current, population)
            point = metrics['map_at_12_conditional']
            points[arm][l2].append(point)
            cells.append(dict(anchor=anchor, arm=arm, l2_leaf_reg=l2, audited_map=point,
                path=relative, report_sha256=records[relative], fit_identity=producer['fit_identity']))
        weeks.append(dict(anchor=anchor, collection=collection_input, population=population,
                          audit=dict(path=item['audit'], sha256=records[item['audit']])))
    choice = choose_l2(points)
    report = dict(format='hm-auto-l2-decision-v2', status='completed', phase='symmetric_regularization',
        plan=dict(path=validated['plan_path'], sha256=plan_sha), selection=plan['selection'],
        **choice, cells=cells, weeks=weeks,
        next_action='requires_separate_customer_holdout_lock' if choice['candidate_eligible'] else 'retain_M_no_test',
        preserve_untouched_customer_holdout=True,
        interpretation='Each arm maximizes unweighted mean weekly audited MAP; ties choose10. Eligibility uses tuned E-M strictly positive on both weeks. Interaction D is descriptive, not a gate. Development CIs are descriptive after search.',
        implementation_sha256=plan['sources']['hm_auto_regularization.py'], provenance=dict(records))
    require(all(selection.digest((ROOT/name).read_bytes()) == sha for name, sha in records.items()), 'Inputs changed during L2 decision')
    destination = Path(output).resolve()
    allowed = (ROOT/'artifacts/hm-auto-v2').resolve()
    require(destination.is_relative_to(allowed) and destination != allowed, 'L2 output must stay inside artifacts/hm-auto-v2')
    destination.mkdir(parents=True, exist_ok=False)
    with (destination/'report.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('check-plan', 'decide'):
        command = sub.add_parser(name)
        command.add_argument('--plan', type=Path, required=True)
        command.add_argument('--plan-sha256', required=True)
        if name == 'decide':
            command.add_argument('--audits', type=Path, nargs=2, required=True)
            command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'check-plan':
            validated = validate_plan(args.plan, args.plan_sha256, before_fits=True)
            result = dict(status='validated', plan_sha256=validated['plan_sha256'], customer_holdout_authorized=False)
        else:
            decision = regularization_decision(args.plan, args.plan_sha256, args.audits, args.output)
            result = {key: decision[key] for key in ('status', 'chosen_l2', 'candidate_eligible', 'customer_holdout_authorized')}
    except Exception as error:
        print(json.dumps(dict(status='failed', error_type=type(error).__name__, message=str(error)[:2048])))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
