"""Synthetic tests of scripts/otto_common.py (docs/otto-design.md §2.5, §3, §7, §10, §11).

No real OTTO data is read: every frame, partition and receipt is built here.
"""
import ast
import importlib
import json
import math
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

S5 = 1_662_328_791          # any second; the contract fixes no calendar date
REPO = Path(oc.__file__).resolve().parents[1]


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


def frame(rows, columns):
    return pd.DataFrame(rows, columns=list(columns))


def ranked(rows):
    return frame(rows, oc.RANKED_COLUMNS)


def labels(rows):
    return frame(rows, oc.LABEL_COLUMNS)


OPEN = dict(format=oc.HOLDOUT_OPEN_FORMAT, quote='да, открывай holdout OTTO', gate1=dict(ok=True))
OPEN2 = dict(format=oc.HOLDOUT_OPEN_2_FORMAT, scores={'fits/BA2027/holdout.parquet': '0'*64})
EXAMPLE_SESSIONS = [1, 2, 3, 4]


def evaluate_mirror(pred_rows, gt_rows, sessions):
    """Pure-Python twin of the Kaggle evaluate.py: top 20 by rank, set intersection, Σhits/Σmin(20, |G|)."""
    preds, truth = {}, {}
    for session, type_, aid, rank in sorted(pred_rows, key=lambda r: r[3]):
        preds.setdefault((session, type_), []).append(aid)
    for session, type_, aid in gt_rows:
        truth.setdefault((session, type_), set()).add(aid)
    recall = {}
    for type_ in oc.TYPES:
        hits = den = 0
        for session in sessions:
            gt = truth.get((session, type_))
            if not gt:
                continue
            hits += len(set(preds.get((session, type_), [])[:20]) & gt)
            den += min(20, len(gt))
        recall[type_] = hits/den
    return recall


