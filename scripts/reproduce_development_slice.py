"""Additive018 one-day core adapter proposal; importing performs no native work.

No owner CLI or execution authority is provided by this draft. A future measured
owner supplies the private connection, exact cores, authenticated model loader,
project-relative outputs and original lifetime guards. Existing cores stay intact.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import math
import re

DAY='2019-10-22T00:00:00Z'
END='2019-10-23T00:00:00Z'
REQUIRED_QUERIES=2000
MAX_ROWS=440000
EXTRAS=[('auto_item_view_count_distinct_24h_user_id','BIGINT'),
        ('auto_item_cart_count_distinct_168h_user_id','BIGINT'),
        ('auto_item_purchase_count_distinct_24h_user_id','BIGINT')]
OUTPUT_NAMES={'queries':'queries.parquet','candidates':'candidates.parquet',
              'base_features':'base-features.parquet','extra_features':'extra-features.parquet',
              'B':'B-scores.parquet','W':'W-scores.parquet'}


def need(value,message):
    if not value:raise ValueError(message)


def quote(name):
    need(type(name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name),'Safe declared SQL identifier required')
    return '"'+name+'"'


def one_day_protocol(base):
    value=deepcopy(base)
    need(value['query']['eligibility_hours']==48 and value['query']['sampling']=='sha256_user_day_seed_before_labels'
         and value['query']['sample_seed']==2026,'Fixed query population semantics required')
    value['pilot']=dict(start=DAY,end=END)
    value['query']['max_users_per_day']=REQUIRED_QUERIES
    value['budget']=dict(max_anchors=REQUIRED_QUERIES,max_candidate_pairs=REQUIRED_QUERIES*220)
    return value


def rekey_reference_scores(all_query_ids,groups,items,scores,selected_query_ids):
    """Pure key transport only: groups belong to the full original Q population.

    No target relation, metric, file IO or comparison permission is supplied.
    Retain complete selected Q separately so empty-C queries cannot disappear.
    """
    need(type(all_query_ids) is list and all(type(x) is str and x for x in all_query_ids)
         and all_query_ids==sorted(set(all_query_ids)),'Complete canonical original Q order required')
    need(type(selected_query_ids) is list and selected_query_ids==sorted(set(selected_query_ids))
         and set(selected_query_ids)<=set(all_query_ids),'Selected Q must be canonical original subset')
    need(len(groups)==len(items)==len(scores),'Equal saved vector lengths required')
    selected=set(selected_query_ids);result=[];last=None
    for group,item,score in zip(groups,items,scores):
        need(type(group) is int and 0<=group<len(all_query_ids) and type(item) is int
             and -2**63<=item<2**63,'Exact original group/int64 item keys required')
        need(type(score) in (float,int) and math.isfinite(score),'Finite original scalar score required')
        key=(group,item);need(last is None or key>last,'Original grouped item keys must be unique and ordered');last=key
        qid=all_query_ids[group]
        if qid in selected:result.append((qid,item,float(score)))
    return result


def build_and_score(con,*,config,pool,models,cores,load_model,export,check,stage):
    """Run only existing label-blind cores, project-relative exports and two scores.

    ``cores`` explicitly supplies already-authenticated anchors/retrieval/compiler/
    programs/schema/inference/predictions plus numpy/pandas. ``export(name,sql)``
    owns exclusive project-relative Parquet output and returns its relative name.
    It must not create acceptance. ``load_model(ref)`` authenticates/opens the
    exact externally reviewed CBM inside the original budget, never fits.
    """
    need(callable(check) and callable(stage) and callable(export) and callable(load_model),'Original measured caller hooks required')
    check();config=cores.protocol.validate_protocol(config)
    need(config['pilot']==dict(start=DAY,end=END) and config['query']['max_users_per_day']==REQUIRED_QUERIES
         and config['query']['eligibility_hours']==48 and config['query']['sample_seed']==2026,
         'One fixed Oct22 population required')
    need(config['target']['horizon_hours']==24 and config['target']['availability_delay_seconds']==0,
         'Fixed calendar-only maturity required')
    need(set(models)=={'B','W'},'Exact fixed B/W only')
    allocation=cores.programs.allocate_slots(pool)
    slot=next(row for row in allocation['identity']['slots'] if row['slot']=='R2')
    need(slot['bundle_id']=='L05' and slot['status']=='planned_unexecuted','Fixed selected R2/L05 required')
    registry=cores.programs.registry_for_slot(pool,allocation,'R2')
    base=pool['identity']['base_registry']
    base_schema=cores.schema.HEADER+cores.schema.generated_schema(base)
    combined_schema=cores.schema.HEADER+cores.schema.generated_schema(registry)
    need(len(base_schema)==45 and len(combined_schema)==48,'Exact B45/chosen48 physical schemas required')
    names=[n for n,t in cores.programs._model_schema(base)]
    need(len(names)==41 and models['B']['feature_names']==names
         and models['W']['feature_names']==names+[n for n,t in EXTRAS],
         'Immutable B41 and appended selected3 model feature order required')
    for spec in models.values():
        need(spec['trained_iterations']==300 and spec['scoring_prefix']==300 and spec['population']==26000,
             'Fixed already-trained model metadata required')
    def guarded(name,operation):
        check();result=stage(name,operation);check();return result
    core_result=cores.anchors.create_queries(con,config,stage=guarded,budget_check=check)
    target_end=datetime.fromisoformat(DAY.replace('Z','+00:00'))+timedelta(hours=24)
    source_end=datetime.fromisoformat(config['source']['end'].replace('Z','+00:00'))
    mature=target_end<=source_end
    guarded('calendar_only_maturity',lambda:con.execute('UPDATE pilot_queries SET label_is_mature=?',[mature]))
    cores.retrieval.create_candidates(con,config,stage=guarded)
    cores.retrieval.verify_catalog(con,config,stage=guarded)
    cores.compiler.create_manual_features(con,config,registry,stage=guarded,budget_check=check)
    actual=[tuple(row[:2]) for row in con.execute('DESCRIBE manual_features').fetchall()]
    need(actual==combined_schema,'Actual chosen48 schema/order differs')
    query_count=con.execute('SELECT count(*),count(DISTINCT query_id),count(DISTINCT(user_id,anchor)) FROM pilot_queries').fetchone()
    need(query_count==(REQUIRED_QUERIES,)*3,'Exact complete required query population missing')
    qids=[row[0] for row in con.execute('SELECT query_id FROM pilot_queries ORDER BY query_id').fetchall()]
    count,unique=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM pilot_candidates').fetchone()
    need(count==unique and count<=MAX_ROWS,'Exact unique full C exceeds finite bound')
    fields=','.join(quote(n) for n,t in base_schema)
    con.execute('CREATE OR REPLACE TEMP VIEW reproduction_base AS SELECT '+fields+' FROM manual_features')
    con.execute('CREATE OR REPLACE TEMP VIEW reproduction_extra AS SELECT query_id,product_id,'+
                ','.join(quote(n) for n,t in EXTRAS)+' FROM manual_features')
    missing=con.execute('''SELECT count(*) FROM((SELECT query_id,product_id FROM pilot_candidates EXCEPT ALL SELECT query_id,product_id FROM reproduction_base)
        UNION ALL(SELECT query_id,product_id FROM reproduction_base EXCEPT ALL SELECT query_id,product_id FROM pilot_candidates))''').fetchone()[0]
    need(missing==0,'Fixed C/base full key cover differs')
    outputs={}
    for name,relation,order in [('queries','pilot_queries','query_id'),('candidates','pilot_candidates','query_id,product_id'),
         ('base_features','reproduction_base','query_id,product_id'),('extra_features','reproduction_extra','query_id,product_id')]:
        outputs[name]=guarded('export_'+name,lambda name=name,relation=relation,order=order:export(name,'SELECT * FROM '+relation+' ORDER BY '+order))
    np=cores.np;pd=cores.pd;native_calls=0;domains=None
    for role in ['B','W']:
        spec=models[role];extra=role=='W'
        data=guarded('load_'+role,lambda:cores.inference.load_inference_data(
            [outputs['queries']],[outputs['base_features']],expected_feature_names=list(spec['feature_names']),
            extra_feature_paths=[outputs['extra_features']] if extra else None,
            extra_feature_names=[n for n,t in EXTRAS] if extra else [],
            max_queries=REQUIRED_QUERIES,max_rows=MAX_ROWS,check=check))
        need([q[0] for q in data.queries]==qids and len(data.items)==count
             and data.feature_names==spec['feature_names'] and data.calendar_maturity.all(),
             'Inference full Q/C/maturity/schema differs')
        current=(tuple(qids),tuple(map(int,data.group)),tuple(map(int,data.items)))
        need(domains is None or current==domains,'B/W candidate key domains differ');domains=current
        witness=hashlib.sha256(data.x.tobytes()).hexdigest()
        model=guarded('load_model_'+role,lambda:load_model(deepcopy(spec['model'])))
        cores.predictions.verify_model(model,spec)
        if count:
            native_calls+=1
            raw=guarded('predict_'+role,lambda:model.predict(data.x,prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2))
        else:raw=np.empty(0,dtype=np.float64)
        cores.predictions.verify_model(model,spec)
        need(type(raw) is np.ndarray and raw.dtype==np.float64 and raw.shape==(count,) and np.isfinite(raw).all(),
             'Exact finite float64 scalar predictions required')
        need(hashlib.sha256(data.x.tobytes()).hexdigest()==witness,'Native caller changed input matrix')
        frame=pd.DataFrame({'query_id':pd.Series([qids[int(g)] for g in data.group],dtype='string'),
                            'product_id':data.items.copy(),'raw_score':raw.copy()})
        con.register('reproduction_scores',frame)
        try:outputs[role]=guarded('export_scores_'+role,lambda role=role:export(role,'SELECT query_id,product_id,raw_score FROM reproduction_scores ORDER BY query_id,product_id'))
        finally:con.unregister('reproduction_scores')
        del frame,data,model,raw;check()
    need(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('pilot_labels','pilot_target_windows')").fetchone()[0]==0,
         'Core must never create target relations')
    check();return dict(status='source_to_scores_pending_independent_output_and_full_exit_acceptance',
        anchor=DAY,query_count=REQUIRED_QUERIES,candidate_count=count,base_physical_columns=45,
        chosen_physical_columns=48,model_columns=dict(B=41,W=44),outputs=outputs,
        native_prediction_calls=native_calls,fit_attempt_count=0,metric_looks=0,
        query_target_relation_created=False,labels_fabricated=False,reserved_targets_opened=False,
        source_acceptance_issued=False,source_formula_acceptance=False,
        interpretation='postselection_development_mechanical_replay_only',source_query_build=core_result)


"""TMP-only additive owner DRAFT; stdlib-only import, no authority or supervisor.

