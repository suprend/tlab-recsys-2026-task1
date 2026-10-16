"""Strict gzip/typed9/new-DB import kernel; caller owns execution authority/lifetime.

No CLI/download/retry/EDA/model/target/approval exists here. A new private work
root consumes one kernel attempt before paid source reads; full runtime admission
and external source acceptance are separate unfinished018 work.
"""
from copy import deepcopy
from contextlib import ExitStack
import csv
from datetime import datetime
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import re

FIELDS=('event_time','event_type','product_id','category_id','category_code','brand','price','user_id','user_session')
TYPES=('TIMESTAMP','VARCHAR','BIGINT','BIGINT','VARCHAR','VARCHAR','DECIMAL(12,2)','BIGINT','VARCHAR')
ACTIONS=('view','cart','purchase')
NULLABLE=FIELDS[2:]
TIME_FORMAT='%Y-%m-%d %H:%M:%S UTC'
PROFILE_KEYS={'version','scope','compressed_sha256','compressed_bytes','uncompressed_bytes','expected_rows','fields','types',
    'nullable_fields','start','end','actions','compression','encoding','empty_policy','max_field_characters'}
PRODUCTION_PROFILE=dict(version=1,scope='project_observed_REES46_October2019',
    compressed_sha256='8ebca1ad741295297368f2cf0315e3f36853a1a11768fb16babf8c9b83838147',compressed_bytes=1741928540,
    uncompressed_bytes=5668612855,expected_rows=42448764,fields=list(FIELDS),types=list(TYPES),nullable_fields=list(NULLABLE),
    start='2019-10-01T00:00:00Z',end='2019-11-01T00:00:00Z',actions=list(ACTIONS),compression='gzip_all_members',encoding='utf-8-strict',
    empty_policy='unquoted_and_quoted_empty_to_NULL_only_declared_nullable',max_field_characters=65536)


