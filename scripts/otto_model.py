"""Model side of the OTTO port (docs/otto-design.md, §11 row ``otto_model.py``).

Commands (``.venv/bin/python -I scripts/otto_model.py <command> ...``; one JSON
line on stdout, exit 0/1, refusal without ``-I``):

``fit --series dev|holdout|final --arm B|BA|BApl --seed 2026|2027``
    Three CatBoost YetiRank models, one per type (§6), on the training fold of
    the series. ``fit --base-dev NAME --base PATH`` is the base development fit
    (arm B, dev, seed 2026, before prereg) with its F3 scores. The final series
    trains on the sessions of ``final-sessions`` and checks them.
``final-sessions [--name NAME]``
    After the committed result receipt otto-holdout.json: the training sessions
    of the final series (first N_t labelled F4 sessions per type, labels through
    ``read_sealed``) as ``final-training/<name>/sessions.json`` of
    otto-final-training-v1; otto_agent builds the F4 sidecar of those sessions.
``smoke [--base PATH]``
    Smoke calibration before prereg (§12): one orders fit of the BA shape on F2
    (base features plus 72 noise columns), the bootstrap type and the time.
``evaluate --series S --arm A --seed N``
    Top-20 per type on the evaluation population of the series in SCORE_BATCH
    batches, topped up from Pop (§6); metrics where the labels are open (F3).
    Pop lists are built from the collection frame by ``otto_data.pop`` inside
    the evaluation, so they belong to the scored collection.
``contrast``
    Dev contrast BA - B, BA - BApl, BApl - B on F3 (descriptive, §8, §10).
``gate --kind power --contrast PATH``
    Power gate (§8): population.json of the holdout collection.
``gate --kind 1 --stage 1|2 --leakcheck PATH ...`` and ``gate --kind 2 --stage 1|2``
    Gate 1 before ``holdout`` and gate 2 before any submission (§8).
``holdout-open --gate PATH --quote TEXT --quote-time ISO [--covers-stage2]``
    The open receipt ``otto-holdout-open.json``; ``--stage 2`` writes
    ``otto-holdout-open-2.json`` (§2.5).
``holdout [--stage 2]``
    Reads the holdout labels through ``read_sealed`` and writes the result
    receipt ``otto-holdout.json`` or ``otto-holdout-2.json`` (§10).
``score --arm B|BA --seed N``
    Final-series scoring of F5: ranked lists (20 aids per type) for
    ``otto_data.py assemble``, which builds and checks the Kaggle file. Nothing
    is submitted here.
``reading --private JSON``
    Kaggle comparison BA against B and the level (§10), descriptive.

Inputs owned elsewhere: collections, Pop lists and the Kaggle file come from
otto_data in the formats of otto_common; the BA frame of a collection (B
candidates and features plus the agent block ``ag_*``) comes from otto_agent
as ``artifacts/otto/sidecars/<collection>/<name>/`` (sidecar.json and parts),
the leakcheck reports as ``leakcheck/<name>/report.json`` and the frozen
columns from the committed set. Their readers live in otto_common
(``sidecar_parts``, ``read_leakcheck``, ``agent_columns``) and are called here
in one place each (``ba_frame``, ``leakcheck_record``, ``frozen_agent_columns``);
there is no command-line override of the BA frame.
A collection without a BA frame is "BA не выполнена" (§5.7): its BA and BApl
arms are absent, D and P are not computed and the holdout opens for B and Pop.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts import otto_common as oc  # noqa: E402
from scripts import otto_data as od  # noqa: E402
from scripts.otto_common import ContractError, require  # noqa: E402,F401

# =============================================================================== constants

FIT_FORMAT = 'otto-fit-v1'
EVAL_FORMAT = 'otto-eval-v1'
CONTRAST_FORMAT = 'otto-contrast-v1'
GATE_FORMAT = oc.GATE_FORMAT
RESULT_FORMAT = 'otto-holdout-result-v1'
READING_FORMAT = 'otto-kaggle-reading-v1'
SMOKE_FORMAT = 'otto-smoke-v1'
ASSEMBLE_FORMAT = 'otto-assemble-v1'           # receipt of otto_data.assemble (read by gate 2)

REPORT_FILE = 'report.json'
GATE_FILE = oc.GATE_FILE
RANKED_FILE = 'ranked.parquet'
POP_FILE = 'pop.parquet'
STARTED_FILE = 'started.json'
METRICS_FILE = 'metrics.parquet'
EVAL_DIR = 'eval'
MODEL_FILE = 'model-{type}.cbm'

# §6 recipe (decision 7); bootstrap_type comes from the smoke run through the prereg
RECIPE = oc.RECIPE
DEFAULT_BOOTSTRAP = 'Bayesian'
FALLBACK_BOOTSTRAP = 'Bernoulli'
PREDICTION_TYPE = 'RawFormulaVal'
NEGATIVE_SALT = '|2026'                        # constant for both seeds (§6)
PERMUTATION_ROOT = 20261022
PERMUTATION_RULE = ('training: numpy.random.default_rng([20261022, seed, k, 0, j]).permutation(n), k the training '
                    'fold, j 0/1/2 for clicks/carts/orders, n training rows of the type in (session, aid) order; '
                    'scoring: default_rng([20261022, seed, k, 1, b]).permutation(n_b), k the evaluation fold, per '
                    'SCORE_BATCH batch b of the evaluation population in sha256 order, rows of the batch in '
                    '(session, aid) order, one permutation for all three types; row i of the agent block takes the '
                    'values of row perm[i], base columns stay')
NEGATIVE_RULE = ("all positives and up to 30 negatives with the smallest sha256(CAST(CAST(session AS BIGINT) AS "
                 "VARCHAR) || '|' || CAST(CAST(aid AS BIGINT) AS VARCHAR) || '|' || t || '|2026') (lower-case hex), "
                 "ties by smaller aid")
AGENT_PREFIX = oc.AGENT_PREFIX
DUCKDB_THREADS = oc.DUCKDB_THREADS
DUCKDB_MEMORY = oc.DUCKDB_MEMORY
DUCKDB_MAX_TEMP = oc.DUCKDB_MAX_TEMP
BA_CHECK_CHUNK = 100_000           # sessions per pass of check_ba_frame (deviation d1; F5 has ~150 rows/session)
PARITY = (0.5, 2.0)
SMOKE_NOISE = 72
SMOKE_LIMIT_SECONDS = 40*60
SMOKE_REDUCED_N_T = 25_000
SMOKE_TYPE = 'orders'
GATE_KINDS = ('1', 'power', '2')
RESOLUTION_NOTE = 'эффекты меньше ≈0,003 holdout не разрешит'
BA_NOT_RUN = 'BA не выполнена'
KAGGLE_KEYS = tuple(f'{arm}{seed}' for seed in oc.SEEDS for arm in ('B', 'BA'))


# =============================================================================== small helpers

class ArgumentError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentError(message)


@contextlib.contextmanager
def quiet_stdout():
    """CatBoost and DuckDB messages go to stderr: stdout carries only the JSON line."""
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        os.dup2(2, 1)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)


def stamp():
    return _dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def rel(path):
    """Repository-relative POSIX path (absolute when outside the repository)."""
    path = Path(path).resolve()
    root = oc.ROOT.resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def from_rel(name):
    path = Path(name)
    return path if path.is_absolute() else oc.ROOT/path


sql_str = oc.sql_literal
sql_list = oc.sql_list


def normalized(value):
    """JSON round trip: tuples become lists, numpy scalars plain numbers."""
    return json.loads(json.dumps(value, default=_plain, allow_nan=False))


def _plain(value):
    import numpy as np
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f'Not JSON serialisable: {type(value).__name__}')


def ever_committed(path):
    """True when ``path`` appears in any commit of the repository."""
    name = Path(path).resolve().relative_to(oc.ROOT.resolve()).as_posix()
    out = subprocess.run(['git', '-C', str(oc.ROOT), 'log', '--all', '--format=%H', '--', name],
                         capture_output=True, text=True, check=False)
    return bool(out.stdout.strip())


def fresh_output(path):
    """A new output directory; an earlier run there that did not complete is moved aside first.

    Not completed: report.json with status 'failed', or no report.json at all (a run killed
    before its finally clause). A completed report refuses: every output is new.
    """
    path = Path(path)
    if path.exists():
        report = path/REPORT_FILE
        completed = report.is_file() and oc.read_json(report).get('status') != 'failed'
        require(not completed, f'{rel(path)} exists; every output is new')
        path.rename(path.with_name(f'{path.name}.failed-{stamp()}'))
    return oc.new_output(path)


def connect(ctx):
    import duckdb
    con = duckdb.connect()
    con.execute(f'SET threads={int(ctx.threads)}')
    con.execute(f"SET memory_limit={sql_str(ctx.memory)}")
    con.execute(f"SET temp_directory={sql_str(ctx.spill())}")
    con.execute(f"SET max_temp_directory_size={sql_str(DUCKDB_MAX_TEMP)}")
    return con


def type_code_sql(column='type'):
    """Type names or integer codes (TYPE_CODES) -> code 0/1/2; anything else NULL."""
    names = ', '.join(sql_str(t) for t in oc.TYPES)
    return (f'CASE WHEN CAST({column} AS VARCHAR) IN ({names}) '
            f'THEN list_position([{names}], CAST({column} AS VARCHAR)) - 1 '
            f'WHEN TRY_CAST(CAST({column} AS VARCHAR) AS INTEGER) BETWEEN 0 AND {len(oc.TYPES)-1} '
            f'THEN TRY_CAST(CAST({column} AS VARCHAR) AS INTEGER) END')


def type_name_sql(column='tc'):
    return 'CASE ' + ' '.join(f'WHEN {column} = {i} THEN {sql_str(t)}' for i, t in enumerate(oc.TYPES)) + ' END'


def array_digest(*arrays):
    import numpy as np
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(np.ascontiguousarray(np.asarray(array, dtype=np.int64)).tobytes())
    return digest.hexdigest()


def negative_key(session, aid, type_):
    """Python twin of the negative-sampling key of §6."""
    return hashlib.sha256(f'{int(session)}|{int(aid)}|{type_}{NEGATIVE_SALT}'.encode('utf-8')).hexdigest()


def negative_key_sql(type_, session='session', aid='aid'):
    """Negative key of §6; session and aid go through BIGINT first, whatever their stored integer type."""
    require(type_ in oc.TYPES, f'Unknown type {type_!r}')
    return (f"sha256(CAST(CAST({session} AS BIGINT) AS VARCHAR) || '|' || CAST(CAST({aid} AS BIGINT) AS VARCHAR) "
            f"|| '|' || {sql_str(type_)} || {sql_str(NEGATIVE_SALT)})")


def permutation(seed, k, phase, index, n):
    """BApl permutation (§6): default_rng([20261022, seed, k, phase, index]).permutation(n)."""
    import numpy as np
    return np.random.default_rng([PERMUTATION_ROOT, int(seed), int(k), int(phase), int(index)]).permutation(int(n))


def permute_block(matrix, columns, perm):
    """Row i of the columns ``columns`` takes the values of row perm[i]; other columns stay."""
    import numpy as np
    out = np.array(matrix, copy=True)
    if len(columns):
        out[:, columns] = matrix[np.asarray(perm)][:, columns]
    return out


# =============================================================================== context

class Context:
    """What a command runs under: base, prereg, code identity, recipe and resources.

    ``Context.contract()`` is the only constructor for preregistered work; tests
    build a Context directly with synthetic values.
    """

    def __init__(self, base, *, mode='contract', prereg=None, prereg_sha256=None, code=None,
                 bootstrap_type=DEFAULT_BOOTSTRAP, recipe_overrides=None, threads=DUCKDB_THREADS,
                 memory=DUCKDB_MEMORY, agent_columns=None, set_digest=None, n_t=oc.N_T,
                 negatives=oc.NEGATIVES, score_batch=oc.SCORE_BATCH, dev_bapl=True):
        require(mode in ('contract', 'base-dev', 'smoke'), f'Unknown mode {mode!r}')
        self.base = oc.check_base(base)
        self.features = oc.base_feature_names(base)
        self.mode = mode
        self.prereg = prereg
        self.prereg_sha256 = prereg_sha256
        self.code = code if code is not None else {}
        self.bootstrap_type = bootstrap_type
        self.recipe_overrides = dict(recipe_overrides or {})
        self.threads = int(threads)
        self.memory = memory
        self.agent_columns = list(agent_columns) if agent_columns is not None else None
        self.set_digest = set_digest
        self._ba = {}
        self._ba_run = {}
        self.n_t = int(n_t)
        self.negatives = int(negatives)
        self.score_batch = int(score_batch)
        self.dev_bapl = bool(dev_bapl)
        self._spill = None

    @classmethod
    def contract(cls):
        """Committed prereg (base, set and code checked by require_prereg) and its recorded rules.

        Prereg keys read here: ``recipe.bootstrap_type`` (required), ``N_t``,
        ``SCORE_BATCH``, ``dev_bapl``; the frozen agent columns and the set digest come
        from the committed set (``frozen_agent_columns``) and are required.
        """
        prereg = oc.require_prereg(check_code=True)
        recipe = prereg.get('recipe') or {}
        require(recipe.get('bootstrap_type'), 'Prereg records no recipe.bootstrap_type (smoke result)')
        agent_set = oc.receipt('set')
        return cls(oc.read_base(), mode='contract', prereg=prereg,
                   prereg_sha256=oc.sha256_file(oc.config_path('prereg')),
                   code=oc.code_identity(strict=True)['files'], bootstrap_type=recipe['bootstrap_type'],
                   agent_columns=frozen_agent_columns(prereg, agent_set), set_digest=agent_set['digest'],
                   n_t=prereg.get('N_t', oc.N_T), score_batch=prereg.get('SCORE_BATCH', oc.SCORE_BATCH),
                   dev_bapl=prereg.get('dev_bapl', True))

    @classmethod
    def before_prereg(cls, base, mode, bootstrap_type=DEFAULT_BOOTSTRAP):
        return cls(base, mode=mode, code=oc.code_identity(strict=False)['files'], bootstrap_type=bootstrap_type)

    def spill(self):
        if self._spill is None:
            self._spill = str(oc.spill_dir())
        return self._spill

    def close(self):
        if self._spill is not None:
            shutil.rmtree(self._spill, ignore_errors=True)
            self._spill = None

    def recipe(self, seed):
        recipe = dict(RECIPE, random_seed=int(seed), bootstrap_type=self.bootstrap_type)
        recipe.update(self.recipe_overrides)
        return recipe

    # ---- collections and frames
    def collection(self, k):
        """Collection directory of fold k (F2 train, F3 val, F4 holdout, F5 kaggle) after its manifest check."""
        role = oc.FOLD_ROLE[int(k)]
        path = oc.collection_dir(role)
        oc.read_collection(path, role=role, base=self.base)
        return path

    def frame_paths(self, collection, arm):
        """Parquet files of the arm frame: frame.parquet for B, the BA frame for BA and BApl."""
        collection = Path(collection)
        if arm == 'B':
            return [str(collection/oc.FRAME_FILE)]
        paths = ba_frame_paths(self, collection)
        require(paths, f'No BA frame for {collection.name}: {BA_NOT_RUN}')
        return paths

    def ba_run(self, train, eval_):
        """True when the BA frames cover the sessions a BA fit and evaluation of the series need.

        Training fold: the union of the training sessions (F2/F3 from the open labels, F4 from
        final-sessions); evaluation fold: the evaluation population. A missing frame or an
        incomplete coverage on either fold is "BA не выполнена" (§8), a result, not an error.
        """
        key = (int(train), int(eval_))
        if key not in self._ba_run:
            self._ba_run[key] = all(ba_covers(self, self.collection(k), sessions(self, k))
                                    for k, sessions in ((key[0], ba_training_sessions),
                                                        (key[1], ba_evaluation_sessions)))
        return self._ba_run[key]


# ---- formats owned by otto_agent: read by otto_common, called here in exactly one function each

def ba_frame(ctx, collection):
    """The BA frame of a collection after ``oc.sidecar_parts`` (None: BA не выполнена); cached per context.

    The sidecars must be built on the frozen set (``ctx.set_digest``; without it any sidecar refuses:
    no frozen set) and carry between the keys exactly the B columns otto_agent writes for this base
    (``od.with_sources(ctx.features)`` = ``od.b_columns(base)``: base features, then the source
    columns they lack) and exactly the frozen agent columns.
    """
    collection = Path(collection)
    if collection.name not in ctx._ba:
        if ctx.set_digest is None:
            root = oc.output_dir('sidecars', collection.name)
            present = root.exists() and any(not p.name.startswith('.') for p in root.iterdir())
            require(not present, f'{collection.name} has sidecars but the context has no frozen agent set '
                                 '(нет замороженного набора)')
            record = None
        else:
            record = oc.sidecar_parts(collection, ctx.set_digest)
        if record is not None:
            columns, agent = record['columns'], record['agent_columns']
            require(columns[2:len(columns)-len(agent)] == od.with_sources(ctx.features),
                    f'{collection.name}: sidecar B columns differ from the B columns of the base (od.b_columns)')
            if ctx.agent_columns is not None:
                require(agent == ctx.agent_columns,
                        f'{collection.name}: sidecar agent columns differ from the frozen set')
        ctx._ba[collection.name] = record
    return ctx._ba[collection.name]


def ba_frame_paths(ctx, collection):
    """Parquet parts of the BA frame of a collection, or [] when otto_agent wrote none (BA не выполнена)."""
    record = ba_frame(ctx, collection)
    return list(record['parts']) if record is not None else []


def ba_covers(ctx, collection, sessions):
    """True when the BA frame of the collection exists and holds every session of ``sessions()``.

    ``sessions`` is called only when the frame exists (no labels are read for a fold without sidecars);
    None from it means the sessions are not defined yet (F4 before final-sessions): not covered.
    """
    record = ba_frame(ctx, collection)
    if record is None:
        return False
    needed = sessions()
    return needed is not None and not (set(needed) - set(record['sessions']))


def ba_training_sessions(ctx, k):
    """A callable giving the training union of fold k: final-sessions on F4, the open labels on F2/F3."""
    def sessions():
        collection = ctx.collection(k)
        if int(k) == 4:                   # no final-sessions yet: no final-training sidecar, BA не выполнена
            if not final_training_written(collection):
                return None
            return {int(s) for s in final_training(ctx, collection)[1]['sessions']}
        labels_path, _ = fold_labels(ctx, k)
        con = connect(ctx)
        try:
            labels_view(con, labels_path)
            chosen = training_sessions(con, 'lab', ctx.n_t)
        finally:
            con.close()
        return set().union(*chosen.values())
    return sessions


def ba_evaluation_sessions(ctx, k):
    """A callable giving the evaluation population of fold k (as ``evaluation_population``)."""
    def sessions():
        collection = ctx.collection(k)
        if int(k) == 3:
            return {int(s) for s in oc.read_population(collection)}
        if int(k) == 4:
            return {int(s) for s in oc.holdout_population(collection)['sessions']}
        con = connect(ctx)
        try:
            return set(collection_sessions(con, collection))
        finally:
            con.close()
    return sessions


def require_ba_coverage(ctx, collection, sessions, what):
    """Every session of ``sessions`` has a sidecar (§5.7: sidecars only for the sessions that need them)."""
    record = ba_frame(ctx, collection)
    require(record is not None, f'No BA frame for {Path(collection).name}: {BA_NOT_RUN}')
    missing = set(int(s) for s in sessions) - set(record['sessions'])
    require(not missing, f'BA frame of {Path(collection).name} lacks {len(missing)} {what} sessions, '
                         f'e.g. {sorted(missing)[:3]}')
    return dict(sessions=len(set(int(s) for s in sessions)), covered=True)


def leakcheck_record(ctx, path):
    """Leakcheck report of otto_agent (``leakcheck/<name>/report.json``) read by ``oc.read_leakcheck``.

    F3 must cover the dev population (population.json of val-F3), F4 the holdout population of
    the power gate (``oc.holdout_population``), both on the frozen set. Problems are recorded, not raised.
    """
    path = Path(path).resolve()
    root = oc.output_dir('leakcheck').resolve()
    out = dict(path=rel(path), sha256=None, fold=None, ok=False, problems=[])
    if not path.is_relative_to(root) or not path.is_file():
        out['problems'].append('not a file under leakcheck/')
        return out
    data = oc.read_json(path)
    out.update(sha256=oc.sha256_file(path), fold=data.get('fold'))
    try:
        if data.get('fold') == 3:
            collection = ctx.collection(3)
            digest = oc.sessions_digest(oc.read_population(collection))
        elif data.get('fold') == 4:
            collection = ctx.collection(4)
            digest = oc.holdout_population(collection)['sessions_digest']
        else:
            raise ContractError('Leakcheck fold must be 3 or 4')
        oc.read_leakcheck(path, set_digest=ctx.set_digest, population_digest=digest, collection=collection.name)
    except ContractError as exc:
        out['problems'].append(str(exc))
    out['ok'] = not out['problems']
    return out


def frozen_agent_columns(prereg, agent_set):
    """Frozen agent columns (§5, §7): ``columns`` of the committed set (``oc.agent_columns``).

    A prereg that records ``agent_columns`` must name the same list.
    """
    columns = oc.agent_columns(agent_set)
    if prereg.get('agent_columns') is not None:
        require(prereg['agent_columns'] == columns, 'Prereg agent_columns differ from the committed set')
    return columns


def series_spec(series):
    require(series in oc.SERIES, f'Unknown series {series!r}')
    return oc.SERIES[series]


def arm_stage(series, arm, seed):
    """Stage of (series, arm, seed) per §2.4; refuses combinations outside the table."""
    spec = series_spec(series)
    require(arm in oc.ARMS, f'Unknown arm {arm!r}')
    require(int(seed) in oc.SEEDS, f'Seed {seed} is not preregistered')
    stage = 1 if int(seed) == oc.SEEDS[0] else 2
    require(stage in spec['arms'] and arm in spec['arms'][stage], f'{series} has no {arm}{seed} (§2.4)')
    return stage


def agent_columns_of(con, paths, ctx):
    """ag_* columns of a BA frame in file order; they must equal the frozen list when the prereg names one."""
    names = [row[0] for row in con.execute(f'DESCRIBE SELECT * FROM read_parquet({sql_list(paths)})').fetchall()]
    missing = [c for c in ('session', 'aid', *ctx.features) if c not in names]
    require(not missing, f'BA frame lacks {missing[:5]}')
    columns = [n for n in names if n.startswith(AGENT_PREFIX)]
    require(columns, 'BA frame carries no agent columns')
    if ctx.agent_columns is not None:
        require(columns == ctx.agent_columns, 'Agent columns differ from the frozen list')
    return columns


def arm_view(con, ctx, collection, arm, name='fr'):
    """DuckDB view ``name`` (session, aid, features...) of the arm frame; returns (paths, agent columns)."""
    paths = ctx.frame_paths(collection, arm)
    agent = agent_columns_of(con, paths, ctx) if arm != 'B' else []
    columns = ', '.join(f'"{c}"' for c in (*ctx.features, *agent))
    con.execute(f"""CREATE OR REPLACE TEMP VIEW {name} AS SELECT CAST(session AS BIGINT) AS session,
        CAST(aid AS BIGINT) AS aid{', ' + columns if columns else ''} FROM read_parquet({sql_list(paths)})""")
    if arm != 'B':                               # the B frame is unique by construction (otto_data.build_frame)
        dup = con.execute(f'SELECT count(*) FROM (SELECT session, aid FROM {name} GROUP BY ALL HAVING count(*) > 1)'
                          ).fetchone()[0]
        require(dup == 0, f'{Path(collection).name} {arm} frame repeats (session, aid) {dup} times')
    return paths, agent


def labels_view(con, path, name='lab'):
    """``name``(session, tc, aid) over a labels parquet with type names or codes."""
    con.execute(f"""CREATE OR REPLACE TEMP VIEW {name} AS SELECT CAST(session AS BIGINT) AS session,
        CAST({type_code_sql()} AS INTEGER) AS tc, CAST(aid AS BIGINT) AS aid FROM read_parquet({sql_str(path)})""")
    bad = con.execute(f'SELECT count(*) FROM {name} WHERE tc IS NULL OR session IS NULL OR aid IS NULL').fetchone()[0]
    require(bad == 0, f'Labels with an unknown type or NULL: {bad}')


def register_sessions(con, name, sessions):
    import numpy as np
    import pandas as pd
    con.register(f'{name}_input', pd.DataFrame({'session': np.asarray(list(sessions), dtype=np.int64)}))
    con.execute(f'CREATE OR REPLACE TEMP TABLE {name} AS SELECT session FROM {name}_input')
    con.unregister(f'{name}_input')


def fold_labels(ctx, k, purpose=None):
    """Labels parquet of fold k: labels.parquet of F2/F3; F4 only through read_sealed('final')."""
    k = int(k)
    collection = ctx.collection(k)
    if k in (2, 3):
        return collection/oc.LABELS_FILE, f'{collection.name}:{oc.LABELS_FILE}'
    require(k == 4 and purpose == 'final', 'F4 labels open only for the final series after the result receipt')
    return oc.read_sealed(collection, 'final')['labels'], f'{collection.name}:read_sealed(final)'


# =============================================================================== training rows (§6)

def training_sessions(con, k_labels='lab', n=oc.N_T):
    """First n sessions with a label of each type in sha256 order (before dropping, independent of the arm)."""
    out = {}
    for j, t in enumerate(oc.TYPES):
        rows = con.execute(f"""SELECT session FROM (SELECT DISTINCT session FROM {k_labels} WHERE tc = {j})
            ORDER BY {oc.ORDER_SQL.format(column='session')}, session LIMIT {int(n)}""").fetchall()
        out[t] = [int(r[0]) for r in rows]
    return out


def training_rows(con, frame='fr', labels='lab', type_=None, sessions=(), features=(), negatives=oc.NEGATIVES):
    """Training block of one type: positives and up to ``negatives`` negatives per session (§6).

    Candidates of ``sessions`` in ``frame``; negatives by the smallest sha256 key, ties by aid;
    sessions without a positive among the candidates are dropped after selection (sessions
    without any row in the frame are refused earlier, by ``require_frame_rows``).
    Returns (pandas frame session, aid, label, features... in (session, aid) order, dropped count).
    """
    j = oc.TYPES.index(type_)
    register_sessions(con, 'train_sessions', sessions)
    cols = ', '.join(f'c."{c}"' for c in features)
    block = con.execute(f"""
        WITH pos AS (SELECT DISTINCT session, aid FROM {labels} WHERE tc = {j}),
             c AS (SELECT f.*, (p.aid IS NOT NULL) AS positive, {negative_key_sql(type_, 'f.session', 'f.aid')} AS nkey
                   FROM {frame} f SEMI JOIN train_sessions USING (session)
                   LEFT JOIN pos p ON p.session = f.session AND p.aid = f.aid),
             r AS (SELECT *, row_number() OVER (PARTITION BY session, positive ORDER BY nkey, aid) AS nrank FROM c),
             kept AS (SELECT * FROM r WHERE positive OR nrank <= {int(negatives)}),
             ok AS (SELECT session FROM kept GROUP BY session HAVING bool_or(positive))
        SELECT c.session, c.aid, CAST(c.positive AS TINYINT) AS label{', ' + cols if cols else ''}
        FROM kept c SEMI JOIN ok USING (session) ORDER BY c.session, c.aid""").df()
    kept = int(block['session'].nunique()) if len(block) else 0
    return block, len(set(int(s) for s in sessions)) - kept


def require_frame_rows(con, frame, sessions_table):
    """Training sessions without a single row in the arm frame: a refusal, unlike "no positive" (§6)."""
    absent = int(con.execute(f"""SELECT count(*) FROM {sessions_table}
        ANTI JOIN (SELECT DISTINCT session FROM {frame}) f USING (session)""").fetchone()[0])
    require(absent == 0, f'{absent} training sessions without rows in the frame')
    return absent


def check_training_digest(manifest, chosen):
    """Training sessions against ``training_digest`` of the collection manifest when otto_data wrote one.

    The digest covers the first N_t sessions of the collection; a different N_t (smoke) is recorded, not compared.
    """
    if 'training_digest' not in manifest:
        return 'no training_digest in the manifest'
    counts = {t: len(chosen[t]) for t in oc.TYPES}
    if manifest.get('training_sessions') != counts:
        return f'not compared: manifest counts {manifest.get("training_sessions")} != {counts}'
    require(oc.canonical_digest(chosen) == manifest['training_digest'],
            'Training sessions differ from training_digest of the collection manifest')
    return 'equal'


def final_training_written(collection):
    """True when some final-training/*/sessions.json names the collection (final-sessions has run)."""
    root = oc.output_dir('final-training')
    return root.exists() and any(oc.read_json(p).get('collection') == Path(collection).name
                                 for p in root.glob(f'*/{oc.FINAL_TRAINING_FILE}'))


