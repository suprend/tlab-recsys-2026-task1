import pathlib,json,hashlib,math,datetime,time,os,sys
P=pathlib.Path('/Users/mdpospelov/tlab-recsys-2026');T=pathlib.Path('/tmp');D=P/'artifacts/heldout-invocations/f8791cc605bb429c817f7f93a163c3a7';START=time.monotonic();SEEN={};CACHE={}
ROLES=['source','source_oracle','predictions','prediction_oracle','targets_evaluation','metric_oracle'];CAPS=[(900,1200),(900,1200),(600,900),(600,900),(300,600),(300,600)]
PROOFLIMIT='Pure caller-owned connection core; refs/source/code/lifetime are authenticated externally. Q/C and metadata/coverage/chosen0or3 values exhaustive; new-date core18 numeric values sampled. No files, models, Y, target capability, approval or resource allowance.'
DAYS=[f'2019-10-{i:02d}T00:00:00Z' for i in range(25,32)]
def canon(o):return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(o):return hashlib.sha256(canon(o).encode()).hexdigest()
def raw(p):
 p=pathlib.Path(p);assert p.resolve().is_relative_to(P.resolve()) and not any(x.is_symlink() for x in [p,*p.parents]);s=p.stat();assert s.st_size<=2**20
 b=p.read_bytes();z=p.stat();assert (s.st_ino,s.st_mtime_ns,s.st_size)==(z.st_ino,z.st_mtime_ns,z.st_size)
 ref=dict(path=p.relative_to(P).as_posix(),sha256=hashlib.sha256(b).hexdigest());SEEN[ref['path']]=dict(bytes=len(b),sha256=ref['sha256']);assert len(SEEN)<=64 and sum(v['bytes'] for v in SEEN.values())<=16*2**20
 return b,ref
def read(p):
 p=pathlib.Path(p)
 if p in CACHE:return CACHE[p]
 b,r=raw(p)
 def unique(pairs):
  a={}
  for k,v in pairs:assert k not in a;a[k]=v
  return a
 def bad(v):raise ValueError('Nonfinite JSON')
 o=json.loads(b,object_pairs_hook=unique,parse_constant=bad);canon(o);CACHE[p]=(o,r);return o,r
def merge(m):
 for k,v in m.items():assert k not in CLOSURE or CLOSURE[k]==v;CLOSURE[k]=v

