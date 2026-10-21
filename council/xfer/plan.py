"""Prereg-0, the plan, the selection and the C_test arms of the council on xfer (council/runs/xfer/contract.md
§3.3, §4), on top of council.design without changing it. Every per-query table comes from council.xfer.broker;
this module never reads a score or a target itself. Files are under council/runs/xfer-<x>/ (Dataset.paths.runs).

  path_queue(ds)   queue-path.json: fit.path_specs + fit.noise_specs (4 fits)
  prereg0(ds)      broker.path_check('select'), broker.path_check('test'), broker.noise_explore -> sigma_q,
                   deff, design.rehearse at n = |S0-select| -> power gate -> prereg-0.json
  build(ds)        curation.json -> prereg-2.json and queue-plan.json (48 fits, design.matrix rows)
  analyze(ds)      broker.y_select(48) -> design.estimate, wy_maxT, calibrate, nominate, mechanism ->
                   plan-result.json; D and, if D is not empty, queue-confirm.json
  select(ds)       after the confirmation (if any) -> selection.json {SEL, D, reason, twin_arm, tables}
  test_queue(ds)   selection.json + the test.started marker -> queue-test.json (14 or 16 fits, roles.TEST_FITS)
  read_test(ds)    broker.c_test -> H1 (design.h1 over 4 seeds), mechanism repeat (twin vs SEL on seeds 7, 11),
                   descriptive contrasts -> test.json

Arms are lists of council tables on top of H+r (= BA of xfer, the frozen agent set inside every arm):
  Hr = [], Hrp = Rb1 + Rb2 kept, ALLP = families, SEL = ALLP minus D, TWIN = SEL with the family of the largest
  t(beta_g - beta_twin) replaced by its twin, Rb1/Rb2 = the kept tables of one reference run.

Guards (as council/plan.py of REES46): plan_specs is a pure builder of the queue from the curation and the
matrix; analyze and select refuse unless design.matrix() has the sha of prereg-2.json, curation.json has its sha
and queue-plan.json is exactly plan_specs(curation); the one-time reads (S0-explore noise, C_test) are kept under
Dataset.paths.out and reused, never read twice; prereg-0, prereg-2, the queue files and selection.json are never
overwritten with other content.

D is the list of nominated F-columns (design.nominate); the confirmation runs only with the power gate and the
calibration passed and D not empty; otherwise SEL = ALL_P (contract §2, §3.3).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from council import design as D
from council.xfer import broker, fit, queue as Q, roles

PLAN_PHASE = 'plan'
CONFIRM_PHASE = 'confirm'
TEST_PHASE = 'test'
DESIGN_COLUMNS = D.COLUMNS          # F1..F12, T1..T4, PL, E1..E6: the columns plan_specs lays out

SPEC_KEYS = ('name', 'phase', 'arm', 'seed', 'half', 'tables', 'placebo', 'selection_sha256')   # = fit.SPEC_KEYS
RB_TABLE = re.compile(r'rb([12])_[a-z][a-z0-9_]*')
NOISE_READ = 'noise-read.parquet'           # the one S0-explore read, kept under Dataset.paths.out
TEST_READ = 'test-read-{sha}.parquet'       # the one C_test read of a selection, kept under Dataset.paths.out
H1_ARMS = ('Hrp', 'SEL')                    # never cut
CUT_ORDER = (('Rb1', 'Rb2'), ('TWIN',), ('Hr',))   # the cut line of contract §4, items 1-3, in order
PATH_TOLERANCE = 'path-tolerance.json'      # {"path_tolerance": x, "reason": text}, written by hand (§6.8, §9.2)
SEL_ALL = 'ALL_P'
SEL_MINUS = 'ALL_P minus D'
REPEATED = 'повторный тест (контракт §0): якоря C_test открыты цепочкой xfer, вывод — первая проверка'


# ---------------------------------------------------------------- files

def _default(v):
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, (tuple, set)):
        return list(v)
    raise TypeError(f'{type(v).__name__} is not JSON')


def _dumps(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, default=_default) + '\n'


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _save(path: Path, obj) -> None:
    _atomic(Path(path), _dumps(obj))


def _save_new(path: Path, obj) -> None:
    """Write once: the same content again is a no-op, other content over an existing file is refused."""
    path, text = Path(path), _dumps(obj)
    if path.exists():
        if path.read_text(encoding='utf-8') == text:
            return
        raise SystemExit(f'{path.name} exists with other content: it is written once (remove it by hand if the '
                         f'change is intended and nothing ran from it)')
    _atomic(path, text)


def _load(path: Path, what: str | None = None):
    path = Path(path)
    if not path.exists():
        raise SystemExit(f'{path.name} is missing' + (f': {what}' if what else ''))
    return json.loads(path.read_text(encoding='utf-8'))


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix_sha256(x: np.ndarray | None = None) -> str:
    return hashlib.sha256((D.matrix() if x is None else x).tobytes()).hexdigest()


def _sql_path(p: Path) -> str:
    return str(p).replace("'", "''")


def _keep(path: Path, y: pd.DataFrame) -> None:
    """A one-time read kept as parquet (qid + one column per fit), written atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = y.rename_axis('qid').reset_index()
    tmp = path.with_name(f'.{path.name}.part')
    tmp.unlink(missing_ok=True)
    duckdb.sql(f"COPY (SELECT * FROM frame) TO '{_sql_path(tmp)}' (FORMAT PARQUET)")
    os.replace(tmp, path)


def _kept(path: Path) -> pd.DataFrame:
    return duckdb.sql(f"SELECT * FROM read_parquet('{_sql_path(path)}')").df().set_index('qid')


# ---------------------------------------------------------------- arms and the plan queue

def _names(items) -> list[str]:
    return [x if isinstance(x, str) else (x.get('table') or x.get('id') or x.get('name')) for x in items or []]


