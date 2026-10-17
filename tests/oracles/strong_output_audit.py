"""DRAFT independent zero-fit 019 observer. Actual launch needs reviewed controller/context.
No production feature/model loader, metric, ranking or chooser defines expected values.
"""
import time
START=time.monotonic()
import resource,sys,json,hashlib,math,random,argparse,threading,struct
from pathlib import Path
from collections import defaultdict

NAMES=('recall','ndcg','average_precision','reciprocal_rank')
ESTIMANDS=('conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero')
GRID=({'depth':4,'l2_leaf_reg':3},{'depth':4,'l2_leaf_reg':30},{'depth':6,'l2_leaf_reg':3},{'depth':6,'l2_leaf_reg':30})
TREES=(50,150,300)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def need(condition,message):
 if not condition:raise ValueError(message)
def ranking_order(scores,groups,items):
 import numpy as np
 need(scores.ndim==1 and scores.shape==groups.shape==items.shape and np.isfinite(scores).all(),'Finite score vector')
 return np.lexsort((items,-scores,groups))
def score_parity(predicted,replay,groups,items,message):
 import numpy as np
 need(replay.shape==predicted.shape and np.isfinite(replay).all() and np.allclose(predicted,replay,rtol=0,atol=1e-12),message)
 # All keyed candidate ranks matter, even outside top20 or positive full-Y.
 need(np.array_equal(ranking_order(predicted,groups,items),ranking_order(replay,groups,items)),message+' rankings differ')
def read_raw_json(raw):
 need(type(raw) is bytes,'JSON must use one immutable byte snapshot')
 def pairs(xs):
  out={}
  for k,v in xs:
   need(k not in out,'Duplicate JSON key');out[k]=v
  return out
 return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def read(path):return read_raw_json(Path(path).read_bytes())
def same(left,right):
 # CBM serialization only: no coercion of bool/int/string into numeric equality.
 if type(left) is float and type(right) is float:return math.isfinite(left) and math.isfinite(right) and math.isclose(left,right,rel_tol=1e-8,abs_tol=1e-12)
 return type(left) is type(right) and left==right
def validate_checkout(root,producer_root,producer_file):
 root=Path(root).resolve()
 need(Path(producer_root).resolve()==root and Path(producer_file).resolve()==root/'scripts/strong_baseline.py','Imported producer differs from trusted context checkout')

def effective_learning_rate(incumbent_params):
 # CatBoost converts the declared input .05 to float32. This specific contract
 # is distinct from saved-CBM float serialization tolerance in same().
 declared=.05;native=struct.unpack('!f',struct.pack('!f',declared))[0]
 value=incumbent_params['learning_rate']
 need(type(value) is float and same(native,value),'Accepted incumbent effective LR violates declared .05 float32 contract')
 return value

def compare(expected,observed,tolerance=1e-12):
 if isinstance(expected,dict):
  need(type(observed) is dict and set(expected)==set(observed),'Object schema differs')
  for k,v in expected.items():compare(v,observed[k],tolerance)
 elif isinstance(expected,(tuple,list)):
  need(type(observed) in (tuple,list) and len(expected)==len(observed),'Sequence schema differs')
  for x,y in zip(expected,observed):compare(x,y,tolerance)
 elif type(expected) is float:need(type(observed) in (int,float) and math.isfinite(observed) and math.isclose(expected,observed,rel_tol=0,abs_tol=tolerance),'Numeric value differs')
 else:need(type(expected) is type(observed) and expected==observed,'Scalar value/type differs')
def validate_worker_launch(body,*,parent_id,worker_id,slot,context_path,context_sha,log_path,root,executable):
 expected=dict(version=1,scope='strong_issued_worker_launch',parent_run_id=parent_id,worker_run_id=worker_id,context_path=context_path,issued_context_sha256=context_sha,slot=slot,argv=[executable,'-m','scripts.strong_baseline','--worker-context',context_path,'--issued-context-sha256',context_sha],cwd=str(root),log_path=log_path)
 compare(expected,body)

def worker_resource_policy(report,slot,*,successful):
 cpu=report['entry_actual_cpu_seconds'];children=report['entry_reaped_children_cpu_seconds'];peak=report['process_peak_rss_bytes']
 need(type(cpu) in (int,float) and math.isfinite(cpu) and cpu>=0 and type(children) in (int,float) and math.isfinite(children) and children==0 and type(peak) is int and peak>0,'Unknown worker usage/descendants')
 if successful:need(cpu<=slot['allocation']['cpu_seconds'] and peak<=slot['allocation']['rss_bytes'],'Successful worker exceeded issued resource limit')
 else:need(report['status']=='failed' and report['outcome']=='resource_failure' and report['error_type'] in {'MemoryError','TimeoutError','OutOfMemoryException'},'Unrecognized failed worker usage')
 # Failed resource trials can overshoot their cooperative individual threshold.
 # They stay ineligible; complete parent ledger must charge them under whole cap.
 return cpu,peak

