"""Source-only wave004 review: stdlib, synthetic literals, no project imports.

Executes selected unchanged AST definitions from the reviewed generator and
registry validator. Other project modules (including DuckDB) are never imported.
This is an isolated symbolic gate test, not an event adapter or quality test.
"""
import ast
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import random
import re
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path('/tmp/tlab-wave004-literal-results-public-copy.json')
started = time.process_time()

paths = [ROOT/'scripts/feature_programs.py', ROOT/'scripts/manual_features.py',
         ROOT/'configs/features/automation-pool.json', ROOT/'configs/features/manual-18.json']
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def selected_definitions(path, functions, assignments, namespace):
    tree = ast.parse(path.read_text(), filename=str(path))
    kept = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            kept.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in assignments for t in node.targets):
            kept.append(node)
    assert len(kept) == len(functions) + len(assignments)
    exec(compile(ast.Module(body=kept, type_ignores=[]), str(path), 'exec'), namespace)

manual = {'re': re, 'deepcopy': deepcopy}
selected_definitions(paths[1], {'_keys', 'validate_registry'}, {'GRAINS', 'HEADER'}, manual)
program = {'deepcopy': deepcopy, 'json': json, 'hashlib': hashlib,
           'platform': platform, 'random': random,
           'GRAINS': manual['GRAINS'], 'validate_registry': manual['validate_registry']}
selected_definitions(paths[0], {'_canonical', '_digest', '_keys', '_feature', '_signature',
                              '_model_schema', '_validate_contract', 'generate_pool', 'allocate_slots'},
                     {'CONTEXT', 'PREFIX', 'SUFFIX'}, program)

contract = json.loads(paths[2].read_text())
base = json.loads(paths[3].read_text())
cases = []

def expect_rejection(name, call, message):
    try:
        call()
    except ValueError as error:
        assert message in str(error), (name, str(error))
        cases.append({'case': name, 'outcome': 'expected_rejection', 'reason': str(error)})
    else:
        raise AssertionError(name + ' unexpectedly passed')

pool = program['generate_pool'](contract, base)
allocation = program['allocate_slots'](pool)
assert len(pool['identity']['bundles']) == 8
assert pool['identity']['execution_approved'] is False
assert allocation['identity']['execution_approved'] is False
assert [s['bundle_id'] for s in allocation['identity']['slots']] == ['L02', 'L06', 'L01', 'L05']
cases.append({'case': 'unchanged_symbolic_control', 'outcome': 'pass',
              'bundles': 8, 'slots': ['L02', 'L06', 'L01', 'L05'],
              'execution_approved': False, 'scope': 'symbolic declarations only'})

review_only = deepcopy(contract)
review_only['schema']['observed_actions'] = ['review']
expect_rejection('honest_review_only_capability',
                 lambda: program['generate_pool'](review_only, base),
                 'All declared actions must be observed capabilities')

raw_retail = deepcopy(contract)
fields = raw_retail['schema']['fields']
fields['visitorid'] = fields.pop('user_id')
fields['itemid'] = fields.pop('product_id')
expect_rejection('raw_RetailRocket_schema_without_typed_mapping',
                 lambda: program['generate_pool'](raw_retail, base),
                 'Explicit typed schema adapter is required')

reduced = deepcopy(base)
reduced['features'] = [f for f in reduced['features'] if f['grain'] in {'user', 'item', 'pair'}]
assert len(reduced['features']) == 12
reduced_columns = len(program['_model_schema'](manual['validate_registry'](reduced)))
expect_rejection('reduced_common12_cannot_inherit_frozen_pool',
                 lambda: program['generate_pool'](contract, reduced),
                 'The final base41/manual18 control must remain explicit')
cases[-1]['reduced_core_count'] = 12
cases[-1]['reduced_physical_model_columns_under_current_builder'] = reduced_columns

# No source rows reach the generator. An untruthful copy is indistinguishable
# from a truthful declaration here; the external source gate must bind evidence.
assert program['generate_pool'](deepcopy(contract), base) == pool
cases.append({'case': 'declaration_cannot_authenticate_business_event_truth',
              'outcome': 'symbolic_pass_without_source_evidence',
              'interpretation': 'Not a generator bug; no source verifier or purchase observability is exercised'})

# Literal RetailRocket boundary witness, integer source-ms and exact rational
# recency. T is a synthetic UTC-midnight epoch, not an observed source endpoint.
H = 86_400_000
T = 10*H
events = [('u', 'x', 'view', T-H), ('u', 'x', 'view', T-1),
          ('u', 'x', 'cart', T-1000), ('u', 'x', 'cart', T-1000),
          ('v', 'x', 'view', T), ('u', 'z', 'purchase', T),
          ('u', 'w', 'purchase', T+H)]
