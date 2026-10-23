"""Synthetic tests of scripts/otto_model.py (docs/otto-design.md §6, §8, §10, §11).

No real OTTO data is read: collections, BA frames and receipts are built in a
throwaway Git repository that stands in for ROOT, with a committed synthetic
base, set and prereg (code_identity is mocked as in test_otto_data). Frames carry
the stored types of otto_data (ranks USMALLINT). The agent's outputs are simulated
in its formats: the set (otto-set-v1, ``columns``), sidecars (sidecar.json and
parts) and leakcheck reports. CatBoost fits are tiny (5 trees, depth 2, 2 threads).
"""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from scripts import otto_common as oc
from scripts import otto_data as od
from scripts import otto_model as om

REPO = Path(om.__file__).resolve().parents[1]
FEATURES = ['f_signal', 'h_rank', 'pop_rank_clicks', 'pop_rank_carts', 'pop_rank_orders']
RANKS = FEATURES[1:]
AGENT = ['ag_src_x_rank', 'ag_src_x_score', 'ag_good']
SET_DIGEST = '5'*64
AGENT_SET = dict(format=oc.SET_FORMAT, digest=SET_DIGEST, columns=AGENT,
                 proposals=[dict(id='r1p1', kind='table', columns=['v']),
                            dict(id='r1p2', kind='source', columns=AGENT[:2]),
                            dict(id='r2p1', kind='feature', columns=AGENT[2:])],
                 audit=dict(verdict='clean', set_digest=SET_DIGEST))
SMALL = dict(iterations=5, depth=2, thread_count=2)
QUOTE = 'да, открывай holdout OTTO, и для этапа 2 тоже'
WHEN = '2026-10-24T10:00:00+03:00'
IDENTITY = dict(files={'scripts/otto_common.py': 'a'*64, 'scripts/otto_model.py': 'c'*64}, missing=[])
POPULAR = list(range(500, 520))


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


def base():
    return oc.make_base({}, [dict(name=n, formula=n, missing='NULL') for n in FEATURES])


def make_fold(first, n, seed, short_every=0, outside_every=0):
    """Frame of B, BA frame and labels of one synthetic fold.

    Each session has 25 own candidates (10 when ``short_every`` divides it) plus the 20
    popular aids POPULAR with pop_rank_<type>, so Pop always holds 20 aids per type; labels
    follow ``f_signal``; the BA frame adds three agent aids per session and the columns AGENT.
    ``outside_every`` puts every label of a session outside its candidates.
    """
    rng = np.random.default_rng(seed)
    orders = {t: rng.permutation(len(POPULAR)) for t in oc.TYPES}
    frame, agent, labels = [], [], []
    for s in range(first, first+n):
        size = 10 if short_every and s % short_every == 0 else 25
        aids = [int(a) for a in rng.choice(np.arange(1, 400), size, replace=False)]
        signal = rng.normal(size=size)
        order = np.argsort(-signal)
        rows = [(s, a, float(v), float(i+1) if i < 8 else math.nan, math.nan, math.nan, math.nan)
                for i, (a, v) in enumerate(zip(aids, signal))]
        rows += [(s, a, float(rng.normal()-2), math.nan, *(float(orders[t][i]+1) for t in oc.TYPES))
                 for i, a in enumerate(POPULAR)]
        for row in rows:
            frame.append(row)
            good = math.nan if rng.random() < 0.1 else float(row[2] + rng.normal(scale=0.5))
            agent.append(row + (math.nan, math.nan, good))
        for r, a in enumerate(int(x) for x in rng.choice(np.arange(600, 700), 3, replace=False)):
            agent.append((s, a, float(rng.normal()-1), math.nan, math.nan, math.nan, math.nan, float(r+1),
                          float(-r), float(rng.normal()-1)))
        if outside_every and s % outside_every == 0:
            labels += [(s, t, 1000+s) for t in oc.TYPES]
        else:
            labels += [(s, 'clicks', aids[order[0]]), (s, 'carts', aids[order[0]]), (s, 'carts', aids[order[1]]),
                       (s, 'orders', aids[order[1]])]
    columns = ['session', 'aid', *FEATURES]
    return dict(frame=pd.DataFrame(frame, columns=columns),
                agent=pd.DataFrame(agent, columns=columns+AGENT),
                labels=pd.DataFrame(labels, columns=list(oc.LABEL_COLUMNS)))


def write_frame(frame, path, typed=True):
    """Parquet of a frame in (session, aid) order; ``typed``: the stored types of otto_data (ranks USMALLINT)."""
    con = duckdb.connect()
    con.register('frame_in', frame)
    cast = {c: ('FLOAT' if c.startswith(oc.AGENT_PREFIX) else 'USMALLINT' if typed and c in RANKS else 'DOUBLE')
            for c in frame.columns if c not in ('session', 'aid')}
    columns = ', '.join(['CAST(session AS BIGINT) AS session', 'CAST(aid AS BIGINT) AS aid']
                        + [f'CAST("{c}" AS {t}) AS "{c}"' for c, t in cast.items()])
    con.execute(f"COPY (SELECT {columns} FROM frame_in ORDER BY session, aid) TO '{path}' (FORMAT parquet)")
    con.close()


def write_sidecar(collection, frame, name='run1', sessions=None, batch=25, set_digest=SET_DIGEST,
                  manifest_sha256=None):
    """sidecars/<collection>/<name>/ in the otto_agent format: part-NNNNN.parquet of ``batch`` sessions and
    sidecar.json (otto-sidecar-v1) with every field of oc.SIDECAR_FIELDS."""
    collection = Path(collection)
    manifest = oc.read_json(collection/oc.MANIFEST_FILE)
    if sessions is not None:
        frame = frame[frame['session'].isin(set(sessions))]
    own = sorted(int(x) for x in frame['session'].unique())
    directory = oc.sidecar_dir(collection.name, name)
    directory.mkdir(parents=True)
    parts = {}
    for i in range(0, len(own), batch):
        chunk = own[i:i+batch]
        part = frame[frame['session'].isin(chunk)]
        path = directory/f'part-{i//batch:05d}.parquet'
        write_frame(part, path, typed=False)                   # base columns DOUBLE in the BA frame
        parts[path.name] = dict(sha256=oc.sha256_file(path), rows=int(len(part)), sessions=len(chunk))
    body = dict(format=oc.SIDECAR_FORMAT, collection=collection.name, role=manifest['role'], fold=manifest['fold'],
                manifest_sha256=manifest_sha256 or oc.sha256_file(collection/oc.MANIFEST_FILE),
                set_digest=set_digest, sessions=len(own), sessions_digest=oc.sessions_digest(own),
                batch=batch, rows=int(len(frame)), parts=parts, columns=list(frame.columns),
                agent_columns=[c for c in frame.columns if c.startswith(oc.AGENT_PREFIX)])
    oc.atomic_json(directory/oc.SIDECAR_REPORT, body)
    return directory


def leak_report(fold, collection, digest, **changes):
    """leakcheck/<name>/report.json body in the otto_agent format (otto-leakcheck-v1), passed."""
    body = dict(format=oc.LEAKCHECK_FORMAT, ok=True, fold=fold, collection=collection, sessions=10,
                sessions_digest=digest, set_digest=SET_DIGEST, degenerate=[], history=dict(days=7), columns=AGENT,
                error=None, history_check=dict(sessions=10, keys_one_side=0, cells={}),
                batch_check=dict(sessions=10, batches=2, keys_one_side=0, cells={}), seconds=1.0,
                prefix_check=dict(rows=['9', '9'], sessions=['10', '10'], ok=True) if fold == 3 else None)
    body.update(changes)
    return body