def whole_resource_policy(report,children):
 values=[worker_resource_policy(c['report'],c['manifest']['identity']['slot'],successful=c['exit_code']==0) for c in children]
 used=report['actual_total_cpu_seconds'];self_used=report['actual_parent_cpu_seconds'];reaped=report['actual_reaped_children_cpu_seconds'];parent_peak=report['parent_peak_rss_bytes']
 need(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in [used,self_used,reaped]) and used<=3300 and used+1e-6>=self_used+reaped and math.fsum(v[0] for v in values)<=reaped+1e-6,'Whole producer CPU/unknown cost')
 need(type(parent_peak) is int and 0<parent_peak<=2**30 and parent_peak+max(v[1] for v in values)<=8*2**30,'Whole producer RSS exceeded8GiB')
 need(type(report['seconds']) in (int,float) and math.isfinite(report['seconds']) and 0<=report['seconds']<=3240,'Whole producer reserved wall exceeded')

def select(candidates):
 eligible=[c for c in candidates if c['metrics']['conditional_macro_query']['recall']>=.5792133072407045]
 need(bool(eligible),'No feasible candidate')
 top=max(c['metrics']['conditional_macro_query']['ndcg'] for c in eligible)
 return min((c for c in eligible if c['metrics']['conditional_macro_query']['ndcg']>=top-1e-12),key=lambda c:(c['trees'],c['depth'],not c['incumbent'],c['config_id']))
def metric_values(ranked,targets):
 if not targets:return None
 hits=[rank for rank,item in enumerate(ranked[:20],1) if item in targets]
 return dict(recall=len(hits)/len(targets),ndcg=math.fsum(1/math.log2(r+1) for r in hits)/math.fsum(1/math.log2(r+1) for r in range(1,min(20,len(targets))+1)),average_precision=math.fsum(n/r for n,r in enumerate(hits,1))/len(targets),reciprocal_rank=1/hits[0] if hits else 0.)
def summarize(qrows,targets,ranked):
 per={q:metric_values(ranked.get(q,()),targets.get(q,set())) for q,u in qrows}
 users={}
 for q,u in qrows:users.setdefault(u,[]).append(q)
 positive=[q for q,u in qrows if per[q] is not None];positive_users=[u for u,qs in users.items() if any(per[q] is not None for q in qs)]
 def mean(vs):return math.fsum(vs)/len(vs) if vs else None
 out=dict(k=20,query_count=len(qrows),mature_query_count=len(qrows),censored_query_count=0,nonempty_query_count=len(positive),mature_user_count=len(users),positive_user_count=len(positive_users),nonempty_fraction=len(positive)/len(qrows) if qrows else None)
 for e in ESTIMANDS:out[e]={}
 for name in NAMES:
  out['conditional_macro_query'][name]=mean([per[q][name] for q in positive])
  out['all_query_zero'][name]=mean([per[q][name] if per[q] else 0. for q,u in qrows])
  out['conditional_user_macro'][name]=mean([mean([per[q][name] for q in users[u] if per[q]]) for u in positive_users])
  out['all_user_macro_zero'][name]=mean([mean([per[q][name] if per[q] else 0. for q in qs]) for qs in users.values()])
 return out,per,users

def bootstrap(left,right,users):
 rng=random.Random(2026);ids=list(users);draws=[]
 def value(per,draw):
  vs=[per[q]['ndcg'] for u in draw for q in users[u] if per[q] is not None]
  return math.fsum(vs)/len(vs) if vs else None
 for _ in range(200):
  draw=rng.choices(ids,k=len(ids));a,b=value(left,draw),value(right,draw);draws.append(None if a is None else a-b)
 def percentile(v,p):
  pos=(len(v)-1)*p;i=math.floor(pos);j=math.ceil(pos);return v[i]*(1-(pos-i))+v[j]*(pos-i)
 valid=sorted(v for v in draws if v is not None);a,b=value(left,ids),value(right,ids)
 return dict(metric='ndcg',estimand='conditional_macro_query',seed=2026,replicates=200,user_count=len(ids),estimate=None if a is None else a-b,samples=draws,undefined_draws=200-len(valid),interval_95=[percentile(valid,.025),percentile(valid,.975)] if valid else None)

