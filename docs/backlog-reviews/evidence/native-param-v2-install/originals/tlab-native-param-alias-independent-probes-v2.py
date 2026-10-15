"""One narrow saved-only V2 context repair replay; stdlib only."""
import ast
import hashlib
import io
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time
import types
import unittest

START=time.monotonic()
resource.setrlimit(resource.RLIMIT_CPU,(15,15));signal.alarm(20)
BASE=Path('/tmp/tlab-018-native-param-repair-independent-inputs-v2')
V1=Path('/tmp/tlab-018-native-param-repair-independent-inputs-v1')
ATTEMPTS=dict(native_import=0,children=0,network=0,model_or_data_read=0,project_write=0)


def audit(event,args):
    if event=='import' and args and str(args[0]).split('.')[0] in {'catboost','duckdb','sqlite3','numpy'}:
        ATTEMPTS['native_import']+=1;raise AssertionError('Only stdlib allowed')
    if event in {'subprocess.Popen','os.system','os.posix_spawn','os.fork'}:
        ATTEMPTS['children']+=1;raise AssertionError('No children')
    if event.startswith('socket.'):
        ATTEMPTS['network']+=1;raise AssertionError('No network')
    if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
        name=os.fsdecode(args[0])
        if name.endswith('.cbm') or '/tlab-recsys-2026/artifacts/' in name or '/tlab-recsys-2026/data/' in name:
            ATTEMPTS['model_or_data_read']+=1;raise AssertionError('No models/data')
        if '/tlab-recsys-2026/' in name and len(args)>1 and isinstance(args[1],str) and any(n in args[1] for n in 'wax+'):
            ATTEMPTS['project_write']+=1;raise AssertionError('No project writes')


sys.addaudithook(audit)
expected={
 'tlab-heldout-predictions-bayesian-alias-proposal-v2.py':'437a054be9b7d47072c240b73b3b713ddef943cb3b04e96d88c8279b41f56af4',
 'tlab-heldout-prediction-audit-bayesian-alias-proposal-v2.py':'3b378274041623ba37dcb5a53a115458f02af4f2665f10821875aaf099d3cf75',
 'test_tlab_native_parameter_alias_proposal_v2.py':'3f743b878ca1a780743ed71182da4258278b8582316c57c0e1d7e4723f67c6ab'}
for name,sha in expected.items():assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==sha
PROJECT=BASE/'project'
for relative,leaf in [('scripts/heldout_contract.py','heldout_contract.py'),('scripts/heldout_predictions.py','heldout_predictions.py'),('tests/oracles/heldout_prediction_audit.py','heldout_prediction_audit.py')]:
    out=PROJECT/relative;out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('xb') as f:f.write((V1/leaf).read_bytes())
tests=BASE/'test_tlab_native_parameter_alias_proposal_v2.py';tree=ast.parse(tests.read_bytes(),filename=str(tests))
paths={'/Users/mdpospelov/tlab-recsys-2026':str(PROJECT),'/tmp/tlab-018-native-param-diagnostic-20261015-once/capture.json':str(V1/'capture.json')}
for version,folder in [('v1',V1),('v2',BASE)]:
    for stem in ['tlab-heldout-predictions-bayesian-alias-proposal','tlab-heldout-prediction-audit-bayesian-alias-proposal']:
        paths['/tmp/'+stem+'-'+version+'.py']=str(folder/(stem+'-'+version+'.py'))
changes=0
for n in ast.walk(tree):
    if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value in paths:n.value=paths[n.value];changes+=1
skipped=[];body=[]
for n in tree.body:
    if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and (n.value.func.value.id,n.value.func.attr) in {('resource','setrlimit'),('signal','alarm')}:
        skipped.append(ast.unparse(n))
    else:body.append(n)
tree.body=body;assert changes==7 and len(skipped)==2
m=types.ModuleType('frozen_alias_v2_tests');m.__file__=str(tests);exec(compile(tree,str(tests),'exec'),m.__dict__)
log=io.StringIO();suite=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(m.AliasTests));assert suite.wasSuccessful()
v1p=m.load_pure(V1/'tlab-heldout-predictions-bayesian-alias-proposal-v1.py','production','a36772a2320634c82f1542658715175ff8956a70e36f803b578a3a2dbf01f68c')
v1o=m.load_pure(V1/'tlab-heldout-prediction-audit-bayesian-alias-proposal-v1.py','oracle','f78d7599ce182299a2275c83d4196b1baea6ec29e7a764a5a310502d02a23ad3')
versions=[('original',m.OLD_P,m.OLD_O),('V1',v1p,v1o),('V2',m.NEW_P,m.NEW_O)]