class Repo(unittest.TestCase):
    """A throwaway Git repository standing in for ROOT: four fold collections, BA frames, base, set, prereg."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q')
        (self.root/'configs'/'datasets').mkdir(parents=True)
        (self.root/'artifacts'/'otto').mkdir(parents=True)
        (self.root/'README').write_text('x')
        git(self.root, 'add', 'README')
        git(self.root, 'commit', '-q', '-m', 'init')
        self.patch = mock.patch.object(oc, 'ROOT', self.root)
        self.patch.start()
        self.code_patch = mock.patch.object(oc, 'code_identity', return_value=IDENTITY)
        self.code_patch.start()
        self.base = base()
        self.folds = {2: make_fold(1, 60, 2, short_every=0, outside_every=9),
                      3: make_fold(1001, 60, 3, short_every=7),
                      4: make_fold(2001, 60, 4, short_every=7),
                      5: make_fold(3001, 30, 5, short_every=7)}
        for k, fold in self.folds.items():
            self.collection(k, fold)
        self.configs()

    def tearDown(self):
        self.code_patch.stop()
        self.patch.stop()
        for path in self.root.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        self.tmp.cleanup()

    def collection(self, k, fold):
        role = oc.FOLD_ROLE[k]
        name = oc.collection_name(role)
        col = oc.new_output(oc.output_dir('collections', name))
        if role != 'kaggle':
            (col/oc.PREFIX_DIR).mkdir()
            prefix = pd.DataFrame([(1, 1, 0, 0, 1)], columns=list(oc.EVENT_COLUMNS))
            oc.write_parquet(prefix, col/oc.PREFIX_DIR/'p.parquet')
        write_frame(fold['frame'], col/oc.FRAME_FILE)
        sealed, extra = None, None
        if role == 'holdout':
            sealed = oc.write_sealed(col, lambda d: oc.write_parquet(fold['labels'], d/oc.LABELS_FILE))
        elif role != 'kaggle':
            oc.write_parquet(fold['labels'], col/oc.LABELS_FILE)
            training = od.training_sessions(fold['labels'], n=40)
            extra = dict(training_sessions={t: len(v) for t, v in training.items()},
                         training_digest=oc.canonical_digest(training))
        oc.write_manifest(col, role, dict(sessions=int(fold['frame']['session'].nunique())), self.base, {},
                          sealed=sealed, extra=extra)
        if role == 'val':
            sessions = sorted(fold['frame']['session'].unique())
            oc.write_population(col, sessions[5:], rule='synthetic: all but the first five (probe pool)')
        write_sidecar(col, fold['agent'])

    def configs(self, prereg_extra=None, set_body=None):
        """Committed base, set and prereg naming them and the mocked code identity."""
        paths = {k: oc.config_path(k) for k in ('base', 'set', 'prereg')}
        paths['base'].write_text(json.dumps(self.base))
        paths['set'].write_text(json.dumps(set_body if set_body is not None else AGENT_SET))
        prereg = dict(base_sha256=oc.sha256_file(paths['base']), set_sha256=oc.sha256_file(paths['set']),
                      code=IDENTITY['files'], recipe=dict(om.RECIPE, bootstrap_type='Bayesian'), N_t=40,
                      SCORE_BATCH=7, agent_columns=AGENT)
        prereg.update(prereg_extra or {})
        prereg = {k: v for k, v in prereg.items() if v is not None}
        paths['prereg'].write_text(json.dumps(prereg))
        self.commit(*paths.values())

    def ctx(self, **kw):
        values = dict(mode='contract', prereg={'recipe': {'bootstrap_type': 'Bayesian'}}, prereg_sha256='0'*64,
                      code={}, recipe_overrides=SMALL, threads=2, memory='2GB', n_t=40, negatives=5, score_batch=7,
                      agent_columns=AGENT, set_digest=SET_DIGEST)
        values.update(kw)
        return om.Context(self.base, **values)

    def commit(self, *paths):
        git(self.root, 'add', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def ranked(self, path):
        return oc.read_parquet(path).sort_values(['session', 'type', 'rank']).reset_index(drop=True)

    def fit_eval(self, ctx, series, arms, seed, eval_too=True):
        for arm in arms:
            om.fit(ctx, series, arm, seed)
            if eval_too:
                om.evaluate(ctx, series, arm, seed)

    def leakcheck(self, f3=None, f4=None):
        """Passed F3 and F4 reports on the dev and the power-gate population; ``f3``/``f4`` change fields."""
        val, hold = oc.collection_dir('val'), oc.current_holdout_collection()
        reports = {3: leak_report(3, val.name, oc.sessions_digest(oc.read_population(val)), **(f3 or {})),
                   4: leak_report(4, hold.name, oc.holdout_population(hold)['sessions_digest'], **(f4 or {}))}
        paths = []
        for fold, body in reports.items():
            path = oc.leakcheck_path(f'F{fold}')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.unlink(missing_ok=True)
            oc.atomic_json(path, body)
            paths.append(path)
        return paths

    def residecar(self, k, frame, **kw):
        """Replace every sidecar of fold k's collection by one sidecar of ``frame``."""
        collection = oc.collection_dir(oc.FOLD_ROLE[k])
        shutil.rmtree(oc.output_dir('sidecars', collection.name))
        return write_sidecar(collection, frame, **kw)


# ================================================================== training rows (§6)

class TrainingRows(Repo):
    def block(self, frame_rows, type_='carts', negatives=5, sessions=None):
        con = duckdb.connect()
        con.register('fr_in', frame_rows)
        con.execute('CREATE TEMP VIEW fr AS SELECT * FROM fr_in')
        om.labels_view(con, oc.collection_dir('train')/oc.LABELS_FILE)
        chosen = om.training_sessions(con, 'lab', 40)
        out = om.training_rows(con, 'fr', 'lab', type_, chosen[type_] if sessions is None else sessions,
                               FEATURES, negatives)
        con.close()
        return out, chosen

    def test_negative_key_sql_matches_python_for_every_stored_type(self):
        con = duckdb.connect()
        for session, aid, t in [(1, 2, 'clicks'), (12_899_999, 1_855_602, 'orders'), (0, 0, 'carts')]:
            for kind in ('BIGINT', 'INTEGER', 'UINTEGER', 'UBIGINT'):
                key = om.negative_key_sql(t, f'CAST({session} AS {kind})', f'CAST({aid} AS {kind})')
                sql = con.execute(f'SELECT {key}').fetchone()[0]
                self.assertEqual(sql, om.negative_key(session, aid, t))
            self.assertEqual(sql, __import__('hashlib').sha256(f'{session}|{aid}|{t}|2026'.encode()).hexdigest())
        con.close()

    def test_negatives_are_the_smallest_keys_and_order_free(self):
        frame = self.folds[2]['frame']
        (block, dropped), chosen = self.block(frame)
        shuffled = frame.sample(frac=1, random_state=7).reset_index(drop=True)
        (again, _), _ = self.block(shuffled)
        pd.testing.assert_frame_equal(block, again)
        labels = self.folds[2]['labels']
        for s, rows in block.groupby('session'):
            positives = set(labels[(labels.session == s) & (labels.type == 'carts')]['aid'])
            candidates = frame[frame.session == s]['aid'].tolist()
            negatives = sorted((a for a in candidates if a not in positives),
                               key=lambda a: (om.negative_key(s, a, 'carts'), a))[:5]
            self.assertEqual(sorted(rows[rows.label == 0]['aid']), sorted(negatives))
            self.assertEqual(set(rows[rows.label == 1]['aid']), positives & set(candidates))
        self.assertTrue((block[['session', 'aid']].apply(tuple, axis=1).is_monotonic_increasing))
        self.assertEqual(dropped, sum(1 for s in chosen['carts'] if s % 9 == 0))   # labels outside candidates
        self.assertGreater(dropped, 0)

    def test_training_sessions_follow_sha256_order_and_otto_data(self):
        _, chosen = self.block(self.folds[2]['frame'])
        labels = self.folds[2]['labels']
        for t in oc.TYPES:
            self.assertEqual(chosen[t], oc.first_in_order(labels[labels.type == t]['session'], 40))
        manifest = oc.read_json(oc.collection_dir('train')/oc.MANIFEST_FILE)
        self.assertEqual(om.check_training_digest(manifest, chosen), 'equal')
        self.assertIn('not compared', om.check_training_digest(manifest, {t: v[:30] for t, v in chosen.items()}))
        swapped = dict(chosen, clicks=list(reversed(chosen['clicks'])))
        with self.assertRaisesRegex(oc.ContractError, 'training_digest'):
            om.check_training_digest(manifest, swapped)


# ================================================================== BApl permutation (§6)

class Permutation(unittest.TestCase):
    def test_key_and_block(self):
        for seed, k, phase, index in [(2026, 2, 0, 1), (2027, 4, 1, 3)]:
            expected = np.random.default_rng([20261022, seed, k, phase, index]).permutation(50)
            np.testing.assert_array_equal(om.permutation(seed, k, phase, index, 50), expected)
        self.assertFalse(np.array_equal(om.permutation(2026, 2, 0, 0, 50), om.permutation(2027, 2, 0, 0, 50)))
        matrix = np.arange(40, dtype=np.float32).reshape(10, 4)
        perm = om.permutation(2026, 3, 1, 0, 10)
        out = om.permute_block(matrix, [2, 3], perm)
        np.testing.assert_array_equal(out[:, :2], matrix[:, :2])
        np.testing.assert_array_equal(out[:, 2:], matrix[perm][:, 2:])
        np.testing.assert_array_equal(om.permute_block(matrix, [], perm), matrix)


# ================================================================== top-20 and Pop top-up (§6)

class Lists(unittest.TestCase):
    def test_top_lists_ties_by_aid(self):
        out = om.top_lists([1, 1, 1, 2], [9, 3, 5, 7], [0.5, 0.5, 0.9, 0.1], k=2)
        self.assertEqual(out.values.tolist(), [[1, 5, 1], [1, 3, 2], [2, 7, 1]])

    def test_fill_without_repeats(self):
        model = pd.DataFrame(dict(session=[1, 1], aid=[10, 11], rank=[1, 2]))
        pop = pd.DataFrame(dict(session=[1, 1, 1, 2], aid=[11, 12, 13, 20], rank=[1, 2, 3, 1]))
        out, topped, short = om.fill_lists(model, pop, [1, 2], k=3)
        self.assertEqual(out.values.tolist(), [[1, 10, 1], [1, 11, 2], [1, 12, 3], [2, 20, 1]])
        self.assertEqual((topped, short), (2, 1))


