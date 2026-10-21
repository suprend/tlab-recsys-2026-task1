"""Tests of scripts/xfer_agent.py on a synthetic adapter (tests/fixtures/xfer_agent/fake_adapter.py).

No real data, no ``claude -p``: ask_llm is replaced and subprocess.run of the H&M loop
module raises. ``xc.adapter`` and ``xc.code_identity`` are patched.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import duckdb
import numpy as np
import pandas as pd

from scripts import hm_agent_loop
from scripts import xfer_agent as xa
from scripts import xfer_common as xc

FIXTURE = Path(__file__).resolve().parent/'fixtures'/'xfer_agent'/'fake_adapter.py'
FAKE_CODE = {'scripts/xfer_agent.py': 'a'*64, 'scripts/xfer_common.py': 'b'*64}
DS = 'tinkoff'

USER_N = dict(name='user_n', idea='events per user', level='user',
              sql='SELECT user_id, CAST(count(*) AS DOUBLE) AS ag_user_n FROM ev '
                  'WHERE user_id IN (SELECT user_id FROM users) GROUP BY user_id')
ITEM_N = dict(name='item_n', idea='events per item', level='item',
              sql='SELECT item_id, CAST(count(*) AS DOUBLE) AS ag_item_n FROM ev GROUP BY item_id')
PAIR_N = dict(name='pair_n', idea='repeat count', level='pair',
              sql='SELECT c.user_id, c.item_id, CAST(count(e.t) AS DOUBLE) AS ag_pair_n FROM cand c '
                  'LEFT JOIN ev e ON e.user_id = c.user_id AND e.item_id = c.item_id GROUP BY c.user_id, c.item_id')
USER_AGE = dict(name='user_age', idea='steps since the last event', level='user',
                sql='SELECT user_id, CAST({A} - max(t) AS DOUBLE) AS ag_user_age FROM ev '
                    'WHERE user_id IN (SELECT user_id FROM users) GROUP BY user_id')
ROW_NUMBER = dict(name='row_no', idea='batch dependent', level='pair',
                  sql='SELECT user_id, item_id, CAST(row_number() OVER (ORDER BY user_id, item_id) AS DOUBLE) '
                      'AS ag_row_no FROM cand')


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


def load_fake():
    spec = importlib.util.spec_from_file_location('xfer_fake_adapter', FIXTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def no_subprocess(*args, **kwargs):
    raise AssertionError('No subprocess (claude -p) may run in these tests')


class _NoRun:
    """subprocess as seen by hm_agent_loop: everything but run (git of the tests keeps the real module)."""

    def __getattr__(self, name):
        return no_subprocess if name == 'run' else getattr(subprocess, name)


def no_llm(prompt, model):
    raise AssertionError('ask_llm must be mocked per test')


class Root(unittest.TestCase):
    """A temp Git root with the fake adapter's partitions, base.json and helpers for collections."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, 'init', '-q')
        (self.root/'configs'/'datasets').mkdir(parents=True)
        (self.root/'artifacts'/'xfer').mkdir(parents=True)
        (self.root/'README').write_text('x')
        git(self.root, 'add', 'README')
        git(self.root, 'commit', '-q', '-m', 'init')
        self.fake = load_fake()
        self.patches = [mock.patch.object(xc, 'ROOT', self.root),
                        mock.patch.object(xc, 'adapter', lambda dataset: self.fake),
                        mock.patch.object(xc, 'code_identity', lambda dataset: dict(FAKE_CODE)),
                        mock.patch.object(hm_agent_loop, 'subprocess', _NoRun()),
                        mock.patch.object(xa, 'ask_llm', no_llm)]
        for patch in self.patches:
            patch.start()
        xa._PROBE_CACHE.clear()
        self.events = self.fake.build()
        self.base = xc.make_base(DS, dict(total=20), [
            dict(name='f_pop', formula='noise', missing='never'),
            dict(name='f_cat', formula='category', missing='never')], ['f_cat'])
        self.write_config('base', self.base)

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        xa._PROBE_CACHE.clear()
        self.tmp.cleanup()

    # -- helpers

    def commit(self, *paths):
        git(self.root, 'add', *[str(Path(p).relative_to(self.root)) for p in paths])
        git(self.root, 'commit', '-q', '-m', 'c')

    def write_config(self, kind, value, commit=True):
        path = xc.config_path(DS, kind)
        path.write_text(json.dumps(value))
        if commit:
            self.commit(path)
        return path

    def users_before(self, anchor):
        return sorted(self.events.loc[self.events['t'] < anchor, 'user_id'].unique().tolist())

    def collection(self, role, anchor, users=None, code=None, base=None):
        users = self.users_before(anchor) if users is None else users
        rng = np.random.default_rng(anchor)
        rows = []
        for user in users:
            for item in sorted(rng.choice(np.arange(1, self.fake.ITEMS+1), size=20, replace=False)):
                rows.append((int(user), int(item)))
        frame = pd.DataFrame(rows, columns=['user_id', 'item_id']).astype('int64')
        n = len(frame)
        frame['rank_recent'] = np.where(rng.random(n) < 0.5, rng.integers(1, 20, n), np.nan)
        frame['rank_pop'] = np.where(np.isnan(frame['rank_recent']), rng.integers(1, 20, n), np.nan)
        frame['f_pop'] = rng.random(n)
        frame['f_cat'] = rng.integers(0, 3, n)
        directory = xc.new_output(xc.output_dir(DS, 'collections', xc.collection_name(role, anchor)))
        xc.write_parquet(frame, directory/xc.FRAME_FILE, order_by='user_id, item_id')
        sealed = None
        if role in ('train', 'val'):
            for name in xc.LABEL_FILES:
                (directory/name).write_bytes(b'labels')
        if role == 'holdout':
            sealed = {name: '0'*64 for name in xc.LABEL_FILES}
        xc.write_manifest(directory, DS, role, anchor, dict(rows=n), base or self.base, code or dict(FAKE_CODE),
                          sealed=sealed)
        return directory

    def probe(self):
        collection = self.collection('probe', 60, users=self.fake.probe_pool())
        return Path(xa.prepare_probe(DS, collection)['path'])

    def make_set(self, proposals, commit=True, audit=None):
        frozen = []
        for index, proposal in enumerate(proposals, 1):
            columns = self._columns(proposal)
            frozen.append(dict(id=f'r1p{index}', round=1, index=index, columns=columns, probe_seconds='2^0–2^1',
                               **proposal))
        prompt = xa.prompt_identity(DS)
        value = dict(format=xa.SET_FORMAT, dataset=DS, run=dict(id='a'), run_sha256='c'*64, probe={},
                     base_digest=self.base['digest'], prompt=prompt, prompt_digest=prompt['digest'],
                     code=dict(FAKE_CODE), proposals=frozen, attempts=[],
                     columns=[n for p in frozen for n in p['columns']], budget={}, digest=xa.set_digest(frozen),
                     audit=audit)
        xa.check_set(DS, value, self.base)
        path = xc.config_path(DS, 'set')
        xc.atomic_json(path, value, exist_ok=True)
        if commit:
            self.commit(path)
        return value

    @staticmethod
    def _columns(proposal):
        import re
        return re.findall(r'AS (ag_[a-z0-9_]+)', proposal['sql'])

    def prereg(self, code=None):
        value = dict(base_sha256=xc.sha256_file(xc.config_path(DS, 'base')),
                     set_sha256=xc.sha256_file(xc.config_path(DS, 'set')), base_digest=self.base['digest'],
                     code=code or dict(FAKE_CODE))
        return self.write_config('prereg', value)

    def keys_file(self, users, anchor=60):
        rows = [(u, i) for u in users for i in range(1, 6)]
        path = self.root/'keys.parquet'
        xc.write_parquet(pd.DataFrame(rows, columns=['user_id', 'item_id']).astype('int64'), path)
        return path


