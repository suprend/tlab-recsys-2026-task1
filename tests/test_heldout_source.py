from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import json,unittest
from unittest.mock import patch
import duckdb
from scripts import feature_programs as p
from tests.test_heldout_contract import fixture
from scripts import heldout_source as m
ROOT=Path(__file__).resolve().parents[1]
T=datetime(2019,10,25);BIG=2**53+1
ROWS=[
 (datetime(2019,10,1),'cart',10,1,100),
 (T-timedelta(hours=48),'view',10,1,100),
 (T-timedelta(hours=1),'view',10,1,100),
 (T-timedelta(hours=1),'view',10,1,100),
 (T-timedelta(minutes=10),'cart',20,2,None),
 (T-timedelta(hours=2),'purchase',30,3,300),
 (T-timedelta(minutes=1),'view',BIG,BIG,500),
 (T,'purchase',40,4,400),
 (T,'view',10,6,999),
 (T+timedelta(hours=1),'purchase',50,5,500)]

def definitions(choice):
 contract=json.loads((ROOT/'configs/features/automation-pool.json').read_text());base=json.loads((ROOT/'configs/features/manual-18.json').read_text());pool=p.generate_pool(contract,base)
 lock,c,*_=fixture(choice);names=[f['name'] for f in pool['identity']['base_model_schema']];lock['models']['B']['feature_names']=names
 if choice=='B':lock['models']['W']=deepcopy(lock['models']['B'])
 else:
  allocation=p.allocate_slots(pool);slot=next(r for r in allocation['identity']['slots'] if r['slot']==choice);bundle=next(b for b in pool['identity']['bundles'] if b['bundle_id']==slot['bundle_id']);lock['models']['W']['feature_names']=bundle['model_feature_order']
 c['models']=deepcopy(lock['models']);return pool,lock,c


