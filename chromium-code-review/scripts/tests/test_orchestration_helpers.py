#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
SET_STATE = SCRIPTS / "set-work-state.py"
REFRESH = SCRIPTS / "refresh-manifest.py"
AWAIT = SCRIPTS / "await-workers.py"

ORCHESTRATION_COLUMNS = (
    "phase", "work_id", "attempt", "state", "tier", "task_id", "brief",
    "artifact", "remaining_scope", "depends_on",
)
INPUT_COLUMNS = (
    "work_id", "attempt", "phase", "brief", "input_path", "role", "bytes",
    "sha256",
)


def table(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(columns)]
    lines.extend("\t".join(row[column] for column in columns) for row in rows)
    return "\n".join(lines) + "\n"


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="orchestration-helpers-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.review = self.root / "review"
        (self.review / "deliverables").mkdir(parents=True)
        (self.review / "briefs").mkdir()
        (self.review / "inputs").mkdir()
        (self.review / "progress.md").write_text("# progress\n", encoding="utf-8")

        self.brief = self.review / "briefs" / "A.md"
        self.brief.write_text("brief body\n", encoding="utf-8")
        self.prestate = self.review / "inputs" / "prestate.txt"
        self.prestate.write_text("one\n", encoding="utf-8")
        self.reference = self.review / "inputs" / "reference.md"
        self.reference.write_text("reference\n", encoding="utf-8")

        self.orchestration = self.review / "orchestration.tsv"
        self.manifest = self.review / "input-manifest.tsv"
        self.write_orchestration([
            self.row("A", "1", "running", "deliverables/A.md"),
            self.row("B", "1", "queued", "deliverables/B.md"),
            self.row("C", "1", "complete", "deliverables/C.md"),
        ])
        self.write_manifest([
            self.input_row("A", "1", self.brief, "brief", b"brief body\n"),
            self.input_row("A", "1", self.prestate, "prestate", b"one\n"),
            self.input_row("A", "1", self.reference, "reference",
                           b"reference\n"),
        ])

    def row(self, work_id: str, attempt: str, state: str,
            artifact: str) -> dict[str, str]:
        return {
            "phase": "P1", "work_id": work_id, "attempt": attempt,
            "state": state, "tier": "standard", "task_id": "-",
            "brief": str(self.brief),
            "artifact": str(self.review / artifact),
            "remaining_scope": "-", "depends_on": "-",
        }

    def input_row(self, work_id: str, attempt: str, path: Path, role: str,
                  payload: bytes) -> dict[str, str]:
        return {
            "work_id": work_id, "attempt": attempt, "phase": "P1",
            "brief": str(self.brief), "input_path": str(path), "role": role,
            "bytes": str(len(payload)),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def write_orchestration(self, rows: list[dict[str, str]]) -> None:
        self.orchestration.write_text(
            table(ORCHESTRATION_COLUMNS, rows), encoding="utf-8")

    def write_manifest(self, rows: list[dict[str, str]]) -> None:
        self.manifest.write_text(
            table(INPUT_COLUMNS, rows), encoding="utf-8")

    def orchestration_lines(self) -> list[str]:
        return self.orchestration.read_text(encoding="utf-8").splitlines()

    def cell(self, work_id: str, attempt: str, column: str) -> str:
        header, *rows = self.orchestration_lines()
        index = header.split("\t").index(column)
        for line in rows:
            values = line.split("\t")
            if values[1] == work_id and values[2] == attempt:
                return values[index]
        self.fail(f"no row for {work_id}:{attempt}")

    def invoke(self, script: Path, *arguments: object,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        if env:
            environment.update(env)
        return subprocess.run(
            [sys.executable, str(script), *(str(value) for value in arguments)],
            capture_output=True, text=True, check=False, env=environment)


class SetWorkStateTests(Fixture):
    def test_happy_path_only_touches_one_row(self) -> None:
        before = self.orchestration_lines()
        result = self.invoke(SET_STATE, self.review, "A", 1, "complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("running -> complete", result.stdout)
        self.assertEqual(self.cell("A", "1", "state"), "complete")
        after = self.orchestration_lines()
        self.assertEqual(len(before), len(after))
        for old, new in zip(before, after):
            if old.split("\t")[1:3] != ["A", "1"]:
                self.assertEqual(old, new)
        self.assertEqual(
            self.manifest.read_text(encoding="utf-8").count("\n"), 4)

    def test_records_task_id_and_remaining_scope(self) -> None:
        result = self.invoke(SET_STATE, self.review, "B", 1, "running",
                          "--task-id", "task-7",
                          "--remaining-scope", "hunks 4-9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cell("B", "1", "task_id"), "task-7")
        self.assertEqual(self.cell("B", "1", "remaining_scope"), "hunks 4-9")

    def test_unknown_work_id_is_refused(self) -> None:
        result = self.invoke(SET_STATE, self.review, "Z", 1, "complete")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no row for Z:1", result.stderr)
        self.assertIn("seal-work-unit.py", result.stderr)

    def test_duplicate_rows_are_refused(self) -> None:
        self.write_orchestration([
            self.row("A", "1", "running", "deliverables/A.md"),
            self.row("A", "1", "queued", "deliverables/A.md"),
        ])
        result = self.invoke(SET_STATE, self.review, "A", 1, "complete")
        self.assertEqual(result.returncode, 1)
        self.assertIn("2 rows match A:1", result.stderr)

    def test_terminal_state_needs_force(self) -> None:
        refused = self.invoke(SET_STATE, self.review, "C", 1, "running")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("terminal state", refused.stderr)
        self.assertIn("--force", refused.stderr)
        self.assertEqual(self.cell("C", "1", "state"), "complete")
        forced = self.invoke(SET_STATE, self.review, "C", 1, "running", "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual(self.cell("C", "1", "state"), "running")

    def test_repeat_is_idempotent(self) -> None:
        before = self.orchestration.read_bytes()
        result = self.invoke(SET_STATE, self.review, "A", 1, "running")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already running", result.stdout)
        self.assertEqual(self.orchestration.read_bytes(), before)

    def test_illegal_state_rejected_by_argparse(self) -> None:
        result = self.invoke(SET_STATE, self.review, "A", 1, "finished")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_log_appends_progress_event(self) -> None:
        result = self.invoke(SET_STATE, self.review, "A", 1, "complete", "--log",
                          "--note", "delivered")
        self.assertEqual(result.returncode, 0, result.stderr)
        progress = (self.review / "progress.md").read_text(encoding="utf-8")
        self.assertIn("collected A attempt 1: delivered", progress)


class RefreshManifestTests(Fixture):
    def test_restamps_grown_prestate(self) -> None:
        self.prestate.write_text("one\ntwo\nthree\n", encoding="utf-8")
        result = self.invoke(REFRESH, self.review, "A", 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("restamped prestate", result.stdout)
        rows = [
            line.split("\t")
            for line in self.manifest.read_text(encoding="utf-8").splitlines()[1:]
        ]
        role = INPUT_COLUMNS.index("role")
        by_role = {row[role]: row for row in rows}
        expected = hashlib.sha256(b"one\ntwo\nthree\n").hexdigest()
        self.assertEqual(by_role["prestate"][INPUT_COLUMNS.index("bytes")], "14")
        self.assertEqual(by_role["prestate"][INPUT_COLUMNS.index("sha256")],
                         expected)
        self.assertEqual(by_role["brief"][INPUT_COLUMNS.index("bytes")], "11")
        self.assertEqual(by_role["reference"][INPUT_COLUMNS.index("bytes")],
                         "10")

    def test_refuses_sealed_roles(self) -> None:
        for role in ("brief", "reference"):
            with self.subTest(role=role):
                before = self.manifest.read_bytes()
                result = self.invoke(REFRESH, self.review, "A", 1, "--role", role)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"refusing to restamp role '{role}'",
                              result.stderr)
                self.assertEqual(self.manifest.read_bytes(), before)

    def test_dry_run_changes_nothing(self) -> None:
        self.prestate.write_text("one\ntwo\n", encoding="utf-8")
        before = self.manifest.read_bytes()
        result = self.invoke(REFRESH, self.review, "A", 1, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would restamp prestate", result.stdout)
        self.assertIn("nothing written", result.stdout)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_unknown_unit_is_refused(self) -> None:
        result = self.invoke(REFRESH, self.review, "B", 1)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no input-manifest rows for B:1", result.stderr)


class AwaitWorkersTests(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.artifact_a = self.review / "deliverables" / "A.md"
        self.artifact_b = self.review / "deliverables" / "B.md"
        self.rejector = self.root / "reject.py"
        self.rejector.write_text(
            "import sys\n"
            "sys.stderr.write('rejected: bad table at line 3\\n"
            "second diagnostic\\nthird diagnostic\\nfourth diagnostic\\n')\n"
            "raise SystemExit(1)\n",
            encoding="utf-8")

    def reject_env(self) -> dict[str, str]:
        return {
            "CHROMIUM_REVIEW_ARTIFACT_VALIDATOR":
                f"{sys.executable} {self.rejector}",
        }

    def test_nothing_outstanding(self) -> None:
        self.write_orchestration([
            self.row("C", "1", "complete", "deliverables/C.md"),
        ])
        result = self.invoke(AWAIT, self.review, "--no-heartbeat")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing outstanding", result.stdout)

    def test_collects_present_artifacts(self) -> None:
        self.artifact_a.write_text("A body\n", encoding="utf-8")
        self.artifact_b.write_text("B body\n", encoding="utf-8")
        result = self.invoke(AWAIT, self.review, "--no-heartbeat",
                          "--no-validate", "--poll-seconds", 0.2,
                          "--timeout-seconds", 10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("A:1 complete", result.stdout)
        self.assertIn("2 complete, 0 needs-repair, 0 outstanding",
                      result.stdout)
        self.assertEqual(self.cell("A", "1", "state"), "complete")
        self.assertEqual(self.cell("B", "1", "state"), "complete")
        progress = (self.review / "progress.md").read_text(encoding="utf-8")
        self.assertIn("collected A attempt 1: artifact", progress)
        self.assertIn("collected B attempt 1: artifact", progress)

    def test_waits_for_late_artifact(self) -> None:
        self.artifact_b.write_text("B body\n", encoding="utf-8")
        timer = threading.Timer(
            0.6, self.artifact_a.write_text, args=("late body\n",))
        timer.start()
        self.addCleanup(timer.cancel)
        result = self.invoke(AWAIT, self.review, "--work", "A:1",
                          "--no-heartbeat", "--no-validate",
                          "--poll-seconds", 0.2, "--timeout-seconds", 10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("A:1 complete", result.stdout)
        self.assertEqual(self.cell("A", "1", "state"), "complete")

    def test_timeout_names_the_outstanding_unit(self) -> None:
        self.artifact_b.write_text("B body\n", encoding="utf-8")
        result = self.invoke(AWAIT, self.review, "--no-heartbeat",
                          "--no-validate", "--poll-seconds", 0.2,
                          "--timeout-seconds", 0.5)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("A:1 outstanding", result.stdout)
        self.assertIn("no artifact yet", result.stdout)
        self.assertIn("1 outstanding", result.stdout)
        self.assertEqual(self.cell("A", "1", "state"), "running")

    def test_no_transition_leaves_state_alone(self) -> None:
        self.artifact_a.write_text("A body\n", encoding="utf-8")
        self.artifact_b.write_text("B body\n", encoding="utf-8")
        before = self.orchestration.read_bytes()
        result = self.invoke(AWAIT, self.review, "--no-heartbeat",
                          "--no-validate", "--no-transition",
                          "--poll-seconds", 0.2, "--timeout-seconds", 10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.orchestration.read_bytes(), before)
        self.assertIn("states left unchanged", result.stdout)
        self.assertNotIn(
            "collected",
            (self.review / "progress.md").read_text(encoding="utf-8"))

    def test_invalid_artifact_becomes_needs_repair(self) -> None:
        self.artifact_a.write_text("A body\n", encoding="utf-8")
        result = self.invoke(AWAIT, self.review, "--work", "A:1",
                          "--no-heartbeat", "--poll-seconds", 0.2,
                          "--timeout-seconds", 10, env=self.reject_env())
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("A:1 needs-repair", result.stdout)
        self.assertIn("bad table at line 3", result.stdout)
        self.assertNotIn("fourth diagnostic", result.stdout)
        self.assertEqual(self.cell("A", "1", "state"), "needs-repair")

    def test_quiet_hides_complete_units(self) -> None:
        self.artifact_a.write_text("A body\n", encoding="utf-8")
        self.artifact_b.write_text("B body\n", encoding="utf-8")
        result = self.invoke(AWAIT, self.review, "--no-heartbeat",
                          "--no-validate", "--quiet", "--poll-seconds", 0.2,
                          "--timeout-seconds", 10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn("A:1 complete", result.stdout)
        self.assertIn("2 complete", result.stdout)


if __name__ == "__main__":
    unittest.main()
