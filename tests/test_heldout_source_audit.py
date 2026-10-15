"""Synthetic only: largest raw fixture21 rows; separate201 count-only ordering input."""
from copy import deepcopy
from datetime import datetime,timedelta
import unittest
from unittest.mock import patch
import duckdb
from tests.test_heldout_source import definitions, ROWS, T, BIG
from scripts import heldout_source as producer
from tests.oracles import heldout_source_audit as m
from types import SimpleNamespace

# Literal accepted-v1 comparison kernel, preserved independently of v2.
ACCEPTED_V1_SOURCE_SHA256='056f9b73eca546552b782141c9c37ba060bd1ba5fc75890b48a35b937ddf81cd'
ACCEPTED_V1_KERNEL_TEXT_SHA256='1cb8255acaa3ccd9b6574b8d26c45aa20bc5afff04c52a82d71bc7ac52802688'
# These transport/constant helpers have unchanged v1/v2 AST/values.
_rows=m._rows
run=m.run
FLAGS=m.FLAGS

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

v1=SimpleNamespace(_sample_values=_sample_values)

RAW=ROWS+[(T-timedelta(hours=2),'view',30,77,None),(T-timedelta(hours=2),'view',30,None,None),
 (T-timedelta(hours=2),'view',None,88,None),(T-timedelta(hours=24),'view',10,1,100),
 (T-timedelta(minutes=10),'cart',20,None,None),(T-timedelta(days=3),'cart',20,99,None),
 (T-timedelta(hours=2),'purchase',30,3,300),(T-timedelta(days=3),'view',999,99,100),(T-timedelta(hours=1),'other',91,1,100),(datetime(2019,10,2),'view',10,1,100),(datetime(2019,10,3),'purchase',10,1,100)]

