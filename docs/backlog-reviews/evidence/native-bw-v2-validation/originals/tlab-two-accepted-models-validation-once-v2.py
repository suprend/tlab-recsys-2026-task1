"""Inert until a separately issued Root grant pins this script and installed V2 bytes."""
import argparse, ast, gc, hashlib, json, math, os, pathlib, re, resource, signal, struct, sys, time, types
ROOT = pathlib.Path('/Users/mdpospelov/tlab-recsys-2026')
GRANT = pathlib.Path('/tmp/tlab-two-accepted-models-validation-root-grant-v1.json')
OUT = pathlib.Path('/tmp/tlab-two-accepted-models-validation-once-v1')
CACHE = pathlib.Path('/tmp/tlab-two-accepted-models-validation-cache-v1')
META = {'/tmp/tlab-development-whole018-request-candidate-v1.json':'0d7d99a9a8fb2a1f9bfbf9375e57935f49f52ee48685ae92dbb7f66f5dc41ce9','/tmp/tlab-root-development-day-reference-handoff-prepared.json':'fd7304383e9c025d205a0b7f9060187f8062daa9baa2f9b0f86ea6a18323e05b'}
# Candidate byte pins, NOT approval. Root grant must separately repeat installed pins.
SOURCES = {'scripts/heldout_predictions.py':'437a054be9b7d47072c240b73b3b713ddef943cb3b04e96d88c8279b41f56af4','tests/oracles/heldout_prediction_audit.py':'3b378274041623ba37dcb5a53a115458f02af4f2665f10821875aaf099d3cf75','scripts/heldout_contract.py':'fc50d11d3b6dfdc2906522472f5b66138424bc4586e7833b43c6fc4e6c4f1abc'}
MODELS = {'B':('artifacts/strong-baseline/9c6969c88857620b24d27da288c6aeb2544187d2cb64267db5e81f8c3599b080/workers/arm-3/736d185cee18266642ad0dbc49199d9b667428c31f99454f78d82f85950d0364/prefix300.cbm','a60a82894ed9385a7b4f38784e7ea34ed9476966557387924406f803343f2b2e'),'W':('artifacts/feature-program-invocations/3a0bf8f0834949c7ab2119a1d2acaef7/workers/R2/45ea167afa64d1051cb65eabdeee8f178abb87ddaa717ed500d10885be61ae89/prefix.cbm','35eb3837db9dcabe0aa2c15a2d999e0c44feb98d39d6ae1da10a19b37c6928ec')}
PROD = ('_bayesian_serialized_alias','_same','verify_model')
ORACLE = ('need','keys','identifier','ref','native_equal','model_spec','native_model')
CONTRACT = ('need','keys','integer','ref','model')
def require(ok, message):
    if not ok: raise ValueError(message)
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def snapshot(path, expected, limit=1024*1024):
    with pathlib.Path(path).open('rb') as f: raw=f.read(limit+1)
    require(len(raw)<=limit and hashlib.sha256(raw).hexdigest()==expected,'bounded snapshot SHA differs')
    return raw

def finalize(report, primary, actions, persist):
    report['secondary_failures']=[]; report['external_acceptance_required']=True
    if primary is not None: report['primary_error']={'stage':'verification','type':type(primary).__name__}
    for name, action in actions:
        try: action()
        except BaseException as error:
            if primary is None: primary=error; report['primary_error']={'stage':name,'type':type(error).__name__}
            else: report['secondary_failures'].append({'stage':name,'type':type(error).__name__})
    report['status']='FAILED' if primary is not None else 'VERIFIED_PENDING_EXTERNAL_ACCEPTANCE'
    try: persist()
    except BaseException as error:
        report['status']='FAILED'
        if primary is None: primary=error; report['primary_error']={'stage':'result_write','type':type(error).__name__}
        else: report['secondary_failures'].append({'stage':'result_write','type':type(error).__name__})
    if primary is not None: raise primary.with_traceback(primary.__traceback__)

