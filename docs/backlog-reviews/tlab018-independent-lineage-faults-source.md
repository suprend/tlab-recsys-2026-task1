# Independent synthetic verification harness archive

Historical source, with only machine paths made portable. Extract the base faults script and dependent scripts to the system temporary directory; run from the project root. These use synthetic fixtures only. Evidence belongs to the exact version in the associated [initial review](tlab018-independent-review.md) or [targeted acceptance](tlab018-independent-rereview.md); the initial lineage harness deliberately records four false passes. Archiving does not claim a new execution, acceptance-writing or real-source run.

```python
from pathlib import Path
exec((Path(__import__('tempfile').gettempdir())/'tlab018-independent-faults.py').read_text().split('start=time.monotonic();cpu=time.process_time();results=[]')[0])
start=time.monotonic();cpu=time.process_time();results=[]
with patch('duckdb.connect',side_effect=limited):
 f=Tiny()
 try:
  e=f.state['shards'][0];a_path=f.root/e['acceptance']['path'];a=read(a_path)
  am=read(f.root/e['anchor']['directory']/'run.json');cm=read(f.root/e['candidate']['directory']/'run.json')
  omitted=[am['artifact_refs']['queries'],cm['artifact_refs']['candidates']]
  for n in omitted:del a['fingerprints'][n]
  write(a_path,a)
  fm_path=f.root/e['features']['directory']/'run.json';fm=read(fm_path)
  for n in omitted:del fm['identity']['input_hashes'][n]
  write(fm_path,fm);f.reseal();out=f.result()
  results.append(dict(case='approval_and_feature_inputs_omit_actual_Q_C',omitted_labels=['queries','candidates'],status=out['status'],gate=out.get('failure_gate'),completed=out['completed']))
 finally:f.close()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,cpu_seconds=time.process_time()-cpu,peak_rss_bytes=v._rss()),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab018-independent-lineage-fault-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
