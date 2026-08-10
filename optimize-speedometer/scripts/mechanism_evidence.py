#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Create and validate mechanistic optimization evidence.

This intentionally accepts a small, rigid schema.  Campaign agents fill raw
counter files; this program performs the arithmetic and emits the only
artifacts accepted by campaign.py's sizing and candidate-verification gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import statistics
import sys


SCHEMA_VERSION = 1
ROW_PREFIX = "[SP3_CYCLE_ROW] "
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
    "build_id",
    "gn_args_sha256",
    "toolchain_id",
    "pgo_profile_sha256",
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


def build_blocks_from_logs(log_refs: list[dict], minimum_running_ratio: float) -> list[dict]:
    finite(minimum_running_ratio, "minimum_running_ratio", positive=True)
    if minimum_running_ratio > 1:
        raise EvidenceError("minimum_running_ratio cannot exceed 1")
    rows = {}
    for index, ref in enumerate(log_refs, 1):
        validate_artifact_ref(ref, f"counter_logs[{index}]")
        path = pathlib.Path(ref["path"])
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
            block = row.get("block")
            group = row.get("group")
            if isinstance(block, bool) or not isinstance(block, int) or block < 1:
                raise EvidenceError(f"{path}:{line_number}: invalid block id")
            if not isinstance(group, str) or "|" not in group:
                raise EvidenceError(f"{path}:{line_number}: group must be repetition|suite")
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
    validate_artifact_ref(scope.get("trace_artifact"), f"{path}: trace_artifact")
    build = data.get("build")
    if not isinstance(build, dict):
        raise EvidenceError(f"{path}: missing build provenance")
    for field in REQUIRED_BUILD_FIELDS:
        if not isinstance(build.get(field), str) or not build[field].strip():
            raise EvidenceError(f"{path}: build.{field} is required")
    validate_artifact_ref(
        build.get("provenance_artifact"), f"{path}: build.provenance_artifact"
    )
    instrumentation = data.get("instrumentation")
    if not isinstance(instrumentation, dict) or not instrumentation.get("revision"):
        raise EvidenceError(f"{path}: instrumentation.revision is required")
    finite(
        instrumentation.get("aa_overhead_pct"),
        f"{path}: instrumentation.aa_overhead_pct",
    )
    if instrumentation["aa_overhead_pct"] > 1.0:
        raise EvidenceError(f"{path}: instrumentation A/A overhead exceeds 1%")
    validate_artifact_ref(
        instrumentation.get("aa_artifact"),
        f"{path}: instrumentation.aa_artifact",
    )
    log_refs = data.get("counter_logs")
    if not isinstance(log_refs, list) or not log_refs:
        raise EvidenceError(f"{path}: counter_logs must bind at least one emitted log")
    minimum_running_ratio = finite(
        data.get("minimum_running_ratio"),
        f"{path}: minimum_running_ratio",
        positive=True,
    )
    if minimum_running_ratio > 1:
        raise EvidenceError(f"{path}: minimum_running_ratio cannot exceed 1")
    if data.get("ingested_by") != "mechanism_evidence.py/v1":
        raise EvidenceError(
            f"{path}: raw evidence must be created by mechanism_evidence.py ingest"
        )
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or len(blocks) < 3:
        raise EvidenceError(f"{path}: at least 3 independent blocks are required")
    reconstructed = build_blocks_from_logs(log_refs, minimum_running_ratio)
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
    return normalized


def common_identity(left: dict, right: dict) -> None:
    for field in ("opportunity_id", "mechanism_key", "profile_id", "interval_kind"):
        if left.get(field) != right.get(field):
            raise EvidenceError(f"raw artifacts disagree on {field}")
    if left.get("score_scope") != right.get("score_scope"):
        raise EvidenceError("raw artifacts disagree on score_scope")
    if left.get("instrumentation") != right.get("instrumentation"):
        raise EvidenceError("raw artifacts use different instrumentation")
    for field in ("gn_args_sha256", "toolchain_id", "pgo_profile_sha256"):
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


def cmd_ingest(args: argparse.Namespace) -> None:
    metadata = read_json(args.metadata)
    forbidden = {"blocks", "counter_logs", "ingested_by"}.intersection(metadata)
    if forbidden:
        raise EvidenceError(
            "metadata must not contain reducer-owned fields: "
            + ", ".join(sorted(forbidden))
        )
    log_refs = [artifact_ref(path) for path in args.log]
    raw = {
        **metadata,
        "minimum_running_ratio": args.minimum_running_ratio,
        "counter_logs": log_refs,
        "ingested_by": "mechanism_evidence.py/v1",
        "blocks": build_blocks_from_logs(log_refs, args.minimum_running_ratio),
    }
    validate_raw(raw, args.out)
    args.out.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")


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
        "gate_pass": data["variant"] == "baseline" and avoidable_low > 0,
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
    ingest = commands.add_parser(
        "ingest", help="reduce machine-emitted counter logs into bound raw JSON"
    )
    ingest.add_argument("--metadata", type=pathlib.Path, required=True)
    ingest.add_argument("--log", type=pathlib.Path, action="append", required=True)
    ingest.add_argument("--minimum-running-ratio", type=float, default=0.99)
    ingest.add_argument("--out", type=pathlib.Path, required=True)
    ingest.set_defaults(func=cmd_ingest)
    summarize = commands.add_parser("summarize", help="validate baseline counter evidence")
    summarize.add_argument("--raw", type=pathlib.Path, required=True)
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
