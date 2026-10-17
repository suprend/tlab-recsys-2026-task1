"""SOURCE-only batching regression; no runtime result is claimed here.

Fixed Q/C test the compiler's partition independence, not retrieval lineage.
Only independent specification constants/helpers are reused from the rich test;
its test body, producer expectation helpers and model/label loaders are never called.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE_START = datetime(2019, 10, 1)
FIRST = datetime(2019, 10, 10)
SECOND = datetime(2019, 10, 11)
ITEM, OTHER, COLD, OLD, OUTSIDE, LATER_OUTSIDE = 10, 20, 30, 70, 90, 80
USER, PEER, EMPTY_USER = 101, 102, 103

# Tuple order: event_time, action, product, user, historical category.
# OUTSIDE is a candidate only for D at FIRST: whole A+D includes it in the
# candidate domain, singleton A excludes it. LATER_OUTSIDE is never a candidate.
EVENTS = (
    (SOURCE_START - timedelta(seconds=1), 'purchase', ITEM, USER, 100),
    (SOURCE_START, 'cart', OLD, EMPTY_USER, 300),
    (FIRST - timedelta(hours=168), 'view', OUTSIDE, 999, 100),
    (FIRST - timedelta(hours=168, seconds=1), 'view', OUTSIDE, 999, 100),
    (FIRST - timedelta(hours=168) + timedelta(seconds=1), 'view', OUTSIDE, 998, 100),
    (FIRST - timedelta(hours=3), 'view', OUTSIDE, 999, 100),
    (FIRST - timedelta(hours=1), 'view', ITEM, USER, 100),
    (FIRST - timedelta(hours=2), 'view', OTHER, USER, 200),
    (FIRST - timedelta(hours=24), 'cart', ITEM, USER, 100),
    (FIRST - timedelta(hours=24), 'cart', ITEM, USER, 100),
    (FIRST - timedelta(minutes=30), 'purchase', OTHER, USER, 200),
    (FIRST - timedelta(hours=168), 'purchase', ITEM, PEER, 100),
    (FIRST - timedelta(hours=6), 'cart', ITEM, None, 100),
    (FIRST - timedelta(hours=5), 'cart', None, USER, None),
    (FIRST, 'view', ITEM, PEER, 999),
    (FIRST + timedelta(hours=2), 'cart', ITEM, USER, 200),
    (FIRST + timedelta(hours=3), 'purchase', ITEM, PEER, 200),
    (FIRST + timedelta(hours=4), 'view', ITEM, PEER, 200),
    (FIRST + timedelta(hours=1), 'view', LATER_OUTSIDE, 999, 200),
    (FIRST + timedelta(hours=6), 'view', LATER_OUTSIDE, 998, 200),
    (SECOND, 'view', ITEM, PEER, 999),
    (SECOND + timedelta(hours=1), 'cart', OTHER, USER, 999),
)
QUERIES = (
    ('A', USER, FIRST, True),
    ('B', PEER, SECOND, True),
    ('C-empty', EMPTY_USER, FIRST, True),
    ('D', 999, FIRST, True),
)
# The inherited retrieval columns are fixed inputs, not reconstructed evidence.
CANDIDATES = (
    ('A', ITEM, True, True, 1, 1, 1, FIRST - timedelta(hours=1)),
    ('A', OTHER, True, True, 1, 2, 2, FIRST - timedelta(minutes=30)),
    ('A', COLD, False, False, 0, None, None, None),
    ('B', ITEM, True, True, 1, 1, 1, FIRST + timedelta(hours=4)),
    ('B', OTHER, True, False, 1, 2, None, None),
    ('D', OUTSIDE, False, True, 0, None, 1, FIRST - timedelta(hours=3)),
)
# Both disjoint schedules run B and D before A. A and D share FIRST but are
# separated in split2/singletons, changing the same-anchor candidate union.
# The empty-C Q has its own singleton and also shares split2 with another anchor.
SCHEDULES = (
    ('whole', (('C-empty', 'B', 'D', 'A'),), False),
    ('split2', (('B', 'C-empty', 'D'), ('A',)), True),
    ('singletons_reverse', (('B',), ('D',), ('C-empty',), ('A',)), True),
)


def expected_extra(records, user, item, anchor, specification):
    """Independent row/set interpretation of the rich test's literal table."""
    _, _, grain, action, operation, hours = specification
    matches = []
    for stamp, kind, product, person, _ in records:
        if not SOURCE_START <= stamp < anchor or kind != action:
            continue
        if grain in {'user', 'pair'} and person != user:
            continue
        if grain in {'item', 'pair'} and product != item:
            continue
        if hours is not None and stamp < anchor - timedelta(hours=hours):
            continue
        matches.append((stamp, product, person))
    if operation == 'count':
        return len(matches)
    if operation == 'distinct':
        position = 1 if grain == 'user' else 2
        return len({row[position] for row in matches if row[position] is not None})
    if operation == 'missing':
        return not matches
    return (anchor - max(row[0] for row in matches)).total_seconds() if matches else None


