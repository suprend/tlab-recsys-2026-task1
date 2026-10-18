"""Real, tiny process lifecycle checks; no datasets, models or GPU operations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import hm_job


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hm job кириллица ")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def invoke(self, arguments, timeout=5):
        return subprocess.run([sys.executable, "-m", "scripts.hm_job", "--timeout", str(timeout),
                               "--", *arguments], cwd=hm_job.ROOT, capture_output=True,
                              text=True, encoding="utf-8", timeout=15)

    def test_success_uses_project_cwd_interpreter_and_literal_arguments(self):
        script = self.directory / "проверка аргументов.py"
        script.write_text("import json,os,sys\nprint(json.dumps([os.getcwd(),sys.executable,sys.argv[1:]]))\n",
                          encoding="utf-8", newline="\n")
        result = self.invoke([str(script), "путь с пробелами", "$(not a shell)"])
        self.assertEqual(result.returncode, 0, result.stderr)
        cwd, executable, arguments = json.loads(result.stdout)
        self.assertEqual(Path(cwd), hm_job.ROOT)
        self.assertEqual(Path(executable), Path(sys.executable))
        self.assertEqual(arguments, ["путь с пробелами", "$(not a shell)"])

    def test_nonzero_status_preserved(self):
        self.assertEqual(self.invoke(["-c", "raise SystemExit(7)"]).returncode, 7)

    def descendants(self, exit_code=None):
        marker = self.directory / "grandchild finished.txt"
        ready = self.directory / "grandchild started.txt"
        grandchild = self.directory / "внук процесс.py"
        grandchild.write_text("import pathlib,sys,time\n"
                              "pathlib.Path(sys.argv[1]).write_text('ready')\n"
                              "time.sleep(2)\n"
                              "pathlib.Path(sys.argv[2]).write_text('LEAK')\n",
                              encoding="utf-8", newline="\n")
        child = self.directory / "child launcher.py"
        child.write_text("import pathlib,subprocess,sys,time\n"
                         "subprocess.Popen([sys.executable,sys.argv[1],sys.argv[2],sys.argv[3]])\n"
                         "deadline=time.monotonic()+5\n"
                         "while not pathlib.Path(sys.argv[2]).exists():\n"
                         "    if time.monotonic()>deadline: raise RuntimeError('grandchild did not start')\n"
                         "    time.sleep(.01)\n" +
                         ("time.sleep(20)\n" if exit_code is None else f"raise SystemExit({exit_code})\n"),
                         encoding="utf-8", newline="\n")
        result = self.invoke([str(child), str(grandchild), str(ready), str(marker)],
                             timeout=1 if exit_code is None else 5)
        self.assertTrue(ready.exists(), result.stderr)
        time.sleep(2.2)
        self.assertFalse(marker.exists(), "Grandchild survived owned process cleanup")
        return result

    def test_timeout_kills_grandchild(self):
        result = self.descendants()
        self.assertEqual(result.returncode, 124, result.stderr)

    def test_leader_success_still_kills_grandchild(self):
        self.assertEqual(self.descendants(0).returncode, 0)

    def test_leader_failure_still_kills_grandchild(self):
        self.assertEqual(self.descendants(9).returncode, 9)

    def test_invalid_timeout_does_not_start_worker(self):
        marker = self.directory / "must not exist"
        code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('executed')"
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                self.assertEqual(self.invoke(["-c", code, str(marker)], timeout).returncode, 2)
                self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "nt", "Windows suspended-start ownership")
    def test_job_assignment_failure_prevents_worker_execution(self):
        marker = self.directory / "worker must not run"
        with patch.object(hm_job, "_assign_job", return_value=False):
            with self.assertRaises(OSError):
                hm_job.run(["-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('LEAK')",
                            str(marker)], 5)
        self.assertFalse(marker.exists())

    def test_keyboard_interrupt_cleans_up_child(self):
        original = subprocess.Popen.wait
        interrupted = False

        def wait_once(process, *args, **kwargs):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return original(process, *args, **kwargs)

        marker = self.directory / "interrupted child must not finish"
        code = "import pathlib,sys,time; time.sleep(1); pathlib.Path(sys.argv[1]).write_text('LEAK')"
        with patch.object(subprocess.Popen, "wait", wait_once):
            self.assertEqual(hm_job.run(["-c", code, str(marker)], 5), 130)
        time.sleep(1.2)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
