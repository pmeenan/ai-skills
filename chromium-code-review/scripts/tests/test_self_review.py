"""Self-review fast path: reviewer authored the CL, so skip report refinement."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load("validate_review_dir_sr", "validate-review-dir.py")
GATE = load("refresh_delivery_gate_sr", "refresh-delivery-gate.py")
RECON = load("build_reconciliation_sr", "build-reconciliation.py")


def build_review(root: Path, pin_extra: str = "") -> Path:
    """Minimal post-Phase-5.5 review with one CONFIRMED P3 finding."""
    review = root / "review"
    worktree = root / "worktree"
    worktree.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(worktree), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.test")
    (worktree / "a.cc").write_text("int x = 1;\nint y = 2;\n")
    git("add", "a.cc")
    git("commit", "-qm", "base")
    parent = git("rev-parse", "HEAD")
    (worktree / "a.cc").write_text("int x = 10;\nint y = 2;\n")
    git("commit", "-qam", "change")
    revision = git("rev-parse", "HEAD")
    shutil.copytree(SCRIPTS.parent, review / "skill-snapshot",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (review / "ledger").mkdir()
    (review / "verification").mkdir()
    (review / "profile.json").write_text(json.dumps({
        "files": [{"path": "a.cc", "status": "M"}],
        "budgets": {"candidate_packet_budget_bytes": 16384,
                    "worker_input_budget_bytes": 131072},
    }))
    (review / "pin.md").write_text(
        f"# CL 123 — patchset 1 pin\n- Revision SHA: {revision}\n"
        f"- Parent SHA: {parent}\n- Worktree: {worktree}\n{pin_extra}")
    (review / "ledger/PR.md").write_text('''# PR

## Candidate rows
| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| PR-1 | minor naming nit on `x` | a.cc:1 | inspected | CL-introduced | P3 | candidate |

## Candidate descriptors
| candidate | classes | obligations | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PR-1 | style | local-consistency | none | a.cc:x | naming consistency | declaration | a.cc | x |
''')
    (review / "verification/batches.md").write_text('''## Batches

| batch | brief | candidates | verdict file |
| --- | --- | --- | --- |
| V001 | briefs/V001.md | PR-1 | verification/V001.md |
''')
    (review / "verification/V001.md").write_text('''# Verification Batch V001

## Verdicts
| id | candidate | verdict | calibrated severity | anchor | delta | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| V001-1 | PR-1 | CONFIRMED | P3 | P3 style | none | a.cc:1 |

## Trace closure
| candidate | obligation | result | evidence |
| --- | --- | --- | --- |
| PR-1 | local-consistency | SUPPORTS CANDIDATE | local file a.cc:1 |

## Verified affinity
| candidate | invariant owner | violated invariant | state / transition |
| --- | --- | --- | --- |
| PR-1 | a.cc:x | naming consistency | declaration |
''')
    return review


class SelfReviewDetectionTests(unittest.TestCase):
    def test_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertFalse(VALIDATOR.is_self_review(root))
            self.assertFalse(GATE.is_self_review(root))
            (root / "pin.md").write_text("- Self-review: yes\n")
            self.assertTrue(VALIDATOR.is_self_review(root))
            self.assertTrue(GATE.is_self_review(root))
            # An explicit directive overrides auto-detection.
            (root / "directives.md").write_text("- Self-review: false\n")
            self.assertFalse(VALIDATOR.is_self_review(root))
            self.assertFalse(GATE.is_self_review(root))
            (root / "directives.md").write_text("- Mode: self-review\n")
            (root / "pin.md").unlink()
            self.assertTrue(VALIDATOR.is_self_review(root))
            (root / "directives.md").unlink()
            (root / "profile.json").write_text(json.dumps({"self_review": True}))
            self.assertTrue(VALIDATOR.is_self_review(root))
            self.assertTrue(RECON.resolve_self_review(
                root, {"self_review": True}, ""))
            self.assertFalse(RECON.resolve_self_review(
                root, {"self_review": True}, "", cli_override=False))


class SelfReviewReconciliationTests(unittest.TestCase):
    def run_recon(self, review: Path, *extra: str):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "build-reconciliation.py"),
             str(review), *extra],
            capture_output=True, text=True)

    def test_normal_review_writes_no_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            review = build_review(Path(temporary))
            result = self.run_recon(review)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse((review / "draft-review.md").exists())
            self.assertFalse((review / "output-coverage.tsv").exists())

    def test_self_review_writes_deterministic_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            review = build_review(Path(temporary), "- Self-review: yes\n")
            result = self.run_recon(review)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("self-review", result.stdout)
            draft = (review / "draft-review.md").read_text()
            self.assertIn("- Draft revision: 1", draft)
            self.assertIn("- Self-review: yes", draft)
            self.assertIn("PS1", draft)
            self.assertFalse(VALIDATOR.contains_local_path_or_url(draft))
            part = (review / "draft-parts/F001.md").read_text()
            self.assertIn(part, draft)
            self.assertIn("- **Synthesis item:** F001", part)
            self.assertTrue((review / "draft-parts/FRAME.md").is_file())
            self.assertIn("Not Posted", (review / "gerrit-comments.md").read_text())

            with (review / "output-coverage.tsv").open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(1, len(rows))
            self.assertEqual("-", rows[0]["gerrit_path"])
            self.assertEqual(
                hashlib.sha256(part.encode()).hexdigest(), rows[0]["draft_sha256"])

            report = VALIDATOR.Report()
            VALIDATOR.validate_output_coverage(
                review, {"F001": "finding"}, draft,
                (review / "gerrit-comments.md").read_text(), report)
            self.assertEqual([], report.errors)

    def test_self_review_lifts_survivor_cap(self):
        with tempfile.TemporaryDirectory() as temporary:
            review = build_review(Path(temporary))
            capped = self.run_recon(review, "--max-survivors", "0")
            self.assertNotEqual(0, capped.returncode)
            self.assertIn("RB subagent", capped.stderr)
            forced = self.run_recon(review, "--self-review")
            self.assertEqual(0, forced.returncode, forced.stderr)
            self.assertTrue((review / "draft-review.md").is_file())


class SelfReviewDeliveryGateTests(unittest.TestCase):
    def test_challenge_proof_without_challenge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "draft-review.md").write_text("- Draft revision: 1\n")
            self.assertIsNone(GATE.challenge_proof(root))
            (root / "pin.md").write_text("- Self-review: yes\n")
            self.assertEqual(
                ("1", "self-review (challenge skipped)"),
                GATE.challenge_proof(root))

    def test_freshness_gate_line_variant_is_replaceable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "reconciliation.md").write_text(
                "1. **Pin:** Yes\n2. **Freshness gate:** Yes — pending\n")
            replaced = GATE.freshness_replacement(root, "current")
            self.assertIsNotNone(replaced)
            self.assertIn("2. **Freshness:** yes — current; delivery-gate.md",
                          replaced[1])


if __name__ == "__main__":
    unittest.main()
