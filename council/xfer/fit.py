"""One council fit on an xfer dataset by a JSON spec (council/runs/xfer/contract.md §3.1), in its own process
(`python -I council/xfer/run.py --dataset <x> fit-one --spec f.json --stamp ... --data ...`, started by
council.xfer.queue.run). The only caller of xm.training_block in the council; it writes scores, never a quality value.

Spec (normalized by validate, keys in SPEC_KEYS order):

  {"name": "plan-r07-1007", "phase": "plan", "arm": "r07", "seed": 1007, "half": "B",
   "tables": ["g1_1", "g2_3_tw", "rb1_cooc_decay"],
   "placebo": {"tables": ["g3_2"], "columns": ["ag_c3_bridge_share"]} | null,
   "selection_sha256": null}

  name              f'{phase}-{arm}-{seed}' (validate checks it).
  phase             a key of PHASES: the series (roles.SERIES), the half of the scored users and the seeds allowed.
  arm               'Hr', 'Hrp', 'ALLP', 'SEL', 'TWIN', 'Rb1', 'Rb2' or 'r01'..'r48' (plan rows).
  seed              CatBoost seed: roles.PATH_SEED for path_*, roles.NOISE_SEEDS, roles.plan_seed(r),
                    roles.CONFIRM_SEEDS, the seeds of roles.TEST_FITS[arm] for phase test.
  half              None (every S0 or C_test user) or 'A'/'B' (S0 users with roles.half(user_id) == half); when
                    the spec leaves it out, validate takes PHASES[phase]['half'].
  tables            council tables joined on top of H+r = the BA block of xfer (base + the frozen xfer agent set);
                    each is artifacts/council/xfer-<x>/sidecars/<collection>/<table>.parquet written by compute.py.
                    Arm Hr has none (and no placebo).
  placebo           columns of those tables (or of tables only the placebo uses) copied to roles.placebo_column(c)
                    and permuted within each anchor with numpy.random.default_rng(roles.placebo_key(anchor)); the
                    original columns of a placebo-only table are dropped.
  selection_sha256  phase test only: sha256 of council/runs/xfer-<x>/selection.json as recorded in the
                    test.started marker (read through council.xfer.marker; fit.py never imports the broker,
                    §10.4); validate refuses a test spec without the marker or with another sha.
  Phase confirm takes the arms ALLP and SEL only; a placebo belongs to phase plan only (§10.6).

What a fit does (run):
  1. stamps: the code identity (roles.identity: xc.code_identity + council stamp) and data_stamp(spec) equal to
     the ones the queue took; xm.recipe_for(seed) == roles.recipe_for(seed).
  2. ctx = xm.Context(ds.name) (the xfer prereg guard); con = xm.connect().
  3. per training anchor of the series (Dataset.training_collections of the series key):
     block, population, _, _, _ = xm.training_block(ctx, con, series, anchor, 'BA', seed); population['rows_sha256']
     must equal the one of the same anchor in the xfer report fits/<series>/BA2026/report.json
     (xm.fit_dir(ds.name, series, 'BA', 2026)) - else stop. The target column and row weights of the pool are
     taken from the training_block result before anything is joined. The council columns are joined to the block
     by (user_id, item_id) with council_join (missing pair -> NaN); the placebo permutes; matrices with
     xm.matrices(ctx, frame, agent + council columns).
  4. model = CatBoostClassifier(**xm.recipe_for(seed)).fit(xm.make_pool(...)).
  5. scoring: the eval collection of the series (Dataset.collection('select') or Dataset.collection('test')),
     xm.frame_rows + xm.with_agent (xfer sidecar of that collection) + council_join + placebo over the whole frame
     (the permutation does not depend on the half), then only the users of `half`; xm.predict -> scores.
  6. writes roles.Paths.scores(phase, arm, seed) = artifacts/council/xfer-<x>/fits/<phase>/<arm>-<seed>/
     scores.parquet with SCORE_COLUMNS, ordered user_id, item_id, atomically and never over an existing file; then
     one record line in artifacts/council/xfer-<x>/fits/runs.jsonl (RECORD_KEYS). Nothing about quality is computed
     or printed: top-K and per-query values are the broker's.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from council.xfer import marker, roles
from scripts import xfer_common as xc
from scripts import xfer_model as xm

SPEC_KEYS = ('name', 'phase', 'arm', 'seed', 'half', 'tables', 'placebo', 'selection_sha256')
OPTIONAL = {'half': None, 'tables': [], 'placebo': None, 'selection_sha256': None}
PHASES = {                          # phase -> council series key of roles.SERIES and the half of the scored users
    'path_select': {'series': 'select', 'half': None},
    'path_test': {'series': 'test', 'half': None},
    'noise': {'series': 'select', 'half': roles.EXPLORE},
    'plan': {'series': 'select', 'half': roles.SELECT},
    'confirm': {'series': 'select', 'half': roles.SELECT},
    'test': {'series': 'test', 'half': None},
}
SCORE_COLUMNS = ('qid', 'user_id', 'item_id', 'score')
RECORD_KEYS = ('name', 'spec', 'series', 'identity', 'data', 'recipe', 'features', 'council_columns',
               'placebo_columns', 'populations', 'eval', 'peak_rss_gb', 'commit', 'dirty', 'started', 'seconds')
TRAIN_ARM = 'BA'                    # the xfer arm whose rows and block every council arm starts from
REFERENCE_SEED = 2026               # the xfer fit whose rows_sha256 every council fit must reproduce
HR = 'Hr'                           # H+r: the BA block alone
PLAN_ARM = re.compile(r'r([0-9]{2})')
TABLE = re.compile(r'g[1-4]_[0-9]+(_tw)?|rb[12]_[a-z][a-z0-9_]*')
SHA = re.compile(r'[0-9a-f]{64}')
KEYS = ['user_id', 'item_id']
CONFIRM_ARMS = ('ALLP', 'SEL')     # ALL_P and ALL_P minus D (§10.6)
REPORT = 'report.json'              # the xfer fit report (only its training row digests are read here)


# ---------------------------------------------------------------- spec

def _seeds(phase: str, arm: str) -> tuple:
    """Seeds allowed for (phase, arm); ValueError for an arm the phase does not take."""
    if phase in ('path_select', 'path_test'):
        if arm != HR:
            raise ValueError(f'phase {phase} fits arm {HR} only, got {arm!r}')
        return (roles.PATH_SEED,)
    if phase == 'noise':
        if arm != HR:
            raise ValueError(f'phase noise fits arm {HR} only, got {arm!r}')
        return tuple(roles.NOISE_SEEDS)
    if phase == 'plan':
        m = PLAN_ARM.fullmatch(arm)
        if not m or not 1 <= int(m.group(1)) <= roles.PLAN_RUNS:
            raise ValueError(f'phase plan fits arms r01..r{roles.PLAN_RUNS:02d}, got {arm!r}')
        return (roles.plan_seed(int(m.group(1))),)
    if phase == 'confirm':
        if arm not in CONFIRM_ARMS:
            raise ValueError(f'phase confirm fits an arm of {CONFIRM_ARMS}, got {arm!r}')
        return tuple(roles.CONFIRM_SEEDS)
    fits = dict(roles.TEST_FITS) | dict(roles.TEST_FITS_ALLP)
    if arm not in fits:
        raise ValueError(f'phase test fits an arm of {sorted(fits)}, got {arm!r}')
    return tuple(fits[arm])


def _names(x, what: str, name: str, pattern=None) -> list[str]:
    if not isinstance(x, list) or not all(isinstance(v, str) for v in x) or len(set(x)) != len(x):
        raise ValueError(f'{name}: {what} must be a list of distinct strings')
    if pattern is not None:
        bad = [v for v in x if not pattern(v)]
        if bad:
            raise ValueError(f'{name}: {what} {bad[:3]} are not council names')
    return list(x)


def _placebo_name_ok(c: str) -> bool:
    return not c.startswith(roles.PLACEBO_PREFIX) and bool(
        roles.CARD_COLUMN.fullmatch(c) or roles.RB_COLUMN.fullmatch(c))


def validate(ds: roles.Dataset, spec: dict) -> dict:
    """The normalized spec (every key of SPEC_KEYS, defaults from OPTIONAL, half from the phase) or ValueError
    before any data is read. Checks: name == f'{phase}-{arm}-{seed}'; phase in PHASES; half equals
    PHASES[phase]['half']; seed allowed for the phase and arm (see the module docstring); tables are distinct names
    of family/twin/Rb tables (roles.family_table/twin_table/rb_table forms); arm Hr has no tables and no placebo;
    placebo columns are council column names (not already placebo names) of placebo tables; selection_sha256 only
    and always for phase test, and the test.started marker in ds.paths.reads names the same sha."""
    if not isinstance(spec, dict):
        raise ValueError('a spec is a JSON object')
    name = spec.get('name')
    if not isinstance(name, str) or not name:
        raise ValueError(f'name {name!r} is not a string')
    unknown = sorted(set(spec) - set(SPEC_KEYS))
    missing = sorted(set(SPEC_KEYS) - set(OPTIONAL) - set(spec))
    if unknown or missing:
        raise ValueError(f'{name}: unknown keys {unknown}, missing keys {missing}')
    phase = spec['phase']
    if not isinstance(phase, str) or phase not in PHASES:
        raise ValueError(f'{name}: phase {phase!r} not in {sorted(PHASES)}')
    s = {k: spec.get(k, PHASES[phase]['half'] if k == 'half' else OPTIONAL.get(k)) for k in SPEC_KEYS}
    if not isinstance(s['arm'], str):
        raise ValueError(f"{name}: arm {s['arm']!r} is not a string")
    seed = s['seed']
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError(f'{name}: seed {seed!r} is not an integer')
    if name != f"{phase}-{s['arm']}-{seed}":
        raise ValueError(f"{name}: the name must be {phase}-{s['arm']}-{seed}")
    if s['half'] != PHASES[phase]['half']:
        raise ValueError(f"{name}: phase {phase} scores half {PHASES[phase]['half']!r}, got {s['half']!r}")
    allowed = _seeds(phase, s['arm'])
    if seed not in allowed:
        raise ValueError(f"{name}: seed {seed} is not allowed for {phase}/{s['arm']} (allowed {list(allowed)})")
    s['tables'] = _names(s['tables'], 'tables', name, TABLE.fullmatch)
    pl = s['placebo']
    if pl is not None:
        if not isinstance(pl, dict) or set(pl) != {'tables', 'columns'}:
            raise ValueError(f'{name}: placebo is null or {{"tables": [...], "columns": [...]}}')
        tables = _names(pl['tables'], 'placebo tables', name, TABLE.fullmatch)
        columns = _names(pl['columns'], 'placebo columns', name, _placebo_name_ok)
        if not tables or not columns:
            raise ValueError(f'{name}: a placebo needs tables and columns')
        s['placebo'] = {'tables': tables, 'columns': columns}
    if s['placebo'] is not None and phase != 'plan':
        raise ValueError(f'{name}: a placebo belongs to phase plan only')
    if s['arm'] == HR and (s['tables'] or s['placebo']):
        raise ValueError(f'{name}: arm {HR} is the BA block alone (no tables, no placebo)')
    sha = s['selection_sha256']
    if phase == 'test':
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError(f'{name}: phase test needs selection_sha256 (64 hex digits)')
        mark = marker.marker(ds)
        if mark is None:
            raise ValueError(f'{name}: phase test needs the test.started marker in {ds.paths.reads}')
        if mark.get('selection_sha256') != sha:
            raise ValueError(f'{name}: selection_sha256 differs from the test.started marker')
    elif sha is not None:
        raise ValueError(f'{name}: selection_sha256 belongs to phase test only')
    return s


def series_key(phase: str) -> str:
    """'select' or 'test': the council key of roles.SERIES behind a phase."""
    return PHASES[phase]['series']


def series_of(phase: str) -> str:
    """The xfer series name of a phase: roles.SERIES[PHASES[phase]['series']]."""
    return roles.SERIES[series_key(phase)]


def _spec(phase: str, arm: str, seed: int) -> dict:
    return {'name': f'{phase}-{arm}-{seed}', 'phase': phase, 'arm': arm, 'seed': int(seed),
            'half': PHASES[phase]['half'], 'tables': [], 'placebo': None, 'selection_sha256': None}


def path_specs(ds: roles.Dataset) -> list[dict]:
    """The two path checks of prereg-0: H+r (tables []), seed roles.PATH_SEED, phases path_select (T_fit -> every
    S0 user) and path_test (training rows of the test series -> every C_test user); broker.path_check reads them."""
    return [validate(ds, _spec(p, HR, roles.PATH_SEED)) for p in ('path_select', 'path_test')]


def noise_specs(ds: roles.Dataset) -> list[dict]:
    """The two noise fits of prereg-0: H+r, phase noise (half A), seeds roles.NOISE_SEEDS."""
    return [validate(ds, _spec('noise', HR, s)) for s in roles.NOISE_SEEDS]


# ---------------------------------------------------------------- stamps

def code_stamp(ds: roles.Dataset) -> dict:
    """roles.identity(ds): {'code': xc.code_identity, 'council': council stamp}; a fit starts and ends with it."""
    return roles.identity(ds)


def prereg_identity(ds: roles.Dataset) -> dict | None:
    """The identity recorded in prereg-0.json of the dataset ('identity', written by plan.prereg0), or None before
    prereg-0 exists. Once it exists, every fit must run with it (contract §3 rule 3, §8.3)."""
    path = ds.paths.prereg(0)
    if not path.exists():
        return None
    ident = xc.read_json(path).get('identity')
    if not isinstance(ident, dict):
        raise SystemExit(f'{path} has no identity stamp')
    return ident


def check_stamp(ds: roles.Dataset, stamp: dict, name: str) -> None:
    """SystemExit if the stamp differs from the identity of prereg-0 (when it exists)."""
    ref = prereg_identity(ds)
    if ref is not None and ref != stamp:
        raise SystemExit(f'{name}: the code identity differs from the one of prereg-0')


_SHA_MEMO: dict = {}


def file_sha(path, cache: bool = True) -> str:
    """sha256 of a file, memoized per (path, size, mtime_ns) inside the process (data stamps repeat files);
    cache=False hashes the bytes again (the control after a fit, §10.9)."""
    path = Path(path)
    if not cache:
        return xc.sha256_file(path)
    st = path.stat()
    key = (str(path.resolve()), st.st_size, st.st_mtime_ns)
    if key not in _SHA_MEMO:
        _SHA_MEMO[key] = xc.sha256_file(path)
    return _SHA_MEMO[key]


def collections_of(ds: roles.Dataset, spec: dict) -> list[tuple]:
    """[(anchor, collection dir)] a spec reads: the training anchors of its series, then the eval collection."""
    key = series_key(spec['phase'])
    return list(ds.training_collections(key)) + [(ds.series(key)['eval'], Path(ds.collection(key)))]


def placebo_only(spec: dict) -> list[str]:
    """Tables the placebo uses that are not among the spec's tables (their own columns are dropped)."""
    return [t for t in (spec['placebo'] or {}).get('tables', []) if t not in spec['tables']]


