"""Selected F57 -> actual training append/inference parity; runtime UNRUN.

This is a synthetic transformation check, not a collection acceptance or model
experiment. Expected names/types/extra values are independent literals; the
reviewed rich raw-row fixture supplies the B45 reference arithmetic only.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ('catboost', 'lightgbm', 'xgboost', 'torch', 'tensorflow', 'tsfresh')
ARMS = (
    ('I1', 'L02', (
        ('auto_pair_view_count_24h', 'BIGINT'),
        ('auto_pair_cart_count_24h', 'BIGINT'),
        ('auto_pair_purchase_count_24h', 'BIGINT'),
    )),
    ('I2', 'L06', (
        ('auto_pair_cart_recency_seconds_observed', 'DOUBLE'),
        ('auto_item_cart_count_24h', 'BIGINT'),
        ('auto_pair_cart_recency_seconds_observed_missing', 'BOOLEAN'),
    )),
    ('R1', 'L01', (
        ('auto_user_view_count_24h', 'BIGINT'),
        ('auto_user_cart_count_24h', 'BIGINT'),
        ('auto_user_purchase_count_24h', 'BIGINT'),
    )),
    ('R2', 'L05', (
        ('auto_item_view_count_distinct_24h_user_id', 'BIGINT'),
        ('auto_item_cart_count_distinct_168h_user_id', 'BIGINT'),
        ('auto_item_purchase_count_distinct_24h_user_id', 'BIGINT'),
    )),
)
# Rows are A/item, A/other, A/cold, B/item, B/old. These values do not use
# generated definitions or the producer's aggregation/schema functions.
EXTRA_GOLD = {
    'L02': ((3, 1, 1), (0, 1, 1), (0, 0, 0), (1, 1, 0), (0, 0, 0)),
    'L06': ((18000.0, 3, False), (14400.0, 1, False), (None, 0, True),
            (86400.0, 3, False), (777600.0, 0, False)),
    'L01': ((4, 2, 3), (4, 2, 3), (4, 2, 3), (2, 1, 1), (2, 1, 1)),
    'L05': ((2, 2, 1), (1, 1, 2), (0, 0, 0), (2, 2, 1), (0, 0, 0)),
}


def expected_union_schema(base_schema):
    """Ordinal insertion literals; no producer schema helper is consulted."""
    pair, recency, user, item = [fields for _, _, fields in ARMS]
    insertions = {
        'user_distinct_viewed_items_7d': user,
        'pair_purchase_recency_seconds': (*pair, recency[0]),
        'item_distinct_viewers_7d': (recency[1], *item),
    }
    result = []
    for field in base_schema:
        result.append(field)
        result.extend(insertions.get(field[0], ()))
    result.append(recency[2])
    return result


class SelectedProgramTrainInferenceParityTests(unittest.TestCase):
    def assert_arm(self, data, bundle_id, names, base_gold, np):
        self.assertEqual(data.feature_names, names)
        self.assertEqual(data.x.dtype, np.dtype('float32'))
        self.assertEqual(data.group.dtype, np.dtype('int32'))
        self.assertEqual(data.items.dtype, np.dtype('int64'))
        self.assertEqual(data.x.shape, (5, 44))
        extra = np.asarray([[np.nan if value is None else value for value in row]
                            for row in EXTRA_GOLD[bundle_id]], dtype=np.float32)
        np.testing.assert_array_equal(data.x[:, :41], base_gold)
        np.testing.assert_array_equal(data.x[:, 41:], extra)

    def test_selected_union_training_append_inference_and_label_perturbation(self):
        # A backend cannot be imported or used by this actual numerical path.
        # Only filesystem roots are patched below; no compiler/loader is mocked.
        with patch.dict(sys.modules, {name: None for name in BACKENDS}):
            import duckdb
            import numpy as np
            from scripts import feature_program_collection as collection_programs
            from scripts import feature_programs as programs
            from scripts import inference_data as inference
            from scripts import manual_features as compiler
            from scripts import model_data as training
            from scripts import program_model_data as appended
            from scripts.protocol_manifest import load_protocol
            from tests import test_feature_programs_all_bundles_rich as rich

            self.assertEqual(len(rich.HISTORY), 20)
            self.assertEqual(len(rich.QUERIES), 3)
            self.assertEqual(len(rich.CANDIDATES), 5)
            # 20 events + 3 Q + 5 C + two distinct 2-row label fixtures = 32.
            labels = ((('A', rich.ITEM), ('C-empty', rich.COLD)),
                      (('A', rich.OTHER), ('B', rich.OLD)))
            self.assertEqual(20 + 3 + 5 + sum(map(len, labels)), 32)
            keys = [('A', rich.ITEM), ('A', rich.OTHER), ('A', rich.COLD),
                    ('B', rich.ITEM), ('B', rich.OLD)]
            self.assertEqual([(c[0], c[1]) for c in rich.CANDIDATES], keys)
            config = deepcopy(load_protocol(ROOT / 'configs/protocols/clock-48h.json'))
            config['pilot'] = dict(start='2019-10-10T00:00:00Z', end='2019-10-11T00:00:00Z')
            config['query']['max_users_per_day'] = 3
            config['budget'] = dict(max_anchors=3, max_candidate_pairs=660)
            base = compiler.load_registry(ROOT / 'configs/features/manual-18.json')
            contract = json.loads((ROOT / 'configs/features/automation-pool.json').read_text())
            pool = programs.generate_pool(contract, base)
            allocation = programs.allocate_slots(pool)
            selected = collection_programs.selected_union(pool, allocation)
            self.assertEqual([(s['slot'], s['bundle_id']) for s in allocation['identity']['slots']],
                             [(slot, bundle) for slot, bundle, _ in ARMS])
            declared_delta = [dict(name=n, dtype=t) for _, _, fields in ARMS for n, t in fields]
            self.assertEqual(selected['physical_delta'], declared_delta)
            schema = expected_union_schema(rich.BASE_SCHEMA)
            self.assertEqual(len(schema), 57)
            self.assertEqual(len({name for name, _ in schema}), 57)
            expected = [rich.reference_base(rich.HISTORY, c) for c in rich.CANDIDATES]
            # Independently fixed B41 coordinates corroborate the shared row oracle.
            for name, value in {
                'user_view_7d': 5, 'user_cart_7d': 2, 'user_purchase_7d': 4,
                'pair_view_7d': 4, 'pair_cart_7d': 1, 'pair_purchase_7d': 2,
                'pair_view_recency_seconds': 7200.0,
                'pair_purchase_recency_seconds': 3600.0,
                'item_view_24h': 4, 'item_purchase_24h': 1,
                'item_distinct_viewers_7d': 2,
                'item_category_view_share_7d': 0.8,
                'retrieval_last_event_age_seconds': 3600.0,
            }.items():
                self.assertEqual(expected[0][name], value, name)
            base_gold = np.asarray([[np.nan if row[name] is None else row[name]
                                     for name in rich.BASE_MODEL] for row in expected], dtype=np.float32)
            with tempfile.TemporaryDirectory(prefix='selected-train-infer-') as tmp:
                root = Path(tmp)
                con = duckdb.connect(':memory:', config={'threads': '2', 'memory_limit': '128MB',
                                                         'max_temp_directory_size': '0B'})
                try:
                    con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
                    con.executemany('INSERT INTO events VALUES (?,?,?,?,?)', rich.HISTORY)
                    con.execute('CREATE TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
                    con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,?)', rich.QUERIES)
                    con.execute('CREATE TABLE pilot_candidates(' + ','.join(n + ' ' + t for n, t in rich.C_SCHEMA) + ')')
                    con.executemany('INSERT INTO pilot_candidates VALUES (?,?,?,?,?,?,?,?)', rich.CANDIDATES)
                    compiler.create_manual_features(con, config, base)
                    self.assertEqual([tuple(r[:2]) for r in con.execute('DESCRIBE manual_features').fetchall()],
                                     list(rich.BASE_SCHEMA))
                    con.execute('CREATE TABLE frozen_base AS SELECT * FROM manual_features')
                    con.execute('COPY frozen_base TO ? (FORMAT PARQUET)', [str(root / 'base.parquet')])
                    con.execute('COPY pilot_queries TO ? (FORMAT PARQUET)', [str(root / 'q.parquet')])
                    compiler.create_manual_features(con, config, selected['registry'])
                    self.assertEqual([tuple(r[:2]) for r in con.execute('DESCRIBE manual_features').fetchall()], schema)
                    con.execute('CREATE TABLE selected_union AS SELECT * FROM manual_features')
                    base_fields = ','.join('"' + n + '"' for n, _ in rich.BASE_SCHEMA)
                    self.assertEqual(con.execute('SELECT ' + base_fields + ' FROM selected_union ORDER BY query_id,product_id').fetchall(),
                                     con.execute('SELECT * FROM frozen_base ORDER BY query_id,product_id').fetchall())
                    con.execute('COPY selected_union TO ? (FORMAT PARQUET)', [str(root / 'union.parquet')])
                    for i, rows in enumerate(labels):
                        con.execute('CREATE OR REPLACE TABLE synthetic_y(query_id VARCHAR,product_id BIGINT)')
                        con.executemany('INSERT INTO synthetic_y VALUES (?,?)', rows)
                        con.execute('COPY synthetic_y TO ? (FORMAT PARQUET)', [str(root / ('y' + str(i) + '.parquet'))])
                    # Legal names/types and identical row shape, but user counts
                    # incorrectly supplied as the pair arm: only gold rejects it.
                    replacements = dict(zip((n for n, _ in ARMS[0][2]), (n for n, _ in ARMS[2][2])))
                    wrong_fields = ','.join('"' + replacements.get(n, n) + '" AS "' + n + '"' for n, _ in schema)
                    con.execute('CREATE TABLE wrong_arm AS SELECT ' + wrong_fields + ' FROM selected_union')
                    con.execute('COPY wrong_arm TO ? (FORMAT PARQUET)', [str(root / 'wrong-arm.parquet')])
                    reordered = [schema[1], schema[0], *schema[2:]]
                    con.execute('CREATE TABLE wrong_schema AS SELECT ' + ','.join('"' + n + '"' for n, _ in reordered) + ' FROM selected_union')
                    con.execute('COPY wrong_schema TO ? (FORMAT PARQUET)', [str(root / 'wrong-schema.parquet')])
                finally:
                    con.close()
                source_schema = [list(field) for field in schema]
                collection = dict(phase=dict(role='train'),
                    feature_columns=[n for n, _ in rich.BASE_SCHEMA],
                    refs=dict(queries=['q.parquet'], features=['base.parquet'], labels=['y0.parquet']))
                with patch.object(training, 'ROOT', root), patch.object(appended, 'ROOT', root), patch.object(inference, 'ROOT', root):
                    first = training.prepare_model_data(collection, max_queries=None, max_rows=5, matrix_byte_cap=65536)
                    changed = deepcopy(collection); changed['refs']['labels'] = ['y1.parquet']
                    second = training.prepare_model_data(changed, max_queries=None, max_rows=5, matrix_byte_cap=65536)
                    self.assertEqual(first.feature_names, list(rich.BASE_MODEL))
                    np.testing.assert_array_equal(first.x, base_gold)
                    np.testing.assert_array_equal(second.x, first.x)
                    np.testing.assert_array_equal(first.y, np.asarray([1, 0, 0, 0, 0], dtype=np.int8))
                    np.testing.assert_array_equal(second.y, np.asarray([0, 1, 0, 0, 1], dtype=np.int8))
                    self.assertEqual(first.y.dtype, np.dtype('int8'))
                    self.assertEqual(second.y.dtype, np.dtype('int8'))
                    self.assertEqual([q[:3] for q in first.queries], [q[:3] for q in rich.QUERIES])
                    self.assertEqual(first.queries[-1][-1], frozenset({rich.COLD}))
                    self.assertEqual(second.queries[-1][-1], frozenset())
                    self.assertNotEqual(first.queries, second.queries)
                    for slot, bundle_id, fields in ARMS:
                        with self.subTest(slot=slot, bundle=bundle_id):
                            names = list(rich.BASE_MODEL) + [n for n, _ in fields]
                            arm = selected['arms'][slot]
                            self.assertEqual(arm['columns'], names[41:])
                            self.assertEqual(arm['model_feature_order'], names)
                            actual_delta = {f['name']: f for f in selected['physical_delta']}
                            delta = [actual_delta[n] for n in arm['columns']]
                            self.assertEqual(delta, [dict(name=n, dtype=t) for n, t in fields])
                            options = dict(extra_columns=delta, expected_source_schema=source_schema,
                                           matrix_byte_cap=65536, chunk_vectors=1)
                            trained = appended.append_program_features(first, ['union.parquet'], **options)
                            retrained = appended.append_program_features(second, ['union.parquet'], **options)
                            inferred = inference.load_inference_data(['q.parquet'], ['base.parquet'],
                                expected_feature_names=names, extra_feature_paths=['union.parquet'],
                                extra_feature_names=names[41:], max_queries=3, max_rows=5,
                                matrix_byte_cap=65536, chunk_vectors=1)
                            for data in (trained, retrained, inferred):
                                self.assert_arm(data, bundle_id, names, base_gold, np)
                                self.assertEqual(data.group.tolist(), [0, 0, 0, 1, 1])
                                self.assertEqual(data.items.tolist(), [rich.ITEM, rich.OTHER, rich.COLD, rich.ITEM, rich.OLD])
                                self.assertEqual([(data.queries[int(g)][0], int(item)) for g, item in zip(data.group, data.items)], keys)
                            self.assertEqual(inferred.queries, [q[:3] for q in rich.QUERIES])
                            np.testing.assert_array_equal(inferred.calendar_maturity, np.ones(3, dtype=np.bool_))
                            self.assertEqual(inferred.preparation['outcome_relations_opened'], 0)
                            for data, base_data in ((trained, first), (retrained, second)):
                                self.assertEqual(data.queries, base_data.queries)
                                np.testing.assert_array_equal(data.y, base_data.y)
                                self.assertEqual(data.preparation['program']['outcome_relations_opened'], 0)
                            with self.assertRaisesRegex(ValueError, 'source schema/order'):
                                appended.append_program_features(first, ['wrong-schema.parquet'], **options)
                            if bundle_id == 'L02':
                                wrong = appended.append_program_features(first, ['wrong-arm.parquet'], **options)
                                self.assertEqual(wrong.feature_names, names)
                                self.assertEqual(wrong.x.shape, trained.x.shape)
                                with self.assertRaises(AssertionError):
                                    self.assert_arm(wrong, bundle_id, names, base_gold, np)
                    np.testing.assert_array_equal(first.x, base_gold)
                    np.testing.assert_array_equal(second.x, base_gold)
            for backend in BACKENDS:
                self.assertIsNone(sys.modules[backend], backend)


if __name__ == '__main__':
    unittest.main()
