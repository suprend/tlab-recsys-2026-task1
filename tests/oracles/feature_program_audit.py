"""DRAFT independent selected12 source audit; reviewed issuer context required.
No Y relation, compiler formula, production counter, model or fit is used.
"""
import time
START=time.monotonic()
import sys,resource,json,hashlib,math,argparse,threading,re
from pathlib import Path
from datetime import datetime,timedelta,timezone

COLUMNS=(('auto_pair_view_count_24h','BIGINT'),('auto_pair_cart_count_24h','BIGINT'),('auto_pair_purchase_count_24h','BIGINT'),('auto_pair_cart_recency_seconds_observed','DOUBLE'),('auto_pair_cart_recency_seconds_observed_missing','BOOLEAN'),('auto_item_cart_count_24h','BIGINT'),('auto_user_view_count_24h','BIGINT'),('auto_user_cart_count_24h','BIGINT'),('auto_user_purchase_count_24h','BIGINT'),('auto_item_view_count_distinct_24h_user_id','BIGINT'),('auto_item_cart_count_distinct_168h_user_id','BIGINT'),('auto_item_purchase_count_distinct_24h_user_id','BIGINT'))
RECENCY='auto_pair_cart_recency_seconds_observed'
PROOF='all_selected12_values_and_accepted_QC_domain'
def need(condition,message):
 if not condition:raise ValueError(message)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def parse(raw):
 def pairs(rows):
  out={}
  for k,v in rows:need(k not in out,'Duplicate JSON key');out[k]=v
  return out
 return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def read(path):return parse(Path(path).read_bytes())
def utc(v):
 need(type(v) is str and v.endswith('Z'),'UTC timestamp required');return datetime.fromisoformat(v[:-1]+'+00:00').astimezone(timezone.utc).replace(tzinfo=None)
def quote(v):
 need(type(v) is str and v.replace('_','').isalnum() and v[0].isalpha(),'Unsafe physical column');return '"'+v+'"'
def schema(con,table):return [tuple(r[:2]) for r in con.execute('DESCRIBE '+table).fetchall()]
def difference(con,left,right,names):
 cols=','.join(quote(n) for n in names)
 return con.execute('SELECT count(*) FROM ((SELECT '+cols+' FROM '+left+' EXCEPT ALL SELECT '+cols+' FROM '+right+') UNION ALL (SELECT '+cols+' FROM '+right+' EXCEPT ALL SELECT '+cols+' FROM '+left+'))').fetchone()[0]
def validate_source_claim(body):
 static=dict(version=1,scope='once_only_selected12_source_preparation',declared_shared_study_actual_cpu_seconds=7200,source_cpu_allocation=900,source_wall_allocation=1200,oracle_cpu_allocation=900,fit_attempts_authorized_here=0,unknown_cost_policy='STOP_no_refill',accounting='fresh_absolute_SELF_plus_successful_parent_tail_receipt_later_shared_prefix')
 need(type(body) is dict and set(body)==set(static)|{'attempt_token','created_actual_utc'} and all(canonical(body[k])==canonical(v) for k,v in static.items()),'Source once-claim contract differs')
 need(type(body['attempt_token']) is str and re.fullmatch(r'attempt-[0-9a-f]{32}',body['attempt_token']) is not None and type(body['created_actual_utc']) is str,'Source claim audit identity')
 created=datetime.fromisoformat(body['created_actual_utc']);need(created.tzinfo is not None and created.utcoffset()==timedelta(0),'Source claim UTC audit timestamp')

