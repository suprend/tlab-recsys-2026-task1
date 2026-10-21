"""Tests of scripts/xfer_sber.py on synthetic fixtures (docs/xfer-sber-design.md, section 9)."""
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from scripts import xfer_common as xc
from scripts import xfer_sber as xs

NUMBER = re.compile(r'(?<![A-Za-z0-9_.@])\d+(?:\.\d+)?(?![A-Za-z0-9_])')
A = '2020-08-05'
PRODUCTS = list(range(1, 121))
CANARY_AT_A = 203       # only bought exactly at A = 2020-08-05 00:00:00
CANARY_HOLDOUT = 201    # only bought on or after 2020-09-02
HEADLESS_ITEM = 202     # only on lines without an order header
NULL_PRODUCT = 30       # never has a category
AT_END = 204            # only in an order at A + W - 1 second (2020-08-18 23:59:59)
BEFORE_HOLDOUT = 205    # only at 2020-09-01 23:59:59
AT_HOLDOUT = 206        # only at 2020-09-02 00:00:00
STORES = {1: ('Alpha', 'Moscow'), 2: ('Beta', 'Kazan'), 3: ('Gamma', 'Omsk'), 4: ('Alpha', 'Abakan'),
          5: ('Delta', 'Tver'), 6: ('Epsilon', 'Ufa')}


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


def category(product):
    return None if product in (NULL_PRODUCT, HEADLESS_ITEM) else product % 6 + 1