def reference_kept(curation: dict) -> list[str]:
    """Rb tables of the arms: reference_order (the order given to curate) without reference_removed and the
    parity cut (the rule of council.agents.reference_kept)."""
    order = curation.get('reference_order')
    if order is None:
        raise ValueError('curation.json has no reference_order (curate.stage writes it)')
    gone = set((curation.get('parity') or {}).get('reference_drop') or []) | set(_names(curation.get('reference_removed')))
    kept = [t for t in order if t not in gone]
    bad = [t for t in kept if not RB_TABLE.fullmatch(t)]
    if bad or len(set(kept)) != len(kept):
        raise ValueError(f'Rb tables must be distinct rb<k>_<slug>: {bad or kept}')
    return kept


def _families(curation: dict) -> tuple[list[str], list[str]]:
    fams, twins = list(curation['families']), list(curation.get('twins') or [])
    if len(fams) > len(D.FAMILIES) or len(twins) > len(D.TWINS):
        raise ValueError(f'{len(fams)} families / {len(twins)} twins: the plan has {len(D.FAMILIES)} / {len(D.TWINS)}')
    if len(set(fams)) != len(fams) or len(set(twins)) != len(twins) or not set(twins) <= set(fams):
        raise ValueError('families must be distinct and every twin must be a family')
    return fams, twins


def arms(curation: dict) -> dict:
    """arm -> council tables: {'Hr', 'Hrp', 'ALLP', 'Rb1', 'Rb2'} from curation.json (families via
    roles.family_table, Rb by reference_order minus reference_removed and the parity cut)."""
    fams, _ = _families(curation)
    rb = reference_kept(curation)
    return {'Hr': [], 'Hrp': list(rb), 'ALLP': [roles.family_table(f) for f in fams],
            'Rb1': [t for t in rb if t.startswith('rb1_')], 'Rb2': [t for t in rb if t.startswith('rb2_')]}


def _sandbox(column: str) -> str:
    """A curation column as the fits name it: f_x_c<lens>_<slug> -> ag_c<lens>_<slug> (already ag_c: kept)."""
    return column if roles.CARD_COLUMN.fullmatch(column) else roles.sandbox_column(column)


def placebo_of(curation: dict) -> dict | None:
    """{tables, columns} of the placebo family PL (columns in the sandbox names the tables carry), or None."""
    cols, fams = list(curation.get('placebo') or []), list(curation.get('placebo_families') or [])
    if not cols:
        return None
    if len(cols) != len(fams):
        raise ValueError('placebo and placebo_families differ in length')
    return {'tables': [roles.family_table(f) for f in fams], 'columns': [_sandbox(c) for c in cols]}


def _spec(phase, arm, seed, half, tables, placebo=None, selection_sha256=None) -> dict:
    spec = {'name': f'{phase}-{arm}-{int(seed)}', 'phase': phase, 'arm': arm, 'seed': int(seed), 'half': half,
            'tables': list(tables), 'placebo': placebo, 'selection_sha256': selection_sha256}
    assert tuple(spec) == SPEC_KEYS
    return spec


def plan_specs(curation: dict, x: np.ndarray | None = None) -> list[dict]:
    """48 fit specs of phase plan: row r of design.matrix() (x) -> arm f'r{r:02d}', seed roles.plan_seed(r),
    half 'B', tables = families with +1/2 in F1..F12, twins (roles.twin_table) with +1/2 in T1..T4 (the columns of
    design.layout(n_families, n_twins)), placebo {tables, columns} of curation['placebo'] when PL is +1/2."""
    x = D.matrix() if x is None else np.asarray(x, dtype=float)
    if x.shape != (roles.PLAN_RUNS, len(DESIGN_COLUMNS)):
        raise ValueError(f'the plan matrix is {roles.PLAN_RUNS} x {len(DESIGN_COLUMNS)}, got {x.shape}')
    fams, twins = _families(curation)
    col = {c: j for j, c in enumerate(DESIGN_COLUMNS)}
    placebo = placebo_of(curation)
    out = []
    for r in range(1, roles.PLAN_RUNS + 1):
        row = x[r - 1]
        tables = [roles.family_table(f) for k, f in enumerate(fams) if row[col[f'F{k + 1}']] > 0]
        tables += [roles.twin_table(f) for k, f in enumerate(twins) if row[col[f'T{k + 1}']] > 0]
        out.append(_spec(PLAN_PHASE, f'r{r:02d}', roles.plan_seed(r), roles.SELECT, tables,
                         placebo if row[col[D.PLACEBO]] > 0 else None))
    return out


def sel_tables(curation: dict, d_columns) -> list[str]:
    """ALL_P minus the families of the D columns (F<k> -> the k-th family of the curation)."""
    fams, _ = _families(curation)
    d = set(d_columns or [])
    unknown = d - {f'F{k + 1}' for k in range(len(fams))}
    if unknown:
        raise ValueError(f'D names columns that are not families: {sorted(unknown)}')
    return [roles.family_table(f) for k, f in enumerate(fams) if f'F{k + 1}' not in d]


def confirm_specs(curation: dict, d_columns: list[str]) -> list[dict]:
    """The confirmation of D on S0-select: ALL_P and ALL_P minus D (arm SEL) on roles.CONFIRM_SEEDS."""
    pairs = (('ALLP', arms(curation)['ALLP']), ('SEL', sel_tables(curation, d_columns)))
    return [_spec(CONFIRM_PHASE, arm, s, roles.SELECT, tables) for arm, tables in pairs for s in roles.CONFIRM_SEEDS]


# ---------------------------------------------------------------- prereg-0

def path_queue(ds: roles.Dataset) -> list[dict]:
    """Writes queue-path.json with fit.path_specs(ds) + fit.noise_specs(ds); returns the specs."""
    specs = list(fit.path_specs(ds)) + list(fit.noise_specs(ds))
    names = [s['name'] for s in specs]
    if len(set(names)) != len(names):
        raise SystemExit('queue-path: repeated fit names')
    _save_new(ds.paths.queue('path'), specs)
    return specs


