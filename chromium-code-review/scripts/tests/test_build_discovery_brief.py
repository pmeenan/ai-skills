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

    def test_generalist_and_probe_briefs_include_required_tables(self) -> None:
        res_gss = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(self.review_dir),
                "--work-id",
                "GSS1",
                "--entry",
                "Generalist Semantic And State Discovery — shard 1",
                "--procedure",
                "worker/discovery-checklists/state-persistence-and-cache.md",
                "--pathspec",
                "graph:E-STATE-1",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_gss.returncode, 0, msg=res_gss.stderr)
        gss_text = (self.review_dir / "briefs" / "GSS1.md").read_text(encoding="utf-8")
        self.assertIn("## Complexity graph delta", gss_text)
        self.assertIn("## Specialist escalation assessments", gss_text)

        res_probe = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(self.review_dir),
                "--work-id",
                "OBL",
                "--entry",
                "Ownership And Blink Lifecycle",
                "--procedure",
                "worker/chromium-specialist-checklists/ownership-and-blink-lifecycle-obl.md",
                "--pathspec",
                "specialist:probe; graph:E-ASYNC-1",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_probe.returncode, 0, msg=res_probe.stderr)
        probe_text = (self.review_dir / "briefs" / "OBL.md").read_text(encoding="utf-8")
        self.assertIn("## Specialist probe outcome", probe_text)

    def test_icrr_and_icr_briefs(self) -> None:
        res_icrr = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(self.review_dir),
                "--work-id",
                "ICRR",
                "--entry",
                "In-Tree Code Review Runner",
                "--procedure",
                "worker/chromium-specialist-checklists/in-tree-experimental-code-review-icrr-icr.md",
                "--pathspec",
                "graph:all-inventory-edges",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_icrr.returncode, 0, msg=res_icrr.stderr)
        icrr_text = (self.review_dir / "briefs" / "ICRR.md").read_text(encoding="utf-8")
        self.assertIn("internal-review-raw.md", icrr_text)
        self.assertIn("internal-review-capabilities.md", icrr_text)
        self.assertIn("packets/ICR-code.md", icrr_text)

        res_icr = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(self.review_dir),
                "--work-id",
                "ICR",
                "--entry",
                "In-Tree Code Review",
                "--procedure",
                "worker/chromium-specialist-checklists/in-tree-experimental-code-review-icrr-icr.md",
                "--pathspec",
                "graph:all-inventory-edges",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_icr.returncode, 0, msg=res_icr.stderr)
        icr_text = (self.review_dir / "briefs" / "ICR.md").read_text(encoding="utf-8")
        self.assertIn("In-Tree Code Review Wrapper Requirements", icr_text)
        self.assertIn("internal-review-raw.md", icr_text)
        self.assertIn("ledger/ICR.md", icr_text)
        self.assertIn("row IDs ICR-1, ICR-2, ...", icr_text)


if __name__ == "__main__":
    unittest.main()
