#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Run a Speedometer measurement on the remote bare-metal machine.

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
  - configured out/perf build dir (args.gn present)
  - perf, vpython3, autoninja, gn on PATH for a non-interactive ssh shell
  - a clean tracked tree (untracked files are tolerated)
  - skill scripts pre-synced to match the local ones (they are gitignored in
    Chromium and are NOT transferred; the job verifies a content digest and
    exits 5 on mismatch)

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
import shlex
import subprocess
import sys
import tempfile

LOCK_FILE = "/tmp/sp3-measure.lock"
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
    ".agents/skills/optimize-speedometer",
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
    # Features applied identically to both arms (aa/ab2): without this, every
    # flag-gated campaign commit behaves as baseline and arms cannot differ.
    common = (
        f" --enable-features={q(args.enable_features)}"
        if args.mode in ("aa", "ab2") and args.enable_features
        else ""
    )

    if args.mode == "ab2":
        for arm, arm_sha in (("a", sha), ("b", sha_b)):
            out_dir = f"out/perf_{arm}"
            lines += [
                f"git checkout --quiet --detach {q(arm_sha)}",
                f"if [ ! -f {out_dir}/args.gn ]; then",
                f"  mkdir -p {out_dir}",
                f"  cp out/perf/args.gn {out_dir}/",
                f"  gn gen {out_dir}",
                "fi",
                f"autoninja -C {out_dir} chrome",
            ]
        lines.append(
            f"vpython3 {bench} --browser-a=out/perf_a/chrome "
            f"--browser-b=out/perf_b/chrome --blocks={blocks} "
            f"--stories={stories} --seed={seed}{common}"
        )
    else:
        lines += [
            f"git checkout --quiet --detach {q(sha)}",
            "autoninja -C out/perf chrome",
        ]
        if args.mode == "aa":
            lines.append(
                f"vpython3 {bench} --browser=out/perf/chrome --aa "
                f"--blocks={blocks} --stories={stories} --seed={seed}{common}"
            )
        elif args.mode == "ab":
            lines.append(
                f"vpython3 {bench} --browser=out/perf/chrome "
                f"--feature={q(args.feature)} --blocks={blocks} "
                f"--stories={stories} --seed={seed}"
            )
        elif args.mode == "profile":
            features = args.enable_features if args.enable_features is not None else ""
            # Quality rejection (exit 3) still produces diagnostic reports;
            # surface it but do not mask it as a hard ssh failure.
            lines.append(
                f"vpython3 {cycle} --browser=out/perf/chrome "
                f"--stories={stories} --repetitions={int(args.repetitions)}"
                f" --enable-features={q(features)} || rc=$?; rc=${{rc:-0}}; "
                f"if [ $rc -ne 0 ] && [ $rc -ne {ANALYSIS_REJECTED_EXIT_CODE} ]; then exit $rc; fi; "
                f'echo "PROFILE_EXIT_CODE: $rc"'
            )
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


def fetch_file(host, remote_path, local_dir):
    local_dir.mkdir(parents=True, exist_ok=True)
    run(["scp", "-q", f"{host}:{shlex.quote(remote_path)}", str(local_dir) + "/"], check=True)


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
            "-a",
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
    """Analysis artifacts promised by the profiler playbook, when present."""
    paths = {}
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


def resolve_remote(args_host, args_src, root):
    """Precedence: CLI flag > env var > campaign ledger > fallback.

    The ledger is consulted only when needed, so explicit --host/--remote-src
    work even while the ledger is broken."""
    host = args_host or os.environ.get("SP3_REMOTE_HOST")
    src = args_src or os.environ.get("SP3_REMOTE_SRC")
    if host and src:
        return host, src
    ledger_host, ledger_src = ledger_remote_defaults()
    return host or ledger_host or "linux", src or ledger_src or str(root)