def final_training(ctx, collection):
    """(path, record) of the single final-training sessions of the holdout collection under this prereg and N_t."""
    return oc.final_training_record(collection.name, prereg_sha256=ctx.prereg_sha256, n_t=ctx.n_t)


def check_final_training(final, chosen):
    """The final-series training sessions recomputed from the labels equal ``training_digest`` of final-sessions."""
    path, record = final
    require(oc.canonical_digest(chosen) == record['training_digest'],
            'Final training sessions differ from training_digest of final-sessions')
    return dict(status='equal', path=rel(path), sha256=oc.sha256_file(path), training_digest=record['training_digest'])


def final_sessions(ctx, name=None):
    """The training sessions of the final series (§6) after the committed result receipt (§2.5).

    First N_t labelled sessions of F4 per type in sha256 order, from the labels of
    ``read_sealed(holdout, 'final')``; written once per holdout collection as
    ``final-training/<name>/sessions.json`` (otto-final-training-v1). otto_agent builds the F4
    sidecar of ``sessions``; ``fit --series final`` recomputes them and checks ``training_digest``.
    """
    require(ctx.mode == 'contract' and ctx.prereg is not None, 'final-sessions runs under the committed prereg')
    name = oc.output_name(name if name is not None else stamp())
    oc.require_window('final')
    collection = ctx.collection(4)
    root = oc.output_dir('final-training')
    earlier = [p for p in sorted(root.glob(f'*/{oc.FINAL_TRAINING_FILE}')) if root.exists()
               and oc.read_json(p).get('collection') == collection.name]
    require(not earlier, f'Final training sessions of {collection.name} exist: {[rel(p) for p in earlier]}')
    labels_path, _ = fold_labels(ctx, 4, 'final')
    con = connect(ctx)
    try:
        labels_view(con, labels_path)
        chosen = training_sessions(con, 'lab', ctx.n_t)
        frame = set(collection_sessions(con, collection))
    finally:
        con.close()
    union = set().union(*chosen.values())
    require(union <= frame, 'Final training sessions outside the holdout frame')
    output = oc.new_output(oc.final_training_dir(name))
    record = oc.write_final_training(output, collection.name, ctx.n_t, ctx.prereg_sha256, chosen)
    return dict(path=rel(output/oc.FINAL_TRAINING_FILE), sessions=len(record['sessions']),
                per_type={t: len(record['per_type'][t]) for t in oc.TYPES}, training_digest=record['training_digest'])


