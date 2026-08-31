#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Run a campaign benchmark measurement locally or on remote bare metal.

Contract: one invocation = one measurement of one committed sha (or two shas
in ab2 mode), returning a compact JSON summary on stdout and local copies of
the result manifests. Nothing is ever pushed upstream: commits travel to the
remote machine's checkout over ssh into the refs/campaign/* namespace, and the
remote measurement worktree checks the sha out detached.

Modes:
  aa       A/A noise calibration (identical binary both arms)
  ab       Flag on/off A/B of --ref (requires --feature)
  ab2      Binary vs binary A/B of --ref-a vs --ref-b (for bisecting a
           checkpoint regression, or checkpoint-vs-checkpoint comparison)
  profile  perf cycle capture + frontier analysis of --ref

Requirements on the remote host:
  - full Chromium checkout sharing upstream history with this one
  - configured out/perf (profile) and out/release (score) build dirs
  - perf, vpython3, autoninja, gn on PATH for a non-interactive ssh shell
  - a clean tracked tree (untracked files are tolerated)
  - .agents/skills resolves into a standalone skills Git clone pre-synced to
    the reviewed local commit (the files are gitignored in Chromium and are
    NOT transferred; the job verifies a content digest and exits 5 on mismatch)

The remote tree is checked out detached at the measured sha and left there.
Concurrent measurements are excluded with flock on the remote host.
Exit codes: 75 = lock busy, 4 = remote tree dirty, 5 = skills out of sync.
"""

import argparse
import errno
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile

import benchmark_adapters

LOCK_FILE = "/tmp/chromium-benchmark-measure.lock"
LOCK_BUSY_EXIT = 75
# Remote builds and multi-block runs stay silent for long stretches;
# keepalives stop idle-timeout middleboxes from dropping the session mid-job.
SSH_KEEPALIVE_OPTS = (
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=10",
)
REMOTE_DIRTY_EXIT = 4
SKILLS_SYNC_EXIT = 5
ANALYSIS_REJECTED_EXIT_CODE = 3

SKILL_DIRS = (
    ".agents/skills/optimize-campaign",
    ".agents/skills/optimize-speedometer",
    ".agents/skills/optimize-jetstream",
    ".agents/skills/chrome-cycle-profiling",
)
# Basename globs excluded from the sync digest on BOTH sides: build caches
# plus editor swap/backup and OS junk files, so an open editor on either
# machine cannot fail every measurement with a spurious exit 5. Keep this the
# single source of truth — skills_digest() and digest_shell_command() both
# render from it, and the tests verify their equivalence.
IGNORED_FILE_GLOBS = (
    "*.pyc", "*.swp", "*.swo", "*~", ".#*", "#*#", ".DS_Store", "*.tmp",
)


def run(cmd, **kwargs):
    print(f"+ {' '.join(str(c) for c in cmd)}", file=sys.stderr)
    return subprocess.run(cmd, **kwargs)


def repo_root():
    out = run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return pathlib.Path(out.stdout.strip())


def resolve_sha(root, ref):
    out = run(
        ["git", "-C", str(root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def push_ref(root, host, remote_src, sha, ref_name):
    url = f"ssh://{host}{remote_src}"
    run(
        ["git", "-C", str(root), "push", "--force", "--quiet", url,
         f"{sha}:refs/campaign/{ref_name}"],
        check=True,
        env={**os.environ, "GIT_SSH_COMMAND": "ssh " + " ".join(SSH_KEEPALIVE_OPTS)},
    )


def staged_commit_sha(root, allow_unstaged=False):
    """Create a commit object from the staged index without moving HEAD.

    Lets a reviewed-but-uncommitted candidate (staged with `git add -A`) be
    measured remotely: the dangling commit pushes like any sha and is never
    on any branch. The index must be authoritative: unstaged or untracked
    changes mean the measurement would cover only part of the candidate, so
    they are a hard error unless explicitly overridden.
    """
    status = run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    unstaged = [line for line in status if len(line) > 1 and line[1] != " "]
    if unstaged:
        message = (
            "STAGED requires a fully staged candidate; unstaged/untracked "
            "changes would be silently excluded from the measurement: "
            + ", ".join(u[3:] for u in unstaged[:5])
            + ". Run `git add -A`, or pass --allow-unstaged to override."
        )
        if not allow_unstaged:
            print(f"error: {message}", file=sys.stderr)
            raise SystemExit(1)
        print(f"warning: {message}", file=sys.stderr)
    tree = run(
        ["git", "-C", str(root), "write-tree"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    head = resolve_sha(root, "HEAD")
    sha = run(
        ["git", "-C", str(root), "commit-tree", tree, "-p", head,
         "-m", "sp3 provisional measurement of staged candidate"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    print(f"created provisional commit {sha[:12]} from the staged tree", file=sys.stderr)
    return sha


def resolve_ref(root, ref, allow_unstaged=False):
    if ref == "STAGED":
        return staged_commit_sha(root, allow_unstaged)
    return resolve_sha(root, ref)


def skills_digest(root):
    """Content digest of the skill directories, dereferencing symlinks.

    The skills are pre-synced to both machines (they are gitignored in
    Chromium, so commits do not carry them). Rather than transferring them,
    the remote job recomputes this digest with `digest_shell_command()` and
    refuses to run (exit 5) on mismatch. The algorithm must stay in
    lockstep with that shell pipeline; test_remote_measure.py verifies the
    equivalence on a real tree.
    """
    entries = []
    for skill_dir in SKILL_DIRS:
        base = root / skill_dir
        if not base.is_dir():
            print(
                f"error: skill directory missing locally: {base} — the local "
                "checkout is incomplete (broken .agents/skills symlink?); "
                "nothing was pushed or run remotely. STOP and report this to "
                "the human; do not attempt to recreate or sync it yourself.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        for dirpath, dirnames, filenames in os.walk(base, followlinks=True):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if any(fnmatch.fnmatch(name, glob) for glob in IGNORED_FILE_GLOBS):
                    continue
                full = pathlib.Path(dirpath) / name
                rel = f"{skill_dir}/{full.relative_to(base)}"
                entries.append((rel, full))
    entries.sort(key=lambda entry: entry[0])
    lines = []
    for rel, full in entries:
        content_hash = hashlib.sha256(full.read_bytes()).hexdigest()
        lines.append(f"{content_hash}  {rel}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def sync_gate_lines(expected_digest):
    """Script lines verifying the remote skills match the local digest.

    Every failure mode — missing directory, digest computation failure, or a
    plain mismatch — maps to the documented SKILLS_SYNC_EXIT so callers can
    rely on the exit-code contract."""
    q = shlex.quote
    lines = []
    for skill_dir in SKILL_DIRS:
        lines += [
            f"if [ ! -d {q(skill_dir)} ]; then",
            f'  echo "REMOTE SKILL DIRECTORY MISSING: {skill_dir}; STOP and'
            ' ask the human to sync the skills repo — do not sync it'
            ' yourself." >&2',
            f"  exit {SKILLS_SYNC_EXIT}",
            "fi",
        ]
    lines += [
        f'actual_digest="$({digest_shell_command()})" || '
        f'{{ echo "REMOTE SKILL DIGEST COMPUTATION FAILED" >&2; exit {SKILLS_SYNC_EXIT}; }}',
        f'if [ "$actual_digest" != {q(expected_digest)} ]; then',
        '  echo "REMOTE SKILL SCRIPTS OUT OF SYNC with the local checkout'
        ' (digest $actual_digest); STOP and ask the human to sync the skills'
        ' repo — do not sync it yourself." >&2',
        f"  exit {SKILLS_SYNC_EXIT}",
        "fi",
    ]
    return lines


def digest_shell_command():
    """Shell pipeline computing the same digest as skills_digest(), run from
    the checkout root. -L dereferences symlinked skill dirs; LC_ALL=C pins
    the sort order to match Python's bytewise sort."""
    dirs = " ".join(shlex.quote(d) for d in SKILL_DIRS)
    ignores = " ".join(f"! -name {shlex.quote(g)}" for g in IGNORED_FILE_GLOBS)
    return (
        f"LC_ALL=C find -L {dirs} -type f "
        f"! -path '*__pycache__*' {ignores} -print0 "
        "| LC_ALL=C sort -z | xargs -0 -r -n1 sha256sum "
        "| sha256sum | cut -d' ' -f1"
    )


