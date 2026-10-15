# Reserved evaluation and independent metric core: code-level evidence

15 October 2026. Tiny synthetic inputs only, no actual reserved data/model/native/target operation. Original and repaired evaluation probes, metric probes and logs are preserved with original SHA below. Local roots/trailing whitespace sanitized only for publication. All fenced material is audit evidence; it is not an execution/approval command.

## tlab-heldout-evaluation-independent.py

Original SHA256 a0903e1cc6518964bfe974f9a6def63d3c2eb5ad2ce87aff55b670cd19a07e71.

```python
import hashlib,json,unittest
from copy import deepcopy
from pathlib import Path
from tests.test_heldout_evaluation import EvaluationCoreTests,BIG
from scripts import heldout_evaluation as m
class Independent(unittest.TestCase):
    def setUp(self):
        self.f=EvaluationCoreTests();self.f.setUp();self.f.raw()
    def tearDown(self):self.f.tearDown()
    def test_user_substitution_at_target_stage_must_reject(self):
        def stage(name,op):
            if name=='create_fullY_independent_of_candidates':self.f.con.execute("UPDATE heldout_target_queries SET user_id=7 WHERE query_id='a'")
            return op()
        with self.assertRaises(ValueError):self.f.evaluate(stage=stage)
    def test_query_deletion_after_target_stage_must_reject(self):
        def stage(name,op):
            value=op()
            if name=='create_fullY_independent_of_candidates':self.f.con.execute("DELETE FROM heldout_target_queries WHERE query_id='f'")
            return value
        with self.assertRaises(ValueError):self.f.evaluate(stage=stage)
    def test_provider_owned_prior_day_keys_and_scores_do_not_change_snapshots(self):
        original=self.f.population
        def population(day):
            if day['anchor']==m.h.DAYS[-1]:
                first=m.h.DAYS[0];self.f.pop[first]['queries'][0]=('tampered',7,self.f.pop[first]['queries'][0][2])
                for role in ['B','W']:
                    ref=self.f.inventory['days'][0]['predictions'][role]['artifact']['path'];self.f.saved[ref]['scores'][:]=100
            return original(day)
        self.f.population=population
        result=self.f.evaluate();self.assertEqual(result['private_targets']['a'],frozenset({BIG+1,999}))
        self.assertGreater(result['periods']['confirmation25_reporting_only']['ndcg_W_minus_B']['conditional_macro_query'],0)
    def test_independent_tie_gold_and_fullY_outside_C(self):
        # Set both B/W equal scores, so lower BIG product precedes relevant BIG+1.
        for desc in self.f.inventory['days'][0]['predictions'].values():self.f.saved[desc['artifact']['path']]['scores'][:]=0
        result=self.f.evaluate()['periods']['confirmation25_reporting_only']
        import math
        expected=(1/math.log2(3))/(1+1/math.log2(3))
        for role in ['B','W']:
            self.assertAlmostEqual(result['metrics'][role]['conditional_macro_query']['ndcg'],expected,places=14)
            self.assertEqual(result['metrics'][role]['conditional_macro_query']['recall'],.5)
        self.assertEqual(result['support']['target_pairs'],2)
if __name__=='__main__':
    freeze=json.loads(Path('<temporary>/tlab-heldout-evaluation-freeze-v1.json').read_text())
    print('freeze',freeze)
    unittest.main(verbosity=2,defaultTest="Independent")
```

## tlab-heldout-evaluation-independent-v1-unique.log

Original SHA256 40718168d8ffdae52fc2c693d3c53efe9065479cf75840e8ec23f1ce8fa87eea.

```text
test_independent_tie_gold_and_fullY_outside_C (__main__.Independent.test_independent_tie_gold_and_fullY_outside_C) ... ok
test_provider_owned_prior_day_keys_and_scores_do_not_change_snapshots (__main__.Independent.test_provider_owned_prior_day_keys_and_scores_do_not_change_snapshots) ... ok
test_query_deletion_after_target_stage_must_reject (__main__.Independent.test_query_deletion_after_target_stage_must_reject) ... FAIL
test_user_substitution_at_target_stage_must_reject (__main__.Independent.test_user_substitution_at_target_stage_must_reject) ... FAIL

======================================================================
FAIL: test_query_deletion_after_target_stage_must_reject (__main__.Independent.test_query_deletion_after_target_stage_must_reject)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-evaluation-independent.py", line 20, in test_query_deletion_after_target_stage_must_reject
    with self.assertRaises(ValueError):self.f.evaluate(stage=stage)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_user_substitution_at_target_stage_must_reject (__main__.Independent.test_user_substitution_at_target_stage_must_reject)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-evaluation-independent.py", line 14, in test_user_substitution_at_target_stage_must_reject
    with self.assertRaises(ValueError):self.f.evaluate(stage=stage)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 4 tests in 0.156s

FAILED (failures=2)
freeze {'docs/experiments/heldout-evaluation.md': '5ba2380df83b812c5cc1fe09b29cdcfd8bef44d386674eaf388d2b1edf7394ab', 'scripts/heldout_evaluation.py': '30610cd36985b7cf211367c39b58a5dd1ae6032a4f558c7dd10c9030b8d73623', 'tests/test_heldout_evaluation.py': '0da3a8d59fcca284a2cccbb36686a25e37322d2c5fd4fa367565f8eabb455f8d'}
```

