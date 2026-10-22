"""H9–H11 of the 23.10 day on REES46 2019, half A of val only (council/runs/side/h9.md, h10.md, h11.md; the shared
stand, the path check and the commands are in h11.md, «Общий стенд H9–H11» and «Проверка пути»).

  path  two points of the new code against their references on A, max|Δ| = 0 required: side_path_H_s0 (the config of
        q2_d8) and side_path_r6base_s0 (agent_night20_r6_base); artifacts/side/t1-path/, t1-path-result.json. H9–H11
        start only after a passed path check with the same code stamp.
  h9    H+ tuning: rsm 0.5 / 0.3, depth 10, l2 3 / 30 on seed (2026, 0) against grid_Hp_s0; at most two passing arms
        get seed (7, 1); stage 3 (H with the winning setting) only on «недонастроен».
  h10   early stopping: a 1500-tree scan of H and H+ fit on train anchors up to 03.11, staged_predict(RawFormulaVal,
        eval_period=50) over the tail 04–07.11, N* and N_full; a refit on two seeds when |N_full - 500| >= 100.
  h11   group acceptance of the agent tables (groups of 5 = the agent's rounds; --groups 10 | 15 is the owner's
        variant), arms H, step, all, group and rules 1–5.

Recipe of every new fit, as task1.placebo.run: exp._read('train', days) (h10 scan: rows with anchor <= 2019-11-03 by
a boolean mask, order kept) -> exp.sample_train -> exp._cache.clear() -> exp.with_extra -> `fit` (= exp.fit, plus
`rsm` when the config has it, without writing CatBoost files) -> val a day at a time through `read_days`, which keeps
the rows of half A only (exp.half) before anything is joined or scored. Half B of val is never scored here, and
reading it is not implemented: the conditional B rules of h9.md and h11.md need the owner's literal «да» and a
separate step. Models of new fits are saved to artifacts/side/<h>/models/<name>.cbm for that case.

Reads: day tables of train and val only (`read_days` refuses any other split and any anchor outside 15.10–13.11.2019,
before a file is opened; the test days 18–28.11 lie in the same directory), the extra tables, grid.json and the
configs (`cfg`, `features`) of the reused fits in artifacts/task1/v2/exp/runs.jsonl, and their per-query files with
`WHERE half = 'A'`. Never refit, test, 2020, a sealed directory, final.json or test.started.

Writes only artifacts/side/<h>/ (<name>.A.parquet, models/<name>.cbm, runs.jsonl, scan-<name>.json) and
council/runs/side/<h>-result.json, through council.side.Out (paths outside them, inside artifacts/task1 or
artifacts/xfer, or naming a sealed directory are refused). TASK1_PERIOD must be 2019.

Guard (council.side, unchanged; two thin wrappers here):
- the whole run holds council.side.heavy_step('<h>', 'rees46-2019') (the shared heavy lock, journalled in the side
  journal council/runs/side/queue.jsonl, so the light gate of H13 sees the peak); before every fit `check_2019`:
  council.side.check() plus the 2019 task1 heavy processes (task1.exp/placebo/replicate/model), which
  council.xfer.queue.FOREIGN does not list;
- `snapshot` lists artifacts/task1/v2, artifacts/task1/v2020, artifacts/xfer and task1/runs without descending into
  any `sealed` directory (council.side.protected_snapshot lists them); a change under artifacts/task1/v2 or task1/runs
  makes the result `refused` and exits 3, a change under v2020 or xfer is listed for reconciliation with the owners'
  journals, as h11.md says.
A real run starts only with this module, its tests, council/side/__init__.py and the three prereg committed; the code
stamp (sha256 of task1/{exp,model,period}.py, council/side/__init__.py and this file) and `peak_rss_gb` go into every
record; a change of the stamp between fits stops the run. A rerun skips a fit whose files and record carry the same
config and stamp; a file without a record or with another config stops it.

  TASK1_PERIOD=2019 .venv/bin/python -m council.side.task1_side {path|h9|h10|h11} --dry
  TASK1_PERIOD=2019 .venv/bin/python -X faulthandler -m council.side.task1_side h11 [--groups 10|15]
"""
from __future__ import annotations

import os
import sys

if os.environ.get('TASK1_PERIOD', '2019') != '2019':
    raise SystemExit(f"TASK1_PERIOD={os.environ['TASK1_PERIOD']!r}: H9–H11 run on REES46 2019 only")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import importlib.metadata  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from datetime import date  # noqa: E402
from fractions import Fraction  # noqa: E402
from pathlib import Path  # noqa: E402

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from catboost import CatBoostClassifier, Pool  # noqa: E402

from council import side as S  # noqa: E402
from task1 import exp  # noqa: E402
from task1 import model as M  # noqa: E402
from task1 import period as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATASET = 'rees46-2019'
DAYS6 = P.ART / 'days6'
REF_DIR = exp.OUT  # artifacts/task1/v2/exp: reused fits, read only
GRID_JSON = ROOT / 'task1' / 'runs' / 'grid-2026-10-20' / 'grid.json'
SPLITS_OK = ('train', 'val')
FIRST_ANCHOR, LAST_ANCHOR = date(2019, 10, 15), date(2019, 11, 13)
HALF_A = 'A'
SEALED = 'sealed'
METRICS = ('ndcg', 'recall', 'purchase_ndcg', 'purchase_recall')
CONFIG_KEYS = set(exp.DEFAULT) | {'rsm'}
BOOT = dict(n=2000, seed=2026)

DFS = ['dfs_p', 'dfs_c', 'dfs_b', 'dfs_u']
AGENT = ['agent_night20_' + t for t in (
    'r1p1_first_touch_conversion', 'r1p2_coacq_cf', 'r1p3_buyer_price_profile', 'r1p4_new_reach',
    'r1p5_cp_staleness', 'r2p1_cmp_session_win_lift', 'r2p2_cp_category_complement', 'r2p3_acq_seed_coview_cf',
    'r2p4_revisit_consideration', 'r2p5_view_dwell_time', 'r3p1_view_session_last_choice',
    'r3p2_intraday_momentum_12h', 'r3p3_user_user_cf_acq', 'r3p4_brand_cat_price_sibling',
    'r3p5_category_search_depth', 'r4p1_acq_regularity_7d', 'r4p2_cat_acq_concentration',
    'r4p3_weekday_seasonality_14d', 'r4p4_cat_to_item_transition', 'r4p5_brand_switch_transition',
    'r5p1_cf_xday_new_acq_transition', 'r5p2_cf_next_view_adjacency', 'r5p3_cf_converting_session_coview',
    'r5p4_uc_nextday_continuation', 'r5p5_cf_considered_seed_coview', 'r6p1_older_view_seed_coview',
    'r6p2_dwell_seed_coview', 'r6p3_abandoned_cart_seed_coview', 'r6p4_user_level_cooccurrence_cf',
    'r6p5_fresh_2d_coview_graph')]