class CheckSql(Root):
    def ok(self, sql, level='pair'):
        xa.check_sql(DS, sql, level)

    def bad(self, sql, level='pair', text=None):
        with self.assertRaises(xa.ProposalError) as caught:
            xa.check_sql(DS, sql, level)
        if text:
            self.assertIn(text, str(caught.exception))

    def test_accepts_the_examples(self):
        for proposal in (USER_N, ITEM_N, PAIR_N, USER_AGE, ROW_NUMBER):
            xa.check_sql(DS, proposal['sql'], proposal['level'])
        self.ok('WITH x AS (SELECT user_id FROM ev WHERE t >= {A} - 10) SELECT 1;')

    def test_hm_rules(self):
        self.bad("SELECT * FROM read_parquet('x')", text='read_parquet')
        self.bad('SELECT 1; SELECT 2', text='one statement')
        self.bad('SELECT 1 -- c', text='comments')
        self.bad('SELECT 1 /* c */', text='comments')
        self.bad('DELETE FROM ev', text='SELECT or WITH')
        self.bad('SELECT * FROM transactions', text='transactions')
        self.bad('SELECT random()', text='random')
        self.bad("SELECT error('x')", text='error(')
        self.bad("SELECT 1 WHERE '2020-01-01' > 'a'", text='date literals')
        self.bad('SELECT {B}', text='placeholder {A}')
        self.bad('SELECT item_id, 1 AS ag_x FROM cand', level='item', text='cand')
        self.bad('SELECT 1', level='global', text='level')

    def test_adapter_rules(self):
        self.bad('SELECT * FROM data_train', text='data_train')
        self.bad('SELECT * FROM ev_raw', text='ev_raw')
        self.bad('SELECT 1 FROM ev WHERE {A} - 5 <= t', text='left of a comparison')
        self.bad('SELECT 1 FROM ev WHERE t < 50', text='compared with a number')
        self.ok('SELECT 1 FROM ev WHERE t < {A} - 5')


class Sandbox(Root):
    def test_barriers(self):
        keys = self.keys_file([1, 2, 3])
        con = xa.sandbox(DS, 60, keys, threads=3)
        try:
            self.assertEqual(con.execute('SELECT count(*) FROM cand').fetchone()[0], 15)
            self.assertEqual(con.execute('SELECT count(*) FROM users').fetchone()[0], 3)
            future = xc.events_path(DS)['parts']/'b=60'/'part-0.parquet'
            with self.assertRaises(duckdb.PermissionException):
                con.execute(f"SELECT count(*) FROM read_parquet('{future}')").fetchall()
            with self.assertRaises(duckdb.Error):
                con.execute('SET enable_external_access=true')
            with self.assertRaises(duckdb.Error):
                con.execute('SET lock_configuration=false')
            secret = pd.DataFrame({'x': [1]})  # noqa: F841 - a Python variable a query must not reach
            with self.assertRaises(duckdb.CatalogException):
                con.execute('SELECT * FROM secret').fetchall()
            xa._require_sandbox(con)
        finally:
            xa._close(con)
        with self.assertRaises(ValueError):
            xa._require_sandbox(duckdb.connect())

    def test_canary_through_views(self):
        keys = self.keys_file([3, 6, 9])
        for anchor in (40, 60, 70):
            con = xa.sandbox(DS, anchor, keys)
            try:
                top, canary = con.execute(
                    f'SELECT max(t), count(*) FILTER (WHERE item_id = {self.fake.CANARY}) FROM ev').fetchone()
            finally:
                xa._close(con)
            self.assertLess(top, anchor)
            if anchor <= 60:
                self.assertEqual(canary, 0)
        with self.assertRaises(xc.ContractError):
            xa.sandbox(DS, 80, keys)
        # the view filter alone, with partitions of the whole history allowed
        self.fake.LEAKY = True
        con = xa.sandbox(DS, 60, keys)
        try:
            self.assertLess(con.execute('SELECT max(t) FROM ev').fetchone()[0], 60)
        finally:
            xa._close(con)

    def test_run_proposal_and_errors(self):
        keys = self.keys_file([3, 6, 9])
        spec = xa._views(DS, 60, 'probe')
        con = xa.sandbox(DS, 60, keys, views=spec)
        try:
            frame = xa.run_proposal(DS, con, spec, USER_AGE, 60, 20)
            self.assertEqual(list(frame.columns), ['user_id', 'item_id', 'ag_user_age'])
            self.assertTrue((frame['ag_user_age'] > 0).all())
            outside = dict(USER_N, sql='SELECT user_id, CAST(count(*) AS DOUBLE) AS ag_user_n FROM ev GROUP BY user_id')
            with self.assertRaisesRegex(xa.ProposalError, 'outside users'):
                xa.run_proposal(DS, con, spec, outside, 60, 20)
            text = dict(USER_N, sql="SELECT user_id, 'a' AS ag_text FROM users")
            with self.assertRaisesRegex(xa.ProposalError, 'VARCHAR'):
                xa.run_proposal(DS, con, spec, text, 60, 20)
            with self.assertRaisesRegex(xa.ProposalError, 'Binder|Catalog'):
                xa.run_proposal(DS, con, spec, dict(USER_N, sql='SELECT user_id, ag_none FROM users'), 60, 20)
        finally:
            xa._close(con)


