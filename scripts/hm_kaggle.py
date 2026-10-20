"""CPU Kaggle late submission for the locked H&M models M23 and E46.

Locked modules are reused by import and never edited; their SHA-256 pins in
configs/datasets/hm-auto-holdout-lock.json are checked before any output. Run
as ``python -I scripts/hm_kaggle.py``: isolated mode keeps the working and data
directories and PYTHONPATH off sys.path, and only this checkout root is added
below; verify, eda and collect refuse to run otherwise. Every row-level output
(DB, collections, models, scores, submissions) stays inside the ignored
artifacts/ tree.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import hm_experiment as experiment  # noqa: E402

pilot = experiment.pilot
ARTIFACTS = ROOT/'artifacts'
LOCK = ROOT/'configs/datasets/hm-auto-holdout-lock.json'
LOCK_SHA256 = 'a04ef587b05c37f33694175d172ef47dc981242b84edf7cd0f4fd5f5b02ce3a1'
FINAL_LOCK = ROOT/'configs/datasets/hm-final-lock.json'
FINAL_LOCK_SHA256 = 'd47df2aca05311a0e56aa645dbd5c20097ca9bcf656256dc4db8120059a05e80'
SOURCE_CONFIG = ROOT/'configs/datasets/hm-source.json'
SOURCE_SHA256 = '8f6e2b6cbf69c207ae2a5993403e913166dc703b72473248396ca071e548466f'
LOCKED_MODULES = ('hm_experiment.py', 'hm_retrieval.py', 'hm_feature_engine.py', 'hm_baseline.py', 'hm_eda.py')
# Transactions end on 2020-09-22. Labelled weeks must fit before 09-23; the
# Kaggle test week starts there and is scored from history only.
LABEL_END = date(2020, 9, 23)
SCORE_ANCHOR = LABEL_END
POLICY = 'C0-Q120'
SEED = experiment.SEED
GPU_ONLY = ('devices', 'gpu_ram_part', 'pinned_memory_size')
CHECKED_PARAMETERS = ('task_type', 'iterations', 'depth', 'learning_rate', 'l2_leaf_reg', 'loss_function',
                      'random_seed', 'bootstrap_type', 'bagging_temperature', 'border_count', 'boosting_type')
RECEIPT = 'kaggle-verify.json'
SOURCE_RECORD = 'kaggle-source.json'
SOURCE_FORMAT = 'hm-kaggle-source-v1'
EDA_FORMAT = 'hm-kaggle-eda-source-v1'
COLLECTION_FORMAT = 'hm-kaggle-collection-v1'
FIT_FORMAT = 'hm-kaggle-fit-v1'
PLAN_FORMAT = 'hm-kaggle-score-plan-v1'
CHUNK_FORMAT = 'hm-kaggle-score-chunk-v1'
SCORE_FORMAT = 'hm-kaggle-score-v1'
SUBMISSION_FORMAT = 'hm-kaggle-submission-v1'
HEADER = 'customer_id,prediction\n'
ITEM = re.compile('[0-9]{10}')
NATIVE_ERRORS = ('duckdb', 'catboost', 'pandas', 'numpy', 'pyarrow')
# Commands that read downloaded files run only under ``python -I``.
ISOLATED_COMMANDS = ('verify', 'eda', 'collect')
MAX_CHUNK_USERS = 50000
# hm_eda caps its spill at 32GB; audit.duckdb (~1.2 GB) and summaries need the rest.
EDA_FREE_BYTES = 36*1024**3
WALL_LIMIT = 'Declared wall limit exceeded'


class ArchiveError(ValueError):
    """A refusal of a downloaded archive, worded here and never by the archive."""


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    """Command-line mistakes become the one-line JSON failure, not usage text."""

    def error(self, message):
        raise UsageError(message)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, value):
    """Write a receipt completely or not at all; a crash leaves only this process's *.part."""
    path = Path(path)
    partial = path.with_name(f'{path.name}.{os.getpid()}.part')
    experiment.write_json(partial, value)
    os.replace(partial, path)


def isolated():
    return bool(sys.flags.isolated)


def peak_rss_bytes():
    try:
        import resource
    except ImportError:  # Windows
        return None
    # Darwin reports bytes, Linux KiB. A process high-water mark, not per chunk.
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == 'darwin' else value*1024)


def current_rss_bytes():
    try:
        import psutil
    except ImportError:
        return None
    return psutil.Process().memory_info().rss


def private_path(output):
    path = Path(output).resolve()
    allowed = ARTIFACTS.resolve()
    if path == allowed or not path.is_relative_to(allowed):
        raise ValueError('Row-level outputs must stay inside checkout artifacts/')
    return path


def new_output(output):
    path = private_path(output)
    path.mkdir(parents=True, exist_ok=False)
    return path


def existing_ancestor(path):
    path = Path(path)
    while not path.exists():
        path = path.parent
    return path


def hold_lock(path):
    """Exclusive advisory lock on a file; the OS drops it when the process ends."""
    handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(handle)
        raise RuntimeError(f'Another process holds {Path(path).name}; wait until it exits') from None
    return handle


def release_lock(handle):
    try:
        if os.name == 'nt':
            import msvcrt
            os.lseek(handle, 0, os.SEEK_SET)
            msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(handle)


def wall_limit(exc, deadline):
    """Past the deadline, an interrupted query is the declared limit, not a native failure.

    The wall timer interrupts DuckDB (InterruptException, "INTERRUPT Error:
    Interrupted!"); any other interruption after the deadline is reported alike.
    """
    interrupted = 'Interrupt' in type(exc).__name__ or 'interrupt' in str(exc).lower()
    if interrupted and time.monotonic() >= deadline.expires:
        return TimeoutError(WALL_LIMIT)
    return exc


def failure(report, exc, deadline):
    """Record a failure in the output's report; return the exception to raise."""
    error = wall_limit(exc, deadline)
    report['status'] = 'failed'
    report['error'] = dict(type=type(error).__name__, message=str(error)[:2048],
                           traceback=traceback.format_exc(limit=12)[-8192:])
    if error is not exc:
        report['error']['cause'] = type(exc).__name__
    return error


def database_sources(database, identity):
    """kaggle-source.json beside the DB: eda validated exactly these bytes."""
    path = Path(database).resolve().with_name(SOURCE_RECORD)
    if not path.is_file():
        raise ValueError(f'{SOURCE_RECORD} from hm_kaggle eda must lie beside the database')
    record = read_json(path)
    audited = record.get('database')
    if (record.get('format') != EDA_FORMAT or not isinstance(audited, dict) or
            (audited.get('sha256'), audited.get('bytes')) != (identity['sha256'], identity['bytes'])):
        raise ValueError(f'Database bytes differ from those audited in {SOURCE_RECORD}')
    if record.get('valid') is not True:
        raise ValueError('EDA of this database did not validate; it is not used')
    return dict(record_sha256=experiment.sha256_file(path), pinned_sources=record['pinned_sources'],
                allow_unpinned=record['allow_unpinned'])


def check_label_anchor(anchor):
    cutoff = date.fromisoformat(anchor) if isinstance(anchor, str) else anchor
    if type(cutoff) is not date or cutoff+timedelta(days=7) > LABEL_END:
        raise ValueError('Labelled anchors need anchor+7d <= 2020-09-23; transactions end on 2020-09-22')
    return cutoff


def read_lock():
    raw = LOCK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LOCK_SHA256:
        raise ValueError('hm-auto-holdout-lock.json differs from its committed SHA-256')
    return json.loads(raw)


def code_identity(deadline=None):
    """Refuse to run unless the reused modules are byte-equal to the lock pins."""
    from scripts import hm_eda, hm_feature_engine, hm_retrieval
    modules = {'hm_experiment.py': experiment, 'hm_retrieval.py': hm_retrieval,
               'hm_feature_engine.py': hm_feature_engine, 'hm_baseline.py': pilot, 'hm_eda.py': hm_eda}
    pins = read_lock()['implementation']['code']
    code = {}
    for name in LOCKED_MODULES:
        path = ROOT/'scripts'/name
        if Path(modules[name].__file__).resolve() != path.resolve():
            raise ImportError(f'{name} was imported from outside this checkout')
        code[name] = experiment.sha256_file(path, deadline)
        if code[name] != pins[name]:
            raise ValueError(f'{name} differs from its pinned SHA-256; locked code must not change')
    code['hm_kaggle.py'] = experiment.sha256_file(Path(__file__), deadline)
    return code


