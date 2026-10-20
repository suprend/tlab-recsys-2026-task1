"""Synthetic witnesses for the MA arm (scripts/hm_agent_kaggle.py); no real H&M data.

One fixture runs the chain once on the tests.test_hm_kaggle data: verify, EDA,
collections 09-02/09-09/09-16, a history export, a hand-written agent set of
three proposals (pair, customer, article), a clean leakcheck, sidecars, a
prereg, port fits M and MA for both seeds, hm_kaggle score of the control and
score_ma in one chunk and in chunks of 7. Tests compare it with hm_kaggle and
with plain-Python oracles, and doctor copies of its artifacts for the gate.
Until scripts/hm_agent_sandbox.py (agent A) exists, a small stand-in that
honours docs/hm-agent-design.md (1.1, 1.2, 1.4, 3.3, 6) is installed under its
name. Scratch lives in /tmp only.
"""
from collections import Counter, defaultdict
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta
import importlib.util
import io
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

import duckdb

from scripts import hm_eda
from scripts import hm_experiment as experiment
from scripts import hm_kaggle as kaggle
from tests import test_hm_kaggle as base

# Contract stand-in for agent A's module: export layout, barrier t_dat < A, the
# four visible tables, keys + DOUBLE columns, NULL for "no data", article cache.
STAND_IN = r'''
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time

import duckdb

from scripts import hm_experiment as experiment
from scripts import hm_kaggle as kaggle

EXPORT_FORMAT = 'hm-agent-export-v1'


def agent_code_identity(deadline=None):
    code = kaggle.code_identity(deadline)
    for name in ('hm_agent_sandbox.py', 'hm_agent_loop.py', 'hm_agent_kaggle.py', 'hm_result_audit.py'):
        if (kaggle.ROOT/'scripts'/name).is_file():
            code[name] = experiment.sha256_file(kaggle.ROOT/'scripts'/name, deadline)
    return code

SET_FORMAT = 'hm-agent-set-v1'
LEVELS = {'pair': ('customer_id', 'article_id'), 'customer': ('customer_id',), 'article': ('article_id',)}
DOMAINS = {'pair': 'cand', 'customer': 'users', 'article': 'articles'}
VALUE_TYPES = ('BOOLEAN', 'TINYINT', 'SMALLINT', 'INTEGER', 'BIGINT', 'HUGEINT', 'UTINYINT', 'USMALLINT',
               'UINTEGER', 'UBIGINT', 'FLOAT', 'DOUBLE')


class ProposalError(ValueError):
    pass


def export_history(database, output, before=None, threads=4):
    database, output = Path(database).resolve(), kaggle.new_output(output)
    identity = dict(sha256=experiment.sha256_file(database), bytes=database.stat().st_size)
    sources = kaggle.database_sources(database, identity)
    where = '' if before is None else f"WHERE t_dat < DATE '{date.fromisoformat(before).isoformat()}'"
    con = duckdb.connect(str(database), read_only=True, config=dict(threads=threads))
    try:
        con.execute(f"""COPY (SELECT t_dat::DATE AS t_dat, customer_id::VARCHAR AS customer_id,
            article_id::VARCHAR AS article_id, price::DOUBLE AS price, sales_channel_id::VARCHAR AS sales_channel_id,
            strftime(t_dat, '%Y-%m-%d') AS d FROM transactions {where}) TO '{output/'tx'}' (FORMAT PARQUET, PARTITION_BY (d))""")
        (output/'articles').mkdir()
        con.execute(f"""COPY (SELECT article_id, product_code, product_type_no, product_type_name FROM articles)
            TO '{output/'articles/articles.parquet'}' (FORMAT PARQUET)""")
        rows, days, first, last = con.execute(f"""SELECT count(*), count(DISTINCT t_dat), min(t_dat)::VARCHAR,
            max(t_dat)::VARCHAR FROM transactions {where}""").fetchone()
        articles = con.execute('SELECT count(*) FROM articles').fetchone()[0]
    finally:
        con.close()
    files = {p.relative_to(output).as_posix(): dict(sha256=experiment.sha256_file(p))
             for p in sorted((output/'tx').rglob('*.parquet'))}
    record = dict(format=EXPORT_FORMAT, status='completed', before=before, database=identity, sources=sources,
                  tx=dict(rows=rows, days=days, first=first, last=last, files=files),
                  articles=dict(rows=articles, sha256=experiment.sha256_file(output/'articles/articles.parquet')), code={})
    record['digest'] = experiment.canonical_digest(record)
    (output/'export.json').write_text(json.dumps(record), encoding='utf-8')
    return record


def read_export(export):
    export = Path(export)
    record = json.loads((export/'export.json').read_text(encoding='utf-8'))
    if record.get('format') != EXPORT_FORMAT or record.get('status') != 'completed':
        raise ValueError('Completed export required')
    if any(experiment.sha256_file(export/name) != value['sha256'] for name, value in record['tx']['files'].items()):
        raise ValueError('Export bytes changed')
    if experiment.canonical_digest({k: v for k, v in record.items() if k != 'digest'}) != record['digest']:
        raise ValueError('Export digest differs')
    return record


def set_digest(proposals):
    return experiment.canonical_digest([[p['id'], p['level'], p['sql'], p['columns']] for p in proposals])


def read_agent_set(path):
    record = json.loads(Path(path).read_text(encoding='utf-8'))
    if (record.get('format') != SET_FORMAT or record.get('digest') != set_digest(record['proposals']) or
            record['columns'] != [c for p in record['proposals'] for c in p['columns']]):
        raise ValueError('Agent set differs from its digest')
    return record


def sandbox(export, anchor, keys_path, threads=4, memory='4GB'):
    export, anchor = Path(export), date.fromisoformat(str(anchor))
    files = [str(p) for p in sorted((export/'tx').glob('d=*/*.parquet')) if date.fromisoformat(p.parent.name[2:]) < anchor]
    con = duckdb.connect(':memory:', config=dict(threads=threads, memory_limit=memory))
    con.execute(f"""CREATE TABLE tx AS SELECT t_dat, customer_id, article_id, price, sales_channel_id
        FROM read_parquet(?, hive_partitioning=false) WHERE t_dat < DATE '{anchor.isoformat()}'""", [files])
    con.execute("""CREATE TABLE articles AS SELECT * FROM read_parquet(?)
        WHERE article_id IN (SELECT article_id FROM tx)""", [str(export/'articles/articles.parquet')])
    con.execute('CREATE TABLE cand AS SELECT customer_id, article_id FROM read_parquet(?)', [str(keys_path)])
    con.execute('CREATE TABLE users AS SELECT DISTINCT customer_id FROM cand')
    con.execute('SET enable_external_access=false')
    con.execute('SET lock_configuration=true')
    return con


def run_proposal(con, proposal, anchor, timeout_s):
    level, names = list(LEVELS[proposal['level']]), list(proposal['columns'])
    keys, domain = ', '.join(level), DOMAINS[proposal['level']]
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        con.execute('CREATE OR REPLACE TEMP TABLE _x AS '+proposal['sql'].replace('{A}', anchor))
        described = con.execute('DESCRIBE _x').fetchall()
        if [d[0] for d in described] != level+names:
            raise ProposalError(f"{proposal['id']}: keys and columns differ from the contract")
        if (any(d[1] != 'VARCHAR' for d in described[:len(level)]) or
                any(d[1] not in VALUE_TYPES and not d[1].startswith('DECIMAL') for d in described[len(level):])):
            raise ProposalError(f"{proposal['id']}: a key or value type differs from the contract")
        nulls = con.execute(f"SELECT count(*) FROM _x WHERE {' OR '.join(k+' IS NULL' for k in level)}").fetchone()[0]
        repeated = con.execute(f'SELECT count(*) FROM (SELECT {keys} FROM _x GROUP BY ALL HAVING count(*) > 1)').fetchone()[0]
        outside = con.execute(f'SELECT count(*) FROM (SELECT {keys} FROM _x EXCEPT SELECT {keys} FROM {domain})').fetchone()[0]
        if nulls or repeated or outside:
            raise ProposalError(f"{proposal['id']}: keys must be unique, not NULL and within {domain}")
        casts = ''.join(f', CAST({name} AS DOUBLE) AS {name}' for name in names)
        return con.execute(f'SELECT {keys}{casts} FROM _x').fetchdf()
    except duckdb.InterruptException:
        raise ProposalError(f"{proposal['id']}: timeout after {timeout_s} s") from None
    except duckdb.Error as exc:
        raise ProposalError(f"{proposal['id']}: {exc}") from None
    finally:
        timer.cancel()


def agent_columns(export, anchor, keys, agent_set, *, threads=4, timeout_s=900, cache=None, deadline=None):
    agent = agent_set if isinstance(agent_set, dict) else read_agent_set(agent_set)
    digest, anchor = read_export(export)['digest'], date.fromisoformat(str(anchor)).isoformat()
    with tempfile.TemporaryDirectory(prefix='tlab-hm-sbx-') as scratch:
        keys_path = Path(scratch)/'keys.parquet'
        writer = duckdb.connect(':memory:')
        try:
            writer.register('batch_keys', keys[['customer_id', 'article_id']])
            writer.execute(f"COPY (SELECT customer_id, article_id FROM batch_keys) TO '{keys_path}' (FORMAT PARQUET)")
        finally:
            writer.close()
        con = sandbox(export, anchor, keys_path, threads=threads)
        try:
            result = con.execute('SELECT customer_id, article_id FROM cand ORDER BY customer_id, article_id').fetchdf()
            seconds = {}
            for proposal in agent['proposals']:
                if deadline:
                    deadline.check()
                began = time.monotonic()
                key = (digest, anchor, proposal['id'], hashlib.sha256(proposal['sql'].encode('utf-8')).hexdigest())
                if proposal['level'] == 'article' and cache is not None and key in cache:
                    values = cache[key]
                else:
                    values = run_proposal(con, proposal, anchor, timeout_s)
                    if proposal['level'] == 'article' and cache is not None:
                        cache[key] = values
                result = result.merge(values, on=list(LEVELS[proposal['level']]), how='left', validate='many_to_one')
                seconds[proposal['id']] = round(time.monotonic()-began, 3)
        finally:
            con.close()
    return result[['customer_id', 'article_id']+agent['columns']], dict(seconds=seconds)
'''


def install_stand_in():
    import scripts
    module = types.ModuleType('scripts.hm_agent_sandbox', 'Contract stand-in for agent A (tests only)')
    module.__file__ = str(kaggle.ROOT/'scripts/hm_agent_sandbox.py')
    exec(compile(STAND_IN, '<stand-in for scripts/hm_agent_sandbox.py>', 'exec'), module.__dict__)
    sys.modules[module.__name__] = module
    scripts.hm_agent_sandbox = module


STAND_IN_USED = importlib.util.find_spec('scripts.hm_agent_sandbox') is None
if STAND_IN_USED:
    install_stand_in()
from scripts import hm_agent_sandbox as sandbox  # noqa: E402
from scripts import hm_agent_kaggle as agent_kaggle  # noqa: E402

ANCHORS = ('2020-09-02', '2020-09-09', '2020-09-16')
SEEDS = (2026, 2027)
PROPOSALS = [
    dict(id='r1p1', round=1, index=1, name='pair_buys', idea='Earlier purchases of the article by the customer',
         level='pair', columns=['ag_pair_buys'],
         sql='SELECT t.customer_id, t.article_id, count(*) AS ag_pair_buys FROM tx t '
             'JOIN cand c ON c.customer_id = t.customer_id AND c.article_id = t.article_id '
             'GROUP BY t.customer_id, t.article_id'),
    dict(id='r1p2', round=1, index=2, name='customer_month', idea='Purchases and recency of the customer in 28 days',
         level='customer', columns=['ag_cust_n28', 'ag_cust_gap28'],
         sql="SELECT customer_id, count(*) AS ag_cust_n28, date_diff('day', max(t_dat), DATE '{A}') AS ag_cust_gap28 "
             "FROM tx JOIN users USING (customer_id) WHERE t_dat >= DATE '{A}' - INTERVAL 28 DAY GROUP BY customer_id"),
    dict(id='r1p3', round=1, index=3, name='article_week', idea='Buyers and recency of the article in 7 days',
         level='article', columns=['ag_art_buyers7', 'ag_art_gap7'],
         sql="SELECT article_id, count(DISTINCT customer_id) AS ag_art_buyers7, "
             "date_diff('day', max(t_dat), DATE '{A}') AS ag_art_gap7 "
             "FROM tx WHERE t_dat >= DATE '{A}' - INTERVAL 7 DAY GROUP BY article_id"),
]
COLUMNS = [c for p in PROPOSALS for c in p['columns']]
# A cross-customer aggregate over cand (forbidden by 1.4): its value depends on the batch.
BATCH_DEPENDENT = [dict(id='r1p1', round=1, index=1, name='batch_rows', idea='Rows in the batch', level='pair',
                        columns=['ag_batch_rows'],
                        sql='SELECT customer_id, article_id, count(*) OVER () AS ag_batch_rows FROM cand')]