Integrate below the reviewed one_day_protocol/build_and_score core in the sole
future scripts/reproduce_development_slice.py. This file alone cannot execute a
slice. Root supplies the exact original request SHA and narrow reference handoff
only after review. No current invocation, budget or data access is authorized.

The external driver MUST reuse accepted V6 process supervision for the entire
stage (owner, independent output verifier, serialization and exit tails). Local
checks cannot interrupt blocked native calls or prove full process-tree RSS.
There is no authority issuer, approval flag, arbitrary module/loader callback,
new supervisor, reference evaluator, target reader, fitting or metric path here.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import resource
import stat
import sys
import time
from types import SimpleNamespace


OWNER_SCOPE = 'existing018_oct22_source_to_scores_postselection_development'
OWNER_FILE = 'scripts/reproduce_development_slice.py'
OWNER_OUT = 'artifacts/development-source-to-score-runs'
OWNER_JSON_CAP = 262144
OWNER_DB_SHA = '4168068b05a5f7033876c05427037732322abe77fd2f97eef3ceca59d42ba786'
OWNER_CSV_SHA = 'e58ae129792ed9ce848644343d75698a506c0c2bcc5b2da6a30db283e85db4c2'
OWNER_RECEIPT_SHA = '3599ad5882356deb9a7252ea8bb69c6395b57b719acae9dca92c04d80431fab8'
OWNER_SUPERVISOR_SHA = '449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
OWNER_HANDOFF_SHA = 'fd7304383e9c025d205a0b7f9060187f8062daa9baa2f9b0f86ea6a18323e05b'
OWNER_CONFIG_SHA = {
    'protocol': 'c985f552fa8a935122adaac9856b4c95bdfbbf390a099afee589124b50304ed9',
    'manual_registry': '44587dd2106ab9bbfc9ec1faa0c496703969ca401894eea73f84a93700b41d9c',
    'pool_contract': 'ef34f45d244bb0458c2af7928c0dad7f57d178d397abee1a9e87e419457cbbb3',
}
OWNER_MODEL_SHA = {'B': 'a60a82894ed9385a7b4f38784e7ea34ed9476966557387924406f803343f2b2e',
                   'W': '35eb3837db9dcabe0aa2c15a2d999e0c44feb98d39d6ae1da10a19b37c6928ec'}