def locked_recipe(arm, seed, threads=4):
    """Locked M23/E46 vectors and the GPU recipe restated for CPU.

    Feature names come from the lock in its order and are cross-checked with the
    engine and the v1 final lock. CPU keeps every explicit GPU choice (Bayesian
    bootstrap, temperature 1, 128 borders, Plain); only device keys are dropped.
    """
    from scripts.hm_feature_engine import CATEGORICAL_FEATURES, PILOT_NUMERIC_FEATURES, feature_manifest, feature_registry
    lock = read_lock()
    training = lock['training']
    if arm not in ('M', 'E') or type(seed) is not int or seed not in training['model_seeds']:
        raise ValueError('Arm M/E and a locked model seed are required')
    if type(threads) is not int or threads < 1:
        raise ValueError('A positive integer thread count is required')
    manual = dict(numeric=list(PILOT_NUMERIC_FEATURES), categorical=list(CATEGORICAL_FEATURES))
    raw = FINAL_LOCK.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FINAL_LOCK_SHA256:
        raise ValueError('hm-final-lock.json differs from its committed SHA-256')
    final = json.loads(raw)
    if lock['features']['M'] != manual or final['features']['M'] != manual or final['feature_digest'] != feature_manifest()['digest']:
        raise ValueError('Locked M23 vector or feature engine differs')
    numeric, categorical = list(lock['features'][arm]['numeric']), list(lock['features'][arm]['categorical'])
    kinds = {d.name: d.operation == 'categorical' for d in feature_registry()}
    if (numeric[:len(PILOT_NUMERIC_FEATURES)] != manual['numeric'] or categorical != manual['categorical'] or
            len(set(numeric+categorical)) != len(numeric)+len(categorical) or
            any(kinds.get(name) is not False for name in numeric) or any(kinds.get(name) is not True for name in categorical)):
        raise ValueError('Locked feature vector is not registered in the engine')
    gpu = dict(lock['hyperparameters'][arm], random_seed=seed)
    if gpu != experiment.fixed_parameters(500, 8, seed, 'GPU'):
        raise ValueError('Locked recipe differs from the canonical GPU recipe')
    cpu = {key: value for key, value in gpu.items() if key not in GPU_ONLY}
    cpu.update(task_type='CPU', thread_count=threads)
    if training['sampling_seed'] != SEED or training['negative_sample'] not in (0, 20):
        raise ValueError('Locked training sampler differs from hm_experiment')
    return dict(arm=arm, seed=seed, numeric=numeric, categorical=categorical, hyperparameters=cpu,
                gpu_hyperparameters=gpu, train_users=training['train_users'],
                negative_sample=training['negative_sample'], sampling_seed=training['sampling_seed'])


def same_value(actual, expected):
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        # CatBoost stores the learning rate as float32.
        return math.isclose(actual, expected, rel_tol=1e-6, abs_tol=0)
    return actual == expected


def read_source_config(path):
    from scripts.hm_eda import FILES
    config = read_json(path)
    files = config['files']
    names = [Path(spec['path']).name for spec in files]
    if sorted(names) != sorted(FILES.values()) or len(names) != len(FILES):
        raise ValueError('Source config must pin exactly the three original CSV tables')
    for spec, name in zip(files, names):
        if (spec['path'] != 'data/raw/'+name or type(spec['size']) is not int or spec['size'] < 1 or
                not re.fullmatch('[0-9a-f]{64}', spec['sha256'])):
            raise ValueError('Unexpected pinned path, size or SHA-256')
    return config, dict(zip(names, files))


def hash_stream(stream, sink, limit, label):
    """Copy/hash in blocks; never accept more bytes than declared."""
    digest, total, started, shown = hashlib.sha256(), 0, time.monotonic(), time.monotonic()
    while block := stream.read(8*1024*1024):
        total += len(block)
        if total > limit:
            raise ArchiveError(f'{label}: more bytes than declared')
        digest.update(block)
        if sink is not None:
            sink.write(block)
        if time.monotonic()-shown >= 15:
            shown = time.monotonic()
            print(f'{label}: {total/1024**2:.0f} MiB, {total/1024**2/(shown-started):.1f} MiB/s', file=sys.stderr, flush=True)
    return total, digest.hexdigest()


def extract_single(archive, target, pinned_size):
    """Stream the one expected CSV out of a Kaggle per-file zip; nothing else.

    zipfile and zlib messages can quote names or bytes chosen by the archive, so
    their errors are reported by type under a fixed message.
    """
    partial = target.with_name(target.name+'.part')
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) != 1 or members[0].filename != target.name or members[0].is_dir():
                raise ArchiveError(f'{archive.name} must contain exactly {target.name}')
            info = members[0]
            if info.flag_bits & 0x1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ArchiveError(f'{archive.name}: encrypted or unsupported member')
            if not 0 < info.file_size <= 2*pinned_size:
                raise ArchiveError(f'{archive.name}: declared size is implausible for the pinned table')
            if shutil.disk_usage(target.parent).free < info.file_size+2*1024**3:
                raise OSError('Extraction needs the CSV size plus a 2 GiB reserve')
            # Exclusive creation: a stale partial from a crash is never adopted.
            with bundle.open(info) as stream, partial.open('xb') as sink:
                total, digest = hash_stream(stream, sink, info.file_size, target.name)
    except (ArchiveError, OSError):
        raise
    except Exception as exc:  # BadZipFile, zlib.error, EOFError and any other zipfile failure
        raise ArchiveError(f'{archive.name} is damaged or unreadable ({type(exc).__name__}); '
                           'download it again into a new directory') from None
    if total != info.file_size:
        raise ArchiveError(f'{archive.name}: member shorter than declared; partial preserved')
    partial.rename(target)
    return total, digest


def verify(raw_dir, config=SOURCE_CONFIG):
    """Compare downloaded CSVs with the pins used by the GPU runs; write a receipt.

    A CSV present in raw_dir is hashed. Otherwise ``<name>.zip`` (the kaggle CLI
    per-file download) must contain exactly that CSV; it is extracted once next
    to the archive. Archives are never deleted. Mismatches are recorded, not hidden.
    """
    raw_dir = Path(raw_dir).resolve()
    if not raw_dir.is_dir():
        raise FileNotFoundError('Raw directory does not exist')
    config_path = Path(config).resolve()
    source, pins = read_source_config(config_path)
    report = dict(format=SOURCE_FORMAT, status='running', dataset=source['dataset'], mirror=source['mirror'],
                  revision=source['revision'], config=dict(path=config_path.name, sha256=experiment.sha256_file(config_path)),
                  checksum_scope='Downloaded Kaggle bytes against the hm-source.json pins of the GPU runs',
                  started_at_utc=utc_now(), files=[])
    try:
        for name, pin in pins.items():
            target, archive = raw_dir/name, raw_dir/(name+'.zip')
            extracted = None
            if target.exists():
                with target.open('rb') as stream:
                    size, digest = hash_stream(stream, None, math.inf, name)
            elif archive.exists():
                extracted = dict(name=archive.name, bytes=archive.stat().st_size, sha256=experiment.sha256_file(archive))
                size, digest = extract_single(archive, target, pin['size'])
            else:
                raise FileNotFoundError(f'{name} and {name}.zip are both missing')
            stat = target.stat()
            report['files'].append(dict(name=name, size=size, sha256=digest, mtime_ns=stat.st_mtime_ns,
                                        extracted_from=extracted, pinned_size=pin['size'], pinned_sha256=pin['sha256'],
                                        matches=(size, digest) == (pin['size'], pin['sha256'])))
        report['status'] = 'complete' if all(f['matches'] for f in report['files']) else 'mismatch'
    except Exception as exc:
        # Local I/O or this module's checks; extract_single rewords archive errors.
        report['status'] = 'failed'
        report['error'] = dict(type=type(exc).__name__, message=str(exc)[:2048])
        raise
    finally:
        report['finished_at_utc'] = utc_now()
        atomic_json(raw_dir/RECEIPT, report)
    return report