def noise_summary(y: pd.DataFrame) -> dict:
    """From the two noise columns (qid x 2) of S0-explore: {queries, users, sigma_q = SD(y1 - y2)/sqrt 2,
    deff = design.design_effect(y1 - y2, design.users_of(qids)), seed_mean_shift_abs}."""
    if y.shape[1] != 2 or len(y) < 2:
        raise ValueError(f'the noise read is qid x 2 fits, got {y.shape}')
    if not np.isfinite(y.to_numpy(dtype=float)).all():
        raise ValueError('the noise read has non-finite values')
    d = (y.iloc[:, 0] - y.iloc[:, 1]).astype(float)
    groups = D.users_of(y.index)
    return {'queries': int(len(y)), 'users': int(len(set(groups))),
            'sigma_q': float(d.std(ddof=1) / math.sqrt(2.0)),
            'deff': float(D.design_effect(d.to_numpy(), groups)),
            'seed_mean_shift_abs': float(abs(d.mean()))}


def _row(r: dict) -> dict:
    return {'power': r['power'], 'sd_t_interval': list(r['sd_t_interval']), 'false_rate': r['false_rate'],
            'gate': r['gate']}


def power_gate(n_select: int, sigma_q: float, deff: float) -> dict:
    """design.rehearse(n_select, sigma_q, deff=deff, beta_harm=design.BETA_HARM) plus the sensitivity rows of
    REES46 prereg-0 (deff 1, sigma_fit = sigma_q / sqrt n, beta -0.001); gate = power >= design.POWER_GATE."""
    n = int(n_select)
    if n < 2 or not sigma_q > 0 or not deff > 0:
        raise ValueError(f'the power gate needs n >= 2, sigma_q > 0 and deff > 0, got {n}, {sigma_q}, {deff}')
    main = D.rehearse(n, sigma_q, deff=deff, beta_harm=D.BETA_HARM)
    main['sd_t_interval'] = list(main['sd_t_interval'])
    sensitivity = {
        'deff1': _row(D.rehearse(n, sigma_q, deff=1.0, beta_harm=D.BETA_HARM)),
        'sigma_fit_1': _row(D.rehearse(n, sigma_q, deff=deff, beta_harm=D.BETA_HARM,
                                       sigma_fit=sigma_q / math.sqrt(n))),
        'beta_-0.001': _row(D.rehearse(n, sigma_q, deff=deff, beta_harm=-0.001)),
    }
    gate = bool(main['power'] >= D.POWER_GATE)
    return {'n_select': n, 'power': float(main['power']), 'gate': gate, 'rehearsal': main,
            'sensitivity': sensitivity,
            'rule': ('SEL = ALL_P minus D after the nomination and the confirmation of D' if gate else
                     f"SEL = ALL_P by construction: power {main['power']:.3f} < {D.POWER_GATE}; the nomination and "
                     f'the confirmation of D do not run, the plan is descriptive (contract §3.3, §6.5)')}


def s0_users(ds: roles.Dataset) -> np.ndarray:
    """The distinct users of the S0 frame (frame.parquet of the select collection: keys and base only)."""
    frame = Path(ds.collection('select')) / 'frame.parquet'
    return duckdb.sql(f"SELECT DISTINCT user_id FROM read_parquet('{_sql_path(frame)}')").df()['user_id'].to_numpy()


def noise_read(ds: roles.Dataset, names: list[str]) -> pd.DataFrame:
    """broker.noise_explore once; the read is kept in Dataset.paths.out and reused (the broker refuses a second)."""
    kept = ds.paths.out / NOISE_READ
    if kept.exists():
        y = _kept(kept)
        if list(y.columns) != list(names):
            raise SystemExit(f'{kept}: the kept noise read has fits {list(y.columns)}, not {names}')
        return y
    y = broker.noise_explore(ds, list(names))[list(names)]
    _keep(kept, y)
    return y


def path_tolerance(ds: roles.Dataset, checks: dict) -> dict:
    """The tolerance of the path checks (contract §3.1, §6.8, §9.2), before any noise read. SystemExit when a check
    has other queries or a non-numeric difference, and when a finite difference exceeds roles.PATH_TOL while no
    explicit tolerance is written: runs/path-tolerance.json {"path_tolerance": x >= the measured max |diff|,
    "reason": text}. Returns {value, reason, explicit, max_abs_diff}."""
    diffs = {}
    for kind, c in checks.items():
        if c.get('same_queries') is not True:
            raise SystemExit(f'path check {kind}: the fit does not cover the queries of BA2026 - stop (contract §3.1)')
        d = c.get('max_abs_diff')
        if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d):
            raise SystemExit(f'path check {kind}: max |diff| is {d!r}, not a finite number - stop')
        diffs[kind] = float(d)
    worst = max(diffs.values())
    if worst <= roles.PATH_TOL:
        return {'value': roles.PATH_TOL, 'reason': 'contract §3.1', 'explicit': False, 'max_abs_diff': diffs}
    f = ds.paths.run_file(PATH_TOLERANCE)
    if not f.exists():
        raise SystemExit(f'path checks: max |diff| {worst!r} > {roles.PATH_TOL}; the noise is not read until the '
                         f'tolerance is written explicitly to {f} {{"path_tolerance": x, "reason": "..."}} (§6.8)')
    t = json.loads(f.read_text(encoding='utf-8'))
    value, reason = t.get('path_tolerance'), t.get('reason')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not isinstance(reason, str) or not reason.strip():
        raise SystemExit(f'{f.name}: needs a finite "path_tolerance" and a non-empty "reason"')
    if worst > value:
        raise SystemExit(f'path checks: max |diff| {worst!r} exceeds the written tolerance {value!r}')
    return {'value': float(value), 'reason': reason.strip(), 'explicit': True, 'max_abs_diff': diffs,
            'file_sha256': _sha(f)}