def joined_tables(spec: dict) -> list[str]:
    """The spec's tables, then the tables only the placebo uses."""
    return list(spec['tables']) + placebo_only(spec)


def data_stamp(ds: roles.Dataset, spec: dict, cache: bool = True) -> dict:
    """Fingerprint of what a normalized spec reads, taken before the fit and compared after it:
    {'collections': {name: manifest sha256} of the training and eval collections,
     'sidecars': {name: xfer sidecar manifest sha256} of the same collections,
     'tables': {collection: {table: file sha256}} of the spec's council tables and placebo tables,
     'selection_sha256': spec['selection_sha256']}. ValueError if a council table file is missing. cache=False
    rehashes every file (the control after the fit)."""
    out = {'collections': {}, 'sidecars': {}, 'tables': {}, 'selection_sha256': spec['selection_sha256']}
    tables = joined_tables(spec)
    for _, path in collections_of(ds, spec):
        path = Path(path)
        out['collections'][path.name] = file_sha(path / xc.MANIFEST_FILE, cache)
        out['sidecars'][path.name] = file_sha(Path(xc.sidecar_dir(ds.name, path)) / xc.MANIFEST_FILE, cache)
        if tables:
            files = {t: ds.paths.table(path.name, t) for t in tables}
            lost = [t for t, f in files.items() if not f.exists()]
            if lost:
                raise ValueError(f"{spec['name']}: council tables {lost[:3]} of {path.name} are not computed")
            out['tables'][path.name] = {t: file_sha(f, cache) for t, f in files.items()}
    return out


