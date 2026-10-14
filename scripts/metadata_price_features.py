"""One strict-past metadata/price block over immutable query/candidate keys.

This module materializes no labels and performs no fits. Latest metadata uses
every row in the last GLOBAL timestamp bucket; fields resolve independently.
Nominal parquet values remain strings and are encoded as UTF8 bytes at loading.
"""
from copy import deepcopy
from datetime import datetime, timedelta

from scripts.anchor_pilot import _direct_stage, _no_budget_check

NOMINAL = ('category_id_nominal', 'category_code_by_id', 'brand')
NUMERIC = ('brand_missing', 'brand_ambiguous', 'code_missing', 'code_ambiguous',
           'code_recovered', 'log_price', 'price_missing', 'price_ambiguous',
           'price_zero', 'price_negative', 'category_peer_log_price_mean',
           'category_peer_product_support', 'category_log_price_difference',
           'category_peer_mean_missing', 'category_price_difference_missing')
SPEC = dict(version=1, name='metadata-price-v1', reference_hours=168,
            snapshot='latest_global_strict_past_bucket_all_rows',
            code_dictionary='unique_nonnull_code_per_clean_id_strict_past',
            reference='distinct_active_products_current_clean_category_valid_price',
            price_unit='unchanged_source_price_unit_not_assumed_currency',
            nonfinite_source='reject_relevant_latest_bucket_before_positive_filter',
            nominal_namespace='value:|state:missing|state:ambiguous',
            missing_flags='brand_price_no_clean_scalar_include_ambiguity_code_missing_dictionary_zero_or_unusable_id',
            one_hot_max_size=4096, nominal_columns=list(NOMINAL), numeric_columns=list(NUMERIC),
            gate=dict(max_queries=100, max_pairs=22000, wall_seconds=600,
                      threads=2, rss_bytes=8*2**30, max_spill_bytes=2*2**30))


def validate_spec(spec):
    # Fixed v1 block, not arbitrary executable expressions or a search space.
    if (not isinstance(spec, dict) or spec.keys() != SPEC.keys()
            or any(type(spec[k]) is not type(v) or spec[k] != v for k, v in SPEC.items())):
        raise ValueError('Metadata-price spec differs from fixed reviewed v1 semantics')
    # bool compares equal to integer in nested containers; reject such drift.
    if (type(spec['gate']) is not dict or spec['gate'].keys() != SPEC['gate'].keys()
            or any(type(spec['gate'][k]) is not int for k in SPEC['gate'])
            or any(type(x) is not str for x in spec['nominal_columns'] + spec['numeric_columns'])):
        raise ValueError('Metadata-price spec has invalid nested types')
    return deepcopy(spec)


def _field(name):
    clean = f'count(DISTINCT e.{name})=1 AND count(*) FILTER(WHERE e.{name} IS NULL)=0'
    ambiguous = f'(count(DISTINCT e.{name})>1 OR (count(DISTINCT e.{name})>0 AND count(*) FILTER(WHERE e.{name} IS NULL)>0))'
    return f'CASE WHEN {clean} THEN min(e.{name}) END {name}, {ambiguous} {name}_ambiguous'


