"""Independent label-blind heldout source core; no files, owner or target authority.

Expected Q/C and selected columns come directly from raw strict-past events.
New-date core18 values are explicitly sampled; structure/metadata are exhaustive.
"""
from copy import deepcopy
from datetime import timedelta
import math
import re

from scripts import heldout_contract as h

Q_SCHEMA=[('query_id','VARCHAR'),('user_id','BIGINT'),('anchor','TIMESTAMP'),('eligibility_events','BIGINT'),
 ('history_events_7d','BIGINT'),('history_distinct_items_7d','BIGINT'),('history_active_days_7d','BIGINT'),
 ('last_history_time','TIMESTAMP'),('history_coverage_7d','DOUBLE'),('label_is_mature','BOOLEAN')]
C_SCHEMA=[('query_id','VARCHAR'),('product_id','BIGINT'),('from_popular','BOOLEAN'),('from_recent','BOOLEAN'),
 ('popularity_distinct_users','BIGINT'),('popular_source_rank','BIGINT'),('recent_source_rank','BIGINT'),('last_user_event_time','TIMESTAMP')]
METADATA=[('candidate_category_id','BIGINT'),('candidate_category_ambiguous','BOOLEAN'),('candidate_category_missing','BOOLEAN'),
 ('item_has_observed_history','BOOLEAN'),('user_has_observed_history','BOOLEAN'),('item_observed_age_seconds','DOUBLE'),('user_observed_age_seconds','DOUBLE')]
CORE=[('user_view_7d','user','view','count'),('user_cart_7d','user','cart','count'),('user_purchase_7d','user','purchase','count'),
 ('user_distinct_viewed_items_7d','user','view','distinct'),('pair_view_7d','pair','view','count'),('pair_cart_7d','pair','cart','count'),
 ('pair_purchase_7d','pair','purchase','count'),('pair_view_recency_seconds','pair','view','recency'),('pair_purchase_recency_seconds','pair','purchase','recency'),
 ('item_view_24h','item','view','count'),('item_purchase_24h','item','purchase','count'),('item_distinct_viewers_7d','item','view','distinct'),
 ('user_category_view_7d','user_category','view','count'),('user_category_view_share_7d','user_category',None,'ratio'),
 ('user_category_view_recency_seconds','user_category','view','recency'),('item_category_view_7d','item_category','view','count'),
 ('category_view_7d','category','view','count'),('item_category_view_share_7d','item_category',None,'ratio')]
FLAGS=[n+'_missing' for n,g,_,op in CORE if op in {'ratio','recency'} or 'category' in g]
CORE_FIELDS=[(n,'DOUBLE' if op=='recency' else 'BIGINT') for n,_,_,op in CORE if op!='ratio']
COVERAGE=[('source_coverage_24h','DOUBLE'),('source_coverage_168h','DOUBLE')]
RATIOS=[(n,'DOUBLE') for n,_,_,op in CORE if op=='ratio']
B_SCHEMA=C_SCHEMA+[('user_id','BIGINT'),('anchor','TIMESTAMP')]+METADATA+CORE_FIELDS+COVERAGE+RATIOS+[(n,'BOOLEAN') for n in FLAGS]
B_MODEL=[n for n,_ in C_SCHEMA[2:7]]+[n for n,_ in METADATA[1:]]+[n for n,_ in CORE_FIELDS+COVERAGE+RATIOS]+FLAGS+['retrieval_last_event_age_seconds','retrieval_last_event_missing']
CHOSEN={
 'B':[],
 'I1':[(f'auto_pair_{a}_count_24h','BIGINT') for a in ('view','cart','purchase')],
 'I2':[('auto_pair_cart_recency_seconds_observed','DOUBLE'),('auto_item_cart_count_24h','BIGINT'),('auto_pair_cart_recency_seconds_observed_missing','BOOLEAN')],
 'R1':[(f'auto_user_{a}_count_24h','BIGINT') for a in ('view','cart','purchase')],
 'R2':[('auto_item_view_count_distinct_24h_user_id','BIGINT'),('auto_item_cart_count_distinct_168h_user_id','BIGINT'),('auto_item_purchase_count_distinct_24h_user_id','BIGINT')]}
