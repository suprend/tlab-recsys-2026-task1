"""Tiny synthetic witnesses for the CPU Kaggle runner; no real H&M data.

One fixture runs the whole chain once (verify through the isolated CLI with a
planted module on PYTHONPATH, EDA, collections, small fits, two scorings,
assembly). Tests then compare it with the locked code and with plain-Python
oracles. Scratch lives in /tmp only; test-side DuckDB connections spill there
and use two threads.
"""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
import csv
from datetime import date, timedelta
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import duckdb

from scripts import hm_eda
from scripts import hm_experiment as experiment
from scripts import hm_kaggle as kaggle
from scripts import hm_retrieval
from scripts.hm_baseline import cohort_key
from scripts.hm_eda import FILES, SCHEMAS
from scripts.hm_feature_engine import CATEGORICAL_FEATURES, PILOT_NUMERIC_FEATURES
from scripts.hm_retrieval import create_candidates

CUSTOMERS = [hashlib.sha256(f'customer-{i}'.encode()).hexdigest() for i in range(48)]
ARTICLES = [f'{108775000+37*i:010d}' for i in range(160)]
START, END = date(2020, 3, 1), date(2020, 9, 22)
GAP = (date(2020, 7, 1), date(2020, 7, 8))  # nobody buys: anchor 07-01 has an empty label week
OLD_ONLY = CUSTOMERS[36:40]  # history ends in April: no 90-day history at 09-23
SCRIPT = str(kaggle.ROOT/'scripts/hm_kaggle.py')
TRAP = "open(__file__+'.imported','w').write('planted module executed')\n"
# A second process takes score.lock with the runner's own function and keeps it until stdin closes.
HOLDER = '''import sys
sys.path.append(sys.argv[1])
from scripts.hm_kaggle import hold_lock
hold_lock(sys.argv[2])
print('locked', flush=True)
sys.stdin.read()
'''
ENDLESS = 'SELECT sum(i % 7) FROM range(10000000000000) t(i)'  # ends only by interruption
WALL = dict(status='failed', error_type='TimeoutError', message='Declared wall limit exceeded')
LOCKED_RECIPE = kaggle.locked_recipe  # captured before the class patches it


def purchases():
    """Two background buyers cycle the catalog every 80 purchase days."""
    rng = random.Random(2026)
    weights = [1/(rank+3) for rank in range(len(ARTICLES))]
    rows, day, k = [], START, 0
    while day <= END:
        if not GAP[0] <= day < GAP[1]:
            rows.append((day, CUSTOMERS[0], ARTICLES[(2*k) % 160]))
            rows.append((day, CUSTOMERS[1], ARTICLES[(2*k+1) % 160]))
            rows += [(day, rng.choice(CUSTOMERS[2:36]), rng.choices(ARTICLES, weights)[0]) for _ in range(5)]
            if day < date(2020, 5, 1) and rng.random() < .3:
                rows.append((day, rng.choice(OLD_ONLY), rng.choices(ARTICLES, weights)[0]))
            k += 1
        day += timedelta(days=1)
    # Identical rows are retained by EDA; they must not create duplicate candidates.
    rows += [(date(2020, 9, 20), CUSTOMERS[2], ARTICLES[5])]*2
    return rows


