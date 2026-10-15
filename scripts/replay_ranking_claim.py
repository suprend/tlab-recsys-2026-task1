"""Bounded zero-fit replay of a synthetic or explicitly authorized ranking package."""
import time
START = time.monotonic()
import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys

ROOT = Path(__file__).resolve().parents[1]
ROLE = 'bounded_fullY_ranking_claim_replay'
PUBLIC_PACKAGE = 'tests/fixtures/reproduction/manual18-small'
PUBLIC_MANIFEST_SHA = '7a9b61af70a2f21a85fa6d4697a644eccab1a2147257c57449b6210be7d2b8c3'
ESTIMANDS = ['conditional_macro_query','all_query_zero','conditional_user_macro','all_user_macro_zero']
CAPS = {'queries':30000,'candidates':6600000,'targets':2000000,'scores':6600000}
KINDS = tuple(CAPS)
DEVELOPMENT = {'train':('2019-10-08T00:00:00Z','2019-10-21T00:00:00Z'),
               'selection':('2019-10-22T00:00:00Z','2019-10-24T00:00:00Z')}
METADATA_BYTES = 65536
LINE_BYTES = 16384


def need(value, gate):
    if not value:raise ValueError(gate)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def parse(raw):
    def pairs(items):
        result = {}
        for key,value in items:
            need(key not in result,'duplicate_json_key');result[key]=value
        return result
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def keys(value, expected, gate):
    need(type(value) is dict and set(value)==set(expected),gate)


def integer(value, low, high, gate):
    need(type(value) is int and low<=value<=high,gate)
    return value


def int64(value):return integer(value,-2**63,2**63-1,'exact_int64_required')


def query_id(value):
    need(type(value) is str and 0<len(value)<=128,'query_id_type_or_length')
    return value


def utc(value):
    need(type(value) is str and value.endswith('Z'),'UTC_timestamp_required')
    try:result=datetime.fromisoformat(value[:-1]+'+00:00')
    except ValueError:raise ValueError('UTC_timestamp_required') from None
    need(result.utcoffset()==timedelta(0),'UTC_timestamp_required')
    return result


def same(left, right):
    if type(left) is dict:
        keys(right,left,'claim_schema_mismatch')
        for key in left:same(left[key],right[key])
    elif type(left) is list:
        need(type(right) is list and len(left)==len(right),'claim_sequence_mismatch')
        for a,b in zip(left,right):same(a,b)
    elif type(left) is float:
        need(type(right) is float and math.isfinite(right) and abs(left-right)<=1e-12,'claim_numeric_mismatch')
    else:need(type(left) is type(right) and left==right,'claim_value_or_type_mismatch')


def local(root, name):
    need(type(name) is str and name and not Path(name).is_absolute() and '..' not in Path(name).parts,'nonlocal_path')
    path=(root/name).resolve()
    need(path.is_relative_to(root),'escaped_path')
    return path


def raw_json(path, check=lambda:None):
    check()
    with path.open('rb') as stream:raw=stream.read(METADATA_BYTES+1)
    need(len(raw)<=METADATA_BYTES,'metadata_cap')
    check()
    return parse(raw),hashlib.sha256(raw).hexdigest()


def pin(path, check):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):check();h.update(block)
    check();return h.hexdigest()


def exclusive(path, body):
    raw=(canonical(body)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return hashlib.sha256(raw).hexdigest()


class Budget:
    def __init__(self):
        self.cpu_seconds=300;self.rss_bytes=512*2**20;self.deadline=START+300
    def cpu(self):
        r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime
    def rss(self):
        need(sys.platform=='darwin' or sys.platform.startswith('linux'),'unsupported_RSS_units')
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1024 if sys.platform.startswith('linux') else 1))
    def guard(self):
        used,peak=self.cpu(),self.rss()
        need(type(used) in (int,float) and math.isfinite(used) and used>=0,'unknown_absolute_CPU')
        need(type(peak) is int and peak>0,'unknown_peak_RSS')
        if used>self.cpu_seconds or time.monotonic()>self.deadline:raise TimeoutError('replay_absolute_CPU_or_wall_cap')
        if peak>self.rss_bytes:raise MemoryError('replay_RSS_cap')
        r=resource.getrusage(resource.RUSAGE_CHILDREN)
        need(r.ru_utime+r.ru_stime==0,'replay_subprocesses_forbidden')
    def report(self):
        used,peak=self.cpu(),self.rss()
        need(type(used) in (int,float) and math.isfinite(used) and used>=0 and type(peak) is int and peak>0,'unknown_resource_receipt')
        return dict(process_cpu_seconds=used,process_peak_rss_bytes=peak,
            started_monotonic=START,finished_monotonic=time.monotonic(),reaped_children_cpu_seconds=0)


