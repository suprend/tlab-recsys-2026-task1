"""Read-only existing full-source018 output review; one physical hash pass, no DB/API/native jobs."""
import time
ENTRY=time.monotonic()
import ast,hashlib,json,math,os,re,resource,signal,sys
from pathlib import Path
PROJECT=Path('/Users/mdpospelov/tlab-recsys-2026');MP=Path('/tmp/tlab-full-source018-independent-output-review-inputfreeze.json');CACHE_PATH=Path('/tmp/tlab-full-source018-independent-hash-cache.json');LEDGER=Path('/tmp/tlab-full-source018-independent-output-review-ledger.json');FRESH=Path('/tmp/tlab-full-source018-independent-output-review-freshness.json')
def need(v,s):
 if not v:raise ValueError(s)
def unique(ps):
 d={}
 for k,v in ps:need(k not in d,'duplicate JSON key');d[k]=v
 return d
def reject(v):raise ValueError('nonfinite JSON '+v)
def parsed(b):return json.loads(b,object_pairs_hook=unique,parse_constant=reject)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def state(p):
 s=Path(p).stat();return dict(device=s.st_dev,inode=s.st_ino,size_bytes=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,resolved_path=str(Path(p).resolve()))
def cpu():
 r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime
def peak():return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
def save(p,v):
 q=Path(str(p)+'.tmp');q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');q.replace(p)
raw_manifest=MP.read_bytes();need(hashlib.sha256(raw_manifest).hexdigest()=='f2e70cbce743cdaa2d7ab2e473be4251d9f8d00aac51a9073f8fe08acc1faaff','original metadata manifest changed');mf=parsed(raw_manifest);ROOT=Path(mf['root']);metadata=mf['files'];large=mf['large_files_not_read_or_hashed'];states={p:e['stat'] for p,e in metadata.items()};states.update(large);frozen={p:Path(e['snapshot_path']).read_bytes() for p,e in metadata.items()};cache={};large_reads=[];cache_hits=0;ref_checks=0;map_checks=0
for p,e in metadata.items():
 need(state(p)==e['stat'],'metadata stat changed before semantics '+p);key=str(e['stat']['device'])+':'+str(e['stat']['inode']);cache[key]=dict(sha256=e['sha256'],bytes=e['stat']['size_bytes'],physical_stat=e['stat'],first_path=p,read_count=1,metadata_frozen_before_review=True)
for p,s in large.items():need(state(p)==s,'large file stat changed before review '+p)
# Install the explicit review budget BEFORE any large content is opened.
resource.setrlimit(resource.RLIMIT_CPU,(179,180));need(resource.getrlimit(resource.RLIMIT_CPU)==(179,180),'review CPU fence readback failed')
def alarm(*_):raise TimeoutError('review wall fence expired')
signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,295)
def guard():
 need(cpu()<165,'review CPU persistence reserve reached');need(time.monotonic()-ENTRY<285,'review wall persistence reserve reached');need(peak()<=2**30,'review sampled self RSS exceeds1GiB')
