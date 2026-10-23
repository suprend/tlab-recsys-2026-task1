"""Synthetic tests of scripts/otto_agent.py (docs/otto-design.md §5, §11).

No real OTTO data is read and no LLM is called: raw files, partitions, collections and
receipts are built inside a throwaway Git repository that stands in for ROOT; the agent's
replies come from a fake ``ask``. DuckDB runs with at most 2 threads and 1-2 GB.
"""
import contextlib
import io
import json
import os
from pathlib import Path
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

from scripts import otto_agent as oa
from scripts import otto_common as oc
from scripts import otto_data as od
from scripts import otto_model as om
from tests.test_otto_data import IDENTITY, S5, ev, git, write_raw

DAY = oc.DAY
REPO = Path(oa.__file__).resolve().parents[1]
NAMES = od.TYPE_NAMES
THREADS = 2
MEMORY = '1GB'
POOL = 150
POPULATION = 60
MIN_SOURCE = 50          # MIN_SOURCE_SESSIONS of the synthetic world (the pool is 150 sessions)
N_T = oc.N_T


def small_duckdb():
    con = duckdb.connect()
    con.execute(f'SET threads={THREADS}')
    con.execute(f"SET memory_limit='{MEMORY}'")
    return con


def make_world(seed=5, n_per_week=260, n_items=120, test_sessions=12, w3_suffix=None):
    """Sessions of W1..W4 drawn mostly from one cluster of 10 items each (co-visitation has signal).

    ``w3_suffix(session, events)`` may rewrite the events of a W3 session (suffix substitution).
    """
    rng = np.random.default_rng(seed)
    clusters = n_items // 10
    train, test = {}, {}
    sid = 1
    for week in (1, 2, 3, 4):
        start = oc.week_start(week, S5)
        for _ in range(n_per_week):
            first = start + int(rng.integers(0, 6*DAY))
            cluster = int(rng.integers(clusters))
            n = int(rng.integers(6, 15))
            events, ts = [], first
            for _ in range(n):
                if week == 4 and ts >= S5:
                    break
                aid = 1 + cluster*10 + int(rng.integers(10)) if rng.random() < 0.8 else int(rng.integers(1, n_items+1))
                kind = NAMES[int(rng.choice(3, p=[0.75, 0.17, 0.08]))]
                events.append(ev(aid, ts, kind, int(rng.integers(0, 1000))))
                ts += int(rng.integers(10, 600))
            if week == 3 and w3_suffix is not None:
                events = w3_suffix(sid, events)
            train[sid] = events
            sid += 1
    for i in range(test_sessions):
        first = S5 + int(rng.integers(0, 6*DAY)) if i else S5
        test[900_000+i] = [ev(int(rng.integers(1, n_items+1)), first + j*60, NAMES[0], 5) for j in range(4)]
    return train, test


class World:
    """A temp repository with load, otto-base.json, probe-F3 and val-F3 (and optionally a probe dir)."""

    def __init__(self, seed=5, probe=True, pool=POOL, population=POPULATION, **world):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q')
        (self.root/'configs'/'datasets').mkdir(parents=True)
        (self.root/'artifacts'/'otto').mkdir(parents=True)
        (self.root/'README').write_text('x')
        git(self.root, 'add', 'README')
        git(self.root, 'commit', '-q', '-m', 'init')
        self.patches = [mock.patch.object(oc, 'ROOT', self.root),
                        mock.patch.object(oc, 'code_identity', return_value=IDENTITY),
                        mock.patch.object(oa, 'MEMORY', MEMORY), mock.patch.object(oa, 'TABLE_MEMORY', MEMORY),
                        mock.patch.object(oa, 'MAX_TEMP', '2GB'),
                        mock.patch.dict(oa.PROBE_THREADS, table=THREADS, other=THREADS),
                        mock.patch.object(oa, 'MIN_SOURCE_SESSIONS', MIN_SOURCE)]
        for patch in self.patches:
            patch.start()
        try:
            train, test = make_world(seed, **world)
            self.train = train
            write_raw(self.root/oc.RAW_DIR, train, test)
            od.load(threads=THREADS, memory=MEMORY, check_contract=False)
            self.base = od.initial_base()
            oc.atomic_json(oc.config_path('base'), self.base)
            self.probe_collection = Path(od.collect('probe', self.base, threads=THREADS, memory=MEMORY,
                                                    probe_pool=pool)['path'])
            self.val = Path(od.collect('val', self.base, threads=THREADS, memory=MEMORY, n_train=20,
                                       dev_population=population, probe_pool=pool)['path'])
            write_smoke(N_T)
            self.probe = None
            if probe:
                self.calibration = oa.calibrate('cal', threads=THREADS)
                self.probe = Path(oa.prepare_probe('probe', threads=THREADS, memory=MEMORY)['path'])
        except BaseException:
            self.close()
            raise

    def close(self):
        for patch in reversed(self.patches):
            patch.stop()
        oa._FINGERPRINTS.clear()
        oa._KNOWN.clear()
        self.tmp.cleanup()


def write_smoke(n_t, name='smoke-1'):
    """A smoke.json of otto_model's format (the smoke run precedes the agent loop)."""
    path = oc.output_dir('smoke', name)/'smoke.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    oc.atomic_json(path, dict(format=oa.SMOKE_FORMAT, N_t=n_t), exist_ok=True)
    return path


def make_set(base, proposals, t_tb=1200):
    """A checked otto set dict from proposals (id, round, index, name, kind, level, sql[, columns])."""
    props, tables = [], []
    for p in proposals:
        p = dict(idea='x', **p)
        p['depends'] = oa.check_sql(p['sql'], p['kind'], p['level'], tables=tables)
        if p['kind'] == 'source':
            p['columns'] = oa.source_columns(p['name'])
        if p['kind'] == 'table':
            tables.append(p['name'])
        props.append(p)
    prompt = oa.prompt_identity()
    record = dict(format=oa.SET_FORMAT, run={}, probe={}, run_sha256='x', base_digest=base['digest'], prompt=prompt,
                  prompt_digest=prompt['digest'], t_tb=t_tb, code={},
                  candidates=dict(sources=[p['name'] for p in props if p['kind'] == 'source']), proposals=props,
                  attempts=[], columns=[c for p in props if p['kind'] != 'table' for c in p['columns']],
                  tables=tables, budget={}, digest=oa.set_digest(props), audit=None)
    return oa.check_set(record, base)


# =============================================================================== the agent's SQL

COVIS = ('SELECT a.item AS item, b.item AS item2, CAST(count(*) AS DOUBLE) AS tv_cnt FROM hist a JOIN hist b '
         'ON a.session = b.session AND a.item <> b.item AND abs(a.seq - b.seq) <= 3 GROUP BY a.item, b.item '
         'QUALIFY row_number() OVER (PARTITION BY a.item ORDER BY count(*) DESC, b.item) <= 20')
COVIS_SRC = ('SELECT s.session AS session, t.item2 AS item, CAST(sum(t.tv_cnt) AS DOUBLE) AS score FROM sess s '
             'JOIN sessions b ON b.session = s.session JOIN tb_covis t ON t.item = s.item GROUP BY s.session, t.item2 '
             'QUALIFY row_number() OVER (PARTITION BY s.session ORDER BY sum(t.tv_cnt) DESC, t.item2) <= 30')
POP_SRC = ('WITH p AS (SELECT item, count(*) + 5*count(*) FILTER (WHERE event = \'cart\') AS n FROM hist '
           'WHERE ts >= {S} - 14*86400 GROUP BY item ORDER BY n DESC, item LIMIT 25) '
           'SELECT s.session AS session, p.item AS item, CAST(p.n AS DOUBLE) AS score FROM sessions s CROSS JOIN p')
# repeat B: the 7-day item count is i_h7_all; the latest occurrence first is the order of h_rank (|rho| = 1)
POP7_SRC = ('WITH p AS (SELECT item, count(*) AS n FROM hist WHERE ts >= {S} - 7*86400 GROUP BY item '
            'ORDER BY n DESC, item LIMIT 25) SELECT s.session AS session, p.item AS item, CAST(p.n AS DOUBLE) AS score '
            'FROM sessions s CROSS JOIN p')
HIST_SRC = ('SELECT session, item, CAST(max(seq) AS DOUBLE) AS score FROM sess JOIN sessions USING (session) '
            'GROUP BY session, item QUALIFY row_number() OVER (PARTITION BY session ORDER BY max(seq) DESC, item) <= 20')
FEW_SRC = ('SELECT session, item, CAST(max(seq) AS DOUBLE) AS score FROM sess JOIN sessions USING (session) '
           'WHERE seq >= 9 GROUP BY session, item')
HUGE_SRC = ('SELECT session, item, CAST(1e39 AS DOUBLE) AS score FROM cand '
            'QUALIFY row_number() OVER (PARTITION BY session ORDER BY item) <= 5')
COVIS_MAX = ('SELECT c.session AS session, c.item AS item, CAST(coalesce(max(t.tv_cnt), 0) AS DOUBLE) AS ag_covis_max '
             'FROM cand c LEFT JOIN sess s ON s.session = c.session LEFT JOIN tb_covis t ON t.item = s.item '
             'AND t.item2 = c.item GROUP BY c.session, c.item')
USERS14 = ('SELECT item, CAST(count(DISTINCT session) AS DOUBLE) AS ag_item_users14 FROM hist '
           'WHERE ts >= {S} - 14*86400 GROUP BY item')
RATIO = ('SELECT s.session AS session, CAST(count(DISTINCT s.item) AS DOUBLE) / count(*) AS ag_ratio FROM sess s '
         'JOIN sessions b ON b.session = s.session GROUP BY s.session')
BATCHY = 'SELECT session, item, CAST(count(*) OVER (PARTITION BY item) AS DOUBLE) AS ag_batchy FROM cand'
DUP_B = ('SELECT item, CAST(count(*) AS DOUBLE) AS ag_dup FROM hist WHERE ts >= {S} - 7*86400 GROUP BY item')
WIDE_TABLE = ('SELECT a.item AS item, b.item AS item2, 1.0 AS tv_one FROM (SELECT DISTINCT item FROM hist) a '
              'CROSS JOIN (SELECT DISTINCT item FROM hist) b WHERE a.item <> b.item')
WIDE_SRC = ('SELECT s.session AS session, i.item AS item, CAST(i.item AS DOUBLE) AS score FROM sessions s '
            'CROSS JOIN (SELECT DISTINCT item FROM hist) i')
GHOST_SRC = ('SELECT session, CAST(item + 500000 AS BIGINT) AS item, 1.0 + item AS score FROM cand '
             'QUALIFY row_number() OVER (PARTITION BY session ORDER BY item) <= 5')


def proposal(name, kind, level, sql):
    return dict(name=name, idea=f'idea of {name}', kind=kind, level=level, sql=sql)