def create_metadata_price_features(con, spec, *, source_start, source_end,
                                   stage=_direct_stage, budget_check=_no_budget_check,
                                   max_pairs=22000):
    """Read events + metadata_queries + metadata_pairs; write separate tables.

    metadata_pairs includes accepted candidate_category_id/ambiguity/missing
    solely to assert compatibility with005. It is never used as truth for the
    new snapshot. Output schema is two keys, three nominal, fifteen numeric.
    provenance/reference tables are audit evidence, excluded from model input.
    """
    validate_spec(spec)
    if (type(source_start) is not datetime or type(source_end) is not datetime
            or source_start.tzinfo is not None or source_end.tzinfo is not None
            or not source_start < source_end):
        raise ValueError('Source bounds must be increasing naive UTC timestamps')
    if type(max_pairs) is not int or not 1 <= max_pairs <= 6000000:
        raise ValueError('Invalid materialization pair cap')
    budget_check()
    q = con.execute('SELECT count(*),count(DISTINCT query_id),count(DISTINCT (user_id,anchor)) FROM metadata_queries').fetchone()
    invalid_q = con.execute('''SELECT count(*) FROM metadata_queries WHERE query_id IS NULL OR user_id IS NULL
        OR anchor IS NULL OR anchor<? OR anchor>=? OR anchor<>date_trunc('day',anchor)''', [source_start, source_end]).fetchone()[0]
    n, distinct = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM metadata_pairs').fetchone()
    invalid_c = con.execute('''SELECT count(*) FROM metadata_pairs p LEFT JOIN metadata_queries q USING(query_id)
        WHERE q.query_id IS NULL OR p.product_id IS NULL OR p.candidate_category_missing IS NULL
        OR p.candidate_category_ambiguous IS NULL''').fetchone()[0]
    if q != (q[0],)*3 or invalid_q or invalid_c or n != distinct or n > max_pairs:
        raise ValueError('Invalid immutable query/candidate keys or budget')
    # Typed zero-row outputs also replace any stale tables left by a prior call.
    con.execute('''CREATE OR REPLACE TEMP TABLE metadata_price_features(query_id VARCHAR,product_id BIGINT,
        category_id_nominal VARCHAR,category_code_by_id VARCHAR,brand VARCHAR,
        brand_missing BOOLEAN,brand_ambiguous BOOLEAN,code_missing BOOLEAN,code_ambiguous BOOLEAN,
        code_recovered BOOLEAN,log_price DOUBLE,price_missing BOOLEAN,price_ambiguous BOOLEAN,
        price_zero BOOLEAN,price_negative BOOLEAN,category_peer_log_price_mean DOUBLE,
        category_peer_product_support BIGINT,category_log_price_difference DOUBLE,
        category_peer_mean_missing BOOLEAN,category_price_difference_missing BOOLEAN)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE metadata_price_provenance(query_id VARCHAR,product_id BIGINT,
        anchor TIMESTAMP,latest_timestamp TIMESTAMP,category_id BIGINT,category_ambiguous BOOLEAN,
        latest_code VARCHAR,latest_code_ambiguous BOOLEAN,latest_brand VARCHAR,latest_brand_ambiguous BOOLEAN,
        latest_price DOUBLE,latest_price_ambiguous BOOLEAN,dictionary_code VARCHAR,
        dictionary_code_count BIGINT,dictionary_first_known TIMESTAMP,in_reference BOOLEAN)''')
    con.execute('''CREATE OR REPLACE TEMP TABLE metadata_price_reference(anchor TIMESTAMP,product_id BIGINT,
        category_id BIGINT,log_price DOUBLE)''')
    batches = []
    for (anchor,) in con.execute('SELECT DISTINCT anchor FROM metadata_queries ORDER BY anchor').fetchall():
        budget_check()
        day = anchor.strftime('%Y-%m-%d')
        def sql(name, query, params=None):
            return stage(name+'_'+day, lambda: con.execute(query, params or []))
        sql('choose_day', '''CREATE OR REPLACE TEMP TABLE mp_pairs AS SELECT p.* FROM metadata_pairs p
            JOIN metadata_queries q USING(query_id) WHERE q.anchor=?''', [anchor])
        sql('active_items', '''CREATE OR REPLACE TEMP TABLE mp_active AS SELECT DISTINCT product_id FROM events
            WHERE event_time>=? AND event_time<? AND product_id IS NOT NULL''',
            [max(source_start,anchor-timedelta(hours=168)),anchor])
        sql('relevant_items', '''CREATE OR REPLACE TEMP TABLE mp_items AS
            SELECT product_id FROM mp_active UNION SELECT product_id FROM mp_pairs''')
        sql('latest_timestamps', '''CREATE OR REPLACE TEMP TABLE mp_latest AS SELECT e.product_id,max(e.event_time) latest_timestamp
            FROM events e SEMI JOIN mp_items i USING(product_id)
            WHERE e.event_time>=? AND e.event_time<? GROUP BY e.product_id''', [source_start,anchor])
        sql('latest_buckets', '''CREATE OR REPLACE TEMP TABLE mp_bucket AS SELECT e.* FROM events e
            JOIN mp_latest m ON e.product_id=m.product_id AND e.event_time=m.latest_timestamp
            WHERE e.event_time>=? AND e.event_time<?''', [source_start,anchor])
        # NaN is not a missing price. Validate all relevant latest bucket rows,
        # including ambiguous/invalid-positive prices and outside-C references.
        if con.execute('SELECT count(*) FROM mp_bucket WHERE price IS NOT NULL AND NOT isfinite(CAST(price AS DOUBLE))').fetchone()[0]:
            raise ValueError('Nonfinite price in relevant strict-past latest bucket')
        expressions = ','.join(_field(name) for name in ['category_id','category_code','brand','price'])
        sql('resolve_independent_fields', f'''CREATE OR REPLACE TEMP TABLE mp_snapshot AS
            SELECT e.product_id,max(e.event_time) latest_timestamp,{expressions}
            FROM mp_bucket e GROUP BY e.product_id''')
        mismatch = con.execute('''SELECT count(*) FROM mp_pairs p LEFT JOIN mp_snapshot s USING(product_id)
            WHERE p.candidate_category_id IS DISTINCT FROM s.category_id
            OR p.candidate_category_ambiguous IS DISTINCT FROM coalesce(s.category_id_ambiguous,false)
            OR p.candidate_category_missing IS DISTINCT FROM (s.category_id IS NULL)''').fetchone()[0]
        if mismatch:
            raise ValueError('New global category snapshot differs from accepted005 category')
        sql('dictionary', '''CREATE OR REPLACE TEMP TABLE mp_dictionary AS
            SELECT e.category_id,count(DISTINCT e.category_code)::BIGINT code_count,
                min(e.category_code) one_code,min(e.event_time) first_known
            FROM events e SEMI JOIN (SELECT DISTINCT category_id FROM mp_snapshot WHERE category_id IS NOT NULL) c USING(category_id)
            WHERE e.event_time>=? AND e.event_time<? AND e.category_code IS NOT NULL GROUP BY e.category_id''',
            [source_start,anchor])
        sql('reference_rows', '''CREATE OR REPLACE TEMP TABLE mp_reference AS
            SELECT s.product_id,s.category_id,ln(1.0+CAST(s.price AS DOUBLE)) log_price
            FROM mp_snapshot s SEMI JOIN mp_active a USING(product_id)
            WHERE s.category_id IS NOT NULL AND s.price>0''')
        sql('reference_aggregates', '''CREATE OR REPLACE TEMP TABLE mp_category AS
            SELECT category_id,count(*)::BIGINT support,sum(log_price)::DOUBLE log_sum FROM mp_reference GROUP BY category_id''')
        sql('join_nullable_reference', '''CREATE OR REPLACE TEMP TABLE mp_values AS
            SELECT p.query_id,p.product_id,s.* EXCLUDE(product_id),d.code_count,d.one_code,d.first_known,
                r.product_id IS NOT NULL in_reference,
                CASE WHEN s.price>0 THEN ln(1.0+CAST(s.price AS DOUBLE)) END log_price,
                CASE WHEN s.category_id IS NOT NULL THEN coalesce(c.support,0)-(r.product_id IS NOT NULL)::BIGINT END peer_support,
                CASE WHEN s.category_id IS NOT NULL THEN coalesce(c.log_sum,0.0)-CASE WHEN r.product_id IS NOT NULL THEN r.log_price ELSE 0.0 END END peer_sum
            FROM mp_pairs p LEFT JOIN mp_snapshot s USING(product_id) LEFT JOIN mp_dictionary d USING(category_id)
            LEFT JOIN mp_category c USING(category_id) LEFT JOIN mp_reference r ON p.product_id=r.product_id''')
        sql('join_features', '''INSERT INTO metadata_price_features
            WITH mean AS (SELECT *,peer_sum/nullif(peer_support,0) peer_mean FROM mp_values),
            derived AS (SELECT *,log_price-peer_mean difference FROM mean)
            SELECT query_id,product_id,
                CASE WHEN category_id IS NOT NULL THEN 'value:'||CAST(category_id AS VARCHAR)
                    WHEN coalesce(category_id_ambiguous,false) THEN 'state:ambiguous' ELSE 'state:missing' END,
                CASE WHEN category_id IS NOT NULL AND code_count=1 THEN 'value:'||one_code
                    WHEN category_id IS NOT NULL AND code_count>1 THEN 'state:ambiguous' ELSE 'state:missing' END,
                CASE WHEN brand IS NOT NULL THEN 'value:'||brand
                    WHEN coalesce(brand_ambiguous,false) THEN 'state:ambiguous' ELSE 'state:missing' END,
                brand IS NULL,coalesce(brand_ambiguous,false),
                category_id IS NULL OR coalesce(code_count,0)=0,
                category_id IS NOT NULL AND coalesce(code_count,0)>1,
                category_id IS NOT NULL AND coalesce(code_count,0)=1 AND category_code IS DISTINCT FROM one_code,
                log_price,price IS NULL,coalesce(price_ambiguous,false),coalesce(price=0,false),coalesce(price<0,false),
                peer_mean,peer_support,difference,peer_mean IS NULL,difference IS NULL FROM derived''')
        sql('preserve_provenance', '''INSERT INTO metadata_price_provenance SELECT query_id,product_id,?::TIMESTAMP,
            latest_timestamp,category_id,coalesce(category_id_ambiguous,false),category_code,coalesce(category_code_ambiguous,false),
            brand,coalesce(brand_ambiguous,false),CAST(price AS DOUBLE),coalesce(price_ambiguous,false),
            CASE WHEN code_count=1 THEN one_code END,coalesce(code_count,0),first_known,in_reference FROM mp_values''', [anchor])
        sql('preserve_reference', 'INSERT INTO metadata_price_reference SELECT ?::TIMESTAMP,* FROM mp_reference', [anchor])
        batches.append(dict(anchor=anchor, pairs=con.execute('SELECT count(*) FROM mp_pairs').fetchone()[0],
                            reference_products=con.execute('SELECT count(*) FROM mp_reference').fetchone()[0]))
        budget_check()
    actual = [r[0] for r in con.execute('DESCRIBE metadata_price_features').fetchall()]
    if actual != ['query_id','product_id',*NOMINAL,*NUMERIC]:
        raise ValueError('Unexpected metadata-price model schema/order')
    uncovered = con.execute('''SELECT count(*) FROM (SELECT query_id,product_id FROM metadata_pairs
        EXCEPT SELECT query_id,product_id FROM metadata_price_features)''').fetchone()[0]
    count, unique = con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM metadata_price_features').fetchone()
    if count != n or count != unique or uncovered:
        raise ValueError('Metadata-price output does not exactly cover immutable keys')
    budget_check()
    return dict(queries=q[0], pairs=n, nominal_features=list(NOMINAL), numeric_features=list(NUMERIC), batches=batches)


