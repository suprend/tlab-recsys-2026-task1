"""Data roles, seeds, names and paths of the council on the xfer datasets (council/runs/xfer/contract.md §1, §3).

Import builds nothing and reads nothing: constants and pure path functions only. `activate(dataset)` imports the
adapter of one dataset through xfer_common (one dataset per process, contract §3 rule 1), reads its anchors and
returns a `Dataset`; the other modules take that object as their first argument.

Phases of the council and the xfer series and collection roles behind them:

  phase    series (SERIES)     collection role (COLLECTION_ROLES)   what
  fit      SERIES['select']    'train'                              T_fit: the train anchors of the dev series
  select   SERIES['select']    'val'                                S0 (S0-explore = half A, S0-select = half B)
  probe    -                   'probe'                              the probe collection, no target columns
  test     SERIES['test']      COLLECTION_ROLES['test']             C_test; it trains on the train anchors + S0

The word of the test series and collection is written only inside the two dict literals below (boundary test of
contract §3); every other module asks SERIES['test'] and Dataset.collection('test').

Halves: h = (user_id * 2654435761) mod 2**64 (unsigned 64 bit), half = 'A' if (h >> 7) % 2 == 0 else 'B'; the same
as task1.exp.half without importing task1 (contract §1).
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import numpy as np

from scripts import xfer_common as xc

ROOT = Path(__file__).resolve().parents[2]

DATASETS = tuple(xc.DATASETS)                      # ('tinkoff', 'sber')
SERIES = {'select': 'dev', 'test': 'holdout'}
COLLECTION_ROLES = {'fit': 'train', 'select': 'val', 'probe': 'probe', 'test': 'holdout'}
PHASES = tuple(COLLECTION_ROLES)                   # ('fit', 'select', 'probe', 'test')
TRAINING_PHASES = ('fit', 'select', 'test')        # the order a training anchor's role is looked up in

# ---------------------------------------------------------------- halves of S0 (contract §1)

EXPLORE, SELECT = 'A', 'B'
HALVES = (EXPLORE, SELECT)
HALF_MULTIPLIER = 2654435761
HALF_SHIFT = 7
MASK64 = 0xFFFF_FFFF_FFFF_FFFF


def half(user_id) -> str:
    """'A' or 'B' of one user id, pure Python: unsigned 64-bit product with explicit wraparound."""
    h = (int(user_id) * HALF_MULTIPLIER) & MASK64
    return EXPLORE if (h >> HALF_SHIFT) % 2 == 0 else SELECT


def halves(user_ids) -> np.ndarray:
    """'A'/'B' per user id, the numpy form (np.uint64 with overflow, as task1.exp.half); an array of str."""
    u = np.atleast_1d(np.asarray(user_ids, dtype=np.uint64))
    h = u * np.uint64(HALF_MULTIPLIER)             # wraps mod 2**64 on arrays
    return np.where((h >> np.uint64(HALF_SHIFT)) % np.uint64(2) == 0, EXPLORE, SELECT)


# ---------------------------------------------------------------- seeds (contract §3.1, §3.3)

PATH_SEED = 2026                    # the path checks only: the seed of BA2026 in xfer
NOISE_SEEDS = (7, 11)               # two noise fits of H+r, T_fit -> S0-explore
PLAN_RUNS = 48                      # PB24 folded over
CONFIRM_SEEDS = (3001, 3002)        # confirmation of D on S0-select
TEST_SEEDS = (7, 11, 13, 17)
TEST_FITS = {                       # arm -> seeds of the C_test fits (14); ALL_P only when D is not empty
    'Hrp': (7, 11, 13, 17),
    'SEL': (7, 11, 13, 17),
    'Hr': (7, 11),
    'TWIN': (7, 11),
    'Rb1': (7,),
    'Rb2': (7,),
}
TEST_FITS_ALLP = {'ALLP': (7, 11)}
ARMS = ('Hr', 'Hrp', 'ALLP', 'SEL', 'TWIN', 'Rb1', 'Rb2')
PLACEBO_SEED = 4242
BOOT_SEED = 2026
N_BOOT = 2000
PATH_TOL = 1e-9                     # path checks against BA2026 (§6.8: replaced by the measured difference if needed)


def plan_seed(r: int) -> int:
    """CatBoost seed of plan fit r = 1..48 (row r - 1 of design.matrix())."""
    if not isinstance(r, int) or isinstance(r, bool) or not 1 <= r <= PLAN_RUNS:
        raise ValueError(f'plan run {r!r} is not in 1..{PLAN_RUNS}')
    return 1000 + r


def placebo_key(anchor) -> list[int]:
    """Seed of numpy.random.default_rng for the placebo permutation inside one anchor (one per campaign)."""
    return [PLACEBO_SEED, 0, xc.anchor_int(anchor), 0]


# ---------------------------------------------------------------- recipe (contract §3.1)

PREDICTION_TYPE = xc.PREDICTION_TYPE


def recipe_for(seed: int) -> dict:
    """xc.RECIPE with the seed: the same dict as xfer_model.recipe_for(seed), in every arm and phase (no proxy
    recipe). fit.py asserts the equality with the xfer function at the start of every fit."""
    return dict(xc.RECIPE, random_seed=int(seed))


# ---------------------------------------------------------------- names (contract §3.4)

CARD_ID = re.compile(r'G([1-4])-([0-9]+)')
CARD_PREFIX = 'f_x_c'               # what a card writes: f_x_c<lens>_<slug>
SANDBOX_PREFIX = 'ag_c'             # the same column in the xfer sandbox: ag_c<lens>_<slug>
TWIN_SUFFIX = '_tw'
PLACEBO_PREFIX = 'plc_'
CARD_COLUMN = re.compile(r'ag_c([1-4])_([a-z0-9_]{1,36})')
RB_COLUMN = re.compile(r'ag_rb([12])_([a-z0-9_]{1,35})')
COUNCIL_COLUMN = re.compile(r'ag_(c[0-9]_|rb|plc)')   # never in the xfer agent set (tested on the set)
SLUG = re.compile(r'[a-z][a-z0-9_]*')


def sandbox_column(card_column: str) -> str:
    """f_x_c<lens>_<slug>[_tw] -> ag_c<lens>_<slug>[_tw]; ValueError on another name."""
    if not card_column.startswith(CARD_PREFIX):
        raise ValueError(f'{card_column!r} is not {CARD_PREFIX}<lens>_<slug>')
    name = SANDBOX_PREFIX + card_column[len(CARD_PREFIX):]
    if not CARD_COLUMN.fullmatch(name):
        raise ValueError(f'{card_column!r}: the sandbox name {name!r} breaks ag_c<lens>_<slug, <= 36>')
    return name


def family_table(card_id: str) -> str:
    """Council table of a family: 'G3-2' -> 'g3_2' (file <table>.parquet under sidecars/<collection>/)."""
    m = CARD_ID.fullmatch(str(card_id))
    if not m:
        raise ValueError(f'card id {card_id!r} is not G<1-4>-<n>')
    return f'g{m.group(1)}_{m.group(2)}'


def twin_table(card_id: str) -> str:
    return family_table(card_id) + TWIN_SUFFIX


def rb_table(k: int, slug: str) -> str:
    """Table of one proposal of the reference agent Rb<k>: 'rb<k>_<slug>'."""
    if k not in (1, 2) or not SLUG.fullmatch(slug or ''):
        raise ValueError(f'Rb{k}: {slug!r} is not a snake_case slug')
    return f'rb{k}_{slug}'


def placebo_column(column: str) -> str:
    return PLACEBO_PREFIX + column


def council_columns_in(columns) -> list[str]:
    """Columns of the xfer agent set that would clash with council names (ag_c<digit>_, ag_rb, ag_plc)."""
    return sorted(c for c in columns if COUNCIL_COLUMN.match(c))


# ---------------------------------------------------------------- LLM (contract §3.4)

LLM_LETTER = {'tinkoff': 'a', 'sber': 'b'}         # the only place that knows which letter is which dataset
LLM_ROOT = Path('/tmp')
LLM_EXTRA_NAMES = r't-bank|т-банк|сбермаркет|kuper|xfer|rees46'
LLM_MAX_CALLS = 24
LLM_MAX_USD = 25.0
LLM_TOTAL_USD = 50.0


def llm_dir(dataset: str, root: Path | None = None) -> Path:
    """The neutral empty working directory of `claude -p` for the dataset (under a test root when one is given)."""
    return (LLM_ROOT if root is None else Path(root)) / f'tlab-council-llm-{LLM_LETTER[xc.check_dataset(dataset)]}'


# ---------------------------------------------------------------- paths

RUNS_ROOT = ROOT / 'council' / 'runs'
OUT_ROOT = ROOT / 'artifacts' / 'council'
TEST_ROOT_PREFIX = '/tmp/tlab-'     # a root other than the repository must lie under it (contract §8.8)


def check_root(root) -> Path:
    """An explicit root of the council paths, absolute and under /tmp/tlab-<...> (/private/tmp on macOS counts);
    ValueError otherwise."""
    p = Path(os.path.abspath(os.fspath(root)))
    for form in (p, p.resolve()):
        parts = form.parts
        top = parts[1:3] if parts[1:2] == ('tmp',) else parts[2:4] if parts[1:3] == ('private', 'tmp') else ()
        if len(top) == 2 and top[1].startswith('tlab-') and len(top[1]) > len('tlab-'):
            continue
        raise ValueError(f'council root {root!r} is not under {TEST_ROOT_PREFIX}')
    return p


@dataclass(frozen=True)
class Paths:
    """Where the council of one dataset writes. runs: journals under Git; out: heavy artifacts outside Git.

    runs/                      prereg-<n>.json, cards-*.json, probes.json, critiques.json, curation.json,
                               compute.json, queue-<name>.json, plan-result.json, selection.json, test.json,
                               test-approved.md, reads.jsonl (broker), llm.jsonl, prompts/, replies/, queue.jsonl
    out/fits/<phase>/<arm>-<seed>/scores.parquet, out/fits/runs.jsonl
    out/probes/<sha256(sql)[:16]>.json and .values.parquet, out/probes/ref-<anchor>.parquet
    out/sidecars/<collection>/<table>.parquet and manifest.json
    """
    dataset: str
    runs: Path
    out: Path
    llm: Path
    root: Path | None = None        # the explicit test root (passed to child processes), None = the repository

    @property
    def fits(self) -> Path:
        return self.out / 'fits'

    @property
    def fit_records(self) -> Path:
        return self.fits / 'runs.jsonl'

    @property
    def probes(self) -> Path:
        return self.out / 'probes'

    @property
    def sidecars(self) -> Path:
        return self.out / 'sidecars'

    @property
    def reads(self) -> Path:
        return self.runs / 'reads.jsonl'

    @property
    def llm_log(self) -> Path:
        return self.runs / 'llm.jsonl'

    @property
    def prompts(self) -> Path:
        return self.runs / 'prompts'

    @property
    def replies(self) -> Path:
        return self.runs / 'replies'

    @property
    def queue_log(self) -> Path:
        return self.runs / 'queue.jsonl'

    @property
    def selection(self) -> Path:
        return self.runs / 'selection.json'

    @property
    def approved(self) -> Path:
        return self.runs / 'test-approved.md'

    def prereg(self, n: int) -> Path:
        return self.runs / f'prereg-{int(n)}.json'

    def queue(self, name: str) -> Path:
        if not SLUG.fullmatch(name):
            raise ValueError(f'queue name {name!r} is not a slug')
        return self.runs / f'queue-{name}.json'

    def run_file(self, name: str) -> Path:
        """A file directly under runs/ by its name (e.g. 'curation.json')."""
        if '/' in name or '\\' in name or name.startswith('.'):
            raise ValueError(f'{name!r} is not a plain file name')
        return self.runs / name

    def scores(self, phase: str, arm: str, seed: int) -> Path:
        return self.fits / phase / f'{arm}-{int(seed)}' / 'scores.parquet'

    def probe_ref(self, anchor) -> Path:
        return self.probes / f'ref-{xc.anchor_text(anchor)}.parquet'

    def table(self, collection: str, table: str) -> Path:
        return self.sidecars / collection / f'{table}.parquet'


def paths(dataset: str, root=None) -> Paths:
    """Paths of one dataset; pure (creates nothing). root None: the repository (council/runs, artifacts/council,
    /tmp/tlab-council-llm-<a|b>); else check_root(root) with the same layout below it."""
    xc.check_dataset(dataset)
    if root is None:
        return Paths(dataset=dataset, runs=RUNS_ROOT / f'xfer-{dataset}', out=OUT_ROOT / f'xfer-{dataset}',
                     llm=llm_dir(dataset))
    r = check_root(root)
    return Paths(dataset=dataset, runs=r / 'council' / 'runs' / f'xfer-{dataset}',
                 out=r / 'artifacts' / 'council' / f'xfer-{dataset}', llm=llm_dir(dataset, r), root=r)


# ---------------------------------------------------------------- the dataset of the process

@dataclass(frozen=True)
class Dataset:
    """One activated dataset: adapter, anchors (adapter.anchors(), checked against the prereg by the fits) and paths."""
    name: str
    adapter: ModuleType = field(repr=False, compare=False)
    anchors: dict = field(repr=False, compare=False)
    paths: Paths = field(compare=False)

    def series(self, phase: str) -> dict:
        """The xfer series behind 'select' or 'test' (train anchors, eval anchor, eval role)."""
        return self.anchors['series'][SERIES[phase]]

    @property
    def fit_anchors(self) -> list:
        """T_fit: the train anchors of the select series, in time order."""
        return sorted(self.series('select')['train'], key=xc.anchor_int)

    @property
    def s0_anchor(self):
        return self.series('select')['eval']

    @property
    def test_train_anchors(self) -> list:
        return sorted(self.series('test')['train'], key=xc.anchor_int)

    @property
    def test_anchor(self):
        return self.series('test')['eval']

    @property
    def probe_anchor(self):
        return self.anchors['probe']

    @property
    def probe_users(self) -> int:
        return int(self.anchors['probe_users'])

    @property
    def probe_anchors(self) -> list:
        """Anchors of the probes: the probe collection, then the last train anchor (keys and base only)."""
        return [self.probe_anchor, self.fit_anchors[-1]]

    @property
    def K(self) -> int:
        return int(self.anchors['K'])

    @property
    def prompt_cutoff(self):
        """The first anchor an LLM prompt may not name: the S0 anchor (T: steps >= 641, S: dates >= 2020-08-19)."""
        return self.s0_anchor

    def phase_of(self, anchor) -> str:
        """'fit', 'select' or 'test' of a training or scored anchor (lookup order TRAINING_PHASES)."""
        text = xc.anchor_text(anchor)
        for phase in TRAINING_PHASES:
            if any(xc.anchor_text(a) == text for a in self.anchors['roles'].get(COLLECTION_ROLES[phase], [])):
                return phase
        raise ValueError(f'anchor {anchor!r} has no training role in {self.name}')

    def collection(self, phase: str, anchor=None) -> Path:
        """Read-only xfer collection directory of a phase (artifacts/xfer/<x>/collections/<role>-<anchor>).

        anchor defaults to the phase's single anchor (select: S0, probe: the probe anchor, test: C_test); 'fit'
        needs it. The test collection is the one in force after deviation rebuilds (xfer_common resolves it)."""
        role = COLLECTION_ROLES[phase]
        if anchor is None:
            if phase == 'fit':
                raise ValueError('the fit phase has several anchors: name one')
            anchor = {'select': self.s0_anchor, 'probe': self.probe_anchor, 'test': self.test_anchor}[phase]
        if xc.anchor_text(anchor) not in {xc.anchor_text(a) for a in self.anchors['roles'].get(role, [])}:
            raise ValueError(f'{anchor!r} is not an anchor of phase {phase} in {self.name}')
        if phase == 'test':
            resolve = getattr(xc, f'current_{role}_collection')
            return Path(resolve(self.name, anchor))
        return xc.dataset_dir(self.name) / 'collections' / xc.collection_name(role, anchor)

    def training_collections(self, phase: str) -> list:
        """[(anchor, collection dir)] of the training anchors of the select or test series."""
        anchors = self.fit_anchors if phase == 'select' else self.test_train_anchors
        return [(a, self.collection(self.phase_of(a), a)) for a in anchors]

    @staticmethod
    def qid(anchor, user_id) -> str:
        """Query id '<anchor_text>:<user_id>' (design.users_of reads the part after the last ':')."""
        return f'{xc.anchor_text(anchor)}:{int(user_id)}'


_ACTIVE: Dataset | None = None


def activate(dataset: str, root=None) -> Dataset:
    """The dataset of this process. Imports its adapter only; refuses a second dataset (contract §3 rule 1) and,
    through xc.code_identity, a process where the other adapter is loaded. root: the explicit root of the council
    paths (contract §8.8), None = the repository, else under /tmp/tlab-; a second call with another root is
    refused. Creates no file."""
    global _ACTIVE
    xc.check_dataset(dataset)
    p = paths(dataset, root)
    if _ACTIVE is not None:
        if _ACTIVE.name != dataset:
            raise xc.ContractError(f'{_ACTIVE.name} is active in this process; {dataset} needs its own process')
        if _ACTIVE.paths.root != p.root:
            raise xc.ContractError(f'{dataset} is active on root {_ACTIVE.paths.root}; not on {p.root}')
        return _ACTIVE
    xc.code_identity(dataset)       # imports the shared modules and the adapter; refuses the other adapter
    adapter = xc.adapter(dataset)
    anchors = adapter.anchors()
    for phase in ('select', 'test'):
        s = anchors['series'].get(SERIES[phase])
        xc.require(s is not None and s.get('eval_role') == COLLECTION_ROLES[phase],
                   f'{dataset}: series {SERIES[phase]} does not score the {COLLECTION_ROLES[phase]} collection')
    _ACTIVE = Dataset(name=dataset, adapter=adapter, anchors=anchors, paths=p)
    return _ACTIVE


def current() -> Dataset:
    if _ACTIVE is None:
        raise xc.ContractError('no dataset is active: roles.activate(dataset) first')
    return _ACTIVE


def collection(phase: str, anchor=None) -> Path:
    """Dataset.collection of the active dataset."""
    return current().collection(phase, anchor)


# ---------------------------------------------------------------- code identity (contract §3 rule 3)

STAMPED = ('broker', 'fit', 'marker', 'plan', 'queue', 'roles', 'run')


def stamp_files() -> list[Path]:
    """The modules between a council table and a number (contract §12.1): council/xfer/{STAMPED}.py that exist,
    and council/design.py. The council stages (agents, sandbox, curate, compute) are pinned by their outputs
    instead: curation_sha256 in prereg-2 and the table files in the data fingerprint of every fit."""
    xfer = ROOT / 'council' / 'xfer'
    return [p for p in (xfer / f'{m}.py' for m in STAMPED) if p.exists()] + [ROOT / 'council' / 'design.py']


def council_stamp() -> dict:
    """sha256 of every stamped council file, by its path relative to ROOT."""
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in stamp_files()}


def identity(ds: Dataset) -> dict:
    """What every fit, probe and compute record carries: xc.code_identity and the council stamp."""
    return {'code': xc.code_identity(ds.name), 'council': council_stamp()}


def prereg_code(ds: Dataset) -> dict:
    """latest_code of the committed prereg and deviations of the dataset (the xfer guard compares with it)."""
    return xc.latest_code(ds.name, xc.read_json(xc.config_path(ds.name, 'prereg')))
