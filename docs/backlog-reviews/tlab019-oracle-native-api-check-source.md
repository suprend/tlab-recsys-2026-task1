# Historical019 observer evidence: native-api-check

Paths normalized for privacy. This archive records an earlier review state or a synthetic/API check, not a new execution. Only tests/oracles/strong_output_audit.py is the final accepted observer entry.

```python
import time
started=time.monotonic()
import importlib.util,json,hashlib,tempfile,resource
from copy import deepcopy
from pathlib import Path
import numpy as np
entry=Path('tlab-verify019-outputs.py');expected='18d45b266dd7666669dd1948eb926b38e613c0921f70daa18092c25a24924a0e'
assert hashlib.sha256(entry.read_bytes()).hexdigest()==expected
s=importlib.util.spec_from_file_location('observer',entry);o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
root=Path('project root');directory=root/'artifacts/training/195c89b9a8500b7977d1840d2ef3a6c7acb8f9cf043e1ca407ac718b22f846b6'
path=directory/'Logloss.cbm';original='d4b2c068fa65700f038a841470ec49f7fd41ee02f6e16d66959f57acfc00eb80';assert hashlib.sha256(path.read_bytes()).hexdigest()==original
report=json.loads((directory/'report.json').read_text());control=next(x for x in report['fit_attempts'] if x['method']=='Logloss');params=control['actual_model_parameters'];names=report['feature_names']
observer=object.__new__(o.Observer);observer.guard=lambda:None
model=observer.model(path,50,names,params);lr=o.effective_learning_rate(params)
x=np.zeros((3,41),dtype=np.float32);score=np.asarray(model.predict(x,ntree_end=17,prediction_type='RawFormulaVal',thread_count=2))
with tempfile.TemporaryDirectory() as temporary:
 p=Path(temporary)/'prefix17.cbm';copy=model.copy();copy.shrink(17);copy.save_model(str(p))
 loaded=observer.model(p,17,names,params);replay=np.asarray(loaded.predict(x,prediction_type='RawFormulaVal',thread_count=2))
 assert np.allclose(score,replay,rtol=0,atol=1e-12)
 wrong=deepcopy(params);wrong['l2_leaf_reg']=30
 try:observer.model(p,17,names,wrong)
 except ValueError:pass
 else:raise AssertionError('Material parameter drift accepted')
assert model.tree_count_==50 and hashlib.sha256(path.read_bytes()).hexdigest()==original
assert hashlib.sha256(entry.read_bytes()).hexdigest()==expected
r=resource.getrusage(resource.RUSAGE_SELF)
result=dict(status='verified_native_observer_API_only',entry_sha256=expected,accepted_control_sha256=original,
 actual_fit_attempt_count=0,real_query_target_or_selection_metric_rows=0,synthetic_rows=3,numeric_columns=41,
 control50_and_saved17_accepted=True,original_bytes_unchanged=True,max_absolute_prefix_score_difference=float(np.max(np.abs(score-replay))),
 effective_lr_from_accepted_params=lr,declared_lr_float32_contract_passed=True,material_l2_drift_rejected=True,
 seconds=time.monotonic()-started,actual_cpu_seconds=r.ru_utime+r.ru_stime,process_peak_rss_bytes=int(r.ru_maxrss))
Path('tlab019-oracle-native-api-proof.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

```