def ranked_list(session, type_, aids):
    return [(session, type_, aid, rank) for rank, aid in enumerate(aids, start=1)]


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

    def tearDown(self):
        self.patch.stop()
        for path in self.root.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        self.tmp.cleanup()

    def commit(self, *paths):
        git(self.root, 'add', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def write_config(self, kind, value, commit=True):
        path = oc.config_path(kind)
        path.write_text(json.dumps(value))
        if commit:
            self.commit(path)
        return path

    def commit_prereg(self):
        base = self.write_config('base', dict(b=1))
        agent_set = self.write_config('set', dict(s=1, audit=dict(verdict='clean')))
        return self.write_config('prereg', dict(base_sha256=oc.sha256_file(base), set_sha256=oc.sha256_file(agent_set),
                                                code={'scripts/otto_common.py': 'x'}))

    def holdout_collection(self, name=None):
        col = oc.new_output(oc.output_dir('collections', name or oc.collection_name('holdout')))
        (col/oc.PREFIX_DIR).mkdir()
        oc.write_parquet(frame([(1, 10, S5-5*86400, 'clicks', 1)], oc.EVENT_COLUMNS), col/oc.PREFIX_DIR/'p.parquet')
        oc.write_parquet(frame([(1, 10)], oc.FRAME_KEYS), col/oc.FRAME_FILE)
        sealed = oc.write_sealed(col, lambda d: oc.write_parquet(labels([(1, 'carts', 11)]), d/oc.LABELS_FILE))
        oc.write_manifest(col, 'holdout', dict(sessions=1, rows=1), oc.make_base({}, []), {}, sealed=sealed)
        return col


# ================================================================== metric (§3)

class Metric(unittest.TestCase):
    """Population 1..4; recalls worked out by hand in the comments."""

    def example(self):
        gt = [(1, 'clicks', 10), (1, 'carts', 11), (1, 'carts', 12), (1, 'carts', 13), (1, 'orders', 11),
              (2, 'clicks', 20), (2, 'orders', 21), (2, 'orders', 22),
              (4, 'clicks', 40)] + [(4, 'carts', 100+i) for i in range(25)]          # session 3 has no labels
        pred = (ranked_list(1, 'clicks', [5, 6, 7, 8, 10])                            # click at rank 5: hit
                + ranked_list(1, 'carts', [11, 99, 12])                               # 2 of 3
                + ranked_list(1, 'orders', [98])                                      # 0 of 1
                + ranked_list(2, 'clicks', [21, 22])                                  # miss
                + ranked_list(2, 'orders', [21])                                      # 1 of 2, a short list
                + ranked_list(3, 'clicks', [1, 2, 3])                                 # no labels: 0/0
                + ranked_list(4, 'carts', [100+i for i in range(20)]))                # 20 of min(25, 20)
        return ranked(pred), labels(gt)

    def test_hand_computed(self):
        pred, gt = self.example()
        m = oc.metric(pred, gt, sessions=[4, 3, 2, 1])
        self.assertEqual(m['sessions'].tolist(), [1, 2, 3, 4])
        self.assertEqual(m['hits']['clicks'].tolist(), [1, 0, 0, 0])
        self.assertEqual(m['den']['clicks'].tolist(), [1, 1, 0, 1])     # session 4 has no ranked rows: 0 hits
        self.assertEqual(m['hits']['carts'].tolist(), [2, 0, 0, 20])
        self.assertEqual(m['den']['carts'].tolist(), [3, 0, 0, 20])
        self.assertEqual(m['hits']['orders'].tolist(), [0, 1, 0, 0])
        self.assertEqual(m['den']['orders'].tolist(), [1, 2, 0, 0])
        self.assertAlmostEqual(m['recall']['clicks'], 1/3, places=15)
        self.assertAlmostEqual(m['recall']['carts'], 22/23, places=15)
        self.assertAlmostEqual(m['recall']['orders'], 1/3, places=15)
        self.assertAlmostEqual(m['score'], 0.10/3 + 0.30*22/23 + 0.60/3, places=15)
        # a ratio of sums, not a mean of per-session ratios ((2/3 + 20/20) / 2)
        self.assertNotAlmostEqual(m['recall']['carts'], (2/3 + 1)/2, places=3)

    def test_weights_are_exact(self):
        self.assertEqual(oc.WEIGHTS, {'clicks': 0.10, 'carts': 0.30, 'orders': 0.60})
        self.assertEqual(oc.TOP_K, 20)

    def test_sessions_required_and_outside_rows(self):
        pred, gt = self.example()
        with self.assertRaises(TypeError):                                         # sessions is keyword-only
            oc.metric(pred, gt, [1, 2])
        with self.assertRaises(TypeError):                                         # and required
            oc.metric(pred, gt)
        with self.assertRaises(oc.ContractError):
            oc.metric(pred, gt, sessions=None)
        restricted = oc.metric(pred, gt, sessions=[1, 2, 7])
        self.assertEqual(restricted['sessions'].tolist(), [1, 2, 7])
        self.assertEqual(restricted['den']['carts'].tolist(), [3, 0, 0])            # session 4 is outside
        self.assertAlmostEqual(restricted['recall']['carts'], 2/3)
        self.assertEqual(restricted['hits']['clicks'].tolist(), [1, 0, 0])          # 7: no rows, no labels

    def test_duplicate_aid_refused(self):
        pred = ranked(ranked_list(1, 'carts', [11, 12, 11]))
        with self.assertRaisesRegex(oc.ContractError, 'repeated aid'):
            oc.metric(pred, labels([(1, 'carts', 11)]), sessions=[1])

    def test_duplicate_rank_refused(self):
        pred = ranked([(1, 'carts', 11, 1), (1, 'carts', 12, 1)])
        with self.assertRaisesRegex(oc.ContractError, 'repeated rank'):
            oc.metric(pred, labels([(1, 'carts', 11)]), sessions=[1])

    def test_more_than_twenty_refused(self):
        aids = list(range(100, 121))                                                # 21 predictions
        with self.assertRaisesRegex(oc.ContractError, 'outside 1..20'):
            oc.metric(ranked(ranked_list(1, 'carts', aids)), labels([(1, 'carts', 120)]), sessions=[1])
        exactly = oc.metric(ranked(ranked_list(1, 'carts', aids[:20])), labels([(1, 'carts', 119)]), sessions=[1])
        self.assertEqual(exactly['recall']['carts'], 1.0)

    def test_bad_rank_and_type_refused(self):
        gt = labels([(1, 'carts', 11)])
        for bad in ([(1, 'carts', 11, 0)], [(1, 'basket', 11, 1)], [(1, 'carts', None, 1)]):
            with self.subTest(bad=bad), self.assertRaises(oc.ContractError):
                oc.metric(ranked(bad), gt, sessions=[1])

    def test_label_rules(self):
        pred = ranked(ranked_list(1, 'clicks', [10]))
        with self.assertRaisesRegex(oc.ContractError, 'more than one clicks'):
            oc.metric(pred, labels([(1, 'clicks', 10), (1, 'clicks', 11)]), sessions=[1])
        with self.assertRaisesRegex(oc.ContractError, 'repeated'):
            oc.metric(pred, labels([(1, 'carts', 10), (1, 'carts', 10)]), sessions=[1])
        with self.assertRaisesRegex(oc.ContractError, 'Duplicate sessions'):
            oc.metric(pred, labels([(1, 'clicks', 10)]), sessions=[1, 1])

    def test_empty_type(self):
        pred = ranked(ranked_list(1, 'clicks', [10]) + ranked_list(1, 'orders', [10]))
        m = oc.metric(pred, labels([(1, 'clicks', 10), (2, 'carts', 5)]), sessions=[1, 2])
        self.assertEqual(m['den']['orders'].tolist(), [0, 0])                        # no session has orders
        self.assertEqual(m['hits']['orders'].tolist(), [0, 0])
        self.assertTrue(math.isnan(m['recall']['orders']))
        self.assertTrue(math.isnan(m['score']))
        self.assertEqual(m['recall']['clicks'], 1.0)
        self.assertEqual(m['den']['clicks'].tolist(), [1, 0])                        # session 2: not counted
        self.assertEqual(m['recall']['carts'], 0.0)

    def test_random_cross_check_with_evaluate_mirror(self):
        rng = np.random.default_rng(7)
        pred_rows, gt_rows = [], []
        for session in range(300):
            for type_ in oc.TYPES:
                if rng.random() < 0.8:
                    k = int(rng.integers(0, 21))
                    pred_rows += ranked_list(session, type_, rng.choice(60, k, replace=False).tolist())
                if rng.random() < 0.6:
                    n = 1 if type_ == 'clicks' else int(rng.integers(1, 30))
                    gt_rows += [(session, type_, int(a)) for a in rng.choice(60, n, replace=False)]
        sessions = list(range(310))                                                 # 300..309: neither rows nor labels
        m = oc.metric(ranked(pred_rows), labels(gt_rows), sessions=sessions)
        expected = evaluate_mirror(pred_rows, gt_rows, sessions)
        for type_ in oc.TYPES:
            self.assertEqual(m['recall'][type_], expected[type_], type_)
        self.assertAlmostEqual(m['score'], sum(oc.WEIGHTS[t]*expected[t] for t in oc.TYPES), places=15)

    def test_integer_type_codes_and_parquet_paths(self):
        pred, gt = self.example()
        coded = pred.assign(type=pred['type'].map(oc.TYPE_CODES).astype('int8'))
        self.assertEqual(oc.metric(coded, gt, sessions=EXAMPLE_SESSIONS)['recall'], oc.metric(pred, gt, sessions=EXAMPLE_SESSIONS)['recall'])
        category = pred.assign(type=pred['type'].astype('category'))
        self.assertEqual(oc.metric(category, gt, sessions=EXAMPLE_SESSIONS)['recall'], oc.metric(pred, gt, sessions=EXAMPLE_SESSIONS)['recall'])
        with tempfile.TemporaryDirectory() as tmp:
            oc.write_parquet(pred, Path(tmp)/'r.parquet')
            oc.write_parquet(gt, Path(tmp)/'l.parquet')
            from_files = oc.metric(Path(tmp)/'r.parquet', str(Path(tmp)/'l.parquet'), sessions=EXAMPLE_SESSIONS)
        self.assertEqual(from_files['score'], oc.metric(pred, gt, sessions=EXAMPLE_SESSIONS)['score'])
        with self.assertRaises(oc.ContractError):
            oc.metric(pred.assign(type=pred['type'].map(oc.TYPE_CODES)+5), gt, sessions=EXAMPLE_SESSIONS)


# ================================================================== bootstrap_ratio (§3)

def synthetic(n, seed, shift=0):
    """A metric-shaped result on sessions 0..n-1 with hits <= den."""
    rng = np.random.default_rng(seed)
    den = {t: rng.integers(0, 4 if t != 'clicks' else 2, n) for t in oc.TYPES}
    hits = {t: np.minimum(den[t], rng.integers(0, 3, n)+shift) for t in oc.TYPES}
    return dict(sessions=np.arange(n, dtype=np.int64), hits=hits, den=den)


def with_hits(result, hits):
    return dict(sessions=result['sessions'], den=result['den'], hits=hits)


class BootstrapRatio(unittest.TestCase):
    def test_same_indices_for_both_arms_and_all_types(self):
        ref = synthetic(200, 1)
        alt = with_hits(ref, synthetic(200, 2, shift=1)['hits'])
        alt['hits'] = {t: np.minimum(alt['hits'][t], ref['den'][t]) for t in oc.TYPES}
        got = oc.bootstrap_ratio(ref, alt, draws=300)
        # reference implementation: one idx per draw, gathered for both arms and three types
        rng = np.random.default_rng(2026)
        n, diffs, per_type = 200, [], {t: [] for t in oc.TYPES}
        for _ in range(300):
            idx = rng.integers(0, n, n)
            r_ref = {t: ref['hits'][t][idx].sum()/ref['den'][t][idx].sum() for t in oc.TYPES}
            r_alt = {t: alt['hits'][t][idx].sum()/ref['den'][t][idx].sum() for t in oc.TYPES}
            score = lambda r: 0.10*r['clicks'] + 0.30*r['carts'] + 0.60*r['orders']   # noqa: E731
            diffs.append(score(r_alt)-score(r_ref))
            for t in oc.TYPES:
                per_type[t].append(r_alt[t]-r_ref[t])
        expected = np.quantile(diffs, [0.025, 0.975], method='linear')
        np.testing.assert_allclose(got['ci'], expected, rtol=0, atol=1e-12)
        for t in oc.TYPES:
            np.testing.assert_allclose(got['types'][t]['ci'], np.quantile(per_type[t], [0.025, 0.975],
                                                                         method='linear'), rtol=0, atol=1e-12)
        self.assertEqual((got['sessions'], got['draws'], got['seed']), (200, 300, 2026))
        # a fresh default_rng(2026) per call: the same CI twice
        self.assertEqual(oc.bootstrap_ratio(ref, alt, draws=300), got)

    def test_known_differences(self):
        ref = synthetic(300, 3)
        same = oc.bootstrap_ratio(ref, ref, draws=200)
        self.assertEqual((same['diff'], same['ci'], same['covers_zero']), (0.0, [0.0, 0.0], True))
        zero = with_hits(ref, {t: np.zeros(300, dtype=np.int64) for t in oc.TYPES})
        perfect = with_hits(ref, ref['den'])
        full = oc.bootstrap_ratio(zero, perfect, draws=200)                  # R_t = 1 vs 0 on every resample
        self.assertAlmostEqual(full['diff'], 1.0, places=12)
        np.testing.assert_allclose(full['ci'], [1.0, 1.0], atol=1e-12)
        self.assertFalse(full['covers_zero'])
        even = {t: 2*ref['den'][t] for t in oc.TYPES}
        half = dict(sessions=ref['sessions'], den=even, hits=ref['den'])     # R_t = 1/2 on every resample
        result = oc.bootstrap_ratio(dict(zero, den=even), half, draws=200)
        np.testing.assert_allclose(result['ci'], [0.5, 0.5], atol=1e-12)
        self.assertAlmostEqual(result['types']['orders']['diff'], 0.5)
        reverse = oc.bootstrap_ratio(perfect, zero, draws=200)
        np.testing.assert_allclose(reverse['ci'], [-1.0, -1.0], atol=1e-12)

    def test_defaults_follow_contract(self):
        self.assertEqual((oc.BOOTSTRAP_DRAWS, oc.BOOTSTRAP_SEED, oc.CI_QUANTILES), (2000, 2026, (0.025, 0.975)))

    def test_on_metric_results_independent_of_input_order(self):
        rng = np.random.default_rng(7)
        gt, pred = [], []
        for s in range(400):
            gt.append((s, 'clicks', int(rng.integers(0, 30))))
            gt += [(s, t, int(a)) for t in ('carts', 'orders') for a in rng.choice(30, int(rng.integers(0, 3)), False)]
            for t in oc.TYPES:
                pred += ranked_list(s, t, [int(a) for a in rng.choice(30, 20, replace=False)])
        pred, gt = ranked(pred), labels(gt)
        a = oc.metric(pred, gt, sessions=range(400))
        population = a['sessions'][::-1].tolist()
        b = oc.metric(pred.sample(frac=1, random_state=4), gt.sample(frac=1, random_state=5), sessions=population)
        base = oc.metric(pred[pred['rank'] <= 5], gt, sessions=range(400))
        self.assertEqual(oc.bootstrap_ratio(base, a, draws=100), oc.bootstrap_ratio(base, b, draws=100))
        self.assertGreater(oc.bootstrap_ratio(base, a, draws=100)['ci'][0], 0)   # top-20 beats its own top-5

    def test_refuses_unpaired_arms(self):
        ref = synthetic(50, 6)
        other = dict(ref, sessions=ref['sessions']+1)
        with self.assertRaises(oc.ContractError):
            oc.bootstrap_ratio(ref, other, draws=10)
        moved = dict(ref, den={t: v+1 for t, v in ref['den'].items()})
        with self.assertRaises(oc.ContractError):
            oc.bootstrap_ratio(ref, moved, draws=10)
        no_orders = dict(ref, den=dict(ref['den'], orders=np.zeros(50, dtype=np.int64)),
                         hits=dict(ref['hits'], orders=np.zeros(50, dtype=np.int64)))
        with self.assertRaises(oc.ContractError):
            oc.bootstrap_ratio(no_orders, no_orders, draws=10)


# ================================================================== weeks and partitions (§2.1, §2.5)

class Partitions(unittest.TestCase):
    def test_floor_boundaries(self):
        self.assertEqual(oc.partition_day(S5-1, S5), -1)
        self.assertEqual(oc.partition_day(S5-86400, S5), -1)
        self.assertEqual(oc.partition_day(S5-86401, S5), -2)
        self.assertEqual(oc.partition_day(S5, S5, 'test'), 0)
        self.assertEqual(oc.partition_day(S5+86399, S5, 'test'), 0)
        self.assertEqual(oc.partition_day(S5+86400, S5, 'test'), 1)
        with self.assertRaises(oc.ContractError):
            oc.partition_day(S5-1, S5, 'test')

    def test_train_event_in_the_s5_second_goes_to_minus_one(self):
        # ts_ms train < ts_ms test can still share the second S5 after ts // 1000 (§1, decision 21)
        train_ms, test_ms = S5*1000+400, S5*1000+700
        self.assertLess(train_ms, test_ms)
        self.assertEqual(train_ms//1000, S5)
        self.assertEqual(oc.partition_day(train_ms//1000, S5, 'train'), -1)
        self.assertEqual(oc.week_of_day(oc.partition_day(train_ms//1000, S5)), 4)
        self.assertEqual(oc.partition_day(test_ms//1000, S5, 'test'), 0)

    def test_first_second_of_w4(self):
        start = oc.week_start(4, S5)
        self.assertEqual(start, S5-7*86400)
        self.assertEqual(oc.partition_day(start, S5), -7)
        self.assertEqual(oc.partition_day(start-1, S5), -8)
        self.assertFalse(oc.partition_open(oc.partition_day(start, S5), 'dev'))
        self.assertTrue(oc.partition_open(oc.partition_day(start-1, S5), 'dev'))

    def test_every_week_boundary_is_a_partition_boundary(self):
        for k in (1, 2, 3, 4, 5):
            start = oc.week_start(k, S5)
            source = 'test' if k == 5 else 'train'
            self.assertEqual(oc.partition_day(start, S5, source), oc.week_first_day(k))
            self.assertEqual(oc.week_of_day(oc.partition_day(start, S5, source)), k)
            if k > 1:
                self.assertEqual(oc.week_of_day(oc.partition_day(start-1, S5)), k-1)
                self.assertEqual(oc.week_end(k-1, S5), start)
        self.assertEqual(oc.week_of_day(oc.partition_day(oc.week_start(1, S5)-1, S5)), 1)   # d = -29 joins W1
        for d in range(-60, 15):
            k = oc.week_of_day(d)
            lo, hi = oc.week_days(k)
            self.assertTrue((lo is None or lo <= d) and (hi is None or d <= hi), (d, k))

    def test_train_days_are_negative(self):
        rng = np.random.default_rng(0)
        for ts in rng.integers(S5-40*86400, S5+1, 2000):
            d = oc.partition_day(int(ts), S5)
            self.assertLess(d, 0)
            self.assertIn(oc.week_of_day(d), (1, 2, 3, 4))
            if d <= -29:
                self.assertEqual(oc.week_of_day(d), 1)
        self.assertEqual([oc.week_days(k) for k in (1, 2, 3, 4, 5)],
                         [(None, -22), (-21, -15), (-14, -8), (-7, -1), (0, None)])

    def test_sql_twin(self):
        stamps = [S5-1, S5, S5-86400, S5-86401, oc.week_start(4, S5), oc.week_start(4, S5)-1,
                  oc.week_start(1, S5)-86400*3-5, S5-29*86400]
        con = duckdb.connect()
        try:
            for source in ('train', 'test'):
                values = [ts for ts in stamps if source == 'train' or ts >= S5]
                sql = oc.partition_sql('ts', S5, source)
                got = con.execute(f'SELECT ts, {sql} FROM (SELECT unnest(?::BIGINT[]) AS ts)', [values]).fetchall()
                for ts, d in got:
                    self.assertEqual(d, oc.partition_day(ts, S5, source), (source, ts))
        finally:
            con.close()


# ================================================================== barrier and receipts (§2.5)

class Barrier(TempRoot):
    def write_partitions(self):
        """Canaries in W4's first second, the second before it, W3, and the first second of W5."""
        events = {-8: [(1, 7, oc.week_start(4, S5)-1, 'clicks', 1)],
                  -9: [(2, 8, oc.week_start(4, S5)-86400-60, 'carts', 1)],
                  -7: [(3, 666, oc.week_start(4, S5), 'orders', 1)],
                  -1: [(4, 667, S5, 'clicks', 1)],                    # train event in the S5 second, d = -1
                  0: [(5, 668, S5, 'clicks', 1)]}
        for d, rows in events.items():
            path = oc.events_path(d)
            path.mkdir(parents=True)
            oc.write_parquet(frame(rows, oc.EVENT_COLUMNS), path/'part-0.parquet')

    def read(self, paths):
        globs = [str(p/'*.parquet') for p in paths]
        con = duckdb.connect()
        try:
            return {r[0] for r in con.execute('SELECT aid FROM read_parquet(?)', [globs]).fetchall()}
        finally:
            con.close()

    def test_events_path_layout(self):
        load = self.root/'artifacts'/'otto'/'load'
        self.assertEqual(oc.events_path(-1), load/'events'/'d=-1')
        self.assertEqual(oc.events_path(-29), load/'events'/'d=-29')
        self.assertEqual(oc.events_path(0), load/'test'/'d=0')
        self.assertEqual(oc.EVENT_COLUMNS, ('session', 'aid', 'ts', 'type', 'seq'))

    def test_canaries_before_and_after_receipts(self):
        self.write_partitions()
        self.assertEqual(oc.existing_days(), [-9, -8, -7, -1, 0])
        self.assertEqual(oc.existing_days('test'), [0])
        h4 = [d for d in oc.existing_days('train') if d < oc.week_first_day(4)]
        visible = self.read(oc.partition_paths(h4, 'dev'))
        self.assertEqual(visible, {7, 8})                          # start(W4) - 1 is visible, start(W4) is not
        for purpose in ('dev', 'probe', 'agent', 'collect-holdout', 'final'):
            for d in (-7, -1, 0):
                with self.subTest(purpose=purpose, d=d), self.assertRaises(oc.ContractError):
                    oc.partition_paths([d], purpose)
        self.commit_prereg()
        w4 = self.read(oc.partition_paths([-7, -1], 'collect-holdout'))
        self.assertEqual(w4, {666, 667})
        for purpose, d in (('collect-holdout', 0), ('dev', -7), ('final', -7), ('final', 0)):
            with self.subTest(purpose=purpose, d=d), self.assertRaises(oc.ContractError):
                oc.partition_paths([d], purpose)
        self.holdout_collection()
        self.assertFalse(oc.partition_open(-7, 'collect-holdout'))      # opened once
        self.write_config('holdout-open', OPEN)
        self.assertFalse(oc.partition_open(0, 'final'))
        self.write_config('holdout', dict(result=1))
        self.assertEqual(self.read(oc.partition_paths([-7, -1, 0], 'final')), {666, 667, 668})
        self.assertFalse(oc.partition_open(-7, 'dev'))

    def test_output_dir_refuses_partition_trees(self):
        self.assertEqual(oc.output_dir('load'), self.root/'artifacts'/'otto'/'load')
        oc.output_dir('load', 'stats')
        for parts in (('events',), ('test',), ('test', 'd=0'), ('events', 'd=-3', 'p.parquet'), ('stats', '..', 'events')):
            with self.subTest(parts=parts), self.assertRaises(oc.ContractError):
                oc.output_dir('load', *parts)

    def test_partition_glob(self):
        self.write_partitions()
        globs = oc.partition_glob([-9, -8], 'dev')
        self.assertEqual(globs, [str(oc.events_path(-9)/'*.parquet'), str(oc.events_path(-8)/'*.parquet')])
        con = duckdb.connect()
        try:
            aids = {r[0] for r in con.execute('SELECT aid FROM read_parquet(?)', [globs]).fetchall()}
        finally:
            con.close()
        self.assertEqual(aids, {7, 8})
        for d in (-7, -1, 0):
            with self.subTest(d=d), self.assertRaises(oc.ContractError):
                oc.partition_glob([-9, d], 'dev')
        self.commit_prereg()
        self.assertEqual(len(oc.partition_glob([-7, -1], 'collect-holdout')), 2)

    def test_window_rules(self):
        self.assertFalse(oc.holdout_window_open('collect-holdout'))
        prereg = self.commit_prereg()
        self.assertTrue(oc.holdout_window_open('collect-holdout'))
        self.assertFalse(oc.holdout_window_open('final'))
        with self.assertRaises(oc.ContractError):
            oc.holdout_window_open('sidecar')
        prereg.write_text(prereg.read_text()+' ')                         # dirty prereg
        self.assertFalse(oc.holdout_window_open('collect-holdout'))
        git(self.root, 'checkout', '--', str(prereg.relative_to(self.root)))
        self.assertTrue(oc.holdout_window_open('collect-holdout'))
        col = self.holdout_collection()                                   # an existing collection closes it
        self.assertFalse(oc.holdout_window_open('collect-holdout'))
        self.write_config('deviations', dict(format=oc.DEVIATIONS_FORMAT, records=[
            dict(id='d1', step='collect-holdout', supersedes=[col.name])]))
        self.assertTrue(oc.holdout_window_open('collect-holdout'))
        self.assertEqual(oc.current_holdout_collection().name, 'holdout-F4-d1')
        self.assertEqual(oc.collection_dir('holdout').name, 'holdout-F4-d1')
        self.write_config('holdout-open', OPEN)                           # an open receipt closes it for good
        self.assertFalse(oc.holdout_window_open('collect-holdout'))

    def test_window_sha_mismatch(self):
        self.write_config('base', dict(b=1))
        agent_set = self.write_config('set', dict(s=1, audit=dict(verdict='clean')))
        self.write_config('prereg', dict(base_sha256='0'*64, set_sha256=oc.sha256_file(agent_set)))
        self.assertFalse(oc.holdout_window_open('collect-holdout'))

    def test_read_sealed_needs_receipts(self):
        self.commit_prereg()
        col = self.holdout_collection()
        self.assertEqual(oct((col/oc._SEALED/oc.LABELS_FILE).stat().st_mode & 0o777), '0o400')
        self.assertEqual(sorted(p.name for p in col.iterdir()), ['frame.parquet', 'manifest.json', 'prefix', 'sealed'])
        for purpose in ('holdout', 'holdout-2', 'final'):
            with self.subTest(purpose=purpose), self.assertRaises(oc.ContractError):
                oc.read_sealed(col, purpose)
        with self.assertRaises(oc.ContractError):
            oc.read_sealed(col, 'dev')
        self.write_config('holdout-open', OPEN, commit=False)             # uncommitted receipt
        with self.assertRaises(oc.ContractError):
            oc.read_sealed(col, 'holdout')
        self.commit(oc.config_path('holdout-open'))
        labels_path = oc.read_sealed(col, 'holdout')['labels']
        self.assertEqual(oc.read_parquet(labels_path)['aid'].tolist(), [11])
        with self.assertRaises(oc.ContractError):
            oc.read_sealed(col, 'final')
        self.write_config('holdout-open-2', OPEN2)                        # stage 2 also needs the stage-1 result
        with self.assertRaises(oc.ContractError):
            oc.read_sealed(col, 'holdout-2')
        self.write_config('holdout', dict(x=1))
        oc.read_sealed(col, 'holdout-2')
        oc.read_sealed(col, 'final')

    def test_stage2_without_its_open_receipt(self):
        col = self.holdout_collection()
        self.write_config('holdout-open', OPEN)
        self.write_config('holdout', dict(x=1))
        with self.assertRaises(oc.ContractError):
            oc.read_sealed(col, 'holdout-2')

    def test_holdout_manifest_carries_no_labels(self):
        base = oc.make_base({}, [])
        col = oc.new_output(oc.output_dir('collections', 'holdout-F4'))
        (col/oc.PREFIX_DIR/'d=-3').mkdir(parents=True)
        oc.write_parquet(frame([(1, 10, S5, 'clicks', 1)], oc.EVENT_COLUMNS), col/oc.PREFIX_DIR/'d=-3'/'p.parquet')
        oc.write_parquet(frame([(1, 10)], oc.FRAME_KEYS), col/oc.FRAME_FILE)
        sealed = oc.write_sealed(col, lambda d: oc.write_parquet(labels([(1, 'carts', 11)]), d/oc.LABELS_FILE))
        write = lambda **kw: oc.write_manifest(col, 'holdout', kw.pop('counts', dict(sessions=1)), base, {},
                                               sealed=kw.pop('sealed', sealed), **kw)
        for counts in (dict(positives=3), dict(n_labels=2), dict(by_type=dict(suffix_events=1)),
                       dict(sessions=1, Recall=0.5), [dict(hits=1)]):
            with self.subTest(counts=counts), self.assertRaises(oc.ContractError):
                write(counts=counts)
        for extra in (dict(stats=dict(positives=3)), dict(targets=1), dict(gate=[dict(recall_carts=0.1)])):
            with self.subTest(extra=extra), self.assertRaisesRegex(oc.ContractError, 'may not carry'):
                write(extra=extra)
        for bad in (None, {}, {oc.LABELS_FILE: '0'*64}, {oc.LABELS_FILE: sealed[oc.LABELS_FILE], 'x': '0'*64}):
            with self.subTest(sealed=bad), self.assertRaises(oc.ContractError):
                write(sealed=bad)
        for name in (oc.LABELS_FILE, 'notes.txt', 'prefix.parquet', 'cache/f.parquet'):
            with self.subTest(outside=name):
                stray = col/name
                stray.parent.mkdir(exist_ok=True)
                stray.write_text('x')
                with self.assertRaisesRegex(oc.ContractError, 'may hold only'):
                    write()
                stray.unlink()
        self.assertEqual(oc.HOLDOUT_FILES, ('frame.parquet', 'prefix/'))
        manifest = write(extra=dict(rule='all of Q_4'))
        self.assertEqual(manifest['sealed'], sealed)
        self.assertEqual(sorted(manifest['files']), ['frame.parquet', 'prefix/d=-3/p.parquet'])

    def test_holdout_manifest_refuses_extra_sealed_file(self):
        col = oc.new_output(oc.output_dir('collections', 'holdout-F4'))
        (col/oc.PREFIX_DIR).mkdir()
        oc.write_parquet(frame([(1, 10, S5, 'clicks', 1)], oc.EVENT_COLUMNS), col/oc.PREFIX_DIR/'p.parquet')
        oc.write_parquet(frame([(1, 10)], oc.FRAME_KEYS), col/oc.FRAME_FILE)
        def writer(d):
            oc.write_parquet(labels([(1, 'carts', 11)]), d/oc.LABELS_FILE)
            (d/'counts.json').write_text('{}')
        with self.assertRaises(oc.ContractError):
            oc.write_sealed(col, writer)

    def test_tampered_sealed_file_detected(self):
        col = self.holdout_collection()
        self.write_config('holdout-open', OPEN)
        path = oc.read_sealed(col, 'holdout')['labels']
        (col/oc._SEALED).chmod(0o700)
        path.chmod(0o600)
        oc.write_parquet(labels([(1, 'carts', 12)]), path)
        with self.assertRaisesRegex(oc.ContractError, 'Sealed file changed'):
            oc.read_sealed(col, 'holdout')
        path.unlink()
        with self.assertRaises((oc.ContractError, OSError)):
            oc.read_sealed(col, 'holdout')

    def test_receipt_schemas(self):
        bad_open = [dict(OPEN, format='otto-holdout-open-v0'), dict(OPEN, quote=''), dict(OPEN, quote='  '),
                    {k: v for k, v in OPEN.items() if k != 'quote'}, dict(OPEN, gate1={}),
                    dict(OPEN, gate1=dict(ok='yes')), {k: v for k, v in OPEN.items() if k != 'gate1'}]
        for data in bad_open:
            with self.subTest(data=data), self.assertRaises(oc.ContractError):
                oc.check_receipt('holdout-open', data)
        bad_open2 = [dict(OPEN2, format=oc.HOLDOUT_OPEN_FORMAT), dict(OPEN2, scores={}), dict(OPEN2, scores=None),
                     dict(OPEN2, scores={'a': 'abc'}), dict(OPEN2, scores={'a': 'A'*64}),
                     {k: v for k, v in OPEN2.items() if k != 'scores'}]
        for data in bad_open2:
            with self.subTest(data=data), self.assertRaises(oc.ContractError):
                oc.check_receipt('holdout-open-2', data)
        self.assertEqual(oc.check_receipt('holdout-open', dict(OPEN, gate1=dict(ok=False))), dict(OPEN, gate1=dict(ok=False)))
        oc.check_receipt('holdout-open-2', OPEN2)
        col = self.holdout_collection()
        self.write_config('holdout-open', dict(OPEN, quote=''))              # committed but malformed: refusal
        with self.assertRaisesRegex(oc.ContractError, 'empty owner quote'):
            oc.holdout_window_open('holdout')
        with self.assertRaises(oc.ContractError):
            oc.read_sealed(col, 'holdout')

    def test_committed_clean(self):
        path = self.root/'configs'/'datasets'/'f.json'
        self.assertFalse(oc.committed_clean(path))                            # missing
        path.write_text('{}')
        self.assertFalse(oc.committed_clean(path))                            # untracked
        git(self.root, 'add', str(path.relative_to(self.root)))
        self.assertFalse(oc.committed_clean(path))                            # staged, not in HEAD
        git(self.root, 'commit', '-q', '-m', 'f')
        self.assertTrue(oc.committed_clean(path))
        path.write_text('{"a": 1}')
        self.assertFalse(oc.committed_clean(path))                            # modified
        git(self.root, 'add', str(path.relative_to(self.root)))
        self.assertFalse(oc.committed_clean(path))                            # staged change, HEAD differs
        git(self.root, 'commit', '-q', '-m', 'f2')
        self.assertTrue(oc.committed_clean(path))

    def test_committed_clean_ignores_index_flags(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                path = self.root/'configs'/'datasets'/f'flag{flag}.json'
                path.write_text('{}')
                self.commit(path)
                rel = str(path.relative_to(self.root))
                git(self.root, 'update-index', flag, rel)
                self.assertTrue(oc.committed_clean(path))
                path.write_text('{"a": 1}')                                    # git status/diff stay silent
                status = subprocess.run(['git', '-C', str(self.root), 'status', '--porcelain', '--', rel],
                                        capture_output=True, text=True, check=True)
                self.assertEqual(status.stdout, '')
                self.assertFalse(oc.committed_clean(path))
                path.write_text('{}')
                self.assertTrue(oc.committed_clean(path))

    def test_uncommitted_deviations_refused(self):
        self.commit_prereg()
        path = self.write_config('deviations', dict(format=oc.DEVIATIONS_FORMAT, records=[
            dict(id='d1', step='collect-holdout', supersedes=[])]), commit=False)
        identity = dict(files={'scripts/otto_common.py': 'x'}, missing=[])
        with mock.patch.object(oc, 'code_identity', return_value=identity):
            with self.assertRaisesRegex(oc.ContractError, 'not committed clean'):
                oc.require_prereg()
        with self.assertRaisesRegex(oc.ContractError, 'not committed clean'):
            oc.current_holdout_collection()
        with self.assertRaises(oc.ContractError):
            oc.collection_dir('holdout')
        self.commit(path)
        self.assertEqual(oc.current_holdout_collection().name, 'holdout-F4-d1')
        path.write_text(path.read_text()+' ')                                  # committed, then edited
        with self.assertRaises(oc.ContractError):
            oc.current_holdout_collection()
        with mock.patch.object(oc, 'code_identity', return_value=identity), self.assertRaises(oc.ContractError):
            oc.require_prereg()

    def test_bare_holdout_directory_closes_window(self):
        self.commit_prereg()
        self.assertTrue(oc.holdout_window_open('collect-holdout'))
        for name in ('holdout-F4', 'holdout-F4-tmp'):
            with self.subTest(name=name):
                bare = oc.output_dir('collections', name)
                bare.mkdir(parents=True)                                       # no manifest, nothing inside
                self.assertFalse(oc.holdout_window_open('collect-holdout'))
                self.assertFalse(oc.partition_open(-1, 'collect-holdout'))
                bare.rmdir()
        oc.output_dir('collections', 'val-F3').mkdir(parents=True)             # other roles do not count
        self.assertTrue(oc.holdout_window_open('collect-holdout'))

    def test_supersedes_by_name(self):
        self.commit_prereg()
        col = self.holdout_collection()
        posix = col.relative_to(self.root).as_posix()
        for supersedes in ([posix], [str(col)], ['holdout-F4-d0'], []):
            with self.subTest(supersedes=supersedes):
                self.write_config('deviations', dict(format=oc.DEVIATIONS_FORMAT, records=[
                    dict(id='d1', step='collect-holdout', supersedes=supersedes)]))
                self.assertFalse(oc.holdout_window_open('collect-holdout'))
        self.write_config('deviations', dict(format=oc.DEVIATIONS_FORMAT, records=[
            dict(id='d1', step='collect-holdout', supersedes=['holdout-F4'])]))
        self.assertTrue(oc.holdout_window_open('collect-holdout'))
        oc.output_dir('collections', 'holdout-F4-d1').mkdir()                  # the rebuild started: closed again
        self.assertFalse(oc.holdout_window_open('collect-holdout'))

    def test_collection_roundtrip(self):
        base = oc.make_base(dict(history=50), [dict(name='s_len', formula='events in prefix', missing='-')])
        col = oc.new_output(oc.collection_dir('val'))
        self.assertEqual(col.name, 'val-F3')
        (col/oc.PREFIX_DIR/'d=-10').mkdir(parents=True)
        oc.write_parquet(frame([(1, 10, S5-10*86400, 'clicks', 1)], oc.EVENT_COLUMNS),
                         col/oc.PREFIX_DIR/'d=-10'/'p.parquet')
        oc.write_parquet(frame([(1, 10)], oc.FRAME_KEYS), col/oc.FRAME_FILE)
        with self.assertRaises(oc.ContractError):                         # val needs labels
            oc.write_manifest(col, 'val', dict(sessions=1), base, {})
        oc.write_parquet(labels([(1, 'carts', 10)]), col/oc.LABELS_FILE)
        manifest = oc.write_manifest(col, 'val', dict(sessions=1), base, {'scripts/otto_common.py': 'x'})
        self.assertEqual(manifest['fold'], 3)
        self.assertIn('prefix/d=-10/p.parquet', manifest['files'])
        self.assertEqual(oc.read_collection(col, role='val', base=base)['files'], manifest['files'])
        with self.assertRaises(oc.ContractError):
            oc.read_collection(col, role='train')
        with self.assertRaises(oc.ContractError):
            oc.read_collection(col, base=oc.make_base(dict(history=40), []))
        oc.write_parquet(frame([(1, 11)], oc.FRAME_KEYS), col/oc.FRAME_FILE)
        with self.assertRaises(oc.ContractError):
            oc.read_collection(col)
        with self.assertRaises(oc.ContractError):
            oc.collection_name('val', 4)
        self.assertEqual([oc.collection_name(r) for r in oc.ROLES],
                         ['train-F2', 'val-F3', 'probe-F3', 'holdout-F4', 'kaggle-F5'])

    def test_population(self):
        col = self.holdout_collection()
        with self.assertRaises(oc.ContractError):
            oc.write_population(col, [3, 1, 3], dict(rule='all'))
        oc.write_population(col, [3, 1, 2], dict(rule='all of Q_4'))
        self.assertEqual(oc.read_population(col), [1, 2, 3])
        digest = oc.read_json(col/oc.POPULATION_FILE)['digest']
        self.assertEqual(oc.read_population(col, expected_digest=digest), [1, 2, 3])
        with self.assertRaisesRegex(oc.ContractError, 'not the expected'):
            oc.read_population(col, expected_digest='0'*64)
        oc.read_collection(col, role='holdout')                           # population.json is outside the manifest
        with self.assertRaises(oc.ContractError):
            oc.write_population(col, [1], dict(rule='again'))

    def test_outputs(self):
        path = oc.output_dir('fits', 'B2026')
        oc.new_output(path)
        with self.assertRaises(FileExistsError):
            oc.new_output(path)
        with self.assertRaises(oc.ContractError):
            oc.new_output(self.root/'artifacts'/'xfer'/'x')
        with self.assertRaises(oc.ContractError):
            oc.output_dir('nowhere')
        self.assertEqual(oc.config_path('holdout-open-2').name, 'otto-holdout-open-2.json')
        self.assertEqual(oc.verify_path(), self.root/'data'/'raw-otto-kaggle'/'otto-verify.json')

    def test_require_prereg(self):
        with self.assertRaises(oc.ContractError):
            oc.require_prereg(check_code=False)
        self.commit_prereg()
        self.assertIn('code', oc.require_prereg(check_code=False))
        with mock.patch.object(oc, 'code_identity', return_value=dict(files={'scripts/otto_common.py': 'x'}, missing=[])):
            oc.require_prereg()
        with mock.patch.object(oc, 'code_identity', return_value=dict(files={'scripts/otto_common.py': 'y'}, missing=[])):
            with self.assertRaises(oc.ContractError):
                oc.require_prereg()
            self.write_config('deviations', dict(format=oc.DEVIATIONS_FORMAT, records=[
                dict(id='d1', step='fit', code={'scripts/otto_common.py': 'y'})]))
            oc.require_prereg()
        base = oc.config_path('base')
        base.write_text('{"b": 2}')
        self.commit(base)
        with self.assertRaises(oc.ContractError):
            oc.require_prereg(check_code=False)


# ================================================================== base, orders, identity

class SqlAndResources(unittest.TestCase):
    def test_sql_text_helpers(self):
        self.assertEqual(oc.sql_literal("a'b"), "'a''b'")
        self.assertEqual(oc.sql_list([Path('x'), "y'"]), "['x', " + "'y''']")
        with self.assertRaisesRegex(oc.ContractError, 'No files'):
            oc.sql_list([])

    def test_agent_float_keeps_finite_float32_values_only(self):
        con = duckdb.connect()
        values = ['1.5', "'inf'::DOUBLE", "'-inf'::DOUBLE", "'nan'::DOUBLE", '1e39', '-1e39', 'NULL',
                  '3.4028234663852886e38', 'true', '3']
        rows = [con.execute(f'SELECT {oc.agent_float_sql(v)}, typeof({oc.agent_float_sql(v)})').fetchone()
                for v in values]
        con.close()
        self.assertEqual({t for _, t in rows}, {'FLOAT'})
        self.assertEqual([None if v is None else float(v) for v, _ in rows],
                         [1.5, None, None, None, None, None, None, float(np.float32(oc.FLOAT32_MAX)), 1.0, 3.0])

    def test_history_days_and_shared_constants(self):
        self.assertEqual([oc.history_days(k) for k in (2, 3, 4, 5)], [7, 14, 21, 28])
        for k in (1, 6):
            with self.assertRaises(oc.ContractError):
                oc.history_days(k)
        self.assertEqual((oc.DUCKDB_MEMORY, oc.DUCKDB_MAX_TEMP, oc.DUCKDB_THREADS), ('20GB', '40GB', 8))
        self.assertEqual((oc.AGENT_PREFIX, oc.SOURCE_PREFIX, oc.NEUTRAL_EVENTS),
                         ('ag_', 'ag_src_', ('view', 'cart', 'order')))
        self.assertEqual(oc.RECIPE['loss_function'], 'YetiRank')
        self.assertEqual(oc.FLOAT32_MAX, float(np.finfo(np.float32).max))

    def test_spill_dir_is_fresh_and_under_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(oc, 'ROOT', Path(tmp).resolve()):
            a, b = oc.spill_dir(), oc.spill_dir()
            self.assertNotEqual(a, b)
            self.assertEqual(a.parent, oc.artifacts_dir()/oc.SPILL_DIR)
            self.assertTrue(a.parent.is_dir() and not a.exists())


AGENT_SET = dict(format=oc.SET_FORMAT, digest='5'*64, columns=['ag_src_x_rank', 'ag_src_x_score', 'ag_a'],
                 proposals=[dict(kind='table', columns=['v']),
                            dict(kind='source', columns=['ag_src_x_rank', 'ag_src_x_score']),
                            dict(kind='feature', columns=['ag_a'])])


class AgentFormats(TempRoot):
    def test_agent_columns(self):
        self.assertEqual(oc.agent_columns(AGENT_SET), AGENT_SET['columns'])
        self.assertEqual(oc.agent_columns({k: v for k, v in AGENT_SET.items() if k != 'proposals'}),
                         AGENT_SET['columns'])
        cases = [(dict(format='x'), oc.SET_FORMAT), (dict(digest=None), 'digest'), (dict(columns=[]), 'no columns'),
                 (dict(columns=['x_a'], proposals=None), 'ag_'),
                 (dict(columns=['ag_a', 'ag_a'], proposals=None), 'Repeated'),
                 (dict(columns=['ag_src_x_rank'], proposals=None), 'both'),
                 (dict(columns=['ag_src_x_rank', 'ag_src_y_score'], proposals=None), 'both'),
                 (dict(columns=['ag_a', 'ag_src_x_rank', 'ag_src_x_score']), 'proposals'),
                 (dict(format=None, digest=None, columns=None, proposals=None, agent_columns=['ag_a']),
                  oc.SET_FORMAT)]                                       # the pre-integration ad-hoc set
        for change, pattern in cases:
            with self.subTest(pattern=pattern):
                record = {k: v for k, v in dict(AGENT_SET, **change).items() if v is not None}
                with self.assertRaisesRegex(oc.ContractError, pattern):
                    oc.agent_columns(record)

    def leak(self, **changes):
        body = dict(format=oc.LEAKCHECK_FORMAT, ok=True, fold=3, collection='val-F3', sessions=3,
                    sessions_digest=oc.sessions_digest([3, 1, 2]), set_digest='5'*64, error=None,
                    history_check=dict(sessions=3, keys_one_side=0, cells={}),
                    batch_check=dict(sessions=3, batches=2, keys_one_side=0, cells=0),
                    prefix_check=dict(rows=['5', '5'], sessions=['3', '3'], ok=True))
        body.update(changes)
        path = oc.leakcheck_path('F3')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        oc.atomic_json(path, body)
        return path

    def test_read_leakcheck(self):
        self.assertEqual(oc.leakcheck_path('F3'), self.root/'artifacts'/'otto'/'leakcheck'/'F3'/'report.json')
        self.assertEqual(oc.sessions_digest([3, 1, 2]), oc.canonical_digest([1, 2, 3]))
        good = dict(set_digest='5'*64, population_digest=oc.sessions_digest([1, 2, 3]))
        self.assertTrue(oc.read_leakcheck(self.leak(), **good, collection='val-F3')['ok'])
        cases = [(dict(format='x'), oc.LEAKCHECK_FORMAT), (dict(error='Timeout after 60 s'), 'Timeout'),
                 (dict(ok=False), 'ok is not true'), (dict(fold=5), 'fold'),
                 (dict(history_check=dict(keys_one_side=1, cells=0)), 'history_check'),
                 (dict(batch_check=dict(keys_one_side=0, cells=4)), 'batch_check'),
                 (dict(batch_check=None), 'batch_check'),
                 (dict(history_check=dict(keys_one_side=0)), 'history_check'),             # cells absent
                 (dict(history_check=dict(keys_one_side=0, cells=None)), 'history_check'),
                 (dict(batch_check=dict(keys_one_side=0, cells={'ag_good': 2})), 'batch_check'),
                 (dict(batch_check=dict(keys_one_side=False, cells=0)), 'batch_check'),
                 (dict(prefix_check=None), 'prefix_check'),
                 (dict(prefix_check=dict(ok=False)), 'prefix_check'),
                 (dict(prefix_check=dict(ok='true')), 'prefix_check'),
                 (dict(fold=4), 'prefix_check'),
                 (dict(set_digest='6'*64), 'another agent set'),
                 (dict(sessions_digest=oc.sessions_digest([1, 2])), 'another population')]
        for change, pattern in cases:
            with self.subTest(pattern=pattern), self.assertRaisesRegex(oc.ContractError, pattern):
                oc.read_leakcheck(self.leak(**change), **good)
        with self.assertRaisesRegex(oc.ContractError, 'another collection'):
            oc.read_leakcheck(self.leak(), **good, collection='holdout-F4')
        self.assertEqual(oc.read_leakcheck(self.leak(fold=4, prefix_check=None), **good)['fold'], 4)

    def power_gate(self, name, collection, digest):
        directory = oc.output_dir('gate', f'{oc.POWER_GATE_PREFIX}{name}')
        directory.mkdir(parents=True)
        oc.atomic_json(directory/oc.GATE_FILE, dict(format=oc.GATE_FORMAT, kind='power', ok=True,
                                                    population=dict(collection=collection, n=3, digest=digest)))
        return directory

    def test_holdout_population_is_checked_against_the_power_gate(self):
        col = self.holdout_collection()
        with self.assertRaisesRegex(oc.ContractError, 'found 0'):
            oc.holdout_population(col)
        oc.write_population(col, [3, 1, 2], 'all of Q_4')
        digest = oc.read_json(col/oc.POPULATION_FILE)['digest']
        self.power_gate('0-old', 'holdout-F4-old', '0'*64)                     # a superseded collection's gate
        gate = self.power_gate('1', col.name, digest)
        out = oc.holdout_population()
        self.assertEqual((out['sessions'], out['n'], out['digest']), ([1, 2, 3], 3, digest))
        self.assertEqual(out['sessions_digest'], oc.sessions_digest([1, 2, 3]))
        self.assertEqual(out['record']['collection'], col.name)
        self.assertEqual(out['gate'], str(gate/oc.GATE_FILE))
        (gate/oc.GATE_FILE).unlink()
        oc.atomic_json(gate/oc.GATE_FILE, dict(format=oc.GATE_FORMAT, kind='power',
                                               population=dict(collection=col.name, digest='1'*64)))
        with self.assertRaisesRegex(oc.ContractError, 'not the expected'):
            oc.holdout_population(col)
        self.power_gate('2', col.name, digest)
        with self.assertRaisesRegex(oc.ContractError, 'found 2'):
            oc.holdout_population(col)

    def test_output_names_are_one_path_component(self):
        for good in ('it0', 'F3', 'leakcheck-F4-20261023T1200Z', 'a.b_c-1'):
            self.assertEqual(oc.output_name(good), good)
        for bad in ('../x', 'a/b', '/tmp/x', '..', '.', '.hidden', '', None, 'a\\b'):
            with self.subTest(name=bad), self.assertRaisesRegex(oc.ContractError, 'Output names'):
                oc.output_name(bad)
        for make in (lambda n: oc.sidecar_dir('val-F3', n), lambda n: oc.sidecar_dir(n, 'run'),
                     oc.leakcheck_path, oc.final_training_dir):
            with self.assertRaisesRegex(oc.ContractError, 'Output names'):
                make('../x')

    def test_final_training_format(self):
        per_type = dict(clicks=[5, 2], carts=[2], orders=[])
        directory = oc.new_output(oc.final_training_dir('a'))
        record = oc.write_final_training(directory, 'holdout-F4', 2, 'a'*64, per_type)
        self.assertEqual(sorted(record), sorted(['format', 'collection', 'N_t', 'prereg_sha256', 'per_type',
                                                 'training_digest', 'sessions', 'digest']))
        self.assertEqual((record['format'], record['sessions'], record['training_digest']),
                         (oc.FINAL_TRAINING_FORMAT, [2, 5], oc.canonical_digest(per_type)))
        path = directory/oc.FINAL_TRAINING_FILE
        with self.assertRaisesRegex(oc.ContractError, 'closed'):              # F4 labels: only after the result
            oc.read_final_training(path)
        self.write_config('holdout', dict(stage=1))
        self.assertEqual(oc.read_final_training(path, collection='holdout-F4', prereg_sha256='a'*64, n_t=2), record)
        for kw, pattern in ((dict(collection='holdout-F4-x'), 'another collection'),
                            (dict(prereg_sha256='b'*64), 'another prereg'), (dict(n_t=3), 'another N_t')):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(oc.ContractError, pattern):
                oc.read_final_training(path, **kw)
        self.assertEqual(oc.final_training_record('holdout-F4', n_t=2)[0], path)
        with self.assertRaisesRegex(oc.ContractError, 'found 0'):
            oc.final_training_record('holdout-F4-x')
        path.unlink()
        oc.atomic_json(path, dict(record, sessions=[2]))
        with self.assertRaisesRegex(oc.ContractError, 'digest mismatch'):
            oc.read_final_training(path)
        with self.assertRaisesRegex(oc.ContractError, 'at most N_t'):
            oc.write_final_training(oc.new_output(oc.final_training_dir('b')), 'holdout-F4', 1, 'a'*64, per_type)
        with self.assertRaises(KeyError):
            oc.write_final_training(oc.new_output(oc.final_training_dir('c')), 'holdout-F4', 2, 'a'*64,
                                    dict(clicks=[1]))


class BaseFormat(unittest.TestCase):
    def test_digest_and_rules(self):
        features = [dict(name='s_len', formula='events in prefix', missing='-')]
        base = oc.make_base(dict(history=50, popular=20), features)
        self.assertEqual(oc.check_base(base)['format'], 'otto-base-v1')
        self.assertEqual(oc.base_feature_names(base), ['s_len'])
        base['features'][0]['formula'] = 'other'
        with self.assertRaises(oc.ContractError):
            oc.check_base(base)
        with self.assertRaises(oc.ContractError):
            oc.make_base({}, features, categorical=['s_len'])
        with self.assertRaises(oc.ContractError):
            oc.make_base({}, [dict(name='ag_x', formula='-', missing='-')])
        with self.assertRaises(oc.ContractError):
            oc.make_base({}, features+features)


class Orders(unittest.TestCase):
    def test_orders_match_duckdb(self):
        sessions = [0, 1, 7, 12_899_778, 14_571_581, 2**40]
        con = duckdb.connect()
        try:
            sql = (f'SELECT s, {oc.ORDER_SQL.format(column="s")}, {oc.PROBE_ORDER_SQL.format(column="s")} '
                   f'FROM (SELECT unnest(?::BIGINT[]) AS s)')
            for s, order, probe in con.execute(sql, [sessions]).fetchall():
                self.assertEqual(order, oc.order_key(s))
                self.assertEqual(probe, oc.probe_key(s))
        finally:
            con.close()
        self.assertNotEqual(oc.order_key(5), oc.probe_key(5))

    def test_first_in_order(self):
        sessions = list(range(100))
        first = oc.first_in_order(sessions, 10)
        self.assertEqual(first, sorted(sessions, key=lambda s: (oc.order_key(s), s))[:10])
        self.assertEqual(len(oc.first_in_order(sessions[:5], 10)), 5)
        self.assertNotEqual(oc.first_in_order(sessions, 10, key=oc.probe_key), first)


class CodeIdentity(unittest.TestCase):
    def tree(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        scripts = Path(tmp.name)/'scripts'
        for rel, text in files.items():
            path = scripts/rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return scripts

    def test_static_closure_on_a_synthetic_tree(self):
        scripts = self.tree({
            'otto_common.py': 'from scripts.xfer_common import read_json\nfrom . import helpers\n',
            'otto_data.py': 'from .sub.inner import f\nfrom scripts import otto_common\n',
            'otto_agent.py': 'import importlib\ndef late():\n    return importlib.import_module("scripts.dyn")\n',
            'xfer_common.py': 'import json\n',
            'helpers.py': 'import scripts.deep.leaf\n',
            'sub/__init__.py': '',
            'sub/inner.py': 'from ..leaf import y\n',
            'leaf.py': 'y = 1\n',
            'dyn.py': '__import__("scripts.via_dunder")\n',
            'via_dunder.py': '',
            'deep/__init__.py': '',
            'deep/leaf.py': '',
            'unrelated.py': 'import scripts.otto_common\n',
        })
        with mock.patch.object(oc, '_SCRIPTS', scripts):
            code = oc.code_identity()
            self.assertEqual(sorted(code['files']), sorted(f'scripts/{p}' for p in (
                'otto_common.py', 'otto_data.py', 'otto_agent.py', 'xfer_common.py', 'helpers.py', 'sub/__init__.py',
                'sub/inner.py', 'leaf.py', 'dyn.py', 'via_dunder.py', 'deep/__init__.py', 'deep/leaf.py')))
            self.assertEqual(code['missing'], ['scripts.otto_model'])
            self.assertEqual(code['files']['scripts/leaf.py'], oc.sha256_file(scripts/'leaf.py'))
            with self.assertRaisesRegex(oc.ContractError, 'otto_model'):
                oc.code_identity(strict=True)
            (scripts/'otto_model.py').write_text('')
            strict = oc.code_identity(strict=True)
            self.assertEqual(strict['missing'], [])
            self.assertIn('scripts/otto_model.py', strict['files'])
            (scripts/'leaf.py').write_text('y = 2\n')                          # a changed dependency changes the hash
            self.assertNotEqual(oc.code_identity()['files']['scripts/leaf.py'], strict['files']['scripts/leaf.py'])

    def test_real_tree_ignores_what_the_process_imported(self):
        before = oc.code_identity()
        self.assertEqual(before['files']['scripts/otto_common.py'], oc.sha256_file(oc.__file__))
        self.assertIn('scripts/xfer_common.py', before['files'])                # imported by otto_common
        self.assertTrue(all(k.startswith('scripts/') and k.endswith('.py') for k in before['files']))
        importlib.import_module('scripts.hm_download')
        self.assertIn('scripts.hm_download', sys.modules)
        after = oc.code_identity()
        self.assertEqual(after, before)
        self.assertNotIn('scripts/hm_download.py', after['files'])
        expected_missing = [m for m in oc.CODE_MODULES if not (REPO/(m.replace('.', '/')+'.py')).is_file()]
        self.assertEqual(after['missing'], sorted(expected_missing))
        self.assertEqual(oc.CODE_MODULES,
                         ('scripts.otto_common', 'scripts.otto_data', 'scripts.otto_agent', 'scripts.otto_model'))


# ================================================================== reading (§10)

class Reading(unittest.TestCase):
    def test_verdicts_two_seeds(self):
        two = lambda a, b: {2026: a, 2027: b}
        self.assertEqual(oc.verdict_transfer(two([0.01, 0.02], [0.001, 0.03]), 2), oc.VERDICT_TRANSFER[0])
        self.assertTrue(oc.VERDICT_TRANSFER[0].endswith('повышает качество базы на OTTO'))
        self.assertEqual(oc.verdict_transfer(two([-0.02, -0.01], [-0.3, -0.001]), 2), 'вредит')
        self.assertEqual(oc.verdict_transfer(two([-0.01, 0.01], [0.0, 0.02]), 2), 'не различено')
        self.assertEqual(oc.verdict_transfer(two([0.01, 0.02], [-0.01, 0.02]), 2), 'не решено')
        self.assertEqual(oc.verdict_content(two([0.01, 0.02], [0.01, 0.03]), 2),
                         'прирост колонок агента несёт их содержание')
        self.assertEqual(oc.verdict_content(two([-0.01, -0.001], [-0.02, -0.01]), 2), 'плацебо лучше')
        self.assertEqual(oc.verdict_content(two([-0.01, 0.01], [-0.01, 0.01]), 2), 'не отличимо от плацебо')
        self.assertEqual(oc.verdict_transfer({'2026': [0.01, 0.02], '2027': [0.01, 0.02]}, 2),   # JSON keys
                         oc.VERDICT_TRANSFER[0])

    def test_stage1_and_not_computed(self):
        self.assertEqual(oc.STAGE_SEEDS, {1: (2026,), 2: (2026, 2027)})
        self.assertEqual(oc.verdict_transfer({2026: [0.01, 0.02]}, 1), 'не решено (одно зерно)')
        self.assertEqual(oc.verdict_content({2026: [-0.02, -0.01]}, 1), 'не решено (одно зерно)')
        for stage in (1, 2):
            self.assertEqual(oc.verdict_transfer(None, stage), 'не вычислен')
            self.assertEqual(oc.verdict_content(None, stage), oc.NOT_COMPUTED)
        self.assertEqual(oc.stage1_note([0.001, 0.02]),
                         'на зерне 2026 CI(D) выше нуля; вердикт по правилу — после этапа 2')
        self.assertIsNone(oc.stage1_note([0.0, 0.02]))

    def test_verdict_refusals(self):
        nan = float('nan')
        bad = [({2027: [0.01, 0.02]}, 1), ({2026: [0.01, 0.02]}, 2), ({2026: [0, 1], 2027: [0, 1], 2028: [0, 1]}, 2),
               ({2026: [0, 1], 2027: [0, 1]}, 1), ({2026: [nan, 0.1], 2027: [0, 1]}, 2), ({2026: [0.0, nan]}, 1),
               ({2026: [0.2, 0.1]}, 1), ({2026: [0.1]}, 1), ([[0.01, 0.02]], 1), ({2026: [0, float('inf')]}, 1),
               ({2026: [0.01, 0.02]}, 3), (None, 0)]
        for cis, stage in bad:
            for verdict in (oc.verdict_transfer, oc.verdict_content):
                with self.subTest(cis=cis, stage=stage), self.assertRaises(oc.ContractError):
                    verdict(cis, stage)
        for ci in ([nan, 0.1], [0.1, nan], [0.2, 0.1]):
            with self.subTest(ci=ci), self.assertRaises(oc.ContractError):
                oc.stage1_note(ci)

    def test_level_thresholds(self):
        cases = {0.57499: 'ниже публичного ноутбука на правилах', 0.575: 'на уровне публичного ноутбука на правилах',
                 0.57999: 'на уровне публичного ноутбука на правилах',
                 0.58: 'пайплайн работает: уровень серебра по чужим отчётам',
                 0.58999: 'пайплайн работает: уровень серебра по чужим отчётам',
                 0.59: 'весомо: между серебром и 3-м местом по чужим отчётам'}
        for value, reading in cases.items():
            with self.subTest(value=value):
                result = oc.level_reading([value])
                self.assertEqual(result['reading'], reading)
                self.assertEqual(result['note'], 'один seed')
        two = oc.level_reading([0.57499, 0.57501])                       # the mean is exactly 0.575
        self.assertEqual((two['reading'], two['seeds'], 'note' in two),
                         ('на уровне публичного ноутбука на правилах', 2, False))

    def test_kaggle_reading_is_xfer_rule(self):
        self.assertEqual(oc.kaggle_reading([0.58], [0.57]), 'один seed — не читается')
        self.assertEqual(oc.kaggle_reading([0.590, 0.591], [0.570, 0.571]), 'BA выше B на обоих зёрнах')


# ================================================================== static checks (§2.5, §11)

def otto_modules():
    return sorted(Path(oc.__file__).resolve().parent.glob('otto_*.py'))


def top_level_owner(tree):
    owners = {}
    for top in tree.body:
        for node in ast.walk(top):
            owners[id(node)] = top
    return owners


def private_uses(source):
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.alias):
            names = [node.name, node.asname]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names = [node.value]
        found += [n for n in names if n in oc._PRIVATE]
    return found


def collect_uses(source):
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and 'collect-holdout' in node.value:
            found.append(node.value)
        name = (node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name)
                else node.name if isinstance(node, ast.alias) else None)
        if name == 'COLLECT_HOLDOUT':
            found.append(name)
    return found


def import_violations(source, module):
    """scripts.* imports outside scripts.otto_* and ALLOWED_IMPORTS: absolute, relative, import_module, __import__."""
    package = module.split('.')[:-1]
    bad = []

    def check(target, names):
        if not target or target[0] != 'scripts':
            return
        dotted = '.'.join(target)
        if len(target) >= 2 and target[1].startswith('otto_'):
            return
        if target == ['scripts']:
            bad.extend(f'scripts.{n}' for n in names if not n.startswith('otto_'))
            return
        if dotted not in oc.ALLOWED_IMPORTS or names is None:
            bad.append(dotted)
            return
        bad.extend(f'{dotted}.{n}' for n in names if n not in oc.ALLOWED_IMPORTS[dotted])

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check(alias.name.split('.'), None)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package)-(node.level-1)] if node.level-1 < len(package) else ['..']
                target = base+(node.module.split('.') if node.module else [])
                if base == ['..']:
                    bad.append('relative import above scripts')
                    continue
            else:
                target = node.module.split('.')
            check(target, [a.name for a in node.names])
        elif isinstance(node, ast.Call):
            func = node.func
            fname = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ''
            if fname not in ('import_module', '__import__'):
                continue
            arg = node.args[0] if node.args else None
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                bad.append(f'{fname} with a dynamic name')
                continue
            name = arg.value
            if name.startswith('.'):
                anchor = node.args[1] if len(node.args) > 1 else None
                anchor = anchor.value if isinstance(anchor, ast.Constant) and isinstance(anchor.value, str) else None
                if anchor is None:
                    bad.append(f'{fname}({name!r}) without a literal package')
                    continue
                level = len(name)-len(name.lstrip('.'))
                anchor_parts = anchor.split('.')
                name = '.'.join(anchor_parts[:len(anchor_parts)-(level-1)]+[name.lstrip('.')])
            check(name.split('.'), None)
    return bad


class Static(unittest.TestCase):
    def test_path_literals_only_in_common(self):
        for path in otto_modules():
            if path.name == 'otto_common.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    parts = set(node.value.replace('\\', '/').split('/'))
                    self.assertNotIn('sealed', parts, f'{path.name}: literal sealed')
                    self.assertNotIn('events', parts, f'{path.name}: events tree literal')   # 'test' is also a source name
                    self.assertFalse(any(p.startswith('d=') for p in parts), f'{path.name}: partition literal')

    def test_barrier_callers(self):
        allowed = {'write_sealed': {'otto_data.py'}, 'read_sealed': {'otto_model.py'}, 'events_path': {'otto_data.py'}}
        for path in otto_modules():
            if path.name == 'otto_common.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                name = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
                if name in allowed:
                    self.assertIn(path.name, allowed[name], f'{path.name} uses {name}')

    def test_private_barrier_names_stay_in_common(self):
        for old in ('SEALED', 'SEALED_FILES', 'LOAD_TREES', 'PARTITION_PREFIX'):
            self.assertFalse(hasattr(oc, old), old)
        self.assertEqual(oc._PRIVATE, ('_SEALED', '_SEALED_FILES', '_LOAD_TREES', '_PARTITION_PREFIX'))
        for path in otto_modules():
            if path.name == 'otto_common.py':
                continue
            self.assertEqual(private_uses(path.read_text(encoding='utf-8')), [], path.name)

    def test_private_check_catches_access(self):
        for source in ('from scripts.otto_common import _SEALED', 'oc._LOAD_TREES["train"]',
                       'getattr(oc, "_PARTITION_PREFIX")', 'x = _SEALED_FILES'):
            with self.subTest(source=source):
                self.assertTrue(private_uses(source))

    def test_collect_holdout_only_in_data(self):
        for path in otto_modules():
            if path.name in ('otto_common.py', 'otto_data.py'):
                continue
            self.assertEqual(collect_uses(path.read_text(encoding='utf-8')), [], path.name)
        self.assertTrue(collect_uses('oc.partition_paths(days, "collect-holdout")'))
        self.assertTrue(collect_uses('oc.require_window(oc.COLLECT_HOLDOUT)'))
        self.assertTrue(collect_uses('from scripts.otto_common import COLLECT_HOLDOUT'))

    def test_imports_from_older_modules_follow_the_list(self):
        for path in otto_modules():
            self.assertEqual(import_violations(path.read_text(encoding='utf-8'), f'scripts.{path.stem}'), [], path.name)

    def test_import_check_catches_relative_and_dynamic(self):
        bad = ['from .xfer_common import ContractError, train_frame', 'from . import hm_kaggle',
               'from .. import scripts', 'import scripts.hm_baseline', 'from scripts import xfer_common',
               'import importlib\nimportlib.import_module("scripts.xfer_common")',
               'from importlib import import_module\nimport_module(".hm_kaggle", "scripts")',
               'import importlib\nimportlib.import_module(name)', '__import__("scripts.hm_job")',
               'from scripts.hm_agent_loop import run_loop']
        for source in bad:
            with self.subTest(source=source):
                self.assertTrue(import_violations(source, 'scripts.otto_model'))
        good = ['from .xfer_common import ContractError', 'from . import otto_common', 'from .otto_common import metric',
                'from scripts.xfer_agent import redact', 'import importlib\nimportlib.import_module("scripts.otto_data")',
                'import importlib\nimportlib.import_module("duckdb")', 'import scripts.otto_common as oc']
        for source in good:
            with self.subTest(source=source):
                self.assertEqual(import_violations(source, 'scripts.otto_model'), [])

    def run_python(self, *flags, code):
        prelude = f'import sys; sys.path.append({str(REPO)!r}); from scripts import otto_common as oc; '
        return subprocess.run([sys.executable, *flags, '-c', prelude+code], capture_output=True, text=True,
                              cwd=tempfile.gettempdir(), check=False)

    def test_import_has_no_heavy_side_effects_and_isolated_guard(self):
        probe = self.run_python('-I', code="print([m in sys.modules for m in ('duckdb', 'numpy', 'pandas')]); "
                                           "oc.isolated(); print('ok')")
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.split(), ['[False,', 'False,', 'False]', 'ok'])
        plain = self.run_python(code='oc.isolated()')
        self.assertNotEqual(plain.returncode, 0)
        self.assertIn('python -I', plain.stderr)


if __name__ == '__main__':
    unittest.main()
