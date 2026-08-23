#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Randomized block-interleaved (ABBA/BAAB) Crossbench benchmark.

Modes (choose exactly one):
  --aa                        Genuine A/A calibration: identical binary and
                              identical flags on both arms.
  --feature=Name              Flag on/off A/B within one binary (--browser).
  --browser-a/--browser-b     Binary vs binary A/B (two build dirs). Pass
                              --enable-features to apply features identically
                              to both arms — required when the binaries differ
                              only behind a default-off flag.

Outputs suite-level block log-difference statistics plus a per-story table
computed from each iteration's per-story total times (lower is better; the
reported per-story delta is sign-normalized so positive = B faster). Per-story
CIs across ~30 stories at 95% imply roughly one false positive per run; treat
single flagged stories as leads to confirm with a targeted rerun, not verdicts.
"""

import argparse
import atexit
import datetime
import fnmatch
import functools
import hashlib
import http.server
import json
import math
import os
import platform
import random
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time


_CAMPAIGN_SCRIPTS = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "optimize-campaign", "scripts")
)
if _CAMPAIGN_SCRIPTS not in sys.path:
    sys.path.append(_CAMPAIGN_SCRIPTS)
import benchmark_adapters


MANIFEST_SCHEMA_VERSION = 4
MANIFEST_RUNNER = "run_ab_benchmark.py/v4"
MIN_FULL_SUITE_REP_SECONDS = 30
SKILL_DIRS = (
    ".agents/skills/optimize-campaign",
    ".agents/skills/optimize-speedometer",
    ".agents/skills/optimize-jetstream",
    ".agents/skills/chrome-cycle-profiling",
)
IGNORED_SKILL_GLOBS = (
    "*.pyc", "*.swp", "*.swo", "*~", ".#*", "#*#", ".DS_Store", "*.tmp",
)

# Two-sided 95% Student-t critical values by degrees of freedom.
T_CRIT_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
    14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
    20: 2.086, 25: 2.060, 30: 2.042,
}
# One-sided 80% Student-t quantiles (for the 80%-power MDE term).
T_POWER_80 = {
    1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906, 7: 0.896,
    8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876, 12: 0.873, 13: 0.870,
    14: 0.868, 15: 0.866, 16: 0.865, 17: 0.863, 18: 0.862, 19: 0.861,
    20: 0.860, 25: 0.856, 30: 0.854,
}


def t_lookup(table, df, asymptote):
    if df <= 0:
        return float("nan")
    if df in table:
        return table[df]
    if df >= 60:
        return asymptote
    # Floor to the nearest lower tabulated df (conservative: wider interval).
    return table[max(d for d in table if d <= df)]


def t_crit(df):
    return t_lookup(T_CRIT_95, df, 1.960)


def t_power(df):
    return t_lookup(T_POWER_80, df, 0.842)


def get_repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def sha256_path(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path):
    """Digest a benchmark payload tree by relative name and file content."""
    path = os.path.realpath(path)
    entries = []
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                raise RuntimeError(
                    f"benchmark payload contains a symlink: {full}"
                )
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                raise RuntimeError(
                    f"benchmark payload contains a symlink: {full}"
                )
            entries.append((os.path.relpath(full, path), sha256_path(full)))
    if not entries:
        raise RuntimeError(f"benchmark payload is empty: {path}")
    encoded = "".join(f"{digest}  {name}\n" for name, digest in entries)
    return hashlib.sha256(encoded.encode()).hexdigest()


def serve_payload_tree(path):
    """Serve a digest-bound payload on an ephemeral loopback port."""
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format_string, *args):
            pass

    handler = functools.partial(QuietHandler, directory=path)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()

    atexit.register(stop)
    return f"http://127.0.0.1:{server.server_port}/"


def artifact_ref(path, *, relative_to=None):
    path = os.path.realpath(path)
    stored = os.path.relpath(path, relative_to) if relative_to else path
    return {"path": stored, "sha256": sha256_path(path)}


def skill_tree_digest(cwd):
    entries = []
    for skill_dir in SKILL_DIRS:
        base = os.path.join(cwd, skill_dir)
        if not os.path.isdir(base):
            raise RuntimeError(f"skill directory is missing: {base}")
        for dirpath, dirnames, filenames in os.walk(base, followlinks=True):
            dirnames[:] = [name for name in dirnames if name != "__pycache__"]
            for name in filenames:
                if any(fnmatch.fnmatch(name, glob) for glob in IGNORED_SKILL_GLOBS):
                    continue
                full = os.path.join(dirpath, name)
                rel = f"{skill_dir}/{os.path.relpath(full, base)}"
                entries.append((rel, full))
    lines = [f"{sha256_path(full)}  {rel}\n" for rel, full in sorted(entries)]
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def capture_environment(required_role="any"):
    with open("/proc/sys/kernel/random/boot_id") as source:
        boot_id = source.read().strip().lower()
    with open("/proc/cpuinfo", errors="replace") as source:
        cpuinfo = source.read()
    model = next(
        (line.split(":", 1)[1].strip() for line in cpuinfo.splitlines()
         if line.lower().startswith("model name") and ":" in line),
        "",
    )
    detected = subprocess.run(
        ["systemd-detect-virt"], capture_output=True, text=True, check=False
    )
    virtualization = detected.stdout.strip() if detected.returncode == 0 else "none"
    if not model or (required_role != "development" and virtualization != "none"):
        raise RuntimeError(
            f"score evidence requires an identified bare-metal host; "
            f"cpu={model!r}, virtualization={virtualization!r}"
        )
    return {
        "host_name": socket.gethostname(),
        "host_boot_id": boot_id,
        "kernel_release": platform.release(),
        "cpu_model": model,
        "virtualization": virtualization,
    }


def git_value(root, *args):
    return subprocess.run(
        ["git", "-C", root, *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def harness_identity(cwd):
    cb = os.path.realpath(os.path.join(cwd, "third_party/crossbench/cb.py"))
    crossbench = os.path.dirname(cb)
    expected_match = re.search(
        r"'crossbench_revision':\s*'([0-9a-f]{40})'",
        open(os.path.join(cwd, "DEPS"), errors="replace").read(),
    )
    expected = expected_match.group(1) if expected_match else ""
    actual = git_value(crossbench, "rev-parse", "HEAD")
    dirty = git_value(crossbench, "status", "--porcelain", "--untracked-files=no")
    if not expected or actual != expected or dirty:
        raise RuntimeError(
            "Crossbench checkout is not the clean revision pinned by Chromium DEPS"
        )
    vpython = shutil.which("vpython3")
    if not vpython:
        raise RuntimeError("vpython3 is not on PATH")
    vpython = os.path.realpath(vpython)
    depot_root = git_value(os.path.dirname(vpython), "rev-parse", "--show-toplevel")
    depot_origin = git_value(depot_root, "remote", "get-url", "origin")
    depot_dirty = git_value(
        depot_root, "status", "--porcelain", "--untracked-files=no"
    )
    if (
        not depot_origin.rstrip("/").endswith("chromium/tools/depot_tools.git")
        or depot_dirty
    ):
        raise RuntimeError("vpython3 is not from a clean Chromium depot_tools checkout")
    return {
        "crossbench_revision": actual,
        "crossbench_cb": artifact_ref(cb),
        "vpython3": artifact_ref(vpython),
        "depot_tools_revision": git_value(depot_root, "rev-parse", "HEAD"),
        "depot_tools_origin": depot_origin,
    }


REQUIRED_RELEASE_GN_ARGS = {
    "is_official_build": "true",
    "is_debug": "false",
    "chrome_pgo_phase": "2",
    "use_thin_lto": "true",
}


def build_provenance(cwd, browser, required_role="any"):
    browser_path = os.path.realpath(os.path.join(cwd, browser))
    build_dir = os.path.dirname(browser_path)
    try:
        sha = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.SubprocessError:
        sha = "unknown"
    try:
        gn_output = subprocess.run(
            ["gn", "args", build_dir, "--list", "--short"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"cannot resolve GN args for {browser_path}: {exc}") from exc
    resolved = {}
    for line in gn_output.splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            resolved[name.strip()] = value.strip()
    mismatches = []
    if required_role != "development":
        mismatches = [
            f"{name}={resolved.get(name)!r} (need {expected})"
            for name, expected in REQUIRED_RELEASE_GN_ARGS.items()
            if resolved.get(name) != expected
        ]
        if mismatches:
            raise RuntimeError(
                "score build is not official PGO2 ThinLTO: "
                + ", ".join(mismatches)
            )
    if required_role == "release" and resolved.get("symbol_level") != "0":
        raise RuntimeError(
            f"authoritative score build requires symbol_level=0, got "
            f"{resolved.get('symbol_level')!r}"
        )
    return {
        "resolved_browser": browser_path,
        "browser_sha256": sha256_path(browser_path),
        "git_sha": sha,
        "gn_args_sha256": hashlib.sha256(gn_output.encode()).hexdigest(),
        "build_role": required_role,
        "release_args_enforced": required_role != "development",
        "symbol_level": resolved.get("symbol_level"),
        "enable_profiling": resolved.get("enable_profiling"),
        "required_release_args": REQUIRED_RELEASE_GN_ARGS,
    }


def check_feature_registered(cwd, feature):
    """Verify the feature name appears in source; unknown features are silently
    ignored by Chrome, which would make the enabled arm identical to baseline."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "grep", "-l", "-F", f'"{feature}"',
             "--", "*.cc", "*.h", "*.json5"],
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        print("warning: could not verify feature registration", file=sys.stderr)
        return True
    if result.returncode != 0 or not result.stdout.strip():
        print(
            f"error: feature '{feature}' is not defined anywhere in the tree. "
            "Chrome silently ignores unknown --enable-features values, so this "
            "A/B would compare identical configurations. Land the feature "
            "definition first, or pass --skip-feature-check if you are certain.",
            file=sys.stderr,
        )
        return False
    return True


