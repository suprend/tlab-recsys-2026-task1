import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from scripts import xfer_agent as xa
from scripts import xfer_common as xc
from scripts import xfer_model as xm

KEYS = ['user_id', 'item_id']
CODE = {'scripts/xfer_model.py': 'c0de'}
COLUMNS = ['a_good', 'a_noise']
K = 3
RECIPE = dict(xc.RECIPE, iterations=12, depth=3, learning_rate=0.3, thread_count=2)
INT_ANCHORS = {10: 10, 20: 20, 30: 30, 40: 40, 50: 50}
ISO_ANCHORS = {10: '2020-06-10', 20: '2020-06-24', 30: '2020-07-08', 40: '2020-07-22', 50: '2020-08-05'}


def make_anchors(a):
    return dict(
        W=10, N=12, K=K, holdout=a[40], probe=a[30],
        roles=dict(train=[a[10], a[20]], val=[a[30]], holdout=[a[40]], kaggle=[a[50]], probe=[a[30]]),
        series=dict(dev=dict(train=[a[20], a[10]], eval=a[30], eval_role='val', arms=['B', 'BA', 'BApl']),
                    holdout=dict(train=[a[10], a[20], a[30]], eval=a[40], eval_role='holdout',
                                 arms=['B', 'BA', 'BApl']),
                    final=dict(train=[a[20], a[30], a[40]], eval=a[50], eval_role='kaggle', arms=['B', 'BA'])))


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


class FakeAdapter:
    """Synthetic adapter: fixed anchors, deterministic negative sampling, hit-rate metric.

    The metric refuses what the real T/S metrics refuse: targets of non-queries and
    ranked users outside the queries.
    """

    def __init__(self, anchors):
        self._anchors = anchors

    def anchors(self):
        return json.loads(json.dumps(self._anchors))

    def training_rows(self, frame, labels, A, seed=xc.SAMPLE_SEED):
        rows = frame.merge(labels, on=KEYS, how='left')
        rows['label'] = rows['label'].fillna(0).astype(int)
        keep = (rows['label'] == 1) | ((rows['user_id']*31 + rows['item_id']*7 + xc.anchor_int(A)) % 4 != 0)
        rows = rows[keep].reset_index(drop=True)
        rows['weight'] = np.where(rows['label'] == 1, 1.0, 4/3)
        return rows

    def metric(self, ranked, targets, labels):
        if (targets['n_targets'] < 1).any():
            raise ValueError('targets must hold queries only')
        if not set(ranked['user_id']) <= set(targets['user_id']):
            raise ValueError('ranked users outside the queries')
        positives = set(map(tuple, labels.loc[labels['label'] == 1, KEYS].to_numpy().tolist()))
        out = []
        for user, n in zip(targets['user_id'], targets['n_targets']):
            items = ranked.loc[ranked['user_id'] == user, 'item_id'].tolist()
            hits = sum((int(user), int(i)) in positives for i in items)
            out.append((int(user), hits/min(int(n), K)))
        return pd.DataFrame(out, columns=['user_id', 'value'])

    def pop(self, A, users, k):
        return pd.DataFrame([(u, i, i+1) for u in users for i in range(k)], columns=['user_id', 'item_id', 'rank'])

    def assemble(self, scores, output):
        top = xm.top_k(scores, K)
        path = Path(output)/'submission.csv'
        top[KEYS].to_csv(path, index=False)
        return dict(rows=len(top), sha256=xc.sha256_file(path))


def make_rows(seed, users, labelled=True):
    rng = np.random.default_rng(seed)
    rows = []
    for user in users:
        for item in sorted(rng.choice(10, 6, replace=False)):
            latent = rng.normal()
            f_num = rng.normal()
            rows.append(dict(user_id=user, item_id=int(item), f_num=f_num,
                             f_cat=[None, 'a', 'b'][int(rng.integers(0, 3))],
                             a_good=None if rng.random() < 0.2 else latent+0.1*rng.normal(),
                             a_noise=None if rng.random() < 0.1 else rng.normal(),
                             label=int(1.5*f_num+latent+0.3*rng.normal() > 1.0)))
    frame = pd.DataFrame(rows).sort_values(KEYS).reset_index(drop=True)
    frame['user_id'] = frame['user_id'].astype('int64')
    frame['item_id'] = frame['item_id'].astype('int64')
    if labelled:
        # users 16 and 17 are not queries: no target at all
        frame.loc[frame['user_id'] >= 16, 'label'] = 0
    return frame


