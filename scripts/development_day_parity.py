"""Independent Oct22 mechanical parity; no owner, grant, models, Y or metrics.

Import is stdlib only. compare_tables uses a caller-owned DuckDB connection;
verify_request is the closed future post-owner adapter. Both require the SAME
original stage's check callback. They never issue acceptance or start a process.
"""
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

DAY = '2019-10-22T00:00:00Z'
DAY_SQL = "TIMESTAMP '2019-10-22 00:00:00'"
ROOT = Path('/Users/mdpospelov/tlab-recsys-2026')
HANDOFF_SHA = 'fd7304383e9c025d205a0b7f9060187f8062daa9baa2f9b0f86ea6a18323e05b'
SCOPE = 'existing018_oct22_source_to_scores_postselection_development'
GROUP_POLICY = 'full4000selectionQsortedquery_id row_number_minus1 BEFORE dayfilter; comparebyquery_id,product_id'
ATOL = 1e-12
JSON_CAP = 262144
MAX_PAIRS = 440000
ALL_PAIRS = 817149
OUTPUTS = {'queries':'queries.parquet', 'candidates':'candidates.parquet',
           'base_features':'base-features.parquet', 'extra_features':'extra-features.parquet',
           'B':'B-scores.parquet', 'W':'W-scores.parquet'}
Q_SCHEMA = [('query_id','VARCHAR'),('user_id','BIGINT'),('anchor','TIMESTAMP'),
 ('eligibility_events','BIGINT'),('history_events_7d','BIGINT'),('history_distinct_items_7d','BIGINT'),
 ('history_active_days_7d','BIGINT'),('last_history_time','TIMESTAMP'),
 ('history_coverage_7d','DOUBLE'),('label_is_mature','BOOLEAN')]
C_SCHEMA = [('query_id','VARCHAR'),('product_id','BIGINT'),('from_popular','BOOLEAN'),
 ('from_recent','BOOLEAN'),('popularity_distinct_users','BIGINT'),('popular_source_rank','BIGINT'),
 ('recent_source_rank','BIGINT'),('last_user_event_time','TIMESTAMP')]
