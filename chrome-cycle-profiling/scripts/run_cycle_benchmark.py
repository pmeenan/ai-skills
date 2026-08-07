#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


PROCESS_POLL_INTERVAL_SECONDS = 0.25
ANALYSIS_REJECTED_EXIT_CODE = 3


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

    for root, dirs, files in os.walk(os.path.join(cwd, out_dir)):
        for file in files:
            if file == "browser.stdout.log":
                log_file_path = os.path.join(root, file)
                pending_start = None
                with open(log_file_path, "r") as f:
                    for line in f:
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
                                    intervals.append(
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
    return sorted(intervals, key=lambda interval: interval["start_time_mono"])


def run_analyzer(command, cwd):
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode not in (0, ANALYSIS_REJECTED_EXIT_CODE):
        raise subprocess.CalledProcessError(completed.returncode, command)
    return completed.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run Speedometer 3 full Chrome process-tree perf cycle sampling with V8 basic-prof symbolization."
    )
    parser.add_argument(
        "--browser",
        default="out/perf/chrome",
        help="Browser build path (default: out/perf/chrome)",
    )
    parser.add_argument(
        "--stories", default="all", help="Speedometer stories to run (default: all)"
    )
    parser.add_argument(
        "--repetitions", type=int, default=1, help="Number of repetitions (default: 1)"
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Capture perf.data without producing the overlap-aware candidate frontier",
    )
    parser.add_argument(
        "--enable-features",
        default="Speedometer3Optimizations",
        help=(
            "Comma-separated Chrome features passed to Crossbench. The default is "
            "the campaign flag Speedometer3Optimizations so captures reflect "
            "already-landed work; pass an empty value for a baseline capture. "
            "Chrome silently ignores names that are not defined in the binary."
        ),
    )
    args = parser.parse_args()

    cwd = get_repo_root()
    temp_results_dir = tempfile.mkdtemp(
        prefix="results_perf_sampling_", dir=os.path.join(cwd, "scratch")
    )
    rel_out_dir = os.path.relpath(temp_results_dir, cwd)

    perf_data_file = os.path.join(temp_results_dir, "perf_sampling.data")

    cb_cmd = [
        "vpython3",
        "./third_party/crossbench/cb.py",
        "speedometer_3.0",
        "--network=third_party/speedometer/v3.0",
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

    intervals = parse_mono_intervals(rel_out_dir, cwd)

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
        "stories": args.stories,
        "enable_features": args.enable_features,
        "perf_data_file": perf_data_file,
        "scoped_to_scored_work": bool(intervals),
        "measurement_intervals": intervals,
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
            "optimize-speedometer",
            "scripts",
            "analyze_stacks.py",
        )
        analysis_dir = os.path.join(temp_results_dir, "analysis", "full")
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
        ]
        if run_analyzer(full_command, cwd) == ANALYSIS_REJECTED_EXIT_CODE:
            rejected_analyses.append("full process tree")
        print(
            f" Candidate Frontier: {os.path.join(analysis_dir, 'candidate_frontier.md')}"
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