def build_and_run_script(args, sha, sha_b=None, expected_digest=None):
    """Build the remote bash script for the requested mode.

    Every interpolated value is shell-quoted; nothing from the command line
    reaches the remote shell unescaped. When expected_digest is given, the
    job refuses to run (exit 5) if the remote skill scripts do not match the
    local ones — the skills are pre-synced out of band, never transferred.
    """
    q = shlex.quote
    lines = [
        "set -euo pipefail",
        f"cd {q(args.remote_src)}",
    ]
    if expected_digest:
        lines += sync_gate_lines(expected_digest)
        lines.append(f"export OPTIMIZE_CAMPAIGN_SKILL_DIGEST={q(expected_digest)}")
    lines += [
        'if [ -n "$(git status --porcelain --untracked-files=no)" ]; then',
        '  echo "REMOTE TREE HAS TRACKED MODIFICATIONS; refusing to check out." >&2',
        f"  exit {REMOTE_DIRTY_EXIT}",
        "fi",
    ]
    bench = ".agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py"
    cycle = ".agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py"
    blocks = int(args.blocks)
    seed = int(args.seed)
    stories = q(args.stories)
    benchmark = q(getattr(args, "benchmark", "speedometer3"))
    benchmark_source = getattr(args, "benchmark_source", None)
    benchmark_url = getattr(args, "benchmark_url", None)
    benchmark_payload_path = getattr(args, "benchmark_payload_path", None)
    iteration_count = getattr(args, "iteration_count", None)
    worst_case_count = getattr(args, "worst_case_count", None)
    benchmark_options = f" --benchmark={benchmark}"
    if benchmark_source:
        benchmark_options += f" --benchmark-source={q(benchmark_source)}"
    if benchmark_url:
        benchmark_options += f" --benchmark-url={q(benchmark_url)}"
    if benchmark_payload_path:
        benchmark_options += (
            f" --benchmark-payload-path={q(benchmark_payload_path)}"
        )
    if iteration_count is not None:
        benchmark_options += f" --iteration-count={int(iteration_count)}"
    if worst_case_count is not None:
        benchmark_options += f" --worst-case-count={int(worst_case_count)}"
    # Features applied identically to both arms (aa/ab2): without this, every
    # flag-gated campaign commit behaves as baseline and arms cannot differ.
    common = (
        f" --enable-features={q(args.enable_features)}"
        if args.mode in ("aa", "ab2") and args.enable_features
        else ""
    )

    if args.mode == "ab2":
        for arm, arm_sha in (("a", sha), ("b", sha_b)):
            out_dir = f"out/release_{arm}"
            lines += [
                f"git checkout --quiet --detach {q(arm_sha)}",
                f"if [ ! -f {out_dir}/args.gn ]; then",
                f"  mkdir -p {out_dir}",
                f"  cp out/release/args.gn {out_dir}/",
                f"  gn gen {out_dir}",
                "fi",
                f"autoninja -C {out_dir} chrome",
            ]
        lines.append(
            f"vpython3 {bench} --browser-a=out/release_a/chrome "
            f"--browser-b=out/release_b/chrome --required-build-role=release "
            f"--blocks={blocks} --stories={stories} --seed={seed}{common}"
            f"{benchmark_options}"
        )
    else:
        out_dir = "out/perf" if args.mode == "profile" else "out/release"
        lines += [
            f"git checkout --quiet --detach {q(sha)}",
            f"autoninja -C {out_dir} chrome",
        ]
        if args.mode == "aa":
            lines.append(
                f"vpython3 {bench} --browser=out/release/chrome --aa "
                f"--required-build-role=release "
                f"--blocks={blocks} --stories={stories} --seed={seed}{common}"
                f"{benchmark_options}"
            )
        elif args.mode == "ab":
            lines.append(
                f"vpython3 {bench} --browser=out/release/chrome "
                f"--required-build-role=release "
                f"--feature={q(args.feature)} --blocks={blocks} "
                f"--stories={stories} --seed={seed}{benchmark_options}"
            )
        elif args.mode == "profile":
            features = args.enable_features if args.enable_features is not None else ""
            # Quality rejection (exit 3) still produces diagnostic reports;
            # surface it but do not mask it as a hard ssh failure.
            lines.append(
                f"vpython3 {cycle} --browser=out/perf/chrome "
                f"--stories={stories} --repetitions={int(args.repetitions)}"
                f" --enable-features={q(features)}"
                f" --min-share={args.share_floor_pct / 100.0}"
                f" --min-marginal-share={args.share_floor_pct / 100.0}"
                f"{benchmark_options}"
                f" || rc=$?; rc=${{rc:-0}}; "
                f"if [ $rc -ne 0 ] && [ $rc -ne {ANALYSIS_REJECTED_EXIT_CODE} ]; then exit $rc; fi; "
                f'echo "PROFILE_EXIT_CODE: $rc"'
            )
    return "\n".join(lines) + "\n"


