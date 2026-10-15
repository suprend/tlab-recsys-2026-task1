"""Small invented-event integration; no source archive or native ML operation."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import reproduce_frozen_comparison as r

ROOT = Path(__file__).resolve().parents[1]


class PublicFrozenComparisonTests(unittest.TestCase):
    def setUp(self):
        global duckdb, np, b, historical, evaluate
        import duckdb
        import numpy as np
        from scripts import train_baselines as b
        from scripts import model_data as historical
        from scripts.ranking_metrics import evaluate
        self.recipe = json.loads((ROOT / 'configs/reproduction/frozen-bw-oct2019.json').read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.con = duckdb.connect(':memory:', config={'threads': '2', 'memory_limit': '128MB',
                                                     'max_temp_directory_size': '0B'})
        self.addCleanup(self.con.close)
        self.con.execute('''CREATE TABLE events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,
            category_id BIGINT,category_code VARCHAR,brand VARCHAR,price DECIMAL(12,2),user_id BIGINT,user_session VARCHAR)''')
        t = datetime(2019, 10, 8)
        self.events = [
            (t-timedelta(hours=4), 'view', 10, 100, 1),
            (t-timedelta(hours=3), 'cart', 10, 100, 1),
            (t-timedelta(hours=2), 'purchase', 10, 100, 1),
            (t-timedelta(hours=3), 'view', 20, 200, 2),
            (t-timedelta(hours=2), 'purchase', 20, 200, 2),
            (t, 'view', 10, 555, 1),  # Same-time category update cannot enter Oct8 features.
            (t, 'purchase', 99, 900, 1),  # FullY off-C and off past catalog.
            (t, 'purchase', 10, None, 3),  # Global peer/new user cannot enter Oct8 history.
            (t+timedelta(hours=1), 'purchase', 10, 100, 1),
            (t+timedelta(hours=2), 'view', 20, 200, 2),
            (t+timedelta(hours=3), 'purchase', 20, 200, 2),
            (t+timedelta(hours=23), 'view', 40, 400, 4),
            (t+timedelta(days=1), 'purchase', 999, 999, 1),
            (t+timedelta(days=1), 'view', 1000, 1000, 2),
        ]
        self.assertLessEqual(len(self.events), 32)
        self.con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',
            [(time, action, item, category, None, None, None, user, None)
             for time, action, item, category, user in self.events])

    def config(self, day):
        config = r.day_protocol(self.recipe, day.replace(tzinfo=r.UTC))
        config['query']['max_users_per_day'] = 4
        config['budget'] = dict(max_anchors=4, max_candidate_pairs=880)
        return config

    def build(self, day, name):
        return r.build_day(self.con, self.config(day), self.recipe, self.root / name, lambda: None)

    def seal_fixture(self, files, name):
        # A distinct explicit synthetic input, never adoption of a changed production export.
        refs = {kind: dict(path=Path(files[kind]).name, **r.file_ref(files[kind], lambda: None))
                for kind in ('queries', 'candidates', 'base', 'extra', 'labels')}
        manifest = self.root / (name + '-manifest.json')
        r.write_new(manifest, dict(files=refs))
        return {**files, '_refs': refs, '_manifest': dict(path=manifest, witness=r.file_ref(manifest, lambda: None))}

    def prepare(self, files, arm='B', **kwargs):
        options = dict(max_queries=None, max_rows=64, check=lambda: None)
        options.update(kwargs)
        return r.prepare_matrix(files, self.recipe, arm, **options)

    def test_lower_cores_preserve_off_candidate_fullY_and_exclude_global_future_peers(self):
        first = self.build(datetime(2019, 10, 8), 'first')
        data = self.prepare([first])
        self.assertEqual(len(data.queries), 2)
        self.assertEqual({q[1] for q in data.queries}, {1, 2})
        one = next(q for q in data.queries if q[1] == 1)
        self.assertEqual(one[3], {99, 10})
        self.assertNotIn(99, data.items)
        metadata = self.con.execute('SELECT DISTINCT candidate_category_id,candidate_category_ambiguous '
                                    'FROM read_parquet(?) WHERE product_id=10', [str(first['base'])]).fetchall()
        self.assertEqual(metadata, [(100, False)])
        self.assertEqual(data.x.dtype, np.float32)
        self.assertTrue(np.isnan(data.x[:, data.feature_names.index('pair_purchase_recency_seconds')]).any())
        self.assertEqual(data.items.dtype, np.int64)
        self.assertEqual(data.group.dtype, np.int32)
        row = (data.group == data.queries.index(one)) & (data.items == 10)
        self.assertEqual(float(data.x[row, data.feature_names.index('user_view_7d')][0]), 1)
        w = self.prepare([first], 'W')
        self.assertTrue(np.all(w.x[w.items == 10, -1] == 1))  # Same-time other-user purchase is excluded.
        metrics = evaluate(b.rankings(data, np.zeros(len(data.items))), 20)
        self.assertLess(metrics.conditional_macro_query.recall, 1.0)  # off-C denominator retained.
        manifest = json.loads((first['queries'].parent / 'manifest.json').read_text())
        self.assertTrue(manifest['label_blind_Q_C_F_frozen_before_Y'])

    def test_two_day_global_matrix_matches_actual_historical_loader_and_named_W_projection(self):
        files = [self.build(datetime(2019, 10, 8), 'd8'), self.build(datetime(2019, 10, 9), 'd9')]
        current = self.prepare(list(reversed(files)))
        self.assertEqual(len(current.queries), 6)
        self.assertLessEqual(len(current.queries), 8)
        self.assertLessEqual(len(current.items), 64)
        refs = {kind: [str(row[kind].relative_to(self.root)) for row in files]
                for kind in ('queries', 'labels')}
        refs['features'] = [str(row['base'].relative_to(self.root)) for row in files]
        collection = dict(phase=dict(role='train'), refs=refs, feature_columns=self.recipe['base_physical_columns'])
        # Existing test convention: scope the historical loader's public root only
        # to synthetic exports, then compare its actual canonical transport.
        with patch.object(historical, 'ROOT', self.root):
            old = historical.prepare_model_data(collection, max_queries=6, max_rows=64)
        self.assertEqual(current.queries, old.queries)
        for name in ('group', 'items', 'y', 'x'):
            np.testing.assert_array_equal(getattr(current, name), getattr(old, name))
        self.assertEqual([q[0] for q in current.queries], sorted(q[0] for q in current.queries))
        w = self.prepare(files, 'W')
        self.assertEqual(w.queries, current.queries)
        for name in ('group', 'items', 'y'):
            np.testing.assert_array_equal(getattr(current, name), getattr(w, name))
        np.testing.assert_array_equal(w.x[:, :41], current.x)
        self.assertEqual(w.feature_names[41:], self.recipe['extra_feature_names'])
        self.assertEqual(w.x.shape[1], 44)
        self.assertEqual(b.group_accounting(w)[4].tolist(), b.group_accounting(current)[4].tolist())

    def test_label_changes_cannot_resample_queries_or_candidates_and_caps_precede_allocation(self):
        files = self.build(datetime(2019, 10, 8), 'day')
        before = self.prepare([files], max_queries=1)
        replacement = self.root / 'changed-labels.parquet'
        self.con.execute("COPY (SELECT query_id,123456::BIGINT product_id FROM pilot_queries) TO ? (FORMAT PARQUET)", [str(replacement)])
        changed = self.seal_fixture(dict(files, labels=replacement), 'changed-label-fixture')
        after = self.prepare([changed], max_queries=1)
        self.assertEqual([q[:3] for q in before.queries], [q[:3] for q in after.queries])
        for name in ('items', 'group', 'x'):
            np.testing.assert_array_equal(getattr(before, name), getattr(after, name))
        self.assertEqual(after.queries[0][3], {123456})
        with patch.object(np, 'empty', side_effect=AssertionError('Premature allocation')):
            with self.assertRaisesRegex(ValueError, 'before allocation'):
                self.prepare([files], max_rows=0)
            with self.assertRaisesRegex(MemoryError, 'before allocation'):
                self.prepare([files], matrix_byte_cap=1)

    def test_empty_negative_positive_query_groups_keep_unit_mass_and_fullY(self):
        prepared = b.Prepared([('empty', 1, datetime(2019, 10, 8), frozenset({999})),
            ('negative', 2, datetime(2019, 10, 8), frozenset()),
            ('positive', 3, datetime(2019, 10, 8), frozenset({20}))],
            np.array([1, 1, 2], np.int32), np.array([10, 11, 20], np.int64),
            np.zeros((3, 1), np.float32), np.array([0, 0, 1], np.int8), ['feature'])
        counts, _, _, informative, weights, report = b.group_accounting(prepared)
        self.assertEqual(counts.tolist(), [0, 2, 1])
        self.assertEqual(weights.tolist(), [.5, .5, 1.])
        self.assertEqual(informative.tolist(), [False, False, False])
        self.assertEqual(report['empty_candidate_groups'], 1)
        self.assertEqual(report['all_negative_groups'], 1)
        self.assertEqual(report['all_positive_groups'], 1)
        ranked = b.rankings(prepared, [0, 0, 0])
        self.assertEqual(ranked[0].ranked_items, ())
        self.assertEqual(ranked[0].targets, {999})
        # Exercise actual empty-C physical transport without inventing candidates/labels.
        files = self.build(datetime(2019, 10, 8), 'empty-transport')
        for kind in ('base', 'extra', 'candidates'):
            path = self.root / ('empty-' + kind + '.parquet')
            self.con.read_parquet(str(files[kind])).create_view('empty_fixture_source', replace=True)
            self.con.execute('COPY (SELECT * FROM empty_fixture_source WHERE false) TO ? (FORMAT PARQUET)',
                             [str(path)])
            files[kind] = path
        files = self.seal_fixture(files, 'empty-candidate-fixture')
        empty = self.prepare([files])
        self.assertEqual(len(empty.queries), 2)
        self.assertEqual(len(empty.items), 0)
        self.assertTrue(any(99 in q[3] for q in empty.queries))
        self.assertEqual(r.matrix_identity(empty, lambda: None)['x']['shape'], [0, 41])

    def test_calendar_maturity_is_outcome_independent_and_includes_full_horizon_end(self):
        self.con.execute('CREATE TEMP TABLE pilot_queries(query_id VARCHAR,anchor TIMESTAMP,label_is_mature BOOLEAN)')
        self.con.execute("INSERT INTO pilot_queries VALUES ('early','2019-10-08',NULL),('late','2019-10-09',NULL)")
        config = self.config(datetime(2019, 10, 8))
        config['source']['end'] = '2019-10-09T00:00:00Z'
        r.calendar_maturity(self.con, config)
        self.assertEqual(self.con.execute('SELECT query_id,label_is_mature FROM pilot_queries ORDER BY query_id').fetchall(),
                         [('early', True), ('late', False)])

    def test_fresh_two_fit_backend_has_no_private_model_input_or_selection_fit_and_stops_after_failure(self):
        files = [self.build(datetime(2019, 10, 8), 'data')]
        recipe = deepcopy(self.recipe)
        recipe['periods']['train']['queries'] = recipe['periods']['selection']['queries'] = 2
        events, saved = [], {}
        class FakePool:
            def __init__(self, x, **kwargs):
                self.names = kwargs['feature_names']
                assert kwargs['thread_count'] == 2 and 'group_id' not in kwargs
                events.append(('pool', list(self.names), list(kwargs['weight'])))
        class FakeModel:
            fail = False
            def __init__(self, **params):
                self.params = params
            def fit(self, pool, **kwargs):
                events.append(('fit', self.params, set(kwargs)))
                if self.fail:
                    raise RuntimeError('Invented native fit failure')
                self.feature_names_ = pool.names
                self.tree_count_ = 300
            def get_all_params(self):
                return recipe['effective_parameters']
            def get_cat_feature_indices(self): return []
            def get_text_feature_indices(self): return []
            def get_embedding_feature_indices(self): return []
            def save_model(self, path, **kwargs):
                saved[path] = (list(self.feature_names_), self.tree_count_)
                Path(path).write_bytes(b'invented fake model, not CatBoost')
            def load_model(self, path, **kwargs):
                self.feature_names_, self.tree_count_ = saved[path]
                events.append(('load', Path(path).name))
            def predict(self, x, **kwargs):
                events.append(('predict', kwargs))
                return np.zeros(len(x), np.float64)
        good = self.root / 'good'; good.mkdir()
        budget = r.Budget(60, 120, 512 * 2**20, 8 * 2**30)
        result = r.compare_two(files, files, recipe, good, budget, backend=(FakeModel, FakePool))
        self.assertEqual(budget.fit_attempts, 2)
        self.assertEqual([event[0] for event in events].count('fit'), 2)
        self.assertEqual([event[0] for event in events].count('predict'), 2)
        self.assertTrue(result['post_selection_reproduction'])
        self.assertTrue(all(event[2] == {'callbacks'} for event in events if event[0] == 'fit'))
        self.assertTrue(all(event[1]['iterations'] == 300 for event in events if event[0] == 'fit'))
        self.assertEqual({event[1] for event in events if event[0] == 'load'}, {'B.cbm', 'W.cbm'})
        with self.assertRaisesRegex(ValueError, 'cap exhausted'):
            budget.reserve_fit()
        events.clear(); FakeModel.fail = True
        bad = self.root / 'bad'; bad.mkdir()
        budget2 = r.Budget(60, 120, 512 * 2**20, 8 * 2**30)
        with self.assertRaisesRegex(RuntimeError, 'Invented native fit failure'):
            r.compare_two(files, files, recipe, bad, budget2, backend=(FakeModel, FakePool))
        self.assertEqual(budget2.fit_attempts, 1)
        self.assertTrue((bad / 'B.fit-consumed.json').exists())
        self.assertFalse((bad / 'W.fit-consumed.json').exists())
        self.assertEqual([event[0] for event in events].count('fit'), 1)

    def test_once_failure_is_retained_and_production_recipe_cannot_use_fixture_profile(self):
        self.assertEqual(r.validate_recipe(ROOT / 'configs/reproduction/frozen-bw-oct2019.json', lambda: None)[0], self.recipe)
        output = self.root / 'fresh-public-output'
        budget = r.Budget(60, 120, 512 * 2**20, 8 * 2**30)
        # No raw read: authentication fails before import, and attempt is retained.
        changed = self.root / 'changed-recipe.json'
        altered = deepcopy(self.recipe)
        altered['source']['scope'] = 'synthetic_typed9_import_fixture'
        changed.write_text(json.dumps(altered))
        with self.assertRaisesRegex(ValueError, 'exact frozen'):
            r.run(self.root / 'does-not-exist.gz', output, changed, budget)
        self.assertTrue((output / 'consumed.json').exists())
        self.assertTrue((output / 'failed.json').exists())
        with self.assertRaisesRegex(ValueError, 'Fresh output'):
            r.run(self.root / 'does-not-exist.gz', output, changed, budget)
        self.assertFalse((output / 'source').exists())




# Stdlib-only fault regressions. Native imports above live only in the separate
# invented-event fixture's setUp; this class runs without those dependencies.
import ast
from array import array
import hashlib
import inspect
import math
import struct
import sys
from types import ModuleType, SimpleNamespace


def pure_body(name, **overrides):
    """Execute the actual function AST, replacing ONLY native import capabilities."""
    node = ast.parse(inspect.getsource(getattr(r, name)))
    class NoImports(ast.NodeTransformer):
        def visit_Import(self, node): return ast.copy_location(ast.Pass(), node)
        def visit_ImportFrom(self, node): return ast.copy_location(ast.Pass(), node)
    node = ast.fix_missing_locations(NoImports().visit(node))
    namespace = dict(r.__dict__, **overrides)
    exec(compile(node, '<actual-function-native-imports-stubbed>', 'exec'), namespace)
    return namespace[name]


class FakeMask:
    def __init__(self, values): self.values = values
    def tobytes(self, order='C'): return bytes(self.values)


class FakeFloatBlock:
    def __init__(self, rows): self.values = array('f', (value for row in rows for value in row))
    def __setitem__(self, mask, value):
        for i, missing in enumerate(mask.values):
            if missing: self.values[i] = value
    def tobytes(self, order='C'): return self.values.tobytes()


class FakeMatrix:
    dtype = 'float32'
    def __init__(self, rows):
        self.rows, self.shape = rows, (len(rows), len(rows[0]) if rows else 41)
    def __len__(self): return len(self.rows)
    def __getitem__(self, key):
        row_slice, columns = key
        return [row[columns] for row in self.rows[row_slice]]


class FakeVector:
    def __init__(self, values): self.values = values
    def __len__(self): return len(self.values)
    def __eq__(self, value): return [v == value for v in self.values]


class PublicFrozenBindingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def exports(self, name='fixture', *, directory=None):
        directory = self.root / name if directory is None else directory
        directory.mkdir()
        files = {kind: directory / (kind + '.parquet') for kind in ('queries', 'candidates', 'base', 'extra', 'labels')}
        for kind, path in files.items(): path.write_bytes(('invented artifact ' + kind).encode())
        refs = {kind: dict(path=path.name, **r.file_ref(path, lambda: None)) for kind, path in files.items()}
        manifest = directory / 'manifest.json'
        r.write_new(manifest, dict(files=refs))
        return dict(files, _refs=refs, _manifest=dict(path=manifest, witness=r.file_ref(manifest, lambda: None)))

    def identity(self, base='same'):
        return dict(queries_sha256='q', group='g', items='i', y='y', weights='w', base41=base)

    def test_recipe_hash_parse_and_persistence_share_one_bounded_snapshot(self):
        recipe = dict(k=20, environment=dict(python_major_minor=list(sys.version_info[:2]), packages={}))
        raw = json.dumps(recipe).encode(); path = self.root / 'recipe.json'; path.write_bytes(raw)
        expected = hashlib.sha256(raw).hexdigest(); calls = []
        original = r.snapshot_file
        def change_after_snapshot(path, check, **kwargs):
            result = original(path, check, **kwargs); calls.append(str(path))
            Path(path).write_text(json.dumps(dict(recipe, k=1)))
            return result
        with patch.object(r, 'RECIPE_SHA256', expected), patch.object(r, 'snapshot_file', change_after_snapshot):
            parsed, authenticated, witness = r.validate_recipe(path, lambda: None)
        self.assertEqual(parsed['k'], 20)
        self.assertEqual(authenticated, raw)
        self.assertEqual(calls, [str(path)])
        copy = self.root / 'owned.json'; r.write_snapshot(copy, authenticated, witness, lambda: None)
        self.assertEqual(copy.read_bytes(), raw)
        self.assertEqual(json.loads(path.read_bytes())['k'], 1)
        with self.assertRaisesRegex(ValueError, 'snapshot exceeded'):
            r.snapshot_file(path, lambda: None, maximum=1)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            r.parse_json(b'{"k":20,"k":1}')

    def test_original_export_and_manifest_pins_reject_changes_before_loader_and_after_reads(self):
        files = self.exports()
        r.verify_exports([files], lambda: None)
        before = files['base'].read_bytes(); files['base'].write_bytes(b'manual feature changed')
        with self.assertRaisesRegex(ValueError, 'Original consumed export'):
            r.prepare_matrix([files], {}, 'W', max_queries=None, max_rows=1, check=lambda: None)
        # Above must fail before even attempting the native imports in the loader.
        with self.assertRaisesRegex(ValueError, 'Original consumed export'):
            r.repin_exports_preserving([files], lambda: None, None)
        primary = KeyboardInterrupt('reader interrupted')
        r.repin_exports_preserving([files], lambda: None, primary)
        self.assertIn('Export repin: ValueError', primary.__notes__)
        files['base'].write_bytes(before)
        body = json.loads(files['_manifest']['path'].read_bytes())
        body['files']['base']['sha256'] = '0' * 64
        files['_manifest']['path'].write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError, 'Original export manifest'):
            r.verify_exports([files], lambda: None)

    def test_shared_B41_chunks_bind_values_and_NaN_masks_without_full_matrix_copy(self):
        copied = []
        def copy(rows, **kwargs):
            self.assertEqual(kwargs, dict(dtype='float32', copy=True, order='C'))
            copied.append(len(rows)); return FakeFloatBlock(rows)
        fake = SimpleNamespace(float32='float32', array=copy,
                               isnan=lambda block: FakeMask([math.isnan(x) for x in block.values]))
        witness = pure_body('shared_base_identity', np=fake)
        rows = [[float(i % 3)] * 41 for i in range(4097)]; rows[2][3] = float('nan')
        base = witness(SimpleNamespace(x=FakeMatrix(rows)), lambda: None)
        expanded = [row[:] + [77., 88., 99.] for row in rows]
        same = witness(SimpleNamespace(x=FakeMatrix(expanded)), lambda: None)
        self.assertEqual(base, same)
        self.assertEqual(max(copied), 4096)
        self.assertGreater(len(copied), 2)
        self.assertTrue(math.isnan(rows[2][3]))  # only a bounded copied block is normalized.
        expanded[1][12] = 99.
        changed = witness(SimpleNamespace(x=FakeMatrix(expanded)), lambda: None)
        with self.assertRaisesRegex(ValueError, 'base41'):
            r.require_shared_base(self.identity(changed), self.identity(base), 'train')
        expanded[1][12] = rows[1][12]; expanded[2][3] = 0.
        missing = witness(SimpleNamespace(x=FakeMatrix(expanded)), lambda: None)
        self.assertEqual(base['values_sha256'], missing['values_sha256'])
        self.assertNotEqual(base['missing_sha256'], missing['missing_sha256'])
        with self.assertRaisesRegex(ValueError, 'base41'):
            r.require_shared_base(self.identity(missing), self.identity(base), 'selection')

    def test_W_train_guard_precedes_Pool_and_selection_guard_precedes_prediction(self):
        class StopPrediction(Exception): pass
        for phase in ('train', 'selection', 'unchanged'):
            with self.subTest(phase=phase):
                directory = self.root / phase; directory.mkdir(); events = []
                train = SimpleNamespace(queries=[1, 2], group=FakeVector([0, 1]), items=FakeVector([10, 20]),
                                        y=FakeVector([0, 1]), x=FakeMatrix([[0.] * 44] * 2), feature_names=['f'] * 44)
                selection = SimpleNamespace(queries=[1, 2], x=train.x)
                baseline = dict(train=self.identity(), selection=self.identity())
                def identity(data, check):
                    which = 'train' if data is train else 'selection'
                    return self.identity('changed' if phase == which else 'same')
                class Pool:
                    def __init__(self, x, **kwargs):
                        self_test.assertEqual(kwargs['thread_count'], 2)
                        self_test.assertNotIn('group_id', kwargs)
                        events.append('pool')
                class Model:
                    feature_names_ = ['f'] * 44
                    def __init__(self, **kwargs): pass
                    def fit(self, *args, **kwargs): events.append('fit')
                    def save_model(self, path, **kwargs): Path(path).write_bytes(b'fake model, not native')
                    def load_model(self, *args, **kwargs): events.append('load')
                    def get_all_params(self): return {}
                class Callback:
                    def __init__(self, check): self.failure = None
                def predict(*args):
                    events.append('predict'); raise StopPrediction()
                self_test = self
                b_fake = SimpleNamespace(group_accounting=lambda data: (None, None, None, None, FakeVector([1., 1.]), {}),
                                         _BudgetCallback=Callback, predict_scores=predict)
                np_fake = SimpleNamespace(any=any, float64='float64', asarray=lambda value, **kw: value)
                budget = SimpleNamespace(check=lambda: None, reserve_fit=lambda: events.append('reserve'), fit_attempts=1)
                recipe = dict(periods=dict(train=dict(queries=2), selection=dict(queries=2)), constructor_parameters={})
                fn = pure_body('fit_arm', np=np_fake, b=b_fake,
                               prepare_matrix=lambda files, *args, **kw: train if files == 'train' else selection,
                               matrix_identity=identity, array_ref=lambda *args: 'w',
                               verify_fresh_model=lambda *args: None)
                if phase == 'unchanged':
                    with self.assertRaises(StopPrediction):
                        fn('W', 'train', 'selection', recipe, directory, budget, backend=(Model, Pool), base_reference=baseline)
                    self.assertEqual(events.count('predict'), 1)
                else:
                    with self.assertRaisesRegex(ValueError, 'shared B41'):
                        fn('W', 'train', 'selection', recipe, directory, budget, backend=(Model, Pool), base_reference=baseline)
                    self.assertNotIn('predict', events)
                    self.assertEqual(events.count('fit'), 0 if phase == 'train' else 1)
                    self.assertEqual(events.count('pool'), 0 if phase == 'train' else 1)

    def test_primary_exception_identity_survives_writer_telemetry_and_handler_failures(self):
        original_write = r.write_new
        for index, primary in enumerate((KeyboardInterrupt('KI'), RuntimeError('fit'), SystemExit(7))):
            output = self.root / ('failure-' + str(index))
            def write(path, body):
                if path.name == 'failed.json': raise OSError('disk full')
                original_write(path, body)
            def telemetry(): raise RuntimeError('telemetry unavailable')
            budget = SimpleNamespace(check=lambda: None, telemetry=telemetry,
                                     cpu_limit=1, wall_limit=1, rss_limit=1, spill_limit=1)
            with patch.object(r, 'validate_recipe', side_effect=primary), patch.object(r, 'write_new', side_effect=write):
                try: r.run(self.root / 'absent.gz', output, self.root / 'absent.json', budget)
                except BaseException as escaped: self.assertIs(escaped, primary)
                else: self.fail('Primary was swallowed')
            self.assertTrue((output / 'consumed.json').exists())
            self.assertTrue(any('Failure persistence: OSError' == note for note in primary.__notes__))
            self.assertTrue(any('Failure telemetry: RuntimeError' == note for note in primary.__notes__))
        primary = KeyboardInterrupt('handler interrupted')
        budget = SimpleNamespace(check=lambda: None, cpu_limit=1, wall_limit=1, rss_limit=1, spill_limit=1)
        with patch.object(r, 'validate_recipe', side_effect=primary), patch.object(r, 'fail_preserving', side_effect=SystemExit(9)):
            try: r.run(self.root / 'absent.gz', self.root / 'handler-failure', self.root / 'absent.json', budget)
            except BaseException as escaped: self.assertIs(escaped, primary)
        self.assertIn('Failure handler: SystemExit', primary.__notes__)
        r.close_preserving(SimpleNamespace(close=lambda: (_ for _ in ()).throw(OSError('close'))), primary)
        self.assertIn('Connection close: OSError', primary.__notes__)

    def test_source_snapshots_are_compiled_and_command_closure_changes_reject(self):
        scripts = self.root / 'scripts'; scripts.mkdir(); source = scripts / 'toy_core.py'
        raw = b'VALUE = 7\n'; source.write_bytes(raw)
        recipe = dict(dependencies={'scripts/toy_core.py': hashlib.sha256(raw).hexdigest()})
        parent = sys.modules['scripts']
        previous = getattr(parent, 'toy_core', None)
        try:
            with patch.object(r, 'ROOT', self.root), patch.object(r, 'CORE_ORDER', ('toy_core',)):
                binding = r.SourceBinding(recipe, lambda: None)
                source.write_bytes(b'VALUE = 99\n')
                with self.assertRaisesRegex(ValueError, 'Initially bound source changed'):
                    binding.load_cores()
                self.assertNotIn('scripts.toy_core', sys.modules)
                source.write_bytes(raw)
                binding.load_cores()
                self.assertEqual(sys.modules['scripts.toy_core'].VALUE, 7)
                source.write_bytes(b'VALUE = 99\n')
                self.assertEqual(binding.loaded['toy_core'].VALUE, 7)
                with self.assertRaisesRegex(ValueError, 'Initially bound source changed'):
                    binding.check()
                source.write_bytes(raw)
                real_ref = r.file_ref
                with patch.object(r, 'file_ref', side_effect=lambda p, check:
                                  dict(sha256='0' * 64, bytes=1) if Path(p) == binding.command_path else real_ref(p, check)):
                    with self.assertRaisesRegex(ValueError, 'Initial command source changed'):
                        binding.check()
                sys.modules['scripts.toy_core'] = ModuleType('scripts.toy_core')
                with self.assertRaisesRegex(ValueError, 'module was replaced'):
                    binding.check()
        finally:
            sys.modules.pop('scripts.toy_core', None)
            if previous is None:
                if hasattr(parent, 'toy_core'): delattr(parent, 'toy_core')
            else: setattr(parent, 'toy_core', previous)

    def test_terminal_run_repin_rejects_export_changed_after_report_persistence(self):
        created = []; output = self.root / 'terminal-output'
        raw_recipe = b'{"fixture":true}'; witness = dict(sha256=hashlib.sha256(raw_recipe).hexdigest(), bytes=len(raw_recipe))
        profile = dict(explicit='invented test profile')
        recipe = dict(source=profile, minimum_free_disk_bytes=0, environment=dict(packages={}),
                      periods={name: dict(start='2019-10-08T00:00:00Z', end='2019-10-09T00:00:00Z')
                               for name in ('train', 'selection')})
        source = ModuleType('scripts.source_import'); source.PRODUCTION_PROFILE = profile
        def imported(*args, **kwargs):
            db = self.root / 'invented-database.bin'; db.write_bytes(b'not a database')
            return dict(database=dict(path=str(db), **r.file_ref(db, lambda: None)), source={})
        source.import_archive = imported
        engine = ModuleType('duckdb'); engine.connect = lambda *args, **kwargs: SimpleNamespace(close=lambda: None)
        sources = SimpleNamespace(load_cores=lambda: None, check=lambda: None, witnesses={}, command={'sha256': 'original'})
        budget = SimpleNamespace(check=lambda: None, telemetry=lambda: {}, cpu_limit=1, wall_limit=1, rss_limit=1, spill_limit=1)
        original_write = r.write_new
        def compare(*args, **kwargs):
            result = {}
            for arm in ('B', 'W'):
                model = output / (arm + '.cbm'); model.write_bytes(b'invented fake model')
                scores = output / (arm + '.selection-scores.npz'); scores.write_bytes(b'invented fake scores')
                result[arm] = dict(model=r.file_ref(model, lambda: None), predictions=r.file_ref(scores, lambda: None),
                                   evaluation=dict(conditional_macro_query=dict(ndcg=0.)))
            return result
        def build(con, config, recipe, directory, check, **kwargs):
            files = self.exports(directory=directory); created.append(files); return files
        def write(path, body):
            original_write(path, body)
            if path.name == 'report.json':
                self.assertEqual(body['data_exports']['train'][0]['manifest']['sha256'],
                                 created[0]['_manifest']['witness']['sha256'])
                self.assertEqual(body['data_exports']['train'][0]['exports']['base']['path'],
                                 'train/2019-10-08/base.parquet')
                created[0]['base'].write_bytes(b'changed after reported snapshot')
        with patch.dict(sys.modules, {'scripts.source_import': source, 'duckdb': engine}), \
             patch.object(r, 'validate_recipe', return_value=(recipe, raw_recipe, witness)), \
             patch.object(r, 'parse_json', side_effect=lambda raw: recipe if raw == raw_recipe else json.loads(raw)), \
             patch.object(r, 'SourceBinding', return_value=sources), patch.object(r, 'day_protocol', return_value={}), \
             patch.object(r, 'build_day', side_effect=build), patch.object(r, 'compare_two', side_effect=compare), \
             patch.object(r, 'write_new', side_effect=write):
            with self.assertRaisesRegex(ValueError, 'Original consumed export'):
                r.run(self.root / 'absent.gz', output, self.root / 'absent.json', budget)
        self.assertTrue((output / 'report.json').exists())
        self.assertEqual(json.loads((output / 'failed.json').read_bytes())['status'], 'failed_consumed')


if __name__ == '__main__':
    unittest.main()
