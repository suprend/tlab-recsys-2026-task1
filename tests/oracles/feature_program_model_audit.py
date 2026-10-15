"""Independent zero-fit observer for one approved fixed-procedure016 study.

Input consumers authenticate lineage only. This entry owns expected SQL arrays,
full-Y ranking mathematics, input witnesses and the frozen selection rule.
"""
import time
START = time.monotonic()
import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import re
import resource
import struct
import sys
import threading
import types

ROLE = 'fixed_procedure_feature_program_experiment'
SCOPE = ROLE + '_independent_model_output_observer'
SLOTS = ('I1', 'I2', 'R1', 'R2')
IDS = ('B', *SLOTS)
CLAIM = 'artifacts/feature-program-study/four-fit.claim.json'
METRICS = ('recall', 'ndcg', 'average_precision', 'reciprocal_rank')
ESTIMANDS = ('conditional_macro_query', 'all_query_zero', 'conditional_user_macro', 'all_user_macro_zero')
JSON_CAP = 16 * 2**20


def need(value, message):
    if not value:
        error = ValueError(message)
        error.assertion_id = hashlib.sha256(message.encode()).hexdigest()[:16]
        raise error


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse(raw):
    need(type(raw) is bytes, 'One verified raw JSON snapshot required')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def keys(value, expected, message):
    need(type(value) is dict and set(value) == set(expected), message)


def same(expected, actual, tolerance=1e-12):
    if type(expected) is dict:
        need(type(actual) is dict and set(expected) == set(actual), 'Object schema differs')
        for key, value in expected.items():
            same(value, actual[key], tolerance)
    elif type(expected) in (tuple, list):
        need(type(actual) in (tuple, list) and len(expected) == len(actual), 'Sequence schema differs')
        for left, right in zip(expected, actual):
            same(left, right, tolerance)
    elif type(expected) is float:
        need(type(actual) is float and math.isfinite(actual)
             and math.isclose(expected, actual, rel_tol=0, abs_tol=tolerance), 'Numerical value differs')
    else:
        need(type(expected) is type(actual) and expected == actual, 'Value or strict type differs')


def native_same(expected, actual):
    if type(expected) is dict:
        keys(actual, expected, 'Native parameter schema differs')
        for key in expected:
            native_same(expected[key], actual[key])
    elif type(expected) in (tuple, list):
        need(type(actual) in (tuple, list) and len(actual) == len(expected), 'Native sequence differs')
        for left, right in zip(expected, actual):
            native_same(left, right)
    elif type(expected) is float:
        need(type(actual) is float and math.isfinite(actual)
             and math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-12), 'Native serialized float differs')
    else:
        need(type(expected) is type(actual) and expected == actual, 'Native parameter type/value differs')


def select(candidates):
    """Independent global maximum band, not pairwise tolerance sorting."""
    need(type(candidates) is list and len(candidates) == 5, 'Exactly five allocated records required')
    by_id = {}
    for candidate in candidates:
        cid = candidate['candidate_id']
        need(cid in IDS and cid not in by_id, 'Original candidate identity cover differs')
        need(type(candidate['added_physical_columns']) is int
             and candidate['added_physical_columns'] == (0 if cid == 'B' else 3), 'Physical tie complexity differs')
        status = candidate['status']
        need(status in {'verified_success', 'resource_failed', 'allocation_collision'}, 'Incomplete or unsafe candidate')
        if status == 'verified_success':
            for name in ('ndcg', 'recall'):
                value = candidate['metrics']['conditional_macro_query'][name]
                need(finite(value) and 0 <= value <= 1, 'Invalid candidate metric')
        else:
            need(cid != 'B' and candidate['metrics'] is None, 'Failed candidate cannot be eligible')
        by_id[cid] = candidate
    need(set(by_id) == set(IDS) and by_id['B']['status'] == 'verified_success', 'Accepted baseline missing')
    threshold = by_id['B']['metrics']['conditional_macro_query']['recall'] - .002
    eligible = [c for c in candidates if c['status'] == 'verified_success'
                and c['metrics']['conditional_macro_query']['recall'] >= threshold]
    high = max(c['metrics']['conditional_macro_query']['ndcg'] for c in eligible)
    tied = [c for c in eligible if c['metrics']['conditional_macro_query']['ndcg'] >= high - 1e-12]
    return min(tied, key=lambda c: (c['added_physical_columns'], c['candidate_id']))


def metric_values(items, targets):
    if not targets:
        return None
    hits = [i for i, item in enumerate(items[:20], 1) if item in targets]
    dcg = math.fsum(1 / math.log2(i + 1) for i in hits)
    ideal = math.fsum(1 / math.log2(i + 1) for i in range(1, min(20, len(targets)) + 1))
    return dict(recall=len(hits) / len(targets), ndcg=dcg / ideal,
                average_precision=math.fsum(n / rank for n, rank in enumerate(hits, 1)) / len(targets),
                reciprocal_rank=1 / hits[0] if hits else 0.)


def summarize(queries, rankings):
    need(len(queries) == len(rankings), 'Every query ranking required')
    values = [metric_values(items, targets) for (_, _, _, targets), items in zip(queries, rankings)]
    users = defaultdict(list)
    for index, query in enumerate(queries):
        users[query[1]].append(index)
    positive = [i for i, value in enumerate(values) if value is not None]
    positive_users = [u for u, indices in users.items() if any(values[i] is not None for i in indices)]
    def avg(xs):
        return math.fsum(xs) / len(xs) if xs else None
    result = dict(k=20, query_count=len(queries), mature_query_count=len(queries), censored_query_count=0,
                  nonempty_query_count=len(positive), mature_user_count=len(users), positive_user_count=len(positive_users),
                  nonempty_fraction=len(positive) / len(queries) if queries else None)
    for estimand in ESTIMANDS:
        result[estimand] = {}
    for name in METRICS:
        result['conditional_macro_query'][name] = avg([values[i][name] for i in positive])
        result['all_query_zero'][name] = avg([v[name] if v else 0. for v in values])
        result['conditional_user_macro'][name] = avg([avg([values[i][name] for i in users[u] if values[i]]) for u in positive_users])
        result['all_user_macro_zero'][name] = avg([avg([values[i][name] if values[i] else 0. for i in indices]) for indices in users.values()])
    return result, values, dict(users)


def paired_bootstrap(winner, baseline, users):
    """Same200 user cluster draws for four NDCG estimands, descriptive only."""
    rng = random.Random(2026)
    ids = list(users)
    samples = {e: [] for e in ESTIMANDS}
    def estimate(values, draw, estimand):
        chunks = []
        for user in draw:
            qs = users[user]
            vals = [values[i]['ndcg'] if values[i] else 0. for i in qs
                    if values[i] or not estimand.startswith('conditional')]
            if 'user_macro' in estimand:
                if vals:
                    chunks.append([math.fsum(vals) / len(vals)])
            else:
                chunks.append(vals)
        flat = [v for chunk in chunks for v in chunk]
        return math.fsum(flat) / len(flat) if flat else None
    for _ in range(200):
        draw = rng.choices(ids, k=len(ids))
        for estimand in ESTIMANDS:
            left, right = estimate(winner, draw, estimand), estimate(baseline, draw, estimand)
            samples[estimand].append(None if left is None or right is None else left - right)
    result = {}
    for estimand in ESTIMANDS:
        defined = sorted(v for v in samples[estimand] if v is not None)
        def percentile(p):
            position = (len(defined) - 1) * p
            lo, hi = math.floor(position), math.ceil(position)
            return defined[lo] * (hi - position) + defined[hi] * (position - lo) if lo != hi else defined[lo]
        left, right = estimate(winner, ids, estimand), estimate(baseline, ids, estimand)
        result[estimand] = dict(metric='ndcg', estimand=estimand, seed=2026, replicates=200, user_count=len(ids),
            estimate=None if left is None or right is None else left - right,
            samples=samples[estimand], undefined_draws=200 - len(defined),
            interval_95=[percentile(.025), percentile(.975)] if defined else None)
    return result


@dataclass
class Matrix:
    queries: list
    group: object
    items: object
    x: object
    y: object
    feature_names: list


