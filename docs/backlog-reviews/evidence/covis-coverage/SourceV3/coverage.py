"""Independent HYP061 coverage consumer; SOURCE prototype, real inputs unbound."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import resource
import sys
import time
import types

ESTIMANDS_SHA='3aa8e4b2d49e275de399e27e5190437d0a9818977ebcb5de2a88f3954fac6a49'
ESTIMANDS_PATH=Path(__file__).with_name('estimands.py')
_source=ESTIMANDS_PATH.read_bytes()
if len(_source)!=7254 or hashlib.sha256(_source).hexdigest()!=ESTIMANDS_SHA:
    raise ValueError('Frozen independent estimands source mismatch')
estimands=types.ModuleType('_hyp061_estimands');estimands.__file__=str(ESTIMANDS_PATH)
exec(compile(_source,str(ESTIMANDS_PATH),'exec'),estimands.__dict__)
del _source

ANALYSIS_SHA='b8896d7f7ee7a12593cdfdfe4f7f3fc4a58bddbd9e3f7312b96de895a104565f'
ANCHORS=tuple(f'2019-10-{d:02d}T00:00:00Z' for d in (8,9,10))
PREFIX=b'tlab-hyp061-q100-v1\0'
LABELS=[('query_id','VARCHAR'),('product_id','BIGINT'),('first_purchase_time','TIMESTAMP'),('raw_purchase_rows','BIGINT'),('same_second_purchase','BOOLEAN'),('catalog_seen_before','BOOLEAN'),('pair_seen_before','BOOLEAN')]
MAX_LIMITS=dict(cpu_seconds=120,wall_seconds=180,rss_bytes=2**30,output_bytes=16*2**20)
CONTRASTS={'cos-C0':('cos','C0'),'count-C0':('count','C0'),'cos-count':('cos','count'),'matched_cos-matched_popular':('matched_cos','matched_popular')}
RNG_SPEC='stdlib random.Random(61061).randrange(M); sorted signed64 user frame; shared2000 draws; multiplicity; type7'


def need(ok,message):
    if not ok: raise ValueError(message)


def canon(body):
    return json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False)


def parse(raw):
    def pairs(rows):
        body=dict(rows); need(len(body)==len(rows),'Duplicate JSON key'); return body
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def integer(value):
    need(type(value) is int and -2**63<=value<2**63,'Exact signed64 ID');return value


def ids(values,cap=220):
    need(type(values) is list and len(values)<=cap,'Bound ID list')
    for x in values: integer(x)
    need(len(set(values))==len(values),'Duplicate item');return values


def union(*parts):
    return list(dict.fromkeys(x for part in parts for x in part))


def note(primary,text):
    try: BaseException.add_note(primary,text)
    except BaseException: pass


def describe(error):
    try:return dict(type=type(error).__name__,message=str(error)[:2048])
    except BaseException:return dict(type=type(error).__name__,message='<unprintable>')


class Guard:
    def __init__(self,output,limits):
        need(type(limits) is dict and set(limits)==set(MAX_LIMITS) and all(type(v) is int and 0<v<=MAX_LIMITS[k] for k,v in limits.items()),'Bound consumer limits')
        self.output,self.limits,self.wall,self.cpu=output,limits,time.monotonic(),time.process_time()
    def telemetry(self):
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return dict(cpu_seconds=time.process_time()-self.cpu,wall_seconds=time.monotonic()-self.wall,rss_bytes=int(rss if sys.platform=='darwin' else rss*1024),physical_io='UNKNOWN',scope='cooperative self process; not hard aggregate containment')
    def check(self,extra=0):
        t=self.telemetry();need(all(t[k]<self.limits[k] for k in ('cpu_seconds','wall_seconds','rss_bytes')),'Consumer resource limit')
        need(sum(p.stat().st_size for p in self.output.iterdir() if p.is_file())+extra<=self.limits['output_bytes']-2**20,'Output limit;1MiB receipt reserve')


def file_ref(path,check=lambda extra=0:None):
    digest=hashlib.sha256();n=0;check()
    with Path(path).open('rb') as stream:
        while True:
            check();raw=stream.read(2**20)
            if not raw: break
            n+=len(raw);digest.update(raw)
    return dict(bytes=n,sha256=digest.hexdigest())


def write_json(path,body,check=lambda extra=0:None):
    raw=(canon(body)+'\n').encode();check(len(raw))
    with Path(path).open('xb') as stream: need(stream.write(raw)==len(raw),'Short JSON write')


def jsonl(path,check):
    with Path(path).open('rb') as stream:
        while True:
            check();raw=stream.readline(64*2**20+1)
            if not raw: break
            need(len(raw)<=64*2**20 and raw.endswith(b'\n'),'Bound complete JSONL record')
            yield parse(raw)


def load_sealed(directory,manifest,check=lambda extra=0:None):
    need(manifest.get('status')=='SEALED6000_UNREVIEWED_NO_OUTCOMES' and manifest.get('queries_written')==6000 and manifest.get('q100_matches')==100 and
         manifest.get('prior_pairs_written')==44172 and manifest.get('history_select_completion')=='complete','Complete accepted seal metadata')
    need(type(manifest.get('graph_builds')) is list and len(manifest['graph_builds'])==3 and
         {g.get('anchor') for g in manifest['graph_builds']}==set(ANCHORS) and all(g.get('complete') is True for g in manifest['graph_builds']), 'Complete three graph ledger')
    need(set(manifest['outputs'])=={'Q6000.jsonl','candidates.jsonl','prior-pairs.jsonl'},'Exact three streams')
    queries=[];seen=set()
    for rank,q in enumerate(jsonl(directory/'Q6000.jsonl',check)):
        need(set(q)=={'global_rank','query_id','user_id','anchor'} and type(q['global_rank']) is int and q['global_rank']==rank and q['anchor'] in ANCHORS,'Q schema/rank')
        u=integer(q['user_id']);qid=q['query_id']
        need(type(qid) is str and re.fullmatch('[0-9a-f]{64}',qid) and qid==hashlib.sha256(f"query|2026|{q['anchor']}|{u}".encode('ascii')).hexdigest(),'Canonical Q')
        need((u,q['anchor']) not in seen,'Duplicate user-day');seen.add((u,q['anchor']));queries.append(q)
    need(len(queries)==6000 and Counter(q['anchor'] for q in queries)==Counter({a:2000 for a in ANCHORS}),'Fixed6000 cohort')
    need(queries==sorted(queries,key=lambda q:(hashlib.sha256(PREFIX+q['query_id'].encode('ascii')).digest(),q['query_id'].encode('ascii'))),'Global Q order')
    by_q={q['query_id']:q for q in queries};records={qid:dict(q,targets=set(),prior=set()) for qid,q in by_q.items()}
    previous=None;n=0
    for pair in jsonl(directory/'prior-pairs.jsonl',check):
        need(set(pair)=={'query_id','product_id'} and pair['query_id'] in by_q,'Prior schema/foreign Q');item=integer(pair['product_id'])
        key=(by_q[pair['query_id']]['global_rank'],item);need(previous is None or previous<key,'Prior order/duplicate');previous=key
        records[pair['query_id']]['prior'].add(item);n+=1
    need(n==44172 and n==manifest['outputs']['prior-pairs.jsonl']['rows'],'Complete prior pair count')
    expected=sorted(queries,key=lambda q:(q['anchor'],q['global_rank']));visits=0;count=0
    for count,row in enumerate(jsonl(directory/'candidates.jsonl',check),1):
        need(count<=6000,'Candidate row cap');q=expected[count-1]
        need(set(row)=={'global_rank','query_id','user_id','anchor','C0','P180','R20','core_result','controls','prior_pair_count'} and type(row['global_rank']) is int and type(row['user_id']) is int and all(row[k]==q[k] for k in q),'Candidate Q schema/order')
        C0=ids(row['C0']);need(C0==sorted(C0),'Sorted C0');p=ids(row['P180'],180);r=ids(row['R20'],20)
        need(set(p+r)<=set(C0),'Original source membership');result=row['core_result'];ctr=row['controls']
        need(set(result)=={'seeds','source','ranked_source','domain','rejection','profile_edge_visits','distinct_top20_sets','query_id','C_count','C_cos'} and result['query_id']==q['query_id'],'Core result schema')
        need(ids(result['seeds'],4)==r[:4] and set(result['source'])==set(result['ranked_source'])=={'count','cosine'},'Frozen seeds/source schema')
        need(type(result['profile_edge_visits']) is int and 0<=result['profile_edge_visits']<=65536,'Shared visit bound');visits+=result['profile_edge_visits']
        need(type(result['domain']) is list and len(result['domain'])<=65536,'Bound full pre-C0 domain')
        domain={};last=None
        for cell in result['domain']:
            need(set(cell)=={'product_id','support','count','cosine','in_C0'},'Domain schema');item=integer(cell['product_id'])
            need(last is None or last<item,'Domain order/duplicate');last=item
            need(type(cell['in_C0']) is bool and cell['in_C0']==(item in C0),'Domain C0 flag')
            need(all(type(cell[k]) in (int,float) and math.isfinite(cell[k]) and cell[k]>0 for k in ('count','cosine')),'Finite scores')
            hs=[]
            for support in cell['support']:
                need(type(support) is list and len(support)==4 and all(type(v) is int for v in support),'Support schema')
                h,c,dh,dj=support;need(h in result['seeds'] and 3<=c<=dh<=512 and dj>=c,'Support/norm bounds');hs.append(h)
            need(hs and hs==[h for h in result['seeds'] if h in hs] and len(set(hs))==len(hs),'Support seed order')
            domain[item]=cell
        novel=set(domain)-set(C0)
        for name in ('count','cosine'):
            source=ids(result['source'][name],20)
            ordered=sorted(novel,key=lambda i:(-domain[i][name],hashlib.sha256(str(i).encode('ascii')).digest(),i))[:20]
            need(source==ordered,'Source top20 drift');ranked=result['ranked_source'][name]
            need(type(ranked) is list,'Ranked source schema')
            for value in ranked:
                need(type(value) is dict and set(value)=={'rank','product_id','score','support'} and type(value['rank']) is int and type(value['score']) in (int,float) and math.isfinite(value['score']),'Rank scalar schema');integer(value['product_id'])
            need(ranked==[dict(rank=i,product_id=j,score=domain[j][name],support=domain[j]['support']) for i,j in enumerate(source,1)],'Rank/support drift')
        need(type(result['distinct_top20_sets']) is bool and result['distinct_top20_sets']==(set(result['source']['count'])!=set(result['source']['cosine'])),'Set comparison')
        need(type(result['rejection']) is list and len(result['rejection'])==len(r[:4]),'Seed guards ledger')
        for seed,reason in zip(r[:4],result['rejection']):
            need(reason.get('seed')==seed and type(reason.get('degree')) is int,'Seed guard identity')
            kind=reason.get('reason');degree=reason['degree']
            need((kind=='seed_view_empty' and degree==0 and set(reason)=={'seed','degree','reason'}) or
                 (kind=='audience_guard' and degree>512 and set(reason)=={'seed','degree','reason'}) or
                 (kind=='admitted' and 1<=degree<=512 and set(reason)=={'seed','degree','reason','support_below3'} and type(reason['support_below3']) is int and reason['support_below3']>=0),'Seed guard schema')
        ids(result['C_count']);ids(result['C_cos'])
        base=union(p,r);need(set(ctr)=={'B','T','k','matched_popular','matched_count','matched_cosine'} and ids(ctr['B'])==base,'Control schema/base')
        for name in ('matched_popular','matched_count','matched_cosine'):ids(ctr[name])
        tail=ids(ctr['T'],20);need(set(tail)==set(C0)-set(base),'Control tail');k=min(len(tail),len(result['source']['count']),len(result['source']['cosine']))
        need(type(ctr['k']) is int and ctr['k']==k,'Matched k');arms=dict(C0=C0,count=union(base,result['source']['count']),cos=union(base,result['source']['cosine']),matched_popular=union(base,tail[:k]),matched_count=union(base,result['source']['count'][:k]),matched_cos=union(base,result['source']['cosine'][:k]))
        need(result['C_count']==arms['count'] and result['C_cos']==arms['cos'] and ctr['matched_popular']==arms['matched_popular'] and ctr['matched_count']==arms['matched_count'] and ctr['matched_cosine']==arms['matched_cos'],'Six-arm composition drift')
        need(type(row['prior_pair_count']) is int and row['prior_pair_count']==len(records[q['query_id']]['prior']),'Prior per-Q count')
        intern={i:i for values in arms.values() for i in ids(values)}
        records[q['query_id']]['arms']={name:frozenset(intern[i] for i in values) for name,values in arms.items()}
    need(count==6000 and visits==manifest['shared_profile_edge_visits'] and visits<=393216000,'Complete candidate count/visits')
    for name,nrows in (('Q6000.jsonl',6000),('candidates.jsonl',6000)):
        need(manifest['outputs'][name]['rows']==nrows,'Stream row descriptor')
    return [records[q['query_id']] for q in queries]


def read_labels(paths,records,barrier,barrier_ref,check):
    need(file_ref(barrier,check)==barrier_ref,'Closed BEFORE_Y marker changed')
    need(type(paths) is list and len(paths)==3,'Exactly three native label paths')
    paths=[Path(p).resolve(strict=True) for p in paths]
    need(len(set(paths))==3 and all(p.name=='labels.parquet' and not any(ch in str(p) for ch in '*?[]{}') for p in paths),'Exact resolved native label paths')
    import duckdb
    need(duckdb.__version__=='1.5.6','Frozen DuckDB version')
    con=duckdb.connect(':memory:',config={'threads':'2','memory_limit':'512MB','max_temp_directory_size':'0B'})
    primary=None;by_q={r['query_id']:r for r in records};seen=set();total=0
    try:
        con.execute('SET allowed_paths = ['+','.join("'"+str(p).replace("'","''")+"'" for p in paths)+']')
        con.execute('SET enable_external_access=false')
        con.execute('SET lock_configuration=true')
        for anchor,path in zip(ANCHORS,paths):
            check();con.read_parquet(str(path)).project(','.join(n for n,t in LABELS)).create_view('declared_labels',replace=True)
            need([tuple(r[:2]) for r in con.execute('DESCRIBE declared_labels').fetchall()]==LABELS,'Historical fullY types')
            n=con.execute('SELECT count(*) FROM declared_labels').fetchone()[0];total+=n;need(total<=1000000,'FullY pair allocation cap')
            con.execute('SELECT '+','.join(n for n,t in LABELS)+' FROM declared_labels')
            while True:
                check();chunk=con.fetchmany(8192)
                if not chunk:break
                for qid,item,stamp,raw,same,catalog,pair in chunk:
                    need(qid in by_q and by_q[qid]['anchor']==anchor,'Foreign fullY Q/shard');integer(item);key=(qid,item)
                    need(key not in seen,'Duplicate fullY target');seen.add(key);q=by_q[qid]
                    need(type(stamp) is datetime and stamp.tzinfo is None and type(raw) is int and raw>0 and all(type(v) is bool for v in (same,catalog,pair)),'FullY scalar schema')
                    start=datetime.fromisoformat(anchor[:-1]);need(start<=stamp<start+timedelta(hours=24) and same==(stamp==start),'FullY window witness')
                    need(pair==(item in q['prior']),'FullY prior-pair mismatch')
                    need(catalog or not any(item in values for values in q['arms'].values()),'Retrieved target contradicts catalog')
                    q['targets'].add(item)
    except BaseException as error: primary=error
    try: con.close()
    except BaseException as error:
        if primary is None:primary=error
        else:note(primary,'Label close failure: '+str(type(error).__name__))
    if primary is not None:raise primary


class JSONL:
    def __init__(self,path,check):self.path,self.check,self.rows=Path(path),check,0;self.stream=self.path.open('xb',buffering=0)
    def emit(self,body):
        raw=(canon(body)+'\n').encode();self.check(len(raw));need(self.stream.write(raw)==len(raw),'Short evidence write');self.rows+=1
    def close(self):self.stream.close()


def run(request_path,output):
    output=Path(output).resolve();need(output.is_relative_to(Path('/private/tmp')) and not output.exists(),'Fresh TMP output')
    with Path(request_path).open('rb') as stream:raw=stream.read(128*1024+1)
    need(len(raw)<=128*1024,'Bound request');request=parse(raw)
    need(set(request)=={'version','seal','analysis','root_acceptance','labels','limits'} and request['version']==1 and type(request['version']) is int and type(request['labels']) is list and len(request['labels'])==3,'Exact consumer request')
    output.mkdir(mode=0o700);guard=Guard(output,request['limits']);pins=[];writers=[];primary=None;outputs={};before=False
    def pin(path,expected=None):
        value=file_ref(path,guard.check);need(expected is None or value==expected,'Pin drift: '+str(path));pins.append((Path(path),value));return value
    def descriptor(body,authenticate=True):
        need(type(body) is dict and set(body)=={'path','bytes','sha256'} and type(body['path']) is str and type(body['bytes']) is int and body['bytes']>=0 and type(body['sha256']) is str and re.fullmatch('[0-9a-f]{64}',body['sha256']),'Bound descriptor')
        if authenticate:pin(body['path'],{k:body[k] for k in ('bytes','sha256')})
        return Path(body['path'])
    def writer(name):
        w=JSONL(output/name,guard.check);writers.append(w);return w
    try:
        pin(__file__);pin(Path(estimands.__file__));pin(request_path,dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        analysis=descriptor(request['analysis']);need(request['analysis']['sha256']==ANALYSIS_SHA,'Frozen analysis identity')
        descriptor(request['root_acceptance'])  # Opaque witness: Root binds its actual meaning before execution.
        seal_path=descriptor(request['seal']);need(seal_path.stat().st_size<=2**20,'Bound seal metadata');manifest=parse(seal_path.read_bytes())
        for name in ('Q6000.jsonl','candidates.jsonl','prior-pairs.jsonl'):
            expected=manifest['outputs'][name];need(set(expected)=={'rows','bytes','sha256'} and type(expected['rows']) is int,'Stream descriptor schema')
            need(type(expected['bytes']) is int and 0<=expected['bytes']<=256*2**20,'Bound sealed stream');pin(seal_path.parent/name,{k:expected[k] for k in ('bytes','sha256')})
        records=load_sealed(seal_path.parent,manifest,guard.check)
        labels=[descriptor(d,False) for d in request['labels']]
        need(all(p.is_absolute() and p.name=='labels.parquet' and not any(ch in str(p) for ch in '*?[]{}') for p in labels) and len({p.resolve() for p in labels})==3,'Exactly three literal historical label files')
        for d in request['labels']:descriptor(d)  # Opaque authentication only; no logical label read yet.
        frame=sorted({r['user_id'] for r in records});marker=output/'BEFORE_Y.json'
        write_json(marker,dict(phase='BEFORE_LOGICAL_Y',queries=6000,prior_pairs=44172,arms=list(estimands.ARMS),analysis_identity=request['analysis'],
                   rng=RNG_SPEC,python=sys.version,frame_users=len(frame),frame_sha256=hashlib.sha256(canon(frame).encode()).hexdigest(),input_hashes=[dict(path=str(p),**v) for p,v in pins]),guard.check)
        marker_ref=pin(marker);before=True
        read_labels(labels,records,marker,marker_ref,guard.check)
        report=estimands.analyze(records,draws=2000,seed=61061,check=guard.check)
        audit=writer('private-per-query.jsonl');changes=writer('private-target-changes.jsonl');net=Counter()
        for r in records:
            target=r['targets'];new=target-r['prior'];repeat=target&r['prior']
            audit.emit(dict(query_id=r['query_id'],user_id=r['user_id'],anchor=r['anchor'],target_mass=[len(target),len(new),len(repeat)],hits={a:[len(target&v),len(new&v),len(repeat&v)] for a,v in r['arms'].items()},candidate_sizes={a:len(v) for a,v in r['arms'].items()}))
            for contrast,(a,b) in CONTRASTS.items():
                gained=target&(r['arms'][a]-r['arms'][b]);lost=target&(r['arms'][b]-r['arms'][a]);net[contrast]+=len(gained)-len(lost)
                for direction,items in (('gained',gained),('lost',lost)):
                    for item in sorted(items):changes.emit(dict(query_id=r['query_id'],product_id=item,contrast=contrast,direction=direction,new_pair=item not in r['prior']))
        for contrast,(a,b) in CONTRASTS.items():
            arms=report['summary']['cohorts']['full']['arms'];need(net[contrast]==arms[a]['hits']-arms[b]['hits'],'Gain/loss accounting')
        report.update(status='EXPLORATORY_AGGREGATE_UNVERIFIED',reused_historical_cohort=True,achieved_ranking_quality=False,causal_or_generalization_claim=False,primary_normalization_claim=False,automatic_new_model=False,analysis_sha256=ANALYSIS_SHA,rng=RNG_SPEC)
        write_json(output/'aggregate.json',report,guard.check);outputs['aggregate.json']=file_ref(output/'aggregate.json',guard.check)
    except BaseException as error:primary=error
    secondary=[]
    operations=[(w.path.name+' close',w.close) for w in writers]
    def late_pins():
        for path,value in pins:need(file_ref(path,guard.check)==value,'Late pin drift: '+str(path))
    def evidence_hashes():
        for w in writers:outputs[w.path.name]=dict(rows=w.rows,**file_ref(w.path,guard.check))
    for label,operation in operations+[('late pins fail-fast',late_pins),('closed evidence hashes',evidence_hashes)]:
        try:operation()
        except BaseException as error:secondary.append(dict(stage=label,**describe(error)))
    if primary is None and secondary:primary=RuntimeError('Consumer finalization failed')
    if primary is not None:
        for item in secondary:note(primary,'Secondary failure: '+canon(item))
    receipt=dict(status='FAILED' if primary is not None else 'COMPLETE_UNREVIEWED_EXPLORATORY_COVERAGE',before_y_closed=before,input_hashes=[dict(path=str(p),**v) for p,v in pins],outputs=outputs,secondary=secondary,telemetry=guard.telemetry(),limits=request['limits'],fits=0,predictions=0,adequacy='UNKNOWN')
    if primary is not None:receipt['primary']=describe(primary)
    try:need(len(canon(receipt).encode())<=2**20,'Receipt reserve');write_json(output/'receipt.json',receipt)
    except BaseException as error:
        if primary is None:primary=error
        else:note(primary,'Receipt failure: '+type(error).__name__)
    if primary is not None:raise primary
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();sys.exit(run(args.request,args.output))