class FeatureBatchInvariance(unittest.TestCase):
    def compile_schedule(self, registry, schema, schedule, reverse_rows,
                         config, compiler, duckdb, candidate_schema):
        """One private connection per schedule; successive calls reuse it.

        This deliberately preserves old TEMP state between compiler calls so
        an accidental stale-cache optimization is observable across anchors.
        """
        con = duckdb.connect(':memory:', config={'threads': '2', 'memory_limit': '128MB',
                                                 'max_temp_directory_size': '0B'})
        try:
            con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
            con.executemany('INSERT INTO events VALUES (?,?,?,?,?)',
                            list(reversed(EVENTS)) if reverse_rows else EVENTS)
            query_by_id = {row[0]: row for row in QUERIES}
            result = {}
            seen_queries = []
            python_types = {'VARCHAR': str, 'BIGINT': int, 'BOOLEAN': bool,
                            'TIMESTAMP': datetime, 'DOUBLE': float}
            for batch in schedule:
                seen_queries.extend(batch)
                con.execute('CREATE OR REPLACE TEMP TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
                con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,?)',
                                [query_by_id[qid] for qid in batch])
                con.execute('CREATE OR REPLACE TEMP TABLE pilot_candidates(' +
                            ','.join(name + ' ' + kind for name, kind in candidate_schema) + ')')
                chosen = [row for row in CANDIDATES if row[0] in batch]
                if chosen:
                    con.executemany('INSERT INTO pilot_candidates VALUES (?,?,?,?,?,?,?,?)',
                                    list(reversed(chosen)) if reverse_rows else chosen)
                summary = compiler.create_manual_features(con, config, registry)
                self.assertEqual(summary['feature_rows'], len(chosen))
                actual_schema = [tuple(row[:2]) for row in con.execute('DESCRIBE manual_features').fetchall()]
                self.assertEqual(actual_schema, schema)
                names = [name for name, _ in schema]
                rows = con.execute('SELECT * FROM manual_features ORDER BY query_id,product_id').fetchall()
                self.assertEqual(len(rows), len(chosen))
                self.assertEqual({row[:2] for row in rows}, {row[:2] for row in chosen})
                for row in rows:
                    key = row[:2]
                    self.assertNotIn(key, result)
                    for value, (name, kind) in zip(row, schema):
                        if value is not None:
                            self.assertIs(type(value), python_types[kind], (key, name))
                    fields = dict(zip(names, row))
                    self.assertEqual((fields['user_id'], fields['anchor']), query_by_id[key[0]][1:3])
                    # Retain types explicitly: Python bool==int must not hide a
                    # value-transport change during the metamorphic comparison.
                    result[key] = tuple((type(value).__name__, value) for value in row)
                self.assertFalse({row[0] for row in con.execute('SHOW TABLES').fetchall()} &
                                 {'pilot_labels', 'all_labels', 'chosen_labels'})
            self.assertCountEqual(seen_queries, list(query_by_id))
            self.assertEqual(set(result), {row[:2] for row in CANDIDATES})
            return result
        finally:
            con.close()

    def assert_literal_core(self, rows, schema):
        def fields(key):
            return dict(zip((name for name, _ in schema),
                            (value for _, value in rows[key])))
        for key, category, numerator, denominator, ratio in (
            (('A', ITEM), 100, 1, 4, 0.25),
            (('A', OTHER), 200, 1, 1, 1.0),
            (('B', ITEM), 200, 1, 4, 0.25),
            (('B', OTHER), 200, 1, 4, 0.25),
            (('D', OUTSIDE), 100, 3, 4, 0.75),
        ):
            actual = fields(key)
            self.assertEqual(actual['candidate_category_id'], category, key)
            self.assertIs(actual['candidate_category_ambiguous'], False, key)
            self.assertIs(actual['candidate_category_missing'], False, key)
            self.assertEqual(actual['item_category_view_7d'], numerator, key)
            self.assertEqual(actual['category_view_7d'], denominator, key)
            self.assertEqual(actual['item_category_view_share_7d'], ratio, key)
            self.assertIs(actual['item_category_view_share_7d_missing'], False, key)
            self.assertEqual(actual['source_coverage_24h'], 1.0, key)
            self.assertEqual(actual['source_coverage_168h'], 1.0, key)
        cold = fields(('A', COLD))
        self.assertIsNone(cold['candidate_category_id'])
        self.assertIs(cold['candidate_category_missing'], True)
        self.assertIs(cold['item_has_observed_history'], False)
        for name in ('user_category_view_7d', 'item_category_view_7d', 'category_view_7d',
                     'user_category_view_share_7d', 'item_category_view_share_7d'):
            self.assertIsNone(cold[name], name)
            self.assertIs(cold[name + '_missing'], True, name)
        # The FIRST peer is future for A, but becomes the exact24h lower bound
        # for B. Latest metadata changes100->200 between the two anchors.
        self.assertEqual(fields(('A', ITEM))['item_view_24h'], 1)
        self.assertEqual(fields(('B', ITEM))['item_view_24h'], 2)

    def test_B45_and_all_eight_programs_are_independent_of_query_batching(self):
        with patch.dict(sys.modules, {'catboost': None, 'tsfresh': None}):
            import duckdb
            from scripts import manual_features as compiler
            from scripts import feature_programs as programs
            from scripts.protocol_manifest import load_protocol
            # Only the inspected independent schema/semantic helpers are
            # reused. No test instance/body, projection or producer helper.
            from tests.test_feature_programs_all_bundles_rich import (
                BASE_SCHEMA, BUNDLES, C_SCHEMA, bundle_schema,
            )

            self.assertEqual(len(EVENTS), 22)
            self.assertEqual((len(QUERIES), len(CANDIDATES)), (4, 6))
            base = compiler.load_registry(ROOT / 'configs/features/manual-18.json')
            contract = json.loads((ROOT / 'configs/features/automation-pool.json').read_text())
            pool = programs.generate_pool(contract, base)
            self.assertEqual([bundle['bundle_id'] for bundle in pool['identity']['bundles']], list(BUNDLES))
            config = deepcopy(load_protocol(ROOT / 'configs/protocols/clock-48h.json'))
            config['pilot'] = dict(start='2019-10-10T00:00:00Z', end='2019-10-12T00:00:00Z')
            config['query']['max_users_per_day'] = 3
            config['budget'] = dict(max_anchors=6, max_candidate_pairs=1320)
            variants = [('B', base, list(BASE_SCHEMA))] + [
                (bundle['bundle_id'], bundle['registry'], bundle_schema(bundle['bundle_id']))
                for bundle in pool['identity']['bundles']
            ]
            baseline = None
            for bundle_id, registry, schema in variants:
                outcomes = []
                for schedule_name, schedule, reverse_rows in SCHEDULES:
                    with self.subTest(bundle=bundle_id, schedule=schedule_name):
                        rows = self.compile_schedule(registry, schema, schedule, reverse_rows,
                                                     config, compiler, duckdb, C_SCHEMA)
                        self.assert_literal_core(rows, schema)
                        outcomes.append(rows)
                self.assertEqual(outcomes[0], outcomes[1], bundle_id)
                self.assertEqual(outcomes[0], outcomes[2], bundle_id)
                if bundle_id == 'B':
                    baseline = outcomes[0]
                    continue
                names = [name for name, _ in schema]
                for candidate in CANDIDATES:
                    key = candidate[:2]
                    record = dict(zip(names, (value for _, value in outcomes[0][key])))
                    # Full B45 is preserved through each program registry.
                    preserved = tuple(outcomes[0][key][names.index(name)] for name, _ in BASE_SCHEMA)
                    self.assertEqual(preserved, baseline[key], (bundle_id, key))
                    query = next(row for row in QUERIES if row[0] == key[0])
                    for specification in BUNDLES[bundle_id]:
                        name = specification[0]
                        want = expected_extra(EVENTS, query[1], key[1], query[2], specification)
                        self.assertIs(type(record[name]), type(want), (bundle_id, key, name))
                        self.assertEqual(record[name], want, (bundle_id, key, name))
                if bundle_id == 'L08':
                    self.assertEqual(outcomes[0][('A', ITEM)][names.index('auto_item_cart_recency_seconds_observed')][1], 21600.0)
                    self.assertEqual(outcomes[0][('B', ITEM)][names.index('auto_item_cart_recency_seconds_observed')][1], 79200.0)

    def test_literal_oracles_reject_candidate_denominator_and_stale_anchor_mutants(self):
        """Two local monkeypatches; never rewrite installed producer source.

        Each mutant still runs the actual compiler. First demonstrate its
        specific legal-but-wrong value, then require the same literal oracle
        used by the metamorphic test to reject it. No expected gate exception
        or schema error substitutes for the intended numerical counterexample.
        """
        with patch.dict(sys.modules, {'catboost': None, 'tsfresh': None}):
            import duckdb
            from scripts import manual_features as compiler
            from scripts.protocol_manifest import load_protocol
            from tests.test_feature_programs_all_bundles_rich import BASE_SCHEMA, C_SCHEMA

            base = compiler.load_registry(ROOT / 'configs/features/manual-18.json')
            config = deepcopy(load_protocol(ROOT / 'configs/protocols/clock-48h.json'))
            config['pilot'] = dict(start='2019-10-10T00:00:00Z', end='2019-10-12T00:00:00Z')
            config['query']['max_users_per_day'] = 3
            config['budget'] = dict(max_anchors=6, max_candidate_pairs=1320)
            schema = list(BASE_SCHEMA)
            names = [name for name, _ in schema]
            original_grain = compiler._grain_sql

            def candidate_conditioned(grain, features, anchor, source_start):
                sql, parameters = original_grain(grain, features, anchor, source_start)
                if grain == 'category':
                    marker = ' WHERE e.event_time>=?'
                    self.assertIn(marker, sql)
                    sql = sql.replace(marker,
                        ' SEMI JOIN manual_day_items fault_item USING(product_id)' + marker, 1)
                return sql, parameters

            with patch.object(compiler, '_grain_sql', side_effect=candidate_conditioned):
                conditioned_whole = self.compile_schedule(base, schema, SCHEDULES[0][1], False,
                                                          config, compiler, duckdb, C_SCHEMA)
                conditioned_singletons = self.compile_schedule(base, schema, SCHEDULES[2][1], True,
                                                               config, compiler, duckdb, C_SCHEMA)
            # Whole A+D includes OUTSIDE's three category100 views, but A's
            # singleton candidate domain contains only ITEM/OTHER/COLD.
            self.assertEqual(conditioned_whole[('A', ITEM)][names.index('category_view_7d')][1], 4)
            self.assertEqual(conditioned_whole[('A', ITEM)][names.index('item_category_view_share_7d')][1], 0.25)
            self.assertEqual(conditioned_singletons[('A', ITEM)][names.index('category_view_7d')][1], 1)
            self.assertEqual(conditioned_singletons[('A', ITEM)][names.index('item_category_view_share_7d')][1], 1.0)
            with self.assertRaises(AssertionError):
                self.assertEqual(conditioned_whole, conditioned_singletons)
            with self.assertRaises(AssertionError):
                self.assert_literal_core(conditioned_singletons, schema)

            original_connect = duckdb.connect

            class KeepFirstMetadata:
                def __init__(self, connection):
                    self.connection = connection
                    self.metadata_seen = False

                def __getattr__(self, name):
                    return getattr(self.connection, name)

                def execute(self, sql, *args, **kwargs):
                    if sql.startswith('CREATE OR REPLACE TEMP TABLE manual_metadata AS'):
                        if self.metadata_seen:
                            # Preserve the first anchor's real TEMP table.
                            return self.connection.execute('SELECT 1')
                        self.metadata_seen = True
                    return self.connection.execute(sql, *args, **kwargs)

            def stale_connect(*args, **kwargs):
                return KeepFirstMetadata(original_connect(*args, **kwargs))

            with patch.object(duckdb, 'connect', side_effect=stale_connect):
                stale = self.compile_schedule(base, schema, SCHEDULES[0][1], False,
                                              config, compiler, duckdb, C_SCHEMA)
            self.assertEqual(stale[('B', ITEM)][names.index('candidate_category_id')][1], 100)
            self.assertEqual(stale[('B', ITEM)][names.index('category_view_7d')][1], 2)
            self.assertEqual(stale[('B', ITEM)][names.index('item_category_view_share_7d')][1], 0.5)
            with self.assertRaises(AssertionError):
                self.assert_literal_core(stale, schema)


if __name__ == '__main__':
    unittest.main()