# ---------------------------------------------------------------- council columns

def table_manifest(ds: roles.Dataset, collection) -> dict:
    """The compute.py manifest of one collection (sidecars/<collection>/manifest.json); ValueError if absent."""
    path = ds.paths.sidecars / Path(collection).name / xc.MANIFEST_FILE
    if not path.exists():
        raise ValueError(f'{path} is missing: compute has not written the council tables of {Path(collection).name}')
    return xc.read_json(path)


def table_columns(ds: roles.Dataset, collection, table: str) -> list[str]:
    """Columns of one council table of one collection, from its compute manifest."""
    entry = table_manifest(ds, collection).get('tables', {}).get(table)
    if not entry or not entry.get('columns'):
        raise ValueError(f'table {table} has no entry in the manifest of {Path(collection).name}')
    return list(entry['columns'])


def columns_of(ds: roles.Dataset, spec: dict) -> list[str]:
    """Council columns the model gets on top of the BA block, in order: table columns of spec['tables'] in table
    order, then the placebo names. Read from the table manifests of compute.py; every collection of the spec must
    give the same columns, placebo columns must be columns of the placebo tables, no column may repeat."""
    tables = joined_tables(spec)
    if not tables:
        return []
    seen = None
    for _, path in collections_of(ds, spec):
        cols = {t: table_columns(ds, path, t) for t in tables}
        if seen is not None and cols != seen:
            raise ValueError(f"{spec['name']}: the council tables of {Path(path).name} have other columns")
        seen = cols
    flat = [c for t in tables for c in seen[t]]
    if len(set(flat)) != len(flat):
        raise ValueError(f"{spec['name']}: a council column repeats across tables")
    out = [c for t in spec['tables'] for c in seen[t]]
    if spec['placebo']:
        pool = {c for t in spec['placebo']['tables'] for c in seen[t]}
        lost = [c for c in spec['placebo']['columns'] if c not in pool]
        if lost:
            raise ValueError(f"{spec['name']}: placebo columns {lost[:3]} are not columns of the placebo tables")
        out += [roles.placebo_column(c) for c in spec['placebo']['columns']]
    return out


