"""HYP061 query-local discovery only. Runtime inputs/limits must be bound by Root."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import resource
import sys
import time
from types import MappingProxyType

Q_COLUMNS = [('query_id', 'VARCHAR'), ('user_id', 'BIGINT'), ('anchor', 'TIMESTAMP')]
C_COLUMNS = [('query_id', 'VARCHAR'), ('product_id', 'BIGINT'), ('from_popular', 'BOOLEAN'),
             ('from_recent', 'BOOLEAN'), ('popular_source_rank', 'BIGINT'),
             ('recent_source_rank', 'BIGINT'), ('last_user_event_time', 'TIMESTAMP')]
SOURCE_COLUMNS = list(zip(('event_time','event_type','product_id','category_id','category_code','brand','price','user_id','user_session'),
                         ('TIMESTAMP','VARCHAR','BIGINT','BIGINT','VARCHAR','VARCHAR','DECIMAL(12,2)','BIGINT','VARCHAR')))
ANCHORS = tuple(datetime(2019, 10, d) for d in (8, 9, 10))
PREFIX = b'tlab-hyp061-q100-v1\0'
MAX_LIMITS = dict(cpu_seconds=1200, wall_seconds=1800, rss_bytes=6*2**30,
                  spill_bytes=8*2**30, output_bytes=64*2**20, admitted_edges=10000000)


def need(value, message):
    if not value:
        raise ValueError(message)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def integer(value):
    need(type(value) is int and -2**63 <= value < 2**63, 'Exact signed64 ID required')
    return value


def anchor_utc(value):
    need(isinstance(value, datetime), 'Datetime required')
    value = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    need(value.microsecond == 0, 'Second precision required')
    return value


def qid_for(user, anchor):
    return hashlib.sha256(f'query|2026|{anchor_utc(anchor):%Y-%m-%dT%H:%M:%SZ}|{integer(user)}'.encode('ascii')).hexdigest()


@dataclass(frozen=True)
class Query:
    query_id: str
    user_id: int
    anchor: datetime


def freeze_queries(rows, *, production=True):
    queries, identities = [], set()
    for qid, user, raw in rows:
        anchor = anchor_utc(raw); integer(user)
        need(type(qid) is str and re.fullmatch('[0-9a-f]{64}', qid) and qid == qid_for(user, anchor), 'Canonical query identity')
        need(anchor in ANCHORS and (user, anchor) not in identities, 'Unique frozen user-day')
        identities.add((user, anchor)); queries.append(Query(qid, user, anchor))
    need(len({q.query_id for q in queries}) == len(queries), 'Duplicate query ID')
    if production:
        need(len(queries) == 6000 and Counter(q.anchor for q in queries) == Counter({a: 2000 for a in ANCHORS}), 'Exact6000Q8-10')
    return sorted(queries, key=lambda q: (hashlib.sha256(PREFIX + q.query_id.encode('ascii')).digest(), q.query_id.encode('ascii')))[:100]


def original_sources(query, rows):
    """Validate selected original C0; derive P180/R20 before union, no refill."""
    members, popular, recent = set(), [], []
    for qid, item, p, r, pr, rr, stamp in rows:
        integer(item)
        need(qid == query.query_id and item not in members and type(p) is bool and type(r) is bool and (p or r), 'Original C0 identity/flags')
        members.add(item)
        need((type(pr) is int and 1 <= pr <= 200) if p else pr is None, 'P200 rank/flag')
        need((type(rr) is int and 1 <= rr <= 20) if r else rr is None, 'R20 rank/flag')
        if p:
            popular.append((pr, item))
        if r:
            need(stamp is not None, 'Recent timestamp required')
            stamp = anchor_utc(stamp)
            need(query.anchor-timedelta(days=7) <= stamp < query.anchor, 'Strict-past7d recent witness')
            recent.append((rr, item, stamp))
        else:
            need(stamp is None, 'Absent recent source cannot carry timestamp')
    popular.sort(); recent.sort()
    need(len(members) <= 220 and [r for r, _ in popular] == list(range(1, len(popular)+1)), 'Complete P prefix')
    need([r for r, _, _ in recent] == list(range(1, len(recent)+1)), 'Complete R prefix')
    ordered = sorted(sorted(recent, key=lambda x: x[1]), key=lambda x: x[2], reverse=True)
    need([i for _, i, _ in recent] == [i for _, i, _ in ordered], 'Canonical R order')
    return members, [i for rank, i in popular if rank <= 180], [i for _, i, _ in recent]


@dataclass(frozen=True)
class Graph:
    profiles: dict
    audience: dict
    degrees: dict
    identity: str
    statistics: dict


def graph_from_profiles(profiles, statistics=None, *, expected_edges=None, check=lambda: None):
    audience, digest, edges = defaultdict(list), hashlib.sha256(), 0
    for pos, user in enumerate(sorted(profiles)):
        if pos % 1024 == 0:
            check()
        integer(user); items = profiles[user]
        need(type(items) is tuple and 1 <= len(items) <= 32 and items == tuple(sorted(set(items))), 'Complete admitted profile, degree1..32')
        for item in items:
            integer(item); audience[item].append(user)
        edges += len(items); digest.update((canon([user, items]) + '\n').encode())
    need(expected_edges is None or edges == expected_edges, 'Incomplete admitted edge fetch')
    audience = {i: tuple(users) for i, users in audience.items()}
    stats = dict(statistics or {}, admitted_users=len(profiles), admitted_edges=edges)
    check()
    return Graph(MappingProxyType(dict(profiles)), MappingProxyType(audience),
                 MappingProxyType({i: len(v) for i, v in audience.items()}), digest.hexdigest(), stats)


def graph_from_edges(edges):
    raw = defaultdict(set)
    for user, item in edges:
        if user is not None and item is not None:
            raw[integer(user)].add(integer(item))
    profiles = {u: tuple(sorted(items)) for u, items in raw.items() if len(items) <= 32}
    return graph_from_profiles(profiles, dict(raw_users=len(raw), raw_edges=sum(map(len, raw.values())),
                                            excluded_profiles=sum(len(v) > 32 for v in raw.values())))


def discover(graph, user, recent, original_C0, check=lambda: None):
    """Both scores share one complete G_q expansion and global degrees."""
    integer(user); self_items = set(graph.profiles.get(user, ()))
    need(len(recent) <= 20 and len(set(recent)) == len(recent) and set(recent) <= set(original_C0), 'Original unique R20 inside C0')
    count, cosine, supports, rejection = defaultdict(float), defaultdict(float), defaultdict(list), []
    visits = 0
    seeds = tuple(recent[:4])  # Freeze before all admission guards; no fifth refill.
    for h in seeds:
        check(); integer(h)
        base = graph.degrees.get(h, 0)
        need((h in graph.audience) == (base > 0), 'Incomplete seed adjacency')
        posting = graph.audience.get(h, ())
        need(len(posting) == base, 'Incomplete seed audience')
        dh = base - (h in self_items)
        if dh == 0 or dh > 512:
            rejection.append(dict(seed=h, degree=dh, reason='seed_view_empty' if dh == 0 else 'audience_guard')); continue
        need(dh > 0, 'Invalid seed degree')
        need(len(posting) <= 513 and len(set(posting)) == base, 'Incomplete admitted seed audience')
        co = Counter()
        for v in posting:
            need(v in graph.profiles and h in graph.profiles[v], 'Incomplete profile adjacency')
            if v == user:
                continue
            profile = graph.profiles[v]; need(1 <= len(profile) <= 32, 'Invalid complete profile')
            visits += len(profile)
            co.update(j for j in profile if j != h)
        rejected = sum(c < 3 for c in co.values())
        rejection.append(dict(seed=h, degree=dh, reason='admitted', support_below3=rejected))
        for j, c in sorted(co.items()):
            if c < 3:
                continue
            need(j in graph.degrees, 'Incomplete endpoint degree')
            dj = graph.degrees[j] - (j in self_items)
            need(dj >= c and dh >= c and dj > 0, 'Invalid global query-local norm')
            a = c*c/(c+10)
            count[j] += a; cosine[j] += a/math.sqrt(dh*dj)
            supports[j].append([h, c, dh, dj])
    need(set(count) == set(cosine), 'Sources must share discovery domain')
    need(all(math.isfinite(x) and x > 0 for s in (count, cosine) for x in s.values()), 'Nonpositive/nonfinite score')
    # Exclude the entire original P200 U R20 BEFORE either top20.
    novel = set(count) - set(original_C0)
    ties = {j: hashlib.sha256(str(integer(j)).encode('ascii')).digest() for j in novel}
    ranked = {name: sorted(novel, key=lambda j: (-scores[j], ties[j], j))[:20]
              for name, scores in (('count', count), ('cosine', cosine))}
    domain = [dict(product_id=j, support=supports[j], count=count[j], cosine=cosine[j], in_C0=j in original_C0) for j in sorted(count)]
    ranks = {name: [dict(rank=r, product_id=j, score=scores[j], support=supports[j]) for r,j in enumerate(ranked[name],1)]
             for name,scores in (('count',count),('cosine',cosine))}
    return dict(seeds=list(seeds), source=ranked, ranked_source=ranks, domain=domain, rejection=rejection, profile_edge_visits=visits,
                distinct_top20_sets=set(ranked['count']) != set(ranked['cosine']))


def candidate_union(popular180, recent20, source20):
    result = list(dict.fromkeys([*popular180, *recent20, *source20]))
    need(len(source20) <= 20 and len(set(source20)) == len(source20) and len(result) <= 220, 'Native no-refill candidate bound')
    return result


def extract_graph(con, anchor, check=lambda: None, *, edge_cap=10000000):
    """One complete events SELECT per represented anchor; temp/norm/index work extra."""
    anchor = anchor_utc(anchor); check()
    con.execute("CREATE OR REPLACE TEMP TABLE dd_edges AS SELECT DISTINCT user_id,product_id FROM discovery_events WHERE event_type='view' AND event_time>=? AND event_time<? AND user_id IS NOT NULL AND product_id IS NOT NULL", [anchor-timedelta(days=7), anchor]); check()
    con.execute('CREATE OR REPLACE TEMP TABLE dd_degree AS SELECT user_id,count(*) m FROM dd_edges GROUP BY user_id'); check()
    raw_users, excluded, maximum = con.execute('SELECT count(*),count(*) FILTER(WHERE m>32),coalesce(max(m),0) FROM dd_degree').fetchone()
    raw_edges = con.execute('SELECT count(*) FROM dd_edges').fetchone()[0]
    n = con.execute('SELECT coalesce(sum(m),0) FROM dd_degree WHERE m<=32').fetchone()[0]
    need(n <= edge_cap, 'Admitted edge cap before Python allocation')
    con.execute('SELECT e.user_id,e.product_id FROM dd_edges e JOIN dd_degree d USING(user_id) WHERE d.m<=32 ORDER BY e.user_id,e.product_id')
    profiles, fetched = defaultdict(list), 0
    while True:
        check(); chunk = con.fetchmany(8192)
        if not chunk:
            break
        fetched += len(chunk); need(fetched <= n, 'Unexpected adjacency growth')
        for user, item in chunk:
            profiles[user].append(item)
    need(fetched == n, 'Incomplete adjacency fetch')
    return graph_from_profiles({u: tuple(v) for u, v in profiles.items()},
        dict(raw_users=raw_users, raw_edges=raw_edges, excluded_profiles=excluded, max_raw_degree=maximum), expected_edges=n, check=check)


def describe(error):
    try:
        return dict(type=type(error).__name__, message=str(error)[:2048])
    except BaseException:
        return dict(type=type(error).__name__, message='<unprintable>')


class Guard:
    def __init__(self, output, limits):
        need(set(limits) == set(MAX_LIMITS) and all(type(v) is int and 0 < v <= MAX_LIMITS[k] for k, v in limits.items()), 'Root-bound finite limits required')
        self.output, self.limits, self.wall, self.cpu = output, limits, time.monotonic(), time.process_time()

    def telemetry(self):
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return dict(wall_seconds=time.monotonic()-self.wall, cpu_seconds=time.process_time()-self.cpu,
                    rss_bytes=int(rss if sys.platform == 'darwin' else rss*1024), cooperative=True, physical_io_bytes='UNKNOWN')

    def check(self, extra=0):
        t = self.telemetry(); need(all(t[k] < self.limits[k] for k in ('wall_seconds','cpu_seconds','rss_bytes')), 'Resource limit')
        sizes = [(p, p.stat().st_size) for p in self.output.rglob('*') if p.is_file()]
        need(sum(n for p, n in sizes if 'spill' in p.relative_to(self.output).parts) <= self.limits['spill_bytes'], 'Spill limit')
        need(sum(n for p, n in sizes if 'spill' not in p.relative_to(self.output).parts)+extra <= self.limits['output_bytes']-2*2**20, 'Output limit; receipt reserve2MiB')


def file_ref(path, check):
    digest, size = hashlib.sha256(), 0; check()
    with Path(path).open('rb') as stream:
        while True:
            check(); block = stream.read(2**20)
            if not block:
                break
            digest.update(block); size += len(block)
    return dict(bytes=size, sha256=digest.hexdigest())


def write_json(path, body, check=lambda extra=0: None):
    raw = (canon(body)+'\n').encode(); check(len(raw))
    with Path(path).open('xb') as stream:
        stream.write(raw)


def run(request_path, output):
    """Root later supplies exact DB/Q/C/semantic-bridge descriptors, no fallback."""
    output = Path(output).resolve(); need(output.is_relative_to(Path('/private/tmp')) and not output.exists(), 'Fresh TMP output')
    with Path(request_path).open('rb') as stream:
        request_raw = stream.read(128*1024+1)
    need(len(request_raw) <= 128*1024, 'Bounded request metadata')
    def pairs(rows):
        body = dict(rows); need(len(body) == len(rows), 'Duplicate request key'); return body
    request = json.loads(request_raw, object_pairs_hook=pairs)
    need(set(request) == {'version','db','queries','candidates','bridge_ref','source_rows','limits'} and type(request['version']) is int and request['version'] == 1, 'Request schema')
    output.mkdir(mode=0o700); guard = Guard(output, request['limits'])
    report = dict(status='FAILED', fits=0, model_predictions=0, physical_io='UNKNOWN', real_quality_inference=False,
                  per_query=[], graph_builds=[], outputs={}, event_passes_reserved=0, profile_edge_visits=0)
    pins, primary, con, secondary = [], None, None, []
    def pin(path, expected=None):
        value = file_ref(path, guard.check); need(expected is None or value == expected, 'Input pin mismatch: '+str(path))
        pins.append((Path(path), value)); return value
    def descriptor(body):
        need(type(body) is dict and set(body) == {'path','bytes','sha256'} and type(body['bytes']) is int and body['bytes'] >= 0 and re.fullmatch('[0-9a-f]{64}', body['sha256']), 'Resolved Root descriptor required')
        pin(body['path'], {k: body[k] for k in ('bytes','sha256')}); return body['path']
    try:
        pin(__file__); pin(request_path, dict(bytes=len(request_raw),sha256=hashlib.sha256(request_raw).hexdigest()))
        need(len(request['queries']) == len(request['candidates']) == 3 and type(request['source_rows']) is int and request['source_rows'] > 0, 'Three frozen train shards and source descriptor count')
        db = descriptor(request['db']); descriptor(request['bridge_ref'])  # Root-reviewed semantic bridge is opaque; no outcome parsing.
        qp, cp = [[descriptor(d) for d in request[k]] for k in ('queries','candidates')]
        import duckdb
        need(duckdb.__version__ == '1.5.6', 'Frozen DuckDB version')
        con = duckdb.connect(':memory:', config={'threads':'2','memory_limit':'2GB','max_temp_directory_size':str(request['limits']['spill_bytes'])+'B','temp_directory':str(output/'spill')})
        con.read_parquet(qp).create_view('input_q'); con.read_parquet(cp).create_view('input_c')
        for table, columns in (('input_q', Q_COLUMNS), ('input_c', C_COLUMNS)):
            schema = dict((r[0], r[1]) for r in con.execute('DESCRIBE '+table).fetchall())
            need(all(schema.get(n) == t for n, t in columns), 'Required input projection types')
        qrows = con.execute('SELECT query_id,user_id,anchor FROM input_q').fetchall(); queries = freeze_queries(qrows)
        seal = [[q.query_id,q.user_id,q.anchor.isoformat()+'Z'] for q in queries]
        write_json(output/'Q100-seal.json', dict(selector='SHA256 prefix + ASCII hex query_id; unsigned bytes ascending', queries=seal), guard.check)
        seal_ref = pin(output/'Q100-seal.json'); report['outputs']['Q100-seal.json'] = seal_ref
        report['Q100_identity'] = hashlib.sha256(canon(seal).encode()).hexdigest()
        con.execute('CREATE TEMP TABLE selected_q(query_id VARCHAR)'); con.executemany('INSERT INTO selected_q VALUES (?)', [(q.query_id,) for q in queries])
        con.execute('CREATE TEMP TABLE selected_c AS SELECT c.query_id,c.product_id,c.from_popular,c.from_recent,c.popular_source_rank,c.recent_source_rank,c.last_user_event_time FROM input_c c SEMI JOIN selected_q q USING(query_id)')
        need(con.execute('SELECT count(*) FROM selected_c').fetchone()[0] <= 22000, 'Q100 originalC0 bound')
        by_query = defaultdict(list)
        for row in con.execute('SELECT * FROM selected_c').fetchall():
            by_query[row[0]].append(row)
        sources = {q.query_id: original_sources(q, by_query[q.query_id]) for q in queries}
        con.execute("ATTACH '"+db.replace("'", "''")+"' AS accepted_source (READ_ONLY)")
        need([tuple(r[:2]) for r in con.execute('DESCRIBE accepted_source.main.events').fetchall()] == SOURCE_COLUMNS, 'Typed9 source schema')
        con.execute('CREATE TEMP VIEW discovery_events AS SELECT event_time,event_type,product_id,user_id FROM accepted_source.main.events')
        for anchor in sorted({q.anchor for q in queries}):
            report['event_passes_reserved'] += 1
            entry = dict(anchor=anchor.isoformat()+'Z', start=guard.telemetry(), reserved_event_selects=1, graph_complete=False, event_select_completion='UNKNOWN_on_failure')
            report['graph_builds'].append(entry)
            graph = extract_graph(con, anchor, guard.check, edge_cap=request['limits']['admitted_edges'])
            entry.update(identity=graph.identity, statistics=graph.statistics, graph_complete=True, event_select_completion='complete', after_global_build=guard.telemetry())
            for q in (q for q in queries if q.anchor == anchor):
                C0, P180, R20 = sources[q.query_id]; result = discover(graph, q.user_id, R20, C0, guard.check)
                result.update(query_id=q.query_id, C_count=candidate_union(P180,R20,result['source']['count']), C_cos=candidate_union(P180,R20,result['source']['cosine']))
                artifact = output/(q.query_id+'.json'); write_json(artifact, result, guard.check)
                report['outputs'][artifact.name] = pin(artifact)
                report['profile_edge_visits'] += result['profile_edge_visits']
                report['per_query'].append(dict(query_id=q.query_id, count_size=len(result['source']['count']), cosine_size=len(result['source']['cosine']),
                    count_C_size=len(result['C_count']), cosine_C_size=len(result['C_cos']), distinct_sets=result['distinct_top20_sets']))
            del graph
        need(len(report['per_query']) == 100 and report['event_passes_reserved'] <= 3 and report['profile_edge_visits'] <= 6553600, 'Finite complete100Q ledger')
        report['mechanism_thresholds'] = dict(nonempty_queries=sum(r['count_size'] > 0 for r in report['per_query']), distinct_set_queries=sum(r['distinct_sets'] for r in report['per_query']))
        report['status'] = 'COMPLETE_DISCOVERY_UNREVIEWED_RESOURCE_QUALIFICATION_UNKNOWN'
    except BaseException as error:
        primary = error
    operations = [('DuckDB close', lambda: con.close() if con is not None else None)]
    def late_pins():
        for path, expected in pins:
            need(file_ref(path, guard.check) == expected, 'Late pin mismatch: '+str(path))
    operations += [('late pins fail-fast', late_pins), ('telemetry', lambda: report.update(telemetry=guard.telemetry()))]
    for label, operation in operations:
        try:
            operation()
        except BaseException as error:
            secondary.append(dict(stage=label, **describe(error)))
    if primary is None and secondary:
        primary = RuntimeError('Finalization failed: '+canon(secondary))
    if primary is not None:
        for description in secondary:
            try:
                BaseException.add_note(primary, 'Secondary failure: '+canon(description))
            except BaseException:
                pass
        report.update(status='FAILED', error=describe(primary))
    report['descriptor_event_row_visits_upper'] = report['event_passes_reserved']*request['source_rows'] if type(request['source_rows']) is int else 'UNKNOWN'
    report.update(secondary=secondary, bound_files=[dict(path=str(p), **r) for p,r in pins], limits=request['limits'],
                  cost_scope='Includes global extraction/degrees/indices/scoring/sorts/output/prepost hashes; self process since Guard creation, outer Root covers startup/exit', adequacy='UNKNOWN')
    try:
        need(len(canon(report).encode()) <= 2*2**20, 'Reserved receipt cap'); write_json(output/'report.json', report)
    except BaseException as error:
        if primary is None:
            raise
        try:
            BaseException.add_note(primary, 'Receipt failure: '+canon(describe(error)))
        except BaseException:
            pass
    if primary is not None:
        raise primary
    need(not secondary, 'Finalization failed: '+canon(secondary))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--request', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); sys.exit(run(args.request, args.output))
