"""council.xfer.fit on a synthetic world (contract §3.1): xm is replaced by a fake that reads small parquet files in
a temporary directory; no real collection, label or model is touched. One smoke test activates the real Tinkoff
dataset in a subprocess, builds xm.Context and checks specs, data stamps and check_rows against the xfer report
without training, without reading any label and without writing anything.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_fit -v
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pandas as pd

from council.xfer import fit, roles
from scripts import xfer_common as xc
from scripts import xfer_model as real_xm

ROOT = Path(__file__).resolve().parents[2]
KEYS = ['user_id', 'item_id']
STAMP = {'code': {'scripts/xfer_model.py': 'c0de'}, 'council': {'council/xfer/fit.py': 'f17'}}
TRAIN = (461, 491)
S0, TEST = 641, 671
USERS = 40
ITEMS = 5


def write_parquet(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    xc.write_parquet(frame, path)


def rows_sha(series, anchor):
    return hashlib.sha256(f'{series}:{anchor}'.encode()).hexdigest()


class FakeDataset(roles.Dataset):
    """roles.Dataset whose collections live in the temporary world (anchors['_world'])."""

    def collection(self, phase, anchor=None):
        role = roles.COLLECTION_ROLES[phase]
        if anchor is None:
            anchor = {'select': self.s0_anchor, 'probe': self.probe_anchor, 'test': self.test_anchor}[phase]
        return Path(self.anchors['_world']) / 'xfer' / 'collections' / f'{role}-{anchor}'


class World:
    """A tiny xfer dataset: 4 collections x 40 users x 5 items, base f1 f2, agent column ag_a, council tables
    g1_1 (ag_c1_x, some pairs missing), g2_1 (ag_c2_y), g3_1 (ag_c3_z, used by the placebo only)."""

    TABLES = {'g1_1': ['ag_c1_x'], 'g2_1': ['ag_c2_y'], 'g3_1': ['ag_c3_z']}

    def __init__(self, tmp):
        self.root = Path(tmp)
        anchors = {
            '_world': str(self.root), 'K': 2, 'N': None, 'probe': S0, 'probe_users': 10,
            'roles': {'train': list(TRAIN), 'val': [S0], 'holdout': [TEST], 'probe': [S0]},
            'series': {'dev': {'train': list(TRAIN), 'eval': S0, 'eval_role': 'val'},
                       'holdout': {'train': [*TRAIN, S0], 'eval': TEST, 'eval_role': 'holdout'}},
        }
        paths = roles.Paths(dataset='tinkoff', runs=self.root / 'repo' / 'council' / 'runs' / 'xfer-tinkoff',
                            out=self.root / 'out' / 'xfer-tinkoff', llm=self.root / 'llm')
        self.ds = FakeDataset(name='tinkoff', adapter=None, anchors=anchors, paths=paths)
        self.calls = []
        for role, anchor in [('train', a) for a in TRAIN] + [('val', S0), ('holdout', TEST)]:
            self.make_collection(role, anchor)
        for series, train in (('dev', TRAIN), ('holdout', (*TRAIN, S0))):
            report = self.xfer_dir(series) / 'report.json'
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({'status': 'completed', 'identity': {'training_populations': [
                {'anchor': a, 'rows_sha256': rows_sha(series, a)} for a in train]}}))

    def xfer_dir(self, series, arm='BA', seed=2026):
        return self.root / 'xfer' / 'fits' / series / f'{arm}{seed}'

    def sidecar_dir(self, collection):
        return self.root / 'xfer' / 'sidecars' / Path(collection).name

    def frame(self, anchor):
        u, i = np.meshgrid(np.arange(USERS, dtype=np.int64), np.arange(ITEMS, dtype=np.int64), indexing='ij')
        u, i = u.ravel(), i.ravel()
        return pd.DataFrame({'user_id': u, 'item_id': i, 'f1': (u * 7 + i * 3 + anchor) % 11 / 10.0,
                             'f2': (u + 2 * i) % 5 / 4.0})

    def make_collection(self, role, anchor):
        coll = self.root / 'xfer' / 'collections' / f'{role}-{anchor}'
        f = self.frame(anchor)
        write_parquet(f, coll / 'frame.parquet')
        (coll / 'manifest.json').write_text(json.dumps({'collection': coll.name}))
        side = self.sidecar_dir(coll)
        write_parquet(f[KEYS].assign(ag_a=(f.user_id % 3).astype(float)), side / 'agent.parquet')
        (side / 'manifest.json').write_text(json.dumps({'collection': coll.name, 'rows': len(f)}))
        entries = {}
        for t, cols in self.TABLES.items():
            tab = f[KEYS].copy()
            for c in cols:
                tab[c] = (tab.user_id * 13 + tab.item_id * (5 + len(t)) + anchor) % 17 / 16.0
            if t == 'g1_1':
                tab = tab[(tab.user_id + tab.item_id) % 4 != 0]          # missing pairs -> NaN
            write_parquet(tab.reset_index(drop=True), self.ds.paths.table(coll.name, t))
            entries[t] = {'columns': cols}
        man = self.ds.paths.sidecars / coll.name / 'manifest.json'
        man.write_text(json.dumps({'format': 'council-xfer-table-v1', 'tables': entries}))

    # ---------------------------------------------------------------- fake xm

    def role_of(self, anchor):
        for role, anchors in self.ds.anchors['roles'].items():
            if anchor in anchors and role != 'probe':
                return role
        raise AssertionError(anchor)

    def training_block(self, ctx, con, series, anchor, arm, seed):
        self.calls.append(('training_block', series, anchor, arm, seed))
        role = self.role_of(anchor)
        coll = self.root / 'xfer' / 'collections' / f'{role}-{anchor}'
        block = self.frame(anchor)
        block['ag_a'] = (block.user_id % 3).astype(float)
        block['label'] = ((block.item_id == block.user_id % ITEMS) | (block.item_id == (anchor % ITEMS))).astype(np.int8)
        block['weight'] = 1.0 + (block.user_id % 2)
        hook = getattr(self, 'hook', None)
        if hook:
            hook(anchor)
        population = {'anchor': anchor, 'role': role, 'collection': coll.name, 'manifest_sha256': 'm',
                      'queries': USERS, 'rows': len(block), 'rows_sha256': self.sha(series, anchor)}
        return block, population, None, None, {}

    def sha(self, series, anchor):
        return rows_sha(series, anchor)

    def xm(self):
        world = self

        class Ctx:
            numeric = ['f1', 'f2']
            categorical = []
            columns = ['ag_a']
            base_names = ['f1', 'f2']

            def __init__(self, dataset):
                world.calls.append(('Context', dataset))

            def check_collection(self, path, role):
                world.calls.append(('check_collection', Path(path).name, role))

            def sidecar(self, path):
                return world.sidecar_dir(path), {}

        def frame_rows(con, path, names, users=None, user_range=None):
            f = xc.read_parquet(path)
            return f[KEYS + list(names)].sort_values(KEYS).reset_index(drop=True)

        def with_agent(con, frame, directory, columns, users=None, user_range=None):
            side = xc.read_parquet(Path(directory) / 'agent.parquet').sort_values(KEYS).reset_index(drop=True)
            out = frame.reset_index(drop=True).copy()
            for c in columns:
                out[c] = side[c].to_numpy()
            return out

        def matrices(ctx, frame, columns):
            names = list(ctx.numeric) + list(columns)
            return frame[names].to_numpy(dtype=np.float32, na_value=np.nan), np.empty((len(frame), 0), dtype=object)

        def make_pool(numbers, cats, numeric_names, cat_names, label=None, weight=None):
            return {'numbers': numbers, 'names': list(numeric_names) + list(cat_names), 'y': label, 'w': weight}

        def predict(ctx, model, frame, columns):
            return model.score(frame, list(ctx.numeric) + list(columns))

        return SimpleNamespace(
            Context=Ctx, connect=lambda: SimpleNamespace(close=lambda: None), training_block=self.training_block,
            frame_rows=frame_rows, with_agent=with_agent, matrices=matrices, make_pool=make_pool, predict=predict,
            recipe_for=real_xm.recipe_for, fit_dir=lambda dataset, series, arm, seed: self.xfer_dir(series, arm, seed),
            check_sidecar_rows=lambda con, path, directory, side: None, KEYS=list(KEYS),
            keys_digest=real_xm.keys_digest)

    def patches(self, stamp=STAMP):
        models = []

        class Model:
            def __init__(self, recipe):
                self.recipe = recipe
                self.tree_count_ = recipe['iterations']
                models.append(self)

            def fit(self, pool):
                self.pool = pool
                self.feature_names_ = pool['names']

            def score(self, frame, names):
                w = np.arange(1, len(names) + 1, dtype=np.float64) / 10
                return np.nan_to_num(frame[names].to_numpy(dtype=np.float64)) @ w + self.recipe['random_seed'] * 1e-6

        self.models = models
        identity = stamp if callable(stamp) else (lambda ds: stamp)
        return [mock.patch.object(fit, 'xm', self.xm()), mock.patch.object(fit, 'classifier', Model),
                mock.patch.object(fit.xc, 'sidecar_dir', lambda dataset, coll: self.sidecar_dir(coll)),
                mock.patch.object(roles, 'identity', identity)]


def snapshot(root):
    out = {}
    for d, _, files in os.walk(root):
        for n in files:
            p = Path(d) / n
            out[p] = p.stat().st_mtime_ns
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(self.tmp.name)
        self.ds = self.w.ds
        self.started = []
        for p in self.w.patches():
            p.start()
            self.started.append(p)

    def tearDown(self):
        for p in reversed(self.started):
            p.stop()
        self.tmp.cleanup()

    def spec(self, phase='plan', arm='r01', seed=None, **kw):
        seed = roles.plan_seed(int(arm[1:])) if seed is None and phase == 'plan' else seed
        s = {'name': f'{phase}-{arm}-{seed}', 'phase': phase, 'arm': arm, 'seed': seed}
        s.update(kw)
        return s


class ValidateTest(Base):
    def test_path_and_noise_specs(self):
        p = fit.path_specs(self.ds)
        self.assertEqual([s['name'] for s in p], ['path_select-Hr-2026', 'path_test-Hr-2026'])
        self.assertTrue(all(s['tables'] == [] and s['placebo'] is None and s['half'] is None for s in p))
        n = fit.noise_specs(self.ds)
        self.assertEqual([(s['seed'], s['half']) for s in n], [(7, 'A'), (11, 'A')])
        self.assertEqual(list(n[0]), list(fit.SPEC_KEYS))
        self.assertEqual(fit.series_of('path_test'), roles.SERIES['test'])
        self.assertEqual(fit.series_of('plan'), 'dev')

    def test_normalizes_and_fills_the_half(self):
        s = fit.validate(self.ds, self.spec(tables=['g1_1', 'g2_1_tw', 'rb1_cooc_decay'],
                                            placebo={'tables': ['g3_1'], 'columns': ['ag_c3_z']}))
        self.assertEqual(s['half'], 'B')
        self.assertEqual(list(s), list(fit.SPEC_KEYS))
        self.assertEqual(fit.validate(self.ds, s), s)            # idempotent (the queue passes normalized specs)
        c = fit.validate(self.ds, self.spec('confirm', 'SEL', 3002, tables=['g1_1']))
        self.assertEqual(c['half'], 'B')

    def test_refusals(self):
        bad = [
            self.spec(name='plan-r01-1002'),
            self.spec(seed=1002, name='plan-r01-1002'),                       # seed of r02
            self.spec('plan', 'r49', 1049),
            self.spec('nope', 'Hr', 7),
            self.spec('noise', 'Hr', 7, half='B'),
            self.spec('noise', 'Hr', 13),
            self.spec('noise', 'SEL', 7),
            self.spec('path_select', 'Hr', 2027),
            self.spec('confirm', 'r01', 3001),
            self.spec('confirm', 'SEL', 7),
            self.spec('confirm', 'Hrp', 3001),                                 # confirm: ALLP and SEL only
            self.spec('confirm', 'TWIN', 3001),
            self.spec('confirm', 'SEL', 3001, placebo={'tables': ['g3_1'], 'columns': ['ag_c3_z']}),
            self.spec('test', 'SEL', 13, selection_sha256='a' * 64,
                      placebo={'tables': ['g3_1'], 'columns': ['ag_c3_z']}),  # a placebo is plan's only
            self.spec('noise', 'Hr', 7, tables=['g1_1']),                      # H+r has no tables
            self.spec(tables=['G1-1']),
            self.spec(tables=['g1_1', 'g1_1']),
            self.spec(tables=['labels']),
            self.spec(placebo={'tables': ['g3_1'], 'columns': ['plc_ag_c3_z']}),
            self.spec(placebo={'tables': ['g3_1'], 'columns': ['f1']}),
            self.spec(placebo={'tables': [], 'columns': ['ag_c3_z']}),
            self.spec(placebo={'columns': ['ag_c3_z']}),
            self.spec(selection_sha256='a' * 64),
            self.spec(extra=1),
            self.spec('test', 'SEL', 13),                                     # no selection sha
            self.spec('test', 'Rb1', 11, selection_sha256='a' * 64),
            {'name': 'x'},
            'plan-r01-1001',
        ]
        for spec in bad:
            with self.assertRaises(ValueError, msg=spec):
                fit.validate(self.ds, spec)

    def test_every_spec_of_plan_is_valid_as_is(self):
        from council.tests.test_xfer_plan import curation
        from council.xfer import plan
        cur = curation()
        specs = plan.plan_specs(cur) + plan.confirm_specs(cur, ['F2']) + plan.confirm_specs(cur, [])
        specs += fit.path_specs(self.ds) + fit.noise_specs(self.ds)
        sha = 'd' * 64
        self.ds.paths.reads.parent.mkdir(parents=True)
        self.ds.paths.reads.write_text(json.dumps({'what': 'test.started', 'selection_sha256': sha}) + '\n')
        for d in (['F2'], []):
            specs += plan.test_specs(cur, {'D': d, 'tables': plan._arm_tables(cur, d, None)}, sha)
        self.assertGreater(len(specs), 48 + 4 + 4)
        self.assertTrue(any(s['placebo'] for s in specs))
        for s in specs:
            self.assertEqual(fit.validate(self.ds, s), s, s['name'])
        self.assertEqual(plan.SPEC_KEYS, fit.SPEC_KEYS)

    def test_test_phase_needs_the_marker_with_the_same_sha(self):
        spec = self.spec('test', 'SEL', 13, selection_sha256='a' * 64)
        with self.assertRaises(ValueError):
            fit.validate(self.ds, spec)                                     # no marker
        self.ds.paths.reads.parent.mkdir(parents=True)
        self.ds.paths.reads.write_text(json.dumps({'what': 'test.started', 'selection_sha256': 'b' * 64}) + '\n')
        with self.assertRaises(ValueError):
            fit.validate(self.ds, spec)                                     # another sha
        self.assertEqual(fit.validate(self.ds, dict(spec, selection_sha256='b' * 64))['half'], None)


class RunTest(Base):
    PLAN = dict(tables=['g1_1', 'g2_1'], placebo={'tables': ['g3_1'], 'columns': ['ag_c3_z']})

    def test_writes_scores_only_at_the_scores_path_with_a_stamped_record(self):
        before = snapshot(self.w.root)
        rec = fit.run(self.ds, self.spec(**self.PLAN), commit='abc', dirty=False)
        after = snapshot(self.w.root)
        out = self.ds.paths.scores('plan', 'r01', 1001)
        self.assertEqual(out, roles.Paths(dataset='tinkoff', runs=self.ds.paths.runs, out=self.ds.paths.out,
                                          llm=self.ds.paths.llm).scores('plan', 'r01', 1001))
        self.assertEqual(out, self.ds.paths.out / 'fits' / 'plan' / 'r01-1001' / 'scores.parquet')
        self.assertEqual(set(after) - set(before), {out, self.ds.paths.fit_records})
        self.assertTrue(all(after[p] == m for p, m in before.items()))
        self.assertEqual(tuple(rec), fit.RECORD_KEYS)
        self.assertEqual(rec['identity'], STAMP)
        self.assertEqual(set(rec['identity']), {'code', 'council'})
        self.assertEqual(rec['data'], fit.data_stamp(self.ds, fit.validate(self.ds, self.spec(**self.PLAN))))
        self.assertEqual(rec['series'], 'dev')
        self.assertEqual(rec['recipe'], roles.recipe_for(1001))
        self.assertEqual(rec['council_columns'], ['ag_c1_x', 'ag_c2_y', 'plc_ag_c3_z'])
        self.assertEqual(rec['placebo_columns'], 1)
        self.assertEqual(rec['features'], 2 + 1 + 3)
        self.assertEqual([p['rows_sha256'] for p in rec['populations']], [rows_sha('dev', a) for a in TRAIN])
        self.assertEqual(fit.records(self.ds)['plan-r01-1001'], rec)
        blocks = [c for c in self.w.calls if c[0] == 'training_block']
        self.assertEqual(blocks, [('training_block', 'dev', a, 'BA', 1001) for a in TRAIN])
        s = xc.read_parquet(out)
        self.assertEqual(tuple(s.columns), fit.SCORE_COLUMNS)
        self.assertTrue((roles.halves(s.user_id.to_numpy()) == 'B').all())
        self.assertEqual(len(s), int((roles.halves(np.arange(USERS)) == 'B').sum()) * ITEMS)
        self.assertTrue(s.qid.str.startswith(f'{S0}:').all())
        self.assertTrue((s.qid == s.user_id.map(lambda u: roles.Dataset.qid(S0, u))).all())
        self.assertTrue(s[KEYS].equals(s[KEYS].sort_values(KEYS).reset_index(drop=True)))
        self.assertEqual(rec['eval']['scores_sha256'], xc.sha256_file(out))
        self.assertNotIn('label', ' '.join(s.columns))

    def test_the_test_series_trains_on_s0_and_scores_every_c_test_user(self):
        rec = fit.run(self.ds, fit.path_specs(self.ds)[1])
        blocks = [c for c in self.w.calls if c[0] == 'training_block']
        self.assertEqual([(c[1], c[2]) for c in blocks], [('holdout', a) for a in (*TRAIN, S0)])
        s = xc.read_parquet(self.ds.paths.scores('path_test', 'Hr', 2026))
        self.assertEqual(len(s), USERS * ITEMS)
        self.assertTrue(s.qid.str.startswith(f'{TEST}:').all())
        self.assertEqual(rec['council_columns'], [])
        self.assertEqual(rec['features'], 3)
        self.assertIn(('check_collection', f'holdout-{TEST}', 'holdout'), self.w.calls)

    def test_training_labels_and_weights_come_from_training_block(self):
        fit.run(self.ds, self.spec(**self.PLAN))
        pool = self.w.models[-1].pool
        expect_y, expect_w = [], []
        for a in TRAIN:
            b, *_ = self.w.training_block(None, None, 'dev', a, 'BA', 0)
            expect_y.append(b['label'].to_numpy())
            expect_w.append(b['weight'].to_numpy())
        np.testing.assert_array_equal(pool['y'], np.concatenate(expect_y))
        np.testing.assert_array_equal(pool['w'], np.concatenate(expect_w))
        self.assertEqual(pool['names'], ['f1', 'f2', 'ag_a', 'ag_c1_x', 'ag_c2_y', 'plc_ag_c3_z'])

    def test_placebo_in_training_is_the_permutation_of_placebo_key_per_anchor(self):
        fit.run(self.ds, self.spec(**self.PLAN))
        numbers = self.w.models[-1].pool['numbers']
        col = self.w.models[-1].pool['names'].index('plc_ag_c3_z')
        n = USERS * ITEMS
        for k, a in enumerate(TRAIN):
            tab = xc.read_parquet(self.ds.paths.table(f'train-{a}', 'g3_1')).sort_values(KEYS)
            perm = np.random.default_rng(roles.placebo_key(a)).permutation(n)
            np.testing.assert_allclose(numbers[k * n:(k + 1) * n, col], tab['ag_c3_z'].to_numpy()[perm], rtol=1e-6)

    def test_never_over_an_existing_file(self):
        spec = self.spec(**self.PLAN)
        fit.run(self.ds, spec)
        with self.assertRaises(ValueError):
            fit.run(self.ds, spec)

    def test_stamp_and_data_of_the_queue(self):
        spec = fit.validate(self.ds, self.spec(**self.PLAN))
        out = self.ds.paths.scores('plan', 'r01', 1001)
        with self.assertRaises(SystemExit):
            fit.run(self.ds, spec, stamp={'code': {}, 'council': {}})
        with self.assertRaises(SystemExit):
            fit.run(self.ds, spec, data={'collections': {}})
        self.assertFalse(out.exists())
        # the data change during the fit: a council table is rewritten while the second anchor loads
        table = self.ds.paths.table(f'val-{S0}', 'g1_1')
        self.w.hook = lambda anchor: anchor == TRAIN[1] and write_parquet(
            xc.read_parquet(table).assign(ag_c1_x=0.5), table)
        with self.assertRaises(SystemExit):
            fit.run(self.ds, spec)
        self.assertFalse(out.exists())
        self.assertFalse(self.ds.paths.fit_records.exists())

    def test_code_change_during_the_fit_writes_nothing(self):
        stamps = iter([STAMP, dict(STAMP, council={'council/xfer/fit.py': 'changed'})])
        with mock.patch.object(roles, 'identity', lambda ds: next(stamps)):
            with self.assertRaises(SystemExit):
                fit.run(self.ds, self.spec(**self.PLAN))
        self.assertFalse(self.ds.paths.scores('plan', 'r01', 1001).exists())

    def test_prereg0_identity_freezes_the_stamp(self):
        self.ds.paths.runs.mkdir(parents=True)
        self.ds.paths.prereg(0).write_text(json.dumps({'identity': {'code': {}, 'council': {'other': '1'}}}))
        with self.assertRaises(SystemExit):
            fit.run(self.ds, self.spec(**self.PLAN))
        self.ds.paths.prereg(0).write_text(json.dumps({'identity': STAMP}))
        fit.run(self.ds, self.spec(**self.PLAN))

    def test_rows_must_be_the_xfer_rows(self):
        self.w.sha = lambda series, anchor: 'f' * 64 if anchor == TRAIN[1] else rows_sha(series, anchor)
        with self.assertRaises(SystemExit):
            fit.run(self.ds, self.spec(**self.PLAN))
        self.assertFalse(self.ds.paths.scores('plan', 'r01', 1001).exists())


class ScoreAndControlTest(Base):
    def test_the_placebo_does_not_depend_on_the_half(self):
        spec = fit.validate(self.ds, self.spec(tables=['g1_1'], placebo={'tables': ['g3_1'], 'columns': ['ag_c3_z']}))
        columns = fit.columns_of(self.ds, spec)
        model = SimpleNamespace(score=lambda frame, names: frame['plc_ag_c3_z'].to_numpy(dtype=np.float64))
        ctx, con = fit.xm.Context('tinkoff'), fit.xm.connect()
        got = {h: fit.score(ctx, con, self.ds, dict(spec, half=h), model, columns).set_index(KEYS)['score']
               for h in ('A', 'B', None)}
        self.assertEqual(len(got['A']) + len(got['B']), len(got[None]))
        self.assertTrue(len(got['A']) and len(got['B']))
        for h in 'AB':
            pd.testing.assert_series_equal(got[h], got[None].loc[got[h].index])
        tab = xc.read_parquet(self.ds.paths.table(f'val-{S0}', 'g3_1'))
        frame = self.w.frame(S0)[KEYS].merge(tab, on=KEYS, how='left')
        perm = np.random.default_rng(roles.placebo_key(S0)).permutation(len(frame))
        whole = pd.Series(frame['ag_c3_z'].to_numpy()[perm], index=pd.MultiIndex.from_frame(frame[KEYS]))
        np.testing.assert_allclose(got[None].to_numpy(), whole.loc[got[None].index].to_numpy())

    def test_the_control_after_the_fit_hashes_again(self):
        spec = fit.validate(self.ds, self.spec(tables=['g1_1']))
        man = self.w.root / 'xfer' / 'collections' / f'val-{S0}' / 'manifest.json'

        def same_size_same_mtime(anchor):
            if anchor == TRAIN[1]:
                st = man.stat()
                text = man.read_text()
                man.write_text(text.replace(str(S0), str(S0 + 1)))
                os.utime(man, ns=(st.st_atime_ns, st.st_mtime_ns))
                self.assertEqual((man.stat().st_size, man.stat().st_mtime_ns), (st.st_size, st.st_mtime_ns))

        self.w.hook = same_size_same_mtime
        with self.assertRaises(SystemExit):
            fit.run(self.ds, spec)
        self.assertFalse(self.ds.paths.scores('plan', 'r01', 1001).exists())

    def test_main_turns_a_lost_race_into_a_stop(self):
        path = self.w.root / 'spec.json'
        path.write_text(json.dumps(self.spec(tables=['g1_1'])))
        argv = ['--spec', str(path), '--stamp', json.dumps(STAMP), '--data', '{}']
        with mock.patch.object(fit, 'git_head', return_value=(None, None)):
            for err in (FileExistsError('scores.parquet'), ValueError('exists')):
                with mock.patch.object(fit, 'run', side_effect=err), self.assertRaises(SystemExit) as cm:
                    fit.main(self.ds, argv)
                self.assertIn('fit-one', str(cm.exception.code))
            with mock.patch.object(fit, '_write', side_effect=FileExistsError('raced')), \
                    self.assertRaises(SystemExit) as cm:
                fit.main(self.ds, ['--spec', str(path), '--stamp', json.dumps(STAMP), '--data',
                                   json.dumps(fit.data_stamp(self.ds, fit.validate(self.ds, json.loads(path.read_text()))))])
            self.assertIn('raced', str(cm.exception.code))
        self.assertFalse(self.ds.paths.fit_records.exists())


class CheckRowsTest(Base):
    def pops(self, series, anchors):
        return [{'anchor': a, 'rows_sha256': rows_sha(series, a)} for a in anchors]

    def test_against_the_xfer_report(self):
        fit.check_rows(self.ds, 'dev', self.pops('dev', TRAIN))
        fit.check_rows(self.ds, 'holdout', self.pops('holdout', (*TRAIN, S0)))
        for bad in (self.pops('holdout', TRAIN), self.pops('dev', TRAIN[:1]), self.pops('dev', TRAIN[::-1]),
                    self.pops('dev', (*TRAIN, S0))):
            with self.assertRaises(SystemExit):
                fit.check_rows(self.ds, 'dev', bad)
        with self.assertRaises(SystemExit):
            fit.check_rows(self.ds, 'final', self.pops('dev', TRAIN))       # no report


class JoinAndPlaceboTest(Base):
    def test_join_keeps_order_and_gives_nan_for_missing_pairs(self):
        frame = self.w.frame(S0).sample(frac=1, random_state=3).reset_index(drop=True)
        out = fit.council_join(self.ds, frame, f'val-{S0}', ['g1_1', 'g2_1'])
        self.assertTrue(out[KEYS].equals(frame[KEYS]))
        self.assertEqual(list(out.columns), list(frame.columns) + ['ag_c1_x', 'ag_c2_y'])
        missing = ((frame.user_id + frame.item_id) % 4 == 0).to_numpy()
        self.assertTrue(out['ag_c1_x'].isna().to_numpy()[missing].all())
        self.assertFalse(out['ag_c1_x'].isna().to_numpy()[~missing].any())
        self.assertFalse(out['ag_c2_y'].isna().any())

    def test_join_refusals(self):
        frame = self.w.frame(S0)
        with self.assertRaises(ValueError):
            fit.council_join(self.ds, frame, f'val-{S0}', ['g4_1'])                   # no file
        with self.assertRaises(ValueError):
            fit.council_join(self.ds, frame.assign(ag_c2_y=1.0), f'val-{S0}', ['g2_1'])   # clash
        path = self.ds.paths.table(f'val-{S0}', 'g2_1')
        tab = xc.read_parquet(path)
        write_parquet(pd.concat([tab, tab.head(1)]), path)
        with self.assertRaises(ValueError):
            fit.council_join(self.ds, frame, f'val-{S0}', ['g2_1'])                   # repeated key
        write_parquet(tab.rename(columns={'ag_c2_y': 'ag_c2_q'}), path)
        with self.assertRaises(ValueError):
            fit.council_join(self.ds, frame, f'val-{S0}', ['g2_1'])                   # not the manifest's

    def test_placebo_permutes_with_the_placebo_key(self):
        frame = fit.council_join(self.ds, self.w.frame(S0), f'val-{S0}', ['g3_1'])
        pl = {'tables': ['g3_1'], 'columns': ['ag_c3_z']}
        out, n = fit.apply_placebo(frame, pl, S0)
        self.assertEqual(n, 1)
        perm = np.random.default_rng([roles.PLACEBO_SEED, 0, S0, 0]).permutation(len(frame))
        np.testing.assert_array_equal(out['plc_ag_c3_z'].to_numpy(), frame['ag_c3_z'].to_numpy()[perm])
        np.testing.assert_array_equal(out['ag_c3_z'].to_numpy(), frame['ag_c3_z'].to_numpy())
        again, _ = fit.apply_placebo(frame, pl, S0)
        self.assertTrue(again.equals(out))
        other, _ = fit.apply_placebo(frame, pl, TEST)
        self.assertFalse(np.array_equal(other['plc_ag_c3_z'].to_numpy(), out['plc_ag_c3_z'].to_numpy()))
        self.assertIs(fit.apply_placebo(frame, None, S0)[0], frame)
        with self.assertRaises(ValueError):
            fit.apply_placebo(out, pl, S0)                                             # exists already
        with self.assertRaises(ValueError):
            fit.apply_placebo(frame, {'tables': ['g3_1'], 'columns': ['ag_c9_x']}, S0)

    def test_placebo_only_tables_are_dropped(self):
        spec = fit.validate(self.ds, self.spec(tables=['g1_1'], placebo={'tables': ['g3_1'], 'columns': ['ag_c3_z']}))
        self.assertEqual(fit.columns_of(self.ds, spec), ['ag_c1_x', 'plc_ag_c3_z'])
        out, n = fit.council_frame(self.ds, self.w.frame(S0), f'val-{S0}', spec, S0)
        self.assertNotIn('ag_c3_z', out.columns)
        self.assertIn('plc_ag_c3_z', out.columns)
        spec = fit.validate(self.ds, self.spec(tables=['g1_1'], placebo={'tables': ['g3_1'], 'columns': ['ag_c1_x']}))
        with self.assertRaises(ValueError):
            fit.columns_of(self.ds, spec)                          # not a column of the placebo tables


class DataStampTest(Base):
    def test_fingerprint(self):
        spec = fit.validate(self.ds, self.spec(tables=['g1_1'], placebo={'tables': ['g3_1'], 'columns': ['ag_c3_z']}))
        d = fit.data_stamp(self.ds, spec)
        names = [f'train-{a}' for a in TRAIN] + [f'val-{S0}']
        self.assertEqual(list(d), ['collections', 'sidecars', 'tables', 'selection_sha256'])
        self.assertEqual(list(d['collections']), names)
        self.assertEqual(list(d['sidecars']), names)
        self.assertEqual({k: sorted(v) for k, v in d['tables'].items()}, {n: ['g1_1', 'g3_1'] for n in names})
        self.assertEqual(d['tables'][f'val-{S0}']['g1_1'], xc.sha256_file(self.ds.paths.table(f'val-{S0}', 'g1_1')))
        self.assertEqual(json.loads(json.dumps(d)), d)
        t = fit.data_stamp(self.ds, fit.path_specs(self.ds)[1])
        self.assertEqual(list(t['collections']), [f'train-{a}' for a in TRAIN] + [f'val-{S0}', f'holdout-{TEST}'])
        self.ds.paths.table(f'train-{TRAIN[0]}', 'g1_1').unlink()
        with self.assertRaises(ValueError):
            fit.data_stamp(self.ds, spec)


class DoneTest(Base):
    def test_done(self):
        spec = fit.validate(self.ds, self.spec(tables=['g1_1']))
        data = fit.data_stamp(self.ds, spec)
        self.assertFalse(fit.done(self.ds, spec, data, STAMP))
        fit.run(self.ds, spec)
        self.assertTrue(fit.done(self.ds, spec, data, STAMP))
        self.assertTrue(fit.done(self.ds, spec))
        with self.assertRaises(SystemExit):
            fit.done(self.ds, spec, dict(data, selection_sha256='x'))                # other data
        with self.assertRaises(SystemExit):
            fit.done(self.ds, spec, data, {'code': {}, 'council': {}})               # other identity: stop
        with self.assertRaises(SystemExit):
            fit.done(self.ds, dict(spec, tables=['g2_1']), data)                     # other spec
        self.ds.paths.runs.mkdir(parents=True)
        self.ds.paths.prereg(0).write_text(json.dumps({'identity': {'code': {}, 'council': {}}}))
        with self.assertRaises(SystemExit):
            fit.done(self.ds, spec, data, STAMP)                                     # not prereg-0's stamp
        self.ds.paths.prereg(0).unlink()
        self.ds.paths.fit_records.unlink()
        with self.assertRaises(SystemExit):
            fit.done(self.ds, spec)                                                  # file without record

    def test_records_tolerate_a_broken_last_line(self):
        spec = fit.validate(self.ds, self.spec(tables=['g1_1']))
        fit.run(self.ds, spec)
        with self.ds.paths.fit_records.open('a') as f:
            f.write('{"name": "plan-r02-10')
        with mock.patch('sys.stderr'):
            self.assertEqual(list(fit.records(self.ds)), ['plan-r01-1001'])
            self.assertTrue(fit.done(self.ds, spec))
        other = fit.validate(self.ds, self.spec('plan', 'r02', tables=['g2_1']))
        with mock.patch('sys.stderr'), self.assertRaises(SystemExit):
            fit.run(self.ds, other)                                 # never glued to a broken line
        self.assertFalse(self.ds.paths.scores('plan', 'r02', 1002).exists())
        with self.ds.paths.fit_records.open('a') as f:
            f.write('\n' + json.dumps({'name': 'x'}) + '\n')
        with self.assertRaises(ValueError):
            fit.records(self.ds)


SMOKE = textwrap.dedent('''
    import json, os, sys
    from pathlib import Path
    ROOT = Path(sys.argv[1]); sys.path.append(str(ROOT))

    def snap(p):
        out = {}
        for d, dirs, files in os.walk(p):
            for n in dirs + files:
                q = Path(d) / n
                out[str(q)] = q.lstat().st_mtime_ns
        return out

    watched = [ROOT / 'artifacts' / 'xfer' / 'tinkoff', ROOT / 'artifacts' / 'council', ROOT / 'council' / 'runs']
    before = [snap(p) for p in watched]
    from council.xfer import roles
    ds = roles.activate('tinkoff')
    from council.xfer import fit, broker
    from scripts import xfer_common as xc
    from scripts import xfer_model as xm
    out = {}
    specs = fit.path_specs(ds) + fit.noise_specs(ds)
    out['names'] = [s['name'] for s in specs]
    ctx = xm.Context(ds.name)
    out['agent_columns'] = len(ctx.columns)
    out['recipe'] = xm.recipe_for(7) == roles.recipe_for(7)
    d = fit.data_stamp(ds, specs[0])
    out['stamp_collections'] = list(d['collections'])
    out['training'] = [p.name for _, p in ds.training_collections('select')]
    path = fit.report_path(ds, fit.series_of('path_select'))
    pops = [{'anchor': p['anchor'], 'rows_sha256': p['rows_sha256']}
            for p in xc.read_json(path)['identity']['training_populations']]
    out['report_collections'] = [xc.collection_name('train', p['anchor']) for p in pops]
    fit.check_rows(ds, 'dev', pops)
    out['rows_ok'] = True
    try:
        fit.check_rows(ds, 'dev', pops[:-1] + [dict(pops[-1], rows_sha256='0' * 64)])
        out['rows_bad'] = 'passed'
    except SystemExit:
        out['rows_bad'] = 'SystemExit'
    out['done'] = fit.done(ds, specs[0])
    out['identity_is_prereg'] = roles.identity(ds)['code'] == roles.prereg_code(ds)
    after = [snap(p) for p in watched]
    out['unchanged'] = [a == b for a, b in zip(before, after)]
    print(json.dumps(out))
''')


class SmokeTest(unittest.TestCase):
    """The real Tinkoff dataset in its own process: Context, specs, data stamp, check_rows; nothing is trained,
    no label is read, nothing is written."""

    def test_real_context_without_training(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
        env['TASK1_PERIOD'] = '2020'
        r = subprocess.run([sys.executable, '-I', '-B', '-c', SMOKE, str(ROOT)], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out['names'], ['path_select-Hr-2026', 'path_test-Hr-2026', 'noise-Hr-7', 'noise-Hr-11'])
        self.assertTrue(out['recipe'])
        self.assertGreater(out['agent_columns'], 0)
        self.assertEqual(out['training'], out['report_collections'])
        self.assertEqual(out['stamp_collections'], out['training'] + ['val-641'])
        self.assertTrue(out['rows_ok'])
        self.assertEqual(out['rows_bad'], 'SystemExit')
        self.assertTrue(out['identity_is_prereg'])
        self.assertTrue(all(out['unchanged']), out['unchanged'])


if __name__ == '__main__':
    unittest.main()
