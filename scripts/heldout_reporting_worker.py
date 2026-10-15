"""Fixed reserved source/prediction/reporting adapter; no standalone authority."""
import time
ENTRY_MONOTONIC=time.monotonic()
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
PRODUCTION_ROLES={'source','predictions','targets_evaluation'}
SOURCE_KEYS={'version','scope','run_id','decision_lock','choice','source','days','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'}
PREDICTION_KEYS={'version','scope','run_id','decision_lock','choice','source_acceptance','source_manifest','created_at','days','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'}


def bootstrap(context_path,issuer_sha):
    """Bounded stdlib-only byte checks precede project/native imports."""
    def raw(path):
        with Path(path).open('rb') as stream:data=stream.read(8*2**20+1)
        if len(data)>8*2**20:raise ValueError('Bounded original worker bootstrap exceeded')
        return data
    def path(name):
        if type(name) is not str or not name or name.startswith('/') or '\\' in name or any(p in {'','.','..'} for p in name.split('/')):raise ValueError('Normalized bootstrap ref required')
        result=(ROOT/name).resolve();result.relative_to(ROOT.resolve());return result
    data=raw(context_path)
    if hashlib.sha256(data).hexdigest()!=issuer_sha:raise ValueError('Original issuer SHA differs before import')
    context=json.loads(data);role=context.get('role')
    if role not in PRODUCTION_ROLES:raise ValueError('Fixed production adapter role required')
    request=context['request'];data=raw(path(request['path']))
    if hashlib.sha256(data).hexdigest()!=request['sha256']:raise ValueError('Original request differs before import')
    body=json.loads(data);pins=body['code_fingerprints']
    required={'scripts/heldout_reporting_worker.py','scripts/heldout_worker_context.py','scripts/heldout_execution.py','scripts/heldout_contract.py','uv.lock','pyproject.toml'}
    if not required<=set(pins):raise ValueError('Mandatory bootstrap pins omitted')
    for name,digest in pins.items():
        if not name.endswith(('.py','.toml','.lock','.json')):raise ValueError('Unexpected bootstrap code path')
        if hashlib.sha256(raw(path(name))).hexdigest()!=digest:raise ValueError('Original project code changed before import')
    for folder in ['scripts','tests','tests/oracles']:
        initializer=folder+'/__init__.py'
        if path(initializer).exists() and initializer not in pins:raise ValueError('Unpinned namespace initializer before project import')
    if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
    return role


def utc_now():return datetime.now(timezone.utc).replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')
def sql_literal(value):return "'"+str(value).replace("'","''")+"'"


@contextmanager
def connection(run,*,source=None):
    import duckdb
    from scripts import heldout_execution as x
    run.budget.guard();prefix=Path(run.root)/Path(run.context['output_path']).parent
    spill=prefix/'spill';spill.mkdir(exist_ok=False)
    con=None;primary=None
    try:
        con=duckdb.connect(':memory:',config={'threads':2,'memory_limit':'2GB','max_temp_directory_size':'2GiB','temp_directory':str(spill)})
        run.budget.watch(con)
        if source is not None:
            x.ref(source);con.execute('ATTACH '+sql_literal(run.root/source['path'])+' AS reserved_input (READ_ONLY)')
            con.execute('CREATE TEMP VIEW heldout_raw_events AS SELECT event_time,event_type,product_id,user_id,category_id FROM reserved_input.main.events')
        run.budget.guard();yield con
    except BaseException as error:primary=error;raise
    finally:
        try:
            if con is not None:con.close()
            run.budget.guard()
        except BaseException as error:
            if primary is not None:primary.add_note('Connection cleanup: '+type(error).__name__)
            else:raise


def original_identity(run):
    from scripts import heldout_execution as x
    name=str(Path(run.context['output_path']).parent.parent/'proposal.json')
    body,sha=x.read(run.root/name);x.need(run.pins[name]==sha,'Original proposal changed')
    return deepcopy(body['identity'])