def accepts(module,e,a,path):
    try:m.leaf(module,e,a,path)
    except ValueError:return False
    return True


E,A=m.E,m.A;observations={}
cases=[('direct_scalar',E,A,('bayesian_matrix_reg',),[False,True,True]),
 ('root_scalar_field',{'bayesian_matrix_reg':E},{'bayesian_matrix_reg':A},(),[False,True,True]),
 ('one_list',[E],[A],('bayesian_matrix_reg',),[False,True,False]),
 ('two_lists',[[E]],[[A]],('bayesian_matrix_reg',),[False,True,False]),
 ('root_list_field',{'bayesian_matrix_reg':[E]},{'bayesian_matrix_reg':[A]},(),[False,True,False]),
 ('list_containing_root_key',[{'bayesian_matrix_reg':E}],[{'bayesian_matrix_reg':A}],(),[False,True,False]),
 ('nested_dict_key',{'outer':{'bayesian_matrix_reg':E}},{'outer':{'bayesian_matrix_reg':A}},(),[False,False,False]),
 ('strict_list_absolute_tolerance',[E],[E+5e-13],('bayesian_matrix_reg',),[True,True,True])]
for label,e,a,path,want in cases:
    seen={name:[accepts(p,e,a,path),accepts(o,e,a,path)] for name,p,o in versions}
    assert list(seen.values())==[[v,v] for v in want],(label,seen)
    observations[label]=seen
LE=m.SPEC['effective_parameters']['learning_rate'];LA=m.PARAMS['learning_rate']
for label,e,a,want in [('learning_list',[LE],[LA],True),('learning_two_lists',[[LE]],[[LA]],True),('learning_list_corruption',[LE],[LE+1e-8],False)]:
    seen={name:[accepts(p,e,a,('learning_rate',)),accepts(o,e,a,('learning_rate',))] for name,p,o in versions}
    assert all(value==[want,want] for value in seen.values());observations[label]=seen


def functions(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef)}
oldp=functions(V1/'tlab-heldout-predictions-bayesian-alias-proposal-v1.py');newp=functions(BASE/'tlab-heldout-predictions-bayesian-alias-proposal-v2.py')
oldo=functions(V1/'tlab-heldout-prediction-audit-bayesian-alias-proposal-v1.py');newo=functions(BASE/'tlab-heldout-prediction-audit-bayesian-alias-proposal-v2.py')
assert set(oldp)==set(newp) and [n for n in oldp if oldp[n]!=newp[n]]==['_same']
assert set(oldo)==set(newo) and [n for n in oldo if oldo[n]!=newo[n]]==['native_equal']
own=resource.getrusage(resource.RUSAGE_SELF);rss=own.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
assert own.ru_utime+own.ru_stime<15 and time.monotonic()-START<20 and rss<=512*2**20
receipt=dict(scope='one focused captured-only Bayesian V2 context rereview',author_suite=dict(tests=suite.testsRun,passed=suite.wasSuccessful(),failures=len(suite.failures),errors=len(suite.errors)),observations=observations,source_SHA=expected['tlab-heldout-predictions-bayesian-alias-proposal-v2.py'],oracle_SHA=expected['tlab-heldout-prediction-audit-bayesian-alias-proposal-v2.py'],transport=dict(frozen_path_constants=changes,author_resource_statements_skipped=skipped,Root_CPU_seconds=15,Root_wall_seconds=20,implementation_AST_changes=0),other_function_ASTs_unchanged=True,guard_attempts=ATTEMPTS,self_CPU_seconds=own.ru_utime+own.ru_stime,internal_body_wall_seconds=time.monotonic()-START,peak_RSS_bytes=rss,native_imports_load_predict_fit_SQL_sourceDB_Y_children_project_writes=0,runtime_grant=False)
with Path('/tmp/tlab-native-param-alias-independent-probe-results-v2.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
with Path('/tmp/tlab-native-param-alias-independent-author-suite-v2.log').open('x') as f:f.write(log.getvalue())
print(json.dumps(receipt,sort_keys=True))
