"""Tests for explain-gate-error.py."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "explain-gate-error.py"
CATALOGUE = SCRIPTS.parent / "references" / "gate-errors.md"

FIXTURE = """# Fixture catalogue

## 1. Enums

| Flag | Legal values | Source |
| --- | --- | --- |
| `validate-review-dir.py --phase` | `auto`, `pin`, `collection` | validate-review-dir.py:34 |

## 2. seal-work-unit.py

| Message | What it means | Fix | Source |
| --- | --- | --- | --- |
| `input-manifest.tsv:<N>: byte count mismatch for <path>` | The file changed size after sealing. | Seal a new attempt. | validate-review-dir.py:2494 |
| `unknown tier <value>; expected one of mechanical, standard` | Bad `--tier`. | Pass a legal tier. | seal-work-unit.py:192 |
"""


def invoke(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class ExplainGateErrorTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fixture = self.tmp / "gate-errors.md"
        self.fixture.write_text(FIXTURE, encoding="utf-8")

    def test_matches_despite_concrete_line_numbers_and_paths(self) -> None:
        result = invoke(
            "--catalogue", str(self.fixture),
            "input-manifest.tsv:14: byte count mismatch for /tmp/cl-1-ps2/briefs/INV.md: 900 != 1200",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("byte count mismatch", result.stdout)
        self.assertIn("Seal a new attempt.", result.stdout)
        self.assertIn("validate-review-dir.py:2494", result.stdout)

    def test_reports_the_section_and_catalogue_line(self) -> None:
        result = invoke("--catalogue", str(self.fixture), "unknown tier frontierish")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2. seal-work-unit.py", result.stdout)
        self.assertRegex(result.stdout, r"gate-errors\.md:\d+")

    def test_no_match_exits_one_and_says_to_add_a_row(self) -> None:
        result = invoke("--catalogue", str(self.fixture), "quokka refrigeration subsystem offline")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no row matches", result.stdout)
        self.assertIn("add one to", result.stdout)

    def test_max_bounds_the_output(self) -> None:
        result = invoke("--catalogue", str(self.fixture), "--max", "1", "byte count mismatch tier")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("MESSAGE:"), 1)

    def test_missing_catalogue_is_a_clear_error(self) -> None:
        result = invoke("--catalogue", str(self.tmp / "absent.md"), "byte count mismatch")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no gate-error catalogue at", result.stderr)

    def test_rejects_an_unsearchable_message(self) -> None:
        result = invoke("--catalogue", str(self.fixture), "!!! ???")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no searchable words", result.stderr)

    @unittest.skipUnless(CATALOGUE.is_file(), "catalogue not present")
    def test_real_catalogue_answers_the_observed_failures(self) -> None:
        for message, expected in (
            ("could not persist authenticated mutable lease state", "local-disk"),
            ("input-manifest.tsv:14: byte count mismatch", "byte count mismatch"),
            ("attempt already exists but does not match the requested seal", "attempt"),
        ):
            with self.subTest(message=message):
                result = invoke("--max", "1", message)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)


if __name__ == "__main__":
    unittest.main()