def feature_matrix(block, columns):
    """float32 matrix of ``columns`` (NULL -> NaN), filled column by column to keep one copy in memory."""
    import numpy as np
    out = np.empty((len(block), len(columns)), dtype=np.float32)
    for i, column in enumerate(columns):
        out[:, i] = block[column].to_numpy(dtype=np.float32, na_value=np.nan)
    return out


# =============================================================================== fit

def fit_dir(series, arm, seed):
    return oc.output_dir('fits', f'{series}-{arm}{int(seed)}')


def fit(ctx, series, arm, seed, output=None, purpose=None):
    """Three YetiRank models of (series, arm, seed) on the training fold; models and report.json."""
    import numpy as np
    from catboost import CatBoost, Pool
    seed = int(seed)
    spec = series_spec(series)
    k = spec['train']
    if ctx.mode == 'contract':
        arm_stage(series, arm, seed)
        require(ctx.prereg is not None, 'Fits need the committed prereg')
    else:
        require((series, arm, seed) == ('dev', 'B', oc.SEEDS[0]), 'Before prereg only dev B2026 is fitted')
    if series == 'final':
        purpose = 'final'
    collection = ctx.collection(k)
    manifest = oc.read_json(collection/oc.MANIFEST_FILE)
    final = None
    if k == 4:
        fold_labels(ctx, k, purpose)                  # refuses before any output when the barrier is closed
        final = final_training(ctx, collection)       # the sessions of final-sessions, checked below
    if arm != 'B':
        ctx.frame_paths(collection, arm)              # BA не выполнена: refused before any output
        if final is not None:
            require_ba_coverage(ctx, collection, final[1]['sessions'], 'final training')
    output = fresh_output(output if output is not None else fit_dir(series, arm, seed))
    started = time.monotonic()
    report = dict(format=FIT_FORMAT, status='running', mode=ctx.mode, series=series, arm=arm, seed=seed, train_fold=k,
                  collection=collection.name, manifest_sha256=oc.sha256_file(collection/oc.MANIFEST_FILE),
                  recipe=ctx.recipe(seed), negatives=NEGATIVE_RULE, N_t=ctx.n_t, prereg_sha256=ctx.prereg_sha256,
                  base_digest=ctx.base['digest'], code=ctx.code, created_utc=oc.utc_now())
    con = connect(ctx)
    try:
        labels_path, labels_source = fold_labels(ctx, k, purpose)
        report['labels'] = labels_source
        labels_view(con, labels_path)
        paths, agent = arm_view(con, ctx, collection, arm)
        report['frames'] = {rel(p): oc.sha256_file(p) for p in paths}
        columns = list(ctx.features) + agent
        agent_idx = list(range(len(ctx.features), len(columns)))
        report['features'] = dict(base=list(ctx.features), agent=agent)
        chosen = training_sessions(con, 'lab', ctx.n_t)
        if final is not None:
            report['training_digest'] = check_final_training(final, chosen)
        else:
            report['training_digest'] = check_training_digest(manifest, chosen)
        union = sorted(set().union(*chosen.values()))
        if arm != 'B':
            report['ba_coverage'] = require_ba_coverage(ctx, collection, union, 'training')
        register_sessions(con, 'train_union', union)
        report['sessions_without_rows'] = require_frame_rows(con, 'fr', 'train_union')
        if arm != 'B':
            report['ba_frame'] = check_ba_frame(con, ctx, collection, 'fr', 'train_union')
        training, files = {}, {}
        for j, t in enumerate(oc.TYPES):
            block, dropped = training_rows(con, 'fr', 'lab', t, chosen[t], columns, ctx.negatives)
            require(len(block) and block['label'].nunique() == 2, f'{t}: training needs positives and negatives')
            x = feature_matrix(block, columns)
            record = dict(sessions=len(chosen[t]), sessions_digest=oc.canonical_digest(chosen[t]),
                          dropped_sessions=int(dropped), dropped_rule='no positive among the candidates',
                          kept_sessions=int(block['session'].nunique()),
                          rows=int(len(block)), positives=int(block['label'].sum()),
                          rows_digest=array_digest(block['session'], block['aid'], block['label']))
            if arm == 'BApl':
                perm = permutation(seed, k, 0, j, len(block))
                x = permute_block(x, agent_idx, perm)
                record['permutation'] = dict(key=[PERMUTATION_ROOT, seed, k, 0, j], n=len(block),
                                             digest=array_digest(perm))
            tick = time.monotonic()
            model = CatBoost(ctx.recipe(seed))
            model.fit(Pool(x, label=block['label'].to_numpy(), group_id=block['session'].to_numpy(),
                           feature_names=columns), verbose=False)
            record['fit_seconds'] = round(time.monotonic()-tick, 3)
            require(model.tree_count_ == ctx.recipe(seed)['iterations'], f'{t}: fixed-tree fit incomplete')
            name = MODEL_FILE.format(type=t)
            model.save_model(str(output/name))
            files[name] = oc.sha256_file(output/name)
            training[t] = record
            del block, x
        report.update(training=training, files=files, status='completed')
        report['identity'] = identity_of(report)
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        raise
    finally:
        con.close()
        report['seconds'] = round(time.monotonic()-started, 3)
        oc.atomic_json(output/REPORT_FILE, normalized(report))
    return dict(report, path=str(output))


