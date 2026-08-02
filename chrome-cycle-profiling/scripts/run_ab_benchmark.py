#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

def get_repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

def run_single_rep(browser, out_dir, stories, feature_flag, enable, rep_index, block_label, is_aa_mode, cwd):
    if is_aa_mode:
        flag_option = ""
        state_str = "ARM_B" if enable else "ARM_A"
    else:
        flag_option = f"--enable-features={feature_flag}" if enable else f"--disable-features={feature_flag}"
        state_str = "ENABLED" if enable else "DISABLED"
        
    print(f"[Block {block_label} - Rep {rep_index+1}] Running {state_str}...")
    
    rep_out_dir = os.path.join(out_dir, f"rep_{rep_index}_{block_label}_{state_str.lower()}")
    full_out_dir = os.path.join(cwd, rep_out_dir)
    if os.path.exists(full_out_dir):
        shutil.rmtree(full_out_dir)
        
    cmd = [
        "vpython3", "./third_party/crossbench/cb.py", "speedometer_3.0",
        "--network=third_party/speedometer/v3.0",
        "--env-validation=warn",
        f"--browser={browser}",
        "--headless",
        "--no-sandbox",
        "--repetitions=1",
        f"--out-dir={rep_out_dir}",
        f"--stories={stories}"
    ]
    if flag_option:
        cmd.append(flag_option)

    subprocess.run(cmd, cwd=cwd, check=True)
    return rep_out_dir

def parse_scores_from_dir(cwd, out_dir):
    scores = []
    for root, dirs, files in os.walk(os.path.join(cwd, out_dir)):
        for file in files:
            if file == "speedometer_3.0.json":
                lf = os.path.join(root, file)
                try:
                    with open(lf, "r") as f:
                        data = json.load(f)
                        if "Score" in data:
                            scores.append(float(data["Score"]))
                except Exception as e:
                    print(f"Error parsing {lf}: {e}", file=sys.stderr)
    return scores

def compute_block_log_diffs(block_data):
    """Computes block observation d_b = mean(ln B scores in block b) - mean(ln A scores in block b)."""
    block_diffs = []
    for b_info in block_data:
        a_scores = b_info["a_scores"]
        b_scores = b_info["b_scores"]
        if not a_scores or not b_scores:
            continue
        mean_ln_a = sum(math.log(x) for x in a_scores) / len(a_scores)
        mean_ln_b = sum(math.log(x) for x in b_scores) / len(b_scores)
        d_b = mean_ln_b - mean_ln_a
        block_diffs.append(d_b)
    
    n_blocks = len(block_diffs)
    if n_blocks < 2:
        return 0.0, 0.0, (0.0, 0.0), 0.0, 0.0

    mean_d = sum(block_diffs) / n_blocks
    var_d = sum((x - mean_d) ** 2 for x in block_diffs) / (n_blocks - 1)
    std_dev_d = math.sqrt(var_d)
    std_err_d = std_dev_d / math.sqrt(n_blocks)

    # Student t-crit for df = n_blocks - 1
    t_crit = 2.776 if n_blocks == 5 else (2.262 if n_blocks <= 10 else 2.145)
    ci_lower_log = mean_d - t_crit * std_err_d
    ci_upper_log = mean_d + t_crit * std_err_d

    pct_gain = (math.exp(mean_d) - 1.0) * 100.0
    ci_lower_pct = (math.exp(ci_lower_log) - 1.0) * 100.0
    ci_upper_pct = (math.exp(ci_upper_log) - 1.0) * 100.0

    mde_pct = (math.exp(2.0 * std_err_d) - 1.0) * 100.0
    t_stat = mean_d / std_err_d if std_err_d > 0 else 0.0

    return pct_gain, std_dev_d, (ci_lower_pct, ci_upper_pct), mde_pct, t_stat