# Frozen explicit schemas/names are expanded below at source preparation time.
B_SCHEMA = [('query_id', 'VARCHAR'), ('product_id', 'BIGINT'), ('from_popular', 'BOOLEAN'), ('from_recent', 'BOOLEAN'), ('popularity_distinct_users', 'BIGINT'), ('popular_source_rank', 'BIGINT'), ('recent_source_rank', 'BIGINT'), ('last_user_event_time', 'TIMESTAMP'), ('user_id', 'BIGINT'), ('anchor', 'TIMESTAMP'), ('candidate_category_id', 'BIGINT'), ('candidate_category_ambiguous', 'BOOLEAN'), ('candidate_category_missing', 'BOOLEAN'), ('item_has_observed_history', 'BOOLEAN'), ('user_has_observed_history', 'BOOLEAN'), ('item_observed_age_seconds', 'DOUBLE'), ('user_observed_age_seconds', 'DOUBLE'), ('user_view_7d', 'BIGINT'), ('user_cart_7d', 'BIGINT'), ('user_purchase_7d', 'BIGINT'), ('user_distinct_viewed_items_7d', 'BIGINT'), ('pair_view_7d', 'BIGINT'), ('pair_cart_7d', 'BIGINT'), ('pair_purchase_7d', 'BIGINT'), ('pair_view_recency_seconds', 'DOUBLE'), ('pair_purchase_recency_seconds', 'DOUBLE'), ('item_view_24h', 'BIGINT'), ('item_purchase_24h', 'BIGINT'), ('item_distinct_viewers_7d', 'BIGINT'), ('user_category_view_7d', 'BIGINT'), ('user_category_view_recency_seconds', 'DOUBLE'), ('item_category_view_7d', 'BIGINT'), ('category_view_7d', 'BIGINT'), ('source_coverage_24h', 'DOUBLE'), ('source_coverage_168h', 'DOUBLE'), ('user_category_view_share_7d', 'DOUBLE'), ('item_category_view_share_7d', 'DOUBLE'), ('pair_view_recency_seconds_missing', 'BOOLEAN'), ('pair_purchase_recency_seconds_missing', 'BOOLEAN'), ('user_category_view_7d_missing', 'BOOLEAN'), ('user_category_view_share_7d_missing', 'BOOLEAN'), ('user_category_view_recency_seconds_missing', 'BOOLEAN'), ('item_category_view_7d_missing', 'BOOLEAN'), ('category_view_7d_missing', 'BOOLEAN'), ('item_category_view_share_7d_missing', 'BOOLEAN')]
E_SCHEMA = [('query_id', 'VARCHAR'), ('product_id', 'BIGINT'), ('auto_item_view_count_distinct_24h_user_id', 'BIGINT'), ('auto_item_cart_count_distinct_168h_user_id', 'BIGINT'), ('auto_item_purchase_count_distinct_24h_user_id', 'BIGINT')]
B_MODEL = ['from_popular', 'from_recent', 'popularity_distinct_users', 'popular_source_rank', 'recent_source_rank', 'candidate_category_ambiguous', 'candidate_category_missing', 'item_has_observed_history', 'user_has_observed_history', 'item_observed_age_seconds', 'user_observed_age_seconds', 'user_view_7d', 'user_cart_7d', 'user_purchase_7d', 'user_distinct_viewed_items_7d', 'pair_view_7d', 'pair_cart_7d', 'pair_purchase_7d', 'pair_view_recency_seconds', 'pair_purchase_recency_seconds', 'item_view_24h', 'item_purchase_24h', 'item_distinct_viewers_7d', 'user_category_view_7d', 'user_category_view_recency_seconds', 'item_category_view_7d', 'category_view_7d', 'source_coverage_24h', 'source_coverage_168h', 'user_category_view_share_7d', 'item_category_view_share_7d', 'pair_view_recency_seconds_missing', 'pair_purchase_recency_seconds_missing', 'user_category_view_7d_missing', 'user_category_view_share_7d_missing', 'user_category_view_recency_seconds_missing', 'item_category_view_7d_missing', 'category_view_7d_missing', 'item_category_view_share_7d_missing', 'retrieval_last_event_age_seconds', 'retrieval_last_event_missing']
W_MODEL = ['from_popular', 'from_recent', 'popularity_distinct_users', 'popular_source_rank', 'recent_source_rank', 'candidate_category_ambiguous', 'candidate_category_missing', 'item_has_observed_history', 'user_has_observed_history', 'item_observed_age_seconds', 'user_observed_age_seconds', 'user_view_7d', 'user_cart_7d', 'user_purchase_7d', 'user_distinct_viewed_items_7d', 'pair_view_7d', 'pair_cart_7d', 'pair_purchase_7d', 'pair_view_recency_seconds', 'pair_purchase_recency_seconds', 'item_view_24h', 'item_purchase_24h', 'item_distinct_viewers_7d', 'user_category_view_7d', 'user_category_view_recency_seconds', 'item_category_view_7d', 'category_view_7d', 'source_coverage_24h', 'source_coverage_168h', 'user_category_view_share_7d', 'item_category_view_share_7d', 'pair_view_recency_seconds_missing', 'pair_purchase_recency_seconds_missing', 'user_category_view_7d_missing', 'user_category_view_share_7d_missing', 'user_category_view_recency_seconds_missing', 'item_category_view_7d_missing', 'category_view_7d_missing', 'item_category_view_share_7d_missing', 'retrieval_last_event_age_seconds', 'retrieval_last_event_missing', 'auto_item_view_count_distinct_24h_user_id', 'auto_item_cart_count_distinct_168h_user_id', 'auto_item_purchase_count_distinct_24h_user_id']
S_SCHEMA = [('query_id','VARCHAR'),('product_id','BIGINT'),('raw_score','DOUBLE')]
RAW_SCHEMA = [('group','INTEGER'),('product_id','BIGINT'),('raw_score','DOUBLE')]
TABLE_KEYS = {'old_q','old_c','old_b','old_union','new_q','new_c','new_b','new_e',
              'old_B_raw','old_W_raw','score_B','score_W'}
INTERNAL_RELATIONS = frozenset(name.casefold() for name in (
    'parity_global_q','parity_day_q','parity_day_c','parity_day_b','parity_day_e',
    'parity_B_all','parity_B_day','parity_W_all','parity_W_day'))


def need(value, message):
    if not value:
        raise ValueError(message)


def quote(name):
    need(type(name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name),
         'Declared safe relation/column name required')
    return '"' + name + '"'


def run(con, sql, params=(), *, check):
    check(); result = con.execute(sql, list(params)); check(); return result


def scalar(con, sql, *, check):
    return run(con, sql, check=check).fetchone()[0]


def schema(con, relation, expected, *, check):
    actual = [tuple(row[:2]) for row in run(con, 'DESCRIBE ' + quote(relation), check=check).fetchall()]
    need(actual == expected, 'Physical schema/order: ' + relation)


def unique(con, relation, keys, cap, *, check):
    fields = ','.join(quote(n) for n in keys)
    nulls = ' OR '.join(quote(n) + ' IS NULL' for n in keys)
    count, distinct, invalid = run(con, 'SELECT count(*),count(DISTINCT (' + fields +
        ')),count(*) FILTER(WHERE ' + nulls + ') FROM ' + quote(relation), check=check).fetchone()
    need(count == distinct and invalid == 0 and count <= cap, 'Unique nonnull bounded keys: ' + relation)
    return count


