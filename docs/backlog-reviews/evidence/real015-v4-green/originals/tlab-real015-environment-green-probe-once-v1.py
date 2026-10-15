import ast,hashlib,json,os,pathlib,resource,signal,subprocess,sys,time,types
T=pathlib.Path('/tmp');P=pathlib.Path('/Users/mdpospelov/tlab-recsys-2026');OUT=T/'tlab-real015-environment-green-probe-once-v1'
V6=T/'tlab-heldout-harness-processes.py';DRIVER=T/'tlab-real015-existing-v6-driver-v4.py';GRANT=T/'tlab-root-real015-environment-green-grant-v1.json'
started=time.monotonic();signal.alarm(8);resource.setrlimit(resource.RLIMIT_CPU,(4,5))
assert len(sys.argv)==2;graw=GRANT.read_bytes();assert hashlib.sha256(graw).hexdigest()==sys.argv[1];g=json.loads(graw)
assert g['approved'] is True and g['script_sha256']==hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest() and g['driver_sha256']=='c00775f4ac0127b565c73b211d1783cde46fd4c357841c788050d2eac0d93428'
assert g['limits']=={'cpu_seconds':5,'wall_seconds':10,'rss_bytes':134217728,'backend_constructors':1,'children':1,'supervise':0,'owner':0,'fit':0,'predict':0,'model_load':0,'DB':0,'Y':0}
assert not OUT.exists();OUT.mkdir()
raw=DRIVER.read_bytes();assert hashlib.sha256(raw).hexdigest()==g['driver_sha256']
tree=ast.parse(raw);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'need','environment','validate_child_environment'}];assert len(nodes)==3
ns={'os':os,'sys':sys,'OUT':T/'tlab-real015-observer-environment-recovery-20261015'};exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pinned-env-functions>','exec'),ns);expected=ns['environment']()
vraw=V6.read_bytes();assert hashlib.sha256(vraw).hexdigest()=='449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
v=types.ModuleType('accepted_green_probe_v6');v.__file__=str(V6);sys.modules[v.__name__]=v;exec(compile(vraw,str(V6),'exec'),v.__dict__)
os.environ.clear();os.environ.update(expected);observer=v.backend()
child='''import ast,hashlib,json,os,pathlib,resource,signal,sys
resource.setrlimit(resource.RLIMIT_CPU,(2,3));signal.alarm(5)
p=pathlib.Path('/tmp/tlab-real015-existing-v6-driver-v4.py');raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()=='c00775f4ac0127b565c73b211d1783cde46fd4c357841c788050d2eac0d93428'
nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in {'need','environment','validate_child_environment'}];assert len(nodes)==3
ns={'os':os,'sys':sys,'OUT':pathlib.Path('/tmp/tlab-real015-observer-environment-recovery-20261015')};exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pinned-child-env-functions>','exec'),ns)
actual=dict(os.environ);expected=ns['environment']();validated=ns['validate_child_environment'](actual)
print(json.dumps({'v4_guard':validated,'old_strict_equality':actual==expected,'unknown_keys':sorted(set(actual)-set(expected)),'missing_keys':sorted(set(expected)-set(actual)),'changed_curated_keys':[k for k in expected if k in actual and actual[k]!=expected[k]],'unknown_values_omitted':True},sort_keys=True))
'''
r=subprocess.run([str(P/'.venv/bin/python'),'-B','-c',child],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=5,cwd=P,check=True);actual=json.loads(r.stdout)
assert actual['v4_guard'] is True and set(actual['unknown_keys'])<= {'__CF_USER_TEXT_ENCODING'} and actual['missing_keys']==[] and actual['changed_curated_keys']==[]
assert hashlib.sha256(DRIVER.read_bytes()).hexdigest()==g['driver_sha256']
body=dict(status='VERIFIED_PENDING_EXTERNAL_ACCEPTANCE',driver_sha256=g['driver_sha256'],grant_sha256=sys.argv[1],child_result=actual,child_exit_code=r.returncode,backend_constructors=1,child_processes=1,supervise=0,owner=0,model_load=0,predict=0,fit=0,DB=0,Y=0,prospective_recovery_OUT_still_absent=not (T/'tlab-real015-observer-environment-recovery-20261015').exists(),wall_seconds=time.monotonic()-started)
with (OUT/'result.json').open('x') as f:json.dump(body,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
signal.alarm(0)