def identity_of(report):
    """What every arm of a series shares: fold, collection, training session sets, recipe without seed."""
    recipe = {k: v for k, v in report['recipe'].items() if k != 'random_seed'}
    return dict(series=report['series'], train_fold=report['train_fold'], collection=report['collection'],
                manifest_sha256=report['manifest_sha256'], labels=report['labels'], recipe=recipe,
                N_t=report['N_t'], base_digest=report['base_digest'],
                sessions={t: report['training'][t]['sessions_digest'] for t in oc.TYPES})


def check_ba_frame(con, ctx, collection, ba_view, sessions_table):
    """B enters BA whole (§5.2) over the sessions of ``sessions_table``: every B key and its base values.

    Base columns are compared as DOUBLE (frame.parquet stores ranks as USMALLINT, flags as
    UTINYINT, other features as INTEGER); NULL equals NULL in EXCEPT. Refuses on any difference.
    """
    b_paths = ctx.frame_paths(collection, 'B')
    values = ', '.join(f'CAST("{c}" AS DOUBLE) AS "{c}"' for c in ctx.features)
    values = ', ' + values if values else ''
    # by chunks of sessions: one EXCEPT over the F4 population (1M sessions) ran out of memory (deviation d1)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE ba_check_chunks AS SELECT session,
        (row_number() OVER (ORDER BY session) - 1) // {int(BA_CHECK_CHUNK)} AS chunk FROM {sessions_table}""")
    chunks = con.execute('SELECT coalesce(max(chunk) + 1, 0) FROM ba_check_chunks').fetchone()[0]
    missing = differ = 0
    try:
        for chunk in range(int(chunks)):
            part = f'(SELECT session FROM ba_check_chunks WHERE chunk = {chunk})'
            m, d = con.execute(f"""
                WITH b AS (SELECT CAST(session AS BIGINT) AS session, CAST(aid AS BIGINT) AS aid{values}
                           FROM read_parquet({sql_list(b_paths)}) SEMI JOIN {part} c USING (session)),
                     a AS (SELECT session, aid{values} FROM {ba_view} SEMI JOIN {part} c USING (session))
                SELECT (SELECT count(*) FROM b ANTI JOIN a USING (session, aid)),
                       (SELECT count(*) FROM (SELECT * FROM b EXCEPT SELECT * FROM a))""").fetchone()
            missing, differ = missing + int(m), differ + int(d)
    finally:
        con.execute('DROP TABLE IF EXISTS ba_check_chunks')
    out = dict(b_keys_missing=int(missing), b_values_differ=int(differ) - int(missing))
    require(out['b_keys_missing'] == 0, f'BA frame lacks {missing} candidates of B (§5.2)')
    require(out['b_values_differ'] == 0, f'BA frame changes base values of {out["b_values_differ"]} B rows (§5.2)')
    return out


def load_fit(directory):
    directory = Path(directory)
    path = directory/REPORT_FILE
    require(path.is_file(), f'No fit report {path}')
    report = oc.read_json(path)
    require(report.get('format') == FIT_FORMAT and report.get('status') == 'completed', f'Fit {path} not completed')
    for name, digest in report['files'].items():
        require(oc.sha256_file(directory/name) == digest, f'Fit file changed: {directory/name}')
    require(identity_of(report) == report['identity'], f'Fit identity of {path} differs from its fields')
    return report


def load_models(directory, report):
    from catboost import CatBoost
    models = {}
    for t in oc.TYPES:
        model = CatBoost()
        model.load_model(str(Path(directory)/MODEL_FILE.format(type=t)))
        models[t] = model
    return models


def check_pairing(reports):
    """Arms of one series: identical training sessions, recipe and inputs; BA and BApl identical rows."""
    reports = list(reports)
    require(reports, 'No fits to pair')
    identities = {oc.canonical_digest(r['identity']) for r in reports}
    require(len(identities) == 1, 'Fits are not paired: training sessions, recipe or inputs differ')
    for r in reports:
        require(r['recipe']['random_seed'] == r['seed'], 'Fit recipe seed differs from its seed')
    by_seed = {}
    for r in reports:
        by_seed.setdefault(r['seed'], {})[r['arm']] = r
    for seed, arms in by_seed.items():
        if 'BA' in arms and 'BApl' in arms:
            for t in oc.TYPES:
                require(arms['BA']['training'][t]['rows_digest'] == arms['BApl']['training'][t]['rows_digest'],
                        f'BA{seed} and BApl{seed} train on different rows of {t}')
            require(arms['BA']['features'] == arms['BApl']['features'], f'BA{seed} and BApl{seed} features differ')
    return identities.pop()


# =============================================================================== scoring (§6)

def top_lists(sessions, aids, scores, k=oc.TOP_K):
    """(session, aid, rank) of the k best rows per session by score desc, aid asc."""
    import numpy as np
    import pandas as pd
    sessions = np.asarray(sessions, dtype=np.int64)
    aids = np.asarray(aids, dtype=np.int64)
    scores = np.asarray(scores, dtype=np.float64)
    order = np.lexsort((aids, -scores, sessions))
    out = pd.DataFrame({'session': sessions[order], 'aid': aids[order]})
    out['rank'] = out.groupby('session', sort=False).cumcount() + 1
    return out[out['rank'] <= k].reset_index(drop=True)


def fill_lists(model_lists, pop_lists, sessions, k=oc.TOP_K):
    """Top up lists shorter than k from Pop of the same type, without repeats (§6).

    ``model_lists``/``pop_lists``: session, aid, rank. Returns (lists, sessions topped up, sessions still short).
    """
    import numpy as np
    import pandas as pd
    model = model_lists[['session', 'aid', 'rank']].assign(key=lambda f: f['rank'].astype(np.int64))
    pop = pop_lists[['session', 'aid', 'rank']].assign(key=lambda f: 1000 + f['rank'].astype(np.int64))
    both = pd.concat([model, pop], ignore_index=True)
    both = both[both['session'].isin(set(int(s) for s in sessions))]
    both = both.sort_values(['session', 'key', 'aid'], kind='mergesort').drop_duplicates(['session', 'aid'])
    both['rank'] = both.groupby('session', sort=False).cumcount() + 1
    out = both[both['rank'] <= k][['session', 'aid', 'rank']].reset_index(drop=True)
    model_counts = model_lists.groupby('session').size()
    counts = out.groupby('session').size()
    population = pd.Index(sorted(int(s) for s in sessions))
    topped = int((model_counts.reindex(population, fill_value=0) < k).sum())
    short = int((counts.reindex(population, fill_value=0) < k).sum())
    return out, topped, short


def score_population(ctx, con, view, population, models, columns, agent_columns, arm, seed, k, pop_view, sink,
                     batch=None):
    """Score the population in batches of ``batch`` sessions (sha256 order) and hand each batch to ``sink``.

    ``sink(batch_index, lists)`` gets a frame session, tc, aid, rank (20 per type after the Pop top-up).
    BApl permutes the agent block of each batch by default_rng([20261022, seed, k, 1, b]), k the evaluation fold.
    Returns counts: rows, finiteness per type, topped-up and short lists per type, agent non-NULL shares.
    """
    import numpy as np
    import pandas as pd
    from catboost import Pool
    batch = int(batch or ctx.score_batch)
    require(batch >= 1, 'batch >= 1')
    ordered = oc.first_in_order(population, None)
    agent_idx = [columns.index(c) for c in agent_columns]
    stats = dict(rows=0, batches=0, finite={t: True for t in oc.TYPES}, topped={t: 0 for t in oc.TYPES},
                 short={t: 0 for t in oc.TYPES}, nonnull={c: 0 for c in agent_columns}, permutations=[])
    cols = ', '.join(f'"{c}"' for c in columns)
    for b, start in enumerate(range(0, len(ordered), batch)):
        chunk = ordered[start:start+batch]
        register_sessions(con, 'score_batch', chunk)
        rows = con.execute(f"""SELECT session, aid{', ' + cols if cols else ''} FROM {view}
            SEMI JOIN score_batch USING (session) ORDER BY session, aid""").df()
        pops = con.execute(f"""SELECT session, tc, aid, rank FROM {pop_view} SEMI JOIN score_batch USING (session)
            ORDER BY session, tc, rank""").df()
        x = feature_matrix(rows, columns)
        for c, i in zip(agent_columns, agent_idx):
            stats['nonnull'][c] += int(np.count_nonzero(~np.isnan(x[:, i])))
        if arm == 'BApl':
            perm = permutation(seed, k, 1, b, len(rows))
            x = permute_block(x, agent_idx, perm)
            stats['permutations'].append(dict(batch=b, key=[PERMUTATION_ROOT, int(seed), int(k), 1, b], n=len(rows),
                                              digest=array_digest(perm)))
        parts = []
        for j, t in enumerate(oc.TYPES):
            if len(rows):
                raw = np.asarray(models[t].predict(Pool(x, feature_names=list(columns)),
                                                   prediction_type=PREDICTION_TYPE, thread_count=ctx.recipe(seed)
                                                   ['thread_count']), dtype=np.float64)
            else:
                raw = np.zeros(0)
            stats['finite'][t] = stats['finite'][t] and bool(np.isfinite(raw).all())
            lists = top_lists(rows['session'], rows['aid'], raw)
            lists, topped, short = fill_lists(lists, pops[pops['tc'] == j], chunk)
            stats['topped'][t] += topped
            stats['short'][t] += short
            parts.append(lists.assign(tc=j))
        stats['rows'] += len(rows)
        stats['batches'] += 1
        out = pd.concat(parts, ignore_index=True)[['session', 'tc', 'aid', 'rank']]
        sink(b, out.sort_values(['session', 'tc', 'rank'], kind='mergesort').reset_index(drop=True))
    stats['nonnull'] = {c: (v/stats['rows'] if stats['rows'] else 0.0) for c, v in stats['nonnull'].items()}
    return stats


def pop_view(con, path, name='popv'):
    """Pop lists (RANKED_COLUMNS, type names or codes) as ``name``(session, tc, aid, rank)."""
    con.execute(f"""CREATE OR REPLACE TEMP VIEW {name} AS SELECT CAST(session AS BIGINT) AS session,
        CAST({type_code_sql()} AS INTEGER) AS tc, CAST(aid AS BIGINT) AS aid, CAST(rank AS BIGINT) AS rank
        FROM read_parquet({sql_str(path)})""")
    bad = con.execute(f'SELECT count(*) FROM {name} WHERE tc IS NULL OR rank < 1 OR rank > {oc.TOP_K}').fetchone()[0]
    require(bad == 0, f'Pop lists: {bad} rows with an unknown type or a rank outside 1..{oc.TOP_K}')


def collection_sessions(con, collection):
    return [int(r[0]) for r in con.execute(f"""SELECT DISTINCT session FROM
        read_parquet({sql_str(Path(collection)/oc.FRAME_FILE)}) ORDER BY session""").fetchall()]


def evaluation_population(ctx, con, series, collection):
    """Evaluation sessions (§2.4): dev population.json; holdout population.json of the power gate; F5 all."""
    k = series_spec(series)['eval']
    if k == 3:
        return oc.read_population(collection), None
    if k == 4:
        population = oc.holdout_population(collection)
        return population['sessions'], population['record']
    return collection_sessions(con, collection), None


def make_pop(ctx, collection, output):
    """Pop lists of the collection frame (otto_data.pop) into ``output``; returns the eval-report record."""
    frame = Path(collection)/oc.FRAME_FILE
    od.pop(frame, output, threads=ctx.threads, memory=ctx.memory)
    return dict(path=rel(output), sha256=oc.sha256_file(output), frame=rel(frame), frame_sha256=oc.sha256_file(frame),
                rule='otto_data.pop: (h) by h_rank, then p_t without repeats, first 20')