HP_EXTRA = DFS + AGENT  # the 34 tables of grid_Hp in the order of grid.json
P5 = 'agent_night20_r5p5_cf_considered_seed_coview'
ROUNDS = {r: AGENT[5 * (r - 1):5 * r] for r in range(1, 7)}
GROUPINGS = {5: [[1], [2], [3], [4], [5], [6]], 10: [[1, 2], [3, 4], [5, 6]], 15: [[1, 2, 3], [4, 5, 6]]}
SEEDS = [dict(seed=2026, neg_seed=0), dict(seed=7, neg_seed=1)]

H = dict(depth=8)  # days are set by the context (days6)
HP = dict(depth=8, extra=HP_EXTRA)
R6BASE = dict(depth=8, extra=[P5])
HAG = dict(depth=8, extra=AGENT)
EXPECTED = {  # the table of reused fits in h11.md: overrides of exp.DEFAULT (days: days6) and number of features
    'q2_d8': (H | SEEDS[0], 80),
    'q3_d8_s1': (H | SEEDS[1], 80),
    'agent_night20_r6_base': (R6BASE | SEEDS[0], 82),
    'pl19_Hag_s0': (HAG | SEEDS[0], 146),
    'pl19_Hag_s1': (HAG | SEEDS[1], 146),
    'grid_Hp_s0': (HP | SEEDS[0], 274),
    'grid_Hp_s1': (HP | SEEDS[1], 274),
    'grid_d10_s0': (dict(depth=10) | SEEDS[0], 80),
}
H_REF = ['q2_d8', 'q3_d8_s1']
HP_REF = ['grid_Hp_s0', 'grid_Hp_s1']
STEP_REF = 'agent_night20_r6_base'
ALL_REF = ['pl19_Hag_s0', 'pl19_Hag_s1']

PREFIX = {'path': 'side_path_', 'h9': 'h9_', 'h10': 'h10_', 'h11': 'h11_'}
OUT_NAME = {'path': 't1-path', 'h9': 'h9', 'h10': 'h10', 'h11': 'h11'}
PATH_POINTS = {'side_path_H_s0': ('q2_d8', H | SEEDS[0]), 'side_path_r6base_s0': (STEP_REF, R6BASE | SEEDS[0])}

H9_ARMS = [('h9_rsm05', {'rsm': 0.5}), ('h9_rsm03', {'rsm': 0.3}), ('h9_d10', {'depth': 10}),
           ('h9_l2_3', {'l2': 3}), ('h9_l2_30', {'l2': 30})]
H9_PASS = 0.0008
H10_SCAN = dict(iterations=1500, eval_period=50)
H10_FIT_LAST = date(2019, 11, 3)
H10_TAIL = [date(2019, 11, d) for d in (4, 5, 6, 7)]
H10_BASE_ITERATIONS = 500
H10_MIN_SHIFT = 100
H10_CAP = 2000
H10_STEP = 50
H10_PASS = 0.0008
H11_PASS = 0.0005
ESTABLISHED = 0.001

COMMITTED = ('council/side/task1_side.py', 'council/tests/test_side_task1.py', 'council/side/__init__.py',
             'council/runs/side/h9.md', 'council/runs/side/h10.md', 'council/runs/side/h11.md')
STAMPED = ('task1/exp.py', 'task1/model.py', 'task1/period.py', 'council/side/__init__.py',
           'council/side/task1_side.py')
SNAPSHOT_ROOTS = {'artifacts/task1/v2': 'incident', 'task1/runs': 'incident',
                  'artifacts/task1/v2020': 'reconcile', 'artifacts/xfer': 'reconcile'}
TASK1_HEAVY = re.compile(r'-m\s*task1\.(exp|placebo|replicate|model|build|final|leakcheck)\b'
                         r'|task1/(exp|placebo|replicate|model|build|final|leakcheck)\.py\b')
SKIPS = ('stage3', 'refit_H')  # --skip: the cuts 2 and 3 of h11.md, «Что режется первым»
DEVIATIONS = [  # from the prereg, written into every *-result.json
    'журнал heavy — общий council/runs/side/queue.jsonl (council.side.heavy_step), а не artifacts/side/<h>/heavy.jsonl',
    'свой снимок под замком (artifacts/task1/v2, v2020, artifacts/xfer, task1/runs без каталогов sealed) — в '
    'дополнение к снимкам find/stat из команд prereg',
    'ключ retrain в результате H10 = перефит prereg',
    '--skip stage3 | refit_H = пп. 2–3 «Что режется первым» (h11.md)',
    'имя замка проверки пути — side t1-path',
    'h10 --dry считает Q_full, Q_sub и запросы хвоста (только anchor, user_id; за световым гейтом); --no-counts '
    'пропускает подсчёт',
]
LIBS = ('pandas', 'numpy', 'duckdb', 'catboost')


# ---------------------------------------------------------------- context

@dataclasses.dataclass
class Ctx:
    """One subcommand's run: where it reads and writes, and the hooks tests replace."""
    h: str
    out: S.Out
    days: Path = DAYS6
    ref_dir: Path = REF_DIR
    over: dict = dataclasses.field(default_factory=dict)  # tests only: applied under every config
    scan: dict = dataclasses.field(default_factory=lambda: dict(H10_SCAN))
    heavy_kw: dict = dataclasses.field(default_factory=dict)
    wait: bool = True
    check_fn: object = None
    stamp_fn: object = None
    snapshot_roots: dict | None = None
    commit: str | None = None
    stamp: dict | None = None
    groups: int = 5
    skip: tuple = ()  # 'stage3' (h9), 'refit_H' (h10): the cuts of h11.md, «Что режется первым»

    def __post_init__(self):
        if self.h not in PREFIX:
            raise S.Refused(f'unknown subcommand {self.h!r}')
        self.check_fn = self.check_fn or check_2019
        self.stamp_fn = self.stamp_fn or code_stamp
        if self.snapshot_roots is None:
            self.snapshot_roots = {ROOT / k: v for k, v in SNAPSHOT_ROOTS.items()}
        if self.stamp is None:
            self.stamp = self.stamp_fn()


