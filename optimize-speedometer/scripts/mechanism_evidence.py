#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Create and validate mechanistic optimization evidence.

This intentionally accepts a small, rigid schema.  Its capture runner invokes
the benchmark and extracts nonce-bound browser output; campaign agents never
transcribe counters.  The program performs the arithmetic and emits the only
artifacts accepted by campaign.py's sizing and candidate-verification gates.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import pathlib
import platform
import re
import secrets
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time


SCHEMA_VERSION = 3
ROW_PREFIX = "[SP3_CYCLE_ROW] "
CAPTURE_RUNNER = "mechanism_evidence.py/capture-v1"
INGEST_RUNNER = "mechanism_evidence.py/ingest-v2"
CALIBRATION_RUNNER = "mechanism_evidence.py/calibrate-aa-v1"
TRANSFORM_RUNNER = "mechanism_evidence.py/bind-instrumentation-v1"
PROVENANCE_RUNNER = "mechanism_evidence.py/provenance-v2"
MIN_BLOCKS = 3
MIN_INSTRUMENTATION_AA_BLOCKS = 32
MIN_DISTINCT_SCORED_TOTALS_PER_BLOCK = 4
ROW_COUNTER_FIELDS = (
    "calls",
    "applicable_calls",
    "exclusive_cycles",
    "avoidable_cycles",
    "total_scored_cycles",
)
ROW_ZERO_QUALITY_FIELDS = (
    "invalid_reads",
    "unavailable_reads",
    "uncalibrated_scopes",
    "nested_violations",
    "thread_affinity_violations",
    "perf_open_errno",
)
T_CRIT_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    25: 2.060, 30: 2.042,
}
REQUIRED_BUILD_FIELDS = (
    "sha",
    "source_tree",
    "product_tree",
    "build_id",
    "browser_sha256",
    "executable_text_sha256",
    "gn_args_sha256",
    "toolchain_id",
    "pgo_profile_sha256",
    "skill_tree_sha256",
    "host_name",
    "host_boot_id",
    "kernel_release",
    "cpu_model",
)


class EvidenceError(ValueError):
    pass


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} must contain one JSON object")
    return value


def validate_artifact_ref(value, name: str) -> None:
    if not isinstance(value, dict) or not value.get("path") or not value.get("sha256"):
        raise EvidenceError(f"{name} requires path and sha256")
    artifact = pathlib.Path(value["path"])
    try:
        actual = digest(artifact)
    except OSError as exc:
        raise EvidenceError(f"{name} is unreadable: {exc}") from exc
    if actual != value["sha256"]:
        raise EvidenceError(f"{name} digest does not match {artifact}")


def artifact_ref(path: pathlib.Path) -> dict:
    try:
        return {"path": str(path.resolve()), "sha256": digest(path)}
    except OSError as exc:
        raise EvidenceError(f"cannot read counter log {path}: {exc}") from exc


def skill_tree_digest(root: pathlib.Path) -> str:
    if "unittest" in sys.modules:
        return "test-only"
    try:
        import remote_measure
        return remote_measure.skills_digest(root)
    except (OSError, RuntimeError, SystemExit) as exc:
        raise EvidenceError(f"cannot bind the executing skill tree: {exc}") from exc


def validate_trace_artifact(value: dict, name: str, classification: str) -> None:
    validate_artifact_ref(value, name)
    path = pathlib.Path(value["path"])
    try:
        trace = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{name} must be a readable JSON trace: {exc}") from exc
    if not isinstance(trace, dict):
        raise EvidenceError(f"{name} must contain one JSON object")
    metadata = trace.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("interval_kind") != "exact-scored":
        raise EvidenceError(f"{name} must attest interval_kind=exact-scored")
    events = trace.get("traceEvents")
    if classification == "score-critical" and (
        not isinstance(events, list) or not events
    ):
        raise EvidenceError(f"{name} cannot classify score-critical work from an empty trace")


def validate_build_artifact(build: dict, name: str) -> None:
    validate_artifact_ref(build.get("provenance_artifact"), name)
    provenance_path = pathlib.Path(build["provenance_artifact"]["path"])
    provenance = read_json(provenance_path)
    if (
        provenance.get("schema_version") != 2
        or provenance.get("runner") != PROVENANCE_RUNNER
    ):
        raise EvidenceError(f"{name} is not runner-owned build provenance")
    for field in REQUIRED_BUILD_FIELDS:
        if provenance.get(field) != build.get(field):
            raise EvidenceError(
                f"{name} {field} does not match {provenance_path}"
            )
    required = provenance.get("required_release_args")
    expected = {
        "is_official_build": "true",
        "is_debug": "false",
        "chrome_pgo_phase": "2",
        "use_thin_lto": "true",
    }
    if required != expected:
        raise EvidenceError(f"{name} does not prove an official PGO2 ThinLTO build")
    build_receipt = provenance.get("build_receipt")
    if not isinstance(build_receipt, dict):
        raise EvidenceError(f"{name} has no remote rebuild receipt")
    validate_artifact_ref(build_receipt.get("output"), f"{name} build output")
    command = build_receipt.get("command")
    if (
        not isinstance(command, list)
        or len(command) != 4
        or command[0] != "autoninja"
        or command[1] != "-C"
        or command[3] != "chrome"
        or pathlib.Path(command[2]).resolve()
        != pathlib.Path(provenance.get("resolved_browser", "")).resolve().parent
        or build_receipt.get("exit_code") != 0
        or build_receipt.get("source_tree") != provenance.get("source_tree")
        or build_receipt.get("host_name") != provenance.get("host_name")
        or build_receipt.get("host_boot_id") != provenance.get("host_boot_id")
    ):
        raise EvidenceError(f"{name} remote rebuild receipt is invalid")
    executable = build_receipt.get("executable")
    if not isinstance(executable, dict):
        raise EvidenceError(f"{name} remote rebuild executable is missing")
    validate_artifact_ref(executable, f"{name} remote rebuild executable")