def build_local_script(args, root, expected_digest):
    """Build a script for an in-place run without checkout or SSH.

    Local mode deliberately never changes refs.  It is ideal for functional
    characterization with an existing out/Default build and can also use an
    explicitly prepared release/perf build for evidence collection.
    """
    q = shlex.quote
    bench = ".agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py"
    cycle = ".agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py"
    browser = args.browser
    driver = args.driver_path
    role = "development" if args.characterization else "release"
    common = [
        f"--benchmark={q(args.benchmark)}",
        f"--benchmark-source={q(args.benchmark_source)}",
        f"--stories={q(args.stories)}",
    ]
    if args.benchmark_url:
        common.append(f"--benchmark-url={q(args.benchmark_url)}")
    if args.benchmark_payload_path:
        common.append(
            f"--benchmark-payload-path={q(args.benchmark_payload_path)}"
        )
    if driver:
        common.append(f"--driver-path={q(driver)}")
    if args.iteration_count is not None:
        common.append(f"--iteration-count={int(args.iteration_count)}")
    if args.worst_case_count is not None:
        common.append(f"--worst-case-count={int(args.worst_case_count)}")
    lines = [
        "set -euo pipefail",
        f"cd {q(str(root))}",
        f"export OPTIMIZE_CAMPAIGN_SKILL_DIGEST={q(expected_digest)}",
    ]
    if not args.skip_build:
        build_dir = os.path.dirname(browser)
        lines.append(f"autoninja -C {q(build_dir)} chrome chromedriver")
    if args.mode == "profile":
        features = args.enable_features or ""
        lines.append(
            f"vpython3 {cycle} --browser={q(browser)} "
            f"--stories={q(args.stories)} "
            f"--repetitions={int(args.repetitions)} "
            f"--enable-features={q(features)} "
            f"--min-share={args.share_floor_pct / 100.0} "
            f"--min-marginal-share={args.share_floor_pct / 100.0} "
            f"--benchmark={q(args.benchmark)} "
            f"--benchmark-source={q(args.benchmark_source)}"
        )
        return "\n".join(lines) + "\n"
    command = [
        "vpython3", bench, f"--required-build-role={role}",
        f"--blocks={int(args.blocks)}", f"--seed={int(args.seed)}",
        *common,
    ]
    if args.mode == "aa":
        command.extend((f"--browser={q(browser)}", "--aa"))
        if args.enable_features:
            command.append(f"--enable-features={q(args.enable_features)}")
    elif args.mode == "ab":
        command.extend((
            f"--browser={q(browser)}", f"--feature={q(args.feature)}"
        ))
    else:
        if not args.browser_a or not args.browser_b:
            raise ValueError(
                "local ab2 requires --browser-a and --browser-b prepared "
                "at the requested refs"
            )
        command.extend((
            f"--browser-a={q(args.browser_a)}",
            f"--browser-b={q(args.browser_b)}",
        ))
        if args.enable_features:
            command.append(f"--enable-features={q(args.enable_features)}")
    lines.append(" ".join(command))
    return "\n".join(lines) + "\n"