# ================================================================== whole pipeline on synthetic folds

class Pipeline(Repo):
    def test_fit_pairing_seed_and_rows(self):
        ctx = self.ctx()
        reports = {}
        for arm, seed in [('B', 2026), ('BA', 2026), ('BApl', 2026), ('BA', 2027)]:
            reports[(arm, seed)] = om.fit(ctx, 'holdout', arm, seed)
        om.check_pairing(reports.values())
        b, ba, pl, ba7 = (reports[k] for k in [('B', 2026), ('BA', 2026), ('BApl', 2026), ('BA', 2027)])
        for t in oc.TYPES:
            self.assertEqual(b['training'][t]['sessions_digest'], ba['training'][t]['sessions_digest'])
            self.assertEqual(ba['training'][t]['rows_digest'], pl['training'][t]['rows_digest'])
            self.assertEqual(ba['training'][t]['rows_digest'], ba7['training'][t]['rows_digest'])   # seed: no rows
            self.assertEqual(pl['training'][t]['permutation']['key'], [20261022, 2026, 3, 0, oc.TYPES.index(t)])
        self.assertEqual(ba['ba_frame'], dict(b_keys_missing=0, b_values_differ=0))
        self.assertEqual((b['training_digest'], b['sessions_without_rows']), ('equal', 0))
        self.assertEqual({k: v for k, v in ba['recipe'].items() if k != 'random_seed'},
                         {k: v for k, v in ba7['recipe'].items() if k != 'random_seed'})
        self.assertEqual((ba['recipe']['random_seed'], ba7['recipe']['random_seed']), (2026, 2027))
        self.assertEqual(ba['identity'], ba7['identity'])
        self.assertEqual(ba['features']['agent'], AGENT)
        with self.assertRaisesRegex(oc.ContractError, 'no BApl'):
            om.fit(ctx, 'final', 'BApl', 2026)
        with self.assertRaisesRegex(oc.ContractError, 'exist'):        # every output is new
            om.fit(ctx, 'holdout', 'B', 2026)

        # check_pairing refuses unpaired fits
        values = list(reports.values())
        other = copy.deepcopy(values)
        other[1]['identity']['sessions']['orders'] = 'f'*64
        with self.assertRaisesRegex(oc.ContractError, 'not paired'):
            om.check_pairing(other)
        other = copy.deepcopy(values)
        other[2]['training']['carts']['rows_digest'] = 'f'*64
        with self.assertRaisesRegex(oc.ContractError, 'different rows'):
            om.check_pairing(other)
        other = copy.deepcopy(values)
        other[2]['features']['agent'] = list(reversed(AGENT))
        with self.assertRaisesRegex(oc.ContractError, 'features differ'):
            om.check_pairing(other)
        other = copy.deepcopy(values)
        other[0]['recipe']['random_seed'] = 7
        with self.assertRaisesRegex(oc.ContractError, 'seed'):
            om.check_pairing(other)

    def test_ba_frame_must_hold_b_whole(self):
        ctx = self.ctx()
        agent = self.folds[2]['agent']
        chosen = od.training_sessions(self.folds[2]['labels'], n=40)
        session = chosen['clicks'][0]
        b_row = self.folds[2]['frame'].iloc[0]
        cases = [('lacks 1 training sessions', agent[agent.session != session]),
                 ('candidates of B', agent[~((agent.session == b_row.session) & (agent.aid == b_row.aid))]),
                 ('changes base values', agent.assign(h_rank=agent['h_rank'].where(
                     ~((agent.session == b_row.session) & (agent.aid == b_row.aid)), 99.0)))]
        for pattern, frame in cases:
            with self.subTest(pattern=pattern):
                self.assertIn(int(b_row.session), set().union(*chosen.values()))
                self.residecar(2, frame)
                ctx = self.ctx()                                    # a context caches the BA frame it read
                with self.assertRaisesRegex(oc.ContractError, pattern):
                    om.fit(ctx, 'dev', 'BA', 2026)
                report = oc.read_json(om.fit_dir('dev', 'BA', 2026)/om.REPORT_FILE)
                self.assertEqual(report['status'], 'failed')
        self.assertEqual(om.fit(ctx, 'dev', 'B', 2026)['sessions_without_rows'], 0)

    def test_ba_frame_check_runs_by_chunks_and_counts_every_chunk(self):
        ctx = self.ctx()
        collection = ctx.collection(2)
        con = om.connect(ctx)
        feature = ctx.features[0]
        try:
            b_paths = ctx.frame_paths(collection, 'B')
            con.execute(f'CREATE TEMP TABLE fr AS SELECT * FROM read_parquet({om.sql_list(b_paths)})')
            con.execute('CREATE TEMP TABLE s AS SELECT DISTINCT CAST(session AS BIGINT) AS session FROM fr')
            ids = [r[0] for r in con.execute('SELECT session FROM s ORDER BY session').fetchall()]
            self.assertGreater(len(ids), 6)
            with mock.patch.object(om, 'BA_CHECK_CHUNK', 3):
                self.assertEqual(om.check_ba_frame(con, ctx, collection, 'fr', 's'),
                                 dict(b_keys_missing=0, b_values_differ=0))
            # damage two chunks: drop one row of the first session, change one value of the last session
            con.execute(f'DELETE FROM fr WHERE session = {ids[0]} AND aid = (SELECT min(aid) FROM fr WHERE session = {ids[0]})')
            con.execute(f'UPDATE fr SET "{feature}" = 9999 WHERE session = {ids[-1]} '
                        f'AND aid = (SELECT min(aid) FROM fr WHERE session = {ids[-1]})')
            counts = {}
            for chunk in (3, 10**9):                       # by chunks and in one pass: the same counts
                with mock.patch.object(om, 'BA_CHECK_CHUNK', chunk), mock.patch.object(om, 'require'):
                    counts[chunk] = om.check_ba_frame(con, ctx, collection, 'fr', 's')
            self.assertEqual(counts[3], dict(b_keys_missing=1, b_values_differ=1))
            self.assertEqual(counts[3], counts[10**9])
            with mock.patch.object(om, 'BA_CHECK_CHUNK', 3):
                with self.assertRaisesRegex(oc.ContractError, 'lacks 1 candidates of B'):
                    om.check_ba_frame(con, ctx, collection, 'fr', 's')
            self.assertEqual(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = 'ba_check_chunks'"
                                         ).fetchone()[0], 0)
        finally:
            con.close()

    def test_batch_size_does_not_change_b_and_ba_and_bapl_keeps_base_columns(self):
        ctx = self.ctx()
        calls = []
        real = om.permute_block

        def spy(matrix, columns, perm):
            out = real(matrix, columns, perm)
            calls.append((matrix.copy(), list(columns), np.asarray(perm), out.copy()))
            return out
        for arm in ('B', 'BA', 'BApl'):
            om.fit(ctx, 'dev', arm, 2026)
            directory = om.fit_dir('dev', arm, 2026)
            runs = {}
            for name, batch in (('b3', 3), ('b1000', 1000), ('b3again', 3)):
                calls.clear()
                with mock.patch.object(om, 'permute_block', side_effect=spy):
                    report = om.evaluate(ctx, 'dev', arm, 2026, output=directory/name, batch=batch)
                runs[name] = self.ranked(Path(report['path'])/om.RANKED_FILE)
                self.assertTrue(report['finite_all'])
                self.assertEqual(sum(report['short_lists'].values()), 0)
                self.assertEqual(report['pop']['short_sessions'], {t: 0 for t in oc.TYPES})
                if arm == 'BApl':
                    batches = report['permutation']['batches']
                    self.assertEqual([b['key'] for b in batches],
                                     [[20261022, 2026, 3, 1, i] for i in range(len(batches))])   # k = eval fold F3
                    self.assertEqual(len(calls), len(batches))
                    base_idx = list(range(len(FEATURES)))
                    for matrix, columns, perm, out in calls:
                        self.assertEqual(columns, [len(FEATURES)+i for i in range(len(AGENT))])
                        np.testing.assert_array_equal(out[:, base_idx], matrix[:, base_idx])
                        np.testing.assert_array_equal(out[:, columns], matrix[perm][:, columns])
                else:
                    self.assertEqual(calls, [])
            pd.testing.assert_frame_equal(runs['b3'], runs['b3again'])            # reproducible per batch size
            if arm != 'BApl':
                pd.testing.assert_frame_equal(runs['b3'], runs['b1000'])
            lists = runs['b3']
            sizes = lists.groupby(['session', 'type'])['aid'].agg(['count', 'nunique'])
            self.assertTrue(((sizes['count'] == 20) & (sizes['nunique'] == 20)).all())
            self.assertEqual(sorted(lists['type'].unique()), sorted(oc.TYPES))

    def test_holdout_refused_without_receipts(self):
        ctx = self.ctx()
        with self.assertRaises(oc.ContractError):
            om.holdout(ctx)
        with self.assertRaises(oc.ContractError):
            om.holdout(ctx, stage=2)
        with self.assertRaises(oc.ContractError):          # final fits read F4 labels only after the result
            om.fit(ctx, 'final', 'B', 2026)
        with self.assertRaisesRegex(oc.ContractError, 'F5'):
            om.evaluate(ctx, 'final', 'B', 2026)
        self.assertFalse(oc.output_dir('holdout').exists())

    def test_stage2_holdout_needs_both_receipts(self):
        ctx = self.ctx()
        with self.assertRaisesRegex(oc.ContractError, 'stage-1 result'):
            om.holdout_open(ctx, oc.output_dir('gate', 'none')/om.GATE_FILE, stage=2)
        open2 = oc.config_path('holdout-open-2')
        open2.write_text(json.dumps(dict(format=oc.HOLDOUT_OPEN_2_FORMAT, scores={'x': 'a'*64}, arms=['B'])))
        self.commit(open2)
        with self.assertRaisesRegex(oc.ContractError, 'holdout-2.*closed'):       # no committed stage-1 result
            om.holdout(ctx, stage=2)
        git(self.root, 'rm', '-q', str(open2.relative_to(self.root)))
        git(self.root, 'commit', '-q', '-m', 'rm')
        result = oc.config_path('holdout')
        result.write_text(json.dumps(dict(format=om.RESULT_FORMAT, stage=1)))
        self.commit(result)
        with self.assertRaisesRegex(oc.ContractError, 'holdout-2.*closed'):       # result, but no stage-2 receipt
            om.holdout(ctx, stage=2)
        self.assertFalse(oc.output_dir('holdout').exists())

    def test_gates_receipts_holdout_and_kaggle(self):
        ctx = self.ctx()
        self.fit_eval(ctx, 'dev', oc.ARMS, 2026)
        contrast = om.contrast(ctx)
        self.assertEqual(len(contrast['D']), 2)
        self.assertIsNone(contrast['ba'])
        self.fit_eval(ctx, 'holdout', oc.ARMS, 2026, eval_too=False)
        with self.assertRaisesRegex(oc.ContractError, 'power gate'):   # F4 is scored on the power-gate population
            om.evaluate(ctx, 'holdout', 'B', 2026)
        self.assertFalse((om.fit_dir('holdout', 'B', 2026)/om.EVAL_DIR).exists())
        other = oc.output_dir('gate', 'power-0-other')               # a gate of another (superseded) collection
        other.mkdir(parents=True)
        (other/om.GATE_FILE).write_text(json.dumps(dict(format=om.GATE_FORMAT, kind='power',
                                                        population=dict(collection='holdout-F4-old'))))
        power = om.gate(ctx, 'power', contrast_path=contrast['path'])
        self.assertEqual(power['population']['n'], 60)    # Q_4 <= 1e6: every session
        with self.assertRaisesRegex(oc.ContractError, 'chosen once'):
            om.gate(ctx, 'power', contrast_path=contrast['path'])
        for arm in oc.ARMS:
            om.evaluate(ctx, 'holdout', arm, 2026)

        # leakcheck: a missing fold, ok:false, an error, another set or another population fails BA and BApl
        f3, _ = self.leakcheck()
        dev_digest = oc.read_json(f3)['sessions_digest']
        bad_cases = [(lambda: [f3], 'fold'), (lambda: self.leakcheck(f4=dict(ok=False)), 'ok is not true'),
                     (lambda: self.leakcheck(f4=dict(error='Timeout')), 'Timeout'),
                     (lambda: self.leakcheck(f3=dict(set_digest='6'*64)), 'another agent set'),
                     (lambda: self.leakcheck(f4=dict(sessions_digest=dev_digest)), 'another population'),
                     (lambda: self.leakcheck(f4=dict(batch_check=dict(keys_one_side=0, cells=2))), 'batch_check'),
                     (lambda: self.leakcheck(f3=dict(prefix_check=dict(ok=False))), 'prefix_check'),
                     (lambda: [], 'fold')]
        for leak, problem in bad_cases:
            with self.subTest(problem=problem):
                bad = om.gate(ctx, '1', 1, leak())
                self.assertEqual(bad['status'], dict(B=True, BA=False, BApl=False))
                self.assertFalse(bad['ok'])
                reports = oc.read_json(bad['path'])['checks']['leakcheck']['reports']
                if problem != 'fold':
                    self.assertTrue(any(problem in p for r in reports for p in r['problems']), reports)
        gate1 = om.gate(ctx, '1', 1, self.leakcheck())
        self.assertTrue(gate1['ok'], gate1)
        with self.assertRaisesRegex(oc.ContractError, 'quote'):
            om.holdout_open(ctx, gate1['path'], quote=' ', quote_time=WHEN)
        for when in ('24.10.2026 10:00', '2026-10-24T10:00:00'):
            with self.subTest(when=when), self.assertRaisesRegex(oc.ContractError, 'ISO|offset'):
                om.holdout_open(ctx, gate1['path'], QUOTE, when)
        opened = om.holdout_open(ctx, gate1['path'], QUOTE, WHEN, covers_stage2=True)
        self.assertEqual(opened['arms'], list(oc.ARMS))
        receipt = oc.config_path('holdout-open')
        with self.assertRaisesRegex(oc.ContractError, 'closed'):     # uncommitted receipt: nothing is started
            om.holdout(ctx)
        self.assertFalse(oc.output_dir('holdout').exists())
        self.commit(receipt)

        # a score file that differs from the pin: refused before started.json and before the labels
        ranked = om.fit_dir('holdout', 'BApl', 2026)/om.EVAL_DIR/om.RANKED_FILE
        saved = ranked.read_bytes()
        ranked.write_bytes(saved+b'x')
        with mock.patch.object(oc, 'read_sealed', side_effect=AssertionError('labels read')):
            with self.assertRaisesRegex(oc.ContractError, 'changed|pinned'):
                om.holdout(ctx)
        self.assertFalse(oc.output_dir('holdout').exists())
        ranked.write_bytes(saved)

        result = om.holdout(ctx)
        data = oc.read_json(oc.config_path('holdout'))
        self.assertEqual(result['verdict_transfer'], oc.ONE_SEED)
        self.assertEqual(result['verdict_content'], oc.ONE_SEED)
        self.assertEqual(sorted(data['metrics']), ['B2026', 'BA2026', 'BApl2026'])
        self.assertIn('2026', data['D'])
        self.assertNotIn('seed_mean', data)                      # seed means only at stage 2
        self.assertGreaterEqual(data['ceiling']['BA']['orders'], data['ceiling']['B']['orders'])
        started = list(oc.output_dir('holdout').glob(f'stage1-*/{om.STARTED_FILE}'))
        self.assertEqual(len(started), 1)
        with self.assertRaises(oc.ContractError):          # once per stage
            om.holdout(ctx)
        self.commit(oc.config_path('holdout'))

        # final series and the Kaggle lists: the training sessions first (final-sessions)
        with self.assertRaisesRegex(oc.ContractError, 'final-training'):
            om.fit(ctx, 'final', 'B', 2026)
        om.final_sessions(ctx)
        self.fit_eval(ctx, 'final', ['B', 'BA'], 2026, eval_too=False)
        sessions = sorted(self.folds[5]['frame']['session'].unique())
        known = set(self.folds[5]['agent']['aid'])
        pop5 = od.pop(oc.collection_dir('kaggle')/oc.FRAME_FILE)
        for arm in ('B', 'BA'):
            out = om.score(ctx, arm, 2026)
            self.assertEqual(out['assemble'][1:4], ['-I', str(self.root/'scripts'/'otto_data.py'), 'assemble'])
            self.assertTrue(all(Path(x).is_absolute() for x in (out['assemble'][0], *out['assemble'][5::2])))
            lists = self.ranked(oc.ROOT/out['ranked'])
            self.assertEqual(lists.groupby(['session', 'type']).size().min(), 20)
            self.assertEqual(sorted(lists['session'].unique()), sessions)
            target = om.kaggle_file(arm, 2026)
            target.parent.mkdir(parents=True)
            od.assemble(oc.ROOT/out['ranked'], target, sessions, known, pop5, sample_rows=3*len(sessions))
            lines = target.read_text(encoding='utf-8').split('\n')
            self.assertEqual(lines[0], 'session_type,labels')
            self.assertEqual(len(lines), 3*len(sessions)+2)                 # header, rows, trailing LF
            key, labels = lines[1].split(',')
            self.assertRegex(key, r'^\d+_(clicks|carts|orders)$')
            self.assertEqual(len(set(labels.split(' '))), 20)
        gate2 = om.gate(ctx, '2', 1)
        self.assertTrue(gate2['ok'], gate2)
        record = oc.read_json(gate2['path'])['checks']['assemble']['BA2026']
        self.assertEqual(record['problems'], [])
        # a receipt of other ranked lists, or of a file topped up at assembly, fails gate 2
        receipt_path = om.kaggle_file('BA', 2026).with_suffix('.json')
        receipt = oc.read_json(receipt_path)
        self.assertEqual(receipt['ranked_sha256'], oc.read_json(
            om.fit_dir('final', 'BA', 2026)/om.EVAL_DIR/om.REPORT_FILE)['ranked']['sha256'])
        for change, problem in ((dict(ranked_sha256='7'*64), 'other ranked lists'),
                                (dict(filled_sessions=3), 'filled_sessions')):
            with self.subTest(problem=problem):
                receipt_path.unlink()
                oc.atomic_json(receipt_path, dict(receipt, **change))
                bad = om.gate(ctx, '2', 1)
                self.assertFalse(bad['status']['BA'])
                problems = oc.read_json(bad['path'])['checks']['assemble']['BA2026']['problems']
                self.assertTrue(any(problem in p for p in problems), problems)
        receipt_path.unlink()
        oc.atomic_json(receipt_path, receipt)
        om.kaggle_file('BA', 2026).write_text('changed\n')
        self.assertFalse(om.gate(ctx, '2', 1)['status']['BA'])

        # stage 2: seed 2027 of the holdout series, same "да"
        self.fit_eval(ctx, 'holdout', oc.ARMS, 2027)
        gate1b = om.gate(ctx, '1', 2)
        self.assertTrue(gate1b['ok'], gate1b)
        om.holdout_open(ctx, gate1b['path'], stage=2)
        receipt2 = oc.read_json(oc.config_path('holdout-open-2'))
        self.assertEqual(receipt2['quote']['source'], 'holdout-open')
        self.commit(oc.config_path('holdout-open-2'))
        final = om.holdout(ctx, stage=2)
        self.assertIn(final['verdict_transfer'], oc.VERDICT_TRANSFER)
        self.assertIn(final['verdict_content'], oc.VERDICT_CONTENT)
        data2 = oc.read_json(oc.config_path('holdout-2'))
        self.assertEqual(sorted(data2['D']), ['2026', '2027'])
        mean = data2['seed_mean']
        self.assertAlmostEqual(mean['BApl_minus_B'], (data2['BApl_minus_B']['2026']['diff']
                                                      + data2['BApl_minus_B']['2027']['diff'])/2)
        self.assertEqual(sorted(mean['types']['carts']), ['BApl_minus_B', 'D', 'P'])

    def test_holdout_open_refuses_a_changed_score_file(self):
        ctx = self.ctx()
        self.fit_eval(ctx, 'dev', oc.ARMS, 2026)
        power = om.gate(ctx, 'power', contrast_path=om.contrast(ctx)['path'])
        self.assertEqual(power['note'] is None, power['resolution'] <= oc.POWER_HALF_WIDTH)
        self.fit_eval(ctx, 'holdout', oc.ARMS, 2026, eval_too=False)
        for arm in oc.ARMS:
            om.evaluate(ctx, 'holdout', arm, 2026)
        gate1 = om.gate(ctx, '1', 1, self.leakcheck())
        ranked = om.fit_dir('holdout', 'BA', 2026)/om.EVAL_DIR/om.RANKED_FILE
        ranked.write_bytes(ranked.read_bytes()+b'x')
        with self.assertRaisesRegex(oc.ContractError, 'changed'):
            om.holdout_open(ctx, gate1['path'], QUOTE, WHEN)
        self.assertFalse(oc.config_path('holdout-open').exists())