class Observer:
 def __init__(self,context_path,*,issued_context_sha256):
  self.path=Path(context_path).resolve()
  need(type(issued_context_sha256) is str and len(issued_context_sha256)==64 and all(z in '0123456789abcdef' for z in issued_context_sha256),'Invalid issuer launch digest')
  raw=self.path.read_bytes();need(len(raw)<=65536 and hashlib.sha256(raw).hexdigest()==issued_context_sha256,'Context differs from issuer launch digest')
  self.issued_context_sha256=issued_context_sha256;self.context=read_raw_json(raw);c=self.context
  need(set(c)=={'version','scope','run_id','project_root','invocation_directory','request_sha256','producer_manifest','producer_report','allocation','expected_verifier_source','issued_at_monotonic','output_path','failed_output_path'},'Unreviewed context schema')
  need(type(c['version']) is int and c['version']==1 and c['scope']=='independent_strong_baseline_verifier','Context scope')
  self.root=Path(c['project_root']).resolve();need(Path(c['project_root']).is_absolute(),'Context project root must be absolute')
  self.allocation=c['allocation'];a=self.allocation
  need(set(a)=={'cpu_seconds','deadline_monotonic','rss_bytes'} and type(a['cpu_seconds']) is int and 1<=a['cpu_seconds']<=300 and type(a['rss_bytes']) is int and a['rss_bytes']==7*2**30 and type(a['deadline_monotonic']) in (int,float) and math.isfinite(a['deadline_monotonic']) and START<a['deadline_monotonic'],'Invalid verifier allowance')
  self.con=None;self.timer=None;self.expired=threading.Event();self.stopped=threading.Event();self.hashes={};self.output=self.local(c['output_path']);self.failed_output=self.local(c['failed_output_path'])
  need(self.output==self.local(c['invocation_directory'])/'verification.json' and self.failed_output==self.output.parent/'verification.failed.json' and self.path==self.output.parent/'verification-context.json','Context/output detached')
  need(type(c['issued_at_monotonic']) in (int,float) and math.isfinite(c['issued_at_monotonic']) and 0<=c['issued_at_monotonic']<=START,'Context was not issued before observer start')
  need(not self.output.exists() and not self.failed_output.exists(),'Immutable observer output exists')
  self.self_sha=self.sha(Path(__file__).resolve());need(c['expected_verifier_source']==dict(path=str(Path(__file__).resolve()),sha256=self.self_sha),'Observer entry hash/path')
  self.context_sha=self.sha(self.path);need(self.context_sha==issued_context_sha256,'Context changed during initialization')
 def local(self,name):
  need(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts,'Nonlocal artifact path')
  p=(self.root/name).resolve();need(p.is_relative_to(self.root),'Artifact escaped root');return p
 def cpu(self):
  r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime
 def rss(self):return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1024 if sys.platform.startswith('linux') else 1))
 def guard(self):
  need(sys.platform=='darwin' or sys.platform.startswith('linux'),'Unsupported RSS units')
  if self.expired.is_set() or time.monotonic()>self.allocation['deadline_monotonic'] or self.cpu()>self.allocation['cpu_seconds']:raise TimeoutError('Shared verifier deadline/absolute CPU')
  if self.rss()>self.allocation['rss_bytes']:raise MemoryError('Verifier RSS7GiB')
  r=resource.getrusage(resource.RUSAGE_CHILDREN);need(r.ru_utime+r.ru_stime==0,'Forbidden observer subprocess')
 def sha(self,path):
  h=hashlib.sha256()
  with Path(path).open('rb') as f:
   while block:=f.read(4*1024*1024):self.guard();h.update(block)
  return h.hexdigest()
 def pins(self,pins):
  for n,h in pins.items():need(self.sha(self.local(n))==h,'Pinned file differs')
 def install_timer(self):
  def monitor():
   while not self.stopped.wait(.1):
    try:self.guard()
    except BaseException:
     self.expired.set()
     if self.con is not None:
      try:self.con.interrupt()
      except BaseException:pass
     return
  self.timer=threading.Thread(target=monitor,daemon=True);self.timer.start()
 def sql(self,sql):self.guard();result=self.con.execute(sql);self.guard();return result
 def atomic(self,body):
  tmp=Path(str(self.output)+'.temp');need(not tmp.exists(),'Observer temp exists');tmp.write_text(canonical(body)+'\n');tmp.replace(self.output)
 def binding(self):
  c=self.context;inv=self.local(c['invocation_directory']);request_path=inv/'verification-request.json'
  need(self.sha(request_path)==c['request_sha256'],'Request changed');request=read(request_path)
  need(set(request)=={'version','scope','run_id','producer_report','producer_manifest','controller_source','outer_deadline_monotonic','canonical_actual_cpu_seconds','maximum_verifier_cpu_seconds','verifier_rss_bytes'},'Request schema')
  need(type(request['version']) is int and request['version']==1 and request['scope']=='strong_baseline_verification_request' and request['run_id']==c['run_id'],'Request scope')
  need(request['producer_report']==c['producer_report'] and request['producer_manifest']==c['producer_manifest'],'Request producer refs')
  need(type(request['maximum_verifier_cpu_seconds']) in (int,float) and 0<self.allocation['cpu_seconds']<=request['maximum_verifier_cpu_seconds']<=300 and request['verifier_rss_bytes']==7*2**30 and self.allocation['deadline_monotonic']<=request['outer_deadline_monotonic']-20,'Request budget boundary')
  need(type(request['canonical_actual_cpu_seconds']) in (int,float) and 0<=request['canonical_actual_cpu_seconds']<=3600 and request['canonical_actual_cpu_seconds']+self.allocation['cpu_seconds']<=3600,'Shared CPU already spent')
  controller_path=Path(request['controller_source']['path']).resolve();need(self.sha(controller_path)==request['controller_source']['sha256'],'Controller hash')
  controller=read(inv/'report.json');need(not (inv/'report.failed.json').exists() and controller['status']=='verifier_running' and controller['run_id']==c['run_id'] and controller['verifier_calls']==1 and controller['producer_calls']==1,'Controller phase/known failure')
  launch=controller['verifier_launch'];need(launch['issued_context_sha256']==self.context_sha and launch['allocation']==self.allocation and launch['argv'][-2:]==['--issued-context-sha256',self.context_sha],'Controller launch seal')
  ar=controller['verifier_approval'];need(self.sha(self.local(ar['path']))==ar['sha256'],'Verifier approval pin')
  approval=read(self.local(ar['path']));compare(dict(version=1,approved=True,scope=c['scope'],run_id=c['run_id'],request_sha256=c['request_sha256'],controller_sha256=request['controller_source']['sha256'],entry_path=str(Path(__file__).resolve()),entry_sha256=self.self_sha),approval)
  refs={v['path']:v['sha256'] for v in [c['producer_manifest'],c['producer_report']]};self.pins(refs)
  manifest=read(self.local(c['producer_manifest']['path']));report=read(self.local(c['producer_report']['path']));directory=self.local(c['producer_report']['path']).parent
  need(directory==self.root/'artifacts/strong-baseline'/c['run_id'] and self.local(c['producer_manifest']['path'])==directory/'run.json','Producer receipt path')
  need(not (directory/'report.failed.json').exists() and report['status']=='complete_produced_unreviewed' and report['run_id']==manifest['run_id']==c['run_id'],'Producer incomplete/failed')
  need(digest(manifest['identity'])==c['run_id'],'Producer digest')
  sys.path.insert(0,str(self.root))
  # Mechanical lineage only. Never use strong/train/model_data metrics/loaders/choose.
  from scripts import strong_baseline as strong
  validate_checkout(self.root,strong.ROOT,strong.__file__)
  i=manifest['identity'];accept=i['acceptance_refs'];spec_path='configs/models/strong-grid.json'
  plan,inputs=strong.prepare_plan(self.local(spec_path),self.local(i['base_config']),self.local(accept['train']),self.local(accept['selection']),self.local(accept['ablation']),check=self.guard)
  compare(plan['identity'],i);need(plan['run_id']==c['run_id'],'Actual plan differs')
  self.pins(i['fingerprints']);self.pins(manifest['outputs'])
  er=manifest['execution_approval'];self.pins({er['path']:er['sha256']});compare(dict(version=1,approved=True,scope='strong_baseline_search',run_id=c['run_id'],fingerprints=i['fingerprints']),read(self.local(er['path'])))
  parent=read(directory/'plan.json');compare({k:manifest[k] for k in ('run_id','identity','execution_approval','budget_claim')},parent)
  claim=parent['budget_claim'];need(claim['path']=='artifacts/fit-claims/tlab019-strong-grid.json','Global claim path');self.pins({claim['path']:claim['sha256']})
  compare(dict(version=1,scope='strong_baseline_search',run_id=c['run_id'],allowed_fit_attempts=4,allowed_gate_attempts=1,allowed_look_slots=12,output_directory=str(directory.relative_to(self.root)),execution_approval=er,slot_paths=[str((directory/'slots'/n).relative_to(self.root)) for n in ['gate.json',*[f'arm-{j}.json' for j in range(4)]]]),read(self.local(claim['path'])))
  need(report['fit_attempt_count']<=4 and report['new_reserved_look_slots']<=12 and not report['unknown_live_fit'],'Fit/look/unknown state')
  need(0<=report['actual_total_cpu_seconds']<=3300 and report['outer_deadline_monotonic']==request['outer_deadline_monotonic'],'Producer resource receipt')
  return manifest,report,directory,inputs,parent
 def collection(self,role,col,cap,arrays=False):
  import numpy as np
  for key,suffix in [('queries','q'),('candidates','c'),('features','f')]:self.con.read_parquet([str(self.local(p)) for p in col['refs'][key]]).create_view(role+'_'+suffix)
  q,c,f=role+'_q',role+'_c',role+'_f'
  need(self.sql(f'SELECT count(*)=count(DISTINCT query_id) AND count(*) FILTER(WHERE query_id IS NULL OR user_id IS NULL)=0 FROM {q}').fetchone()[0],'Query keys')
  limit='' if cap is None else ' LIMIT '+str(cap)
  self.sql(f'CREATE TEMP TABLE {role}_chosen AS SELECT *,row_number()OVER(ORDER BY query_id)-1 idx FROM (SELECT * FROM {q} ORDER BY sha256(query_id),query_id{limit})')
  qrows=self.sql(f'SELECT query_id,user_id FROM {role}_chosen ORDER BY idx').fetchall()
  need(len(qrows)==(4000 if role=='selection' else cap),'Fixed query population')
  self.sql(f'CREATE TEMP VIEW {role}_rows AS SELECT f.*,q.idx FROM {f} f JOIN {role}_chosen q USING(query_id)')
  r=role+'_rows'
  need(self.sql(f'SELECT count(*)=count(DISTINCT(query_id,product_id)) AND count(*) FILTER(WHERE product_id IS NULL)=0 FROM {r}').fetchone()[0],'Feature pair keys')
  need(self.sql(f'SELECT count(*) FROM ((SELECT query_id,product_id FROM {r} EXCEPT ALL SELECT query_id,product_id FROM {c} SEMI JOIN {role}_chosen USING(query_id)) UNION ALL (SELECT query_id,product_id FROM {c} SEMI JOIN {role}_chosen USING(query_id) EXCEPT ALL SELECT query_id,product_id FROM {r}))').fetchone()[0]==0,'C/F pair multiset')
  # First target relation is opened only after bottom-SHA choice and C/F key checks.
  self.con.read_parquet([str(self.local(p)) for p in col['refs']['labels']]).create_view(role+'_y')
  need(self.sql(f'SELECT count(*)=count(DISTINCT(query_id,product_id)) AND count(*) FILTER(WHERE product_id IS NULL)=0 FROM {role}_y').fetchone()[0],'FullY pair keys')
  targets=defaultdict(set)
  for qid,item in self.sql(f'SELECT y.query_id,y.product_id FROM {role}_y y SEMI JOIN {role}_chosen q USING(query_id) ORDER BY y.query_id,y.product_id').fetchall():targets[qid].add(int(item))
  pop=self.sql(f'SELECT r.query_id,count(*) n,count(y.product_id) p FROM {r} r LEFT JOIN {role}_y y USING(query_id,product_id) GROUP BY r.query_id').fetchall()
  n=sum(z[1] for z in pop);need(n<=len(qrows)*220,'Candidate population cap')
  summary=dict(queries=len(qrows),candidate_rows=n,nonempty_candidate_groups=len(pop),empty_candidate_groups=len(qrows)-len(pop),informative_groups=sum(0<p<n0 for _,n0,p in pop),all_negative_groups=sum(p==0 for _,n0,p in pop),all_positive_groups=sum(p==n0 for _,n0,p in pop),positive_fullY_queries=len(targets),retrieved_positive_rows=sum(p for _,_,p in pop),zero_gradient_pairwise_groups=len(qrows)-sum(0<p<n0 for _,n0,p in pop),matrix_bytes=n*41*4,row_weight_sum=float(len(pop)))
  if not arrays:return summary
  excluded={'query_id','user_id','product_id','anchor','candidate_category_id','last_user_event_time'}
  cols=[row[0] for row in self.sql(f'DESCRIBE {f}').fetchall()];need(excluded<=set(cols),'Manual schema keys')
  base=[z for z in cols if z not in excluded];need(len(base)==39 and len(set(base))==39 and all(z.replace('_','').isalnum() for z in base),'Base numeric schema')
  names=base+['retrieval_last_event_age_seconds','retrieval_last_event_missing']
  fields=[f'CAST("{name}" AS FLOAT) AS "{name}"' for name in base]+['CAST(epoch(anchor)-epoch(last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds','CAST(last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
  a=self.sql(f'SELECT idx,product_id,{",".join(fields)} FROM {r} ORDER BY idx,product_id').fetchnumpy()
  need(not np.ma.isMaskedArray(a['idx']) and not np.ma.isMaskedArray(a['product_id']) and np.issubdtype(a['product_id'].dtype,np.integer),'Exact nonnullable key transport')
  groups=np.asarray(a['idx'],dtype=np.int32);items=np.asarray(a['product_id'],dtype=np.int64)
  def numeric(v):return np.asarray(v.astype(np.float32).filled(np.nan),dtype=np.float32) if np.ma.isMaskedArray(v) else np.asarray(v,dtype=np.float32)
  x=np.column_stack([numeric(a[name]) for name in names]);need(x.shape==(n,41) and not np.isinf(x).any(),'Selection arrays')
  return x,groups,items,qrows,targets,names,summary
 def scored(self,scores,groups,items,qrows,targets):
  order=ranking_order(scores,groups,items);ranked={};offset=0
  for g,(q,u) in enumerate(qrows):
   end=offset
   while end<len(order) and groups[order[end]]==g:end+=1
   ranked[q]=[int(items[z]) for z in order[offset:min(end,offset+20)]];offset=end
  need(offset==len(order),'Ranking group cover');return summarize(qrows,targets,ranked)
 def npz(self,path,predicted,groups,items):
  import numpy as np
  with np.load(path,allow_pickle=False) as saved:
   need(set(saved.files)=={'group','product_id','raw_score'},'NPZ exact fields')
   need(np.issubdtype(saved['group'].dtype,np.integer) and np.issubdtype(saved['product_id'].dtype,np.integer),'NPZ key dtypes')
   need(np.array_equal(saved['group'],groups) and np.array_equal(saved['product_id'],items),'NPZ sorted exact keys')
   score_parity(predicted,saved['raw_score'],groups,items,'Saved score replay')
 def model(self,path,trees,names,params):
  from catboost import CatBoostClassifier
  m=CatBoostClassifier();m.load_model(str(path));self.guard();need(m.tree_count_==trees and m.feature_names_==names and m.get_cat_feature_indices()==[] and m.get_text_feature_indices()==[],'Saved numeric model trees/features')
  actual=m.get_all_params();need(set(actual)==set(params) and all(same(actual[k],params[k]) for k in params),'Loaded CBM effective parameters')
  return m
 def execute(self):
  import numpy as np,duckdb
  self.install_timer();m,r,d,inputs,parent=self.binding();self.guard()
  self.con=duckdb.connect(':memory:');self.sql('SET threads=2');self.sql("SET memory_limit='2GB'");self.sql("SET max_temp_directory_size='0B'")
  x,g,it,qrows,targets,names,selection=self.collection('selection',inputs['selection'],None,True);need(names==m['identity']['feature_names'],'Independent41 names')
  control=inputs['control']['control'];inc=m['identity']['incumbent'];compare(control,inc)
  oldmodelpath=next(p for p in control['artifacts'] if p.endswith('.cbm'));oldscorepath=next(p for p in control['artifacts'] if p.endswith('.npz'))
  oldmodel=self.model(self.local(oldmodelpath),50,names,control['actual_model_parameters']);oldpred=np.asarray(oldmodel.predict(x,prediction_type='RawFormulaVal',thread_count=2));self.guard();self.npz(self.local(oldscorepath),oldpred,g,it)
  oldmetrics,oldper,users=self.scored(oldpred,g,it,qrows,targets);compare(oldmetrics,control['metrics'])
  incumbent=dict(config_id='incumbent-'+m['identity']['incumbent_run_id'],incumbent=True,trees=50,trained_iterations=50,depth=6,l2_leaf_reg=3,population=6000,metrics=oldmetrics,artifacts=control['artifacts'],model_path=oldmodelpath,score_path=oldscorepath)
  candidates=[incumbent];replayed=0;partial_replayed=0;seen=0;attempts=0;children=r['children'];need(1<=len(children)<=5,'Child count')
  populations={};reports=[]
  for number,child in enumerate(children):
   self.guard();need(set(child)=={'report','manifest','directory','exit_code','report_sha256','manifest_sha256','launch_receipt'} and type(child['exit_code']) is int and child['exit_code'] in (0,1),'Child result schema');wr=child['report'];wm=child['manifest'];wd=self.local(child['directory']);need(wd.parent.parent==d/'workers','Worker output confinement')
   need(not (wd/'report.failed.json').exists(),'Known failed worker marker');need(self.sha(wd/'report.json')==child['report_sha256'] and self.sha(wd/'run.json')==child['manifest_sha256'],'Worker receipt pins')
   compare(wr,read(wd/'report.json'));compare(wm,read(wd/'run.json'));wi=wm['identity'];slot=wi['slot'];mode='gate' if number==0 else 'arm';index=None if number==0 else number-1
   need(slot['mode']==mode and slot['index']==index and wi['parent_run_id']==m['run_id'] and digest(wi)==wm['run_id']==wr['run_id'],'Worker scope/order')
   slotpath=d/'slots'/('gate.json' if mode=='gate' else f'arm-{index}.json');contextpath=slotpath.with_name(slotpath.stem+'-context.json');context=read(contextpath);compare(slot,read(slotpath))
   need(set(context)=={'version','parent_plan_path','slot_path','slot_sha256'} and type(context['version']) is int and context['version']==1 and context['parent_plan_path']==str((d/'plan.json').relative_to(self.root)) and context['slot_path']==str(slotpath.relative_to(self.root)),'Worker context physical scope')
   context_sha=self.sha(contextpath)
   need(context['slot_sha256']==self.sha(slotpath) and wi['context_sha256']==context_sha,'Worker issued bytes')
   workerpins=dict(m['identity']['fingerprints'])
   for key,value in {context['parent_plan_path']:self.sha(d/'plan.json'),context['slot_path']:context['slot_sha256'],str(contextpath.relative_to(self.root)):context_sha,parent['budget_claim']['path']:parent['budget_claim']['sha256'],parent['execution_approval']['path']:parent['execution_approval']['sha256']}.items():
    need(key not in workerpins or workerpins[key]==value,'Conflicting worker pin');workerpins[key]=value
   compare(dict(version=1,role='strong_'+mode+'_worker',parent_run_id=m['run_id'],slot=slot,fingerprints=workerpins,context_sha256=context_sha),wi)
   logpath=d/'logs'/('gate.log' if mode=='gate' else f'arm-{index}.log');launchpath=logpath.with_suffix('.launch.json');launchrel=str(launchpath.relative_to(self.root));launchref=child['launch_receipt']
   need(launchrel in m['outputs'] and launchref==dict(path=launchrel,sha256=m['outputs'][launchrel]) and self.sha(launchpath)==launchref['sha256'],'Original launch receipt pin/cover')
   validate_worker_launch(read(launchpath),parent_id=m['run_id'],worker_id=wm['run_id'],slot=slot,context_path=str(contextpath.relative_to(self.root)),context_sha=context_sha,log_path=str(logpath.relative_to(self.root)),root=self.root,executable=sys.executable)
   allocation=slot['allocation'];need(set(allocation)=={'cpu_seconds','deadline_monotonic','rss_bytes'} and type(allocation['cpu_seconds']) is int and 1<=allocation['cpu_seconds']<=3240 and type(allocation['rss_bytes']) is int and allocation['rss_bytes']==7*2**30 and type(allocation['deadline_monotonic']) in (int,float) and math.isfinite(allocation['deadline_monotonic']) and allocation['deadline_monotonic']<=r['producer_deadline_monotonic']-20,'Issued allowance outside producer clock/caps')
   compare(dict(version=1,parent_run_id=m['run_id'],token=slot['token'],context_sha256=self.sha(contextpath)),read(slotpath.with_suffix('.consumed.json')))
   self.pins(wi['fingerprints']);need(set(m['identity']['fingerprints'])<=set(wi['fingerprints']),'Worker input scope');self.pins(wm.get('outputs',{}))
   need(wr['parent_run_id']==m['run_id'] and wr['mode']==mode and wr['index']==index and wr['population']==slot['population'],'Worker report scope')
   need(type(wr['fit_attempt_count']) is int and wr['fit_attempt_count'] in ([0] if mode=='gate' else [0,1]),'Worker fit count');attempts+=wr['fit_attempt_count']
   worker_resource_policy(wr,slot,successful=child['exit_code']==0)
   if mode=='gate':
    need(slot['population']==26000 and slot['look_reservations']==[],'Gate scope');population=26000 if child['exit_code']==0 else 6000
    if child['exit_code']!=0:need(child['exit_code']==1 and wr['status']=='failed' and wr['outcome']=='resource_failure' and wr['error_type'] in {'MemoryError','TimeoutError','OutOfMemoryException'},'Fallback classification')
    else:need(wr['status']=='complete_produced_unreviewed' and wr['outcome']=='gate_pass','Gate success')
   else:
    need(slot['population']==population and type(index) is int and slot['look_reservations']==list(TREES) and all(type(k) is int for k in slot['look_reservations']),'Fixed arm population/looks')
    seen+=sum(z['status'].startswith('seen') for z in wr['look_reservations']);arm=GRID[index]
    if child['exit_code']!=0:
     need(child['exit_code']==1 and wr['status']=='failed' and wr['outcome']=='resource_failure' and wr['error_type'] in {'MemoryError','TimeoutError','OutOfMemoryException'},'Failed arm classification')
     # A late failed arm contributes no eligible checkpoint, but every persisted
     # NPZ is still replayed. Incomplete/nonexistent partial files are never invented.
     available=[k for k in TREES if (wd/f'prefix{k}-scores.npz').exists()]
     if available:
      from catboost import CatBoostClassifier
      partial=CatBoostClassifier();partial.load_model(str(wd/'full300.cbm'));pparams=partial.get_all_params()
      need(partial.tree_count_==300 and partial.feature_names_==names and partial.get_cat_feature_indices()==[],'Partial full300 schema')
      for key,value in {'depth':arm['depth'],'l2_leaf_reg':arm['l2_leaf_reg'],'iterations':300,'loss_function':'Logloss','learning_rate':effective_learning_rate(control['actual_model_parameters'])}.items():need(same(value,pparams[key]),'Partial grid scope')
      for k in available:
       for path in [wd/'full300.cbm',wd/f'prefix{k}.cbm',wd/f'prefix{k}-scores.npz']:
        name=str(path.relative_to(self.root));need(name in m['outputs'] and self.sha(path)==m['outputs'][name],'Partial artifact is not sealed')
       score=np.asarray(partial.predict(x,ntree_end=k,prediction_type='RawFormulaVal',thread_count=2));self.guard();prefix=self.model(wd/f'prefix{k}.cbm',k,names,pparams)
       replay=np.asarray(prefix.predict(x,prediction_type='RawFormulaVal',thread_count=2));self.guard();score_parity(score,replay,g,it,'Partial prefix fidelity');self.npz(wd/f'prefix{k}-scores.npz',score,g,it);partial_replayed+=1
       del prefix,replay,score
      del partial
     continue
    need(wr['fit_attempt_count']==1 and wr['status']=='complete_produced_unreviewed' and wr['outcome']=='arm_complete','Successful arm scope')
    compare([dict(trees=k,status='seen_complete',metrics=cp['metrics']) for k,cp in zip(TREES,wr['checkpoints'])],wr['look_reservations']);need(len(wr['checkpoints'])==3,'Three checkpoint scope')
    expected={str((wd/n).relative_to(self.root)) for n in ['full300.cbm','full300.json',*[f'prefix{k}{suffix}' for k in TREES for suffix in ['.cbm','-scores.npz']]]};need(set(wm['outputs'])==expected and wr['artifacts']==wm['outputs'],'Exact8 outputs')
    stages=wr['stages'];stagenames=[z['stage'] for z in stages];need(all(z['status']=='complete' for z in stages),'Successful stage status')
    need(stagenames.index('one_fixed300fit')<stagenames.index('save_full300')<stagenames.index('predict_prefix50') and stagenames.index('save_full300_JSON')<stagenames.index('external_fullY_prefix50'),'300 before looks')
    params=wr['actual_model_parameters'];fixed=dict(loss_function='Logloss',iterations=300,depth=arm['depth'],l2_leaf_reg=arm['l2_leaf_reg'],learning_rate=effective_learning_rate(control['actual_model_parameters']),random_seed=2026,task_type='CPU',boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',random_strength=1,boost_from_average=False,use_best_model=False)
    for key,value in fixed.items():need(same(value,params[key]),'Frozen parameter')
    for key in ['border_count','nan_mode','rsm']:need(same(params[key],control['actual_model_parameters'][key]),'Incumbent shared parameter')
    body=read(wd/'full300.json');need(len(body.get('oblivious_trees',[]))==300 and not body.get('features_info',{}).get('ctrs') and all(z['split_type']=='FloatFeature' for tree in body['oblivious_trees'] for z in tree.get('splits') or []),'Full numeric300 JSON')
    full=self.model(wd/'full300.cbm',300,names,params)
    for cp,k in zip(wr['checkpoints'],TREES):
     pred=np.asarray(full.predict(x,ntree_end=k,prediction_type='RawFormulaVal',thread_count=2));self.guard()
     prefix=self.model(wd/f'prefix{k}.cbm',k,names,params);pp=np.asarray(prefix.predict(x,prediction_type='RawFormulaVal',thread_count=2));self.guard();score_parity(pred,pp,g,it,'Full300/prefix equivalence')
     self.npz(wd/f'prefix{k}-scores.npz',pred,g,it);metrics,per,_=self.scored(pred,g,it,qrows,targets)
     artifacts={str((wd/n).relative_to(self.root)):wm['outputs'][str((wd/n).relative_to(self.root))] for n in [f'prefix{k}.cbm',f'prefix{k}-scores.npz']}
     expectedcp=dict(config_id=digest(arm),incumbent=False,trees=k,trained_iterations=300,depth=arm['depth'],l2_leaf_reg=arm['l2_leaf_reg'],population=population,metrics=metrics,artifacts=artifacts,model_path=str((wd/f'prefix{k}.cbm').relative_to(self.root)),score_path=str((wd/f'prefix{k}-scores.npz').relative_to(self.root)))
     if 'comparison' in cp:
      compare(bootstrap(per,oldper,users),cp['comparison']);expectedcp['comparison']=cp['comparison']
     compare(expectedcp,cp);expectedcp.pop('comparison',None);candidates.append(expectedcp);replayed+=1
     del prefix,pp,pred
    reports.append(wr);del full
  whole_resource_policy(r,children)
  need(population==r['population'] and attempts==r['fit_attempt_count'] and seen==r['actual_seen_looks'] and r['new_reserved_look_slots']==3*(len(children)-1),'Parent ledger')
  remaining=list(range(len(children)-1,4));need(r.get('unattempted_remaining_arms',[])==remaining,'Unattempted slot accounting')
  train=self.collection('train',inputs['train'],population)
  for wr in reports:compare(train,wr['training'],tolerance=1e-8)
  winner=select(candidates);compare(winner,r['winner']);compare(winner,read(d/'winner.json'));need(r['eligible_outputs']==len(candidates),'Eligible candidate count')
  self.pins(m['identity']['fingerprints']);self.pins(m['outputs']);self.pins({v['path']:v['sha256'] for v in [self.context['producer_manifest'],self.context['producer_report']]});need(not (d/'report.failed.json').exists(),'Late failed producer')
  return dict(status='verified',run_id=m['run_id'],fit_attempt_count=0,observer_refits=0,saved_prefixes_replayed=replayed,failed_arm_saved_prefixes_replayed=partial_replayed,successful_new_arms=len(reports),allocated_new_arms=len(children)-1,selection_query_count=len(qrows),selection_candidate_rows=len(g),selection_full_targets=sum(map(len,targets.values())),selection_positive_queries=sum(bool(targets.get(q)) for q,u in qrows),numeric_features=41,expected_training_population=train,all_four_estimands_recomputed=True,full300_prefix_equivalence=True,winner=dict(config_id=winner['config_id'],incumbent=winner['incumbent'],trees=winner['trees'],trained_iterations=winner['trained_iterations'],depth=winner['depth'],l2_leaf_reg=winner['l2_leaf_reg'],population=winner['population'],metrics=winner['metrics']),proof_limits='Expected accepted-source population/row mass plus reviewed fit code and producer receipts; CBM does not recover actual training weights. Prior base18 source proof is reused; no new formula proof or quality generalization.',context_sha256=self.context_sha,request_sha256=self.context['request_sha256'],producer_receipt_pins={v['path']:v['sha256'] for v in [self.context['producer_manifest'],self.context['producer_report']]},entry_sha256=self.self_sha)
 def run(self):
  attempt=Path(str(self.output)+'.attempt');need(not attempt.exists(),'Observer attempt consumed')
  with attempt.open('x') as f:f.write(canonical(dict(version=1,context_sha256=self.context_sha,entry_sha256=self.self_sha,status='running'))+'\n')
  primary=None;result=None
  try:result=self.execute()
  except BaseException as error:primary=error
  finally:
   self.stopped.set()
   for name,operation in [('close',lambda:self.con.close() if self.con is not None else None),('timer_join',lambda:self.timer.join(timeout=1) if self.timer is not None else None),('terminal_guard',self.guard)]:
    try:operation()
    except BaseException as error:
     if primary is None:primary=error
     else:primary.add_note(name+': '+repr(error))
  if primary is None:
   try:
    need(self.sha(self.path)==self.context_sha,'Context changed during replay');self.guard()
    result['receipt_boundary']='postclose_guard_before_minimal_persistence_controller_reaps_and_charges_tail'
    used=self.cpu();finished=time.monotonic()
    receipt=dict(version=1,status='verified',scope=self.context['scope'],run_id=self.context['run_id'],context_sha256=self.context_sha,request_sha256=self.context['request_sha256'],producer_manifest=self.context['producer_manifest'],producer_report=self.context['producer_report'],verifier_source=self.context['expected_verifier_source'],allocation=self.allocation,fit_attempt_count=0,process_cpu_seconds=used,reaped_children_cpu_seconds=0,process_peak_rss_bytes=self.rss(),started_monotonic=START,finished_monotonic=finished,seconds=finished-START,evidence=result)
    self.atomic(receipt);self.guard();need(self.sha(self.path)==self.context_sha,'Context changed after receipt');print(canonical(dict(status='verified',run_id=result['run_id'],fit_attempt_count=0)),flush=True);self.guard()
   except BaseException as error:primary=error
  if primary is not None:
   failed=dict(status='failed',run_id=self.context['run_id'],fit_attempt_count=0,error_type=type(primary).__name__,error='Independent verification failed; raw exception values suppressed',secondary_error_count=len(getattr(primary,'__notes__',[])))
   try:self.failed_output.write_text(canonical(failed)+'\n')
   except BaseException as secondary:primary.add_note('Failure receipt: '+repr(secondary))
   raise primary
  return receipt

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',type=Path,required=True);p.add_argument('--issued-context-sha256',required=True);a=p.parse_args();Observer(a.context,issued_context_sha256=a.issued_context_sha256).run()
if __name__=='__main__':
 try:main()
 except BaseException as error:
  print(canonical(dict(status='failed',fit_attempt_count=0,error_type=type(error).__name__,diagnostic='Raw source/model/query values suppressed')),file=sys.stderr,flush=True)
  sys.exit(1)
