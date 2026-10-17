"""Rich, label-free compiler/projection contract; runtime UNRUN at source freeze.

The expected vocabulary, ordered physical schema and row arithmetic are local
specification literals. They do not call producer schema/expression helpers.
This compiler fixture supplies fixed Q/C; it does not claim retrieval lineage.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE_START = datetime(2019, 10, 1)
ANCHOR = datetime(2019, 10, 10)
ITEM = 2**60 + 1
OTHER = ITEM + 1
COLD = ITEM + 2
OLD = ITEM + 3
USER = 101
PEER = 102

# Source tuple: time, action, item, user, historical category.
HISTORY = (
    (SOURCE_START - timedelta(seconds=1), 'cart', ITEM, USER, 100),
    (SOURCE_START, 'cart', OLD, PEER, 200),
    (ANCHOR - timedelta(hours=168), 'purchase', ITEM, USER, 100),
    (ANCHOR - timedelta(hours=168, seconds=1), 'purchase', ITEM, USER, 100),
    (ANCHOR - timedelta(hours=24), 'view', ITEM, USER, 100),
    (ANCHOR - timedelta(hours=24, seconds=1), 'view', ITEM, USER, 100),
    (ANCHOR - timedelta(hours=24), 'cart', ITEM, PEER, 100),
    (ANCHOR - timedelta(hours=24, seconds=1), 'cart', ITEM, PEER, 100),
    (ANCHOR - timedelta(hours=2), 'view', ITEM, USER, 100),
    (ANCHOR - timedelta(hours=2), 'view', ITEM, USER, 100),
    (ANCHOR - timedelta(hours=1), 'purchase', ITEM, USER, 100),
    (ANCHOR - timedelta(minutes=30), 'purchase', OTHER, USER, 200),
    (ANCHOR - timedelta(hours=3), 'purchase', OTHER, PEER, None),
    (ANCHOR - timedelta(hours=4), 'cart', OTHER, USER, 200),
    (ANCHOR - timedelta(hours=5), 'cart', ITEM, USER, 100),
    (ANCHOR - timedelta(hours=6), 'cart', ITEM, None, 100),
    (ANCHOR - timedelta(hours=7), 'view', None, USER, 100),
    (ANCHOR - timedelta(hours=8), 'purchase', None, USER, 100),
    (ANCHOR - timedelta(hours=9), 'view', OTHER, PEER, 200),
    (ANCHOR - timedelta(hours=2), 'view', ITEM, PEER, None),
)
FUTURE_SUFFIX = (
    (ANCHOR, 'cart', ITEM, USER, 999),
    (ANCHOR, 'purchase', ITEM, PEER, 999),
    (ANCHOR + timedelta(hours=1), 'view', OTHER, USER, 999),
)
QUERIES = (('A', USER, ANCHOR, True), ('B', PEER, ANCHOR, True),
           ('C-empty', 103, ANCHOR, True))
CANDIDATES = (
    ('A', ITEM, True, True, 2, 1, 1, ANCHOR - timedelta(hours=1)),
    ('A', OTHER, False, True, 1, None, 2, ANCHOR - timedelta(minutes=30)),
    ('A', COLD, False, False, 0, None, None, None),
    ('B', ITEM, True, True, 2, 1, 1, ANCHOR - timedelta(hours=2)),
    ('B', OLD, False, False, 0, None, None, None),
)
C_SCHEMA = (
    ('query_id', 'VARCHAR'), ('product_id', 'BIGINT'),
    ('from_popular', 'BOOLEAN'), ('from_recent', 'BOOLEAN'),
    ('popularity_distinct_users', 'BIGINT'), ('popular_source_rank', 'BIGINT'),
    ('recent_source_rank', 'BIGINT'), ('last_user_event_time', 'TIMESTAMP'),
)
BASE_SCHEMA = C_SCHEMA + (
    ('user_id', 'BIGINT'), ('anchor', 'TIMESTAMP'),
    ('candidate_category_id', 'BIGINT'),
    ('candidate_category_ambiguous', 'BOOLEAN'), ('candidate_category_missing', 'BOOLEAN'),
    ('item_has_observed_history', 'BOOLEAN'), ('user_has_observed_history', 'BOOLEAN'),
    ('item_observed_age_seconds', 'DOUBLE'), ('user_observed_age_seconds', 'DOUBLE'),
    ('user_view_7d', 'BIGINT'), ('user_cart_7d', 'BIGINT'), ('user_purchase_7d', 'BIGINT'),
    ('user_distinct_viewed_items_7d', 'BIGINT'),
    ('pair_view_7d', 'BIGINT'), ('pair_cart_7d', 'BIGINT'), ('pair_purchase_7d', 'BIGINT'),
    ('pair_view_recency_seconds', 'DOUBLE'), ('pair_purchase_recency_seconds', 'DOUBLE'),
    ('item_view_24h', 'BIGINT'), ('item_purchase_24h', 'BIGINT'),
    ('item_distinct_viewers_7d', 'BIGINT'),
    ('user_category_view_7d', 'BIGINT'), ('user_category_view_recency_seconds', 'DOUBLE'),
    ('item_category_view_7d', 'BIGINT'), ('category_view_7d', 'BIGINT'),
    ('source_coverage_24h', 'DOUBLE'), ('source_coverage_168h', 'DOUBLE'),
    ('user_category_view_share_7d', 'DOUBLE'), ('item_category_view_share_7d', 'DOUBLE'),
    ('pair_view_recency_seconds_missing', 'BOOLEAN'),
    ('pair_purchase_recency_seconds_missing', 'BOOLEAN'),
    ('user_category_view_7d_missing', 'BOOLEAN'),
    ('user_category_view_share_7d_missing', 'BOOLEAN'),
    ('user_category_view_recency_seconds_missing', 'BOOLEAN'),
    ('item_category_view_7d_missing', 'BOOLEAN'), ('category_view_7d_missing', 'BOOLEAN'),
    ('item_category_view_share_7d_missing', 'BOOLEAN'),
)
EXCLUDED = {'query_id', 'user_id', 'product_id', 'anchor',
            'candidate_category_id', 'last_user_event_time'}
BASE_MODEL = tuple(name for name, _ in BASE_SCHEMA if name not in EXCLUDED) + (
    'retrieval_last_event_age_seconds', 'retrieval_last_event_missing')

# Every tuple is (name, physical type, grain, action, operation, hours).
# These are independent specification literals, never generated-program input.
BUNDLES = {
    'L01': tuple((f'auto_user_{a}_count_24h', 'BIGINT', 'user', a, 'count', 24)
                 for a in ('view', 'cart', 'purchase')),
    'L02': tuple((f'auto_pair_{a}_count_24h', 'BIGINT', 'pair', a, 'count', 24)
                 for a in ('view', 'cart', 'purchase')),
    'L03': tuple((f'auto_item_{a}_count_168h', 'BIGINT', 'item', a, 'count', 168)
                 for a in ('view', 'cart', 'purchase')),
    'L04': (
        ('auto_user_view_count_distinct_24h_product_id', 'BIGINT', 'user', 'view', 'distinct', 24),
        ('auto_user_cart_count_distinct_168h_product_id', 'BIGINT', 'user', 'cart', 'distinct', 168),
        ('auto_user_purchase_count_distinct_168h_product_id', 'BIGINT', 'user', 'purchase', 'distinct', 168),
    ),
    'L05': (
        ('auto_item_view_count_distinct_24h_user_id', 'BIGINT', 'item', 'view', 'distinct', 24),
        ('auto_item_cart_count_distinct_168h_user_id', 'BIGINT', 'item', 'cart', 'distinct', 168),
        ('auto_item_purchase_count_distinct_24h_user_id', 'BIGINT', 'item', 'purchase', 'distinct', 24),
    ),
    'L06': (
        ('auto_pair_cart_recency_seconds_observed', 'DOUBLE', 'pair', 'cart', 'recency', None),
        ('auto_item_cart_count_24h', 'BIGINT', 'item', 'cart', 'count', 24),
        ('auto_pair_cart_recency_seconds_observed_missing', 'BOOLEAN', 'pair', 'cart', 'missing', None),
    ),
    'L07': (
        ('auto_user_cart_recency_seconds_observed', 'DOUBLE', 'user', 'cart', 'recency', None),
        ('auto_user_purchase_count_distinct_24h_product_id', 'BIGINT', 'user', 'purchase', 'distinct', 24),
        ('auto_user_cart_recency_seconds_observed_missing', 'BOOLEAN', 'user', 'cart', 'missing', None),
    ),
    'L08': (
        ('auto_item_cart_recency_seconds_observed', 'DOUBLE', 'item', 'cart', 'recency', None),
        ('auto_item_cart_count_distinct_24h_user_id', 'BIGINT', 'item', 'cart', 'distinct', 24),
        ('auto_item_cart_recency_seconds_observed_missing', 'BOOLEAN', 'item', 'cart', 'missing', None),
    ),
}
INSERT_AFTER = {
    'L01': ('user_distinct_viewed_items_7d',),
    'L02': ('pair_purchase_recency_seconds',),
    'L03': ('item_distinct_viewers_7d',),
    'L04': ('user_distinct_viewed_items_7d',),
    'L05': ('item_distinct_viewers_7d',),
    'L06': ('pair_purchase_recency_seconds', 'item_distinct_viewers_7d'),
    'L07': ('user_distinct_viewed_items_7d',),
    'L08': ('item_distinct_viewers_7d',),
}
# Literal first-row values corroborate the independent row-list interpreter.
FIRST_ROW_GOLD = {
    'L01': (4, 2, 3), 'L02': (3, 1, 1), 'L03': (5, 4, 2),
    'L04': (1, 2, 2), 'L05': (2, 2, 1),
    'L06': (18000.0, 3, False), 'L07': (14400.0, 2, False),
    'L08': (18000.0, 2, False),
}


def bundle_schema(bundle_id):
    """Literal ordinal insertion rules independent of any producer schema helper."""
    delta = [(spec[0], spec[1]) for spec in BUNDLES[bundle_id]]
    out = list(BASE_SCHEMA)
    if bundle_id == 'L06':
        for anchor, field in zip(INSERT_AFTER[bundle_id], delta[:2]):
            out.insert(next(i for i, pair in enumerate(out) if pair[0] == anchor) + 1, field)
        out.append(delta[2])
    else:
        anchor = INSERT_AFTER[bundle_id][0]
        position = next(i for i, pair in enumerate(out) if pair[0] == anchor) + 1
        additions = delta[:2] if bundle_id in {'L07', 'L08'} else delta
        out[position:position] = additions
        if bundle_id in {'L07', 'L08'}:
            out.append(delta[2])
    return out


def reference_value(records, user, item, spec):
    """Raw-row/set arithmetic; spec comes only from BUNDLES above."""
    _, _, grain, action, operation, hours = spec
    matches = []
    for stamp, kind, product, person, _ in records:
        if not SOURCE_START <= stamp < ANCHOR or kind != action:
            continue
        if grain in {'user', 'pair'} and person != user:
            continue
        if grain in {'item', 'pair'} and product != item:
            continue
        if hours is not None and stamp < ANCHOR - timedelta(hours=hours):
            continue
        matches.append((stamp, product, person))
    if operation == 'count':
        return len(matches)
    if operation == 'distinct':
        position = 1 if grain == 'user' else 2
        return len({row[position] for row in matches if row[position] is not None})
    if operation == 'missing':
        return not matches
    return (ANCHOR - max(row[0] for row in matches)).total_seconds() if matches else None


def reference_base(records, candidate):
    """Independent full B45 row, plus the two named loader coordinates."""
    qid, item = candidate[:2]
    user = USER if qid == 'A' else PEER
    past = [r for r in records if SOURCE_START <= r[0] < ANCHOR]
    recent = [r for r in past if r[0] >= ANCHOR - timedelta(days=7)]
    ih = [r for r in past if r[2] == item]
    uh = [r for r in past if r[3] == user]
    latest = max((r[0] for r in ih), default=None)
    categories = {r[4] for r in ih if r[0] == latest}
    category = next(iter(categories)) if len(categories) == 1 and None not in categories else None
    count = lambda rows, kind: sum(r[1] == kind for r in rows)
    def age(rows, kind=None):
        stamp = max((r[0] for r in rows if kind is None or r[1] == kind), default=None)
        return (ANCHOR - stamp).total_seconds() if stamp is not None else None
    ur = [r for r in recent if r[3] == user]
    pr = [r for r in ur if r[2] == item]
    ph = [r for r in uh if r[2] == item]
    i24 = [r for r in ih if r[0] >= ANCHOR - timedelta(days=1)]
    uc = [r for r in recent if r[3] == user and r[4] == category]
    ic = [r for r in recent if r[2] == item and r[4] == category]
    cc = [r for r in recent if r[4] == category]
    values = dict(zip((name for name, _ in C_SCHEMA), candidate))
    values.update(user_id=user, anchor=ANCHOR, candidate_category_id=category,
                  candidate_category_ambiguous=len(categories) > 1,
                  candidate_category_missing=category is None,
                  item_has_observed_history=bool(ih), user_has_observed_history=bool(uh),
                  item_observed_age_seconds=(ANCHOR - min(r[0] for r in ih)).total_seconds() if ih else None,
                  user_observed_age_seconds=(ANCHOR - min(r[0] for r in uh)).total_seconds() if uh else None)
    for kind in ('view', 'cart', 'purchase'):
        values['user_' + kind + '_7d'] = count(ur, kind)
        values['pair_' + kind + '_7d'] = count(pr, kind)
    values.update(user_distinct_viewed_items_7d=len({r[2] for r in ur if r[1] == 'view' and r[2] is not None}),
                  pair_view_recency_seconds=age(ph, 'view'), pair_purchase_recency_seconds=age(ph, 'purchase'),
                  item_view_24h=count(i24, 'view'), item_purchase_24h=count(i24, 'purchase'),
                  item_distinct_viewers_7d=len({r[3] for r in recent if r[2] == item and r[1] == 'view' and r[3] is not None}),
                  user_category_view_7d=count(uc, 'view') if category is not None else None,
                  user_category_view_recency_seconds=age([r for r in past if r[3] == user and r[4] == category], 'view') if category is not None else None,
                  item_category_view_7d=count(ic, 'view') if category is not None else None,
                  category_view_7d=count(cc, 'view') if category is not None else None,
                  user_category_view_share_7d=count(uc, 'view') / count(ur, 'view') if category is not None and count(ur, 'view') else None,
                  item_category_view_share_7d=count(ic, 'view') / count(cc, 'view') if category is not None and count(cc, 'view') else None,
                  source_coverage_24h=1.0, source_coverage_168h=1.0)
    for name, kind in BASE_SCHEMA:
        if kind == 'BOOLEAN' and name.endswith('_missing') and name[:-8] in values:
            values[name] = values[name[:-8]] is None
    values['retrieval_last_event_age_seconds'] = ((ANCHOR - candidate[-1]).total_seconds()
                                                  if candidate[-1] is not None else None)
    values['retrieval_last_event_missing'] = candidate[-1] is None
    return values


class AllEightRichProgramsTests(unittest.TestCase):
    def assert_scalar(self, actual, expected, label):
        if type(expected) is float:
            self.assertIs(type(actual), float, label)
            self.assertAlmostEqual(actual, expected, delta=1e-9, msg=label)
        else:
            self.assertIs(type(actual), type(expected), label)
            self.assertEqual(actual, expected, label)

    def exercise(self, records, root, config, base, pool, compiler, inference, duckdb, np):
        self.assertLessEqual(len(records) + len(QUERIES) + len(CANDIDATES), 32)
        con = duckdb.connect(':memory:', config={'threads': '2', 'memory_limit': '128MB',
                                                 'max_temp_directory_size': '0B'})
        try:
            con.execute('CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)')
            con.executemany('INSERT INTO events VALUES (?,?,?,?,?)', records)
            con.execute('CREATE TABLE pilot_queries(query_id VARCHAR,user_id BIGINT,anchor TIMESTAMP,label_is_mature BOOLEAN)')
            con.executemany('INSERT INTO pilot_queries VALUES (?,?,?,?)', QUERIES)
            con.execute('CREATE TABLE pilot_candidates(' + ','.join(name + ' ' + kind for name, kind in C_SCHEMA) + ')')
            con.executemany('INSERT INTO pilot_candidates VALUES (?,?,?,?,?,?,?,?)', CANDIDATES)
            compiler.create_manual_features(con, config, base)
            schema = [tuple(row[:2]) for row in con.execute('DESCRIBE manual_features').fetchall()]
            self.assertEqual(schema, list(BASE_SCHEMA))
            expected = {(c[0], c[1]): reference_base(records, c) for c in CANDIDATES}
            ordered_keys = [(c[0], c[1]) for c in CANDIDATES]
            baseline_rows = con.execute('SELECT * FROM manual_features ORDER BY query_id,product_id').fetchall()
            for row in baseline_rows:
                values = dict(zip((name for name, _ in BASE_SCHEMA), row))
                for name, _ in BASE_SCHEMA:
                    self.assert_scalar(values[name], expected[row[:2]][name], 'B:' + name)
            con.execute('CREATE TABLE fixed_base AS SELECT * FROM manual_features')
            con.execute('COPY fixed_base TO ? (FORMAT PARQUET)', [str(root / 'base.parquet')])
            con.execute('COPY pilot_queries TO ? (FORMAT PARQUET)', [str(root / 'q.parquet')])
            gold_base = np.asarray([[np.nan if expected[key][name] is None else expected[key][name]
                                     for name in BASE_MODEL] for key in ordered_keys], dtype=np.float32)
            with patch.object(inference, 'ROOT', root):
                control = inference.load_inference_data(['q.parquet'], ['base.parquet'],
                    expected_feature_names=list(BASE_MODEL), max_queries=3, max_rows=5, matrix_byte_cap=65536)
                np.testing.assert_array_equal(control.x, gold_base)
                self.assertEqual(control.feature_names, list(BASE_MODEL))
                self.assertEqual(control.group.dtype, np.dtype('int32'))
                self.assertEqual(control.items.dtype, np.dtype('int64'))
                self.assertEqual(control.x.dtype, np.dtype('float32'))
                self.assertEqual(control.group.tolist(), [0, 0, 0, 1, 1])
                self.assertEqual(control.items.tolist(), [ITEM, OTHER, COLD, ITEM, OLD])
                self.assertEqual(control.queries, [q[:3] for q in QUERIES])
                outcomes = {}
                self.assertEqual([b['bundle_id'] for b in pool['identity']['bundles']], list(BUNDLES))
                for bundle in pool['identity']['bundles']:
                    bundle_id = bundle['bundle_id']
                    specs = BUNDLES[bundle_id]
                    delta = [(spec[0], spec[1]) for spec in specs]
                    names = [name for name, _ in delta]
                    self.assertEqual(bundle['physical_delta'], [dict(name=n, dtype=t) for n, t in delta])
                    self.assertEqual(bundle['model_feature_order'], list(BASE_MODEL) + names)
                    compiler.create_manual_features(con, config, bundle['registry'])
                    physical = [tuple(row[:2]) for row in con.execute('DESCRIBE manual_features').fetchall()]
                    self.assertEqual(physical, bundle_schema(bundle_id))
                    fields = ','.join('"' + name + '"' for name, _ in BASE_SCHEMA)
                    self.assertEqual(con.execute('SELECT ' + fields + ' FROM manual_features ORDER BY query_id,product_id').fetchall(), baseline_rows)
                    produced = con.execute('SELECT query_id,product_id,' + ','.join('"' + n + '"' for n in names) +
                                           ' FROM manual_features ORDER BY query_id,product_id').fetchall()
                    gold_extra = []
                    for row, candidate in zip(produced, CANDIDATES):
                        self.assertEqual(row[:2], candidate[:2])
                        user = USER if row[0] == 'A' else PEER
                        values = [reference_value(records, user, row[1], spec) for spec in specs]
                        for name, actual, want in zip(names, row[2:], values):
                            self.assert_scalar(actual, want, bundle_id + ':' + name)
                        gold_extra.append(values)
                    # L03 purchase->cart substitution yields 4 instead of 2.
                    # The independently literal first-row gold also checks the
                    # row-list interpreter on every generated bundle.
                    self.assertEqual(produced[0][2:], FIRST_ROW_GOLD[bundle_id])
                    if bundle_id == 'L08':
                        self.assertEqual(produced[-1][2:], (777600.0, 0, False))
                    extra_path = root / (bundle_id + '.parquet')
                    con.execute('COPY (SELECT query_id,product_id,' + ','.join('"' + n + '"' for n in names) +
                                ' FROM manual_features) TO ? (FORMAT PARQUET)', [str(extra_path)])
                    projected = inference.load_inference_data(['q.parquet'], ['base.parquet'],
                        expected_feature_names=list(BASE_MODEL) + names, extra_feature_paths=[extra_path.name],
                        extra_feature_names=names, max_queries=3, max_rows=5, matrix_byte_cap=65536)
                    self.assertEqual(projected.feature_names, list(BASE_MODEL) + names)
                    self.assertEqual(projected.x.dtype, np.dtype('float32'))
                    self.assertEqual(projected.queries, control.queries)
                    np.testing.assert_array_equal(projected.group, control.group)
                    np.testing.assert_array_equal(projected.items, control.items)
                    np.testing.assert_array_equal(projected.x[:, :41], gold_base)
                    np.testing.assert_array_equal(projected.x[:, 41:],
                        np.asarray([[np.nan if v is None else v for v in row] for row in gold_extra], dtype=np.float32))
                    self.assertEqual(projected.preparation['outcome_relations_opened'], 0)
                    outcomes[bundle_id] = projected.x.copy()
                self.assertFalse({row[0] for row in con.execute('SHOW TABLES').fetchall()} &
                                 {'pilot_labels', 'all_labels', 'chosen_labels'})
                return control.x.copy(), outcomes
        finally:
            con.close()

    def test_all_eight_rich_literal_values_types_order_and_label_free_projection(self):
        # No model/backend capability is needed by the actual compiler/loaders.
        with patch.dict(sys.modules, {'catboost': None, 'tsfresh': None}):
            import duckdb
            import numpy as np
            from scripts import manual_features as compiler
            from scripts import feature_programs as programs
            from scripts import inference_data as inference
            from scripts.protocol_manifest import load_protocol

            base = compiler.load_registry(ROOT / 'configs/features/manual-18.json')
            contract = json.loads((ROOT / 'configs/features/automation-pool.json').read_text())
            pool = programs.generate_pool(contract, base)
            config = deepcopy(load_protocol(ROOT / 'configs/protocols/clock-48h.json'))
            config['pilot'] = dict(start='2019-10-10T00:00:00Z', end='2019-10-11T00:00:00Z')
            config['query']['max_users_per_day'] = 3
            config['budget'] = dict(max_anchors=3, max_candidate_pairs=660)
            self.assertEqual(len(BASE_SCHEMA), 45)
            self.assertEqual(len(BASE_MODEL), 41)
            with tempfile.TemporaryDirectory(prefix='all-eight-rich-') as tmp:
                root = Path(tmp)
                before = root / 'before'; before.mkdir()
                after = root / 'after'; after.mkdir()
                initial, bundles_initial = self.exercise(HISTORY, before, config, base, pool, compiler, inference, duckdb, np)
                permuted, bundles_permuted = self.exercise(tuple(reversed(HISTORY + FUTURE_SUFFIX)), after,
                    config, base, pool, compiler, inference, duckdb, np)
                np.testing.assert_array_equal(initial, permuted)
                for bundle_id in BUNDLES:
                    np.testing.assert_array_equal(bundles_initial[bundle_id], bundles_permuted[bundle_id])


if __name__ == '__main__':
    unittest.main()
