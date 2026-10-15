import ast,pathlib,json,hashlib,math,datetime,time,re
T=pathlib.Path('/tmp');P=pathlib.Path('/Users/mdpospelov/tlab-recsys-2026');SP=T/'tlab-root-real015-runtime-gate-v2.py';s=SP.read_text();assert hashlib.sha256(s.encode()).hexdigest()=='ccdeab718445a8b2b7a74dfd6cbf22974983518d02dbaa3bd9cf7ba2440d5986'
s=s.replace("REPORT['reserved_targets_may_have_been_opened'] is False","REPORT['reserved_targets_may_have_been_opened'] is True").replace("receipt['labels_loaded'] is False","receipt['labels_loaded'] is (role in ROLES[4:])")
anchor=" for name,ref in REPORT['gates'].items():\n";assert s.count(anchor)==1
s=s.replace(anchor," for name in ['prediction-boundary.json','all-predictions-inventory.json','target-policy.json']:\n  value,r=read(D/name);merge({r['path']:r['sha256']})\n"+anchor)
tr=ast.parse(s);names={'canon','digest','raw','read','merge','init'};const={'P','T','D','START','SEEN','CACHE','ROLES','CAPS'};nodes=[]
for n in tr.body:
 if isinstance(n,ast.Import):nodes.append(n)
 elif isinstance(n,ast.Assign) and all(isinstance(t,ast.Name) and t.id in const for t in n.targets):nodes.append(n)
 elif isinstance(n,ast.FunctionDef) and n.name in names:nodes.append(n)
ns={};exec(compile(ast.Module(body=nodes,type_ignores=[]),'<Root-final-metadata-only>','exec'),ns);run=ns['init'](6);read=ns['read'];D=ns['D'];r=ns['REPORT'];closure=ns['CLOSURE'];seen=ns['SEEN']
assert r['status']=='verified_reporting_pending_external_lifetime_acceptance' and set(r['gates'])=={'initial_execution','source_acceptance','prediction_acceptance','target_execution'} and r['independent_fullY_pairs']==307
assert r['actual_total_cpu_seconds']==r['actual_parent_cpu_seconds']+r['actual_reaped_children_cpu_seconds'] and r['actual_total_cpu_seconds']<=4200 and r['seconds']<=7200 and r['parent_peak_rss_bytes']<=2**30
assert r['reporting_policy']=='confirmation25_reporting_only_and_final26_31_frozen_no_adaptation'
evalbody,er=read(D/'targets_evaluation/evaluation.json');oracle,orr=read(D/'metric_oracle/evidence.json');core=oracle['core'];targetpolicy,tpr=read(D/'target-policy.json');pred,pr=read(P/r['gates']['prediction_acceptance']['path']);target,tar=read(P/r['gates']['target_execution']['path']);ctx,ctr=read(D/'metric_oracle/context.json');consumed,csr=read(D/'metric_oracle/execution.consumed.json')
assert oracle['context']==ctr and oracle['execution_consumed']==csr and oracle['inputs']==ctx['inputs'] and oracle['run_id']==run and oracle['decision_lock']==r['decision_lock']
assert core['status']=='independent_core_values_match_pending_owner_acceptance' and core['proof_scope']=='raw_fullY_all_queries_all_scores_four_estimands_every_fixed_user_draw_no_lifetime_or_byte_authentication' and core['fullY_pairs']==307 and core['private_ranking_rows_checked']==28000 and core['bootstrap_replicates_per_estimand']==200 and core['fit_attempt_count']==core['native_prediction_count']==0
assert evalbody['scope']=='unaccepted_reserved_fullY_reporting' and evalbody['fit_attempt_count']==evalbody['native_prediction_count']==0 and evalbody['labels_loaded'] is True and evalbody['periods']==r['aggregate_periods']
assert target['sealed_at']>=pred['sealed_at'] and core['oracle_target_stage_opened_at']>=target['sealed_at'] and core['oracle_fullY_started_at']>=core['oracle_target_stage_opened_at'] and targetpolicy['no_adaptation'] is True
comparisons=0

def close(a,b):
 global comparisons
 if type(a) is dict:assert type(b) is dict and set(a)==set(b);[close(a[k],b[k]) for k in a]
 elif type(a) is list:assert type(b) is list and len(a)==len(b);[close(x,y) for x,y in zip(a,b)]
 elif type(a) in (int,float) and type(b) in (int,float):assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12);comparisons+=1
 else:assert a==b
close(r['aggregate_periods'],core['periods'])
for period in r['aggregate_periods'].values():
 for estimand,b in period['paired_user_bootstrap'].items():assert b['seed']==2026 and b['replicates']==200 and len(b['samples'])==200 and b['undefined_draws']==0
