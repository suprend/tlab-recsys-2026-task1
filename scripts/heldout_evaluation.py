"""Gated fullY reporting core; no files, models, fitting or approval issuance.

Measured caller authenticates all snapshots/bytes and provides explicit Q/C and
saved-score readers on a private bounded connection. All seven dates' inputs
are checked before the first target relation is created. Private return values
must remain ignored artifacts; only aggregate reports may be published.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime

import numpy as np
from scripts import heldout_contract as h
from scripts import ranking_metrics as metrics


def _array(value, dtype, n, what):
    h.need(type(value) is np.ndarray and value.dtype==np.dtype(dtype) and value.shape==(n,),what+' exact typed vector required')
    return value.copy()


def _population(body, day, check):
    h.keys(body,{'queries','calendar_maturity','candidate_group','candidate_items'},'Q/C population')
    queries=deepcopy(body['queries']);qn,n=day['query_count'],day['candidate_count']
    h.need(type(queries) is list and len(queries)==qn,'All source queries required')
    identifiers=[];users=set();anchor=h.utc(day['anchor']).replace(tzinfo=None)
    for q in queries:
        h.need(type(q) is tuple and len(q)==3,'Q must contain exactly id/user/anchor')
        qid,user,when=q
        h.need(type(qid) is str and qid and type(user) is int and -2**63<=user<2**63
            and type(when) is datetime and when==anchor,'Exact Q identity/calendar required')
        h.need(user not in users,'Repeated user within daily Q');users.add(user);identifiers.append(qid)
    h.need(identifiers==sorted(set(identifiers)),'Canonical distinct all-Q order required')
    mature=_array(body['calendar_maturity'],'bool',qn,'Calendar')
    h.need(mature.all(),'Current calendar requires all Q mature')
    group=_array(body['candidate_group'],'int32',n,'C group');items=_array(body['candidate_items'],'int64',n,'C items')
    h.need(((group>=0)&(group<qn)).all(),'C group outside complete Q')
    h.need(((group[1:]>group[:-1])|((group[1:]==group[:-1])&(items[1:]>items[:-1]))).all(),'C duplicate/unordered keys')
    h.need((np.bincount(group,minlength=qn)<=220).all(),'Daily per-Q C cap')
    check();return dict(queries=queries,calendar_maturity=mature,group=group,items=items)


def _scores(body, pop, count, check):
    h.keys(body,{'group','items','scores'},'Saved score data')
    group=_array(body['group'],'int32',count,'Score group');items=_array(body['items'],'int64',count,'Score items')
    raw=_array(body['scores'],'float64',count,'Raw score')
    h.need(np.isfinite(raw).all(),'Nonfinite saved raw score')
    h.need(np.array_equal(group,pop['group']) and np.array_equal(items,pop['items']),'Saved score/source C exact keys differ')
    check();return raw


def _prepare(source, inventory, lock, population_loader, score_loader, check):
    h.need(callable(population_loader) and callable(score_loader),'Explicit source/saved-score providers required')
    source_by_day={day['anchor']:day for day in source['days']}
    predicted={day['anchor']:day for day in inventory['days']};prepared=[];seen=set()
    for anchor in h.DAYS:
        check();day=deepcopy(source_by_day[anchor]);pop=_population(population_loader(deepcopy(day)),day,check)
        for qid,user,when in pop['queries']:
            h.need(qid not in seen,'Query ID repeated across dates');seen.add(qid)
        raw={}
        for role in ['B','W']:
            descriptor=deepcopy(predicted[anchor]['predictions'][role])
            raw[role]=_scores(score_loader(descriptor),pop,day['candidate_count'],check)
        if lock['choice']=='B':h.need(np.array_equal(raw['B'],raw['W']),'W=B saved raw scores must be identical')
        prepared.append(dict(anchor=anchor,population=pop,scores=raw))
    check();return prepared


def _staged_population(con, rows):
    actual=con.execute('SELECT query_id,user_id,anchor FROM heldout_target_queries ORDER BY query_id').fetchall()
    h.need(actual==sorted(rows),'Staged target Q population differs from retained all-date snapshot')


def _targets(con, prepared, lock, check, stage):
    check()
    h.need(con.execute("SELECT current_setting('threads')").fetchone()[0]==2,'Explicit two-thread target connection required')
    types={row[0]:row[1] for row in con.execute('DESCRIBE heldout_raw_events').fetchall()}
    h.need(all(types.get(k)==v for k,v in dict(event_time='TIMESTAMP',event_type='VARCHAR',user_id='BIGINT',product_id='BIGINT').items()),'Typed fullY source required')
    rows=[q for day in prepared for q in day['population']['queries']]
    def create_population():
        # Exclusive TEMP names also make accidental in-connection retry fail.
        con.execute('CREATE TEMP TABLE heldout_target_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP)')
        if rows:con.executemany('INSERT INTO heldout_target_queries VALUES (?,?,?)',rows)
    check();stage('create_complete_target_query_population',create_population);check()
    _staged_population(con,rows)
    def create_targets():
        # The stage wrapper can run before the JOIN; compare inside its operation.
        _staged_population(con,rows)
        con.execute("""CREATE TEMP TABLE heldout_full_targets AS SELECT DISTINCT q.query_id,e.product_id
            FROM heldout_target_queries q JOIN heldout_raw_events e ON e.user_id=q.user_id
              AND e.event_time>=q.anchor AND e.event_time<q.anchor+INTERVAL 24 HOUR
            WHERE e.event_type='purchase' AND e.product_id IS NOT NULL""")
    stage('create_fullY_independent_of_candidates',create_targets);check()
    _staged_population(con,rows)
    target={qid:set() for qid,user,when in rows};count=0
    cursor=con.execute('SELECT query_id,product_id FROM heldout_full_targets ORDER BY query_id,product_id')
    while True:
        check();chunk=cursor.fetchmany(65536)
        if not chunk:break
        for qid,item in chunk:
            h.need(type(qid) is str and qid in target and type(item) is int and -2**63<=item<2**63,'Exact target Q/product key required')
            h.need(item not in target[qid],'Distinct full targets required');target[qid].add(item);count+=1
        h.need(count<=2000000,'FullY row safety cap')
    check();_staged_population(con,rows)
    return {key:frozenset(value) for key,value in target.items()}


def _rankings(prepared, targets, check):
    result={role:[] for role in ['B','W']};support=dict(query_count=0,candidate_pairs=0,target_pairs=0,retrieved_target_pairs=0,positive_empty_C_queries=0)
    for day in prepared:
        pop=day['population'];group,items=pop['group'],pop['items'];left=0
        for index,(qid,user,when) in enumerate(pop['queries']):
            check();right=left
            while right<len(group) and group[right]==index:right+=1
            candidate_items=items[left:right].tolist();full=targets[qid]
            support['query_count']+=1;support['candidate_pairs']+=len(candidate_items);support['target_pairs']+=len(full)
            support['retrieved_target_pairs']+=len(set(candidate_items)&full);support['positive_empty_C_queries']+=int(bool(full) and not candidate_items)
            for role in ['B','W']:
                scores=day['scores'][role][left:right].tolist()
                ordered=[item for item,score in sorted(zip(candidate_items,scores),key=lambda pair:(-pair[1],pair[0]))[:20]]
                result[role].append(metrics.QueryRanking(qid,user,ordered,full,True))
            left=right
        h.need(left==len(group),'Every candidate must map to a retained query')
    check();return result,support


def evaluate_windows(con, lock, inventory, target_intent, *, authenticated_choice,
        authenticated_source, authenticated_prediction_acceptance,
        load_day_population, load_saved_scores, check=lambda:None,stage=lambda name,op:op()):
    """One reporting call after authenticated all-date prediction acceptance.

    No default provider, file read or authorization writer is supplied. Successful
    return does not accept the owner exit tail or independently verify fullY.
    A failed original target attempt remains consumed in the external owner.
    """
    check();locked=h.validate_lock(lock,authenticated_choice=authenticated_choice)
    source=deepcopy(authenticated_source)
    predicted=h.validate_prediction_inventory(inventory,locked,authenticated_source=source)
    intent=h.validate_target_intent(target_intent,locked,predicted,
        authenticated_prediction_acceptance=authenticated_prediction_acceptance)
    prepared=_prepare(source,predicted,locked,load_day_population,load_saved_scores,check)
    # The first source/target operation follows ALL7 Q/C/B/W shape/key checks.
    targets=_targets(con,prepared,locked,check,stage)
    report={};private={}
    for name,anchors in [('confirmation25_reporting_only',h.DAYS[:1]),('final26_31_frozen',h.DAYS[1:])]:
        check();days=[day for day in prepared if day['anchor'] in anchors]
        ranked,support=_rankings(days,targets,check);values={}
        for role in ['B','W']:check();values[role]=asdict(metrics.evaluate(ranked[role],20))
        bootstrap={};difference={}
        for estimand in metrics.ESTIMANDS:
            check();first=values['W'][estimand]['ndcg'];second=values['B'][estimand]['ndcg']
            difference[estimand]=first-second if first is not None and second is not None else None
            bootstrap[estimand]=asdict(metrics.paired_user_bootstrap(ranked['W'],ranked['B'],20,
                metric='ndcg',estimand=estimand,replicates=200,seed=2026));check()
        report[name]=dict(anchors=list(anchors),metrics=values,ndcg_W_minus_B=difference,paired_user_bootstrap=bootstrap,support=support)
        private[name]=ranked
    # Last callback precedes the final exact binding check; no callback follows it.
    check();_staged_population(con,[q for day in prepared for q in day['population']['queries']])
    return dict(scope='fixed_reserved_fullY_reporting_core',periods=report,
        private_targets=targets,private_rankings=private,target_intent=intent,
        fit_attempt_count=0,native_prediction_count=0,source_feature_calculations=0,
        proof='independent_fullY_metric_oracle_and_complete_owner_lifetime_acceptance_required')
