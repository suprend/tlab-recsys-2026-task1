"""Tests of scripts/xfer_tinkoff.py on synthetic fixtures (docs/xfer-tinkoff-design.md, section 9)."""
import ast
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import string
import subprocess
import tempfile
import unittest
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from scripts import xfer_common as xc
from scripts import xfer_tinkoff as xt

NUMBER = re.compile(r'(?<![A-Za-z0-9_.@])\d+(?:\.\d+)?(?![A-Za-z0-9_])')
TEST_USERS = list(range(30))
CANARY_ITEM = 99      # only events at t >= 671
EDGE_ITEM = 98        # first event exactly at t = 641
DUP_USER, DUP_ITEM = 2, 5
QUIET_USER = 59       # history but no event in [641, 671)
TWICE_USER, TWICE_ITEM = 3, 95   # the same new pair twice inside the val target window [641, 671)


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


def synthetic_events(seed=7, users=60, items=40, extra=()):
    rng = np.random.default_rng(seed)
    rows = []
    for u in range(users):
        k = int(rng.integers(8, 17))
        chosen = rng.choice(items, size=k, replace=False)
        low, high = (0, 400) if u == QUIET_USER else ((0 if u % 3 == 0 else 300), 701)
        times = rng.integers(low, high, size=k)
        for i, t in zip(chosen, times):
            if (u, int(i)) == (DUP_USER, DUP_ITEM):
                continue
            rows.append((u, int(i), int(t)))
    rows += [(0, CANARY_ITEM, 680), (1, EDGE_ITEM, 641), (DUP_USER, DUP_ITEM, 100), (DUP_USER, DUP_ITEM, 650),
             (4, TWICE_ITEM, 300), (TWICE_USER, TWICE_ITEM, 645), (TWICE_USER, TWICE_ITEM, 660)]
    rows += list(extra)
    return rows