DAY_FIELDS={'anchor','queries','candidates','base_features','extra_features','query_count','candidate_count','mature_query_count'}


def need(value,gate):
 if not value:raise ValueError(gate)


def quote(name):
 need(type(name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',name) is not None,'Unsafe relation identifier')
 return '"'+name+'"'


def run(con,sql,params=(),*,check):
 check();value=con.execute(sql,list(params));check();return value


def schema(con,table,expected,check):
 need([tuple(r[:2]) for r in run(con,'DESCRIBE '+quote(table),check=check).fetchall()]==expected,'Physical schema/order differs: '+table)


def equivalent(con,left,right,columns,check):
 fields=','.join(quote(n) for n in columns)
 sql='SELECT count(*) FROM((SELECT '+fields+' FROM '+quote(left)+' EXCEPT ALL SELECT '+fields+' FROM '+quote(right)+') UNION ALL(SELECT '+fields+' FROM '+quote(right)+' EXCEPT ALL SELECT '+fields+' FROM '+quote(left)+'))'
 need(run(con,sql,check=check).fetchone()[0]==0,'Exact source relation differs: '+left)


def _rank_popularity(con,check):
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_top AS SELECT *,row_number() OVER(ORDER BY popularity_distinct_users DESC,product_id) popular_source_rank
 FROM _hsa_pop QUALIFY popular_source_rank<=200''',check=check)


def _rank_recent(con,check):
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_recent AS SELECT *,row_number() OVER(PARTITION BY query_id ORDER BY last_user_event_time DESC,product_id) recent_source_rank
 FROM _hsa_recent_all QUALIFY recent_source_rank<=20''',check=check)


def _combine_candidates(con,check):
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_c AS WITH k AS(
 SELECT q.query_id,p.product_id FROM _hsa_q q CROSS JOIN _hsa_top p UNION SELECT query_id,product_id FROM _hsa_recent)
 SELECT k.query_id,k.product_id,p.product_id IS NOT NULL from_popular,r.product_id IS NOT NULL from_recent,
 coalesce(g.popularity_distinct_users,0)::BIGINT popularity_distinct_users,p.popular_source_rank,r.recent_source_rank,r.last_user_event_time
 FROM k LEFT JOIN _hsa_top p USING(product_id) LEFT JOIN _hsa_recent r USING(query_id,product_id) LEFT JOIN _hsa_pop g USING(product_id)''',check=check)


def _expected_qc(con,t,S,E,check):
 lo7=max(S,t-timedelta(days=7));lo48=max(S,t-timedelta(hours=48));serial=t.strftime('%Y-%m-%dT%H:%M:%SZ')
 run(con,"CREATE OR REPLACE TEMP VIEW _hsa_raw AS SELECT event_time,event_type,product_id,user_id,category_id FROM heldout_raw_events WHERE event_time>=TIMESTAMP '"+S.strftime('%Y-%m-%d %H:%M:%S')+"' AND event_time<TIMESTAMP '"+t.strftime('%Y-%m-%d %H:%M:%S')+"'",check=check)
 coverage=max(0,(min(t,E)-lo7).total_seconds())/(7*86400)
 mature=t+timedelta(days=1)<=E
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_q AS WITH eligible AS(
 SELECT user_id,sum(CASE WHEN event_time>=? AND event_type IN('view','cart','purchase') THEN 1 ELSE 0 END)::BIGINT eligibility_events,
 count(*)::BIGINT history_events_7d,count(DISTINCT product_id)::BIGINT history_distinct_items_7d,
 count(DISTINCT event_time::DATE)::BIGINT history_active_days_7d,max(event_time) last_history_time
 FROM _hsa_raw WHERE user_id IS NOT NULL AND event_time>=? GROUP BY user_id HAVING eligibility_events>0),
 picked AS(SELECT *,row_number() OVER(ORDER BY sha256(?||user_id::VARCHAR),user_id) sample_rank FROM eligible)
 SELECT sha256(?||user_id::VARCHAR) query_id,user_id,?::TIMESTAMP anchor,eligibility_events,history_events_7d,
 history_distinct_items_7d,history_active_days_7d,last_history_time,?::DOUBLE history_coverage_7d,?::BOOLEAN label_is_mature
 FROM picked WHERE sample_rank<=2000''',[lo48,lo7,'sample|2026|'+serial+'|','query|2026|'+serial+'|',t,coverage,mature],check=check)
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_pop AS SELECT product_id,count(DISTINCT user_id)::BIGINT popularity_distinct_users
 FROM _hsa_raw WHERE event_time>=? AND event_type='purchase' AND product_id IS NOT NULL AND user_id IS NOT NULL GROUP BY product_id''',[lo7],check=check)
 _rank_popularity(con,check)
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_recent_all AS SELECT q.query_id,e.product_id,max(e.event_time) last_user_event_time
 FROM _hsa_q q JOIN _hsa_raw e USING(user_id) WHERE e.event_time>=? AND e.product_id IS NOT NULL AND e.event_type IN('view','cart','purchase')
 GROUP BY q.query_id,e.product_id''',[lo7],check=check)
 _rank_recent(con,check);_combine_candidates(con,check)
 need(run(con,'SELECT count(*) FROM _hsa_c c WHERE NOT EXISTS(SELECT 1 FROM _hsa_raw e WHERE e.product_id=c.product_id)',check=check).fetchone()[0]==0,'Expected catalog is not strict past')
 run(con,'CREATE OR REPLACE TEMP VIEW _hsa_t AS SELECT c.query_id,c.product_id,q.user_id,q.anchor FROM _hsa_c c JOIN _hsa_q q USING(query_id)',check=check)
 for name,fields,source in [('du','user_id','_hsa_q'),('di','product_id','_hsa_t'),('dp','user_id,product_id','_hsa_t')]:
  run(con,'CREATE OR REPLACE TEMP TABLE _hsa_'+name+' AS SELECT DISTINCT '+fields+' FROM '+source,check=check)
 return mature


