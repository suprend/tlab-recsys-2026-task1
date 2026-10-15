"""Synthetic six-real-process harness. Importing performs no launch/native work.

Only run after review of exact frozen bytes. The historical admission seam and
self-issued test gates are explicitly scoped; production entries stay unchanged.
"""
import time
ENTRY_MONOTONIC = time.monotonic()
import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import sys
import types

PROJECT = Path('/Users/mdpospelov/tlab-recsys-2026')
BUILDER = Path('/tmp/tlab-build-heldout-native-fixture.py')
PROCESSES = Path('/tmp/tlab-heldout-harness-processes.py')
FREEZE = Path('/tmp/tlab-heldout-six-role-harness-freeze.json')
HARNESS_FILES = (str(BUILDER), '/tmp/tlab-run-heldout-six-role-toy.py', '/tmp/tlab-test-heldout-six-role-harness.py',
    str(PROCESSES), '/tmp/tlab-test-heldout-harness-processes.py')
PUBLIC_CONFIGS = ('configs/features/manual-18.json', 'configs/features/automation-pool.json', 'configs/heldout/reporting-only-v1.json')
DISCLOSURES = dict(scope='synthetic_six_role_integration_only', historical_authentication_exercised=False,
    historical_consumer_stub=True, synthetic_gate_issuer=True, actual_training_rows=8,
    protocol_population_literal=26000, setup_fit_attempt_count=1, study_fit_attempt_count=0,
    W_equals_B=True, chosen3_native_integration_proven=False, real_recommendation_quality_claim=False,
    fresh_source_bootstrap_proven=False, production_resource_sufficiency_proven=False)


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while part := stream.read(2**20):
            value.update(part)
    return value.hexdigest()


def canonical(body):
    return json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False)


def exclusive(path, body):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(canonical(body)+'\n'); stream.flush(); os.fsync(stream.fileno())


def read(path, *, expected_sha256=None):
    with Path(path).open('rb') as stream:
        raw = stream.read(8*2**20+1)
    need(len(raw) <= 8*2**20, 'Bounded harness JSON required')
    if expected_sha256 is not None:
        need(hashlib.sha256(raw).hexdigest() == expected_sha256, 'Original reviewed harness-freeze bytes changed')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'Duplicate harness JSON key'); result[key] = value
        return result
    def reject(_):
        raise ValueError('Nonfinite harness JSON')
    result = json.loads(raw, object_pairs_hook=unique, parse_constant=reject)
    need('Infinity' not in canonical(result) and 'NaN' not in canonical(result), 'Finite harness JSON required')
    return result


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def load_freeze(path, issued_sha256):
    need(type(issued_sha256) is str and re.fullmatch('[a-f0-9]{64}', issued_sha256) is not None, 'Original issued harness-freeze SHA required')
    return verify_harness(read(path, expected_sha256=issued_sha256))


def public_files(project=PROJECT):
    """Parse the reviewed CODE literal without importing project/native modules."""
    tree = ast.parse((project/'scripts/run_heldout_reporting.py').read_text())
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'OWNER':
                    constants['OWNER'] = ast.literal_eval(node.value)
    def value(node):
        if isinstance(node, ast.Name):
            return constants[node.id]
        if isinstance(node, (ast.Tuple, ast.List)):
            return tuple(value(child) for child in node.elts)
        return ast.literal_eval(node)
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CODE' for t in node.targets))
    names = tuple(value(assignment.value)) + PUBLIC_CONFIGS
    need(len(names) == len(set(names)), 'Duplicate frozen public path')
    need(all(not name.startswith(('data/', 'artifacts/', '.git/', '.venv/')) and '..' not in Path(name).parts for name in names), 'Only public dependency closure may be copied')
    return names


def verify_harness(freeze):
    need(type(freeze['version']) is int and freeze['version'] == 1 and freeze['scope'] == 'synthetic_six_role_harness_code_only_no_execution_authority', 'Harness freeze scope/version differs')
    need(set(freeze['harness_files']) == set(HARNESS_FILES), 'Exact five-file reviewed harness closure required')
    for name, digest in freeze['harness_files'].items():
        need(Path(name).resolve().is_relative_to(Path('/tmp').resolve()) and sha(name) == digest, 'Frozen harness bytes differ')
    need(set(freeze['production_files']) == set(public_files()), 'Frozen executable/public closure differs')
    need(freeze['disclosures'] == DISCLOSURES, 'Mandatory synthetic disclosure differs')
    return freeze


