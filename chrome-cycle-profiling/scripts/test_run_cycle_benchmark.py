#!/usr/bin/env python3

import importlib.util
import pathlib
import subprocess
import sys
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("run_cycle_benchmark.py")
SPEC = importlib.util.spec_from_file_location("run_cycle_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RunCycleBenchmarkTest(unittest.TestCase):
    def test_quality_rejection_is_returned_without_raising(self):
        completed = subprocess.CompletedProcess(["analyzer"], 3)
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed):
            self.assertEqual(3, MODULE.run_analyzer(["analyzer"], "/tmp"))

    def test_unexpected_analyzer_failure_raises(self):
        completed = subprocess.CompletedProcess(["analyzer"], 2)
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed):
            with self.assertRaises(subprocess.CalledProcessError):
                MODULE.run_analyzer(["analyzer"], "/tmp")

    def test_process_polling_is_not_high_frequency(self):
        self.assertGreaterEqual(MODULE.PROCESS_POLL_INTERVAL_SECONDS, 0.25)

    def test_snapshot_chrome_processes_space_and_null_delimited(self):
        stat_perf = "100 (perf) S 1 100 100 0 -1 4194304 0 0 0 0 0 0 0 0 20 0 1 0"
        stat_browser = "200 (chrome) S 100 100 100 0 -1 4194304 0 0 0 0 0 0 0 0 20 0 1 0"
        stat_renderer = "300 (chrome) S 200 100 100 0 -1 4194304 0 0 0 0 0 0 0 0 20 0 1 0"

        entry1 = mock.Mock()
        entry1.name = "100"
        entry2 = mock.Mock()
        entry2.name = "200"
        entry3 = mock.Mock()
        entry3.name = "300"
        scandir_mock = [entry1, entry2, entry3]

        def fake_open(path, mode="r"):
            if path == "/proc/100/stat":
                return mock.mock_open(read_data=stat_perf)()
            elif path == "/proc/100/cmdline":
                return mock.mock_open(read_data=b"perf\0record\0")()
            elif path == "/proc/200/stat":
                return mock.mock_open(read_data=stat_browser)()
            elif path == "/proc/200/cmdline":
                # Space-delimited cmdline as seen when process title is modified
                return mock.mock_open(
                    read_data=b"/home/user/chrome --enable-features=X --headless\0"
                )()
            elif path == "/proc/300/stat":
                return mock.mock_open(read_data=stat_renderer)()
            elif path == "/proc/300/cmdline":
                # Space-delimited cmdline for renderer
                return mock.mock_open(
                    read_data=b"/home/user/chrome --type=renderer --js-flags=--perf-basic-prof\0"
                )()
            raise FileNotFoundError(path)

        with mock.patch("os.scandir", return_value=scandir_mock), mock.patch(
            "builtins.open", side_effect=fake_open
        ):
            procs = MODULE.snapshot_chrome_processes(100, "chrome")
            self.assertEqual(2, len(procs))
            self.assertIn(200, procs)
            self.assertEqual("browser", procs[200]["role"])
            self.assertIn(300, procs)
            self.assertEqual("renderer", procs[300]["role"])


if __name__ == "__main__":
    unittest.main()
