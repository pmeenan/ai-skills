#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Automate Pinpoint A/B tryjob execution and evaluation for optimization campaigns.

Workflow:
  1. Upload a lightweight try CL to Gerrit (or use an existing CL URL).
     (Try CL does NOT require feature flags or unit tests, but its URL is recorded).
  2. Launch a Pinpoint A/B tryjob (default: mac-m1_mini_2020-perf-pgo, 150 attempts).
  3. Wait/poll for the job to complete.
  4. Fetch and parse raw Catapult histogram results.
  5. Compute geometric score delta, per-workload deltas, Welch's t-test, and 95% CIs.
  6. Record the Gerrit CL URL in the candidate results.
  7. If the candidate regresses or fails the gate, abandon the try CL on Gerrit.

Usage:
  # All-in-one run (upload current diff as try CL, test on Pinpoint, abandon if regressed):
  python3 pinpoint_measure.py run --benchmark speedometer3 --bot mac-m1_mini_2020-perf-pgo --attempts 150

  # Run on an existing Gerrit CL:
  python3 pinpoint_measure.py run --cl https://chromium-review.googlesource.com/c/chromium/src/+/8349622

  # Standalone subcommands:
  python3 pinpoint_measure.py upload-cl --message "optimize-campaign try: my_opt"
  python3 pinpoint_measure.py start --cl <url> --bot mac-m1_mini_2020-perf-pgo --attempts 150
  python3 pinpoint_measure.py wait --job-id <id>
  python3 pinpoint_measure.py analyze --job-id <id> --cl <url> --out summary.json
  python3 pinpoint_measure.py abandon --cl <url> --reason "Regressed TodoMVC by -0.3%"