def safe_root(root):
    root = Path(root).resolve()
    need(root.is_relative_to(Path('/tmp').resolve()) and ' ' in root.name and root != Path('/tmp').resolve(), 'Dedicated TMP root with spaces required')
    return root


def create_copy(root, freeze):
    root = safe_root(root); need(not root.exists(), 'Exclusive fresh isolated root required')
    root.mkdir()
    copies = {}
    for name, digest in freeze['production_files'].items():
        source = PROJECT/name
        need(source.is_file() and source.resolve().is_relative_to(PROJECT.resolve()) and sha(source) == digest, 'Frozen source production bytes changed')
        destination = root/name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        need(sha(destination) == digest, 'Copy differs from original public bytes')
        copies[name] = dict(source_sha256=digest, copied_sha256=sha(destination))
    for namespace in ['scripts', 'tests', 'tests/oracles']:
        need(not (root/namespace/'__init__.py').exists(), 'No copied namespace initializer allowed')
    python = Path(freeze['python']).resolve()
    need(python.is_file(), 'Reviewed Python executable missing')
    runtime = freeze['runtime']
    need(sha(runtime['pyvenv_config']) == runtime['pyvenv_config_sha256'], 'Reviewed venv configuration changed')
    venv = Path(runtime['venv']).resolve()
    need(venv == (PROJECT/'.venv').resolve() and Path(runtime['pyvenv_config']).resolve() == venv/'pyvenv.cfg', 'Trusted existing locked venv required')
    need((venv/'bin/python').resolve() == python and Path(freeze['python']) == PROJECT/'.venv/bin/python', 'Normal existing venv interpreter required')
    (root/'.venv').symlink_to(venv, target_is_directory=True)
    exclusive(root/'harness-copy.json', dict(version=1, scope='synthetic_public_copy_only', files=copies, python=str(python),
        runtime=runtime, package_runtime_shared=True, environment_override=False, copied_private_data=False))
    need(not (root/'data').exists() and not (root/'artifacts').exists(), 'Original private directories must not be copied')
    return root


def toy_events():
    """Literal typed values; BIGINT never travels through float/pandas."""
    big = 2**60+1
    return [('2019-10-24 23:00:00','view',None,big,None),
        ('2019-10-25 00:00:00','purchase',big,big,9),
        ('2019-10-25 00:00:00','purchase',big,big,9),
        ('2019-10-25 02:00:00','view',10,2,100),
        ('2019-10-26 12:00:00','view',10,2,100),
        ('2019-10-26 12:00:00','view',10,3,None),
        ('2019-10-26 12:00:00','purchase',10,2,100),
        ('2019-10-27 12:00:00','cart',10,2,200),
        ('2019-10-28 10:00:00','view',20,4,200),
        ('2019-10-28 11:00:00','purchase',big,4,9),
        ('2019-10-28 11:00:00','view',None,5,None)]