def run_single_rep(browser, out_dir, stories, flag_option, state_str, rep_index,
                   block_label, cwd, *, adapter,
                   benchmark_source=None, benchmark_url=None, driver_path=None,
                   iteration_count=None, worst_case_count=None):
    print(f"[Block {block_label} - Rep {rep_index+1}] Running {state_str}...")
    rep_out_dir = os.path.join(out_dir, f"rep_{rep_index}_{block_label}_{state_str.lower()}")
    full_out_dir = os.path.join(cwd, rep_out_dir)
    if os.path.exists(full_out_dir):
        shutil.rmtree(full_out_dir)

    cmd = [
        "vpython3", "./third_party/crossbench/cb.py",
        *adapter.crossbench_args(benchmark_source, benchmark_url),
        "--env-validation=warn",
        f"--browser={browser}",
        "--headless",
        "--no-sandbox",
        "--repetitions=1",
        f"--out-dir={rep_out_dir}",
        f"--stories={stories}"
    ]
    if driver_path:
        cmd.append(f"--driver-path={driver_path}")
    if iteration_count is not None:
        cmd.append(f"--iteration-count={int(iteration_count)}")
    if worst_case_count is not None:
        cmd.append(f"--worst-case-count={int(worst_case_count)}")
    if flag_option:
        cmd.append(flag_option)

    subprocess.run(cmd, cwd=cwd, check=True)
    return rep_out_dir