def prereg0(ds: roles.Dataset) -> dict:
    """prereg-0.json: path checks (both kinds, measured max |diff|), noise_summary, |S0-explore| and the expected
    |S0-select| (roles.halves over the S0 frame users), power_gate, identity (roles.identity), council stamp,
    data fingerprints, peak memory from the queue journal, and the records of contract §6.5 and §6.10 (gate
    expected to fail, SEL = ALL_P; target shares not compared before the test).

    The path checks come first and stop the stage before the one noise read (path_tolerance, contract §9.2)."""
    out_path = ds.paths.prereg(0)
    if out_path.exists():
        raise SystemExit(f'{out_path.name} exists: prereg-0 is written once')
    specs = list(fit.path_specs(ds)) + list(fit.noise_specs(ds))
    names = {s['name'] for s in specs}
    noise_names = [s['name'] for s in fit.noise_specs(ds)]
    done = fit.records(ds)
    missing = [s['name'] for s in specs if s['name'] not in done]
    if missing:
        raise SystemExit(f'run the queue path first: no record of {missing}')
    checks = {kind: broker.path_check(ds, kind) for kind in ('select', 'test')}
    tol = path_tolerance(ds, checks)
    noise = noise_summary(noise_read(ds, noise_names))
    users = s0_users(ds)
    h = roles.halves(users)
    n_explore, n_select = int((h == roles.EXPLORE).sum()), int((h == roles.SELECT).sum())
    gate = power_gate(n_select, noise['sigma_q'], noise['deff'])
    path_ok = not tol['explicit']
    deviation = None
    if not path_ok:
        deviation = dict(tol['max_abs_diff'], tolerance=tol['value'], reason=tol['reason'],
                         note='CatBoost не воспроизвёл BA2026: фактическая разница — отклонение набора, допуск '
                              'записан явно до чтения шума и до любого числа совета (контракт §6.8, §9.2)')
    prereg = {
        'dataset': ds.name,
        'path_checks': checks,
        'path_ok': path_ok,
        'path_tolerance': tol,
        'deviation_6_8': deviation,
        'noise_fits': noise_names,
        'explore_queries': noise['queries'],
        'users': noise['users'],
        'sigma_q': noise['sigma_q'],
        'deff': noise['deff'],
        'seed_mean_shift_abs': noise['seed_mean_shift_abs'],
        's0_frame_users': {'all': int(len(users)), roles.EXPLORE: n_explore, roles.SELECT: n_select},
        'explore_check': {'frame_half_users': n_explore, 'explore_queries': noise['queries'],
                          'equal': noise['queries'] == n_explore},
        'select_queries_expected': n_select,
        'rehearsal': gate['rehearsal'],
        'rehearsal_layout': {'n_families': len(D.FAMILIES), 'n_twins': len(D.TWINS)},
        'sensitivity': gate['sensitivity'],
        'power': gate['power'],
        'gate': gate['gate'],
        'rule': gate['rule'],
        'expected_gate': 'не пройден: SEL = ALL_P по построению, план описательный (контракт §6.5)',
        'shares_before_test': 'доли запросов с целью до теста не считаются и не сравниваются; после чтения C_test — '
                              'описательно в квитанции (контракт §1, §6.10)',
        'test': REPEATED,
        'identity': roles.identity(ds),
        'fits': {s['name']: {k: done[s['name']].get(k) for k in ('spec', 'data', 'populations', 'identity',
                                                                  'peak_rss_gb', 'seconds', 'commit', 'dirty')}
                 for s in specs},
        'peak_gb': max([v for k, v in Q.peaks(ds.paths.queue_log).items()
                        if k in names or k.removeprefix('fit ') in names], default=None),
        'seeds': {'path': roles.PATH_SEED, 'noise': list(roles.NOISE_SEEDS), 'plan': '1000 + r',
                  'confirm': list(roles.CONFIRM_SEEDS), 'test': {k: list(v) for k, v in roles.TEST_FITS.items()}},
    }
    _save(out_path, prereg)
    return prereg


# ---------------------------------------------------------------- prereg-2 and the plan

def _path_cleared(p0: dict) -> bool:
    """prereg-0 passed the path checks, or a written tolerance (with its reason) covers the measured difference."""
    if p0.get('path_ok') is True:
        return True
    tol = p0.get('path_tolerance') or {}
    diffs = list((tol.get('max_abs_diff') or {}).values())
    return bool(tol.get('explicit') and isinstance(tol.get('reason'), str) and tol['reason'].strip()
                and isinstance(tol.get('value'), (int, float)) and diffs and max(diffs) <= tol['value'])


def empty_columns(curation: dict) -> list[str]:
    """design.layout empties of the curation, plus PL when there is no placebo (contract §9.6), in column order."""
    fams, twins = _families(curation)
    _, empty = D.layout(len(fams), len(twins))
    if placebo_of(curation) is None:
        empty = [c for c in DESIGN_COLUMNS if c in set(empty) | {D.PLACEBO}]
    return empty


def _same_code(ds: roles.Dataset, pre: dict) -> None:
    if roles.identity(ds) != pre.get('identity'):
        raise SystemExit('the code identity (roles.identity) differs from prereg-2.json (contract §3 rule 3, §9.4)')