def eda(raw_dir, output, allow_unpinned=False):
    """Run the locked hm_eda ingestion on verified CSVs and keep the provenance.

    kaggle-source.json beside audit.duckdb records validity, source pins and
    the DB bytes; collect, score and assemble refuse a DB without a valid one.
    """
    from scripts import hm_eda
    raw_dir = Path(raw_dir).resolve()
    receipt_path = raw_dir/RECEIPT
    receipt = read_json(receipt_path)
    if receipt.get('format') != SOURCE_FORMAT or receipt.get('status') not in ('complete', 'mismatch'):
        raise ValueError('Run verify first; a finished verification receipt is required')
    pinned = receipt['status'] == 'complete' and receipt['config']['sha256'] == SOURCE_SHA256
    if not pinned and not allow_unpinned:
        raise ValueError('Sources differ from the GPU-run pins; continue only by an explicit --allow-unpinned decision')
    if sorted(entry['name'] for entry in receipt['files']) != sorted(hm_eda.FILES.values()):
        raise ValueError('Verification receipt must cover exactly the three CSV tables')
    output = private_path(output)
    if output.exists():
        raise FileExistsError('EDA output must be a new directory')
    free = shutil.disk_usage(existing_ancestor(output)).free
    if free < EDA_FREE_BYTES:
        raise OSError(f'EDA needs {EDA_FREE_BYTES/1024**3:.0f} GiB free: hm_eda may spill up to 32GB beside audit.duckdb')
    for entry in receipt['files']:
        # Rehash rather than trust size and mtime.
        with (raw_dir/entry['name']).open('rb') as stream:
            size, digest = hash_stream(stream, None, math.inf, entry['name'])
        if (size, digest) != (entry['size'], entry['sha256']):
            raise ValueError(f"{entry['name']} changed after verification")
    code = code_identity()
    try:
        report = hm_eda.run(raw_dir, output)
    except Exception as exc:
        # Native CSV errors can quote source rows; like the hm_eda CLI, name the type only.
        raise RuntimeError(f'hm_eda ingestion failed ({type(exc).__name__}); inputs unchanged, '
                           'fix the cause and use a new output') from None
    rows = {table: value['matches_reference_rows'] for table, value in report['tables'].items()}
    database = output/'audit.duckdb'
    provenance = dict(format=EDA_FORMAT, valid=all(report['validation'].values()) and all(rows.values()),
                      pinned_sources=pinned, allow_unpinned=allow_unpinned,
                      database=dict(name=database.name, sha256=experiment.sha256_file(database),
                                    bytes=database.stat().st_size),
                      verify_receipt_sha256=experiment.sha256_file(receipt_path), source_status=receipt['status'],
                      files=receipt['files'], eda_validation=report['validation'], reference_rows=rows,
                      resources=dict(output_disk_free_bytes=free, min_free_bytes=EDA_FREE_BYTES), code=code)
    atomic_json(output/SOURCE_RECORD, provenance)
    return dict(provenance, database_path=database.as_posix())


def collect(database, output, anchor, users=20000, wall_seconds=3600):
    """hm_experiment.collect for C0-Q120 without its 09-09 ceiling.

    Files, ordering, labels and identities are produced by the same statements;
    the guard is instead a fully observed label week before 2020-09-23 that
    contains positives. Candidates come from the locked hm_retrieval builder.
    """
    cutoff = check_label_anchor(anchor)
    if type(users) is not int or users < 1:
        raise ValueError('Positive user count required')
    deadline = experiment.Deadline(wall_seconds)
    code = code_identity(deadline)
    source = Path(database).resolve()
    stat = source.stat()
    identity = dict(sha256=experiment.sha256_file(source, deadline), bytes=stat.st_size)
    sources = database_sources(source, identity)
    output = new_output(output)
    report = dict(format=COLLECTION_FORMAT, status='running', anchor=cutoff.isoformat(), policy=POLICY,
                  requested_users=users, cohort_seed=SEED, horizon_days=7,
                  history='[anchor-90d,anchor)', target='[anchor,anchor+7d)',
                  private_data='All parquet files contain real IDs; ignored artifacts only.')
    con = timer = None
    try:
        report['resources'] = experiment.resource_preflight(output)
        from scripts.hm_feature_engine import build_features
        from scripts.hm_retrieval import create_candidates
        report['database'] = identity
        report['sources'] = sources
        report['runtime'] = experiment.runtime_identity()
        report['code'] = code
        con = experiment.connection_for(source, output)
        timer = deadline.interrupt_sql(con)
        last = con.execute('SELECT max(t_dat) FROM transactions').fetchone()[0]
        if last is None or last < cutoff+timedelta(days=6):
            raise ValueError('Database does not cover the whole label week')
        create_candidates(con, cutoff, users, SEED)
        con.execute('''CREATE TEMP TABLE hm_candidates AS SELECT customer_id,article_id,
            source,source_rank,candidate_rank FROM hm_r_candidates WHERE policy=?''', [POLICY])
        deadline.check()
        built = build_features(con, cutoff.isoformat(), candidates_table='hm_candidates')
        report['features'] = experiment.feature_contract(built)
        con.register('_hm_feature_frame', built.frame)
        bad = con.execute('''SELECT count(*) FROM (
            (SELECT customer_id,article_id FROM hm_candidates EXCEPT SELECT customer_id,article_id FROM _hm_feature_frame)
            UNION ALL
            (SELECT customer_id,article_id FROM _hm_feature_frame EXCEPT SELECT customer_id,article_id FROM hm_candidates))''').fetchone()[0]
        duplicate = con.execute('''SELECT count(*) FROM (SELECT customer_id,article_id,count(*) n
            FROM _hm_feature_frame GROUP BY customer_id,article_id HAVING n<>1)''').fetchone()[0]
        if bad or duplicate:
            raise ValueError('Feature frame must preserve exact unique candidate keys')
        # Full future truth is first accessed after construction of cohort/candidates/features.
        con.execute('''CREATE TEMP TABLE hm_exp_targets AS SELECT DISTINCT t.customer_id,t.article_id
            FROM transactions t JOIN hm_r_users u USING(customer_id)
            WHERE t.t_dat>=?::DATE AND t.t_dat<?::DATE+INTERVAL '7 days' ''',
                    [cutoff.isoformat(), cutoff.isoformat()])
        con.execute('''CREATE TEMP TABLE hm_exp_frame AS SELECT f.*,
            (t.article_id IS NOT NULL)::BOOLEAN AS label,
            count(*) OVER(PARTITION BY f.customer_id)::INTEGER AS full_candidate_count,
            1.0/count(*) OVER(PARTITION BY f.customer_id) AS query_weight
            FROM _hm_feature_frame f LEFT JOIN hm_exp_targets t USING(customer_id,article_id)''')
        queries = con.execute('SELECT count(*) FROM hm_r_users').fetchone()[0]
        represented = con.execute('SELECT count(DISTINCT customer_id) FROM hm_exp_frame').fetchone()[0]
        if represented != queries or queries == 0:
            raise ValueError('Every history-selected query must have candidate rows')
        buyers, pairs = con.execute('SELECT count(DISTINCT customer_id),count(*) FROM hm_exp_targets').fetchone()
        hits = con.execute('SELECT count(*) FROM hm_exp_frame WHERE label').fetchone()[0]
        report['label_week'] = dict(buyers=buyers, target_pairs=pairs, positive_candidate_rows=hits)
        if not pairs or not hits:
            raise ValueError('Labelled week has no positives for the selected customers')
        for table, filename in [('hm_exp_frame', 'frame.parquet'), ('hm_exp_targets', 'targets.parquet')]:
            con.sql(f'SELECT * FROM {table} ORDER BY customer_id,article_id').write_parquet(str(output/filename))
        con.sql('''SELECT u.customer_id,sha256(u.customer_id || ':2026') AS cohort_hash,
            count(c.article_id)::INTEGER AS full_candidate_count
            FROM hm_r_users u LEFT JOIN hm_candidates c USING(customer_id)
            GROUP BY u.customer_id ORDER BY cohort_hash,u.customer_id''').write_parquet(str(output/'users.parquet'))
        names = [d[0] for d in con.execute('SELECT count(*) candidate_rows,count(*) FILTER(WHERE label) positive_rows FROM hm_exp_frame').description]
        values = con.fetchone()
        report['population'] = dict(zip(names, values), selected_queries=queries, target_pairs=pairs)
        report['files'] = {name: experiment.sha256_file(output/name, deadline) for name in
                           ('frame.parquet', 'users.parquet', 'targets.parquet')}
        report['qcy_identity'] = experiment.canonical_digest({k: report['files'][k] for k in ('users.parquet', 'targets.parquet')})
        report['candidate_identity'] = experiment.candidate_digest(con, deadline)
        # The GPU campaign pinned users.parquet of 08-12..09-09: a match confirms data
        # and code; a mismatch is reported for investigation, not refused.
        pin = {c['anchor']: c['users'] for c in read_lock()['train_collections']}.get(cutoff.isoformat())
        if pin is not None:
            produced = (report['files']['users.parquet'], (output/'users.parquet').stat().st_size)
            report['lock_users'] = dict(sha256=pin['sha256'], bytes=pin['bytes'],
                                        matches=produced == (pin['sha256'], pin['bytes']))
        else:
            report['lock_users'] = None
        after = source.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Source database changed during collection')
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        error = failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
        atomic_json(output/'manifest.json', report)
    return report