class Rows:
    """Bounded-line exact hash/rowcount validation while consuming a sorted stream."""
    def __init__(self,path,kind,reference,check):
        self.path,self.kind,self.reference,self.check=path,kind,reference,check
        self.count=0;self.previous=None;self.hash=hashlib.sha256();self.done=False
    def __iter__(self):
        need(not hasattr(self,'iterator'),'stream_reuse_forbidden')
        self.iterator=self._iterate()
        return self.iterator
    def close(self):
        if hasattr(self,'iterator'):self.iterator.close()
    def _iterate(self):
        with self.path.open('rb') as stream:
            while True:
                self.check();raw=stream.readline(LINE_BYTES+1)
                if not raw:break
                need(len(raw)<=LINE_BYTES and raw.endswith(b'\n'),'line_cap_or_unterminated_JSONL')
                self.hash.update(raw);row=parse(raw)
                required={'query_id','user_id','anchor','label_is_mature'} if self.kind=='queries' else {'query_id','product_id'}
                if self.kind=='scores':required=required|{'raw_score'}
                keys(row,required,'row_schema');qid=query_id(row['query_id'])
                if self.kind=='queries':
                    key=qid;int64(row['user_id']);utc(row['anchor']);need(type(row['label_is_mature']) is bool,'maturity_boolean_required')
                else:
                    key=(qid,int64(row['product_id']))
                    if self.kind=='scores':
                        need(type(row['raw_score']) in (int,float) and math.isfinite(row['raw_score']),'finite_raw_score_required')
                need(self.previous is None or key>self.previous,'duplicate_or_unsorted_exact_keys')
                self.previous=key;self.count+=1
                need(self.count<=self.reference['rows'],'row_count_over_declared')
                yield row
        self.check()
        need(self.count==self.reference['rows'] and self.hash.hexdigest()==self.reference['sha256'],'stream_hash_or_row_count_mismatch')
        self.done=True


class Cursor:
    def __init__(self,rows):self.rows=iter(rows);self.value=next(self.rows,None)
    def take(self,qid):
        result=[]
        need(self.value is None or self.value['query_id']>=qid,'orphan_query_key')
        while self.value is not None and self.value['query_id']==qid:
            result.append(self.value);self.value=next(self.rows,None)
        return result
    def finish(self):need(self.value is None,'orphan_trailing_query_key')


