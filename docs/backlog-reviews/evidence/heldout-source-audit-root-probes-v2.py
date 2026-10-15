import unittest,json,hashlib,sys
from pathlib import Path
from datetime import timedelta
from tests import test_heldout_source_audit as fixtures
from tests.oracles import heldout_source_audit as m
import importlib.util
spec=importlib.util.spec_from_file_location('source_batch_v2','/tmp/tlab-heldout-source-audit-v2.py');batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch);fixtures.m=batch
class Independent(unittest.TestCase):
 def setUp(self):self.f=fixtures.SourceAudit();self.f.setUp()
 def tearDown(self):self.f.tearDown()
 def test_latest_NULL_only_bucket_does_not_backoff_and_is_not_ambiguous(self):
  t=fixtures.T
  self.f.insert([(t-timedelta(hours=4),'view',10,1,100),(t-timedelta(hours=1),'cart',10,1,None)])
  args=self.f.build('I2');r=self.f.audit(args)
  values=self.f.con.execute('SELECT candidate_category_id,candidate_category_missing,candidate_category_ambiguous,user_category_view_7d,user_category_view_7d_missing FROM actual_base_features').fetchone()
  self.assertEqual(values,(None,True,False,None,True));self.assertTrue(r['metadata_ages_coverage_complete'])
 def test_raw_duplicate_count_and_distinct_user_selected_R2_differ_exactly(self):
  t=fixtures.T;rows=[(t-timedelta(hours=2),'purchase',10,1,100)]*2+[(t-timedelta(hours=3),'purchase',10,2,100)]
  self.f.insert(rows);args=self.f.build('R2');self.f.audit(args)
  con=self.f.con
  self.assertEqual(con.execute('SELECT DISTINCT auto_item_purchase_count_distinct_24h_user_id FROM actual_extra_features').fetchall(),[(2,)])
  self.assertEqual(con.execute('SELECT DISTINCT item_purchase_24h FROM actual_base_features').fetchall(),[(3,)])
  self.assertEqual(con.execute('SELECT pair_purchase_7d FROM actual_base_features WHERE user_id=1').fetchone(),(2,))
 def test_known_zero_category_share_differs_from_unknown_category_NULL(self):
  t=fixtures.T
  self.f.insert([(t-timedelta(hours=3),'cart',10,1,100),(t-timedelta(hours=2),'view',20,1,200),(t-timedelta(hours=1),'cart',30,1,None)])
  args=self.f.build('R1');self.f.audit(args);con=self.f.con
  self.assertEqual(con.execute('SELECT user_category_view_7d,user_category_view_share_7d,user_category_view_share_7d_missing FROM actual_base_features WHERE product_id=10').fetchone(),(0,0.,False))
  self.assertEqual(con.execute('SELECT user_category_view_7d,user_category_view_share_7d,user_category_view_share_7d_missing FROM actual_base_features WHERE product_id=30').fetchone(),(None,None,True))
if __name__=='__main__':
 freeze=json.loads(Path('/tmp/tlab-heldout-source-audit-freeze-v1.json').read_text())
 for name,record in freeze['files'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==record['sha256']
 unittest.main(verbosity=2,defaultTest='Independent')