def read_collection(path, deadline):
    path = Path(path).resolve()
    manifest = read_json(path/'manifest.json')
    if manifest.get('format') != COLLECTION_FORMAT or manifest.get('status') != 'completed':
        raise ValueError('Completed hm_kaggle collection manifest required')
    check_label_anchor(manifest['anchor'])
    if (manifest.get('policy'), manifest.get('cohort_seed'), manifest.get('horizon_days')) != (POLICY, SEED, 7):
        raise ValueError('Collection policy/cohort/horizon mismatch')
    for name in ('frame.parquet', 'users.parquet', 'targets.parquet'):
        if manifest['files'].get(name) != experiment.sha256_file(path/name, deadline):
            raise ValueError('Collection byte identity changed')
    if manifest['qcy_identity'] != experiment.canonical_digest({k: manifest['files'][k] for k in ('users.parquet', 'targets.parquet')}):
        raise ValueError('Collection Q/Y identity differs')
    return manifest


def memory_connection(output, threads):
    import duckdb
    con = duckdb.connect(':memory:')
    con.execute(f'SET threads={int(threads)}')
    con.execute("SET memory_limit='2GB'")
    con.execute('SET autoinstall_known_extensions=false')
    temp = output/'duckdb-temp'
    temp.mkdir(exist_ok=True)
    con.execute('SET temp_directory=?', [str(temp)])
    con.execute("SET max_temp_directory_size='8GB'")
    return con


def fit(arm, seed, train_paths, output, validation_path=None, threads=4, wall_seconds=7200):
    """One fixed 500-tree CPU fit of locked M23/E46; validation only reports MAP@12.

    Training rows reuse hm_experiment.load_part: nested seed-2026 cohort of the
    locked size, all positives plus 20 hashed negatives with inverse weights.
    """
    recipe = locked_recipe(arm, seed, threads)
    parameters = recipe['hyperparameters']
    train_paths = [Path(p).resolve() for p in train_paths]
    if not train_paths or len(set(train_paths)) != len(train_paths):
        raise ValueError('Distinct training collection paths required')
    if validation_path is not None:
        validation_path = Path(validation_path).resolve()
        if validation_path in train_paths:
            raise ValueError('Validation collection must not be a training collection')
    deadline = experiment.Deadline(wall_seconds)
    code = code_identity(deadline)
    output = new_output(output)
    report = dict(format=FIT_FORMAT, status='running', fit_count=0, arm=arm, seed=seed,
                  selection='One fixed-tree CPU fit of the locked recipe; no eval_set, early stopping or parameter search',
                  lock=dict(path='configs/datasets/hm-auto-holdout-lock.json', sha256=LOCK_SHA256),
                  training_user_limit=recipe['train_users'], negative_sample=recipe['negative_sample'],
                  sampling_seed=recipe['sampling_seed'])
    con = timer = None
    try:
        report['resources'] = dict(experiment.resource_preflight(output), threads=threads, catboost_thread_count=threads)
        import numpy as np
        from catboost import CatBoostClassifier
        manifests = [read_collection(p, deadline) for p in train_paths]
        val_manifest = read_collection(validation_path, deadline) if validation_path is not None else None
        anchors = [date.fromisoformat(m['anchor']) for m in manifests]
        if len(set(anchors)) != len(anchors):
            raise ValueError('Training anchors must be distinct')
        if val_manifest is not None and any(a+timedelta(days=7) > date.fromisoformat(val_manifest['anchor']) for a in anchors):
            raise ValueError('Training target periods must finish before validation anchor')
        everything = manifests+([val_manifest] if val_manifest is not None else [])
        if any(m['features'] != everything[0]['features'] or m['database'] != everything[0]['database'] for m in everything):
            raise ValueError('Collections must share feature contract and database identity')
        numeric, categorical = experiment.choose_features(everything[0], feature_names=recipe['numeric']+recipe['categorical'])
        if (numeric, categorical) != (recipe['numeric'], recipe['categorical']):
            raise ValueError('Locked ordered feature vector differs from collection kinds')
        names = numeric+categorical
        report['features'] = dict(numeric=numeric, categorical=categorical, contract_digest=everything[0]['features']['digest'])
        report['database'] = everything[0]['database']
        paths = train_paths+([validation_path] if val_manifest is not None else [])
        report['inputs'] = [dict(role='train' if i < len(train_paths) else 'validation', anchor=m['anchor'],
                                 manifest_sha256=experiment.sha256_file(p/'manifest.json', deadline),
                                 qcy_identity=m['qcy_identity'], candidate_identity=m['candidate_identity'])
                            for i, (p, m) in enumerate(zip(paths, everything))]
        report['runtime'] = experiment.runtime_identity()
        report['code'] = code
        report['hyperparameters'] = parameters
        report['gpu_reference_hyperparameters'] = recipe['gpu_hyperparameters']
        report['fit_identity'] = experiment.canonical_digest(dict(
            inputs=report['inputs'], features=report['features'], hyperparameters=parameters,
            train_users=recipe['train_users'], negative_sample=recipe['negative_sample'],
            sampling_seed=recipe['sampling_seed'], code=code, runtime=report['runtime']))
        con = memory_connection(output, threads)
        timer = deadline.interrupt_sql(con)
        training = []
        report['training_populations'] = []
        for path, manifest in zip(train_paths, manifests):
            deadline.check()
            frame, _, summary = experiment.load_part(con, path, manifest, names, recipe['train_users'], recipe['negative_sample'])
            numbers, cats = experiment.model_arrays(frame, numeric, categorical)
            training.append((numbers, cats, frame['label'].to_numpy(dtype=np.int8), frame['fit_weight'].to_numpy(dtype=np.float64)))
            report['training_populations'].append(summary)
            del frame
        numbers = np.concatenate([p[0] for p in training])
        cats = np.concatenate([p[1] for p in training])
        labels = np.concatenate([p[2] for p in training])
        weights = np.concatenate([p[3] for p in training])
        del training
        if len(np.unique(labels)) != 2:
            raise ValueError('Training needs both naturally retrieved label classes')
        deadline.check()
        pool = experiment.model_pool(numbers, cats, numeric, categorical, labels, weights)

        class WallCallback:
            def after_iteration(self, info):
                report['last_training_iteration'] = int(info.iteration)
                if info.iteration % 50 == 0:
                    print(json.dumps(dict(iteration=int(info.iteration),
                                          elapsed_seconds=round(time.monotonic()-deadline.started, 3))),
                          file=sys.stderr, flush=True)
                return time.monotonic() < deadline.expires
        model = CatBoostClassifier(**parameters)
        report['fit_count'] = 1
        report['last_training_iteration'] = 0
        model.fit(pool, callbacks=[WallCallback()])
        deadline.check()
        if model.tree_count_ != parameters['iterations']:
            raise RuntimeError('Fixed-tree fit incomplete')
        report['actual_trees'] = model.tree_count_
        resolved = model.get_all_params()
        report['resolved_checks'] = {key: resolved.get(key) for key in CHECKED_PARAMETERS}
        if not all(same_value(resolved.get(key), parameters[key]) for key in CHECKED_PARAMETERS):
            raise RuntimeError('Resolved CPU parameters differ from the locked recipe')
        model.save_model(str(output/'model.cbm'))
        atomic_json(output/'params.json', resolved)
        del pool, numbers, cats, labels, weights
        files = ['model.cbm', 'params.json']
        if val_manifest is not None:
            frame, targets, summary = experiment.load_part(con, validation_path, val_manifest, names, None, None)
            numbers, cats = experiment.model_arrays(frame, numeric, categorical)
            validation = pilot.Collection(numbers, cats, frame['label'].to_numpy(), frame['query_weight'].to_numpy(),
                                          frame['customer_id'].to_numpy(), frame['article_id'].to_numpy(), targets, summary)
            deadline.check()
            scores = model.predict_proba(experiment.model_pool(numbers, cats, numeric, categorical), thread_count=threads)[:, 1]
            if not np.isfinite(scores).all():
                raise ValueError('Prediction scores must be finite')
            report['validation_population'] = summary
            report['validation_metrics'] = pilot.rank_collection(validation, scores=scores)
            experiment.write_private_predictions(con, output, validation, scores)
            files += ['query-metrics.parquet', 'predictions-top12.parquet']
        report['files'] = {name: experiment.sha256_file(output/name, deadline) for name in files}
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        error = failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
        atomic_json(output/'report.json', report)
    return report


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError('Simple relation identifier required')
    return '"'+value+'"'