def build(ds: roles.Dataset) -> dict:
    """prereg-2.json {families F1.., twins T1.., placebo, empty, columns, matrix_sha256, seeds, arms,
    tables_over_hr, curation_sha256, rule, twin_arm, h1} and queue-plan.json (plan_specs); returns prereg-2.

    The null rehearsal is repeated on the actual layout (n_families, n_twins) of the curation: its sd_t_interval
    is the calibration interval of analyze; the gate stays the one of prereg-0 (12/4), both are written (§9.1).
    The code identity is stamped (§9.4). Refuses when the path checks failed without a written tolerance."""
    cur_path = ds.paths.run_file('curation.json')
    cur = _load(cur_path, 'run curate first')
    p0 = _load(ds.paths.prereg(0), 'prereg-0 comes before the plan (contract §4)')
    if not _path_cleared(p0):
        raise SystemExit('prereg-0: the path checks failed and no tolerance with a reason is written (§6.8, §9.2)')
    fams, twins = _families(cur)
    if not fams:
        raise SystemExit('curation.json has no family: there is no plan')
    empty = empty_columns(cur)
    x = D.matrix()
    queue = plan_specs(cur, x)
    a = arms(cur)
    reh = D.rehearse(int(p0['select_queries_expected']), p0['sigma_q'], deff=p0['deff'], beta_harm=D.BETA_HARM,
                     n_families=len(fams), n_twins=len(twins))
    reh['sd_t_interval'] = list(reh['sd_t_interval'])
    reh['layout'] = {'n_families': len(fams), 'n_twins': len(twins)}
    if placebo_of(cur) is None:
        reh['note'] = 'PL is empty in the analysis but not in design.rehearse: the interval has one empty less'
    prereg = {
        'families': {f'F{k + 1}': f for k, f in enumerate(fams)},
        'family_tables': {f'F{k + 1}': roles.family_table(f) for k, f in enumerate(fams)},
        'twins': {f'T{k + 1}': {'family': f'F{fams.index(f) + 1}', 'card': f, 'table': roles.twin_table(f)}
                  for k, f in enumerate(twins)},
        'placebo': placebo_of(cur), 'empty': empty, 'columns': list(DESIGN_COLUMNS),
        'matrix_sha256': matrix_sha256(x),
        'seeds': {q['name']: q['seed'] for q in queue},
        'arms': a, 'tables_over_hr': {k: len(v) for k, v in a.items()},
        'curation_sha256': _sha(cur_path),
        'rehearsal': reh,
        'power_gate': {'power': p0['power'], 'gate': p0['gate'], 'layout': '12/4 (prereg-0)',
                       'sd_t_interval': p0['rehearsal']['sd_t_interval'],
                       'power_on_this_layout': reh['power']},
        'rule': p0['rule'] + '; calibration on the interval of this layout, beta and twins by council.design',
        'twin_arm': 'SEL with the family of the largest t(beta_g - beta_twin) replaced by its twin, chosen by select',
        'h1': f'design.h1 on C_test, SEL vs H+r+ over seeds {list(roles.TEST_SEEDS)}',
        'test_fits': {k: list(v) for k, v in roles.TEST_FITS.items()},
        'test': REPEATED,
        'identity': roles.identity(ds),
    }
    _save_new(ds.paths.prereg(2), prereg)
    _save_new(ds.paths.queue('plan'), queue)
    return prereg


def _what(prereg2: dict) -> dict:
    out = {c: 'empty' for c in DESIGN_COLUMNS}
    out |= dict(prereg2.get('family_tables') or {k: roles.family_table(v) for k, v in prereg2['families'].items()})
    out |= {t: roles.twin_table(v['card']) for t, v in prereg2['twins'].items()}
    if D.PLACEBO not in prereg2['empty']:
        out[D.PLACEBO] = 'placebo'
    return out


def estimate(y: pd.DataFrame, prereg2: dict, sd_t_interval: tuple[float, float]) -> dict:
    """Pure analysis of the 48 plan columns (qid x fit name in plan order): design.estimate with users as groups
    (design.users_of), wy_maxT, calibrate(t_empty, sd_t_interval = prereg-2['rehearsal']['sd_t_interval'],
    p_wy_empty), nominate (D), mechanism -> {queries, users, beta {column: {what, beta, se, t}}, se_empty,
    wy_harm, wy_empty_max, calibration, D, mechanism (rows), twin_arm_family}."""
    if y.shape[1] != roles.PLAN_RUNS:
        raise ValueError(f'the plan read is qid x {roles.PLAN_RUNS} fits, got {y.shape}')
    groups = D.users_of(y.index)
    est = D.estimate(y.to_numpy(dtype=float), D.matrix(), prereg2['empty'], groups=groups, names=DESIGN_COLUMNS,
                     n_boot=roles.N_BOOT, seed=roles.BOOT_SEED)
    harm = D.present_families(est) + ([D.PLACEBO] if D.PLACEBO not in est.empty else [])
    wy = D.wy_maxT(est, harm=harm, seed=roles.BOOT_SEED)
    cal = D.calibrate(est.t[est.empty], tuple(sd_t_interval), float(wy['empty_max']))
    nominated = D.nominate(est.t, wy['harm'], D.present_families(est))
    twins = {t: v['family'] for t, v in prereg2['twins'].items()}
    if twins:
        mech = D.mechanism(est, twins)
        rows, arm = mech['table'].reset_index(names='family').to_dict('records'), mech['arm']
    else:
        rows, arm = [], None
    what = _what(prereg2)
    return {'queries': int(len(y)), 'users': int(len(set(groups))),
            'beta': {c: {'what': what[c], 'beta': float(est.beta[c]), 'se': float(est.se[c]), 't': float(est.t[c])}
                     for c in DESIGN_COLUMNS},
            'se_empty': float(est.se_empty), 'wy_harm': {k: float(v) for k, v in wy['harm'].items()},
            'wy_empty_max': float(wy['empty_max']), 'calibration': cal, 'D': list(nominated),
            'mechanism': rows, 'twin_arm_family': arm}


def _checked_plan(ds: roles.Dataset) -> tuple[dict, dict, list[dict]]:
    """(curation, prereg-2, queue-plan) after the guards: the code identity, the matrix sha, the curation sha and
    the queue equal to plan_specs(curation) (the rows of the matrix are the fits that ran)."""
    cur_path = ds.paths.run_file('curation.json')
    cur = _load(cur_path)
    pre = _load(ds.paths.prereg(2), 'run plan-build first')
    q = _load(ds.paths.queue('plan'), 'run plan-build first')
    _same_code(ds, pre)
    if matrix_sha256() != pre['matrix_sha256']:
        raise SystemExit('design.matrix() differs from prereg-2.json')
    if _sha(cur_path) != pre['curation_sha256']:
        raise SystemExit('curation.json differs from the one prereg-2.json was built on')
    if q != plan_specs(cur):
        raise SystemExit('queue-plan.json is not the queue of the matrix and the curation: rows would not match fits')
    return cur, pre, q