def pop_coverage(con, pop_name, sessions_table):
    """Sessions of the population whose Pop list of a type holds fewer than 20 aids."""
    out = {}
    for j, t in enumerate(oc.TYPES):
        out[t] = int(con.execute(f"""SELECT count(*) FROM {sessions_table} s LEFT JOIN
            (SELECT session, count(*) AS n FROM {pop_name} WHERE tc = {j} GROUP BY session) p USING (session)
            WHERE coalesce(p.n, 0) < {oc.TOP_K}""").fetchone()[0])
    return out


def evaluate(ctx, series, arm, seed, fit_directory=None, output=None, batch=None):
    """Score the evaluation fold of the series with the three models of a fit (§6); metrics on open labels."""
    seed = int(seed)
    spec = series_spec(series)
    k = spec['eval']
    if k == 5:
        require(oc.holdout_window_open('final'), 'F5 is scored after the committed holdout result (§2.5)')
    fit_directory = Path(fit_directory) if fit_directory is not None else fit_dir(series, arm, seed)
    fit_report = load_fit(fit_directory)
    require((fit_report['series'], fit_report['arm'], fit_report['seed']) == (series, arm, seed),
            f'{fit_directory} is not {series} {arm}{seed}')
    require(fit_report['mode'] == ctx.mode and fit_report['prereg_sha256'] == ctx.prereg_sha256,
            'Fit ran under another prereg or mode')
    collection = ctx.collection(k)
    if arm != 'B':
        ctx.frame_paths(collection, arm)              # BA не выполнена: refused before any output
    con = connect(ctx)
    try:
        population, power = evaluation_population(ctx, con, series, collection)
        if arm != 'B':
            require_ba_coverage(ctx, collection, population, 'population')
    except Exception:
        con.close()
        raise
    output = fresh_output(output if output is not None else fit_directory/EVAL_DIR)
    started = time.monotonic()
    report = dict(format=EVAL_FORMAT, status='running', mode=ctx.mode, series=series, arm=arm, seed=seed, eval_fold=k,
                  fit_report_sha256=oc.sha256_file(fit_directory/REPORT_FILE), collection=collection.name,
                  manifest_sha256=oc.sha256_file(collection/oc.MANIFEST_FILE), prereg_sha256=ctx.prereg_sha256,
                  code=ctx.code, created_utc=oc.utc_now())
    parts = output/'parts'
    try:
        report['pop'] = make_pop(ctx, collection, output/POP_FILE)
        report['population'] = dict(n=len(population), digest=oc.sessions_digest(population))
        if power is not None:
            report['population']['power_gate'] = power
        paths, agent = arm_view(con, ctx, collection, arm)
        require(agent == fit_report['features']['agent'], 'Agent columns differ from the fit')
        report['frames'] = {rel(p): oc.sha256_file(p) for p in paths}
        register_sessions(con, 'population', population)
        report['sessions_without_rows'] = int(con.execute("""SELECT count(*) FROM population
            ANTI JOIN (SELECT DISTINCT session FROM fr) f USING (session)""").fetchone()[0])
        if arm != 'B':
            report['ba_frame'] = check_ba_frame(con, ctx, collection, 'fr', 'population')
        pop_view(con, output/POP_FILE)
        report['pop']['short_sessions'] = pop_coverage(con, 'popv', 'population')
        models = load_models(fit_directory, fit_report)
        columns = list(ctx.features) + agent
        parts.mkdir()

        def sink(b, lists):
            oc.write_parquet(lists, parts/f'part-{b:06d}.parquet')
        stats = score_population(ctx, con, 'fr', population, models, columns, agent, arm, seed, k, 'popv', sink,
                                 batch=batch)
        con.execute(f"""COPY (SELECT session, {type_name_sql()} AS type, aid, rank FROM
            read_parquet({sql_str(parts/'*.parquet')}) ORDER BY session, tc, rank)
            TO {sql_str(output/RANKED_FILE)} (FORMAT parquet)""")
        shutil.rmtree(parts)
        report.update(batch=int(batch or ctx.score_batch), batches=stats['batches'], rows=stats['rows'],
                      finite=stats['finite'], finite_all=all(stats['finite'].values()),
                      topped_sessions=stats['topped'], short_lists=stats['short'],
                      ranked=dict(file=RANKED_FILE, sha256=oc.sha256_file(output/RANKED_FILE)))
        if agent:
            report['agent_nonnull'] = dict(definition='share of non-NULL values over the full arm frame of the '
                                                      'evaluation population', shares=stats['nonnull'])
        if arm == 'BApl':
            report['permutation'] = dict(rule=PERMUTATION_RULE, batches=stats['permutations'])
        if k == 3:
            labels_path = collection/oc.LABELS_FILE
            value = oc.metric(output/RANKED_FILE, labels_path, sessions=population, threads=ctx.threads)
            write_metrics(value, output/METRICS_FILE)
            report['metrics'] = dict(file=METRICS_FILE, sha256=oc.sha256_file(output/METRICS_FILE),
                                     recall=value['recall'], score=value['score'])
            report['ceiling'] = ceiling(con, 'fr', labels_path, 'population')
        report['status'] = 'completed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = f'{type(exc).__name__}: {exc}'[:2000]
        raise
    finally:
        con.close()
        shutil.rmtree(parts, ignore_errors=True)
        report['seconds'] = round(time.monotonic()-started, 3)
        oc.atomic_json(output/REPORT_FILE, normalized(report))
    return dict(report, path=str(output))


def ceiling(con, view, labels_path, sessions_table):
    """Candidate ceiling per type: Σ min(20, |G ∩ C|) / Σ min(20, |G|) over the population (§10)."""
    labels_view(con, labels_path, 'ceil_lab')
    out = {}
    for j, t in enumerate(oc.TYPES):
        hit, den = con.execute(f"""WITH g AS (SELECT l.session, l.aid FROM ceil_lab l SEMI JOIN {sessions_table}
                                              USING (session) WHERE l.tc = {j}),
                 d AS (SELECT session, least(count(*), {oc.TOP_K}) AS n FROM g GROUP BY session),
                 h AS (SELECT session, least(count(*), {oc.TOP_K}) AS n FROM g SEMI JOIN {view} USING (session, aid)
                       GROUP BY session)
            SELECT (SELECT coalesce(sum(n), 0) FROM h), (SELECT coalesce(sum(n), 0) FROM d)""").fetchone()
        out[t] = float(hit)/float(den) if den else None
    return out


def write_metrics(value, path):
    import pandas as pd
    columns = {'session': value['sessions']}
    for t in oc.TYPES:
        columns[f'hits_{t}'] = value['hits'][t]
        columns[f'den_{t}'] = value['den'][t]
    oc.write_parquet(pd.DataFrame(columns), path, order_by='session')


def read_metrics(path):
    """metrics.parquet -> the dict shape of otto_common.metric."""
    import numpy as np
    frame = oc.read_parquet(path).sort_values('session', kind='mergesort')
    out = dict(sessions=frame['session'].to_numpy(dtype=np.int64), hits={}, den={}, recall={})
    for t in oc.TYPES:
        out['hits'][t] = frame[f'hits_{t}'].to_numpy(dtype=np.int64)
        out['den'][t] = frame[f'den_{t}'].to_numpy(dtype=np.int64)
        total = int(out['den'][t].sum())
        out['recall'][t] = float(out['hits'][t].sum())/total if total else float('nan')
    out['score'] = sum(oc.WEIGHTS[t]*out['recall'][t] for t in oc.TYPES)
    return out


def load_eval(series, arm, seed, directory=None):
    """Completed evaluation of a fit, its files re-hashed; returns (directory, report)."""
    directory = Path(directory) if directory is not None else fit_dir(series, arm, seed)/EVAL_DIR
    path = directory/REPORT_FILE
    require(path.is_file(), f'No evaluation report {path}')
    report = oc.read_json(path)
    require(report.get('format') == EVAL_FORMAT and report.get('status') == 'completed', f'{path} not completed')
    require((report['series'], report['arm'], report['seed']) == (series, arm, int(seed)), f'{path} is another fit')
    require(oc.sha256_file(directory/RANKED_FILE) == report['ranked']['sha256'], f'Ranked file changed: {directory}')
    if 'metrics' in report:
        require(oc.sha256_file(directory/METRICS_FILE) == report['metrics']['sha256'], f'Metrics changed: {directory}')
    fit_report = directory.parent/REPORT_FILE
    require(oc.sha256_file(fit_report) == report['fit_report_sha256'], f'Fit report changed: {fit_report}')
    return directory, report


def check_eval_pairing(evals):
    """Evaluations of one series: same collection, population and Pop lists (built from the same frame)."""
    keys = {(r['collection'], r['manifest_sha256'], r['population']['digest'], r['pop']['frame_sha256'])
            for _, r in evals.values()}
    require(len(keys) == 1, 'Evaluations are not paired: collection, population or Pop lists differ')


def eval_exists(series, arm, seed):
    return (fit_dir(series, arm, seed)/EVAL_DIR/REPORT_FILE).is_file()


def series_evals(ctx, series, seed, arms):
    """({arm: (directory, report)}, BA present) for the evaluations of a series.

    B is required. An evaluation of BA or BApl, when present, must be complete; it may be
    absent only when BA is not run (``Context.ba_run``: frames short of the training union or the population).
    """
    spec = series_spec(series)
    out = {}
    for arm in arms:
        if arm == 'B' or eval_exists(series, arm, seed):
            out[arm] = load_eval(series, arm, seed)
        else:
            require(not ctx.ba_run(spec['train'], spec['eval']),
                    f'{series} {arm}{seed} is not evaluated though the BA frames cover the series')
    return out, 'BA' in out


def pop_metric(con_threads, report, labels_path, population):
    path = from_rel(report['pop']['path'])
    require(oc.sha256_file(path) == report['pop']['sha256'], f'Pop lists changed: {path}')
    return oc.metric(path, labels_path, sessions=population, threads=con_threads)


# =============================================================================== contrast (§8, §10)

def dev_arms(ctx):
    return [a for a in oc.ARMS if a != 'BApl' or ctx.dev_bapl]


def contrast(ctx, output=None):
    """Dev contrast on F3, seed 2026: D = BA - B, P = BA - BApl, BApl - B; descriptive only.

    Without a BA frame (BA не выполнена) D and P are null and the power gate takes all of Q_4.
    """
    seed = oc.SEEDS[0]
    evals, ba_run = series_evals(ctx, 'dev', seed, dev_arms(ctx))
    arms = list(evals)
    check_eval_pairing(evals)
    check_pairing([load_fit(d.parent) for d, _ in evals.values()])
    values = {a: read_metrics(d/METRICS_FILE) for a, (d, _) in evals.items()}
    first = evals['B'][1]
    collection = ctx.collection(3)
    population = oc.read_population(collection)
    require(oc.canonical_digest(sorted(int(s) for s in population)) == first['population']['digest'],
            'Dev population changed since the evaluation')
    pop = pop_metric(ctx.threads, first, collection/oc.LABELS_FILE, population)
    result = dict(format=CONTRAST_FORMAT, series='dev', seed=seed, descriptive=True, prereg_sha256=ctx.prereg_sha256,
                  population=first['population'], arms=arms, bapl_cut=not ctx.dev_bapl,
                  ba=None if ba_run else BA_NOT_RUN,
                  metrics={f'{a}{seed}': dict(recall=v['recall'], score=v['score']) for a, v in values.items()},
                  pop=dict(recall=pop['recall'], score=pop['score']),
                  ceiling={a: r['ceiling'] for a, (_, r) in evals.items()},
                  D={str(seed): oc.bootstrap_ratio(values['B'], values['BA']) if 'BA' in values else None},
                  evals={rel(d/REPORT_FILE): oc.sha256_file(d/REPORT_FILE) for d, _ in evals.values()},
                  code=ctx.code, created_utc=oc.utc_now())
    if 'BApl' in values:
        result['P'] = {str(seed): oc.bootstrap_ratio(values['BApl'], values['BA'])}
        result['BApl_minus_B'] = {str(seed): oc.bootstrap_ratio(values['B'], values['BApl'])}
    output = oc.new_output(output if output is not None else oc.output_dir('contrast', stamp()))
    oc.atomic_json(output/'contrast.json', normalized(result))
    d = result['D'][str(seed)]
    return dict(path=str(output/'contrast.json'), D=d['ci'] if d else None,
                P=result['P'][str(seed)]['ci'] if 'P' in result else None, metrics=result['metrics'], pop=result['pop'],
                ba=result['ba'])


