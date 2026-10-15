# Historical019 audit source: prefix-api-proof

Aggregate/synthetic evidence archive. Paths below are normalized for privacy; this preserves the historical observer, not a new execution approval. Original freeze references belong to the version reviewed by that pass. No real019 model fit was run by these checks.

```python
import time
start=time.monotonic()
import hashlib,json,resource,tempfile
from pathlib import Path
import numpy as np
from catboost import CatBoostClassifier
root=Path('project root')
path=root/'artifacts/training/195c89b9a8500b7977d1840d2ef3a6c7acb8f9cf043e1ca407ac718b22f846b6/Logloss.cbm'
expected='d4b2c068fa65700f038a841470ec49f7fd41ee02f6e16d66959f57acfc00eb80'
if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Prior accepted control bytes changed')
model=CatBoostClassifier();model.load_model(str(path));before=model.get_all_params();names=model.feature_names_
x=np.zeros((3,len(names)),dtype=np.float32)
a=np.asarray(model.predict(x,ntree_end=17,prediction_type='RawFormulaVal',thread_count=2))
copy=model.copy();copy.shrink(17)
with tempfile.TemporaryDirectory() as tmp:
 saved=Path(tmp)/'prefix17.cbm';copy.save_model(str(saved));loaded=CatBoostClassifier();loaded.load_model(str(saved))
 b=np.asarray(loaded.predict(x,prediction_type='RawFormulaVal',thread_count=2));after=loaded.get_all_params()
if model.tree_count_!=50 or copy.tree_count_!=17 or loaded.tree_count_!=17 or not np.allclose(a,b,rtol=0,atol=1e-12):raise ValueError('Native saved prefix mismatch')
if before!=model.get_all_params() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Immutable original changed')
r=resource.getrusage(resource.RUSAGE_SELF)
proof=dict(status='verified_native_API_only',fit_attempt_count=0,real_query_or_target_rows=0,synthetic_rows=3,numeric_columns=len(names),
 original_trees=50,copy_trees=17,reloaded_trees=17,max_absolute_score_difference=float(np.max(np.abs(a-b))),
 original_unchanged=True,accepted_original_sha256=expected,parameter_types={k:dict(original=type(before[k]).__name__,loaded=type(after[k]).__name__,original_value=before[k],loaded_value=after[k]) for k in ['iterations','l2_leaf_reg','random_strength','learning_rate']},
 seconds=time.monotonic()-start,actual_cpu_seconds=r.ru_utime+r.ru_stime,process_peak_rss_bytes=int(r.ru_maxrss))
Path('tlab019-prefix-api-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))

```