class PromptNumbers(Root):
    def test_whitelist(self):
        stats = dict(users=60, share=0.25, nested=dict(p90=12))
        constants = dict(k=5)
        problems = xa.prompt_number_problems(
            dict(stats='users 60, share 0.25, p90 12, k 5', names='ag_x1 p90 v2 x.5 a@3', feedback='2^3–2^4 s'),
            stats, {}, constants, ['2^3–2^4 s'])
        self.assertEqual(problems, [])
        problems = xa.prompt_number_problems(dict(stats='users 61', x='seen 0.250'), stats, {}, constants, '')
        self.assertEqual(problems, [('stats', '61')])  # 0.250 equals the value 0.25
        problems = xa.prompt_number_problems(dict(x=['about 7']), stats, {}, constants, 'round 7 of 6')
        self.assertEqual(problems, [])

    def test_render_prompt(self):
        probe = self.probe()
        stats = xc.read_json(probe/xa.STATS_FILE)
        left = dict(pair_user_seconds=73.4, item_seconds=180.0)
        prompt = xa.render_prompt(DS, stats, self.base, [], 2, 6, left)
        self.assertIn('pair+user 70 s of 90 s', prompt)  # the template's own numbers are not tested
        self.assertIn('round 2 of 6', prompt)
        self.assertIn(xa.WARNING, prompt)
        self.fake.EXTRA = '\nrows: 777'
        with self.assertRaisesRegex(ValueError, 'stats:777'):
            xa.render_prompt(DS, stats, self.base, [], 2, 6, left)
        self.fake.EXTRA = '\nsource: kaggle'
        with self.assertRaisesRegex(ValueError, 'names'):
            xa.render_prompt(DS, stats, self.base, [], 2, 6, left)

    def test_feedback_is_coarse(self):
        record = dict(id='r1p1', name='x', idea='an idea 12345678901', level='user', sql=USER_N['sql'],
                      status='invalid', error='bad 1234567890123', seconds='2^1–2^2', rows='2^5–2^6',
                      columns=[dict(name='ag_user_n', non_null_share=0.333333, non_null_share_recent=0.5,
                                    non_null_share_global=None, distinct='2^3–2^4', max_abs_spearman=0.4567,
                                    nearest='f_pop')])
        text = xa.format_feedback([record])
        self.assertIn('non-null 0.33', text)
        self.assertIn('max |rho| 0.5', text)
        self.assertNotIn('12345678901', text)
        self.assertNotIn('0.4567', text)
        self.assertEqual(xa.format_feedback([]), '')


class Evaluate(Root):
    def setUp(self):
        super().setUp()
        self.probe_dir = self.probe()

    def test_valid_and_coarse(self):
        record, values = xa.evaluate_proposal(DS, self.probe_dir, dict(USER_N, id='r1p1', round=1, index=1), [])
        self.assertEqual(record['status'], 'valid', record['error'])
        self.assertTrue(xa._is_bucket(record['seconds']))
        self.assertTrue(xa._is_bucket(record['rows']))
        column = record['columns'][0]
        self.assertEqual(column['name'], 'ag_user_n')
        self.assertEqual(column['non_null_share'], 1.0)
        self.assertTrue(xa._is_bucket(column['distinct']))
        self.assertIsInstance(values.attrs['probe_seconds'], float)
        record, values = xa.evaluate_proposal(DS, self.probe_dir, dict(ITEM_N, id='r1p2', round=1, index=2), [values])
        self.assertEqual(record['status'], 'valid', record['error'])

    def test_invalid(self):
        cases = {
            'distinct': "SELECT user_id, CAST(1 AS DOUBLE) AS ag_one FROM users",
            'batch invariance': ROW_NUMBER['sql'],
            'Spearman': 'SELECT user_id, CAST(count(*) AS DOUBLE) AS ag_aa, CAST(2 * count(*) AS DOUBLE) AS ag_bb '
                        'FROM ev WHERE user_id IN (SELECT user_id FROM users) GROUP BY user_id',
            'does not match': "SELECT user_id, CAST(count(*) AS DOUBLE) AS f_pop FROM ev "
                            "WHERE user_id IN (SELECT user_id FROM users) GROUP BY user_id",
            'outside users': 'SELECT user_id, CAST(count(*) AS DOUBLE) AS ag_nn FROM ev GROUP BY user_id',
        }
        for text, sql in cases.items():
            level = 'pair' if 'cand' in sql else 'user'
            record, values = xa.evaluate_proposal(DS, self.probe_dir, dict(USER_N, level=level, sql=sql, id='r1p1',
                                                                           round=1, index=1), [])
            self.assertEqual(record['status'], 'invalid', text)
            self.assertIn(text, record['error'])
            self.assertIsNone(values)
        _, values = xa.evaluate_proposal(DS, self.probe_dir, dict(USER_N, id='r1p1', round=1, index=1), [])
        record, _ = xa.evaluate_proposal(DS, self.probe_dir, dict(USER_N, id='r1p2', round=1, index=2), [values])
        self.assertIn('already accepted', record['error'])

    def test_probe_refusals(self):
        other = self.collection('val', 60)
        with self.assertRaises(xc.ContractError):
            xa.prepare_probe(DS, other, name='bad')
        with self.assertRaises(FileExistsError):  # the probe exists
            xa.prepare_probe(DS, self.probe_dir.parent.parent/'collections'/'probe-60')


def reply(*proposals):
    return [{key: p[key] for key in xa.FIELDS} for p in proposals]