class AgentFormats(Repo):
    """Integration with the otto_agent formats: freeze -> frozen columns, sidecar.json -> BA frame."""

    def test_frozen_columns_come_from_the_set_written_by_freeze(self):
        frozen = dict(format=oc.SET_FORMAT, run='run-1', probe='probe-1', run_sha256='1'*64, base_digest='2'*64,
                      prompt={'digest': '3'*64}, prompt_digest='3'*64, t_tb=60, code={}, candidates={'sources': ['x']},
                      proposals=AGENT_SET['proposals'], attempts=[], columns=AGENT, tables=['v'], budget={},
                      digest=SET_DIGEST, audit=AGENT_SET['audit'])   # the fields otto_agent freeze writes
        self.configs(prereg_extra=dict(agent_columns=None), set_body=frozen)
        ctx = om.Context.contract()
        self.assertEqual((ctx.agent_columns, ctx.set_digest), (AGENT, SET_DIGEST))
        self.assertEqual(om.frozen_agent_columns({}, frozen), AGENT)
        self.assertEqual(oc.agent_columns(frozen), AGENT)

    def test_sidecar_b_columns_follow_b_tables_of_the_base(self):
        """A base without h_rank: otto_agent writes the base features, then h_rank (od.b_columns)."""
        lean = oc.make_base({}, [dict(name=n, formula=n, missing='NULL') for n in FEATURES if n != 'h_rank'])
        expected = [n for n in FEATURES if n != 'h_rank'] + ['h_rank']
        self.assertEqual(od.b_columns(lean), expected)
        self.assertEqual(od.b_columns(self.base), FEATURES)
        ctx = lambda: om.Context(lean, **{k: v for k, v in dict(
            mode='contract', prereg={'recipe': {'bootstrap_type': 'Bayesian'}}, prereg_sha256='0'*64, code={},
            agent_columns=AGENT, set_digest=SET_DIGEST).items()})
        val = oc.collection_dir('val')
        agent = self.folds[3]['agent']
        self.residecar(3, agent[['session', 'aid', *expected, *AGENT]])
        self.assertEqual(om.ba_frame(ctx(), val)['columns'][2:-len(AGENT)], expected)
        for frame in (agent[['session', 'aid', *FEATURES, *AGENT]],                       # h_rank in base order
                      agent[['session', 'aid', *expected[:-1], *AGENT]]):                 # h_rank missing
            self.residecar(3, frame)
            with self.assertRaisesRegex(oc.ContractError, 'B columns of the base'):
                om.ba_frame(ctx(), val)

    def test_sidecars_make_the_ba_frame(self):
        ctx = self.ctx()
        val = oc.collection_dir('val')
        agent = self.folds[3]['agent']
        sessions = sorted(int(x) for x in agent['session'].unique())
        # two sidecar runs (population first, the rest later) form one BA frame
        self.residecar(3, agent, name='a', sessions=sessions[:30], batch=7)
        write_sidecar(val, agent, name='b', sessions=sessions[30:], batch=50)
        record = om.ba_frame(ctx, val)
        self.assertEqual(record['sessions'], sessions)
        self.assertEqual(len(record['parts']), 5+1)
        self.assertEqual((record['columns'][:2], record['agent_columns']), (['session', 'aid'], AGENT))
        self.assertEqual(om.ba_frame_paths(ctx, val), record['parts'])
        self.assertEqual([r['name'] for r in record['sidecars']], ['a', 'b'])
        om.fit(ctx, 'dev', 'B', 2026)
        om.fit(ctx, 'dev', 'BA', 2026)
        self.assertTrue(om.evaluate(ctx, 'dev', 'BA', 2026)['finite_all'])

        # a population session without a sidecar: refused before any evaluation output
        self.residecar(3, agent, name='a', sessions=sessions[:-1])
        ctx = self.ctx()
        output = om.fit_dir('dev', 'BA', 2026)/'again'
        with self.assertRaisesRegex(oc.ContractError, 'lacks 1 population sessions'):
            om.evaluate(ctx, 'dev', 'BA', 2026, output=output)
        self.assertFalse(output.exists())

        def broken(change, frame=agent):
            self.residecar(3, frame, name='a')
            directory = oc.sidecar_dir(val.name, 'a')
            change(directory)
            return self.ctx()
        def report(directory):
            return oc.read_json(directory/oc.SIDECAR_REPORT)

        def rewrite(directory, drop=(), **changes):
            body = {k: v for k, v in dict(report(directory), **changes).items() if k not in drop}
            (directory/oc.SIDECAR_REPORT).unlink()
            oc.atomic_json(directory/oc.SIDECAR_REPORT, body)
        def retype(directory, column, type_):
            """part-00001 rewritten with ``column`` of another type, listed with its new SHA-256."""
            path = directory/'part-00001.parquet'
            con = duckdb.connect()
            con.execute(f"""COPY (SELECT * REPLACE (CAST("{column}" AS {type_}) AS "{column}")
                FROM read_parquet('{path}')) TO '{path}.new' (FORMAT parquet)""")
            con.close()
            Path(f'{path}.new').replace(path)
            body = report(directory)
            rewrite(directory, parts={**body['parts'], path.name: dict(body['parts'][path.name],
                                                                         sha256=oc.sha256_file(path))})

        def relink(path):
            """``path`` moved aside and replaced by a symbolic link to it."""
            moved = path.with_name('.' + path.name + '-target') if path.is_dir() else self.root/'moved.parquet'
            path.rename(moved)
            path.symlink_to(moved, target_is_directory=moved.is_dir())

        cases = [
            (lambda d: rewrite(d, set_digest='6'*64), 'another agent set'),
            (lambda d: rewrite(d, manifest_sha256='6'*64), 'another manifest'),
            (lambda d: rewrite(d, collection='train-F2'), 'another collection'),
            (lambda d: rewrite(d, format='x'), oc.SIDECAR_FORMAT),
            (lambda d: rewrite(d, sessions_digest='6'*64), 'sessions_digest'),
            (lambda d: rewrite(d, rows=1), 'row counts'),
            (lambda d: rewrite(d, columns=report(d)['columns'][::-1]), 'columns must be session, aid'),
            (lambda d: rewrite(d, columns=[*report(d)['columns'][:2], *report(d)['columns'][3:4],
                                           *report(d)['columns'][2:3], *report(d)['columns'][4:]]),
             'columns differ from sidecar.json'),
            (lambda d: rewrite(d, drop=('manifest_sha256',)), 'lacks'),
            (lambda d: rewrite(d, parts={**report(d)['parts'], 'part-00000.parquet': dict(
                report(d)['parts']['part-00000.parquet'], sha256=None)}), 'without sha256'),
            (lambda d: rewrite(d, parts={**report(d)['parts'], 'part-00000.parquet': dict(
                report(d)['parts']['part-00000.parquet'], rows=1)}), 'rows or sessions differ'),
            (lambda d: rewrite(d, parts={**report(d)['parts'], 'part-00000.parquet': dict(
                report(d)['parts']['part-00000.parquet'], sessions=1)}), 'rows or sessions differ'),
            (lambda d: retype(d, 'ag_good', 'DOUBLE'), 'not FLOAT'),
            (lambda d: retype(d, report(d)['columns'][2], 'FLOAT'), 'types differ'),
            (lambda d: relink(d/'part-00000.parquet'), 'links'),
            (lambda d: relink(d), 'links'),
            (lambda d: (d/'part-00000.parquet').write_bytes(b'x'), 'part changed'),
            (lambda d: (d/'extra.parquet').write_bytes(b'x'), 'differ from the listed parts'),
            (lambda d: (d.parent/'stray').mkdir(), 'without sidecar.json'),
            (lambda d: write_sidecar(val, agent, name='z', sessions=sessions[:2]), 'already in another'),
        ]
        cases.append(((lambda d: None), 'frozen set', agent.drop(columns=['ag_good'])))   # another column list
        cases.append(((lambda d: None), 'B columns of the base', agent.drop(columns=[self.ctx().features[0]])))
        for change, pattern, *frame in cases:
            with self.subTest(pattern=pattern):
                ctx = broken(change, *frame)
                with self.assertRaisesRegex(oc.ContractError, pattern):
                    om.ba_frame_paths(ctx, val)
        self.residecar(3, agent, name='a')
        with self.assertRaisesRegex(oc.ContractError, 'нет замороженного набора'):
            om.ba_frame_paths(self.ctx(set_digest=None), val)
        # one command hashes every part once: the cache keys on path, mtime and size
        oc._PART_SHA.clear()
        with mock.patch.object(oc, 'sha256_file', wraps=oc.sha256_file) as hashed:
            oc.sidecar_parts(val, SET_DIGEST)
            oc.sidecar_parts(val, SET_DIGEST)
        parts = [c for c in hashed.call_args_list if str(c.args[0]).endswith('.parquet')]
        self.assertEqual(len(parts), len(list(oc.sidecar_dir(val.name, 'a').glob('*.parquet'))))
        shutil.rmtree(oc.output_dir('sidecars', val.name))
        self.assertEqual(om.ba_frame_paths(self.ctx(), val), [])                # BA не выполнена
        self.assertEqual(om.ba_frame_paths(self.ctx(set_digest=None), val), [])