OWNER_MODULES = (
    'anchor_pilot', 'candidate_pilot', 'development_collection', 'feature_programs',
    'heldout_contract', 'heldout_predictions', 'heldout_source', 'heuristic_baselines',
    'inference_data', 'manual_features', 'protocol_manifest', 'ranking_metrics',
    'temporal_contract', 'train_baselines',
)
OWNER_CODE_PATHS = {f'scripts/{name}.py' for name in OWNER_MODULES} | {OWNER_FILE}
OWNER_EXISTING_CODE = {
    'scripts/heldout_predictions.py': 'e1b06b2aac68c59379d15298c39101ec02b6a176c26b13d4671f8e445de2851b',
    'scripts/inference_data.py': '3ed9e1c2d06d77302d1d39dbe2604fb7d778e18a4dcb583d3eb7ddd30236f8dd',
    'scripts/protocol_manifest.py': '0a8aa0fe4213226665d1f7ff61393dd7b7aacfe0df094c3f22a781982929ffc0',
    'scripts/temporal_contract.py': 'c85adccbd861463051c479b96f9dffdc8dfd920326e08c55ddefe6b5bbd41d66',
    'scripts/train_baselines.py': 'bdab8bbe0ed4863dd9922e436c38699a0c69e0d2846289ab9f5a63b44c52412a',
    'scripts/development_collection.py': 'd3d811e7987812366d36163537bdd8784ccb55ef3e1596ba7bf6d02338f80f3c',
    'scripts/heuristic_baselines.py': 'db00b2375fed1083d4bf9b45ef4535793d36ffeaa537050a07e99c61dad13ee4',
    'scripts/ranking_metrics.py': '90c3a02d69bb7850eda24a61526978e53e70ffc3856f44c5204e6409b833c9a9',
    'scripts/candidate_pilot.py': 'c6044b683acafb3d7a90d2310037e65c46699d98b640e46cb1a45f4f4314fa70',
    'scripts/anchor_pilot.py': 'd9344599ae1d64780374ede5006644e1f9983ed84085d0c8a64ec76fd99c835d',
    'scripts/manual_features.py': 'e2558299783a04aba34432fe72c0e7e16e6ddbcbfd074bdf18e8b09eae224103',
    'scripts/heldout_contract.py': 'fc50d11d3b6dfdc2906522472f5b66138424bc4586e7833b43c6fc4e6c4f1abc',
    'scripts/heldout_source.py': 'c864bec3a3aefa946b7759993505bcde9dcd9c9edb7cb9ce03216d6ebddeafbb',
    'scripts/feature_programs.py': 'afaefd6b2a608870d952c0782d2ca9fcbd685f9650afe6229ee74772bab92bf7',
}
OWNER_PARITY = ('allQdiagnostics/calendar', 'allCfields/keys',
    'everyB45/threeextrasvaluekey/type/NULL/mask', 'float32representationequivalence',
    'allkeyedfinitefloat64scoresabs1e-12', 'completequeryrankorder_descscore_ascitemid')
OWNER_REFERENCE = {'B_saved_scores', 'W_saved_scores', 'all_selection_base45',
    'all_selection_candidates', 'all_selection_queries', 'day_selected_union57',
    'global_group_policy', 'score_npz_members'}
OWNER_GROUP_POLICY = 'full4000selectionQsortedquery_id row_number_minus1 BEFORE dayfilter; comparebyquery_id,product_id'
OWNER_EVENTS = [('event_time', 'TIMESTAMP'), ('event_type', 'VARCHAR'),
                ('product_id', 'BIGINT'), ('category_id', 'BIGINT'),
                ('category_code', 'VARCHAR'), ('brand', 'VARCHAR'),
                ('price', 'DECIMAL(12,2)'), ('user_id', 'BIGINT'), ('user_session', 'VARCHAR')]


def _owner_need(value, message):
    if not value:
        raise ValueError(message)


def _owner_keys(value, keys, message):
    _owner_need(type(value) is dict and set(value) == set(keys), message)


def _owner_sha(value):
    _owner_need(type(value) is str and len(value) == 64
                and all(c in '0123456789abcdef' for c in value), 'Exact SHA256 required')
    return value


def _owner_rel(value):
    _owner_need(type(value) is str and value and '\\' not in value
                and not value.startswith('/') and all(c.isascii() and
                (c.isalnum() or c in '._-/') for c in value), 'Normalized project-relative path required')
    path = PurePosixPath(value)
    _owner_need(str(path) == value and all(p not in ('', '.', '..') for p in path.parts),
                'Normalized project-relative path required')
    return value


def _owner_ref(value):
    _owner_keys(value, {'path', 'sha256'}, 'Exact path/SHA reference required')
    _owner_rel(value['path']); _owner_sha(value['sha256'])
    return value


