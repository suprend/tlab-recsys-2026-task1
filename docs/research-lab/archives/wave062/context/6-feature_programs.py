"""Symbolic schema -> bounded typed programs, independently of data or labels.

This module generates definitions and closure/draw artifacts. It never reads an
experiment collection, executes SQL, fits a model or grants execution approval.
Human-authored schema semantics/templates and fixed windows remain explicit.
"""
from copy import deepcopy
import hashlib
import json
import platform
import random

from scripts.manual_features import HEADER, GRAINS, validate_registry

CONTEXT = dict(history='strict_past_raw_event_rows', source_availability='event_time_assumed',
               peer_policy='exclude_all_global_timestamp_peers', count_boundary='lower_inclusive_upper_exclusive',
               recency_boundary='full_observed_prefix', identity='nominal_keys_not_numeric_model_features',
               retrieval_alias_policy='v1_purchase_distinct_users_168h_full_join_including_recent_only')
PREFIX = [('from_popular','BOOLEAN'),('from_recent','BOOLEAN'),('popularity_distinct_users','BIGINT'),
          ('popular_source_rank','BIGINT'),('recent_source_rank','BIGINT'),
          ('candidate_category_ambiguous','BOOLEAN'),('candidate_category_missing','BOOLEAN'),
          ('item_has_observed_history','BOOLEAN'),('user_has_observed_history','BOOLEAN'),
          ('item_observed_age_seconds','DOUBLE'),('user_observed_age_seconds','DOUBLE')]
SUFFIX = [('retrieval_last_event_age_seconds','DOUBLE'),('retrieval_last_event_missing','BOOLEAN')]


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _keys(value,keys,kind):
    if not isinstance(value,dict) or set(value)!=set(keys):
        raise ValueError(kind+' fields differ from the declared contract')


def _feature(grain,action,operator,window,column=None):
    token = str(window)+'h' if type(window) is int else 'observed'
    name = 'auto_'+grain+'_'+action+'_'+operator+'_'+token
    if operator=='count_distinct':name+='_'+column
    return dict(name=name,grain=grain,event_type=action,operator=operator,window=window,column=column)


def _signature(feature):
    # Context is common and separately bound in every pool identity. Names are
    # presentation only; semantic equality must survive a rename.
    return tuple(feature[k] for k in ['grain','operator','event_type','window','column'])


def _model_schema(registry):
    by_grain={}
    for f in registry['features']:
        if f['operator']!='ratio':by_grain.setdefault(f['grain'],[]).append(f)
    columns=list(PREFIX)
    for fs in by_grain.values():
        columns.extend((f['name'],'DOUBLE' if f['operator']=='recency_seconds' else 'BIGINT') for f in fs)
    windows=sorted({f['window'] for f in registry['features'] if f['operator']!='ratio' and type(f['window']) is int})
    columns.extend(('source_coverage_'+str(w)+'h','DOUBLE') for w in windows)
    columns.extend((f['name'],'DOUBLE') for f in registry['features'] if f['operator']=='ratio')
    columns.extend((f['name']+'_missing','BOOLEAN') for f in registry['features']
                   if f['operator'] in {'ratio','recency_seconds'} or 'category_id' in GRAINS[f['grain']])
    columns.extend(SUFFIX)
    if len({n for n,t in columns})!=len(columns):raise ValueError('Physical model schema contains duplicate names')
    return columns