def source_snapshot(run,lock):
    from scripts import heldout_execution as x
    from scripts import heldout_contract as h
    manifest=run.input_json('source_manifest');seal=run.input_json('source_acceptance')
    h.keys(manifest,SOURCE_KEYS,'Issued source manifest');identity=original_identity(run)
    h.need(type(manifest['version']) is int and manifest['version']==1 and manifest['scope']=='unaccepted_reserved_source'
        and manifest['run_id']==run.context['run_id'],'Source producer identity differs')
    h.need(manifest['decision_lock']==run.context['inputs']['lock'] and manifest['choice']==run.context['inputs']['choice']
        and manifest['source']==identity['source_inputs']['source'],'Source producer original input refs differ')
    h.need(manifest['labels_loaded'] is False and type(manifest['fit_attempt_count']) is int and manifest['fit_attempt_count']==0
        and type(manifest['native_prediction_count']) is int and manifest['native_prediction_count']==0,'Source producer opened forbidden capability')
    h.need(h.canonical(manifest['days'])==h.canonical(seal['days']),'Source seal exact daily domain differs')
    prefix=str(Path(run.context['output_path']).parent.parent/'source');expected=set(x.expected_paths(str(Path(prefix).parent),'source',lock['choice']))-{prefix+'/source-manifest.json'}
    refs={}
    h.need(type(manifest['days']) is list and len(manifest['days'])==7,'All seven accepted source dates required')
    for index,day in enumerate(manifest['days']):
        h.keys(day,{'anchor','queries','candidates','base_features','extra_features','query_count','candidate_count','mature_query_count'},'Accepted source day')
        h.need(day['anchor']==h.DAYS[index],'Canonical source calendar required')
        for kind,suffix in [('queries','queries'),('candidates','candidates'),('base_features','base-features'),('extra_features','extra-features')]:
            ref=day[kind]
            if kind=='extra_features' and lock['choice']=='B':h.need(ref is None,'B-only unexpected extras');continue
            x.ref(ref);h.need(ref['path']==prefix+f'/day-{25+index}/'+suffix+'.parquet','Source daily path outside fixed role')
            h.need(seal['fingerprints'].get(ref['path'])==ref['sha256'],'Source output outside external accepted closure');refs[ref['path']]=ref['sha256']
    h.need(set(refs)==expected and h.canonical(refs)==h.canonical(manifest['outputs']),'Exact source output map differs')
    run.retain_pins(refs)
    return manifest,dict(acceptance=deepcopy(run.context['inputs']['source_acceptance']),days=deepcopy(manifest['days']))


def write_json(run,name,body):
    from scripts import heldout_execution as x
    run.budget.guard();saved=x.exclusive(run.root/name,body);run.budget.guard()
    return dict(path=name,sha256=saved['sha256'])


def export_table(run,con,name,query):
    from scripts import heldout_execution as x
    path=run.root/name;path.parent.mkdir(parents=True,exist_ok=True);x.need(not path.exists(),'Export path already consumed')
    run.budget.guard();con.execute('COPY ('+query+') TO '+sql_literal(path)+' (FORMAT PARQUET, COMPRESSION ZSTD)');run.budget.guard()
    return dict(path=name,sha256=x.sha(path,run.budget.guard))


