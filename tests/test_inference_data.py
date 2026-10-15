from datetime import datetime,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import duckdb
import numpy as np

from scripts import inference_data as m
BASE=['from_popular', 'from_recent', 'popularity_distinct_users', 'popular_source_rank', 'recent_source_rank', 'candidate_category_ambiguous', 'candidate_category_missing', 'item_has_observed_history', 'user_has_observed_history', 'item_observed_age_seconds', 'user_observed_age_seconds', 'user_view_7d', 'user_cart_7d', 'user_purchase_7d', 'user_distinct_viewed_items_7d', 'pair_view_7d', 'pair_cart_7d', 'pair_purchase_7d', 'pair_view_recency_seconds', 'pair_purchase_recency_seconds', 'item_view_24h', 'item_purchase_24h', 'item_distinct_viewers_7d', 'user_category_view_7d', 'user_category_view_recency_seconds', 'item_category_view_7d', 'category_view_7d', 'source_coverage_24h', 'source_coverage_168h', 'user_category_view_share_7d', 'item_category_view_share_7d', 'pair_view_recency_seconds_missing', 'pair_purchase_recency_seconds_missing', 'user_category_view_7d_missing', 'user_category_view_share_7d_missing', 'user_category_view_recency_seconds_missing', 'item_category_view_7d_missing', 'category_view_7d_missing', 'item_category_view_share_7d_missing', 'retrieval_last_event_age_seconds', 'retrieval_last_event_missing']

class InferenceTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
  self.root_patch=patch.object(m,'ROOT',self.root);self.root_patch.start();self.addCleanup(self.root_patch.stop)
  self.con=duckdb.connect(':memory:');self.addCleanup(self.con.close)
  self.t=datetime(2019,10,25)
  self.con.execute('CREATE TABLE q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
  self.con.executemany('INSERT INTO q VALUES(?,?,?,?)',[('a',100,self.t,True),('b',101,self.t,True),('empty',102,self.t,False)])
  fields=['query_id VARCHAR','user_id BIGINT','product_id BIGINT','anchor TIMESTAMP','candidate_category_id BIGINT','last_user_event_time TIMESTAMP']+[f'"{n}" DOUBLE' for n in BASE[:-2]]
  self.con.execute('CREATE TABLE f('+','.join(fields)+')')
  values=[0.]*39
  values[BASE.index('pair_view_recency_seconds')]=None
  values[BASE.index('pair_view_recency_seconds_missing')]=1.
  rows=[('a',100,9007199254740993,self.t,9007199254740995,self.t-timedelta(seconds=50),*values),('b',101,42,self.t,1,None,*values)]
  self.con.executemany('INSERT INTO f VALUES('+','.join('?' for _ in rows[0])+')',rows)
  self.con.execute('CREATE TABLE extra(query_id VARCHAR,product_id BIGINT,auto_count DOUBLE,auto_recency DOUBLE,auto_missing DOUBLE,unused DOUBLE)')
  self.con.execute("INSERT INTO extra VALUES('a',9007199254740993,3,50,0,999),('b',42,0,NULL,1,888)")
  self.poison=self.root/'labels.parquet';self.poison.write_bytes(b'not a parquet file and must never be read')
  self.export()
 def export(self):
  for name in ['q','f','extra']:
   self.con.execute('COPY '+name+' TO ? (FORMAT PARQUET)',[str(self.root/(name+'.parquet'))])
 def load(self,extra=False,**kwargs):
  names=BASE+(['auto_count','auto_recency','auto_missing'] if extra else [])
  return m.load_inference_data(['q.parquet'],['f.parquet'],expected_feature_names=names,
   extra_feature_paths=['extra.parquet'] if extra else None,extra_feature_names=names[41:],**kwargs)
 def test_triples_exact_large_ids_nulls_and_all_queries(self):
  data=self.load();self.assertEqual([q[0] for q in data.queries],['a','b','empty'])
  self.assertEqual(data.calendar_maturity.tolist(),[True,True,False]);self.assertTrue(all(len(q)==3 for q in data.queries));self.assertFalse(hasattr(data,'y'))
  self.assertEqual(data.items.tolist(),[9007199254740993,42]);self.assertEqual(data.group.tolist(),[0,1])
  self.assertTrue(np.isnan(data.x[:,BASE.index('pair_view_recency_seconds')]).all())
  self.assertEqual(data.x[:,BASE.index('retrieval_last_event_age_seconds')].tolist()[0],50.)
  self.assertEqual(data.x[:,BASE.index('retrieval_last_event_missing')].tolist(),[0.,1.])
  self.assertEqual(data.preparation['outcome_relations_opened'],0)
 def test_optional_query_group_column_cannot_shadow_generated_identity(self):
  reference=self.load(True)
  self.con.execute('ALTER TABLE q ADD COLUMN _group BIGINT DEFAULT 0')
  self.export();data=self.load(True)
  self.assertEqual(data.queries,reference.queries)
  self.assertEqual(data.group.tolist(),[0,1])
  self.assertEqual([(data.queries[int(g)][0],int(item)) for g,item in zip(data.group,data.items)],
   [('a',9007199254740993),('b',42)])
  np.testing.assert_array_equal(data.x,reference.x)
  np.testing.assert_array_equal(data.calendar_maturity,reference.calendar_maturity)
 def test_reserved_clock_metadata_cannot_be_caller_declared_base_feature(self):
  changed=BASE.copy();changed[0]='label_is_mature'
  with self.assertRaisesRegex(ValueError,'Keys/clock'):
   m.load_inference_data(['q.parquet'],['f.parquet'],expected_feature_names=changed)
 def test_outcome_changes_do_not_change_arrays_and_no_fakeY_argument(self):
  first=self.load();self.poison.write_bytes(b'different future outcomes')
  second=self.load();np.testing.assert_array_equal(first.x,second.x)
  with self.assertRaises(TypeError):self.load(label_paths=['labels.parquet'])
 def test_only_final_three_extras_project_and_nulls_survive(self):
  data=self.load(True);self.assertEqual(data.x.shape,(2,44));self.assertNotIn('unused',data.feature_names)
  self.assertEqual(data.x[:,41].tolist(),[3.,0.]);self.assertTrue(np.isnan(data.x[1,42]));self.assertEqual(data.x[:,43].tolist(),[0.,1.])
 def test_duplicate_orphan_future_and_missing_extra_keys_reject(self):
  self.con.execute('INSERT INTO f SELECT * FROM f LIMIT 1');self.export()
  with self.assertRaisesRegex(ValueError,'candidate feature keys'):self.load()
  self.con.execute('DELETE FROM f WHERE rowid=(SELECT max(rowid)FROM f)');self.con.execute("UPDATE f SET user_id=999 WHERE query_id='a'");self.export()
  with self.assertRaisesRegex(ValueError,'candidate feature keys'):self.load()
  self.con.execute("UPDATE f SET user_id=100,last_user_event_time=anchor WHERE query_id='a'");self.export()
  with self.assertRaisesRegex(ValueError,'candidate feature keys'):self.load()
  self.con.execute("UPDATE f SET last_user_event_time=anchor-INTERVAL 50 SECOND WHERE query_id='a'");self.con.execute("DELETE FROM extra WHERE query_id='b'");self.export()
  with self.assertRaisesRegex(ValueError,'key multiset'):self.load(True)
 def test_caps_identifiers_rawIDs_and_inf_fail(self):
  with self.assertRaises(MemoryError):self.load(matrix_byte_cap=1)
  with self.assertRaises(ValueError):self.load(max_queries=True)
  with self.assertRaisesRegex(ValueError,'Keys/clock'):m.load_inference_data(['q.parquet'],['f.parquet'],expected_feature_names=BASE+['user_id'],extra_feature_names=['user_id'],extra_feature_paths=['extra.parquet'])
  self.con.execute('UPDATE f SET user_view_7d=1e309');self.export()
  with self.assertRaisesRegex(ValueError,'Infinite'):self.load()
 def test_base_arrays_equal_separate_accepted_training_loader_on_syntheticY(self):
  from scripts import model_data as d
  self.con.execute('UPDATE q SET label_is_mature=true');self.export()
  self.con.execute('CREATE TABLE synthetic_y(query_id VARCHAR,product_id BIGINT)')
  self.con.execute("INSERT INTO synthetic_y VALUES('a',9007199254740993),('empty',42)")
  self.con.execute('COPY synthetic_y TO ? (FORMAT PARQUET)',[str(self.root/'synthetic-y.parquet')])
  col=dict(phase=dict(role='selection'),feature_columns=[r[0] for r in self.con.execute('DESCRIBE f').fetchall()],
   refs=dict(queries=['q.parquet'],features=['f.parquet'],labels=['synthetic-y.parquet']))
  with patch.object(d,'ROOT',self.root):reference=d.prepare_model_data(col,max_queries=None,max_rows=660)
  inferred=self.load()
  self.assertEqual(inferred.queries,[q[:3] for q in reference.queries]);self.assertEqual(inferred.feature_names,reference.feature_names)
  np.testing.assert_array_equal(inferred.x,reference.x);np.testing.assert_array_equal(inferred.group,reference.group);np.testing.assert_array_equal(inferred.items,reference.items)
 def test_expired_caller_guard_precedes_any_engine_or_file_open(self):
  with patch.object(m.duckdb,'connect') as connect:
   def fail():raise TimeoutError('caller expired')
   with self.assertRaisesRegex(TimeoutError,'caller expired'):self.load(check=fail)
   connect.assert_not_called()
 def test_empty_query_and_candidate_relations(self):
  self.con.execute('DELETE FROM f');self.export();data=self.load();self.assertEqual(len(data.queries),3);self.assertEqual(data.x.shape,(0,41))
  self.con.execute('DELETE FROM q');self.export();data=self.load();self.assertEqual(data.queries,[]);self.assertEqual(data.x.shape,(0,41))

if __name__=='__main__':unittest.main()
