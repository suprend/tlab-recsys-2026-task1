import importlib.util,unittest
from datetime import timedelta,datetime
from tests import test_heldout_source_audit as fixtures
spec=importlib.util.spec_from_file_location('batch','/tmp/tlab-heldout-source-audit-v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Independent(unittest.TestCase):
 def test_nominal_zero_category_global_NULL_user_denominator_and_order_independence(self):
  t=fixtures.T;raw=[(t-timedelta(hours=3),'view',10,1,0),(t-timedelta(hours=2),'view',10,1,0),
    (t-timedelta(hours=1),'cart',10,1,0),(t-timedelta(hours=3),'view',99,None,0),
    (t-timedelta(hours=2),'view',None,1,0),(t-timedelta(hours=1),'cart',20,1,None)]
  results=[]
  for rows in [raw,list(reversed(raw))]:
   f=fixtures.SourceAudit();f.setUp()
   try:
    f.insert(rows);args=f.build('R2');lock=m._choice(args[1],args[2]);m._audit_day(f.con,args[0],lock,args[3],lambda:None)
    q=f.con.execute('SELECT query_id FROM _hsa_q WHERE user_id=1').fetchone()[0]
    values=m._sample_values_batch(f.con,[(q,10),(q,20)],t,datetime(2019,10,1),datetime(2019,11,1),lambda:None)
    self.assertEqual(values[(q,10)]['candidate_category_id'],0);self.assertEqual(values[(q,10)]['category_view_7d'],4)
    self.assertEqual(values[(q,10)]['user_category_view_7d'],3);self.assertEqual(values[(q,10)]['item_category_view_7d'],2)
    self.assertEqual(values[(q,10)]['item_category_view_share_7d'],.5);self.assertEqual(values[(q,10)]['user_distinct_viewed_items_7d'],1)
    self.assertIsNone(values[(q,20)]['category_view_7d']);results.append(values)
   finally:f.tearDown()
  self.assertEqual(results[0],results[1])
if __name__=='__main__':unittest.main(verbosity=2,defaultTest='Independent')
