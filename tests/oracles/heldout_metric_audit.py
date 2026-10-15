"""Independent reserved fullY/metric arithmetic core, never a runtime grant.

No production evaluator, ranking-metric or target-builder import is used.
The measured external caller authenticates/gates input bytes and lifetime.
Only synthetic callers are used by code tests; no file or model API exists.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import math
import random

import numpy as np

DAYS=tuple((datetime(2019,10,25)+timedelta(days=i)).isoformat()+'Z' for i in range(7))
NAMES=('recall','ndcg','average_precision','reciprocal_rank')
ESTIMANDS=('conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero')


def need(condition,message):
    if not condition:raise ValueError(message)


def keys(body,expected,what):
    need(type(body) is dict and set(body)==set(expected),what+' exact keys required')


def vector(value,dtype,count,what):
    need(type(value) is np.ndarray and value.dtype==np.dtype(dtype) and value.shape==(count,),what+' exact typed vector required')
    return value.copy()


def snapshot_days(days,check):
    need(type(days) is list and len(days)==7,'All seven metric-oracle dates required')
    result=[];seen=set()
    for index,body in enumerate(days):
        check();keys(body,{'anchor','queries','calendar_maturity','group','items','scores'},'Metric oracle day')
        need(body['anchor']==DAYS[index],'Canonical exact oracle date order required')
        queries=deepcopy(body['queries']);need(type(queries) is list and len(queries)<=2000,'Daily all-Q oracle cap')
        qids=[];users=set();when=datetime.fromisoformat(DAYS[index][:-1])
        for q in queries:
            need(type(q) is tuple and len(q)==3,'Exact oracle Q triple required')
            qid,user,anchor=q
            need(type(qid) is str and qid and qid not in seen,'Unique all-date oracle Q identifier required')
            need(type(user) is int and -2**63<=user<2**63 and user not in users,'Daily unique exact int64 user required')
            need(type(anchor) is datetime and anchor==when,'Exact oracle query anchor required')
            seen.add(qid);users.add(user);qids.append(qid)
        need(qids==sorted(qids),'Canonical oracle Q order required')
        mature=vector(body['calendar_maturity'],'bool',len(queries),'Oracle calendar')
        need(mature.all(),'Declared Nov1 coverage requires every reserved query mature')
        items=body['items'];need(type(items) is np.ndarray and items.ndim==1 and len(items)<=440000,'Daily oracle C cap')
        items=vector(items,'int64',len(items),'Oracle item');group=vector(body['group'],'int32',len(items),'Oracle group')
        need(((group>=0)&(group<len(queries))).all(),'Oracle C group outside all-Q')
        need(((group[1:]>group[:-1])|((group[1:]==group[:-1])&(items[1:]>items[:-1]))).all(),'Oracle C keys must be distinct canonical')
        need((np.bincount(group,minlength=len(queries))<=220).all(),'Oracle per-Q C cap')
        keys(body['scores'],{'B','W'},'Oracle model scores');scores={}
        for role in ('B','W'):
            scores[role]=vector(body['scores'][role],'float64',len(items),'Oracle raw score')
            need(np.isfinite(scores[role]).all(),'Oracle raw scores must be finite')
        result.append(dict(anchor=DAYS[index],queries=queries,group=group,items=items,scores=scores))
    return result


def check_query_relation(con,queries):
    actual=con.execute('SELECT query_id,user_id,anchor FROM heldout_metric_queries ORDER BY query_id').fetchall()
    need(actual==sorted(queries),'Oracle staged Q differs from retained complete source Q')


def raw_targets(con,queries,check):
    check();need(con.execute("SELECT current_setting('threads')").fetchone()[0]==2,'Two-thread oracle connection required')
    schema=dict((row[0],row[1]) for row in con.execute('DESCRIBE heldout_raw_events').fetchall())
    need(all(schema.get(k)==v for k,v in dict(event_time='TIMESTAMP',event_type='VARCHAR',user_id='BIGINT',product_id='BIGINT').items()),'Typed independent raw target source required')
    # Exclusive name: failed original calls cannot be retried on this connection.
    con.execute('CREATE TEMP TABLE heldout_metric_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)')
    if queries:con.executemany('INSERT INTO heldout_metric_queries VALUES (?,?,?)',queries)
    check();check_query_relation(con,queries)
    cursor=con.execute("""SELECT q.query_id,e.product_id FROM heldout_raw_events e
        INNER JOIN heldout_metric_queries q ON q.user_id=e.user_id
        WHERE e.event_type='purchase' AND e.product_id IS NOT NULL
          AND e.event_time>=q.anchor AND e.event_time<q.anchor+INTERVAL 24 HOUR
        GROUP BY q.query_id,e.product_id ORDER BY q.query_id,e.product_id""")
    full={qid:set() for qid,user,anchor in queries};count=0
    while True:
        check();chunk=cursor.fetchmany(65536)
        if not chunk:break
        for qid,item in chunk:
            need(type(qid) is str and qid in full and type(item) is int and -2**63<=item<2**63,'Exact independent fullY key required')
            need(item not in full[qid],'Independent target key repeated');full[qid].add(item);count+=1
        need(count<=2000000,'Independent fullY safety cap')
    check();check_query_relation(con,queries)
    return {qid:frozenset(items) for qid,items in full.items()}


def query_values(ordered,full):
    if not full:return dict.fromkeys(NAMES,None)
    relevant=[int(item in full) for item in ordered[:20]]
    hits=sum(relevant);ranks=[i+1 for i,value in enumerate(relevant) if value]
    dcg=math.fsum(1/math.log2(rank+1) for rank in ranks)
    ideal=math.fsum(1/math.log2(rank+1) for rank in range(1,min(20,len(full))+1))
    ap=math.fsum(index/rank for index,rank in enumerate(ranks,1))/len(full)
    return dict(recall=hits/len(full),ndcg=dcg/ideal,average_precision=ap,
        reciprocal_rank=1/ranks[0] if ranks else 0.0)


def ranked_rows(days,full,check):
    output={role:[] for role in ('B','W')}
    support=dict(query_count=0,candidate_pairs=0,target_pairs=0,retrieved_target_pairs=0,positive_empty_C_queries=0)
    for day in days:
        bounds=np.searchsorted(day['group'],np.arange(len(day['queries'])+1),side='left')
        for index,(qid,user,anchor) in enumerate(day['queries']):
            check();left,right=int(bounds[index]),int(bounds[index+1]);items=day['items'][left:right].tolist();targets=full[qid]
            support['query_count']+=1;support['candidate_pairs']+=len(items);support['target_pairs']+=len(targets)
            support['retrieved_target_pairs']+=len(set(items)&targets);support['positive_empty_C_queries']+=int(bool(targets) and not items)
            for role in ('B','W'):
                # Independent index permutation, then explicit exact-ID tie order.
                scores=day['scores'][role][left:right].tolist()
                permutation=sorted(range(len(items)),key=lambda j:(-scores[j],items[j]))[:20]
                ordered=tuple(items[j] for j in permutation)
                output[role].append(dict(query_id=qid,user_id=user,targets=targets,ordered=ordered,values=query_values(ordered,targets)))
    return output,support


def user_groups(rows):
    groups={}
    for row in rows:groups.setdefault(row['user_id'],[]).append(row)
    return groups


def aggregate(groups,estimand,metric,draw=None):
    conditional=estimand.startswith('conditional');user_macro='user_macro' in estimand
    contributions=[]
    for user in groups if draw is None else draw:
        rows=groups[user];chosen=[row for row in rows if row['targets']] if conditional else rows
        values=[row['values'][metric] if row['targets'] else 0.0 for row in chosen]
        if user_macro:
            if values:contributions.append(math.fsum(values)/len(values))
        else:contributions.extend(values)
    return math.fsum(contributions)/len(contributions) if contributions else None


def evaluation(rows):
    groups=user_groups(rows);positive=[row for row in rows if row['targets']]
    result=dict(k=20,query_count=len(rows),mature_query_count=len(rows),censored_query_count=0,
        nonempty_query_count=len(positive),mature_user_count=len(groups),positive_user_count=len({row['user_id'] for row in positive}),
        nonempty_fraction=len(positive)/len(rows) if rows else None)
    result.update({estimand:{name:aggregate(groups,estimand,name) for name in NAMES} for estimand in ESTIMANDS})
    return result


def percentile(values,p):
    position=p*(len(values)-1);lower=int(math.floor(position));upper=int(math.ceil(position));fraction=position-lower
    return values[lower]*(1-fraction)+values[upper]*fraction


def bootstrap(left,right,estimand,draws,check):
    a,b=user_groups(left),user_groups(right)
    def delta(draw):
        first,second=aggregate(a,estimand,'ndcg',draw),aggregate(b,estimand,'ndcg',draw)
        return first-second if first is not None and second is not None else None
    samples=[]
    for draw in draws:check();samples.append(delta(draw))
    defined=sorted(value for value in samples if value is not None)
    return dict(metric='ndcg',estimand=estimand,seed=2026,replicates=200,user_count=len(a),estimate=delta(None),
        samples=tuple(samples),undefined_draws=200-len(defined),interval_95=(percentile(defined,.025),percentile(defined,.975)) if defined else None)


def compare(actual,expected,path='report'):
    if type(expected) is dict:
        keys(actual,expected,path)
        for key,value in expected.items():compare(actual[key],value,path+'.'+key)
    elif type(expected) in (list,tuple):
        need(type(actual) in (list,tuple) and len(actual)==len(expected),path+' exact array cover required')
        for index,value in enumerate(expected):compare(actual[index],value,path+'['+str(index)+']')
    elif type(expected) is float:
        need(type(actual) is float and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12),path+' independent numeric mismatch')
    else:need(type(actual) is type(expected) and actual==expected,path+' independent exact mismatch')


def audit_windows(con,*,days,produced_targets,produced_periods,check=lambda:None):
    """Audit supplied immutable artifacts AFTER external target/observer approval.

    Caller pins raw source and all seven Q/C/score/output bytes before and after
    this paid original observer. This function cannot issue that authorization.
    """
    targets=deepcopy(produced_targets);periods=deepcopy(produced_periods)
    snapshots=snapshot_days(days,check);queries=[q for day in snapshots for q in day['queries']]
    need(type(targets) is dict and set(targets)=={q[0] for q in queries},'Produced fullY must retain exactly all Q')
    for value in targets.values():
        need(type(value) in (set,frozenset) and all(type(item) is int and -2**63<=item<2**63 for item in value),'Produced fullY exact int64 sets required')
    full=raw_targets(con,queries,check);need(full==targets,'Independent raw fullY mismatch')
    expected={};private={}
    for name,selected in [('confirmation25_reporting_only',snapshots[:1]),('final26_31_frozen',snapshots[1:])]:
        rows,support=ranked_rows(selected,full,check);values={role:evaluation(rows[role]) for role in ('B','W')}
        users=list(user_groups(rows['W']));rng=random.Random(2026)
        draws=[rng.choices(users,k=len(users)) for _ in range(200)]
        differences={};replicates={}
        for estimand in ESTIMANDS:
            first,second=values['W'][estimand]['ndcg'],values['B'][estimand]['ndcg']
            differences[estimand]=first-second if first is not None and second is not None else None
            replicates[estimand]=bootstrap(rows['W'],rows['B'],estimand,draws,check)
        expected[name]=dict(anchors=[day['anchor'] for day in selected],metrics=values,ndcg_W_minus_B=differences,
            paired_user_bootstrap=replicates,support=support);private[name]=rows
    compare(periods,expected)
    result=dict(status='independent_core_values_match_pending_owner_acceptance',periods=expected,
        private_targets=full,private_rankings=private,fullY_pairs=sum(map(len,full.values())),
        fit_attempt_count=0,native_prediction_count=0,bootstrap_replicates_per_estimand=200,
        proof_scope='raw_fullY_all_queries_all_scores_four_estimands_every_fixed_user_draw_no_lifetime_or_byte_authentication')
    check();check_query_relation(con,queries)
    return result