class Loop(Root):
    def setUp(self):
        super().setUp()
        self.probe_dir = self.probe()
        self.prompts = []

    def asker(self, *rounds):
        queue = list(rounds)

        def ask(prompt, model):
            self.assertEqual(model, xa.MODEL)
            self.prompts.append(prompt)
            item = queue.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item, dict(cost_usd=0.5, command=['claude', '-p', '--model', model], seconds=1.0)
        return ask

    def test_run_and_freeze(self):
        ask = self.asker(reply(USER_N, ITEM_N), reply(PAIR_N, USER_N), *[reply(USER_AGE)]*4)
        with mock.patch.object(xa, 'ask_llm', ask):
            run = xa.run_loop(DS, self.probe_dir, 'run-a')
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(run['calls'], 6)
        self.assertEqual(run['columns'], ['ag_user_n', 'ag_item_n', 'ag_pair_n', 'ag_user_age'])
        self.assertEqual(run['prompt'], xa.prompt_identity(DS))
        self.assertEqual(run['code'], FAKE_CODE)
        self.assertIn('ag_user_n', self.prompts[1])
        self.assertIn('already accepted', self.prompts[2])
        for prompt in self.prompts:
            self.assertNotIn('probe_seconds', prompt)
        result = xa.freeze(DS, run['path'])
        saved = xc.read_json(xc.config_path(DS, 'set'))
        for key in ('format', 'dataset', 'proposals', 'columns', 'prompt_digest', 'code', 'run_sha256', 'audit'):
            self.assertIn(key, saved)
        self.assertEqual(saved['prompt_digest'], xa.prompt_digest(DS))
        self.assertEqual(saved['prompt_digest'], self.fake_digest())
        self.assertIsNone(saved['audit'])
        self.assertEqual(saved['run_sha256'], xc.sha256_file(Path(run['path'])/'run.json'))
        self.assertEqual(saved['columns'], ['ag_user_n', 'ag_item_n', 'ag_pair_n', 'ag_user_age'])
        self.assertEqual([p['id'] for p in saved['proposals']], ['r1p1', 'r1p2', 'r2p1', 'r3p1'])
        self.assertEqual(saved['digest'], xa.set_digest(saved['proposals']))
        self.assertEqual(result['digest'], saved['digest'])
        xa.read_set(DS, base=self.base)
        xa.freeze(DS, run['path'])  # identical content: allowed
        path = xc.config_path(DS, 'set')
        path.write_text(path.read_text().replace('"audit": null', '"audit": {}'))
        with self.assertRaises(FileExistsError):
            xa.freeze(DS, run['path'])
        with self.assertRaisesRegex(ValueError, 'already has a run'):
            xa.run_loop(DS, self.probe_dir, 'run-b')

    def fake_digest(self):
        return xc.canonical_digest(dict(template=self.fake.PROMPT_TEMPLATE, constants=self.fake.PROMPT_CONSTANTS))

    def test_limits(self):
        with self.assertRaisesRegex(ValueError, 'max_calls'):
            xa.run_loop(DS, self.probe_dir, 'run-a', max_calls=13)
        with self.assertRaisesRegex(ValueError, 'model'):
            xa.run_loop(DS, self.probe_dir, 'run-a', model='other')

    def test_failed_call_retry_and_retry_run(self):
        error = hm_agent_loop.LLMError('no answer', dict(cost_usd=0.25))
        ask = self.asker(error, reply(USER_N), error, error)
        with mock.patch.object(xa, 'ask_llm', ask):
            with self.assertRaisesRegex(RuntimeError, 'both failed'):
                xa.run_loop(DS, self.probe_dir, 'run-a')
        failed = xc.read_json(xc.output_dir(DS, 'run', 'run-a', 'run.json'))
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['calls'], 4)
        self.assertEqual(failed['cost_usd'], 1.25)  # three failed calls of 0.25 and one of 0.5
        self.assertEqual(failed['cost_unknown_calls'], 0)
        self.assertEqual(failed['valid'], 1)
        with self.assertRaisesRegex(ValueError, 'reason'):
            xa.run_loop(DS, self.probe_dir, 'run-b', retry_of=xc.output_dir(DS, 'run', 'run-a'))
        ask = self.asker(reply(USER_N), *[reply(USER_AGE)]*5)
        with mock.patch.object(xa, 'ask_llm', ask):
            run = xa.run_loop(DS, self.probe_dir, 'run-b', max_calls=3,
                              retry_of=xc.output_dir(DS, 'run', 'run-a'), reason='network')
        self.assertEqual(run['stop'], 'max_calls')
        self.assertEqual(run['calls'], 3)

    def test_budget(self):
        def evaluate(dataset, probe, proposal, prior, threads=3):
            values = pd.DataFrame({'user_id': [1, 2], proposal['name']: [1.0, 2.0]})
            values.attrs['probe_seconds'] = 50.0
            column = dict(name=proposal['name'])
            return dict(status='valid', error=None, seconds='2^5–2^6', rows='2^1–2^2', columns=[column]), values
        proposals = [dict(USER_N, name=f'ag_u{i}') for i in range(3)]
        with mock.patch.object(xa, 'ask_llm', self.asker(reply(*proposals))):
            run = xa.run_loop(DS, self.probe_dir, 'run-a', rounds=1, evaluate=evaluate)
        log = [json.loads(line) for line in (Path(run['path'])/'log.jsonl').read_text().splitlines()]
        self.assertEqual([r['status'] for r in log], ['valid', 'budget', 'budget'])
        self.assertEqual(run['budget']['used']['pair_user_seconds'], 50.0)


class Sidecar(Root):
    def setUp(self):
        super().setUp()
        self.make_set([USER_N, ITEM_N, PAIR_N], audit=dict(ok=True))
        self.prereg()

    def test_alignment(self):
        collection = self.collection('train', 50)
        result = xa.sidecar(DS, collection, batch_users=7)
        directory = Path(result['path'])
        manifest = xc.read_sidecar(directory, collection, xc.sha256_file(xc.config_path(DS, 'set')))
        self.assertEqual(manifest['columns'], ['ag_user_n', 'ag_item_n', 'ag_pair_n'])
        agent = xc.read_parquet(directory/xc.SIDECAR_FILE)
        frame = xc.read_parquet(collection/xc.FRAME_FILE)
        self.assertEqual(agent[['user_id', 'item_id']].values.tolist(), frame[['user_id', 'item_id']].values.tolist())
        past = self.events[self.events['t'] < 50]
        users = past.groupby('user_id').size()
        items = past.groupby('item_id').size()
        pairs = past.groupby(['user_id', 'item_id']).size()
        expected_user = agent['user_id'].map(users).astype(float)
        expected_item = agent['item_id'].map(items).astype(float)
        expected_pair = pd.Series([float(pairs.get((u, i), 0)) for u, i in zip(agent['user_id'], agent['item_id'])])
        np.testing.assert_array_equal(agent['ag_user_n'].to_numpy(), expected_user.to_numpy())
        np.testing.assert_array_equal(agent['ag_item_n'].to_numpy(), expected_item.to_numpy())
        np.testing.assert_array_equal(agent['ag_pair_n'].to_numpy(), expected_pair.to_numpy())
        report = xc.read_json(directory/xa.SIDECAR_REPORT)
        self.assertGreater(report['batches'], 1)
        with self.assertRaises(xc.ContractError):
            xa.sidecar(DS, collection)  # never rewritten

    def test_refusals(self):
        other_code = self.collection('train', 40, code={'scripts/xfer_agent.py': 'f'*64})
        with self.assertRaisesRegex(xc.ContractError, 'code other than the prereg'):
            xa.sidecar(DS, other_code)
        other_base = xc.make_base(DS, dict(total=21), self.base['features'], ['f_cat'])
        val = self.collection('val', 60, base=other_base)
        with self.assertRaisesRegex(xc.ContractError, 'another base'):
            xa.sidecar(DS, val)
        kaggle = self.collection('kaggle', 80)
        with self.assertRaisesRegex(xc.ContractError, 'window closed'):
            xa.sidecar(DS, kaggle)
        self.assertFalse(xc.output_dir(DS, 'sidecars', 'kaggle-80').exists())