def create_item_ranks(con, anchor):
    """Pre-anchor history and global item ranks, built once for every chunk.

    All customers' purchases in the 90 days count; buyers7 ties break by ID.
    """
    anchor = anchor.isoformat() if isinstance(anchor, date) else date.fromisoformat(anchor).isoformat()
    con.execute('''CREATE OR REPLACE TEMP TABLE hm_k_history AS
        SELECT t_dat,customer_id,article_id FROM transactions
        WHERE t_dat >= ?::DATE-INTERVAL '90 days' AND t_dat < ?::DATE''', [anchor, anchor])
    con.execute('''CREATE OR REPLACE TEMP TABLE hm_k_items AS
        SELECT article_id,buyers7,row_number() OVER(ORDER BY buyers7 DESC,article_id) global_rank FROM(
          SELECT article_id,count(DISTINCT customer_id) FILTER(
            WHERE t_dat >= ?::DATE-INTERVAL '7 days') buyers7
          FROM hm_k_history GROUP BY article_id)''', [anchor])
    if con.execute('SELECT count(*) FROM hm_k_items').fetchone()[0] < 120:
        raise ValueError('Observed90d catalog has fewer than120 articles')


def create_chunk_candidates(con, query_table, expected_users):
    """C0-Q120 for the customers in query_table: hm_auto_holdout SQL, any anchor.

    Recent20 by last purchase date DESC, ID; refill from global ranks <= 200 not
    already recent, to exactly 120. Requires create_item_ranks first.
    """
    table = identifier(query_table)
    con.execute(f'''CREATE OR REPLACE TEMP TABLE hm_k_recent AS
        SELECT customer_id,article_id,source_rank FROM(
          SELECT h.customer_id,h.article_id,row_number() OVER(
            PARTITION BY h.customer_id ORDER BY max(h.t_dat) DESC,h.article_id) source_rank
          FROM hm_k_history h JOIN {table} q USING(customer_id)
          GROUP BY h.customer_id,h.article_id) WHERE source_rank<=20''')
    con.execute(f'''CREATE OR REPLACE TEMP TABLE hm_candidates AS
        WITH initial AS(
          SELECT customer_id,article_id,'recent' AS source,source_rank,1 priority FROM hm_k_recent
        ), global_unseen AS(
          SELECT q.customer_id,g.article_id,'global' AS source,g.global_rank source_rank,4 priority,
            row_number() OVER(PARTITION BY q.customer_id ORDER BY g.global_rank) refill_rank
          FROM {table} q CROSS JOIN hm_k_items g
          WHERE g.global_rank<=200 AND NOT EXISTS(
            SELECT 1 FROM hm_k_recent r WHERE r.customer_id=q.customer_id AND r.article_id=g.article_id)
        ), selected AS(
          SELECT * FROM initial UNION ALL
          SELECT customer_id,article_id,source,source_rank,priority FROM global_unseen g
          WHERE g.refill_rank<=120-(SELECT count(*) FROM initial r WHERE r.customer_id=g.customer_id)
        ) SELECT customer_id,article_id,source,source_rank,
          row_number() OVER(PARTITION BY customer_id ORDER BY priority,source_rank,article_id) candidate_rank
          FROM selected''')
    invalid = con.execute('''SELECT count(*) FROM(
        SELECT customer_id,count(*) n,count(DISTINCT article_id) unique_n FROM hm_candidates GROUP BY customer_id)
        WHERE n<>120 OR unique_n<>120''').fetchone()[0]
    represented = con.execute('SELECT count(DISTINCT customer_id) FROM hm_candidates').fetchone()[0]
    if invalid or represented != expected_users:
        raise ValueError('C0-Q120 candidate-size/key invariant failed')


def ordered_digest(con, sql, params=None):
    """Length-prefixed hash of an ordered result, read in bounded batches."""
    digest = hashlib.sha256()
    cursor = con.execute(sql, params or [])
    while block := cursor.fetchmany(8192):
        for row in block:
            for value in row:
                encoded = str(value).encode('utf-8')
                digest.update(len(encoded).to_bytes(4, 'big'))
                digest.update(encoded)
    return digest.hexdigest()


def database_connection(database, temp, threads):
    import duckdb
    con = duckdb.connect(str(Path(database).resolve()), read_only=True)
    con.execute(f'SET threads={int(threads)}')
    con.execute("SET memory_limit='2GB'")
    con.execute('SET preserve_insertion_order=false')
    con.execute('SET autoinstall_known_extensions=false')
    temp.mkdir(exist_ok=True)
    con.execute('SET temp_directory=?', [str(temp)])
    con.execute("SET max_temp_directory_size='8GB'")
    return con


def load_fit(path, deadline):
    """A completed fit with its byte-pinned model and the same feature vector."""
    from catboost import CatBoostClassifier
    path = Path(path).resolve()
    report = read_json(path/'report.json')
    if report.get('format') != FIT_FORMAT or report.get('status') != 'completed':
        raise ValueError('Completed hm_kaggle fit report required')
    model_sha = experiment.sha256_file(path/'model.cbm', deadline)
    if model_sha != report['files']['model.cbm']:
        raise ValueError('Model bytes differ from the fit report')
    model = CatBoostClassifier()
    model.load_model(str(path/'model.cbm'))
    numeric, categorical = report['features']['numeric'], report['features']['categorical']
    if list(model.feature_names_) != numeric+categorical or model.tree_count_ != report['hyperparameters']['iterations']:
        raise ValueError('Saved model differs from its reported feature vector or tree count')
    name = f"{report['arm']}{report['seed']}"
    identity = dict(name=name, arm=report['arm'], seed=report['seed'],
                    report_sha256=experiment.sha256_file(path/'report.json', deadline), model_sha256=model_sha,
                    numeric=numeric, categorical=categorical, contract_digest=report['features']['contract_digest'],
                    database=report['database'])
    return dict(name=name, model=model, numeric=numeric, categorical=categorical, identity=identity)


