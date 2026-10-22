"""Synthetic tests of scripts/otto_data.py (docs/otto-design.md §1, §2, §4, §8, §11).

No real OTTO data is read: raw jsonl files, partitions and receipts are built here
inside a throwaway Git repository that stands in for ROOT.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
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

S5 = 1_661_724_000                     # seconds; the contract fixes no calendar date
DAY = oc.DAY
REPO = Path(od.__file__).resolve().parents[1]
NAMES = od.TYPE_NAMES
# code_identity of the tree in these tests (otto_agent may be absent): the prereg names it
IDENTITY = dict(files={'scripts/otto_common.py': 'a'*64, 'scripts/otto_data.py': 'b'*64}, missing=[])


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


def ev(aid, ts_s, kind='clicks', ms=0):
    return (int(aid), int(ts_s)*1000+ms, kind)


def make_world(seed=7, n_per_week=14, test_sessions=10):
    """Train sessions starting in W1..W4 (some crossing weeks) and test sessions in W5, ts in ms."""
    rng = np.random.default_rng(seed)
    train, test = {}, {}
    sid = 0
    for week in (1, 2, 3, 4):
        start = oc.week_start(week, S5)
        for i in range(n_per_week):
            first = start + int(rng.integers(0, 7*DAY - 3600))
            n = int(rng.integers(3, 13))
            events = []
            ts = first
            for _ in range(n):
                if week == 4 and ts >= S5:
                    break
                kind = NAMES[int(rng.choice(3, p=[0.7, 0.2, 0.1]))]
                events.append(ev(int(rng.integers(1, 16)), ts, kind, int(rng.integers(0, 1000))))
                ts += int(rng.integers(600, 4*3600))
            train[sid] = events
            sid += 1
    for i in range(test_sessions):
        first = S5 + int(rng.integers(0, 6*DAY)) if i else S5          # the first test event defines S5
        n = int(rng.integers(1, 6))
        test[100_000+i] = [ev(int(rng.integers(1, 16)), first + j*900, NAMES[j % 3 if j else 0], 5)
                           for j in range(n)]
    return train, test


def write_raw(raw, train, test):
    raw.mkdir(parents=True, exist_ok=True)
    for name, sessions in (('train.jsonl', train), ('test.jsonl', test)):
        with (raw/name).open('w', encoding='utf-8', newline='\n') as stream:
            for session, events in sessions.items():
                stream.write(json.dumps(dict(session=session, events=[dict(aid=a, ts=t, type=k) for a, t, k in events]),
                                        separators=(',', ':')) + '\n')
    with (raw/'sample_submission.csv').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('session_type,labels\n')
        for session in test:
            for kind in NAMES:
                stream.write(f'{session}_{kind},1 2 3\n')


def frame_digest(frame):
    """SHA-256 of the column names and integer values (NULL as null) of a frame, row order included."""
    rows = [[None if pd.isna(v) else int(v) for v in row] for row in frame.astype(object).itertuples(index=False)]
    return hashlib.sha256(json.dumps([list(frame.columns), rows]).encode()).hexdigest()


class TempRoot(unittest.TestCase):
    """A throwaway Git repository standing in for ROOT."""

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
        self.raw = self.root/oc.RAW_DIR
        self.base = od.initial_base()

    def tearDown(self):
        self.code_patch.stop()
        self.patch.stop()
        for path in self.root.rglob('*'):
            if not path.is_symlink():
                path.chmod(0o700 if path.is_dir() else 0o600)
        self.tmp.cleanup()

    def load(self, train, test, **kwargs):
        write_raw(self.raw, train, test)
        kwargs.setdefault('check_contract', False)
        return od.load(threads=2, memory='1GB', **kwargs)

    def partition(self, d):
        files = sorted(oc.events_path(d).glob('*.parquet'))
        return duckdb.sql(f"SELECT * FROM read_parquet({[str(f) for f in files]}, hive_partitioning=false) "
                          f"ORDER BY session, seq").df()

    def all_train(self):
        files = [str(f) for d in oc.existing_days('train') for f in oc.events_path(d).glob('*.parquet')]
        return duckdb.sql(f"SELECT * FROM read_parquet({files}, hive_partitioning=false) ORDER BY session, seq").df()

    def fold_frame(self, k, batch=od.FRAME_BATCH, purpose='test'):
        con = od.connect(2, '1GB')
        out = Path(tempfile.mkdtemp(dir=self.tmp.name))
        try:
            od.build_fold(con, k, purpose, S5)
            con.execute('CREATE TEMP TABLE frame_sessions AS SELECT DISTINCT session FROM fold')
            built = od.build_frame(con, k, self.base, S5, batch=batch, out=out)
            parts = [str(p) for p in built['parts']]
            frame = con.execute(f'SELECT * FROM read_parquet({parts}) ORDER BY session, aid').df()
            fold = con.execute('SELECT * FROM fold ORDER BY session, seq').df()
            labels = con.execute('SELECT * FROM labels ORDER BY session, type, aid').df()
        finally:
            con.close()
        return frame, fold, labels

    def commit(self, *paths):
        git(self.root, 'add', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def commit_prereg(self):
        base = oc.config_path('base')
        oc.atomic_json(base, self.base)
        agent_set = oc.config_path('set')
        agent_set.write_text(json.dumps(dict(s=1, audit=dict(verdict='clean'))))
        prereg = oc.config_path('prereg')
        prereg.write_text(json.dumps(dict(base_sha256=oc.sha256_file(base), set_sha256=oc.sha256_file(agent_set),
                                          code=IDENTITY['files'])))
        self.commit(base, agent_set, prereg)

    def commit_result(self):
        receipt = oc.config_path('holdout')
        receipt.write_text(json.dumps(dict(stage=1)))
        self.commit(receipt)


# =============================================================================== load

class LoadTest(TempRoot):

    def test_seq_follows_the_array_index_from_one(self):
        t = S5 - 20*DAY
        train = {1: [ev(30, t), ev(10, t), ev(20, t)], 2: [ev(10, t+5), ev(30, t+6)]}
        test = {9: [ev(10, S5), ev(30, S5+1)]}
        self.load(train, test)
        part = self.partition(oc.partition_day(t, S5))
        rows = part[part.session == 1][['aid', 'seq', 'ts']].values.tolist()
        self.assertEqual(rows, [[30, 1, t], [10, 2, t], [20, 3, t]])

    def test_milliseconds_become_seconds_by_integer_division(self):
        train = {1: [ev(1, S5 - 3*DAY, ms=999), ev(2, S5 - 3*DAY + 1, ms=1)]}
        test = {9: [ev(1, S5, ms=999)]}
        receipt = self.load(train, test)
        self.assertEqual(receipt['ts_unit'], 'ms')
        self.assertEqual(receipt['s5'], S5)
        part = self.partition(-3)
        self.assertEqual(part.ts.tolist(), [S5 - 3*DAY, S5 - 3*DAY + 1])

    def test_seconds_are_kept(self):
        train = {1: [(1, S5 - 3*DAY, 'clicks'), (2, S5 - 2*DAY, 'carts')]}
        test = {9: [(1, S5 + 10, 'clicks')]}
        receipt = self.load(train, test)
        self.assertEqual(receipt['ts_unit'], 's')
        self.assertEqual(receipt['s5'], S5 + 10)

    def test_mixed_units_are_refused(self):
        train = {1: [ev(1, S5 - 3*DAY), (2, S5 - 2*DAY, 'clicks')]}       # one ms, one s
        test = {9: [ev(1, S5)]}
        with self.assertRaisesRegex(oc.ContractError, 'Mixed ts units'):
            self.load(train, test)
        self.assertFalse(oc.verify_path().exists())
        self.assertEqual(oc.existing_days(), [])

    def test_train_before_test_is_checked_in_milliseconds(self):
        # train max = S5·1000 + 3 ms < test min = S5·1000 + 4 ms: allowed; after // 1000 it is S5 -> d = -1
        train = {1: [ev(1, S5 - DAY), ev(2, S5, ms=3)]}
        test = {9: [ev(1, S5, ms=4)]}
        receipt = self.load(train, test)
        self.assertEqual(receipt['s5'], S5)
        self.assertEqual(receipt['facts']['train_events_at_s5'], 1)
        part = self.partition(-1)
        self.assertEqual(sorted(part.ts.tolist()), [S5 - DAY, S5])
        self.assertEqual(oc.existing_days('test'), [0])

    def test_train_not_before_test_is_refused(self):
        train = {1: [ev(1, S5 - DAY), ev(2, S5, ms=4)]}
        test = {9: [ev(1, S5, ms=4)]}
        with self.assertRaisesRegex(oc.ContractError, 'source units'):
            self.load(train, test)

    def test_partition_day_floors(self):
        train = {1: [ev(1, S5 - 7*DAY - 1), ev(2, S5 - 7*DAY), ev(3, S5 - 1)]}
        test = {9: [ev(1, S5)]}
        self.load(train, test)
        self.assertEqual(self.partition(-8).aid.tolist(), [1])
        self.assertEqual(sorted(self.partition(-7).aid.tolist()), [2])
        self.assertEqual(self.partition(-1).aid.tolist(), [3])
        # a week boundary is a partition boundary
        for k in (2, 3, 4, 5):
            self.assertEqual(oc.partition_day(oc.week_start(k, S5), S5, 'train' if k < 5 else 'test'),
                             oc.week_first_day(k))
            self.assertEqual(oc.partition_day(oc.week_start(k, S5) - 1, S5), oc.week_first_day(k) - 1)

    def test_load_runs_once_and_writes_the_receipt(self):
        train, test = make_world()
        receipt = self.load(train, test)
        self.assertEqual(od.read_load()['digest'], receipt['digest'])
        self.assertFalse(receipt['checked'])
        with self.assertRaisesRegex(oc.ContractError, 'runs once'):
            od.load(check_contract=False, threads=2, memory='1GB')

    def test_unchecked_load_is_refused_under_the_repo_root(self):
        train, test = make_world()
        receipt = self.load(train, test)                     # a test root: oc.ROOT is not this repository
        self.assertFalse(receipt['checked'])
        self.assertEqual(od.read_load()['digest'], receipt['digest'])
        with mock.patch.object(od, 'ROOT', self.root):        # the same receipt under the repository's ROOT
            with self.assertRaisesRegex(oc.ContractError, 'unchecked load only outside the repo'):
                od.read_load()
            with self.assertRaisesRegex(oc.ContractError, 'unchecked load only outside the repo'):
                od.s5()
            with self.assertRaisesRegex(oc.ContractError, 'unchecked load only outside the repo'):
                od.collect('train', self.base, threads=2, memory='1GB', n_train=3)
            with self.assertRaisesRegex(oc.ContractError, 'unchecked load only outside the repo'):
                od.load(check_contract=False, threads=2, memory='1GB')
        self.assertFalse(oc.collection_dir('train').exists())

    def test_sum_n2_and_q_sizes(self):
        w = {k: oc.week_start(k, S5) for k in (1, 2, 3, 4)}
        train = {
            1: [ev(1, w[1]), ev(1, w[1]+1), ev(1, w[2]+1)],      # W1-start: 2 in W1, 1 in W2
            2: [ev(1, w[2]+5), ev(2, w[2]+6), ev(2, w[3]+1), ev(2, w[4]+1)],   # W2-start
            3: [ev(1, w[3]+5)],                                 # W3-start
        }
        test = {9: [ev(1, S5), ev(2, S5+1)]}
        facts = self.load(train, test)['facts']
        # F2: H_2 = W1 (session 1: 2) + Q_2 full in W2 (session 2: 2) -> 4 + 4
        # F3: H_3 (session 1: 3, session 2: 2) + Q_3 in W3 (session 3: 1) -> 9 + 4 + 1
        # F4: H_4 (s1: 3, s2: 3, s3: 1) -> 9 + 9 + 1; no W4 starts
        # F5: all train (3, 4, 1) + test (2) -> 9 + 16 + 1 + 4
        self.assertEqual(facts['sum_n2_upper'], dict(F2=8, F3=14, F4=19, F5=30))
        self.assertEqual(facts['q_sessions_raw'], dict(W1=1, W2=1, W3=1, W4=0, W5=1))

    def contract_raw(self, train, test):
        write_raw(self.raw, train, test)
        (self.raw/od.ZIP_FILE).write_bytes(b'zip')
        (self.raw/od.ZIP_SHA_FILE).write_text(hashlib.sha256(b'zip').hexdigest() + '  ' + od.ZIP_FILE + '\n')
        return {name: (self.raw/name).stat().st_size for name in od.FILE_SIZES}

    def test_contract_sizes_and_zip_are_checked_before_reading(self):
        train, test = make_world()
        sizes = self.contract_raw(train, test)
        bad = dict(sizes, **{od.TRAIN_JSONL: sizes[od.TRAIN_JSONL] + 1})
        with mock.patch.object(od, 'FILE_SIZES', bad):
            with self.assertRaisesRegex(oc.ContractError, 'train.jsonl'):
                od.load(threads=2, memory='1GB')
        (self.raw/od.ZIP_SHA_FILE).write_text('0'*64 + '  x\n')
        with mock.patch.object(od, 'FILE_SIZES', sizes):
            with self.assertRaisesRegex(oc.ContractError, 'SHA-256'):
                od.load(threads=2, memory='1GB')
        self.assertFalse(oc.verify_path().exists())
        self.assertEqual(oc.existing_days(), [])

    def test_gate0_failure_writes_the_receipt_and_exits(self):
        train, test = make_world()
        sizes = self.contract_raw(train, test)
        with mock.patch.object(od, 'FILE_SIZES', sizes):
            with self.assertRaisesRegex(oc.ContractError, 'Gate 0 failed'):
                od.load(threads=2, memory='1GB')
        receipt = oc.read_json(oc.verify_path())
        self.assertTrue(receipt['checked'])
        self.assertFalse(receipt['gate0']['ok'])
        self.assertTrue(any('train_sessions' in f for f in receipt['gate0']['failures']))
        with self.assertRaisesRegex(oc.ContractError, 'Gate 0 failed'):
            od.read_load()

    def test_gate0_passes_on_matching_readme_facts(self):
        train, test = make_world()
        sizes = self.contract_raw(train, test)
        with mock.patch.object(od, 'FILE_SIZES', sizes), mock.patch.object(od, 'README_FACTS', {}):
            receipt = od.load(threads=2, memory='1GB')
        self.assertTrue(receipt['gate0']['ok'])
        self.assertTrue(receipt['files'][od.ZIP_FILE]['matches'])

    def test_gate0_refuses_test_aids_unknown_to_train(self):
        train, test = make_world()
        test[100_000].append(ev(999, S5 + DAY))
        sizes = self.contract_raw(train, test)
        with mock.patch.object(od, 'FILE_SIZES', sizes), mock.patch.object(od, 'README_FACTS', {}):
            with self.assertRaisesRegex(oc.ContractError, 'not in train'):
                od.load(threads=2, memory='1GB')


# =============================================================================== hashing and the cut

class CutTest(unittest.TestCase):

    def test_hex_to_ubigint_matches_hashlib(self):
        ids = list(range(10_000))
        con = duckdb.connect()
        con.execute('CREATE TABLE s AS SELECT range AS session FROM range(10000)')
        sql = od.hex_ubigint_sql("sha256(CAST(session AS VARCHAR) || ':otto-cut:2026')", con)
        got = dict(con.execute(f'SELECT session, {sql} FROM s').fetchall())
        expected = {i: int(hashlib.sha256(f'{i}:otto-cut:2026'.encode()).hexdigest()[:16], 16) for i in ids}
        self.assertEqual({int(k): int(v) for k, v in got.items()}, expected)
        self.assertTrue(any(v >= 2**63 for v in expected.values()))
        self.assertEqual(expected, {i: od.cut_hash(i) for i in ids})

    def test_two_half_fallback_agrees(self):
        con = duckdb.connect()
        con.execute('CREATE TABLE s AS SELECT range AS session FROM range(2000)')
        with mock.patch.object(od, '_HEX_CAST', False):
            sql = od.hex_ubigint_sql("sha256(CAST(session AS VARCHAR) || ':otto-cut:2026')")
        got = {int(k): int(v) for k, v in con.execute(f'SELECT session, {sql} FROM s').fetchall()}
        self.assertEqual(got, {i: od.cut_hash(i) for i in range(2000)})

    def test_cut_point_range_and_sql_twin(self):
        con = duckdb.connect()
        rows = [(s, n) for s in range(0, 3000, 7) for n in (2, 3, 7, 50, 500)]
        con.execute('CREATE TABLE x (session BIGINT, n BIGINT)')
        con.executemany('INSERT INTO x VALUES (?, ?)', rows)
        got = {(int(s), int(n)): int(c) for s, n, c in con.execute(f'SELECT session, n, {od.cut_sql()} FROM x').fetchall()}
        for (s, n), c in got.items():
            self.assertEqual(c, od.cut_point(s, n))
            self.assertTrue(1 <= c <= n - 1)
        self.assertEqual(od.cut_point(5, 2), 1)
        with self.assertRaises(oc.ContractError):
            od.cut_point(5, 1)


# =============================================================================== folds, frame, Pop

class FoldTest(TempRoot):

    def test_fold_membership_filters_and_truncation(self):
        w2, w3 = oc.week_start(2, S5), oc.week_start(3, S5)
        train = {
            1: [ev(1, w2 - 100), ev(2, w2 + 10), ev(3, w2 + 20)],          # starts in W1: not in Q_2, cut by H_2
            2: [ev(1, w2 + 100), ev(77, w2 + 110), ev(2, w2 + 120), ev(1, w3 + 5)],   # 77 unknown to H_2
            3: [ev(1, w2 + 200), ev(77, w2 + 210)],                        # one event after the aid filter
            4: [ev(1, w2 + 300), ev(2, w2 + 310), ev(1, w2 + 320, 'carts'), ev(2, w2 + 330, 'orders')],
            5: [ev(2, w2 - 50), ev(1, w2 - 40)],
        }
        test = {9: [ev(1, S5), ev(2, S5 + 1)]}
        self.load(train, test)
        frame, fold, labels = self.fold_frame(2)
        self.assertEqual(sorted(fold.session.unique()), [2, 4])
        s2 = fold[fold.session == 2]
        self.assertEqual(s2.aid.tolist(), [1, 2])                        # 77 dropped, W3 event dropped
        self.assertEqual(s2.n.unique().tolist(), [2])
        self.assertEqual(s2.c.unique().tolist(), [od.cut_point(2, 2)])
        s4 = fold[fold.session == 4]
        c4 = od.cut_point(4, 4)
        self.assertEqual(s4.c.unique().tolist(), [c4])
        self.assertTrue(1 <= c4 <= 3)
        # H_2 holds only events before start(W2)
        con = od.history(2, 'test', threads=1, memory='512MB')
        try:
            self.assertEqual(con.execute('SELECT max(ts) FROM hist').fetchone()[0], w2 - 40)
        finally:
            con.close()

    def test_clicks_label_is_the_first_click_of_the_suffix(self):
        w2 = oc.week_start(2, S5)
        train = {0: [ev(a, w2 - 100 + a) for a in range(1, 9)]}
        # find a session id whose cut leaves a suffix with several clicks
        sid = next(s for s in range(1, 500) if od.cut_point(s, 8) <= 3)
        c = od.cut_point(sid, 8)
        events = [ev(a, w2 + 10*a, 'carts' if a == c + 1 else 'clicks') for a in range(1, 9)]
        train[sid] = events
        self.load(train, {9: [ev(1, S5)]})
        _, _, labels = self.fold_frame(2)
        mine = labels[labels.session == sid]
        self.assertEqual(mine[mine.type == 'clicks'].aid.tolist(), [c + 2])
        self.assertEqual(mine[mine.type == 'carts'].aid.tolist(), [c + 1])
        self.assertEqual(mine[mine.type == 'orders'].aid.tolist(), [])

    def test_suffix_substitution_changes_no_feature(self):
        train, test = make_world(seed=11)
        self.load(train, test)
        frame_a, fold_a, labels_a = self.fold_frame(3)
        prefix_a = fold_a[fold_a.pos <= fold_a.c]
        self.tearDown()
        self.setUp()
        changed = dict(train)
        rng = np.random.default_rng(3)
        for session, group in fold_a.groupby('session'):
            c = int(group.c.iloc[0])
            events = list(changed[session])
            # suffix positions are those after the c-th kept event; all aids here are known to H_3
            kept_seq = group.sort_values('seq').seq.tolist()
            for seq in kept_seq[c:]:
                aid, ts, _ = events[seq-1]
                events[seq-1] = (int(rng.integers(1, 16)), ts, NAMES[int(rng.integers(0, 3))])
            changed[session] = events
        self.load(changed, test)
        frame_b, fold_b, labels_b = self.fold_frame(3)
        pd.testing.assert_frame_equal(frame_a, frame_b)
        prefix_b = fold_b[fold_b.pos <= fold_b.c]
        pd.testing.assert_frame_equal(prefix_a.reset_index(drop=True), prefix_b.reset_index(drop=True))
        self.assertFalse(labels_a.equals(labels_b))

    def test_base_candidates_come_from_the_prefix_only(self):
        train, test = make_world(seed=5)
        w3 = oc.week_start(3, S5)
        train[0] = train[0] + [ev(500, oc.week_start(1, S5) + 7)]     # aid 500 known to H_3
        sid = next(s for s in range(50_000, 60_000) if od.cut_point(s, 4) == 1)
        train[sid] = [ev(1, w3 + 10), ev(500, w3 + 20), ev(500, w3 + 30, 'carts'), ev(500, w3 + 40, 'orders')]
        self.load(train, test)
        frame, fold, labels = self.fold_frame(3)
        self.assertNotIn(500, frame[frame.session == sid].aid.tolist())
        self.assertIn(500, labels[labels.session == sid].aid.tolist())
        # every history candidate is a prefix aid of its own session
        prefix = fold[fold.pos <= fold.c]
        hist_pairs = set(map(tuple, frame[frame.h_rank.notna()][['session', 'aid']].values.tolist()))
        prefix_pairs = set(map(tuple, prefix[['session', 'aid']].values.tolist()))
        self.assertLessEqual(hist_pairs, prefix_pairs)
        self.assertEqual(prefix_pairs, hist_pairs)                  # depth 50 covers every prefix here
        # candidates: (h) then the three popularity lists, at most 110, unique
        self.assertFalse(frame.duplicated(['session', 'aid']).any())
        self.assertLessEqual(frame.groupby('session').size().max(), od.MAX_CANDIDATES)
        popular = frame[frame.h_rank.isna()]
        self.assertTrue(popular[['pop_rank_clicks', 'pop_rank_carts', 'pop_rank_orders']].notna().any(axis=1).all())

    def test_frame_features_by_hand(self):
        w2, w3 = oc.week_start(2, S5), oc.week_start(3, S5)
        train = {
            1: [ev(3, w2 - 8*DAY), ev(1, w3 - DAY), ev(2, w3 - DAY + 1, 'carts')],   # H_3; aid 3 outside 7 d
            2: [ev(1, w3 - 10), ev(2, w3 - 5, 'orders')],                            # W2 start, in H_3
        }
        sid = next(s for s in range(10, 5000) if od.cut_point(s, 5) == 4)
        train[sid] = [ev(1, w3 + 10), ev(2, w3 + 20, 'carts'), ev(1, w3 + 30), ev(3, w3 + 70), ev(2, w3 + 90)]
        self.load(train, {9: [ev(1, S5)]})
        frame, _, _ = self.fold_frame(3)
        rows = frame.set_index('aid')
        self.assertEqual(rows.loc[1, 's_len'], 4)
        self.assertEqual(rows.loc[1, 's_items'], 3)
        self.assertEqual(rows.loc[1, 's_carts'], 1)
        self.assertEqual(rows.loc[1, 's_dur'], 60)
        self.assertEqual((rows.loc[1, 'p_clicks'], rows.loc[1, 'p_last_pos'], rows.loc[1, 'p_last_age']), (2, 2, 40))
        self.assertEqual((rows.loc[3, 'p_is_last'], rows.loc[3, 'p_last_pos'], rows.loc[3, 'h_rank']), (1, 1, 1))
        self.assertEqual(rows.loc[1, 'h_rank'], 2)
        self.assertEqual(rows.loc[2, 'h_rank'], 3)
        self.assertEqual(rows.loc[2, 'p_carts'], 1)
        # H_3 = W1 + W2; the 7 days before start(W3) are W2: sessions 1 and 2 (day -1 of W2 is inside)
        self.assertEqual(rows.loc[2, 'i_h7_carts'], 1)
        self.assertEqual(rows.loc[2, 'i_h7_orders'], 1)
        self.assertEqual(rows.loc[3, 'i_h7_all'], 0)
        self.assertEqual(rows.loc[1, 'i_h7_all'], 2)
        self.assertEqual(rows.loc[2, 'i_wk_carts'], 1)
        self.assertEqual(rows.loc[1, 'pop_rank_clicks'], 1)

    def test_frame_does_not_depend_on_the_batch(self):
        train, test = make_world(seed=2)
        self.load(train, test)
        whole, _, _ = self.fold_frame(3)
        small, _, _ = self.fold_frame(3, batch=2)
        pd.testing.assert_frame_equal(whole, small)

    # (rows, frame_digest) of build_frame at commit e45e70f, before the B SQL moved into b_tables/b_feature_sql,
    # on make_world(seed=5, n_per_week=40): the contract base, a base whose depths and limit bite
    # (h 2, p_t 3, max 5, item windows of 1 and 3 days) and one without h_rank/pop_rank_carts in the base.
    GOLDEN = {
        ('initial', 2): (570, '90295abad0f31cd64137fb75733dccb63401605030511eacdb650d453e93af5a'),
        ('initial', 3): (600, '56959b2c4818205c445f4e10d26d7c28d448b50276097be4cca15362e2734caa'),
        ('small', 2): (190, '0279863e77117c88ccd15ed7fba72e95193d9d2edd14ef85dfa19b5b191aa1ae'),
        ('small', 3): (200, 'e8b062fbfd91685282fe3599e00c2f7be89b31277d34ccb4c114e8ee7d2c9336'),
        ('small2', 2): (266, 'c07b42962bf56745b24196af6da2070d4a0871d1102229a575b378b22a71261d'),
        ('small2', 3): (280, '2d94f97894c39980ca628a9363db2494aa3fb899e25d18466ad40fb22f13ab0d'),
    }

    @staticmethod
    def golden_bases():
        base = od.initial_base()
        small = copy.deepcopy(base['candidates'])
        small['history']['depth'], small['popular']['depth'], small['max'] = 2, 3, 5
        windows = [dict(name='i_h1_clicks', formula='x', missing='0'), dict(name='i_h3_all', formula='x', missing='0')]
        small2 = copy.deepcopy(small)
        small2['max'], small2['history']['depth'] = 7, 4
        return dict(initial=base, small=oc.make_base(small, base['features'] + windows),
                    small2=oc.make_base(small2, [f for f in base['features']
                                                 if f['name'] not in ('h_rank', 'pop_rank_carts')]))

    def test_frame_values_are_unchanged_by_the_shared_b_sql(self):
        train, test = make_world(seed=5, n_per_week=40)
        self.load(train, test)
        for name, base in self.golden_bases().items():
            self.base = base
            for k in (2, 3):
                for batch in (od.FRAME_BATCH, 4):
                    with self.subTest(base=name, k=k, batch=batch):
                        frame, _, _ = self.fold_frame(k, batch=batch)
                        self.assertEqual((len(frame), frame_digest(frame)), self.GOLDEN[(name, k)])

    def test_b_features_on_arbitrary_keys_from_neutral_views(self):
        """otto_agent's route: neutral sess/hist -> coded_events_sql -> b_tables -> b_feature_sql on any keys."""
        train, test = make_world(seed=2)
        self.load(train, test)
        con = od.connect(2, '1GB')
        out = Path(tempfile.mkdtemp(dir=self.tmp.name))
        try:
            od.build_fold(con, 3, 'test', S5)
            con.execute('CREATE TEMP TABLE frame_sessions AS SELECT DISTINCT session FROM fold')
            built = od.build_frame(con, 3, self.base, S5, out=out)
            frame = con.execute(f'SELECT * FROM read_parquet({[str(p) for p in built["parts"]]}) '
                                'ORDER BY session, aid').df()
            names = ' '.join(f"WHEN {c} THEN '{n}'" for c, n in enumerate(od.NEUTRAL_EVENTS))
            for view, source in (('sess', 'fold WHERE pos <= c'), ('hist_n', 'hist')):
                con.execute(f'CREATE TEMP VIEW {view} AS SELECT session, aid AS item, ts, '
                            f'CASE type {names} END AS event, seq FROM {source}')
            con.execute(f'CREATE TEMP VIEW pfx_n AS {od.coded_events_sql("sess")}')
            con.execute(f'CREATE TEMP VIEW hist_c AS {od.coded_events_sql("hist_n")}')
            spec = od.b_tables(con, self.base, oc.week_start(3, S5), prefix='pfx_n', hist='hist_c')
            self.assertEqual(spec['columns'], built['columns'])
            # every third frame key, plus an aid outside the candidates and a session without a prefix
            keys = frame[['session', 'aid']].iloc[::3]
            first = int(frame['session'].iloc[0])
            extra = pd.DataFrame({'session': [first, 10**9], 'aid': [987654, 1]})
            con.register('keys_in', pd.concat([keys, extra], ignore_index=True).astype('int64'))
            con.execute('CREATE TEMP TABLE keys AS SELECT * FROM keys_in')
            got = con.execute(od.b_feature_sql(spec, 'keys')).df()
            kinds = con.execute(f'DESCRIBE {od.b_feature_sql(spec, "keys")}').fetchall()
            # keys as a CTE of ``ctes``: the sessions relation is given, the default would read an unknown CTE
            in_cte = con.execute(od.b_feature_sql(spec, 'kc', '(SELECT DISTINCT session FROM keys)',
                                                  ctes='kc AS (SELECT * FROM keys)')).df()
            with self.assertRaisesRegex(oc.ContractError, 'sessions relation is required'):
                od.b_feature_sql(spec, 'kc', ctes='kc AS (SELECT * FROM keys)')
            # an event outside NEUTRAL_EVENTS (or NULL) fails the query, it never becomes a NULL type
            for event in ("'like'", 'NULL'):
                con.execute(f"""CREATE OR REPLACE TEMP VIEW odd AS SELECT * FROM sess UNION ALL
                    (SELECT session, item, ts, {event}, seq + 1000 FROM sess LIMIT 5)""")
                with self.subTest(event=event), self.assertRaisesRegex(duckdb.Error, 'unknown event'):
                    con.execute(f'SELECT count(*), count(type) FROM ({od.coded_events_sql("odd")})').fetchall()
        finally:
            con.close()
        self.assertEqual(list(got.columns), ['session', 'aid', *built['columns']])
        self.assertEqual({n: t for n, t, *_ in kinds if n in spec['types']}, spec['types'])
        pd.testing.assert_frame_equal(in_cte, got)
        on_frame = got.merge(keys, on=['session', 'aid'])
        expected = frame.merge(keys, on=['session', 'aid'])
        pd.testing.assert_frame_equal(on_frame.reset_index(drop=True), expected.reset_index(drop=True))
        outside = got[(got['session'] == first) & (got['aid'] == 987654)].iloc[0]
        session_row = frame[frame['session'] == first].iloc[0]
        for column in ('s_len', 's_items', 's_dur'):                         # session values hold for any key
            self.assertEqual(outside[column], session_row[column])
        self.assertTrue(pd.isna(outside['h_rank']) and outside['p_clicks'] == 0 and outside['p_is_last'] == 0)
        self.assertNotIn(10**9, set(got['session']))                         # no prefix, no row

    def test_pop_does_not_see_the_future(self):
        train, test = make_world(seed=4)
        self.load(train, test)
        frame_a, fold_a, _ = self.fold_frame(3)
        pop_a = od.pop(frame_a)
        self.tearDown()
        self.setUp()
        later = dict(train)
        w4 = oc.week_start(4, S5)
        for i in range(30):                                          # a flood of one aid in W4 and in test
            later[90_000+i] = [ev(15, w4 + 10*i, 'orders'), ev(15, w4 + 10*i + 1, 'carts')]
        for session, group in fold_a.groupby('session'):             # and every F3 suffix rewritten to aid 15
            c = int(group.c.iloc[0])
            events = list(later[session])
            for seq in group.sort_values('seq').seq.tolist()[c:]:
                events[seq-1] = (15, events[seq-1][1], 'orders')
            later[session] = events
        test2 = {**test, **{200_000+i: [ev(15, S5 + i, 'orders')] for i in range(20)}}
        self.load(later, test2)
        frame_b, _, _ = self.fold_frame(3)
        pd.testing.assert_frame_equal(pop_a, od.pop(frame_b))
        pd.testing.assert_frame_equal(frame_a, frame_b)
        self.assertTrue((pop_a.groupby(['session', 'type']).size() <= oc.TOP_K).all())
        first = pop_a[pop_a['rank'] == 1].merge(frame_a[frame_a.h_rank == 1][['session', 'aid']], on=['session', 'aid'])
        self.assertEqual(len(first), 3*frame_a.session.nunique())

    def test_canaries_at_the_w4_boundary(self):
        train, test = make_world(seed=9)
        w4 = oc.week_start(4, S5)
        train[70_001] = [ev(1, w4 - 50), ev(901, w4 - 1)]            # last second of W3: visible
        train[70_002] = [ev(2, w4), ev(902, w4 + 1)]                 # first second of W4: closed
        test[300_000] = [ev(1, S5 + 5), ev(903, S5 + 6)]
        train[0] = train[0] + [ev(903, oc.week_start(1, S5) + 3)]    # keeps 903 a train aid
        self.load(train, test)
        con = od.history(4, 'dev', threads=1, memory='512MB')
        try:
            aids = {a for (a,) in con.execute('SELECT DISTINCT aid FROM hist').fetchall()}
            max_ts = con.execute('SELECT max(ts) FROM hist').fetchone()[0]
        finally:
            con.close()
        self.assertIn(901, aids)
        self.assertNotIn(902, aids)
        self.assertLess(max_ts, w4)
        for purpose in ('dev', 'probe', 'agent', oc.COLLECT_HOLDOUT):
            with self.assertRaisesRegex(oc.ContractError, 'closed'):
                od._partition_files([-7], purpose)
            with self.assertRaisesRegex(oc.ContractError, 'closed'):
                od._partition_files([0], purpose)
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.history(5, 'dev')
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.views(5, 'agent')
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.collect('kaggle', self.base)
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.collect_holdout(self.base)
        with self.assertRaisesRegex(oc.ContractError, 'F2 and F3 only'):
            od.fold_stats(4)
        with self.assertRaisesRegex(oc.ContractError, 'F2 and F3'):
            od.rehearse_frame(4)
        # B and Pop on F3 do not see W4 or W5: neither canary reaches the frame
        frame, _, _ = self.fold_frame(3)
        self.assertFalse(frame.aid.isin([902, 903]).any())
        # views of F3 read only partitions before W3 for hist
        collection = od.collect('val', self.base, threads=2, memory='1GB', n_train=5, dev_population=10, probe_pool=3)
        view = od.views(3, 'agent', collection=collection['path'])
        self.assertTrue(all(int(Path(d).name[2:]) < oc.week_first_day(3) for d in view['directories']['hist']))
        self.assertNotIn('902', json.dumps(view))
        files = view['files']['hist'] + view['files']['sess']
        seen = duckdb.sql(f"SELECT max(ts) FROM read_parquet({files}, hive_partitioning=false)").fetchone()[0]
        self.assertLess(seen, w4)

    def test_collect_holdout_opens_w4_once(self):
        train, test = make_world(seed=12)
        w4 = oc.week_start(4, S5)
        train[70_002] = [ev(2, w4), ev(3, w4 + 1), ev(4, w4 + 2)]
        self.load(train, test)
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.collect_holdout()
        self.commit_prereg()
        manifest = od.collect_holdout(threads=2, memory='1GB')
        collection = Path(manifest['path'])
        self.assertEqual(collection, oc.current_holdout_collection())
        sealed = collection/'sealed'/oc.LABELS_FILE
        self.assertEqual(oct(sealed.stat().st_mode & 0o777), '0o400')
        self.assertFalse((collection/oc.LABELS_FILE).exists())
        text = json.dumps(manifest['counts']).lower()
        for word in oc.HOLDOUT_FORBIDDEN_WORDS:
            self.assertNotIn(word, text)
        for key in od.HOLDOUT_SUFFIX_COUNTS:
            self.assertNotIn(key, manifest['counts'])
            self.assertNotIn(key, oc.read_json(collection/oc.MANIFEST_FILE)['counts'])
        self.assertEqual(manifest['code'], IDENTITY)
        frame = oc.read_parquet(collection/oc.FRAME_FILE)
        self.assertIn(70_002, frame.session.tolist())
        self.assertTrue(frame.equals(frame.sort_values(['session', 'aid']).reset_index(drop=True)))
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.collect_holdout()
        # views of F4 after collect-holdout: sess only from prefix/, hist only d < -7
        view = od.views(4, 'agent')
        prefix = collection/oc.PREFIX_DIR
        self.assertEqual(view['directories']['sess'], [str(prefix)])
        self.assertTrue(view['files']['sess'])
        self.assertTrue(all(Path(f).is_relative_to(prefix) for f in view['files']['sess']))
        self.assertTrue(view['files']['hist'])
        self.assertTrue(all(int(Path(d).name[2:]) < oc.week_first_day(4) for d in view['directories']['hist']))
        hist_max = duckdb.sql(f"SELECT max(ts) FROM read_parquet({view['files']['hist']}, "
                              f"hive_partitioning=false)").fetchone()[0]
        self.assertLess(hist_max, w4)
        self.assertNotIn('sealed', json.dumps(view))
        sess = duckdb.sql(f"SELECT DISTINCT session FROM ({view['views']['sess']})").df()
        self.assertEqual(set(sess.session), set(frame.session))

    def test_holdout_directory_exists_before_w4_is_read(self):
        train, test = make_world(seed=16)
        self.load(train, test)
        self.commit_prereg()
        target = oc.current_holdout_collection()
        seen = {}

        def crash(con, k, purpose, s5_, files=None):
            seen['exists'] = target.is_dir()
            seen['w4'] = any(f'{-1}' in Path(f).parent.name for f in files[1])
            raise RuntimeError('crash while reading W4')
        with mock.patch.object(od, 'build_fold', crash), self.assertRaisesRegex(RuntimeError, 'crash'):
            od.collect_holdout(threads=2, memory='1GB')
        self.assertTrue(seen['exists'])
        self.assertTrue(seen['w4'])
        self.assertTrue(target.is_dir())
        with self.assertRaisesRegex(oc.ContractError, 'closed'):     # the window stays closed after a crash
            od.collect_holdout(threads=2, memory='1GB')

    def test_holdout_kaggle_and_assemble_need_the_prereg_code(self):
        train, test = make_world(seed=17)
        self.load(train, test)
        self.commit_prereg()
        other = dict(files=dict(IDENTITY['files'], **{'scripts/otto_data.py': 'c'*64}), missing=[])
        with mock.patch.object(oc, 'code_identity', return_value=other):
            with self.assertRaisesRegex(oc.ContractError, 'Code differs'):
                od.collect_holdout(threads=2, memory='1GB')
            self.assertFalse(oc.current_holdout_collection().exists())
            self.commit_result()
            with self.assertRaisesRegex(oc.ContractError, 'Code differs'):
                od.collect('kaggle', self.base, threads=2, memory='1GB')
            out = oc.output_dir('kaggle')
            out.mkdir(parents=True)
            ranked = pd.DataFrame([(100_000, 'clicks', 1, 1)], columns=list(oc.RANKED_COLUMNS))
            with self.assertRaisesRegex(oc.ContractError, 'Code differs'):
                od.assemble(ranked, out/'B.csv', [100_000], {1}, ranked)
            self.assertEqual(list(out.iterdir()), [])

    def test_train_event_at_s5_is_in_f4_and_in_h5(self):
        train, test = make_world(seed=21)
        w1, w4 = oc.week_start(1, S5), oc.week_start(4, S5)
        train[70_011] = [ev(1, w1 + 5), ev(2, w1 + 6), ev(3, w1 + 7)]     # aids 1..3 known to H_4
        train[70_010] = [ev(1, w4 + 10), ev(2, w4 + 20), ev(3, S5, ms=3)]   # < first test ms (S5 s + 5 ms)
        self.load(train, test)
        self.assertEqual(oc.existing_days('train')[-1], -1)
        self.commit_prereg()
        con = od.connect(2, '1GB')
        try:
            od.build_fold(con, 4, oc.COLLECT_HOLDOUT, S5)
            rows = con.execute('SELECT aid, ts FROM fold WHERE session = 70010 ORDER BY seq').fetchall()
        finally:
            con.close()
        self.assertEqual(rows, [(1, w4 + 10), (2, w4 + 20), (3, S5)])
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.history(5, 'final')
        self.commit_result()
        con = od.history(5, 'final', threads=1, memory='512MB')
        try:
            self.assertEqual(con.execute('SELECT max(ts), count(*) FILTER (WHERE ts = ?) FROM hist',
                                         [S5]).fetchone(), (S5, 1))
            self.assertEqual(con.execute('SELECT count(*) FROM hist WHERE session = 70010').fetchone()[0], 3)
        finally:
            con.close()

    def test_kaggle_collection_after_the_result_receipt(self):
        train, test = make_world(seed=15)
        self.load(train, test)
        with self.assertRaisesRegex(oc.ContractError, 'closed'):
            od.collect('kaggle', self.base)
        self.commit_prereg()
        self.commit_result()
        manifest = od.collect('kaggle', self.base, threads=2, memory='1GB', batch=3)
        self.assertEqual(manifest['code'], IDENTITY)
        path = Path(manifest['path'])
        self.assertEqual(path.name, 'kaggle-F5')
        self.assertFalse((path/oc.LABELS_FILE).exists())
        frame = oc.read_parquet(path/oc.FRAME_FILE)
        self.assertEqual(set(frame.session), set(test))
        # the whole test session is the prefix: its last event has p_is_last = 1
        for session, events in test.items():
            last = events[-1][0]
            rows = frame[(frame.session == session) & (frame.aid == last)]
            self.assertEqual(rows.p_is_last.tolist(), [1])
        ranked = od.pop(path/oc.FRAME_FILE)
        out = oc.output_dir('kaggle')
        out.mkdir(parents=True)
        known = {a for events in train.values() for a, _, _ in events}
        with self.assertRaisesRegex(oc.ContractError, 'need 20'):      # 15 aids cannot fill 20 slots
            od.assemble(ranked[ranked['rank'] <= 5], out/'Pop.csv', sorted(test), known, ranked)
        extra = pd.DataFrame([(s_, t, 1000+i, 100+i) for s_ in test for t in NAMES for i in range(20)],
                             columns=list(oc.RANKED_COLUMNS))
        body = od.assemble(ranked[ranked['rank'] <= 5], out/'Pop.csv', sorted(test), known | set(range(1000, 1020)),
                           pd.concat([ranked, extra], ignore_index=True))
        self.assertEqual((body['rows'], body['filled_sessions']), (3*len(test), len(test)))
        self.assertEqual(body['code'], IDENTITY)
        targets = od.kaggle_targets(threads=2, memory='1GB')
        self.assertEqual(targets['sessions'], sorted(test))
        self.assertEqual(targets['sample_rows'], 3*len(test))
        self.assertEqual(targets['known'], known)
        filled = od.pop(path/oc.FRAME_FILE, self.root/'artifacts'/'otto'/'pop.parquet')
        self.assertEqual(filled['rows'], len(ranked))
        pd.testing.assert_frame_equal(oc.read_parquet(filled['path']), ranked)
        (self.raw/od.SAMPLE_CSV).write_text('session_type,labels\n')
        with self.assertRaisesRegex(oc.ContractError, 'differs from the load receipt'):
            od.kaggle_targets()

    def test_kaggle_targets_compare_the_sample_sessions(self):
        train, test = make_world(seed=18)
        write_raw(self.raw, train, test)
        lines = (self.raw/od.SAMPLE_CSV).read_text().splitlines()
        swapped = [line.replace(f'{max(test)}_', '424242_') for line in lines]    # same count, other session
        (self.raw/od.SAMPLE_CSV).write_text('\n'.join(swapped) + '\n')
        od.load(check_contract=False, threads=2, memory='1GB')
        self.commit_prereg()
        self.commit_result()
        od.collect('kaggle', self.base, threads=2, memory='1GB')
        with self.assertRaisesRegex(oc.ContractError, '1 extra, 1 missing'):
            od.kaggle_targets(threads=2, memory='1GB')

    def test_probe_pool_is_outside_the_dev_population(self):
        train, test = make_world(seed=13, n_per_week=30)
        self.load(train, test)
        probe = od.collect('probe', self.base, threads=2, memory='1GB', probe_pool=6)
        val = od.collect('val', self.base, threads=2, memory='1GB', n_train=4, dev_population=10, probe_pool=6)
        pool = set(oc.read_parquet(Path(probe['path'])/oc.FRAME_FILE).session)
        population = set(oc.read_population(val['path']))
        self.assertEqual(len(pool), 6)
        self.assertFalse(pool & population)
        prefix = [str(f) for f in (Path(val['path'])/oc.PREFIX_DIR).rglob('*.parquet')]
        q3 = [int(x) for (x,) in duckdb.sql(f'SELECT DISTINCT session FROM read_parquet({prefix}, '
                                            f'hive_partitioning=false)').fetchall()]
        expected_pool = oc.first_in_order(q3, 6, key=oc.probe_key)
        self.assertEqual(sorted(pool), sorted(expected_pool))
        self.assertEqual(val['probe_pool_digest'], oc.canonical_digest(expected_pool))
        self.assertEqual(probe['pool_digest'], oc.canonical_digest(expected_pool))
        expected_population = oc.first_in_order(set(q3) - set(expected_pool), 10)
        self.assertEqual(sorted(population), sorted(expected_population))
        labels = oc.read_parquet(Path(probe['path'])/oc.LABELS_FILE)
        self.assertLessEqual(set(labels.session), pool)
        val_frame = oc.read_parquet(Path(val['path'])/oc.FRAME_FILE)
        self.assertLessEqual(population, set(val_frame.session))
        oc.read_collection(val['path'], role='val', base=self.base)
        oc.read_collection(probe['path'], role='probe', base=self.base)

    def test_training_sessions_follow_the_sha256_order(self):
        rows = [(s, NAMES[s % 3], s) for s in range(200)] + [(s, 'orders', 1) for s in range(0, 200, 5)]
        labels = pd.DataFrame(rows, columns=list(oc.LABEL_COLUMNS)).drop_duplicates()
        got = od.training_sessions(labels, n=7)
        for t in NAMES:
            sessions = labels[labels.type == t].session.tolist()
            self.assertEqual(got[t], oc.first_in_order(sessions, 7))

    def test_collect_train_frame_and_manifest(self):
        train, test = make_world(seed=14, n_per_week=25)
        self.load(train, test)
        manifest = od.collect('train', self.base, threads=2, memory='1GB', n_train=5, batch=2)
        path = Path(manifest['path'])
        self.assertEqual(path.name, 'train-F2')
        frame = oc.read_parquet(path/oc.FRAME_FILE)
        labels = oc.read_parquet(path/oc.LABELS_FILE)
        training = od.training_sessions(labels, n=5)
        self.assertEqual(set(frame.session), set().union(*training.values()))
        self.assertEqual(list(frame.columns), ['session', 'aid', *oc.base_feature_names(self.base)])
        self.assertTrue(frame.equals(frame.sort_values(['session', 'aid']).reset_index(drop=True)))
        prefix = list((path/oc.PREFIX_DIR).rglob('*.parquet'))
        self.assertTrue(prefix)
        self.assertTrue(all(oc.week_days(2)[0] <= int(p.parent.name[2:]) <= oc.week_days(2)[1] for p in prefix))
        oc.read_collection(path, role='train', base=self.base)
        types = dict(duckdb.sql(f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM "
                                f"read_parquet('{path/oc.FRAME_FILE}'))").fetchall())
        self.assertEqual((types['session'], types['aid']), ('BIGINT', 'BIGINT'))
        self.assertEqual((types['h_rank'], types['p_last_pos'], types['pop_rank_orders']), ('USMALLINT',)*3)
        self.assertEqual((types['s_dur'], types['p_last_age'], types['i_h7_all']), ('INTEGER',)*3)
        self.assertEqual(types['p_is_last'], 'UTINYINT')
        self.assertEqual(manifest['counts']['frame_sessions'], frame.session.nunique())
        self.assertEqual(manifest['counts']['frame_rows'], len(frame))
        self.assertEqual(sorted(p.name for p in path.iterdir()),
                         sorted([oc.FRAME_FILE, oc.LABELS_FILE, oc.MANIFEST_FILE, oc.PREFIX_DIR]))
        self.assertFalse(any(p.name.startswith(('.frame-', 'duckdb-')) for p in oc.artifacts_dir().rglob('*')))
        with self.assertRaisesRegex(oc.ContractError, 'exists'):
            od.collect('train', self.base, threads=2, memory='1GB', n_train=5)

    def test_rehearse_frame_measures_the_whole_fold(self):
        train, test = make_world(seed=19, n_per_week=25)
        self.load(train, test)
        whole, fold, _ = self.fold_frame(3)
        report = od.rehearse_frame(3, threads=2, memory='1GB', batch=4, keep=True)
        kept = Path(report['kept'])
        frame = oc.read_parquet(kept/oc.FRAME_FILE)
        pd.testing.assert_frame_equal(frame, whole)
        self.assertEqual(report['sessions'], fold.session.nunique())
        self.assertEqual(report['frame_rows'], len(whole))
        self.assertGreater(report['batches'], 1)
        for key in ('peak_rss_mb', 'peak_spill_mb', 'peak_scratch_mb', 'frame_bytes'):
            self.assertGreaterEqual(report[key], 0)
        self.assertEqual(set(report['seconds']), {'fold', 'frame', 'concat', 'total'})
        self.assertEqual(set(report['projected_rows']), {'F4', 'F5'})
        report = od.rehearse_frame(3, threads=2, memory='1GB', batch=4)
        self.assertIsNone(report['kept'])
        self.assertEqual(sorted(p.name for p in oc.artifacts_dir().iterdir() if p.name.startswith('.rehearse-')),
                         [kept.name])
        self.assertFalse(oc.collection_dir('val').exists())