def same_keys(con, left, right, keys, *, check):
    fields = ','.join(quote(n) for n in keys)
    need(scalar(con, 'SELECT count(*) FROM ((SELECT ' + fields + ' FROM ' + quote(left) +
        ' EXCEPT ALL SELECT ' + fields + ' FROM ' + quote(right) + ') UNION ALL (SELECT ' + fields +
        ' FROM ' + quote(right) + ' EXCEPT ALL SELECT ' + fields + ' FROM ' + quote(left) + '))', check=check) == 0,
        'Complete key multiset: ' + left + '/' + right)


def equal_columns(con, left, right, columns, keys, *, check):
    """NULL exact, finite DOUBLE abs<=1e-12; all other physical values exact."""
    same_keys(con, left, right, keys, check=check)
    conditions = []
    for name, dtype in columns:
        a, b = 'a.' + quote(name), 'b.' + quote(name)
        if dtype == 'DOUBLE':
            conditions.append('((' + a + ' IS NULL) != (' + b + ' IS NULL) OR (' + a +
                ' IS NOT NULL AND (NOT isfinite(' + a + ') OR NOT isfinite(' + b + ') OR abs(' + a + '-' + b + ') > 1e-12)))')
        else:
            conditions.append(a + ' IS DISTINCT FROM ' + b)
    joined = ' FROM ' + quote(left) + ' a JOIN ' + quote(right) + ' b USING(' + ','.join(quote(n) for n in keys) + ')'
    need(scalar(con, 'SELECT count(*)' + joined + ' WHERE ' + ' OR '.join(conditions), check=check) == 0,
         'All physical values/NULL/finite DOUBLE: ' + left + '/' + right)


def _matrix(con, base, extra, rows, *, check):
    """Independent SQL projection; canonical NaN for missing, exact float32 bits."""
    import numpy as np
    names = W_MODEL
    fields = ['CAST(f.' + quote(n) + ' AS FLOAT) AS ' + quote(n) for n in B_MODEL[:-2]]
    fields += ['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) AS retrieval_last_event_age_seconds',
               'CAST(f.last_user_event_time IS NULL AS FLOAT) AS retrieval_last_event_missing']
    fields += ['CAST(e.' + quote(n) + ' AS FLOAT) AS ' + quote(n) for n in W_MODEL[41:]]
    arrays = run(con, 'SELECT ' + ','.join(fields) + ' FROM ' + quote(base) + ' f JOIN ' +
        quote(extra) + ' e USING(query_id,product_id) ORDER BY f.query_id,f.product_id', check=check).fetchnumpy()
    check(); matrix = np.empty((rows, 44), dtype=np.float32)
    for index, name in enumerate(names):
        column = arrays[name]
        need(len(column) == rows and column.dtype == np.dtype('float32'), 'Exact bounded FLOAT projection')
        matrix[:, index] = column.filled(np.nan) if np.ma.isMaskedArray(column) else column
    need(not np.isinf(matrix).any(), 'Infinite float32 model representation')
    check(); return matrix


