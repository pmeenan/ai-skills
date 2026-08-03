#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
INSTRUMENT = SCRIPTS / "instrument-command.py"
ARCHIVE = SCRIPTS / "archive-review-instrumentation.py"
REPORT = SCRIPTS / "report-review-costs.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        check=True, env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                         "GIT_COMMITTER_NAME": "t",
                         "GIT_COMMITTER_EMAIL": "t@t",
                         "PATH": "/usr/bin:/bin"}).stdout.strip()


class InstrumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="review-instrumentation-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.review = self.root / "review"
        self.review.mkdir()
        (self.review / "directives.md").write_text(
            "instrumentation: code-reads-v1\n"
            "instrumentation-label: model-a\n", encoding="utf-8")
        (self.review / "pin.md").write_text(
            "# CL 9999999 — patchset 3 pin\n\n"
            "- Pinned patchset: 3\n- Revision SHA: abcdef1234567890\n",
            encoding="utf-8")
        (self.review / "orchestration.tsv").write_text(
            "phase\twork_id\tattempt\tstate\ttier\ttask_id\tbrief\t"
            "artifact\tremaining_scope\tdepends_on\n"
            "4\tEPW\t1\tcomplete\tfrontier\tt1\tb\t-\t-\tPLAN\n",
            encoding="utf-8")
        self.skill = self.root / "skill"
        self.skill.mkdir()
        (self.skill / "SKILL.md").write_text(
            "---\nname: test\ndescription: test\n---\n", encoding="utf-8")
        git(self.skill, "init", "-q")
        git(self.skill, "add", "SKILL.md")
        git(self.skill, "commit", "-qm", "skill")
        snapshot = self.review / "skill-snapshot"
        snapshot.mkdir()
        (snapshot / "snapshot-manifest.json").write_text(json.dumps({
            "schema_version": 1, "source_path": str(self.skill), "files": []
        }) + "\n", encoding="utf-8")

    def instrument(self, *command: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(INSTRUMENT), str(self.review), "EPW", "1",
             "--cwd", str(self.root), "--", *command],
            capture_output=True, check=False)

    def test_wrapper_preserves_output_status_and_logs_cost(self) -> None:
        result = self.instrument(
            sys.executable, "-c",
            "import sys; print('source'); print('warn', file=sys.stderr); "
            "raise SystemExit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, b"source\n")
        self.assertEqual(result.stderr, b"warn\n")
        log = next((self.review / "instrumentation" /
                    "code-reads").glob("*.jsonl"))
        event = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(event["schema"], "code-reads-v1")
        self.assertEqual(event["stdout_bytes"], 7)
        self.assertEqual(event["stderr_bytes"], 5)
        self.assertEqual(event["exit_code"], 7)

        report = subprocess.run(
            [sys.executable, str(REPORT), str(self.review)],
            capture_output=True, text=True, check=False)
        self.assertEqual(report.returncode, 0, report.stderr)
        text = (self.review / "cost-report.md").read_text(encoding="utf-8")
        self.assertIn("## Instrumented code/tool reads", text)
        self.assertIn("| EPW#1 | 1 | 1 | 7 |", text)
        read_tsv = (self.review / "code-read-costs.tsv").read_text(
            encoding="utf-8")
        self.assertIn("EPW\t1\t1\t1\t7\t5\t", read_tsv)

    def test_wrapper_requires_opt_in(self) -> None:
        (self.review / "directives.md").write_text("mode: full\n",
                                                   encoding="utf-8")
        result = self.instrument(sys.executable, "-c", "print('x')")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"lacks 'instrumentation: code-reads-v1'", result.stderr)

    def test_archive_is_versioned_and_excludes_review_content(self) -> None:
        self.instrument(sys.executable, "-c", "print('code bytes')")
        subprocess.run([sys.executable, str(REPORT), str(self.review)],
                       check=True, capture_output=True)
        (self.review / "draft-review.md").write_text(
            "finding text must not be archived", encoding="utf-8")
        (self.review / "packets").mkdir()
        (self.review / "packets" / "EPW.spec.tsv").write_text(
            "kind\tpath\told_range\tnew_range\tnote\n",
            encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ARCHIVE), str(self.review)],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = Path(result.stdout.strip())
        commit = git(self.skill, "rev-parse", "HEAD")
        self.assertEqual(destination.parent.name, commit)
        self.assertTrue((destination / "metadata.json").is_file())
        self.assertTrue((destination / "cost-report.md").is_file())
        self.assertTrue((destination / "instrumentation" / "code-reads" /
                         "EPW-attempt-1.jsonl").is_file())
        self.assertTrue((destination / "packets" / "EPW.spec.tsv").is_file())
        self.assertFalse((destination / "draft-review.md").exists())
        pointer = (self.review / "instrumentation-archive.md").read_text(
            encoding="utf-8")
        self.assertIn(str(destination), pointer)
        metadata = json.loads((destination / "metadata.json").read_text(
            encoding="utf-8"))
        self.assertEqual(metadata["instrumentation_label"], "model-a")
        self.assertEqual(metadata["skill_git_revision"], commit)
        self.assertEqual(metadata["repository_git_revision"], commit)

        # Re-archiving one review is idempotent.
        again = subprocess.run(
            [sys.executable, str(ARCHIVE), str(self.review)],
            capture_output=True, text=True, check=False)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(Path(again.stdout.strip()), destination)

    def test_parallel_same_cl_runs_get_distinct_archives(self) -> None:
        second = self.root / "review-second-model"
        shutil.copytree(self.review, second)
        (second / "directives.md").write_text(
            "instrumentation: code-reads-v1\n"
            "instrumentation-label: model-b\n", encoding="utf-8")
        destinations = []
        for review in (self.review, second):
            result = subprocess.run(
                [sys.executable, str(ARCHIVE), str(review)],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            destinations.append(Path(result.stdout.strip()))
        self.assertNotEqual(destinations[0], destinations[1])
        self.assertEqual(destinations[0].parent, destinations[1].parent)
        uuids = {
            json.loads((destination / "metadata.json").read_text(
                encoding="utf-8"))["run_uuid"]
            for destination in destinations
        }
        self.assertEqual(len(uuids), 2)


if __name__ == "__main__":
    unittest.main()