def parse_run_metric_artifacts(cwd, out_dir, *, adapter):
    """Return parsed per-repetition metrics for one Crossbench invocation.

    Only per-iteration result files (where Score is a scalar) are trusted;
    aggregate files repeat the same numbers and would multiply-count them.
    """
    runs = []
    for root, dirs, files in os.walk(os.path.join(cwd, out_dir)):
        for file in files:
            if file != adapter.result_filename:
                continue
            path = os.path.join(root, file)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                print(f"Error parsing {path}: {e}", file=sys.stderr)
                continue
            parsed = adapter.parse_result(data)
            if parsed is None:
                continue
            runs.append((
                parsed.score,
                parsed.workloads,
                os.path.realpath(path),
                parsed.components,
            ))
    return runs


def parse_run_metrics(cwd, out_dir, *, adapter):
    return [
        item[:2] for item in parse_run_metric_artifacts(
            cwd, out_dir, adapter=adapter
        )
    ]


def summarize_block_diffs(block_diffs):
    """Paired log-ratio statistics over per-block observations d_b.

    Positive d_b means arm B is better. Returns None with fewer than 2 blocks.
    """
    n = len(block_diffs)
    if n < 2:
        return None
    mean_d = sum(block_diffs) / n
    var_d = sum((x - mean_d) ** 2 for x in block_diffs) / (n - 1)
    std_err = math.sqrt(var_d) / math.sqrt(n)
    df = n - 1
    tc = t_crit(df)
    ci_lower_log = mean_d - tc * std_err
    ci_upper_log = mean_d + tc * std_err

    def pct(x):
        return (math.exp(x) - 1.0) * 100.0

    sig_threshold_pct = pct(tc * std_err)
    mde80_pct = pct((tc + t_power(df)) * std_err)
    ci = (pct(ci_lower_log), pct(ci_upper_log))
    return {
        "n_blocks": n,
        "delta_pct": pct(mean_d),
        "ci_95_pct": [ci[0], ci[1]],
        "std_err_log": std_err,
        "t_stat": (mean_d / std_err) if std_err > 0 else 0.0,
        "significance_threshold_pct": sig_threshold_pct,
        "mde_80_power_pct": mde80_pct,
        "is_stat_sig": (ci[0] > 0 and ci[1] > 0) or (ci[0] < 0 and ci[1] < 0),
    }


