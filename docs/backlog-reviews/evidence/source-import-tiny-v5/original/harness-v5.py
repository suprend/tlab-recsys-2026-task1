"""TMP-only eight-row source-import integration; execution requires root review.

No real source, global process inventory, acceptance or fit. Importing this file
never creates fixtures, opens native DBs or launches a process.
"""
import resource
import time
ENTRY_MONOTONIC=time.monotonic()
from copy import deepcopy
import argparse
import csv
from decimal import Decimal
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tomllib
from types import ModuleType

PROJECT=Path('/Users/mdpospelov/tlab-recsys-2026')
FIXTURE_ROOT=Path('/tmp/tlab source import integration 20261015')
TRUSTED_VENV=PROJECT/'.venv'
SOURCES={
 'scripts/run_source_import.py':(Path('/tmp/tlab-source-import-owner-v8-draft/scripts/run_source_import.py'),'5df50bb2577b4515c5d80a5eaf4a6f2bf18abe344039d1cd22a51a872e1c7653'),
 'scripts/source_import.py':(PROJECT/'scripts/source_import.py','7d7ed34b336294bd18d822b9798a7b644f45dc72f8c1f6edeb6d518b55284236'),
 'uv.lock':(PROJECT/'uv.lock','4675021f74063889ffb596325b9e608a3a5776a29f967d052b86923e40485eab'),
 'pyproject.toml':(PROJECT/'pyproject.toml','416cef16f91689db9f244c9c178c86bebb0f7e8140b2081372bd2324148a816a')}
LIMITS=dict(cpu_seconds=200,wall_seconds=240,parent_rss_bytes=2**30,job_rss_bytes=8*2**30,
 command_cpu_seconds=70,command_wall_seconds=70,cleanup_wall_seconds=10,log_bytes=2**20)
OWNER_RESOURCES=dict(cpu_seconds=60,wall_seconds=60,parent_rss_bytes=2**30,worker_rss_bytes=7*2**30,job_rss_bytes=8*2**30,
 threads=2,engine_memory='2GB',spill_bytes=8*2**30,parent_launch_cpu_reserve=15,final_cpu_reserve=2,cleanup_wall_reserve=10,log_bytes=2**20)
BIG=2**60
ROWS=[['2019-10-01 00:00:00 UTC','view',str(BIG),'9','electronics.phone','acme, labs','0',str(BIG),''],
 ['2019-10-01 00:00:00 UTC','view',str(BIG),'9','electronics.phone','acme, labs','0',str(BIG),''],
 ['2019-10-01 00:00:00 UTC','cart',str(BIG+1),'','',' "x" ','9999999999.99',str(BIG),'s'],
 ['2019-10-31 23:59:59 UTC','purchase','','0','electronics.phone',' spaced ','-1.20','','']]
FIELDS=['event_time','event_type','product_id','category_id','category_code','brand','price','user_id','user_session']
TYPES=['TIMESTAMP','VARCHAR','BIGINT','BIGINT','VARCHAR','VARCHAR','DECIMAL(12,2)','BIGINT','VARCHAR']
_HANDLES=[]
_ACTIVE_SOURCE_OWNER=None
SHARED_SUPERVISOR=(Path('/tmp/tlab-heldout-harness-processes.py'),'449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232')
# Root-selected canonical V6 dependency; this candidate still requires focused review and root launch.


def need(value,message):
 if not value:raise ValueError(message)
def canonical(body):return json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=False)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def usage(kind=resource.RUSAGE_SELF):
 r=resource.getrusage(kind);return r.ru_utime+r.ru_stime,int(r.ru_maxrss)
def cpu():return usage()[0]+usage(resource.RUSAGE_CHILDREN)[0]
def exclusive(path,body):
 raw=(canonical(body)+'\n').encode();fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 return dict(path=str(path),sha256=digest(raw))