def analyze(ds: roles.Dataset) -> dict:
    """broker.y_select(the 48 plan fits) -> estimate() -> plan-result.json; with D not empty also
    queue-confirm.json (ALL_P and ALL_P minus D on roles.CONFIRM_SEEDS). Returns plan-result.
    The calibration interval is the one of prereg-2 (the actual layout, §9.1); the gate is the one of prereg-0."""
    if ds.paths.selection.exists():
        raise SystemExit('selection.json exists: the plan result is frozen with it')
    cur, pre, q = _checked_plan(ds)
    p0 = _load(ds.paths.prereg(0))
    names = [s['name'] for s in q]
    y = broker.y_select(ds, names)[names]
    res = estimate(y, pre, pre['rehearsal']['sd_t_interval'])
    res['fits'] = names
    res['power_gate'] = bool(p0['gate'])
    if p0['gate']:
        res['thresholds'] = (f'DELTA_MIN {D.DELTA_MIN} и BETA_HARM {D.BETA_HARM} абсолютные, не масштабированы к '
                             f'уровню метрики набора (отклонение 4, контракт §6.1)')
    confirm = bool(p0['gate']) and bool(res['calibration']['passed']) and bool(res['D'])
    res['subtraction'] = ('D is confirmed on seeds ' + json.dumps(list(roles.CONFIRM_SEEDS)) if confirm else
                          'descriptive: ' + ('power gate failed' if not p0['gate'] else
                                             'calibration failed' if not res['calibration']['passed'] else
                                             'D is empty'))
    _save(ds.paths.run_file('plan-result.json'), res)
    if confirm:
        _save_new(ds.paths.queue('confirm'), confirm_specs(cur, res['D']))
    return res


# ---------------------------------------------------------------- selection

def check_cut(cut) -> list[str]:
    """The cut of contract §4 items 1-3 in canonical order; only whole items, in their order (Rb1+Rb2, then TWIN,
    then Hr); the H1 arms are never cut."""
    cut = list(cut or [])
    allowed = [sum((list(g) for g in CUT_ORDER[:k]), []) for k in range(len(CUT_ORDER) + 1)]
    canon = [a for g in CUT_ORDER for a in g if a in cut]
    if len(set(cut)) != len(cut) or set(cut) != set(canon) or canon not in allowed:
        raise ValueError(f'cut {cut!r}: by contract §4 the cut is one of {allowed}')
    return canon


def twin_arm(prereg2: dict, mechanism_rows: list[dict], exclude=()) -> dict:
    """{family, card, replace: [family table, twin table]} of the largest t(beta_g - beta_twin) outside `exclude`."""
    rows = [m for m in mechanism_rows if m['family'] not in set(exclude)]
    if not rows:
        return {'family': None, 'card': None, 'replace': None}
    best = max(rows, key=lambda m: m['t'])
    card = prereg2['families'][best['family']]
    return {'family': best['family'], 'card': card, 'replace': [roles.family_table(card), roles.twin_table(card)]}


def _twin_tables(sel: list[str], replace) -> list[str] | None:
    if not replace:
        return None
    fam, twin = replace
    if fam not in sel:
        raise ValueError(f'the twin arm replaces {fam}, which is not in SEL')
    return [twin if t == fam else t for t in sel]


def _arm_tables(curation: dict, d_columns, replace) -> dict:
    sel = sel_tables(curation, d_columns)
    tables = dict(arms(curation), SEL=sel)
    twin = _twin_tables(sel, replace)
    if twin is not None:
        tables['TWIN'] = twin
    return tables


def _shas(ds: roles.Dataset) -> dict:
    """sha256 of the files selection.json is bound to (None for a file that does not exist)."""
    files = {'curation_sha256': ds.paths.run_file('curation.json'), 'prereg2_sha256': ds.paths.prereg(2),
             'plan_result_sha256': ds.paths.run_file('plan-result.json')}
    return {k: (_sha(p) if p.exists() else None) for k, p in files.items()}


def _check_bound(ds: roles.Dataset, selection: dict) -> None:
    """SystemExit unless curation.json, prereg-2.json and plan-result.json are the files selection.json names."""
    now = _shas(ds)
    for k, v in now.items():
        if k not in selection:
            raise SystemExit(f'selection.json has no {k}')
        if selection[k] != v:
            raise SystemExit(f'{k}: the file changed after selection.json (contract §9.4)')