def suite_block_diffs(block_data):
    diffs = []
    for b in block_data:
        if not b["a_scores"] or not b["b_scores"]:
            continue
        mean_ln_a = sum(math.log(x) for x in b["a_scores"]) / len(b["a_scores"])
        mean_ln_b = sum(math.log(x) for x in b["b_scores"]) / len(b["b_scores"])
        diffs.append(mean_ln_b - mean_ln_a)
    return diffs


def per_story_stats(block_data, *, adapter):
    """Per-story block log-diffs from per-iteration total times.

    Story values are times (lower is better), so the sign is flipped:
    d_b = mean(ln A_time) - mean(ln B_time); positive = B faster.
    """
    stories = set()
    for b in block_data:
        for arm in ("a_stories", "b_stories"):
            for rep in b.get(arm, []):
                stories.update(rep.keys())

    results = {}
    for story in sorted(stories):
        diffs = []
        for b in block_data:
            a_vals = [rep[story] for rep in b.get("a_stories", []) if story in rep]
            b_vals = [rep[story] for rep in b.get("b_stories", []) if story in rep]
            if not a_vals or not b_vals:
                continue
            mean_ln_a = sum(math.log(x) for x in a_vals) / len(a_vals)
            mean_ln_b = sum(math.log(x) for x in b_vals) / len(b_vals)
            if adapter.workload_value_direction == "higher":
                diffs.append(mean_ln_b - mean_ln_a)
            else:
                diffs.append(mean_ln_a - mean_ln_b)
        stats = summarize_block_diffs(diffs)
        if stats is None:
            continue
        stats["stat_sig_regression"] = stats["ci_95_pct"][1] < 0.0
        stats["exceeds_2pct_regression"] = (
            stats["stat_sig_regression"] and stats["delta_pct"] <= -2.0
        )
        results[story] = stats
    return results


def manifest_block_details(block_data):
    """Keep the runner/ledger block contract in one testable serializer."""
    fields = (
        "block", "pattern", "a_scores", "b_scores",
        "a_stories", "b_stories", "a_results", "b_results",
        "a_components", "b_components",
    )
    return [{key: block[key] for key in fields if key in block}
            for block in block_data]


