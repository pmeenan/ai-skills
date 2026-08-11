#!/usr/bin/env python3

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import command_evidence


class CommandEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email", "t@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "T"],
            check=True,
        )
        (self.repo / "engine.cc").write_text("int Work() { return 1; }\n")
        (self.repo / ".gitignore").write_text("/out/\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-qm", "base"], check=True
        )
        (self.repo / "engine.cc").write_text("int Work() { return 2; }\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        self.previous_cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.previous_cwd)
        self.tmp.cleanup()

    def executable(self, name, body="#!/bin/sh\necho real-run\n"):
        path = self.root / name
        path.write_text(body)
        path.chmod(0o755)
        return path

    def make_test_binary(self, name="blink_unittests"):
        path = self.repo / "out" / "perf" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        source = self.root / f"{name}.c"
        source.write_text(
            '#include <stdio.h>\nint main(void) {'
            ' puts("[  PASSED  ] 1 test."); return 0; }\n'
        )
        subprocess.run(["cc", str(source), "-o", str(path)], check=True)
        return path

    def depot_autoninja(self):
        depot = self.root / "depot_tools"
        depot.mkdir()
        subprocess.run(["git", "init", "-q", str(depot)], check=True)
        subprocess.run(
            ["git", "-C", str(depot), "config", "user.email", "t@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(depot), "config", "user.name", "T"], check=True
        )
        subprocess.run(
            ["git", "-C", str(depot), "remote", "add", "origin",
             "https://chromium.googlesource.com/chromium/tools/depot_tools.git"],
            check=True,
        )
        path = depot / "autoninja"
        path.write_text("#!/bin/sh\necho real-build\n")
        path.chmod(0o755)
        subprocess.run(["git", "-C", str(depot), "add", "autoninja"], check=True)
        subprocess.run(["git", "-C", str(depot), "commit", "-qm", "tool"], check=True)
        return path

    def test_runner_emits_tree_bound_passing_receipt(self):
        runner = self.make_test_binary()
        receipt_path = self.root / "test-receipt.json"
        self.assertEqual(0, command_evidence.main([
            "--kind", "test", "--out", str(receipt_path), "--", str(runner)
        ]))
        receipt = json.loads(receipt_path.read_text())
        expected_tree = subprocess.run(
            ["git", "write-tree"], check=True, capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(command_evidence.RUNNER, receipt["runner"])
        self.assertEqual(expected_tree, receipt["source_tree"])
        self.assertEqual(0, receipt["exit_code"])
        self.assertEqual(1, receipt["tests_passed"])
        self.assertTrue(pathlib.Path(receipt["output"]["path"]).is_file())

    def test_build_must_invoke_ninja_family_directly(self):
        receipt_path = self.root / "build-receipt.json"
        self.assertEqual(1, command_evidence.main([
            "--kind", "build", "--out", str(receipt_path), "--", "/bin/true"
        ]))
        autoninja = self.depot_autoninja()
        self.assertEqual(0, command_evidence.main([
            "--kind", "build", "--out", str(receipt_path), "--", str(autoninja)
        ]))

    def test_shell_and_noop_tests_are_rejected(self):
        for executable in ("/bin/true", "/bin/sh"):
            with self.subTest(executable=executable):
                self.assertEqual(1, command_evidence.main([
                    "--kind", "test", "--out", str(self.root / "bad.json"),
                    "--", executable,
                ]))

    def test_test_receipt_requires_checkout_elf(self):
        outside = self.executable("not_a_test_tool")
        inside = self.repo / "out" / "perf" / "fake_test"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_text("#!/bin/sh\nexit 0\n")
        inside.chmod(0o755)
        for executable in (outside, inside):
            with self.subTest(executable=executable):
                self.assertEqual(1, command_evidence.main([
                    "--kind", "test", "--out", str(self.root / "bad-elf.json"),
                    "--", str(executable),
                ]))

    def test_zero_exit_without_gtest_results_is_rejected(self):
        path = self.repo / "out" / "perf" / "empty_test"
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2("/bin/true", path)
        self.assertEqual(1, command_evidence.main([
            "--kind", "test", "--out", str(self.root / "empty.json"),
            "--", str(path),
        ]))


if __name__ == "__main__":
    unittest.main()