def write_tables(directory, rows):
    directory.mkdir(parents=True)
    rng = random.Random(7)
    types = [('253', 'Vest top'), ('272', 'Trousers'), ('265', 'Dress'), ('-1', 'Unknown')]
    articles = []
    for i, article in enumerate(ARTICLES):
        row = dict.fromkeys(SCHEMAS['articles'], 'fixture')
        row.update(article_id=article, product_code=article[:7], product_type_no=types[i % 4][0],
                   product_type_name=types[i % 4][1], colour_group_code=('09', '10', '73', '')[i % 4],
                   department_no=str(1000+i % 6), index_code='ABCD'[i % 4], garment_group_no=str(1001+i % 5))
        articles.append(row)
    customers = []
    for customer in CUSTOMERS:
        row = dict.fromkeys(SCHEMAS['customers'], '')
        row.update(customer_id=customer, age='30', club_member_status='ACTIVE', fashion_news_frequency='NONE',
                   postal_code=customer[::-1])
        customers.append(row)
    transactions = [dict(t_dat=d.isoformat(), customer_id=u, article_id=a, price=f'{rng.uniform(.005, .06):.6f}',
                         sales_channel_id=str(1+rng.random() < .5)) for d, u, a in rows]
    for table, records in (('articles', articles), ('customers', customers), ('transactions', transactions)):
        with (directory/FILES[table]).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(SCHEMAS[table]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(records)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_config(path, staging):
    files = [dict(path='data/raw/'+name, size=(staging/name).stat().st_size, sha256=sha(staging/name))
             for name in ('articles.csv', 'customers.csv', 'transactions_train.csv')]
    path.write_text(json.dumps(dict(dataset='fixture', mirror='fixture', revision='fixture', files=files)), encoding='utf-8')
    return path


def zip_one(archive, source, arcname=None, extra=None):
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(source, arcname=arcname or source.name)
        if extra:
            bundle.writestr(extra, 'x')


def kaggle_layout(raw, staging):
    """The kaggle CLI leaves large tables as per-file zips; customers stays plain here."""
    raw.mkdir()
    zip_one(raw/'articles.csv.zip', staging/'articles.csv')
    zip_one(raw/'transactions_train.csv.zip', staging/'transactions_train.csv')
    shutil.copy2(staging/'customers.csv', raw/'customers.csv')


def read_lines(path):
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as stream:
        return stream.readlines()


def leftovers(directory):
    """Partial receipts or per-process spill left behind by a finished run."""
    return sorted(p.name for p in Path(directory).rglob('*')
                  if p.name.endswith('.part') or p.name.startswith('duckdb-temp-'))


def run_main(argv, **patches):
    """kaggle.main with stdout captured; returns the exit code and the printed lines."""
    out = io.StringIO()
    with ExitStack() as stack:
        for name, value in patches.items():
            stack.enter_context(mock.patch.object(kaggle, name, value))
        stack.enter_context(redirect_stdout(out))
        stack.enter_context(redirect_stderr(io.StringIO()))
        code = kaggle.main(argv)
    return code, out.getvalue().splitlines()


class HmKaggleTests(unittest.TestCase):
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
        cls.tmp = Path(cls.stack.enter_context(tempfile.TemporaryDirectory(prefix='tlab-hm-kaggle-', dir='/tmp')))
        cls.artifacts = cls.tmp/'artifacts'
        cls.artifacts.mkdir()
        cls.rows = purchases()
        cls.staging = cls.tmp/'staging'
        write_tables(cls.staging, cls.rows)
        cls.config = write_config(cls.tmp/'hm-source.json', cls.staging)
        cls.raw = cls.tmp/'raw'
        kaggle_layout(cls.raw, cls.staging)
        (cls.raw/'json.py').write_text(TRAP, encoding='utf-8')
        # The real CLI in isolated mode, from inside the download directory and with
        # that directory on PYTHONPATH: the planted json.py must not run.
        cls.cli = subprocess.run([sys.executable, '-I', SCRIPT, 'verify', '--raw-dir', str(cls.raw), '--config', str(cls.config)],
                                 cwd=cls.raw, env=dict(os.environ, PYTHONPATH=str(cls.raw)),
                                 capture_output=True, text=True, timeout=300)
        connection_for = experiment.connection_for

        def two_threads(database, output):
            con = connection_for(database, output)
            con.execute('SET threads=2')
            return con

        def small_recipe(arm, seed, threads=4):
            recipe = LOCKED_RECIPE(arm, seed, threads)
            recipe['hyperparameters'].update(iterations=25, depth=4)
            recipe['train_users'] = 20
            return recipe
        # Fixture-sized reference counts, so its EDA validates like the full dataset would.
        counts = dict(transactions=len(cls.rows), customers=len(CUSTOMERS), articles=len(ARTICLES))
        cls.stack.enter_context(mock.patch.dict(hm_eda.EXPECTED_ROWS, counts))
        # In-process calls stand in for ``python -I``; subprocess runs check the real flag.
        for target, name, value in ((kaggle, 'ARTIFACTS', cls.artifacts), (kaggle, 'SOURCE_SHA256', sha(cls.config)),
                                    (kaggle, 'isolated', lambda: True), (kaggle, 'EDA_FREE_BYTES', 10*1024**3),
                                    (experiment, 'connection_for', two_threads), (kaggle, 'locked_recipe', small_recipe)):
            cls.stack.enter_context(mock.patch.object(target, name, value))
        cls.eda = kaggle.eda(cls.raw, cls.artifacts/'eda')
        cls.database = Path(cls.eda['database_path'])
        cls.collections = {anchor: cls.artifacts/'collections'/anchor for anchor in ('2020-09-02', '2020-09-09', '2020-09-16')}
        cls.manifests = {anchor: kaggle.collect(cls.database, path, anchor, 1000) for anchor, path in cls.collections.items()}
        c = [cls.collections[a] for a in ('2020-09-02', '2020-09-09', '2020-09-16')]
        cls.fits = [cls.artifacts/'fits/M2026', cls.artifacts/'fits/E2027']
        with redirect_stderr(io.StringIO()):
            cls.port = kaggle.fit('M', 2026, c[:2], cls.fits[0], validation_path=c[2], threads=2)
            cls.final = kaggle.fit('E', 2027, c, cls.fits[1], threads=2)
            cls.whole = kaggle.score(cls.database, cls.fits, cls.artifacts/'score-whole', chunk_users=1000, threads=2)
            cls.chunked = kaggle.score(cls.database, cls.fits, cls.artifacts/'score-chunked', chunk_users=7, threads=2)
        cls.submission_path = cls.artifacts/'submissions/M2026.csv.gz'
        cls.submission = kaggle.assemble(cls.database, cls.artifacts/'score-chunked', 'M2026', cls.submission_path,
                                         expected_customers=len(CUSTOMERS))

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def eligible(self, anchor):
        return {u for d, u, _ in self.rows if anchor-timedelta(days=90) <= d < anchor}

    def duckdb_config(self):
        return dict(threads=2, temp_directory=str(self.tmp/'duckdb-test-temp'))

    def connect(self):
        return duckdb.connect(str(self.database), read_only=True, config=self.duckdb_config())

    def memory(self):
        return duckdb.connect(config=self.duckdb_config())

    def top_rows(self, directory, model):
        files = sorted(str(p) for p in Path(directory).glob(f'top12-{model}-*.parquet'))
        con = self.memory()
        try:
            return con.execute('SELECT customer_id,article_id,"rank",score FROM read_parquet(?) ORDER BY customer_id,"rank"',
                               [files]).fetchall()
        finally:
            con.close()

    def score_argv(self, output, *extra):
        return ['score', '--database', str(self.database), '--fits', *map(str, self.fits), '--output', str(output),
                '--chunk-users', '7', '--threads', '2', *extra]

    def broken_scores(self, name, edit):
        """A copy of the chunked scores with one parquet edited and its receipt re-signed."""
        broken = self.artifacts/name
        shutil.copytree(self.artifacts/'score-chunked', broken)
        target = broken/'top12-M2026-0000.parquet'
        con = self.memory()
        try:
            frame = con.execute('SELECT * FROM read_parquet(?) ORDER BY customer_id,"rank"', [str(target)]).df()
            con.register('edited_frame', edit(frame))
            con.sql('SELECT * FROM edited_frame').write_parquet(str(broken/'edited.parquet'))
        finally:
            con.close()
        (broken/'edited.parquet').replace(target)
        receipt = json.loads((broken/'chunk-0000.json').read_text(encoding='utf-8'))
        receipt['files'][target.name]['sha256'] = sha(target)
        (broken/'chunk-0000.json').write_text(json.dumps(receipt), encoding='utf-8')
        return broken

    def test_isolated_cli_ignores_planted_modules_and_extracts_single_member_zips(self):
        self.assertEqual(self.cli.returncode, 0, self.cli.stdout+self.cli.stderr)
        self.assertEqual(json.loads(self.cli.stdout)['status'], 'complete')
        self.assertFalse((self.raw/'json.py.imported').exists())
        receipt = json.loads((self.raw/kaggle.RECEIPT).read_text(encoding='utf-8'))
        files = {f['name']: f for f in receipt['files']}
        self.assertTrue(all(f['matches'] for f in files.values()))
        self.assertIsNone(files['customers.csv']['extracted_from'])
        self.assertEqual(files['articles.csv']['extracted_from']['name'], 'articles.csv.zip')
        for name in ('articles.csv', 'transactions_train.csv'):
            self.assertEqual(sha(self.raw/name), sha(self.staging/name))
            self.assertTrue((self.raw/(name+'.zip')).exists())
        self.assertTrue(self.eda['pinned_sources'])
        self.assertTrue(all(self.eda['eda_validation'].values()))
        # Controls: the same CLI without -I, in a fresh download directory. main()
        # refuses it; a module planted on PYTHONPATH still runs at import time,
        # before any check of ours, so only -I stops it.
        control = self.tmp/'control'
        kaggle_layout(control, self.staging)
        (control/'json.py').write_text(TRAP, encoding='utf-8')
        clean = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
        argv = [sys.executable, SCRIPT, 'verify', '--raw-dir', str(control), '--config', str(self.config)]
        refused = subprocess.run(argv, cwd=control, env=clean, capture_output=True, text=True, timeout=300)
        self.assertEqual(refused.returncode, 1, refused.stderr)
        printed = json.loads(refused.stdout)
        self.assertEqual((printed['status'], printed['command'], printed['error_type']), ('failed', 'verify', 'RuntimeError'))
        self.assertIn('python -I', printed['message'])
        self.assertFalse((control/'json.py.imported').exists())
        trapped = subprocess.run(argv, cwd=control, env=dict(clean, PYTHONPATH=str(control)),
                                 capture_output=True, text=True, timeout=300)
        self.assertTrue((control/'json.py.imported').exists())
        self.assertNotEqual(trapped.returncode, 0)
        self.assertFalse((control/kaggle.RECEIPT).exists())
        self.assertFalse((control/'articles.csv').exists())

    def test_commands_reading_downloads_refuse_to_run_without_isolation(self):
        self.assertEqual(kaggle.ISOLATED_COMMANDS, ('verify', 'eda', 'collect'))
        raw = self.tmp/'not-isolated'
        kaggle_layout(raw, self.staging)
        a = self.artifacts
        commands = [['verify', '--raw-dir', str(raw), '--config', str(self.config)],
                    ['eda', '--raw-dir', str(self.raw), '--output', str(a/'eda-not-isolated')],
                    ['collect', '--database', str(self.database), '--output', str(a/'collect-not-isolated'),
                     '--anchor', '2020-09-09']]
        for argv in commands:
            code, lines = run_main(argv, isolated=lambda: False)
            with self.subTest(argv[0]):
                self.assertEqual((code, len(lines)), (1, 1))
                printed = json.loads(lines[0])
                self.assertEqual((printed['command'], printed['error_type']), (argv[0], 'RuntimeError'))
                self.assertIn('python -I', printed['message'])
        self.assertEqual(sorted(p.name for p in raw.iterdir()), ['articles.csv.zip', 'customers.csv', 'transactions_train.csv.zip'])
        self.assertFalse((a/'eda-not-isolated').exists())
        self.assertFalse((a/'collect-not-isolated').exists())

    def test_usage_errors_print_one_json_line_and_exit_1(self):
        cases = [([], None), (['frobnicate'], None),
                 (['collect', '--database', 'db', '--output', 'out', '--anchor', '2020-09-09', '--users', 'many'], 'collect'),
                 (['fit', '--arm', 'X', '--seed', '2026', '--train', 'a', '--output', 'b'], 'fit'),
                 (['score', '--database', 'db', '--fits', 'f'], 'score')]
        for argv, command in cases:
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(argv), redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(kaggle.main(argv), 1)
            lines = out.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            printed = json.loads(lines[0])
            self.assertEqual((printed['status'], printed['command'], printed['error_type']), ('failed', command, 'UsageError'))
            self.assertEqual(err.getvalue(), '')
        cli = subprocess.run([sys.executable, '-I', SCRIPT, 'score', '--chunk-users', 'many'],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual((cli.returncode, json.loads(cli.stdout)['error_type']), (1, 'UsageError'))

    def test_verify_rejects_bad_archives_and_records_mismatch(self):
        small = json.loads(self.config.read_text(encoding='utf-8'))
        small['files'][0]['size'] = 10  # articles: a declared member far above the pin
        (self.tmp/'small-pin.json').write_text(json.dumps(small), encoding='utf-8')
        cases = {'two-members': (dict(extra='notes.txt'), self.config, kaggle.ArchiveError),
                 'nested-member': (dict(arcname='nested/articles.csv'), self.config, kaggle.ArchiveError),
                 'oversized-member': ({}, self.tmp/'small-pin.json', kaggle.ArchiveError),
                 'stale-partial': ({}, self.config, FileExistsError)}
        for label, (options, config, error) in cases.items():
            raw = self.tmp/f'bad-{label}'
            raw.mkdir()
            zip_one(raw/'articles.csv.zip', self.staging/'articles.csv', **options)
            if label == 'stale-partial':
                (raw/'articles.csv.part').write_text('stale', encoding='utf-8')
            with self.subTest(label), self.assertRaises(error):
                kaggle.verify(raw, config)
            self.assertEqual(json.loads((raw/kaggle.RECEIPT).read_text(encoding='utf-8'))['status'], 'failed')
            self.assertFalse((raw/'articles.csv').exists())
        self.assertEqual((self.tmp/'bad-stale-partial/articles.csv.part').read_text(encoding='utf-8'), 'stale')
        raw = self.tmp/'bad-bytes'
        kaggle_layout(raw, self.staging)
        text = (raw/'customers.csv').read_text(encoding='utf-8')
        (raw/'customers.csv').write_text(text.replace('ACTIVE', 'ACTIVF', 1), encoding='utf-8', newline='')
        code, _ = run_main(['verify', '--raw-dir', str(raw), '--config', str(self.config)])
        self.assertEqual(code, 2)
        receipt = json.loads((raw/kaggle.RECEIPT).read_text(encoding='utf-8'))
        self.assertEqual(receipt['status'], 'mismatch')
        self.assertEqual([f['name'] for f in receipt['files'] if not f['matches']], ['customers.csv'])
        with self.assertRaisesRegex(ValueError, 'allow-unpinned'):
            kaggle.eda(raw, self.artifacts/'eda-unpinned')
        self.assertFalse((self.artifacts/'eda-unpinned').exists())
        unpinned = kaggle.eda(raw, self.artifacts/'eda-unpinned', allow_unpinned=True)
        record = json.loads((self.artifacts/'eda-unpinned'/kaggle.SOURCE_RECORD).read_text(encoding='utf-8'))
        self.assertEqual((unpinned['pinned_sources'], unpinned['allow_unpinned']), (False, True))
        self.assertEqual((record['pinned_sources'], record['allow_unpinned'], record['source_status']), (False, True, 'mismatch'))

    def test_damaged_archives_are_reported_without_archive_text(self):
        good = self.tmp/'zip-good.zip'
        zip_one(good, self.staging/'articles.csv')
        data = good.read_bytes()
        self.assertEqual(data[30:42], b'articles.csv')  # the local header's own copy of the name
        corrupt = bytearray(data)
        corrupt[60:400] = b'\xff'*340  # inside the deflate stream
        cases = {'header-name': (data[:30]+b'SECRETxx.csv'+data[42:], None, {'BadZipFile'}),
                 'not-a-zip': (b'SECRET '*64, None, {'BadZipFile'}),
                 'deflate': (bytes(corrupt), None, {'error', 'BadZipFile'}),
                 'eof': (data, EOFError('SECRET tail'), {'EOFError'})}
        for label, (content, raised, kinds) in cases.items():
            raw = self.tmp/f'zip-{label}'
            raw.mkdir()
            (raw/'articles.csv.zip').write_bytes(content)
            patches = {} if raised is None else dict(hash_stream=mock.Mock(side_effect=raised))
            with self.subTest(label):
                code, lines = run_main(['verify', '--raw-dir', str(raw), '--config', str(self.config)], **patches)
                self.assertEqual((code, len(lines)), (1, 1))
                printed = json.loads(lines[0])
                text = (raw/kaggle.RECEIPT).read_text(encoding='utf-8')
                error = json.loads(text)['error']
                self.assertEqual((printed['error_type'], error['type']), ('ArchiveError', 'ArchiveError'))
                self.assertEqual(printed['message'], error['message'])
                kind = error['message'].removeprefix('articles.csv.zip is damaged or unreadable (').removesuffix(
                    '); download it again into a new directory')
                self.assertIn(kind, kinds)
                self.assertNotIn('SECRET', lines[0]+text)
                self.assertFalse((raw/'articles.csv').exists())

    def test_eda_rehashes_sources_and_checks_free_disk_before_writing(self):
        raw = self.tmp/'rehash'
        shutil.copytree(self.raw, raw)
        path = raw/'customers.csv'
        before = path.stat()
        data = path.read_bytes()
        at = data.index(b'ACTIVE')
        path.write_bytes(data[:at]+b'ACTIVF'+data[at+6:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual((path.stat().st_size, path.stat().st_mtime_ns), (before.st_size, before.st_mtime_ns))
        output = self.artifacts/'eda-rehash'
        with self.assertRaisesRegex(ValueError, 'customers.csv changed after verification'):
            kaggle.eda(raw, output)
        self.assertFalse(output.exists())
        output = self.artifacts/'eda-low-disk'
        disk = SimpleNamespace(total=1, used=0, free=36*1024**3-1)
        with mock.patch.object(kaggle, 'EDA_FREE_BYTES', 36*1024**3), mock.patch('shutil.disk_usage', return_value=disk), \
                self.assertRaisesRegex(OSError, '36 GiB'):
            kaggle.eda(self.raw, output)
        self.assertFalse(output.exists())
        target = self.artifacts/'submissions/low-disk.csv.gz'
        disk = SimpleNamespace(total=1, used=0, free=10*1024**3-1)
        with mock.patch('shutil.disk_usage', return_value=disk), self.assertRaisesRegex(OSError, '10GiB'):
            kaggle.assemble(self.database, self.artifacts/'score-chunked', 'M2026', target, expected_customers=len(CUSTOMERS))
        self.assertEqual(list(target.parent.glob('low-disk*')), [])

    def test_provenance_reaches_every_output_and_unvalidated_databases_are_refused(self):
        record_path = self.database.with_name(kaggle.SOURCE_RECORD)
        record = json.loads(record_path.read_text(encoding='utf-8'))
        self.assertEqual({k: record[k] for k in ('format', 'valid', 'pinned_sources', 'allow_unpinned', 'database',
                                                 'verify_receipt_sha256')},
                         dict(format=kaggle.EDA_FORMAT, valid=True, pinned_sources=True, allow_unpinned=False,
                              database=dict(name='audit.duckdb', sha256=sha(self.database), bytes=self.database.stat().st_size),
                              verify_receipt_sha256=sha(self.raw/kaggle.RECEIPT)))
        sources = dict(record_sha256=sha(record_path), pinned_sources=True, allow_unpinned=False)
        plan = json.loads((self.artifacts/'score-chunked/plan.json').read_text(encoding='utf-8'))
        for value in [m['sources'] for m in self.manifests.values()]+[plan['sources'], self.submission['sources']]:
            self.assertEqual(value, sources)
        # A real EDA whose reference counts fail: exit 2, valid=false, and its DB is refused.
        invalid = self.artifacts/'eda-invalid'
        with mock.patch.dict(hm_eda.EXPECTED_ROWS, customers=len(CUSTOMERS)+1):
            code, lines = run_main(['eda', '--raw-dir', str(self.raw), '--output', str(invalid)])
        self.assertEqual((code, json.loads(lines[0])['valid']), (2, False))
        self.assertIs(json.loads((invalid/kaggle.SOURCE_RECORD).read_text(encoding='utf-8'))['valid'], False)
        with self.assertRaisesRegex(ValueError, 'did not validate'):
            kaggle.collect(invalid/'audit.duckdb', self.artifacts/'collect-invalid', '2020-09-09', 10)
        with self.assertRaisesRegex(ValueError, 'did not validate'):
            kaggle.score(invalid/'audit.duckdb', self.fits, self.artifacts/'score-invalid', chunk_users=7, threads=2)
        self.assertFalse((self.artifacts/'collect-invalid').exists())
        self.assertFalse((self.artifacts/'score-invalid').exists())
        # Copies of the audited bytes beside an edited, missing or different record.
        edits = {'invalid': ('did not validate', lambda r: r.update(valid=False)),
                 'other-bytes': ('differ from those audited', lambda r: r['database'].update(sha256='0'*64)),
                 'missing': ('must lie beside the database', None),
                 'other-record': ('provenance differs from the score plan', lambda r: r.update(allow_unpinned=True))}
        for label, (message, edit) in edits.items():
            directory = self.tmp/f'db-{label}'
            directory.mkdir()
            database = directory/'audit.duckdb'
            shutil.copy2(self.database, database)
            if edit is not None:
                changed = copy.deepcopy(record)
                edit(changed)
                (directory/kaggle.SOURCE_RECORD).write_text(json.dumps(changed), encoding='utf-8')
            submission = self.artifacts/f'submissions/db-{label}.csv.gz'
            calls = dict(assemble=lambda: kaggle.assemble(database, self.artifacts/'score-chunked', 'M2026', submission,
                                                          expected_customers=len(CUSTOMERS)))
            if label != 'other-record':  # a valid record of these bytes is a new source for collect and score
                calls.update(collect=lambda: kaggle.collect(database, self.artifacts/f'collect-db-{label}', '2020-09-09', 10),
                             score=lambda: kaggle.score(database, self.fits, self.artifacts/f'score-db-{label}',
                                                        chunk_users=7, threads=2))
            for command, call in calls.items():
                with self.subTest(label=label, command=command), self.assertRaisesRegex(ValueError, message):
                    call()
            self.assertEqual(list(submission.parent.glob(f'db-{label}*')), [])
            self.assertFalse((self.artifacts/f'collect-db-{label}').exists())
            self.assertFalse((self.artifacts/f'score-db-{label}').exists())

    def test_short_candidate_sql_equals_locked_retrieval(self):
        columns = 'customer_id,article_id,source,source_rank,candidate_rank'
        con = self.connect()
        try:
            for anchor in ('2020-09-09', '2020-09-16'):
                with self.subTest(anchor):
                    create_candidates(con, anchor, 1000)
                    expected = con.execute(f"SELECT {columns} FROM hm_r_candidates WHERE policy='C0-Q120' ORDER BY ALL").fetchall()
                    kaggle.create_item_ranks(con, anchor)
                    con.execute('CREATE OR REPLACE TEMP TABLE q AS SELECT customer_id FROM hm_r_users')
                    users = con.execute('SELECT count(*) FROM q').fetchone()[0]
                    kaggle.create_chunk_candidates(con, 'q', users)
                    self.assertEqual(con.execute(f'SELECT {columns} FROM hm_candidates ORDER BY ALL').fetchall(), expected)
                    self.assertEqual(len(expected), 120*users)
                    self.assertEqual(users, len(self.eligible(date.fromisoformat(anchor))))
                    self.assertEqual(con.execute("SELECT max(source_rank) FROM hm_candidates WHERE source='recent'").fetchone()[0], 20)
                    # A chunk of customers receives exactly its rows of the whole.
                    con.execute('''CREATE OR REPLACE TEMP TABLE q AS SELECT customer_id FROM hm_r_users
                        ORDER BY customer_id LIMIT 5''')
                    kaggle.create_chunk_candidates(con, 'q', 5)
                    subset = con.execute(f'SELECT {columns} FROM hm_candidates ORDER BY ALL').fetchall()
                    chosen = {row[0] for row in con.execute('SELECT customer_id FROM q').fetchall()}
                    self.assertEqual(subset, [row for row in expected if row[0] in chosen])
        finally:
            con.close()

    def test_collect_matches_locked_experiment_collect(self):
        root = self.tmp/'locked-root'
        (root/'scripts').mkdir(parents=True)
        (root/'artifacts').mkdir()
        for name in ('hm_retrieval.py', 'hm_feature_engine.py', 'hm_baseline.py'):
            shutil.copy2(kaggle.ROOT/'scripts'/name, root/'scripts'/name)
        with mock.patch.object(experiment, 'ROOT', root):
            locked = experiment.collect(self.database, root/'artifacts/2020-09-09', '2020-09-09', 1000, 'C0-Q120')
        ours = self.manifests['2020-09-09']
        for key in ('anchor', 'policy', 'requested_users', 'cohort_seed', 'horizon_days', 'history', 'target',
                    'database', 'features', 'population', 'files', 'qcy_identity', 'candidate_identity', 'status'):
            self.assertEqual(ours[key], locked[key], key)
        self.assertEqual(ours['format'], kaggle.COLLECTION_FORMAT)
        for name in ('frame.parquet', 'users.parquet', 'targets.parquet'):
            self.assertEqual(sha(self.collections['2020-09-09']/name), sha(root/'artifacts/2020-09-09'/name))
        self.assertEqual(ours['code']['hm_experiment.py'], locked['code']['hm_experiment.py'])

    def test_collect_compares_users_with_the_gpu_lock_pins(self):
        lock = kaggle.read_lock()
        pins = {c['anchor']: c['users'] for c in lock['train_collections']}
        for anchor in ('2020-09-02', '2020-09-09'):
            self.assertEqual(self.manifests[anchor]['lock_users'],
                             dict(sha256=pins[anchor]['sha256'], bytes=pins[anchor]['bytes'], matches=False))
        self.assertIsNone(self.manifests['2020-09-16']['lock_users'])
        users = self.collections['2020-09-09']/'users.parquet'
        for entry in lock['train_collections']:
            if entry['anchor'] == '2020-09-09':
                entry['users'].update(sha256=sha(users), bytes=users.stat().st_size)
        with mock.patch.object(kaggle, 'read_lock', return_value=lock):
            manifest = kaggle.collect(self.database, self.artifacts/'collect-pinned', '2020-09-09', 1000)
        self.assertTrue(manifest['lock_users']['matches'])

    def test_label_anchor_guard_and_empty_label_week(self):
        self.assertEqual(kaggle.check_label_anchor('2020-09-16'), date(2020, 9, 16))
        with self.assertRaises(ValueError):
            experiment.check_anchor('2020-09-16')
        for anchor in ('2020-09-17', '2020-09-23'):
            output = self.artifacts/f'guard-{anchor}'
            with self.subTest(anchor), self.assertRaisesRegex(ValueError, '2020-09-23'):
                kaggle.collect(self.database, output, anchor, 10)
            self.assertFalse(output.exists())
        output = self.artifacts/'guard-empty-week'
        with self.assertRaisesRegex(ValueError, 'no positives'):
            kaggle.collect(self.database, output, '2020-07-01', 1000)
        manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((manifest['status'], manifest['label_week']['target_pairs']), ('failed', 0))
        self.assertFalse((output/'frame.parquet').exists())
        with self.assertRaisesRegex(ValueError, 'artifacts'):
            kaggle.collect(self.database, self.tmp/'outside', '2020-09-09', 10)

    def test_recipe_comes_from_locks_and_states_cpu_choices(self):
        for arm, width in (('M', 18), ('E', 41)):
            recipe = LOCKED_RECIPE(arm, 2027, 3)
            self.assertEqual((len(recipe['numeric']), recipe['categorical']), (width, list(CATEGORICAL_FEATURES)))
            self.assertEqual(recipe['numeric'][:18], list(PILOT_NUMERIC_FEATURES))
            params = recipe['hyperparameters']
            self.assertEqual({k: params[k] for k in ('task_type', 'bootstrap_type', 'bagging_temperature', 'border_count',
                                                     'boosting_type', 'iterations', 'depth', 'l2_leaf_reg', 'random_seed',
                                                     'thread_count')},
                             dict(task_type='CPU', bootstrap_type='Bayesian', bagging_temperature=1, border_count=128,
                                  boosting_type='Plain', iterations=500, depth=8, l2_leaf_reg=10, random_seed=2027,
                                  thread_count=3))
            self.assertFalse(set(kaggle.GPU_ONLY) & set(params))
            self.assertEqual(recipe['gpu_hyperparameters'], experiment.fixed_parameters(500, 8, 2027, 'GPU'))
            self.assertEqual((recipe['train_users'], recipe['negative_sample'], recipe['sampling_seed']), (20000, 20, 2026))
        for arm, seed, threads in (('X', 2026, 1), ('M', 2028, 1), ('E', 2026, 0)):
            with self.subTest(arm=arm, seed=seed), self.assertRaises(ValueError):
                LOCKED_RECIPE(arm, seed, threads)
        self.assertEqual(kaggle.code_identity()['hm_feature_engine.py'], kaggle.read_lock()['implementation']['code']['hm_feature_engine.py'])
        with mock.patch.object(kaggle, 'LOCK_SHA256', '0'*64), self.assertRaises(ValueError):
            kaggle.code_identity()

    def test_fit_reports_validation_map_and_resolved_cpu_parameters(self):
        self.assertEqual(self.port['features']['numeric'], list(PILOT_NUMERIC_FEATURES))
        self.assertEqual(len(self.final['features']['numeric']), 41)
        self.assertNotIn('validation_metrics', self.final)
        resolved = json.loads((self.fits[0]/'params.json').read_text(encoding='utf-8'))
        self.assertEqual({k: resolved[k] for k in ('task_type', 'bootstrap_type', 'border_count', 'boosting_type', 'random_seed')},
                         dict(task_type='CPU', bootstrap_type='Bayesian', border_count=128, boosting_type='Plain', random_seed=2026))
        self.assertEqual([p['selected_queries'] for p in self.port['training_populations']], [20, 20])
        metrics = self.port['validation_metrics']
        con = self.memory()
        try:
            positive, mean_ap, pairs = con.execute('''SELECT count(*),avg(ap12),sum(targets) FROM read_parquet(?)
                WHERE targets>0''', [str(self.fits[0]/'query-metrics.parquet')]).fetchone()
        finally:
            con.close()
        self.assertEqual(metrics['positive_queries'], positive)
        self.assertEqual(metrics['positive_queries'], self.manifests['2020-09-16']['label_week']['buyers'])
        self.assertEqual(metrics['distinct_query_target_pairs'], self.manifests['2020-09-16']['population']['target_pairs'])
        self.assertEqual(pairs, metrics['distinct_query_target_pairs'])
        self.assertAlmostEqual(metrics['map_at_12_conditional'], mean_ap, places=12)

    def test_chunked_scoring_equals_unchunked(self):
        users = len(self.eligible(kaggle.SCORE_ANCHOR))
        self.assertEqual((self.whole['users'], self.chunked['users']), (users, users))
        self.assertEqual((self.whole['chunks'], self.chunked['chunks']), (1, math.ceil(users/7)))
        for model in ('M2026', 'E2027'):
            whole = self.top_rows(self.artifacts/'score-whole', model)
            self.assertEqual(self.top_rows(self.artifacts/'score-chunked', model), whole)
            self.assertEqual(len(whole), 12*users)
            self.assertEqual({row[0] for row in whole}, self.eligible(kaggle.SCORE_ANCHOR))
        receipt = json.loads((self.artifacts/'score-chunked/chunk-0000.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['users'], 7)
        self.assertGreater(receipt['peak_rss_bytes'], 0)
        # Atomic receipts and per-process spill leave nothing behind after the fixture's runs.
        for name in ('eda', 'collections', 'fits', 'score-whole', 'score-chunked', 'submissions'):
            self.assertEqual(leftovers(self.artifacts/name), [], name)

    def test_score_resumes_finished_chunks_and_refuses_changed_plan(self):
        directory = self.artifacts/'score-resume'
        shutil.copytree(self.artifacts/'score-chunked', directory)
        before = {p.name: sha(p) for p in directory.glob('top12-*.parquet')}
        with redirect_stderr(io.StringIO()):
            again = kaggle.score(self.database, self.fits, directory, chunk_users=7, threads=2)
            self.assertEqual((again['computed'], again['skipped']), (0, self.chunked['chunks']))
            # An interrupted chunk: its files may exist, its receipt does not.
            (directory/'chunk-0002.json').unlink()
            (directory/'top12-E2027-0002.parquet').unlink()
            again = kaggle.score(self.database, self.fits, directory, chunk_users=7, threads=2)
        self.assertEqual((again['computed'], again['skipped']), (1, self.chunked['chunks']-1))
        self.assertEqual({p.name: sha(p) for p in directory.glob('top12-*.parquet')}, before)
        plan, report = sha(directory/'plan.json'), sha(directory/'report.json')
        self.assertEqual(json.loads((directory/'plan.json').read_text(encoding='utf-8'))['threads'], 2)
        # Another chunk size or thread count is another plan; the refusal writes nothing.
        for chunk_users, threads in ((8, 2), (7, 1)):
            with self.subTest(chunk_users=chunk_users, threads=threads), redirect_stderr(io.StringIO()), \
                    self.assertRaisesRegex(ValueError, 'plan differs'):
                kaggle.score(self.database, self.fits, directory, chunk_users=chunk_users, threads=threads)
        self.assertEqual((sha(directory/'plan.json'), sha(directory/'report.json')), (plan, report))
        self.assertEqual(leftovers(directory), [])

    def test_score_caps_chunk_size_before_writing(self):
        self.assertEqual(kaggle.MAX_CHUNK_USERS, 50000)
        output = self.artifacts/'score-cap'
        with self.assertRaisesRegex(ValueError, '1..50000'):
            kaggle.score(self.database, self.fits, output, chunk_users=50001, threads=2)
        code, lines = run_main(self.score_argv(output, '--chunk-users', '50001'))
        self.assertEqual((code, json.loads(lines[0])['error_type']), (1, 'ValueError'))
        self.assertFalse(output.exists())

    def test_score_lock_refuses_a_second_process_until_the_first_exits(self):
        directory = self.artifacts/'score-locked'
        shutil.copytree(self.artifacts/'score-chunked', directory)
        holder = subprocess.Popen([sys.executable, '-I', '-c', HOLDER, str(kaggle.ROOT), str(directory/'score.lock')],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline(), 'locked\n')
            before = {p.name: sha(p) for p in directory.iterdir()}
            code, lines = run_main(self.score_argv(directory))
            self.assertEqual((code, len(lines)), (1, 1))
            self.assertEqual(json.loads(lines[0]), dict(status='failed', command='score', error_type='RuntimeError',
                                                        message='Another process holds score.lock; wait until it exits'))
            self.assertEqual({p.name: sha(p) for p in directory.iterdir()}, before)
        finally:
            holder.stdin.close()
            holder.wait(timeout=60)
            holder.stdout.close()
        # The lock ends with its process; the same command then resumes.
        with redirect_stderr(io.StringIO()):
            again = kaggle.score(self.database, self.fits, directory, chunk_users=7, threads=2)
        self.assertEqual((again['computed'], again['skipped']), (0, self.chunked['chunks']))

    def test_interrupt_after_the_deadline_is_reported_as_the_wall_limit(self):
        real, made = experiment.Deadline, []

        def recording(seconds):
            made.append(real(seconds))
            return made[-1]

        def interrupted(con, *args, **kwargs):
            # The newest deadline is cut to 0.3 s; its own wall timer interrupts an endless query.
            deadline = made[-1]
            deadline.expires = time.monotonic()+0.3
            timer = deadline.interrupt_sql(con)
            try:
                con.execute(ENDLESS).fetchone()
            finally:
                timer.cancel()
        a = self.artifacts
        cases = [(hm_retrieval, 'create_candidates', a/'collect-timeout/manifest.json',
                  ['collect', '--database', str(self.database), '--output', str(a/'collect-timeout'), '--anchor', '2020-09-09']),
                 (kaggle, 'create_item_ranks', a/'score-timeout/report.json', self.score_argv(a/'score-timeout')),
                 (kaggle, 'ordered_digest', None, ['assemble', '--database', str(self.database), '--scores',
                                                   str(a/'score-chunked'), '--model', 'M2026',
                                                   '--output', str(a/'submissions/timeout.csv.gz')])]
        for target, name, record, argv in cases:
            with self.subTest(argv[0]), mock.patch.object(experiment, 'Deadline', recording), \
                    mock.patch.object(target, name, interrupted):
                code, lines = run_main(argv)
                self.assertEqual((code, len(lines)), (1, 1))
                self.assertEqual(json.loads(lines[0]), dict(WALL, command=argv[0]))
                if record is not None:
                    error = json.loads(record.read_text(encoding='utf-8'))['error']
                    self.assertEqual((error['type'], error['message'], error['cause']),
                                     ('TimeoutError', WALL['message'], 'InterruptException'))
        self.assertFalse((a/'score-timeout/plan.json').exists())
        self.assertEqual(list((a/'submissions').glob('timeout*')), [])
        # Before the deadline an interrupt stays a native error; other errors are never renamed.
        error, other = duckdb.InterruptException('INTERRUPT Error: Interrupted!'), ValueError('rows')
        live, spent = real(60), real(60)
        spent.expires = time.monotonic()-1
        self.assertIs(kaggle.wall_limit(error, live), error)
        self.assertIs(kaggle.wall_limit(other, spent), other)
        self.assertEqual(str(kaggle.wall_limit(error, spent)), WALL['message'])

    def test_assemble_uses_scored_top12_and_last_week_popular_fallback(self):
        lines = read_lines(self.submission_path)
        self.assertEqual(lines[0], 'customer_id,prediction\n')
        rows = dict(line.rstrip('\n').split(',') for line in lines[1:])
        self.assertEqual(list(rows), sorted(CUSTOMERS))
        buyers = {}
        for d, u, a in self.rows:
            if date(2020, 9, 16) <= d < date(2020, 9, 23):
                buyers.setdefault(a, set()).add(u)
        popular = sorted(buyers, key=lambda a: (-len(buyers[a]), a))[:12]
        top = {}
        for customer, article, _, _ in self.top_rows(self.artifacts/'score-chunked', 'M2026'):
            top.setdefault(customer, []).append(article)
        eligible = self.eligible(kaggle.SCORE_ANCHOR)
        for customer in CUSTOMERS:
            expected = top[customer] if customer in eligible else popular
            self.assertEqual(rows[customer].split(' '), expected)
        self.assertEqual((self.submission['rows'], self.submission['popular_fallback_customers'], self.submission['popular_last7']),
                         (len(CUSTOMERS), len(CUSTOMERS)-len(eligible), popular))
        self.assertEqual(self.submission['file']['sha256'], sha(self.submission_path))
        self.assertFalse(self.submission_path.with_name(self.submission_path.name+'.part').exists())
        with self.assertRaises(FileExistsError):
            kaggle.assemble(self.database, self.artifacts/'score-chunked', 'M2026', self.submission_path,
                            expected_customers=len(CUSTOMERS))

        def repeated_rank(frame):
            # Twelve distinct articles, ranks 1 and 12 present, but rank 11 missing and 12 twice.
            first = frame['customer_id'].iloc[0]
            frame.loc[(frame['customer_id'] == first) & (frame['rank'] == 11), 'rank'] = 12
            return frame
        # A short list or a repeated rank is refused, not repaired, even with a re-signed receipt.
        for label, edit in (('short', lambda frame: frame.iloc[:-1]), ('repeated-rank', repeated_rank)):
            broken = self.broken_scores(f'score-{label}', edit)
            output = self.artifacts/f'submissions/{label}.csv.gz'
            with self.subTest(label), self.assertRaisesRegex(ValueError, 'Scored top 12'):
                kaggle.assemble(self.database, broken, 'M2026', output, expected_customers=len(CUSTOMERS))
            self.assertEqual(list(output.parent.glob(f'{label}*')), [])

    def test_submission_checks_reject_bad_files(self):
        lines = read_lines(self.submission_path)
        customers = set(CUSTOMERS)
        articles = set(ARTICLES)
        first, last = lines[1], lines[-1]
        customer, prediction = first.rstrip('\n').split(',')
        items = prediction.split(' ')
        bad = {
            'header': ['customer_id,predictions\n']+lines[1:],
            'missing customer': lines[:-1],
            'duplicate customer': lines[:-1]+[first],
            'unknown customer': lines[:-1]+['f'*64+','+last.rstrip('\n').split(',')[1]+'\n'],
            'eleven items': [lines[0], f"{customer},{' '.join(items[:11])}\n"]+lines[2:],
            'duplicate item': [lines[0], f"{customer},{' '.join(items[:11]+items[:1])}\n"]+lines[2:],
            'unknown item': [lines[0], f"{customer},{' '.join(items[:11]+['9999999999'])}\n"]+lines[2:],
            'unpadded item': [lines[0], f"{customer},{' '.join(items[:11]+[ARTICLES[-1][1:]])}\n"]+lines[2:],
            'crlf': [lines[0], first.replace('\n', '\r\n')]+lines[2:],
            'extra field': [lines[0], first.replace('\n', ',x\n')]+lines[2:],
            'no final newline': lines[:-1]+[last.rstrip('\n')],
        }
        self.assertEqual(kaggle.check_submission(self.submission_path, customers, articles), dict(rows=len(CUSTOMERS)))
        for label, content in bad.items():
            path = self.tmp/f"bad-{label.replace(' ', '-')}.csv"
            path.write_text(''.join(content), encoding='utf-8', newline='')
            with self.subTest(label), self.assertRaises(ValueError):
                kaggle.check_submission(path, customers, articles)
        path = self.tmp/'bad-gzip.csv.gz'
        with gzip.open(path, 'wt', encoding='utf-8', newline='') as stream:
            stream.write(''.join(bad['duplicate item']))
        with self.assertRaises(ValueError):
            kaggle.check_submission(path, customers, articles)

    def test_cli_prints_one_json_summary_per_command(self):
        c, cli = self.collections, self.artifacts/'cli'
        commands = [
            ['eda', '--raw-dir', str(self.raw), '--output', str(cli/'eda')],
            ['collect', '--database', str(self.database), '--output', str(cli/'collect'), '--anchor', '2020-09-09',
             '--users', '1000'],
            ['fit', '--arm', 'M', '--seed', '2027', '--train', str(c['2020-09-02']), str(c['2020-09-09']),
             '--validation', str(c['2020-09-16']), '--output', str(cli/'M2027'), '--threads', '2'],
            ['score', '--database', str(self.database), '--fits', *map(str, self.fits), '--output', str(cli/'score'),
             '--chunk-users', '1000', '--threads', '2'],
            ['assemble', '--database', str(self.database), '--scores', str(cli/'score'), '--model', 'M2026',
             '--output', str(cli/'M2026.csv.gz')],
            ['collect', '--database', str(self.database), '--output', str(cli/'late'), '--anchor', '2020-09-17'],
        ]
        printed = []
        for argv in commands:
            code, lines = run_main(argv)
            self.assertEqual(len(lines), 1, argv[0])
            printed.append((code, json.loads(lines[0])))
        self.assertEqual([code for code, _ in printed], [0, 0, 0, 0, 0, 1])
        eda, collect, fit, score, assemble, late = (value for _, value in printed)
        self.assertEqual((eda['valid'], eda['pinned_sources'], eda['allow_unpinned'], set(eda['reference_rows'].values())),
                         (True, True, False, {True}))
        self.assertEqual(eda['database'], (cli/'eda/audit.duckdb').resolve().as_posix())
        self.assertEqual({k: collect[k] for k in ('buyers', 'target_pairs', 'positive_candidate_rows')},
                         self.manifests['2020-09-09']['label_week'])
        self.assertIs(collect['lock_users_match'], False)
        self.assertEqual((fit['model'], fit['trees'], fit['train_queries'], fit['queries']), ('M2027', 25, 40, 36))
        self.assertEqual(fit['train_positive_rows'], sum(p['positive_rows'] for p in self.port['training_populations']))
        self.assertEqual(fit['positive_queries'], self.manifests['2020-09-16']['label_week']['buyers'])
        self.assertEqual(fit['oracle_map_at_12_conditional'], self.port['validation_metrics']['oracle_map_at_12_conditional'])
        self.assertEqual(score, dict(status='completed', users=36, chunks=1, computed=1, skipped=0))
        # Unchunked scores give the very bytes assembled from chunked scores.
        self.assertEqual((assemble['rows'], assemble['popular_fallback_customers'], assemble['sha256']),
                         (len(CUSTOMERS), 12, sha(self.submission_path)))
        self.assertEqual((late['status'], late['error_type']), ('failed', 'ValueError'))
        self.assertFalse((cli/'late').exists())

    def test_cli_failures_do_not_echo_source_rows(self):
        raw = self.tmp/'bad-row'
        shutil.copytree(self.staging, raw)
        path = raw/'transactions_train.csv'
        lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
        fields = lines[1].split(',')
        fields[list(SCHEMAS['transactions']).index('price')] = 'SECRET-ROW'
        lines[1] = ','.join(fields)
        path.write_text(''.join(lines), encoding='utf-8', newline='')
        kaggle.verify(raw, write_config(self.tmp/'bad-row.json', raw))
        with self.assertRaises(Exception) as native:
            hm_eda.run(raw, self.artifacts/'eda-bad-row-direct')
        self.assertIn('SECRET-ROW', str(native.exception))  # the leak being guarded against
        failing = [(['eda', '--raw-dir', str(raw), '--output', str(self.artifacts/'eda-bad-row'), '--allow-unpinned'], {}),
                   (['collect', '--database', str(self.database), '--output', str(self.artifacts/'native'),
                     '--anchor', '2020-09-09'],
                    dict(collect=mock.Mock(side_effect=duckdb.ConversionException('Could not convert SECRET-ROW'))))]
        printed = []
        for argv, patches in failing:
            code, lines = run_main(argv, **patches)
            self.assertEqual((code, len(lines)), (1, 1))
            self.assertNotIn('SECRET', lines[0])
            printed.append(json.loads(lines[0]))
        self.assertTrue(printed[0]['message'].startswith('hm_eda ingestion failed ('))
        self.assertEqual(printed[1]['error_type'], 'ConversionException')

    def test_cohort_order_matches_hm_baseline_key(self):
        users = self.eligible(kaggle.SCORE_ANCHOR)
        order = sorted(users, key=lambda u: (cohort_key(u, 2026), u))
        con = self.connect()
        try:
            digest = kaggle.ordered_digest(con, 'SELECT unnest(?::VARCHAR[])', [order])
        finally:
            con.close()
        plan = json.loads((self.artifacts/'score-chunked/plan.json').read_text(encoding='utf-8'))
        self.assertEqual(plan['users_digest'], digest)


if __name__ == '__main__':
    unittest.main()