def council_join(ds: roles.Dataset, frame: pd.DataFrame, collection, tables: list[str]) -> pd.DataFrame:
    """frame (keys user_id, item_id + anything) with the columns of each council table of `collection` attached by
    (user_id, item_id), row order kept; a pair absent from a table gets NaN, as in xfer sidecars. ValueError if a
    table repeats a key, a column clashes with a frame column, the file's columns differ from its manifest, or a
    table file is missing."""
    name = Path(collection).name
    out = frame.reset_index(drop=True)
    n = len(out)
    for t in tables:
        path = ds.paths.table(name, t)
        if not path.exists():
            raise ValueError(f'council table {t} of {name} is missing ({path})')
        expected = table_columns(ds, name, t)
        tab = xc.read_parquet(path)
        cols = [c for c in tab.columns if c not in KEYS]
        if list(tab.columns[:2]) != KEYS or cols != expected:
            raise ValueError(f'council table {t} of {name}: columns {list(tab.columns)[:6]} differ from '
                             f'user_id, item_id + {expected}')
        clash = sorted(set(cols) & set(out.columns))
        if clash:
            raise ValueError(f'council table {t} of {name}: columns {clash[:3]} clash with the frame')
        if tab.duplicated(KEYS).any():
            raise ValueError(f'council table {t} of {name} repeats a (user_id, item_id) key')
        for k in KEYS:
            tab[k] = tab[k].astype(out[k].dtype)
        out = out.merge(tab, on=KEYS, how='left', validate='many_to_one', sort=False)
        if len(out) != n:
            raise ValueError(f'council table {t} of {name} changed the number of rows')
    return out


