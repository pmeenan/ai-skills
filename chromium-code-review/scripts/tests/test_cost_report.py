#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
REPORT = SCRIPTS / "report-review-costs.py"


class CostReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.review = Path(tempfile.mkdtemp(prefix="cost-report-"))
        self.addCleanup(shutil.rmtree, self.review, True)
        ledger = self.review / "ledger"
        ledger.mkdir()
        (ledger / "EPW.md").write_text("x" * 400, encoding="utf-8")
        (self.review / "orchestration.tsv").write_text(
            "phase\twork_id\tattempt\tstate\ttier\ttask_id\tbrief\t"
            "artifact\tremaining_scope\tdepends_on\n"
            f"4\tEPW\t1\tpartial\tfrontier\tt1\t{self.review}/briefs/EPW.md\t"
            f"{self.review}/ledger/EPW.md\tcells\tPLAN\n"
            f"4\tEPW\t2\tcomplete\tfrontier\tt2\t"
            f"{self.review}/briefs/EPW-2.md\t{self.review}/ledger/EPW.md\t"
            "-\tEPW:1\n"
            "5\tV001\t1\tcomplete\tstandard\tt3\t"
            f"{self.review}/briefs/V001.md\t{self.review}/verification/"
            "V001.md\t-\tEPW:2\n",
            encoding="utf-8")
        (self.review / "input-manifest.tsv").write_text(
            "work_id\tattempt\tphase\tbrief\tinput_path\trole\tbytes\tsha256\n"
            f"EPW\t1\t4\tb\t{self.review}/briefs/EPW.md\tbrief\t100\tdead\n"
            f"EPW\t1\t4\tb\t{self.review}/refs/recipe.md\treference\t250\tbeef\n"
            # Same path with a second role must count once.
            f"EPW\t1\t4\tb\t{self.review}/refs/recipe.md\tcontrol\t250\tbeef\n"
            f"V001\t1\t5\tb\t{self.review}/briefs/V001.md\tbrief\t80\tfeed\n",
            encoding="utf-8")

    def run_report(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPORT), str(self.review)],
            capture_output=True, text=True, check=False)

    def test_report_totals(self) -> None:
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        tsv = (self.review / "cost-report.tsv").read_text(encoding="utf-8")
        rows = [line.split("\t") for line in tsv.splitlines()[1:]]
        self.assertEqual(len(rows), 3)
        by_key = {(row[1], row[2]): row for row in rows}
        # Duplicate-role path counted once: 100 + 250, not 100 + 500.
        self.assertEqual(by_key[("EPW", "1")][5], "350")
        # Artifact bytes attributed once across attempts of one artifact.
        self.assertEqual(by_key[("EPW", "1")][6], "400")
        self.assertEqual(by_key[("EPW", "2")][6], "0")
        # Unmanifested attempt reports zero input, missing artifact zero out.
        self.assertEqual(by_key[("V001", "1")][5], "80")
        self.assertEqual(by_key[("V001", "1")][6], "0")
        md = (self.review / "cost-report.md").read_text(encoding="utf-8")
        self.assertIn("| 4 | 2 | 1 | 350 | 400 |", md)
        self.assertIn("| frontier | 2 | 350 |", md)
        self.assertFalse((self.review / "code-read-costs.tsv").exists())

    def test_wall_clock_timeline(self) -> None:
        (self.review / "progress.md").write_text(
            "# Progress\n"
            "- 2026-07-01T14:00:00Z Phase 0 done: pinned.\n"
            "- 2026-07-01T14:20:00Z Phase 1 done: inventory.\n"
            # Dashed phase labels (any single token) must not be dropped.
            "- 2026-07-01T14:22:00Z Phase verification-2 done: delta round.\n"
            # Batch spawn: one event per work unit, same wave.
            "- 2026-07-01T14:25:00Z spawned EPW attempt 1: batch D01\n"
            "- 2026-07-01T14:25:01Z spawned i18n-audit.7 attempt 1: batch D01\n"
            "- 2026-07-01T15:40:00Z collected EPW attempt 1: 9 rows\n"
            # Retry: same work ID, distinct attempt, distinct latency.
            "- 2026-07-01T15:45:00Z spawned EPW attempt 2: continuation\n"
            "- 2026-07-01T16:00:00Z collected EPW attempt 2: 2 rows\n"
            # Non-task-prefixed odd identifier still pairs by (id, attempt).
            "- 2026-07-01T16:10:00Z collected i18n-audit.7 attempt 1: clean\n"
            "- untimestamped legacy line is tolerated\n",
            encoding="utf-8")
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        md = (self.review / "cost-report.md").read_text(encoding="utf-8")
        self.assertIn("- Total span: 2h10m", md)
        self.assertIn("| Phase 1 done | 20m00s |", md)
        self.assertIn("| Phase verification-2 done | 2m00s |", md)
        self.assertIn("| EPW#1 | 1h15m |", md)
        self.assertIn("| EPW#2 | 15m00s |", md)
        self.assertIn("| i18n-audit.7#1 | 1h44m |", md)

    def test_log_progress_helper_emits_parsable_events(self) -> None:
        helper = SCRIPTS / "log-progress.py"
        for args in (["spawned", "EPW", "1", "batch", "D01"],
                     ["collected", "EPW", "1", "9 rows"],
                     ["phase", "4", "discovery complete"],
                     ["note", "free text"]):
            result = subprocess.run(
                [sys.executable, str(helper), str(self.review), *args],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
        bad = subprocess.run(
            [sys.executable, str(helper), str(self.review),
             "spawned", "two words", "1"],
            capture_output=True, text=True, check=False)
        self.assertNotEqual(bad.returncode, 0)
        progress = (self.review / "progress.md").read_text(encoding="utf-8")
        self.assertRegex(
            progress,
            r"- \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ spawned EPW attempt 1: "
            r"batch D01")
        self.assertRegex(
            progress,
            r"- \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ collected EPW attempt 1: "
            r"9 rows")
        self.assertRegex(
            progress,
            r"- \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ Phase 4 done: "
            r"discovery complete")
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        md = (self.review / "cost-report.md").read_text(encoding="utf-8")
        self.assertIn("| EPW#1 |", md)

    def test_missing_orchestration_fails(self) -> None:
        (self.review / "orchestration.tsv").unlink()
        result = self.run_report()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