def matrix_proof(data, *, weights=None, check=lambda: None):
    import numpy as np
    need(sys.byteorder == 'little', 'Reviewed matrix witness requires little-endian host')
    arrays = {}
    for name, expected in [('x', '<f4'), ('group', '<i4'), ('items', '<i8'), ('y', '|i1')]:
        value = getattr(data, name)
        need(value.dtype.str == expected, 'Canonical matrix array dtype differs')
        h = hashlib.sha256()
        for start in range(0, len(value), 65536):
            check()
            block = np.array(value[start:start+65536], copy=True, order='C')
            if name == 'x':
                need(not np.isinf(block).any(), 'Infinite input matrix value')
                block[np.isnan(block)] = np.float32(np.nan)
            h.update(memoryview(block).cast('B'))
        arrays[name] = dict(shape=list(value.shape), dtype=expected, sha256=h.hexdigest())
    if weights is not None:
        need(weights.dtype.str == '<f8', 'Canonical query weight dtype differs')
        h = hashlib.sha256()
        for start in range(0, len(weights), 65536):
            check()
            h.update(memoryview(np.ascontiguousarray(weights[start:start+65536])).cast('B'))
        arrays['weights'] = dict(shape=list(weights.shape), dtype='<f8', sha256=h.hexdigest())
    rows = [dict(query_id=q, user_id=u, anchor=t.isoformat(), targets=sorted(targets)) for q, u, t, targets in data.queries]
    check()
    return dict(version=1, feature_names=list(data.feature_names), queries_sha256=digest(rows), query_count=len(rows),
                arrays=arrays, scope='canonical_input_value_witness_not_native_fit_weight_recovery')


def group_weights(data):
    import numpy as np
    counts = np.zeros(len(data.queries), dtype=np.int64)
    positive = np.zeros(len(data.queries), dtype=np.int64)
    need(np.isin(data.y, [0, 1]).all(), 'Binary development relevance required')
    if len(data.group):
        need(np.all(data.group >= 0) and np.all(data.group < len(counts))
             and np.all(data.group[1:] >= data.group[:-1]), 'Ordered group domain required')
        starts = np.r_[0, np.flatnonzero(data.group[1:] != data.group[:-1]) + 1]
        ids = data.group[starts]
        counts[ids] = np.diff(np.r_[starts, len(data.group)])
        positive[ids] = np.add.reduceat(data.y.astype(np.int64), starts)
    weights = np.reciprocal(counts[data.group].astype(np.float64))
    negative = counts - positive
    informative = (positive > 0) & (negative > 0)
    summary = dict(queries=len(data.queries), candidate_rows=len(data.group), nonempty_candidate_groups=int((counts > 0).sum()),
        empty_candidate_groups=int((counts == 0).sum()), informative_groups=int(informative.sum()),
        all_negative_groups=int(((counts > 0) & (positive == 0)).sum()), all_positive_groups=int(((counts > 0) & (negative == 0)).sum()),
        positive_fullY_queries=sum(bool(q[3]) for q in data.queries), retrieved_positive_rows=int(positive.sum()),
        zero_gradient_pairwise_groups=int((~informative).sum()), matrix_bytes=data.x.nbytes, row_weight_sum=float(weights.sum()))
    return weights, summary


def rankings(data, scores):
    import numpy as np
    scores = np.asarray(scores)
    need(scores.dtype.kind == 'f' and scores.shape == (len(data.items),) and np.isfinite(scores).all(), 'Finite exact score domain required')
    output = []
    cursor = 0
    for group in range(len(data.queries)):
        end = cursor
        while end < len(data.items) and int(data.group[end]) == group:
            end += 1
        order = sorted(range(cursor, end), key=lambda i: (-float(scores[i]), int(data.items[i])))
        output.append(tuple(int(data.items[i]) for i in order))
        cursor = end
    need(cursor == len(data.items), 'Sorted score group cover differs')
    return output


def quote(name):
    need(type(name) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name) is not None, 'Unsafe physical identifier')
    return '"' + name + '"'