def make_out(h: str, art_root=None, runs_root=None) -> S.Out:
    return S.Out(OUT_NAME[h], art_root, runs_root)


def wpath(ctx: Ctx, *parts, runs: bool = False) -> Path:
    """A path to write, through Out.path (artifacts/side/<h>/ or council/runs/side/ only), never a sealed one."""
    p = ctx.out.path(*parts, runs=runs)
    if SEALED in Path(os.path.abspath(p)).parts or SEALED in p.resolve().parts:
        raise S.Refused(f'{p}: a path through a {SEALED} directory')
    return p


def result_name(ctx: Ctx) -> str:
    if ctx.h == 'h11' and ctx.groups != 5:
        return f'h11-L{ctx.groups}-result.json'
    return f'{OUT_NAME[ctx.h]}-result.json'


def require_2019() -> None:
    if P.PERIOD != '2019' or P.ART.resolve() != (ROOT / 'artifacts' / 'task1' / 'v2').resolve():
        raise SystemExit(f'TASK1_PERIOD={P.PERIOD}: H9–H11 run on REES46 2019 only')


# ---------------------------------------------------------------- the one reader of day tables

def guard_days(split: str, days_dir, days) -> None:
    """Refuse a split other than train/val, a sealed directory and any anchor outside 15.10–13.11.2019."""
    if split not in SPLITS_OK:
        raise S.Refused(f'split {split!r}: only {SPLITS_OK} are read')
    if SEALED in Path(os.path.abspath(days_dir)).parts or SEALED in Path(days_dir).resolve().parts:
        raise S.Refused(f'{days_dir}: a {SEALED} directory')
    allowed = set(M.days(split))
    for d in days:
        if not isinstance(d, date) or not FIRST_ANCHOR <= d <= LAST_ANCHOR or d not in allowed:
            raise S.Refused(f'anchor {d}: outside {split} {FIRST_ANCHOR}..{LAST_ANCHOR}')


def read_days(split: str, days_dir, day: date | None = None):
    """The only way this module reads day tables. day None: the train pool of exp._read (train only). A day: that day
    by exp.read_day; for val only the rows of half A are returned. The guard runs before any file is opened."""
    days = list(M.days(split)) if split in SPLITS_OK and day is None else [day]
    guard_days(split, days_dir, days)
    if day is None:
        if split != 'train':
            raise S.Refused('the pool is read for train only')
        return exp._read(split, str(days_dir))
    df = exp.read_day(day, str(days_dir))
    if split == 'val':
        df = df[exp.half(df['user_id'].to_numpy()) == HALF_A].reset_index(drop=True)
    return df


def count_queries(days_dir, days, gate=None) -> int:
    """Distinct (anchor, user_id) of train days, reading those two columns only (h10 --dry); `gate` (the light gate
    of council.side) runs after the guard and before the read."""
    days = list(days)
    guard_days('train', days_dir, days)
    if gate is not None:
        gate()
    files = [str(Path(days_dir) / f'{d}.parquet') for d in days]
    return int(duckdb.sql(f'SELECT count(*) FROM (SELECT DISTINCT anchor, user_id FROM read_parquet({files}))')
               .fetchone()[0])


# ---------------------------------------------------------------- configs

def config(ctx: Ctx, over: dict) -> dict:
    """exp.DEFAULT | test overrides | the declared overrides, days of the context; JSON-normal."""
    cfg = exp.DEFAULT | {'days': str(ctx.days)} | ctx.over | over
    return json.loads(json.dumps(cfg))


def validate(ctx: Ctx, name: str, cfg: dict) -> None:
    if not name.startswith(PREFIX[ctx.h]) or '/' in name:
        raise S.Refused(f'{name}: a {ctx.h} fit is named {PREFIX[ctx.h]}*')
    unknown = sorted(set(cfg) - CONFIG_KEYS)
    if unknown or cfg['loss'] != 'Logloss' or cfg['half_life']:
        raise S.Refused(f'{name}: unknown keys {unknown}, loss {cfg["loss"]}, half_life {cfg["half_life"]}')
    for p in [cfg['days']] + [str(M.EXTRA / e) for e in cfg['extra']]:
        if SEALED in Path(os.path.abspath(p)).parts or SEALED in Path(p).resolve().parts:
            raise S.Refused(f'{name}: {p} lies in a {SEALED} directory')


def _same_days(a, b) -> bool:
    ra = Path(a) if Path(a).is_absolute() else ROOT / a
    rb = Path(b) if Path(b).is_absolute() else ROOT / b
    return ra.resolve() == rb.resolve()


def reused_records(ctx: Ctx) -> dict:
    """name -> {cfg, features} of the last record of each reused fit in ref_dir/runs.jsonl (metrics are not kept)."""
    out = {}
    path = ctx.ref_dir / 'runs.jsonl'
    if not path.exists():
        return out
    for line in path.read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if r.get('name') in EXPECTED:
            out[r['name']] = {'cfg': r['cfg'], 'features': r['features']}
    return out


def check_reused(ctx: Ctx, names, records: dict | None = None) -> dict:
    """Every reused fit must have its last record with the expected config (days compared resolved), the expected
    number of features and its per-query file. Returns name -> 'ok' or the reason."""
    records = reused_records(ctx) if records is None else records
    res = {}
    for n in names:
        over, feats = EXPECTED[n]
        want = config(ctx, over)
        r = records.get(n)
        if r is None:
            res[n] = 'no record in runs.jsonl'
            continue
        got = dict(r['cfg'])
        if set(got) != set(want) or not _same_days(got.pop('days'), want['days']) or \
                got != {k: v for k, v in want.items() if k != 'days'}:
            res[n] = 'config differs from the table of expected configs'
        elif r['features'] != feats:
            res[n] = f"{r['features']} features, expected {feats}"
        elif not (ctx.ref_dir / f'{n}.parquet').exists():
            res[n] = 'no per-query file'
        else:
            res[n] = 'ok'
    return res