def _validate_contract(contract):
    _keys(contract,{'version','role','schema','context','grammar','allocation'},'Program contract')
    if type(contract['version']) is not int or contract['version']!=1 or contract['role']!='bounded_typed_feature_programs':
        raise ValueError('Unsupported program contract version/role')
    if contract['context']!=CONTEXT:raise ValueError('Unsupported temporal/source semantics')
    schema=contract['schema'];_keys(schema,{'fields','observed_actions'},'Declared schema')
    if schema['fields']!={'user_id':dict(dtype='BIGINT',role='nominal_user'),
                         'product_id':dict(dtype='BIGINT',role='nominal_item'),
                         'event_time':dict(dtype='TIMESTAMP',role='event_time'),
                         'event_type':dict(dtype='VARCHAR',role='action'),
                         'category_id':dict(dtype='BIGINT',role='nullable_nominal_category')}:
        raise ValueError('Explicit typed schema adapter is required; semantics cannot be inferred from names')
    if schema['observed_actions']!=['view','cart','purchase']:
        raise ValueError('All declared actions must be observed capabilities, not invented zeros')
    grammar=contract['grammar'];_keys(grammar,{'operators','windows_hours','action_count_bindings','action_distinct_bindings','cart_recency_bindings'},'Grammar')
    if grammar['operators']!=['count','count_distinct','recency_seconds'] or grammar['windows_hours']!=[24,168] or any(type(w) is not int for w in grammar['windows_hours']):
        raise ValueError('Only the reviewed005 vocabulary/windows are supported')
    allocation=contract['allocation'];_keys(allocation,{'static_bundle_ids','random_draws','random_seed','random_law','collision_policy','max_new_columns','max_fits'},'Allocation')
    if (allocation['static_bundle_ids']!=['L02','L06'] or type(allocation['random_draws']) is not int
            or allocation['random_draws']!=2 or type(allocation['random_seed']) is not int
            or allocation['random_seed']!=2026 or allocation['random_law']!='uniform_independent_with_replacement'
            or allocation['collision_policy']!='whole_bundle_across_all_slots_consumed_no_redraw'
            or type(allocation['max_new_columns']) is not int or allocation['max_new_columns']!=12
            or type(allocation['max_fits']) is not int or allocation['max_fits']!=4):
        raise ValueError('Frozen static/random allocation and budgets cannot silently change')
    return deepcopy(contract)


def generate_pool(contract,base_registry):
    """Return8 generated bundles with exact3-column closure; no data is opened.

    Failure of any reviewed template/alias/closure stops the whole proposal.
    The output records human templates and the exact generated registries, so
    generation is inspectable rather than a list of prewritten feature JSONs.
    """
    contract=_validate_contract(contract);base=validate_registry(base_registry)
    base_schema=_model_schema(base);base_names={n for n,t in base_schema}
    if len(base_schema)!=41 or len(base['features'])!=18:
        raise ValueError('The final base41/manual18 control must remain explicit')
    actions=contract['schema']['observed_actions'];grammar=contract['grammar'];recipes=[]
    expected_bindings = {
        'action_count_bindings':[dict(grain='user',window=24),dict(grain='pair',window=24),dict(grain='item',window=168)],
        'action_distinct_bindings':[dict(grain='user',windows_by_action=dict(view=24,cart=168,purchase=168)),dict(grain='item',windows_by_action=dict(view=24,cart=168,purchase=24))],
        'cart_recency_bindings':[dict(grain='pair',companion_grain='item',companion_operator='count',companion_action='cart',companion_window=24),dict(grain='user',companion_grain='user',companion_operator='count_distinct',companion_action='purchase',companion_window=24),dict(grain='item',companion_grain='item',companion_operator='count_distinct',companion_action='cart',companion_window=24)]}
    if any(_canonical(grammar[k])!=_canonical(v) for k,v in expected_bindings.items()):
        raise ValueError('Changed template bindings require an explicit new prospective review')
    for binding in grammar['action_count_bindings']:
        _keys(binding,{'grain','window'},'Action-count binding')
        grain,window=binding['grain'],binding['window']
        recipes.append(('action_counts',binding,[_feature(grain,a,'count',window) for a in actions]))
    for binding in grammar['action_distinct_bindings']:
        _keys(binding,{'grain','windows_by_action'},'Action-distinct binding')
        grain=binding['grain'];windows=binding['windows_by_action']
        if set(windows)!=set(actions):raise ValueError('Every observed action needs one reviewed window')
        # The schema's opposite nominal entity, never an arbitrary numeric field.
        column={'user':'product_id','item':'user_id'}.get(grain)
        if column is None:raise ValueError('Distinct template requires user/item entity')
        recipes.append(('action_distinct',binding,[_feature(grain,a,'count_distinct',windows[a],column) for a in actions]))
    for binding in grammar['cart_recency_bindings']:
        _keys(binding,{'grain','companion_grain','companion_operator','companion_action','companion_window'},'Cart-recency binding')
        op=binding['companion_operator'];grain=binding['companion_grain']
        column={'user':'product_id','item':'user_id'}.get(grain) if op=='count_distinct' else None
        recipes.append(('cart_recency_plus_stat',binding,[_feature(binding['grain'],'cart','recency_seconds','observed','event_time'),
             _feature(grain,binding['companion_action'],op,binding['companion_window'],column)]))
    if len(recipes)!=8:raise ValueError('The reviewed common pool contains exactly8 templates')
    aliases={_signature(f) for f in base['features'] if f['operator']!='ratio'}
    aliases.add(('item','count_distinct','purchase',168,'user_id')) # accepted retrieval score, also recent-only C
    bundles=[];seen=set()
    for i,(family,binding,features) in enumerate(recipes,1):
        registry=deepcopy(base);registry['name']='typed_L'+str(i).zfill(2);registry['features']+=features
        registry=validate_registry(registry)
        if any(_signature(f) in aliases for f in features):raise ValueError('Generated program aliases frozen B/retrieval')
        signatures=sorted([_signature(f) for f in features],key=_canonical);signature=_digest(signatures)
        if signature in seen:raise ValueError('Duplicate whole bundle')
        seen.add(signature)
        emitted=_model_schema(registry);delta=[(n,t) for n,t in emitted if n not in base_names]
        if len(delta)!=3 or len({n for n,t in delta})!=3:raise ValueError('A legal bundle must emit exactly3 new physical columns')
        if any(n in base_names for f in features for n in [f['name'],f['name']+'_missing']):raise ValueError('Generated name collides with frozen B')
        if any((n,t) not in emitted for n,t in base_schema):raise ValueError('Generated registry changed base schema')
        bundles.append(dict(bundle_id='L'+str(i).zfill(2),family=family,binding=deepcopy(binding),programs=features,
             semantic_signature=signature,physical_delta=[dict(name=n,dtype=t) for n,t in delta],registry=registry,
             model_feature_order=[n for n,t in base_schema]+[n for n,t in delta]))
    identity=dict(version=1,role=contract['role'],contract=contract,base_registry=base,
                  base_model_schema=[dict(name=n,dtype=t) for n,t in base_schema],bundles=bundles,
                  source_semantic_scope='manual18/v1 declared semantics; source/protocol/artifact hashes must be bound externally',
                  execution_bindings_required=['source_and_protocol_hashes','accepted_Q_C_Y_and_feature_lineage',
                      'final019_trained_iterations_scoring_prefix_and_population','physical_and_simulated_decision_lock'],
                  execution_approved=False)
    return dict(pool_id=_digest(identity),identity=identity)


