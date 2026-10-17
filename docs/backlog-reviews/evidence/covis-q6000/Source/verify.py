import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
if sys.flags.optimize != 0:
    raise RuntimeError('Optimization disables no verification: ordinary Python required')
import time
import traceback

PROPOSAL = Path(__file__).resolve().parent
OUT = Path('/private/tmp/tlab-hyp061-q6000-independent-correctness-runtime-v1-once')
JOB = Path('/private/tmp/tlab-hyp061-q6000-seal-runtime-v1-once')
PROD = JOB / 'producer'
REQUEST = Path('/private/tmp/tlab-hyp061-q6000-real-binding-proposal-v1/request.json')
TERMINAL = Path('/private/tmp/tlab-root-hyp061-q6000-seal-original-terminal-v1.json')
PREFIX = b'tlab-hyp061-q100-v1\0'
ANCHORS = tuple(dt.datetime(2019, 10, d) for d in (8, 9, 10))


def need(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def loads(raw):
    def pairs(rows):
        result = dict(rows)
        need(len(result) == len(rows), 'Duplicate JSON keys')
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def load(path):
    return loads(Path(path).read_bytes())

def write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    if Path(path).parent == OUT:
        need(sum(p.stat().st_size for p in OUT.iterdir() if p.is_file()) + len(raw) <= 64*2**20-65536, 'Aggregate result/log output cap with footer reserve')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)


def file_ref(path, check=lambda: None):
    path = Path(path)
    digest, size = hashlib.sha256(), 0
    check()
    with path.open('rb') as stream:
        while True:
            check()
            block = stream.read(2**20)
            if not block:
                break
            digest.update(block)
            size += len(block)
    check()
    return dict(path=str(path), bytes=size, sha256=digest.hexdigest(),
                mode=f'{path.stat().st_mode & 0o777:04o}')


def witness(row):
    return {k: row[k] for k in ('bytes', 'sha256')}



def expected_core(qid, C0, P, R, support_rows, nd, visit, near):
    counts, cosines, supports = {}, {}, collections.defaultdict(list)
    below = collections.Counter()
    for position, h, item, c, dh, dj in support_rows:
        if c < 3:
            below[position] += 1
            continue
        need(0 < c <= dh <= 512 and c <= dj, 'Query-local support/norm bound')
        contribution = (c*c)/(c+10)
        counts[item] = counts.get(item, 0.0) + contribution
        cosines[item] = cosines.get(item, 0.0) + contribution/math.sqrt(dh*dj)
        supports[item].append([h, c, dh, dj])
    need(counts.keys() == cosines.keys() and all(math.isfinite(v) and v > 0 for scores in (counts, cosines) for v in scores.values()), 'Shared finite score domain')
    domain = [dict(product_id=i, support=supports[i], count=counts[i], cosine=cosines[i], in_C0=i in C0) for i in sorted(counts)]
    sources, ranked, rejection = {}, {}, []
    for name, scores in [('count', counts), ('cosine', cosines)]:
        ordered = sorted(set(scores)-C0, key=lambda i: (-scores[i], hashlib.sha256(str(i).encode('ascii')).digest(), i))
        for a, b in zip(ordered, ordered[1:]):
            gap = scores[a] - scores[b]
            if gap == 0:
                near['exact_adjacent_ties'] += 1
            else:
                ratio = gap / math.ulp(scores[a])
                old = near['minimum_positive_adjacent_gap_ulps']
                near['minimum_positive_adjacent_gap_ulps'] = ratio if old is None else min(old, ratio)
        if len(ordered) > 20:
            gap = scores[ordered[19]] - scores[ordered[20]]
            if gap == 0:
                near['exact_boundary_ties'] += 1
            else:
                ratio = gap/math.ulp(scores[ordered[19]])
                near['nonzero_boundary_gaps_le4ulp'] += ratio <= 4
                old = near['min_positive_boundary_gap_ulps']
                near['min_positive_boundary_gap_ulps'] = ratio if old is None else min(old, ratio)
        sources[name] = ordered[:20]
        ranked[name] = [dict(rank=n, product_id=i, score=scores[i], support=supports[i]) for n, i in enumerate(ordered[:20], 1)]
        # Diagnostic only: the accepted protocol remains ordered binary64 addition.
        alternate = {i: math.fsum((c*c)/(c+10) / (math.sqrt(dh*dj) if name == 'cosine' else 1)
                                 for h,c,dh,dj in supports[i]) for i in scores}
        near['diagnostic_fsum_changed_values'] += sum(alternate[i] != scores[i] for i in scores)
        alternate_top = sorted(set(scores)-C0, key=lambda i: (-alternate[i], hashlib.sha256(str(i).encode('ascii')).digest(), i))[:20]
        near['diagnostic_fsum_top20_order_changes'] += alternate_top != sources[name]
        near['diagnostic_fsum_top20_set_changes'] += set(alternate_top) != set(sources[name])
    for position, h in enumerate(R[:4]):
        degree = nd[qid, position]
        reason = 'seed_view_empty' if degree == 0 else 'audience_guard' if degree > 512 else 'admitted'
        row = dict(seed=h, degree=degree, reason=reason)
        if reason == 'admitted':
            row['support_below3'] = below[position]
        rejection.append(row)
    pv = sum(visit.get((qid, p), 0) for p in range(len(R[:4])))
    union = {k: list(dict.fromkeys(P + R + s)) for k, s in sources.items()}
    need(all(len(v) <= 220 for v in union.values()), 'Native candidate bound')
    expected = dict(seeds=R[:4], source=sources, ranked_source=ranked, domain=domain,
                    rejection=rejection, profile_edge_visits=pv,
                    distinct_top20_sets=set(sources['count']) != set(sources['cosine']),
                    query_id=qid, C_count=union['count'], C_cos=union['cosine'])
    return expected


