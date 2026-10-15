"""TMP-only reviewed-harness process observation; importing never launches a process.

No general Darwin process-tree containment claim: enumeration is sampled and cannot
reap orphaned nonchildren. Successful normal runs additionally require the caller's
six known worker/reaped-receipt ledger. Sampled RSS is not a kernel memory limit.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
import errno
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time


class ObservationError(RuntimeError):
    pass


class OwnershipLost(ObservationError):
    pass


@dataclass
class ChildOwnership:
    """Shared with the launch wrapper before the core can fail or be interrupted.

    A wait-in-progress interruption is uncertain: the syscall may already have
    reaped the child. A saved wait result is authoritative even if later Python
    work is interrupted before the core returns its normal report.
    """
    pid: int | None
    identity: Identity | None = None
    wait_result: tuple | None = None
    phase: str = "popen_owned"
    report: dict | None = None

    @property
    def reaped(self):
        return self.wait_result is not None or (self.report is not None and self.report.get("reaped") is True)

    def wait(self):
        if self.reaped or self.phase == "lost":
            raise OwnershipLost("wait attempted after original ownership ended")
        self.phase = "wait_in_progress"
        try:
            result = os.wait4(self.pid, os.WNOHANG)
        except ChildProcessError as exc:
            self.phase = "lost"
            raise OwnershipLost("direct child reaped elsewhere; actual CPU unknown") from exc
        except BaseException:
            self.phase = "wait_uncertain"
            raise
        if result[0]:
            if result[0] != self.pid:
                self.phase = "lost"
                raise OwnershipLost("wait4 returned unexpected child")
            self.wait_result = result
            self.phase = "reaped"
        else:
            self.phase = "popen_owned"
        return result


@dataclass(frozen=True)
class Identity:
    pid: int
    start: tuple[int, ...]


@dataclass(frozen=True)
class Process:
    identity: Identity
    ppid: int
    pgid: int
    uid: int
    zombie: bool


@dataclass(frozen=True)
class Usage:
    process: Process
    self_cpu: float
    waited_cpu: float
    rss_bytes: int


class BSDInfo(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in (
        "flags", "status", "xstatus", "pid", "ppid", "uid", "gid",
        "ruid", "rgid", "svuid", "svgid", "reserved")]
    _fields_ += [("comm", C.c_char * 16), ("name", C.c_char * 32)]
    _fields_ += [(n, C.c_uint32) for n in (
        "nfiles", "pgid", "jobc", "tdev", "tpgid")]
    _fields_ += [("nice", C.c_int32), ("start_sec", C.c_uint64),
                 ("start_usec", C.c_uint64)]


class RUsageV1(C.Structure):
    _fields_ = [("uuid", C.c_uint8 * 16)] + [(n, C.c_uint64) for n in (
        "user", "system", "idle_wakeups", "interrupt_wakeups", "pageins",
        "wired", "resident", "footprint", "start_absolute", "exit_absolute",
        "child_user", "child_system", "child_idle_wakeups",
        "child_interrupt_wakeups", "child_pageins", "child_elapsed")]


class Timebase(C.Structure):
    _fields_ = [("numer", C.c_uint32), ("denom", C.c_uint32)]


def ticks_seconds(ticks: int, numer: int, denom: int) -> float:
    if any(type(n) is not int or n < 0 for n in (ticks, numer, denom)):
        raise ValueError("invalid Mach timebase/tick type")
    if not numer or not denom:
        raise ValueError("zero Mach timebase")
    return (ticks * numer / denom) / 1_000_000_000


def _missing(err: int) -> bool:
    return err in (errno.ESRCH, errno.ENOENT)


class Darwin:
    """Lazy libproc binding. Instantiate only inside an approved supervisor."""
    def __init__(self):
        if C.sizeof(BSDInfo) != 136 or C.sizeof(RUsageV1) != 144:
            raise ObservationError("unsupported Darwin struct ABI")
        self.lib = C.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        self.lib.proc_listchildpids.argtypes = [C.c_int, C.c_void_p, C.c_int]
        self.lib.proc_listchildpids.restype = C.c_int
        self.lib.proc_pidinfo.argtypes = [C.c_int, C.c_int, C.c_uint64,
                                         C.c_void_p, C.c_int]
        self.lib.proc_pidinfo.restype = C.c_int
        self.lib.proc_pid_rusage.argtypes = [C.c_int, C.c_int, C.c_void_p]
        self.lib.proc_pid_rusage.restype = C.c_int
        mach = C.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        mach.mach_timebase_info.argtypes = [C.POINTER(Timebase)]
        mach.mach_timebase_info.restype = C.c_int
        tb = Timebase()
        if mach.mach_timebase_info(C.byref(tb)) != 0 or not tb.numer or not tb.denom:
            raise ObservationError("Mach timebase unavailable")
        self.timebase = (int(tb.numer), int(tb.denom))
        self.root_pid = os.getpid()
        self.root_uid = os.geteuid()
        self.root_identity = None
        self.known_owned = set()
        self.authenticated_edges = set()

    def process(self, pid: int) -> Process | None:
        value = BSDInfo()
        C.set_errno(0)
        n = self.lib.proc_pidinfo(pid, 3, 0, C.byref(value), C.sizeof(value))
        if n != C.sizeof(value):
            if n == 0 and _missing(C.get_errno()):
                return None
            raise ObservationError(f"proc_pidinfo({pid}) short/error: {n}, errno={C.get_errno()}")
        if value.pid != pid:
            raise ObservationError("libproc returned another PID")
        return Process(Identity(pid, (int(value.start_sec), int(value.start_usec))),
                       int(value.ppid), int(value.pgid), int(value.uid), value.status == 5)

    def child_pids(self, ppid: int) -> list[int]:
        # proc_listchildpids returns a COUNT; its buffer argument is in BYTES.
        # A leaf's zero count is valid only with errno still zero.
        C.set_errno(0)
        count = self.lib.proc_listchildpids(ppid, None, 0)
        if count < 0 or (count == 0 and C.get_errno()):
            raise ObservationError(f"proc_listchildpids({ppid}) count errno={C.get_errno()}")
        if count == 0:
            return []
        for _ in range(4):
            capacity = count + max(16, count // 4)
            values = (C.c_int * capacity)()
            C.set_errno(0)
            count = self.lib.proc_listchildpids(ppid, values, C.sizeof(values))
            if count < 0 or (count == 0 and C.get_errno()):
                raise ObservationError(f"proc_listchildpids({ppid}) fill errno={C.get_errno()}")
            if count < capacity:
                result = list(values[:count])
                if any(pid <= 0 or pid == ppid for pid in result) or len(set(result)) != len(result):
                    raise ObservationError("invalid/duplicate child PID enumeration")
                return result
        raise ObservationError("process enumeration repeatedly filled buffer")

    def inventory(self) -> dict[int, Process]:
        """Observe our own family, never enumerate every app on the machine.

        Original known identities remain eligible after reparenting. EPERM for
        any enumerated/tracked potential member is never skipped. This remains
        sampled discovery, not atomic hostile-process containment.
        """
        # Pure __new__ fixtures predating this bookkeeping have no edge store.
        # Initialize it empty; known_owned never substitutes for lineage proof.
        if not hasattr(self, "authenticated_edges"):
            self.authenticated_edges = set()
        root = self.process(self.root_pid)
        if root is None or root.uid != self.root_uid:
            raise ObservationError("supervisor identity/UID unavailable")
        if self.root_identity is not None and root.identity != self.root_identity:
            raise ObservationError("supervisor birth identity changed")
        self.root_identity = root.identity
        result = {self.root_pid: root}
        for identity in sorted(self.known_owned, key=lambda item: (item.pid, item.start)):
            if identity == root.identity:
                continue
            current = self.process(identity.pid)
            if current is None or current.identity != identity:
                continue  # Proven dead/recycled identities are not adopted.
            if current.uid != root.uid:
                raise ObservationError("tracked original descendant UID changed")
            result[identity.pid] = current
        queue = list(result.values())
        visited = set()
        while queue:
            parent = queue.pop()
            if parent.identity in visited:
                continue
            visited.add(parent.identity)
            current = self.process(parent.identity.pid)
            if current is None or current.identity != parent.identity:
                result.pop(parent.identity.pid, None)
                continue
            if current.uid != root.uid:
                raise ObservationError("owned parent UID changed")
            result[current.identity.pid] = current
            children = self.child_pids(current.identity.pid)
            after = self.process(current.identity.pid)
            if after is None:
                if children:
                    raise ObservationError("parent vanished during nonempty child enumeration")
                result.pop(current.identity.pid, None)
                continue
            if after.identity != current.identity or after.uid != root.uid:
                raise ObservationError("parent identity/UID changed during child enumeration")
            result[after.identity.pid] = after
            for pid in children:
                edge_before = self.process(current.identity.pid)
                if (edge_before is None or edge_before.identity != current.identity
                        or edge_before.uid != root.uid):
                    raise ObservationError("parent identity/UID changed before child metadata")
                child = self.process(pid)
                edge_after = self.process(current.identity.pid)
                if (edge_after is None or edge_after.identity != current.identity
                        or edge_after.uid != root.uid):
                    raise ObservationError("parent identity/UID changed after child metadata")
                if child is None:
                    continue  # Ordinary exit between list and metadata read.
                if child.ppid != current.identity.pid or child.uid != root.uid:
                    raise ObservationError("enumerated child parent/UID mismatch")
                if child.identity.start < current.identity.start:
                    raise ObservationError("enumerated child predates original parent")
                old = result.get(pid)
                if old is not None and old.identity != child.identity:
                    raise ObservationError("child birth changed during inventory")
                # Preserve this authenticated historical association before a
                # queued revisit can observe a new current PPID.
                self.authenticated_edges.add((current.identity, child.identity))
                result[pid] = child
                queue.append(child)
        if self.root_pid not in result:
            raise ObservationError("supervisor disappeared during inventory")
        self.known_owned.update(p.identity for p in result.values())
        return result

    def authenticated_descendants(self, root: Identity) -> frozenset[Identity]:
        """Historical exact-birth closure, never all supervisor-owned records.

        Dead/recycled intermediate ancestors do not erase genuine descendants.
        The core subsequently selects only current exact-birth endpoints.
        """
        edges = getattr(self, "authenticated_edges", ())
        reachable = {root}
        changed = True
        while changed:
            changed = False
            for parent, child in edges:
                if parent in reachable and child not in reachable:
                    reachable.add(child)
                    changed = True
        return frozenset(reachable - {root})

    def observe(self, identity: Identity) -> Usage | None:
        before = self.process(identity.pid)
        if before is None or before.identity != identity:
            return None
        value = RUsageV1()
        C.set_errno(0)
        status = self.lib.proc_pid_rusage(identity.pid, 1, C.byref(value))
        if status != 0:
            if _missing(C.get_errno()):
                return None
            raise ObservationError(f"proc_pid_rusage({identity.pid}) errno={C.get_errno()}")
        after = self.process(identity.pid)
        if after is None or after.identity != identity:
            return None
        numer, denom = self.timebase
        return Usage(after, ticks_seconds(int(value.user + value.system), numer, denom),
                     ticks_seconds(int(value.child_user + value.child_system), numer, denom),
                     int(value.resident))


def parse_linux_stat(text: str, *, uid: int, clock_ticks: int,
                     page_size: int) -> Usage:
    """Parse /proc/PID/stat; comm may contain spaces and closing parentheses."""
    end = text.rfind(")")
    begin = text.find("(")
    if begin < 1 or end <= begin or clock_ticks <= 0 or page_size <= 0:
        raise ObservationError("malformed /proc stat or units")
    try:
        pid = int(text[:begin].strip())
        fields = text[end + 1:].split()
        # fields[0] is kernel field3; starttime=22, RSS=24.
        if len(fields) < 22 or len(fields[0]) != 1:
            raise ValueError("short stat")
        ppid, pgid = int(fields[1]), int(fields[2])
        user, system = int(fields[11]), int(fields[12])
        cuser, csystem = int(fields[13]), int(fields[14])
        start, rss = int(fields[19]), int(fields[21])
        if min(pid, ppid, pgid, user, system, cuser, csystem, start, rss, uid) < 0 or pid == 0:
            raise ValueError("negative stat counter")
        process = Process(Identity(pid, (start,)), ppid, pgid, uid, fields[0] == "Z")
        return Usage(process, (user + system) / clock_ticks,
                     (cuser + csystem) / clock_ticks, rss * page_size)
    except (ValueError, IndexError) as exc:
        raise ObservationError("malformed /proc stat fields") from exc


class Linux:
    def __init__(self, proc_root: Path = Path("/proc")):
        self.root = proc_root
        self.ticks = int(os.sysconf("SC_CLK_TCK"))
        self.page = int(os.sysconf("SC_PAGE_SIZE"))

    def _read(self, pid: int) -> Usage | None:
        path = self.root / str(pid) / "stat"
        try:
            # Identity and counters come from one stat read; uid is a separate
            # ownership cross-check, not a way to establish PID identity.
            uid = path.stat().st_uid
            value = parse_linux_stat(path.read_text(), uid=uid,
                                     clock_ticks=self.ticks, page_size=self.page)
            if value.process.identity.pid != pid:
                raise ObservationError("/proc returned another PID")
            return value
        except (FileNotFoundError, ProcessLookupError):
            return None
        except PermissionError as exc:
            raise ObservationError(f"/proc access denied for {pid}") from exc

    def inventory(self) -> dict[int, Process]:
        result = {}
        for path in self.root.iterdir():
            if path.name.isdecimal():
                value = self._read(int(path.name))
                if value is not None:
                    result[value.process.identity.pid] = value.process
        return result

    def observe(self, identity: Identity) -> Usage | None:
        value = self._read(identity.pid)
        return value if value is not None and value.process.identity == identity else None


def backend():
    if sys.platform == "darwin":
        return Darwin()
    if sys.platform.startswith("linux"):
        return Linux()
    raise ObservationError("unsupported process observation platform")


def select_tree(root: Identity, inventory: dict[int, Process],
                previously_seen: set[Identity]) -> dict[int, Process]:
    """Keep previously observed descendants even after reparenting/setsid."""
    owned = {p.identity.pid: p for p in inventory.values()
             if p.identity == root or p.identity in previously_seen}
    changed = True
    while changed:
        changed = False
        for p in inventory.values():
            if p.identity.pid not in owned and p.ppid in owned:
                parent = owned[p.ppid]
                if p.uid != parent.uid:
                    raise ObservationError("unexpected descendant ownership")
                owned[p.identity.pid] = p
                changed = True
    return owned


def _select_job_tree(observer, root: Identity, inventory: dict[int, Process],
                     previously_seen: set[Identity]) -> dict[int, Process]:
    if isinstance(observer, Darwin):
        # Darwin inventory is rooted at the supervisor; siblings and their
        # families must not inherit the declared controller's job membership.
        previously_seen = previously_seen | observer.authenticated_descendants(root)
    return select_tree(root, inventory, previously_seen)


def live_totals(usages: list[Usage]) -> tuple[float, int]:
    """No prior per-process maxima, no ru_maxrss, no thread enumeration.

    Waited CPU is rolled into its parent, so only currently present processes
    are summed. Nonatomic sampling can transiently overcount at a reap boundary;
    it is an early-stop estimate, not the terminal actual accounting value.
    """
    if len({u.process.identity for u in usages}) != len(usages):
        raise ObservationError("duplicate process identity")
    if any(not math.isfinite(u.self_cpu + u.waited_cpu)
           or min(u.self_cpu, u.waited_cpu, u.rss_bytes) < 0 for u in usages):
        raise ObservationError("invalid usage counter")
    return math.fsum(u.self_cpu + u.waited_cpu for u in usages), sum(u.rss_bytes for u in usages)


def usage_cpu(value) -> float:
    result = float(value.ru_utime + value.ru_stime)
    if not math.isfinite(result) or result < 0:
        raise ObservationError("invalid getrusage/wait4 CPU")
    return result


def assert_fresh_supervisor() -> None:
    """Call before the one launch. Includes no subprocess/native library call."""
    value = resource.getrusage(resource.RUSAGE_CHILDREN)
    if usage_cpu(value) != 0 or value.ru_maxrss != 0:
        raise ObservationError("supervisor already reaped children")


def signal_observed(observer, processes: dict[int, Process], sig: int,
                    *, exclude_pid: int | None = None) -> list[int]:
    """Signal current original identities, including separately created groups.

    Individual validated PIDs avoid signaling an unrelated recycled group; every
    currently observed session/group is traversed. A post-check PID race remains
    on Darwin, so this is cooperative-harness cleanup, not hostile containment.
    """
    signaled = []
    for pid, old in sorted(processes.items(), reverse=True):
        if pid in (0, 1, os.getpid(), exclude_pid):
            continue
        value = observer.observe(old.identity)
        if value is not None and not value.process.zombie:
            try:
                os.kill(pid, sig)
                signaled.append(pid)
            except ProcessLookupError:
                pass
    return signaled


def supervise_direct_child(pid: int, started_monotonic: float, *,
                           cpu_limit: float = 60.0, wall_limit: float = 120.0,
                           rss_limit: int = 2 * 1024 ** 3,
                           cleanup_reserve_wall: float = 5.0,
                           cleanup_reserve_cpu: float = 5.0,
                           interval: float = .025, observer=None,
                           ownership: ChildOwnership | None = None) -> dict:
    """Wait/reap one already launched direct child. Never call Popen.poll/wait.

    Supervising process must be fresh. CPU includes its complete SELF lifetime
    plus the final wait4 child+waited-descendant rollup. Normal success still
    requires caller verification of every expected nested reaped-worker record.
    No final success is inferred from an output/status file.
    """
    if type(pid) is not int or pid <= 1 or pid == os.getpid():
        raise ValueError("invalid direct child")
    if not (0 < cleanup_reserve_wall < wall_limit and 0 < cleanup_reserve_cpu < cpu_limit
            and 0 < interval <= .1 and type(rss_limit) is int and rss_limit > 0
            and math.isfinite(started_monotonic) and started_monotonic <= time.monotonic()):
        raise ValueError("invalid original supervisor limits/clock")
    observer = backend() if observer is None else observer
    ownership = ChildOwnership(pid) if ownership is None else ownership
    if ownership.pid != pid or ownership.reaped or ownership.phase != "popen_owned":
        raise ObservationError("invalid original child ownership")
    initial = observer.inventory()
    if pid not in initial or initial[pid].ppid != os.getpid():
        raise ObservationError("child identity/parent unavailable before observation")
    root = initial[pid].identity
    ownership.identity = root
    initial_owned = _select_job_tree(observer, root, initial, {root})
    seen = {p.identity for p in initial_owned.values()}
    last_known = dict(initial_owned)
    sampled_peak = 0
    sampled_cpu_high = 0.0
    sample_count = 0
    stop_reason = None
    cleanup_started = None
    signaled = set()
    child_result = None
    errors = []
    while child_result is None:
        now = time.monotonic()
        try:
            inventory = observer.inventory()
            selected = _select_job_tree(observer, root, inventory, seen)
            seen.update(p.identity for p in selected.values())
            last_known.update(selected)
            observations = [u for p in selected.values()
                            if (u := observer.observe(p.identity)) is not None]
            own = observer.observe(inventory[os.getpid()].identity) if os.getpid() in inventory else None
            if own is None:
                raise ObservationError("supervisor RSS unavailable")
            live_cpu, resident = live_totals(observations)
            own_cpu = usage_cpu(resource.getrusage(resource.RUSAGE_SELF))
            sampled_cpu_high = max(sampled_cpu_high, own_cpu + live_cpu)
            sampled_peak = max(sampled_peak, resident + own.rss_bytes)
            sample_count += 1
            if stop_reason is None:
                if own_cpu + live_cpu >= cpu_limit - cleanup_reserve_cpu:
                    stop_reason = "cpu_cleanup_reserve"
                elif now - started_monotonic >= wall_limit - cleanup_reserve_wall:
                    stop_reason = "wall_cleanup_reserve"
                elif resident + own.rss_bytes > rss_limit:
                    stop_reason = "sampled_job_rss"
            if stop_reason is not None:
                if cleanup_started is None:
                    cleanup_started = now
                # Give the controller a chance to reap a terminated worker.
                sig = (signal.SIGKILL if now >= min(started_monotonic + wall_limit - 1,
                                                   cleanup_started + 1)
                       else signal.SIGTERM)
                signaled.update(signal_observed(observer, selected, sig,
                                               exclude_pid=pid if sig == signal.SIGTERM else None))
                if not any(p.identity != root and not p.zombie for p in selected.values()):
                    signaled.update(signal_observed(observer, selected, sig))
        except (OSError, ObservationError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            stop_reason = stop_reason or "process_observation_unknown"
            # Never authorize success after unknown observation. Kill only the
            # already-owned original identities; rediscovery resumes next pass.
            try:
                signaled.update(signal_observed(observer, last_known, signal.SIGKILL))
            except (OSError, ObservationError) as cleanup_error:
                errors.append(f"cleanup observation unknown: {cleanup_error}")
            # No raw old-PID fallback: the original identity remains required
            # once observed, and lost/reaped ownership forbids further signals.
            try:
                if _may_signal_direct(ownership, observer):
                    os.kill(pid, signal.SIGKILL)
                    signaled.add(pid)
            except ProcessLookupError:
                pass
        waited_pid, status, rusage = ownership.wait()
        if waited_pid:
            if waited_pid != pid:
                raise ObservationError("wait4 returned unexpected child")
            child_result = (status, rusage)
        elif time.monotonic() - started_monotonic >= wall_limit:
            # Bounded cleanup may be unable to reap a stuck/uninterruptible
            # child. Preserve unknown state; caller must not claim completion.
            return {"scope": "synthetic_harness_process_supervision", "status": "failed_unknown_active",
                    "stop_reason": stop_reason or "wall_limit", "reaped": False,
                    "actual_cpu": None, "sampled_cpu_high": sampled_cpu_high,
                    "sampled_job_rss_high": sampled_peak, "samples": sample_count,
                    "observed_process_count": len(seen), "errors": errors,
                    "signaled_pids": sorted(signaled), "arbitrary_descendant_containment": False}
        else:
            time.sleep(interval)
    status, rusage = child_result
    try:
        final_inventory = observer.inventory()
        remaining = _select_job_tree(observer, root, final_inventory, seen)
    except (OSError, ObservationError) as exc:
        errors.append(f"terminal scan unknown: {exc}")
        remaining = {p.identity.pid: p for p in last_known.values() if p.identity != root}
    survivors = [p.identity.pid for p in remaining.values()]
    if survivors:
        signaled.update(signal_observed(observer, remaining, signal.SIGKILL))
    actual = usage_cpu(resource.getrusage(resource.RUSAGE_SELF)) + usage_cpu(rusage)
    wall = time.monotonic() - started_monotonic
    exit_code = os.waitstatus_to_exitcode(status)
    valid = (exit_code == 0 and stop_reason is None and not errors and not survivors
             and actual <= cpu_limit and wall <= wall_limit and sampled_peak <= rss_limit)
    return {"scope": "synthetic_harness_process_supervision",
            "status": "normal_reaped_pending_worker_ledger" if valid else "failed",
            "stop_reason": stop_reason, "reaped": True, "exit_code": exit_code,
            "actual_cpu": actual, "direct_child_inclusive_cpu": usage_cpu(rusage),
            "supervisor_self_cpu": usage_cpu(resource.getrusage(resource.RUSAGE_SELF)),
            "wall_seconds": wall, "sampled_cpu_high": sampled_cpu_high,
            "sampled_job_rss_high": sampled_peak, "samples": sample_count,
            "observed_process_count": len(seen), "survivors_at_terminal_scan": survivors,
            "errors": errors, "signaled_pids": sorted(signaled),
            "worker_ledger_verified": False, "arbitrary_descendant_containment": False,
            "rss_is_sampled_not_hard_limit": True}


_UNREAPED = {}  # Keep Popen destructor from independently reaping an unknown child.


def _release_reaped(process, result):
    """A failed registry insertion must not mask a successful cleanup/reap."""
    process.returncode = result["exit_code"]
    if _UNREAPED.get(process.pid) is process:
        del _UNREAPED[process.pid]


def _may_signal_direct(ownership: ChildOwnership, observer) -> bool:
    if ownership.reaped or ownership.phase == "lost":
        return False
    if ownership.identity is None:
        # A freshly returned Popen owns its child before this supervisor ever
        # attempts wait4. An interrupted wait without an identity is uncertain.
        return ownership.phase == "popen_owned"
    value = observer.observe(ownership.identity)
    return (value is not None and value.process.identity == ownership.identity
            and value.process.ppid == os.getpid())


def _failure_cleanup(ownership: ChildOwnership, observer, *, started, wall_seconds,
                     primary: BaseException) -> dict:
    """Bounded best effort; secondary interruptions never replace the primary.

    At most three signal attempts and256 nonblocking wait attempts. A lost or
    already reaped child is never signaled/waited by its old PID. Darwin nested
    cleanup remains unknown on this emergency path.
    """
    errors = [f"primary {type(primary).__name__}: {primary}"]
    for _ in range(3):
        if ownership.reaped or ownership.phase == "lost":
            break
        try:
            if _may_signal_direct(ownership, observer):
                os.kill(ownership.pid, signal.SIGKILL)
            break
        except ProcessLookupError:
            break
        except BaseException as secondary:
            errors.append(f"cleanup signal {type(secondary).__name__}: {secondary}")
    try:
        deadline = min(started + wall_seconds, time.monotonic() + 5)
    except BaseException as secondary:
        errors.append(f"cleanup clock {type(secondary).__name__}: {secondary}")
        deadline = None
    for _ in range(256):
        if ownership.reaped or ownership.phase == "lost":
            break
        try:
            if deadline is None or time.monotonic() >= deadline:
                break
            if ownership.phase in ("wait_in_progress", "wait_uncertain"):
                if ownership.identity is None or not _may_signal_direct(ownership, observer):
                    ownership.phase = "lost"
                    errors.append("cleanup ownership uncertain; original birth/parent not verified")
                    break
            ownership.wait()
            if not ownership.reaped:
                time.sleep(.025)
        except OwnershipLost as secondary:
            errors.append(f"cleanup ownership {type(secondary).__name__}: {secondary}")
            break
        except BaseException as secondary:
            errors.append(f"cleanup wait {type(secondary).__name__}: {secondary}")
    # Preserve successful wait4 accounting even when terminal observation or
    # reporting was interrupted. Observation failure never fabricates a value.
    try:
        own = usage_cpu(resource.getrusage(resource.RUSAGE_SELF))
    except BaseException as secondary:
        own = None
        errors.append(f"cleanup self usage {type(secondary).__name__}: {secondary}")
    waited = ownership.wait_result
    report = ownership.report or {}
    child_cpu = usage_cpu(waited[2]) if waited is not None else report.get("direct_child_inclusive_cpu")
    exit_code = os.waitstatus_to_exitcode(waited[1]) if waited is not None else report.get("exit_code")
    return {"scope": "synthetic_harness_process_supervision", "status": "failed",
            "reaped": ownership.reaped, "exit_code": exit_code,
            "actual_cpu": own + child_cpu if own is not None and child_cpu is not None else None,
            "direct_child_inclusive_cpu": child_cpu,
            "sampled_job_rss_high": report.get("sampled_job_rss_high", 0),
            "errors": errors, "survivors_at_terminal_scan": [],
            "cleanup_nested_unknown": True, "ownership_phase": ownership.phase,
            "primary_exception_type": type(primary).__name__}


def supervise(argv, log_path, *, started, cpu_seconds=60, wall_seconds=120,
              rss_bytes=2 * 1024 ** 3, cwd):
    """The one launch seam. Definition only; no invocation occurs on import.

    Return status is a process-boundary claim, pending the caller's exact six
    worker ledger. ``actual_total_cpu_seconds`` is observed through terminal
    scan; an outer reaper or an explicitly charged final-tail reserve is needed
    for serialization/exit after this function returns.
    """
    if not (math.isfinite(cpu_seconds) and cpu_seconds > 5
            and math.isfinite(wall_seconds) and wall_seconds > 5
            and math.isfinite(started) and started <= time.monotonic()
            and type(rss_bytes) is int and rss_bytes > 0):
        raise ValueError("invalid prelaunch limits")
    assert_fresh_supervisor()
    observer = backend()
    if (time.monotonic() - started >= wall_seconds - 5
            or usage_cpu(resource.getrusage(resource.RUSAGE_SELF)) >= cpu_seconds - 5):
        raise ObservationError("original test budget cannot admit launch")
    # No bookkeeping constructor is allowed between Popen and its protected
    # cleanup boundary. This allocation can fail only before any launch.
    ownership = ChildOwnership(None)
    process = None
    try:
        with Path(log_path).open("xb") as log:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=log, start_new_session=True, cwd=cwd)
            ownership.pid = process.pid
            _UNREAPED[process.pid] = process
            result = supervise_direct_child(process.pid, started,
                                            cpu_limit=cpu_seconds, wall_limit=wall_seconds,
                                            rss_limit=rss_bytes, observer=observer,
                                            ownership=ownership)
            ownership.report = result
            if result["reaped"]:
                _release_reaped(process, result)
        return _terminal_report(result, started=started, cpu_seconds=cpu_seconds,
                                wall_seconds=wall_seconds)
    except BaseException as exc:
        if process is None:
            # Popen did not return a process handle. No old PID is invented.
            exc.supervisor_cleanup_evidence = {
                "scope": "synthetic_harness_process_supervision",
                "status": "failed_unknown_launch", "launch_returned": False,
                "reaped": False, "cleanup_nested_unknown": True,
                "errors": [f"primary {type(exc).__name__}: {exc}"]}
            raise
        # Also recover binding if interruption occurred immediately after the
        # handle returned, before the first postlaunch bookkeeping assignment.
        if ownership.pid is None:
            ownership.pid = process.pid
        try:
            result = _failure_cleanup(ownership, observer, started=started,
                                      wall_seconds=wall_seconds, primary=exc)
            if result["reaped"]:
                _release_reaped(process, result)
        except BaseException as secondary:
            # Retain primary reason and known raw facts; no old-PID retry.
            exc.supervisor_cleanup_evidence = {
                "scope": "synthetic_harness_process_supervision",
                "status": "failed_unknown_cleanup", "reaped": ownership.reaped,
                "retained_wait4_result": ownership.wait_result,
                "ownership_phase": ownership.phase, "cleanup_nested_unknown": True,
                "errors": [f"primary {type(exc).__name__}: {exc}",
                           f"cleanup bookkeeping {type(secondary).__name__}: {secondary}"]}
            raise exc from secondary
        exc.supervisor_cleanup_evidence = result
        if not isinstance(exc, Exception):
            raise
        try:
            return _terminal_report(result, started=started, cpu_seconds=cpu_seconds,
                                    wall_seconds=wall_seconds)
        except BaseException as secondary:
            result["errors"].append(f"cleanup report {type(secondary).__name__}: {secondary}")
            raise exc from secondary


def _terminal_report(result, *, started, cpu_seconds, wall_seconds):
    """No launch ownership is created here; caller keeps this inside its try."""
    own_observed = usage_cpu(resource.getrusage(resource.RUSAGE_SELF))
    finalization_cpu_reserve = 2.0
    cpu_upper = (result.get("direct_child_inclusive_cpu") + own_observed + finalization_cpu_reserve
                 if result.get("direct_child_inclusive_cpu") is not None else None)
    # Only now may supervisor lower its hard CPU fence: earlier inheritance
    # would prevent unmodified production workers setting their original caps.
    if result["reaped"]:
        final_hard = math.ceil(own_observed) + 1
        _, old_hard = resource.getrlimit(resource.RLIMIT_CPU)
        if old_hard != resource.RLIM_INFINITY:
            final_hard = min(final_hard, old_hard)
        resource.setrlimit(resource.RLIMIT_CPU, (final_hard, final_hard))
    else:
        final_hard = None
    elapsed = time.monotonic() - started
    valid = (result["status"] == "normal_reaped_pending_worker_ledger"
             and cpu_upper is not None and cpu_upper <= cpu_seconds
             and elapsed + 5 <= wall_seconds)
    return {**result, "status": "verified_normal_exit" if valid else "failed_unknown_cleanup",
            "exit_code": result.get("exit_code"), "wait4_child_cpu_seconds": result.get("direct_child_inclusive_cpu"),
            "actual_total_cpu_seconds": None,
            "observed_total_cpu_seconds": result.get("actual_cpu"),
            "cpu_upper_seconds": cpu_upper, "finalization_cpu_reserve_seconds": finalization_cpu_reserve,
            "supervisor_finalization_hard_cpu_seconds": final_hard,
            "elapsed_seconds": elapsed, "elapsed_upper_seconds": elapsed + 5,
            "observed_job_peak_rss_bytes": result["sampled_job_rss_high"],
            "unknown_active_work": not result["reaped"] or bool(result.get("survivors_at_terminal_scan"))
                                   or bool(result["errors"]) or bool(result.get("stop_reason"))
                                   or result.get("exit_code") != 0,
            "supervisor_exit_tail_measured": False}
