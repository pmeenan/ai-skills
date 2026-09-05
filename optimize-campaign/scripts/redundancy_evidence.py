#!/usr/bin/env python3
"""Reduce redundancy-probe rows into the evidence packet a proposal must cite.

A Layer 1 claim ("this subtree can be skipped when condition C holds") and a
Layer 2 claim ("this result is recomputed for inputs already seen") are only
as good as two measured numbers: how often the site runs per benchmark step
and how often C holds or the input repeats. `redundancy_probe.h` counts both
inside the exact scored window; this tool turns the browser log rows into a
digest-bound packet. `campaign.py decompose` binds that packet to the
proposal and refuses an estimated avoidable fraction the counts do not
support.

Usage:
  python3 redundancy_evidence.py --site style/resolve-style \\
      --target-story TodoMVC-React --browser-log <cb browser log> [...] \\
      --out <packet.json>
"""
import argparse
import hashlib
import json
import pathlib
import statistics
import sys

ROW_PREFIX = "[SP3_REDUNDANCY_ROW] "
SCHEMA_VERSION = 1


class RedundancyError(ValueError):
    pass


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_rows(path: pathlib.Path) -> list[dict]:
    rows = []
    with path.open(errors="replace") as source:
        for line in source:
            index = line.find(ROW_PREFIX)
            if index < 0:
                continue
            try:
                row = json.loads(line[index + len(ROW_PREFIX):])
            except json.JSONDecodeError as exc:
                raise RedundancyError(f"{path}: malformed redundancy row: {exc}") from exc
            if row.get("schema_version") != SCHEMA_VERSION:
                raise RedundancyError(f"{path}: unsupported redundancy row schema")
            for field in ("site", "group", "calls", "applicable_calls",
                          "distinct_inputs", "repeated_inputs", "overflow"):
                if field not in row:
                    raise RedundancyError(f"{path}: redundancy row lacks {field}")
            rows.append(row)
    return rows


def story_of(group: str) -> str:
    return group.rsplit("|", 1)[1] if "|" in group else group


def reduce_rows(rows: list[dict], site: str, target_story: str) -> dict:
    selected = [
        row for row in rows
        if row["site"] == site and story_of(row["group"]) == target_story
    ]
    if not selected:
        raise RedundancyError(
            f"no rows for site {site!r} in story {target_story!r}; the probe "
            "did not run inside that story's scored window"
        )
    violations = sum(int(row.get("thread_affinity_violations", 0)) for row in selected)
    if violations:
        raise RedundancyError("redundancy counter was touched from another thread")
    calls = [int(row["calls"]) for row in selected]
    applicable = [int(row["applicable_calls"]) for row in selected]
    distinct = [int(row["distinct_inputs"]) for row in selected]
    repeated = [int(row["repeated_inputs"]) for row in selected]
    overflow = any(int(row["overflow"]) for row in selected)
    total_calls = sum(calls)
    if total_calls == 0:
        raise RedundancyError(f"site {site!r} never ran inside {target_story!r}'s scored window")
    return {
        "site": site,
        "target_story": target_story,
        "repetitions": len(selected),
        "calls_total": total_calls,
        "calls_per_repetition_mean": statistics.fmean(calls),
        "calls_per_repetition_min": min(calls),
        "calls_per_repetition_max": max(calls),
        "applicable_fraction": sum(applicable) / total_calls,
        "repeat_fraction": sum(repeated) / total_calls,
        "distinct_inputs_mean": statistics.fmean(distinct),
        "distinct_overflow": overflow,
        "measured_avoidable_fraction_upper": (
            None if overflow else max(sum(applicable), sum(repeated)) / total_calls
        ),
        "groups": [row["group"] for row in selected],
    }


def build_packet(logs: list[pathlib.Path], site: str, target_story: str) -> dict:
    rows = []
    sources = []
    for path in logs:
        if not path.is_file():
            raise RedundancyError(f"browser log not found: {path}")
        rows.extend(parse_rows(path))
        sources.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    summary = reduce_rows(rows, site, target_story)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "redundancy-evidence",
        "sources": sources,
        "rows_total": len(rows),
        **summary,
    }


def load_packet(path: pathlib.Path) -> dict:
    try:
        packet = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RedundancyError(f"cannot read redundancy packet {path}: {exc}") from exc
    if not isinstance(packet, dict) or packet.get("kind") != "redundancy-evidence":
        raise RedundancyError(f"{path} is not a redundancy evidence packet")
    if packet.get("schema_version") != SCHEMA_VERSION:
        raise RedundancyError(f"{path}: unsupported packet schema")
    for field in ("site", "target_story", "calls_total", "applicable_fraction",
                  "repeat_fraction", "distinct_overflow", "sources"):
        if field not in packet:
            raise RedundancyError(f"{path}: packet lacks {field}")
    return packet


def supported_avoidable_fraction(packet: dict) -> float | None:
    """Largest avoidable fraction the counts can support, or None on overflow."""
    if packet.get("distinct_overflow"):
        return float(packet["applicable_fraction"])
    return max(float(packet["applicable_fraction"]), float(packet["repeat_fraction"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", required=True, help="probe site name as passed to RedundancyCounter")
    parser.add_argument("--target-story", required=True)
    parser.add_argument("--browser-log", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        packet = build_packet(args.browser_log, args.site, args.target_story)
    except RedundancyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "site": packet["site"], "target_story": packet["target_story"],
        "calls_per_repetition_mean": packet["calls_per_repetition_mean"],
        "applicable_fraction": packet["applicable_fraction"],
        "repeat_fraction": packet["repeat_fraction"],
        "distinct_overflow": packet["distinct_overflow"],
        "out": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
