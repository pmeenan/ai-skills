#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for remote_measure script generation, quoting, and result discovery."""

import argparse
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

import remote_measure as rm


def make_args(**overrides):
    defaults = dict(
        mode="ab",
        remote_src="/home/user/src/chromium/src",
        feature="Speedometer3Optimizations",
        blocks=5,
        stories="all",
        seed=42,
        repetitions=2,
        enable_features=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


SHA_A = "a" * 40
SHA_B = "b" * 40


class ScriptGenerationTest(unittest.TestCase):
    def test_ab_mode(self):
        script = rm.build_and_run_script(make_args(), SHA_A)
        self.assertIn(f"git checkout --quiet --detach {SHA_A}", script)
        self.assertIn("autoninja -C out/perf chrome", script)
        self.assertIn("--feature=Speedometer3Optimizations", script)
        self.assertIn("run_ab_benchmark.py", script)
        self.assertNotIn("--aa", script)

    def test_aa_mode(self):
        script = rm.build_and_run_script(make_args(mode="aa"), SHA_A)
        self.assertIn("--aa", script)
        self.assertNotIn("--feature", script)

    def test_ab2_mode_builds_both_arms(self):
        script = rm.build_and_run_script(make_args(mode="ab2"), SHA_A, SHA_B)
        self.assertIn(f"git checkout --quiet --detach {SHA_A}", script)
        self.assertIn(f"git checkout --quiet --detach {SHA_B}", script)
        self.assertIn("gn gen out/perf_a", script)
        self.assertIn("gn gen out/perf_b", script)
        self.assertIn("--browser-a=out/perf_a/chrome", script)
        self.assertIn("--browser-b=out/perf_b/chrome", script)

    def test_ab2_common_features_applied_to_both_arms(self):
        script = rm.build_and_run_script(
            make_args(mode="ab2", enable_features="Speedometer3Optimizations"),
            SHA_A, SHA_B)
        bench_line = [l for l in script.splitlines() if "run_ab_benchmark" in l][0]
        self.assertIn("--enable-features=Speedometer3Optimizations", bench_line)

    def test_aa_common_features(self):
        script = rm.build_and_run_script(
            make_args(mode="aa", enable_features="Speedometer3Optimizations"), SHA_A)
        bench_line = [l for l in script.splitlines() if "run_ab_benchmark" in l][0]
        self.assertIn("--enable-features=Speedometer3Optimizations", bench_line)

    def test_ab_mode_never_gets_common_features(self):
        script = rm.build_and_run_script(
            make_args(mode="ab", enable_features="ShouldNotAppear"), SHA_A)
        bench_line = [l for l in script.splitlines() if "run_ab_benchmark" in l][0]
        self.assertNotIn("ShouldNotAppear", bench_line)

    def test_profile_mode(self):
        script = rm.build_and_run_script(
            make_args(mode="profile", enable_features="Speedometer3Optimizations"),
            SHA_A,
        )
        self.assertIn("run_cycle_benchmark.py", script)
        self.assertIn("--enable-features=Speedometer3Optimizations", script)
        self.assertIn("PROFILE_EXIT_CODE", script)

    def test_profile_mode_baseline_empty_features(self):
        script = rm.build_and_run_script(make_args(mode="profile"), SHA_A)
        self.assertIn("--enable-features=''", script)

    def test_dirty_tree_guard_precedes_checkout(self):
        script = rm.build_and_run_script(make_args(), SHA_A)
        self.assertLess(script.index("REMOTE TREE HAS TRACKED"),
                        script.index("git checkout"))
        self.assertIn(f"exit {rm.REMOTE_DIRTY_EXIT}", script)


class QuotingTest(unittest.TestCase):
    def test_metacharacters_are_quoted(self):
        evil = "all; rm -rf $HOME"
        script = rm.build_and_run_script(make_args(stories=evil), SHA_A)
        self.assertIn(f"--stories={shlex.quote(evil)}", script)
        # The unquoted injection must not appear anywhere.
        self.assertNotIn("--stories=all; rm", script)

    def test_remote_src_with_spaces(self):
        src = "/home/user/my src/chromium"
        script = rm.build_and_run_script(make_args(remote_src=src), SHA_A)
        self.assertIn(f"cd {shlex.quote(src)}", script)

    def test_feature_quoted(self):
        evil = "Flag`whoami`"
        script = rm.build_and_run_script(make_args(feature=evil), SHA_A)
        self.assertIn(shlex.quote(evil), script)
        self.assertNotIn(f"--feature={evil}\n", script)

    def test_numeric_args_coerced(self):
        script = rm.build_and_run_script(make_args(blocks="7", seed="9"), SHA_A)
        self.assertIn("--blocks=7", script)
        self.assertIn("--seed=9", script)


class ResultDiscoveryTest(unittest.TestCase):
    def test_parse_remote_results_dir(self):
        stdout = (
            "ninja: Entering directory `out/perf'\n"
            " FULL CHROME PROCESS TREE PERF SAMPLING (-k mono)\n"
            " Output Dir  : scratch/results_perf_sampling_ab12cd\n"
        )
        self.assertEqual("scratch/results_perf_sampling_ab12cd",
                         rm.parse_remote_results_dir(stdout))

    def test_parse_missing_results_dir(self):
        self.assertIsNone(rm.parse_remote_results_dir("no dir here"))

    def test_profile_summary_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            full = out / "analysis" / "full"
            full.mkdir(parents=True)
            (full / "candidate_frontier.md").write_text("x")
            (full / "candidate_frontier.json").write_text("{}")
            (full / "opportunity_trees.txt").write_text("x")
            paths = rm.profile_summary_paths(out)
            self.assertEqual(
                {"full_candidate_frontier", "full_candidate_frontier_json",
                 "full_opportunity_trees"},
                set(paths),
            )


def make_skill_tree(root, content="pass\n", symlinked=False):
    """Create SKILL_DIRS under root; optionally as symlinks to real dirs."""
    for i, skill_dir in enumerate(rm.SKILL_DIRS):
        if symlinked:
            real = root / f"real-{i}" / "scripts"
            real.mkdir(parents=True)
            (real / "tool.py").write_text(content)
            link = root / skill_dir
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(real.parent)
            target = real
        else:
            target = root / skill_dir / "scripts"
            target.mkdir(parents=True)
            (target / "tool.py").write_text(content)
        cache = target / "__pycache__"
        cache.mkdir()
        (cache / "tool.cpython-312.pyc").write_bytes(b"\x00")


class SkillsDigestTest(unittest.TestCase):
    def test_symlinked_layout_matches_real_layout(self):
        # The Chromium checkout symlinks .agents/skills/* elsewhere; the
        # digest must see through that to the file contents.
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            make_skill_tree(pathlib.Path(a), symlinked=False)
            make_skill_tree(pathlib.Path(b), symlinked=True)
            self.assertEqual(
                rm.skills_digest(pathlib.Path(a)), rm.skills_digest(pathlib.Path(b))
            )

    def test_digest_tracks_content(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            make_skill_tree(pathlib.Path(a), content="v1\n")
            make_skill_tree(pathlib.Path(b), content="v2\n")
            self.assertNotEqual(
                rm.skills_digest(pathlib.Path(a)), rm.skills_digest(pathlib.Path(b))
            )

    def test_shell_pipeline_matches_python(self):
        # The remote check recomputes the digest with the shell pipeline; the
        # two implementations must agree, including through symlinks.
        for symlinked in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                make_skill_tree(root, symlinked=symlinked)
                shell = subprocess.run(
                    ["bash", "-c", rm.digest_shell_command()],
                    cwd=root, capture_output=True, text=True, check=True,
                ).stdout.strip()
                self.assertEqual(rm.skills_digest(root), shell,
                                 f"mismatch (symlinked={symlinked})")

    def test_script_includes_sync_gate(self):
        script = rm.build_and_run_script(make_args(), SHA_A,
                                         expected_digest="d" * 64)
        self.assertIn("d" * 64, script)
        self.assertIn(f"exit {rm.SKILLS_SYNC_EXIT}", script)
        # The sync gate must run before anything mutates the remote tree.
        self.assertLess(script.index(f"exit {rm.SKILLS_SYNC_EXIT}"),
                        script.index("git checkout"))


class SendStdinTest(unittest.TestCase):
    def test_broken_pipe_does_not_mask_exit_code(self):
        # Peer exits immediately without reading; a large write hits EPIPE.
        proc = subprocess.Popen(["/bin/false"], stdin=subprocess.PIPE)
        rm.send_stdin(proc, b"x" * (1 << 20))
        self.assertEqual(1, proc.wait())
        # stdin must be closed even on the exception path (no fd leak).
        self.assertTrue(proc.stdin.closed)


class SyncGateShellTest(unittest.TestCase):
    """The remote sync gate must honor the exit-5 contract in every failure
    mode, including missing directories under `set -euo pipefail`."""

    def run_gate(self, cwd, digest):
        script = "\n".join(["set -euo pipefail"] + rm.sync_gate_lines(digest))
        return subprocess.run(["bash", "-c", script], cwd=cwd,
                              capture_output=True, text=True).returncode

    def test_missing_directories_exit_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rm.SKILLS_SYNC_EXIT, self.run_gate(tmp, "d" * 64))

    def test_wrong_digest_exits_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill_tree(pathlib.Path(tmp))
            self.assertEqual(rm.SKILLS_SYNC_EXIT, self.run_gate(tmp, "d" * 64))

    def test_matching_digest_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_skill_tree(root)
            self.assertEqual(0, self.run_gate(tmp, rm.skills_digest(root)))

    def test_missing_local_directory_is_a_hard_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                rm.skills_digest(pathlib.Path(tmp))


class LedgerDefaultsTest(unittest.TestCase):
    ENV_KEYS = ("SP3_CAMPAIGN_DIR", "SP3_REMOTE_HOST", "SP3_REMOTE_SRC")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.campaign_dir = pathlib.Path(self.tmp.name) / "camp"
        self.campaign_dir.mkdir()
        self.saved_env = {k: os.environ.pop(k, None) for k in self.ENV_KEYS}
        os.environ["SP3_CAMPAIGN_DIR"] = str(self.campaign_dir)

    def tearDown(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def write_ledger(self, text):
        (self.campaign_dir / "ledger.json").write_text(text)

    def test_absent_ledger_falls_back(self):
        self.assertEqual((None, None), rm.ledger_remote_defaults())
        host, src = rm.resolve_remote(None, None, pathlib.Path("/repo"))
        self.assertEqual(("linux", "/repo"), (host, src))

    def test_valid_ledger_supplies_defaults(self):
        self.write_ledger(
            '{"config": {"remote_host": "perfbox", "remote_src": "/srv/src"}}')
        self.assertEqual(("perfbox", "/srv/src"), rm.ledger_remote_defaults())
        self.assertEqual(
            ("perfbox", "/srv/src"),
            rm.resolve_remote(None, None, pathlib.Path("/repo")))

    def test_malformed_ledger_fails_loudly(self):
        self.write_ledger("{not json")
        with self.assertRaises(SystemExit):
            rm.ledger_remote_defaults()

    def test_ledger_missing_config_fails_loudly(self):
        self.write_ledger('{"opportunities": []}')
        with self.assertRaises(SystemExit):
            rm.ledger_remote_defaults()

    def test_explicit_args_bypass_broken_ledger(self):
        self.write_ledger("{not json")
        self.assertEqual(
            ("h", "/s"), rm.resolve_remote("h", "/s", pathlib.Path("/repo")))

    def test_env_beats_ledger(self):
        self.write_ledger(
            '{"config": {"remote_host": "perfbox", "remote_src": "/srv/src"}}')
        os.environ["SP3_REMOTE_HOST"] = "envhost"
        host, src = rm.resolve_remote(None, None, pathlib.Path("/repo"))
        self.assertEqual("envhost", host)
        self.assertEqual("/srv/src", src)


class StagedCommitTest(unittest.TestCase):
    def test_staged_commit_matches_index_and_keeps_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp)

            def git(*argv):
                return subprocess.run(
                    ["git", "-C", str(repo)] + list(argv),
                    check=True, capture_output=True, text=True,
                    env={**os.environ,
                         "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e.c",
                         "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e.c"},
                ).stdout.strip()

            git("init", "-q")
            (repo / "f.txt").write_text("base\n")
            git("add", "-A")
            git("commit", "-qm", "base")
            head = git("rev-parse", "HEAD")
            (repo / "f.txt").write_text("candidate\n")
            git("add", "-A")
            staged_tree = git("write-tree")

            sha = rm.staged_commit_sha(repo)
            self.assertEqual(staged_tree, git("rev-parse", f"{sha}^{{tree}}"))
            self.assertEqual(head, git("rev-parse", f"{sha}^"))
            # HEAD must not move and the branch must not gain the commit.
            self.assertEqual(head, git("rev-parse", "HEAD"))

            # Unstaged changes make the index non-authoritative: hard error.
            (repo / "g.txt").write_text("untracked\n")
            with self.assertRaises(SystemExit):
                rm.staged_commit_sha(repo)
            # The explicit escape hatch proceeds, still from the index only.
            sha2 = rm.staged_commit_sha(repo, allow_unstaged=True)
            self.assertEqual(staged_tree, git("rev-parse", f"{sha2}^{{tree}}"))


class OutDirTest(unittest.TestCase):
    def test_default_out_dirs_are_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            a = rm.default_out_dir(root, "ab")
            b = rm.default_out_dir(root, "ab")
            self.assertNotEqual(a, b)
            self.assertTrue(a.is_dir() and b.is_dir())
            self.assertEqual(root / "scratch", a.parent)


if __name__ == "__main__":
    unittest.main()
