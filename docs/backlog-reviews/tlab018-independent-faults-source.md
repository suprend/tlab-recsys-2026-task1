# Independent synthetic verification harness archive

Historical source, with only machine paths made portable. Extract the base faults script and dependent scripts to the system temporary directory; run from the project root. These use synthetic fixtures only. Evidence belongs to the exact version in the associated [initial review](tlab018-independent-review.md) or [targeted acceptance](tlab018-independent-rereview.md); the initial lineage harness deliberately records four false passes. Archiving does not claim a new execution, acceptance-writing or real-source run.

```python
import sys, json, hashlib, time, resource, unittest, contextlib, io
from pathlib import Path
from unittest.mock import patch
ROOT=Path.cwd().resolve();sys.path.insert(0,str(ROOT))
import duckdb
from tests.test_development_collection import DevelopmentRuntimeTests
from scripts import verify_development as v

def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(enc(x)+'\n')
realconnect=duckdb.connect

def limited(*a,**k):
 c=realconnect(*a,**k);c.execute('SET threads=2');return c

class Tiny:
 def __init__(self):
  self.f=DevelopmentRuntimeTests('test_actual_producers_wait_for_external_review_then_resume_full_features_and_cache');self.f.setUp()
  self.root=self.f.root;self.f.execute();self.f.approve_shards();self.f.execute();self.state=self.f.read_state()
  names=set(self.f.plan['execution_inputs']['fingerprints'])|{str((self.f.directory/'state.json').relative_to(self.root)),str((self.f.directory/'plan.json').relative_to(self.root)),self.state['attempts'][-1]}
  for e in self.state['shards']:
   names.add(e['acceptance']['path'])
   for kind in ['anchor','candidate','features']:
    names.update(e[kind]['fingerprints']);m=read(self.root/e[kind]['directory']/'run.json')
    names.update(m['identity']['input_hashes']);names.update(m['identity']['code_hashes'])
  self.exp=self.root/'artifacts/acceptance/independent018.json'
  write(self.exp,dict(version=1,approved=True,scope='reviewed_development_collection',collection_id=self.f.plan['collection_id'],complete_attempt_report=self.state['attempts'][-1],fingerprints={n:digest(self.root/n) for n in names}))
 def repin(self):
  x=read(self.exp);x['fingerprints']={n:digest(self.root/n) for n in x['fingerprints']};write(self.exp,x)
 def reseal(self):
  # Independently rebuild the directed content dependencies, not author rewrite_output.
  for e in self.state['shards']:
   dirs={k:self.root/e[k]['directory'] for k in ['anchor','candidate','features']}
   am=read(dirs['anchor']/'run.json');cm=read(dirs['candidate']/'run.json')
   cm['identity']['input_hashes']={n:digest(self.root/n) for n in cm['identity']['input_hashes']}
   cm['run_id']=hashlib.sha256(enc(cm['identity']).encode()).hexdigest();write(dirs['candidate']/'run.json',cm)
   cr=read(dirs['candidate']/'report.json');cr['run_id']=cm['run_id'];write(dirs['candidate']/'report.json',cr)
   ap=self.root/e['acceptance']['path'];a=read(ap);a['candidate_run_id']=cm['run_id'];a['fingerprints']={n:digest(self.root/n) for n in a['fingerprints']};write(ap,a)
   e['acceptance']['sha256']=digest(ap);e['candidate']['run_id']=cm['run_id']
   fm=read(dirs['features']/'run.json');fr=read(dirs['features']/'report.json')
   for n in fm['identity']['input_hashes']:
    if '/selections/' in n:
     s=read(self.root/n);s['source_candidate_run']=cm['run_id'];write(self.root/n,s);fr['selection']=s
   fm['identity']['input_hashes']={n:digest(self.root/n) for n in fm['identity']['input_hashes']};fm['run_id']=hashlib.sha256(enc(fm['identity']).encode()).hexdigest();write(dirs['features']/'run.json',fm)
   fr['run_id']=fm['run_id'];fr['output_sha256']=digest(self.root/fm['artifact_refs']['features']);write(dirs['features']/'report.json',fr);e['features']['run_id']=fm['run_id']
   for k in dirs:e[k]['fingerprints']={n:digest(self.root/n) for n in e[k]['fingerprints']}
  write(self.f.directory/'state.json',self.state);self.repin()
 def mutate(self,label,sql):
  e=self.state['shards'][0];kind={'features':'features','labels':'anchor','queries':'anchor','candidates':'candidate'}[label]
  m=read(self.root/e[kind]['directory']/'run.json');p=self.root/m['artifact_refs'][label];c=limited(':memory:')
  try:
   c.read_parquet(str(p)).create_view('old');c.execute('CREATE TABLE bad AS '+sql);tmp=p.with_suffix('.independent.parquet');c.execute('COPY bad TO ? (FORMAT PARQUET)',[str(tmp)]);tmp.replace(p)
  finally:c.close()
  self.reseal()
 def result(self):
  try:return v.verify(self.root,self.exp)
  except v.VerificationError as e:return e.evidence
 def close(self):self.f.doCleanups()

start=time.monotonic();cpu=time.process_time();results=[]
with patch('duckdb.connect',side_effect=limited):
 for name,label,sql in [
  ('baseline',None,None),('drop_fullY','labels','SELECT * FROM old WHERE false'),
  ('alter_Q_diagnostic','queries','SELECT * REPLACE(history_active_days_7d+1 AS history_active_days_7d) FROM old'),
  ('alter_recent_time','candidates',"SELECT * REPLACE(last_user_event_time+INTERVAL 1 SECOND AS last_user_event_time) FROM old"),
  ('bad_coverage','features','SELECT * REPLACE(0.125::DOUBLE AS source_coverage_168h) FROM old'),
  ('bad_age','features','SELECT * REPLACE(item_observed_age_seconds+1 AS item_observed_age_seconds) FROM old'),
  ('bad_category_denominator','features','SELECT * REPLACE(category_view_7d+1 AS category_view_7d) FROM old')]:
  f=Tiny()
  try:
   if label:f.mutate(label,sql)
   out=f.result();results.append(dict(case=name,status=out['status'],gate=out.get('failure_gate'),completed=out['completed']))
  finally:f.close()
 for name,kind,field in [('candidate_report_wrong_anchor','candidate','anchor_run_id'),('feature_report_wrong_anchor','features','anchor_run_id'),('feature_report_wrong_candidate','features','candidate_run_id')]:
  f=Tiny()
  try:
   p=f.root/f.state['shards'][0][kind]['directory']/'report.json';r=read(p);r[field]='a'*64;write(p,r);f.reseal();out=f.result();results.append(dict(case=name,status=out['status'],gate=out.get('failure_gate'),completed=out['completed']))
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
    out=f.result();results.append(dict(case='cleanup_'+name,status=out['status'],gate=out.get('failure_gate'),completed=out['completed'],resources=out['resources'],finalization_failures=out.get('finalization_failures',[])))
 finally:f.close()
result=dict(cases=results,actual_resources=dict(wall_seconds=time.monotonic()-start,cpu_seconds=time.process_time()-cpu,peak_rss_bytes=v._rss()),fits=0,real_source_reads=0)
(Path(__import__('tempfile').gettempdir())/'tlab018-independent-fault-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

```
