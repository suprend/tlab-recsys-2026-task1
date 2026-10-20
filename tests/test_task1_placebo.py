"""Placebo control and decomposition of H+ (task1/runs/placebo-2026-10-21/spec.md): the permutations within days and
by key, the runner against task1.exp.run on a small fixture, the levels of the real tables, the queues and the reading
of the results.

Run: .venv/bin/python -m unittest tests.test_task1_placebo
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from task1 import exp, placebo
from task1 import model as M
from task1 import period as P

ROOT = Path(__file__).resolve().parents[1]
AUTO = ['f_x_a', 'f_x_b', 'f_x_y']


def frame(seed=0, days=('2019-11-08', '2019-11-09', '2019-11-10')):
    """Candidate rows of a few anchor days with keys, labels, hand-made columns and three automation columns: f_x_b is
    tied to f_x_a row by row, f_x_y is the label itself."""
    rng = np.random.default_rng(seed)
    parts = []
    for d in days:
        for u in range(1, 41):
            n = int(rng.integers(5, 15))
            label = (rng.random(n) < 0.2).astype(np.int32)
            parts.append(pd.DataFrame({'anchor': pd.Timestamp(d), 'user_id': u,
                                       'product_id': rng.choice(np.arange(1000, 1100), n, replace=False),
                                       'label': label, 'n_targets': max(1, int(label.sum())), 's_pop_rank': np.arange(n),
                                       'u_n': np.float32(rng.random()), 'cf_x': rng.random(n).astype(np.float32)}))
    df = pd.concat(parts, ignore_index=True)
    df['qid'] = df.anchor.dt.strftime('%Y-%m-%d') + ':' + df.user_id.astype(str)
    a = rng.random(len(df)).astype(np.float32)
    a[rng.random(len(df)) < 0.3] = np.nan
    df['f_x_a'] = a
    df['f_x_b'] = a * np.float32(2) + np.float32(1)
    df['f_x_y'] = df.label.astype(np.float32)
    return df


def by_keys(df):
    return df.sort_values(['anchor', 'user_id', 'product_id']).reset_index(drop=True)


class PermutationTest(unittest.TestCase):
    def setUp(self):
        self.df = frame()
        self.out = placebo.permute_within_days(self.df, AUTO, 2026, 0)

    def test_each_column_keeps_its_values_and_nulls_within_each_day(self):
        for day, rows in self.df.groupby('anchor').groups.items():
            for c in AUTO:
                before, after = self.df.loc[rows, c].to_numpy(), self.out.loc[rows, c].to_numpy()
                np.testing.assert_array_equal(np.sort(before), np.sort(after), err_msg=f'{day} {c}')
                self.assertEqual(np.isnan(before).sum(), np.isnan(after).sum())
        self.assertGreater(self.df.f_x_a.isna().sum(), 0)

    def test_columns_move_together(self):
        np.testing.assert_array_equal(self.out.f_x_b.to_numpy(), self.out.f_x_a.to_numpy() * np.float32(2) + np.float32(1))

    def test_the_link_to_rows_is_broken(self):
        a, b = self.df.f_x_a.to_numpy(), self.out.f_x_a.to_numpy()
        both = ~np.isnan(a) & ~np.isnan(b)
        self.assertGreater((a[both] != b[both]).mean(), 0.9)
        self.assertEqual((self.df.f_x_y == self.df.label).mean(), 1.0)
        positives = self.out.label == 1
        # the label column moved: among positives it is now about as often 1 as anywhere
        self.assertLess(abs(self.out.f_x_y[positives].mean() - self.df.label.mean()), 0.1)

    def test_deterministic_per_seed_and_day(self):
        again = placebo.permute_within_days(self.df, AUTO, 2026, 0)
        pd.testing.assert_frame_equal(again, self.out)
        shuffled = placebo.permute_within_days(self.df.sample(frac=1, random_state=1), AUTO, 2026, 0)
        pd.testing.assert_frame_equal(by_keys(shuffled), by_keys(self.out))
        other = placebo.permute_within_days(self.df, AUTO, 7, 1)
        self.assertFalse(other.f_x_a.equals(self.out.f_x_a))
        day = self.df.anchor == pd.Timestamp('2019-11-09')
        alone = placebo.permute_within_days(self.df[day], AUTO, 2026, 0)
        pd.testing.assert_frame_equal(by_keys(alone), by_keys(self.out[day]))

    def test_the_draw_follows_the_spec(self):
        """One day rebuilt from the spec: the rows of the day in (user_id, product_id) order, perm =
        default_rng([20261021, seed, neg_seed, ordinal]).permutation(n), the row at position i takes the values of the
        row at position perm[i]. The input is scrambled."""
        t = pd.Timestamp('2019-11-10')
        day = by_keys(self.df[self.df.anchor == t])
        perm = np.random.default_rng([20261021, 7, 1, t.toordinal()]).permutation(len(day))
        want = day.copy()
        want[AUTO] = day[AUTO].to_numpy()[perm]
        got = by_keys(placebo.permute_within_days(self.df.sample(frac=1, random_state=5), AUTO, 7, 1))
        pd.testing.assert_frame_equal(got[got.anchor == t].reset_index(drop=True), want)

    def test_other_columns_stay(self):
        keep = [c for c in self.df.columns if c not in AUTO]
        pd.testing.assert_frame_equal(self.out[keep], self.df[keep])
        self.assertEqual(list(self.out.columns), list(self.df.columns))
        self.assertTrue(all(self.out[c].dtype == np.float32 for c in AUTO))
        pd.testing.assert_frame_equal(self.df, frame())  # the input is not modified

    def test_refuses_columns_that_are_not_automation(self):
        for cols in (['u_n'], ['label'], ['s_pop_rank'], ['cf_x'], ['qid'], ['user_id'], [], ['f_x_a', 'f_x_a'],
                     ['f_x_missing']):
            with self.assertRaises(ValueError, msg=str(cols)):
                placebo.permute_within_days(self.df, cols, 2026, 0)
        twice = pd.concat([self.df, self.df.head(1)])
        with self.assertRaisesRegex(ValueError, 'not unique'):
            placebo.permute_within_days(twice, AUTO, 2026, 0)
        with self.assertRaisesRegex(ValueError, 'not a day'):
            placebo.permute_within_days(self.df.assign(anchor=self.df.anchor + pd.Timedelta(hours=3)), AUTO, 2026, 0)


USER, PRODUCT, PAIR = ['f_x_u1', 'f_x_u2'], ['f_x_p1', 'f_x_p2', 'f_x_c'], ['f_x_q1', 'f_x_q2']
BY_LEVEL = {'user': USER, 'product': PRODUCT, 'pair': PAIR}


def key_frame(seed=0, days=('2019-11-08', '2019-11-09', '2019-11-10')):
    """Candidate rows of a few days, joined the way exp.with_extra joins: user columns constant per (day, user), a
    product vector constant per (day, product) with a category column shared by the products of a category, pair
    columns free per row; f_x_p2 and f_x_q2 are tied to f_x_p1 and f_x_q1, user 7 and product 1003 are missing from
    their tables."""
    rng = np.random.default_rng(seed)
    parts = []
    for d in days:
        t = pd.Timestamp(d)
        user = pd.DataFrame({'user_id': np.arange(1, 31), 'f_x_u1': rng.random(30), 'f_x_u2': rng.random(30)})
        user.loc[user.user_id == 7, USER] = np.nan
        item = pd.DataFrame({'product_id': np.arange(1000, 1060), 'f_x_p1': rng.random(60)})
        item['f_x_p2'] = item.f_x_p1 * 3 + 1
        item['f_x_c'] = (item.product_id // 10).map(dict(enumerate(rng.random(200))))
        item.loc[item.product_id == 1003, ['f_x_p1', 'f_x_p2']] = np.nan
        for u in range(1, 31):
            n = int(rng.integers(6, 20))
            items = rng.choice(np.arange(1000, 1060), n, replace=False)
            q1 = rng.random(n)
            q1[rng.random(n) < 0.2] = np.nan
            parts.append(pd.DataFrame({'anchor': t, 'user_id': u, 'product_id': items,
                                       'label': (rng.random(n) < 0.2).astype(np.int32), 's_pop_rank': np.arange(n),
                                       'u_n': np.float32(u), 'i_price': items / 10.0, 'f_x_q1': q1, 'f_x_q2': q1 + 10})
                         .merge(user, on='user_id', how='left').merge(item, on='product_id', how='left'))
    df = pd.concat(parts, ignore_index=True)
    df['qid'] = df.anchor.dt.strftime('%Y-%m-%d') + ':' + df.user_id.astype(str)
    for c in USER + PRODUCT + PAIR:
        df[c] = df[c].astype(np.float32)
    return df


def tuples(df, keys, cols):
    """keys -> sorted list of the distinct-or-not tuples of cols (NaN as a number) on the rows of each group."""
    x = df[keys + cols].fillna(-1.0)
    return {k: sorted(map(tuple, g[cols].to_numpy().tolist())) for k, g in x.groupby(keys)}


def constant(df, keys, cols):
    """Every group of keys holds one vector of cols (NaN equal to NaN)."""
    return len(df[keys + cols].drop_duplicates()) == len(df[keys].drop_duplicates())


def entity_vectors(df, key, cols):
    """day -> the sorted vectors of cols, one per distinct key of the day."""
    return tuples(df.drop_duplicates(['anchor', key]), ['anchor'], cols)


def user_level_kept(before, after):
    return constant(after, ['anchor', 'user_id'], USER) and \
        entity_vectors(after, 'user_id', USER) == entity_vectors(before, 'user_id', USER)


def product_level_kept(before, after):
    return constant(after, ['anchor', 'product_id'], PRODUCT) and \
        entity_vectors(after, 'product_id', PRODUCT) == entity_vectors(before, 'product_id', PRODUCT)


def pair_level_kept(before, after):
    return tuples(after, ['qid'], PAIR) == tuples(before, ['qid'], PAIR)


def moved(before, after, key, cols):
    """Share of the entities (rows for key=None) of the frame whose values of cols changed."""
    b = before.set_index(['anchor', 'user_id', 'product_id'])[cols].fillna(-1.0)
    a = after.set_index(['anchor', 'user_id', 'product_id']).loc[b.index, cols].fillna(-1.0)
    changed = (a != b).any(axis=1)
    return float(changed.mean() if key is None else changed.groupby(level=['anchor', key]).max().mean())


class KeyPermutationTest(unittest.TestCase):
    def setUp(self):
        self.df = key_frame()
        self.out = placebo.permute_by_key(self.df, BY_LEVEL, 2026, 0)

    def test_user_columns_move_to_another_user_and_stay_constant_within_each_query(self):
        self.assertTrue(constant(self.out, ['qid'], USER))
        self.assertTrue(user_level_kept(self.df, self.out))

    def test_product_vectors_stay_whole_and_consistent_across_the_queries_of_a_day(self):
        self.assertTrue(product_level_kept(self.df, self.out))
        np.testing.assert_allclose(self.out.f_x_p2, self.out.f_x_p1 * 3 + 1, rtol=1e-6)
        day = self.out[self.out.anchor == pd.Timestamp('2019-11-09')]
        self.assertGreater(day.groupby('product_id').qid.nunique().min(), 1)  # the products sit in several queries

    def test_pair_columns_keep_each_query_multiset(self):
        self.assertTrue(pair_level_kept(self.df, self.out))
        np.testing.assert_allclose(self.out.f_x_q2, self.out.f_x_q1 + 10, rtol=1e-6)

    def test_it_is_a_real_permutation(self):
        self.assertGreater(moved(self.df, self.out, 'user_id', USER), 0.9)
        self.assertGreater(moved(self.df, self.out, 'product_id', PRODUCT), 0.9)
        self.assertGreater(moved(self.df, self.out, None, PAIR), 0.8)

    def test_deterministic(self):
        pd.testing.assert_frame_equal(placebo.permute_by_key(self.df, BY_LEVEL, 2026, 0), self.out)
        shuffled = placebo.permute_by_key(self.df.sample(frac=1, random_state=3), BY_LEVEL, 2026, 0)
        pd.testing.assert_frame_equal(by_keys(shuffled), by_keys(self.out))
        day = self.df.anchor == pd.Timestamp('2019-11-10')
        alone = placebo.permute_by_key(self.df[day], BY_LEVEL, 2026, 0)
        pd.testing.assert_frame_equal(by_keys(alone), by_keys(self.out[day]))
        other = placebo.permute_by_key(self.df, BY_LEVEL, 7, 1)
        for cols in BY_LEVEL.values():
            self.assertFalse(other[cols].equals(self.out[cols]))

    def test_the_draws_follow_the_spec(self):
        """One day rebuilt from the spec: default_rng([20261021, 2, seed, neg_seed, ordinal]) draws pi_u over the sorted
        users, then pi_p over the sorted products, then one uniform number per row in (user_id, product_id) order; the
        j-th row of a query takes the pair values of its row with the j-th smallest number."""
        t = pd.Timestamp('2019-11-09')
        day = by_keys(self.df[self.df.anchor == t])
        rng = np.random.default_rng([20261021, 2, 7, 1, t.toordinal()])
        users, items = np.sort(day.user_id.unique()), np.sort(day.product_id.unique())
        pi_u, pi_p, z = rng.permutation(len(users)), rng.permutation(len(items)), rng.random(len(day))
        user_vec = day.drop_duplicates('user_id').set_index('user_id')[USER]
        item_vec = day.drop_duplicates('product_id').set_index('product_id')[PRODUCT]
        want = day.copy()
        want[USER] = user_vec.loc[[dict(zip(users, users[pi_u]))[u] for u in day.user_id]].to_numpy()
        want[PRODUCT] = item_vec.loc[[dict(zip(items, items[pi_p]))[i] for i in day.product_id]].to_numpy()
        src = np.concatenate([g.index.to_numpy()[np.argsort(z[g.index], kind='stable')]
                              for _, g in day.groupby('user_id', sort=True)])
        want[PAIR] = day.loc[src, PAIR].to_numpy()
        got = by_keys(placebo.permute_by_key(self.df, BY_LEVEL, 7, 1))
        pd.testing.assert_frame_equal(got[got.anchor == t].reset_index(drop=True), want)

    def test_other_columns_stay(self):
        keep = [c for c in self.df.columns if c not in USER + PRODUCT + PAIR]
        pd.testing.assert_frame_equal(self.out[keep], self.df[keep])
        self.assertEqual(list(self.out.columns), list(self.df.columns))
        self.assertTrue(all(self.out[c].dtype == np.float32 for c in USER + PRODUCT + PAIR))
        pd.testing.assert_frame_equal(self.df, key_frame())  # the input is not modified

    def test_a_level_left_out_stays(self):
        out = placebo.permute_by_key(self.df, {'product': PRODUCT}, 2026, 0)
        pd.testing.assert_frame_equal(out[USER + PAIR], self.df[USER + PAIR])
        pd.testing.assert_frame_equal(out[PRODUCT], self.out[PRODUCT])  # the draws do not depend on the levels

    def test_the_constancy_checks_stop_bad_input(self):
        varying_user = self.df.copy()
        varying_user.loc[varying_user.index[varying_user.qid == '2019-11-09:4'][0], 'f_x_u2'] += 1
        with self.assertRaisesRegex(ValueError, 'f_x_u2: the values of the user level differ'):
            placebo.permute_by_key(varying_user, BY_LEVEL, 2026, 0)
        varying_item = self.df.copy()
        rows = varying_item.index[(varying_item.product_id == 1012) & (varying_item.anchor == pd.Timestamp('2019-11-08'))]
        self.assertGreater(len(rows), 1)
        varying_item.loc[rows[1], 'f_x_c'] = np.nan
        with self.assertRaisesRegex(ValueError, 'f_x_c: the values of the product level differ'):
            placebo.permute_by_key(varying_item, BY_LEVEL, 2026, 0)
        with self.assertRaisesRegex(ValueError, 'product level differ'):  # pair columns are no product columns
            placebo.permute_by_key(self.df, {'product': ['f_x_q1']}, 2026, 0)

    def test_rows_with_a_null_key_keep_its_levels(self):
        df = self.df.astype({'product_id': 'float64'})
        hole = df.index[(df.qid == '2019-11-08:5')][:2]
        df.loc[hole, 'product_id'] = np.nan
        df.loc[hole, PRODUCT] = np.nan  # the join finds no product
        out = placebo.permute_by_key(df, BY_LEVEL, 2026, 0)
        pd.testing.assert_frame_equal(out.loc[hole, PRODUCT + PAIR], df.loc[hole, PRODUCT + PAIR])
        self.assertTrue(constant(out, ['qid'], USER))  # the user of these rows still moves with its query
        self.assertFalse(out.loc[hole, USER].equals(df.loc[hole, USER]))

    def test_refusals(self):
        for levels in ({'query': PAIR}, {'user': ['u_n']}, {'product': ['i_price']}, {'pair': ['label']}, {},
                       {'user': USER, 'pair': USER}):
            with self.assertRaises(ValueError, msg=str(levels)):
                placebo.permute_by_key(self.df, levels, 2026, 0)
        with self.assertRaisesRegex(ValueError, 'not unique'):
            placebo.permute_by_key(pd.concat([self.df, self.df.tail(1)]), BY_LEVEL, 2026, 0)

    def test_breaking_the_key_level_permutation_is_caught(self):
        """The property checks above fail on permutations that break one rule of the key level."""
        row = lambda cols: placebo.permute_within_days(self.df, cols, 2026, 0)
        per_column = self.df
        for k, c in enumerate(PRODUCT):  # every product column its own permutation of the products
            per_column = placebo.permute_by_key(per_column, {'product': [c]}, 2026 + k, 0)
        self.assertTrue(constant(per_column, ['anchor', 'product_id'], PRODUCT))
        per_column_user = self.df
        for k, c in enumerate(USER):
            per_column_user = placebo.permute_by_key(per_column_user, {'user': [c]}, 2026 + k, 0)
        within_query = placebo.permute_by_key(self.df, {'pair': PRODUCT}, 2026, 0)
        self.assertFalse(user_level_kept(self.df, row(USER)))  # user values spread over rows
        self.assertFalse(user_level_kept(self.df, per_column_user))  # vectors torn apart
        self.assertFalse(product_level_kept(self.df, per_column))
        self.assertFalse(product_level_kept(self.df, within_query))  # one product, different vectors by query
        self.assertFalse(product_level_kept(self.df, row(PRODUCT)))
        self.assertFalse(pair_level_kept(self.df, row(PAIR)))  # pair values leave their query
        for level, key in (('user', 'user_id'), ('product', 'product_id'), ('pair', None)):
            self.assertEqual(moved(self.df, self.df, key, BY_LEVEL[level]), 0.0)  # the identity is no permutation


EXTRA = ['tx_p', 'tx_u', 'tx_up']


def write_fixture(root):
    """Day tables for every train and val day of the period and three extra tables keyed like the real ones: by
    product, by user (one user missing) and by pair (one column informative)."""
    rng = np.random.default_rng(3)
    (root / 'days').mkdir()
    for name in EXTRA:
        (root / 'extra' / name).mkdir(parents=True)
    for d in M.days('train') + M.days('val'):
        parts = []
        for u in rng.choice(np.arange(1, 40), 6, replace=False):
            items = rng.choice(np.arange(100, 160), 12, replace=False)
            label = (np.arange(12) == rng.integers(0, 12)).astype(np.int32)
            bought = label * int(rng.random() < 0.5)
            parts.append(pd.DataFrame({'anchor': d, 'user_id': int(u), 'product_id': items, 'label': label,
                                       'label_purchase': bought, 'n_targets': 1 + int(rng.integers(0, 2)),
                                       'n_targets_purchase': int(bought.sum()), 's_pop_rank': np.arange(12),
                                       'u_n': rng.random(), 'i_price': items / 10.0,
                                       'i_cat_l1': [f'c{i % 3}' for i in items],
                                       'cf_cv_cond_tdecay20': label + rng.random(12)}))
        days = pd.concat(parts, ignore_index=True)
        duckdb.sql(f"COPY (SELECT * FROM days) TO '{root / 'days' / f'{d}.parquet'}' (FORMAT PARQUET)")
        tables = {'tx_p': pd.DataFrame({'product_id': np.arange(100, 160), 'f_x_p_pop': rng.random(60)}),
                  'tx_u': pd.DataFrame({'user_id': days.user_id.unique()[1:], 'f_x_u_act': rng.random(5)}),
                  'tx_up': days[['user_id', 'product_id']].assign(
                      f_x_up_sig=days.label + rng.random(len(days)),
                      f_x_up_rec=np.where(rng.random(len(days)) < 0.3, np.nan, rng.random(len(days))))}
        for name, x in tables.items():
            duckdb.sql(f"COPY (SELECT * FROM x) TO '{root / 'extra' / name / f'{d}.parquet'}' (FORMAT PARQUET)")


class RunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        write_fixture(cls.root)
        cls.cfg = {'days': str(cls.root / 'days'), 'depth': 3, 'iterations': 15, 'threads': 2}
        cls.train_queries = duckdb.sql(f"""SELECT count(DISTINCT (anchor, user_id)) FROM read_parquet(
            {[str(cls.root / 'days' / f'{d}.parquet') for d in M.days('train')]})""").fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        out = tempfile.mkdtemp(dir=self.root)
        self.patches = [mock.patch.object(M, 'EXTRA', self.root / 'extra'), mock.patch.object(exp, 'OUT', Path(out))]
        for p in self.patches:
            p.start()
        exp._cache.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        exp._cache.clear()

    def quiet(self, fn, *args, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            rec = fn(*args, **kw)
        return rec, printed.getvalue()

    def test_without_the_new_keys_a_run_is_exp_run(self):
        for over in ({'extra': EXTRA}, {'seed': 7, 'neg_seed': 1}):
            cfg = self.cfg | over
            ref, _ = self.quiet(exp.run, 'ref', **cfg)
            exp._cache.clear()
            new, printed = self.quiet(placebo.run, 'new', **cfg)
            pd.testing.assert_frame_equal(exp.metrics('new'), exp.metrics('ref'))
            self.assertEqual((new['features'], new['train_rows']), (ref['features'], ref['train_rows']))
            self.assertEqual((new['permuted'], new['fit_queries']), (0, self.train_queries))
            self.assertEqual(new['cfg'], exp.DEFAULT | cfg)
            self.assertEqual((new['commit'], len(new['started'])), (None, 19))
            self.assertEqual((new['code'], new['libraries']), (placebo.code_stamp(), placebo.libraries()))
            self.assertNotIn('ndcg', printed)
            self.assertFalse([k for k in new if 'ndcg' in k or 'recall' in k])

    def test_the_placebo_permutes_train_and_each_val_day(self):
        fits, scored, reads, days = [], [], [], []
        real_fit, real_predict, real_read, real_day = exp.fit, M.predict, exp._read, exp.read_day

        def fit(train, features, cfg):
            fits.append(train.copy())
            return real_fit(train, features, cfg)

        def predict(model, df, features):
            scored.append(df.copy())
            return real_predict(model, df, features)

        def read(split, days_dir, cap=None):
            reads.append(split)
            return real_read(split, days_dir, cap)

        def read_day(d, days_dir):
            days.append(d)
            return real_day(d, days_dir)

        with mock.patch.object(exp, 'fit', fit), mock.patch.object(M, 'predict', predict), \
                mock.patch.object(exp, '_read', read), mock.patch.object(exp, 'read_day', read_day):
            hp, _ = self.quiet(placebo.run, 'hp', **self.cfg, extra=EXTRA)
            pl, _ = self.quiet(placebo.run, 'pl', **self.cfg, extra=EXTRA, permute='within_day')
        auto = ['f_x_p_pop', 'f_x_u_act', 'f_x_up_sig', 'f_x_up_rec']
        self.assertEqual((pl['permuted'], hp['permuted']), (4, 0))
        self.assertEqual((pl['features'], pl['train_rows'], pl['fit_queries']),
                         (hp['features'], hp['train_rows'], hp['fit_queries']))
        self.assertEqual(reads, ['train', 'train'])  # never refit or test
        self.assertEqual(days, M.days('val') * 2)
        self.assertEqual(len(fits), 2)
        self.assertEqual(len(scored), 2 * len(M.days('val')))
        n = len(M.days('val'))
        for plain, moved in [(fits[0], fits[1])] + list(zip(scored[:n], scored[n:])):
            pd.testing.assert_frame_equal(moved, placebo.permute_within_days(plain, auto, 2026, 0))
            self.assertGreater((moved.f_x_up_sig != plain.f_x_up_sig).mean(), 0.5)
        self.assertEqual(sorted(fits[1].anchor.unique()), sorted(pd.Timestamp(d) for d in M.days('train')))
        pd.testing.assert_index_equal(exp.metrics('pl').index, exp.metrics('hp').index)
        self.assertIsNotNone(pl['added_importance'])
        records = [json.loads(x) for x in (exp.OUT / 'runs.jsonl').read_text().splitlines()]
        self.assertEqual([r['name'] for r in records], ['hp', 'pl'])
        self.assertEqual(records[1]['cfg']['permute'], 'within_day')

    def test_the_key_placebo_moves_each_table_by_its_join_key(self):
        fits, scored = [], []
        real_fit, real_predict = exp.fit, M.predict

        def fit(train, features, cfg):
            fits.append(train.copy())
            return real_fit(train, features, cfg)

        def predict(model, df, features):
            scored.append(df.copy())
            return real_predict(model, df, features)

        with mock.patch.object(exp, 'fit', fit), mock.patch.object(M, 'predict', predict):
            hp, _ = self.quiet(placebo.run, 'hp', **self.cfg, extra=EXTRA)
            pk, _ = self.quiet(placebo.run, 'pk', **self.cfg, extra=EXTRA, permute='by_key')
        self.assertEqual(pk['levels'], {'user': ['tx_u'], 'product': ['tx_p'], 'pair': ['tx_up']})
        self.assertEqual((pk['permuted'], hp['permuted'], hp['levels']), (4, 0, None))
        self.assertEqual((pk['features'], pk['train_rows'], pk['fit_queries']),
                         (hp['features'], hp['train_rows'], hp['fit_queries']))
        n = len(M.days('val'))
        self.assertEqual((len(fits), len(scored)), (2, 2 * n))
        levels = {'user': ['f_x_u_act'], 'product': ['f_x_p_pop'], 'pair': ['f_x_up_sig', 'f_x_up_rec']}
        for plain, moved in [(fits[0], fits[1])] + list(zip(scored[:n], scored[n:])):
            pd.testing.assert_frame_equal(moved, placebo.permute_by_key(plain, levels, 2026, 0))
            self.assertEqual(moved.groupby('qid').f_x_u_act.nunique(dropna=False).max(), 1)
            self.assertEqual(moved.groupby(['anchor', 'product_id']).f_x_p_pop.nunique(dropna=False).max(), 1)
            self.assertGreater((moved.f_x_p_pop != plain.f_x_p_pop).mean(), 0.5)
            self.assertGreater((moved.f_x_up_sig != plain.f_x_up_sig).mean(), 0.5)
            for c in levels['pair']:
                pd.testing.assert_series_equal(moved.groupby('qid')[c].sum(), plain.groupby('qid')[c].sum())
        pd.testing.assert_index_equal(exp.metrics('pk').index, exp.metrics('hp').index)
        records = [json.loads(x) for x in (exp.OUT / 'runs.jsonl').read_text().splitlines()]
        self.assertEqual([(r['cfg'].get('permute'), r['levels']) for r in records], [(None, None), ('by_key', pk['levels'])])

    def test_a_table_without_a_level_stops_the_key_placebo_before_the_fit(self):
        day0 = M.days('val')[0]
        self.assertEqual(placebo.table_levels(EXTRA, day0), {'tx_p': ('product', ['f_x_p_pop']),
                                                            'tx_u': ('user', ['f_x_u_act']),
                                                            'tx_up': ('pair', ['f_x_up_sig', 'f_x_up_rec'])})
        flat = self.root / 'extra' / 'tx_day'  # one row a day, joined by anchor alone
        flat.mkdir()
        self.addCleanup(shutil.rmtree, flat)
        for d in M.days('train') + M.days('val'):
            x = pd.DataFrame({'f_x_day': [1.0]})
            duckdb.sql(f"COPY (SELECT * FROM x) TO '{flat / f'{d}.parquet'}' (FORMAT PARQUET)")
        with self.assertRaisesRegex(ValueError, r'tx_day: the join key \(\) maps to no level'):
            placebo.table_levels(['tx_day'], day0)
        with mock.patch.object(exp, 'fit', side_effect=AssertionError('fitted')), \
                self.assertRaisesRegex(ValueError, 'maps to no level'):
            placebo.run('flat', **self.cfg, extra=EXTRA + ['tx_day'], permute='by_key')
        wrong = placebo.table_levels(EXTRA, day0) | {'tx_up': ('pair', ['f_x_up_rec', 'f_x_up_sig'])}
        with mock.patch.object(placebo, 'table_levels', return_value=wrong), \
                mock.patch.object(exp, 'fit', side_effect=AssertionError('fitted')), \
                self.assertRaisesRegex(ValueError, 'do not give the joined columns'):
            placebo.run('swapped', **self.cfg, extra=EXTRA, permute='by_key')
        self.assertFalse(list(exp.OUT.glob('*.parquet')))

    def test_a_run_whose_code_changed_writes_nothing(self):
        with self.assertRaisesRegex(SystemExit, 'the code changed during the run'):
            self.quiet(placebo.run, 'changed', stamp=placebo.code_stamp() | {'task1/placebo.py': 'earlier'}, **self.cfg)
        self.assertFalse(list(exp.OUT.iterdir()))

    def test_cap(self):
        rec, _ = self.quiet(placebo.run, 'cap', **self.cfg, cap=40)
        self.assertEqual(rec['fit_queries'], 40)
        self.assertLess(40, self.train_queries)

    def test_bad_configs_stop_before_any_read(self):
        with mock.patch.object(exp, '_read', side_effect=AssertionError('the pool was read')):
            for over in ({'permute': 'yes'}, {'capp': 3}, {'permute': 'within_day'}, {'permute': 'by_key'},
                         {'days': 'artifacts/task1/v2020/sealed/days'}, {'extra': ['tx_p', 'sealed_tx']}):
                with self.assertRaises(ValueError, msg=str(over)):
                    placebo.run('bad', **(self.cfg | over))
        self.assertFalse((exp.OUT / 'bad.parquet').exists())


class LevelsTest(unittest.TestCase):
    """The levels of the spec against the grid and the schemas of the real tables (schemas only, no values)."""

    def setUp(self):
        grid = {x['name']: x for x in json.loads((ROOT / 'task1/runs/grid-2026-10-20/grid.json').read_text())}
        self.hp = grid['grid_Hp_s0']['extra']

    def test_every_table_of_h_plus_has_one_level_in_grid_order(self):
        self.assertEqual(list(placebo.LEVELS), list(placebo.LEVEL_ORDER))
        self.assertEqual(sorted(t for v in placebo.LEVELS.values() for t in v), sorted(self.hp))
        self.assertEqual({lv: [t for t in self.hp if t in v] for lv, v in placebo.LEVELS.items()}, placebo.LEVELS)

    def test_the_schemas_give_the_levels_in_both_periods(self):
        level = {t: lv for lv, v in placebo.LEVELS.items() for t in v}
        for art, days in (('v2', ('2019-10-15', '2019-11-13')), ('v2020', ('2020-01-15', '2020-02-13'))):
            extra = ROOT / 'artifacts/task1' / art / 'extra'
            if not all((extra / t / f'{d}.parquet').exists() for t in self.hp for d in days):
                self.skipTest(f'the extra tables of {art} are not here')
            for d in days:  # the first train day and the last val day
                with self.subTest(day=d), mock.patch.object(M, 'EXTRA', extra):
                    got = placebo.table_levels(self.hp, d)
                    self.assertEqual({t: lv for t, (lv, _) in got.items()}, level)
                    width = {lv: sum(len(v) for t_lv, v in got.values() if t_lv == lv) for lv in placebo.LEVEL_ORDER}
                    self.assertEqual(width, {'user': 32, 'product': 126, 'pair': 36})
                    cols = [c for _, v in got.values() for c in v]
                    self.assertTrue(all(c.startswith('f_x_') for c in cols) and len(set(cols)) == len(cols) == 194)


class GuardTest(unittest.TestCase):
    def test_a_queue_starts_only_with_the_spec_queues_and_code_committed(self):
        calls = []

        def fake_git(dirty):
            def git(*args):
                calls.append(args)
                return dirty if args[0] == 'status' else 'abc123\n'
            return git

        with mock.patch.object(placebo, 'git', fake_git('?? task1/runs/placebo-2026-10-21/\n')):
            with self.assertRaisesRegex(SystemExit, 'commit the spec'):
                placebo.committed()
        self.assertEqual(calls[0], ('status', '--porcelain', '--', 'task1/exp.py', 'task1/model.py', 'task1/period.py',
                                    'task1/posthoc.py', 'task1/placebo.py', 'tests/test_task1_placebo.py',
                                    'task1/runs/placebo-2026-10-21',
                                    ':(exclude)task1/runs/placebo-2026-10-21/result.json'))
        with mock.patch.object(placebo, 'git', fake_git('')):
            self.assertEqual(placebo.committed(), 'abc123')
        with mock.patch.object(placebo, 'committed', side_effect=SystemExit('dirty')), \
                mock.patch.object(placebo, 'run_queue') as run_queue, \
                mock.patch.object(sys, 'argv', ['placebo', 'run', 'queue.json']), self.assertRaises(SystemExit):
            placebo.main()
        run_queue.assert_not_called()

    def test_importing_placebo_leaves_exp_as_it_is(self):
        code = """
            from task1 import exp
            before, default = dict(vars(exp)), dict(exp.DEFAULT)
            from task1 import placebo
            after = dict(vars(exp))
            print(before.keys() == after.keys() and all(after[k] is v for k, v in before.items()), exp.DEFAULT == default)
        """
        r = subprocess.run([sys.executable, '-c', textwrap.dedent(code)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.stdout.split(), ['True', 'True'], r.stderr)


def load_queue(period):
    return {x['name']: x for x in json.loads(placebo.QUEUE[period].read_text())}


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.grid = {x['name']: x for x in json.loads((ROOT / 'task1/runs/grid-2026-10-20/grid.json').read_text())}

    def test_queues_follow_the_grid(self):
        strip = lambda x, *keys: {k: v for k, v in x.items() if k not in ('name', *keys)}
        hp = self.grid['grid_Hp_s0']['extra']
        part = {'Hag': [e for e in hp if e.startswith('agent_night20_')], 'Hdfs': [e for e in hp if e.startswith('dfs_')]}
        self.assertEqual((len(part['Hag']), len(part['Hdfs'])), (30, 4))
        q19, q20 = load_queue('2019'), load_queue('2020')
        self.assertEqual(list(q19), [f'pl19_{a}_s{s}' for a in ('Hpl', 'Hpk', 'Hag', 'Hdfs') for s in (0, 1)])
        self.assertEqual(list(q20), ['pl20_Hp_s0', 'pl20_Hpl_s0', 'pl20_Hp_s1', 'pl20_Hpl_s1', 'pl20_Hpk_s0', 'pl20_Hpk_s1']
                         + [f'pl20_{a}_s{s}' for a in ('H', 'Hag', 'Hdfs') for s in (0, 1)])
        for s in (0, 1):
            grid_hp = strip(self.grid[f'grid_Hp_s{s}'])
            self.assertEqual(strip(q19[f'pl19_Hpl_s{s}']), grid_hp | {'permute': 'within_day'})
            self.assertEqual(strip(q19[f'pl19_Hpk_s{s}']), grid_hp | {'permute': 'by_key'})
            for arm in ('Hag', 'Hdfs'):
                self.assertEqual(strip(q19[f'pl19_{arm}_s{s}']), grid_hp | {'extra': part[arm]})
            v2020 = grid_hp | {'days': 'artifacts/task1/v2020/days6', 'cap': placebo.FIT_QUERIES['2020']}
            self.assertEqual(strip(q20[f'pl20_Hp_s{s}']), v2020)
            self.assertEqual(strip(q20[f'pl20_Hpl_s{s}']), v2020 | {'permute': 'within_day'})
            self.assertEqual(strip(q20[f'pl20_Hpk_s{s}']), v2020 | {'permute': 'by_key'})
            self.assertEqual(strip(q20[f'pl20_H_s{s}']), strip(v2020, 'extra'))
            for arm in ('Hag', 'Hdfs'):
                self.assertEqual(strip(q20[f'pl20_{arm}_s{s}']), v2020 | {'extra': part[arm]})

    def test_reused_runs_and_feature_counts_match_the_grid(self):
        from task1 import posthoc
        self.assertEqual(placebo.REUSED['H'], posthoc.H)
        self.assertEqual(placebo.REUSED['Hp'], [f"{posthoc.ARMS['Hp']}_s{s}" for s in (0, 1)])
        f = posthoc.FEATURES
        self.assertEqual(placebo.FEATURES, {'H': 80, 'Hp': f['grid_Hp'], 'Hpl': f['grid_Hp'], 'Hpk': f['grid_Hp'],
                                            'Hag': 80 + f['grid_F1agent'] - 6, 'Hdfs': 80 + f['grid_F1dfs'] - 6})
        self.assertEqual(placebo.PERMUTED, {'Hpl': f['grid_Hp'] - 80, 'Hpk': f['grid_Hp'] - 80})

    def test_reader_dirs_are_exp_out_of_each_period(self):
        code = 'from task1 import exp, placebo, period as P; print(exp.OUT == placebo.OUT[P.PERIOD])'
        for period in ('2019', '2020'):
            env = {k: v for k, v in os.environ.items() if k not in ('TASK1_PERIOD', 'TASK1_DAYS')}
            r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env | {'TASK1_PERIOD': period},
                               capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), 'True', r.stderr)

    def test_a_queue_runs_only_under_its_period(self):
        stub = """
            import sys
            from task1 import exp, placebo
            def refuse(*a, **k):
                raise RuntimeError('data were read')
            exp._read = exp.read_day = placebo.run = refuse
            placebo.run_queue(placebo.QUEUE[sys.argv[1]])
        """
        for queue, period in (('2020', '2019'), ('2019', '2020')):
            env = {k: v for k, v in os.environ.items() if k not in ('TASK1_PERIOD', 'TASK1_DAYS')}
            r = subprocess.run([sys.executable, '-c', textwrap.dedent(stub), queue], cwd=ROOT,
                               env=env | {'TASK1_PERIOD': period}, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(f'not a run of TASK1_PERIOD={period}', r.stderr)
            self.assertNotIn('data were read', r.stderr)

    def test_a_stopped_queue_goes_on_and_a_changed_run_stops_it(self):
        path = placebo.QUEUE[P.PERIOD]  # the queue of the period of this process
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as d2, contextlib.chdir(ROOT), \
                mock.patch.object(exp, 'OUT', Path(d)), mock.patch.object(placebo, 'run') as run, \
                mock.patch.object(placebo, 'OUT', {P.PERIOD: Path(d), 'other': Path(d2)}):
            queue = json.loads(path.read_text())
            name, first = queue[0]['name'], {k: v for k, v in queue[0].items() if k != 'name'}
            (Path(d) / f'{name}.parquet').write_text('')
            with self.assertRaisesRegex(SystemExit, 'without a record'):
                placebo.run_queue(path)
            rec = {'name': name, 'cfg': exp.DEFAULT | first, 'code': placebo.code_stamp()}
            (Path(d) / 'runs.jsonl').write_text(json.dumps(rec) + '\n')
            with contextlib.redirect_stdout(io.StringIO()):
                placebo.run_queue(path, 'abc')
            self.assertEqual([c.args for c in run.call_args_list],
                             [(x['name'], 'abc', placebo.code_stamp()) for x in queue[1:]])
            self.assertEqual(run.call_args_list[0].kwargs, {k: v for k, v in queue[1].items() if k != 'name'})
            with open(Path(d) / 'runs.jsonl', 'a') as f:
                f.write(json.dumps(rec | {'cfg': exp.DEFAULT | first | {'depth': 6}}) + '\n')
            with self.assertRaisesRegex(SystemExit, 'another config'):
                placebo.run_queue(path)

    def test_a_queue_stops_on_runs_of_another_code_and_on_any_bad_entry(self):
        path = placebo.QUEUE[P.PERIOD]
        queue = json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as d2, contextlib.chdir(ROOT), \
                mock.patch.object(exp, 'OUT', Path(d)), mock.patch.object(placebo, 'run') as run, \
                mock.patch.object(placebo, 'OUT', {P.PERIOD: Path(d), 'other': Path(d2)}):
            earlier = {'name': 'pl00_Hpl_s0', 'cfg': {}, 'code': placebo.code_stamp() | {'task1/posthoc.py': 'old'}}
            (Path(d2) / 'runs.jsonl').write_text(json.dumps({'name': 'q2_d8', 'cfg': {}}) + '\n' + json.dumps(earlier) + '\n')
            with self.assertRaisesRegex(SystemExit, r"another version of the code: \['pl00_Hpl_s0'\]"):
                placebo.run_queue(path)
            (Path(d2) / 'runs.jsonl').unlink()
            for bad in ({'capp': 1}, {'permute': 'by_row'}, {'extra': ['sealed_tx']}):
                with self.subTest(bad=bad):
                    q = Path(d) / 'queue.json'
                    q.write_text(json.dumps(queue[:-1] + [queue[-1] | bad]))
                    with self.assertRaisesRegex(SystemExit, queue[-1]['name']):
                        placebo.run_queue(q)
        run.assert_not_called()


def series(effects, n=4000, seed=1, noise=0.003):
    """Per-seed NDCG of every arm over the same queries: a common base, the effect of the arm (one number or one per
    seed) and independent noise."""
    rng = np.random.default_rng(seed)
    idx = pd.Index([f'2019-11-08:{u}' for u in range(n)], name='qid')
    base = rng.random(n) * 0.3
    out = {}
    for arm, eff in effects.items():
        eff = eff if isinstance(eff, tuple) else (eff, eff)
        out[arm] = [pd.Series(base + e + rng.normal(0, noise, n), index=idx) for e in eff]
    return out


class RulesTest(unittest.TestCase):
    def test_content(self):
        raw = placebo.compare(series({'H': 0, 'Hp': 0.01, 'Hpl': 0.0, 'Hpk': 0.0, 'Hag': 0.006, 'Hdfs': 0.003}))
        self.assertEqual((raw['reading'], raw['reading_keys']), ('content', 'content'))
        self.assertTrue(all(lo > 0 for _, lo, _ in raw['D']))
        self.assertAlmostEqual(raw['D'][0][0], 0.01, places=3)
        self.assertAlmostEqual(raw['share']['Hag'][0][0], 0.6, places=1)
        self.assertAlmostEqual(raw['share']['Hdfs'][1][0], 0.3, places=1)
        self.assertLess(abs(raw['P'][0][0]), 0.001)
        self.assertLess(abs(raw['Pk'][1][0]), 0.001)

    def test_placebo(self):
        raw = placebo.compare(series({'H': 0, 'Hp': 0.01, 'Hpl': 0.01, 'Hpk': 0.01, 'Hag': 0, 'Hdfs': 0}))
        self.assertEqual((raw['reading'], raw['reading_keys']), ('placebo', 'placebo'))
        self.assertTrue(all(lo <= 0 <= hi for _, lo, hi in raw['D']))
        self.assertAlmostEqual(raw['P'][0][0], 0.01, places=3)

    def test_everything_else_is_undecided(self):
        one_seed = series({'H': 0, 'Hp': 0.01, 'Hpl': (0.0, 0.01), 'Hpk': 0, 'Hag': 0, 'Hdfs': 0})
        below = series({'H': 0, 'Hp': 0.0, 'Hpl': 0.01, 'Hpk': 0, 'Hag': 0, 'Hdfs': 0})
        self.assertEqual(placebo.compare(one_seed)['reading'], 'undecided')
        self.assertEqual(placebo.compare(below)['reading'], 'placebo_better')  # both CIs below 0
        self.assertEqual(placebo.reading([(0.002, 0.0001, 0.004), (0.002, -0.0001, 0.004)]), 'undecided')
        self.assertEqual(placebo.reading([(-0.002, -0.004, -0.0001), (-0.002, -0.004, 0.0001)]), 'undecided')
        self.assertEqual(placebo.reading([(0.002, 0.0, 0.004)] * 2), 'placebo')  # a bound at 0 covers it

    def test_the_key_placebo_only_adds_its_reading_and_the_caveat(self):
        """Dk is read by the same rule; the headline stays D's; content by D with Dk short of rule 1 on a seed carries
        the caveat of the spec word for word."""
        self.assertEqual(placebo.CAVEAT, 'вывод о содержании не устойчив к плацебо по ключам')
        base, ds = {'H': 0, 'Hp': 0.01, 'Hag': 0.006, 'Hdfs': 0.003}, []
        for hpl, hpk, reading, keys, caveat in (
                (0.0, 0.0, 'content', 'content', None),
                (0.0, 0.01, 'content', 'placebo', placebo.CAVEAT),
                (0.0, (0.0, 0.01), 'content', 'undecided', placebo.CAVEAT),
                (0.0, 0.02, 'content', 'placebo_better', placebo.CAVEAT),  # the key placebo beats H+
                (0.01, 0.01, 'placebo', 'placebo', None),
                (0.01, 0.0, 'placebo', 'content', placebo.CAVEAT_KEYS),
                ((0.0, 0.01), 0.01, 'undecided', 'placebo', None)):
            with self.subTest(hpl=hpl, hpk=hpk):
                x = series(base | {'Hpl': hpl, 'Hpk': hpk})
                raw = placebo.compare(x)
                self.assertEqual((raw['reading'], raw['reading_keys']), (reading, keys))
                out = placebo.render(x, raw, [[2026, 0], [7, 1]])
                self.assertEqual((out['reading'], out['reading_keys'], out['caveat']),
                                 (placebo.READING[reading], placebo.READING_KEYS[keys], caveat))
                self.assertEqual([d['seed'] for d in out['Dk']], [[2026, 0], [7, 1]])
                want = (hpk if isinstance(hpk, tuple) else (hpk,) * 2)[0] - (hpl if isinstance(hpl, tuple) else (hpl,) * 2)[0]
                self.assertAlmostEqual(out['Hpk-Hpl'][0]['d'], want, places=3)
                if hpl == 0.0:
                    ds.append(raw['D'])
        self.assertTrue(all(d == ds[0] for d in ds))  # D does not depend on Hpk

    def test_claim_of_the_two_periods(self):
        self.assertEqual(placebo.claim({'2019': 'content', '2020': 'content'}),
                         {'claim': 'прирост H+ несёт содержание колонок, а не их число', 'periods': 'согласны'})
        self.assertEqual(placebo.claim({'2019': 'placebo', '2020': 'placebo'})['claim'],
                         'H+ не отличим от плацебо: утверждение о H+ снимается для обоих периодов')
        split = placebo.claim({'2019': 'content', '2020': 'placebo'})
        self.assertEqual(split['claim'], 'не решено')
        self.assertTrue(split['periods'].startswith('расходятся'))
        self.assertEqual(placebo.claim({'2019': 'undecided', '2020': 'undecided'})['claim'], 'не решено')
        self.assertEqual(placebo.claim({'2019': 'placebo_better', '2020': 'placebo_better'})['claim'],
                         'плацебо лучше H+: утверждение о H+ снимается для обоих периодов')
        against = placebo.claim({'2019': 'placebo', '2020': 'placebo_better'})  # counts against content
        self.assertEqual(against['claim'], 'H+ не отличим от плацебо: утверждение о H+ снимается для обоих периодов')
        self.assertEqual(against['periods'], 'расходятся: 2019 val B — «H+ не отличим от плацебо», '
                                             '2020 val — «плацебо лучше H+»')
        self.assertEqual(placebo.claim({'2019': 'content', '2020': 'placebo_better'})['claim'], 'не решено')


class ReaderTest(unittest.TestCase):
    """read() on fake per-query files and records of all 20 new runs of the check and the 4 reused ones."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.out = {p: t / p for p in placebo.OUT}
        self.decl = placebo.declared()
        effects = {'2019': {'H': 0, 'Hp': 0.01, 'Hpl': 0.0, 'Hpk': 0.01, 'Hag': 0.006, 'Hdfs': 0.003},
                   '2020': {'H': 0, 'Hp': 0.01, 'Hpl': 0.01, 'Hpk': 0.0, 'Hag': 0.006, 'Hdfs': 0.003}}
        grid = []
        for p, out in self.out.items():
            out.mkdir()
            x = series(effects[p], seed=int(p))
            users = np.array([int(q.split(':')[1]) for q in x['H'][0].index])
            records = []
            for arm in placebo.ARMS:
                for name, s in zip(placebo.names(p, arm), x[arm]):
                    res = pd.DataFrame({'qid': s.index, 'ndcg': s.to_numpy(), 'recall': s.to_numpy(),
                                        'half': exp.half(users)})
                    duckdb.sql(f"COPY (SELECT * FROM res) TO '{out / name}.parquet' (FORMAT PARQUET)")
                    rec = {'name': name, 'cfg': exp.DEFAULT | self.decl[name], 'features': placebo.FEATURES[arm],
                           'train_rows': 5174606}
                    if name.startswith('pl'):
                        rec |= {'fit_queries': placebo.FIT_QUERIES[p], 'permuted': placebo.PERMUTED.get(arm, 0),
                                'levels': placebo.LEVELS if arm == 'Hpk' else None,
                                'added_importance': 0.1, 'peak_rss_gb': 20.0, 'code': placebo.code_stamp(),
                                'libraries': placebo.libraries(),
                                'commit': 'abc', 'started': '2026-10-21 01:00:00',
                                'seconds': {'prepare': 1, 'fit': 1, 'predict': 1}}
                    records.append(rec)
            (out / 'runs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
            if p == '2019':
                b = exp.half(users) == 'B'
                for h, hp in zip(x['H'], x['Hp']):
                    d, lo, hi = M.bootstrap_diff(h[b], hp[b])
                    grid.append({'d': round(float(d), 5), 'ci': [round(float(lo), 5), round(float(hi), 5)]})
        (t / 'grid.json').write_text(json.dumps({'grid': {'Hp-H_by_seed': grid}}))
        self.patches = [mock.patch.object(placebo, 'OUT', self.out), mock.patch.object(placebo, 'RESULT', t / 'result.json'),
                        mock.patch.object(placebo, 'GRID_RESULT', t / 'grid.json'),
                        mock.patch.object(placebo, 'committed', return_value='head1')]
        for q in self.patches:
            q.start()

    def tearDown(self):
        for q in self.patches:
            q.stop()
        self.tmp.cleanup()

    def read(self):
        with contextlib.redirect_stdout(io.StringIO()):
            placebo.read()
        return json.loads(placebo.RESULT.read_text())

    def edit_record(self, period, name, change):
        path = self.out[period] / 'runs.jsonl'
        recs = [json.loads(x) for x in path.read_text().splitlines()]
        path.write_text(''.join(json.dumps(change(r) if r['name'] == name else r) + '\n' for r in recs))

    def test_result(self):
        res = self.read()
        self.assertEqual(res['2019']['reading'], 'прирост H+ несёт содержание колонок, а не их число')
        self.assertEqual(res['2020']['reading'], 'H+ не отличим от плацебо')
        self.assertEqual(res['claim'], 'не решено')
        self.assertTrue(res['periods'].startswith('расходятся'))
        self.assertLess(res['2019']['queries'], res['2020']['queries'])  # half B against all of val
        self.assertEqual(res['2019']['runs']['Hp'], ['grid_Hp_s0', 'grid_Hp_s1'])
        self.assertEqual([d['seed'] for d in res['2019']['D']], [[2026, 0], [7, 1]])
        self.assertAlmostEqual(res['2019']['share']['Hag'][0]['r'], 0.6, places=1)
        self.assertEqual(len(res['fits']), 20)
        self.assertEqual(res['2019']['runs']['Hpk'], ['pl19_Hpk_s0', 'pl19_Hpk_s1'])
        self.assertEqual(res['2019']['reading_keys'], 'H+ не отличим от плацебо по ключам')
        self.assertEqual(res['2019']['caveat'], 'вывод о содержании не устойчив к плацебо по ключам')
        self.assertEqual((res['2020']['reading_keys'], res['2020']['caveat']), ('H+ лучше плацебо по ключам', placebo.CAVEAT_KEYS))
        self.assertAlmostEqual(res['2019']['Pk'][0]['d'], 0.01, places=3)
        self.assertEqual(res['levels'], placebo.LEVELS)
        self.assertEqual((res['code'], res['libraries']), (placebo.code_stamp(), placebo.libraries()))
        self.assertEqual(res['read']['commit'], 'head1')
        self.assertEqual(res['caveats'], {'2019': 'вывод о содержании не устойчив к плацебо по ключам',
                                          '2020': placebo.CAVEAT_KEYS})
        self.assertAlmostEqual(res['2019']['Hpk-Hpl'][1]['d'], 0.01, places=3)
        self.assertFalse(list(placebo.RESULT.parent.glob('.*.tmp')))
        self.assertEqual(res['fits']['pl20_Hpl_s1']['commit'], 'abc')
        self.assertEqual(res['spec_sha256'], hashlib.sha256((placebo.DIR / 'spec.md').read_bytes()).hexdigest())
        written = placebo.RESULT.stat().st_mtime_ns
        with mock.patch.object(placebo, 'committed', return_value='head2'):
            self.read()  # the same result again, after the result's own commit: the file is left as it is
        self.assertEqual(placebo.RESULT.stat().st_mtime_ns, written)
        placebo.RESULT.write_text(placebo.RESULT.read_text().replace('не решено', 'решено'))
        with self.assertRaisesRegex(SystemExit, 'says something else'):
            self.read()

    def test_a_missing_run_stops_before_reading(self):
        (self.out['2020'] / 'pl20_Hdfs_s1.parquet').unlink()
        self.edit_record('2019', 'pl19_Hpk_s0', lambda r: r | {'name': 'pl19_Hpk_s0_old'})
        with mock.patch.object(duckdb, 'sql', side_effect=AssertionError('a metric was read')), \
                self.assertRaisesRegex(SystemExit, r"\['pl19_Hpk_s0', 'pl20_Hdfs_s1'\]"):
            self.read()
        self.assertFalse(placebo.RESULT.exists())

    def test_checks_stop_it(self):
        cases = [('2019', 'q3_d8_s1', lambda r: r | {'cfg': r['cfg'] | {'depth': 6}}, 'differs from its declaration'),
                 ('2020', 'pl20_Hpl_s0', lambda r: r | {'cfg': {k: v for k, v in r['cfg'].items() if k != 'permute'}},
                  'differs from its declaration'),
                 ('2019', 'pl19_Hag_s0', lambda r: r | {'features': 145}, '145 features'),
                 ('2020', 'pl20_Hpl_s1', lambda r: r | {'permuted': 0}, 'permuted 0 columns'),
                 ('2020', 'pl20_H_s0', lambda r: r | {'fit_queries': 140680}, 'fit on 140680'),
                 ('2020', 'pl20_H_s1', lambda r: r | {'train_rows': 1}, 'different numbers of rows'),
                 ('2020', 'pl20_Hag_s0', lambda r: r | {'commit': None}, 'commit None'),
                 ('2019', 'pl19_Hdfs_s1', lambda r: r | {'code': {'task1/placebo.py': 'v2'}}, 'versions of the code'),
                 ('2020', 'pl20_Hpk_s1', lambda r: r | {'cfg': r['cfg'] | {'permute': 'within_day'}},
                  'differs from its declaration'),
                 ('2019', 'pl19_Hpk_s0', lambda r: r | {'permuted': 193}, 'permuted 193 columns'),
                 ('2020', 'pl20_Hpk_s0', lambda r: r | {'levels': None}, 'tables by level differ'),
                 ('2019', 'pl19_Hpk_s1', lambda r: r | {'levels': r['levels'] | {
                     'user': [], 'product': ['dfs_u'] + r['levels']['product']}}, 'tables by level differ'),
                 ('2019', 'pl19_Hpl_s0', lambda r: r | {'levels': placebo.LEVELS}, 'tables by level differ'),
                 ('2020', 'pl20_Hag_s1', lambda r: r | {'libraries': r['libraries'] | {'numpy': '0.0'}},
                  'sets of library versions')]
        for period, name, change, message in cases:
            with self.subTest(name=name):
                path = self.out[period] / 'runs.jsonl'
                kept = path.read_text()
                self.edit_record(period, name, change)
                with self.assertRaisesRegex(SystemExit, message):
                    self.read()
                path.write_text(kept)
        with mock.patch.object(placebo, 'libraries', return_value={'numpy': '0.0'}), \
                self.assertRaisesRegex(SystemExit, 'differ from those of the runs'):
            self.read()
        self.assertFalse(placebo.RESULT.exists())

    def test_reading_needs_a_clean_tree_and_the_code_of_the_runs(self):
        with mock.patch.object(placebo, 'committed', side_effect=SystemExit('commit the spec')), \
                self.assertRaisesRegex(SystemExit, 'commit the spec'):
            self.read()
        stamp = placebo.code_stamp()
        with tempfile.TemporaryDirectory() as root:  # the code of the runs, then one rule edited after them
            for f in placebo.CODE:
                (Path(root) / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / f, Path(root) / f)
            with mock.patch.object(M, 'ROOT', Path(root)):
                self.assertEqual(placebo.code_stamp(), stamp)
                code = Path(root) / 'task1/placebo.py'
                code.write_text(code.read_text().replace("if all(hi < 0 for _, _, hi in d_by_seed):",
                                                         "if all(hi < 0.001 for _, _, hi in d_by_seed):"))
                with self.assertRaisesRegex(SystemExit, 'differs from the code of the runs'):
                    self.read()
        self.assertFalse(placebo.RESULT.exists())

    def test_the_arms_of_a_seed_share_its_seeds(self):
        decl = self.decl | {'pl20_Hag_s1': self.decl['pl20_Hag_s1'] | {'seed': 8}}
        self.edit_record('2020', 'pl20_Hag_s1', lambda r: r | {'cfg': r['cfg'] | {'seed': 8}})
        with mock.patch.object(placebo, 'declared', return_value=decl), \
                self.assertRaisesRegex(SystemExit, 'differ in seeds'):
            self.read()

    def test_the_2019_runs_must_give_the_grid_result(self):
        g = json.loads(placebo.GRID_RESULT.read_text())
        g['grid']['Hp-H_by_seed'][1]['d'] += 0.00001
        placebo.GRID_RESULT.write_text(json.dumps(g))
        with self.assertRaisesRegex(SystemExit, 'differs from the grid result'):
            self.read()


if __name__ == '__main__':
    unittest.main()