def fixture_request(root, owner):
    """Create only synthetic source/authority metadata; original history unopened."""
    import duckdb
    path = root/owner.SOURCE_INPUTS['source']; path.parent.mkdir(parents=True)
    need(not path.exists(), 'Exclusive toy source database required')
    con = duckdb.connect(str(path))
    try:
        con.execute('SET threads=2')
        con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
        con.executemany('INSERT INTO events VALUES(CAST(? AS TIMESTAMP),CAST(? AS VARCHAR),CAST(? AS BIGINT),CAST(? AS BIGINT),CAST(? AS BIGINT))', toy_events())
        need(con.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 11, 'Exact synthetic event count required')
    finally:
        con.close()
    def ref(name):
        return dict(path=name, sha256=sha(root/name))
    authorities = {}
    for name in ['control','automation','source','selector']:
        location = 'fixture-history/'+name+'.json'
        exclusive(root/location, dict(version=1, scope='synthetic_historical_authority_placeholder_only', authority=name, authenticates_actual_history=False))
        authorities[name] = ref(location)
    authorities['pool'] = ref(owner.SOURCE_INPUTS['pool'])
    spec = read(root/'fixture-setup/model-spec.json')
    need(sha(root/spec['model']['path']) == spec['model']['sha256'], 'Synthetic native model changed')
    choice = dict(candidate_id='B', models=dict(B=deepcopy(spec), W=deepcopy(spec)), authority_refs=authorities)
    evidence = []
    for stage in sorted(owner.h.STAGES):
        location = 'fixture-history/compute-'+stage+'.json'
        exclusive(root/location, dict(version=1, scope='synthetic_compute_fixture_not_historical_receipt', stage=stage,
            measured_active_wall_upper_seconds=0, declared_unmeasured_wall_upper_seconds=1))
        evidence.append(dict(stage=stage, measured_active_wall_upper_seconds=0, declared_unmeasured_wall_upper_seconds=1, receipt=ref(location)))
    exclusive(root/'fixture-history/compute-evidence.json', evidence)
    exclusive(root/'fixture-history/model-acceptance.json', dict(version=1, scope='synthetic_admission_stub_only', actual_439_authentication=False))
    request = dict(version=1, scope='prospective_reserved_reporting_owner', owner_source=ref(owner.OWNER), policy=ref(owner.POLICY),
        model_acceptance=ref('fixture-history/model-acceptance.json'), compute_evidence=ref('fixture-history/compute-evidence.json'),
        code_fingerprints={name:sha(root/name) for name in owner.CODE}, role_entries={role:ref(path) for role,path in owner.x.ENTRY.items()},
        authority_paths={name:'artifacts/acceptance/synthetic-'+name+'.json' for name in sorted(owner.AUTHORITY_KEYS)},
        source_inputs={name:ref(path) for name,path in owner.SOURCE_INPUTS.items()})
    exclusive(root/'fixture-history/request.json', request)
    pins = {reference['path']:reference['sha256'] for reference in list(request['source_inputs'].values())+list(authorities.values())+
        [request['model_acceptance'], spec['model']]}
    return request, choice, pins


def issuer(owner, real_await, trace):
    """Explicit self-issued test gates, then unchanged production gate checker."""
    def issue(session, prepared, name, expected):
        path = owner.local(prepared['request']['authority_paths'][name])
        need(not path.exists(), 'No fixture authority may be reissued')
        count = {'initial_execution':0, 'source_acceptance':2, 'prediction_acceptance':4, 'target_execution':4}[name]
        need(len(session.states) == count and session.active is None, 'Fixture gate before actual reaped role boundary')
        body = dict(version=1, approved=True, scope={'initial_execution':'reserved_source_inference_execution',
            'source_acceptance':'reviewed_reserved_source', 'prediction_acceptance':'reviewed_all_reserved_predictions_before_targets',
            'target_execution':'report_only_reserved_fullY'}[name], run_id=session.plan['run_id'], fingerprints=owner.closure(session))
        if name != 'initial_execution':
            body['sealed_at'] = utc_now()
        if name == 'source_acceptance':
            source = owner.read_ref(owner.role_output(session,'source','source-manifest.json'), session.budget.guard)
            body.update(days=source['days'], proof_limits=owner.SOURCE_PROOF_LIMITS)
        elif name == 'prediction_acceptance':
            inventory_path = session.relative(session.directory/'all-predictions-inventory.json')
            body['inventory'] = dict(path=inventory_path, sha256=session.authority_pins[inventory_path])
        elif name == 'target_execution':
            policy_path = session.relative(session.directory/'target-policy.json')
            body['target_policy'] = dict(path=policy_path, sha256=session.authority_pins[policy_path])
        value = expected(deepcopy(body))
        need(canonical(value) == canonical(body), 'Fixture authority differs before real admission')
        exclusive(path, body)
        trace.append(dict(gate=name, completed_roles=[row['role'] for row in session.states], issued_at=utc_now(),
            issued_monotonic=time.monotonic(), self_issued_synthetic=True))
        return real_await(session, prepared, name, expected)
    return issue