def compare_tables(con, tables, *, check, all_queries=4000, all_pairs=ALL_PAIRS, day_queries=2000):
    """All-keyed compare API, no file IO. Low count overrides are for tiny tests.

    Closed verify_request never accepts count overrides. Tables are explicit
    source-only Q/C/B/selected-union + six fresh outputs + two raw NPZ relations.
    """
    need(callable(check) and type(tables) is dict and set(tables) == TABLE_KEYS, 'Exact independent relation interface')
    for name in tables.values(): quote(name)
    # DuckDB identifiers are case-insensitive, even when quoted. Reject every
    # internal alias before the first SQL statement can overwrite caller data.
    folded = {name.casefold() for name in tables.values()}
    need(len(folded) == len(tables), 'Distinct case-insensitive input relations required')
    need(not folded & INTERNAL_RELATIONS, 'Reserved internal relation names forbidden')
    need(type(all_queries) is int and 1 <= all_queries <= 4000 and type(all_pairs) is int
         and 0 <= all_pairs <= ALL_PAIRS and type(day_queries) is int and 0 <= day_queries <= 2000,
         'Finite comparison populations required')
    t = tables
    for key in ('old_q','new_q'): schema(con, t[key], Q_SCHEMA, check=check)
    for key in ('old_c','new_c'): schema(con, t[key], C_SCHEMA, check=check)
    for key in ('old_b','new_b'): schema(con, t[key], B_SCHEMA, check=check)
    schema(con, t['new_e'], E_SCHEMA, check=check)
    for role in ('B','W'):
        schema(con, t['score_' + role], S_SCHEMA, check=check)
        schema(con, t['old_' + role + '_raw'], RAW_SCHEMA, check=check)
    union_schema = [tuple(r[:2]) for r in run(con, 'DESCRIBE ' + quote(t['old_union']), check=check).fetchall()]
    need(len(union_schema) == 57 and len(dict(union_schema)) == 57 and
         all(dict(union_schema).get(n) == typ for n, typ in E_SCHEMA), 'Old union57 chosen-three explicit types')
    need(unique(con, t['old_q'], ['query_id'], 4000, check=check) == all_queries, 'Complete original Q population')
    need(unique(con, t['new_q'], ['query_id'], 2000, check=check) == day_queries, 'Complete new day Q population')
    for key in ('old_q','new_q'):
        q = quote(t[key])
        need(scalar(con, 'SELECT count(*) FROM ' + q + ' WHERE user_id IS NULL OR anchor IS NULL OR '
             'label_is_mature IS DISTINCT FROM TRUE', check=check) == 0, 'Q key/calendar maturity')
        need(scalar(con, 'SELECT count(*)-count(DISTINCT(user_id,anchor)) FROM ' + q, check=check) == 0,
             'Unique complete user/day Q')
    need(scalar(con, 'SELECT count(*) FROM ' + quote(t['new_q']) + ' WHERE anchor != ' + DAY_SQL, check=check) == 0,
         'Only fixed Oct22 anchors')
    # Full original Q map is materialized before filtering; no day-local group reuse.
    run(con, 'CREATE OR REPLACE TEMP TABLE parity_global_q AS SELECT *,row_number() OVER(ORDER BY query_id)-1 AS _group FROM ' + quote(t['old_q']), check=check)
    run(con, 'CREATE OR REPLACE TEMP VIEW parity_day_q AS SELECT ' + ','.join(quote(n) for n,_ in Q_SCHEMA) +
        ' FROM parity_global_q WHERE anchor=' + DAY_SQL, check=check)
    equal_columns(con, 'parity_day_q', t['new_q'], Q_SCHEMA, ['query_id'], check=check)
    pair_keys = ['query_id','product_id']
    for key in ('old_c','old_b'):
        need(unique(con, t[key], pair_keys, ALL_PAIRS, check=check) == all_pairs, 'Complete original pair population')
    same_keys(con, t['old_c'], t['old_b'], pair_keys, check=check)
    for side in ('old','new'):
        c, b, q = (quote(t[side + '_' + suffix]) for suffix in ('c','b','q'))
        need(scalar(con, 'SELECT count(*) FROM ' + c + ' c LEFT JOIN ' + q + ' q USING(query_id) '
            'WHERE q.query_id IS NULL OR c.last_user_event_time>=q.anchor', check=check) == 0, 'Candidate query/strict-past closure')
        need(scalar(con, 'SELECT count(*) FROM ' + b + ' b LEFT JOIN ' + q + ' q USING(query_id) '
            'WHERE q.query_id IS NULL OR b.user_id IS DISTINCT FROM q.user_id OR b.anchor IS DISTINCT FROM q.anchor '
            'OR b.last_user_event_time>=q.anchor', check=check) == 0, 'Base query/time closure')
        need(scalar(con, 'SELECT coalesce(max(n),0) FROM (SELECT count(*) n FROM ' + c + ' GROUP BY query_id)', check=check) <= 220,
             'Per-query complete candidate cap')
    for source, dest in [('old_c','parity_day_c'),('old_b','parity_day_b')]:
        run(con, 'CREATE OR REPLACE TEMP VIEW ' + quote(dest) + ' AS SELECT s.* FROM ' + quote(t[source]) +
            ' s JOIN parity_day_q q USING(query_id)', check=check)
    # Never slice union57 by prefix: selected extras come only from these three names.
    run(con, 'CREATE OR REPLACE TEMP VIEW parity_day_e AS SELECT ' + ','.join(quote(n) for n,_ in E_SCHEMA) +
        ' FROM ' + quote(t['old_union']), check=check)
    rows = unique(con, t['new_c'], pair_keys, MAX_PAIRS, check=check)
    for key in ('new_b','new_e','score_B','score_W'):
        need(unique(con, t[key], pair_keys, MAX_PAIRS, check=check) == rows, 'Complete fresh pair transport')
        same_keys(con, t['new_c'], t[key], pair_keys, check=check)
    unique(con, 'parity_day_e', pair_keys, MAX_PAIRS, check=check)
    same_keys(con, 'parity_day_b', 'parity_day_e', pair_keys, check=check)
    for old, fresh, columns in [('parity_day_c','new_c',C_SCHEMA),('parity_day_b','new_b',B_SCHEMA),('parity_day_e','new_e',E_SCHEMA)]:
        equal_columns(con, old, t[fresh], columns, pair_keys, check=check)
    import numpy as np
    old_matrix = _matrix(con, 'parity_day_b', 'parity_day_e', rows, check=check)
    new_matrix = _matrix(con, t['new_b'], t['new_e'], rows, check=check)
    need(np.array_equal(old_matrix.view(np.uint32), new_matrix.view(np.uint32)), 'Exact float32 model representation bits')
    matrix_hashes = {role:hashlib.sha256(np.ascontiguousarray(new_matrix[:,:n]).tobytes()).hexdigest()
                     for role,n in [('B',41),('W',44)]}
    del old_matrix, new_matrix
    scores = {}
    for role in ('B','W'):
        raw = quote(t['old_' + role + '_raw']); fresh = quote(t['score_' + role])
        need(unique(con, t['old_' + role + '_raw'], ['group','product_id'], ALL_PAIRS, check=check) == all_pairs,
             'All saved NPZ rows exactly transported')
        need(scalar(con, 'SELECT count(*) FROM ' + raw + ' WHERE "group"<0 OR "group">=' + str(all_queries) +
            ' OR raw_score IS NULL OR NOT isfinite(raw_score)', check=check) == 0, 'Saved score finite/group domain')
        global_name = 'parity_' + role + '_all'; day_name = 'parity_' + role + '_day'
        run(con, 'CREATE OR REPLACE TEMP VIEW ' + quote(global_name) + ' AS SELECT q.query_id,s.product_id,s.raw_score '
            'FROM ' + raw + ' s JOIN parity_global_q q ON s."group"=q._group', check=check)
        same_keys(con, global_name, t['old_c'], pair_keys, check=check)
        run(con, 'CREATE OR REPLACE TEMP VIEW ' + quote(day_name) + ' AS SELECT s.* FROM ' + quote(global_name) +
            ' s JOIN parity_day_q q USING(query_id)', check=check)
        need(scalar(con, 'SELECT count(*) FROM ' + fresh + ' WHERE raw_score IS NULL OR NOT isfinite(raw_score)', check=check) == 0,
             'Fresh scores exact finite float64')
        equal_columns(con, day_name, t['score_' + role], S_SCHEMA, pair_keys, check=check)
        # Rank both raw score columns independently; tolerance does not forgive order changes.
        ranked = lambda rel: '(SELECT query_id,product_id,row_number() OVER(PARTITION BY query_id ORDER BY raw_score DESC,product_id ASC) r FROM ' + quote(rel) + ')'
        need(scalar(con, 'SELECT count(*) FROM ' + ranked(day_name) + ' a JOIN ' + ranked(t['score_' + role]) +
            ' b USING(query_id,product_id) WHERE a.r!=b.r', check=check) == 0, 'Complete raw-score/item tie rank: ' + role)
        delta = run(con, 'SELECT coalesce(max(abs(a.raw_score-b.raw_score)),0) FROM ' + quote(day_name) +
            ' a JOIN ' + fresh + ' b USING(query_id,product_id)', check=check).fetchone()[0]
        scores[role] = dict(rows=rows, max_abs_error=delta, complete_ranks_equal=True)
    check()
    return dict(version=1, scope='independent_Oct22_all_keyed_mechanical_parity',
        status='parity_checks_passed_pending_Root_and_full_exit', anchor=DAY,
        all_query_count=all_queries, all_pair_count=all_pairs, query_count=day_queries, candidate_count=rows,
        physical_columns=dict(Q=10,C=8,B=45,extra=5), model_columns=dict(B=41,W=44),
        double_policy='finite_abs_1e-12_exact_NULL_keys_ints_BOOL_timestamps', float32_policy='exact_uint32_bits_canonical_missing_NaN',
        model_representation_sha256=matrix_hashes, score_checks=scores, sampling='none_all_rows_and_full_ranks',
        target_relations_opened=0, model_files_opened=0, fit_attempts=0, metrics_computed=0,
        source_acceptance_issued=False, execution_authority_issued=False, external_exit_accepted=False)


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'Duplicate JSON key'); result[key] = value
    return result


