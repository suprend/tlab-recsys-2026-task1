from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import duckdb
import numpy as np

from scripts import model_data as d
from scripts import metadata_price_features as m
from scripts import train_baselines as b
import tests.test_train_baselines as baseline_tests
import tests.test_metadata_price_features as metadata_tests


class ModelDataTests(unittest.TestCase):
    def setUp(self):
        fixture=baseline_tests.TrainingDataTests('test_real_parquet_prepare_keeps_fullY_outside_C_and_float32_missing_semantics')
        fixture.setUp();self.addCleanup(fixture.doCleanups);self.fixture=fixture;self.root=fixture.root
        self.collection=deepcopy(fixture.collection);self.collection['phase']=dict(role='train')
        patch.object(d,'ROOT',self.root).start()
        self.con=duckdb.connect(':memory:');self.addCleanup(self.con.close)
        self.con.execute('CREATE TABLE f AS SELECT * FROM read_parquet(?)',[str(self.root/'features.parquet')])
        self.make_metadata()

    def make_metadata(self):
        numeric={name:'false' for name in m.NUMERIC}
        numeric.update(log_price='1.0::DOUBLE',category_peer_log_price_mean='2.0::DOUBLE',
            category_peer_product_support='1::BIGINT',category_log_price_difference='-1.0::DOUBLE')
        fields=["'value:1152921504606846977'::VARCHAR category_id_nominal","'value:code'::VARCHAR category_code_by_id",
                "'value:state:missing'::VARCHAR brand"]
        fields += [numeric[name]+' '+name for name in m.NUMERIC]
        self.con.execute('CREATE OR REPLACE TABLE addon AS SELECT query_id,product_id,'+','.join(fields)+' FROM f')
        self.con.execute("UPDATE addon SET brand='state:missing',brand_missing=true WHERE product_id=3")
        self.con.execute("UPDATE addon SET brand='state:ambiguous',brand_missing=true,brand_ambiguous=true WHERE product_id=5")
        self.save('addon','addon.parquet')

    def save(self,table,name):
        path=self.root/name
        if path.exists():path.unlink()
        self.con.execute('COPY '+table+' TO ? (FORMAT PARQUET)',[str(path)])

    def load(self,**kwargs):
        options=dict(max_queries=None,max_rows=10000,metadata_paths=['addon.parquet'])
        options.update(kwargs)
        return d.prepare_model_data(self.collection,**options)

    def test_base_and_mixed_exactly_match_unchanged008_including_fullY_emptyC_and_NaN(self):
        self.con.execute("UPDATE f SET last_user_event_time=NULL WHERE product_id=3")
        self.save('f','features.parquet')
        reference=b.prepare_dataset(self.collection,max_queries=None,max_rows=100)
        base=self.load(metadata_paths=None);mixed=self.load()
        d.assert_base_equivalent(base,reference);d.assert_base_equivalent(mixed,reference)
        self.assertIsNone(base.categorical)
        self.assertEqual(mixed.categorical.shape,(9,3));self.assertEqual(mixed.categorical_names,list(m.NOMINAL))
        self.assertEqual(mixed.x.dtype,np.float32);self.assertEqual(mixed.items.dtype,np.int64)
        self.assertEqual(mixed.group.dtype,np.int32);self.assertEqual(mixed.y.dtype,np.int8)
        q={r[0]:r[3] for r in mixed.queries}
        self.assertEqual(q['missed'],{999});self.assertEqual(q['emptyC'],{111});self.assertNotIn(999,mixed.items)
        self.assertEqual(b.group_accounting(mixed)[-1]['empty_candidate_groups'],1)
        self.assertIn(b'value:1152921504606846977',mixed.categorical[:,0])
        self.assertIn(b'value:state:missing',mixed.categorical[:,2])
        common=[v for v in mixed.categorical[:,2] if v==b'value:state:missing']
        self.assertTrue(all(v is common[0] for v in common))
        changed=deepcopy(mixed);changed.x[0,0]+=1
        with self.assertRaisesRegex(ValueError,'equivalence'):d.assert_base_equivalent(changed,reference)

    def test_sampling_label_independent_and_selection_unseen_does_not_fit_encoder(self):
        first=self.load(max_queries=2)
        self.con.execute("CREATE TABLE changed(query_id VARCHAR,product_id BIGINT)")
        self.con.execute("INSERT INTO changed VALUES ('missed',30)");self.save('changed','changed.parquet')
        self.collection['refs']['labels']=['changed.parquet'];second=self.load(max_queries=2)
        self.assertEqual([q[:3] for q in first.queries],[q[:3] for q in second.queries])
        np.testing.assert_array_equal(first.items,second.items);np.testing.assert_array_equal(first.x,second.x)
        self.collection['phase']['role']='selection'
        self.con.execute("UPDATE addon SET brand='value:selection-unseen',brand_missing=false,brand_ambiguous=false")
        self.save('addon','addon.parquet');selection=self.load()
        self.assertEqual(set(selection.categorical[:,2]),{b'value:selection-unseen'})

    def test_rows_keys_and_byte_caps_reject_before_array_allocation(self):
        with patch.object(d.np,'empty',side_effect=AssertionError('allocated prematurely')):
            with self.assertRaisesRegex(ValueError,'before allocation'):self.load(max_rows=1)
            with self.assertRaisesRegex(MemoryError,'before allocation'):self.load(matrix_byte_cap=1)
            self.con.execute('DELETE FROM addon WHERE product_id=3');self.save('addon','addon.parquet')
            with self.assertRaisesRegex(ValueError,'key cover'):self.load()

    def test_duplicate_or_orphan_metadata_and_wrong_order_reject(self):
        self.con.execute('INSERT INTO addon SELECT * FROM addon LIMIT 1');self.save('addon','addon.parquet')
        with self.assertRaisesRegex(ValueError,'key cover'):self.load()
        self.make_metadata();self.con.execute("INSERT INTO addon SELECT query_id,9999,*EXCLUDE(query_id,product_id) FROM addon LIMIT 1")
        self.save('addon','addon.parquet')
        with self.assertRaisesRegex(ValueError,'key cover'):self.load()
        self.make_metadata();self.con.execute('CREATE TABLE reordered AS SELECT product_id,query_id,*EXCLUDE(query_id,product_id) FROM addon')
        self.save('reordered','addon.parquet')
        with self.assertRaisesRegex(ValueError,'schema/order'):self.load()

    def test_invalid_namespace_missing_mask_and_infinite_numeric_reject(self):
        for alteration,expected in [("brand='raw-unprefixed'",'namespace'),
            ('category_peer_log_price_mean=NULL','missing-mask'),("log_price='inf'::DOUBLE",'Infinite')]:
            self.make_metadata();self.con.execute('UPDATE addon SET '+alteration);self.save('addon','addon.parquet')
            with self.subTest(alteration=alteration),self.assertRaisesRegex(ValueError,expected):self.load()

    def test_empty_candidate_matrix_keeps_whole_fullY_query_universe(self):
        self.con.execute('DELETE FROM f');self.save('f','features.parquet');self.make_metadata()
        data=self.load()
        self.assertEqual(data.x.shape,(0,18));self.assertEqual(data.categorical.shape,(0,3))
        self.assertEqual(len(data.queries),5);self.assertEqual(data.preparation['chunks'],0)
        self.assertEqual(b.group_accounting(data)[-1]['positive_fullY_queries'],4)

    def test_chunk_boundaries_preserve_every_row_once_and_large_int64_ids_exactly(self):
        self.con.execute('''CREATE TABLE q AS SELECT 'q'||r.id query_id,r.id::BIGINT user_id,
            TIMESTAMP '2019-10-08' anchor,true label_is_mature FROM range(12) r(id)''')
        self.con.execute('''CREATE OR REPLACE TABLE f AS SELECT q.query_id,q.user_id,
            (1152921504606846977+r.id)::BIGINT product_id,q.anchor,100::BIGINT candidate_category_id,
            TIMESTAMP '2019-10-07' last_user_event_time,r.id::BIGINT user_view_7d FROM q CROSS JOIN range(220) r(id)''')
        self.save('q','queries.parquet');self.save('f','features.parquet');self.make_metadata()
        data=self.load(chunk_vectors=1)
        reference=b.prepare_dataset(self.collection,max_queries=None,max_rows=10000)
        d.assert_base_equivalent(data,reference)
        self.assertEqual(data.preparation['rows'],2640);self.assertEqual(data.preparation['chunks'],2)
        self.assertEqual(data.preparation['max_chunk_rows'],2048)
        self.assertEqual(int(data.items.min()),1152921504606846977)
        self.assertEqual(int(data.items.max()),1152921504606847196)

    def test_train_encoded_cardinality_includes_sentinels_and_rejects_above4096(self):
        nominal=np.array([[b'value:'+str(i).encode(),b'state:missing',b'value:brand'] for i in range(4095)]+
            [[b'state:missing',b'state:missing',b'value:brand']],dtype=object)
        self.assertEqual(m.validate_train_cardinality(nominal)['category_id_nominal'],4096)
        with self.assertRaisesRegex(ValueError,'one-hot ceiling'):
            m.validate_train_cardinality(np.vstack([nominal,np.array([[b'state:ambiguous',b'state:missing',b'value:brand']],dtype=object)]))

    def test_reserved_phase_bad_limits_and_fullY_duplicate_are_rejected(self):
        self.collection['phase']['role']='confirmation'
        with self.assertRaisesRegex(ValueError,'development'):self.load()
        self.collection['phase']['role']='train'
        for values in [dict(chunk_vectors=33),dict(max_queries=26001),dict(max_rows=5720001)]:
            with self.subTest(values=values),self.assertRaises(ValueError):self.load(**values)
        self.con.execute('CREATE TABLE y AS SELECT * FROM read_parquet(?)',[str(self.root/'labels.parquet')])
        self.con.execute('INSERT INTO y SELECT * FROM y LIMIT 1');self.save('y','labels.parquet')
        with self.assertRaisesRegex(ValueError,'full targets'):self.load()


class RepresentationPortTests(unittest.TestCase):
    def test_all_direct_oracle_edge_cases_match_frozen_metadata_array_validator(self):
        fixture=metadata_tests.MetadataPriceTests('test_all_pairs_match_direct_list_oracle_and_fixed_schema')
        fixture.setUp();self.addCleanup(fixture.tearDown);fixture.create()
        numeric,nominal=m.model_arrays(fixture.con)
        d.validate_metadata_arrays(numeric,nominal)
        for field in ['price_missing','brand_missing','code_missing','category_peer_mean_missing']:
            changed=numeric.copy();changed[:,m.NUMERIC.index(field)]=1-changed[:,m.NUMERIC.index(field)]
            with self.subTest(field=field),self.assertRaises(ValueError):d.validate_metadata_arrays(changed,nominal)


if __name__=='__main__':unittest.main()
