"""Independent daily matrix/native replay core; caller owns authenticated bytes.

No production inference loader/prediction core, file/model opener, fit or Y API.
Private caller relations are separately accepted Q, C, B45 and chosen0/3 extras.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import math
import re

import numpy as np

META={'query_id','user_id','product_id','anchor','last_user_event_time','candidate_category_id'}
DERIVED=['retrieval_last_event_age_seconds','retrieval_last_event_missing']


def need(value,message):
    if not value:raise ValueError(message)


def keys(value,names,what):need(type(value) is dict and set(value)==set(names),what+' exact keys required')
def identifier(name):need(type(name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) is not None,'Safe feature identifier required')
def ref(value):
    keys(value,{'path','sha256'},'Oracle artifact ref')
    need(type(value['path']) is str and value['path'] and not value['path'].startswith('/') and
        all(part not in {'','.','..'} for part in value['path'].split('/')) and '\\' not in value['path'],'Project-relative original reference required')
    need(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None,'Oracle SHA256 required')


def native_equal(actual,expected,path=()):
    if type(expected) is dict:
        keys(actual,expected,'Native parameter')
        for name,value in expected.items():native_equal(actual[name],value,(*path,name))
    elif type(expected) is list:
        need(type(actual) is list and len(actual)==len(expected),'Native parameter list differs')
        for first,second in zip(actual,expected):native_equal(first,second,path)
    elif type(expected) is float:
        tolerance=max(1e-12,abs(expected)*1e-8) if path==('learning_rate',) else 1e-12
        need(type(actual) is float and math.isfinite(actual) and math.isfinite(expected) and abs(actual-expected)<=tolerance,'Native parameter float differs')
    else:need(type(actual) is type(expected) and actual==expected,'Native parameter value/type differs')


def model_spec(spec,width):
    keys(spec,{'model','feature_names','trained_iterations','scoring_prefix','population','effective_parameters'},'Frozen model spec');ref(spec['model'])
    for name,value in [('trained_iterations',300),('scoring_prefix',300),('population',26000)]:need(type(spec[name]) is int and spec[name]==value,'Frozen300/300/26000 model required')
    names=spec['feature_names'];need(type(names) is list and len(names)==width and len(set(names))==width,'Exact numeric feature width required')
    for name in names:identifier(name)
    need(not set(names)&META and names[39:41]==DERIVED,'Keys excluded and derived retrieval projection required')
    params=spec['effective_parameters'];need(type(params) is dict,'Authenticated complete native parameters required')
    fixed=dict(loss_function='Logloss',iterations=300,depth=6,l2_leaf_reg=30,random_seed=2026,task_type='CPU',
        boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,
        leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False,
        border_count=254,nan_mode='Min',rsm=1)
    for key,value in fixed.items():native_equal(params.get(key),value,(key,))
    rate=params.get('learning_rate');need(type(rate) is float and math.isfinite(rate) and abs(rate-.05)<1e-8,'Frozen loaded learning rate required')


def native_model(model,spec):
    need(type(model.tree_count_) is int and model.tree_count_==300 and model.feature_names_==spec['feature_names'],'Native tree/feature state differs')
    need(model.get_cat_feature_indices()==[] and model.get_text_feature_indices()==[] and model.get_embedding_feature_indices()==[],'Numeric native model only')
    native_equal(model.get_all_params(),spec['effective_parameters'])


def check_staged(con,queries):
    actual=con.execute('SELECT query_id,user_id,anchor,oracle_group FROM heldout_prediction_oracle_q ORDER BY oracle_group').fetchall()
    need(actual==[(*q,index) for index,q in enumerate(queries)],'Independent staged Q binding differs')


def schema(con,name):return {row[0]:row[1] for row in con.execute('DESCRIBE '+name).fetchall()}
def numeric(kind):return kind in {'BOOLEAN','TINYINT','SMALLINT','INTEGER','BIGINT','HUGEINT','UTINYINT','USMALLINT','UINTEGER','UBIGINT','FLOAT','DOUBLE'} or kind.startswith('DECIMAL(')


def independent_matrix(con,anchor,row,names,check):
    check();need(con.execute("SELECT current_setting('threads')").fetchone()[0]==2,'Two-thread oracle matrix connection required')
    qt=schema(con,'heldout_prediction_queries');bt=schema(con,'heldout_prediction_base_features');ct=schema(con,'heldout_prediction_candidates')
    need(all(qt.get(k)==v for k,v in dict(query_id='VARCHAR',user_id='BIGINT',anchor='TIMESTAMP',label_is_mature='BOOLEAN').items()),'Typed independent Q schema required')
    need(all(bt.get(k)==v for k,v in dict(query_id='VARCHAR',user_id='BIGINT',product_id='BIGINT',anchor='TIMESTAMP',last_user_event_time='TIMESTAMP',candidate_category_id='BIGINT').items()),'Typed independent B metadata required')
    need(ct.get('query_id')=='VARCHAR' and ct.get('product_id')=='BIGINT','Typed independent C keys required')
    need(len(bt)==45 and [name for name in bt if name not in META]==names[:39],'Exact B45 column order/projection required')
    need(all(numeric(bt[name]) for name in names[:39]),'Physical B feature types must be numeric')
    qrows=con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM heldout_prediction_queries ORDER BY query_id').fetchall()
    need(len(qrows)==row['query_count'],'Complete source Q count differs')
    queries=[];maturity=[];qids=set();users=set();when=datetime.fromisoformat(anchor[:-1])
    for qid,user,time,mature in qrows:
        need(type(qid) is str and qid and qid not in qids and type(user) is int and -2**63<=user<2**63 and user not in users,'Unique exact Q identity required')
        need(type(time) is datetime and time==when and mature is True,'Exact Q anchor/calendar required')
        qids.add(qid);users.add(user);queries.append((qid,user,time));maturity.append(mature)
    # Explicit columns exclude any source-provided _group helper.
    con.execute('CREATE TEMP TABLE heldout_prediction_oracle_q AS SELECT query_id,user_id,anchor,row_number()OVER(ORDER BY query_id)-1 oracle_group FROM heldout_prediction_queries')
    n,unique,invalid=con.execute("""SELECT count(*),count(DISTINCT(query_id,product_id)),count(*)FILTER(WHERE query_id IS NULL OR product_id IS NULL)
        FROM heldout_prediction_candidates""").fetchone()
    need(n==row['candidate_count'] and n==unique and not invalid,'Exact candidate key count/uniqueness required')
    need(con.execute('SELECT coalesce(max(n),0) FROM(SELECT count(*) n FROM heldout_prediction_candidates GROUP BY query_id)').fetchone()[0]<=220,'Candidate per-Q cap')
    orphan=con.execute('SELECT count(*) FROM heldout_prediction_candidates c LEFT JOIN heldout_prediction_oracle_q q USING(query_id) WHERE q.query_id IS NULL').fetchone()[0]
    need(not orphan,'Candidate outside complete Q')
    for table in ['heldout_prediction_base_features']+(['heldout_prediction_extra_features'] if len(names)==44 else []):
        if table.endswith('extra_features'):
            extra=schema(con,table);need(set(extra)=={'query_id','product_id',*names[41:]} and extra['query_id']=='VARCHAR' and extra['product_id']=='BIGINT' and all(numeric(extra[name]) for name in names[41:]),'Exact chosen3 extra schema required')
        difference=con.execute('SELECT count(*) FROM((SELECT query_id,product_id FROM '+table+' EXCEPT ALL SELECT query_id,product_id FROM heldout_prediction_candidates) UNION ALL(SELECT query_id,product_id FROM heldout_prediction_candidates EXCEPT ALL SELECT query_id,product_id FROM '+table+'))').fetchone()[0]
        need(not difference,'Independent F/C exact key multiset differs')
    bad=con.execute("""SELECT count(*) FROM heldout_prediction_base_features f JOIN heldout_prediction_oracle_q q USING(query_id)
        WHERE f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor OR f.last_user_event_time>=q.anchor""").fetchone()[0]
    need(not bad,'Independent F/Q identity or strictpast timestamp differs')
    estimated=n*(4*len(names)+12)+len(queries);need(estimated<=2*2**30,'Independent matrix allocation cap')
    x=np.empty((n,len(names)),dtype=np.float32);groups=np.empty(n,dtype=np.int32);items=np.empty(n,dtype=np.int64)
    fields=[f'f."{name}"' for name in names[:39]]
    fields.extend(f'a."{name}"' for name in names[41:]);join=' JOIN heldout_prediction_extra_features a USING(query_id,product_id)' if len(names)==44 else ''
    check_staged(con,queries)
    con.execute('SELECT q.oracle_group,f.product_id,f.anchor,f.last_user_event_time,'+','.join(fields)+
        ' FROM heldout_prediction_base_features f JOIN heldout_prediction_oracle_q q USING(query_id)'+join+' ORDER BY q.oracle_group,f.product_id')
    offset=0
    while True:
        check();chunk=con.fetchmany(65536)
        if not chunk:break
        stop=offset+len(chunk);need(stop<=n,'Independent matrix row overrun')
        values=[]
        for j,(group,item,time,last,*features) in enumerate(chunk,offset):
            need(type(group) is int and 0<=group<len(queries) and type(item) is int and -2**63<=item<2**63,'Exact independent integer transport required')
            groups[j]=group;items[j]=item
            age=(time-last).total_seconds() if last is not None else float('nan')
            values.append([float(v) if v is not None else float('nan') for v in features[:39]]+[age,float(last is None)]+
                [float(v) if v is not None else float('nan') for v in features[39:]])
        x[offset:stop]=np.asarray(values,dtype=np.float32);need(not np.isinf(x[offset:stop]).any(),'Independent float32 features overflow/infinite')
        offset=stop
    need(offset==n,'Independent matrix incomplete');check();check_staged(con,queries)
    return dict(queries=queries,calendar_maturity=np.asarray(maturity,dtype=np.bool_),group=groups,items=items,x=x)


def matrix_digest(x,check):
    digest=hashlib.sha256()
    for start in range(0,len(x),65536):check();digest.update(memoryview(np.ascontiguousarray(x[start:start+65536])).cast('B'))
    check();return digest.hexdigest()


def saved_snapshot(body,spec,row):
    keys(body,{'artifact','model','feature_names','queries','calendar_maturity','group','items','scores'},'Saved prediction')
    saved=deepcopy(body);ref(saved['artifact']);ref(saved['model'])
    need(saved['model']==spec['model'] and saved['feature_names']==spec['feature_names'],'Saved model/projection differs')
    for name,dtype,count in [('calendar_maturity','bool',row['query_count']),('group','int32',row['candidate_count']),('items','int64',row['candidate_count']),('scores','float64',row['candidate_count'])]:
        value=saved[name];need(type(value) is np.ndarray and value.dtype==np.dtype(dtype) and value.shape==(count,),'Exact saved typed shape required')
    need(np.isfinite(saved['scores']).all(),'Finite saved raw scores required')
    queries=saved['queries'];need(type(queries) is list and len(queries)==row['query_count'],'Exact saved all-Q list required')
    identifiers=[];users=set();anchor=datetime.fromisoformat(row['anchor'][:-1])
    for q in queries:
        need(type(q) is tuple and len(q)==3,'Saved Q exact triple without targets required')
        qid,user,when=q
        need(type(qid) is str and qid and type(user) is int and -2**63<=user<2**63 and user not in users and type(when) is datetime and when==anchor,'Saved Q identity/calendar differs')
        identifiers.append(qid);users.add(user)
    need(identifiers==sorted(set(identifiers)) and saved['calendar_maturity'].all(),'Saved all-Q order/maturity differs')
    group,items=saved['group'],saved['items']
    need(((group>=0)&(group<len(queries))).all() and ((group[1:]>group[:-1])|((group[1:]==group[:-1])&(items[1:]>items[:-1]))).all(),'Saved canonical candidate domain differs')
    need((np.bincount(group,minlength=len(queries))<=220).all(),'Saved per-Q C cap')
    return saved


def verify_domain(saved,data):
    need(saved['queries']==data['queries'] and np.array_equal(saved['calendar_maturity'],data['calendar_maturity']) and
        np.array_equal(saved['group'],data['group']) and np.array_equal(saved['items'],data['items']),'Saved/all-Q and candidate key domain differs')


def verify_saved(saved,data,replay,check):
    verify_domain(saved,data)
    need(np.allclose(saved['scores'],replay,rtol=1e-12,atol=1e-12),'Independent native raw score mismatch')
    bounds=np.searchsorted(data['group'],np.arange(len(data['queries'])+1),side='left')
    for index in range(len(data['queries'])):
        check();left,right=int(bounds[index]),int(bounds[index+1]);items=data['items'][left:right].tolist()
        first=saved['scores'][left:right].tolist();second=replay[left:right].tolist()
        a=sorted(range(len(items)),key=lambda j:(-first[j],items[j]));b=sorted(range(len(items)),key=lambda j:(-second[j],items[j]))
        need(a==b,'Independent complete candidate tie/rank order mismatch')


def audit_day(con,anchor,source_day,*,choice,models,produced,load_model,check=lambda:None):
    """Paid original observer core; caller owns whole-lock and all-date gating."""
    need(type(anchor) is str and anchor in [f'2019-10-{day}T00:00:00Z' for day in range(25,32)],'Reserved oracle date required')
    need(choice in {'B','I1','I2','R1','R2'} and callable(load_model),'Frozen choice/explicit authenticated native loader required')
    row=deepcopy(source_day);specs=deepcopy(models);keys(specs,{'B','W'},'Frozen B/W specs');keys(produced,{'B','W'},'Saved B/W')
    need(type(row) is dict and row.get('anchor')==anchor,'Matching accepted source day required')
    for name,limit in [('query_count',2000),('candidate_count',440000)]:need(type(row.get(name)) is int and 0<=row[name]<=limit,'Daily independent source cap')
    need(row.get('mature_query_count')==row['query_count'] and type(row.get('mature_query_count')) is int,'All source Q must be mature')
    model_spec(specs['B'],41);model_spec(specs['W'],41 if choice=='B' else 44)
    need(specs['W']['feature_names'][:41]==specs['B']['feature_names'] and specs['W']['effective_parameters']==specs['B']['effective_parameters'],'B/W common model contract differs')
    if choice=='B':need(specs['B']==specs['W'],'W=B exact model reuse required')
    saved={role:saved_snapshot(produced[role],specs[role],row) for role in ('B','W')}
    if choice=='B':need(saved['B']['artifact']==saved['W']['artifact'],'W=B exact artifact reuse required')
    # Build W's superset once independently, then retain exact B projection.
    check();data=independent_matrix(con,anchor,row,specs['W']['feature_names'],check);calls=0;replayed={}
    for role in ('B','W'):verify_domain(saved[role],data)
    for role in ('B','W'):
        if role=='W' and choice=='B':replayed['W']=replayed['B'];verify_saved(saved['W'],data,replayed['W'],check);continue
        check();spec=specs[role];model=load_model(deepcopy(spec['model']));native_model(model,spec)
        x=data['x'][:,:len(spec['feature_names'])];witness=matrix_digest(data['x'],check)
        if row['candidate_count']:
            raw=model.predict(x,prediction_type='RawFormulaVal',ntree_start=0,ntree_end=300,thread_count=2);calls+=1
        else:raw=np.empty(0,dtype=np.float64)
        check();native_model(model,spec);need(matrix_digest(data['x'],check)==witness,'Independent matrix changed during native replay')
        need(type(raw) is np.ndarray and raw.dtype==np.dtype('float64') and raw.shape==(row['candidate_count'],) and np.isfinite(raw).all(),'Exact independent native raw float64 vector required')
        replayed[role]=raw.copy();verify_saved(saved[role],data,replayed[role],check);del model
    result=dict(status='independent_daily_scores_match_pending_all_date_and_owner_acceptance',anchor=anchor,
        queries=row['query_count'],candidate_pairs=row['candidate_count'],native_prediction_count=calls,
        fit_attempt_count=0,outcome_relations_opened=0,private_replayed_scores=replayed,
        proof_scope='independent_Q_C_F_numeric_projection_native_state_all_rawscores_complete_rank_order_no_byte_or_lifetime_authentication')
    check();check_staged(con,data['queries'])
    return result
