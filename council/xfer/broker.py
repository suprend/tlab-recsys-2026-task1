"""The only reader of evaluation labels in the council on xfer (council/runs/xfer/contract.md §3 «Граница меток»,
§3.2, §10; decision N1a). It takes the score files of council.xfer.fit, computes xm.top_k(ctx.K) -> xm.evaluate ->
the per-query metric of adapter.metric (T NDCG@20, S MAP@50) and returns a table qid x fit; agents, probes, the
curator and the LLM get nothing from it.

Label paths: S0 (val collection) through xm.open_labels(collection); C_test (the holdout collection) through
xm.final_labels(collection) (xfer purpose 'final', allowed by the committed result receipt
configs/datasets/xfer-<x>-holdout.json). The xfer holdout helper is never used. Labels are read only under the
default root of the council paths (Dataset.paths.root is None, §10.3).

Every fit read is checked before any label (§10.1): its record spec equals the spec derived for its name from the
committed files (fit.path_specs/noise_specs; plan.plan_specs of the committed curation.json; plan.confirm_specs of
the curation and the D of plan-result.json; plan.test_specs of the curation, the committed selection.json and the
marker sha); its identity equals the one of prereg-0 (before prereg-0: the current roles.identity); eval.collection
and eval.manifest_sha256 equal the current eval collection; the score file has the sha256 and the keys digest
(xm.keys_digest) of its record; a name read before with another scores sha256 is refused. Reads demand one set of
queries for all fits read together and at least one query, and are appended to council/runs/xfer-<x>/reads.jsonl
(what, at, names, commit, scores {name: sha256}, extra) before the values are returned. No count of queries with
a target is returned or logged before the test (§10.7). A read that fails a check returns nothing and logs
nothing - except c_test, whose every gate refusal is logged as 'c_test.refused' (§3.2).

  path_check(ds, kind)     kind 'select': the path fit H+r 2026 T_fit -> S0, per-query values against the xfer
                           fit dev/BA2026 (its report.json and metrics file); kind 'test': the path fit of the test
                           series, scores against holdout/BA2026, no labels. Returns {kind, name, ref,
                           same_queries, max_abs_diff, ok}.
  noise_explore(ds, names) S0-explore (half A), the two noise fits; refuses a second call.
  y_select(ds, names)      S0-select (half B): plan and confirmation fits; any number of reads.
  start_test(ds)           marker test.started (a reads.jsonl record, council.xfer.marker) after the owner's «да»
                           for this dataset and final_labels, with selection.json committed; it fixes the sha256 of
                           selection.json, its last commit and the sha256 of test-approved.md.
  c_test(ds, names)        C_test after test.started with the same selection and approval; the shares of queries
                           with a target on S0 and C_test are computed in the same read and logged in its record.
  target_shares(ds)        those shares from the last c_test record (no read of its own, §10.5).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from council.xfer import fit, roles
from council.xfer import marker as journal
from scripts import xfer_common as xc
from scripts import xfer_model as xm

PATH_REF = {'select': ('dev', 'BA', 2026), 'test': ('holdout', 'BA', 2026)}   # xfer fits of the path checks
PATH_PHASE = {'select': 'path_select', 'test': 'path_test'}
REPORT = 'report.json'                                  # the xfer fit report read by the path checks (§10.8)
APPROVED_LINE = r'^approved:[ \t]*(\S.*?)[ \t]*$'      # verbatim quote with «да» for this dataset and final_labels
TRANSCRIPT_LINE = r'^transcript:[ \t]*(\S.*?)[ \t]*$'  # <session id> / <exact message text>
MARKER = journal.MARKER
YES = re.compile(r'(?i)(?<!\w)да(?!\w)')
PLACEHOLDER = re.compile(r'<[^>]*>')
GENERAL = re.compile(r'(?i)ни\s+о\s+ч[её]м\s+не\s+спрашивай')   # the general phrase of the xfer receipts
TRANSCRIPT = re.compile(r'\S.*?\s/\s\S.*')                          # <session id> / <message text>
FINAL = 'final_labels'
SELECT_PHASES = ('plan', 'confirm')
CURATION = 'curation.json'
PLAN_RESULT = 'plan-result.json'


# ---------------------------------------------------------------- journal and git

def _git(*args, cwd) -> str:
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _existing(path: Path) -> Path:
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    return path if path.is_dir() else path.parent


def head(ds: roles.Dataset) -> str | None:
    """HEAD of the repository that holds the dataset's journal."""
    try:
        return _git('rev-parse', 'HEAD', cwd=_existing(ds.paths.runs)).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def reads(ds: roles.Dataset) -> list[dict]:
    """Records of ds.paths.reads (a broken last line is skipped, council.xfer.marker)."""
    return journal.reads(ds)