def need(condition,message):
    if not condition:raise ValueError(message)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_profile(profile):
    need(type(profile) is dict and set(profile)==PROFILE_KEYS,'Exact typed9 source profile required')
    need(type(profile['version']) is int and profile['version']==1,'Typed profile version required')
    need(profile['scope'] in {'project_observed_REES46_October2019','synthetic_typed9_import_fixture'},'Explicit source/fixture scope required')
    if profile['scope']=='project_observed_REES46_October2019':need(canonical(profile)==canonical(PRODUCTION_PROFILE),'Observed production archive/profile may not be resealed')
    need(type(profile['compressed_sha256']) is str and re.fullmatch('[a-f0-9]{64}',profile['compressed_sha256']),'Compressed source SHA required')
    for name in ['compressed_bytes','uncompressed_bytes','expected_rows']:
        need(type(profile[name]) is int and profile[name]>=0,'Typed source size/count required')
    need(profile['fields']==list(FIELDS) and profile['types']==list(TYPES) and profile['nullable_fields']==list(NULLABLE),'Fixed ordered typed9/null contract required')
    for name in ['start','end']:
        need(type(profile[name]) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',profile[name]),'Exact second UTC profile clock')
    clocks=[datetime.strptime(profile[name],'%Y-%m-%dT%H:%M:%SZ') for name in ['start','end']]
    need(clocks[0]<clocks[1],'Ordered source coverage required')
    need(profile['actions']==list(ACTIONS) and profile['compression']=='gzip_all_members' and profile['encoding']=='utf-8-strict' and
        profile['empty_policy']=='unquoted_and_quoted_empty_to_NULL_only_declared_nullable' and type(profile['max_field_characters']) is int and
        profile['max_field_characters']==65536,'Unsupported parsing semantics')
    return deepcopy(profile)


def parse_row(tokens,profile):
    need(type(tokens) is list and len(tokens)==9,'Exact nine CSV fields required; no padding/skips')
    need(all(type(v) is str and len(v)<=profile['max_field_characters'] and '\x00' not in v for v in tokens),'Bounded UTF8 fields without NUL required')
    values=[]
    for name,token in zip(FIELDS,tokens):
        if token=='':
            need(name in NULLABLE,'Required clock/action cannot be NULL');values.append(None);continue
        if name=='event_time':
            need(re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC',token),'Literal UTC timestamp required')
            value=datetime.strptime(token,TIME_FORMAT);stamp=value.strftime('%Y-%m-%dT%H:%M:%SZ')
            need(profile['start']<=stamp<profile['end'],'Event outside fixed half-open source period')
        elif name=='event_type':need(token in ACTIONS,'Unknown source action');value=token
        elif name in {'product_id','category_id','user_id'}:
            need(re.fullmatch(r'[+-]?(?:0|[1-9][0-9]*)',token),'Exact integer token required; no float/exponent/rounding')
            value=int(token);need(-2**63<=value<2**63,'Exact signed64 key range')
        elif name=='price':
            need(re.fullmatch(r'[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?',token),'Exact price scale/token required; no rounding')
            value=Decimal(token);need(abs(value)<=Decimal('9999999999.99'),'DECIMAL(12,2) price range')
        else:value=token
        values.append(value)
    return tuple(values)


def file_hash(path,check):
    sha=hashlib.sha256();size=0;check()
    with Path(path).open('rb') as stream:
        while part:=stream.read(2**20):check();sha.update(part);size+=len(part)
    check();return sha.hexdigest(),size


def exclusive(path,body):
    raw=(canonical(body)+'\n').encode();fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def snapshot_archive(archive,destination,profile,check):
    sha=hashlib.sha256();size=0;check();fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as output,Path(archive).open('rb') as source:
        while part:=source.read(2**20):check();output.write(part);sha.update(part);size+=len(part)
        output.flush();os.fsync(output.fileno())
    check();need((sha.hexdigest(),size)==(profile['compressed_sha256'],profile['compressed_bytes']),'Original compressed SHA/size differs')
    return sha.hexdigest(),size


def decompress_complete(snapshot,spool,profile,check):
    sha=hashlib.sha256();size=0;check();fd=os.open(spool,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as output,gzip.open(snapshot,'rb') as source:
        while part:=source.read(2**20):check();output.write(part);sha.update(part);size+=len(part)
        output.flush();os.fsync(output.fileno())
    # GzipFile has reached EOF and checked every member CRC/ISIZE. Python's
    # ISIZE is modulo2**32; this independent full stream count is not modulo.
    check();need(size==profile['uncompressed_bytes'],'Full uncompressed stream size differs')
    return sha.hexdigest(),size


def validate_csv(spool,profile,check,*,canonical_path=None):
    """Parse once under one dialect; optionally emit its unambiguous native input.

    DuckDB may interpret whitespace-surrounded quotes differently from Python.
    The native reader never consumes the original ambiguous CSV spelling.
    """
    summary=dict(rows=0,actions={name:0 for name in ACTIONS},nulls={name:0 for name in FIELDS},minimum_time=None,maximum_time=None)
    prior=csv.field_size_limit();csv.field_size_limit(profile['max_field_characters'])
    try:
        with ExitStack() as stack:
            stream=stack.enter_context(Path(spool).open('r',encoding='utf-8',errors='strict',newline=''))
            reader=csv.reader(stream,delimiter=',',quotechar='"',doublequote=True,strict=True)
            need(next(reader,None)==list(FIELDS),'Exact ordered CSV header required; no duplicate/reordered fields')
            output=writer=None
            if canonical_path is not None:
                fd=os.open(canonical_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                output=stack.enter_context(os.fdopen(fd,'w',encoding='utf-8',errors='strict',newline=''))
                writer=csv.writer(output,delimiter=',',quotechar='"',doublequote=True,quoting=csv.QUOTE_ALL,lineterminator='\n')
                writer.writerow(FIELDS)
            for tokens in reader:
                if summary['rows']%8192==0:check()
                values=parse_row(tokens,profile);stamp=values[0].strftime('%Y-%m-%dT%H:%M:%SZ');summary['rows']+=1;summary['actions'][values[1]]+=1
                for name,value in zip(FIELDS,values):summary['nulls'][name]+=int(value is None)
                summary['minimum_time']=stamp if summary['minimum_time'] is None else min(stamp,summary['minimum_time'])
                summary['maximum_time']=stamp if summary['maximum_time'] is None else max(stamp,summary['maximum_time'])
                if writer is not None:writer.writerow(tokens)
            if output is not None:output.flush();os.fsync(output.fileno())
    finally:csv.field_size_limit(prior)
    check();need(summary['rows']==profile['expected_rows'],'Complete raw-bag row count differs')
    return summary


def import_archive(archive,work_directory,profile,*,check):
    """Caller-authenticated local archive → new owned snapshot/spool/events DB.

    check is a mandatory trusted non-SQL lifetime callback. Work directory must
    not exist; failures/partials remain. Snapshot/spool are owned0600 files in a
    new0700 directory under the trusted caller, not an adversarial writer lock.
    No claim of source completeness, resource acceptance or old DB identity.
    """
    need(callable(check),'Explicit guarded caller required');check();profile=validate_profile(profile)
    archive=Path(archive).resolve();directory=Path(work_directory).resolve();need(archive!=directory and not directory.exists(),'New exclusive import work directory required')
    directory.mkdir(mode=0o700,parents=False,exist_ok=False);con=None
    snapshot=directory/'source.csv.gz';spool=directory/'source.csv';canonical_csv=directory/'validated.csv';database=directory/'events.duckdb'
    exclusive(directory/'import.consumed.json',dict(version=1,scope='caller_owned_source_import_kernel_attempt',profile=profile,archive=str(archive),work_directory=str(directory)))
    try:
        compressed=snapshot_archive(archive,snapshot,profile,check);uncompressed=decompress_complete(snapshot,spool,profile,check)
        summary=validate_csv(spool,profile,check,canonical_path=canonical_csv)
        canonical_witness=file_hash(canonical_csv,check)
        import duckdb
        check();con=duckdb.connect(str(database),config={'threads':'2','memory_limit':'2GB','max_temp_directory_size':'8GiB','temp_directory':str(directory/'spill')})
        con.execute('BEGIN TRANSACTION');check()
        columns='{'+','.join("'"+name+"':'"+kind+"'" for name,kind in zip(FIELDS,TYPES))+'}'
        con.execute("CREATE TABLE events AS SELECT * FROM read_csv(?,columns="+columns+",auto_detect=false,header=true,delim=',',quote='\"',escape='\"',strict_mode=true,ignore_errors=false,null_padding=false,nullstr='',allow_quoted_nulls=true,encoding='utf-8',timestampformat='%Y-%m-%d %H:%M:%S UTC')",[str(canonical_csv)]);check()
        need([tuple(r[:2]) for r in con.execute('DESCRIBE events').fetchall()]==list(zip(FIELDS,TYPES)),'Native typed9 schema differs')
        counts=con.execute('SELECT count(*),min(event_time),max(event_time),'+','.join("count(*)FILTER(WHERE event_type='"+name+"')" for name in ACTIONS)+','+','.join('count(*)FILTER(WHERE '+name+' IS NULL)' for name in FIELDS)+' FROM events').fetchone();check()
        native=dict(rows=counts[0],minimum_time=counts[1].strftime('%Y-%m-%dT%H:%M:%SZ') if counts[1] else None,
            maximum_time=counts[2].strftime('%Y-%m-%dT%H:%M:%SZ') if counts[2] else None,actions=dict(zip(ACTIONS,counts[3:6])),nulls=dict(zip(FIELDS,counts[6:])))
        need(canonical(native)==canonical(summary),'Native import/raw-bag conformance differs')
        con.execute('COMMIT');check();con.execute('CHECKPOINT');check();con.close();con=None;check()
        need(file_hash(archive,check)==compressed and file_hash(snapshot,check)==compressed,'Original archive/owned snapshot changed')
        need(file_hash(spool,check)==uncompressed,'Original decompressed CSV snapshot changed')
        need(file_hash(canonical_csv,check)==canonical_witness,'Canonical validated CSV changed')
        db_sha,db_bytes=file_hash(database,check)
        result=dict(version=1,status='import_kernel_complete_pending_external_source_acceptance',profile=profile,profile_sha256=digest(profile),
            source=dict(sha256=compressed[0],bytes=compressed[1]),csv=dict(sha256=uncompressed[0],bytes=uncompressed[1],all_gzip_members_EOF_CRC_ISIZE_checked=True),
            validated_csv=dict(sha256=canonical_witness[0],bytes=canonical_witness[1],quoting='all_fields',parser='Python_csv_strict',native_reader_used=True),
            schema=[dict(name=n,type=t) for n,t in zip(FIELDS,TYPES)],summary=summary,database=dict(path=str(database),sha256=db_sha,bytes=db_bytes),
            parser='strict_typed9_no_float_keys_no_price_rounding_raw_bag',fit_attempt_count=0,labels_created=False,external_lifetime_acceptance_required=True)
        evidence=exclusive(directory/'import-evidence.json',result);check()
        need(file_hash(archive,check)==compressed and file_hash(snapshot,check)==compressed and file_hash(spool,check)==uncompressed and file_hash(canonical_csv,check)==canonical_witness,'Original import inputs changed during evidence persistence')
        need(file_hash(database,check)==(db_sha,db_bytes),'Original imported DB changed during evidence persistence')
        need(file_hash(directory/'import-evidence.json',check)[0]==evidence['sha256'],'Original import evidence changed')
        need(not (directory/'report.failed.json').exists(),'Known failed import cannot complete')
        return deepcopy(result)
    except BaseException as error:
        if con is not None:
            try:con.close();con=None
            except BaseException as secondary:error.add_note('Import cleanup: '+type(secondary).__name__)
        try:exclusive(directory/'report.failed.json',dict(version=1,status='failed_import_kernel',error_type=type(error).__name__,retry=False,source_acceptance_issued=False))
        except BaseException as secondary:error.add_note('Import failure persistence: '+type(secondary).__name__)
        raise