def model_arrays(con, *, max_rows=22000):
    """Own FeaturesData validation; no estimator, target or learned encoder."""
    import numpy as np
    count = con.execute('SELECT count(*) FROM metadata_price_features').fetchone()[0]
    if type(max_rows) is not int or not 0 <= count <= max_rows:
        raise ValueError('Metadata-price matrix cap exceeded before allocation')
    rows = con.execute('SELECT '+','.join([*NUMERIC,*NOMINAL])+' FROM metadata_price_features ORDER BY query_id,product_id').fetchall()
    numeric = np.array([[np.nan if v is None else v for v in row[:len(NUMERIC)]] for row in rows], dtype=np.float32).reshape(count,len(NUMERIC))
    nominal = np.empty((count,len(NOMINAL)), dtype=object)
    for i,row in enumerate(rows):
        for j,value in enumerate(row[len(NUMERIC):]):
            if not isinstance(value,str) or not (value.startswith('value:') or value in {'state:missing','state:ambiguous'}):
                raise ValueError('Invalid nominal namespace/type')
            nominal[i,j] = value.encode('utf8')
    if np.isinf(numeric).any():
        raise ValueError('Nonfinite numeric value after float32 cast')
    for value,mask in [('log_price',None),('category_peer_log_price_mean','category_peer_mean_missing'),
                       ('category_log_price_difference','category_price_difference_missing')]:
        missing = np.isnan(numeric[:,NUMERIC.index(value)])
        if mask is not None and not np.array_equal(missing,numeric[:,NUMERIC.index(mask)].astype(bool)):
            raise ValueError('Numeric NULL/missing-mask mismatch')
    flag_indices = [i for i,n in enumerate(NUMERIC) if n not in {'log_price','category_peer_log_price_mean',
        'category_peer_product_support','category_log_price_difference'}]
    if any(not np.isin(numeric[:,i],[0,1]).all() for i in flag_indices):
        raise ValueError('Invalid boolean metadata flag')
    def flag(name):
        return numeric[:,NUMERIC.index(name)].astype(bool)
    price_unknown = flag('price_missing') | flag('price_zero') | flag('price_negative')
    if (not np.array_equal(np.isnan(numeric[:,NUMERIC.index('log_price')]),price_unknown)
            or np.any(flag('price_ambiguous') & ~flag('price_missing'))
            or np.any(flag('price_zero') & (flag('price_missing') | flag('price_negative')))
            or np.any(flag('price_negative') & flag('price_missing'))):
        raise ValueError('Price NULL/resolution-mask mismatch')
    for column,missing,ambiguous in [(2,'brand_missing','brand_ambiguous'),(1,'code_missing','code_ambiguous')]:
        values = nominal[:,column]
        expected_missing = np.isin(values,[b'state:missing',b'state:ambiguous']) if column==2 else values==b'state:missing'
        if not np.array_equal(flag(missing),expected_missing) or not np.array_equal(flag(ambiguous),values==b'state:ambiguous'):
            raise ValueError('Nominal resolution-mask mismatch')
    if np.any(flag('code_recovered') & np.isin(nominal[:,1],[b'state:missing',b'state:ambiguous'])):
        raise ValueError('Recovered code must be known')
    support = numeric[:,NUMERIC.index('category_peer_product_support')]
    if np.any(np.isfinite(support) & ((support<0) | (support!=np.floor(support)))):
        raise ValueError('Invalid distinct-product support')
    unknown_category = np.isin(nominal[:,0],[b'state:missing',b'state:ambiguous'])
    if (not np.array_equal(np.isnan(support),unknown_category)
            or not np.array_equal(flag('category_peer_mean_missing'),np.isnan(support) | (support==0))
            or not np.array_equal(flag('category_price_difference_missing'),price_unknown | flag('category_peer_mean_missing'))):
        raise ValueError('Conditional reference NULL/mask mismatch')
    return numeric, nominal