class FinalSeries(Repo):
    """final-sessions after the committed result receipt; fit final trains on exactly those sessions."""

    def setUp(self):
        super().setUp()
        result = oc.config_path('holdout')
        result.write_text(json.dumps(dict(format=om.RESULT_FORMAT, stage=1)))
        self.commit(result)

    def test_final_training_then_fit_final(self):
        ctx = self.ctx()
        with self.assertRaisesRegex(oc.ContractError, 'found 0'):
            om.fit(ctx, 'final', 'B', 2026)
        self.assertFalse(om.fit_dir('final', 'B', 2026).exists())
        out = om.final_sessions(ctx, name='first')
        path = oc.ROOT/out['path']
        self.assertEqual(path, oc.final_training_dir('first')/oc.FINAL_TRAINING_FILE)
        record = oc.read_json(path)
        expected = od.training_sessions(self.folds[4]['labels'], n=40)
        self.assertEqual(record['per_type'], expected)
        self.assertEqual((record['format'], record['collection'], record['N_t'], record['prereg_sha256']),
                         (oc.FINAL_TRAINING_FORMAT, oc.collection_name('holdout'), 40, '0'*64))
        self.assertEqual(record['training_digest'], oc.canonical_digest(expected))
        self.assertEqual(record['sessions'], sorted(set().union(*map(set, expected.values()))))
        with self.assertRaisesRegex(oc.ContractError, 'exist'):                # once per holdout collection
            om.final_sessions(ctx, name='second')
        for bad in ('../x', 'a/b', '/tmp/x', '..', '.hidden', ''):
            with self.subTest(name=bad), self.assertRaisesRegex(oc.ContractError, 'Output names'):
                om.final_sessions(ctx, name=bad)

        # the BA frame of F4 must cover the training sessions: population sidecar first, training sidecar later
        hold = oc.collection_dir('holdout')
        agent = self.folds[4]['agent']
        rest = sorted(set(int(x) for x in agent['session'].unique()) - set(record['sessions']))
        self.residecar(4, agent, name='population', sessions=rest + record['sessions'][:-1])
        with self.assertRaisesRegex(oc.ContractError, 'lacks 1 final training sessions'):
            om.fit(self.ctx(), 'final', 'BA', 2026)
        self.assertFalse(om.fit_dir('final', 'BA', 2026).exists())
        write_sidecar(hold, agent, name='final-training', sessions=record['sessions'][-1:])
        ctx = self.ctx()
        for arm in ('B', 'BA'):
            report = om.fit(ctx, 'final', arm, 2026)
            self.assertEqual(report['training_digest']['status'], 'equal')
            self.assertEqual(report['training_digest']['training_digest'], record['training_digest'])
            self.assertEqual({t: report['training'][t]['sessions_digest'] for t in oc.TYPES},
                             {t: oc.canonical_digest(expected[t]) for t in oc.TYPES})
        with self.assertRaisesRegex(oc.ContractError, 'another N_t'):
            om.fit(self.ctx(n_t=30), 'final', 'B', 2027)
        with self.assertRaisesRegex(oc.ContractError, 'another prereg'):
            om.fit(self.ctx(prereg_sha256='1'*64), 'final', 'B', 2027)

        # sessions.json that names other sessions than the labels give: refused, the fit fails
        path.unlink()
        changed = dict(expected, clicks=expected['clicks'][:-1])
        oc.write_final_training(path.parent, oc.collection_name('holdout'), 40, '0'*64, changed)
        with self.assertRaisesRegex(oc.ContractError, 'differ from training_digest'):
            om.fit(self.ctx(), 'final', 'B', 2027)
        self.assertEqual(oc.read_json(om.fit_dir('final', 'B', 2027)/om.REPORT_FILE)['status'], 'failed')

    def test_refused_final_training_sidecar_is_ba_not_run(self):
        """§8: a population sidecar of F4 without the final-training one is "BA не выполнена" — gate 2 counts B."""
        ctx = self.ctx()
        record = oc.read_json(oc.ROOT/om.final_sessions(ctx, name='first')['path'])
        agent = self.folds[4]['agent']
        rest = sorted(set(int(x) for x in agent['session'].unique()) - set(record['sessions']))
        self.residecar(4, agent, name='population', sessions=rest)       # the training sidecar was refused
        with self.assertRaisesRegex(oc.ContractError, 'lacks'):
            om.fit(self.ctx(), 'final', 'BA', 2026)
        ctx = self.ctx()
        self.assertFalse(ctx.ba_run(4, 5))
        om.fit(ctx, 'final', 'B', 2026)
        out = om.score(ctx, 'B', 2026)
        sessions = sorted(self.folds[5]['frame']['session'].unique())
        target = om.kaggle_file('B', 2026)
        target.parent.mkdir(parents=True)
        od.assemble(oc.ROOT/out['ranked'], target, sessions, set(self.folds[5]['agent']['aid']),
                    od.pop(oc.collection_dir('kaggle')/oc.FRAME_FILE), sample_rows=3*len(sessions))
        evals, present = om.series_evals(self.ctx(), 'final', 2026, ('B', 'BA'))
        self.assertEqual((list(evals), present), (['B'], False))
        gate2 = om.gate(self.ctx(), '2', 1)
        self.assertEqual(gate2['status'], dict(B=True, BA=False))
        self.assertFalse(oc.read_json(gate2['path'])['checks']['present']['BA'])
        # the training sidecar arrives: now the missing BA evaluation is an error, not a result
        write_sidecar(oc.collection_dir('holdout'), agent, name='final-training', sessions=record['sessions'])
        with self.assertRaisesRegex(oc.ContractError, 'not evaluated though the BA frames cover the series'):
            om.series_evals(self.ctx(), 'final', 2026, ('B', 'BA'))

    def test_ba_run_before_final_sessions_is_ba_not_run(self):
        self.assertFalse(oc.output_dir('final-training').exists())
        self.assertFalse(self.ctx().ba_run(4, 5))                       # not "found 0": BA не выполнена
        om.final_sessions(self.ctx(), name='first')
        self.assertTrue(self.ctx().ba_run(4, 5))                        # the setUp sidecars cover all of F4

    def test_final_sessions_needs_the_result_receipt(self):
        git(self.root, 'rm', '-q', str(oc.config_path('holdout').relative_to(self.root)))
        git(self.root, 'commit', '-q', '-m', 'rm')
        with mock.patch.object(oc, 'read_sealed', side_effect=AssertionError('labels read')):
            with self.assertRaisesRegex(oc.ContractError, 'closed'):
                om.final_sessions(self.ctx())
        self.assertFalse(oc.output_dir('final-training').exists())


