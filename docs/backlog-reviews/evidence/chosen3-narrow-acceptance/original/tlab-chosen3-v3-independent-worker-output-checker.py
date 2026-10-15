"""Authenticate/recompute EXISTING synthetic W44 worker output; preserve failed outer status."""
from pathlib import Path
import ast,collections,datetime,hashlib,io,json,math,random,re,struct,time,types,zipfile,sys
started=time.monotonic();cpu0=time.process_time();sha=lambda b:hashlib.sha256(b).hexdigest()
mp=Path('/tmp/tlab-chosen3-v3-worker-output-review-inputfreeze.json');assert sha(mp.read_bytes())=='92742e9f3eb5f14a922b0086ed7cf3619e7a3b37a02f5dfdbca4d3a3de5bcb75';mf=json.loads(mp.read_text());files=mf['files'];root=Path(mf['root']);project=Path('/Users/mdpospelov/tlab-recsys-2026')
def budget():assert time.monotonic()-started<10 and time.process_time()-cpu0<5

def raw(p):return Path(files[str(p)]['snapshot_path']).read_bytes()
def unique(ps):
 d={}
 for k,v in ps:assert k not in d;d[k]=v
 return d
def reject(x):raise AssertionError(x)
def read(p):return json.loads(raw(p),object_pairs_hook=unique,parse_constant=reject)
def href(p):return {'path':str(Path(p).relative_to(root)),'sha256':sha(raw(p))}
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
for p,e in files.items():assert sha(raw(p))==e['sha256'] and sha(Path(p).read_bytes())==e['sha256'];budget()
f=read('/tmp/tlab-chosen3-integration-draft-freeze-v3.json');fail=read('/tmp/tlab-root-chosen3-v3-failed-external-receipt.json');sr=read('/tmp/tlab-root-chosen3-v3-setup-external-receipt.json')
assert sha(raw('/tmp/tlab-chosen3-six-role-candidate-v3.py'))=='b40060a970546ea749291695bd60585b06ad7f1facdbf2388e6bfb1371f43a6d'
assert sha(raw('/tmp/tlab-chosen3-integration-draft-freeze-v3.json'))=='fc3a44a40b00b90dc0df7ddff0a5492772d3bfb802533a9523fb439c81737c8e'
assert sha(raw('/tmp/tlab-root-chosen3-v3-failed-external-receipt.json'))=='d32348f7a3831216aa2efdac8c22da53216cc53f696c7dd349f351ef645ed789'
for p,d in f['harness_files'].items():assert sha(raw(p))==d
cp=read(root/'harness-copy.json');assert len(cp['files'])==len(f['production_files'])==31
for p,d in f['production_files'].items():assert sha(raw(project/p))==sha(raw(root/p))==d and cp['files'][p]==dict(source_sha256=d,copied_sha256=d)
assert cp['package_runtime_shared'] and not cp['copied_private_data'] and not cp['environment_override']
assert mf['symlinks']=={str(root/'.venv'):str(project/'.venv')}
for p,d in fail['artifacts'].items():assert sha(raw(p))==d
assert fail['explicit_terminal_exit_code']==fail['supervisor_direct_exit_code']==1 and fail['whole_harness_accepted'] is False
assert sr['explicit_exit_code']==0 and sr['actual_new_synthetic_W_fits']==1 and sr['new_B_fits']==sr['study_fits']==0
setup=read(root/'setup-supervision.json');supervision=read(root/'integration-supervision.json');fm=read(root/'integration.failed.json');sm=read(root/'integration-supervision.failed.json')
assert sha(raw(root/'setup-supervision.json'))==sr['setup_supervision_sha256'] and setup['bound_outputs']==sr['bound_outputs']
for p,d in setup['bound_outputs'].items():assert sha(raw(root/p))==d
assert setup['status']=='verified_normal_exit' and setup['exit_code']==0 and setup['reaped']
assert supervision['exit_code']==1 and supervision['reaped'] and supervision['unknown_active_work'] is True and supervision['status']=='failed_unknown_cleanup'
assert supervision['survivors_at_terminal_scan']==[] and supervision['errors']==[] and supervision['signaled_pids']==[]
assert fm['status']==sm['status']=='failed_consumed_no_retry' and fm['error_type']=='TypeError' and fm['unknown_active_work'] is sm['unknown_active_work'] is True
assert sm['returned_process_observation']==supervision and sm['error_type']=='ValueError'
assert 'TypeError: dict() got multiple values for keyword argument' in raw(root/'integration-process.log').decode() and "'metric_delta_required_nonzero'" in raw(root/'integration-process.log').decode()
assert not (root/'integration-result.json').exists() and not (root/'harness-ledger.json').exists()
claim=read(root/'artifacts/heldout-study/owner.claim.json');run=root/claim['output_directory'];report=read(run/'report.json');lock=read(run/'decision-lock.json');choice=read(run/'authenticated-choice.json');b=read(root/'fixture-setup/model-spec.json');w=read(root/'fixture-setup/W-model-spec.json');proposal=read(run/'proposal.json')
EXTRAS=['auto_item_view_count_distinct_24h_user_id','auto_item_cart_count_distinct_168h_user_id','auto_item_purchase_count_distinct_24h_user_id']
assert choice['candidate_id']==lock['choice']=='R2' and lock['models']==choice['models']=={'B':b,'W':w}
assert len(b['feature_names'])==41 and w['feature_names']==b['feature_names']+EXTRAS and len(set(w['feature_names']))==44
assert b['effective_parameters']==w['effective_parameters'] and b['model']['sha256']!=w['model']['sha256']
assert b['model']==href(root/'fixture-reused/B.cbm') and w['model']==href(root/'fixture-setup/W.cbm')
original=read(root/'fixture-reused/original-B-spec.json');expected=json.loads(json.dumps(original));expected['model']['path']='fixture-reused/B.cbm';assert b==expected
oldroot=Path(f['reused_B']['root']);assert sha(raw(oldroot/'fixture-setup/B.cbm'))==sha(raw(root/'fixture-reused/B.cbm'))==f['reused_B']['bound_outputs']['fixture-setup/B.cbm']
assert raw(oldroot/'fixture-setup/model-spec.json')==raw(root/'fixture-reused/original-B-spec.json')
assert report['run_id']==proposal['run_id']==sha(canonical(proposal['identity']).encode())
assert report['status']=='verified_reporting_pending_external_lifetime_acceptance' and report['active_role'] is None and report['unknown_active_work'] is False
assert report['fit_attempt_count']==0 and report['external_exit_tail_acceptance_required'] and report['full_owner_exit_tail_acceptance_required']
roles=['source','source_oracle','predictions','prediction_oracle','targets_evaluation','metric_oracle'];assert [r['role'] for r in report['roles']]==roles
entries={'source':'scripts/heldout_reporting_worker.py','source_oracle':'tests/oracles/heldout_source_worker.py','predictions':'scripts/heldout_reporting_worker.py','prediction_oracle':'tests/oracles/heldout_prediction_worker.py','targets_evaluation':'scripts/heldout_reporting_worker.py','metric_oracle':'tests/oracles/heldout_metric_worker.py'}
receipts={};contexts={};reaps={};ref_checks=0;map_checks=0;allpins={}
def add(p,d,reference_root=root):
 path=Path(p) if Path(p).is_absolute() else reference_root/p
 assert sha(raw(path))==d,(p,d)
 assert str(path) not in allpins or allpins[str(path)]==d
 allpins[str(path)]=d