def require_reused(ctx: Ctx, names) -> dict:
    res = check_reused(ctx, names)
    bad = {k: v for k, v in res.items() if v != 'ok'}
    if bad:
        raise SystemExit(f'reused fits do not match the table of expected configs: {bad}')
    return res


def check_grid_order(path: Path = GRID_JSON) -> dict:
    """The 34 tables of grid_Hp and the 30 of grid_F1agent in grid.json must be HP_EXTRA and AGENT, in order."""
    g = {x['name']: x for x in json.loads(Path(path).read_text(encoding='utf-8'))}
    ok = {'grid_Hp_s0': g['grid_Hp_s0'].get('extra') == HP_EXTRA,
          'grid_F1agent_s0': g['grid_F1agent_s0'].get('extra') == AGENT}
    if not all(ok.values()):
        raise SystemExit(f'the table lists differ from grid.json: {ok}')
    return ok


# ---------------------------------------------------------------- identity, commit, processes, snapshot

def code_stamp() -> dict:
    return {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in STAMPED}


def git(*args) -> str:
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def commit_state() -> dict:
    dirty = git('status', '--porcelain', '--', *COMMITTED)
    return {'clean': not dirty.strip(), 'dirty': dirty.splitlines(), 'head': git('rev-parse', 'HEAD').strip()}


def committed() -> str:
    st = commit_state()
    if not st['clean']:
        raise SystemExit('commit the prereg, this module, its tests and council/side/__init__.py first:\n'
                         + '\n'.join(st['dirty']))
    return st['head']


def libraries() -> dict:
    out = {}
    for n in LIBS:
        try:
            out[n] = importlib.metadata.version(n)
        except importlib.metadata.PackageNotFoundError:
            out[n] = None
    return out


def check_2019(procs=None, own=None) -> None:
    """council.side.check() and, for 2019, no task1 heavy process (exp, placebo, replicate, model) besides this one."""
    from council.xfer import queue as Q
    S.check(procs, own)
    procs = Q.processes() if procs is None else procs
    own = {os.getpid(), os.getppid()} if own is None else set(own)
    found = [pid for pid, _, cmd in procs if pid not in own and TASK1_HEAVY.search(cmd)]
    if found:
        raise Q.Busy(f'task1 heavy processes run: {found}')


def snapshot(roots) -> dict:
    """path -> [size, mtime_ns] of every file under each root, never descending into a directory named sealed."""
    out = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            out[str(root)] = ['missing', 0]
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d != SEALED)
            for n in filenames:
                p = os.path.join(dirpath, n)
                try:
                    s = os.lstat(p)
                except FileNotFoundError:
                    continue
                out[p] = [s.st_size, s.st_mtime_ns]
    return out


def snapshot_verdict(before: dict, roots: dict) -> dict:
    d = S.protected_diff(before, snapshot(roots))
    changed = d['added'] + d['removed'] + d['changed']
    kind = lambda p: next((v for r, v in roots.items() if S.inside(Path(p), Path(r)) or p == str(r)), 'incident')
    incident = [p for p in changed if kind(p) == 'incident']
    return {'unchanged': not changed, 'incident': incident[:50], 'n_incident': len(incident),
            'reconcile': [p for p in changed if kind(p) != 'incident'][:50], 'entries': len(before),
            'roots': {str(r): v for r, v in roots.items()}}


# ---------------------------------------------------------------- fit and score

def fit(train, features: list, cfg: dict) -> CatBoostClassifier:
    """exp.fit for a Logloss config, plus `rsm` when the config has the key (absent: not passed at all)."""
    params = dict(iterations=cfg['iterations'], depth=cfg['depth'], learning_rate=cfg['lr'], l2_leaf_reg=cfg['l2'],
                  random_seed=cfg['seed'], thread_count=cfg['threads'], verbose=0, allow_writing_files=False)
    if 'rsm' in cfg:
        params['rsm'] = cfg['rsm']
    pool = Pool(train[features], train.label, cat_features=[c for c in M.CAT if c in features])
    m = CatBoostClassifier(loss_function='Logloss', **params)
    m.fit(pool)
    return m


def score_a(m, features: list, cfg: dict):
    """Per-query metrics of val half A, a day at a time, as exp.run computes them."""
    parts = []
    for d in M.days('val'):
        val = exp.with_extra(read_days('val', cfg['days'], d), cfg['extra'])
        score = M.predict(m, val, features)
        pq = M.per_query(val, score)
        pq['half'] = HALF_A
        parts.append(pq.join(M.per_query(val, score, purchase=True).add_prefix('purchase_'), how='left'))
        del val
    return pd.concat(parts).sort_index().reset_index()


def stage_trees(j: int, every: int, trees: int) -> int:
    """Trees behind stage j (0-based) of staged_predict(eval_period=every)."""
    return min((j + 1) * every, trees)


def staged_ndcg(m, frame, features: list, every: int) -> dict:
    """k -> per-query NDCG@20 of one frame for k = every, 2*every, ... (RawFormulaVal)."""
    out = {}
    stages = m.staged_predict(frame[features], prediction_type='RawFormulaVal', eval_period=every)
    for j, raw in enumerate(stages):
        out[stage_trees(j, every, m.tree_count_)] = M.per_query(frame, raw)['ndcg']
    return out


def scan_tail(m, features: list, cfg: dict, every: int, days=H10_TAIL) -> dict:
    per_k, queries = {}, {}
    for d in days:
        frame = exp.with_extra(read_days('train', cfg['days'], d), cfg['extra'])
        for k, s in staged_ndcg(m, frame, features, every).items():
            per_k.setdefault(k, []).append(s)
        queries[str(d)] = int(next(iter(per_k.values()))[-1].shape[0])
        del frame
    curve = {k: float(pd.concat(v).mean()) for k, v in sorted(per_k.items())}
    return {'curve': curve, 'tail_queries': queries, 'tail_queries_total': sum(queries.values())}