def _json(raw):
    need(0 < len(raw) <= JSON_CAP, 'Bounded JSON required')
    def reject(value): raise ValueError('Nonfinite JSON: ' + value)
    def finite(value):
        number = float(value); need(math.isfinite(number), 'Nonfinite JSON float'); return number
    result = json.loads(raw.decode(), object_pairs_hook=_unique_json, parse_constant=reject, parse_float=finite)
    need(type(result) is dict, 'JSON object required'); return result


def _path(root, relative):
    need(type(relative) is str and relative and not relative.startswith('/') and '\\' not in relative,
         'Project-relative path required')
    pure = PurePosixPath(relative)
    need(str(pure) == relative and all(p not in ('','.','..') for p in pure.parts), 'Normalized relative path required')
    current = root
    for part in pure.parts:
        current = current / part; need(not current.is_symlink(), 'Symlink reference forbidden')
    need(current.resolve().is_relative_to(root), 'Reference escaped project'); return current


def _stat(path):
    s = path.stat(); need(stat.S_ISREG(s.st_mode), 'Regular pinned file required')
    return dict(device=s.st_dev,inode=s.st_ino,size_bytes=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)


def _hash(path, sha, check, *, cap):
    need(type(sha) is str and re.fullmatch('[0-9a-f]{64}', sha), 'Exact SHA256 required')
    before = _stat(path); need(0 < before['size_bytes'] <= cap, 'Bounded file required')
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            check(); chunk = f.read(1024*1024)
            if not chunk: break
            h.update(chunk)
    check(); need(_stat(path) == before and h.hexdigest() == sha, 'Pinned bytes changed: ' + path.name)
    return dict(sha256=sha,stat=before)