class Leakcheck(Root):
    def setUp(self):
        super().setUp()
        self.train = self.collection('train', 50)
        self.holdout = self.collection('holdout', 70)

    def check(self, proposals):
        self.make_set(proposals)
        self.prereg()
        return xa.leakcheck(DS, users=40, name='lc')

    def test_ok(self):
        result = self.check([USER_N, ITEM_N, PAIR_N, USER_AGE])
        report = xc.read_json(Path(result['path'])/'report.json')
        self.assertIs(report['ok'], True)
        self.assertEqual(set(report['anchors']), {'50', '70'})
        for entry in report['anchors'].values():
            self.assertEqual(entry['users'], 40)
            self.assertEqual(entry['invariance_batches'], 4)
            self.assertTrue(entry['ok'])
        self.assertEqual(report['anchors']['50']['future_files'], 2)  # b=50, b=60 start before A_holdout
        self.assertTrue(report['anchors']['70']['degenerate'])  # full history = the cut at A_holdout

    def test_leak_without_view_filter(self):
        self.fake.LEAKY = True
        with self.assertRaisesRegex(ValueError, 'LEAK'):
            self.check([USER_N, USER_AGE])
        report = xc.read_json(xc.output_dir(DS, 'leakcheck', 'lc', 'report.json'))
        self.assertIs(report['ok'], False)
        self.assertGreater(sum(report['anchors']['50']['leak_mismatches'].values()), 0)

    def test_invariance_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'LEAK'):
            self.check([USER_N, ROW_NUMBER])
        report = xc.read_json(xc.output_dir(DS, 'leakcheck', 'lc', 'report.json'))
        self.assertIs(report['ok'], False)
        entry = report['anchors']['50']
        self.assertEqual(sum(entry['leak_mismatches'].values()), 0)
        self.assertGreater(entry['invariance_mismatches']['ag_row_no'], 0)
        self.assertEqual(entry['invariance_mismatches']['ag_user_n'], 0)

    def test_leak_keys_in_query_order(self):
        keys, users = xa.leak_keys(self.train, 5)
        self.assertEqual(users, xc.cap_queries(self.users_before(50), 5))
        self.assertEqual(sorted(set(keys['user_id'])), sorted(users))

    def test_cell_mismatches(self):
        left = pd.DataFrame({'a': [1.0, np.nan, 3.0, np.inf]})
        right = pd.DataFrame({'a': [1.0 + 1e-12, np.nan, np.nan, np.nan]})
        self.assertEqual(xa.cell_mismatches(left, right, ['a']), {'a': 1})


class Export(Root):
    def test_manifest_only(self):
        result = xa.export(DS, 'e1')
        directory = Path(result['path'])
        self.assertEqual(sorted(p.name for p in directory.iterdir()), ['export.json'])
        record = xc.read_json(directory/'export.json')
        self.assertEqual(list(record['anchors']), ['40', '50', '60', '70'])
        self.assertEqual(len(record['files']), 7)
        self.assertEqual(xa.check_export(DS, directory, 60), record['digest'])
        (xc.events_path(DS)['parts']/'b=0'/'part-0.parquet').write_bytes(b'changed')
        with self.assertRaises(xc.ContractError):
            xa.check_export(DS, directory, 60)


