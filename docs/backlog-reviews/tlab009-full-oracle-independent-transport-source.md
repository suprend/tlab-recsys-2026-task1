# Independent targeted audit source archive

Historical exact-version audit; only machine paths are portable. Dependent archived scripts must be extracted to the system temporary directory before use. Original false accepts remain evidence for their original versions; later fixes have separate reviews. No source/model execution or new acceptance is claimed by archiving.

```python
import ast,types,hashlib,time,resource,json,math
from pathlib import Path
from datetime import datetime
import duckdb,pandas as pd
path=(Path(__import__('tempfile').gettempdir())/'tlab009-verify-full-source.py');source=path.read_text();tree=ast.parse(source)
allowed={'need','same','equal_relations','compare_broadcast','install_expected'}
module=ast.Module(body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in allowed],type_ignores=[])
ns=dict(pd=pd,math=math,datetime=datetime);exec(compile(module,str(path),'exec'),ns)
start=time.monotonic();cpu=time.process_time();con=duckdb.connect(':memory:');con.execute('SET threads=2');results=[]
try:
 wanted=2**60+1
 ns['install_expected'](con,'expected',[[1,wanted],[2,None]],[('product_id','BIGINT'),('category_id','BIGINT')])
 actual_expected=con.execute('SELECT * FROM expected ORDER BY product_id').fetchall()
 results.append(dict(case='nullable_large_BIGINT_preservation',wanted=wanted,installed=actual_expected,exact=actual_expected[0][1]==wanted))
 con.execute('CREATE TEMP TABLE correct(query_id VARCHAR,product_id BIGINT,category_id BIGINT)')
 con.executemany('INSERT INTO correct VALUES (?,?,?)',[('q',1,wanted),('q',2,None)])
 try:ns['compare_broadcast'](con,'correct','expected',[('category_id','BIGINT')],lambda:None);out='accepted';gate=None
 except ValueError as e:out='rejected';gate=str(e)
 results.append(dict(case='correct_source_value',status=out,gate=gate))
 con.execute('UPDATE correct SET category_id=? WHERE product_id=1',[2**60])
 try:ns['compare_broadcast'](con,'correct','expected',[('category_id','BIGINT')],lambda:None);out='accepted';gate=None
 except ValueError as e:out='rejected';gate=str(e)
 results.append(dict(case='rounded_wrong_source_value',status=out,gate=gate,wanted=wanted,wrong=2**60))
 ns['install_expected'](con,'numeric',[[1,1.0,None],[2,None,0.0]],[('product_id','BIGINT'),('value','DOUBLE'),('optional','DOUBLE')])
 con.execute("CREATE TEMP TABLE physical AS SELECT 'q' query_id,* FROM numeric UNION ALL SELECT 'r',* FROM numeric")
 checks=[('healthy_broadcast',None),('one_bad_duplicate_copy',"UPDATE physical SET value=9 WHERE query_id='r' AND product_id=1"),('wrong_NULL',"UPDATE physical SET value=1.0 WHERE query_id='r' AND product_id=1; UPDATE physical SET optional=0 WHERE query_id='r' AND product_id=1")]
 for name,statement in checks:
  if statement:con.execute(statement)
  try:ns['compare_broadcast'](con,'physical','numeric',[('value','DOUBLE'),('optional','DOUBLE')],lambda:None);out='accepted';gate=None
  except ValueError as e:out='rejected';gate=str(e)
  results.append(dict(case=name,status=out,gate=gate))
finally:con.close()
result=dict(script_sha256=hashlib.sha256(source.encode()).hexdigest(),cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,process_cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),fits=0,real_source_reads=0,root_WIP_imported=False,method='AST-only unchanged helper definitions; standalone in-memory DuckDB')
(Path(__import__('tempfile').gettempdir())/'tlab009-full-oracle-independent-transport-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