def _metadata(con,t,S,E,check):
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_i AS SELECT d.product_id,min(e.event_time) first_seen,max(e.event_time) last_seen
 FROM _hsa_di d LEFT JOIN _hsa_raw e USING(product_id) GROUP BY d.product_id''',check=check)
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_category AS SELECT i.product_id,
 CASE WHEN count(DISTINCT e.category_id)=1 AND count(*) FILTER(WHERE e.event_time IS NOT NULL AND e.category_id IS NULL)=0 THEN min(e.category_id) END candidate_category_id,
 (count(DISTINCT e.category_id)>1 OR(count(DISTINCT e.category_id)>0 AND count(*) FILTER(WHERE e.event_time IS NOT NULL AND e.category_id IS NULL)>0)) candidate_category_ambiguous
 FROM _hsa_i i LEFT JOIN _hsa_raw e ON e.product_id=i.product_id AND e.event_time=i.last_seen GROUP BY i.product_id''',check=check)
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_u AS SELECT d.user_id,min(e.event_time) first_seen
 FROM _hsa_du d LEFT JOIN _hsa_raw e USING(user_id) GROUP BY d.user_id''',check=check)
 cov=[max(0,(min(t,E)-max(S,t-timedelta(hours=w))).total_seconds())/(w*3600) for w in (24,168)]
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_meta AS SELECT p.*,c.candidate_category_id,c.candidate_category_ambiguous,
 c.candidate_category_id IS NULL candidate_category_missing,i.first_seen IS NOT NULL item_has_observed_history,u.first_seen IS NOT NULL user_has_observed_history,
 date_diff('microsecond',i.first_seen,?::TIMESTAMP)::DOUBLE/1000000 item_observed_age_seconds,
 date_diff('microsecond',u.first_seen,?::TIMESTAMP)::DOUBLE/1000000 user_observed_age_seconds,
 ?::DOUBLE source_coverage_24h,?::DOUBLE source_coverage_168h
 FROM _hsa_t p JOIN _hsa_i i USING(product_id) JOIN _hsa_category c USING(product_id) JOIN _hsa_u u USING(user_id)''',[t,t,*cov],check=check)