class Replay:
    def __init__(self, package, *, expected_manifest_sha=None, access_contract=None, issued_access_sha=None,
                 execution_approval=None, issued_approval_sha=None, evidence_out=None):
        self.root=ROOT.resolve();self.budget=Budget();self.phase='metadata';self.observed={};self.streams=[];self.claim=None
        self.package=local(self.root,package);need(self.package.is_dir(),'package_directory_required')
        self.manifest_path=self.package/'manifest.json'
        self.output=local(self.root,evidence_out) if evidence_out else None
        if self.output is not None:
            need(not self.output.is_relative_to(self.package),'evidence_cannot_modify_package')
            need(self.output.parent.is_dir() and not self.output.exists(),'exclusive_evidence_path_required')
        self.failed=self.output.with_suffix('.failed.json') if self.output else None
        if self.failed is not None:need(not self.failed.exists(),'known_failed_replay')
        self.args=dict(expected_manifest_sha=expected_manifest_sha,access_contract=access_contract,issued_access_sha=issued_access_sha,
            execution_approval=execution_approval,issued_approval_sha=issued_approval_sha)
    def metadata_ref(self,reference):
        keys(reference,{'path','sha256'},'reference_schema')
        path=local(self.root,reference['path']);body,sha=raw_json(path,self.budget.guard)
        need(sha==reference['sha256'],'verified_metadata_bytes_changed');self.observed[reference['path']]=sha
        return body
    def bind(self):
        m,sha=raw_json(self.manifest_path,self.budget.guard);self.manifest=m;self.manifest_sha=sha
        keys(m,{'version','scope','stage','k','estimands','tie_policy','target_policy','horizon_hours','availability_delay_seconds',
                'query_range','label_available_before','source_observed_until','files','claim_metrics'},'manifest_schema')
        need(type(m['version']) is int and m['version']==1 and m['scope']=='ranking_claim_replay_package','manifest_scope')
        # Reject closed stages before opening/hash-streaming Q, C, Y or scores.
        need(m['stage'] in {'synthetic','train','selection'},'heldout_or_unsupported_stage_closed')
        integer(m['k'],20,20,'fixed_K20_required');same(ESTIMANDS,m['estimands'])
        need(m['tie_policy']=='raw_score_desc_product_id_asc' and m['target_policy']=='full_distinct_targets_not_intersected_with_C','ranking_policy')
        integer(m['horizon_hours'],24,24,'fixed_purchase24h_required');integer(m['availability_delay_seconds'],0,86400,'availability_delay')
        keys(m['query_range'],{'start','end'},'query_range_schema')
        self.start,self.end=utc(m['query_range']['start']),utc(m['query_range']['end']);need(self.start<self.end,'query_range_order')
        need(all(v.hour==v.minute==v.second==v.microsecond==0 for v in (self.start,self.end)),'daily_UTC_range_required')
        self.cutoff=min(utc(m['label_available_before']),utc(m['source_observed_until']))
        if m['stage']!='synthetic':
            low,high=map(utc,DEVELOPMENT[m['stage']])
            need(low<=self.start<self.end<=high and utc(m['label_available_before'])<=high,'historical_development_only_before_targets')
        keys(m['files'],KINDS,'file_map_schema');self.files={}
        for kind,ref in m['files'].items():
            keys(ref,{'path','sha256','rows'},'file_reference_schema')
            integer(ref['rows'],0,CAPS[kind],'declared_row_cap')
            need(type(ref['sha256']) is str and len(ref['sha256'])==64 and all(c in '0123456789abcdef' for c in ref['sha256']),'data_digest_type')
            path=local(self.package,ref['path']);need(path!=self.manifest_path,'manifest_is_not_data')
            self.files[kind]=path
        need(len(set(self.files.values()))==4,'file_aliasing')
        if m['stage']!='synthetic':
            query_cap=26000 if m['stage']=='train' else 4000
            need(m['files']['queries']['rows']<=query_cap and all(m['files'][k]['rows']<=query_cap*220 for k in ('candidates','scores')),'development_population_cap')
        self.package_ref=dict(path=str(self.manifest_path.relative_to(self.root)),sha256=sha)
        self.observed[self.package_ref['path']]=sha
        supplied=[self.args[k] for k in ('access_contract','issued_access_sha','execution_approval','issued_approval_sha')]
        if m['stage']=='synthetic':
            need(self.package==local(self.root,PUBLIC_PACKAGE) and sha==PUBLIC_MANIFEST_SHA,'unreviewed_synthetic_package')
            need(not any(supplied) and self.args['expected_manifest_sha'] in (None,sha),'synthetic_authority_arguments')
            self.access=None;self.approval=None
        else:
            need(type(self.args['expected_manifest_sha']) is str and self.args['expected_manifest_sha']==sha and all(supplied),'external_manifest_access_budget_required')
            access_ref=dict(path=self.args['access_contract'],sha256=self.args['issued_access_sha'])
            approval_ref=dict(path=self.args['execution_approval'],sha256=self.args['issued_approval_sha'])
            access=self.metadata_ref(access_ref)
            same(dict(version=1,scope='reviewed_train_selection_ranking_replay_access',approved=True,manifest=self.package_ref,
                stage=m['stage'],query_range=m['query_range'],permissions=dict(queries=True,candidates=True,targets=True,scores=True,
                confirmation=False,final=False)),access)
            approval=self.metadata_ref(approval_ref)
            keys(approval,{'version','scope','approved','manifest','access','code','limits','claim_path','allowed_replay_attempts','allowed_fit_attempts','allowed_native_predictions'},'budget_schema')
            need(type(approval['version']) is int and approval['version']==1 and approval['scope']==ROLE and approval['approved'] is True,'budget_scope')
            same(self.package_ref,approval['manifest']);same(access_ref,approval['access'])
            same(1,approval['allowed_replay_attempts']);same(0,approval['allowed_fit_attempts']);same(0,approval['allowed_native_predictions'])
            limits=approval['limits'];keys(limits,{'cpu_seconds','wall_seconds','rss_bytes'},'budget_limits_schema')
            self.budget.cpu_seconds=integer(limits['cpu_seconds'],1,300,'budget_CPU_cap')
            self.budget.deadline=min(self.budget.deadline,START+integer(limits['wall_seconds'],1,300,'budget_wall_cap'))
            self.budget.rss_bytes=integer(limits['rss_bytes'],1,512*2**20,'budget_RSS_cap')
            expected_code={str(Path(__file__).resolve().relative_to(self.root)),'scripts/ranking_metrics.py'}
            keys(approval['code'],expected_code,'runtime_code_pinset')
            for name,digest in approval['code'].items():
                need(pin(local(self.root,name),self.budget.guard)==digest,'runtime_code_changed');self.observed[name]=digest
            claim_path=local(self.root,approval['claim_path'])
            need(claim_path.parent==self.root/'artifacts/reproduction/claims' and claim_path.suffix=='.json' and claim_path.parent.is_dir(),'claim_namespace')
            body=dict(version=1,scope=ROLE+'_attempt',manifest=self.package_ref,access=access_ref,execution_approval=approval_ref,
                allowed_replay_attempts=1,allowed_fit_attempts=0,allowed_native_predictions=0)
            hashed=exclusive(claim_path,body)
            self.claim=dict(path=str(claim_path.relative_to(self.root)),sha256=hashed);self.observed[self.claim['path']]=hashed
            self.access,self.approval=access_ref,approval_ref
        self.budget.guard()
    def rows(self,kind):
        rows=Rows(self.files[kind],kind,self.manifest['files'][kind],self.budget.guard);self.streams.append(rows);return rows
    def calculate(self):
        self.phase='all_query_scope_before_targets'
        queries=list(self.rows('queries'));identities=set()
        for q in queries:
            anchor=utc(q['anchor']);key=(q['user_id'],anchor)
            need(self.start<=anchor<self.end and key not in identities and anchor.hour==anchor.minute==anchor.second==anchor.microsecond==0,'query_range_or_duplicate_user_anchor');identities.add(key)
            mature=anchor+timedelta(hours=24,seconds=self.manifest['availability_delay_seconds'])<=self.cutoff
            need(q['label_is_mature'] is mature,'maturity_availability_mismatch')
        self.phase='keyed_score_fullY_merge'
        candidates=Cursor(self.rows('candidates'));scores=Cursor(self.rows('scores'));targets=Cursor(self.rows('targets'))
        # Import only public006 evaluator, after authority/maturity gates. No
        # training/model/native-prediction modules are imported by this entry.
        from scripts import ranking_metrics as evaluator
        need(Path(evaluator.__file__).resolve()==local(self.root,'scripts/ranking_metrics.py'),'loaded_evaluator_checkout_mismatch')
        QueryRanking,evaluate=evaluator.QueryRanking,evaluator.evaluate
        counts=dict(candidate_rows=0,target_rows=0,score_rows=0,empty_candidate_queries=0,targets_outside_candidates=0)
        def rankings():
            for q in queries:
                self.budget.guard();qid=q['query_id'];c=candidates.take(qid);s=scores.take(qid);y=targets.take(qid)
                need(len(c)<=220 and len(y)<=1000000,'per_query_population_cap')
                need([(r['query_id'],r['product_id']) for r in c]==[(r['query_id'],r['product_id']) for r in s],'exact_C_score_key_multiset')
                need(q['label_is_mature'] or not y,'censored_query_contains_targets')
                items={r['product_id'] for r in c};full={r['product_id'] for r in y}
                ordered=[r['product_id'] for r in sorted(s,key=lambda r:(-r['raw_score'],r['product_id']))]
                counts['candidate_rows']+=len(c);counts['target_rows']+=len(y);counts['score_rows']+=len(s)
                counts['empty_candidate_queries']+=int(not c);counts['targets_outside_candidates']+=len(full-items)
                yield QueryRanking(qid,q['user_id'],ordered,full if q['label_is_mature'] else None,q['label_is_mature'])
            for cursor in (candidates,scores,targets):cursor.finish()
        result=asdict(evaluate(rankings(),20))
        need(all(s.done for s in self.streams),'all_streams_complete_required')
        if self.manifest['claim_metrics'] is not None:same(self.manifest['claim_metrics'],result)
        return result,counts
    def repin(self, *, full=True):
        need(self.failed is None or not self.failed.exists(),'known_failed_replay')
        for name,expected in self.observed.items():need(pin(local(self.root,name),self.budget.guard)==expected,'authority_changed_at_completion')
        if full:
            for kind,path in self.files.items():need(pin(path,self.budget.guard)==self.manifest['files'][kind]['sha256'],'data_changed_at_completion')
        self.budget.guard();need(self.failed is None or not self.failed.exists(),'late_failed_replay')
    def run(self):
        primary=None;metrics=None;counts=None;result=None
        try:
            self.bind();metrics,counts=self.calculate()
        except BaseException as error:primary=error
        finally:
            for stream in self.streams:
                try:stream.close()
                except BaseException as error:primary=primary or error
            try:self.budget.guard()
            except BaseException as error:primary=primary or error
        if primary is None:
            try:
                self.phase='postclose_final_original_pins';self.repin()
                result=dict(version=1,status='computed_verified_package_replay',scope=ROLE,stage=self.manifest['stage'],manifest=self.package_ref,
                    access=self.access,execution_approval=self.approval,execution_consumed=self.claim,fit_attempt_count=0,native_prediction_count=0,
                    source_regeneration_count=0,metrics=metrics,counts=counts,
                    proof_limits='Replay of supplied exact keyed scores and full targets only. No source-formula proof, actual training-weight recovery, heldout access, model fitting/prediction, selection-bias correction or generalization claim.',
                    receipt_boundary='after_stream_close_before_small_evidence_fsync_and_exit_tail_external_lifetime_receipt_required_for_private_acceptance',**self.budget.report())
                self.budget.guard()
                if self.output is not None:
                    exclusive(self.output,result)
                self.repin(full=False)
                self.budget.guard();need(self.failed is None or not self.failed.exists(),'terminal_failed_replay')
            except BaseException as error:primary=error
        if primary is not None:
            failure=dict(version=1,status='failed',scope=ROLE,phase=self.phase,error_type=type(primary).__name__,
                fit_attempt_count=0,native_prediction_count=0,execution_consumed=self.claim)
            try:failure.update(self.budget.report())
            except BaseException as secondary:primary.add_note('Resource receipt unavailable: '+type(secondary).__name__)
            if self.failed is not None:
                try:exclusive(self.failed,failure)
                except BaseException as secondary:primary.add_note('Failure receipt persistence: '+type(secondary).__name__)
            primary.replay_evidence=failure
            raise primary
        return result


def replay(package, **kwargs):return Replay(package,**kwargs).run()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True)
    p.add_argument('--expected-manifest-sha')
    p.add_argument('--access-contract');p.add_argument('--issued-access-sha')
    p.add_argument('--execution-approval');p.add_argument('--issued-approval-sha')
    p.add_argument('--evidence-out')
    args=vars(p.parse_args(argv));package=args.pop('package')
    try:result=replay(package,**args)
    except BaseException as error:
        # No raw values, IDs or engine traceback in public CLI output.
        failure=getattr(error,'replay_evidence',dict(version=1,status='failed',scope=ROLE,error_type=type(error).__name__,fit_attempt_count=0,native_prediction_count=0))
        print(canonical(failure));return 1
    print(canonical(result));return 0


if __name__=='__main__':raise SystemExit(main())