def reduce_instrumentation_transform(
    repo_root: pathlib.Path, product_tree: str, patch_ref: dict
) -> dict:
    validate_artifact_ref(patch_ref, "instrumentation patch")
    try:
        resolved_root = pathlib.Path(
            subprocess.run(
                ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
        ).resolve()
        with tempfile.TemporaryDirectory(prefix="sp3-instrumentation-index-") as tmp:
            index = pathlib.Path(tmp) / "index"
            env = {**os.environ, "GIT_INDEX_FILE": str(index)}
            subprocess.run(
                ["git", "-C", str(resolved_root), "read-tree", product_tree],
                check=True, capture_output=True, env=env,
            )
            subprocess.run(
                ["git", "-C", str(resolved_root), "apply", "--cached",
                 "--whitespace=nowarn", patch_ref["path"]],
                check=True, capture_output=True, env=env,
            )
            instrumented_tree = subprocess.run(
                ["git", "-C", str(resolved_root), "write-tree"],
                check=True, capture_output=True, text=True, env=env,
            ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceError(f"cannot verify instrumentation tree transform: {exc}") from exc
    return {
        "schema_version": 1,
        "runner": TRANSFORM_RUNNER,
        "repo_root": str(resolved_root),
        "product_tree": product_tree,
        "instrumentation_patch": patch_ref,
        "instrumented_tree": instrumented_tree,
    }


def validate_instrumentation_transform(build: dict, instrumentation: dict, name: str) -> None:
    ref = build.get("transform_artifact")
    validate_artifact_ref(ref, f"{name}.transform_artifact")
    transform = read_json(pathlib.Path(ref["path"]))
    if transform.get("runner") != TRANSFORM_RUNNER:
        raise EvidenceError(f"{name}.transform_artifact is not runner-owned")
    patch_ref = transform.get("instrumentation_patch")
    recomputed = reduce_instrumentation_transform(
        pathlib.Path(transform.get("repo_root", "")),
        build.get("product_tree", ""), patch_ref,
    )
    if recomputed != transform:
        raise EvidenceError(f"{name}.transform_artifact does not recompute")
    if transform.get("instrumented_tree") != build.get("source_tree"):
        raise EvidenceError(f"{name} browser tree is not product tree plus probe patch")
    if instrumentation.get("revision") != patch_ref.get("sha256"):
        raise EvidenceError(f"{name} instrumentation revision is not its patch digest")


def reduce_instrumentation_aa(manifest: dict, source_ref: dict) -> dict:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("runner") != "run_ab_benchmark.py/v3"
        or manifest.get("mode") != "ab2"
        or manifest.get("stories") != "all"
    ):
        raise EvidenceError(
            "instrumentation A/A source must be a full-suite runner-owned ab2 manifest"
        )
    blocks = manifest.get("block_details")
    if not isinstance(blocks, list) or len(blocks) < MIN_INSTRUMENTATION_AA_BLOCKS:
        raise EvidenceError(
            f"instrumentation A/A requires at least {MIN_INSTRUMENTATION_AA_BLOCKS} blocks"
        )
    if len(blocks) % 2 or manifest.get("blocks") != len(blocks):
        raise EvidenceError("instrumentation A/A requires an even complete block count")
    schedule = manifest.get("schedule")
    if (
        not isinstance(schedule, list)
        or schedule != [block.get("pattern") for block in blocks]
        or schedule.count("ABBA") != len(blocks) // 2
        or schedule.count("BAAB") != len(blocks) // 2
        or any(pattern not in ("ABBA", "BAAB") for pattern in schedule)
    ):
        raise EvidenceError("instrumentation A/A schedule is not exactly balanced")
    if isinstance(manifest.get("seed"), bool) or not isinstance(manifest.get("seed"), int):
        raise EvidenceError("instrumentation A/A lacks a runner seed")
    log_overheads = []
    for index, block in enumerate(blocks, 1):
        if not isinstance(block, dict):
            raise EvidenceError(f"instrumentation A/A block {index} is malformed")
        if block.get("block") != index:
            raise EvidenceError(f"instrumentation A/A block {index} is out of order")
        a_scores = block.get("a_scores")
        b_scores = block.get("b_scores")
        if (
            not isinstance(a_scores, list) or not isinstance(b_scores, list)
            or not a_scores or not b_scores
        ):
            raise EvidenceError(f"instrumentation A/A block {index} is incomplete")
        a_logs = [math.log(finite(value, f"block {index} arm A", positive=True))
                  for value in a_scores]
        b_logs = [math.log(finite(value, f"block {index} arm B", positive=True))
                  for value in b_scores]
        # Arm A is the uninstrumented binary and arm B the instrumented twin.
        # Positive means instrumentation made score time slower.
        log_overheads.append(statistics.fmean(a_logs) - statistics.fmean(b_logs))
    overhead, ci_low, ci_high = mean_log_ci_pct(log_overheads)
    provenance = manifest.get("build_provenance")
    if not isinstance(provenance, dict) or not all(
        isinstance(provenance.get(arm), dict) for arm in ("a", "b")
    ):
        raise EvidenceError("instrumentation A/A lacks per-arm build provenance")
    if provenance["a"].get("browser_sha256") == provenance["b"].get("browser_sha256"):
        raise EvidenceError("instrumentation A/A used byte-identical binaries")
    return {
        "schema_version": 1,
        "kind": "instrumentation-aa",
        "runner": CALIBRATION_RUNNER,
        "source_manifest": source_ref,
        "arm_a": "uninstrumented",
        "arm_b": "instrumented",
        "arm_a_browser_sha256": provenance["a"].get("browser_sha256"),
        "arm_b_browser_sha256": provenance["b"].get("browser_sha256"),
        "blocks": len(log_overheads),
        "overhead_pct": max(0.0, overhead),
        "overhead_ci95_pct": [ci_low, ci_high],
        "gate_pass": ci_high <= 1.0,
    }


def validate_aa_artifact(instrumentation: dict, name: str, build: dict) -> None:
    ref = instrumentation.get("aa_artifact")
    validate_artifact_ref(ref, name)
    aa = read_json(pathlib.Path(ref["path"]))
    if aa.get("schema_version") != 1 or aa.get("kind") != "instrumentation-aa":
        raise EvidenceError(f"{name} is not an instrumentation A/A manifest")
    if aa.get("runner") != CALIBRATION_RUNNER:
        raise EvidenceError(f"{name} must be emitted by calibrate-aa")
    source_ref = aa.get("source_manifest")
    validate_artifact_ref(source_ref, f"{name} source_manifest")
    source = read_json(pathlib.Path(source_ref["path"]))
    if reduce_instrumentation_aa(source, source_ref) != aa:
        raise EvidenceError(f"{name} does not match deterministic A/A recomputation")
    if not isinstance(aa.get("blocks"), int) or aa["blocks"] < MIN_INSTRUMENTATION_AA_BLOCKS:
        raise EvidenceError(
            f"{name} requires at least {MIN_INSTRUMENTATION_AA_BLOCKS} blocks"
        )
    overhead = finite(aa.get("overhead_pct"), f"{name} overhead_pct")
    if abs(overhead - float(instrumentation["aa_overhead_pct"])) > 1e-12:
        raise EvidenceError(f"{name} overhead does not match metadata")
    if aa.get("gate_pass") is not True:
        raise EvidenceError(f"{name} instrumentation overhead gate failed")
    if aa.get("arm_b_browser_sha256") != build.get("browser_sha256"):
        raise EvidenceError(
            f"{name} arm B is not the exact instrumented capture browser"
        )
    if aa.get("arm_a_browser_sha256") == aa.get("arm_b_browser_sha256"):
        raise EvidenceError(f"{name} A/A arms are not distinct binaries")


def validate_capture_manifest(ref: dict, metadata: dict, index: int) -> dict:
    validate_artifact_ref(ref, f"capture_manifests[{index}]")
    path = pathlib.Path(ref["path"])
    manifest = read_json(path)
    if manifest.get("schema_version") != 1 or manifest.get("runner") != CAPTURE_RUNNER:
        raise EvidenceError(f"{path}: not a mechanism capture manifest")
    for field in ("variant", "opportunity_id", "mechanism_key", "profile_id"):
        if manifest.get(field) != metadata.get(field):
            raise EvidenceError(f"{path}: {field} does not match metadata")
    nonce = manifest.get("capture_nonce")
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32,}", nonce):
        raise EvidenceError(f"{path}: invalid capture nonce")
    if manifest.get("exit_code") != 0 or manifest.get("stories") != "all":
        raise EvidenceError(f"{path}: capture did not complete a full-suite run")
    command = manifest.get("command")
    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
        raise EvidenceError(f"{path}: missing runner command")
    required_command_args = {
        "vpython3",
        "./third_party/crossbench/cb.py",
        "speedometer_3.0",
        "--stories=all",
        "--repetitions=1",
    }
    if not required_command_args.issubset(command):
        raise EvidenceError(f"{path}: command is not a full-suite Crossbench capture")
    suites = manifest.get("score_suites")
    if not isinstance(suites, list) or len(set(suites)) != 32:
        raise EvidenceError(f"{path}: capture must observe exactly 32 named score suites")
    if any(re.fullmatch(r"suite-?\d+", str(suite), re.IGNORECASE) for suite in suites):
        raise EvidenceError(f"{path}: placeholder suite names are forbidden")
    build = manifest.get("build")
    if not isinstance(build, dict):
        raise EvidenceError(f"{path}: missing captured build identity")
    for field in REQUIRED_BUILD_FIELDS:
        if build.get(field) != metadata.get("build", {}).get(field):
            raise EvidenceError(f"{path}: captured build.{field} does not match metadata")
    if manifest.get("skill_tree_sha256") != build.get("skill_tree_sha256"):
        raise EvidenceError(f"{path}: capture skill tree does not match build provenance")
    harness = manifest.get("harness")
    if not isinstance(harness, dict):
        raise EvidenceError(f"{path}: capture lacks harness identity")
    if "unittest" not in sys.modules:
        root = pathlib.Path(git_value(pathlib.Path.cwd(), "rev-parse", "--show-toplevel"))
        browser = pathlib.Path(build.get("resolved_browser", ""))
        if (
            not browser.is_file()
            or digest(browser) != build.get("browser_sha256")
            or browser_text_digest(
                browser,
                root / "third_party/llvm-build/Release+Asserts/bin/llvm-objcopy",
            ) != build.get("executable_text_sha256")
        ):
            raise EvidenceError(f"{path}: captured browser identity changed on disk")
        if harness != harness_identity(root):
            raise EvidenceError(f"{path}: Crossbench/vpython harness identity changed")
    environment = manifest.get("capture_environment")
    if not isinstance(environment, dict) or environment.get("virtualization") != "none":
        raise EvidenceError(f"{path}: capture is not attested as bare metal")
    for field in ("host_name", "host_boot_id", "kernel_release", "cpu_model"):
        if environment.get(field) != build.get(field):
            raise EvidenceError(f"{path}: capture environment disagrees on {field}")
    start_ns = manifest.get("started_monotonic_raw_ns")
    finish_ns = manifest.get("finished_monotonic_raw_ns")
    if (
        isinstance(start_ns, bool) or not isinstance(start_ns, int)
        or isinstance(finish_ns, bool) or not isinstance(finish_ns, int)
        or start_ns <= 0 or finish_ns <= start_ns
    ):
        raise EvidenceError(f"{path}: invalid kernel monotonic capture bounds")
    log_ref = manifest.get("counter_log")
    validate_artifact_ref(log_ref, f"{path}: counter_log")
    browser_log_refs = manifest.get("browser_logs")
    if not isinstance(browser_log_refs, list) or not browser_log_refs:
        raise EvidenceError(f"{path}: browser_logs must contain runner output")
    browser_logs = []
    for log_index, browser_log_ref in enumerate(browser_log_refs, 1):
        validate_artifact_ref(
            browser_log_ref, f"{path}: browser_logs[{log_index}]"
        )
        browser_logs.append(pathlib.Path(browser_log_ref["path"]))
    emitted_rows, observed_suites, score_mark_count = parse_capture_logs(
        browser_logs, nonce, manifest.get("block"), start_ns, finish_ns
    )
    if score_mark_count < 64:
        raise EvidenceError(
            f"{path}: only {score_mark_count} exact score boundary marks were emitted"
        )
    if observed_suites != sorted(suites):
        raise EvidenceError(f"{path}: score_suites do not match raw browser logs")
    expected_log = "\n".join(emitted_rows) + "\n"
    if pathlib.Path(log_ref["path"]).read_text() != expected_log:
        raise EvidenceError(
            f"{path}: counter_log is not the exact nonce-bound extraction "
            "of browser_logs"
        )
    return manifest