def init(n):
 global CLAIM,REQUEST,CREATED,REPORT,CLOSURE,LOCK,CHOICE,INPUTS
 CLAIM,cr=read(P/'artifacts/heldout-study/owner.claim.json');assert CLAIM['output_directory']==D.relative_to(P).as_posix()
 REQUEST,rr=read(P/CLAIM['request']['path']);assert rr==CLAIM['request'] and rr['sha256']=='de1eacf7283d564ea5dae8a1f38a9938c4d6f4bc560dcbe79af9d659fa40101b'
 CREATED,_=read(D/'session.created.json');REPORT,_=read(D/'report.json');LOCK,lr=read(D/'decision-lock.json');CHOICE,chr=read(D/'authenticated-choice.json');proposal,pr=read(D/'proposal.json');ident=proposal['identity'];plan=CREATED['plan']
 assert CREATED['request']==rr and CREATED['owner_claim']==cr and ident['request']==rr and ident['owner_claim']==cr and ident['lock']==lr and ident['authenticated_choice']==chr
 assert digest(ident)==proposal['run_id']==plan['run_id']==REPORT['run_id']=='c24ba56f267f417cf673542baca1518ac24c8ddd0e4349d7ca9193f5567684c9'
 assert plan['fingerprints']==dict(ident['fingerprints'],**{pr['path']:pr['sha256']}) and plan['choice']==LOCK['choice']=='R2' and LOCK['models']==CHOICE['models']
 assert REPORT['active_role'] is None and REPORT['unknown_active_work'] is False and REPORT['fit_attempt_count']==0 and REPORT['reserved_targets_may_have_been_opened'] is False and [s['role'] for s in REPORT['roles']]==ROLES[:n]
 assert not (D/'report.failed.json').exists();CLOSURE=dict(plan['fingerprints']);INPUTS=dict(lock=lr,choice=chr,**REQUEST['source_inputs'])
 for name,ref in REPORT['gates'].items():
  body,actual=read(P/ref['path']);assert actual==ref and body['run_id']==plan['run_id'] and body['approved'] is True;merge({ref['path']:ref['sha256']})
 for i,record in enumerate(REPORT['roles']):
  role=ROLES[i];base=D/role
  for f in ['report.failed.json','evidence.failed.json','worker.log.cleanup-failed.json']:assert not (base/f).exists()
  context,ct=read(base/'context.json');slot,sr=read(base/'slot.json');launch,lref=read(base/'launch.json');consumed,cs=read(base/'execution.consumed.json');receipt,rref=read(base/'receipt.json');reap,repref=read(D/(role+'-reaped.json'));_,logref=raw(base/'worker.log');evidence,evref=read(P/receipt['evidence']['path'])
  assert context['run_id']==plan['run_id'] and context['request']==rr and context['owner_claim']==cr and context['plan']==plan and context['role']==role and context['slot']==sr and context['entry']==REQUEST['role_entries'][role]
  alloc=context['allocation'];cpu,wall=CAPS[i];assert type(alloc['cpu_seconds']) is int and 0<alloc['cpu_seconds']<=cpu and alloc['rss_bytes']==7*2**30 and alloc['deadline_monotonic']<=CREATED['original_deadline']-20 and alloc['deadline_monotonic']-context['issued_at_monotonic']<=wall
  assert slot==dict(version=1,scope='reserved_role_slot',role=role,ordinal=i,run_id=plan['run_id'],allocation=alloc,entry=context['entry'])
  argv=[str(P/'.venv/bin/python'),str(P/context['entry']['path']),'--context',str(base/'context.json'),'--issued-context-sha256',ct['sha256']]
  assert launch==dict(argv=argv,issued_context_sha256=ct['sha256'],original_slot=slot,context=ct,entry=context['entry'],allocation=alloc)
  assert consumed==dict(version=1,scope='reserved_child_execution_consumed',role=role,run_id=plan['run_id'],context=ct,slot=sr)
  assert record['receipt']==rref and receipt['context']==ct and receipt['inputs']==context['inputs'] and receipt['execution_consumed']==cs and receipt['evidence']==evref and receipt['role']==role and receipt['run_id']==plan['run_id'] and receipt['status']=='role_complete_unaccepted'
  assert receipt['scope']=='reserved_reporting_'+role and receipt['fit_attempt_count']==0 and receipt['labels_loaded'] is False and receipt['descendant_cpu_seconds']==0 and set(receipt['outputs'])==set(context['expected_outputs'])
  assert context['issued_at_monotonic']<=receipt['started_monotonic']<=receipt['finished_monotonic']<=alloc['deadline_monotonic'];actual=record['actual_reaped_cpu_seconds'];assert math.isfinite(actual) and receipt['process_cpu_seconds']<=actual+1e-6<=alloc['cpu_seconds']+1e-6
  assert 0<receipt['process_peak_rss_bytes']<=7*2**30 and reap['parent_peak_rss_bytes']+receipt['process_peak_rss_bytes']<=8*2**30
  assert reap['role']==role and reap['run_id']==plan['run_id'] and reap['context']==ct and reap['receipt']==rref and reap['log']==logref and reap['explicitly_reaped_exit_code']==0 and reap['actual_reaped_cpu_seconds']==actual
  for name,ref in context['inputs'].items():assert CLOSURE.get(ref['path'])==ref['sha256']
  for name,ref in context['authorities'].items():assert REPORT['gates'][name]==ref
  for ref in [ct,sr,lref,cs,evref,rref,repref,logref]:merge({ref['path']:ref['sha256']})
  merge(receipt['outputs']);assert CLOSURE[evref['path']]==evref['sha256']
 return plan['run_id']