"""

import argparse
from collections import defaultdict
import csv
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PINPOINT_BASE_URL = "https://pinpoint-dot-chromeperf.appspot.com"
PINPOINT_API_NEW = f"{PINPOINT_BASE_URL}/api/new"
PINPOINT_API_JOB = f"{PINPOINT_BASE_URL}/api/job"
PINPOINT_API_RESULTS2 = f"{PINPOINT_BASE_URL}/api/results2-serve"

DEFAULT_BOT = "mac-m1_mini_2020-perf-pgo"
DEFAULT_BENCHMARK = "speedometer3"
DEFAULT_STORY = "Speedometer3"
DEFAULT_ATTEMPTS = 150


def run_cmd(cmd, cwd=None, check=True):
    print(f"+ {' '.join(str(c) for c in cmd)}", file=sys.stderr)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def get_auth_token():
    """Retrieve an OAuth access token using luci-auth or gcloud."""
    for cmd in (["luci-auth", "token"], ["gcloud", "auth", "print-access-token"]):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            tok = res.stdout.strip()
            if tok:
                return tok
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    return None


def extract_cl_issue_number(cl_ref):
    """Extract numeric issue ID from a Gerrit URL or string."""
    if not cl_ref:
        return None
    cl_ref = str(cl_ref).strip()
    match = re.search(r"/c/(?:[^/]+/)+/\+/(\d+)", cl_ref)
    if match:
        return int(match.group(1))
    match = re.search(r"/(\d{6,})", cl_ref)
    if match:
        return int(match.group(1))
    if cl_ref.isdigit():
        return int(cl_ref)
    return None


def upload_try_cl(message=None, cwd=None):
    """Upload current staged/working branch as a Gerrit try CL."""
    if not message:
        message = "optimize-campaign: provisional candidate try CL"

    cmd = ["git", "cl", "upload", "--bypass-hooks", "--squash", "-m", message]
    print(f"Uploading try CL: {' '.join(cmd)}", file=sys.stderr)
    res = run_cmd(cmd, cwd=cwd, check=True)

    issue_res = run_cmd(["git", "cl", "issue"], cwd=cwd, check=True)
    out = issue_res.stdout.strip()
    match = re.search(r"Issue number:\s*(\d+)\s*\((https://[^\)]+)\)", out)
    if match:
        issue = int(match.group(1))
        url = match.group(2)
        print(f"Uploaded Gerrit CL #{issue}: {url}", file=sys.stderr)
        return {"issue": issue, "url": url}

    match_url = re.search(r"(https://chromium-review\.googlesource\.com/[^\s]+)", res.stdout)
    if match_url:
        url = match_url.group(1)
        issue = extract_cl_issue_number(url)
        return {"issue": issue, "url": url}

    raise RuntimeError(f"Could not parse Gerrit CL issue from 'git cl issue': {out}")


def abandon_cl(cl_ref, reason="Abandoned candidate try CL", cwd=None):
    """Abandon a Gerrit try CL so it does not linger in review queues."""
    issue = extract_cl_issue_number(cl_ref)
    if not issue:
        raise ValueError(f"Cannot parse issue number from '{cl_ref}'")

    print(f"Abandoning Gerrit CL #{issue} (reason: {reason})...", file=sys.stderr)
    try:
        run_cmd(["git", "cl", "set-close", "-i", str(issue)], cwd=cwd, check=True)
        print(f"Successfully abandoned Gerrit CL #{issue}.", file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"git cl set-close failed: {e.stderr}", file=sys.stderr)
        # Attempt direct Gerrit REST API abandon if possible
        token = get_auth_token()
        if token:
            url = f"https://chromium-review.googlesource.com/a/changes/{issue}/abandon"
            req = urllib.request.Request(
                url,
                data=json.dumps({"message": reason}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    if resp.status in (200, 204):
                        print(f"Successfully abandoned Gerrit CL #{issue} via REST API.", file=sys.stderr)
                        return True
            except urllib.error.URLError as url_err:
                print(f"Gerrit REST API abandon failed: {url_err}", file=sys.stderr)
        return False


def start_pinpoint_job(
    cl_url,
    benchmark=DEFAULT_BENCHMARK,
    bot=DEFAULT_BOT,
    attempts=DEFAULT_ATTEMPTS,
    story=DEFAULT_STORY,
    base_commit="HEAD",
    bug=None,
    base_extra_args="",
    experiment_extra_args="",
):
    """Start an A/B Pinpoint tryjob comparing an immutable base and patchset."""
    if not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        raise ValueError("Pinpoint requires a full immutable baseline commit")
    if not re.fullmatch(r"https://chromium-review.googlesource.com/c/chromium/src/\+/\d+/\d+", cl_url):
        raise ValueError("Pinpoint requires a Gerrit URL including the patchset number")
    payload = {
        "comparison_mode": "try",
        "benchmark": benchmark,
        "configuration": bot,
        "story": story,
        "story_tags": "all",
        "initial_attempt_count": str(attempts),
        "base_git_hash": base_commit if base_commit.startswith("-") else f"-{base_commit}",
        "end_git_hash": base_commit if base_commit.startswith("-") else f"-{base_commit}",
        "base_patch": "",
        "experiment_patch": cl_url,
        "base_extra_args": base_extra_args,
        "experiment_extra_args": experiment_extra_args,
        "project": "chromium",
        "bug_id": str(bug or ""),
        "batch_id": "",
        "target": "performance_test_suite",
        "try": "on",
    }

    token = get_auth_token()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(PINPOINT_API_NEW, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            job_id = resp_data.get("jobId") or resp_data.get("job_id")
            job_url = resp_data.get("jobUrl") or f"{PINPOINT_BASE_URL}/job/{job_id}"
            print(f"Pinpoint job started: {job_url} (id: {job_id})", file=sys.stderr)
            return {"job_id": job_id, "job_url": job_url}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to start Pinpoint job ({e.code}): {err_body}") from e


def get_job_status(job_id):
    """Fetch status dict for a Pinpoint job."""
    url = f"{PINPOINT_API_JOB}/{job_id}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_job(job_id, poll_interval=30, timeout=7200, verbose=True):
    """Poll a Pinpoint job until completion, cancellation, or failure."""
    start_time = time.time()
    job_url = f"{PINPOINT_BASE_URL}/job/{job_id}"
    if verbose:
        print(f"Polling Pinpoint job {job_url} every {poll_interval}s (timeout: {timeout}s)...", file=sys.stderr)

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Pinpoint job {job_id} exceeded timeout of {timeout}s")

        status_data = get_job_status(job_id)
        status = status_data.get("status", "Unknown")

        if status == "Completed":
            if verbose:
                print(f"\nJob {job_id} completed successfully!", file=sys.stderr)
            return status_data
        elif status in ("Failed", "Cancelled"):
            reason = status_data.get("cancel_reason") or status_data.get("exception", "Unknown error")
            raise RuntimeError(f"Pinpoint job {job_id} finished with status '{status}': {reason}")

        if verbose:
            sys.stderr.write(f"\r[{int(elapsed)}s elapsed] Status: {status} ...")
            sys.stderr.flush()

        time.sleep(poll_interval)


def fetch_results2(job_id, out_file=None):
    """Download the raw Catapult results2 HTML/JSON from Pinpoint."""
    url = f"{PINPOINT_API_RESULTS2}/{job_id}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode("utf-8")

    if out_file:
        path = pathlib.Path(out_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"Saved raw results to {out_file}", file=sys.stderr)

    return content


def extract_histogram_text(content):
    """Extract the embedded JSON lines from results2 HTML, or return raw text."""
    start = content.find('<div id="histogram-json-data"')
    if start != -1:
        start_comment = content.find("<!--", start) + 4
        end_comment = content.find("-->", start_comment)
        return content[start_comment:end_comment].strip()
    return content.strip()


# Statistical helper functions (pure standard library)
def _betacf(a, b, x):
    max_it = 100
    eps = 3.0e-7
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        del_val = d * c
        h *= del_val
        if abs(del_val - 1.0) < eps:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t, df):
    if df <= 0:
        return 0.5
    x = df / (df + t * t)
    prob = 0.5 * _ibeta(0.5 * df, 0.5, x)
    return prob if t <= 0 else 1.0 - prob


def student_t_p_value(t, df):
    return 2.0 * (1.0 - student_t_cdf(abs(t), df))


def student_t_crit_95(df):
    if df >= 100:
        return 1.960
    low = 1.960
    high = 15.0
    for _ in range(40):
        mid = (low + high) / 2
        if student_t_cdf(mid, df) < 0.975:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def parse_and_analyze_results(content, job_id=None, cl_url=None, bot=None, plan=None):
    """Parse raw Catapult histograms and compute delta, Welch's t-test, 95% CIs."""
    data_text = extract_histogram_text(content)

    diagnostics_by_guid = {}
    histograms = []
    for line in data_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "guid" in obj and "name" not in obj:
            diagnostics_by_guid[obj["guid"]] = obj
        elif obj.get("type") is None:
            histograms.append(obj)

    metric_data = defaultdict(lambda: {"base": [], "exp": [], "unit": ""})

    for h in histograms:
        name = h.get("name")
        unit = h.get("unit", "")
        label_guid = h.get("diagnostics", {}).get("labels")
        label = diagnostics_by_guid.get(label_guid, {}).get("values", ["unknown"])[0]
        arm_match = re.fullmatch(r"(base|exp)(?:: .+)?", str(label))
        if not arm_match:
            raise ValueError("unrecognized Pinpoint arm label: " + str(label))
        arm = arm_match.group(1)
        running = h.get("running", [])
        if not name or len(running) < 4 or running[0] <= 0:
            raise ValueError("missing histogram observations")
        mean_val = running[3]
        if isinstance(mean_val, bool) or not isinstance(mean_val, (int, float)) or not math.isfinite(mean_val) or mean_val <= 0:
            raise ValueError("non-positive/non-finite Pinpoint metric")
        if "biggerIsBetter" not in unit and "smallerIsBetter" not in unit:
            raise ValueError("metric lacks a direction")
        if metric_data[name]["unit"] and metric_data[name]["unit"] != unit:
            raise ValueError("metric unit changed between attempts")
        metric_data[name][arm].append(mean_val)
        metric_data[name]["unit"] = unit

    results = {
        "job_id": job_id,
        "cl_url": cl_url,
        "bot": bot,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics": {},
        "regressions": [],
        "wins": [],
        "verdict": "INCONCLUSIVE",
    }

    for name in sorted(metric_data.keys()):
        base_vals = metric_data[name]["base"]
        exp_vals = metric_data[name]["exp"]
        unit = metric_data[name]["unit"]

        n1, n2 = len(base_vals), len(exp_vals)
        if n1 < 2 or n2 < 2:
            continue

        m1 = sum(base_vals) / n1
        m2 = sum(exp_vals) / n2
        v1 = sum((x - m1) ** 2 for x in base_vals) / (n1 - 1)
        v2 = sum((x - m2) ** 2 for x in exp_vals) / (n2 - 1)

        se1_sq = v1 / n1
        se2_sq = v2 / n2
        se_diff = math.sqrt(se1_sq + se2_sq)

        if se_diff > 1e-15:
            t_stat = (m2 - m1) / se_diff
            denom = (se1_sq**2) / (n1 - 1) + (se2_sq**2) / (n2 - 1)
            df = ((se1_sq + se2_sq) ** 2) / denom if denom > 0 else 1
            p_val = student_t_p_value(t_stat, df)
            t_crit = student_t_crit_95(df)
        else:
            df = n1 + n2 - 2
            t_crit = 1.96
            if abs(m2 - m1) < 1e-15:
                t_stat = 0.0
                p_val = 1.0
            else:
                t_stat = 999.0 if m2 > m1 else -999.0
                p_val = 0.0

        diff = m2 - m1
        delta_pct = (diff / m1 * 100) if m1 != 0 else 0.0
        ci_low_pct = ((diff - t_crit * se_diff) / m1 * 100) if m1 != 0 else 0.0
        ci_high_pct = ((diff + t_crit * se_diff) / m1 * 100) if m1 != 0 else 0.0

        is_score = "biggerIsBetter" in unit
        is_stat_sig = p_val < 0.05

        if is_score:
            is_regression = is_stat_sig and delta_pct < 0
            is_win = is_stat_sig and delta_pct > 0
        else:
            # For story execution times, lower ms is better
            is_regression = is_stat_sig and delta_pct > 0
            is_win = is_stat_sig and delta_pct < 0

        metric_entry = {
            "base_mean": round(m1, 4),
            "exp_mean": round(m2, 4),
            "delta_pct": round(delta_pct, 4),
            "ci_95_low_pct": round(ci_low_pct, 4),
            "ci_95_high_pct": round(ci_high_pct, 4),
            "t_stat": round(t_stat, 4),
            "p_value": round(p_val, 4),
            "df": round(df, 1),
            "base_count": n1,
            "exp_count": n2,
            "unit": unit,
            "is_stat_sig": is_stat_sig,
            "is_regression": is_regression,
            "is_win": is_win,
        }
        results["metrics"][name] = metric_entry

        if is_regression:
            results["regressions"].append(name)
        elif is_win:
            results["wins"].append(name)

    if "Score" in results["metrics"]:
        results["score"] = results["metrics"]["Score"]

    results["verdict"] = "INVALID" if "Score" not in results["metrics"] else "INCONCLUSIVE"
    if plan is not None:
        results.update(fleet_decision(metric_data, plan))
    results["raw_sha256"] = __import__("hashlib").sha256(content.encode()).hexdigest()

    return results