def send_stdin(proc, data):
    """Write data to proc's stdin, tolerating early exit of the peer.

    When flock rejects the job (lock busy), ssh can close stdin while we are
    still writing; the resulting EPIPE must not mask the real exit code."""
    try:
        proc.stdin.write(data)
    except BrokenPipeError:
        pass
    except OSError as e:
        if e.errno != errno.EPIPE:
            raise
    finally:
        try:
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass


def remote_job_command(host):
    return [
        "ssh",
        *SSH_KEEPALIVE_OPTS,
        host,
        f"flock -n -E {LOCK_BUSY_EXIT} {LOCK_FILE} bash -s",
    ]


def run_remote(host, script):
    """Run the job script on the remote host under the measurement lock."""
    cmd = remote_job_command(host)
    print(f"+ ssh {host} flock ... bash -s  # job script:\n{script}", file=sys.stderr)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
    )
    send_stdin(proc, script.encode())
    stdout_lines = []
    for raw in proc.stdout:
        line = raw.decode(errors="replace")
        sys.stderr.write(line)
        stdout_lines.append(line)
    proc.wait()
    return proc.returncode, "".join(stdout_lines)


def run_local(script):
    """Run an in-place measurement under the same host-wide lock."""
    cmd = ["flock", "-n", "-E", str(LOCK_BUSY_EXIT), LOCK_FILE, "bash", "-s"]
    print(f"+ flock ... bash -s  # local job script:\n{script}", file=sys.stderr)
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None
    )
    send_stdin(proc, script.encode())
    stdout_lines = []
    for raw in proc.stdout:
        line = raw.decode(errors="replace")
        sys.stderr.write(line)
        stdout_lines.append(line)
    proc.wait()
    return proc.returncode, "".join(stdout_lines)


def fetch_file(host, remote_path, local_dir):
    local_dir.mkdir(parents=True, exist_ok=True)
    run(
        ["scp", "-C", "-q", f"{host}:{shlex.quote(remote_path)}",
         str(local_dir) + "/"],
        check=True,
    )


def fetch_score_evidence(host, remote_src, manifest_path, local_dir):
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read fetched score manifest: {exc}") from exc
    evidence_dir = manifest.get("evidence_dir")
    if (
        not isinstance(evidence_dir, str)
        or pathlib.PurePath(evidence_dir).name != evidence_dir
        or not re.fullmatch(r"ab_evidence_[0-9a-f]{24}", evidence_dir)
    ):
        raise RuntimeError("score manifest has an invalid evidence_dir")
    run(
        [
            "scp", "-C", "-q", "-r",
            f"{host}:{shlex.quote(f'{remote_src}/scratch/{evidence_dir}')}",
            str(local_dir) + "/",
        ],
        check=True,
    )


def copy_local_score_evidence(root, local_dir):
    """Copy runner-owned score evidence out of Chromium scratch."""
    source_manifest = root / "scratch" / "ab_results_manifest.json"
    if not source_manifest.is_file():
        raise RuntimeError(f"local score manifest is missing: {source_manifest}")
    local_dir.mkdir(parents=True, exist_ok=True)
    target_manifest = local_dir / source_manifest.name
    shutil.copy2(source_manifest, target_manifest)
    manifest = json.loads(target_manifest.read_text())
    evidence_name = manifest.get("evidence_dir")
    if (
        not isinstance(evidence_name, str)
        or not re.fullmatch(r"ab_evidence_[0-9a-f]{24}", evidence_name)
    ):
        raise RuntimeError("local score manifest has an invalid evidence_dir")
    source_evidence = root / "scratch" / evidence_name
    target_evidence = local_dir / evidence_name
    if target_evidence.exists():
        raise RuntimeError(f"local evidence destination already exists: {target_evidence}")
    shutil.copytree(source_evidence, target_evidence)
    return target_manifest


def parse_remote_results_dir(remote_stdout):
    m = re.search(r"Output Dir\s*:\s*(\S+)", remote_stdout)
    return m.group(1) if m else None


