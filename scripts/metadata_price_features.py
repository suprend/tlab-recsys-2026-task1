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