def allocate_slots(pool):
    """Freeze2static +2uniform replacement draws, consuming collisions.

    No caller-supplied seed or exclusions can adapt the frozen random law.
    The returned object is a symbolic allocation, not fit/execution permission.
    """
    if set(pool)!= {'pool_id','identity'} or _digest(pool['identity'])!=pool['pool_id']:
        raise ValueError('Pool digest mismatch')
    identity=pool['identity'];expected=generate_pool(identity['contract'],identity['base_registry'])
    if pool!=expected:raise ValueError('Pool structure differs from canonical generated proposal')
    bundles={b['bundle_id']:b for b in identity['bundles']};policy=identity['contract']['allocation']
    rng=random.Random(policy['random_seed']);before=rng.getstate()
    drawn=rng.choices(sorted(bundles),k=policy['random_draws']);after=rng.getstate()
    selected=[*policy['static_bundle_ids'],*drawn];seen={};slots=[]
    for name,bundle_id in zip(['I1','I2','R1','R2'],selected):
        bundle=bundles[bundle_id];signature=bundle['semantic_signature'];collision=seen.get(signature)
        slots.append(dict(slot=name,bundle_id=bundle_id,semantic_signature=signature,
                          status='collision_consumed_no_refill' if collision else 'planned_unexecuted',
                          duplicate_of=collision,new_physical_columns=0 if collision else 3,fit_budget_slots_consumed=1,native_fits_started=0,
                          slot_consumed=True,execution_approved=False))
        if not collision:seen[signature]=name
    result=dict(pool_id=pool['pool_id'],slots=slots,random=dict(implementation='python.random.Random.choices',
         python_version=platform.python_version(),seed=policy['random_seed'],pool_order=sorted(bundles),
         state_before_sha256=_digest(before),state_after_sha256=_digest(after),drawn=drawn),
         max_fits=4,max_new_physical_columns=12,execution_approved=False)
    return dict(allocation_id=_digest(result),identity=result)


def registry_for_slot(pool,allocation,slot):
    """Return the exact fullB+program registry for one unexecuted legal slot."""
    if allocation!=allocate_slots(pool):raise ValueError('Allocation differs from the frozen law')
    matches=[s for s in allocation['identity']['slots'] if s['slot']==slot]
    if len(matches)!=1 or matches[0]['status']!='planned_unexecuted':
        raise ValueError('Unknown/colliding slot cannot be replaced or materialized')
    return deepcopy(next(b['registry'] for b in pool['identity']['bundles'] if b['bundle_id']==matches[0]['bundle_id']))