class SourceAudit(unittest.TestCase):
 def setUp(self):
  self.con=duckdb.connect(':memory:');self.con.execute('SET threads=2');self.con.execute("SET memory_limit='128MB'");self.con.execute("SET max_temp_directory_size='0B'")
  self.con.execute('CREATE TABLE heldout_raw_events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
 def tearDown(self):self.con.close()
 def insert(self,rows=RAW):
  self.assertLessEqual(len(rows),32)
  if rows:self.con.executemany('INSERT INTO heldout_raw_events VALUES (?,?,?,?,?)',rows)
 def build(self,choice='I1',day=25,tag='actual'):
  pool,lock,auth=definitions(choice);r=producer.build_day(self.con,f'2019-10-{day:02d}T00:00:00Z',pool,lock,authenticated_choice=auth)
  tables={'queries':'pilot_queries','candidates':'pilot_candidates','base_features':'heldout_base_features','extra_features':None if choice=='B' else 'heldout_extra_features'};relations={}
  for key,table in tables.items():
   relations[key]=None if table is None else tag+'_'+key
   if table:self.con.execute('CREATE OR REPLACE TEMP TABLE '+relations[key]+' AS SELECT * FROM '+table)
  ref=lambda key:dict(path=tag+'/'+key,sha256='a'*64)
  row=dict(anchor=f'2019-10-{day:02d}T00:00:00Z',queries=ref('q'),candidates=ref('c'),base_features=ref('b'),extra_features=None if choice=='B' else ref('extra'),query_count=r['query_count'],candidate_count=r['candidate_count'],mature_query_count=r['mature_query_count'])
  return row,lock,auth,relations
 def audit(self,args,**kwargs):
  row,lock,auth,tables=args;return m.audit_day(self.con,row,lock,authenticated_choice=auth,relations=tables,**kwargs)
 def test_all_choices_independent_literal_gold_and_bigint(self):
  self.insert()
  gold={'I1':(3,0,0),'I2':((T-datetime(2019,10,1)).total_seconds(),0,False),'R1':(3,0,0),'R2':(1,0,0)}
  for choice in ['B','I1','I2','R1','R2']:
   with self.subTest(choice=choice):
    args=self.build(choice);r=self.audit(args);self.assertEqual(r['chosen_columns'],0 if choice=='B' else 3)
    self.assertFalse(r['baseline_formula_values_complete']);self.assertEqual(r['fit_attempt_count'],0)
    self.assertEqual(self.con.execute('SELECT category_view_7d FROM actual_base_features WHERE user_id=1 AND product_id=10').fetchone(),(5,))
    self.assertIn((BIG,),self.con.execute('SELECT product_id FROM actual_candidates').fetchall())
    if choice!='B':
     fields=','.join(n for n,_ in m.CHOSEN[choice]);actual=self.con.execute('SELECT '+fields+' FROM actual_extra_features JOIN actual_queries USING(query_id) WHERE user_id=1 AND product_id=10').fetchone();self.assertEqual(actual,gold[choice])
  self.assertEqual(self.con.execute('SELECT auto_item_cart_count_distinct_168h_user_id FROM actual_extra_features WHERE product_id=20 LIMIT 1').fetchone(),(2,))
 def test_fullprefix_old_recency_and_nonaction_history_diagnostics(self):
  self.insert();args=self.build();r=self.audit(args)
  self.assertEqual(self.con.execute('SELECT pair_purchase_recency_seconds FROM actual_base_features WHERE user_id=1 AND product_id=10').fetchone(),((T-datetime(2019,10,3)).total_seconds(),))
  self.assertGreater(r['strata']['old_recency_support']['available_pairs'],0)
  # One unrelated action remains in raw history diagnostics, not eligibility or action counts.
  self.assertEqual(self.con.execute('SELECT eligibility_events,history_events_7d,history_distinct_items_7d FROM actual_queries WHERE user_id=1').fetchone(),(4,5,2))
 def test_bad_locked_schema_rejected_before_first_SQL(self):
  args=self.build();args[1]['models']['B']['feature_names'][0]='unapproved'
  class NoSQL:
   def execute(self,*a,**k):raise AssertionError('must reject authority first')
  with self.assertRaises(ValueError):m.audit_day(NoSQL(),args[0],args[1],authenticated_choice=args[2],relations=args[3])
 def test_global_latest_all_peers_ambiguity_and_category_move(self):
  self.insert();args=self.build('I2');self.audit(args)
  self.assertEqual(self.con.execute('SELECT candidate_category_missing,candidate_category_ambiguous FROM actual_base_features WHERE user_id=3 AND product_id=30').fetchone(),(True,True))
  self.assertEqual(self.con.execute('SELECT auto_item_cart_count_24h FROM actual_extra_features WHERE product_id=20 LIMIT 1').fetchone(),(2,))
  args=self.build('I1',26);self.audit(args)
  self.assertEqual(self.con.execute('SELECT candidate_category_id,user_category_view_7d,category_view_7d FROM actual_base_features WHERE user_id=1 AND product_id=10').fetchone(),(999,0,1))
 def test_future_suffix_and_lawful25_history26(self):
  self.insert(ROWS[:7]);args=self.build();self.audit(args);before=self.con.execute('SELECT * FROM actual_candidates ORDER BY query_id,product_id').fetchall()
  self.insert(ROWS[7:]);self.audit(args);self.assertEqual(self.con.execute('SELECT * FROM _hsa_c ORDER BY query_id,product_id').fetchall(),before)
  args=self.build(day=26);self.audit(args);self.assertIn((4,),self.con.execute('SELECT user_id FROM _hsa_q').fetchall());self.assertIn((5,),self.con.execute('SELECT user_id FROM _hsa_q').fetchall())
 def test_all_empty_and_eligible_empty_C(self):
  args=self.build();r=self.audit(args);self.assertEqual((r['query_count'],r['candidate_count']),(0,0))
  self.insert([(T-timedelta(hours=1),'view',None,BIG,None)]);args=self.build('R1');r=self.audit(args);self.assertEqual((r['query_count'],r['candidate_count'],r['empty_candidate_queries']),(1,0,1))
 def test_fullseven_calendar_partition_cover_and_noY(self):
  self.insert();days=[];tables={};lock=auth=None
  for day in range(25,32):
   row,lock,auth,relations=self.build('I2',day,'d'+str(day));days.append(row);tables[row['anchor']]=relations
  self.con.execute("CREATE VIEW forbidden_Y AS SELECT error('target read forbidden') x")
  def provider(con,row):return tables[row['anchor']]
  r=m.audit_source(self.con,lock,authenticated_choice=auth,days=list(reversed(days)),load_day=provider)
  self.assertEqual(r['checked_days'],list(m.h.DAYS));self.assertEqual(r['chosen_scalar_values'],3*r['candidate_count']);self.assertFalse(r['labels_loaded']);self.assertFalse(r['baseline_formula_values_complete'])
  with self.assertRaises(ValueError):m.audit_source(self.con,lock,authenticated_choice=auth,days=days[:-1]+[days[0]],load_day=provider)
 def test_jointQC_F_omission_updated_counts_and_refs_rejected(self):
  self.insert();args=self.build();row,_,_,tables=args;qid=self.con.execute('SELECT query_id FROM actual_queries LIMIT 1').fetchone()[0]
  for table in tables.values():self.con.execute('DELETE FROM '+table+' WHERE query_id=?',[qid])
  row['query_count']-=1;row['mature_query_count']-=1;row['candidate_count']=self.con.execute('SELECT count(*) FROM actual_candidates').fetchone()[0]
  for key in ['queries','candidates','base_features','extra_features']:row[key]['sha256']='b'*64
  with self.assertRaisesRegex(ValueError,'Exact source relation'):self.audit(args)
 def test_one_broadcast_legal_chosen_count_mutation_rejected(self):
  self.insert();args=self.build();pair=self.con.execute('SELECT query_id,product_id FROM actual_extra_features LIMIT 1').fetchone();self.con.execute('UPDATE actual_extra_features SET auto_pair_view_count_24h=auto_pair_view_count_24h+1 WHERE query_id=? AND product_id=?',pair)
  with self.assertRaisesRegex(ValueError,'Independent values'):self.audit(args)
 def test_metadata_coverage_and_mask_faults_rejected(self):
  self.insert();args=self.build('I2')
  for sql in ['UPDATE actual_base_features SET item_observed_age_seconds=item_observed_age_seconds+1', 'UPDATE actual_base_features SET source_coverage_168h=0.5','UPDATE actual_extra_features SET auto_pair_cart_recency_seconds_observed_missing=NOT auto_pair_cart_recency_seconds_observed_missing']:
   self.con.execute('BEGIN');self.con.execute(sql)
   try:
    with self.assertRaises(ValueError):self.audit(args)
   finally:self.con.execute('ROLLBACK')
 def test_category_grain_counts_sample_wrong_value_rejected(self):
  self.insert();args=self.build();self.audit(args);pair=self.con.execute("SELECT query_id,product_id FROM _hsa_strata WHERE NOT category_missing ORDER BY sha256(query_id||'|'||product_id::VARCHAR),query_id,product_id LIMIT 1").fetchone()
  self.con.execute('UPDATE actual_base_features SET user_category_view_7d=user_category_view_7d+1 WHERE query_id=? AND product_id=?',pair)
  # Force this same sourced pair into an independent sample call to test formula arithmetic.
  with patch.object(m,'_sample_pairs',return_value=([pair],{})):
   with self.assertRaisesRegex(ValueError,'Sampled B18'):self.audit(args)
 def test_sample_boundary_is_explicit_not_fullB_formula_claim(self):
  self.insert([(T-timedelta(hours=1),'purchase',i,i,100) for i in range(10)]);args=self.build();r=self.audit(args)
  sampled,_=m._sample_pairs(self.con,T,lambda:None);pair=next(p for p in self.con.execute('SELECT query_id,product_id FROM actual_candidates').fetchall() if p not in sampled)
  self.con.execute('UPDATE actual_base_features SET pair_cart_7d=pair_cart_7d+1 WHERE query_id=? AND product_id=?',pair)
  r=self.audit(args);self.assertFalse(r['baseline_formula_values_complete']);self.assertLess(r['base_core18_sample_pairs'],r['candidate_count'])
 def test_expected_does_not_call_producer_or_compiler(self):
  self.insert();args=self.build()
  with patch('scripts.anchor_pilot.create_queries',side_effect=AssertionError('producer')),patch('scripts.candidate_pilot.create_candidates',side_effect=AssertionError('producer')),patch('scripts.manual_features.create_manual_features',side_effect=AssertionError('compiler'),create=True),patch.object(producer,'generated_schema',side_effect=AssertionError('producer'),create=True):
   self.audit(args)
 def test_guard_before_engine_and_caller_connection_retained(self):
  args=self.build()
  with self.assertRaises(TimeoutError):self.audit(args,check=lambda:(_ for _ in ()).throw(TimeoutError('stop')))
  self.assertEqual(self.con.execute('SELECT 42').fetchone(),(42,))
  calls=[0]
  def guard():
   calls[0]+=1
   if calls[0]>30:raise TimeoutError('mid-sql stop')
  with self.assertRaises(TimeoutError):self.audit(args,check=guard)
 def test_no_file_IO_and_input_snapshots_unchanged(self):
  self.insert();args=self.build();before=deepcopy(args)
  with patch('builtins.open',side_effect=AssertionError('file read')),patch('io.open',side_effect=AssertionError('file read')):self.audit(args)
  self.assertEqual(args,before)
 def test_strict_typed_keys_bad_schema_alias_and_maturity(self):
  self.insert();args=self.build();bad=deepcopy(args);bad[0]['mature_query_count']=False
  with self.assertRaises(ValueError):self.audit(bad)
  bad=deepcopy(args);bad[3]['queries']='_hsa_q'
  with self.assertRaises(ValueError):self.audit(bad)
  self.con.execute('ALTER TABLE actual_candidates ALTER product_id TYPE DOUBLE')
  with self.assertRaisesRegex(ValueError,'schema'):self.audit(args)
 def test_duplicate_orphan_rows_and_Q_diagnostics_rejected(self):
  self.insert();args=self.build()
  for table in ['actual_candidates','actual_base_features','actual_extra_features']:
   self.con.execute('BEGIN');self.con.execute('INSERT INTO '+table+' SELECT * FROM '+table+' LIMIT 1')
   try:
    with self.assertRaises(ValueError):self.audit(args)
   finally:self.con.execute('ROLLBACK')
  self.con.execute('UPDATE actual_queries SET history_events_7d=history_events_7d+1')
  with self.assertRaises(ValueError):self.audit(args)
 def test_literal200_20_saturation_overlap_no_refill_count_only(self):
  #201 preaggregated counts; NOT201 raw events or a source-integration saturation proof.
  self.con.execute('CREATE TEMP TABLE _hsa_pop AS SELECT range::BIGINT product_id,1::BIGINT popularity_distinct_users FROM range(201)')
  self.con.execute("CREATE TEMP TABLE _hsa_q AS SELECT 'q'::VARCHAR query_id")
  self.con.execute("CREATE TEMP TABLE _hsa_recent_all AS SELECT 'q'::VARCHAR query_id,product_id,TIMESTAMP '2019-10-24 00:00:00' last_user_event_time FROM _hsa_pop WHERE product_id<=20")
  m._rank_popularity(self.con,lambda:None);m._rank_recent(self.con,lambda:None);m._combine_candidates(self.con,lambda:None)
  self.assertEqual(self.con.execute('SELECT min(product_id),max(product_id),count(*) FROM _hsa_top').fetchone(),(0,199,200));self.assertEqual(self.con.execute('SELECT min(product_id),max(product_id),count(*) FROM _hsa_recent').fetchone(),(0,19,20));self.assertEqual(self.con.execute('SELECT count(*),count(*) FILTER(WHERE from_recent) FROM _hsa_c').fetchone(),(200,20))


class BatchSampleTests(unittest.TestCase):
 setUp=SourceAudit.setUp
 tearDown=SourceAudit.tearDown
 insert=SourceAudit.insert
 build=SourceAudit.build
 audit=SourceAudit.audit
 def compare(self,choice='I1',day=25):
  args=self.build(choice,day);self.audit(args)
  t=T+timedelta(days=day-25);S=datetime(2019,10,1);E=datetime(2019,11,1)
  pairs,_=m._sample_pairs(self.con,t,lambda:None)
  batch=m._sample_values_batch(self.con,pairs,t,S,E,lambda:None)
  users=dict(self.con.execute('SELECT query_id,user_id FROM _hsa_q').fetchall())
  for q,i in pairs:self.assertEqual(batch[(q,i)],v1._sample_values(self.con,users[q],i,t,S,E,lambda:None))
  return batch
 def test_every_sample_field_equal_accepted_v1_allchoices_and_dates(self):
  self.insert()
  for choice in ['B','I1','I2','R1','R2']:
   for day in [25,26,31]:
    with self.subTest(choice=choice,day=day):self.compare(choice,day)
 def test_exact_NULL_distinct_and_raw_multiplicity_literal(self):
  self.insert([(T-timedelta(hours=1),'view',None,1,9),(T-timedelta(hours=1),'view',1,1,9),(T-timedelta(hours=1),'view',1,1,9),(T-timedelta(hours=1),'view',1,None,9),(T-timedelta(hours=1),'view',1,2,9),(T-timedelta(minutes=1),'cart',1,1,9)])
  values=self.compare();qid=self.con.execute('SELECT query_id FROM _hsa_q WHERE user_id=1').fetchone()[0];v=values[(qid,1)]
  self.assertEqual((v['user_view_7d'],v['user_distinct_viewed_items_7d'],v['item_view_24h'],v['item_distinct_viewers_7d'],v['category_view_7d']),(3,1,4,2,5))
 def test_late_latest_category_requires_all_history_category_maps(self):
  self.insert([(T-timedelta(days=10),'view',1,1,777),(T-timedelta(hours=3),'view',1,1,777),(T-timedelta(hours=2),'view',1,1,9),(T-timedelta(minutes=1),'cart',1,7,777),(T-timedelta(hours=4),'view',99,99,777)])
  values=self.compare('I2');qid=self.con.execute('SELECT query_id FROM _hsa_q WHERE user_id=1').fetchone()[0];v=values[(qid,1)]
  self.assertEqual((v['candidate_category_id'],v['user_category_view_7d'],v['user_category_view_recency_seconds'],v['item_category_view_7d'],v['category_view_7d']),(777,1,10800.0,1,2))
 def test_mixed_latest_NULL_ties_and_known_empty_category(self):
  self.insert([(T-timedelta(hours=2),'purchase',1,1,9),(T-timedelta(hours=1),'cart',1,1,9),(T-timedelta(hours=1),'cart',1,2,None),(T-timedelta(hours=1),'cart',2,3,8)])
  values=self.compare('I2');unknown=[v for (_,i),v in values.items() if i==1];self.assertTrue(unknown);self.assertTrue(all(v['candidate_category_ambiguous'] and v['user_category_view_7d'] is None for v in unknown))
  zero=[v for (_,i),v in values.items() if i==2];self.assertTrue(zero);self.assertTrue(all(v['category_view_7d']==0 and v['item_category_view_share_7d'] is None for v in zero))
 def test_future_suffix_and_prefix_recency_v1_equality(self):
  self.insert(ROWS[:7]);before=self.compare('I2');self.insert(ROWS[7:]);after=self.compare('I2');self.assertEqual(before,after)
  self.assertTrue(any(v['pair_purchase_recency_seconds'] is None for v in after.values()))
 def test_single_stream_plus_single_global_denominator_shape(self):
  self.insert();args=self.build();self.audit(args);pairs,_=m._sample_pairs(self.con,T,lambda:None);statements=[]
  class Recording:
   def __init__(inner,con):inner.con=con
   def execute(inner,sql,params=()):statements.append(sql);return inner.con.execute(sql,params)
   def __getattr__(inner,name):return getattr(inner.con,name)
  m._sample_values_batch(Recording(self.con),pairs,T,datetime(2019,10,1),datetime(2019,11,1),lambda:None)
  self.assertEqual(len(statements),3) # expected-Q lookup, one raw tuple stream, one category aggregate
  self.assertEqual(sum('SELECT user_id,product_id,event_time,event_type,category_id FROM _hsa_raw' in s for s in statements),1)
  self.assertEqual(sum("SELECT category_id,count(*)::BIGINT FROM _hsa_raw" in s for s in statements),1)
 def test_empty_pairs_do_no_SQL_and_unknown_domain_rejects(self):
  class NoSQL:
   def execute(self,*a,**kw):raise AssertionError('empty sample must not query')
  self.assertEqual(m._sample_values_batch(NoSQL(),[],T,T,T,lambda:None),{})
  args=self.build();self.audit(args)
  with self.assertRaisesRegex(ValueError,'outside expected Q'):m._sample_values_batch(self.con,[('unknown',1)],T,datetime(2019,10,1),datetime(2019,11,1),lambda:None)
 def test_kernel_guard_abort_and_no_raw_row_cache_source_contract(self):
  self.insert();args=self.build();self.audit(args);pairs,_=m._sample_pairs(self.con,T,lambda:None);n=[0]
  def stop():
   n[0]+=1
   if n[0]==5:raise TimeoutError('stream interrupted')
  with self.assertRaises(TimeoutError):m._sample_values_batch(self.con,pairs,T,datetime(2019,10,1),datetime(2019,11,1),stop)
  import inspect
  source=inspect.getsource(m._sample_values_batch)
  self.assertNotIn('list(_rows',source);self.assertNotIn('fetchall()',source.split('for u,i,stamp,kind,cat in _rows',1)[1].split('clean=',1)[0])

if __name__=='__main__':unittest.main()