def fleet_decision(metrics, plan):
    """Independent attempt histograms, log Welch bounds; no inner-iteration n."""
    import statistics
    import statistics_policy as policy
    spec = policy.validate_plan(plan["statistics"])
    expected = set(plan["identity"]["workloads"]) | {"Score"}
    # Extra submetrics remain diagnostic; every required workload must exist.
    if not expected <= set(metrics):
        return {"verdict": "INVALID", "error": "missing planned fleet metrics"}
    targets = ["Score"] if spec["primary"] == "suite" else spec["primary"]
    if not set(targets) <= expected:
        raise ValueError("primary metrics do not belong to the planned inventory")
    bounds = {}; components = {}
    family_alpha = spec["alpha"] / (len(expected) + 1)
    for name in expected:
        row = metrics[name]
        if any(len(row[a]) != spec["blocks"] for a in ("base", "exp")):
            return {"verdict": "INVALID", "error": "fleet attempt count differs from fixed plan"}
        a, b = ([math.log(x) for x in row[arm]] for arm in ("base", "exp"))
        v1, v2 = statistics.variance(a)/len(a), statistics.variance(b)/len(b)
        se = math.sqrt(v1+v2)
        df = (v1+v2)**2/(v1*v1/(len(a)-1)+v2*v2/(len(b)-1)) if se else len(a)+len(b)-2
        delta = statistics.fmean(b)-statistics.fmean(a)
        if "smallerIsBetter" in row["unit"]: delta = -delta
        half = policy.t_critical(df, family_alpha)*se
        bounds[name] = [100*math.expm1(delta-half), 100*math.expm1(delta+half)]
        components[name] = (delta, half)
    # Sum marginal error bounds, allowing arbitrary inter-metric correlation.
    mean = statistics.fmean(components[n][0] for n in targets)
    half = statistics.fmean(components[n][1] for n in targets)
    primary_ci = [100*math.expm1(mean-half),100*math.expm1(mean+half)]
    margin = lambda n: spec["suite_regression_margin_pct"] if n == "Score" else spec["regression_margin_pct"]
    regressions = [n for n, ci in bounds.items() if ci[1] < -margin(n)]
    unresolved = [n for n, ci in bounds.items() if ci[0] < -margin(n)]
    verdict = "REGRESSION" if regressions else "IMPROVEMENT" if primary_ci[0] >= spec["minimum_effect_pct"] and not unresolved else "INCONCLUSIVE"
    return {"verdict": verdict, "primary_ci_pct": primary_ci, "guardrail_bounds": bounds,
            "regressions": regressions, "unresolved_regression_bounds": unresolved,
            "plan": plan, "simultaneous_alpha": family_alpha}