def select(ds: roles.Dataset, cut=(), cut_plan: bool = False) -> dict:
    """selection.json: SEL = ALL_P when the power gate failed or D is empty or not confirmed (design.confirm on
    broker.y_select of the confirmation fits), else ALL_P minus D; twin_arm {family, card, replace: [family table,
    twin table]}; tables per arm. Written once; it is committed before the test.

    cut: arms of the cut line (contract §4 items 1-3, check_cut), recorded before test.started and applied by
    test_specs. cut_plan: items 4-5 - the plan did not start in time: SEL = ALL_P without plan-result and without a
    twin arm (prereg-2 is required)."""
    if ds.paths.selection.exists():
        raise SystemExit('selection.json exists: it is written once')
    cut = check_cut(cut)
    cur, pre, _ = _checked_plan(ds)
    p0 = _load(ds.paths.prereg(0))
    res_path = ds.paths.run_file('plan-result.json')
    confirmation, d_used, nominated = None, [], None
    if cut_plan:
        if res_path.exists():
            raise SystemExit('plan-result.json exists: the plan ran, select without cut_plan')
        reason = 'контракт §4 п. 4/5: план не начат к сроку; SEL = ALL_P без плана и без руки-близнеца'
        tw = {'family': None, 'card': None, 'replace': None}
    else:
        res = _load(res_path, 'run analyze first')
        nominated = list(res['D'])
        if not p0['gate']:
            reason = f"prereg-0: power gate failed (power {p0['power']:.3f} < {D.POWER_GATE})"
        elif not res['calibration']['passed']:
            reason = 'plan: calibration failed'
        elif not nominated:
            reason = 'plan: D is empty'
        else:
            specs = confirm_specs(cur, nominated)
            if _load(ds.paths.queue('confirm'), 'analyze writes it') != specs:
                raise SystemExit('queue-confirm.json is not the confirmation of D')
            names = [s['name'] for s in specs]
            y = broker.y_select(ds, names)[names]
            k = len(roles.CONFIRM_SEEDS)
            confirmation = D.confirm([y[n] for n in names[:k]], [y[n] for n in names[k:]],
                                     groups=D.users_of(y.index), n_boot=roles.N_BOOT, seed=roles.BOOT_SEED)
            if confirmation['confirmed']:
                d_used, reason = nominated, 'D confirmed: ALL_P minus D'
            else:
                reason = 'D not confirmed'
        tw = twin_arm(pre, res['mechanism'], exclude=d_used)
    selection = {'SEL': SEL_MINUS if d_used else SEL_ALL, 'D': d_used, 'nominated': nominated, 'reason': reason,
                 'confirmation': confirmation, 'twin_arm': tw, 'tables': _arm_tables(cur, d_used, tw['replace']),
                 'cut': cut, 'cut_plan': bool(cut_plan), **_shas(ds), 'test': REPEATED}
    _save_new(ds.paths.selection, selection)
    return selection


# ---------------------------------------------------------------- C_test

def test_specs(curation: dict, selection: dict, selection_sha256: str) -> list[dict]:
    """The C_test specs of roles.TEST_FITS (+ roles.TEST_FITS_ALLP when D is not empty; no TWIN without a twin
    arm) minus the arms of selection['cut'], phase test, each with selection_sha256. selection['tables'] is
    required and must equal the tables of the curation, D and the twin arm."""
    if not re.fullmatch(r'[0-9a-f]{64}', selection_sha256 or ''):
        raise ValueError('selection_sha256 must be a sha256 hex digest')
    if not isinstance(selection.get('tables'), dict):
        raise ValueError('selection.json has no tables')
    d = list(selection.get('D') or [])
    tables = _arm_tables(curation, d, (selection.get('twin_arm') or {}).get('replace'))
    if selection['tables'] != tables:
        raise ValueError('selection.json tables differ from the curation, D and the twin arm')
    cut = set(check_cut(selection.get('cut')))
    fits = dict(roles.TEST_FITS)
    if d:
        fits |= roles.TEST_FITS_ALLP
    return [_spec(TEST_PHASE, arm, s, None, tables[arm], None, selection_sha256)
            for arm, seeds in fits.items() if arm in tables and arm not in cut for s in seeds]


def test_queue(ds: roles.Dataset) -> list[dict]:
    """queue-test.json from curation.json, selection.json and the test.started marker (broker.marker); refuses
    without the marker, with another selection sha, or when curation.json, prereg-2.json or plan-result.json
    changed after selection.json."""
    cur = _load(ds.paths.run_file('curation.json'))
    selection = _load(ds.paths.selection, 'run select first')
    _check_bound(ds, selection)
    sha = broker.selection_sha(ds)
    m = broker.marker(ds)
    if not m:
        raise SystemExit('no test.started marker: broker.start_test comes after the owner\'s «да»')
    if m.get('selection_sha256') != sha:
        raise SystemExit('selection.json differs from the one named by test.started')
    try:
        specs = test_specs(cur, selection, sha)
    except ValueError as e:
        raise SystemExit(f'selection.json: {e}') from None
    _save_new(ds.paths.queue('test'), specs)
    return specs


def _contrast(y: pd.DataFrame, a: list[str], b: list[str], groups) -> dict:
    """mean(b - a) over seeds, two-level bootstrap (users, then seeds), 2.5/97.5% and the per-seed means."""
    d = np.vstack([(y[bb] - y[aa]).to_numpy(dtype=float) for aa, bb in zip(a, b)])
    reps = D.two_level(d, groups=groups, n_boot=roles.N_BOOT, seed=roles.BOOT_SEED)
    return {'d': float(d.mean()), 'ci95': [float(np.percentile(reps, 2.5)), float(np.percentile(reps, 97.5))],
            'by_seed': [float(v) for v in d.mean(axis=1)], 'a': list(a), 'b': list(b)}


def mechanism_repeat(y: pd.DataFrame, sel: list[str], twin: list[str], sign: float, n_boot: int = roles.N_BOOT,
                     seed: int = roles.BOOT_SEED) -> dict:
    """Delta_tw(s) = SEL(s) - twin(s) on C_test over the same seeds; 'repeated' if the mean has the sign of
    beta_g - beta_twin and the one-sided 95% bound of design.two_level (users, then seeds) does not cross 0."""
    if not sel or len(sel) != len(twin):
        raise ValueError('SEL and the twin arm need the same non-zero number of seeds')
    d = np.vstack([(y[s] - y[t]).to_numpy(dtype=float) for s, t in zip(sel, twin)])
    if not np.isfinite(d).all():
        raise ValueError('non-finite per-query values')
    reps = D.two_level(d, groups=D.users_of(y.index), n_boot=n_boot, seed=seed)
    delta = float(d.mean())
    lower, upper = (float(v) for v in np.percentile(reps, [5, 95]))
    s = float(np.sign(sign))
    repeated = bool((s > 0 and delta > 0 and lower > 0) or (s < 0 and delta < 0 and upper < 0))
    return {'delta': delta, 'lower': lower, 'upper': upper, 'by_seed': [float(v) for v in d.mean(axis=1)],
            'sign': s, 'repeated': repeated, 'n_boot': n_boot, 'seed': seed}


