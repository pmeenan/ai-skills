"""Tests for in-tree experimental-code-review integration (ICRR / ICR)."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SKILL_ROOT = SCRIPT_DIR.parent
RESOLVE_SCRIPT = SCRIPT_DIR / "resolve-internal-review-capabilities.py"
PROFILE_SCRIPT = SCRIPT_DIR / "profile-review.py"
INITIAL_PLAN_SCRIPT = SCRIPT_DIR / "build-initial-plan.py"
VALIDATE_WORKER_SCRIPT = SCRIPT_DIR / "validate-worker-artifact.py"
VALIDATE_REVIEW_DIR_SCRIPT = SCRIPT_DIR / "validate-review-dir.py"


class InternalCodeReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test-icr-"))
        self.repo = self.tmpdir / "repo"
        self.repo.mkdir()
        subprocess.run(
            ["git", "-C", str(self.repo), "init", "-q"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "Test User"],
            check=True,
        )
        (self.repo / "net").mkdir()
        (self.repo / "net" / "foo.cc").write_text(
            "int Foo(int x) {\n  return x;\n}\n", encoding="utf-8"
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "add", "."], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-q", "-m", "base"],
            check=True,
        )
        self.parent_sha = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True
        ).strip()

        # Add a general rule and modify net/foo.cc so content_patterns match.
        rules_dir = (
            self.repo
            / "agents"
            / "knowledge_base"
            / "rules"
            / "general"
            / "cpp_safety_and_correctness"
        )
        rules_dir.mkdir(parents=True)
        (rules_dir / "check-magic-call.md").write_text(
            "---\n"
            "name: general/check-magic-call\n"
            "rubric: correctness\n"
            "severity: should_fix\n"
            "---\n\n"
            "**Rule.** Never call `MagicDangerCall()` without checking the return value.\n\n"
            "**Why.** Ignoring the return value drops error states.\n",
            encoding="utf-8",
        )
        (rules_dir / "general-cc-style.md").write_text(
            "---\n"
            "name: general/general-cc-style\n"
            "rubric: correctness\n"
            "severity: suggestion\n"
            "---\n\n"
            "**Rule.** Keep helper functions concise.\n",
            encoding="utf-8",
        )
        (rules_dir / "COMMON_METADATA").write_text(
            'agentic_review {\n'
            '  capability_groups {\n'
            '    name: "magic-call-rule"\n'
            '    path_expressions: ".*\\\\.cc$"\n'
            '    content_patterns: "MagicDangerCall"\n'
            '    rules: "//agents/knowledge_base/rules/general/cpp_safety_and_correctness/check-magic-call.md"\n'
            '  }\n'
            '  capability_groups {\n'
            '    name: "general-cc-rule"\n'
            '    path_expressions: ".*\\\\.cc$"\n'
            '    rules: "//agents/knowledge_base/rules/general/cpp_safety_and_correctness/general-cc-style.md"\n'
            '  }\n'
            '}\n',
            encoding="utf-8",
        )
        (self.repo / "net" / "foo.cc").write_text(
            "int Foo(int x) {\n  MagicDangerCall(x);\n  return x + 1;\n}\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "add", "."], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-q", "-m", "change"],
            check=True,
        )
        self.rev_sha = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True
        ).strip()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_fake_experimental_skill(self) -> Path:
        skill_dir = (
            self.repo
            / "internal"
            / "agents"
            / "skills"
            / "experimental-code-review"
        )
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: experimental-code-review\n---\n# Experimental Code Review\n",
            encoding="utf-8",
        )
        for cat in ("correctness", "safety", "security", "performance", "UX", "accessibility", "testing"):
            (refs_dir / f"{cat}.md").write_text(f"# {cat}\n", encoding="utf-8")
        return skill_dir

    def test_resolve_capabilities_unavailable_when_skill_missing(self) -> None:
        out_md = self.tmpdir / "caps.md"
        env = dict(os.environ)
        env["CHROMIUM_REVIEW_INTERNAL_SKILL_DIR"] = str(self.tmpdir / "nonexistent")
        res = subprocess.run(
            [
                sys.executable,
                str(RESOLVE_SCRIPT),
                str(self.repo),
                "--base",
                self.parent_sha,
                "--revision",
                self.rev_sha,
                "--output",
                str(out_md),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        meta = json.loads(res.stdout)
        self.assertFalse(meta["available"])
        self.assertFalse(out_md.exists())

    def test_resolve_capabilities_and_initial_plan_when_skill_present(self) -> None:
        self._create_fake_experimental_skill()
        out_md = self.tmpdir / "internal-review-capabilities.md"
        res = subprocess.run(
            [
                sys.executable,
                str(RESOLVE_SCRIPT),
                str(self.repo),
                "--base",
                self.parent_sha,
                "--revision",
                self.rev_sha,
                "--output",
                str(out_md),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        meta = json.loads(res.stdout)
        self.assertTrue(meta["available"])
        self.assertEqual(meta["matched_content_rule_count"], 1)
        self.assertEqual(meta["matched_path_rule_count"], 1)
        self.assertTrue(out_md.is_file())
        caps_text = out_md.read_text(encoding="utf-8")
        self.assertIn("check-magic-call.md", caps_text)
        self.assertIn("MagicDangerCall", caps_text)
        self.assertIn("general-cc-style.md", caps_text)

        # Verify build-initial-plan.py emits In-Tree Code Review + ICRR/ICR briefs.
        review_dir = self.tmpdir / "review"
        (review_dir / "indexes").mkdir(parents=True)
        (review_dir / "pin.md").write_text(
            f"# CL 999999 — patchset 1 pin\n\n"
            f"- Revision SHA: {self.rev_sha}\n"
            f"- Parent SHA: {self.parent_sha}\n"
            f"- Worktree: {self.repo}\n",
            encoding="utf-8",
        )
        shutil.copy(out_md, review_dir / "internal-review-capabilities.md")
        profile = {
            "schema_version": 3,
            "effort": "standard",
            "initial_plan_fast_path_eligible": True,
            "compact_generalist_fast_path_eligible": True,
            "topology": {
                "policy": "evidence-graph-v1",
                "collapsed": False,
            },
            "pin": {
                "revision_sha": self.rev_sha,
                "parent_sha": self.parent_sha,
                "worktree": str(self.repo),
            },
            "files": [
                {
                    "path": "net/foo.cc",
                    "status": "M",
                    "changed_lines": 2,
                }
            ],
            "internal_code_review": meta,
        }
        (review_dir / "profile.json").write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
        (review_dir / "indexes" / "inventory.tsv").write_text(
            "kind\tid\tshard\tfile\tsymbol\thunks\tsummary\n"
            "surface\tS1\troot\tnet/foo.cc\tFoo\tH1\tCalls MagicDangerCall\n",
            encoding="utf-8",
        )
        (review_dir / "indexes" / "topology.tsv").write_text(
            "edge\tkind\tsource\ttarget\tevidence\tstatus\n"
            "E-CALL-1\tcall\tS1\tMagicDangerCall\tnet/foo.cc:2\topen\n",
            encoding="utf-8",
        )
        (review_dir / "inventory.md").write_text(
            "# Inventory\n\n## Trigger inventory\n\n"
            "| scope id | surface | root-cause triggers | discovery triggers | graph scope | evidence |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| T1 | S1 | none | TSY absent | graph:E-CALL-1 | net/foo.cc:2 |\n",
            encoding="utf-8",
        )
        res_plan = subprocess.run(
            [
                sys.executable,
                str(INITIAL_PLAN_SCRIPT),
                str(review_dir),
                "--worktree",
                str(self.repo),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_plan.returncode, 0, msg=res_plan.stderr)
        plan_text = (review_dir / "plan.md").read_text(encoding="utf-8")
        self.assertIn("| In-Tree Code Review | graph:all-inventory-edges | spawn | frontier | D01 |", plan_text)
        self.assertTrue((review_dir / "packets" / "ICR-code.md").is_file())
        self.assertTrue((review_dir / "briefs" / "ICRR.md").is_file())
        self.assertTrue((review_dir / "briefs" / "ICR.md").is_file())

        # Verify validate-worker-artifact.py accepts non-empty internal-review-raw.md
        raw_md = review_dir / "internal-review-raw.md"
        raw_md.write_text(
            "## Evaluated Capability Groups And Rules\n- magic-call-rule\n\n"
            "## Findings\n\n### [P1] Unchecked MagicDangerCall\n"
            "**File:** `net/foo.cc:2`\n**Rule:** `general/check-magic-call`\n",
            encoding="utf-8",
        )
        res_val = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_WORKER_SCRIPT),
                str(review_dir),
                str(raw_md),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_val.returncode, 0, msg=res_val.stderr)

    def test_validate_plan_and_collection_coverage_for_icr(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "validate_review_dir", VALIDATE_REVIEW_DIR_SCRIPT
        )
        assert spec and spec.loader
        vrd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vrd)

        review_dir = self.tmpdir / "review_val"
        (review_dir / "indexes").mkdir(parents=True)
        (review_dir / "ledger").mkdir(parents=True)
        (review_dir / "briefs").mkdir(parents=True)
        (review_dir / "indexes" / "topology.tsv").write_text(
            "edge\tkind\tsource\ttarget\tevidence\tstatus\n"
            "E-CALL-1\tcall\tS1\tMagicDangerCall\tnet/foo.cc:2\topen\n",
            encoding="utf-8",
        )
        (review_dir / "profile.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "topology": {
                        "policy": "evidence-graph-v1",
                        "collapsed": False,
                    },
                    "internal_code_review": {"available": True},
                }
            ),
            encoding="utf-8",
        )
        plan_rows_missing_icr = [
            {
                "roster entry": "Generalist Semantic And State Discovery",
                "scope": "graph:all-inventory-edges",
                "status": "spawn",
                "tier": "frontier",
                "batch": "D01",
                "subagent": "—",
                "outcome": "—",
            },
            {
                "roster entry": "Generalist Adversarial And Integration Discovery",
                "scope": "graph:all-inventory-edges",
                "status": "spawn",
                "tier": "frontier",
                "batch": "D01",
                "subagent": "—",
                "outcome": "—",
            },
        ]
        rep1 = vrd.Report()
        vrd.validate_plan(review_dir, {}, plan_rows_missing_icr, True, rep1)
        self.assertTrue(
            any("plan.md omits roster entry: In-Tree Code Review" in e for e in rep1.errors),
            msg=str(rep1.errors),
        )

        plan_rows_with_icr = plan_rows_missing_icr + [
            {
                "roster entry": "In-Tree Code Review",
                "scope": "graph:all-inventory-edges",
                "status": "spawn",
                "tier": "frontier",
                "batch": "D01",
                "subagent": "—",
                "outcome": "—",
            }
        ]
        rep2 = vrd.Report()
        vrd.validate_plan(review_dir, {}, plan_rows_with_icr, True, rep2)
        self.assertEqual(rep2.errors, [])


if __name__ == "__main__":
    unittest.main()