def validate_deltas(periods):
    """Check every declared W=B metric/draw; undefined draws remain None."""
    estimands = {'conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero'}
    inspected = 0
    for period in periods.values():
        need(set(period['metrics']) == {'B','W'} and canonical(period['metrics']['B']) == canonical(period['metrics']['W']), 'W=B metric vectors differ')
        need(set(period['ndcg_W_minus_B']) == estimands and set(period['paired_user_bootstrap']) == estimands, 'All four estimands required')
        for estimand, delta in period['ndcg_W_minus_B'].items():
            need(delta is None or type(delta) in (int,float) and delta == 0, 'W=B nonzero declared metric delta'); inspected += 1
            bootstrap = period['paired_user_bootstrap'][estimand]
            need(bootstrap['estimand'] == estimand and bootstrap['seed'] == 2026 and bootstrap['replicates'] == 200 and len(bootstrap['samples']) == 200, 'All original paired user draws required')
            need(bootstrap['estimate'] == delta, 'Observed paired W=B difference differs')
            need(all(value is None or type(value) in (int,float) and value == 0 for value in bootstrap['samples']), 'W=B nonzero paired user draw')
            need(bootstrap['undefined_draws'] == sum(value is None for value in bootstrap['samples']), 'Undefined draws were replaced or redrawn')
            interval = bootstrap['interval_95']
            need(interval is None or interval == [0.0,0.0], 'W=B nonzero paired interval')
    return inspected


def verify_results(root, owner, report, consumer_calls, gate_trace, freeze):
    need(consumer_calls == 1, 'Exactly one synthetic historical admission required')
    need(report['status'] == 'verified_reporting_pending_external_lifetime_acceptance' and report['external_exit_tail_acceptance_required'] is True, 'Actual owner terminal state differs')
    need([row['role'] for row in report['roles']] == list(owner.x.ROLES) and len(gate_trace) == 4, 'Exactly six real roles/four gates required')
    claim = read(root/owner.CLAIM); directory = root/claim['output_directory']
    need(not list(root.rglob('*failed.json')), 'Known failed marker cannot become test success')
    source = read(directory/'source/source-manifest.json'); expected_calls = sum(row['candidate_count'] > 0 for row in source['days'])
    need(source['days'][0]['query_count'] > 0 and source['days'][0]['candidate_count'] == 0, 'First empty-C eligible query lost')
    need(source['days'][-1]['query_count'] == 0 and source['days'][-1]['candidate_count'] == 0, 'Final empty Q/C date lost')
    for index, role in enumerate(owner.x.ROLES):
        context = read(directory/role/'context.json'); receipt = read(directory/role/'receipt.json')
        boundary = read(directory/(role+'-reaped.json'))
        need(boundary['explicitly_reaped_exit_code'] == 0 and receipt['labels_loaded'] is (index >= 4), 'Actual reaped role capability differs')
        need(receipt['fit_attempt_count'] == 0 and receipt['descendant_cpu_seconds'] == 0, 'Forbidden role fit/descendant')
        need(receipt['native_prediction_count'] == (expected_calls if role in {'predictions','prediction_oracle'} else 0), 'Actual native-call count differs')
        expected_entry = owner.x.ENTRY[role]
        launch = read(directory/role/'launch.json')
        need(context['entry']['path'] == expected_entry and launch['argv'][1] == str(root/expected_entry), 'Actual fixed worker entry differs')
        need(not list((directory/role).glob('oracle-scratch-*')), 'Oracle scratch not closed')
        spill = directory/role/'spill'
        need(not spill.exists() or not any(spill.iterdir()), 'Producer spill retains active material')
    source_core = read(directory/'source_oracle/evidence.json')['core']
    need(source_core['baseline_formula_values_complete'] is False and source_core['chosen_columns'] == 0 and source_core['chosen_scalar_values'] == 0, 'Toy source proof scope differs')
    eval_body = read(directory/'targets_evaluation/evaluation.json')
    need(eval_body['periods']['confirmation25_reporting_only']['support']['target_pairs'] == 1, 'Duplicate fullY anchor purchase did not deduplicate')
    need(eval_body['periods']['confirmation25_reporting_only']['support']['candidate_pairs'] == 0, 'First unretrieved positive silently inserted into C')
    need(set(eval_body['periods']) == {'confirmation25_reporting_only','final26_31_frozen'}, 'Both fixed reporting windows required')
    checked_deltas = validate_deltas(eval_body['periods'])
    need(checked_deltas > 0, 'No explicit W=B delta field was checked')
    metric = read(directory/'metric_oracle/evidence.json')['core']
    need(metric['bootstrap_replicates_per_estimand'] == 200 and metric['private_ranking_rows_checked'] == 2*sum(d['query_count'] for d in source['days']), 'Independent all-query/paired-draw support differs')
    all_pins = {}
    def refs(value):
        if isinstance(value, dict):
            if 'fingerprints' in value:
                for name, digest in value['fingerprints'].items():
                    previous = all_pins.get(name); need(previous in (None,digest), 'Conflicting final fingerprint closure'); all_pins[name] = digest
            if set(value) == {'path','sha256'}:
                previous = all_pins.get(value['path']); need(previous in (None,value['sha256']), 'Conflicting final reference'); all_pins[value['path']] = value['sha256']
            for child in value.values():
                refs(child)
        elif isinstance(value, list):
            for child in value:
                refs(child)
    for path in [root/'fixture-history/request.json', root/owner.CLAIM, directory/'proposal.json'] + list(directory.rglob('*.json')):
        refs(read(path)); all_pins[str(path.relative_to(root))] = sha(path)
    for name, digest in all_pins.items():
        need(sha(root/name) == digest, 'Final bound evidence changed')
    for name, digest in freeze['production_files'].items():
        need(sha(root/name) == digest, 'Final copied code/config changed')
    own = resource.getrusage(resource.RUSAGE_SELF); children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(version=1, **DISCLOSURES, status='six_roles_complete_pending_supervisor_exit_tail',
        actual_roles=list(owner.x.ROLES), actual_gate_order=[row['gate'] for row in gate_trace], native_calls_each_prediction_role=expected_calls,
        query_count=sum(row['query_count'] for row in source['days']), candidate_pairs=sum(row['candidate_count'] for row in source['days']),
        source_baseline_numeric_scope='core18_sampled_not_exhaustive', chosen_columns=0, checked_W_equals_B_delta_fields=checked_deltas,
        actual_parent_cpu_seconds=own.ru_utime+own.ru_stime, actual_reaped_children_cpu_seconds=children.ru_utime+children.ru_stime,
        actual_total_cpu_seconds=own.ru_utime+own.ru_stime+children.ru_utime+children.ru_stime,
        elapsed_seconds=time.monotonic()-ENTRY_MONOTONIC, evidence_fingerprints=all_pins, gate_trace=gate_trace,
        external_exit_tail_acceptance_required=True, unknown_active_work=False, production_report_status=report['status'])


