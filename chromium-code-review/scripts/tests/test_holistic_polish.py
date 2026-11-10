"""Tests for the always-run schema-3 Holistic-and-polish thread (`HOL`) and
the test-hygiene mechanical leads."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
INITIAL_PLAN_SCRIPT = SCRIPT_DIR / "build-initial-plan.py"
MECHANICAL_LEADS_SCRIPT = SCRIPT_DIR / "mechanical-leads.sh"
VALIDATE_REVIEW_DIR_SCRIPT = SCRIPT_DIR / "validate-review-dir.py"

SPEC = importlib.util.spec_from_file_location(
    "validate_review_dir_hol", VALIDATE_REVIEW_DIR_SCRIPT
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

HOL = "Holistic-and-polish thread"


def row(entry: str, scope: str, status: str = "spawn") -> dict[str, str]:
    return {
        "roster entry": entry,
        "scope": scope,
        "status": status,
        "tier": "frontier",
        "batch": "D01",
        "subagent": "—",
        "outcome": "—",
    }


GENERALISTS = [
    row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
    row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
]


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


class HolisticPlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="hol-plan-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "indexes").mkdir()
        (self.root / "indexes" / "topology.tsv").write_text(
            "edge\tcandidate\nE-A\t-\n", encoding="utf-8"
        )

    def write_profile(self, **topology: object) -> None:
        (self.root / "profile.json").write_text(
            json.dumps({
                "schema_version": 3,
                "topology": {"policy": "evidence-graph-v1", **topology},
            }),
            encoding="utf-8",
        )

    def validate(self, rows: list[dict[str, str]]) -> list[str]:
        report = VALIDATOR.Report()
        VALIDATOR.validate_plan(self.root, {}, rows, True, report)
        return report.errors

    def test_missing_holistic_row_is_rejected_when_required(self) -> None:
        self.write_profile(holistic_polish=True, collapsed=False)
        errors = self.validate(list(GENERALISTS))
        self.assertTrue(
            any(f"plan.md omits roster entry: {HOL}" in e for e in errors), errors
        )

    def test_holistic_row_with_all_edges_scope_is_accepted(self) -> None:
        self.write_profile(holistic_polish=True, collapsed=False)
        rows = GENERALISTS + [row(HOL, "graph:all-inventory-edges")]
        self.assertEqual([], self.validate(rows))

    def test_holistic_row_has_standard_floor(self) -> None:
        self.write_profile(holistic_polish=True, collapsed=False)
        standard = dict(row(HOL, "graph:all-inventory-edges"), tier="standard")
        self.assertEqual([], self.validate(GENERALISTS + [standard]))
        mechanical = dict(standard, tier="mechanical")
        self.assertTrue(self.validate(GENERALISTS + [mechanical]))

    def test_holistic_row_must_spawn(self) -> None:
        self.write_profile(holistic_polish=True, collapsed=False)
        rows = GENERALISTS + [
            row(HOL, "graph:all-inventory-edges",
                status="not applicable — trigger absence proved by T1")
        ]
        errors = self.validate(rows)
        self.assertTrue(
            any(f"requires a spawned {HOL} row" in e for e in errors), errors
        )

    def test_not_required_for_legacy_or_collapsed_profiles(self) -> None:
        self.write_profile()
        self.assertEqual([], self.validate(list(GENERALISTS)))
        self.write_profile(holistic_polish=True, collapsed=True)
        self.assertEqual([], self.validate(list(GENERALISTS)))


class HolisticInitialPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="hol-initial-"))
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.repo = self.tmpdir / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test User")
        (self.repo / "net").mkdir()
        (self.repo / "net" / "foo.cc").write_text("int Foo() { return 0; }\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "base")
        self.parent_sha = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "net" / "foo.cc").write_text("int Foo() { return 1; }\n")
        (self.repo / "net" / "foo_unittest.cc").write_text(
            '#include "testing/gtest/include/gtest/gtest.h"\n'
            "TEST(Foo, Bar) {\n"
            "  std::vector<int> v;\n"
            "  auto w = MakeThing();\n"
            "  auto u = std::make_unique<int>(1);\n"
            "  EXPECT_TRUE(v.empty());\n"
            "  EXPECT_EQ(v.size(), 0u);\n"
            "  EXPECT_THAT(v, testing::IsEmpty());\n"
            "  EXPECT_EQ(net::OK, Foo());\n"
            "}\n"
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "change")
        self.rev_sha = git(self.repo, "rev-parse", "HEAD")

    def test_initial_plan_emits_holistic_row_and_brief(self) -> None:
        review_dir = self.tmpdir / "review"
        (review_dir / "indexes").mkdir(parents=True)
        (review_dir / "pin.md").write_text(
            "# CL 999999 — patchset 1 pin\n\n"
            f"- Revision SHA: {self.rev_sha}\n"
            f"- Parent SHA: {self.parent_sha}\n"
            f"- Worktree: {self.repo}\n",
            encoding="utf-8",
        )
        (review_dir / "profile.json").write_text(json.dumps({
            "schema_version": 3,
            "effort": "standard",
            "initial_plan_fast_path_eligible": True,
            "topology": {
                "policy": "evidence-graph-v1",
                "collapsed": False,
                "holistic_polish": True,
            },
            "pin": {
                "revision_sha": self.rev_sha,
                "parent_sha": self.parent_sha,
                "worktree": str(self.repo),
            },
            "files": [{"path": "net/foo.cc", "status": "M", "changed_lines": 2}],
        }), encoding="utf-8")
        (review_dir / "indexes" / "inventory.tsv").write_text(
            "kind\tid\tshard\tfile\tsymbol\thunks\tsummary\n"
            "surface\tS1\troot\tnet/foo.cc\tFoo\tH1\tReturns 1\n",
            encoding="utf-8",
        )
        (review_dir / "indexes" / "topology.tsv").write_text(
            "edge\tkind\tsource\ttarget\tevidence\tstatus\n"
            "E-CALL-1\tcall\tS1\tFoo\tnet/foo.cc:1\topen\n",
            encoding="utf-8",
        )
        (review_dir / "inventory.md").write_text("# Inventory\n", encoding="utf-8")
        (review_dir / "mechanical-leads.md").write_text("# leads\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(INITIAL_PLAN_SCRIPT), str(review_dir),
             "--worktree", str(self.repo)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        plan_text = (review_dir / "plan.md").read_text(encoding="utf-8")
        self.assertIn(
            f"| {HOL} | graph:all-inventory-edges | spawn | standard | D01 |",
            plan_text,
        )
        brief = (review_dir / "briefs" / "HOL.md").read_text(encoding="utf-8")
        self.assertIn("Holistic-and-polish Requirements", brief)
        self.assertIn("changed-lines-polish.md", brief)
        self.assertIn("mechanical-leads.md", brief)

    def test_mechanical_leads_flag_test_hygiene(self) -> None:
        result = subprocess.run(
            ["bash", str(MECHANICAL_LEADS_SCRIPT), self.parent_sha, self.rev_sha,
             str(self.repo)],
            capture_output=True, text=True,
        )
        self.assertIn(result.returncode, (0, 2), msg=result.stderr)
        out = result.stdout
        self.assertNotIn("command not found", result.stderr)
        auto_section = out.split("## Added auto declarations", 1)[1].split("\n## ", 1)[0]
        self.assertIn("auto w = MakeThing()", auto_section)
        self.assertNotIn("std::make_unique<int>", auto_section)
        bool_section = out.split("## Boolean-collapsing test assertions", 1)[1].split("\n## ", 1)[0]
        self.assertIn("EXPECT_TRUE(v.empty())", bool_section)
        self.assertIn("EXPECT_EQ(v.size(), 0u)", bool_section)
        include_section = out.split("without a direct include", 1)[1].split("\n## ", 1)[0]
        self.assertIn("testing/gmock/include/gmock/gmock.h", include_section)
        self.assertIn("net/base/net_errors.h", include_section)


if __name__ == "__main__":
    unittest.main()