def walk(v,reference_root=root):
 global ref_checks,map_checks
 if isinstance(v,dict):
  if set(v)=={'path','sha256'}:add(v['path'],v['sha256'],reference_root);ref_checks+=1
  for k,x in v.items():
   if k in ['fingerprints','outputs','code_fingerprints'] and isinstance(x,dict):
    for p,d in x.items():
     if isinstance(d,str) and re.fullmatch('[0-9a-f]{64}',d):add(p,d,reference_root);map_checks+=1
   walk(x,reference_root)
 elif isinstance(v,list):
  for x in v:walk(x,reference_root)
for p in files:
 if p.startswith(str(root)+'/') and p.endswith('.json'):walk(read(p),oldroot if p.endswith('/fixture-reused/original-B-spec.json') else root)
for idx,role in enumerate(roles):
 c=contexts[role]=read(run/role/'context.json');r=receipts[role]=read(run/role/'receipt.json');reap=reaps[role]=read(run/(role+'-reaped.json'));slot=read(run/role/'slot.json');launch=read(run/role/'launch.json');consume=read(run/role/'execution.consumed.json')
 assert c['role']==r['role']==reap['role']==slot['role']==consume['role']==role and slot['ordinal']==idx
 assert c['entry']==href(root/entries[role]) and r['scope']=='reserved_reporting_'+role and r['status']=='role_complete_unaccepted'
 assert fail['actual_role_reaps'][idx]==dict(role=role,reaped_exit_code=0,fit_attempt_count=0,labels_loaded=idx>=4,native_prediction_count=10 if role in ['predictions','prediction_oracle'] else 0)
 assert c['run_id']==r['run_id']==reap['run_id']==slot['run_id']==consume['run_id']==report['run_id']
 assert reap['explicitly_reaped_exit_code']==0 and r['labels_loaded'] is (idx>=4) and r['fit_attempt_count']==0 and r['descendant_cpu_seconds']==0
 assert r['native_prediction_count']==(10 if role in ['predictions','prediction_oracle'] else 0)
 assert c['issued_at_monotonic']<=r['started_monotonic']<=r['finished_monotonic']<=c['allocation']['deadline_monotonic']
 if idx:assert receipts[roles[idx-1]]['finished_monotonic']<c['issued_at_monotonic']
 assert r['process_cpu_seconds']<=reap['actual_reaped_cpu_seconds']<=c['allocation']['cpu_seconds']
 assert r['context']==reap['context']==launch['context']==consume['context']==href(run/role/'context.json')
 assert launch['original_slot']==slot and c['slot']==consume['slot']==href(run/role/'slot.json') and c['entry']==slot['entry']==launch['entry']
 assert r['inputs']==c['inputs'] and set(r['outputs'])==set(c['expected_outputs']) and r['execution_consumed']==href(run/role/'execution.consumed.json') and reap['receipt']==href(run/role/'receipt.json')
 assert launch['argv']==[str(root/'.venv/bin/python').replace('/tmp/','/private/tmp/',1),str(root/c['entry']['path']).replace('/tmp/','/private/tmp/',1),'--context',str(run/role/'context.json').replace('/tmp/','/private/tmp/',1),'--issued-context-sha256',r['context']['sha256']]
 assert raw(run/role/'worker.log')==b''
