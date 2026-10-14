"""Independent typed expected transport and known failed-receipt regressions."""
from pathlib import Path
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
import duckdb
from tests.oracles import metadata_export_audit as o

class MetadataExpectedTransportTests(unittest.TestCase):
    def setUp(self):
        self.con=duckdb.connect(':memory:');self.con.execute('SET threads=2');self.addCleanup(self.con.close)

    def test_nullable_bigint_is_exact_before_dataframe_inference(self):
        values=[2**60+1,None,-2**63,2**63-1]
        rows=[[i,v] for i,v in enumerate(values)]
        o.install_expected(self.con,'expected',rows,[('product_id','BIGINT'),('category_id','BIGINT')])
        self.assertEqual(self.con.execute('SELECT * FROM expected ORDER BY product_id').fetchall(),[tuple(r) for r in rows])
        self.con.execute("CREATE TEMP TABLE physical AS SELECT 'q' query_id,* FROM expected")
        o.compare_broadcast(self.con,'physical','expected',[('category_id','BIGINT')],lambda:None)
        self.con.execute('UPDATE physical SET category_id=? WHERE product_id=0',[2**60])
        with self.assertRaisesRegex(ValueError,'Every-row metadata mismatch'):
            o.compare_broadcast(self.con,'physical','expected',[('category_id','BIGINT')],lambda:None)

    def test_all_five_nullable_types_and_empty_relation(self):
        schema=[('product_id','BIGINT'),('flag','BOOLEAN'),('text','VARCHAR'),('price','DOUBLE'),('stamp','TIMESTAMP')]
        rows=[[1,True,'value:русский',1.25,datetime(2019,10,1)],[2,None,None,None,None]]
        o.install_expected(self.con,'expected',rows,schema)
        self.assertEqual(self.con.execute('SELECT * FROM expected ORDER BY product_id').fetchall(),[tuple(r) for r in rows])
        o.install_expected(self.con,'empty',[],schema)
        self.assertEqual([tuple(r[:2]) for r in self.con.execute('DESCRIBE empty').fetchall()],schema)
        self.assertEqual(self.con.execute('SELECT count(*) FROM empty').fetchone()[0],0)

    def test_every_broadcast_copy_and_null_is_compared(self):
        schema=[('product_id','BIGINT'),('value','DOUBLE')]
        o.install_expected(self.con,'expected',[[1,None],[2,2.0]],schema)
        self.con.execute("CREATE TEMP TABLE physical AS SELECT 'q' query_id,* FROM expected UNION ALL SELECT 'r',* FROM expected")
        o.compare_broadcast(self.con,'physical','expected',[('value','DOUBLE')],lambda:None)
        self.con.execute("UPDATE physical SET value=3 WHERE query_id='r' AND product_id=2")
        with self.assertRaises(ValueError):o.compare_broadcast(self.con,'physical','expected',[('value','DOUBLE')],lambda:None)
        self.con.execute("UPDATE physical SET value=2 WHERE query_id='r' AND product_id=2")
        self.con.execute("UPDATE physical SET value=0 WHERE query_id='r' AND product_id=1")
        with self.assertRaises(ValueError):o.compare_broadcast(self.con,'physical','expected',[('value','DOUBLE')],lambda:None)

    def test_known_failed_receipt_rejects_before_inputs_or_source(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();directory=root/'artifacts/metadata-price-development'/('a'*64);directory.mkdir(parents=True)
            (directory/'report.failed.json').write_text('{"status":"failed"}')
            with patch.object(o,'ROOT',root),patch.object(o.tempfile,'gettempdir',return_value=str(root)),patch.object(o.transport,'prepare_export_plan') as transport,patch.object(o.duckdb,'connect') as engine:
                with self.assertRaisesRegex(ValueError,'known failed finalization receipt'):o.run(directory)
                transport.assert_not_called();engine.assert_not_called()
            report=json.loads(next(root.glob('tlab009-full-source-*/report.json')).read_text())
            self.assertEqual(report['status'],'failed')
            self.assertFalse((directory/'run.json').exists())

if __name__=='__main__':unittest.main()