need(not CACHE_PATH.exists(),'previous consumed review cache exists; no repeat physical hashing')
cache_record=dict(version=1,status='running',CPU_hard_seconds=180,wall_alarm_seconds=295,guard_CPU_seconds=165,guard_wall_seconds=285,RSS_bytes=2**30,metadata_physical_files=len(cache),files=cache,large_attempts=[],hashed_large_bytes=0)
save(CACHE_PATH,cache_record)
def json_at(p):return parsed(frozen[str(p)])
def digest_at(p):
 global cache_hits
 p=Path(p);name=str(p);need(name in states,'unfrozen reference '+name);s=state(p);need(s==states[name],'original file stat changed '+name);key=str(s['device'])+':'+str(s['inode'])
 if key in cache:
  cache_hits+=1;need(cache[key]['physical_stat']==s,'cached physical identity changed '+name);return cache[key]['sha256']
 need(name in large,'uncached large file not in finite allowance');guard();attempt=dict(path=name,physical_key=key,expected_bytes=s['size_bytes'],state='reading',bytes_read=0);cache_record['large_attempts'].append(attempt);save(CACHE_PATH,cache_record);h=hashlib.sha256();n=0;cpu0=cpu();wall0=time.monotonic()
 with p.open('rb',buffering=0) as stream:
  fs=os.fstat(stream.fileno());need((fs.st_dev,fs.st_ino,fs.st_size)==(s['device'],s['inode'],s['size_bytes']),'opened file identity changed')
  while True:
   guard();part=stream.read(4*2**20)
   if not part:break
   h.update(part);n+=len(part)
   if n%(64*2**20)<4*2**20:attempt['bytes_read']=n;save(CACHE_PATH,cache_record)
 need(n==s['size_bytes'] and state(p)==s,'large file changed during hash '+name);guard();entry=dict(sha256=h.hexdigest(),bytes=n,physical_stat=s,first_path=name,read_count=1,metadata_frozen_before_review=False,hash_cpu_seconds=cpu()-cpu0,hash_wall_seconds=time.monotonic()-wall0);cache[key]=entry;cache_record['files']=cache;cache_record['hashed_large_bytes']+=n;attempt.update(state='complete',bytes_read=n,sha256=entry['sha256']);large_reads.append(entry);save(CACHE_PATH,cache_record);print(json.dumps({'hashed_once':p.name,'bytes':n,'cpu_seconds':entry['hash_cpu_seconds'],'wall_seconds':entry['hash_wall_seconds'],'sha256':entry['sha256']}),flush=True);return entry['sha256']
def path_of(name):return Path(name) if Path(name).is_absolute() else PROJECT/name
def ref(v):
 global ref_checks
 need(set(v)=={'path','sha256'},'exact reference needed');need(digest_at(path_of(v['path']))==v['sha256'],'reference hash differs '+v['path']);ref_checks+=1

def walk(v):
 global map_checks
 if isinstance(v,dict):
  if set(v)=={'path','sha256'}:ref(v)
  for k,x in v.items():
   if k in ['fingerprints','outputs','metadata_pins'] and isinstance(x,dict):
    for p,d in x.items():
     if isinstance(d,str) and re.fullmatch('[0-9a-f]{64}',d):need(digest_at(path_of(p))==d,'map pin differs '+p);map_checks+=1
   walk(x)
 elif isinstance(v,list):
  for x in v:walk(x)