def source_role(run,environment):
    from scripts import heldout_contract as h
    from scripts import heldout_source as source
    from scripts import feature_programs as programs
    lock=run.input_json('lock');choice=run.input_json('choice');h.validate_lock(lock,authenticated_choice=choice)
    pool=programs.generate_pool(run.input_json('pool'),run.input_json('registry'));days=[];outputs={}
    with connection(run,source=run.context['inputs']['source']) as con:
        for index,anchor in enumerate(h.DAYS):
            run.budget.guard();meta=source.build_day(con,anchor,pool,lock,authenticated_choice=choice,check=run.budget.guard)
            prefix=str(Path(run.context['output_path']).parent/f'day-{25+index}')
            refs={}
            for kind,view,suffix in [('queries','pilot_queries','queries'),('candidates','pilot_candidates','candidates'),('base_features','heldout_base_features','base-features')]:
                query='SELECT * FROM '+view+' ORDER BY query_id' if kind=='queries' else 'SELECT * FROM '+view+' ORDER BY query_id,product_id'
                refs[kind]=export_table(run,con,prefix+'/'+suffix+'.parquet',query)
            refs['extra_features']=export_table(run,con,prefix+'/extra-features.parquet','SELECT * FROM heldout_extra_features ORDER BY query_id,product_id') if lock['choice']!='B' else None
            row=dict(anchor=anchor,**refs,**{key:meta[key] for key in ['query_count','candidate_count','mature_query_count']});days.append(row)
            for ref in refs.values():
                if ref is not None:outputs[ref['path']]=ref['sha256']
    body=dict(version=1,scope='unaccepted_reserved_source',run_id=run.context['run_id'],decision_lock=run.context['inputs']['lock'],choice=run.context['inputs']['choice'],
        source=run.context['inputs']['source'],days=days,outputs=deepcopy(outputs),labels_loaded=False,fit_attempt_count=0,native_prediction_count=0,environment=environment)
    ref=write_json(run,str(Path(run.context['output_path']).parent/'source-manifest.json'),body);outputs[ref['path']]=ref['sha256']
    return outputs,ref,0,False


def save_scores(run,name,scores):
    import numpy as np
    from scripts import heldout_execution as x
    x.need(all(type(q[0]) is str and len(q[0])<=64 for q in scores.queries),'No silent Unicode query-id truncation')
    arrays=dict(query_ids=np.asarray([q[0] for q in scores.queries],dtype='U64'),user_ids=np.asarray([q[1] for q in scores.queries],dtype='int64'),
        anchors=np.asarray([np.datetime64(q[2],'us').astype('int64') for q in scores.queries],dtype='int64'),calendar_maturity=scores.calendar_maturity,
        group=scores.group,items=scores.items,scores=scores.scores)
    path=run.root/name;path.parent.mkdir(parents=True,exist_ok=True);x.need(not path.exists(),'Prediction path already consumed')
    run.budget.guard()
    with path.open('xb') as stream:np.savez(stream,**arrays)
    run.budget.guard();return dict(path=name,sha256=x.sha(path,run.budget.guard))


def predictions_role(run,environment):
    from scripts import heldout_contract as h
    from scripts import heldout_predictions as p
    from catboost import CatBoostClassifier
    lock=run.input_json('lock');choice=run.input_json('choice');h.validate_lock(lock,authenticated_choice=choice)
    manifest,snapshot=source_snapshot(run,lock);days=[];outputs={};models={};calls=0
    class ObservedModel:
        def __init__(self,model):self.model=model
        def __getattr__(self,name):return getattr(self.model,name)
        def predict(self,*args,**kwargs):
            nonlocal calls
            calls+=1;run.budget.guard();result=self.model.predict(*args,**kwargs);run.budget.guard();return result
    def load_model(reference):
        from scripts import heldout_execution as x
        x.ref(reference);x.need(run.pins.get(reference['path'])==reference['sha256'],'Model outside original accepted closure')
        run.budget.guard()
        if reference['path'] not in models:
            model=CatBoostClassifier();model.load_model(str(run.root/reference['path']));models[reference['path']]=ObservedModel(model)
        return models[reference['path']]
    try:
        for index,anchor in enumerate(h.DAYS):
            scored=p.score_day(anchor,lock,authenticated_choice=choice,authenticated_source=snapshot,load_model=load_model,check=run.budget.guard)
            descriptors={}
            for role in ['B','W']:
                if role=='W' and lock['choice']=='B':descriptors['W']=deepcopy(descriptors['B']);continue
                scores=scored['predictions'][role];ref=save_scores(run,str(Path(run.context['output_path']).parent/f'day-{25+index}'/(role+'.npz')),scores)
                outputs[ref['path']]=ref['sha256'];descriptors[role]=dict(artifact=ref,model=scores.model,rows=len(scores.items),queries=len(scores.queries),scoring_prefix=300,feature_names=scores.feature_names)
            days.append(dict(**deepcopy(manifest['days'][index]),predictions=descriptors));del scored
    finally:models.clear()
    expected=sum(day['candidate_count']>0 for day in days)*(1 if lock['choice']=='B' else 2);h.need(calls==expected,'Actual native prediction count differs')
    body=dict(version=1,scope='unaccepted_reserved_predictions',run_id=run.context['run_id'],decision_lock=run.context['inputs']['lock'],choice=run.context['inputs']['choice'],
        source_acceptance=run.context['inputs']['source_acceptance'],source_manifest=run.context['inputs']['source_manifest'],created_at=utc_now(),days=days,outputs=deepcopy(outputs),
        labels_loaded=False,fit_attempt_count=0,native_prediction_count=calls,environment=environment)
    ref=write_json(run,str(Path(run.context['output_path']).parent/'prediction-manifest.json'),body);outputs[ref['path']]=ref['sha256'];return outputs,ref,calls,False