class BaNotRun(Repo):
    """§5.7: no BA frame — D null, gate 1 fails BA and BApl, the holdout opens for B and Pop."""

    def test_holdout_for_b_and_pop(self):
        shutil.rmtree(oc.output_dir('sidecars'))
        ctx = self.ctx()
        with self.assertRaisesRegex(oc.ContractError, om.BA_NOT_RUN):
            om.fit(ctx, 'dev', 'BA', 2026)
        self.assertFalse(om.fit_dir('dev', 'BA', 2026).exists())
        self.fit_eval(ctx, 'dev', ['B'], 2026)
        contrast = om.contrast(ctx)
        self.assertIsNone(contrast['D'])
        self.assertEqual(contrast['ba'], om.BA_NOT_RUN)
        self.assertIsNone(oc.read_json(contrast['path'])['D']['2026'])
        power = om.gate(ctx, 'power', contrast_path=contrast['path'])
        self.assertEqual(power['population']['n'], 60)          # CI(BA - B) not computed: all of Q_4
        self.fit_eval(ctx, 'holdout', ['B'], 2026)
        gate1 = om.gate(ctx, '1', 1)
        self.assertEqual(gate1['status'], dict(B=True, BA=False, BApl=False))
        opened = om.holdout_open(ctx, gate1['path'], QUOTE, WHEN)
        self.assertEqual(opened['arms'], ['B'])
        self.commit(oc.config_path('holdout-open'))
        result = om.holdout(ctx)
        self.assertEqual((result['verdict_transfer'], result['verdict_content']), (oc.NOT_COMPUTED, oc.NOT_COMPUTED))
        data = oc.read_json(oc.config_path('holdout'))
        self.assertEqual(sorted(data['metrics']), ['B2026'])
        self.assertEqual(sorted(data['pop']['recall']), sorted(oc.TYPES))
        self.assertNotIn('D', data)
        self.assertEqual(sorted(data['ceiling']), ['B'])

    def test_ba_run_needs_coverage_of_the_training_union_and_the_population(self):
        ctx = self.ctx()
        self.assertTrue(ctx.ba_run(2, 3))
        train = self.folds[2]['agent']
        con = duckdb.connect()
        om.labels_view(con, str(oc.collection_dir('train')/oc.LABELS_FILE))
        union = set().union(*om.training_sessions(con, 'lab', ctx.n_t).values())
        con.close()
        short = train[train['session'] != min(union)]
        self.residecar(2, short)                                    # one training session without a sidecar
        self.assertFalse(self.ctx().ba_run(2, 3))
        self.residecar(2, train)
        val = self.folds[3]['agent']
        population = oc.read_population(oc.collection_dir('val'))
        self.residecar(3, val[val['session'] != population[0]])     # one population session without a sidecar
        self.assertFalse(self.ctx().ba_run(2, 3))
        self.fit_eval(self.ctx(), 'dev', ['B'], 2026)
        self.assertEqual(list(om.series_evals(self.ctx(), 'dev', 2026, oc.ARMS)[0]), ['B'])
        shutil.rmtree(oc.output_dir('sidecars'))
        with mock.patch.object(om, 'fold_labels', side_effect=AssertionError('labels read')):
            self.assertFalse(self.ctx().ba_run(2, 3))               # no frame: no labels read

    def test_missing_ba_evaluation_with_a_ba_frame_is_refused(self):
        ctx = self.ctx()
        self.fit_eval(ctx, 'dev', ['B'], 2026)
        with self.assertRaisesRegex(oc.ContractError, 'not evaluated though the BA frames cover the series'):
            om.contrast(ctx)


