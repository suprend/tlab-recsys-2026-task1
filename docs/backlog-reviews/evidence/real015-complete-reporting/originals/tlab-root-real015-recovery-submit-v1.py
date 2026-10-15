import pathlib,json,hashlib,os,datetime,time
T=pathlib.Path('/tmp');P=pathlib.Path('/Users/mdpospelov/tlab-recsys-2026');p=T/'tlab-root-real015-environment-recovery-operation-issued-v1.json';b=p.read_bytes();assert hashlib.sha256(b).hexdigest()=='0ad85714f478a682f7dfc804d9107958a6b12a95264cdf0401d283822377150c';o=json.loads(b);assert o['approved'] is True and o['status']=='prepared'
for r in o['fresh_small_pins']:
 raw=pathlib.Path(r['path']).read_bytes();assert len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==r['sha256']
assert not (P/o['canonical_claim']).exists() and not pathlib.Path(o['required_absent_namespace']).exists()
req=json.loads(pathlib.Path(o['request']['path']).read_bytes());assert all(not (P/n).exists() for n in req['authority_paths'].values())
p=T/'tlab-root-real015-environment-recovery-submitted-v1.json';assert not p.exists()
r=dict(version=1,status='submitted_before_exec',operation_id=o['operation_id'],operation_sha256=hashlib.sha256(b).hexdigest(),submitted_at_utc=datetime.datetime.now(datetime.UTC).isoformat(),pid=os.getpid(),driver=o['driver'],request=o['request'],remaining_Root_external_reserve_only=o['remaining_Root_external_reserve_only'],no_staging_or_claim_reset=True)
with p.open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
os.chdir(P);os.execv(o['runtime_argv'][0],o['runtime_argv'])