assert math.isclose(sum(r['actual_reaped_cpu_seconds'] for r in reaps.values()),report['actual_reaped_children_cpu_seconds'],abs_tol=1e-12)
closure=dict(contexts['source']['plan']['fingerprints']);gates=[]
def append(p):closure[str(p.relative_to(root))]=sha(raw(p))
def gate(name):
 p=root/'artifacts/acceptance'/('synthetic-'+name+'.json');g=read(p);assert g['fingerprints']==closure and g['approved'] is True and g['run_id']==report['run_id'];gates.append({'gate':name,'fingerprints':len(closure),'sealed_at':g.get('sealed_at')});append(p)
def append_role(role):
 closure.update(receipts[role]['outputs'])
 for name in ['context.json','slot.json','launch.json','execution.consumed.json','receipt.json','worker.log']:append(run/role/name)
 append(run/(role+'-reaped.json'))
gate('initial_execution')
for role in roles[:2]:append_role(role)
gate('source_acceptance')
for role in roles[2:4]:append_role(role)
boundary=read(run/'prediction-boundary.json');assert boundary['fingerprints']==closure and not boundary['heldout_targets_opened'] and boundary['native_calls_each_role']==10
append(run/'prediction-boundary.json');append(run/'all-predictions-inventory.json');gate('prediction_acceptance');append(run/'target-policy.json');gate('target_execution')
for role in roles[4:]:append_role(role)
source=read(run/'source/source-manifest.json');proof=read(run/'source_oracle/evidence.json')['core'];pred=read(run/'predictions/prediction-manifest.json');oracle=read(run/'prediction_oracle/evidence.json')['core'];evaluation=read(run/'targets_evaluation/evaluation.json');metric=read(run/'metric_oracle/evidence.json')['core'];days=[f'2019-10-{d:02}T00:00:00Z' for d in range(25,32)]
assert [d['anchor'] for d in source['days']]==days and [d['query_count'] for d in source['days']]==[1,2,3,2,3,2,0] and [d['candidate_count'] for d in source['days']]==[0,3,6,4,7,5,0]
assert proof['choice']=='R2' and proof['chosen_columns']==3 and proof['chosen_scalar_values']==75 and proof['mismatch_count']==0 and proof['chosen_formula_values_complete'] is True and proof['extra_proof_scope']=='all_selected3_values_every_C_row' and proof['baseline_formula_values_complete'] is False
assert oracle['native_prediction_count']==10 and [d['native_prediction_count'] for d in oracle['days']]==[0,2,2,2,2,2,0]
for sd,pd in zip(source['days'],pred['days']):
 assert sd['extra_features'] is not None and sd['anchor']==pd['anchor']
 for side,spec in [('B',b),('W',w)]:
  d=pd['predictions'][side];assert d['model']==spec['model'] and d['feature_names']==spec['feature_names'] and d['scoring_prefix']==300 and d['queries']==sd['query_count'] and d['rows']==sd['candidate_count']
 assert pd['predictions']['B']['artifact']!=pd['predictions']['W']['artifact']