def validate_train_cardinality(nominal, *, maximum=4096):
    import numpy as np
    if type(maximum) is not int or maximum != 4096 or not isinstance(nominal,np.ndarray) or nominal.dtype != object or nominal.ndim != 2 or nominal.shape[1] != len(NOMINAL):
        raise ValueError('Invalid one-hot input contract')
    counts = {}
    for i,name in enumerate(NOMINAL):
        values = nominal[:,i].tolist()
        if any(type(v) is not bytes for v in values):
            raise ValueError('Nominal train values must be UTF8 bytes')
        for v in values:
            v.decode('utf8')
        counts[name] = len(set(values))
        if counts[name] > maximum:
            raise ValueError('Encoded train cardinality exceeds one-hot ceiling: '+name)
    return counts


# The only executable scope in v1 is this reviewed100-query diagnostic.
# Full exports and the one ablation fit need separate prospective approval.
from pathlib import Path
import hashlib
import json
import math
import resource
import time
import uuid

from scripts.protocol_manifest import (canonical_json,sha256_file,_read_json,_unique_object,
                                      _reject_constant,_relative_path,_utc)
from scripts.anchor_pilot import RunDeadline,StageLedger,peak_rss_bytes,directory_bytes,naive_utc
from scripts.development_collection import _atomic_json

