#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import os
import re
import shutil
import subprocess
import sys

CWD = "/usr/local/google/home/pmeenan/src/chromium/src"
DEFAULT_STORIES = "NewsSite-Next,NewsSite-Nuxt"

def run_crossbench(browser, stories, repetitions, out_dir, extra_browser_args=""):
    print(f"Running Crossbench Speedometer: browser={browser}, stories={stories}, repetitions={repetitions}...")
    full_out_dir = os.path.join(CWD, out_dir)
    if os.path.exists(full_out_dir):
        print(f"Cleaning up existing output directory: {full_out_dir}")
        shutil.rmtree(full_out_dir)
        
    full_browser_args = f"--enable-logging=stderr --log-level=0 --v=1 {extra_browser_args}".strip()
    cmd = [
        "vpython3", "./third_party/crossbench/cb.py",
        "speedometer_3.0",
        "--env-validation=warn",
        f"--browser={browser}",
        "--headless",
        f"--repetitions={repetitions}",
        f"--out-dir={out_dir}",
        f"--stories={stories}",
        f"--browser-args={full_browser_args}"
    ]
    subprocess.run(cmd, cwd=CWD, check=True)

def parse_and_report_cycles(out_dir):
    print("\n=== PARSING CYCLE PROFILER LOGS ===")
    profile_found = False
    
    # Crossbench results structure contains stories and sessions folders
    for root, dirs, files in os.walk(os.path.join(CWD, out_dir)):
        for file in files:
            if file == "browser.stdout.log":
                log_file_path = os.path.join(root, file)
                print(f"Parsing log file: {os.path.relpath(log_file_path, CWD)}")
                
                with open(log_file_path, "r") as f:
                    lines = f.readlines()
                    
                # Read backward to find the last/most complete CYCLE PROFILE block
                block_started = False
                profile_block = []
                for line in reversed(lines):
                    if "=== CYCLE PROFILE" in line:
                        profile_block.append(line.strip())
                        block_started = True
                        break # Got the most complete header
                    if block_started or "cycles (" in line:
                        profile_block.append(line.strip())
                        block_started = True
                
                if block_started and profile_block:
                    profile_found = True
                    print("\nFinal Measured Cycle Profile:")
                    for val in reversed(profile_block):
                        # Clean up standard Chromium log metadata prefix
                        clean_line = re.sub(r'^\[\d+:\d+:\d+\/\d+\.\d+:ERROR:[^\]]+\]\s*', '', val)
                        print(clean_line)
                    print("-" * 40)

    if not profile_found:
        print("Warning: No '=== CYCLE PROFILE' log lines found in any browser.stdout.log files.")
        print("Make sure you have compiled with CycleProfiler active and executed matching stories.")

def main():
    parser = argparse.ArgumentParser(description="Run Speedometer with cycle profiling probes and report results.")
    parser.add_argument("--browser", default="out/Default/chrome", help="Browser build path (default: out/Default/chrome)")
    parser.add_argument("--stories", default=DEFAULT_STORIES, help=f"Speedometer stories to run (default: {DEFAULT_STORIES})")
    parser.add_argument("--repetitions", type=int, default=1, help="Number of repetitions (default: 1)")
    parser.add_argument("--out-dir", default="scratch/results_probes", help="Crossbench results output directory (default: scratch/results_probes)")
    parser.add_argument("--extra-browser-args", default="", help="Extra browser arguments")
    parser.add_argument("--no-run", action="store_true", help="Skip running and only parse existing logs in out-dir")
    args = parser.parse_args()

    if not args.no_run:
        try:
            run_crossbench(args.browser, args.stories, args.repetitions, args.out_dir, args.extra_browser_args)
        except Exception as e:
            print(f"Error running Crossbench: {e}", file=sys.stderr)
            sys.exit(1)
            
    parse_and_report_cycles(args.out_dir)

if __name__ == "__main__":
    main()