class RunFamily(Loop):
    """B1 and the retry chain: one run per dataset, whatever its probe."""

    def write_run(self, name, **fields):
        directory = xc.output_dir(DS, 'run', name)
        directory.mkdir(parents=True)
        record = dict(format=xa.RUN_FORMAT, dataset=DS, status='failed', retry_of=None,
                      probe=dict(probe_sha256=self.probe_sha()), error=dict(type='RuntimeError'))
        record.update(fields)
        xc.atomic_json(directory/'run.json', record)
        return directory

    def probe_sha(self):
        return xc.sha256_file(self.probe_dir/'probe.json')

    def family(self, name, retry_of=None, reason=None, probe_sha=None):
        return xa.run_family(DS, xc.output_dir(DS, 'run', name), probe_sha or self.probe_sha(), retry_of, reason)

    def test_two_probes(self):
        second = Path(xa.prepare_probe(DS, xc.output_dir(DS, 'collections', 'probe-60'), name='probe-2')['path'])
        with mock.patch.object(xa, 'ask_llm', self.asker(*[reply(USER_N)]*6)):
            run = xa.run_loop(DS, self.probe_dir, 'run-a')
        self.assertEqual(run['status'], 'completed')
        with self.assertRaisesRegex(ValueError, 'already has a run'):
            xa.run_loop(DS, second, 'run-b')
        with self.assertRaisesRegex(xc.ContractError, 'already has a run'):
            xa.prepare_probe(DS, xc.output_dir(DS, 'collections', 'probe-60'), name='probe-3')
        # a second completed run, wherever it came from, leaves freeze nothing to choose
        copy = xc.output_dir(DS, 'run', 'run-c')
        copy.mkdir()
        record = xc.read_json(Path(run['path'])/'run.json')
        record['probe'] = dict(record['probe'], probe_sha256=xc.sha256_file(second/'probe.json'))
        xc.atomic_json(copy/'run.json', record)
        with self.assertRaisesRegex(xc.ContractError, 'More than one completed run'):
            xa.freeze(DS, run['path'])

    def test_retry_chain(self):
        first = self.write_run('run-a')
        with self.assertRaisesRegex(ValueError, 'already has a run'):
            self.family('run-b')
        with self.assertRaisesRegex(ValueError, 'go together'):
            self.family('run-b', retry_of=first)
        with self.assertRaisesRegex(ValueError, 'non-empty'):
            self.family('run-b', retry_of=first, reason=' ')
        with self.assertRaisesRegex(ValueError, 'probe of run-a'):
            self.family('run-b', retry_of=first, reason='net', probe_sha='0'*64)
        self.assertEqual(self.family('run-b', retry_of=first, reason='net'), str(first.resolve()))
        second = self.write_run('run-b', retry_of=str(first.resolve()))
        with self.assertRaisesRegex(ValueError, 'already retried'):
            self.family('run-c', retry_of=first, reason='net')
        third = self.write_run('run-c', retry_of=str(second.resolve()))
        with self.assertRaisesRegex(ValueError, 'already has 2 retries'):
            self.family('run-d', retry_of=third, reason='net')

    def test_retry_refusals(self):
        aborted = self.write_run('run-a', error=dict(type='KeyboardInterrupt'))
        with self.assertRaisesRegex(ValueError, 'stopped by the operator'):
            self.family('run-b', retry_of=aborted, reason='x')
        silent = self.write_run('run-b', error=None)
        with self.assertRaisesRegex(ValueError, 'no error type'):
            self.family('run-c', retry_of=silent, reason='x')
        failed = self.write_run('run-c')
        self.write_run('run-d', status='completed')
        with self.assertRaisesRegex(ValueError, 'completed'):
            self.family('run-e', retry_of=failed, reason='x')
        done = xc.output_dir(DS, 'run', 'run-d')
        with self.assertRaisesRegex(ValueError, 'not failed'):
            self.family('run-e', retry_of=done, reason='x')
        with self.assertRaisesRegex(ValueError, 'must name a run'):
            self.family('run-e', retry_of=xc.output_dir(DS, 'run', 'run-zz'), reason='x')

    def test_unreadable_run_dir_blocks(self):
        xc.output_dir(DS, 'run', 'run-x').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'already has a run'):
            self.family('run-a')
        with self.assertRaisesRegex(ValueError, 'no error type'):
            self.family('run-a', retry_of=xc.output_dir(DS, 'run', 'run-x'), reason='x')

    def test_keyboard_interrupt_recorded(self):
        with mock.patch.object(xa, 'ask_llm', self.asker(KeyboardInterrupt())):
            with self.assertRaises(KeyboardInterrupt):
                xa.run_loop(DS, self.probe_dir, 'run-a')
        record = xc.read_json(xc.output_dir(DS, 'run', 'run-a', 'run.json'))
        self.assertEqual(record['error']['type'], 'KeyboardInterrupt')
        with self.assertRaisesRegex(ValueError, 'stopped by the operator'):
            xa.run_loop(DS, self.probe_dir, 'run-b', retry_of=xc.output_dir(DS, 'run', 'run-a'), reason='x')

    def test_lock(self):
        with xa._RunLock(DS):
            with self.assertRaisesRegex(ValueError, 'Another run holds'):
                xa.run_loop(DS, self.probe_dir, 'run-a')
        self.assertFalse((xc.output_dir(DS, 'run')/'.run.lock').exists())
        self.assertFalse(xc.output_dir(DS, 'run', 'run-a').exists())