def read_matrix(con, collection, base_names, *, local, cap, extra_paths=None, delta=(), check=lambda: None):
    """Independent SQL reconstruction; choose Q before opening any label view."""
    import numpy as np
    import pandas as pd
    need(collection['phase']['role'] in {'train', 'selection'}, 'Development collections only')
    need(cap is None or type(cap) is int and 1 <= cap <= 26000, 'Bounded frozen query population required')
    need(type(base_names) is list and len(base_names) == len(set(base_names)) == 41
         and base_names[-2:] == ['retrieval_last_event_age_seconds', 'retrieval_last_event_missing'], 'Exact ordered B41 required')
    for name in base_names:
        quote(name)
    need(len(delta) in (0, 3) and bool(delta) == (extra_paths is not None), 'Only zero or one exact three-column arm')
    names = [*base_names, *[v['name'] for v in delta]]
    need(len(names) == len(set(names)), 'Arm/base name collision')
    for value in delta:
        keys(value, {'name', 'dtype'}, 'Exact typed physical delta required')
        quote(value['name'])
        need(value['name'].startswith('auto_') and value['dtype'] in {'BIGINT', 'DOUBLE', 'BOOLEAN'}, 'Unsupported physical delta')
    dtypes = {v['name']: v['dtype'] for v in delta}
    for v in delta:
        if v['dtype'] == 'DOUBLE':
            need(dtypes.get(v['name'] + '_missing') == 'BOOLEAN', 'Same-arm recency mask closure required')
        if v['dtype'] == 'BOOLEAN':
            need(v['name'].endswith('_missing') and dtypes.get(v['name'][:-8]) == 'DOUBLE', 'Same-arm mask recency closure required')
    def paths(kind):
        values = collection['refs'][kind]
        need(type(values) is list and 1 <= len(values) <= 15 and len(values) == len(set(values)), 'Explicit approved phase files required')
        return [str(local(v)) for v in values]
    check()
    for kind in ('queries', 'features', 'candidates'):
        con.read_parquet(paths(kind)).create_view('ma_' + kind, replace=True)
    qt = {r[0]: r[1] for r in con.execute('DESCRIBE ma_queries').fetchall()}
    need(all(qt.get(n) == t for n, t in [('query_id', 'VARCHAR'), ('user_id', 'BIGINT'), ('anchor', 'TIMESTAMP'), ('label_is_mature', 'BOOLEAN')]), 'Query schema differs')
    limit = '' if cap is None else ' LIMIT ' + str(cap)
    con.execute('''CREATE OR REPLACE TEMP TABLE ma_chosen AS SELECT query_id,user_id,anchor,label_is_mature,
        row_number() OVER(ORDER BY query_id)-1 AS ma_group FROM
        (SELECT query_id,user_id,anchor,label_is_mature FROM ma_queries ORDER BY sha256(query_id),query_id''' + limit + ')')
    qn, qu, qa, bad = con.execute('''SELECT count(*),count(DISTINCT query_id),count(DISTINCT(user_id,anchor)),
        count(*) FILTER(WHERE query_id IS NULL OR user_id IS NULL OR anchor IS NULL OR label_is_mature IS DISTINCT FROM true) FROM ma_chosen''').fetchone()
    need(qn == qu == qa and qn <= 26000 and bad == 0, 'Mature unique query population differs')
    ft = {r[0]: r[1] for r in con.execute('DESCRIBE ma_features').fetchall()}
    ct = {r[0]: r[1] for r in con.execute('DESCRIBE ma_candidates').fetchall()}
    need(all(ft.get(n) == t for n, t in [('query_id', 'VARCHAR'), ('user_id', 'BIGINT'), ('product_id', 'BIGINT'), ('anchor', 'TIMESTAMP'), ('last_user_event_time', 'TIMESTAMP')])
         and ct.get('query_id') == 'VARCHAR' and ct.get('product_id') == 'BIGINT', 'Exact base integer/time schema differs')
    need(all(n in ft for n in base_names[:-2]), 'Base feature absent')
    con.execute('CREATE OR REPLACE TEMP VIEW ma_f AS SELECT f.* FROM ma_features f SEMI JOIN ma_chosen USING(query_id)')
    con.execute('CREATE OR REPLACE TEMP VIEW ma_c AS SELECT c.query_id,c.product_id FROM ma_candidates c SEMI JOIN ma_chosen USING(query_id)')
    n, nu = con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM ma_f').fetchone()
    need(n == nu and n <= 5720000 and n <= qn * 220, 'Bounded unique candidate domain differs')
    bad = con.execute('''SELECT count(*) FROM ma_f f JOIN ma_chosen q USING(query_id) WHERE
        f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor
        OR f.product_id IS NULL OR f.last_user_event_time>=q.anchor''').fetchone()[0]
    need(bad == 0, 'Feature/query identity or strict-past retrieval differs')
    pairdiff = con.execute('''SELECT count(*) FROM ((SELECT query_id,product_id FROM ma_f EXCEPT ALL SELECT * FROM ma_c)
        UNION ALL(SELECT * FROM ma_c EXCEPT ALL SELECT query_id,product_id FROM ma_f))''').fetchone()[0]
    need(pairdiff == 0, 'Base/C exact candidate key multiset differs')
    if delta:
        need(type(extra_paths) is list and 1 <= len(extra_paths) <= 15, 'Explicit accepted F57 phase required')
        con.read_parquet([str(local(v)) for v in extra_paths]).create_view('ma_extra', replace=True)
        et = {r[0]: r[1] for r in con.execute('DESCRIBE ma_extra').fetchall()}
        need(len(et) == 57 and et.get('query_id') == 'VARCHAR' and et.get('product_id') == 'BIGINT'
             and all(et.get(v['name']) == v['dtype'] for v in delta), 'Accepted F57/delta physical type differs')
        con.execute('CREATE OR REPLACE TEMP VIEW ma_e AS SELECT e.* FROM ma_extra e SEMI JOIN ma_chosen USING(query_id)')
        diff = con.execute('''SELECT count(*) FROM ((SELECT query_id,product_id FROM ma_e EXCEPT ALL SELECT query_id,product_id FROM ma_f)
            UNION ALL(SELECT query_id,product_id FROM ma_f EXCEPT ALL SELECT query_id,product_id FROM ma_e))''').fetchone()[0]
        need(diff == 0, 'Selected three source columns do not cover every B key')
        mismatch = con.execute('''SELECT count(*) FROM ma_e e JOIN ma_chosen q USING(query_id)
            WHERE e.user_id IS DISTINCT FROM q.user_id OR e.anchor IS DISTINCT FROM q.anchor''').fetchone()[0]
        need(mismatch == 0, 'Selected source query identity differs')
    need(n * (len(names)*4 + 4 + 8 + 1) <= 2*2**30, 'Matrix allocation cap before arrays')
    check()
    # The first label relation is opened only after fixed Q and physical C/F gates.
    con.read_parquet(paths('labels')).create_view('ma_labels', replace=True)
    yt = {r[0]: r[1] for r in con.execute('DESCRIBE ma_labels').fetchall()}
    need(yt.get('query_id') == 'VARCHAR' and yt.get('product_id') == 'BIGINT', 'FullY exact key type differs')
    con.execute('CREATE OR REPLACE TEMP VIEW ma_y AS SELECT y.query_id,y.product_id FROM ma_labels y SEMI JOIN ma_chosen USING(query_id)')
    yn, yu, ybad = con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)),count(*) FILTER(WHERE product_id IS NULL OR query_id IS NULL) FROM ma_y').fetchone()
    need(yn == yu and yn <= 2000000 and ybad == 0, 'FullY identity/cap differs')
    targets = defaultdict(set)
    for qid, item in con.execute('SELECT query_id,product_id FROM ma_y ORDER BY query_id,product_id').fetchall():
        targets[qid].add(item)
    queries = [(q, u, t, frozenset(targets[q])) for q, u, t in con.execute('SELECT query_id,user_id,anchor FROM ma_chosen ORDER BY ma_group').fetchall()]
    x = np.empty((n, len(names)), dtype=np.float32)
    group = np.empty(n, dtype=np.int32)
    items = np.empty(n, dtype=np.int64)
    y = np.empty(n, dtype=np.int8)
    fields = ['CAST(f.' + quote(name) + ' AS FLOAT) AS ' + quote(name) for name in base_names[:-2]]
    fields += ["CAST(date_diff('microsecond',f.last_user_event_time,f.anchor)/1000000.0 AS FLOAT) AS retrieval_last_event_age_seconds",
               'CAST(f.last_user_event_time IS NULL AS FLOAT) AS retrieval_last_event_missing']
    fields += ['CAST(e.' + quote(v['name']) + ' AS FLOAT) AS ' + quote(v['name']) for v in delta]
    join = ' JOIN ma_e e USING(query_id,product_id)' if delta else ''
    con.execute('SELECT q.ma_group,f.product_id,CAST(y.product_id IS NOT NULL AS TINYINT) AS ma_y,' + ','.join(fields)
                + ' FROM ma_f f JOIN ma_chosen q USING(query_id) LEFT JOIN ma_y y USING(query_id,product_id)' + join
                + ' ORDER BY q.ma_group,f.product_id')
    offset = 0
    previous = None
    while True:
        check()
        frame = con.fetch_df_chunk(32)
        if frame.empty:
            break
        size = len(frame)
        need(size <= 65536 and offset + size <= n, 'Bounded result chunk coverage differs')
        for name in ('ma_group', 'product_id'):
            need(pd.api.types.is_integer_dtype(frame[name].dtype) and not frame[name].isna().any(), 'Nonnullable exact integer transport required')
        gg = frame['ma_group'].to_numpy(dtype=np.int64)
        ii = frame['product_id'].to_numpy(dtype=np.int64)
        need(np.all(gg >= 0) and np.all(gg < qn) and np.all(gg[1:] >= gg[:-1])
             and not np.any((gg[1:] == gg[:-1]) & (ii[1:] <= ii[:-1]))
             and (previous is None or (int(gg[0]), int(ii[0])) > previous), 'Stable exact group/item ordering differs')
        previous = (int(gg[-1]), int(ii[-1]))
        sl = slice(offset, offset+size)
        x[sl] = frame[names].to_numpy(dtype=np.float32, na_value=np.nan)
        need(not np.isinf(x[sl]).any(), 'Infinite float32 model input')
        group[sl], items[sl], y[sl] = gg, ii, frame['ma_y'].to_numpy(dtype=np.int8)
        for j, value in enumerate(delta, 41):
            column = x[sl, j]
            if value['dtype'] == 'BIGINT':
                need(not np.isnan(column).any() and np.all(column >= 0), 'Invalid count state')
            elif value['dtype'] == 'BOOLEAN':
                need(not np.isnan(column).any() and np.isin(column, [0., 1.]).all(), 'Invalid missing mask')
            else:
                mask = value['name'] + '_missing'
                need(mask in names and np.array_equal(np.isnan(column), x[sl, names.index(mask)].astype(bool))
                     and np.all(column[~np.isnan(column)] > 0), 'Invalid recency/NULL/mask state')
        offset += size
    need(offset == n, 'Matrix cursor misses candidate rows')
    check()
    return Matrix(queries, group, items, x, y, names)


