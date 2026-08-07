#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for the campaign ledger state machine and STATUS.md generation."""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest

import campaign


class CampaignTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name) / "camp"
        # Run outside any git repo so commit verification is skipped.
        self.prev_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.assertEqual(0, self.run_cmd(
            "init", "--name", "test-campaign", "--target", "20",
            "--share-floor", "0.1"))

    def tearDown(self):
        os.chdir(self.prev_cwd)
        self.tmp.cleanup()

    def run_cmd(self, *argv):
        return campaign.main(["--dir", str(self.dir)] + list(argv))

    def ledger(self):
        with open(self.dir / "ledger.json") as f:
            return json.load(f)

    def status_text(self):
        with open(self.dir / "STATUS.md") as f:
            return f.read()

    def add_opp(self, anchor="StyleEngine::RecalcStyle subtree", share="0.6"):
        self.assertEqual(0, self.run_cmd("add", "--anchor", anchor, "--share", share))
        return self.ledger()["opportunities"][-1]["id"]

    def test_add_and_status(self):
        opp_id = self.add_opp()
        self.assertEqual(1, opp_id)
        text = self.status_text()
        self.assertIn("StyleEngine::RecalcStyle subtree", text)
        self.assertIn("Landed: 0/20", text)

    def test_full_lifecycle_gates(self):
        opp = self.add_opp()
        # Cannot skip straight to implementing.
        self.assertEqual(1, self.run_cmd("advance", "--opp", str(opp), "--to", "implementing"))
        # sized requires ceiling + evidence.
        self.assertEqual(1, self.run_cmd("advance", "--opp", str(opp), "--to", "sized"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "sized",
            "--ceiling", "0.4", "--evidence", "counter shows 12k avoidable recalcs"))
        self.assertEqual(0, self.run_cmd("advance", "--opp", str(opp), "--to", "implementing"))
        # review requires tests.
        self.assertEqual(1, self.run_cmd("advance", "--opp", str(opp), "--to", "review"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "review",
            "--tests", "blink_unittests StyleEngine*, wpt css/"))
        # landed blocked without both PASS verdicts.
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))
        self.assertEqual(0, self.run_cmd(
            "review", "--opp", str(opp), "--role", "skeptic", "--verdict", "PASS"))
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))
        self.assertEqual(0, self.run_cmd(
            "review", "--opp", str(opp), "--role", "adversary", "--verdict", "PASS"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))
        data = self.ledger()
        self.assertEqual("landed", data["opportunities"][0]["status"])
        self.assertIn("Landed: 1/20", self.status_text())

    def test_review_fail_and_rework(self):
        opp = self.add_opp()
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        self.run_cmd("review", "--opp", str(opp), "--role", "adversary",
                     "--verdict", "FAIL", "--notes", "event order change")
        # Rework path clears verdicts.
        self.assertEqual(0, self.run_cmd("advance", "--opp", str(opp), "--to", "implementing"))
        data = self.ledger()["opportunities"][0]
        self.assertEqual(1, data["rework_rounds"])
        self.assertEqual({}, data["reviews"])
        # Second review round: a stale FAIL cannot leak through.
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))

    def test_reject_park_reopen(self):
        opp = self.add_opp()
        self.assertEqual(0, self.run_cmd("reject", "--opp", str(opp), "--reason", "off critical path"))
        self.assertIn("off critical path", self.status_text())
        self.assertEqual(0, self.run_cmd("reopen", "--opp", str(opp)))
        self.assertEqual("candidate", self.ledger()["opportunities"][0]["status"])

    def test_review_only_in_review_state(self):
        opp = self.add_opp()
        self.assertEqual(1, self.run_cmd(
            "review", "--opp", str(opp), "--role", "skeptic", "--verdict", "PASS"))

    def test_checkpoint_and_next_ordering(self):
        self.add_opp(anchor="small", share="0.2")
        self.add_opp(anchor="large", share="0.9")
        self.assertEqual(0, self.run_cmd(
            "checkpoint", "--delta", "1.8", "--ci-low", "0.9", "--ci-high", "2.7"))
        text = self.status_text()
        self.assertIn("+1.80%", text)
        candidates = campaign.Ledger(self.dir).load().next_candidates(2)
        self.assertEqual("large", candidates[0]["anchor"])

    def test_squeeze_only_while_implementing(self):
        opp = self.add_opp()
        self.assertEqual(1, self.run_cmd("squeeze", "--opp", str(opp)))
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        self.assertEqual(0, self.run_cmd(
            "squeeze", "--opp", str(opp), "--note", "hoisted allocation"))
        self.assertEqual(0, self.run_cmd("squeeze", "--opp", str(opp)))
        self.assertEqual(2, self.ledger()["opportunities"][0]["squeeze_rounds"])

    def test_rework_limit_enforced(self):
        opp = self.add_opp()
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        for _ in range(2):
            self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
            self.assertEqual(0, self.run_cmd(
                "advance", "--opp", str(opp), "--to", "implementing"))
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        # Third rework round is blocked without the override.
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "implementing"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "implementing",
            "--override-rework-limit", "--notes", "reviewer error, justified"))

    def test_landed_is_terminal(self):
        opp = self.add_opp()
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        self.run_cmd("review", "--opp", str(opp), "--role", "skeptic", "--verdict", "PASS")
        self.run_cmd("review", "--opp", str(opp), "--role", "adversary", "--verdict", "PASS")
        self.run_cmd("advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef")
        self.assertEqual(1, self.run_cmd("reject", "--opp", str(opp), "--reason", "nope"))


