"""Pure tests only: no child, native library, data/model or subprocess launch."""
import ctypes
import importlib.util
import math
import os
from pathlib import Path
import resource
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("toy_processes_v6", "/tmp/tlab-heldout-harness-processes-v6.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
raw_source = Path(spec.origin).read_bytes()
import hashlib
assert hashlib.sha256(raw_source).hexdigest() == '449d98755ce6ea32e34bad7def7838a3f1d5ccabcbc666fb05dddc5e8c6ac232'
exec(compile(raw_source, spec.origin, 'exec', dont_inherit=True), m.__dict__)


def proc(pid, parent=0, start=1, group=None, uid=501):
    return m.Process(m.Identity(pid, (start,)), parent, group or pid, uid, False)


def ru(cpu=0):
    return SimpleNamespace(ru_utime=cpu, ru_stime=0., ru_maxrss=0)


class PureProcessTests(unittest.TestCase):
    def test_import_has_no_owned_child_registry_entries(self):
        self.assertEqual(m._UNREAPED, {})

    def test_local_darwin_abi_layout(self):
        self.assertEqual(ctypes.sizeof(m.BSDInfo), 136)
        self.assertEqual(m.BSDInfo.start_sec.offset, 120)
        self.assertEqual(ctypes.sizeof(m.RUsageV1), 144)
        self.assertEqual(m.RUsageV1.child_user.offset, 96)

    def test_mach_non_unit_timebase(self):
        self.assertEqual(m.ticks_seconds(24_000_000, 125, 3), 1.0)
        self.assertEqual(m.ticks_seconds(1_000_000_000, 1, 1), 1.0)

    def test_invalid_mach_timebase(self):
        for args in [(1, 0, 1), (1, 1, 0), (-1, 1, 1), (True, 1, 1)]:
            with self.assertRaises(ValueError):
                m.ticks_seconds(*args)

    def linux_stat(self, *, rss="7", comm="spaces ) and (brackets"):
        # fields3..24, deliberately independent literals.
        values = ["S", "5", "6", "6", "0", "0", "0", "0", "0", "0", "0",
                  "200", "300", "400", "500", "20", "0", "2", "0", "12345", "90000", rss]
        return "99 (" + comm + ") " + " ".join(values)

    def test_linux_stat_awkward_comm_and_units(self):
        value = m.parse_linux_stat(self.linux_stat(), uid=501, clock_ticks=100, page_size=4096)
        self.assertEqual(value.process.identity, m.Identity(99, (12345,)))
        self.assertEqual((value.process.ppid, value.process.pgid), (5, 6))
        self.assertEqual((value.self_cpu, value.waited_cpu, value.rss_bytes), (5, 9, 28672))

    def test_linux_stat_invalid_counter_and_truncation(self):
        for data in (self.linux_stat(rss="-1"), "99 (x) S 1", "not stat"):
            with self.assertRaises(m.ObservationError):
                m.parse_linux_stat(data, uid=501, clock_ticks=100, page_size=4096)

    def test_tree_includes_new_session_and_orphan_known(self):
        root, worker, orphan = proc(10), proc(11, 10, group=11), proc(12, 1, group=12)
        result = m.select_tree(root.identity, {10: root, 11: worker, 12: orphan}, {orphan.identity})
        self.assertEqual(set(result), {10, 11, 12})

    def test_tree_rejects_recycled_root_and_does_not_follow_it(self):
        result = m.select_tree(m.Identity(10, (1,)), {10: proc(10, start=2), 11: proc(11, 10)}, set())
        self.assertEqual(result, {})

    def test_tree_rejects_unexpected_descendant_uid(self):
        root = proc(10)
        with self.assertRaises(m.ObservationError):
            m.select_tree(root.identity, {10: root, 11: proc(11, 10, uid=0)}, set())

    def test_cpu_sums_current_self_and_waited_without_prior_maxima(self):
        root, worker = proc(10), proc(11, 10)
        before = [m.Usage(root, 1., 3., 100), m.Usage(worker, 2., 0., 200)]
        after = [m.Usage(root, 1.1, 5., 105)]
        self.assertEqual(m.live_totals(before), (6., 300))
        self.assertEqual(m.live_totals(after), (6.1, 105))

    def test_cpu_duplicate_and_nonfinite_fail(self):
        value = m.Usage(proc(10), 1., 0., 10)
        for values in ([value, value], [m.Usage(proc(10), math.inf, 0., 10)]):
            with self.assertRaises(m.ObservationError):
                m.live_totals(values)

    def test_supervisor_rejects_prior_reaped_cpu(self):
        with patch.object(m.resource, "getrusage", return_value=ru(.01)):
            with self.assertRaises(m.ObservationError):
                m.assert_fresh_supervisor()

    def test_signal_revalidates_recycled_identity_and_skips_own(self):
        root = proc(10)
        obs = SimpleNamespace(observe=lambda identity: None)
        with patch.object(m.os, "kill") as kill:
            self.assertEqual(m.signal_observed(obs, {10: root}, 9), [])
            kill.assert_not_called()

    def test_wait4_terminal_accounting_does_not_add_role_cpu_twice(self):
        own_pid = os.getpid()
        own, root, worker = proc(own_pid), proc(10, own_pid), proc(11, 10)
        inventories = iter([{own_pid: own, 10: root}, {own_pid: own, 10: root, 11: worker}, {own_pid: own}])
        usages = {own.identity: m.Usage(own, 1, 0, 10), root.identity: m.Usage(root, .5, 0, 20),
                  worker.identity: m.Usage(worker, 2, 0, 30)}
        observer = SimpleNamespace(inventory=lambda: next(inventories), observe=usages.get)
        with patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.os, "wait4", return_value=(10, 0, ru(3))) as wait:
            result = m.supervise_direct_child(10, 0., observer=observer)
        self.assertEqual(result["actual_cpu"], 4)
        self.assertEqual(result["sampled_job_rss_high"], 60)
        self.assertEqual(result["status"], "normal_reaped_pending_worker_ledger")
        self.assertFalse(result["worker_ledger_verified"])
        wait.assert_called_once_with(10, os.WNOHANG)

    def test_wait4_lost_reaper_fails(self):
        own_pid = os.getpid()
        own, root = proc(own_pid), proc(10, own_pid)
        inventory = {own_pid: own, 10: root}
        observer = SimpleNamespace(inventory=lambda: inventory,
                                   observe=lambda identity: m.Usage(inventory[identity.pid], 0, 0, 1))
        with patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(0)), \
             patch.object(m.os, "wait4", side_effect=ChildProcessError):
            with self.assertRaises(m.ObservationError):
                m.supervise_direct_child(10, 0., observer=observer)

    def test_memory_stop_escalates_after_one_second_not_wall_deadline(self):
        own_pid = os.getpid()
        own, root, worker = proc(own_pid), proc(10, own_pid), proc(11, 10)
        state = {"time": 0., "reaped": False}
        def inventory():
            return {own_pid: own} if state["reaped"] else {own_pid: own, 10: root, 11: worker}
        usages = {own.identity: m.Usage(own, 0, 0, 10), root.identity: m.Usage(root, 0, 0, 10),
                  worker.identity: m.Usage(worker, 0, 0, 200)}
        observer = SimpleNamespace(inventory=inventory, observe=usages.get)
        def wait(*_):
            if state["time"] > 1.1:
                state["reaped"] = True
                return 10, 0, ru(0)
            return 0, 0, None
        def sleep(duration):
            state["time"] += duration
        with patch.object(m.time, "monotonic", side_effect=lambda: state["time"]), \
             patch.object(m.time, "sleep", side_effect=sleep), \
             patch.object(m.resource, "getrusage", return_value=ru(0)), \
             patch.object(m.os, "wait4", side_effect=wait), \
             patch.object(m.os, "kill") as kill:
            result = m.supervise_direct_child(10, 0., observer=observer, rss_limit=100)
        self.assertEqual(result["stop_reason"], "sampled_job_rss")
        self.assertEqual(result["status"], "failed")
        self.assertLess(state["time"], 2)
        self.assertIn(unittest.mock.call(11, m.signal.SIGTERM), kill.call_args_list)
        self.assertIn(unittest.mock.call(10, m.signal.SIGKILL), kill.call_args_list)

    def test_terminal_scan_failure_preserves_reaped_cpu_but_rejects_success(self):
        own_pid = os.getpid()
        own, root, worker = proc(own_pid), proc(10, own_pid), proc(11, 10)
        inventories = iter([{own_pid: own, 10: root}, {own_pid: own, 10: root, 11: worker}])
        def inventory():
            try:
                return next(inventories)
            except StopIteration:
                raise m.ObservationError("synthetic lost scan")
        usages = {p.identity: m.Usage(p, 0, 0, 1) for p in (own, root, worker)}
        observer = SimpleNamespace(inventory=inventory, observe=usages.get)
        with patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.os, "wait4", return_value=(10, 0, ru(3))), \
             patch.object(m.os, "kill"):
            result = m.supervise_direct_child(10, 0., observer=observer)
        self.assertTrue(result["reaped"])
        self.assertEqual(result["actual_cpu"], 4)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["survivors_at_terminal_scan"], [11])

    def test_wrapper_launch_definition_mocked_and_truthful_tail(self):
        fake = SimpleNamespace(pid=123, returncode=None)
        terminal = {"status": "normal_reaped_pending_worker_ledger", "reaped": True,
                    "exit_code": 0, "actual_cpu": 4., "direct_child_inclusive_cpu": 3.,
                    "sampled_job_rss_high": 100, "errors": [], "survivors_at_terminal_scan": []}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "backend", return_value=object()), \
             patch.object(m, "assert_fresh_supervisor"), \
             patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.resource, "getrlimit", return_value=(resource.RLIM_INFINITY, resource.RLIM_INFINITY)), \
             patch.object(m.resource, "setrlimit") as fence, \
             patch.object(m.subprocess, "Popen", return_value=fake) as popen, \
             patch.object(m, "supervise_direct_child", return_value=terminal):
            result = m.supervise(["unexecuted-fixture"], Path(directory) / "log", started=0., cwd=directory)
        self.assertEqual(result["status"], "verified_normal_exit")
        self.assertEqual(result["cpu_upper_seconds"], 6.)
        self.assertIsNone(result["actual_total_cpu_seconds"])
        self.assertFalse(result["supervisor_exit_tail_measured"])
        self.assertEqual(fake.returncode, 0)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        fence.assert_called_once_with(resource.RLIMIT_CPU, (2, 2))
        self.assertEqual(m._UNREAPED, {})

    def test_wrapper_invalid_caps_reject_before_launch(self):
        with patch.object(m.subprocess, "Popen") as popen:
            with self.assertRaises(ValueError):
                m.supervise(["unexecuted"], "/tmp/unused-log", started=0., cpu_seconds=math.nan, cwd="/tmp")
        popen.assert_not_called()

    def test_wrapper_internal_failure_kills_own_child_and_preserves_unknown_cleanup(self):
        fake = SimpleNamespace(pid=123, returncode=None)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "backend", return_value=object()), \
             patch.object(m, "assert_fresh_supervisor"), \
             patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.resource, "getrlimit", return_value=(resource.RLIM_INFINITY, resource.RLIM_INFINITY)), \
             patch.object(m.resource, "setrlimit"), \
             patch.object(m.subprocess, "Popen", return_value=fake), \
             patch.object(m, "supervise_direct_child", side_effect=m.ObservationError("synthetic observer lost")), \
             patch.object(m.os, "kill") as kill, \
             patch.object(m.os, "wait4", return_value=(123, 9, ru(3))):
            result = m.supervise(["unexecuted-fixture"], Path(directory) / "log", started=0., cwd=directory)
        kill.assert_called_once_with(123, m.signal.SIGKILL)
        self.assertEqual(result["status"], "failed_unknown_cleanup")
        self.assertTrue(result["unknown_active_work"])
        self.assertEqual(result["wait4_child_cpu_seconds"], 3.)
        self.assertTrue(result["cleanup_nested_unknown"])
        self.assertEqual(fake.returncode, -9)

    def test_wrapper_reserve_rejects_overspent_before_launch(self):
        with patch.object(m, "backend", return_value=object()), \
             patch.object(m, "assert_fresh_supervisor"), \
             patch.object(m.time, "monotonic", return_value=119.), \
             patch.object(m.resource, "getrusage", return_value=ru(0)), \
             patch.object(m.subprocess, "Popen") as popen:
            with self.assertRaises(m.ObservationError):
                m.supervise(["unexecuted"], "/tmp/unused-log", started=0., cwd="/tmp")
        popen.assert_not_called()

    def interrupted_wrapper(self, exception, *, signal_interrupt=False, after_reap=False):
        fake = SimpleNamespace(pid=123, returncode=None)
        own_pid = os.getpid()
        own, root = proc(own_pid), proc(123, own_pid)
        state = {"inventories": 0}
        def inventory():
            state["inventories"] += 1
            if state["inventories"] == 3:
                raise exception
            return {own_pid: own, 123: root}
        observer = SimpleNamespace(inventory=inventory,
                                   observe=lambda identity: m.Usage(own if identity.pid == own_pid else root, 0, 0, 1))
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "backend", return_value=observer if after_reap else object()), \
             patch.object(m, "assert_fresh_supervisor"), \
             patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.resource, "setrlimit"), \
             patch.object(m.subprocess, "Popen", return_value=fake), \
             patch.object(m.os, "wait4", return_value=(123, 0, ru(3))) as wait, \
             patch.object(m.os, "kill", side_effect=[KeyboardInterrupt("secondary interruption"), None] if signal_interrupt else None) as kill:
            if after_reap:
                try:
                    m.supervise(["unexecuted-fixture"], Path(directory) / "log", started=0., cwd=directory)
                except type(exception) as caught:
                    self.assertIs(caught, exception)
                else:
                    self.fail("primary interruption was not preserved")
            else:
                with patch.object(m, "supervise_direct_child", side_effect=exception):
                    try:
                        m.supervise(["unexecuted-fixture"], Path(directory) / "log", started=0., cwd=directory)
                    except type(exception) as caught:
                        self.assertIs(caught, exception)
                    else:
                        self.fail("primary interruption was not preserved")
        evidence = exception.supervisor_cleanup_evidence
        self.assertTrue(evidence["reaped"])
        self.assertEqual(evidence["direct_child_inclusive_cpu"], 3.)
        self.assertEqual(fake.returncode, 0)
        wait.assert_called_once_with(123, os.WNOHANG)
        self.assertEqual(m._UNREAPED, {})
        return kill.call_args_list, evidence

    def test_system_exit_after_launch_reaps_and_preserves_original(self):
        calls, evidence = self.interrupted_wrapper(SystemExit(17))
        self.assertEqual(calls, [unittest.mock.call(123, m.signal.SIGKILL)])
        self.assertEqual(evidence["primary_exception_type"], "SystemExit")

    def test_keyboard_interrupt_during_terminal_scan_never_signals_or_waits_old_pid(self):
        calls, evidence = self.interrupted_wrapper(KeyboardInterrupt("terminal scan cancelled"), after_reap=True)
        self.assertEqual(calls, [])
        self.assertEqual(evidence["ownership_phase"], "reaped")

    def test_repeated_interrupt_during_cleanup_preserves_primary_and_still_waits(self):
        calls, evidence = self.interrupted_wrapper(KeyboardInterrupt("primary cancellation"), signal_interrupt=True)
        self.assertEqual(len(calls), 2)
        self.assertTrue(any("secondary interruption" in item for item in evidence["errors"]))

    def test_interrupt_during_uncertain_wait_requires_original_identity_before_signal(self):
        ownership = m.ChildOwnership(123, identity=m.Identity(123, (1,)))
        with patch.object(m.os, "wait4", side_effect=KeyboardInterrupt("wait syscall uncertain")):
            with self.assertRaises(KeyboardInterrupt):
                ownership.wait()
        observer = SimpleNamespace(observe=lambda identity: m.Usage(proc(123, 1, start=2), 0, 0, 1))
        self.assertFalse(m._may_signal_direct(ownership, observer))
        self.assertEqual(ownership.phase, "wait_uncertain")

    def test_uncertain_wait_with_recycled_identity_never_waits_or_kills_again(self):
        ownership = m.ChildOwnership(123, identity=m.Identity(123, (1,)), phase="wait_uncertain")
        observer = SimpleNamespace(observe=lambda identity: m.Usage(proc(123, 1, start=2), 0, 0, 1))
        with patch.object(m.os, "kill") as kill, patch.object(m.os, "wait4") as wait, \
             patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)):
            result = m._failure_cleanup(ownership, observer, started=0., wall_seconds=120,
                                        primary=KeyboardInterrupt("uncertain wait cancelled"))
        kill.assert_not_called()
        wait.assert_not_called()
        self.assertEqual(result["ownership_phase"], "lost")
        self.assertFalse(result["reaped"])

    def test_ownership_constructor_interrupt_occurs_before_any_Popen(self):
        primary = KeyboardInterrupt("preallocated ownership interrupted")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "backend", return_value=object()), \
             patch.object(m, "assert_fresh_supervisor"), \
             patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m, "ChildOwnership", side_effect=primary), \
             patch.object(m.subprocess, "Popen") as popen, \
             patch.object(m.os, "wait4") as wait, patch.object(m.os, "kill") as kill:
            with self.assertRaises(KeyboardInterrupt) as caught:
                m.supervise(["unexecuted"], Path(directory) / "log", started=0., cwd=directory)
        self.assertIs(caught.exception, primary)
        popen.assert_not_called()
        wait.assert_not_called()
        kill.assert_not_called()

    def registry_interrupted(self, primary):
        class BrokenRegistry(dict):
            def __setitem__(self, key, value):
                raise primary
        registry = BrokenRegistry()
        fake = SimpleNamespace(pid=123, returncode=None)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "backend", return_value=object()), \
             patch.object(m, "assert_fresh_supervisor"), \
             patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.resource, "setrlimit") as fence, \
             patch.object(m, "_UNREAPED", registry), \
             patch.object(m.subprocess, "Popen", return_value=fake), \
             patch.object(m, "supervise_direct_child") as core, \
             patch.object(m.os, "wait4", return_value=(123, 0, ru(3))) as wait, \
             patch.object(m.os, "kill") as kill:
            with self.assertRaises(type(primary)) as caught:
                m.supervise(["unexecuted"], Path(directory) / "log", started=0., cwd=directory)
        self.assertIs(caught.exception, primary)
        kill.assert_called_once_with(123, m.signal.SIGKILL)
        wait.assert_called_once_with(123, os.WNOHANG)
        core.assert_not_called()
        fence.assert_not_called()
        self.assertEqual(fake.returncode, 0)
        self.assertEqual(registry, {})
        self.assertTrue(primary.supervisor_cleanup_evidence["reaped"])
        self.assertEqual(primary.supervisor_cleanup_evidence["direct_child_inclusive_cpu"], 3.)

    def test_postlaunch_registry_KeyboardInterrupt_cleans_and_preserves_primary(self):
        self.registry_interrupted(KeyboardInterrupt("postlaunch registry interrupted"))

    def test_postlaunch_registry_SystemExit_cleans_and_preserves_primary(self):
        self.registry_interrupted(SystemExit(17))

    def test_late_terminal_report_interrupt_retains_reaped_facts_without_old_PID_actions(self):
        primary = KeyboardInterrupt("terminal report interrupted")
        fake = SimpleNamespace(pid=123, returncode=None)
        terminal = {"reaped": True, "exit_code": 0, "direct_child_inclusive_cpu": 3.,
                    "sampled_job_rss_high": 100}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "backend", return_value=object()), \
             patch.object(m, "assert_fresh_supervisor"), \
             patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.resource, "setrlimit"), \
             patch.object(m.subprocess, "Popen", return_value=fake), \
             patch.object(m, "supervise_direct_child", return_value=terminal), \
             patch.object(m, "_terminal_report", side_effect=primary), \
             patch.object(m.os, "wait4") as wait, patch.object(m.os, "kill") as kill:
            with self.assertRaises(KeyboardInterrupt) as caught:
                m.supervise(["unexecuted"], Path(directory) / "log", started=0., cwd=directory)
        self.assertIs(caught.exception, primary)
        wait.assert_not_called()
        kill.assert_not_called()
        self.assertEqual(fake.returncode, 0)
        self.assertEqual(m._UNREAPED, {})
        self.assertEqual(primary.supervisor_cleanup_evidence["direct_child_inclusive_cpu"], 3.)

    def darwin_owned_family(self, records, children, known=()):
        observer = m.Darwin.__new__(m.Darwin)
        observer.root_pid = 10
        observer.root_uid = 501
        observer.root_identity = None
        observer.known_owned = set(known)
        reads, calls = [], []
        def process(pid):
            reads.append(pid)
            value = records.get(pid)
            if isinstance(value, BaseException):
                raise value
            return value
        def fill(ppid, buffer, size):
            calls.append((ppid, size))
            values = children.get(ppid, [])
            if buffer is None:
                return len(values)
            for index, pid in enumerate(values):
                buffer[index] = pid
            return len(values)
        observer.process = process
        observer.lib = SimpleNamespace(proc_listchildpids=fill)
        return observer, reads, calls

    def test_Darwin_owned_family_count_bytes_and_unrelated_sibling_not_read(self):
        root, child, grandchild = proc(10, 1, start=1), proc(11, 10, start=2), proc(12, 11, start=3)
        observer, reads, calls = self.darwin_owned_family(
            {10: root, 11: child, 12: grandchild, 99: m.ObservationError("unrelated EPERM")},
            {10: [11], 11: [12]})
        result = observer.inventory()
        self.assertEqual(set(result), {10, 11, 12})
        self.assertNotIn(99, reads)
        self.assertEqual(calls, [(10, 0), (10, 17 * ctypes.sizeof(ctypes.c_int)),
                                 (11, 0), (11, 17 * ctypes.sizeof(ctypes.c_int)), (12, 0)])
        self.assertEqual(observer.known_owned, {root.identity, child.identity, grandchild.identity})

    def test_Darwin_child_empty_zero_errno_is_valid_and_stale_errno_cleared(self):
        observer, _, _ = self.darwin_owned_family({10: proc(10)}, {})
        ctypes.set_errno(m.errno.EPERM)
        self.assertEqual(observer.child_pids(10), [])

    def test_Darwin_child_count_zero_EPERM_fails(self):
        observer, _, _ = self.darwin_owned_family({10: proc(10)}, {})
        def denied(*_):
            ctypes.set_errno(m.errno.EPERM)
            return 0
        observer.lib.proc_listchildpids = denied
        with self.assertRaisesRegex(m.ObservationError, "count errno=1"):
            observer.child_pids(10)

    def test_Darwin_child_fill_zero_EPERM_fails(self):
        observer, _, _ = self.darwin_owned_family({10: proc(10)}, {})
        def denied(ppid, buffer, size):
            if buffer is None:
                return 1
            ctypes.set_errno(m.errno.EPERM)
            return 0
        observer.lib.proc_listchildpids = denied
        with self.assertRaisesRegex(m.ObservationError, "fill errno=1"):
            observer.child_pids(10)

    def test_Darwin_child_full_buffer_retries_with_count_not_byte_capacity(self):
        observer, _, _ = self.darwin_owned_family({10: proc(10)}, {})
        calls = []
        def growing(ppid, buffer, size):
            calls.append(size)
            if buffer is None:
                return 1
            if len(calls) == 2:
                return size // ctypes.sizeof(ctypes.c_int)
            buffer[0] = 11
            return 1
        observer.lib.proc_listchildpids = growing
        self.assertEqual(observer.child_pids(10), [11])
        self.assertEqual(calls, [0, 68, 132])

    def test_Darwin_child_persistent_full_buffer_stops_after_four_fills(self):
        observer, _, _ = self.darwin_owned_family({10: proc(10)}, {})
        calls = []
        def always_full(ppid, buffer, size):
            calls.append(size)
            return 1 if buffer is None else size // ctypes.sizeof(ctypes.c_int)
        observer.lib.proc_listchildpids = always_full
        with self.assertRaisesRegex(m.ObservationError, "repeatedly filled"):
            observer.child_pids(10)
        self.assertEqual(len(calls), 5)

    def test_Darwin_enumerated_owned_metadata_EPERM_is_never_skipped(self):
        observer, _, _ = self.darwin_owned_family(
            {10: proc(10), 11: m.ObservationError("proc_pidinfo owned EPERM")}, {10: [11]})
        with self.assertRaisesRegex(m.ObservationError, "owned EPERM"):
            observer.inventory()

    def test_Darwin_tracked_owned_metadata_EPERM_is_never_skipped(self):
        old = proc(11, 10, start=2)
        observer, _, _ = self.darwin_owned_family(
            {10: proc(10), 11: m.ObservationError("tracked original EPERM")}, {}, [old.identity])
        with self.assertRaisesRegex(m.ObservationError, "tracked original EPERM"):
            observer.inventory()

    def test_Darwin_tracked_reparented_original_keeps_its_descendants(self):
        root, orphan, descendant = proc(10, 1, start=1), proc(11, 1, start=2), proc(12, 11, start=3)
        observer, _, calls = self.darwin_owned_family(
            {10: root, 11: orphan, 12: descendant}, {11: [12]}, [orphan.identity])
        result = observer.inventory()
        self.assertEqual(set(result), {10, 11, 12})
        self.assertEqual(result[11].ppid, 1)
        self.assertIn((11, 0), calls)

    def test_Darwin_recycled_tracked_identity_does_not_adopt_unrelated_sibling_family(self):
        old, recycled = proc(11, 10, start=2), proc(11, 99, start=20)
        observer, reads, calls = self.darwin_owned_family(
            {10: proc(10, start=1), 11: recycled, 12: m.ObservationError("unrelated descendant EPERM")},
            {11: [12]}, [old.identity])
        self.assertEqual(set(observer.inventory()), {10})
        self.assertNotIn(12, reads)
        self.assertNotIn((11, 0), calls)

    def test_Darwin_enumerated_child_requires_actual_parent_UID_and_birth_order(self):
        for child in (proc(11, 99, start=2), proc(11, 10, start=2, uid=0), proc(11, 10, start=0)):
            with self.subTest(child=child):
                observer, _, _ = self.darwin_owned_family({10: proc(10, start=1), 11: child}, {10: [11]})
                with self.assertRaises(m.ObservationError):
                    observer.inventory()

    def test_Darwin_parent_birth_change_across_child_enumeration_fails(self):
        records = {10: proc(10, start=1), 11: proc(11, 10, start=2), 12: proc(12, 11, start=3)}
        observer, _, _ = self.darwin_owned_family(records, {10: [11], 11: [12]})
        original = observer.lib.proc_listchildpids
        def changed(ppid, buffer, size):
            result = original(ppid, buffer, size)
            if ppid == 11 and buffer is not None:
                records[11] = proc(11, 99, start=20)
            return result
        observer.lib.proc_listchildpids = changed
        with self.assertRaisesRegex(m.ObservationError, "parent identity/UID changed"):
            observer.inventory()

    def test_initial_worker_reparented_before_first_loop_remains_owned(self):
        own_pid = os.getpid()
        own, root, worker = proc(own_pid), proc(10, own_pid), proc(11, 10)
        orphan = proc(11, 1)
        inventories = iter([{own_pid: own, 10: root, 11: worker},
                            {own_pid: own, 10: root, 11: orphan}, {own_pid: own, 11: orphan}])
        values = {own.identity: m.Usage(own, 0, 0, 10), root.identity: m.Usage(root, 0, 0, 20),
                  orphan.identity: m.Usage(orphan, 0, 0, 30)}
        observer = SimpleNamespace(inventory=lambda: next(inventories), observe=values.get)
        with patch.object(m.time, "monotonic", return_value=1.), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.os, "wait4", return_value=(10, 0, ru(3))), patch.object(m.os, "kill") as kill:
            result = m.supervise_direct_child(10, 0., observer=observer)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["observed_process_count"], 2)
        self.assertEqual(result["sampled_job_rss_high"], 60)
        self.assertEqual(result["survivors_at_terminal_scan"], [11])
        kill.assert_called_once_with(11, m.signal.SIGKILL)

    def test_first_inventory_reparenting_preserves_authenticated_job_lineage(self):
        own_pid = os.getpid()
        own, root, worker = proc(own_pid, 1, start=1), proc(10, own_pid, start=2), proc(11, 10, start=3)
        orphan = proc(11, 1, start=3)
        records = {own_pid: own, 10: root, 11: worker}
        children = {own_pid: [10], 10: [11]}
        observer, _, _ = self.darwin_owned_family(records, children)
        observer.root_pid = own_pid
        original = observer.process
        reads = {"worker": 0}
        def current(pid):
            if pid == 11:
                reads["worker"] += 1
                if reads["worker"] == 2:
                    records[11] = orphan
                    records[10] = m.Process(root.identity, own_pid, 10, 501, True)
                    children[10] = []
            return original(pid)
        observer.process = current
        def usage(identity):
            value = records.get(identity.pid)
            return m.Usage(value, 0, 0, 30 if identity.pid == 11 else 10) if value is not None and value.identity == identity else None
        observer.observe = usage
        def reap(*_):
            records.pop(10, None)
            children[own_pid] = []
            return 10, 0, ru(3)
        with patch.object(m.time, "monotonic", return_value=1.), patch.object(m.time, "sleep"), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.os, "wait4", side_effect=reap), patch.object(m.os, "kill") as kill:
            result = m.supervise_direct_child(10, 0., observer=observer)
        self.assertIn((root.identity, worker.identity), observer.authenticated_edges)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["sampled_job_rss_high"], 50)
        self.assertEqual(result["observed_process_count"], 2)
        self.assertEqual(result["survivors_at_terminal_scan"], [11])
        kill.assert_called_once_with(11, m.signal.SIGKILL)

    def test_supervisor_sibling_lineage_is_excluded_from_declared_job(self):
        own_pid = os.getpid()
        own, root = proc(own_pid, 1, start=1), proc(10, own_pid, start=2)
        sibling, sibling_child = proc(20, own_pid, start=3), proc(21, 20, start=4)
        records = {own_pid: own, 10: root, 20: sibling, 21: sibling_child}
        children = {own_pid: [10, 20], 20: [21]}
        observer, _, _ = self.darwin_owned_family(records, children)
        observer.root_pid = own_pid
        original = observer.inventory
        calls = {"inventory": 0}
        def inventory():
            value = original()
            calls["inventory"] += 1
            if calls["inventory"] == 1:
                records[20] = proc(20, 1, start=3)
                records[21] = proc(21, 1, start=4)
                children[own_pid] = [10]
                children[20] = []
            return value
        observer.inventory = inventory
        usage_pids = []
        def usage(identity):
            usage_pids.append(identity.pid)
            value = records.get(identity.pid)
            return m.Usage(value, 0, 0, 10) if value is not None and value.identity == identity else None
        observer.observe = usage
        def reap(*_):
            records.pop(10, None)
            children[own_pid] = []
            return 10, 0, ru(3)
        with patch.object(m.time, "monotonic", return_value=1.), patch.object(m.time, "sleep"), \
             patch.object(m.resource, "getrusage", return_value=ru(1)), \
             patch.object(m.os, "wait4", side_effect=reap), patch.object(m.os, "kill") as kill:
            result = m.supervise_direct_child(10, 0., observer=observer)
        self.assertTrue({sibling.identity, sibling_child.identity} <= observer.known_owned)
        self.assertEqual(observer.authenticated_descendants(root.identity), frozenset())
        self.assertEqual(result["status"], "normal_reaped_pending_worker_ledger")
        self.assertEqual(result["sampled_job_rss_high"], 20)
        self.assertEqual(result["survivors_at_terminal_scan"], [])
        self.assertNotIn(20, usage_pids)
        self.assertNotIn(21, usage_pids)
        kill.assert_not_called()

    def lineage_fixture(self):
        supervisor, root, worker, grandchild = (proc(10, 1, start=1), proc(11, 10, start=2),
                                               proc(12, 11, start=3), proc(13, 12, start=4))
        records = {10: supervisor, 11: root, 12: worker, 13: grandchild}
        children = {10: [11], 11: [12], 12: [13]}
        observer, _, _ = self.darwin_owned_family(records, children)
        observer.inventory()
        self.assertEqual(observer.authenticated_descendants(root.identity), frozenset({worker.identity, grandchild.identity}))
        records.pop(11)
        records[12] = proc(12, 1, start=3)
        records[13] = proc(13, 1, start=4)
        children.clear()
        return observer, records, children, root, worker, grandchild

    def test_historical_transitive_lineage_keeps_original_orphans_after_root_exit(self):
        observer, records, children, root, worker, grandchild = self.lineage_fixture()
        current = observer.inventory()
        selected = m._select_job_tree(observer, root.identity, current, {root.identity})
        self.assertEqual(set(selected), {12, 13})
        self.assertEqual({p.identity for p in selected.values()}, {worker.identity, grandchild.identity})

    def test_recycled_declared_root_does_not_inherit_old_lineage_or_new_family(self):
        observer, records, children, root, worker, grandchild = self.lineage_fixture()
        new_root, unrelated = proc(11, 10, start=99), proc(14, 11, start=100)
        records[11], records[14] = new_root, unrelated
        children.update({10: [11], 11: [14]})
        current = observer.inventory()
        self.assertIn((new_root.identity, unrelated.identity), observer.authenticated_edges)
        selected = m._select_job_tree(observer, root.identity, current, {root.identity})
        self.assertEqual(set(selected), {12, 13})
        self.assertNotIn(new_root.identity, observer.authenticated_descendants(root.identity))
        self.assertNotIn(unrelated.identity, observer.authenticated_descendants(root.identity))

    def test_recycled_intermediate_excludes_new_family_but_keeps_original_grandchild(self):
        observer, records, children, root, worker, grandchild = self.lineage_fixture()
        new_worker, unrelated = proc(12, 10, start=99), proc(14, 12, start=100)
        records[12], records[14] = new_worker, unrelated
        children.update({10: [12], 12: [14]})
        current = observer.inventory()
        selected = m._select_job_tree(observer, root.identity, current, {root.identity})
        self.assertEqual(set(selected), {13})
        self.assertEqual(selected[13].identity, grandchild.identity)
        self.assertIn(worker.identity, observer.authenticated_descendants(root.identity))
        self.assertNotIn(unrelated.identity, observer.authenticated_descendants(root.identity))

    def test_recycled_grandchild_endpoint_is_excluded(self):
        observer, records, children, root, worker, grandchild = self.lineage_fixture()
        records[13] = proc(13, 1, start=99)
        current = observer.inventory()
        selected = m._select_job_tree(observer, root.identity, current, {root.identity})
        self.assertEqual(set(selected), {12})
        self.assertEqual(selected[12].identity, worker.identity)

    def test_broken_exact_intermediate_birth_edge_is_not_recovered_by_numeric_PID(self):
        observer, records, children, root, worker, grandchild = self.lineage_fixture()
        observer.authenticated_edges.remove((worker.identity, grandchild.identity))
        observer.authenticated_edges.add((m.Identity(worker.identity.pid, (99,)), grandchild.identity))
        current = observer.inventory()
        selected = m._select_job_tree(observer, root.identity, current, {root.identity})
        self.assertEqual(set(selected), {12})

    def test_Linux_and_generic_observers_do_not_adopt_backend_known_owned_union(self):
        root, orphan, sibling = proc(10, start=1), proc(11, 1, start=2), proc(12, 1, start=3)
        current = {10: root, 11: orphan, 12: sibling}
        linux = m.Linux.__new__(m.Linux)
        linux.known_owned = {orphan.identity, sibling.identity}
        linux.authenticated_edges = {(root.identity, orphan.identity)}
        generic = SimpleNamespace(known_owned=linux.known_owned,
                                  authenticated_descendants=lambda _: self.fail("generic lineage was trusted"))
        for observer in (linux, generic):
            with self.subTest(observer=type(observer).__name__):
                self.assertEqual(set(m._select_job_tree(observer, root.identity, current, {root.identity})), {10})

    def child_metadata_parent_change(self, replacement):
        supervisor, root, worker, grandchild = (proc(10, 1, start=1), proc(11, 10, start=2),
                                               proc(12, 11, start=3), proc(13, 12, start=4))
        records = {10: supervisor, 11: root, 12: worker, 13: grandchild}
        children = {10: [11], 11: [12], 12: [13]}
        observer, _, _ = self.darwin_owned_family(records, children)
        original = observer.process
        switched = []
        def current(pid):
            if pid == 13 and not switched:
                switched.append(True)
                if replacement is None:
                    records.pop(12, None)
                else:
                    records[12] = replacement
                records[13] = proc(13, 12, start=100)
            return original(pid)
        observer.process = current
        with self.assertRaises(m.ObservationError):
            observer.inventory()
        self.assertEqual(switched, [True])
        self.assertIn((root.identity, worker.identity), observer.authenticated_edges)
        self.assertNotIn((worker.identity, records[13].identity), observer.authenticated_edges)
        self.assertNotIn(records[13].identity, observer.authenticated_descendants(root.identity))
        return observer

    def test_recycled_parent_during_child_metadata_cannot_commit_old_parent_new_child_edge(self):
        self.child_metadata_parent_change(proc(12, 10, start=99))

    def test_parent_UID_change_during_child_metadata_cannot_commit_edge(self):
        self.child_metadata_parent_change(proc(12, 11, start=3, uid=0))

    def test_parent_disappearance_during_child_metadata_cannot_commit_edge(self):
        self.child_metadata_parent_change(None)

    def test_owned_parent_EPERM_after_child_metadata_cannot_commit_edge(self):
        self.child_metadata_parent_change(m.ObservationError("parent after child EPERM"))

    def test_parent_recycled_before_child_metadata_is_rejected_before_reading_child(self):
        supervisor, root, worker, grandchild = (proc(10, 1, start=1), proc(11, 10, start=2),
                                               proc(12, 11, start=3), proc(13, 12, start=4))
        records = {10: supervisor, 11: root, 12: worker, 13: grandchild}
        children = {10: [11], 11: [12], 12: [13]}
        observer, reads, _ = self.darwin_owned_family(records, children)
        original = observer.process
        count = {"worker": 0}
        def current(pid):
            if pid == 12:
                count["worker"] += 1
                if count["worker"] == 4:
                    records[12] = proc(12, 10, start=99)
            return original(pid)
        observer.process = current
        with self.assertRaisesRegex(m.ObservationError, "before child metadata"):
            observer.inventory()
        self.assertNotIn(13, reads)
        self.assertNotIn((worker.identity, grandchild.identity), observer.authenticated_edges)


if __name__ == "__main__":
    unittest.main(verbosity=2)
