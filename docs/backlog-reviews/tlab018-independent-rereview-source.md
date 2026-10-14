# Independent synthetic verification harness archive

Historical source, with only machine paths made portable. Extract the base faults script and dependent scripts to the system temporary directory; run from the project root. These use synthetic fixtures only. Evidence belongs to the exact version in the associated [initial review](tlab018-independent-review.md) or [targeted acceptance](tlab018-independent-rereview.md); the initial lineage harness deliberately records four false passes. Archiving does not claim a new execution, acceptance-writing or real-source run.

```python
from pathlib import Path
exec((Path(__import__('tempfile').gettempdir())/'tlab018-independent-faults.py').read_text().split('start=time.monotonic();cpu=time.process_time();results=[]')[0])
BaseTiny=Tiny
class Tiny(BaseTiny):
 def reseal(self):
  # Maintain legitimately changed candidate lineage; preserve intentionally wrong report IDs.
  for e in self.state['shards']:
   cm=read(self.root/e['candidate']['directory']/'run.json');old_id=cm['run_id']
   cm['identity']['input_hashes']={n:digest(self.root/n) for n in cm['identity']['input_hashes']}
   new_id=hashlib.sha256(enc(cm['identity']).encode()).hexdigest()
   p=self.root/e['features']['directory']/'report.json';fr=read(p)
   if fr.get('candidate_run_id')==old_id:fr['candidate_run_id']=new_id;write(p,fr)
  super().reseal()

start=time.monotonic();cpu=time.process_time();results=[]
with patch('duckdb.connect',side_effect=limited):
 for case in ['baseline','joint_Q_C','query_only','query_coverage','source','code','extra','wrong_approval_value','F_only_missing_C','candidate_wrong_anchor','feature_wrong_anchor','feature_wrong_candidate']:
  f=Tiny()
  try:
   e=f.state['shards'][0];am=read(f.root/e['anchor']['directory']/'run.json');cm=read(f.root/e['candidate']['directory']/'run.json')
   ap=f.root/e['acceptance']['path'];a=read(ap);fmp=f.root/e['features']['directory']/'run.json';fm=read(fmp)
   omitted={'joint_Q_C':[am['artifact_refs']['queries'],cm['artifact_refs']['candidates']], 'query_only':[am['artifact_refs']['queries']], 'query_coverage':[cm['artifact_refs']['query_coverage']], 'source':[next(iter(am['identity']['input_hashes']))], 'code':['scripts/anchor_pilot.py']}.get(case,[])
   for n in omitted:a['fingerprints'].pop(n);fm['identity']['input_hashes'].pop(n)
   if case=='extra':
    n='artifacts/independent_extra.txt';(f.root/n).write_text('synthetic extra');a['fingerprints'][n]=digest(f.root/n);fm['identity']['input_hashes'][n]=digest(f.root/n)
    top=read(f.exp);top['fingerprints'][n]=digest(f.root/n);write(f.exp,top)
   if case=='wrong_approval_value':a['fingerprints'][cm['artifact_refs']['candidates']]='b'*64
   if case=='F_only_missing_C':fm['identity']['input_hashes'].pop(cm['artifact_refs']['candidates'])
   if case!='baseline':
    write(ap,a);write(fmp,fm)
    if 'wrong_anchor' in case or case=='feature_wrong_candidate':
     kind='candidate' if case.startswith('candidate_') else 'features';p=f.root/e[kind]['directory']/'report.json';r=read(p);r['candidate_run_id' if case=='feature_wrong_candidate' else 'anchor_run_id']='a'*64;write(p,r)
    f.reseal()
    if case=='wrong_approval_value':
     # Ordinary resealing refreshes values. Reintroduce the wrong declared value,
     # then independently reseal only dependent F/report/state/top bytes.
     a=read(ap);a['fingerprints'][cm['artifact_refs']['candidates']]='b'*64;write(ap,a);e['acceptance']['sha256']=digest(ap)
     fm=read(fmp);fm['identity']['input_hashes'][e['acceptance']['path']]=digest(ap);fm['run_id']=hashlib.sha256(enc(fm['identity']).encode()).hexdigest();write(fmp,fm)
     frp=f.root/e['features']['directory']/'report.json';fr=read(frp);fr['run_id']=fm['run_id'];write(frp,fr);e['features']['run_id']=fm['run_id'];e['features']['fingerprints']={n:digest(f.root/n) for n in e['features']['fingerprints']};write(f.f.directory/'state.json',f.state);f.repin()
   out=f.result();results.append(dict(case=case,status=out['status'],gate=out.get('failure_gate'),completed=out['completed']))
  finally:f.close()
 f=Tiny()
 try:
  for name in ['wall','cpu','rss','close_error','counter_error','primary_plus_close']:
   changed=[False];realwall=time.monotonic;realcpu=time.process_time;realrss=v._rss
   class Connection:
    def __init__(self,*a,**k):self.inner=limited(*a,**k)
    def __getattr__(self,n):return getattr(self.inner,n)
    def close(self):
     self.inner.close();changed[0]=True
     if name in ['close_error','primary_plus_close']:raise OSError('INDEPENDENT close error')
   def rss():
    if changed[0] and name=='counter_error':raise OSError('INDEPENDENT counter unavailable')
    return 512*2**20+1 if changed[0] and name=='rss' else realrss()
   extra=patch.object(v,'_qyc',side_effect=ValueError('independent.primary')) if name=='primary_plus_close' else contextlib.nullcontext()
   with patch('duckdb.connect',side_effect=Connection),patch.object(v.time,'monotonic',side_effect=lambda:realwall()+(700 if changed[0] and name=='wall' else 0)),patch.object(v.time,'process_time',side_effect=lambda:realcpu()+(700 if changed[0] and name=='cpu' else 0)),patch.object(v,'_rss',side_effect=rss),extra:
    out=f.result();results.append(dict(case='cleanup_'+name,status=out['status'],gate=out.get('failure_gate'),completed=out['completed'],resources=out['resources'],secondary=out.get('finalization_failures',[])))
 finally:f.close()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,cpu_seconds=time.process_time()-cpu,peak_rss_bytes=v._rss()),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab018-independent-rereview-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
assert results[0]['status']=='verified'
assert all(r['status']=='failed' for r in results[1:])

```