def _mismatch(con,actual,expected,fields,check,*,time_tolerance=None):
 conditions=[]
 for name,dtype in fields:
  a='a.'+quote(name);e='e.'+quote(name)
  if dtype=='DOUBLE':
   tolerance=str(time_tolerance) if time_tolerance is not None else 'greatest(1e-12,abs('+e+')*1e-12)'
   conditions.append('('+a+' IS NULL) IS DISTINCT FROM ('+e+' IS NULL) OR ('+a+' IS NOT NULL AND(NOT isfinite('+a+') OR abs('+a+'-'+e+')>'+tolerance+'))')
  else:conditions.append(a+' IS DISTINCT FROM '+e)
 sql='SELECT count(*) FROM '+quote(actual)+' a JOIN '+quote(expected)+' e USING(query_id,product_id) WHERE '+' OR '.join('('+c+')' for c in conditions)
 need(run(con,sql,check=check).fetchone()[0]==0,'Independent values differ: '+actual)


def _chosen(con,choice,t,S,check):
 fields=CHOSEN[choice]
 if not fields:return
 lo24=max(S,t-timedelta(days=1));lo7=max(S,t-timedelta(days=7))
 if choice=='I1':
  names=[n for n,_ in fields]
  expressions=','.join("count(e.event_type) FILTER(WHERE e.event_type='"+action+"')::BIGINT "+quote(n) for action,n in zip(('view','cart','purchase'),names))
  run(con,'CREATE OR REPLACE TEMP TABLE _hsa_values AS SELECT d.user_id,d.product_id,'+expressions+' FROM _hsa_dp d LEFT JOIN _hsa_raw e ON e.user_id=d.user_id AND e.product_id=d.product_id AND e.event_time>=? GROUP BY d.user_id,d.product_id',[lo24],check=check)
  join='JOIN _hsa_values v USING(user_id,product_id)'
 elif choice=='R1':
  expressions=','.join("count(e.event_type) FILTER(WHERE e.event_type='"+action+"')::BIGINT "+quote(n) for action,(n,_) in zip(('view','cart','purchase'),fields))
  run(con,'CREATE OR REPLACE TEMP TABLE _hsa_values AS SELECT d.user_id,'+expressions+' FROM _hsa_du d LEFT JOIN _hsa_raw e ON e.user_id=d.user_id AND e.event_time>=? GROUP BY d.user_id',[lo24],check=check)
  join='JOIN _hsa_values v USING(user_id)'
 elif choice=='R2':
  expressions=','.join("count(DISTINCT e.user_id) FILTER(WHERE e.event_type='"+action+"' AND e.event_time>=?)::BIGINT "+quote(n) for action,(n,_) in zip(('view','cart','purchase'),fields))
  run(con,'CREATE OR REPLACE TEMP TABLE _hsa_values AS SELECT d.product_id,'+expressions+' FROM _hsa_di d LEFT JOIN _hsa_raw e ON e.product_id=d.product_id AND e.event_time>=? GROUP BY d.product_id',[lo24,lo7,lo24,lo7],check=check)
  join='JOIN _hsa_values v USING(product_id)'
 else:
  run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_pair AS SELECT d.user_id,d.product_id,
 date_diff('microsecond',max(e.event_time) FILTER(WHERE e.event_type='cart'),?::TIMESTAMP)::DOUBLE/1000000 auto_pair_cart_recency_seconds_observed,
 (max(e.event_time) FILTER(WHERE e.event_type='cart') IS NULL) auto_pair_cart_recency_seconds_observed_missing
 FROM _hsa_dp d LEFT JOIN _hsa_raw e ON e.user_id=d.user_id AND e.product_id=d.product_id GROUP BY d.user_id,d.product_id''',[t],check=check)
  run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_values AS SELECT d.product_id,count(e.event_type) FILTER(WHERE e.event_type='cart')::BIGINT auto_item_cart_count_24h
 FROM _hsa_di d LEFT JOIN _hsa_raw e ON e.product_id=d.product_id AND e.event_time>=? GROUP BY d.product_id''',[lo24],check=check)
  join='JOIN _hsa_pair z USING(user_id,product_id) JOIN _hsa_values v USING(product_id)'
 prefix=lambda n:('z.' if choice=='I2' and n!='auto_item_cart_count_24h' else 'v.')+quote(n)
 run(con,'CREATE OR REPLACE TEMP VIEW _hsa_extra AS SELECT p.query_id,p.product_id,'+','.join(prefix(n) for n,_ in fields)+' FROM _hsa_t p '+join,check=check)
 equivalent(con,'_hsa_extra','_hsa_c',['query_id','product_id'],check)