def _small(path, sha, check):
    pin = _hash(path, sha, check, cap=JSON_CAP)
    raw = path.read_bytes(); check()
    need(hashlib.sha256(raw).hexdigest() == sha and _stat(path) == pin['stat'], 'Small JSON reread changed')
    return _json(raw), pin


def _npz(con, path, table, *, check, rows=ALL_PAIRS, expected_sha=None):
    """One bounded immutable archive backs BOTH header validation and loading.

    The closed adapter supplies the externally pinned expected SHA. Direct tiny
    tests may omit it; byte/size/stat checks still bind their sole snapshot.
    """
    import numpy as np
    import pandas as pd
    need(type(rows) is int and 0 <= rows <= ALL_PAIRS, 'Bounded saved NPZ population')
    expected = {'group.npy':np.dtype('int32'),'product_id.npy':np.dtype('int64'),'raw_score.npy':np.dtype('float64')}
    # Include bounded header and ZIP/deflate overhead. This limits compressed
    # input allocation independently of ZIP member metadata or a changed path.
    compressed_cap = rows*20 + 4*65536
    check(); before = _stat(path)
    need(0 < before['size_bytes'] <= compressed_cap, 'Bounded compressed NPZ snapshot')
    with path.open('rb') as handle:
        raw = handle.read(compressed_cap+1)
    need(0 < len(raw) <= compressed_cap and len(raw) == before['size_bytes']
         and _stat(path) == before, 'NPZ snapshot file identity/size changed')
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None:
        need(type(expected_sha) is str and re.fullmatch('[0-9a-f]{64}',expected_sha)
             and digest == expected_sha, 'NPZ snapshot expected SHA256 differs')
    check()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        info = z.infolist()
        need(len(info) == 3 and {i.filename for i in info} == set(expected), 'Exactly three saved NPZ members')
        need(sum(item.file_size for item in info) <= rows*20+3*65536,
             'Bounded total uncompressed NPZ payload')
        for item in info:
            need(not item.is_dir() and item.file_size <= rows*expected[item.filename].itemsize+65536,
                 'Bounded uncompressed NPZ member')
            with z.open(item) as handle:
                version = np.lib.format.read_magic(handle)
                need(version in {(1,0),(2,0)}, 'Supported bounded NPY header')
                header = (np.lib.format.read_array_header_1_0 if version == (1,0) else np.lib.format.read_array_header_2_0)
                shape, fortran, dtype = header(handle, max_header_size=65536)
                need(shape == (rows,) and fortran is False and dtype == expected[item.filename],
                     'Exact NPY shape/dtype/order before allocation')
                need(item.file_size == handle.tell()+rows*dtype.itemsize, 'No trailing/truncated NPY bytes')
    check()
    with np.load(io.BytesIO(raw), allow_pickle=False, max_header_size=65536) as data:
        need(len(data.files) == 3 and set(data.files) == {'group','product_id','raw_score'}, 'Exact NPZ logical members')
        arrays = {name:data[name] for name in ('group','product_id','raw_score')}
    for name, array in arrays.items():
        need(type(array) is np.ndarray and array.shape == (rows,) and array.dtype == expected[name+'.npy'], 'Exact NPZ array')
    need(np.isfinite(arrays['raw_score']).all(), 'Saved float64 scores finite')
    check(); frame = pd.DataFrame(arrays, copy=False)
    con.register(table, frame); check()
    return frame  # retained until the caller connection is closed