def issue_source():
 run=init(2);assert set(REPORT['gates'])=={'initial_execution'}
 manifest,mr=read(D/'source/source-manifest.json');oracle,oref=read(D/'source_oracle/evidence.json');core=oracle['core'];days=manifest['days'];scontext,sctx=read(D/'source/context.json');ocontext,octx=read(D/'source_oracle/context.json');oconsumed,ocref=read(D/'source_oracle/execution.consumed.json')
 assert CLOSURE[mr['path']]==mr['sha256'] and CLOSURE[oref['path']]==oref['sha256'] and manifest['run_id']==run and manifest['choice']==INPUTS['choice'] and manifest['decision_lock']==INPUTS['lock'] and manifest['source']==REQUEST['source_inputs']['source']
 assert manifest['scope']=='unaccepted_reserved_source' and manifest['labels_loaded'] is False and manifest['fit_attempt_count']==manifest['native_prediction_count']==0
 assert oracle['context']==octx and oracle['execution_consumed']==ocref and oracle['inputs']==ocontext['inputs'] and oracle['choice']==INPUTS['choice'] and oracle['decision_lock']==INPUTS['lock'] and oracle['run_id']==run
 assert core['status']=='source_core_checked_pending_external_acceptance' and core['scope']=='independent_reserved_source_core' and core['choice']=='R2' and core['checked_days']==[d['anchor'] for d in days]==DAYS and core['verified_outputs']==days
 assert core['source_Q_C_domain_complete'] is True and core['chosen_formula_values_complete'] is True and core['mismatch_count']==0 and core['extra_proof_scope']=='all_selected3_values_every_C_row' and core['proof_limits']==PROOFLIMIT
 strata={'bottom_hash':4,'pair_view_support':1,'category_missing':1,'category_ambiguous':1,'past_pair_purchase_support':1,'old_recency_support':1}
 for a,b in zip(core['days'],days):
  assert a['anchor']==b['anchor'] and a['chosen_columns']==3 and a['chosen_scalar_values']==3*b['candidate_count'] and a['source_Q_C_complete'] is True and a['metadata_ages_coverage_complete'] is True and a['chosen_formula_values_complete'] is True
  assert a['query_count']==a['mature_query_count']==b['query_count']==b['mature_query_count']==2000 and a['candidate_count']==b['candidate_count']<=440000
  assert 4<=a['base_core18_sample_pairs']<=9 and a['base_core18_comparisons']==18*a['base_core18_sample_pairs'] and set(a['strata'])==set(strata)
  for name,cap in strata.items():assert a['strata'][name]['sampled_pairs']==min(cap,a['strata'][name]['available_pairs'])
  for key in ['queries','candidates','base_features','extra_features']:assert CLOSURE[b[key]['path']]==b[key]['sha256'] and '/source/day-'+b['anchor'][8:10]+'/' in b[key]['path']
 for a in [core,*core['days']]:assert a['labels_loaded'] is False and a['target_relation_created'] is False and a['fit_attempt_count']==a['native_prediction_count']==0 and a['baseline_formula_values_complete'] is False and a['base_proof_scope']=='all_structure_metadata_coverage_core18_sampled'
 assert core['query_count']==sum(d['query_count'] for d in days)==14000 and core['candidate_count']==sum(d['candidate_count'] for d in days)==2861322 and core['chosen_scalar_values']==3*core['candidate_count'] and core['base_core18_sample_pairs']==sum(d['base_core18_sample_pairs'] for d in core['days'])
 for role in ['source','source_oracle']:assert next(r for r in REPORT['roles'] if r['role']==role)['native_prediction_count']==0
 sr,_=read(D/'source/receipt.json');assert manifest['outputs']=={k:v for k,v in sr['outputs'].items() if k!=mr['path']}
 sealed=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ');reap,_=read(D/'source_oracle-reaped.json');assert sealed>=reap['reaped_at']
 body=dict(version=1,approved=True,scope='reviewed_reserved_source',run_id=run,fingerprints=CLOSURE,days=days,proof_limits=PROOFLIMIT,sealed_at=sealed)
 save('source_acceptance',body,dict(query_count=core['query_count'],candidate_count=core['candidate_count'],chosen_scalar_values=core['chosen_scalar_values'],base_core18_sample_pairs=core['base_core18_sample_pairs'],base_core18_comparisons=core['base_core18_comparisons'],core18_exhaustive=False,chosen3_exhaustive=True))