ROOT=Path(__file__).resolve().parents[1]
GATE_ROLE='metadata_price_100q_source_cost_gate'
GATE_CODE=('uv.lock','scripts/metadata_price_features.py','scripts/train_baselines.py',
           'scripts/development_collection.py','scripts/protocol_manifest.py',
           'scripts/anchor_pilot.py','scripts/temporal_contract.py')


def _gate_local(name):
    _relative_path(name)
    path=(ROOT/name).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _gate_relative(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def _json_snapshot(path):
    raw=Path(path).read_bytes()
    body=json.loads(raw,object_pairs_hook=_unique_object,parse_constant=_reject_constant)
    return body,hashlib.sha256(raw).hexdigest()


def prepare_gate_plan(acceptance_path,spec_path,*,check=_no_budget_check):
    """Read-only plan preparation is not approval for source materialization."""
    from scripts.train_baselines import verify_collection
    spec_path=Path(spec_path).resolve()
    spec,digest=_json_snapshot(spec_path)
    validate_spec(spec)
    collection=verify_collection(acceptance_path,check=check)
    if collection['phase']['role']!='train' or collection['phase']['lock_required']:
        raise ValueError('Metadata100Q gate may open only the accepted train collection')
    pins=dict(collection['pins'])
    for name in [*GATE_CODE,_gate_relative(spec_path),'pyproject.toml']:
        check()
        actual=sha256_file(_gate_local(name))
        if name==_gate_relative(spec_path) and actual!=digest:
            raise ValueError('Metadata spec changed during plan preparation')
        if name in pins and actual!=pins[name]:
            raise ValueError('Accepted input/helper changed: '+name)
        pins[name]=actual
        check()
    identity=dict(version=1,role=GATE_ROLE,spec=spec,
        collection_id=collection['plan']['collection_id'],fingerprints=pins,
        query_selection='bottom_sha256_query_id_per_day_then_round_robin_day_rank_anchor_query_id_100',
        label_policy='no_label_table_loaded_or_parsed',
        outputs='fixed_keys_3nominal_15numeric_separate_provenance_and_full_reference_no_model')
    return dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity),collection


def choose_gate_queries(con):
    """Reads mp_all_queries only; the policy cannot depend on fullY or C."""
    con.execute('''CREATE OR REPLACE TEMP TABLE metadata_queries AS
        SELECT * EXCLUDE(day_rank) FROM (
            SELECT *,row_number() OVER(PARTITION BY anchor ORDER BY sha256(query_id),query_id) day_rank
            FROM mp_all_queries) ORDER BY day_rank,anchor,query_id LIMIT 100''')
    n,days=con.execute('SELECT count(*),count(DISTINCT anchor) FROM metadata_queries').fetchone()
    expected=min(100,con.execute('SELECT count(*) FROM mp_all_queries').fetchone()[0])
    if n!=expected or n==0 or days<2:
        raise ValueError('Metadata gate requires nonempty deterministic multi-day sample')
    by_day=[dict(anchor=t.strftime('%Y-%m-%dT%H:%M:%SZ'),queries=count) for t,count in
            con.execute('SELECT anchor,count(*) FROM metadata_queries GROUP BY anchor ORDER BY anchor').fetchall()]
    keys=[r[0] for r in con.execute('SELECT query_id FROM metadata_queries ORDER BY query_id').fetchall()]
    return dict(queries=n,days=days,by_day=by_day,
                query_key_sha256=hashlib.sha256(canonical_json(keys).encode()).hexdigest())