# =============================================================================== gates (§8)

def power_rule(ci, n_dev, q4):
    """Population rule of the power gate: (n_population, expected half-width at 1e6, resolution, rule text)."""
    cap = oc.HOLDOUT_POPULATION_CAP
    if ci is None:
        return q4, None, None, 'CI(BA - B) on F3 not computed: every session of Q_4'
    w = (float(ci[1]) - float(ci[0]))/2
    expected = w*math.sqrt(n_dev/cap)
    if q4 <= cap:
        n, rule = q4, f'Q_4 has {q4} <= {cap} sessions: every session'
    elif expected <= oc.POWER_HALF_WIDTH:
        n, rule = cap, f'expected half-width {expected:.6f} <= {oc.POWER_HALF_WIDTH}: first {cap} in sha256 order'
    else:
        n, rule = q4, f'expected half-width {expected:.6f} > {oc.POWER_HALF_WIDTH}: every session of Q_4'
    return n, expected, w*math.sqrt(n_dev/n), rule


power_gate_dirs = oc.power_gate_dirs
power_gate_report = oc.power_gate_report


def gate_power(ctx, contrast_path, output=None):
    """Choose the F4 evaluation population (§8) and write population.json of the holdout collection."""
    collection = ctx.collection(4)
    require(not power_gate_dirs(collection.name), 'A power gate report of this holdout collection exists; '
                                                  'the population is chosen once')
    contrast_path = Path(contrast_path)
    data = oc.read_json(contrast_path)
    require(data.get('format') == CONTRAST_FORMAT and data.get('prereg_sha256') == ctx.prereg_sha256,
            'Not a dev contrast of this prereg')
    d = data['D'].get(str(oc.SEEDS[0]))
    ci = d['ci'] if d and all(x is not None and math.isfinite(x) for x in d['ci']) else None
    n_dev = int(data['population']['n'])
    con = connect(ctx)
    try:
        q4 = collection_sessions(con, collection)
        n, expected, resolution, rule = power_rule(ci, n_dev, len(q4))
        register_sessions(con, 'q4', q4)
        sessions = [int(r[0]) for r in con.execute(f"""SELECT session FROM q4
            ORDER BY {oc.ORDER_SQL.format(column='session')}, session LIMIT {int(n)}""").fetchall()]
    finally:
        con.close()
    body = oc.write_population(collection, sessions, rule)
    digest = oc.canonical_digest(body)
    output = oc.new_output(output if output is not None else oc.output_dir('gate', f'{oc.POWER_GATE_PREFIX}{stamp()}'))
    report = dict(format=GATE_FORMAT, kind='power', ok=True, contrast=dict(path=rel(contrast_path),
                  sha256=oc.sha256_file(contrast_path)), ci_dev=ci, n_dev=n_dev, q4_sessions=len(q4),
                  expected_half_width_1e6=expected, threshold=oc.POWER_HALF_WIDTH,
                  population=dict(collection=collection.name, n=len(sessions), digest=digest, rule=rule),
                  resolution=resolution, note=RESOLUTION_NOTE if resolution is not None and
                  resolution > oc.POWER_HALF_WIDTH else None, prereg_sha256=ctx.prereg_sha256, code=ctx.code,
                  created_utc=oc.utc_now())
    oc.atomic_json(output/GATE_FILE, normalized(report))
    return dict(path=str(output/GATE_FILE), population=report['population'], resolution=resolution,
                note=report['note'])


def parity(reference, target):
    """Non-NULL parity (§8): share in [0.5·r_c, 2·r_c]; r_c = 0 needs share 0."""
    columns = {}
    for column, r in reference.items():
        share = target.get(column)
        ok = share is not None and (share == 0 if r == 0 else PARITY[0]*r <= share <= PARITY[1]*r)
        columns[column] = dict(reference=r, share=share, ok=bool(ok))
    extra = sorted(set(target) - set(reference))
    return dict(ok=bool(columns) and not extra and all(c['ok'] for c in columns.values()), columns=columns,
                unexpected=extra)


def evals_files(evals):
    """Hashes a receipt pins for a set of evaluations: ranked files, reports and the Pop lists."""
    files = {}
    for d, r in evals.values():
        files[rel(d/RANKED_FILE)] = r['ranked']['sha256']
        files[rel(d/REPORT_FILE)] = oc.sha256_file(d/REPORT_FILE)
        files[r['pop']['path']] = r['pop']['sha256']
    return files


def gate1_checks(ctx, stage, leakcheck=()):
    """Checks of gate 1 (stage 1) or gate 1 of stage 2 (§8), recomputed from the files."""
    stage = int(stage)
    seed = oc.SEEDS[stage-1]
    hold, hold_ba = series_evals(ctx, 'holdout', seed, oc.ARMS)
    check_eval_pairing(hold)
    check_pairing([load_fit(d.parent) for d, _ in hold.values()])
    dev_ba = load_eval('dev', 'BA', oc.SEEDS[0]) if 'BA' in hold and eval_exists('dev', 'BA', oc.SEEDS[0]) else None
    checks = dict(stage=stage, seed=seed, finite={}, lists={}, present={a: a in hold for a in oc.ARMS},
                  ba=None if hold_ba else BA_NOT_RUN)
    if dev_ba is not None:
        checks['parity'] = parity(dev_ba[1]['agent_nonnull']['shares'], hold['BA'][1]['agent_nonnull']['shares'])
    else:
        checks['parity'] = dict(ok=False, columns={}, unexpected=[], reason=BA_NOT_RUN)
    if 'BA' in hold and 'BApl' in hold:
        require(hold['BA'][1]['agent_nonnull'] == hold['BApl'][1]['agent_nonnull'], 'BA and BApl shares differ on F4')
    for a, (_, r) in hold.items():
        checks['finite'][f'holdout-{a}{seed}'] = bool(r['finite_all'])
        checks['lists'][f'holdout-{a}{seed}'] = int(sum(r['short_lists'].values()))
    files = evals_files(hold)
    if stage == 1:
        dev, _ = series_evals(ctx, 'dev', seed, dev_arms(ctx))
        check_eval_pairing(dev)
        records = [leakcheck_record(ctx, p) for p in leakcheck]
        folds = sorted({r['fold'] for r in records if r['ok']})
        checks['leakcheck'] = dict(ok=bool(records) and all(r['ok'] for r in records) and folds == [3, 4],
                                   reports=records)
        collection = ctx.collection(3)
        population = oc.read_population(collection)
        pop = pop_metric(ctx.threads, dev['B'][1], collection/oc.LABELS_FILE, population)
        checks['floor'] = {}
        for a, (d, r) in dev.items():
            checks['finite'][f'dev-{a}{seed}'] = bool(r['finite_all'])
            checks['lists'][f'dev-{a}{seed}'] = int(sum(r['short_lists'].values()))
            recall = read_metrics(d/METRICS_FILE)['recall']
            checks['floor'][f'{a}{seed}'] = dict(recall=recall, pop=pop['recall'],
                                                 ok=all(recall[t] >= pop['recall'][t] for t in oc.TYPES))
        checks['bapl_dev_cut'] = not ctx.dev_bapl
        files.update(evals_files(dev))
    else:
        opened = oc.receipt('holdout-open')
        checks['floor_inherited'] = {a: opened['gate1']['status'].get(a) for a in oc.ARMS}
        checks['leakcheck'] = dict(ok=True, inherited=True)
        files.update({k: v for k, v in opened['score_files'].items()})
    return normalized(checks), files


def gate1_status(checks):
    """Arm status of gate 1 from its checks: B needs finite, floor and full lists; BA, BApl also leakcheck, parity."""
    seed = checks['seed']

    def own(arm):
        if not checks.get('present', {}).get(arm, True):
            return False                       # an absent arm (BA не выполнена) fails gate 1
        keys = [k for k in checks['finite'] if k.endswith(f'-{arm}{seed}')]
        good = all(checks['finite'][k] for k in keys) and all(checks['lists'][k] == 0 for k in keys)
        if checks['stage'] == 1:
            floor = checks['floor'].get(f'{arm}{seed}')
            good = good and (floor['ok'] if floor is not None else arm == 'BApl' and checks['bapl_dev_cut'])
        else:
            good = good and bool(checks['floor_inherited'].get(arm))
        if arm != 'B':
            good = good and checks['leakcheck']['ok'] and checks['parity']['ok']
        return bool(good)
    return {arm: own(arm) for arm in oc.ARMS}


def opened_arms(status):
    """Arms the holdout opens for (§8): all three, or B (with Pop) when BA or BApl failed; none without B."""
    require(status.get('B'), 'Gate 1 failed for B: the holdout is not read (§8)')
    return list(oc.ARMS) if status.get('BA') and status.get('BApl') else ['B']


def gate2_checks(ctx, stage):
    """Gate 2 (§8): finite F5 scores, non-NULL parity against F4, assemble receipts of the stage's files."""
    seed = oc.SEEDS[int(stage)-1]
    final, _ = series_evals(ctx, 'final', seed, ('B', 'BA'))
    check_eval_pairing(final)
    check_pairing([load_fit(d.parent) for d, _ in final.values()])
    checks = dict(stage=int(stage), seed=seed, finite={}, lists={}, assemble={},
                  present={a: a in final for a in ('B', 'BA')})
    if 'BA' in final and eval_exists('holdout', 'BA', oc.SEEDS[0]):
        hold_ba = load_eval('holdout', 'BA', oc.SEEDS[0])
        checks['parity'] = parity(hold_ba[1]['agent_nonnull']['shares'], final['BA'][1]['agent_nonnull']['shares'])
    else:
        checks['parity'] = dict(ok=False, columns={}, unexpected=[], reason=BA_NOT_RUN)
    for a, (d, r) in final.items():
        checks['finite'][f'{a}{seed}'] = bool(r['finite_all'])
        checks['lists'][f'{a}{seed}'] = int(sum(r['short_lists'].values()))
        checks['assemble'][f'{a}{seed}'] = assemble_record(a, seed, r)
    return normalized(checks), evals_files(final)


def kaggle_file(arm, seed):
    name = f'{arm}{int(seed)}'
    return oc.output_dir('kaggle', name)/f'{name}.csv'


def assemble_record(arm, seed, eval_report):
    """The otto_data.assemble receipt next to the Kaggle file of (arm, seed), re-hashed: built from the ranked
    lists of the F5 evaluation (``ranked_sha256``), one file of the population, nothing topped up at assembly."""
    path = kaggle_file(arm, seed)
    receipt_path = path.with_suffix('.json')
    out = dict(file=rel(path), ok=False, problems=[])
    if not path.is_file() or not receipt_path.is_file():
        out['problems'].append('no assembled file or receipt')
        return out
    data = oc.read_json(receipt_path)
    sha = oc.sha256_file(path)
    out.update(sha256=sha, bytes=path.stat().st_size, rows=data.get('rows'), sessions=data.get('sessions'))
    if data.get('format') != ASSEMBLE_FORMAT or data.get('sha256') != sha:
        out['problems'].append('receipt format or SHA-256 differs')
    if data.get('rows') != len(oc.TYPES)*int(data.get('sessions') or -1):
        out['problems'].append('rows != 3 x sessions')
    if data.get('sessions') != eval_report['population']['n']:
        out['problems'].append('sessions differ from the F5 population')
    if data.get('ranked_sha256') != eval_report['ranked']['sha256']:
        out['problems'].append('assembled from other ranked lists than the F5 evaluation')
    if data.get('filled_sessions') != 0:
        out['problems'].append(f'filled_sessions is {data.get("filled_sessions")}, not 0')
    out['ok'] = not out['problems']
    return out


def gate2_status(checks):
    seed = checks['seed']
    status = {}
    for arm in ('B', 'BA'):
        key = f'{arm}{seed}'
        if not checks.get('present', {}).get(arm, True):
            status[arm] = False
            continue
        good = checks['finite'][key] and checks['lists'][key] == 0 and checks['assemble'][key]['ok']
        status[arm] = bool(good and (arm == 'B' or checks['parity']['ok']))
    return status