class ExactJSONL:
    """Compare one canonical typed record at a time; never truncate a long record."""
    def __init__(self, path, check):
        self.path, self.check, self.rows = Path(path), check, 0
        self.stream = self.path.open('rb')
    def expect(self, value):
        self.check()
        raw = self.stream.readline(32*2**20+1)
        need(len(raw) <= 32*2**20 and raw.endswith(b'\n'), 'Missing/oversize/non-LF JSONL record: '+self.path.name)
        # Exact canonical bytes also discriminate bool/int/float, keys, NULLs and array order.
        need(raw == (canonical(value)+'\n').encode(), 'Whole typed record mismatch: '+self.path.name+' row '+str(self.rows))
        self.rows += 1
        self.check()
    def end(self, count):
        need(self.rows == count and self.stream.read(1) == b'', 'JSONL rowcount/EOF: '+self.path.name)
    def close(self):
        self.stream.close()


def controls(C0, P, R, popular, source):
    B = list(dict.fromkeys(P+R))
    tail = [item for rank,item in sorted(popular) if item not in set(B)]
    need(set(tail) == C0-set(B) and len(tail) == len(set(tail)), 'Independent control tail identity')
    k = min(len(tail), len(source['count']), len(source['cosine']))
    arms = dict(B=B, T=tail, k=k, matched_popular=B+tail[:k],
                matched_count=B+source['count'][:k], matched_cosine=B+source['cosine'][:k])
    need(all(len(arms[n]) == len(B)+k == len(set(arms[n])) for n in ('matched_popular','matched_count','matched_cosine')), 'Equal-cardinality controls')
    return arms


def literal_checks():
    P, C0 = list(range(1,181)), set(range(1,202))
    popular = list(enumerate(range(1,201),1))
    expected = dict(B=P+[201], T=list(range(181,201)), k=2,
                    matched_popular=P+[201,181,182], matched_count=P+[201,400,401], matched_cosine=P+[201,402,403])
    need(controls(C0,P,[201],popular,dict(count=[400,401],cosine=[402,403])) == expected, 'Literal matched tails')
    empty = controls(C0,P,[201],popular,dict(count=[],cosine=[402,403]))
    need(empty['k'] == 0 and all(empty[n] == P+[201] for n in ('matched_popular','matched_count','matched_cosine')), 'Literal k0 retention')
    unequal = controls(C0,P,[201],popular,dict(count=[400,401],cosine=[402]))
    need(unequal['k'] == 1 and unequal['matched_count'][-1] == 400 and unequal['matched_cosine'][-1] == 402, 'Literal common minimum')
    need((3*3)/(3+10)+(3*3)/(3+10) == 18/13, 'Literal two-seed count')
    need(math.isclose((3*3)/(3+10)/3+(3*3)/(3+10)/3, 6/13, rel_tol=0, abs_tol=math.ulp(6/13)), 'Literal mathematical cosine within one binary64 ULP')
    return dict(matched_tail_lengths=[len(expected[n]) for n in ('matched_popular','matched_count','matched_cosine')],
                matched_tails=[[181,182],[400,401],[402,403]], retained_k0=True, common_k=1,
                multiseed_count=18/13, multiseed_cosine=6/13)


