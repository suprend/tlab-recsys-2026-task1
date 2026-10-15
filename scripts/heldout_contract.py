"""Pure reserved-period evidence contracts; no files, models or targets opened.

These validators check supplied snapshots against caller-authenticated authority.
They do not establish file authenticity, issue approval, or grant target access.
The executable source/inference/evaluator owners remain separate review gates.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re

DAYS=[f'2019-10-{day:02d}T00:00:00Z' for day in range(25,32)]
DECISION_AVAILABLE='2019-10-24T12:00:00Z'
MATURITY='2019-10-24T00:00:00Z'
SCHEMA_VERSION=1
STAGES={'smoke008','metadata009','strong019','automation016','decision_preparation'}
POLICY=dict(version=1,scope='reporting_only_reserved_calendar_v1',
    confirmation=dict(start=DAYS[0],end=DAYS[1]),
    final=dict(start=DAYS[1],end='2019-11-01T00:00:00Z'),
    supersedes='old017_confirmation24_25_planning_only',
    source=dict(start='2019-10-01T00:00:00Z',end='2019-11-01T00:00:00Z',
                coverage_basis='original_archive_completeness_assumption_not_observed_extrema',
                availability='event_time_offline_assumption',delay_seconds=0),
    query=dict(kind='daily_UTC_clock',eligibility_hours=48,events=['view','cart','purchase'],
               sampling='sha256_user_day_seed_before_labels',seed=2026,max_users_per_day=2000),
    candidates=dict(popular_limit=200,recent_limit=20,window_hours=168,max_unique=220,
                    popularity_unit='distinct_purchase_users',recent_events=['view','cart','purchase'],
                    catalog='seen_strictly_before_query',duplicates='deduplicate_product_no_refill'),
    history=dict(duplicates='raw',ties='global_read_before_update',metadata='last_strict_past_ambiguity_preserved'),
    target=dict(event='purchase',horizon_hours=24,include_anchor=True,include_end=False,
                relevance='distinct_binary_products',full_Y_independent_of_C=True),
    estimator=dict(primary='conditional_macro_query_NDCG20_W_minus_B',
                   secondary=['conditional_macro_query_recall20','all_query_zero','conditional_user_macro','all_user_macro_zero'],
                   bootstrap=dict(unit='paired_user',replicates=200,seed=2026,undefined='report_undefined_not_zero')),
    inference=dict(thread_count=2,raw_formula=True,no_fit=True,no_adaptation=True,
                   all_predictions_before_any_reserved_Y=True,losing_arms_scored=False),
    disclosure=dict(full_month_EDA_and_source_audit=True,
                    claim='reserved_query_level_targets_and_metrics_not_used_for_model_selection'))


def canonical(body):
    return json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def digest(body):return hashlib.sha256(canonical(body).encode()).hexdigest()


def need(condition,message):
    if not condition:raise ValueError(message)


def keys(body,expected,what):
    need(type(body) is dict and set(body)==set(expected),what+' exact keys required')


def utc(value):
    need(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',value) is not None,'Second-resolution UTC required')
    return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def integer(value,lower,upper,what):
    need(type(value) is int and lower<=value<=upper,what+' typed integer range')


def nonnegative(value,what):
    need(type(value) in (int,float) and math.isfinite(value) and value>=0,what+' finite nonnegative required')


def ref(body):
    keys(body,{'path','sha256'},'reference')
    name=body['path']
    need(type(name) is str and re.fullmatch(r'[A-Za-z0-9_./-]+',name) is not None
         and not name.startswith('/') and '..' not in name.split('/') and name not in {'.',''},'Local normalized reference required')
    need(all(part not in {'','.'} for part in name.split('/')),'Reference aliases forbidden')
    need(type(body['sha256']) is str and re.fullmatch(r'[a-f0-9]{64}',body['sha256']) is not None,'Reference SHA256 required')


def validate_policy(body):
    need(canonical(body)==canonical(POLICY),'Prospective reserved calendar/policy differs')
    return deepcopy(body)


def model(body):
    keys(body,{'model','feature_names','trained_iterations','scoring_prefix','population','effective_parameters'},'frozen model')
    ref(body['model']);integer(body['trained_iterations'],300,300,'trained iterations')
    integer(body['scoring_prefix'],300,300,'scoring prefix');integer(body['population'],26000,26000,'training population')
    names=body['feature_names'];need(type(names) is list and len(names) in {41,44} and len(set(names))==len(names),'Frozen B41 or B+3 schema required')
    need(all(type(n) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',n) for n in names),'Feature names required')
    need(not set(names)&{'query_id','user_id','product_id','anchor','label_is_mature','candidate_category_id'},'Keys/calendar cannot become inputs')
    params=body['effective_parameters'];need(type(params) is dict and params,'Exact effective parameters required')
    for key,value in {'loss_function':'Logloss','depth':6,'l2_leaf_reg':30,'iterations':300,'task_type':'CPU'}.items():
        need(type(params.get(key)) is type(value) and params[key]==value,'Inherited model settings differ')


def validate_lock(body,*,authenticated_choice):
    """Choice is a previously authenticated external model-output snapshot.

    Passing self-authored choice/receipts supplies no independent acceptance.
    This function deliberately neither hashes files nor reads model metadata.
    """
    keys(body,{'version','scope','policy','choice','models','authority_refs','code_refs','sealed_at',
               'simulated_clock','compute_evidence','heldout_targets_opened'},'decision lock')
    need(type(body['version']) is int and body['version']==1 and body['scope']=='whole_reserved_decision_lock','Lock version/scope differs')
    validate_policy(body['policy']);need(body['heldout_targets_opened'] is False,'Lock after target access forbidden')
    keys(authenticated_choice,{'candidate_id','models','authority_refs'},'authenticated choice')
    need(body['choice']==authenticated_choice['candidate_id'] and body['choice'] in {'B','I1','I2','R1','R2'},'Final selector identity differs')
    need(canonical(body['models'])==canonical(authenticated_choice['models']) and
         canonical(body['authority_refs'])==canonical(authenticated_choice['authority_refs']),'Whole choice/model authority differs')
    keys(body['models'],{'B','W'},'models')
    for item in body['models'].values():model(item)
    b,w=body['models']['B'],body['models']['W'];need(len(b['feature_names'])==41,'B41 required')
    if body['choice']=='B':need(canonical(b)==canonical(w),'W=B must transparently reuse exact B')
    else:
        need(len(w['feature_names'])==44 and w['feature_names'][:41]==b['feature_names'],'W must append exact three inputs')
        need(canonical(b['effective_parameters'])==canonical(w['effective_parameters']),'Frozen matched learner required')
    authorities=body['authority_refs'];keys(authorities,{'control','automation','source','selector','pool'},'decision authorities')
    for item in authorities.values():ref(item)
    need(type(body['code_refs']) is list and body['code_refs'],'Complete executable code references required')
    for item in body['code_refs']:ref(item)
    need(len({r['path'] for r in body['code_refs']})==len(body['code_refs']),'Repeated code paths')
    utc(body['sealed_at'])
    clock=body['simulated_clock'];keys(clock,{'maximum_used_label_maturity','declared_compute_allowance_seconds','decision_available_at'},'simulated clock')
    need(clock['maximum_used_label_maturity']==MATURITY,'Maximum development label maturity differs')
    integer(clock['declared_compute_allowance_seconds'],43200,43200,'Positive simulated allowance')
    need(clock['decision_available_at']==DECISION_AVAILABLE and utc(MATURITY)+timedelta(seconds=43200)==utc(DECISION_AVAILABLE)<utc(DAYS[0]),'Decision compute gap differs')
    evidence=body['compute_evidence'];need(type(evidence) is list and len(evidence)==len(STAGES),'All decision-producing stage bounds required')
    seen=set();total=0
    for row in evidence:
        keys(row,{'stage','measured_active_wall_upper_seconds','declared_unmeasured_wall_upper_seconds','receipt'},'compute evidence')
        need(row['stage'] in STAGES and row['stage'] not in seen,'Duplicate/missing development stage');seen.add(row['stage']);ref(row['receipt'])
        for key in ['measured_active_wall_upper_seconds','declared_unmeasured_wall_upper_seconds']:nonnegative(row[key],key)
        total+=row['measured_active_wall_upper_seconds']+row['declared_unmeasured_wall_upper_seconds']
    need(0<total<=43200,'Recorded-plus-declared active wall exceeds simulated allowance')
    return deepcopy(body)


def validate_prediction_inventory(body,lock,*,authenticated_source):
    """Physical proof/source authenticity and native replay belong to the caller."""
    keys(body,{'version','scope','decision_lock_sha256','created_at','source_acceptance','days','output_verification','lifetime_receipt','heldout_targets_opened'},'prediction inventory')
    need(type(body['version']) is int and body['version']==1 and body['scope']=='all_reserved_predictions_before_targets','Prediction scope differs')
    need(body['decision_lock_sha256']==digest(lock),'Prediction decision lock differs')
    need(utc(body['created_at'])>=utc(lock['sealed_at']),'Prediction precedes physical decision seal')
    need(body['heldout_targets_opened'] is False,'Predictions after target access forbidden')
    keys(authenticated_source,{'acceptance','days'},'authenticated heldout source')
    ref(body['source_acceptance']);need(body['source_acceptance']==authenticated_source['acceptance'],'New-date source authority differs')
    ref(body['output_verification']);ref(body['lifetime_receipt'])
    need(type(body['days']) is list and len(body['days'])==7,'All seven dates must precede any Y opening')
    source_days=authenticated_source['days']
    need(type(source_days) is list and len(source_days)==7,'Authenticated source requires exactly seven physical day records')
    source={row['anchor']:row for row in source_days}
    need(len(source)==7 and set(source)==set(DAYS),'Authenticated source calendar incomplete or repeated')
    seen=set()
    for row in body['days']:
        keys(row,{'anchor','queries','candidates','base_features','extra_features','query_count','candidate_count','mature_query_count','predictions'},'daily prediction inventory')
        day=row['anchor'];need(day in DAYS and day not in seen,'Missing/repeated/outside reserved date');seen.add(day)
        src=source[day]
        for field in ['queries','candidates','base_features','extra_features','query_count','candidate_count','mature_query_count']:
            need(canonical(row[field])==canonical(src[field]),'Daily source domain differs')
        for field in ['queries','candidates','base_features']:ref(row[field])
        integer(row['query_count'],0,2000,'Daily Q');integer(row['candidate_count'],0,row['query_count']*220,'Daily C')
        integer(row['mature_query_count'],0,row['query_count'],'Mature Q')
        policy=lock['policy']
        available=utc(day)+timedelta(hours=policy['target']['horizon_hours'],seconds=policy['source']['delay_seconds'])
        calendar_mature=available<=utc(policy['source']['end'])
        need(row['mature_query_count']==(row['query_count'] if calendar_mature else 0),
             'Daily maturity must follow declared calendar coverage, never outcomes')
        if lock['choice']=='B':need(row['extra_features'] is None,'B-only comparison cannot invent extras')
        else:ref(row['extra_features'])
        keys(row['predictions'],{'B','W'},'daily B/W predictions')
        for name,item in row['predictions'].items():
            keys(item,{'artifact','model','rows','queries','scoring_prefix','feature_names'},'prediction descriptor')
            ref(item['artifact']);need(item['model']==lock['models'][name]['model'],'Prediction model changed')
            need(type(item['rows']) is int and item['rows']==row['candidate_count'] and type(item['queries']) is int and item['queries']==row['query_count'],'Empty-C/all-Q domain lost')
            need(type(item['scoring_prefix']) is int and item['scoring_prefix']==300 and item['feature_names']==lock['models'][name]['feature_names'],'Prediction prefix/schema changed')
        if lock['choice']=='B':need(canonical(row['predictions']['B'])==canonical(row['predictions']['W']),'W=B prediction reuse must be exact')
    return deepcopy(body)


def validate_target_intent(body,lock,inventory,*,authenticated_prediction_acceptance):
    """Check intent only; never creates Y or grants an unverified capability."""
    keys(body,{'version','scope','prediction_acceptance','prediction_inventory_sha256','decision_lock_sha256','opened_at','periods','no_adaptation'},'target intent')
    need(type(body['version']) is int and body['version']==1 and body['scope']=='report_only_reserved_fullY','Target intent scope differs')
    keys(authenticated_prediction_acceptance,{'reference','inventory_sha256','decision_lock_sha256'},'authenticated prediction acceptance')
    ref(body['prediction_acceptance']);need(body['prediction_acceptance']==authenticated_prediction_acceptance['reference'],'External prediction acceptance differs')
    need(body['prediction_inventory_sha256']==authenticated_prediction_acceptance['inventory_sha256']==digest(inventory),'All-date prediction inventory unbound')
    need(body['decision_lock_sha256']==authenticated_prediction_acceptance['decision_lock_sha256']==digest(lock),'Whole-decision lock unbound')
    need(utc(body['opened_at'])>utc(inventory['created_at'])>=utc(lock['sealed_at']),'Physical prediction-before-Y order violated')
    need(body['periods']==['confirmation25_reporting_only','final26_31_frozen'] and body['no_adaptation'] is True,'Reporting periods/adaptation changed')
    return deepcopy(body)