## tlab-heldout-evaluation-independent-v2.py

Original SHA256 31448883fe4c878937b9947329e65c4c5ac827668bc0ca36ce221bc0f9cb9480.

```python
import hashlib,json,unittest
from copy import deepcopy
from pathlib import Path
from tests.test_heldout_evaluation import EvaluationCoreTests,BIG
from scripts import heldout_evaluation as m
class Independent(unittest.TestCase):
    def setUp(self):
        self.f=EvaluationCoreTests();self.f.setUp();self.f.raw()
    def tearDown(self):self.f.tearDown()
    def test_user_substitution_at_target_stage_must_reject(self):
        def stage(name,op):
            if name=='create_fullY_independent_of_candidates':self.f.con.execute("UPDATE heldout_target_queries SET user_id=7 WHERE query_id='a'")
            return op()
        with self.assertRaises(ValueError):self.f.evaluate(stage=stage)
    def test_query_deletion_after_target_stage_must_reject(self):
        def stage(name,op):
            value=op()
            if name=='create_fullY_independent_of_candidates':self.f.con.execute("DELETE FROM heldout_target_queries WHERE query_id='f'")
            return value
        with self.assertRaises(ValueError):self.f.evaluate(stage=stage)
    def test_provider_owned_prior_day_keys_and_scores_do_not_change_snapshots(self):
        original=self.f.population
        def population(day):
            if day['anchor']==m.h.DAYS[-1]:
                first=m.h.DAYS[0];self.f.pop[first]['queries'][0]=('tampered',7,self.f.pop[first]['queries'][0][2])
                for role in ['B','W']:
                    ref=self.f.inventory['days'][0]['predictions'][role]['artifact']['path'];self.f.saved[ref]['scores'][:]=100
            return original(day)
        self.f.population=population
        result=self.f.evaluate();self.assertEqual(result['private_targets']['a'],frozenset({BIG+1,999}))
        self.assertGreater(result['periods']['confirmation25_reporting_only']['ndcg_W_minus_B']['conditional_macro_query'],0)
    def test_independent_tie_gold_and_fullY_outside_C(self):
        # Set both B/W equal scores, so lower BIG product precedes relevant BIG+1.
        for desc in self.f.inventory['days'][0]['predictions'].values():self.f.saved[desc['artifact']['path']]['scores'][:]=0
        result=self.f.evaluate()['periods']['confirmation25_reporting_only']
        import math
        expected=(1/math.log2(3))/(1+1/math.log2(3))
        for role in ['B','W']:
            self.assertAlmostEqual(result['metrics'][role]['conditional_macro_query']['ndcg'],expected,places=14)
            self.assertEqual(result['metrics'][role]['conditional_macro_query']['recall'],.5)
        self.assertEqual(result['support']['target_pairs'],2)
if __name__=='__main__':
    freeze=json.loads(Path('<temporary>/tlab-heldout-evaluation-freeze-v2.json').read_text())
    print('freeze',freeze)
    unittest.main(verbosity=2,defaultTest="Independent")
```

## tlab-heldout-evaluation-independent-v2.log

Original SHA256 a594ea22bd514b95253192eb6a8dfa9a36736700938673bdc9dd3e34a6376213.

```text
test_independent_tie_gold_and_fullY_outside_C (__main__.Independent.test_independent_tie_gold_and_fullY_outside_C) ... ok
test_provider_owned_prior_day_keys_and_scores_do_not_change_snapshots (__main__.Independent.test_provider_owned_prior_day_keys_and_scores_do_not_change_snapshots) ... ok
test_query_deletion_after_target_stage_must_reject (__main__.Independent.test_query_deletion_after_target_stage_must_reject) ... ok
test_user_substitution_at_target_stage_must_reject (__main__.Independent.test_user_substitution_at_target_stage_must_reject) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.152s

OK
freeze {'docs/experiments/heldout-evaluation.md': '02d587812239943f586e4bf35806fc10d4ab2f8f9febcd8fe6f9229d47e68bf2', 'scripts/heldout_evaluation.py': '13ff442a599ab2623c7a3fa2316f36ed9ec8015215172edfcee86b8f25f51446', 'tests/test_heldout_evaluation.py': '188d6f6c4a521dff17ebab0451ad56e2d036a747c272fcfe10df8f54f90bd3ce'}
```

