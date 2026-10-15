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

ROLE='prediction_oracle'
ENTRY='tests/oracles/heldout_prediction_worker.py'
CORE='tests/oracles/heldout_prediction_audit.py'
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

def calculate(execution):
 from tests.oracles import heldout_prediction_audit as core
 from catboost import CatBoostClassifier
 _,_,h=_modules();lock=execution.input_json('lock');choice=execution.input_json('choice');h.validate_lock(lock,authenticated_choice=choice)
 source=source_manifest(execution,lock);days,expected_calls=prediction_days(execution,lock,source)
 retain(execution,{s['model']['path']:s['model']['sha256'] for s in lock['models'].values()})
 con=scratch=None;primary=None;models=[];reports=[];calls=0
 try:
  con,scratch=open_connection(execution)
  def loader(reference):
   execution.budget.guard();model=CatBoostClassifier();model.load_model(str(local(reference['path'])));models.append(model);execution.budget.guard();return model
  for day in days:
   load_day(execution,con,day,'heldout_prediction');con.execute('DROP TABLE IF EXISTS heldout_prediction_oracle_q');execution.budget.guard()
   saved={side:saved_npz(execution,day['predictions'][side],day) for side in ('B','W')}
   result=core.audit_day(con,day['anchor'],day,choice=lock['choice'],models=lock['models'],produced=saved,load_model=loader,check=execution.budget.guard)
   calls+=result['native_prediction_count'];result.pop('private_replayed_scores');reports.append(result);models.clear();del saved
  need(calls==expected_calls,'Independent actual native call count differs')
  return dict(status='independent_all_seven_scores_match_pending_owner_acceptance',days=reports,native_prediction_count=calls,fit_attempt_count=0,labels_loaded=False,proof_scope='all7_independent_matrix_native_scores_rank_order_with_external_byte_lifetime_authority'),calls
 except BaseException as error:primary=error;raise
 finally:close_resources(execution,con,scratch,primary,models)


if __name__=='__main__':raise SystemExit(main())
