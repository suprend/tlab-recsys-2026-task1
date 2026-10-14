# Round007: source archive of the failed synthetic check

Original check preserved with only a portable temporary path. **Do not run this as an approved experiment:** it already consumed3fits, saved2BCEmodels and failed at Ranker.predict(prediction_type). No fourth or retryfit was issued. The final complete branch below was never reached; [partial evidence](round-007-partial-result.json) is the actual outcome. Its output guard checks result.json only and is not the project-wide immutablefitclaim used by008. Fit thread_count=2 is explicit, but Pool/defaultpredict thread budgets were not independently asserted here; no all-stage2core or exactCPU benchmark is claimed. This archival code intentionally retains its meaningful API defect. Correct API and source conclusions are discussed in [round007](round-007.md); accepted008 separately enforces Pool/predict threads.

```python
"""Four tiny synthetic fits; never imports project code or opens real data."""
import json, resource, signal, time, tempfile
from pathlib import Path
START = time.monotonic()
def timeout(*_): raise TimeoutError('60 second research cap')
signal.signal(signal.SIGALRM, timeout)
signal.alarm(60)
resource.setrlimit(resource.RLIMIT_CPU, (55, 55))
import numpy as np
import catboost
from catboost import Pool, CatBoostClassifier, CatBoostRanker
ROOT = Path(tempfile.gettempdir()) / 'tlab-round007-weight-scale'
ROOT.mkdir(exist_ok=True)
assert not (ROOT/'result.json').exists(), 'Preserve immutable previous experiment'
def guard():
    assert time.monotonic()-START < 60
    assert resource.getrusage(resource.RUSAGE_SELF).ru_maxrss < 300_000_000
guard()
x = np.array([[0,0],[1,0],[0,1],[1,1],[2,1],[3,1],
              [0,2],[1,2],[2,2],[3,2],[4,2],[5,2],
              [0,3],[2,3],[5,3]], dtype=np.float32)
y = np.array([0,1,0,0,1,0,0,1,0,0,1,0,0,0,0], dtype=np.int8)
groups = np.repeat(np.arange(4,dtype=np.int32), [2,4,6,3])
w = np.repeat([1/2,1/4,1/6,1/3], [2,4,6,3])
pairs=[]; pair_weights=[]
for g in range(3):
    ids=np.flatnonzero(groups[:12]==g)
    pos=ids[y[ids]==1]; neg=ids[y[ids]==0]
    for a in pos:
        for b in neg:
            pairs.append([int(a),int(b)])
            pair_weights.append(1/(len(pos)*len(neg)))
pairs=np.array(pairs,dtype=np.int32); pair_weights=np.array(pair_weights)
assert np.allclose([w[groups==g].sum() for g in range(4)], 1)
assert np.allclose([sum(pair_weights[n] for n,(a,b) in enumerate(pairs) if groups[a]==g) for g in range(3)],1)
args=dict(iterations=3, depth=2, learning_rate=.1,l2_leaf_reg=3,
          task_type='CPU',thread_count=2,random_seed=2026,bootstrap_type='No',
          random_strength=0,boosting_type='Plain',leaf_estimation_method='Newton',
          leaf_estimation_iterations=1,leaf_estimation_backtracking='No',
          score_function='L2',allow_writing_files=False,use_best_model=False,verbose=False)
predictions={}; saved_models={}
result=dict(purpose='synthetic weight-scale mechanism, no REES46 or model quality',
            catboost=catboost.__version__, scale_values=[1,16],
            row_count=15,pair_fit_row_count=12,query_sizes=[2,4,6,3],
            pair_count=int(len(pairs)),bce_mass_per_query=[1]*4,pair_mass_per_informative_query=[1]*3,
            bce_weighted_positive_rate=float(np.dot(w,y)/sum(w)),fits=[])
for method in ['Logloss','PairLogit']:
    for k in [1,16]:
        guard()
        if method=='Logloss':
            pool=Pool(x,label=y,weight=w*k)
            model=CatBoostClassifier(loss_function=method,boost_from_average=False,**args)
        else:
            pool=Pool(x[:12],label=y[:12],group_id=groups[:12],pairs=pairs,pairs_weight=pair_weights*k)
            model=CatBoostRanker(loss_function=method,**args)
        tick=time.monotonic(); model.fit(pool); guard()
        p=np.asarray(model.predict(x,prediction_type='RawFormulaVal'),dtype=float)
        assert np.isfinite(p).all()
        key=f'{method}-k{k}'
        predictions[key]=p
        path=ROOT/(key+'.json');model.save_model(str(path),format='json')
        saved=json.loads(path.read_text());saved_models[key]=saved
        params=model.get_all_params()
        result['fits'].append(dict(key=key,seconds=time.monotonic()-tick,
            effective_params={a:params.get(a) for a in [*args,'loss_function','boost_from_average']},
            scale_bias=model.get_scale_and_bias(),raw_predictions=p.tolist(),
            leaf_values=model.get_leaf_values().tolist()))
result['comparisons']={}
for method in ['Logloss','PairLogit']:
    a,b=[f'{method}-k{k}' for k in [1,16]]
    p=predictions[a]
    if method=='Logloss':
        losses=np.logaddexp(0,p)-y*p
        hand=[float(np.dot(w*k,losses)/sum(w*k)) for k in [1,16]]
    else:
        losses=np.array([np.logaddexp(0,-(p[a]-p[b])) for a,b in pairs])
        hand=[float(np.dot(pair_weights*k,losses)/sum(pair_weights*k)) for k in [1,16]]
    result['comparisons'][method]=dict(
        max_abs_raw_difference=float(np.max(np.abs(predictions[a]-predictions[b]))),
        same_tree_splits=[t.get('splits') for t in saved_models[a]['oblivious_trees']]==[t.get('splits') for t in saved_models[b]['oblivious_trees']],
        normalized_hand_loss_at_same_fixed_predictions=hand)
result.update(wall_seconds=time.monotonic()-START,
              cpu_seconds=sum(resource.getrusage(resource.RUSAGE_SELF)[i] for i in [0,1]),
              rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              fit_attempts=4,status='complete')
guard();(ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
signal.alarm(0)
print(json.dumps({k:result[k] for k in ['catboost','comparisons','wall_seconds','cpu_seconds','rss_peak_bytes','fit_attempts','status']}))

```