def worker():
    start, cpu = time.monotonic(), time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU, (590,591))
    resource.setrlimit(resource.RLIMIT_CORE, (0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8*2**30,8*2**30))
    def expired(signum, frame):
        raise TimeoutError('Independent SEALED6000 worker deadline')
    signal.signal(signal.SIGALRM,expired)
    signal.signal(signal.SIGXCPU,expired)
    signal.alarm(880)
    con, error, streams = None, None, []
    result = dict(status='INCOMPLETE', attempts=1, retry=False, no_producer_or_core_import=True,
                  fits=0,model_loads=0,predictions=0,Y_access=False)
    inputs = {}
    def check():
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        need(time.monotonic()-start < 879 and time.process_time()-cpu < 588, 'Worker time cap')
        need(rss < 6*2**30, 'Cooperative worker RSS cap')
        # Engine spill is separately capped by DuckDB; result/log output is64MiB inclusive.
        need(sum(p.stat().st_size for p in OUT.iterdir() if p.is_file()) < 64*2**20-2*2**20, 'Output reserve cap')
    def query(sql, params=()):
        check(); rows=con.execute(sql,params).fetchall(); check(); return rows
    def sql_stream(sql,params=()):
        check(); con.execute(sql,params)
        while True:
            check(); rows=con.fetchmany(8192)
            if not rows: break
            yield from rows
    def pin(path,expected=None):
        row=file_ref(path,check)
        need(expected is None or witness(row)==witness(expected), 'Input byte pin: '+str(path))
        key=str(Path(path).resolve())
        need(key not in inputs or inputs[key]==row, 'Repeated input differs')
        inputs[key]=row
        return row
    try:
        need(OUT.is_dir() and load(OUT/'CONSUMED.json') == dict(attempts=1,retry=False,authority='Root separate admission required after non-author SOURCE review; no producer/core imports'), 'Owner once marker')
        pin(__file__)
        pin(PROPOSAL/'literal-protocol.json')
        request=load(REQUEST)
        pin(REQUEST,dict(bytes=2528,sha256='420aeb4dd325694452d58e34f804760f15df3cd1d7a8d2ce3441e1908e6d356f'))
        bridge=load(request['bridge_ref']['path']); pin(request['bridge_ref']['path'],request['bridge_ref'])
        terminal=load(TERMINAL); pin(TERMINAL)
        report=load(PROD/'seal.json'); pin(PROD/'seal.json',dict(bytes=28055,sha256='0985b316ebdde6b7b4f676868131bb7c07e9004cd844a18d75fe115c66900d40'))
        receipt=load(JOB/'receipt.json'); pin(JOB/'receipt.json',terminal['outer_receipt'])
        need(terminal['exit_code']==0 and terminal['reaped'] is True and terminal['retry'] is False, 'Root original terminal facts')
        need(receipt['returncode']==0 and receipt['reaped'] is True and receipt['primary_error'] is None and receipt['cleanup_errors']==[], 'Producer receipt closure')
        need(report['status']=='SEALED6000_UNREVIEWED_NO_OUTCOMES' and report['fits']==report['model_predictions']==0 and report['secondary']==[], 'Reported outcome-free seal')
        need(report['history_select_reserved']==1 and report['history_select_completion']=='complete', 'Reported full prior-pairs scan')
        need(report['descriptor_source_row_visits_upper']==4*request['source_rows'],'Reported3graph plus1history complete-scan ledger')
        for name,expected in receipt['streams'].items():
            need(name in ('stdout.log','stderr.log'), 'Only expected original streams')
            pin(JOB/name,expected)
        caller=Path('/private/tmp/tlab-hyp061-q6000-seal-proposal-v1/seal6000.py')
        core=Path('/private/tmp/tlab-hyp061-discovery-proposal-v2/discovery.py')
        pin(caller,dict(bytes=13792,sha256='2d43f10d66241a7fe9bd53731757649ef71c997af1a474860d4e25544d636383'))
        pin(core,dict(bytes=21921,sha256='a903a30f06b83314eb1f83dcb6693237d59f814d09a9e8956bb35f4345e45d4b'))
        need(request['db']==bridge['db'] and request['queries']==bridge['queries'] and request['candidates']==bridge['candidates'], 'Same accepted DB/Q/C bridge')
        need(request['db']['sha256']=='8391078ff9747434b8683d2ea81302310791b6f03588fc398b9298ef7d765bfd', 'Accepted same DB')
        for key in ('accepted_Q100','accepted_current15','original_semantic_bridge'):
            pin(bridge[key]['path'],bridge[key])
        db=Path(request['db']['path']); wal=Path(str(db)+'.wal')
        need(not wal.exists(), 'No initial source WAL')
        pin(db,request['db'])
        for key in ('queries','candidates'):
            need(len(request[key])==3, 'Exactly three historical shards')
            for ref in request[key]: pin(ref['path'],ref)
        refdoc=load(request['q100_reference']['path']); pin(request['q100_reference']['path'],request['q100_reference'])
        need(type(refdoc)==dict and set(refdoc)=={'version','records'} and refdoc['version']==1 and len(refdoc['records'])==100, '100 accepted reference descriptors')
        for qid,ref in refdoc['records'].items(): pin(ref['path'],ref) # Opaque old JSON bytes only; never load/call an old artifact.
        intended=[caller,core,REQUEST,db,Path(request['bridge_ref']['path']),Path(request['q100_reference']['path'])]
        intended += [Path(r['path']) for k in ('queries','candidates') for r in request[k]]
        intended += [Path(r['path']) for r in refdoc['records'].values()]
        bound={str(Path(r['path']).resolve()):witness(r) for r in report['bound_files']}
        need(len(report['bound_files'])==len(bound)==112 and set(bound)=={str(p.resolve()) for p in intended}, 'Exact112 outcome-free input witnesses')
        for key,expected in bound.items(): need(witness(inputs[key])==expected,'Producer input binding')
        need(report['core']==dict(path='/tmp/tlab-hyp061-discovery-proposal-v2/discovery.py',bytes=21921,sha256='a903a30f06b83314eb1f83dcb6693237d59f814d09a9e8956bb35f4345e45d4b'), 'Reported unchanged core')
        names={'Q6000.jsonl','candidates.jsonl','prior-pairs.jsonl'}
        need(set(report['outputs'])==names and {p.name for p in PROD.iterdir()}==names|{'seal.json'} and not any(p.is_symlink() for p in PROD.iterdir()), 'Exact four producer files')
        for name in sorted(names): pin(PROD/name,report['outputs'][name])
        import duckdb
        need(duckdb.__version__=='1.5.6','Locked existing DuckDB')
        con=duckdb.connect(':memory:',config={'threads':'2','memory_limit':'2GB','max_temp_directory_size':str(8*2**30)+'B','temp_directory':str(OUT/'spill')})
        allowed=[str(db),str(wal)]+[r['path'] for k in ('queries','candidates') for r in request[k]]
        con.execute('SET allowed_paths = ['+','.join("'"+p.replace("'","''")+"'" for p in allowed)+']')
        con.execute('SET enable_external_access=false'); con.execute('SET lock_configuration=true')
        result['literal_oracles']=literal_checks()
        qp,cp=([r['path'] for r in request[k]] for k in ('queries','candidates'))
        need([tuple(r[:2]) for r in query('DESCRIBE SELECT query_id,user_id,anchor FROM read_parquet(?)',[qp])]==[('query_id','VARCHAR'),('user_id','BIGINT'),('anchor','TIMESTAMP')], 'Q typed3')
        qrows=query('SELECT query_id,user_id,anchor FROM read_parquet(?)',[qp])
        need(len(qrows)==len({r[0] for r in qrows})==len({(r[1],r[2]) for r in qrows})==6000,'Complete unique6000')
        need(collections.Counter(r[2] for r in qrows)==collections.Counter({a:2000 for a in ANCHORS}),'2000 per day')
        for qid,user,anchor in qrows:
            need(type(user)is int and -(2**63)<=user<2**63,'Exact signed Q user')
            need(qid==hashlib.sha256(('query|2026|'+anchor.strftime('%Y-%m-%dT%H:%M:%SZ')+'|'+str(user)).encode('ascii')).hexdigest(),'Canonical Q identity')
        chosen=sorted(qrows,key=lambda r:(hashlib.sha256(PREFIX+r[0].encode('ascii')).digest(),r[0].encode('ascii')))
        ranks={r[0]:n for n,r in enumerate(chosen)}
        need(set(refdoc['records'])=={r[0] for r in chosen[:100]},'Accepted100 exact prefix')
        prefix=[[q,u,a.isoformat()+'Z'] for q,u,a in chosen[:100]]
        need(hashlib.sha256(canonical(prefix).encode()).hexdigest()==bridge['Q100_identity'],'Independent accepted prefix identity')
        qstream=ExactJSONL(PROD/'Q6000.jsonl',check); streams.append(qstream)
        for n,(q,u,a) in enumerate(chosen): qstream.expect(dict(global_rank=n,query_id=q,user_id=u,anchor=a.isoformat()+'Z'))
        qstream.end(6000)
        con.execute('CREATE TEMP TABLE fixed_q(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,global_rank BIGINT)')
        con.executemany('INSERT INTO fixed_q VALUES(?,?,?,?)',[(q,u,a,n) for n,(q,u,a) in enumerate(chosen)])
        fields='query_id,product_id,from_popular,from_recent,popular_source_rank,recent_source_rank,last_user_event_time'
        need([tuple(r[:2]) for r in query('DESCRIBE SELECT '+fields+' FROM read_parquet(?)',[cp])]==[('query_id','VARCHAR'),('product_id','BIGINT'),('from_popular','BOOLEAN'),('from_recent','BOOLEAN'),('popular_source_rank','BIGINT'),('recent_source_rank','BIGINT'),('last_user_event_time','TIMESTAMP')], 'C typed7')
        need(query('SELECT count(*) FROM read_parquet(?)',[cp])[0][0]<=1320000,'Full original C bound')
        need(query('SELECT count(*) FROM read_parquet(?) c ANTI JOIN fixed_q q USING(query_id)',[cp])[0][0]==0,'No foreign C query')
        need(not wal.exists(),'No WAL immediately before READ_ONLY ATTACH')
        con.execute("ATTACH '"+str(db).replace("'","''")+"' AS src (READ_ONLY)")
        need([tuple(r[:2]) for r in query('DESCRIBE src.main.events')]==[('event_time','TIMESTAMP'),('event_type','VARCHAR'),('product_id','BIGINT'),('category_id','BIGINT'),('category_code','VARCHAR'),('brand','VARCHAR'),('price','DECIMAL(12,2)'),('user_id','BIGINT'),('user_session','VARCHAR')],'Literal typed9 source')
        need(query('SELECT count(*) FROM src.main.events')[0][0]==request['source_rows'],'Full source count')
        prior=ExactJSONL(PROD/'prior-pairs.jsonl',check); streams.append(prior)
        prior_sets=collections.defaultdict(set); previous=None
        for rank,qid,item in sql_stream('SELECT q.global_rank,q.query_id,e.product_id FROM fixed_q q JOIN src.main.events e ON e.user_id=q.user_id WHERE e.event_time>=? AND e.event_time<q.anchor AND e.product_id IS NOT NULL GROUP BY q.global_rank,q.query_id,e.product_id ORDER BY q.global_rank,e.product_id',[dt.datetime(2019,10,1)]):
            need(type(item)is int and -(2**63)<=item<2**63 and (previous is None or previous<(rank,item)),'Exact distinct prior-pair order')
            previous=(rank,item); prior.expect(dict(query_id=qid,product_id=item)); prior_sets[qid].add(item)
        prior.end(report['prior_pairs_written'])
        need(prior.rows==report['outputs']['prior-pairs.jsonl']['rows'],'Prior stream rows footer')
        candidates=ExactJSONL(PROD/'candidates.jsonl',check); streams.append(candidates)
        near=dict(exact_boundary_ties=0,nonzero_boundary_gaps_le4ulp=0,exact_adjacent_ties=0,min_positive_boundary_gap_ulps=None,minimum_positive_adjacent_gap_ulps=None,diagnostic_fsum_changed_values=0,diagnostic_fsum_top20_order_changes=0,diagnostic_fsum_top20_set_changes=0)
        graphs,checks,global_visits,matched100=[],[],0,0
        for anchor in ANCHORS:
            byq=collections.defaultdict(list)
            for row in query('SELECT c.'+fields.replace(',',',c.')+' FROM read_parquet(?) c JOIN fixed_q q USING(query_id) WHERE q.anchor=?',[cp,anchor]): byq[row[0]].append(row)
            originals,seed_rows={},[]
            for qid,user,a in (r for r in chosen if r[2]==anchor):
                members,pp,rr=set(),[],[]
                for _,item,popular,recent,pr,rank,timestamp in byq[qid]:
                    need(type(item)is int and -(2**63)<=item<2**63 and item not in members,'Exact distinct C key')
                    need(type(popular)is bool and type(recent)is bool and (popular or recent),'C source flags')
                    need((type(pr)is int and 1<=pr<=200) if popular else pr is None,'P rank/flag')
                    need((type(rank)is int and 1<=rank<=20) if recent else rank is None,'R rank/flag')
                    members.add(item)
                    if popular: pp.append((pr,item))
                    if recent:
                        need(type(timestamp)is dt.datetime and anchor-dt.timedelta(days=7)<=timestamp<anchor,'Strict R7d timestamp')
                        rr.append((rank,item,timestamp))
                    else: need(timestamp is None,'Absent R timestamp')
                pp.sort();rr.sort()
                need([n for n,i in pp]==list(range(1,len(pp)+1)) and len(pp)<=200,'Complete P200 prefix')
                need([n for n,i,t in rr]==list(range(1,len(rr)+1)) and len(rr)<=20,'Complete R20 prefix')
                need(rr==sorted(rr,key=lambda r:(anchor-r[2],r[1])),'R timestamp desc exact-ID asc')
                P=[i for n,i in pp if n<=180];R=[i for n,i,t in rr]
                originals[qid]=(members,P,R,pp)
                for position,h in enumerate(R[:4]):seed_rows.append((qid,user,anchor,h,position))
            del byq
            con.execute("CREATE OR REPLACE TEMP TABLE raw_view AS SELECT DISTINCT user_id,product_id FROM src.main.events WHERE event_type='view' AND event_time>=? AND event_time<? AND user_id IS NOT NULL AND product_id IS NOT NULL",[anchor-dt.timedelta(days=7),anchor])
            con.execute('CREATE OR REPLACE TEMP TABLE user_degree AS SELECT user_id,count(*) n FROM raw_view GROUP BY user_id')
            con.execute('CREATE OR REPLACE TEMP TABLE graph_edges AS SELECT r.* FROM raw_view r JOIN user_degree d USING(user_id) WHERE d.n<=32')
            con.execute('CREATE OR REPLACE TEMP TABLE item_degree AS SELECT product_id,count(*) n FROM graph_edges GROUP BY product_id')
            users,excluded,maximum,admitted_users=query('SELECT count(*),count(*) FILTER(WHERE n>32),max(n),count(*) FILTER(WHERE n<=32) FROM user_degree')[0]
            raw_edges=query('SELECT count(*) FROM raw_view')[0][0];admitted_edges=query('SELECT count(*) FROM graph_edges')[0][0]
            need(admitted_edges<=10000000,'Admitted graph cap')
            stat=dict(raw_users=users,raw_edges=raw_edges,excluded_profiles=excluded,max_raw_degree=maximum,admitted_users=admitted_users,admitted_edges=admitted_edges)
            digest=hashlib.sha256();active_user=None;items=[];seen_users=seen_edges=0;previous=None
            for user,item in sql_stream('SELECT user_id,product_id FROM graph_edges ORDER BY user_id,product_id'):
                need(previous is None or previous<(user,item),'Unique full graph stream');previous=(user,item)
                if active_user is not None and user!=active_user:
                    need(1<=len(items)<=32,'Complete whole admitted profile');digest.update((canonical([active_user,items])+'\n').encode());seen_users+=1;items=[]
                active_user=user;items.append(item);seen_edges+=1
            if active_user is not None:
                need(1<=len(items)<=32,'Last whole admitted profile');digest.update((canonical([active_user,items])+'\n').encode());seen_users+=1
            need((seen_users,seen_edges)==(admitted_users,admitted_edges),'Full graph identity counts')
            original_graph=next(g for g in report['graph_builds'] if g['anchor']==anchor.isoformat()+'Z')
            need(original_graph['complete'] is True and stat==original_graph['statistics'] and digest.hexdigest()==original_graph['identity'],'Independent graph identity/statistics')
            graphs.append(dict(anchor=anchor.isoformat()+'Z',identity=digest.hexdigest(),statistics=stat))
            heavy={q for q,n in query('SELECT q.query_id,d.n FROM fixed_q q JOIN user_degree d USING(user_id) WHERE q.anchor=? AND d.n>32',[anchor])}
            con.execute('CREATE OR REPLACE TEMP TABLE seeds(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,h BIGINT,ordinal INTEGER)')
            if seed_rows:con.executemany('INSERT INTO seeds VALUES(?,?,?,?,?)',seed_rows)
            con.execute('CREATE OR REPLACE TEMP TABLE seed_norms AS SELECT s.*,coalesce(d.n,0)-CASE WHEN own.user_id IS NULL THEN 0 ELSE 1 END dh FROM seeds s LEFT JOIN item_degree d ON d.product_id=s.h LEFT JOIN graph_edges own ON own.user_id=s.user_id AND own.product_id=s.h')
            nd={(q,p):degree for q,p,h,degree in query('SELECT query_id,ordinal,h,dh FROM seed_norms ORDER BY query_id,ordinal')}
            con.execute('CREATE OR REPLACE TEMP TABLE admitted_seeds AS SELECT * FROM seed_norms WHERE dh BETWEEN 1 AND 512')
            visits=query('SELECT a.query_id,a.ordinal,count(p.user_id),coalesce(sum(u.n),0) FROM admitted_seeds a LEFT JOIN graph_edges p ON p.product_id=a.h AND p.user_id<>a.user_id LEFT JOIN user_degree u ON u.user_id=p.user_id GROUP BY a.query_id,a.ordinal ORDER BY a.query_id,a.ordinal')
            visit={(q,p):n for q,p,audience,n in visits}
            need(all(audience==nd[q,p] for q,p,audience,n in visits),'Complete query-self-deleted audience')
            con.execute('CREATE OR REPLACE TEMP TABLE co_support AS SELECT a.query_id,a.ordinal,a.h,j.product_id,count(DISTINCT p.user_id) c FROM admitted_seeds a JOIN graph_edges p ON p.product_id=a.h AND p.user_id<>a.user_id JOIN graph_edges j ON j.user_id=p.user_id AND j.product_id<>a.h GROUP BY a.query_id,a.ordinal,a.h,j.product_id')
            co=iter(sql_stream('SELECT q.global_rank,c.ordinal,c.h,c.product_id,c.c,a.dh,d.n-CASE WHEN own.user_id IS NULL THEN 0 ELSE 1 END dj FROM co_support c JOIN fixed_q q USING(query_id) JOIN admitted_seeds a ON a.query_id=c.query_id AND a.ordinal=c.ordinal JOIN item_degree d ON d.product_id=c.product_id LEFT JOIN graph_edges own ON own.user_id=a.user_id AND own.product_id=c.product_id ORDER BY q.global_rank,c.ordinal,c.product_id'))
            pending=next(co,None)
            for qid,user,a in (r for r in chosen if r[2]==anchor):
                rank=ranks[qid];C0,P,R,pp=originals[qid];support_rows=[]
                while pending is not None and pending[0]==rank:
                    support_rows.append(pending[1:]);pending=next(co,None)
                need(pending is None or pending[0]>rank,'No missing/foreign query in support stream')
                expected=expected_core(qid,C0,P,R,support_rows,nd,visit,near)
                control=controls(C0,P,R,pp,expected['source'])
                body=dict(global_rank=rank,query_id=qid,user_id=user,anchor=anchor.isoformat()+'Z',C0=sorted(C0),P180=P,R20=R,core_result=expected,controls=control,prior_pair_count=len(prior_sets[qid]))
                candidates.expect(body)
                if qid in refdoc['records']:
                    raw=(canonical(expected)+'\n').encode();need(dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())==witness(refdoc['records'][qid]),'Entire canonical accepted100 core parity');matched100+=1
                domain={r['product_id'] for r in expected['domain']};global_visits+=expected['profile_edge_visits']
                checks.append(dict(query_id=qid,global_rank=rank,anchor=body['anchor'],whole_record_sha256=hashlib.sha256((canonical(body)+'\n').encode()).hexdigest(),domain_size=len(domain),count_size=len(expected['source']['count']),cosine_size=len(expected['source']['cosine']),count_C_size=len(expected['C_count']),cosine_C_size=len(expected['C_cos']),distinct_sets=expected['distinct_top20_sets'],k=control['k'],B_size=len(control['B']),prior_pairs=len(prior_sets[qid]),prior_outside_C0=len(prior_sets[qid]-C0),prior_outside_D=len(prior_sets[qid]-domain),raw_query_degree_over32=qid in heavy,profile_edge_visits=expected['profile_edge_visits']))
                if len(checks)%500==0:print('verified candidates',len(checks),flush=True)
            need(pending is None,'Support stream exhausted after entire anchor')
            for name in ('co_support','admitted_seeds','seed_norms','seeds','item_degree','graph_edges','user_degree','raw_view'):con.execute('DROP TABLE '+name)
            del originals,seed_rows,heavy
            check()
        candidates.end(6000)
        need(report['queries_written']==report['outputs']['Q6000.jsonl']['rows']==report['outputs']['candidates.jsonl']['rows']==len(checks)==6000,'Exact complete6000 rowcounts')
        need(len(graphs)==len(report['graph_builds'])==3 and matched100==report['q100_matches']==100,'3 full graphs and100 full reference matches')
        need(global_visits==report['shared_profile_edge_visits'] and global_visits<=393216000,'Complete6000 profile visit ledger')
        need({r['query_id'] for r in checks}==set(ranks),'All fixed queries retained including empty sources/history')
        for stream in streams:stream.close()
        streams=[];con.close();con=None
        need(not wal.exists(),'No source WAL after close')
        for before in inputs.values():need(file_ref(before['path'],check)==before,'Final input bytes/modes changed')
        result.update(status='PASS_FINITE_SEALED6000_CORRECTNESS',inputs=list(inputs.values()),all_input_final_hashes_equal=True,source_WAL_absent=True,
                      global_Q=6000,decoded_Q_files=3,decoded_C_files=3,independently_rebuilt_graphs=graphs,per_query_checks=checks,
                      all6000_entire_records_canonical_equal=True,all3_JSONL_streams_entire_typed_equal=True,prior_pairs=prior.rows,matched100=matched100,
                      empty_source_queries=sum(r['count_size']==0 for r in checks),empty_prior_queries=sum(r['prior_pairs']==0 for r in checks),
                      k0_queries=sum(r['k']==0 for r in checks),profile_edge_visits=global_visits,floating_analysis=near,literal_oracles=literal_checks())
    except BaseException as caught:
        error=caught;result['failure']=dict(type=type(caught).__name__,message=str(caught));traceback.print_exc()
    finally:
        secondary=[]
        for stream in streams:
            try:stream.close()
            except BaseException as caught:secondary.append(dict(stage='stream close',type=type(caught).__name__,message=str(caught)))
        if con is not None:
            try:con.close()
            except BaseException as caught:secondary.append(dict(stage='DuckDB close',type=type(caught).__name__,message=str(caught)))
        if secondary:
            result['secondary']=secondary;result['status']='INCOMPLETE';error=error if error is not None else RuntimeError('Cleanup failed')
        result.setdefault('inputs',list(inputs.values()))
        result.setdefault('all_input_final_hashes_equal',False)
        result['resource_prefix']=dict(cpu_seconds=time.process_time()-cpu,wall_seconds=time.monotonic()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),DuckDB_threads=2,DuckDB_memory='2GB',spill_limit_bytes=8*2**30,worker_CPU_soft=590,worker_CPU_hard=591,worker_alarm_seconds=880)
        write(OUT/'oracle-results.json',result)
        signal.alarm(0)
    return 0 if error is None else 1