def fetch_profile_results(host, remote_src, remote_stdout, local_dir):
    remote_dir = parse_remote_results_dir(remote_stdout)
    if not remote_dir:
        print("warning: could not locate remote results dir in output", file=sys.stderr)
        return None
    local_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            "rsync",
            "-az",
            "--exclude",
            "perf_sampling.data",
            f"{host}:{shlex.quote(f'{remote_src}/{remote_dir}')}/",
            f"{local_dir}/",
        ],
        check=True,
    )
    return remote_dir


def default_out_dir(root, mode):
    scratch = root / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    return pathlib.Path(tempfile.mkdtemp(prefix=f"remote_{mode}_", dir=scratch))


def profile_summary_paths(out_dir):
    """Analysis artifacts promised by the profiler playbook, when present.

    The authoritative frontier inventory is the concatenation of the
    per-story silo analyses under analysis/stories/ (story-qualified entry
    keys, shares local to each story's scored cycles). The full-suite and
    renderer views remain diagnostic only.
    """
    import campaign
    paths = {}
    paths["inventory_complete"] = False
    index_path = out_dir / "analysis" / "stories" / "stories_index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
            stories = index.get("stories", [])
            paths["stories_index_json"] = str(index_path)
            paths["metric_weighting"] = index.get("metric_weighting")
            paths["interval_kind"] = index.get("interval_kind")
            paths["analyzer_min_marginal_share"] = index.get(
                "min_marginal_share"
            )
            paths["analyzer_min_inclusive_share"] = index.get(
                "min_inclusive_share"
            )
            complete = bool(stories) and index.get("accepted") is True
            entries = []
            inventory = []
            problems = []
            story_frontiers = []
            nominal_floor = None
            build_provenance = None
            for item in stories:
                # The fetched result tree has a different absolute root from
                # the measurement host. Resolve only within the local copy;
                # older indexes that stored absolute remote paths remain
                # readable through their relocatable `dir` field.
                relative_artifact = pathlib.PurePath(
                    item.get("candidate_frontier_json", "")
                )
                if relative_artifact.is_absolute() or ".." in relative_artifact.parts:
                    relative_artifact = pathlib.PurePath(
                        item.get("dir", item.get("story", ""))
                    ) / "candidate_frontier.json"
                artifact_path = index_path.parent / relative_artifact
                report = json.loads(artifact_path.read_text())
                quality = report.get("quality", {})
                selection = report.get("selection", {})
                if quality.get("accepted") is not True:
                    complete = False
                if selection.get("inventory_complete") is not True:
                    complete = False
                # The importer re-derives each story inventory from its
                # artifact with the same shared function and rejects the
                # capture on any mismatch.
                story_entries, story_inventory, story_problems = (
                    campaign.derive_frontier_inventory(report)
                )
                if story_problems:
                    complete = False
                    problems.extend(
                        f"{item.get('story')}: {problem}"
                        for problem in story_problems
                    )
                entries.extend(story_entries)
                inventory.extend(story_inventory)
                nominal = quality.get("nominal_samples_at_floor")
                if isinstance(nominal, (int, float)):
                    nominal_floor = (
                        nominal if nominal_floor is None
                        else min(nominal_floor, nominal)
                    )
                if build_provenance is None:
                    build_provenance = quality.get("build_provenance")
                story_frontiers.append({
                    "story": item.get("story"),
                    "artifact": str(artifact_path),
                    "samples": quality.get("samples"),
                    "nominal_samples_at_floor": nominal,
                    "accepted": quality.get("accepted"),
                    "frontier_count": len(story_entries),
                })
            paths["inventory_complete"] = complete
            if problems:
                paths["inventory_problems"] = problems
            paths["story_frontiers"] = story_frontiers
            paths["story_count"] = len(story_frontiers)
            # The weakest story bounds the whole capture: every silo must
            # clear the 100-nominal-sample floor independently.
            paths["nominal_samples_at_floor"] = nominal_floor
            paths["build_provenance"] = build_provenance
            paths["frontier_count"] = len(entries)
            paths["frontier_entries"] = entries
            paths["frontier_inventory"] = inventory
        except (OSError, ValueError, TypeError):
            paths["inventory_complete"] = False
    for view in ("full", "renderer"):
        base = out_dir / "analysis" / view
        for key, name in (
            ("candidate_frontier", "candidate_frontier.md"),
            ("candidate_frontier_json", "candidate_frontier.json"),
            ("opportunity_trees", "opportunity_trees.txt"),
        ):
            path = base / name
            if path.exists():
                paths[f"{view}_{key}"] = str(path)
    return paths


