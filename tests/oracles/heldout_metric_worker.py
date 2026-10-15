"""Fixed issuer-bound heldout oracle adapter; actual execution requires authority."""
import time
ENTRY_MONOTONIC=time.monotonic()
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROLE='metric_oracle'
ENTRY='tests/oracles/heldout_metric_worker.py'
CORE='tests/oracles/heldout_metric_audit.py'
ROOT=Path(__file__).resolve().parents[2]


def need(condition,message):
 if not condition:raise ValueError(message)


def strict_json(raw):
 def unique(pairs):
  result={}
  for key,value in pairs:need(key not in result,'Duplicate JSON key');result[key]=value
  return result
 body=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
 def finite(value):
  if type(value) is float:need(math.isfinite(value),'Nonfinite JSON exponent')
  elif type(value) is dict:
   for child in value.values():finite(child)
  elif type(value) is list:
   for child in value:finite(child)
 finite(body);return body


def local(name):
 need(type(name) is str and name and not name.startswith('/') and '\\' not in name and all(p not in {'','.','..'} for p in name.split('/')),'Normalized original project path required')
 path=(ROOT/name).resolve();path.relative_to(ROOT.resolve());return path


def bounded_bytes(path,maximum):
 with Path(path).open('rb') as stream:raw=stream.read(maximum+1)
 need(len(raw)<=maximum,'Bounded original metadata/code exceeded');return raw