try:
 guard();external=json_at('/tmp/tlab-root-full-source018-external-lifetime-receipt.json');need(digest_at('/tmp/tlab-root-full-source018-external-lifetime-receipt.json')=='6418c99510bd993a85afe11e31c787798adcd7d0aa79b4939a4eb516f9726b62','Root external receipt differs')
 request=json_at(PROJECT/'artifacts/reproduction/requests/oct2019-full-018-20261015-once.json');claim=json_at(PROJECT/'artifacts/source-import-owner/claims/oct2019-full-018-20261015-once.json');report=json_at(ROOT/'report.json');context=json_at(ROOT/'worker-context.json');worker=json_at(ROOT/'worker-receipt.json');reaped=json_at(ROOT/'worker-reaped.json');consumed=json_at(ROOT/'worker.consumed.json');kernel_consumed=json_at(ROOT/'kernel/import.consumed.json');kernel=json_at(ROOT/'kernel/import-evidence.json');process=json_at('/tmp/tlab-full-source018-20261015-once-process-receipt.json');driver_stdout=json_at('/tmp/tlab-full-source018-20261015-once-driver.stdout.json');issued=json_at('/tmp/tlab-root-full-source018-operation-issued.json');stage=json_at('/tmp/tlab-root-full-source018-stage-receipt.json');edata=json_at(PROJECT/'artifacts/eda-october/quality.json');erun=json_at(PROJECT/'artifacts/eda-october/run.json');eid='oct2019-full-018-20261015-once';directory='artifacts/source-import-runs/'+eid
 need(request['execution_id']==claim['execution_id']==report['execution_id']==context['execution_id']==worker['execution_id']==eid,'original execution identity differs')
 need(request['output_directory']==claim['output_directory']==context['directory']==directory,'original output namespace differs')
 need(report['status']=='completed_source_import_pending_external_source_acceptance' and worker['status']=='source_import_worker_complete_unaccepted' and kernel['status']=='import_kernel_complete_pending_external_source_acceptance','original pending statuses differ')
 reqref=report['request'];claimref=report['claim'];ctxref=report['worker_context'];wref=report['worker_receipt'];kr=report['kernel_evidence'];br=report['worker_reaped_boundary'];need(reqref['sha256']=='17edb3954caed6cd409765e870ef8ec547bfc407e30f0e47f5d1df92f553219c','issued request differs')
 need(context['request']==worker['request']==consumed['request']==claim['request']==reqref and context['claim']==worker['claim']==consumed['claim']==claimref,'original authority association differs')
 need(worker['context']==reaped['context']==consumed['context']==ctxref and worker['evidence']==kr,'worker/kernel association differs')
 need(worker['consumed']['path']==directory+'/worker.consumed.json' and wref['path']==directory+'/worker-receipt.json' and ctxref['path']==directory+'/worker-context.json' and br['path']==directory+'/worker-reaped.json','fixed worker destinations differ')
 need(claimref['path']=='artifacts/source-import-owner/claims/'+eid+'.json','fixed once claim differs')
 need(claim['scope']=='consumed_original_typed9_import' and consumed['scope']=='consumed_typed9_import_worker' and claim['retry'] is consumed['retry'] is report['retry'] is False,'consumption/retry differs')
 need(claim['owner_pid']==context['owner_pid'] and claim['started_monotonic']==report['original_started_monotonic'] and consumed['started_monotonic']==worker['started_monotonic'],'owner/lifetime association differs')
 need(kernel_consumed['archive']==str(PROJECT/request['archive']) and kernel_consumed['work_directory']==str(ROOT/'kernel') and kernel_consumed['profile']==request['profile']==kernel['profile'],'kernel source linkage differs')
 need(report['limits']==request['resources'] and request['resources']['cpu_seconds']==7200 and request['resources']['wall_seconds']==10800,'original whole limits differ')
 need(claim['deadline_monotonic']==claim['started_monotonic']+10800 and context['allocation']['deadline_monotonic']==claim['deadline_monotonic']-10,'original deadlines differ')
 alloc=context['allocation'];need(alloc['cpu_seconds']==7182 and alloc['rss_bytes']==7*2**30 and alloc['cpu_seconds']<=7200-15-2,'worker original allocation differs')
 needed_outputs={directory+'/kernel/'+name for name in ['import-evidence.json','events.duckdb','source.csv.gz','source.csv','validated.csv','import.consumed.json']};need(set(worker['outputs'])==needed_outputs,'exact6 kernel output vocabulary differs')
 pins=dict(request['fingerprints']);pins.update({reqref['path']:reqref['sha256'],claimref['path']:claimref['sha256']});need(context['fingerprints']==pins,'worker original code authority closure differs')
 pins.update(worker['outputs']);pins.update({v['path']:v['sha256'] for v in [ctxref,wref,br,worker['consumed']]});pins[directory+'/worker.log']=hashlib.sha256(b'').hexdigest();pins[request['archive']]=request['profile']['compressed_sha256'];need(report['fingerprints']==pins,'complete owner18 closure differs')
 for v in [worker,report,kernel]:need(v['fit_attempt_count']==0 and v['labels_created'] is False,'downstream work claimed')
 for v in [worker,report,external,process,driver_stdout]:need(v['source_acceptance_issued'] is False,'source acceptance was rewritten')
 need(worker['descendant_cpu_seconds']==0 and reaped['actual_exit_code']==report['actual_worker_exit_code']==0 and reaped['worker_reaped'] is report['worker_reaped'] is reaped['owned_group_gone'] is True,'actual worker reap differs')
 need(worker['process_cpu_seconds']<=reaped['actual_reaped_cpu_seconds']==report['actual_reaped_worker_cpu_seconds']<=alloc['cpu_seconds'],'actual worker CPU differs')
 need(worker['process_peak_rss_bytes']==reaped['actual_reaped_peak_rss_bytes']==report['actual_reaped_worker_peak_rss_bytes']<=alloc['rss_bytes'],'worker RSS association differs')
 env=report['environment'];wenv=dict(env,kernel_cpu={'soft':7181,'hard':7182});need(report['worker_environment']==worker['environment']==wenv,'environment/fence differs')
 need(env['kernel_cpu'] is None and env['python']=='3.12.14' and env['duckdb']=='1.5.6' and env['platform']=='darwin' and env['architecture']=='arm64' and env['subprocess_probe'] is False and env['engine_settings']=={'threads':2,'memory':'2GB','spill_bytes':8*2**30},'locked runtime differs')
 need(env['lock_sha256']==request['fingerprints']['uv.lock'] and 'name = "duckdb"\nversion = "1.5.6"' in frozen[str(PROJECT/'uv.lock')].decode(),'lock version linkage differs')
 sr=process['supervisor_report'];need(sr['status']=='verified_normal_exit' and sr['reaped'] and sr['exit_code']==0 and sr['unknown_active_work'] is False and not sr['errors'] and not sr['signaled_pids'] and not sr['survivors_at_terminal_scan'],'external normal reaping differs')
 need(external['explicit_terminal_exit_code']==external['supervised_owner_reaped_exit_code']==0 and external['exec_session_id']==65471 and external['terminal_chunk']=='a5ea08','Root actual external terminal differs')
 need(process['command']==[str(PROJECT/'.venv/bin/python'),'-I','-B',str(PROJECT/'scripts/run_source_import.py'),'--request',reqref['path'],'--expected-request-sha',reqref['sha256']],'actual owner CLI differs')
 need(process['outer_limits']=={'cpu_seconds':7190,'wall_seconds':10790,'rss_bytes':8*2**30} and sr['cpu_upper_seconds']<=7190 and sr['elapsed_upper_seconds']<=10790,'outer original allocation differs')
 need(sr['actual_total_cpu_seconds'] is None and sr['supervisor_exit_tail_measured'] is False and process['driver_exit_tail_measured'] is driver_stdout['driver_exit_tail_measured'] is False and process['nested_owner_worker_ledger_accepted'] is process['external_full_exit_acceptance_issued'] is False and process['supervisor_flags_reinterpreted'] is False,'original measurement/acceptance flags changed')
 need(process['entry_monotonic']<=claim['started_monotonic']<=worker['started_monotonic']<=worker['finished_monotonic']<=reaped['reaped_at_monotonic']<=report['observed_finished_monotonic']<=process['entry_monotonic']+sr['elapsed_seconds']<alloc['deadline_monotonic'],'complete original monotonic lifetime differs')
 need(reaped['actual_reaped_cpu_seconds']<=report['observed_owner_and_reaped_children_cpu_seconds']<=sr['wait4_child_cpu_seconds']<=sr['observed_total_cpu_seconds'],'nested inclusive CPU accounting differs')
 profile=request['profile'];fields=['event_time','event_type','product_id','category_id','category_code','brand','price','user_id','user_session'];types=['TIMESTAMP','VARCHAR','BIGINT','BIGINT','VARCHAR','VARCHAR','DECIMAL(12,2)','BIGINT','VARCHAR'];need(kernel['schema']==[dict(name=n,type=t) for n,t in zip(fields,types)] and profile['fields']==fields and profile['types']==types,'typed9 schema/order differs')
 need(kernel['profile_sha256']==hashlib.sha256(canonical(profile).encode()).hexdigest() and kernel['summary']['rows']==profile['expected_rows']==42448764,'profile/row association differs')
 need(kernel['summary']['actions']=={r['event_type']:r['events'] for r in edata['events']} and kernel['summary']['nulls']==edata['missing'] and kernel['summary']['rows']==edata['summary']['rows']==erun['source']['rows'],'original EDA aggregate mismatch')
 need(kernel['summary']['minimum_time']==edata['summary']['first_time_utc']+'Z' and kernel['summary']['maximum_time']==edata['summary']['last_time_utc']+'Z' and edata['summary']['outside_october']==edata['summary']['unknown_event_types']==0,'original EDA time/action boundary differs')
 need(sum(kernel['summary']['actions'].values())==kernel['summary']['rows'] and erun['source']['sha256']==profile['compressed_sha256'] and erun['source']['compressed_bytes']==profile['compressed_bytes'],'original EDA/source identity differs')
 need(kernel['csv']['all_gzip_members_EOF_CRC_ISIZE_checked'] is True and kernel['validated_csv']['quoting']=='all_fields' and kernel['validated_csv']['parser']=='Python_csv_strict' and kernel['validated_csv']['native_reader_used'] is True,'canonical/native-reader linkage flags differ')
 need(kernel['parser']=='strict_typed9_no_float_keys_no_price_rounding_raw_bag' and kernel['database']['path']==str(ROOT/'kernel/events.duckdb'),'new DB/kernel identity differs')
 need(kernel['source']['bytes']==profile['compressed_bytes']==1741928540 and kernel['csv']['bytes']==profile['uncompressed_bytes']==5668612855 and kernel['validated_csv']['bytes']==6432690625 and kernel['database']['bytes']==1509437440,'file sizes differ')
 need(worker['spill_observation']=={'peak_measured':False,'retained_bytes':0,'retained_files':0},'retained spill metadata differs')
 all_current=list(ROOT.rglob('*'));bad=[str(p) for p in all_current if p.is_file() and (p.name.endswith('.wal') or 'failed' in p.name or 'spill' in p.parts)];need(not bad,'failure/WAL/spill leftovers '+repr(bad));need(not Path(str(PROJECT/claimref['path'])+'.failed.json').exists(),'claim failure marker exists')
 # No large content was opened before every bounded association check above passed.
 guard();need(cache_record['hashed_large_bytes']==0,'unexpected prior large read');print(json.dumps({'metadata_semantics':'passed','large_physical_files':len(large),'large_bytes_expected':sum(v['size_bytes'] for v in large.values()),'CPU_hard':resource.getrlimit(resource.RLIMIT_CPU),'wall_alarm_seconds':295,'memory_guard_bytes':2**30}),flush=True)
 for p in large:
  got=digest_at(p);rel=Path(p).relative_to(PROJECT).as_posix();need(got==report['fingerprints'][rel],'large output/archive pin differs '+p)
 # Complete refs reuse the physical digest cache; no large file is read twice.
 for p in [ROOT/'report.json',ROOT/'worker-context.json',ROOT/'worker-receipt.json',ROOT/'worker-reaped.json',ROOT/'worker.consumed.json'] :walk(json_at(p))
 for p,d in external['metadata_pins'].items():need(digest_at(p)==d,'Root bound metadata differs');map_checks+=1
 for key,kname in [('source','source.csv.gz'),('csv','source.csv'),('validated_csv','validated.csv'),('database','events.duckdb')]:need(digest_at(ROOT/'kernel'/kname)==kernel[key]['sha256'],'kernel byte binding differs')
 need(digest_at(PROJECT/request['archive'])==kernel['source']['sha256']==digest_at(ROOT/'kernel/source.csv.gz'),'original gzip/copy identity differs')
 actuallogs={}
 for name,entry in external['external_logs'].items():
  need(digest_at(entry['path'])==entry['sha256'],'external time log pin differs');text=frozen[entry['path']].decode();m=re.search(r'([0-9.]+) real\s+([0-9.]+) user\s+([0-9.]+) sys',text);wall,user,system=map(float,m.groups());need((wall,user,system)==(entry['wall_seconds_rounded'],entry['user_seconds_rounded'],entry['system_seconds_rounded']),'actual external timing differs');actuallogs[name]=dict(wall=wall,user=user,system=system,cpu_rounded=user+system,rounding_upper=entry['cpu_rounding_upper_seconds'])
 need(math.isclose(sum(v['rounding_upper'] for v in actuallogs.values()),external['charged_stage_plus_driver_cpu_rounding_upper_seconds']) and external['charged_stage_plus_driver_cpu_rounding_upper_seconds']==609.92 and external['charged_stage_plus_driver_wall_rounding_upper_seconds']==586.14,'charged inclusive external stage/driver differs')
 need(external['conservative_driver_and_outside_reserve_cpu_prefix_upper_seconds']==622<7200 and sr['observed_job_peak_rss_bytes']==external['sampled_aggregate_peak_bytes']<=8*2**30 and external['external_MAXRSS_bytes']==1915109376,'actual resource boundary differs')
 freshness={p:dict(initial=s,current=state(p),unchanged=state(p)==s) for p,s in states.items()};need(all(e['unchanged'] for e in freshness.values()),'scoped current stat changed after hash');initial_files={p for p in states if p.startswith(str(ROOT)+'/')};current_files={str(p) for p in ROOT.rglob('*') if p.is_file()};need(initial_files==current_files,'output namespace changed')
 save(FRESH,dict(version=1,policy='Final stable dev/inode/size/mtime/ctime; no second physical large read',files=freshness,output_namespace_unchanged=True));guard();cache_record.update(status='completed',cache_hits=cache_hits,large_physical_reads=len(large_reads),review_observed_CPU_seconds=cpu(),review_observed_wall_seconds=time.monotonic()-ENTRY,review_peak_RSS_bytes=peak());save(CACHE_PATH,cache_record)
 record=dict(version=1,scope='MAIN018_actual_fullsource_output_hash_and_aggregate_review',verdict='no_supported_output_findings_within_explicit_scope_pending_Root_source_acceptance',whole_row_or_DB_cell_oracle_performed=False,source_acceptance_issued=False,original_flags_unchanged=True,inputfreeze_path=str(MP),inputfreeze_sha256=hashlib.sha256(raw_manifest).hexdigest(),metadata_files=len(metadata),large_physical_file_reads=len(large_reads),large_hash_bytes=cache_record['hashed_large_bytes'],hash_cache_path=str(CACHE_PATH),cache_hits=cache_hits,large_files=large_reads,reference_checks=ref_checks,map_checks=map_checks,complete_owner_fingerprint_count=len(report['fingerprints']),summary=kernel['summary'],schema=kernel['schema'],canonical_csv_quoted_all_and_native_reader_linkage=True,original_EDA_aggregate_comparison_passed=True,new_DB_byte_identity_verified=True,original_historical_DB_opened_or_compared=False,review_budget=dict(CPU_seconds=180,wall_seconds=300,RSS_bytes=2**30,CPU_hard_readback=[179,180],guard_CPU=165,guard_wall=285,wall_alarm=295),review_observed_CPU_seconds=cpu(),review_observed_wall_seconds=time.monotonic()-ENTRY,review_peak_RSS_bytes=peak(),actual_import_external_logs=actuallogs,actual_import_cpu_rounding_upper=609.92,actual_import_wall_rounding_upper=586.14,conservative_import_prefix_CPU=622,review_external_terminal_evidence_pending=True,Root_import_terminal=dict(session=65471,chunk='a5ea08',exit_code=0),full_worker_owner_association=True,actual_worker_exit_code=0,fit_attempt_count=0,labels_created=False,no_fail_WAL_retained_spill=True,internal_supervisor_driver_exit_tail_flags_unmeasured_retained=True,freshness_path=str(FRESH),limitations=['Byte binding plus accepted kernel strict typed validation and native schema/count/actions/null/time conformance; no independent every-DB-cell comparison','Original source hash is project-observed, not publisher-signed','No DB connection, gzip decompression, SQL, fit, model, queryY, evaluation, rerun or source-acceptance write','Internal sampled RSS and exit-tail measurement limits preserved; Root owns final source acceptance'])
 save(LEDGER,record);print(json.dumps({'verdict':record['verdict'],'large_bytes_hashed_once':record['large_hash_bytes'],'large_physical_files':len(large_reads),'cache_hits':cache_hits,'CPU_seconds':record['review_observed_CPU_seconds'],'wall_seconds':record['review_observed_wall_seconds'],'peak_RSS_bytes':peak(),'ledger_path':str(LEDGER)}),flush=True);signal.setitimer(signal.ITIMER_REAL,0)
except BaseException as exc:
 cache_record.update(status='failed_preserved_no_repeat',error_type=type(exc).__name__,error=str(exc),review_observed_CPU_seconds=cpu(),review_observed_wall_seconds=time.monotonic()-ENTRY);save(CACHE_PATH,cache_record);save(Path('/tmp/tlab-full-source018-independent-output-review-failed.json'),cache_record);raise