def write_set(path, proposals, export_digest):
    proposals = [dict(p, probe_seconds=0.01) for p in proposals]
    record = dict(format='hm-agent-set-v1',
                  run=dict(id='fixture', model='claude-opus-5-5', rounds=1, proposals_per_round=len(proposals),
                           calls=1, cost_usd=0.0),
                  probe=dict(anchor='2020-09-09', users=24, export_digest=export_digest), proposals=proposals,
                  attempts=[dict(id=p['id'], status='valid', error=None) for p in proposals],
                  columns=[c for p in proposals for c in p['columns']],
                  budget=dict(pair_customer_seconds=0.02, article_seconds=0.01),
                  digest=experiment.canonical_digest([[p['id'], p['level'], p['sql'], p['columns']] for p in proposals]))
    path.write_text(json.dumps(record, indent=2), encoding='utf-8')
    return path


def write_prereg(path, set_path, exported, edit=None):
    agent = sandbox.read_agent_set(set_path)
    record = dict(format='hm-agent-prereg-v1', threads=2,
                  agent_set=dict(sha256=base.sha(set_path), digest=agent['digest'], columns=len(agent['columns'])),
                  export_digest=exported['digest'], database=exported['database'], code=agent_kaggle.code_identity())
    if edit:
        edit(record)
    path.write_text(json.dumps(record), encoding='utf-8')
    return path


def write_deviations(path, prereg, entries, prereg_sha256=None):
    """``entries``: (id, full code map, rebuilt steps) in time order, one hour apart; each names the prereg."""
    record = dict(format='hm-agent-deviations-v1', deviations=[
        dict(id=key, time=f'2026-10-21T{9+n:02d}:00+03:00', reason='fixture: chunk memory',
             prereg_sha256=prereg_sha256 or base.sha(prereg), code=code, rebuilds=rebuilds)
        for n, (key, code, rebuilds) in enumerate(entries)])
    path.write_text(json.dumps(record), encoding='utf-8')
    return path


def edit_json(path, edit):
    value = json.loads(path.read_text(encoding='utf-8'))
    edit(value)
    path.write_text(json.dumps(value), encoding='utf-8')


def resign_plan(directory, edit):
    """Edit a score plan.json and re-sign every chunk receipt with its new SHA-256."""
    edit_json(directory/'plan.json', edit)
    plan_sha256 = base.sha(directory/'plan.json')
    for path in directory.glob('chunk-*.json'):
        edit_json(path, lambda r: r.update(plan_sha256=plan_sha256))


# The rank-1 row of the first customer of a top-12 file.
FIRST_ROW = '"rank"=1 AND customer_id=(SELECT min(customer_id) FROM read_parquet($1))'


def edit_top12(directory, filename, expression):
    """Rewrite one top-12 file with ``score`` := expression, then re-sign it in its chunk receipt."""
    target, edited = directory/filename, directory/'edited.parquet'
    con = duckdb.connect(config=dict(threads=2))
    try:
        con.execute(f'''COPY (SELECT customer_id,article_id,"rank",{expression} AS score FROM read_parquet($1)
            ORDER BY customer_id,"rank") TO '{edited}' (FORMAT PARQUET)''', [str(target)])
    finally:
        con.close()
    edited.replace(target)
    chunk = int(filename.rsplit('-', 1)[1].split('.')[0])
    edit_json(directory/f'chunk-{chunk:04d}.json', lambda r: r['files'][filename].update(sha256=base.sha(target)))


def numbers(value):
    """Every number inside a JSON value."""
    if isinstance(value, dict):
        for item in value.values():
            yield from numbers(item)
    elif isinstance(value, list):
        for item in value:
            yield from numbers(item)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield value


def shifted(real):
    """The planted leak: the sandbox barrier moved from t_dat < A to t_dat <= A."""
    def leaky(export, anchor, keys_path, *args, **kwargs):
        day = date.fromisoformat(str(anchor))+timedelta(days=1)
        return real(export, day.isoformat() if isinstance(anchor, str) else day, keys_path, *args, **kwargs)
    return leaky


def run_main(argv, **patches):
    """hm_agent_kaggle.main with stdout captured; patches apply to hm_kaggle."""
    out = io.StringIO()
    with ExitStack() as stack:
        for name, value in patches.items():
            stack.enter_context(mock.patch.object(kaggle, name, value))
        stack.enter_context(redirect_stdout(out))
        stack.enter_context(redirect_stderr(io.StringIO()))
        code = agent_kaggle.main(argv)
    return code, out.getvalue().splitlines()


def same(left, right):
    """Rows equal with NULL == NULL and NaN == NaN."""
    def norm(value):
        return None if isinstance(value, float) and math.isnan(value) else value
    return [tuple(map(norm, row)) for row in left] == [tuple(map(norm, row)) for row in right]


