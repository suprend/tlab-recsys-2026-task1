# Pure heldout contract independent evidence

V1 source/policy/tests were reviewed and four independent probes yielded two failures. V2 repairs close both unchanged probes; sixteen author plus four unique independent cases pass. This is structural CODE ACCEPT only: no actual heldout source, model, prediction, target access, execution authority or budget. Temporary/home roots are sanitized in published audit copies; original SHA256 below.

## tlab-heldout-contract-independent.py

Original SHA256 bf8fb772811deb6683c1a75ee4547b5833aad48ef070f38a8a1e75230269bd47.

```python
import sys,unittest
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,'<repository>')
from scripts import heldout_contract as h
from tests.test_heldout_contract import fixture
class Independent(unittest.TestCase):
 def test_duplicate_authenticated_source_day_must_not_collapse(self):
  l,c,i,s,*_=fixture();s['days'].append(deepcopy(s['days'][2]))
  with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
 def test_frozen_calendar_all_seven_full_horizons_mature(self):
  l,c,i,s,*_=fixture()
  self.assertTrue(all(h.utc(day)+__import__('datetime').timedelta(hours=24)<=h.utc(l['policy']['source']['end']) for day in h.DAYS))
  i['days'][-1]['mature_query_count']=0;s['days'][-1]['mature_query_count']=0
  with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
 def test_zero_complete_compute_and_above_allowance_forbidden(self):
  for value in [0,43201]:
   l,c,*_=fixture()
   for e in l['compute_evidence']:e['measured_active_wall_upper_seconds']=0;e['declared_unmeasured_wall_upper_seconds']=0
   l['compute_evidence'][0]['declared_unmeasured_wall_upper_seconds']=value
   with self.assertRaises(ValueError):h.validate_lock(l,authenticated_choice=c)
 def test_metadata_io_remains_forbidden_and_exact_allowance_inclusive(self):
  from unittest.mock import patch
  l,c,*_=fixture()
  for e in l['compute_evidence']:e['measured_active_wall_upper_seconds']=0;e['declared_unmeasured_wall_upper_seconds']=0
  l['compute_evidence'][0]['declared_unmeasured_wall_upper_seconds']=43200
  with patch('builtins.open',side_effect=AssertionError('no IO')):self.assertEqual(h.validate_lock(l,authenticated_choice=c),l)
if __name__=='__main__':unittest.main()
```

## tlab-heldout-contract-independent-v1.log

Original SHA256 8cf7b395fc8873adacfc67bda16ffe9bf2a6edf6ede40f188d835da439118357.

```text
FF..
======================================================================
FAIL: test_duplicate_authenticated_source_day_must_not_collapse (__main__.Independent.test_duplicate_authenticated_source_day_must_not_collapse)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-contract-independent.py", line 10, in test_duplicate_authenticated_source_day_must_not_collapse
    with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

======================================================================
FAIL: test_frozen_calendar_all_seven_full_horizons_mature (__main__.Independent.test_frozen_calendar_all_seven_full_horizons_mature)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<temporary>/tlab-heldout-contract-independent.py", line 15, in test_frozen_calendar_all_seven_full_horizons_mature
    with self.assertRaises(ValueError):h.validate_prediction_inventory(i,l,authenticated_source=s)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: ValueError not raised

----------------------------------------------------------------------
Ran 4 tests in 0.022s

FAILED (failures=2)
```

## tlab-heldout-contract-independent-v2.log

Original SHA256 7a559f5f3b288fe7710f7d08453f712cd2e9ce60025f248acc51ca1c2ff5db00.

```text
....
----------------------------------------------------------------------
Ran 4 tests in 0.022s

OK
```

## tlab-heldout-contract-author-v2.log

Original SHA256 f0c79ce6dc83e2fb10ea0f89a87b9acd70f8b8d0c1da65db952928491752af3f.

```text
................
----------------------------------------------------------------------
Ran 16 tests in 0.036s

OK
```
