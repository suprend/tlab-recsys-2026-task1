from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import numpy as np

from scripts import model_data as d
from tests import test_inference_data as inference_tests
BASE=inference_tests.BASE

from scripts import program_model_data as m


class ProgramModelDataTests(unittest.TestCase):
    def setUp(self):
        fixture=inference_tests.InferenceTests('test_triples_exact_large_ids_nulls_and_all_queries')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.root=fixture.root;self.con=fixture.con
        for module in [d,m]:
            p=patch.object(module,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        self.con.execute('UPDATE q SET label_is_mature=true')
        self.con.execute('CREATE TABLE y(query_id VARCHAR,product_id BIGINT)')
        self.con.execute("INSERT INTO y VALUES('a',9007199254740993),('empty',999)")
        self.con.execute('COPY y TO ? (FORMAT PARQUET)',[str(self.root/'y.parquet')])
        fixture.export()
        self.collection=dict(phase=dict(role='selection'),feature_columns=[r[0] for r in self.con.execute('DESCRIBE f').fetchall()],
            refs=dict(queries=['q.parquet'],features=['f.parquet'],labels=['y.parquet']))
        self.data=d.prepare_model_data(self.collection,max_queries=None,max_rows=660)
        fields=['3::BIGINT auto_test_count','50.0::DOUBLE auto_test_recency','false::BOOLEAN auto_test_recency_missing']
        fields += [str(i)+'::BIGINT auto_unused'+str(i) for i in range(9)]
        self.con.execute('CREATE TABLE export AS SELECT f.*,'+','.join(fields)+' FROM f')
        self.con.execute("UPDATE export SET auto_test_count=0,auto_test_recency=NULL,auto_test_recency_missing=true WHERE query_id='b'")
        self.schema=[list(r[:2]) for r in self.con.execute('DESCRIBE export').fetchall()]
        self.delta=[dict(name=n,dtype=t) for n,t in self.schema[-12:-9]]
        self.save()

    def save(self):
        self.con.execute('COPY export TO ? (FORMAT PARQUET)',[str(self.root/'export.parquet')])

    def load(self,**kwargs):
        options=dict(extra_columns=self.delta,expected_source_schema=self.schema)
        options.update(kwargs)
        return m.append_program_features(self.data,['export.parquet'],**options)

    def test_every_B_query_key_target_value_preserved_and_only_three_columns_added(self):
        before=self.data.x.copy();data=self.load()
        self.assertEqual(data.x.shape,(2,44));self.assertEqual(data.feature_names,BASE+[x['name'] for x in self.delta])
        self.assertEqual(data.queries,self.data.queries);self.assertEqual(data.queries[-1][-1],frozenset({999}))
        for name in ['group','items','y']:np.testing.assert_array_equal(getattr(data,name),getattr(self.data,name))
        np.testing.assert_array_equal(data.x[:,:41],before);np.testing.assert_array_equal(self.data.x,before)
        self.assertEqual(data.group.tolist(),[0,1]);self.assertEqual(data.items.tolist(),[9007199254740993,42])
        self.assertEqual(data.x[:,41].tolist(),[3.,0.]);self.assertTrue(np.isnan(data.x[1,42]));self.assertEqual(data.x[:,43].tolist(),[0.,1.])
        self.assertEqual(data.preparation['program']['outcome_relations_opened'],0)
        self.assertNotIn('auto_unused0',data.feature_names)

    def test_extra_missing_replaced_duplicate_and_wrong_query_identity_fail(self):
        original=self.con.execute('SELECT * FROM export').fetchall()
        for sql in ["DELETE FROM export WHERE query_id='b'",'INSERT INTO export SELECT * FROM export LIMIT 1',
            "UPDATE export SET product_id=43 WHERE query_id='b'","UPDATE export SET user_id=999 WHERE query_id='b'",
            "UPDATE export SET anchor=anchor+INTERVAL 1 SECOND WHERE query_id='b'"]:
            self.con.execute('DELETE FROM export');self.con.executemany('INSERT INTO export VALUES('+','.join('?' for _ in self.schema)+')',original)
            self.con.execute(sql);self.save()
            with self.subTest(sql=sql),self.assertRaisesRegex(ValueError,'key|identity'):self.load()

    def test_cap_and_expired_guard_precede_engine_or_merged_allocation(self):
        with patch.object(m.duckdb,'connect') as connect:
            with self.assertRaisesRegex(MemoryError,'before allocation'):self.load(matrix_byte_cap=1)
            connect.assert_not_called()
            def stop():raise TimeoutError('caller expired')
            with self.assertRaisesRegex(TimeoutError,'caller expired'):self.load(check=stop)
            connect.assert_not_called()

    def test_schema_delta_mask_and_infinity_fail_without_mutating_B(self):
        before=self.data.x.copy()
        bad=deepcopy(self.delta);bad[0]['name']='user_id'
        with self.assertRaisesRegex(ValueError,'name/type'):self.load(extra_columns=bad)
        bad=deepcopy(self.schema);bad[-1][1]='DOUBLE'
        with self.assertRaisesRegex(ValueError,'schema/order'):self.load(expected_source_schema=bad)
        self.con.execute("UPDATE export SET auto_test_recency_missing=false WHERE query_id='b'");self.save()
        with self.assertRaisesRegex(ValueError,'NULL/mask'):self.load()
        self.con.execute("UPDATE export SET auto_test_recency='inf'::DOUBLE");self.save()
        with self.assertRaisesRegex(ValueError,'Infinite'):self.load()
        np.testing.assert_array_equal(self.data.x,before)

    def test_empty_C_retains_all_queries_fullY_and_returns_empty44(self):
        self.data.x=self.data.x[:0];self.data.items=self.data.items[:0];self.data.group=self.data.group[:0];self.data.y=self.data.y[:0]
        self.con.execute('DELETE FROM export');self.save();data=self.load()
        self.assertEqual(data.x.shape,(0,44));self.assertEqual(data.queries,self.data.queries)
        self.assertEqual(data.preparation['program']['chunks'],0)

    def test_multichunk_exact_large_keys_and_nonchosen_queries_are_not_resampled(self):
        from datetime import datetime
        t=datetime(2019,10,25)
        self.con.execute('DELETE FROM export')
        # 12 groups x220 rows crosses a one-vector chunk boundary. Every query
        # has a unique user; an extra unchosen source query is intentionally
        # ignored because the immutable base loader already fixed Q before Y.
        q=[('q'+str(i),100+i,t,frozenset()) for i in range(12)]
        g=np.repeat(np.arange(12,dtype=np.int32),220)
        items=np.tile(np.arange(220,dtype=np.int64)+9007199254740993,12)
        self.data=d.ModelData(q,g,items,np.zeros((2640,41),np.float32),np.zeros(2640,np.int8),BASE.copy(),None,[],{})
        names=[n for n,t in self.schema]
        for i,row in enumerate(q):
            for j in range(220):
                values={n:0 for n in names};values.update(query_id=row[0],user_id=row[1],anchor=t,
                    product_id=9007199254740993+j,last_user_event_time=t,auto_test_recency=None,auto_test_recency_missing=True)
                self.con.execute('INSERT INTO export VALUES('+','.join('?' for _ in names)+')',[values[n] for n in names])
        self.con.execute("INSERT INTO export SELECT 'unchosen',user_id,product_id,anchor,*EXCLUDE(query_id,user_id,product_id,anchor) FROM export LIMIT 1")
        self.save();data=self.load(chunk_vectors=1)
        np.testing.assert_array_equal(data.group,g);np.testing.assert_array_equal(data.items,items)
        self.assertEqual(data.preparation['program']['chunks'],2);self.assertEqual(data.preparation['program']['largest_chunk_rows'],2048)
        self.assertEqual(data.queries,q);self.assertEqual(int(data.items.min()),9007199254740993)


if __name__=='__main__':unittest.main()