REPLIES = {
    1: [proposal('covis', 'table', 'item_pair', COVIS), proposal('covis_src', 'source', 'pair', COVIS_SRC),
        proposal('pop_src', 'source', 'pair', POP_SRC), proposal('peek', 'source', 'pair', 'SELECT * FROM labels'),
        proposal('early_feature', 'feature', 'item', USERS14)],
    2: [proposal('wide', 'table', 'item_pair', WIDE_TABLE), proposal('ghost', 'source', 'pair', GHOST_SRC),
        proposal('covis_again', 'source', 'pair', COVIS_SRC), proposal('wide_src', 'source', 'pair', WIDE_SRC),
        proposal('on_wide', 'source', 'pair', COVIS_SRC.replace('tb_covis', 'tb_wide'))],
    3: [proposal('covis_max', 'feature', 'pair', COVIS_MAX), proposal('users14', 'feature', 'item', USERS14),
        proposal('ratio', 'feature', 'session', RATIO), proposal('batchy', 'feature', 'pair', BATCHY),
        proposal('late_source', 'source', 'pair', POP_SRC)],
    4: [proposal('dup', 'feature', 'item', DUP_B)],
}


class FakeAsk:
    """Prepared replies per round; the first call fails once (the loop retries it)."""

    def __init__(self):
        self.calls, self.prompts = 0, []

    def __call__(self, prompt, model):
        self.calls += 1
        self.prompts.append(prompt)
        if self.calls == 1:
            error = RuntimeError('claude gave no answer')
            error.meta = dict(cost_usd=0.5, seconds=1.0)
            raise error
        number = int(prompt.split('This is round ')[1].split(' ')[0])
        return [dict(p) for p in REPLIES[number]], dict(cost_usd=1.25, seconds=2.0, text='[...]', command=['claude'])


# =============================================================================== pure checks (no data)

