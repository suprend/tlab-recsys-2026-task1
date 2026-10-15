"""ONE Root-authorized stdlib AST witness; metadata dictionaries, no arrays/ML/Y."""
import time
START=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(2,2))
import signal
signal.alarm(4)
import ast
from dataclasses import asdict,dataclass
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace

FREEZE=Path('/tmp/tlab-public-frozen-comparison-review-a-input-freeze-v1.json')
raw=FREEZE.read_bytes();assert hashlib.sha256(raw).hexdigest()=='f603be6cb4597cd52d31635a3253bcea1bf79f2363cf2285fecdd1c987553e19'
pins=json.loads(raw)['files']
def freshness():
    for path,row in pins.items():
        actual=Path(path).read_bytes();copy=Path(row['snapshot_path']).read_bytes()
        assert actual==copy and len(actual)==row['bytes'] and hashlib.sha256(actual).hexdigest()==row['sha256'],path
freshness()
source=Path(pins['/tmp/tlab-reproduce-frozen-comparison-v1.py']['snapshot_path']).read_bytes()
assert hashlib.sha256(source).hexdigest()=='5409bd4393bcaef2b455bef580e1f6ca9edb8b5e146e7fde617676c975a2c0b7'
tree=ast.parse(source)
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'need','compare_two'}]
assert {n.name for n in nodes}=={'need','compare_two'}
recipe=json.loads(Path(pins['/tmp/tlab-frozen-bw-oct2019-v1.json']['snapshot_path']).read_bytes())
base_names=recipe['feature_names']['B'];extra_names=recipe['extra_feature_names']
assert len(base_names)==41 and recipe['feature_names']['W']==base_names+extra_names
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
# Explicit metadata semantics, not numeric/model arrays or actual source rows.
# W has a changed MANUAL field in its first41, in addition to legitimate extras.
B_semantics={name:0 for name in base_names};B_semantics['user_view_7d']=1
W_semantics={**B_semantics,**{name:7 for name in extra_names}};W_semantics['user_view_7d']=99
W_prefix={name:W_semantics[name] for name in base_names}
assert set(B_semantics)==set(W_prefix) and {n for n in base_names if B_semantics[n]!=W_prefix[n]}=={'user_view_7d'}
assert digest(B_semantics)!=digest(W_prefix)
common=dict(queries_sha256='a'*64,group=dict(shape=[1],dtype='int32',sha256='b'*64),
            items=dict(shape=[1],dtype='int64',sha256='c'*64),y=dict(shape=[1],dtype='int8',sha256='d'*64))
weights=dict(shape=[1],dtype='float64',sha256='e'*64)
def summary(arm,semantics):
    identity={**common,'feature_names':recipe['feature_names'][arm],
              'x':dict(shape=[1,len(semantics)],dtype='float32',sha256=digest(semantics))}
    return dict(train={**identity,'weights':weights},selection=dict(identity))
summaries={'B':summary('B',B_semantics),'W':summary('W',W_semantics)}
budget=SimpleNamespace(fit_attempts=0,check=lambda:None);calls=[]
def fake_fit(arm,*args,**kwargs):
    budget.fit_attempts+=1;calls.append(arm);return object(),summaries[arm]
@dataclass
class MockDifference:
    estimate:object=None
bootstrap_calls=[]
def fake_bootstrap(*args,**kwargs):bootstrap_calls.append(kwargs);return MockDifference()
scripts=ModuleType('scripts');scripts.__path__=[]
metrics=ModuleType('scripts.ranking_metrics');metrics.paired_user_bootstrap=fake_bootstrap
sys.modules['scripts']=scripts;sys.modules['scripts.ranking_metrics']=metrics
namespace=dict(fit_arm=fake_fit,asdict=asdict)
exec(compile(ast.Module(body=nodes,type_ignores=[]),'frozen_compare_two_AST','exec',dont_inherit=True),namespace)
answer=namespace['compare_two']([],[],recipe,None,budget,backend=None)
assert calls==['B','W'] and budget.fit_attempts==2 and len(bootstrap_calls)==1
for phase in ('train','selection'):
    assert all(summaries['B'][phase][k]==summaries['W'][phase][k] for k in ('queries_sha256','group','items','y'))
assert summaries['B']['train']['weights']==summaries['W']['train']['weights']
assert answer['B']==summaries['B'] and answer['W']==summaries['W'] and answer['post_selection_reproduction'] is True
freshness()
r=resource.getrusage(resource.RUSAGE_SELF);c=resource.getrusage(resource.RUSAGE_CHILDREN)
cpu=r.ru_utime+r.ru_stime;wall=time.monotonic()-START;rss=r.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
assert cpu<=2 and wall<=5 and rss<=128*2**20 and c.ru_utime+c.ru_stime==0 and c.ru_maxrss==0
result=dict(scope='stdlib_AST_missing_B41_prefix_binding_witness_only',status='SUPPORTED_P2_GUARD_FALSE_NEGATIVE',
    compare_two_returned_without_rejection=True,all_existing_checked_Q_keys_Y_weight_identities_equal=True,
    manual_prefix_semantic_delta={'feature':'user_view_7d','B':1,'W_prefix':99},
    B41_prefix_semantics_sha256=digest(B_semantics),W_B41_prefix_semantics_sha256=digest(W_prefix),
    B41_names_identical=True,W_has_legitimate_three_additions=True,native_or_historical_equivalence_claimed=False,
    AST_extracted_functions=['need','compare_two'],mock_fit_arm_calls=calls,mock_bootstrap_calls=len(bootstrap_calls),
    input_count=len(pins),all_frozen_originals_and_snapshots_fresh=True,CPU_seconds=cpu,wall_seconds=wall,RSS_bytes=rss,
    bounds=dict(CPU_seconds=2,wall_seconds=5,RSS_bytes=128*2**20),
    actual_DuckDB_numpy_native_arrays_ML_data_Y_children_fits_predict_install_project_work=0)
Path('/tmp/tlab-public-frozen-comparison-review-a-prefix-binding-probe-v1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,sort_keys=True))
