"""UNRUN compiler/retrieval projection canary; no labels, model loader or ML.

Literal gold comes from independently frozen wave061 A (07cae0d7 FIRST,
9b57d96a pins), corroborated by wave060 C/skeptic. This is not a tsfresh test.
"""
from datetime import datetime
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import duckdb
import numpy as np

T = datetime(2019, 10, 8)  # Source TIMESTAMP represents a naive UTC wall clock.
TIMES_A = (datetime(2019, 10, 7, 18, 30), datetime(2019, 10, 7, 20, 30),
           datetime(2019, 10, 7, 21, 30), datetime(2019, 10, 7, 23, 30))
TIMES_B = (datetime(2019, 10, 7, 18, 30), datetime(2019, 10, 7, 19, 30),
           datetime(2019, 10, 7, 20, 30), datetime(2019, 10, 7, 23, 30))
# Occupied midpoints of (0,)*162 + A=(1,0,1,1,0,1), B=(1,1,1,0,0,1).
# No production binning or bank implementation is executed by this canary.
BASE_GOLD = (
    ('from_popular', 'BOOLEAN', False),
    ('from_recent', 'BOOLEAN', True),
    ('popularity_distinct_users', 'BIGINT', 0),
    ('popular_source_rank', 'BIGINT', None),
    ('recent_source_rank', 'BIGINT', 1),
    ('candidate_category_ambiguous', 'BOOLEAN', False),
    ('candidate_category_missing', 'BOOLEAN', False),
    ('item_has_observed_history', 'BOOLEAN', True),
    ('user_has_observed_history', 'BOOLEAN', True),
    ('item_observed_age_seconds', 'DOUBLE', 19800),
    ('user_observed_age_seconds', 'DOUBLE', 19800),
    ('user_view_7d', 'BIGINT', 4),
    ('user_cart_7d', 'BIGINT', 0),
    ('user_purchase_7d', 'BIGINT', 0),
    ('user_distinct_viewed_items_7d', 'BIGINT', 1),
    ('pair_view_7d', 'BIGINT', 4),
    ('pair_cart_7d', 'BIGINT', 0),
    ('pair_purchase_7d', 'BIGINT', 0),
    ('pair_view_recency_seconds', 'DOUBLE', 1800),
    ('pair_purchase_recency_seconds', 'DOUBLE', None),
    ('item_view_24h', 'BIGINT', 4),
    ('item_purchase_24h', 'BIGINT', 0),
    ('item_distinct_viewers_7d', 'BIGINT', 1),
    ('user_category_view_7d', 'BIGINT', 4),
    ('user_category_view_recency_seconds', 'DOUBLE', 1800),
    ('item_category_view_7d', 'BIGINT', 4),
    ('category_view_7d', 'BIGINT', 4),
    ('source_coverage_24h', 'DOUBLE', 1),
    ('source_coverage_168h', 'DOUBLE', 1),
    ('user_category_view_share_7d', 'DOUBLE', 1),
    ('item_category_view_share_7d', 'DOUBLE', 1),
    ('pair_view_recency_seconds_missing', 'BOOLEAN', False),
    ('pair_purchase_recency_seconds_missing', 'BOOLEAN', True),
    ('user_category_view_7d_missing', 'BOOLEAN', False),
    ('user_category_view_share_7d_missing', 'BOOLEAN', False),
    ('user_category_view_recency_seconds_missing', 'BOOLEAN', False),
    ('item_category_view_7d_missing', 'BOOLEAN', False),
    ('category_view_7d_missing', 'BOOLEAN', False),
    ('item_category_view_share_7d_missing', 'BOOLEAN', False),
    ('retrieval_last_event_age_seconds', 'DOUBLE', 1800),
    ('retrieval_last_event_missing', 'BOOLEAN', False),
)
BUNDLE_GOLD = {
    'L01': (
        ('auto_user_view_count_24h', 'BIGINT', 4),
        ('auto_user_cart_count_24h', 'BIGINT', 0),
        ('auto_user_purchase_count_24h', 'BIGINT', 0),
    ),
    'L02': (
        ('auto_pair_view_count_24h', 'BIGINT', 4),
        ('auto_pair_cart_count_24h', 'BIGINT', 0),
        ('auto_pair_purchase_count_24h', 'BIGINT', 0),
    ),
    'L03': (
        ('auto_item_view_count_168h', 'BIGINT', 4),
        ('auto_item_cart_count_168h', 'BIGINT', 0),
        ('auto_item_purchase_count_168h', 'BIGINT', 0),
    ),
    'L04': (
        ('auto_user_view_count_distinct_24h_product_id', 'BIGINT', 1),
        ('auto_user_cart_count_distinct_168h_product_id', 'BIGINT', 0),
        ('auto_user_purchase_count_distinct_168h_product_id', 'BIGINT', 0),
    ),
    'L05': (
        ('auto_item_view_count_distinct_24h_user_id', 'BIGINT', 1),
        ('auto_item_cart_count_distinct_168h_user_id', 'BIGINT', 0),
        ('auto_item_purchase_count_distinct_24h_user_id', 'BIGINT', 0),
    ),
    'L06': (
        ('auto_pair_cart_recency_seconds_observed', 'DOUBLE', None),
        ('auto_item_cart_count_24h', 'BIGINT', 0),
        ('auto_pair_cart_recency_seconds_observed_missing', 'BOOLEAN', True),
    ),
    'L07': (
        ('auto_user_cart_recency_seconds_observed', 'DOUBLE', None),
        ('auto_user_purchase_count_distinct_24h_product_id', 'BIGINT', 0),
        ('auto_user_cart_recency_seconds_observed_missing', 'BOOLEAN', True),
    ),
    'L08': (
        ('auto_item_cart_recency_seconds_observed', 'DOUBLE', None),
        ('auto_item_cart_count_distinct_24h_user_id', 'BIGINT', 0),
        ('auto_item_cart_recency_seconds_observed_missing', 'BOOLEAN', True),
    ),
}


