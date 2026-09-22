#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
BUILD_BRIEF = SCRIPTS / "build-phase-brief.py"
PROFILE = SCRIPTS / "profile-review.py"
REFERENCES = SCRIPTS.parent / "references"

OPEN = "\u27e8"
CLOSE = "\u27e9"
PATHSPEC_LONG = (
    OPEN + "explicit path list including both sides of renames/deletions" + CLOSE
)


def placeholder(name: str) -> str:
    return OPEN + name + CLOSE


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=False
    )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin"})
    return result.stdout.strip()


def load_module(name: str, path: Path):
    """Import a module by path so hyphenated helpers can be inspected."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildPhaseBriefTests(unittest.TestCase):
    """The generator must never hand a placeholder to a worker."""

    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="phase-brief-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.review = root / "review"
        self.skill = self.review / "skill-snapshot"
        self.worktree = root / "worktree"
        self.worktree.mkdir(parents=True)
        (self.skill / "references" / "worker" / "phase-briefs").mkdir(parents=True)
        (self.review / "pin.md").write_text(
            "# CL 8400959 — patchset 2 pin\n"
            "- Revision SHA: " + "a" * 40 + "\n"
            "- Parent SHA: " + "b" * 40 + "\n"
            f"- Worktree: {self.worktree}\n",
            encoding="utf-8",
        )
        self.write_header(
            "You are reviewing CL " + placeholder("CL") + " patchset "
            + placeholder("PS") + " as " + placeholder("work-id")
            + " attempt " + placeholder("attempt") + ".\n"
            "Run commands with --cwd "
            + placeholder("worktree-or-current-directory") + " -- "
            + placeholder("command...") + ".\n"
            "Return \"partial — remaining: "
            + placeholder("explicit list of unprocessed scope") + "\".\n"
        )

    def write_header(self, body: str) -> None:
        (self.skill / "references" / "worker" / "phase-briefs"
         / "common-header.md").write_text(
            "# Common Header\n\n```text\n" + body + "```\n", encoding="utf-8"
        )

    def write_phase_briefs(self, body: str, *, tier: str = "standard") -> None:
        (self.skill / "references" / "phase-briefs.md").write_text(
            "# Phase Briefs\n\n"
            "## Brief — Inventory (Phase 1, unsharded)\n\n"
            f"Tier: `{tier}` (Model Tiers in `references/scaling-and-indexes.md`).\n\n"
            "```text\n" + body + "```\n\n"
            "## Brief — Planner (Phase 3)\n\n"
            "Tier: `frontier`.\n\n"
            "```text\nScope: nothing.\n```\n",
            encoding="utf-8",
        )

    def standard_body(self) -> str:
        return (
            "Scope: every changed file in the pinned diff.\n\n"
            "Pinned range/pathspec: parent " + placeholder("parent-sha")
            + ", revision " + placeholder("sha") + ", exact pathspec "
            + PATHSPEC_LONG + ". Use only `git diff "
            + placeholder("parent-sha") + " " + placeholder("sha") + " -- "
            + placeholder("pathspec") + "`.\n\n"
            "Inputs: " + placeholder("review-dir") + "/profile.json.\n\n"
            "Procedure: read " + placeholder("skill-dir")
            + "/references/worker/inventory.md, then execute Pass 1.\n\n"
            "Deliverable: " + placeholder("review-dir")
            + "/inventory.md — changed surfaces.\n\n"
            "Return: one line.\n"
        )

    def build(self, *extra: str, output: Path | None = None):
        target = output if output is not None else self.review / "briefs" / "INV.md"
        return run(
            str(BUILD_BRIEF), str(self.review), "INV", "Inventory",
            "--output", str(target), *extra,
        )

    def test_generated_verification_planner_extracts_command_executable(self) -> None:
        shutil.copytree(SCRIPTS.parent, self.skill, dirs_exist_ok=True)
        output = self.review / "briefs" / "VPLAN.md"
        result = run(str(BUILD_BRIEF), str(self.review), "VPLAN", "Verification Planner",
                     "--output", str(output), "--set", "batch=001", "--set", "n=1")
        self.assertEqual(0, result.returncode, result.stderr)
        validator = load_module("quoted_command_validator", SCRIPTS / "validate-review-dir.py")
        inputs = validator.named_brief_inputs(output)
        executable = self.skill / "scripts" / "build-batch-briefs.py"
        self.assertIn(executable, inputs)
        self.assertFalse(any(" --phase verification" in str(path) for path in inputs))

    def test_pathspec_fills_both_placeholder_spellings(self) -> None:
        self.write_phase_briefs(self.standard_body())
        result = self.build("--pathspec", "net/a.cc net/a.h")
        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.review / "briefs" / "INV.md").read_text(encoding="utf-8")
        self.assertIn("exact pathspec net/a.cc net/a.h.", text)
        self.assertIn("-- net/a.cc net/a.h`", text)
        self.assertNotIn(PATHSPEC_LONG, text)
        self.assertNotIn(placeholder("pathspec"), text)

    def test_set_substitutes_an_arbitrary_placeholder(self) -> None:
        self.write_phase_briefs(
            self.standard_body() + "\nBatch: " + placeholder("batch") + "\n"
        )
        result = self.build(
            "--pathspec", "net/a.cc", "--set", "batch=CH-2"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.review / "briefs" / "INV.md").read_text(encoding="utf-8")
        self.assertIn("Batch: CH-2", text)

    def test_unsubstituted_placeholder_refuses_and_names_the_flag(self) -> None:
        self.write_phase_briefs(
            self.standard_body() + "\nBatch: " + placeholder("batch") + "\n"
        )
        result = self.build()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("placeholder(s) are still unsubstituted", result.stderr)
        self.assertIn("--pathspec", result.stderr)
        self.assertIn("--set batch=VALUE", result.stderr)
        self.assertIn("--allow-placeholders", result.stderr)
        self.assertFalse((self.review / "briefs" / "INV.md").exists())

    def test_runtime_placeholders_are_not_treated_as_unsubstituted(self) -> None:
        self.write_phase_briefs(self.standard_body())
        result = self.build("--pathspec", "net/a.cc")
        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.review / "briefs" / "INV.md").read_text(encoding="utf-8")
        self.assertIn(placeholder("command..."), text)

    def test_allow_placeholders_is_an_explicit_escape_hatch(self) -> None:
        self.write_phase_briefs(
            self.standard_body() + "\nBatch: " + placeholder("batch") + "\n"
        )
        result = self.build("--pathspec", "net/a.cc", "--allow-placeholders")
        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.review / "briefs" / "INV.md").read_text(encoding="utf-8")
        self.assertIn("Batch: " + placeholder("batch"), text)

    def test_seal_command_matches_the_validator_input_extraction(self) -> None:
        self.write_phase_briefs(self.standard_body())
        (self.review / "profile.json").write_text("{}\n", encoding="utf-8")
        (self.skill / "references" / "worker" / "inventory.md").write_text(
            "reference\n", encoding="utf-8")
        result = self.build("--pathspec", "net/a.cc")
        self.assertEqual(0, result.returncode, result.stderr)
        command = result.stdout.splitlines()[-1]
        brief = self.review / "briefs" / "INV.md"
        self.assertIn(f"--phase 1 --work-id INV --attempt 1", command)
        self.assertIn("--tier standard", command)
        self.assertIn(f"--brief {brief}", command)
        self.assertIn(f"--artifact {self.review}/inventory.md", command)
        self.assertIn(f"--input control={self.review}/profile.json", command)
        self.assertIn(
            f"--input reference={self.skill}/references/worker/inventory.md",
            command,
        )
        self.assertIn("seal-work-unit.py", command)
        # The deliverable must never be declared as an input.
        self.assertNotIn(f"--input control={self.review}/inventory.md", command)
        module = load_module("brief_inputs_check", SCRIPTS / "brief_inputs.py")
        for path in module.named_brief_inputs(brief):
            self.assertIn(f"={path}", command)

    def test_seal_command_reports_which_source_supplied_each_field(self) -> None:
        self.write_phase_briefs(self.standard_body(), tier="mechanical")
        result = self.build("--pathspec", "net/a.cc")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("tier from the brief Tier: line", result.stdout)
        self.assertIn("--tier mechanical", result.stdout)
        result = self.build("--pathspec", "net/a.cc", "--tier", "frontier")
        self.assertIn("tier from --tier", result.stdout)
        self.assertIn("--tier frontier", result.stdout)

    def test_no_emit_seal_command_suppresses_the_command(self) -> None:
        self.write_phase_briefs(self.standard_body())
        result = self.build("--pathspec", "net/a.cc", "--no-emit-seal-command")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("seal-work-unit.py", result.stdout)

    def test_unknown_brief_name_lists_the_available_headings(self) -> None:
        self.write_phase_briefs(self.standard_body())
        result = run(
            str(BUILD_BRIEF), str(self.review), "INV", "Nonexistent Brief",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Could not find template", result.stderr)
        self.assertIn("Brief — Inventory (Phase 1, unsharded)", result.stderr)
        self.assertIn("Brief — Planner (Phase 3)", result.stderr)

    def test_real_inventory_brief_has_no_unsubstituted_placeholders(self) -> None:
        shutil.rmtree(self.skill / "references")
        shutil.copytree(REFERENCES, self.skill / "references")
        result = self.build(
            "--pathspec", "net/socket/socket.cc net/socket/socket.h"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.review / "briefs" / "INV.md").read_text(encoding="utf-8")
        self.assertNotIn(PATHSPEC_LONG, text)
        self.assertIn("--tier standard", result.stdout)
        self.assertIn(f"--artifact {self.review}/inventory.md", result.stdout)


class NamedBriefInputsAgreementTests(unittest.TestCase):
    """`brief_inputs.py` duplicates the gate's rule; prove it has not drifted.

    `validate-review-dir.py` is not modified by this change, so the two
    implementations are separate copies. This corpus exercises every branch
    that distinguishes them.
    """

    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="brief-inputs-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.root = root
        (root / "some-dir").mkdir()
        self.shared = load_module("brief_inputs_shared", SCRIPTS / "brief_inputs.py")
        self.validator = load_module(
            "validate_review_dir_under_test", SCRIPTS / "validate-review-dir.py"
        )

    def corpus(self) -> dict[str, str]:
        root = self.root
        return {
            "quoted-and-bare": (
                f"Inputs: `{root}/quoted.md` and {root}/bare.md\n"
                "Return: one line.\n"
            ),
            "directory-excluded": (
                f"Inputs: {root}/some-dir and `{root}/some-dir`\n"
            ),
            "trailing-slash-excluded": (
                f"Inputs: `{root}/packets/` and {root}/cards/\n"
            ),
            "trailing-punctuation": (
                f"Inputs: {root}/one.md, {root}/two.md; ({root}/three.md).\n"
            ),
            "section-switch-stops-collection": (
                f"Inputs: {root}/kept.md\n"
                f"Rules: never read {root}/ignored.md\n"
            ),
            "procedure-counts-as-inputs": (
                f"Procedure: read {root}/procedure.md then stop.\n"
            ),
            "deliverable-subtracted": (
                f"Inputs: {root}/both.md\n"
                f"Deliverables: {root}/both.md and {root}/out.md\n"
            ),
            "deliverable-then-inputs": (
                f"Deliverable: {root}/out.md\n"
                f"Inputs: {root}/after.md\n"
            ),
            "unusual-characters": (
                f"Inputs: {root}/a+b@c%d=e:f-g.md\n"
            ),
            "relative-paths-ignored": (
                "Inputs: references/worker/index.md and ../escape.md\n"
            ),
            "case-insensitive-labels": (
                f"INPUTS: {root}/upper.md\n"
                f"deliverables: {root}/lower-out.md\n"
            ),
            "empty": "",
        }

    def test_implementations_agree_on_a_tricky_corpus(self) -> None:
        for name, text in self.corpus().items():
            with self.subTest(brief=name):
                brief = self.root / f"{name}.md"
                brief.write_text(text, encoding="utf-8")
                self.assertEqual(
                    self.validator.named_brief_inputs(brief),
                    self.shared.named_brief_inputs(brief),
                )

    def test_shared_source_is_byte_identical_to_the_gate(self) -> None:
        def body(path: Path) -> str:
            text = path.read_text(encoding="utf-8")
            start = text.index("def named_brief_inputs(brief: Path)")
            end = text.index("    return named_inputs - named_deliverables\n", start)
            return text[start:end]

        self.assertEqual(
            body(SCRIPTS / "validate-review-dir.py"),
            body(SCRIPTS / "brief_inputs.py"),
        )


class TrivialCodeEffortTests(unittest.TestCase):
    """A one-line code edit must not cost a full standard review."""

    def make_review(
        self, base: dict[str, str], changed: dict[str, str]
    ) -> Path:
        root = Path(tempfile.mkdtemp(prefix="trivial-code-"))
        self.addCleanup(shutil.rmtree, root, True)
        repo = root / "repo"
        review = root / "review"
        repo.mkdir()
        review.mkdir()
        git(repo, "init", "-q")
        for name, content in base.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        parent = git(repo, "rev-parse", "HEAD")
        for name, content in changed.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "change")
        revision = git(repo, "rev-parse", "HEAD")
        (review / "pin.md").write_text(
            f"- Revision SHA: {revision}\n- Parent SHA: {parent}\n"
            f"- Worktree: {repo} (rev-parse verified)\n",
            encoding="utf-8",
        )
        self.revision = revision
        return review

    def profile(self, review: Path) -> dict:
        result = run(str(PROFILE), str(review), "--stdout")
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def include_removal(self) -> Path:
        return self.make_review(
            {"components/example/widget.cc":
             "#include \"components/example/other.h\"\nint Value() { return 1; }\n"},
            {"components/example/widget.cc": "int Value() { return 1; }\n"},
        )

    def test_single_include_removal_is_trivial_code(self) -> None:
        profile = self.profile(self.include_removal())
        self.assertEqual("trivial-code", profile["effort"])
        self.assertEqual(
            ["all conservative trivial-code proofs passed"],
            profile["effort_reasons"],
        )
        self.assertTrue(profile["trivial_code_eligibility"]["eligible"])
        self.assertFalse(profile["micro_eligibility"]["eligible"])
        self.assertIn(
            "all files are documentation or non-executable metadata",
            profile["micro_eligibility"]["failed"],
        )

    def test_trivial_code_collapses_the_topology(self) -> None:
        profile = self.profile(self.include_removal())
        self.assertTrue(profile["topology"]["collapsed"])
        self.assertEqual(1, profile["topology"]["initial_generalists"])
        self.assertEqual(1, profile["topology"]["max_challenge_rounds"])

    def test_external_context_no_longer_blocks_the_fast_path(self) -> None:
        review = self.include_removal()
        (review / "detail.json").write_text(
            json.dumps({"revisions": {self.revision: {"commit": {
                "message": "Drop unused include\n\nBug: chromium:12345\n"}}}}),
            encoding="utf-8",
        )
        profile = self.profile(review)
        self.assertEqual("trivial-code", profile["effort"])
        self.assertGreater(profile["prior_context"]["external_context"]["count"], 0)
        self.assertTrue(profile["context_fast_path_eligible"])

    def test_specialist_trigger_forbids_the_fast_path(self) -> None:
        review = self.make_review(
            {"android/Foo.java": "class Foo {}\n"},
            {"android/Foo.java": "class Foo { int value = 1; }\n"},
        )
        profile = self.profile(review)
        self.assertEqual("standard", profile["effort"])
        self.assertIn(
            "no trigger-only specialist lenses",
            profile["trivial_code_eligibility"]["failed"],
        )
        self.assertIn(
            "trivial-code proof failed: no trigger-only specialist lenses",
            profile["effort_reasons"],
        )
        self.assertFalse(profile["context_fast_path_eligible"])
        self.assertNotIn("collapsed", profile["topology"])

    def test_high_risk_signal_forbids_the_fast_path(self) -> None:
        review = self.make_review(
            {"net/foo.cc": "void Run() {}\n"},
            {"net/foo.cc": "void Run() { PostTask(BindOnce(&Done)); }\n"},
        )
        profile = self.profile(review)
        self.assertEqual("high-risk", profile["effort"])
        self.assertFalse(profile["trivial_code_eligibility"]["eligible"])
        self.assertEqual([], profile["trivial_code_eligibility"]["proof"])
        self.assertFalse(profile["context_fast_path_eligible"])
        self.assertNotIn("collapsed", profile["topology"])

    def test_twenty_one_changed_lines_is_too_large_for_trivial_code(self) -> None:
        review = self.make_review(
            {"components/example/table.cc": "int kTable[] = {\n};\n"},
            {"components/example/table.cc":
             "int kTable[] = {\n" + "".join(f"  {n},\n" for n in range(21)) + "};\n"},
        )
        profile = self.profile(review)
        self.assertEqual("standard", profile["effort"])
        self.assertIn(
            "at most 20 changed lines",
            profile["trivial_code_eligibility"]["failed"],
        )

    def test_docs_only_change_still_reaches_micro(self) -> None:
        review = self.make_review(
            {"docs/readme.md": "old\n"}, {"docs/readme.md": "old\nnew\n"}
        )
        profile = self.profile(review)
        self.assertEqual("micro", profile["effort"])
        self.assertTrue(profile["micro_eligibility"]["eligible"])
        self.assertTrue(profile["trivial_code_eligibility"]["eligible"])
        self.assertTrue(profile["topology"]["collapsed"])


if __name__ == "__main__":
    unittest.main()