class FreezeGuards(Loop):
    def completed(self):
        with mock.patch.object(xa, 'ask_llm', self.asker(reply(USER_N, ITEM_N), *[reply(USER_AGE)]*5)):
            return Path(xa.run_loop(DS, self.probe_dir, 'run-a')['path'])

    def test_log_sha(self):
        run = self.completed()
        with (run/'log.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(xc.ContractError, 'log.jsonl differs'):
            xa.freeze(DS, run)

    def test_budget(self):
        run = self.completed()
        record = xc.read_json(run/'run.json')
        record['probe_seconds'] = {k: 100.0 for k in record['probe_seconds']}
        xc.atomic_json(run/'run.json', record, exist_ok=True)
        with self.assertRaisesRegex(xc.ContractError, 'exceed the probe budget'):
            xa.freeze(DS, run)

    def test_base(self):
        run = self.completed()
        other = xc.make_base(DS, dict(total=21), self.base['features'], ['f_cat'])
        self.write_config('base', other)
        with self.assertRaisesRegex(xc.ContractError, 'base.json changed'):
            xa.freeze(DS, run)

    def test_run_outside_run_dir(self):
        run = self.completed()
        stray = xc.output_dir(DS, 'probe', 'run-a')
        shutil.copytree(run, stray)
        with self.assertRaisesRegex(xc.ContractError, 'Only a run under'):
            xa.freeze(DS, stray)
        self.assertFalse(xc.config_path(DS, 'set').exists())

    def test_failed_run_not_frozen(self):
        with mock.patch.object(xa, 'ask_llm', self.asker(ValueError('x'), ValueError('y'))):
            with self.assertRaises(RuntimeError):
                xa.run_loop(DS, self.probe_dir, 'run-a')
        with self.assertRaisesRegex(xc.ContractError, 'Only a completed'):
            xa.freeze(DS, xc.output_dir(DS, 'run', 'run-a'))


class SetGuards(Root):
    def test_check_set(self):
        good = self.make_set([USER_N, ITEM_N], commit=False)
        xa.check_set(DS, good, self.base)
        bad = json.loads(json.dumps(good))
        bad['proposals'][0]['sql'] = bad['proposals'][0]['sql'].replace('count(*)', 'sum(1)')
        with self.assertRaisesRegex(xc.ContractError, 'digest'):
            xa.check_set(DS, bad, self.base)
        bad = json.loads(json.dumps(good))
        bad['prompt_digest'] = '0'*64
        with self.assertRaisesRegex(xc.ContractError, 'prompt_digest'):
            xa.check_set(DS, bad, self.base)
        bad = json.loads(json.dumps(good))
        bad['proposals'][0]['sql'] = USER_N['sql'].replace('FROM ev', 'FROM ev_raw')
        bad['digest'] = xa.set_digest(bad['proposals'])
        with self.assertRaisesRegex(xa.ProposalError, 'r1p1: .*ev_raw'):
            xa.check_set(DS, bad, self.base)
        bad = json.loads(json.dumps(good))
        del bad['audit']
        with self.assertRaisesRegex(xc.ContractError, 'audit'):
            xa.check_set(DS, bad, self.base)


class SidecarGuards(Root):
    def setUp(self):
        super().setUp()
        self.train = self.collection('train', 50)

    def test_requires_prereg_and_audit(self):
        self.make_set([USER_N], audit=dict(ok=True))
        with self.assertRaisesRegex(xc.ContractError, 'Prereg'):
            xa.sidecar(DS, self.train)
        self.prereg()
        self.make_set([USER_N, ITEM_N], audit=dict(ok=True))  # committed after the prereg
        with self.assertRaisesRegex(xc.ContractError, 'set differs from prereg'):
            xa.sidecar(DS, self.train)
        self.make_set([USER_N])
        self.prereg()
        with self.assertRaisesRegex(xc.ContractError, 'audit is null'):
            xa.sidecar(DS, self.train)

    def test_row_alignment_guard(self):
        self.make_set([USER_N], audit=dict(ok=True))
        self.prereg()
        real = xa.agent_columns

        def shuffled(*args, **kwargs):
            values, info = real(*args, **kwargs)
            return values.iloc[::-1].reset_index(drop=True), info
        with mock.patch.object(xa, 'agent_columns', shuffled):
            with self.assertRaisesRegex(xc.ContractError, 'rows differ from the frame rows'):
                xa.sidecar(DS, self.train)
        self.assertFalse(xc.sidecar_dir(DS, self.train).exists())
        self.assertEqual(list(xc.output_dir(DS, 'sidecars').iterdir()), [])

    def test_batches_and_superseded_holdout(self):
        self.make_set([USER_N, ITEM_N], audit=dict(ok=True))
        self.prereg()
        keys = xa._frame_keys(self.train)
        ranges = xa.sidecar_batches(keys, batch_rows=100)
        self.assertEqual(ranges[0][0], 0)
        self.assertEqual(ranges[-1][1], len(keys))
        self.assertTrue(all(a[1] == b[0] for a, b in zip(ranges, ranges[1:])))
        users = keys['user_id'].to_numpy()
        self.assertTrue(all(users[b-1] != users[b] for _, b in ranges[:-1]))  # whole users only
        with mock.patch.object(xa, 'MAX_ROWS', 50):
            with self.assertRaisesRegex(xc.ContractError, 'exceeds'):
                xa.sidecar_batches(keys, batch_rows=100)
        result = xa.sidecar(DS, self.train, batch_rows=100)
        report = xc.read_json(Path(result['path'])/xa.SIDECAR_REPORT)
        self.assertEqual(report['batches'], len(ranges))
        self.assertFalse((Path(result['path'])/'parts').exists())
        holdout = self.collection('holdout', 70)
        self.write_config('deviations', dict(format=xc.DEVIATIONS_FORMAT, dataset=DS,
                                             records=[dict(id='d1', step='collect-holdout')]))
        with self.assertRaisesRegex(xc.ContractError, 'superseded'):
            xa.sidecar(DS, holdout)


class OutputGuards(Root):
    def test_output_contract(self):
        keys = self.keys_file([3, 6, 9])
        spec = xa._views(DS, 60, 'probe')
        con = xa.sandbox(DS, 60, keys, views=spec)
        try:
            cases = {
                'duplicate keys': 'SELECT user_id, 1.0 AS ag_dd FROM users UNION ALL SELECT user_id, 2.0 FROM users',
                'NULL keys': 'SELECT CAST(NULL AS BIGINT) AS user_id, 1.0 AS ag_nl',
                'must be BIGINT': 'SELECT CAST(user_id AS INTEGER) AS user_id, 1.0 AS ag_ty FROM users',
            }
            for text, sql in cases.items():
                with self.assertRaisesRegex(xa.ProposalError, text):
                    xa.run_proposal(DS, con, spec, dict(USER_N, sql=sql), 60, 20)
            with mock.patch.object(xa, 'MAX_ROWS', 2):
                with self.assertRaisesRegex(xa.ProposalError, 'exceed the limit'):
                    xa.run_proposal(DS, con, spec, USER_N, 60, 20)
        finally:
            xa._close(con)

    def test_nondeterminism_forbidden(self):
        for word in ('uuidv4()', 'uuidv7()', 'nextval(\'s\')', 'currval(\'s\')', 'version()', 'txid_current()',
                     'transaction_timestamp()', 'get_current_timestamp()', 'localtimestamp', 'current_localtimestamp()'):
            with self.assertRaises(xa.ProposalError, msg=word):
                xa.check_sql(DS, f'SELECT user_id, {word} AS ag_x FROM users', 'user')


class ProbeGuards(Root):
    def setUp(self):
        super().setUp()
        self.probe_dir = self.probe()

    def test_min_non_null(self):
        sql = ('SELECT user_id, CAST(user_id AS DOUBLE) AS ag_few FROM users WHERE user_id IN '
               '(SELECT min(user_id) FROM users UNION ALL SELECT max(user_id) FROM users)')
        record, _ = xa.evaluate_proposal(DS, self.probe_dir, dict(USER_N, sql=sql, id='r1p1', round=1, index=1), [])
        self.assertIn('fewer than 100 non-NULL rows', record['error'])

    def test_probe_file_hash(self):
        (self.probe_dir/xa.STATS_FILE).write_text('{"users": 61}')
        with self.assertRaisesRegex(xc.ContractError, 'Probe file changed'):
            xa.evaluate_proposal(DS, self.probe_dir, dict(USER_N, id='r1p1', round=1, index=1), [])
        with self.assertRaisesRegex(xc.ContractError, 'Probe file changed'):
            xa.run_loop(DS, self.probe_dir, 'run-a')


class PromptGuards(Root):
    def setUp(self):
        super().setUp()
        self.stats = dict(users=60, window_steps=10)
        self.left = dict(pair_user_seconds=90.0, item_seconds=180.0)

    def render(self, history=()):
        return xa.render_prompt(DS, self.stats, self.base, list(history), 1, 6, self.left)

    def test_warning_required(self):
        self.fake.PROMPT_TEMPLATE = self.fake.PROMPT_TEMPLATE.replace(self.fake.WARNING, 'Be careful.')
        with self.assertRaisesRegex(ValueError, 'warning'):
            self.render()

    def test_names(self):
        for extra in ('\nfile: sample_submission', '\nsource: Instamart', '\nбанк Тинькофф', '\nfrom data_train'):
            self.fake.EXTRA = extra
            with self.assertRaisesRegex(ValueError, 'names', msg=extra):
                self.render()
        self.fake.EXTRA = ''
        # raw file names may stand in the template's forbidden list; brands may not
        self.fake.PROMPT_TEMPLATE += '\nForbidden tables: test_users, sample_submission.'
        self.render()
        self.fake.PROMPT_TEMPLATE += '\nData of Kuper (Купер).'
        with self.assertRaisesRegex(ValueError, 'names'):
            self.render()

    def test_agent_words_masked_in_feedback(self):
        record = dict(id='r1p1', name='kaggle_trick', idea='read sample_submission', level='user',
                      sql='SELECT * FROM sample_submission', status='invalid', error='forbidden: sample_submission',
                      seconds=None, rows=None, columns=[])
        prompt = self.render([record])
        self.assertNotIn('sample_submission', prompt)
        self.assertIn('<name>', prompt)


class LeakGuards(Root):
    def setUp(self):
        super().setUp()
        self.collection('train', 50)
        self.collection('holdout', 70)
        self.make_set([USER_N, ITEM_N, PAIR_N])
        self.prereg()

    def test_reviewer_case_refused(self):
        # views(50) lists the partitions of 70 and has no filter: nothing left to inject
        self.fake.FILES_FOR = {50: 70}
        self.fake.LEAKY = True
        with self.assertRaisesRegex(xc.ContractError, 'nothing would be injected'):
            xa.leakcheck(DS, users=20, name='lc')
        report = xc.read_json(xc.output_dir(DS, 'leakcheck', 'lc', 'report.json'))
        self.assertIs(report['ok'], False)
        self.assertEqual(report['status'], 'failed')

    def test_cut_read_alone_catches_wide_partitions(self):
        # views(50) lists the partition [50, 60) but keeps its filter: agent values agree everywhere,
        # only the direct read of the allowed partitions sees rows at or after A
        self.fake.FILES_FOR = {50: 60}
        with self.assertRaisesRegex(ValueError, 'LEAK'):
            xa.leakcheck(DS, users=20, name='lc')
        entry = xc.read_json(xc.output_dir(DS, 'leakcheck', 'lc', 'report.json'))['anchors']['50']
        self.assertGreater(entry['cut_rows_at_or_after_anchor'], 0)
        for key in ('leak_mismatches', 'production_mismatches', 'invariance_mismatches', 'cached_mismatches'):
            self.assertEqual(sum(entry[key].values()), 0, key)
        self.assertEqual(entry['result'], 'LEAK')

    def test_cache_mismatch_alone(self):
        # item tables taken through the cache (shape 'table') differ from the direct runs
        real = xa._execute

        def corrupt(con, spec, level, sql, anchor, timeout_s, shape='pairs'):
            result, names, rows = real(con, spec, level, sql, anchor, timeout_s, shape)
            if shape == 'table' and level == 'item':
                result[names] = result[names] + 1.0
            return result, names, rows
        with mock.patch.object(xa, '_execute', corrupt):
            with self.assertRaisesRegex(ValueError, 'LEAK'):
                xa.leakcheck(DS, users=20, name='lc')
        entry = xc.read_json(xc.output_dir(DS, 'leakcheck', 'lc', 'report.json'))['anchors']['50']
        self.assertGreater(entry['cached_mismatches']['ag_item_n'], 0)
        for key in ('leak_mismatches', 'production_mismatches', 'invariance_mismatches'):
            self.assertEqual(sum(entry[key].values()), 0, key)
        self.assertEqual(entry['cut_rows_at_or_after_anchor'], 0)

    def test_wide_cut_is_leak(self):
        # one extra partition allowed at 50 and no filter: the direct read of the cut finds it
        self.fake.FILES_FOR = {50: 60}
        self.fake.LEAKY = True
        with self.assertRaisesRegex(ValueError, 'LEAK'):
            xa.leakcheck(DS, users=20, name='lc')
        entry = xc.read_json(xc.output_dir(DS, 'leakcheck', 'lc', 'report.json'))['anchors']['50']
        self.assertGreater(entry['cut_rows_at_or_after_anchor'], 0)
        self.assertGreater(entry['injected_rows_at_or_after_anchor'], 0)

    def test_report_fields(self):
        report = xa.leakcheck(DS, users=20, name='lc')
        entry = report['anchors']['50']
        self.assertEqual(entry['time_columns'], ['t'])
        self.assertEqual(entry['cut_rows_at_or_after_anchor'], 0)
        self.assertGreater(entry['injected_rows'], 0)
        self.assertEqual(entry['cached_mismatches'], {'ag_user_n': 0, 'ag_item_n': 0, 'ag_pair_n': 0})
        self.assertEqual(report['result'], 'OK')

    def test_time_columns_and_file_times(self):
        spec = xa._views(DS, 50, 'probe')
        self.assertEqual(xa.time_columns(spec), {'t'})
        self.assertEqual(xa.time_columns(dict(spec, time_columns={'ev': 'ts'})), {'ts'})
        with self.assertRaises(xc.ContractError):
            xa.time_columns(dict(spec, schema={'ev': [['user_id', 'BIGINT']]}))
        cut = xa.file_times(spec['files'], {'t'}, 50)
        self.assertEqual(cut['rows_at_or_after'], 0)
        wide = xa.file_times(xa._views(DS, 70, 'probe')['files'], {'t'}, 50)
        self.assertEqual(wide['rows_at_or_after'], wide['rows']-cut['rows'])

    def test_reroot_refuses_type_change(self):
        spec = xa._views(DS, 50, 'probe')
        future = xa._views(DS, 70, 'probe')['files'][-1]
        frame = xc.read_parquet(future)
        frame['t'] = frame['t'].astype('int64')
        xc.write_parquet(frame, future)
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaisesRegex(xc.ContractError, 'no upcast'):
                xa._reroot(spec, Path(scratch)/'full', [future])


class Cli(unittest.TestCase):
    def test_refuses_without_isolation(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = xa.main(['export', '--dataset', 'tinkoff'])
        self.assertEqual(code, 1)
        line = json.loads(out.getvalue())
        self.assertFalse(line['ok'])
        self.assertIn('python -I', line['error'])

    def test_bad_arguments_are_one_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = xa.main(['export', '--dataset', 'other'])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out.getvalue())['ok'])


if __name__ == '__main__':
    unittest.main()
