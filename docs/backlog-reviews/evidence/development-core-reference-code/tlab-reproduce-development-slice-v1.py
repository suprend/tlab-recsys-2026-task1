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