def _structural_base(con,table,t,S,check):
 for n,g,_,op in CORE:
  column=quote(n);bad=column+'<0' if op!='recency' else '('+column+'<=0 OR '+column+'>?)'
  params=[(t-S).total_seconds()] if op=='recency' else []
  if op=='ratio':bad+=' OR '+column+'>1'
  if op in {'recency','ratio'}:bad+=' OR ('+column+' IS NOT NULL AND NOT isfinite('+column+'))'
  if 'category' in g and op=='count':bad+=' OR (candidate_category_missing IS DISTINCT FROM ('+column+' IS NULL))'
  elif 'category' not in g and op!='recency':bad+=' OR '+column+' IS NULL'
  if 'category' in g:bad+=' OR (candidate_category_missing AND '+column+' IS NOT NULL)'
  if n+'_missing' in FLAGS:bad+=' OR '+quote(n+'_missing')+' IS DISTINCT FROM ('+column+' IS NULL)'
  need(run(con,'SELECT count(*) FROM '+quote(table)+' WHERE '+bad,params,check=check).fetchone()[0]==0,'B18 structural NULL/range/mask: '+n)


def _sample_pairs(con,t,check):
 run(con,'''CREATE OR REPLACE TEMP TABLE _hsa_support AS SELECT p.query_id,p.product_id,
 coalesce(bool_or(e.event_type='view' AND e.event_time>=?),false) pair_view_support,
 coalesce(bool_or(e.event_type='purchase' AND e.event_time>=?),false) past_pair_purchase_support,
 max(e.event_time) FILTER(WHERE e.event_type='view') last_pair_view,max(e.event_time) FILTER(WHERE e.event_type='purchase') last_pair_purchase
 FROM _hsa_t p LEFT JOIN _hsa_raw e ON e.user_id=p.user_id AND e.product_id=p.product_id GROUP BY p.query_id,p.product_id''',[t-timedelta(days=7),t-timedelta(days=7)],check=check)
 run(con,'CREATE OR REPLACE TEMP TABLE _hsa_strata AS SELECT s.*,m.candidate_category_missing category_missing,m.candidate_category_ambiguous category_ambiguous,(last_pair_view<? OR last_pair_purchase<?) old_recency_support FROM _hsa_support s JOIN _hsa_meta m USING(query_id,product_id)',[t-timedelta(days=7),t-timedelta(days=7)],check=check)
 predicates={'bottom_hash':('true',4),'pair_view_support':('pair_view_support',1),'category_missing':('category_missing',1),
             'category_ambiguous':('category_ambiguous',1),'past_pair_purchase_support':('past_pair_purchase_support',1),'old_recency_support':('old_recency_support',1)}
 selected=set();strata={}
 for name,(predicate,limit) in predicates.items():
  available=run(con,'SELECT count(*) FROM _hsa_strata WHERE '+predicate,check=check).fetchone()[0]
  picked=run(con,"SELECT query_id,product_id FROM _hsa_strata WHERE "+predicate+" ORDER BY sha256(query_id||'|'||product_id::VARCHAR),query_id,product_id LIMIT ?",[limit],check=check).fetchall()
  selected.update(picked);strata[name]=dict(available_pairs=available,sampled_pairs=len(picked))
 return sorted(selected),strata


def _rows(con,sql,params,check):
 run(con,sql,params,check=check)
 while True:
  check();block=con.fetchmany(8192)
  if not block:break
  for row in block:yield row
 check()