def verify_request(request_path, expected_request_sha, *, check):
    """Future Root driver calls AFTER owner, inside its SAME 600CPU/900wall cap.

    No CLI, owner invocation, acceptance writer or lifetime reset. No actual
    source DB/CBM access. Only exact old references and six bound fresh outputs.
    The original request SHA is supplied externally by Root, never self-derived.
    """
    need(callable(check), 'Original-stage budget guard required')
    root = ROOT.resolve(strict=True)
    request, request_pin = _small(_path(root, request_path), expected_request_sha, check)
    need(set(request) == {'version','scope','execution_id','source','protocol','manual_registry','pool_contract',
        'models','reference_handoff','code','environment','resources','output_directory','comparison'}, 'Closed owner request fields')
    need(request.get('version') == 1 and request.get('scope') == SCOPE, 'Exact existing018 owner request scope')
    execution = request.get('execution_id')
    need(type(execution) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,94}[a-z0-9]|[a-z0-9]', execution), 'Exact execution ID')
    out = 'artifacts/development-source-to-score-runs/' + execution
    need(request.get('output_directory') == out and not request_path.startswith(out+'/'), 'Original fixed output namespace')
    handoff_ref = request.get('reference_handoff')
    need(type(handoff_ref) is dict and set(handoff_ref) == {'path','sha256'} and handoff_ref['sha256'] == HANDOFF_SHA,
         'Exact Root-prepared reference handoff binding')
    handoff, handoff_pin = _small(_path(root,handoff_ref['path']), HANDOFF_SHA, check)
    comparison = request.get('comparison'); refs = handoff['reference_artifacts']
    need(type(comparison) is dict and set(comparison) == {'mode','same_stage_budget','anchor','original_query_count',
        'original_group_mapping','key','required_checks','references'} and comparison['mode'] == 'external_independent_required'
        and comparison['same_stage_budget'] is True and comparison['anchor'] == DAY
        and type(comparison['original_query_count']) is int and comparison['original_query_count'] == 4000
        and comparison['original_group_mapping'] == GROUP_POLICY and comparison['key'] == ['query_id','product_id']
        and comparison['references'] == refs and comparison['required_checks'] == handoff['mandatory_parity'],
        'Exact closed comparison request/reference set')
    need(request.get('models') == handoff['models'] and request.get('source') == handoff['source'],
         'Source/model handoff detached from original request')
    need(request.get('manual_registry') == handoff['manual_registry'] and request.get('pool_contract') == handoff['pool_contract'],
         'Immutable registry/pool binding')
    resources = request.get('resources', {})
    need(set(resources) == {'total_cpu_seconds','total_wall_seconds','job_rss_bytes','threads','engine_memory',
        'spill_bytes','final_tail_cpu_seconds','final_tail_wall_seconds'} and
        all(type(resources.get(n)) is int and 0 < resources[n] <= upper for n,upper in
            [('total_cpu_seconds',600),('total_wall_seconds',900),('job_rss_bytes',8*2**30)])
        and resources.get('threads') == 2 and resources.get('engine_memory') == '2GB', 'Same finite original-stage resource request')
    need(handoff['models']['B']['feature_names'] == B_MODEL and handoff['models']['W']['feature_names'] == W_MODEL,
         'Explicit fixed B41/W44 names')
    report_path = _path(root,out+'/report.json')
    # The owner report is newly produced. Retain its raw bytes/hash as evidence,
    # then bind every selector to the externally pinned original request.
    need(_stat(report_path)['size_bytes'] <= JSON_CAP, 'Bounded owner report')
    report_raw = report_path.read_bytes(); report_sha = hashlib.sha256(report_raw).hexdigest()
    report_pin = _hash(report_path, report_sha, check, cap=JSON_CAP); report = _json(report_raw)
    need(report.get('scope') == SCOPE and report.get('execution_id') == execution
        and report.get('original_request_sha256') == expected_request_sha
        and report.get('status') == 'pending_independent_all_keyed_parity_and_full_exit_acceptance'
        and report.get('comparison') == comparison and report.get('independent_output_acceptance') is None
        and report.get('external_full_exit_acceptance') is None, 'Owner report original request/pending binding')
    need(report.get('resources') == resources, 'Owner original budget binding')
    association = report.get('source_model_code_environment_pins', {})
    associated_refs = [request['source']['database'],request['source']['prefix_acceptance'],request['source']['kernel_evidence'],
        request['protocol'],request['manual_registry'],request['pool_contract'],request['reference_handoff'],
        *[s['model'] for s in request['models'].values()]]
    associated_refs += [dict(path=n,sha256=h) for n,h in request['code'].items()]
    associated_refs += [request['environment'][n] for n in ('pyproject','uv_lock','external_supervisor')]
    need(set(association) == {r['path'] for r in associated_refs}|{'interpreter'}
         and all(association[r['path']].get('sha256') == r['sha256'] for r in associated_refs)
         and association['interpreter'].get('sha256') == request['environment']['interpreter_sha256'],
         'Owner complete source/model/code/environment fingerprint association')
    need(not _path(root,out+'/failure.json').exists(), 'Owner failure marker preserved; parity forbidden')
    need(report.get('fit_attempt_count') == 0 and report.get('metric_looks') == 0
         and report.get('query_targets_opened') is False and report.get('source_acceptance_issued') is False
         and report.get('execution_authority_issued') is False, 'Owner source-only boundaries')
    core = report.get('core', {})
    need(core.get('anchor') == DAY and core.get('query_count') == 2000
         and core.get('base_physical_columns') == 45 and core.get('chosen_physical_columns') == 48
         and core.get('model_columns') == {'B':41,'W':44} and core.get('fit_attempt_count') == 0
         and core.get('metric_looks') == 0 and core.get('query_target_relation_created') is False
         and core.get('reserved_targets_opened') is False, 'Owner fixed day/schema/no-target report')
    pins = {'request':request_pin,'handoff':handoff_pin,'owner_report':report_pin}; paths = {}
    output_pins = report.get('output_pins')
    need(type(output_pins) is dict and set(output_pins) == set(OUTPUTS) and
         core.get('outputs') == {n:out+'/'+leaf for n,leaf in OUTPUTS.items()}, 'Exact six owner outputs')
    for name, leaf in OUTPUTS.items():
        pin = output_pins[name]
        need(type(pin) is dict and set(pin) == {'path','sha256','stat'} and pin['path'] == out+'/'+leaf,
             'Fixed fresh output selector')
        path = _path(root,pin['path']); current = _hash(path,pin['sha256'],check,cap=512*2**20)
        need(current['stat'] == pin['stat'], 'Owner fresh output stat binding'); pins[pin['path']] = current; paths['new_'+name] = path
    old = {}
    for name in ('B_saved_scores','W_saved_scores','day_selected_union57'):
        old[name] = refs[name]
    for name in ('all_selection_queries','all_selection_candidates','all_selection_base45'):
        need(type(refs[name]) is list and len(refs[name]) == 1, 'Fixed single-shard references'); old[name] = refs[name][0]
    need(set(report.get('explicit_reference_pins',{})) == {r['path'] for r in old.values()}, 'Exact owner old-reference pins')
    for name, ref in old.items():
        path = _path(root,ref['path']); pin = _hash(path,ref['sha256'],check,cap=1024*2**20)
        need(pin == report['explicit_reference_pins'][ref['path']], 'Old frozen ref bytes/stat differ from owner')
        pins[ref['path']] = pin; paths[name] = path
    import duckdb
    con = duckdb.connect(':memory:',config={'threads':'2','memory_limit':'2GB','max_temp_directory_size':'0B'})
    frames = []
    try:
        selectors = {'old_q':'all_selection_queries','old_c':'all_selection_candidates',
                     'old_b':'all_selection_base45','old_union':'day_selected_union57',
                     'new_q':'new_queries','new_c':'new_candidates','new_b':'new_base_features','new_e':'new_extra_features',
                     'score_B':'new_B','score_W':'new_W'}
        for table, name in selectors.items():
            check(); con.read_parquet(str(paths[name])).create_view(table); check()
        for role in ('B','W'):
            frames.append(_npz(con,paths[role+'_saved_scores'],'old_'+role+'_raw',check=check,
                               expected_sha=old[role+'_saved_scores']['sha256']))
        result = compare_tables(con,{name:name for name in TABLE_KEYS},check=check)
        need(result['candidate_count'] == core.get('candidate_count'), 'Owner/core actual pair count binding')
        calls = 2 if result['candidate_count'] else 0
        progress = report.get('progress', {})
        need(report.get('actual_native_calls') == core.get('native_prediction_calls') == calls
             and progress.get('model_load_attempts') == 2
             and progress.get('native_prediction_attempts') == progress.get('native_prediction_returns') == calls
             and progress.get('source_connection_opened_read_only') is True and progress.get('source_connection_closed') is True,
             'Owner actual model/prediction/read-only close association')
    finally:
        con.close(); frames.clear(); check()
    # Fresh byte hashes AFTER all parsing/comparison bind semantics to exactly
    # the reviewed bytes, including retained initial small JSON digests.
    for name, pin in pins.items():
        if name == 'request': path = _path(root,request_path)
        elif name == 'handoff': path = _path(root,handoff_ref['path'])
        elif name == 'owner_report': path = report_path
        else: path = _path(root,name)
        need(_hash(path,pin['sha256'],check,cap=1024*2**20) == pin, 'Final byte/stat freshness: '+name)
    result.update(original_request_sha256=expected_request_sha, owner_report_sha256=report_sha,
                  execution_id=execution, input_output_byte_bindings=pins, same_original_stage_budget_required=True)
    check(); return result