observer=T/'tlab-real015-observer-environment-recovery-20261015';control=json.loads((observer/'controller-result.json').read_bytes());v6=json.loads((observer/'V6-observation.json').read_bytes());reportsha=hashlib.sha256((D/'report.json').read_bytes()).hexdigest();claimsha=hashlib.sha256((P/'artifacts/heldout-study/owner.claim.json').read_bytes()).hexdigest()
assert control['owner_exit_code']==0 and control['owner_explicitly_reaped'] is True and control['owner_report_sha256']==reportsha and control['owner_claim_sha256']==claimsha and control['status']=='six_role_owner_complete_pending_Root_readback_and_full_exit'
assert v6['status']=='verified_normal_exit' and v6['exit_code']==0 and v6['reaped'] is True and v6['unknown_active_work'] is False and v6['errors']==[] and v6['survivors_at_terminal_scan']==[] and v6['observed_process_count']==8 and v6['observed_job_peak_rss_bytes']<=8*2**30
log=T/'tlab-root-real015-environment-recovery-external-v1.log';txt=log.read_text();m=re.search(r'([0-9.]+) real\s+([0-9.]+) user\s+([0-9.]+) sys',txt);assert m;wall,u,sy=map(float,m.groups());rss=int(re.search(r'(\d+)\s+maximum resident set size',txt).group(1));assert wall<=7200 and u+sy<=4200 and rss<=8*2**30
for role in r['roles']:assert role['native_prediction_count']==(14 if role['role'] in ['predictions','prediction_oracle'] else 0)
summary={}
for name,p in r['aggregate_periods'].items():summary[name]=dict(anchors=p['anchors'],metrics={a:p['metrics'][a]['conditional_macro_query'] for a in ['B','W']},query_count=p['metrics']['B']['query_count'],positive_queries=p['metrics']['B']['nonempty_query_count'],mature_users=p['metrics']['B']['mature_user_count'],positive_users=p['metrics']['B']['positive_user_count'],ndcg_delta=p['ndcg_W_minus_B']['conditional_macro_query'],paired_user_bootstrap_95=p['paired_user_bootstrap']['conditional_macro_query']['interval_95'],undefined_draws=p['paired_user_bootstrap']['conditional_macro_query']['undefined_draws'])

def pin(p):
 p=pathlib.Path(p);b=p.read_bytes();assert len(b)<=1048576;return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
extra=[T/'tlab-root-real015-environment-recovery-operation-issued-v1.json',T/'tlab-root-real015-environment-recovery-submitted-v1.json',T/'tlab-root-real015-recovery-submit-v1.py',log,observer/'controller-result.json',observer/'V6-observation.json',T/'tlab-root-real015-initial-gate-readback-v1.json',T/'tlab-root-real015-source_acceptance-readback-v1.json',T/'tlab-root-real015-prediction_acceptance-readback-v1.json',T/'tlab-root-real015-target_execution-readback-v1.json',SP,pathlib.Path(__file__)]
body=dict(version=1,status='ROOT_ACCEPTED_COMPLETE_RESERVED_REPORTING',accepted_at_utc=datetime.datetime.now(datetime.UTC).isoformat(),run_id=run,owner_directory=D.relative_to(P).as_posix(),terminal=dict(session_id=67253,chunk_id='0ce0cd',exit_code=0,closed=True),report_sha256=reportsha,claim_sha256=claimsha,fullY_pairs=307,private_ranking_rows_independently_checked=28000,metric_numeric_comparisons=comparisons,periods=summary,metadata_reads=seen,external_evidence=[pin(p) for p in extra],external_resources=dict(wall_seconds_rounded=wall,cpu_seconds_rounded=u+sy,wall_upper_seconds=wall+.01,cpu_upper_seconds=u+sy+.02,maximum_resident_set_size_bytes=rss,sampled_job_peak_rss_bytes=v6['observed_job_peak_rss_bytes'],V6_conservative_cpu_upper_seconds=v6['cpu_upper_seconds'],V6_conservative_wall_upper_seconds=v6['elapsed_upper_seconds']),native_predictions_each_prediction_role=14,total_native_predictions=28,fit=0,adaptation=False,decision_cost_33914_43200_1000_300_unchanged=True,old_V3_018_failure_unknown_flags_immutable=True,original_producer_pending_flags_not_rewritten=True,proof_limits='full chosen3 source and all7 independent score/rank parity, fullY/four estimands/every fixed bootstrap draw; core18 source numeric values remain sampled. RSS sampled, no arbitrary descendant hardcontainment. Binary refs authenticated by original owner/oracles, not reread by Root.',Root_reserve='original10/10 with carryforward debit; no refill; runtime phase full profiles recorded separately',readback_body_wall_seconds=time.monotonic()-ns['START'])
out=T/'tlab-root-real015-complete-reporting-acceptance-v1.json'
with out.open('x') as f:json.dump(body,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps(dict(acceptance=pin(out),periods=summary,metrics_numeric_comparisons=comparisons,metadata_files=len(seen),external_resources=body['external_resources'])))