def write_top12(con, frame, scores, path):
    """Top 12 by score DESC, then article ID, as hm_baseline.rank_collection."""
    partial = path.with_name(f'{path.name}.{os.getpid()}.part')
    con.register('_hm_k_scores', frame[['customer_id', 'article_id']].assign(score=scores))
    try:
        con.sql('''SELECT customer_id,article_id,"rank",score FROM (SELECT customer_id,article_id,score,
            row_number() OVER(PARTITION BY customer_id ORDER BY score DESC,article_id) AS "rank"
            FROM _hm_k_scores) WHERE "rank"<=12 ORDER BY customer_id,"rank"''').write_parquet(str(partial))
    finally:
        con.unregister('_hm_k_scores')
    rows = con.execute('SELECT count(*) FROM read_parquet(?)', [str(partial)]).fetchone()[0]
    os.replace(partial, path)
    return dict(sha256=experiment.sha256_file(path), rows=rows)


def check_chunk(output, receipt, plan_sha256, chunk, names):
    expected = {f'top12-{name}-{chunk:04d}.parquet' for name in names}
    if (receipt.get('format') != CHUNK_FORMAT or receipt.get('plan_sha256') != plan_sha256 or
            receipt.get('chunk') != chunk or set(receipt['files']) != expected):
        raise ValueError(f'Chunk {chunk} receipt belongs to another plan')
    for filename, value in receipt['files'].items():
        if experiment.sha256_file(output/filename) != value['sha256']:
            raise ValueError(f'Chunk {chunk} file bytes changed after its receipt')


def score(database, fits, output, chunk_users=15000, threads=4, wall_seconds=21600, anchor=SCORE_ANCHOR):
    """Score every customer with 90-day history at the Kaggle anchor, resumably.

    Customers are ordered by sha256(id||':2026'), id and cut into chunks. Each
    chunk builds C0-Q120 and the locked features once and scores all models on
    that frame. A chunk is finished when its receipt exists; reruns skip it.
    One process at a time: score.lock is held from the output checks to the end.
    """
    cutoff = date.fromisoformat(anchor) if isinstance(anchor, str) else anchor
    if (type(chunk_users) is not int or not 1 <= chunk_users <= MAX_CHUNK_USERS or
            type(threads) is not int or threads < 1):
        raise ValueError(f'Chunk size must be an integer in 1..{MAX_CHUNK_USERS}; threads a positive integer')
    deadline = experiment.Deadline(wall_seconds)
    code = code_identity(deadline)
    import numpy as np
    from scripts.hm_feature_engine import build_features, feature_manifest
    models = [load_fit(path, deadline) for path in fits]
    names = [m['name'] for m in models]
    if not models or len(set(names)) != len(names):
        raise ValueError('Distinct arm/seed fits required')
    feature_digest = feature_manifest()['digest']
    source = Path(database).resolve()
    stat = source.stat()
    db_identity = dict(sha256=experiment.sha256_file(source, deadline), bytes=stat.st_size)
    sources = database_sources(source, db_identity)
    for m in models:
        if m['identity']['database'] != db_identity or m['identity']['contract_digest'] != feature_digest:
            raise ValueError('Fits must come from collections of this database and feature engine')
    output = private_path(output)
    resume = output.exists()
    if resume and not (output/'plan.json').is_file():
        raise ValueError('Existing output is not a resumable score run')
    if not resume:
        output.mkdir(parents=True, exist_ok=False)
    lock = hold_lock(output/'score.lock')
    started_at = utc_now()
    report = dict(format=SCORE_FORMAT, status='running', anchor=cutoff.isoformat(), policy=POLICY,
                  chunk_users=chunk_users, threads=threads, resumed=resume, started_at_utc=started_at)
    con = timer = None
    accepted = not resume
    spill = output/f'duckdb-temp-{os.getpid()}'
    try:
        report['resources'] = experiment.resource_preflight(output)
        con = database_connection(source, spill, threads)
        timer = deadline.interrupt_sql(con)
        if con.execute('SELECT max(t_dat) FROM transactions').fetchone()[0] != cutoff-timedelta(days=1):
            raise ValueError('Scoring needs transactions ending exactly the day before the anchor')
        create_item_ranks(con, cutoff)
        con.execute('''CREATE TEMP TABLE hm_k_users AS SELECT customer_id,user_rank,(user_rank-1)//? AS chunk FROM(
            SELECT customer_id,row_number() OVER(ORDER BY sha256(customer_id || ':' || ?),customer_id) user_rank
            FROM (SELECT DISTINCT customer_id FROM hm_k_history))''', [chunk_users, str(SEED)])
        users = con.execute('SELECT count(*) FROM hm_k_users').fetchone()[0]
        if not users:
            raise ValueError('No customer has history before the anchor')
        chunks = math.ceil(users/chunk_users)
        plan = dict(format=PLAN_FORMAT, anchor=cutoff.isoformat(), policy=POLICY, history='[anchor-90d,anchor)',
                    order='sha256(customer_id || ":2026"), customer_id', chunk_users=chunk_users, threads=threads,
                    users=users, chunks=chunks,
                    users_digest=ordered_digest(con, 'SELECT customer_id FROM hm_k_users ORDER BY user_rank'),
                    items_digest=ordered_digest(con, 'SELECT article_id,buyers7,global_rank FROM hm_k_items ORDER BY global_rank'),
                    database=db_identity, sources=sources, feature_digest=feature_digest,
                    models=[m['identity'] for m in models],
                    code=code, runtime={k: v for k, v in experiment.runtime_identity().items() if k in ('python', 'packages')})
        plan_path = output/'plan.json'
        if resume and read_json(plan_path) != plan:
            raise ValueError('Existing score plan differs; resume needs identical inputs, chunking and threads')
        accepted = True
        if not resume:
            atomic_json(plan_path, plan)
        plan_sha256 = experiment.sha256_file(plan_path)
        report.update(plan_sha256=plan_sha256, users=users, chunks=chunks, computed=0, skipped=0)
        for chunk in range(chunks):
            deadline.check()
            receipt_path = output/f'chunk-{chunk:04d}.json'
            if receipt_path.exists():
                check_chunk(output, read_json(receipt_path), plan_sha256, chunk, names)
                report['skipped'] += 1
                print(json.dumps(dict(event='skip', chunk=chunk, chunks=chunks)), file=sys.stderr, flush=True)
                continue
            began = time.monotonic()
            con.execute('CREATE OR REPLACE TEMP TABLE hm_k_query AS SELECT customer_id FROM hm_k_users WHERE chunk=?', [chunk])
            size = con.execute('SELECT count(*) FROM hm_k_query').fetchone()[0]
            create_chunk_candidates(con, 'hm_k_query', size)
            built = build_features(con, cutoff.isoformat(), candidates_table='hm_candidates')
            if experiment.feature_contract(built)['digest'] != feature_digest:
                raise ValueError('Feature engine output differs from the plan')
            frame = built.frame
            con.register('_hm_k_frame', frame)
            try:
                bad = con.execute('''SELECT count(*) FROM (
                    (SELECT customer_id,article_id FROM hm_candidates EXCEPT SELECT customer_id,article_id FROM _hm_k_frame)
                    UNION ALL
                    (SELECT customer_id,article_id FROM _hm_k_frame EXCEPT SELECT customer_id,article_id FROM hm_candidates))''').fetchone()[0]
            finally:
                con.unregister('_hm_k_frame')
            if bad or len(frame) != 120*size:
                raise ValueError('Feature frame must preserve exact unique candidate keys')
            files = {}
            for m in models:
                deadline.check()
                numbers, cats = experiment.model_arrays(frame, m['numeric'], m['categorical'])
                scores = m['model'].predict_proba(experiment.model_pool(numbers, cats, m['numeric'], m['categorical']),
                                                  thread_count=threads)[:, 1]
                del numbers, cats
                if not np.isfinite(scores).all():
                    raise ValueError('Prediction scores must be finite')
                filename = f"top12-{m['name']}-{chunk:04d}.parquet"
                files[filename] = write_top12(con, frame, scores, output/filename)
                if files[filename]['rows'] != 12*size:
                    raise ValueError('Every scored customer needs exactly 12 rows')
            receipt = dict(format=CHUNK_FORMAT, plan_sha256=plan_sha256, chunk=chunk, users=size,
                           users_digest=ordered_digest(con, 'SELECT customer_id FROM hm_k_query ORDER BY customer_id'),
                           candidate_rows=len(frame), files=files, threads=threads,
                           seconds=round(time.monotonic()-began, 3), rss_bytes=current_rss_bytes(),
                           peak_rss_bytes=peak_rss_bytes(), finished_at_utc=utc_now())
            del frame, built
            atomic_json(receipt_path, receipt)
            report['computed'] += 1
            print(json.dumps(dict(event='chunk', chunk=chunk, chunks=chunks, users=size, seconds=receipt['seconds'],
                                  rss_bytes=receipt['rss_bytes'], peak_rss_bytes=receipt['peak_rss_bytes'])),
                  file=sys.stderr, flush=True)
        receipts = [read_json(output/f'chunk-{chunk:04d}.json') for chunk in range(chunks)]
        if sum(r['users'] for r in receipts) != users:
            raise ValueError('Chunk receipts do not cover every scored customer')
        report['receipts'] = {f'chunk-{c:04d}.json': experiment.sha256_file(output/f'chunk-{c:04d}.json') for c in range(chunks)}
        report['models'] = {name: dict(rows=sum(r['files'][f'top12-{name}-{c:04d}.parquet']['rows']
                                                for c, r in enumerate(receipts))) for name in names}
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        error = failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        try:
            if timer:
                timer.cancel()
            if con:
                con.close()
            if spill.is_dir() and not any(spill.iterdir()):
                spill.rmdir()  # DuckDB removes its files on close; only the empty directory is left
            report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
            report['peak_rss_bytes'] = peak_rss_bytes()
            if accepted:
                # Latest invocation only; chunk receipts are the durable record.
                atomic_json(output/'report.json', report)
        finally:
            release_lock(lock)
    return report