def gate(ctx, kind, stage=1, leakcheck=(), contrast_path=None, output=None):
    kind = str(kind)
    require(kind in GATE_KINDS, f'Unknown gate {kind!r}')
    if kind == 'power':
        require(contrast_path, 'The power gate needs --contrast')
        return gate_power(ctx, contrast_path, output)
    stage = int(stage)
    require(stage in (1, 2), 'Stage 1 or 2')
    if kind == '1':
        checks, files = gate1_checks(ctx, stage, leakcheck)     # no leakcheck reports: BA and BApl fail
        status = gate1_status(checks)
    else:
        checks, files = gate2_checks(ctx, stage)
        status = gate2_status(checks)
    output = oc.new_output(output if output is not None else oc.output_dir('gate', f'gate{kind}-s{stage}-{stamp()}'))
    report = dict(format=GATE_FORMAT, kind=kind, stage=stage, ok=all(status.values()), status=status, checks=checks,
                  files=files, prereg_sha256=ctx.prereg_sha256, code=ctx.code, created_utc=oc.utc_now())
    oc.atomic_json(output/GATE_FILE, normalized(report))
    return dict(path=str(output/GATE_FILE), ok=report['ok'], status=status)


def read_gate(path, kind, stage, ctx):
    path = Path(path)
    report = oc.read_json(path)
    require(report.get('format') == GATE_FORMAT and report.get('kind') == kind and report.get('stage') == stage,
            f'{path} is not gate {kind} of stage {stage}')
    require(report['prereg_sha256'] == ctx.prereg_sha256, 'Gate ran under another prereg')
    for name, digest in report['files'].items():
        require(oc.sha256_file(from_rel(name)) == digest, f'File changed since the gate: {name}')
    return report


# =============================================================================== holdout-open and holdout (§2.5, §10)

def quote_time_iso(value):
    """The time of the owner quote: ISO 8601 with a UTC offset; returned as given."""
    require(isinstance(value, str) and value.strip(), 'The date and time of the quote are required')
    try:
        parsed = _dt.datetime.fromisoformat(value.strip())
    except ValueError:
        raise ContractError(f'Quote time is not ISO 8601: {value!r}') from None
    require(parsed.tzinfo is not None, f'Quote time needs a UTC offset: {value!r}')
    return value.strip()


def holdout_open(ctx, gate_path, quote=None, quote_time=None, covers_stage2=False, stage=1):
    """Write the open receipt of stage 1 or 2 after re-checking gate 1 from the files."""
    stage = int(stage)
    kind = 'holdout-open' if stage == 1 else 'holdout-open-2'
    path = oc.config_path(kind)
    require(not path.exists() and not ever_committed(path), f'{path.name} exists or was committed; it is written once')
    if stage == 2:
        require(oc.committed_clean(oc.config_path('holdout')), 'Stage 2 opens after the committed stage-1 result')
    gate_path = Path(gate_path)
    record = read_gate(gate_path, '1', stage, ctx)
    leak = [from_rel(r['path']) for r in record['checks']['leakcheck'].get('reports', [])]
    checks, files = gate1_checks(ctx, stage, leak)
    require(checks == record['checks'] and files == record['files'], 'Gate 1 differs from a recomputation')
    status = gate1_status(checks)
    require(status == record['status'], 'Gate 1 status differs from its checks')
    arms = opened_arms(status)
    gate_ref = dict(ok=record['ok'], status=status, path=rel(gate_path), sha256=oc.sha256_file(gate_path))
    if stage == 1:
        require(isinstance(quote, str) and quote.strip(), 'The owner quote is required')
        quote_time = quote_time_iso(quote_time)
        power = power_gate_report()
        body = dict(format=oc.HOLDOUT_OPEN_FORMAT, quote=quote, quote_time=quote_time,
                    covers_stage2=bool(covers_stage2), gate1=gate_ref, arms=arms, score_files=files,
                    population=power['population'], prereg_sha256=ctx.prereg_sha256, opened_utc=oc.utc_now())
    else:
        first = oc.receipt('holdout-open')
        if quote is None:
            require(first.get('covers_stage2'), 'The stage-1 quote does not name stage 2: a new quote is required')
            quote_ref = dict(source='holdout-open', quote=first['quote'], quote_time=first['quote_time'])
        else:
            require(quote.strip(), 'The owner quote is required')
            quote_ref = dict(source='stage-2 question', quote=quote, quote_time=quote_time_iso(quote_time))
        arms = [a for a in arms if a in first['arms']]
        scores = {name: digest for name, digest in {**first['score_files'], **files}.items()}
        body = dict(format=oc.HOLDOUT_OPEN_2_FORMAT, quote=quote_ref, gate1=gate_ref, arms=arms, scores=scores,
                    population=first['population'], prereg_sha256=ctx.prereg_sha256, opened_utc=oc.utc_now())
    oc.check_receipt(kind, body)
    oc.atomic_json(path, normalized(body))
    return dict(path=rel(path), arms=arms, gate_ok=record['ok'])


def holdout_inputs(receipt, pinned, arms, seeds):
    """Evaluations of each (arm, seed) whose files and population match the open receipt (before any label)."""
    reports = {}
    for seed in seeds:
        for arm in arms:
            d, r = load_eval('holdout', arm, seed)
            for name, digest in ((rel(d/RANKED_FILE), r['ranked']['sha256']),
                                 (rel(d/REPORT_FILE), oc.sha256_file(d/REPORT_FILE))):
                require(pinned.get(name) == digest, f'{name} is not the file pinned by the open receipt')
            require((r['population'].get('power_gate') or {}).get('digest') == receipt['population']['digest'],
                    'Evaluation on another population than the one pinned by the open receipt')
            reports[(arm, seed)] = (d, r)
    r0 = reports[('B', seeds[0])][1]
    require(pinned.get(r0['pop']['path']) == r0['pop']['sha256'] == oc.sha256_file(from_rel(r0['pop']['path'])),
            'Pop lists are not the file pinned by the open receipt')
    return reports


def mean_diff(results, seeds, part=None):
    values = [(results[str(s)]['types'][part] if part else results[str(s)])['diff'] for s in seeds]
    return sum(values)/len(values)


def holdout(ctx, stage=1, output=None):
    """Read the holdout once per stage (§2.5, §10): metrics, D and P with CIs, verdicts, the result receipt.

    Every check that needs no label runs first: receipts, the window, evaluations, pins and the
    population. Then ``stageN-<stamp>/started.json`` is written and only then the labels are read,
    so a run that reached the labels always leaves a trace and is not repeated.
    """
    stage = int(stage)
    kind = 'holdout' if stage == 1 else 'holdout-2'
    path = oc.config_path(kind)
    require(not path.exists() and not ever_committed(path), f'{path.name} exists or was committed; holdout runs once')
    root = oc.output_dir('holdout')
    earlier = sorted(p.name for p in root.iterdir() if p.name.startswith(f'stage{stage}-')) if root.exists() else []
    require(not earlier, f'An earlier stage-{stage} holdout run exists: {earlier}')
    require(oc.holdout_window_open(kind), f'Holdout window {kind!r} is closed: it needs committed '
                                          f'{", ".join(oc.SEALED_PURPOSES[kind])}')
    collection = ctx.collection(4)
    first = oc.receipt('holdout-open')
    receipt = first if stage == 1 else oc.receipt('holdout-open-2')
    pinned = receipt['score_files'] if stage == 1 else receipt['scores']
    population = oc.read_population(collection, expected_digest=first['population']['digest'])
    arms = list(receipt['arms'])
    require('B' in arms, 'The open receipt does not name B')
    seeds = oc.STAGE_SEEDS[stage]
    reports = holdout_inputs(first, pinned, arms, seeds)
    open_sha = oc.sha256_file(oc.config_path('holdout-open' if stage == 1 else 'holdout-open-2'))
    output = oc.new_output(output if output is not None else root/f'stage{stage}-{stamp()}')
    oc.atomic_json(output/STARTED_FILE, dict(stage=stage, arms=arms, seeds=list(seeds), open_receipt_sha256=open_sha,
                                             population=first['population'], started_utc=oc.utc_now()))
    labels_path = oc.read_sealed(collection, kind)['labels']
    values = {key: oc.metric(d/RANKED_FILE, labels_path, sessions=population, threads=ctx.threads)
              for key, (d, _) in reports.items()}
    pop = pop_metric(ctx.threads, reports[('B', seeds[0])][1], labels_path, population)
    result = dict(format=RESULT_FORMAT, stage=stage, seeds=list(seeds), arms=arms, collection=collection.name,
                  population=first['population'], open_receipt_sha256=open_sha, prereg_sha256=ctx.prereg_sha256,
                  metrics={f'{a}{s}': dict(recall=v['recall'], score=v['score']) for (a, s), v in values.items()},
                  pop=dict(recall=pop['recall'], score=pop['score']))
    if arms == list(oc.ARMS):
        D = {str(s): oc.bootstrap_ratio(values[('B', s)], values[('BA', s)]) for s in seeds}
        P = {str(s): oc.bootstrap_ratio(values[('BApl', s)], values[('BA', s)]) for s in seeds}
        L = {str(s): oc.bootstrap_ratio(values[('B', s)], values[('BApl', s)]) for s in seeds}
        result.update(D=D, P=P, BApl_minus_B=L,
                      verdict_transfer=oc.verdict_transfer({s: D[str(s)]['ci'] for s in seeds}, stage),
                      verdict_content=oc.verdict_content({s: P[str(s)]['ci'] for s in seeds}, stage))
        if stage == 1:
            result['note'] = oc.stage1_note(D[str(seeds[0])]['ci'])
        else:
            result['seed_mean'] = dict(
                D=mean_diff(D, seeds), P=mean_diff(P, seeds), BApl_minus_B=mean_diff(L, seeds),
                types={t: dict(D=mean_diff(D, seeds, t), P=mean_diff(P, seeds, t), BApl_minus_B=mean_diff(L, seeds, t))
                       for t in oc.TYPES})
    else:
        result['ba'] = 'BA или BApl не прошли гейт 1 или BA не выполнена'
        result['verdict_transfer'] = oc.verdict_transfer(None, stage)
        result['verdict_content'] = oc.verdict_content(None, stage)
    con = connect(ctx)
    try:
        register_sessions(con, 'population', population)
        result['ceiling'] = {}
        for arm in ('B', 'BA') if 'BA' in arms else ('B',):
            arm_view(con, ctx, collection, arm, name='cv')
            result['ceiling'][arm] = ceiling(con, 'cv', labels_path, 'population')
    finally:
        con.close()
    result.update(code=ctx.code, created_utc=oc.utc_now())
    result = normalized(result)
    oc.atomic_json(output/'result.json', result)
    oc.atomic_json(path, result)
    return dict(path=rel(path), verdict_transfer=result['verdict_transfer'],
                verdict_content=result['verdict_content'], metrics=result['metrics'])


# =============================================================================== score and reading (§9, §10)

def score(ctx, arm, seed):
    """Final-series ranked lists of F5 for otto_data.assemble (§9); nothing is assembled or submitted here.

    The returned ``assemble`` command uses absolute paths, so it runs from any directory.
    """
    require(arm in ('B', 'BA'), 'Kaggle files are B and BA only (§9)')
    arm_stage('final', arm, seed)
    report = evaluate(ctx, 'final', arm, seed)
    target = kaggle_file(arm, seed)
    ranked = Path(report['path'])/RANKED_FILE
    root = oc.ROOT.resolve()
    command = [str(root/'.venv'/'bin'/'python'), '-I', str(root/'scripts'/'otto_data.py'), 'assemble',
               '--ranked', str(ranked.resolve()), '--output', str(target.resolve())]
    return dict(ranked=rel(ranked), sha256=report['ranked']['sha256'], finite=report['finite_all'],
                short_lists=report['short_lists'], topped_sessions=report['topped_sessions'],
                assemble=command, output=rel(target))