past24 = [e for e in events if T-H <= e[3] < T]
cart = [e for e in past24 if e[2] == 'cart' and e[1] == 'x']
views = [e for e in past24 if e[2] == 'view' and e[1] == 'x']
target = sorted({e[1] for e in events if e[0] == 'u' and e[2] == 'purchase' and T <= e[3] < T+H})
assert len(cart) == 2 and len({e[0] for e in cart}) == 1 and len(views) == 2
assert Fraction(T-max(e[3] for e in views), 1000) == Fraction(1, 1000)
assert target == ['z'] and 'z' not in {'x'}
cases.append({'case': 'RetailRocket_literal_ms_bag_global_peer_fullY', 'outcome': 'pass',
              'synthetic_event_rows': 7, 'cart_rows': 2, 'distinct_cart_users': 1,
              'view_rows': 2, 'view_recency_seconds_exact': '1/1000',
              'fullY': ['z'], 'off_C_target_retained': True,
              'scope': 'Independent literal arithmetic; no real adapter or dataset rows'})

# Metadata state is per property. Business-event context and query-current
# context are intentionally different; later snapshots must not change either.
props = [('x', 'category', 'A', T-4*3_600_000),
         ('x', 'category', 'B', T-3_600_000),
         ('x', 'available', '0', T-1_800_000),
         ('x', 'category', 'C', T+3_600_000)]
def property_state(rows, item, key, cutoff):
    eligible = [p for p in rows if p[0] == item and p[1] == key and p[3] < cutoff]
    if not eligible:
        return None
    latest = max(p[3] for p in eligible)
    values = {p[2] for p in eligible if p[3] == latest}
    return next(iter(values)) if len(values) == 1 and None not in values else None

event_time = T-3*3_600_000
historical = property_state(props, 'x', 'category', event_time)
current = property_state(props, 'x', 'category', T)
assert historical == 'A' and current == 'B'
assert property_state(props, 'x', 'available', T) == '0'
assert property_state(props[:-1], 'x', 'category', T) == current
mixed = props + [('x', 'category', None, T-3_600_000)]
assert property_state(mixed, 'x', 'category', T) is None
cases.append({'case': 'RetailRocket_literal_two_category_policies', 'outcome': 'pass',
              'synthetic_property_rows': 5, 'frozen_last_event_category': 'A',
              'query_current_property_category': 'B', 'known_plus_NULL_bucket': None,
              'future_suffix_invariant': True,
              'scope': 'Own literal resolver, not production EventFact adapter'})

# Both worlds have exactly the same released review fields but different true
# next-day purchases. This checks the written counterexample, not hidden truth.
release_A = {'user_id': 'u', 'parent_asin': 'i', 'timestamp': T+10*H, 'verified_purchase': True}
release_B = deepcopy(release_A)
purchases_A = [('i', T+3_600_000), ('j', T+7_200_000)]
purchases_B = [('i', T-7*H)]
Y_A = sorted({i for i, t in purchases_A if T <= t < T+H})
Y_B = sorted({i for i, t in purchases_B if T <= t < T+H})
assert release_A == release_B and Y_A == ['i', 'j'] and Y_B == []
cases.append({'case': 'Amazon_review_purchase_nonidentifiability', 'outcome': 'pass',
              'same_released_row': True, 'true_purchase_Y_world_A': Y_A,
              'true_purchase_Y_world_B': Y_B,
              'scope': 'Constructed worlds; proof witness only, no actual Y accessed'})

after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
assert before == after
result = {'schema_version': 1, 'outcome': 'pass', 'case_count': len(cases),
          'cases': cases, 'source_pins_before': before, 'source_pins_after': after,
          'source_bytes_unchanged': True, 'cpu_seconds': time.process_time()-started,
          'scope': 'stdlib AST-isolated symbolic gate plus hand literals; no project module imports, actual data, SQL, native ML, fits, weights, API or download',
          'data_or_model_jobs_admitted': 0, 'runtime_adapter_quality_test': False}
with OUT.open('x') as file:
    json.dump(result, file, indent=2)
    file.write('\n')
print(json.dumps({'outcome': result['outcome'], 'cases': len(cases),
                  'cpu_seconds': result['cpu_seconds'], 'source_bytes_unchanged': True}))