def n_star(curve: dict) -> int:
    best = max(curve.values())
    return min(k for k, v in curve.items() if v == best)


def n_full(n: int, q_full: int, q_sub: int) -> int:
    """N* * Q_full / Q_sub to the nearest multiple of 50 (half up), at most 2000."""
    x = Fraction(n * q_full, q_sub * H10_STEP)
    return min(int((x + Fraction(1, 2)).__floor__()) * H10_STEP, H10_CAP)


def last_records(ctx: Ctx) -> dict:
    p = ctx.out.art / 'runs.jsonl'
    if not p.exists():
        return {}
    return {r['name']: r for r in map(json.loads, p.read_text(encoding='utf-8').splitlines())}


def files_of(ctx: Ctx, name: str, kind: str) -> list:
    fs = [wpath(ctx, 'models', f'{name}.cbm')]
    fs.append(wpath(ctx, f'scan-{name}.json') if kind == 'scan' else wpath(ctx, f'{name}.A.parquet'))
    return fs


def done(ctx: Ctx, name: str, cfg: dict, kind: str):
    """The record of a finished fit with the same config and stamp, None if nothing exists; anything else stops."""
    rec = last_records(ctx).get(name)
    fs = files_of(ctx, name, kind)
    if rec is None and not any(f.exists() for f in fs):
        return None
    if rec is None or rec['cfg'] != cfg or rec['code'] != ctx.stamp or not all(f.exists() for f in fs):
        raise SystemExit(f'{name}: files or a record exist with another config or code; move them aside')
    print(json.dumps({'name': name, 'skipped': 'done with the same config and code'}), flush=True)
    return rec


def ensure_stamp(ctx: Ctx) -> None:
    if ctx.stamp_fn() != ctx.stamp:
        raise SystemExit('the code changed during the run; stopped')


def fit_one(ctx: Ctx, name: str, over: dict, *, kind: str = 'A', fit_last: date | None = None) -> dict:
    """One new fit by the recipe of placebo.run. kind 'A': score val half A to <name>.A.parquet; kind 'scan': fit on
    train anchors <= fit_last and write the tail curve to scan-<name>.json. Model to models/<name>.cbm."""
    cfg = config(ctx, over)
    validate(ctx, name, cfg)
    rec = done(ctx, name, cfg, kind)
    if rec is not None:
        return rec
    ctx.check_fn()
    ensure_stamp(ctx)
    t0 = time.time()
    pool = read_days('train', cfg['days'])
    q_full = int(pool.qid.nunique())
    if fit_last is not None:
        pool = pool[(pd.to_datetime(pool.anchor) <= pd.Timestamp(fit_last)).to_numpy()]
        exp._cache.clear()  # the unfiltered pool is no longer needed; the order of the rows is kept
    q_sub = int(pool.qid.nunique())
    train = exp.sample_train(pool, cfg)
    del pool
    exp._cache.clear()  # as placebo.run: the pool is the largest frame, the joins need the room
    train = exp.with_extra(train, cfg['extra'])
    features = M.base_features(train, cfg['drop'])
    train_rows, fit_queries = len(train), int(train.qid.nunique())
    t1 = time.time()
    m = fit(train, features, cfg)
    del train
    t2 = time.time()
    extra = {}
    if kind == 'scan':
        scan = scan_tail(m, features, cfg, ctx.scan['eval_period'])
        ns = n_star(scan['curve'])
        extra = {'q_full': q_full, 'q_sub': q_sub, 'fit_last': str(fit_last), 'n_star': ns,
                 'n_full': n_full(ns, q_full, q_sub), 'edge': ns == max(scan['curve']),
                 'tail_days': [str(d) for d in H10_TAIL], **scan}
    else:
        res = score_a(m, features, cfg)
        extra = {'queries_A': len(res)}
    t3 = time.time()
    ensure_stamp(ctx)
    mp = wpath(ctx, 'models', f'{name}.cbm')
    mp.parent.mkdir(parents=True, exist_ok=True)
    m.save_model(str(mp))
    if kind == 'scan':
        ctx.out.write_json({'name': name, **extra}, f'scan-{name}.json')
    else:
        wpath(ctx, f'{name}.A.parquet')
        ctx.out.write_frame(res, f'{name}.A.parquet')
    rec = {'name': name, 'kind': kind, 'cfg': cfg, 'features': len(features), 'train_rows': train_rows,
           'fit_queries': fit_queries, 'pool_queries': q_full,
           **{k: v for k, v in extra.items() if k in ('q_sub', 'n_star', 'n_full', 'queries_A')},
           'model': mp.relative_to(ctx.out.art).as_posix(), 'peak_rss_gb': S.peak_rss_gb(), 'code': ctx.stamp,
           'commit': ctx.commit, 'libraries': libraries(), 'started': time.strftime('%Y-%m-%d %H:%M:%S',
                                                                                    time.localtime(t0)),
           'seconds': {'prepare': round(t1 - t0), 'fit': round(t2 - t1), 'predict': round(t3 - t2)}}
    p = wpath(ctx, 'runs.jsonl')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps({k: rec[k] for k in ('name', 'features', 'fit_queries', 'peak_rss_gb', 'seconds')}), flush=True)
    return rec


def scan_of(ctx: Ctx, name: str) -> dict:
    return json.loads(wpath(ctx, f'scan-{name}.json').read_text(encoding='utf-8'))


# ---------------------------------------------------------------- half A metrics and comparisons

def metrics_a(ctx: Ctx, name: str):
    """Per-query metrics of half A: a reused fit from ref_dir, a new one from artifacts/side/<h>/."""
    if name in EXPECTED:
        p = ctx.ref_dir / f'{name}.parquet'
    else:
        p = wpath(ctx, f'{name}.A.parquet')
    q = str(p).replace("'", "''")
    df = duckdb.sql(f"SELECT qid, {', '.join(METRICS)} FROM read_parquet('{q}') WHERE half = 'A'").df()
    return df.set_index('qid').sort_index()