def main():
    parser = argparse.ArgumentParser(description=(
        "Run randomized block-interleaved (ABBA/BAAB) A/B or A/A "
        "Crossbench benchmark."
    ))
    parser.add_argument(
        "--benchmark", default="speedometer3",
        choices=benchmark_adapters.available_benchmarks(),
        help="Benchmark adapter (default: speedometer3)",
    )
    parser.add_argument(
        "--benchmark-source", default=None,
        help="Payload source: Speedometer local; JetStream live, official, "
        "local, or investigation-only custom",
    )
    parser.add_argument(
        "--benchmark-url", default=None,
        help="URL for --benchmark-source=local",
    )
    parser.add_argument(
        "--benchmark-payload-path", default=None,
        help="Local payload tree served and digest-bound by this runner",
    )
    parser.add_argument(
        "--driver-path", default=None,
        help="Explicit matching chromedriver path (useful for local builds)",
    )
    parser.add_argument(
        "--iteration-count", type=int, default=None,
        help="JetStream iterations nested inside each page-load repetition",
    )
    parser.add_argument(
        "--worst-case-count", type=int, default=None,
        help="JetStream internal worst-case component count",
    )
    parser.add_argument("--browser", default="out/release/chrome", help="Browser build path (aa and feature modes)")
    parser.add_argument("--browser-a", default="", help="Arm A browser path (two-binary mode)")
    parser.add_argument("--browser-b", default="", help="Arm B browser path (two-binary mode)")
    parser.add_argument("--feature", default="", help="Chromium Feature flag name to test")
    parser.add_argument("--aa", action="store_true", help="Run in genuine A/A baseline mode (identical binaries/flags on both arms)")
    parser.add_argument("--blocks", type=int, default=32, help="Even number of ABBA/BAAB blocks (default: 32 = 64 paired reps per arm)")
    parser.add_argument(
        "--required-build-role", choices=("any", "release", "development"),
        default="any",
        help="development permits functional characterization builds; release "
        "requires a symbol-free official PGO2 ThinLTO binary",
    )
    parser.add_argument(
        "--stories", default=None,
        help="Crossbench story/workload selector (benchmark default if omitted)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for block ordering (default: a fresh recorded seed)",
    )
    parser.add_argument("--enable-features", default="",
                        help="Comma-separated features enabled on BOTH arms "
                        "(aa and two-binary modes only). Required for bisecting "
                        "flag-gated campaign commits: without it, two-binary arms "
                        "both run baseline behavior and cannot differ.")
    parser.add_argument("--skip-feature-check", action="store_true",
                        help="Skip verifying that --feature is defined in the source tree")
    args = parser.parse_args()
    adapter = benchmark_adapters.get_adapter(args.benchmark)
    if adapter.benchmark_id != "jetstream3" and (
        args.iteration_count is not None or args.worst_case_count is not None
    ):
        parser.error("iteration/worst-case counts are JetStream-only")
    if args.iteration_count is not None and args.iteration_count < 1:
        parser.error("--iteration-count must be positive")
    if args.worst_case_count is not None and args.worst_case_count < 1:
        parser.error("--worst-case-count must be positive")
    if args.stories is None:
        args.stories = adapter.default_workload_selector
    source = args.benchmark_source or adapter.score_sources[0]
    try:
        payload_provenance = adapter.source_provenance(source, args.benchmark_url)
        adapter.crossbench_args(source, args.benchmark_url)
    except ValueError as exc:
        parser.error(str(exc))
    if args.benchmark_payload_path:
        payload_path = os.path.realpath(
            os.path.join(get_repo_root(), args.benchmark_payload_path)
        )
        if source != "local":
            parser.error("--benchmark-payload-path requires --benchmark-source=local")
        if not os.path.isdir(payload_path):
            parser.error(f"benchmark payload directory does not exist: {payload_path}")
        payload_digest = sha256_tree(payload_path)
        args.benchmark_url = serve_payload_tree(payload_path)
        payload_provenance = adapter.source_provenance(
            source, args.benchmark_url
        )
        payload_provenance.update({
            "resolved_payload_path": payload_path,
            "payload_sha256": payload_digest,
            "content_pinned": True,
            "served_by_runner": True,
        })
    if args.required_build_role == "release":
        if payload_provenance["investigation_only"]:
            parser.error(
                "an investigation-only benchmark payload cannot produce score evidence"
            )
        if not payload_provenance["content_pinned"]:
            parser.error(
                "authoritative score evidence requires an immutable benchmark "
                "payload; use --benchmark-source=local with "
                "--benchmark-payload-path"
            )
    if args.blocks < 2 or args.blocks % 2:
        print("Error: --blocks must be even for exact ABBA/BAAB balance.", file=sys.stderr)
        sys.exit(1)

    two_binary = bool(args.browser_a or args.browser_b)
    mode_count = sum([args.aa, bool(args.feature), two_binary])
    if mode_count != 1:
        print("Error: choose exactly one mode: --aa, --feature=<flag>, or "
              "--browser-a/--browser-b.", file=sys.stderr)
        sys.exit(1)
    if two_binary and not (args.browser_a and args.browser_b):
        print("Error: two-binary mode requires both --browser-a and --browser-b.", file=sys.stderr)
        sys.exit(1)
    if args.enable_features and args.feature:
        print("Error: --enable-features applies to both arms and cannot combine "
              "with --feature mode, which manages the flag itself.", file=sys.stderr)
        sys.exit(1)

    cwd = get_repo_root()
    environment = capture_environment(args.required_build_role)
    harness = harness_identity(cwd)
    skill_digest = skill_tree_digest(cwd)
    expected_skill_digest = os.environ.get("OPTIMIZE_CAMPAIGN_SKILL_DIGEST", skill_digest)
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_skill_digest)
        or expected_skill_digest != skill_digest
    ):
        print(
            "Error: executing skill tree does not match the remote wrapper digest.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.skip_feature_check:
        if args.feature and not check_feature_registered(cwd, args.feature):
            sys.exit(2)
        # A typo here is worse than in --feature mode: both arms silently run
        # baseline behavior and a bisect goes blind.
        for name in filter(None, (n.strip() for n in args.enable_features.split(","))):
            if not check_feature_registered(cwd, name):
                sys.exit(2)

    scratch_dir = os.path.join(cwd, "scratch")
    os.makedirs(scratch_dir, exist_ok=True)
    temp_results_dir = tempfile.mkdtemp(prefix="results_ab_interleaved_", dir=scratch_dir)
    rel_out_dir = os.path.relpath(temp_results_dir, cwd)
    evidence_name = f"ab_evidence_{secrets.token_hex(12)}"
    evidence_dir = os.path.join(scratch_dir, evidence_name)
    os.makedirs(evidence_dir, exist_ok=True)
    actual_seed = args.seed if args.seed is not None else secrets.randbits(32)
    rng = random.Random(actual_seed)

    if args.aa:
        mode_str = "GENUINE A/A CALIBRATION"
        mode_key = "aa"
    elif two_binary:
        mode_str = f"TWO-BINARY A/B ({args.browser_a} vs {args.browser_b})"
        mode_key = "ab2"
    else:
        mode_str = f"FEATURE A/B ({args.feature})"
        mode_key = "ab"

    print(f"\n=======================================================")
    print(f" RANDOMIZED BLOCK-INTERLEAVED BENCHMARK (ABBA/BAAB)")
    print(f" Mode         : {mode_str}")
    print(f" Output Dir   : {rel_out_dir}")
    print(f" Blocks       : {args.blocks} (Total paired runs: {args.blocks * 2} per arm)")
    print(f" Benchmark    : {adapter.benchmark_id}")
    print(f" Workloads    : {args.stories}")
    print(f" Seed         : {actual_seed}")
    print(f"=======================================================\n")

    common_flags = (
        f"--enable-features={args.enable_features}" if args.enable_features else ""
    )

    def arm_config(enable):
        """Return (browser, flag_option, state_str) for one arm."""
        if args.aa:
            return args.browser, common_flags, ("ARM_B" if enable else "ARM_A")
        if two_binary:
            return (
                (args.browser_b if enable else args.browser_a),
                common_flags,
                ("ARM_B" if enable else "ARM_A"),
            )
        return (
            args.browser,
            (f"--enable-features={args.feature}" if enable else f"--disable-features={args.feature}"),
            ("ENABLED" if enable else "DISABLED"),
        )

    block_data = []
    block_patterns = ["ABBA"] * ((args.blocks + 1) // 2)
    block_patterns += ["BAAB"] * (args.blocks // 2)
    rng.shuffle(block_patterns)
    total_rep = 0
    arm_browser_paths = {
        "a": os.path.realpath(os.path.join(cwd, args.browser_a or args.browser)),
        "b": os.path.realpath(os.path.join(cwd, args.browser_b or args.browser)),
    }
    initial_browser_hashes = {
        arm: sha256_path(path) for arm, path in arm_browser_paths.items()
    }
    run_started_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    run_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    observed_workloads = None

    for b_idx in range(args.blocks):
        pattern = block_patterns[b_idx]
        print(f"\n--- Block {b_idx + 1}/{args.blocks} Pattern: {pattern} ---")
        a_scores, b_scores = [], []
        a_stories, b_stories = [], []
        a_components, b_components = [], []
        a_results, b_results = [], []

        for char in pattern:
            enable = (char == "B")
            browser, flag_option, state_str = arm_config(enable)
            block_label = f"B{b_idx+1}_{char}"
            rep_started_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
            out_d = run_single_rep(
                browser, rel_out_dir, args.stories, flag_option, state_str,
                total_rep, block_label, cwd, adapter=adapter,
                benchmark_source=source, benchmark_url=args.benchmark_url,
                driver_path=args.driver_path,
                iteration_count=args.iteration_count,
                worst_case_count=args.worst_case_count,
            )
            rep_finished_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
            runs = parse_run_metric_artifacts(cwd, out_d, adapter=adapter)
            if len(runs) != 1:
                print(
                    f"Error: repetition {total_rep + 1} emitted {len(runs)} "
                    f"scalar {adapter.crossbench_name} results; expected "
                    "exactly one.",
                    file=sys.stderr,
                )
                sys.exit(1)
            score, stories, source_result, components = runs[0]
            expected_count = adapter.expected_workload_count(args.stories)
            if expected_count is not None and len(stories) != expected_count:
                print(
                    f"Error: selector {args.stories!r} produced {len(stories)} "
                    f"workloads; {adapter.benchmark_id} expects "
                    f"{expected_count}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            current_workloads = set(stories)
            if observed_workloads is None:
                observed_workloads = current_workloads
            elif current_workloads != observed_workloads:
                print(
                    "Error: observed workload set changed between repetitions.",
                    file=sys.stderr,
                )
                sys.exit(1)
            copied_name = f"rep-{total_rep + 1:04d}-{block_label}-{state_str.lower()}.json"
            copied_result = os.path.join(evidence_dir, copied_name)
            shutil.copy2(source_result, copied_result)
            result = {
                **artifact_ref(copied_result, relative_to=os.path.join(cwd, "scratch")),
                "score": score,
                "block": b_idx + 1,
                "position": len(a_scores) + len(b_scores) + 1,
                "arm": "b" if enable else "a",
                "started_monotonic_raw_ns": rep_started_ns,
                "finished_monotonic_raw_ns": rep_finished_ns,
            }
            if enable:
                b_scores.append(score)
                b_stories.append(stories)
                b_components.append(components)
                b_results.append(result)
            else:
                a_scores.append(score)
                a_stories.append(stories)
                a_components.append(components)
                a_results.append(result)
            total_rep += 1

        block_data.append({
            "block": b_idx + 1, "pattern": pattern,
            "a_scores": a_scores, "b_scores": b_scores,
            "a_stories": a_stories, "b_stories": b_stories,
            "a_components": a_components, "b_components": b_components,
            "a_results": a_results, "b_results": b_results,
        })

    run_finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    run_finished_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    minimum_duration_ns = (
        args.blocks * 4 * MIN_FULL_SUITE_REP_SECONDS * 1_000_000_000
        if adapter.benchmark_id == "speedometer3" and args.stories == "all"
        else 0
    )
    if run_finished_ns - run_started_ns < minimum_duration_ns:
        print(
            "Error: full-suite run completed below the conservative wall-time "
            "floor; refusing implausible checkpoint evidence.",
            file=sys.stderr,
        )
        sys.exit(1)
    final_harness = harness_identity(cwd)
    final_skill_digest = skill_tree_digest(cwd)
    if final_harness != harness or final_skill_digest != skill_digest:
        print(
            "Error: benchmark harness or campaign skill tree changed during the run.",
            file=sys.stderr,
        )
        sys.exit(1)
    final_browser_hashes = {
        arm: sha256_path(path) for arm, path in arm_browser_paths.items()
    }
    if final_browser_hashes != initial_browser_hashes:
        print("Error: a measured browser changed during the run.", file=sys.stderr)
        sys.exit(1)
    if args.benchmark_payload_path and sha256_tree(payload_path) != payload_digest:
        print("Error: benchmark payload changed during the run.", file=sys.stderr)
        sys.exit(1)

    suite = summarize_block_diffs(suite_block_diffs(block_data))
    if suite is None:
        print("Error: fewer than 2 complete blocks; no statistics possible.", file=sys.stderr)
        sys.exit(1)
    stories = per_story_stats(block_data, adapter=adapter)

    stat_sig_regressions = sorted(
        (name for name, s in stories.items() if s["stat_sig_regression"]),
        key=lambda name: stories[name]["delta_pct"],
    )
    hard_story_regressions = [
        name for name in stat_sig_regressions if stories[name]["exceeds_2pct_regression"]
    ]
    ci_low, ci_high = suite["ci_95_pct"]
    passes_regression_guardrail = (ci_low >= -2.0) and not hard_story_regressions
    achieves_5pct_goal = (ci_low >= 5.0)

    print(f"\n=======================================================")
    print(f" STATISTICAL RESULT SUMMARY ({mode_str})")
    print(f"=======================================================")
    print(f"  Valid Blocks Analyzed        : {suite['n_blocks']} blocks")
    print(f"-------------------------------------------------------")
    print(f"  Geometric Score Delta        : {suite['delta_pct']:+.2f}%")
    print(f"  95% Confidence Interval      : [{ci_low:+.2f}%, {ci_high:+.2f}%]")
    print(f"  Significance Threshold       : +/-{suite['significance_threshold_pct']:.2f}%")
    print(f"  MDE (80% power)              : +/-{suite['mde_80_power_pct']:.2f}%")
    print(f"  Block t-statistic            : {suite['t_stat']:.3f}")
    print(f"  Passes Regression Guardrail  : {'YES' if passes_regression_guardrail else 'NO'}")

    if args.aa:
        print(f"  A/A Calibration Status       : {'PASSED (No false positive)' if not suite['is_stat_sig'] else 'HIGH NOISE FLOOR'}")
    else:
        print(f"  Statistically Significant    : {'PROVISIONAL PASS' if suite['is_stat_sig'] else 'NO (CI crosses 0%)'}")
        print(f"  Achieves 5% Goal Bar         : {'YES (CI_lower >= +5.0%)' if achieves_5pct_goal else 'NO'}")

    worst = sorted(stories.items(), key=lambda kv: kv[1]["delta_pct"])[:5]
    if worst:
        print(f"-------------------------------------------------------")
        print(f"  Worst stories (positive = B faster):")
        for name, s in worst:
            flag = " ** STAT-SIG REGRESSION **" if s["stat_sig_regression"] else ""
            print(f"    {name:45s} {s['delta_pct']:+6.2f}% "
                  f"[{s['ci_95_pct'][0]:+.2f}%, {s['ci_95_pct'][1]:+.2f}%]{flag}")
    if stat_sig_regressions:
        print(f"  NOTE: ~30 stories at 95% CI yield ~1 false positive per run; "
              f"confirm flagged stories with a targeted rerun "
              f"(--stories={stat_sig_regressions[0]}).")
    print(f"=======================================================\n")

    res_manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "runner": MANIFEST_RUNNER,
        "benchmark": adapter.benchmark_id,
        "metric_model": adapter.metric_model,
        "workload_value_direction": adapter.workload_value_direction,
        "payload_provenance": payload_provenance,
        "iteration_count": args.iteration_count,
        "worst_case_count": args.worst_case_count,
        "mode": mode_key,
        "feature": args.feature,
        "enable_features": args.enable_features,
        "browser": args.browser,
        "browser_a": args.browser_a,
        "browser_b": args.browser_b,
        "stories": args.stories,
        "observed_workloads": sorted(observed_workloads or ()),
        "expected_workload_count": adapter.expected_workload_count(
            args.stories
        ),
        "blocks": suite["n_blocks"],
        "seed": actual_seed,
        "schedule": block_patterns,
        "started_at": run_started_at,
        "finished_at": run_finished_at,
        "started_monotonic_raw_ns": run_started_ns,
        "finished_monotonic_raw_ns": run_finished_ns,
        "minimum_duration_ns": minimum_duration_ns,
        "capture_environment": environment,
        "harness": harness,
        "skill_tree_sha256": skill_digest,
        "evidence_dir": evidence_name,
        "block_details": manifest_block_details(block_data),
        "geometric_delta_pct": suite["delta_pct"],
        "ci_95_pct": suite["ci_95_pct"],
        "significance_threshold_pct": suite["significance_threshold_pct"],
        "mde_80_power_pct": suite["mde_80_power_pct"],
        "is_stat_sig": suite["is_stat_sig"],
        "passes_regression_guardrail": passes_regression_guardrail,
        "achieves_5pct_goal": achieves_5pct_goal,
        "per_story": stories,
        "stat_sig_story_regressions": stat_sig_regressions,
        "build_provenance": {
            "a": build_provenance(
                cwd, args.browser_a or args.browser, args.required_build_role
            ),
            "b": build_provenance(
                cwd, args.browser_b or args.browser, args.required_build_role
            ),
        },
    }
    if any(
        res_manifest["build_provenance"][arm]["browser_sha256"]
        != initial_browser_hashes[arm]
        for arm in ("a", "b")
    ):
        print("Error: final build provenance does not match the measured browser.", file=sys.stderr)
        sys.exit(1)
    manifest_path = os.path.join(cwd, "scratch", "ab_results_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(res_manifest, f, indent=2)

    # Explicit cleanup of unique temp result directory
    shutil.rmtree(temp_results_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