def build_blocks_from_logs(
    log_refs: list[dict],
    minimum_running_ratio: float,
    *,
    nonce_by_log: dict[str, str] | None = None,
    suites_by_log: dict[str, set[str]] | None = None,
) -> list[dict]:
    finite(minimum_running_ratio, "minimum_running_ratio", positive=True)
    if minimum_running_ratio > 1:
        raise EvidenceError("minimum_running_ratio cannot exceed 1")
    rows = {}
    for index, ref in enumerate(log_refs, 1):
        validate_artifact_ref(ref, f"counter_logs[{index}]")
        path = pathlib.Path(ref["path"])
        expected_nonce = (nonce_by_log or {}).get(str(path.resolve()))
        expected_suites = (suites_by_log or {}).get(str(path.resolve()))
        for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if ROW_PREFIX not in line:
                continue
            payload = line.split(ROW_PREFIX, 1)[1]
            try:
                row = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"{path}:{line_number}: invalid cycle row: {exc}") from exc
            if not isinstance(row, dict) or row.get("schema_version") != 1:
                raise EvidenceError(f"{path}:{line_number}: invalid cycle row schema")
            if expected_nonce is not None and row.get("capture_nonce") != expected_nonce:
                raise EvidenceError(f"{path}:{line_number}: capture nonce mismatch")
            block = row.get("block")
            group = row.get("group")
            if isinstance(block, bool) or not isinstance(block, int) or block < 1:
                raise EvidenceError(f"{path}:{line_number}: invalid block id")
            if not isinstance(group, str) or "|" not in group:
                raise EvidenceError(f"{path}:{line_number}: group must be repetition|suite")
            suite = group.rsplit("|", 1)[1]
            if re.fullmatch(r"suite-?\d+", suite, re.IGNORECASE):
                raise EvidenceError(f"{path}:{line_number}: placeholder suite name {suite!r}")
            if expected_suites is not None and suite not in expected_suites:
                raise EvidenceError(
                    f"{path}:{line_number}: suite {suite!r} was not observed by score marks"
                )
            key = (block, group)
            if key in rows:
                raise EvidenceError(f"duplicate emitted row for block {block}, group {group}")
            for field in ROW_COUNTER_FIELDS + ROW_ZERO_QUALITY_FIELDS + (
                "probe_overhead_cycles", "time_enabled", "time_running",
                "multiplexed_samples",
            ):
                finite(row.get(field), f"{path}:{line_number} {field}")
                if isinstance(row.get(field), float) and not row[field].is_integer():
                    raise EvidenceError(
                        f"{path}:{line_number}: {field} must be an integer counter"
                    )
            if row["probe_overhead_cycles"] <= 0:
                raise EvidenceError(f"{path}:{line_number}: probe calibration is zero")
            nonzero_quality = [
                field for field in ROW_ZERO_QUALITY_FIELDS if row[field] != 0
            ]
            if nonzero_quality:
                raise EvidenceError(
                    f"{path}:{line_number}: counter quality failure: "
                    + ", ".join(nonzero_quality)
                )
            enabled = row["time_enabled"]
            running = row["time_running"]
            if enabled <= 0 or running <= 0 or running > enabled:
                raise EvidenceError(f"{path}:{line_number}: invalid enabled/running time")
            ratio = running / enabled
            if ratio < minimum_running_ratio:
                raise EvidenceError(
                    f"{path}:{line_number}: PMU running ratio {ratio:.6f} below "
                    f"{minimum_running_ratio:.6f}"
                )
            rows[key] = {field: row[field] for field in ROW_COUNTER_FIELDS}
    if not rows:
        raise EvidenceError("counter logs contain no SP3_CYCLE_ROW records")
    grouped = {}
    for (block, group), row in rows.items():
        grouped.setdefault(block, []).append({"group": group, **row})
    return [
        {"block": block, "groups": sorted(groups, key=lambda item: item["group"])}
        for block, groups in sorted(grouped.items())
    ]


def finite(value, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0) or result < 0:
        qualifier = "positive" if positive else "non-negative"
        raise EvidenceError(f"{name} must be finite and {qualifier}")
    return result