class HmAgentKaggleTests(unittest.TestCase):
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
        cls.tmp = Path(cls.stack.enter_context(tempfile.TemporaryDirectory(prefix='tlab-hm-agent-kaggle-', dir='/tmp')))
        cls.artifacts = cls.tmp/'artifacts'
        cls.artifacts.mkdir()
        cls.rows = base.purchases()
        raw = cls.tmp/'raw'
        base.write_tables(raw, cls.rows)
        config = base.write_config(cls.tmp/'hm-source.json', raw)
        connection_for = experiment.connection_for

        def two_threads(database, output):
            con = connection_for(database, output)
            con.execute('SET threads=2')
            return con

        def small_recipe(arm, seed, threads=4):
            recipe = base.LOCKED_RECIPE(arm, seed, threads)
            recipe['hyperparameters'].update(iterations=25, depth=4)
            recipe['train_users'] = 20
            return recipe
        counts = dict(transactions=len(cls.rows), customers=len(base.CUSTOMERS), articles=len(base.ARTICLES))
        cls.stack.enter_context(mock.patch.dict(hm_eda.EXPECTED_ROWS, counts))
        patches = [(kaggle, 'ARTIFACTS', cls.artifacts), (kaggle, 'SOURCE_SHA256', base.sha(config)),
                   (kaggle, 'isolated', lambda: True), (kaggle, 'EDA_FREE_BYTES', 10*1024**3),
                   (experiment, 'connection_for', two_threads), (kaggle, 'locked_recipe', small_recipe)]
        for target, name, value in patches:
            cls.stack.enter_context(mock.patch.object(target, name, value))
        kaggle.verify(raw, config)
        cls.database = Path(kaggle.eda(raw, cls.artifacts/'eda')['database_path'])
        cls.collections = {anchor: cls.artifacts/'collections'/anchor for anchor in ANCHORS}
        cls.manifests = {anchor: kaggle.collect(cls.database, path, anchor, 1000) for anchor, path in cls.collections.items()}
        cls.agent = cls.artifacts/'hm-agent'
        cls.export = cls.agent/'export'
        cls.exported = sandbox.export_history(cls.database, cls.export, threads=2)
        cls.set_path = write_set(cls.tmp/'hm-agent-set.json', PROPOSALS, cls.exported['digest'])
        cls.batch_set = write_set(cls.tmp/'hm-agent-set-batch.json', BATCH_DEPENDENT, cls.exported['digest'])
        cls.leak_collections = [cls.collections['2020-09-02'], cls.collections['2020-09-16']]
        cls.leak_users = cls.manifests['2020-09-02']['population']['selected_queries']
        # The fixture chain: three sidecar anchors, port = train 09-02/09-09 + validation 09-16,
        # final = train 09-09/09-16 without validation.
        for name, value in (('SIDECAR_ANCHORS', ANCHORS), ('PORT_TRAIN_ANCHORS', ANCHORS[:2]),
                            ('PORT_VALIDATION_ANCHOR', ANCHORS[2]), ('FINAL_TRAIN_ANCHORS', ANCHORS[1:]), ('LEAKCHECK_ANCHORS', ('2020-09-02', '2020-09-16')),
                            ('LEAKCHECK_USERS', cls.leak_users)):
            cls.stack.enter_context(mock.patch.object(agent_kaggle, name, value))
        cls.leak = agent_kaggle.leakcheck(cls.database, cls.export, cls.set_path, cls.leak_collections,
                                          cls.agent/'leakcheck', users=cls.leak_users)
        cls.sidecar_root = cls.agent/'sidecars'
        cls.sidecars = {anchor: agent_kaggle.sidecar(cls.database, cls.export, cls.set_path, path,
                                                     cls.sidecar_root/anchor, threads=2)
                        for anchor, path in cls.collections.items()}
        cls.prereg = write_prereg(cls.tmp/'hm-agent-prereg.json', cls.set_path, cls.exported)
        c = [cls.collections[anchor] for anchor in ANCHORS]
        cls.port = cls.agent/'port'
        with redirect_stderr(io.StringIO()):
            cls.m = {seed: kaggle.fit('M', seed, c[:2], cls.port/f'M{seed}', validation_path=c[2], threads=2)
                     for seed in SEEDS}
            cls.ma = {seed: agent_kaggle.fit_ma(seed, c[:2], cls.sidecar_root, cls.prereg, cls.port/f'MA{seed}',
                                                validation_path=c[2], threads=2) for seed in SEEDS}
            cls.kaggle_scores = cls.agent/'score-m'
            kaggle.score(cls.database, [cls.port/'M2026'], cls.kaggle_scores, chunk_users=1000, threads=2)
            cls.final = {seed: agent_kaggle.fit_ma(seed, c[1:], cls.sidecar_root, cls.prereg, cls.agent/f'final/MA{seed}',
                                                   threads=2) for seed in SEEDS}
            cls.fits = [cls.agent/'final/MA2026', cls.agent/'final/MA2027']
            cls.whole = agent_kaggle.score_ma(cls.database, cls.export, cls.set_path, cls.fits, cls.port/'M2026',
                                              cls.agent/'score-whole', chunk_users=1000, threads=2)
            cls.chunked = agent_kaggle.score_ma(cls.database, cls.export, cls.set_path, cls.fits, cls.port/'M2026',
                                                cls.agent/'score-chunked', chunk_users=7, threads=2)

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def query(self, sql, params=()):
        con = duckdb.connect(config=dict(threads=2, temp_directory=str(self.tmp/'duckdb-test-temp')))
        try:
            return con.execute(sql, list(params)).fetchall()
        finally:
            con.close()

    def eligible(self, anchor):
        return {u for d, u, _ in self.rows if anchor-timedelta(days=90) <= d < anchor}

    def oracle(self, anchor, keys):
        """PROPOSALS in plain Python on purchases before ``anchor``; None is NULL."""
        cutoff = date.fromisoformat(anchor)
        pair, n28, last28, buyers7, last7 = Counter(), Counter(), {}, defaultdict(set), {}
        for d, u, a in self.rows:
            if d >= cutoff:
                continue
            pair[u, a] += 1
            if d >= cutoff-timedelta(days=28):
                n28[u] += 1
                last28[u] = max(last28.get(u, d), d)
            if d >= cutoff-timedelta(days=7):
                buyers7[a].add(u)
                last7[a] = max(last7.get(a, d), d)
        return [(u, a, pair.get((u, a)), n28.get(u), (cutoff-last28[u]).days if u in last28 else None,
                 len(buyers7[a]) if a in buyers7 else None, (cutoff-last7[a]).days if a in last7 else None)
                for u, a in keys]

    def top_rows(self, directory, model):
        files = sorted(str(p) for p in Path(directory).glob(f'top12-{model}-*.parquet'))
        return self.query('SELECT customer_id,article_id,"rank",score FROM read_parquet(?) ORDER BY customer_id,"rank"',
                          [files])

    def receipts(self, name):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.agent/name).glob('chunk-*.json'))]

    def copy(self, source, name, edit=None):
        """A doctored copy of an artifact directory."""
        target = self.agent/'doctored'/name
        shutil.copytree(source, target)
        if edit:
            edit(target)
        return target

    def gate(self, name, **changes):
        inputs = dict(prereg=self.prereg, leakcheck=self.agent/'leakcheck', sidecars=self.sidecar_root,
                      agent_scores=self.agent/'score-chunked', kaggle_scores=self.kaggle_scores,
                      port_fits=[self.port/f'MA{seed}' for seed in SEEDS], model='M2026', deviations=None)
        inputs.update(changes)
        return agent_kaggle.gate(output=self.agent/'gates'/name, **inputs)

    def test_sidecars_hold_every_candidate_key_with_values_of_the_past_only(self):
        agent = sandbox.read_agent_set(self.set_path)
        for anchor, path in self.collections.items():
            with self.subTest(anchor):
                report, manifest = self.sidecars[anchor], self.manifests[anchor]
                directory = self.sidecar_root/anchor
                self.assertEqual((report['format'], report['status'], report['anchor']),
                                 ('hm-agent-sidecar-v1', 'completed', anchor))
                self.assertEqual(json.loads((directory/'manifest.json').read_text(encoding='utf-8')), report)
                self.assertEqual(report['collection'], dict(
                    manifest_sha256=base.sha(path/'manifest.json'), frame_sha256=manifest['files']['frame.parquet'],
                    qcy_identity=manifest['qcy_identity'], candidate_identity=manifest['candidate_identity'],
                    database=self.exported['database']))
                self.assertEqual(report['agent_set'], dict(digest=agent['digest'], sha256=base.sha(self.set_path),
                                                           columns=COLUMNS))
                self.assertEqual(report['export_digest'], self.exported['digest'])
                self.assertEqual(set(report['seconds']), {p['id'] for p in PROPOSALS})
                self.assertEqual((report['code'], report['deviation'], report['deviations_sha256'],
                                  report['deviations_records'], report['deviations_prefix_sha256']),
                                 (agent_kaggle.code_identity(), None, None, 0, None))
                self.assertLess(datetime.fromisoformat(self.leak['finished_at_utc']),
                                datetime.fromisoformat(report['started_at_utc']))
                self.assertIn('hm_result_audit.py', report['code'])
                # The collection is unchanged and keys.parquet carries keys only.
                self.assertEqual(kaggle.read_collection(path, None)['files'], manifest['files'])
                self.assertEqual(self.query('DESCRIBE SELECT * FROM read_parquet(?)', [str(directory/'keys.parquet')])[0][0],
                                 'customer_id')
                described = self.query('DESCRIBE SELECT * FROM read_parquet(?)', [str(directory/'agent.parquet')])
                self.assertEqual([(d[0], d[1]) for d in described],
                                 [('customer_id', 'VARCHAR'), ('article_id', 'VARCHAR')]+[(c, 'DOUBLE') for c in COLUMNS])
                self.assertEqual(report['files'], {'agent.parquet': base.sha(directory/'agent.parquet')})
                rows = self.query('SELECT * FROM read_parquet(?)', [str(directory/'agent.parquet')])
                keys = self.query('SELECT customer_id,article_id FROM read_parquet(?) ORDER BY customer_id,article_id',
                                  [str(path/'frame.parquet')])
                self.assertEqual([r[:2] for r in rows], keys)
                self.assertEqual(report['keys']['rows'], len(keys))
                self.assertEqual(report['keys']['rows'], manifest['population']['candidate_rows'])
                self.assertTrue(same(rows, self.oracle(anchor, keys)))
                self.assertEqual(report['non_null'], {c: sum(r[2+i] is not None for r in rows) for i, c in enumerate(COLUMNS)})
                # Every column has values; rows without data stay NULL ("no data"), not 0.
                self.assertTrue(all(0 < n <= len(rows) for n in report['non_null'].values()), report['non_null'])
                self.assertLess(report['non_null']['ag_pair_buys'], len(rows))
        # Over the anchors every column has NULLs somewhere (09-09: customers without purchases in 28 days).
        for name in COLUMNS:
            self.assertTrue(any(self.sidecars[a]['non_null'][name] < self.sidecars[a]['keys']['rows'] for a in ANCHORS), name)

    def test_sidecar_refuses_a_cut_export_before_writing(self):
        cut = self.agent/'export-cut'
        sandbox.export_history(self.database, cut, before='2020-09-09', threads=2)
        output = self.agent/'sidecar-cut'
        with self.assertRaisesRegex(ValueError, 'without --before'):
            agent_kaggle.sidecar(self.database, cut, self.set_path, self.collections['2020-09-02'], output, threads=2)
        self.assertFalse(output.exists())

    def test_a_proposal_error_fails_the_whole_sidecar_and_names_the_proposal(self):
        # Customer keys outside users: the OLD_ONLY customers have history but no candidates at 09-09.
        outside = dict(id='r2p4', round=2, index=4, name='all_customers', idea='Purchases of every customer in tx',
                       level='customer', columns=['ag_all_n'],
                       sql='SELECT customer_id, count(*) AS ag_all_n FROM tx GROUP BY customer_id')
        set_path = write_set(self.tmp/'hm-agent-set-outside.json', PROPOSALS+[outside], self.exported['digest'])
        collection, output = self.collections['2020-09-09'], self.agent/'sidecar-outside'
        with self.assertRaises(sandbox.ProposalError):
            agent_kaggle.sidecar(self.database, self.export, set_path, collection, output, threads=2)
        manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((manifest['status'], manifest['proposal'], manifest['error']['type']),
                         ('failed', 'r2p4', 'ProposalError'))
        self.assertNotIn('non_null', manifest)
        self.assertFalse((output/'agent.parquet').exists())
        self.assertEqual(base.leftovers(output), [])
        argv = ['sidecar', '--database', str(self.database), '--export', str(self.export), '--agent-set', str(set_path),
                '--collection', str(collection), '--output', str(self.agent/'sidecar-outside-cli'), '--threads', '2']
        code, lines = run_main(argv)
        self.assertEqual((code, len(lines)), (1, 1))
        printed = json.loads(lines[0])
        self.assertEqual((printed['status'], printed['command'], printed['error_type'], printed['proposal']),
                         ('failed', 'sidecar', 'ProposalError', 'r2p4'))
        # A proposal the set reader refuses (a comment in its SQL) is named as well.
        broken = [dict(p) for p in PROPOSALS]
        broken[1]['sql'] += ' -- a comment'
        broken_set = write_set(self.tmp/'hm-agent-set-comment.json', broken, self.exported['digest'])
        argv = ['sidecar', '--database', str(self.database), '--export', str(self.export), '--agent-set', str(broken_set),
                '--collection', str(collection), '--output', str(self.agent/'sidecar-comment-cli'), '--threads', '2']
        code, lines = run_main(argv)
        printed = json.loads(lines[0])
        self.assertEqual((code, printed['error_type'], printed['proposal']), (1, 'ProposalError', 'r1p2'))
        self.assertFalse((self.agent/'sidecar-comment-cli').exists())

    def test_fit_ma_trains_on_the_rows_of_m_plus_the_agent_block(self):
        recipe = kaggle.locked_recipe('M', 2026, 2)
        for seed in SEEDS:
            with self.subTest(seed):
                m, ma = self.m[seed], self.ma[seed]
                self.assertEqual((ma['format'], ma['status'], ma['arm'], ma['fit_count'], ma['actual_trees']),
                                 ('hm-agent-fit-v1', 'completed', 'MA', 1, 25))
                for key in ('training_populations', 'inputs', 'validation_population', 'database', 'hyperparameters',
                            'training_user_limit', 'negative_sample', 'sampling_seed', 'resolved_checks'):
                    self.assertEqual(ma[key], m[key], key)
                self.assertEqual(ma['features'], dict(m['features'], numeric=recipe['numeric']+COLUMNS))
                self.assertEqual(m['features']['numeric'], recipe['numeric'])
                self.assertEqual(ma['agent'], dict(
                    digest=sandbox.read_agent_set(self.set_path)['digest'], sha256=base.sha(self.set_path),
                    columns=COLUMNS, export_digest=self.exported['digest'],
                    sidecars={a: base.sha(self.sidecar_root/a/'manifest.json') for a in ANCHORS}))
                self.assertEqual((ma['prereg'], ma['deviation']),
                                 (dict(sha256=base.sha(self.prereg), deviations_sha256=None), None))
                self.assertEqual(ma['code'], agent_kaggle.code_identity())
                self.assertEqual(ma['files']['model.cbm'], base.sha(self.port/f'MA{seed}/model.cbm'))
        with self.assertRaisesRegex(ValueError, 'Completed hm_kaggle fit report required'):
            kaggle.load_fit(self.port/'MA2026', None)
        loaded = agent_kaggle.load_agent_fit(self.port/'MA2026', None)
        self.assertEqual((loaded['name'], loaded['columns'], loaded['base_numeric']), ('MA2026', COLUMNS, recipe['numeric']))
        self.assertEqual((loaded['identity']['code'], loaded['identity']['deviation'], loaded['identity']['agent']['sidecars']),
                         (self.ma[2026]['code'], None, self.ma[2026]['agent']['sidecars']))
        self.assertEqual(list(loaded['model'].feature_names_), recipe['numeric']+COLUMNS+recipe['categorical'])
        with self.assertRaisesRegex(ValueError, 'Completed hm_agent MA fit'):
            agent_kaggle.load_agent_fit(self.port/'M2026', None)
        # The anchors the plan carries for the gate: port with validation, final without.
        self.assertEqual(loaded['identity']['anchors'], dict(train=list(ANCHORS[:2]), validation=[ANCHORS[2]]))
        final = agent_kaggle.load_agent_fit(self.agent/'final/MA2026', None)
        self.assertEqual(final['identity']['anchors'], dict(train=list(ANCHORS[1:]), validation=[]))
        # A fit without validation trains on the final anchors only; nothing is written otherwise.
        c = [self.collections[anchor] for anchor in ANCHORS]
        with self.assertRaisesRegex(ValueError, 'A final fit'):
            agent_kaggle.fit_ma(2026, c[:2], self.sidecar_root, self.prereg, self.agent/'final-port-anchors', threads=2)
        self.assertFalse((self.agent/'final-port-anchors').exists())

    def test_ma_validation_scores_equal_an_independent_join_of_the_sidecar(self):
        import numpy as np
        fit = agent_kaggle.load_agent_fit(self.port/'MA2026', None)
        path, anchor = self.collections['2020-09-16'], '2020-09-16'
        con = duckdb.connect(config=dict(threads=2))
        try:
            frame, _, _ = experiment.load_part(con, path, self.manifests[anchor], fit['base_numeric']+fit['categorical'])
            side = con.execute('SELECT * FROM read_parquet(?)', [str(self.sidecar_root/anchor/'agent.parquet')]).fetchdf()
        finally:
            con.close()
        # Shuffled sidecar rows: the block must follow the keys, not the row order.
        side = side.sample(frac=1, random_state=7)
        block = frame[['customer_id', 'article_id']].merge(side, how='left', on=['customer_id', 'article_id'])
        numbers_, cats = experiment.model_arrays(frame, fit['base_numeric'], fit['categorical'])
        numbers_ = np.hstack([numbers_, block[COLUMNS].to_numpy(dtype=np.float32)])
        scores = fit['model'].predict_proba(experiment.model_pool(numbers_, cats, fit['numeric'], fit['categorical']))[:, 1]
        ranked = defaultdict(list)
        for u, a, s in zip(frame['customer_id'], frame['article_id'], scores):
            ranked[u].append((-s, a))
        expected = sorted((u, a, r, -s) for u, items in ranked.items() for r, (s, a) in enumerate(sorted(items)[:12], 1))
        stored = self.query('SELECT customer_id,article_id,"rank",score FROM read_parquet(?) ORDER BY ALL',
                            [str(self.port/'MA2026/predictions-top12.parquet')])
        self.assertEqual(stored, expected)

    def test_fit_ma_refuses_without_a_matching_prereg(self):
        c = [self.collections[anchor] for anchor in ANCHORS]
        output = self.agent/'refused-fit'

        def fit(prereg):
            agent_kaggle.fit_ma(2026, c[:2], self.sidecar_root, prereg, output, validation_path=c[2], threads=2)
        with self.assertRaisesRegex(FileNotFoundError, 'Preregistration'):
            fit(self.tmp/'no-prereg.json')
        cases = [('code', lambda r: r['code'].update({'hm_agent_kaggle.py': '0'*64}), 'Code differs'),
                 ('audit', lambda r: r['code'].pop('hm_result_audit.py'), 'Code differs'),
                 ('set', lambda r: r['agent_set'].update(sha256='0'*64), 'preregistered agent set'),
                 ('export', lambda r: r.update(export_digest='0'*64), 'preregistered agent set'),
                 ('fields', lambda r: r.pop('export_digest'), 'must state'),
                 ('threads', lambda r: r.update(threads=8), 'preregistered threads'),
                 ('no-threads', lambda r: r.pop('threads'), 'preregistered threads')]
        for name, edit, message in cases:
            with self.subTest(name), self.assertRaisesRegex(ValueError, message):
                fit(write_prereg(self.tmp/f'prereg-{name}.json', self.set_path, self.exported, edit))
        self.assertFalse(output.exists())

    def test_deviations_accept_only_the_last_entry_of_this_prereg(self):
        current = agent_kaggle.code_identity()
        old, other = (dict(current, **{'hm_agent_kaggle.py': digit*64}) for digit in 'ab')
        prereg = write_prereg(self.tmp/'prereg-old-code.json', self.set_path, self.exported, lambda r: r.update(code=old))
        # d1 fixed something from the contrast on, d2 the fits: port and every later step.
        last = write_deviations(self.tmp/'deviations-last.json', prereg, [('d1', other, ['contrast']), ('d2', current, ['port'])])
        with self.assertRaisesRegex(ValueError, 'Code differs'):
            agent_kaggle.read_prereg(prereg, None, current)
        accepted = agent_kaggle.read_prereg(prereg, last, current)
        entries = accepted['entries']
        self.assertEqual((accepted['deviation'], accepted['deviations_sha256'], accepted['sha256'], accepted['codes']),
                         ('d2', base.sha(last), base.sha(prereg), [old, other, current]))
        self.assertEqual(agent_kaggle.required_deviations(entries), dict.fromkeys(agent_kaggle.STEPS[2:], 1))
        self.assertIsNone(agent_kaggle.read_prereg(prereg, last, old)['deviation'])
        older = write_deviations(self.tmp/'deviations-older.json', prereg, [('d1', current, ['port']), ('d2', other, ['port'])])
        partial = {'hm_agent_kaggle.py': current['hm_agent_kaggle.py']}
        unordered = write_deviations(self.tmp/'deviations-unordered.json', prereg,
                                     [('d1', other, ['port']), ('d2', current, ['port'])])
        edit_json(unordered, lambda r: r['deviations'][0].update(time='2026-10-21T23:00+03:00'))
        refused = [('older', older, 'Code differs'),
                   ('other-prereg', write_deviations(self.tmp/'deviations-other.json', prereg,
                                                     [('d1', other, ['port']), ('d2', current, ['port'])], '0'*64),
                    'another preregistration'),
                   ('partial', write_deviations(self.tmp/'deviations-partial.json', prereg, [('d1', partial, ['port'])]),
                    'full code map'),
                   ('repeated', write_deviations(self.tmp/'deviations-repeated.json', prereg,
                                                 [('d1', other, ['port']), ('d1', current, ['port'])]), 'unique'),
                   ('unordered', unordered, 'time order'),
                   ('no-rebuilds', write_deviations(self.tmp/'deviations-empty.json', prereg, [('d1', current, [])]),
                    'rebuilds'),
                   ('unknown-step', write_deviations(self.tmp/'deviations-step.json', prereg, [('d1', current, ['submit'])]),
                    'rebuilds')]
        for name, path, message in refused:
            with self.subTest(name), self.assertRaisesRegex(ValueError, message):
                agent_kaggle.read_prereg(prereg, path, current)
        # Every record must name this prereg, not only the first one.
        edit_json(self.tmp/'deviations-other.json', lambda r: r['deviations'][1].update(prereg_sha256=base.sha(prereg)))
        with self.assertRaisesRegex(ValueError, 'another preregistration'):
            agent_kaggle.read_prereg(prereg, self.tmp/'deviations-other.json', current)
        # Steps without a prereg take the latest record for its code; other code runs with a null
        # deviation unless a record rebuilds the step (the gate binds the prereg code).
        for step in ('leakcheck', 'sidecar', 'score', 'control'):
            self.assertEqual(agent_kaggle.current_deviation(last, step), dict(
                deviation='d2', deviations_sha256=base.sha(last), deviations_records=2,
                deviations_prefix_sha256=experiment.canonical_digest(entries)))
            self.assertEqual(agent_kaggle.current_deviation(None, step), dict(
                deviation=None, deviations_sha256=None, deviations_records=0, deviations_prefix_sha256=None))
            if step in ('leakcheck', 'sidecar'):  # ``older`` rebuilds port: score and control are stale
                self.assertEqual({k: agent_kaggle.current_deviation(older, step)[k] for k in ('deviation', 'deviations_records')},
                                 dict(deviation=None, deviations_records=2))
            else:
                with self.assertRaisesRegex(ValueError, f'{step} is stale: deviation d2'):
                    agent_kaggle.current_deviation(older, step)
        runs = ('leakcheck', 'sidecar', 'score', 'control')
        for step in runs:
            stale_file = write_deviations(self.tmp/f'deviations-stale-{step}.json', prereg, [('d1', other, [step])])
            for run in runs:
                with self.subTest(rebuilt=step, run=run):
                    if agent_kaggle.STEPS.index(run) >= agent_kaggle.STEPS.index(step):
                        with self.assertRaisesRegex(ValueError, f'{run} is stale: deviation d1'):
                            agent_kaggle.current_deviation(stale_file, run)
                    else:
                        self.assertIsNone(agent_kaggle.current_deviation(stale_file, run)['deviation'])
        with self.assertRaisesRegex(ValueError, 'sidecar is stale'):
            agent_kaggle.sidecar(self.database, self.export, self.set_path, self.collections['2020-09-02'],
                                 self.agent/'sidecar-stale', threads=2, deviations=self.tmp/'deviations-stale-sidecar.json')
        self.assertFalse((self.agent/'sidecar-stale').exists())
        c = [self.collections[anchor] for anchor in ANCHORS]

        def prereg_code(root):
            for path in root.glob('*/manifest.json'):
                edit_json(path, lambda manifest: manifest.update(code=old))
        # Sidecars built under the prereg code (null deviation).
        sidecars = self.copy(self.sidecar_root, 'sidecars-prereg-code', prereg_code)
        # fit_ma writes nothing for a match with an older entry or for a sidecar a later record rebuilds.
        rebuilt = write_deviations(self.tmp/'deviations-sidecar.json', prereg,
                                   [('d1', other, ['contrast']), ('d2', current, ['sidecar'])])
        for name, path, message in (('older', older, 'Code differs'), ('stale-sidecar', rebuilt, 'stale')):
            with self.subTest(fit=name), self.assertRaisesRegex(ValueError, message):
                agent_kaggle.fit_ma(2026, c[:2], sidecars, prereg, self.agent/f'fit-{name}', validation_path=c[2], threads=2,
                                    deviations=path)
            self.assertFalse((self.agent/f'fit-{name}').exists())
        # The chain rebuilt under d2: port fits, scores, control, contrast.
        dev = self.agent/'deviation'
        port = [dev/f'port/MA{seed}' for seed in SEEDS]
        with redirect_stderr(io.StringIO()):
            fits = {seed: agent_kaggle.fit_ma(seed, c[:2], sidecars, prereg, dev/f'port/MA{seed}',
                                              validation_path=c[2], threads=2, deviations=last) for seed in SEEDS}
            final = [agent_kaggle.fit_ma(seed, c[1:], sidecars, prereg, dev/f'final/MA{seed}', threads=2, deviations=last)
                     for seed in SEEDS]
            self.assertEqual([f['deviation'] for f in final], ['d2', 'd2'])
            scored = agent_kaggle.score_ma(self.database, self.export, self.set_path,
                                           [dev/f'final/MA{seed}' for seed in SEEDS], self.port/'M2026', dev/'score',
                                           chunk_users=1000, threads=2, deviations=last)
        fields = agent_kaggle.current_deviation(last, 'score')
        for seed in SEEDS:
            fit = fits[seed]
            self.assertEqual(json.loads((dev/f'port/MA{seed}/report.json').read_text(encoding='utf-8')), fit)
            self.assertEqual((fit['status'], fit['prereg']),
                             ('completed', dict(sha256=base.sha(prereg), deviations_sha256=base.sha(last))))
            self.assertEqual({k: fit[k] for k in fields}, fields)
        plan = json.loads((dev/'score/plan.json').read_text(encoding='utf-8'))
        self.assertEqual(({k: plan[k] for k in fields}, scored['deviation'], [m.get('deviation') for m in plan['models']]),
                         (fields, 'd2', [None, 'd2', 'd2']))
        checked = agent_kaggle.control(dev/'score', self.kaggle_scores, 'M2026', last)
        self.assertEqual((checked['result'], checked['deviation']), ('OK', 'd2'))
        refs = [self.port/f'M{seed}' for seed in SEEDS]
        contrast = agent_kaggle.contrast(refs, port, prereg, self.agent/'contrast-deviation.json', deviations=last)
        self.assertEqual((contrast['deviation'], contrast['prereg']),
                         ('d2', dict(sha256=base.sha(prereg), deviations_sha256=base.sha(last))))
        # Alternatives a later record rebuilds are refused by the contrast.
        with self.assertRaisesRegex(ValueError, 'stale'):
            agent_kaggle.contrast(refs, [self.port/f'MA{seed}' for seed in SEEDS], prereg,
                                  self.agent/'contrast-stale.json', deviations=last)
        # Gate: sidecars of the prereg code, leakcheck of the current code (both null), port/final/score under d2: OK.
        inputs = dict(prereg=prereg, deviations=last, sidecars=sidecars, agent_scores=dev/'score', port_fits=port)
        result = self.gate('deviation', **inputs)
        self.assertEqual((result['result'], result['deviation'], result['prereg']),
                         ('OK', 'd2', dict(sha256=base.sha(prereg), deviations_sha256=base.sha(last))))
        prereg_check = result['checks']['prereg']
        self.assertEqual((prereg_check['unregistered_code'], prereg_check['stale_deviation'], prereg_check['rebuilt'],
                          prereg_check['deviation_problems'], prereg_check['sidecar_binding'], prereg_check['code_binding']),
                         ([], [], dict.fromkeys(agent_kaggle.STEPS[2:], 'd2'), [], [], []))
        # Code bound to the record an artifact names: d2 with d1's code; null under the file with non-prereg code.
        file_fields = dict(deviation=None, deviations_sha256=base.sha(last), deviations_records=2,
                           deviations_prefix_sha256=experiment.canonical_digest(entries))
        d2_other = self.copy(port[0], 'port-d2-other-code', lambda d: edit_json(d/'report.json', lambda r: r.update(code=other)))
        null_current = self.copy(port[0], 'port-null-current-code',
                                 lambda d: edit_json(d/'report.json', lambda r: r.update(file_fields)))
        for name, fit, problem, stale in (
                ('d2-other-code', d2_other, "its code is not the code of deviation 'd2'", []),
                ('null-current-code', null_current,
                 'its deviation is null under a deviations file, but its code is not the prereg code', ['port'])):
            with self.subTest(code=name):
                result = self.gate(f'deviation-{name}', **dict(inputs, port_fits=[fit, port[1]]))
                self.assertEqual([k for k, v in result['checks'].items() if v['result'] != 'OK'], ['prereg'])
                check = result['checks']['prereg']
                self.assertEqual((check['code_binding'], check['unregistered_code'], check['deviation_problems']),
                                 ([dict(path=str((fit/'report.json').resolve()), problem=problem)], [], []))
                self.assertEqual([s['step'] for s in check['stale_deviation']], stale)
        # A rebuilt step, or a later one, that carries null or an older record: FAIL with the artifact path.
        none = dict(deviation=None, deviations_sha256=None, deviations_records=0, deviations_prefix_sha256=None)
        d1 = dict(deviation='d1', deviations_sha256='1'*64, deviations_records=1,
                  deviations_prefix_sha256=experiment.canonical_digest(entries[:1]))
        null_port = self.copy(port[0], 'port-null', lambda d: edit_json(d/'report.json', lambda r: r.update(none)))
        older_port = self.copy(port[0], 'port-d1', lambda d: edit_json(d/'report.json', lambda r: r.update(d1)))
        null_score = self.copy(dev/'score', 'score-null', lambda d: resign_plan(d, lambda p: p.update(none)))
        plan_path = str((null_score/'plan.json').resolve())
        cases = [('null-port', dict(port_fits=[null_port, port[1]]), [(str((null_port/'report.json').resolve()), 'port', None)]),
                 ('older-port', dict(port_fits=[older_port, port[1]]), [(str((older_port/'report.json').resolve()), 'port', 'd1')]),
                 ('null-score', dict(agent_scores=null_score), [(plan_path, 'score', None)])]
        for name, changes, stale in cases:
            with self.subTest(name):
                result = self.gate(f'deviation-{name}', **dict(inputs, **changes))
                self.assertEqual((result['result'], [k for k, v in result['checks'].items() if v['result'] != 'OK']),
                                 ('FAIL', ['prereg']))
                found = result['checks']['prereg']['stale_deviation']
                self.assertEqual([(s['path'], s['step'], s['deviation']) for s in found], stale)
                self.assertEqual({s['required'] for s in found}, {'d2'})
                self.assertEqual(result['checks']['prereg']['deviation_problems'], [])
        # The last record rebuilds only control and the gate runs on the prereg code: its own control is stale.
        control_file = write_deviations(self.tmp/'deviations-control.json', self.prereg,
                                        [('d1', other, ['control'])])
        result = self.gate('deviation-control', deviations=control_file)
        self.assertEqual([k for k, v in result['checks'].items() if v['result'] != 'OK'], ['prereg'])
        self.assertEqual((result['deviation'], result['checks']['prereg']['stale_deviation']),
                         (None, [dict(path='gate (control)', step='control', deviation=None, required='d1')]))
        # A deviations file that is not the one the artifacts grew from: every d2 artifact is named.
        rewritten = write_deviations(self.tmp/'deviations-rewritten.json', prereg,
                                     [('d1', other, ['score']), ('d2', current, ['port'])])
        result = self.gate('deviation-rewritten', **dict(inputs, deviations=rewritten))
        self.assertEqual([k for k, v in result['checks'].items() if v['result'] != 'OK'], ['prereg'])
        named = [p['path'] for p in result['checks']['prereg']['deviation_problems']]
        self.assertEqual(len(named), 2+1+2, named)
        # Without the deviations file the current code itself is refused.
        result = self.gate('deviation-missing', **dict(inputs, deviations=None))
        self.assertEqual([name for name, check in result['checks'].items() if check['result'] != 'OK'], ['prereg'])

    def test_chunked_scoring_equals_unchunked(self):
        users = len(self.eligible(kaggle.SCORE_ANCHOR))
        self.assertEqual((self.whole['users'], self.chunked['users']), (users, users))
        self.assertEqual((self.whole['chunks'], self.chunked['chunks']), (1, math.ceil(users/7)))
        self.assertEqual((self.whole['format'], self.whole['status']), ('hm-agent-score-v1', 'completed'))
        for model in ('M2026', 'MA2026', 'MA2027'):
            with self.subTest(model):
                whole = self.top_rows(self.agent/'score-whole', model)
                self.assertEqual(self.top_rows(self.agent/'score-chunked', model), whole)
                self.assertEqual(len(whole), 12*users)
                self.assertEqual({row[0] for row in whole}, self.eligible(kaggle.SCORE_ANCHOR))
        self.assertNotEqual([r[3] for r in self.top_rows(self.agent/'score-whole', 'MA2026')],
                            [r[3] for r in self.top_rows(self.agent/'score-whole', 'M2026')])
        plan = json.loads((self.agent/'score-chunked/plan.json').read_text(encoding='utf-8'))
        reference = json.loads((self.kaggle_scores/'plan.json').read_text(encoding='utf-8'))
        self.assertEqual(plan['format'], kaggle.PLAN_FORMAT)
        self.assertEqual(set(plan), set(reference) | {'agent', 'deviation', 'deviations_sha256', 'deviations_records',
                                                      'deviations_prefix_sha256'})
        self.assertEqual((plan['deviation'], [m.get('deviation') for m in plan['models']]), (None, [None, None, None]))
        self.assertEqual(plan['agent'], dict(digest=sandbox.read_agent_set(self.set_path)['digest'],
                                             sha256=base.sha(self.set_path), export_digest=self.exported['digest'],
                                             columns=COLUMNS))
        self.assertEqual([m['name'] for m in plan['models']], ['M2026', 'MA2026', 'MA2027'])
        self.assertEqual(plan['models'][0], reference['models'][0])
        self.assertEqual([m['code'] for m in plan['models'][1:]], [self.ma[seed]['code'] for seed in SEEDS])
        for key in ('users_digest', 'items_digest', 'database', 'sources', 'feature_digest', 'users'):
            self.assertEqual(plan[key], reference[key], key)
        receipt = json.loads((self.agent/'score-chunked/chunk-0000.json').read_text(encoding='utf-8'))
        self.assertEqual((receipt['format'], receipt['users'], receipt['candidate_rows']), (kaggle.CHUNK_FORMAT, 7, 7*120))
        self.assertGreaterEqual(receipt['agent_seconds'], 0)
        # Counts for the gate: every candidate scored by every model, finite; agent non-NULL per column.
        totals = {}
        for name in ('score-whole', 'score-chunked'):
            for r in self.receipts(name):
                self.assertEqual(r['models'], {m: dict(rows=r['candidate_rows'], nonfinite_scores=0)
                                               for m in ('M2026', 'MA2026', 'MA2027')})
                self.assertEqual((r['agent_rows'], list(r['agent_non_null'])), (r['candidate_rows'], COLUMNS))
            totals[name] = {c: sum(r['agent_non_null'][c] for r in self.receipts(name)) for c in COLUMNS}
        self.assertEqual(totals['score-chunked'], totals['score-whole'])
        # One article cache per run: the article proposal is computed in the first chunk only.
        self.assertEqual([r['agent_cached'] for r in self.receipts('score-chunked')],
                         [[]]+[['r1p3']]*(self.chunked['chunks']-1))
        self.assertEqual([r['agent_cached'] for r in self.receipts('score-whole')], [[]])
        self.assertTrue(all(0 < n < 120*users for n in totals['score-whole'].values()), totals)
        for name in ('score-whole', 'score-chunked', 'score-m', 'port', 'sidecars'):
            self.assertEqual(base.leftovers(self.agent/name), [], name)

    def test_control_is_ok_and_assemble_accepts_ma(self):
        for name in ('score-whole', 'score-chunked'):
            with self.subTest(name):
                result = agent_kaggle.control(self.agent/name, self.kaggle_scores, 'M2026')
                rows = 12*self.whole['users']
                self.assertEqual(result, dict(
                    model='M2026', agent=dict(rows=rows, customers=self.whole['users'], duplicate_keys=0),
                    kaggle=dict(rows=rows, customers=self.whole['users'], duplicate_keys=0), only_agent=0, only_kaggle=0,
                    article_mismatches=0, score_mismatches=0, max_abs_score_difference=0.0, tolerance=1e-9, deviation=None,
                    deviations_sha256=None, deviations_records=0, deviations_prefix_sha256=None, result='OK'))
        # One control score moved by 1e-6, its receipt re-signed: DIFF.
        broken = self.copy(self.agent/'score-chunked', 'control-diff', lambda d: edit_top12(
            d, 'top12-M2026-0001.parquet', f'score+CASE WHEN {FIRST_ROW} THEN 1e-6 ELSE 0 END'))
        result = agent_kaggle.control(broken, self.kaggle_scores, 'M2026')
        self.assertEqual((result['result'], result['score_mismatches'], result['article_mismatches']), ('DIFF', 1, 0))
        with self.assertRaisesRegex(ValueError, 'hm_kaggle score run'):
            agent_kaggle.control(self.kaggle_scores, self.agent/'score-whole', 'M2026')
        with self.assertRaisesRegex(ValueError, 'does not contain'):
            agent_kaggle.control(self.agent/'score-whole', self.kaggle_scores, 'MA2026')
        # The unchanged hm_kaggle assemble reads score_ma output; its control file is byte-equal to hm_kaggle's.
        submissions = self.agent/'submissions'
        ma = kaggle.assemble(self.database, self.agent/'score-chunked', 'MA2026', submissions/'MA2026.csv.gz',
                             expected_customers=len(base.CUSTOMERS))
        self.assertEqual((ma['model'], ma['rows'], ma['model_customers']), ('MA2026', len(base.CUSTOMERS), self.whole['users']))
        control = [kaggle.assemble(self.database, scores, 'M2026', submissions/f'M2026-{name}.csv.gz',
                                   expected_customers=len(base.CUSTOMERS))
                   for name, scores in (('agent', self.agent/'score-whole'), ('kaggle', self.kaggle_scores))]
        self.assertEqual(control[0]['file']['sha256'], control[1]['file']['sha256'])
        self.assertNotEqual(ma['file']['sha256'], control[0]['file']['sha256'])

    def test_score_ma_resumes_finished_chunks_and_refuses_changed_plan(self):
        directory = self.agent/'score-resume'
        shutil.copytree(self.agent/'score-chunked', directory)
        before = {p.name: base.sha(p) for p in directory.glob('top12-*.parquet')}

        def score(chunk_users=7, threads=2, agent_set=None):
            return agent_kaggle.score_ma(self.database, self.export, agent_set or self.set_path, self.fits,
                                         self.port/'M2026', directory, chunk_users=chunk_users, threads=threads)
        with redirect_stderr(io.StringIO()):
            again = score()
            self.assertEqual((again['computed'], again['skipped']), (0, self.chunked['chunks']))
            (directory/'chunk-0002.json').unlink()
            (directory/'top12-MA2026-0002.parquet').unlink()
            again = score()
        self.assertEqual((again['computed'], again['skipped']), (1, self.chunked['chunks']-1))
        self.assertEqual({p.name: base.sha(p) for p in directory.glob('top12-*.parquet')}, before)
        plan, report = base.sha(directory/'plan.json'), base.sha(directory/'report.json')
        for chunk_users, threads in ((8, 2), (7, 1)):
            with self.subTest(chunk_users=chunk_users, threads=threads), redirect_stderr(io.StringIO()), \
                    self.assertRaisesRegex(ValueError, 'plan differs'):
                score(chunk_users, threads)
        # Fits of another agent set are refused before anything is read from the export.
        with self.assertRaisesRegex(ValueError, 'plus this agent set'):
            score(agent_set=self.batch_set)
        self.assertEqual((base.sha(directory/'plan.json'), base.sha(directory/'report.json')), (plan, report))
        self.assertEqual(base.leftovers(directory), [])

    def test_score_ma_fails_on_a_proposal_error_and_resume_recomputes_its_chunk(self):
        source, directory = self.agent/'score-chunked', self.agent/'score-proposal-error'
        shutil.copytree(source, directory)
        for chunk in (3, 4):
            (directory/f'chunk-{chunk:04d}.json').unlink()
            for path in directory.glob(f'top12-*-{chunk:04d}.parquet'):
                path.unlink()

        def score():
            return agent_kaggle.score_ma(self.database, self.export, self.set_path, self.fits, self.port/'M2026',
                                         directory, chunk_users=7, threads=2)
        planted = sandbox.ProposalError('r1p3: article key outside articles (planted)')
        with redirect_stderr(io.StringIO()), mock.patch.object(sandbox, 'agent_columns', side_effect=planted), \
                self.assertRaises(sandbox.ProposalError):
            score()
        report = json.loads((directory/'report.json').read_text(encoding='utf-8'))
        self.assertEqual((report['status'], report['proposal'], report['error']['type'], report['computed'],
                          report['skipped']), ('failed', 'r1p3', 'ProposalError', 0, 3))
        self.assertFalse((directory/'chunk-0003.json').exists())
        self.assertEqual(list(directory.glob('top12-*-0003.parquet')), [])
        # After the (technical) fix the same plan resumes and recomputes exactly the failed chunks.
        with redirect_stderr(io.StringIO()):
            again = score()
        self.assertEqual((again['status'], again['computed'], again['skipped']), ('completed', 2, self.chunked['chunks']-2))
        self.assertEqual({p.name: base.sha(p) for p in directory.glob('top12-*.parquet')},
                         {p.name: base.sha(p) for p in source.glob('top12-*.parquet')})
        for chunk in (3, 4):
            new, old = (json.loads((d/f'chunk-{chunk:04d}.json').read_text(encoding='utf-8')) for d in (directory, source))
            for key in ('files', 'models', 'agent_rows', 'agent_non_null', 'users_digest', 'candidate_rows'):
                self.assertEqual(new[key], old[key], key)
        self.assertEqual(base.leftovers(directory), [])

    def test_score_ma_interrupted_after_the_deadline_reports_the_wall_limit(self):
        real, made = experiment.Deadline, []

        def recording(seconds):
            made.append(real(seconds))
            return made[-1]

        def interrupted(con, *args, **kwargs):
            deadline = made[-1]
            deadline.expires = time.monotonic()+0.3
            timer = deadline.interrupt_sql(con)
            try:
                con.execute(base.ENDLESS).fetchone()
            finally:
                timer.cancel()
        output = self.agent/'score-timeout'
        argv = ['score', '--database', str(self.database), '--export', str(self.export), '--agent-set', str(self.set_path),
                '--fits', str(self.fits[0]), '--control', str(self.port/'M2026'), '--output', str(output),
                '--chunk-users', '7', '--threads', '2']
        with mock.patch.object(experiment, 'Deadline', recording), mock.patch.object(kaggle, 'create_item_ranks', interrupted):
            code, lines = run_main(argv)
        self.assertEqual((code, len(lines)), (1, 1))
        self.assertEqual(json.loads(lines[0]), dict(base.WALL, command='score'))
        error = json.loads((output/'report.json').read_text(encoding='utf-8'))['error']
        self.assertEqual((error['type'], error['cause']), ('TimeoutError', 'InterruptException'))
        self.assertFalse((output/'plan.json').exists())

    def test_leakcheck_passes_and_catches_a_planted_leak_and_batch_dependence(self):
        users = self.leak_users
        self.assertEqual(users, self.manifests['2020-09-16']['population']['selected_queries'])

        def run(name, agent_set=None, collections=None):
            return agent_kaggle.leakcheck(self.database, self.export, agent_set or self.set_path,
                                          collections or self.leak_collections, self.agent/name, users=users)
        clean = self.leak
        self.assertEqual((clean['format'], clean['status'], clean['result']), ('hm-agent-leakcheck-v1', 'completed', 'OK'))
        self.assertEqual(sorted(clean['anchors']), ['2020-09-02', '2020-09-16'])
        for anchor, item in clean['anchors'].items():
            self.assertEqual((item['customers'], item['rows'], item['columns'], item['invariance_batches'], item['result']),
                             (users, 120*users, len(COLUMNS), 4, 'OK'))
            self.assertEqual(item['leak_mismatches'], dict.fromkeys(COLUMNS, 0))
            self.assertEqual(item['invariance_mismatches'], dict.fromkeys(COLUMNS, 0))
        with mock.patch.object(sandbox, 'sandbox', shifted(sandbox.sandbox)):
            leaky = run('leakcheck-leak')
            # An article-level proposal alone: its values are computed without cache on both exports.
            article = write_set(self.tmp/'hm-agent-set-article.json', PROPOSALS[2:], self.exported['digest'])
            article_only = run('leakcheck-article', article, self.leak_collections[1:])
        self.assertEqual(leaky['result'], 'LEAK')
        for anchor, item in leaky['anchors'].items():
            with self.subTest(anchor):
                # Two background customers buy on every day, also on the anchor itself.
                self.assertEqual(item['result'], 'LEAK')
                for name in ('ag_cust_n28', 'ag_cust_gap28', 'ag_art_buyers7', 'ag_art_gap7'):
                    self.assertGreater(item['leak_mismatches'][name], 0, name)
                self.assertEqual(item['invariance_mismatches'], dict.fromkeys(COLUMNS, 0))
        self.assertEqual(article_only['result'], 'LEAK')
        item = article_only['anchors']['2020-09-16']
        self.assertTrue(all(item['leak_mismatches'][name] > 0 for name in ('ag_art_buyers7', 'ag_art_gap7')), item)
        batch = run('leakcheck-batch', self.batch_set)
        self.assertEqual(batch['result'], 'LEAK')
        for anchor, item in batch['anchors'].items():
            self.assertEqual((item['leak_mismatches'], item['invariance_mismatches']),
                             (dict(ag_batch_rows=0), dict(ag_batch_rows=120*users)))
        # Counts only: no customer ID reaches a report, and the cut exports are gone.
        for name in ('leakcheck', 'leakcheck-leak', 'leakcheck-article', 'leakcheck-batch'):
            text = (self.agent/name/'report.json').read_text(encoding='utf-8')
            self.assertFalse(any(u in text for u in base.CUSTOMERS), name)
            self.assertEqual(sorted(p.name for p in (self.agent/name).iterdir()), ['duckdb-temp', 'report.json'], name)

    def test_contrast_pairs_seeds_and_records_the_prereg(self):
        output = self.agent/'dev-contrast.json'
        refs, alts = [self.port/f'M{s}' for s in SEEDS], [self.port/f'MA{s}' for s in SEEDS]
        result = agent_kaggle.contrast(refs, alts, self.prereg, output)
        maps = {f'{arm}{s}': fits[s]['validation_metrics']['map_at_12_conditional']
                for arm, fits in (('M', self.m), ('MA', self.ma)) for s in SEEDS}
        positive = self.m[2026]['validation_metrics']['positive_queries']
        self.assertEqual(result['map_by_fit'], maps)
        self.assertEqual(result['delta_by_seed'], {str(s): maps[f'MA{s}']-maps[f'M{s}'] for s in SEEDS})
        self.assertEqual((result['positive_queries'], result['bootstrap']['queries'], result['bootstrap']['draws']),
                         (positive, positive, 2000))
        self.assertAlmostEqual(result['mean_map']['reference'], sum(maps[f'M{s}'] for s in SEEDS)/2, places=12)
        self.assertAlmostEqual(result['mean_map']['alternative'], sum(maps[f'MA{s}'] for s in SEEDS)/2, places=12)
        self.assertAlmostEqual(result['bootstrap']['mean_delta'],
                               result['mean_map']['alternative']-result['mean_map']['reference'], places=12)
        self.assertEqual((result['prereg'], result['deviation'], result['deviations_records']),
                         (dict(sha256=base.sha(self.prereg), deviations_sha256=None), None, 0))
        self.assertNotIn('gate', result)
        self.assertEqual(result['code'], agent_kaggle.code_identity())
        self.assertEqual(json.loads(output.read_text(encoding='utf-8')), result)
        with self.assertRaisesRegex(FileExistsError, 'must be new'):
            agent_kaggle.contrast(refs, alts, self.prereg, output)
        with self.assertRaisesRegex(ValueError, 'same distinct seeds'):
            agent_kaggle.contrast(refs[:1], alts, self.prereg, self.agent/'contrast-seeds.json')
        with self.assertRaisesRegex(ValueError, 'Completed M fit'):
            agent_kaggle.contrast(alts, alts, self.prereg, self.agent/'contrast-swapped.json')
        # Pairing: the populations and the recipe (thread_count included) must be those of M.
        unpaired = [('population', lambda r: r['training_populations'][0].update(selected_queries=1)),
                    ('threads', lambda r: r['hyperparameters'].update(thread_count=8)),
                    ('inputs', lambda r: r['inputs'][0].update(manifest_sha256='0'*64))]
        for name, edit in unpaired:
            fit = self.copy(self.port/'MA2027', f'contrast-{name}', lambda d: edit_json(d/'report.json', edit))
            with self.subTest(name), self.assertRaisesRegex(ValueError, 'not paired'):
                agent_kaggle.contrast(refs, [alts[0], fit], self.prereg, self.agent/f'contrast-{name}.json')
        other = write_prereg(self.tmp/'prereg-other.json', self.set_path, self.exported,
                             lambda r: r['agent_set'].update(sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'preregistered'):
            agent_kaggle.contrast(refs, alts, other, self.agent/'contrast-other.json')

    def test_gate_is_ok_on_the_fixture_chain_and_never_records_a_map(self):
        result = self.gate('ok')
        users = self.chunked['users']
        self.assertEqual((result['format'], result['status'], result['result'], result['deviation'], result['model']),
                         ('hm-agent-gate-v1', 'completed', 'OK', None, 'M2026'))
        checks = result['checks']
        self.assertEqual({name: check['result'] for name, check in checks.items()},
                         dict.fromkeys(agent_kaggle.GATE_CHECKS, 'OK'))
        self.assertEqual(result['prereg'], dict(sha256=base.sha(self.prereg), deviations_sha256=None))
        # Leakcheck, three sidecars, the score plan and its two MA fits, two port fits.
        prereg = checks['prereg']
        self.assertEqual((prereg['artifacts'], prereg['other_set_or_export'], prereg['unregistered_code'],
                          prereg['sidecar_binding'], prereg['deviation_problems'], prereg['rebuilt'],
                          prereg['stale_deviation'], prereg['code_binding'], prereg['final_anchors']),
                         (1+len(ANCHORS)+1+2+2, [], [], [], [], {}, [], [], {'MA2026': 'OK', 'MA2027': 'OK'}))
        leak = checks['leakcheck']
        self.assertEqual((leak['anchors'], leak['rows'], leak['leak_mismatches'], leak['invariance_mismatches'],
                          leak['anchor_results'], leak['users'], leak['columns'], leak['before_every_sidecar']),
                         (2, 2*120*self.leak_users, 0, 0, {'2020-09-02': 'OK', '2020-09-16': 'OK'}, self.leak_users,
                          len(COLUMNS), True))
        self.assertEqual((checks['control']['control'], checks['control']['score_mismatches'],
                          checks['control']['agent']['rows']), ('OK', 0, 12*users))
        self.assertEqual((checks['finite']['every_candidate_scored'], checks['finite']['models']),
                         (True, {f'MA{s}': dict(rows=120*users, nonfinite_scores=0, top12_rows=12*users,
                                                top12_nonfinite_scores=0) for s in SEEDS}))
        parity = checks['parity']
        self.assertEqual((parity['sidecars'], parity['score_rows'], list(parity['columns'])), (list(ANCHORS), 120*users, COLUMNS))
        whole = self.receipts('score-whole')
        for name, column in parity['columns'].items():
            shares = [self.sidecars[a]['non_null'][name]/self.sidecars[a]['keys']['rows'] for a in ANCHORS]
            self.assertEqual((column['sidecar_min'], column['sidecar_max']), (min(shares), max(shares)))
            self.assertEqual(column['score_share'], sum(r['agent_non_null'][name] for r in whole)/(120*users))
            self.assertTrue(0 < column['score_share'] < 1, name)
        popularity = checks['popularity']
        self.assertEqual(set(popularity), {'result', 'rule', 'seeds', 'anchors', 'fits'})
        self.assertEqual((popularity['seeds'], popularity['anchors'], popularity['fits']),
                         ('OK', {f'MA{s}': 'OK' for s in SEEDS}, {f'MA{s}': 'OK' for s in SEEDS}))
        text = (self.agent/'gates/ok/gate.json').read_text(encoding='utf-8')
        self.assertEqual(json.loads(text), result)
        # Only OK/FAIL for the floor: no MAP anywhere in gate.json.
        recorded = list(numbers(result))
        for seed in SEEDS:
            self.assertNotIn(self.ma[seed]['validation_metrics']['map_at_12_conditional'], recorded)
        self.assertNotIn('map_at_12', text)
        self.assertFalse(any(u in text for u in base.CUSTOMERS))
        self.assertEqual(sorted(p.name for p in (self.agent/'gates/ok').iterdir()), ['gate.json'])
        with self.assertRaises(FileExistsError):
            self.gate('ok')

    def test_gate_fails_each_check_on_doctored_input(self):
        score, port = self.agent/'score-chunked', self.port

        def fit_code(root):
            edit_json(root/'report.json', lambda r: r['code'].update({'hm_agent_kaggle.py': 'b'*64}))

        def key_set(root):
            edit_json(root/'report.json', lambda r: r['code'].pop('hm_result_audit.py'))

        def unknown_deviation(root):
            edit_json(root/'report.json', lambda r: r.update(deviation='d1'))

        def leak(root):
            def edit(report):
                item = report['anchors']['2020-09-02']
                item.update(result='LEAK', leak_mismatches=dict(item['leak_mismatches'], ag_cust_n28=5))
                report['result'] = 'LEAK'
            edit_json(root/'report.json', edit)

        def anchor_leak(root):
            edit_json(root/'report.json', lambda r: r['anchors']['2020-09-16'].update(result='LEAK'))

        def late(root):
            edit_json(root/'report.json', lambda r: r.update(finished_at_utc='2099-01-01T00:00:00+00:00'))

        def anchor_missing(root):
            edit_json(root/'report.json', lambda r: r['anchors'].pop('2020-09-16'))

        def users(root):
            edit_json(root/'report.json', lambda r: r.update(users=r['users']+1))

        def nan_receipt(root):
            edit_json(root/'chunk-0001.json', lambda r: r['models']['MA2026'].update(nonfinite_scores=1))

        def unscored(root):
            edit_json(root/'chunk-0002.json', lambda r: r['models']['MA2027'].update(rows=r['candidate_rows']-1))

        def null_column(root):
            for path in root.glob('chunk-*.json'):
                edit_json(path, lambda r: r['agent_non_null'].update(ag_art_gap7=0))

        def final_moved(root):
            resign_plan(root, lambda p: next(m for m in p['models'] if m['name'] == 'MA2026')['anchors'].update(
                train=list(ANCHORS[:2]), validation=[ANCHORS[2]]))

        def final_validated(root):
            resign_plan(root, lambda p: next(m for m in p['models'] if m['name'] == 'MA2027')['anchors'].update(
                validation=[ANCHORS[2]]))

        def below_floor(root):
            edit_json(root/'report.json', lambda r: r['validation_metrics'].update(map_at_12_conditional=0.0055))
        # Too few users at one anchor only, and run after the sidecars.
        small = self.agent/'leakcheck-small'
        agent_kaggle.leakcheck(self.database, self.export, self.set_path, [self.collections['2020-09-16']], small, users=8)
        cases = [
            ('other-set', dict(prereg=write_prereg(self.tmp/'gate-prereg-set.json', self.set_path, self.exported,
                                                   lambda r: r['agent_set'].update(sha256='0'*64))), 'prereg'),
            ('other-code', dict(prereg=write_prereg(self.tmp/'gate-prereg-code.json', self.set_path, self.exported,
                                                    lambda r: r['code'].update({'hm_agent_kaggle.py': '0'*64}))), 'prereg'),
            ('unregistered', dict(port_fits=[self.copy(port/'MA2026', 'unregistered', fit_code), port/'MA2027']), 'prereg'),
            ('key-set', dict(port_fits=[self.copy(port/'MA2026', 'key-set', key_set), port/'MA2027']), 'prereg'),
            ('unknown-deviation', dict(port_fits=[self.copy(port/'MA2026', 'unknown-deviation', unknown_deviation),
                                                  port/'MA2027']), 'prereg'),
            ('leak', dict(leakcheck=self.copy(self.agent/'leakcheck', 'leak', leak)), 'leakcheck'),
            ('anchor-leak', dict(leakcheck=self.copy(self.agent/'leakcheck', 'anchor-leak', anchor_leak)), 'leakcheck'),
            ('leakcheck-late', dict(leakcheck=self.copy(self.agent/'leakcheck', 'leakcheck-late', late)), 'leakcheck'),
            ('leakcheck-small', dict(leakcheck=small), 'leakcheck'),
            ('leakcheck-anchor', dict(leakcheck=self.copy(self.agent/'leakcheck', 'leakcheck-anchor', anchor_missing)),
             'leakcheck'),
            ('leakcheck-users', dict(leakcheck=self.copy(self.agent/'leakcheck', 'leakcheck-users', users)), 'leakcheck'),
            ('diff', dict(agent_scores=self.copy(score, 'diff', lambda d: edit_top12(
                d, 'top12-M2026-0001.parquet', f'score+CASE WHEN {FIRST_ROW} THEN 1e-6 ELSE 0 END'))), 'control'),
            ('final-anchors', dict(agent_scores=self.copy(score, 'final-anchors', final_moved)), 'prereg'),
            ('final-validation', dict(agent_scores=self.copy(score, 'final-validation', final_validated)), 'prereg'),
            ('nan-receipt', dict(agent_scores=self.copy(score, 'nan-receipt', nan_receipt)), 'finite'),
            ('unscored', dict(agent_scores=self.copy(score, 'unscored', unscored)), 'finite'),
            ('nan-score', dict(agent_scores=self.copy(score, 'nan-score', lambda d: edit_top12(
                d, 'top12-MA2026-0001.parquet', f"CASE WHEN {FIRST_ROW} THEN 'NaN'::DOUBLE ELSE score END"))), 'finite'),
            ('null-column', dict(agent_scores=self.copy(score, 'null-column', null_column)), 'parity'),
            ('below-floor', dict(port_fits=[self.copy(port/'MA2026', 'below-floor', below_floor), port/'MA2027']),
             'popularity')]
        for name, changes, failing in cases:
            with self.subTest(name):
                result = self.gate(name, **changes)
                self.assertEqual((result['result'], [k for k, v in result['checks'].items() if v['result'] != 'OK']),
                                 ('FAIL', [failing]))
        checks = {name: json.loads((self.agent/'gates'/name/'gate.json').read_text(encoding='utf-8'))['checks']
                  for name, _, _ in cases}
        self.assertEqual(len(checks['other-set']['prereg']['other_set_or_export']), 1+len(ANCHORS)+1+2+2)
        self.assertEqual(checks['other-code']['prereg']['error']['type'], 'ValueError')
        for name in ('unregistered', 'key-set'):
            self.assertEqual(checks[name]['prereg']['unregistered_code'],
                             [str((self.agent/'doctored'/name/'report.json').resolve())])
        self.assertEqual(checks['unknown-deviation']['prereg']['deviation_problems'], [dict(
            path=str((self.agent/'doctored/unknown-deviation/report.json').resolve()),
            problem="deviation 'd1' is not a record of the supplied deviations file")])
        self.assertEqual((checks['leak']['leakcheck']['leakcheck'], checks['leak']['leakcheck']['leak_mismatches']), ('LEAK', 5))
        self.assertEqual((checks['anchor-leak']['leakcheck']['leakcheck'],
                          checks['anchor-leak']['leakcheck']['anchor_results']['2020-09-16']), ('OK', 'LEAK'))
        self.assertFalse(checks['leakcheck-late']['leakcheck']['before_every_sidecar'])
        self.assertEqual((checks['leakcheck-small']['leakcheck']['users'], checks['leakcheck-small']['leakcheck']['anchors']), (8, 1))
        self.assertEqual(checks['leakcheck-anchor']['leakcheck']['anchor_results'], {'2020-09-02': 'OK'})
        self.assertEqual((checks['leakcheck-users']['leakcheck']['users'], checks['leakcheck-users']['leakcheck']['anchors']),
                         (self.leak_users+1, 2))
        for name in ('leakcheck-anchor', 'leakcheck-users'):
            self.assertEqual((checks[name]['leakcheck']['leakcheck'], checks[name]['leakcheck']['before_every_sidecar']),
                             ('OK', True))
        self.assertEqual(checks['final-anchors']['prereg']['final_anchors'], {'MA2026': 'FAIL', 'MA2027': 'OK'})
        self.assertEqual(checks['final-validation']['prereg']['final_anchors'], {'MA2026': 'OK', 'MA2027': 'FAIL'})
        self.assertEqual((checks['diff']['control']['control'], checks['diff']['control']['score_mismatches']), ('DIFF', 1))
        self.assertEqual(checks['nan-receipt']['finite']['models']['MA2026']['nonfinite_scores'], 1)
        self.assertFalse(checks['unscored']['finite']['every_candidate_scored'])
        self.assertEqual(checks['nan-score']['finite']['models']['MA2026']['top12_nonfinite_scores'], 1)
        self.assertEqual({k: v['result'] for k, v in checks['null-column']['parity']['columns'].items()},
                         dict(dict.fromkeys(COLUMNS, 'OK'), ag_art_gap7='FAIL'))
        self.assertEqual(checks['below-floor']['popularity']['fits'], {'MA2026': 'FAIL', 'MA2027': 'OK'})
        self.assertNotIn(0.0055, list(numbers(checks['below-floor'])))
        # CLI: exit 1 and one line of OK/FAIL.
        argv = ['gate', '--prereg', str(self.prereg), '--leakcheck', str(self.agent/'leakcheck'),
                '--sidecars', str(self.sidecar_root), '--agent-scores', str(score), '--kaggle-scores', str(self.kaggle_scores),
                '--port', str(self.agent/'doctored/below-floor'), str(port/'MA2027'),
                '--output', str(self.agent/'gates/cli-below-floor')]
        code, lines = run_main(argv)
        self.assertEqual((code, len(lines)), (1, 1))
        self.assertEqual(json.loads(lines[0]), dict(status='completed', result='FAIL', deviation=None, checks=dict(
            dict.fromkeys(agent_kaggle.GATE_CHECKS, 'OK'), popularity='FAIL')))

    def test_gate_binds_the_sidecars_and_port_fits_the_scored_fits_used(self):
        def stale(root):
            edit_json(root/'2020-09-09/manifest.json', lambda m: m.update(deviation='d1'))

        def only_last(root):
            for anchor in ANCHORS[:2]:
                shutil.rmtree(root/anchor)

        def moved(root):
            edit_json(root/'report.json', lambda r: r['inputs'][0].update(anchor='2020-08-26'))
        stale_root = self.copy(self.sidecar_root, 'sidecars-stale', stale)
        cases = [('stale-sidecar', dict(sidecars=stale_root), {'prereg', 'parity'}),
                 ('one-sidecar', dict(sidecars=self.copy(self.sidecar_root, 'sidecars-one', only_last)), {'prereg', 'parity'}),
                 ('no-sidecar', dict(sidecars=self.copy(self.sidecar_root, 'sidecars-none',
                                                        lambda root: [shutil.rmtree(root/a) for a in ANCHORS])),
                  {'prereg', 'parity'}),
                 ('one-port-fit', dict(port_fits=[self.port/'MA2026']), {'popularity'}),
                 ('port-anchors', dict(port_fits=[self.copy(self.port/'MA2026', 'port-anchors', moved), self.port/'MA2027']),
                  {'popularity'})]
        for name, changes, failing in cases:
            with self.subTest(name):
                result = self.gate(f'binding-{name}', **changes)
                self.assertEqual({k for k, v in result['checks'].items() if v['result'] != 'OK'}, failing)
        checks = {name: json.loads((self.agent/'gates'/f'binding-{name}'/'gate.json').read_text(encoding='utf-8'))['checks']
                  for name, _, _ in cases}
        self.assertEqual(checks['stale-sidecar']['prereg']['sidecar_binding'],
                         [f"{(stale_root/'2020-09-09/manifest.json').resolve()}: not the sidecar the fits used"])
        self.assertEqual(len(checks['one-sidecar']['prereg']['sidecar_binding']), 2)
        # No bound sidecar: a binding failure of prereg; the leakcheck cannot order itself and says so.
        self.assertEqual(len(checks['no-sidecar']['prereg']['sidecar_binding']), len(ANCHORS))
        self.assertEqual((checks['no-sidecar']['leakcheck']['result'], checks['no-sidecar']['leakcheck']['before_every_sidecar']),
                         ('OK', None))
        self.assertEqual((checks['one-port-fit']['popularity']['seeds'], checks['one-port-fit']['popularity']['fits']),
                         ('FAIL', {'MA2026': 'OK'}))
        self.assertEqual(checks['port-anchors']['popularity']['anchors'], {'MA2026': 'FAIL', 'MA2027': 'OK'})
        # The fits used three anchors; a chain of four is not complete.
        with mock.patch.object(agent_kaggle, 'SIDECAR_ANCHORS', ('2020-08-26',)+ANCHORS):
            result = self.gate('binding-anchors')
        self.assertEqual({k for k, v in result['checks'].items() if v['result'] != 'OK'}, {'prereg', 'parity'})
        self.assertEqual(result['checks']['prereg']['sidecar_binding'],
                         ['the fits used sidecars of 2020-09-02, 2020-09-09, 2020-09-16, '
                          'not 2020-08-26, 2020-09-02, 2020-09-09, 2020-09-16'])

    def test_score_ma_refuses_fits_with_other_sidecars_or_hyperparameters(self):
        def other_sidecar(root):
            edit_json(root/'report.json', lambda r: r['agent']['sidecars'].update({'2020-09-09': '0'*64}))

        def other_depth(root):
            edit_json(root/'report.json', lambda r: r['hyperparameters'].update(depth=5))
        for name, edit, message in (('sidecar', other_sidecar, 'different sidecars at 2020-09-09'),
                                    ('depth', other_depth, 'hyperparameters of the control')):
            fit = self.copy(self.fits[1], f'score-fit-{name}', edit)
            output = self.agent/f'score-refused-{name}'
            with self.subTest(name), self.assertRaisesRegex(ValueError, message):
                agent_kaggle.score_ma(self.database, self.export, self.set_path, [self.fits[0], fit],
                                      self.port/'M2026', output, chunk_users=1000, threads=2)
            self.assertFalse(output.exists())
        # A port fit (validation) among the scored fits: refused before any output.
        output = self.agent/'score-refused-port'
        with self.assertRaisesRegex(ValueError, 'MA2026 is not a final fit'):
            agent_kaggle.score_ma(self.database, self.export, self.set_path, [self.port/'MA2026', self.fits[1]],
                                  self.port/'M2026', output, chunk_users=1000, threads=2)
        self.assertFalse(output.exists())

    def test_score_ma_records_a_nonfinite_score_per_model(self):
        import numpy as np
        from catboost import CatBoostClassifier

        def nan_scores(model, pool, *args, **kwargs):
            return np.full((pool.num_row(), 2), np.nan)
        output = self.agent/'score-nan'
        with redirect_stderr(io.StringIO()), mock.patch.object(CatBoostClassifier, 'predict_proba', nan_scores), \
                self.assertRaisesRegex(ValueError, 'must be finite'):
            agent_kaggle.score_ma(self.database, self.export, self.set_path, self.fits, self.port/'M2026', output,
                                  chunk_users=1000, threads=2)
        report = json.loads((output/'report.json').read_text(encoding='utf-8'))
        self.assertEqual((report['status'], report['nonfinite_scores'], report['nonfinite_chunk']),
                         ('failed', {'M2026': 120*self.whole['users']}, 0))
        self.assertEqual(list(output.glob('chunk-*.json')), [])

    def test_parity_needs_positive_shares_within_the_band(self):
        passes = agent_kaggle.parity_passes
        self.assertTrue(passes(0.3, [0.2, 0.4]))
        self.assertTrue(passes(0.1, [0.2, 0.4]) and passes(0.8, [0.2, 0.4]))
        self.assertFalse(passes(0.09, [0.2, 0.4]) or passes(0.81, [0.2, 0.4]))
        # An all-NULL column is never parity, nor one that a sidecar never fills.
        self.assertFalse(passes(0.0, [0.0, 0.0]) or passes(0.0, [0.2, 0.4]) or passes(0.3, [0.0, 0.4]) or passes(0.3, []))

    def test_agent_block_turns_every_kind_of_missing_into_nan(self):
        import numpy as np
        import pandas as pd
        frame = pd.DataFrame({'customer_id': ['a', 'a', 'b', 'b', 'c', 'c'], 'article_id': ['1', '2', '1', '2', '1', '2'],
                              'ag_x': [1.5, None, float('nan'), float('inf'), -float('inf'), 1e39],
                              'ag_y': pd.array([3, None, 2, 1, 0, -7], dtype='Int64')})
        block = agent_kaggle.agent_block(frame, ['ag_x', 'ag_y'])
        self.assertEqual((block.dtype, block.shape, block.flags['C_CONTIGUOUS']), (np.dtype('float32'), (6, 2), True))
        self.assertEqual(np.isnan(block).tolist(), [[False, False], [True, True], [True, False], [True, False],
                                                    [True, False], [True, False]])
        self.assertEqual((block[0, 0], block[5, 1]), (np.float32(1.5), np.float32(-7)))
        self.assertEqual(agent_kaggle.agent_block(frame, []).shape, (6, 0))
        keys = frame[['customer_id', 'article_id']]
        values = frame[['customer_id', 'article_id', 'ag_x']].iloc[::-1]
        aligned = agent_kaggle.align_block(keys, values, ['ag_x'])
        self.assertEqual(aligned[['customer_id', 'article_id']].values.tolist(), keys.values.tolist())
        self.assertTrue(same(aligned['ag_x'].map(lambda v: (v,)).tolist(), frame['ag_x'].map(lambda v: (v,)).tolist()))
        bad = [(values.iloc[1:], 'one row per key'), (values[['article_id', 'customer_id', 'ag_x']], 'keys and the agent-set'),
               (values.assign(article_id=['9']+list(values['article_id'][1:])), 'exactly the given keys')]
        for wrong, message in bad:
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                agent_kaggle.align_block(keys, wrong, ['ag_x'])
        with self.assertRaises(Exception):
            agent_kaggle.align_block(keys, pd.concat([values.iloc[:5], values.iloc[:1]]), ['ag_x'])

    def test_cli_prints_one_json_line_per_command_and_requires_isolation(self):
        c, cli, port = self.collections, self.agent/'cli', self.port
        db, export, agent_set = str(self.database), str(self.export), str(self.set_path)
        commands = [
            ['sidecar', '--database', db, '--export', export, '--agent-set', agent_set,
             '--collection', str(c['2020-09-09']), '--output', str(cli/'sidecar'), '--threads', '2'],
            ['fit', '--seed', '2027', '--train', str(c['2020-09-09']), str(c['2020-09-16']), '--sidecars',
             str(self.sidecar_root), '--prereg', str(self.prereg), '--output', str(cli/'MA2027'), '--threads', '2'],
            ['score', '--database', db, '--export', export, '--agent-set', agent_set, '--fits', str(self.fits[0]),
             str(self.fits[1]), '--control', str(port/'M2026'), '--output', str(cli/'score'), '--chunk-users', '1000', '--threads', '2'],
            ['control', '--agent-scores', str(cli/'score'), '--kaggle-scores', str(self.kaggle_scores)],
            ['leakcheck', '--database', db, '--export', export, '--agent-set', agent_set,
             '--collections', str(c['2020-09-16']), '--users', '8', '--output', str(cli/'leakcheck')],
            ['leakcheck', '--database', db, '--export', export, '--agent-set', str(self.batch_set),
             '--collections', str(c['2020-09-16']), '--users', '8', '--output', str(cli/'leakcheck-batch')],
            ['contrast', '--reference', str(port/'M2026'), str(port/'M2027'), '--alternative', str(port/'MA2026'),
             str(port/'MA2027'), '--prereg', str(self.prereg), '--output', str(cli/'contrast.json')],
            ['gate', '--prereg', str(self.prereg), '--leakcheck', str(self.agent/'leakcheck'), '--sidecars', str(self.sidecar_root),
             '--agent-scores', str(cli/'score'), '--kaggle-scores', str(self.kaggle_scores),
             '--port', str(port/'MA2026'), str(port/'MA2027'), '--output', str(cli/'gate')],
        ]
        # Without -I every command refuses before it writes anything.
        for argv in commands:
            code, lines = run_main(argv, isolated=lambda: False)
            with self.subTest(refused=argv[0]):
                self.assertEqual((code, len(lines)), (1, 1))
                printed = json.loads(lines[0])
                self.assertEqual((printed['status'], printed['command'], printed['error_type']),
                                 ('failed', argv[0], 'RuntimeError'))
                self.assertIn('python -I', printed['message'])
        self.assertFalse(cli.exists())
        printed = []
        for argv in commands:
            with redirect_stderr(io.StringIO()):
                code, lines = run_main(argv)
            self.assertEqual(len(lines), 1, argv[0])
            printed.append((code, json.loads(lines[0])))
        self.assertEqual([code for code, _ in printed], [0, 0, 0, 0, 0, 1, 0, 0], printed)
        sidecar, fit, score, control, leak, batch, contrast, gate = (value for _, value in printed)
        self.assertEqual(sidecar, dict(status='completed', anchor='2020-09-09', columns=len(COLUMNS),
                                       rows=self.manifests['2020-09-09']['population']['candidate_rows']))
        self.assertEqual((fit['model'], fit['trees'], fit['columns'], fit['train_queries'], fit['deviation']),
                         ('MA2027', 25, len(COLUMNS), 40, None))
        self.assertEqual(score, dict(status='completed', users=self.whole['users'], chunks=1, computed=1, skipped=0))
        self.assertEqual((control['status'], control['result'], control['score_mismatches']), ('completed', 'OK', 0))
        self.assertEqual((leak['result'], leak['anchors']['2020-09-16']), ('OK', dict(
            rows=8*120, columns=len(COLUMNS), leak_mismatches=0, invariance_mismatches=0, result='OK')))
        self.assertEqual((batch['status'], batch['result'], batch['anchors']['2020-09-16']['invariance_mismatches']),
                         ('completed', 'LEAK', 8*120))
        stored = json.loads((cli/'contrast.json').read_text(encoding='utf-8'))
        self.assertEqual(contrast, dict(status='completed', deviation=None, map_by_fit=stored['map_by_fit'],
                                        delta_by_seed=stored['delta_by_seed'], mean_delta=stored['bootstrap']['mean_delta'],
                                        percentile_95=stored['bootstrap']['percentile_95']))
        self.assertEqual(gate, dict(status='completed', result='OK', deviation=None,
                                    checks=dict.fromkeys(agent_kaggle.GATE_CHECKS, 'OK')))
        for argv in ([], ['frobnicate'], ['fit', '--seed', '2025', '--train', 'a', '--sidecars', 's', '--prereg', 'p',
                                          '--output', 'o'], ['leakcheck', '--database', db], ['gate', '--prereg', 'p']):
            code, lines = run_main(argv)
            with self.subTest(usage=argv):
                self.assertEqual((code, len(lines)), (1, 1))
                self.assertEqual(json.loads(lines[0])['error_type'], 'UsageError')

    def test_cli_masks_native_and_proposal_errors(self):
        argv = ['sidecar', '--database', str(self.database), '--export', str(self.export), '--agent-set', str(self.set_path),
                '--collection', str(self.collections['2020-09-09']), '--threads', '2']
        errors = [(duckdb.ConversionException('Could not convert SECRET-ROW'), None),
                  (sandbox.ProposalError('r1p1: SECRET-ROW'), 'r1p1')]
        for number, (error, proposal) in enumerate(errors):
            output = self.agent/f'sidecar-masked-{number}'
            with self.subTest(type(error).__name__), mock.patch.object(sandbox, 'agent_columns', side_effect=error):
                code, lines = run_main(argv+['--output', str(output)])
                self.assertEqual((code, len(lines)), (1, 1))
                self.assertNotIn('SECRET', lines[0])
                printed = json.loads(lines[0])
                self.assertEqual((printed['error_type'], printed.get('proposal')), (type(error).__name__, proposal))
                manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
                self.assertEqual((manifest['status'], manifest.get('proposal')), ('failed', proposal))
                self.assertFalse((output/'agent.parquet').exists())


if __name__ == '__main__':
    unittest.main()