## tlab-heldout-metric-independent.py

Original SHA256 f28f62af0d4c8711e2efd49b159c3fc281b9ab2b71870a0b7c5a23840f51a08c.

```python
import math,unittest,hashlib,json
from pathlib import Path
from tests.oracles import heldout_metric_audit as a
from tests import test_heldout_metric_audit as f
class Independent(unittest.TestCase):
 def test_literal_unequal_query_user_mass_and_expanded_draw(self):
  # Hand-assigned query metrics isolate estimand arithmetic from query scorer.
  rows=[dict(user_id=u,targets=frozenset({1}) if p else frozenset(),values=dict.fromkeys(a.NAMES,v)) for u,p,v in [(1,True,1.),(1,True,1.),(2,True,0.),(3,False,None)]]
  groups=a.user_groups(rows)
  gold={'conditional_macro_query':2/3,'all_query_zero':.5,'conditional_user_macro':.5,'all_user_macro_zero':1/3}
  drawn={'conditional_macro_query':1.,'all_query_zero':.8,'conditional_user_macro':1.,'all_user_macro_zero':2/3}
  for name in a.ESTIMANDS:
   self.assertAlmostEqual(a.aggregate(groups,name,'ndcg'),gold[name],places=14)
   self.assertAlmostEqual(a.aggregate(groups,name,'ndcg',[1,1,3]),drawn[name],places=14)
 def test_top20_fullY_denominator_and_last_position_discount(self):
  result=a.query_values(list(range(30)),frozenset(range(30)))
  self.assertEqual(result['ndcg'],1.);self.assertEqual(result['average_precision'],20/30);self.assertEqual(result['recall'],20/30);self.assertEqual(result['reciprocal_rank'],1.)
  result=a.query_values(list(range(20)),frozenset({19,999}))
  self.assertAlmostEqual(result['ndcg'],(1/math.log2(21))/(1+1/math.log2(3)),places=14)
  self.assertEqual(result['average_precision'],1/40)
 def test_numeric_tolerance_accepts_roundoff_rejects_material_drift_and_bool(self):
  a.compare({'ndcg':.5+1e-13},{'ndcg':.5})
  with self.assertRaises(ValueError):a.compare({'ndcg':.5+1e-6},{'ndcg':.5})
  with self.assertRaises(ValueError):a.compare({'count':True},{'count':1})
 def test_snapshot_owned_earlier_vectors_survive_late_original_mutation(self):
  fixture=f.MetricOracleTests();fixture.setUp()
  try:
   inputs=fixture.inputs();first=inputs['days'][0];original_queries=list(first['queries']);original_items=first['items'].copy();done=False
   def guard():
    nonlocal done
    if done:return
    # On the seventh iteration the first six snapshots already exist.
    guard.calls+=1
    if guard.calls==7:
     first['queries'][0]=('evil',7,first['queries'][0][2]);first['items'][:]=7;first['scores']['W'][:]=999.;done=True
   guard.calls=0
   snap=a.snapshot_days(inputs['days'],guard)
   self.assertEqual(snap[0]['queries'],original_queries);self.assertTrue((snap[0]['items']==original_items).all());self.assertEqual(snap[0]['scores']['W'].tolist(),[0.,1.])
  finally:fixture.tearDown()
if __name__=='__main__':unittest.main(verbosity=2,defaultTest='Independent')
```

## tlab-heldout-metric-independent.log

Original SHA256 001f1196dee44b9a53f5d0c3caa315c9a565b77115db23fbf9373484d38d3f5b.

```text
test_literal_unequal_query_user_mass_and_expanded_draw (__main__.Independent.test_literal_unequal_query_user_mass_and_expanded_draw) ... ok
test_numeric_tolerance_accepts_roundoff_rejects_material_drift_and_bool (__main__.Independent.test_numeric_tolerance_accepts_roundoff_rejects_material_drift_and_bool) ... ok
test_snapshot_owned_earlier_vectors_survive_late_original_mutation (__main__.Independent.test_snapshot_owned_earlier_vectors_survive_late_original_mutation) ... ok
test_top20_fullY_denominator_and_last_position_discount (__main__.Independent.test_top20_fullY_denominator_and_last_position_discount) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.120s

OK
```