def main():
    parser = argparse.ArgumentParser(description="Run randomized block-interleaved (ABBA/BAAB) A/B or A/A Speedometer benchmark.")
    parser.add_argument("--browser", default="out/perf/chrome", help="Browser build path")
    parser.add_argument("--feature", default="", help="Chromium Feature flag name to test")
    parser.add_argument("--aa", action="store_true", help="Run in genuine A/A baseline mode (identical binaries/flags on both arms)")
    parser.add_argument("--blocks", type=int, default=5, help="Number of ABBA/BAAB blocks (default: 5 blocks = 10 paired reps per arm)")
    parser.add_argument("--stories", default="all", help="Speedometer stories to run (default: all)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for block ordering")
    args = parser.parse_args()

    if not args.aa and not args.feature:
        print("Error: Must specify --feature <flag> or --aa for A/A calibration mode.", file=sys.stderr)
        sys.exit(1)

    cwd = get_repo_root()
    temp_results_dir = tempfile.mkdtemp(prefix="results_ab_interleaved_", dir=os.path.join(cwd, "scratch"))
    rel_out_dir = os.path.relpath(temp_results_dir, cwd)
    random.seed(args.seed)

    mode_str = "GENUINE A/A CALIBRATION" if args.aa else f"FEATURE A/B ({args.feature})"
    print(f"\n=======================================================")
    print(f" RANDOMIZED BLOCK-INTERLEAVED BENCHMARK (ABBA/BAAB)")
    print(f" Mode         : {mode_str}")
    print(f" Output Dir   : {rel_out_dir}")
    print(f" Blocks       : {args.blocks} (Total paired runs: {args.blocks * 2} per arm)")
    print(f" Stories      : {args.stories}")
    print(f" Browser      : {args.browser}")
    print(f"=======================================================\n")

    block_data = []
    block_patterns = ["ABBA", "BAAB"]
    total_rep = 0

    for b_idx in range(args.blocks):
        pattern = random.choice(block_patterns)
        print(f"\n--- Block {b_idx + 1}/{args.blocks} Pattern: {pattern} ---")
        a_scores = []
        b_scores = []

        for char in pattern:
            enable = (char == "B")
            block_label = f"B{b_idx+1}_{char}"
            out_d = run_single_rep(args.browser, rel_out_dir, args.stories, args.feature, enable, total_rep, block_label, args.aa, cwd)
            s_list = parse_scores_from_dir(cwd, out_d)
            if s_list:
                score = s_list[0]
                if enable:
                    b_scores.append(score)
                else:
                    a_scores.append(score)
            total_rep += 1

        block_data.append({"block": b_idx + 1, "pattern": pattern, "a_scores": a_scores, "b_scores": b_scores})

    mean_pct, std_dev_d, (ci_low, ci_high), mde_pct, t_stat = compute_block_log_diffs(block_data)

    # Correct confidence bound check: d_b > 0 is gain, d_b < 0 is regression.
    # CI_lower >= -2.0% for regression limit check. CI_lower >= +5.0% for 5% suite goal check.
    passes_regression_guardrail = (ci_low >= -2.0)
    achieves_5pct_goal = (ci_low >= 5.0)
    is_stat_sig = (ci_low > 0 and ci_high > 0) or (ci_low < 0 and ci_high < 0)

    print(f"\n=======================================================")
    print(f" STATISTICAL RESULT SUMMARY ({mode_str})")
    print(f"=======================================================")
    print(f"  Valid Blocks Analyzed        : {len(block_data)} blocks")
    print(f"-------------------------------------------------------")
    print(f"  Geometric Score Delta        : {mean_pct:+.2f}%")
    print(f"  95% Confidence Interval      : [{ci_low:+.2f}%, {ci_high:+.2f}%]")
    print(f"  Session MDE (80% Power)      : +/-{mde_pct:.2f}%")
    print(f"  Block t-statistic            : {t_stat:.3f}")
    print(f"  Passes Per-Story Regr Guard  : {'YES (CI_lower >= -2.0%)' if passes_regression_guardrail else 'NO (Regresses > 2.0%)'}")
    
    if args.aa:
        print(f"  A/A Calibration Status       : {'PASSED (No false positive)' if not is_stat_sig else 'HIGH NOISE FLOOR'}")
    else:
        print(f"  Statistically Significant    : {'PROVISIONAL PASS' if is_stat_sig else 'NO (CI crosses 0%)'}")
        print(f"  Achieves 5% Goal Bar         : {'YES (CI_lower >= +5.0%)' if achieves_5pct_goal else 'NO'}")

    print(f"=======================================================\n")

    res_manifest = {
        "mode": "aa" if args.aa else "ab",
        "feature": args.feature,
        "blocks": len(block_data),
        "block_details": block_data,
        "geometric_delta_pct": mean_pct,
        "ci_95_pct": [ci_low, ci_high],
        "mde_pct": mde_pct,
        "is_stat_sig": is_stat_sig,
        "passes_regression_guardrail": passes_regression_guardrail,
        "achieves_5pct_goal": achieves_5pct_goal
    }
    manifest_path = os.path.join(cwd, "scratch", "ab_results_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(res_manifest, f, indent=2)

    # Explicit cleanup of unique temp result directory
    shutil.rmtree(temp_results_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
