# Independent synthetic model-data/ablation audit archive

Historical exact-version audit, with only machine paths made portable. Extract dependent archived helpers into the system temporary directory before use. Initial model-data overflow assertion mismatch and initial terminal-decision faults remain evidence for their original versions. Archiving claims no new execution or actual fitting.

```python
from pathlib import Path
exec((Path(__import__('tempfile').gettempdir())/'tlab-model-data-independent-faults-v2.py').read_text().split("run('direct_expected_rows_fullY_chunks_UTF8_base_equivalence',healthy)")[0])
results=[]
def chunk32():
 with Fixture() as f:
  t=Transport()
  with patch.object(d.duckdb,'connect',return_value=t):data=f.load(chunk_vectors=32)
  assert t.final_execs==1 and [v for k,v in t.trace if k=='chunk']==[32,32]
  assert data.preparation['chunks']==1 and data.preparation['max_chunk_rows']==2420
  return dict(chunk_vectors=32,execute_count=1,fetch_calls=2,max_allowed=65536)
run('connection_execute_once_fetch_chunk32',chunk32)
def int64_edges():
 with Fixture() as f:
  f.con.execute('DELETE FROM f WHERE user_view_7d>1');f.con.execute('UPDATE f SET product_id=CASE WHEN user_view_7d IS NULL THEN 9223372036854775807 ELSE -9223372036854775808 END');f.save('f')
  f.con.execute('DELETE FROM addon');f.con.execute("INSERT INTO addon SELECT query_id,product_id,'value:77','state:missing','value:бренд',"+','.join(f.expr(n) for n in m.NUMERIC)+' FROM f');f.save('addon')
  data=f.load();assert data.items.tolist()==[-9223372036854775808,9223372036854775807]*11
  assert data.items.dtype==np.int64
  return dict(rows=len(data.items),minimum=int(data.items.min()),maximum=int(data.items.max()))
run('nonnullable_BIGINT_min_max_exact',int64_edges)
def nominal_selection():
 with Fixture() as f:
  f.collection['phase']['role']='selection';f.con.execute("UPDATE addon SET brand='value:selection-only' ");f.save('addon')
  data=f.load();assert set(data.categorical[:,2])=={b'value:selection-only'}
  return dict(accepted=True,encoder_fit_count=0)
run('selection_unseen_no_encoder_fit',nominal_selection)
def limited_schema_boundary():
 with Fixture() as f:
  f.con.execute('ALTER TABLE f ADD future_unreviewed DOUBLE DEFAULT 9.0');f.save('f');f.collection['feature_columns'].append('future_unreviewed')
  data=f.load();assert 'future_unreviewed' in data.feature_names
  return dict(observation='loader accepts safe extra numeric name from supplied collection; external accepted005 registry/column binding is essential, not standalone grammar acceptance')
run('external_schema_trust_boundary_observation',limited_schema_boundary)
assert before==hashes()
out=dict(scope='supplement synthetic-only; no Pool/fit/source',before=before,after=hashes(),cases=results,wall_seconds=time.monotonic()-T,cpu_seconds=time.process_time()-CPU,maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
(Path(__import__('tempfile').gettempdir())/'tlab-model-data-independent-supplement-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
if any(r['status']!='PASS' for r in results):sys.exit(1)

```