class Audit:
    def __init__(self, path, issued_context_sha256):
        self.phase = 'issuer_context'
        self.path = Path(path).resolve()
        with self.path.open('rb') as handle:
            raw = handle.read(65537)
        need(len(raw) <= 65536 and type(issued_context_sha256) is str
             and hashlib.sha256(raw).hexdigest() == issued_context_sha256, 'Original issuer context bytes differ')
        self.context = parse(raw)
        self.context_sha = issued_context_sha256
        c = self.context
        keys(c, {'version','scope','run_id','project_root','invocation_directory','request','producer_manifest',
                 'producer_report','oracle_source','allocation','issued_at_monotonic','output_path','failed_output_path'}, 'Context schema differs')
        need(type(c['version']) is int and c['version'] == 1 and c['scope'] == SCOPE
             and type(c['run_id']) is str and re.fullmatch('[0-9a-f]{64}', c['run_id']) is not None, 'Context scope differs')
        self.root = Path(c['project_root']).resolve()
        need(Path(c['project_root']).is_absolute(), 'Absolute checkout required')
        self.con = None
        self.timer = None
        self.stopped = threading.Event()
        self.expired = threading.Event()
        self.observed = {}
        self.allocation = c['allocation']
        a = self.allocation
        keys(a, {'cpu_seconds','deadline_monotonic','rss_bytes'}, 'Allocation schema differs')
        need(type(a['cpu_seconds']) is int and 1 <= a['cpu_seconds'] <= 600
             and type(a['rss_bytes']) is int and a['rss_bytes'] == 7*2**30
             and finite(a['deadline_monotonic']) and START < a['deadline_monotonic'] <= START+600,
             'Shared observer allocation differs')
        need(finite(c['issued_at_monotonic']) and 0 <= c['issued_at_monotonic'] <= START, 'Context issue clock differs')
        self.inv = self.local(c['invocation_directory'])
        self.directory = self.inv.parent
        need(self.directory.parent == self.root/'artifacts/feature-program-invocations'
             and re.fullmatch('[0-9a-f]{32}', self.directory.name) is not None and self.inv.name == 'observer', 'Original model invocation namespace')
        self.output = self.local(c['output_path'])
        self.failed = self.local(c['failed_output_path'])
        need(self.path == self.inv/'context.json' and self.output == self.inv/'evidence.json'
             and self.failed == self.inv/'evidence.failed.json', 'Observer outputs detached')
        need(not self.output.exists() and not self.failed.exists(), 'Immutable observer evidence exists')
        entry = Path(__file__).resolve()
        need(entry == self.root/'tests/oracles/feature_program_model_audit.py', 'Public observer entry differs from checkout')
        self.source = dict(path=str(entry.relative_to(self.root)), sha256=self.sha(entry))
        need(c['oracle_source'] == self.source, 'Observer source bytes differ')

    def local(self, name):
        need(type(name) is str and name and not Path(name).is_absolute() and '..' not in Path(name).parts, 'Nonlocal artifact')
        path = (self.root/name).resolve()
        need(path.is_relative_to(self.root), 'Artifact escaped checkout')
        return path

    def cpu(self):
        r = resource.getrusage(resource.RUSAGE_SELF)
        return r.ru_utime+r.ru_stime

    def rss(self):
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1024 if sys.platform.startswith('linux') else 1))

    def guard(self):
        need(sys.platform == 'darwin' or sys.platform.startswith('linux'), 'Unsupported RSS units')
        if self.expired.is_set() or time.monotonic() > self.allocation['deadline_monotonic'] or self.cpu() > self.allocation['cpu_seconds']:
            raise TimeoutError('Shared observer deadline/absolute CPU exhausted')
        if self.rss() > self.allocation['rss_bytes']:
            raise MemoryError('Observer RSS7GiB exceeded')
        r = resource.getrusage(resource.RUSAGE_CHILDREN)
        need(r.ru_utime+r.ru_stime == 0, 'Observer subprocesses forbidden')

    def timer_start(self):
        def monitor():
            while not self.stopped.wait(.1):
                try:
                    self.guard()
                except BaseException:
                    self.expired.set()
                    if self.con is not None:
                        try:
                            self.con.interrupt()
                        except BaseException:
                            pass
                    return
        self.timer = threading.Thread(target=monitor, daemon=True)
        self.timer.start()

    def sha(self, path):
        h = hashlib.sha256()
        with Path(path).open('rb') as handle:
            while block := handle.read(4*2**20):
                self.guard()
                h.update(block)
        self.guard()
        return h.hexdigest()

    def read(self, path):
        self.guard()
        with Path(path).open('rb') as handle:
            raw = handle.read(JSON_CAP+1)
        need(len(raw) <= JSON_CAP, 'Receipt JSON cap exceeded')
        body = parse(raw)
        self.guard()
        return body, hashlib.sha256(raw).hexdigest()

    def ref(self, value):
        keys(value, {'path','sha256'}, 'Exact artifact reference required')
        need(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None, 'Invalid artifact SHA')
        path = self.local(value['path'])
        body, hashed = self.read(path)
        need(hashed == value['sha256'], 'Referenced snapshot changed')
        self.observed[value['path']] = hashed
        return body

    def pins(self, values):
        need(type(values) is dict, 'Fingerprint map required')
        for name, hashed in values.items():
            need(type(hashed) is str and re.fullmatch('[0-9a-f]{64}', hashed) is not None, 'Invalid fingerprint')
            need(self.sha(self.local(name)) == hashed, 'Pinned bytes changed')

    def verified_module(self, name, pins):
        relative = name.replace('.', '/')+'.py'
        need(relative in pins, 'Mandatory executable input pin missing')
        path = self.local(relative)
        with path.open('rb') as handle:
            raw = handle.read(2*2**20+1)
        need(len(raw) <= 2*2**20 and hashlib.sha256(raw).hexdigest() == pins[relative], 'Executable snapshot changed')
        self.guard()
        module = types.ModuleType('_verified_'+name.replace('.', '_'))
        module.__file__ = str(path)
        module.__package__ = 'scripts'
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        self.guard()
        need(self.sha(path) == pins[relative], 'Executable changed during verified import')
        return module

    def binding(self):
        c = self.context
        need(c['producer_manifest']['path'] == str((self.directory/'run.json').relative_to(self.root))
             and c['producer_report']['path'] == str((self.directory/'producer-report.json').relative_to(self.root)), 'Producer receipt paths detached')
        request = self.ref(c['request'])
        keys(request, {'version','scope','run_id','producer_manifest','producer_report','execution_approval','budget_claim',
                       'oracle_source','shared_budget','original_owner','permissions'}, 'Observer request schema differs')
        need(type(request['version']) is int and request['version'] == 1 and request['scope'] == SCOPE
             and request['run_id'] == c['run_id'], 'Observer request scope differs')
        for key in ('producer_manifest','producer_report','oracle_source'):
            same(c[key], request[key])
        same(dict(observer_calls=1,refits=0,source_regenerations=0), request['permissions'])
        owner = request['original_owner']
        keys(owner, {'started_monotonic','absolute_deadline_monotonic'}, 'Original owner clock schema differs')
        need(all(finite(v) for v in owner.values()) and 0 <= owner['started_monotonic'] <= c['issued_at_monotonic']
             and owner['absolute_deadline_monotonic'] == owner['started_monotonic']+3600
             and self.allocation['deadline_monotonic'] <= owner['absolute_deadline_monotonic']-20, 'New observer clock outside original owner')
        budget = request['shared_budget']
        keys(budget, {'limit_cpu_seconds','charged_prefix_cpu_seconds','unknown_cost','source_paid_cpu_seconds',
                      'owner_parent_cpu_seconds','owner_reaped_children_cpu_seconds'}, 'Shared counter schema differs')
        need(type(budget['limit_cpu_seconds']) is int and budget['limit_cpu_seconds'] == 7200 and budget['unknown_cost'] is False
             and all(finite(budget[k]) and budget[k] >= 0 for k in budget if k not in {'limit_cpu_seconds','unknown_cost'})
             and budget['charged_prefix_cpu_seconds'] == budget['source_paid_cpu_seconds']+budget['owner_parent_cpu_seconds']+budget['owner_reaped_children_cpu_seconds']
             and budget['charged_prefix_cpu_seconds']+self.allocation['cpu_seconds'] <= 7200, 'Shared CPU reset/unknown/over allowance')
        m = self.ref(c['producer_manifest'])
        report = self.ref(c['producer_report'])
        keys(m, {'run_id','identity','execution_approval','budget_claim','outputs'}, 'Producer manifest schema differs')
        identity = m['identity']
        identity_keys = {'version','role','limits','fingerprints','source_run_id','source_acceptance','control_acceptance','selector','selector_path',
            'model_spec','model_parameters','native_reference','baseline','feature_names','slots','accepted_base_refs','collection_ids','daily_features',
            'expected_source_schema','paid_source_cpu_seconds','environment','interpretation','heldout_labels_opened','oracle_source','owner_attempt_claim'}
        keys(identity, identity_keys, 'Frozen model identity schema differs')
        need(type(identity['version']) is int and identity['version'] == 1 and identity['role'] == ROLE
             and identity['heldout_labels_opened'] is False and digest(identity) == m['run_id'] == c['run_id'], 'Model identity differs')
        need(identity['oracle_source'] == self.source and identity['fingerprints'].get(self.source['path']) == self.source['sha256'], 'Observer not part of original approved model inputs')
        same(request['execution_approval'], m['execution_approval'])
        same(request['budget_claim'], m['budget_claim'])
        approval = self.ref(m['execution_approval'])
        same(dict(version=1,approved=True,scope=ROLE,run_id=m['run_id'],fingerprints=identity['fingerprints']), approval)
        claim = self.ref(m['budget_claim'])
        need(m['budget_claim']['path'] == CLAIM, 'Original global four-fit claim namespace')
        same(dict(version=1,scope=ROLE,run_id=m['run_id'],allowed_fit_attempts=4,allowed_metric_looks=4,allowed_observer_attempts=1,
                  oracle_source=self.source,no_refill=True,output_directory=str(self.directory.relative_to(self.root)),execution_approval=m['execution_approval'],
                  slot_paths=[str((self.directory/'slots'/(slot+'.json')).relative_to(self.root)) for slot in SLOTS]), claim)
        parent = self.ref(dict(path=str((self.directory/'plan.json').relative_to(self.root)),sha256=m['outputs'][str((self.directory/'plan.json').relative_to(self.root))]))
        same({k:m[k] for k in ('run_id','identity','execution_approval','budget_claim')}, parent)
        keys(report, {'version','scope','run_id','status','fit_attempt_count','sum_metric_looks','children','candidates','winner','source_paid_cpu_seconds',
             'actual_parent_cpu_seconds','actual_reaped_children_cpu_seconds','charged_study_cpu_seconds','started_monotonic','producer_finished_monotonic',
             'original_absolute_deadline_monotonic','parent_peak_rss_bytes','heldout_labels_opened','active_slot','unknown_live_fit','unknown_metric_looks'}, 'Immutable producer report schema differs')
        need(type(report['version']) is int and report['version'] == 1 and report['scope'] == ROLE and report['run_id'] == m['run_id']
             and report['status'] == 'producer_complete_pending_independent_observer' and report['heldout_labels_opened'] is False
             and report['active_slot'] is None and report['unknown_live_fit'] is False and report['unknown_metric_looks'] is False,
             'Original complete producer report required')
        need(report['source_paid_cpu_seconds'] == identity['paid_source_cpu_seconds'] == budget['source_paid_cpu_seconds']
             and report['started_monotonic'] == owner['started_monotonic']
             and report['original_absolute_deadline_monotonic'] == owner['absolute_deadline_monotonic']
             and report['producer_finished_monotonic'] <= c['issued_at_monotonic'], 'Producer/source original clock differs')
        for key in ('actual_parent_cpu_seconds','actual_reaped_children_cpu_seconds','charged_study_cpu_seconds'):
            need(finite(report[key]) and report[key] >= 0, 'Unknown producer resource cost')
        need(report['charged_study_cpu_seconds'] == report['source_paid_cpu_seconds']+report['actual_parent_cpu_seconds']+report['actual_reaped_children_cpu_seconds']
             and report['actual_parent_cpu_seconds'] <= budget['owner_parent_cpu_seconds']
             and report['actual_reaped_children_cpu_seconds'] <= budget['owner_reaped_children_cpu_seconds']
             and type(report['parent_peak_rss_bytes']) is int and 0 < report['parent_peak_rss_bytes'] <= 2**30, 'Producer canonical resource prefix differs')
        for name in ('report.failed.json',):
            need(not (self.directory/name).exists(), 'Known failed model owner')
        once = self.ref(dict(path=str((self.inv/'once.claim.json').relative_to(self.root)),sha256=self.sha(self.inv/'once.claim.json')))
        same(dict(version=1,scope=SCOPE,run_id=m['run_id'],observer_calls=1,original_four_fit_claim=m['budget_claim'],request=c['request'],context_sha256=self.context_sha), once)
        launch, launch_sha = self.read(self.inv/'launch.json')
        same(dict(version=1,scope=SCOPE,run_id=m['run_id'],argv=[sys.executable,str(Path(__file__).resolve()),'--context',str(self.path),'--issued-context-sha256',self.context_sha],
             cwd=str(self.root),context_sha256=self.context_sha,request=c['request'],allocation=self.allocation,
             claim=dict(path=str((self.inv/'once.claim.json').relative_to(self.root)),sha256=self.sha(self.inv/'once.claim.json'))), launch)
        self.observed[str((self.inv/'launch.json').relative_to(self.root))] = launch_sha
        need(not self.failed.exists(),'Known failed observer')
        consumed_body = dict(version=1,scope=SCOPE+'_execution_consumed',run_id=m['run_id'],context_sha256=self.context_sha,
            request=c['request'],original_four_fit_claim=m['budget_claim'],oracle_source=self.source,observer_calls=1,refits=0,source_regenerations=0)
        consumed_path = self.inv/'execution.consumed.json'
        consumed_sha = self.persist(consumed_path,consumed_body)
        self.execution_consumed = dict(path=str(consumed_path.relative_to(self.root)),sha256=consumed_sha)
        self.observed[self.execution_consumed['path']] = consumed_sha
        self.pins(identity['fingerprints'])
        self.pins(m['outputs'])
        self.manifest, self.report, self.identity, self.parent = m, report, identity, parent
        return identity

    def lineage(self):
        """Authenticate accepted inputs; never borrow their feature/math loaders."""
        i = self.identity
        sys.path.insert(0, str(self.root))
        source_module = self.verified_module('scripts.recovered_feature_source', i['fingerprints'])
        control_module = self.verified_module('scripts.strong_control', i['fingerprints'])
        source = source_module.verify_source_acceptance(self.local(i['source_acceptance']), check=self.guard)
        control = control_module.verify_control(self.local(i['control_acceptance']), check=self.guard)
        same(dict(status='independently_verified_all_rows',source_formula_acceptance=True), source['physical'])
        same(control['selected_spec'], i['model_spec'])
        same(control['actual_model_parameters'], i['native_reference'])
        same(control['feature_names'], i['feature_names'])
        need(len(i['feature_names']) == 41 and len(set(i['feature_names'])) == 41, 'Exactly accepted B41 features required')
        spec = i['model_spec']
        for k in ('population','trained_iterations','scoring_prefix','depth','l2_leaf_reg'):
            need(type(spec[k]) is int and spec[k] > 0, 'Accepted procedure integer differs')
        need(spec['population'] in (6000,26000) and spec['scoring_prefix'] <= spec['trained_iterations'], 'Accepted procedure population/prefix differs')
        fixed = dict(loss_function='Logloss',iterations=spec['trained_iterations'],depth=spec['depth'],l2_leaf_reg=spec['l2_leaf_reg'],
            random_seed=2026,task_type='CPU',boosting_type='Plain',bootstrap_type='No',leaf_estimation_method='Newton',
            leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',random_strength=1,
            boost_from_average=False,use_best_model=False)
        for k,v in fixed.items():
            same(v, i['native_reference'][k])
        effective = struct.unpack('!f', struct.pack('!f', .05))[0]
        native_same(effective, i['native_reference']['learning_rate'])
        same(dict(fixed,learning_rate=.05,thread_count=2,border_count=254,nan_mode='Min',rsm=1,verbose=False,allow_writing_files=False), i['model_parameters'])
        same(dict(shared_cpu_seconds=7200,fit_wall_seconds=3600,verification_cpu_reserve=600,verification_wall_reserve=600,
            parent_launch_cpu_reserve=60,cleanup_wall_reserve=20,parent_rss_bytes=2**30,worker_rss_bytes=7*2**30,
            whole_job_rss_bytes=8*2**30,term_grace_seconds=5,kill_reap_seconds=5,log_bytes=2**20), i['limits'])
        need(i['interpretation'] == 'fixed_learner_conditional_feature_program_contrast_development_selection_not_heldout_quality', 'Development scope differs')
        same(control['manifest']['identity']['environment'], i['environment'])
        need(i['source_run_id'] == source['manifest']['run_id'] and i['paid_source_cpu_seconds'] == source['paid_source_cpu_seconds'], 'Source identity or paid lifetime differs')
        for role in ('train','selection'):
            need(i['accepted_base_refs'][role] == source['manifest']['identity']['acceptance_refs'][role] == control['acceptance_refs'][role]
                 and source['collections'][role]['plan']['collection_id'] == i['collection_ids'][role], 'Source/control base collection mismatch')
        same(source['daily_features'], i['daily_features'])
        need(all(part['artifacts']['features']['schema'] == i['expected_source_schema'] for parts in source['manifest']['outputs'].values() for part in parts)
             and len(i['expected_source_schema']) == 57, 'Accepted F57 schema differs')
        same([v['name'] for v in source['pool']['identity']['base_model_schema']], i['feature_names'])
        declared = {v['slot']:v for v in source['allocation']['identity']['slots']}
        keys(declared,SLOTS,'Original allocation cover differs')
        types_ = {v['name']:v['dtype'] for v in source['selected_union']['physical_delta']}
        need(len(types_) == 12, 'Selected union must have exactly12 physical columns')
        slots = {}
        for cid,bundle in zip(SLOTS,('L02','L06','L01','L05')):
            a = source['selected_union']['arms'][cid]
            need(a['status'] == declared[cid]['status'] == 'planned_unexecuted' and a['bundle_id'] == declared[cid]['bundle_id'] == bundle
                 and len(a['columns']) == len(set(a['columns'])) == 3, 'Original fixed arm changed')
            slots[cid] = dict(candidate_id=cid,bundle_id=bundle,columns=a['columns'],physical_delta=[dict(name=n,dtype=types_[n]) for n in a['columns']],feature_names=[*i['feature_names'],*a['columns']])
            same(slots[cid]['feature_names'], a['model_feature_order'])
        same(slots,i['slots'])
        same(dict(candidate_id='B',status='verified_success',added_physical_columns=0,metrics=control['winner']['metrics'],
            model_path=spec['model_path'],score_path=spec['score_path'],feature_names=i['feature_names']),i['baseline'])
        required = {}
        def merge(mapping):
            for k,v in mapping.items():
                need(k not in required or required[k] == v,'Conflicting accepted input pin')
                required[k] = v
        merge(source['pins']);merge(control['pins'])
        for ref in (source['acceptance'],control['acceptance']):
            merge({ref['path']:ref['sha256']})
        selector, selector_sha = self.read(self.local(i['selector_path']))
        same(selector,i['selector']); validate_selector(selector)
        merge({i['selector_path']:selector_sha})
        self.observed[i['selector_path']] = selector_sha
        code = ('scripts/feature_program_experiment.py','scripts/model_data.py','scripts/program_model_data.py',
                'scripts/strong_control.py','scripts/recovered_feature_source.py','scripts/ranking_metrics.py',self.source['path'],'uv.lock')
        for name in code:
            need(name in i['fingerprints'],'Required runtime code omitted')
            merge({name:i['fingerprints'][name]})
        owner = i['owner_attempt_claim']
        need(owner['path'] == 'artifacts/feature-program-study/fit-owner.claim.json','Owner claim namespace differs')
        original = self.ref(owner)
        same(dict(version=1,scope=ROLE+'_owner_attempt',allowed_owner_attempts=1,
            owner_source=dict(path=code[0],sha256=i['fingerprints'][code[0]]),source_acceptance=source['acceptance'],
            control_acceptance=control['acceptance'],selector=dict(path=i['selector_path'],sha256=selector_sha),
            output_directory=str(self.directory.relative_to(self.root)),started_monotonic=self.report['started_monotonic'],
            original_absolute_deadline_monotonic=self.report['original_absolute_deadline_monotonic']),original)
        merge({owner['path']:owner['sha256']})
        same(required,i['fingerprints'])
        self.source_inputs,self.control = source,control
        self.runtime_environment()

    def runtime_environment(self):
        import os,plistlib,tomllib
        from importlib.metadata import version
        import catboost,duckdb,numpy,pandas
        expected = self.identity['environment']
        loaded = {k:v.__version__ for k,v in [('catboost',catboost),('duckdb',duckdb),('numpy',numpy),('pandas',pandas)]}
        same(expected['loaded_packages'],loaded)
        need(sys.version == expected['python'],'Loaded Python differs')
        lock = tomllib.loads(self.local('uv.lock').read_text())['package']
        for k,v in loaded.items():
            need(version(k) == v and [p['version'] for p in lock if p['name'] == k] == [v],'Loaded/locked package differs')
        u = os.uname()
        need(sys.platform == 'darwin' and u.machine == 'arm64' and struct.calcsize('P') == 8,'Historical native host family differs')
        product = plistlib.loads(Path('/System/Library/CoreServices/SystemVersion.plist').read_bytes())['ProductVersion']
        need(expected['platform'] == 'macOS-'+product+'-arm64-arm-64bit','In-process platform differs')
        self.environment = dict(python=sys.version,loaded_packages=loaded,os_sysname=u.sysname,os_release=u.release,
            os_machine=u.machine,subprocesses_started=0,scope='loaded_versions_and_reviewed_host_family_no_platform_platform')
        self.guard()

    def workers(self):
        """All durable original launch/consumption bindings, including paid failures."""
        i,r = self.identity,self.report
        need(type(r['children']) is list and len(r['children']) == 4,'Every original child required')
        by_id,proofs,fit_count,look_count = {},{},0,0
        for child in r['children']:
            keys(child,{'slot','context','exit_code','actual_reaped_cpu_seconds','report','manifest','launch','worker_report','candidate'},'Child receipt schema differs')
            slot = self.ref(child['slot']);cid = slot['candidate_id']
            need(cid in SLOTS and cid not in by_id,'Original child cover differs')
            keys(slot,{'version','parent_run_id','candidate_id','token','allocation','context_path','output_root','look_reservations'},'Slot schema differs')
            need(type(slot['version']) is int and slot['version'] == 1 and slot['parent_run_id'] == r['run_id']
                 and type(slot['token']) is str and re.fullmatch('[0-9a-f]{32}',slot['token']) is not None,'Slot identity differs')
            need(child['slot']['path'] == str((self.directory/'slots'/(cid+'.json')).relative_to(self.root))
                 and slot['context_path'] == child['context']['path'] == str((self.directory/'slots'/(cid+'-context.json')).relative_to(self.root))
                 and slot['output_root'] == str((self.directory/'workers'/cid).relative_to(self.root)), 'Slot path binding differs')
            same([i['model_spec']['scoring_prefix']],slot['look_reservations'])
            a = slot['allocation'];keys(a,{'cpu_seconds','deadline_monotonic','rss_bytes'},'Worker allowance schema differs')
            need(type(a['cpu_seconds']) is int and 1 <= a['cpu_seconds'] <= 6540 and type(a['rss_bytes']) is int and a['rss_bytes'] == 7*2**30
                 and finite(a['deadline_monotonic']) and a['deadline_monotonic'] <= r['original_absolute_deadline_monotonic']-600-20,'Worker issued allowance differs')
            context = self.ref(child['context'])
            same(dict(version=1,parent_plan=dict(path=str((self.directory/'plan.json').relative_to(self.root)),sha256=self.manifest['outputs'][str((self.directory/'plan.json').relative_to(self.root))]),slot=child['slot']),context)
            consumed_path = str(self.local(child['slot']['path']).with_suffix('.consumed.json').relative_to(self.root))
            need(consumed_path in self.manifest['outputs'],'Paid consumed slot omitted')
            consumed_ref = dict(path=consumed_path,sha256=self.manifest['outputs'][consumed_path])
            same(dict(version=1,parent_run_id=r['run_id'],candidate_id=cid,token=slot['token'],context_sha256=child['context']['sha256'],allowed_fit_attempts=1,allowed_metric_looks=1),self.ref(consumed_ref))
            wi = dict(version=1,role=ROLE+'_worker',parent_plan=context['parent_plan'],slot=child['slot'],issued_context=child['context'],
                      consumed=consumed_ref,candidate=i['slots'][cid],procedure=i['model_spec'])
            wid = digest(wi);directory = self.local(slot['output_root'])/wid
            need(child['report']['path'] == str((directory/'report.json').relative_to(self.root))
                 and child['manifest']['path'] == str((directory/'run.json').relative_to(self.root)),'Worker output identity differs')
            manifest = self.ref(child['manifest']);report = self.ref(child['report'])
            keys(manifest,{'run_id','identity','outputs'},'Worker manifest schema differs')
            same(wi,manifest['identity']);need(manifest['run_id'] == wid,'Worker digest differs')
            same(report,child['worker_report'])
            required_report = {'version','status','scope','run_id','parent_run_id','candidate_id','bundle_id','added_columns','physical_delta','feature_names',
                'fit_attempt_count','look_reservations','labels_loaded','started_monotonic','allocation','outcome','stages',
                'actual_entry_cpu_seconds','actual_reaped_children_cpu_seconds','process_peak_rss_bytes','finished_monotonic','receipt_boundary','seconds'}
            successful_report = required_report | {'environment','training','train_preparation','train_matrix_proof','selection_preparation','selection_matrix_proof',
                'actual_model_parameters','metrics','artifacts','model_path','full_model_path','score_path'}
            if report['status'] == 'complete_produced_unreviewed':
                keys(report,successful_report,'Successful worker report schema differs')
            else:
                need(required_report | {'error','error_type'} <= set(report) <= successful_report | {'error','error_type'},'Failed worker report schema differs')
            launch = self.ref(child['launch'])
            keys(launch,{'version','scope','parent_run_id','candidate_id','argv','cwd','context','slot','allocation','log_path','issued_at_monotonic'},'Launch schema differs')
            need(finite(launch['issued_at_monotonic']) and r['started_monotonic'] <= launch['issued_at_monotonic'] <= report['started_monotonic'],'Launch original clock differs')
            same(dict(version=1,scope=ROLE,parent_run_id=r['run_id'],candidate_id=cid,
                argv=[sys.executable,str(self.local('scripts/feature_program_experiment.py')),'--worker','--context',str(self.local(child['context']['path'])),'--issued-context-sha256',child['context']['sha256']],
                cwd=str(self.root),context=child['context'],slot=child['slot'],allocation=a,log_path=str((self.directory/'logs'/(cid+'.log')).relative_to(self.root)),
                issued_at_monotonic=launch['issued_at_monotonic']),launch)
            need(child['launch']['path'] == str((self.directory/'logs'/(cid+'.launch.json')).relative_to(self.root)),'Launch receipt path differs')
            need(type(child['exit_code']) is int and finite(child['actual_reaped_cpu_seconds']) and child['actual_reaped_cpu_seconds'] >= 0,'Unknown child exit/cost')
            for key in ('version','run_id','parent_run_id','candidate_id','scope','allocation'):
                same(dict(version=1,run_id=wid,parent_run_id=r['run_id'],candidate_id=cid,scope=ROLE+'_worker',allocation=a)[key],report[key])
            need(type(report['fit_attempt_count']) is int and report['fit_attempt_count'] in (0,1)
                 and type(report['actual_reaped_children_cpu_seconds']) in (int,float) and report['actual_reaped_children_cpu_seconds'] == 0
                 and finite(report['actual_entry_cpu_seconds']) and 0 <= report['actual_entry_cpu_seconds'] <= child['actual_reaped_cpu_seconds']+1e-6
                 and type(report['process_peak_rss_bytes']) is int and 0 < report['process_peak_rss_bytes']
                 and report['process_peak_rss_bytes']+r['parent_peak_rss_bytes'] <= 8*2**30
                 and finite(report['started_monotonic']) and finite(report['finished_monotonic'])
                 and report['started_monotonic'] <= report['finished_monotonic'] <= r['producer_finished_monotonic'], 'Child cost/clock unknown or whole-cap violation')
            need(finite(report['seconds']) and report['seconds'] == report['finished_monotonic']-report['started_monotonic'],'Worker clock duration differs')
            fits = report['fit_attempt_count'];looks = report['look_reservations']
            need(type(looks) is list and len(looks) == 1 and type(looks[0]['prefix']) is int
                 and looks[0]['prefix'] == i['model_spec']['scoring_prefix'],'Original one-look reservation differs')
            fit_count += fits;look_count += int(looks[0]['status'].startswith('seen'))
            if report['status'] == 'complete_produced_unreviewed':
                need(child['exit_code'] == 0 and report['outcome'] == 'arm_complete' and fits == 1 and report['labels_loaded'] is True
                     and report['actual_entry_cpu_seconds'] <= a['cpu_seconds'] and child['actual_reaped_cpu_seconds'] <= a['cpu_seconds']
                     and report['finished_monotonic'] <= a['deadline_monotonic'] and report['process_peak_rss_bytes'] <= a['rss_bytes']
                     and not (directory/'report.failed.json').exists(),'Late/known failed arm cannot be eligible')
                arm = i['slots'][cid]
                same(arm['bundle_id'],report['bundle_id']);same(arm['columns'],report['added_columns']);same(arm['physical_delta'],report['physical_delta']);same(arm['feature_names'],report['feature_names'])
                expected = {str((directory/n).relative_to(self.root)) for n in ('full.cbm','full.json','prefix.cbm','scores.npz')}
                need(set(manifest['outputs']) == expected,'Successful four-file closure differs')
                same(manifest['outputs'],report['artifacts'])
                for k,n in [('full_model_path','full.cbm'),('model_path','prefix.cbm'),('score_path','scores.npz')]:
                    need(report[k] == str((directory/n).relative_to(self.root)),'Worker model/score path differs')
                same(dict(prefix=i['model_spec']['scoring_prefix'],status='seen_complete',metrics=report['metrics']),looks[0])
                candidate = dict(candidate_id=cid,status='verified_success',added_physical_columns=3,metrics=report['metrics'],model_path=report['model_path'],score_path=report['score_path'],feature_names=report['feature_names'])
            else:
                need(child['exit_code'] != 0 and report['status'] == 'failed' and report['outcome'] == 'resource_failure'
                     and report['error_type'] in {'MemoryError','TimeoutError','OutOfMemoryException'},'Non-resource/unknown failure causes STOP')
                need(looks[0]['status'] in {'reserved_consumed','seen_evaluation_started','seen_complete'},'Unknown failure look status')
                need((directory/'report.failed.json').exists(),'Failed arm marker required')
                candidate = dict(candidate_id=cid,status='resource_failed',added_physical_columns=3,metrics=None)
            same(candidate,child['candidate'])
            self.pins(manifest['outputs'])
            for path,hashed in manifest['outputs'].items():
                need(self.manifest['outputs'].get(path) == hashed and self.local(path).is_relative_to(directory),'Worker output not part of parent closure')
            for ref in (child['slot'],child['context'],child['report'],child['manifest'],child['launch'],consumed_ref):
                need(self.manifest['outputs'].get(ref['path']) == ref['sha256'],'Parent omitted durable child proof')
            by_id[cid] = (report,manifest,child,directory)
            proofs[cid] = dict(report=child['report'],manifest=child['manifest'],slot=child['slot'],context=child['context'],launch=child['launch'],
                status='preserved_paid_resource_failure' if candidate['status'] == 'resource_failed' else 'saved_model_and_input_witness_replayed')
        need(set(by_id) == set(SLOTS) and type(r['fit_attempt_count']) is int and r['fit_attempt_count'] == fit_count <= 4
             and type(r['sum_metric_looks']) is int and r['sum_metric_looks'] == look_count <= 4,'Fit/seen-look count differs')
        need(math.fsum(c['actual_reaped_cpu_seconds'] for c in r['children']) <= r['actual_reaped_children_cpu_seconds']+1e-6,'Children costs exceed canonical reaped prefix')
        expected_paths = {str((self.directory/n).relative_to(self.root)) for n in ('plan.json','winner.json')}
        for name in ('slots','logs','workers'):
            for path in (self.directory/name).rglob('*'):
                self.guard()
                if path.is_file():expected_paths.add(str(path.relative_to(self.root)))
        need(set(self.manifest['outputs']) == expected_paths,'Whole physical worker/slot/log closure differs')
        self.worker_data,self.worker_proofs = by_id,proofs

    def model_scores(self, data, model_path, score_path, *, actual, full_path=None, json_path=None):
        import numpy as np
        from catboost import CatBoostClassifier
        spec = self.identity['model_spec']
        fixed = self.identity['model_parameters']
        reference = self.identity['native_reference']
        for k in ('loss_function','iterations','depth','l2_leaf_reg','random_seed','task_type','boosting_type','bootstrap_type',
                  'leaf_estimation_method','leaf_estimation_iterations','leaf_estimation_backtracking','random_strength','boost_from_average','use_best_model'):
            same(fixed[k],actual[k])
        for k in ('learning_rate','border_count','nan_mode','rsm'):
            native_same(reference[k],actual[k])
        for k,v in dict(eval_metric='Logloss',auto_class_weights='None',grow_policy='SymmetricTree',feature_border_type='GreedyLogSum').items():
            same(v,actual[k])
        self.guard()
        saved = np.load(self.local(score_path),allow_pickle=False)
        try:
            need(set(saved.files) == {'group','product_id','raw_score'},'Saved score schema differs')
            group,items,scores = saved['group'],saved['product_id'],saved['raw_score']
            need(group.dtype.str == '<i4' and items.dtype.str == '<i8' and scores.dtype.str == '<f8'
                 and np.array_equal(group,data.group) and np.array_equal(items,data.items)
                 and scores.shape == data.items.shape and np.isfinite(scores).all(),'Saved scores exact keyed domain differs')
        finally:saved.close()
        prefix = CatBoostClassifier()
        prefix.load_model(str(self.local(model_path)))
        self.guard()
        need(type(prefix.tree_count_) is int and prefix.tree_count_ == spec['scoring_prefix'] and prefix.feature_names_ == data.feature_names
             and prefix.get_cat_feature_indices() == [],'Saved numeric scoring prefix/schema differs')
        native_same(actual,prefix.get_all_params())
        replay = np.asarray(prefix.predict(data.x,prediction_type='RawFormulaVal',thread_count=2),dtype=np.float64)
        self.guard()
        original_ranking = rankings(data,scores)
        need(np.allclose(scores,replay,rtol=0,atol=1e-12) and original_ranking == rankings(data,replay),'Saved prefix score/ranking fidelity differs')
        del prefix,replay
        if full_path is not None:
            full = CatBoostClassifier();full.load_model(str(self.local(full_path)))
            self.guard()
            need(type(full.tree_count_) is int and full.tree_count_ == spec['trained_iterations'] and full.feature_names_ == data.feature_names
                 and full.get_cat_feature_indices() == [],'Complete trained model/schema differs')
            native_same(actual,full.get_all_params())
            replay = np.asarray(full.predict(data.x,ntree_end=spec['scoring_prefix'],prediction_type='RawFormulaVal',thread_count=2),dtype=np.float64)
            self.guard()
            need(np.allclose(scores,replay,rtol=0,atol=1e-12) and original_ranking == rankings(data,replay),'Complete model inherited prefix fidelity differs')
            del full,replay
        if json_path is not None:
            body,_ = self.read(self.local(json_path))
            info = body.get('features_info',{})
            need(len(body.get('oblivious_trees',[])) == spec['trained_iterations'] and not info.get('ctrs') and not info.get('categorical_features')
                 and len(info.get('float_features',[])) == len(data.feature_names),'Saved complete numeric JSON schema differs')
            need([(f['flat_feature_index'],f['feature_id']) for f in info['float_features']] == list(enumerate(data.feature_names)), 'Native JSON ordered numeric feature names differ')
            need(all(s['split_type'] == 'FloatFeature' for tree in body['oblivious_trees'] for s in tree.get('splits') or []),'Saved JSON contains nonnumeric split')
        return summarize(data.queries,original_ranking)

    def execute(self):
        import duckdb,numpy as np
        self.phase = 'accepted_lineage';self.lineage()
        self.phase = 'all_original_worker_authority';self.workers()
        self.con = duckdb.connect()
        self.con.execute("SET threads=2")
        self.con.execute("SET memory_limit='3GB'")
        self.con.execute("SET max_temp_directory_size='0B'")
        base_names = self.identity['feature_names'];collections = self.source_inputs['collections']
        def matrix(role,delta=(),cap=None):
            return read_matrix(self.con,collections[role],base_names,local=self.local,cap=cap,
                extra_paths=self.identity['daily_features'][role] if delta else None,delta=delta,check=self.guard)
        self.phase = 'baseline_selection_expected_arrays'
        base = matrix('selection')
        need(len(base.queries) == 4000,'Every original4000 selection query required')
        self.phase = 'accepted_B_saved_prediction_replay'
        b = self.identity['baseline']
        bm,bvalues,users = self.model_scores(base,b['model_path'],b['score_path'],actual=self.control['actual_model_parameters'])
        same(bm,b['metrics'])
        candidates = [dict(b,metrics=bm)]
        values = {'B':bvalues}
        for cid in SLOTS:
            report,manifest,child,directory = self.worker_data[cid]
            if report['status'] == 'failed':
                candidates.append(dict(candidate_id=cid,status='resource_failed',added_physical_columns=3,metrics=None))
                continue
            self.phase = cid+'_expected_train_matrix'
            delta = self.identity['slots'][cid]['physical_delta']
            train = matrix('train',delta,cap=self.identity['model_spec']['population'])
            need(len(train.queries) == self.identity['model_spec']['population'],'Exact inherited train population differs')
            weights,summary = group_weights(train)
            need(np.unique(train.y).size == 2,'Expected train support lacks bothclasses')
            same(summary,report['training'])
            same(matrix_proof(train,weights=weights,check=self.guard),report['train_matrix_proof'])
            self.worker_proofs[cid]['train_matrix_proof'] = report['train_matrix_proof']
            self.worker_proofs[cid]['expected_training'] = summary
            del weights,train
            self.phase = cid+'_expected_selection_matrix'
            data = matrix('selection',delta)
            need(data.queries == base.queries and np.array_equal(data.group,base.group) and np.array_equal(data.items,base.items)
                 and np.array_equal(data.y,base.y) and np.array_equal(data.x[:,:41],base.x,equal_nan=True),'Append-only mixed matrix changed accepted B41/Q/C/Y')
            proof = matrix_proof(data,check=self.guard)
            same(proof,report['selection_matrix_proof'])
            same(self.environment,report['environment'])
            self.phase = cid+'_saved_model_prediction_replay'
            metrics,v,u = self.model_scores(data,report['model_path'],report['score_path'],actual=report['actual_model_parameters'],
                                           full_path=report['full_model_path'],json_path=str((directory/'full.json').relative_to(self.root)))
            need(u == users,'Paired user domain differs')
            same(metrics,report['metrics'])
            candidate = dict(child['candidate'],metrics=metrics)
            self.worker_proofs[cid].update(selection_matrix_proof=proof,all_query_rankings_identical=True,
                complete_trained_iterations=self.identity['model_spec']['trained_iterations'],scoring_prefix=self.identity['model_spec']['scoring_prefix'],
                checked_saved_outputs=manifest['outputs'])
            candidates.append(candidate);values[cid]=v
            del data
        self.phase = 'independent_frozen_global_selector'
        same(candidates,self.report['candidates'])
        winner = select(candidates)
        same(winner,self.report['winner'])
        winner_file = self.ref(dict(path=str((self.directory/'winner.json').relative_to(self.root)),sha256=self.manifest['outputs'][str((self.directory/'winner.json').relative_to(self.root))]))
        same(winner,winner_file)
        self.phase = 'descriptive_paired_user_bootstrap'
        bootstrap = paired_bootstrap(values[winner['candidate_id']],bvalues,users)
        result = dict(version=1,status='verified',scope=SCOPE,run_id=self.context['run_id'],source_run_id=self.identity['source_run_id'],
            context_sha256=self.context_sha,execution_consumed=self.execution_consumed,request=self.context['request'],producer_manifest=self.context['producer_manifest'],
            producer_report=self.context['producer_report'],oracle_source=self.source,fit_attempt_count=0,observer_refits=0,source_regenerations=0,
            allocated_slots=4,checked_slots=list(SLOTS),candidate_records=candidates,winner=winner,worker_proofs=self.worker_proofs,
            paired_bootstrap=bootstrap,selection_query_count=len(base.queries),selection_candidate_rows=len(base.items),
            proof_limits='Independent accepted-input matrices, expected query row mass, saved predictions and full-Y metrics plus reviewed fit code/receipts; native training weights are not recoverable from CBM. Prior B41/source formula proofs are reused. Bootstrap200 is descriptive after selection, conditional on this development support/two evaluation dates; no heldout/generalization or power guarantee.')
        del base
        return result

    def repin(self, *, full=True):
        need(not self.failed.exists(),'Known failed observer')
        need(self.sha(self.path) == self.context_sha,'Original issuer context changed')
        need(not (self.directory/'report.failed.json').exists() and not (self.inv/'oracle.log.cleanup-failed.json').exists(),'Known failed owner/cleanup')
        if full:
            self.pins(self.identity['fingerprints']);self.pins(self.manifest['outputs'])
        self.pins(self.observed)
        need(self.sha(self.local(self.source['path'])) == self.source['sha256'],'Observer source changed')
        for report,manifest,child,directory in self.worker_data.values():
            if report['status'] == 'complete_produced_unreviewed':
                need(not (directory/'report.failed.json').exists(),'Known late failed arm')
        need(not self.failed.exists(),'Known late failed observer')
        self.guard()

    def persist(self,path,value):
        import os
        raw = (canonical(value)+'\n').encode()
        with path.open('xb') as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
        fd = os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return hashlib.sha256(raw).hexdigest()

    def run(self):
        primary = None;result = None
        try:
            self.timer_start()
            self.phase = 'original_producer_binding';self.binding()
            result = self.execute()
            self.phase = 'final_original_input_and_output_pins';self.repin()
        except BaseException as error:primary = error
        finally:
            if self.con is not None:
                try:self.con.close()
                except BaseException as error:primary = primary or error
                self.con = None
            try:self.guard()
            except BaseException as error:primary = primary or error
        if primary is None:
            try:
                need(not self.failed.exists(),'Known failed observer before success persistence')
                result.update(started_monotonic=START,finished_monotonic=time.monotonic(),process_cpu_seconds=self.cpu(),
                    reaped_children_cpu_seconds=0,process_peak_rss_bytes=self.rss(),
                    receipt_boundary='after_SQL_close_and_full_pin_reverification_before_small_authority_repin_evidence_fsync_and_exit_tail_parent_reaping_charges_tail')
                self.persist(self.output,result)
                self.repin(full=False)
                self.guard()
            except BaseException as error:primary = error
        self.stopped.set()
        if self.timer is not None:
            try:self.timer.join(timeout=.5)
            except BaseException as error:primary = primary or error
        try:
            self.guard()
            need(not self.failed.exists(),'Known failed observer at terminal return')
        except BaseException as error:primary = primary or error
        if primary is not None:
            usage = {}
            for name,read in [('process_cpu_seconds',self.cpu),('process_peak_rss_bytes',self.rss),('finished_monotonic',time.monotonic)]:
                try:usage[name] = read()
                except BaseException as secondary:
                    usage[name] = None
                    primary.add_note('Failure usage unavailable: '+type(secondary).__name__)
            failure = dict(version=1,status='failed',scope=SCOPE,run_id=self.context['run_id'],context_sha256=self.context_sha,
                fit_attempt_count=0,observer_refits=0,source_regenerations=0,failure_phase=self.phase,
                assertion_id=getattr(primary,'assertion_id',hashlib.sha256(('exception:'+type(primary).__name__).encode()).hexdigest()[:16]),
                error_type=type(primary).__name__,**usage)
            try:self.persist(self.failed,failure)
            except BaseException as secondary:primary.add_note('Failure persistence: '+type(secondary).__name__)
            raise primary
        print(canonical(dict(status='verified',fit_attempt_count=0,run_id=self.context['run_id'])),flush=True)
        return result


