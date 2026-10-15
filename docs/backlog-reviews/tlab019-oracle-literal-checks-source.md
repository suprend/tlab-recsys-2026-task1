# Historical019 observer evidence: literal-checks

Paths normalized for privacy. This archive records an earlier review state or a synthetic/API check, not a new execution. Only tests/oracles/strong_output_audit.py is the final accepted observer entry.

```python
import importlib.util,unittest,math
from copy import deepcopy
from pathlib import Path
p='tlab-verify019-outputs.py';s=importlib.util.spec_from_file_location('audit',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
class Checks(unittest.TestCase):
 def test_fullY_and_empty_negative_queries_four_estimands_literal(self):
  q=[('q1',1),('q2',1),('q3',2)];targets={'q1':{10,99},'q3':{20}};rank={'q1':[10], 'q3':[77,20]}
  m,per,users=o.summarize(q,targets,rank)
  self.assertEqual(m['query_count'],3);self.assertEqual(m['nonempty_query_count'],2)
  self.assertEqual(m['conditional_macro_query']['recall'],.75);self.assertEqual(m['all_query_zero']['recall'],.5)
  self.assertEqual(m['conditional_user_macro']['recall'],.75);self.assertEqual(m['all_user_macro_zero']['recall'],.625)
  self.assertAlmostEqual(m['conditional_macro_query']['ndcg'],(.6131471927654584+.6309297535714575)/2,places=14)
  self.assertEqual(m['conditional_macro_query']['average_precision'],.5)
 def test_tie_law_global_band_not_pairwise_chain(self):
  def arm(score,trees,depth,inc=False,id='z'):
   return dict(metrics={'conditional_macro_query':{'ndcg':score,'recall':.6}},trees=trees,depth=depth,incumbent=inc,config_id=id)
  a=arm(.4,150,4);b=arm(.4-.8e-12,50,6);c=arm(.4-1.6e-12,50,4)
  self.assertIs(o.select([c,b,a]),b)
  self.assertTrue(o.select([arm(.4,50,6,False,'a'),arm(.4,50,6,True,'z')])['incumbent'])
 def test_known_failed_individual_overshoot_whole_shared_cap(self):
  slot={'allocation':{'cpu_seconds':10,'rss_bytes':7*2**30}}
  failed=dict(entry_actual_cpu_seconds=10.01,entry_reaped_children_cpu_seconds=0,process_peak_rss_bytes=7*2**30+1,status='failed',outcome='resource_failure',error_type='MemoryError')
  o.worker_resource_policy(failed,slot,successful=False)
  with self.assertRaises(ValueError):o.worker_resource_policy(failed,slot,successful=True)
  child={'exit_code':1,'manifest':{'identity':{'slot':slot}},'report':failed};r=dict(actual_total_cpu_seconds=12,actual_parent_cpu_seconds=1,actual_reaped_children_cpu_seconds=11,parent_peak_rss_bytes=1000000,seconds=30)
  o.whole_resource_policy(r,[child]);r['parent_peak_rss_bytes']=2**30
  with self.assertRaises(ValueError):o.whole_resource_policy(r,[child])
 def test_effective_parameters_are_typed_and_material_drift_rejected(self):
  self.assertTrue(o.same(3,3));self.assertFalse(o.same(3,True));self.assertFalse(o.same(3,3.))
  self.assertTrue(o.same(.05000000075,.05000000074505806));self.assertFalse(o.same(.05000000075,.0501))
if __name__=='__main__':unittest.main(verbosity=2)

```