def validate_source_parent(parent,run_id,manifest_ref,report_ref,*,report=None):
 need(type(parent) is dict and set(parent)=={'status','scope','run_id','actual_cpu_seconds','producer'} and parent['status']=='verified' and parent['scope']=='source_lifetime_only_no_formula_acceptance' and parent['run_id']==run_id,'Exact pre-oracle source parent receipt required')
 cost=parent['producer'];need(type(cost) is dict and set(cost)=={'exit_code','actual_cpu_seconds','wall_seconds','peak_rss_bytes','manifest','report'} and type(cost['exit_code']) is int and cost['exit_code']==0,'Successful source producer lifetime required')
 for key,cap in [('actual_cpu_seconds',900),('wall_seconds',1200)]:need(type(cost[key]) in (int,float) and math.isfinite(cost[key]) and 0<=cost[key]<=cap,'Source parent lifetime cost unknown/over cap')
 need(type(cost['peak_rss_bytes']) is int and 0<cost['peak_rss_bytes']<=8*2**30 and canonical(cost['manifest'])==canonical(manifest_ref) and canonical(cost['report'])==canonical(report_ref),'Source parent RSS/receipt binding')
 need(type(parent['actual_cpu_seconds']) in (int,float) and math.isfinite(parent['actual_cpu_seconds']) and parent['actual_cpu_seconds']==cost['actual_cpu_seconds'],'Source prefix CPU must charge producer once')
 if report is not None:
  for key,cap in [('process_cpu_user_system_seconds',900),('seconds',1200),('process_peak_rss_bytes',8*2**30)]:need(type(report.get(key)) in (int,float) and math.isfinite(report[key]) and 0<=report[key]<=cap,'Source body measurement unknown/over cap')
  need(cost['actual_cpu_seconds']+1e-6>=report['process_cpu_user_system_seconds'] and cost['wall_seconds']+1e-6>=report['seconds'] and cost['peak_rss_bytes']>=report['process_peak_rss_bytes'],'Source parent full lifetime contradicts measured body')

def expected_programs():
 # This explicit reviewed vocabulary is independent of producer program helpers.
 rows=[]
 for grain in ['pair','user']:
  for action in ['view','cart','purchase']:rows.append(dict(name=f'auto_{grain}_{action}_count_24h',grain=grain,event_type=action,operator='count',window=24,column=None))
 rows.extend([dict(name=RECENCY,grain='pair',event_type='cart',operator='recency_seconds',window='observed',column='event_time'),dict(name='auto_item_cart_count_24h',grain='item',event_type='cart',operator='count',window=24,column=None)])
 for action,h in [('view',24),('cart',168),('purchase',24)]:rows.append(dict(name=f'auto_item_{action}_count_distinct_{h}h_user_id',grain='item',event_type=action,operator='count_distinct',window=h,column='user_id'))
 return {r['name']:r for r in rows}
def validate_selected(union,base):
 need(len(union['physical_delta'])==12 and {f['name']:f['dtype'] for f in union['physical_delta']}==dict(COLUMNS),'Only exact selected12 schema supported')
 programs=union['registry']['features'][len(base['features']):]
 need(len(programs)==11 and {p['name']:p for p in programs}==expected_programs(),'Selected11 core definitions differ from independently reviewed vocabulary')
 need([union['arms'][slot]['bundle_id'] for slot in ['I1','I2','R1','R2']]==['L02','L06','L01','L05'],'Fixed selected bundle allocation differs')