# =============================================================================== assemble

class AssembleTest(TempRoot):

    def setUp(self):
        super().setUp()
        self.commit_prereg()
        self.out = oc.output_dir('kaggle')
        self.out.mkdir(parents=True)
        self.sessions = [10, 11, 12]
        self.known = set(range(1, 101))
        self.fill = pd.DataFrame([(s, t, a, r) for s in self.sessions for t in NAMES
                                  for r, a in enumerate(range(50, 80), start=1)], columns=list(oc.RANKED_COLUMNS))

    def ranked(self, rows):
        return pd.DataFrame(rows, columns=list(oc.RANKED_COLUMNS))

    def test_assemble_fills_from_pop_without_repeats(self):
        rows = [(10, t, a, r) for t in NAMES for r, a in enumerate(range(1, 21), start=1)]
        rows += [(11, 'clicks', 50, 1), (11, 'clicks', 7, 2)]
        body = od.assemble(self.ranked(rows), self.out/'B2026.csv', self.sessions, self.known, self.fill)
        self.assertEqual(body['rows'], 9)
        self.assertEqual(body['filled_sessions'], 2)
        lines = (self.out/'B2026.csv').read_text().splitlines()
        self.assertEqual(lines[0], oc.SUBMISSION_HEADER)
        self.assertEqual(lines[1], '10_clicks,' + ' '.join(str(a) for a in range(1, 21)))
        self.assertEqual(lines[4].split(',')[1].split()[:3], ['50', '7', '51'])
        self.assertTrue((self.out/'B2026.json').exists())
        self.assertFalse((self.out/'B2026.csv.part').exists())
        self.assertEqual((body['ranked_sha256'], body['fill_sha256']), (None, None))     # frames, not files

    def test_assemble_receipt_names_the_ranked_file(self):
        rows = [(s, t, a, r) for s in self.sessions for t in NAMES for r, a in enumerate(range(1, 21), start=1)]
        ranked, fill = self.out/'ranked.parquet', self.out/'pop.parquet'
        oc.write_parquet(self.ranked(rows), ranked)
        oc.write_parquet(self.fill, fill)
        body = od.assemble(ranked, self.out/'BA2026.csv', self.sessions, self.known, fill)
        self.assertEqual((body['ranked_sha256'], body['fill_sha256'], body['filled_sessions']),
                         (oc.sha256_file(ranked), oc.sha256_file(fill), 0))
        self.assertEqual(oc.read_json(self.out/'BA2026.json'), body)
        # the hash names the bytes DuckDB read: a file replaced after the copy does not move it
        before = oc.sha256_file(ranked)
        copy = od._copy_hashed
        def copy_then_replace(source, target):
            digest = copy(source, target)
            if Path(source) == ranked:
                ranked.write_bytes(b'replaced')
            return digest
        with mock.patch.object(od, '_copy_hashed', side_effect=copy_then_replace):
            again = od.assemble(ranked, self.out/'BA2027.csv', self.sessions, self.known, fill)
        self.assertEqual(again['ranked_sha256'], before)
        self.assertNotEqual(oc.sha256_file(ranked), before)

    def write(self, lines):
        path = self.out/'x.csv'
        path.write_text('\n'.join([oc.SUBMISSION_HEADER, *lines]) + '\n')
        return path

    def good(self):
        return [f'{s}_{t},' + ' '.join(str(a) for a in range(1, 21)) for s in self.sessions for t in NAMES]

    def test_check_submission_accepts_a_good_file(self):
        self.assertEqual(od.check_submission(self.write(self.good()), self.sessions, self.known),
                         dict(rows=9, sessions=3))

    def test_check_submission_rejects(self):
        cases = {
            '19 aids': (0, '10_clicks,' + ' '.join(str(a) for a in range(1, 20))),
            'repeated aid': (0, '10_clicks,' + ' '.join(str(a) for a in [1]*2 + list(range(2, 20)))),
            'unknown aids': (0, '10_clicks,' + ' '.join(str(a) for a in range(500, 520))),
        }
        for message, (index, line) in cases.items():
            lines = self.good()
            lines[index] = line
            with self.subTest(message), self.assertRaisesRegex(oc.ContractError, message):
                od.check_submission(self.write(lines), self.sessions, self.known)
        lines = [line for line in self.good() if not line.startswith('12_')]
        with self.assertRaisesRegex(oc.ContractError, 'missing'):
            od.check_submission(self.write(lines), self.sessions, self.known)
        with self.assertRaisesRegex(oc.ContractError, 'sample_submission'):
            od.check_submission(self.write(self.good()), self.sessions, self.known, sample_rows=12)

    def test_assemble_refuses_unknown_aids_and_leaves_no_part(self):
        rows = [(10, 'clicks', 999, 1)]
        with self.assertRaisesRegex(oc.ContractError, 'unknown aids'):
            od.assemble(self.ranked(rows), self.out/'B.csv', self.sessions, self.known, self.fill)
        self.assertEqual(list(self.out.iterdir()), [])
        with self.assertRaisesRegex(oc.ContractError, 'repeated aid'):
            od.assemble(self.ranked([(10, 'clicks', 1, 1), (10, 'clicks', 1, 2)]), self.out/'B.csv',
                        self.sessions, self.known, self.fill)