def _sample_values(con,u,i,t,S,E,check):
 """Independent streaming row arithmetic, not compiler/grouped expected fields."""
 lo7=t-timedelta(days=7);lo24=t-timedelta(days=1)
 item_first=latest=None;cats=set();item_counts={'view':0,'purchase':0}
 for _,stamp,kind,cat in _rows(con,'SELECT user_id,event_time,event_type,category_id FROM _hsa_raw WHERE product_id=?',[i],check):
  item_first=stamp if item_first is None else min(item_first,stamp)
  if latest is None or stamp>latest:latest=stamp;cats={cat}
  elif stamp==latest:cats.add(cat)
  if stamp>=lo24 and kind in item_counts:item_counts[kind]+=1
 category=next(iter(cats)) if len(cats)==1 and None not in cats else None
 user_counts={a:0 for a in ('view','cart','purchase')};pair_counts=user_counts.copy();last_pair={'view':None,'purchase':None};first_user=None;ucount=0;u_last=None
 for pid,stamp,kind,cat in _rows(con,'SELECT product_id,event_time,event_type,category_id FROM _hsa_raw WHERE user_id=?',[u],check):
  first_user=stamp if first_user is None else min(first_user,stamp)
  if stamp>=lo7 and kind in user_counts:
   user_counts[kind]+=1
   if pid==i:pair_counts[kind]+=1
  if pid==i and kind in last_pair:last_pair[kind]=stamp if last_pair[kind] is None else max(last_pair[kind],stamp)
  if category is not None and kind=='view' and cat==category:
   if stamp>=lo7:ucount+=1
   u_last=stamp if u_last is None else max(u_last,stamp)
 scalar=lambda sql,args:run(con,sql,args,check=check).fetchone()[0]
 udist=scalar("SELECT count(DISTINCT product_id) FROM _hsa_raw WHERE user_id=? AND event_type='view' AND event_time>=?",[u,lo7])
 idist=scalar("SELECT count(DISTINCT user_id) FROM _hsa_raw WHERE product_id=? AND event_type='view' AND event_time>=?",[i,lo7])
 icount=scalar("SELECT count(*) FROM _hsa_raw WHERE product_id=? AND category_id=? AND event_type='view' AND event_time>=?",[i,category,lo7]) if category is not None else None
 ccount=scalar("SELECT count(*) FROM _hsa_raw WHERE category_id=? AND event_type='view' AND event_time>=?",[category,lo7]) if category is not None else None
 rec=lambda stamp:None if stamp is None else (t-stamp).total_seconds()
 values={}
 for a in user_counts:values['user_'+a+'_7d']=user_counts[a];values['pair_'+a+'_7d']=pair_counts[a]
 values.update(user_distinct_viewed_items_7d=udist,pair_view_recency_seconds=rec(last_pair['view']),pair_purchase_recency_seconds=rec(last_pair['purchase']),
  item_view_24h=item_counts['view'],item_purchase_24h=item_counts['purchase'],item_distinct_viewers_7d=idist,
  user_category_view_7d=ucount if category is not None else None,user_category_view_recency_seconds=rec(u_last) if category is not None else None,
  item_category_view_7d=icount,category_view_7d=ccount,
  user_category_view_share_7d=ucount/user_counts['view'] if category is not None and user_counts['view'] else None,
  item_category_view_share_7d=icount/ccount if ccount else None)
 values.update(candidate_category_id=category,candidate_category_ambiguous=len(cats)>1,candidate_category_missing=category is None,
  item_has_observed_history=item_first is not None,user_has_observed_history=first_user is not None,
  item_observed_age_seconds=rec(item_first),user_observed_age_seconds=rec(first_user))
 for w in (24,168):values['source_coverage_'+str(w)+'h']=max(0,(min(t,E)-max(S,t-timedelta(hours=w))).total_seconds())/(w*3600)
 values.update({n:values[n[:-8]] is None for n in FLAGS})
 return values


def _same_value(expected,actual,field):
 if expected is None:ok=actual is None
 elif type(expected) in (bool,int):ok=type(actual) is type(expected) and actual==expected
 else:ok=type(actual) in (int,float) and math.isfinite(actual) and math.isclose(expected,actual,rel_tol=1e-12,abs_tol=1e-12)
 need(ok,'Sampled B18/source value differs: '+field)


