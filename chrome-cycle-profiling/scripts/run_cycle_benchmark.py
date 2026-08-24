#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

_CAMPAIGN_SCRIPTS = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "optimize-campaign", "scripts")
)
if _CAMPAIGN_SCRIPTS not in sys.path:
    sys.path.append(_CAMPAIGN_SCRIPTS)
import benchmark_adapters


PROCESS_POLL_INTERVAL_SECONDS = 0.25
ANALYSIS_REJECTED_EXIT_CODE = 3
REQUIRED_RELEASE_GN_ARGS = {
    "is_official_build": "true",
    "is_debug": "false",
    "chrome_pgo_phase": "2",
    "use_thin_lto": "true",
}


def build_provenance(cwd, browser):
    browser_path = os.path.realpath(os.path.join(cwd, browser))
    build_dir = os.path.dirname(browser_path)
    completed = subprocess.run(
        ["gn", "args", build_dir, "--list", "--short"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    resolved = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        resolved[name.strip()] = value.strip()
    mismatches = [
        f"{name}={resolved.get(name)!r} (need {expected})"
        for name, expected in REQUIRED_RELEASE_GN_ARGS.items()
        if resolved.get(name) != expected
    ]
    if mismatches:
        raise RuntimeError(
            "Profiling build is not an official PGO/ThinLTO release-like build: "
            + ", ".join(mismatches)
        )
    return {
        "resolved_browser": browser_path,
        "gn_args_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "required_release_args": REQUIRED_RELEASE_GN_ARGS,
        "symbol_level": resolved.get("symbol_level"),
        "enable_profiling": resolved.get("enable_profiling"),
        "full_stack_no_inline": resolved.get(
            "enable_full_stack_frames_for_profiling"
        ),
    }


def snapshot_chrome_processes(root_pid, browser_name):
    processes = {}
    parent_by_pid = {}
    cmdline_by_pid = {}
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            with open(f"/proc/{pid}/stat", "r") as stat_file:
                stat = stat_file.read()
            close_paren = stat.rfind(")")
            parent_by_pid[pid] = int(stat[close_paren + 2 :].split()[1])
            with open(f"/proc/{pid}/cmdline", "rb") as cmdline_file:
                raw_items = [
                    item.decode(errors="replace")
                    for item in cmdline_file.read().split(b"\0")
                    if item
                ]
                if len(raw_items) == 1 and " " in raw_items[0]:
                    try:
                        cmdline_by_pid[pid] = shlex.split(raw_items[0])
                    except ValueError:
                        cmdline_by_pid[pid] = raw_items[0].split()
                else:
                    cmdline_by_pid[pid] = raw_items
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            continue

    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parent_by_pid.items():
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True

    for pid in descendants:
        command = cmdline_by_pid.get(pid, [])
        if not command or os.path.basename(command[0]) != browser_name:
            continue
        process_type = next(
            (arg.split("=", 1)[1] for arg in command if arg.startswith("--type=")),
            "browser",
        )
        role = "gpu" if process_type == "gpu-process" else process_type
        subtype = next(
            (
                arg.split("=", 1)[1]
                for arg in command
                if arg.startswith("--utility-sub-type=")
            ),
            None,
        )
        processes[pid] = {"pid": pid, "role": role, "subtype": subtype}
    return processes


def get_repo_root():
    return os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    )


def parse_mono_intervals(out_dir, cwd):
    intervals = []
    outer_intervals = []

    for root, dirs, files in os.walk(os.path.join(cwd, out_dir)):
        for file in files:
            if file == "browser.stdout.log":
                log_file_path = os.path.join(root, file)
                pending_start = None
                score_starts = {}
                with open(log_file_path, "r") as f:
                    for line in f:
                        score = re.search(
                            r"\[SP3_SCORE_TIME\]\s+(.+?):\s*([\d.]+)", line
                        )
                        if score:
                            name, timestamp = score.group(1), float(score.group(2))
                            if name == "sp3-measurement-start":
                                if pending_start is not None:
                                    raise RuntimeError(
                                        f"Unmatched measurement start in {log_file_path}"
                                    )
                                pending_start = timestamp
                            elif name == "sp3-measurement-end":
                                if pending_start is None or timestamp <= pending_start:
                                    raise RuntimeError(
                                        f"Invalid measurement end in {log_file_path}"
                                    )
                                outer_intervals.append({
                                    "start_time_mono": pending_start,
                                    "end_time_mono": timestamp,
                                    "browser_log": log_file_path,
                                })
                                pending_start = None
                            elif name.endswith("-sync-end"):
                                base = name[: -len("-sync-end")]
                                start = score_starts.pop(base + "-start", None)
                                if start is None:
                                    raise RuntimeError(
                                        f"Unmatched score end {name} in {log_file_path}"
                                    )
                                suite, test = base.split(".", 1)
                                intervals.append({
                                    "start_time_mono": start,
                                    "end_time_mono": timestamp,
                                    "browser_log": log_file_path,
                                    "suite": suite,
                                    "test": test,
                                    "phase": "sync",
                                    "group": (
                                        f"{os.path.relpath(log_file_path, cwd)}|{suite}"
                                    ),
                                })
                            elif name.endswith("-async-end"):
                                base = name[: -len("-async-end")]
                                start = score_starts.pop(base + "-async-start", None)
                                if start is None:
                                    raise RuntimeError(
                                        f"Unmatched score end {name} in {log_file_path}"
                                    )
                                suite, test = base.split(".", 1)
                                intervals.append({
                                    "start_time_mono": start,
                                    "end_time_mono": timestamp,
                                    "browser_log": log_file_path,
                                    "suite": suite,
                                    "test": test,
                                    "phase": "async",
                                    "group": (
                                        f"{os.path.relpath(log_file_path, cwd)}|{suite}"
                                    ),
                                })
                            elif name.endswith("-start"):
                                if name in score_starts:
                                    raise RuntimeError(
                                        f"Repeated score start {name} in {log_file_path}"
                                    )
                                score_starts[name] = timestamp
                        if "[SP3_MONO_TIME]" in line:
                            if "sp3-measurement-start" in line:
                                m = re.search(
                                    r"sp3-measurement-start:\s*([\d\.]+)", line
                                )
                                if m:
                                    if pending_start is not None:
                                        raise RuntimeError(
                                            f"Unmatched measurement start in {log_file_path}"
                                        )
                                    pending_start = float(m.group(1))
                            elif "sp3-measurement-end" in line:
                                m = re.search(r"sp3-measurement-end:\s*([\d\.]+)", line)
                                if m:
                                    if pending_start is None:
                                        raise RuntimeError(
                                            f"Unmatched measurement end in {log_file_path}"
                                        )
                                    end_time = float(m.group(1))
                                    if end_time <= pending_start:
                                        raise RuntimeError(
                                            f"Invalid measurement interval in {log_file_path}"
                                        )
                                    outer_intervals.append(
                                        {
                                            "start_time_mono": pending_start,
                                            "end_time_mono": end_time,
                                            "browser_log": log_file_path,
                                        }
                                    )
                                    pending_start = None
                if pending_start is not None:
                    raise RuntimeError(
                        f"Unmatched measurement start in {log_file_path}"
                    )
                if score_starts:
                    raise RuntimeError(
                        f"Unmatched score starts in {log_file_path}: "
                        + ", ".join(sorted(score_starts)[:3])
                    )
    return (
        sorted(intervals, key=lambda interval: interval["start_time_mono"]),
        sorted(outer_intervals, key=lambda interval: interval["start_time_mono"]),
    )


def parse_jetstream_mono_intervals(out_dir, cwd):
    intervals = []
    outer_intervals = []

    for root, dirs, files in os.walk(os.path.join(cwd, out_dir)):
        if "performance.entries.json" in files:
            entry_path = os.path.join(root, "performance.entries.json")
            try:
                with open(entry_path, "r") as f:
                    data = json.load(f)
            except Exception:
                continue

            story = None
            parts = pathlib.Path(entry_path).parts
            if "stories" in parts:
                idx = parts.index("stories")
                if idx + 1 < len(parts):
                    story = parts[idx + 1]

            start_time = None
            end_time = None

            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0:
                    val_time = float(val[0])
                    if story and key.startswith(f"mark/{story}") and key.endswith("/startTime"):
                        start_time = val_time
                    elif key.startswith("mark/update-ui") and key.endswith("/startTime"):
                        end_time = val_time

            if start_time is not None and end_time is not None and end_time > start_time:
                rel_log = os.path.relpath(entry_path, cwd)
                intervals.append({
                    "start_time_mono": start_time / 1000.0,
                    "end_time_mono": end_time / 1000.0,
                    "browser_log": entry_path,
                    "suite": story or "jetstream",
                    "test": "run",
                    "phase": "run",
                    "group": f"{rel_log}|{story}",
                })
                outer_intervals.append({
                    "start_time_mono": start_time / 1000.0,
                    "end_time_mono": end_time / 1000.0,
                    "browser_log": entry_path,
                })
    return (
        sorted(intervals, key=lambda interval: interval["start_time_mono"]),
        sorted(outer_intervals, key=lambda interval: interval["start_time_mono"]),
    )


def run_analyzer(command, cwd):
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode not in (0, ANALYSIS_REJECTED_EXIT_CODE):
        raise subprocess.CalledProcessError(completed.returncode, command)
    return completed.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run benchmark full Chrome process-tree perf cycle sampling with V8 basic-prof symbolization."
    )
    parser.add_argument(
        "--benchmark", default="speedometer3",
        choices=benchmark_adapters.available_benchmarks(),
    )
    parser.add_argument("--benchmark-source", default=None)
    parser.add_argument(
        "--browser",
        default="out/perf/chrome",
        help="Browser build path (default: out/perf/chrome)",
    )
    parser.add_argument(
        "--stories", default="all", help="Stories to run (default: all)"
    )
    parser.add_argument(
        "--repetitions", type=int, default=16,
        help=(
            "Number of repetitions (default: 16; per-story decomposition "
            "needs enough samples in every story to clear its local "
            "marginal-share floor)"
        ),
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Capture perf.data without producing the overlap-aware candidate frontier",
    )
    parser.add_argument(
        "--enable-features",
        default=None,
        help=(
            "Comma-separated Chrome features passed to Crossbench. Defaults to "
            "the campaign flag (e.g. Speedometer3Optimizations / JetStream3Optimizations); "
            "pass an empty value for a baseline capture."
        ),
    )
    parser.add_argument(
        "--min-share",
        type=float,
        default=0.003,
        help="Fractional inclusive-share floor for candidate eligibility",
    )
    parser.add_argument(
        "--min-marginal-share",
        type=float,
        default=0.003,
        help="Fractional profile-share floor for the exhaustive candidate inventory",
    )
    args = parser.parse_args()
    adapter = benchmark_adapters.get_adapter(args.benchmark)
    if adapter.benchmark_id not in ("speedometer3", "jetstream3"):
        parser.error(f"unsupported benchmark {args.benchmark}")

    if args.enable_features is None:
        args.enable_features = (
            "Speedometer3Optimizations"
            if adapter.benchmark_id == "speedometer3"
            else "JetStream3Optimizations"
        )

    cwd = get_repo_root()
    provenance = build_provenance(cwd, args.browser)
    scratch_dir = os.path.join(cwd, "scratch")
    os.makedirs(scratch_dir, exist_ok=True)
    temp_results_dir = tempfile.mkdtemp(
        prefix="results_perf_sampling_", dir=scratch_dir
    )
    rel_out_dir = os.path.relpath(temp_results_dir, cwd)

    perf_data_file = os.path.join(temp_results_dir, "perf_sampling.data")

    if adapter.benchmark_id == "speedometer3":
        cb_benchmark = "speedometer_3.0"
        cb_source_flags = ["--network=third_party/speedometer/v3.0"]
    else:
        cb_benchmark = "jetstream_3.0"
        source = args.benchmark_source or "custom"
        cb_source_flags = [f"--{source}", "--probe=performance.entries"]

    cb_cmd = [
        "vpython3",
        "./third_party/crossbench/cb.py",
        cb_benchmark,
        *cb_source_flags,
        "--env-validation=warn",
        f"--browser={args.browser}",
        "--headless",
        "--no-sandbox",
        "--js-flags=--perf-basic-prof",
        f"--repetitions={args.repetitions}",
        f"--out-dir={os.path.join(rel_out_dir, 'cb')}",
        f"--stories={args.stories}",
    ]
    if args.enable_features:
        cb_cmd.append(f"--enable-features={args.enable_features}")

    print(f"\n=======================================================")
    print(f" FULL CHROME PROCESS TREE PERF SAMPLING (-k mono)")
    print(f" Output Data : {perf_data_file}")
    print(f" Output Dir  : {rel_out_dir}")
    print(f" Browser     : {args.browser}")
    print(f" Stories     : {args.stories}")
    print(f"=======================================================\n")

    perf_cmd = [
        "perf",
        "record",
        "-e",
        "cycles",
        "-F",
        "997",
        "-k",
        "mono",
        "-g",
        "-o",
        perf_data_file,
        "--",
    ] + cb_cmd

    print(f"Launching perf record wrapper: {' '.join(perf_cmd)}")
    capture = subprocess.Popen(perf_cmd, cwd=cwd)
    process_manifest = {}
    browser_name = os.path.basename(args.browser)
    while capture.poll() is None:
        observed_at = time.monotonic()
        for pid, details in snapshot_chrome_processes(
            capture.pid, browser_name
        ).items():
            if pid not in process_manifest:
                process_manifest[pid] = {
                    **details,
                    "first_seen_mono": observed_at,
                    "last_seen_mono": observed_at,
                }
            else:
                process_manifest[pid]["last_seen_mono"] = observed_at
        time.sleep(PROCESS_POLL_INTERVAL_SECONDS)
    if capture.returncode:
        raise subprocess.CalledProcessError(capture.returncode, perf_cmd)

    if adapter.benchmark_id == "jetstream3":
        intervals, outer_intervals = parse_jetstream_mono_intervals(rel_out_dir, cwd)
        if not intervals:
            intervals, outer_intervals = parse_mono_intervals(rel_out_dir, cwd)
    else:
        intervals, outer_intervals = parse_mono_intervals(rel_out_dir, cwd)

    if intervals and not outer_intervals:
        raise RuntimeError("Exact score intervals exist without outer diagnostic windows")
    for interval in intervals:
        if not any(
            outer["start_time_mono"] <= interval["start_time_mono"]
            and interval["end_time_mono"] <= outer["end_time_mono"]
            for outer in outer_intervals
        ):
            raise RuntimeError("Exact score interval falls outside every suite window")

    print(f"\n=======================================================")
    print(f" PERF PROFILE CAPTURED")
    print(f" Perf Data File: {perf_data_file}")
    if intervals:
        measured_duration = sum(
            interval["end_time_mono"] - interval["start_time_mono"]
            for interval in intervals
        )
        print(
            f" Measurement Intervals: {len(intervals)} ({measured_duration:.3f}s total)"
        )
        outer_duration = sum(
            interval["end_time_mono"] - interval["start_time_mono"]
            for interval in outer_intervals
        )
        print(
            f" Outer Diagnostic Windows: {len(outer_intervals)} "
            f"({outer_duration:.3f}s; {outer_duration - measured_duration:.3f}s unscored)"
        )
        print(
            " Candidate analysis uses the union of intervals; do not replace it with one broad --time range."
        )
    else:
        print(
            " No measurement intervals found; the profile is invalid for candidate selection."
        )
    print(f" Note: Ensure /tmp/perf-*.map files remain intact for symbol resolution.")
    print(f"=======================================================\n")

    observed_roles = {process["role"] for process in process_manifest.values()}
    missing_roles = sorted({"browser", "renderer"} - observed_roles)
    manifest = {
        "browser": args.browser,
        "build_provenance": provenance,
        "stories": args.stories,
        "enable_features": args.enable_features,
        "perf_data_file": perf_data_file,
        "scoped_to_scored_work": bool(intervals),
        "interval_kind": "exact-scored" if intervals else "missing",
        "metric_weighting": adapter.metric_model,
        "measurement_intervals": intervals,
        "outer_measurement_intervals": outer_intervals,
        "processes": sorted(process_manifest.values(), key=lambda item: item["pid"]),
        "missing_required_roles": missing_roles,
    }
    manifest_file = os.path.join(temp_results_dir, "perf_run_manifest.json")
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)
    shutil.copyfile(
        manifest_file, os.path.join(cwd, "scratch", "perf_run_manifest.json")
    )

    if not intervals:
        raise RuntimeError("No matched Speedometer measurement intervals were captured")
    if missing_roles:
        raise RuntimeError(
            "Missing required Chrome process roles: " + ", ".join(missing_roles)
        )

    if not args.skip_analysis:
        analyzer = os.path.join(
            cwd,
            ".agents",
            "skills",
            "optimize-campaign",
            "scripts",
            "analyze_stacks.py",
        )
        analysis_dir = os.path.join(temp_results_dir, "analysis", "full")
        stories_dir = os.path.join(temp_results_dir, "analysis", "stories")
        rejected_analyses = []
        full_command = [
            sys.executable,
            analyzer,
            "--input",
            perf_data_file,
            "--intervals",
            manifest_file,
            "--out-dir",
            analysis_dir,
            "--stories-out-dir",
            stories_dir,
            "--min-marginal-share",
            str(args.min_marginal_share),
            "--min-share",
            str(args.min_share),
        ]
        if run_analyzer(full_command, cwd) == ANALYSIS_REJECTED_EXIT_CODE:
            rejected_analyses.append("full process tree or story silo")
        print(
            f" Candidate Frontier: {os.path.join(analysis_dir, 'candidate_frontier.md')}"
        )
        print(
            f" Per-Story Silos: {os.path.join(stories_dir, 'stories_index.json')}"
        )
        print(
            f" Opportunity Trees: {os.path.join(analysis_dir, 'opportunity_trees.txt')}"
        )
        print(
            f" Interactive Profile: {os.path.join(analysis_dir, 'profile.collapsed')}"
        )
        if any(process["role"] == "renderer" for process in process_manifest.values()):
            renderer_dir = os.path.join(temp_results_dir, "analysis", "renderer")
            renderer_command = [
                sys.executable,
                analyzer,
                "--input",
                perf_data_file,
                "--intervals",
                manifest_file,
                "--role",
                "renderer",
                "--out-dir",
                renderer_dir,
                "--min-marginal-share",
                str(args.min_marginal_share),
                "--min-share",
                str(args.min_share),
            ]
            if run_analyzer(renderer_command, cwd) == ANALYSIS_REJECTED_EXIT_CODE:
                rejected_analyses.append("renderer")
            print(
                f" Renderer Frontier: {os.path.join(renderer_dir, 'candidate_frontier.md')}"
            )
            print(
                f" Renderer Trees: {os.path.join(renderer_dir, 'opportunity_trees.txt')}"
            )
            print(
                f" Renderer Profile: {os.path.join(renderer_dir, 'profile.collapsed')}"
            )
        if rejected_analyses:
            print(
                "Profile quality rejection: " + ", ".join(rejected_analyses),
                file=sys.stderr,
            )
            return ANALYSIS_REJECTED_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
