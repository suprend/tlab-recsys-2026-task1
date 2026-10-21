"""council.xfer.sandbox on a synthetic world (council/runs/xfer/contract.md §3.4, §8.7, §8.9, §8.10).

The world lives in /tmp/tlab-council-test-*: an events parquet, collections train-100, train-110, probe-115,
val-120 and the C_test collection at 130 (frame.parquet + manifest.json), a fake adapter (xc.adapter is patched:
the real adapters never load in this process), a fake agent set and base names; queue.heavy is a recording
stub. DuckDB runs with 2 threads on a few hundred rows. Nothing under artifacts/ or council/runs/ is touched.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_xfer_sandbox -v
"""
import builtins
import contextlib
import io
import json
import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from council import evidence as ev
from council.xfer import queue, roles, sandbox
from scripts import xfer_agent as xa
from scripts import xfer_common as xc

TRAIN = (100, 110)
PROBE = 115
S0 = 120
TEST = 130
USERS = 40
ITEMS = 8
THREADS = 2
LEVEL_KEYS = {'pair': ['user_id', 'item_id'], 'user': ['user_id'], 'item': ['item_id']}

AGENT_SQL = ('SELECT e.user_id, count(*)::DOUBLE AS ag_ucnt FROM events e '
             'WHERE e.user_id IN (SELECT user_id FROM users) GROUP BY e.user_id')
USER_SQL = ('SELECT e.user_id, avg(e.value)::DOUBLE AS f_x_c1_uval FROM events e '
            'WHERE e.user_id IN (SELECT user_id FROM users) AND e.step >= {A} - 40 GROUP BY e.user_id')
USER_TWIN = ('SELECT e.user_id, avg(e.value * ((e.user_id * 7 + e.step) % 5))::DOUBLE AS f_x_c1_uval_tw '
             'FROM events e WHERE e.user_id IN (SELECT user_id FROM users) AND e.step >= {A} - 40 GROUP BY e.user_id')
PAIR_SQL = ('SELECT c.user_id, c.item_id, count(e.step)::DOUBLE AS f_x_c2_pcnt FROM cand c '
            'LEFT JOIN events e ON e.user_id = c.user_id AND e.item_id = c.item_id GROUP BY c.user_id, c.item_id')
PAIR_TWIN = ('SELECT c.user_id, c.item_id, count(e.step)::DOUBLE AS f_x_c2_pcnt_tw FROM cand c '
             'LEFT JOIN events e ON e.user_id = c.user_id AND (e.item_id + 3) % 8 = c.item_id '
             'GROUP BY c.user_id, c.item_id')
ITEM_SQL = 'SELECT e.item_id, count(*)::DOUBLE AS f_x_c3_ipop FROM events e GROUP BY e.item_id'
ITEM_TWIN = ('SELECT e.item_id, sum((e.user_id * 3 + e.step) % 4)::DOUBLE AS f_x_c3_ipop_tw FROM events e '
             'GROUP BY e.item_id')
TRAP = ('labels.parquet', 'targets.parquet')     # in every collection; reading one fails the test
BATCH_SQL = 'SELECT u.user_id, (SELECT count(*) FROM users)::DOUBLE AS ag_bad FROM users u'


def card(cid, name, level, sql, twin, sign='+'):
    return dict(id=cid, lens=cid.split('-')[0], name=name, level=level, mechanism='m', sign=sign, stratum='s',
                null_stratum='n', sql=sql, twin=dict(how='time_shuffle', sql=twin),
                rival=dict(explanation='e', stratum='r'))


CARDS = [card('G1-1', 'uval', 'user', USER_SQL, USER_TWIN), card('G2-1', 'pcnt', 'pair', PAIR_SQL, PAIR_TWIN),
         card('G3-1', 'ipop', 'item', ITEM_SQL, ITEM_TWIN)]


class FakeDataset(roles.Dataset):
    """roles.Dataset whose collections are the world's (anchors['_world'])."""

    def collection(self, phase, anchor=None):
        role = roles.COLLECTION_ROLES[phase]
        if anchor is None:
            anchor = {'select': self.s0_anchor, 'probe': self.probe_anchor, 'test': self.test_anchor}[phase]
        if xc.anchor_text(anchor) not in {xc.anchor_text(a) for a in self.anchors['roles'].get(role, [])}:
            raise ValueError(f'{anchor!r} is not an anchor of phase {phase}')
        return Path(self.anchors['_world']) / 'collections' / f'{role}-{anchor}'


