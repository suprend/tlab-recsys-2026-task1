"""MA arm of the H&M Kaggle transfer: locked M23 plus every column of the frozen agent set.

Contract: docs/hm-agent-design.md, sections 3-6. scripts/hm_kaggle.py and the
locked modules are reused by import and never edited; their functions are called
through module attributes (``kaggle.locked_recipe(...)``) so that fixture patches
apply. Agent values come only from scripts/hm_agent_sandbox.py over the exported
history: labels, collections and future rows never reach the sandbox. Run as
``python -I scripts/hm_agent_kaggle.py``; every command refuses otherwise and
prints one JSON line. Row-level outputs (sidecars, models, scores, leakcheck
scratch) stay inside the ignored artifacts/ tree.

Deviations (one rule for every step): under a deviations file, code equal to the
LAST record's code runs as that record; any other code runs with a null
``deviation``, and the step refuses only when a record rebuilds it (stale). Steps
that read the prereg (fit, contrast, gate) also refuse code that is neither the
prereg's nor the last record's; the others cannot know the prereg code, and the
gate binds it: a recorded deviation must carry its record's code, a null one
under a deviations file the prereg code.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # ``python -I`` omits the script directory; the checkout goes after the stdlib.
    sys.path.append(str(ROOT))

from scripts import hm_experiment as experiment  # noqa: E402
from scripts import hm_kaggle as kaggle  # noqa: E402
from scripts import hm_agent_sandbox as sandbox  # noqa: E402

pilot = experiment.pilot
SIDECAR_FORMAT = 'hm-agent-sidecar-v1'
FIT_FORMAT = 'hm-agent-fit-v1'
SCORE_FORMAT = 'hm-agent-score-v1'
LEAKCHECK_FORMAT = 'hm-agent-leakcheck-v1'
CONTRAST_FORMAT = 'hm-agent-contrast-v1'
GATE_FORMAT = 'hm-agent-gate-v1'
DEVIATIONS_FORMAT = 'hm-agent-deviations-v1'
# ``code`` = sandbox.agent_code_identity(): one key set for the prereg, every deviation and every artifact.
AUDIT_MODULE = 'hm_result_audit.py'  # paired bootstrap of contrast
KEYS = ['customer_id', 'article_id']
VALUE_TOLERANCE = 1e-9  # leakcheck cells: two NULLs are equal, else |x-y| <= 1e-9*(1+|x|)
SCORE_TOLERANCE = 1e-9  # control: |score difference| against hm_kaggle score
INVARIANCE_BATCHES = 4  # leakcheck: one batch of N customers against 4 batches of N/4
BOOTSTRAP_DRAWS, BOOTSTRAP_SEED = 2000, 2026
# Gate (section 4). Popularity on the port week: docs/hm-pilot.md:65, MAP@12 0.00562780.
POPULARITY_FLOOR = 0.0056
PARITY = (0.5, 2.0)  # non-NULL share at scoring within [0.5*min, 2*max] of the sidecar shares
GATE_CHECKS = ('prereg', 'leakcheck', 'control', 'finite', 'parity', 'popularity')
# The chain in order: a deviation that rebuilds a step also rebuilds every later step.
STEPS = ('leakcheck', 'sidecar', 'port', 'contrast', 'final', 'score', 'control', 'assemble')
# Chain anchors (sections 3.1, 4 and the leakcheck run): the gate binds its inputs to them.
SIDECAR_ANCHORS = ('2020-08-12', '2020-08-19', '2020-08-26', '2020-09-02', '2020-09-09', '2020-09-16')
PORT_TRAIN_ANCHORS = ('2020-08-12', '2020-08-19', '2020-08-26', '2020-09-02', '2020-09-09')
PORT_VALIDATION_ANCHOR = '2020-09-16'
FINAL_TRAIN_ANCHORS = ('2020-08-19', '2020-08-26', '2020-09-02', '2020-09-09', '2020-09-16')  # no validation
LEAKCHECK_ANCHORS = ('2020-08-19', '2020-09-16')
LEAKCHECK_USERS = 2000


def positive_int(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(f'{label} must be a positive integer')
    return value


def code_identity(deadline=None):
    """The one code key set shared by A, B and C: sandbox.agent_code_identity()."""
    return sandbox.agent_code_identity(deadline)


def database_identity(database, deadline):
    """The DB bytes and their validated EDA provenance, as hm_kaggle records them."""
    source = Path(database).resolve()
    identity = dict(sha256=experiment.sha256_file(source, deadline), bytes=source.stat().st_size)
    return source, identity, kaggle.database_sources(source, identity)


def read_full_export(export, db_identity, sources):
    """The complete history export of exactly this database; a --before cut is refused."""
    path = Path(export).resolve()
    exported = sandbox.read_export(path)
    if exported.get('format') != sandbox.EXPORT_FORMAT or exported.get('before') is not None:
        raise ValueError('A complete hm_agent export (without --before) is required')
    if exported.get('database') != db_identity or exported.get('sources') != sources:
        raise ValueError('Export and database must be the same audited bytes')
    return path, exported


def read_set(agent_set, deadline=None):
    """Frozen agent set: digest, file SHA-256 and the ordered column list; then its proposal ids."""
    from scripts.hm_feature_engine import feature_registry
    path = Path(agent_set).resolve()
    try:
        agent = sandbox.read_agent_set(path)
    except Exception as exc:
        if is_proposal_error(exc):
            try:
                proposals = json.loads(path.read_text(encoding='utf-8')).get('proposals') or []
                ids = [p['id'] for p in proposals if isinstance(p, dict) and isinstance(p.get('id'), str)]
            except (OSError, ValueError, AttributeError):
                ids = []
            exc.hm_agent_proposal = failed_proposal(exc, ids)
        raise
    columns = list(agent['columns'])
    taken = {d.name for d in feature_registry()} | set(experiment.RESERVED) | set(KEYS)
    if len(set(columns)) != len(columns) or taken & set(columns):
        raise ValueError('Agent columns must be unique and disjoint from engine and reserved names')
    ids = [p['id'] for p in agent['proposals']]
    return path, dict(digest=agent['digest'], sha256=experiment.sha256_file(path, deadline), columns=columns), ids


def is_proposal_error(exc):
    proposal_error = getattr(sandbox, 'ProposalError', None)
    return isinstance(proposal_error, type) and isinstance(exc, proposal_error)


def failed_proposal(exc, ids):
    """The proposal a sandbox ProposalError names: an attribute, or one id as a whole word of its message."""
    for attribute in ('proposal_id', 'proposal', 'id'):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and value in ids:
            return value
    message = str(exc)
    named = [i for i in ids if re.search(rf'(?<![\w-]){re.escape(i)}(?![\w-])', message)]
    leading = [i for i in named if re.match(rf'\W*{re.escape(i)}(?![\w-])', message)]
    if len(leading) == 1:
        return leading[0]
    return named[0] if len(named) == 1 else None


def note_proposal(report, exc, ids):
    """Failure rule: a proposal error fails the whole command, and its report names the proposal.

    Columns are never dropped, skipped or set to NULL instead. None means the
    error did not name one of the set's proposals.
    """
    if is_proposal_error(exc):
        report['proposal'] = failed_proposal(exc, ids)
        try:
            exc.hm_agent_proposal = report['proposal']  # for the masked CLI line
        except AttributeError:
            pass


def collection_identity(path, manifest, deadline):
    return dict(manifest_sha256=experiment.sha256_file(Path(path)/'manifest.json', deadline),
                frame_sha256=manifest['files']['frame.parquet'], qcy_identity=manifest['qcy_identity'],
                candidate_identity=manifest['candidate_identity'], database=manifest['database'])


def align_block(keys, values, columns):
    """Agent values aligned 1:1 to the rows of ``keys``; a missing, extra or repeated key is an error."""
    if list(values.columns) != KEYS+list(columns):
        raise ValueError('Agent values must hold the two keys and the agent-set columns in order')
    if len(values) != len(keys):
        raise ValueError('Agent values must have exactly one row per key')
    merged = keys[KEYS].reset_index(drop=True).merge(values, on=KEYS, how='left', validate='one_to_one',
                                                     indicator='_hm_agent_match', sort=False)
    if len(merged) != len(keys) or not (merged['_hm_agent_match'] == 'both').all():
        raise ValueError('Agent values must cover exactly the given keys')
    return merged.drop(columns='_hm_agent_match')


def agent_block(frame, columns):
    """Agent columns as contiguous float32; NULL, NaN, +-inf and float32 overflow become NaN.

    experiment.model_arrays is not used here: it requires finite values. The
    same function feeds fit and score.
    """
    import numpy as np
    columns = list(columns)
    if not columns:
        return np.empty((len(frame), 0), dtype=np.float32)
    values = frame[columns].to_numpy(dtype=np.float64, na_value=np.nan)
    with np.errstate(over='ignore', invalid='ignore'):
        block = values.astype(np.float32)
    block[~np.isfinite(block)] = np.nan
    return np.ascontiguousarray(block)


def cell_mismatches(left, right, columns):
    """Per column: cells where exactly one side is NULL or |x-y| > 1e-9*(1+|x|).

    NULL is the contract's "no data": missing, NaN or +-inf. Counts only.
    """
    import numpy as np
    counts = {}
    for name in columns:
        x = left[name].to_numpy(dtype=np.float64, na_value=np.nan)
        y = right[name].to_numpy(dtype=np.float64, na_value=np.nan)
        x_null, y_null = ~np.isfinite(x), ~np.isfinite(y)
        with np.errstate(invalid='ignore', over='ignore'):
            close = np.abs(x-y) <= VALUE_TOLERANCE*(1+np.abs(x))
        equal = (x_null & y_null) | (~x_null & ~y_null & close)
        counts[name] = int((~equal).sum())
    return counts


def sidecar(database, export, agent_set, collection, output, threads=4, wall_seconds=3600, deviations=None):
    """Agent columns for every candidate key of one labelled collection; the collection is unchanged.

    A connection of its own reads only customer_id and article_id from
    frame.parquet into keys.parquet; the sandbox receives those keys alone.
    """
    positive_int(threads, 'Threads')
    deadline = experiment.Deadline(wall_seconds)
    code = code_identity(deadline)
    deviated = current_deviation(deviations, 'sidecar', deadline)
    collection = Path(collection).resolve()
    manifest = kaggle.read_collection(collection, deadline)
    source, db_identity, sources = database_identity(database, deadline)
    export_path, exported = read_full_export(export, db_identity, sources)
    set_path, agent, ids = read_set(agent_set, deadline)
    if manifest['database'] != exported['database']:
        raise ValueError('Collection and export must come from the same database')
    columns = agent['columns']
    output = kaggle.new_output(output)
    report = dict(format=SIDECAR_FORMAT, status='running', anchor=manifest['anchor'], started_at_utc=kaggle.utc_now())
    con = timer = None
    try:
        import numpy as np
        report['resources'] = dict(experiment.resource_preflight(output), threads=threads)
        report['collection'] = collection_identity(collection, manifest, deadline)
        report['agent_set'] = agent
        report['export_digest'] = exported['digest']
        report['code'] = code
        report.update(deviated)
        report['runtime'] = experiment.runtime_identity()
        con = kaggle.memory_connection(output, threads)
        timer = deadline.interrupt_sql(con)
        con.execute('''CREATE TEMP TABLE hm_a_keys AS SELECT customer_id,article_id FROM read_parquet(?)
            ORDER BY customer_id,article_id''', [str(collection/'frame.parquet')])
        con.sql('SELECT customer_id,article_id FROM hm_a_keys ORDER BY customer_id,article_id').write_parquet(
            str(output/'keys.parquet'))
        keys = con.execute('SELECT customer_id,article_id FROM hm_a_keys ORDER BY customer_id,article_id').fetchdf()
        if len(keys) != manifest['population']['candidate_rows']:
            raise ValueError('Keys must be every candidate row of the collection')
        report['keys'] = dict(rows=len(keys), sha256=experiment.sha256_file(output/'keys.parquet', deadline))
        deadline.check()
        values, info = sandbox.agent_columns(export_path, manifest['anchor'], keys, set_path, threads=threads,
                                             deadline=deadline)
        block = align_block(keys, values, columns)
        del values
        report['seconds'] = info['seconds']
        # Non-NULL in the contract's sense: a value the model receives as a number.
        finite = np.isfinite(agent_block(block, columns)).sum(axis=0)
        report['non_null'] = {name: int(count) for name, count in zip(columns, finite)}
        partial = output/f'agent.parquet.{os.getpid()}.part'
        projection = ''.join(f',CAST({experiment.quote(c)} AS DOUBLE) AS {experiment.quote(c)}' for c in columns)
        con.register('_hm_agent_block', block)
        try:
            con.sql(f'''SELECT customer_id,article_id{projection} FROM _hm_agent_block
                ORDER BY customer_id,article_id''').write_parquet(str(partial))
        finally:
            con.unregister('_hm_agent_block')
        del block
        written = con.execute('SELECT * FROM read_parquet(?) LIMIT 0', [str(partial)]).description
        rows = con.execute('SELECT count(*) FROM read_parquet(?)', [str(partial)]).fetchone()[0]
        if ([d[0] for d in written] != KEYS+columns or any(str(d[1]) != 'DOUBLE' for d in written[2:]) or
                rows != report['keys']['rows']):
            raise ValueError('agent.parquet must hold every key once with DOUBLE agent columns')
        os.replace(partial, output/'agent.parquet')
        report['files'] = {'agent.parquet': experiment.sha256_file(output/'agent.parquet', deadline)}
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        note_proposal(report, exc, ids)
        error = kaggle.failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
        report['peak_rss_bytes'] = kaggle.peak_rss_bytes()
        kaggle.atomic_json(output/'manifest.json', report)
    return report


def deviation_time(value):
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        moment = None
    if moment is None or moment.tzinfo is None:
        raise ValueError('Deviation time must be ISO 8601 with its UTC offset, as 2026-10-21T10:15+03:00')
    return moment


def read_deviations(deviations, keys):
    """The deviations file: (entries, SHA-256); every entry names its prereg and has the full code map over ``keys``."""
    raw = Path(deviations).resolve().read_bytes()
    log = json.loads(raw)
    if not isinstance(log, dict) or log.get('format') != DEVIATIONS_FORMAT:
        raise ValueError(f'Deviations file must have format {DEVIATIONS_FORMAT}')
    entries = log.get('deviations')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Deviations file must list at least one deviation')
    times = []
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or not entry['id'] or
                not isinstance(entry.get('reason'), str) or not entry['reason'].strip() or
                not isinstance(entry.get('prereg_sha256'), str) or
                not isinstance(entry.get('code'), dict) or set(entry['code']) != set(keys) or
                not all(isinstance(v, str) for v in entry['code'].values())):
            raise ValueError('Every deviation needs id, time, reason, prereg_sha256 and the full code map of the prereg files')
        rebuilds = entry.get('rebuilds')
        if (not isinstance(rebuilds, list) or not rebuilds or len(set(map(str, rebuilds))) != len(rebuilds) or
                any(step not in STEPS for step in rebuilds)):
            raise ValueError(f"Every deviation needs rebuilds: distinct steps of {', '.join(STEPS)}")
        times.append(deviation_time(entry.get('time')))
    if len({e['id'] for e in entries}) != len(entries) or times != sorted(times):
        raise ValueError('Deviation ids must be unique and the entries in time order')
    return entries, hashlib.sha256(raw).hexdigest()


def deviation_fields(deviation, entries, sha256):
    """What an artifact records of the deviations file it ran under.

    ``deviations_records`` and ``deviations_prefix_sha256`` (canonical digest of
    those records) let the gate check that the file has only grown since.
    """
    return dict(deviation=deviation, deviations_sha256=sha256, deviations_records=len(entries) if sha256 else 0,
                deviations_prefix_sha256=experiment.canonical_digest(entries) if sha256 else None)


def current_deviation(deviations, step, deadline=None):
    """deviation_fields of a sidecar, leakcheck, score or control run; all empty without a file.

    With a deviations file, code equal to the LAST entry's code records that
    entry; other code records a null deviation and is refused when a record
    rebuilds ``step``. The prereg code is bound later, by the gate.
    """
    if deviations is None:
        return deviation_fields(None, [], None)
    code = code_identity(deadline)
    entries, sha256 = read_deviations(deviations, code)
    if entries[-1]['code'] == code:
        return deviation_fields(entries[-1]['id'], entries, sha256)
    required = stale_deviation(None, step, entries)
    if required:
        raise ValueError(f'Code differs from the last deviation and {step} is stale: deviation {required} rebuilds it')
    return deviation_fields(None, entries, sha256)


def deviation_problem(artifact, entries):
    """Why an artifact's deviation fields do not fit the supplied deviation records; None if they do.

    A non-null id must be one of the records; a recorded file must be a prefix
    of the supplied one, and its id the last record of that prefix.
    """
    deviation, sha256 = artifact.get('deviation'), artifact.get('deviations_sha256')
    records, prefix = artifact.get('deviations_records'), artifact.get('deviations_prefix_sha256')
    if deviation is not None and deviation not in [e['id'] for e in entries]:
        return f'deviation {deviation!r} is not a record of the supplied deviations file'
    if sha256 is None:
        if deviation is None and prefix is None and records in (None, 0):
            return None
        return 'deviation fields without a deviations file'
    if type(records) is not int or not 1 <= records <= len(entries) or experiment.canonical_digest(entries[:records]) != prefix:
        return 'its deviations file is not a prefix of the supplied one'
    if deviation is not None and deviation != entries[records-1]['id']:
        return 'its deviation is not the last record of its deviations file'
    return None


def code_problem(artifact, prereg_code, entries):
    """Why an artifact's code is not the code of the record it names; None if it is (or deviation_problem applies).

    A recorded deviation carries that record's code; a null deviation under a
    deviations file (records > 0) the prereg code.
    """
    deviation, records = artifact.get('deviation'), artifact.get('deviations_records')
    if type(records) is not int or not 0 <= records <= len(entries):
        return None
    if deviation is not None:
        if records and entries[records-1]['id'] == deviation and artifact['code'] != entries[records-1]['code']:
            return f'its code is not the code of deviation {deviation!r}'
        return None
    if records > 0 and artifact['code'] != prereg_code:
        return 'its deviation is null under a deviations file, but its code is not the prereg code'
    return None


def stale_deviation(deviation, step, entries):
    """The id required at ``step`` when ``deviation`` is older than it (or null); None if not stale."""
    required = required_deviations(entries)
    order = {e['id']: n for n, e in enumerate(entries)}
    if step in required and order.get(deviation, -1) < required[step]:
        return entries[required[step]]['id']
    return None


def required_deviations(entries):
    """{step: index of the latest entry that rebuilds it or an earlier step}."""
    required = {}
    for index, entry in enumerate(entries):
        first = min(STEPS.index(step) for step in entry['rebuilds'])
        for step in STEPS[first:]:
            required[step] = index
    return required


def read_prereg(prereg, deviations=None, code=None):
    """Preregistration, optional deviations file and, with ``code``, acceptance of the current code.

    Accepted code equals the prereg ``code`` or the ``code`` of the LAST
    deviation; each deviation states the full code map after its fix, and the
    file names this prereg by SHA-256. Returns the record, both SHA-256, the
    deviation id (None for the prereg code), every registered code map, which
    artifacts made before a later fix may carry, and the deviation entries.
    """
    path = Path(prereg).resolve()
    if not path.is_file():
        raise FileNotFoundError('Preregistration file is required before any MA number')
    raw = path.read_bytes()
    record = json.loads(raw)
    agent = record.get('agent_set') if isinstance(record, dict) else None
    if (not isinstance(agent, dict) or not isinstance(agent.get('sha256'), str) or
            not isinstance(record.get('export_digest'), str) or not isinstance(record.get('code'), dict) or
            not record['code']):
        raise ValueError('Preregistration must state agent_set.sha256, export_digest and code')
    accepted = dict(record=record, sha256=hashlib.sha256(raw).hexdigest(), deviation=None, deviations_sha256=None,
                    codes=[record['code']], entries=[])
    entries = []
    if deviations is not None:
        entries, accepted['deviations_sha256'] = read_deviations(deviations, record['code'])
        if any(e['prereg_sha256'] != accepted['sha256'] for e in entries):
            raise ValueError('A deviation belongs to another preregistration (prereg_sha256)')
        accepted['codes'] = accepted['codes']+[e['code'] for e in entries]
        accepted['entries'] = entries
    if code is not None:
        if entries and code == entries[-1]['code']:
            accepted['deviation'] = entries[-1]['id']
        elif code != record['code']:
            raise ValueError('Code differs from the preregistered hashes and from the last deviation')
    accepted['fields'] = deviation_fields(accepted['deviation'], entries, accepted['deviations_sha256'])
    return accepted


def read_sidecars(root, paths, manifests, registered, deadline):
    """One completed sidecar per collection, by registered code, from one preregistered set and export."""
    found = {}
    for path, manifest in zip(paths, manifests):
        anchor = manifest['anchor']
        directory = Path(root)/anchor
        side = kaggle.read_json(directory/'manifest.json')
        if side.get('format') != SIDECAR_FORMAT or side.get('status') != 'completed' or side.get('anchor') != anchor:
            raise ValueError(f'Completed hm_agent sidecar for {anchor} required')
        if side['collection'] != collection_identity(path, manifest, deadline):
            raise ValueError(f'Sidecar {anchor} was built from another collection')
        if side['keys']['rows'] != manifest['population']['candidate_rows']:
            raise ValueError(f'Sidecar {anchor} must cover every candidate key')
        if experiment.sha256_file(directory/'agent.parquet', deadline) != side['files']['agent.parquet']:
            raise ValueError(f'Sidecar {anchor} bytes changed after its manifest')
        if side['code'] not in registered['codes']:
            raise ValueError(f'Sidecar {anchor} was built by code neither preregistered nor in a deviation')
        problem = deviation_problem(side, registered['entries'])
        if problem:
            raise ValueError(f'Sidecar {anchor}: {problem}')
        required = stale_deviation(side.get('deviation'), 'sidecar', registered['entries'])
        if required:
            raise ValueError(f'Sidecar {anchor} is stale: deviation {required} rebuilds sidecars')
        found[anchor] = (directory, side, experiment.sha256_file(directory/'manifest.json', deadline))
    first = next(iter(found.values()))[1]
    if any(side['agent_set'] != first['agent_set'] or side['export_digest'] != first['export_digest']
           for _, side, _ in found.values()):
        raise ValueError('Sidecars must come from one agent set and one export')
    record = registered['record']
    if first['agent_set']['sha256'] != record['agent_set']['sha256'] or first['export_digest'] != record['export_digest']:
        raise ValueError('Sidecars differ from the preregistered agent set or export')
    agent = dict(digest=first['agent_set']['digest'], sha256=first['agent_set']['sha256'],
                 columns=list(first['agent_set']['columns']), export_digest=first['export_digest'],
                 sidecars={anchor: value[2] for anchor, value in found.items()})
    return agent, {anchor: value[0]/'agent.parquet' for anchor, value in found.items()}


def sidecar_rows(con, frame, path, columns):
    """Sidecar values of exactly the frame's keys, in the frame's (customer_id, article_id) order."""
    described = con.execute('SELECT * FROM read_parquet(?) LIMIT 0', [str(path)]).description
    if [d[0] for d in described] != KEYS+list(columns):
        raise ValueError('Sidecar columns differ from the agent set')
    projection = ''.join(','+'a.'+experiment.quote(c) for c in columns)
    con.register('_hm_agent_keys', frame[KEYS])
    try:
        block = con.execute(f'''SELECT k.customer_id,k.article_id{projection} FROM _hm_agent_keys k
            JOIN read_parquet(?) a USING(customer_id,article_id) ORDER BY k.customer_id,k.article_id''',
                            [str(path)]).fetchdf()
    finally:
        con.unregister('_hm_agent_keys')
    if (len(block) != len(frame) or not (block['customer_id'].to_numpy() == frame['customer_id'].to_numpy()).all() or
            not (block['article_id'].to_numpy() == frame['article_id'].to_numpy()).all()):
        raise ValueError('Sidecar rows must match the frame keys one to one')
    return block


def fit_ma(seed, train_paths, sidecars, prereg, output, validation_path=None, threads=8, wall_seconds=14400,
           deviations=None):
    """One fixed 500-tree CPU fit of locked M23 plus every frozen agent column.

    Rows, labels, negatives and weights are those of ``kaggle.fit('M')`` on the
    same collections (experiment.load_part); the agent block is joined by keys.
    Without a matching preregistration (or last deviation) nothing is written.
    """
    recipe = kaggle.locked_recipe('M', seed, threads)
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
    registered = read_prereg(prereg, deviations, code)
    if registered['record'].get('threads') != threads:
        raise ValueError('Fit threads differ from the preregistered threads')
    required = stale_deviation(registered['deviation'], 'port' if validation_path is not None else 'final',
                               registered['entries'])
    if required:
        raise ValueError(f'Deviation {required} rebuilds this fit; the current code must be its code')
    manifests = [kaggle.read_collection(p, deadline) for p in train_paths]
    val_manifest = kaggle.read_collection(validation_path, deadline) if validation_path is not None else None
    anchors = [date.fromisoformat(m['anchor']) for m in manifests]
    if len(set(anchors)) != len(anchors):
        raise ValueError('Training anchors must be distinct')
    if val_manifest is None and sorted(m['anchor'] for m in manifests) != sorted(FINAL_TRAIN_ANCHORS):
        raise ValueError(f"A final fit (no validation) trains on {', '.join(FINAL_TRAIN_ANCHORS)}")
    if val_manifest is not None and any(a+timedelta(days=7) > date.fromisoformat(val_manifest['anchor']) for a in anchors):
        raise ValueError('Training target periods must finish before validation anchor')
    everything = manifests+([val_manifest] if val_manifest is not None else [])
    if any(m['features'] != everything[0]['features'] or m['database'] != everything[0]['database'] for m in everything):
        raise ValueError('Collections must share feature contract and database identity')
    paths = train_paths+([validation_path] if val_manifest is not None else [])
    agent, blocks = read_sidecars(Path(sidecars).resolve(), paths, everything, registered, deadline)
    columns = agent['columns']
    output = kaggle.new_output(output)
    report = dict(format=FIT_FORMAT, status='running', fit_count=0, arm='MA', seed=seed,
                  selection='One fixed-tree CPU fit of the locked M23 recipe plus every frozen agent column; '
                            'no eval_set, early stopping, parameter search or column selection',
                  lock=dict(path='configs/datasets/hm-auto-holdout-lock.json', sha256=kaggle.LOCK_SHA256),
                  training_user_limit=recipe['train_users'], negative_sample=recipe['negative_sample'],
                  sampling_seed=recipe['sampling_seed'], **registered['fields'],
                  prereg=dict(sha256=registered['sha256'], deviations_sha256=registered['deviations_sha256']))
    con = timer = None
    try:
        report['resources'] = dict(experiment.resource_preflight(output), threads=threads, catboost_thread_count=threads)
        import numpy as np
        from catboost import CatBoostClassifier
        numeric, categorical = experiment.choose_features(everything[0], feature_names=recipe['numeric']+recipe['categorical'])
        if (numeric, categorical) != (recipe['numeric'], recipe['categorical']):
            raise ValueError('Locked ordered feature vector differs from collection kinds')
        names = numeric+categorical
        model_numeric = numeric+columns
        report['features'] = dict(numeric=model_numeric, categorical=categorical, contract_digest=everything[0]['features']['digest'])
        report['database'] = everything[0]['database']
        report['inputs'] = [dict(role='train' if i < len(train_paths) else 'validation', anchor=m['anchor'],
                                 manifest_sha256=experiment.sha256_file(p/'manifest.json', deadline),
                                 qcy_identity=m['qcy_identity'], candidate_identity=m['candidate_identity'])
                            for i, (p, m) in enumerate(zip(paths, everything))]
        report['runtime'] = experiment.runtime_identity()
        report['code'] = code
        report['hyperparameters'] = parameters
        report['gpu_reference_hyperparameters'] = recipe['gpu_hyperparameters']
        report['agent'] = agent
        report['fit_identity'] = experiment.canonical_digest(dict(
            inputs=report['inputs'], features=report['features'], hyperparameters=parameters,
            train_users=recipe['train_users'], negative_sample=recipe['negative_sample'],
            sampling_seed=recipe['sampling_seed'], code=code, runtime=report['runtime'], agent=agent))
        con = kaggle.memory_connection(output, threads)
        timer = deadline.interrupt_sql(con)
        training = []
        report['training_populations'] = []
        for path, manifest in zip(train_paths, manifests):
            deadline.check()
            frame, _, summary = experiment.load_part(con, path, manifest, names, recipe['train_users'], recipe['negative_sample'])
            block = agent_block(sidecar_rows(con, frame, blocks[manifest['anchor']], columns), columns)
            numbers, cats = experiment.model_arrays(frame, numeric, categorical)
            numbers = np.ascontiguousarray(np.hstack([numbers, block]))
            training.append((numbers, cats, frame['label'].to_numpy(dtype=np.int8), frame['fit_weight'].to_numpy(dtype=np.float64)))
            report['training_populations'].append(summary)
            del frame, block
        numbers = np.concatenate([p[0] for p in training])
        cats = np.concatenate([p[1] for p in training])
        labels = np.concatenate([p[2] for p in training])
        weights = np.concatenate([p[3] for p in training])
        del training
        if len(np.unique(labels)) != 2:
            raise ValueError('Training needs both naturally retrieved label classes')
        deadline.check()
        pool = experiment.model_pool(numbers, cats, model_numeric, categorical, labels, weights)

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
        if list(model.feature_names_) != model_numeric+categorical:
            raise RuntimeError('Fitted feature vector differs from M23 plus the agent columns')
        report['actual_trees'] = model.tree_count_
        resolved = model.get_all_params()
        report['resolved_checks'] = {key: resolved.get(key) for key in kaggle.CHECKED_PARAMETERS}
        if not all(kaggle.same_value(resolved.get(key), parameters[key]) for key in kaggle.CHECKED_PARAMETERS):
            raise RuntimeError('Resolved CPU parameters differ from the locked recipe')
        model.save_model(str(output/'model.cbm'))
        kaggle.atomic_json(output/'params.json', resolved)
        del pool, numbers, cats, labels, weights
        files = ['model.cbm', 'params.json']
        if val_manifest is not None:
            frame, targets, summary = experiment.load_part(con, validation_path, val_manifest, names, None, None)
            block = agent_block(sidecar_rows(con, frame, blocks[val_manifest['anchor']], columns), columns)
            numbers, cats = experiment.model_arrays(frame, numeric, categorical)
            numbers = np.ascontiguousarray(np.hstack([numbers, block]))
            del block
            validation = pilot.Collection(numbers, cats, frame['label'].to_numpy(), frame['query_weight'].to_numpy(),
                                          frame['customer_id'].to_numpy(), frame['article_id'].to_numpy(), targets, summary)
            deadline.check()
            scores = model.predict_proba(experiment.model_pool(numbers, cats, model_numeric, categorical),
                                         thread_count=threads)[:, 1]
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
        error = kaggle.failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
        kaggle.atomic_json(output/'report.json', report)
    return report


def load_agent_fit(path, deadline):
    """A completed MA fit with its byte-pinned model; vector = locked M23 then the agent columns."""
    from catboost import CatBoostClassifier
    path = Path(path).resolve()
    report = kaggle.read_json(path/'report.json')
    if report.get('format') != FIT_FORMAT or report.get('status') != 'completed' or report.get('arm') != 'MA':
        raise ValueError('Completed hm_agent MA fit report required')
    model_sha = experiment.sha256_file(path/'model.cbm', deadline)
    if model_sha != report['files']['model.cbm']:
        raise ValueError('Model bytes differ from the fit report')
    model = CatBoostClassifier()
    model.load_model(str(path/'model.cbm'))
    numeric, categorical = report['features']['numeric'], report['features']['categorical']
    agent = report['agent']
    columns = list(agent['columns'])
    base = numeric[:len(numeric)-len(columns)]
    recipe = kaggle.locked_recipe('M', report['seed'])
    if (numeric[len(base):] != columns or base != recipe['numeric'] or categorical != recipe['categorical'] or
            list(model.feature_names_) != numeric+categorical or model.tree_count_ != report['hyperparameters']['iterations']):
        raise ValueError('Saved model differs from M23 plus its agent columns or from its tree count')
    name = f"MA{report['seed']}"
    identity = dict(name=name, arm='MA', seed=report['seed'],
                    report_sha256=experiment.sha256_file(path/'report.json', deadline), model_sha256=model_sha,
                    numeric=numeric, categorical=categorical, contract_digest=report['features']['contract_digest'],
                    database=report['database'], code=report['code'],
                    anchors=dict(train=sorted(i['anchor'] for i in report['inputs'] if i['role'] == 'train'),
                                 validation=sorted(i['anchor'] for i in report['inputs'] if i['role'] == 'validation')),
                    **{k: report.get(k) for k in ('deviation', 'deviations_sha256', 'deviations_records',
                                                  'deviations_prefix_sha256')},
                    agent=dict(digest=agent['digest'], sha256=agent['sha256'], export_digest=agent['export_digest'],
                               sidecars=agent['sidecars']))
    return dict(name=name, model=model, numeric=numeric, categorical=categorical, base_numeric=base,
                columns=columns, identity=identity, hyperparameters=report['hyperparameters'])


def score_ma(database, export, agent_set, fits, control, output, chunk_users=15000, threads=4, wall_seconds=28800,
             deviations=None):
    """Score MA fits and the control M fit at 2020-09-23 with kaggle.score's chunks, resumably.

    Customers, chunks, candidates, features and top 12 come from hm_kaggle's own
    functions and SQL. Each chunk's keys go to the sandbox; article-level agent
    values are computed once per process (one cache for this call). plan.json and
    the receipts stay in hm_kaggle formats, so the unchanged ``hm_kaggle.py
    assemble`` reads them; receipts add the counts the gate reads. A proposal
    error fails the run; its chunk has no receipt and a resume recomputes it.

    Deviations: the plan records the deviation fields of its run, so a resume
    needs the same code and the same deviations file version (or none). A new
    record whose ``rebuilds`` include score or an earlier step means a new
    output, never a resume. A record that rebuilds only later steps leaves the
    run as it is: resume with the arguments it started with (without
    ``--deviations`` if it started without one); the gate accepts it, since its
    stale-step rule does not reach score.
    """
    cutoff = kaggle.SCORE_ANCHOR
    if (type(chunk_users) is not int or not 1 <= chunk_users <= kaggle.MAX_CHUNK_USERS or
            type(threads) is not int or threads < 1):
        raise ValueError(f'Chunk size must be an integer in 1..{kaggle.MAX_CHUNK_USERS}; threads a positive integer')
    deadline = experiment.Deadline(wall_seconds)
    code = code_identity(deadline)
    deviated = current_deviation(deviations, 'score', deadline)
    import numpy as np
    from scripts.hm_feature_engine import build_features, feature_manifest
    reference = kaggle.load_fit(control, deadline)
    if reference['identity']['arm'] != 'M':
        raise ValueError('The control must be a locked M23 fit of hm_kaggle')
    agents = [load_agent_fit(path, deadline) for path in fits]
    models = [reference]+agents
    names = [m['name'] for m in models]
    if not agents or len(set(names)) != len(names):
        raise ValueError('Distinct MA fits and one control fit required')
    feature_digest = feature_manifest()['digest']
    source, db_identity, sources = database_identity(database, deadline)
    for m in models:
        if m['identity']['database'] != db_identity or m['identity']['contract_digest'] != feature_digest:
            raise ValueError('Fits must come from collections of this database and feature engine')
    export_path, exported = read_full_export(export, db_identity, sources)
    set_path, agent, ids = read_set(agent_set, deadline)
    columns = agent['columns']
    expected = dict(digest=agent['digest'], sha256=agent['sha256'], export_digest=exported['digest'])
    control_hyper = kaggle.read_json(Path(control).resolve()/'report.json')['hyperparameters']
    sidecars = {}
    for m in agents:
        if m['identity']['anchors'] != dict(train=sorted(FINAL_TRAIN_ANCHORS), validation=[]):
            raise ValueError(f"{m['name']} is not a final fit: train {', '.join(FINAL_TRAIN_ANCHORS)}, no validation")
        if ({k: v for k, v in m['identity']['agent'].items() if k != 'sidecars'} != expected or m['columns'] != columns or
                m['base_numeric'] != reference['numeric'] or m['categorical'] != reference['categorical']):
            raise ValueError('MA fits must be M23 of the control plus this agent set and export')
        if ({k: v for k, v in m['hyperparameters'].items() if k != 'random_seed'} !=
                {k: v for k, v in control_hyper.items() if k != 'random_seed'}):
            raise ValueError('MA fits must have the hyperparameters of the control, except random_seed')
        for anchor, sha in m['identity']['agent']['sidecars'].items():
            if sidecars.setdefault(anchor, sha) != sha:
                raise ValueError(f'MA fits used different sidecars at {anchor}')
    output = kaggle.private_path(output)
    resume = output.exists()
    if resume and not (output/'plan.json').is_file():
        raise ValueError('Existing output is not a resumable score run')
    if not resume:
        output.mkdir(parents=True, exist_ok=False)
    lock = kaggle.hold_lock(output/'score.lock')
    report = dict(format=SCORE_FORMAT, status='running', anchor=cutoff.isoformat(), policy=kaggle.POLICY,
                  chunk_users=chunk_users, threads=threads, resumed=resume, **deviated,
                  started_at_utc=kaggle.utc_now())
    con = timer = None
    accepted = not resume
    spill = output/f'duckdb-temp-{os.getpid()}'
    try:
        report['resources'] = experiment.resource_preflight(output)
        con = kaggle.database_connection(source, spill, threads)
        timer = deadline.interrupt_sql(con)
        if con.execute('SELECT max(t_dat) FROM transactions').fetchone()[0] != cutoff-timedelta(days=1):
            raise ValueError('Scoring needs transactions ending exactly the day before the anchor')
        kaggle.create_item_ranks(con, cutoff)
        # Verbatim the hm_kaggle score population and chunking.
        con.execute('''CREATE TEMP TABLE hm_k_users AS SELECT customer_id,user_rank,(user_rank-1)//? AS chunk FROM(
            SELECT customer_id,row_number() OVER(ORDER BY sha256(customer_id || ':' || ?),customer_id) user_rank
            FROM (SELECT DISTINCT customer_id FROM hm_k_history))''', [chunk_users, str(kaggle.SEED)])
        users = con.execute('SELECT count(*) FROM hm_k_users').fetchone()[0]
        if not users:
            raise ValueError('No customer has history before the anchor')
        chunks = math.ceil(users/chunk_users)
        plan = dict(format=kaggle.PLAN_FORMAT, anchor=cutoff.isoformat(), policy=kaggle.POLICY, history='[anchor-90d,anchor)',
                    order='sha256(customer_id || ":2026"), customer_id', chunk_users=chunk_users, threads=threads,
                    users=users, chunks=chunks,
                    users_digest=kaggle.ordered_digest(con, 'SELECT customer_id FROM hm_k_users ORDER BY user_rank'),
                    items_digest=kaggle.ordered_digest(con, 'SELECT article_id,buyers7,global_rank FROM hm_k_items ORDER BY global_rank'),
                    database=db_identity, sources=sources, feature_digest=feature_digest,
                    models=[m['identity'] for m in models],
                    code=code, **deviated,
                    runtime={k: v for k, v in experiment.runtime_identity().items() if k in ('python', 'packages')},
                    agent=dict(digest=agent['digest'], sha256=agent['sha256'], export_digest=exported['digest'], columns=columns))
        plan_path = output/'plan.json'
        if resume and kaggle.read_json(plan_path) != plan:
            raise ValueError('Existing score plan differs; resume needs identical inputs, chunking and threads')
        accepted = True
        if not resume:
            kaggle.atomic_json(plan_path, plan)
        plan_sha256 = experiment.sha256_file(plan_path)
        report.update(plan_sha256=plan_sha256, users=users, chunks=chunks, computed=0, skipped=0)
        article_cache = {}
        for chunk in range(chunks):
            deadline.check()
            receipt_path = output/f'chunk-{chunk:04d}.json'
            if receipt_path.exists():
                kaggle.check_chunk(output, kaggle.read_json(receipt_path), plan_sha256, chunk, names)
                report['skipped'] += 1
                print(json.dumps(dict(event='skip', chunk=chunk, chunks=chunks)), file=sys.stderr, flush=True)
                continue
            began = time.monotonic()
            con.execute('CREATE OR REPLACE TEMP TABLE hm_k_query AS SELECT customer_id FROM hm_k_users WHERE chunk=?', [chunk])
            size = con.execute('SELECT count(*) FROM hm_k_query').fetchone()[0]
            kaggle.create_chunk_candidates(con, 'hm_k_query', size)
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
            deadline.check()
            keys = frame[KEYS]
            agent_began = time.monotonic()
            values, info = sandbox.agent_columns(export_path, cutoff.isoformat(), keys, set_path, threads=threads,
                                                 cache=article_cache, deadline=deadline)
            agent_seconds = round(time.monotonic()-agent_began, 3)
            block = agent_block(align_block(keys, values, columns), columns)
            del values, keys
            non_null = np.isfinite(block).sum(axis=0)
            files, scored = {}, {}
            for m in models:
                deadline.check()
                if m is reference:
                    numbers, cats = experiment.model_arrays(frame, m['numeric'], m['categorical'])
                else:
                    numbers, cats = experiment.model_arrays(frame, m['base_numeric'], m['categorical'])
                    numbers = np.ascontiguousarray(np.hstack([numbers, block]))
                scores = m['model'].predict_proba(experiment.model_pool(numbers, cats, m['numeric'], m['categorical']),
                                                  thread_count=threads)[:, 1]
                del numbers, cats
                scored[m['name']] = dict(rows=int(len(scores)), nonfinite_scores=int((~np.isfinite(scores)).sum()))
                if scored[m['name']]['nonfinite_scores']:
                    # As kaggle.score: no receipt with a non-finite score; the count goes to the report.
                    report['nonfinite_scores'] = {m['name']: scored[m['name']]['nonfinite_scores']}
                    report['nonfinite_chunk'] = chunk
                    raise ValueError('Prediction scores must be finite')
                filename = f"top12-{m['name']}-{chunk:04d}.parquet"
                files[filename] = kaggle.write_top12(con, frame, scores, output/filename)
                if files[filename]['rows'] != 12*size:
                    raise ValueError('Every scored customer needs exactly 12 rows')
            receipt = dict(format=kaggle.CHUNK_FORMAT, plan_sha256=plan_sha256, chunk=chunk, users=size,
                           users_digest=kaggle.ordered_digest(con, 'SELECT customer_id FROM hm_k_query ORDER BY customer_id'),
                           candidate_rows=len(frame), files=files, threads=threads,
                           seconds=round(time.monotonic()-began, 3), agent_seconds=agent_seconds,
                           rss_bytes=kaggle.current_rss_bytes(), peak_rss_bytes=kaggle.peak_rss_bytes(),
                           finished_at_utc=kaggle.utc_now(), models=scored, agent_rows=int(len(block)),
                           agent_non_null={name: int(n) for name, n in zip(columns, non_null)},
                           agent_cached=list(info.get('cached', [])))
            del frame, built, block
            kaggle.atomic_json(receipt_path, receipt)
            report['computed'] += 1
            print(json.dumps(dict(event='chunk', chunk=chunk, chunks=chunks, users=size, seconds=receipt['seconds'],
                                  agent_seconds=agent_seconds, rss_bytes=receipt['rss_bytes'],
                                  peak_rss_bytes=receipt['peak_rss_bytes'])), file=sys.stderr, flush=True)
        receipts = [kaggle.read_json(output/f'chunk-{chunk:04d}.json') for chunk in range(chunks)]
        if sum(r['users'] for r in receipts) != users:
            raise ValueError('Chunk receipts do not cover every scored customer')
        report['receipts'] = {f'chunk-{c:04d}.json': experiment.sha256_file(output/f'chunk-{c:04d}.json') for c in range(chunks)}
        report['models'] = {name: dict(rows=sum(r['files'][f'top12-{name}-{c:04d}.parquet']['rows']
                                                for c, r in enumerate(receipts))) for name in names}
        deadline.check()
        report['status'] = 'completed'
    except Exception as exc:
        note_proposal(report, exc, ids)
        error = kaggle.failure(report, exc, deadline)
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
            report['peak_rss_bytes'] = kaggle.peak_rss_bytes()
            if accepted:
                # Latest invocation only; chunk receipts are the durable record.
                kaggle.atomic_json(output/'report.json', report)
        finally:
            kaggle.release_lock(lock)
    return report


def finished_scores(directory, model):
    """Plan, its SHA-256 and the checked top-12 files of ``model`` from a finished score run."""
    directory = Path(directory).resolve()
    plan_path = directory/'plan.json'
    plan = kaggle.read_json(plan_path)
    plan_sha256 = experiment.sha256_file(plan_path)
    names = [m['name'] for m in plan.get('models', [])]
    if plan.get('format') != kaggle.PLAN_FORMAT or model not in names:
        raise ValueError(f'Score plan in {directory.name} does not contain {model}')
    files = []
    for chunk in range(plan['chunks']):
        receipt = directory/f'chunk-{chunk:04d}.json'
        if not receipt.exists():
            raise ValueError(f'Scoring in {directory.name} is unfinished')
        kaggle.check_chunk(directory, kaggle.read_json(receipt), plan_sha256, chunk, names)
        files.append(str(directory/f'top12-{model}-{chunk:04d}.parquet'))
    identity = next(m for m in plan['models'] if m['name'] == model)
    return directory, plan, files, identity


def control(agent_scores, kaggle_scores, model='M2026', deviations=None):
    """The control's top 12 from score_ma against hm_kaggle score: exact (customer, rank, article), |dscore| <= 1e-9.

    Returns counters and OK/DIFF only; no IDs or scores; ``deviation`` as in sidecar.
    """
    import duckdb
    deviated = current_deviation(deviations, 'control')
    agent_dir, agent_plan, agent_files, agent_identity = finished_scores(agent_scores, model)
    _, kaggle_plan, kaggle_files, kaggle_identity = finished_scores(kaggle_scores, model)
    if 'agent' not in agent_plan or 'agent' in kaggle_plan:
        raise ValueError('Compare a score_ma run (agent scores) with an hm_kaggle score run (kaggle scores)')
    if agent_identity != kaggle_identity or agent_identity.get('arm') != 'M':
        raise ValueError('Both runs must score the same control M fit')
    for key in ('anchor', 'policy', 'users', 'users_digest', 'items_digest', 'database', 'sources', 'feature_digest'):
        if agent_plan.get(key) != kaggle_plan.get(key):
            raise ValueError(f'Score runs differ in {key}')
    with tempfile.TemporaryDirectory(prefix='hm-agent-control-', dir=agent_dir) as spill:
        con = duckdb.connect(':memory:')
        try:
            con.execute('SET threads=2')
            con.execute("SET memory_limit='2GB'")
            con.execute('SET autoinstall_known_extensions=false')
            con.execute('SET temp_directory=?', [str(Path(spill)/'duckdb-temp')])
            con.execute("SET max_temp_directory_size='8GB'")
            counts = {}
            for role, files in (('agent', agent_files), ('kaggle', kaggle_files)):
                con.execute(f'CREATE TEMP TABLE hm_c_{role} AS SELECT customer_id,"rank",article_id,score FROM read_parquet(?)', [files])
                rows, customers = con.execute(f'SELECT count(*),count(DISTINCT customer_id) FROM hm_c_{role}').fetchone()
                duplicates = con.execute(f'''SELECT count(*) FROM (SELECT customer_id,"rank" FROM hm_c_{role}
                    GROUP BY customer_id,"rank" HAVING count(*)>1)''').fetchone()[0]
                counts[role] = dict(rows=rows, customers=customers, duplicate_keys=duplicates)
            only_agent, only_kaggle, articles, scores, largest = con.execute('''SELECT
                count(*) FILTER(WHERE k.customer_id IS NULL),
                count(*) FILTER(WHERE a.customer_id IS NULL),
                count(*) FILTER(WHERE a.customer_id IS NOT NULL AND k.customer_id IS NOT NULL AND a.article_id<>k.article_id),
                count(*) FILTER(WHERE a.customer_id IS NOT NULL AND k.customer_id IS NOT NULL AND NOT abs(a.score-k.score)<=?),
                max(abs(a.score-k.score))
                FROM hm_c_agent a FULL OUTER JOIN hm_c_kaggle k ON a.customer_id=k.customer_id AND a."rank"=k."rank"''',
                                                                       [SCORE_TOLERANCE]).fetchone()
        finally:
            con.close()
    result = dict(model=model, agent=counts['agent'], kaggle=counts['kaggle'], only_agent=only_agent,
                  only_kaggle=only_kaggle, article_mismatches=articles, score_mismatches=scores,
                  max_abs_score_difference=largest, tolerance=SCORE_TOLERANCE, **deviated)
    ok = (counts['agent']['rows'] == counts['kaggle']['rows'] > 0 and
          not counts['agent']['duplicate_keys'] and not counts['kaggle']['duplicate_keys'] and
          not only_agent and not only_kaggle and not articles and not scores)
    result['result'] = 'OK' if ok else 'DIFF'
    return result


def leak_keys(con, collection, users):
    """Candidate keys (no labels) of the first ``users`` customers in users.parquet order, and those customers."""
    import pandas as pd
    frame = con.execute('SELECT customer_id,cohort_hash FROM read_parquet(?)', [str(collection/'users.parquet')]).fetchdf()
    selected = experiment.nested_users(frame, users)['customer_id'].tolist()
    con.register('_hm_leak_users', pd.DataFrame({'customer_id': selected}))
    try:
        keys = con.execute('''SELECT f.customer_id,f.article_id FROM read_parquet(?) f JOIN _hm_leak_users u USING(customer_id)
            ORDER BY f.customer_id,f.article_id''', [str(collection/'frame.parquet')]).fetchdf()
    finally:
        con.unregister('_hm_leak_users')
    return keys, selected


def leakcheck(database, export, agent_set, collections, output, users=2000, wall_seconds=7200, deviations=None):
    """Agent values on the full export against a ``--before A`` cut, and one batch against four.

    For each collection anchor A the first ``users`` customers' keys are
    computed on both exports; then on the full export as 4 consecutive batches.
    Cells compare as in the contract (two NULLs equal). Reports counts only.
    """
    import pandas as pd
    positive_int(users, 'Users')
    collections = [Path(p).resolve() for p in collections]
    if not collections or len(set(collections)) != len(collections):
        raise ValueError('Distinct collection paths required')
    deadline = experiment.Deadline(wall_seconds)
    code = code_identity(deadline)
    deviated = current_deviation(deviations, 'leakcheck', deadline)
    source, db_identity, sources = database_identity(database, deadline)
    export_path, exported = read_full_export(export, db_identity, sources)
    set_path, agent, ids = read_set(agent_set, deadline)
    columns = agent['columns']
    manifests = [kaggle.read_collection(p, deadline) for p in collections]
    anchors = [m['anchor'] for m in manifests]
    if len(set(anchors)) != len(anchors) or any(m['database'] != db_identity for m in manifests):
        raise ValueError('Collections need distinct anchors and this database')
    output = kaggle.new_output(output)
    report = dict(format=LEAKCHECK_FORMAT, status='running', users=users, batches=INVARIANCE_BATCHES,
                  tolerance='two NULLs equal, else |x-y| <= 1e-9*(1+|x|); NULL = missing, NaN or +-inf',
                  values='never recorded; counts only')
    con = timer = None
    try:
        report['resources'] = experiment.resource_preflight(output)
        report['database'] = db_identity
        report['export_digest'] = exported['digest']
        report['agent_set'] = agent
        report['code'] = code
        report.update(deviated)
        report['runtime'] = experiment.runtime_identity()
        report['anchors'] = {}
        con = kaggle.memory_connection(output, 2)
        timer = deadline.interrupt_sql(con)
        for path, manifest in zip(collections, manifests):
            anchor = manifest['anchor']
            keys, selected = leak_keys(con, path, users)
            deadline.check()
            # cache=None everywhere: a cached article value would hide a difference between exports.
            full = align_block(keys, sandbox.agent_columns(export_path, anchor, keys, set_path, cache=None,
                                                           deadline=deadline)[0], columns)
            with tempfile.TemporaryDirectory(prefix='cut-', dir=output) as scratch:
                cut_path = Path(scratch)/'export'
                cut = sandbox.export_history(source, cut_path, before=anchor)
                if cut.get('before') != anchor or cut.get('database') != db_identity:
                    raise ValueError('Cut export must be this database before the anchor')
                past = align_block(keys, sandbox.agent_columns(cut_path, anchor, keys, set_path, cache=None,
                                                               deadline=deadline)[0], columns)
            leak = cell_mismatches(full, past, columns)
            del past
            size = math.ceil(len(selected)/INVARIANCE_BATCHES)
            parts = []
            for start in range(0, len(selected), size):
                deadline.check()
                part = keys[keys['customer_id'].isin(set(selected[start:start+size]))]
                parts.append(sandbox.agent_columns(export_path, anchor, part, set_path, cache=None, deadline=deadline)[0])
            batched = align_block(keys, pd.concat(parts, ignore_index=True), columns)
            invariance = cell_mismatches(full, batched, columns)
            del parts, batched, full
            leaks, differences = sum(leak.values()), sum(invariance.values())
            report['anchors'][anchor] = dict(
                collection_manifest_sha256=experiment.sha256_file(path/'manifest.json', deadline),
                cut_export_digest=cut['digest'], customers=len(selected), rows=len(keys), columns=len(columns),
                invariance_batches=math.ceil(len(selected)/size), leak_mismatches=leak, invariance_mismatches=invariance,
                result='OK' if leaks == differences == 0 else 'LEAK')
        report['result'] = 'OK' if all(a['result'] == 'OK' for a in report['anchors'].values()) else 'LEAK'
        deadline.check()
        report['status'] = 'completed'
        report['finished_at_utc'] = kaggle.utc_now()
    except Exception as exc:
        note_proposal(report, exc, ids)
        error = kaggle.failure(report, exc, deadline)
        if error is not exc:
            raise error from exc
        raise
    finally:
        if timer:
            timer.cancel()
        if con:
            con.close()
        report['elapsed_seconds'] = round(time.monotonic()-deadline.started, 3)
        kaggle.atomic_json(output/'report.json', report)
    return report


def contrast_fit(path, agent):
    """A completed port fit with validation and its pinned query-metrics.parquet."""
    path = Path(path).resolve()
    report = kaggle.read_json(path/'report.json')
    expected = (FIT_FORMAT, 'MA') if agent else (kaggle.FIT_FORMAT, 'M')
    if ((report.get('format'), report.get('arm')) != expected or report.get('status') != 'completed' or
            'validation_metrics' not in report):
        raise ValueError(f'Completed {expected[1]} fit with validation required')
    metrics = experiment.sha256_file(path/'query-metrics.parquet')
    if metrics != report['files']['query-metrics.parquet']:
        raise ValueError('query-metrics.parquet differs from its fit report')
    return dict(path=path, report=report, name=f"{report['arm']}{report['seed']}", seed=report['seed'],
                report_sha256=experiment.sha256_file(path/'report.json'), query_metrics_sha256=metrics)


def contrast(reference, alternative, prereg, output, deviations=None):
    """Descriptive dev contrast MA - M on the shared validation week.

    Per user, ap12 is averaged over each arm's seeds; hm_result_audit.paired_bootstrap
    gives the interval. Also the MAP of every fit and MA - M per seed, unrounded.
    The submission gate is the separate ``gate`` command.
    """
    import duckdb
    from scripts import hm_result_audit
    from scripts.hm_feature_engine import CATEGORICAL_FEATURES, PILOT_NUMERIC_FEATURES
    if Path(hm_result_audit.__file__).resolve() != (ROOT/'scripts'/AUDIT_MODULE).resolve():
        raise ImportError(f'{AUDIT_MODULE} was imported from outside this checkout')
    refs = [contrast_fit(p, False) for p in reference]
    alts = [contrast_fit(p, True) for p in alternative]
    fits = refs+alts
    if not refs or not alts or len({f['path'] for f in fits}) != len(fits):
        raise ValueError('Distinct reference and alternative fits required')
    seeds = [f['seed'] for f in refs], [f['seed'] for f in alts]
    if len(set(seeds[0])) != len(seeds[0]) or sorted(seeds[0]) != sorted(seeds[1]):
        raise ValueError('Each arm needs the same distinct seeds')
    code = code_identity()
    registered = read_prereg(prereg, deviations, code)
    record = registered['record']
    output = kaggle.private_path(output)
    if output.exists():
        raise FileExistsError('Contrast output must be new')
    base = refs[0]['report']
    hyper = {k: v for k, v in base['hyperparameters'].items() if k != 'random_seed'}
    for f in fits:
        r = f['report']
        if (r['inputs'] != base['inputs'] or r['training_populations'] != base['training_populations'] or
                r['validation_population'] != base['validation_population'] or r['database'] != base['database'] or
                r['features']['contract_digest'] != base['features']['contract_digest'] or
                {k: v for k, v in r['hyperparameters'].items() if k != 'random_seed'} != hyper):
            raise ValueError(f"{f['name']} is not paired: inputs, populations, database and recipe must be equal")
    validation = [i for i in base['inputs'] if i['role'] == 'validation']
    if len(validation) != 1:
        raise ValueError('Exactly one validation collection required')
    numeric, categorical = list(PILOT_NUMERIC_FEATURES), list(CATEGORICAL_FEATURES)
    agent = alts[0]['report']['agent']
    for f in refs:
        r = f['report']
        if (r['features']['numeric'], r['features']['categorical']) != (numeric, categorical):
            raise ValueError('Reference fits must be locked M23')
        if any(record['code'].get(name) != value for name, value in r['code'].items()):
            raise ValueError(f"{f['name']} was fitted by code other than the preregistered")
    for f in alts:
        r = f['report']
        if (r['agent'] != agent or r['features']['numeric'] != numeric+agent['columns'] or
                r['features']['categorical'] != categorical):
            raise ValueError('Alternative fits must be M23 plus one agent set')
        if (r['agent']['sha256'] != record['agent_set']['sha256'] or r['agent']['export_digest'] != record['export_digest'] or
                r['code'] not in registered['codes']):
            raise ValueError(f"{f['name']} differs from the preregistered agent set or export, or its code is not registered")
        problem = deviation_problem(r, registered['entries'])
        if problem:
            raise ValueError(f"{f['name']}: {problem}")
        required = stale_deviation(r.get('deviation'), 'port', registered['entries'])
        if required:
            raise ValueError(f"{f['name']} is stale: deviation {required} rebuilds port fits")
    required = stale_deviation(registered['deviation'], 'contrast', registered['entries'])
    if required:
        raise ValueError(f'Deviation {required} rebuilds the contrast; the current code must be its code')
    con = duckdb.connect(':memory:')
    try:
        con.execute('SET threads=2')
        values = {f['name']: {u: (t, ap) for u, t, ap in con.execute(
            'SELECT customer_id,targets,ap12 FROM read_parquet(?) ORDER BY customer_id',
            [str(f['path']/'query-metrics.parquet')]).fetchall()} for f in fits}
    finally:
        con.close()
    first = values[fits[0]['name']]
    if any({u: t for u, (t, _) in values[f['name']].items()} != {u: t for u, (t, _) in first.items()} for f in fits):
        raise ValueError('Fits must share validation users and target counts')
    positive = [u for u, (t, _) in first.items() if t > 0]
    if not positive:
        raise ValueError('Validation week has no positive users')
    maps = {}
    for f in fits:
        computed = math.fsum(values[f['name']][u][1] for u in positive)/len(positive)
        reported = f['report']['validation_metrics']['map_at_12_conditional']
        if abs(computed-reported) > hm_result_audit.TOLERANCE:
            raise ValueError(f"{f['name']} query metrics disagree with its reported MAP")
        maps[f['name']] = reported

    def arm(group):
        return {u: dict(targets=t, ap12=math.fsum(values[f['name']][u][1] for f in group)/len(group))
                for u, (t, _) in first.items()}
    by_arm = dict(reference=arm(refs), alternative=arm(alts))
    bootstrap = hm_result_audit.paired_bootstrap(by_arm['reference'], by_arm['alternative'],
                                                 draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED)
    by_seed = {f['seed']: f['name'] for f in refs}
    result = dict(
        format=CONTRAST_FORMAT, status='completed',
        role='Descriptive dev contrast; the 95% interval is too wide to resolve a +2% effect',
        prereg=dict(sha256=registered['sha256'], deviations_sha256=registered['deviations_sha256']),
        **registered['fields'], validation=validation[0],
        reference=[{k: f[k] for k in ('name', 'seed', 'report_sha256', 'query_metrics_sha256')} for f in refs],
        alternative=[{k: f[k] for k in ('name', 'seed', 'report_sha256', 'query_metrics_sha256')} for f in alts],
        positive_queries=len(positive), map_by_fit=maps,
        mean_map={name: math.fsum(v[u]['ap12'] for u in positive)/len(positive) for name, v in by_arm.items()},
        delta_by_seed={str(f['seed']): maps[f['name']]-maps[by_seed[f['seed']]] for f in alts},
        bootstrap=bootstrap, code=code, created_at_utc=kaggle.utc_now())
    output.parent.mkdir(parents=True, exist_ok=True)
    kaggle.atomic_json(output, result)
    return result


def score_receipts(directory):
    """Plan and checked chunk receipts of a finished score_ma run."""
    directory = Path(directory).resolve()
    plan_path = directory/'plan.json'
    plan = kaggle.read_json(plan_path)
    if plan.get('format') != kaggle.PLAN_FORMAT or not isinstance(plan.get('agent'), dict):
        raise ValueError(f'{plan_path} is not a score_ma plan')
    plan_sha256 = experiment.sha256_file(plan_path)
    names = [m['name'] for m in plan['models']]
    receipts = []
    for chunk in range(plan['chunks']):
        path = directory/f'chunk-{chunk:04d}.json'
        if not path.exists():
            raise ValueError(f'Scoring in {directory} is unfinished')
        receipts.append(kaggle.read_json(path))
        kaggle.check_chunk(directory, receipts[-1], plan_sha256, chunk, names)
    return directory, plan, receipts


def artifact(path, step, record, agent, code):
    """One artifact the gate binds: its set, export, code and deviation fields."""
    return dict(path=str(path), step=step, sha256=agent['sha256'], export_digest=agent['export_digest'], code=code,
                **{k: record.get(k) for k in ('deviation', 'deviations_sha256', 'deviations_records',
                                              'deviations_prefix_sha256')})


def bound_sidecars(sidecars, agent_scores, port_fits):
    """{anchor: (manifest path, manifest)} of the sidecars the port and final MA fits used, and the problems.

    Every port fit and every MA model of the score plan names its sidecars by
    manifest SHA-256. One sidecar per anchor, the anchors exactly
    SIDECAR_ANCHORS, each present under ``sidecars`` with that SHA-256.
    """
    root = Path(sidecars).resolve()
    plan_path = Path(agent_scores).resolve()/'plan.json'
    plan = kaggle.read_json(plan_path)
    sources = [(f"{plan_path} models[{m['name']}]", m['agent'].get('sidecars')) for m in plan['models']
               if m.get('arm') == 'MA']
    for fit in port_fits:
        path = Path(fit).resolve()/'report.json'
        sources.append((str(path), kaggle.read_json(path)['agent'].get('sidecars')))
    used, problems, found = {}, [], {}
    for where, mapping in sources:
        if not isinstance(mapping, dict) or not mapping:
            problems.append(f'{where}: names no sidecars')
            continue
        for anchor, sha in mapping.items():
            used.setdefault(anchor, set()).add(sha)
    for anchor in sorted(used):
        path = root/anchor/'manifest.json'
        if len(used[anchor]) != 1:
            problems.append(f'{anchor}: the fits used different sidecars')
        elif not path.is_file() or experiment.sha256_file(path) != next(iter(used[anchor])):
            problems.append(f'{path}: not the sidecar the fits used')
        else:
            found[anchor] = (path, kaggle.read_json(path))
    if sorted(used) != sorted(SIDECAR_ANCHORS):
        problems.append(f"the fits used sidecars of {', '.join(sorted(used))}, not {', '.join(SIDECAR_ANCHORS)}")
    return found, problems


def gate_artifacts(leakcheck, sidecars, agent_scores, port_fits):
    """Every artifact the gate binds to the prereg, and the sidecar binding problems.

    Final MA fits are reached through the score plan: their identity there
    carries the code and deviation fields of their report.json. Sidecars are
    those the fits used (bound_sidecars), not whatever lies under ``sidecars``.
    """
    found = []
    path = Path(leakcheck).resolve()/'report.json'
    report = kaggle.read_json(path)
    found.append(artifact(path, 'leakcheck', report, report['agent_set'] | dict(export_digest=report['export_digest']),
                          report['code']))
    bound, problems = bound_sidecars(sidecars, agent_scores, port_fits)
    for anchor, (path, side) in bound.items():
        found.append(artifact(path, 'sidecar', side, side['agent_set'] | dict(export_digest=side['export_digest']),
                              side['code']))
    path = Path(agent_scores).resolve()/'plan.json'
    plan = kaggle.read_json(path)
    found.append(artifact(path, 'score', plan, plan['agent'], plan['code']))
    for identity in plan['models']:
        if identity.get('arm') == 'MA':
            found.append(artifact(f"{path} models[{identity['name']}]", 'final', identity, identity['agent'],
                                  identity.get('code')))
    for fit in port_fits:
        path = Path(fit).resolve()/'report.json'
        report = kaggle.read_json(path)
        if report.get('format') != FIT_FORMAT:
            raise ValueError(f'{path} is not an hm_agent MA fit report')
        found.append(artifact(path, 'port', report, report['agent'], report['code']))
    return found, problems


def parity_passes(share, shares):
    """Non-NULL share at scoring against the sidecar shares: both positive, within [0.5*min, 2*max]."""
    return bool(shares) and share > 0 and min(shares) > 0 and PARITY[0]*min(shares) <= share <= PARITY[1]*max(shares)


def gate_message(exc):
    if masked(exc):
        return 'Native library or agent query error'
    return str(exc)[:500]


def gate(prereg, leakcheck, sidecars, agent_scores, kaggle_scores, port_fits, output, model='M2026', deviations=None):
    """Mechanical submission gate of MA (section 4): every check with its counts and OK/FAIL.

    a prereg: current code is the prereg or the last deviation; the sidecars are
    exactly those the port and final fits used, one per SIDECAR_ANCHORS; every
    bound artifact names the preregistered set and export, carries registered
    code, deviation fields consistent with the supplied records, the code of the
    record it names (code_problem) and, for a step a deviation rebuilds or a
    later one, that deviation or a later one; every scored MA fit trained on
    FINAL_TRAIN_ANCHORS without validation (``final_anchors``);
    b leakcheck OK at LEAKCHECK_ANCHORS with LEAKCHECK_USERS, finished before
    every bound sidecar started (with no bound sidecar, a fails on the binding
    and b reports ``before_every_sidecar`` null); c ``control`` OK; d every MA score finite;
    e non-NULL parity of every agent column over the bound sidecars;
    f port MAP of every MA fit >= the popularity floor, with port fits for
    exactly the scored MA seeds on the port anchors.
    Only f touches labels: for it gate.json holds OK/FAIL, never a MAP. A check
    that cannot be evaluated is FAIL with its error. gate.json goes to a new
    directory ``output``.
    """
    import duckdb
    output = kaggle.new_output(output)
    checks, accepted = {}, {}

    def prereg_check():
        code = code_identity()
        registered = read_prereg(prereg, deviations, code)
        accepted.update(registered, code=code)
        record = registered['record']
        artifacts, binding = gate_artifacts(leakcheck, sidecars, agent_scores, port_fits)
        other = [a['path'] for a in artifacts
                 if (a['sha256'], a['export_digest']) != (record['agent_set']['sha256'], record['export_digest'])]
        unregistered = [a['path'] for a in artifacts if a['code'] not in registered['codes']]
        entries = registered['entries']
        problems = [dict(path=a['path'], problem=p) for a in artifacts for p in [deviation_problem(a, entries)] if p]
        mismatched = [dict(path=a['path'], problem=p) for a in artifacts
                      for p in [code_problem(a, record['code'], entries)] if p]
        # The gate computes control itself: its own deviation stands for the control step.
        bound = [(a['path'], a['step'], a['deviation']) for a in artifacts]
        bound.append(('gate (control)', 'control', registered['deviation']))
        stale = [dict(path=p, step=step, deviation=d, required=r)
                 for p, step, d in bound for r in [stale_deviation(d, step, entries)] if r]
        plan = kaggle.read_json(Path(agent_scores).resolve()/'plan.json')
        final = {m['name']: 'OK' if m.get('anchors') == dict(train=sorted(FINAL_TRAIN_ANCHORS), validation=[]) else 'FAIL'
                 for m in plan['models'] if m.get('arm') == 'MA'}
        ok = (not other and not unregistered and not stale and not problems and not mismatched and not binding and
              all(v == 'OK' for v in final.values()))
        return dict(result='OK' if ok else 'FAIL', deviation=registered['deviation'], artifacts=len(artifacts),
                    sidecar_binding=binding, other_set_or_export=other, unregistered_code=unregistered,
                    deviation_problems=problems, code_binding=mismatched, final_anchors=final,
                    rebuilt={step: entries[n]['id'] for step, n in required_deviations(entries).items()},
                    stale_deviation=stale)

    def leakcheck_check():
        report = kaggle.read_json(Path(leakcheck).resolve()/'report.json')
        anchors = report.get('anchors') or {}
        width = len(report.get('agent_set', {}).get('columns', []))
        finished = report.get('finished_at_utc')
        bound, _ = bound_sidecars(sidecars, agent_scores, port_fits)
        started = [side.get('started_at_utc') for _, side in bound.values()]
        # No bound sidecar is a binding failure of prereg, not a leakcheck one: null here.
        before = None if not started else (
            isinstance(finished, str) and all(isinstance(s, str) for s in started) and
            all(datetime.fromisoformat(finished) < datetime.fromisoformat(s) for s in started))
        ok = (report.get('format') == LEAKCHECK_FORMAT and report.get('status') == 'completed' and
              report.get('result') == 'OK' and sorted(anchors) == sorted(LEAKCHECK_ANCHORS) and
              report.get('users') == LEAKCHECK_USERS and width > 0 and
              all(a.get('result') == 'OK' and a.get('columns') == width for a in anchors.values()) and
              before is not False)
        return dict(result='OK' if ok else 'FAIL', status=report.get('status'), leakcheck=report.get('result'),
                    anchor_results={k: a.get('result') for k, a in sorted(anchors.items())}, users=report.get('users'),
                    columns=width, before_every_sidecar=before,
                    anchors=len(anchors), rows=sum(a.get('rows', 0) for a in anchors.values()),
                    leak_mismatches=sum(sum(a.get('leak_mismatches', {}).values()) for a in anchors.values()),
                    invariance_mismatches=sum(sum(a.get('invariance_mismatches', {}).values()) for a in anchors.values()))

    def control_check():
        result = control(agent_scores, kaggle_scores, model)
        return dict({k: v for k, v in result.items() if k != 'result' and not k.startswith('deviation')},
                    control=result['result'],
                    result='OK' if result['result'] == 'OK' else 'FAIL')

    def finite_check():
        directory, plan, receipts = score_receipts(agent_scores)
        names = [m['name'] for m in plan['models'] if m.get('arm') == 'MA']
        if not names:
            raise ValueError('The score run has no MA model')
        counts = {}
        with tempfile.TemporaryDirectory(prefix='hm-agent-gate-', dir=output) as spill:
            con = duckdb.connect(':memory:')
            try:
                con.execute('SET threads=2')
                con.execute('SET temp_directory=?', [str(Path(spill)/'duckdb-temp')])
                for name in names:
                    files = [str(directory/f'top12-{name}-{c:04d}.parquet') for c in range(plan['chunks'])]
                    top_rows, top_bad = con.execute('''SELECT count(*),
                        count(*) FILTER(WHERE score IS NULL OR NOT isfinite(score)) FROM read_parquet(?)''',
                                                    [files]).fetchone()
                    counts[name] = dict(rows=sum(r['models'][name]['rows'] for r in receipts),
                                        nonfinite_scores=sum(r['models'][name]['nonfinite_scores'] for r in receipts),
                                        top12_rows=top_rows, top12_nonfinite_scores=top_bad)
            finally:
                con.close()
        complete = all(r['models'][name]['rows'] == r['candidate_rows'] for r in receipts for name in names)
        ok = complete and all(c['nonfinite_scores'] == 0 and c['top12_nonfinite_scores'] == 0 and
                              c['top12_rows'] == 12*plan['users'] for c in counts.values())
        return dict(result='OK' if ok else 'FAIL', every_candidate_scored=complete, models=counts)

    def parity_check():
        _, plan, receipts = score_receipts(agent_scores)
        columns = plan['agent']['columns']
        bound, _ = bound_sidecars(sidecars, agent_scores, port_fits)
        if sorted(bound) != sorted(SIDECAR_ANCHORS):
            raise ValueError('Parity needs exactly the sidecars the fits used, one per chain anchor')
        sides = [side for _, side in bound.values()]
        if any(s.get('format') != SIDECAR_FORMAT or s.get('status') != 'completed' or
               s['agent_set']['columns'] != columns for s in sides):
            raise ValueError('Every sidecar must be completed, with the columns of the scored set')
        if any(r.get('agent_rows') != r['candidate_rows'] or list(r.get('agent_non_null', {})) != columns
               for r in receipts):
            raise ValueError('Every receipt must count agent_rows and agent_non_null of each column')
        rows = sum(r['agent_rows'] for r in receipts)
        per = {}
        for name in columns:
            shares = [s['non_null'][name]/s['keys']['rows'] for s in sides]
            share = sum(r['agent_non_null'][name] for r in receipts)/rows
            passed = parity_passes(share, shares)
            per[name] = dict(score_share=share, sidecar_min=min(shares), sidecar_max=max(shares),
                             result='OK' if passed else 'FAIL')
        return dict(result='OK' if all(c['result'] == 'OK' for c in per.values()) else 'FAIL',
                    rule='score share > 0, every sidecar share > 0, score share in [0.5*min, 2*max] of the sidecar shares',
                    sidecars=[s['anchor'] for s in sides], score_rows=rows, columns=per)

    def popularity_check():
        paths = [Path(p).resolve() for p in port_fits]
        if not paths or len(set(paths)) != len(paths):
            raise ValueError('Distinct port MA fits required')
        plan = kaggle.read_json(Path(agent_scores).resolve()/'plan.json')
        scored = sorted(m['seed'] for m in plan['models'] if m.get('arm') == 'MA')
        verdicts, seeds, anchors = {}, [], {}
        for path in paths:
            fit = contrast_fit(path, True)
            inputs = fit['report']['inputs']
            train = sorted(i['anchor'] for i in inputs if i['role'] == 'train')
            validation = [i['anchor'] for i in inputs if i['role'] == 'validation']
            on_port = train == sorted(PORT_TRAIN_ANCHORS) and validation == [PORT_VALIDATION_ANCHOR]
            value = fit['report']['validation_metrics']['map_at_12_conditional']
            passed = on_port and type(value) in (int, float) and math.isfinite(value) and value >= POPULARITY_FLOOR
            verdicts[fit['name']] = 'OK' if passed else 'FAIL'
            anchors[fit['name']] = 'OK' if on_port else 'FAIL'
            seeds.append(fit['seed'])
        if len(verdicts) != len(paths):
            raise ValueError('Port MA fits must have distinct seeds')
        same_seeds = sorted(seeds) == scored
        return dict(result='OK' if same_seeds and all(v == 'OK' for v in verdicts.values()) else 'FAIL',
                    rule=f'port MAP@12 of every MA fit >= {POPULARITY_FLOOR} (popularity, docs/hm-pilot.md); '
                         'port fits for exactly the scored MA seeds, on the port anchors',
                    seeds='OK' if same_seeds else 'FAIL', anchors=anchors, fits=verdicts)

    for name, check in zip(GATE_CHECKS, (prereg_check, leakcheck_check, control_check, finite_check, parity_check,
                                         popularity_check)):
        try:
            checks[name] = check()
        except Exception as exc:
            checks[name] = dict(result='FAIL', error=dict(type=type(exc).__name__, message=gate_message(exc)))
    fields = accepted.get('fields') or deviation_fields(None, [], None)
    result = dict(format=GATE_FORMAT, status='completed', model=model,
                  prereg=dict(sha256=accepted.get('sha256'), deviations_sha256=accepted.get('deviations_sha256')),
                  **fields, checks=checks,
                  result='OK' if all(c['result'] == 'OK' for c in checks.values()) else 'FAIL',
                  code=accepted.get('code'), created_at_utc=kaggle.utc_now())
    kaggle.atomic_json(output/'gate.json', result)
    return result


def masked(exc):
    """Native messages can quote data rows; the agent sandbox may relay them in its errors."""
    if type(exc).__module__.split('.')[0].lstrip('_') in kaggle.NATIVE_ERRORS:
        return True
    return is_proposal_error(exc)


def main(argv=None):
    parser = kaggle.Parser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('sidecar', help='agent columns for every candidate key of one collection')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--export', type=Path, required=True)
    command.add_argument('--agent-set', type=Path, required=True)
    command.add_argument('--collection', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--deviations', type=Path)
    command.add_argument('--threads', type=int, default=4)
    command.add_argument('--wall-seconds', type=float, default=3600)
    command = sub.add_parser('fit', help='one locked CPU fit of M23 plus every agent column (MA)')
    command.add_argument('--seed', type=int, choices=(2026, 2027), required=True)
    command.add_argument('--train', type=Path, nargs='+', required=True)
    command.add_argument('--sidecars', type=Path, required=True)
    command.add_argument('--prereg', type=Path, required=True)
    command.add_argument('--deviations', type=Path)
    command.add_argument('--validation', type=Path)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--threads', type=int, default=8)
    command.add_argument('--wall-seconds', type=float, default=14400)
    command = sub.add_parser('score', help='resumable chunked top 12 at 2020-09-23 for MA fits and the control')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--export', type=Path, required=True)
    command.add_argument('--agent-set', type=Path, required=True)
    command.add_argument('--fits', type=Path, nargs='+', required=True)
    command.add_argument('--control', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--chunk-users', type=int, default=15000)
    command.add_argument('--deviations', type=Path,
                         help='deviations file; the plan records it, so a resume needs the same version or none. '
                              'A record that rebuilds score or an earlier step needs a new --output')
    command.add_argument('--threads', type=int, default=4)
    command.add_argument('--wall-seconds', type=float, default=28800)
    command = sub.add_parser('control', help='control top 12 of score against hm_kaggle score: OK or DIFF')
    command.add_argument('--agent-scores', type=Path, required=True)
    command.add_argument('--kaggle-scores', type=Path, required=True)
    command.add_argument('--model', default='M2026')
    command.add_argument('--deviations', type=Path)
    command = sub.add_parser('leakcheck', help='full export against a --before cut, and batch invariance: OK or LEAK')
    command.add_argument('--database', type=Path, required=True)
    command.add_argument('--export', type=Path, required=True)
    command.add_argument('--agent-set', type=Path, required=True)
    command.add_argument('--collections', type=Path, nargs='+', required=True)
    command.add_argument('--users', type=int, default=2000)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--deviations', type=Path)
    command.add_argument('--wall-seconds', type=float, default=7200)
    command = sub.add_parser('contrast', help='descriptive dev contrast MA - M on the port validation week')
    command.add_argument('--reference', type=Path, nargs='+', required=True)
    command.add_argument('--alternative', type=Path, nargs='+', required=True)
    command.add_argument('--prereg', type=Path, required=True)
    command.add_argument('--deviations', type=Path)
    command.add_argument('--output', type=Path, required=True)
    command = sub.add_parser('gate', help='mechanical submission gate of MA: OK or FAIL for every check')
    command.add_argument('--prereg', type=Path, required=True)
    command.add_argument('--deviations', type=Path)
    command.add_argument('--leakcheck', type=Path, required=True)
    command.add_argument('--sidecars', type=Path, required=True)
    command.add_argument('--agent-scores', type=Path, required=True)
    command.add_argument('--kaggle-scores', type=Path, required=True)
    command.add_argument('--port', type=Path, nargs='+', required=True)
    command.add_argument('--model', default='M2026')
    command.add_argument('--output', type=Path, required=True)
    try:
        args = parser.parse_args(argv)
    except kaggle.UsageError as exc:
        tokens = sys.argv[1:] if argv is None else list(argv)
        print(json.dumps(dict(status='failed', command=next((t for t in tokens if t in sub.choices), None),
                              error_type='UsageError', message=str(exc)[:500])))
        return 1
    code = 0
    try:
        if not kaggle.isolated():
            raise RuntimeError(f'{args.command} reads private data; run it as python -I scripts/hm_agent_kaggle.py')
        if args.command == 'sidecar':
            result = sidecar(args.database, args.export, args.agent_set, args.collection, args.output,
                             args.threads, args.wall_seconds, args.deviations)
            summary = dict(status=result['status'], anchor=result['anchor'], rows=result['keys']['rows'],
                           columns=len(result['agent_set']['columns']))
        elif args.command == 'fit':
            result = fit_ma(args.seed, args.train, args.sidecars, args.prereg, args.output, args.validation,
                            args.threads, args.wall_seconds, args.deviations)
            populations = result['training_populations']
            summary = dict(status=result['status'], model=f'MA{args.seed}', trees=result['actual_trees'],
                           columns=len(result['agent']['columns']), deviation=result['deviation'],
                           train_queries=sum(p['selected_queries'] for p in populations),
                           train_positive_rows=sum(p['positive_rows'] for p in populations))
            if 'validation_metrics' in result:
                metrics = result['validation_metrics']
                summary.update({key: metrics[key] for key in ('map_at_12_conditional', 'positive_queries',
                                                              'distinct_query_target_pairs', 'queries',
                                                              'oracle_map_at_12_conditional')})
        elif args.command == 'score':
            result = score_ma(args.database, args.export, args.agent_set, args.fits, args.control, args.output,
                              args.chunk_users, args.threads, args.wall_seconds, args.deviations)
            summary = dict(status=result['status'], users=result['users'], chunks=result['chunks'],
                           computed=result['computed'], skipped=result['skipped'])
        elif args.command == 'control':
            result = control(args.agent_scores, args.kaggle_scores, args.model, args.deviations)
            summary = dict(status='completed', **result)
            code = 0 if result['result'] == 'OK' else 1
        elif args.command == 'leakcheck':
            result = leakcheck(args.database, args.export, args.agent_set, args.collections, args.output,
                               args.users, args.wall_seconds, args.deviations)
            summary = dict(status=result['status'], result=result['result'], anchors={
                anchor: dict(rows=a['rows'], columns=a['columns'], leak_mismatches=sum(a['leak_mismatches'].values()),
                             invariance_mismatches=sum(a['invariance_mismatches'].values()), result=a['result'])
                for anchor, a in result['anchors'].items()})
            code = 0 if result['result'] == 'OK' else 1
        elif args.command == 'contrast':
            result = contrast(args.reference, args.alternative, args.prereg, args.output, args.deviations)
            summary = dict(status=result['status'], deviation=result['deviation'], map_by_fit=result['map_by_fit'],
                           delta_by_seed=result['delta_by_seed'], mean_delta=result['bootstrap']['mean_delta'],
                           percentile_95=result['bootstrap']['percentile_95'])
        else:
            result = gate(args.prereg, args.leakcheck, args.sidecars, args.agent_scores, args.kaggle_scores, args.port,
                          args.output, args.model, args.deviations)
            # OK/FAIL only: the popularity floor must never print a MAP.
            summary = dict(status=result['status'], result=result['result'], deviation=result['deviation'],
                           checks={name: check['result'] for name, check in result['checks'].items()})
            code = 0 if result['result'] == 'OK' else 1
        print(json.dumps(summary))
    except Exception as exc:
        message = str(exc)[:500]
        if masked(exc):
            message = 'Native library or agent query error; see the output manifest or report if one was written'
        line = dict(status='failed', command=args.command, error_type=type(exc).__name__, message=message)
        if is_proposal_error(exc):
            line['proposal'] = getattr(exc, 'hm_agent_proposal', None)
        print(json.dumps(line))
        return 1
    return code


if __name__ == '__main__':
    raise SystemExit(main())