def summarize_ab(manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)
    keys = (
        "mode",
        "feature",
        "enable_features",
        "blocks",
        "geometric_delta_pct",
        "ci_95_pct",
        "significance_threshold_pct",
        "mde_80_power_pct",
        "is_stat_sig",
        "passes_regression_guardrail",
        "stat_sig_story_regressions",
    )
    return {k: manifest.get(k) for k in keys if k in manifest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", required=True, choices=("aa", "ab", "ab2", "profile"))
    parser.add_argument(
        "--host", default=None,
        help="ssh host of the measurement machine (default: $SP3_REMOTE_HOST, "
        "then the campaign ledger's remote_host, then 'linux')",
    )
    parser.add_argument(
        "--remote-src",
        default=None,
        help="Absolute path of the Chromium checkout on the remote host "
        "(default: $SP3_REMOTE_SRC, then the campaign ledger's remote_src, "
        "then the same path as the local checkout)",
    )
    parser.add_argument("--ref", default="HEAD",
                        help="Commit to measure. The special value STAGED builds a "
                        "provisional commit from the staged index (for measuring a "
                        "reviewed-but-uncommitted candidate) without moving HEAD.")
    parser.add_argument("--ref-a", help="ab2 mode: arm A commit (STAGED allowed)")
    parser.add_argument("--ref-b", help="ab2 mode: arm B commit (STAGED allowed)")
    parser.add_argument("--feature", help="ab mode: feature flag to toggle")
    parser.add_argument("--blocks", type=int, default=5)
    parser.add_argument("--stories", default="all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repetitions", type=int, default=2, help="profile mode")
    parser.add_argument(
        "--enable-features",
        default=None,
        help="profile mode: features for the capture (empty string = baseline). "
        "aa/ab2 modes: features enabled identically on BOTH arms — required "
        "when bisecting flag-gated campaign commits.",
    )
    parser.add_argument("--out", help="Local results directory")
    parser.add_argument("--allow-unstaged", action="store_true",
                        help="Allow STAGED to proceed despite unstaged/untracked "
                        "changes (they are excluded from the measurement)")
    args = parser.parse_args(argv)

    if args.mode == "ab" and not args.feature:
        parser.error("--mode ab requires --feature")
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

    root = repo_root()
    args.host, args.remote_src = resolve_remote(args.host, args.remote_src, root)
    out_dir = pathlib.Path(args.out) if args.out else default_out_dir(root, args.mode)

    if args.mode == "ab2":
        sha = resolve_ref(root, args.ref_a, args.allow_unstaged)
        sha_b = resolve_ref(root, args.ref_b, args.allow_unstaged)
        push_ref(root, args.host, args.remote_src, sha, "measure-a")
        push_ref(root, args.host, args.remote_src, sha_b, "measure-b")
    else:
        sha = resolve_ref(root, args.ref, args.allow_unstaged)
        sha_b = None
        push_ref(root, args.host, args.remote_src, sha, "measure")

    script = build_and_run_script(args, sha, sha_b, skills_digest(root))
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
        print(f"error: remote measurement failed with exit code {rc}", file=sys.stderr)
        return rc

    summary = {
        "mode": args.mode,
        "host": args.host,
        "sha": sha,
        "sha_b": sha_b,
        "local_results": str(out_dir),
    }
    if args.mode in ("aa", "ab", "ab2"):
        fetch_file(args.host, f"{args.remote_src}/scratch/ab_results_manifest.json", out_dir)
        summary["manifest"] = str(out_dir / "ab_results_manifest.json")
        summary.update(summarize_ab(out_dir / "ab_results_manifest.json"))
    else:
        remote_dir = fetch_profile_results(args.host, args.remote_src, remote_stdout, out_dir)
        summary["remote_results_dir"] = remote_dir
        summary["remote_perf_data"] = (
            f"{args.remote_src}/{remote_dir}/perf_sampling.data" if remote_dir else None
        )
        quality = re.search(r"PROFILE_EXIT_CODE: (\d+)", remote_stdout)
        summary["quality_rejected"] = bool(
            quality and int(quality.group(1)) == ANALYSIS_REJECTED_EXIT_CODE
        )
        summary.update(profile_summary_paths(out_dir))

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
