# Independent009 saved-model oracle: accepted

Historical audit source, only machine paths made portable. Run from project root with the accepted metadata-ablation output directory as argument; produces a system-temporary aggregate evidence file. No production loaders or model fitting. Successful process exit, external parent resource receipt and exact output/metadata scope checks are required in addition to the status file. Initial strict float-parameter assertion failure is retained; accepted observer tolerates CBM decimal metadata serialization only.

```python
"""Independent saved009 model replay; no production loaders or estimators fitted."""
from pathlib import Path
from collections import defaultdict
import json,hashlib,math,sys,random,time,resource,threading
START=time.monotonic();CPU=time.process_time()
import numpy as np
import duckdb
from catboost import CatBoostClassifier,FeaturesData,Pool
ROOT=Path.cwd().resolve();D=Path(sys.argv[1]).resolve();assert D.is_relative_to(ROOT/'artifacts/metadata-ablation')
OUT=(Path(__import__('tempfile').gettempdir())/'tlab009-model-output-evidence.json');assert not OUT.exists()
canon=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
read=lambda p:json.loads(Path(p).read_text())
R=read(D/'report.json');M=read(D/'run.json');I=M['identity'];assert not (D/'report.failed.json').exists()
assert R['status']=='complete_produced_unreviewed' and R['run_id']==M['run_id']==D.name
assert hashlib.sha256(canon(I).encode()).hexdigest()==D.name
assert I['role']=='metadata_price_single_ablation' and R['fit_attempt_count']==1
assert all(z['status']=='complete' for z in R['stages'])
con=duckdb.connect();con.execute('SET threads=2');con.execute("SET memory_limit='2GB'");con.execute("SET max_temp_directory_size='2GB'")
expired=threading.Event()
def guard():
 if expired.is_set() or time.monotonic()-START>1200 or time.process_time()-CPU>900:raise TimeoutError('Independent009 replay budget')
 rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
 if rss>8*2**30:raise MemoryError('Independent009 replay RSS')
def interrupt():expired.set();con.interrupt()
timer=threading.Timer(1200,interrupt);timer.daemon=True;timer.start();cache={}
def sha(p):
 p=Path(p)
 if p not in cache:
  h=hashlib.sha256()
  with p.open('rb') as f:
   while block:=f.read(8*1024*1024):guard();h.update(block)
  cache[p]=h.hexdigest()
 return cache[p]
def floats(a):
 return np.asarray(a.astype(np.float32).filled(np.nan),dtype=np.float32) if np.ma.isMaskedArray(a) else np.asarray(a,dtype=np.float32)
def metrics(scores,groups,items,qrows,targets):
 order=np.lexsort((items,-scores,groups));result={};offset=0
 for g,(qid,user) in enumerate(qrows):
  end=offset
  while end<len(order) and groups[order[end]]==g:end+=1
  chosen=items[order[offset:min(end,offset+20)]];ys=targets.get(qid,set())
  if ys:
   hits=[j for j,item in enumerate(chosen,1) if int(item) in ys]
   result[qid]=dict(recall=len(hits)/len(ys),ndcg=sum(1/math.log2(j+1) for j in hits)/sum(1/math.log2(j+1) for j in range(1,min(20,len(ys))+1)),average_precision=sum(k/j for k,j in enumerate(hits,1))/len(ys),reciprocal_rank=1/hits[0] if hits else 0.)
  offset=end
 assert offset==len(order)
 users=defaultdict(list);positive=defaultdict(list)
 for qid,user in qrows:
  users[user].append(qid)
  if qid in result:positive[user].append(qid)
 summary={e:{} for e in ['conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero']}
 for name in ['recall','ndcg','average_precision','reciprocal_rank']:
  total=sum(v[name] for v in result.values())
  summary['conditional_macro_query'][name]=total/len(result)
  summary['all_query_zero'][name]=total/len(qrows)
  summary['conditional_user_macro'][name]=sum(sum(result[q][name] for q in qs)/len(qs) for qs in positive.values())/len(positive)
  summary['all_user_macro_zero'][name]=sum(sum(result[q][name] if q in result else 0 for q in qs)/len(qs) for qs in users.values())/len(users)
 return result,summary,users
try:
 assert len(I['fingerprints'])==192
 for name,h in {**I['fingerprints'],M['execution_approval']['path']:M['execution_approval']['sha256'],**M['outputs']}.items():assert sha(ROOT/name)==h,name
 assert M['outputs']==R['artifacts'] and set(Path(p).name for p in M['outputs'])=={'Logloss.cbm','Logloss-scores.npz','Logloss.json'}
 approval=read(ROOT/M['execution_approval']['path']);assert approval==dict(version=1,approved=True,scope=I['role'],run_id=D.name,fingerprints=I['fingerprints'])
 claim=read(ROOT/R['fit_budget_claim']);assert claim==dict(version=1,scope=I['role'],run_id=D.name,allowed_fit_attempts=1,consumed_before='matrix_Pool_fit_preparation',output_directory=str(D.relative_to(ROOT)))
 full=read(ROOT/'artifacts/metadata-price-development'/I['metadata_run_id']/'run.json')
 control=ROOT/'artifacts/training'/I['control_run_id'];controlreport=read(control/'report.json')
 spec=read(ROOT/'configs/features/metadata-price.json');meta_names=spec['numeric_columns'];cat_names=spec['nominal_columns'];assert len(meta_names)==15 and len(cat_names)==3
 trainpop=None;traincard=None;base_names=None
 for role in ['train','selection']:
  cd=ROOT/'artifacts/development'/full['identity']['collections'][role];state=read(cd/'state.json');refs={'q':[],'y':[],'f':[]}
  for entry in state['shards']:
   for kind,key,v in [('anchor','queries','q'),('anchor','labels','y'),('features','features','f')]:
    child=read(ROOT/entry[kind]['directory']/'run.json');refs[v].append(str(ROOT/child['artifact_refs'][key]))
  for v,paths in refs.items():con.read_parquet(paths).create_view(role+'_'+v)
  con.read_parquet([str(ROOT/day['artifacts']['features']['path']) for day in full['outputs'][role]]).create_view(role+'_a')
  limit=' LIMIT 6000' if role=='train' else ''
  con.execute('CREATE TEMP TABLE '+role+'_chosen AS SELECT *,row_number()OVER(ORDER BY query_id)-1 idx FROM (SELECT * FROM '+role+'_q ORDER BY sha256(query_id),query_id'+limit+')')
  # Independence: direct parquet SQL; no model_data/train_baselines functions.
  con.execute('CREATE TEMP VIEW '+role+'_rows AS SELECT f.*,q.idx,(y.product_id IS NOT NULL)::INT expected_y FROM '+role+'_f f JOIN '+role+'_chosen q USING(query_id) LEFT JOIN '+role+'_y y USING(query_id,product_id)')
  assert con.execute('SELECT count(*)-count(DISTINCT(query_id,product_id)) FROM '+role+'_rows').fetchone()[0]==0
  assert con.execute('SELECT count(*) FROM (SELECT query_id,product_id FROM '+role+'_rows EXCEPT ALL SELECT query_id,product_id FROM '+role+'_a SEMI JOIN '+role+'_chosen USING(query_id))').fetchone()[0]==0
  poprows=con.execute('SELECT query_id,count(*) n,sum(expected_y) p FROM '+role+'_rows GROUP BY query_id').fetchall()
  qrows_role=con.execute('SELECT query_id,user_id FROM '+role+'_chosen ORDER BY idx').fetchall()
  fullpositive=con.execute('SELECT count(DISTINCT y.query_id) FROM '+role+'_y y JOIN '+role+'_chosen USING(query_id)').fetchone()[0]
  rowmass=sum(n*(1/n) for _,n,p in poprows)
  if role=='train':
   trainpop=dict(queries=len(qrows_role),candidate_rows=sum(n for _,n,p in poprows),nonempty_candidate_groups=len(poprows),empty_candidate_groups=len(qrows_role)-len(poprows),informative_groups=sum(0<p<n for _,n,p in poprows),all_negative_groups=sum(p==0 for _,n,p in poprows),all_positive_groups=sum(p==n for _,n,p in poprows),positive_fullY_queries=fullpositive,retrieved_positive_rows=sum(p for _,n,p in poprows),zero_gradient_pairwise_groups=len(qrows_role)-sum(0<p<n for _,n,p in poprows),row_weight_sum=rowmass)
   for name,v in trainpop.items():assert math.isclose(R['training'][name],v,abs_tol=1e-8),(name,v,R['training'][name])
   assert R['training']['trained_rows']==trainpop['candidate_rows'] and R['training']['explicit_pairs']==0 and R['training']['row_weight']=='1/|Cq|'
   traincard={name:con.execute('SELECT count(DISTINCT a."'+name+'") FROM train_a a SEMI JOIN train_chosen q USING(query_id)').fetchone()[0] for name in cat_names}
   assert traincard==R['training']['encoded_train_cardinality'] and max(traincard.values())<=4096
  else:
   qrows=qrows_role;targets=defaultdict(set)
   for q,item in con.execute('SELECT query_id,product_id FROM selection_y').fetchall():targets[q].add(item)
   excluded={'query_id','user_id','product_id','anchor','candidate_category_id','last_user_event_time'}
   base_names=[z[0] for z in con.execute('DESCRIBE selection_f').fetchall() if z[0] not in excluded]
   fields=['CAST(f."'+name+'" AS FLOAT) AS "'+name+'"' for name in base_names]
   fields+=['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds','CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
   base_names+=['retrieval_last_event_age_seconds','retrieval_last_event_missing'];names=base_names+meta_names
   fields+=['CAST(a."'+name+'" AS FLOAT) AS "'+name+'"' for name in meta_names]+['a."'+name+'"' for name in cat_names]
   assert len(base_names)==41 and names==I['numeric_features']==R['feature_names'] and cat_names==I['categorical_features']==R['categorical_names']
   arrays=con.execute('SELECT f.idx,f.product_id,'+','.join(fields)+' FROM selection_rows f JOIN selection_a a USING(query_id,product_id) ORDER BY f.idx,f.product_id').fetchnumpy()
   x=np.column_stack([floats(arrays[n]) for n in names]);groups=np.asarray(arrays['idx'],dtype=np.int32);items=np.asarray(arrays['product_id'],dtype=np.int64)
   cats=np.empty((len(groups),3),dtype=object)
   for j,name in enumerate(cat_names):
    values=arrays[name];assert all(isinstance(v,str) for v in values)
    encoding={v:v.encode('utf8') for v in set(values)};cats[:,j]=[encoding[v] for v in values]
   assert len(groups)==817149 and len(qrows)==4000 and not np.isinf(x).any();del arrays
 guard()
 model=CatBoostClassifier();model.load_model(str(D/'Logloss.cbm'));params=model.get_all_params()
 assert model.tree_count_==50 and model.feature_names_==names+cat_names
 def same_param(left,right):
  # Saved CBM metadata serializes some floating parameters to fewer decimals.
  return math.isclose(left,right,rel_tol=1e-8,abs_tol=1e-12) if type(left) is float and type(right) is float else type(left) is type(right) and left==right
 assert set(params)==set(R['actual_model_parameters']) and all(same_param(params[k],R['actual_model_parameters'][k]) for k in params)
 oldparams=next(s for s in controlreport['fit_attempts'] if s['method']=='Logloss')['actual_model_parameters']
 for key in ['loss_function','iterations','depth','learning_rate','l2_leaf_reg','random_seed','task_type','boosting_type','bootstrap_type','leaf_estimation_method','leaf_estimation_iterations','leaf_estimation_backtracking','random_strength','boost_from_average','use_best_model','border_count','nan_mode','rsm']:assert same_param(params[key],oldparams[key]),key
 assert params['one_hot_max_size']==4096
 body=read(D/'Logloss.json');assert len(body['oblivious_trees'])==50 and not body.get('features_info',{}).get('ctrs')
 splittypes=defaultdict(int)
 for tree in body['oblivious_trees']:
  for split in tree.get('splits') or []:splittypes[split['split_type']]+=1;assert split['split_type']!='OnlineCtr'
 pool=Pool(FeaturesData(num_feature_data=x,cat_feature_data=cats,num_feature_names=names,cat_feature_names=cat_names),thread_count=2)
 predicted=model.predict(pool,prediction_type='RawFormulaVal',thread_count=2);guard()
 with np.load(D/'Logloss-scores.npz',allow_pickle=False) as saved:
  assert set(saved.files)=={'group','product_id','raw_score'} and np.array_equal(saved['group'],groups) and np.array_equal(saved['product_id'],items)
  assert np.isfinite(predicted).all() and np.allclose(predicted,saved['raw_score'],rtol=0,atol=1e-12)
 own,summary,users=metrics(predicted,groups,items,qrows,targets)
 for estimand,vs in summary.items():
  for name,value in vs.items():assert math.isclose(R['metrics'][estimand][name],value,abs_tol=1e-12),(estimand,name)
 assert R['metrics']['query_count']==4000 and R['metrics']['nonempty_query_count']==len(own)==73
 # Independently replay unchanged numeric control on our own41-column assembly.
 controlmodel=CatBoostClassifier();controlmodel.load_model(str(control/'Logloss.cbm'))
 control_pred=controlmodel.predict(x[:,:41],prediction_type='RawFormulaVal',thread_count=2)
 with np.load(control/'Logloss-scores.npz',allow_pickle=False) as saved:
  assert np.array_equal(saved['group'],groups) and np.array_equal(saved['product_id'],items) and np.allclose(control_pred,saved['raw_score'],rtol=0,atol=1e-12)
 old,oldsummary,_=metrics(control_pred,groups,items,qrows,targets)
 ids=list(users);left=np.array([sum(own[q]['ndcg'] for q in qs if q in own) for qs in users.values()]);right=np.array([sum(old[q]['ndcg'] for q in qs if q in old) for qs in users.values()]);den=np.array([sum(q in own for q in qs) for qs in users.values()]);rng=random.Random(2026);samples=[]
 for _ in range(200):
  draw=rng.choices(range(len(ids)),k=len(ids));weights=np.bincount(draw,minlength=len(ids));n=weights@den;samples.append(float(weights@left/n-weights@right/n) if n else None)
 comparison=R['comparison'];assert comparison['replicates']==200 and comparison['undefined_draws']==sum(v is None for v in samples)
 for actual,expected in zip(comparison['samples'],samples):assert (actual is None and expected is None) or math.isclose(actual,expected,abs_tol=1e-12)
 assert len(comparison['samples'])==200 and np.allclose(comparison['interval_95'],np.quantile([v for v in samples if v is not None],[.025,.975]),rtol=0,atol=1e-12)
 delta=summary['conditional_macro_query']['ndcg']-oldsummary['conditional_macro_query']['ndcg'];assert math.isclose(comparison['estimate'],delta,abs_tol=1e-12)
 values=summary['conditional_macro_query'];keep=values['recall']>=.5792133072407045 and values['ndcg']>.41444755081727774+1e-12
 assert R['decision']['retain_metadata_block'] is keep and R['decision']['feature_choice']==('base41_plus_metadata18' if keep else 'base41')
 guard();evidence=dict(status='independently_accepted_single_metadata_ablation_outputs',run_id=D.name,input_pins=192,fit_attempts=1,independent_refits=0,train_population=trainpop,train_encoded_cardinality=traincard,selection_queries=len(qrows),selection_candidate_rows=len(groups),selection_full_targets=sum(len(y) for y in targets.values()),selection_positive_queries=len(own),numeric_features=len(names),categorical_features=len(cat_names),all_raw_scores_replayed=True,unchanged_control_scores_replayed=True,all_four_estimands_recomputed=True,paired_user_bootstrap_recomputed=True,metrics=summary,control_metrics=oldsummary,comparison=R['comparison'],decision=R['decision'],model_split_types=dict(splittypes),verification_wall_seconds=time.monotonic()-START,verification_actual_cpu_seconds=time.process_time()-CPU,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),limits=dict(wall_seconds=1200,actual_cpu_seconds=900,rss_bytes=8*2**30))
 OUT.write_text(json.dumps(evidence,indent=2)+'\n');guard();print(json.dumps(evidence))
finally:timer.cancel();con.close()

```
