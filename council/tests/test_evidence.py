"""council.evidence: probes on a small synthetic event base, the verdicts, the curator and one real smoke run.

Run: TASK1_PERIOD=2020 .venv/bin/python -m unittest council.tests.test_evidence -v"""
import json
import random
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from council import evidence as E
from council import roles
from task1 import extra as X

def _write(df, path):
    con = duckdb.connect()
    con.register('df_', df)
    cast = 'anchor::DATE AS anchor, * EXCLUDE (anchor)' if 'anchor' in df.columns else '*'
    con.execute(f"COPY (SELECT {cast} FROM df_) TO '{path}' (FORMAT PARQUET)")
    con.close()


def _read(path, columns='*'):
    return duckdb.sql(f"SELECT {columns} FROM read_parquet('{path}')").df()


DAYS = ('2020-01-05', '2020-01-06', '2020-01-07')
USERS, PRODUCTS, CANDIDATES = 240, 200, 25
I_Y = '(product_id % 7) + 0.1 * (product_id % 3)'


def _events(root):
    rng = np.random.default_rng(7)
    for d in pd.date_range('2020-01-01', '2020-01-07'):
        rows = []
        for u in range(1, USERS + 1):
            for k in range(3):
                p = int(rng.integers(1, PRODUCTS + 1))
                rows.append(dict(event_time=d + pd.Timedelta(minutes=int(rng.integers(0, 1440))),
                                 event_type=['view', 'view', 'cart', 'purchase'][int(rng.integers(0, 4))],
                                 product_id=p, category_id=p % 10, category_code=f'c{p % 10}', brand=f'b{p % 5}',
                                 price=float(p), user_id=u, user_session=f's{u}-{d.day}'))
        for p in range(1, PRODUCTS + 1):  # every product appears every day
            rows.append(dict(event_time=d + pd.Timedelta(hours=1), event_type='view', product_id=p,
                             category_id=p % 10, category_code=f'c{p % 10}', brand=f'b{p % 5}', price=float(p),
                             user_id=1, user_session=f's1-{d.day}'))
        out = root / 'events_by_day' / f'd={d.date()}'
        out.mkdir(parents=True)
        df = pd.DataFrame(rows)
        df['event_time'] = df.event_time.astype('datetime64[us]')
        _write(df, out / 'part.parquet')


def _days6(root):
    rng = np.random.default_rng(11)
    (root / 'days6').mkdir()
    for t in ('tp', 'tu'):
        (root / 'extra' / t).mkdir(parents=True)
    hidden = 'lab' + 'el'
    for day in DAYS:
        rows = []
        for u in range(1, 201):
            for p in sorted(rng.choice(np.arange(1, PRODUCTS + 1), CANDIDATES, replace=False)):
                rows.append((u, int(p)))
        df = pd.DataFrame(rows, columns=['user_id', 'product_id'])
        df.insert(0, 'anchor', pd.Timestamp(day))
        df[hidden] = 0
        df['s_pop_rank'] = (df.product_id * 37) % 101
        df['i_y'] = (df.product_id % 7) + 0.1 * (df.product_id % 3)
        df['u_z'] = (df.user_id % 5).astype(float)
        df['i_cat_l1'] = 'c' + (df.product_id % 10).astype(str)
        _write(df, root / 'days6' / f'{day}.parquet')
        _write(pd.DataFrame({'product_id': np.arange(1, PRODUCTS + 1),
                             'f_x_tp_a': np.sin(np.arange(1, PRODUCTS + 1) * 1.7)}),
               root / 'extra' / 'tp' / f'{day}.parquet')
        _write(pd.DataFrame({'user_id': np.arange(1, USERS + 1),
                             'f_x_tu_b': (np.arange(1, USERS + 1) * 0.37) % 1}),
               root / 'extra' / 'tu' / f'{day}.parquet')


class Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix='tlab-evidence-test-'))
        _events(cls.root)
        _days6(cls.root)
        cls.patches = [mock.patch.object(X, 'EVENTS', cls.root / 'events_by_day'),
                       mock.patch.object(E, 'DAYS6', cls.root / 'days6'),
                       mock.patch.object(E, 'EXTRA', cls.root / 'extra'),
                       mock.patch.object(E, 'PROBES', cls.root / 'probes'),
                       mock.patch.object(E, 'TABLES', ['tp', 'tu'])]
        for p in cls.patches:
            p.start()
        E._CTX.clear()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        E._CTX.clear()
        shutil.rmtree(cls.root, ignore_errors=True)

    def probe(self, sql):
        return E.probe(sql, days=DAYS, threads=2)

    # ---------------------------------------------------------------- probe

    def test_coverage_is_share_of_candidate_rows(self):
        p = self.probe('SELECT DISTINCT product_id, 1.0 AS f_x_c2_even FROM hist WHERE product_id % 2 = 0')
        self.assertEqual(E.machine_red(p), [])
        self.assertEqual(p['level'], 'product')
        self.assertIsNone(p['batch_invariant'])
        for d in DAYS:
            c = _read(self.root / 'days6' / f'{d}.parquet', 'product_id')
            self.assertAlmostEqual(p['per_day'][d]['coverage']['f_x_c2_even'], (c.product_id % 2 == 0).mean(), places=5)
            self.assertEqual(p['per_day'][d]['candidate_rows'], len(c))
            self.assertEqual(p['per_day'][d]['rows'], PRODUCTS // 2)
        self.assertTrue(p['parity']['ok'])

    def test_rho_and_r2_find_a_copy_of_the_base(self):
        p = self.probe(f'SELECT DISTINCT product_id, {I_Y} AS f_x_c2_copy FROM hist')
        self.assertEqual(p['nearest']['f_x_c2_copy'], 'i_y')
        self.assertGreater(p['max_abs_rho']['f_x_c2_copy'], 0.999)
        self.assertGreater(p['r2']['f_x_c2_copy'], 0.99)
        refs = p['per_day'][DAYS[0]]['stats']['f_x_c2_copy']['rho']
        self.assertEqual(set(refs), {'s_pop_rank', 'i_y', 'f_x_tp_a'})  # u_z, f_x_tu_b: constant inside a query
        self.assertEqual(p['per_day'][DAYS[0]]['sample']['references'], 5)  # i_cat_l1 is not numeric

        noise = self.probe('SELECT DISTINCT product_id, (hash(product_id, 99) % 1000)::DOUBLE AS f_x_c2_noise FROM hist')
        self.assertLess(noise['max_abs_rho']['f_x_c2_noise'], 0.5)
        self.assertLess(noise['r2']['f_x_c2_noise'], 0.3)

    def test_user_level_uses_between_queries(self):
        p = self.probe('SELECT user_id, (user_id % 5)::DOUBLE AS f_x_c1_uz FROM active_users')
        s = p['per_day'][DAYS[0]]['stats']['f_x_c1_uz']
        self.assertEqual(s['mode'], 'between')
        self.assertEqual(s['nearest'], 'u_z')
        self.assertGreater(s['max_abs_rho'], 0.999)

    def test_rho_skips_nulls_pairwise(self):
        p = self.probe(f'SELECT DISTINCT product_id, {I_Y} AS f_x_c2_part FROM hist WHERE product_id % 3 = 0')
        self.assertLess(p['coverage']['f_x_c2_part'], 0.5)
        self.assertGreater(p['max_abs_rho']['f_x_c2_part'], 0.999)  # NULL rows do not count against rho

    def test_batch_invariance(self):
        bad = self.probe('SELECT user_id, (SELECT count(*) FROM active_users)::DOUBLE AS f_x_c1_n FROM active_users')
        self.assertIs(bad['batch_invariant'], False)
        self.assertTrue(any(r.startswith('batch') for r in E.machine_red(bad)))
        good = self.probe('SELECT h.user_id, count(*)::DOUBLE AS f_x_c1_ev FROM hist h JOIN active_users a '
                          'ON h.user_id = a.user_id GROUP BY h.user_id')
        self.assertIs(good['batch_invariant'], True)
        self.assertEqual(E.machine_red(good), [])
        b = good['per_day'][DAYS[0]]['batch']
        self.assertEqual((b['key_mismatches'], b['value_mismatches'], b['reason']), (0, 0, None))
        self.assertGreater(b['checked'], 100)
        pair = self.probe('SELECT h.user_id, h.product_id, count(*)::DOUBLE AS f_x_c3_n FROM hist h '
                          'JOIN active_users a ON h.user_id = a.user_id GROUP BY 1, 2')
        self.assertEqual(pair['level'], 'pair')
        self.assertIs(pair['batch_invariant'], True)
        pair_bad = self.probe('SELECT h.user_id, h.product_id, count(*)::DOUBLE / (SELECT count(*) FROM active_users) '
                              'AS f_x_c3_n FROM hist h JOIN active_users a ON h.user_id = a.user_id GROUP BY 1, 2')
        self.assertIs(pair_bad['batch_invariant'], False)
        self.assertIn('values differ', pair_bad['per_day'][DAYS[0]]['batch']['reason'])
        self.assertEqual(bad['per_day'][DAYS[0]]['batch']['key_mismatches'], 0)
        self.assertGreater(bad['per_day'][DAYS[0]]['batch']['value_mismatches'], 0)

    def test_batch_keys_differ_and_tolerance(self):
        keys = self.probe('SELECT DISTINCT user_id, 1.0 AS f_x_c1_k FROM hist WHERE user_id IN '
                          '(SELECT user_id FROM active_users ORDER BY user_id LIMIT 50)')
        b = keys['per_day'][DAYS[0]]['batch']
        self.assertIs(keys['batch_invariant'], False)
        self.assertGreater(b['key_mismatches'], 0)
        self.assertEqual(b['value_mismatches'], 0)
        self.assertIn('keys differ', b['reason'])
        self.assertNotIn('values differ', b['reason'])
        tiny = self.probe('SELECT user_id, 1e-12 * (SELECT count(*) FROM active_users) AS f_x_c1_tiny FROM active_users')
        self.assertIs(tiny['batch_invariant'], True)        # absolute 1e-9 for small values
        huge = self.probe('SELECT user_id, 1e12 + (SELECT count(*) FROM active_users) AS f_x_c1_huge FROM active_users')
        self.assertIs(huge['batch_invariant'], True)        # relative 1e-9 for large values
        near = self.probe('SELECT user_id, 1e-6 * (SELECT count(*) FROM active_users) AS f_x_c1_near FROM active_users')
        self.assertIs(near['batch_invariant'], False)

    def test_nondeterministic_and_invalid_are_red_without_running(self):
        p = self.probe('SELECT DISTINCT product_id, random() AS f_x_c2_r FROM hist')
        self.assertEqual(p['nondeterministic'], 'random')
        self.assertEqual(p['per_day'], {})
        self.assertTrue(E.machine_red(p))
        q = self.probe('SELECT product_id, 1.0 AS f_x_c2_r FROM events')
        self.assertIn('forbidden', q['check'])
        self.assertTrue(E.machine_red(q))
        r = self.probe('SELECT product_id, nonexistent AS f_x_c2_r FROM hist')
        self.assertTrue(r['error'])
        self.assertTrue(E.machine_red(r))

    def test_cache(self):
        sql = 'SELECT DISTINCT product_id, (product_id % 4)::DOUBLE AS f_x_c2_cache FROM hist'
        p = self.probe(sql)
        path = E.probe_path(sql)
        self.assertEqual(path.name, E._sha(sql)[:16] + '.json')
        self.assertEqual(json.loads(path.read_text()), p)
        mtime = path.stat().st_mtime_ns
        with mock.patch.object(E, '_probe_day', side_effect=AssertionError('recomputed')):
            self.assertEqual(self.probe(sql), p)
        self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_twin(self):
        card = f'SELECT DISTINCT product_id, {I_Y} AS f_x_c2_v FROM hist'
        shuffled = (f'WITH v AS (SELECT DISTINCT product_id, {I_Y} AS f_x_c2_v FROM hist), '
                    'r AS (SELECT product_id, f_x_c2_v, row_number() OVER (ORDER BY hash(product_id, 7)) rn, '
                    'row_number() OVER (ORDER BY product_id) rk FROM v) '
                    'SELECT a.product_id, b.f_x_c2_v AS f_x_c2_v_tw FROM r a JOIN r b ON a.rk = b.rn')
        same = f'SELECT DISTINCT product_id, {I_Y} AS f_x_c2_v_tw FROM hist'
        sparse = f'SELECT DISTINCT product_id, {I_Y} AS f_x_c2_v_tw FROM hist WHERE product_id % 2 = 0'
        pc = self.probe(card)
        ok = E.twin_check(pc, self.probe(shuffled))
        self.assertEqual(ok['verdict'], 'ok', ok)
        self.assertLess(abs(ok['columns']['f_x_c2_v']['rho']), 0.8)
        broken = E.twin_check(pc, self.probe(same))
        self.assertEqual(broken['verdict'], 'TWIN-BROKEN')
        self.assertIn('rho_wq', broken['reasons'][0])
        thin = E.twin_check(pc, self.probe(sparse))
        self.assertEqual(thin['verdict'], 'TWIN-BROKEN')
        self.assertTrue(any('coverage' in r for r in thin['reasons']))
        wrong = E.twin_check(pc, self.probe('SELECT DISTINCT product_id, 1.0 AS f_x_c2_w_tw FROM hist'))
        self.assertEqual(wrong['verdict'], 'TWIN-BROKEN')

        full = E.probe(dict(_card('G2-1', ['f_x_c2_v'], card=card, twin=shuffled)), days=DAYS, threads=2)
        self.assertEqual(full['problems'], [])
        self.assertEqual(full['twin_check']['verdict'], 'ok')

    def test_cross_inside_council(self):
        a = self.probe(f'SELECT DISTINCT product_id, {I_Y} AS f_x_c2_a FROM hist')
        b = self.probe(f'SELECT DISTINCT product_id, 2 * ({I_Y}) + 1 AS f_x_c3_b FROM hist')
        cr = E.cross(a, b)
        self.assertGreater(cr['max_abs_rho'], 0.999)
        self.assertGreater(cr['r2_a_on_b']['f_x_c2_a'], 0.99)


# ---------------------------------------------------------------- pure functions

def _card(cid, cols, card=None, twin=None):
    lens = cid.split('-')[0]
    sel = ', '.join(f'1.0 AS {c}' for c in cols)
    tsel = ', '.join(f'1.0 AS {c}_tw' for c in cols)
    return dict(id=cid, lens=lens, name=f'card_{cid.lower().replace("-", "_")}', mechanism='m', sign='+',
                stratum='s', null_stratum='n', sql=card or f'SELECT DISTINCT product_id, {sel} FROM hist',
                twin=dict(how='time_shuffle', sql=twin or f'SELECT DISTINCT product_id, {tsel} FROM hist'),
                rival=dict(explanation='r', stratum='s'))


def _sql_probe(cols, coverage=0.3, r2=0.1, rho=0.2, seconds=1.0, days=DAYS, shares=None, red=None):
    per_day = {d: dict(seconds=seconds, coverage={c: (shares or {}).get(d, coverage) for c in cols}, batch=None)
               for d in days}
    p = dict(days=list(days), columns=list(cols), level='product', per_day=per_day, check=red, nondeterministic=None,
             error=None, batch_invariant=None, seconds_median=seconds, coverage={c: coverage for c in cols},
             r2={c: r2 for c in cols}, max_abs_rho={c: rho for c in cols}, nearest={c: 'i_y' for c in cols})
    p['parity'] = E.parity(p)
    return p


def _probes(cards, twin_ok=lambda cid: True, **kw):
    out = {}
    for c in cards:
        cols = c['_cols']
        out[c['id']] = dict(problems=[], card=_sql_probe(cols, **kw.get(c['id'], {})),
                            twin=None, twin_check=dict(verdict='ok' if twin_ok(c['id']) else 'TWIN-BROKEN'))
    return out


def _deck(per_lens=5, cols=1):
    cards = []
    for lens in E.LENSES:
        for n in range(1, per_lens + 1):
            cid = f'{lens}-{n}'
            names = [f'f_x_c{lens[1]}_k{n}_{j}' for j in range(cols)]
            c = _card(cid, names)
            c['_cols'] = names
            cards.append(c)
    return cards


def _strip(cards):
    return [{k: v for k, v in c.items() if k != '_cols'} for c in cards]


def no_cross(a, b):
    return None


class Pure(unittest.TestCase):
    def test_parity(self):
        p = _sql_probe(['f_x_c1_a'], shares={'2020-01-05': 0.2, '2020-01-06': 0.25, '2020-01-07': 0.39})
        self.assertTrue(E.parity(p)['ok'])
        p = _sql_probe(['f_x_c1_a'], shares={'2020-01-05': 0.2, '2020-01-06': 0.25, '2020-01-07': 0.6})
        par = E.parity(p)
        self.assertFalse(par['ok'])
        self.assertEqual(par['columns']['f_x_c1_a']['outside'], ['2020-01-07'])
        p = _sql_probe(['f_x_c1_a'], shares={'2020-01-05': 0.04, '2020-01-06': 0.1, '2020-01-07': 0.1})
        self.assertEqual(E.parity(p)['columns']['f_x_c1_a']['outside'], ['2020-01-05'])

    def test_rho_grouped_centres_inside_queries(self):
        rng = np.random.default_rng(0)
        q = np.repeat(np.arange(200), 10)
        x = rng.normal(size=len(q))
        offset = np.repeat(rng.normal(size=200) * 100, 10)
        r = np.c_[x + offset, offset, -x]
        rho = E.rho_grouped(x, r, E._starts(q), 100)
        np.testing.assert_allclose(rho[[0, 2]], [1, -1], atol=1e-9)
        self.assertTrue(np.isnan(rho[1]))  # constant inside every query
        self.assertAlmostEqual(E.r2_grouped(x, r, q, 100), 1.0, places=9)
        y = x.copy()
        y[::3] = np.nan
        self.assertAlmostEqual(E.rho_grouped(y, r, E._starts(q), 100)[0], 1.0, places=9)

    def test_validate_card(self):
        good = _card('G3-2', ['f_x_c3_seed', 'f_x_c3_seed_age'])
        self.assertEqual(E.validate_card(good), [])
        self.assertTrue(E.validate_card(_card('G3-2', ['f_x_c1_seed'])))       # wrong lens digit
        self.assertTrue(E.validate_card(_card('G3-2', [f'f_x_c3_k{i}' for i in range(5)])))
        bad = _card('G3-2', ['f_x_c3_seed'])
        bad['twin']['sql'] = 'SELECT DISTINCT product_id, 1.0 AS f_x_c3_other_tw FROM hist'
        self.assertTrue(any('twin columns' in p for p in E.validate_card(bad)))
        bad = _card('G3-2', ['f_x_c3_seed'])
        bad['twin']['how'] = 'random'
        self.assertTrue(E.validate_card(bad))
        bad = _card('G3-2', ['f_x_c3_seed'])
        bad['twin']['sql'] = 'SELECT DISTINCT product_id, random() AS f_x_c3_seed_tw FROM hist'
        self.assertTrue(any('NONDETERMINISTIC' in p for p in E.validate_card(bad)))
        bad = dict(_card('G3-2', ['f_x_c3_seed']), lens='G1', extra=1)
        self.assertGreaterEqual(len(E.validate_card(bad)), 2)

    def test_quotas_round_robin(self):
        deck = _deck(per_lens=5)
        out = E.curate(_strip(deck), _probes(deck), 12, cross_fn=no_cross)
        self.assertEqual(out['families'][:5], ['G1-1', 'G2-1', 'G3-1', 'G4-1', 'G1-2'])
        self.assertEqual(len(out['families']), 12)
        self.assertEqual({lens: sum(f.startswith(lens) for f in out['families']) for lens in E.LENSES},
                         {lens: 3 for lens in E.LENSES})
        self.assertEqual(sorted(r['id'] for r in out['removed'] if r['step'] == 3),
                         sorted(f'{lens}-{n}' for lens in E.LENSES for n in (4, 5)))
        self.assertTrue(out['parity']['ok'])

    def test_step1_removals_and_withdrawn(self):
        deck = _deck(per_lens=2)
        kw = {'G1-1': dict(red='invalid sql'), 'G2-1': dict(seconds=61.0), 'G3-1': dict(coverage=0.004),
              'G4-1': dict(shares={'2020-01-05': 0.1, '2020-01-06': 0.1, '2020-01-07': 0.5})}
        out = E.curate(_strip(deck), _probes(deck, **kw), 3, critiques=[dict(card='G1-2', type='WITHDRAWN'),
                                                                         dict(card='G2-2', type='LEAK')],
                       cross_fn=no_cross)
        step1 = {r['id']: r['reason'] for r in out['removed'] if r['step'] == 1}
        self.assertEqual(set(step1), {'G1-1', 'G2-1', 'G3-1', 'G4-1', 'G1-2'})
        self.assertIn('machine', step1['G1-1'])
        self.assertIn('seconds', step1['G2-1'])
        self.assertIn('coverage', step1['G3-1'])
        self.assertIn('parity', step1['G4-1'])
        self.assertIn('withdrawn', step1['G1-2'])
        self.assertEqual(out['families'], ['G2-2', 'G3-2', 'G4-2'])  # LEAK alone does not remove

    def test_duplicates(self):
        deck = _deck(per_lens=2)
        deck[0]['_cols'] = ['f_x_c1_k1_0', 'f_x_c1_k1_1']   # G1-1 has two columns
        kw = {'G3-2': dict(r2=0.91), 'G4-2': dict(rho=0.96)}

        def cross_fn(a, b):
            pair = {a['columns'][0], b['columns'][0]}
            if pair == {'f_x_c1_k1_0', 'f_x_c2_k1_0'}:
                return dict(max_abs_rho=0.97, r2_a_on_b={}, r2_b_on_a={})
            if pair == {'f_x_c3_k1_0', 'f_x_c4_k1_0'}:
                return dict(max_abs_rho=0.5, r2_a_on_b={'x': 0.92}, r2_b_on_a={})
            return None
        out = E.curate(_strip(deck), _probes(deck, **kw), 4, cross_fn=cross_fn)
        step2 = {r['id']: r['reason'] for r in out['removed'] if r['step'] == 2}
        self.assertEqual(set(step2), {'G3-2', 'G4-2', 'G1-1', 'G4-1'})
        self.assertIn('H+', step2['G3-2'])
        self.assertIn('G2-1', step2['G1-1'])   # fewer columns stays
        self.assertIn('G3-1', step2['G4-1'])   # equal columns: lens order
        self.assertEqual(out['families'], ['G1-2', 'G2-1', 'G3-1', 'G2-2'])

    def test_parity_cuts(self):
        deck = _deck(per_lens=3, cols=2)                    # 12 families x 2 = 24 columns
        out = E.curate(_strip(deck), _probes(deck), 15, cross_fn=no_cross)
        self.assertEqual(out['parity']['cut'], ['council'])
        self.assertEqual(out['parity']['council_removed'], ['G4-3', 'G3-3', 'G2-3', 'G1-3'])
        self.assertEqual(out['width'], 16)
        self.assertTrue(out['parity']['ok'])
        ref = [(f'rb1_{i}', 3) for i in range(6)] + [(f'rb2_{i}', 3) for i in range(6)]   # 36 columns
        out = E.curate(_strip(deck), _probes(deck), ref, cross_fn=no_cross)
        self.assertEqual(out['parity']['cut'], ['reference'])
        self.assertEqual(out['parity']['reference_drop'], ['rb2_5', 'rb2_4', 'rb2_3', 'rb2_2'])
        self.assertEqual(out['parity']['w_reference_after'], 24)
        self.assertTrue(out['parity']['ok'])
        self.assertEqual(len(out['families']), 12)

    def test_twins_and_placebo(self):
        deck = _deck(per_lens=3)
        out = E.curate(_strip(deck), _probes(deck, twin_ok=lambda c: not c.startswith('G2') and c != 'G1-1'), 12,
                       cross_fn=no_cross)
        self.assertEqual(out['twins'], ['G1-2', 'G3-1', 'G3-2', 'G4-1'])
        names = {c['id']: c['name'] for c in deck}
        first = sorted(out['families'], key=lambda c: (E._sha(names[c]), c))[:4]
        self.assertEqual(out['placebo_families'], first)
        self.assertEqual(out['placebo'], [out['columns'][c][0] for c in first])

    def test_deterministic(self):
        deck = _deck(per_lens=4, cols=2)
        probes = _probes(deck, twin_ok=lambda c: c.endswith('2'))
        ref = [(f'rb_{i}', 2) for i in range(10)]
        a = E.curate(_strip(deck), probes, ref, cross_fn=no_cross)
        shuffled = _strip(deck)
        random.Random(3).shuffle(shuffled)
        b = E.curate(shuffled, dict(reversed(list(probes.items()))), ref, cross_fn=no_cross)
        self.assertEqual(a, b)

    def test_reference_arm_is_filtered_like_the_council(self):
        deck = _deck(per_lens=3)                            # 12 families x 1 column
        ref = {'rb1_ok': _sql_probe(['f_x_a', 'f_x_b', 'f_x_c']),
               'rb1_red': _sql_probe(['f_x_d'], red='forbidden table'),
               'rb1_slow': _sql_probe(['f_x_e'], seconds=61.0),
               'rb1_thin': _sql_probe(['f_x_f'], coverage=0.004),
               'rb1_shift': _sql_probe(['f_x_g'], shares={'2020-01-05': 0.1, '2020-01-06': 0.1, '2020-01-07': 0.5}),
               'rb1_hplus': _sql_probe(['f_x_h'], r2=0.95),
               'rb2_ok': _sql_probe(['f_x_i', 'f_x_j', 'f_x_k', 'f_x_l']),
               'rb2_copy': _sql_probe(['f_x_m', 'f_x_n']),
               'rb2_tail': _sql_probe(['f_x_o', 'f_x_p', 'f_x_q'])}
        calls = []

        def cross_fn(a, b):
            calls.append((a['columns'][0], b['columns'][0]))
            if {a['columns'][0], b['columns'][0]} == {'f_x_m', 'f_x_a'}:
                return dict(max_abs_rho=0.97, r2_a_on_b={}, r2_b_on_a={})
            return None
        out = E.curate(_strip(deck), _probes(deck), critiques=(), cross_fn=cross_fn, reference_probes=ref)
        rr = {r['table']: (r['step'], r['reason']) for r in out['reference_removed']}
        self.assertEqual(set(rr), {'rb1_red', 'rb1_slow', 'rb1_thin', 'rb1_shift', 'rb1_hplus', 'rb2_copy'})
        self.assertEqual([rr[t][0] for t in ('rb1_red', 'rb1_slow', 'rb1_thin', 'rb1_shift')], [1, 1, 1, 1])
        self.assertEqual(rr['rb1_hplus'][0], 2)
        self.assertIn('rb1_ok', rr['rb2_copy'][1])            # the earlier table stays
        self.assertIn(('f_x_m', 'f_x_a'), calls)
        self.assertEqual(out['parity']['w_reference'], 10)  # 3 + 4 + 3 after the filter
        self.assertEqual(out['parity']['cut'], ['council'])
        self.assertEqual(out['width'], 11)
        self.assertEqual(out['reference'], ['rb1_ok', 'rb2_ok', 'rb2_tail'])
        self.assertEqual(out['warnings'], [])
        legacy = E.curate(_strip(deck), _probes(deck), 12, cross_fn=no_cross)
        self.assertTrue(any('not filtered' in w for w in legacy['warnings']))

    def test_stops(self):
        deck = _deck(per_lens=1)
        dead = _probes(deck, **{c['id']: dict(red='bad') for c in deck})
        with self.assertRaisesRegex(SystemExit, 'no family'):
            E.curate(_strip(deck), dead, 4, cross_fn=no_cross)
        with self.assertRaisesRegex(SystemExit, 'reference width is 0'):
            E.curate(_strip(deck), _probes(deck), cross_fn=no_cross,
                     reference_probes={'rb1_red': _sql_probe(['f_x_a'], red='bad')})
        with self.assertRaisesRegex(SystemExit, 'only its width'):
            E.curate(_strip(deck), _probes(deck), 40, cross_fn=no_cross)

    def test_parity_overshoot(self):
        two = [c for c in _deck(per_lens=1) if c['id'] in ('G1-1', 'G2-1')]
        two[0]['_cols'] = [f'f_x_c1_k1_{j}' for j in range(4)]
        two[1]['_cols'] = [f'f_x_c2_k1_{j}' for j in range(4)]
        with self.assertRaisesRegex(SystemExit, 'parity not reached'):   # 8 vs 7+2: r2 cut, then G2-1 cut
            E.curate(_strip(two), _probes(two), [('r1', 7), ('r2', 2)], cross_fn=no_cross)
        two[1]['_cols'] = ['f_x_c2_k1_0']                   # 5 vs 4+3: r2 cut overshoots, G2-1 cut lands
        out = E.curate(_strip(two), _probes(two), [('r1', 4), ('r2', 3)], cross_fn=no_cross)
        self.assertEqual(out['parity']['cut'], ['reference', 'council'])
        self.assertEqual(out['parity']['reference_drop'], ['r2'])
        self.assertEqual(out['parity']['council_removed'], ['G2-1'])
        self.assertEqual((out['parity']['w_council_after'], out['parity']['w_reference_after']), (4, 4))


class Boundary(unittest.TestCase):
    def test_no_target_words(self):
        text = Path(E.__file__).read_text()
        for word in ('lab' + 'el', 'n_tar' + 'gets', 'nd' + 'cg', 're' + 'call', 'per_' + 'query'):
            self.assertNotIn(word, text.lower(), word)
        self.assertNotIn('task1.exp', text)
        self.assertNotIn('task1.placebo', text)


class RealSmoke(unittest.TestCase):
    SQL = roles.ROOT / 'artifacts/task1/v2020/extra/agent_night20_r1p1_first_touch_conversion/feature.sql'
    DAY = '2020-02-05'

    def test_real_probe_one_day(self):
        if not (self.SQL.exists() and (roles.DAYS6 / f'{self.DAY}.parquet').exists() and X.EVENTS.exists()):
            self.skipTest('no 2020 data on this machine')
        sql = self.SQL.read_text()
        t0 = time.time()
        p = E.probe(sql, days=(self.DAY,), threads=10)
        print(f'\nreal probe {E.probe_path(sql).name}: {time.time() - t0:.1f}s (cache hit if ~0), '
              f'query {p["seconds_median"]}s, references {p["per_day"][self.DAY]["sample"]["references"]}, '
              f'coverage {p["coverage"]}, max|rho| {p["max_abs_rho"]}, nearest {p["nearest"]}, R2 {p["r2"]}')
        self.assertEqual(E.machine_red(p), [])
        self.assertEqual(p['level'], 'product')
        self.assertEqual(p['columns'], ['f_x_i_first_touch_conv_lift_7d', 'f_x_i_quick_acq_share_7d'])
        self.assertEqual(p['per_day'][self.DAY]['sample']['references'], 79 + 194)
        self.assertEqual(p['per_day'][self.DAY]['sample']['queries'], E.SAMPLE_QUERIES)
        for c in p['columns']:
            self.assertGreater(p['coverage'][c], 0)
            self.assertLessEqual(p['coverage'][c], 1)
            # the column itself is one of the H+ references
            self.assertGreater(p['max_abs_rho'][c], 0.99)
            self.assertEqual(p['nearest'][c], c)
        self.assertTrue(E.probe_path(sql).exists())


if __name__ == '__main__':
    unittest.main()
