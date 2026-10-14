"""Daily bounded metadata export over externally accepted train/selection.

The accepted100Q producer is immutable. This runtime changes no Q/Y/C/baseF,
loads no targets, and exports no models. Execution needs external exactapproval.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import hashlib
import json
import time
import uuid

import duckdb

from scripts import metadata_price_features as m
from scripts.anchor_pilot import RunDeadline,StageLedger,peak_rss_bytes,directory_bytes,naive_utc
from scripts.development_collection import _atomic_json
from scripts.protocol_manifest import (_read_json,_keys,_hashes,_relative_path,_utc,canonical_json,sha256_file)

ROOT=Path(__file__).resolve().parents[1]
ROLE='metadata_price_development_export'
LIMITS=dict(wall_seconds=1200,max_process_cpu_seconds=900,threads=2,rss_bytes=8*2**30,max_spill_bytes=2*2**30,
            max_pairs_per_day=440000,max_unique_items_per_day=22000)
CODE=(*m.GATE_CODE,'scripts/metadata_price_collection.py')


def cpu_time():return m._process_cpu_seconds()


def local(name):
    _relative_path(name)
    path=(ROOT/name).resolve()
    path.relative_to(ROOT.resolve())
    return path


def relative(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def verify_pins(pins,check=lambda:None):
    _hashes(pins,'reviewed metadata pins')
    for name,digest in pins.items():
        check()
        if sha256_file(local(name))!=digest:
            raise ValueError('Reviewed metadata content changed: '+name)
        check()


def merge_pins(*groups):
    result={}
    for group in groups:
        for name,digest in group.items():
            if name in result and result[name]!=digest:
                raise ValueError('Conflicting accepted metadata inputs: '+name)
            result[name]=digest
    return result


def verify_collection_strict(path,*,check=lambda:None):
    """Reuse008 validation and add exact14 Q/Y/C approval scope and reportIDs.

    Older017 feature-lineage helper derives consumed inputs from the approval
    map; that map itself must also have the complete canonical004 scope.
    This supplement changes no accepted producer/helper or prior data record.
    """
    from scripts.train_baselines import verify_collection
    collection=verify_collection(path,check=check)
    cid=collection['plan']['collection_id']
    state_name=next(n for n in collection['pins'] if n.endswith('/'+cid+'/state.json'))
    state=_read_json(local(state_name))
    execution=collection['plan']['execution_inputs']
    identity=collection['plan']['identity']
    for entry in state['shards']:
        check()
        manifests={kind:_read_json(local(entry[kind]['directory']+'/run.json'))
                   for kind in ['anchor','candidate','features']}
        reports={kind:_read_json(local(entry[kind]['directory']+'/report.json'))
                 for kind in ['candidate','features']}
        am,cm,fm=(manifests[k] for k in ['anchor','candidate','features'])
        expected=merge_pins(am['identity']['code_hashes'],cm['identity']['code_hashes'],
            {execution['source_path']:identity['source_sha256']},
            entry['anchor']['fingerprints'],entry['candidate']['fingerprints'])
        approval=_read_json(local(entry['acceptance']['path']))
        if len(expected)!=14 or approval['fingerprints']!=expected:
            raise ValueError('Shard approval must contain exact canonical14 code/source/Q/Y/C pins')
        if (reports['candidate'].get('anchor_run_id')!=am['run_id']
                or reports['features'].get('anchor_run_id')!=am['run_id']
                or reports['features'].get('candidate_run_id')!=cm['run_id']):
            raise ValueError('Candidate/feature report consumed runIDs mismatch')
        consumed=fm['identity']['input_hashes']
        registry=collection['phase']['feature_registry']
        fixed=merge_pins(expected,{registry:identity['registry_sha256'],
            entry['acceptance']['path']:entry['acceptance']['sha256']})
        extra=set(consumed)-set(fixed)
        if len(extra)!=1 or any(consumed.get(n)!=d for n,d in fixed.items()):
            raise ValueError('Feature input scope must include exact canonical Q/Y/C dependencies')
        selection=next(iter(extra))
        if _read_json(local(selection))!=reports['features']['selection']:
            raise ValueError('Feature selection definition differs from consumed input')
        check()
    return collection


def verify_accepted_metadata_gate(path,*,check=lambda:None):
    approval=_read_json(path)
    _keys(approval,{'version','approved','scope','run_id','fingerprints'},'metadata source acceptance')
    if type(approval['version']) is not int or approval['version']!=1 or approval['approved'] is not True or approval['scope']!='reviewed_metadata_price_100q':
        raise ValueError('External independent100Q source/cost acceptance required')
    _hashes({'run_id':approval['run_id']},'metadata gate runID')
    directory=ROOT/'artifacts/metadata-price'/approval['run_id']
    manifest_name,report_name=relative(directory/'run.json'),relative(directory/'report.json')
    # Pin the manifest/report before using either to derive required scope.
    for name in [manifest_name,report_name]:
        if name not in approval['fingerprints']:
            raise ValueError('Missing accepted100Q manifest/report pin')
        verify_pins({name:approval['fingerprints'][name]},check)
    manifest,report=_read_json(local(manifest_name)),_read_json(local(report_name))
    _keys(manifest,{'run_id','identity','gate_approval','outputs'},'metadata gate manifest')
    identity=manifest['identity']
    _keys(identity,{'version','role','spec','collection_id','fingerprints','query_selection','label_policy','outputs'},'metadata gate identity')
    if (type(identity['version']) is not int or identity['version']!=1 or identity['role']!=m.GATE_ROLE
            or identity['query_selection']!='bottom_sha256_query_id_per_day_then_round_robin_day_rank_anchor_query_id_100'
            or identity['label_policy']!='no_label_table_loaded_or_parsed'
            or identity['outputs']!='fixed_keys_3nominal_15numeric_separate_provenance_and_full_reference_no_model'):
        raise ValueError('Accepted100Q semantic identity changed')
    m.validate_spec(identity['spec'])
    # Identity.fp is a claim, not its own source of required input scope.
    # Find the bound accepted train/spec, then let the frozen100Q planner
    # derive the complete actual bundle, including source/candidate code.
    train_paths=[];spec_paths=[]
    for name,digest in identity['fingerprints'].items():
        if not name.endswith('.json'):continue
        verify_pins({name:digest},check)
        body=_read_json(local(name))
        if isinstance(body,dict) and body.get('scope')=='reviewed_development_collection' and body.get('collection_id')==identity['collection_id']:
            train_paths.append(local(name))
        if body==m.SPEC:spec_paths.append(local(name))
    if len(train_paths)!=1 or len(spec_paths)!=1:
        raise ValueError('Accepted100Q must bind one actual accepted train and spec file')
    expected_plan,_=m.prepare_gate_plan(train_paths[0],spec_paths[0],check=check)
    if identity!=expected_plan['identity']:
        raise ValueError('Accepted100Q identity differs from complete actual train/spec/code scope')
    if (manifest['run_id']!=approval['run_id'] or hashlib.sha256(canonical_json(identity).encode()).hexdigest()!=approval['run_id']
            or report.get('run_id')!=approval['run_id'] or report.get('status')!='complete_produced_unreviewed'
            or report.get('scope')!=m.GATE_ROLE or report.get('labels_loaded') is not False
            or type(report.get('fit_attempt_count')) is not int or report['fit_attempt_count']!=0
            or report.get('spec')!=identity['spec'] or report.get('collection_id')!=identity['collection_id']
            or report.get('query_selection',{}).get('queries')!=100):
        raise ValueError('Accepted100Q output/report identity is incomplete or detached')
    _keys(manifest['gate_approval'],{'path','sha256'},'100Q executionapproval reference')
    gate_ref=manifest['gate_approval']
    required=merge_pins(identity['fingerprints'],{gate_ref['path']:gate_ref['sha256']},
                        {manifest_name:approval['fingerprints'][manifest_name],report_name:approval['fingerprints'][report_name]})
    if manifest['outputs'].keys()!={'queries','features','provenance','reference'} or report.get('artifacts')!=manifest['outputs']:
        raise ValueError('Accepted100Q output scope changed')
    for name,artifact in manifest['outputs'].items():
        if artifact['path']!=relative(directory/(name+'.parquet')):
            raise ValueError('Accepted100Q output path detached')
        required=merge_pins(required,{artifact['path']:artifact['sha256']})
    if required!=approval['fingerprints']:
        raise ValueError('Accepted100Q fingerprints differ from exact required scope')
    verify_pins(required,check)
    execution=_read_json(local(gate_ref['path']))
    expected=dict(version=1,approved=True,scope=m.GATE_ROLE,run_id=approval['run_id'],fingerprints=identity['fingerprints'])
    if type(execution.get('version')) is not int or execution.get('approved') is not True or execution!=expected:
        raise ValueError('Accepted100Q executionapproval differs from pinned identity')
    for name in m.GATE_CODE:
        if name not in identity['fingerprints']:
            raise ValueError('Accepted100Q code bundle incomplete')
    return dict(manifest=manifest,report=report,pins=merge_pins(required,{relative(path):sha256_file(path)}))


def prepare_export_plan(train_acceptance,selection_acceptance,gate_acceptance,*,check=lambda:None):
    from scripts.train_baselines import validate_training_phases
    train=verify_collection_strict(train_acceptance,check=check)
    selection=verify_collection_strict(selection_acceptance,check=check)
    validate_training_phases(train,selection,dict(wall_seconds=LIMITS['wall_seconds']))
    if train['feature_columns']!=selection['feature_columns']:
        raise ValueError('Base train/selection feature schema differs')
    gate=verify_accepted_metadata_gate(gate_acceptance,check=check)
    if gate['manifest']['identity']['collection_id']!=train['plan']['collection_id']:
        raise ValueError('Accepted100Q source gate is not bound to this training collection')
    pins=merge_pins(train['pins'],selection['pins'],gate['pins'])
    for name in CODE:
        check();actual=sha256_file(local(name))
        pins=merge_pins(pins,{name:actual});check()
    identity=dict(version=1,role=ROLE,limits=deepcopy(LIMITS),spec=deepcopy(m.SPEC),fingerprints=pins,
        acceptance_refs=dict(train=relative(train_acceptance),selection=relative(selection_acceptance),gate=relative(gate_acceptance)),
        collections={role:c['plan']['collection_id'] for role,c in [('train',train),('selection',selection)]},
        gate_run_id=gate['manifest']['run_id'],label_policy='no_target_table_loaded_or_parsed',
        partition='all_accepted_queries_per_UTC_day_no_new_sampling',
        validation='whole_key_schema_reference_cover_and_every_unique_anchor_item_model_boundary')
    return dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity),dict(train=train,selection=selection)


class ExecutionAudit:
    """Small execution boundary: attemptfirst, boundedstages, terminalseal.

    Exposed for subsequent reviewed runners so close/serialization checks do
    not need another partial implementation. It performs no approval itself.
    """
    def __init__(self,output_root,*,seconds,scope,cpu_seconds=900):
        if type(cpu_seconds) is not int or not 1<=cpu_seconds<=3600:raise ValueError('Invalid reviewed processCPU cap')
        self.max_cpu_seconds=cpu_seconds
        self.started=time.monotonic();self.cpu_started=None
        self.directory=output_root/('attempt-'+uuid.uuid4().hex)
        self.directory.mkdir(parents=True,exist_ok=False)
        for name in ['profiles','temp']:(self.directory/name).mkdir()
        self.deadline=RunDeadline(seconds,started_at=self.started)
        self.ledger=StageLedger(self.directory/'profiles',deadline=self.deadline)
        self.report=dict(version=1,status='running',scope=scope,stages=self.ledger.rows,labels_loaded=False,fit_attempt_count=0)
        _atomic_json(self.directory/'report.json',self.report)
        self.connection=self.timer=self.manifest=None
        try:self.cpu_started=cpu_time()
        except Exception as error:
            self.report.update(status='failed',error_type=type(error).__name__,error=str(error),process_cpu_user_system_seconds=None)
            _atomic_json(self.directory/'report.json',self.report)
            raise

    def guard(self):
        self.deadline.check()
        used=cpu_time()-self.cpu_started
        if used<0:raise ValueError('Nonmonotonic CPU measurement')
        if used>self.max_cpu_seconds:raise TimeoutError('Execution processCPU ceiling exceeded')
        if peak_rss_bytes()>LIMITS['rss_bytes']:raise MemoryError('Execution cooperative RSS ceiling exceeded8GiB')
        if directory_bytes(self.directory/'temp')>LIMITS['max_spill_bytes']:raise MemoryError('Execution tempdisk ceiling exceeded2GiB')

    def stage(self,name,operation):
        before=None;index=len(self.ledger.rows);primary=None
        def secondary(error):
            self.report.setdefault('secondary_errors',[]).append(dict(stage=name,error_type=type(error).__name__,error=str(error)))
        def checked():
            nonlocal before,primary
            try:
                before=cpu_time()
                self.guard();value=operation();self.guard();return value
            except BaseException as error:
                primary=error;raise
        try:return self.ledger(name,checked)
        except BaseException as error:
            if primary is not None and primary is not error:
                secondary(error);raise primary
            primary=error;raise
        finally:
            if before is not None:
                try:self.ledger.rows[index]['process_cpu_user_system_seconds']=cpu_time()-before
                except Exception as error:
                    self.ledger.rows[index].update(status='failed',cpu_measurement_error=str(error))
                    secondary(error)
                    if primary is None:raise

    def identify(self,manifest,approval_path):
        approval=_read_json(approval_path)
        expected=dict(version=1,approved=True,scope=self.report['scope'],run_id=manifest['run_id'],fingerprints=manifest['identity']['fingerprints'])
        if type(approval.get('version')) is not int or approval.get('approved') is not True or approval!=expected:
            raise ValueError('External reviewed executionapproval differs from actual proposal')
        identified=self.directory.parent/manifest['run_id']
        if identified.exists():raise FileExistsError('Existing immutable export preserved; recovery requiresreview')
        self.directory.rename(identified);self.directory=identified;self.ledger.directory=identified/'profiles'
        self.manifest=deepcopy(manifest)
        self.manifest['execution_approval']=dict(path=relative(approval_path),sha256=sha256_file(approval_path))
        self.report['run_id']=manifest['run_id']

    def attach(self,connection):
        self.connection=connection;self.timer=self.deadline.interrupt_timer(connection);self.ledger.connection=connection
        connection.execute('SET threads=2');connection.execute("SET memory_limit='2GB'")
        connection.execute("SET max_temp_directory_size='2GB'")
        connection.execute('SET temp_directory=?',[str(self.directory/'temp')])
        connection.execute('SET preserve_insertion_order=false')

    def __enter__(self):return self

    def __exit__(self,kind,error,traceback):
        initial=error
        terminal=[]
        def fail(value,location):
            nonlocal error
            error=error or value
            terminal.append(dict(location=location,error_type=type(value).__name__,error=str(value)))
        for location,operation in [('timer_cancel',lambda:self.timer.cancel() if self.timer is not None else None),
                                   ('connection_close',lambda:self.connection.close() if self.connection is not None else None)]:
            try:operation()
            except Exception as value:fail(value,location)
        if self.manifest is not None:
            try:_atomic_json(self.directory/'run.json',self.manifest)
            except Exception as value:fail(value,'manifest_write')
        def measurements():
            for name,operation in [('seconds',lambda:time.monotonic()-self.started),
                ('process_cpu_user_system_seconds',lambda:cpu_time()-self.cpu_started),
                ('process_peak_rss_bytes',peak_rss_bytes),('temp_disk_bytes_after_close',lambda:directory_bytes(self.directory/'temp'))]:
                try:
                    result=operation()
                    if result<0:raise ValueError('Nonmonotonic/negative final measurement')
                    self.report[name]=result
                except Exception as value:
                    self.report[name]=None;fail(value,'measure_'+name)
            try:self.guard()
            except Exception as value:fail(value,'terminal_guard')
            if error is not None:self.report.update(status='failed',error_type=type(error).__name__,error=str(error))
            if terminal:self.report['terminal_errors']=terminal
        def persist():
            try:_atomic_json(self.directory/'report.json',self.report)
            except Exception as value:
                fail(value,'report_write')
                self.report.update(status='failed',error_type=type(error).__name__,error=str(error),terminal_errors=terminal)
                # Preserve the prior partial report if the filesystem/writer
                # is unavailable. A separate best-effort evidence path cannot
                # turn a failed write into an accepted complete run.
                try:(self.directory/'report.failed.json').write_text(canonical_json(self.report)+'\n')
                except Exception as extra:fail(extra,'fallback_failed_report_write')
        requested_status=self.report['status']
        if error is None:self.report['status']='finalizing'
        measurements()
        persist()
        # Charge manifest + first summary persistence. Only the final receipt
        # rewrite is outside this CPU snapshot; a parent ledger covers that
        # minimal tail. The cap itself is checked again after the rewrite.
        self.report['cpu_accounting_boundary']='after_close_manifest_and_initial_summary_before_final_receipt_persistence'
        if error is None:self.report['status']=requested_status
        measurements()
        persist()
        try:self.guard()
        except Exception as value:
            fail(value,'post_receipt_guard')
            self.report.update(status='failed',error_type=type(error).__name__,error=str(error),terminal_errors=terminal)
            measurements();persist()
        if error is not None and initial is None:raise error
        return False


def validate_day_arrays(con,*,check=lambda:None,vocabulary=None):
    """Prove item-invariance across all Q, validate only one row per item.

    Full numeric/categorical matrices are not allocated in this export stage.
    The separate small connection prevents renaming/replacing output tables.
    """
    fields=[*m.NOMINAL,*m.NUMERIC]
    check()
    con.execute('CREATE OR REPLACE TEMP TABLE mp_validation AS SELECT product_id,'+','.join(fields)+' FROM metadata_price_features GROUP BY ALL')
    n,items=con.execute('SELECT count(*),count(DISTINCT product_id) FROM mp_validation').fetchone()
    if n>LIMITS['max_unique_items_per_day']:
        raise ValueError('Unique daily metadata projection exceeds reviewed22000cap')
    if n!=items:
        raise ValueError('Metadata model values differ across Q for the same day/item')
    unique=con.execute('SELECT * FROM mp_validation ORDER BY product_id').fetchall()
    check()
    small=duckdb.connect(':memory:')
    try:
        small.execute('SET threads=2')
        schema=con.execute('DESCRIBE metadata_price_features').fetchall()
        small.execute('CREATE TEMP TABLE metadata_price_features('+','.join('"'+r[0]+'" '+r[1] for r in schema)+')')
        if unique:small.executemany('INSERT INTO metadata_price_features VALUES ('+','.join('?' for _ in schema)+')',
                                   [('day-validation',*r) for r in unique])
        numeric,nominal=m.model_arrays(small,max_rows=LIMITS['max_unique_items_per_day'])
        check()
        if vocabulary is not None:
            for i,name in enumerate(m.NOMINAL):vocabulary[name].update(nominal[:,i])
        return dict(unique_items=n,numeric_bytes=numeric.nbytes,nominal_pointer_bytes=nominal.nbytes,
            diagnostic_cardinality={name:len(set(nominal[:,i])) for i,name in enumerate(m.NOMINAL)})
    finally:small.close()


def run_export(train_acceptance,selection_acceptance,gate_acceptance,*,execution_approval):
    with ExecutionAudit(ROOT/'artifacts/metadata-price-development',seconds=LIMITS['wall_seconds'],scope=ROLE,
                        cpu_seconds=LIMITS['max_process_cpu_seconds']) as audit:
        manifest,collections=audit.stage('verify_accepted_collections_source_gate_and_plan',
            lambda:prepare_export_plan(train_acceptance,selection_acceptance,gate_acceptance,check=audit.guard))
        audit.identify(manifest,execution_approval)
        outputs={}
        audit.report.update(limits=LIMITS,spec=m.SPEC,phases={},purpose='complete bounded metadata export; no model or labels')
        source=collections['train']['plan']['execution_inputs']['source_path']
        def open_source():
            audit.connection=duckdb.connect(str(local(source)),read_only=True)
            audit.attach(audit.connection)
        audit.stage('open_bound_source_read_only',open_source)
        con=audit.connection
        for role,collection in collections.items():
            phase=collection['phase'];days=[]
            vocabulary={name:set() for name in m.NOMINAL}
            qpaths=[str(local(p)) for p in collection['refs']['queries']]
            fpaths=[str(local(p)) for p in collection['refs']['features']]
            audit.stage(role+'_load_queries',lambda:con.execute('CREATE OR REPLACE TEMP TABLE mp_all_queries AS SELECT * FROM read_parquet(?)',[qpaths]))
            total_q=con.execute('SELECT count(*) FROM mp_all_queries').fetchone()[0]
            total_pairs=con.execute('SELECT count(*) FROM read_parquet(?)',[fpaths]).fetchone()[0]
            if total_q>phase['budget']['max_queries'] or total_pairs>phase['budget']['max_candidate_pairs']:
                raise ValueError('Accepted collection exceeds phase caps')
            start,end=(_utc(phase['range'][k]).replace(tzinfo=None) for k in ['start','end'])
            source_bounds=collection['plan']['identity']['shard_protocols'][0]['source']
            day=start
            while day<end:
                audit.guard();tag=role+'_'+day.strftime('%Y-%m-%d')
                audit.stage(tag+'_queries',lambda:con.execute('CREATE OR REPLACE TEMP TABLE metadata_queries AS SELECT * FROM mp_all_queries WHERE anchor=?',[day]))
                audit.stage(tag+'_fixed_base_pairs',lambda:con.execute('''CREATE OR REPLACE TEMP TABLE metadata_pairs AS
                    SELECT f.query_id,f.product_id,f.candidate_category_id,f.candidate_category_ambiguous,f.candidate_category_missing
                    FROM read_parquet(?) f SEMI JOIN metadata_queries q USING(query_id)''',[fpaths]))
                qn=con.execute('SELECT count(*) FROM metadata_queries').fetchone()[0]
                if qn>2000:raise ValueError('Daily accepted query cap exceeded')
                audit.stage(tag+'_metadata',lambda:m.create_metadata_price_features(con,m.SPEC,
                    source_start=naive_utc(_utc(source_bounds['start'])),source_end=naive_utc(_utc(source_bounds['end'])),
                    max_pairs=LIMITS['max_pairs_per_day'],stage=lambda n,op:audit.stage(role+'_'+n,op),budget_check=audit.guard))
                audit.stage(tag+'_whole_boundary',lambda:m.validate_gate_outputs(con))
                validation=audit.stage(tag+'_every_unique_item_model_boundary',lambda:validate_day_arrays(con,check=audit.guard,vocabulary=vocabulary))
                directory=audit.directory/role/day.strftime('%Y-%m-%d');directory.mkdir(parents=True,exist_ok=False)
                artifacts={}
                for name,table,order in [('queries','metadata_queries','query_id'),('features','metadata_price_features','query_id,product_id'),
                    ('provenance','metadata_price_provenance','query_id,product_id'),('reference','metadata_price_reference','anchor,product_id')]:
                    path=directory/(name+'.parquet')
                    audit.stage(tag+'_export_'+name,lambda table=table,order=order,path=path:con.execute(
                        'COPY (SELECT * FROM '+table+' ORDER BY '+order+') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)]))
                    artifacts[name]=dict(path=relative(path),sha256=sha256_file(path),bytes=path.stat().st_size,
                        rows=con.execute('SELECT count(*) FROM '+table).fetchone()[0],
                        schema=[list(r[:2]) for r in con.execute('DESCRIBE '+table).fetchall()])
                days.append(dict(anchor=day.strftime('%Y-%m-%dT%H:%M:%SZ'),artifacts=artifacts,model_boundary=validation))
                audit.report['phases'][role]=dict(status='producing',days=days)
                _atomic_json(audit.directory/'report.json',audit.report)
                day+=timedelta(days=1)
            if sum(d['artifacts']['queries']['rows'] for d in days)!=total_q or sum(d['artifacts']['features']['rows'] for d in days)!=total_pairs:
                raise ValueError('Daily exports do not exactly cover accepted collection')
            # Exact whole-phase key equality, not counts alone; checks all rows.
            feature_paths=[str(local(d['artifacts']['features']['path'])) for d in days]
            query_paths=[str(local(d['artifacts']['queries']['path'])) for d in days]
            def exact_cover():
                for original,new,keys in [(fpaths,feature_paths,'query_id,product_id'),(qpaths,query_paths,'query_id')]:
                    bad=con.execute('''SELECT count(*) FROM ((SELECT '''+keys+''' FROM read_parquet(?) EXCEPT ALL SELECT '''+keys+''' FROM read_parquet(?))
                        UNION ALL (SELECT '''+keys+''' FROM read_parquet(?) EXCEPT ALL SELECT '''+keys+''' FROM read_parquet(?)))''',[original,new,new,original]).fetchone()[0]
                    if bad:raise ValueError('Full metadata export key multiset differs from accepted input')
            audit.stage(role+'_full_key_multiset_cover',exact_cover)
            outputs[role]=days
            audit.report['phases'][role]=dict(status='complete_produced_unreviewed',queries=total_q,pairs=total_pairs,days=days,
                diagnostic_phase_encoded_cardinality={name:len(values) for name,values in vocabulary.items()})
        audit.manifest['outputs']=outputs
        def final_pins():
            verify_pins(merge_pins(manifest['identity']['fingerprints'],{
                audit.manifest['execution_approval']['path']:audit.manifest['execution_approval']['sha256']}),audit.guard)
        audit.stage('reverify_all_actual_inputs',final_pins)
        audit.report['status']='complete_produced_unreviewed'
    print(json.dumps(dict(status=audit.report['status'],run_id=audit.report['run_id'],seconds=audit.report['seconds'],
        process_cpu_user_system_seconds=audit.report['process_cpu_user_system_seconds'])),flush=True)
    return audit.report


def verify_accepted_export(path,*,check=lambda:None):
    """Consume a later independent source acceptance; never create one."""
    approval=_read_json(path)
    _keys(approval,{'version','approved','scope','run_id','fingerprints'},'metadata export acceptance')
    if type(approval['version']) is not int or approval['version']!=1 or approval['approved'] is not True or approval['scope']!='reviewed_metadata_price_development_export':
        raise ValueError('Independent complete metadata export acceptance required')
    _hashes({'run_id':approval['run_id']},'metadata export runID')
    directory=ROOT/'artifacts/metadata-price-development'/approval['run_id']
    if (directory/'report.failed.json').exists():
        raise ValueError('Known failed metadata export receipt prevents acceptance')
    names=[relative(directory/name) for name in ['run.json','report.json']]
    for name in names:
        if name not in approval['fingerprints']:raise ValueError('Missing accepted full export manifest/report')
        verify_pins({name:approval['fingerprints'][name]},check)
    manifest,report=(_read_json(local(n)) for n in names)
    _keys(manifest,{'run_id','identity','execution_approval','outputs'},'full export manifest')
    refs=manifest['identity'].get('acceptance_refs',{})
    _keys(refs,{'train','selection','gate'},'full export acceptedinput refs')
    current,collections=prepare_export_plan(local(refs['train']),local(refs['selection']),local(refs['gate']),check=check)
    if (manifest['run_id']!=approval['run_id'] or report.get('run_id')!=approval['run_id']
            or report.get('status')!='complete_produced_unreviewed' or manifest['identity']['role']!=ROLE
            or hashlib.sha256(canonical_json(manifest['identity']).encode()).hexdigest()!=approval['run_id']
            or manifest['identity']['limits']!=LIMITS or manifest['identity']['spec']!=m.SPEC
            or manifest['outputs'].keys()!={'train','selection'} or manifest['identity']!=current['identity']
            or report.get('scope')!=ROLE or report.get('labels_loaded') is not False
            or type(report.get('fit_attempt_count')) is not int or report['fit_attempt_count']!=0):
        raise ValueError('Full export semantic identity/status differs from accepted bundle')
    ref=manifest['execution_approval']
    required=merge_pins(manifest['identity']['fingerprints'],{ref['path']:ref['sha256']},
        {n:approval['fingerprints'][n] for n in names})
    for role,days in manifest['outputs'].items():
        phase=collections[role]['phase']
        start,end=(_utc(phase['range'][k]).replace(tzinfo=None) for k in ['start','end'])
        expected_days=[]
        while start<end:
            expected_days.append(start.strftime('%Y-%m-%dT%H:%M:%SZ'));start+=timedelta(days=1)
        if [day['anchor'] for day in days]!=expected_days:
            raise ValueError('Full export phase day cover differs from bound accepted inputs')
        if report['phases'][role]['days']!=days or report['phases'][role]['status']!='complete_produced_unreviewed':
            raise ValueError('Full export phase output/report cover differs')
        for day in days:
            if day['artifacts'].keys()!={'queries','features','provenance','reference'}:
                raise ValueError('Full export artifact scope differs')
            for name,artifact in day['artifacts'].items():
                if artifact['path']!=relative(directory/role/day['anchor'][:10]/(name+'.parquet')):
                    raise ValueError('Full export output path detached from phase/day/identity')
                required=merge_pins(required,{artifact['path']:artifact['sha256']})
    if required!=approval['fingerprints']:raise ValueError('Full export acceptance must pin exact required scope')
    verify_pins(required,check)
    execution=_read_json(local(ref['path']))
    if type(execution.get('version')) is not int or execution.get('approved') is not True or execution!=dict(version=1,approved=True,
        scope=ROLE,run_id=approval['run_id'],fingerprints=manifest['identity']['fingerprints']):
        raise ValueError('Full export executionapproval not bound to identity')
    verify_physical_export(manifest,report,collections,check=check)
    verify_pins(required,check)
    return dict(manifest=manifest,report=report,pins=merge_pins(required,{relative(path):sha256_file(path)}),
        refs={role:[d['artifacts']['features']['path'] for d in days] for role,days in manifest['outputs'].items()})


def verify_physical_export(manifest,report,collections,*,check=lambda:None):
    """Read actual Parquets: hashes/schema claims cannot prove row/key cover.

    This relational/model boundary deliberately does not redo the external
    source-formula oracle. Accepted Q/baseF define its domain independently.
    """
    con=duckdb.connect(':memory:')
    try:
        con.execute('SET threads=2');con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='0B'")
        for role,days in manifest['outputs'].items():
            collection=collections[role]
            qpaths=[str(local(n)) for n in collection['refs']['queries']]
            fpaths=[str(local(n)) for n in collection['refs']['features']]
            vocabulary={name:set() for name in m.NOMINAL};queries=pairs=0
            for day in days:
                check();anchor=_utc(day['anchor']).replace(tzinfo=None)
                con.execute('CREATE OR REPLACE TEMP TABLE expected_queries AS SELECT * FROM read_parquet(?) WHERE anchor=?',[qpaths,anchor])
                con.execute('''CREATE OR REPLACE TEMP TABLE metadata_pairs AS SELECT f.query_id,f.product_id,
                    f.candidate_category_id,f.candidate_category_ambiguous,f.candidate_category_missing
                    FROM read_parquet(?) f SEMI JOIN expected_queries q USING(query_id)''',[fpaths])
                for name,table in [('queries','metadata_queries'),('features','metadata_price_features'),
                    ('provenance','metadata_price_provenance'),('reference','metadata_price_reference')]:
                    artifact=day['artifacts'][name];path=local(artifact['path'])
                    con.execute('CREATE OR REPLACE TEMP TABLE '+table+' AS SELECT * FROM read_parquet(?)',[str(path)])
                    actual_schema=[list(r[:2]) for r in con.execute('DESCRIBE '+table).fetchall()]
                    actual_rows=con.execute('SELECT count(*) FROM '+table).fetchone()[0]
                    if (type(artifact['rows']) is not int or type(artifact['bytes']) is not int
                            or artifact['schema']!=actual_schema or artifact['rows']!=actual_rows or artifact['bytes']!=path.stat().st_size):
                        raise ValueError('Physical metadata artifact differs from claimed schema/count/size')
                    check()
                if con.execute('DESCRIBE metadata_queries').fetchall()!=con.execute('DESCRIBE expected_queries').fetchall():
                    raise ValueError('Physical query schema differs from accepted queries')
                mismatch=con.execute('''SELECT count(*) FROM ((SELECT * FROM metadata_queries EXCEPT ALL SELECT * FROM expected_queries)
                    UNION ALL (SELECT * FROM expected_queries EXCEPT ALL SELECT * FROM metadata_queries))''').fetchone()[0]
                if mismatch:raise ValueError('Physical query rows differ from accepted queries/day')
                m.validate_gate_outputs(con)
                validation=validate_day_arrays(con,check=check,vocabulary=vocabulary)
                if validation!=day['model_boundary']:
                    raise ValueError('Physical metadata model boundary differs from reported diagnostics')
                queries+=con.execute('SELECT count(*) FROM metadata_queries').fetchone()[0]
                pairs+=con.execute('SELECT count(*) FROM metadata_pairs').fetchone()[0]
                check()
            actual_q=con.execute('SELECT count(*) FROM read_parquet(?)',[qpaths]).fetchone()[0]
            actual_f=con.execute('SELECT count(*) FROM read_parquet(?)',[fpaths]).fetchone()[0]
            summary=report['phases'][role]
            if (queries!=actual_q or pairs!=actual_f or summary['queries']!=actual_q or summary['pairs']!=actual_f
                    or summary.get('diagnostic_phase_encoded_cardinality')!={name:len(values) for name,values in vocabulary.items()}):
                raise ValueError('Physical phase cover/cardinality differs from accepted inputs/report')
            check()
    finally:con.close()


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train-acceptance',required=True,type=Path)
    parser.add_argument('--selection-acceptance',required=True,type=Path)
    parser.add_argument('--gate-acceptance',required=True,type=Path)
    parser.add_argument('--execution-approval',required=True,type=Path)
    args=parser.parse_args()
    run_export(args.train_acceptance,args.selection_acceptance,args.gate_acceptance,execution_approval=args.execution_approval)


if __name__=='__main__':main()