def supervise():
    started,cpu=time.monotonic(),time.process_time()
    process,primary,stdout,stderr=None,None,None,None
    status=dict(status='INCOMPLETE',attempts=1,retry=False,child_reaped=False,
                caps=dict(inclusive_CPU=600,inclusive_wall=900,RSS_cooperative=6*2**30,engine_memory='2GB',threads=2,spill=8*2**30,outputs=64*2**20))
    try:
        need(sys.argv==[__file__],'Exact ordinary owner invocation')
        need(not OUT.exists(),'Fresh once-only verifier runtime')
        OUT.mkdir(mode=0o700)
        write(OUT/'CONSUMED.json',dict(attempts=1,retry=False,authority='Root separate admission required after non-author SOURCE review; no producer/core imports'))
        stdout=(OUT/'stdout.log').open('xb');stderr=(OUT/'stderr.log').open('xb')
        process=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--worker'],cwd=OUT,stdout=stdout,stderr=stderr,start_new_session=True)
        # Applied after spawn, so it does not constrain the child to the owner's7CPU hard limit.
        resource.setrlimit(resource.RLIMIT_CPU,(7,7));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_FSIZE,(64*2**20,64*2**20))
        def stop(signum,frame):raise TimeoutError('Independent owner deadline')
        signal.signal(signal.SIGALRM,stop);signal.signal(signal.SIGXCPU,stop);signal.alarm(895)
        while process.poll() is None:
            need(time.monotonic()-started<885,'Owner wait deadline')
            need(time.process_time()-cpu<5,'Owner cooperative CPU reserve')
            need(sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())<64*2**20-2*2**20,'Owner output reserve cap')
            time.sleep(.2)
        code=process.wait();scale=1 if sys.platform=='darwin' else 1024
        maximum=(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss+resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)*scale
        status.update(child_exit=code,child_reaped=True,sum_of_process_peak_RSS_bytes=maximum,RSS_scope='Single child cooperative6GiB plus engine2GB; sum of per-process kernel highwaters afterreap, not hard aggregateRSS')
        need(maximum<6*2**30,'Observed sum of process RSS peaks')
        need(code==0,'Verifier child nonzero')
        result=load(OUT/'oracle-results.json');need(result['status']=='PASS_FINITE_SEALED6000_CORRECTNESS','Verifier oracle incomplete')
        status.update(status='PASS_CLOSED_PENDING_ROOT_OUTER_TERMINAL',result=file_ref(OUT/'oracle-results.json'))
    except BaseException as error:
        primary=error;status['failure']=dict(type=type(error).__name__,message=str(error))
    finally:
        secondary=[]
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
            except BaseException as error:secondary.append(dict(stage='terminate/reap',type=type(error).__name__,message=str(error)))
        if process is not None:status.update(child_exit=process.returncode,child_reaped=process.returncode is not None)
        for label,stream in (('stdout',stdout),('stderr',stderr)):
            if stream is not None:
                try:stream.close()
                except BaseException as error:secondary.append(dict(stage=label+' close',type=type(error).__name__,message=str(error)))
        if secondary:status['secondary']=secondary;primary=primary if primary is not None else RuntimeError('Owner cleanup failed')
        child=resource.getrusage(resource.RUSAGE_CHILDREN)
        status['resource_prefix']=dict(wall_seconds=time.monotonic()-started,owner_CPU_seconds=time.process_time()-cpu,children_CPU_seconds=child.ru_utime+child.ru_stime,child_CPU_scope='Exactly one independent verifier child; no ps/proc census')
        status['resource_prefix']['combined_CPU_seconds']=status['resource_prefix']['owner_CPU_seconds']+status['resource_prefix']['children_CPU_seconds']
        status['sample_scope']='After child reap/cleanup and before final receipt/print: CPU/wall PREFIX, not exact process-tail total; Root original-tool terminal required; hard CPU 7+591<600 and wall owner895<900 reserve.'
        if status['resource_prefix']['combined_CPU_seconds']>=598 or status['resource_prefix']['wall_seconds']>=895:
            primary=primary if primary is not None else RuntimeError('Inclusive sampled reserve cap')
        if primary is not None:status['status']='INCOMPLETE'
        try:
            if OUT.exists():
                need(sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())<64*2**20-2*2**20,'Final output reserve')
                status['source']=file_ref(__file__)
                write(OUT/'actual-receipt.json',status)
                print(json.dumps(dict(status=status['status'],child_reaped=status['child_reaped'],receipt=file_ref(OUT/'actual-receipt.json')),sort_keys=True))
        finally:signal.alarm(0)
    return 0 if primary is None else 1


if __name__=='__main__':
    if sys.argv[1:]==['--worker']:
        sys.exit(worker())
    sys.exit(supervise())