class Env:
    """A temporary git root with raw files of ``events`` and a finished load."""

    def __init__(self, events, test_users=TEST_USERS):
        self.events = events
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q')
        (self.root/'configs'/'datasets').mkdir(parents=True)
        (self.root/'artifacts'/'xfer').mkdir(parents=True)
        (self.root/'README').write_text('x')
        git(self.root, 'add', 'README')
        git(self.root, 'commit', '-q', '-m', 'init')
        self.patches = [mock.patch.object(xc, 'ROOT', self.root),
                        mock.patch.object(xc, 'code_identity', lambda dataset: {'scripts/xfer_tinkoff.py': 'x'})]
        for p in self.patches:
            p.start()
        self.raw = xc.raw_dir('tinkoff')
        self.raw.mkdir(parents=True)
        lines = ['user_id,item_id,timestamp'] + [f'{u},{i},{t}' for u, i, t in events]
        (self.raw/'data_train.csv').write_text('\n'.join(lines)+'\n')
        (self.raw/'test_users.csv').write_text('\n'.join(['user_id', *map(str, test_users)])+'\n')
        (self.raw/'baseline.csv').write_text('user_id,item_id\n0,1\n')
        files = [dict(name=n, size=(self.raw/n).stat().st_size, sha256=xc.sha256_file(self.raw/n))
                 for n in xt.CSV_FILES]
        (self.raw/'kaggle-verify.json').write_text(json.dumps(dict(status='complete', files=files)))
        self.facts = dict(rows=len(events), pairs=len({(u, i) for u, i, _ in events}),
                          users=len({u for u, _, _ in events}), items=len({i for _, i, _ in events}),
                          t_min=min(t for *_, t in events), t_max=max(t for *_, t in events),
                          test_users=len(test_users))
        self.facts_patch = mock.patch.object(xt, 'LOAD_FACTS', self.facts)
        self.facts_patch.start()

    def load(self):
        return xt.load(self.raw, xc.output_dir('tinkoff', 'load'))

    def close(self):
        self.facts_patch.stop()
        for p in reversed(self.patches):
            p.stop()
        for path in self.root.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        self.tmp.cleanup()

    def commit(self, *paths):
        git(self.root, 'add', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def write_config(self, kind, value, commit=True):
        path = xc.config_path('tinkoff', kind)
        path.write_text(json.dumps(value))
        if commit:
            self.commit(path)
        return path

    def open_result(self):
        self.write_config('holdout', dict(result=1))

    def freeze(self, base):
        base_path = self.write_config('base', base)
        set_path = self.write_config('set', dict(columns=[]))
        self.write_config('prereg', dict(base_sha256=xc.sha256_file(base_path), set_sha256=xc.sha256_file(set_path)))


class EnvCase(unittest.TestCase):
    events = None

    def setUp(self):
        self.env = Env(self.events or synthetic_events())
        self.env.load()
        self.base = xt.initial_base()

    def tearDown(self):
        self.env.close()

    def out(self, name):
        return xc.output_dir('tinkoff', 'base-dev', name)


def past_pairs(events, A):
    pairs = {}
    for u, i, t in events:
        if t < A:
            t0, t1 = pairs.get((u, i), (t, t))
            pairs[(u, i)] = (min(t0, t), max(t1, t))
    return pairs


def reference_frame(events, A, users, base):
    """Plain-Python reading of sections 3-4 for the comparison with the vectorised build."""
    sources = base['candidates']['sources']
    total = base['candidates']['total']
    pairs = past_pairs(events, A)
    items = sorted({i for _, i in pairs})

    def users_w(i, w):
        return sum(1 for (u, j), (t0, t1) in pairs.items() if j == i and (w is None or t1 >= A - w))
    seen = {}
    for (u, i), (t0, t1) in pairs.items():
        seen.setdefault(u, {})[i] = (t0, t1)
    rows = []
    sims = {}
    for s in sources:
        if s['kind'] == 'cooc':
            sets = {}
            for (u, i), (t0, t1) in pairs.items():
                if t1 >= A - s['window']:
                    sets.setdefault(u, set()).add(i)
            n = {i: sum(1 for v in sets.values() if i in v) for i in items}
            sim = {}
            for i in items:
                for j in items:
                    co = sum(1 for v in sets.values() if i in v and j in v) if i != j else 0
                    sim[(i, j)] = co/math.sqrt(n[i]*n[j]) if co else 0.0
            sims[s['name']] = (sim, n)
    first_step = {}
    for (u, i), (t0, t1) in pairs.items():
        first_step[u] = min(first_step.get(u, t0), t0)
    all_order = sorted(items, key=lambda i: (-users_w(i, None), i))
    for u in sorted(users):
        mine = seen.get(u, {})
        unseen = [i for i in items if i not in mine]
        recent = [i for i, _ in sorted(mine.items(), key=lambda kv: (-kv[1][1], kv[0]))]
        lists, extra = {}, {}
        for s in sources:
            if s['kind'] == 'pop':
                order = sorted(unseen, key=lambda i: (-users_w(i, s['window']), i))
            else:
                last = recent[:s['last']]
                sim, n = sims[s['name']]
                score = {j: round(sum(sim[(i, j)] for i in last), s['decimals']) for j in unseen}
                extra[s['name']] = dict(last=last, sim=sim, n=n, score=score)
                order = sorted([j for j in unseen if score[j] > 0], key=lambda j: (-score[j], j))
            if s['depth'] is not None:
                order = order[:s['depth']]
            lists[s['name']] = order
        taken, reach = [], {}
        for s in sources:
            last_kept, stopped = 0, False
            for rank, i in enumerate(lists[s['name']], start=1):
                if i in taken:
                    continue
                if len(taken) == total:
                    stopped = True
                    break
                taken.append(i)
                last_kept = rank
            reach[s['name']] = last_kept if stopped else math.inf
        times = list(mine.values())
        for j in sorted(taken):
            row = dict(user_id=u, item_id=j)
            for f in base['features']:
                name = f['name']
                d = xt.feature_definition(name, sources)
                kind, params = d['kind'], d['params']
                if kind == 'users':
                    row[name] = users_w(j, params['window'])
                elif kind == 'trend':
                    row[name] = users_w(j, 7)/users_w(j, 30) if users_w(j, 30) else np.nan
                elif kind == 'item_age':
                    row[name] = A - min(t0 for (v, i), (t0, t1) in pairs.items() if i == j)
                elif kind == 'item_last':
                    row[name] = A - max(t1 for (v, i), (t0, t1) in pairs.items() if i == j)
                elif kind == 'n_items':
                    row[name] = sum(1 for (t0, t1) in times if params['window'] is None or t1 >= A - params['window'])
                elif kind == 'user_recency':
                    row[name] = A - max(t1 for _, t1 in times)
                elif kind == 'user_age':
                    row[name] = A - min(t0 for t0, _ in times)
                elif kind == 'global_rank':
                    row[name] = all_order.index(j) + 1
                elif kind == 'rank':
                    order = lists[params['source']]
                    row[name] = order.index(j) + 1 if j in order else np.nan
                elif kind == 'pop_share':
                    row[name] = users_w(j, params['window'])/users_w(j, None)
                elif kind == 'item_new':
                    row[name] = sum(1 for (v, i) in pairs if i == j and first_step[v] >= A - params['window'])
                elif kind == 'user_rate':
                    row[name] = len(times)/max(A - min(t0 for t0, _ in times), 1)
                else:
                    e = extra[params['source']]
                    sims_j = [e['sim'][(i, j)] for i in e['last']]
                    m = params.get('m')
                    if kind == 'cooc_score':
                        row[name] = e['score'][j]
                    elif kind == 'cooc_max':
                        row[name] = max(sims_j or [0.0])
                    elif kind == 'cooc_hits':
                        row[name] = sum(1 for x in sims_j if x > 0)
                    elif kind == 'cooc_last':
                        row[name] = sum(sims_j[:m])
                    elif kind == 'cooc_n_last':
                        row[name] = sum(1 for x in sims_j[:m] if x > 0)
                    elif kind == 'cooc_wsum':
                        row[name] = sum(0.8**p * x for p, x in enumerate(sims_j))
                    else:
                        known = sum(1 for i in e['last'] if e['n'][i] > 0)
                        row[name] = e['score'][j]/known if known else np.nan
            for s in sources:
                order = lists[s['name']]
                rank = order.index(j) + 1 if j in order else None
                row['src_'+s['name']] = rank if rank is not None and rank <= reach[s['name']] else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def assert_frames_equal(test, got, want):
    test.assertEqual(list(got.columns), list(want.columns))
    test.assertEqual(len(got), len(want))
    got = got.sort_values(['user_id', 'item_id']).reset_index(drop=True)
    want = want.sort_values(['user_id', 'item_id']).reset_index(drop=True)
    for column in got.columns:
        a = got[column].astype('float64').to_numpy()
        b = want[column].astype('float64').to_numpy()
        test.assertTrue(np.array_equal(np.isnan(a), np.isnan(b)), column)
        mask = ~np.isnan(a)
        test.assertTrue(np.allclose(a[mask], b[mask], rtol=0, atol=1e-9), column)


class Load(EnvCase):
    def test_load_report_and_partitions(self):
        report = xc.read_json(xc.output_dir('tinkoff', 'load', 'load.json'))
        self.assertEqual(report['facts'], self.env.facts)
        self.assertEqual(report['digest'], xc.canonical_digest({k: v for k, v in report.items() if k != 'digest'}))
        parts = xc.events_path('tinkoff')['parts']
        con = duckdb.connect()
        for entry in report['partitions']:
            start = entry['bucket']
            self.assertEqual(start, xt.bucket_start(start))
            self.assertTrue(start == 0 or (start - 11) % 30 == 0)
            path = parts/entry['file']
            self.assertEqual(path.parent.name, f'b={start}')
            low, high, n = con.execute(f"SELECT min(t), max(t), count(*) FROM read_parquet('{path}')").fetchone()
            self.assertEqual(n, entry['rows'])
            if n:
                self.assertEqual(xt.bucket_start(low), start)
                self.assertLess(high, xt.bucket_end(start))
        self.assertEqual(sum(e['rows'] for e in report['partitions']), len(self.env.events))
        cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parts}/b=641/*.parquet', hive_partitioning=false)").fetchall()
        self.assertEqual([(c[0], c[1]) for c in cols], [('user_id', 'BIGINT'), ('item_id', 'BIGINT'), ('t', 'INTEGER')])
        static = duckdb.connect(str(xc.static_path('tinkoff')), read_only=True)
        self.assertEqual(static.execute('SELECT count(*) FROM test_users').fetchone()[0], len(TEST_USERS))
        static.close()
        with self.assertRaises(xc.ContractError):
            self.env.load()

    def test_anchor_buckets(self):
        info = xt.anchors()
        for role, values in info['roles'].items():
            for anchor in values:
                self.assertTrue(xt.is_boundary(anchor), (role, anchor))
                self.assertEqual(xt.bucket_start(anchor), anchor)
        self.assertEqual(xt.bucket_start(10), 0)
        self.assertEqual(xt.bucket_start(40), 11)
        self.assertEqual(xt.bucket_start(700), 671)


class LoadRefusals(unittest.TestCase):
    def test_wrong_facts_leave_nothing(self):
        env = Env(synthetic_events())
        try:
            with mock.patch.object(xt, 'LOAD_FACTS', dict(env.facts, rows=1)):
                with self.assertRaises(xc.ContractError):
                    env.load()
            paths = xc.events_path('tinkoff')
            self.assertFalse(paths['db'].exists())
            self.assertFalse(paths['parts'].exists())
            self.assertFalse(xc.static_path('tinkoff').exists())
            self.assertEqual([p.name for p in paths['db'].parent.iterdir()], [])
        finally:
            env.close()

    def test_hash_mismatch(self):
        env = Env(synthetic_events())
        try:
            with (env.raw/'baseline.csv').open('a') as stream:
                stream.write('2,3\n')
            with self.assertRaises(xc.ContractError):
                env.load()
        finally:
            env.close()


class Barrier(EnvCase):
    def test_history_canary(self):
        for before in (461, 641, 671):
            con = xt.history(before, 'test')
            top, canary = con.execute(f'SELECT max(t), count(*) FILTER (WHERE item_id = {CANARY_ITEM}) FROM events'
                                      ).fetchone()
            con.close()
            self.assertLess(top, before)
            self.assertEqual(canary, 0)
        with self.assertRaises(xc.ContractError):
            xt.history(701, 'sidecar')
        with self.assertRaises(xc.ContractError):
            xt.history(672, 'collect-holdout')
        self.env.open_result()
        con = xt.history(701, 'sidecar')
        self.assertEqual(con.execute(f'SELECT count(*) FROM events WHERE item_id = {CANARY_ITEM}').fetchone()[0], 1)
        con.close()

    def test_views_canary_and_slice(self):
        for anchor in (611, 641, 671):
            spec = xt.views(anchor, 'probe')
            for directory in spec['directories']:
                start = int(Path(directory).name.split('=')[1])
                self.assertLessEqual(start + 30, anchor)
            con = duckdb.connect()
            top, at_anchor, canary = con.execute(
                f"SELECT max(t), count(*) FILTER (WHERE t = {anchor}), count(*) FILTER (WHERE item_id = {CANARY_ITEM})"
                f" FROM ({spec['views']['ev']})").fetchone()
            items = {r[0] for r in con.execute(spec['items']).fetchall()}
            con.close()
            self.assertLess(top, anchor)
            self.assertEqual((at_anchor, canary), (0, 0))
            self.assertEqual(items, {i for u, i, t in self.env.events if t < anchor})
            self.assertEqual(spec['levels'], {'pair': ['user_id', 'item_id'], 'user': ['user_id'], 'item': ['item_id']})
        self.assertNotIn(EDGE_ITEM, {r[0] for r in duckdb.connect().execute(xt.views(641, 'p')['items']).fetchall()})
        with self.assertRaises(xc.ContractError):
            xt.views(701, 'sidecar')
        with self.assertRaises(xc.ContractError):
            xt.views(640, 'probe')
        self.env.open_result()
        spec = xt.views(701, 'sidecar')
        self.assertIn(671, spec['buckets'])

    def test_collect_kaggle_needs_result_receipt(self):
        with self.assertRaises(xc.ContractError):
            xt.collect(701, 'kaggle', self.base, xc.output_dir('tinkoff', 'collections', 'kaggle-701'))
        self.assertFalse(xc.output_dir('tinkoff', 'collections', 'kaggle-701').exists())


class FutureInvariance(unittest.TestCase):
    def frame_and_pool(self, events):
        env = Env(events)
        try:
            env.load()
            with mock.patch.object(xt, 'PROBE_USERS', 12):
                pool = xt.probe_pool()
            out = xc.output_dir('tinkoff', 'collections', 'probe-641')
            manifest = xt.collect(641, 'probe', xt.initial_base(), out, users=list(range(20)))
            frame = xc.read_parquet(out/'frame.parquet')
            return pool, manifest['frame_digest'], frame
        finally:
            env.close()

    def test_events_at_and_after_anchor_are_invisible(self):
        base_events = synthetic_events()
        future = [(u, i, t) for u, i, t in [(3, 33, 641), (4, 97, 641), (5, 96, 660), (200, 1, 641), (201, 2, 700),
                                             (6, 30, 641)]
                  if (u, i) not in {(v, j) for v, j, _ in base_events}]
        pool_a, digest_a, frame_a = self.frame_and_pool(base_events)
        pool_b, digest_b, frame_b = self.frame_and_pool(base_events + future)
        self.assertEqual(digest_a, digest_b)
        self.assertEqual(pool_a, pool_b)
        users = {u for u, _, t in base_events if t < 641}
        self.assertEqual(pool_a, xc.cap_queries(users, 12))
        self.assertNotIn(97, set(frame_a['item_id']))


class Collect(EnvCase):
    def test_reference_build_initial_base(self):
        con = xt.history(641, 'test')
        frame = xt._build(xt._Past(con, 641), range(25), xt._spec(self.base))
        con.close()
        assert_frames_equal(self, frame, reference_frame(self.env.events, 641, range(25), self.base))

    def test_reference_build_union_and_parametric_features(self):
        candidates = dict(total=30, sources=[dict(name='pop30', kind='pop', window=30, depth=20),
                                             dict(name='near', kind='cooc', window=90, last=6, depth=5, decimals=9),
                                             dict(name='cooc60', kind='cooc', window=60, last=5, depth=3, decimals=9),
                                             dict(name='cooc3', kind='cooc', window=3, last=5, depth=3, decimals=6),
                                             dict(name='fill', kind='pop', window=None, depth=None)])
        sources = candidates['sources']
        names = ['users_1', 'users_3', 'users_14', 'users_all', 'trend', 'item_age', 'item_last', 'pop_share_7',
                 'pop_share_30', 'pop_share_90', 'item_new_30',
                 'n_items_all', 'n_items_90', 'n_items_7', 'user_recency', 'user_age', 'user_rate',
                 'near_score', 'near_rank', 'near_max', 'near_hits', 'near_last3', 'near_wsum', 'near_mean',
                 'near_n_last', 'cooc60_rank', 'cooc60_score', 'cooc60_mean', 'cooc3_rank', 'cooc3_score',
                 'cooc3_mean', 'cooc3_last5', 'pop30_rank',
                 'fill_rank', 'global_rank']
        features = [{k: xt.feature_definition(n, sources)[k] for k in ('name', 'formula', 'missing')} for n in names]
        base = xc.make_base('tinkoff', candidates, features, [])
        for anchor in (461, 611):
            con = xt.history(anchor, 'test')
            users = sorted({u for u, _, t in self.env.events if t < anchor})
            with mock.patch.object(xt, 'BATCH_USERS', 7):
                frame = xt._build(xt._Past(con, anchor), users, xt._spec(base))
            con.close()
            assert_frames_equal(self, frame, reference_frame(self.env.events, anchor, users, base))
            past = past_pairs(self.env.events, anchor)
            universe = {i for _, i in past}
            sizes = frame.groupby('user_id').size()
            for u in users:
                self.assertEqual(sizes[u], min(30, len(universe - {i for v, i in past if v == u})))
            self.assertTrue(frame['cooc3_mean'].isna().any() and frame['cooc3_mean'].notna().any())
            self.assertTrue(frame['src_cooc60'].notna().any() and frame['src_near'].notna().any())
        self.assertEqual(xt.coverage_sources(base), {'recent': ['src_near', 'src_cooc60', 'src_cooc3'],
                                                     'global': ['src_pop30', 'src_fill']})

    def test_pop_inside_candidates_of_another_base(self):
        candidates = dict(total=22, sources=[dict(name='pop30', kind='pop', window=30, depth=20),
                                             dict(name='near', kind='cooc', window=60, last=4, depth=10, decimals=9),
                                             dict(name='fill', kind='pop', window=None, depth=None)])
        names = ['users_30', 'near_score', 'near_rank', 'user_rate']
        features = [{k: xt.feature_definition(n, candidates['sources'])[k] for k in ('name', 'formula', 'missing')}
                    for n in names]
        base = xc.make_base('tinkoff', candidates, features, [])
        out = self.out('smoke-pop')
        xt.collect(641, 'val', base, out)
        frame = xc.read_parquet(out/'frame.parquet')
        labels = xc.read_parquet(out/'labels.parquet')
        targets = xc.read_parquet(out/'targets.parquet')
        lists = xt.pop(641, targets['user_id'].tolist())
        pairs = set(zip(frame['user_id'], frame['item_id']))
        self.assertTrue(set(zip(lists['user_id'], lists['item_id'])) <= pairs)
        got = xt.metric(lists, targets, labels).set_index('user_id')['value']
        truth = {}
        for u, i, t in self.env.events:
            if 641 <= t < 671:
                truth.setdefault(u, set()).add(i)
        for u, n in zip(targets['user_id'], targets['n_targets']):
            mine = lists[lists['user_id'] == u]
            dcg = sum(1/math.log2(r+1) for i, r in zip(mine['item_id'], mine['rank']) if i in truth[u])
            self.assertAlmostEqual(got[u], dcg/sum(1/math.log2(k+1) for k in range(1, min(n, 20)+1)))
        self.assertGreater(got.sum(), 0)
        for bad in (dict(candidates, total=19),
                    dict(candidates, sources=candidates['sources'][1:]),
                    dict(candidates, sources=[dict(candidates['sources'][0], depth=19), *candidates['sources'][1:]]),
                    dict(candidates, sources=[dict(candidates['sources'][0], window=7), *candidates['sources'][1:]]),
                    dict(candidates, sources=[candidates['sources'][2], *candidates['sources'][:2]]),
                    dict(candidates, sources=[dict(candidates['sources'][1], window=30, depth=20),
                                              candidates['sources'][0], candidates['sources'][2]])):
            with self.assertRaises(xc.ContractError):
                xt._policy(bad)

    def test_existing_output_refused_before_history(self):
        self.env.freeze(self.base)
        self.env.open_result()
        cases = dict(train=(611, self.out('smoke-x1')), val=(641, self.out('smoke-x2')),
                     probe=(641, self.out('smoke-x3')), kaggle=(701, self.out('smoke-x4')),
                     holdout=(671, xc.current_holdout_collection('tinkoff', 671)))
        for role, (anchor, out) in cases.items():
            out.mkdir(parents=True)
            users = [1, 2] if role == 'probe' else None
            with mock.patch.object(xt, 'history', side_effect=AssertionError('history was read')):
                with self.assertRaises(xc.ContractError, msg=role):
                    xt.collect(anchor, role, self.base, out, users=users)
            self.assertEqual(list(out.iterdir()), [], role)

    def test_batch_size_does_not_change_frame(self):
        con = xt.history(641, 'test')
        past = xt._Past(con, 641)
        con.close()
        spec = xt._spec(self.base)
        whole = xt._build(past, range(40), spec)
        with mock.patch.object(xt, 'BATCH_USERS', 3):
            split = xt._build(past, range(40), spec)
        self.assertEqual(xt.content_digest(whole), xt.content_digest(split))

    def test_val_targets_labels(self):
        out = self.out('smoke-val')
        manifest = xt.collect(641, 'val', self.base, out)
        frame = xc.read_parquet(out/'frame.parquet')
        labels = xc.read_parquet(out/'labels.parquet')
        targets = xc.read_parquet(out/'targets.parquet')
        events = self.env.events
        past = past_pairs(events, 641)
        expected = {}
        for u, i, t in events:
            if 641 <= t < 671 and (u, i) not in past and any(v == u for v, _ in past):
                expected.setdefault(u, set()).add(i)
        self.assertEqual(dict(zip(targets['user_id'], targets['n_targets'])), {u: len(v) for u, v in expected.items()})
        self.assertNotIn(QUIET_USER, set(targets['user_id']))
        self.assertNotIn(DUP_ITEM, expected.get(DUP_USER, set()))
        self.assertIn(EDGE_ITEM, expected[1])
        self.assertIn(TWICE_ITEM, expected[TWICE_USER])
        twice = labels[(labels['user_id'] == TWICE_USER) & (labels['item_id'] == TWICE_ITEM)]
        self.assertEqual(twice['label'].tolist(), [1])
        universe = {i for u, i, t in events if t < 641}
        self.assertTrue(set(frame['item_id']) <= universe)
        self.assertNotIn(EDGE_ITEM, set(frame['item_id']))
        self.assertFalse(any((u, i) in past for u, i in zip(frame['user_id'], frame['item_id'])))
        self.assertEqual(list(zip(labels['user_id'], labels['item_id'])), list(zip(frame['user_id'], frame['item_id'])))
        positives = {(u, i) for u, v in expected.items() for i in v}
        self.assertEqual(set(labels.loc[labels['label'] == 1, ['user_id', 'item_id']].itertuples(index=False, name=None)),
                         {(u, i) for u, i in zip(frame['user_id'], frame['item_id']) if (u, i) in positives})
        self.assertEqual(manifest['counts']['queries'], len(expected))
        self.assertEqual(set(frame['user_id']), set(expected))
        self.assertEqual(list(frame.columns), ['user_id', 'item_id', *xc.base_feature_names(self.base),
                                               'src_pop30', 'src_cooc', 'src_fill'])
        ordered = frame.sort_values(['user_id', 'item_id']).reset_index(drop=True)
        self.assertTrue(frame[['user_id', 'item_id']].equals(ordered[['user_id', 'item_id']]))
        xc.read_collection(out, dataset='tinkoff', role='val', base=self.base)

    def test_train_cap_in_query_order(self):
        with mock.patch.object(xt, 'N', 5):
            out = self.out('smoke-train')
            manifest = xt.collect(611, 'train', self.base, out)
        events = self.env.events
        past = past_pairs(events, 611)
        eligible = {u for u, i, t in events if 611 <= t < 641 and (u, i) not in past and any(v == u for v, _ in past)}
        targets = xc.read_parquet(out/'targets.parquet')
        self.assertEqual(sorted(targets['user_id']), sorted(xc.cap_queries(eligible, 5)))
        self.assertEqual(manifest['counts']['eligible_queries'], len(eligible))
        self.assertEqual(manifest['counts']['queries'], 5)

    def test_repeat_collect_same_digest(self):
        a = xt.collect(641, 'probe', self.base, self.out('smoke-a'), users=list(range(30)))
        b = xt.collect(641, 'probe', self.base, self.out('smoke-b'), users=list(range(30)))
        self.assertEqual(a['frame_digest'], b['frame_digest'])
        self.assertEqual(a['frame_digest'], xt.content_digest(self.out('smoke-a')/'frame.parquet'))

    def test_probe_writes_no_labels(self):
        out = self.out('smoke-probe')
        manifest = xt.collect(641, 'probe', self.base, out, users=list(range(10)))
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['frame.parquet', 'manifest.json'])
        self.assertEqual(manifest['role'], 'probe')
        with self.assertRaises(xc.ContractError):
            xt.collect(641, 'probe', self.base, self.out('smoke-probe2'))
        with self.assertRaises(xc.ContractError):
            xt.collect(641, 'val', self.base, self.out('smoke-val2'), users=[1])
        with self.assertRaises(xc.ContractError):
            xt.collect(640, 'val', self.base, self.out('smoke-val3'))

    def test_coverage_sources(self):
        self.assertEqual(xt.coverage_sources(self.base), {'recent': ['src_cooc'], 'global': ['src_pop30', 'src_fill']})
        out = self.out('smoke-cov')
        xt.collect(641, 'probe', self.base, out, users=list(range(30)))
        frame = xc.read_parquet(out/'frame.parquet')
        sources = frame[['src_pop30', 'src_cooc', 'src_fill']].notna()
        self.assertTrue(sources.any(axis=1).all())
        self.assertTrue((frame['src_pop30'].notna() == frame['pop30_rank'].notna()).all())
        self.assertTrue((frame['src_cooc'].notna() == frame['cooc_rank'].notna()).all())
        self.assertTrue((frame['cooc_rank'].notna() <= (frame['cooc_score'] > 0)).all())

    def test_holdout_collect_once_and_sealed(self):
        target = xc.current_holdout_collection('tinkoff', 671)
        with self.assertRaises(xc.ContractError):
            xt.collect(671, 'holdout', self.base, target)
        self.assertFalse(target.exists())
        self.env.freeze(self.base)
        with self.assertRaises(xc.ContractError):
            xt.collect(671, 'holdout', self.base, xc.output_dir('tinkoff', 'collections', 'elsewhere'))
        manifest = xt.collect(671, 'holdout', self.base, target)
        names = sorted(p.name for p in target.iterdir())
        self.assertEqual(names, ['frame.parquet', 'manifest.json', 'sealed'])
        for name in ('labels.parquet', 'targets.parquet'):
            self.assertEqual(oct((target/'sealed'/name).stat().st_mode & 0o777), '0o400')
        self.assertFalse({'positives', 'targets', 'labels', 'n_targets'} & set(manifest['counts']))
        frame = xc.read_parquet(target/'frame.parquet')
        self.assertIn(CANARY_ITEM, {i for u, i, t in self.env.events if t >= 671})
        self.assertNotIn(CANARY_ITEM, set(frame['item_id']))
        with self.assertRaises(xc.ContractError):
            xt.collect(671, 'holdout', self.base, target)
        self.env.write_config('holdout-open', dict(x=1))
        sealed = xc.read_sealed(target, 'holdout')
        labels = xc.read_parquet(sealed['labels'])
        targets = xc.read_parquet(sealed['targets'])
        self.assertEqual(list(zip(labels['user_id'], labels['item_id'])), list(zip(frame['user_id'], frame['item_id'])))
        events = self.env.events
        past = past_pairs(events, 671)
        expected = {}
        for u, i, t in events:
            if 671 <= t < 701 and (u, i) not in past and any(v == u for v, _ in past):
                expected.setdefault(u, set()).add(i)
        self.assertIn(CANARY_ITEM, expected[0])
        self.assertEqual(dict(zip(targets['user_id'], targets['n_targets'])), {u: len(v) for u, v in expected.items()})
        self.assertEqual(set(frame['user_id']), set(expected))
        positives = {(u, i) for u, v in expected.items() for i in v}
        self.assertEqual(set(labels.loc[labels['label'] == 1, ['user_id', 'item_id']].itertuples(index=False, name=None)),
                         {(u, i) for u, i in zip(frame['user_id'], frame['item_id']) if (u, i) in positives})
        self.assertNotIn((0, CANARY_ITEM), set(zip(labels['user_id'], labels['item_id'])))

    def test_kaggle_and_assemble(self):
        self.env.open_result()
        out = xc.output_dir('tinkoff', 'collections', 'kaggle-701')
        manifest = xt.collect(701, 'kaggle', self.base, out)
        frame = xc.read_parquet(out/'frame.parquet')
        self.assertEqual(set(frame['user_id']), set(TEST_USERS))
        self.assertEqual(manifest['counts']['users'], len(TEST_USERS))
        self.assertIn(CANARY_ITEM, set(frame['item_id']))
        rng = np.random.default_rng(1)
        scores = frame[['user_id', 'item_id']].assign(score=rng.normal(size=len(frame)))
        scores = scores[scores['user_id'] != 7]
        few = scores[scores['user_id'] == 8].sort_values('item_id').head(5)
        scores = pd.concat([scores[scores['user_id'] != 8], few], ignore_index=True)
        kaggle = xc.output_dir('tinkoff', 'kaggle')
        kaggle.mkdir(parents=True)
        receipt = xt.assemble(scores, kaggle/'B2026.csv')
        self.assertEqual(receipt['fallback_users'], 2)
        past = past_pairs(self.env.events, 701)
        order = sorted({i for _, i in past}, key=lambda i: (-sum(1 for _, j in past if j == i), i))
        written = {}
        for line in (kaggle/'B2026.csv').read_text().splitlines()[1:]:
            u, i = map(int, line.split(','))
            written.setdefault(u, []).append(i)
        self.assertEqual(written[7], [i for i in order if (7, i) not in past][:20])
        head = few.sort_values(['score', 'item_id'], ascending=[False, True])['item_id'].tolist()
        self.assertEqual(written[8], head + [i for i in order if (8, i) not in past and i not in head][:15])
        self.assertEqual(receipt['rows'], 20*len(TEST_USERS))
        lines = (kaggle/'B2026.csv').read_text().splitlines()
        self.assertEqual(lines[0], 'user_id,item_id')
        first = [int(line.split(',')[1]) for line in lines[1:] if line.startswith('0,')]
        mine = scores[scores['user_id'] == 0].sort_values(['score', 'item_id'], ascending=[False, True])
        self.assertEqual(first, mine['item_id'].head(20).tolist())
        with self.assertRaises(xc.ContractError):
            xt.assemble(scores, kaggle/'B2026.csv')
        bad_user = pd.concat([scores, pd.DataFrame(dict(user_id=[55], item_id=[0], score=[1.0]))])
        bad_seen = scores.copy()
        seen_item = next(i for u, i, t in self.env.events if u == 0)
        bad_seen = pd.concat([bad_seen[~((bad_seen.user_id == 0) & (bad_seen.item_id == seen_item))],
                              pd.DataFrame(dict(user_id=[0], item_id=[seen_item], score=[9.0]))])
        bad_item = pd.concat([scores, pd.DataFrame(dict(user_id=[1], item_id=[555], score=[1.0]))])
        for i, bad in enumerate((bad_user, bad_seen, bad_item)):
            with self.assertRaises(xc.ContractError):
                xt.assemble(bad, kaggle/f'bad{i}.csv')

    def test_check_submission_rejects(self):
        users = [0, 1]
        universe = list(range(30))
        seen = xt.pair_keys([0], [0])
        good = ['user_id,item_id'] + [f'{u},{i}' for u in users for i in range(1, 21)]

        def write(lines, name):
            path = Path(self.env.root)/name
            path.write_text('\n'.join(lines)+'\n')
            return path
        self.assertEqual(xt.check_submission(write(good, 'ok.csv'), users, universe, seen)['rows'], 40)
        cases = dict(short=good[:-1], foreign=good + ['5,3'], seen=['user_id,item_id'] + [
            f'{u},{i}' for u in users for i in range(0 if u == 0 else 1, 20 if u == 0 else 21)],
            outside=['user_id,item_id'] + [f'{u},{i}' for u in users for i in range(11, 31)],
            header=['user,item'] + good[1:], repeat=good[:-1] + [good[-2]])
        for name, lines in cases.items():
            with self.assertRaises(xc.ContractError, msg=name):
                xt.check_submission(write(lines, f'{name}.csv'), users, universe, seen)
        scores = pd.DataFrame(dict(user_id=[0]*20 + [1]*15, item_id=[*range(1, 21), *range(1, 16)],
                                   score=[-float(i) for i in range(1, 21)] + [-float(i) for i in range(1, 16)]))
        fill = list(range(1, 30))
        self.assertEqual(xt.check_submission(write(good, 'ok2.csv'), users, universe, seen, scores=scores,
                                             fill=fill)['rows'], 40)
        swapped = list(good)
        swapped[1], swapped[2] = swapped[2], swapped[1]
        late_fill = good[:21] + [f'1,{i}' for i in [*range(1, 16), 17, 16, 18, 19, 20]]
        for name, lines in dict(swapped=swapped, late_fill=late_fill).items():
            with self.assertRaises(xc.ContractError, msg=name):
                xt.check_submission(write(lines, f'{name}.csv'), users, universe, seen, scores=scores, fill=fill)
        with self.assertRaises(xc.ContractError):  # fill item 0 is unseen by user 1 and comes first
            xt.check_submission(write(good, 'ok3.csv'), users, universe, seen, scores=scores, fill=list(range(30)))
        crlf = Path(self.env.root)/'crlf.csv'
        crlf.write_bytes(('\r\n'.join(good)+'\r\n').encode())
        with self.assertRaises(xc.ContractError):
            xt.check_submission(crlf, users, universe, seen)

    def test_pop(self):
        users = list(range(20))
        lists = xt.pop(641, users, 20)
        past = past_pairs(self.env.events, 641)
        universe = {i for _, i in past}
        self.assertTrue(set(lists['item_id']) <= universe)
        self.assertFalse(any((u, i) in past for u, i in zip(lists['user_id'], lists['item_id'])))
        self.assertTrue((lists.groupby('user_id').size() == 20).all())
        con = xt.history(641, 'test')
        frame = xt._build(xt._Past(con, 641), users, xt._spec(self.base))
        con.close()
        top = frame[frame['pop30_rank'] <= 20][['user_id', 'item_id', 'pop30_rank']]
        self.assertEqual(sorted(zip(lists.user_id, lists.item_id, lists['rank'])),
                         sorted(zip(top.user_id, top.item_id, top.pop30_rank.astype(int))))

    def test_probe_stats_and_pool(self):
        with mock.patch.object(xt, 'PROBE_USERS', 15):
            pool = xt.probe_pool()
        self.assertEqual(pool, xc.cap_queries({u for u, _, t in self.env.events if t < 641}, 15))
        stats = xt.probe_stats(641, pool, self.base)
        rows = sum(1 for *_, t in self.env.events if t < 641)
        self.assertEqual(stats['events_by_window']['all_history']['events'], rows)
        self.assertEqual(stats['events_by_window']['last_30_steps']['events'],
                         sum(1 for *_, t in self.env.events if 611 <= t < 641))
        added = stats['candidates']['added_per_user_mean_by_source']
        self.assertAlmostEqual(sum(added.values()), stats['candidates']['per_user_mean'], places=1)
        json.dumps(stats, allow_nan=False)

    def test_training_rows(self):
        out = self.out('smoke-tr')
        xt.collect(641, 'val', self.base, out)
        frame = xc.read_parquet(out/'frame.parquet')
        labels = xc.read_parquet(out/'labels.parquet')
        rows = xt.training_rows(frame.sample(frac=1, random_state=1), labels, 641)
        self.assertEqual(len(rows), len(frame))
        self.assertTrue((rows['weight'] == 1.0).all())
        self.assertEqual(int(rows['label'].sum()), int(labels['label'].sum()))
        self.assertTrue(rows[['user_id', 'item_id']].equals(frame[['user_id', 'item_id']]))


class Rules(unittest.TestCase):
    def test_check_sql(self):
        check = xt.sql_rules()['check']
        for sql in ('SELECT user_id, item_id FROM ev WHERE t<400', 'SELECT 1 FROM ev WHERE 400>=t',
                    'SELECT 1 FROM ev WHERE {A} - 30 <= t', 'SELECT 1 FROM ev WHERE t = 5',
                    'SELECT 1 FROM ev WHERE t >= {B}', 'SELECT 1 FROM data_train', 'SELECT 1 FROM ev_all',
                    'SELECT user_id FROM test_users'):
            with self.assertRaises(ValueError, msg=sql):
                check(sql, 'pair')
        check('SELECT user_id, item_id, count(*) AS ag_n FROM ev WHERE t >= {A} - 30 GROUP BY ALL', 'pair')
        check('SELECT item_id, max({A} - t) AS ag_age FROM ev GROUP BY item_id LIMIT 20', 'item')
        with self.assertRaises(ValueError):
            check('SELECT item_id FROM cand', 'item')
        with self.assertRaises(ValueError):
            check('SELECT 1', 'customer')
        self.assertEqual(xt.substitute('t >= {A} - 30', 641), 't >= 641 - 30')

    def test_ranking_ties_and_rounding(self):
        scores = np.round(np.array([[0.3, 0.3 + 1e-12, 0.5, 0.0, 0.3]]), 9)
        ranks = xt.rank_by_score(scores, scores > 0)
        self.assertEqual(ranks.tolist(), [[2.0, 3.0, 1.0, math.inf, 4.0]])

    def test_metric_manual(self):
        targets = pd.DataFrame(dict(user_id=[1, 2, 3], n_targets=[2, 30, 1]))
        labels = pd.DataFrame(dict(user_id=[1, 1, 1, 2, 2], item_id=[10, 11, 12, 20, 21], label=[1, 0, 1, 1, 1]))
        ranked = pd.DataFrame(dict(user_id=[1, 1, 1, 2, 2], item_id=[11, 10, 12, 21, 20], rank=[1, 2, 3, 5, 25]))
        got = xt.metric(ranked, targets, labels).set_index('user_id')['value']
        idcg1 = 1 + 1/math.log2(3)
        self.assertAlmostEqual(got[1], (1/math.log2(3) + 1/math.log2(4))/idcg1)
        idcg2 = sum(1/math.log2(k+1) for k in range(1, 21))
        self.assertAlmostEqual(got[2], (1/math.log2(6))/idcg2)
        self.assertEqual(got[3], 0.0)
        self.assertEqual(list(got.index), [1, 2, 3])
        beyond = pd.concat([ranked, pd.DataFrame(dict(user_id=[2], item_id=[77], rank=[30]))])
        self.assertEqual(xt.metric(beyond, targets, labels)['value'].tolist(), got.tolist())
        unlabelled = pd.concat([ranked, pd.DataFrame(dict(user_id=[1], item_id=[77], rank=[4]))])
        foreign = pd.concat([ranked, pd.DataFrame(dict(user_id=[9], item_id=[1], rank=[1]))])
        for bad in (ranked.assign(rank=[1, 1, 3, 5, 6]), ranked.assign(item_id=[11, 11, 12, 21, 20]),
                    unlabelled, foreign):
            with self.assertRaises(xc.ContractError):
                xt.metric(bad, targets, labels)
        with self.assertRaises(xc.ContractError):
            xt.metric(ranked, targets.assign(n_targets=[0, 1, 1]), labels)

    def test_anchors_and_windows(self):
        info = xt.anchors()
        self.assertEqual((info['W'], info['N'], info['K'], info['holdout'], info['probe']), (30, 5000, 20, 671, 641))
        self.assertEqual(info['roles']['train'], [461, 491, 521, 551, 581, 611])
        self.assertEqual(info['series']['holdout']['train'], [461, 491, 521, 551, 581, 611, 641])
        self.assertEqual(info['series']['final']['train'], [521, 551, 581, 611, 641, 671])
        self.assertTrue(info['series']['final']['after_holdout'])
        self.assertEqual(info['series']['final']['arms'], ['B', 'BA'])
        roles = dict(info['roles'], val=[621])
        with self.assertRaises(xc.ContractError):
            xt._check_windows(roles, {}, 30)
        with self.assertRaises(xc.ContractError):
            xt._check_windows(dict(info['roles'], holdout=[661]), {}, 30)

    def test_base(self):
        base = xt.initial_base()
        self.assertEqual(len(base['features']), 17)
        self.assertEqual(base['categorical'], [])
        levels = [xt.feature_definition(f['name'], base['candidates']['sources'])['level'] for f in base['features']]
        self.assertEqual((levels.count('item'), levels.count('user'), levels.count('pair')), (7, 4, 6))
        bad = json.loads(json.dumps(base))
        bad['features'][0]['formula'] = 'something else'
        bad = xc.make_base('tinkoff', bad['candidates'], bad['features'], [])
        with self.assertRaises(xc.ContractError):
            xt._spec(bad)
        with self.assertRaises(xc.ContractError):
            xt.feature_definition('mystery', base['candidates']['sources'])

    def test_training_rows_need_labels(self):
        frame = pd.DataFrame(dict(user_id=[1, 1], item_id=[2, 3]))
        with self.assertRaises(xc.ContractError):
            xt.training_rows(frame, pd.DataFrame(dict(user_id=[1], item_id=[2], label=[1])), 461)


def numbers_in(value):
    found = set()
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        found.add(float(value))
    elif isinstance(value, str):
        found |= {float(x) for x in NUMBER.findall(value)}
    elif isinstance(value, dict):
        for k, v in value.items():
            found |= numbers_in(k) | numbers_in(v)
    elif isinstance(value, list):
        for v in value:
            found |= numbers_in(v)
    return found


class Prompt(EnvCase):
    def test_substitution_numbers_whitelist(self):
        with mock.patch.object(xt, 'PROBE_USERS', 20):
            pool = xt.probe_pool()
        stats = xt.probe_stats(641, pool, self.base)
        history = 'r1p1 ag_x [pair]: valid (2^3–2^4 rows)'
        budget = dict(pair_user_seconds=47.3, item_seconds=180.0)
        subs = xt.prompt_substitutions(stats, self.base, history, 2, budget)
        allowed = numbers_in(stats) | numbers_in(self.base) | numbers_in(xt.PROMPT_CONSTANTS) | {2.0, 40.0, 180.0, 3.0, 4.0}
        for key, value in subs.items():
            for token in NUMBER.findall(value):
                self.assertIn(float(token), allowed, f'{key}: {token}')
        load = xc.read_json(xc.output_dir('tinkoff', 'load', 'load.json'))
        tokens = {float(t) for value in subs.values() for t in NUMBER.findall(value)}
        # whole-table counters (they include the label windows) never reach the substitutions
        leaked = {float(load['facts'][k]) for k in ('rows', 'pairs')} - numbers_in(stats)
        self.assertFalse(tokens & leaked, 'load counters leaked')
        self.assertNotIn(f"0..{load['facts']['t_max']}", ' '.join(subs.values()))
        self.assertEqual(load['facts'], self.env.facts)
        prompt = xt.PROMPT_TEMPLATE.format(**subs)
        self.assertEqual(prompt, xt.render_prompt(stats, self.base, history, 2, budget))
        self.assertIn(xt.WARNING, prompt)
        self.assertIn('All valid columns will enter the model without selection. Superfluous and noisy columns hurt: '
                      'a few strong, non-redundant signals are needed. User-level columns work only through '
                      'interactions.', prompt)
        self.assertIn('an online store', prompt.lower())
        self.assertIn('t >= {A} - 30', prompt)
        self.assertIn('^ag_[a-z][a-z0-9_]{1,38}$', prompt)
        for word in ('tinkoff', 'kaggle', 'competition', 'data_train', 'test_users', 'baseline', '11047', '3178'):
            self.assertNotIn(word, prompt.lower())
        self.assertIn('about 40 s of 90 s', prompt)
        fields = {name for _, name, _, _ in string.Formatter().parse(xt.PROMPT_TEMPLATE) if name is not None}
        self.assertEqual(fields, set(subs))

    def test_prompt_digest_stable(self):
        self.assertEqual(xt.prompt_digest(), xt.prompt_digest())


class Static(unittest.TestCase):
    def tree(self):
        return ast.parse(Path(xt.__file__).read_text(encoding='utf-8'))

    def owners(self, predicate):
        tree = self.tree()
        top = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        found = set()
        for node in ast.walk(tree):
            if predicate(node):
                owner = [t.name for t in top if node in set(ast.walk(t))]
                found.add(owner[0] if owner else '<module>')
        return found

    def test_collect_holdout_purpose_only_in_collect(self):
        owners = self.owners(lambda n: isinstance(n, ast.Constant) and n.value == 'collect-holdout')
        self.assertEqual(owners, {'collect'})

    def test_write_sealed_and_events_path_owners(self):
        sealed = self.owners(lambda n: isinstance(n, ast.Attribute) and n.attr == 'write_sealed')
        self.assertEqual(sealed, {'collect'})
        events = self.owners(lambda n: isinstance(n, ast.Attribute) and n.attr == 'events_path')
        self.assertEqual(events, {'history', 'views', 'load'})
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn('sealed', node.value.lower())

    def test_prompt_names_nothing(self):
        text = xt.PROMPT_TEMPLATE.lower()
        for word in ('tinkoff', 'kaggle', 'competition', 'data_train', 'test_users', 'baseline'):
            self.assertNotIn(word, text)


class Cli(unittest.TestCase):
    def test_refuses_without_isolation(self):
        if os.sys.flags.isolated:
            self.skipTest('running isolated')
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = xt.main(['load'])
        self.assertEqual(code, 1)
        self.assertIn('python -I', json.loads(stream.getvalue())['error'])


class CliCollect(EnvCase):
    def test_collect_command(self):
        base_path = self.env.root/'base.json'
        base_path.write_text(json.dumps(self.base))
        users = self.env.root/'users.json'
        users.write_text(json.dumps(list(range(10))))
        out = self.out('smoke-cli')
        stream = io.StringIO()
        with mock.patch.object(xc, 'isolated', lambda: None), contextlib.redirect_stdout(stream):
            code = xt.main(['collect', '--dataset', 'tinkoff', '--role', 'probe', '--anchor', '641', '--base',
                            str(base_path), '--output', str(out), '--users-file', str(users)])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0, result)
        self.assertEqual(result['counts']['users'], 10)
        other = self.out('smoke-cli2')
        other.mkdir(parents=True)
        stream = io.StringIO()
        with mock.patch.object(xc, 'isolated', lambda: None), contextlib.redirect_stdout(stream), \
                mock.patch.object(xt, 'history', side_effect=AssertionError('history was read')):
            code = xt.main(['collect', '--role', 'probe', '--anchor', '641', '--base', str(base_path),
                            '--output', str(other)])
        self.assertEqual(code, 1)
        self.assertIn('exists', json.loads(stream.getvalue())['error'])


if __name__ == '__main__':
    unittest.main()
