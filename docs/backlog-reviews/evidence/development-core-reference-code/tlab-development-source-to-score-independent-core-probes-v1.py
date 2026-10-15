"""Finite synthetic-only CORE review. No production input/model/owner launch."""
import time
ENTRY=time.monotonic()
import resource
resource.setrlimit(resource.RLIMIT_CPU,(59,60))
import signal
signal.alarm(120)
import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
import builtins

for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='2'
manifest_path=Path('/tmp/tlab-development-source-to-score-independent-core-inputs-v1/input-freeze.json')
manifest_raw=manifest_path.read_bytes()
assert hashlib.sha256(manifest_raw).hexdigest()=='2ec0593b987e5edb829713b396766817b413b7f2f6c9bb8eb0b35a2ab100db93'
files=json.loads(manifest_raw)['files'];raws={}
def freshness():
    for name,e in files.items():
        current=Path(name).read_bytes();copy=Path(e['snapshot_path']).read_bytes()
        assert current==copy and len(current)==e['bytes'] and hashlib.sha256(current).hexdigest()==e['sha256']
        raws[name]=copy
freshness()
ORIGINAL_PROJECT=Path('/Users/mdpospelov/tlab-recsys-2026')
RUNTIME=tempfile.TemporaryDirectory(prefix='tlab018-independent-copied-code-')
COPIED_PROJECT=Path(RUNTIME.name)/'synthetic-project'
for name,raw in raws.items():
    original=Path(name)
    if original.is_relative_to(ORIGINAL_PROJECT) and ('scripts' in original.parts or 'configs' in original.parts):
        target=COPIED_PROJECT/original.relative_to(ORIGINAL_PROJECT)
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
with (COPIED_PROJECT/'scripts/__init__.py').open('xb') as stream:stream.write(b'')

violations=[]
def forbidden(label):
    def fail(*args,**kwargs):violations.append(label);raise AssertionError('Forbidden review operation: '+label)
    return fail
real_import=builtins.__import__
def safe_import(name,*args,**kwargs):
    if name.split('.')[0] in {'catboost','xgboost','torch','tensorflow'}:return forbidden('native ML import '+name)()
    value=real_import(name,*args,**kwargs)
    for module_name,module in tuple(sys.modules.items()):
        if module_name=='scripts' or module_name.startswith('scripts.'):
            filename=getattr(module,'__file__',None)
            if filename and not Path(filename).is_relative_to(COPIED_PROJECT):return forbidden('project import outside copied code '+filename)()
    return value
real_read=Path.read_bytes
def frozen_read(path):
    if str(path) in raws:return raws[str(path)]
    if path.is_relative_to(COPIED_PROJECT):return real_read(path)
    return forbidden('unfrozen Path.read_bytes '+str(path))()

import duckdb
real_connect=duckdb.connect
connections=[]
def checked_connect(database=':memory:',*args,**kwargs):
    text=str(database)
    if text!=':memory:' and not Path(text).is_relative_to(Path(tempfile.gettempdir())):
        return forbidden('non-TMP DB '+text)()
    connections.append(text)
    return real_connect(database,*args,**kwargs)

author_path='/tmp/tlab-test-reproduce-development-slice-v1.py'
tree=ast.parse(raws[author_path],author_path)
transport=[]
for node in tree.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROJECT' for t in node.targets):
        node.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(COPIED_PROJECT))],keywords=[]);transport.append('PROJECT literal -> copied frozen public modules/configs')
