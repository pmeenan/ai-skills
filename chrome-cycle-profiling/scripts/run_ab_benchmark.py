#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Randomized block-interleaved (ABBA/BAAB) Speedometer benchmark.

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
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

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
                   block_label, cwd):
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


def _scalar(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and isinstance(value.get("average"), (int, float)):
        return float(value["average"])
    return None


def parse_run_metrics(cwd, out_dir):
    """Return (suite_score, {story: total_time_ms}) for one crossbench rep.

    Only per-iteration result files (where Score is a scalar) are trusted;
    aggregate files repeat the same numbers and would multiply-count them.
    """
    runs = []
    for root, dirs, files in os.walk(os.path.join(cwd, out_dir)):
        for file in files:
            if file != "speedometer_3.0.json":
                continue
            path = os.path.join(root, file)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                print(f"Error parsing {path}: {e}", file=sys.stderr)
                continue
            score = data.get("Score")
            if not isinstance(score, (int, float)):
                continue
            stories = {}
            for key, value in data.items():
                if key == "Score" or "/" in key:
                    continue
                num = _scalar(value)
                if num is not None and num > 0:
                    stories[key] = num
            runs.append((float(score), stories))
    return runs


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


def per_story_stats(block_data):
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


def main():
    parser = argparse.ArgumentParser(description="Run randomized block-interleaved (ABBA/BAAB) A/B or A/A Speedometer benchmark.")
    parser.add_argument("--browser", default="out/perf/chrome", help="Browser build path (aa and feature modes)")
    parser.add_argument("--browser-a", default="", help="Arm A browser path (two-binary mode)")
    parser.add_argument("--browser-b", default="", help="Arm B browser path (two-binary mode)")
    parser.add_argument("--feature", default="", help="Chromium Feature flag name to test")
    parser.add_argument("--aa", action="store_true", help="Run in genuine A/A baseline mode (identical binaries/flags on both arms)")
    parser.add_argument("--blocks", type=int, default=5, help="Number of ABBA/BAAB blocks (default: 5 blocks = 10 paired reps per arm)")
    parser.add_argument("--stories", default="all", help="Speedometer stories to run (default: all)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for block ordering")
    parser.add_argument("--enable-features", default="",
                        help="Comma-separated features enabled on BOTH arms "
                        "(aa and two-binary modes only). Required for bisecting "
                        "flag-gated campaign commits: without it, two-binary arms "
                        "both run baseline behavior and cannot differ.")
    parser.add_argument("--skip-feature-check", action="store_true",
                        help="Skip verifying that --feature is defined in the source tree")
    args = parser.parse_args()

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

    if not args.skip_feature_check:
        if args.feature and not check_feature_registered(cwd, args.feature):
            sys.exit(2)
        # A typo here is worse than in --feature mode: both arms silently run
        # baseline behavior and a bisect goes blind.
        for name in filter(None, (n.strip() for n in args.enable_features.split(","))):
            if not check_feature_registered(cwd, name):
                sys.exit(2)

    temp_results_dir = tempfile.mkdtemp(prefix="results_ab_interleaved_", dir=os.path.join(cwd, "scratch"))
    rel_out_dir = os.path.relpath(temp_results_dir, cwd)
    random.seed(args.seed)

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
    print(f" Stories      : {args.stories}")
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
    block_patterns = ["ABBA", "BAAB"]
    total_rep = 0

    for b_idx in range(args.blocks):
        pattern = random.choice(block_patterns)
        print(f"\n--- Block {b_idx + 1}/{args.blocks} Pattern: {pattern} ---")
        a_scores, b_scores = [], []
        a_stories, b_stories = [], []

        for char in pattern:
            enable = (char == "B")
            browser, flag_option, state_str = arm_config(enable)
            block_label = f"B{b_idx+1}_{char}"
            out_d = run_single_rep(browser, rel_out_dir, args.stories, flag_option,
                                   state_str, total_rep, block_label, cwd)
            runs = parse_run_metrics(cwd, out_d)
            if runs:
                score, stories = runs[0]
                if enable:
                    b_scores.append(score)
                    b_stories.append(stories)
                else:
                    a_scores.append(score)
                    a_stories.append(stories)
            total_rep += 1

        block_data.append({
            "block": b_idx + 1, "pattern": pattern,
            "a_scores": a_scores, "b_scores": b_scores,
            "a_stories": a_stories, "b_stories": b_stories,
        })

    suite = summarize_block_diffs(suite_block_diffs(block_data))
    if suite is None:
        print("Error: fewer than 2 complete blocks; no statistics possible.", file=sys.stderr)
        sys.exit(1)
    stories = per_story_stats(block_data)

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
        "mode": mode_key,
        "feature": args.feature,
        "enable_features": args.enable_features,
        "browser": args.browser,
        "browser_a": args.browser_a,
        "browser_b": args.browser_b,
        "stories": args.stories,
        "blocks": suite["n_blocks"],
        "block_details": [
            {k: b[k] for k in ("block", "pattern", "a_scores", "b_scores")}
            for b in block_data
        ],
        "geometric_delta_pct": suite["delta_pct"],
        "ci_95_pct": suite["ci_95_pct"],
        "significance_threshold_pct": suite["significance_threshold_pct"],
        "mde_80_power_pct": suite["mde_80_power_pct"],
        "is_stat_sig": suite["is_stat_sig"],
        "passes_regression_guardrail": passes_regression_guardrail,
        "achieves_5pct_goal": achieves_5pct_goal,
        "per_story": stories,
        "stat_sig_story_regressions": stat_sig_regressions,
    }
    manifest_path = os.path.join(cwd, "scratch", "ab_results_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(res_manifest, f, indent=2)

    # Explicit cleanup of unique temp result directory
    shutil.rmtree(temp_results_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