def read_scores(run,descriptor,day):
    """Exact seven-array physical transport, before any target relation."""
    import zipfile
    import numpy as np
    from scripts import heldout_execution as x
    from scripts import heldout_contract as h
    h.keys(descriptor,{'artifact','model','rows','queries','scoring_prefix','feature_names'},'Saved descriptor')
    ref=descriptor['artifact'];x.ref(ref);x.need(run.pins.get(ref['path'])==ref['sha256'],'Saved score outside retained prediction authority')
    qn,n=day['query_count'],day['candidate_count'];x.need(descriptor['queries']==qn and descriptor['rows']==n,'Declared score transport sizes differ')
    types=dict(query_ids=np.dtype('U64'),user_ids=np.dtype('int64'),anchors=np.dtype('int64'),calendar_maturity=np.dtype('bool'),group=np.dtype('int32'),items=np.dtype('int64'),scores=np.dtype('float64'))
    counts={name:qn if name in {'query_ids','user_ids','anchors','calendar_maturity'} else n for name in types}
    x.need(type(qn) is int and 0<=qn<=2000 and type(n) is int and 0<=n<=440000,'Known bounded saved shape required')
    path=run.root/ref['path'];run.budget.guard()
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist();x.need(len(entries)==7 and {entry.filename for entry in entries}=={name+'.npy' for name in types},'Exact unique NPZ members required')
        for entry in entries:
            run.budget.guard();name=entry.filename[:-4];dtype=types[name];count=counts[name]
            x.need(entry.file_size<=count*dtype.itemsize+4108,'Bounded uncompressed NPZ member required')
            with archive.open(entry) as stream:
                version=np.lib.format.read_magic(stream)
                x.need(version in {(1,0),(2,0)},'Unsupported NPY header version')
                reader=np.lib.format.read_array_header_1_0 if version==(1,0) else np.lib.format.read_array_header_2_0
                shape,fortran,actual=reader(stream,max_header_size=4096)
                x.need(shape==(count,) and fortran is False and actual==dtype and not actual.hasobject,'Exact simple NPY dtype/shape required before allocation')
                x.need(entry.file_size==stream.tell()+count*dtype.itemsize,'NPY header/payload byte cover differs')
    with np.load(path,allow_pickle=False) as archive:arrays={name:archive[name] for name in types}
    for name,value in arrays.items():x.need(type(value) is np.ndarray and value.dtype==types[name] and value.shape==(counts[name],),'Decoded saved array differs')
    queries=[(str(qid),int(user),datetime(1970,1,1)+timedelta(microseconds=int(when))) for qid,user,when in zip(arrays['query_ids'],arrays['user_ids'],arrays['anchors'])]
    x.need(all(qid and when==h.utc(day['anchor']).replace(tzinfo=None) for qid,user,when in queries),'Saved query anchor/key differs')
    x.need([q[0] for q in queries]==sorted({q[0] for q in queries}) and len({q[1] for q in queries})==qn,'Saved Q identity/order differs')
    x.need(arrays['calendar_maturity'].all() and np.isfinite(arrays['scores']).all(),'Saved maturity/raw values invalid')
    group,items=arrays['group'],arrays['items'];x.need(((group>=0)&(group<qn)).all() and ((group[1:]>group[:-1])|((group[1:]==group[:-1])&(items[1:]>items[:-1]))).all(),'Saved C key order/domain differs')
    x.need((np.bincount(group,minlength=qn)<=220).all(),'Saved per-query candidate cap')
    run.budget.guard();return dict(queries=queries,calendar_maturity=arrays['calendar_maturity'],group=group,items=items,scores=arrays['scores'])