class Raw:
    """Synthetic raw files in the layout of data/raw-sbermarket-kaggle."""

    def __init__(self, seed=7, users=40, future=True):
        self.rng = np.random.default_rng(seed)
        self.orders, self.lines = [], []
        self.order_id, self.line_id = 1000, 50_000
        start = pd.Timestamp('2020-05-01')
        weights = np.array([p ** -0.6 for p in PRODUCTS])
        weights = weights / weights.sum()
        for u in range(1, users+1):
            day = float(self.rng.integers(0, 10))
            favourites = list(self.rng.choice(PRODUCTS, size=3, replace=False))
            while day < 152:
                ts = start + pd.Timedelta(days=day, seconds=int(self.rng.integers(3600, 80000)))
                store = 1 if u % 2 else 2
                if self.rng.random() < 0.2:
                    store = 3 - store
                if ts >= pd.Timestamp('2020-09-05') and self.rng.random() < 0.3:
                    store = 3 if u % 2 else 4
                items = set(int(x) for x in self.rng.choice(PRODUCTS, size=int(self.rng.integers(2, 7)),
                                                            replace=False, p=weights))
                items |= {int(f) for f in favourites if self.rng.random() < 0.5}
                if ts >= pd.Timestamp('2020-09-03') and u % 4 == 0:
                    items.add(CANARY_HOLDOUT)
                self.add(u, ts, store, sorted(items))
                day += float(self.rng.integers(4, 10))
        self.crafted()
        if not future:
            # The same draws without every order from A on (headerless lines stay).
            late = {o[1] for o in self.orders if pd.Timestamp(o[2]) >= pd.Timestamp(A)}
            self.orders = [o for o in self.orders if o[1] not in late]
            self.lines = [r for r in self.lines if r[1] not in late]

    def add(self, user, ts, store, items, order_id=None, header=True, lines=True, qty=None, null_cat=()):
        if order_id is None:
            self.order_id += 1
            order_id = self.order_id
        ts = pd.Timestamp(ts)
        if header:
            retailer = STORES[store][0]
            self.orders.append((user, order_id, ts.strftime('%Y-%m-%d %H:%M:%S'), retailer, store,
                                'app' if user % 3 else 'web'))
        if lines:
            for item in items:
                self.line_id += 1
                price = float(self.rng.integers(10, 500)) + 0.5
                discount = 0.0 if self.rng.random() < 0.7 else round(float(self.rng.uniform(-3, 30)), 2)
                cat = None if item in null_cat else category(item)
                quantity = (qty or {}).get(item, int(self.rng.integers(1, 4)))
                self.lines.append((user, order_id, self.line_id, price, quantity, discount, f'Name {item}, kg', item,
                                   '' if item % 5 == 0 else f'Brand{item % 7}', '' if cat is None else f'{cat}.0',
                                   '' if cat is None else str(cat // 3)))
        return order_id

    def crafted(self):
        # 101: history, an order exactly at A with CANARY_AT_A (history must not see it, the target must).
        self.add(101, '2020-07-20 10:00:00', 1, [1, 2, 3])
        self.add(101, '2020-08-05 00:00:00', 1, [CANARY_AT_A, 2])
        # 102: two window orders at the same ts; the smaller order_id is the first one.
        self.add(102, '2020-07-21 10:00:00', 2, [4, 5])
        self.add(102, '2020-08-07 12:00:00', 2, [8], order_id=900_002)
        self.add(102, '2020-08-07 12:00:00', 2, [9, 10], order_id=900_001)
        # 103: two orders at each retailer, the latest at Beta -> Beta.
        for ts, store in (('2020-07-01', 1), ('2020-07-02', 1), ('2020-07-03', 2), ('2020-07-04 12:00', 2)):
            self.add(103, ts, store, [11])
        # 104: two orders at each retailer, the latest ones at the same ts -> name order, Alpha.
        for ts, store in (('2020-07-01', 2), ('2020-07-02', 1), ('2020-07-04 12:00', 2), ('2020-07-04 12:00', 1)):
            self.add(104, ts, store, [12])
        # 105: a repeated header (Beta store 2 and Alpha store 1) -> Alpha store 1.
        oid = self.add(105, '2020-07-10 09:00:00', 2, [13], header=True)
        self.add(105, '2020-07-10 09:00:00', 1, [], order_id=oid, lines=False)
        self.repeated_header = oid
        # 106: product 5 on two lines of one order (qty 2 and 3) and in another order (qty 1);
        # in the window, product 7 twice in the first order.
        oid = self.add(106, '2020-07-11 09:00:00', 1, [5], qty={5: 2})
        self.add(106, None, None, [5], order_id=oid, header=False, qty={5: 3})
        self.add(106, '2020-07-15 09:00:00', 1, [5, 6], qty={5: 1})
        oid = self.add(106, '2020-08-06 09:00:00', 1, [7])
        self.add(106, None, None, [7], order_id=oid, header=False)
        # 107: two orders; product 29 on a line with NULL category, product 30 has no category at all.
        self.add(107, '2020-07-12 09:00:00', 1, [29], null_cat={29})
        self.add(107, '2020-07-13 09:00:00', 1, [NULL_PRODUCT])
        self.add(110, '2020-06-01 09:00:00', 1, [29])   # cat(29) is known from this line
        # 108: a header without lines only (retailer Delta, store 5).
        self.add(108, '2020-07-01 09:00:00', 5, [], lines=False)
        # 109: lines without a header only.
        self.add(109, None, None, [HEADLESS_ITEM, 1], order_id=700_001, header=False)
        # 111: a main retailer (Epsilon) with fewer than K window products.
        for ts, items in (('2020-07-20 10:00', [1, 2, 3]), ('2020-07-25 10:00', [2, 4]), ('2020-08-01 10:00', [5])):
            self.add(111, ts, 6, items)
        # 112: many more repeat products than repeat_depth, mostly from the tail.
        tail = list(range(61, 121))
        for i in range(6):
            self.add(112, pd.Timestamp('2020-07-10 10:00') + pd.Timedelta(days=4*i), 1, tail[i*7: i*7 + 30])
        # 113: the only order from A on is at A + W exactly; 114: at A + W - 1 second.
        self.add(113, '2020-07-20 10:00:00', 1, [1, 2])
        self.add(113, '2020-08-19 00:00:00', 1, [3])
        self.add(114, '2020-07-20 10:00:00', 1, [1, 2])
        self.add(114, '2020-08-18 23:59:59', 1, [AT_END])
        # 115: one second before the holdout anchor and exactly at it.
        self.add(115, '2020-07-20 10:00:00', 2, [1])
        self.add(115, '2020-09-01 23:59:59', 2, [BEFORE_HOLDOUT])
        self.add(115, '2020-09-02 00:00:00', 2, [AT_HOLDOUT])
        # 116: an order every day of 2020-03-01 .. 2020-04-30 at 00:30, so that A - 120 days has data.
        for day in pd.date_range('2020-03-01', '2020-04-30'):
            self.add(116, day + pd.Timedelta(minutes=30), 2, [1])

    def write(self, raw, mutate=None):
        raw = Path(raw)
        (raw/'kaggle_tab_1345').mkdir(parents=True)
        (raw/'sbermarket_tab_2_1').mkdir()
        (raw/'sbermarket_tab_2_2').mkdir()
        files = {}

        def table(name, header, rows):
            path = raw/name
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream, lineterminator='\n')
                writer.writerow(header)
                writer.writerows(rows)
            files[name] = path
        table(xs.ORDERS_FILE, [c for c, _ in xs.RAW_ORDERS], self.orders)
        header = [c for c, _ in xs.RAW_LINES]
        table('sbermarket_tab_2_1/tab_2_products_2020-05-01.csv', header, self.lines[: len(self.lines)//2])
        table('sbermarket_tab_2_2/tab_2_products_2020-08-01.csv', header, self.lines[len(self.lines)//2:])
        table(xs.CATEGORIES_FILE, ['id', 'name', 'parent_id'],
              [(i, f'Category {i}', 0) for i in range(1, 8)])
        table(xs.CITY_FILE, ['store_id', 'city_name'], [(s, c) for s, (_, c) in STORES.items()])
        self.submission = list(range(1, 31)) + [108, 109, 999]
        table(xs.SUBMISSION_FILE, ['Id', 'Predicted'], [(u, ' '.join(str(p) for p in range(1, 51)))
                                                        for u in self.submission])
        table('kaggle_tab_1345/tab_4_user_profiles.csv', ['user_id', 'gender'], [(1, 'x')])
        if mutate:
            mutate(raw)
        verify = dict(files=[dict(name=name, sha256=xc.sha256_file(path), matches=True)
                             for name, path in sorted(files.items())])
        (raw/xs.VERIFY_FILE).write_text(json.dumps(verify))
        return raw


class Env:
    """A temporary git root with synthetic raw files and a finished load."""

    def __init__(self, raw=None):
        self.raw_data = raw or Raw()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q')
        (self.root/'configs'/'datasets').mkdir(parents=True)
        (self.root/'artifacts'/'xfer').mkdir(parents=True)
        (self.root/'README').write_text('x')
        git(self.root, 'add', 'README')
        git(self.root, 'commit', '-q', '-m', 'init')
        self.patches = [mock.patch.object(xc, 'ROOT', self.root),
                        mock.patch.object(xc, 'code_identity', lambda dataset: {'scripts/xfer_sber.py': 'x'})]
        for p in self.patches:
            p.start()
        self.raw = self.raw_data.write(self.root/'raw')
        self.report = xs.load(self.raw, xc.output_dir('sber', 'load'), threads=2, memory='2GB')

    def close(self):
        for p in reversed(self.patches):
            p.stop()
        for path in self.root.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        self.tmp.cleanup()

    def commit(self, *paths):
        git(self.root, 'add', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def config(self, kind, value):
        path = xc.config_path('sber', kind)
        path.write_text(json.dumps(value) if not isinstance(value, str) else value)
        self.commit(path)
        return path


def small_base():
    return xs.initial_base(per_query=60, repeat_depth=10, pop_retailer_depth=50, window_days=28)


class EnvCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = Env()
        cls.base = small_base()

    @classmethod
    def tearDownClass(cls):
        cls.env.close()

    def out(self, name):
        return xc.output_dir('sber', 'base-dev', name)

    def frame(self, path):
        return xc.read_parquet(Path(path)/xc.FRAME_FILE)


# ---------------------------------------------------------------- load

class Load(EnvCase):
    def test_facts_and_exclusions(self):
        facts = self.env.report['facts']
        self.assertEqual(self.env.report['status'], 'completed')
        self.assertEqual(facts['orders']['orders_without_lines'], 1)   # the header of 108
        self.assertEqual(facts['lines']['orders_without_header'], 1)
        self.assertEqual(facts['orders']['repeated_order_ids'], 1)
        self.assertEqual(facts['lines']['repeated_order_product_pairs'], 2)
        con = duckdb.connect(str(xc.events_path('sber')['db']), read_only=True)
        try:
            self.assertEqual(con.execute('SELECT count(*) FROM orders WHERE user_id IN (108, 109)').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT count(*) FROM lines WHERE user_id IN (108, 109) OR product_id = ?',
                                         [HEADLESS_ITEM]).fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT typeof(master_category_id) FROM lines LIMIT 1').fetchone()[0], 'BIGINT')
        finally:
            con.close()

    def test_one_header_per_order(self):
        con = duckdb.connect()
        try:
            spec = xs.views(A, 'agent')
            con.execute(f"CREATE VIEW orders AS {spec['views']['orders']}")
            raw = xs._event_view([f for f in spec['files'] if '/orders/' in f], xs.VIEW_SCHEMA['orders'], xs._date(A))
            shift = con.execute(f'SELECT min(order_id) FROM ({raw})').fetchone()[0]   # views shift ids to the window
            rows = con.execute('SELECT retailer, store_id FROM orders WHERE order_id = ?',
                               [self.env.raw_data.repeated_header - shift]).fetchall()
            self.assertEqual(rows, [('r01', 1)])
            self.assertEqual(con.execute('SELECT count(*) - count(DISTINCT order_id) FROM orders').fetchone()[0], 0)
        finally:
            con.close()

    def test_codes_monotone_and_early_only(self):
        st = duckdb.connect(str(xc.static_path('sber')), read_only=True)
        try:
            retailers = st.execute('SELECT code, retailer FROM retailer_codes ORDER BY code').fetchall()
            cities = st.execute('SELECT code, city_name FROM city_codes ORDER BY code').fetchall()
        finally:
            st.close()
        # Early (before 2020-09-02): Alpha, Beta, Epsilon; late: Gamma. Delta has no order with lines.
        self.assertEqual(retailers, [('r01', 'Alpha'), ('r02', 'Beta'), ('r03', 'Epsilon'), ('r04', 'Gamma')])
        # Early: Kazan, Moscow, Ufa; late: Abakan, Omsk (by name after the early ones).
        self.assertEqual(cities, [('c001', 'Kazan'), ('c002', 'Moscow'), ('c003', 'Ufa'), ('c004', 'Abakan'),
                                  ('c005', 'Omsk')])
        con = xs.history(A, 'collect')
        try:
            base_codes = con.execute('SELECT DISTINCT retailer FROM orders ORDER BY 1').fetchall()
        finally:
            con.close()
        agent = duckdb.connect()
        try:
            agent_codes = agent.execute(f"SELECT DISTINCT retailer FROM ({xs.views(A, 'agent')['views']['orders']}) "
                                        'ORDER BY 1').fetchall()
        finally:
            agent.close()
        self.assertEqual(base_codes, agent_codes)
        self.assertEqual(base_codes, [('r01',), ('r02',), ('r03',)])

    def test_partitions_read_only_and_listed(self):
        parts = Path(xc.events_path('sber')['parts'])
        files = sorted(p.relative_to(parts).as_posix() for p in parts.rglob('*.parquet'))
        self.assertEqual(files, sorted(self.env.report['partitions']))
        self.assertTrue(all(not (p.stat().st_mode & 0o222) for p in parts.rglob('*.parquet')))


class LoadRefusals(unittest.TestCase):
    def run_load(self, mutate=None, after=None):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name).resolve()
        (root/'artifacts'/'xfer').mkdir(parents=True)
        try:
            with mock.patch.object(xc, 'ROOT', root):
                raw = Raw(users=6).write(root/'raw', mutate)
                if after:
                    after(raw)
                xs.load(raw, xc.output_dir('sber', 'load'), threads=1, memory='1GB')
        finally:
            for path in root.rglob('*'):
                path.chmod(0o700 if path.is_dir() else 0o600)
            tmp.cleanup()

    def test_hash_mismatch(self):
        def after(raw):
            with (raw/xs.CITY_FILE).open('a') as stream:
                stream.write('6,Extra\n')
        with self.assertRaisesRegex(xc.ContractError, 'SHA-256'):
            self.run_load(after=after)

    def test_header_mismatch(self):
        def mutate(raw):
            path = raw/xs.CITY_FILE
            path.write_text(path.read_text().replace('store_id,city_name', 'store,city_name', 1))
        with self.assertRaisesRegex(xc.ContractError, 'Header'):
            self.run_load(mutate)

    def test_category_not_integer(self):
        def mutate(raw):
            path = raw/'sbermarket_tab_2_1'/'tab_2_products_2020-05-01.csv'
            rows = list(csv.reader(io.StringIO(path.read_text())))
            row = next(r for r in rows[1:] if r[9])
            row[9] = '2.5'
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator='\n').writerows(rows)
            path.write_text(buffer.getvalue())
        with self.assertRaisesRegex(xc.ContractError, 'not integer'):
            self.run_load(mutate)

    def test_listed_files_must_match(self):
        def after(raw):
            (raw/'sbermarket_tab_2_2'/'tab_2_products_2020-09-01.csv').write_text('x\n')
        with self.assertRaisesRegex(xc.ContractError, 'differ'):
            self.run_load(after=after)


# ---------------------------------------------------------------- barrier

class Barrier(EnvCase):
    def test_order_at_A_invisible(self):
        con = xs.history(A, 'collect')
        try:
            self.assertEqual(con.execute('SELECT count(*) FROM lines WHERE product_id = ?', [CANARY_AT_A]).fetchone()[0], 0)
            self.assertLess(con.execute('SELECT max(ts) FROM orders').fetchone()[0], pd.Timestamp(A))
        finally:
            con.close()
        spec = xs.views(A, 'agent')
        con = duckdb.connect()
        try:
            for name, sql in spec['views'].items():
                con.execute(f'CREATE VIEW {name} AS {sql}')
            self.assertEqual(con.execute('SELECT count(*) FROM lines WHERE product_id = ?', [CANARY_AT_A]).fetchone()[0], 0)
            self.assertEqual(con.execute(f"SELECT count(*) FROM ({spec['items']}) WHERE product_id = ?",
                                         [CANARY_AT_A]).fetchone()[0], 0)
        finally:
            con.close()
        self.assertTrue(all('d=2020-08-05' not in f and 'd=2020-08-06' not in f for f in spec['files']))
        out = self.out('canary-a')
        xs.collect(A, 'train', self.base, out)
        frame = self.frame(out)
        self.assertNotIn(CANARY_AT_A, set(frame['item_id']))
        targets = xc.read_parquet(out/'labels.parquet')
        self.assertTrue(bool(targets[(targets.user_id == 101) & (targets.item_id == CANARY_AT_A)].empty))
        target_pairs = self.window_targets(101)
        self.assertIn(CANARY_AT_A, target_pairs)

    def window_targets(self, user):
        con = duckdb.connect(str(xc.events_path('sber')['db']), read_only=True)
        try:
            first = con.execute("""SELECT order_id FROM orders WHERE user_id = ? AND ts >= TIMESTAMP '2020-08-05'
                ORDER BY ts, order_id LIMIT 1""", [user]).fetchone()[0]
            return {r[0] for r in con.execute('SELECT product_id FROM lines WHERE order_id = ?', [first]).fetchall()}
        finally:
            con.close()

    def test_holdout_canary(self):
        for purpose in ('collect', 'collect-kaggle', 'agent', 'probe', 'pop'):
            with self.assertRaisesRegex(xc.ContractError, 'Holdout window closed'):
                xs.history('2020-09-03', purpose)
            with self.assertRaisesRegex(xc.ContractError, 'Holdout window closed'):
                xs.views('2020-09-03', purpose)
        con = xs.history(xs.HOLDOUT_ANCHOR, 'collect')
        try:
            seen = {r[0] for r in con.execute('SELECT product_id FROM lines WHERE product_id IN (?, ?, ?)',
                                              [CANARY_HOLDOUT, BEFORE_HOLDOUT, AT_HOLDOUT]).fetchall()}
            self.assertEqual(seen, {BEFORE_HOLDOUT})
            self.assertEqual(con.execute("SELECT max(ts) FROM orders WHERE user_id = 115").fetchone()[0],
                             pd.Timestamp('2020-09-01 23:59:59'))
        finally:
            con.close()
        spec = xs.views(xs.HOLDOUT_ANCHOR, 'agent')
        days = [d for f in spec['files'] for d in re.findall(r'd=([0-9-]{10})', f)]
        self.assertTrue(days and max(days) < xs.HOLDOUT_ANCHOR)
        con = duckdb.connect()
        try:
            for name, sql in spec['views'].items():
                con.execute(f'CREATE VIEW {name} AS {sql}')
            seen = {r[0] for r in con.execute('SELECT product_id FROM lines WHERE product_id IN (?, ?, ?)',
                                              [CANARY_HOLDOUT, BEFORE_HOLDOUT, AT_HOLDOUT]).fetchall()}
            self.assertEqual(seen, {BEFORE_HOLDOUT})
            self.assertEqual(con.execute(f"SELECT count(*) FROM ({spec['items']}) WHERE product_id = ?",
                                         [AT_HOLDOUT]).fetchone()[0], 0)
        finally:
            con.close()
        # The holdout path is checked first; at the right path the window is closed (no prereg).
        with self.assertRaisesRegex(xc.ContractError, 'current holdout collection'):
            xs.collect(xs.HOLDOUT_ANCHOR, 'holdout', self.base, self.out('holdout-closed'))
        right = xc.current_holdout_collection('sber', xs.HOLDOUT_ANCHOR)
        with self.assertRaisesRegex(xc.ContractError, 'Holdout window closed'):
            xs.collect(xs.HOLDOUT_ANCHOR, 'holdout', self.base, right)
        self.assertFalse(right.exists())

    def test_collect_holdout_reads_no_further_than_window(self):
        # The bound is checked before the window, so it holds even with the window open.
        with mock.patch.object(xc, 'require_window', lambda *args: None):
            with self.assertRaisesRegex(xc.ContractError, 'no further than'):
                xs.history(xs._shift(xs.HOLDOUT_ANCHOR, xs.W + 1), 'collect-holdout')

    def test_output_refusals_before_history(self):
        def boom(*args, **kwargs):
            raise AssertionError('history was called')
        with mock.patch.object(xs, 'history', boom):
            with self.assertRaisesRegex(xc.ContractError, 'current holdout collection'):
                xs.collect(xs.HOLDOUT_ANCHOR, 'holdout', self.base, self.out('x'))
            existing = self.out('existing')
            existing.mkdir(parents=True)
            for role, anchor, users in (('train', A, None), ('holdout', xs.HOLDOUT_ANCHOR, None),
                                        ('probe', xs.PROBE_ANCHOR, [1]), ('kaggle', xs.KAGGLE_ANCHOR, None)):
                with self.subTest(role), self.assertRaisesRegex(xc.ContractError, 'exists'):
                    xs.collect(anchor, role, self.base, existing, users=users)
            with self.assertRaisesRegex(xc.ContractError, 'user restriction'):
                xs.collect(A, 'train', self.base, xc.output_dir('sber', 'collections', 'train-x'), users=[1])
        self.assertFalse(xc.output_dir('sber', 'collections', 'train-x').exists())

    def test_agent_views_start_at_A_minus_120_days(self):
        for anchor in ('2020-08-05', '2020-08-19'):
            with self.subTest(anchor):
                spec = xs.views(anchor, 'agent')
                since = pd.Timestamp(anchor) - pd.Timedelta(days=xs.AGENT_DAYS)
                days = sorted(d for f in spec['files'] for d in re.findall(r'd=([0-9-]{10})', f))
                self.assertEqual(days[0], since.strftime('%Y-%m-%d'))
                self.assertLess(days[-1], anchor)
                con = duckdb.connect()
                try:
                    for name, sql in spec['views'].items():
                        con.execute(f'CREATE VIEW {name} AS {sql}')
                    for table in ('orders', 'lines'):
                        low = con.execute(f'SELECT min(ts) FROM {table}').fetchone()[0]
                        self.assertGreaterEqual(low, since)
                        self.assertLess(low - since, pd.Timedelta(days=1))
                finally:
                    con.close()
                hist = xs.history(anchor, 'collect')   # the base keeps the whole history
                try:
                    self.assertEqual(hist.execute('SELECT min(ts) FROM orders').fetchone()[0],
                                     pd.Timestamp('2020-03-01 00:30'))
                finally:
                    hist.close()

    def test_agent_views_shift_ids_to_the_window(self):
        # order_id and line_item_id grow with time: views shift them by their minimum over the whole window,
        # order_id by that of orders in both tables, so the join of orders and lines is kept.
        for anchor in ('2020-08-05', '2020-08-19'):
            with self.subTest(anchor):
                spec = xs.views(anchor, 'agent')
                since = pd.Timestamp(anchor) - pd.Timedelta(days=xs.AGENT_DAYS)
                con = duckdb.connect()
                try:
                    for name, sql in spec['views'].items():
                        con.execute(f'CREATE VIEW {name} AS {sql}')
                    for table in ('orders', 'lines'):
                        table_files = [f for f in spec['files'] if f'/{table}/' in f]
                        self.assertTrue(table_files)
                        raw = xs._event_view(table_files, xs.VIEW_SCHEMA[table], pd.Timestamp(anchor).date(),
                                             since.date())
                        con.execute(f'CREATE VIEW raw_{table} AS {raw}')
                    self.assertEqual(con.execute('SELECT min(order_id) FROM orders').fetchone()[0], 0)
                    self.assertEqual(con.execute('SELECT min(line_item_id) FROM lines').fetchone()[0], 0)
                    join = 'SELECT count(*) FROM {0}orders o JOIN {0}lines l ON l.order_id = o.order_id'
                    shifted, plain = (con.execute(join.format(p)).fetchone()[0] for p in ('', 'raw_'))
                    self.assertGreater(plain, 0)
                    self.assertEqual(shifted, plain)
                    # One shift for the whole window: every row moves by the same amount.
                    for table, column, base in (('orders', 'order_id', 'orders'), ('lines', 'order_id', 'orders'),
                                                ('lines', 'line_item_id', 'lines')):
                        shifted = con.execute(f'SELECT list_sort(list({column})) FROM {table}').fetchone()[0]
                        expected = con.execute(f'SELECT list_sort(list({column} - (SELECT min({column}) FROM '
                                               f'raw_{base}))) FROM raw_{table}').fetchone()[0]
                        self.assertTrue(shifted)
                        self.assertEqual(shifted, expected, (table, column))
                finally:
                    con.close()

    def test_collect_holdout_purpose_only_in_collect(self):
        tree = ast.parse(Path(xs.__file__).read_text(encoding='utf-8'))
        owners, compared = [], []
        for func in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(func):
                if isinstance(node, ast.Constant) and node.value == 'collect-holdout':
                    owners.append(func.name)
                if isinstance(node, ast.Compare) and any(isinstance(c, ast.Constant) and c.value == 'collect-holdout'
                                                         for c in [node.left, *node.comparators]):
                    compared.append(func.name)
        # collect is the only one to use the purpose; history only compares with it (its read bound).
        self.assertEqual(sorted(owners), ['collect', 'history'])
        self.assertEqual(compared, ['history'])

    def test_static_literals(self):
        tree = ast.parse(Path(xs.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn('sealed', node.value)
                self.assertNotIn('events.duckdb', node.value)
                self.assertFalse('events' in node.value.replace('\\', '/').split('/') and '/' in node.value)


class FutureInvariance(unittest.TestCase):
    def test_frame_independent_of_events_from_A(self):
        frames = []
        for future in (True, False):
            env = Env(Raw(future=future))
            try:
                pool = sorted(set(range(1, 41)) | {101, 103, 104, 105, 106, 107})
                con = xs.history(A, 'collect')
                try:
                    xs._build_frame(con, small_base(), A, pool)
                    frames.append(con.execute('SELECT * FROM frame_rows ORDER BY user_id, item_id').df())
                finally:
                    con.close()
                views = xs.views(A, 'agent')
                frames.append(len(views['files']))
            finally:
                env.close()
        pd.testing.assert_frame_equal(frames[0], frames[2])
        self.assertEqual(frames[1], frames[3])


# ---------------------------------------------------------------- collections

class Collect(EnvCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.train = xc.output_dir('sber', 'base-dev', 'train')
        cls.manifest = xs.collect(A, 'train', cls.base, cls.train)

    def test_frame_columns_and_union(self):
        frame = self.frame(self.train)
        self.assertEqual(list(frame.columns), ['user_id', 'item_id', *xc.base_feature_names(self.base)])
        self.assertFalse(frame.duplicated(['user_id', 'item_id']).any())
        self.assertTrue((frame.groupby('user_id').size() == 60).all())
        self.assertTrue(frame.equals(frame.sort_values(['user_id', 'item_id']).reset_index(drop=True)))
        sources = xc.read_parquet(self.train/'sources.parquet')
        self.assertEqual(set(sources['source']), {'repeat', 'pop_retailer', 'global'})
        # Every repeat source row has repeat_rank <= depth; pop-retailer rows have popr_rank <= depth.
        merged = frame.merge(sources, on=['user_id', 'item_id'])
        self.assertTrue((merged[merged.source == 'repeat']['repeat_rank'] <= 10).all())
        self.assertTrue((merged[merged.source == 'pop_retailer']['popr_rank'] <= 50).all())
        other = merged[merged.source != 'repeat']['repeat_rank']
        self.assertTrue((other.isna() | (other > 10)).all())
        self.assertEqual(self.manifest['counts']['rows'], len(frame))

    def test_labels_and_targets(self):
        labels = xc.read_parquet(self.train/'labels.parquet')
        targets = xc.read_parquet(self.train/'targets.parquet')
        frame = self.frame(self.train)
        self.assertEqual(len(labels), len(frame))
        self.assertTrue((labels[['user_id', 'item_id']].to_numpy() == frame[['user_id', 'item_id']].to_numpy()).all())
        self.assertEqual(set(targets['user_id']), set(frame['user_id']))
        # 102: first window order by order_id at equal ts -> {9, 10}.
        self.assertEqual(int(targets.set_index('user_id').loc[102, 'n_targets']), 2)
        positives = set(labels[(labels.user_id == 102) & labels.label]['item_id'])
        self.assertLessEqual(positives, {9, 10})
        # 106: product 7 twice in the first window order -> one target.
        self.assertEqual(int(targets.set_index('user_id').loc[106, 'n_targets']), 1)
        self.assertNotIn(103, set(targets['user_id']))   # no window order

    def test_window_end_exclusive(self):
        targets = xc.read_parquet(self.train/'targets.parquet').set_index('user_id')
        labels = xc.read_parquet(self.train/'labels.parquet')
        # 113: the only order from A on is at A + W = 2020-08-19 00:00:00 -> not a query.
        self.assertNotIn(113, targets.index)
        self.assertNotIn(113, set(self.frame(self.train)['user_id']))
        # 114: the first window order is at 2020-08-18 23:59:59 with the single product AT_END.
        self.assertEqual(int(targets.loc[114, 'n_targets']), 1)
        self.assertFalse(labels[labels.user_id == 114]['label'].any())   # AT_END is no candidate
        self.assertTrue(self.window_target_of(114) == {AT_END})

    def window_target_of(self, user):
        con = xs.history(xs._shift(A, xs.W), 'collect')
        try:
            return {r[0] for r in con.execute('''SELECT l.product_id FROM lines l WHERE l.order_id = (
                SELECT order_id FROM orders WHERE user_id = ? AND ts >= TIMESTAMP '2020-08-05'
                ORDER BY ts, order_id LIMIT 1)''', [user]).fetchall()}
        finally:
            con.close()

    def test_pop_inside_frame(self):
        # 111: main retailer Epsilon with fewer than K window products; 112: many repeat products.
        users = [1, 2, 102, 103, 106, 111, 112]
        con = xs.history(A, 'collect')
        try:
            xs._build_frame(con, self.base, A, users)
            frame = con.execute('SELECT user_id, item_id, source FROM frame_rows').df()
            xs._anchor_tables(con, A, xs.POP_WINDOW_DAYS)
            epsilon = con.execute("SELECT count(*) FROM r_rank WHERE retailer = 'r03'").fetchone()[0]
        finally:
            con.close()
        self.assertLess(epsilon, xs.K)
        con = xs.history(A, 'collect')
        try:
            self.assertGreater(con.execute('SELECT count(DISTINCT product_id) FROM lines WHERE user_id = 112'
                                           ).fetchone()[0], 3*self.base['candidates']['repeat_depth'])
        finally:
            con.close()
        self.assertGreater(int((frame[frame.user_id == 112].source == 'repeat').sum()), 0)
        ranked = xs.pop(A, users, xs.K)
        self.assertTrue((ranked.groupby('user_id').size() == xs.K).all())
        missing = ranked.merge(frame, on=['user_id', 'item_id'], how='left', indicator=True)
        self.assertEqual(missing[missing._merge == 'left_only'][['user_id', 'item_id']].values.tolist(), [])

    def test_repeated_lines(self):
        frame = self.frame(self.train).set_index(['user_id', 'item_id'])
        row = frame.loc[(106, 5)]
        self.assertEqual(row['up_orders'], 2)
        self.assertEqual(row['up_qty_total'], 6)
        self.assertEqual(row['repeat_rank'], 1)
        self.assertEqual(row['u_orders'], 2)

    def test_main_retailer_ties(self):
        con = xs.history(A, 'collect')
        try:
            xs._register_users(con, 'cu', [103, 104, 105])
            xs._user_tables(con, A)
            main = dict(con.execute('SELECT user_id, main_retailer FROM c_main').fetchall())
        finally:
            con.close()
        self.assertEqual(main, {103: 'r02', 104: 'r01', 105: 'r01'})

    def test_uc_share_through_cat(self):
        con = xs.history(A, 'collect')
        try:
            xs._build_frame(con, self.base, A, [107])
            rows = con.execute('SELECT item_id, uc_share, u_orders FROM frame_rows').df().set_index('item_id')
        finally:
            con.close()
        self.assertEqual(rows.loc[29, 'uc_share'], 0.5)       # its line has NULL category; cat(29) is known
        self.assertTrue(np.isnan(rows.loc[NULL_PRODUCT, 'uc_share']))
        same = [p for p in rows.index if p not in (29, NULL_PRODUCT) and category(p) == category(29)]
        for p in same:
            self.assertEqual(rows.loc[p, 'uc_share'], 0.5)

    def test_cap_and_small_pool(self):
        pool = self.manifest['pool']
        self.assertEqual(self.manifest['counts']['queries'], pool)   # pool smaller than N: all
        with mock.patch.dict(xs.QUERY_CAP, {'train': 5}):
            out = self.out('capped')
            manifest = xs.collect(A, 'train', self.base, out)
        users = sorted(set(self.frame(out)['user_id']))
        self.assertEqual(manifest['counts']['queries'], 5)
        self.assertEqual(manifest['pool'], pool)
        self.assertEqual(users, sorted(xc.cap_queries(set(self.frame(self.train)['user_id']), 5)))

    def test_chunk_invariance(self):
        out = self.out('chunked')
        xs.collect(A, 'train', self.base, out, chunk=7)
        pd.testing.assert_frame_equal(self.frame(out), self.frame(self.train))

    def test_probe_has_no_labels(self):
        pool = xs.probe_pool()
        self.assertEqual(pool, xc.cap_queries(pool, None))
        out = self.out('probe')
        manifest = xs.collect(xs.PROBE_ANCHOR, 'probe', self.base, out, users=pool)
        self.assertFalse((out/'labels.parquet').exists() or (out/'targets.parquet').exists())
        self.assertNotIn('positive_rows', manifest['counts'])
        self.assertEqual(set(self.frame(out)['user_id']), set(pool))

    def test_pop(self):
        users = [101, 103, 104, 1, 2]
        ranked = xs.pop(A, users, 50)
        self.assertTrue((ranked.groupby('user_id').size() == 50).all())
        self.assertFalse(ranked.duplicated(['user_id', 'item_id']).any())
        con = xs.history(A, 'pop')
        try:
            xs._anchor_tables(con, A, 28)
            beta = [r[0] for r in con.execute("SELECT product_id FROM r_rank WHERE retailer = 'r02' ORDER BY rnk"
                                              ).fetchall()]
        finally:
            con.close()
        head = list(ranked[ranked.user_id == 103].sort_values('rank')['item_id'])
        self.assertEqual(head[:min(50, len(beta))], beta[:50])

    def test_training_rows(self):
        frame = self.frame(self.train)
        labels = xc.read_parquet(self.train/'labels.parquet')
        rows = xs.training_rows(frame, labels, A)
        self.assertEqual(list(rows.columns[:len(frame.columns)]), list(frame.columns))
        for user, group in frame.merge(labels).groupby('user_id'):
            negatives = group[~group.label]
            expected = sorted(negatives['item_id'], key=lambda i: (xs.negative_hash(A, user, i), i))[:20]
            kept = rows[rows.user_id == user]
            self.assertEqual(sorted(kept[~kept.label]['item_id']), sorted(expected))
            self.assertEqual(int(kept.label.sum()), int(group.label.sum()))
            n_neg = len(negatives)
            for _, row in kept.iterrows():
                pi = 1.0 if row.label else min(20, n_neg)/n_neg
                self.assertAlmostEqual(row.weight, (1/len(group))/pi)


# ---------------------------------------------------------------- optional base-dev features

INITIAL_DIGEST = 'b27e1c00d84eb4e6d3217462d9a3f47d0f699c9d3a075bf3541a1bc62f2601e6'


def all_feature_base():
    return xs.initial_base(extra=[n for n, _, _ in xs.OPTIONAL_FEATURES], per_query=60, repeat_depth=10,
                           pop_retailer_depth=50, window_days=28)


def reference_features(con, A, frame):
    """The optional features recomputed in pandas from the history before A (independent of _build)."""
    a = pd.Timestamp(A)
    orders = con.execute('SELECT order_id, user_id, ts, retailer FROM orders').df()
    lines = con.execute('SELECT order_id, user_id, ts, product_id, quantity, master_category_id FROM lines').df()
    lines = lines.merge(orders[['order_id', 'retailer']], on='order_id')
    cat = lines.dropna(subset=['master_category_id']).groupby('product_id')['master_category_id'].max()
    lines['cat'] = lines['product_id'].map(cat)
    w7, w28 = lines[lines.ts >= a - pd.Timedelta(days=7)], lines[lines.ts >= a - pd.Timedelta(days=28)]
    b7 = w7.groupby('product_id')['user_id'].nunique()
    b28 = w28.groupby('product_id')['user_id'].nunique()
    b28_main = w28.groupby(['retailer', 'product_id'])['user_id'].nunique()
    days = lambda ts: (a - ts).total_seconds() / 86400.0
    rows = []
    for (user, item, main), _ in frame.groupby(['user_id', 'item_id', 'main_retailer']):
        ul = lines[(lines.user_id == user) & (lines.product_id == item)]
        uo = orders[orders.user_id == user].sort_values(['ts', 'order_id'], ascending=False)
        last5 = set(uo['order_id'].iloc[:5])
        bought = set(ul['order_id'])
        n28, n7 = b28.get(item, 0), b7.get(item, 0)
        same = lines[(lines.user_id == user) & (lines.cat == cat.get(item, np.nan))]
        rows.append(dict(
            user_id=user, item_id=item,
            up_orders_28=float(ul[ul.ts >= a - pd.Timedelta(days=28)]['order_id'].nunique()),
            up_last5_share=len(bought & last5) / min(5, len(uo)),
            up_in_last_order=float(uo['order_id'].iloc[0] in bought),
            up_days_since_first=days(ul.ts.min()) if len(ul) else np.nan,
            p_buyers_7=float(n7),
            p_trend=n7 / n28 if n28 else np.nan,
            p_buyers_28_main_share=b28_main.get((main, item), 0) / n28 if n28 else np.nan,
            up_qty_mean=ul.quantity.sum() / len(ul) if len(ul) else np.nan,
            uc_days_since_last=(days(same.ts.max()) if item in cat.index and len(same) else np.nan)))
    return pd.DataFrame(rows)


class OptionalFeatures(EnvCase):
    names = [n for n, _, _ in xs.OPTIONAL_FEATURES]

    def build(self, base, A, chunk=xs.CHUNK, users=None):
        con = xs.history(A, 'collect')
        try:
            if users is None:
                users = sorted(r[0] for r in con.execute('SELECT DISTINCT user_id FROM orders').fetchall())
            xs._build_frame(con, base, A, users, chunk=chunk)
            frame = con.execute('SELECT * EXCLUDE (source) FROM frame_rows ORDER BY user_id, item_id').df()
            reference = reference_features(con, A, frame)
        finally:
            con.close()
        return frame, reference

    def test_initial_base_unchanged(self):
        self.assertEqual(xs.initial_base()['digest'], INITIAL_DIGEST)
        self.assertEqual(xs.initial_base(extra=())['digest'], INITIAL_DIGEST)
        self.assertEqual(xc.base_feature_names(xs.initial_base()), [n for n, _, _ in xs.FEATURES])
        self.assertFalse(set(self.names) & set(xc.base_feature_names(xs.initial_base())))
        self.assertEqual(set(self.names) | {n for n, _, _ in xs.FEATURES}, set(xs.FEATURE_SQL))
        with self.assertRaises(xc.ContractError):
            xs.initial_base(extra=['nope'])
        # Changed texts are refused against the implementation.
        base = all_feature_base()
        body = {k: v for k, v in base.items() if k != 'digest'}
        body['features'] = [dict(f, missing='0') if f['name'] == 'p_trend' else f for f in body['features']]
        changed = xc.make_base('sber', body['candidates'], body['features'], body['categorical'])
        with self.assertRaisesRegex(xc.ContractError, 'differs from its implementation'):
            xs._policy(changed)

    def test_reference_and_chunk_invariance(self):
        base = all_feature_base()
        for A in ('2020-08-05', '2020-08-19'):
            with self.subTest(A):
                frame, reference = self.build(base, A)
                chunked, _ = self.build(base, A, chunk=7)
                pd.testing.assert_frame_equal(frame, chunked, check_exact=False, rtol=1e-12, atol=1e-12)
                got = frame[['user_id', 'item_id', *self.names]].reset_index(drop=True)
                pd.testing.assert_frame_equal(got, reference[got.columns].astype(got.dtypes.to_dict()),
                                              check_exact=False, rtol=1e-9, atol=1e-9)
                # The initial columns do not depend on the optional ones.
                plain, _ = self.build(small_base(), A)
                pd.testing.assert_frame_equal(frame[plain.columns], plain, check_exact=False, rtol=1e-12,
                                              atol=1e-12)
                for name in self.names:
                    self.assertTrue(frame[name].notna().any(), name)

    def test_crafted_values(self):
        base = all_feature_base()
        frame, _ = self.build(base, '2020-08-19', users=[102, 106, 107])
        rows = frame.set_index(['user_id', 'item_id'])
        # 102: two orders at the same latest time; the larger order_id (900002 with product 8) is the last one.
        self.assertEqual(rows.loc[(102, 8), 'up_in_last_order'], 1.0)
        self.assertEqual(rows.loc[(102, 9), 'up_in_last_order'], 0.0)
        self.assertEqual(rows.loc[(102, 9), 'up_last5_share'], 1/3)          # 3 orders: min(5, 3)
        # 106: product 5 on two lines (qty 2 and 3) of one order and one line (qty 1) of another.
        self.assertEqual(rows.loc[(106, 5), 'up_qty_mean'], 2.0)
        self.assertEqual(rows.loc[(106, 5), 'up_days_since_first'],
                         (pd.Timestamp('2020-08-19') - pd.Timestamp('2020-07-11 09:00')).total_seconds()/86400)
        # 107: cat(29) comes from another user's line; its own line has NULL category; product 30 has none.
        self.assertEqual(rows.loc[(107, 29), 'uc_days_since_last'],
                         (pd.Timestamp('2020-08-19') - pd.Timestamp('2020-07-12 09:00')).total_seconds()/86400)
        self.assertTrue(np.isnan(rows.loc[(107, NULL_PRODUCT), 'uc_days_since_last']))
        unseen = rows.loc[107]
        unseen = unseen[unseen['up_orders'] == 0]
        self.assertTrue((unseen['up_orders_28'] == 0).all() and (unseen['up_last5_share'] == 0).all())
        self.assertTrue((unseen['up_in_last_order'] == 0).all())
        self.assertTrue(unseen['up_days_since_first'].isna().all() and unseen['up_qty_mean'].isna().all())

    def test_collect_with_optional_features(self):
        out = self.out('allfeat')
        xs.collect(A, 'train', all_feature_base(), out)
        frame = self.frame(out)
        self.assertEqual(list(frame.columns), ['user_id', 'item_id', *xc.base_feature_names(all_feature_base())])
        train = self.out('allfeat-plain')
        xs.collect(A, 'train', small_base(), train)
        plain = self.frame(train)
        pd.testing.assert_frame_equal(frame[plain.columns], plain, check_exact=False, rtol=1e-12, atol=1e-12)


class TrainingRowsUnit(unittest.TestCase):
    def test_sampling_and_anchor_dependence(self):
        users, items = [1, 2], list(range(100, 160))
        frame = pd.DataFrame([(u, i) for u in users for i in items], columns=['user_id', 'item_id'])
        frame['x'] = 1.0
        labels = frame[['user_id', 'item_id']].copy()
        labels['label'] = labels['item_id'].isin([100, 101])
        a = xs.training_rows(frame, labels, '2020-08-05')
        b = xs.training_rows(frame, labels, '2020-08-19')
        self.assertEqual(len(a), 2*(2+20))
        self.assertNotEqual(list(a['item_id']), list(b['item_id']))
        neg = a[~a.label]
        self.assertTrue(np.allclose(neg['weight'], (1/60)/(20/58)))
        self.assertTrue(np.allclose(a[a.label]['weight'], 1/60))
        self.assertTrue(np.allclose(a['inclusion_probability'][~a.label], 20/58))

    def test_hash_reference_strings(self):
        self.assertEqual(xs.negative_hash('2020-08-19', 123, 456),
                         hashlib.sha256(b'2020-08-19|123|456|2026').hexdigest())
        self.assertEqual(xs.negative_hash('2020-08-19', 123, 456), xs.negative_hash('2020-08-19', 123, 456).lower())
        self.assertNotEqual(xs.negative_hash('2020-08-05', 123, 456), xs.negative_hash('2020-08-19', 123, 456))
        self.assertEqual(xc.query_order_key(123), hashlib.sha256(b'123:2026').hexdigest())
        con = duckdb.connect()
        try:
            self.assertEqual(con.execute(f"SELECT {xc.QUERY_ORDER_SQL.format(column='123')}").fetchone()[0],
                             hashlib.sha256(b'123:2026').hexdigest())
        finally:
            con.close()


# ---------------------------------------------------------------- metric

class Metric(unittest.TestCase):
    def test_manual_ap(self):
        # user 1: 60 targets (M > 50), 10 of them among 50 candidates at ranks 1, 3, 5, ..., 19.
        cand = list(range(1000, 1050))
        labels = pd.DataFrame({'user_id': 1, 'item_id': cand, 'label': [i < 1020 and i % 2 == 0 for i in cand]})
        ranked = pd.DataFrame({'user_id': 1, 'item_id': cand, 'rank': range(1, 51)})
        # user 2: 3 targets, one candidate target at rank 2, others outside candidates.
        labels = pd.concat([labels, pd.DataFrame({'user_id': 2, 'item_id': [7, 8, 9], 'label': [False, True, False]})])
        ranked = pd.concat([ranked, pd.DataFrame({'user_id': 2, 'item_id': [7, 8, 9], 'rank': [1, 2, 3]})])
        targets = pd.DataFrame({'user_id': [1, 2, 3], 'n_targets': [60, 3, 2]})
        result = xs.metric(ranked, targets, labels).set_index('user_id')['value']
        hits = [k for k in range(1, 51) if cand[k-1] < 1020 and cand[k-1] % 2 == 0]
        expected1 = sum((i+1)/k for i, k in enumerate(hits))/50
        self.assertAlmostEqual(result[1], expected1)
        self.assertAlmostEqual(result[2], (1/2)/3)
        self.assertEqual(result[3], 0.0)

    def test_unlabeled_item_refused(self):
        labels = pd.DataFrame({'user_id': [1], 'item_id': [5], 'label': [True]})
        ranked = pd.DataFrame({'user_id': [1, 1], 'item_id': [5, 6], 'rank': [1, 2]})
        with self.assertRaises(xc.ContractError):
            xs.metric(ranked, pd.DataFrame({'user_id': [1], 'n_targets': [1]}), labels)

    def test_rank_ties_by_item(self):
        scores = pd.DataFrame({'user_id': [1, 1, 1, 2], 'item_id': [9, 3, 5, 1], 'score': [0.5, 0.5, 0.7, 0.1]})
        ranked = xs.rank_scores(scores)
        self.assertEqual(list(ranked[ranked.user_id == 1]['item_id']), [5, 3, 9])
        self.assertEqual(list(ranked['rank']), [1, 2, 3, 1])


# ---------------------------------------------------------------- SQL rules

BYPASSES = (
    "ts > CAST('2020' || '-09-01' AS TIMESTAMP)", "ts > CAST(2020 || '-09-01' AS TIMESTAMP)",
    "ts > $$2020-09-01$$::TIMESTAMP", "ts > CAST('2020/09/01' AS TIMESTAMP)", "ts > '02020-09-01'::TIMESTAMP",
    "ts IS DISTINCT FROM CAST('2020' || '-09-01' AS TIMESTAMP)",
    "date_diff('day', ts, CAST('2020' || '-09-01' AS DATE)) > 0",
    "epoch(ts) > (SELECT 1598000000)", "epoch(ts) > power(10, 9) * 1.598", "epoch(ts) > exp(21.19)",
    "epoch(ts) > 2::BIGINT << 30", "greatest(epoch(ts), 1598000000) = epoch(ts)",
    "list_filter([epoch(ts)], x -> x > 1598000000) <> []", "epoch(ts) - 1598000000 > 0",
    "epoch(ts) / 10000000 > 159.8", "date_part('year', ts) - 2000 = 20", "year(ts) - 1700 > 319",
    "yearweek(ts) - 202000 > 35", "julian(ts) - 2459000 > 0", "strftime(ts, '%Y-%m') >= '2020-08'",
    "CAST(ts AS VARCHAR) > '2020-08'", "CAST(ts AS VARCHAR) LIKE '2020-08%'",
    "starts_with(CAST(ts AS VARCHAR), '2020-08')", "strftime(ts, 'x%Y%m%d') > 'x20200901'",
    "epoch(ts) > 1598000000 + 0 * epoch(TIMESTAMP '{A}')",
    "ts > TIMESTAMP '{A}' - TIMESTAMP '{A}' + CAST('2020' || '-09-01' AS TIMESTAMP)",
    "ts >= TIMESTAMP '{A}' - to_years(1)", "ts >= TIMESTAMP '{A}' - to_days(400)", "ts < current_localtimestamp()",
)
LEGIT = (
    ("SELECT user_id, count(*) AS ag_x FROM lines WHERE ts >= TIMESTAMP '{A}' - INTERVAL 28 DAY GROUP BY 1", 'user'),
    ("SELECT user_id, max(date_diff('day', ts, TIMESTAMP '{A}')) AS ag_x FROM lines GROUP BY 1", 'user'),
    ("SELECT user_id, date_diff('day', max(ts), TIMESTAMP '{A}') AS ag_x FROM orders GROUP BY 1", 'user'),
    ("SELECT user_id, epoch(TIMESTAMP '{A}' - max(ts)) / 86400.0 AS ag_x FROM orders GROUP BY 1", 'user'),
    ("SELECT user_id, count(*) FILTER (WHERE date_part('dow', ts) IN (0, 6)) AS ag_x FROM orders GROUP BY 1", 'user'),
    ("SELECT user_id, avg(date_part('hour', ts)) AS ag_x, count(DISTINCT CAST(ts AS DATE)) AS ag_y FROM orders "
     "WHERE date_part('dow', ts) = 6 GROUP BY 1", 'user'),
    ("WITH g AS (SELECT user_id, ts - lag(ts) OVER (PARTITION BY user_id ORDER BY ts, order_id) AS gap FROM orders) "
     "SELECT user_id, avg(epoch(gap)) AS ag_x FROM g GROUP BY 1", 'user'),
    ("WITH l AS (SELECT user_id, product_id, max(ts) AS last_ts FROM lines GROUP BY 1, 2) SELECT c.user_id, "
     "c.product_id, date_diff('day', l.last_ts, TIMESTAMP '{A}') AS ag_x FROM cand c LEFT JOIN l "
     "USING (user_id, product_id)", 'pair'),
    ("SELECT o.user_id, count(*) AS ag_x FROM orders o JOIN lines l ON l.order_id = o.order_id AND l.ts = o.ts "
     "WHERE o.ts BETWEEN TIMESTAMP '{A}' - INTERVAL 90 DAY AND TIMESTAMP '{A}' GROUP BY 1", 'user'),
    ("SELECT user_id, arg_max(retailer = 'r01', ts)::INT AS ag_x FROM orders GROUP BY 1", 'user'),
    ("SELECT product_id, count(*) AS ag_x FROM lines WHERE CAST(ts AS DATE) >= TIMESTAMP '{A}' - INTERVAL 7 DAY "
     "GROUP BY 1", 'item'),
    ("SELECT user_id, max(CASE WHEN retailer = 'r01' THEN ts END) IS NOT NULL AS ag_x FROM orders GROUP BY 1", 'user'),
    ("SELECT user_id, count(*) FILTER (WHERE date_part('day', ts) <= 7) AS ag_x, avg(hour(ts)) AS ag_y FROM "
     "orders GROUP BY 1", 'user'),
    ("WITH c AS (SELECT * FROM orders) SELECT user_id, max(date_diff('day', c.ts, TIMESTAMP '{A}')) AS ag_x "
     "FROM c GROUP BY 1", 'user'),
    ("SELECT u.user_id, (SELECT count(*) FROM orders o WHERE o.user_id = u.user_id AND o.ts >= TIMESTAMP '{A}' "
     "- INTERVAL 7 DAY) AS ag_x FROM users u", 'user'),
    ("SELECT user_id, count(*) AS ag_x FROM orders WHERE date_trunc('day', ts) >= TIMESTAMP '{A}' - INTERVAL 7 "
     "DAY GROUP BY 1", 'user'),
    ("SELECT l.user_id, l.product_id, max(date_diff('hour', l.ts, TIMESTAMP '{A}')) AS ag_x FROM lines l JOIN "
     "cand c ON c.user_id = l.user_id AND c.product_id = l.product_id GROUP BY 1, 2", 'pair'),
    ("SELECT user_id, count(*) AS ag_x FROM (SELECT user_id, ts FROM orders UNION ALL SELECT user_id, ts FROM "
     "lines) WHERE ts > TIMESTAMP '{A}' - INTERVAL 3 DAY GROUP BY 1", 'user'),
    ("SELECT product_id, count(*) AS ag_x FROM lines l JOIN categories c ON c.id = l.master_category_id GROUP "
     "BY 1", 'item'),
)

STRUCT_QUERY = ("SELECT user_id, count(*) AS ag_x FROM orders, "
                "(SELECT CAST(struct_pack(x_ts := '2020' || '-08-01') AS STRUCT(x_ts TIMESTAMP)) AS s) q WHERE "
                "{w} GROUP BY 1")

BYPASS_QUERIES = (  # whole statements: structs, rows, calendar parts, names, bindings
    "SELECT user_id, max(epoch(main.orders.ts)) > 1596240000 AS ag_x FROM orders, range(1) r GROUP BY user_id",
    "SELECT user_id, avg(epoch(memory.main.orders.ts)) AS ag_x FROM orders, range(1) r GROUP BY user_id",
    "SELECT users.user_id, max(epoch(main.orders.ts)) AS ag_x FROM users JOIN orders USING (user_id) GROUP "
    "BY users.user_id",
    'SELECT user_id, max(epoch("main"."orders"."ts")) AS ag_x FROM orders, range(1) r GROUP BY user_id',
    "SELECT product_id, max(month(main.lines.ts)) AS ag_x FROM lines, categories GROUP BY product_id",
    "SELECT user_id, sum((SELECT month(orders.ts) FROM users orders LIMIT 1)) AS ag_x FROM orders GROUP BY "
    "user_id",
    "SELECT user_id, sum((SELECT month(o.ts) FROM (SELECT 1 AS one) o)) AS ag_x FROM orders o GROUP BY "
    "user_id",
    "WITH o AS (SELECT 1 AS one) SELECT x.user_id, sum((SELECT month(x.ts) FROM o x LIMIT 1)) AS ag_x FROM "
    "orders x GROUP BY x.user_id",
    "SELECT user_id, sum((SELECT month(orders.ts) FROM categories orders LIMIT 1)) AS ag_x FROM orders GROUP "
    "BY user_id",
    "SELECT user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM users o WHERE epoch(o.ts) > "
    "1590000000) GROUP BY user_id",
    "SELECT c.user_id, c.product_id, max((SELECT dayofyear(l.ts) FROM cand l LIMIT 1)) AS ag_x FROM cand c "
    "JOIN lines l USING (user_id, product_id) GROUP BY ALL",
    "SELECT l.product_id, avg((SELECT month(l.ts) FROM categories l LIMIT 1)) AS ag_x FROM lines l GROUP BY "
    "l.product_id",
    "SELECT user_id, sum((SELECT epoch(orders.ts) FROM users orders LIMIT 1)) AS ag_x FROM orders GROUP BY "
    "user_id",
    "SELECT user_id, sum((SELECT epoch(o.ts) FROM (SELECT 1 AS one) o)) AS ag_x FROM orders o GROUP BY "
    "user_id",
    "SELECT user_id, max(date_part('dow', TIMESTAMP '{A}')) AS ag_x FROM orders GROUP BY 1",
    "SELECT user_id, max(lag(ts, 1, 0) OVER (PARTITION BY user_id ORDER BY ts, order_id)) AS ag_x FROM "
    "orders GROUP BY 1",
    STRUCT_QUERY.format(w='ts >= s.x_ts'),
    "SELECT user_id, count(*) AS ag_x FROM orders, (SELECT CAST(struct_pack(x_ts := 'epoch') AS STRUCT(x_ts "
    "TIMESTAMP)) AS s) q WHERE epoch(ts - s.x_ts) > 1596240000 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders, (SELECT struct_pack(x_ts := '2020-08-01') AS s) q WHERE "
    "ts >= s.x_ts GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders, (SELECT struct_pack(x_ts := '2020-08-01') AS s) q WHERE "
    "date_diff('day', s.x_ts, ts) > 0 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders, (SELECT unnest(struct_pack(x_ts := '2020-08-01')) ) q "
    "WHERE ts >= q.x_ts GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders, (SELECT s.* FROM (SELECT struct_pack(x_ts := "
    "'2020-08-01') AS s)) q WHERE ts >= x_ts GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders o, (SELECT o2 AS r FROM orders o2) q WHERE epoch(q.r.ts) > "
    "1 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE ts >= CAST(NULL AS STRUCT(x_ts TIMESTAMP)).x_ts "
    "GROUP BY 1",
    "SELECT user_id, CAST(x AS MAP(VARCHAR, DATE)) AS ag_x FROM orders",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE date_part('doy', ts) > 200 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE dayofyear(ts) > 200 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE week(ts) > 30 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE date_part('month', ts) * 100 + date_part('day', ts) "
    "> 801 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE month(ts) = 8 GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE quarter(ts) = 3 GROUP BY 1",
    "SELECT user_id, max(date_diff('day', date_trunc('year', ts), ts)) AS ag_x FROM orders GROUP BY 1",
    "SELECT user_id, max(date_diff('day', date_trunc('year', ts), TIMESTAMP '{A}')) AS ag_x FROM orders "
    "GROUP BY 1",
    "SELECT user_id, max(date_diff('month', ts, TIMESTAMP '{A}')) AS ag_x FROM orders GROUP BY 1",
    "SELECT user_id, max(date_diff('day', date_trunc('month', ts), TIMESTAMP '{A}')) AS ag_x FROM orders "
    "GROUP BY 1",
    "WITH RECURSIVE r AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM r WHERE n < 3) SELECT user_id, 1 AS ag_x "
    "FROM users",
    "WITH c AS (SELECT * FROM orders) SELECT user_id, max(epoch(c.ts)) AS ag_x FROM c GROUP BY 1",
    "SELECT user_id, max(m_ts) AS ag_x FROM (SELECT user_id, max(ts) AS m_ts FROM orders GROUP BY 1) GROUP "
    "BY 1",
    "SELECT user_id, max(ts) AS m_ts, epoch(m_ts) AS ag_x FROM orders GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM users u WHERE epoch(o.ts) > "
    "1) GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE nope > 1 GROUP BY 1",
    # lambdas: a parameter named like a table alias binds to the table
    "SELECT o.user_id, max(list_transform([1], o -> epoch(o.ts))[1]) AS ag_x FROM orders o GROUP BY o.user_id",
    "SELECT o.user_id, max(list_transform([1], o -> month(o.ts))[1]) AS ag_x FROM orders o GROUP BY o.user_id",
    "SELECT o.user_id, max(list_transform([1], lambda o: month(o.ts))[1]) AS ag_x FROM orders o GROUP BY "
    "o.user_id",
    "SELECT o.user_id, count(*) FILTER (WHERE len(list_filter([1], o -> epoch(o.ts) > 1590000000)) > 0) AS "
    "ag_x FROM orders o GROUP BY o.user_id",
    "SELECT user_id, max(list_transform([1], x -> month(ts))[1]) AS ag_x FROM orders GROUP BY user_id",
    "SELECT user_id, list_count(list_filter([quantity], x -> x > 1)) AS ag_x FROM lines GROUP BY 1",
    "SELECT user_id, len([y FOR y IN [1, 2]]) AS ag_x FROM orders GROUP BY user_id",
    # table functions, ts-named struct keys and fields, an unqualified ts behind an opaque FROM item
    "SELECT o.user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM (SELECT unnest(struct_pack(ts "
    ":= t.m + INTERVAL 106770374 DAY)) FROM (SELECT min(\"timestamp\") AS m FROM test_all_types()) t) x WHERE "
    "ts < o.ts) GROUP BY o.user_id",
    "SELECT o.user_id, max(date_diff('day', x.ts, o.ts)) AS ag_x FROM orders o, (SELECT unnest(struct_pack(ts "
    ":= t.m + INTERVAL 106770374 DAY)) FROM (SELECT min(\"timestamp\") AS m FROM test_all_types()) t) x GROUP "
    "BY o.user_id",
    "SELECT o.user_id, max(date_diff('day', (SELECT min(\"timestamp\") FROM test_all_types()) + INTERVAL "
    "106770374 DAY, o.ts)) AS ag_x FROM orders o GROUP BY o.user_id",
    "SELECT user_id, count(*) AS ag_x FROM orders, range(1) r GROUP BY user_id",
    "SELECT user_id, count(*) AS ag_x FROM orders, unnest([1, 2]) GROUP BY user_id",
    "SELECT o.user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM (SELECT unnest(struct_pack(ts "
    ":= 1))) x WHERE ts IS NOT NULL) GROUP BY o.user_id",
    "SELECT user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM (SELECT struct_pack(p_ts := 1) AS s) q"
    ") GROUP BY 1",
    "SELECT user_id, count(*) AS ag_x FROM (SELECT unnest(CAST(row(1) AS STRUCT(ts INT))) FROM users) GROUP BY 1",
    "SELECT o.user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM users u WHERE ts > "
    "TIMESTAMP '{A}' - INTERVAL 7 DAY) GROUP BY o.user_id",
    "SELECT o.user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM (VALUES (1)) v WHERE ts < "
    "o.ts) GROUP BY o.user_id",
    # ago(): the wall clock minus an interval
    "SELECT user_id, count(*) + 0 * epoch(ago(INTERVAL 1 DAY)) AS ag_x FROM orders GROUP BY user_id",
    "SELECT user_id, count(*) AS ag_x FROM orders WHERE ts > AGO(INTERVAL 30 DAY) GROUP BY user_id",
)


class Rules(unittest.TestCase):
    def ok(self, sql, level='pair'):
        xs.check_sql(sql, level)

    def bad(self, sql, level='pair'):
        with self.assertRaises(ValueError):
            xs.check_sql(sql, level)

    def test_section_9_cases(self):
        self.bad('SELECT user_id, product_id, 1 AS ag_x FROM lines WHERE epoch(ts) > 1598000000')
        self.bad("SELECT user_id, 1 AS ag_x FROM lines WHERE date_part('year', ts) = 2020", 'user')
        self.bad('SELECT user_id, 1 AS ag_x FROM lines WHERE ts > make_date(2020, 9, 1)', 'user')
        self.ok("SELECT user_id, count(*) AS ag_x FROM lines WHERE ts >= TIMESTAMP '{A}' - INTERVAL 28 DAY "
                'GROUP BY 1', 'user')
        # month, doy, week and quarter are absolute dates here: the data lie within one year.
        self.bad("SELECT user_id, count(*) AS ag_x FROM lines WHERE date_part('month', ts) = 9 GROUP BY 1", 'user')
        self.ok("SELECT user_id, count(*) AS ag_x FROM lines WHERE date_part('day', ts) <= 7 GROUP BY 1", 'user')
        self.ok("SELECT user_id, count(*) AS ag_x FROM lines WHERE date_part('dow', ts) IN (0, 6) GROUP BY 1", 'user')

    def test_more_time_rules(self):
        self.bad('SELECT user_id, 1 AS ag_x FROM lines WHERE epoch(ts) BETWEEN 0 AND 1598000000.5', 'user')
        self.bad('SELECT user_id, 1 AS ag_x FROM lines WHERE 1598000000 < epoch(ts)', 'user')
        self.bad('SELECT user_id, 1 AS ag_x FROM lines WHERE epoch(ts) IN (1598000000)', 'user')
        self.bad("SELECT user_id, 1 AS ag_x FROM lines WHERE ts > '2020-09-01'", 'user')
        self.bad("SELECT user_id, 1 AS ag_x FROM lines WHERE ts > TIMESTAMP '2020-09-01'", 'user')
        self.bad("SELECT user_id, 1 AS ag_x FROM lines WHERE ts > TIMESTAMP '{B}'", 'user')
        self.bad('SELECT user_id, 1 AS ag_x FROM lines WHERE epoch_ms(ts) > 5', 'user')
        self.bad('SELECT user_id, 1 AS ag_x FROM lines WHERE ts > to_timestamp(1598000000)', 'user')
        self.bad("SELECT user_id, 1 AS ag_x FROM lines WHERE ts >= TIMESTAMP '{A}' - INTERVAL '28 days'", 'user')
        self.ok("SELECT user_id, 1 AS ag_x FROM lines WHERE ts BETWEEN TIMESTAMP '{A}' - INTERVAL 90 DAY AND "
                "TIMESTAMP '{A}'", 'user')
        self.ok("SELECT user_id, max(date_diff('day', ts, TIMESTAMP '{A}')) AS ag_x FROM lines GROUP BY 1", 'user')
        self.ok('SELECT user_id, 1 AS ag_x FROM lines WHERE quantity > 1000', 'user')

    def test_bypasses_rejected(self):
        self.assertEqual(len(BYPASSES), 29)
        for condition in BYPASSES:
            with self.subTest(condition):
                self.bad(f'SELECT user_id, count(*) AS ag_x FROM lines WHERE {condition} GROUP BY 1', 'user')

    def test_bypass_queries_rejected(self):
        for sql in BYPASS_QUERIES:
            with self.subTest(sql):
                self.bad(sql, 'user')

    def test_struct_bypass_runs_in_duckdb(self):
        # The rejected struct query is a real bypass: DuckDB runs it and compares ts with a built time.
        con = duckdb.connect()
        try:
            con.execute("CREATE TABLE orders AS SELECT 1::BIGINT AS user_id, TIMESTAMP '2020-08-02' AS ts")
            struct = next(q for q in BYPASS_QUERIES if q.startswith(STRUCT_QUERY[:60]))
            self.assertEqual(con.execute(struct).fetchall(), [(1, 1)])
            # An alias reused inner without the column binds to the outer time value.
            self.assertEqual(con.execute('SELECT user_id, sum((SELECT epoch(o.ts) FROM (SELECT 1 AS one) o)) '
                                         'FROM orders o GROUP BY user_id').fetchall(), [(1, 1596326400.0)])
            # An unqualified ts binds to the closest FROM item that has it, here a renamed opaque column.
            self.assertEqual(con.execute("SELECT count(*) FROM orders o WHERE EXISTS (SELECT 1 FROM (SELECT "
                                         "unnest(struct_pack(ts := TIMESTAMP '2030-01-01'))) x WHERE ts > o.ts)")
                             .fetchall(), [(1,)])
        finally:
            con.close()

    def test_legit_time_forms_accepted(self):
        for sql, level in LEGIT:
            with self.subTest(sql):
                self.ok(sql, level)

    def test_names_cannot_launder_time(self):
        self.bad('SELECT user_id, max(ts) AS ag_x FROM orders GROUP BY 1', 'user')            # time named as value
        self.bad('SELECT user_id, epoch(max(ts)) AS ag_x FROM orders GROUP BY 1', 'user')
        self.bad('WITH t(u, x) AS (SELECT user_id, ts FROM orders) SELECT u AS user_id, 1 AS ag_x FROM t', 'user')
        self.bad('WITH t AS (SELECT user_id, quantity AS q_ts FROM lines) SELECT user_id, 1 AS ag_x FROM t', 'user')
        self.bad('SELECT user_id, #2 AS ag_x FROM orders', 'user')
        # ago is forbidden as a whole word only: names containing it stay allowed.
        self.ok("SELECT user_id, count(*) AS ag_days_ago FROM orders WHERE ts >= TIMESTAMP '{A}' - INTERVAL 7 DAY "
                'GROUP BY 1', 'user')
        # The outer ts written as alias.ts behind an opaque FROM item is fine.
        self.ok("SELECT o.user_id, count(*) AS ag_x FROM orders o WHERE EXISTS (SELECT 1 FROM users u WHERE "
                "u.user_id = o.user_id AND o.ts > TIMESTAMP '{A}' - INTERVAL 7 DAY) GROUP BY o.user_id", 'user')
        self.bad("SELECT user_id, 1 AS ag_x FROM lines WHERE CAST(ts AS DATE) > DATE '{A}'", 'user')

    def test_relaxed_forbidden_names(self):
        self.bad('SELECT * FROM user_profiles', 'user')
        self.bad('SELECT * FROM product_properties', 'item')
        self.bad("SELECT product_id, 1 AS ag_x FROM 'x/y.parquet'", 'item')
        self.bad('SELECT product_id, 1 AS ag_x FROM "x/y.parquet"', 'item')
        self.bad('SELECT product_id, 1 AS ag_x FROM main.lines', 'item')

    def test_policy_keeps_pop_inside_candidates(self):
        xs._policy(small_base())
        for change, message in (({'window_days': 27}, 'window_days'), ({'pop_retailer_depth': 49}, 'pop_retailer'),
                                ({'repeat_depth': 11}, 'per_query - repeat_depth')):
            policy = {**dict(per_query=60, repeat_depth=10, pop_retailer_depth=50, window_days=28), **change}
            with self.subTest(change), self.assertRaisesRegex(xc.ContractError, message):
                xs._policy(xs.initial_base(**policy))

    def test_hm_rules(self):
        self.bad('SELECT 1; SELECT 2', 'user')
        self.bad('SELECT user_id -- x\n FROM lines', 'user')
        self.bad("SELECT * FROM read_parquet('x')", 'user')
        self.bad('SELECT product_name FROM lines', 'item')
        self.bad('SELECT product_id, 1 AS ag_x FROM lines JOIN cand USING (product_id)', 'item')
        self.bad('SELECT * FROM tab_1_orders', 'user')
        self.bad('SELECT user_id FROM labels', 'user')
        self.bad('SELECT error(1)', 'user')
        self.bad('UPDATE lines SET price = 0', 'user')
        rules = xs.sql_rules()
        self.assertTrue(callable(rules['check']))
        self.assertEqual(rules['timeouts'], {'pair': 40.0, 'user': 40.0, 'item': 120.0})
        self.assertEqual(rules['budget'], {'pair_user_seconds': 180.0, 'item_seconds': 360.0})
        self.assertTrue(re.compile(r'\b(' + rules['forbidden'] + r')\b', re.I).search('product_name'))


# ---------------------------------------------------------------- prompt

class Prompt(EnvCase):
    def test_numbers_warning_names(self):
        from scripts import xfer_agent as xa
        pool = xs.probe_pool()
        stats = xs.probe_stats(xs.PROBE_ANCHOR, pool, base=self.base)
        self.assertNotRegex(json.dumps(stats), r'[0-9]{9,}')
        history = 'Accepted columns: (none)'
        budget = {'pair_user_seconds': 170, 'item_seconds': 360}
        subs = xs.prompt_substitutions(stats, self.base, history, 2, budget)
        problems = xa.prompt_number_problems(subs, stats, self.base, xs.PROMPT_CONSTANTS,
                                             xa.feedback_outputs(history, 2, 6, budget))
        self.assertEqual(problems, [])
        prompt = xs.PROMPT_TEMPLATE.format(**subs)
        self.assertIn(xs.WARNING, ' '.join(prompt.split()))
        self.assertEqual(xs.WARNING, xa.WARNING)
        self.assertIn('a grocery delivery service', prompt)
        self.assertNotRegex(prompt, re.compile(r'kaggle|sber|tinkoff|competition|instamart|metro', re.I))
        self.assertNotIn('Name ', prompt)
        self.assertIn("TIMESTAMP '{A}'", prompt)
        self.assertIn('round 2 of 6', prompt)
        # The template itself has no slots left and no stray braces.
        self.assertNotRegex(prompt, r'\{(?!A\})[a-z_]+\}')

    def test_number_test_catches_foreign_numbers(self):
        from scripts import xfer_agent as xa
        stats = {'windows': {'last_14_days': {'lines': 10}}}
        subs = xs.prompt_substitutions(stats, self.base, 'x 12345', 1, {'pair_user_seconds': 0, 'item_seconds': 0})
        problems = xa.prompt_number_problems(subs, stats, self.base, xs.PROMPT_CONSTANTS,
                                             xa.feedback_outputs('x', 1, 6, {}))
        self.assertIn(('history', '12345'), problems)

    def test_coverage_sources(self):
        self.assertEqual(xs.coverage_sources(), {'recent': ['repeat_rank'], 'global': ['popr_rank', 'glob_rank']})
        names = xc.base_feature_names(self.base)
        for columns in xs.coverage_sources().values():
            self.assertTrue(set(columns) <= set(names))


# ---------------------------------------------------------------- holdout, kaggle, assemble

class Window(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = Env()
        cls.base = small_base()

    @classmethod
    def tearDownClass(cls):
        cls.env.close()

    def open_collect_holdout(self):
        base = xc.config_path('sber', 'base')
        base.write_text(json.dumps(self.base))
        agent_set = xc.config_path('sber', 'set')
        agent_set.write_text(json.dumps({'columns': []}))
        self.env.commit(base, agent_set)
        self.env.config('prereg', {'base_sha256': xc.sha256_file(base), 'set_sha256': xc.sha256_file(agent_set)})

    def test_holdout_then_kaggle(self):
        self.open_collect_holdout()
        with self.assertRaisesRegex(xc.ContractError, 'Holdout window closed'):
            xs.history('2020-09-10', 'collect')
        out = xc.output_dir('sber', 'collections', xc.holdout_collection_name(xs.HOLDOUT_ANCHOR))
        with self.assertRaisesRegex(xc.ContractError, 'every query'):
            xs.collect(xs.HOLDOUT_ANCHOR, 'holdout', self.base, out, users=[1])
        self.assertEqual(out, xc.current_holdout_collection('sber', xs.HOLDOUT_ANCHOR))
        with mock.patch.dict(xs.QUERY_CAP, {'holdout': 5}):
            manifest = xs.collect(xs.HOLDOUT_ANCHOR, 'holdout', self.base, out)
        self.assertGreater(manifest['pool'], 5)
        self.assertEqual(manifest['counts']['queries'], 5)
        self.assertEqual(sorted(p.name for p in (out/xc.SEALED).iterdir()), sorted(xc.SEALED_FILES))
        self.assertFalse((out/'labels.parquet').exists())
        self.assertFalse({'labels', 'positives', 'targets', 'n_targets', 'positive_rows'} & set(manifest['counts']))
        self.assertEqual(set(manifest['sealed']), set(xc.SEALED_FILES))
        frame = xc.read_parquet(out/xc.FRAME_FILE)
        self.assertNotIn(CANARY_HOLDOUT, set(frame['item_id']))
        # The window closes once a holdout collection exists; nothing is left behind by the refusals.
        with self.assertRaisesRegex(xc.ContractError, 'current holdout collection'):
            xs.collect(xs.HOLDOUT_ANCHOR, 'holdout', self.base, xc.output_dir('sber', 'collections', 'holdout-x'))
        with self.assertRaisesRegex(xc.ContractError, 'exists'):
            xs.collect(xs.HOLDOUT_ANCHOR, 'holdout', self.base, out)
        with self.assertRaisesRegex(xc.ContractError, 'Holdout window closed'):
            xs.collect(xs.KAGGLE_ANCHOR, 'kaggle', self.base, xc.output_dir('sber', 'collections', 'kaggle-x'))
        self.assertFalse(xc.output_dir('sber', 'collections', 'kaggle-x').exists())

        self.env.config('holdout', {'result': 'committed'})
        kaggle = xc.output_dir('sber', 'collections', xc.collection_name('kaggle', xs.KAGGLE_ANCHOR))
        manifest = xs.collect(xs.KAGGLE_ANCHOR, 'kaggle', self.base, kaggle)
        fallback = set(xc.read_parquet(kaggle/'fallback.parquet')['user_id'])
        self.assertEqual(fallback, {108, 109, 999})
        known = set(xc.read_parquet(kaggle/'known.parquet')['item_id'])
        self.assertNotIn(HEADLESS_ITEM, known)
        self.assertIn(CANARY_HOLDOUT, known)
        frame = xc.read_parquet(kaggle/xc.FRAME_FILE)
        self.assertEqual(set(frame['user_id']), set(range(1, 31)))
        chunked = xc.output_dir('sber', 'base-dev', 'kaggle-chunk-7')
        xs.collect(xs.KAGGLE_ANCHOR, 'kaggle', self.base, chunked, chunk=7)
        pd.testing.assert_frame_equal(xc.read_parquet(chunked/xc.FRAME_FILE), frame)

        rng = np.random.default_rng(1)
        scores = frame[['user_id', 'item_id']].copy()
        scores['score'] = rng.normal(size=len(scores))
        target = xc.output_dir('sber', 'kaggle', 'B2026.csv')
        receipt = xs.assemble(scores, target, collection=kaggle)
        self.assertEqual(receipt['rows'], len(self.env.raw_data.submission))
        self.assertEqual(receipt['fallback'], 3)
        self.assertEqual(receipt['sha256'], xc.sha256_file(target))
        self.assertTrue(target.with_suffix('.json').exists())
        self.assertFalse(target.with_name(target.name+'.part').exists())
        text = target.read_text().split('\n')
        self.assertEqual(text[0], 'Id,Predicted')
        rows = {int(l.split(',')[0]): [int(x) for x in l.split(',')[1].split()] for l in text[1:] if l}
        self.assertEqual([int(l.split(',')[0]) for l in text[1:] if l], self.env.raw_data.submission)
        self.assertEqual(rows[999], receipt['fallback_items'])
        top = xs.rank_scores(scores)
        first = top[top.user_id == 1].sort_values('rank')['item_id'].tolist()
        self.assertEqual(rows[1][:len(first)], first)
        self.assertTrue(all(len(set(v)) == 50 and set(v) <= known for v in rows.values()))
        with self.assertRaisesRegex(xc.ContractError, 'overwrite'):
            xs.assemble(scores, target, collection=kaggle)
        with self.assertRaisesRegex(xc.ContractError, 'cover exactly'):
            xs.assemble(scores[scores.user_id != 1], xc.output_dir('sber', 'kaggle', 'x.csv'), collection=kaggle)
        outside = scores.copy()
        outside.loc[outside.index[0], 'item_id'] = 10**6
        with self.assertRaisesRegex(xc.ContractError, 'not rows of the kaggle frame'):
            xs.assemble(outside, xc.output_dir('sber', 'kaggle', 'y.csv'), collection=kaggle)
        with self.assertRaisesRegex(xc.ContractError, 'repeat'):
            xs.assemble(pd.concat([scores, scores.head(1)]), xc.output_dir('sber', 'kaggle', 'z.csv'),
                        collection=kaggle)
        self.assertFalse(any(xc.output_dir('sber', 'kaggle', n).exists() for n in ('x.csv', 'y.csv', 'z.csv')))
        # The fallback list is the first K of the global order at the kaggle anchor (Pop window).
        con = xs.history(xs.KAGGLE_ANCHOR, 'pop')
        try:
            xs._anchor_tables(con, xs.KAGGLE_ANCHOR, xs.POP_WINDOW_DAYS)
            glob = [r[0] for r in con.execute('SELECT product_id FROM g_rank ORDER BY rnk LIMIT 50').fetchall()]
        finally:
            con.close()
        self.assertEqual(len(glob), xs.K)
        self.assertEqual(receipt['fallback_items'], glob)
        self.assertEqual(rows[108], glob)


class Submission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'s.csv'
        self.known = set(range(1, 101))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        self.path.write_bytes(('Id,Predicted\n' + ''.join(f'{u},{" ".join(map(str, items))}\n'
                                                          for u, items in rows)).encode())

    def test_refusals(self):
        good = [(1, list(range(1, 51))), (2, list(range(51, 101)))]
        self.write(good)
        self.assertEqual(xs.check_submission(self.path, [1, 2], self.known)['rows'], 2)
        cases = {
            '49': [(1, list(range(1, 50))), good[1]],
            'duplicate Id': [good[0], good[0], good[1]],
            'unknown': [(1, list(range(1, 50)) + [500]), good[1]],
            'repeat product': [(1, list(range(1, 50)) + [1]), good[1]],
            'extra Id': good + [(3, list(range(1, 51)))],
            'missing Id': good[:1],
            'Id order': [good[1], good[0]],
        }
        for name, rows in cases.items():
            with self.subTest(name):
                self.write(rows)
                with self.assertRaises(xc.ContractError):
                    xs.check_submission(self.path, [1, 2], self.known)
        self.path.write_bytes(b'Id,Predicted\r\n')
        with self.assertRaises(xc.ContractError):
            xs.check_submission(self.path, [], self.known)


# ---------------------------------------------------------------- CLI and anchors

class Cli(unittest.TestCase):
    def test_refuses_without_isolated(self):
        result = subprocess.run([sys.executable, str(Path(xs.__file__)), 'load'], capture_output=True, text=True,
                                cwd=tempfile.gettempdir())
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(payload['ok'])
        self.assertIn('-I', payload['error'])

    def test_anchors(self):
        a = xs.anchors()
        self.assertEqual(a['roles']['train'], ['2020-06-10', '2020-06-24', '2020-07-08', '2020-07-22', '2020-08-05'])
        self.assertEqual(a['holdout'], '2020-09-02')
        self.assertEqual(a['probe'], '2020-08-19')
        self.assertEqual(a['series']['final']['train'], ['2020-06-24', '2020-07-08', '2020-07-22', '2020-08-05',
                                                         '2020-08-19', '2020-09-02'])
        self.assertEqual(a['series']['final']['arms'], ['B', 'BA', 'BApl'])
        self.assertEqual((a['W'], a['N'], a['K']), (14, 20000, 50))
        # Training windows [A, A+14) of a series do not reach its evaluation anchor.
        for spec in a['series'].values():
            for anchor in spec['train']:
                self.assertLessEqual(xs._shift(anchor, xs.W), spec['eval'])

    def test_initial_base(self):
        base = xs.initial_base()
        self.assertEqual(len(base['features']), 22)
        self.assertEqual(base['categorical'], ['main_retailer'])
        self.assertEqual(base['candidates']['per_query'], 200)
        xc.check_base(base, 'sber')


if __name__ == '__main__':
    unittest.main()