def build_expected(con,source_start,anchor,*,check=lambda:None):
 """Source events+accepted audit_q/audit_c only; no producer values or AST eval.
 Three maps have full determinant domains, including known-empty aggregate keys.
 """
 need(source_start<=anchor,'Anchor before observed source');check()
 need(all(dict(schema(con,'audit_q')).get(k)==t for k,t in [('query_id','VARCHAR'),('user_id','BIGINT'),('anchor','TIMESTAMP')]) and all(dict(schema(con,'audit_c')).get(k)==t for k,t in [('query_id','VARCHAR'),('product_id','BIGINT')]),'Accepted Q/C exact typed key transport')
 need(con.execute('SELECT count(*)=count(DISTINCT query_id) AND count(*) FILTER(WHERE query_id IS NULL OR user_id IS NULL OR anchor IS NULL OR anchor<>?)=0 FROM audit_q',[anchor]).fetchone()[0],'Accepted Q identity/anchor')
 need(con.execute('SELECT count(*)=count(DISTINCT(query_id,product_id)) AND count(*) FILTER(WHERE query_id IS NULL OR product_id IS NULL)=0 FROM audit_c').fetchone()[0],'Accepted C identity')
 need(con.execute('SELECT count(*) FROM audit_c c ANTI JOIN audit_q q USING(query_id)').fetchone()[0]==0,'Accepted C orphan')
 con.execute('CREATE OR REPLACE TEMP TABLE audit_t AS SELECT c.query_id,c.product_id,q.user_id,q.anchor FROM audit_c c JOIN audit_q q USING(query_id)')
 con.execute('CREATE OR REPLACE TEMP TABLE audit_du AS SELECT DISTINCT user_id FROM audit_q')
 con.execute('CREATE OR REPLACE TEMP TABLE audit_di AS SELECT DISTINCT product_id FROM audit_t')
 con.execute('CREATE OR REPLACE TEMP TABLE audit_dp AS SELECT DISTINCT user_id,product_id FROM audit_t')
 lo24=max(source_start,anchor-timedelta(hours=24));lo168=max(source_start,anchor-timedelta(hours=168))
 # Count raw joined event rows. Only domain keys are distinct; never source rows.
 con.execute('''CREATE OR REPLACE TEMP TABLE audit_eu AS SELECT d.user_id,
  count(e.event_type) FILTER(WHERE e.event_type='view')::BIGINT auto_user_view_count_24h,
  count(e.event_type) FILTER(WHERE e.event_type='cart')::BIGINT auto_user_cart_count_24h,
  count(e.event_type) FILTER(WHERE e.event_type='purchase')::BIGINT auto_user_purchase_count_24h
  FROM audit_du d LEFT JOIN events e ON e.user_id=d.user_id AND e.event_time>=? AND e.event_time<? GROUP BY d.user_id''',[lo24,anchor]);check()
 con.execute('''CREATE OR REPLACE TEMP TABLE audit_ei AS SELECT d.product_id,
  count(DISTINCT e.user_id) FILTER(WHERE e.event_type='view' AND e.event_time>=?)::BIGINT auto_item_view_count_distinct_24h_user_id,
  count(DISTINCT e.user_id) FILTER(WHERE e.event_type='cart')::BIGINT auto_item_cart_count_distinct_168h_user_id,
  count(DISTINCT e.user_id) FILTER(WHERE e.event_type='purchase' AND e.event_time>=?)::BIGINT auto_item_purchase_count_distinct_24h_user_id,
  count(e.event_type) FILTER(WHERE e.event_type='cart' AND e.event_time>=?)::BIGINT auto_item_cart_count_24h
  FROM audit_di d LEFT JOIN events e ON e.product_id=d.product_id AND e.event_time>=? AND e.event_time<? GROUP BY d.product_id''',[lo24,lo24,lo24,lo168,anchor]);check()
 con.execute('''CREATE OR REPLACE TEMP TABLE audit_ep AS SELECT d.user_id,d.product_id,
  count(e.event_type) FILTER(WHERE e.event_type='view' AND e.event_time>=?)::BIGINT auto_pair_view_count_24h,
  count(e.event_type) FILTER(WHERE e.event_type='cart' AND e.event_time>=?)::BIGINT auto_pair_cart_count_24h,
  count(e.event_type) FILTER(WHERE e.event_type='purchase' AND e.event_time>=?)::BIGINT auto_pair_purchase_count_24h,
  CAST(date_diff('microsecond',max(e.event_time) FILTER(WHERE e.event_type='cart'),?::TIMESTAMP) AS DOUBLE)/1000000 auto_pair_cart_recency_seconds_observed,
  (max(e.event_time) FILTER(WHERE e.event_type='cart') IS NULL) auto_pair_cart_recency_seconds_observed_missing
  FROM audit_dp d LEFT JOIN events e ON e.user_id=d.user_id AND e.product_id=d.product_id AND e.event_time>=? AND e.event_time<? GROUP BY d.user_id,d.product_id''',[lo24,lo24,lo24,anchor,source_start,anchor]);check()
 for domain,expected,keys in [('audit_du','audit_eu',['user_id']),('audit_di','audit_ei',['product_id']),('audit_dp','audit_ep',['user_id','product_id'])]:
  need(difference(con,domain,expected,keys)==0,'Expected map domain is incomplete')
  need(con.execute('SELECT count(*)=count(DISTINCT('+','.join(keys)+')) FROM '+expected).fetchone()[0],'Expected map multiplicity')
 cols=[]
 for n,t in COLUMNS:cols.append(('p.' if n.startswith('auto_pair_') else 'u.' if n.startswith('auto_user_') else 'i.')+quote(n))
 con.execute('CREATE OR REPLACE TEMP VIEW audit_expected AS SELECT t.query_id,t.product_id,'+','.join(cols)+' FROM audit_t t JOIN audit_eu u USING(user_id) JOIN audit_ei i USING(product_id) JOIN audit_ep p USING(user_id,product_id)')
 need(difference(con,'audit_t','audit_expected',['query_id','product_id'])==0,'Expected every-key broadcast incomplete');check()
 return dict(queries=con.execute('SELECT count(*) FROM audit_q').fetchone()[0],pairs=con.execute('SELECT count(*) FROM audit_t').fetchone()[0],user_domain=con.execute('SELECT count(*) FROM audit_du').fetchone()[0],item_domain=con.execute('SELECT count(*) FROM audit_di').fetchone()[0],pair_domain=con.execute('SELECT count(*) FROM audit_dp').fetchone()[0])