def mechanism_class(row: dict, repeated: bool) -> str:
    """Contract §3.3: t > 2 on S0-select and the sign repeated -> established; t <= 2, beta_g > 0 and t_g > 2 ->
    form without mechanism; otherwise not distinguished."""
    if row['t'] > D.T_MECHANISM:
        return D.MECHANISM if repeated else D.NOT_DISTINGUISHED
    if row['beta'] > 0 and row['t_family'] > D.T_MECHANISM:
        return D.FORM
    return D.NOT_DISTINGUISHED


def _fit(arm: str, seed: int) -> str:
    return f'{TEST_PHASE}-{arm}-{int(seed)}'


# what -> (arm a, arm b, seeds): b - a, descriptive (REES46 read_val / read_test, contract §1 item 2, §3.3)
CONTRASTS = {
    'H+r⁺ − H+r (кривая объёма)': ('Hr', 'Hrp', roles.TEST_FITS['Hr']),
    'ALL_P − H+r (вклад совета)': ('Hr', 'ALLP', roles.TEST_FITS_ALLP['ALLP']),
    'SEL − H+r': ('Hr', 'SEL', roles.TEST_FITS['Hr']),
    'SEL − ALL_P (вычитание D)': ('ALLP', 'SEL', roles.TEST_FITS_ALLP['ALLP']),
    'SEL − рука-близнец (механизм)': ('TWIN', 'SEL', roles.TEST_FITS['TWIN']),
    'H+Rb2 − H+Rb1 (генерация и ширина)': ('Rb1', 'Rb2', roles.TEST_FITS['Rb1']),
    'H+Rb1 − H+r (зерно 7)': ('Hr', 'Rb1', roles.TEST_FITS['Rb1']),
    'H+Rb2 − H+r (зерно 7)': ('Hr', 'Rb2', roles.TEST_FITS['Rb2']),
}


def read_test(ds: roles.Dataset) -> dict:
    """broker.c_test(every fit of queue-test.json) -> test.json {queries, mean per fit, h1 (design.h1 of SEL vs
    Hrp over roles.TEST_SEEDS), mechanism repeat and class, descriptive contrasts (CONTRASTS), target shares
    (broker.target_shares)}; the test is called repeated everywhere (contract §0).

    Before any read: the code identity of prereg-2, the files selection.json is bound to, and queue-test.json
    exactly test_specs (the cut of selection.json applied). The one C_test read is kept (TEST_READ under
    Dataset.paths.out) and reused; a c_test record in reads.jsonl without the kept file stops (§9.5)."""
    cur = _load(ds.paths.run_file('curation.json'))
    selection = _load(ds.paths.selection)
    _check_bound(ds, selection)
    _same_code(ds, _load(ds.paths.prereg(2)))
    sha = broker.selection_sha(ds)
    q = _load(ds.paths.queue('test'), 'run test-queue first')
    try:
        expected = test_specs(cur, selection, sha)
    except ValueError as e:
        raise SystemExit(f'selection.json: {e}') from None
    if q != expected:
        raise SystemExit('queue-test.json is not the C_test queue of selection.json (its cut included)')
    names = [s['name'] for s in q]
    kept = ds.paths.out / TEST_READ.format(sha=sha[:16])
    if kept.exists():
        y = _kept(kept)
        if list(y.columns) != names:
            raise SystemExit(f'{kept}: the kept C_test read has fits {list(y.columns)}, not {names}')
    else:
        if any(r.get('what') == 'c_test' for r in broker.reads(ds)):
            raise SystemExit(f'C_test was read already (reads.jsonl) and {kept.name} is missing: no second read')
        y = broker.c_test(ds, names)[names]
        _keep(kept, y)
    groups = D.users_of(y.index)
    have = set(y.columns)
    out = {'test': REPEATED, 'selection_sha256': sha, 'queries': int(len(y)), 'users': int(len(set(groups))),
           'mean': {c: float(y[c].mean()) for c in names},
           'h1': D.h1([y[_fit('Hrp', s)] for s in roles.TEST_SEEDS], [y[_fit('SEL', s)] for s in roles.TEST_SEEDS],
                      groups=groups, n_boot=roles.N_BOOT, seed=roles.BOOT_SEED),
           'contrasts': {}, 'mechanism': None, 'cut': list(selection.get('cut') or [])}
    for what, (a, b, seeds) in CONTRASTS.items():
        fa, fb = [_fit(a, s) for s in seeds], [_fit(b, s) for s in seeds]
        if set(fa + fb) <= have:
            out['contrasts'][what] = _contrast(y, fa, fb, groups)
    tw = selection.get('twin_arm') or {}
    if tw.get('family'):
        rows = [m for m in _load(ds.paths.run_file('plan-result.json'))['mechanism'] if m['family'] == tw['family']]
        if len(rows) != 1:
            raise SystemExit(f"plan-result.json has no mechanism row of {tw['family']}")
        row = rows[0]
        twin_fits = [_fit('TWIN', s) for s in roles.TEST_FITS['TWIN']]
        if set(twin_fits) <= have:
            rep = mechanism_repeat(y, [_fit('SEL', s) for s in roles.TEST_FITS['TWIN']], twin_fits, row['diff'])
            cls = mechanism_class(row, rep['repeated'])
        else:
            rep, cls = None, D.NOT_DISTINGUISHED + ' (рука-близнец срезана, контракт §4)'
        out['mechanism'] = {'family': tw['family'], 'card': tw['card'], 't_select': row['t'], 'diff': row['diff'],
                            'repeat': rep, 'class': cls}
    out['target_shares'] = broker.target_shares(ds)
    _save(ds.paths.run_file('test.json'), out)
    return out