def population(run,con,day):
    import numpy as np
    from scripts import heldout_execution as x
    from scripts import heldout_contract as h
    run.budget.guard();con.execute('CREATE OR REPLACE TEMP VIEW _worker_q AS SELECT * FROM read_parquet('+sql_literal(run.root/day['queries']['path'])+')')
    con.execute('CREATE OR REPLACE TEMP VIEW _worker_c AS SELECT * FROM read_parquet('+sql_literal(run.root/day['candidates']['path'])+')')
    types=dict((r[0],r[1]) for r in con.execute('DESCRIBE _worker_q').fetchall());x.need(types==dict(query_id='VARCHAR',user_id='BIGINT',anchor='TIMESTAMP',eligibility_events='BIGINT',history_events_7d='BIGINT',history_distinct_items_7d='BIGINT',history_active_days_7d='BIGINT',last_history_time='TIMESTAMP',history_coverage_7d='DOUBLE',label_is_mature='BOOLEAN'),'Exact source Q transport schema')
    rows=con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM _worker_q ORDER BY query_id').fetchall()
    x.need(len(rows)==day['query_count'] and all(type(qid) is str and qid and type(user) is int and -2**63<=user<2**63 and when==h.utc(day['anchor']).replace(tzinfo=None) and mature is True for qid,user,when,mature in rows),'Complete source Q identity/calendar')
    triples=[tuple(r[:3]) for r in rows];x.need([q[0] for q in triples]==sorted({q[0] for q in triples}) and len({q[1] for q in triples})==len(rows),'Unique source user-day/query keys')
    qn,n=len(rows),day['candidate_count'];con.execute('CREATE OR REPLACE TEMP VIEW _worker_qgroup AS SELECT query_id,row_number()OVER(ORDER BY query_id)-1 g FROM _worker_q')
    x.need(con.execute('SELECT count(*) FROM _worker_c').fetchone()[0]==n,'All C row count differs')
    con.execute('SELECT q.g,c.product_id FROM _worker_c c LEFT JOIN _worker_qgroup q USING(query_id) ORDER BY q.g,c.product_id')
    groups=np.empty(n,dtype=np.int32);items=np.empty(n,dtype=np.int64);offset=0
    while True:
        run.budget.guard();chunk=con.fetchmany(65536)
        if not chunk:break
        x.need(offset+len(chunk)<=n,'C transport row overrun')
        for g,item in chunk:
            x.need(type(g) is int and 0<=g<qn and type(item) is int and -2**63<=item<2**63,'Exact source C integer/group transport')
            groups[offset]=g;items[offset]=item;offset+=1
    x.need(offset==n and ((groups[1:]>groups[:-1])|((groups[1:]==groups[:-1])&(items[1:]>items[:-1]))).all(),'Exact source C ordered multiset')
    x.need((np.bincount(groups,minlength=qn)<=220).all(),'Source per-Q candidate cap')
    run.budget.guard();return dict(queries=triples,calendar_maturity=np.ones(qn,dtype=np.bool_),candidate_group=groups,candidate_items=items)


