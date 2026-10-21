"""Heavy steps of the council on xfer: the shared lock, the process guard, the light-step gate, the journal and
the fit queue (council/runs/xfer/contract.md §4, §6.6).

Heavy step = compute, a fit, a sidecar-like table. It holds fcntl.flock(LOCK_EX | LOCK_NB) on /tmp/tlab-heavy.lock
for its whole duration; without the lock it waits. A child process of the step (a fit) inherits the locked file
(pass_fds, contract §8.5): the lock lives as long as the child, even if the parent dies. The REES46 queue does not
take that lock, so before taking it and again before every fit the step lists the processes (`ps ax -o
pid=,ppid=,command=`: the command lines that `pgrep -af` prints, portable to macOS, where `pgrep -a` means ancestors)
and waits while any command line other than its own and its parent's matches FOREIGN: REES46 fits, queue and memory
trial (`-m council.fit|queue|memory`), the REES46 compute stage (`-m council.agents ... compute`) and python
launches of the xfer scripts (`python… scripts/xfer_<name>.py`, `python… -m scripts.xfer_<name>`; contract §8.11).
council.xfer processes never match; editors, grep and git on those files do not either.

Light step = an LLM stage or a probe (threads=4, DuckDB 4 GB). light_gate() says whether it may run next to the
heavy step of the moment (heavy_now): an LLM call always; a probe not next to a REES46 full_val/full_test fit (peak
~21 GB) or a REES46 council.memory / council.agents compute run (§13.2), nor next to a heavy step whose
journalled peak exceeds PEAK_LIMIT_GB or is unknown (contract §8.6).
run.probe_gate wraps it as the `gate` of sandbox.probe_stage (asked before every probe, §8.7); light_wait()
is the blocking form.

Journal: one JSON line per event in council/runs/xfer-<x>/queue.jsonl (waits, starts, ends with the peak RSS of
the process and its children, fit peaks, refusals).

The fit queue (`run`): a JSON list of council.xfer.fit specs, each fit in its own `python -I council/xfer/run.py
--dataset <x> fit-one` process under heavy(); the identity of the code (xc.code_identity and the council stamp)
and the data fingerprint of every spec are taken once at the start, a change between fits stops the queue. Spec,
stamp and data reach the child as files in the queue's temporary directory, never in argv (contract §8.4).
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from council.xfer import roles

LOCK_PATH = Path('/tmp/tlab-heavy.lock')
FOREIGN = (
    re.compile(r'-m council\.(fit|queue|memory)\b'),
    re.compile(r'-m council\.agents\b.*\bcompute\b'),
    re.compile(r'(^|/)python[\w.]*\s(.*\s)?\S*scripts/xfer_\w+\.py\b', re.I),
    re.compile(r'(^|/)python[\w.]*\s(.*\s)?-m\s*scripts\.xfer_\w+', re.I),
)
REES46_FIT = re.compile(r'-m council\.fit\b')
REES46_UNKNOWN = re.compile(r'-m council\.memory\b|-m council\.agents\b.*\bcompute\b')   # REES46 heavy, peak unknown
SPEC_ARG = re.compile(r'--spec[ =](\S+)')
FULL_RECIPES = ('full_val', 'full_test')        # REES46 recipes of ~21 GB peak: they run alone
PEAK_LIMIT_GB = 20.0                            # contract §4: probes run next to a heavy step peaking <= 20 GB
POLL_SECONDS = 30.0
LIGHT_KINDS = ('llm', 'probe')


class Busy(RuntimeError):
    """A heavy step cannot start now (a foreign process runs or the lock is held) and was told not to wait."""


# ---------------------------------------------------------------- processes

def processes() -> list[tuple[int, int, str]]:
    """(pid, ppid, command line) of every process, from ps."""
    out = subprocess.run(['ps', 'ax', '-o', 'pid=,ppid=,command='], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) == 3 else ''))
    return rows


def is_foreign(command: str) -> bool:
    """True if a command line is a REES46 heavy process or an xfer series/sidecar process (FOREIGN)."""
    return any(p.search(command) for p in FOREIGN)


def foreign(procs=None, own=None) -> list[tuple[int, str]]:
    """(pid, command) of the foreign heavy processes, without this process and its parent (or the pids in `own`)."""
    procs = processes() if procs is None else procs
    own = {os.getpid(), os.getppid()} if own is None else set(own)
    return [(pid, cmd) for pid, _, cmd in procs if pid not in own and is_foreign(cmd)]


def rees46_full(procs=None, own=None) -> list[tuple[int, str]]:
    """REES46 fits (`-m council.fit --spec f`) whose spec file names a full_val/full_test recipe. A spec file that
    cannot be read counts as full (the safe side)."""
    out = []
    for pid, cmd in foreign(procs, own):
        if not REES46_FIT.search(cmd):
            continue
        m = SPEC_ARG.search(cmd)
        recipe = None
        if m:
            try:
                recipe = json.loads(Path(m.group(1)).read_text()).get('recipe')
            except (OSError, ValueError, AttributeError):
                recipe = None
        if recipe is None or recipe in FULL_RECIPES:
            out.append((pid, cmd))
    return out


# ---------------------------------------------------------------- lock

def try_lock(path: Path = LOCK_PATH):
    """An open file holding flock(LOCK_EX | LOCK_NB) on `path`, or None when another holder has it."""
    f = open(path, 'a+')
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def release(f) -> None:
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()


def _holder(f, what, dataset):
    """Who holds the lock, for people reading the lock file; the lock itself is the flock, not this text."""
    f.seek(0)
    f.truncate()
    f.write(json.dumps({'pid': os.getpid(), 'what': what, 'dataset': dataset,
                        'since': time.strftime('%Y-%m-%d %H:%M:%S')}) + '\n')
    f.flush()


# ---------------------------------------------------------------- journal

def journal(path: Path | None, record: dict) -> dict:
    """Append one record (with `at`) to a queue journal; path None writes nothing (tests, dry runs)."""
    rec = {'at': time.strftime('%Y-%m-%d %H:%M:%S')} | record
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
    return rec


def entries(path: Path) -> list[dict]:
    """Journal records. A broken last line (a step killed while appending) is skipped with a warning on stderr;
    a broken line before it is an error (contract §8.12)."""
    path = Path(path)
    if not path.exists():
        return []
    lines = [x for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    out = []
    for i, line in enumerate(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            if i != len(lines) - 1:
                raise ValueError(f'{path}: line {i + 1} is broken') from None
            print(f'warning: {path}: the last line is broken and skipped', file=sys.stderr)
    return out


def peaks(path: Path) -> dict:
    """what -> the largest journalled peak (GB) of a step of that name (heavy `end` and light `light-end`; heavy_now
    looks only at the kind of the heavy lock holder, 'fit' or 'compute')."""
    out = {}
    for r in entries(path):
        if isinstance(r.get('peak_gb'), (int, float)) and not isinstance(r.get('peak_gb'), bool):
            out[r['what']] = max(out.get(r['what'], 0.0), float(r['peak_gb']))
    return out


# ---------------------------------------------------------------- heavy step and light gate

def check(procs=None, own=None) -> None:
    """Busy if a foreign heavy process runs (called before every fit inside a heavy step)."""
    found = foreign(procs, own)
    if found:
        raise Busy(f'foreign heavy processes run: {[p for p, _ in found]}')


@contextlib.contextmanager
def heavy(what: str, dataset: str, *, log: Path | None = None, wait: bool = True, poll: float = POLL_SECONDS,
          lock_path: Path = LOCK_PATH, procs_fn=processes, sleep=time.sleep, own=None):
    """Hold the heavy lock for the body. Before taking it and right after, no foreign process may run; otherwise
    wait (poll seconds) or, with wait=False, raise Busy. Journal: wait (once per reason), start, end."""
    waited = None
    while True:
        found = foreign(procs_fn(), own)
        f = None
        if not found:
            f = try_lock(lock_path)
            if f is not None:
                found = foreign(procs_fn(), own)
                if found:
                    release(f)
                    f = None
        if f is not None:
            break
        reason = ('foreign: ' + ', '.join(str(p) for p, _ in found)) if found else 'lock held'
        if not wait:
            journal(log, {'event': 'refused', 'what': what, 'dataset': dataset, 'reason': reason})
            raise Busy(f'{what}: {reason}')
        if reason != waited:
            journal(log, {'event': 'wait', 'what': what, 'dataset': dataset, 'reason': reason})
            waited = reason
        sleep(poll)
    _holder(f, what, dataset)
    t0 = time.time()
    journal(log, {'event': 'start', 'what': what, 'dataset': dataset, 'pid': os.getpid()})
    ok = False
    try:
        yield f
        ok = True
    finally:
        journal(log, {'event': 'end', 'what': what, 'dataset': dataset, 'ok': ok,
                      'seconds': round(time.time() - t0, 1), 'peak_gb': peak_rss_gb()})
        release(f)


def peak_rss_gb() -> float:
    """Peak resident set (GB) of this process and of its largest waited-for child (resource.getrusage; ru_maxrss
    is bytes on macOS, kilobytes on Linux). Lifetime maxima: inside a long queue process it is the largest so far,
    the safe side."""
    unit = 1 if sys.platform == 'darwin' else 1024
    rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    return round(rss * unit / 1024 ** 3, 3)


def spawn(cmd: list[str], lock, **kw) -> subprocess.CompletedProcess:
    """subprocess.run with the locked file inherited by the child (pass_fds): the flock is shared by the open file
    description, so it outlives the parent while the child runs."""
    return subprocess.run(cmd, pass_fds=(lock.fileno(),), **kw)


def lock_holder(lock_path: Path = LOCK_PATH) -> dict | None:
    """The holder record of the heavy lock while somebody holds it ({pid, what, dataset, since}), else None."""
    f = try_lock(lock_path)
    if f is not None:
        release(f)
        return None
    try:
        return json.loads(Path(lock_path).read_text(encoding='utf-8').splitlines()[0])
    except (OSError, ValueError, IndexError):
        return {'what': None}


def kind_of(what: str) -> str:
    """The kind of a step for peak lookups: the first word of `what` ('fit', 'compute'; light: 'probe')."""
    return str(what or '').split(' ', 1)[0]


def heavy_now(journals, lock_path: Path = LOCK_PATH) -> dict | None:
    """The heavy step of the moment: None when the lock is free, else {what, peak_gb}; peak_gb is the largest peak
    journalled in `journals` (the queue.jsonl of both datasets) for a step of the same kind, None when unknown."""
    holder = lock_holder(lock_path)
    if holder is None:
        return None
    kind = kind_of(holder.get('what'))
    found = [v for j in journals for w, v in peaks(j).items() if kind and kind_of(w) == kind]
    return {'what': holder.get('what'), 'peak_gb': max(found) if found else None}


def light_gate(kind: str, *, procs=None, own=None, heavy: dict | None = None) -> list[str]:
    """Reasons a light step may not run now ([] = it may). kind 'llm': never refused. kind 'probe': refused next
    to a REES46 full fit or a REES46 memory/compute run (council.memory, council.agents compute: peak unknown),
    and next to a heavy step (heavy = heavy_now(...), None when none runs) whose peak is
    unknown or exceeds PEAK_LIMIT_GB."""
    if kind not in LIGHT_KINDS:
        raise ValueError(f'light kind {kind!r} not in {LIGHT_KINDS}')
    if kind == 'llm':
        return []
    procs = processes() if procs is None else procs
    out = [f'REES46 full fit {pid} runs alone' for pid, _ in rees46_full(procs, own)]
    out += [f'REES46 heavy step {pid} has no known peak' for pid, cmd in foreign(procs, own)
            if REES46_UNKNOWN.search(cmd)]
    if heavy is not None:
        peak = heavy.get('peak_gb')
        if peak is None:
            out.append(f"the heavy step {heavy.get('what')!r} has no journalled peak yet")
        elif peak > PEAK_LIMIT_GB:
            out.append(f"the heavy step {heavy.get('what')!r} peaks at {peak} GB > {PEAK_LIMIT_GB}")
    return out


def light_wait(kind: str, journals, *, log: Path | None = None, dataset: str | None = None, wait: bool = True,
               poll: float = POLL_SECONDS, lock_path: Path = LOCK_PATH, procs_fn=processes, sleep=time.sleep,
               own=None) -> None:
    """Block until light_gate(kind) has no reason (journal 'light-wait' once per reason); with wait=False raise
    Busy instead."""
    waited = None
    while True:
        reasons = light_gate(kind, procs=procs_fn(), own=own, heavy=heavy_now(journals, lock_path))
        if not reasons:
            return
        reason = '; '.join(reasons)
        if not wait:
            raise Busy(f'{kind}: {reason}')
        if reason != waited:
            journal(log, {'event': 'light-wait', 'what': kind, 'dataset': dataset, 'reason': reason})
            waited = reason
        sleep(poll)


# ---------------------------------------------------------------- fit queue

RUN_PY = roles.ROOT / 'council' / 'xfer' / 'run.py'


def load(ds, path) -> list[dict]:
    """Normalized specs of a queue file (fit.validate each); SystemExit on any invalid spec or repeated name."""
    from council.xfer import fit
    queue = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(queue, list) or not queue:
        raise SystemExit(f'{path}: a queue is a non-empty JSON list of specs')
    specs = []
    for x in queue:
        try:
            specs.append(fit.validate(ds, x))
        except ValueError as e:
            raise SystemExit(f'{path}: {e}') from None
    names = [s['name'] for s in specs]
    if len(set(names)) != len(names):
        raise SystemExit(f'{path}: repeated fit names')
    return specs


def fit_command(ds, spec_file: Path, stamp_file: Path, data_file: Path) -> list[str]:
    """argv of one fit process: file paths only (spec, code stamp, data stamp), and --root when the dataset was
    activated on a test root."""
    root = ['--root', str(ds.paths.root)] if getattr(ds.paths, 'root', None) is not None else []
    return [sys.executable, '-I', str(RUN_PY), '--dataset', ds.name, *root, 'fit-one', '--spec', str(spec_file),
            '--stamp', str(stamp_file), '--data', str(data_file)]


def write_inputs(tmp: Path, spec: dict, stamp: dict, data: dict) -> tuple[Path, Path, Path]:
    """spec.json, stamp.json and data.json of one fit in the queue's temporary directory."""
    out = []
    for name, obj in (('spec', spec), ('stamp', stamp), ('data', data)):
        f = Path(tmp) / f'{name}.json'
        f.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
        out.append(f)
    return tuple(out)