def _validate_record(row,choice):
 h.keys(row,DAY_FIELDS,'Produced source day')
 need(row['anchor'] in h.DAYS,'Only fixed seven source dates supported')
 for n in ('queries','candidates','base_features'):h.ref(row[n])
 if choice=='B':need(row['extra_features'] is None,'B choice must have zero extra columns')
 else:h.ref(row['extra_features'])
 h.integer(row['query_count'],0,2000,'Daily queries');h.integer(row['candidate_count'],0,row['query_count']*220,'Daily candidates')
 need(type(row['mature_query_count']) is int and row['mature_query_count']==row['query_count'],'Calendar maturity differs')


def _choice(lock,authenticated_choice):
 locked=h.validate_lock(lock,authenticated_choice=authenticated_choice)
 need(locked['models']['B']['feature_names']==B_MODEL,'Unsupported B41 order/registry')
 need(locked['models']['W']['feature_names']==B_MODEL+[n for n,_ in CHOSEN[locked['choice']]],'Unsupported chosen3 order/semantics')
 return locked


def _audit_day(con,row,locked,relations,check):
 check();_validate_record(row,locked['choice'])
 keys={'queries','candidates','base_features','extra_features'}
 h.keys(relations,keys,'Output relation provider')
 for key,name in relations.items():
  if key=='extra_features' and locked['choice']=='B':need(name is None,'No extra relation for B');continue
  quote(name);need(not name.startswith('_hsa_') and name!='heldout_raw_events','Output cannot alias expected/source relation')
 names=[v for v in relations.values() if v is not None];need(len(set(names))==len(names),'Output relation aliases forbidden')
 need(run(con,"SELECT current_setting('threads')",check=check).fetchone()[0]==2,'Caller must supply two-thread bounded private connection')
 raw={r[0]:r[1] for r in run(con,'DESCRIBE heldout_raw_events',check=check).fetchall()}
 need(all(raw.get(n)==t for n,t in [('event_time','TIMESTAMP'),('event_type','VARCHAR'),('product_id','BIGINT'),('user_id','BIGINT'),('category_id','BIGINT')]),'Raw source exact typed adapter required')
 q,c,b=(relations[n] for n in ('queries','candidates','base_features'));extra=relations['extra_features'];choice=locked['choice']
 schema(con,q,Q_SCHEMA,check);schema(con,c,C_SCHEMA,check);schema(con,b,B_SCHEMA,check)
 if extra:schema(con,extra,[('query_id','VARCHAR'),('product_id','BIGINT')]+CHOSEN[choice],check)
 t=h.utc(row['anchor']).replace(tzinfo=None);S=h.utc(locked['policy']['source']['start']).replace(tzinfo=None);E=h.utc(locked['policy']['source']['end']).replace(tzinfo=None)
 mature=_expected_qc(con,t,S,E,check)
 equivalent(con,q,'_hsa_q',[n for n,_ in Q_SCHEMA],check)
 equivalent(con,c,'_hsa_c',[n for n,_ in C_SCHEMA],check)
 actual_q=run(con,'SELECT count(*) FROM '+quote(q),check=check).fetchone()[0];actual_c=run(con,'SELECT count(*) FROM '+quote(c),check=check).fetchone()[0]
 need(actual_q==row['query_count'] and actual_c==row['candidate_count'] and row['mature_query_count']==(actual_q if mature else 0),'Produced source counts differ from source truth')
 equivalent(con,b,'_hsa_c',[n for n,_ in C_SCHEMA],check)
 need(run(con,'SELECT count(*) FROM '+quote(b)+' f JOIN _hsa_q q USING(query_id) WHERE f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor',check=check).fetchone()[0]==0,'B45 source Q identity differs')
 _metadata(con,t,S,E,check)
 _mismatch(con,b,'_hsa_meta',METADATA+COVERAGE,check)
 _structural_base(con,b,t,S,check)
 if extra:
  equivalent(con,extra,'_hsa_c',['query_id','product_id'],check);_chosen(con,choice,t,S,check)
  _mismatch(con,extra,'_hsa_extra',CHOSEN[choice],check,time_tolerance=1e-9)
 pairs,strata=_sample_pairs(con,t,check)
 for qid,pid in pairs:
  fields=[n for n,_ in B_SCHEMA]
  actual_values=run(con,'SELECT * FROM '+quote(b)+' WHERE query_id=? AND product_id=?',[qid,pid],check=check).fetchone()
  actual=dict(zip(fields,actual_values));expected=_sample_values(con,actual['user_id'],pid,t,S,E,check)
  for name,value in expected.items():_same_value(value,actual[name],name)
 qids=[v[0] for v in run(con,'SELECT query_id FROM _hsa_q ORDER BY query_id',check=check).fetchall()]
 empty=run(con,'SELECT count(*) FROM _hsa_q q WHERE NOT EXISTS(SELECT 1 FROM _hsa_c c WHERE c.query_id=q.query_id)',check=check).fetchone()[0]
 check()
 return dict(anchor=row['anchor'],query_count=actual_q,candidate_count=actual_c,mature_query_count=row['mature_query_count'],
  empty_candidate_queries=empty,chosen_columns=len(CHOSEN[choice]),chosen_scalar_values=actual_c*len(CHOSEN[choice]),
  source_Q_C_complete=True,metadata_ages_coverage_complete=True,chosen_formula_values_complete=True,
  base_core18_sample_pairs=len(pairs),base_core18_comparisons=18*len(pairs),strata=strata,
  base_proof_scope='all_structure_metadata_coverage_core18_sampled',baseline_formula_values_complete=False,
  labels_loaded=False,target_relation_created=False,fit_attempt_count=0,native_prediction_count=0),qids