def validate_selector(body):
    """Independent literal policy contract; no caller-selected comparison law."""
    expected = dict(version=1,role='prospective_bounded_feature_program_selection',candidate_ids=list(IDS),
        added_physical_columns={n:0 if n=='B' else 3 for n in IDS},
        shared_model_contract='accepted019_population_weights_settings_trained_iterations_and_scoring_prefix',
        objective=dict(metric='ndcg',k=20,estimand='conditional_macro_query',targets='full_Y_independent_of_C'),
        feasibility=dict(metric='recall',k=20,estimand='conditional_macro_query',reference='B',minimum_delta=-.002,boundary='inclusive'),
        tie=dict(global_maximum_absolute_band=1e-12,order=['fewer_added_physical_columns_including_masks','lexicographic_candidate_id']),
        failure=dict(known_resource_failure='paid_consumed_ineligible',integrity_api_or_unknown_usage='STOP',collision='consumed_ineligible',refill=False),
        primary_comparison=dict(chosen_candidate='W_may_equal_B',reference='B',freeze_before='reserved_query_targets_and_metrics_open',
            heldout_policy='same_frozen_models_programs_and_predictions_no_refit_or_adaptation'),
        strategy_comparison='best_two_I_minus_best_two_R_descriptive_screening_only',
        random_winner_interpretation='mixed_typed_automation_not_rule_guided_superiority',permissions=dict(new_fit_budget=0,actual_execution_approved=False))
    same(expected,body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context',required=True)
    parser.add_argument('--issued-context-sha256',required=True)
    args = parser.parse_args()
    Audit(args.context,args.issued_context_sha256).run()


if __name__ == '__main__':main()
