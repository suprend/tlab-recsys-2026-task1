# TLAB-009: synthetic mixed-input API proof

15 октября 2026. Root фактически выполнил tiny6-row proof на installedCatBoost1.2.10 CPU,2threads,2trees,1numeric+3nominal. [Actual JSON result](../backlog-reviews/metadata-price-api-result.json) сохранён: обе Logloss/PairLogit ветки PASS, categoryindices1/2/3, one_hot_max_size4096, finiteunseenpredictions, JSONsplits OneHotFeature безOnlineCtr. Это interfacecompatibility, не realREES46fit, quality/realcardinality/peakmemory proof.

Primary [FeaturesData docs](https://catboost.ai/docs/en/concepts/python-features-data__desc) требуют float32numeric/objectUTF8bytes иownvalidation; [categorical docs](https://catboost.ai/docs/en/features/categorical-features) различаютобычныйPairLogit иCPU pairwise-scoringobjectives. На реальных данных дополнительно проверяются cardinalities includingstate sentinels≤4096, effectiveparams/JSONCTR evidence, exactschema/lineage иcost. [Design](../backlog-reviews/metadata-price-design.md) и [independentcritic](../backlog-reviews/metadata-price-design-review.md) — отдельныеgates.

Ниже тот же synthetic check с переносимым временным каталогом вместо исходныхлокальныхpaths. Result timing относитсяRootoriginalcheck, не новойpublicationэкзекуции.

```python
from pathlib import Path
import json,time,tempfile
import numpy as np
import catboost
from catboost import FeaturesData,Pool,CatBoostClassifier,CatBoostRanker

x=np.zeros((6,1),dtype=np.float32)
cats=np.array([[b'cat:1',b'electronics.phone',b'a'],[b'cat:2',b'electronics.tablet',b'b']]*3,dtype=object)
y=np.array([0,1,0,1,0,1],dtype=np.int8)
groups=np.array([0,0,1,1,2,2],dtype=np.int32)
assert x.dtype==np.float32 and cats.dtype==object and x.shape[0]==cats.shape[0]
assert all(isinstance(value,bytes) for value in cats.flat)
def features(values):
 return FeaturesData(num_feature_data=x,cat_feature_data=values,num_feature_names=['constant_counter'],
    cat_feature_names=['category_id_nominal','category_code','brand'])
result=dict(purpose='synthetic mixed-input API only; no REES46 fit/quality',catboost=catboost.__version__,models={})
for method in ['Logloss','PairLogit']:
 args=dict(iterations=2,depth=2,learning_rate=0.1,task_type='CPU',thread_count=2,
    bootstrap_type='No',boosting_type='Plain',random_seed=2026,allow_writing_files=False,
    use_best_model=False,one_hot_max_size=4096,verbose=False)
 if method=='Logloss':
  pool=Pool(features(cats),label=y,weight=np.full(6,.5))
  model=CatBoostClassifier(loss_function=method,**args)
 else:
  pool=Pool(features(cats),label=y,group_id=groups,pairs=np.array([[1,0],[3,2],[5,4]],dtype=np.int32),pairs_weight=np.ones(3))
  model=CatBoostRanker(loss_function=method,**args)
 started=time.monotonic();model.fit(pool)
 unseen=cats.copy();unseen[0]=[b'cat:new',b'unknown',b'__MISSING__']
 values=model.predict(features(unseen),prediction_type='RawFormulaVal') if method=='Logloss' else model.predict(features(unseen))
 assert np.asarray(values).shape==(6,) and np.isfinite(values).all()
 assert model.get_all_params()['one_hot_max_size']==4096
 model_path=Path(tempfile.gettempdir())/('tlab009-'+method+'-mixed.json');model.save_model(str(model_path),format='json')
 saved=json.loads(model_path.read_text())
 split_types=sorted({s['split_type'] for tree in saved['oblivious_trees'] for s in tree.get('splits',[])})
 assert 'OnlineCtr' not in split_types
 result['models'][method]=dict(status='pass',feature_count=pool.num_col(),cat_feature_indices=pool.get_cat_feature_indices(),
    tree_count=model.tree_count_,one_hot_max_size=model.get_all_params()['one_hot_max_size'],
    finite_unseen_predictions=True,split_types=split_types,seconds=time.monotonic()-started)
(Path(tempfile.gettempdir())/'tlab009-mixed-api-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

```