def physical_boundary(con):
 """Independent range/oldF preservation gate. Legal count2->3 can pass here."""
 old=schema(con,'audit_old');actual=schema(con,'audit_actual');oldnames=[n for n,t in old]
 need(len(old)==45 and len(actual)==57 and len(set(n for n,t in actual))==57,'Old45 plus selected12 physical schema')
 need([(n,t) for n,t in actual if n not in oldnames]==list(COLUMNS) or dict((n,t) for n,t in actual if n not in oldnames)==dict(COLUMNS),'Selected12 physical names/types')
 need({n:t for n,t in actual if n in oldnames}==dict(old),'Old physical types changed')
 need(difference(con,'audit_old','audit_actual',oldnames)==0,'Some accepted baseline field changed')
 need(difference(con,'audit_t','audit_actual',['query_id','product_id'])==0,'Every accepted C physical key differs')
 need(con.execute('SELECT count(*)=count(DISTINCT(query_id,product_id)) FROM audit_actual').fetchone()[0],'Actual row duplicates')
 for n,t in COLUMNS:
  if t=='BIGINT':need(con.execute('SELECT count(*) FROM audit_actual WHERE '+quote(n)+' IS NULL OR '+quote(n)+'<0').fetchone()[0]==0,'Invalid count NULL/range')
 need(con.execute('SELECT count(*) FROM audit_actual WHERE '+quote(RECENCY+'_missing')+' IS DISTINCT FROM ('+quote(RECENCY)+' IS NULL) OR ('+quote(RECENCY)+' IS NOT NULL AND (NOT isfinite('+quote(RECENCY)+') OR '+quote(RECENCY)+'<=0))').fetchone()[0]==0,'Invalid recency/missing state')
 return dict(baseline_all45_preserved=True,source_formula_acceptance=False)

def compare_every_value(con,*,check=lambda:None):
 need(difference(con,'audit_t','audit_actual',['query_id','product_id'])==0,'Actual source key cover')
 checks=[]
 for n,t in COLUMNS:
  a='a.'+quote(n);e='e.'+quote(n)
  if t=='DOUBLE':checks.append('('+a+' IS NULL) IS DISTINCT FROM ('+e+' IS NULL) OR ('+a+' IS NOT NULL AND ('+'NOT isfinite('+a+') OR abs('+a+'-'+e+')>1e-9))')
  else:checks.append(a+' IS DISTINCT FROM '+e)
 sql='SELECT count(*) FROM audit_actual a JOIN audit_expected e USING(query_id,product_id) WHERE '+' OR '.join('('+v+')' for v in checks)
 check();bad=con.execute(sql).fetchone()[0];check();need(bad==0,'Independent selected12 source formulas differ')
 rows=con.execute('SELECT count(*) FROM audit_actual').fetchone()[0]
 return dict(checked_rows=rows,checked_values=rows*12,mismatch_rows=bad,formula_values_complete=True)