def apply_placebo(frame: pd.DataFrame, placebo: dict | None, anchor) -> tuple[pd.DataFrame, int]:
    """(frame with roles.placebo_column(c) for every placebo column, its values permuted by
    numpy.random.default_rng(roles.placebo_key(anchor)).permutation(len(frame)), number of placebo columns).
    Row i of a placebo column gets the value of row perm[i] of its source column (the convention of the xfer agent permutation). The same
    anchor gives the same permutation in every fit of the campaign."""
    if not placebo:
        return frame, 0
    cols = list(placebo['columns'])
    lost = [c for c in cols if c not in frame.columns]
    if lost:
        raise ValueError(f'placebo columns {lost[:3]} are not in the frame')
    new = [roles.placebo_column(c) for c in cols]
    clash = sorted(set(new) & set(frame.columns))
    if clash:
        raise ValueError(f'placebo columns {clash[:3]} exist already')
    perm = np.random.default_rng(roles.placebo_key(anchor)).permutation(len(frame))
    out = frame.reset_index(drop=True).copy()
    moved = out[cols].iloc[perm].reset_index(drop=True)
    for c, n in zip(cols, new):
        out[n] = moved[c].to_numpy()
    return out, len(new)


def council_frame(ds: roles.Dataset, frame: pd.DataFrame, collection, spec: dict, anchor) -> tuple:
    """council_join of every joined table, the placebo, the placebo-only tables dropped: (frame, placebo count)."""
    out = council_join(ds, frame, collection, joined_tables(spec))
    out, permuted = apply_placebo(out, spec['placebo'], anchor)
    drop = [c for t in placebo_only(spec) for c in table_columns(ds, collection, t)]
    return out.drop(columns=drop), permuted