def audit_day(con,row,lock,*,authenticated_choice,relations,check=lambda:None):
 """One produced day checked; this does not prove whole-period completeness."""
 check();locked=_choice(lock,authenticated_choice)
 result,_=_audit_day(con,deepcopy(row),locked,deepcopy(relations),check)
 return result


def audit_source(con,lock,*,authenticated_choice,days,load_day,check=lambda:None):
 """Check exact seven supplied day records through a trusted relation provider.

 Caller authenticates refs and source/code bytes and owns resource lifetime.
 load_day(con,day) exposes Q/C/B45/extra relations; no default file/Y loader exists.
 """
 check();locked=_choice(lock,authenticated_choice)
 need(type(days) is list and len(days)==7,'Exactly seven physical day records required')
 copied=deepcopy(days);by_day={}
 for row in copied:
  _validate_record(row,locked['choice']);need(row['anchor'] not in by_day,'Repeated source day');by_day[row['anchor']]=row
 need(set(by_day)==set(h.DAYS) and callable(load_day),'Complete calendar and explicit provider required')
 reports=[];qids=set()
 for anchor in h.DAYS:
  check();row=by_day[anchor];relations=load_day(con,deepcopy(row));check()
  report,local_ids=_audit_day(con,row,locked,relations,check)
  need(not(qids&set(local_ids)),'Query ID repeated across source partitions');qids.update(local_ids);reports.append(report)
 check();pairs=sum(r['candidate_count'] for r in reports);columns=len(CHOSEN[locked['choice']])
 return dict(version=1,status='source_core_checked_pending_external_acceptance',scope='independent_reserved_source_core',choice=locked['choice'],
  checked_days=list(h.DAYS),days=reports,verified_outputs=copied,source_Q_C_domain_complete=True,
  chosen_columns=columns,chosen_scalar_values=pairs*columns,chosen_formula_values_complete=True,
  extra_proof_scope='no_extras_W_equals_B' if columns==0 else 'all_selected3_values_every_C_row',
  base_proof_scope='all_structure_metadata_coverage_core18_sampled',baseline_formula_values_complete=False,
  base_core18_sample_pairs=sum(r['base_core18_sample_pairs'] for r in reports),base_core18_comparisons=sum(r['base_core18_comparisons'] for r in reports),
  query_count=len(qids),candidate_count=pairs,mismatch_count=0,labels_loaded=False,target_relation_created=False,fit_attempt_count=0,native_prediction_count=0,
  proof_limits='Pure caller-owned connection core; refs/source/code/lifetime are authenticated externally. Q/C and metadata/coverage/chosen0or3 values exhaustive; new-date core18 numeric values sampled. No files, models, Y, target capability, approval or resource allowance.')
