"""Read frozen small metadata only; never resolve or open physical refs."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json
import resource
import signal
import time

resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
signal.alarm(60)
started = time.monotonic()
cpu0 = resource.getrusage(resource.RUSAGE_SELF)
BASE = Path('/tmp/tlab-development-reference-handoff-independent-inputs')
ROOT = '/Users/mdpospelov/tlab-recsys-2026/'
checks = []


def need(value, label):
    assert value, label
    checks.append(label)


def read_small(path):
    need(path.stat().st_size <= 8 * 1024 * 1024, 'bounded input: ' + str(path))
    return path.read_bytes()


hraw = read_small(BASE / 'tlab-root-development-day-reference-handoff-prepared.json')
need(hashlib.sha256(hraw).hexdigest() == 'fd7304383e9c025d205a0b7f9060187f8062daa9baa2f9b0f86ea6a18323e05b', 'exact Root handoff raw SHA')
h = json.loads(hraw)
metadata = {}
for row in json.loads(read_small(BASE / 'metadata-ledger.json'))['inputs']:
    raw = read_small(Path(row['copy']))
    need(hashlib.sha256(raw).hexdigest() == row['sha256'], 'snapshot raw SHA: ' + row['input_key'])
    if row['input_key'].endswith('.json'):
        metadata[row['input_key']] = json.loads(raw)

acceptance = metadata[h['historical_acceptance']['path']]
selection_path = 'artifacts/acceptance/tlab017-selection-collection.json'
selection = metadata[selection_path]
selection_report = metadata[selection['complete_attempt_report']]
prefix = metadata[h['source']['prefix_acceptance']['path']]
kernel = metadata[h['source']['kernel_evidence']['path']]
life = metadata[acceptance['external_lifetime']['path']]
report = metadata[life['owner_report']['path']]
run_path = str(PurePosixPath(life['owner_report']['path']).parent / 'run.json')
run = metadata[run_path]
identity = run['identity']
anchor_path = next(k for k in metadata if '/anchor/' in k and k.endswith('/run.json'))
anchor = metadata[anchor_path]
schema = metadata['/tmp/tlab-development-source-to-score-concrete-schema-proposal.json']
bindings = metadata['/tmp/tlab-development-source-to-score-model-source-bindings-proposal.json']
pins = acceptance['fingerprints']

need(h['execution_granted'] is False and h['full438_or439_streaming_performed'] is False and h['models_or_data_files_opened'] is False, 'prepared scope is explicitly non-runtime')
need(acceptance['approved'] is True and acceptance['scope'] == 'reviewed_fixed_procedure_feature_program_models', 'historical accepted model scope')
need(len(pins) == 438, 'historical 438 map count inspected without traversal')
need(acceptance['run_id'] == run['run_id'] == report['run_id'] == life['run_id'], 'historical metadata run identities agree')
for name in [acceptance['external_lifetime']['path'], life['owner_report']['path'], run_path]:
    need(h['metadata_pins'][name]['sha256'] == pins[name], 'historical metadata anchored: ' + name)
need(life['explicitly_reaped_exit_code'] == 0, 'historical lifetime records explicit exit zero')
need(report['status'] == 'model_outputs_verified_pending_external_acceptance' and report['fit_attempt_count'] == report['sum_metric_looks'] == 4 and report['observer_calls'] == 1, 'historical finite choice evidence counts')
need(acceptance['heldout_targets_opened'] is False and report['heldout_labels_opened'] is False, 'historical heldout disclosure preserved')
need(acceptance['selected_spec']['candidate_id'] == report['winner']['candidate_id'] == 'R2' and acceptance['selected_spec']['bundle_id'] == identity['slots']['R2']['bundle_id'] == 'L05', 'historical fixed R2 L05 choice')

B, W = h['models']['B'], h['models']['W']
spec = acceptance['selected_spec']
need(B == bindings['models']['B'] and W == bindings['models']['W'], 'handoff exact model dictionaries equal prepared bindings')
need(B['model']['path'] == identity['baseline']['model_path'] and B['model']['sha256'] == pins[B['model']['path']], 'B model ref anchored in accepted identity')
need(B['feature_names'] == identity['feature_names'] == identity['baseline']['feature_names'], 'B41 feature order anchored')
need(B['effective_parameters'] == identity['native_reference'], 'B native effective parameters anchored')
need(W['model'] == spec['model'] and W['feature_names'] == spec['feature_names'] == report['winner']['feature_names'] == identity['slots']['R2']['feature_names'], 'W model and W44 order anchored')
need(W['effective_parameters'] == spec['native_effective_parameters'] == B['effective_parameters'], 'W native parameters match accepted spec and B')
need(len(B['feature_names']) == 41 and len(W['feature_names']) == 44 and W['feature_names'][:41] == B['feature_names'], 'B41 W44 exact prefix contract')
need(all(m['population'] == 26000 and m['trained_iterations'] == m['scoring_prefix'] == 300 for m in [B, W]), 'accepted population and finite 300 tree prefixes')
need(spec['physical_delta'] == identity['slots']['R2']['physical_delta'] == [{'name': name, 'dtype': 'BIGINT'} for name in W['feature_names'][41:]], 'three selected physical BIGINT extras')
need(schema['model_feature_names'] == {'B': B['feature_names'], 'W': W['feature_names']}, 'concrete schema model order matches handoff')
need(len(schema['base_feature_schema']) == 45 and len(schema['extra_feature_schema']) == 5, 'physical B45 and two-key three-extra schema')
need(schema['extra_feature_schema'] == [['query_id', 'VARCHAR'], ['product_id', 'BIGINT']] + [[n, 'BIGINT'] for n in W['feature_names'][41:]], 'five-column chosen-extra projection exact')
need(selection_report['collection']['feature_columns'] == [r[0] for r in schema['base_feature_schema']], 'B45 ordered fields anchored by accepted collection metadata')
need(len(identity['expected_source_schema']) == 57, 'historical union57 schema count')
union = dict(identity['expected_source_schema'])
need(all(union.get(n) == t for n, t in schema['base_feature_schema'] + schema['extra_feature_schema']), 'B45 and chosen3 types present in historical union57')

old_protocol = copy.deepcopy(anchor['identity']['protocol'])
old_protocol['pilot']['end'] = '2019-10-23T00:00:00Z'
old_protocol['budget'] = {'max_anchors': 2000, 'max_candidate_pairs': 440000}
need(h['protocol'] == old_protocol == schema['protocol'], 'one day protocol differs from accepted two-day protocol only by end and budgets')
need(selection['approved'] is True and selection['collection_id'] == selection_report['collection_id'] == identity['collection_ids']['selection'], 'accepted selection collection identity')
need(selection_report['collection']['counts']['queries'] == 4000 and selection_report['collection']['daily_anchors'] == ['2019-10-22T00:00:00Z', '2019-10-23T00:00:00Z'], 'global reference has complete 4000 queries across exact two days')

refs = h['reference_artifacts']
for role, collection_kind in [('all_selection_queries', 'queries'), ('all_selection_candidates', 'candidates'), ('all_selection_base45', 'features')]:
    need([r['path'] for r in refs[role]] == selection_report['collection']['artifact_refs'][collection_kind], 'complete accepted collection refs: ' + role)
    for r in refs[role]:
        need(r['sha256'] == selection['fingerprints'][r['path']] == pins[r['path']], 'physical historical expected SHA: ' + role)
need(refs['day_selected_union57']['path'] == identity['daily_features']['selection'][0], 'day22 union57 ref selected from accepted identity')
need(refs['B_saved_scores']['path'] == identity['baseline']['score_path'] and refs['W_saved_scores'] == spec['scores'], 'B/W saved NPZ refs anchored')
physical = [h['source']['database'], B['model'], W['model'], refs['B_saved_scores'], refs['W_saved_scores'], *refs['all_selection_queries'], *refs['all_selection_candidates'], *refs['all_selection_base45'], refs['day_selected_union57']]
need(len(physical) == len({r['path'] for r in physical}) == 9, 'nine explicit physical refs for future current hashing')
for r in physical:
    p = PurePosixPath(r['path'])
    need(not p.is_absolute() and '..' not in p.parts and str(p) == r['path'], 'project relative physical ref: ' + r['path'])
    if r != h['source']['database']:
        need(pins[r['path']] == r['sha256'], 'expected physical SHA from accepted historical map: ' + r['path'])
need(refs['score_npz_members'] == ['group', 'product_id', 'raw_score'], 'saved NPZ has group keys requiring global query map')
need(refs['global_group_policy'] == 'full4000selectionQsortedquery_id row_number_minus1 BEFORE dayfilter; comparebyquery_id,product_id', 'explicit global mapping before day filter')

need(prefix['source_prefix_accepted'] is True and prefix['actual_heldout_authorized'] is False and prefix['complete_TLAB018_accepted'] is False and prefix['query_targets_opened'] is False, 'accepted source prefix scope not whole reproduction')
need(kernel['database']['path'] == ROOT + h['source']['database']['path'] and kernel['database']['sha256'] == h['source']['database']['sha256'], 'new typed source DB expected identity')
need(any(r['path'] == kernel['database']['path'] and r['sha256'] == kernel['database']['sha256'] for r in prefix['large_current_bindings']), 'Root source acceptance binds same new DB')
need(kernel['summary'] == prefix['summary'] and kernel['summary']['rows'] == 42448764, 'source accepted summary consistency')
need(kernel['fit_attempt_count'] == 0 and kernel['labels_created'] is False and len(kernel['schema']) == 9, 'typed9 source metadata remains source-only')
need(h['source']['raw_or_canonical_spools_required_to_rehash'] is False, 'no raw or canonical spool rehash demand')
need(schema['native_scores'] == {'type': 'float64', 'prediction_type': 'RawFormulaVal', 'ntree_start': 0, 'ntree_end': 300, 'thread_count': 2, 'models': 2, 'fits': 0}, 'fixed two native prediction contracts metadata only')
need(h['future_candidate_bounds']['CPU_seconds'] == 600 and h['future_candidate_bounds']['wall_seconds'] == 900 and h['future_candidate_bounds']['RSS_bytes'] == 8 * 2**30, 'future proposal bounds remain the stated ungranted bounds')

# Tiny literal witness: an empty-C query must still shift later NPZ groups.
queries = [('a22', 22), ('b23-empty', 23), ('c22', 22), ('d23', 23)]
global_map = {qid: n for n, (qid, day) in enumerate(sorted(queries))}
local_map = {qid: n for n, (qid, day) in enumerate(sorted(q for q in queries if q[1] == 22))}
need(global_map['c22'] == 2 and local_map['c22'] == 1, 'literal global group mapping exposes day-local/empty-C shift')
huge_item = 2**53 + 1
need(int(float(huge_item)) != huge_item, 'literal BIGINT witness requires exact integer key transport')

cpu1 = resource.getrusage(resource.RUSAGE_SELF)
result = {'scope': 'frozen bounded metadata and pure literal checks only', 'status': 'PASS', 'checks': checks, 'check_count': len(checks), 'required_future_physical_refs': physical, 'future_grant': False, 'historical_438_recertified': False, 'physical_refs_opened_or_hashed': 0, 'native_calls': 0, 'helper_calls': 0, 'data_or_model_imports': 0, 'project_writes': 0, 'cpu_seconds': cpu1.ru_utime + cpu1.ru_stime - cpu0.ru_utime - cpu0.ru_stime, 'wall_seconds': time.monotonic() - started}
out = Path('/tmp/tlab-development-reference-handoff-independent-check-results.json')
with out.open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['checks', 'required_future_physical_refs']}))
