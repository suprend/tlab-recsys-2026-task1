"""Side experiments of the 22.10 night plan (E4: H8, H6, H13), outside the council and the xfer stamp.

Shared guard of the three modules (council/runs/night/2026-10-22-plan.md п. 2, п. 3; critique п. 2, п. 3):

- Output goes only to artifacts/side/<name>/ and council/runs/side/ (`Out`); every write goes through `Out.path`,
  which refuses anything else. Tests move both roots under /tmp/tlab-.
- `protected_snapshot()` lists every file and directory of artifacts/xfer and artifacts/task1 with size and
  mtime_ns (closed label directories are listed, not entered); a run takes it once it holds the heavy lock (or has
  passed the light gate) and again before it lets go, and `protected_diff` names any change. A changed tree makes
  the run's result `status: refused` and the process exit with PROTECTED_EXIT.
- Heavy inputs (fits) run inside `heavy_step`: council.xfer.queue.heavy('side <name>', dataset) (the shared
  /tmp/tlab-heavy.lock plus the FOREIGN process check for REES46 fits, queue, memory and compute) and the caller
  runs council.xfer.queue.check() before every fit. The lock holder record ('side <name>') makes
  queue.lock_holder() non-None, so ПРОВЕРКА-HEAVY of the plan holds REES46 heavy steps back while a side step runs.
- Light inputs (DuckDB on the REES46 database, H13) wait in `light_gate_wait`: council.xfer.queue.light_wait
  ('probe', journals) over the xfer journals and the side journal, as a probe of the council does.

Journal of the side steps: council/runs/side/queue.jsonl (heavy wait/start/end with the peak, light-start/-end).
Nothing here reads data. Modules import council.xfer.queue only (no change to council/xfer/*).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART_ROOT = ROOT / 'artifacts' / 'side'
RUNS_ROOT = ROOT / 'council' / 'runs' / 'side'
PROTECTED = (ROOT / 'artifacts' / 'xfer', ROOT / 'artifacts' / 'task1')
XFER_JOURNALS = (ROOT / 'council' / 'runs' / 'xfer-tinkoff' / 'queue.jsonl',
                 ROOT / 'council' / 'runs' / 'xfer-sber' / 'queue.jsonl')
TEST_PREFIX = '/tmp/tlab-'
PROTECTED_EXIT = 3
SKIP_DIR = 'sealed'           # closed label directories: listed with their mtime, never entered


class Refused(RuntimeError):
    """A side step refused to write or to go on (a path outside its roots, a changed protected tree)."""


# ---------------------------------------------------------------- outputs

class Out:
    """The two output roots of one side experiment: art = artifacts/side/<name>, runs = council/runs/side.
    Other roots are allowed only under /tmp/tlab- (tests)."""

    def __init__(self, name: str, art_root: Path | None = None, runs_root: Path | None = None):
        if not name or '/' in name or name.startswith('.'):
            raise Refused(f'bad side experiment name {name!r}')
        self.name = name
        art_root = Path(art_root) if art_root is not None else ART_ROOT
        runs_root = Path(runs_root) if runs_root is not None else RUNS_ROOT
        for r, default in ((art_root, ART_ROOT), (runs_root, RUNS_ROOT)):
            if os.path.abspath(r) != os.path.abspath(default) and not test_root(r):
                raise Refused(f'{r}: a side root is {default} or lies under {TEST_PREFIX}')
        self.art = art_root / name
        self.runs = runs_root
        self.journal = runs_root / 'queue.jsonl'

    def path(self, *parts, runs: bool = False) -> Path:
        """A path to write: under art (default) or runs; anything that resolves elsewhere is refused."""
        base = self.runs if runs else self.art
        p = base.joinpath(*[str(x) for x in parts])
        if not inside(p, base):
            raise Refused(f'{p} is outside {base}')
        for prot in PROTECTED:
            if inside(p, prot):
                raise Refused(f'{p} is inside the protected tree {prot}')
        return p

    def write_json(self, obj, *parts, runs: bool = False) -> Path:
        p = self.path(*parts, runs=runs)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f'.{p.name}.tmp-{os.getpid()}')
        tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=_default) + '\n', encoding='utf-8')
        os.replace(tmp, p)
        return p

    def write_frame(self, frame, *parts) -> Path:
        """A pandas frame to parquet under art, through DuckDB (pyarrow is not installed)."""
        import duckdb
        p = self.path(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f'.{p.name}.tmp-{os.getpid()}')
        con = duckdb.connect()
        try:
            con.register('_side_frame', frame)
            con.execute(f"COPY (SELECT * FROM _side_frame) TO '{str(tmp).replace(chr(39), chr(39) * 2)}' "
                        f"(FORMAT PARQUET)")
        finally:
            con.close()
        os.replace(tmp, p)
        return p


def test_root(r) -> bool:
    """True for a directory under /tmp/tlab- (macOS: /private/tmp/tlab- once resolved), with no way out."""
    a, rr = os.path.abspath(r), str(Path(r).resolve())
    return a.startswith(TEST_PREFIX) and (rr.startswith(TEST_PREFIX) or rr.startswith('/private' + TEST_PREFIX))


def inside(path: Path, base: Path) -> bool:
    try:
        Path(os.path.abspath(path)).relative_to(os.path.abspath(base))
    except ValueError:
        return False
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
    except ValueError:
        return False
    return True


def _default(x):
    try:
        import numpy as np
        if isinstance(x, np.generic):
            return x.item()
        if isinstance(x, np.ndarray):
            return x.tolist()
    except ImportError:
        pass
    return str(x)


# ---------------------------------------------------------------- protected trees

def protected_snapshot(roots=PROTECTED) -> dict:
    """path -> [kind, size, mtime_ns] of every entry under each root (missing root -> marker). Closed label
    directories (SKIP_DIR) are entries with their own mtime but are not entered."""
    out = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            out[str(root)] = ['missing', 0, 0]
            continue
        st = root.lstat()
        out[str(root)] = ['dir', 0, st.st_mtime_ns]
        for dirpath, dirnames, filenames in os.walk(root):
            entries = dirnames + filenames
            dirnames[:] = [d for d in dirnames if d != SKIP_DIR]   # the closed directory itself stays an entry
            for n in entries:
                p = os.path.join(dirpath, n)
                try:
                    s = os.lstat(p)
                except FileNotFoundError:
                    continue
                kind = 'dir' if stat.S_ISDIR(s.st_mode) else 'file'
                out[p] = [kind, 0 if kind == 'dir' else s.st_size, s.st_mtime_ns]
    return out


def protected_diff(before: dict, after: dict) -> dict:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return {'added': added, 'removed': removed, 'changed': changed,
            'n': len(added) + len(removed) + len(changed)}


def protected_verdict(before: dict, roots=PROTECTED) -> dict:
    d = protected_diff(before, protected_snapshot(roots))
    return {'unchanged': d['n'] == 0, 'roots': [str(r) for r in roots], 'entries': len(before),
            'changes': d['n'], 'first': (d['added'] + d['removed'] + d['changed'])[:50]}


# ---------------------------------------------------------------- lock, process check, light gate

@contextlib.contextmanager
def heavy_step(name: str, dataset: str, out: Out, *, wait: bool = True, **kw):
    """council.xfer.queue.heavy('side <name>', dataset), journalled in the side journal. kw: lock_path, procs_fn,
    sleep, poll, own (tests)."""
    from council.xfer import queue as Q
    with Q.heavy(f'side {name}', dataset, log=out.journal, wait=wait, **kw) as lock:
        yield lock


def check(procs=None, own=None) -> None:
    """council.xfer.queue.check(): Busy if a foreign heavy process (REES46 fit/queue/memory/compute, an xfer
    script) runs. Called before every fit inside heavy_step."""
    from council.xfer import queue as Q
    Q.check(procs, own)


def light_gate_wait(name: str, dataset: str, out: Out, *, wait: bool = True, **kw) -> None:
    """council.xfer.queue.light_wait('probe', ...) over both xfer journals and the side journal."""
    from council.xfer import queue as Q
    Q.light_wait('probe', [*XFER_JOURNALS, out.journal], log=out.journal, dataset=dataset, wait=wait, **kw)


def journal(out: Out, record: dict) -> dict:
    from council.xfer import queue as Q
    return Q.journal(out.journal, record)


def peak_rss_gb() -> float:
    from council.xfer import queue as Q
    return Q.peak_rss_gb()


# ---------------------------------------------------------------- identity

def code_identity(*modules) -> dict:
    """sha256 (16 hex) of council/side/__init__.py and the given module files."""
    files = [Path(__file__)] + [Path(m) for m in modules]
    return {Path(f).resolve().relative_to(ROOT).as_posix() if inside(f, ROOT) else str(f):
            hashlib.sha256(Path(f).read_bytes()).hexdigest()[:16] for f in files}


def now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


def print_json(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False, default=_default), flush=True)
