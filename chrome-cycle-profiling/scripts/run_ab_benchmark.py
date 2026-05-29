#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import json
import math
import os
import shutil
import subprocess
import sys

CWD = "/usr/local/google/home/pmeenan/src/chromium/src"

def run_benchmark(browser, out_dir, repetitions, stories, feature_flag, enable):
    flag_option = f"--enable-features={feature_flag}" if enable else f"--disable-features={feature_flag}"
    state_str = "ENABLED" if enable else "DISABLED"
    print(f"\nRunning Speedometer A/B ({state_str}): repetitions={repetitions}, flag={flag_option}...")
    
    full_out_dir = os.path.join(CWD, out_dir)
    if os.path.exists(full_out_dir):
        shutil.rmtree(full_out_dir)
        
    cmd = [
        "vpython3", "./third_party/crossbench/cb.py", "speedometer_3.0",
        f"--browser={browser}",
        "--headless",
        f"--repetitions={repetitions}",
        f"--out-dir={out_dir}",
        f"--stories={stories}",
        "--env-validation=warn",
        flag_option
    ]
    subprocess.run(cmd, cwd=CWD, check=True)

def parse_results(out_dir, stories_list):
    scores = []
    story_durations = {story: [] for story in stories_list}
    
    for root, dirs, files in os.walk(os.path.join(CWD, out_dir)):
        for file in files:
            if file == "speedometer_3.0.json" and "0_default" in root:
                lf = os.path.join(root, file)
                try:
                    with open(lf, "r") as f:
                        data = json.load(f)
                        if "Score" in data:
                            scores.append(float(data["Score"]))
                        for story in stories_list:
                            if story in data:
                                story_durations[story].append(float(data[story]))
                except Exception as e:
                    print(f"Error parsing {lf}: {e}")
                    
    results = {"Score": scores}
    for story, values in story_durations.items():
        results[story] = values
    return results

def calculate_stats(values):
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = math.sqrt(variance)
    return mean, std_dev

def print_stats(name, results):
    print(f"\n=== {name} Stats ===")
    for key, values in results.items():
        if not values:
            continue
        mean, std = calculate_stats(values)
        print(f"  {key:20}: Mean = {mean:.3f}, StdDev = {std:.3f} (Runs: {len(values)})")

def main():
    parser = argparse.ArgumentParser(description="Run high-precision A/B Speedometer comparison benchmark.")
    parser.add_argument("--browser", default="out/Default/chrome", help="Browser build path")
    parser.add_argument("--feature", required=True, help="Chromium Feature flag name to enable/disable (e.g., OptimizeMixedContentChecks)")
    parser.add_argument("--repetitions", type=int, default=5, help="Number of repetitions for each A/B run (default: 5)")
    parser.add_argument("--stories", default="NewsSite-Next,NewsSite-Nuxt", help="Speedometer stories to run (comma-separated)")
    args = parser.parse_args()

    stories_list = args.stories.split(",")
    
    # 1. Run A (Feature Disabled)
    disabled_dir = "scratch/results_ab_disabled"
    try:
        run_benchmark(args.browser, disabled_dir, args.repetitions, args.stories, args.feature, enable=False)
    except Exception as e:
        print(f"Error in disabled run: {e}", file=sys.stderr)
        sys.exit(1)
    disabled_results = parse_results(disabled_dir, stories_list)
    
    # 2. Run B (Feature Enabled)
    enabled_dir = "scratch/results_ab_enabled"
    try:
        run_benchmark(args.browser, enabled_dir, args.repetitions, args.stories, args.feature, enable=True)
    except Exception as e:
        print(f"Error in enabled run: {e}", file=sys.stderr)
        sys.exit(1)
    enabled_results = parse_results(enabled_dir, stories_list)

    # Print statistics
    print_stats(f"DISABLED (Baseline)", disabled_results)
    print_stats(f"ENABLED (Optimized)", enabled_results)
    
    # Print final comparison summary
    if disabled_results["Score"] and enabled_results["Score"]:
        base_score, _ = calculate_stats(disabled_results["Score"])
        opt_score, _ = calculate_stats(enabled_results["Score"])
        pct_diff = ((opt_score - base_score) / base_score) * 100
        print(f"\n=== COMPARISON SUMMARY ===")
        print(f"  Baseline Score  : {base_score:.3f}")
        print(f"  Optimized Score : {opt_score:.3f}")
        print(f"  Net Score Change: {pct_diff:+.2f}%")
        print("==========================")

if __name__ == "__main__":
    main()