class Audit:
 def __init__(self,path,issued_sha):
  self.path=Path(path).resolve();raw=self.path.read_bytes();need(len(raw)<=65536 and type(issued_sha) is str and hashlib.sha256(raw).hexdigest()==issued_sha,'Context issuer snapshot differs');c=parse(raw);self.context=c;self.context_sha=issued_sha
  need(set(c)=={'version','scope','run_id','project_root','invocation_directory','request','oracle_execution_approval','producer_manifest','producer_report','oracle_source','allocation','shared_budget','issued_at_monotonic','output_path','failed_output_path'},'Prospective oracle context schema')
  need(type(c['version']) is int and c['version']==1 and c['scope']=='independent_selected_feature_program_source_oracle','Oracle context scope')
  self.root=Path(c['project_root']).resolve();need(Path(c['project_root']).is_absolute(),'Absolute context root required');self.con=None;self.timer=None;self.stopped=threading.Event();self.expired=threading.Event()
  a=c['allocation'];need(set(a)=={'cpu_seconds','deadline_monotonic','rss_bytes'} and type(a['cpu_seconds']) is int and 1<=a['cpu_seconds']<=900 and type(a['rss_bytes']) is int and a['rss_bytes']==8*2**30 and type(a['deadline_monotonic']) in (int,float) and math.isfinite(a['deadline_monotonic']) and START<a['deadline_monotonic']<=START+1200,'Oracle allocation')
  need(type(c['issued_at_monotonic']) in (int,float) and 0<=c['issued_at_monotonic']<=START,'Context issue clock');self.allocation=a
  inv=self.local(c['invocation_directory']);need(inv.is_relative_to(self.root/'artifacts/feature-program-source-oracle'),'Oracle output namespace')
  self.output=self.local(c['output_path']);self.failed=self.local(c['failed_output_path']);need(self.path==inv/'context.json' and self.output==inv/'evidence.json' and self.failed==inv/'evidence.failed.json','Oracle output paths')
  need(not self.output.exists() and not self.failed.exists(),'Immutable oracle output already exists')
  self.source=dict(path=str(Path(__file__).resolve().relative_to(self.root)),sha256=self.sha(Path(__file__).resolve())) if Path(__file__).resolve().is_relative_to(self.root) else dict(path=str(Path(__file__).resolve()),sha256=self.sha(Path(__file__).resolve()))
  need(c['oracle_source']==self.source,'Oracle source binding')
 def local(self,n):
  need(type(n) is str and not Path(n).is_absolute() and '..' not in Path(n).parts,'Nonlocal artifact path');p=(self.root/n).resolve();need(p.is_relative_to(self.root),'Artifact escaped root');return p
 def cpu(self):
  r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime
 def rss(self):return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1024 if sys.platform.startswith('linux') else 1))
 def guard(self):
  need(sys.platform=='darwin' or sys.platform.startswith('linux'),'Unknown RSS units')
  if self.expired.is_set() or time.monotonic()>self.allocation['deadline_monotonic'] or self.cpu()>self.allocation['cpu_seconds']:raise TimeoutError('Oracle actual CPU/shared deadline')
  if self.rss()>self.allocation['rss_bytes']:raise MemoryError('Oracle RSS8GiB')
  child=resource.getrusage(resource.RUSAGE_CHILDREN);need(child.ru_utime+child.ru_stime==0,'Oracle children forbidden')
 def sha(self,path):
  h=hashlib.sha256()
  with Path(path).open('rb') as f:
   while block:=f.read(4*1024*1024):self.guard();h.update(block)
  return h.hexdigest()
 def pins(self,pins):
  for p,h in pins.items():need(self.sha(self.local(p))==h,'Pinned bytes differ')
 def request_binding(self):
  c=self.context
  refs=[c[n] for n in ['request','oracle_execution_approval','producer_manifest','producer_report']]
  for v in refs:need(set(v)=={'path','sha256'},'Artifact pin schema');self.pins({v['path']:v['sha256']})
  request=read(self.local(c['request']['path']));need(canonical(request)==canonical({k:c[k] for k in ['scope','run_id','producer_manifest','producer_report','oracle_source','shared_budget']}),'Oracle request scope')
  need(canonical(read(self.local(c['oracle_execution_approval']['path'])))==canonical(dict(version=1,approved=True,scope=c['scope'],run_id=c['run_id'],request_sha256=c['request']['sha256'],oracle_source=c['oracle_source'])),'Independent exact oracle approval required')
  shared=c['shared_budget'];need(set(shared)=={'limit_cpu_seconds','charged_prefix_cpu_seconds','unknown_cost','source_parent_receipt'} and type(shared['limit_cpu_seconds']) is int and shared['limit_cpu_seconds']==7200 and shared['unknown_cost'] is False and type(shared['charged_prefix_cpu_seconds']) in (int,float) and math.isfinite(shared['charged_prefix_cpu_seconds']) and shared['charged_prefix_cpu_seconds']>=0 and shared['charged_prefix_cpu_seconds']+self.allocation['cpu_seconds']<=7200,'Unknown/insufficient shared016 cost')
  pr=shared['source_parent_receipt'];need(set(pr)=={'path','sha256'},'Parent receipt pin');self.pins({pr['path']:pr['sha256']});parent=read(self.local(pr['path']))
  validate_source_parent(parent,c['run_id'],c['producer_manifest'],c['producer_report']);need(parent['actual_cpu_seconds']<=shared['charged_prefix_cpu_seconds'],'Shared charged prefix omits source parent');self.source_parent=parent
  return refs
 def install_timer(self):
  def monitor():
   while not self.stopped.wait(.1):
    try:self.guard()
    except BaseException:
     self.expired.set()
     if self.con is not None:
      try:self.con.interrupt()
      except BaseException:pass
     return
  self.timer=threading.Thread(target=monitor,daemon=True);self.timer.start()
 def execute(self):
  self.install_timer();refs=self.request_binding();c=self.context;directory=self.local(c['producer_manifest']['path']).parent
  need(directory==self.root/'artifacts/feature-program-collection'/c['run_id'] and self.local(c['producer_report']['path'])==directory/'report.json' and not (directory/'report.failed.json').exists(),'Producer known failure/path')
  manifest=read(directory/'run.json');report=read(directory/'report.json');need(manifest['run_id']==report['run_id']==c['run_id'] and digest(manifest['identity'])==c['run_id'],'Producer identity')
  need(report['status']=='complete_produced_unreviewed' and report['labels_loaded'] is False and type(report['fit_attempt_count']) is int and report['fit_attempt_count']==0 and report.get('source_formula_acceptance') is False,'Source-only complete producer required');validate_source_parent(self.source_parent,c['run_id'],c['producer_manifest'],c['producer_report'],report=report)
  sys.path.insert(0,str(self.root));from scripts import feature_program_collection as producer
  need(producer.ROOT.resolve()==self.root and Path(producer.__file__).resolve()==self.root/'scripts/feature_program_collection.py','Wrong imported producer checkout');need(canonical(report.get('limits'))==canonical(producer.LIMITS),'Source report limits differ from reviewed producer')
  r=manifest['identity']['acceptance_refs'];plan,collections=producer.prepare_plan(*(self.local(r[k]) for k in ['train','selection','contract','base_registry']),check=self.guard)
  need(canonical(plan['identity'])==canonical(manifest['identity']) and plan['run_id']==c['run_id'],'Re-derived actual source plan differs');self.pins(plan['identity']['fingerprints'])
  union=plan['identity']['selected_union'];validate_selected(union,plan['identity']['pool']['identity']['base_registry'])
  er=manifest['execution_approval'];self.pins({er['path']:er['sha256']});need(canonical(read(self.local(er['path'])))==canonical(dict(version=1,approved=True,scope=producer.ROLE,run_id=c['run_id'],fingerprints=plan['identity']['fingerprints'])),'Producer execution approval differs')
  claim=manifest['source_claim'];need(set(claim)=={'path','sha256'} and claim['path']=='artifacts/feature-program-study/source.claim.json','Source once-claim namespace');self.pins({claim['path']:claim['sha256']});need(canonical(claim)==canonical(report['source_claim']),'Source once-claim detached');validate_source_claim(read(self.local(claim['path'])))
  need(set(manifest['outputs'])=={'train','selection'},'Exact phase cover required')
  import duckdb
  source_path=collections['train']['plan']['execution_inputs']['source_path'];self.con=duckdb.connect(str(self.local(source_path)),read_only=True);con=self.con
  con.execute('SET threads=2');con.execute("SET memory_limit='2GB'");temp=self.output.parent/'temp';temp.mkdir(exist_ok=False);con.execute('SET temp_directory=?',[str(temp)]);con.execute("SET max_temp_directory_size='2GB'")
  types=dict(schema(con,'events'));need(all(types.get(k)==t for k,t in [('event_time','TIMESTAMP'),('event_type','VARCHAR'),('product_id','BIGINT'),('user_id','BIGINT')]),'Raw source typed adapter differs')
  totals=dict(queries=0,pairs=0,user_domain=0,item_domain=0,pair_domain=0,checked_rows=0,checked_values=0);days=0;outputpins={};phase_coverage={}
  for role,col in collections.items():
   phase=col['phase'];start=utc(phase['range']['start']);end=utc(phase['range']['end']);source=col['plan']['identity']['shard_protocols'][0]['source'];source_start=utc(source['start']);source_end=utc(source['end'])
   qpaths=[str(self.local(p)) for p in col['refs']['queries']];cpaths=[str(self.local(p)) for p in col['refs']['candidates']]
   aq=con.execute("SELECT count(*),count(DISTINCT query_id),count(*) FILTER(WHERE anchor IS NULL OR user_id IS NULL OR query_id IS NULL OR anchor<? OR anchor>=? OR date_trunc('day',anchor)<>anchor) FROM read_parquet(?)",[start,end,qpaths]).fetchone()
   ac=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)),count(*) FILTER(WHERE query_id IS NULL OR product_id IS NULL) FROM read_parquet(?)',[cpaths]).fetchone()
   need(aq[0]==aq[1] and aq[2]==0 and ac[0]==ac[1] and ac[2]==0 and con.execute('SELECT count(*) FROM read_parquet(?) c ANTI JOIN read_parquet(?) q USING(query_id)',[cpaths,qpaths]).fetchone()[0]==0,'Whole accepted phase Q/C domain')
   phase_coverage[role]=dict(expected_queries=aq[0],expected_pairs=ac[0],checked_queries=0,checked_pairs=0)
   anchors=[start+timedelta(days=i) for i in range((end-start).days)];declared=manifest['outputs'][role];need([d['anchor'] for d in declared]==[t.strftime('%Y-%m-%dT%H:%M:%SZ') for t in anchors],'Every UTC day required')
   for day,anchor in zip(declared,anchors):
    self.guard();need(source_start<=anchor<=source_end,'Anchor/source availability');need(set(day)=={'anchor','artifacts','boundary'} and set(day['artifacts'])=={'queries','features'},'Exact daily artifacts')
    for kind,table in [('queries','audit_q'),('candidates','audit_c'),('features','audit_old')]:
     paths=[str(self.local(p)) for p in col['refs'][kind]]
     if kind=='queries':con.execute('CREATE OR REPLACE TEMP TABLE audit_q AS SELECT * FROM read_parquet(?) WHERE anchor=?',[paths,anchor])
     else:con.execute('CREATE OR REPLACE TEMP TABLE '+table+' AS SELECT f.* FROM read_parquet(?) f SEMI JOIN audit_q q USING(query_id)',[paths])
    qn=con.execute('SELECT count(*) FROM audit_q').fetchone()[0];cn=con.execute('SELECT count(*) FROM audit_c').fetchone()[0];need(qn<=2000 and cn<=440000,'Daily Q/C resource cap before aggregation')
    domains=build_expected(con,source_start,anchor,check=self.guard)
    phase_coverage[role]['checked_queries']+=domains['queries'];phase_coverage[role]['checked_pairs']+=domains['pairs']
    for kind,table in [('queries','audit_export_q'),('features','audit_actual')]:
     a=day['artifacts'][kind];need(set(a)=={'path','sha256','bytes','rows','schema'} and type(a['bytes']) is int and a['bytes']>0 and type(a['rows']) is int and a['rows']>=0,'Artifact descriptor');path=self.local(a['path']);need(path==directory/role/anchor.strftime('%Y-%m-%d')/(kind+'.parquet'),'Daily artifact namespace');need(self.sha(path)==a['sha256'] and path.stat().st_size==a['bytes'],'Physical artifact bytes');outputpins[a['path']]=a['sha256'];con.execute('CREATE OR REPLACE TEMP TABLE '+table+' AS SELECT * FROM read_parquet(?)',[str(path)]);need([list(r) for r in schema(con,table)]==a['schema'] and con.execute('SELECT count(*) FROM '+table).fetchone()[0]==a['rows'],'Artifact physical schema/count')
    need(schema(con,'audit_export_q')==schema(con,'audit_q') and difference(con,'audit_q','audit_export_q',[n for n,t in schema(con,'audit_q')])==0,'ALL accepted Q including emptyC preserved')
    # Mechanical schema composition only, on the SAME interruptible source
    # connection. No second producer inspector/connection can escape timer.
    expected_schema=producer._expected_schema(schema(con,'audit_old'),plan['identity']['pool']['identity']['base_registry'],union['registry'])
    need(schema(con,'audit_actual')==expected_schema,'Exact reviewed57 physical order/types')
    expected_boundary=dict(queries=qn,pairs=cn,new_physical_columns=12,baseline_all_fields_preserved=True,source_formula_acceptance=False,schema=[list(r) for r in expected_schema])
    need(canonical(day['boundary'])==canonical(expected_boundary),'Exact source daily boundary receipt')
    physical_boundary(con);checked=compare_every_value(con,check=self.guard)
    for name in ['queries','pairs','user_domain','item_domain','pair_domain']:totals[name]+=domains[name]
    for name in ['checked_rows','checked_values']:totals[name]+=checked[name]
    days+=1
  for cover in phase_coverage.values():need(cover['checked_queries']==cover['expected_queries'] and cover['checked_pairs']==cover['expected_pairs'],'Every accepted phase physical key must be covered once')
  self.pins(plan['identity']['fingerprints']);self.pins(outputpins);self.pins({v['path']:v['sha256'] for v in refs});need(not (directory/'report.failed.json').exists(),'Late failed producer')
  need(totals['checked_rows']==totals['pairs'] and totals['checked_values']==12*totals['pairs'],'Every physical selected value coverage')
  return dict(version=1,status='verified',run_id=c['run_id'],source_proof_scope=PROOF,formula_values_complete=True,fit_attempt_count=0,verified_outputs=outputpins,checked_pairs=totals['pairs'],checked_physical_columns=12,checked_scalar_values=totals['checked_values'],mismatch_count=0,oracle_source=self.source,checked_columns=12,checked_days=days,domains_and_coverage=totals,phase_coverage=phase_coverage,source_claim=claim,source_parent_receipt=c['shared_budget']['source_parent_receipt'],mismatch_rows=0,baseline_all45_preserved=True,baseline_source_formula_scope='preservation_only_prior_manual18_source_proof_unchanged',labels_loaded=False,independent_expected_values=True,recency_absolute_tolerance_seconds=1e-9,context_sha256=self.context_sha,request=c['request'],producer_manifest=c['producer_manifest'],producer_report=c['producer_report'],shared_budget=c['shared_budget'])
 def run(self):
  attempt=self.output.parent/'attempt.json'
  with attempt.open('x') as f:f.write(canonical(dict(status='running',context_sha256=self.context_sha,oracle_source=self.source))+'\n')
  error=None;result=None
  try:result=self.execute()
  except BaseException as e:error=e
  finally:
   self.stopped.set()
   for operation in [lambda:self.con.close() if self.con is not None else None,lambda:self.timer.join(timeout=1) if self.timer is not None else None,self.guard]:
    try:operation()
    except BaseException as e:
     if error is None:error=e
     else:error.add_note(type(e).__name__+' during terminal cleanup')
  if error is None:
   try:
    need(self.sha(self.path)==self.context_sha,'Context changed after verification');result.update(process_cpu_seconds=self.cpu(),process_peak_rss_bytes=self.rss(),started_monotonic=START,finished_monotonic=time.monotonic(),receipt_boundary='postclose_before_minimal_persistence_fresh_parent_must_charge_exit_tail')
    temp=Path(str(self.output)+'.temp');need(not temp.exists(),'Immutable output temp');temp.write_text(canonical(result)+'\n');temp.replace(self.output);self.guard();need(self.sha(self.path)==self.context_sha,'Context changed after evidence persistence');print(canonical(dict(status='verified',run_id=self.context['run_id'],fit_attempt_count=0)),flush=True);self.guard()
   except BaseException as e:error=e
  if error is not None:
   try:self.failed.write_text(canonical(dict(status='failed',run_id=self.context['run_id'],fit_attempt_count=0,error_type=type(error).__name__,raw_values_suppressed=True))+'\n')
   except BaseException as secondary:error.add_note(type(secondary).__name__+' while persisting failure')
   raise error
  return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',type=Path,required=True);p.add_argument('--issued-context-sha256',required=True);a=p.parse_args();Audit(a.context,a.issued_context_sha256).run()
if __name__=='__main__':
 try:main()
 except BaseException as error:print(canonical(dict(status='failed',fit_attempt_count=0,error_type=type(error).__name__,raw_values_suppressed=True)),file=sys.stderr);sys.exit(1)