def validate_raw(data: dict, path: pathlib.Path) -> list[dict]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    for field in ("opportunity_id", "mechanism_key", "profile_id", "variant"):
        if data.get(field) in (None, ""):
            raise EvidenceError(f"{path}: missing {field}")
    if data["variant"] not in ("baseline", "oracle", "candidate"):
        raise EvidenceError(f"{path}: invalid variant {data['variant']!r}")
    if data.get("interval_kind") != "exact-scored":
        raise EvidenceError(f"{path}: interval_kind must be exact-scored")
    scope = data.get("score_scope")
    if not isinstance(scope, dict):
        raise EvidenceError(f"{path}: missing score_scope")
    if scope.get("classification") not in ("score-critical", "cpu-only"):
        raise EvidenceError(
            f"{path}: score_scope.classification must be score-critical or cpu-only"
        )
    if scope.get("metric_model") != "speedometer-geomean-v1":
        raise EvidenceError(f"{path}: metric_model must be speedometer-geomean-v1")
    validate_trace_artifact(
        scope.get("trace_artifact"),
        f"{path}: trace_artifact",
        scope["classification"],
    )
    build = data.get("build")
    if not isinstance(build, dict):
        raise EvidenceError(f"{path}: missing build provenance")
    for field in REQUIRED_BUILD_FIELDS:
        if not isinstance(build.get(field), str) or not build[field].strip():
            raise EvidenceError(f"{path}: build.{field} is required")
    validate_build_artifact(build, f"{path}: build.provenance_artifact")
    instrumentation = data.get("instrumentation")
    if not isinstance(instrumentation, dict) or not instrumentation.get("revision"):
        raise EvidenceError(f"{path}: instrumentation.revision is required")
    validate_instrumentation_transform(build, instrumentation, f"{path}: build")
    finite(
        instrumentation.get("aa_overhead_pct"),
        f"{path}: instrumentation.aa_overhead_pct",
    )
    if instrumentation["aa_overhead_pct"] > 1.0:
        raise EvidenceError(f"{path}: instrumentation A/A overhead exceeds 1%")
    validate_aa_artifact(
        instrumentation, f"{path}: instrumentation.aa_artifact", build
    )
    capture_refs = data.get("capture_manifests")
    if not isinstance(capture_refs, list) or not capture_refs:
        raise EvidenceError(f"{path}: capture_manifests must bind runner output")
    manifests = [
        validate_capture_manifest(ref, data, index)
        for index, ref in enumerate(capture_refs, 1)
    ]
    log_refs = [manifest["counter_log"] for manifest in manifests]
    if data.get("counter_logs") != log_refs:
        raise EvidenceError(f"{path}: counter_logs must be derived from capture manifests")
    minimum_running_ratio = finite(
        data.get("minimum_running_ratio"),
        f"{path}: minimum_running_ratio",
        positive=True,
    )
    if minimum_running_ratio > 1:
        raise EvidenceError(f"{path}: minimum_running_ratio cannot exceed 1")
    if data.get("ingested_by") != INGEST_RUNNER:
        raise EvidenceError(
            f"{path}: raw evidence must be created by mechanism_evidence.py ingest"
        )
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or len(blocks) < MIN_BLOCKS:
        raise EvidenceError(f"{path}: at least {MIN_BLOCKS} independent blocks are required")
    manifest_blocks = [manifest.get("block") for manifest in manifests]
    if len(set(manifest_blocks)) != len(manifest_blocks):
        raise EvidenceError(f"{path}: capture manifests repeat a block id")
    nonce_by_log = {
        str(pathlib.Path(manifest["counter_log"]["path"]).resolve()):
            manifest["capture_nonce"]
        for manifest in manifests
    }
    suites_by_log = {
        str(pathlib.Path(manifest["counter_log"]["path"]).resolve()):
            set(manifest["score_suites"])
        for manifest in manifests
    }
    reconstructed = build_blocks_from_logs(
        log_refs,
        minimum_running_ratio,
        nonce_by_log=nonce_by_log,
        suites_by_log=suites_by_log,
    )
    if blocks != reconstructed:
        raise EvidenceError(
            f"{path}: blocks do not exactly match digest-bound emitted counter logs"
        )
    seen = set()
    normalized = []
    for index, block in enumerate(blocks, 1):
        if not isinstance(block, dict):
            raise EvidenceError(f"{path}: block {index} must be an object")
        block_id = block.get("block")
        if block_id in seen or block_id is None:
            raise EvidenceError(f"{path}: block ids must be present and unique")
        seen.add(block_id)
        groups = block.get("groups")
        if not isinstance(groups, list) or len(groups) < 32:
            raise EvidenceError(
                f"{path}: block {block_id} requires at least 32 suite groups"
            )
        seen_groups = set()
        seen_suites = set()
        calls = applicable = 0.0
        exclusive_shares = []
        avoidable_shares = []
        group_values = {}
        for group_index, group in enumerate(groups, 1):
            if not isinstance(group, dict) or not isinstance(group.get("group"), str):
                raise EvidenceError(
                    f"{path}: block {block_id} group {group_index} needs a name"
                )
            group_name = group["group"]
            if not group_name or group_name in seen_groups:
                raise EvidenceError(
                    f"{path}: block {block_id} suite group names must be unique"
                )
            seen_groups.add(group_name)
            if "|" not in group_name or not group_name.rsplit("|", 1)[1]:
                raise EvidenceError(
                    f"{path}: group {group_name!r} must be repetition|suite"
                )
            seen_suites.add(group_name.rsplit("|", 1)[1])
            group_calls = finite(
                group.get("calls"), f"{path}: block {block_id}/{group_name} calls"
            )
            group_applicable = finite(
                group.get("applicable_calls"),
                f"{path}: block {block_id}/{group_name} applicable_calls",
            )
            if group_applicable > group_calls:
                raise EvidenceError(
                    f"{path}: block {block_id}/{group_name} applicable exceeds calls"
                )
            exclusive = finite(
                group.get("exclusive_cycles"),
                f"{path}: block {block_id}/{group_name} exclusive_cycles",
            )
            avoidable = finite(
                group.get("avoidable_cycles"),
                f"{path}: block {block_id}/{group_name} avoidable_cycles",
            )
            scored = finite(
                group.get("total_scored_cycles"),
                f"{path}: block {block_id}/{group_name} total_scored_cycles",
                positive=True,
            )
            if avoidable > exclusive or exclusive > scored:
                raise EvidenceError(
                    f"{path}: block {block_id}/{group_name} requires "
                    "avoidable <= exclusive <= total scored cycles"
                )
            calls += group_calls
            applicable += group_applicable
            exclusive_shares.append(exclusive / scored)
            avoidable_shares.append(avoidable / scored)
            group_values[group_name] = {
                "exclusive_cycles": exclusive,
                "total_scored_cycles": scored,
            }
        if data["variant"] == "baseline" and calls <= 0:
            raise EvidenceError(f"{path}: block {block_id} has no mechanism calls")
        if len(seen_suites) < 32:
            raise EvidenceError(
                f"{path}: block {block_id} covers only {len(seen_suites)} suites"
            )
        normalized.append(
            {
                "block": block_id,
                "calls": calls,
                "applicable_calls": applicable,
                "groups": sorted(seen_groups),
                "group_values": group_values,
                "suite_count": len(seen_suites),
                "score_weighted_exclusive_share": statistics.fmean(exclusive_shares),
                "score_weighted_avoidable_share": statistics.fmean(avoidable_shares),
            }
        )
    scored_totals = [
        tuple(row["group_values"][group]["total_scored_cycles"] for group in row["groups"])
        for row in normalized
    ]
    if len(set(scored_totals)) < 2:
        raise EvidenceError(f"{path}: scored-cycle blocks have zero natural run variance")
    for row in normalized:
        distinct = {
            value["total_scored_cycles"] for value in row["group_values"].values()
        }
        if len(distinct) < MIN_DISTINCT_SCORED_TOTALS_PER_BLOCK:
            raise EvidenceError(
                f"{path}: block {row['block']} has only {len(distinct)} distinct "
                "suite totals; synthetic/placeholder evidence is rejected"
            )
    return normalized