def _process_cpu_seconds():
    usage=resource.getrusage(resource.RUSAGE_SELF)
    value=float(usage.ru_utime+usage.ru_stime)
    if not math.isfinite(value) or value<0:
        raise ValueError('CPU user/system measurement unavailable')
    return value


def validate_gate_outputs(con):
    """Schema and relational output boundary, independent of stage success."""
    feature_types={'log_price':'DOUBLE','category_peer_log_price_mean':'DOUBLE',
        'category_peer_product_support':'BIGINT','category_log_price_difference':'DOUBLE'}
    expected={
        'metadata_price_features':[('query_id','VARCHAR'),('product_id','BIGINT')]
            +[(n,'VARCHAR') for n in NOMINAL]+[(n,feature_types.get(n,'BOOLEAN')) for n in NUMERIC],
        'metadata_price_provenance':[('query_id','VARCHAR'),('product_id','BIGINT'),('anchor','TIMESTAMP'),
            ('latest_timestamp','TIMESTAMP'),('category_id','BIGINT'),('category_ambiguous','BOOLEAN'),
            ('latest_code','VARCHAR'),('latest_code_ambiguous','BOOLEAN'),('latest_brand','VARCHAR'),
            ('latest_brand_ambiguous','BOOLEAN'),('latest_price','DOUBLE'),('latest_price_ambiguous','BOOLEAN'),
            ('dictionary_code','VARCHAR'),('dictionary_code_count','BIGINT'),('dictionary_first_known','TIMESTAMP'),('in_reference','BOOLEAN')],
        'metadata_price_reference':[('anchor','TIMESTAMP'),('product_id','BIGINT'),('category_id','BIGINT'),('log_price','DOUBLE')]
    }
    for table,schema in expected.items():
        if [tuple(r[:2]) for r in con.execute('DESCRIBE '+table).fetchall()]!=schema:
            raise ValueError('Metadata output schema/order mismatch: '+table)
    for table in ['metadata_price_features','metadata_price_provenance']:
        n,unique=con.execute('SELECT count(*),count(DISTINCT (query_id,product_id)) FROM '+table).fetchone()
        pairs=con.execute('SELECT count(*) FROM metadata_pairs').fetchone()[0]
        mismatch=con.execute('''SELECT count(*) FROM (
            (SELECT query_id,product_id FROM metadata_pairs EXCEPT SELECT query_id,product_id FROM '''+table+''')
            UNION ALL (SELECT query_id,product_id FROM '''+table+''' EXCEPT SELECT query_id,product_id FROM metadata_pairs))''').fetchone()[0]
        if n!=pairs or n!=unique or mismatch:
            raise ValueError('Metadata output key cover mismatch: '+table)
    if con.execute('''SELECT count(*) FROM metadata_price_provenance p JOIN metadata_queries q USING(query_id)
        WHERE p.anchor IS DISTINCT FROM q.anchor OR p.latest_timestamp>=q.anchor OR p.dictionary_first_known>=q.anchor
        OR p.category_ambiguous IS NULL OR p.latest_code_ambiguous IS NULL OR p.latest_brand_ambiguous IS NULL
        OR p.latest_price_ambiguous IS NULL OR p.in_reference IS NULL OR p.dictionary_code_count IS NULL
        OR p.dictionary_code_count<0''').fetchone()[0]:
        raise ValueError('Provenance strict-past/resolution boundary invalid')
    n,unique=con.execute('SELECT count(*),count(DISTINCT (anchor,product_id)) FROM metadata_price_reference').fetchone()
    invalid=con.execute('''SELECT count(*) FROM metadata_price_reference r
        LEFT JOIN (SELECT DISTINCT anchor FROM metadata_queries) q USING(anchor)
        WHERE q.anchor IS NULL OR r.product_id IS NULL OR r.category_id IS NULL OR r.log_price IS NULL
        OR NOT isfinite(r.log_price) OR r.log_price<0''').fetchone()[0]
    if n!=unique or invalid:
        raise ValueError('Full reference product key/value boundary invalid')
    disagreement=con.execute('''SELECT count(*) FROM metadata_price_provenance p
        LEFT JOIN metadata_price_reference r USING(anchor,product_id)
        WHERE p.in_reference IS DISTINCT FROM (r.product_id IS NOT NULL)''').fetchone()[0]
    if disagreement:
        raise ValueError('Reference membership differs from provenance')