# ---------------------------------------------------------------- fit and scores

def classifier(recipe: dict):
    from catboost import CatBoostClassifier
    return CatBoostClassifier(**recipe)


def report_path(ds: roles.Dataset, series: str, arm: str = TRAIN_ARM, seed: int = REFERENCE_SEED) -> Path:
    """The xfer fit report of (series, arm, seed): xm.fit_dir(...)/report.json (read-only)."""
    return Path(xm.fit_dir(ds.name, series, arm, seed)) / REPORT


def check_rows(ds: roles.Dataset, series: str, populations: list[dict]) -> None:
    """SystemExit unless rows_sha256 of every anchor equals the xfer report of (series, TRAIN_ARM, REFERENCE_SEED);
    only identity.training_populations[].anchor/rows_sha256 of the report are read."""
    path = report_path(ds, series)
    if not path.exists():
        raise SystemExit(f'rows check: the xfer report {path} is missing')
    ref = [(xc.anchor_text(p['anchor']), p['rows_sha256'])
           for p in xc.read_json(path)['identity']['training_populations']]
    got = [(xc.anchor_text(p['anchor']), p['rows_sha256']) for p in populations]
    if [a for a, _ in got] != [a for a, _ in ref]:
        raise SystemExit(f'rows check: anchors {[a for a, _ in got]} differ from xfer {[a for a, _ in ref]}')
    bad = [a for (a, x), (_, y) in zip(got, ref) if x != y]
    if bad:
        raise SystemExit(f'rows check: rows_sha256 differs from xfer {series}/{TRAIN_ARM}{REFERENCE_SEED} at {bad}')


def train(ctx, con, ds: roles.Dataset, spec: dict):
    """(model, populations, feature names) of one spec: the rows of every training anchor from xm.training_block
    (arm TRAIN_ARM), the council columns joined, the placebo applied, one CatBoostClassifier(**xm.recipe_for(seed)).
    populations: per anchor {anchor, collection, manifest_sha256, rows, queries, rows_sha256}, checked with
    check_rows before the model is fitted."""
    key = series_key(spec['phase'])
    series = roles.SERIES[key]
    columns = list(ctx.columns) + columns_of(ds, spec)
    parts, populations = [], []
    for anchor, path in ds.training_collections(key):
        block, population, _, _, _ = xm.training_block(ctx, con, series, anchor, TRAIN_ARM, spec['seed'])
        if population['collection'] != Path(path).name:
            raise SystemExit(f"{spec['name']}: xfer trains {anchor} on {population['collection']}, "
                             f'the council on {Path(path).name}')
        labels = block['label'].to_numpy(dtype=np.int8)
        weights = block['weight'].to_numpy(dtype=np.float64)
        frame, _ = council_frame(ds, block, path, spec, anchor)
        del block
        missing = [c for c in columns if c not in frame.columns]
        if missing:
            raise ValueError(f"{spec['name']}: {Path(path).name} lacks columns {missing[:3]}")
        numbers, cats = xm.matrices(ctx, frame, columns)
        parts.append((numbers, cats, labels, weights))
        populations.append({k: population[k] for k in ('anchor', 'collection', 'manifest_sha256', 'rows', 'queries',
                                                       'rows_sha256')})
        del frame
    check_rows(ds, series, populations)
    numbers = np.ascontiguousarray(np.concatenate([p[0] for p in parts]))
    cats = np.concatenate([p[1] for p in parts])
    labels = np.concatenate([p[2] for p in parts])
    weights = np.concatenate([p[3] for p in parts])
    del parts
    if len(np.unique(labels)) != 2:
        raise ValueError(f"{spec['name']}: training needs both classes")
    numeric = list(ctx.numeric) + columns
    recipe = xm.recipe_for(spec['seed'])
    model = classifier(recipe)
    model.fit(xm.make_pool(numbers, cats, numeric, ctx.categorical, labels, weights))
    if model.tree_count_ != recipe['iterations']:
        raise ValueError(f"{spec['name']}: {model.tree_count_} trees instead of {recipe['iterations']}")
    features = numeric + list(ctx.categorical)
    if list(model.feature_names_) != features:
        raise ValueError(f"{spec['name']}: the fitted feature vector differs from the spec's")
    return model, populations, features