class GitReviewVerificationTest(unittest.TestCase):
    """Landing must prove the commit is exactly the reviewed diff."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.dir = pathlib.Path(self.tmp.name) / "camp"
        self.prev_cwd = os.getcwd()
        os.chdir(self.repo)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        (self.repo / "f.txt").write_text("base\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.run_cmd("init", "--name", "gittest", "--branch", self.branch)
        self.run_cmd("add", "--anchor", "anchor", "--share", "0.5")
        self.run_cmd("advance", "--opp", "1", "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", "1", "--to", "implementing")

    def tearDown(self):
        os.chdir(self.prev_cwd)
        self.tmp.cleanup()

    def git(self, *argv):
        return subprocess.run(["git"] + list(argv), check=True,
                              capture_output=True, text=True).stdout.strip()

    def run_cmd(self, *argv):
        return campaign.main(["--dir", str(self.dir)] + list(argv))

    def enter_review_with(self, content, path="f.txt"):
        target = self.repo / path
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
        # The implementer stages the candidate before handing it to review.
        self.git("add", "-A")
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "review", "--tests", "unit"))

    def pass_reviews(self):
        self.run_cmd("review", "--opp", "1", "--role", "skeptic", "--verdict", "PASS")
        self.run_cmd("review", "--opp", "1", "--role", "adversary", "--verdict", "PASS")

    def test_matching_commit_lands(self):
        self.enter_review_with("optimized v1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))

    def test_tampered_content_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        # Content changes after review before committing.
        (self.repo / "f.txt").write_text("optimized v2 sneaky\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))
        # The escape hatch still works when explicitly requested.
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha,
            "--skip-review-verification"))

    def test_wrong_parent_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        (self.repo / "g.txt").write_text("unrelated\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "unrelated")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))

    def test_binary_tamper_is_rejected(self):
        # Binary replacement after review: a filtered-text diff digest would
        # miss this; the tree hash must not.
        self.enter_review_with(b"\x00\x01BINv1\x02", path="blob.bin")
        (self.repo / "blob.bin").write_bytes(b"\x00\x01BINv2\x02")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))

    def test_matching_but_non_head_commit_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        self.git("commit", "-qm", "opt")
        reviewed_sha = self.git("rev-parse", "HEAD")
        (self.repo / "g.txt").write_text("later work\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "later")
        self.pass_reviews()
        # Parent and tree both match, but the commit is no longer HEAD.
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", reviewed_sha))

    def test_unstaged_review_entry_is_blocked(self):
        (self.repo / "f.txt").write_text("unstaged change\n")
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "review", "--tests", "unit"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "review", "--tests", "unit",
            "--allow-unstaged"))

    def test_wrong_branch_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        self.git("checkout", "-qb", "side-branch")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))


if __name__ == "__main__":
    unittest.main()
