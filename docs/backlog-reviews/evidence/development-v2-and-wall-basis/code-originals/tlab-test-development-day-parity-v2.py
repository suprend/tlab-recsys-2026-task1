"""Tiny independent parity tests: four invented Q, eight C, zero events/models/Y."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

START = time.monotonic()
resource.setrlimit(resource.RLIMIT_CPU, (59,60))
signal.alarm(115)
SPEC = importlib.util.spec_from_file_location('independent_parity','/tmp/tlab-development-day-parity-v2.py')
p = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(p)
import duckdb
import numpy as np

ATTEMPTS = dict(real_data=0,children=0,network=0,models=0)
def audit(event,args):
    if event in {'subprocess.Popen','os.system','os.posix_spawn','os.fork'}:
        ATTEMPTS['children'] += 1; raise AssertionError('No child processes')
    if event.startswith('socket.'):
        ATTEMPTS['network'] += 1; raise AssertionError('No network')
    if event == 'open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
        name = os.fsdecode(args[0])
        if '/tlab-recsys-2026/artifacts/' in name or '/tlab-recsys-2026/data/' in name:
            ATTEMPTS['real_data'] += 1; raise AssertionError('No real artifact/data reads')
        if name.endswith('.cbm'):
            ATTEMPTS['models'] += 1; raise AssertionError('No models')
sys.addaudithook(audit)

def check():
    r = resource.getrusage(resource.RUSAGE_SELF)
    rss = r.ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    if r.ru_utime+r.ru_stime >= 58 or time.monotonic()-START >= 110 or rss > 512*2**20:
        raise RuntimeError('Tiny-test budget exhausted')

class Parity(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(':memory:', config={'threads':'2','memory_limit':'128MB','max_temp_directory_size':'0B'})
        self.tables = {name:name for name in p.TABLE_KEYS}
        def create(name,schema):
            self.con.execute('CREATE TABLE '+p.quote(name)+'('+','.join(p.quote(n)+' '+t for n,t in schema)+')')
        for name in ('old_q','new_q'): create(name,p.Q_SCHEMA)
        for name in ('old_c','new_c'): create(name,p.C_SCHEMA)
        for name in ('old_b','new_b'): create(name,p.B_SCHEMA)
        create('new_e',p.E_SCHEMA)
        for role in ('B','W'):
            create('old_'+role+'_raw',p.RAW_SCHEMA); create('score_'+role,p.S_SCHEMA)
        # Intentionally put chosen extras after unrelated union columns; no prefix slicing.
        suffix = [('irrelevant_'+str(i),'BIGINT') for i in range(9)] + p.E_SCHEMA[2:]
        create('old_union',p.B_SCHEMA+suffix)
        self.qids = ['a-other','b-selected','c-other','d-selected']
        qrows = []
        import datetime
        self.day = datetime.datetime(2019,10,22)
        for i,qid in enumerate(self.qids):
            anchor = self.day if i%2 else self.day+datetime.timedelta(days=1)
            qrows.append((qid,100+i,anchor,3,5,2,1,anchor-datetime.timedelta(seconds=1),168.0,True))
        self.con.executemany('INSERT INTO old_q VALUES ('+','.join('?' for _ in p.Q_SCHEMA)+')',qrows)
        self.con.execute('INSERT INTO new_q SELECT * FROM old_q WHERE anchor='+p.DAY_SQL)
        self.crows=[]; self.brows=[]; self.raw=[]
        for g,q in enumerate(qrows):
            for j in range(2):
                item=9007199254740993+g*10+j
                c=(q[0],item,True,j==1,3,1,None if j==0 else 2,None if j==0 else q[2]-datetime.timedelta(seconds=2))
                values=dict(zip((n for n,t in p.C_SCHEMA),c));values.update(user_id=q[1],anchor=q[2])
                for n,t in p.B_SCHEMA[10:]:
                    values[n] = (False if t=='BOOLEAN' else 1.25 if t=='DOUBLE' else 7)
                values['candidate_category_id']=None if j==0 else 17
                values['pair_view_recency_seconds']=None if j==0 else 2.0
                values['pair_view_recency_seconds_missing']=j==0
                values['user_view_7d']=16777217+j  # rounds distinctly at float32 boundary
                b=tuple(values[n] for n,t in p.B_SCHEMA)
                self.crows.append(c); self.brows.append(b)
                # Exact tie requires ascending int64 product; day-local group 0/1 would be wrong.
                self.raw.append((g,item,0.25 if g==1 else float(j)))
                if g%2:
                    extra=(g+1,j+1,0)
                    self.con.execute('INSERT INTO old_union VALUES ('+','.join('?' for _ in p.B_SCHEMA+suffix)+')',b+tuple(range(9))+extra)
        self.con.executemany('INSERT INTO old_c VALUES ('+','.join('?' for _ in p.C_SCHEMA)+')',self.crows)
        self.con.executemany('INSERT INTO old_b VALUES ('+','.join('?' for _ in p.B_SCHEMA)+')',self.brows)
        for suffix in ('c','b'):
            self.con.execute('INSERT INTO new_'+suffix+' SELECT s.* FROM old_'+suffix+' s JOIN new_q q USING(query_id)')
        self.con.execute('INSERT INTO new_e SELECT '+','.join(p.quote(n) for n,t in p.E_SCHEMA)+' FROM old_union')
        for role in ('B','W'):
            self.con.executemany('INSERT INTO old_'+role+'_raw VALUES (?,?,?)',self.raw)
            self.con.execute('INSERT INTO score_'+role+' SELECT q.query_id,s.product_id,s.raw_score FROM old_'+role+'_raw s '
                'JOIN (SELECT query_id,row_number()OVER(ORDER BY query_id)-1 g FROM old_q)q ON s."group"=q.g JOIN new_q n USING(query_id)')
    def tearDown(self): self.con.close()
    def compare(self):
        return p.compare_tables(self.con,self.tables,check=check,all_queries=4,all_pairs=8,day_queries=2)
    def rejected(self,sql,pattern):
        self.con.execute(sql)
        with self.assertRaisesRegex(ValueError,pattern): self.compare()
    def test_complete_positive_global_mapping_and_nonprefix_extras(self):
        r=self.compare();self.assertEqual((r['query_count'],r['candidate_count']),(2,4))
        self.assertEqual(r['score_checks']['B']['max_abs_error'],0)
        self.assertEqual(r['model_columns'],{'B':41,'W':44})
    def test_all_Q_diagnostics_checked(self):
        self.rejected("UPDATE new_q SET history_active_days_7d=9 WHERE query_id='d-selected'",'physical values')
    def test_calendar_and_day_exact(self):
        self.rejected("UPDATE new_q SET label_is_mature=FALSE WHERE query_id='d-selected'",'calendar maturity')
    def test_candidate_optional_NULL_checked(self):
        self.rejected('UPDATE new_c SET popular_source_rank=NULL','physical values')
    def test_feature_beyond_any_sample_checked(self):
        self.rejected("UPDATE new_b SET item_distinct_viewers_7d=99 WHERE query_id='d-selected'",'physical values')
    def test_chosen_three_explicit_values_checked(self):
        self.rejected('UPDATE new_e SET '+p.quote(p.W_MODEL[-1])+'=11','physical values')
    def test_null_mask_exact(self):
        self.rejected('UPDATE new_b SET pair_view_recency_seconds_missing=FALSE','physical values')
    def test_physical_type_exact(self):
        self.rejected('ALTER TABLE new_b ALTER user_view_7d TYPE DOUBLE','Physical schema')
    def test_finite_physical_and_scores(self):
        self.rejected("UPDATE score_B SET raw_score='Infinity'::DOUBLE",'finite float64')
    def test_complete_key_missing_tail(self):
        self.rejected("DELETE FROM new_e WHERE query_id='d-selected'",'pair transport')
    def test_exact_float32_signed_zero_bits(self):
        self.con.execute('UPDATE old_b SET item_observed_age_seconds=0.0')
        self.con.execute("UPDATE new_b SET item_observed_age_seconds='-0.0'::DOUBLE")
        with self.assertRaisesRegex(ValueError,'representation bits'): self.compare()
    def test_score_tolerance_can_pass_without_order_change(self):
        self.con.execute('UPDATE score_B SET raw_score=raw_score+5e-13')
        self.assertLessEqual(self.compare()['score_checks']['B']['max_abs_error'],1e-12)
    def test_rank_tie_order_not_forgiven_by_score_tolerance(self):
        self.rejected("UPDATE score_B SET raw_score=raw_score+5e-13 WHERE query_id='b-selected' AND product_id=9007199254741004",'tie rank')
    def test_full_old_score_domain_closed(self):
        self.rejected('UPDATE old_B_raw SET "group"=4000 WHERE "group"=0','group domain')
    def test_empty_C_query_retained(self):
        # Keep the selected Q with no C in every old/new relation; comparisons must retain Q.
        for name in ('old_c','old_b','old_union','new_c','new_b','new_e','score_B','score_W'):
            self.con.execute('DELETE FROM '+p.quote(name)+" WHERE query_id='d-selected'")
        for role in ('B','W'):self.con.execute('DELETE FROM old_'+role+'_raw WHERE "group"=3')
        r=p.compare_tables(self.con,self.tables,check=check,all_queries=4,all_pairs=6,day_queries=2)
        self.assertEqual((r['query_count'],r['candidate_count']),(2,2))
    def test_NPZ_safe_dtypes_members_bounds_and_large_integer(self):
        with tempfile.TemporaryDirectory(prefix='tlab-parity-tiny-') as tmp:
            path=Path(tmp)/'scores.npz'
            arrays=dict(group=np.array([1,3],dtype=np.int32),product_id=np.array([9007199254740993,9007199254741003],dtype=np.int64),raw_score=np.array([.1,.2],dtype=np.float64))
            np.savez_compressed(path,**arrays)
            frame=p._npz(self.con,path,'tiny_npz',check=check,rows=2)
            self.assertEqual(int(frame.product_id.iloc[0]),9007199254740993)
            self.con.unregister('tiny_npz')
            for name,bad in [('group',np.array([1,3],dtype=np.int64)),('product_id',np.array([1.,2.])),('raw_score',np.array([1.,np.nan]))]:
                changed={**arrays,name:bad};np.savez_compressed(path,**changed)
                with self.assertRaises(ValueError):p._npz(self.con,path,'tiny_npz',check=check,rows=2)
            np.savez_compressed(path,**arrays,forbidden=np.array([1]))
            with self.assertRaisesRegex(ValueError,'three'):p._npz(self.con,path,'tiny_npz',check=check,rows=2)
            np.savez_compressed(path,**arrays)
            with self.assertRaises(ValueError):p._npz(self.con,path,'tiny_npz',check=check,rows=1)
    def test_closed_entrypoint_rejects_without_data_access(self):
        with patch.object(p,'_small',return_value=({'version':1,'scope':'other'},{})):
            with self.assertRaisesRegex(ValueError,'Closed owner request'):p.verify_request('no-real-request.json','0'*64,check=check)
    def test_reserved_internal_relation_rejects_before_mutation(self):
        self.con.execute("UPDATE new_b SET item_distinct_viewers_7d=99 WHERE query_id='d-selected'")
        names=['parity_day_b','PaRiTy_DaY_B','parity_global_q','parity_day_q','parity_day_c',
               'parity_day_e','parity_B_all','parity_B_day','parity_W_all','parity_W_day']
        for name in names:
            self.con.execute('CREATE OR REPLACE TEMP VIEW '+p.quote(name)+' AS SELECT * FROM new_b')
            self.tables['new_b']=name
            with self.assertRaisesRegex(ValueError,'Reserved internal'):
                self.compare()
            current=self.con.execute('SELECT item_distinct_viewers_7d FROM '+p.quote(name)+
                " WHERE query_id='d-selected' ORDER BY product_id").fetchall()
            self.assertEqual(current,[(99,),(99,)])
        self.tables['new_b']='new_b'
        self.tables['new_e']='NEW_B'
        with self.assertRaisesRegex(ValueError,'case-insensitive'):
            self.compare()
    def test_NPZ_header_seam_cannot_change_allocated_snapshot(self):
        with tempfile.TemporaryDirectory(prefix='tlab-parity-v2-npz-race-') as tmp:
            path=Path(tmp)/'scores.npz'
            original=dict(group=np.array([1,3],dtype=np.int32),product_id=np.array([10,11],dtype=np.int64),raw_score=np.array([.1,.2],dtype=np.float64))
            replacement=dict(group=np.array([1,3,1],dtype=np.int32),product_id=np.array([10,11,12],dtype=np.int64),raw_score=np.array([.1,.2,.3],dtype=np.float64))
            np.savez_compressed(path,**original);expected=hashlib.sha256(path.read_bytes()).hexdigest()
            header_count=0;changed=False;shapes=[];frame=None;error=None
            actual_header=np.lib.format.read_array_header_1_0
            actual_read=np.lib.format.read_array
            def header(*args,**kwargs):
                nonlocal header_count
                answer=actual_header(*args,**kwargs);header_count+=1;return answer
            def read(*args,**kwargs):
                answer=actual_read(*args,**kwargs);shapes.append(list(answer.shape));return answer
            def seam():
                nonlocal changed
                check()
                if header_count>=3 and not changed:
                    np.savez_compressed(path,**replacement);changed=True
            with patch.object(np.lib.format,'read_array_header_1_0',side_effect=header),patch.object(np.lib.format,'read_array',side_effect=read):
                try:frame=p._npz(self.con,path,'snapshot_probe',check=seam,rows=2)
                except ValueError as exc:error=str(exc)
            self.assertTrue(changed)
            self.assertEqual(shapes,[[2],[2],[2]],'Allocation must use validated immutable two-row snapshot')
            self.assertIsNone(error)
            self.assertEqual(frame.product_id.tolist(),[10,11])
            self.con.unregister('snapshot_probe')
            # Closed adapter's final byte pin still rejects path changes.
            with self.assertRaisesRegex(ValueError,'Pinned bytes changed'):
                p._hash(path,expected,check,cap=262144)
    def test_NPZ_snapshot_expected_hash_and_compressed_cap(self):
        with tempfile.TemporaryDirectory(prefix='tlab-parity-v2-npz-bounds-') as tmp:
            path=Path(tmp)/'scores.npz'
            np.savez_compressed(path,group=np.array([1],dtype=np.int32),product_id=np.array([10],dtype=np.int64),raw_score=np.array([.1],dtype=np.float64))
            with self.assertRaisesRegex(ValueError,'expected SHA256'):
                p._npz(self.con,path,'wrong_snapshot',check=check,rows=1,expected_sha='0'*64)
            path.write_bytes(b'0'*(20+4*65536+1))
            with self.assertRaisesRegex(ValueError,'compressed NPZ snapshot'):
                p._npz(self.con,path,'large_snapshot',check=check,rows=1)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Parity))
    check();r=resource.getrusage(resource.RUSAGE_SELF)
    receipt=dict(scope='tiny_invented_parity_only',success=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        wall_seconds=time.monotonic()-START,cpu_seconds=r.ru_utime+r.ru_stime,peak_rss_bytes=r.ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        bounds=dict(cpu_seconds=60,wall_seconds=120,rss_bytes=512*2**20,threads=2),
        fixture=dict(invented_queries=4,invented_candidate_pairs=8,invented_event_rows=0,models=0,fits=0,Y=0),guard_attempts=ATTEMPTS,
        actual_DB_Parquet_NPZ_reads=0,project_writes=0,children=0,source_acceptance_issued=False,execution_granted=False)
    Path('/tmp/tlab-development-day-parity-tiny-result-v2.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,sort_keys=True));sys.exit(0 if result.wasSuccessful() else 1)