def save(gate,body,findings):
 dest=P/REQUEST['authority_paths'][gate];assert not dest.exists()
 with dest.open('x') as f:json.dump(body,f,sort_keys=True,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
 receipt=dict(version=1,gate=gate,run_id=body['run_id'],gate_ref=dict(path=dest.relative_to(P).as_posix(),sha256=hashlib.sha256(dest.read_bytes()).hexdigest()),accepted_at_utc=datetime.datetime.now(datetime.UTC).isoformat(),metadata_reads=SEEN,binary_hashes='transcribed authenticated role/oracle refs, not opened by Root',findings=findings,root_body_wall_seconds=time.monotonic()-START,fit=0,targets_opened=False)
 out=T/('tlab-root-real015-'+gate+'-readback-v1.json')
 with out.open('x') as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in receipt.items() if k!='metadata_reads'}))

def prediction_proof():
 run=init(4);assert set(REPORT['gates']) in [{'initial_execution','source_acceptance'},{'initial_execution','source_acceptance','prediction_acceptance'}]
 source,sref=read(D/'source/source-manifest.json');manifest,mr=read(D/'predictions/prediction-manifest.json');inventory,ir=read(D/'all-predictions-inventory.json');boundary,br=read(D/'prediction-boundary.json');oracle,oref=read(D/'prediction_oracle/evidence.json');core=oracle['core'];pc,pc_ref=read(D/'predictions/context.json');oc,oc_ref=read(D/'prediction_oracle/context.json');consumed,cs=read(D/'prediction_oracle/execution.consumed.json')
 assert CLOSURE[mr['path']]==mr['sha256'] and CLOSURE[oref['path']]==oref['sha256'] and manifest['run_id']==run and manifest['choice']==INPUTS['choice'] and manifest['decision_lock']==INPUTS['lock']
 assert manifest['source_manifest']==sref and manifest['source_acceptance']==REPORT['gates']['source_acceptance'] and manifest['scope']=='unaccepted_reserved_predictions' and manifest['labels_loaded'] is False and manifest['fit_attempt_count']==0 and manifest['native_prediction_count']==14
 assert oracle['context']==oc_ref and oracle['execution_consumed']==cs and oracle['inputs']==oc['inputs'] and oracle['choice']==INPUTS['choice'] and oracle['decision_lock']==INPUTS['lock'] and oracle['run_id']==run
 assert core['status']=='independent_all_seven_scores_match_pending_owner_acceptance' and core['proof_scope']=='all7_independent_matrix_native_scores_rank_order_with_external_byte_lifetime_authority' and core['labels_loaded'] is False and core['fit_attempt_count']==0 and core['native_prediction_count']==14
 assert not set(core)&{'private_replayed_scores','private_targets','private_rankings'} and [d['anchor'] for d in core['days']]==DAYS and [d['anchor'] for d in inventory['days']]==DAYS and inventory['days']==manifest['days']
 for day,sday,cday in zip(inventory['days'],source['days'],core['days']):
  for k,v in sday.items():assert day[k]==v
  assert cday==dict(status='independent_daily_scores_match_pending_all_date_and_owner_acceptance',anchor=day['anchor'],queries=day['query_count'],candidate_pairs=day['candidate_count'],native_prediction_count=2,fit_attempt_count=0,outcome_relations_opened=0,proof_scope='independent_Q_C_F_numeric_projection_native_state_all_rawscores_complete_rank_order_no_byte_or_lifetime_authentication')
  for role,width in [('B',41),('W',44)]:
   spec=day['predictions'][role];assert spec['model']==LOCK['models'][role]['model'] and spec['feature_names']==LOCK['models'][role]['feature_names'] and len(spec['feature_names'])==width and spec['scoring_prefix']==300 and spec['queries']==day['query_count'] and spec['rows']==day['candidate_count']
   ref=spec['artifact'];assert CLOSURE[ref['path']]==ref['sha256'] and ref['path']==(D/'predictions'/('day-'+day['anchor'][8:10])/(role+'.npz')).relative_to(P).as_posix()
 for role in ['predictions','prediction_oracle']:assert next(r for r in REPORT['roles'] if r['role']==role)['native_prediction_count']==14
 predreceipt,pr=read(D/'predictions/receipt.json');oraclereceipt,orr=read(D/'prediction_oracle/receipt.json');assert manifest['outputs']=={k:v for k,v in predreceipt['outputs'].items() if k!=mr['path']}
 old=dict(CLOSURE)
 if 'prediction_acceptance' in REPORT['gates']:old.pop(REPORT['gates']['prediction_acceptance']['path'])
 assert boundary['fingerprints']==old and boundary['producer']==pr and boundary['oracle']==orr and boundary['prediction_manifest']==mr and boundary['output_verification']==oref and boundary['native_calls_each_role']==14 and boundary['heldout_targets_opened'] is False and boundary['run_id']==run
 assert inventory['scope']=='all_reserved_predictions_before_targets' and inventory['decision_lock_sha256']==digest(LOCK) and inventory['source_acceptance']==REPORT['gates']['source_acceptance'] and inventory['output_verification']==oref and inventory['lifetime_receipt']==br and inventory['heldout_targets_opened'] is False and inventory['created_at']==manifest['created_at']
 merge({br['path']:br['sha256'],ir['path']:ir['sha256']});return run,inventory,ir,boundary,br

