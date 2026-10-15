import argparse,ast,hashlib,json,math,os,pathlib,resource,signal,subprocess,sys,time,types
T=pathlib.Path('/tmp');P=pathlib.Path('/Users/mdpospelov/tlab-recsys-2026');OUT=T/'tlab-real015-environment-diagnostic-once-v1'
V6=T/'tlab-heldout-harness-processes.py';DRIVER=T/'tlab-real015-existing-v6-driver-v3.py'
started=time.monotonic();signal.alarm(8);resource.setrlimit(resource.RLIMIT_CPU,(4,5))
assert not OUT.exists();OUT.mkdir()
raw=DRIVER.read_bytes();assert hashlib.sha256(raw).hexdigest()=='7ba7ffec6654515715b1d30be88eb54819ac31d0d1e9cf94a4388e43dffde7fa'
fn=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='environment');ns={'OUT':T/'tlab-real015-observer-original-20261015'};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<exact-environment>','exec'),ns);expected=ns['environment']()
vraw=V6.read_bytes();assert hashlib.sha256(vraw).hexdigest()=='449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
v=types.ModuleType('accepted_environment_diagnostic_v6');v.__file__=str(V6);sys.modules[v.__name__]=v;exec(compile(vraw,str(V6),'exec'),v.__dict__)
os.environ.clear();os.environ.update(expected)
before=dict(os.environ);observer=v.backend();after=dict(os.environ)
child="import argparse,hashlib,json,math,os,pathlib,resource,signal,subprocess,sys,time,types;resource.setrlimit(resource.RLIMIT_CPU,(2,3));signal.alarm(5);print(json.dumps(dict(os.environ),sort_keys=True))"
r=subprocess.run([str(P/'.venv/bin/python'),'-B','-c',child],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=5,cwd=P,check=True)
actual=json.loads(r.stdout);unknown=sorted(set(actual)-set(expected));missing=sorted(set(expected)-set(actual));changed={k:{'expected':expected[k],'actual':actual[k]} for k in expected if k in actual and actual[k]!=expected[k]}
body={'status':'DIAGNOSTIC_COMPLETE_NOT_OWNER_ACCEPTANCE','ranked_hypotheses_before_probe':['native observer initialization injects runtime key into C environment inherited by Popen','CPython startup changes locale/launcher key','script-import or directory mismatch'],'one_backend_constructor':True,'supervise_calls':0,'child_processes':1,'child_exit_code':r.returncode,'parent_mapping_changed':before!=after,'unknown_child_keys':unknown,'missing_child_keys':missing,'changed_curated_values':changed,'exact_equality':actual==expected,'unknown_values_omitted':True,'owner_source_model_DB_Y_fit_predict':0,'no_original_namespace_writes':True,'wall_seconds':time.monotonic()-started}
with (OUT/'result.json').open('x') as f:json.dump(body,f,sort_keys=True,indent=2);f.write('\n')
signal.alarm(0)