def run_controller(root, freeze_path, freeze_sha256):
    root = safe_root(root); freeze = load_freeze(freeze_path, freeze_sha256)
    need(root == safe_root(freeze['isolated_root']), 'Original reviewed isolated root cannot be replaced/refilled')
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    need(child.ru_utime+child.ru_stime == 0, 'Controller must start with no previous reaped children')
    need(not any(name == 'scripts' or name.startswith('scripts.') or name == 'tests' or name.startswith('tests.') for name in sys.modules), 'Fresh controller project module namespace required')
    exclusive(root/'integration-controller.consumed.json', dict(version=1, **DISCLOSURES, started_monotonic=ENTRY_MONOTONIC))
    owner = None
    try:
        # Leave inherited hard CPU unlimited: real workers install their original
        # role caps (up to900). The separate test supervisor enforces60 total.
        sys.path.insert(0, str(root))
        from scripts import run_heldout_reporting as owner
        need(owner.ROOT == root, 'Owner ROOT must derive from copied exact file')
        for name, digest in freeze['production_files'].items():
            need(sha(root/name) == digest, 'Copied production pin changed before owner')
        request, choice, pins = fixture_request(root, owner)
        from scripts import feature_program_control as control
        real_consumer = control.verify_choice; real_await = owner.await_external
        calls = 0; gates = []
        def synthetic_history(path, *, check):
            nonlocal calls
            need(calls == 0, 'Synthetic admission is once-only, never refill')
            calls += 1; check()
            need(path == root/request['model_acceptance']['path'] and (root/owner.CLAIM).exists(), 'Historical seam before consumed original owner')
            return dict(acceptance=deepcopy(request['model_acceptance']), pins=deepcopy(pins), authenticated_choice=deepcopy(choice))
        control.verify_choice = synthetic_history
        owner.await_external = issuer(owner, real_await, gates)
        try:
            report = owner.run_owner(root/'fixture-history/request.json')
        finally:
            control.verify_choice = real_consumer; owner.await_external = real_await
        for name, module in list(sys.modules.items()):
            if name.startswith(('scripts.','tests.')) and getattr(module,'__file__',None):
                need(Path(module.__file__).resolve().is_relative_to(root), 'Controller project import escaped isolated root')
                need(str(Path(module.__file__).resolve().relative_to(root)) in owner.CODE, 'Controller imported unpinned project dependency')
        result = verify_results(root, owner, report, calls, gates, freeze)
        exclusive(root/'integration-result.json', result)
    except BaseException as error:
        try:
            exclusive(root/'integration.failed.json', dict(version=1, **DISCLOSURES, status='failed_consumed_no_retry',
                error_type=type(error).__name__, unknown_active_work=True, targets_may_have_opened=True))
        except BaseException as secondary:
            error.add_note('Integration failure persistence: '+type(secondary).__name__)
        raise