def project_file(name):
    p=ROOT/name; require(p.resolve().is_relative_to(ROOT.resolve()),'path outside fixed project')
    require(all(not x.is_symlink() for x in [p,*p.parents]),'symlink forbidden'); return p

def select_functions(raw,names,extra=None,constants=()):
    tree=ast.parse(raw); body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    require(len(body)==len(names) and {n.name for n in body}==set(names),'function closure differs')
    require(all(not n.decorator_list for n in body),'decorated closure forbidden')
    ns={'math':math,'struct':struct,'re':re}; ns.update(extra or {})
    for n in tree.body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in constants: ns[n.targets[0].id]=ast.literal_eval(n.value)
    exec(compile(ast.Module(body=body,type_ignores=[]),'<pinned-pure-functions>','exec'),ns)
    return ns

def main():
    started=time.monotonic(); signal.signal(signal.SIGALRM,signal.SIG_DFL); signal.alarm(25)
    resource.setrlimit(resource.RLIMIT_CPU,(14,15))
    def check():
        require(time.monotonic()-started<25,'wall budget exhausted')
        r=resource.getrusage(resource.RUSAGE_SELF); peak=r.ru_maxrss if sys.platform=='darwin' else r.ru_maxrss*1024
        require(peak<=512*2**20,'SELF RSS512MiB exceeded')
    parser=argparse.ArgumentParser(); parser.add_argument('--grant-sha256',required=True); parser.add_argument('--production-source-sha256',required=True); parser.add_argument('--oracle-source-sha256',required=True); args=parser.parse_args()
    require(args.production_source_sha256==SOURCES['scripts/heldout_predictions.py'] and args.oracle_source_sha256==SOURCES['tests/oracles/heldout_prediction_audit.py'],'separate Root-approved installed source pins required')
    require(re.fullmatch('[a-f0-9]{64}',args.grant_sha256) is not None,'external grant SHA required')
    grant=json.loads(snapshot(GRANT,args.grant_sha256))
    require(set(grant)=={'version','scope','approved','script_sha256','installed_sources','metadata','model_refs','limits','output_directory','cache_directory'},'exact grant schema')
    require(grant['version']==1 and type(grant['version']) is int and grant['scope']=='two_accepted_models_verify_model_once' and grant['approved'] is True,'separate Root approval required')
    require(grant['script_sha256']==sha(__file__) and grant['installed_sources']==SOURCES and grant['metadata']==META and grant['model_refs']=={k:list(v) for k,v in MODELS.items()},'Root-issued exact code/metadata/models required')
    require(all(type(v) is int for v in grant['limits'].values()) and grant['limits']=={'cpu_seconds':15,'wall_seconds':30,'rss_bytes':512*2**20,'model_loads':2,'get_all_params_per_model':2,'fit':0,'predict':0,'DB':0,'Y':0,'subprocess':0},'fixed scope limits')
    require(grant['output_directory']==str(OUT) and grant['cache_directory']==str(CACHE),'fixed once destinations')
    require(sys.flags.isolated and sys.dont_write_bytecode and sys.pycache_prefix==str(CACHE),'isolated -I -B and fresh -X cache prefix required')
    require(not OUT.exists() and not OUT.is_symlink() and not CACHE.exists() and not CACHE.is_symlink(),'once destinations already used')
    OUT.mkdir(); CACHE.mkdir(); (OUT/'started.json').write_text(json.dumps({'scope':grant['scope'],'grant_sha256':args.grant_sha256,'fit':0,'predict':0})+'\n')
    report={'status':'STARTED','model_load_attempts':0,'rows':[],'grant_sha256':args.grant_sha256,'fit':0,'predict':0,'DB':0,'Y':0,'subprocess':0}; originals={}; source_before={}; primary=None
    try:
        check(); bodies=[]
        for p,d in META.items(): bodies.append(json.loads(snapshot(p,d)))
        specs=bodies[0]['models']; require(specs==bodies[1]['models'] and set(specs)=={'B','W'},'accepted model specs differ')
        require(tuple(sys.version_info[:3])==tuple(bodies[0]['environment']['python_version']) and sha(sys.executable)==bodies[0]['environment']['interpreter_sha256'],'pinned isolated interpreter differs')
        raw={p:snapshot(project_file(p),d) for p,d in SOURCES.items()}; source_before=dict(SOURCES)
        for role,(p,d) in MODELS.items(): require(specs[role]['model']=={'path':p,'sha256':d} and sha(project_file(p))==d,'original CBM bytes differ'); originals[p]=d
        h=select_functions(raw['scripts/heldout_contract.py'],CONTRACT)
        prod=select_functions(raw['scripts/heldout_predictions.py'],PROD,{'h':types.SimpleNamespace(**h)})
        oracle=select_functions(raw['tests/oracles/heldout_prediction_audit.py'],ORACLE,constants=('META','DERIVED'))
        require('_same' not in oracle and '_bayesian_serialized_alias' not in oracle,'oracle shares production helper')
        for p,names in [('scripts/heldout_predictions.py',PROD),('tests/oracles/heldout_prediction_audit.py',ORACLE)]:
            nodes=[n for n in ast.parse(raw[p]).body if isinstance(n,ast.FunctionDef) and n.name in names]
            attrs=[n.func.attr for node in nodes for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
            require(attrs.count('get_all_params')==1 and not set(attrs)&{'predict','fit','load_model','execute','connect'},'native call scope differs')
        import catboost
        require(catboost.__version__==bodies[0]['environment']['packages']['catboost'] and catboost.CatBoostClassifier.__module__=='catboost.core','fixed native backend required'); check()
        for role,width in [('B',41),('W',44)]:
            spec=specs[role]; require(len(spec['feature_names'])==width,'fixed width'); oracle['model_spec'](spec,width); check()
            model=catboost.CatBoostClassifier(); report['model_load_attempts']+=1; model.load_model(str(project_file(MODELS[role][0])),format='cbm'); check()
            prod['verify_model'](model,spec); oracle['native_model'](model,spec); check()
            report['rows'].append({'role':role,'width':len(model.feature_names_),'tree_count':model.tree_count_,'production':'PASS','independent_oracle':'PASS','get_all_params_calls':2})
            del model; gc.collect(); check()
        require(report['model_load_attempts']==2,'exactly two native loads'); report['status']='VERIFICATION_COMPLETE'
    except BaseException as error: primary=error
    def model_hashes():
        report['original_model_snapshots']=len(originals); report['model_hashes_unchanged']=all(sha(project_file(p))==d for p,d in originals.items())
        require(report['model_hashes_unchanged'],'original model bytes changed')
    def source_hashes():
        report['original_source_snapshots']=len(source_before); report['source_hashes_unchanged']=all(sha(project_file(p))==d for p,d in source_before.items())
        require(report['source_hashes_unchanged'],'compiled source bytes changed')
    def resources():
        report['wall_seconds']=time.monotonic()-started; r=resource.getrusage(resource.RUSAGE_SELF)
        report['cpu_seconds']=r.ru_utime+r.ru_stime; report['peak_rss_bytes']=r.ru_maxrss if sys.platform=='darwin' else r.ru_maxrss*1024
        require(report['wall_seconds']<=30 and report['cpu_seconds']<=15 and report['peak_rss_bytes']<=512*2**20,'final resource allowance exceeded')
    def persist():
        with (OUT/'result.json').open('x') as f: json.dump(report,f,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
    finalize(report,primary,[('model_rehash',model_hashes),('source_rehash',source_hashes),('resources',resources)],persist)
    signal.alarm(0)
if __name__=='__main__': main()