def ndcg_a(ctx: Ctx, names) -> pd.Series:
    """Per-query NDCG@20 on A; a list of fits gives the per-query mean (the queries must agree)."""
    names = [names] if isinstance(names, str) else list(names)
    ms = [metrics_a(ctx, n)['ndcg'] for n in names]
    if not all(s.index.equals(ms[0].index) for s in ms):
        raise SystemExit(f'fits {names} differ in A queries')
    s = sum(ms) / len(ms)
    if s.isna().any():
        raise SystemExit(f'{names}: NDCG is missing for some A queries')
    return s


def boot(ctx: Ctx, ref, new) -> dict:
    """mean(new - ref) on A with M.bootstrap_diff (2000, seed 2026), unrounded."""
    a, b = ndcg_a(ctx, ref), ndcg_a(ctx, new)
    if not a.index.equals(b.index):
        raise SystemExit(f'{ref} and {new} differ in A queries')
    d, lo, hi = M.bootstrap_diff(a, b, **BOOT)
    return {'ref': ref, 'new': new, 'd': float(d), 'ci': [float(lo), float(hi)], 'queries': int(len(a))}


def path_diff(ctx: Ctx, ref: str, new: str) -> dict:
    a, b = metrics_a(ctx, ref), metrics_a(ctx, new)
    if not a.index.equals(b.index):
        return {'same_queries': False, 'queries_ref': len(a), 'queries_new': len(b), 'max_abs': None}
    mx = {}
    for c in METRICS:
        x, y = a[c].to_numpy(dtype=float), b[c].to_numpy(dtype=float)
        if not (np.isnan(x) == np.isnan(y)).all():
            mx[c] = float('inf')
        else:
            k = ~np.isnan(x)
            mx[c] = float(np.abs(x[k] - y[k]).max()) if k.any() else 0.0
    return {'same_queries': True, 'queries': int(len(a)), 'max_abs': mx}


# ---------------------------------------------------------------- subcommands: the steps

def run_path(ctx: Ctx) -> dict:
    points = {}
    for name, (ref, over) in PATH_POINTS.items():
        fit_one(ctx, name, over)
        points[name] = {'ref': ref} | path_diff(ctx, ref, name)
    ok = all(p['same_queries'] and all(v == 0 for v in p['max_abs'].values()) for p in points.values())
    return {'points': points, 'passed': bool(ok),
            'verdict': 'путь совпал с опорами на A: max|Δ| = 0' if ok else 'путь НЕ совпал: H9–H11 не запускаются'}


def run_h9(ctx: Ctx) -> dict:
    res = {'stage1': [], 'stage2': [], 'stage3': None}
    for i, (arm, axis) in enumerate(H9_ARMS, 1):
        fit_one(ctx, f'{arm}_s0', HP | SEEDS[0] | axis)
        b = boot(ctx, 'grid_Hp_s0', f'{arm}_s0')
        res['stage1'].append({'n': i, 'arm': arm, 'axis': axis, **b, 'passes': b['d'] >= H9_PASS})
    passed = sorted([r for r in res['stage1'] if r['passes']], key=lambda r: (-r['d'], r['n']))[:2]
    if not passed:
        res['verdict'] = 'H+ на A без выигрыша по rsm 0.5/0.3, глубине 10, l2 3/30'
        res['note'] = '1-й этап не прошла ни одна рука; 2-й и 3-й этапы не запускаются'
        return res
    for r in passed:
        arm, axis = r['arm'], r['axis']
        fit_one(ctx, f'{arm}_s1', HP | SEEDS[1] | axis)
        seeds = [boot(ctx, 'grid_Hp_s0', f'{arm}_s0'), boot(ctx, 'grid_Hp_s1', f'{arm}_s1')]
        mean = boot(ctx, HP_REF, [f'{arm}_s0', f'{arm}_s1'])
        res['stage2'].append({'n': r['n'], 'arm': arm, 'axis': axis, 'mean': mean, 'by_seed': seeds})
    w = sorted(res['stage2'], key=lambda r: (-r['mean']['d'], r['n']))[0]
    tuned = (w['mean']['d'] >= H9_PASS and w['mean']['ci'][0] > 0 and all(s['d'] > 0 for s in w['by_seed']))
    res['W'] = w['arm']
    if not tuned:
        res['verdict'] = 'H+ на A без выигрыша по rsm 0.5/0.3, глубине 10, l2 3/30'
        return res
    res['verdict'] = f"H+ недонастроен на A по оси {w['arm']}"
    res['note'] = ('выбрано на A из пяти рук, без B не подтверждено; эффект выбора завышает d победителя; '
                   f'установленным по протоколу считается только прирост >= ≈{ESTABLISHED}')
    if SKIPS[0] in ctx.skip:
        res['stage3'] = 'срезан (--skip stage3)'
        return res
    short = w['arm'][len('h9_'):]
    hw = []
    for i in (0, 1):
        if short == 'd10' and i == 0:
            require_reused(ctx, ['grid_d10_s0'])
            hw.append('grid_d10_s0')
            continue
        fit_one(ctx, f'h9_H_{short}_s{i}', H | SEEDS[i] | w['axis'])
        hw.append(f'h9_H_{short}_s{i}')
    res['stage3'] = {'H_W': hw, 'Hp_W': [f"{w['arm']}_s0", f"{w['arm']}_s1"],
                     'HpW_minus_HW': boot(ctx, hw, [f"{w['arm']}_s0", f"{w['arm']}_s1"]),
                     'Hp_minus_H': boot(ctx, H_REF, HP_REF), 'reading': 'описательно'}
    return res


def h10_verdict(arm: str, scan: dict, refit: dict | None) -> str:
    ns, nf = scan['n_star'], scan['n_full']
    if abs(nf - H10_BASE_ITERATIONS) < H10_MIN_SHIFT:
        return f'500 итераций у оптимума по хвосту train (N* = {ns}, N_full = {nf})'
    if refit is None:
        return 'перефит срезан'
    m = refit['mean']
    if m['d'] >= H10_PASS and m['ci'][0] > 0 and all(s['d'] > 0 for s in refit['by_seed']):
        return f'ранняя остановка даёт прирост на A при N = {nf}'
    if m['ci'][1] < 0:
        return 'ранняя остановка по хвосту train хуже 500 итераций на A'
    return 'без выигрыша на A'


