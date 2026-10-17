"""Independent fixed-cohort HYP061 verifier; SOURCE only until Root binding/admission."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timedelta
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
import resource
import sys
import time
import types

STATS_SHA = '55b7857088fcfdb42bd69513515417a5bcd1e663a6f154559fbd76acd6a8a97b'
ANALYSIS_SHA = 'b8896d7f7ee7a12593cdfdfe4f7f3fc4a58bddbd9e3f7312b96de895a104565f'
PRIMARY_REQUEST_SHA = '1b0bda2f1289b9cf9a99881f406c02c1c2efe7525044f0650fb3b87c984c44ad'
ROOT_TERMINAL_SHA = '238662863069508d990abab66b069735c79b76fb1c3ae4de4c746e00e07a6a28'
PRIMARY_CODE_SHA = '3f7d1ae6a226ea512965098009cc7f24eee80456ec6a938fb1621ae484c9a03e'
PRIMARY_STATS_SHA = '3aa8e4b2d49e275de399e27e5190437d0a9818977ebcb5de2a88f3954fac6a49'
PRIMARY_DIRECTORY = Path('/private/tmp/tlab-hyp061-coverage-runtime-v1-once/consumer')
DATES = tuple(f'2019-10-{d:02d}T00:00:00Z' for d in (8, 9, 10))
ARMS = ('C0', 'count', 'cos', 'matched_popular', 'matched_count', 'matched_cos')
PAIRS = (('cos-C0', 'cos', 'C0'), ('count-C0', 'count', 'C0'),
         ('cos-count', 'cos', 'count'), ('matched_cos-matched_popular', 'matched_cos', 'matched_popular'))
COHORTS = ('full', 'new', 'repeat')
FIELDS = [('query_id', 'VARCHAR'), ('product_id', 'BIGINT'), ('first_purchase_time', 'TIMESTAMP'),
          ('raw_purchase_rows', 'BIGINT'), ('same_second_purchase', 'BOOLEAN'),
          ('catalog_seen_before', 'BOOLEAN'), ('pair_seen_before', 'BOOLEAN')]
MAXIMA = {'cpu_seconds': 90, 'wall_seconds': 120, 'rss_bytes': 2**30, 'output_bytes': 16*2**20}


def require(value, message):
    if not value:
        raise ValueError(message)


def annotate(error, message):
    try:
        BaseException.add_note(error, message)
    except BaseException:
        pass


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def decode(raw):
    def unique(rows):
        result = {}
        for k, v in rows:
            require(k not in result, 'Duplicate JSON field')
            result[k] = v
        return result
    def nonfinite(_):
        raise ValueError('Nonfinite JSON scalar')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def identity(path, tick=lambda: None):
    size, digest = 0, hashlib.sha256()
    tick()
    with Path(path).open('rb') as stream:
        while True:
            tick()
            part = stream.read(2**20)
            if not part:
                break
            size += len(part)
            digest.update(part)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def metadata(path, limit=2**20):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'Bound metadata bytes')
    return decode(raw)


def signed(value):
    require(type(value) is int and -2**63 <= value < 2**63, 'Exact signed64 identity required')
    return value


def sequence(values, maximum):
    require(type(values) is list and len(values) <= maximum, 'Bound item sequence')
    for value in values:
        signed(value)
    require(len(set(values)) == len(values), 'Repeated item identity')
    return values


def merge(*parts):
    result, present = [], set()
    for part in parts:
        for item in part:
            if item not in present:
                result.append(item)
                present.add(item)
    return result


def lines(path, tick):
    with Path(path).open('rb') as stream:
        while True:
            tick()
            raw = stream.readline(64*2**20 + 1)
            if not raw:
                return
            require(len(raw) <= 64*2**20 and raw.endswith(b'\n'), 'Bound newline-terminated record')
            yield decode(raw)


class Budget:
    def __init__(self, directory, limits):
        require(type(limits) is dict and set(limits) == set(MAXIMA), 'Exact verifier limits')
        require(all(type(v) is int and 0 < v <= MAXIMA[k] for k, v in limits.items()), 'Finite verifier caps')
        self.directory, self.limits = directory, limits
        self.start_wall, self.start_cpu = time.monotonic(), time.process_time()
    def sample(self):
        high = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {'cpu_seconds': time.process_time() - self.start_cpu,
                'wall_seconds': time.monotonic() - self.start_wall,
                'rss_bytes': int(high if sys.platform == 'darwin' else high*1024)}
    def tick(self, extra=0):
        require(all(v < self.limits[k] for k, v in self.sample().items()), 'Verifier cooperative resource cap')
        written = sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file())
        require(written + extra <= self.limits['output_bytes'] - 2*2**20, 'Output cap with two MiB final reserve')


def write(path, value, budget=None):
    raw = encode(value)
    if budget is not None:
        budget.tick(len(raw))
    with Path(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'Short verifier metadata write')


def reconstruct(candidate, q):
    require(type(candidate) is dict and set(candidate) == {'global_rank', 'query_id', 'user_id', 'anchor', 'C0', 'P180', 'R20', 'core_result', 'controls', 'prior_pair_count'}, 'Candidate row schema')
    require(all(candidate[k] == q[k] and type(candidate[k]) is type(q[k]) for k in q), 'Candidate cohort/order drift')
    original = sequence(candidate['C0'], 220)
    require(original == sorted(original), 'C0 sorted identity order')
    popular, recent = sequence(candidate['P180'], 180), sequence(candidate['R20'], 20)
    require(set(popular + recent) <= set(original), 'Baseline source not in C0')
    core, control = candidate['core_result'], candidate['controls']
    require(set(core) == {'seeds', 'source', 'ranked_source', 'domain', 'rejection', 'profile_edge_visits', 'distinct_top20_sets', 'query_id', 'C_count', 'C_cos'}, 'Core evidence schema')
    require(core['query_id'] == q['query_id'] and sequence(core['seeds'], 4) == recent[:4], 'Core query/seed drift')
    require(set(core['source']) == set(core['ranked_source']) == {'count', 'cosine'}, 'Two source arms')
    visits = core['profile_edge_visits']
    require(type(visits) is int and 0 <= visits <= 65536, 'Shared profile visits')
    require(type(core['domain']) is list and len(core['domain']) <= 65536, 'Full bounded pre-C0 domain')
    domain, previous = {}, None
    for cell in core['domain']:
        require(set(cell) == {'product_id', 'support', 'count', 'cosine', 'in_C0'}, 'Domain cell schema')
        item = signed(cell['product_id'])
        require(previous is None or previous < item, 'Domain duplicate/order')
        previous = item
        require(type(cell['in_C0']) is bool and cell['in_C0'] == (item in original), 'Domain C0 evidence')
        require(all(type(cell[k]) in (int, float) and math.isfinite(cell[k]) and cell[k] > 0 for k in ('count', 'cosine')), 'Finite positive source scores')
        require(type(cell['support']) is list and bool(cell['support']), 'Domain support evidence')
        seeds = []
        for row in cell['support']:
            require(type(row) is list and len(row) == 4 and all(type(v) is int for v in row), 'Support tuple')
            h, count, dh, dj = row
            require(h in core['seeds'] and 3 <= count <= dh <= 512 and count <= dj, 'Support/norm bounds')
            seeds.append(h)
        require(seeds == [h for h in core['seeds'] if h in seeds] and len(set(seeds)) == len(seeds), 'Support seed order')
        domain[item] = cell
    source = {}
    for name in ('count', 'cosine'):
        chosen = sequence(core['source'][name], 20)
        expected = sorted((i for i in domain if i not in set(original)), key=lambda i: (-domain[i][name], hashlib.sha256(str(i).encode('ascii')).digest(), i))[:20]
        require(chosen == expected, 'Complete-domain top20 mismatch')
        ranked = core['ranked_source'][name]
        require(type(ranked) is list and len(ranked) == len(chosen), 'Ranked source count')
        for rank, (item, row) in enumerate(zip(chosen, ranked), 1):
            require(set(row) == {'rank', 'product_id', 'score', 'support'} and type(row['rank']) is int and row['rank'] == rank, 'Ranked source schema')
            require(type(row['score']) in (int, float) and math.isfinite(row['score']) and signed(row['product_id']) == item and row['score'] == domain[item][name] and row['support'] == domain[item]['support'], 'Ranked source payload')
        source[name] = chosen
    require(type(core['distinct_top20_sets']) is bool and core['distinct_top20_sets'] == (set(source['count']) != set(source['cosine'])), 'Distinct source-set evidence')
    require(type(core['rejection']) is list and len(core['rejection']) == len(recent[:4]), 'Guard ledger count')
    for seed, guard in zip(recent[:4], core['rejection']):
        require(type(guard) is dict and guard.get('seed') == seed and type(guard.get('degree')) is int, 'Guard identity')
        degree, reason = guard['degree'], guard.get('reason')
        require((reason == 'seed_view_empty' and degree == 0 and set(guard) == {'seed', 'degree', 'reason'}) or (reason == 'audience_guard' and degree > 512 and set(guard) == {'seed', 'degree', 'reason'}) or (reason == 'admitted' and 1 <= degree <= 512 and set(guard) == {'seed', 'degree', 'reason', 'support_below3'} and type(guard['support_below3']) is int and guard['support_below3'] >= 0), 'Guard schema')
    base = merge(popular, recent)
    require(set(control) == {'B', 'T', 'k', 'matched_popular', 'matched_count', 'matched_cosine'}, 'Matched control schema')
    require(sequence(control['B'], 220) == base, 'Matched base order')
    tail = sequence(control['T'], 20)
    require(set(tail) == set(original) - set(base), 'Matched original-tail domain')
    k = min(len(tail), len(source['count']), len(source['cosine']))
    require(type(control['k']) is int and control['k'] == k, 'Common matched cardinality')
    expected = {'C0': original, 'count': merge(base, source['count']), 'cos': merge(base, source['cosine']),
                'matched_popular': merge(base, tail[:k]), 'matched_count': merge(base, source['count'][:k]), 'matched_cos': merge(base, source['cosine'][:k])}
    require(sequence(core['C_count'], 220) == expected['count'] and sequence(core['C_cos'], 220) == expected['cos'], 'Native arms')
    for field, arm in (('matched_popular', 'matched_popular'), ('matched_count', 'matched_count'), ('matched_cosine', 'matched_cos')):
        require(sequence(control[field], 220) == expected[arm], 'Matched arms')
    require(type(candidate['prior_pair_count']) is int and candidate['prior_pair_count'] >= 0, 'Prior per-query count type')
    return {name: frozenset(values) for name, values in expected.items()}, visits


def load_cohort(directory, seal, tick):
    require(seal.get('status') == 'SEALED6000_UNREVIEWED_NO_OUTCOMES' and seal.get('queries_written') == 6000 and seal.get('prior_pairs_written') == 44172 and seal.get('q100_matches') == 100 and seal.get('history_select_completion') == 'complete', 'Complete fixed seal')
    graph = seal.get('graph_builds')
    require(type(graph) is list and len(graph) == 3 and {g.get('anchor') for g in graph} == set(DATES) and all(g.get('complete') is True for g in graph), 'Complete graph ledger')
    qrows, users_days = [], set()
    for index, row in enumerate(lines(directory/'Q6000.jsonl', tick)):
        require(index < 6000 and set(row) == {'global_rank', 'query_id', 'user_id', 'anchor'}, 'Q stream schema/count')
        require(type(row['global_rank']) is int and row['global_rank'] == index and row['anchor'] in DATES, 'Q rank/anchor')
        user = signed(row['user_id'])
        require(type(row['query_id']) is str and row['query_id'] == hashlib.sha256(f"query|2026|{row['anchor']}|{user}".encode('ascii')).hexdigest(), 'Canonical query identity')
        require((user, row['anchor']) not in users_days, 'Repeated user-day')
        users_days.add((user, row['anchor']))
        qrows.append(row)
    require(len(qrows) == 6000 and Counter(q['anchor'] for q in qrows) == Counter({a: 2000 for a in DATES}), 'Fixed 2000/day cohort')
    require(qrows == sorted(qrows, key=lambda q: (hashlib.sha256(b'tlab-hyp061-q100-v1\0'+q['query_id'].encode('ascii')).digest(), q['query_id'].encode('ascii'))), 'Canonical global Q order')
    records = {q['query_id']: dict(q, targets=set(), prior=set()) for q in qrows}
    previous, count = None, 0
    for row in lines(directory/'prior-pairs.jsonl', tick):
        require(set(row) == {'query_id', 'product_id'} and row['query_id'] in records, 'Foreign/malformed prior pair')
        item = signed(row['product_id']);key = (records[row['query_id']]['global_rank'], item)
        require(previous is None or previous < key, 'Prior pair order/duplicate')
        previous = key;records[row['query_id']]['prior'].add(item);count += 1
        require(count <= 44172, 'Prior cap')
    require(count == 44172, 'Complete prior relation count')
    ordered = sorted(qrows, key=lambda q: (q['anchor'], q['global_rank']));visits = 0;count = 0
    for count, candidate in enumerate(lines(directory/'candidates.jsonl', tick), 1):
        require(count <= 6000, 'Candidate count cap')
        q = ordered[count-1];arms, number = reconstruct(candidate, q);record = records[q['query_id']]
        require(candidate['prior_pair_count'] == len(record['prior']), 'Prior row count equality')
        record['arms'] = arms;visits += number
    require(count == 6000 and visits == seal.get('shared_profile_edge_visits') and visits <= 393216000, 'Candidate count/visits equality')
    for name, count in (('Q6000.jsonl', 6000), ('candidates.jsonl', 6000), ('prior-pairs.jsonl', 44172)):
        require(seal['outputs'][name]['rows'] == count, 'Manifest stream row count')
    return [records[q['query_id']] for q in qrows]


def target_rows(paths, records, marker, marker_pin, tick):
    require(identity(marker, tick) == marker_pin, 'Independent closed marker drift')
    paths = [Path(p).resolve(strict=True) for p in paths]
    require(len(paths) == 3 and len(set(paths)) == 3 and all(p.name == 'labels.parquet' and not any(c in str(p) for c in '*?[]{}') for p in paths), 'Exact three resolved labels')
    import duckdb
    require(duckdb.__version__ == '1.5.6', 'Pinned DuckDB')
    connection = duckdb.connect(':memory:', config={'threads': '2', 'memory_limit': '512MB', 'max_temp_directory_size': '0B'})
    failure = None;seen = set();total = 0;lookup = {r['query_id']: r for r in records}
    try:
        connection.execute('SET allowed_paths = ['+','.join("'"+str(p).replace("'", "''")+"'" for p in paths)+']')
        connection.execute('SET enable_external_access=false')
        connection.execute('SET lock_configuration=true')
        settings = connection.execute("SELECT current_setting('allowed_paths'),current_setting('enable_external_access'),current_setting('lock_configuration')").fetchone()
        require(sorted(settings[0]) == sorted(map(str, paths)) and settings[1:] == (False, True), 'Native settings readback')
        for anchor, path in zip(DATES, paths):
            tick();connection.read_parquet(str(path)).project(','.join(n for n, _ in FIELDS)).create_view('oracle_y', replace=True)
            require([tuple(r[:2]) for r in connection.execute('DESCRIBE oracle_y').fetchall()] == FIELDS, 'Seven-column native schema')
            total += connection.execute('SELECT count(*) FROM oracle_y').fetchone()[0]
            require(total <= 1000000, 'Full target cap')
            connection.execute('SELECT '+','.join(n for n, _ in FIELDS)+' FROM oracle_y')
            while True:
                tick();chunk = connection.fetchmany(4096)
                if not chunk:
                    break
                for qid, item, first, raw, same, catalog, prior in chunk:
                    require(qid in lookup and lookup[qid]['anchor'] == anchor, 'Foreign fullY query/shard')
                    signed(item);require((qid, item) not in seen, 'Duplicate fullY identity');seen.add((qid, item))
                    require(type(first) is datetime and first.tzinfo is None and type(raw) is int and raw > 0 and all(type(v) is bool for v in (same, catalog, prior)), 'Target scalar schema')
                    t = datetime.fromisoformat(anchor[:-1])
                    require(t <= first < t+timedelta(hours=24) and same == (first == t), '24-hour half-open target window')
                    row = lookup[qid]
                    require(prior == (item in row['prior']), 'Complete prior relation versus fullY flag')
                    require(catalog or all(item not in arm for arm in row['arms'].values()), 'Retrieved target catalog witness')
                    row['targets'].add(item)
    except BaseException as error:
        failure = error
    try:
        connection.close()
    except BaseException as error:
        if failure is None:
            failure = error
        else:
            annotate(failure, 'Independent native connection close failed: '+type(error).__name__)
    if failure is not None:
        raise failure


def compare_private(records, audit_path, changes_path, tick):
    audit_count = 0
    for q, actual in zip_longest(records, lines(audit_path, tick)):
        require(q is not None and actual is not None, 'Private per-query row count mismatch')
        require(set(actual) == {'query_id', 'user_id', 'anchor', 'target_mass', 'hits', 'candidate_sizes'}, 'Private query audit schema')
        target = q['targets'];parts = (target, target-q['prior'], target&q['prior'])
        expected = {'query_id': q['query_id'], 'user_id': q['user_id'], 'anchor': q['anchor'], 'target_mass': [len(y) for y in parts], 'hits': {a: [len(y & q['arms'][a]) for y in parts] for a in ARMS}, 'candidate_sizes': {a: len(q['arms'][a]) for a in ARMS}}
        require(type(actual['user_id']) is int and type(actual['target_mass']) is list and all(type(n) is int for n in actual['target_mass']), 'Private exact count types')
        require(set(actual['hits']) == set(actual['candidate_sizes']) == set(ARMS) and all(type(v) is list and all(type(n) is int for n in v) for v in actual['hits'].values()) and all(type(v) is int for v in actual['candidate_sizes'].values()), 'Private arm count types')
        require(actual == expected, 'Private per-query values mismatch');audit_count += 1
    def expected_changes():
        for q in records:
            for contrast, left, right in PAIRS:
                for direction, hit in (('gained', q['targets'] & (q['arms'][left]-q['arms'][right])), ('lost', q['targets'] & (q['arms'][right]-q['arms'][left]))):
                    for item in sorted(hit):
                        yield {'query_id': q['query_id'], 'product_id': item, 'contrast': contrast, 'direction': direction, 'new_pair': item not in q['prior']}
    changes_count = 0
    for expected, actual in zip_longest(expected_changes(), lines(changes_path, tick)):
        require(expected is not None and actual is not None, 'Private gained/lost row count mismatch')
        require(set(actual) == {'query_id', 'product_id', 'contrast', 'direction', 'new_pair'} and type(actual['new_pair']) is bool, 'Private gained/lost schema')
        signed(actual['product_id']);require(expected == actual, 'Private gained/lost identities mismatch');changes_count += 1
    return {'private_queries_checked': audit_count, 'private_target_change_rows_checked': changes_count, 'contrasts_checked': len(PAIRS)}


def compare_number(expected, actual, errors):
    if expected is None:
        require(actual is None, 'Undefined metric mismatch')
    elif type(expected) is bool or type(expected) is int:
        require(type(actual) is type(expected) and expected == actual, 'Exact metric/count mismatch')
    else:
        require(type(expected) is float and type(actual) in (int, float) and math.isfinite(actual), 'Finite numeric metric')
        errors.append(abs(expected-actual));require(errors[-1] <= 1e-12, 'Numerical metric mismatch')


def compare_summary(independent, primary):
    """Translate independently calculated definitions into the primary report schema."""
    public = independent['summary'];expected_top = {'summary', 'bootstrap', 'continuation', 'decision', 'inference_scope', 'status', 'reused_historical_cohort', 'achieved_ranking_quality', 'causal_or_generalization_claim', 'primary_normalization_claim', 'automatic_new_model', 'analysis_sha256', 'rng'}
    require(set(primary) == expected_top, 'Primary aggregate schema')
    errors = [];checks = 0
    def check(expected, actual):
        nonlocal checks
        compare_number(expected, actual, errors);checks += 1
    summary = primary['summary'];require(set(summary) == {'queries', 'users', 'cohorts', 'contrasts'}, 'Primary summary schema')
    check(public['frame']['queries'], summary['queries']);check(public['frame']['users'], summary['users'])
    require(set(summary['cohorts']) == set(summary['contrasts']) == set(COHORTS), 'Complete primary slices')
    mapping = {'hits': 'hits', 'micro_recall': 'micro_recall', 'macro_recall': 'macro_recall', 'hit_any_queries': 'hit_any', 'hit_any_positive': 'hit_any_over_positive_queries', 'hit_any_all': 'hit_any_over_all_queries', 'oracle_ndcg20': 'oracle_ndcg20'}
    for cohort in COHORTS:
        actual = summary['cohorts'][cohort]
        require(set(actual) == {'target_mass', 'positive_queries', 'arms'} and set(actual['arms']) == set(ARMS), 'Primary slice schema')
        for key in ('target_mass', 'positive_queries'):
            check(public['slices'][cohort][key], actual[key])
        for arm in ARMS:
            require(set(actual['arms'][arm]) == set(mapping), 'Primary arm metrics schema')
            for target_name, own_name in mapping.items():
                check(public['arms'][arm][cohort][own_name], actual['arms'][arm][target_name])
        require(set(summary['contrasts'][cohort]) == {p[0] for p in PAIRS}, 'Primary four contrasts')
        for contrast, _, _ in PAIRS:
            check(public['contrasts'][contrast][cohort]['estimate'], summary['contrasts'][cohort][contrast])
    boot = primary['bootstrap']
    require(set(boot) == {'draws', 'seed', 'frame_users', 'intervals', 'sampler'} and set(boot['intervals']) == set(COHORTS), 'Primary bootstrap schema')
    check(2000, boot['draws']);check(61061, boot['seed']);check(public['frame']['users'], boot['frame_users'])
    for cohort in COHORTS:
        require(set(boot['intervals'][cohort]) == {p[0] for p in PAIRS}, 'All contrast intervals')
        for name, _, _ in PAIRS:
            own = public['contrasts'][name][cohort];actual = boot['intervals'][cohort][name]
            require(set(actual) == {'ci95', 'defined_draws', 'undefined_draws', 'conditional_on_defined'}, 'Interval schema')
            for field in ('defined_draws', 'undefined_draws'):
                check(own[field], actual[field])
            check(not (cohort == 'full' and name == 'cos-C0'), actual['conditional_on_defined'])
            if own['ci95'] is None:
                check(None, actual['ci95'])
            else:
                require(type(actual['ci95']) is list and len(actual['ci95']) == 2, 'Two percentile endpoints')
                for expected, value in zip(own['ci95'], actual['ci95']):
                    check(expected, value)
    decision = public['continuation']['decision']
    check(decision == 'propose_optional_continuation', primary['continuation'])
    require(decision == primary['decision'], 'Independent continuation decision mismatch')
    require(primary['status'] == 'EXPLORATORY_AGGREGATE_UNVERIFIED' and primary['analysis_sha256'] == ANALYSIS_SHA, 'Original aggregate identity/status')
    for field, value in [('reused_historical_cohort', True), ('achieved_ranking_quality', False), ('causal_or_generalization_claim', False), ('primary_normalization_claim', False), ('automatic_new_model', False)]:
        check(value, primary[field])
    return {'numeric_or_exact_scalar_checks': checks, 'absolute_tolerance': 1e-12, 'maximum_absolute_error': max(errors, default=0.0), 'contrasts': 4, 'slices': 3, 'bootstrap_draws_independently_generated': 2000, 'primary_individual_draws_persisted': False, 'draw_parity_claim': 'Primary stores intervals/counts, not individual draw values; all reported interval endpoints and counts compared.'}


def run(request_path, output):
    output = Path(output).resolve()
    require(output.is_relative_to(Path('/private/tmp')) and not output.exists(), 'Fresh private TMP output')
    request = metadata(request_path, 128*1024)
    require(type(request) is dict and set(request) == {'version', 'primary_request', 'primary_directory', 'primary_receipt', 'primary_aggregate', 'primary_before_y', 'primary_per_query', 'primary_changes', 'root_original_terminal', 'limits'} and type(request['version']) is int and request['version'] == 1, 'Exact independent request')
    output.mkdir(mode=0o700)
    budget = Budget(output, request['limits']);pins = [];failure = None;secondary = [];result = None
    def pin(path, expected=None):
        value = identity(path, budget.tick)
        require(expected is None or value == expected, 'Independent input byte identity mismatch')
        pins.append((Path(path), value));return value
    def descriptor(item):
        require(type(item) is dict and set(item) == {'path', 'bytes', 'sha256'} and type(item['path']) is str and type(item['bytes']) is int and item['bytes'] >= 0 and type(item['sha256']) is str and len(item['sha256']) == 64 and all(c in '0123456789abcdef' for c in item['sha256']), 'Exact immutable descriptor')
        path = Path(item['path']);require(path.is_absolute(), 'Absolute descriptor path')
        pin(path, {k: item[k] for k in ('bytes', 'sha256')});return path
    try:
        pin(__file__);pin(request_path)
        own_stats = Path(__file__).with_name('oracle_stats.py');stats_pin = pin(own_stats)
        require(stats_pin['sha256'] == STATS_SHA, 'Frozen independent stats module')
        module = types.ModuleType('hyp061_independent_oracle_stats');module.__file__ = str(own_stats)
        exec(compile(own_stats.read_bytes(), str(own_stats), 'exec'), module.__dict__)
        primary_request_path = descriptor(request['primary_request'])
        require(request['primary_request']['sha256'] == PRIMARY_REQUEST_SHA, 'Exact primary request Source binding')
        original_request = metadata(primary_request_path, 128*1024)
        require(Path(request['primary_directory']).resolve() == PRIMARY_DIRECTORY, 'Fixed original primary directory')
        primary_paths = {}
        for key, name in [('primary_receipt', 'receipt.json'), ('primary_aggregate', 'aggregate.json'), ('primary_before_y', 'BEFORE_Y.json'), ('primary_per_query', 'private-per-query.jsonl'), ('primary_changes', 'private-target-changes.jsonl')]:
            path = descriptor(request[key]);require(path.resolve() == PRIMARY_DIRECTORY/name, 'Exact original primary evidence path');primary_paths[key] = path
        terminal_path = descriptor(request['root_original_terminal']);require(request['root_original_terminal']['sha256'] == ROOT_TERMINAL_SHA, 'Original Root observed terminal identity');terminal = metadata(terminal_path)
        require(terminal.get('exit_code') == 0 and type(terminal['exit_code']) is int and terminal.get('reaped') is True and terminal.get('retry') is False, 'Original Root terminal must be closed exit0/no retry')
        require(type(terminal.get('original_session')) is int and terminal['original_session'] > 0 and all(type(terminal.get(k)) is str and terminal[k] for k in ('state', 'utc', 'first_chunk', 'terminal_chunk')), 'Original Root terminal identity fields')
        require(terminal.get('consumer_receipt') == request['primary_receipt'] and terminal.get('BEFORE_Y') == request['primary_before_y'] and terminal.get('aggregate') == request['primary_aggregate'], 'Root terminal bound to exact primary evidence')
        descriptor(terminal['outer_receipt'])
        receipt = metadata(primary_paths['primary_receipt']);marker = metadata(primary_paths['primary_before_y'])
        require(receipt.get('status') == 'COMPLETE_UNREVIEWED_EXPLORATORY_COVERAGE' and receipt.get('before_y_closed') is True and not receipt.get('secondary') and 'primary' not in receipt, 'Primary receipt must report clean close')
        require(set(receipt['outputs']) == {'aggregate.json', 'private-per-query.jsonl', 'private-target-changes.jsonl'}, 'Primary exact three output witnesses')
        for key, name in [('primary_aggregate', 'aggregate.json'), ('primary_per_query', 'private-per-query.jsonl'), ('primary_changes', 'private-target-changes.jsonl')]:
            expected = {k: request[key][k] for k in ('bytes', 'sha256')}
            require(all(receipt['outputs'][name].get(k) == v for k, v in expected.items()), 'Primary closed-output hash binding')
        def lookup_refs(rows):
            require(type(rows) is list, 'Input witness list')
            result = {}
            for r in rows:
                require(type(r) is dict and set(r) == {'path', 'bytes', 'sha256'}, 'Input witness descriptor')
                require(r['path'] not in result, 'Duplicate input witness path')
                result[r['path']] = {k: r[k] for k in ('bytes', 'sha256')}
            return result
        closed_pins, before_pins = lookup_refs(receipt['input_hashes']), lookup_refs(marker['input_hashes'])
        require(sum(v['sha256'] == PRIMARY_CODE_SHA and v['bytes'] == 22141 for v in before_pins.values()) == 1 and sum(v['sha256'] == PRIMARY_STATS_SHA and v['bytes'] == 7254 for v in before_pins.values()) == 1, 'Original marker binds exact independently reviewed primary code')
        require(marker.get('rng') == 'stdlib random.Random(61061).randrange(M); sorted signed64 user frame; shared2000 draws; multiplicity; type7', 'Original frozen RNG declaration')
        for path, value in before_pins.items():
            require(closed_pins.get(path) == value, 'Before/closed input hash drift')
        require(closed_pins.get(str(primary_paths['primary_before_y'])) == {k: request['primary_before_y'][k] for k in ('bytes', 'sha256')}, 'Closed primary BEFORE_Y witness')
        require(marker.get('phase') == 'BEFORE_LOGICAL_Y' and marker.get('queries') == 6000 and marker.get('prior_pairs') == 44172 and marker.get('arms') == list(ARMS), 'Complete original BEFORE_Y marker')
        require(marker.get('analysis_identity') == original_request['analysis'] and original_request['analysis']['sha256'] == ANALYSIS_SHA, 'Frozen analysis identity')
        descriptor(original_request['analysis']);descriptor(original_request['root_acceptance'])
        seal_path = descriptor(original_request['seal']);seal = metadata(seal_path)
        require(set(seal['outputs']) == {'Q6000.jsonl', 'candidates.jsonl', 'prior-pairs.jsonl'}, 'Fixed three sealed streams')
        for name, item in seal['outputs'].items():
            require(set(item) == {'bytes', 'sha256', 'rows'} and type(item['rows']) is int and type(item['bytes']) is int and 0 <= item['bytes'] <= 256*2**20, 'Bound stream witness')
            path = seal_path.parent/name;value = pin(path, {k: item[k] for k in ('bytes', 'sha256')})
            require(before_pins.get(str(path)) == value, 'Original marker binds exact sealed stream')
        records = load_cohort(seal_path.parent, seal, budget.tick)
        labels = [descriptor(item) for item in original_request['labels']]
        require(len(labels) == 3, 'Three historical labels')
        for item in original_request['labels']:
            require(before_pins.get(item['path']) == {k: item[k] for k in ('bytes', 'sha256')}, 'Original BEFORE_Y label identity')
        frame = sorted({r['user_id'] for r in records})
        require(marker['frame_users'] == len(frame) and marker['frame_sha256'] == hashlib.sha256(json.dumps(frame, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(), 'Original complete all-user RNG frame')
        # Root terminal observes the original primary process; this separate marker fixes our own inputs before labels.
        independent_marker = output/'ORACLE_BEFORE_Y.json'
        write(independent_marker, {'phase': 'INDEPENDENT_BEFORE_LOGICAL_Y', 'queries': len(records), 'frame_users': len(frame), 'root_original_terminal': request['root_original_terminal'], 'inputs': [{'path': str(p), **v} for p, v in pins]}, budget)
        marker_pin = pin(independent_marker)
        target_rows(labels, records, independent_marker, marker_pin, budget.tick)
        independent = module.calculate(records, draws=2000, seed=61061, check=budget.tick)
        write(output/'private-bootstrap.json', independent['_bootstrap'], budget)
        private_checks = compare_private(records, primary_paths['primary_per_query'], primary_paths['primary_changes'], budget.tick)
        primary = metadata(primary_paths['primary_aggregate'], 8*2**20)
        comparison = compare_summary(independent, primary)
        result = {'status': 'INDEPENDENT_VALUES_MATCH_PENDING_ROOT_CLOSURE', 'scope': 'fixed reused cohort, no causal/generalization/achieved ranking claim', 'private_checks': private_checks, 'metric_checks': comparison, 'oracle_summary': independent['summary'], 'fits': 0, 'new_predictions': 0}
        write(output/'result.json', result, budget)
    except BaseException as error:
        failure = error
    # Each cleanup/check is attempted separately; no truth-testing of retained exceptions.
    for label, action in [('late_input_hashes', lambda: [require(identity(p, budget.tick) == v, 'Late independent input hash drift') for p, v in pins])]:
        try:
            action()
        except BaseException as error:
            secondary.append({'stage': label, 'type': type(error).__name__})
            if failure is None:
                failure = error
            else:
                annotate(failure, 'Secondary verifier failure: '+label)
    telemetry = None
    try:
        telemetry = budget.sample()
    except BaseException as error:
        secondary.append({'stage': 'telemetry', 'type': type(error).__name__})
        if failure is None:
            failure = error
        else:
            annotate(failure, 'Secondary verifier telemetry failure')
    try:
        receipt = {'status': 'FAILED' if failure is not None else 'COMPLETE_INDEPENDENT_VALUES_UNREVIEWED', 'inputs': [{'path': str(p), **v} for p, v in pins], 'telemetry': telemetry, 'limits': request['limits'], 'secondary': secondary, 'startup_final_exit_tail': 'outside self timer; Root external original terminal required', 'physical_IO': 'UNKNOWN', 'hard_aggregate_containment': False, 'fits': 0, 'new_predictions': 0}
        if failure is not None:
            try:
                message = str(failure)[:2048]
            except BaseException:
                message = '<unprintable>'
            receipt['primary'] = {'type': type(failure).__name__, 'message': message}
        outputs = {}
        for p in output.iterdir():
            if p.is_file():
                outputs[p.name] = identity(p)
        receipt['outputs'] = outputs
        require(len(encode(receipt)) <= 2*2**20, 'Final receipt reserve')
        write(output/'receipt.json', receipt)
    except BaseException as error:
        if failure is None:
            failure = error
        else:
            annotate(failure, 'Secondary independent receipt failure: '+type(error).__name__)
    if failure is not None:
        raise failure
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(run(args.request, args.output))