# =============================================================================== base and CLI

class BaseAndCliTest(unittest.TestCase):

    def test_initial_base_is_the_contract_base(self):
        base = od.initial_base()
        oc.check_base(base)
        self.assertEqual(len(base['features']), 21)
        self.assertEqual(base['candidates']['max'], 110)
        self.assertEqual(base['categorical'], [])

    def test_unknown_or_long_window_features_are_refused(self):
        with self.assertRaisesRegex(oc.ContractError, 'Unknown base feature'):
            od._feature_sql('cooc_score', set())
        with self.assertRaisesRegex(oc.ContractError, '1..7 days'):
            od._feature_sql('i_h14_all', set())
        windows = set()
        od._feature_sql('i_h3_orders', windows)
        self.assertEqual(windows, {(3, 'orders')})

    def test_week_sql_matches_week_of_day(self):
        con = duckdb.connect()
        for d in range(-40, 8):
            self.assertEqual(con.execute(f'SELECT {od.week_sql(d)}').fetchone()[0], oc.week_of_day(d))

    def run_cli(self, *args, isolated=True):
        command = [sys.executable, *(['-I'] if isolated else []), str(REPO/'scripts'/'otto_data.py'), *args]
        result = subprocess.run(command, capture_output=True, text=True, cwd=tempfile.gettempdir(),
                                env=dict(os.environ))
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stdout + result.stderr)
        return result.returncode, json.loads(lines[0])

    def test_cli_refuses_without_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'base.json'
            code, payload = self.run_cli('init-base', '--output', str(target), isolated=False)
            self.assertFalse(target.exists())
        self.assertEqual(code, 1)
        self.assertFalse(payload['ok'])
        self.assertIn('-I', payload['error'])

    def test_cli_init_base_with_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'base.json'
            code, payload = self.run_cli('init-base', '--output', str(target))
            self.assertEqual(code, 0, payload)
            self.assertEqual(oc.read_json(target)['digest'], od.initial_base()['digest'])
            code, payload = self.run_cli('init-base', '--output', str(target))
            self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