def print_summary_table(results):
    """Print an ASCII scorecard table of the Pinpoint results."""
    print("\n" + "=" * 92)
    print(f"Pinpoint Job: {results.get('job_id')} | Bot: {results.get('bot')}")
    if results.get("cl_url"):
        print(f"Gerrit CL:    {results.get('cl_url')}")
    print(f"Overall Verdict: {results.get('verdict')}")
    print("=" * 92)
    print(f"{'Metric':<42} {'Base':>9} {'Exp':>9} {'Delta':>8} {'95% CI':>16} {'t-stat':>7} {'p-val':>7}")
    print("-" * 92)

    score = results.get("score")
    if score:
        ci_str = f"[{score['ci_95_low_pct']:+.2f}%, {score['ci_95_high_pct']:+.2f}%]"
        print(
            f"{'Score (Higher is better)':<42} {score['base_mean']:>9.2f} {score['exp_mean']:>9.2f} "
            f"{score['delta_pct']:>+7.2f}% {ci_str:>16} {score['t_stat']:>7.2f} {score['p_value']:>7.3f}"
        )
        print("-" * 92)

    for name, m in sorted(results.get("metrics", {}).items()):
        if name.lower() == "score":
            continue
        flag = " [REGRESSION]" if m["is_regression"] else (" [WIN]" if m["is_win"] else "")
        display_name = (name[:38] + ".." if len(name) > 40 else name) + flag
        ci_str = f"[{m['ci_95_low_pct']:+.2f}%, {m['ci_95_high_pct']:+.2f}%]"
        print(
            f"{display_name:<42} {m['base_mean']:>9.2f} {m['exp_mean']:>9.2f} "
            f"{m['delta_pct']:>+7.2f}% {ci_str:>16} {m['t_stat']:>7.2f} {m['p_value']:>7.3f}"
        )
    print("=" * 92)

    if results["regressions"]:
        print(f"\nWARNING: {len(results['regressions'])} statistically significant regression(s) detected:")
        for r in results["regressions"]:
            print(f"  - {r}")
    if results["wins"]:
        print(f"\nStatistically significant win(s) detected:")
        for w in results["wins"]:
            print(f"  + {w}")