def processes(expected_sha256):
    """Execute the issued original source bytes; never consult an unpinned pyc."""
    need(type(expected_sha256) is str and re.fullmatch('[a-f0-9]{64}',expected_sha256) is not None, 'Issued supervisor source SHA required')
    with PROCESSES.open('rb') as stream:
        raw = stream.read(2**20+1)
    need(len(raw) <= 2**20 and hashlib.sha256(raw).hexdigest() == expected_sha256, 'Original supervisor source bytes changed')
    module = types.ModuleType('tlab_harness_processes'); module.__file__ = str(PROCESSES)
    sys.modules[module.__name__] = module
    exec(compile(raw,str(PROCESSES),'exec',dont_inherit=True),module.__dict__)
    return module


def _supervise(stage, root, freeze_path, freeze_sha256):
    freeze_path = Path(freeze_path).resolve(); freeze = load_freeze(freeze_path, freeze_sha256); root = safe_root(root)
    need(stage in {'setup','integration'}, 'Finite setup/integration stage only')
    need(root == safe_root(freeze['isolated_root']), 'Original reviewed isolated root cannot be replaced/refilled')
    if stage == 'setup':
        # The root itself is the once-consumed setup namespace; never recreate it.
        create_copy(root, freeze)
    else:
        setup = read(root/'setup-supervision.json')
        need(setup['status'] == 'verified_normal_exit' and setup['exit_code'] == 0 and setup['reviewed_freeze_sha256'] == freeze_sha256 and not (root/'fixture-setup/failed.json').exists(), 'Successful original paid setup prerequisite absent')
        need(sha(root/'fixture-setup/model-spec.json') == setup['bound_outputs']['fixture-setup/model-spec.json'] and sha(root/'fixture-setup/B.cbm') == setup['bound_outputs']['fixture-setup/B.cbm'], 'Setup original model/spec changed')
    exclusive(root/(stage+'-supervisor.consumed.json'), dict(version=1, stage=stage, started_monotonic=ENTRY_MONOTONIC,
        reviewed_freeze_sha256=freeze_sha256, cpu_seconds=60, wall_seconds=120, job_rss_bytes=2**30 if stage=='setup' else 2*2**30, automatic_retry=False))
    argv = [freeze['python'], str(BUILDER if stage=='setup' else Path(__file__).resolve()), '--root', str(root), '--freeze', str(freeze_path), '--issued-freeze-sha256', freeze_sha256]
    if stage == 'integration':
        argv += ['--child']
    observation = processes(freeze['harness_files'][str(PROCESSES)]).supervise(argv, root/(stage+'-process.log'), started=ENTRY_MONOTONIC,
        cpu_seconds=60, wall_seconds=120, rss_bytes=2**30 if stage=='setup' else 2*2**30, cwd=root)
    observation.update(version=1, stage=stage, reviewed_freeze_sha256=freeze_sha256, scope='synthetic_six_role_integration_only',
        counter_rule='supervisor_SELF_plus_wait4_child_tree_once; role_subtotals_are_cross_checks_only')
    if observation['status'] == 'verified_normal_exit' and observation['exit_code'] == 0:
        need(observation['unknown_active_work'] is False and observation['cpu_upper_seconds'] <= 60 and observation['elapsed_upper_seconds'] <= 120,
            'Known normal finite test-process boundary required')
        names = ['fixture-setup/model-spec.json','fixture-setup/B.cbm','fixture-setup/result.json'] if stage=='setup' else ['integration-result.json']
        observation['bound_outputs'] = {name:sha(root/name) for name in names}
        result = read(root/names[-1])
        if stage == 'setup':
            need(result['status'] == 'setup_complete_pending_external_exit_tail' and result['fit_attempt_count'] == 1 and result['training_rows'] == 8,
                'Original counted synthetic setup proof absent')
        else:
            need(result['status'] == 'six_roles_complete_pending_supervisor_exit_tail' and result['unknown_active_work'] is False and
                all(result[name] == value for name,value in DISCLOSURES.items()), 'Original scoped six-role ledger absent')
        expected_cpu = result['child_cpu_seconds'] if stage=='setup' else result['actual_total_cpu_seconds']
        need(observation['wait4_child_cpu_seconds'] + .05 >= expected_cpu, 'External wait4 tree CPU fails terminal subtotal cross-check')
    exclusive(root/(stage+'-supervision.json'), observation)
    need(observation['status'] == 'verified_normal_exit' and observation['exit_code'] == 0, 'Consumed synthetic stage failed; no retry/refit/cap raise')
    if stage == 'integration':
        setup = read(root/'setup-supervision.json')
        exclusive(root/'harness-ledger.json', dict(version=1, **DISCLOSURES, status='synthetic_six_role_test_verified',
            setup_reaped_child_cpu_seconds=setup['wait4_child_cpu_seconds'], integration_reaped_child_cpu_seconds=observation['wait4_child_cpu_seconds'],
            setup_job_cpu_upper_seconds=setup['cpu_upper_seconds'], integration_job_cpu_upper_seconds=observation['cpu_upper_seconds'],
            total_job_cpu_upper_seconds=setup['cpu_upper_seconds']+observation['cpu_upper_seconds'],
            exact_supervisor_exit_tail_measured=False,
            setup_elapsed_seconds=setup['elapsed_seconds'], integration_elapsed_seconds=observation['elapsed_seconds'],
            setup_observed_job_peak_rss_bytes=setup['observed_job_peak_rss_bytes'], integration_observed_job_peak_rss_bytes=observation['observed_job_peak_rss_bytes'],
            unknown_active_work=False, full_owner_exit_tail_verified=True, actual_historical_439_authentications=0,
            setup_supervision_sha256=sha(root/'setup-supervision.json'), integration_supervision_sha256=sha(root/'integration-supervision.json'),
            integration_evidence_sha256=sha(root/'integration-result.json')))


