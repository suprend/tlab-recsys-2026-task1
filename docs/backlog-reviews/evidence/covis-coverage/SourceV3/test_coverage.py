"""Invented seal/labels only; no actual producer output or target reads."""
from collections import Counter
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import duckdb
import coverage as c
from test_estimands import EstimandTests


def dump(path,body):
    path.write_text(json.dumps(body,sort_keys=True,separators=(',',':'))+'\n')


def ref(path):
    raw=path.read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def desc(path):return dict(path=str(path),**ref(path))


def make_labels(root,rows_by_day):
    paths=[];con=duckdb.connect(':memory:',config={'threads':'2','memory_limit':'32MB'})
    try:
        for day,rows in zip((8,9,10),rows_by_day):
            path=root/str(day)/'labels.parquet';path.parent.mkdir(parents=True,exist_ok=True)
            con.execute('CREATE OR REPLACE TEMP TABLE fixture_labels(query_id VARCHAR,product_id BIGINT,first_purchase_time TIMESTAMP,raw_purchase_rows BIGINT,same_second_purchase BOOLEAN,catalog_seen_before BOOLEAN,pair_seen_before BOOLEAN)')
            if rows:con.executemany('INSERT INTO fixture_labels VALUES(?,?,?,?,?,?,?)',rows)
            con.execute('COPY fixture_labels TO ? (FORMAT PARQUET)',[str(path)]);paths.append(path)
    finally:con.close()
    return paths


def fixture(root):
    seal_dir=root/'sealed';seal_dir.mkdir()
    queries=[]
    for day in (8,9,10):
        anchor=f'2019-10-{day:02d}T00:00:00Z'
        for user in range(1,2001):
            qid=hashlib.sha256(f'query|2026|{anchor}|{user}'.encode('ascii')).hexdigest()
            queries.append(dict(query_id=qid,user_id=user,anchor=anchor))
    queries.sort(key=lambda q:(hashlib.sha256(b'tlab-hyp061-q100-v1\0'+q['query_id'].encode('ascii')).digest(),q['query_id'].encode('ascii')))
    for rank,q in enumerate(queries):q['global_rank']=rank
    with (seal_dir/'Q6000.jsonl').open('w') as stream:
        for q in queries:stream.write(json.dumps(q)+'\n')
    with (seal_dir/'prior-pairs.jsonl').open('w') as stream:
        for rank,q in enumerate(queries):
            for item in range(1000,1000+(8 if rank<2172 else 7)):
                stream.write(json.dumps(dict(query_id=q['query_id'],product_id=item))+'\n')
    visits=0
    with (seal_dir/'candidates.jsonl').open('w') as stream:
        for q in sorted(queries,key=lambda q:(q['anchor'],q['global_rank'])):
            large=q['global_rank']==0;empty=q['global_rank']==1
            p=list(range(1,181)) if large else [];r=[] if empty else [1000]
            baseline=[*p,*r];tail=[181] if large else [];C0=sorted([*baseline,*tail]);source=[] if empty else [2000]
            support=[[1000,3,3,3]]
            domain=[] if empty else [dict(product_id=2000,count=9/13,cosine=(9/13)/3,support=support,in_C0=False)]
            result=dict(seeds=r,source=dict(count=source,cosine=source),ranked_source={name:[] if empty else [dict(rank=1,product_id=2000,score=domain[0][name],support=support)] for name in ('count','cosine')},
                domain=domain,rejection=[] if empty else [dict(seed=1000,degree=3,reason='admitted',support_below3=0)],profile_edge_visits=0 if empty else 6,distinct_top20_sets=False,query_id=q['query_id'],C_count=[*baseline,*source],C_cos=[*baseline,*source])
            k=1 if large else 0
            controls=dict(B=baseline,T=tail,k=k,matched_popular=[*baseline,*tail[:k]],matched_count=[*baseline,*source[:k]],matched_cosine=[*baseline,*source[:k]])
            row=dict(q,C0=C0,P180=p,R20=r,core_result=result,controls=controls,prior_pair_count=8 if q['global_rank']<2172 else 7)
            visits+=result['profile_edge_visits'];stream.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
    manifest=dict(status='SEALED6000_UNREVIEWED_NO_OUTCOMES',queries_written=6000,q100_matches=100,prior_pairs_written=44172,history_select_completion='complete',
        shared_profile_edge_visits=visits,graph_builds=[dict(anchor=a,complete=True) for a in c.ANCHORS],
        outputs={name:dict(rows=44172 if name=='prior-pairs.jsonl' else 6000,**ref(seal_dir/name)) for name in ('Q6000.jsonl','candidates.jsonl','prior-pairs.jsonl')})
    dump(seal_dir/'seal.json',manifest)
    rows=[[],[],[]]
    q0,q1=queries[:2]
    for q,items in ((q0,(1000,181,2000)),(q1,(9999,))):
        stamp=datetime.fromisoformat(q['anchor'][:-1])+timedelta(seconds=1)
        index=(8,9,10).index(stamp.day)
        rows[index].extend((q['query_id'],item,stamp,1,False,item!=9999,item==1000) for item in items)
    paths=make_labels(root/'invented-targets',rows)
    witness=root/'opaque-acceptance.txt';witness.write_text('Invented witness; no authority, no real acceptance')
    analysis=Path('/tmp/tlab-hyp061-q6000-seal-proposal-v1/NEXTSTAGE-PLAN-v2.md')
    request=dict(version=1,seal=desc(seal_dir/'seal.json'),analysis=desc(analysis),root_acceptance=desc(witness),labels=list(map(desc,paths)),
        limits=dict(cpu_seconds=15,wall_seconds=25,rss_bytes=512*2**20,output_bytes=16*2**20))
    request_path=root/'request.json';dump(request_path,request)
    return queries,manifest,request,request_path


class ConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='coverage-invented-',dir=Path(__file__).resolve().parent)
        cls.root=Path(cls.temp.name);cls.queries,cls.manifest,cls.request,cls.request_path=fixture(cls.root)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_full_consumer_barrier_all6arms_offC_private_gainloss_and_public_aggregate(self):
        output=self.root/'full-output';real_connect=duckdb.connect;projections=[];reads=[];statements=[];native=[];case=self
        allowed=[str(Path(d['path']).resolve()) for d in self.request['labels']]
        outside=self.root/'not-allowed.parquet';outside.write_bytes(Path(allowed[0]).read_bytes())
        class Relation:
            def __init__(self,value):self.value=value
            def project(self,fields):projections.append(fields);self.value=self.value.project(fields);return self
            def create_view(self,*a,**k):return self.value.create_view(*a,**k)
        class Connection:
            def __init__(self,value):self.value=value
            def read_parquet(self,path):
                marker=output/'BEFORE_Y.json';self.assertion(marker.exists())
                body=json.loads(marker.read_text());self.assertion(body['queries']==6000 and body['prior_pairs']==44172)
                settings=self.value.execute("SELECT current_setting('allowed_paths'),current_setting('enable_external_access'),current_setting('lock_configuration')").fetchone()
                case.assertEqual(sorted(settings[0]),sorted(allowed));case.assertEqual(settings[1:],(False,True));native.append(settings)
                if not reads:
                    with case.assertRaises(duckdb.Error):self.value.execute('SET enable_external_access=true')
                    with case.assertRaises(duckdb.Error):self.value.read_parquet(str(outside)).fetchall()
                reads.append(path);return Relation(self.value.read_parquet(path))
            def execute(self,sql,*args):statements.append(sql);self.value.execute(sql,*args);return self
            def assertion(self,value):
                if not value:raise AssertionError('Logical labels opened before complete marker')
            def __getattr__(self,name):return getattr(self.value,name)
        with patch.object(duckdb,'connect',side_effect=lambda *a,**k:Connection(real_connect(*a,**k))):
            self.assertEqual(c.run(self.request_path,output),0)
        self.assertEqual(reads,[d['path'] for d in self.request['labels']])
        self.assertEqual(len(native),3)
        self.assertEqual(statements[:3],['SET allowed_paths = ['+','.join("'"+p.replace("'","''")+"'" for p in allowed)+']','SET enable_external_access=false','SET lock_configuration=true'])
        self.assertEqual(projections,[','.join(n for n,t in c.LABELS)]*3)
        public=json.loads((output/'aggregate.json').read_text());full=public['summary']['cohorts']['full']
        self.assertEqual((public['summary']['queries'],full['positive_queries'],full['target_mass']),(6000,2,4))
        self.assertEqual(full['arms']['cos']['micro_recall'],.5);self.assertEqual(full['arms']['cos']['macro_recall'],1/3)
        self.assertFalse(public['continuation']);self.assertIsNone(public['bootstrap']['intervals']['full']['cos-C0']['ci95'])
        self.assertEqual(public['bootstrap']['frame_users'],2000)
        text=(output/'aggregate.json').read_text()
        for forbidden in ('"query_id"','"user_id"','"product_id"',self.queries[0]['query_id']):self.assertNotIn(forbidden,text)
        private=[json.loads(line) for line in (output/'private-per-query.jsonl').read_text().splitlines()]
        self.assertEqual(len(private),6000);self.assertEqual(sum(row['target_mass'][0]==0 for row in private),5998)
        empty=next(row for row in private if row['query_id']==self.queries[1]['query_id'])
        self.assertEqual(empty['target_mass'][0],1);self.assertTrue(all(n==0 for n in empty['candidate_sizes'].values()))
        changes=[json.loads(line) for line in (output/'private-target-changes.jsonl').read_text().splitlines()]
        self.assertEqual(len(changes),6)
        self.assertEqual({(row['direction'],row['product_id']) for row in changes},{('gained',2000),('lost',181)})
        self.assertTrue(all(row['new_pair'] for row in changes))
        receipt=json.loads((output/'receipt.json').read_text());self.assertEqual(receipt['status'],'COMPLETE_UNREVIEWED_EXPLORATORY_COVERAGE')
        marker_ref=next({k:d[k] for k in ('bytes','sha256')} for d in receipt['input_hashes'] if Path(d['path']).name=='BEFORE_Y.json')
        self.assertEqual(ref(output/'BEFORE_Y.json'),marker_ref)

    def test_hash_drift_and_missing_acceptance_fail_before_any_logical_Y(self):
        changed=dict(self.request);changed['seal']=dict(changed['seal'],sha256='0'*64)
        for label,request in (('drift',changed),('missing',{k:v for k,v in self.request.items() if k!='root_acceptance'})):
            path=self.root/(label+'-request.json');dump(path,request)
            with patch.object(c,'read_labels',side_effect=AssertionError('Forbidden read')) as read:
                with self.assertRaises(ValueError):c.run(path,self.root/(label+'-output'))
                read.assert_not_called()
            self.assertFalse((self.root/(label+'-output')/'BEFORE_Y.json').exists())

    def test_composition_drift_foreignQ_and_duplicate_prior_are_rejected(self):
        directory=self.root/'sealed'
        for name,change,pattern in (
            ('candidates.jsonl',lambda row:row['controls'].update(k=17),'Matched k'),
            ('candidates.jsonl',lambda row:row.update(query_id='foreign'),'Candidate Q'),
            ('prior-pairs.jsonl',lambda row:row.update(product_id=1001),'Prior order/duplicate')):
            path=directory/name;original=path.read_bytes();lines=original.splitlines(keepends=True)
            first=json.loads(lines[0]);change(first);lines[0]=(json.dumps(first)+'\n').encode();path.write_bytes(b''.join(lines))
            try:
                with self.assertRaisesRegex(ValueError,pattern):c.load_sealed(directory,self.manifest)
            finally:path.write_bytes(original)

    def test_duplicate_foreign_Y_and_changed_marker_fail_without_silent_dedup(self):
        q=self.queries[0];anchor=q['anchor'];index=c.ANCHORS.index(anchor);stamp=datetime.fromisoformat(anchor[:-1])+timedelta(seconds=1)
        for name,rows,message in (('duplicate',[(q['query_id'],1000,stamp,1,False,True,True)]*2,'Duplicate fullY'),('foreign',[('foreign',1000,stamp,1,False,True,True)],'Foreign fullY')):
            folder=self.root/name;folder.mkdir();by_day=[[],[],[]];by_day[index]=rows;paths=make_labels(folder,by_day)
            marker=folder/'BEFORE_Y.json';dump(marker,{'phase':'fixture-closed'})
            records=[dict(q,targets=set(),prior={1000},arms={a:frozenset({1000}) for a in c.estimands.ARMS})]
            with self.assertRaisesRegex(ValueError,message):c.read_labels(paths,records,marker,ref(marker),lambda extra=0:None)
        marker=self.root/'changed-marker.json';dump(marker,{'old':1});old=ref(marker);dump(marker,{'new':2})
        with patch.object(duckdb,'connect',side_effect=AssertionError('Opened despite marker drift')) as connect:
            with self.assertRaisesRegex(ValueError,'BEFORE_Y'):c.read_labels([],[],marker,old,lambda extra=0:None)
            connect.assert_not_called()

    def test_target24h_half_open_literal_endpoints_and_same_second_flag(self):
        q=self.queries[0];start=datetime.fromisoformat(q['anchor'][:-1]);index=c.ANCHORS.index(q['anchor'])
        cells=[('anchor',start,True,True),('before24',start+timedelta(hours=24)-timedelta(microseconds=1),False,True),
               ('at24',start+timedelta(hours=24),False,False),('at30',start+timedelta(hours=30),False,False),
               ('at48',start+timedelta(hours=48),False,False),('preanchor',start-timedelta(seconds=1),False,False),
               ('anchor-wrong-flag',start,False,False)]
        for name,stamp,same,accepted in cells:
            with self.subTest(name=name):
                folder=self.root/"target-boundary's"/name;folder.mkdir(parents=True)
                by_day=[[],[],[]];by_day[index]=[(q['query_id'],1000,stamp,1,same,True,True)]
                paths=make_labels(folder,by_day);marker=folder/'BEFORE_Y.json';dump(marker,{'phase':'invented-closed-marker'})
                records=[dict(q,targets=set(),prior={1000},arms={a:frozenset({1000}) for a in c.estimands.ARMS})]
                if accepted:
                    c.read_labels(paths,records,marker,ref(marker),lambda extra=0:None)
                    self.assertEqual(records[0]['targets'],{1000})
                else:
                    with self.assertRaisesRegex(ValueError,'FullY window witness'):c.read_labels(paths,records,marker,ref(marker),lambda extra=0:None)


if __name__=='__main__':
    signal.alarm(16);resource.setrlimit(resource.RLIMIT_CPU,(8,8))
    started,cpu=time.monotonic(),time.process_time();suite=unittest.TestSuite()
    for cls in (ConsumerTests,EstimandTests):suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;rss=int(rss if sys.platform=='darwin' else rss*1024)
    record=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),wall_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,
        rss_bytes=rss,fits=0,real_inputs_read=0,duckdb=duckdb.__version__,success=result.wasSuccessful() and rss<=512*2**20)
    record['exit_code']=0 if record['success'] else 1;print(json.dumps(record,sort_keys=True),flush=True);sys.exit(record['exit_code'])
