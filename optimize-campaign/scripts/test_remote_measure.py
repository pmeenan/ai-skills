#!/usr/bin/env python3
"""Tests for shared local and remote measurement."""
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for remote_measure script generation, quoting, and result discovery."""

import argparse
import json
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

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
        share_floor_pct=0.1,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


SHA_A = "a" * 40
SHA_B = "b" * 40


class ScriptGenerationTest(unittest.TestCase):
    def test_ab_mode(self):
        script = rm.build_and_run_script(make_args(), SHA_A)
        self.assertIn(f"git checkout --quiet --detach {SHA_A}", script)
        self.assertIn("autoninja -C out/release chrome", script)
        self.assertIn("--browser=out/release/chrome", script)
        self.assertIn("--required-build-role=release", script)
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
        self.assertIn("gn gen out/release_a", script)
        self.assertIn("gn gen out/release_b", script)
        self.assertIn("--browser-a=out/release_a/chrome", script)
        self.assertIn("--browser-b=out/release_b/chrome", script)

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
        self.assertIn("autoninja -C out/perf chrome", script)
        self.assertIn("--browser=out/perf/chrome", script)
        self.assertIn("--enable-features=Speedometer3Optimizations", script)
        self.assertIn("--min-share=0.001", script)
        self.assertIn("--min-marginal-share=0.001", script)
        self.assertIn("PROFILE_EXIT_CODE", script)

    def test_profile_mode_propagates_sub_point_one_percent_floor(self):
        script = rm.build_and_run_script(
            make_args(
                mode="profile",
                enable_features="Speedometer3Optimizations",
                share_floor_pct=0.05,
            ),
            SHA_A,
        )
        self.assertIn("--min-share=0.0005", script)
        self.assertIn("--min-marginal-share=0.0005", script)

    def test_profile_mode_baseline_empty_features(self):
        script = rm.build_and_run_script(make_args(mode="profile"), SHA_A)
        self.assertIn("--enable-features=''", script)

    def test_dirty_tree_guard_precedes_checkout(self):
        script = rm.build_and_run_script(make_args(), SHA_A)
        self.assertLess(script.index("REMOTE TREE HAS TRACKED"),
                        script.index("git checkout"))
        self.assertIn(f"exit {rm.REMOTE_DIRTY_EXIT}", script)

    def test_local_characterization_uses_existing_development_build(self):
        args = make_args(
            mode="aa",
            benchmark="jetstream3",
            benchmark_source="custom",
            benchmark_url=None,
            benchmark_payload_path=None,
            browser="out/Default/chrome",
            driver_path="out/Default/chromedriver",
            browser_a=None,
            browser_b=None,
            characterization=True,
            skip_build=True,
            iteration_count=4,
            worst_case_count=1,
        )
        script = rm.build_local_script(args, pathlib.Path("/chromium"), "a" * 64)
        self.assertNotIn("git checkout", script)
        self.assertNotIn("autoninja", script)
        self.assertIn("--required-build-role=development", script)
        self.assertIn("--benchmark=jetstream3", script)
        self.assertIn("--benchmark-source=custom", script)
        self.assertIn("--iteration-count=4", script)
        self.assertIn("--driver-path=out/Default/chromedriver", script)

    def test_tune_host_in_remote_script_enabled_by_default(self):
        script = rm.build_and_run_script(make_args(), SHA_A)
        self.assertIn('tune_benchmark_host.py" enable', script)
        self.assertIn("trap 'python3 \".agents/skills/optimize-campaign/scripts/tune_benchmark_host.py\" disable' EXIT", script)

    def test_display_policy_flows_to_runner_and_tuner(self):
        script = rm.build_and_run_script(
            make_args(display=":1", display_vt=9, viewport="1500x1000", gpu_clock_mhz=1365),
            SHA_A,
        )
        self.assertIn("--display=:1 --display-vt=9 --viewport=1500x1000", script)
        self.assertIn('tune_benchmark_host.py" enable --keep-aslr --vt 9 --gpu-clock-mhz 1365', script)
        paused = rm.build_and_run_script(
            make_args(display=":1", display_vt=9, viewport="1500x1000", pause_services=["ollama"]), SHA_A)
        self.assertIn("--pause-service ollama", paused)
        local = rm.build_local_script(
            make_args(mode="aa", display=":1", display_vt=9, viewport="1500x1000",
                      benchmark="speedometer3", benchmark_source="local",
                      benchmark_url=None, benchmark_payload_path=None,
                      driver_path=None, iteration_count=None, worst_case_count=None,
                      skip_build=True, browser="out/release/chrome",
                      characterization=False),
            pathlib.Path("/repo"), "0" * 64,
        )
        self.assertIn("--display=:1", local)
        self.assertIn("--display-vt=9", local)
        self.assertIn("--keep-aslr", local)

    def test_headless_default_keeps_aslr_and_omits_display(self):
        script = rm.build_and_run_script(make_args(), SHA_A)
        self.assertNotIn("--display", script)
        self.assertIn("enable --keep-aslr", script)

    def test_tune_host_disabled_via_flag(self):
        script = rm.build_and_run_script(make_args(tune_host=False), SHA_A)
        self.assertNotIn("tune_benchmark_host.py", script)


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
            stories = out / "analysis" / "stories"
            story_dir = stories / "Charts-chartjs"
            story_dir.mkdir(parents=True)
            (story_dir / "candidate_frontier.json").write_text(json.dumps({
                "quality": {
                    "accepted": True,
                    "samples": 40000,
                    "nominal_samples_at_floor": 120.0,
                    "build_provenance": {"required_release_args": {}},
                },
                "selection": {
                    "inventory_complete": True,
                    "metric_weighting": "speedometer-story-v1",
                    "story": "Charts-chartjs",
                    "min_marginal_share": 0.001,
                    "min_inclusive_share": 0.001,
                },
                "frontier": [{
                    "entry_key": "story:Charts-chartjs/symbol:blink::Hot",
                    "kind": "symbol", "name": "blink::Hot",
                    "marginal_share": 0.09,
                }],
                "overlapping_alternatives": [{
                    "kind": "symbol", "name": "blink::Shared",
                    "entry_key": "story:Charts-chartjs/symbol:blink::Shared",
                    "inclusive_share": 0.03,
                    "assigned_frontier_entry":
                        "story:Charts-chartjs/symbol:blink::Hot",
                }],
            }))
            (stories / "stories_index.json").write_text(json.dumps({
                "schema_version": 1,
                "metric_weighting": "speedometer-story-v1",
                "interval_kind": "exact-scored",
                "min_marginal_share": 0.001,
                "min_inclusive_share": 0.001,
                "story_count": 1,
                "accepted": True,
                "stories": [{
                    "story": "Charts-chartjs",
                    "dir": "Charts-chartjs",
                    "candidate_frontier_json": (
                        "/remote/chromium/scratch/results/analysis/stories/"
                        "Charts-chartjs/candidate_frontier.json"
                    ),
                    "samples": 40000,
                    "nominal_samples_at_floor": 120.0,
                    "accepted": True,
                    "issues": [],
                }],
            }))
            paths = rm.profile_summary_paths(out)
            self.assertEqual(True, paths.pop("inventory_complete"))
            self.assertEqual(
                "speedometer-story-v1", paths.pop("metric_weighting")
            )
            self.assertEqual("exact-scored", paths.pop("interval_kind"))
            self.assertEqual(0.001, paths.pop("analyzer_min_marginal_share"))
            self.assertEqual(0.001, paths.pop("analyzer_min_inclusive_share"))
            self.assertIsNone(paths.pop("stories_scope"))
            self.assertEqual({}, paths.pop("score_time_composition"))
            self.assertEqual(1, paths.pop("frontier_count"))
            self.assertEqual(1, paths.pop("story_count"))
            self.assertEqual(120.0, paths.pop("nominal_samples_at_floor"))
            self.assertEqual(
                ["story:Charts-chartjs/symbol:blink::Hot"],
                paths.pop("frontier_entries"),
            )
            self.assertEqual(
                [{
                    "entry_key": "story:Charts-chartjs/symbol:blink::Hot",
                    "work_items": [{
                        "hotspot_key": "@root",
                        "semantic_key": "symbol:blink::Hot",
                        "measured_share_pct": 9.0,
                    }, {
                        "hotspot_key": (
                            "alternative:story:Charts-chartjs/"
                            "symbol:blink::Shared"
                        ),
                        "semantic_key": "symbol:blink::Shared",
                        "measured_share_pct": 3.0,
                    }],
                }],
                paths.pop("frontier_inventory"),
            )
            story_frontiers = paths.pop("story_frontiers")
            self.assertEqual(1, len(story_frontiers))
            self.assertEqual("Charts-chartjs", story_frontiers[0]["story"])
            self.assertEqual(True, story_frontiers[0]["accepted"])
            self.assertEqual(
                {"full_candidate_frontier", "full_candidate_frontier_json",
                 "full_opportunity_trees", "stories_index_json",
                 "build_provenance"}, set(paths))


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

    def test_editor_and_junk_files_do_not_change_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_skill_tree(root)
            clean = rm.skills_digest(root)
            scripts = root / rm.SKILL_DIRS[0] / "scripts"
            for junk in (".tool.py.swp", "tool.py~", ".#tool.py",
                         "#tool.py#", ".DS_Store", "out.tmp"):
                (scripts / junk).write_text("junk")
            self.assertEqual(clean, rm.skills_digest(root))
            # The shell pipeline must ignore the same set.
            shell = subprocess.run(
                ["bash", "-c", rm.digest_shell_command()],
                cwd=root, capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(clean, shell)

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
        self.assertIn(f"export OPTIMIZE_CAMPAIGN_SKILL_DIGEST={'d' * 64}", script)


class ScoreEvidenceFetchTest(unittest.TestCase):
    def test_fetches_only_manifest_named_evidence_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = root / "ab_results_manifest.json"
            manifest.write_text(json.dumps({
                "evidence_dir": "ab_evidence_" + "a" * 24,
            }))
            with mock.patch.object(rm, "run") as run:
                rm.fetch_score_evidence(
                    "linux", "/src", manifest, root / "local"
                )
            command = run.call_args.args[0]
            self.assertIn("-C", command)
            self.assertIn(
                "linux:/src/scratch/ab_evidence_" + "a" * 24,
                command,
            )

    def test_profile_fetch_uses_rsync_compression(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            rm, "run"
        ) as run:
            rm.fetch_profile_results(
                "linux", "/src",
                "Output Dir : scratch/results_perf_sampling_abc\n",
                pathlib.Path(tmp),
            )
        self.assertIn("-az", run.call_args.args[0])

    def test_manifest_fetch_uses_scp_compression(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            rm, "run"
        ) as run:
            rm.fetch_file("linux", "/src/manifest.json", pathlib.Path(tmp))
        self.assertIn("-C", run.call_args.args[0])

    def test_rejects_unsafe_evidence_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = root / "ab_results_manifest.json"
            manifest.write_text('{"evidence_dir":"../forged"}')
            with self.assertRaisesRegex(RuntimeError, "invalid evidence_dir"):
                rm.fetch_score_evidence("linux", "/src", manifest, root)


class RemoteJobCommandTest(unittest.TestCase):
    def test_keepalives_and_lock_present(self):
        cmd = rm.remote_job_command("linux")
        self.assertEqual("ssh", cmd[0])
        self.assertIn("ServerAliveInterval=30", cmd)
        self.assertIn("ServerAliveCountMax=10", cmd)
        self.assertIn("linux", cmd)
        self.assertIn(f"flock -n -E {rm.LOCK_BUSY_EXIT} {rm.LOCK_FILE} bash -s",
                      cmd[-1])


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
    ENV_KEYS = ("OPTIMIZE_CAMPAIGN_DIR", "OPTIMIZE_CAMPAIGN_REMOTE_HOST", "OPTIMIZE_CAMPAIGN_REMOTE_SRC")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.campaign_dir = pathlib.Path(self.tmp.name) / "camp"
        self.campaign_dir.mkdir()
        self.saved_env = {k: os.environ.pop(k, None) for k in self.ENV_KEYS}
        os.environ["OPTIMIZE_CAMPAIGN_DIR"] = str(self.campaign_dir)

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
        os.environ["OPTIMIZE_CAMPAIGN_REMOTE_HOST"] = "envhost"
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


class MainValidationTest(unittest.TestCase):
    def test_score_mode_rejects_fewer_than_32_blocks(self):
        with self.assertRaises(SystemExit):
            rm.main(["--mode", "aa", "--blocks", "16"])


if __name__ == "__main__":
    unittest.main()
