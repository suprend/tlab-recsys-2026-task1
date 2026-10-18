"""Concrete H&M v2 customer-holdout authorization, never the v1 final gate.

The caller supplies the expected lock SHA. Metadata and file byte hashes are
checked before SQL/Pool; no parquet/model parser is imported here. Hash-bound
reservation evidence certifies the old query sets. Collector and auditor must
also check actual customer membership independently before accessing test Y.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from scripts import hm_auto_regularization as regularization
from scripts import hm_auto_select as selection
from scripts import hm_experiment as legacy

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = 'configs/datasets/hm-auto-holdout-lock.json'
RESERVATION_PATH = 'artifacts/hm-auto-v2/reservation/manifest.json'
RESERVATION_SHA = '424eace8c378caf7d10d98af364ba1a7f99f7d17177e7b41c19ccb9bc0f53e89'
ANCHORS = ['2020-08-12', '2020-08-19', '2020-08-26', '2020-09-02', '2020-09-09']
CODE_NAMES = tuple(sorted(('hm_baseline.py', 'hm_contrasts.py', 'hm_download.py', 'hm_eda.py',
    'hm_experiment.py', 'hm_feature_engine.py', 'hm_final_lock.py', 'hm_job.py', 'hm_result_audit.py',
    'hm_retrieval.py', 'hm_select_features.py', *regularization.SOURCES,
    'hm_auto_holdout_lock.py', 'hm_auto_holdout.py', 'hm_auto_holdout_audit.py')))
COHORT = dict(kind='reserved_customer_holdout', anchor='2020-09-16', horizon_days=7, users=20000,
              history_days=90, salt='hm-v2-customer-test-20261018', policy='C0-Q120')
TRAINING = dict(train_users=20000, negative_sample=20, sampling_seed=2026, model_seeds=[2026, 2027])
BASE = 'artifacts/hm-auto-v2/customer-test'
OUTPUTS = dict(collection=BASE+'/collection', fits=[BASE+'/fits/'+name for name in ('M2026', 'M2027', 'E2026', 'E2027')],
               audit=BASE+'/audit', contrasts=BASE+'/contrasts')
INFERENCE = dict(contrasts=[
    dict(name='E_minus_M_seed_mean', positive=['arm-02', 'arm-03'], negative=['arm-00', 'arm-01']),
    dict(name='E_minus_M_seed2026', positive=['arm-02'], negative=['arm-00']),
    dict(name='E_minus_M_seed2027', positive=['arm-03'], negative=['arm-01'])],
    bootstrap=dict(draws=2000, seed=2026, interval='percentile95'), gain_if_lower95_gt=0,
    interpretation='Customer holdout on the known calendar week; not an independent temporal holdout')
MAX_WALL_SECONDS = 1800
EXTERNAL_JOB_SECONDS = 1860
require = selection.require


@dataclass(frozen=True)
class FrozenPlan:
    path: Path
    data: dict
    sha256: str


def runtime_identity():
    return legacy.runtime_identity()


def same(actual, expected):
    return selection.canonical(actual) == selection.canonical(expected)


def path(value):
    regularization.portable(value)
    result = (ROOT/value).resolve()
    require(result.is_relative_to(ROOT.resolve()), 'Lock path escapes checkout')
    return result


def read(ref, records):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and
            isinstance(ref['sha256'], str) and selection.HEX.fullmatch(ref['sha256']), 'Path/SHA256 reference required')
    path(ref['path'])
    return selection.read_metadata(ref['path'], records, ref['sha256'])


def byte_pin(ref, records):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256', 'bytes'} and
            type(ref['bytes']) is int and ref['bytes'] > 0 and isinstance(ref['sha256'], str) and
            selection.HEX.fullmatch(ref['sha256']), 'Path/SHA256/positive-byte-size pin required')
    target = path(ref['path'])
    require(target.is_file() and target.stat().st_size == ref['bytes'] and
            legacy.sha256_file(target) == ref['sha256'], 'Pinned file byte identity changed')
    records[ref['path']] = ref['sha256']


def inventory(folder, files, names):
    require(isinstance(files, dict) and set(files) == set(names), 'Exact produced file inventory required')
    for name, sha in files.items():
        target = (folder/name).resolve()
        require(target.is_relative_to(folder.resolve()) and isinstance(sha, str) and selection.HEX.fullmatch(sha)
                and target.is_file() and legacy.sha256_file(target) == sha, 'Produced artifact byte identity changed')


def l2_evidence(value, protocol, records):
    plan = read(value['l2_plan'], records)
    # Reuse the frozen metadata replay of group1/group2. It reads historical
    # contracts as evidence; it does not invoke the old final authorization.
    validated = regularization.validate_plan(path(value['l2_plan']['path']), value['l2_plan']['sha256'])
    require(same(validated['plan'], plan), 'Replayed L2 plan differs')
    records.update(validated['records'])
    context = validated['context']
    decision = read(value['l2_decision'], records)
    require(plan.get('format') == 'hm-auto-l2-plan-v2' and plan['protocol'] == value['protocol'] and
            decision.get('format') == 'hm-auto-l2-decision-v2' and decision.get('status') == 'completed' and
            decision.get('phase') == 'symmetric_regularization' and decision.get('candidate_eligible') is True and
            decision.get('customer_holdout_authorized') is False and decision['plan'] == value['l2_plan'] and
            decision['selection'] == plan['selection'], 'Accepted original-v2 eligible L2 decision required')
    group = read(plan['selection'], records)
    require(plan['selection']['path'] == regularization.GROUP_DECISION and group.get('status') == 'completed' and
            group.get('stage') == 2 and type(group.get('width')) is int and group['width'] > 0 and
            group.get('run_symmetric_L2') is True and group['selected_programs'] and
            group['selected_names'] == value['features']['M']['numeric']+value['features']['M']['categorical']+group['selected_programs'] and
            value['features']['E'] == dict(numeric=value['features']['M']['numeric']+group['selected_programs'],
                categorical=value['features']['M']['categorical']) and plan['features'] == value['features'],
            'Nonempty accepted group2 expansion/model order required')
    require(group == validated['selection'] and value['features']['M'] == context['manual'] and
            len(context['manual']['numeric']) == 18 and len(context['manual']['categorical']) == 5,
            'Frozen M23 and replayed accepted expansion required')
    require(set(plan['sources']) == set(regularization.SOURCES) and all(value['implementation']['code'][name] == sha
        for name, sha in plan['sources'].items()) and decision['implementation_sha256'] == plan['sources']['hm_auto_regularization.py'],
        'L2 implementation differs from accepted source')
    for relative, sha in decision['provenance'].items():
        require(path(relative).suffix in ('.json', '.py') and isinstance(sha, str) and selection.HEX.fullmatch(sha),
                'Bounded metadata/source L2 provenance required')
        if relative.endswith('.json'):
            read(dict(path=relative, sha256=sha), records)
        else:
            require(legacy.sha256_file(path(relative)) == sha, 'L2 source provenance changed')
            records[relative] = sha
    require(decision['provenance'].get(value['l2_plan']['path']) == value['l2_plan']['sha256'], 'L2 plan provenance missing')
    points = {arm: {l2: [] for l2 in (10, 50)} for arm in ('M', 'E')}
    require(len(decision['cells']) == 8 and len(plan['folds']) == 2, 'Eight audited L2 cells required')
    common, inputs = None, {}
    contract_digest = context['lock']['feature_digest']
    for fold, anchor in enumerate(selection.ANCHORS):
        item = plan['folds'][fold]
        require(item['anchor'] == anchor, 'L2 development fold differs')
        audit_ref = dict(path=item['audit'], sha256=decision['provenance'][item['audit']])
        audit = read(audit_ref, records)
        require(audit.get('format') == 'hm-independent-result-audit-v1' and audit.get('status') == 'PASS' and
                audit.get('checker_sha256') == protocol['v1_frozen']['source']['hm_result_audit.py'] and
                audit.get('source_rebuild') == 'PASS: raw history-only SHA256 Q and full distinct weekly Y' and
                'final_lock_sha256' not in audit and audit['collection']['anchor'] == anchor and
                audit['collection']['policy'] == 'C0-Q120' and audit['collection']['database_identity'] == context['lock']['database'] and
                len(audit['fits']) == 4, 'Frozen PASS L2 audit required')
        for index, (arm, l2) in enumerate(regularization.CELLS):
            cell, row = decision['cells'][fold*4+index], audit['fits'][index]
            relative = item[arm+'10']['path'] if l2 == 10 else item[arm+'50']+'/report.json'
            require(type(row['arm']) is int and row['arm'] == index and
                    Path(row['fit_directory']).resolve() == path(relative).parent and
                    cell['anchor'] == anchor and cell['arm'] == arm and type(cell['l2_leaf_reg']) is int and cell['l2_leaf_reg'] == l2 and cell['path'] == relative and
                    cell['report_sha256'] == row['report_sha256'] == decision['provenance'][relative] and
                    cell['fit_identity'] == row['fit_identity'] and cell['audited_map'] == row['metrics']['map_at_12_conditional'],
                    'L2 audited cell/provenance differs')
            producer = read(dict(path=relative, sha256=cell['report_sha256']), records)
            expected_code = ({name: protocol['v1_frozen']['source'][name] for name in ('hm_experiment.py', 'hm_baseline.py')} if l2 == 10 else
                {name: plan['sources'][name] if name == 'hm_auto_fit.py' else protocol['v1_frozen']['source'][name]
                 for name in regularization.NEW_FIT_SOURCES})
            require(producer.get('format') == 'hm-experiment-fit-v1' and producer.get('status') == 'completed' and
                    all(type(producer.get(key)) is int and producer[key] == expected for key, expected in
                        dict(fit_count=1, actual_trees=500, training_user_limit=20000, negative_sample=20, sampling_seed=2026).items()) and
                    'final_lock_sha256' not in producer and producer['code'] == expected_code and set(row['code']) == set(expected_code) and
                    all(row['code'][name].get('recorded_sha256') == sha and row['code'][name].get('current_source_matches') is True
                        for name, sha in expected_code.items()) and
                    producer['fit_identity'] == cell['fit_identity'] == selection.fit_identity(producer) and
                    producer['features'] == dict(value['features'][arm], contract_digest=contract_digest),
                    'L2 fit identity/metrics/features differ')
            regularization.groups.checked_metrics(row['metrics'], producer['validation_metrics'])
            params = dict(producer['hyperparameters']); seed = params.pop('random_seed')
            require(type(seed) is int and seed == 2026 and same(params, dict(context['lock']['hyperparameters'], l2_leaf_reg=l2)) and
                    same(producer['runtime'], value['implementation']['runtime']),
                    'L2 model seed/recipe/runtime differs')
            base = dict(params, l2_leaf_reg=10)
            common = base if common is None else common
            require(same(base, common), 'L2 cells changed another model parameter')
            points[arm][l2].append(cell['audited_map'])
            require([identity['anchor'] for identity in producer['inputs']] == protocol['development']['train_anchors'][fold]+[anchor] and
                    producer['inputs'][-1] == {key: audit['collection'][key] for key in
                        ('anchor', 'manifest_sha256', 'qcy_identity', 'candidate_identity')}, 'L2 supervised chronology/collection differs')
            for identity in producer['inputs']:
                require(set(identity) == {'anchor', 'manifest_sha256', 'qcy_identity', 'candidate_identity'} and
                        all(isinstance(identity[key], str) and selection.HEX.fullmatch(identity[key]) for key in
                            ('manifest_sha256', 'qcy_identity', 'candidate_identity')), 'L2 input identity shape differs')
                previous = inputs.setdefault(identity['anchor'], identity)
                require(previous == identity, 'L2 shared input identities differ')
    choice = regularization.choose_l2(points)
    require(choice['candidate_eligible'] and all(same(decision[key], choice[key]) for key in choice), 'L2 eligibility/tuned choice differs')
    for arm in ('M', 'E'):
        require(same(value['hyperparameters'][arm], dict(common, l2_leaf_reg=choice['chosen_l2'][arm])), 'Holdout recipe differs from equally tuned choice')
    return inputs, contract_digest


def load_lock(lock_path, expected_sha256):
    require(ROOT.resolve() == selection.ROOT.resolve(), 'Lock/metadata checkout roots differ')
    require(Path(lock_path).resolve() == path(LOCK_PATH) and isinstance(expected_sha256, str) and
            selection.HEX.fullmatch(expected_sha256), 'Explicit concrete lock path and SHA256 required')
    records = {}
    value = read(dict(path=LOCK_PATH, sha256=expected_sha256), records)
    require(set(value) == set('format protocol l2_plan l2_decision reservation train_collections database features hyperparameters training cohort implementation outputs inference'.split()) and
            value['format'] == 'hm-auto-holdout-lock-v2', 'Unexpected customer-holdout lock schema')
    require(value['protocol'] == dict(path=selection.PROTOCOL, sha256=selection.PROTOCOL_SHA), 'Original84f protocol required')
    protocol = read(value['protocol'], records)
    require(same(value['cohort'], COHORT) and same(value['training'], TRAINING) and same(value['outputs'], OUTPUTS) and
            same(value['inference'], INFERENCE), 'Frozen cohort/training/outputs/inference differs')
    require(set(value['implementation']) == {'code', 'runtime'} and set(value['implementation']['code']) == set(CODE_NAMES),
            'Exact19 full-pipeline source pins required')
    for name, sha in value['implementation']['code'].items():
        require(isinstance(sha, str) and selection.HEX.fullmatch(sha) and legacy.sha256_file(path('scripts/'+name)) == sha,
                'Frozen pipeline source changed')
        records['scripts/'+name] = sha
    require(all(value['implementation']['code'][name] == sha for name, sha in protocol['v1_frozen']['source'].items()) and
            same(runtime_identity(), value['implementation']['runtime']), 'Frozen v1 source/runtime changed')
    require(set(value['features']) == set(value['hyperparameters']) == {'M', 'E'}, 'Exactly M/E required')
    identities, expected_digest = l2_evidence(value, protocol, records)
    require(set(value['database']) == {'path', 'sha256', 'bytes'} and type(value['database']['bytes']) is int and
            value['database']['bytes'] > 0 and selection.HEX.fullmatch(value['database']['sha256']), 'Database path/SHA/bytes required')
    path(value['database']['path'])  # Identity only here; authorize_collect hashes DB after metadata authorization.
    reservation = value['reservation']
    require(set(reservation) == {'manifest', 'files', 'reserved_ordered_ids_sha256', 'excluded_ordered_ids_sha256'} and
            reservation['manifest'] == dict(path=RESERVATION_PATH, sha256=RESERVATION_SHA), 'Exact accepted reservation required')
    reserved = read(reservation['manifest'], records)
    counts = reserved['counts_history_only']
    require(reserved.get('format') == 'hm-auto-v2-customer-reservation-v1' and reserved.get('status') == 'completed' and
            reserved['no_test_targets_or_features'] is True and reserved['cutoff'] == COHORT['anchor'] and reserved['history_days'] == 90 and
            reserved['config']['sha256'] == selection.PROTOCOL_SHA and reserved['source']['sha256'] == value['implementation']['code']['hm_auto_reserve.py'] and
            reserved['database'] == dict(sha256=value['database']['sha256'], bytes=value['database']['bytes'], opened_read_only=True) and
            type(counts['reserved_users']) is int and counts['reserved_users'] == 20000 and type(counts['overlap_users']) is int and counts['overlap_users'] == 0,
            'Accepted history-only reservation differs')
    require(set(reservation['files']) == {'reserved-users.parquet', 'excluded-users.parquet'}, 'Both reservation ID files required')
    for name, ref in reservation['files'].items():
        require(ref == dict(path='artifacts/hm-auto-v2/reservation/'+name, **reserved['files'][name]), 'Reservation file pin differs')
        byte_pin(ref, records)
    for field in ('reserved_ordered_ids_sha256', 'excluded_ordered_ids_sha256'):
        require(reservation[field] == counts[field] and selection.HEX.fullmatch(reservation[field]), 'Reservation ordered-ID digest differs')
    require(isinstance(value['train_collections'], list) and len(value['train_collections']) == 5, 'Five exact supervised training collections required')
    full_contract = None
    for item, anchor in zip(value['train_collections'], ANCHORS):
        require(set(item) == {'anchor', 'manifest', 'users'} and item['anchor'] == anchor and
                item['manifest']['path'] == f'artifacts/hm-campaign/collections/{anchor}-c0q120/manifest.json', 'Frozen training path/order differs')
        manifest = read(item['manifest'], records)
        require(identities[anchor]['manifest_sha256'] == item['manifest']['sha256'] and
                manifest.get('format') == 'hm-experiment-collection-v1' and manifest.get('status') == 'completed' and
                same({key: manifest.get(key) for key in ('anchor', 'horizon_days', 'cohort_seed', 'policy', 'requested_users')},
                    dict(anchor=anchor, horizon_days=7, cohort_seed=2026, policy='C0-Q120', requested_users=20000)) and
                manifest['database'] == dict(sha256=value['database']['sha256'], bytes=value['database']['bytes']) and
                manifest['code']['hm_feature_engine.py'] == value['implementation']['code']['hm_feature_engine.py'], 'Frozen training identity/schema/source differs')
        for key in ('qcy_identity', 'candidate_identity'):
            require(manifest[key] == identities[anchor][key], 'Training Q/C/Y identity differs')
        contract = manifest['features']
        full_contract = contract if full_contract is None else full_contract
        require(contract == full_contract and contract['digest'] == expected_digest, 'Training feature contracts differ')
        specs = {entry['name']: entry['kind'] for entry in contract['registry']}
        require(len(specs) == len(contract['registry']) and all(set(vector) == {'numeric', 'categorical'} and
            all(specs.get(name) == kind for kind, names in vector.items() for name in names) and
            len(set(vector['numeric']+vector['categorical'])) == len(vector['numeric']+vector['categorical'])
            for vector in value['features'].values()), 'Locked feature schema kinds/names differ')
        old = [entry for entry in counts['actual_old_cohorts'] if entry['anchor'] == anchor]
        require(len(old) == 1 and old[0]['users'] == 20000 and old[0]['covered_by_reconstruction'] is True and
                Path(old[0]['path']).resolve() == path(item['users']['path']) and
                item['users'] == dict(path=f'artifacts/hm-campaign/collections/{anchor}-c0q120/users.parquet',
                    sha256=old[0]['sha256'], bytes=old[0]['bytes']) and manifest['files']['users.parquet'] == item['users']['sha256'],
                'Supervised users are not bound to the accepted exclusion certificate')
        byte_pin(item['users'], records)
    require(all(selection.digest((ROOT/name).read_bytes()) == sha for name, sha in records.items()), 'Lock evidence changed during validation')
    return FrozenPlan(path(LOCK_PATH), deepcopy(value), expected_sha256)


def guard(plan):
    require(isinstance(plan, FrozenPlan), 'Validated FrozenPlan required')
    fresh = load_lock(plan.path, plan.sha256)
    require(same(plan.data, fresh.data), 'FrozenPlan data mutated')
    return fresh.data


def authorize_collect(plan, database, output):
    value = guard(plan)
    require(Path(database).resolve() == path(value['database']['path']) and
            Path(output).resolve() == path(value['outputs']['collection']) and
            all(not path(relative).exists() for relative in [value['outputs']['collection'],
                *value['outputs']['fits'], value['outputs']['audit'], value['outputs']['contrasts']]), 'Collection request/output differs')
    byte_pin(value['database'], {})


def collection_manifest(value, plan_sha, collection):
    folder = Path(collection).resolve()
    require(folder == path(value['outputs']['collection']), 'Customer collection path differs')
    manifest_path = folder/'manifest.json'
    manifest = selection.read_metadata(manifest_path.relative_to(ROOT).as_posix(), {})
    require(manifest.get('format') == 'hm-auto-holdout-collection-v2' and manifest.get('status') == 'completed' and
            manifest.get('holdout_lock_sha256') == plan_sha and 'cohort_seed' not in manifest and
            same(manifest.get('cohort'), value['cohort']) and same({key: manifest.get(key) for key in
                ('anchor', 'horizon_days', 'policy', 'requested_users')}, dict(anchor='2020-09-16', horizon_days=7, policy='C0-Q120', requested_users=20000)) and
            manifest.get('database') == {key: value['database'][key] for key in ('sha256', 'bytes')} and
            manifest.get('reservation_manifest_sha256') == value['reservation']['manifest']['sha256'] and
            all(manifest.get(field) == value['reservation'][field] for field in ('reserved_ordered_ids_sha256', 'excluded_ordered_ids_sha256')) and
            same(manifest.get('id_checks'), dict(reserved_users=20000, excluded_overlap_users=0, training_overlap_users=0)) and
            manifest.get('code') == value['implementation']['code'] and same(manifest.get('runtime'), value['implementation']['runtime']),
            'Customer collection lock/cohort/source/reservation proof differs')
    first = read(value['train_collections'][0]['manifest'], {})
    require(manifest['features'] == first['features'], 'Customer feature contract differs from training')
    inventory(folder, manifest['files'], ('frame.parquet', 'users.parquet', 'targets.parquet'))
    require(manifest['qcy_identity'] == selection.canonical({key: manifest['files'][key] for key in ('users.parquet', 'targets.parquet')}) and
            isinstance(manifest['candidate_identity'], str) and selection.HEX.fullmatch(manifest['candidate_identity']), 'Customer Q/C/Y identity differs')
    identity = dict(anchor=manifest['anchor'], manifest_sha256=legacy.sha256_file(manifest_path),
                    qcy_identity=manifest['qcy_identity'], candidate_identity=manifest['candidate_identity'])
    return manifest, identity


def train_identities(value, verify_files=False):
    result = []
    for item in value['train_collections']:
        manifest = read(item['manifest'], {})
        if verify_files:
            inventory(path(item['manifest']['path']).parent, manifest['files'], ('frame.parquet', 'users.parquet', 'targets.parquet'))
        result.append(dict(anchor=item['anchor'], manifest_sha256=item['manifest']['sha256'],
                           qcy_identity=manifest['qcy_identity'], candidate_identity=manifest['candidate_identity']))
    return result


def authorize_fit(plan, arm, seed, train_paths, collection, output):
    value = guard(plan)
    require(arm in ('M', 'E') and type(seed) is int and seed in (2026, 2027), 'Exact holdout arm/model seed required')
    slot = (0 if arm == 'M' else 2)+(seed-2026)
    require([Path(p).resolve() for p in train_paths] == [path(item['manifest']['path']).parent for item in value['train_collections']] and
            Path(output).resolve() == path(value['outputs']['fits'][slot]) and not Path(output).exists(), 'Holdout fit training paths/output differs')
    collection_manifest(value, plan.sha256, collection)
    train_identities(value, verify_files=True)
    return dict(features=deepcopy(value['features'][arm]), hyperparameters=dict(value['hyperparameters'][arm], random_seed=seed), fit_index=slot)


def fit_identity(report):
    payload = {key: report[key] for key in ('inputs', 'features', 'hyperparameters', 'code', 'runtime',
        'holdout_lock_sha256', 'holdout_arm', 'reservation_manifest_sha256', 'cohort')}
    payload.update(train_users=report['training_user_limit'], negative_sample=report['negative_sample'], sampling_seed=report['sampling_seed'])
    return selection.canonical(payload)


def authorize_audit(plan, collection, fits, output):
    value = guard(plan)
    require(len(fits) == 4 and [Path(p).resolve() for p in fits] == [path(p) for p in value['outputs']['fits']] and
            Path(output).resolve() == path(value['outputs']['audit']) and not Path(output).exists(), 'Exact ordered four-fit audit request required')
    manifest, validation_input = collection_manifest(value, plan.sha256, collection)
    expected_inputs = train_identities(value, verify_files=True)+[validation_input]
    for index, folder in enumerate(fits):
        report = selection.read_metadata((Path(folder).resolve()/'report.json').relative_to(ROOT).as_posix(), {})
        arm, seed = ('M' if index < 2 else 'E'), (2026, 2027)[index % 2]
        require(report.get('format') == 'hm-auto-holdout-fit-v2' and report.get('status') == 'completed' and
                type(report.get('fit_count')) is int and report['fit_count'] == 1 and type(report.get('actual_trees')) is int and report['actual_trees'] == 500 and
                report.get('holdout_lock_sha256') == plan.sha256 and report.get('holdout_arm') == arm and
                report.get('reservation_manifest_sha256') == value['reservation']['manifest']['sha256'] and same(report.get('cohort'), value['cohort']) and
                same(report['hyperparameters'], dict(value['hyperparameters'][arm], random_seed=seed)) and
                all(report.get('resolved_model_parameters', {}).get(key) == report['hyperparameters'][key]
                    for key in ('task_type', 'iterations', 'depth', 'l2_leaf_reg', 'random_seed')) and
                report['features'] == dict(value['features'][arm], contract_digest=manifest['features']['digest']) and report['inputs'] == expected_inputs and
                all(type(report[key]) is int and report[key] == expected for key, expected in
                    dict(training_user_limit=20000, negative_sample=20, sampling_seed=2026).items()) and
                report['code'] == value['implementation']['code'] and same(report['runtime'], value['implementation']['runtime']) and
                report['fit_identity'] == fit_identity(report), 'Completed locked holdout fit identity/recipe differs')
        inventory(Path(folder).resolve(), report['files'], ('model.cbm', 'query-metrics.parquet', 'predictions-top12.parquet'))