REAL_BASE_NAMES = sandbox.base_names


class World:
    """The synthetic dataset and the patches that keep the test process off the real xfer data."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix='tlab-council-test-', dir='/tmp'))
        self.data = self.root / 'data'
        self.data.mkdir()
        rng = np.random.default_rng(5)
        n = 900
        events = pd.DataFrame({'user_id': rng.integers(1, USERS + 1, n).astype(np.int64),
                               'item_id': rng.integers(0, ITEMS, n).astype(np.int64),
                               'step': rng.integers(0, TEST, n).astype(np.int64),
                               'value': rng.normal(size=n)})
        self.events = self.data / 'events.parquet'
        xc.write_parquet(events, self.events)
        test_role = roles.COLLECTION_ROLES['test']
        self.anchors = {
            '_world': str(self.root), 'K': 2, 'probe': PROBE, 'probe_users': 12, test_role: TEST,
            'roles': {'train': list(TRAIN), 'val': [S0], test_role: [TEST], 'probe': [PROBE]},
            'series': {roles.SERIES['select']: {'train': list(TRAIN), 'eval': S0, 'eval_role': 'val'},
                       roles.SERIES['test']: {'train': [*TRAIN, S0], 'eval': TEST, 'eval_role': test_role}},
        }
        self.adapter = types.SimpleNamespace(LEVELS=LEVEL_KEYS, sql_rules=self.sql_rules, anchors=self.fake_anchors,
                                             views=self.views)
        self.ds = FakeDataset(name='tinkoff', adapter=self.adapter, anchors=self.anchors,
                              paths=roles.paths('tinkoff', self.root))
        self.collections = {}
        for role, anchor in [('train', a) for a in TRAIN] + [('probe', PROBE), ('val', S0), (test_role, TEST)]:
            self.collections[anchor] = self.make_collection(role, anchor)
        self.heavy_calls = []
        self.stack = contextlib.ExitStack()

    # ---------------------------------------------------------------- fake adapter
    def sql_rules(self):
        return {'forbidden': [], 'check': lambda sql, level: None}

    def fake_anchors(self):
        return {**self.anchors, roles.COLLECTION_ROLES['test']: TEST}

    def views(self, A, purpose):
        src = str(self.events).replace("'", "''")
        return {'files': [str(self.events)],
                'views': {'events': f"SELECT * FROM read_parquet('{src}') WHERE step < {int(A)}"},
                'levels': LEVEL_KEYS, 'items': f"SELECT DISTINCT item_id FROM read_parquet('{src}') "
                                                f"WHERE step < {int(A)}"}

    # ---------------------------------------------------------------- collections
    def make_collection(self, role, anchor):
        d = self.root / 'collections' / f'{role}-{anchor}'
        d.mkdir(parents=True)
        rows = [(u, i) for u in range(1, USERS + 1) for i in range(ITEMS) if (u * 3 + i + anchor) % 2 == 0]
        f = pd.DataFrame(rows, columns=['user_id', 'item_id']).astype('int64')
        f['f1'] = (f.user_id * 0.5 + f.item_id + anchor % 7).astype(float)
        f['f2'] = ((f.user_id * 13 + f.item_id * 5) % 11).astype('int32')
        f['cat'] = 'x' + (f.item_id % 3).astype(str)
        xc.write_parquet(f, d / xc.FRAME_FILE)
        manifest = {'anchor': anchor, 'files': {xc.FRAME_FILE: xc.sha256_file(d / xc.FRAME_FILE)},
                    'base_digest': 'b0', 'features': ['f1', 'f2', 'cat']}
        (d / xc.MANIFEST_FILE).write_text(json.dumps(manifest))
        for name in TRAP:                           # not parquet: DuckDB fails on it; Python reads are trapped
            (d / name).write_bytes(b'trap: the council never reads this file\n')
        return d

    # ---------------------------------------------------------------- patches
    @contextlib.contextmanager
    def heavy(self, what, dataset, **kw):
        self.heavy_calls.append((what, dataset, kw.get('log')))
        yield

    def trapped(self, fn):
        def f(path, *a, **k):
            if isinstance(path, (str, os.PathLike)) and Path(os.fspath(path)).name in TRAP:
                self.trap_hits.append(str(path))
                raise AssertionError(f'{path} was read')
            return fn(path, *a, **k)
        return f

    def __enter__(self):
        s = self.stack
        self.trap_hits = []
        self.ident = {'code': 'test'}
        for mod, name in ((xc, 'read_parquet'), (xc, 'read_json'), (xc, 'sha256_file'), (builtins, 'open'),
                          (io, 'open')):
            s.enter_context(mock.patch.object(mod, name, self.trapped(getattr(mod, name))))
        s.enter_context(mock.patch.object(xc, 'adapter', lambda dataset: self.adapter))
        s.enter_context(mock.patch.object(queue, 'heavy', self.heavy))
        s.enter_context(mock.patch.object(sandbox, 'identity', lambda ds: dict(self.ident)))
        s.enter_context(mock.patch.object(sandbox, 'agent_set', lambda ds: {
            'proposals': [dict(id='p1', level='user', sql=AGENT_SQL, columns=['ag_ucnt'])], 'columns': ['ag_ucnt']}))
        s.enter_context(mock.patch.object(sandbox, 'base_names', lambda ds, man: ['f1', 'f2']))
        s.enter_context(mock.patch.object(sandbox, 'THREADS', THREADS))
        s.enter_context(mock.patch.dict(sandbox._DATA, clear=True))
        return self

    def __exit__(self, *exc):
        self.stack.close()
        hits, self.trap_hits = self.trap_hits, []
        if hits:
            raise AssertionError(f'files of the trap were read: {hits}')
        if str(self.root).startswith('/tmp/tlab-council-test-'):
            shutil.rmtree(self.root, ignore_errors=True)
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self.w = World().__enter__()
        self.addCleanup(self.w.__exit__, None, None, None)
        self.ds = self.w.ds

    def data(self):
        return sandbox.probe_data(self.ds, THREADS)


class NamesAndChecks(Base):
    def test_to_sandbox(self):
        self.assertEqual(sandbox.to_sandbox('SELECT 1 AS f_x_c1_ab, 2 AS F_X_C1_AB_tw'),
                         'SELECT 1 AS ag_c1_ab, 2 AS ag_c1_ab_tw')
        with self.assertRaises(ValueError):
            sandbox.to_sandbox('SELECT 1 AS f_x_q')

    def test_check(self):
        self.assertIsNone(sandbox.check(self.ds, USER_SQL, 'user'))
        self.assertIn('forbidden', sandbox.check(self.ds, 'SELECT user_id, random() AS f_x_c1_a FROM users', 'user'))
        self.assertIn('item query', sandbox.check(self.ds, 'SELECT item_id, 1 AS f_x_c3_a FROM cand', 'item'))
        self.assertIn('placeholder', sandbox.check(self.ds, 'SELECT {B} AS f_x_c1_a', 'user'))

    def test_validate_card(self):
        for c in CARDS:
            self.assertEqual(sandbox.validate_card(self.ds, c), [], c['id'])
        bad = dict(CARDS[0], level='day', lens='G2', extra=1)
        got = ' | '.join(sandbox.validate_card(self.ds, bad))
        for part in ('unknown fields', 'lens', 'level'):
            self.assertIn(part, got)
        no_key = dict(CARDS[1], sql='SELECT u.user_id, 1.0 AS f_x_c2_pcnt FROM users u')
        self.assertTrue(any('no item_id key' in p for p in sandbox.validate_card(self.ds, no_key)))
        long_slug = 'f_x_c1_' + 'a' * 34
        twin_off = dict(CARDS[0], sql=USER_SQL.replace('f_x_c1_uval', long_slug),
                        twin=dict(how='time_shuffle', sql=USER_TWIN.replace('f_x_c1_uval_tw', long_slug + '_tw')))
        self.assertTrue(any('slug of 34' in p for p in sandbox.validate_card(self.ds, twin_off)))
        twin_bad = dict(CARDS[0], twin=dict(how='flip', sql=USER_SQL))
        got = ' | '.join(sandbox.validate_card(self.ds, twin_bad))
        self.assertIn('twin.how', got)
        self.assertIn('twin columns', got)

    def test_mask_anchors(self):
        obj = {'115': {'note': 'day 115 vs 110, not 110.5, 1.115 or 1150; probe-115/frame, ref-110.parquet',
                       'days': ['115', '110']}, 'n': 115}
        got = sandbox.mask_anchors(self.ds, obj)
        self.assertEqual(got, {'probe_day_1': {
            'note': 'day probe_day_1 vs probe_day_2, not 110.5, 1.115 or 1150; probe-probe_day_1/frame, '
                    'ref-probe_day_2.parquet', 'days': ['probe_day_1', 'probe_day_2']}, 'n': 115})

    def test_mask_in_the_views_of_a_real_probe_with_dates(self):
        """A card probe of this world, its anchors renamed to S dates, through council.agents.evidence_view with
        the xfer mask: no anchor text survives, in any of its forms."""
        from council import agents as A
        data = self.data()
        entry = sandbox.probe_card(self.ds, CARDS[1], data, THREADS)
        dates = {str(PROBE): '2020-08-05', str(TRAIN[-1]): '2020-07-29'}
        text = json.dumps(entry)
        for t, d in dates.items():
            text = text.replace(f'"{t}"', f'"{d}"')
        entry = json.loads(text)
        entry['card']['error'] = (f'2020-08-05: IO Error: /x/collections/probe-2020-08-05/frame.parquet '
                                  f'at 2020-08-05T00:00:00, train-2020-07-29')
        anchors = dict(self.anchors_s())
        ds_s = FakeDataset(name='tinkoff', adapter=self.ds.adapter, anchors=anchors, paths=self.ds.paths)
        self.assertEqual([xc.anchor_text(a) for a in ds_s.probe_anchors], ['2020-08-05', '2020-07-29'])
        ctx = types.SimpleNamespace(mask=lambda obj: sandbox.mask_anchors(ds_s, obj))
        views = [A.probe_view(entry['card'], ctx), A.evidence_view(entry, ctx), sandbox.mask_anchors(ds_s, entry)]
        for v in views:
            out = json.dumps(v)
            for d in ('2020-08-05', '2020-07-29', '20200805'):
                self.assertNotIn(d, out)
        self.assertIn('probe_day_1', json.dumps(views[0]))
        masked = views[2]['card']
        self.assertEqual(masked['days'], ['probe_day_1', 'probe_day_2'])
        self.assertEqual(sorted(masked['per_day']), ['probe_day_1', 'probe_day_2'])
        self.assertIn('probe-probe_day_1/frame.parquet at probe_day_1T00:00:00, train-probe_day_2', masked['error'])

    def anchors_s(self):
        import datetime as dt
        d = lambda t: dt.date.fromisoformat(t)
        test_role = roles.COLLECTION_ROLES['test']
        return {'K': 2, 'probe': d('2020-08-05'), 'probe_users': 12,
                'roles': {'train': [d('2020-07-22'), d('2020-07-29')], 'val': [d('2020-08-19')],
                          test_role: [d('2020-09-02')], 'probe': [d('2020-08-05')]},
                'series': {roles.SERIES['select']: {'train': [d('2020-07-22'), d('2020-07-29')],
                                                    'eval': d('2020-08-19'), 'eval_role': 'val'},
                           roles.SERIES['test']: {'train': [d('2020-07-22'), d('2020-07-29'), d('2020-08-19')],
                                                  'eval': d('2020-09-02'), 'eval_role': test_role}}}

    def test_reserved_base_names(self):
        base = {'digest': 'b0', 'features': [{'name': 'f1'}, {'name': 'label'}], 'categorical': []}
        with mock.patch.object(xc, 'read_base', lambda x: base):
            with self.assertRaises(xc.ContractError) as e:
                REAL_BASE_NAMES(self.ds, {'base_digest': 'b0'})
        self.assertIn('reserved', str(e.exception))
        with mock.patch.object(sandbox, 'base_names', lambda ds, man: ['f1', 'ag_x1']):
            with self.assertRaises(xc.ContractError) as e:
                sandbox.probe_frame(self.ds, PROBE, THREADS)
        self.assertIn('reserved', str(e.exception))

    def test_trap_is_armed(self):
        coll = self.w.collections[PROBE]
        for name in TRAP:
            with self.assertRaises(AssertionError):
                xc.read_parquet(coll / name)
            with self.assertRaises(AssertionError):
                (coll / name).read_bytes()
        self.w.trap_hits.clear()


class ProbeData(Base):
    def test_rows_reference_and_cache(self):
        data = self.data()
        self.assertEqual([d['anchor'] for d in data], [PROBE, TRAIN[-1]])
        self.assertEqual(len(self.w.heavy_calls), 2)
        self.assertTrue(all(c[0].startswith('probe reference') and c[1] == 'tinkoff' for c in self.w.heavy_calls))
        for d in data:
            self.assertEqual(d['names'], ['f1', 'f2', 'ag_ucnt'])
            self.assertEqual(list(d['cohort']), xc.cap_queries(d['cohort'], None))
            self.assertEqual(len(d['cohort']), 12)
            self.assertTrue(np.all(np.diff(d['q']) >= 0))
            first = xc.cap_queries(range(1, USERS + 1), None)
            coll = self.w.collections[d['anchor']]
            users = set(xc.read_parquet(coll / xc.FRAME_FILE)['user_id'])
            self.assertEqual(list(d['cohort']), [u for u in first if u in users][:12])
            self.assertEqual(d['ranks'].dtype, np.float32)
            ref = xc.read_parquet(self.ds.paths.probe_ref(d['anchor']))
            self.assertEqual(list(ref.columns), ['user_id', 'item_id', 'f1', 'f2', 'ag_ucnt'])
        sandbox._DATA.clear()
        with mock.patch.object(xa, 'agent_columns', side_effect=AssertionError('recomputed')):
            again = self.data()
        self.assertEqual(len(self.w.heavy_calls), 2)
        for a, b in zip(data, again):
            pd.testing.assert_frame_equal(a['ref'], b['ref'])

    def test_reference_values(self):
        d = self.data()[0]
        ev_ = xc.read_parquet(self.w.events)
        ev_ = ev_[ev_.step < PROBE]
        counts = ev_.groupby('user_id').size()
        exp = counts.reindex(d['keys']['user_id']).to_numpy(dtype=float)
        np.testing.assert_allclose(d['ref']['ag_ucnt'].to_numpy(), exp)


class Probes(Base):
    def test_levels(self):
        data = self.data()
        for c, level in zip(CARDS, ('user', 'pair', 'item')):
            sql = sandbox.to_sandbox(c['sql'])
            p = sandbox.probe(self.ds, sql, level, data, THREADS)
            self.assertIsNone(p['error'] or p['check'] or p['nondeterministic'], level)
            self.assertEqual(p['days'], [str(PROBE), str(TRAIN[-1])])
            self.assertEqual(p['keys'], LEVEL_KEYS[level])
            self.assertEqual(p['columns'], [roles.sandbox_column(sandbox.TOKEN.findall(c['sql'])[0])])
            self.assertEqual(ev.machine_red(p), [], level)
            self.assertEqual(p['batch_invariant'], None if level == 'item' else True)
            self.assertTrue(p['parity']['ok'])
            self.assertEqual(p['identity'], {'code': 'test'})
            vals = xc.read_parquet(self.ds.paths.probes / p['values'])
            self.assertEqual(list(vals.columns), ['anchor', 'user_id', 'item_id'] + p['columns'])
            self.assertEqual(len(vals), sum(len(d['keys']) for d in data))
        # values of the pair card at the probe anchor
        p = sandbox.probe(self.ds, sandbox.to_sandbox(PAIR_SQL), 'pair', data, THREADS)
        vals = xc.read_parquet(self.ds.paths.probes / p['values'])
        vals = vals[vals.anchor == str(PROBE)]
        e = xc.read_parquet(self.w.events)
        e = e[e.step < PROBE].groupby(['user_id', 'item_id']).size()
        exp = [e.get((u, i), 0) for u, i in zip(vals.user_id, vals.item_id)]
        np.testing.assert_allclose(vals['ag_c2_pcnt'].to_numpy(), exp)

    def test_failures_are_recorded(self):
        data = self.data()
        p = sandbox.probe(self.ds, 'SELECT user_id, random() AS ag_c1_r FROM users', 'user', data, THREADS)
        self.assertIn('forbidden', p['check'])
        self.assertTrue(ev.machine_red(p))
        p = sandbox.probe(self.ds, 'SELECT e.user_id, 1.0 AS ag_c1_r FROM events e', 'user', data, THREADS)
        self.assertIn('duplicate keys', p['error'])
        self.assertIsNone(p['values'])
        p = sandbox.probe(self.ds, BATCH_SQL, 'user', data, THREADS)
        self.assertIs(p['batch_invariant'], False)
        self.assertTrue(any(r.startswith('batch') for r in ev.machine_red(p)))

    def test_cache(self):
        data = self.data()
        sql = sandbox.to_sandbox(USER_SQL)
        p = sandbox.probe(self.ds, sql, 'user', data, THREADS)
        path = sandbox.probe_path(self.ds, sql, 'user')
        self.assertTrue(path.exists())
        with mock.patch.object(sandbox, 'run_sql', side_effect=AssertionError('ran again')):
            self.assertEqual(sandbox.probe(self.ds, sql, 'user', data, THREADS), p)
        self.assertNotEqual(sandbox.probe_path(self.ds, sql, 'pair'), path)
        self.w.ident = {'code': 'changed'}                     # another code: the cached probe is not reused
        runs = []
        real = sandbox.run_sql
        with mock.patch.object(sandbox, 'run_sql', lambda *a, **k: runs.append(1) or real(*a, **k)):
            q = sandbox.probe(self.ds, sql, 'user', data, THREADS)
        self.assertEqual(len(runs), 2)
        self.assertEqual(q['identity'], {'code': 'changed'})
        other = [dict(d, keys_sha256='0' * 64) for d in data]   # other probe keys: not reused either
        with mock.patch.object(sandbox, 'run_sql', lambda *a, **k: runs.append(1) or real(*a, **k)):
            sandbox.probe(self.ds, sql, 'user', other, THREADS)
        self.assertEqual(len(runs), 4)

    def test_technical_failures_are_raised_timeouts_not_cached(self):
        import duckdb
        data = self.data()
        sql = sandbox.to_sandbox(USER_SQL)
        path = sandbox.probe_path(self.ds, sql, 'user')
        for exc in (duckdb.IOException('IO Error: disk'), KeyboardInterrupt()):
            with mock.patch.object(xa, '_execute', side_effect=exc):
                with self.assertRaises(type(exc)):
                    sandbox.probe(self.ds, sql, 'user', data, THREADS)
            self.assertFalse(path.exists())
        with mock.patch.object(xa, 'sandbox', side_effect=ValueError('Batch keys must be unique non-NULL pairs')):
            with self.assertRaises(ValueError):
                sandbox.probe(self.ds, sql, 'user', data, THREADS)
        self.assertFalse(path.exists())
        with mock.patch.object(xa, '_execute', side_effect=xa.ProposalError('timeout after 20 s')):
            p = sandbox.probe(self.ds, sql, 'user', data, THREADS)
        self.assertIn('timeout after 20 s', p['error'])
        self.assertFalse(path.exists())
        p = sandbox.probe(self.ds, sql, 'user', data, THREADS)
        self.assertIsNone(p['error'])
        self.assertTrue(path.exists())

    def test_reference_cache_follows_identity_and_set(self):
        self.data()
        self.assertEqual(len(self.w.heavy_calls), 2)
        sandbox._DATA.clear()
        self.w.ident = {'code': 'changed'}
        self.data()
        self.assertEqual(len(self.w.heavy_calls), 4)
        stamp = json.loads(self.ds.paths.probe_ref(PROBE).with_suffix('.json').read_text())
        self.assertEqual(stamp['identity'], {'code': 'changed'})
        sandbox._DATA.clear()
        other = {'proposals': [dict(id='p1', level='user', sql=AGENT_SQL + ' ', columns=['ag_ucnt'])],
                 'columns': ['ag_ucnt']}
        with mock.patch.object(sandbox, 'agent_set', lambda ds: other):
            self.data()
        self.assertEqual(len(self.w.heavy_calls), 6)

    def test_values_match_compute(self):
        """The probe of a card and compute.py on the same keys (the last train collection) give the same values."""
        from council.xfer import compute
        data = self.data()
        for c in CARDS:
            sql = sandbox.to_sandbox(c['sql'])
            p = sandbox.probe(self.ds, sql, c['level'], data, THREADS)
            vals = xc.read_parquet(self.ds.paths.probes / p['values'])
            vals = vals[vals.anchor == str(TRAIN[-1])].drop(columns='anchor')
            coll = self.w.collections[TRAIN[-1]]
            entry = dict(table=roles.family_table(c['id']), level=c['level'], sql=sql, columns=p['columns'])
            got, _ = compute.compute_table(self.ds, TRAIN[-1], compute.frame_keys(coll), entry, {}, threads=THREADS)
            m = vals.merge(got, on=['user_id', 'item_id'], suffixes=('_probe', ''))
            self.assertEqual(len(m), len(vals))
            col = p['columns'][0]
            np.testing.assert_allclose(m[col + '_probe'].to_numpy(dtype=float), m[col].to_numpy(dtype=float),
                                       rtol=1e-6, equal_nan=True)

    def test_card_twin_and_cross(self):
        data = self.data()
        with mock.patch.object(ev, 'MIN_ROWS', 5), mock.patch.object(ev, 'MIN_QUERIES', 3):
            out = sandbox.probe_card(self.ds, CARDS[1], data, THREADS)
            self.assertEqual(out['problems'], [])
            self.assertEqual(out['twin']['columns'], ['ag_c2_pcnt_tw'])
            tc = out['twin_check']                           # the twin counts another item: unrelated
            self.assertEqual(tc['verdict'], 'ok', tc)
            self.assertLess(abs(tc['columns']['ag_c2_pcnt']['rho']), ev.TWIN_RHO)
            copy = dict(CARDS[1], twin=dict(how='time_shuffle', sql=PAIR_SQL.replace('f_x_c2_pcnt', 'f_x_c2_pcnt_tw')))
            tc = sandbox.probe_card(self.ds, copy, data, THREADS)['twin_check']
            self.assertEqual(tc['verdict'], 'TWIN-BROKEN')
            self.assertEqual(tc['reasons'], ['ag_c2_pcnt: |rho_wq| with the twin 1.000 > 0.8'])
            sparse = dict(CARDS[1], twin=dict(how='time_shuffle', sql=(
                'SELECT c.user_id, c.item_id, CASE WHEN c.item_id = 0 THEN 1.0 END AS f_x_c2_pcnt_tw FROM cand c')))
            tc = sandbox.probe_card(self.ds, sparse, data, THREADS)['twin_check']
            self.assertEqual(tc['verdict'], 'TWIN-BROKEN')
            self.assertTrue(any('coverage 1.0000, twin 0.' in r for r in tc['reasons']), tc)
            same = sandbox.cross(self.ds, out['card'], out['card'])
            self.assertEqual(same['max_abs_rho'], 1.0)
            self.assertEqual(same['mode'], 'within')
            u = sandbox.probe_card(self.ds, CARDS[0], data, THREADS)
            self.assertEqual(sandbox.cross(self.ds, out['card'], u['card'])['mode'], 'between')
        bad = dict(CARDS[0], sql=USER_SQL.replace('f_x_c1_uval', 'f_x_c2_uval'))
        self.assertTrue(any('ag_c1_<slug>' in p or 'f_x_c1_<slug>' in p
                            for p in sandbox.probe_card(self.ds, bad, data, THREADS)['problems']))


class Stage(Base):
    def test_merge_and_gate(self):
        path = self.ds.paths.run_file('probes.json')
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'cards': {'G4-9': {'id': 'G4-9'}}, 'reference': {}}))
        answers = iter([['heavy step'], ['heavy step'], [], [], [], [], [], []])
        slept = []
        refs = {1: [dict(table='rb1_ucnt', level='user', sql=AGENT_SQL.replace('ag_ucnt', 'ag_rb1_ucnt'),
                         columns=['ag_rb1_ucnt'])]}
        store = sandbox.probe_stage(self.ds, CARDS[:2], refs, gate=lambda: next(answers), threads=THREADS,
                                    poll=0.5, sleep=slept.append)
        self.assertEqual(slept, [0.5, 0.5])
        self.assertEqual(sorted(store['cards']), ['G1-1', 'G2-1', 'G4-9'])
        self.assertEqual(list(store['reference']), ['rb1_ucnt'])
        self.assertEqual(json.loads(path.read_text()), store)
        self.assertTrue(path.read_text().endswith('\n'))

    def test_another_writer_keeps_its_entries(self):
        path = self.ds.paths.run_file('probes.json')
        path.parent.mkdir(parents=True)
        n = [0]

        def gate():                                     # another writer adds an entry while the stage runs
            n[0] += 1
            if n[0] == 2:
                store = json.loads(path.read_text())
                store['cards']['G4-7'] = {'id': 'G4-7'}
                path.write_text(json.dumps(store))
            return []
        store = sandbox.probe_stage(self.ds, CARDS[:2], None, gate=gate, threads=THREADS)
        self.assertEqual(sorted(store['cards']), ['G1-1', 'G2-1', 'G4-7'])

    def test_gate_none_never_waits(self):
        self.assertEqual(sandbox.wait_gate(None, 1.0, sleep=lambda s: self.fail('slept')), 0)


if __name__ == '__main__':
    unittest.main()