def targets_role(run,environment):
    import numpy as np
    from scripts import heldout_execution as x
    from scripts import heldout_contract as h
    from scripts import heldout_evaluation as evaluator
    lock=run.input_json('lock');choice=run.input_json('choice');h.validate_lock(lock,authenticated_choice=choice)
    manifest,source=source_snapshot(run,lock);inventory=run.input_json('prediction_inventory');policy=run.input_json('target_policy')
    prediction_seal=run.input_json('prediction_acceptance');target_ref=run.context['authorities']['target_execution'];target_seal,target_sha=x.read(run.root/target_ref['path']);x.need(target_sha==target_ref['sha256'],'Parsed original target authority changed')
    authenticated=dict(reference=run.context['inputs']['prediction_acceptance'],inventory_sha256=h.digest(inventory),decision_lock_sha256=h.digest(lock))
    h.validate_prediction_inventory(inventory,lock,authenticated_source=source)
    h.keys(policy,{'prediction_acceptance','prediction_inventory_sha256','decision_lock_sha256','periods','no_adaptation','earliest_opened_at'},'Prospective target policy')
    h.need(policy['prediction_acceptance']==authenticated['reference'] and policy['prediction_inventory_sha256']==authenticated['inventory_sha256'] and policy['decision_lock_sha256']==authenticated['decision_lock_sha256'],'Target policy actual authority binding')
    h.need(policy['periods']==['confirmation25_reporting_only','final26_31_frozen'] and policy['no_adaptation'] is True and policy['earliest_opened_at']==prediction_seal['sealed_at'],'Target prospective policy differs')
    score_pins={};descriptors={}
    for day in inventory['days']:
        for role,descriptor in day['predictions'].items():
            ref=descriptor['artifact'];h.ref(ref);h.need(prediction_seal['fingerprints'].get(ref['path'])==ref['sha256'],'Saved prediction outside accepted closure')
            expected=str(Path(run.context['output_path']).parent.parent/'predictions'/('day-'+day['anchor'][8:10])/(('B' if role=='W' and lock['choice']=='B' else role)+'.npz'))
            h.need(ref['path']==expected,'Saved prediction outside fixed original path');score_pins[ref['path']]=ref['sha256'];descriptors[ref['path']]=(descriptor,day)
    run.retain_pins(score_pins);saved={name:read_scores(run,descriptor,day) for name,(descriptor,day) in descriptors.items()};pop={}
    with connection(run) as con:
        # All seven actual source/score domains precede target admission and raw IO.
        for day in source['days']:
            pop[day['anchor']]=population(run,con,day)
            entry=next(row for row in inventory['days'] if row['anchor']==day['anchor'])
            for descriptor in entry['predictions'].values():
                body=saved[descriptor['artifact']['path']];domain=pop[day['anchor']]
                h.need(body['queries']==domain['queries'] and np.array_equal(body['calendar_maturity'],domain['calendar_maturity']) and np.array_equal(body['group'],domain['candidate_group']) and np.array_equal(body['items'],domain['candidate_items']),'All-date saved/source exact population differs before Y')
        latest=max(h.utc(prediction_seal['sealed_at']),h.utc(target_seal['sealed_at']))
        while h.utc(utc_now())<=latest:run.budget.guard();time.sleep(.02)
        admission_at=utc_now();admission_mono=time.monotonic();intent=dict(version=1,scope='report_only_reserved_fullY',prediction_acceptance=authenticated['reference'],prediction_inventory_sha256=authenticated['inventory_sha256'],decision_lock_sha256=authenticated['decision_lock_sha256'],opened_at=admission_at,periods=policy['periods'],no_adaptation=True)
        h.validate_target_intent(intent,lock,inventory,authenticated_prediction_acceptance=authenticated)
        identity=original_identity(run);raw=identity['source_inputs']['source'];h.need(run.pins.get(raw['path'])==raw['sha256'],'Raw target source outside original closure')
        con.execute('ATTACH '+sql_literal(run.root/raw['path'])+' AS reserved_input (READ_ONLY)');con.execute('CREATE TEMP VIEW heldout_raw_events AS SELECT event_time,event_type,product_id,user_id,category_id FROM reserved_input.main.events')
        full_open={}
        class SQLAdmission:
            def __getattr__(self,name):return getattr(con,name)
            def execute(self,sql,*args,**kwargs):
                if 'CREATE TEMP TABLE heldout_full_targets AS SELECT DISTINCT' in sql:
                    h.need(not full_open,'Original fullY SQL cannot repeat');run.budget.guard();full_open.update(at=utc_now(),monotonic=time.monotonic())
                return con.execute(sql,*args,**kwargs)
        result=evaluator.evaluate_windows(SQLAdmission(),lock,inventory,intent,authenticated_choice=choice,authenticated_source=source,authenticated_prediction_acceptance=authenticated,
            load_day_population=lambda day:deepcopy(pop[day['anchor']]),load_saved_scores=lambda descriptor:{key:saved[descriptor['artifact']['path']][key].copy() for key in ['group','items','scores']},check=run.budget.guard)
        h.need(set(full_open)=={'at','monotonic'} and h.utc(full_open['at'])>=h.utc(admission_at) and full_open['monotonic']>=admission_mono,'Actual target SQL clock missing/out of order')
        prefix=str(Path(run.context['output_path']).parent);targets=export_table(run,con,prefix+'/full-targets.parquet','SELECT query_id,product_id FROM heldout_full_targets ORDER BY query_id,product_id')
    ranking_name=prefix+'/private-rankings.jsonl';ranking_path=run.root/ranking_name
    with ranking_path.open('x') as stream:
        for period in ['confirmation25_reporting_only','final26_31_frozen']:
            for role in ['B','W']:
                for row in result['private_rankings'][period][role]:
                    run.budget.guard();body=dict(period=period,role=role,query_id=row.query_id,user_id=row.user_id,ranked_items=list(row.ranked_items),targets=sorted(row.targets),mature=row.mature)
                    stream.write(x.canonical(body)+'\n')
    ranking=dict(path=ranking_name,sha256=x.sha(ranking_path,run.budget.guard));outputs={ref['path']:ref['sha256'] for ref in [targets,ranking]}
    body=dict(version=1,scope='unaccepted_reserved_fullY_reporting',run_id=run.context['run_id'],decision_lock=run.context['inputs']['lock'],choice=run.context['inputs']['choice'],source_acceptance=run.context['inputs']['source_acceptance'],source_manifest=run.context['inputs']['source_manifest'],prediction_acceptance=run.context['inputs']['prediction_acceptance'],prediction_inventory=run.context['inputs']['prediction_inventory'],target_execution=target_ref,target_policy=run.context['inputs']['target_policy'],actual_target_intent=intent,target_stage_opened_at=admission_at,target_stage_started_monotonic=admission_mono,fullY_started_at=full_open['at'],fullY_started_monotonic=full_open['monotonic'],periods=result['periods'],private_outputs=dict(targets=targets,rankings=ranking),outputs=deepcopy(outputs),labels_loaded=True,fit_attempt_count=0,native_prediction_count=0,environment=environment)
    ref=write_json(run,prefix+'/evaluation.json',body);outputs[ref['path']]=ref['sha256'];return outputs,ref,0,True


def run_worker(context_path,issuer_sha,*,started=ENTRY_MONOTONIC):
    role=bootstrap(context_path,issuer_sha)
    from scripts import heldout_worker_context as common
    execution=common.begin_role(context_path,issuer_sha,role,started)
    try:
        execution.verify_pins();environment=execution.environment()
        if role=='source':outputs,evidence,calls,labels=source_role(execution,environment)
        elif role=='predictions':outputs,evidence,calls,labels=predictions_role(execution,environment)
        else:outputs,evidence,calls,labels=targets_role(execution,environment)
        return execution.finish(outputs,evidence,native_prediction_count=calls,labels_loaded=labels)
    except BaseException as error:execution.fail(error);raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--context',required=True);parser.add_argument('--issued-context-sha256',required=True);args=parser.parse_args()
    run_worker(args.context,args.issued_context_sha256)


if __name__=='__main__':main()
