#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

def get_repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

def parse_mono_timestamps(out_dir, cwd):
    start_time = None
    end_time = None
    
    for root, dirs, files in os.walk(os.path.join(cwd, out_dir)):
        for file in files:
            if file == "browser.stdout.log":
                log_file_path = os.path.join(root, file)
                with open(log_file_path, "r") as f:
                    for line in f:
                        if "[SP3_MONO_TIME]" in line:
                            if "sp3-measurement-start" in line:
                                m = re.search(r"sp3-measurement-start:\s*([\d\.]+)", line)
                                if m:
                                    if start_time is None:
                                        start_time = float(m.group(1))
                            elif "sp3-measurement-end" in line:
                                m = re.search(r"sp3-measurement-end:\s*([\d\.]+)", line)
                                if m:
                                    end_time = float(m.group(1))
    return start_time, end_time

def main():
    parser = argparse.ArgumentParser(description="Run Speedometer 3 full Chrome process-tree perf cpu-clock sampling with V8 basic-prof symbolization.")
    parser.add_argument("--browser", default="out/perf/chrome", help="Browser build path (default: out/perf/chrome)")
    parser.add_argument("--stories", default="all", help="Speedometer stories to run (default: all)")
    parser.add_argument("--repetitions", type=int, default=1, help="Number of repetitions (default: 1)")
    args = parser.parse_args()

    cwd = get_repo_root()
    temp_results_dir = tempfile.mkdtemp(prefix="results_perf_sampling_", dir=os.path.join(cwd, "scratch"))
    rel_out_dir = os.path.relpath(temp_results_dir, cwd)

    perf_data_file = os.path.join(temp_results_dir, "perf_sampling.data")

    cb_cmd = [
        "vpython3", "./third_party/crossbench/cb.py",
        "speedometer_3.0",
        "--network=third_party/speedometer/v3.0",
        "--env-validation=warn",
        f"--browser={args.browser}",
        "--headless",
        "--no-sandbox",
        "--js-flags=--perf-basic-prof",
        f"--repetitions={args.repetitions}",
        f"--out-dir={os.path.join(rel_out_dir, 'cb')}",
        f"--stories={args.stories}"
    ]

    print(f"\n=======================================================")
    print(f" FULL CHROME PROCESS TREE PERF SAMPLING (-k mono)")
    print(f" Output Data : {perf_data_file}")
    print(f" Output Dir  : {rel_out_dir}")
    print(f" Browser     : {args.browser}")
    print(f" Stories     : {args.stories}")
    print(f"=======================================================\n")

    perf_cmd = [
        "perf", "record",
        "-e", "cycles",
        "-F", "997",
        "-k", "mono",
        "-g",
        "-o", perf_data_file,
        "--"
    ] + cb_cmd

    print(f"Launching perf record wrapper: {' '.join(perf_cmd)}")
    subprocess.run(perf_cmd, cwd=cwd, check=True)

    start_t, end_t = parse_mono_timestamps(rel_out_dir, cwd)
    
    print(f"\n=======================================================")
    print(f" PERF PROFILE CAPTURED")
    print(f" Perf Data File: {perf_data_file}")
    if start_t and end_t:
        print(f" Measurement Window: {start_t:.3f}s to {end_t:.3f}s (Duration: {end_t - start_t:.3f}s)")
        print(f" 1. Full Process-Tree Report: perf report -i {perf_data_file} --time {start_t:.3f},{end_t:.3f} --stdio | head -60")
        print(f" 2. Renderer-Only Report    : perf report -i {perf_data_file} --comms=chrome --time {start_t:.3f},{end_t:.3f} --stdio | head -60")
    else:
        print(f" 1. Full Process-Tree Report: perf report -i {perf_data_file} --stdio | head -60")
        print(f" 2. Renderer-Only Report    : perf report -i {perf_data_file} --comms=chrome --stdio | head -60")
    print(f" Note: Ensure /tmp/perf-*.map files remain intact for symbol resolution.")
    print(f"=======================================================\n")

    manifest = {
        "browser": args.browser,
        "stories": args.stories,
        "perf_data_file": perf_data_file,
        "start_time_mono": start_t,
        "end_time_mono": end_t
    }
    manifest_file = os.path.join(cwd, "scratch", "perf_run_manifest.json")
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

if __name__ == "__main__":
    main()