def bootstrap(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('--context',required=True);parser.add_argument('--issued-context-sha256',required=True)
 args=parser.parse_args(argv);need(re.fullmatch('[a-f0-9]{64}',args.issued_context_sha256) is not None,'Mandatory original issuer SHA')
 path=Path(args.context).resolve();path.relative_to(ROOT.resolve())
 raw=bounded_bytes(path,2**20);need(hashlib.sha256(raw).hexdigest()==args.issued_context_sha256,'Original context bytes differ')
 context=strict_json(raw)
 need(type(context) is dict and context.get('role')==ROLE and context.get('entry',{}).get('path')==ENTRY,'Fixed oracle entry required')
 pins=context['plan']['fingerprints'];request_ref=context['request'];need(pins.get(request_ref['path'])==request_ref['sha256'],'Original request outside projection')
 request_raw=bounded_bytes(local(request_ref['path']),2**20);need(hashlib.sha256(request_raw).hexdigest()==request_ref['sha256'],'Original request bytes differ')
 request=strict_json(request_raw);code=request['code_fingerprints']
 required={ENTRY,CORE,'scripts/heldout_worker_context.py','scripts/heldout_execution.py','scripts/heldout_contract.py'}
 need(type(code) is dict and required<=set(code),'Mandatory oracle bootstrap code omitted')
 for name,digest in code.items():
  need(pins.get(name)==digest,'Original code closure differs')
  if name.endswith('.py'):
   need(type(digest) is str and re.fullmatch('[a-f0-9]{64}',digest) is not None,'Original code SHA')
   need(hashlib.sha256(bounded_bytes(local(name),2**20)).hexdigest()==digest,'Cheap original code pin differs')
 for folder in ['scripts','tests','tests/oracles']:
  initializer=folder+'/__init__.py'
  need(not local(initializer).exists() or initializer in code,'Unpinned namespace initializer')
 need(context['entry']['sha256']==code[ENTRY],'Original adapter source detached')
 return path,args.issued_context_sha256


def _modules():
 from scripts import heldout_worker_context as w
 from scripts import heldout_execution as x
 from scripts import heldout_contract as h
 return w,x,h


def retain(execution,mapping):
 # Prospective reviewed helper API; retain BEFORE streaming/using nested bytes.
 execution.retain_pins(mapping);execution.verify_pins(mapping)


def parsed_ref(execution,reference):
 _,x,_=_modules();x.ref(reference);retain(execution,{reference['path']:reference['sha256']})
 body,digest=x.read(local(reference['path']));need(digest==reference['sha256'],'Original nested JSON differs');execution.budget.guard();return body


def owner_identity(execution):
 name=execution.reference['path'].rsplit('/',2)[0]+'/proposal.json';pins=execution.pins
 need(name in pins,'Original full owner proposal missing')
 proposal=parsed_ref(execution,dict(path=name,sha256=pins[name]));_,_,h=_modules()
 need(proposal['run_id']==execution.context['run_id']==h.digest(proposal['identity']),'Original full identity detached')
 return proposal['identity']


def source_manifest(execution,lock):
 _,x,h=_modules();body=execution.input_json('source_manifest');ctx=execution.context
 keys={'version','scope','run_id','decision_lock','choice','source','days','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'}
 h.keys(body,keys,'Unaccepted source manifest');need(type(body['version']) is int and body['version']==1 and body['scope']=='unaccepted_reserved_source' and body['run_id']==ctx['run_id'],'Original source manifest scope')
 need(body['decision_lock']==ctx['inputs']['lock'] and body['choice']==ctx['inputs']['choice'] and body['source']==owner_identity(execution)['source_inputs']['source'],'Original source authority detached')
 need(body['labels_loaded'] is False and type(body['fit_attempt_count']) is int and body['fit_attempt_count']==0 and type(body['native_prediction_count']) is int and body['native_prediction_count']==0,'Source work state differs')
 need(type(body['environment']) is dict,'Source environment absent')
 days=body['days'];need(type(days) is list and len(days)==7 and [r['anchor'] for r in days]==h.DAYS,'Complete canonical source days required')
 prefix=ctx['inputs']['source_manifest']['path'].rsplit('/',1)[0];outputs={}
 for row in days:
  h.keys(row,{'anchor','queries','candidates','base_features','extra_features','query_count','candidate_count','mature_query_count'},'Source day')
  h.integer(row['query_count'],0,2000,'Source Q');h.integer(row['candidate_count'],0,row['query_count']*220,'Source C');need(type(row['mature_query_count']) is int and row['mature_query_count']==row['query_count'],'Source maturity')
  for key,stem in [('queries','queries'),('candidates','candidates'),('base_features','base-features'),('extra_features','extra-features')]:
   ref=row[key]
   if key=='extra_features' and lock['choice']=='B':need(ref is None,'W=B extras forbidden');continue
   h.ref(ref);need(ref['path']==prefix+'/day-'+row['anchor'][8:10]+'/'+stem+'.parquet','Original daily output destination differs');outputs[ref['path']]=ref['sha256']
 need(body['outputs']==outputs,'Exact source output map differs');retain(execution,outputs)
 if ROLE=='source_oracle':
  receipt=execution.input_json('source_receipt');need(receipt['status']=='role_complete_unaccepted' and receipt['scope']=='reserved_reporting_source' and receipt['role']=='source' and receipt['run_id']==ctx['run_id'],'Original source receipt differs')
  need(receipt['inputs']=={k:ctx['inputs'][k] for k in ['lock','choice','source','pool','registry']},'Original source receipt input map differs')
  expected=dict(outputs);expected[ctx['inputs']['source_manifest']['path']]=ctx['inputs']['source_manifest']['sha256']
  need(receipt['outputs']==expected and receipt['labels_loaded'] is False and type(receipt['fit_attempt_count']) is int and receipt['fit_attempt_count']==0 and type(receipt['native_prediction_count']) is int and receipt['native_prediction_count']==0,'Original source receipt output/work state')
 else:
  acceptance=execution.input_json('source_acceptance');need(acceptance['approved'] is True and acceptance['scope']=='reviewed_reserved_source' and acceptance['run_id']==ctx['run_id'] and acceptance['days']==days,'Accepted source domain differs')
  need(all(acceptance['fingerprints'].get(n)==d for n,d in outputs.items()),'Accepted source physical closure differs')
 return body


def open_connection(execution,source=None):
 import duckdb,tempfile
 base=local(execution.reference['path']).parent;scratch=tempfile.TemporaryDirectory(prefix='oracle-scratch-',dir=base)
 con=None
 try:
  execution.budget.guard();con=duckdb.connect(':memory:',config={'threads':'2','memory_limit':'2GB','max_temp_directory_size':'2GB','temp_directory':scratch.name});execution.budget.watch(con)
  if source is not None:
   retain(execution,{source['path']:source['sha256']});path=str(local(source['path'])).replace("'","''")
   con.execute("ATTACH '"+path+"' AS heldout_input (READ_ONLY)");execution.budget.guard()
   con.execute('CREATE TEMP VIEW heldout_raw_events AS SELECT event_time,event_type,product_id,user_id,category_id FROM heldout_input.events');execution.budget.guard()
  return con,scratch
 except BaseException as error:
  close_resources(execution,con,scratch,error);raise


def load_day(execution,con,day,prefix):
 result={}
 for key in ['queries','candidates','base_features','extra_features']:
  reference=day[key];name=prefix+'_'+key;result[key]=None if reference is None else name
  con.execute('DROP VIEW IF EXISTS '+name);execution.budget.guard()
  if reference is not None:
   # All output refs were retained/hashed in the exact manifest closure first.
   path=str(local(reference['path'])).replace("'","''")
   con.execute("CREATE TEMP VIEW "+name+" AS SELECT * FROM read_parquet('"+path+"')");execution.budget.guard()
 return result


def close_resources(execution,con,scratch,primary=None,models=None):
 errors=[]
 if models is not None:
  try:
   import gc
   models.clear();gc.collect()
  except BaseException as error:errors.append(error)
 if con is not None:
  try:con.close()
  except BaseException as error:errors.append(error)
 if scratch is not None:
  try:scratch.cleanup()
  except BaseException as error:errors.append(error)
 try:execution.budget.guard()
 except BaseException as error:errors.append(error)
 if primary is not None:
  for error in errors:primary.add_note('Oracle cleanup: '+type(error).__name__)
 elif errors:raise errors[0]


def wrap(execution,core,environment):
 ctx=execution.context
 return dict(version=1,scope='unaccepted_reserved_'+ROLE+'_evidence',run_id=ctx['run_id'],context=execution.reference,execution_consumed=execution.consumed,
  decision_lock=ctx['inputs']['lock'],choice=ctx['inputs']['choice'],inputs=ctx['inputs'],core=core,environment=environment)


def perform(execution):
 _,x,_=_modules();execution.verify_pins();environment=execution.environment();core,calls=calculate(execution)
 execution.budget.guard();execution.verify_pins();execution.markers();body=wrap(execution,core,environment)
 names=execution.context['expected_outputs'];need(len(names)==1 and names[0].endswith('/evidence.json'),'Fixed evidence-only output vocabulary')
 written=x.exclusive(local(names[0]),body);ref=dict(path=names[0],sha256=written['sha256'])
 return execution.finish({ref['path']:ref['sha256']},ref,native_prediction_count=calls,labels_loaded=ROLE=='metric_oracle')


def main(argv=None):
 try:path,issued=bootstrap(argv)
 except SystemExit as error:return error.code
 except BaseException as error:
  print('STOP fixed '+ROLE+': '+type(error).__name__,file=sys.stderr);return 1
 execution=None
 try:
  sys.path.insert(0,str(ROOT));w,_,_=_modules()
  execution=w.begin_role(path,issued,ROLE,ENTRY_MONOTONIC);perform(execution);return 0
 except BaseException as error:
  if execution is not None:execution.fail(error)
  print('STOP fixed '+ROLE+': '+type(error).__name__,file=sys.stderr);return 1

def saved_npz(execution,descriptor,day):
 """Preflight exact seven numeric .npy members/header/payload BEFORE np.load."""
 import ast,struct,zipfile
 import numpy as np
 _,_,h=_modules();h.keys(descriptor,{'artifact','model','rows','queries','scoring_prefix','feature_names'},'Saved descriptor')
 need(type(descriptor['queries']) is int and descriptor['queries']==day['query_count'] and type(descriptor['rows']) is int and descriptor['rows']==day['candidate_count'],'Saved descriptor counts')
 qn,n=descriptor['queries'],descriptor['rows'];h.integer(qn,0,2000,'NPZ Q');h.integer(n,0,440000,'NPZ C')
 expected=dict(query_ids=('<U64',qn),user_ids=('<i8',qn),anchors=('<i8',qn),calendar_maturity=('|b1',qn),group=('<i4',n),items=('<i8',n),scores=('<f8',n))
 ref=descriptor['artifact'];h.ref(ref);retain(execution,{ref['path']:ref['sha256']});path=local(ref['path']);execution.budget.guard()
 with zipfile.ZipFile(path) as archive:
  infos=archive.infolist();need(len(infos)==7 and {i.filename for i in infos}=={k+'.npy' for k in expected},'Exact unique seven NPZ members')
  for info in infos:
   execution.budget.guard();need(info.compress_type in {zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED} and not info.flag_bits&1,'Supported unencrypted NPZ compression')
   key=info.filename[:-4];dtype,count=expected[key]
   with archive.open(info) as stream:
    need(stream.read(6)==b'\x93NUMPY','NPY magic required');version=stream.read(2);need(version in {b'\x01\x00',b'\x02\x00'},'Supported NPY1/2 version')
    size=2 if version==b'\x01\x00' else 4;length_bytes=stream.read(size);need(len(length_bytes)==size,'Complete NPY header length')
    length=int.from_bytes(length_bytes,'little');need(0<length<=4096,'Bounded NPY header BEFORE allocation');raw=stream.read(length);need(len(raw)==length,'Complete NPY header')
    header=ast.literal_eval(raw.decode('latin1'));need(type(header) is dict and set(header)=={'descr','fortran_order','shape'},'Exact simple NPY header')
    need(type(header['descr']) is str and header['descr']==dtype and header['fortran_order'] is False and type(header['shape']) is tuple and len(header['shape'])==1 and type(header['shape'][0]) is int and header['shape'][0]==count,'Exact NPY dtype/order/bounded shape BEFORE allocation')
    need(info.file_size==6+2+size+length+count*np.dtype(dtype).itemsize,'NPY payload size differs from original shape')
 execution.budget.guard()
 with np.load(path,allow_pickle=False) as archive:arrays={key:archive[key] for key in expected}
 for key,(dtype,count) in expected.items():need(type(arrays[key]) is np.ndarray and arrays[key].dtype==np.dtype(dtype) and arrays[key].shape==(count,),'NPZ loaded typed shape differs')
 from datetime import datetime,timedelta
 epoch=datetime(1970,1,1);queries=[]
 for q,u,t in zip(arrays['query_ids'],arrays['user_ids'],arrays['anchors']):
  q=str(q);need(len(q)==64 and re.fullmatch('[0-9a-f]{64}',q) is not None,'Exact hashed query ID in saved NPZ')
  queries.append((q,int(u),epoch+timedelta(microseconds=int(t))))
 need(np.isfinite(arrays['scores']).all(),'Saved finite raw scores required');execution.budget.guard()
 return dict(artifact=ref,model=descriptor['model'],feature_names=descriptor['feature_names'],queries=queries,calendar_maturity=arrays['calendar_maturity'],group=arrays['group'],items=arrays['items'],scores=arrays['scores'])


def prediction_days(execution,lock,source):
 _,_,h=_modules();body=execution.input_json('prediction_manifest');ctx=execution.context
 h.keys(body,{'version','scope','run_id','decision_lock','choice','source_acceptance','source_manifest','created_at','days','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'},'Prediction manifest')
 need(type(body['version']) is int and body['version']==1 and body['scope']=='unaccepted_reserved_predictions' and body['run_id']==ctx['run_id'],'Prediction original scope')
 for key in ['decision_lock','choice','source_acceptance','source_manifest']:need(body[key]==ctx['inputs']['lock' if key=='decision_lock' else key],'Prediction original input ref')
 need(body['labels_loaded'] is False and type(body['fit_attempt_count']) is int and body['fit_attempt_count']==0 and type(body['native_prediction_count']) is int and body['native_prediction_count']>=0 and type(body['environment']) is dict,'Prediction original work/environment')
 need(h.utc(body['created_at'])>=h.utc(lock['sealed_at']),'Prediction physical seal order')
 need(type(body['days']) is list and len(body['days'])==7,'Prediction whole calendar')
 outputs={};prefix=ctx['inputs']['prediction_manifest']['path'].rsplit('/',1)[0]
 for day,original in zip(body['days'],source['days']):
  h.keys(day,set(original)|{'predictions'},'Prediction day');need({k:day[k] for k in original}==original,'Prediction source day differs')
  h.keys(day['predictions'],{'B','W'},'Prediction B/W descriptors')
  for side,descriptor in day['predictions'].items():
   h.keys(descriptor,{'artifact','model','rows','queries','scoring_prefix','feature_names'},'Prediction descriptor');h.ref(descriptor['artifact'])
   need(descriptor['model']==lock['models'][side]['model'] and descriptor['feature_names']==lock['models'][side]['feature_names'] and type(descriptor['scoring_prefix']) is int and descriptor['scoring_prefix']==300,'Prediction model/schema/prefix')
   need(type(descriptor['rows']) is int and descriptor['rows']==day['candidate_count'] and type(descriptor['queries']) is int and descriptor['queries']==day['query_count'],'Prediction descriptor physical counts')
   stem='B' if lock['choice']=='B' else side;need(descriptor['artifact']['path']==prefix+'/day-'+day['anchor'][8:10]+'/'+stem+'.npz','Prediction fixed NPZ destination')
   ref=descriptor['artifact'];need(ref['path'] not in outputs or outputs[ref['path']]==ref['sha256'],'Prediction output ref conflict');outputs[ref['path']]=ref['sha256']
  if lock['choice']=='B':need(day['predictions']['B']==day['predictions']['W'],'Exact W=B prediction reuse')
 calls=sum(d['candidate_count']>0 for d in body['days'])*(1 if lock['choice']=='B' else 2)
 need(body['native_prediction_count']==calls and body['outputs']==outputs,'Prediction full output/nativecall map differs');retain(execution,outputs)
 receipt=execution.input_json('prediction_receipt');expected=dict(outputs);expected[ctx['inputs']['prediction_manifest']['path']]=ctx['inputs']['prediction_manifest']['sha256']
 need(receipt['status']=='role_complete_unaccepted' and receipt['scope']=='reserved_reporting_predictions' and receipt['run_id']==ctx['run_id'] and receipt['role']=='predictions' and receipt['outputs']==expected,'Prediction producer receipt differs')
 need(receipt['inputs']=={k:ctx['inputs'][k] for k in ['lock','choice','source_acceptance','source_manifest']} and receipt['labels_loaded'] is False and type(receipt['fit_attempt_count']) is int and receipt['fit_attempt_count']==0 and type(receipt['native_prediction_count']) is int and receipt['native_prediction_count']==calls,'Prediction receipt work/input binding')
 return body['days'],calls

def utc_now():
 from datetime import datetime,timezone
 return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def source_saved_domain(execution,con,day,saved):
 import numpy as np
 load_day(execution,con,day,'heldout_metric_source');guard=execution.budget.guard
 qrows=con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM heldout_metric_source_queries ORDER BY query_id').fetchall();guard()
 need(len(qrows)==day['query_count'],'Metric accepted all-Q count differs')
 queries=[tuple(q[:3]) for q in qrows];calendar=np.asarray([q[3] for q in qrows],dtype=np.bool_)
 for side in ('B','W'):need(saved[side]['queries']==queries and np.array_equal(saved[side]['calendar_maturity'],calendar),'Metric saved/source Q domain differs')
 con.execute('CREATE OR REPLACE TEMP TABLE metric_transport_q AS SELECT query_id,row_number() OVER(ORDER BY query_id)-1 g FROM heldout_metric_source_queries');guard()
 need(con.execute('SELECT count(*) FROM heldout_metric_source_candidates c WHERE NOT EXISTS(SELECT 1 FROM metric_transport_q q WHERE q.query_id=c.query_id)').fetchone()[0]==0,'Metric source orphan C');guard()
 con.execute('SELECT q.g,c.product_id FROM heldout_metric_source_candidates c JOIN metric_transport_q q USING(query_id) ORDER BY q.g,c.product_id')
 offset=0;previous=None
 while True:
  guard();rows=con.fetchmany(65536)
  if not rows:break
  for group,item in rows:
   need(type(group) is int and type(item) is int and -2**63<=item<2**63 and (previous is None or (group,item)>previous),'Exact unique metric source C keys')
   need(offset<day['candidate_count'],'Metric source C overrun')
   for side in ('B','W'):need(int(saved[side]['group'][offset])==group and int(saved[side]['items'][offset])==item,'Metric saved/source C domain differs')
   previous=(group,item);offset+=1
 need(offset==day['candidate_count'],'Metric complete source C domain differs');guard()


def compare_private_rankings(execution,reference,expected,core):
 # No IDs or targets escape this transport comparison into public evidence.
 rows=0
 with local(reference['path']).open('rb') as stream:
  for period in ('confirmation25_reporting_only','final26_31_frozen'):
   for side in ('B','W'):
    for row in expected[period][side]:
     execution.budget.guard();raw=stream.readline(64*2**20+1);need(raw and len(raw)<=64*2**20,'Bounded complete private ranking row required')
     actual=strict_json(raw);gold=dict(period=period,role=side,query_id=row['query_id'],user_id=row['user_id'],ranked_items=list(row['ordered']),targets=sorted(row['targets']),mature=True)
     core.compare(actual,gold,'private-ranking');rows+=1
  execution.budget.guard();need(not stream.read(1),'Private ranking has extra rows')
 return rows


def calculate(execution):
 from tests.oracles import heldout_metric_audit as core
 _,_,h=_modules();ctx=execution.context;lock=execution.input_json('lock');choice=execution.input_json('choice');h.validate_lock(lock,authenticated_choice=choice)
 source=source_manifest(execution,lock);source_acceptance=execution.input_json('source_acceptance')
 inventory=execution.input_json('prediction_inventory');h.validate_prediction_inventory(inventory,lock,authenticated_source=dict(acceptance=ctx['inputs']['source_acceptance'],days=source['days']))
 retain(execution,{inventory[k]['path']:inventory[k]['sha256'] for k in ['output_verification','lifetime_receipt']})
 prediction_seal=execution.input_json('prediction_acceptance');target_policy=execution.input_json('target_policy');target_seal=parsed_ref(execution,ctx['authorities']['target_execution'])
 need(prediction_seal['approved'] is True and prediction_seal['scope']=='reviewed_all_reserved_predictions_before_targets' and prediction_seal['inventory']==ctx['inputs']['prediction_inventory'] and prediction_seal['run_id']==ctx['run_id'],'Metric original prediction acceptance')
 h.keys(target_policy,{'prediction_acceptance','prediction_inventory_sha256','decision_lock_sha256','periods','no_adaptation','earliest_opened_at'},'Prospective target policy')
 authenticated=dict(reference=ctx['inputs']['prediction_acceptance'],inventory_sha256=h.digest(inventory),decision_lock_sha256=h.digest(lock))
 need(target_seal['approved'] is True and target_seal['scope']=='report_only_reserved_fullY' and target_seal['run_id']==ctx['run_id'] and target_seal['target_policy']==ctx['inputs']['target_policy'],'Metric original target execution')
 need(target_policy['earliest_opened_at']==prediction_seal['sealed_at'] and target_policy['prediction_acceptance']==authenticated['reference'] and target_policy['prediction_inventory_sha256']==authenticated['inventory_sha256'] and target_policy['decision_lock_sha256']==authenticated['decision_lock_sha256'] and target_policy['periods']==['confirmation25_reporting_only','final26_31_frozen'] and target_policy['no_adaptation'] is True,'Metric target policy detached')
 evaluation=execution.input_json('evaluation_manifest')
 fields={'version','scope','run_id','decision_lock','choice','source_acceptance','source_manifest','prediction_acceptance','prediction_inventory','target_execution','target_policy','actual_target_intent','target_stage_opened_at','target_stage_started_monotonic','fullY_started_at','fullY_started_monotonic','periods','private_outputs','outputs','labels_loaded','fit_attempt_count','native_prediction_count','environment'}
 h.keys(evaluation,fields,'Reserved evaluation manifest');need(type(evaluation['version']) is int and evaluation['version']==1 and evaluation['scope']=='unaccepted_reserved_fullY_reporting' and evaluation['run_id']==ctx['run_id'],'Metric evaluation original scope')
 for key in ['decision_lock','choice','source_acceptance','source_manifest','prediction_acceptance','prediction_inventory','target_policy']:need(evaluation[key]==ctx['inputs']['lock' if key=='decision_lock' else key],'Evaluation original input ref')
 need(evaluation['target_execution']==ctx['authorities']['target_execution'],'Evaluation target execution ref')
 intent=evaluation['actual_target_intent'];h.validate_target_intent(intent,lock,inventory,authenticated_prediction_acceptance=authenticated)
 need(intent['opened_at']==evaluation['target_stage_opened_at'] and h.utc(intent['opened_at'])>max(h.utc(prediction_seal['sealed_at']),h.utc(target_seal['sealed_at'])),'Actual producer target admission chronology')
 need(h.utc(evaluation['fullY_started_at'])>=h.utc(evaluation['target_stage_opened_at']),'Actual producer fullY UTC chronology')
 for key in ['target_stage_started_monotonic','fullY_started_monotonic']:need(type(evaluation[key]) in (int,float) and math.isfinite(evaluation[key]) and evaluation[key]>=0,'Known producer target clocks')
 need(evaluation['fullY_started_monotonic']>=evaluation['target_stage_started_monotonic'],'Actual producer fullY monotonic chronology')
 need(evaluation['labels_loaded'] is True and type(evaluation['fit_attempt_count']) is int and evaluation['fit_attempt_count']==0 and type(evaluation['native_prediction_count']) is int and evaluation['native_prediction_count']==0 and type(evaluation['environment']) is dict,'Evaluation actual work/environment state')
 h.keys(evaluation['private_outputs'],{'targets','rankings'},'Private evaluation outputs');prefix=ctx['inputs']['evaluation_manifest']['path'].rsplit('/',1)[0];outputs={}
 for key,name in [('targets','full-targets.parquet'),('rankings','private-rankings.jsonl')]:
  ref=evaluation['private_outputs'][key];h.ref(ref);need(ref['path']==prefix+'/'+name,'Fixed private output destination');outputs[ref['path']]=ref['sha256']
 need(evaluation['outputs']==outputs,'Exact evaluation private output map');retain(execution,outputs)
 receipt=execution.input_json('evaluation_receipt');expected=dict(outputs);expected[ctx['inputs']['evaluation_manifest']['path']]=ctx['inputs']['evaluation_manifest']['sha256']
 need(receipt['status']=='role_complete_unaccepted' and receipt['scope']=='reserved_reporting_targets_evaluation' and receipt['role']=='targets_evaluation' and receipt['run_id']==ctx['run_id'] and receipt['outputs']==expected,'Evaluation producer receipt')
 need(receipt['inputs']=={k:ctx['inputs'][k] for k in ['lock','choice','source_acceptance','source_manifest','prediction_acceptance','prediction_inventory','target_policy']} and receipt['labels_loaded'] is True and type(receipt['fit_attempt_count']) is int and receipt['fit_attempt_count']==0 and type(receipt['native_prediction_count']) is int and receipt['native_prediction_count']==0,'Evaluation receipt original input/work state')
 con=scratch=None;primary=None;days=[];timing={}
 try:
  con,scratch=open_connection(execution,owner_identity(execution)['source_inputs']['source'])
  # All seven accepted saved score domains must be loaded before target artifacts.
  for day in inventory['days']:
   saved={side:saved_npz(execution,day['predictions'][side],day) for side in ('B','W')};source_saved_domain(execution,con,day,saved)
   days.append(dict(anchor=day['anchor'],queries=saved['B']['queries'],calendar_maturity=saved['B']['calendar_maturity'],group=saved['B']['group'],items=saved['B']['items'],scores={s:saved[s]['scores'] for s in ('B','W')}))
  core.snapshot_days(days,execution.budget.guard)
  execution.budget.guard();timing['oracle_target_stage_opened_at']=utc_now();timing['oracle_target_stage_started_monotonic']=time.monotonic()
  need(h.utc(timing['oracle_target_stage_opened_at'])>max(h.utc(prediction_seal['sealed_at']),h.utc(target_seal['sealed_at'])),'Actual metric target opening must follow both seals')
  target_ref=evaluation['private_outputs']['targets'];path=str(local(target_ref['path'])).replace("'","''")
  con.execute("CREATE TEMP VIEW metric_produced_targets AS SELECT * FROM read_parquet('"+path+"')");execution.budget.guard()
  need([tuple(r[:2]) for r in con.execute('DESCRIBE metric_produced_targets').fetchall()]==[('query_id','VARCHAR'),('product_id','BIGINT')],'Exact produced positive-target schema')
  count,distinct,nulls=con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)),count(*)FILTER(WHERE query_id IS NULL OR product_id IS NULL) FROM metric_produced_targets').fetchone();need(count==distinct and not nulls and count<=2000000,'Exact bounded produced positive-target keys')
  full={q[0]:set() for day in days for q in day['queries']};con.execute('SELECT query_id,product_id FROM metric_produced_targets')
  while True:
   execution.budget.guard();rows=con.fetchmany(65536)
   if not rows:break
   for qid,item in rows:need(type(qid) is str and qid in full and type(item) is int and -2**63<=item<2**63,'Produced target outside source Q/exact int64');full[qid].add(item)
  class Observed:
   def execute(self,sql,*args,**kwargs):
    if 'SELECT q.query_id,e.product_id FROM heldout_raw_events e' in sql:
     need('oracle_fullY_started_at' not in timing,'Original independent fullY SQL cannot repeat')
     execution.budget.guard();timing['oracle_fullY_started_at']=utc_now();timing['oracle_fullY_started_monotonic']=time.monotonic()
    return con.execute(sql,*args,**kwargs)
   def __getattr__(self,name):return getattr(con,name)
  result=core.audit_windows(Observed(),days=days,produced_targets=full,produced_periods=evaluation['periods'],check=execution.budget.guard)
  ranking_rows=compare_private_rankings(execution,evaluation['private_outputs']['rankings'],result['private_rankings'],core)
  need('oracle_fullY_started_at' in timing and timing['oracle_fullY_started_monotonic']>=timing['oracle_target_stage_started_monotonic'],'Observed independent fullY query stage missing')
  result.pop('private_targets');result.pop('private_rankings');result.update(timing);result['private_ranking_rows_checked']=ranking_rows
  return result,0
 except BaseException as error:primary=error;raise
 finally:close_resources(execution,con,scratch,primary)


if __name__=='__main__':raise SystemExit(main())