def read(path):return json.loads(Path(path).read_bytes())
def read_snapshot(path):
 with Path(path).open('rb') as stream:raw=stream.read(2**20+1)
 need(len(raw)<=2**20,'Bounded original receipt snapshot required')
 return json.loads(raw),dict(path=str(path),sha256=digest(raw))
def receipt_pins(refs):
 for reference in refs:need(hashed(reference['path'],guarded)==reference['sha256'],'Original validated receipt bytes changed')
def positive_unchanged(stable,claim):
 need(snapshot(FIXTURE_ROOT/'artifacts/source-import-runs/tiny-positive')==stable and hashed(FIXTURE_ROOT/'artifacts/source-import-owner/claims/tiny-positive.json',guarded)==claim,'Original positive source outputs/claim changed during terminal stages')

def hashed(path,check):
 h=hashlib.sha256();check()
 with Path(path).open('rb') as stream:
  while data:=stream.read(2**20):check();h.update(data)
 check();return h.hexdigest()
def guarded():
 if time.monotonic()-ENTRY_MONOTONIC>LIMITS['wall_seconds']-10:raise TimeoutError('Original whole-harness wall budget')
 if cpu()>LIMITS['cpu_seconds']-5:raise TimeoutError('Original whole-harness CPU budget')
 if usage()[1]>LIMITS['parent_rss_bytes']:raise MemoryError('Harness parent peak RSS exceeded')
def compiled(path,expected):
 with Path(path).open('rb') as stream:raw=stream.read(2**20+1)
 need(len(raw)<=2**20 and digest(raw)==expected,'Original copied source differs')
 module=ModuleType('reviewed_'+Path(path).stem);module.__file__=str(path);sys.modules[module.__name__]=module;exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__);return module


def copies(check):
 for name,(source,expected) in SOURCES.items():
  need(hashed(source,check)==expected,'Original harness dependency changed');need(hashed(FIXTURE_ROOT/name,check)==expected,'Copied harness dependency changed')

def fixture_identity(positive_reference):
 need(type(positive_reference) is dict and set(positive_reference)=={'path','sha256'} and positive_reference['path']==str(FIXTURE_ROOT/'tiny-positive-request.json'),'Original positive fixture request reference required')
 positive,original=read_snapshot(positive_reference['path']);need(original['sha256']==positive_reference['sha256'],'Original positive fixture request changed')
 need(positive['archive']=='data/raw/tiny.csv.gz' and positive['profile']['scope']=='synthetic_typed9_import_fixture' and positive['profile']['expected_rows']==4,'Exact original four-row synthetic fixture required')
 expected=positive['profile'];need(type(expected['compressed_bytes']) is int and 0<expected['compressed_bytes']<=2048,'Bounded original fixture size required')
 archive=FIXTURE_ROOT/positive['archive']
 for path in [FIXTURE_ROOT/'data',FIXTURE_ROOT/'data/raw',archive]:need(not path.is_symlink(),'Fixture path symlinks forbidden')
 need(archive.is_file() and archive.stat().st_size==expected['compressed_bytes'],'Original physical fixture byte count changed')
 need(hashed(archive,guarded)==expected['compressed_sha256'],'Original physical fixture SHA changed')
 return dict(path=str(archive),sha256=expected['compressed_sha256'],bytes=expected['compressed_bytes'])


def private_closure(expected_harness_sha,refs,context):
 for path,expected in [(Path(__file__),expected_harness_sha),(FIXTURE_ROOT/'.review/source-harness.py',expected_harness_sha),(SHARED_SUPERVISOR[0],SHARED_SUPERVISOR[1]),(FIXTURE_ROOT/'.review/supervisor.py',SHARED_SUPERVISOR[1])]:
  need(hashed(path,guarded)==expected,'Original driver/supervisor execution closure changed')
 for reference in [*refs.values(),context]:need(hashed(reference['path'],guarded)==reference['sha256'],'Original private request/context changed')
 fixture_identity(refs['tiny-positive'])