def supervise(stage, root, freeze_path, freeze_sha256):
    need(stage in {'setup','integration'}, 'Finite setup/integration stage only')
    root = safe_root(root); previously_consumed = (root/(stage+'-supervisor.consumed.json')).exists()
    try:
        return _supervise(stage, root, freeze_path, freeze_sha256)
    except BaseException as error:
        if not previously_consumed and (root/(stage+'-supervisor.consumed.json')).exists():
            try:
                exclusive(root/(stage+'-supervision.failed.json'), dict(version=1, scope='synthetic_six_role_integration_only',
                    stage=stage, status='failed_consumed_no_retry', reviewed_freeze_sha256=freeze_sha256,
                    error_type=type(error).__name__, unknown_active_work=True, automatic_retry=False,
                    process_cleanup_evidence=deepcopy(getattr(error,'supervisor_cleanup_evidence',None))))
            except BaseException as secondary:
                error.add_note('Supervision failure persistence: '+type(secondary).__name__)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root', required=True); parser.add_argument('--freeze', required=True)
    parser.add_argument('--issued-freeze-sha256', required=True)
    parser.add_argument('--stage', choices=['setup','integration']); parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    need((args.stage is None) == args.child, 'Exactly one finite supervisor stage or controller child mode required')
    if args.child:
        run_controller(args.root, args.freeze, args.issued_freeze_sha256)
    else:
        supervise(args.stage, args.root, args.freeze, args.issued_freeze_sha256)
