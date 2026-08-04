"""Tests for build-discovery-brief.py."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "build-discovery-brief.py"
)
SKILL_ROOT = SCRIPT_PATH.parent.parent


class BuildDiscoveryBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.review_dir = self.tmpdir / "review"
        self.review_dir.mkdir()
        self.skill_snap = self.review_dir / "skill-snapshot"
        self.skill_snap.mkdir()

        # Copy required templates from real skill root
        tmpl_dir = self.skill_snap / "references/worker/templates"
        tmpl_dir.mkdir(parents=True)
        for name in [
            "generated-common-header.md",
            "subagent-brief-discovery-thread.md",
        ]:
            src = SKILL_ROOT / "references/worker/templates" / name
            shutil.copy(src, tmpl_dir / name)

        pin_md = self.review_dir / "pin.md"
        pin_md.write_text(
            "# CL 123456 — patchset 2 pin\n\n"
            "- Revision SHA: aaaabbbbccccddddeeeeffff0000111122223333\n"
            "- Parent SHA: 1111222233334444555566667777888899990000\n"
            "- Worktree: /path/to/worktree\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_help_option(self) -> None:
        res = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("usage:", res.stdout)

    def test_builds_brief_successfully(self) -> None:
        res = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(self.review_dir),
                "--work-id",
                "TEST1",
                "--entry",
                "Test Roster Entry",
                "--procedure",
                "worker/deep-dive-recipes/recipe-test.md",
                "--pathspec",
                "foo/bar.cc",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        out_file = self.review_dir / "briefs" / "TEST1.md"
        self.assertTrue(out_file.is_file())
        text = out_file.read_text(encoding="utf-8")
        self.assertIn("CL 123456", text)
        self.assertIn("patchset 2", text)
        self.assertIn("TEST1", text)
        self.assertIn("Test Roster Entry", text)
        self.assertIn("foo/bar.cc", text)
        self.assertNotIn("⟨CL⟩", text)
        self.assertNotIn("⟨PS⟩", text)


if __name__ == "__main__":
    unittest.main()