def consume_root():
 guarded();need(not FIXTURE_ROOT.exists() and not FIXTURE_ROOT.is_symlink(),'Fixed tiny integration root already consumed')
 FIXTURE_ROOT.mkdir(mode=0o700);exclusive(FIXTURE_ROOT/'harness.consumed.json',dict(version=1,scope='one_reviewed_eight_row_source_import_harness',started_monotonic=ENTRY_MONOTONIC,limits=LIMITS,owners=3,workers_at_most=2,source_acceptance_issued=False))


def prepare(expected_harness_sha):
 need(FIXTURE_ROOT.is_dir() and (FIXTURE_ROOT/'harness.consumed.json').is_file(),'Original fixed root consumption required')
 for name,(source,expected) in SOURCES.items():
  with source.open('rb') as input_stream:raw=input_stream.read(2**20+1)
  need(len(raw)<=2**20 and digest(raw)==expected,'Original copied code differs');path=FIXTURE_ROOT/name;path.parent.mkdir(parents=True,mode=0o700,exist_ok=True);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 review=FIXTURE_ROOT/'.review';review.mkdir(mode=0o700)
 for source,name,expected in [(Path(__file__),'source-harness.py',expected_harness_sha),(SHARED_SUPERVISOR[0],'supervisor.py',SHARED_SUPERVISOR[1])]:
  with source.open('rb') as input_stream:raw=input_stream.read(2**20+1)
  need(len(raw)<=2**20 and digest(raw)==expected,'Original reviewed driver/supervisor bytes differ');fd=os.open(review/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 need(TRUSTED_VENV.is_dir(),'Trusted prepared venv required');(FIXTURE_ROOT/'.venv').symlink_to(TRUSTED_VENV,target_is_directory=True)
 kernel=compiled(FIXTURE_ROOT/'scripts/source_import.py',SOURCES['scripts/source_import.py'][1]);stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(FIELDS);writer.writerows(ROWS);raw=stream.getvalue().encode();compressed=gzip.compress(raw,mtime=0);need(len(compressed)<=2048,'Bounded tiny gzip required')
 path=FIXTURE_ROOT/'data/raw/tiny.csv.gz';path.parent.mkdir(parents=True,mode=0o700);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as output:output.write(compressed);output.flush();os.fsync(output.fileno())
 profile=deepcopy(kernel.PRODUCTION_PROFILE);profile.update(scope='synthetic_typed9_import_fixture',compressed_sha256=digest(compressed),compressed_bytes=len(compressed),uncompressed_bytes=len(raw),expected_rows=4);kernel.validate_profile(profile)
 refs={}
 for eid,bad in [('tiny-positive',False),('tiny-wrong-sha',True)]:
  current=deepcopy(profile)
  if bad:current['compressed_sha256']='0'*64
  request=dict(version=1,scope='externally_reviewed_typed9_source_import',execution_id=eid,archive='data/raw/tiny.csv.gz',profile=current,
   output_directory='artifacts/source-import-runs/'+eid,resources=OWNER_RESOURCES,fingerprints={name:v[1] for name,v in SOURCES.items()})
  refs[eid]=exclusive(FIXTURE_ROOT/(eid+'-request.json'),request)
 copies(guarded);return refs


def owner_argv(reference):return [str(FIXTURE_ROOT/'.venv/bin/python'),'-I','-B',str(FIXTURE_ROOT/'scripts/run_source_import.py'),'--request',Path(reference['path']).name,'--expected-request-sha',reference['sha256']]
def snapshot(directory):
 result={}
 for path in sorted(Path(directory).rglob('*')):
  need(not path.is_symlink(),'Unexpected output symlink')
  if path.is_file():result[str(path.relative_to(directory))]=hashed(path,guarded)
 return result

def positive_proof():
 directory=FIXTURE_ROOT/'artifacts/source-import-runs/tiny-positive';report=read(directory/'report.json');evidence=read(directory/'kernel/import-evidence.json')
 need(report['status']=='completed_source_import_pending_external_source_acceptance' and report['source_acceptance_issued'] is False and report['fit_attempt_count']==0 and report['labels_created'] is False,'Positive owner scope differs')
 for name in ['report.failed.json','kernel/report.failed.json','worker.log.cleanup-failed.json','worker.log.descendants-failed.json']:need(not (directory/name).exists(),'Known failed positive source import')
 need(evidence['summary']['rows']==4 and evidence['csv']['all_gzip_members_EOF_CRC_ISIZE_checked'] is True and evidence['validated_csv']['native_reader_used'] is True,'Original typed4/canonical evidence differs')
 for filename,key in [('source.csv.gz','source'),('source.csv','csv'),('validated.csv','validated_csv'),('events.duckdb','database')]:
  path=directory/'kernel'/filename;need(hashed(path,guarded)==evidence[key]['sha256'] and path.stat().st_size==evidence[key]['bytes'],'Original canonical/source/DB bytes differ')
 import duckdb
 lock={p['name']:p.get('version') for p in tomllib.loads((FIXTURE_ROOT/'uv.lock').read_text())['package']};need(duckdb.__version__==lock['duckdb'],'Harness loaded DuckDB differs from copied lock')
 con=duckdb.connect(str(directory/'kernel/events.duckdb'),read_only=True,config={'threads':'2'})
 try:
  need(con.execute('SHOW TABLES').fetchall()==[('events',)],'Only the raw events table may exist')
  schema=[tuple(r[:2]) for r in con.execute('DESCRIBE events').fetchall()]
  literal=con.execute('SELECT * FROM events ORDER BY product_id NULLS LAST, event_type').fetchall()
 finally:con.close()
 expected=[(datetime(2019,10,1),'view',BIG,9,'electronics.phone','acme, labs',Decimal('0.00'),BIG,None)]*2+[(datetime(2019,10,1),'cart',BIG+1,None,None,' "x" ',Decimal('9999999999.99'),BIG,'s'),(datetime(2019,10,31,23,59,59),'purchase',None,0,'electronics.phone',' spaced ',Decimal('-1.20'),None,None)]
 need(schema==list(zip(FIELDS,TYPES)) and literal==expected,'Independent exact typed literals/raw bag differ');guarded()
 return dict(rows=4,exact_typed9=True,bigint_above_2pow53_exact=True,decimal_exact=True,metadata_strings_exact=True,duplicate_multiplicity=2,canonical_csv_verified=True,source_acceptance_issued=False)

def wrong_proof(*,positive_reference=None):
 directory=FIXTURE_ROOT/'artifacts/source-import-runs/tiny-wrong-sha';failed=read(directory/'report.failed.json');kernel=directory/'kernel'
 need(failed['status']=='failed_original_source_import' and failed['source_acceptance_issued'] is False and failed['unknown_owned_process_usage'] is False,'Wrong-SHA failure lifetime differs')
 kernel_failed=read(kernel/'report.failed.json')
 need(kernel_failed['status']=='failed_import_kernel' and kernel_failed['error_type']=='ValueError','Wrong-SHA proof requires the specific compressed-hash rejection, not an unrelated source failure')
 lines=(directory/'worker.log').read_text().splitlines()
 need(lines and lines[-1]=='ValueError: Original compressed SHA/size differs','Wrong-SHA worker did not report its expected compressed-hash rejection')
 fixture=fixture_identity(positive_reference);request=read(FIXTURE_ROOT/'tiny-wrong-sha-request.json')
 need(request['archive']=='data/raw/tiny.csv.gz' and request['profile']['scope']=='synthetic_typed9_import_fixture' and request['profile']['compressed_sha256']=='0'*64 and fixture['sha256']!='0'*64 and (kernel/'source.csv.gz').stat().st_size==fixture['bytes'] and hashed(kernel/'source.csv.gz',guarded)==fixture['sha256'],'Wrong-SHA original fixture/complete snapshot identity differs')
 need((kernel/'import.consumed.json').is_file() and (kernel/'report.failed.json').is_file() and (kernel/'source.csv.gz').is_file(),'Wrong-SHA consumption/partials missing')
 for name in ['events.duckdb','source.csv','validated.csv','import-evidence.json']:need(not (kernel/name).exists(),'Wrong-SHA crossed native/decompression admission')
 need(not (directory/'report.json').exists() and not (directory/'worker-receipt.json').exists(),'Wrong-SHA was promoted')
 return dict(wrong_compressed_sha_rejected=True,failed_before_native_DB=True,consumption_and_partial_snapshot_preserved=True,retry=False,source_acceptance_issued=False)



def active_handle_ids():
 values=[p.pid for p in _HANDLES]
 if _ACTIVE_SOURCE_OWNER is not None and _ACTIVE_SOURCE_OWNER.pid not in values:values.append(_ACTIVE_SOURCE_OWNER.pid)
 return values


def duplicate_proof(code):
 need(code==1,'Duplicate rejection must be the expected normal Python failure exit')
 lines=(FIXTURE_ROOT/'duplicate.log').read_text().splitlines()
 need(lines and lines[-1]=='ValueError: Existing import output cannot be reused','Duplicate request did not prove the expected once/output refusal')
 return dict(duplicate_claim_rejected=True,source_work_admitted=False)


def run_owner_case(reference,*,ordinal):
 """Mechanical driver wait only. The one shared outer supervisor owns all live
 resource/family observation; this function never invents another backend."""
 global _ACTIVE_SOURCE_OWNER
 need(ordinal in (1,2,3),'Exact three-case source-owner sequence required');need(_ACTIVE_SOURCE_OWNER is None and not _HANDLES,'Original source-owner handle still active');guarded();process=None;started=time.monotonic();deadline=started+LIMITS['command_wall_seconds'];before=usage(resource.RUSAGE_CHILDREN)[0]
 path=FIXTURE_ROOT/(['positive.log','duplicate.log','wrong-sha.log'][ordinal-1]);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as log:
  try:
   process=subprocess.Popen(owner_argv(reference),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=FIXTURE_ROOT);_ACTIVE_SOURCE_OWNER=process
   try:_HANDLES.append(process)
   except BaseException as registration_error:
    # The scalar already retains the actual handle without another allocation.
    # Best-effort list recovery keeps diagnostics compatible, but is not the
    # ownership guarantee if allocation itself continues to fail.
    try:
     if process not in _HANDLES:_HANDLES.insert(0,process)
    except BaseException as secondary:registration_error.add_note('Handle-list recovery: '+type(secondary).__name__)
    raise
   code=process.wait(timeout=max(.001,deadline-LIMITS['cleanup_wall_seconds']-time.monotonic()))
   actual=usage(resource.RUSAGE_CHILDREN)[0]-before;need(0<=actual<=LIMITS['command_cpu_seconds'],'Actual full-owner CPU allowance');guarded()
   need(path.stat().st_size<=LIMITS['log_bytes'],'Full owner log allowance')
   return dict(ordinal=ordinal,exit_code=code,reaped=True,actual_full_owner_inclusive_cpu_seconds=actual,external_started_monotonic=started,external_finished_monotonic=time.monotonic(),unknown_owned_process_usage=False)
  except BaseException as error:
   if process is not None and process.returncode is None:
    # An interrupt may land after STORE_FAST process but before the immediate
    # scalar registration. Recover that original local handle before cleanup.
    _ACTIVE_SOURCE_OWNER=process
    error.unknown_owned_process_usage=True
    # The reviewed outer supervisor independently tracks and cleans this whole
    # owned family. Retain the original handle and never promote this failure.
    for sig in (signal.SIGTERM,signal.SIGKILL):
     try:
      remaining=deadline-time.monotonic()
      if remaining<=0:raise TimeoutError('Original per-owner cleanup wall allowance exhausted')
      process.send_signal(sig);process.wait(timeout=min(5,remaining));break
     except BaseException as secondary:error.add_note('Driver direct-owner cleanup: '+type(secondary).__name__)
   raise
  finally:
   if process is not None and process.returncode is not None:
    if process in _HANDLES:_HANDLES.remove(process)
    if _ACTIVE_SOURCE_OWNER is process:_ACTIVE_SOURCE_OWNER=None


def driver(context_path,expected_context_sha):
 global ENTRY_MONOTONIC
 consumed=False
 try:
  raw=Path(context_path).read_bytes();need(len(raw)<=65536 and digest(raw)==expected_context_sha,'Original private driver context differs');context=json.loads(raw)
  need(set(context)=={'version','scope','owner_pid','entry','requests','limits','original_started_monotonic'} and type(context['version']) is int and context['version']==1 and context['scope']=='reviewed_eight_row_source_import_driver','Exact private driver context required')
  need(type(context['owner_pid']) is int and context['owner_pid']==os.getppid(),'Private driver requires its actual original supervisor parent')
  need(Path(context_path).resolve()==(FIXTURE_ROOT/'.review/driver-context.json').resolve() and Path(__file__).resolve()==(FIXTURE_ROOT/'.review/source-harness.py').resolve(),'Fixed original private driver paths required')
  need(context['entry']['path']==str(FIXTURE_ROOT/'.review/source-harness.py') and digest(Path(__file__).read_bytes())==context['entry']['sha256'],'Original executable driver changed')
  need(context['limits']==LIMITS and type(context['original_started_monotonic']) in (int,float) and context['original_started_monotonic']<=time.monotonic(),'Original finite harness limits/start required')
  ENTRY_MONOTONIC=context['original_started_monotonic'];refs=context['requests'];need(set(refs)=={'tiny-positive','tiny-wrong-sha'},'Exact original source-owner requests required')
  for eid,ref in refs.items():
   need(ref['path']==str(FIXTURE_ROOT/(eid+'-request.json')) and digest(Path(ref['path']).read_bytes())==ref['sha256'],'Original source-owner request changed')
  exclusive(FIXTURE_ROOT/'driver.consumed.json',dict(version=1,scope='consumed_exact_three_source_owner_cases',context=dict(path=str(context_path),sha256=expected_context_sha),retry=False));consumed=True
  records=[]
  private_closure(context['entry']['sha256'],refs,dict(path=str(context_path),sha256=expected_context_sha))
  positive=run_owner_case(refs['tiny-positive'],ordinal=1);records.append(positive);need(positive['exit_code']==0,'Positive owner did not exit0');proof=positive_proof();copies(guarded)
  original_report=read(FIXTURE_ROOT/'artifacts/source-import-runs/tiny-positive/report.json')
  need(positive['actual_full_owner_inclusive_cpu_seconds']+1e-9>=original_report['observed_owner_and_reaped_children_cpu_seconds'],'External owner reap must include its complete observed CPU')
  stable=snapshot(FIXTURE_ROOT/'artifacts/source-import-runs/tiny-positive');claim=hashed(FIXTURE_ROOT/'artifacts/source-import-owner/claims/tiny-positive.json',guarded)
  private_closure(context['entry']['sha256'],refs,dict(path=str(context_path),sha256=expected_context_sha))
  duplicate=run_owner_case(refs['tiny-positive'],ordinal=2);records.append(duplicate);duplicate_reason=duplicate_proof(duplicate['exit_code']);need(snapshot(FIXTURE_ROOT/'artifacts/source-import-runs/tiny-positive')==stable and hashed(FIXTURE_ROOT/'artifacts/source-import-owner/claims/tiny-positive.json',guarded)==claim,'Duplicate attempt changed accepted tiny outputs')
  private_closure(context['entry']['sha256'],refs,dict(path=str(context_path),sha256=expected_context_sha))
  wrong=run_owner_case(refs['tiny-wrong-sha'],ordinal=3);records.append(wrong);need(wrong['exit_code']==1,'Wrong compressed SHA did not produce its expected normal Python failure exit');badproof=wrong_proof(positive_reference=refs['tiny-positive']);copies(guarded)
  positive_unchanged(stable,claim)
  need(len(list(FIXTURE_ROOT.glob('artifacts/source-import-runs/*/worker.consumed.json')))==2,'Exactly two source worker contexts must be consumed');need(not active_handle_ids(),'No live original source-owner handle may remain');guarded()
  receipt=dict(version=1,status='tiny_driver_complete_pending_outer_full_exit',scope='exact_three_source_owner_cases',context=dict(path=str(context_path),sha256=expected_context_sha),source_acceptance_issued=False,actual_real_source_rows=0,synthetic_input_rows=8,owners=records,workers=2,fit_attempt_count=0,labels_created=False,positive=proof,duplicate_outputs_unchanged=True,duplicate_claim_rejected=duplicate_reason['duplicate_claim_rejected'],wrong_sha=badproof,
   observed_driver_and_children_cpu_seconds=cpu(),observed_driver_peak_rss_bytes=usage()[1],observed_reaped_children_peak_rss_bytes=usage(resource.RUSAGE_CHILDREN)[1],started_monotonic=ENTRY_MONOTONIC,finished_monotonic=time.monotonic(),limits=LIMITS)
  reference=exclusive(FIXTURE_ROOT/'driver-report.json',receipt);positive_unchanged(stable,claim);copies(guarded);private_closure(context['entry']['sha256'],refs,dict(path=str(context_path),sha256=expected_context_sha));need(hashed(FIXTURE_ROOT/'driver-report.json',guarded)==reference['sha256'],'Original driver report changed');guarded();return receipt
 except BaseException as error:
  if consumed:
   try:exclusive(FIXTURE_ROOT/'driver.failed.json',dict(version=1,status='failed_consumed_tiny_driver',error_type=type(error).__name__,unknown_owned_process_usage=getattr(error,'unknown_owned_process_usage',False),source_acceptance_issued=False,retry=False,active_handles=active_handle_ids()))
   except BaseException as secondary:error.add_note('Driver failure persistence: '+type(secondary).__name__)
  raise


def run(expected_harness_sha):
 need(sys.platform=='darwin' and os.uname().machine=='arm64' and sys.version_info[:2]==(3,12),'Reviewed target runtime required')
 need(digest(Path(__file__).read_bytes())==expected_harness_sha,'Original externally reviewed harness SHA required')
 need(usage(resource.RUSAGE_CHILDREN)==(0,0),'Fresh dedicated harness supervisor required');resource.setrlimit(resource.RLIMIT_CPU,(199,200));need(resource.getrlimit(resource.RLIMIT_CPU)==(199,200),'Harness CPU fence readback failed')
 consume_root()
 try:
  refs=prepare(expected_harness_sha);helper=compiled(FIXTURE_ROOT/'.review/supervisor.py',SHARED_SUPERVISOR[1])
  context=exclusive(FIXTURE_ROOT/'.review/driver-context.json',dict(version=1,scope='reviewed_eight_row_source_import_driver',owner_pid=os.getpid(),entry=dict(path=str(FIXTURE_ROOT/'.review/source-harness.py'),sha256=expected_harness_sha),requests=refs,limits=LIMITS,original_started_monotonic=ENTRY_MONOTONIC))
  private_closure(expected_harness_sha,refs,context)
  argv=[str(FIXTURE_ROOT/'.venv/bin/python'),'-I','-B',str(FIXTURE_ROOT/'.review/source-harness.py'),'--driver-context',context['path'],'--expected-context-sha',context['sha256']]
  result=helper.supervise(argv,FIXTURE_ROOT/'driver.log',started=ENTRY_MONOTONIC,cpu_seconds=LIMITS['cpu_seconds'],wall_seconds=LIMITS['wall_seconds'],rss_bytes=LIMITS['job_rss_bytes'],cwd=FIXTURE_ROOT)
  result=deepcopy(result);supervisor_reference=exclusive(FIXTURE_ROOT/'supervisor-report.json',result);receipt_pins([supervisor_reference])
  need(result['status']=='verified_normal_exit' and result['exit_code']==0 and result['reaped'] is True and result['unknown_active_work'] is False,'Reviewed outer supervision did not establish a known normal driver exit')
  receipt,driver_reference=read_snapshot(FIXTURE_ROOT/'driver-report.json');need(receipt['status']=='tiny_driver_complete_pending_outer_full_exit' and receipt['scope']=='exact_three_source_owner_cases' and receipt['synthetic_input_rows']==8 and receipt['actual_real_source_rows']==0 and receipt['workers']==2 and len(receipt['owners'])==3 and [v['exit_code'] for v in receipt['owners']]==[0,1,1] and all(v['reaped'] is True and v['unknown_owned_process_usage'] is False for v in receipt['owners']),'Exact known three-case driver ledger differs')
  need(receipt['source_acceptance_issued'] is False and receipt['fit_attempt_count']==0 and receipt['labels_created'] is False and receipt['positive']['exact_typed9'] is True and receipt['duplicate_outputs_unchanged'] is True and receipt['duplicate_claim_rejected'] is True and receipt['wrong_sha']['failed_before_native_DB'] is True and receipt['wrong_sha']['wrong_compressed_sha_rejected'] is True,'Tiny source proof/zero-fit scope differs')
  for name in ['driver.failed.json','harness.failed.json']:need(not (FIXTURE_ROOT/name).exists(),'Known failed tiny harness cannot complete')
  copies(guarded);private_closure(expected_harness_sha,refs,context);receipt_pins([supervisor_reference,driver_reference])
  report=dict(version=1,status='tiny_source_import_integration_complete_pending_harness_exit',source_acceptance_issued=False,driver_report=deepcopy(driver_reference),shared_supervisor=dict(path=str(SHARED_SUPERVISOR[0]),sha256=SHARED_SUPERVISOR[1]),supervisor_report=deepcopy(supervisor_reference),driver_ledger_verified=True,full_harness_exit_receipt_required=True,limits=LIMITS,fit_attempt_count=0,actual_real_source_rows=0)
  reference=exclusive(FIXTURE_ROOT/'harness-report.json',report);copies(guarded);private_closure(expected_harness_sha,refs,context);receipt_pins([supervisor_reference,driver_reference]);need(hashed(FIXTURE_ROOT/'harness-report.json',guarded)==reference['sha256'],'Original final harness receipt changed');guarded();return report
 except BaseException as error:
  try:exclusive(FIXTURE_ROOT/'harness.failed.json',dict(version=1,status='failed_consumed_tiny_import_harness',error_type=type(error).__name__,source_acceptance_issued=False,retry=False))
  except BaseException as secondary:error.add_note('Harness failure persistence: '+type(secondary).__name__)
  raise


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--run-reviewed-tiny',action='store_true');group.add_argument('--driver-context');parser.add_argument('--expected-harness-sha');parser.add_argument('--expected-context-sha');args=parser.parse_args()
 if args.run_reviewed_tiny:
  need(args.expected_harness_sha is not None and args.expected_context_sha is None,'Original reviewed harness acknowledgment required');run(args.expected_harness_sha)
 else:
  need(args.expected_context_sha is not None and args.expected_harness_sha is None,'Original parent-issued driver context required');driver(args.driver_context,args.expected_context_sha)