ast.fix_missing_locations(tree)
author=ModuleType('independent_copied_author_tiny_fixture')
author.__file__=author_path
sys.modules[author.__name__]=author
observations={}
log_path=Path('/tmp/tlab-development-source-to-score-independent-core-probes-v1.log')
result=None
with ExitStack() as guards:
    guards.enter_context(patch.object(builtins,'__import__',side_effect=safe_import))
    guards.enter_context(patch.object(Path,'read_bytes',frozen_read))
    guards.enter_context(patch.object(duckdb,'connect',side_effect=checked_connect))
    for module,name in [(subprocess,'Popen'),(os,'system'),(os,'fork'),(os,'posix_spawn'),(os,'posix_spawnp'),(os,'kill'),(os,'wait4'),(socket,'create_connection')]:
        if hasattr(module,name):guards.enter_context(patch.object(module,name,side_effect=forbidden(module.__name__+'.'+name)))
    guards.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden('network connect')))
    exec(compile(tree,author_path,'exec',dont_inherit=True),author.__dict__)
    a=author.adapter
    class IndependentTinyTests(author.TinyAdapterTests):
        def export_for(self,con,tag):
            root=author.FIXTURE/tag;root.mkdir(exist_ok=False)
            def export(name,sql):
                target=root/a.OUTPUT_NAMES[name]
                if target.exists():raise FileExistsError(str(target))
                con.execute('COPY ('+sql+') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(target)])
                return target.relative_to(author.FIXTURE).as_posix()
            return export

        def test_z_all_queries_empty_candidates_keep_exact_Q_without_predict(self):
            db=author.FIXTURE/'independent-empty-events.duckdb'
            con=duckdb.connect(str(db))
            con.execute('SET threads=2');con.execute("SET memory_limit='64MB'");con.execute("SET max_temp_directory_size='0B'")
            con.execute('''CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,category_id BIGINT,category_code VARCHAR,brand VARCHAR,price DECIMAL(12,2),user_id BIGINT,user_session VARCHAR)''')
            con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',[
                ('2019-10-21 12:00:00','view',None,None,None,None,None,77,'empty'),
                ('2019-10-21 12:00:00','view',None,None,None,None,None,78,'empty')])
            con.close();con=duckdb.connect(str(db),read_only=True)
            con.execute('SET threads=2');con.execute("SET memory_limit='64MB'");con.execute("SET max_temp_directory_size='0B'")
            calls_before=len(author.MODEL_CALLS)
            try:
                def model(ref):
                    role=next(r for r in self.models if self.models[r]['model']==ref)
                    return author.FakeModel(self.models[role])
                r=a.build_and_score(con,config=self.config,pool=self.pool,models=self.models,cores=author.CORES,load_model=model,export=self.export_for(con,'independent-empty-output'),check=author.guard,stage=author.stage)
                self.assertEqual((r['query_count'],r['candidate_count'],r['native_prediction_calls']),(2,0,0))
                self.assertEqual(len(author.MODEL_CALLS),calls_before)
                self.assertEqual(con.execute('SELECT count(*) FROM pilot_queries').fetchone()[0],2)
                for role in ['B','W']:
                    self.assertEqual(con.execute('SELECT count(*) FROM read_parquet(?)',[str(author.FIXTURE/r['outputs'][role])]).fetchone()[0],0)
                observations['all_empty_C']=dict(queries=2,candidates=0,prediction_calls=0,source_acceptance=r['source_acceptance_issued'])
            finally:con.close()

        def fault(self,kind,expected):
            class FaultModel(author.FakeModel):
                def predict(model,x,**kwargs):
                    raw=super().predict(x,**kwargs)
                    if kind=='nan':raw[0]=float('nan')
                    elif kind=='shape':raw=raw.reshape(-1,1)
                    elif kind=='matrix':x[0,0]+=1
                    elif kind=='model':model.tree_count_=299
                    return raw
            def load(ref):
                role=next(r for r in self.models if self.models[r]['model']==ref)
                return FaultModel(self.models[role])
            before=len(author.MODEL_CALLS)
            with self.assertRaisesRegex(ValueError,expected) as caught:
                a.build_and_score(self.con,config=self.config,pool=self.pool,models=self.models,cores=author.CORES,load_model=load,export=self.export_for(self.con,'independent-fault-'+kind),check=author.guard,stage=author.stage)
            self.assertEqual(len(author.MODEL_CALLS)-before,1)
            observations[kind]=dict(rejected=True,error=str(caught.exception),fake_prediction_calls=1)
        def test_z_fault_nonfinite_scores_rejected(self):self.fault('nan','finite float64')
        def test_z_fault_wrong_score_shape_rejected(self):self.fault('shape','finite float64')
        def test_z_fault_input_matrix_mutation_rejected(self):self.fault('matrix','changed input matrix')
        def test_z_fault_model_state_mutation_rejected(self):self.fault('model','tree count')

    with log_path.open('x') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IndependentTinyTests))

freshness()
usage=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
elapsed=time.monotonic()-ENTRY;peak=usage.ru_maxrss*(1024 if sys.platform.startswith('linux') else 1)
cpu=usage.ru_utime+usage.ru_stime
assert elapsed<=120 and cpu<=60 and peak<=512*2**20
assert children.ru_utime+children.ru_stime==0 and children.ru_maxrss==0
assert not violations
out=dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,author_inherited_tests=9,independent_tests=5,failures=len(result.failures),errors=len(result.errors),observations=observations,frozen_input_count=len(files),input_hashes={p:e['sha256'] for p,e in files.items()},fixture_transport=transport,copied_project=str(COPIED_PROJECT),fixture_directory=str(author.FIXTURE),fixture_cleanup_on_interpreter_exit=True,fixture_artifacts_not_retained_as_acceptance=True,invented_events_total=10,synthetic_queries_total=4,maximum_candidate_rows_per_run=1,fake_prediction_calls=len(author.MODEL_CALLS),native_ML_calls=0,fits=0,Y_relations_created=False,actual_source_DB_CBM_NPZ_archive_reads=0,project_or_consumed_root_writes=0,application_children=0,guard_violations=violations,process_cpu_seconds=cpu,elapsed_seconds=elapsed,process_peak_rss_bytes=peak,children_cpu_seconds=0,children_peak_rss=0,observations_not_full_exit_receipt=True,execution_grant=False,runtime=dict(python=sys.version,duckdb=duckdb.__version__,numpy=author.np.__version__,pandas=author.pd.__version__))
p=Path('/tmp/tlab-development-source-to-score-independent-core-probes-v1-results.json')
with p.open('x') as stream:json.dump(out,stream,sort_keys=True,indent=2);stream.write('\n')
print(json.dumps({k:out[k] for k in ['status','tests','failures','errors','invented_events_total','synthetic_queries_total','fake_prediction_calls','process_cpu_seconds','elapsed_seconds','process_peak_rss_bytes','guard_violations']}))
if not result.wasSuccessful():
    print(log_path.read_text())
    raise SystemExit(1)