class ContextAndOutputs(Repo):
    def test_contract_context_from_the_committed_prereg(self):
        ctx = om.Context.contract()
        self.assertEqual((ctx.bootstrap_type, ctx.agent_columns, ctx.set_digest, ctx.n_t, ctx.score_batch),
                         ('Bayesian', AGENT, SET_DIGEST, 40, 7))
        self.assertEqual(ctx.code, IDENTITY['files'])
        self.assertEqual(ctx.prereg_sha256, oc.sha256_file(oc.config_path('prereg')))
        self.configs(prereg_extra=dict(agent_columns=None))                # columns from the committed set
        self.assertEqual(om.Context.contract().agent_columns, AGENT)
        cases = [(dict(agent_columns=None), dict(agent_columns=AGENT, audit=AGENT_SET['audit']), oc.SET_FORMAT),
                 (dict(agent_columns=None), dict(AGENT_SET, audit=None), 'verdict clean'),     # not audited
                 (dict(agent_columns=None), dict(AGENT_SET, audit=dict(verdict='leak')), 'verdict clean'),
                 (dict(agent_columns=['ag_other']), AGENT_SET, 'differ from the committed set'),
                 (dict(agent_columns=None), dict(AGENT_SET, columns=['x_bad'], proposals=None), 'ag_'),
                 (dict(agent_columns=None), dict(AGENT_SET, columns=AGENT[::2], proposals=None), 'both'),
                 (dict(agent_columns=None), dict(AGENT_SET, columns=AGENT[::-1]), 'proposals'),
                 (dict(agent_columns=None), dict(AGENT_SET, digest='x'), 'digest')]
        for prereg_extra, set_body, pattern in cases:
            with self.subTest(pattern=pattern):
                self.configs(prereg_extra=prereg_extra, set_body={k: v for k, v in set_body.items() if v is not None})
                with self.assertRaisesRegex(oc.ContractError, pattern):
                    om.Context.contract()
        self.configs()
        other = dict(files=dict(IDENTITY['files'], **{'scripts/otto_model.py': 'd'*64}), missing=[])
        with mock.patch.object(oc, 'code_identity', return_value=other):
            with self.assertRaisesRegex(oc.ContractError, 'Code differs'):
                om.Context.contract()
        oc.config_path('prereg').write_text('{}')                          # uncommitted change
        with self.assertRaisesRegex(oc.ContractError, 'committed'):
            om.Context.contract()

    def test_agent_columns_must_match_the_frozen_list(self):
        ctx = self.ctx(agent_columns=list(reversed(AGENT)))
        with self.assertRaisesRegex(oc.ContractError, 'frozen'):
            om.fit(ctx, 'dev', 'BA', 2026)

    def test_fresh_output_moves_unfinished_runs_aside(self):
        path = oc.output_dir('fits', 'x')
        path.mkdir(parents=True)
        (path/'model-clicks.cbm').write_text('partial')                   # killed run: no report.json
        om.fresh_output(path)
        self.assertEqual(len(list(path.parent.glob('x.failed-*'))), 1)
        oc.atomic_json(path/om.REPORT_FILE, dict(status='failed'))
        om.fresh_output(path)
        self.assertEqual(len(list(path.parent.glob('x.failed-*'))), 2)
        (path/om.REPORT_FILE).unlink(missing_ok=True)
        oc.atomic_json(path/om.REPORT_FILE, dict(status='completed'))
        with self.assertRaisesRegex(oc.ContractError, 'exists'):
            om.fresh_output(path)