class TimeseriesNonaliasCanary(unittest.TestCase):
    def project_base(self, con, names):
        """Test-local label-free projection of B39 plus the two loader expressions.

        This intentionally does not invoke prepare_dataset/prepare_model_data,
        whose complete interfaces join Y. It is not a new production adapter.
        """
        self.assertEqual(names, [name for name, _, _ in BASE_GOLD])
        schema = {row[0]: row[1] for row in con.execute('DESCRIBE manual_features').fetchall()}
        self.assertEqual([(name, schema[name]) for name in names[:-2]],
                         [(name, kind) for name, kind, _ in BASE_GOLD[:-2]])
        fields = [f'CAST(f."{name}" AS FLOAT) AS "{name}"' for name in names[:-2]]
        # Exact expressions from train_baselines.prepare_dataset/model_data;
        # only the label-free SELECT is copied, not their loader or joins.
        fields += ['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds',
                   'CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
        cursor = con.execute('SELECT ' + ','.join(fields) +
                             ' FROM manual_features f ORDER BY f.query_id,f.product_id')
        self.assertEqual([column[0] for column in cursor.description], names)
        self.assertEqual([str(column[1]) for column in cursor.description], ['FLOAT'] * 41)
        columns = cursor.fetchnumpy()
        vectors = []
        for name in names:
            column = columns[name]
            if np.ma.isMaskedArray(column):
                column = column.astype(np.float32).filled(np.nan)
            vectors.append(np.asarray(column, dtype=np.float32))
        actual = np.column_stack(vectors)
        expected = np.array([[np.nan if value is None else value for _, _, value in BASE_GOLD]],
                            dtype=np.float32)
        # These two missing coordinates are literal expectations, not producer-derived.
        expected_mask = np.array([[name in ('popular_source_rank', 'pair_purchase_recency_seconds')
                                   for name, _, _ in BASE_GOLD]], dtype=bool)
        self.assertEqual(actual.shape, (1, 41))
        self.assertEqual(actual.dtype, np.dtype('float32'))
        np.testing.assert_array_equal(np.isnan(actual), expected_mask)
        np.testing.assert_array_equal(actual[~expected_mask], expected[~expected_mask])
        return actual

    def compile_history(self, times, config, base_registry, pool, compiler, retrieval, baseline):
        con = duckdb.connect(':memory:')
        try:
            con.execute('SET threads=2')
            con.execute("SET memory_limit='64MB'")  # Engine setting, not a process RSS bound.
            con.execute("SET max_temp_directory_size='0B'")
            con.execute('''CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,
                product_id BIGINT,user_id BIGINT,category_id BIGINT)''')
            con.executemany('INSERT INTO events VALUES (?,?,?,?,?)',
                            [(time, 'view', 201, 101, 301) for time in times])
            con.execute('''CREATE TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,
                anchor TIMESTAMP,label_is_mature BOOLEAN)''')
            con.execute('INSERT INTO pilot_queries VALUES (?,?,?,?)', ['fixture-q', 101, T, True])
            result = retrieval.create_candidates(con, config)
            self.assertEqual(result['candidate_rows'], 1)
            self.assertEqual(con.execute('SELECT * FROM pilot_candidates ORDER BY query_id,product_id').fetchall(),
                             [('fixture-q', 201, False, True, 0, None, 1, datetime(2019, 10, 7, 23, 30))])
            self.assertEqual([(r[0], r[1]) for r in con.execute('DESCRIBE pilot_candidates').fetchall()],
                             [('query_id', 'VARCHAR'), ('product_id', 'BIGINT'),
                              ('from_popular', 'BOOLEAN'), ('from_recent', 'BOOLEAN'),
                              ('popularity_distinct_users', 'BIGINT'), ('popular_source_rank', 'BIGINT'),
                              ('recent_source_rank', 'BIGINT'), ('last_user_event_time', 'TIMESTAMP')])
            initial = compiler.create_manual_features(con, config, base_registry)
            self.assertEqual((initial['feature_rows'], initial['core_features']), (1, 18))
            physical = [r[0] for r in con.execute('DESCRIBE manual_features').fetchall()]
            self.assertEqual(len(physical), 45)
            names = baseline.numeric_feature_names(physical)
            control = self.project_base(con, names)
            self.assertEqual(con.execute('''SELECT query_id,user_id,product_id,anchor,candidate_category_id
                FROM manual_features''').fetchall(), [('fixture-q', 101, 201, T, 301)])
            bundles = {}
            for bundle in pool['identity']['bundles']:
                bundle_id = bundle['bundle_id']
                gold = BUNDLE_GOLD[bundle_id]
                extra_names = [name for name, _, _ in gold]
                self.assertEqual([(f['name'], f['dtype']) for f in bundle['physical_delta']],
                                 [(name, kind) for name, kind, _ in gold])
                self.assertEqual(bundle['model_feature_order'], names + extra_names)
                produced = compiler.create_manual_features(con, config, bundle['registry'])
                self.assertEqual(produced['feature_rows'], 1)
                # Compiler extras interleave grain blocks; never treat raw48 as a B41 prefix.
                schema = {r[0]: r[1] for r in con.execute('DESCRIBE manual_features').fetchall()}
                self.assertEqual(len(schema), 48)
                self.assertEqual([(name, schema[name]) for name in extra_names],
                                 [(name, kind) for name, kind, _ in gold])
                projected = self.project_base(con, names)
                np.testing.assert_array_equal(np.isnan(projected), np.isnan(control))
                np.testing.assert_array_equal(projected[~np.isnan(control)], control[~np.isnan(control)])
                rows = con.execute('SELECT ' + ','.join('"' + name + '"' for name in extra_names) +
                                   ' FROM manual_features ORDER BY query_id,product_id').fetchall()
                self.assertEqual(rows, [tuple(value for _, _, value in gold)])
                bundles[bundle_id] = rows[0]
            self.assertEqual(set(bundles), {'L01', 'L02', 'L03', 'L04', 'L05', 'L06', 'L07', 'L08'})
            tables = {r[0] for r in con.execute('SHOW TABLES').fetchall()}
            self.assertFalse(tables & {'pilot_labels', 'all_labels', 'chosen_labels'})
            return control, bundles
        finally:
            con.close()

    def test_same_complete_b41_retrieval_and_eight_supports_for_distinct_histories(self):
        # Prevent any accidental ML/bank import while exercising this compiler-only body.
        with patch.dict(sys.modules, {'catboost': None, 'tsfresh': None}):
            from scripts import candidate_pilot as retrieval
            from scripts import feature_programs as programs
            from scripts import manual_features as compiler
            from scripts import train_baselines as baseline
            from scripts.protocol_manifest import load_protocol

            root = Path(compiler.__file__).resolve().parents[1]
            config = load_protocol(root / 'configs/protocols/clock-48h.json')
            base = compiler.load_registry(root / 'configs/features/manual-18.json')
            contract = json.loads((root / 'configs/features/automation-pool.json').read_text())
            pool = programs.generate_pool(contract, base)
            self.assertEqual(config['source'], {'start': '2019-10-01T00:00:00Z',
                                                'end': '2019-11-01T00:00:00Z'})
            self.assertEqual(config['query']['eligibility_hours'], 48)
            self.assertEqual(config['pilot']['start'], '2019-10-08T00:00:00Z')
            self.assertEqual(config['pilot']['end'], '2019-10-11T00:00:00Z')
            self.assertEqual([(f['name'], f['dtype']) for f in pool['identity']['base_model_schema']],
                             [(name, kind) for name, kind, _ in BASE_GOLD])
            self.assertEqual([b['bundle_id'] for b in pool['identity']['bundles']],
                             ['L01', 'L02', 'L03', 'L04', 'L05', 'L06', 'L07', 'L08'])
            self.assertNotEqual(TIMES_A, TIMES_B)
            a, supports_a = self.compile_history(TIMES_A, config, base, pool, compiler, retrieval, baseline)
            b, supports_b = self.compile_history(TIMES_B, config, base, pool, compiler, retrieval, baseline)
            np.testing.assert_array_equal(np.isnan(a), np.isnan(b))
            np.testing.assert_array_equal(a[~np.isnan(a)], b[~np.isnan(b)])
            self.assertEqual(supports_a, supports_b)


if __name__ == '__main__':
    unittest.main(verbosity=2)
