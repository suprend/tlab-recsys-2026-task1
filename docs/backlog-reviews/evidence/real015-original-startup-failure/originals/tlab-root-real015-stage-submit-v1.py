import pathlib,json,hashlib,os,sys,time,datetime
P=pathlib.Path('/Users/mdpospelov/tlab-recsys-2026');T=pathlib.Path('/tmp');OP=T/'tlab-root-real015-original-operation-issued-v1.json'
started=time.monotonic()
def raw_checked(p,digest):
 p=pathlib.Path(p);raw=p.read_bytes();assert len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==digest;return raw
raw=raw_checked(OP,'448b15aa8fcebbf95b8ea7774a11f2b5a58145ee6f3ec125db0b29ea68153da4');op=json.loads(raw);assert op['approved'] is True and op['status']=='prepared'
submitted=T/'tlab-root-real015-original-operation-submitted-v1.json';assert not submitted.exists()
for r in op['fresh_small_pins']:raw_checked(r['path'],r['sha256'])
rb=json.loads(raw_checked(op['fresh_request_closure_readback']['path'],op['fresh_request_closure_readback']['sha256']))
for r in rb['fresh_small_pins']:raw_checked(r['path'],r['sha256'])
for n in op['required_absent_project_paths']:
 p=P/n;assert not p.exists() and not p.is_symlink();assert p.resolve().is_relative_to(P.resolve())
assert not pathlib.Path(op['required_absent_external_directory']).exists()
staged=[]
for r in op['stage_files']:
 content=raw_checked(r['source']['path'],r['source']['sha256']);p=P/r['destination'];p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(content);f.flush();os.fsync(f.fileno())
 assert hashlib.sha256(p.read_bytes()).hexdigest()==r['source']['sha256'];staged.append(dict(path=r['destination'],sha256=r['source']['sha256']))
receipt=dict(version=1,status='submitted_before_exec',submitted_at_utc=datetime.datetime.now(datetime.UTC).isoformat(),operation_id=op['operation_id'],operation_sha256=hashlib.sha256(raw).hexdigest(),stage_files=staged,driver=op['driver'],request=op['request'],launch_argv=op['runtime_argv'],stage_wall_seconds=time.monotonic()-started,pid=os.getpid(),note='A lost tool outcome is UNKNOWN; inspect original owner claim and this fixed observer namespace before any repeat. This consumes no replacement owner or grant. Root manual four gates still required.')
with submitted.open('x') as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
os.chdir(P);os.execv(op['runtime_argv'][0],op['runtime_argv'])