def score(ctx, con, ds: roles.Dataset, spec: dict, model, columns: list[str]) -> pd.DataFrame:
    """Scores of the eval collection of the spec's series for the users of spec['half'] (all if None):
    DataFrame[SCORE_COLUMNS], qid = Dataset.qid(eval anchor, user_id), ordered user_id, item_id, finite. The
    council columns and the placebo are built on the whole frame, the half is taken after them."""
    key = series_key(spec['phase'])
    path = Path(ds.collection(key))
    anchor = ds.series(key)['eval']
    ctx.check_collection(path, roles.COLLECTION_ROLES[key])
    directory, side = ctx.sidecar(path)
    xm.check_sidecar_rows(con, path, directory, side)
    frame = xm.frame_rows(con, path / xc.FRAME_FILE, ctx.base_names)
    frame = xm.with_agent(con, frame, directory, ctx.columns)
    frame, _ = council_frame(ds, frame, path, spec, anchor)
    if spec['half'] is not None:
        keep = roles.halves(frame['user_id'].to_numpy()) == spec['half']
        frame = frame[keep].reset_index(drop=True)
    values = np.asarray(xm.predict(ctx, model, frame, list(ctx.columns) + list(columns)), dtype=np.float64)
    if len(values) != len(frame) or not np.isfinite(values).all():
        raise ValueError(f"{spec['name']}: scores are not finite or not one per row")
    users = frame['user_id'].astype(np.int64)
    out = pd.DataFrame({'qid': f'{xc.anchor_text(anchor)}:' + users.astype(str),
                        'user_id': users.to_numpy(), 'item_id': frame['item_id'].astype(np.int64).to_numpy(),
                        'score': values})
    return out.sort_values(KEYS, kind='mergesort').reset_index(drop=True)[list(SCORE_COLUMNS)]


def peak_gb() -> float:
    """Peak resident memory of this process (ru_maxrss: bytes on macOS, KiB on Linux)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 ** 3 if sys.platform == 'darwin' else 1024 ** 2), 2)


def _write(scores: pd.DataFrame, out: Path) -> None:
    """Atomic, never over an existing file: a temporary file in the same directory linked to the final name."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f'.{out.name}.tmp-{os.getpid()}')
    xc.write_parquet(scores, tmp, order_by='user_id, item_id')
    try:
        os.link(tmp, out)
    finally:
        tmp.unlink()


def run(ds: roles.Dataset, spec: dict, stamp: dict | None = None, data: dict | None = None,
        commit: str | None = None, dirty: bool | None = None) -> dict:
    """One fit (steps 1-6 of the module docstring); returns the record appended to ds.paths.fit_records.
    ValueError if the scores file exists; SystemExit if the code or data changed against `stamp`/`data`."""
    s = validate(ds, spec)
    name = s['name']
    out = ds.paths.scores(s['phase'], s['arm'], s['seed'])
    if out.exists():
        raise ValueError(f'{name}: {out} exists; fits are never overwritten')
    marker.check_tail(ds.paths.fit_records)
    identity = code_stamp(ds)
    if stamp is not None and identity != stamp:
        raise SystemExit(f'{name}: the code identity differs from the stamp of the queue')
    stamp = identity
    check_stamp(ds, stamp, name)
    if xm.recipe_for(s['seed']) != roles.recipe_for(s['seed']):
        raise SystemExit(f'{name}: the xfer recipe differs from the council recipe')
    fingerprint = data_stamp(ds, s)
    if data is not None and fingerprint != data:
        raise SystemExit(f'{name}: the data differ from the fingerprint of the queue')
    data = fingerprint
    t0 = time.time()
    ctx = xm.Context(ds.name)
    con = xm.connect()
    try:
        columns = columns_of(ds, s)
        model, populations, features = train(ctx, con, ds, s)
        t1 = time.time()
        scores = score(ctx, con, ds, s, model, columns)
        del model
    finally:
        con.close()
    t2 = time.time()
    if code_stamp(ds) != stamp:
        raise SystemExit(f'{name}: the code changed during the fit; nothing was written')
    if data_stamp(ds, s, cache=False) != data:
        raise SystemExit(f'{name}: the data changed during the fit; nothing was written')
    _write(scores, out)
    key = series_key(s['phase'])
    path = Path(ds.collection(key))
    rec = {
        'name': name, 'spec': s, 'series': series_of(s['phase']), 'identity': stamp, 'data': data,
        'recipe': xm.recipe_for(s['seed']), 'features': len(features), 'council_columns': columns,
        'placebo_columns': len((s['placebo'] or {}).get('columns', [])), 'populations': populations,
        'eval': {'collection': path.name, 'anchor': ds.series(key)['eval'], 'half': s['half'],
                 'manifest_sha256': data['collections'][path.name], 'rows': len(scores),
                 'users': int(scores['user_id'].nunique()), 'keys_sha256': xm.keys_digest(scores),
                 'scores_sha256': xc.sha256_file(out)},
        'peak_rss_gb': peak_gb(), 'commit': commit, 'dirty': dirty,
        'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0)),
        'seconds': {'train': round(t1 - t0), 'score': round(t2 - t1), 'write': round(time.time() - t2)},
    }
    rec = json.loads(json.dumps(rec, default=str))
    marker.append(ds.paths.fit_records, rec)
    return rec