def run_h10(ctx: Ctx) -> dict:
    res = {}
    for arm, base, refs in (('H', H, H_REF), ('Hp', HP, HP_REF)):
        name = f'h10_{arm}_scan_s0'
        fit_one(ctx, name, base | SEEDS[0] | {'iterations': ctx.scan['iterations']}, kind='scan',
                fit_last=H10_FIT_LAST)
        sc = scan_of(ctx, name)
        r = {'scan': {k: sc[k] for k in ('q_full', 'q_sub', 'n_star', 'n_full', 'edge', 'tail_queries_total')},
             'curve': sc['curve'], 'retrain': None}
        if sc['edge']:
            r['note'] = 'N* на краю скана: оптимум не найден в пределах скана'
        nf = sc['n_full']
        if abs(nf - H10_BASE_ITERATIONS) >= H10_MIN_SHIFT and not (arm == 'H' and SKIPS[1] in ctx.skip):
            names = [f'h10_{arm}_n{nf}_s{i}' for i in (0, 1)]
            for i, n in enumerate(names):
                fit_one(ctx, n, base | SEEDS[i] | {'iterations': nf})
            r['retrain'] = {'names': names, 'mean': boot(ctx, refs, names),
                          'by_seed': [boot(ctx, refs[i], names[i]) for i in (0, 1)]}
        r['verdict'] = h10_verdict(arm, sc, r['retrain'])
        res[arm] = r
    if res['H']['retrain'] and res['Hp']['retrain']:
        hn, hpn = res['H']['retrain']['names'], res['Hp']['retrain']['names']
        res['automation'] = {'HpN_minus_HN': boot(ctx, hn, hpn),
                             'Hp_minus_H': boot(ctx, H_REF, HP_REF), 'reading': 'описательно'}
    res['verdict'] = {arm: res[arm]['verdict'] for arm in ('H', 'Hp')}
    res['risk'] = ('хвост 04–07.11 в режиме 16–21 тыс. корзин в день, val — 63–81 тыс.; N*, лучший на хвосте, может '
                   'не быть лучшим на val')
    return res


def groups_of(size: int) -> list:
    return [[t for r in rs for t in ROUNDS[r]] for rs in GROUPINGS[size]]


def h11_name(size: int, r: int, i: int) -> str:
    return f'h11_g{r}_s{i}' if size == 5 else f'h11_L{size}_g{r}_s{i}'


def h11_rule(raw: dict, accepted: int, size: int) -> tuple:
    if accepted == 0:
        return 1, (f'группы по {size} с порогом агента не проходят: совместный сигнал не собирается и группами '
                   f'по {size}')
    d, e = raw['D']['ci'], raw['E']['ci']
    if d[1] < 0:
        return 2, 'групповой приём сохраняет часть сигнала, но меньше, чем всё сразу'
    if d[0] <= 0 <= d[1] and e[0] > 0:
        return 3, ('на A групповой приём держит сигнал наравне со всем сразу и больше пошагового; без B или нового '
                   'периода не подтверждено')
    if d[0] > 0:
        return 4, 'на A групповой приём выше всего сразу; оценка завышена отбором на A, вывода без B нет'
    return 5, 'не различено'


def run_h11(ctx: Ctx) -> dict:
    size = ctx.groups
    fit_one(ctx, 'h11_step_s1', R6BASE | SEEDS[1])
    state = list(H_REF)  # S_{r-1} for seeds 0 and 1
    tables: list = []
    rounds = []
    for r, g in enumerate(groups_of(size), 1):
        cand = [t for t in AGENT if t in set(tables) | set(g)]
        s0 = h11_name(size, r, 0)
        fit_one(ctx, s0, H | SEEDS[0] | {'extra': cand})
        b0 = boot(ctx, state[0], s0)
        row = {'round': r, 'group': g, 'extra': len(cand), 'by_seed': [b0], 'accepted': False}
        if b0['d'] > H11_PASS and b0['ci'][0] > 0:
            s1 = h11_name(size, r, 1)
            fit_one(ctx, s1, H | SEEDS[1] | {'extra': cand})
            b1 = boot(ctx, state[1], s1)
            row['by_seed'].append(b1)
            row['mean_of_seeds'] = boot(ctx, state, [s0, s1])  # descriptive
            if b1['d'] > H11_PASS and b1['ci'][0] > 0:
                row['accepted'] = True
                state, tables = [s0, s1], cand
        rounds.append(row)
    accepted = sum(r['accepted'] for r in rounds)
    group, step, all_ = state, [STEP_REF, 'h11_step_s1'], ALL_REF
    raw = {'D': boot(ctx, all_, group), 'E': boot(ctx, step, group),
           'to_H': {'step': boot(ctx, H_REF, step), 'all': boot(ctx, H_REF, all_), 'group': boot(ctx, H_REF, group)}}
    rule, verdict = h11_rule(raw, accepted, size)
    return {'groups': size, 'rounds': rounds, 'accepted': accepted, 'G_star': {'fits': group, 'tables': tables},
            'arms': {'H': H_REF, 'step': step, 'all': all_, 'group': group}, **raw, 'rule': rule,
            'verdict': verdict, 'note': f'разности меньше ≈{ESTABLISHED} по протоколу не считаются установленными'}


STEPS = {'path': run_path, 'h9': run_h9, 'h10': run_h10, 'h11': run_h11}
REUSED_BY = {'path': ['q2_d8', STEP_REF], 'h9': H_REF + HP_REF + ['grid_d10_s0'], 'h10': H_REF + HP_REF,
             'h11': H_REF + [STEP_REF] + ALL_REF}


# ---------------------------------------------------------------- run, dry

def path_passed(ctx: Ctx) -> bool:
    p = ctx.out.runs / f"{OUT_NAME['path']}-result.json"
    if not p.exists():
        return False
    r = json.loads(p.read_text(encoding='utf-8'))
    return r.get('status') == 'ok' and r.get('passed') is True and r.get('code') == ctx.stamp