def passing_gate2():
    """{'B2026': True, ...} from the gate 2 reports on disk (latest per stage)."""
    root = oc.output_dir('gate')
    out = {}
    for stage in (1, 2):
        dirs = sorted(p for p in root.iterdir() if p.name.startswith(f'gate2-s{stage}-')) if root.exists() else []
        if dirs:
            report = oc.read_json(dirs[-1]/GATE_FILE)
            seed = oc.SEEDS[stage-1]
            out.update({f'{arm}{seed}': bool(ok) for arm, ok in report['status'].items()})
    return out


def reading(private, passed=None, output=None):
    """Kaggle reading (§10): BA against B (H&M rule) and the level of BA files that passed gate 2."""
    text = str(private)
    data = json.loads(text) if text.lstrip().startswith('{') else oc.read_json(text)
    scores = {k: float(v) for k, v in data.items()}
    unknown = sorted(set(scores) - set(KAGGLE_KEYS))
    require(not unknown, f'Only {KAGGLE_KEYS} are submitted (§9); not read: {unknown}')
    passed = passing_gate2() if passed is None else passed
    failed = sorted(k for k in scores if not passed.get(k))
    require(not failed, f'Files without gate 2: {failed}')
    ba = [scores[f'BA{s}'] for s in oc.SEEDS if f'BA{s}' in scores]
    b = [scores[f'B{s}'] for s in oc.SEEDS if f'B{s}' in scores]
    result = dict(format=READING_FORMAT, private=scores, descriptive=True,
                  comparison=oc.kaggle_reading(ba, b),
                  difference={str(s): scores[f'BA{s}']-scores[f'B{s}'] for s in oc.SEEDS
                              if f'BA{s}' in scores and f'B{s}' in scores},
                  level=oc.level_reading(ba) if ba else None, level_B=oc.level_reading(b) if b else None,
                  created_utc=oc.utc_now())
    output = oc.new_output(output if output is not None else oc.output_dir('kaggle', f'reading-{stamp()}'))
    oc.atomic_json(output/'reading.json', normalized(result))
    return dict(path=rel(output/'reading.json'), comparison=result['comparison'], level=result['level'])


# =============================================================================== smoke (§6, §12)

def smoke(ctx, output=None, noise=SMOKE_NOISE, type_=SMOKE_TYPE):
    """One orders fit of the BA shape on F2: base features + noise columns, rows of B; bootstrap and time."""
    import numpy as np
    from catboost import CatBoost, CatBoostError, Pool
    require(ctx.mode == 'smoke', 'smoke runs in smoke mode, before prereg')
    output = oc.new_output(output if output is not None else oc.output_dir('smoke', stamp()))
    collection = ctx.collection(2)
    con = connect(ctx)
    try:
        labels_view(con, collection/oc.LABELS_FILE)
        arm_view(con, ctx, collection, 'B')
        chosen = training_sessions(con, 'lab', ctx.n_t)
        block, dropped = training_rows(con, 'fr', 'lab', type_, chosen[type_], ctx.features, ctx.negatives)
    finally:
        con.close()
    x = feature_matrix(block, ctx.features)
    rng = np.random.default_rng(oc.SEEDS[0])
    x = np.hstack([x, rng.standard_normal((len(block), int(noise)), dtype=np.float32)])
    names = list(ctx.features) + [f'noise_{i}' for i in range(int(noise))]
    pool = Pool(x, label=block['label'].to_numpy(), group_id=block['session'].to_numpy(), feature_names=names)
    tried = []
    for bootstrap in (DEFAULT_BOOTSTRAP, FALLBACK_BOOTSTRAP):
        recipe = dict(ctx.recipe(oc.SEEDS[0]), bootstrap_type=bootstrap)
        tick = time.monotonic()
        try:
            model = CatBoost(recipe)
            model.fit(pool, verbose=False)
        except CatBoostError as exc:
            tried.append(dict(bootstrap_type=bootstrap, error=str(exc)[:500]))
            continue
        seconds = round(time.monotonic()-tick, 3)
        tried.append(dict(bootstrap_type=bootstrap, seconds=seconds, trees=int(model.tree_count_)))
        break
    else:
        raise ContractError(f'No bootstrap type fits YetiRank: {tried}')
    result = dict(format=SMOKE_FORMAT, type=type_, rows=int(len(block)), sessions=len(chosen[type_]),
                  dropped_sessions=int(dropped), columns=len(names), noise=int(noise), recipe=recipe,
                  bootstrap_type=bootstrap, tried=tried, seconds=seconds, limit_seconds=SMOKE_LIMIT_SECONDS,
                  N_t=ctx.n_t if seconds <= SMOKE_LIMIT_SECONDS else SMOKE_REDUCED_N_T, code=ctx.code,
                  created_utc=oc.utc_now())
    oc.atomic_json(output/'smoke.json', normalized(result))
    return dict(path=rel(output/'smoke.json'), bootstrap_type=bootstrap, seconds=seconds, N_t=result['N_t'])


def prereg_rules(smoke_json):
    """Model rules the prereg records (§7), with bootstrap_type and N_t of the smoke run (§12).

    The committed set must carry an audit with verdict clean, and ``smoke_json`` must be the
    smoke result the agent run of that set used: run/run-<set.run.id>/run.json has the SHA-256
    ``set.run_sha256`` and names ``smoke.sha256`` of this file (N_t of the prompt = N_t of the prereg).
    The prereg command itself is the coordinator's; ``Context.contract`` reads back
    ``recipe.bootstrap_type``, ``N_t`` and ``SCORE_BATCH``.
    """
    smoke_json = Path(smoke_json)
    data = oc.read_json(smoke_json)
    require(data.get('format') == SMOKE_FORMAT, f'{smoke_json} is not a smoke result')
    require(data.get('bootstrap_type') in (DEFAULT_BOOTSTRAP, FALLBACK_BOOTSTRAP), 'Smoke names no bootstrap type')
    require(int(data.get('N_t', 0)) in (oc.N_T, SMOKE_REDUCED_N_T), f'Smoke N_t {data.get("N_t")} is not allowed')
    smoke_sha = oc.sha256_file(smoke_json)
    agent_set = oc.receipt('set')
    oc.require_clean_audit(agent_set)
    run_id = (agent_set.get('run') or {}).get('id')
    require(isinstance(run_id, str) and run_id, 'The committed set names no run')
    run_json = oc.output_dir('run', oc.output_name(f'run-{run_id}'))/'run.json'
    require(run_json.is_file() and oc.sha256_file(run_json) == agent_set.get('run_sha256'),
            f'{rel(run_json)} is not the run.json the set was frozen from (run_sha256)')
    run_smoke = oc.read_json(run_json).get('smoke') or {}
    require(run_smoke.get('sha256') == smoke_sha,
            f'{smoke_json} is not the smoke result of run {run_id} (run.json smoke.sha256)')
    return normalized(dict(recipe=dict(RECIPE, bootstrap_type=data['bootstrap_type']),
                           smoke=dict(path=rel(smoke_json), sha256=smoke_sha, seconds=data.get('seconds'),
                                      run=run_id),
                           prediction_type=PREDICTION_TYPE, negatives=NEGATIVE_RULE,
                           N_t=int(data['N_t']), SCORE_BATCH=oc.SCORE_BATCH, permutation=PERMUTATION_RULE,
                           parity=list(PARITY),
                           power=dict(cap=oc.HOLDOUT_POPULATION_CAP, half_width=oc.POWER_HALF_WIDTH),
                           top_k=oc.TOP_K, threads=dict(catboost=RECIPE['thread_count'], duckdb=DUCKDB_THREADS),
                           memory=DUCKDB_MEMORY))


# =============================================================================== CLI

def parser():
    p = Parser(prog='otto_model.py', description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='command', required=True)

    c = sub.add_parser('fit')
    c.add_argument('--series', choices=tuple(oc.SERIES))
    c.add_argument('--arm', choices=oc.ARMS)
    c.add_argument('--seed', type=int)
    c.add_argument('--base-dev', metavar='NAME')
    c.add_argument('--base')
    c.add_argument('--bootstrap', default=DEFAULT_BOOTSTRAP)
    c = sub.add_parser('final-sessions')
    c.add_argument('--name')
    c = sub.add_parser('smoke')
    c.add_argument('--base')
    c.add_argument('--bootstrap', default=DEFAULT_BOOTSTRAP)
    c = sub.add_parser('evaluate')
    c.add_argument('--series', choices=tuple(oc.SERIES), required=True)
    c.add_argument('--arm', choices=oc.ARMS, required=True)
    c.add_argument('--seed', type=int, required=True)
    sub.add_parser('contrast')
    c = sub.add_parser('gate')
    c.add_argument('--kind', choices=GATE_KINDS, required=True)
    c.add_argument('--stage', type=int, choices=(1, 2), default=1)
    c.add_argument('--leakcheck', nargs='*', default=[])
    c.add_argument('--contrast')
    c = sub.add_parser('holdout-open')
    c.add_argument('--gate', required=True)
    c.add_argument('--stage', type=int, choices=(1, 2), default=1)
    c.add_argument('--quote')
    c.add_argument('--quote-time')
    c.add_argument('--covers-stage2', action='store_true')
    c = sub.add_parser('holdout')
    c.add_argument('--stage', type=int, choices=(1, 2), default=1)
    c = sub.add_parser('score')
    c.add_argument('--arm', choices=('B', 'BA'), required=True)
    c.add_argument('--seed', type=int, required=True)
    c = sub.add_parser('reading')
    c.add_argument('--private', required=True)
    return p


def cmd_fit(args):
    if args.base_dev:
        oc.output_name(args.base_dev)
        require(args.base, 'Base-dev needs --base')
        require(args.series in (None, 'dev') and args.arm in (None, 'B') and args.seed in (None, oc.SEEDS[0]),
                'Base-dev is dev B2026')
        ctx = Context.before_prereg(oc.read_base(args.base), 'base-dev', args.bootstrap)
        directory = oc.output_dir('base-dev', oc.output_name(args.base_dev))
        report = fit(ctx, 'dev', 'B', oc.SEEDS[0], output=directory)
        ev = evaluate(ctx, 'dev', 'B', oc.SEEDS[0], fit_directory=directory)
        return dict(path=rel(directory), training={t: r['rows'] for t, r in report['training'].items()},
                    metrics=ev.get('metrics'), ceiling=ev.get('ceiling'))
    require(args.series and args.arm and args.seed is not None, 'fit needs --series, --arm and --seed')
    require(not args.base, 'Only base-dev takes --base')
    ctx = Context.contract()
    report = fit(ctx, args.series, args.arm, args.seed)
    return dict(path=rel(report['path']), training={t: dict(rows=r['rows'], dropped_sessions=r['dropped_sessions'])
                                                    for t, r in report['training'].items()})


def cmd_evaluate(args):
    ctx = Context.contract()
    report = evaluate(ctx, args.series, args.arm, args.seed)
    return dict(path=rel(report['path']), finite=report['finite_all'], short_lists=report['short_lists'],
                topped_sessions=report['topped_sessions'], metrics=report.get('metrics'))


def cmd_gate(a):
    """CLI gate: the gate verdict goes out as ``passed``; ``ok`` belongs to the CLI line (deviation d2)."""
    result = dict(gate(Context.contract(), a.kind, a.stage, a.leakcheck, a.contrast))
    if 'ok' in result:
        result['passed'] = result.pop('ok')
    return result


COMMANDS = {
    'fit': cmd_fit,
    'final-sessions': lambda a: final_sessions(Context.contract(), a.name),
    'smoke': lambda a: smoke(Context.before_prereg(oc.read_base(a.base), 'smoke', a.bootstrap)),
    'evaluate': cmd_evaluate,
    'contrast': lambda a: contrast(Context.contract()),
    'gate': cmd_gate,
    'holdout-open': lambda a: holdout_open(Context.contract(), a.gate, a.quote, a.quote_time, a.covers_stage2,
                                           a.stage),
    'holdout': lambda a: holdout(Context.contract(), a.stage),
    'score': lambda a: score(Context.contract(), a.arm, a.seed),
    'reading': lambda a: reading(a.private),
}


def handle(argv=None):
    oc.isolated()
    args = parser().parse_args(argv)
    with quiet_stdout():
        return dict(command=args.command, **COMMANDS[args.command](args))


def main(argv=None):
    return oc.run_cli(handle, argv)


if __name__ == '__main__':
    raise SystemExit(main())