def check_submission(path, customers, articles):
    """Reject anything but one line of 12 distinct known 10-digit IDs per customer.

    Errors name line numbers only, never customer IDs.
    """
    path = Path(path)
    with path.open('rb') as probe:
        compressed = probe.read(2) == b'\x1f\x8b'
    opener = gzip.open if compressed else open
    seen = set()
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        if stream.readline() != HEADER:
            raise ValueError('Header must be exactly customer_id,prediction')
        for number, line in enumerate(stream, 2):
            if not line.endswith('\n'):
                raise ValueError(f'Line {number} lacks a final LF')
            fields = line[:-1].split(',')
            if len(fields) != 2:
                raise ValueError(f'Line {number} needs exactly two fields')
            customer, prediction = fields
            if customer not in customers:
                raise ValueError(f'Line {number}: customer is not in the customer list')
            if customer in seen:
                raise ValueError(f'Line {number}: duplicate customer')
            seen.add(customer)
            items = prediction.split(' ')
            if len(items) != 12 or len(set(items)) != 12:
                raise ValueError(f'Line {number}: 12 distinct article IDs required')
            if not all(ITEM.fullmatch(item) and item in articles for item in items):
                raise ValueError(f'Line {number}: article IDs must be known 10-digit IDs')
    if len(seen) != len(customers):
        raise ValueError('Submission rows differ from the full customer list')
    return dict(rows=len(seen))


def assemble(database, scores, model, output, expected_customers=None, wall_seconds=3600):
    """Kaggle CSV for one model: scored top 12, popular fallback, strict checks.

    Customers without 90-day history receive the 12 articles with most distinct
    buyers in the last 7 days, ties by ID. A scored customer without exactly 12
    articles is an error, not a fill. The file is checked as a .part and
    renamed only after every check passes.
    """
    from scripts.hm_eda import EXPECTED_ROWS
    expected_customers = EXPECTED_ROWS['customers'] if expected_customers is None else expected_customers
    deadline = experiment.Deadline(wall_seconds)
    code = code_identity(deadline)
    output = private_path(output)
    if not output.name.endswith('.csv.gz'):
        raise ValueError('Submission output must end with .csv.gz')
    partial = output.with_name(output.name+'.part')
    receipt_path = output.with_name(output.name[:-len('.csv.gz')]+'.json')
    if output.exists() or partial.exists() or receipt_path.exists():
        raise FileExistsError('Submission output, partial and receipt must be new')
    scores = Path(scores).resolve()
    plan_path = scores/'plan.json'
    plan = read_json(plan_path)
    plan_sha256 = experiment.sha256_file(plan_path, deadline)
    names = [m['name'] for m in plan['models']]
    if plan.get('format') != PLAN_FORMAT or model not in names:
        raise ValueError('Score plan does not contain this model')
    files, receipts = [], {}
    for chunk in range(plan['chunks']):
        name = f'chunk-{chunk:04d}.json'
        if not (scores/name).exists():
            raise ValueError('Scoring is unfinished; rerun score with the same arguments')
        check_chunk(scores, read_json(scores/name), plan_sha256, chunk, names)
        receipts[name] = experiment.sha256_file(scores/name, deadline)
        files.append(str(scores/f'top12-{model}-{chunk:04d}.parquet'))
    source = Path(database).resolve()
    db_identity = dict(sha256=experiment.sha256_file(source, deadline), bytes=source.stat().st_size)
    if db_identity != plan['database']:
        raise ValueError('Database differs from the scored database')
    sources = database_sources(source, db_identity)
    if sources != plan.get('sources'):
        raise ValueError('Database provenance differs from the score plan')
    # Spill up to 8GB plus the file: the same 10 GiB floor as collect and score.
    resources = experiment.resource_preflight(existing_ancestor(output.parent))
    anchor = plan['anchor']
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hm-kaggle-assemble-', dir=output.parent) as spill:
        # The connection closes before its spill directory is removed.
        con = database_connection(source, Path(spill)/'duckdb-temp', 2)
        timer = deadline.interrupt_sql(con)
        try:
            count, unique, missing = con.execute('''SELECT count(*),count(DISTINCT customer_id),
                count(*) FILTER(WHERE customer_id IS NULL) FROM customers''').fetchone()
            if count != expected_customers or unique != count or missing:
                raise ValueError('Customer list must be the complete unique Kaggle list')
            invalid, padded, total = con.execute('''SELECT count(*) FILTER(WHERE article_id IS NULL OR NOT regexp_full_match(article_id,'[0-9]{1,10}')),
                count(DISTINCT lpad(article_id,10,'0')),count(*) FROM articles''').fetchone()
            if invalid or padded != total:
                raise ValueError('Article IDs must be unique digit strings of at most 10 digits')
            # Recompute the scored population from the database, not from receipts.
            con.execute('''CREATE TEMP TABLE hm_k_users AS SELECT DISTINCT customer_id FROM transactions
                WHERE t_dat >= ?::DATE-INTERVAL '90 days' AND t_dat < ?::DATE''', [anchor, anchor])
            digest = ordered_digest(con, '''SELECT customer_id FROM hm_k_users
                ORDER BY sha256(customer_id || ':' || ?),customer_id''', [str(SEED)])
            if digest != plan['users_digest']:
                raise ValueError('Scored customers differ from the database history population')
            con.execute('CREATE TEMP TABLE hm_k_top AS SELECT customer_id,article_id,"rank" FROM read_parquet(?)', [files])
            # Ranks exactly 1..12: twelve rows, twelve distinct ranks between 1 and 12.
            bad = con.execute('''SELECT count(*) FROM (SELECT customer_id,count(*) n,count(DISTINCT article_id) a,
                count(DISTINCT "rank") r,min("rank") lo,max("rank") hi FROM hm_k_top GROUP BY customer_id)
                WHERE n<>12 OR a<>12 OR r<>12 OR lo<>1 OR hi<>12''').fetchone()[0]
            outside = con.execute('''SELECT count(*) FROM (
                (SELECT customer_id FROM hm_k_users EXCEPT SELECT customer_id FROM hm_k_top) UNION ALL
                (SELECT customer_id FROM hm_k_top EXCEPT SELECT customer_id FROM customers) UNION ALL
                (SELECT customer_id FROM hm_k_top EXCEPT SELECT customer_id FROM hm_k_users))''').fetchone()[0]
            unknown = con.execute('SELECT count(*) FROM hm_k_top t ANTI JOIN articles a USING(article_id)').fetchone()[0]
            if bad or outside or unknown:
                raise ValueError('Scored top 12 must cover exactly the history customers with known articles')
            popular = [row[0] for row in con.execute('''SELECT lpad(article_id,10,'0') padded FROM transactions
                WHERE t_dat >= ?::DATE-INTERVAL '7 days' AND t_dat < ?::DATE GROUP BY article_id
                ORDER BY count(DISTINCT customer_id) DESC,padded LIMIT 12''', [anchor, anchor]).fetchall()]
            if len(popular) != 12:
                raise ValueError('Fewer than 12 articles were bought in the last 7 days')
            fallback = 0
            with partial.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as stream:
                stream.write(HEADER.encode('utf-8'))
                cursor = con.execute('''SELECT c.customer_id,t.items FROM customers c LEFT JOIN (
                    SELECT customer_id,list(lpad(article_id,10,'0') ORDER BY "rank") items FROM hm_k_top GROUP BY customer_id) t
                    USING(customer_id) ORDER BY c.customer_id''')
                while block := cursor.fetchmany(65536):
                    deadline.check()
                    lines = []
                    for customer, items in block:
                        if items is None:
                            fallback += 1
                            items = popular
                        lines.append(customer+','+' '.join(items)+'\n')
                    stream.write(''.join(lines).encode('utf-8'))
            customers = {row[0] for row in con.execute('SELECT customer_id FROM customers').fetchall()}
            articles = {row[0] for row in con.execute("SELECT lpad(article_id,10,'0') FROM articles").fetchall()}
            checked = check_submission(partial, customers, articles)
            scored = con.execute('SELECT count(*) FROM hm_k_users').fetchone()[0]
        except Exception as exc:
            error = wall_limit(exc, deadline)
            if error is not exc:
                raise error from exc
            raise
        finally:
            timer.cancel()
            con.close()
    if checked['rows'] != expected_customers or fallback != expected_customers-scored:
        raise ValueError('Submission population accounting differs')
    partial.rename(output)
    receipt = dict(format=SUBMISSION_FORMAT, model=model, anchor=anchor, scores=dict(plan_sha256=plan_sha256, receipts=receipts),
                   database=db_identity, sources=sources, rows=checked['rows'], model_customers=scored,
                   popular_fallback_customers=fallback, popular_last7=popular, header=HEADER.strip(),
                   file=dict(name=output.name, bytes=output.stat().st_size, sha256=experiment.sha256_file(output)),
                   resources=resources, code=code, created_at_utc=utc_now())
    atomic_json(receipt_path, receipt)
    return receipt