class HeldoutSource(unittest.TestCase):
 def setUp(self):
  self.con=duckdb.connect(':memory:');self.con.execute('SET threads=2');self.con.execute("SET memory_limit='128MB'");self.con.execute("SET max_temp_directory_size='0B'")
  self.con.execute('CREATE TABLE heldout_raw_events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
 def tearDown(self):self.con.close()
 def rows(self,rows=ROWS):
  if rows:self.con.executemany('INSERT INTO heldout_raw_events VALUES (?,?,?,?,?)',rows)
 def build(self,day=25,choice='I1',**kw):
  pool,l,c=definitions(choice);return m.build_day(self.con,f'2019-10-{day:02d}T00:00:00Z',pool,l,authenticated_choice=c,**kw)
 def snapshot(self):
  q=self.con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM pilot_queries ORDER BY query_id').fetchall()
  f=self.con.execute('SELECT * FROM manual_features ORDER BY query_id,product_id').fetchall();return q,f
 def test_exact48h_anchor_global_peers_raw_bag_and_bigint(self):
  self.rows();result=self.build();users={r[0] for r in self.con.execute('SELECT user_id FROM pilot_queries').fetchall()}
  self.assertEqual(users,{1,2,3,BIG});self.assertEqual(result['query_count'],4);self.assertEqual(len(result['base_schema']),45);self.assertEqual(len(result['extra_schema']),3)
  actual=self.con.execute('SELECT candidate_category_id,auto_pair_view_count_24h,category_view_7d FROM manual_features WHERE user_id=1 AND product_id=10').fetchone()
  self.assertEqual(actual,(100,2,3));self.assertIn((BIG,),self.con.execute('SELECT product_id FROM heldout_base_features').fetchall())
  self.assertEqual(self.con.execute('SELECT count(*) FROM events WHERE event_time>=?', [T]).fetchone()[0],0)
 def test_future_suffix_and_peer_permutation_do_not_change_same_day(self):
  self.rows(ROWS[:7]);self.build();before=self.snapshot()
  self.rows(list(reversed(ROWS[7:])));self.build();self.assertEqual(self.snapshot(),before)
 def test_purchase25_lawfully_changes26_under_same_frozen_policy(self):
  self.rows();self.build();users25={r[0] for r in self.con.execute('SELECT user_id FROM pilot_queries').fetchall()}
  self.build(day=26);users26={r[0] for r in self.con.execute('SELECT user_id FROM pilot_queries').fetchall()}
  self.assertNotIn(4,users25);self.assertIn(4,users26);self.assertIn(5,users26)
  self.assertGreater(self.con.execute('SELECT max(popularity_distinct_users) FROM pilot_candidates WHERE product_id=40').fetchone()[0],0)
 def test_never_calls_label_builder_or_reads_poison_Y(self):
  self.rows();self.con.execute("CREATE VIEW pilot_labels AS SELECT error('Y must remain closed') AS x")
  with patch('scripts.anchor_pilot.create_labels',side_effect=AssertionError('NoY')),patch('scripts.anchor_pilot.build_pilot',side_effect=AssertionError('No generic builder')):
   result=self.build(day=31)
  self.assertFalse(result['target_relation_created']);self.assertEqual(result['mature_query_count'],result['query_count'])
 def test_W_B_computes_no_extra_table_or_all_union(self):
  self.rows();result=self.build(choice='B');self.assertEqual(result['extra_schema'],[]);self.assertEqual(len(self.con.execute('DESCRIBE manual_features').fetchall()),45)
  with self.assertRaises(duckdb.CatalogException):self.con.execute('SELECT * FROM heldout_extra_features')
 def test_chosen_recency_mask_full_prefix_and_unknown_category(self):
  self.rows();result=self.build(choice='I2');self.assertEqual(result['bundle_id'],'L06')
  actual=self.con.execute('SELECT auto_pair_cart_recency_seconds_observed,auto_item_cart_count_24h,auto_pair_cart_recency_seconds_observed_missing FROM manual_features WHERE user_id=1 AND product_id=10').fetchone()
  self.assertEqual(actual,((T-datetime(2019,10,1)).total_seconds(),0,False))
  self.assertEqual(self.con.execute('SELECT candidate_category_missing,user_category_view_7d FROM manual_features WHERE user_id=2 AND product_id=20').fetchone(),(True,None))
  self.assertEqual(len(self.con.execute('DESCRIBE manual_features').fetchall()),48)
 def test_empty_Q_produces_typed_empty_B_and_chosen3(self):
  result=self.build();self.assertEqual((result['query_count'],result['candidate_count']),(0,0));self.assertEqual(len(result['base_schema']),45);self.assertEqual(len(self.con.execute('DESCRIBE heldout_extra_features').fetchall()),5)
 def test_empty_C_preserves_eligible_Q(self):
  self.rows([(T-timedelta(hours=1),'view',None,1,None)]);result=self.build();self.assertEqual((result['query_count'],result['candidate_count']),(1,0));self.assertEqual(self.con.execute('SELECT label_is_mature FROM pilot_queries').fetchone(),(True,))
 def test_guard_before_engine_and_between_helper_stages(self):
  with self.assertRaises(TimeoutError):self.build(check=lambda:(_ for _ in ()).throw(TimeoutError('stop')))
  self.assertNotIn('events',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
  self.rows()
  def stage(name,op):
   if name=='calendar_maturity':raise TimeoutError('stage stop')
   return op()
  with self.assertRaises(TimeoutError):self.build(stage=stage)
  self.assertNotIn('pilot_candidates',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
 def test_pool_or_authenticated_choice_tampering_rejected(self):
  pool,l,c=definitions('I1');pool['identity']['bundles'][0]['programs'][0]['window']=72
  with self.assertRaises(ValueError):m.selected_registry(pool,l,authenticated_choice=c)
  pool,l,c=definitions('I1');l['models']['W']['feature_names'][-1]='other'
  with self.assertRaises(ValueError):m.selected_registry(pool,l,authenticated_choice=c)
 def test_latest_null_mixture_ambiguous_and_later_clean_not_backfilled(self):
  self.rows(ROWS+[(T-timedelta(hours=1),'view',10,7,None),(T+timedelta(hours=1),'view',10,7,200)])
  self.build();self.assertEqual(self.con.execute('SELECT candidate_category_missing,candidate_category_ambiguous FROM manual_features WHERE user_id=1 AND product_id=10').fetchone(),(True,True))
  self.build(day=26);self.assertEqual(self.con.execute('SELECT candidate_category_id,candidate_category_ambiguous FROM manual_features WHERE user_id=1 AND product_id=10').fetchone(),(200,False))
 def test_private_two_thread_connection_required(self):
  self.con.execute('SET threads=1')
  with self.assertRaises(ValueError):self.build()
  self.assertNotIn('events',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
 def test_noninteger_raw_key_transport_rejected_before_history(self):
  self.con.execute('DROP TABLE heldout_raw_events');self.con.execute('CREATE TABLE heldout_raw_events(event_time TIMESTAMP,event_type VARCHAR,product_id DOUBLE,user_id BIGINT,category_id BIGINT)')
  with self.assertRaises(ValueError):self.build()
  self.assertNotIn('events',{r[0] for r in self.con.execute('SHOW TABLES').fetchall()})
 def test_no_reserved_day_or_protocol_adaptation(self):
  for day in ['2019-10-24T00:00:00Z','2019-11-01T00:00:00Z','2019-10-25T01:00:00Z']:
   with self.assertRaises(ValueError):m.daily_protocol(day)
  config=m.daily_protocol('2019-10-31T00:00:00Z');self.assertEqual(config['pilot']['end'],'2019-11-01T00:00:00Z');self.assertEqual(config['target']['horizon_hours'],24)

if __name__=='__main__':unittest.main()