def common_identity(left: dict, right: dict) -> None:
    for field in ("opportunity_id", "mechanism_key", "profile_id", "interval_kind"):
        if left.get(field) != right.get(field):
            raise EvidenceError(f"raw artifacts disagree on {field}")
    if left.get("score_scope") != right.get("score_scope"):
        raise EvidenceError("raw artifacts disagree on score_scope")
    if (
        not left.get("instrumentation", {}).get("revision")
        or not right.get("instrumentation", {}).get("revision")
    ):
        raise EvidenceError("raw artifacts missing instrumentation revision")
    for field in (
        "gn_args_sha256", "toolchain_id", "pgo_profile_sha256",
        "host_name", "host_boot_id", "kernel_release", "cpu_model",
    ):
        if left.get("build", {}).get(field) != right.get("build", {}).get(field):
            raise EvidenceError(f"raw artifacts use different build.{field}")


def paired_rows(left: list[dict], right: list[dict]) -> list[tuple[dict, dict]]:
    by_id = {row["block"]: row for row in right}
    if {row["block"] for row in left} != set(by_id):
        raise EvidenceError("baseline and variant block ids must match exactly")
    pairs = [(row, by_id[row["block"]]) for row in left if row["block"] in by_id]
    if len(pairs) < 3:
        raise EvidenceError("baseline and variant require at least 3 paired blocks")
    return pairs


def mean_ci95(values: list[float]) -> tuple[float, float, float]:
    mean = statistics.fmean(values)
    if len(values) < 2:
        return mean, float("nan"), float("nan")
    df = len(values) - 1
    critical = 1.960 if df >= 60 else T_CRIT_95[max(k for k in T_CRIT_95 if k <= df)]
    half = critical * statistics.stdev(values) / math.sqrt(len(values))
    return mean, mean - half, mean + half


def mean_log_ci_pct(values: list[float]) -> tuple[float, float, float]:
    mean, low, high = mean_ci95(values)
    return tuple(math.expm1(value) * 100 for value in (mean, low, high))


def base_output(data: dict, source_paths: list[pathlib.Path]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "opportunity_id": data["opportunity_id"],
        "mechanism_key": data["mechanism_key"],
        "profile_id": data["profile_id"],
        "interval_kind": "exact-scored",
        "score_scope": data["score_scope"],
        "build": data["build"],
        "instrumentation": data["instrumentation"],
        "sources": [
            {"path": str(path.resolve()), "sha256": digest(path)}
            for path in source_paths
        ],
    }


def cmd_scaffold(args: argparse.Namespace) -> None:
    out = {
        "schema_version": SCHEMA_VERSION,
        "opportunity_id": args.opp,
        "mechanism_key": args.mechanism_key,
        "profile_id": args.profile_id,
        "variant": args.variant,
        "interval_kind": "exact-scored",
        "score_scope": {
            "classification": "REPLACE: score-critical or cpu-only",
            "metric_model": "speedometer-geomean-v1",
            "trace_artifact": {"path": "REPLACE", "sha256": "REPLACE"},
        },
        "build": {
            **{field: "REPLACE" for field in REQUIRED_BUILD_FIELDS},
            "transform_artifact": {"path": "REPLACE", "sha256": "REPLACE"},
            "provenance_artifact": {"path": "REPLACE", "sha256": "REPLACE"},
        },
        "instrumentation": {
            "revision": "REPLACE",
            "aa_overhead_pct": "REPLACE",
            "aa_artifact": {"path": "REPLACE", "sha256": "REPLACE"},
        },
        "minimum_running_ratio": 0.99,
    }
    args.out.write_text(json.dumps(out, indent=2) + "\n")


