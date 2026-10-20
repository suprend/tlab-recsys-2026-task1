"""Synthetic witnesses for the agent sandbox (docs/hm-agent-design.md, sections 1, 2, 5, 6); no real H&M data.

One fixture writes a tiny audited DB (the purchases of test_hm_kaggle plus a
future canary: price 999, an article with unique attributes, bought on the
anchor 2020-09-09 and later), the full export, a cut export before the anchor
and a 30-user probe. Scratch lives in /tmp; connections use two threads.
"""
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from datetime import date, timedelta
import functools
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from scripts import hm_agent_sandbox as sbx
from scripts import hm_experiment as experiment
from scripts import hm_feature_engine as engine
from scripts import hm_kaggle as kaggle
from scripts.hm_baseline import cohort_key
from scripts.hm_eda import SCHEMAS
from tests.test_hm_kaggle import ARTICLES, CUSTOMERS, ENDLESS, WALL, purchases

A = '2020-09-09'
CANARY = '0999999999'
CANARY_DAYS = (date(2020, 9, 9), date(2020, 9, 10), date(2020, 9, 16))
USERS = 30
SCRIPT = str(kaggle.ROOT/'scripts/hm_agent_sandbox.py')
PAIR = ('SELECT customer_id, article_id, count(*) AS ag_pair_buys FROM tx SEMI JOIN cand USING (customer_id, article_id) '
        'GROUP BY customer_id, article_id')
CUSTOMER = ("SELECT customer_id, count(*) AS ag_cust_n28, max(price) AS ag_cust_maxprice FROM tx SEMI JOIN users "
            "USING (customer_id) WHERE t_dat >= DATE '{A}' - INTERVAL 28 DAY GROUP BY customer_id")
ARTICLE = ("SELECT article_id, count(DISTINCT customer_id) AS ag_art_buyers7 FROM tx "
           "WHERE t_dat >= DATE '{A}' - INTERVAL 7 DAY GROUP BY article_id")
SPIN = ('SELECT customer_id, CAST(sum(i % 7) AS DOUBLE) AS ag_spin FROM users, range(10000000000000) t(i) '
        'GROUP BY customer_id')
HUNGRY = 'SELECT customer_id, CAST(len(list(i)) AS DOUBLE) AS ag_big FROM users, range(3000000) r(i) GROUP BY customer_id'


def proposal(sql, level='pair', name='test proposal'):
    return dict(name=name, idea='a synthetic witness', level=level, sql=sql)


def agent_set(*items, digest=None):
    """A frozen set in the shape the loop writes; items are (level, sql, columns)."""
    proposals = [dict(id=f'r1p{i}', round=1, index=i, name=f'p{i}', idea='idea', level=level, sql=sql,
                      columns=list(columns), probe_seconds=0.01) for i, (level, sql, columns) in enumerate(items, 1)]
    return dict(format=sbx.SET_FORMAT, run={}, probe=dict(anchor=A, users=USERS, export_digest=digest),
                proposals=proposals, attempts=[], columns=[c for p in proposals for c in p['columns']], budget={},
                digest=sbx.set_digest(proposals))


def same(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    return x.shape == y.shape and bool(((np.isnan(x) & np.isnan(y)) | (x == y)).all())


def shifted(real):
    """A leaking sandbox: one day of history past the anchor."""
    def wrapper(export, anchor, keys_path, threads=4, memory='4GB'):
        day = date.fromisoformat(anchor) if isinstance(anchor, str) else anchor
        return real(export, day+timedelta(days=1), keys_path, threads=threads, memory=memory)
    return wrapper


def build_database(path, rows):
    """audit.duckdb with the EDA schemas, the fixture purchases and the canary."""
    rng = random.Random(11)
    types = [('253', 'Vest top'), ('272', 'Trousers'), ('265', 'Dress'), ('-1', 'Unknown')]
    con = duckdb.connect(str(path))
    try:
        for table, schema in SCHEMAS.items():
            con.execute(f'CREATE TABLE {table} ({", ".join(f"{n} {t}" for n, t in schema.items())})')
        articles = []
        for i, article in enumerate([*ARTICLES, CANARY]):
            row = dict.fromkeys(SCHEMAS['articles'], 'fixture')
            row.update(article_id=article, product_code=article[:7], product_type_no=types[i % 4][0],
                       product_type_name=types[i % 4][1], colour_group_code=('09', '10', '73', '')[i % 4],
                       department_no=str(1000+i % 6), index_code='ABCD'[i % 4], garment_group_no=str(1001+i % 5),
                       prod_name='free text', detail_desc='free text')
            if article == CANARY:
                row.update({name: 'Canary attribute' for name in sbx.ARTICLE_COLUMNS if name.endswith('_name')})
                row.update(product_type_no='777', department_no='7777')
            articles.append(row)
        con.executemany(f'INSERT INTO articles VALUES ({", ".join("?"*len(SCHEMAS["articles"]))})',
                        [list(r.values()) for r in articles])
        tx = [(d, u, a, round(rng.uniform(.005, .06), 6), str(1+(rng.random() < .5))) for d, u, a in rows]
        tx += [(d, CUSTOMERS[2], CANARY, 999.0, '2') for d in CANARY_DAYS]
        con.executemany('INSERT INTO transactions VALUES (?, ?, ?, ?, ?)', tx)
        con.executemany('INSERT INTO customers VALUES (?, NULL, NULL, ?, ?, 30, ?)',
                        [(c, 'ACTIVE', 'NONE', c[::-1]) for c in CUSTOMERS])
    finally:
        con.close()
    return len(tx)


def write_source(database):
    raw = Path(database).read_bytes()
    record = dict(format=kaggle.EDA_FORMAT, database=dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)),
                  valid=True, pinned_sources=True, allow_unpinned=False)
    (Path(database).parent/kaggle.SOURCE_RECORD).write_text(json.dumps(record), encoding='utf-8')


def read_table(path):
    """A parquet file as a DataFrame in key order (no pyarrow in this environment)."""
    con = duckdb.connect()
    try:
        return con.execute('SELECT * FROM read_parquet(?) ORDER BY customer_id, article_id', [str(path)]).fetch_df()
    finally:
        con.close()


def run_main(argv, **patches):
    out = io.StringIO()
    with ExitStack() as stack:
        for name, value in patches.items():
            stack.enter_context(mock.patch.object(kaggle, name, value))
        stack.enter_context(redirect_stdout(out))
        stack.enter_context(redirect_stderr(io.StringIO()))
        code = sbx.main(argv)
    return code, out.getvalue().splitlines()


class HmAgentSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        try:
            cls.build()
        except BaseException:
            cls.stack.close()
            raise

    @classmethod
    def build(cls):
        cls.tmp = Path(cls.stack.enter_context(tempfile.TemporaryDirectory(prefix='tlab-hm-agent-a-', dir='/tmp'))).resolve()
        cls.artifacts = cls.tmp/'artifacts'
        (cls.artifacts/'eda').mkdir(parents=True)
        for name, value in (('ARTIFACTS', cls.artifacts), ('isolated', lambda: True)):
            cls.stack.enter_context(mock.patch.object(kaggle, name, value))
        cls.rows = purchases()
        cls.database = cls.artifacts/'eda/audit.duckdb'
        cls.tx_rows = build_database(cls.database, cls.rows)
        write_source(cls.database)
        cls.full = cls.artifacts/'agent/export'
        cls.cut = cls.artifacts/'agent/export-cut'
        cls.probe = cls.artifacts/'agent/probe'
        cls.full_record = sbx.export_history(cls.database, cls.full, threads=2)
        cls.cut_record = sbx.export_history(cls.database, cls.cut, before=A, threads=2)
        cls.probe_record = sbx.prepare_probe(cls.database, cls.full, A, USERS, cls.probe, threads=2)
        cls.keys = read_table(cls.probe/'keys.parquet')

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    @contextmanager
    def box(self, anchor=A, export=None, keys=None, memory='4GB'):
        con = sbx.sandbox(export or self.full, anchor, keys or self.probe/'keys.parquet', threads=2, memory=memory)
        try:
            yield con
        finally:
            sbx._close(con)

    def run_sql(self, sql, level='pair', timeout=20):
        with self.box() as con:
            return sbx.run_proposal(con, proposal(sql, level), A, timeout)

    def refused(self, sql, level, text):
        with self.subTest(sql=sql), self.assertRaises(sbx.ProposalError) as caught:
            self.run_sql(sql, level)
        self.assertIn(text, str(caught.exception))

    def writable_copy(self, name):
        target = self.artifacts/'agent'/name
        shutil.copytree(self.full, target)
        for path in target.rglob('*'):
            if path.is_file():
                path.chmod(0o644)
        return target

    def evaluate(self, sql, level='pair', prior=()):
        return sbx.evaluate_proposal(self.probe, self.full, proposal(sql, level), list(prior), threads=2)

    def shuffled_keys(self, fraction=1.0, seed=3):
        keys = self.keys.sample(frac=fraction, random_state=seed)
        keys.index = np.arange(len(keys))*7+5  # non-contiguous: results follow positions, not the index
        return keys

    # --- section 5 ------------------------------------------------------------------------------------------

    def test_future_canary_is_invisible_before_the_anchor_and_visible_after(self):
        with self.box(A) as con:
            self.assertEqual(con.execute('SELECT count(*) FILTER (WHERE price >= 999 OR article_id = ?), max(t_dat) '
                                         'FROM tx', [CANARY]).fetchone(), (0, date(2020, 9, 8)))
            self.assertEqual(con.execute("SELECT count(*) FROM articles WHERE article_id = ? "
                                         "OR product_type_name LIKE 'Canary%'", [CANARY]).fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT count(*) FROM cand WHERE article_id = ?', [CANARY]).fetchone()[0], 0)
        with self.box('2020-09-16') as con:
            self.assertEqual(con.execute('SELECT count(*) FROM tx WHERE article_id = ?', [CANARY]).fetchone()[0], 2)
            self.assertEqual(con.execute('SELECT count(*) FROM articles WHERE article_id = ?', [CANARY]).fetchone()[0], 1)
        keys = self.keys[self.keys['customer_id'] == CUSTOMERS[2]]
        self.assertTrue(len(keys))
        chosen = agent_set(('customer', CUSTOMER, ['ag_cust_n28', 'ag_cust_maxprice']))
        before = sbx.agent_columns(self.full, A, keys, chosen, threads=2)[0]
        after = sbx.agent_columns(self.full, '2020-09-16', keys, chosen, threads=2)[0]
        self.assertTrue((before['ag_cust_maxprice'] < 1).all())
        self.assertTrue((after['ag_cust_maxprice'] == 999).all())

    def test_future_partition_read_fails_even_without_check_sql(self):
        future = sorted((self.full/'tx/d=2020-09-10').glob('*.parquet'))[0]
        past = sorted((self.full/'tx/d=2020-09-01').glob('*.parquet'))[0]
        with self.box() as con:
            self.assertGreater(con.execute('SELECT count(*) FROM read_parquet(?)', [str(past)]).fetchone()[0], 0)
            with self.assertRaises(duckdb.PermissionException):
                con.execute('SELECT count(*) FROM read_parquet(?)', [str(future)])
            with self.assertRaises(duckdb.PermissionException):
                con.execute('SELECT count(*) FROM read_parquet(?)', [str(self.full/'tx/*/*.parquet')])
            with self.assertRaises(duckdb.Error):
                con.execute(f"ATTACH '{self.database}' AS db (READ_ONLY)")
            with self.assertRaises(duckdb.Error):
                con.execute('SET enable_external_access=true')
            leak = proposal(f"SELECT customer_id, article_id, price AS ag_leak FROM read_parquet('{future}')")
            with mock.patch.object(sbx, 'check_sql', lambda sql, level: None), \
                    self.assertRaises(sbx.ProposalError) as caught:
                sbx.run_proposal(con, leak, A, 20)
            self.assertIn('PermissionException', str(caught.exception))
            with self.assertRaises(sbx.ProposalError):
                sbx.run_proposal(con, leak, A, 20)

    def test_caller_variable_secret_is_unreachable(self):
        secret = pd.DataFrame({'customer_id': CUSTOMERS[:2], 'ag_secret': [1.0, 2.0]})
        self.assertEqual(len(secret), 2)
        with self.box() as con:
            with self.assertRaises(duckdb.CatalogException):
                con.execute('SELECT * FROM secret')
            with self.assertRaises(sbx.ProposalError) as caught:
                sbx.run_proposal(con, proposal('SELECT customer_id, ag_secret FROM secret', 'customer'), A, 20)
            self.assertIn('CatalogException', str(caught.exception))

    def test_check_sql_rejects_forbidden_sql(self):
        rejected = [
            ('SELECT customer_id, 1 AS ag_val FROM transactions GROUP BY 1', 'customer'),
            ('SELECT customer_id, 1 AS ag_val FROM labels', 'customer'),
            ("SELECT * FROM read_parquet('x')", 'pair'),
            ('SELECT customer_id, random() AS ag_val FROM users', 'customer'),
            ("SELECT customer_id, 1 AS ag_val FROM users WHERE current_date > DATE '{A}'", 'customer'),
            ('SELECT customer_id, 1 AS ag_val FROM users USING SAMPLE 10', 'customer'),
            ('SELECT 1; SELECT 2', 'pair'),
            ('SELECT 1 AS ag_val; DROP TABLE cand', 'pair'),
            ("SELECT customer_id, 1 AS ag_val FROM tx WHERE t_dat < DATE '2020-09-01'", 'customer'),
            ("SELECT customer_id, 1 AS ag_val FROM tx WHERE t_dat < '2020-9-1'", 'customer'),
            ("SELECT customer_id, 1 AS ag_val FROM tx WHERE t_dat < '{A}'", 'customer'),
            ("SELECT customer_id, 1 AS ag_val FROM tx WHERE t_dat < {A}", 'customer'),
            ("SELECT customer_id, 1 AS ag_val FROM tx WHERE t_dat < CAST('{A}' AS DATE)", 'customer'),
            ('SELECT article_id, count(*) AS ag_val FROM tx SEMI JOIN cand USING (article_id) GROUP BY 1', 'article'),
            ('SELECT article_id, count(*) AS ag_val FROM tx JOIN users USING (customer_id) GROUP BY 1', 'article'),
            ('SELECT 1 -- comment', 'pair'),
            ('UPDATE cand SET article_id = 1', 'pair'),
            ('', 'pair'),
        ]
        for sql, level in rejected:
            with self.subTest(sql=sql), self.assertRaises(sbx.ProposalError):
                sbx.check_sql(sql, level)
        with self.assertRaises(sbx.ProposalError):
            sbx.check_sql(ARTICLE, 'user')
        for sql, level in ((PAIR, 'pair'), (CUSTOMER, 'customer'), (ARTICLE, 'article'),
                           ("SELECT customer_id, 1 AS ag_val FROM tx WHERE t_dat >= date '{A}' - 7;", 'customer')):
            sbx.check_sql(sql, level)

    def test_count_over_cand_is_invalid_by_invariance(self):
        record, values = self.evaluate('SELECT customer_id, article_id, count(*) OVER () AS ag_pair_total FROM cand')
        self.assertEqual((record['status'], values), ('invalid', None))
        self.assertIn('batch invariance', record['error'])
        window = ('SELECT customer_id, article_id, row_number() OVER (PARTITION BY customer_id ORDER BY article_id) '
                  'AS ag_pair_order FROM cand')
        record, values = self.evaluate(window)
        self.assertEqual(record['status'], 'valid', record['error'])
        self.assertEqual(list(values.columns), ['customer_id', 'article_id', 'ag_pair_order'])
        # The same window in agent_columns: one batch against two halves.
        chosen = agent_set(('pair', 'SELECT customer_id, article_id, count(*) OVER () AS ag_pair_total FROM cand',
                            ['ag_pair_total']))
        whole = sbx.agent_columns(self.full, A, self.keys, chosen, threads=2)[0]
        half = self.keys[self.keys['customer_id'].isin(sorted(set(self.keys['customer_id']))[:10])]
        part = sbx.agent_columns(self.full, A, half, chosen, threads=2)[0]
        self.assertEqual(set(whole['ag_pair_total']), {len(self.keys)})
        self.assertEqual(set(part['ag_pair_total']), {len(half)})

    # --- 1.4 output contract, one test per rule -------------------------------------------------------------

    def test_proposal_fields_and_level_are_required(self):
        with self.box() as con:
            for bad in ({}, dict(proposal(PAIR), sql=''), dict(proposal(PAIR), level='user'),
                        {k: v for k, v in proposal(PAIR).items() if k != 'idea'}, 'SELECT 1'):
                with self.subTest(bad=bad), self.assertRaises(sbx.ProposalError):
                    sbx.run_proposal(con, bad, A, 20)

    def test_level_keys_must_be_present(self):
        self.refused('SELECT customer_id, count(*) AS ag_val FROM tx GROUP BY 1', 'pair', 'missing article_id')
        self.refused('SELECT article_id, count(*) AS ag_val FROM tx GROUP BY 1', 'customer', 'missing customer_id')

    def test_keys_must_be_varchar(self):
        self.refused('SELECT length(customer_id) AS customer_id, 1 AS ag_val FROM users', 'customer', 'must be VARCHAR')

    def test_keys_must_not_be_null(self):
        self.refused('SELECT CAST(NULL AS VARCHAR) AS customer_id, 1 AS ag_val', 'customer', 'NULL keys')

    def test_keys_must_be_unique(self):
        self.refused('SELECT customer_id, 1 AS ag_val FROM tx SEMI JOIN users USING (customer_id)', 'customer',
                     'duplicate keys')

    def test_keys_must_lie_inside_their_level_set(self):
        self.refused('SELECT customer_id, article_id, count(*) AS ag_val FROM tx GROUP BY ALL', 'pair', 'outside cand')
        self.refused('SELECT customer_id, count(*) AS ag_val FROM tx GROUP BY ALL', 'customer', 'outside users')
        self.refused("SELECT article_id || 'x' AS article_id, 1 AS ag_val FROM articles", 'article', 'outside articles')

    def test_one_to_three_value_columns(self):
        self.refused('SELECT customer_id FROM users', 'customer', 'got 0')
        self.refused('SELECT customer_id, 1 AS ag_aa, 2 AS ag_bb, 3 AS ag_cc, 4 AS ag_dd FROM users', 'customer', 'got 4')
        values = self.run_sql('SELECT customer_id, 1 AS ag_aa, 2 AS ag_bb, 3 AS ag_cc FROM users', 'customer')
        self.assertEqual(list(values.columns), ['customer_id', 'article_id', 'ag_aa', 'ag_bb', 'ag_cc'])

    def test_value_names_follow_the_pattern(self):
        for name in ('x', 'ag_', 'ag_1x', 'ag_' + 'a'*40, '"ag_Upper"', 'f_ag_x'):
            self.refused(f'SELECT customer_id, 1 AS {name} FROM users', 'customer', 'does not match')
        self.run_sql('SELECT customer_id, 1 AS ag_' + 'a'*39 + ' FROM users', 'customer')

    def test_registered_and_reserved_names_are_refused(self):
        with mock.patch.object(experiment, 'RESERVED', experiment.RESERVED | {'ag_reserved'}):
            self.refused('SELECT customer_id, 1 AS ag_reserved FROM users', 'customer', 'reserved')
        registry = (*engine.feature_registry(), SimpleNamespace(name='ag_registered'))
        with mock.patch.object(engine, 'feature_registry', lambda: registry):
            self.refused('SELECT customer_id, 1 AS ag_registered FROM users', 'customer', 'registered feature')

    def test_names_of_accepted_proposals_are_refused(self):
        sql = 'SELECT customer_id, article_id, row_number() OVER (PARTITION BY customer_id ORDER BY article_id) AS ag_ord FROM cand'
        record, values = self.evaluate(sql)
        self.assertEqual(record['status'], 'valid', record['error'])
        again = sql.replace('row_number()', '1000 - row_number()')
        record, _ = self.evaluate(again, prior=[values])
        self.assertEqual(record['status'], 'invalid')
        self.assertIn('ag_ord: already accepted', record['error'])

    def test_value_types(self):
        allowed = ['CAST(1 AS TINYINT)', 'CAST(1 AS UTINYINT)', 'sum(1)', 'CAST(1 AS HUGEINT)', 'CAST(1 AS UHUGEINT)',
                   'CAST(1.5 AS DECIMAL(18,3))', 'CAST(1.5 AS FLOAT)', '1.5', 'true', 'count(*)']
        for expression in allowed:
            with self.subTest(expression):
                values = self.run_sql(f'SELECT customer_id, {expression} AS ag_val FROM users GROUP BY customer_id',
                                      'customer')
                self.assertEqual(str(values['ag_val'].dtype), 'float64')
        for expression in ("'a'", "DATE '{A}'", 'INTERVAL 1 DAY', '[1, 2]', 'struct_pack(k := 1)'):
            self.refused(f'SELECT customer_id, {expression} AS ag_val FROM users', 'customer', 'has type')

    def test_extra_columns_are_refused(self):
        self.refused('SELECT customer_id, article_id, 1 AS ag_val, 2 AS note FROM cand', 'pair', 'note is not a key')
        self.refused('SELECT customer_id, article_id, 1 AS ag_val FROM cand', 'customer', 'article_id is not a key')

    def test_harness_keeps_cand_order_and_left_joins(self):
        values = self.run_sql('SELECT customer_id, article_id, 1 AS ag_val FROM cand ORDER BY article_id DESC LIMIT 7')
        expected = self.keys.sort_values(['customer_id', 'article_id']).reset_index(drop=True)
        self.assertEqual(values[['customer_id', 'article_id']].values.tolist(), expected.values.tolist())
        self.assertEqual((int(values['ag_val'].notna().sum()), set(values['ag_val'].dropna())), (7, {1.0}))

    def test_null_rule_casts_to_double(self):
        sql = ("SELECT customer_id, CASE n WHEN 1 THEN 'inf'::DOUBLE WHEN 2 THEN '-inf'::DOUBLE "
               "WHEN 3 THEN 'nan'::DOUBLE WHEN 4 THEN 3.5e38 WHEN 5 THEN NULL WHEN 6 THEN 3e38 ELSE 1.5 END AS ag_value, "
               "n = 1 AS ag_flag FROM (SELECT customer_id, row_number() OVER (ORDER BY customer_id) AS n FROM users)")
        values = self.run_sql(sql, 'customer').drop_duplicates('customer_id')
        got = values['ag_value'].tolist()
        self.assertTrue(all(math.isnan(v) for v in got[:5]))
        self.assertEqual((got[5], set(got[6:])), (3e38, {1.5}))
        self.assertEqual(values['ag_flag'].tolist(), [1.0]+[0.0]*(len(values)-1))

    def test_per_proposal_timeout(self):
        started = time.monotonic()
        with self.assertRaises(sbx.ProposalError) as caught:
            self.run_sql(SPIN, 'customer', timeout=0.3)
        self.assertIn('timeout after 0.3 s', str(caught.exception))
        self.assertLess(time.monotonic()-started, 30)

    def test_row_limit(self):
        with mock.patch.object(sbx, 'MAX_ROWS', 5):
            self.refused('SELECT customer_id, 1 AS ag_val FROM users', 'customer', 'exceed the limit of 5')

    def test_proposal_errors_cover_sql_timeout_memory_and_contract_only(self):
        broken = 'SELECT customer_id, FROM users WHERE'
        contract = 'SELECT customer_id FROM users'
        with self.box() as con:
            for sql, text in ((broken, 'ParserException'), (contract, 'got 0')):
                with self.subTest(sql), self.assertRaises(sbx.ProposalError) as caught:
                    sbx.run_proposal(con, proposal(sql, 'customer'), A, 20)
                self.assertIn(text, str(caught.exception))
            with self.assertRaises(sbx.ProposalError) as caught:
                sbx.run_proposal(con, proposal(SPIN, 'customer'), A, 0.3)
            self.assertIn('timeout', str(caught.exception))
            # Technical failures are not renamed: Python errors and DuckDB I/O keep their type.
            for error in (OSError('disk failed'), duckdb.IOException('IO Error: disk failed'), RuntimeError('bug'),
                          duckdb.InterruptException('INTERRUPT Error: Interrupted!')):
                with self.subTest(type(error).__name__), mock.patch.object(sbx, '_check_output', side_effect=error), \
                        self.assertRaises(type(error)) as caught:
                    sbx.run_proposal(con, proposal(CUSTOMER, 'customer'), A, 20)
                self.assertNotIsInstance(caught.exception, sbx.ProposalError)
        with self.box(memory='16MB') as con, self.assertRaises(sbx.ProposalError) as caught:
            sbx.run_proposal(con, proposal(HUNGRY, 'customer'), A, 60)
        self.assertIn('OutOfMemoryException', str(caught.exception))
        # The same mapping in evaluate_proposal (invalid records) and agent_columns (ProposalError with the id).
        small = functools.partial(sbx.sandbox, memory='16MB')
        cases = [(broken, {}, 'ParserException'), (contract, {}, 'got 0'),
                 (SPIN, dict(PROBE_TIMEOUTS={'pair': 20.0, 'customer': 0.3, 'article': 60.0}), 'timeout'),
                 (HUNGRY, dict(sandbox=small), 'OutOfMemoryException')]
        for sql, patches, text in cases:
            with self.subTest(sql), ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(sbx, name, value))
                record, values = self.evaluate(sql, 'customer')
                self.assertEqual((record['status'], values), ('invalid', None))
                self.assertIn(text, record['error'])
        with mock.patch.object(sbx, 'sandbox', small), self.assertRaises(sbx.ProposalError) as caught:
            sbx.agent_columns(self.full, A, self.keys, agent_set(('customer', HUNGRY, ['ag_big'])), threads=2)
        self.assertIn('r1p1: OutOfMemoryException', str(caught.exception))
        with self.assertRaises(OSError) as caught:
            sbx.evaluate_proposal(self.probe, self.artifacts/'missing-export', proposal(CUSTOMER, 'customer'), [],
                                  threads=2)
        self.assertNotIsInstance(caught.exception, sbx.ProposalError)
        with mock.patch.object(sbx, '_fetch', side_effect=OSError('disk failed')), self.assertRaises(OSError):
            self.evaluate(CUSTOMER, 'customer')
        with self.assertRaises(OSError):
            sbx.agent_columns(self.artifacts/'missing-export', A, self.keys, agent_set(('pair', PAIR, ['ag_pair_buys'])))

    # --- agent_columns ----------------------------------------------------------------------------------------

    def test_agent_columns_on_three_levels_match_run_proposal(self):
        chosen = agent_set(('pair', PAIR, ['ag_pair_buys']), ('customer', CUSTOMER, ['ag_cust_n28', 'ag_cust_maxprice']),
                           ('article', ARTICLE, ['ag_art_buyers7']))
        keys = self.shuffled_keys()
        for cache in (None, {}):
            got, info = sbx.agent_columns(self.full, A, keys, chosen, threads=2, cache=cache)
            self.assertEqual(list(got.columns), ['customer_id', 'article_id', *chosen['columns']])
            self.assertEqual(got[['customer_id', 'article_id']].values.tolist(), keys.values.tolist())
            self.assertEqual(list(got.index), list(range(len(keys))))
            self.assertEqual((info['keys'], info['export_digest'], info['set_digest']),
                             (len(keys), self.full_record['digest'], chosen['digest']))
            reference = keys.reset_index(drop=True)
            for item in chosen['proposals']:
                expected = self.run_sql(item['sql'], item['level'])
                merged = reference.merge(expected, on=['customer_id', 'article_id'], how='left', validate='1:1')
                for name in item['columns']:
                    with self.subTest(cache=cache, column=name):
                        self.assertTrue(same(got[name], merged[name]))
                        self.assertEqual(str(got[name].dtype), 'float64')
                        self.assertGreater(info['non_null'][name], 0)

    def test_agent_columns_needs_the_frozen_columns(self):
        chosen = agent_set(('customer', CUSTOMER, ['ag_cust_n28', 'ag_other']))
        with self.assertRaises(sbx.ProposalError) as caught:
            sbx.agent_columns(self.full, A, self.keys, chosen, threads=2)
        self.assertIn('r1p1: value columns', str(caught.exception))

    def test_agent_columns_is_batch_invariant_and_equal_on_the_cut_export(self):
        chosen = agent_set(('pair', PAIR, ['ag_pair_buys']), ('customer', CUSTOMER, ['ag_cust_n28', 'ag_cust_maxprice']),
                           ('article', ARTICLE, ['ag_art_buyers7']))
        whole = sbx.agent_columns(self.full, A, self.keys, chosen, threads=2)[0]
        cut = sbx.agent_columns(self.cut, A, self.keys, chosen, threads=2)[0]
        users = sorted(set(self.keys['customer_id']))
        parts = [sbx.agent_columns(self.full, A, self.keys[self.keys['customer_id'].isin(users[i::3])], chosen,
                                   threads=2)[0] for i in range(3)]
        joined = whole.merge(pd.concat(parts), on=['customer_id', 'article_id'], validate='1:1', suffixes=('', '_b'))
        for name in chosen['columns']:
            with self.subTest(name):
                self.assertTrue(same(whole[name], cut[name]))
                self.assertTrue(same(joined[name], joined[name+'_b']))
        with self.assertRaises(ValueError) as caught:
            sbx.agent_columns(self.cut, '2020-09-16', self.keys, chosen, threads=2)
        self.assertNotIsInstance(caught.exception, sbx.ProposalError)

    def test_agent_columns_refuses_bad_keys(self):
        chosen = agent_set(('pair', PAIR, ['ag_pair_buys']))
        doubled = pd.concat([self.keys.head(3), self.keys.head(1)])
        missing = self.keys.head(3).copy()
        missing.loc[missing.index[0], 'article_id'] = None
        for keys in (doubled, missing, self.keys.head(0), self.keys[['customer_id']]):
            with self.subTest(len(keys)), self.assertRaises(ValueError):
                sbx.agent_columns(self.full, A, keys, chosen, threads=2)

    def test_agent_columns_stops_at_the_wall_deadline(self):
        chosen = agent_set(('customer', SPIN, ['ag_spin']))
        spent = experiment.Deadline(60)
        spent.expires = time.monotonic()-1
        with self.assertRaises(TimeoutError) as caught:
            sbx.agent_columns(self.full, A, self.keys, chosen, threads=2, deadline=spent)
        self.assertEqual(str(caught.exception), kaggle.WALL_LIMIT)
        short = experiment.Deadline(60)
        short.expires = time.monotonic()+3
        with self.assertRaises(TimeoutError) as caught:
            sbx.agent_columns(self.full, A, self.keys, chosen, threads=2, deadline=short)
        self.assertEqual(str(caught.exception), kaggle.WALL_LIMIT)

    def test_article_cache_is_keyed_by_export_and_anchor(self):
        chosen = agent_set(('article', 'SELECT article_id, count(*) AS ag_art_n FROM tx GROUP BY article_id',
                            ['ag_art_n']))
        cache = {}
        with mock.patch.object(sbx, 'sandbox', shifted(sbx.sandbox)):
            leaked, info = sbx.agent_columns(self.full, A, self.keys, chosen, threads=2, cache=cache)
            clean, again = sbx.agent_columns(self.cut, A, self.keys, chosen, threads=2, cache=cache)
        # The day-A rows reach the leaking full export only; a cache keyed by proposal alone would hide it.
        self.assertFalse(same(leaked['ag_art_n'], clean['ag_art_n']))
        self.assertEqual((info['cached'], again['cached']), ([], []))
        self.assertEqual(len(cache), 2)
        digest = hashlib.sha256(chosen['proposals'][0]['sql'].encode()).hexdigest()
        self.assertEqual(set(cache), {(self.full_record['digest'], A, 'r1p1', digest),
                                      (self.cut_record['digest'], A, 'r1p1', digest)})
        repeat, info = sbx.agent_columns(self.cut, A, self.keys, chosen, threads=2, cache=cache)
        self.assertEqual((info['cached'], len(cache)), (['r1p1'], 2))
        self.assertTrue(same(repeat['ag_art_n'], clean['ag_art_n']))
        later, info = sbx.agent_columns(self.full, '2020-09-16', self.keys, chosen, threads=2, cache=cache)
        self.assertEqual((info['cached'], len(cache)), ([], 3))

    def test_read_agent_set_checks_schema_rules_and_digest(self):
        path = self.tmp/'set.json'
        good = agent_set(('pair', PAIR, ['ag_pair_buys']), ('article', ARTICLE, ['ag_art_buyers7']))
        path.write_text(json.dumps(good), encoding='utf-8')
        self.assertEqual(sbx.read_agent_set(path), good)
        self.assertEqual(sbx.set_digest(good['proposals']), experiment.canonical_digest(
            [[p['id'], p['level'], p['sql'], p['columns']] for p in good['proposals']]))

        def broken(edit):
            record = json.loads(json.dumps(good))
            edit(record)
            return record
        cases = [lambda r: r.update(digest='0'*64), lambda r: r.update(format='other'), lambda r: r.pop('budget'),
                 lambda r: r['proposals'][0].update(id='r1p9'), lambda r: r.update(columns=['ag_art_buyers7']),
                 lambda r: r['proposals'][1].update(columns=['ag_pair_buys']),
                 lambda r: r['proposals'][0].update(probe_seconds=float('nan')),
                 lambda r: r['proposals'][0].update(probe_seconds='2^3\u20132^5'),
                 lambda r: r['proposals'][0].update(probe_seconds='1.5'),
                 lambda r: r['proposals'][1].update(round=0, id='r0p2'), lambda r: r.update(proposals=[]),
                 lambda r: r['proposals'][0].update(columns=['customer_id'])]
        for i, edit in enumerate(cases):
            record = broken(edit)
            if i:  # every case but the first keeps a matching digest
                record['digest'] = sbx.set_digest(record['proposals'])
            with self.subTest(i), self.assertRaises(ValueError):
                path.write_text(json.dumps(record), encoding='utf-8')
                sbx.read_agent_set(path)
        unsafe = broken(lambda r: r['proposals'][1].update(
            sql='SELECT article_id, 1 AS ag_art_buyers7 FROM tx SEMI JOIN cand USING (article_id) GROUP BY 1'))
        unsafe['digest'] = sbx.set_digest(unsafe['proposals'])
        with self.assertRaises(sbx.ProposalError) as caught:
            sbx.agent_columns(self.full, A, self.keys, unsafe, threads=2)
        self.assertIn('r1p2', str(caught.exception))

    # --- review regressions: barriers one at a time, error text, identity -------------------------------------

    def test_day_a_partition_is_outside_the_file_list_and_the_allowed_directories(self):
        day_a = sorted((self.full/'tx/d=2020-09-09').glob('*.parquet'))[0]
        day_before = sorted((self.full/'tx/d=2020-09-08').glob('*.parquet'))[0]
        with self.box() as con:
            view = con.execute("SELECT sql FROM duckdb_views() WHERE view_name = 'tx'").fetchone()[0]
            self.assertIn('d=2020-09-08', view)
            self.assertNotIn('d=2020-09-09', view)
            self.assertEqual(con.execute('SELECT max(t_dat) FROM read_parquet(?)', [str(day_before)]).fetchone()[0],
                             date(2020, 9, 8))
            with self.assertRaises(duckdb.PermissionException):
                con.execute('SELECT max(t_dat) FROM read_parquet(?)', [str(day_a)])

    def test_view_filter_hides_a_day_a_row_inside_an_earlier_partition(self):
        crafted = self.writable_copy('export-late-row')
        manifest = json.loads((crafted/'export.json').read_text(encoding='utf-8'))
        rel = next(r for r in sorted(manifest['tx']['files']) if r.startswith('tx/d=2020-09-08/'))
        con = duckdb.connect()
        try:
            con.execute(f"""COPY (SELECT * FROM read_parquet('{crafted/rel}', hive_partitioning=false) UNION ALL
                SELECT DATE '2020-09-09', ?, ?, 555.0, '1') TO '{crafted/rel}.new' (FORMAT PARQUET)""",
                        [CUSTOMERS[0], ARTICLES[0]])
        finally:
            con.close()
        Path(f'{crafted/rel}.new').replace(crafted/rel)
        manifest['tx']['files'][rel] = dict(sha256=experiment.sha256_file(crafted/rel),
                                            rows=manifest['tx']['files'][rel]['rows']+1)
        manifest['tx']['rows'] += 1
        manifest['digest'] = experiment.canonical_digest({k: v for k, v in manifest.items() if k != 'digest'})
        (crafted/'export.json').write_text(json.dumps(manifest), encoding='utf-8')
        sbx.read_export(crafted)
        with self.box(export=crafted) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM tx WHERE price = 555').fetchone()[0], 0)
        with self.box('2020-09-10', export=crafted) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM tx WHERE price = 555').fetchone()[0], 1)

    def test_forbidden_words_each_reject_on_their_own(self):
        for word in ('copy', 'getenv', 'pragma', 'pragma_version', 'current_setting', 'sniff_csv', 'checkpoint',
                     'force_checkpoint', 'which_secret', 'error', 'strptime'):
            with self.subTest(word), self.assertRaises(sbx.ProposalError) as caught:
                sbx.check_sql(f'SELECT customer_id, {word}(1) AS ag_val FROM users', 'customer')
            self.assertIn(f': {word}', str(caught.exception))

    def test_sanitize_error_keeps_names_and_constants_fixed_by_code(self):
        """M23 names and the constants of the validity and contract messages are not data: they stay readable."""
        readable = ['ag_x: |Spearman| with i_buyers7 reaches 0.999; ag_y: fewer than 100 non-NULL rows',
                    'ag_z: fewer than 2 distinct non-NULL values', 'output rows exceed the limit of 20000000',
                    'one to 3 value columns are required besides the keys', 'timeout after 20 s', 'timeout after 60 s',
                    'batch invariance: values of the first 1000 probe customers differ',
                    *(f'ag_x: |Spearman| with {name} reaches 0.999' for name in engine.PILOT_NUMERIC_FEATURES)]
        for text in readable:
            with self.subTest(text=text):
                self.assertEqual(sbx.sanitize_error(text), text)
        # Near misses are still values.
        for text, masked in [('with i_buyers77 reaches 0.9991', 'with <v> reaches <v>'),
                             ('limit of 120000000', 'limit of <digits>'), ('first 1001 customers', 'first <v> customers'),
                             ('x7 = 7 or 21', '<v> = <v> or <v>')]:
            with self.subTest(text=text):
                self.assertEqual(sbx.sanitize_error(text), masked)

    def test_sanitize_error_removes_literals_paths_and_ids(self):
        cases = {
            "Conversion Error: Could not convert string '3 f 2 a 9 b' to INT32": "'…'",
            "Could not convert string 'it''s 0.012,0.034' to INT32": "'…'",
            'Permission Error: Cannot access file "/private/var/folders/x/tlab-hm-sbx-1/data_0.parquet"': '"…"',
            'IO Error: No files found at /private/var/folders/x/tlab-hm-sbx-1/data_0.parquet': '<path>',
            r'Cannot open C:\Users\me\audit.duckdb': '<path>',
            'value 01087-75000 is out of range': '<digits>',
            'value 0.012, 0.034, 0.056 is out of range': '<digits>',
            f'row {CUSTOMERS[4]}': '<hex>',
            f'row {ARTICLES[7]}': '<digits>',
        }
        for text, marker in cases.items():
            with self.subTest(text):
                clean = sbx.sanitize_error(text)
                self.assertIn(marker, clean)
                for leak in ('3 f 2', '0.012', '01087', '/private', 'Users', CUSTOMERS[4][:12], ARTICLES[7], "it''s"):
                    self.assertNotIn(leak, clean)
        rules = [  # (text, masked fragment, marker)
            ('Overflow in multiplication of INT32 (12345 * 67890)!', '12345', '(<digits> * <digits>)'),
            ('value 108775 out of range', '108775', '<digits>'),
            ('row 3f2a9b1c in table', '3f2a9b1c', '<hex>'),
            ('row ABCDEF12 in table', 'ABCDEF12', '<hex>'),
            ('id 3 f 2 a 9 b 1 c 4 d 5 e here', '3 f 2', '<hex>'),
            ('id 3f2a,9b1c,4d5e here', '3f2a', '<hex>'),
            ('id 3f2a-9b1c-4d5e here', '9b1c', '<hex>'),
        ]
        for text, fragment, marker in rules:
            with self.subTest(text):
                clean = sbx.sanitize_error(text)
                self.assertNotIn(fragment, clean)
                self.assertIn(marker, clean)
        # Every other token with a digit becomes <v>, unless the agent's SQL holds it or it is a type name.
        sql = 'SELECT customer_id, CAST(price * 7 AS DECIMAL(18,3)) AS ag_val2 FROM users'
        for text, sql_kept, bare in (
                ('Conversion Error: Type DOUBLE with value 576.92 cannot be cast', None, '576.92'),
                ('value 0108x7752x96 here', None, '0108x7752x96'),
                ('value 3f2az9b1cz4d5ez6a7b here', None, '3f2az9b1cz4d5ez6a7b'),
                ('Could not parse string "2020 x 0.0123" according to format specifier "%Y"\n2020 x 0.0123\n  ^',
                 None, '0.0123'),
                ('Binder Error: column 12 of _x', None, '12'),
                ('Binder Error: Referenced column "ag_val2" not found! Candidate bindings: "ag_val3", "price"',
                 '"ag_val2"', '"ag_val3"'),
                ('Conversion Error: overflow in CAST(price * 7 AS DECIMAL(18,3)) for 576.92', 'DECIMAL(18,3))', '576.92')):
            with self.subTest(text):
                own, bare_clean = sbx.sanitize_error(text, sql), sbx.sanitize_error(text)
                self.assertNotIn(bare, own)
                self.assertNotIn(bare, bare_clean)
                if sql_kept:
                    self.assertIn(sql_kept, own)
        kept = ['Parser Error: syntax error at or near "FROM"\n\nLINE 3: SELECT customer_id FROM users',
                'Conversion Error: Could not convert to INT32 or INT8 or DECIMAL(18,3)',
                'Binder Error: Referenced column "ag_val2" not found; candidates "price", "article_id"',
                'Out of Range Error: value is too large; deadbeef cafe a b c']
        for text in kept:
            with self.subTest(kept=text):
                self.assertEqual(sbx.sanitize_error(text, sql), text)
        self.assertEqual(sbx.sanitize_error('LINE 3: x', ''), 'LINE 3: x')
        self.assertEqual(sbx.sanitize_error('Referenced column "ag_val2" not found'),
                         'Referenced column "…" not found')
        self.assertEqual(sbx._mask(f'{CUSTOMERS[4]} {ARTICLES[7]}'), '<hex> <digits>')

    def test_runtime_failures_carry_only_a_fixed_text(self):
        users = 'FROM tx SEMI JOIN users USING (customer_id) GROUP BY customer_id'
        conversion = 'ConversionException: ' + sbx.RUNTIME_TEXT['ConversionException']
        invalid = 'InvalidInputException: ' + sbx.RUNTIME_TEXT['InvalidInputException']
        out_of_range = 'OutOfRangeException: ' + sbx.RUNTIME_TEXT['OutOfRangeException']
        evasions = [  # every evasion found so far: (sql, level, exact text)
            ("SELECT customer_id, CAST(array_to_string(string_split(customer_id, ''), ' ') AS INT) AS ag_val "
             'FROM users', 'customer', conversion),
            (f"SELECT customer_id, CAST(string_agg(price::VARCHAR, ',') AS INT) AS ag_val {users}", 'customer',
             conversion),
            ("SELECT article_id, CAST(substr(article_id, 1, 5) || '-' || substr(article_id, 6) AS INT) AS ag_val "
             'FROM articles', 'article', conversion),
            ("SELECT customer_id, CAST(current_setting('temp_directory') AS INT) AS ag_val FROM users", 'customer',
             conversion),
            (f"SELECT customer_id, error(string_agg(round(price, 4)::VARCHAR, ' | ')) AS ag_val {users}", 'customer',
             invalid),
            ("SELECT customer_id, CAST(epoch(strptime(string_agg(round(price, 4)::VARCHAR, ' '), '%Y')) AS DOUBLE) "
             f'AS ag_val {users}', 'customer', invalid),
            (f'SELECT customer_id, CAST(CAST(list(struct_pack(d := t_dat, p := price)) AS VARCHAR) AS INT) AS ag_val '
             f'{users}', 'customer', conversion),
            ("SELECT article_id, error(substr(article_id, 1, 4) || 'x' || substr(article_id, 5, 4) || 'x' || "
             'substr(article_id, 9)) AS ag_val FROM articles', 'article', invalid),
            ("SELECT customer_id, error(array_to_string(string_split(customer_id, ''), 'z')) AS ag_val FROM users",
             'customer', invalid),
            (f'SELECT customer_id, CAST(max(price) * 10000 AS TINYINT) AS ag_val {users}', 'customer', conversion),
            ('SELECT article_id, CAST(substr(article_id, 1, 5) AS INT) * 1000000000 AS ag_val FROM articles',
             'article', out_of_range),
            ("SELECT customer_id, CAST(len(regexp_extract_all('a', translate(customer_id, '0123456789', "
             "'ghijklmnop') || '(')) AS DOUBLE) AS ag_val FROM users", 'customer', invalid),
            (f'SELECT customer_id, CAST(CASE WHEN max(price) * 10000 NOT IN (500.00, 576.92, 599.99) '
             f'THEN max(price) * 10000 END AS TINYINT) AS ag_val {users}', 'customer', conversion),
        ]
        for sql, level, _ in evasions:
            if re.search(r'\b(error|strptime|regexp_\w+|current_setting)\s*\(', sql):
                with self.subTest(refused=sql), self.assertRaises(sbx.ProposalError):
                    sbx.check_sql(sql, level)
        sbx.check_sql("SELECT customer_id, try_strptime('x', '%Y') AS ag_val FROM users", 'customer')
        with mock.patch.object(sbx, 'check_sql', lambda sql, level: None):
            for sql, level, text in evasions:
                with self.subTest(sql=sql):
                    with self.box() as con, self.assertRaises(sbx.ProposalError) as caught:
                        sbx.run_proposal(con, proposal(sql, level), A, 20)
                    self.assertEqual(str(caught.exception), text)
                    self.assertIsNone(caught.exception.__context__)  # the DuckDB message is not kept
                    self.assertIsNone(caught.exception.__cause__)
                    record, values = self.evaluate(sql, level)
                    self.assertEqual((record['status'], values, record['error']), ('invalid', None, text))

    def test_planning_errors_stay_readable(self):
        sql = 'SELECT customer_id, ag_missing_column + 1 AS ag_val FROM users'
        with self.box() as con, self.assertRaises(sbx.ProposalError) as caught:
            sbx.run_proposal(con, proposal(sql, 'customer'), A, 20)
        text = str(caught.exception)
        self.assertTrue(text.startswith('BinderException: '), text)
        self.assertIn('"ag_missing_column"', text)
        record, _ = self.evaluate("SELECT customer_id, CAST('x' AS INT32) AS ag_val FROM users WHERE", 'customer')
        self.assertTrue(record['error'].startswith('ParserException: '), record['error'])
        with self.box() as con, self.assertRaises(sbx.ProposalError) as caught:
            sbx.run_proposal(con, proposal('SELECT customer_id, 1 AS ag_val FROM no_such_table', 'customer'), A, 20)
        self.assertTrue(str(caught.exception).startswith('CatalogException: '))
        self.assertIn('no_such_table', str(caught.exception))

    def test_contract_messages_never_quote_data(self):
        pivot = ('SELECT * FROM (PIVOT (SELECT customer_id, article_id FROM tx SEMI JOIN users USING (customer_id)) '
                 'ON article_id USING count(*))')
        rows = ('SELECT customer_id, 1 AS ag_val FROM users, '
                'range(CAST((SELECT max(price) * 100000 FROM tx) AS BIGINT)) t(i)')
        unnamed = 'SELECT customer_id, count(*) FROM tx SEMI JOIN users USING (customer_id) GROUP BY customer_id'
        with mock.patch.object(sbx, 'check_sql', lambda sql, level: None):
            # PIVOT would name columns after data; it expands to several statements and is refused as such.
            for sql, text in ((pivot, 'exactly one SELECT'), (unnamed, 'a column name not written in the SQL'),
                              (rows, 'duplicate keys')):
                with self.subTest(sql), self.box() as con, self.assertRaises(sbx.ProposalError) as caught:
                    sbx.run_proposal(con, proposal(sql, 'customer'), A, 20)
                self.assertIn(text, str(caught.exception))
                self.assertIsNone(re.search(r'[0-9]', str(caught.exception)))

    def test_random_runtime_failures_never_quote_data(self):
        """Property: whatever data a failing expression touches, the text is one fixed class text."""
        rng = random.Random(2026)
        values = ['customer_id', 'article_id', 'price::VARCHAR', 't_dat::VARCHAR', 'sales_channel_id',
                  "string_agg(price::VARCHAR, ' ')", "string_agg(article_id, '')", 'max(t_dat)::VARCHAR',
                  "array_to_string(string_split(min(customer_id), ''), ' ')"]
        wrappers = ['CAST({v} AS INT)', 'CAST({v} AS DATE)', 'error({v})', "strptime({v}, '%Y')",
                    "regexp_matches('a', {v} || '(')", 'CAST(CAST({v} AS VARCHAR) || {k} AS BIGINT)',
                    'CAST(length({v}) * {k} AS TINYINT)']
        fixed = {f'{name}: {text}' for name, text in sbx.RUNTIME_TEXT.items()}
        data = set()
        con = duckdb.connect()
        try:
            for row in con.execute("SELECT customer_id, article_id, CAST(price AS VARCHAR), CAST(t_dat AS VARCHAR) "
                                   "FROM read_parquet(?, hive_partitioning=false)",
                                   [[str(self.full/p) for p in self.full_record['tx']['files']]]).fetchall():
                data.update(row)
        finally:
            con.close()
        with mock.patch.object(sbx, 'check_sql', lambda sql, level: None), self.box() as con:
            for _ in range(16):
                expression = rng.choice(wrappers).format(v=rng.choice(values), k=rng.randint(10**5, 10**9))
                aggregate = 'string_agg' in expression or 'max(' in expression or 'min(' in expression
                sql = (f'SELECT customer_id, {expression} AS ag_val FROM tx SEMI JOIN users USING (customer_id)'
                       + (' GROUP BY customer_id' if aggregate else ''))
                try:
                    sbx.run_proposal(con, proposal(sql, 'customer'), A, 20)
                except sbx.ProposalError as exc:
                    text = str(exc)
                    with self.subTest(sql=sql):
                        if re.match(r'\w+Exception: ', text) and not text.startswith(
                                ('BinderException', 'ParserException', 'CatalogException')):
                            self.assertIn(text, fixed)
                        self.assertFalse(any(len(v) >= 4 and v in text for v in data))
                        self.assertIsNone(re.search(r'[0-9]{3}', text))

    def test_probe_refuses_id_shaped_statistics(self):
        real = sbx._stats
        for name, planted in (('hex', CUSTOMERS[5]), ('digits', ARTICLES[9])):
            output = self.artifacts/'agent'/f'probe-ids-{name}'
            with self.subTest(name), mock.patch.object(sbx, '_stats', lambda con, cutoff: dict(real(con, cutoff),
                                                                                              note=planted)):
                with self.assertRaises(ValueError) as caught:
                    sbx.prepare_probe(self.database, self.full, A, 5, output, threads=2)
                self.assertIn('id-shaped', str(caught.exception))
            self.assertFalse((output/'stats.json').exists())

    def test_single_statement_guard_holds_without_check_sql(self):
        with self.box() as con, mock.patch.object(sbx, 'check_sql', lambda sql, level: None):
            for sql in ('SELECT customer_id, 1.5 AS ag_val FROM users; DROP TABLE cand',
                        'SELECT customer_id, 1.5 AS ag_val FROM users; SELECT 1'):
                with self.subTest(sql), self.assertRaises(sbx.ProposalError) as caught:
                    sbx.run_proposal(con, proposal(sql, 'customer'), A, 20)
                self.assertIn('exactly one SELECT', str(caught.exception))
            self.assertEqual(con.execute('SELECT count(*) FROM cand').fetchone()[0], len(self.keys))

    def test_agent_code_identity_is_one_key_set(self):
        code = sbx.agent_code_identity()
        self.assertEqual(set(code), set(kaggle.code_identity()) | set(sbx.AGENT_CODE))
        self.assertEqual(set(sbx.AGENT_CODE), {'hm_agent_sandbox.py', 'hm_agent_loop.py', 'hm_agent_kaggle.py',
                                               'hm_result_audit.py'})
        self.assertEqual(set(self.full_record['code']), set(code))
        with mock.patch.object(sbx, 'AGENT_CODE', (*sbx.AGENT_CODE, 'hm_absent_module.py')), \
                self.assertRaises(FileNotFoundError):
            sbx.agent_code_identity()

    def test_export_files_are_read_only(self):
        for path in self.full.rglob('*'):
            if path.is_file():
                with self.subTest(path.name):
                    self.assertEqual(path.stat().st_mode & 0o222, 0)

    # --- export ---------------------------------------------------------------------------------------------

    def test_export_layout_and_rows(self):
        record = sbx.read_export(self.full)
        self.assertEqual(list(record), list(sbx.EXPORT_FIELDS))
        self.assertEqual((record['format'], record['status'], record['before']), (sbx.EXPORT_FORMAT, 'completed', None))
        self.assertRegex(record['digest'], '^[0-9a-f]{64}$')
        days = {d for d, _, _ in self.rows} | set(CANARY_DAYS)
        self.assertEqual((record['tx']['rows'], record['tx']['days']), (self.tx_rows, len(days)))
        self.assertEqual(sorted({Path(p).parent.name for p in record['tx']['files']}),
                         sorted(f'd={d.isoformat()}' for d in days))
        self.assertIn('hm_agent_sandbox.py', record['code'])
        con = duckdb.connect()
        try:
            files = [str(self.full/p) for p in record['tx']['files']]
            described = con.execute('DESCRIBE SELECT * FROM read_parquet(?, hive_partitioning=false)', [files]).fetchall()
            self.assertEqual([(r[0], r[1]) for r in described], list(sbx.TX_SCHEMA))
            duplicates = con.execute('''SELECT count(*) FROM read_parquet(?, hive_partitioning=false)
                WHERE t_dat = DATE '2020-09-20' AND customer_id = ? AND article_id = ?''',
                                     [files, CUSTOMERS[2], ARTICLES[5]]).fetchone()[0]
            self.assertGreaterEqual(duplicates, 2)
            articles = con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(self.full/sbx.ARTICLES_FILE)]).fetchall()
            self.assertEqual([r[0] for r in articles], list(sbx.ARTICLE_COLUMNS))
            self.assertEqual(record['articles']['rows'], len(ARTICLES)+1)
        finally:
            con.close()
        cut = sbx.read_export(self.cut)
        self.assertEqual((cut['before'], cut['tx']['last']), (A, '2020-09-08'))
        self.assertEqual(cut['tx']['rows'], sum(1 for d, _, _ in self.rows if d < date(2020, 9, 9)))
        self.assertEqual(sorted(p.name for p in self.full.iterdir()), ['articles', 'export.json', 'tx'])

    def test_export_is_deterministic(self):
        # The other agent modules are part of ``code`` and may change between runs; the data must not.
        with mock.patch.object(sbx, 'agent_code_identity', lambda deadline=None: self.full_record['code']):
            again = sbx.export_history(self.database, self.artifacts/'agent/export-again', threads=2)
        self.assertEqual(again['digest'], self.full_record['digest'])
        self.assertEqual(again['tx']['files'], self.full_record['tx']['files'])

    def test_read_export_refuses_tampering(self):
        copy = self.writable_copy
        changed = copy('tampered-bytes')
        target = changed/sorted(self.full_record['tx']['files'])[0]
        target.write_bytes(target.read_bytes()+b'x')
        extra = copy('tampered-extra')
        (extra/'tx/d=2020-09-23').mkdir()
        (extra/'tx/d=2020-09-23/data_0.parquet').write_bytes(b'x')
        record = copy('tampered-record')
        manifest = json.loads((record/'export.json').read_text(encoding='utf-8'))
        manifest['before'] = A
        (record/'export.json').write_text(json.dumps(manifest), encoding='utf-8')
        for path in (changed, extra, record):
            with self.subTest(path.name), self.assertRaises(ValueError):
                sbx.read_export(path)

    def test_export_refuses_outside_artifacts_and_unaudited_databases(self):
        with self.assertRaises(ValueError):
            sbx.export_history(self.database, self.tmp/'outside-export', threads=2)
        self.assertFalse((self.tmp/'outside-export').exists())
        copy = self.artifacts/'unaudited/audit.duckdb'
        copy.parent.mkdir()
        shutil.copy2(self.database, copy)
        with self.assertRaises(ValueError):
            sbx.export_history(copy, self.artifacts/'agent/unaudited-export', threads=2)
        with self.assertRaises(FileExistsError):
            sbx.export_history(self.database, self.full, threads=2)

    # --- probe ------------------------------------------------------------------------------------------------

    def test_probe_cohort_candidates_and_files(self):
        anchor = date.fromisoformat(A)
        eligible = {u for d, u, _ in self.rows if anchor-timedelta(days=90) <= d < anchor}
        expected = sorted(eligible, key=lambda u: (cohort_key(u, experiment.SEED), u))[:USERS]
        self.assertEqual(sorted(set(self.keys['customer_id'])), sorted(expected))
        self.assertEqual(len(self.keys), 120*USERS)
        self.assertEqual(self.keys.values.tolist(), self.keys.sort_values(['customer_id', 'article_id']).values.tolist())
        sources = read_table(self.probe/'sources.parquet')
        self.assertEqual(set(sources['source']), {'recent', 'global'})
        m23 = read_table(self.probe/'m23.parquet')
        self.assertEqual(list(m23.columns), ['customer_id', 'article_id', *engine.PILOT_NUMERIC_FEATURES])
        self.assertTrue(all(str(m23[c].dtype) == 'float64' for c in engine.PILOT_NUMERIC_FEATURES))
        record = json.loads((self.probe/'probe.json').read_text(encoding='utf-8'))
        self.assertEqual((record['format'], record['status'], record['anchor'], record['users'], record['export_digest']),
                         (sbx.PROBE_FORMAT, 'completed', A, USERS, self.full_record['digest']))
        self.assertEqual(sorted(p.name for p in self.probe.iterdir()), sorted([*sbx.PROBE_FILES, 'probe.json']))
        text = (self.probe/'stats.json').read_text(encoding='utf-8')
        stats = json.loads(text)
        self.assertEqual(stats['anchor'], A)
        self.assertEqual(stats['history']['last_day'], '2020-09-08')
        self.assertEqual(stats['candidates']['users'], USERS)
        self.assertLess(stats['price_all_history']['max'], 1)  # the canary price 999 is after the anchor
        for leak in ('Canary', 'free text', CUSTOMERS[0][:12], ARTICLES[0]):
            self.assertNotIn(leak, text)
        self.assertIsNone(sbx.HEXLIKE.search(text))
        self.assertIsNone(sbx.DIGITS.search(text))

    def test_probe_refusals(self):
        out = self.artifacts/'agent'
        with self.assertRaises(ValueError):
            sbx.prepare_probe(self.database, self.cut, A, USERS, out/'probe-cut', threads=2)
        with self.assertRaises(ValueError):
            sbx.prepare_probe(self.database, self.full, A, 1000, out/'probe-many', threads=2)
        with self.assertRaises(ValueError):
            sbx.prepare_probe(self.database, self.full, '2020-09-16', USERS, out/'probe-late', threads=2)
        failed = json.loads((out/'probe-many/probe.json').read_text(encoding='utf-8'))
        self.assertEqual(failed['status'], 'failed')
        self.assertFalse((out/'probe-cut').exists())

    # --- evaluate_proposal ------------------------------------------------------------------------------------

    def test_evaluate_record_schema(self):
        sql = ("SELECT customer_id, date_diff('day', min(t_dat), DATE '{A}') AS ag_cust_tenure, "
               "avg(CASE WHEN sales_channel_id = '2' THEN 1 ELSE 0 END) AS ag_cust_online "
               "FROM tx SEMI JOIN users USING (customer_id) GROUP BY customer_id")
        record, values = self.evaluate(sql, 'customer')
        self.assertEqual(record['status'], 'valid', record['error'])
        self.assertEqual(list(record), ['id', 'round', 'index', 'name', 'idea', 'level', 'sql', 'status', 'error',
                                        'seconds', 'rows', 'columns'])
        self.assertEqual([c['name'] for c in record['columns']], ['ag_cust_tenure', 'ag_cust_online'])
        for column in record['columns']:
            self.assertEqual(set(column), {'name', 'non_null_share', 'non_null_share_recent', 'non_null_share_global',
                                           'distinct', 'max_abs_spearman', 'nearest'})
            for key in ('non_null_share', 'non_null_share_recent', 'non_null_share_global'):
                self.assertEqual(column[key], round(column[key], 2))
            self.assertEqual(column['max_abs_spearman'], round(column['max_abs_spearman'], 1))
            self.assertTrue(sbx._is_bucket(column['distinct']), column['distinct'])
        self.assertEqual(record['columns'][0]['distinct'], sbx.log2_bucket(values['ag_cust_tenure'].nunique()))
        # Rows and seconds are log2 buckets; the exact probe seconds ride on the frame for the budget only.
        self.assertTrue(sbx._is_bucket(record['seconds']), record['seconds'])
        self.assertEqual(record['rows'], sbx.log2_bucket(len(values)))
        self.assertTrue(math.isfinite(values.attrs['probe_seconds']) and values.attrs['probe_seconds'] >= 0)
        self.assertEqual(list(values.columns), ['customer_id', 'ag_cust_tenure', 'ag_cust_online'])
        json.dumps(record, allow_nan=False)

    def test_log2_bucket(self):
        cases = {0: '0', 1: '2^0\u20132^1', 1.99: '2^0\u20132^1', 2: '2^1\u20132^2', 1023: '2^9\u20132^10',
                 1024: '2^10\u20132^11', 0.3: '2^-2\u20132^-1', 2**-30: '2^-30\u20132^-29'}
        for value, bucket in cases.items():
            with self.subTest(value=value):
                self.assertEqual(sbx.log2_bucket(value), bucket)
                self.assertTrue(sbx._is_bucket(bucket))
        self.assertIsNone(sbx.log2_bucket(None))
        for bad in (-1, float('nan'), float('inf')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sbx.log2_bucket(bad)
        for text in ('2^3\u20132^5', '2^3-2^4', '1', '2^x\u20132^y', '00'):
            self.assertFalse(sbx._is_bucket(text), text)
        path = self.tmp/'bucket-set.json'
        record = agent_set(('pair', PAIR, ['ag_pair_buys']))
        record['proposals'][0]['probe_seconds'] = '2^-3\u20132^-2'
        path.write_text(json.dumps(record), encoding='utf-8')
        self.assertEqual(sbx.read_agent_set(path)['proposals'][0]['probe_seconds'], '2^-3\u20132^-2')

    def test_record_statistics_carry_no_rows(self):
        """Review 21.10: a 3-level step column over customers put purchase rows into p01/p50/p99.

        Customers in hash tiles 1-3 get one value, tiles 4-7 another and 8-10 a third (30/40/30),
        each copied from the earliest transaction before A: round(price*1e6), DATE A - t_dat and
        article_id - 100000000. No record field may equal or contain any of them.
        """
        secret = '(SELECT {expr} FROM tx ORDER BY t_dat, customer_id, article_id, price LIMIT 1)'
        parts = dict(price='CAST(round(price * 1e6) AS BIGINT)', days="DATE '{A}' - t_dat",
                     article='CAST(article_id AS BIGINT) - 100000000')
        levels = [secret.format(expr=expr) for expr in parts.values()]
        sql = ("SELECT customer_id, CASE WHEN tile <= 3 THEN list_sort([{0}, {1}, {2}])[1] "
               "WHEN tile <= 7 THEN list_sort([{0}, {1}, {2}])[2] ELSE list_sort([{0}, {1}, {2}])[3] END AS ag_step "
               "FROM (SELECT customer_id, hash(customer_id) % 10 + 1 AS tile FROM users)").format(*levels)
        with duckdb.connect() as con:
            tx = sorted(con.execute("SELECT t_dat, customer_id, article_id, price FROM "
                                    "read_parquet(?, hive_partitioning = false) WHERE t_dat < DATE '2020-09-09'",
                                    [str(Path(self.full)/'tx/*/*.parquet')]).fetchall(),
                        key=lambda r: (r[0], r[1], r[2], r[3]))
        t_dat, _, article, price = tx[0]
        values = sorted({round(price*1e6), (date(2020, 9, 9)-t_dat).days, int(article)-100000000})
        self.assertEqual(len(values), 3)
        self.assertGreaterEqual(min(values), 100)  # distinctive enough for the substring checks below
        record, table = self.evaluate(sql, 'customer')
        self.assertEqual(record['status'], 'valid', record['error'])
        # The attack is real: on the probe rows the three levels sit exactly at p01, p50 and p99.
        keys = read_table(Path(self.probe)/'keys.parquet')
        rows = keys.merge(table, on='customer_id', how='left')['ag_step'].to_numpy(dtype=float)
        self.assertEqual(sorted(set(np.quantile(rows, [0.01, 0.5, 0.99]).tolist())), [float(v) for v in values])
        computed = dict(record)
        for key in ('id', 'round', 'index', 'name', 'idea', 'level', 'sql'):  # echoed from the proposal
            computed.pop(key)
        text = json.dumps(computed, ensure_ascii=False)
        numbers = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', text)]

        def leaves(node):
            if isinstance(node, dict):
                for item in node.values():
                    yield from leaves(item)
            elif isinstance(node, list):
                for item in node:
                    yield from leaves(item)
            else:
                yield node
        for value in values:
            with self.subTest(value=value):
                self.assertNotIn(str(value), text)
                self.assertNotIn(float(value), numbers)
                for leaf in leaves(computed):
                    self.assertNotEqual(leaf, value)
                    if isinstance(leaf, str):
                        self.assertNotIn(str(value), leaf)

    def test_evaluate_refuses_near_copies_of_m23_prior_and_siblings(self):
        copy = ("SELECT customer_id, count(*) * 2 + 1 AS ag_u28 FROM tx SEMI JOIN users USING (customer_id) "
                "WHERE t_dat >= DATE '{A}' - INTERVAL 28 DAY GROUP BY customer_id")
        record, _ = self.evaluate(copy, 'customer')
        self.assertEqual(record['status'], 'invalid')
        self.assertEqual(record['columns'][0]['nearest'], 'u_tx28')
        self.assertIn('with u_tx28', record['error'])
        # The loop logs the sanitized text; the M23 name and the limit stay readable there.
        self.assertIn('ag_u28: |Spearman| with u_tx28 reaches 0.999', sbx.sanitize_error(record['error'], copy))
        base = ('SELECT customer_id, article_id, row_number() OVER (PARTITION BY customer_id ORDER BY article_id) '
                'AS ag_rank FROM cand')
        record, values = self.evaluate(base)
        self.assertEqual(record['status'], 'valid', record['error'])
        record, _ = self.evaluate(base.replace('ag_rank', 'ag_rank_b'), prior=[values])
        self.assertIn('with ag_rank reaches', record['error'])
        siblings = base.replace('AS ag_rank FROM', 'AS ag_one, 3 * row_number() OVER (PARTITION BY customer_id '
                                                   'ORDER BY article_id) AS ag_two FROM')
        record, _ = self.evaluate(siblings)
        self.assertEqual(record['status'], 'invalid')
        self.assertIn('with ag_two reaches', record['error'])

    def test_evaluate_refuses_sparse_constant_and_failing_sql(self):
        record, _ = self.evaluate('SELECT customer_id, article_id, row_number() OVER () AS ag_few FROM cand LIMIT 50')
        self.assertIn('fewer than 100 non-NULL rows', record['error'])
        # No value quantile is stored at any size (review 21.10).
        self.assertFalse({'p01', 'p50', 'p99'} & set(record['columns'][0]))
        record, _ = self.evaluate('SELECT customer_id, 1 AS ag_one FROM users', 'customer')
        self.assertIn('fewer than 2 distinct', record['error'])
        record, values = self.evaluate('SELECT customer_id, missing_column AS ag_val FROM users', 'customer')
        self.assertEqual((record['status'], values, record['rows']), ('invalid', None, None))
        self.assertIn('BinderException', record['error'])
        self.assertLessEqual(len(record['error']), 400)
        record, _ = self.evaluate("SELECT customer_id, 1 AS ag_val FROM tx WHERE t_dat < DATE '2020-01-01'", 'customer')
        self.assertIn('date literals', record['error'])
        for prior in ([pd.DataFrame({'ag_val': [1.0]})], [pd.DataFrame({'customer_id': ['a'], 'name': [1.0]})], 'frame'):
            with self.subTest(prior=prior), self.assertRaises(ValueError) as caught:
                sbx.evaluate_proposal(self.probe, self.full, proposal(CUSTOMER, 'customer'), prior, threads=2)
            self.assertNotIsInstance(caught.exception, sbx.ProposalError)

    # --- CLI --------------------------------------------------------------------------------------------------

    def test_cli_prints_one_json_line(self):
        out = self.artifacts/'cli'
        code, lines = run_main(['export', '--database', str(self.database), '--output', str(out/'export'),
                                '--before', '2020-09-02', '--threads', '2'])
        self.assertEqual((code, len(lines)), (0, 1), lines)
        printed = json.loads(lines[0])
        self.assertEqual(set(printed), {'status', 'before', 'rows', 'days', 'files', 'articles', 'digest'})
        self.assertEqual((printed['status'], printed['before']), ('completed', '2020-09-02'))
        code, lines = run_main(['probe', '--database', str(self.database), '--export', str(self.full), '--anchor', A,
                                '--users', '5', '--output', str(out/'probe'), '--threads', '2'])
        self.assertEqual((code, len(lines)), (0, 1), lines)
        printed = json.loads(lines[0])
        self.assertEqual((printed['status'], printed['users'], printed['rows'], printed['export_digest']),
                         ('completed', 5, 600, self.full_record['digest']))

    def test_cli_refuses_without_isolation_and_reports_usage(self):
        out = self.artifacts/'cli-refused'
        for argv in (['export', '--database', str(self.database), '--output', str(out/'export')],
                     ['probe', '--database', str(self.database), '--export', str(self.full), '--anchor', A,
                      '--output', str(out/'probe')]):
            code, lines = run_main(argv, isolated=lambda: False)
            with self.subTest(argv[0]):
                self.assertEqual((code, len(lines)), (1, 1))
                printed = json.loads(lines[0])
                self.assertEqual((printed['status'], printed['command'], printed['error_type']),
                                 ('failed', argv[0], 'RuntimeError'))
                self.assertIn('python -I', printed['message'])
        self.assertFalse(out.exists())
        for argv, command in (([], None), (['probe', '--users', 'many'], 'probe'), (['export'], 'export')):
            code, lines = run_main(argv)
            with self.subTest(argv):
                self.assertEqual((code, len(lines)), (1, 1))
                self.assertEqual(json.loads(lines[0]), dict(status='failed', command=command, error_type='UsageError',
                                                            message=json.loads(lines[0])['message']))
        cli = subprocess.run([sys.executable, SCRIPT, 'export', '--database', str(self.database), '--output',
                              str(out/'subprocess')], capture_output=True, text=True, timeout=300)
        self.assertEqual((cli.returncode, json.loads(cli.stdout)['error_type']), (1, 'RuntimeError'))
        self.assertFalse(out.exists())

    def test_cli_masks_native_errors_and_reports_the_wall_limit(self):
        out = self.artifacts/'cli-failed'
        argv = ['probe', '--database', str(self.database), '--export', str(self.full), '--anchor', A,
                '--users', '5', '--threads', '2', '--output']
        native = duckdb.BinderException(f'row {CUSTOMERS[3]} 0108775000')
        with mock.patch.object(kaggle, 'create_item_ranks', side_effect=native):
            code, lines = run_main([*argv, str(out/'native')])
        self.assertEqual((code, len(lines)), (1, 1))
        printed = json.loads(lines[0])
        self.assertEqual(printed['error_type'], 'BinderException')
        self.assertNotIn(CUSTOMERS[3], lines[0])
        self.assertIn('Native library error', printed['message'])
        real, made = experiment.Deadline, []

        def recording(seconds):
            made.append(real(seconds))
            return made[-1]

        def interrupted(con, *args, **kwargs):
            deadline = made[-1]
            deadline.expires = time.monotonic()+0.3
            timer = deadline.interrupt_sql(con)
            try:
                con.execute(ENDLESS).fetchone()
            finally:
                timer.cancel()
        with mock.patch.object(experiment, 'Deadline', recording), \
                mock.patch.object(kaggle, 'create_item_ranks', interrupted):
            code, lines = run_main([*argv, str(out/'wall')])
        self.assertEqual((code, len(lines)), (1, 1))
        self.assertEqual(json.loads(lines[0]), dict(WALL, command='probe'))
        error = json.loads((out/'wall/probe.json').read_text(encoding='utf-8'))['error']
        self.assertEqual((error['type'], error['cause']), ('TimeoutError', 'InterruptException'))
        self.assertFalse((out/'wall/duckdb-temp').exists())


if __name__ == '__main__':
    unittest.main()
