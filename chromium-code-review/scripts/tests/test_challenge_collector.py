#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
COLLECT = SCRIPTS / "collect-challenge-round.py"

INDEX = """# Challenge index — round 1 / draft revision 1

- Draft revision: 1

| shard | scope | brief | artifact | expected coverage | issues |
| --- | --- | --- | --- | --- | --- |
| CH001 | F001 | briefs/CH001.md | challenge/round-1/CH001.md | card:F001 | |
| CH002 | global-consistency | briefs/CH002.md | challenge/round-1/CH002.md | global:consistency | |
"""

SHARD_WITH_ISSUE = """# Synthesis challenge — round 1 / CH001 — draft revision 1

| id | scope | draft says | record says | evidence | required correction | status |
| --- | --- | --- | --- | --- | --- | --- |
| CH001-1 | F001 | fix validated | only immediate path | RC001-1 | downgrade | open |
"""

SHARD_CLEAN = """# Synthesis challenge — round 1 / CH002 — draft revision 1

No issues found. Hashes audited: abc123.
"""


class ChallengeCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.review = Path(tempfile.mkdtemp(prefix="challenge-collect-"))
        self.addCleanup(shutil.rmtree, self.review, True)
        self.round = self.review / "challenge" / "round-1"
        self.round.mkdir(parents=True)
        (self.round / "index.md").write_text(INDEX, encoding="utf-8")
        (self.round / "CH001.md").write_text(SHARD_WITH_ISSUE, encoding="utf-8")
        (self.round / "CH002.md").write_text(SHARD_CLEAN, encoding="utf-8")

    def collect(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(COLLECT), str(self.review), "1"],
            capture_output=True, text=True, check=False)

    def test_open_issue_round_collects_as_revision_required(self) -> None:
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        index = (self.round / "index.md").read_text(encoding="utf-8")
        self.assertIn("| CH001-1 |", index)
        self.assertIn("| none |", index)
        self.assertIn("- Result: revision required", index)
        self.assertIn("- Total open issues: 1", index)
        pointer = (self.review / "challenge.md").read_text(encoding="utf-8")
        self.assertIn("challenge/round-1/index.md", pointer)
        self.assertIn("- Draft revision: 1", pointer)

    def test_clean_round_passes(self) -> None:
        (self.round / "CH001.md").write_text(SHARD_CLEAN, encoding="utf-8")
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        index = (self.round / "index.md").read_text(encoding="utf-8")
        self.assertIn("- Result: pass", index)
        self.assertIn("- Total open issues: 0", index)

    def test_missing_shard_fails(self) -> None:
        (self.round / "CH002.md").unlink()
        result = self.collect()
        self.assertNotEqual(result.returncode, 0)
        index = (self.round / "index.md").read_text(encoding="utf-8")
        self.assertIn("incomplete", index)

    def test_revision_mismatch_fails(self) -> None:
        (self.round / "CH001.md").write_text(
            SHARD_WITH_ISSUE.replace("draft revision 1", "draft revision 2"),
            encoding="utf-8")
        result = self.collect()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("audited draft revision 2", result.stderr)

    def test_recollection_is_idempotent(self) -> None:
        self.collect()
        first = (self.round / "index.md").read_bytes()
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(first, (self.round / "index.md").read_bytes())

    def test_clerical_projection_closes_issue_without_editing_shard(self) -> None:
        before = self.review / "draft-sections" / "FRAME.before-clerical.md"
        current = self.review / "draft-sections" / "FRAME.md"
        before.parent.mkdir()
        before.write_text("Card: synthesis/cards/F001.md\n", encoding="utf-8")
        current.write_text(
            "Card: synthesis/format-revision2/cards/F001.md\n", encoding="utf-8"
        )
        audited = hashlib.sha256(before.read_bytes()).hexdigest()
        current_hash = hashlib.sha256(current.read_bytes()).hexdigest()
        shard = SHARD_WITH_ISSUE.replace(
            "| CH001-1 | F001 | fix validated | only immediate path | RC001-1 | downgrade | open |",
            f"| CH001-1 | F001 | stale path | current path | {audited} | clerical — update path | open |",
        )
        shard_path = self.round / "CH001.md"
        shard_path.write_text(shard, encoding="utf-8")
        original_shard = shard_path.read_bytes()
        receipt = {
            "draft_revision": "1",
            "resolutions": [{
                "issue": "CH001-1", "shard": "CH001",
                "classification": "clerical", "evidence": "path-only correction",
                "corrections": [{
                    "kind": "exact-text-projection",
                    "path": "draft-sections/FRAME.md",
                    "before_path": "draft-sections/FRAME.before-clerical.md",
                    "audited_sha256": audited,
                    "current_sha256": current_hash,
                    "replacements": [{
                        "old": "synthesis/cards/F001.md",
                        "new": "synthesis/format-revision2/cards/F001.md",
                        "count": 1,
                    }],
                }],
            }],
        }
        (self.round / "clerical-resolutions.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        index = (self.round / "index.md").read_text(encoding="utf-8")
        self.assertIn("- Result: pass", index)
        self.assertIn("- Clerical resolutions:", index)
        self.assertEqual(original_shard, shard_path.read_bytes())
        first_index = (self.round / "index.md").read_bytes()
        self.assertEqual(self.collect().returncode, 0)
        self.assertEqual(first_index, (self.round / "index.md").read_bytes())

    def test_receipt_cannot_close_unclassified_issue(self) -> None:
        receipt = {
            "draft_revision": "1",
            "resolutions": [{
                "issue": "CH001-1", "shard": "CH001",
                "classification": "clerical", "evidence": "claimed clerical",
                "corrections": [{
                    "kind": "structured-amendment", "path": "reconciliation.md",
                    "amendment": "A1",
                }],
            }],
        }
        (self.review / "reconciliation.md").write_text(
            "A1 replace-fields\n", encoding="utf-8"
        )
        (self.round / "clerical-resolutions.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )
        result = self.collect()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not explicitly clerical", result.stderr)


if __name__ == "__main__":
    unittest.main()
