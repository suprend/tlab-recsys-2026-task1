# Independent synthetic verification harness archive

Historical source, with only machine paths made portable. Extract the base faults script and dependent scripts to the system temporary directory; run from the project root. These use synthetic fixtures only. Evidence belongs to the exact version in the associated [initial review](tlab018-independent-review.md) or [targeted acceptance](tlab018-independent-rereview.md); the initial lineage harness deliberately records four false passes. Archiving does not claim a new execution, acceptance-writing or real-source run.

```python
from pathlib import Path
exec((Path(__import__('tempfile').gettempdir())/'tlab018-independent-faults.py').read_text().split('start=time.monotonic();cpu=time.process_time();results=[]')[0])
start=time.monotonic();cpu=time.process_time();results=[]
with patch('duckdb.connect',side_effect=limited):
 f=Tiny()
 try:
  before={str(p.relative_to(f.root)):digest(p) for p in f.root.rglob('*') if p.is_file()}
  args=['--project-root',str(f.root),'--expectations',str(f.exp.relative_to(f.root))]
  stdout=io.StringIO()
  with contextlib.redirect_stdout(stdout):code=v.main(args)
  after={str(p.relative_to(f.root)):digest(p) for p in f.root.rglob('*') if p.is_file()}
  results.append(dict(case='default_readonly_CLI',exit=code,status=json.loads(stdout.getvalue())['status'],file_bytes_and_membership_unchanged=before==after))
  for name,path in [('traversal','../independent018.json'),('symlink','escape.json')]:
   if name=='symlink':(f.root/path).symlink_to(ROOT/'pyproject.toml')
   try:v.verify(f.root,path);out='unexpected_verified'
   except v.VerificationError as e:out=e.evidence['status']
   results.append(dict(case=name,status=out))
  readonly=[False];orig=v._qyc
  def source_write_probe(con,*a,**k):
   try:con.execute('DELETE FROM source.events')
   except duckdb.Error as e:readonly[0]='read-only' in str(e).lower() or 'read only' in str(e).lower()
   else:raise ValueError('independent.source_writable')
   return orig(con,*a,**k)
  with patch.object(v,'_qyc',side_effect=source_write_probe):out=f.result()
  results.append(dict(case='source_attachment_rejects_write',status=out['status'],readonly_engine_error=readonly[0]))
 finally:f.close()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,cpu_seconds=time.process_time()-cpu,peak_rss_bytes=v._rss()),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab018-independent-safety-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
