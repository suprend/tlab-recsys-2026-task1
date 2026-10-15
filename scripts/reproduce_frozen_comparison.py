"""Public raw -> fresh features/full targets -> two frozen development fits.

An ordinary user owns this command and its exclusive output. It consumes no
historical approvals/models. Limits here are cooperative, including native fit
callbacks; a separately supervised agent execution needs its own total budget.
Imports at module load are standard library only. Final/heldout dates are not
part of this development reproduction.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time
from types import ModuleType

RECIPE_SHA256 = '3a26fed3bee450cb7ce4b658816386c14cbd2c4133a18bdaa39ae058e5b560ec'
ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
CORE_ORDER = ('source_import', 'temporal_contract', 'protocol_manifest', 'anchor_pilot',
              'candidate_pilot', 'manual_features', 'feature_programs', 'development_collection',
              'ranking_metrics', 'train_baselines', 'inference_data', 'heldout_contract', 'heldout_predictions')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(body):
    return json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False)


def parse_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def write_new(path, body):
    with Path(path).open('x', encoding='utf8') as stream:
        stream.write(json.dumps(body, sort_keys=True, indent=2, allow_nan=False) + '\n')


def file_ref(path, check):
    check()
    digest = hashlib.sha256()
    count = 0
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            count += len(block)
            check()
    return dict(sha256=digest.hexdigest(), bytes=count)



def snapshot_file(path, check, *, maximum=256 * 1024):
    """One bounded byte read: its digest, parser and compiler share the snapshot."""
    check()
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum + 1)
    need(len(raw) <= maximum, 'Bounded metadata/source snapshot exceeded')
    check()
    return raw, dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def write_snapshot(path, raw, expected, check):
    with Path(path).open('xb') as stream:
        stream.write(raw)
    need(file_ref(path, check) == expected, 'Owned snapshot differs from authenticated bytes')


def secondary_note(primary, stage, secondary):
    try:
        primary.add_note(stage + ': ' + type(secondary).__name__)
    except BaseException:
        pass


def fail_preserving(primary, output, budget):
    """No telemetry/format/persistence failure can replace RuntimeError/KI/exit."""
    secondary = []
    try:
        message = str(primary)
    except BaseException as error:
        secondary_note(primary, 'Failure formatting', error)
        secondary.append(dict(stage='format', error_type=type(error).__name__))
        message = '<primary error message unavailable>'
    try:
        telemetry = budget.telemetry()
    except BaseException as error:
        secondary_note(primary, 'Failure telemetry', error)
        secondary.append(dict(stage='telemetry', error_type=type(error).__name__))
        telemetry = dict(unknown=True)
    try:
        write_new(output / 'failed.json', dict(status='failed_consumed', error_type=type(primary).__name__,
                  error=message, retry=False, telemetry=telemetry, secondary_errors=secondary,
                  independent_acceptance_issued=False))
    except BaseException as error:
        secondary_note(primary, 'Failure persistence', error)


def close_preserving(con, primary):
    try:
        con.close()
    except BaseException as error:
        if primary is None:
            raise
        secondary_note(primary, 'Connection close', error)


class SourceBinding:
    """Fixed public source closure; compile verified snapshots, never cached pyc.

    This is the closed entry's source loader, not a plugin/authority mechanism.
    It requires a fresh command process and keeps all initially bound witnesses.
    """
    def __init__(self, recipe, check):
        self.check_budget = check
        self.command_path = Path(__file__)
        self.command_raw, self.command = snapshot_file(self.command_path, check)
        self.raw, self.witnesses, self.loaded = {}, {}, {}
        total = 0
        for name, expected in recipe['dependencies'].items():
            raw, witness = snapshot_file(ROOT / name, check, maximum=512 * 1024)
            need(witness['sha256'] == expected, 'Frozen dependency differs: ' + name)
            total += len(raw)
            need(total <= 2 * 2**20, 'Bounded public source closure exceeded')
            self.raw[name], self.witnesses[name] = raw, witness

    def check(self):
        check = self.check_budget
        need(file_ref(self.command_path, check) == self.command, 'Initial command source changed')
        for name, expected in self.witnesses.items():
            need(file_ref(ROOT / name, check) == expected, 'Initially bound source changed: ' + name)
        for name, module in self.loaded.items():
            need(sys.modules.get('scripts.' + name) is module, 'Verified source module was replaced')

    def load_cores(self):
        self.check()
        need(all('scripts.' + name not in sys.modules for name in CORE_ORDER),
             'Public command requires fresh core modules; cached execution is unsupported')
        # Actual dependencies are already ordered before their importers. Imports
        # inside compiled cores therefore resolve these exact source snapshots.
        for name in CORE_ORDER:
            key = 'scripts/' + name + '.py'
            need(key in self.raw, 'Fixed core is absent from authenticated closure')
            fullname = 'scripts.' + name
            module = ModuleType(fullname)
            module.__file__, module.__package__ = str(ROOT / key), 'scripts'
            sys.modules[fullname] = module
            setattr(sys.modules['scripts'], name, module)
            self.loaded[name] = module
            exec(compile(self.raw[key], module.__file__, 'exec', dont_inherit=True), module.__dict__)
        self.check()


def verify_exports(files, check):
    """Carry original producer witnesses; later files cannot redefine the pins."""
    for row in files:
        manifest = row['_manifest']
        raw, actual = snapshot_file(manifest['path'], check, maximum=128 * 1024)
        need(actual == manifest['witness'], 'Original export manifest changed')
        body = parse_json(raw)
        need(body['files'] == row['_refs'], 'Manifest/original export witnesses differ')
        for kind, expected in row['_refs'].items():
            need(Path(row[kind]).name == expected['path'], 'Manifest export path differs')
            need(file_ref(row[kind], check) == {k: expected[k] for k in ('sha256', 'bytes')},
                 'Original consumed export changed: ' + kind)



def export_inventory(phases, output):
    """Serialize original witnesses, with paths relative to the owned output."""
    return {phase: [dict(manifest=dict(path=Path(row['_manifest']['path']).relative_to(output).as_posix(),
                                     **row['_manifest']['witness']),
                        exports={kind: dict(path=Path(row[kind]).relative_to(output).as_posix(),
                                            **{key: expected[key] for key in ('sha256', 'bytes')})
                                 for kind, expected in row['_refs'].items()}) for row in files]
            for phase, files in phases.items()}

def repin_exports_preserving(files, check, primary):
    try:
        verify_exports(files, check)
    except BaseException as error:
        if primary is None:
            raise
        secondary_note(primary, 'Export repin', error)

def stamp(text):
    return datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)


def iso(value):
    return value.strftime('%Y-%m-%dT%H:%M:%SZ')


class Budget:
    """Since Budget construction; startup/full process exit need external accounting."""
    def __init__(self, cpu, wall, rss, spill):
        for value in (cpu, wall, rss, spill):
            need(type(value) is int and value > 0, 'Positive integer resource limits required')
        need(wall <= 43200, 'Public reproduction wall ceiling is twelve hours')
        need(spill >= 8 * 2**30, 'Existing import kernel requires an 8 GiB spill allowance')
        try:
            import resource
        except ImportError as error:
            raise RuntimeError('RSS accounting requires Linux/macOS; use WSL on Windows') from error
        self.spill_paths = []
        self.cpu_limit, self.wall_limit, self.rss_limit, self.spill_limit = cpu, wall, rss, spill
        self.cpu_start, self.wall_start = time.process_time(), time.monotonic()
        self.fit_attempts = 0

    def telemetry(self):
        # resource is unavailable on Windows: fail explicitly instead of omitting RSS.
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return dict(cpu_seconds=time.process_time() - self.cpu_start,
                    wall_seconds=time.monotonic() - self.wall_start,
                    peak_rss_bytes=int(peak if sys.platform == 'darwin' else peak * 1024),
                    fit_attempts=self.fit_attempts, accounting='current_process_all_threads',
                    cooperative=True, external_process_tail_accepted=False,
                    timer_scope='Budget construction through sample; excludes interpreter/CLI startup and full exit')

    def check(self):
        state = self.telemetry()
        if (state['cpu_seconds'] >= self.cpu_limit or state['wall_seconds'] >= self.wall_limit
                or state['peak_rss_bytes'] > self.rss_limit):
            raise RuntimeError('Original total cooperative resource limit exceeded')
        spill_bytes = sum(path.stat().st_size for directory in self.spill_paths if directory.exists()
                          for path in directory.rglob('*') if path.is_file())
        if spill_bytes > self.spill_limit:
            raise RuntimeError('Original aggregate cooperative spill limit exceeded')

    def reserve_fit(self):
        self.check()
        need(self.fit_attempts < 2, 'Frozen two-fit cap exhausted')
        self.fit_attempts += 1


def validate_recipe(path, check):
    raw, witness = snapshot_file(path, check, maximum=128 * 1024)
    need(witness['sha256'] == RECIPE_SHA256, 'Only the exact frozen public recipe is supported')
    recipe = parse_json(raw)
    from importlib.metadata import version
    need(list(sys.version_info[:2]) == recipe['environment']['python_major_minor'], 'Frozen Python 3.12 environment required')
    need({name: version(name) for name in recipe['environment']['packages']} == recipe['environment']['packages'],
         'Installed native/data packages differ from the locked recipe')
    return recipe, raw, witness


def selected_registry(recipe):
    from scripts.feature_programs import generate_pool, allocate_slots, registry_for_slot
    pool = generate_pool(recipe['program_contract'], recipe['manual_registry'])
    allocation = allocate_slots(pool)
    slot = next(row for row in allocation['identity']['slots'] if row['slot'] == recipe['program_slot'])
    need(slot['bundle_id'] == recipe['program_bundle'], 'Frozen program allocation changed')
    return registry_for_slot(pool, allocation, recipe['program_slot'])


def day_protocol(recipe, day):
    from scripts.protocol_manifest import validate_protocol
    config = deepcopy(recipe['protocol'])
    config['pilot'] = dict(start=iso(day), end=iso(day + timedelta(days=1)))
    config['budget'] = dict(max_anchors=config['query']['max_users_per_day'],
                            max_candidate_pairs=config['query']['max_users_per_day'] * 220)
    return validate_protocol(config)


def calendar_maturity(con, config):
    """Calendar only: no target read, outcome count, or candidate-based censoring."""
    end = stamp(config['source']['end'])
    target = config['target']
    for query_id, anchor in con.execute('SELECT query_id,anchor FROM pilot_queries').fetchall():
        ready = anchor.replace(tzinfo=UTC) + timedelta(hours=target['horizon_hours'],
                            seconds=target['availability_delay_seconds'])
        con.execute('UPDATE pilot_queries SET label_is_mature=? WHERE query_id=?', [ready <= end, query_id])


def export_table(con, table, names, path, order, check):
    check()
    fields = '*' if names is None else ','.join('"' + name + '"' for name in names)
    con.execute('COPY (SELECT ' + fields + ' FROM ' + table + ' ORDER BY ' + order +
                ') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)', [str(path)])
    check()


def build_day(con, config, recipe, directory, check, *, expected_queries=None):
    """Lower-core seam: fixture tests supply an explicit synthetic connection/config.

    Production always calls this with its exact authenticated recipe and source.
    Q/C/F exports precede the first target creation. The test seam does not relax
    the public command's production archive, dependency, or recipe checks.
    """
    from scripts.anchor_pilot import create_queries, create_labels, utc
    from scripts.candidate_pilot import create_candidates, verify_catalog
    from scripts.manual_features import create_manual_features
    directory.mkdir(exist_ok=False)
    def stage(name, operation):
        check()
        value = operation()
        check()
        return value
    create_queries(con, config, stage=stage, budget_check=check)
    calendar_maturity(con, config)
    query_rows = con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM pilot_queries ORDER BY query_id').fetchall()
    if expected_queries is not None:
        need(len(query_rows) == expected_queries, 'Exact frozen daily query population differs')
    need(all(row[3] is True for row in query_rows), 'Complete mature development queries required')
    create_candidates(con, config, stage=stage)
    verify_catalog(con, config, stage=stage)
    create_manual_features(con, config, selected_registry(recipe), stage=stage, budget_check=check)
    actual = [row[0] for row in con.execute('DESCRIBE manual_features').fetchall()]
    expected = set(recipe['base_physical_columns']) | set(recipe['extra_feature_names'])
    need(len(actual) == 48 and set(actual) == expected, 'Chosen compiler48 physical schema differs')
    bad = con.execute('''SELECT count(*) FROM ((SELECT query_id,product_id FROM pilot_candidates
        EXCEPT ALL SELECT query_id,product_id FROM manual_features) UNION ALL
        (SELECT query_id,product_id FROM manual_features EXCEPT ALL
        SELECT query_id,product_id FROM pilot_candidates))''').fetchone()[0]
    need(bad == 0, 'Features changed full candidate key multiset')
    files = {kind: directory / (kind + '.parquet') for kind in ('queries', 'candidates', 'base', 'extra', 'labels')}
    export_table(con, 'pilot_queries', None, files['queries'], 'query_id', check)
    export_table(con, 'pilot_candidates', None, files['candidates'], 'query_id,product_id', check)
    export_table(con, 'manual_features', recipe['base_physical_columns'], files['base'], 'query_id,product_id', check)
    export_table(con, 'manual_features', ['query_id', 'product_id', *recipe['extra_feature_names']],
                 files['extra'], 'query_id,product_id', check)
    past_only = {kind: file_ref(path, check) for kind, path in files.items() if kind != 'labels'}
    create_labels(con, target_config=config['target'], source_start=utc(config['source']['start']),
                  source_end=utc(config['source']['end']), stage=stage, budget_check=check)
    after = con.execute('SELECT query_id,user_id,anchor,label_is_mature FROM pilot_queries ORDER BY query_id').fetchall()
    need(after == query_rows, 'Target creation altered frozen cohort or calendar maturity')
    export_table(con, 'pilot_labels', None, files['labels'], 'query_id,product_id', check)
    for kind, witness in past_only.items():
        need(file_ref(files[kind], check) == witness, 'Target creation changed past-only exports')
    refs = {kind: dict(path=path.name, **file_ref(path, check)) for kind, path in files.items()}
    manifest = directory / 'manifest.json'
    write_new(manifest, dict(version=1, queries=len(query_rows), protocol=config,
              label_blind_Q_C_F_frozen_before_Y=True, files=refs))
    files['_manifest'] = dict(path=manifest, witness=file_ref(manifest, check))
    files['_refs'] = refs
    verify_exports([files], check)
    return files


def prepare_matrix(files, recipe, arm, *, max_queries, max_rows, check, matrix_byte_cap=None):
    """Portable model_data transport: identical global ordering, float32 and Y.

    Paths are caller-owned fresh exports, never historical collection references.
    Only selected query keys are fixed before opening the full-Y files.
    """
    verify_exports(files, check)
    import duckdb
    import numpy as np
    from scripts.train_baselines import Prepared, numeric_feature_names, group_accounting
    need(arm in ('B', 'W'), 'Exactly frozen B/W arms required')
    need(type(max_rows) is int and 0 <= max_rows <= 5720000, 'Development matrix row cap')
    names = recipe['feature_names'][arm]
    cap = recipe['matrix_byte_cap'] if matrix_byte_cap is None else matrix_byte_cap
    con = duckdb.connect(':memory:', config={'threads': '2', 'memory_limit': '2GB', 'max_temp_directory_size': '0B'})
    try:
        check()
        for kind in ('queries', 'base'):
            con.read_parquet([str(row[kind]) for row in files]).create_view('all_' + kind)
        columns = con.execute('DESCRIBE all_base').fetchall()
        need([row[0] for row in columns] == recipe['base_physical_columns'], 'Named B45 projection/order differs')
        need(numeric_feature_names([row[0] for row in columns]) == recipe['feature_names']['B'], 'B41 numeric order differs')
        qt = dict((row[0], row[1]) for row in con.execute('DESCRIBE all_queries').fetchall())
        need(all(qt.get(k) == v for k, v in dict(query_id='VARCHAR', user_id='BIGINT',
                  anchor='TIMESTAMP', label_is_mature='BOOLEAN').items()), 'Query key/calendar schema differs')
        ft = dict((row[0], row[1]) for row in columns)
        need(all(ft.get(k) == v for k, v in dict(query_id='VARCHAR', product_id='BIGINT',
                  user_id='BIGINT', anchor='TIMESTAMP', last_user_event_time='TIMESTAMP').items()), 'Feature key schema differs')
        limit = '' if max_queries is None else ' LIMIT ' + str(max_queries)
        need(max_queries is None or type(max_queries) is int and 1 <= max_queries <= 26000, 'Query cap differs')
        con.execute('''CREATE TEMP TABLE chosen AS SELECT *,row_number() OVER(ORDER BY query_id)-1 group_index
            FROM (SELECT * FROM all_queries ORDER BY sha256(query_id),query_id''' + limit + ')')
        qn, uq, up, bad = con.execute('''SELECT count(*),count(DISTINCT query_id),count(DISTINCT(user_id,anchor)),
            count(*)FILTER(WHERE query_id IS NULL OR user_id IS NULL OR anchor IS NULL
            OR label_is_mature IS DISTINCT FROM true) FROM chosen''').fetchone()
        need(qn == uq == up and qn <= 26000 and bad == 0, 'Complete mature unique global Q required')
        # Reject orphans even if a future caller asks for a Q subset.
        need(con.execute('''SELECT count(*) FROM all_base f LEFT JOIN all_queries q USING(query_id)
            WHERE q.query_id IS NULL OR f.user_id IS DISTINCT FROM q.user_id OR f.anchor IS DISTINCT FROM q.anchor
            OR f.product_id IS NULL OR f.last_user_event_time >= q.anchor''').fetchone()[0] == 0,
            'Feature key/orphan/strict-past mismatch')
        con.execute('CREATE TEMP VIEW chosen_features AS SELECT f.*,q.group_index FROM all_base f JOIN chosen q USING(query_id)')
        n, unique = con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM chosen_features').fetchone()
        max_per = con.execute('SELECT coalesce(max(n),0) FROM(SELECT count(*) n FROM chosen_features GROUP BY query_id)').fetchone()[0]
        need(n == unique and n <= max_rows and n <= qn * 220 and max_per <= 220, 'Candidate key/matrix row cap before allocation')
        estimated = n * (len(names) * 4 + 4 + 8 + 1)
        need(type(cap) is int and 0 < cap <= 2 * 2**30, 'Matrix byte cap differs')
        if estimated > cap:
            raise MemoryError('Matrix byte cap exceeded before allocation')
        extra = recipe['extra_feature_names'] if arm == 'W' else []
        if extra:
            con.read_parquet([str(row['extra']) for row in files]).create_view('all_extra')
            et = con.execute('DESCRIBE all_extra').fetchall()
            need([tuple(row[:2]) for row in et] == [('query_id', 'VARCHAR'), ('product_id', 'BIGINT'),
                  *((name, 'BIGINT') for name in extra)], 'Exact three typed extra fields required')
            missing = con.execute('''SELECT count(*) FROM((SELECT query_id,product_id FROM all_base
                EXCEPT ALL SELECT query_id,product_id FROM all_extra) UNION ALL
                (SELECT query_id,product_id FROM all_extra EXCEPT ALL SELECT query_id,product_id FROM all_base))''').fetchone()[0]
            need(missing == 0, 'Extra/base exact key cover differs')
        check()
        # First Y read occurs only after label-blind Q selection and row/key caps.
        con.read_parquet([str(row['labels']) for row in files]).create_view('all_labels')
        lt = dict((row[0], row[1]) for row in con.execute('DESCRIBE all_labels').fetchall())
        need(lt.get('query_id') == 'VARCHAR' and lt.get('product_id') == 'BIGINT', 'FullY key types differ')
        need(con.execute('''SELECT count(*) FROM all_labels l LEFT JOIN all_queries q USING(query_id)
            WHERE q.query_id IS NULL OR l.product_id IS NULL''').fetchone()[0] == 0, 'Orphan/null full target')
        con.execute('CREATE TEMP VIEW chosen_labels AS SELECT l.* FROM all_labels l SEMI JOIN chosen q USING(query_id)')
        yn, yu = con.execute('SELECT count(*),count(DISTINCT(query_id,product_id)) FROM chosen_labels').fetchone()
        need(yn == yu and yn <= 1000000, 'Duplicate/oversize full target set')
        targets = {}
        for qid, item in con.execute('SELECT query_id,product_id FROM chosen_labels ORDER BY query_id,product_id').fetchall():
            targets.setdefault(qid, set()).add(item)
        queries = [(qid, user, anchor, frozenset(targets.get(qid, ()))) for qid, user, anchor in
                   con.execute('SELECT query_id,user_id,anchor FROM chosen ORDER BY group_index').fetchall()]
        x = np.empty((n, len(names)), dtype=np.float32)
        group = np.empty(n, dtype=np.int32)
        items = np.empty(n, dtype=np.int64)
        y = np.empty(n, dtype=np.int8)
        base = recipe['feature_names']['B']
        fields = [f'CAST(f."{name}" AS FLOAT) AS "{name}"' for name in base[:-2]]
        fields += ['CAST(epoch(f.anchor)-epoch(f.last_user_event_time) AS FLOAT) retrieval_last_event_age_seconds',
                   'CAST(f.last_user_event_time IS NULL AS FLOAT) retrieval_last_event_missing']
        fields += [f'CAST(a."{name}" AS FLOAT) AS "{name}"' for name in extra]
        join = ' JOIN all_extra a USING(query_id,product_id)' if extra else ''
        check()
        con.execute('SELECT f.group_index,f.product_id,CAST(l.product_id IS NOT NULL AS TINYINT) y,' + ','.join(fields) +
                    ' FROM chosen_features f LEFT JOIN chosen_labels l USING(query_id,product_id)' + join +
                    ' ORDER BY f.group_index,f.product_id')
        cursor, previous = 0, None
        while True:
            check()
            frame = con.fetch_df_chunk(8)
            if frame.empty:
                break
            stop = cursor + len(frame)
            need(stop <= n and len(frame) <= 16384, 'Chunk/result cover exceeded')
            need(all(np.issubdtype(frame[key].dtype, np.integer) for key in ('group_index', 'product_id')),
                 'Raw keys must remain nonnullable integers')
            g = frame['group_index'].to_numpy(dtype=np.int64)
            it = frame['product_id'].to_numpy(dtype=np.int64)
            need(not (np.any(g < 0) or np.any(g >= qn) or np.any(g[1:] < g[:-1])
                 or np.any((g[1:] == g[:-1]) & (it[1:] <= it[:-1]))
                 or previous is not None and (int(g[0]), int(it[0])) <= previous), 'Global group/item order differs')
            previous = int(g[-1]), int(it[-1])
            x[cursor:stop] = frame[names].to_numpy(dtype=np.float32, na_value=np.nan)
            need(not np.isinf(x[cursor:stop]).any(), 'Infinite float32 feature')
            group[cursor:stop], items[cursor:stop] = g, it
            y[cursor:stop] = frame['y'].to_numpy(dtype=np.int8)
            cursor = stop
        need(cursor == n, 'Matrix does not cover full candidates')
        result = Prepared(queries, group, items, x, y, list(names))
        group_accounting(result)
        check()
        return result
    finally:
        primary = sys.exception()
        close_preserving(con, primary)
        repin_exports_preserving(files, check, primary)


def array_ref(array, check):
    digest = hashlib.sha256()
    view = memoryview(array).cast('B') if array.size else memoryview(b'')
    for start in range(0, len(view), 1024 * 1024):
        check()
        digest.update(view[start:start + 1024 * 1024])
    return dict(shape=list(array.shape), dtype=str(array.dtype), sha256=digest.hexdigest())



def shared_base_identity(data, check):
    """Exact B41 float32 values AND missing masks, with at most4096 copied rows."""
    import numpy as np
    need(data.x.dtype == np.float32 and data.x.shape[1] in (41, 44), 'Shared B41 float32 representation differs')
    values, missing = hashlib.sha256(), hashlib.sha256()
    for start in range(0, len(data.x), 4096):
        check()
        block = np.array(data.x[start:start + 4096, :41], dtype=np.float32, copy=True, order='C')
        mask = np.isnan(block)
        missing.update(mask.tobytes(order='C'))
        block[mask] = 0
        values.update(block.tobytes(order='C'))
    return dict(shape=[len(data.x), 41], dtype='float32', values_sha256=values.hexdigest(),
                missing_sha256=missing.hexdigest(), max_copied_rows=4096)


def require_shared_base(identity, reference, phase):
    for name in ('queries_sha256', 'group', 'items', 'y', 'base41'):
        need(identity[name] == reference[name], 'B/W ' + phase + ' shared B41/cohort/key/Y differs: ' + name)
    if phase == 'train':
        need(identity['weights'] == reference['weights'], 'B/W train query-mass weights differ')

def matrix_identity(data, check):
    # Full targets are part of the identity, including positives absent from C.
    q = [(qid, int(user), iso(anchor), sorted(targets)) for qid, user, anchor, targets in data.queries]
    return dict(queries_sha256=hashlib.sha256(canonical(q).encode()).hexdigest(), feature_names=data.feature_names,
                base41=shared_base_identity(data, check),
                **{name: array_ref(getattr(data, name), check) for name in ('group', 'items', 'x', 'y')})


def verify_fresh_model(model, recipe, arm):
    from scripts.heldout_predictions import _same
    need(type(model.tree_count_) is int and model.tree_count_ == 300, 'Fresh model must contain all 300 trees')
    need(model.feature_names_ == recipe['feature_names'][arm], 'Fresh model feature order differs')
    need(model.get_cat_feature_indices() == model.get_text_feature_indices() == model.get_embedding_feature_indices() == [],
         'Numeric-only fresh model required')
    _same(recipe['effective_parameters'], model.get_all_params())


def fit_arm(arm, train_files, selection_files, recipe, directory, budget, *, backend=None, base_reference=None, source_check=None):
    """One fixed fit; backend injection is exclusively an explicit unit-test seam."""
    import numpy as np
    from scripts import train_baselines as b
    if backend is None:
        from catboost import CatBoostClassifier, Pool
    else:
        CatBoostClassifier, Pool = backend
    check = budget.check
    if source_check is not None:
        source_check()
    train = prepare_matrix(train_files, recipe, arm, max_queries=recipe['periods']['train']['queries'],
                           max_rows=5720000, check=check)
    need(len(train.queries) == recipe['periods']['train']['queries'], 'Exact frozen training population differs')
    counts, positive, negative, informative, weights, accounting = b.group_accounting(train)
    need(len(train.group) > 0 and np.any(train.y == 0) and np.any(train.y == 1), 'Observed binary training support required')
    identity = matrix_identity(train, check)
    identity['weights'] = array_ref(weights, check)
    if base_reference is not None:
        require_shared_base(identity, base_reference['train'], 'train')
    check()
    pool = Pool(train.x, label=train.y, weight=weights, feature_names=train.feature_names, thread_count=2)
    model = CatBoostClassifier(**recipe['constructor_parameters'])
    callback = b._BudgetCallback(check)
    # Reserve before native fit, including failed fits; no retry or alternative arm.
    budget.reserve_fit()
    write_new(directory / (arm + '.fit-consumed.json'), dict(arm=arm, attempt=budget.fit_attempts,
              constructor_parameters=recipe['constructor_parameters'], train=identity, accounting=accounting))
    if source_check is not None:
        source_check()
    model.fit(pool, callbacks=[callback])
    if callback.failure is not None:
        raise callback.failure
    check()
    verify_fresh_model(model, recipe, arm)
    path = directory / (arm + '.cbm')
    need(not path.exists(), 'New model output required')
    model.save_model(str(path), format='cbm')
    model_witness = file_ref(path, check)
    check()
    del pool, train, weights, counts, positive, negative, informative, model
    gc.collect()
    # Evaluate the actual fresh serialized model, not a historical CBM or prefix.
    need(file_ref(path, check) == model_witness, 'Fresh serialized model changed before reload')
    model = CatBoostClassifier()
    model.load_model(str(path), format='cbm')
    verify_fresh_model(model, recipe, arm)
    actual_parameters = deepcopy(model.get_all_params())
    selection = prepare_matrix(selection_files, recipe, arm, max_queries=None, max_rows=880000, check=check)
    need(len(selection.queries) == recipe['periods']['selection']['queries'], 'Exact frozen selection population differs')
    selection_identity = matrix_identity(selection, check)
    if base_reference is not None:
        require_shared_base(selection_identity, base_reference['selection'], 'selection')
    if source_check is not None:
        source_check()
    scores = np.asarray(b.predict_scores(model, selection, 'Logloss'), dtype=np.float64)
    check()
    ranked = b.rankings(selection, scores)
    out = directory / (arm + '.selection-scores.npz')
    with out.open('xb') as stream:
        np.savez_compressed(stream, group=selection.group, items=selection.items, scores=scores)
    from scripts.ranking_metrics import evaluate
    need(file_ref(path, check) == model_witness, 'Fresh serialized model changed during consumption')
    summary = dict(arm=arm, model=model_witness, predictions=file_ref(out, check),
                   train=identity, training_accounting=accounting, selection=selection_identity,
                   evaluation=asdict(evaluate(ranked, recipe['k'])), trained_iterations=300,
                   scoring_prefix=300, fit_attempts=1, score_type='RawFormulaVal',
                   actual_effective_parameters=actual_parameters, model_feature_names=model.feature_names_)
    del model, selection, scores
    gc.collect()
    check()
    write_new(directory / (arm + '.json'), summary)
    return ranked, summary


def compare_two(train_files, selection_files, recipe, directory, budget, *, backend=None, source_check=None):
    from scripts.ranking_metrics import paired_user_bootstrap
    b_ranked, baseline = fit_arm('B', train_files, selection_files, recipe, directory, budget, backend=backend, source_check=source_check)
    w_ranked, program = fit_arm('W', train_files, selection_files, recipe, directory, budget, backend=backend, base_reference=baseline, source_check=source_check)
    need(budget.fit_attempts == 2, 'Exactly two frozen fits required')
    for name in ('queries_sha256', 'group', 'items', 'y', 'base41'):
        need(baseline['train'][name] == program['train'][name], 'B/W training cohort/keys/Y differ')
        need(baseline['selection'][name] == program['selection'][name], 'B/W selection cohort/keys/Y differ')
    need(baseline['train']['weights'] == program['train']['weights'], 'B/W query-mass weights differ')
    budget.check()
    difference = paired_user_bootstrap(w_ranked, b_ranked, k=recipe['k'], metric='ndcg',
                estimand='conditional_macro_query', replicates=recipe['bootstrap_replicates'], seed=recipe['bootstrap_seed'])
    budget.check()
    return dict(B=baseline, W=program, W_minus_B=asdict(difference),
                post_selection_reproduction=True, selection_changes_recipe=False, final_targets_opened=False)


def run(raw, output, recipe_path, budget):
    """Exclusive attempt from the pinned archive; failures remain consumed."""
    output, raw = Path(output).absolute(), Path(raw).resolve()
    need(output.parent.is_dir() and not output.exists() and not output.is_symlink(), 'Fresh output under existing parent required')
    output.mkdir(mode=0o700, exist_ok=False)
    write_new(output / 'consumed.json', dict(version=1, recipe_sha256=RECIPE_SHA256, raw=str(raw),
              resource_limits=dict(cpu=budget.cpu_limit, wall=budget.wall_limit, rss=budget.rss_limit, spill=budget.spill_limit),
              status='attempt_consumed_no_retry'))
    try:
        recipe, recipe_raw, recipe_witness = validate_recipe(recipe_path, budget.check)
        sources = SourceBinding(recipe, budget.check)
        sources.load_cores()
        from scripts.source_import import PRODUCTION_PROFILE
        need(recipe['source'] == PRODUCTION_PROFILE, 'Production source profile differs')
        need(shutil.disk_usage(output).free >= recipe['minimum_free_disk_bytes'], 'At least 40 GiB free scratch disk required; more may be needed')
        write_snapshot(output / 'recipe.json', recipe_raw, recipe_witness, budget.check)
        sources.check()
        budget.spill_paths = [output / 'source/spill', output / 'feature-spill']
        from scripts.source_import import import_archive
        imported = import_archive(raw, output / 'source', recipe['source'], check=budget.check)
        write_new(output / 'source.json', imported)
        database = Path(imported['database']['path'])
        source_db_ref = file_ref(database, budget.check)
        need(source_db_ref == {k: imported['database'][k] for k in ('sha256', 'bytes')},
             'Fresh typed source DB differs from import evidence')
        import duckdb
        con = duckdb.connect(imported['database']['path'], read_only=True,
                    config={'threads': '2', 'memory_limit': '2GB', 'max_temp_directory_size': '8GiB',
                            'temp_directory': str(output / 'feature-spill')})
        phases = {}
        try:
            for name, period in recipe['periods'].items():
                # JSON sort order is irrelevant: never fit until every development export exists.
                directory = output / name
                directory.mkdir()
                files = []
                day = stamp(period['start'])
                while day < stamp(period['end']):
                    budget.check()
                    sources.check()
                    need(parse_json(recipe_raw) == recipe, 'In-memory frozen recipe changed')
                    config = day_protocol(recipe, day)
                    files.append(build_day(con, config, recipe, directory / day.strftime('%Y-%m-%d'),
                                           budget.check, expected_queries=2000))
                    day += timedelta(days=1)
                phases[name] = files
        finally:
            close_preserving(con, sys.exception())
        budget.check()
        sources.check()
        need(file_ref(database, budget.check) == source_db_ref, 'Typed source changed during Q/C/Y/features')
        compared = compare_two(phases['train'], phases['selection'], recipe, output, budget, source_check=sources.check)
        verify_exports([row for phase in phases.values() for row in phase], budget.check)
        need(file_ref(output / 'recipe.json', budget.check) == recipe_witness, 'Owned authenticated recipe changed')
        need(parse_json(recipe_raw) == recipe, 'In-memory frozen recipe changed')
        sources.check()
        for arm, summary in ((name, compared[name]) for name in ('B', 'W')):
            need(file_ref(output / (arm + '.cbm'), budget.check) == summary['model'], 'Produced model changed before report')
            need(file_ref(output / (arm + '.selection-scores.npz'), budget.check) == summary['predictions'],
                 'Produced scores changed before report')
        report = dict(version=1, status='complete_produced_pending_independent_review',
                      recipe_sha256=RECIPE_SHA256, source=imported['source'],
                      dependencies=sources.witnesses, command_source=sources.command, recipe=recipe_witness,
                      data_exports=export_inventory(phases, output),
                      environment=dict(python=platform.python_version(), platform=sys.platform + '-' + platform.machine(),
                                       locked_packages=recipe['environment']['packages']),
                      comparison=compared, telemetry=budget.telemetry(),
                      historical_model_equivalence_claimed=False, independent_acceptance_issued=False,
                      private_model_inputs=[], historical_approval_inputs=[], final_dates_in_scope=False)
        budget.check()
        write_new(output / 'report.json', report)
        b = compared['B']['evaluation']['conditional_macro_query']['ndcg']
        w = compared['W']['evaluation']['conditional_macro_query']['ndcg']
        text = ('# Frozen development reproduction\n\nTwo fresh 300-tree fits: manual B41 and generated R2/L05 W44.\n\n'
                f'Conditional macro-query NDCG@20: B={b}, W={w}.\n\n'
                'This reproduces a previously selected recipe. It is not a new selection or heldout result. '
                'Full targets include products outside candidates; empty-target queries remain in all-query summaries. '
                'See report.json for all estimands, paired user bootstrap, matrix identities and cooperative costs. '
                'Independent review and full external process-tail acceptance remain separate.\n')
        with (output / 'report.md').open('x', encoding='utf8') as stream:
            stream.write(text)
        budget.check()
        sources.check()
        verify_exports([row for phase in phases.values() for row in phase], budget.check)
        need(file_ref(output / 'recipe.json', budget.check) == recipe_witness, 'Owned recipe changed at terminal close')
        return report
    except BaseException as error:
        try:
            fail_preserving(error, output, budget)
        except BaseException as secondary:
            secondary_note(error, 'Failure handler', secondary)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory; parent must exist')
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--cpu-seconds', type=int, required=True)
    parser.add_argument('--wall-seconds', type=int, required=True)
    parser.add_argument('--rss-bytes', type=int, required=True)
    parser.add_argument('--spill-bytes', type=int, required=True)
    args = parser.parse_args(argv)
    budget = Budget(args.cpu_seconds, args.wall_seconds, args.rss_bytes, args.spill_bytes)
    run(args.raw, args.output, args.recipe, budget)


if __name__ == '__main__':
    main()
