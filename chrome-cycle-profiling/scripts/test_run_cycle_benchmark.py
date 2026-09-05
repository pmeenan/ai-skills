#!/usr/bin/env python3

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("run_cycle_benchmark.py")
SPEC = importlib.util.spec_from_file_location("run_cycle_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RunCycleBenchmarkTest(unittest.TestCase):
    def test_speedometer_profile_uses_same_payload_as_score_runner(self):
        adapter = MODULE.benchmark_adapters.get_adapter("speedometer3")
        self.assertEqual([
            "speedometer_3.1", "--network=third_party/speedometer/v3.1",
        ], MODULE.profile_benchmark_args(adapter))
        self.assertEqual(
            adapter.crossbench_args(), MODULE.profile_benchmark_args(adapter)
        )

    def test_jetstream_profile_keeps_custom_payload_and_marks(self):
        adapter = MODULE.benchmark_adapters.get_adapter("jetstream3")
        self.assertEqual([
            "jetstream_3.0", "--custom", "--probe=performance.entries",
        ], MODULE.profile_benchmark_args(adapter))

    def test_exact_score_intervals_are_labeled_and_outer_is_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            log_dir = root / "results" / "run"
            log_dir.mkdir(parents=True)
            (log_dir / "browser.stdout.log").write_text(
                "[SP3_SCORE_TIME] sp3-measurement-start: 10.000000000\n"
                "[SP3_SCORE_TIME] TodoMVC-React.Adding100Items-start: 10.100000000\n"
                "[SP3_SCORE_TIME] TodoMVC-React.Adding100Items-sync-end: 10.200000000\n"
                "[SP3_SCORE_TIME] TodoMVC-React.Adding100Items-async-start: 10.300000000\n"
                "[SP3_SCORE_TIME] TodoMVC-React.Adding100Items-async-end: 10.500000000\n"
                "[SP3_SCORE_TIME] sp3-measurement-end: 10.700000000\n"
            )
            intervals, outer = MODULE.parse_mono_intervals("results", tmp)
            self.assertEqual(["sync", "async"], [item["phase"] for item in intervals])
            self.assertTrue(all(
                item["group"].endswith("|TodoMVC-React") for item in intervals
            ))
            self.assertAlmostEqual(0.3, sum(
                item["end_time_mono"] - item["start_time_mono"]
                for item in intervals
            ))
            self.assertAlmostEqual(0.7, outer[0]["end_time_mono"] - outer[0]["start_time_mono"])

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

    def test_jetstream_exact_score_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            log_dir = root / "results" / "cb" / "stories" / "hash-map" / "0" / "0_default"
            log_dir.mkdir(parents=True)
            entries = {
                "mark/hash-map/startTime": [500.0],
                "mark/hash-map/duration": [0],
                "mark/update-ui/startTime": [2500.0],
                "mark/update-ui/duration": [0],
            }
            (log_dir / "performance.entries.json").write_text(json.dumps(entries))
            intervals, outer = MODULE.parse_jetstream_mono_intervals("results", tmp)
            self.assertEqual(1, len(intervals))
            self.assertEqual("hash-map", intervals[0]["suite"])
            self.assertEqual(0.5, intervals[0]["start_time_mono"])
            self.assertEqual(2.5, intervals[0]["end_time_mono"])
            self.assertEqual(2.0, intervals[0]["end_time_mono"] - intervals[0]["start_time_mono"])
            self.assertTrue(intervals[0]["group"].endswith("|hash-map"))


if __name__ == "__main__":
    import json
    unittest.main()
