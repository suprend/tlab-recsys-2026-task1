"""Pure fixed-cohort exploratory estimands; no IO, graph rebuild or model calls."""
from collections import Counter
import math
from random import Random

ARMS = ('C0', 'count', 'cos', 'matched_popular', 'matched_count', 'matched_cos')
COHORTS = ('full', 'new', 'repeat')
PAIRS = {'cos-C0': ('cos', 'C0'), 'count-C0': ('count', 'C0'),
         'cos-count': ('cos', 'count'),
         'matched_cos-matched_popular': ('matched_cos', 'matched_popular')}
PRIMARY = 'cos-C0'
MATCHED = 'matched_cos-matched_popular'
SCOPE = 'Reused exploratory fixed cohort/graph; no causal, fresh or normalization claim.'


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def type7(values, p):
    """Finite type-7 quantile, zero-based h=(n-1)p; empty sample is undefined."""
    _need(type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1, 'Invalid percentile')
    data = list(values)
    _need(all(type(v) in (int, float) and math.isfinite(v) for v in data), 'Nonfinite sample')
    if not data:
        return None
    data.sort()
    h = (len(data) - 1) * p
    lo, hi = math.floor(h), math.ceil(h)
    return data[lo] + (h - lo) * (data[hi] - data[lo])


def _ids(value):
    _need(isinstance(value, (set, frozenset)) and all(
        type(v) is int and -(2**63) <= v < 2**63 for v in value), 'Expected signed64 ID set')
    return value


def _prepare(records, check):
    rows, seen = [], set()
    check()
    for index, record in enumerate(records):
        if index % 32 == 0:
            check()
        _need(index < 6000, 'Fixed cohort exceeds 6000 queries')
        q, user = record['query_id'], record['user_id']
        _need(type(q) is str and q and q not in seen, 'Nonunique/invalid query ID')
        _need(type(user) is int and -(2**63) <= user < 2**63, 'Invalid user ID')
        seen.add(q)
        target, prior = _ids(record['targets']), _ids(record['prior'])
        _need(set(record['arms']) == set(ARMS), 'Exactly six arms required')
        arms = {arm: _ids(record['arms'][arm]) for arm in ARMS}
        rows.append((q, user, (target, target - prior, target & prior), arms))
    _need(bool(rows), 'Nonempty fixed query frame required')
    rows.sort(key=lambda row: row[0])
    discounts = [0.0]
    for rank in range(1, 21):
        discounts.append(discounts[-1] + 1 / math.log2(rank + 1))
    accum = {c: {'target_mass': 0, 'positive_queries': 0,
                'arms': {a: [0, 0.0, 0, 0.0] for a in ARMS}} for c in COHORTS}
    numerators = {c: {name: 0.0 for name in PAIRS} for c in COHORTS}
    groups = {}
    for index, (_, user, targets, arms) in enumerate(rows):
        if index % 32 == 0:
            check()
        vector = groups.setdefault(user, [0.0] * 15)
        for ci, cohort in enumerate(COHORTS):
            y, cell = targets[ci], accum[cohort]
            mass = len(y)
            cell['target_mass'] += mass
            if not mass:
                continue
            cell['positive_queries'] += 1
            vector[ci * 5] += 1
            hits = {a: len(arms[a] & y) for a in ARMS}
            for arm, hit in hits.items():
                total = cell['arms'][arm]
                total[0] += hit
                total[1] += hit / mass
                total[2] += hit > 0
                total[3] += discounts[min(20, hit)] / discounts[min(20, mass)]
            for pi, (name, (left, right)) in enumerate(PAIRS.items(), 1):
                delta = hits[left] / mass - hits[right] / mass
                numerators[cohort][name] += delta
                vector[ci * 5 + pi] += delta
    for cell in accum.values():
        mass, positive = cell['target_mass'], cell['positive_queries']
        for arm, (hits, recall, hit_any, oracle) in cell['arms'].items():
            cell['arms'][arm] = dict(hits=hits, micro_recall=hits / mass if mass else None,
                macro_recall=recall / positive if positive else None, hit_any_queries=hit_any,
                hit_any_positive=hit_any / positive if positive else None,
                hit_any_all=hit_any / len(rows), oracle_ndcg20=oracle / positive if positive else None)
    contrasts = {c: {name: value / accum[c]['positive_queries'] if accum[c]['positive_queries'] else None
                    for name, value in numerators[c].items()} for c in COHORTS}
    check()
    return dict(queries=len(rows), users=len(groups), cohorts=accum, contrasts=contrasts), groups


def summarize(records, *, check=lambda: None):
    return _prepare(records, check)[0]


def _bootstrap(groups, draws, seed, check):
    _need(type(draws) is int and 1 <= draws <= 2000, 'Expected 1..2000 draws')
    _need(type(seed) is int and seed == 61061, 'Frozen seed 61061 required')
    # Sorting is part of the frozen randrange-to-user mapping; output exposes no IDs.
    vectors = [groups[user] for user in sorted(groups)]
    count, rng = len(vectors), Random(seed)
    values = {c: {name: [] for name in PAIRS} for c in COHORTS}
    undefined = {c: 0 for c in COHORTS}
    for draw in range(draws):
        if draw % 32 == 0:
            check()
        multiplicity = Counter(rng.randrange(count) for _ in range(count))
        total = [0.0] * 15
        for user, repeats in sorted(multiplicity.items()):
            for index, value in enumerate(vectors[user]):
                total[index] += repeats * value
        for ci, cohort in enumerate(COHORTS):
            positive = total[ci * 5]
            if not positive:
                undefined[cohort] += 1
                continue
            for pi, name in enumerate(PAIRS, 1):
                values[cohort][name].append(total[ci * 5 + pi] / positive)
    intervals = {}
    for cohort in COHORTS:
        intervals[cohort] = {}
        for name, sample in values[cohort].items():
            primary = cohort == 'full' and name == PRIMARY
            ci = None if not sample or (primary and undefined[cohort]) else [
                type7(sample, .025), type7(sample, .975)]
            intervals[cohort][name] = dict(ci95=ci, defined_draws=len(sample),
                undefined_draws=undefined[cohort], conditional_on_defined=not primary)
    check()
    return dict(draws=draws, seed=seed, frame_users=count, intervals=intervals,
                sampler='stdlib Random.randrange; sorted signed user IDs; ascending weighted aggregation')


def cluster_bootstrap(records, *, draws=2000, seed=61061, check=lambda: None):
    return _bootstrap(_prepare(records, check)[1], draws, seed, check)


def analyze(records, *, draws=2000, seed=61061, check=lambda: None):
    summary, groups = _prepare(records, check)
    bootstrap = _bootstrap(groups, draws, seed, check)
    primary, matched = (summary['contrasts']['full'][name] for name in (PRIMARY, MATCHED))
    ci = bootstrap['intervals']['full'][PRIMARY]['ci95']
    continuation = (primary is not None and matched is not None and ci is not None
                    and primary >= .005 and ci[0] > 0 and matched > 0)
    decision = 'propose_optional_continuation' if continuation else 'inconclusive'
    if ci is not None and ci[1] <= 0:
        decision = 'reject_current_cosine_continuation'
    return dict(summary=summary, bootstrap=bootstrap, continuation=continuation,
                decision=decision, inference_scope=SCOPE)