def records(ds: roles.Dataset) -> dict:
    """name -> the last record of each fit in ds.paths.fit_records. A broken last line (a fit killed while
    appending) is skipped with a warning on stderr; a broken line before it is an error (contract §8.12)."""
    path = ds.paths.fit_records
    if not path.exists():
        return {}
    lines = [x for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    out = {}
    for i, line in enumerate(lines):
        try:
            r = json.loads(line)
        except ValueError:
            if i != len(lines) - 1:
                raise ValueError(f'{path}: line {i + 1} is broken') from None
            print(f'warning: {path}: the last line is broken and skipped', file=sys.stderr)
            continue
        out[r['name']] = r
    return out


def done(ds: roles.Dataset, spec: dict, data: dict | None = None, stamp: dict | None = None) -> bool:
    """True if the scores file and a record with this spec (and, given `data`/`stamp`, this data stamp and this
    code identity) exist; SystemExit if the file exists without a record, with another spec, other data or another
    identity (the queue stops, it does not skip), and if `stamp` differs from the identity of prereg-0."""
    if stamp is not None:
        check_stamp(ds, stamp, spec['name'])
    if not ds.paths.scores(spec['phase'], spec['arm'], spec['seed']).exists():
        return False
    rec = records(ds).get(spec['name'])
    if rec is None or rec.get('spec') != spec:
        raise SystemExit(f"{spec['name']}: a scores file exists without a record or with another spec; move it aside")
    if data is not None and rec.get('data') != data:
        raise SystemExit(f"{spec['name']}: done on other data than the queue's fingerprint; move it aside")
    if stamp is not None and rec.get('identity') != stamp:
        raise SystemExit(f"{spec['name']}: done with another code identity than the queue's; move it aside")
    return True


def git_head() -> tuple:
    """HEAD and whether a stamped council file differs from it; (None, None) outside a git checkout."""
    try:
        def git(*a):
            return subprocess.run(['git', *a], cwd=roles.ROOT, capture_output=True, text=True, check=True).stdout
        files = [p.relative_to(roles.ROOT).as_posix() for p in roles.stamp_files()]
        return git('rev-parse', 'HEAD').strip(), bool(git('status', '--porcelain', '--', *files).strip())
    except (OSError, subprocess.CalledProcessError):
        return None, None


def main(ds: roles.Dataset, argv: list[str]) -> int:
    """CLI of the stage fit-one: --spec FILE (one JSON spec), --stamp JSON, --data JSON (set by queue.run).
    Prints one JSON line with name, features, rows, peak and seconds; returns the exit code."""
    ap = argparse.ArgumentParser(prog='fit-one', description='one council fit on xfer (contract §3.1)')
    ap.add_argument('--spec', required=True)
    ap.add_argument('--stamp', required=True)
    ap.add_argument('--data', required=True)
    args = ap.parse_args(argv)
    spec = json.loads(Path(args.spec).read_text(encoding='utf-8'))
    commit, dirty = git_head()
    try:
        rec = run(ds, spec, json.loads(args.stamp), json.loads(args.data), commit, dirty)
    except (ValueError, FileExistsError) as e:
        raise SystemExit(f'fit-one: {e}') from None
    print(json.dumps({'name': rec['name'], 'features': rec['features'], 'rows': rec['eval']['rows'],
                      'peak_rss_gb': rec['peak_rss_gb'], 'seconds': rec['seconds']}), flush=True)
    return 0
