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


if __name__ == "__main__":
    unittest.main()