class CheckSqlTest(unittest.TestCase):
    def ok(self, sql, kind='feature', level='pair', tables=()):
        return oa.check_sql(sql, kind, level, tables)

    def bad(self, sql, pattern, kind='feature', level='pair', tables=()):
        with self.assertRaisesRegex(oa.ProposalError, pattern):
            oa.check_sql(sql, kind, level, tables)

    def test_time_rules(self):
        self.ok('SELECT session, item, CAST({S} - max(ts) AS DOUBLE) AS ag_age FROM cand JOIN hist USING (session, item) '
                'WHERE ts >= {S} - 7*86400 GROUP BY ALL')
        self.ok('SELECT item, count(*) AS ag_n FROM hist WHERE ts < {E} GROUP BY item', level='item')
        self.bad('SELECT item, count(*) AS ag_n FROM hist WHERE ts > 1661000000 GROUP BY item', '9 or more digits|ts may not',
                 level='item')
        self.bad('SELECT item, count(*) AS ag_n FROM hist WHERE ts > 100 GROUP BY item', 'ts may not', level='item')
        self.bad('SELECT item, count(*) AS ag_n FROM hist WHERE {S} - 86400 <= ts GROUP BY item', 'left',
                 level='item')
        self.bad('SELECT item, count(*) AS ag_n FROM hist WHERE ts BETWEEN 5 AND 9 GROUP BY item', 'ts may not',
                 level='item')
        self.bad('SELECT item, count(*) AS ag_n FROM hist WHERE {A} > 0 GROUP BY item', r'\{S\} and \{E\}',
                 level='item')
        self.bad("SELECT item, count(*) AS ag_n FROM hist WHERE to_timestamp(ts) > '2022-08-01' GROUP BY item",
                 'date literals', level='item')
        self.bad('SELECT item, 123456789 AS ag_n FROM hist', '9 or more digits', level='item')

    def test_forbidden_words_commands_and_paths(self):
        for sql, pattern in (
                ("SELECT * FROM read_parquet('x')", 'forbidden'),
                ("SELECT * FROM read_csv_auto('x')", 'forbidden'),
                ('COPY (SELECT 1) TO \'out.csv\'', 'SELECT or WITH'),
                ("SELECT 1 AS ag_x FROM cand; COPY cand TO 'x.csv'", 'one statement'),
                ("SELECT 1 AS ag_x FROM cand -- note", 'comments'),
                ('WITH a AS (SELECT 1) SELECT * FROM a, (ATTACH)', 'forbidden'),
                ('SELECT * FROM cand WHERE 1 = (SELECT 1 FROM duckdb_settings())', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM cand, labels', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM cand, suffix_events', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM train', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM cand WHERE getenv(1) IS NULL', 'forbidden'),
                ('SELECT session, item, random() AS ag_x FROM cand', 'forbidden'),
                ("SELECT session, item, length('data/otto.jsonl') AS ag_x FROM cand", 'forbidden|path'),
                ("SELECT session, item, length('/tmp/x') AS ag_x FROM cand", 'path'),
                ("SELECT session, item, length('a.parquet') AS ag_x FROM cand", 'path'),
                ('SELECT session, item, 1 AS ag_x FROM cand WHERE error(1) IS NULL', 'forbidden'),
        ):
            with self.subTest(sql=sql):
                self.bad(sql, pattern)
        for word in ('INSTALL httpfs', 'LOAD httpfs', 'SET threads=8', 'ATTACH x'):
            with self.subTest(word=word):
                self.bad(f'SELECT 1 AS ag_x FROM cand WHERE 1 = 1 OR {word}', 'forbidden')

    def test_hashes_catalogs_dollars_and_session_literals(self):
        for sql, pattern in (
                ('SELECT session, item, CAST(hash(session) AS DOUBLE) AS ag_x FROM cand', 'forbidden'),
                ('SELECT session, item, length(sha256(CAST(item AS VARCHAR))) AS ag_x FROM cand', 'forbidden'),
                ('SELECT session, item, length(md5(CAST(item AS VARCHAR))) AS ag_x FROM cand', 'forbidden'),
                ('SELECT session, item, crc32(CAST(item AS VARCHAR)) AS ag_x FROM cand', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM cand, pg_views', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM cand WHERE getvariable(1) IS NULL', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM (SUMMARIZE cand)', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM (DESCRIBE cand)', 'forbidden'),
                ('SELECT session, item, 1 AS ag_x FROM (SHOW TABLES)', 'forbidden'),
                ("SELECT session, item, length($$data/x.parquet$$) AS ag_x FROM cand", r'"\$"'),
                ("SELECT session, item, length('part.ndjson') AS ag_x FROM cand", 'forbidden|path'),
                ('SELECT session, item, 1 AS ag_x FROM cand WHERE session = 5', 'session may not'),
                ('SELECT session, item, 1 AS ag_x FROM cand WHERE 3 < c.session', 'session may not'),
                ('SELECT session, item, 1 AS ag_x FROM cand c WHERE c.session IN (1, 2)', 'session may not'),
                ('SELECT session, item, 1 AS ag_x FROM cand WHERE session BETWEEN 1 AND 9', 'session may not'),
                ('SELECT session, item, CAST(session % 7 AS DOUBLE) AS ag_x FROM cand', 'session may not'),
                ('SELECT session, item, 1 AS ag_x FROM cand c WHERE 7 % c.session = 0', 'session may not'),
        ):
            with self.subTest(sql=sql):
                self.bad(sql, pattern)
        self.ok('SELECT c.session, c.item, CAST(count(*) AS DOUBLE) AS ag_share FROM cand c JOIN sess s '
                'ON s.session = c.session AND s.item = c.item GROUP BY c.session, c.item')

    def test_tables_and_item_queries_ignore_the_batch(self):
        self.bad('SELECT a.item AS item, b.item AS item2, 1 AS tv_x FROM cand a, cand b', 'must not use cand',
                 kind='table', level='item_pair')
        self.bad('SELECT item, count(*) AS ag_n FROM hist JOIN sessions USING (session) GROUP BY item',
                 'must not use sessions', level='item')
        self.assertEqual(self.ok('SELECT session, item, 1 AS score FROM cand JOIN tb_b USING (item) JOIN tb_a '
                                 'USING (item)', kind='source', tables=['a', 'b']), ['b', 'a'])
        self.bad('SELECT session, item, 1 AS score FROM cand JOIN tb_c USING (item)', 'tb_c is not a table',
                 kind='source', tables=['a'])
        self.bad('SELECT 1', 'level', kind='source', level='item')

    def test_substitution_and_neutral_names(self):
        self.assertEqual(oa.substitute('ts >= {S} - 7 AND ts < {E}', 100, 200), 'ts >= 100 - 7 AND ts < 200')
        self.assertEqual(oa.neutral('p_clicks, carts of the aid, orders'), 'p_view, cart of the item, order')
        self.assertEqual(oa.mask_names('an OTTO kaggle competition'), 'an <name> <name> <name>')

    def test_parse_proposals_needs_the_five_fields(self):
        text = 'here: ' + json.dumps([proposal('a', 'table', 'item_pair', 'SELECT 1')])
        self.assertEqual(oa.parse_proposals(text)[0]['kind'], 'table')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            oa.parse_proposals(json.dumps([dict(name='a', idea='b', level='pair', sql='SELECT 1')]))

    def test_ask_proposals_takes_over_the_four_field_refusal(self):
        reply = json.dumps([proposal('a', 'source', 'pair', 'SELECT 1')])
        error = RuntimeError('Unparsable reply: missing fields')
        error.meta = dict(text=reply, cost_usd=1.0)
        with mock.patch.object(oa, 'ask_llm', side_effect=error):
            items, meta = oa.ask_proposals('prompt', oa.MODEL)
        self.assertEqual(items[0]['name'], 'a')
        self.assertEqual(meta['cost_usd'], 1.0)
        other = RuntimeError('claude call refused: not isolated')
        other.meta = dict(text=reply)
        with mock.patch.object(oa, 'ask_llm', side_effect=other):
            with self.assertRaisesRegex(RuntimeError, 'not isolated'):
                oa.ask_proposals('prompt', oa.MODEL)

    def test_table_timeout_calibration_clamp(self):
        self.assertEqual(oa.table_timeout(100), (1200, None))
        self.assertEqual(oa.table_timeout(401), (1260, None))
        self.assertEqual(oa.table_timeout(500), (1500, None))
        self.assertEqual(oa.table_timeout(700), (1800, None))
        value, limitation = oa.table_timeout(1801)
        self.assertEqual(value, 1800)
        self.assertIn('t_20 above', limitation)
        self.assertEqual(oa.table_timeout(None, timed_out=True)[0], 1800)

    def test_table_timeout_on_a_fold_scales_with_sum_n2_unclamped(self):
        load = dict(facts=dict(sum_n2_upper=dict(F2=2.0e9, F3=1.0e9, F4=4.0e9, F5=0.5e9)))
        with mock.patch.object(od, 'read_load', return_value=load):
            self.assertEqual(oa.table_timeout_on(4, 1200), 1.5*1200*4)              # 7200 s, above the 1800 cap
            self.assertEqual(oa.table_timeout_on(4, 1200, factor=2), 2*1.5*1200*4)
            self.assertEqual(oa.table_timeout_on(2, 1800), 1.5*1800*2)
            self.assertEqual(oa.table_timeout_on(3, 1200), oa.TABLE_TIMEOUT_MIN)    # 1800 < 3600
            self.assertEqual(oa.table_timeout_on(5, 1800), oa.TABLE_TIMEOUT_MIN)

    def test_ba_union_rule(self):
        b = pd.DataFrame({'session': [1, 1, 1, 2], 'aid': [10, 11, 12, 20]})
        s1 = pd.DataFrame({'session': [1, 1, 1, 2], 'aid': [11, 30, 31, 21], 'score': [9.0, 8.0, 7.0, 1.0],
                           'rank': [1, 2, 3, 1]})
        s2 = pd.DataFrame({'session': [1, 1, 1], 'aid': [40, 31, 30], 'score': [5.0, 4.0, 3.0], 'rank': [1, 2, 3]})
        frame = oa.ba_union(b, [('one', s1), ('two', s2)], limit=5)
        got = frame[frame.session == 1]
        # B (10, 11, 12) always; then rank 1 of two (40); rank 2: 30 of source one before 31 of two
        self.assertEqual(sorted(got.aid), [10, 11, 12, 30, 40])
        self.assertTrue(got[got.aid.isin([10, 11, 12])].in_b.all())
        row30 = got[got.aid == 30].iloc[0]
        self.assertEqual((row30['ag_src_one_rank'], row30['ag_src_two_rank']), (2, 3))
        row11 = got[got.aid == 11].iloc[0]
        self.assertEqual(row11['ag_src_one_rank'], 1)
        self.assertTrue(pd.isna(row11['ag_src_two_rank']))
        self.assertEqual(sorted(frame[frame.session == 2].aid), [20, 21])
        # B is kept whole even above the limit; no agent item then
        tight = oa.ba_union(b, [('one', s1)], limit=2)
        self.assertEqual(sorted(tight[tight.session == 1].aid), [10, 11, 12])
        self.assertEqual(list(frame.columns), ['session', 'aid', 'in_b', 'ag_src_one_rank', 'ag_src_one_score',
                                               'ag_src_two_rank', 'ag_src_two_score'])

    def test_prompt_number_whitelist(self):
        base = od.initial_base()
        stats = dict(prefix_sessions=321)
        constants = oa.prompt_constants(1260, N_T)
        self.assertEqual(oa.prompt_number_problems({'stats': 'sessions 321', 'x': 'tables 1260 s'}, stats, base,
                                                   constants, []), [])
        self.assertEqual(oa.prompt_number_problems({'stats': 'sessions 4242'}, stats, base, constants, []),
                         [('stats', '4242')])
        self.assertEqual(oa.prompt_number_problems({'history': 'recall 0.37'}, stats, base, constants,
                                                   ['recall 0.37']), [])
        with mock.patch.object(oa, '_candidates_text', return_value='the first 77 items'):
            with self.assertRaisesRegex(ValueError, 'candidates:77'):
                oa.render_prompt(stats, base, '', 1, oa.budget_limits(1260), 1260, N_T)

    def test_prompt_is_neutral_and_carries_the_warning(self):
        base = od.initial_base()
        prompt = oa.render_prompt(dict(prefix_sessions=321), base, '', 1, oa.budget_limits(1260), 1260, N_T)
        self.assertIsNone(oa.NAMES_IN_PROMPT.search(prompt))
        self.assertIn(oa.WARNING, ' '.join(prompt.split()))
        self.assertIn('0.10*R_view + 0.30*R_cart +\n0.60*R_order', prompt)
        self.assertIn('table 1260 s', prompt)
        self.assertIn('phase S: table and source only', prompt)
        self.assertIn('p_view', prompt)
        self.assertNotIn('aid', prompt.replace('said', ''))
        late = oa.render_prompt(dict(prefix_sessions=321), base, '', 3, oa.budget_limits(1260), 1260, N_T)
        self.assertIn('phase F: table and feature only', late)

    def test_prompt_constants_follow_the_recipe_and_the_smoke(self):
        constants = oa.PROMPT_CONSTANTS
        self.assertEqual((constants['trees'], constants['depth'], constants['learning_rate'], constants['l2'],
                          constants['borders']),
                         tuple(om.RECIPE[k] for k in ('iterations', 'depth', 'learning_rate', 'l2_leaf_reg',
                                                      'border_count')))
        self.assertEqual(oa.SMOKE_N_T, (oc.N_T, om.SMOKE_REDUCED_N_T))
        self.assertEqual(constants['history_days'], {f'F{k}': oc.history_days(k) for k in (2, 3, 4, 5)})
        with self.assertRaisesRegex(oc.ContractError, 'N_t must be one of'):
            oa.prompt_constants(1260, 12345)
        reduced = oa.render_prompt(dict(prefix_sessions=321), od.initial_base(), '', 1, oa.budget_limits(1260), 1260,
                                   om.SMOKE_REDUCED_N_T)
        self.assertIn(f'the first {om.SMOKE_REDUCED_N_T} sessions', reduced)

    def test_smoke_n_t_reads_one_smoke_result(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(oc, 'ROOT', Path(tmp)):
            with self.assertRaisesRegex(oc.ContractError, '0 found'):
                oa.smoke_n_t()
            path = write_smoke(om.SMOKE_REDUCED_N_T)
            n_t, record = oa.smoke_n_t()
            self.assertEqual((n_t, record['N_t'], record['sha256']), (om.SMOKE_REDUCED_N_T, om.SMOKE_REDUCED_N_T,
                                                                      oc.sha256_file(path)))
            oc.atomic_json(path, dict(format=oa.SMOKE_FORMAT, N_t=30000), exist_ok=True)
            with self.assertRaisesRegex(oc.ContractError, 'not one of'):
                oa.smoke_n_t(path)
            oc.atomic_json(path, dict(format='other', N_t=oc.N_T), exist_ok=True)
            with self.assertRaisesRegex(oc.ContractError, 'not a smoke result'):
                oa.smoke_n_t(path)
            write_smoke(oc.N_T, 'smoke-2')
            with self.assertRaisesRegex(oc.ContractError, '2 found'):
                oa.smoke_n_t()

    def test_clock_caps_a_proposal_per_fold(self):
        clock = oa._Clock(100)
        self.assertEqual(clock.left('r1p1', 900), 100)
        clock.add('r1p1', 60)
        self.assertEqual(clock.left('r1p1', 900), 40)
        self.assertEqual(clock.left('r1p2', 30), 30)
        clock.add('r1p1', 40)
        with self.assertRaisesRegex(oa.ProposalError, 'r1p1: over 100 s'):
            clock.left('r1p1', 900)

    def test_limit_interrupts_a_long_query(self):
        con = small_duckdb()
        self.addCleanup(con.close)
        with oa._Limit(con, 0.2) as limit:
            try:
                con.execute('SELECT count(*) FROM range(10000000000) a').fetchall()
                error = None
            except duckdb.Error as exc:
                error = limit.error(exc)
        self.assertIsInstance(error, oa.ProposalError)
        self.assertIn('timeout after 0.2 s', str(error))

    def test_feedback_masks_names_and_keeps_coarse_numbers(self):
        record = dict(id='r1p1', name='src', kind='source', level='pair', status='valid', idea='otto clicks trick',
                      sql='SELECT 1', seconds='2^3–2^4', rows='2^10–2^11', columns=[dict(name='ag_src_src_rank')],
                      coverage=dict(candidates_per_session='2^4–2^5', new_item_share='2^-2–2^-1',
                                    sessions_covered='2^-1–2^0'), recall=dict(view='0.12', cart='0.05', order='0.03'),
                      gain=dict(view='0.004', cart='0.001', order='0.000'))
        text = oa.format_feedback([record])
        self.assertNotIn('otto', text.lower())
        self.assertIn('<name> view trick', text)
        self.assertIn('recall of its candidates: view 0.12, cart 0.05, order 0.03', text)
        self.assertIn('gain of the candidate ceiling: view 0.004', text)

    def test_cli_refuses_without_isolated_mode(self):
        result = subprocess.run([sys.executable, str(REPO/'scripts'/'otto_agent.py'), 'export'], cwd=REPO,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        line = json.loads(result.stdout.strip())
        self.assertFalse(line['ok'])
        self.assertIn('-I', line['error'])
        result = subprocess.run([sys.executable, '-I', str(REPO/'scripts'/'otto_agent.py'), 'nonsense'], cwd=REPO,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('usage', json.loads(result.stdout.strip())['error'])


# =============================================================================== the probe world

class ProbeWorldTest(unittest.TestCase):
    """One synthetic world: load, collections, calibration, probe, a run with a fake agent, freeze,
    a sidecar and the leakcheck. Expensive steps run once in setUpClass."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=5)
        cls.base = cls.world.base
        cls.data = oa.ProbeData(cls.world.probe)
        cls.ask = FakeAsk()
        cls.outcome = oa.run_loop(cls.world.probe, name='run-t1', rounds=4, ask=cls.ask)
        cls.records = {r['id']: r for r in map(json.loads, (Path(cls.outcome['path'])/'log.jsonl').read_text().splitlines())}

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    # ---------------------------------------------------------------- sandbox

    def sandbox(self, keys=True):
        return oa.sandbox(self.data.spec, self.data.keys_path if keys else None, threads=THREADS)

    def test_sandbox_refuses_files_settings_and_extensions(self):
        con = self.sandbox()
        labels = self.world.probe_collection/oc.LABELS_FILE
        outside = Path(tempfile.mkdtemp()).resolve()
        try:
            self.assertEqual(con.execute('SELECT count(*) FROM cand').fetchone()[0], self.data.record['rows'])
            for sql in (f"SELECT * FROM read_parquet('{labels}')",
                        f"SELECT * FROM read_parquet('{self.world.probe_collection/oc.FRAME_FILE}')",
                        f"SELECT * FROM read_csv('{oc.config_path('base')}')",
                        f"COPY (SELECT 1) TO '{outside/'x.csv'}'",
                        f"COPY (SELECT 1) TO '{self.data.path/'x.csv'}'",
                        f"ATTACH '{outside/'x.duckdb'}' AS other",
                        'INSTALL httpfs', 'LOAD httpfs', 'SET threads=8', 'SET enable_external_access=true',
                        "SET allowed_directories=['/']", 'RESET lock_configuration'):
                with self.subTest(sql=sql):
                    with self.assertRaises(duckdb.Error):
                        con.execute(sql).fetchall()
            self.assertFalse((outside/'x.csv').exists())
            self.assertFalse((self.data.path/'x.csv').exists())
        finally:
            oa.close(con)

    def test_sandbox_refuses_traversal_neighbours_sealed_and_later_weeks(self):
        con = self.sandbox()
        hist_dir = Path(self.data.spec['directories']['hist'][-1])
        neighbour = Path(str(hist_dir) + '0')                     # d=-15 allowed, d=-150 not
        neighbour.mkdir()
        shutil.copyfile(sorted(hist_dir.glob('*.parquet'))[0], neighbour/'x.parquet')
        sealed = self.world.val/'sealed'
        sealed.mkdir(exist_ok=True)
        shutil.copyfile(self.world.val/oc.LABELS_FILE, sealed/'x.parquet')
        later = hist_dir.with_name(f"{hist_dir.name.split('=')[0]}={oc.week_days(4)[0]}")   # a W4 partition
        self.assertTrue(any(later.glob('*.parquet')))
        try:
            for path in (f'{hist_dir}/../../{oc.CONFIG_PREFIX}-base.json', f'{hist_dir}/../{neighbour.name}/x.parquet',
                         neighbour/'x.parquet', f'{neighbour}/*.parquet', sealed/'x.parquet', f'{later}/*.parquet',
                         f'{self.world.probe_collection}/{oc.PREFIX_DIR}/../{oc.LABELS_FILE}'):
                with self.subTest(path=str(path)):
                    with self.assertRaises(duckdb.Error):
                        con.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchall()
            self.assertGreater(con.execute(f"SELECT count(*) FROM read_parquet('{hist_dir}/*.parquet')").fetchone()[0], 0)
            for sql in ("SELECT $$x$$ AS s", 'SELECT count(*) FROM pg_catalog.pg_views'):
                with self.subTest(sql=sql):                       # check_sql refuses both before the sandbox
                    with self.assertRaises(oa.ProposalError):
                        oa.check_sql(f'SELECT session, item, 1 AS ag_x FROM cand WHERE EXISTS ({sql})', 'feature',
                                     'pair', [])
        finally:
            oa.close(con)
            shutil.rmtree(neighbour)
            shutil.rmtree(sealed)

    def test_execute_runs_one_create_only(self):
        con = self.sandbox()
        try:
            with self.assertRaisesRegex(oa.ProposalError, 'one SELECT'):
                oa.execute(con, 'feature', 'item', "SELECT 1 AS item; COPY cand TO 'x.csv'", 0, 1, 10)
            with self.assertRaisesRegex(ValueError, 'locked sandbox'):
                oa.execute(duckdb.connect(), 'feature', 'item', 'SELECT 1 AS item', 0, 1, 10)
        finally:
            oa.close(con)

    def test_probe_labels_are_outside_the_sandbox_and_only_for_the_probe(self):
        labels = oa.probe_labels(self.world.probe_collection)
        self.assertTrue(set(labels.session) <= set(self.data.pool))
        self.assertNotIn(str(self.world.probe_collection/oc.LABELS_FILE), json.dumps(self.data.spec))
        allowed = [*self.data.spec['directories']['hist'], *self.data.spec['directories']['sess']]
        self.assertFalse(any(Path(d) == self.world.probe_collection for d in allowed))
        with self.assertRaisesRegex(oc.ContractError, 'only the probe labels'):
            oa.probe_labels(self.world.val)
        for role, fold in (('holdout', 4), ('kaggle', 5)):
            with mock.patch.object(oc, 'read_collection', return_value=dict(role=role, fold=fold)):
                with self.subTest(role=role):
                    with self.assertRaisesRegex(oc.ContractError, 'only the probe labels'):
                        oa.probe_labels(self.world.probe_collection)

    def test_probe_pool_outside_the_dev_population(self):
        population = set(oc.read_population(self.world.val))
        self.assertFalse(population & set(self.data.pool))
        self.assertEqual(len(self.data.pool), POOL)
        original = (self.world.val/oc.POPULATION_FILE).read_bytes()
        try:
            (self.world.val/oc.POPULATION_FILE).unlink()
            oc.write_population(self.world.val, sorted(population | {self.data.pool[0]}), rule='tampered')
            with self.assertRaisesRegex(oc.ContractError, 'overlaps'):
                oa.prepare_probe('probe-bad', threads=THREADS, memory=MEMORY)
        finally:
            (self.world.val/oc.POPULATION_FILE).write_bytes(original)

    def test_calibration_and_stats(self):
        cal = oa.read_calibration()
        self.assertEqual(cal['t_tb'], 1200)
        self.assertIsNone(cal['limitation'])
        self.assertEqual(set(cal['pairs']), {'5', '20'})
        self.assertGreater(cal['pairs']['20'], cal['pairs']['5'])
        self.assertTrue((oc.ROOT/'docs'/'otto-run'/'calibration-cal.json').exists())
        stats = self.data.stats
        self.assertEqual(set(stats['prefixes']), set(od.NEUTRAL_EVENTS))
        self.assertEqual(stats['events_squared_per_session'], cal['n2'])
        self.assertIsNone(oa.NAMES_IN_PROMPT.search(json.dumps(stats)))
        self.assertEqual(self.data.t_tb, 1200)

    # ---------------------------------------------------------------- limits and tables

    def test_source_limits(self):
        con = self.sandbox()
        try:
            with self.assertRaisesRegex(oa.ProposalError, 'at most 40 rows per session'):
                oa.execute(con, 'source', 'pair', WIDE_SRC, 0, 1, 30, known=self.data.known)
            with self.assertRaisesRegex(oa.ProposalError, 'not items known'):
                oa.execute(con, 'source', 'pair', GHOST_SRC, 0, 1, 30, known=self.data.known)
            with self.assertRaisesRegex(oa.ProposalError, 'outside sessions'):
                oa.execute(con, 'source', 'pair', 'SELECT CAST(-1 AS BIGINT) AS session, CAST(1 AS BIGINT) AS item, '
                                                  '1.0 AS score', 0, 1, 30)
            with self.assertRaisesRegex(oa.ProposalError, 'exactly one value column, score'):
                oa.execute(con, 'source', 'pair', 'SELECT session, item, 1.0 AS ag_x FROM cand', 0, 1, 30)
            with self.assertRaisesRegex(oa.ProposalError, 'FLOAT range'):
                oa.execute(con, 'source', 'pair', HUGE_SRC, 0, 1, 30, known=self.data.known)
            with self.assertRaisesRegex(oa.ProposalError, 'duplicate keys'):
                oa.execute(con, 'source', 'pair', 'SELECT session, item, 1.0 AS score FROM cand UNION ALL '
                                                  'SELECT session, item, 2.0 FROM cand', 0, 1, 30)
            result = oa.execute(con, 'source', 'pair', POP_SRC, self.data.spec['start'], self.data.spec['end'], 30,
                                known=self.data.known)[0]
            first = result[result.session == result.session.iloc[0]].sort_values('rank')
            self.assertTrue((np.diff(first.score.to_numpy()) <= 0).all())
        finally:
            oa.close(con)

    def evaluate(self, proposals, sources=(), freeze=False):
        """Records of proposals evaluated one by one on a fresh run state in phase S (accepted ones join);
        ``freeze`` moves the state to phase F on the candidates of ``sources`` first."""
        state = oa.RunState(self.data, Path(tempfile.mkdtemp(dir=oc.output_dir('run'))), self.base)
        scorer = oa.Scorer(oa.probe_labels(self.world.probe_collection))
        state.sources.extend(sources)
        records = {}
        try:
            if freeze:
                state.freeze_candidates()
            for index, (name, kind, level, sql) in enumerate(proposals, 1):
                item = dict(id=f'r1p{index}', round=1, index=index, **proposal(name, kind, level, sql))
                record, payload = oa.evaluate_proposal(self.data, state, item, scorer)
                if record['status'] == 'valid':
                    oa.accept(state, record, payload)
                records[name] = record
        finally:
            scorer.close()
            state.close()
            shutil.rmtree(state.workdir)
        return records

    def test_source_is_judged_on_ba_against_b_and_earlier_sources(self):
        # the history source has ~600 rows here; on the probe MIN_SOURCE_SESSIONS keeps it above 1000
        with mock.patch.object(oa, 'MIN_SPEARMAN_ROWS', 100):
            records = self.evaluate([('covis', 'table', 'item_pair', COVIS), ('history', 'source', 'pair', HIST_SRC),
                                     ('pop7', 'source', 'pair', POP7_SRC), ('few', 'source', 'pair', FEW_SRC)])
        self.assertEqual(records['history']['status'], 'invalid')
        self.assertIn('|Spearman| with h_rank', records['history']['error'])
        self.assertIn('|Spearman| with i_h7_all', records['pop7']['error'])
        self.assertIn(f'fewer than {MIN_SOURCE} probe sessions', records['few']['error'])
        for name in ('history', 'pop7', 'few'):
            self.assertNotIn('recall', records[name])
            self.assertNotIn('gain', records[name])
        self.assertEqual([c['name'] for c in records['pop7']['columns']], list(oa.source_columns('pop7')))
        self.assertEqual(self.records['r1p3']['status'], 'valid')         # the run's popular source differs from B
        dummy = pd.DataFrame({'session': [1], 'aid': [1], 'score': [1.0], 'rank': [1]})
        full = self.evaluate([('pop', 'source', 'pair', POP_SRC)],
                             sources=[(f's{i}', dummy) for i in range(oa.MAX_SOURCES)])
        self.assertIn(f'{oa.MAX_SOURCES} sources are already accepted', full['pop']['error'])

    def test_a_session_oracle_by_literals_fails_batch_invariance_and_coverage(self):
        """Selecting sessions by id without a literal comparison: a VALUES join, list_contains; padding every
        session with a B pair while the new items go to a few sessions only."""
        targets = [int(s) for s in self.data.pool[:2*MIN_SOURCE]]
        values = ', '.join(f'({s})' for s in targets)
        popular = ('(SELECT item, count(*) AS n FROM hist GROUP BY item ORDER BY n DESC, item LIMIT 5 OFFSET 40)')
        joined = (f'SELECT s.session AS session, p.item AS item, CAST(p.n AS DOUBLE) AS score FROM sessions s '
                  f'JOIN (VALUES {values}) v(x) ON v.x = s.session CROSS JOIN {popular} p')
        contains = (f'SELECT session, item, CAST(list_contains([{", ".join(map(str, targets))}], session) AS DOUBLE) '
                    'AS ag_marked FROM cand')
        few = ', '.join(f'({s})' for s in targets[:MIN_SOURCE//5])
        padded = (f'SELECT session, min(item) AS item, 0.5 AS score FROM cand GROUP BY session UNION ALL '
                  f'SELECT s.session, p.item, CAST(p.n AS DOUBLE) FROM sessions s JOIN (VALUES {few}) v(x) '
                  f'ON v.x = s.session CROSS JOIN {popular} p WHERE NOT EXISTS (SELECT 1 FROM cand c '
                  'WHERE c.session = s.session AND c.item = p.item)')
        for sql in (joined, contains, padded):
            self.assertEqual(oa.check_sql(sql, 'source', 'pair'), [])         # no session literal for the regex
        records = self.evaluate([('joined', 'source', 'pair', joined), ('padded', 'source', 'pair', padded)])
        self.assertEqual(records['joined']['status'], 'invalid')
        self.assertIn('batch invariance', records['joined']['error'])
        self.assertNotIn('fewer than', records['joined']['error'])
        self.assertEqual(records['padded']['status'], 'invalid')
        self.assertIn(f'brings new candidates to fewer than {MIN_SOURCE} probe sessions', records['padded']['error'])
        feature = self.evaluate([('marked', 'feature', 'pair', contains)], freeze=True)['marked']
        self.assertEqual(feature['status'], 'invalid')
        self.assertIn('batch invariance', feature['error'])

    def test_a_table_reads_hist_only(self):
        carrier = ('SELECT min(ts) AS item, session AS item2, CAST(count(*) AS DOUBLE) AS tv_n FROM sess '
                   'GROUP BY session')
        with self.assertRaisesRegex(oa.ProposalError, 'a table must not use sess: it reads hist only'):
            oa.check_sql(carrier, 'table', 'item_pair')
        record = self.evaluate([('carrier', 'table', 'item_pair', carrier)])['carrier']
        self.assertEqual(record['status'], 'invalid')
        self.assertIn('it reads hist only', record['error'])

    def test_the_scored_pass_runs_on_permuted_ids(self):
        """A VALUES join on three real ids: the scored pass sees permuted ids, so the rows that reach
        coverage, the checks and the Scorer belong to other sessions than the literals."""
        pool = set(int(s) for s in self.data.pool)
        permuted = oa.PermutedSess(self.data.spec)                       # the same seed: the map of the run
        try:
            backward = permuted.backward
        finally:
            permuted.close()
        # literals that are pool sessions and whose preimage is another pool session: the attack does select rows
        targets = [int(x) for x in sorted(pool) if int(backward[x]) in pool and int(backward[x]) != x][:3]
        hit = {int(backward[x]) for x in targets}
        self.assertEqual(len(targets), 3)
        values = ', '.join(f'({s})' for s in targets)
        sql = (f'SELECT s.session AS session, p.item AS item, CAST(p.n AS DOUBLE) AS score FROM sessions s '
               f'JOIN (VALUES {values}) v(x) ON v.x = s.session CROSS JOIN (SELECT item, count(*) AS n FROM hist '
               'GROUP BY item ORDER BY n DESC, item LIMIT 5) p')
        seen, real = [], oa.RunState.union

        def union(state, *extra):
            seen.extend(frame for _, frame in extra)
            return real(state, *extra)
        with mock.patch.object(oa.RunState, 'union', union):
            record = self.evaluate([('three', 'source', 'pair', sql)])['three']
        self.assertEqual(record['status'], 'invalid')
        self.assertIn('batch invariance', record['error'])               # on the cohort the halves see real ids
        [frame] = seen
        got = set(frame['session'].astype(int))
        self.assertEqual(got, hit)                                       # the preimages, not the literals
        self.assertNotEqual(got, set(targets))
        self.assertEqual(len(frame), 5*len(got))

    def test_permuted_sess_is_a_bijection_off_order_and_residues(self):
        permuted = oa.PermutedSess(self.data.spec)
        try:
            forward = permuted.forward
            self.assertEqual(sorted(forward.index), sorted(forward.to_numpy()))
            self.assertLess((forward.index == forward.to_numpy()).mean(), 0.1)
            self.assertLess((forward.index % 2 == forward.to_numpy() % 2).mean(), 0.8)
            self.assertFalse((np.diff(forward.to_numpy()) > 0).all())
            con = oa.sandbox(permuted.spec, None, threads=THREADS)
            try:
                got = con.execute('SELECT session, item, ts, event, seq FROM sess').df()
            finally:
                oa.close(con)
            con = oa.sandbox(self.data.spec, None, threads=THREADS)
            try:
                real = con.execute('SELECT session, item, ts, event, seq FROM sess').df()
            finally:
                oa.close(con)
            self.assertFalse(got['session'].equals(real['session']))
            order = ['session', 'seq', 'ts', 'item']
            back = permuted.back(got).sort_values(order).reset_index(drop=True)
            pd.testing.assert_frame_equal(back, real.sort_values(order).reset_index(drop=True), check_dtype=False)
            with self.assertRaisesRegex(oc.ContractError, 'outside the permuted sess'):
                permuted.back(pd.DataFrame({'session': [10**12]}))
        finally:
            permuted.close()
        self.assertFalse(permuted.dir.exists())

    def test_calibration_limitation_when_the_join_is_slow(self):
        with mock.patch.object(oa, '_timed', return_value=(10, 1900.0, False)):
            record = oa.calibrate('cal-slow', threads=THREADS)
        try:
            self.assertEqual(record['t_20'], 1900.0)
            self.assertEqual(record['t_tb'], 1800)
            self.assertIn('t_20 above', record['limitation'])
            self.assertEqual(oa.read_calibration(record['path'])['t_tb'], 1800)
        finally:
            shutil.rmtree(Path(record['path']).parent)
            (oc.ROOT/'docs'/'otto-run'/'calibration-cal-slow.json').unlink()

    def test_table_limits_leave_no_cache(self):
        wide = dict(id='r9p1', name='wide', kind='table', level='item_pair', sql=WIDE_TABLE)
        with self.assertRaisesRegex(oa.ProposalError, 'at most 50 rows per item'):
            oa.compute_table(self.data.spec, wide, {}, timeout_s=60, threads=THREADS, fingerprint=self.data.fingerprint)
        self.assertFalse(any(p.name.startswith('r9p1') or '.partial' in p.name
                             for p in oc.output_dir('tables').rglob('*')))
        names = dict(id='r9p2', name='bad', kind='table', level='item_pair',
                     sql='SELECT item, item AS item2, 1.0 AS ag_x FROM hist GROUP BY item')
        with self.assertRaisesRegex(oa.ProposalError, 'tv_'):
            oa.compute_table(self.data.spec, names, {}, timeout_s=60, threads=THREADS, fingerprint=self.data.fingerprint)

    def test_table_cache_is_reused_and_keyed_by_data(self):
        table = dict(id='r1p1', name='covis', kind='table', level='item_pair', sql=COVIS)
        entry = oa.compute_table(self.data.spec, table, {}, timeout_s=60, threads=THREADS,
                                 fingerprint=self.data.fingerprint)
        self.assertTrue(entry['cached'])                       # the run computed it already
        other = oa.compute_table(self.data.spec, table, {}, timeout_s=60, threads=THREADS, fingerprint='f'*64)
        self.assertFalse(other['cached'])
        self.assertNotEqual(other['key'], entry['key'])
        self.assertEqual(other['sha256'], entry['sha256'])

    def test_tables_run_in_one_thread_and_the_count_keys_the_cache(self):
        # lc-F3: a parallel DOUBLE sum flipped a top-50 cut at ties; tables are computed single-threaded
        self.assertEqual(oa.TABLE_THREADS, 1)
        key = oa.table_key(3, 'r1p1', COVIS, 'f'*64, [])
        with mock.patch.object(oa, 'TABLE_THREADS', 4):
            self.assertNotEqual(oa.table_key(3, 'r1p1', COVIS, 'f'*64, []), key)
        with mock.patch.object(oa, 'TABLE_MEMORY', '7GB'):
            self.assertNotEqual(oa.table_key(3, 'r1p1', COVIS, 'f'*64, []), key)
        seen = []
        real = oa.sandbox

        def spy(*args, **kwargs):
            seen.append(kwargs.get('threads'))
            return real(*args, **kwargs)
        table = dict(id='r1p9', name='covis9', kind='table', level='item_pair', sql=COVIS)
        with mock.patch.object(oa, 'sandbox', spy):
            entry = oa.compute_table(self.data.spec, table, {}, timeout_s=60, threads=THREADS, fingerprint='e'*64)
        try:
            self.assertEqual(seen, [1])
            record = oa.read_table(Path(entry['path']).parent)
            self.assertEqual((record['threads'], record['memory']), (1, oa.TABLE_MEMORY))
        finally:
            shutil.rmtree(Path(entry['path']).parent)

    def test_leakcheck_cli_reports_passed_without_clashing_with_ok(self):
        fake = dict(path='/x/report.json', ok=False, fold=3)
        out = io.StringIO()
        with mock.patch.object(oa, 'leakcheck', return_value=fake), mock.patch.object(oc, 'isolated'), \
                contextlib.redirect_stdout(out):
            code = oa.main(['leakcheck', '--fold', '3'])
        line = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual((line['ok'], line['passed'], line['command']), (True, False, 'leakcheck'))

    def test_rejected_table_drops_its_dependents(self):
        agent_set = make_set(self.base, [
            dict(id='r1p1', round=1, index=1, name='wide', kind='table', level='item_pair', sql=WIDE_TABLE,
                 columns=['tv_one']),
            dict(id='r1p2', round=1, index=2, name='uses_wide', kind='source', level='pair',
                 sql=COVIS_SRC.replace('tb_covis', 'tb_wide').replace('tv_cnt', 'tv_one')),
            dict(id='r3p1', round=3, index=1, name='plain', kind='feature', level='item', sql=USERS14,
                 columns=['ag_item_users14'])])
        self.assertEqual(oa.dependents(agent_set, 'wide'), ['r1p2'])
        with self.assertRaisesRegex(oa.ProposalError, r'r1p1: .*50 rows per item; dependent proposals fall with it: r1p2'):
            oa.set_tables(self.data.spec, agent_set, timeout_s=60, threads=THREADS)
        # in the loop a proposal on a rejected table is invalid: tb_wide was never accepted
        self.assertEqual(self.records['r2p1']['status'], 'invalid')
        self.assertEqual(self.records['r2p5']['status'], 'invalid')
        self.assertIn('tb_wide is not a table accepted earlier', self.records['r2p5']['error'])

    # ---------------------------------------------------------------- the run

    def test_run_phases_and_statuses(self):
        status = {pid: r['status'] for pid, r in self.records.items()}
        self.assertEqual(status, {
            'r1p1': 'valid', 'r1p2': 'valid', 'r1p3': 'valid', 'r1p4': 'invalid', 'r1p5': 'invalid',
            'r2p1': 'invalid', 'r2p2': 'invalid', 'r2p3': 'invalid', 'r2p4': 'invalid', 'r2p5': 'invalid',
            'r3p1': 'valid', 'r3p2': 'valid', 'r3p3': 'valid', 'r3p4': 'invalid', 'r3p5': 'invalid',
            'r4p1': 'invalid'})
        self.assertIn('phase S accepts only table and source', self.records['r1p5']['error'])
        self.assertIn('phase F accepts only table and feature', self.records['r3p5']['error'])
        self.assertIn('forbidden', self.records['r1p4']['error'])
        self.assertIn('not items known', self.records['r2p2']['error'])
        self.assertIn('same candidates', self.records['r2p3']['error'])
        self.assertIn('40 rows per session', self.records['r2p4']['error'])
        self.assertIn('batch invariance', self.records['r3p4']['error'])
        self.assertIn('|Spearman| with i_h7_all', self.records['r4p1']['error'])
        self.assertEqual(self.outcome['calls'], 5)
        self.assertEqual(self.outcome['cost_usd'], 5.5)
        self.assertEqual(self.outcome['call_log'][0]['status'], 'failed')
        self.assertEqual(self.outcome['sources'], ['covis_src', 'pop_src'])
        self.assertEqual(self.outcome['columns'], ['ag_src_covis_src_rank', 'ag_src_covis_src_score', 'ag_src_pop_src_rank',
                                               'ag_src_pop_src_score', 'ag_covis_max', 'ag_item_users14', 'ag_ratio'])
        self.assertEqual(self.outcome['status'], 'completed')
        self.assertEqual(self.ask.calls, 5)

    def test_feedback_is_coarse(self):
        source = self.records['r1p2']
        self.assertRegex(source['recall']['view'], r'^[01]\.\d\d$')
        self.assertRegex(source['gain']['order'], r'^-?[01]\.\d{3}$')
        self.assertTrue(all(oa._is_bucket(v) for v in source['coverage'].values()))
        feature = self.records['r3p1']['columns'][0]
        self.assertEqual(set(feature['recall']), set(od.NEUTRAL_EVENTS))
        third = (Path(self.outcome['path'])/'prompt-r3.txt').read_text()
        self.assertIn('The candidates are frozen with the sources covis_src, pop_src', third)
        self.assertIn('Best single base column', third)
        self.assertIn('recall of its candidates: view', third)
        for number in range(1, 5):
            prompt = (Path(self.outcome['path'])/f'prompt-r{number}.txt').read_text()
            self.assertIsNone(oa.NAMES_IN_PROMPT.search(prompt))
            self.assertIn(oa.WARNING, ' '.join(prompt.split()))
            self.assertNotIn(str(self.world.root), prompt)

    def test_candidates_freeze_after_phase_s(self):
        run_dir = Path(self.outcome['path'])
        frame = oc.read_parquet(run_dir/'candidates.parquet')
        b = self.data.keys
        merged = b.merge(frame, on=['session', 'aid'], how='left', indicator=True)
        self.assertTrue((merged['_merge'] == 'both').all())             # B whole
        self.assertTrue(frame.groupby('session').size().max() <= oa.BA_MAX)
        sources = [(name, oc.read_parquet(run_dir/'values'/f'{pid}.parquet'))
                   for name, pid in (('covis_src', 'r1p2'), ('pop_src', 'r1p3'))]
        again = oa.ba_union(b, sources)
        pd.testing.assert_frame_equal(frame.reset_index(drop=True), again.reset_index(drop=True), check_dtype=False)
        self.assertGreater(int((~frame['in_b']).sum()), 0)
        self.assertEqual(self.outcome['candidates']['sources'], ['covis_src', 'pop_src'])

    def test_one_run_only(self):
        with self.assertRaisesRegex(ValueError, 'A run exists'):
            oa.run_loop(self.world.probe, name='run-t2', rounds=1, ask=FakeAsk())

    # ---------------------------------------------------------------- freeze, sidecar, leakcheck

    def frozen(self):
        if not oc.config_path('set').exists():
            oa.freeze(self.outcome['path'])
        return oa.read_set(base=self.base)

    def test_freeze_writes_the_set_and_the_journal(self):
        agent_set = self.frozen()
        self.assertEqual([p['id'] for p in agent_set['proposals']],
                         ['r1p1', 'r1p2', 'r1p3', 'r3p1', 'r3p2', 'r3p3'])
        self.assertEqual(agent_set['tables'], ['covis'])
        self.assertEqual(agent_set['columns'], self.outcome['columns'])
        self.assertEqual(agent_set['proposals'][1]['depends'], ['covis'])
        self.assertEqual(agent_set['t_tb'], 1200)
        journal = oc.ROOT/'docs'/'otto-run'/'run-t1'
        self.assertTrue((journal/'log.jsonl').exists() and (journal/'prompt-r1.txt').exists())
        again = oa.freeze(self.outcome['path'])                       # same content: accepted
        self.assertEqual(again['digest'], agent_set['digest'])
        broken = dict(agent_set, proposals=[dict(agent_set['proposals'][1], depends=[])] + agent_set['proposals'][2:])
        with self.assertRaises(ValueError):
            oa.check_set(broken)

    def test_sidecar_writes_the_ba_frame(self):
        agent_set = self.frozen()
        with self.assertRaisesRegex(oc.ContractError, 'prereg'):
            oa.sidecar(self.world.val, name='gated', threads=THREADS, memory=MEMORY)
        result = oa.sidecar(self.world.val, name='side', threads=THREADS, memory=MEMORY, batch=25,
                            agent_set=agent_set)
        root = oc.output_dir('sidecars', self.world.val.name)
        files = sorted(str(p) for p in root.rglob('*.parquet'))
        self.assertEqual(len(files), -(-result['sessions']//25))
        con = small_duckdb()
        self.addCleanup(con.close)
        frame = con.sql(f'SELECT * FROM read_parquet({files})').df()
        b = oc.read_parquet(self.world.val/oc.FRAME_FILE)
        names = oc.base_feature_names(self.base)
        self.assertEqual(list(frame.columns), ['session', 'aid', *[c for c in b.columns if c not in ('session', 'aid')],
                                               *agent_set['columns']])
        self.assertFalse(frame.duplicated(['session', 'aid']).any())
        merged = b.merge(frame, on=['session', 'aid'], how='left', suffixes=('', '_ba'), indicator=True)
        self.assertTrue((merged['_merge'] == 'both').all())
        for name in names:
            pd.testing.assert_series_equal(merged[name].astype('float64'), merged[f'{name}_ba'].astype('float64'),
                                           check_names=False)
        self.assertGreater(len(frame), len(b))
        self.assertEqual(set(frame.session), set(b.session))
        types = dict(con.sql(f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM "
                                f"read_parquet({files}))").fetchall())
        self.assertEqual(types['h_rank'], 'USMALLINT')
        self.assertEqual(types['ag_ratio'], 'FLOAT')
        report = oc.read_json(Path(result['path'])/oa.SIDECAR_REPORT)
        self.assertEqual(report['set_digest'], agent_set['digest'])
        self.assertEqual(report['manifest_sha256'], oc.sha256_file(self.world.val/oc.MANIFEST_FILE))
        self.assertTrue(set(oc.SIDECAR_FIELDS) <= set(report))
        self.assertEqual((report['factor'], report['deviation'], report['resumed']), (1, None, 0))
        self.assertEqual(report['table_timeout'], 3600.0)
        self.assertEqual(sorted(p.name for p in oc.output_dir('sidecars').iterdir()),
                         [self.world.val.name])                                 # no lock, no partial left
        parts = oc.sidecar_parts(self.world.val, agent_set['digest'])                 # otto_model's reader
        self.assertEqual(parts['sessions'], sorted(set(b.session)))
        self.assertEqual(parts['agent_columns'], agent_set['columns'])
        self.assertEqual(report['rows'], sum(v['rows'] for v in report['parts'].values()))
        ctx = SimpleNamespace(set_digest=agent_set['digest'], _ba={}, agent_columns=agent_set['columns'],
                              features=oc.base_feature_names(self.base))
        self.assertEqual(om.ba_frame_paths(ctx, self.world.val), parts['parts'])
        with self.assertRaisesRegex(oc.ContractError, 'already has a sidecar'):
            oa.sidecar(self.world.val, name='side-2', threads=THREADS, memory=MEMORY, agent_set=agent_set)

    def test_leakcheck_passes_on_honest_columns(self):
        agent_set = self.frozen()
        result = oa.leakcheck(3, name='leak-ok', agent_set=agent_set, threads=THREADS, memory=MEMORY, batch=20)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['fold'], 3)
        self.assertFalse(result['degenerate'])
        self.assertEqual(result['batch_check']['batches'], 4)
        self.assertEqual(result['history_check']['sessions'], POPULATION)
        self.assertTrue(result['prefix_check']['ok'])
        self.assertEqual(result['prefix_check']['rows'][0], result['prefix_check']['rows'][1])
        path = Path(result['path'])
        self.assertTrue(path.is_relative_to(oc.output_dir('leakcheck').resolve()))
        self.assertEqual(oc.read_json(path)['ok'], True)
        self.assertTrue((oc.ROOT/'docs'/'otto-run'/'leak-ok.json').exists())

    def test_audit_is_recorded_before_the_commit_and_gates_the_sidecar(self):
        agent_set = self.frozen()
        report = oc.ROOT/'docs'/'otto-run'/'audit-t1.json'
        body = dict(format=oa.AUDIT_FORMAT, set_digest=agent_set['digest'], verdict='clean',
                    recognizability={p['id']: 'common' for p in agent_set['proposals']},
                    points={k: 'checked' for k in oa.AUDIT_POINTS})
        outside = oc.output_dir('run')/'audit.json'
        oc.atomic_json(outside, body, exist_ok=True)
        with self.assertRaisesRegex(oc.ContractError, 'docs/otto-run'):
            oa.audit(outside)
        oc.atomic_json(report, dict(body, points={'hidden_encoding': 'x'}), exist_ok=True)
        with self.assertRaisesRegex(oc.ContractError, 'answers'):
            oa.audit(report)
        oc.atomic_json(report, dict(body, set_digest='0'*64), exist_ok=True)
        with self.assertRaisesRegex(oc.ContractError, 'another set'):
            oa.audit(report)
        oc.atomic_json(report, body, exist_ok=True)
        audited = oa.audit(report)
        self.assertEqual(audited['audit']['verdict'], 'clean')
        self.assertEqual(audited['audit']['sha256'], oc.sha256_file(report))
        self.assertEqual(audited['digest'], agent_set['digest'])                 # the digest ignores the audit
        self.assertEqual(oa.read_set(base=self.base)['audit'], audited['audit'])
        with self.assertRaisesRegex(oc.ContractError, 'already carries'):
            oa.audit(report)
        self.assertEqual(oa.freeze(self.outcome['path'])['audit'], audited['audit'])   # freeze again keeps it
        with mock.patch.object(oc, 'require_prereg'):
            self.assertEqual(oa.sidecar_gate()['digest'], agent_set['digest'])
            leak = dict(audited, audit=dict(audited['audit'], verdict='leak'))
            with mock.patch.object(oa, 'read_set', return_value=leak):
                with self.assertRaisesRegex(oc.ContractError, 'found a leak'):
                    oa.sidecar_gate()
            with mock.patch.object(oa, 'read_set', return_value=dict(audited, audit=None)):
                with self.assertRaisesRegex(oc.ContractError, 'no audit'):
                    oa.sidecar_gate()

    def test_readers_of_the_other_modules_accept_the_outputs(self):
        agent_set = self.frozen()
        self.assertEqual(agent_set['format'], oc.SET_FORMAT)
        self.assertEqual(oc.agent_columns(agent_set), agent_set['columns'])
        self.assertEqual(om.frozen_agent_columns({}, agent_set), agent_set['columns'])
        result = oa.leakcheck(3, name='leak-read', agent_set=agent_set, threads=THREADS, memory=MEMORY, batch=20)
        self.assertEqual(Path(result['path']), oc.leakcheck_path('leak-read'))
        population = oc.read_population(self.world.val)
        oc.read_leakcheck(result['path'], set_digest=agent_set['digest'], population_digest=oc.sessions_digest(population),
                          collection=self.world.val.name)
        ctx = SimpleNamespace(collection=lambda k: self.world.val, set_digest=agent_set['digest'], _ba={},
                              agent_columns=agent_set['columns'])
        self.assertEqual(om.leakcheck_record(ctx, result['path'])['problems'], [])
        self.assertTrue(result['prefix_check']['ok'], result['prefix_check'])

    def test_twin_of_b_features_matches_the_frame(self):
        frame = oc.read_parquet(self.world.val/oc.FRAME_FILE)
        twin = oa.BaseFeatures(oa.fold_spec(3, 'test', self.world.val), self.base,
                               oa.frame_columns(self.world.val/oc.FRAME_FILE), threads=THREADS, memory=MEMORY)
        try:
            computed = twin.frame(frame[['session', 'aid']])
        finally:
            twin.close()
        oa.check_b_twin(computed, frame, oc.base_feature_names(self.base))
        shifted = frame.copy()
        shifted['s_len'] = shifted['s_len'] + 1
        with self.assertRaisesRegex(oc.ContractError, 'B twin differs'):
            oa.check_b_twin(computed, shifted, oc.base_feature_names(self.base))


# =============================================================================== the loop: calls, retries, budget

class LoopTest(unittest.TestCase):
    """A failed run (both calls of round 1 fail), then its declared retry with 3 calls and a tight budget."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=6)

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    def test_retries_exhausted_then_a_retry_with_call_cap_and_budget(self):
        with self.assertRaisesRegex(ValueError, 'At most'):
            oa.run_loop(self.world.probe, name='run-x', max_calls=oa.MAX_CALLS+1, ask=FakeAsk())

        def silent(prompt, model):
            raise RuntimeError('claude gave no answer')
        with self.assertRaisesRegex(RuntimeError, 'the call and its retry both failed'):
            oa.run_loop(self.world.probe, name='run-a', rounds=2, ask=silent)
        failed = oc.read_json(oc.output_dir('run', 'run-a')/'run.json')
        self.assertEqual((failed['status'], failed['stop'], failed['calls'], failed['failed_round']),
                         ('failed', oa.RETRIES_EXHAUSTED, 2, 1))
        self.assertTrue((oc.ROOT/'docs'/'otto-run'/'run-a'/'run.json').exists())     # journal of a failed run

        seconds = {'r1p1': 4800.0, 'r1p2': 899.0, 'r1p3': 5.0}             # tables 4*T_tb, sources 900 s
        called = []

        def evaluate(data, state, item, scorer):
            called.append(item['id'])
            record, payload = oa.evaluate_proposal(data, state, item, scorer)
            if payload is not None and item['id'] in seconds:
                payload = dict(payload, seconds=seconds[item['id']])
            return record, payload
        ask = FakeAsk()
        outcome = oa.run_loop(self.world.probe, name='run-b', rounds=3, max_calls=3, ask=ask, evaluate=evaluate,
                              retry_of=oc.output_dir('run', 'run-a'), reason='the claude call failed twice')
        records = {r['id']: r for r in map(json.loads, (Path(outcome['path'])/'log.jsonl').read_text().splitlines())}
        self.assertEqual((outcome['status'], outcome['stop'], outcome['calls'], outcome['rounds_run']),
                         ('completed', 'max_calls', 3, 2))
        self.assertEqual(ask.calls, 3)
        self.assertEqual(outcome['retry_of'], str(oc.output_dir('run', 'run-a').resolve()))
        self.assertEqual(records['r1p2']['status'], 'valid')
        self.assertIn('recall', records['r1p2'])
        # valid, but over what is left: status budget without any label-derived number
        self.assertEqual(records['r1p3']['status'], 'budget')
        self.assertIn('over the probe budget', records['r1p3']['error'])
        self.assertNotIn('recall', records['r1p3'])
        self.assertNotIn('gain', records['r1p3'])
        # the table budget is used up: the next table is not run at all
        self.assertEqual(records['r2p1']['status'], 'budget')
        self.assertIn('was not run', records['r2p1']['error'])
        self.assertNotIn('r2p1', called)
        self.assertIn('r2p2', called)
        self.assertEqual(outcome['sources'], ['covis_src'])
        self.assertEqual(outcome['budget']['used']['table_seconds'], 4800.0)
        self.assertEqual(outcome['n_t'], N_T)
        self.assertEqual(outcome['smoke']['N_t'], N_T)
        third = (Path(outcome['path'])/'prompt-r2.txt').read_text()
        self.assertNotIn('recall of its candidates', third.split('r1p3 pop_src')[1].split('\nr1p4')[0])


# =============================================================================== sidecars

SIDE_SET = [dict(id='r1p1', round=1, index=1, name='covis', kind='table', level='item_pair', sql=COVIS,
                 columns=['tv_cnt']),
            dict(id='r1p2', round=1, index=2, name='covis_src', kind='source', level='pair', sql=COVIS_SRC),
            dict(id='r3p1', round=3, index=1, name='ratio', kind='feature', level='session', sql=RATIO,
                 columns=['ag_ratio'])]


class SidecarTest(unittest.TestCase):
    """Failure record, resume, lock, collection path, stale sets and the deviation of §5.7."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=11, probe=False, n_per_week=120, pool=40, population=40)
        cls.set = make_set(cls.world.base, SIDE_SET)

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    def setUp(self):
        shutil.rmtree(oc.output_dir('sidecars'), ignore_errors=True)
        self.root = oc.output_dir('sidecars')
        self.val = self.world.val
        self.sessions = sorted(set(oc.read_parquet(self.val/oc.FRAME_FILE, columns=['session']).session))

    def run_sidecar(self, name, fail_at=None, **kwargs):
        """oa.sidecar with batches of 20; ``fail_at``: the agent_block call (0-based) that fails. Returns calls."""
        real, calls = oa.agent_block, []

        def block(*args, **kw):
            calls.append(1)
            if fail_at is not None and len(calls) == fail_at+1:
                raise oa.ProposalError('r3p1: injected failure')
            return real(*args, **kw)
        with mock.patch.object(oa, 'agent_block', block):
            result = oa.sidecar(self.val, name=name, threads=THREADS, memory=MEMORY, batch=20,
                                agent_set=kwargs.pop('agent_set', self.set), **kwargs)
        return result, len(calls)

    def test_failure_is_recorded_and_the_same_command_resumes(self):
        batches = -(-len(self.sessions)//20)
        self.assertGreaterEqual(batches, 3)
        with self.assertRaisesRegex(oa.ProposalError, 'injected'):
            self.run_sidecar('s1', fail_at=1)
        failures = sorted(self.root.glob('.failed-*.json'))
        self.assertEqual([p.name for p in failures], [f'.failed-{self.val.name}-s1-1.json'])
        failure = oc.read_json(failures[0])
        self.assertEqual((failure['format'], failure['status'], failure['batch'], failure['proposal'],
                          failure['error_type'], failure['parts_done']),
                         (oa.SIDECAR_FAILURE_FORMAT, 'failed', 1, 'r3p1', 'ProposalError', 1))
        partial = self.root/f'.partial-{self.val.name}-s1'
        progress = oc.read_json(partial/oa.SIDECAR_PROGRESS)
        self.assertEqual(sorted(progress['parts']), ['part-00000.parquet'])
        first = oc.sha256_file(partial/'part-00000.parquet')
        self.assertIsNone(oc.sidecar_parts(self.val, self.set['digest']))           # BA не выполнена
        result, calls = self.run_sidecar('s1')
        self.assertEqual(calls, batches-1)                                          # the first part is kept
        self.assertEqual(result['resumed'], 1)
        final = Path(result['path'])
        self.assertFalse(partial.exists())
        self.assertFalse((final/oa.SIDECAR_PROGRESS).exists())
        self.assertEqual(oc.sha256_file(final/'part-00000.parquet'), first)
        parts = oc.sidecar_parts(self.val, self.set['digest'])
        self.assertEqual(parts['sessions'], self.sessions)
        self.assertEqual(len(parts['parts']), batches)
        # a set with other proposals meets a stale sidecar and refuses
        other = make_set(self.world.base, SIDE_SET[:2])
        with self.assertRaisesRegex(oc.ContractError, 'another agent set'):
            self.run_sidecar('s2', agent_set=other)

    def test_seconds_of_earlier_batches_count_against_the_4h(self):
        with self.assertRaises(oa.ProposalError):
            self.run_sidecar('s1', fail_at=1)
        path = self.root/f'.partial-{self.val.name}-s1'/oa.SIDECAR_PROGRESS
        progress = oc.read_json(path)
        oc.atomic_json(path, dict(progress, proposal_seconds={'r3p1': float(oa.PROPOSAL_CAP)}), exist_ok=True)
        with self.assertRaisesRegex(oa.ProposalError, f'r3p1: over {oa.PROPOSAL_CAP:g} s'):
            self.run_sidecar('s1')
        self.assertEqual(len(list(self.root.glob(f'.failed-{self.val.name}-s1-*.json'))), 2)

    def test_seconds_of_a_timed_out_proposal_reach_progress_and_the_failure_record(self):
        real, features = oa.execute, []

        def execute(con, kind, *args, **kw):
            if kind == 'feature':
                features.append(1)
                if len(features) == 2:                 # the second batch: r3p1 runs 0.3 s, then times out
                    time.sleep(0.3)
                    raise oa.ProposalError('the query ran past its limit')
            return real(con, kind, *args, **kw)
        with mock.patch.object(oa, 'execute', execute):
            with self.assertRaisesRegex(oa.ProposalError, 'r3p1: the query ran past its limit'):
                self.run_sidecar('slow')
        progress = oc.read_json(self.root/f'.partial-{self.val.name}-slow'/oa.SIDECAR_PROGRESS)
        self.assertEqual(len(progress['parts']), 1)
        self.assertGreaterEqual(progress['proposal_seconds']['r3p1'], 0.3)
        self.assertGreater(progress['proposal_seconds']['r1p2'], 0)
        [failed] = self.root.glob(f'.failed-{self.val.name}-slow-*.json')
        self.assertEqual(oc.read_json(failed)['proposal_seconds'], progress['proposal_seconds'])

    def test_abandoned_sidecars_under_other_names_count_against_the_4h(self):
        with self.assertRaises(oa.ProposalError):
            self.run_sidecar('a1', fail_at=1)
        partial = self.root/f'.partial-{self.val.name}-a1'
        progress = oc.read_json(partial/oa.SIDECAR_PROGRESS)
        self.assertGreater(progress['proposal_seconds']['r3p1'], 0)
        oc.atomic_json(partial/oa.SIDECAR_PROGRESS, dict(progress, proposal_seconds={'r3p1': float(oa.PROPOSAL_CAP)}),
                       exist_ok=True)
        with self.assertRaisesRegex(oa.ProposalError, f'r3p1: over {oa.PROPOSAL_CAP:g} s'):
            self.run_sidecar('a2')                         # a1 is abandoned, its seconds stay
        # the partial is gone: its last failure record still carries the seconds
        [failed] = self.root.glob(f'.failed-{self.val.name}-a1-*.json')
        oc.atomic_json(failed, dict(oc.read_json(failed), proposal_seconds={'r3p1': float(oa.PROPOSAL_CAP)}),
                       exist_ok=True)
        shutil.rmtree(partial)
        shutil.rmtree(self.root/f'.partial-{self.val.name}-a2')
        with self.assertRaisesRegex(oa.ProposalError, f'r3p1: over {oa.PROPOSAL_CAP:g} s'):
            self.run_sidecar('a3')
        # another set does not count
        self.assertEqual(oa._abandoned_seconds(self.root, self.val.name, 'a4', 'f'*64), {})
        self.assertEqual(oa._abandoned_seconds(self.root, 'other', 'a4', self.set['digest']), {})

    def test_sessions_of_the_holdout_come_from_the_gate_or_the_final_training_record(self):
        manifest = dict(role='holdout', fold=4)
        with self.assertRaisesRegex(oc.ContractError, 'belongs to the holdout'):
            oa.sidecar_sessions(self.val, dict(role='val', fold=3), 'auto')
        with self.assertRaisesRegex(oc.ContractError, 'no sidecar'):
            oa.sidecar_sessions(self.val, dict(role='probe', fold=3))
        with mock.patch.object(oc, 'holdout_population', return_value=dict(sessions=self.sessions[:5])):
            self.assertEqual(oa.sidecar_sessions(self.val, manifest), (self.sessions[:5], None))
        path = oc.output_dir('run')/'sessions.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')
        record = dict(sessions=self.sessions[:7], digest='d'*64, training_digest='t'*64)
        prereg = oc.output_dir('run')/'prereg.json'
        prereg.write_text(json.dumps(dict(N_t=321)))
        with mock.patch.object(oc, 'config_path', return_value=prereg):
            expected = oa._final_training_expected()
        self.assertEqual(expected, dict(prereg_sha256=oc.sha256_file(prereg), n_t=321))
        prereg.unlink()
        expected = dict(prereg_sha256='p'*64, n_t=77)
        with mock.patch.object(oa, '_final_training_expected', return_value=expected), \
                mock.patch.object(oc, 'final_training_record', return_value=(path, record)) as found:
            sessions, training = oa.sidecar_sessions(self.val, manifest, 'auto')
        found.assert_called_once_with(self.val.name, **expected)
        self.assertEqual(sessions, self.sessions[:7])
        self.assertEqual((training['digest'], training['sha256']), ('d'*64, oc.sha256_file(path)))
        with mock.patch.object(oa, '_final_training_expected', return_value=expected), \
                mock.patch.object(oc, 'read_final_training', return_value=dict(record, sessions=[-5])) as read:
            with self.assertRaisesRegex(oc.ContractError, 'outside the holdout frame'):
                oa.sidecar_sessions(self.val, manifest, path)
        read.assert_called_once_with(path, collection=self.val.name, **expected)
        # a final-training record of another prereg or N_t stops the sidecar before its tables and batches
        with mock.patch.object(oa, 'sidecar_sessions', side_effect=oc.ContractError('Final training under another prereg')), \
                mock.patch.object(oa, 'set_tables') as tables:
            with self.assertRaisesRegex(oc.ContractError, 'another prereg'):
                self.run_sidecar('early')
        tables.assert_not_called()

    def test_lock_and_collection_path(self):
        lock = self.root/f'.lock-{self.val.name}'
        lock.parent.mkdir(parents=True, exist_ok=True)
        gone = subprocess.Popen([sys.executable, '-c', 'pass'])
        gone.wait()
        try:
            lock.write_text(f'{gone.pid}\n')
            with self.assertRaisesRegex(oc.ContractError, rf'Another sidecar.*pid {gone.pid} is dead'):
                self.run_sidecar('locked')
            lock.write_text(f'{os.getpid()}\n')
            with self.assertRaisesRegex(oc.ContractError, rf'Another sidecar.*\(pid {os.getpid()}\)$'):
                self.run_sidecar('locked')
        finally:
            lock.unlink()
        with oa._FileLock(lock, 'test') as held:
            self.assertEqual(lock.read_text().split(), [str(os.getpid())])
        self.assertFalse(lock.exists())
        copy = oc.output_dir('collections', 'val-copy')
        shutil.copytree(self.val, copy)
        try:
            with self.assertRaises(oc.ContractError):
                oa.sidecar(copy, name='copy', threads=THREADS, memory=MEMORY, agent_set=self.set)
        finally:
            shutil.rmtree(copy)

    def test_deviation_doubles_the_table_and_proposal_limits_once(self):
        records = [dict(id='dev1', step=oa.SIDECAR_STEP, collection=self.val.name),
                   dict(id='dev2', step='leakcheck', collection=self.val.name),
                   dict(id='dev3', step=oa.SIDECAR_STEP, collection='other')]
        with mock.patch.object(oc, 'deviations', return_value=records):
            self.assertEqual(oa.retry_factor(None, self.val.name), 1)
            self.assertEqual(oa.retry_factor('dev1', self.val.name), 2)
            for deviation, pattern in (('dev2', 'not of step'), ('dev3', 'another collection'),
                                       ('dev9', 'not recorded')):
                with self.subTest(deviation=deviation):
                    with self.assertRaisesRegex(oc.ContractError, pattern):
                        oa.retry_factor(deviation, self.val.name)
            with self.assertRaises(oa.ProposalError):
                self.run_sidecar('s1', fail_at=0, deviation='dev1')
            self.assertEqual(oc.read_json(self.root/f'.failed-{self.val.name}-s1-1.json')['factor'], 2)
            result, _ = self.run_sidecar('s1', deviation='dev1')           # its own resume is the same attempt
            report = oc.read_json(Path(result['path'])/oa.SIDECAR_REPORT)
            self.assertEqual((report['deviation'], report['factor'], report['proposal_cap'], report['table_timeout'],
                              report['batch_timeout']),
                             ('dev1', 2, 2*oa.PROPOSAL_CAP, 7200.0, oa.BATCH_TIMEOUT))
            with self.assertRaisesRegex(oc.ContractError, 'already used'):
                self.run_sidecar('s2', deviation='dev1')


# =============================================================================== leaks and suffixes

def plant(day, rows):
    """An extra parquet file in a day partition (a misplaced future event), typed like the partition."""
    directory = oc.partition_paths([day], 'test')[0]
    existing = sorted(directory.glob('*.parquet'))[0]  # caller picks a day with files
    con = small_duckdb()
    try:
        types = con.execute(f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM "
                            f"read_parquet('{existing}', hive_partitioning=false))").fetchall()
        frame = pd.DataFrame(rows, columns=[n for n, _ in types])
        con.register('rows', frame)
        casts = ', '.join(f'CAST({n} AS {t}) AS {n}' for n, t in types)
        con.execute(f"COPY (SELECT {casts} FROM rows) TO '{directory/'zz-planted.parquet'}' (FORMAT parquet)")
    finally:
        con.close()


class LeakTest(unittest.TestCase):
    def test_leakcheck_catches_a_column_that_reads_the_target_week(self):
        world = World(seed=8, probe=False, n_per_week=120, pool=40, population=40)
        try:
            honest = 'SELECT item, CAST(count(*) AS DOUBLE) AS ag_old FROM hist WHERE ts < {S} GROUP BY item'
            leaky = 'SELECT item, CAST(count(*) AS DOUBLE) AS ag_new FROM hist WHERE ts >= {S} GROUP BY item'
            agent_set = make_set(world.base, [
                dict(id='r3p1', round=3, index=1, name='old', kind='feature', level='item', sql=honest,
                     columns=['ag_old']),
                dict(id='r3p2', round=3, index=2, name='new', kind='feature', level='item', sql=leaky,
                     columns=['ag_new'])])
            clean = oa.leakcheck(3, name='leak-clean', agent_set=agent_set, threads=THREADS, memory=MEMORY, batch=30)
            self.assertTrue(clean['ok'], clean)
            start = oc.week_start(3, S5)
            lo, hi = oc.week_days(2)
            last_h3_day = next(d for d in range(hi, lo-1, -1)
                               if any(oc.partition_paths([d], 'test')[0].glob('*.parquet')))
            frame = oc.read_parquet(world.val/oc.FRAME_FILE)
            aid = int(frame.aid.iloc[0])
            plant(last_h3_day, [(1, aid, start + 60, 0, 1), (2, aid, start + 120, 1, 1)])
            oa._FINGERPRINTS.clear()
            oa._KNOWN.clear()
            caught = oa.leakcheck(3, name='leak-caught', agent_set=agent_set, threads=THREADS, memory=MEMORY,
                                  batch=30)
            self.assertFalse(caught['ok'])
            self.assertEqual(caught['fold'], 3)
            self.assertIn('ag_new', caught['history_check']['cells'])
            self.assertNotIn('ag_old', caught['history_check']['cells'])
            self.assertEqual(oc.read_json(caught['path'])['ok'], False)
        finally:
            world.close()

    def test_leakcheck_f4_is_degenerate_and_checks_the_batch_cohort(self):
        """F4: H_4 already holds every partition d < -7, so the variant reads the same files; both variants run
        on the first LEAK_SESSIONS of the holdout population (here the val collection stands in for the holdout)."""
        world = World(seed=9, probe=False, n_per_week=120, pool=40, population=40)
        try:
            honest = 'SELECT item, CAST(count(*) AS DOUBLE) AS ag_old FROM hist WHERE ts < {S} GROUP BY item'
            agent_set = make_set(world.base, [dict(id='r3p1', round=3, index=1, name='old', kind='feature',
                                                   level='item', sql=honest, columns=['ag_old'])])
            holdout = oc.output_dir('collections', 'holdout-F4')       # val with the manifest of F4
            shutil.copytree(world.val, holdout)
            manifest = oc.read_json(holdout/oc.MANIFEST_FILE)
            oc.atomic_json(holdout/oc.MANIFEST_FILE, dict(manifest, role='holdout', fold=4), exist_ok=True)
            sessions = sorted(set(oc.read_parquet(holdout/oc.FRAME_FILE, columns=['session']).session))
            with mock.patch.object(oc, 'require_prereg') as prereg, \
                    mock.patch.object(oc, 'collection_dir', return_value=holdout) as where, \
                    mock.patch.object(oc, 'holdout_population', return_value=dict(sessions=sessions)):
                report = oa.leakcheck(4, name='leak-f4', agent_set=agent_set, threads=THREADS, memory=MEMORY,
                                      batch=7, leak_sessions=12)
            prereg.assert_called_once_with(check_code=True)
            where.assert_called_once_with('holdout')
            self.assertTrue(report['ok'], report)
            self.assertEqual(report['fold'], 4)
            self.assertTrue(report['degenerate'])
            self.assertEqual(report['history']['normal'], report['history']['full'])
            self.assertEqual(report['sessions'], len(sessions))
            self.assertEqual(report['history_check']['sessions'], 12)
            self.assertEqual(report['batch_check']['sessions'], 12)
            self.assertIsNone(report['prefix_check'])
            self.assertEqual(oc.read_json(oc.leakcheck_path('leak-f4'))['degenerate'], True)
        finally:
            world.close()


class SuffixTest(unittest.TestCase):
    def test_suffix_substitution_changes_no_agent_column(self):
        """The events after the cut of W3 sessions are rewritten; every agent column of val-F3 stays."""
        def rewrite(session, events):
            n = len(events)
            if n < 2:
                return events
            c = od.cut_point(session, n)
            # other items, later times (order kept, still inside the week) and other event types
            return events[:c] + [(1 + (aid % 10), ts + 30*(i+1), NAMES[(NAMES.index(kind)+1) % 3])
                                 for i, (aid, ts, kind) in enumerate(events[c:])]
        blocks, labels = [], []
        for suffix in (None, rewrite):
            world = World(seed=9, probe=False, n_per_week=120, pool=40, population=40, w3_suffix=suffix)
            try:
                agent_set = make_set(world.base, [
                    dict(id='r1p1', round=1, index=1, name='covis', kind='table', level='item_pair', sql=COVIS,
                         columns=['tv_cnt']),
                    dict(id='r1p2', round=1, index=2, name='covis_src', kind='source', level='pair', sql=COVIS_SRC),
                    dict(id='r3p1', round=3, index=1, name='covis_max', kind='feature', level='pair', sql=COVIS_MAX,
                         columns=['ag_covis_max']),
                    dict(id='r3p2', round=3, index=2, name='ratio', kind='feature', level='session', sql=RATIO,
                         columns=['ag_ratio'])])
                spec = oa.fold_spec(3, 'test', world.val)
                tables = oa.set_tables(spec, agent_set, timeout_s=60, threads=THREADS)
                keys = oc.read_parquet(world.val/oc.FRAME_FILE, columns=['session', 'aid'])
                block, _ = oa.agent_block(spec, keys, agent_set, tables, threads=THREADS)
                blocks.append(block)
                labels.append(oc.read_parquet(world.val/oc.LABELS_FILE))
            finally:
                world.close()
        self.assertFalse(labels[0].equals(labels[1]))                 # the suffixes did change
        common = blocks[0][['session']].drop_duplicates().merge(blocks[1][['session']].drop_duplicates())
        self.assertGreater(len(common), 20)
        left, right = (b.merge(common).sort_values(['session', 'aid']).reset_index(drop=True) for b in blocks)
        pd.testing.assert_frame_equal(left, right)


if __name__ == '__main__':
    unittest.main()