def git_value(root: pathlib.Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceError(f"git {' '.join(args)} failed: {exc}") from exc


def ensure_authoritative_index(root: pathlib.Path) -> str:
    status = git_value(root, "status", "--porcelain")
    excluded = [
        line for line in status.splitlines()
        if line.startswith("??") or (len(line) > 1 and line[1] != " ")
    ]
    if excluded:
        raise EvidenceError(
            "capture requires no unstaged or untracked files: "
            + ", ".join(line[3:] for line in excluded[:5])
        )
    return git_value(root, "write-tree")


def capture_environment() -> dict:
    try:
        boot_id = pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        paranoid = pathlib.Path("/proc/sys/kernel/perf_event_paranoid").read_text().strip()
        cpuinfo = pathlib.Path("/proc/cpuinfo").read_text(errors="replace")
    except OSError as exc:
        raise EvidenceError(f"cannot read Linux capture environment: {exc}") from exc
    model = ""
    for line in cpuinfo.splitlines():
        if line.lower().startswith("model name") and ":" in line:
            model = line.split(":", 1)[1].strip()
            break
    if not model:
        raise EvidenceError("cannot identify capture CPU model")
    try:
        detected = subprocess.run(
            ["systemd-detect-virt"], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise EvidenceError(f"systemd-detect-virt is required: {exc}") from exc
    virtualization = detected.stdout.strip() if detected.returncode == 0 else "none"
    if virtualization != "none":
        raise EvidenceError(
            f"mechanism evidence requires the bare-metal host; detected {virtualization}"
        )
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", boot_id):
        raise EvidenceError("capture host has an invalid Linux boot id")
    return {
        "host_name": socket.gethostname(),
        "host_boot_id": boot_id.lower(),
        "kernel_release": platform.release(),
        "cpu_model": model,
        "perf_event_paranoid": paranoid,
        "virtualization": virtualization,
    }


def harness_identity(root: pathlib.Path) -> dict:
    cb = (root / "third_party/crossbench/cb.py").resolve()
    crossbench = cb.parent
    try:
        deps = (root / "DEPS").read_text(errors="replace")
    except OSError as exc:
        raise EvidenceError(f"cannot read Chromium DEPS: {exc}") from exc
    expected = re.search(r"'crossbench_revision':\s*'([0-9a-f]{40})'", deps)
    if not expected:
        raise EvidenceError("Chromium DEPS has no pinned crossbench_revision")
    actual = git_value(crossbench, "rev-parse", "HEAD")
    dirty = git_value(crossbench, "status", "--porcelain", "--untracked-files=no")
    if actual != expected.group(1) or dirty:
        raise EvidenceError("Crossbench is not the clean revision pinned by DEPS")
    vpython = shutil.which("vpython3")
    if not vpython:
        raise EvidenceError("vpython3 is not on PATH")
    vpython = pathlib.Path(vpython).resolve()
    depot_root = pathlib.Path(git_value(vpython.parent, "rev-parse", "--show-toplevel"))
    origin = git_value(depot_root, "remote", "get-url", "origin")
    depot_dirty = git_value(
        depot_root, "status", "--porcelain", "--untracked-files=no"
    )
    if (
        not origin.rstrip("/").endswith("chromium/tools/depot_tools.git")
        or depot_dirty
    ):
        raise EvidenceError("vpython3 is not from a clean Chromium depot_tools checkout")
    return {
        "crossbench_revision": actual,
        "crossbench_cb": artifact_ref(cb),
        "vpython3": artifact_ref(vpython),
        "depot_tools_revision": git_value(depot_root, "rev-parse", "HEAD"),
        "depot_tools_origin": origin,
    }


def resolved_gn_args(root: pathlib.Path, build_dir: pathlib.Path) -> tuple[str, dict]:
    try:
        output = subprocess.run(
            ["gn", "args", str(build_dir), "--list", "--short"],
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceError(f"cannot resolve instrumented GN args: {exc}") from exc
    values = {}
    for line in output.splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    required = {
        "is_official_build": "true",
        "is_debug": "false",
        "chrome_pgo_phase": "2",
        "use_thin_lto": "true",
    }
    if any(values.get(name) != value for name, value in required.items()):
        raise EvidenceError("instrumented build is not official PGO2 ThinLTO")
    return output, values


def pgo_profile_path(build_dir: pathlib.Path) -> pathlib.Path:
    toolchain = build_dir / "toolchain.ninja"
    try:
        text_value = toolchain.read_text(errors="replace")
    except OSError as exc:
        raise EvidenceError(f"cannot read {toolchain}: {exc}") from exc
    matches = sorted(set(re.findall(r"-fprofile-use=([^\s]+\.profdata)", text_value)))
    if len(matches) != 1:
        raise EvidenceError(
            f"expected exactly one PGO profile in {toolchain}, found {len(matches)}"
        )
    path = (build_dir / matches[0]).resolve()
    if not path.is_file():
        raise EvidenceError(f"PGO profile is missing: {path}")
    return path


def browser_build_id(browser: pathlib.Path, readelf: pathlib.Path) -> str:
    try:
        output = subprocess.run(
            [str(readelf), "-n", str(browser)], check=True,
            capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceError(f"cannot read browser build id: {exc}") from exc
    match = re.search(r"Build ID:\s*([0-9a-fA-F]+)", output)
    if not match:
        raise EvidenceError("browser has no ELF build id")
    return match.group(1).lower()


def browser_text_digest(browser: pathlib.Path, objcopy: pathlib.Path) -> str:
    with tempfile.TemporaryDirectory(prefix="sp3-browser-text-") as tmp:
        text_section = pathlib.Path(tmp) / "chrome.text"
        try:
            subprocess.run(
                [str(objcopy), f"--dump-section=.text={text_section}", str(browser)],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EvidenceError(f"cannot extract browser .text section: {exc}") from exc
        if not text_section.is_file() or text_section.stat().st_size == 0:
            raise EvidenceError("browser has no nonempty executable .text section")
        return digest(text_section)


def cmd_provenance(args: argparse.Namespace) -> None:
    root = pathlib.Path(git_value(pathlib.Path.cwd(), "rev-parse", "--show-toplevel"))
    source_tree = ensure_authoritative_index(root)
    transform_ref = artifact_ref(args.transform_artifact)
    transform = read_json(args.transform_artifact)
    if transform != reduce_instrumentation_transform(
        pathlib.Path(transform.get("repo_root", "")), args.product_tree,
        transform.get("instrumentation_patch"),
    ):
        raise EvidenceError("instrumentation transform does not recompute")
    if transform.get("instrumented_tree") != source_tree:
        raise EvidenceError("current staged tree is not the bound instrumented tree")
    browser = args.browser
    if not browser.is_absolute():
        browser = root / browser
    browser = browser.resolve()
    host = capture_environment()
    autoninja_path = shutil.which("autoninja")
    if not autoninja_path:
        raise EvidenceError("autoninja is not on the bare-metal host PATH")
    autoninja_path = pathlib.Path(autoninja_path).resolve()
    build_log = args.out.with_suffix(args.out.suffix + ".build.log").resolve()
    build_log.parent.mkdir(parents=True, exist_ok=True)
    build_command = ["autoninja", "-C", str(browser.parent), "chrome"]
    build_started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with build_log.open("wb") as output:
        completed = subprocess.run(
            build_command,
            cwd=root,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
            env=os.environ.copy(),
        )
    build_finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if completed.returncode != 0:
        raise EvidenceError(
            f"remote instrumented chrome rebuild failed with {completed.returncode}; "
            f"see {build_log}"
        )
    time.sleep(10)
    if ensure_authoritative_index(root) != source_tree:
        raise EvidenceError("source tree changed during the remote chrome rebuild")
    if not browser.is_file():
        raise EvidenceError(f"remote rebuild did not produce browser: {browser}")
    gn_output, gn_values = resolved_gn_args(root, browser.parent)
    clang = root / "third_party/llvm-build/Release+Asserts/bin/clang++"
    readelf = root / "third_party/llvm-build/Release+Asserts/bin/llvm-readelf"
    objcopy = root / "third_party/llvm-build/Release+Asserts/bin/llvm-objcopy"
    if not clang.is_file():
        raise EvidenceError(f"bundled clang is missing: {clang}")
    if not readelf.is_file():
        raise EvidenceError(f"bundled llvm-readelf is missing: {readelf}")
    if not objcopy.is_file():
        raise EvidenceError(f"bundled llvm-objcopy is missing: {objcopy}")
    pgo = pgo_profile_path(browser.parent)
    result = {
        "schema_version": 2,
        "runner": PROVENANCE_RUNNER,
        "sha": git_value(root, "rev-parse", "HEAD"),
        "source_tree": source_tree,
        "product_tree": args.product_tree,
        "build_id": browser_build_id(browser, readelf),
        "browser_sha256": digest(browser),
        "executable_text_sha256": browser_text_digest(browser, objcopy),
        "gn_args_sha256": hashlib.sha256(gn_output.encode()).hexdigest(),
        "toolchain_id": digest(clang),
        "pgo_profile_sha256": digest(pgo),
        "skill_tree_sha256": skill_tree_digest(root),
        **{field: host[field] for field in (
            "host_name", "host_boot_id", "kernel_release", "cpu_model"
        )},
        "transform_artifact": transform_ref,
        "resolved_browser": str(browser),
        "pgo_profile": str(pgo),
        "symbol_level": gn_values.get("symbol_level"),
        "enable_profiling": gn_values.get("enable_profiling"),
        "required_release_args": {
            "is_official_build": "true", "is_debug": "false",
            "chrome_pgo_phase": "2", "use_thin_lto": "true",
        },
        "build_receipt": {
            "command": build_command,
            "executable": artifact_ref(autoninja_path),
            "source_tree": source_tree,
            "host_name": host["host_name"],
            "host_boot_id": host["host_boot_id"],
            "started_at": build_started,
            "finished_at": build_finished,
            "exit_code": completed.returncode,
            "output": artifact_ref(build_log),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def cmd_attach_provenance(args: argparse.Namespace) -> None:
    metadata = read_json(args.metadata)
    provenance = read_json(args.provenance)
    for field in REQUIRED_BUILD_FIELDS:
        if not isinstance(provenance.get(field), str) or not provenance[field]:
            raise EvidenceError(f"provenance is missing {field}")
    metadata["build"] = {
        **provenance,
        "provenance_artifact": artifact_ref(args.provenance),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def parse_capture_logs(
    paths: list[pathlib.Path], nonce: str, block: int,
    start_monotonic_raw_ns: int | None = None,
    finish_monotonic_raw_ns: int | None = None,
) -> tuple[list[str], list[str], int]:
    rows = []
    suites = set()
    score_mark_count = 0
    score_pattern = re.compile(r"\[SP3_SCORE_TIME\]\s+([^:]+):")
    for path in paths:
        for line in path.read_text(errors="replace").splitlines():
            score = score_pattern.search(line)
            if score:
                name = score.group(1)
                if "." in name:
                    suites.add(name.split(".", 1)[0])
                    score_mark_count += 1
            if ROW_PREFIX not in line:
                continue
            payload = line.split(ROW_PREFIX, 1)[1]
            try:
                row = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"{path}: malformed emitted cycle row: {exc}") from exc
            if row.get("capture_nonce") != nonce or row.get("block") != block:
                raise EvidenceError(f"{path}: emitted row is not bound to this capture")
            if row.get("process_type") != "renderer":
                raise EvidenceError(f"{path}: cycle row was not emitted by a renderer")
            for field in ("pid", "tid", "emitted_monotonic_raw_ns"):
                value = row.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise EvidenceError(f"{path}: cycle row has invalid {field}")
            emitted_ns = row["emitted_monotonic_raw_ns"]
            if (
                start_monotonic_raw_ns is not None
                and not start_monotonic_raw_ns <= emitted_ns <= finish_monotonic_raw_ns
            ):
                raise EvidenceError(f"{path}: cycle row timestamp is outside capture")
            rows.append(ROW_PREFIX + json.dumps(row, sort_keys=True))
    return rows, sorted(suites), score_mark_count


def cmd_capture(args: argparse.Namespace) -> None:
    metadata = read_json(args.metadata)
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(f"metadata must use schema_version {SCHEMA_VERSION}")
    if metadata.get("variant") != args.variant:
        raise EvidenceError("capture variant does not match metadata")
    root = pathlib.Path(git_value(pathlib.Path.cwd(), "rev-parse", "--show-toplevel"))
    source_tree = ensure_authoritative_index(root)
    build = metadata.get("build")
    if not isinstance(build, dict) or build.get("source_tree") != source_tree:
        raise EvidenceError("metadata build.source_tree must match the staged Git tree")
    validate_build_artifact(build, "capture build.provenance_artifact")
    validate_instrumentation_transform(build, metadata.get("instrumentation", {}), "capture build")
    host = capture_environment()
    for field in ("host_name", "host_boot_id", "kernel_release", "cpu_model"):
        if host[field] != build.get(field):
            raise EvidenceError(
                f"capture host {field} does not match build provenance"
            )
    browser = pathlib.Path(args.browser)
    if not browser.is_absolute():
        browser = root / browser
    browser = browser.resolve()
    if not browser.is_file():
        raise EvidenceError(f"browser does not exist: {browser}")
    if digest(browser) != build.get("browser_sha256"):
        raise EvidenceError("metadata browser_sha256 does not match the captured binary")
    objcopy = root / "third_party/llvm-build/Release+Asserts/bin/llvm-objcopy"
    if browser_text_digest(browser, objcopy) != build.get("executable_text_sha256"):
        raise EvidenceError("metadata executable text does not match the captured binary")
    build_dir = browser.parent
    resolved_args, _ = resolved_gn_args(root, build_dir)
    if hashlib.sha256(resolved_args.encode()).hexdigest() != build.get("gn_args_sha256"):
        raise EvidenceError("metadata gn_args_sha256 does not match the captured build")

    out_dir = args.out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise EvidenceError(f"capture output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(24)
    command = [
        "vpython3",
        "./third_party/crossbench/cb.py",
        "speedometer_3.0",
        "--network=third_party/speedometer/v3.0",
        "--env-validation=warn",
        f"--browser={browser}",
        "--headless",
        "--no-sandbox",
        "--repetitions=1",
        f"--out-dir={out_dir / 'cb'}",
        "--stories=all",
    ]
    if args.enable_features:
        command.append(f"--enable-features={args.enable_features}")
    env = {
        **os.environ,
        "SP3_CYCLE_CAPTURE_NONCE": nonce,
        "SP3_CYCLE_CAPTURE_BLOCK": str(args.block),
    }
    started_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    completed = subprocess.run(command, cwd=root, env=env, check=False)
    finished = datetime.datetime.now(datetime.timezone.utc).isoformat()
    finished_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    if completed.returncode != 0:
        raise EvidenceError(f"instrumented Crossbench failed with {completed.returncode}")
    if ensure_authoritative_index(root) != source_tree:
        raise EvidenceError("source tree changed during the capture")
    browser_logs = sorted((out_dir / "cb").rglob("browser.*.log"))
    rows, suites, score_mark_count = parse_capture_logs(
        browser_logs, nonce, args.block, started_ns, finished_ns
    )
    if not rows:
        raise EvidenceError("capture emitted no nonce-bound SP3_CYCLE_ROW records")
    if len(suites) != 32:
        raise EvidenceError(f"capture observed {len(suites)} scored suites, expected 32")
    if score_mark_count < 64:
        raise EvidenceError(
            f"capture observed only {score_mark_count} exact score boundary marks"
        )
    row_suites = {
        json.loads(line.split(ROW_PREFIX, 1)[1])["group"].rsplit("|", 1)[1]
        for line in rows
    }
    if row_suites != set(suites):
        raise EvidenceError("counter-row suites do not match exact score-mark suites")
    counter_log = out_dir / "counter.log"
    counter_log.write_text("\n".join(rows) + "\n")
    manifest = {
        "schema_version": 1,
        "runner": CAPTURE_RUNNER,
        "capture_nonce": nonce,
        "block": args.block,
        "variant": metadata["variant"],
        "opportunity_id": metadata["opportunity_id"],
        "mechanism_key": metadata["mechanism_key"],
        "profile_id": metadata["profile_id"],
        "stories": "all",
        "score_suites": suites,
        "exit_code": completed.returncode,
        "started_at": started,
        "finished_at": finished,
        "started_monotonic_raw_ns": started_ns,
        "finished_monotonic_raw_ns": finished_ns,
        "capture_environment": host,
        "harness": harness_identity(root),
        "skill_tree_sha256": build["skill_tree_sha256"],
        "command": command,
        "build": build,
        "counter_log": artifact_ref(counter_log),
        "browser_logs": [artifact_ref(path) for path in browser_logs],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def cmd_ingest(args: argparse.Namespace) -> None:
    metadata = read_json(args.metadata)
    forbidden = {
        "blocks", "counter_logs", "capture_manifests", "ingested_by"
    }.intersection(metadata)
    if forbidden:
        raise EvidenceError(
            "metadata must not contain reducer-owned fields: "
            + ", ".join(sorted(forbidden))
        )
    capture_refs = [artifact_ref(path) for path in args.capture_manifest]
    manifests = [
        validate_capture_manifest(ref, metadata, index)
        for index, ref in enumerate(capture_refs, 1)
    ]
    log_refs = [manifest["counter_log"] for manifest in manifests]
    nonce_by_log = {
        str(pathlib.Path(manifest["counter_log"]["path"]).resolve()):
            manifest["capture_nonce"]
        for manifest in manifests
    }
    suites_by_log = {
        str(pathlib.Path(manifest["counter_log"]["path"]).resolve()):
            set(manifest["score_suites"])
        for manifest in manifests
    }
    raw = {
        **metadata,
        "minimum_running_ratio": args.minimum_running_ratio,
        "capture_manifests": capture_refs,
        "counter_logs": log_refs,
        "ingested_by": INGEST_RUNNER,
        "blocks": build_blocks_from_logs(
            log_refs,
            args.minimum_running_ratio,
            nonce_by_log=nonce_by_log,
            suites_by_log=suites_by_log,
        ),
    }
    validate_raw(raw, args.out)
    args.out.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")


def cmd_calibrate_aa(args: argparse.Namespace) -> None:
    source_ref = artifact_ref(args.manifest)
    result = reduce_instrumentation_aa(read_json(args.manifest), source_ref)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def cmd_bind_instrumentation(args: argparse.Namespace) -> None:
    root = pathlib.Path(git_value(pathlib.Path.cwd(), "rev-parse", "--show-toplevel"))
    result = reduce_instrumentation_transform(
        root, args.product_tree, artifact_ref(args.patch)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def cmd_summarize(args: argparse.Namespace) -> None:
    data = read_json(args.raw)
    blocks = validate_raw(data, args.raw)
    if data["variant"] != "baseline":
        raise EvidenceError("summarize requires a variant=baseline artifact")
    applicability = [row["applicable_calls"] / row["calls"] for row in blocks]
    shares = [row["score_weighted_exclusive_share"] * 100 for row in blocks]
    avoidable_shares = [
        row["score_weighted_avoidable_share"] * 100
        for row in blocks
    ]
    share, share_low, share_high = mean_ci95(shares)
    avoidable, avoidable_low, avoidable_high = mean_ci95(avoidable_shares)
    result = {
        **base_output(data, [args.raw]),
        "phase": "sizing",
        "variant": data["variant"],
        "n_blocks": len(blocks),
        "suite_groups_per_block": [len(row["groups"]) for row in blocks],
        "calls": int(sum(row["calls"] for row in blocks)),
        "applicable_calls": int(sum(row["applicable_calls"] for row in blocks)),
        "applicability_fraction": statistics.fmean(applicability),
        "baseline_exclusive_share_pct": share,
        "baseline_exclusive_share_ci95_pct": [share_low, share_high],
        "avoidable_scored_cycle_share_pct": avoidable,
        "avoidable_scored_cycle_share_ci95_pct": [avoidable_low, avoidable_high],
        "ceiling_pct": max(0.0, avoidable_high),
        "min_avoidable_pct_floor": getattr(args, "min_avoidable_pct", 0.0),
        "gate_pass": data["variant"] == "baseline" and avoidable_low >= getattr(args, "min_avoidable_pct", 0.0) and avoidable_low > 0,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def cmd_compare(args: argparse.Namespace) -> None:
    baseline = read_json(args.baseline)
    variant = read_json(args.variant)
    base_blocks = validate_raw(baseline, args.baseline)
    variant_blocks = validate_raw(variant, args.variant)
    if baseline["variant"] != "baseline":
        raise EvidenceError("--baseline artifact must have variant=baseline")
    expected = "oracle" if args.kind == "oracle" else "candidate"
    if variant["variant"] != expected:
        raise EvidenceError(f"--variant artifact must have variant={expected}")
    common_identity(baseline, variant)
    if baseline["build"]["product_tree"] == variant["build"]["product_tree"]:
        raise EvidenceError("baseline and variant are bound to the same product tree")
    reductions = []
    saved_shares = []
    total_change_logs = []
    for base, changed in paired_rows(base_blocks, variant_blocks):
        if base["groups"] != changed["groups"]:
            raise EvidenceError(
                f"baseline and variant block {base['block']} have different suite groups"
            )
        group_saved_shares = []
        group_base_shares = []
        group_total_change_logs = []
        for group_name in base["groups"]:
            base_group = base["group_values"][group_name]
            changed_group = changed["group_values"][group_name]
            base_total = base_group["total_scored_cycles"]
            changed_total = changed_group["total_scored_cycles"]
            group_saved_shares.append(
                (base_group["exclusive_cycles"] - changed_group["exclusive_cycles"])
                / base_total
            )
            group_base_shares.append(base_group["exclusive_cycles"] / base_total)
            group_total_change_logs.append(math.log(changed_total / base_total))
        base_ratio = statistics.fmean(group_base_shares)
        saved_ratio = statistics.fmean(group_saved_shares)
        if base_ratio <= 0:
            raise EvidenceError("baseline has no score-weighted mechanism cycles")
        reductions.append(saved_ratio / base_ratio * 100)
        saved_shares.append(saved_ratio * 100)
        total_change_logs.append(statistics.fmean(group_total_change_logs))
    reduction, reduction_low, reduction_high = mean_ci95(reductions)
    saved, saved_low, saved_high = mean_ci95(saved_shares)
    total_change, total_change_low, total_change_high = mean_log_ci_pct(
        total_change_logs
    )
    if len(set(round(value, 15) for value in reductions)) < 2:
        raise EvidenceError("paired reduction has zero block-to-block variance")
    if len(set(round(value, 15) for value in saved_shares)) < 2:
        raise EvidenceError("paired saved share has zero block-to-block variance")
    phase = "oracle" if args.kind == "oracle" else "candidate"
    result = {
        **base_output(variant, [args.baseline, args.variant]),
        "phase": phase,
        "baseline_build": baseline["build"],
        "n_paired_blocks": len(reductions),
        "suite_groups_per_block": [len(row["groups"]) for row in base_blocks],
        "exclusive_cycle_reduction_pct": reduction,
        "exclusive_cycle_reduction_ci95_pct": [reduction_low, reduction_high],
        "net_scored_cycle_share_saved_pct": saved,
        "net_scored_cycle_share_saved_ci95_pct": [saved_low, saved_high],
        "total_scored_cycle_change_pct": total_change,
        "total_scored_cycle_change_ci95_pct": [
            total_change_low, total_change_high
        ],
        "moved_work_warning": total_change_low > 0,
        "ceiling_pct": max(0.0, saved_high) if phase == "oracle" else None,
        "gate_pass": reduction_low > 0 and saved_low > 0,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest="command", required=True)
    scaffold = commands.add_parser("scaffold", help="write a raw counter template")
    scaffold.add_argument("--opp", type=int, required=True)
    scaffold.add_argument("--mechanism-key", required=True)
    scaffold.add_argument("--profile-id", required=True)
    scaffold.add_argument("--variant", choices=("baseline", "oracle", "candidate"), required=True)
    scaffold.add_argument("--out", type=pathlib.Path, required=True)
    scaffold.set_defaults(func=cmd_scaffold)
    capture = commands.add_parser(
        "capture", help="run one full-suite instrumented block and bind its output"
    )
    capture.add_argument("--metadata", type=pathlib.Path, required=True)
    capture.add_argument("--variant", choices=("baseline", "oracle", "candidate"), required=True)
    capture.add_argument("--browser", required=True)
    capture.add_argument("--block", type=int, required=True)
    capture.add_argument("--enable-features", default="")
    capture.add_argument("--out-dir", type=pathlib.Path, required=True)
    capture.add_argument("--out", type=pathlib.Path, required=True)
    capture.set_defaults(func=cmd_capture)
    ingest = commands.add_parser(
        "ingest", help="reduce runner-owned capture manifests into bound raw JSON"
    )
    ingest.add_argument("--metadata", type=pathlib.Path, required=True)
    ingest.add_argument(
        "--capture-manifest", type=pathlib.Path, action="append", required=True
    )
    ingest.add_argument("--minimum-running-ratio", type=float, default=0.99)
    ingest.add_argument("--out", type=pathlib.Path, required=True)
    ingest.set_defaults(func=cmd_ingest)
    calibrate = commands.add_parser(
        "calibrate-aa",
        help="reduce uninstrumented-vs-instrumented ab2 output into overhead evidence",
    )
    calibrate.add_argument("--manifest", type=pathlib.Path, required=True)
    calibrate.add_argument("--out", type=pathlib.Path, required=True)
    calibrate.set_defaults(func=cmd_calibrate_aa)
    bind = commands.add_parser(
        "bind-instrumentation",
        help="prove a probe patch maps a product tree to an instrumented tree",
    )
    bind.add_argument("--product-tree", required=True)
    bind.add_argument("--patch", type=pathlib.Path, required=True)
    bind.add_argument("--out", type=pathlib.Path, required=True)
    bind.set_defaults(func=cmd_bind_instrumentation)
    provenance = commands.add_parser(
        "provenance", help="measure instrumented build/tree provenance",
    )
    provenance.add_argument("--browser", type=pathlib.Path, required=True)
    provenance.add_argument("--product-tree", required=True)
    provenance.add_argument("--transform-artifact", type=pathlib.Path, required=True)
    provenance.add_argument("--out", type=pathlib.Path, required=True)
    provenance.set_defaults(func=cmd_provenance)
    attach = commands.add_parser(
        "attach-provenance", help="attach runner-owned build provenance to metadata",
    )
    attach.add_argument("--metadata", type=pathlib.Path, required=True)
    attach.add_argument("--provenance", type=pathlib.Path, required=True)
    attach.add_argument("--out", type=pathlib.Path, required=True)
    attach.set_defaults(func=cmd_attach_provenance)
    summarize = commands.add_parser("summarize", help="validate baseline counter evidence")
    summarize.add_argument("--raw", type=pathlib.Path, required=True)
    summarize.add_argument("--min-avoidable-pct", type=float, default=0.0)
    summarize.add_argument("--out", type=pathlib.Path, required=True)
    summarize.set_defaults(func=cmd_summarize)
    compare = commands.add_parser("compare", help="validate paired oracle/candidate evidence")
    compare.add_argument("--baseline", type=pathlib.Path, required=True)
    compare.add_argument("--variant", type=pathlib.Path, required=True)
    compare.add_argument("--kind", choices=("oracle", "candidate"), required=True)
    compare.add_argument("--out", type=pathlib.Path, required=True)
    compare.set_defaults(func=cmd_compare)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except EvidenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
