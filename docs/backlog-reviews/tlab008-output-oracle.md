# TLAB-008: independent output audit script archive

This is the actual read-only model replay/oracle with only repository and temporary-directory paths made portable. It is an audit record, not the hardened public regeneration CLI proposed for018. Run from the project root with its locked environment and existing accepted input/model artifacts. It uses assert statements, so Python optimization must be disabled; unsupported inputs abort. It fits no models and writes only aggregate evidence to a temporary directory. The [accepted result](tlab008-smoke-output-verification.md) was obtained before this path-only archival conversion; no extra replay or fit is claimed.

```python
from pathlib import Path
from collections import defaultdict
import json,hashlib,math,sys,random,time,resource,threading,tempfile
import numpy as np
import duckdb
from catboost import CatBoostClassifier,CatBoostRanker
root=Path.cwd().resolve();d=Path(sys.argv[1]).resolve();assert d.is_relative_to(root/'artifacts')
r=json.loads((d/'report.json').read_text());m=json.loads((d/'run.json').read_text());identity=m['identity'];config=identity['config']
assert r['status']=='complete_produced_unreviewed' and r['run_id']==m['run_id']==d.name
canon=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
assert hashlib.sha256(canon(identity).encode()).hexdigest()==d.name
started=time.monotonic();cpu0=resource.getrusage(resource.RUSAGE_SELF);expired=threading.Event();con=duckdb.connect()
con.execute('SET threads=2');con.execute("SET memory_limit='2GB'");con.execute("SET max_temp_directory_size='2GB'")
def guard():
 if expired.is_set() or time.monotonic()-started>600:raise TimeoutError('Independent008 verification cap')
 if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>8*2**30:raise MemoryError('Independent008 RSS gate')
def stop():expired.set();con.interrupt()
timer=threading.Timer(600,stop);timer.daemon=True;timer.start()
cache={}
def sha(p):
 if p not in cache:
  h=hashlib.sha256()
  with p.open('rb') as f:
   while b:=f.read(8*1024*1024):guard();h.update(b)
  cache[p]=h.hexdigest()
 return cache[p]
try:
 for name,h in {**identity['fingerprints'],m['fit_approval']['path']:m['fit_approval']['sha256']}.items():assert sha(root/name)==h,name
 assert r['fit_attempt_count']==2 and len(r['fit_attempts'])==2 and all(z['status']=='complete' for z in r['fit_attempts'])
 assert all(z['status']=='complete' for z in r['stages']) and r['seconds']<config['wall_seconds'] and r['process_peak_rss_bytes']<8*2**30
 claim=json.loads((root/r['fit_budget_claim']).read_text());assert claim['run_id']==d.name and claim['allowed_fit_attempts']==2 and root/claim['output_directory']==d
 collections={}
 for role in ['train','selection']:
  cid=identity[role+'_collection_id'];cd=root/'artifacts/development'/cid;s=json.loads((cd/'state.json').read_text())
  assert s['collection_id']==cid and s['status']=='complete_produced_unreviewed'
  refs={k:[] for k in ['q','y','f']}
  for entry in s['shards']:
   for kind,key,v in [('anchor','queries','q'),('anchor','labels','y'),('features','features','f')]:
    sm=json.loads((root/entry[kind]['directory']/'run.json').read_text());refs[v].append(str(root/sm['artifact_refs'][key]))
  for v,paths in refs.items():con.read_parquet(paths).create_view(role+'_'+v)
  if role=='train':
   con.execute('CREATE TEMP TABLE train_selected AS SELECT * FROM train_q ORDER BY sha256(query_id),query_id LIMIT ?',[config['training_query_cap']])
   con.execute('CREATE TEMP VIEW train_target_rows AS SELECT f.query_id,f.product_id,(y.product_id IS NOT NULL)::INT y FROM train_f f JOIN train_selected USING(query_id) LEFT JOIN train_y y USING(query_id,product_id)')
   rows=con.execute('SELECT query_id,count(*) n,sum(y) p FROM train_target_rows GROUP BY query_id').fetchall()
   allq=con.execute('SELECT query_id FROM train_selected').fetchall();fullpos=con.execute('SELECT count(DISTINCT y.query_id) FROM train_y y JOIN train_selected USING(query_id)').fetchone()[0]
   pop=dict(queries=len(allq),candidate_rows=sum(n for _,n,p in rows),informative_groups=sum(0<p<n for _,n,p in rows),all_negative_groups=sum(p==0 for _,n,p in rows),all_positive_groups=sum(p==n for _,n,p in rows),retrieved_positive_rows=sum(p for _,n,p in rows),positive_fullY_queries=fullpos)
   expected_pairs=sum(int(p)*int(n-p) for _,n,p in rows);expected_informative_rows=sum(n for _,n,p in rows if 0<p<n)
   for name,value in pop.items():assert r['training_population'][name]==value,(name,value,r['training_population'][name])
  else:
   qrows=con.execute('SELECT query_id,user_id FROM selection_q ORDER BY query_id').fetchall();targets=defaultdict(set)
   for q,i in con.execute('SELECT query_id,product_id FROM selection_y').fetchall():targets[q].add(i)
   con.execute('CREATE TEMP TABLE indexed AS SELECT *,row_number()OVER(ORDER BY query_id)-1 idx FROM selection_q')
   excluded={'query_id','user_id','product_id','anchor','candidate_category_id','last_user_event_time'}
   names=[z[0] for z in con.execute('DESCRIBE selection_f').fetchall() if z[0] not in excluded]
   fields=[f'CAST(f."{n}" AS FLOAT) AS "{n}"' for n in names]
   fields+=['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds','CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
   names+=['retrieval_last_event_age_seconds','retrieval_last_event_missing'];assert names==r['feature_names']
   arrays=con.execute('SELECT q.idx,f.product_id,'+','.join(fields)+' FROM selection_f f JOIN indexed q USING(query_id) ORDER BY q.idx,f.product_id').fetchnumpy()
   def floats(a):return np.asarray(a.astype(np.float32).filled(np.nan),dtype=np.float32) if np.ma.isMaskedArray(a) else np.asarray(a,dtype=np.float32)
   x=np.column_stack([floats(arrays[n]) for n in names]);group=np.asarray(arrays['idx'],dtype=np.int32);items=np.asarray(arrays['product_id'],dtype=np.int64)
   assert len(group)==r['selection_population']['candidate_rows'] and len(qrows)==r['selection_population']['queries'] and not np.isinf(x).any()
 results={};metric_summaries={}
 for step in r['fit_attempts']:
  guard();method=step['method'];assert method in ('Logloss','PairLogit')
  for rel,h in step['artifacts'].items():assert sha(root/rel)==h
  model=(CatBoostClassifier() if method=='Logloss' else CatBoostRanker());model.load_model(str(d/(method+'.cbm')))
  params=model.get_all_params();assert model.tree_count_==config['iterations']==step['tree_count'] and model.feature_names_==names
  for key,value in [('iterations',config['iterations']),('depth',config['depth']),('task_type','CPU'),('bootstrap_type','No'),('boosting_type','Plain'),('use_best_model',False)]:assert params[key]==value,(key,params[key],value)
  saved=np.load(d/(method+'-scores.npz'));assert set(saved.files)=={'group','product_id','raw_score'}
  assert np.array_equal(saved['group'],group) and np.array_equal(saved['product_id'],items)
  predicted=model.predict(x,prediction_type='RawFormulaVal',thread_count=2) if method=='Logloss' else model.predict(x,thread_count=2)
  assert np.isfinite(predicted).all() and np.allclose(predicted,saved['raw_score'],rtol=0,atol=1e-12)
  if method=='Logloss':assert step['training']['trained_rows']==pop['candidate_rows'] and step['training']['explicit_pairs']==0
  else:
   assert step['training']['trained_rows']==expected_informative_rows and step['training']['explicit_pairs']==expected_pairs
   assert math.isclose(step['training']['pair_weight_sum'],pop['informative_groups'],abs_tol=1e-10)
  order=np.lexsort((items,-predicted,group));query_metrics={};offset=0
  for g,(qid,user) in enumerate(qrows):
   stopi=offset
   while stopi<len(order) and group[order[stopi]]==g:stopi+=1
   chosen=items[order[offset:min(stopi,offset+config['k'])]];ys=targets[qid]
   if ys:
    hits=[rank for rank,pid in enumerate(chosen,1) if int(pid) in ys]
    query_metrics[qid]=dict(recall=len(hits)/len(ys),ndcg=sum(1/math.log2(rank+1) for rank in hits)/sum(1/math.log2(rank+1) for rank in range(1,min(config['k'],len(ys))+1)),average_precision=sum(n/rank for n,rank in enumerate(hits,1))/len(ys),reciprocal_rank=1/hits[0] if hits else 0.)
   offset=stopi
  assert offset==len(order)
  users=defaultdict(list);positive=defaultdict(list)
  for qid,user in qrows:
   users[user].append(qid)
   if qid in query_metrics:positive[user].append(qid)
  summary={}
  for metric in ['recall','ndcg','average_precision','reciprocal_rank']:
   values={e:None for e in ['conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero']}
   values['conditional_macro_query']=sum(z[metric] for z in query_metrics.values())/len(query_metrics)
   values['all_query_zero']=sum(z[metric] for z in query_metrics.values())/len(qrows)
   values['conditional_user_macro']=sum(sum(query_metrics[q][metric] for q in qs)/len(qs) for qs in positive.values())/len(positive)
   values['all_user_macro_zero']=sum(sum(query_metrics[q][metric] if q in query_metrics else 0 for q in qs)/len(qs) for qs in users.values())/len(users)
   for estimand,value in values.items():assert math.isclose(step['metrics'][estimand][metric],value,abs_tol=1e-12),(method,metric,estimand)
   summary[metric]=values['conditional_macro_query']
  assert step['metrics']['query_count']==len(qrows) and step['metrics']['nonempty_query_count']==len(query_metrics)
  results[method]=query_metrics;metric_summaries[method]=summary
 # Independent paired cluster ratio calculation, retaining all mature users.
 user_ids=list(users);left=np.array([sum(results['PairLogit'][q]['ndcg'] for q in qs if q in results['PairLogit']) for qs in users.values()]);right=np.array([sum(results['Logloss'][q]['ndcg'] for q in qs if q in results['Logloss']) for qs in users.values()]);den=np.array([sum(q in results['PairLogit'] for q in qs) for qs in users.values()])
 rng=random.Random(config['random_seed']);samples=[]
 for _ in range(config['bootstrap_replicates']):
  draw=rng.choices(range(len(user_ids)),k=len(user_ids));weights=np.bincount(draw,minlength=len(user_ids));n=weights@den
  samples.append(float(weights@left/n-weights@right/n) if n else None)
 actual=r['comparison'];assert len(samples)==actual['replicates'] and actual['undefined_draws']==sum(z is None for z in samples)
 for a,b in zip(samples,actual['samples']):assert (a is None and b is None) or math.isclose(a,b,abs_tol=1e-12)
 expected_interval=np.quantile([z for z in samples if z is not None],[.025,.975]);assert np.allclose(expected_interval,actual['interval_95'],rtol=0,atol=1e-12)
 assert math.isclose(actual['estimate'],metric_summaries['PairLogit']['ndcg']-metric_summaries['Logloss']['ndcg'],abs_tol=1e-12)
 guard();cpu1=resource.getrusage(resource.RUSAGE_SELF)
 evidence=dict(status='independently_accepted_smoke_outputs',run_id=d.name,train_population=pop,explicit_pairs=expected_pairs,selection_queries=len(qrows),selection_rows=len(group),positive_queries=sum(bool(v) for v in targets.values()),numeric_features=len(names),model_metrics=metric_summaries,all_raw_scores_replayed=True,all_four_estimands_recomputed=True,paired_bootstrap_recomputed=True,verification_seconds=time.monotonic()-started,verification_cpu_seconds=cpu1.ru_utime+cpu1.ru_stime-cpu0.ru_utime-cpu0.ru_stime,peak_rss_bytes=cpu1.ru_maxrss)
 (Path(tempfile.gettempdir())/'tlab008-actual-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))
finally:timer.cancel();con.close()

```