class World(unittest.TestCase):
    """Temp git repo: configs, train/val/kaggle collections, sidecars, committed prereg, then holdout."""

    DATASET = 'tinkoff'
    MAP = INT_ANCHORS

    def setUp(self):
        self.ds = self.DATASET
        self.anchors = make_anchors(self.MAP)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q')
        for name in ('configs/datasets', 'artifacts/xfer', 'docs'):
            (self.root/name).mkdir(parents=True)
        for doc in (xm.CONTRACT_DOC, xm.DATASET_DOCS[self.ds]):
            (self.root/doc).write_text('contract\n')
        self.patches = [mock.patch.object(xc, 'ROOT', self.root),
                        mock.patch.object(xc, 'adapter', lambda dataset: FakeAdapter(self.anchors)),
                        mock.patch.object(xc, 'code_identity', lambda dataset: dict(CODE)),
                        mock.patch.object(xc, 'RECIPE', RECIPE),
                        mock.patch.object(xc, 'isolated', lambda: None),
                        mock.patch.object(xm, 'current_prompt_digest', lambda dataset: 'prompt-1')]
        for p in self.patches:
            p.start()
        self.base = xc.make_base(self.ds, dict(sources=['pop']), [
            dict(name='f_num', formula='x', missing='0'), dict(name='f_cat', formula='c', missing='NULL')], ['f_cat'])
        base_path = self.config('base', self.base)
        set_path = self.config('set', dict(columns=COLUMNS, prompt_digest='prompt-1', code=dict(CODE)))
        self.commit(base_path, set_path, *(self.root/'docs').rglob('*.md'))
        self.set_sha = xc.sha256_file(set_path)
        self.frames = {}
        for role, key in (('train', 10), ('train', 20), ('val', 30)):
            self.frames[key] = make_rows(key, range(18))
            self.collection(role, key, self.frames[key])
        self.frames[50] = make_rows(50, range(25), labelled=False)
        self.collection('kaggle', 50, self.frames[50])
        xm.prereg(self.ds)
        self.commit(xc.config_path(self.ds, 'prereg'))
        self.frames[40] = make_rows(40, range(18))
        self.collection('holdout', 40, self.frames[40])
        self.leaks = 0

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        for path in self.root.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        self.tmp.cleanup()

    def A(self, key):
        return self.MAP[key]

    def config(self, kind, value):
        path = xc.config_path(self.ds, kind)
        path.write_text(json.dumps(value))
        return path

    def commit(self, *paths):
        git(self.root, 'add', '-f', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def collection(self, role, key, frame, base=None):
        anchor = self.A(key)
        col = xc.new_output(xc.output_dir(self.ds, 'collections', xc.collection_name(role, anchor)))
        xc.write_parquet(frame[KEYS+['f_num', 'f_cat']], col/'frame.parquet', order_by='user_id, item_id')
        sealed = None
        if role in ('train', 'val', 'holdout'):
            labels = frame[KEYS+['label']]
            n = labels.groupby('user_id')['label'].sum()
            targets = pd.DataFrame(dict(user_id=n.index.astype('int64'),
                                        n_targets=np.where(n.index >= 16, 0, np.maximum(n.to_numpy(), 1)+n.index % 2)))

            def writer(d):
                xc.write_parquet(labels, Path(d)/'labels.parquet', order_by='user_id, item_id')
                xc.write_parquet(targets, Path(d)/'targets.parquet', order_by='user_id')
            if role == 'holdout':
                sealed = xc.write_sealed(col, writer)
            else:
                writer(col)
        xc.write_manifest(col, self.ds, role, anchor, dict(queries=16, users=int(frame['user_id'].nunique()),
                                                           rows=len(frame)), base or self.base, dict(CODE),
                          sealed=sealed)
        side = xc.new_output(xc.sidecar_dir(self.ds, col))
        xc.write_parquet(frame[KEYS+COLUMNS], side/xc.SIDECAR_FILE, order_by='user_id, item_id')
        xc.write_sidecar_manifest(side, self.ds, col, self.set_sha, COLUMNS, len(frame), dict(CODE))
        return col

    def cli(self, *argv):
        return xm.handle([argv[0], '--dataset', self.ds, *argv[1:]])

    def fit(self, series, arm, seed):
        return self.cli('fit', '--series', series, '--arm', arm, '--seed', str(seed))

    def fits(self, series, arms=xc.ARMS):
        for arm in arms:
            for seed in xc.SEEDS:
                self.fit(series, arm, seed)

    def report(self, series, arm, seed):
        return xc.read_json(xm.fit_dir(self.ds, series, arm, seed)/'report.json')

    def leakcheck(self, anchors=None, **override):
        """A leakcheck report as xfer_agent writes it, under leakcheck/<name>/report.json."""
        last, hold = self.A(20), self.A(40)
        cols = {xc.anchor_text(last): xc.output_dir(self.ds, 'collections', xc.collection_name('train', last)),
                xc.anchor_text(hold): xc.current_holdout_collection(self.ds, hold)}
        data = dict(format=xa.LEAKCHECK_FORMAT, dataset=self.ds, status='completed', ok=True, result='OK',
                    set_sha256=self.set_sha, set_digest='d', code=dict(CODE),
                    anchors=anchors if anchors is not None else
                    {a: dict(collection=xa._collection_identity(c), ok=True, result='OK') for a, c in cols.items()})
        data.update(override)
        self.leaks += 1
        path = xc.new_output(xc.output_dir(self.ds, 'leakcheck', f'lc-{self.leaks}'))/'report.json'
        path.write_text(json.dumps(data))
        return path

    def gate1(self, leak=None):
        leak = leak or self.leakcheck()
        return self.cli('gate', '--stage', '1', '--leakcheck', str(leak))

    def open(self, gate):
        return self.cli('holdout-open', '--gate', str(self.root/gate['output']), '--quote', 'да')

    def forge(self, gate, change):
        """A copy of gate.json with ``change(checks)`` applied and a status consistent with the forged checks."""
        record = xc.read_json(self.root/gate['output'])
        change(record['checks'])
        record['status'] = xm.stage1_status(record['checks'])
        record['ok'] = all(record['status'].values())
        self.forged = getattr(self, 'forged', 0)+1
        path = xc.new_output(xc.output_dir(self.ds, 'gate', f'stage1-forged-{self.forged}'))/'gate.json'
        path.write_text(json.dumps(record))
        return dict(output=xm.rel(path))

    def assert_forgery_refused(self, gate, check, change):
        forged = self.forge(gate, change)
        self.assertTrue(xc.read_json(self.root/forged['output'])['ok'])
        with self.assertRaisesRegex(xc.ContractError, rf"checks differ from a recomputation: \['{check}'\]"):
            self.open(forged)
        self.assertFalse(xc.config_path(self.ds, 'holdout-open').exists())

    def rewrite_scores(self, series, arm, seed, change):
        """Rewrite a score file in place and update the report hashes; returns a restore function."""
        directory = xm.fit_dir(self.ds, series, arm, seed)
        report = directory/'report.json'
        name = self.report(series, arm, seed)['eval']['scores_file']
        saved = {p: p.read_bytes() for p in (report, directory/name)}
        scores = xc.read_parquet(directory/name)
        change(scores)
        (directory/name).unlink()
        xc.write_parquet(scores, directory/name, order_by='user_id, item_id')
        data = xc.read_json(report)
        data['eval']['scores_sha256'] = data['files'][name] = xc.sha256_file(directory/name)
        report.write_text(json.dumps(data))

        def restore():
            for path, raw in saved.items():
                path.write_bytes(raw)
        return restore

    def nan_scores(self, series, arm, seed):
        return self.rewrite_scores(series, arm, seed, lambda s: s.__setitem__('score', s['score'].where(s.index > 0)))


class Fits(World):
    def test_rows_paired_across_arms_and_seeds(self):
        for arm in xc.ARMS:
            self.fit('dev', arm, 2026)
        self.fit('dev', 'BA', 2027)
        reports = [self.report('dev', a, 2026) for a in xc.ARMS]+[self.report('dev', 'BA', 2027)]
        self.assertEqual(len({r['identity_digest'] for r in reports}), 1)
        populations = reports[0]['identity']['training_populations']
        self.assertEqual([p['anchor'] for p in populations], [10, 20])  # ascending, whatever the adapter order
        self.assertEqual([p['query_pool'] for p in populations], [16, 16])
        self.assertEqual([p['queries'] for p in populations], [12, 12])  # N caps the training queries
        capped = set(xc.cap_queries(range(16), 12))
        ctx = xm.Context(self.ds)
        con = xm.connect()
        blocks = {arm: xm.training_block(ctx, con, 'dev', 10, arm, 2026)[0] for arm in xc.ARMS}
        con.close()
        self.assertEqual(set(blocks['B']['user_id']), capped)
        for arm in ('BA', 'BApl'):
            pd.testing.assert_frame_equal(blocks[arm][KEYS+['f_num', 'f_cat', 'label', 'weight']], blocks['B'])
        self.assertEqual(populations[0]['rows'], len(blocks['B']))
        self.assertEqual(populations[0]['rows_sha256'], xm.rows_digest(blocks['B']))
        self.assertLess(len(blocks['B']), int(self.frames[10]['user_id'].isin(capped).sum()))  # sampled rows
        self.assertEqual(len({r['eval']['keys_sha256'] for r in reports}), 1)
        self.assertEqual(reports[0]['features']['agent'], [])
        self.assertEqual(reports[1]['features']['agent'], COLUMNS)
        self.assertNotIn('random_seed', reports[0]['identity']['recipe'])
        xm.check_pairing({(r['arm'], r['seed']): (None, r) for r in reports})

    def test_check_pairing_rejects_mismatched_fits(self):
        self.fit('dev', 'B', 2026)
        self.fit('dev', 'BA', 2026)
        good = [self.report('dev', 'B', 2026), self.report('dev', 'BA', 2026)]

        def pair(other):
            return {('B', 2026): (None, good[0]), ('BA', 2026): (None, other)}
        xm.check_pairing(pair(good[1]))
        other = json.loads(json.dumps(good[1]))
        other['identity']['training_populations'][0]['rows_sha256'] = '0'*64
        with self.assertRaisesRegex(xc.ContractError, 'digest mismatch'):
            xm.check_pairing(pair(other))
        other['identity_digest'] = xc.canonical_digest(other['identity'])
        with self.assertRaisesRegex(xc.ContractError, 'identities differ'):
            xm.check_pairing(pair(other))
        other = json.loads(json.dumps(good[1]))
        other['code'] = {'scripts/xfer_model.py': 'other'}
        with self.assertRaisesRegex(xc.ContractError, 'code differs'):
            xm.check_pairing(pair(other))
        other = json.loads(json.dumps(good[1]))
        other['eval']['keys_sha256'] = '1'*64
        with self.assertRaisesRegex(xc.ContractError, 'eval rows differ'):
            xm.check_pairing(pair(other))
        other = json.loads(json.dumps(good[1]))
        del other['identity']['training_populations'][0]['rows_sha256']
        other['identity_digest'] = xc.canonical_digest(other['identity'])
        with self.assertRaisesRegex(xc.ContractError, 'row digests'):
            xm.check_pairing(pair(other))

    def test_placebo_permutes_only_the_agent_block(self):
        ctx = xm.Context(self.ds)
        con = xm.connect()
        ba = xm.training_block(ctx, con, 'dev', 20, 'BA', 2026)
        pl = xm.training_block(ctx, con, 'dev', 20, 'BApl', 2026)
        again = xm.training_block(ctx, con, 'dev', 20, 'BApl', 2026)[0]
        other = xm.training_block(ctx, con, 'dev', 20, 'BApl', 2027)[0]
        con.close()
        rest = KEYS+['f_num', 'f_cat', 'label', 'weight']
        pd.testing.assert_frame_equal(ba[0][rest], pl[0][rest])
        perm = xc.permutation(2026, 20, 0, len(ba[0]))
        expected = ba[0][COLUMNS].iloc[perm].reset_index(drop=True)
        pd.testing.assert_frame_equal(pl[0][COLUMNS], expected)
        self.assertEqual(pl[3], dict(anchor=20, chunk=0, rows=len(ba[0])))
        pd.testing.assert_frame_equal(pl[0], again)
        self.assertFalse(pl[0][COLUMNS].equals(other[COLUMNS]))
        self.assertEqual(ba[2], pl[2])  # finite shares survive the permutation
        for column in COLUMNS:
            self.assertEqual(sorted(pl[0][column].dropna()), sorted(ba[0][column].dropna()))
        self.fit('dev', 'BApl', 2026)
        report = self.report('dev', 'BApl', 2026)
        permuted = report['permutation']['permuted']
        self.assertEqual(permuted[:2], [dict(anchor=p['anchor'], chunk=0, rows=p['rows'])
                                        for p in report['identity']['training_populations']])
        self.assertEqual(permuted[2], dict(anchor=30, chunk=0, rows=len(self.frames[30])))

    def test_kaggle_chunks_ascending_users_and_placebo_per_chunk(self):
        from catboost import CatBoostClassifier
        self.fit('dev', 'B', 2026)
        self.fit('dev', 'BA', 2026)
        ctx = xm.Context(self.ds)
        con = xm.connect()
        kaggle = xc.output_dir(self.ds, 'collections', 'kaggle-50')
        directory, _ = ctx.sidecar(kaggle)
        for arm in ('B', 'BA'):
            model = CatBoostClassifier()
            model.load_model(str(xm.fit_dir(self.ds, 'dev', arm, 2026)/xm.MODEL_FILE))
            big = xm.score_chunked(ctx, con, kaggle, arm, 2026, 50, model, 1000, directory)
            small = xm.score_chunked(ctx, con, kaggle, arm, 2026, 50, model, 7, directory)
            self.assertEqual((big[3]['chunks'], small[3]['chunks']), (1, 4))
            pd.testing.assert_frame_equal(xm.top_k(big[0], K), xm.top_k(small[0], K))
            self.assertEqual(len(big[0]), len(self.frames[50]))
        seen = []
        real = xm.predict

        def spy(ctx_, model_, frame, columns):
            seen.append(frame.copy())
            return real(ctx_, model_, frame, columns)
        with mock.patch.object(xm, 'predict', spy):
            placebo = xm.score_chunked(ctx, con, kaggle, 'BApl', 2026, 50, model, 7, directory)
        con.close()
        self.assertEqual([p['chunk'] for p in placebo[2]], [0, 1, 2, 3])
        self.assertEqual(sum(p['rows'] for p in placebo[2]), len(self.frames[50]))
        chunk1 = self.frames[50][self.frames[50]['user_id'].between(7, 13)].reset_index(drop=True)
        self.assertEqual(seen[1]['user_id'].tolist(), chunk1['user_id'].tolist())
        perm = xc.permutation(2026, 50, 1, len(chunk1))
        pd.testing.assert_frame_equal(seen[1][COLUMNS].reset_index(drop=True),
                                      chunk1[COLUMNS].iloc[perm].reset_index(drop=True), check_dtype=False)
        pd.testing.assert_frame_equal(seen[1][['f_num']], chunk1[['f_num']], check_dtype=False)

    def test_base_dev_needs_no_prereg(self):
        base = xc.make_base(self.ds, dict(sources=['pop', 'x']), [dict(name='f_num', formula='y', missing='0'),
                                                                   dict(name='f_cat', formula='c', missing='NULL')],
                            ['f_cat'])
        root = self.root/'artifacts'/'xfer'/self.ds/'base-dev'/'it1'/'collections'
        for role, anchor in (('train', 10), ('train', 20), ('val', 30)):
            col = root/xc.collection_name(role, anchor)
            shutil.copytree(xc.output_dir(self.ds, 'collections', col.name), col)
            (col/'manifest.json').unlink()
            files = {p.name for p in col.iterdir()}
            self.assertEqual(files, {'frame.parquet', 'labels.parquet', 'targets.parquet'})
            xc.write_manifest(col, self.ds, role, anchor, dict(queries=16), base, dict(CODE))
        path = self.root/'base.json'
        path.write_text(json.dumps(base))
        out = self.cli('fit', '--base-dev', '--base', str(path), '--output', 'it1/fit', '--collections', str(root))
        self.assertEqual((out['arm'], out['seed'], out['series']), ('B', 2026, 'dev'))
        self.assertIn('metric', out['eval'])
        self.assertIn('pop_metric', out['eval'])
        with self.assertRaises(xc.ContractError):  # collections of another base are refused
            self.cli('fit', '--base-dev', '--base', str(path), '--output', 'it2')

    def test_failed_fit_is_moved_aside_completed_is_kept(self):
        with mock.patch.object(xm, 'make_pool', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.fit('dev', 'B', 2026)
        self.assertEqual(self.report('dev', 'B', 2026)['status'], 'failed')
        out = self.fit('dev', 'B', 2026)
        moved = self.root/out['moved_failed']
        self.assertTrue(moved.name.startswith('B2026.failed-'))
        self.assertEqual(xc.read_json(moved/'report.json')['status'], 'failed')
        self.assertEqual(self.report('dev', 'B', 2026)['status'], 'completed')
        before = xc.sha256_file(xm.fit_dir(self.ds, 'dev', 'B', 2026)/'report.json')
        with self.assertRaisesRegex(xc.ContractError, 'only a failed fit'):
            self.fit('dev', 'B', 2026)
        self.assertEqual(xc.sha256_file(xm.fit_dir(self.ds, 'dev', 'B', 2026)/'report.json'), before)

    def test_collection_identity_matches_xfer_agent(self):
        inside = xc.output_dir(self.ds, 'collections', 'val-30')
        outside = Path(tempfile.mkdtemp(dir=self.root.parent))/'val-30'
        self.addCleanup(shutil.rmtree, outside.parent)
        shutil.copytree(inside, outside)
        for path in (inside, outside):
            self.assertEqual(xm.collection_identity(path), xa._collection_identity(path))
        self.assertTrue(xm.collection_identity(outside)['path'].startswith('/'))

    def test_empty_agent_set_refuses_ba(self):
        ctx = xm.Context(self.ds)
        ctx.columns = []
        for arm in ('BA', 'BApl'):
            with self.assertRaisesRegex(xc.ContractError, 'BA не построена'):
                xm.fit(ctx, 'dev', arm, 2026, xm.fit_dir(self.ds, 'dev', arm, 2026))
            self.assertFalse(xm.fit_dir(self.ds, 'dev', arm, 2026).exists())
        with self.assertRaisesRegex(xc.ContractError, 'BA не построена'):
            ctx.sidecar(xc.output_dir(self.ds, 'collections', 'val-30'))

    def test_prereg_guards(self):
        prereg = xc.config_path(self.ds, 'prereg')
        prereg.unlink()
        with self.assertRaisesRegex(xc.ContractError, 'Holdout collections exist'):
            xm.prereg(self.ds)
        holdout = xc.output_dir(self.ds, 'collections', 'holdout-40')
        aside = holdout.with_name('moved')
        holdout.rename(aside)
        agent_fit = xm.fit_dir(self.ds, 'dev', 'BApl', 2026)
        agent_fit.mkdir(parents=True)
        with self.assertRaisesRegex(xc.ContractError, 'BA/BApl fits exist'):
            xm.prereg(self.ds)
        agent_fit.rmdir()
        doc = self.root/xm.DATASET_DOCS[self.ds]
        doc.write_text('changed\n')
        with self.assertRaisesRegex(xc.ContractError, 'committed clean'):
            xm.prereg(self.ds)
        doc.write_text('contract\n')
        xm.handle(['prereg', '--dataset', self.ds])
        record = xc.read_json(prereg)
        self.assertEqual(record['gate']['arms']['B'], ['finite', 'floor'])
        self.assertEqual(record['gate']['arms']['BA'], ['finite', 'floor', 'leakcheck', 'parity'])
        self.assertEqual(record['gate']['stage2_arms']['B'], ['finite'])
        self.assertIn('ascending user_id', record['kaggle_chunk_order'])


class Gates(World):
    """Gate 1 per arm, holdout-open checks, crash rerun of holdout."""

    def test_gate1_per_arm_failures_and_open_checks(self):
        self.fits('dev')
        self.fits('holdout')
        with self.assertRaises(xc.ContractError):
            self.cli('holdout')
        ctx = xm.Context(self.ds)
        good = xm.leakcheck_check(ctx, self.leakcheck())
        self.assertTrue(good['ok'], good)
        outside = self.root/'artifacts'/'xfer'/self.ds/'leak.json'
        outside.write_text(self.leakcheck().read_text())
        hold = xc.anchor_text(self.A(40))
        identities = xc.read_json(self.leakcheck())['anchors']
        bad = dict(outside=outside, leak=self.leakcheck(result='LEAK', ok=False),
                   failed=self.leakcheck(status='failed'), format=self.leakcheck(format='other'),
                   dataset=self.leakcheck(dataset='sber' if self.ds == 'tinkoff' else 'tinkoff'),
                   set=self.leakcheck(set_sha256='0'*64),
                   extra=self.leakcheck(anchors=dict(identities, extra=identities[hold])),
                   missing=self.leakcheck(anchors={hold: identities[hold]}),
                   identity=self.leakcheck(anchors=dict(identities, **{hold: dict(identities[hold], collection=dict(
                       identities[hold]['collection'], manifest_sha256='0'*64))})))
        for name, path in bad.items():
            with self.subTest(leakcheck=name):
                self.assertFalse(xm.leakcheck_check(ctx, path)['ok'])
        gate = self.gate1(bad['identity'])
        self.assertEqual(gate['status'], dict(B=True, BA=False, BApl=False))
        self.assertFalse(gate['gate_ok'])
        self.assertEqual(xc.read_json(self.root/gate['output'])['checks']['leakcheck']['sha256'],
                         xc.sha256_file(bad['identity']))
        self.assert_forgery_refused(gate, 'leakcheck', lambda c: c['leakcheck'].update(ok=True, problems=[]))
        # a passing leakcheck swapped in after the gate: its hash is recorded
        good_gate = self.gate1(self.leakcheck())
        leak_file = self.root/xc.read_json(self.root/good_gate['output'])['checks']['leakcheck']['path']
        raw = leak_file.read_bytes()
        leak_file.write_text(json.dumps(dict(json.loads(raw), note='edited')))
        with self.assertRaisesRegex(xc.ContractError, 'Leakcheck report changed'):
            self.open(good_gate)
        leak_file.write_bytes(raw)

        # the floor reads the hashed metrics file, not the number in report.json
        report = xm.fit_dir(self.ds, 'dev', 'B', 2026)/'report.json'
        raw = report.read_bytes()
        data = json.loads(raw)
        data['eval']['metric'] = -1.0
        report.write_text(json.dumps(data))
        gate = self.gate1()
        record = xc.read_json(self.root/gate['output'])
        on_file = xm.mean(xm.read_metrics(report.parent, data))
        self.assertTrue(record['checks']['floor']['B2026']['ok'])
        self.assertEqual(record['checks']['floor']['B2026']['metric'], on_file)
        self.assertNotEqual(on_file, -1.0)
        self.assertTrue(gate['status']['B'])
        report.write_bytes(raw)

        # parity: agent fits record eval shares far below the training shares
        reports = [xm.fit_dir(self.ds, 'holdout', a, s)/'report.json' for a in ('BA', 'BApl') for s in xc.SEEDS]
        saved = {p: p.read_bytes() for p in reports}
        for path in reports:
            data = xc.read_json(path)
            data['agent_nonnull']['eval'] = {c: 0.01 for c in COLUMNS}
            path.write_text(json.dumps(data))
        gate = self.gate1()
        self.assertEqual(gate['status'], dict(B=True, BA=False, BApl=False))
        record = xc.read_json(self.root/gate['output'])
        self.assertFalse(record['checks']['parity']['ok'])

        def pass_parity(checks):
            checks['parity']['ok'] = True
            for value in checks['parity']['columns'].values():
                value['ok'] = True
        self.assert_forgery_refused(gate, 'parity', pass_parity)
        for path, raw in saved.items():
            path.write_bytes(raw)

        # non-finite scores fail only their arm
        restore = self.nan_scores('holdout', 'BA', 2027)
        gate = self.gate1()
        self.assertEqual(gate['status'], dict(B=True, BA=False, BApl=True))
        self.assertEqual(xc.gate_arms(gate['status']), ['Pop', 'B'])
        self.assert_forgery_refused(gate, 'finite', lambda c: c['finite']['holdout'].update(BA2027=True))
        restore()
        restore = self.nan_scores('dev', 'B', 2026)
        self.assertEqual(self.gate1()['status'], dict(B=False, BA=True, BApl=True))
        restore()

        gate = self.gate1()
        self.assertTrue(gate['gate_ok'], gate)
        out = io.StringIO()
        with mock.patch('sys.stdout', out):
            code = xm.main(['gate', '--dataset', self.ds, '--stage', '1', '--leakcheck', str(self.leakcheck())])
        line = json.loads(out.getvalue())
        self.assertEqual((code, line['ok'], line['gate_ok']), (0, True, True))
        path = self.root/gate['output']
        record = xc.read_json(path)
        self.assertEqual(sorted(record['score_files']), sorted(
            xm.rel(xm.fit_dir(self.ds, 'holdout', a, s)/f'scores-holdout-{xc.anchor_text(self.A(40))}.parquet')
            for a in xc.ARMS for s in xc.SEEDS))

        # holdout-open: path pattern, recomputed status, hashes of scores and reports
        elsewhere = self.root/'artifacts'/'xfer'/self.ds/'gate'/'gate.json'
        shutil.copy(path, elsewhere)
        with self.assertRaisesRegex(xc.ContractError, 'stage1-'):
            self.cli('holdout-open', '--gate', str(elsewhere), '--quote', 'да')
        forged = xc.new_output(xc.output_dir(self.ds, 'gate', 'stage1-forged'))/'gate.json'
        forged.write_text(json.dumps(dict(record, status=dict(B=True, BA=True, BApl=False), ok=False)))
        with self.assertRaisesRegex(xc.ContractError, 'differs from its checks'):
            self.cli('holdout-open', '--gate', str(forged), '--quote', 'да')
        restore = self.rewrite_scores('holdout', 'BA', 2026, lambda s: s.__setitem__('score', s['score']+1.0))
        with self.assertRaisesRegex(xc.ContractError, 'changed since the gate'):
            self.open(gate)
        restore()
        # an incomplete gate: one score entry (or fit report) dropped, hashes of the rest intact
        for key in ('score_files', 'fit_reports'):
            trimmed = dict(record, **{key: dict(sorted(record[key].items())[1:])})
            self.forged = getattr(self, 'forged', 0)+1
            short = xc.new_output(xc.output_dir(self.ds, 'gate', f'stage1-short-{self.forged}'))/'gate.json'
            short.write_text(json.dumps(trimmed))
            with self.subTest(dropped=key), self.assertRaisesRegex(xc.ContractError, 'differ from the .*fits in force'):
                self.cli('holdout-open', '--gate', str(short), '--quote', 'да')
        self.assertFalse(xc.config_path(self.ds, 'holdout-open').exists())
        report = xm.fit_dir(self.ds, 'dev', 'B', 2027)/'report.json'
        raw = report.read_bytes()
        report.write_text(json.dumps(dict(json.loads(raw), note='edited')))
        with self.assertRaisesRegex(xc.ContractError, 'Fit report changed'):
            self.open(gate)
        report.write_bytes(raw)
        self.assertFalse(xc.config_path(self.ds, 'holdout-open').exists())

        opened = self.open(gate)
        self.assertEqual(opened['arms'], ['Pop', 'B', 'BA', 'BApl'])
        with self.assertRaises(xc.ContractError):  # the receipt exists already
            self.open(gate)
        with self.assertRaises(xc.ContractError):  # not committed yet
            self.cli('holdout')
        receipt = xc.config_path(self.ds, 'holdout-open')
        self.commit(receipt)

        # holdout: changed score hash, crashed earlier run
        restore = self.rewrite_scores('holdout', 'BApl', 2026, lambda s: s.__setitem__('score', -s['score']))
        with self.assertRaisesRegex(xc.ContractError, 'not the one hashed'):
            self.cli('holdout')
        restore()
        crashed = xc.new_output(xc.output_dir(self.ds, 'holdout', 'crashed'))
        with self.assertRaisesRegex(xc.ContractError, 'need a deviation'):
            self.cli('holdout')
        deviations = xc.config_path(self.ds, 'deviations')
        deviations.write_text(json.dumps(dict(format=xc.DEVIATIONS_FORMAT, dataset=self.ds, records=[
            dict(id='d1', step='holdout', supersedes=['artifacts/xfer/other'])])))
        self.commit(deviations)
        with self.assertRaisesRegex(xc.ContractError, 'does not name'):
            self.cli('holdout')
        deviations.write_text(json.dumps(dict(format=xc.DEVIATIONS_FORMAT, dataset=self.ds, records=[
            dict(id='d1', step='holdout', supersedes=[xm.rel(crashed)])])))
        with self.assertRaisesRegex(xc.ContractError, 'must be committed'):
            self.cli('holdout')
        self.commit(deviations)
        result = self.cli('holdout')
        self.assertEqual(xc.read_json(xc.config_path(self.ds, 'holdout'))['reruns_superseded'], [xm.rel(crashed)])
        self.assertEqual(sorted(result['metrics']), sorted([f'{a}{s}' for a in xc.ARMS for s in xc.SEEDS]+['Pop']))
        with self.assertRaises(xc.ContractError):  # one holdout per dataset
            self.cli('holdout')
        # a committed receipt that disappeared still blocks a second opening
        self.commit(xc.config_path(self.ds, 'holdout'))
        xc.config_path(self.ds, 'holdout').unlink()
        runs = xc.output_dir(self.ds, 'holdout')
        runs.rename(runs.with_name('holdout-aside'))
        with self.assertRaisesRegex(xc.ContractError, 'holdout runs once'):  # Git history remembers the result
            self.cli('holdout')
        receipt.unlink()
        with self.assertRaisesRegex(xc.ContractError, 'committed before'):
            self.open(gate)

    def test_b_failing_floor_opens_pop_only(self):
        self.fits('dev')
        self.fits('holdout')
        frames = {self.A(k): f for k, f in self.frames.items()}

        def oracle(adapter, A, users, k):
            frame = frames[A].sort_values(['user_id', 'label', 'item_id'], ascending=[True, False, True])
            top = frame[frame['user_id'].isin(users)].groupby('user_id').head(k).copy()
            top['rank'] = top.groupby('user_id').cumcount()+1
            return top[KEYS+['rank']].reset_index(drop=True)
        with mock.patch.object(FakeAdapter, 'pop', oracle):
            gate = self.gate1()
            self.assertFalse(gate['status']['B'])

            def pass_floor(checks):
                for value in checks['floor'].values():
                    value['ok'] = True
            self.assert_forgery_refused(gate, 'floor', pass_floor)
            opened = self.open(gate)
        self.assertEqual(opened['arms'], ['Pop'])
        self.commit(xc.config_path(self.ds, 'holdout-open'))
        with mock.patch.object(FakeAdapter, 'metric', autospec=True, side_effect=FakeAdapter.metric) as metric:
            result = self.cli('holdout')
        self.assertEqual(metric.call_count, 1)
        self.assertEqual(sorted(result['metrics']), ['Pop'])
        self.assertEqual(result['verdict_transfer'], xc.NOT_COMPUTED)
        self.assertNotIn('D', xc.read_json(xc.config_path(self.ds, 'holdout')))


class Flow(World):
    def test_full_reading_then_final_series(self):
        self.fits('dev')
        contrast = self.cli('contrast')
        self.assertEqual(sorted(contrast['contrasts']), ['BA-B', 'BApl-B'])
        stored = xc.read_json(self.root/contrast['output']/'contrast.json')
        means = {a: np.mean([stored['metrics'][f'{a}{s}'] for s in xc.SEEDS]) for a in xc.ARMS}
        for alt in ('BA', 'BApl'):  # alternative minus reference
            self.assertAlmostEqual(stored['contrasts'][f'{alt}-B']['seed_mean']['mean'], means[alt]-means['B'])
        self.fits('holdout')
        gate = self.gate1()
        self.assertTrue(gate['gate_ok'], gate)
        hold = xc.output_dir(self.ds, 'collections', xc.collection_name('holdout', self.A(40)))
        with self.assertRaises(xc.ContractError):
            xm.final_labels(hold)
        self.open(gate)
        self.commit(xc.config_path(self.ds, 'holdout-open'))
        result = self.cli('holdout')
        self.assertEqual(sorted(result['metrics']), sorted([f'{a}{s}' for a in xc.ARMS for s in xc.SEEDS]+['Pop']))
        label = xm.DATASET_LABEL[self.ds]
        self.assertIn(result['verdict_transfer'], (xc.VERDICT_TRANSFER[0].format(dataset=label),)
                      + xc.VERDICT_TRANSFER[1:])
        self.assertIn(result['verdict_content'], xc.VERDICT_CONTENT)
        stored = xc.read_json(xc.config_path(self.ds, 'holdout'))
        self.assertEqual(sorted(stored['D']), ['2026', '2027'])
        self.assertEqual(sorted(stored['descriptive']), ['BApl_minus_B', 'D', 'P'])
        for s in xc.SEEDS:
            self.assertAlmostEqual(stored['D'][str(s)]['mean'], stored['metrics'][f'BA{s}']-stored['metrics'][f'B{s}'])
        # final reads holdout labels only with the committed result receipt
        with self.assertRaises(xc.ContractError):
            xm.final_labels(hold)
        with self.assertRaises(xc.ContractError):
            self.fit('final', 'B', 2026)
        shutil.rmtree(xm.fit_dir(self.ds, 'final', 'B', 2026))
        self.commit(xc.config_path(self.ds, 'holdout'))
        labels, targets = xm.final_labels(hold)
        self.assertEqual(len(labels), len(self.frames[40]))
        with self.assertRaises(xc.ContractError):  # BApl is not a final arm on this fixture
            self.fit('final', 'BApl', 2026)
        self.fits('final', ('B', 'BA'))
        populations = self.report('final', 'BA', 2026)['identity']['training_populations']
        self.assertEqual([(p['anchor'], p['role'], p['queries']) for p in populations],
                         [(self.A(20), 'train', 12), (self.A(30), 'val', 12), (self.A(40), 'holdout', 12)])

        # gate 2 fails: nothing assembled, exit 1
        restore = self.nan_scores('final', 'BA', 2026)
        out = io.StringIO()
        with mock.patch('sys.stdout', out):
            code = xm.main(['score', '--dataset', self.ds])
        line = json.loads(out.getvalue())
        self.assertEqual((code, line['ok']), (1, False))
        self.assertIn('Gate 2 failed', line['error'])
        self.assertFalse(xc.output_dir(self.ds, 'kaggle').exists())
        gates = sorted(xc.output_dir(self.ds, 'gate').glob('stage2-*/gate.json'))
        self.assertEqual(xc.read_json(gates[-1])['status'], dict(B=True, BA=False))
        restore()

        out = self.cli('score')
        self.assertEqual(sorted(out['files']), ['B2026', 'B2027', 'BA2026', 'BA2027'])
        self.assertEqual(out['gate']['stage'], 2)
        self.assertEqual(out['gate']['status'], dict(B=True, BA=True))
        reading = self.cli('reading', '--private', json.dumps(dict(B2026=0.2, B2027=0.21, BA2026=0.3, BA2027=0.31)))
        self.assertEqual(reading['reading'], 'BA выше B на обоих зёрнах')


class IsoFlow(Flow):
    """The S-style world: ISO-date anchors, dataset sber."""

    DATASET = 'sber'
    MAP = ISO_ANCHORS

    def test_iso_anchors_order_and_placebo(self):
        self.fit('dev', 'BApl', 2026)
        report = self.report('dev', 'BApl', 2026)
        anchors = [p['anchor'] for p in report['identity']['training_populations']]
        self.assertEqual(anchors, ['2020-06-10', '2020-06-24'])
        ctx = xm.Context(self.ds)
        con = xm.connect()
        ba = xm.training_block(ctx, con, 'dev', '2020-06-24', 'BA', 2026)[0]
        pl = xm.training_block(ctx, con, 'dev', '2020-06-24', 'BApl', 2026)[0]
        con.close()
        perm = xc.permutation(2026, '2020-06-24', 0, len(ba))
        pd.testing.assert_frame_equal(pl[COLUMNS], ba[COLUMNS].iloc[perm].reset_index(drop=True))
        self.assertEqual(report['permutation']['permuted'][-1]['anchor'], '2020-07-08')
        leak = xc.read_json(self.leakcheck())
        self.assertEqual(sorted(leak['anchors']), ['2020-06-24', '2020-07-22'])
        self.assertTrue(xm.leakcheck_check(ctx, self.leakcheck())['ok'])


class Units(unittest.TestCase):
    def test_parity_math(self):
        self.assertTrue(xm.parity_ok(0.25, [0.5, 0.6]))   # 0.5 * min
        self.assertFalse(xm.parity_ok(0.2499, [0.5, 0.6]))
        self.assertTrue(xm.parity_ok(1.2, [0.5, 0.6]))    # 2 * max
        self.assertFalse(xm.parity_ok(1.2001, [0.5, 0.6]))
        self.assertFalse(xm.parity_ok(0.5, []))
        result = xm.parity({'10': dict(a=0.4, b=0.9), '20': dict(a=0.8, b=0.9)}, dict(a=0.19, b=0.9), ['a', 'b'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['columns']['a'], dict(share=0.19, min=0.4, max=0.8, ok=False))
        self.assertTrue(result['columns']['b']['ok'])

    def test_finite_shares_ignore_inf_and_nan(self):
        frame = pd.DataFrame(dict(a=[1.0, np.inf, np.nan, -np.inf], b=pd.array([1, None, 2, 3], dtype='Int64')))
        self.assertEqual(xm.finite_shares(frame, ['a', 'b']), dict(a=0.25, b=0.75))

    def test_category_values_per_value(self):
        self.assertEqual(list(xm.category_values(pd.Series([1.0, 2.5, None, 3.0]))),
                         ['1', '2.5', xm.MISSING_CATEGORY, '3'])
        self.assertEqual(list(xm.category_values(pd.Series(['a', 3.0, 3, None], dtype=object))),
                         ['a', '3', '3', xm.MISSING_CATEGORY])
        self.assertEqual(list(xm.category_values(pd.Series(pd.array([7, None], dtype='Int64')))),
                         ['7', xm.MISSING_CATEGORY])
        self.assertEqual(list(xm.category_values(pd.Series(['x', None], dtype='str'))), ['x', xm.MISSING_CATEGORY])

    def test_top_k_ties_by_item(self):
        scores = pd.DataFrame(dict(user_id=[1, 1, 1, 2, 2], item_id=[5, 3, 4, 9, 8], score=[0.1, 0.1, 0.2, 0.0, 0.0]))
        ranked = xm.top_k(scores, 2)
        self.assertEqual(ranked.values.tolist(), [[1, 4, 1], [1, 3, 2], [2, 8, 1], [2, 9, 2]])

    def values(self, ba_shift, pl_shift):
        rng = np.random.default_rng(0)
        out = {}
        for s in xc.SEEDS:
            base = rng.random(200)
            noise = 0.01*rng.normal(size=200)
            out[('B', s)] = dict(enumerate(base))
            out[('BA', s)] = dict(enumerate(base+ba_shift+noise))
            out[('BApl', s)] = dict(enumerate(base+ba_shift-pl_shift))
        return out

    def test_verdict_direction(self):
        up = xm.readings(self.values(0.2, 0.2), 'tinkoff')
        self.assertEqual(up['verdict_transfer'], xc.VERDICT_TRANSFER[0].format(dataset='Tinkoff'))
        self.assertEqual(up['verdict_content'], xc.VERDICT_CONTENT[0])
        self.assertIn('повышают', up['verdict_transfer'])
        self.assertGreater(up['descriptive']['D']['mean'], 0)
        self.assertTrue(all(up['D'][str(s)]['mean'] > 0 for s in xc.SEEDS))
        down = xm.readings(self.values(-0.2, -0.2), 'sber')
        self.assertEqual(down['verdict_transfer'], xc.VERDICT_TRANSFER[1])
        self.assertEqual(down['verdict_content'], xc.VERDICT_CONTENT[1])
        self.assertLess(down['descriptive']['D']['mean'], 0)
        self.assertLess(down['descriptive']['P']['mean'], 0)

    def test_contrast_sign(self):
        values = self.values(0.2, 0.0)
        out = xm.contrasts(values, 'B', ['BA', 'BApl'])
        self.assertGreater(out['BA-B']['seed_mean']['mean'], 0.19)
        self.assertGreater(out['BApl-B']['per_seed']['2026']['ci'][0], 0)
        out = xm.contrasts(self.values(-0.2, 0.0), 'B', ['BA'])
        self.assertLess(out['BA-B']['seed_mean']['ci'][1], 0)

    def test_cli_requires_isolated_python(self):
        out = io.StringIO()
        with mock.patch('sys.stdout', out):
            code = xm.main(['contrast', '--dataset', 'tinkoff'])
        self.assertEqual(code, 1)
        self.assertIn('python -I', json.loads(out.getvalue())['error'])


if __name__ == '__main__':
    unittest.main()