def run_gate(acceptance_path,spec_path,*,gate_approval_path):
    """One immutable diagnostic with no fits, labels or larger-scope flags."""
    started=time.monotonic()
    cpu_started=None
    output_root=ROOT/'artifacts/metadata-price'
    directory=output_root/('attempt-'+uuid.uuid4().hex)
    directory.mkdir(parents=True,exist_ok=False)
    for name in ['profiles','temp']:(directory/name).mkdir()
    deadline=RunDeadline(600,started_at=started)
    ledger=StageLedger(directory/'profiles',deadline=deadline)
    report=dict(version=1,status='running',scope=GATE_ROLE,stages=ledger.rows,
                labels_loaded=False,fit_attempt_count=0,
                limits=SPEC['gate'],rss_enforcement='cooperative checks; no OS hard-kill claim')
    _atomic_json(directory/'report.json',report)
    manifest=con=timer=None
    def guard():
        deadline.check()
        if peak_rss_bytes()>SPEC['gate']['rss_bytes']:
            raise MemoryError('Metadata diagnostic cooperative RSS ceiling exceeded8GiB')
        if directory_bytes(directory/'temp')>SPEC['gate']['max_spill_bytes']:
            raise MemoryError('Metadata diagnostic temporary disk ceiling exceeded2GiB')
    def stage(name,operation):
        before=None
        index=len(ledger.rows)
        def checked():
            nonlocal before
            before=_process_cpu_seconds()
            guard()
            result=operation()
            guard()
            return result
        try:return ledger(name,checked)
        finally:
            if before is not None:
                try:ledger.rows[index]['process_cpu_user_system_seconds']=_process_cpu_seconds()-before
                except Exception as error:
                    ledger.rows[index].update(status='failed',cpu_measurement_error=str(error))
                    raise
    try:
        cpu_started=_process_cpu_seconds()
        manifest,collection=stage('verify_accepted_train_and_prepare_plan',
            lambda:prepare_gate_plan(acceptance_path,spec_path,check=guard))
        approval,approval_sha=_json_snapshot(gate_approval_path)
        expected=dict(version=1,approved=True,scope=GATE_ROLE,run_id=manifest['run_id'],
                      fingerprints=manifest['identity']['fingerprints'])
        if (not isinstance(approval,dict) or approval.keys()!=expected.keys()
                or type(approval['version']) is not int or approval['approved'] is not True or approval!=expected):
            raise ValueError('External reviewed100Q source/cost approval differs from actual plan')
        manifest['gate_approval']=dict(path=_gate_relative(gate_approval_path),sha256=approval_sha)
        identified=output_root/manifest['run_id']
        if identified.exists():
            raise FileExistsError('Existing metadata diagnostic preserved; recovery requires review')
        directory.rename(identified)
        directory=identified
        ledger.directory=directory/'profiles'
        report['run_id']=manifest['run_id']
        report['spec']=manifest['identity']['spec']
        report['collection_id']=manifest['identity']['collection_id']
        db=_gate_local(collection['plan']['execution_inputs']['source_path'])
        from scripts.train_baselines import environment_snapshot
        report['environment']=stage('verify_loaded_versions_against_lock',environment_snapshot)
        import duckdb
        con=stage('open_source_read_only',lambda:duckdb.connect(str(db),read_only=True))
        timer=deadline.interrupt_timer(con)
        ledger.connection=con
        con.execute('SET threads=2')
        con.execute("SET memory_limit='2GB'")
        con.execute("SET max_temp_directory_size='2GB'")
        con.execute('SET temp_directory=?',[str(directory/'temp')])
        con.execute('SET preserve_insertion_order=false')
        stage('load_accepted_query_table',lambda:con.execute(
            'CREATE TEMP TABLE mp_all_queries AS SELECT * FROM read_parquet(?)',
            [[str(_gate_local(p)) for p in collection['refs']['queries']]]))
        report['query_selection']=stage('select_queries_without_labels',lambda:choose_gate_queries(con))
        stage('fixed_base_pairs',lambda:con.execute('''CREATE TEMP TABLE metadata_pairs AS
            SELECT f.query_id,f.product_id,f.candidate_category_id,
                f.candidate_category_ambiguous,f.candidate_category_missing
            FROM read_parquet(?) f SEMI JOIN metadata_queries q USING(query_id)''',
            [[str(_gate_local(p)) for p in collection['refs']['features']]]))
        source=collection['plan']['identity']['shard_protocols'][0]['source']
        core=stage('materialize_separate_metadata',lambda:create_metadata_price_features(con,
            manifest['identity']['spec'],source_start=naive_utc(_utc(source['start'])),
            source_end=naive_utc(_utc(source['end'])),stage=stage,budget_check=guard,max_pairs=22000))
        # StageLedger rows are appended by nested SQL stages; record own CPU on
        # the parent by identity, not the last child (see stage implementation).
        core['batches']=[{**b,'anchor':b['anchor'].strftime('%Y-%m-%dT%H:%M:%SZ')} for b in core['batches']]
        report['materialization']=core
        stage('validate_exact_schema_key_provenance_reference_boundary',lambda:validate_gate_outputs(con))
        numeric,nominal=stage('validate_model_arrays_without_pool_or_fit',lambda:model_arrays(con))
        report['matrix']=dict(numeric_shape=list(numeric.shape),nominal_shape=list(nominal.shape),
            numeric_dtype=str(numeric.dtype),nominal_dtype=str(nominal.dtype),
            numeric_bytes=numeric.nbytes,nominal_pointer_bytes=nominal.nbytes,
            diagnostic_cardinality=validate_train_cardinality(nominal),
            cardinality_scope='100Q diagnostics; not full encoded training-cardinality proof')
        del numeric,nominal
        artifacts={}
        for name,table,order in [('queries','metadata_queries','query_id'),
            ('features','metadata_price_features','query_id,product_id'),
            ('provenance','metadata_price_provenance','query_id,product_id'),
            ('reference','metadata_price_reference','anchor,product_id')]:
            path=directory/(name+'.parquet')
            stage('export_'+name,lambda table=table,order=order,path=path:con.execute(
                'COPY (SELECT * FROM '+table+' ORDER BY '+order+') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(path)]))
            artifacts[name]=dict(path=_gate_relative(path),sha256=sha256_file(path),bytes=path.stat().st_size,
                rows=con.execute('SELECT count(*) FROM '+table).fetchone()[0],
                schema=[list(r[:2]) for r in con.execute('DESCRIBE '+table).fetchall()])
        report['artifacts']=artifacts
        manifest['outputs']=artifacts
        def reverify():
            pins={**manifest['identity']['fingerprints'],manifest['gate_approval']['path']:approval_sha}
            for name,digest in pins.items():
                guard()
                if sha256_file(_gate_local(name))!=digest:
                    raise ValueError('Reviewed input changed during metadata diagnostic: '+name)
            guard()
        stage('reverify_all_reviewed_inputs',reverify)
        report['status']='complete_produced_unreviewed'
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error))
        raise
    finally:
        had_failure=report.get('status')=='failed'
        terminal_errors=[]
        terminal_error=None
        def terminal_failure(error):
            nonlocal terminal_error
            terminal_error=terminal_error or error
            terminal_errors.append(dict(error_type=type(error).__name__,error=str(error)))
            report['status']='failed'
            if 'error_type' not in report:
                report.update(error_type=type(error).__name__,error=str(error))
        try:
            if timer is not None:timer.cancel()
            if con is not None:con.close()
        except Exception as error:terminal_failure(error)
        try:
            total_cpu=_process_cpu_seconds()-cpu_started if cpu_started is not None else None
            if total_cpu is None or total_cpu<0:
                raise ValueError('CPU measurement unavailable or nonmonotonic')
        except Exception as error:
            total_cpu=None
            report['cpu_measurement_error']=str(error)
            terminal_failure(error)
        if manifest is not None and report.get('run_id') is not None:
            try:_atomic_json(directory/'run.json',manifest)
            except Exception as error:terminal_failure(error)
        # Cleanup, close, final CPU reads and manifest serialization can cross
        # the limits too. An earlier successful SQL stage is not a final seal.
        try:guard()
        except Exception as error:terminal_failure(error)
        report.update(seconds=time.monotonic()-started,
            process_cpu_user_system_seconds=total_cpu,
            process_peak_rss_bytes=peak_rss_bytes(),temp_disk_bytes_after_close=directory_bytes(directory/'temp'))
        if terminal_errors:report['terminal_errors']=terminal_errors
        _atomic_json(directory/'report.json',report)
        # Check the audit write itself before returning success. If it crossed
        # a resource boundary, preserve the failure rather than a falsecomplete.
        if report['status']=='complete_produced_unreviewed':
            try:guard()
            except Exception as error:
                terminal_failure(error)
                report.update(terminal_errors=terminal_errors,seconds=time.monotonic()-started,
                    process_peak_rss_bytes=peak_rss_bytes())
                _atomic_json(directory/'report.json',report)
        print(json.dumps(dict(status=report['status'],run_id=report.get('run_id'),seconds=report['seconds'],
            process_cpu_user_system_seconds=report['process_cpu_user_system_seconds'])),flush=True)
        if terminal_error is not None and not had_failure:raise terminal_error
    return report


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection-acceptance',type=Path,required=True)
    parser.add_argument('--spec',type=Path,default=ROOT/'configs/features/metadata-price.json')
    parser.add_argument('--gate-approval',type=Path,required=True)
    args=parser.parse_args()
    run_gate(args.collection_acceptance,args.spec,gate_approval_path=args.gate_approval)


if __name__=='__main__':main()
