"""Independent tiny row/list oracle. No producer imports, DB, files, or fits.

Interface: calculate(events, queries, candidates, source_start).
events: mappings with event_time/product_id/category_id/category_code/brand/price.
queries: mappings query_id/anchor; candidates: mappings query_id/product_id.
All timestamps are timezone-aware UTC datetimes. None is the only NULL marker.
Nominal strings are exact: no trimming/case-folding/empty-string coercion.
Returns separate model_rows and source_provenance; full product peer lists are
recomputed for each candidate, deliberately avoiding production A-z/N-member.
"""
from datetime import timedelta, timezone
from math import fsum, isfinite, log1p

NUMERIC = (
    'brand_missing', 'brand_ambiguous', 'code_missing', 'code_ambiguous',
    'code_recovered', 'log_price', 'price_missing', 'price_ambiguous',
    'price_zero', 'price_negative', 'category_peer_log_price_mean',
    'category_peer_product_support', 'category_log_price_difference',
    'category_peer_mean_missing', 'category_price_difference_missing',
)
NOMINAL = ('category_id_nominal', 'category_code_by_id', 'brand')


def _check_time(value):
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError('oracle requires explicit UTC timestamps')


def _field(bucket, name):
    values = [r[name] for r in bucket]
    known = [v for v in values if v is not None]
    if not known:
        return 'missing', None
    first = known[0]
    if len(known) != len(values) or any(v != first for v in known):
        return 'ambiguous', None
    return 'clean', first


def _encode(value, state):
    if state != 'clean':
        return ('state:' + state).encode('utf-8')
    return ('value:' + str(value)).encode('utf-8')


def calculate(events, queries, candidates, source_start):
    _check_time(source_start)
    events, queries, candidates = list(events), list(queries), list(candidates)
    for row in events:
        _check_time(row['event_time'])
    query_map = {q['query_id']: q for q in queries}
    if len(query_map) != len(queries):
        raise ValueError('duplicate query')
    keys = [(r['query_id'], r['product_id']) for r in candidates]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate candidate')
    if any(q not in query_map or i is None for q, i in keys):
        raise ValueError('orphan/null candidate')
    model_rows, source_provenance, reference_rows = [], [], []
    completed_anchors = set()
    for q in queries:
        t = q['anchor']; _check_time(t)
        if t < source_start:
            raise ValueError('anchor predates source')
        prefix = [r for r in events if source_start <= r['event_time'] < t]
        chosen = [r['product_id'] for r in candidates if r['query_id'] == q['query_id']]
        products = {r['product_id'] for r in prefix if r['product_id'] is not None}
        snapshots = {}
        for i in products | set(chosen):
            own = [r for r in prefix if r['product_id'] == i]
            last = max((r['event_time'] for r in own), default=None)
            bucket = [r for r in own if r['event_time'] == last]
            active = last is not None and last >= t - timedelta(days=7)
            # Guard selected latest snapshot before NULL/positive filters.
            if active or i in chosen:
                for r in bucket:
                    p = r['price']
                    if p is not None and not isfinite(float(p)):
                        raise ValueError('nonfinite selected-asof price')
            state = {name: _field(bucket, name) for name in
                     ('category_id', 'category_code', 'brand', 'price')}
            pstate, p = state['price']
            price_valid = pstate == 'clean' and p > 0
            snapshots[i] = dict(last=last, active=active, fields=state,
                                log_price=log1p(float(p)) if price_valid else None)
        dictionary = {}
        for r in prefix:
            c, code = r['category_id'], r['category_code']
            if c is not None and code is not None:
                dictionary.setdefault(c, set()).add(code)
        if t not in completed_anchors:
            for j, v in snapshots.items():
                cstate, c = v['fields']['category_id']
                if v['active'] and cstate == 'clean' and v['log_price'] is not None:
                    reference_rows.append(dict(anchor=t, product_id=j, category_id=c, log_price=v['log_price']))
            completed_anchors.add(t)
        for i in chosen:
            s = snapshots[i]
            cat_state, cat = s['fields']['category_id']
            brand_state, brand = s['fields']['brand']
            price_state, price = s['fields']['price']
            raw_state, raw_code = s['fields']['category_code']
            codes = dictionary.get(cat, set()) if cat_state == 'clean' else set()
            code_state = 'missing' if not codes else 'clean' if len(codes) == 1 else 'ambiguous'
            code = next(iter(codes)) if code_state == 'clean' else None
            # Recompute actual R and peers as product lists for this candidate.
            reference = [] if cat_state != 'clean' else [j for j, v in snapshots.items()
                if v['active'] and v['fields']['category_id'] == ('clean', cat)
                and v['log_price'] is not None]
            peers = [j for j in reference if j != i]
            support = len(peers) if cat_state == 'clean' else None
            mean = fsum(snapshots[j]['log_price'] for j in peers) / len(peers) if peers else None
            z = s['log_price']
            difference = z - mean if z is not None and mean is not None else None
            values = dict(
                brand_missing=brand_state != 'clean', brand_ambiguous=brand_state == 'ambiguous',
                code_missing=code_state == 'missing', code_ambiguous=code_state == 'ambiguous',
                code_recovered=code_state == 'clean' and not(raw_state == 'clean' and raw_code == code),
                log_price=z, price_missing=price_state != 'clean', price_ambiguous=price_state == 'ambiguous',
                price_zero=price_state == 'clean' and price == 0,
                price_negative=price_state == 'clean' and price < 0,
                category_peer_log_price_mean=mean, category_peer_product_support=support,
                category_log_price_difference=difference,
                category_peer_mean_missing=mean is None,
                category_price_difference_missing=difference is None,
            )
            nominal = dict(category_id_nominal=_encode(cat, cat_state),
                           category_code_by_id=_encode(code, code_state), brand=_encode(brand, brand_state))
            model_rows.append(dict(query_id=q['query_id'], product_id=i,
                                   **{k: nominal[k] for k in NOMINAL}, **{k: values[k] for k in NUMERIC}))
            source_provenance.append(dict(query_id=q['query_id'], product_id=i,
                latest=s['last'], field_states=s['fields'], dictionary_codes=sorted(codes),
                dictionary_first_known=min((r['event_time'] for r in prefix
                    if cat_state == 'clean' and r['category_id'] == cat
                    and r['category_code'] is not None), default=None),
                reference_ids=sorted(reference), peer_ids=sorted(peers), actual_member=i in reference))
    return dict(model_rows=model_rows, source_provenance=source_provenance,
                reference_rows=reference_rows)


def validate_train_categories(rows, maximum=4096):
    """Actual encoded values, including sentinels; no encoder/model training."""
    rows = list(rows)
    counts = {}
    for name in NOMINAL:
        values = [r[name] for r in rows]
        if any(not isinstance(v, bytes) for v in values):
            raise ValueError('categorical value is not encoded bytes')
        for v in values:
            v.decode('utf-8')
            if not(v.startswith(b'value:') or v in (b'state:missing', b'state:ambiguous')):
                raise ValueError('invalid categorical namespace')
        counts[name] = len(set(values))
        if counts[name] > maximum:
            raise ValueError('train cardinality exceeds declared one-hot limit')
    return counts