# Reuse only the four previously reviewed pure scalar/NPY decoder definitions, not the previous checker execution.
previous=ast.parse(Path('/tmp/tlab-six-role-v2-independent-output-checker.py').read_bytes());defs=[n for n in previous.body if isinstance(n,ast.FunctionDef) and n.name in ['npy','values','groups','aggregate']];assert len(defs)==4
exec(compile(ast.Module(body=defs,type_ignores=[]),'previous_pure_definitions_only','exec'),globals())
pq=types.ModuleType('flat_parquet_stdlib_only');exec(compile(Path('/tmp/tlab-chosen3-v3-stdlib-parquet.py').read_bytes(),'flat_parquet_stdlib_only','exec'),pq.__dict__)
# Independent fixture transcription plus exact source-AST correspondence, without project execution.
big=2**60+1
E=[('2019-10-24 23:00:00','view',None,big,None),('2019-10-25 00:00:00','purchase',big,big,9),('2019-10-25 00:00:00','purchase',big,big,9),('2019-10-25 02:00:00','view',10,2,100),('2019-10-26 12:00:00','view',10,2,100),('2019-10-26 12:00:00','view',10,3,None),('2019-10-26 12:00:00','purchase',10,2,100),('2019-10-27 12:00:00','cart',10,2,200),('2019-10-28 10:00:00','view',20,4,200),('2019-10-28 11:00:00','purchase',big,4,9),('2019-10-28 11:00:00','view',None,5,None)]
tree=ast.parse(raw('/tmp/tlab-run-heldout-six-role-toy.py'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='toy_events');ret=next(n.value for n in fn.body if isinstance(n,ast.Return))
def literal(n):
 if isinstance(n,ast.Name):assert n.id=='big';return big
 if isinstance(n,(ast.Tuple,ast.List)):return (tuple if isinstance(n,ast.Tuple) else list)(literal(v) for v in n.elts)
 return ast.literal_eval(n)
assert literal(ret)==E;events=[(datetime.datetime.fromisoformat(t),kind,item,user,category) for t,kind,item,user,category in E]
rankings=[json.loads(line,object_pairs_hook=unique,parse_constant=reject) for line in raw(run/'targets_evaluation/private-rankings.jsonl').splitlines()];assert len(rankings)==26
expected_rankings={};expected_full=set();scalar_checks=0;scalar_hist={e:collections.Counter() for e in EXTRAS};score_diffs=0;rank_diffs=0;W_scores=[];B_scores=[];partitions=[];parquet_decodes=0
for day in days:
 budget();a=datetime.datetime.fromisoformat(day[:-1]);past=[e for e in events if e[0]<a];users={e[3] for e in past if e[0]>=a-datetime.timedelta(hours=48)};qs=sorted((sha(f'query|2026|{day}|{u}'.encode()),u) for u in users)
 arrays={}
 for side in ['B','W']:
  with zipfile.ZipFile(io.BytesIO(raw(run/'predictions'/('day-'+day[8:10])/(side+'.npz')))) as z:arrays[side]={name[:-4]:npy(z.read(name)) for name in z.namelist()}
  aa=arrays[side];assert set(aa)=={'query_ids','user_ids','anchors','calendar_maturity','group','items','scores'}
  assert aa['query_ids']==('<U64',[q for q,u in qs]) and aa['user_ids']==('<i8',[u for q,u in qs]) and aa['anchors']==('<i8',[int(a.replace(tzinfo=datetime.timezone.utc).timestamp()*1000000)]*len(qs)) and aa['calendar_maturity']==('|b1',[True]*len(qs))
  assert aa['group'][0]=='<i4' and aa['items'][0]=='<i8' and aa['scores'][0]=='<f8' and all(math.isfinite(v) for v in aa['scores'][1])
 assert {k:v for k,v in arrays['B'].items() if k!='scores'}=={k:v for k,v in arrays['W'].items() if k!='scores'}
 B_scores+=arrays['B']['scores'][1];W_scores+=arrays['W']['scores'][1];score_diffs+=sum(x!=y for x,y in zip(arrays['B']['scores'][1],arrays['W']['scores'][1]))
 sd=next(d for d in source['days'] if d['anchor']==day);query_table=pq.table(raw(root/sd['queries']['path']),{'query_id','user_id','anchor'});candidate_table=pq.table(raw(root/sd['candidates']['path']),{'query_id','product_id'});extra=pq.table(raw(root/sd['extra_features']['path']));parquet_decodes+=3
 assert list(zip(query_table['columns']['query_id'],query_table['columns']['user_id']))==qs
 assert query_table['columns']['anchor']==arrays['B']['anchors'][1]
 assert extra['schema']==dict(query_id=(6,1),product_id=(2,1),**{e:(2,1) for e in EXTRAS})
 actual_C=list(zip(candidate_table['columns']['query_id'],candidate_table['columns']['product_id']));actual_extra=list(zip(extra['columns']['query_id'],extra['columns']['product_id']));assert actual_C==actual_extra and len(actual_C)==extra['row_count']==sd['candidate_count']
 popular={e[2] for e in past if e[1]=='purchase' and e[2] is not None and e[0]>=a-datetime.timedelta(days=7)};expected_C=[];daily_checks=0
 for index,(qid,user) in enumerate(qs):
  candidate_items=popular|{e[2] for e in past if e[3]==user and e[2] is not None and e[0]>=a-datetime.timedelta(days=7)};expected_C.extend((qid,item) for item in sorted(candidate_items));targets=sorted({e[2] for e in events if e[3]==user and e[1]=='purchase' and e[2] is not None and a<=e[0]<a+datetime.timedelta(days=1)})
  expected_full.update((qid,item) for item in targets)
  positions=[j for j,g in enumerate(arrays['B']['group'][1]) if g==index];assert [arrays['B']['items'][1][j] for j in positions]==sorted(candidate_items)
  orders={}
  for side in ['B','W']:
   aa=arrays[side];orders[side]=[aa['items'][1][j] for j in sorted(positions,key=lambda j:(-aa['scores'][1][j],aa['items'][1][j]))][:20]
   period='confirmation25_reporting_only' if day==days[0] else 'final26_31_frozen';expected_rankings[(period,side,qid)]=dict(mature=True,period=period,query_id=qid,ranked_items=orders[side],role=side,targets=targets,user_id=user)
  rank_diffs+=orders['B']!=orders['W']
 assert actual_C==expected_C
 for index,(qid,item) in enumerate(actual_extra):
  for name,action,hours in zip(EXTRAS,['view','cart','purchase'],[24,168,24]):
   expected=len({e[3] for e in past if e[2]==item and e[1]==action and e[3] is not None and e[0]>=a-datetime.timedelta(hours=hours)})
   actual=extra['columns'][name][index];assert type(actual) is int and actual==expected,(day,name,index,actual,expected);scalar_checks+=1;daily_checks+=1;scalar_hist[name][actual]+=1
 partitions.append({'anchor':day,'queries':len(qs),'candidates':len(actual_C),'chosen_scalar_checks':daily_checks})
assert scalar_checks==75 and score_diffs>0 and len(set(W_scores))>1
for part,d in zip(partitions,proof['days']):assert d['anchor']==part['anchor'] and d['chosen_columns']==3 and d['chosen_scalar_values']==part['chosen_scalar_checks'] and d['chosen_formula_values_complete'] is True
assert not list(run.rglob('*failed.json'))
assert {(r['period'],r['role'],r['query_id']):r for r in rankings}==expected_rankings and len(expected_rankings)==26
full=pq.table(raw(run/'targets_evaluation/full-targets.parquet'));parquet_decodes+=1;actual_full=list(zip(full['columns']['query_id'],full['columns']['product_id']));assert len(actual_full)==len(set(actual_full))==2 and set(actual_full)==expected_full
assert full['schema']=={'query_id':(6,1),'product_id':(2,1)} and metric['fullY_pairs']==report['independent_fullY_pairs']==2 and metric['private_ranking_rows_checked']==26
assert evaluation['periods']==metric['periods']==report['aggregate_periods'];estimands=['conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero'];names=['recall','ndcg','average_precision','reciprocal_rank'];scalar_fields=0;draw_fields=0;bootstrap_stats=[]
for period,p in evaluation['periods'].items():
 rs={side:[r for r in rankings if r['period']==period and r['role']==side] for side in ['B','W']};gs={side:groups(v) for side,v in rs.items()};users=list(gs['W']);rng=random.Random(2026);draws=[rng.choices(users,k=len(users)) for _ in range(200)]
 support={'query_count':len(rs['B']),'candidate_pairs':sum(len(r['ranked_items']) for r in rs['B']),'target_pairs':sum(len(r['targets']) for r in rs['B']),'retrieved_target_pairs':sum(len(set(r['ranked_items'])&set(r['targets'])) for r in rs['B']),'positive_empty_C_queries':sum(bool(r['targets']) and not r['ranked_items'] for r in rs['B'])};assert p['support']==support
 for side in ['B','W']:
  positives=[r for r in rs[side] if r['targets']];expected=dict(k=20,query_count=len(rs[side]),mature_query_count=len(rs[side]),censored_query_count=0,nonempty_query_count=len(positives),mature_user_count=len(gs[side]),positive_user_count=len({r['user_id'] for r in positives}),nonempty_fraction=len(positives)/len(rs[side]) if rs[side] else None);expected.update({e:{n:aggregate(gs[side],e,n) for n in names} for e in estimands});assert p['metrics'][side]==expected;scalar_fields+=16
 for e in estimands:
  def delta(draw):
   a,b=aggregate(gs['W'],e,'ndcg',draw),aggregate(gs['B'],e,'ndcg',draw);return a-b if a is not None and b is not None else None
  samples=[delta(draw) for draw in draws];defined=sorted(v for v in samples if v is not None)
  def percentile(p):
   position=p*(len(defined)-1);lo=math.floor(position);hi=math.ceil(position);weight=position-lo;return defined[lo]*(1-weight)+defined[hi]*weight
  expected=dict(metric='ndcg',estimand=e,seed=2026,replicates=200,user_count=len(users),estimate=delta(None),samples=samples,undefined_draws=200-len(defined),interval_95=[percentile(.025),percentile(.975)] if defined else None);assert p['paired_user_bootstrap'][e]==expected and p['ndcg_W_minus_B'][e]==delta(None);draw_fields+=200;bootstrap_stats.append({'period':period,'estimand':e,'estimate':delta(None),'undefined_draws':200-len(defined)})
predseal=read(root/'artifacts/acceptance/synthetic-prediction_acceptance.json');targetseal=read(root/'artifacts/acceptance/synthetic-target_execution.json')
assert evaluation['target_stage_opened_at']==evaluation['actual_target_intent']['opened_at']>max(predseal['sealed_at'],targetseal['sealed_at']) and evaluation['fullY_started_at']>=evaluation['target_stage_opened_at']
assert receipts['targets_evaluation']['started_monotonic']<=evaluation['target_stage_started_monotonic']<=evaluation['fullY_started_monotonic']<=receipts['targets_evaluation']['finished_monotonic']
assert metric['oracle_target_stage_opened_at']>max(predseal['sealed_at'],targetseal['sealed_at']) and metric['oracle_fullY_started_at']>=metric['oracle_target_stage_opened_at'] and receipts['metric_oracle']['started_monotonic']<=metric['oracle_target_stage_started_monotonic']<=metric['oracle_fullY_started_monotonic']<=receipts['metric_oracle']['finished_monotonic']
resources={}
for stage,s in [('setup',setup),('integration',supervision)]:
 text=raw('/tmp/tlab-chosen3-v3-'+stage+'-external.stderr-time.txt').decode();hit=re.search(r'([0-9.]+) real\s+([0-9.]+) user\s+([0-9.]+) sys',text);wall,user,system=map(float,hit.groups());rss=int(re.search(r'(\d+)\s+maximum resident set size',text).group(1));resources[stage]=dict(external_rounded_cpu_seconds=round(user+system,2),external_wall_seconds=wall,external_MAXRSS_bytes=rss,sampled_aggregate_RSS_bytes=s['observed_job_peak_rss_bytes'],internal_observed_cpu_seconds=s['observed_total_cpu_seconds'],internal_cpu_upper_including_reserve=s['cpu_upper_seconds'],exit_code=s['exit_code'])
 assert s['actual_total_cpu_seconds'] is None and s['supervisor_exit_tail_measured'] is False and s['rss_is_sampled_not_hard_limit']
 assert wall<120 and user+system+.02<60 and s['observed_job_peak_rss_bytes']<=(2**30 if stage=='setup' else 2**31)
assert sha(raw('/tmp/tlab-chosen3-v3-integration-external.stderr-time.txt'))==fail['external_log_sha256'] and sha(raw('/tmp/tlab-chosen3-v3-setup-external.stderr-time.txt'))==sr['external_time_sha256']
current={str(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()};initial={p for p in files if p.startswith(str(root)+'/')};assert current==initial
changed=[p for p,e in files.items() if sha(Path(p).read_bytes())!=e['sha256']];assert not changed;budget()
result=dict(version=1,scope='existing_synthetic_chosen3_v3_worker_outputs_only',worker_output_status='accepted_existing_six_role_worker_outputs_within_synthetic_scope',whole_operation_status='FAILED_consumed_outer_TypeError_exit1',whole_harness_accepted=False,source_free_reconstruction_not_execution=True,inputfreeze_path=str(mp),inputfreeze_sha256=sha(mp.read_bytes()),frozen_inputs=len(files),fixedroot_files=len(initial),all_scoped_inputs_unchanged=True,recursive_reference_occurrences=ref_checks,recursive_hash_map_occurrences=map_checks,unique_authentication_pins=len(allpins),gates=gates,roles=roles,all_six_reaped_exit0=True,native_predictions_each_prediction_role=10,setup_W_fits=1,new_B_fits=0,study_fits=0,query_count=13,candidate_pairs=25,partitions=partitions,chosen3_scalar_groundtruth_comparisons=scalar_checks,chosen3_value_histograms={n:dict(h) for n,h in scalar_hist.items()},source_event_provenance='Eleven typed literal events independently transcribed and checked against frozen base.toy_events AST; existing DB byte-hashed only, no SQL/deserialize.',actual_saved_NPZ_files=14,actual_saved_Parquet_partitions_decoded=parquet_decodes,Parquet_decoder='Flat CompactProtocol/plain/RLE page reader with Python3.14 stdlib compression.zstd only',distinct_fullY_pairs=2,all_ranking_rows_checked=26,metric_scalar_fields_checked=scalar_fields,paired_user_draw_fields_checked=draw_fields,bootstrap=bootstrap_stats,W_unique_raw_score_values=len(set(W_scores)),W_raw_score_range=[min(W_scores),max(W_scores)],B_raw_score_range=[min(B_scores),max(B_scores)],B_W_raw_score_pairs_different=score_diffs,B_W_query_rankings_different=rank_diffs,native_model_deserialization_or_prediction_by_reviewer=False,resources=resources,additional_external_cpu_rounded=sum(x['external_rounded_cpu_seconds'] for x in resources.values()),additional_external_wall_rounded=sum(x['external_wall_seconds'] for x in resources.values()),failure_markers_preserved=['integration.failed.json','integration-supervision.failed.json'],failure_unknown_active_work_retained=True,internal_exact_tail_unmeasured_preserved=True,outer_integration_result_absent=True,outer_harness_ledger_absent=True,new_jobs_or_refits_or_promotions=0,review_cpu_seconds=time.process_time()-cpu0,review_wall_seconds=time.monotonic()-started,python_version=sys.version.split()[0],limitations=['synthetic_R2_L05_shared_existing_runtime_only','Historical once-only admission stub and four self-issued gates','No actual016/history/realdata/quality/capacity/fresh-environment proof','Native numeric predictions not independently rerun; existing native replay receipt and raw score transports authenticated','Outer failed operation remains failed; no pure posthoc output may replace failure receipt'])
out=Path('/tmp/tlab-chosen3-v3-independent-worker-output-review-ledger.json');out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'ledger_path':str(out),'ledger_sha256':sha(out.read_bytes()),'worker_status':result['worker_output_status'],'whole_operation_status':result['whole_operation_status'],'pins':len(allpins),'refs':ref_checks,'maps':map_checks,'chosen_scalar_checks':scalar_checks,'metric_fields':scalar_fields,'draw_fields':draw_fields,'W_unique_rawscores':len(set(W_scores)),'rawscore_diffs':score_diffs,'ranking_diffs':rank_diffs,'bootstrap':bootstrap_stats,'resources':resources,'cpu':result['review_cpu_seconds'],'wall':result['review_wall_seconds']},indent=2))