def run(ds, path, *, wait: bool = True) -> list[dict]:
    """Run a queue file of fit specs one at a time, each in its own process under heavy(); returns what happened
    per spec. A fit done with the same spec, data and code stamp is skipped; fit.done(ds, spec, data, stamp) stops
    the queue (SystemExit) on a record with another stamp (contract §8.3), as do a failed fit, a changed code
    identity and a fit that ends without its record. The child inherits the lock (spawn, pass_fds)."""
    from council.xfer import fit
    specs = load(ds, path)
    stamp = fit.code_stamp(ds)
    data = {s['name']: fit.data_stamp(ds, s) for s in specs}
    log = ds.paths.queue_log
    out = []
    for s in specs:
        if fit.done(ds, s, data[s['name']], stamp):
            out.append({'name': s['name'], 'skipped': 'done with the same spec'})
            continue
        if fit.code_stamp(ds) != stamp:
            journal(log, {'event': 'stop', 'what': s['name'], 'dataset': ds.name, 'reason': 'code changed'})
            raise SystemExit(f"{s['name']}: the code identity changed since the queue started")
        with heavy(f"fit {s['name']}", ds.name, log=log, wait=wait) as lock:
            check()
            with tempfile.TemporaryDirectory(prefix='council-xfer-queue-') as tmp:
                files = write_inputs(Path(tmp), s, stamp, data[s['name']])
                r = spawn(fit_command(ds, *files), lock, cwd=roles.ROOT)
        if r.returncode:
            journal(log, {'event': 'failed', 'what': s['name'], 'dataset': ds.name, 'code': r.returncode})
            raise SystemExit(r.returncode)
        if not fit.done(ds, s, data[s['name']], stamp):
            raise SystemExit(f"{s['name']}: the fit ended without writing its scores and record")
        rec = fit.records(ds).get(s['name'], {})
        journal(log, {'event': 'peak', 'what': f"fit {s['name']}", 'dataset': ds.name, 'peak_gb': rec.get('peak_rss_gb')})
        out.append({'name': s['name'], 'done': True, 'peak_gb': rec.get('peak_rss_gb')})
    return out
