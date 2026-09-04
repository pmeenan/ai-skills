#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import tune_benchmark_host


class TuneBenchmarkHostTest(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = os.path.join(self.temp_dir.name, "tuning_state.json")
        self.real_exists = os.path.exists

    def tearDown(self):
        self.temp_dir.cleanup()

    def mock_exists_side_effect(self, path):
        if path == self.state_file:
            return self.real_exists(path)
        return path.startswith("/sys") or path.startswith("/proc")

    @mock.patch("tune_benchmark_host.get_current_state")
    @mock.patch("tune_benchmark_host.write_sys_file")
    @mock.patch("tune_benchmark_host.set_governor")
    @mock.patch("tune_benchmark_host.set_epp")
    def test_enable_tuning_saves_state_and_applies(
        self, mock_set_epp, mock_set_gov, mock_write, mock_get_state
    ):
        mock_get_state.return_value = {
            "governor": "powersave",
            "epp": "balance_performance",
            "no_turbo": "0",
            "smt": "on",
            "aslr": "2",
            "nmi_watchdog": "1",
        }

        with mock.patch("os.path.exists", side_effect=self.mock_exists_side_effect):
            tune_benchmark_host.enable_tuning(state_file=self.state_file, disable_smt=True)

        # Verify state file was created and contains the original state
        self.assertTrue(self.real_exists(self.state_file))
        with open(self.state_file) as f:
            saved = json.load(f)
        self.assertEqual(saved["governor"], "powersave")
        self.assertEqual(saved["no_turbo"], "0")
        self.assertEqual(saved["smt"], "on")

        # Verify performance settings were applied
        mock_set_gov.assert_called_with("performance")
        mock_set_epp.assert_called_with("performance")
        mock_write.assert_any_call(tune_benchmark_host.SYS_NO_TURBO, "1")
        mock_write.assert_any_call(tune_benchmark_host.PROC_ASLR, "0")
        mock_write.assert_any_call(tune_benchmark_host.PROC_NMI, "0")
        mock_write.assert_any_call(tune_benchmark_host.SYS_SMT, "off")

    @mock.patch("tune_benchmark_host.write_sys_file")
    @mock.patch("tune_benchmark_host.set_governor")
    @mock.patch("tune_benchmark_host.set_epp")
    def test_disable_tuning_restores_from_file(
        self, mock_set_epp, mock_set_gov, mock_write
    ):
        # Pre-populate state file
        original_state = {
            "governor": "powersave",
            "epp": "balance_performance",
            "no_turbo": "0",
            "smt": "on",
            "aslr": "2",
            "nmi_watchdog": "1",
        }
        with open(self.state_file, "w") as f:
            json.dump(original_state, f)

        with mock.patch("os.path.exists", side_effect=self.mock_exists_side_effect):
            tune_benchmark_host.disable_tuning(state_file=self.state_file)

        # Verify original settings were restored
        mock_write.assert_any_call(tune_benchmark_host.SYS_SMT, "on")
        mock_set_gov.assert_called_with("powersave")
        mock_set_epp.assert_called_with("balance_performance")
        mock_write.assert_any_call(tune_benchmark_host.SYS_NO_TURBO, "0")
        mock_write.assert_any_call(tune_benchmark_host.PROC_ASLR, "2")
        mock_write.assert_any_call(tune_benchmark_host.PROC_NMI, "1")

        # Verify state file was removed
        self.assertFalse(self.real_exists(self.state_file))

    @mock.patch("tune_benchmark_host.enable_tuning")
    @mock.patch("tune_benchmark_host.disable_tuning")
    def test_run_context_manager_always_restores(
        self, mock_disable, mock_enable
    ):
        with mock.patch("subprocess.run", side_effect=RuntimeError("Benchmark crashed")):
            with self.assertRaises(RuntimeError):
                try:
                    tune_benchmark_host.enable_tuning(state_file=self.state_file)
                    subprocess.run(["false"], check=True)
                finally:
                    tune_benchmark_host.disable_tuning(state_file=self.state_file)

        mock_enable.assert_called_once_with(state_file=self.state_file)
        mock_disable.assert_called_once_with(state_file=self.state_file)

    @mock.patch("tune_benchmark_host.is_root", return_value=False)
    @mock.patch("subprocess.run")
    def test_can_tune_host_with_sudo(self, mock_subproc, mock_root):
        mock_subproc.return_value = mock.Mock(returncode=0)
        self.assertTrue(tune_benchmark_host.can_tune_host())

        mock_subproc.return_value = mock.Mock(returncode=1)
        self.assertFalse(tune_benchmark_host.can_tune_host())

    @mock.patch("tune_benchmark_host.can_tune_host", return_value=True)
    @mock.patch("tune_benchmark_host.enable_tuning")
    @mock.patch("tune_benchmark_host.disable_tuning")
    def test_tuned_host_context_lifecycle(self, mock_disable, mock_enable, mock_can):
        with tune_benchmark_host.tuned_host_context(state_file=self.state_file) as active:
            self.assertTrue(active)
            mock_enable.assert_called_once_with(state_file=self.state_file, disable_smt=True)
            mock_disable.assert_not_called()

        mock_disable.assert_called_once_with(state_file=self.state_file)

    @mock.patch("tune_benchmark_host.can_tune_host", return_value=False)
    @mock.patch("tune_benchmark_host.enable_tuning")
    @mock.patch("tune_benchmark_host.disable_tuning")
    def test_tuned_host_context_noop_when_no_privileges(
        self, mock_disable, mock_enable, mock_can
    ):
        with tune_benchmark_host.tuned_host_context(state_file=self.state_file) as active:
            self.assertFalse(active)
            mock_enable.assert_not_called()

        mock_disable.assert_not_called()


if __name__ == "__main__":
    unittest.main()