def issue_predictions():
 run,inventory,ir,boundary,br=prediction_proof();assert set(REPORT['gates'])=={'initial_execution','source_acceptance'}
 sealed=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ');assert sealed>=boundary['reaped_at']
 body=dict(version=1,approved=True,scope='reviewed_all_reserved_predictions_before_targets',run_id=run,fingerprints=CLOSURE,inventory=ir,sealed_at=sealed)
 save('prediction_acceptance',body,dict(days=7,query_count=14000,candidate_count=2861322,native_predictions_each_role=14,independent_full_rawscores_and_complete_rank_order=True,targets_opened=False))

def issue_targets():
 run,inventory,ir,boundary,br=prediction_proof();assert set(REPORT['gates'])=={'initial_execution','source_acceptance','prediction_acceptance'}
 predref=REPORT['gates']['prediction_acceptance'];pred,predactual=read(P/predref['path']);assert predactual==predref and pred['inventory']==ir and pred['scope']=='reviewed_all_reserved_predictions_before_targets'
 policy,pref=read(D/'target-policy.json');assert policy==dict(prediction_acceptance=predref,prediction_inventory_sha256=digest(inventory),decision_lock_sha256=digest(LOCK),periods=['confirmation25_reporting_only','final26_31_frozen'],no_adaptation=True,earliest_opened_at=pred['sealed_at'])
 merge({pref['path']:pref['sha256']});sealed=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ');assert sealed>=pred['sealed_at']
 body=dict(version=1,approved=True,scope='report_only_reserved_fullY',run_id=run,fingerprints=CLOSURE,target_policy=pref,sealed_at=sealed)
 save('target_execution',body,dict(all7_predictions_already_sealed=True,prediction_sealed_at=pred['sealed_at'],periods=policy['periods'],no_adaptation=True,targets_opened_by_Root=False))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1] in {'predictions','targets'}
 (issue_predictions if sys.argv[1]=='predictions' else issue_targets)()