def main(argv=None):
    parser = Parser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('verify', help='hash the three CSVs (or their per-file zips) against hm-source.json')
    command.add_argument('--raw-dir', type=Path, required=True)
    command.add_argument('--config', type=Path, default=SOURCE_CONFIG)
    command = sub.add_parser('eda', help='locked hm_eda ingestion of verified CSVs into a new audit.duckdb')
    command.add_argument('--raw-dir', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--allow-unpinned', action='store_true')
    command = sub.add_parser('collect', help='one labelled C0-Q120 weekly collection, anchor <= 2020-09-16')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--anchor', required=True)
    command.add_argument('--users', type=int, default=20000)
    command.add_argument('--wall-seconds', type=float, default=3600)
    command = sub.add_parser('fit', help='one locked CPU fit of M23 or E46')
    command.add_argument('--arm', choices=('M', 'E'), required=True)
    command.add_argument('--seed', type=int, choices=(2026, 2027), required=True)
    command.add_argument('--train', type=Path, nargs='+', required=True)
    command.add_argument('--validation', type=Path)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--threads', type=int, default=4)
    command.add_argument('--wall-seconds', type=float, default=7200)
    command = sub.add_parser('score', help='resumable chunked top 12 at 2020-09-23 for every given fit')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--fits', type=Path, nargs='+', required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--chunk-users', type=int, default=15000)
    command.add_argument('--threads', type=int, default=4)
    command.add_argument('--wall-seconds', type=float, default=21600)
    command = sub.add_parser('assemble', help='checked Kaggle submission .csv.gz for one scored model')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--scores', type=Path, required=True)
    command.add_argument('--model', required=True)
    command.add_argument('--output', type=Path, required=True)
    try:
        args = parser.parse_args(argv)
    except UsageError as exc:
        tokens = sys.argv[1:] if argv is None else list(argv)
        print(json.dumps(dict(status='failed', command=next((t for t in tokens if t in sub.choices), None),
                              error_type='UsageError', message=str(exc)[:500])))
        return 1
    try:
        if args.command in ISOLATED_COMMANDS and not isolated():
            raise RuntimeError(f'{args.command} reads downloaded data; run it as python -I scripts/hm_kaggle.py')
        if args.command == 'verify':
            result = verify(args.raw_dir, args.config)
            print(json.dumps(dict(status=result['status'], files={f['name']: f['matches'] for f in result['files']})))
            return 0 if result['status'] == 'complete' else 2
        if args.command == 'eda':
            result = eda(args.raw_dir, args.output, args.allow_unpinned)
            print(json.dumps(dict(status='completed', valid=result['valid'], pinned_sources=result['pinned_sources'],
                                  allow_unpinned=result['allow_unpinned'], reference_rows=result['reference_rows'],
                                  database=result['database_path'])))
            return 0 if result['valid'] else 2
        if args.command == 'collect':
            result = collect(args.database, args.output, args.anchor, args.users, args.wall_seconds)
            pin = result['lock_users']
            print(json.dumps(dict(status=result['status'], anchor=result['anchor'], **result['label_week'],
                                  selected_queries=result['population']['selected_queries'],
                                  lock_users_match=None if pin is None else pin['matches'])))
        elif args.command == 'fit':
            result = fit(args.arm, args.seed, args.train, args.output, args.validation, args.threads, args.wall_seconds)
            populations = result['training_populations']
            summary = dict(status=result['status'], model=f'{args.arm}{args.seed}', trees=result['actual_trees'],
                           train_queries=sum(p['selected_queries'] for p in populations),
                           train_positive_rows=sum(p['positive_rows'] for p in populations))
            if 'validation_metrics' in result:
                metrics = result['validation_metrics']
                summary.update({key: metrics[key] for key in ('map_at_12_conditional', 'positive_queries',
                                                              'distinct_query_target_pairs', 'queries',
                                                              'oracle_map_at_12_conditional')})
            print(json.dumps(summary))
        elif args.command == 'score':
            result = score(args.database, args.fits, args.output, args.chunk_users, args.threads, args.wall_seconds)
            print(json.dumps(dict(status=result['status'], users=result['users'], chunks=result['chunks'],
                                  computed=result['computed'], skipped=result['skipped'])))
        else:
            result = assemble(args.database, args.scores, args.model, args.output)
            print(json.dumps(dict(status='completed', rows=result['rows'], model_customers=result['model_customers'],
                                  popular_fallback_customers=result['popular_fallback_customers'],
                                  sha256=result['file']['sha256'])))
    except Exception as exc:
        message = str(exc)[:500]
        if type(exc).__module__.split('.')[0].lstrip('_') in NATIVE_ERRORS:
            # Native errors can quote data rows; manifests/reports in artifacts/ keep the detail.
            message = 'Native library error; see the output manifest or report if one was written'
        print(json.dumps(dict(status='failed', command=args.command, error_type=type(exc).__name__, message=message)))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
