"""SOURCE prototype: fixed6000 outcome-blind seal only; Root has not admitted a real run."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import types

CORE_PATH = Path('/tmp/tlab-hyp061-discovery-proposal-v2/discovery.py')
CORE_SHA = 'a903a30f06b83314eb1f83dcb6693237d59f814d09a9e8956bb35f4345e45d4b'
CORE_BYTES = 21921
SOURCE_START = datetime(2019, 10, 1)


def load_core():
    raw = CORE_PATH.read_bytes()
    if len(raw) != CORE_BYTES or hashlib.sha256(raw).hexdigest() != CORE_SHA:
        raise ValueError('Pinned core mismatch')
    module = types.ModuleType('_hyp061_fixed_core_v2'); module.__file__ = str(CORE_PATH)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(CORE_PATH), 'exec'), module.__dict__)
    return module


c = load_core()
MAX_LIMITS = dict(c.MAX_LIMITS, output_bytes=256*2**20)


class Guard(c.Guard):
    def __init__(self, output, limits):
        c.need(type(limits) is dict and set(limits) == set(MAX_LIMITS) and
               all(type(v) is int and 0 < v <= MAX_LIMITS[k] for k,v in limits.items()), 'Bound finite seal limits required')
        self.output, self.limits, self.wall, self.cpu = output, limits, time.monotonic(), time.process_time()


def select6000(rows):
    """Same canonical validation and hash order as core Q100, without truncation."""
    first = c.freeze_queries(rows)
    queries = [c.Query(qid, user, c.anchor_utc(anchor)) for qid,user,anchor in rows]
    queries.sort(key=lambda q:(hashlib.sha256(c.PREFIX+q.query_id.encode('ascii')).digest(),q.query_id.encode('ascii')))
    c.need(queries[:100] == first, 'Q100 prefix changed')
    return queries


def controls(C0, P180, R20, rows, result):
    base = c.candidate_union(P180,R20,[])
    base_set = set(base)
    tail = [item for rank,item in sorted((r[4],r[1]) for r in rows if r[2]) if item not in base_set]
    c.need(set(tail) == C0-set(base), 'Original tail identity')
    k = min(len(tail),len(result['source']['count']),len(result['source']['cosine']))
    return dict(B=base,T=tail,k=k,matched_popular=c.candidate_union(P180,R20,tail[:k]),
                matched_count=c.candidate_union(P180,R20,result['source']['count'][:k]),
                matched_cosine=c.candidate_union(P180,R20,result['source']['cosine'][:k]))


class JSONL:
    def __init__(self, path, check):
        self.path, self.check, self.rows = Path(path), check, 0
        self.stream = self.path.open('xb',buffering=0)
    def emit(self, body):
        raw = (c.canon(body)+'\n').encode(); self.check(len(raw))
        c.need(self.stream.write(raw) == len(raw), 'Short JSONL write')
        self.rows += 1
    def close(self):
        self.stream.close()


def note(primary, text):
    try:
        BaseException.add_note(primary,text)
    except BaseException:
        pass


def finish(primary, operations, persist):
    secondary = []
    for label, operation in operations:
        try:
            operation()
        except BaseException as error:
            secondary.append(dict(stage=label,**c.describe(error)))
    if primary is None and secondary:
        primary = RuntimeError('Seal finalization failed')
    if primary is not None:
        for error in secondary:
            note(primary,'Secondary failure: '+c.canon(error))
    try:
        persist(primary,secondary)
    except BaseException as error:
        if primary is None:
            primary = error
        else:
            note(primary,'Receipt failure: '+c.canon(c.describe(error)))
    if primary is not None:
        raise primary


def parse_request(raw):
    c.need(len(raw) <= 128*1024, 'Bound request metadata')
    def pairs(rows):
        body = dict(rows); c.need(len(body)==len(rows), 'Duplicate request key'); return body
    request = json.loads(raw,object_pairs_hook=pairs)
    c.need(type(request) is dict and set(request)=={'version','db','queries','candidates','bridge_ref','q100_reference','source_rows','limits'} and
           type(request['version']) is int and request['version']==1, 'Exact seal request fields')
    c.need(type(request['queries']) is list and type(request['candidates']) is list and
           len(request['queries'])==len(request['candidates'])==3 and type(request['source_rows']) is int and request['source_rows']>0, 'Fixed shard metadata')
    return request


def reference_hash(result, expected):
    raw = (c.canon(result)+'\n').encode()
    c.need(dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) == expected, 'Accepted Q100 result mismatch')


def stream_prior_pairs(con, queries, writer, check):
    """One complete source relation; all event types, all prior items for fixed Q."""
    con.execute('CREATE TEMP TABLE fixed_q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,global_rank BIGINT)')
    con.executemany('INSERT INTO fixed_q VALUES(?,?,?,?)',[(q.query_id,q.user_id,q.anchor,r) for r,q in enumerate(queries)])
    check()
    con.execute('SELECT q.query_id,e.product_id FROM discovery_events e JOIN fixed_q q ON e.user_id=q.user_id WHERE e.event_time>=? AND e.event_time<q.anchor AND e.product_id IS NOT NULL GROUP BY q.query_id,e.product_id,q.global_rank ORDER BY q.global_rank,e.product_id',[SOURCE_START])
    counts = Counter()
    while True:
        check(); chunk = con.fetchmany(8192)
        if not chunk:
            break
        for qid,item in chunk:
            c.integer(item); writer.emit(dict(query_id=qid,product_id=item)); counts[qid] += 1
    return counts


def run(request_path, output):
    output = Path(output).resolve()
    c.need(output.is_relative_to(Path('/private/tmp')) and not output.exists(), 'Fresh TMP output')
    with Path(request_path).open('rb') as stream:
        raw = stream.read(128*1024+1)
    request = parse_request(raw); output.mkdir(mode=0o700); guard = Guard(output,request['limits'])
    pins, writers, con, primary = [], [], None, None
    ledger = dict(status='FAILED',fits=0,model_predictions=0,physical_io='UNKNOWN',adequacy='UNKNOWN',
                  graph_builds=[],history_select_reserved=0,history_select_completion='not_started',shared_profile_edge_visits=0,queries_written=0,q100_matches=0,outputs={})
    def pin(path, expected=None):
        value = c.file_ref(path,guard.check)
        c.need(expected is None or value==expected, 'Pin mismatch: '+str(path))
        pins.append((Path(path),value)); return value
    def descriptor(body):
        c.need(type(body) is dict and set(body)=={'path','bytes','sha256'} and type(body['path']) is str and
               type(body['bytes']) is int and body['bytes']>=0 and type(body['sha256']) is str and re.fullmatch('[0-9a-f]{64}',body['sha256']), 'Resolved descriptor')
        pin(body['path'],{k:body[k] for k in ('bytes','sha256')}); return body['path']
    def writer(name):
        value = JSONL(output/name,guard.check); writers.append(value); return value
    try:
        pin(__file__); pin(CORE_PATH,dict(bytes=CORE_BYTES,sha256=CORE_SHA))
        pin(request_path,dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        db = descriptor(request['db']); descriptor(request['bridge_ref'])
        qp,cp = [[descriptor(d) for d in request[k]] for k in ('queries','candidates')]
        c.need(request['q100_reference']['bytes'] <= 128*1024, 'Bound Q100 manifest')
        reference = json.loads(Path(descriptor(request['q100_reference'])).read_text())
        c.need(type(reference) is dict and set(reference)=={'version','records'} and type(reference['version']) is int and reference['version']==1 and
               type(reference['records']) is dict and len(reference['records'])==100, 'Exact Q100 reference manifest')
        refs = {}
        for qid,body in reference['records'].items():
            descriptor(body); refs[qid] = {k:body[k] for k in ('bytes','sha256')}
        import duckdb
        c.need(duckdb.__version__=='1.5.6', 'Frozen DuckDB version')
        con = duckdb.connect(':memory:',config={'threads':'2','memory_limit':'2GB','max_temp_directory_size':str(request['limits']['spill_bytes'])+'B','temp_directory':str(output/'spill')})
        for name,paths,columns in (('input_q',qp,c.Q_COLUMNS),('input_c',cp,c.C_COLUMNS)):
            con.read_parquet(paths).project(','.join(n for n,t in columns)).create_view(name)
            c.need([tuple(r[:2]) for r in con.execute('DESCRIBE '+name).fetchall()]==columns, 'Exact input projection types')
        c.need(con.execute('SELECT count(*) FROM input_q').fetchone()[0]==6000, 'Exact6000 query count')
        queries = select6000(con.execute('SELECT query_id,user_id,anchor FROM input_q').fetchall())
        c.need(set(refs)=={q.query_id for q in queries[:100]}, 'Accepted Q100 identity mismatch')
        qout = writer('Q6000.jsonl')
        for rank,q in enumerate(queries):
            qout.emit(dict(global_rank=rank,query_id=q.query_id,user_id=q.user_id,anchor=q.anchor.isoformat()+'Z'))
        c.need(con.execute('SELECT count(*) FROM input_c').fetchone()[0]<=1320000, 'Original C0 count bound')
        c.need(con.execute('SELECT count(*) FROM input_c c ANTI JOIN input_q q USING(query_id)').fetchone()[0]==0, 'Foreign C0 query')
        con.execute("ATTACH '"+db.replace("'","''")+"' AS accepted_source(READ_ONLY)")
        c.need([tuple(r[:2]) for r in con.execute('DESCRIBE accepted_source.main.events').fetchall()]==c.SOURCE_COLUMNS, 'Typed9 source schema')
        con.execute('CREATE TEMP VIEW discovery_events AS SELECT event_time,event_type,product_id,user_id FROM accepted_source.main.events')
        pout = writer('prior-pairs.jsonl'); ledger.update(history_select_reserved=1,history_select_completion='UNKNOWN_on_failure')
        prior_counts = stream_prior_pairs(con,queries,pout,guard.check)
        ledger['prior_pairs_written']=pout.rows; ledger['history_select_completion']='complete'
        cout = writer('candidates.jsonl'); ranks = {q.query_id:r for r,q in enumerate(queries)}
        for anchor in c.ANCHORS:
            rows_by_query = defaultdict(list)
            fields = ','.join('c.'+name for name,t in c.C_COLUMNS)
            rows = con.execute('SELECT '+fields+' FROM input_c c JOIN input_q q USING(query_id) WHERE q.anchor=?',[anchor]).fetchall()
            for row in rows:
                rows_by_query[row[0]].append(row)
            entry = dict(anchor=anchor.isoformat()+'Z',complete=False,reserved_source_selects=1)
            ledger['graph_builds'].append(entry)
            graph = c.extract_graph(con,anchor,guard.check,edge_cap=request['limits']['admitted_edges'])
            entry.update(complete=True,identity=graph.identity,statistics=graph.statistics)
            for q in (q for q in queries if q.anchor==anchor):
                C0,P180,R20 = c.original_sources(q,rows_by_query[q.query_id])
                result = c.discover(graph,q.user_id,R20,C0,guard.check)
                result.update(query_id=q.query_id,C_count=c.candidate_union(P180,R20,result['source']['count']),C_cos=c.candidate_union(P180,R20,result['source']['cosine']))
                if q.query_id in refs:
                    reference_hash(result,refs[q.query_id]); ledger['q100_matches'] += 1
                cout.emit(dict(global_rank=ranks[q.query_id],query_id=q.query_id,user_id=q.user_id,anchor=q.anchor.isoformat()+'Z',
                    C0=sorted(C0),P180=P180,R20=R20,core_result=result,controls=controls(C0,P180,R20,rows_by_query[q.query_id],result),prior_pair_count=prior_counts[q.query_id]))
                ledger['queries_written'] += 1; ledger['shared_profile_edge_visits'] += result['profile_edge_visits']
            del graph,rows,rows_by_query
        c.need(ledger['queries_written']==6000 and ledger['q100_matches']==100 and ledger['shared_profile_edge_visits']<=393216000, 'Complete fixed6000 seal')
    except BaseException as error:
        primary = error
    operations = [(w.path.name+' close',w.close) for w in writers]
    operations.append(('DuckDB close',lambda:con.close() if con is not None else None))
    def late_pins():
        for path,expected in pins:
            c.need(c.file_ref(path,guard.check)==expected,'Late pin mismatch: '+str(path))
    def output_refs():
        for w in writers:
            ledger['outputs'][w.path.name]=dict(rows=w.rows,**c.file_ref(w.path,guard.check))
    operations += [('late pins fail-fast',late_pins),('closed output hashes',output_refs)]
    def persist(error,secondary):
        ledger.update(secondary=secondary,bound_files=[dict(path=str(p),**r) for p,r in pins],core=dict(path=str(CORE_PATH),bytes=CORE_BYTES,sha256=CORE_SHA),
                      descriptor_source_row_visits_upper=(len(ledger['graph_builds'])+ledger['history_select_reserved'])*request['source_rows'],
                      limits=request['limits'],telemetry=guard.telemetry(),format='hyp061-fixed6000-jsonl-v1; Q global hash order; candidates anchor/global_rank; prior pairs global_rank/product signed order',
                      resource_scope='Cooperative self CPU/wall/peak process RSS; no hard aggregate RSS or physical IO proof')
        if error is not None:
            ledger['error']=c.describe(error); name='FAILED.json'
        else:
            ledger['status']='SEALED6000_UNREVIEWED_NO_OUTCOMES'; name='seal.json'; guard.check()
        c.need(len(c.canon(ledger).encode())<=2*2**20,'Receipt reserve')
        c.write_json(output/name,ledger)
    finish(primary,operations,persist)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--request',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); sys.exit(run(args.request,args.output))