def _owner_path(root, name):
    _owner_rel(name)
    root = root.resolve(strict=True)
    path = root.joinpath(name)
    # Reject every symlink component, including a still nonexistent output leaf.
    current = root
    for part in PurePosixPath(name).parts:
        current = current / part
        _owner_need(not current.is_symlink(), 'Symlink file references are forbidden')
    _owner_need(path.resolve().is_relative_to(root), 'Reference leaves installed project')
    return path


def _owner_unique(pairs):
    result = {}
    for key, value in pairs:
        _owner_need(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def _owner_json(raw):
    _owner_need(type(raw) is bytes and 0 < len(raw) <= OWNER_JSON_CAP, 'Bounded small JSON required')
    def reject(value):
        raise ValueError('Nonfinite JSON constant forbidden: ' + value)
    def finite_float(value):
        result = float(value)
        _owner_need(math.isfinite(result), 'Nonfinite JSON float forbidden')
        return result
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_owner_unique,
                       parse_constant=reject, parse_float=finite_float)
    _owner_need(type(value) is dict, 'JSON object required')
    return value


def _owner_small(path, expected_sha):
    _owner_sha(expected_sha)
    before = path.stat()
    _owner_need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= OWNER_JSON_CAP,
                'Bounded regular JSON file required')
    with path.open('rb') as handle:
        raw = handle.read(OWNER_JSON_CAP + 1)
    after = path.stat()
    _owner_need(all(getattr(before, key) == getattr(after, key) for key in
                ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
                and hashlib.sha256(raw).hexdigest() == expected_sha,
                'Small JSON byte identity changed')
    return _owner_json(raw), raw


def _owner_request(value):
    """Pure admission only. A passing declaration does not grant execution."""
    _owner_keys(value, {'version', 'scope', 'execution_id', 'source', 'protocol',
        'manual_registry', 'pool_contract', 'models', 'reference_handoff', 'code',
        'environment', 'resources', 'output_directory', 'comparison'}, 'Request fields differ')
    _owner_need(type(value['version']) is int and value['version'] == 1
                and value['scope'] == OWNER_SCOPE, 'Fixed existing018 development scope required')
    execution = value['execution_id']
    _owner_need(type(execution) is str and 1 <= len(execution) <= 96
                and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in execution)
                and execution[0] != '-' and execution[-1] != '-', 'Explicit one-shot execution ID required')
    _owner_need(value['output_directory'] == OWNER_OUT + '/' + execution,
                'Output namespace must be fixed and bound to original execution ID')
    source = value['source']
    _owner_keys(source, {'prefix_acceptance', 'database', 'kernel_evidence',
                        'raw_or_canonical_spools_required_to_rehash'}, 'Source fields differ')
    for name in ('prefix_acceptance', 'database', 'kernel_evidence'): _owner_ref(source[name])
    _owner_need(source['database']['sha256'] == OWNER_DB_SHA
                and source['prefix_acceptance']['sha256'] == OWNER_RECEIPT_SHA
                and source['raw_or_canonical_spools_required_to_rehash'] is False,
                'Accepted new typed9 DB and distinct canonical CSV identities required')
    for name in ('protocol', 'manual_registry', 'pool_contract', 'reference_handoff'):
        _owner_ref(value[name])
        if name in OWNER_CONFIG_SHA:
            _owner_need(value[name]['sha256'] == OWNER_CONFIG_SHA[name], 'Immutable original config binding required: ' + name)
    _owner_need(value['reference_handoff']['sha256'] == OWNER_HANDOFF_SHA, 'Exact Root-prepared narrow handoff bytes required')
    _owner_keys(value['code'], OWNER_CODE_PATHS, 'Exact fixed 14-module closure and final runner required')
    for digest in value['code'].values(): _owner_sha(digest)
    _owner_need(all(value['code'][name] == digest for name, digest in OWNER_EXISTING_CODE.items()),
                'Immutable original existing core fingerprints required')
    _owner_keys(value['models'], {'B', 'W'}, 'Exactly B/W model specs required')
    for role, spec in value['models'].items():
        _owner_keys(spec, {'model', 'feature_names', 'trained_iterations', 'scoring_prefix',
                          'population', 'effective_parameters'}, 'Model spec fields differ')
        _owner_ref(spec['model'])
        _owner_need(spec['model']['sha256'] == OWNER_MODEL_SHA[role], 'Exact original fixed B/W model bytes required')
        _owner_need(type(spec['feature_names']) is list and len(spec['feature_names']) == (41 if role == 'B' else 44)
                    and len(set(spec['feature_names'])) == len(spec['feature_names'])
                    and all(type(x) is str and x and x.isascii() and
                    all(c.isalnum() or c == '_' for c in x) for x in spec['feature_names']),
                    'Fixed unique numeric feature names required')
        _owner_need(all(type(spec[k]) is int and spec[k] == n for k, n in
                    [('trained_iterations', 300), ('scoring_prefix', 300), ('population', 26000)])
                    and type(spec['effective_parameters']) is dict, 'Fixed model population/prefix required')
    _owner_need(value['models']['W']['feature_names'] == value['models']['B']['feature_names'] +
                [name for name, dtype in EXTRAS], 'Exact appended chosen three required')
    env = value['environment']
    _owner_keys(env, {'pyproject', 'uv_lock', 'interpreter_sha256', 'python_version',
        'implementation', 'packages', 'external_supervisor'}, 'Environment fields differ')
    for name in ('pyproject', 'uv_lock', 'external_supervisor'): _owner_ref(env[name])
    _owner_need(env['external_supervisor']['sha256'] == OWNER_SUPERVISOR_SHA,
                'Exact accepted V6 supervisor binding required')
    _owner_need(env['pyproject']['path'] == 'pyproject.toml' and env['uv_lock']['path'] == 'uv.lock',
                'Fixed environment manifests required')
    _owner_sha(env['interpreter_sha256'])
    _owner_need(type(env['python_version']) is list and len(env['python_version']) == 3
                and all(type(x) is int and x >= 0 for x in env['python_version'])
                and env['implementation'] == 'CPython', 'Exact interpreter identity required')
    _owner_keys(env['packages'], {'duckdb', 'numpy', 'pandas', 'catboost'}, 'Fixed native package metadata required')
    _owner_need(all(type(x) is str and 0 < len(x) <= 64 for x in env['packages'].values()),
                'Exact package versions required')
    bounds = value['resources']
    _owner_keys(bounds, {'total_cpu_seconds', 'total_wall_seconds', 'job_rss_bytes', 'threads',
        'engine_memory', 'spill_bytes', 'final_tail_cpu_seconds', 'final_tail_wall_seconds'}, 'Resource fields differ')
    for key, low, high in [('total_cpu_seconds', 30, 600), ('total_wall_seconds', 60, 900),
                         ('job_rss_bytes', 1, 8 * 2**30), ('spill_bytes', 0, 2 * 2**30),
                         ('final_tail_cpu_seconds', 5, 60), ('final_tail_wall_seconds', 10, 120)]:
        _owner_need(type(bounds[key]) is int and low <= bounds[key] <= high, 'Finite original resource bound required: ' + key)
    _owner_need(type(bounds['threads']) is int and bounds['threads'] == 2 and bounds['engine_memory'] == '2GB'
                and bounds['final_tail_cpu_seconds'] < bounds['total_cpu_seconds']
                and bounds['final_tail_wall_seconds'] < bounds['total_wall_seconds'], 'Fixed engines and reserved final tails required')
    comparison = value['comparison']
    _owner_keys(comparison, {'mode', 'same_stage_budget', 'anchor', 'original_query_count',
        'original_group_mapping', 'key', 'required_checks', 'references'}, 'Comparison fields differ')
    _owner_need(comparison['mode'] == 'external_independent_required' and comparison['same_stage_budget'] is True
                and comparison['anchor'] == DAY and type(comparison['original_query_count']) is int
                and comparison['original_query_count'] == 4000
                and comparison['original_group_mapping'] == OWNER_GROUP_POLICY
                and comparison['key'] == ['query_id', 'product_id']
                and comparison['required_checks'] == list(OWNER_PARITY), 'All-keyed parity within same original cap required')
    refs = comparison['references']
    _owner_keys(refs, OWNER_REFERENCE, 'Exact Root old fullQ/C/B45/union57/savedscores handoff required')
    _owner_need(refs['global_group_policy'] == OWNER_GROUP_POLICY
                and refs['score_npz_members'] == ['group', 'product_id', 'raw_score'],
                'Exact full4000Q saved NPZ key transport required')
    leaves = []
    for name in ('B_saved_scores', 'W_saved_scores', 'day_selected_union57'):
        leaves.append(_owner_ref(refs[name]))
    for name in ('all_selection_base45', 'all_selection_candidates', 'all_selection_queries'):
        _owner_need(type(refs[name]) is list and len(refs[name]) == 1, 'Exact Root single-shard reference list required')
        leaves.append(_owner_ref(refs[name][0]))
    inputs = [source[name]['path'] for name in ('prefix_acceptance', 'database', 'kernel_evidence')]
    inputs += [value[name]['path'] for name in ('protocol', 'manual_registry', 'pool_contract', 'reference_handoff')]
    inputs += [spec['model']['path'] for spec in value['models'].values()]
    inputs += list(value['code']) + [env[name]['path'] for name in ('pyproject', 'uv_lock', 'external_supervisor')]
    inputs += [ref['path'] for ref in leaves]
    out = value['output_directory']
    _owner_need(all(path != out and not path.startswith(out + '/') for path in inputs), 'Output overlaps immutable input')
    return value