def run(ctx: Ctx) -> dict:
    """The real run of one subcommand under the heavy lock, with the snapshot before and after."""
    require_2019()
    if ctx.h != 'path' and not path_passed(ctx):
        raise SystemExit('the path check has not passed with this code (t1-path-result.json): run `path` first')
    if ctx.h == 'h11' and ctx.groups != 5:
        main_result = ctx.out.runs / f"{OUT_NAME['h11']}-result.json"
        if not main_result.exists() or json.loads(main_result.read_text(encoding='utf-8')).get('status') != 'ok':
            raise SystemExit('--groups 10 | 15 runs only after the main h11 run (h11-result.json, status ok)')
    check_grid_order()
    reused = require_reused(ctx, REUSED_BY[ctx.h])
    t0 = time.time()
    with S.heavy_step(OUT_NAME[ctx.h], DATASET, ctx.out, wait=ctx.wait, **ctx.heavy_kw):
        ctx.check_fn()
        before = snapshot(ctx.snapshot_roots)  # under the lock: nobody of the queue writes between the snapshots
        body = STEPS[ctx.h](ctx)
        verdict = snapshot_verdict(before, ctx.snapshot_roots)
    status = 'refused' if verdict['n_incident'] else 'ok'
    result = {'step': ctx.h, 'status': status, **body, 'deviations': DEVIATIONS, 'reused': reused,
              'eval': 'val half A 2019-11-08..13',
              'half_b': 'не скорится и не читается', 'protected': verdict, 'code': ctx.stamp, 'commit': ctx.commit,
              'peak_rss_gb': S.peak_rss_gb(), 'seconds_total': round(time.time() - t0, 1), 'finished': S.now()}
    wpath(ctx, result_name(ctx), runs=True)
    ctx.out.write_json(result, result_name(ctx), runs=True)
    if status != 'ok':
        raise SystemExit(S.PROTECTED_EXIT)
    return result


def dry(ctx: Ctx, counts: bool = False) -> dict:
    """Specs and checks without a fit, a metric or a label: configs of the reused fits from runs.jsonl."""
    require_2019()
    res = {'dry': True, 'step': ctx.h, 'deviations': DEVIATIONS, 'period': P.PERIOD, 'days': str(ctx.days), 'extra_root': str(M.EXTRA),
           'commit': commit_state(), 'code': ctx.stamp, 'grid_order': check_grid_order(),
           'reused': check_reused(ctx, REUSED_BY[ctx.h]), 'heavy': f'side {OUT_NAME[ctx.h]}',
           'outputs': {'art': str(wpath(ctx, 'runs.jsonl').parent), 'result': str(wpath(ctx, result_name(ctx),
                                                                                         runs=True))},
           'journal': str(ctx.out.journal), 'snapshot_roots': {str(k): v for k, v in ctx.snapshot_roots.items()}}
    if ctx.h != 'path':
        res['path_passed'] = path_passed(ctx)
    spec = lambda name, over: {'name': name, 'cfg': config(ctx, over)}
    if ctx.h == 'path':
        res['fits'] = [spec(n, o) | {'ref': r} for n, (r, o) in PATH_POINTS.items()]
    elif ctx.h == 'h9':
        res['fits'] = {'stage1': [spec(f'{a}_s0', HP | SEEDS[0] | x) for a, x in H9_ARMS],
                       'stage2': '<= 2 passing arms, seed (7, 1): <arm>_s1',
                       'stage3': 'only on «недонастроен»: h9_H_<W>_s0/_s1 (d10: grid_d10_s0 + h9_H_d10_s1)'}
    elif ctx.h == 'h10':
        res['fits'] = {'scan': [spec(f'h10_{a}_scan_s0', b | SEEDS[0] | {'iterations': ctx.scan['iterations']})
                                for a, b in (('H', H), ('Hp', HP))],
                       'eval_period': ctx.scan['eval_period'], 'fit_anchors': f'{FIRST_ANCHOR}..{H10_FIT_LAST}',
                       'tail': [str(d) for d in H10_TAIL],
                       'retrain': 'h10_<arm>_n<N_full>_s0/_s1 if |N_full - 500| >= 100'}
        if counts:
            gate = lambda: S.light_gate_wait(f'{OUT_NAME[ctx.h]} counts', DATASET, ctx.out, wait=ctx.wait,
                                             **ctx.heavy_kw)
            train = list(M.days('train'))
            q_full = count_queries(ctx.days, train, gate)
            q_sub = count_queries(ctx.days, [d for d in train if d <= H10_FIT_LAST], gate)
            res['counts'] = {'q_full': q_full, 'q_sub': q_sub,
                             'tail_queries': count_queries(ctx.days, H10_TAIL, gate),
                             'note': 'distinct (anchor, user_id); the scored tail keeps queries with targets'}
    else:
        gs = groups_of(ctx.groups)
        res['fits'] = {'groups': ctx.groups, 'group_tables': gs, 'step': spec('h11_step_s1', R6BASE | SEEDS[1]),
                       'round1': spec(h11_name(ctx.groups, 1, 0), H | SEEDS[0] | {'extra': gs[0]})}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='H9–H11 on REES46 2019, half A (council/runs/side/h11.md)')
    ap.add_argument('step', choices=list(STEPS))
    ap.add_argument('--dry', action='store_true', help='specs and checks only: no fit, no metric, no label')
    ap.add_argument('--no-counts', action='store_true', help='h10 --dry: skip the query counts (they read days6)')
    ap.add_argument('--groups', type=int, choices=[5, 10, 15], default=5, help='h11: tables per group')
    ap.add_argument('--skip', action='append', choices=list(SKIPS), default=[],
                    help='the cuts of h11.md: h9 stage 3, the h10 retrain of H')
    ap.add_argument('--no-wait', action='store_true', help='refuse instead of waiting for the heavy lock')
    args = ap.parse_args(argv)
    require_2019()
    if args.groups != 5 and args.step != 'h11':
        ap.error('--groups is an option of h11')
    out = make_out(args.step)
    if args.dry:
        ctx = Ctx(args.step, out, groups=args.groups, wait=not args.no_wait)
        S.print_json(dry(ctx, counts=args.step == 'h10' and not args.no_counts))
        return 0
    commit = committed()
    ctx = Ctx(args.step, out, commit=commit, groups=args.groups, skip=tuple(args.skip), wait=not args.no_wait)
    res = run(ctx)
    S.print_json({k: res.get(k) for k in ('step', 'status', 'verdict', 'passed', 'peak_rss_gb', 'seconds_total')})
    return 0


if __name__ == '__main__':
    sys.exit(main())