def main():
    parser = argparse.ArgumentParser(
        description="Automate Pinpoint A/B tryjobs for optimization campaigns."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: upload-cl
    p_upload = subparsers.add_parser("upload-cl", help="Upload current diff as a Gerrit try CL.")
    p_upload.add_argument("-m", "--message", default=None, help="Commit / CL message.")

    # Subcommand: start
    p_start = subparsers.add_parser("start", help="Start a Pinpoint A/B tryjob.")
    p_start.add_argument("--cl", required=True, help="Gerrit CL URL or number.")
    p_start.add_argument("--benchmark", default=DEFAULT_BENCHMARK, help="Benchmark suite (default: speedometer3).")
    p_start.add_argument("--bot", default=DEFAULT_BOT, help="Bot configuration (default: mac-m1_mini_2020-perf-pgo).")
    p_start.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS, help="Number of attempts (default: 150).")
    p_start.add_argument("--story", default=DEFAULT_STORY, help="Story to run (default: Speedometer3).")
    p_start.add_argument("--base-commit", default="HEAD", help="Base commit hash (default: HEAD).")
    p_start.add_argument("--bug", default=None, help="Optional bug ID.")

    # Subcommand: wait
    p_wait = subparsers.add_parser("wait", help="Wait for a Pinpoint job to finish.")
    p_wait.add_argument("--job-id", required=True, help="Pinpoint job ID.")
    p_wait.add_argument("--poll-interval", type=int, default=30, help="Polling interval in seconds.")
    p_wait.add_argument("--timeout", type=int, default=7200, help="Timeout in seconds.")

    # Subcommand: fetch
    p_fetch = subparsers.add_parser("fetch", help="Download raw Pinpoint results HTML.")
    p_fetch.add_argument("--job-id", required=True, help="Pinpoint job ID.")
    p_fetch.add_argument("--out", required=True, help="Output file path.")

    # Subcommand: analyze
    p_analyze = subparsers.add_parser("analyze", help="Parse and analyze raw Pinpoint results.")
    p_analyze.add_argument("--job-id", default=None, help="Pinpoint job ID (fetches if --input not given).")
    p_analyze.add_argument("--input", default=None, help="Path to downloaded results HTML/JSON.")
    p_analyze.add_argument("--cl", default=None, help="Gerrit CL URL to record.")
    p_analyze.add_argument("--bot", default=None, help="Bot name.")
    p_analyze.add_argument("--out", default=None, help="Path to write JSON summary.")
    p_analyze.add_argument("--csv-out", default=None, help="Path to write CSV summary.")

    # Subcommand: abandon
    p_abandon = subparsers.add_parser("abandon", help="Abandon a failed or rejected Gerrit try CL.")
    p_abandon.add_argument("--cl", required=True, help="Gerrit CL URL or issue number.")
    p_abandon.add_argument("--reason", default="Abandoned candidate try CL", help="Abandonment reason.")

    # Subcommand: run (end-to-end pipeline)
    p_run = subparsers.add_parser("run", help="Full pipeline: upload try CL, run Pinpoint, analyze, and abandon if regressed.")
    p_run.add_argument("--cl", default=None, help="Existing Gerrit CL URL (if omitted, uploads current git state).")
    p_run.add_argument("-m", "--message", default=None, help="Commit message if uploading a new CL.")
    p_run.add_argument("--benchmark", default=DEFAULT_BENCHMARK, help="Benchmark suite (default: speedometer3).")
    p_run.add_argument("--bot", default=DEFAULT_BOT, help="Bot configuration (default: mac-m1_mini_2020-perf-pgo).")
    p_run.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS, help="Number of attempts (default: 150).")
    p_run.add_argument("--story", default=DEFAULT_STORY, help="Story to run (default: Speedometer3).")
    p_run.add_argument("--base-commit", default="HEAD", help="Base commit hash (default: HEAD).")
    p_run.add_argument("--bug", default=None, help="Optional bug ID.")
    p_run.add_argument("--out", default=None, help="Path to write JSON summary.")
    p_run.add_argument("--raw-out", default=None, help="Path to write raw HTML results.")
    p_run.add_argument("--poll-interval", type=int, default=30, help="Polling interval in seconds.")
    p_run.add_argument("--timeout", type=int, default=7200, help="Timeout in seconds.")
    p_run.add_argument(
        "--auto-abandon-on-fail",
        action="store_true",
        default=False,
        help="Automatically abandon the Gerrit CL if the job detects stat-sig regressions.",
    )
    p_run.add_argument(
        "--no-auto-abandon",
        dest="auto_abandon_on_fail",
        action="store_false",
        help="Do not automatically abandon the CL on failure.",
    )

    for p in (p_start, p_run):
        p.add_argument("--base-extra-args", default="")
        p.add_argument("--experiment-extra-args", default="")
    for p in (p_run, p_analyze):
        p.add_argument("--plan", help="Immutable preregistered experiment plan JSON")
    args = parser.parse_args()
    plan = json.loads(pathlib.Path(args.plan).read_text()) if getattr(args, "plan", None) else None
    if plan and args.subcommand == "run":
        identity = plan["identity"]
        if (args.cl != identity["patchset_url"] or args.base_commit != identity["baseline_sha"]
                or args.benchmark != identity["benchmark"]
                or args.attempts != plan["statistics"]["blocks"]
                or args.base_extra_args
                or args.experiment_extra_args != "--enable-features=" + identity["feature"]):
            parser.error("fleet invocation differs from registered plan")

    if args.subcommand == "upload-cl":
        info = upload_try_cl(message=args.message)
        print(json.dumps(info, indent=2))
        return 0

    if args.subcommand == "start":
        info = start_pinpoint_job(
            cl_url=args.cl,
            benchmark=args.benchmark,
            bot=args.bot,
            attempts=args.attempts,
            story=args.story,
            base_commit=args.base_commit,
            bug=args.bug,
            base_extra_args=args.base_extra_args,
            experiment_extra_args=args.experiment_extra_args,
        )
        print(json.dumps(info, indent=2))
        return 0

    if args.subcommand == "wait":
        info = wait_for_job(args.job_id, poll_interval=args.poll_interval, timeout=args.timeout)
        print(json.dumps(info, indent=2))
        return 0

    if args.subcommand == "fetch":
        fetch_results2(args.job_id, out_file=args.out)
        return 0

    if args.subcommand == "analyze":
        if args.input:
            content = pathlib.Path(args.input).read_text()
        elif args.job_id:
            content = fetch_results2(args.job_id)
        else:
            sys.exit("Error: must provide either --input or --job-id")

        results = parse_and_analyze_results(
            content, job_id=args.job_id, cl_url=args.cl, bot=args.bot, plan=plan
        )
        print_summary_table(results)

        if args.out:
            pathlib.Path(args.out).write_text(json.dumps(results, indent=2))
            print(f"Summary written to {args.out}", file=sys.stderr)

        if args.csv_out:
            with open(args.csv_out, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "metric",
                        "base_mean",
                        "exp_mean",
                        "delta_pct",
                        "ci_95_low",
                        "ci_95_high",
                        "t_stat",
                        "p_value",
                        "is_stat_sig",
                        "is_regression",
                        "is_win",
                    ],
                )
                writer.writeheader()
                for m_name, m_val in sorted(results["metrics"].items()):
                    writer.writerow({
                        "metric": m_name,
                        "base_mean": m_val["base_mean"],
                        "exp_mean": m_val["exp_mean"],
                        "delta_pct": m_val["delta_pct"],
                        "ci_95_low": m_val["ci_95_low_pct"],
                        "ci_95_high": m_val["ci_95_high_pct"],
                        "t_stat": m_val["t_stat"],
                        "p_value": m_val["p_value"],
                        "is_stat_sig": m_val["is_stat_sig"],
                        "is_regression": m_val["is_regression"],
                        "is_win": m_val["is_win"],
                    })
            print(f"CSV summary written to {args.csv_out}", file=sys.stderr)

        return 0 if results["verdict"] == "IMPROVEMENT" else 2

    if args.subcommand == "abandon":
        success = abandon_cl(args.cl, reason=args.reason)
        return 0 if success else 1

    if args.subcommand == "run":
        cl_url = args.cl
        if not cl_url:
            cl_info = upload_try_cl(message=args.message)
            cl_url = cl_info["url"]

        job_info = start_pinpoint_job(
            cl_url=cl_url,
            benchmark=args.benchmark,
            bot=args.bot,
            attempts=args.attempts,
            story=args.story,
            base_commit=args.base_commit,
            bug=args.bug,
            base_extra_args=args.base_extra_args,
            experiment_extra_args=args.experiment_extra_args,
        )
        job_id = job_info["job_id"]

        wait_for_job(job_id, poll_interval=args.poll_interval, timeout=args.timeout)
        content = fetch_results2(job_id, out_file=args.raw_out)

        results = parse_and_analyze_results(
            content, job_id=job_id, cl_url=cl_url, bot=args.bot, plan=plan
        )
        print_summary_table(results)

        if args.out:
            pathlib.Path(args.out).write_text(json.dumps(results, indent=2))
            print(f"Summary written to {args.out}", file=sys.stderr)

        if results["verdict"] != "IMPROVEMENT":
            print(f"\n[!] Gate Evaluation: Candidate {results['verdict']} ({len(results['regressions'])} regressions)", file=sys.stderr)
            if args.auto_abandon_on_fail and results["verdict"] == "REGRESSION":
                reason = f"optimize-campaign: candidate failed fleet validation with {len(results['regressions'])} regression(s)"
                abandon_cl(cl_url, reason=reason)
            return 2

        print(f"\n[+] Gate Evaluation: Candidate IMPROVEMENT (simultaneous bounds satisfied, CL preserved: {cl_url})", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