class BeforePrereg(Repo):
    def test_smoke_prereg_rules_and_base_dev(self):
        smoke = om.smoke(self.ctx(mode='smoke', prereg=None, prereg_sha256=None, agent_columns=None))
        data = oc.read_json(oc.ROOT/smoke['path'])
        self.assertEqual((data['bootstrap_type'], data['columns'], data['N_t']), ('Bayesian', len(FEATURES)+72, 40))
        full = oc.output_dir('smoke', 'full')
        full.mkdir(parents=True)
        oc.atomic_json(full/'smoke.json', dict(data, N_t=oc.N_T, bootstrap_type='Bernoulli'))
        # the run the set was frozen from names this smoke result; the set carries a clean audit
        run = oc.output_dir('run', 'run-t1')
        run.mkdir(parents=True)
        oc.atomic_json(run/'run.json', dict(format='otto-run-v1', smoke=dict(
            path='x', sha256=oc.sha256_file(full/'smoke.json'), N_t=oc.N_T)))
        frozen = dict(AGENT_SET, run=dict(id='t1'), run_sha256=oc.sha256_file(run/'run.json'))
        self.configs(set_body=frozen)
        rules = om.prereg_rules(full/'smoke.json')
        self.assertEqual((rules['recipe']['bootstrap_type'], rules['N_t']), ('Bernoulli', oc.N_T))
        self.assertEqual((rules['smoke']['sha256'], rules['smoke']['run']), (oc.sha256_file(full/'smoke.json'), 't1'))
        other = oc.output_dir('smoke', 'other')
        other.mkdir(parents=True)
        oc.atomic_json(other/'smoke.json', dict(data, N_t=oc.N_T, bootstrap_type='Bayesian'))
        bad = [(frozen, other/'smoke.json', 'not the smoke result of run t1'),
               (dict(frozen, run_sha256='0'*64), full/'smoke.json', 'run_sha256'),
               (dict(frozen, run=None), full/'smoke.json', 'names no run'),
               (dict(frozen, run=dict(id='../x')), full/'smoke.json', 'Output names'),
               (dict(frozen, audit=dict(verdict='leak')), full/'smoke.json', 'verdict clean'),
               (dict(frozen, audit=None), full/'smoke.json', 'verdict clean')]
        for body, smoke_path, pattern in bad:
            with self.subTest(pattern=pattern):
                if body is not frozen:
                    self.configs(set_body=body)
                with self.assertRaisesRegex(oc.ContractError, pattern):
                    om.prereg_rules(smoke_path)
        self.configs(set_body=frozen)
        self.assertEqual(rules['recipe']['iterations'], 500)
        self.assertIn('evaluation fold', rules['permutation'])
        with self.assertRaisesRegex(oc.ContractError, 'N_t'):             # smoke of the tiny test N_t
            om.prereg_rules(oc.ROOT/smoke['path'])
        ctx = self.ctx(mode='base-dev', prereg=None, prereg_sha256=None, agent_columns=None)
        with self.assertRaisesRegex(oc.ContractError, 'Before prereg'):
            om.fit(ctx, 'dev', 'BA', 2026, output=oc.output_dir('base-dev', 'x'))
        directory = oc.output_dir('base-dev', 'iter1')
        om.fit(ctx, 'dev', 'B', 2026, output=directory)
        report = om.evaluate(ctx, 'dev', 'B', 2026, fit_directory=directory)
        self.assertEqual(report['population']['n'], 55)
        self.assertTrue(0 <= report['metrics']['score'] <= 1)
        self.assertEqual(report['ceiling']['clicks'], 1.0)
        with self.assertRaisesRegex(oc.ContractError, 'another prereg or mode'):
            om.evaluate(self.ctx(), 'dev', 'B', 2026, fit_directory=directory, output=directory/'again')


# ================================================================== gate rules (§8)

class GateRules(unittest.TestCase):
    def test_parity(self):
        ok = om.parity(dict(a=0.4, b=0.0), dict(a=0.2, b=0.0))
        self.assertTrue(ok['ok'])
        for target in (dict(a=0.19, b=0.0), dict(a=0.81, b=0.0), dict(a=0.4, b=0.01), dict(a=0.4),
                       dict(a=0.4, b=0.0, c=0.5)):
            with self.subTest(target=target):
                self.assertFalse(om.parity(dict(a=0.4, b=0.0), target)['ok'])
        self.assertFalse(om.parity({}, {})['ok'])

    def test_power_rule(self):
        n, expected, resolution, _ = om.power_rule([-0.002, 0.002], 300_000, 1_700_000)
        self.assertEqual(n, 1_000_000)
        self.assertAlmostEqual(expected, 0.002*math.sqrt(0.3))
        self.assertAlmostEqual(resolution, expected)
        self.assertEqual(om.power_rule([-0.004, 0.004], 300_000, 1_700_000)[0], 1_700_000)
        self.assertEqual(om.power_rule([-0.001, 0.001], 300_000, 900_000)[0], 900_000)
        self.assertEqual(om.power_rule(None, 300_000, 1_700_000)[0], 1_700_000)

    def checks(self, **kw):
        c = dict(stage=1, seed=2026, finite={f'{p}-{a}2026': True for p in ('dev', 'holdout') for a in oc.ARMS},
                 lists={f'{p}-{a}2026': 0 for p in ('dev', 'holdout') for a in oc.ARMS},
                 floor={f'{a}2026': dict(ok=True) for a in oc.ARMS}, bapl_dev_cut=False,
                 leakcheck=dict(ok=True), parity=dict(ok=True), present={a: True for a in oc.ARMS})
        c.update(kw)
        return c

    def test_gate1_status_and_opened_arms(self):
        self.assertEqual(om.gate1_status(self.checks()), dict(B=True, BA=True, BApl=True))
        status = om.gate1_status(self.checks(parity=dict(ok=False)))
        self.assertEqual(status, dict(B=True, BA=False, BApl=False))
        self.assertEqual(om.opened_arms(status), ['B'])
        floor = {f'{a}2026': dict(ok=a != 'B') for a in oc.ARMS}
        with self.assertRaisesRegex(oc.ContractError, 'B'):
            om.opened_arms(om.gate1_status(self.checks(floor=floor)))
        lists = dict(self.checks()['lists'], **{'holdout-BA2026': 3})
        self.assertFalse(om.gate1_status(self.checks(lists=lists))['BA'])
        cut = {k: v for k, v in self.checks()['floor'].items() if k != 'BApl2026'}
        self.assertTrue(om.gate1_status(self.checks(floor=cut, bapl_dev_cut=True))['BApl'])
        self.assertFalse(om.gate1_status(self.checks(floor=cut))['BApl'])
        absent = self.checks(present=dict(B=True, BA=False, BApl=True))      # an absent arm is False
        self.assertEqual(om.gate1_status(absent), dict(B=True, BA=False, BApl=True))
        self.assertEqual(om.opened_arms(om.gate1_status(absent)), ['B'])


# ================================================================== reading and CLI (§10, §11)

class ReadingAndCli(unittest.TestCase):
    def test_reading(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(oc, 'ROOT', Path(tmp).resolve()):
            (Path(tmp)/'artifacts'/'otto').mkdir(parents=True)
            passed = dict(B2026=True, BA2026=True)
            out = om.reading('{"B2026": 0.570, "BA2026": 0.582}', passed=passed)
            self.assertEqual(out['comparison'], 'один seed — не читается')
            self.assertEqual(out['level']['note'], oc.LEVEL_ONE_SEED)
            self.assertEqual(out['level']['reading'], oc.LEVEL_THRESHOLDS[2][1])
            with self.assertRaisesRegex(oc.ContractError, 'not read'):
                om.reading('{"BApl2026": 0.5}', passed=passed)
            with self.assertRaisesRegex(oc.ContractError, 'gate 2'):
                om.reading('{"BA2027": 0.5}', passed=passed)

    def run_cli(self, *flags):
        return subprocess.run([sys.executable, *flags, str(REPO/'scripts'/'otto_model.py'), 'reading', '--private',
                               '{}'], capture_output=True, text=True, cwd=tempfile.gettempdir(), check=False)

    def test_cli_has_final_sessions_and_no_agent_frame_override(self):
        args = om.parser().parse_args(['final-sessions', '--name', 'x'])
        self.assertEqual((args.command, args.name), ('final-sessions', 'x'))
        self.assertIn('final-sessions', om.COMMANDS)
        for command in (['fit', '--series', 'dev', '--arm', 'BA', '--seed', '2026'],
                        ['evaluate', '--series', 'dev', '--arm', 'BA', '--seed', '2026'],
                        ['score', '--arm', 'BA', '--seed', '2026']):
            with self.subTest(command=command[0]), self.assertRaises(om.ArgumentError):
                om.parser().parse_args(command + ['--agent-frame', 'val-F3=x.parquet'])

    def test_cli_names_are_one_path_component(self):
        for bad in ('../x', 'a/b', '/tmp/x', '..'):
            args = om.parser().parse_args(['fit', '--base-dev', bad, '--base', 'b.json'])
            with self.subTest(name=bad), mock.patch.object(oc, 'read_base', return_value=None), \
                    mock.patch.object(om.Context, 'before_prereg', side_effect=AssertionError('context')):
                with self.assertRaisesRegex(oc.ContractError, 'Output names'):
                    om.cmd_fit(args)

    def test_gate_cli_reports_passed_without_clashing_with_ok(self):
        fake = dict(path='/x/gate.json', ok=False, status=dict(B=False, BA=True, BApl=True))
        out = io.StringIO()
        with mock.patch.object(om, 'gate', return_value=fake) as gate, \
                mock.patch.object(om.Context, 'contract', return_value='ctx'), \
                mock.patch.object(oc, 'isolated'), contextlib.redirect_stdout(out):
            code = om.main(['gate', '--kind', '1', '--leakcheck', 'a.json', 'b.json'])
        line = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual((line['ok'], line['passed'], line['command']), (True, False, 'gate'))
        self.assertEqual(line['status'], fake['status'])
        self.assertEqual(gate.call_args.args[:2], ('ctx', '1'))
        self.assertIn('ok', fake)

    def test_cli_refuses_without_isolation_and_prints_one_json_line(self):
        plain = self.run_cli()
        self.assertEqual(plain.returncode, 1)
        lines = plain.stdout.strip().split('\n')
        self.assertEqual(len(lines), 1)
        self.assertIn('python -I', json.loads(lines[0])['error'])
        bad = subprocess.run([sys.executable, '-I', str(REPO/'scripts'/'otto_model.py'), 'nope'],
                             capture_output=True, text=True, cwd=tempfile.gettempdir(), check=False)
        self.assertEqual(bad.returncode, 1)
        self.assertFalse(json.loads(bad.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