def marker(ds: roles.Dataset) -> dict | None:
    """The test.started record of ds.paths.reads, or None."""
    return journal.marker(ds)


def log(ds: roles.Dataset, what: str, names: list[str], **extra) -> dict:
    """Append {what, at, names, commit, **extra} to ds.paths.reads; returns the record."""
    rec = {'what': what, 'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'names': list(names), 'commit': head(ds)} | extra
    rec = json.loads(json.dumps(rec, ensure_ascii=False, default=str))
    journal.append(ds.paths.reads, rec)
    return rec


def _repo(path: Path) -> tuple[Path, str]:
    top = Path(_git('rev-parse', '--show-toplevel', cwd=_existing(path)).strip()).resolve()
    return top, Path(path).resolve().relative_to(top).as_posix()


def committed(path) -> bool:
    """True if `path` is in HEAD and has no uncommitted changes."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        top, rel = _repo(path)
        if _git('status', '--porcelain', '--', rel, cwd=top).strip():
            return False
        _git('cat-file', '-e', f'HEAD:{rel}', cwd=top)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False
    return True


def last_commit(path) -> str | None:
    """The last commit that changed `path` (git log -1 --format=%H -- path)."""
    try:
        top, rel = _repo(Path(path))
        return _git('log', '-1', '--format=%H', '--', rel, cwd=top).strip() or None
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- expected specs (§10.1)

def _committed_json(path: Path, what: str):
    if not committed(path):
        raise PermissionError(f'{what}: {path} must exist, be in HEAD and have no uncommitted changes')
    return json.loads(path.read_text(encoding='utf-8'))


def expected_specs(ds: roles.Dataset, phases, what: str) -> dict:
    """name -> the spec a fit of one of `phases` must carry, derived from the committed files (module docstring);
    PermissionError if a file the derivation needs is missing or not committed."""
    phases = set(phases)
    out = {}
    if phases & {'path_select', 'path_test'}:
        out |= {s['name']: s for s in fit.path_specs(ds) if s['phase'] in phases}
    if 'noise' in phases:
        out |= {s['name']: s for s in fit.noise_specs(ds)}
    if phases & {'plan', 'confirm', 'test'}:
        try:
            out |= _plan_specs(ds, phases, what)
        except ValueError as e:
            raise PermissionError(f'{what}: the committed plan files give no specs: {e}') from None
    return {n: fit.validate(ds, s) for n, s in out.items()}


def _plan_specs(ds: roles.Dataset, phases: set, what: str) -> dict:
    """The plan.py derivation of expected_specs (imported here: plan imports the broker)."""
    from council.xfer import plan
    out = {}
    cur = _committed_json(ds.paths.run_file(CURATION), what)
    if 'plan' in phases:
        out |= {s['name']: s for s in plan.plan_specs(cur)}
    result = ds.paths.run_file(PLAN_RESULT)
    if 'confirm' in phases and result.exists():
        d = json.loads(result.read_text(encoding='utf-8')).get('D') or []
        if d:
            out |= {s['name']: s for s in plan.confirm_specs(cur, d)}
    if 'test' in phases:
        selection = _committed_json(ds.paths.selection, what)
        mark = marker(ds)
        if mark is None:
            raise PermissionError(f'{what}: the marker {MARKER} is missing')
        out |= {s['name']: s for s in plan.test_specs(cur, selection, mark['selection_sha256'])}
    return out


def frames(ds: roles.Dataset, names: list[str], expected: dict, key: str, what: str) -> tuple[dict, dict]:
    """({name: score frame}, {name: scores sha256}) of fits that pass every record check of §10.1 (module
    docstring); PermissionError otherwise. key: 'select' or 'test', the series key of the eval collection."""
    names = list(names)
    if not names or len(set(names)) != len(names) or not all(isinstance(n, str) for n in names):
        raise ValueError(f'{what}: a non-empty list of distinct fit names')
    journal.check_tail(ds.paths.reads)
    recs = fit.records(ds)
    identity = fit.prereg_identity(ds)
    identity = roles.identity(ds) if identity is None else identity
    collection = Path(ds.collection(key))
    manifest = _sha(collection / xc.MANIFEST_FILE)
    seen = {}
    for r in reads(ds):
        for n, sha in (r.get('scores') or {}).items():
            seen.setdefault(n, set()).add(sha)
    out, shas = {}, {}
    for n in names:
        if n not in expected:
            raise PermissionError(f'{what}: {n} is not a fit this read takes')
        rec = recs.get(n)
        if rec is None:
            raise PermissionError(f'{what}: fit {n} has no record')
        if rec.get('spec') != expected[n]:
            raise PermissionError(f'{what}: the record of {n} carries another spec than the committed plan')
        if rec.get('identity') != identity:
            raise PermissionError(f'{what}: fit {n} ran with another code identity than prereg-0 (or the current)')
        ev = rec.get('eval') or {}
        if ev.get('collection') != collection.name or ev.get('manifest_sha256') != manifest:
            raise PermissionError(f'{what}: fit {n} was scored on another collection than {collection.name}')
        s = rec['spec']
        path = ds.paths.scores(s['phase'], s['arm'], s['seed'])
        if not path.exists():
            raise PermissionError(f'{what}: fit {n} has no scores file')
        sha = xc.sha256_file(path)
        if sha != ev.get('scores_sha256'):
            raise PermissionError(f'{what}: {path} differs from the sha256 in its record')
        if seen.get(n, {sha}) != {sha}:
            raise PermissionError(f'{what}: {n} was read before with other scores')
        frame = xc.read_parquet(path)
        if tuple(frame.columns) != fit.SCORE_COLUMNS:
            raise PermissionError(f'{what}: fit {n}: columns {list(frame.columns)} are not {fit.SCORE_COLUMNS}')
        if xm.keys_digest(frame) != ev.get('keys_sha256'):
            raise PermissionError(f'{what}: the keys of {path} differ from its record')
        out[n] = frame.sort_values(['user_id', 'item_id'], kind='mergesort').reset_index(drop=True)
        shas[n] = sha
    return out, shas


# ---------------------------------------------------------------- per-query values

def context(ds: roles.Dataset):
    """xm.Context of the dataset (prereg guard, adapter with its metric, K)."""
    return xm.Context(ds.name)


def per_query_metric(ctx, frame: pd.DataFrame, labels: pd.DataFrame, targets: pd.DataFrame) -> pd.Series:
    """qid -> adapter metric of one score frame: xm.evaluate(ctx, frame, targets, labels) (top_k(ctx.K) inside),
    indexed by the qid of the frame ('<anchor>:<user_id>'), ordered by user_id."""
    values = xm.evaluate(ctx, frame[['user_id', 'item_id', 'score']], targets, labels)
    qids = frame.drop_duplicates('user_id').set_index('user_id')['qid']
    users = sorted(values)
    return pd.Series([values[u] for u in users], index=pd.Index([qids[u] for u in users], name='qid'),
                     dtype=np.float64)


def _check_frames(ds: roles.Dataset, frames_: dict, key: str, half: str | None) -> None:
    """The same keys in every fit, qids of the eval anchor of `key`, users of `half` only."""
    names = list(frames_)
    first = frames_[names[0]]
    prefix = f"{xc.anchor_text(ds.series(key)['eval'])}:"
    for n, f in frames_.items():
        if len(f) != len(first) or not (np.array_equal(f['user_id'].to_numpy(), first['user_id'].to_numpy())
                                        and np.array_equal(f['item_id'].to_numpy(), first['item_id'].to_numpy())):
            raise ValueError(f'fit {n} differs in queries or rows from {names[0]}')
        if not f['qid'].astype(str).str.startswith(prefix).all():
            raise ValueError(f'fit {n} holds queries of another anchor than {prefix[:-1]}')
        if not np.isfinite(f['score'].to_numpy(dtype=np.float64)).all():
            raise ValueError(f'fit {n} has scores that are not finite')
    if half is not None and (roles.halves(first['user_id'].to_numpy()) != half).any():
        raise ValueError(f'fits {names} hold users outside half {half}')


def labels_of(ds: roles.Dataset, key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(labels, targets) of the eval collection of 'select' (xm.open_labels) or 'test' (xm.final_labels);
    PermissionError under a non-default root of the council paths (§10.3)."""
    if ds.paths.root is not None:
        raise PermissionError(f'labels are read under the default root only, not under {ds.paths.root}')
    collection = ds.collection(key)
    if key == 'select':
        return xm.open_labels(collection)
    if key == 'test':
        return xm.final_labels(collection)
    raise ValueError(f'labels of {key!r}: select or test only')


def table(ds: roles.Dataset, frames_: dict, key: str, half: str | None, read=None) -> pd.DataFrame:
    """qid x fit of the per-query metric of checked score frames of one collection (labels_of(key), or `read`
    already taken), restricted to the queries of `half`; ValueError unless all fits cover the same queries, every
    query of the half is scored and there is at least one query."""
    names = list(frames_)
    _check_frames(ds, frames_, key, half)
    labels, targets = labels_of(ds, key) if read is None else read
    targets = targets[targets['n_targets'] >= 1]
    if half is not None:
        keep = set(targets['user_id'][roles.halves(targets['user_id'].to_numpy()) == half].astype(np.int64))
        targets = targets[targets['user_id'].isin(keep)].reset_index(drop=True)
        labels = labels[labels['user_id'].isin(keep)].reset_index(drop=True)
    if not len(targets):
        raise ValueError(f'the {key} read has no query')
    scored = set(frames_[names[0]]['user_id'].astype(np.int64))
    if set(targets['user_id'].astype(np.int64)) - scored:
        raise ValueError(f'queries of the {key} collection are not scored by {names[0]}')
    ctx = context(ds)
    out = pd.DataFrame({n: per_query_metric(ctx, f, labels, targets) for n, f in frames_.items()})
    out.index.name = 'qid'
    out.columns.name = None
    return out


# ---------------------------------------------------------------- reads of the plan

def path_check(ds: roles.Dataset, kind: str) -> dict:
    """{kind, name, ref, same_queries, max_abs_diff, ok}; ok iff the same queries and max |diff| <=
    roles.PATH_TOL. Logged as 'path_check:<kind>'. Never returns a value of the metric or a count of queries."""
    if kind not in PATH_PHASE:
        raise ValueError(f'path_check: kind {kind!r} not in {sorted(PATH_PHASE)}')
    phase = PATH_PHASE[kind]
    expected = expected_specs(ds, [phase], 'path_check')
    name = next(iter(expected))
    series, arm, seed = PATH_REF[kind]
    if series != roles.SERIES[kind]:
        raise ValueError(f'path_check: the reference series {series} is not the series of {kind}')
    got, shas = frames(ds, [name], expected, kind, 'path_check')
    ours = got[name]
    directory = Path(xm.fit_dir(ds.name, series, arm, seed))
    report = xc.read_json(directory / REPORT)
    if (report.get('status'), report.get('dataset'), report.get('series'), report.get('arm'), report.get('seed')) != \
            ('completed', ds.name, series, arm, seed):
        raise ValueError(f'path_check: {directory / REPORT} is not a completed {series}/{arm}{seed} fit of {ds.name}')
    if kind == 'select':
        ref = xm.read_metrics(directory, report)
        mine = table(ds, got, 'select', None)[name]
        mine.index = [int(q.rsplit(':', 1)[1]) for q in mine.index]
        same = bool(len(ref)) and sorted(mine.index) == sorted(ref)
        x = mine.sort_index().to_numpy(dtype=np.float64)
        y = np.array([ref[u] for u in sorted(ref)], dtype=np.float64) if same else None
    else:
        _check_frames(ds, got, 'test', None)
        ref = xm.read_scores(directory, report).sort_values(['user_id', 'item_id'], kind='mergesort')
        same = bool(len(ref)) and len(ref) == len(ours) \
            and np.array_equal(ref['user_id'].to_numpy(), ours['user_id'].to_numpy()) \
            and np.array_equal(ref['item_id'].to_numpy(), ours['item_id'].to_numpy())
        x = ours['score'].to_numpy(dtype=np.float64)
        y = ref['score'].to_numpy(dtype=np.float64) if same else None
    diff = float(np.max(np.abs(x - y))) if same else float('inf')
    if not np.isfinite(diff):
        diff = float('inf')
    res = {'kind': kind, 'name': name, 'ref': f'{series}/{arm}{seed}', 'same_queries': bool(same),
           'max_abs_diff': diff, 'ok': bool(same) and diff <= roles.PATH_TOL}
    log(ds, f'path_check:{kind}', [name], scores=shas, ref=res['ref'], same_queries=res['same_queries'],
        max_abs_diff=diff if np.isfinite(diff) else 'inf', ok=res['ok'])
    return res


def noise_explore(ds: roles.Dataset, names: list[str]) -> pd.DataFrame:
    """S0-explore, once: the two fits of fit.noise_specs (H+r, seeds roles.NOISE_SEEDS, half A); qid x fit."""
    names = list(names)
    if any(r.get('what') == 'noise_explore' for r in reads(ds)):
        raise PermissionError(f'noise_explore has been read already ({ds.paths.reads}); it is read once')
    expected = expected_specs(ds, ['noise'], 'noise_explore')
    if sorted(names) != sorted(expected):
        raise PermissionError(f'noise_explore: the fits must be {sorted(expected)}')
    got, shas = frames(ds, names, expected, 'select', 'noise_explore')
    out = table(ds, got, 'select', roles.EXPLORE)
    log(ds, 'noise_explore', names, scores=shas)
    return out


def y_select(ds: roles.Dataset, names: list[str]) -> pd.DataFrame:
    """S0-select: fits of phase plan or confirm (half B) whose specs are the ones of the committed plan; qid x
    fit; any number of reads."""
    names = list(names)
    expected = expected_specs(ds, SELECT_PHASES, 'y_select')
    got, shas = frames(ds, names, expected, 'select', 'y_select')
    out = table(ds, got, 'select', roles.SELECT)
    log(ds, 'y_select', names, scores=shas)
    return out


# ---------------------------------------------------------------- the gate of the test

def _approvals(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    return re.findall(APPROVED_LINE, text, re.M), re.findall(TRANSCRIPT_LINE, text, re.M)


def _norm(s: str) -> str:
    return ' '.join(s.split()).casefold()


def approved(ds: roles.Dataset, what: str) -> dict:
    """{'approved': quote, 'transcript': line, 'sha256': of test-approved.md} from ds.paths.approved: a line
    `approved: <quote with «да»>` (no angle-bracket placeholder, not the general phrase of the xfer receipts) and a
    line `transcript: <session id> / <message>`; the quote or the message names this dataset and final_labels.
    PermissionError otherwise, and if a transcript line or a quote (normalized by whitespace and case) is one of
    the other dataset's test-approved.md: a «да» for one dataset does not open the other (§10.2)."""
    path = ds.paths.approved
    quotes, lines = _approvals(path)
    quotes = [q for q in quotes if YES.search(q) and not PLACEHOLDER.search(q) and not GENERAL.search(q)]
    lines = [t for t in lines if TRANSCRIPT.fullmatch(t) and not PLACEHOLDER.search(t)]
    if not quotes:
        raise PermissionError(f"{what}: {path} needs a line `approved: <the owner's verbatim quote with «да»>`")
    if not lines:
        raise PermissionError(f'{what}: {path} needs a line `transcript: <session id> / <exact message text>`')
    named = [(q, t) for q in quotes for t in lines
             if ds.name.casefold() in _norm(q + ' ' + t) and FINAL in _norm(q + ' ' + t)]
    if not named:
        raise PermissionError(f'{what}: the quote or the message of {path} must name {ds.name} and {FINAL}')
    other = next(x for x in roles.DATASETS if x != ds.name)
    other_path = ds.paths.runs.with_name(roles.paths(other).runs.name) / ds.paths.approved.name
    oq, ot = _approvals(other_path)
    if {_norm(t) for t in lines} & {_norm(t) for t in ot} or {_norm(q) for q in quotes} & {_norm(q) for q in oq}:
        raise PermissionError(f'{what}: the «да» of {path} is also in {other_path}; each dataset needs its own')
    q, t = named[0]
    return {'approved': q, 'transcript': t, 'sha256': _sha(path)}


def selection_sha(ds: roles.Dataset) -> str:
    """sha256 of the bytes of ds.paths.selection."""
    return _sha(ds.paths.selection)


def start_test(ds: roles.Dataset) -> dict:
    """Writes the marker record {what: 'test.started', selection_sha256, selection_commit, approved_sha256,
    approved, transcript} once, after approved() and with selection.json committed; PermissionError if a marker
    exists already."""
    ok = approved(ds, 'start_test')
    sel = ds.paths.selection
    if not committed(sel):
        raise PermissionError(f'start_test: {sel} must exist, be in HEAD and have no uncommitted changes')
    if marker(ds) is not None:
        raise PermissionError(f'start_test: the marker {MARKER} exists already in {ds.paths.reads}')
    return log(ds, MARKER, [], selection_sha256=selection_sha(ds), selection_commit=last_commit(sel),
               approved_sha256=ok['sha256'], approved=ok['approved'], transcript=ok['transcript'])


def _share(ds: roles.Dataset, key: str, targets: pd.DataFrame) -> float:
    frame = xc.read_parquet(Path(ds.collection(key)) / xc.FRAME_FILE, columns=['user_id'])
    users = set(frame['user_id'].astype(np.int64))
    hit = set(targets.loc[targets['n_targets'] >= 1, 'user_id'].astype(np.int64)) & users
    return len(hit) / len(users) if users else 0.0


def c_test(ds: roles.Dataset, names: list[str]) -> pd.DataFrame:
    """C_test: fits of phase test whose specs are plan.test_specs of the committed curation and selection with the
    marker's sha. Every refusal of the gate is logged as 'c_test.refused' before PermissionError (§3.2): no marker,
    no approval or another test-approved.md than the marker's, the current selection sha or its last commit differ
    from the marker, selection.json has uncommitted changes, a fit fails a record check. No label is read before
    the gate passes. The record 'c_test' carries the scores sha256 of each fit and the target shares (§10.5).
    qid x fit."""
    names = list(names)
    sel = ds.paths.selection

    def refuse(reason: str):
        log(ds, 'c_test.refused', names, reason=reason)
        raise PermissionError(f'c_test: {reason}')

    mark = marker(ds)
    if mark is None:
        refuse(f'the marker {MARKER} is missing; broker.start_test first')
    try:
        ok = approved(ds, 'c_test')
    except PermissionError as e:
        refuse(str(e).removeprefix('c_test: '))
    if ok['sha256'] != mark.get('approved_sha256'):
        refuse('test-approved.md differs from the one of the test.started marker')
    if not sel.exists():
        refuse('selection.json is missing')
    current = selection_sha(ds)
    if current != mark.get('selection_sha256'):
        refuse('selection.json differs from the one of the test.started marker')
    if not committed(sel):
        refuse('selection.json has uncommitted changes')
    if last_commit(sel) != mark.get('selection_commit'):
        refuse('selection.json was committed again after the test.started marker')
    try:
        expected = expected_specs(ds, ['test'], 'c_test')
        got, shas = frames(ds, names, expected, 'test', 'c_test')
        _check_frames(ds, got, 'test', None)
    except (PermissionError, ValueError) as e:
        refuse(str(e).removeprefix('c_test: '))
    read = labels_of(ds, 'test')
    out = table(ds, got, 'test', None, read)
    shares = {'select': _share(ds, 'select', labels_of(ds, 'select')[1]), 'test': _share(ds, 'test', read[1])}
    log(ds, 'c_test', names, scores=shas, selection_sha256=current, target_shares=shares)
    return out


def target_shares(ds: roles.Dataset) -> dict:
    """{'select': share, 'test': share} of frame users with at least one target, from the last c_test record
    (computed in that read); PermissionError before a c_test read."""
    found = [r for r in reads(ds) if r.get('what') == 'c_test']
    if not found:
        raise PermissionError('target_shares: only after the C_test read')
    return dict(found[-1]['target_shares'])