def ledger_remote_defaults():
    """Remote host/src recorded at campaign init, if a campaign is active.

    Only a genuinely absent ledger falls back to (None, None). A present but
    unreadable/malformed active ledger is a hard error: silently substituting
    fallback infrastructure could send an unattended run to the wrong host.
    """
    import campaign
    path = campaign.default_campaign_dir() / "ledger.json"
    if not path.exists():
        return None, None
    try:
        config = json.loads(path.read_text())["config"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(
            f"error: active campaign ledger at {path} is unreadable or "
            f"malformed ({e}); fix it, or pass --host and --remote-src "
            "explicitly to bypass ledger defaults",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return config.get("remote_host"), config.get("remote_src")


def ledger_benchmark_defaults():
    """Return execution and benchmark defaults from an active campaign."""
    import campaign
    path = campaign.default_campaign_dir() / "ledger.json"
    if not path.exists():
        return None, None, None
    try:
        config = json.loads(path.read_text())["config"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: cannot read campaign benchmark defaults: {exc}", file=sys.stderr)
        raise SystemExit(1)
    return (
        config.get("execution"),
        config.get("benchmark"),
        config.get("benchmark_source"),
    )


def ledger_share_floor_pct(default=0.3):
    """Return the active campaign's percentage share floor when available."""
    import campaign
    path = campaign.default_campaign_dir() / "ledger.json"
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text())["config"]["share_floor_pct"]
        return float(value)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(
            f"error: active campaign ledger at {path} has no valid "
            f"share_floor_pct ({e}); pass --share-floor-pct explicitly",
            file=sys.stderr,
        )
        raise SystemExit(1)


def verify_opportunity_ready_for_ab(opp_id, feature_name):
    """Verify that an opportunity has passed Gate 3 (sized) before running candidate A/B."""
    import campaign
    path = campaign.default_campaign_dir() / "ledger.json"
    if not path.exists():
        print(f"error: cannot verify opportunity #{opp_id}: no active campaign ledger at {path}", file=sys.stderr)
        raise SystemExit(1)
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        print(f"error: cannot read campaign ledger at {path}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    opps = [o for o in data.get("opportunities", []) if o.get("id") == opp_id]
    if not opps:
        print(f"error: opportunity #{opp_id} not found in active campaign ledger {path}", file=sys.stderr)
        raise SystemExit(1)

    opp = opps[0]
    status = opp.get("status")
    # Verify that the opportunity has passed sizing
    if status not in ("sized", "implementing", "review", "landed"):
        print(
            f"error: opportunity #{opp_id} is in status '{status}'; candidate A/B measurement "
            "requires the opportunity to have passed Gate 3 (sized) via mechanism_evidence.py first.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def resolve_remote(args_host, args_src, root):
    """Precedence: CLI flag > env var > campaign ledger > fallback.

    The ledger is consulted only when needed, so explicit --host/--remote-src
    work even while the ledger is broken."""
    host = args_host or os.environ.get("OPTIMIZE_CAMPAIGN_REMOTE_HOST")
    src = args_src or os.environ.get("OPTIMIZE_CAMPAIGN_REMOTE_SRC")
    if host and src:
        return host, src
    ledger_host, ledger_src = ledger_remote_defaults()
    return host or ledger_host or "linux", src or ledger_src or str(root)


def summarize_ab(manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)
    keys = (
        "schema_version",
        "runner",
        "benchmark",
        "metric_model",
        "workload_value_direction",
        "payload_provenance",
        "mode",
        "feature",
        "enable_features",
        "stories",
        "observed_workloads",
        "expected_workload_count",
        "blocks",
        "seed",
        "schedule",
        "geometric_delta_pct",
        "ci_95_pct",
        "significance_threshold_pct",
        "mde_80_power_pct",
        "is_stat_sig",
        "passes_regression_guardrail",
        "stat_sig_story_regressions",
        "build_provenance",
        "started_at",
        "finished_at",
        "started_monotonic_raw_ns",
        "finished_monotonic_raw_ns",
        "minimum_duration_ns",
        "capture_environment",
        "harness",
        "skill_tree_sha256",
        "evidence_dir",
    )
    return {k: manifest.get(k) for k in keys if k in manifest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", required=True, choices=("aa", "ab", "ab2", "profile"))
    parser.add_argument(
        "--execution", choices=("local", "ssh"), default=None,
        help="Run directly on this host or through SSH (campaign default, then ssh)",
    )
    parser.add_argument(
        "--benchmark", choices=benchmark_adapters.available_benchmarks(),
        default=None,
        help="Benchmark adapter (campaign default, then speedometer3)",
    )
    parser.add_argument(
        "--benchmark-source", default=None,
        help="Benchmark payload source (adapter/campaign default if omitted)",
    )
    parser.add_argument("--benchmark-url", default=None)
    parser.add_argument(
        "--benchmark-payload-path", default=None,
        help="Immutable payload tree served and digest-bound by the runner",
    )
    parser.add_argument("--iteration-count", type=int, default=None)
    parser.add_argument("--worst-case-count", type=int, default=None)
    parser.add_argument(
        "--host", default=None,
        help="ssh host of the measurement machine (default: $OPTIMIZE_CAMPAIGN_REMOTE_HOST, "
        "then the campaign ledger's remote_host, then 'linux')",
    )
    parser.add_argument(
        "--remote-src",
        default=None,
        help="Absolute path of the Chromium checkout on the remote host "
        "(default: $OPTIMIZE_CAMPAIGN_REMOTE_SRC, then the campaign ledger's remote_src, "
        "then the same path as the local checkout)",
    )
    parser.add_argument("--ref", default="HEAD",
                        help="Commit to measure. The special value STAGED builds a "
                        "provisional commit from the staged index (for measuring a "
                        "reviewed-but-uncommitted candidate) without moving HEAD.")
    parser.add_argument("--ref-a", help="ab2 mode: arm A commit (STAGED allowed)")
    parser.add_argument("--ref-b", help="ab2 mode: arm B commit (STAGED allowed)")
    parser.add_argument("--feature", help="ab mode: feature flag to toggle")
    parser.add_argument(
        "--blocks", type=int, default=None,
        help="Score blocks (default: 32, exactly balanced; profile mode ignores it)",
    )
    parser.add_argument("--stories", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--repetitions", type=int, default=16,
        help="profile mode (default: 16 so every story silo clears its "
        "local sample floor)",
    )
    parser.add_argument(
        "--enable-features",
        default=None,
        help="profile mode: features for the capture (empty string = baseline). "
        "aa/ab2 modes: features enabled identically on BOTH arms — required "
        "when bisecting flag-gated campaign commits.",
    )
    parser.add_argument(
        "--share-floor-pct",
        type=float,
        default=None,
        help="profile mode: campaign marginal-share floor in percent",
    )
    parser.add_argument("--out", help="Local results directory")
    parser.add_argument(
        "--browser", default=None,
        help="Local-mode browser (out/Default/chrome for characterization, "
        "otherwise out/release/chrome)",
    )
    parser.add_argument("--driver-path", default=None)
    parser.add_argument("--browser-a", default=None)
    parser.add_argument("--browser-b", default=None)
    parser.add_argument(
        "--characterization", action="store_true",
        help="Functional/local validation only; permits development builds and "
        "small block counts, and cannot be imported as campaign evidence",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Use the existing local build without invoking autoninja",
    )
    parser.add_argument(
        "--summary-out",
        help="Write the final machine-readable summary JSON to this local path",
    )
    parser.add_argument("--allow-unstaged", action="store_true",
                        help="Allow STAGED to proceed despite unstaged/untracked "
                        "changes (they are excluded from the measurement)")
    parser.add_argument(
        "--opp",
        type=int,
        default=None,
        help="Campaign opportunity ID under evaluation (enforces Gate 3 sized status)",
    )
    args = parser.parse_args(argv)
    cli_benchmark = args.benchmark
    if args.execution and args.benchmark:
        ledger_execution, ledger_benchmark, ledger_source = None, None, None
    else:
        ledger_execution, ledger_benchmark, ledger_source = (
            ledger_benchmark_defaults()
        )
    args.execution = args.execution or ledger_execution or "ssh"
    args.benchmark = args.benchmark or ledger_benchmark or "speedometer3"
    adapter = benchmark_adapters.get_adapter(args.benchmark)
    args.benchmark_source = (
        args.benchmark_source
        or (
            adapter.profile_source
            if args.mode == "profile"
            else (
                ledger_source
                if cli_benchmark is None or ledger_benchmark == args.benchmark
                else None
            )
            or adapter.score_sources[0]
        )
    )
    if args.stories is None:
        args.stories = adapter.default_workload_selector
    if args.browser is None:
        args.browser = (
            "out/Default/chrome" if args.characterization
            else "out/release/chrome"
        )
    if args.driver_path is None and args.characterization:
        candidate_driver = os.path.join(
            os.path.dirname(args.browser), "chromedriver"
        )
        if os.path.exists(candidate_driver):
            args.driver_path = candidate_driver
    if args.blocks is None:
        args.blocks = 2 if args.characterization else 32
    if args.mode in ("aa", "ab", "ab2") and (
        args.blocks < (2 if args.characterization else 32) or args.blocks % 2
    ):
        parser.error(
            f"{'characterization' if args.characterization else 'score'} "
            "measurements require an even block count of at least "
            f"{2 if args.characterization else 32}"
        )
    if args.seed is None:
        args.seed = secrets.randbits(32)

    if args.mode == "ab" and not args.feature:
        parser.error("--mode ab requires --feature")
    if args.mode == "ab" and args.opp is not None and not args.characterization:
        verify_opportunity_ready_for_ab(args.opp, args.feature)
    if args.mode == "ab" and args.enable_features:
        parser.error("--mode ab manages the flag itself; --enable-features "
                     "applies only to aa/ab2/profile modes")
    if args.mode == "ab2" and not (args.ref_a and args.ref_b):
        parser.error("--mode ab2 requires --ref-a and --ref-b")
    if args.mode == "ab2" and not args.enable_features:
        print(
            "warning: --mode ab2 without --enable-features compares BASELINE "
            "behavior of both binaries; flag-gated campaign commits cannot "
            "differ. Pass --enable-features=<campaign flag> for bisects.",
            file=sys.stderr,
        )
    if args.characterization and args.execution != "local":
        parser.error("--characterization is intentionally local-only")

    root = repo_root()
    if args.mode == "profile" and args.share_floor_pct is None:
        args.share_floor_pct = ledger_share_floor_pct(default=0.3)
    if args.execution == "ssh":
        args.host, args.remote_src = resolve_remote(
            args.host, args.remote_src, root
        )
    else:
        args.host = args.host or socket.gethostname()
        args.remote_src = args.remote_src or str(root)
    out_dir = pathlib.Path(args.out) if args.out else default_out_dir(root, args.mode)

    if args.execution == "local" and args.ref == "STAGED":
        parser.error("local mode cannot bind an existing binary to STAGED")
    if args.mode == "ab2":
        sha = resolve_ref(root, args.ref_a, args.allow_unstaged)
        sha_b = resolve_ref(root, args.ref_b, args.allow_unstaged)
        if args.execution == "ssh":
            push_ref(root, args.host, args.remote_src, sha, "measure-a")
            push_ref(root, args.host, args.remote_src, sha_b, "measure-b")
    else:
        sha = resolve_ref(root, args.ref, args.allow_unstaged)
        sha_b = None
        if args.execution == "ssh":
            push_ref(root, args.host, args.remote_src, sha, "measure")

    if args.execution == "local":
        head = resolve_sha(root, "HEAD")
        if args.mode != "ab2" and sha != head:
            parser.error(
                "local mode never changes the checkout; --ref must resolve to HEAD"
            )
        if args.mode == "ab2" and not args.characterization:
            parser.error(
                "authoritative local ab2 needs separately attested build trees; "
                "use SSH mode or --characterization with explicit browsers"
            )

    executing_skill_digest = skills_digest(root)
    if args.execution == "local":
        try:
            script = build_local_script(args, root, executing_skill_digest)
        except ValueError as exc:
            parser.error(str(exc))
        rc, remote_stdout = run_local(script)
    else:
        script = build_and_run_script(args, sha, sha_b, executing_skill_digest)
        rc, remote_stdout = run_remote(args.host, script)
    if rc == LOCK_BUSY_EXIT:
        print("error: another measurement holds the remote lock; retry later", file=sys.stderr)
        return LOCK_BUSY_EXIT
    if rc == REMOTE_DIRTY_EXIT:
        print(
            "error: remote tracked tree is dirty; clean it (or commit/stash there) first",
            file=sys.stderr,
        )
        return REMOTE_DIRTY_EXIT
    if rc == SKILLS_SYNC_EXIT:
        print(
            "error: remote skill scripts differ from local. STOP and report "
            "this to the human — syncing the skills repo is a human "
            "operation; never rsync/scp/git-push it yourself. Retry only "
            "after the human confirms the sync.",
            file=sys.stderr,
        )
        return SKILLS_SYNC_EXIT
    if rc != 0:
        print(
            f"error: {args.execution} measurement failed with exit code {rc}",
            file=sys.stderr,
        )
        return rc

    summary = {
        "mode": args.mode,
        "execution": args.execution,
        "benchmark": args.benchmark,
        "characterization": args.characterization,
        "host": socket.gethostname() if args.execution == "local" else args.host,
        "sha": sha,
        "sha_b": sha_b,
        "local_results": str(out_dir),
        "skill_tree_sha256": executing_skill_digest,
    }
    if args.mode in ("aa", "ab", "ab2"):
        if args.execution == "local":
            manifest_path = copy_local_score_evidence(root, out_dir)
        else:
            fetch_file(
                args.host,
                f"{args.remote_src}/scratch/ab_results_manifest.json",
                out_dir,
            )
            manifest_path = out_dir / "ab_results_manifest.json"
            fetch_score_evidence(
                args.host, args.remote_src, manifest_path, out_dir
            )
        summary["manifest"] = str(manifest_path)
        summary.update(summarize_ab(manifest_path))
    else:
        if args.execution == "local":
            remote_dir = parse_remote_results_dir(remote_stdout)
            if remote_dir:
                source_dir = root / remote_dir
                if out_dir.resolve() != source_dir.resolve():
                    shutil.copytree(source_dir, out_dir, dirs_exist_ok=True)
        else:
            remote_dir = fetch_profile_results(
                args.host, args.remote_src, remote_stdout, out_dir
            )
        summary["remote_results_dir"] = remote_dir
        summary["remote_perf_data"] = (
            (
                str(root / remote_dir / "perf_sampling.data")
                if args.execution == "local"
                else f"{args.remote_src}/{remote_dir}/perf_sampling.data"
            ) if remote_dir else None
        )
        quality = re.search(r"PROFILE_EXIT_CODE: (\d+)", remote_stdout)
        summary["quality_rejected"] = bool(
            quality and int(quality.group(1)) == ANALYSIS_REJECTED_EXIT_CODE
        )
        summary["enable_features"] = (
            args.enable_features if args.enable_features is not None else ""
        )
        summary["share_floor_pct"] = args.share_floor_pct
        summary["repetitions"] = args.repetitions
        summary["stories"] = args.stories
        summary["capture_id"] = out_dir.name
        summary.update(profile_summary_paths(out_dir))

    summary_json = json.dumps(summary, indent=2)
    if args.summary_out:
        summary_path = pathlib.Path(args.summary_out)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary_json + "\n")
    print(summary_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