def _owner_stat(path):
    value = path.stat()
    _owner_need(stat.S_ISREG(value.st_mode), 'Regular pinned file required')
    return dict(device=value.st_dev, inode=value.st_ino, size_bytes=value.st_size,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def _owner_hash(path, expected_sha, check):
    check(); before = _owner_stat(path); digest = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            check(); chunk = handle.read(1024 * 1024)
            if not chunk: break
            digest.update(chunk)
    check()
    _owner_need(_owner_stat(path) == before and digest.hexdigest() == expected_sha, 'Pinned bytes changed: ' + path.name)
    return dict(sha256=digest.hexdigest(), stat=before)


def _owner_json_default(value):
    # create_queries returns real UTC datetimes in population/scan_plans. Keep
    # only that documented type, never default=str or arbitrary object repr.
    if type(value) is datetime and value.tzinfo is not None and value.utcoffset() == timedelta(0):
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    raise TypeError('Only explicit UTC datetime report normalization is supported')


def _owner_encode(value):
    raw = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
                      default=_owner_json_default) + '\n').encode()
    _owner_need(len(raw) <= OWNER_JSON_CAP, 'Bounded report required')
    return raw


def _owner_write(path, value):
    raw = _owner_encode(value)
    with path.open('xb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _owner_consume(root, request, raw, request_sha):
    out = _owner_path(root, request['output_directory'])
    _owner_need(out.parent.is_dir(), 'Root must prepare the fixed output parent explicitly')
    out.mkdir(mode=0o700)  # No exist_ok/retry/new-ID fallback, even after a failure.
    try:
        _owner_write(out / 'consumed.json', dict(execution_id=request['execution_id'],
            original_request_sha256=request_sha, status='consumed_once_pending_external_acceptance',
            execution_authority_issued=False))
        with (out / 'request-snapshot.json').open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    except BaseException as exc:
        try:
            _owner_write(out / 'failure.json', dict(status='failed_consumed_no_retry',
                execution_id=request['execution_id'], original_request_sha256=request_sha,
                error_type=type(exc).__name__, error=str(exc)[:2048],
                independent_output_acceptance=None, external_full_exit_acceptance=None))
        except BaseException: pass
        raise
    return out


class _OwnerChecks:
    """Cooperative guards only; accepted V6 owns blocked-call/full lifetime limits."""
    def __init__(self, bounds, started, spill):
        _owner_need(type(started) in (int, float) and math.isfinite(started)
                    and 0 <= started <= time.monotonic(), 'Original external monotonic start required')
        self.bounds, self.started, self.spill = bounds, started, spill
        self.stages = []; self.spill_high = 0; self.rss_high = 0

    def telemetry(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        waited = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = usage.ru_utime + usage.ru_stime + waited.ru_utime + waited.ru_stime
        rss = usage.ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
        self.rss_high = max(self.rss_high, rss)
        total = 0
        if self.spill.exists():
            for index, path in enumerate(self.spill.rglob('*')):
                _owner_need(index < 4096 and not path.is_symlink(), 'Spill inventory escaped finite bound')
                if path.is_file(): total += path.stat().st_size
        self.spill_high = max(self.spill_high, total)
        return dict(cpu_seconds=cpu, wall_seconds=time.monotonic() - self.started,
                    process_peak_rss_bytes=rss, spill_bytes=total)

    def check(self):
        value = self.telemetry(); b = self.bounds
        _owner_need(value['cpu_seconds'] < b['total_cpu_seconds'] - b['final_tail_cpu_seconds']
                    and value['wall_seconds'] < b['total_wall_seconds'] - b['final_tail_wall_seconds']
                    and value['process_peak_rss_bytes'] <= b['job_rss_bytes']
                    and value['spill_bytes'] <= b['spill_bytes'], 'Original budget/tail reserve exhausted')

    def stage(self, name, operation):
        self.check(); _owner_need(len(self.stages) < 128, 'Finite stage ledger required')
        row = dict(name=name, before=self.telemetry(), status='entered'); self.stages.append(row)
        try:
            result = operation(); self.check(); row['status'] = 'returned'; return result
        except BaseException:
            row['status'] = 'failed'; raise
        finally:
            row['after'] = self.snapshot()

    def snapshot(self):
        try: return self.telemetry()
        except BaseException as exc:
            return dict(telemetry_unknown=True, error_type=type(exc).__name__, error=str(exc)[:512])


def _owner_runtime(root, out):
    _owner_need(sys.flags.isolated == 1 and sys.dont_write_bytecode is True,
                'Future external driver must use isolated Python -I -B')
    _owner_need(Path(__file__).resolve() == (root / OWNER_FILE).resolve(), 'TMP owner must first be integrated into fixed installed module')
    _owner_need(callable(globals().get('one_day_protocol')) and callable(globals().get('build_and_score')),
                'Reviewed core must be integrated into the same fixed module')
    _owner_need(not any(name == 'scripts' or name.startswith('scripts.') or name.split('.')[0] in
                {'duckdb', 'numpy', 'pandas', 'catboost'} for name in sys.modules), 'Fresh project/native import state required')
    cache = out / 'pycache'; cache.mkdir(mode=0o700)
    # -B alone can READ old caches. This previously nonexistent prefix plus -B
    # prevents reads of project caches and never writes new ones. It is set
    # before any project/native import; no custom importer/framework is needed.
    sys.pycache_prefix = str(cache)
    _owner_need(not (root / 'scripts' / '__init__.py').exists(), 'Fixed reviewed namespace-package closure required')


def _owner_authenticate(root, request, checks):
    pins = {}
    for name, digest in sorted(request['code'].items()):
        pins[name] = _owner_hash(_owner_path(root, name), digest, checks.check)
    env = request['environment']
    _owner_need(list(sys.version_info[:3]) == env['python_version']
                and platform.python_implementation() == env['implementation'], 'Interpreter version changed')
    pins['interpreter'] = _owner_hash(Path(sys.executable).resolve(strict=True), env['interpreter_sha256'], checks.check)
    for name in ('pyproject', 'uv_lock', 'external_supervisor'):
        ref = env[name]; pins[ref['path']] = _owner_hash(_owner_path(root, ref['path']), ref['sha256'], checks.check)
    for package, version in env['packages'].items():
        checks.check(); _owner_need(importlib.metadata.version(package) == version, 'Locked package version changed: ' + package)
    loaded = {}
    for name in ('protocol', 'manual_registry', 'pool_contract', 'reference_handoff'):
        ref = request[name]; loaded[name], raw = _owner_small(_owner_path(root, ref['path']), ref['sha256']); checks.check()
        pins[ref['path']] = dict(sha256=ref['sha256'], stat=_owner_stat(_owner_path(root, ref['path'])))
    handoff = loaded['reference_handoff']
    _owner_need(handoff.get('scope') == 'Root_prepared_narrow_existing_model_and_reference_handoff_not_runtime_grant'
                and handoff.get('execution_granted') is False and handoff.get('models') == request['models']
                and handoff.get('source') == request['source']
                and handoff.get('reference_artifacts') == request['comparison']['references']
                and handoff.get('mandatory_parity') == request['comparison']['required_checks']
                and handoff.get('manual_registry') == request['manual_registry']
                and handoff.get('pool_contract') == request['pool_contract']
                and handoff.get('protocol') == one_day_protocol(loaded['protocol']),
                'Request differs from exact narrow Root source/model/config/reference handoff')
    # metadata_pins is preparation provenance, including TMP paths. It is never
    # iterated, copied, treated as an input closure, or granted runtime access.
    source = request['source']; receipt_ref = source['prefix_acceptance']
    kernel = source['kernel_evidence']
    _owner_small(_owner_path(root, kernel['path']), kernel['sha256']); checks.check()
    pins[kernel['path']] = dict(sha256=kernel['sha256'], stat=_owner_stat(_owner_path(root, kernel['path'])))
    receipt, raw = _owner_small(_owner_path(root, receipt_ref['path']), receipt_ref['sha256'])
    _owner_need(receipt.get('source_prefix_accepted') is True and receipt.get('verdict') == 'ACCEPTED_source_prefix'
                and receipt.get('scope') == 'MAIN018_actual_fullsource_typed9_source_prefix_only', 'Exact accepted new source-prefix receipt required')
    rows = receipt.get('large_current_bindings')
    _owner_need(type(rows) is list and 2 <= len(rows) <= 16, 'Finite accepted source bindings required')
    _owner_need(sum(type(row) is dict and row.get('sha256') == OWNER_CSV_SHA for row in rows) == 1,
                'Distinct accepted canonical CSV identity missing from exact prefix metadata')
    ref = source['database']; path = _owner_path(root, ref['path']); current = _owner_stat(path)
    bound = [row for row in rows if type(row) is dict and row.get('path') == str(path)]
    _owner_need(len(bound) == 1 and bound[0].get('sha256') == ref['sha256']
                and all(bound[0].get('stat', {}).get(key) == value for key, value in current.items()),
                'Accepted source DB binding/stat freshness differs')
    pins[ref['path']] = _owner_hash(path, ref['sha256'], checks.check)
    pins[receipt_ref['path']] = dict(sha256=receipt_ref['sha256'], stat=_owner_stat(_owner_path(root, receipt_ref['path'])))
    for spec in request['models'].values():
        ref = spec['model']; pins[ref['path']] = _owner_hash(_owner_path(root, ref['path']), ref['sha256'], checks.check)
    return loaded, pins


def _owner_fixed_cores(root, checks):
    checks.check(); sys.path.insert(0, str(root))
    modules = {name: importlib.import_module('scripts.' + name) for name in OWNER_MODULES}
    scripts = sys.modules['scripts']
    _owner_need(list(scripts.__path__) == [str(root / 'scripts')], 'Project namespace import escaped exact root')
    for name, module in tuple(sys.modules.items()):
        if name.startswith('scripts.'):
            short = name.removeprefix('scripts.')
            _owner_need(short in OWNER_MODULES and Path(module.__file__).resolve() == root / 'scripts' / (short + '.py'),
                        'Unpinned project import outside fixed closure')
    duckdb = importlib.import_module('duckdb'); np = importlib.import_module('numpy')
    pd = importlib.import_module('pandas'); cb = importlib.import_module('catboost')
    checks.check()
    return SimpleNamespace(protocol=modules['protocol_manifest'], anchors=modules['anchor_pilot'],
        retrieval=modules['candidate_pilot'], compiler=modules['manual_features'], programs=modules['feature_programs'],
        schema=modules['heldout_source'], inference=modules['inference_data'], predictions=modules['heldout_predictions'],
        np=np, pd=pd, duckdb=duckdb, catboost=cb)


class _OwnerModel:
    """Only verifier metadata and prediction are exposed; attempts survive failure."""
    def __init__(self, native, progress):
        self._native, self._progress = native, progress

    def __getattr__(self, name):
        _owner_need(name in {'tree_count_', 'feature_names_', 'get_cat_feature_indices',
            'get_text_feature_indices', 'get_embedding_feature_indices', 'get_all_params'},
            'Native proxy exposes only frozen-state verification metadata')
        return getattr(self._native, name)

    def predict(self, *args, **kwargs):
        self._progress['native_prediction_attempts'] += 1
        result = self._native.predict(*args, **kwargs)
        self._progress['native_prediction_returns'] += 1
        return result


def _owner_execute(root, out, request, loaded, checks, progress):
    cores = checks.stage('fixed_native_and_project_imports', lambda: _owner_fixed_cores(root, checks))
    config = one_day_protocol(loaded['protocol'])
    pool = cores.programs.generate_pool(loaded['pool_contract'], loaded['manual_registry'])
    con = None; exported = set()
    def export(name, sql):
        _owner_need(name in OUTPUT_NAMES and name not in exported, 'One fixed export per output required')
        relative = request['output_directory'] + '/' + OUTPUT_NAMES[name]
        path = _owner_path(root, relative)
        # Reserve the new file exclusively; COPY may replace only this owner's
        # just-created empty reservation inside its fresh consumed directory.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); os.close(fd)
        exported.add(name); checks.check()
        con.execute("COPY (" + sql + ") TO '" + str(path).replace("'", "''") + "' (FORMAT PARQUET)")
        checks.check(); return relative
    def load_model(ref):
        _owner_need(ref in [spec['model'] for spec in request['models'].values()], 'Only exact B/W model refs supported')
        path = _owner_path(root, ref['path']); _owner_hash(path, ref['sha256'], checks.check)
        progress['model_load_attempts'] += 1
        model = cores.catboost.CatBoostClassifier(); model.load_model(str(path)); checks.check()
        return _OwnerModel(model, progress)
    try:
        source = request['source']['database']
        con = checks.stage('open_exact_new_source_read_only', lambda: cores.duckdb.connect(
            str(_owner_path(root, source['path'])), read_only=True,
            config={'threads': '2', 'memory_limit': '2GB', 'temp_directory': str(checks.spill),
                    'max_temp_directory_size': str(request['resources']['spill_bytes']) + 'B'}))
        progress['source_connection_opened_read_only'] = True
        schema = [tuple(row[:2]) for row in con.execute('DESCRIBE events').fetchall()]
        _owner_need(schema == OWNER_EVENTS, 'Fresh source must expose the exact accepted events typed9 schema')
        # No ingest_metadata assumption and no source writes: all core relations
        # are TEMP; DuckDB itself enforces read_only on the accepted DB.
        result = build_and_score(con, config=config, pool=pool, models=request['models'], cores=cores,
            load_model=load_model, export=export, check=checks.check, stage=checks.stage)
        _owner_need(exported == set(OUTPUT_NAMES), 'Incomplete required Q/C/B45/extra3/B/W outputs')
        return result
    finally:
        if con is not None:
            primary_active = sys.exc_info()[0] is not None
            try: con.close(); progress['source_connection_closed'] = True
            except BaseException as exc:
                progress['connection_close_error'] = type(exc).__name__ + ': ' + str(exc)[:512]
                if not primary_active: raise


def _owner_repin(root, request, pins, checks):
    result = {}
    for name, pin in pins.items():
        if name == 'interpreter': path = Path(sys.executable).resolve(strict=True)
        else: path = _owner_path(root, name)
        _owner_need(_owner_stat(path) == pin['stat'], 'Pinned file stat changed before finalization: ' + name)
        result[name] = _owner_hash(path, pin['sha256'], checks.check)
    return result


def _owner_reference_pins(root, request, checks):
    """Authenticate only explicit old leaves AFTER fresh source computation.

    No parsing/comparison occurs here. The independent verifier owns required
    all-keyed parity under the SAME cap; metadata provenance is not a leaf list.
    """
    refs = request['comparison']['references']; leaves = []
    for name in ('B_saved_scores', 'W_saved_scores', 'day_selected_union57'): leaves.append(refs[name])
    for name in ('all_selection_base45', 'all_selection_candidates', 'all_selection_queries'): leaves.extend(refs[name])
    return {ref['path']: _owner_hash(_owner_path(root, ref['path']), ref['sha256'], checks.check) for ref in leaves}


def run_slice(request_path, expected_request_sha, *, started_monotonic):
    """Future Root-issued one-shot entry; no callbacks or authority creation.

    request_path is project-relative. expected_request_sha must come from Root's
    exact original invocation, never be derived by this function. Returning a
    report proves neither parity nor full exit; the same original budget must
    still cover independent ALL-keyed comparison and accepted V6 exit receipts.
    """
    root = Path(__file__).resolve().parents[1]
    _owner_sha(expected_request_sha)
    request, raw = _owner_small(_owner_path(root, request_path), expected_request_sha)
    _owner_request(request)
    _owner_need(not request_path.startswith(request['output_directory'] + '/'), 'Request cannot be inside new output namespace')
    checks = _OwnerChecks(request['resources'], started_monotonic,
                          _owner_path(root, request['output_directory']) / 'spill')
    out = _owner_consume(root, request, raw, expected_request_sha)
    pins = {}; result = None
    progress = dict(model_load_attempts=0, native_prediction_attempts=0,
                    native_prediction_returns=0, source_connection_opened_read_only=False,
                    source_connection_closed=False)
    try:
        checks.check(); _owner_runtime(root, out); checks.spill.mkdir(mode=0o700)
        loaded, pins = checks.stage('authenticate_exact_inputs', lambda: _owner_authenticate(root, request, checks))
        result = _owner_execute(root, out, request, loaded, checks, progress)
        _owner_need(result['native_prediction_calls'] == progress['native_prediction_attempts']
                    == progress['native_prediction_returns'] <= 2,
                    'Core/owner native prediction counters differ')
        reference_pins = checks.stage('authenticate_only_explicit_old_reference_bytes',
            lambda: _owner_reference_pins(root, request, checks))
        outputs = {}
        _owner_need(set(result['outputs']) == set(OUTPUT_NAMES), 'Exact output set required')
        for name, relative in result['outputs'].items():
            _owner_need(relative == request['output_directory'] + '/' + OUTPUT_NAMES[name], 'Fixed project-relative output name required')
            path = _owner_path(root, relative)
            # Output digest is produced once inside the original guarded budget.
            digest = hashlib.sha256(); before = _owner_stat(path)
            with path.open('rb') as handle:
                while True:
                    checks.check(); chunk = handle.read(1024 * 1024)
                    if not chunk: break
                    digest.update(chunk)
            _owner_need(_owner_stat(path) == before, 'Output changed during pinning')
            outputs[name] = dict(path=relative, sha256=digest.hexdigest(), stat=before)
        final_pins = checks.stage('repin_source_model_code_environment', lambda: _owner_repin(root, request, pins, checks))
        for relative, pin in reference_pins.items():
            _owner_need(_owner_stat(_owner_path(root, relative)) == pin['stat'], 'Explicit reference changed before handoff')
        checks.check()
        report = dict(version=1, scope=OWNER_SCOPE, status='pending_independent_all_keyed_parity_and_full_exit_acceptance',
            execution_id=request['execution_id'], original_request_sha256=expected_request_sha,
            core=result, source_model_code_environment_pins=final_pins, output_pins=outputs,
            explicit_reference_pins=reference_pins, canonical_input_sha256_from_accepted_prefix=OWNER_CSV_SHA,
            resources=request['resources'], telemetry=checks.telemetry(), stages=checks.stages,
            comparison=request['comparison'], independent_output_acceptance=None, external_full_exit_acceptance=None,
            canonical_csv_rehashed=False, source_database_opened_read_only=True,
            actual_native_calls=result['native_prediction_calls'], progress=progress, fit_attempt_count=0, metric_looks=0,
            query_targets_opened=False, source_acceptance_issued=False, execution_authority_issued=False,
            supervision='external_accepted_V6_required_same_stage_cap_including_comparison_and_final_tails',
            process_rss_is_peak_not_job_hard_limit=True, external_exit_tail_measured=False)
        # The returned object is JSON-safe too; outer reporters must not fail
        # after successful work on the production-shaped query build record.
        report = _owner_json(_owner_encode(report))
        _owner_write(out / 'report.json', report)
        checks.check(); return report
    except BaseException as exc:
        # Failure reporting/close tails consume original lifetime, never restart
        # a budget. External V6 retains authoritative failure/reap accounting.
        failure = dict(version=1, scope=OWNER_SCOPE, status='failed_consumed_no_retry',
            execution_id=request['execution_id'], original_request_sha256=expected_request_sha,
            error_type=type(exc).__name__, error=str(exc)[:2048], stages=checks.stages,
            telemetry=checks.snapshot(), resources=request['resources'], progress=progress,
            independent_output_acceptance=None, external_full_exit_acceptance=None,
            execution_authority_issued=False, source_acceptance_issued=False)
        try: _owner_write(out / 'failure.json', failure)
        except BaseException as reporting_error:
            exc.failure_report_error = type(reporting_error).__name__ + ': ' + str(reporting_error)[:512]
        raise


def owner_main():
    parser = argparse.ArgumentParser(description='DRAFT fixed existing018 development owner; Root/V6 handoff required')
    parser.add_argument('--request', required=True)
    parser.add_argument('--expected-request-sha', required=True)
    parser.add_argument('--started-monotonic', required=True, type=float)
    args = parser.parse_args()
    run_slice(args.request, args.expected_request_sha, started_monotonic=args.started_monotonic)


if __name__ == '__main__':
    owner_main()
