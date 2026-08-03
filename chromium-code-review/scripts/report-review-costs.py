#!/usr/bin/env python3
"""Derive a per-phase / per-work-unit cost report for a review directory.

Reads only artifacts the review already produces — `orchestration.tsv`
(attempts, states, tiers) and `input-manifest.tsv` (exact preassigned input
bytes per attempt) — plus the on-disk sizes of each attempt's artifact. It
writes `cost-report.tsv` (every work unit, no caps) and a compact
`cost-report.md` summary, and never modifies any review artifact.

The numbers are honest proxies, not billing data: input bytes cover manifested
preassigned inputs; opt-in code-read logs cover emitted bytes from wrapped
worktree/tool commands; and artifact sizes are not model output tokens.
Unwrapped worktree/tool reads remain invisible. The proxies are comparable
across phases and runs of this skill, which is what optimization needs. Token
estimates use the same conservative four-bytes-per-token rule as the input-
budget contract.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sys

TOKEN_BYTES = 4
TIMESTAMPED = re.compile(r"^- (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) (.+)$")
# The normative event grammar appended by scripts/log-progress.py. Work IDs
# are opaque single tokens; the attempt number keeps retries distinct.
SPAWNED = re.compile(r"^spawned (\S+) attempt (\d+)\b")
COLLECTED = re.compile(r"^collected (\S+) attempt (\d+)\b")
PHASE_LINE = re.compile(r"^Phase (\S+) ")


def parse_timeline(progress: Path):
    """Wall-clock evidence from timestamped progress.md lines.

    Returns (phase_rows, thread_rows, total_seconds) where phase_rows are
    (label, elapsed_seconds_since_previous_marker) and thread_rows are
    ("WORK#attempt", spawn_to_collect_seconds). Only the log-progress.py
    event grammar is recognized; lines without timestamps or in other shapes
    contribute nothing — old reviews still report byte costs.
    """
    events = []
    for line in progress.read_text(encoding="utf-8").splitlines():
        match = TIMESTAMPED.match(line.strip())
        if not match:
            continue
        try:
            stamp = datetime.strptime(
                match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
        except ValueError:
            continue
        events.append((stamp, match.group(2)))
    if not events:
        return [], [], None
    phase_rows = []
    previous = events[0][0]
    spawn_times: dict[tuple[str, str], datetime] = {}
    thread_rows = []
    for stamp, text in events:
        phase = PHASE_LINE.match(text)
        if phase:
            phase_rows.append(
                (text.split(":", 1)[0], (stamp - previous).total_seconds()))
            previous = stamp
        spawned = SPAWNED.match(text)
        if spawned:
            spawn_times.setdefault(
                (spawned.group(1), spawned.group(2)), stamp)
        collected = COLLECTED.match(text)
        if collected:
            key = (collected.group(1), collected.group(2))
            if key in spawn_times:
                thread_rows.append((
                    f"{key[0]}#{key[1]}",
                    (stamp - spawn_times[key]).total_seconds()))
    total = (events[-1][0] - events[0][0]).total_seconds()
    return phase_rows, thread_rows, total


def duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{secs:02d}s"


def fail(message: str) -> None:
    print(f"report-review-costs.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_tsv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    rows = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        values = line.split("\t")
        if len(values) != len(header):
            fail(f"{path}:{number}: expected {len(header)} columns, "
                 f"got {len(values)}")
        rows.append(dict(zip(header, values)))
    return rows


def tokens(byte_count: int) -> str:
    return f"~{byte_count // TOKEN_BYTES:,}"


def code_read_costs(review_dir: Path):
    """Return aggregate instrumented command costs and malformed-log count."""
    totals: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int))
    malformed = 0
    root = review_dir / "instrumentation" / "code-reads"
    if not root.is_dir():
        return totals, malformed
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
                if event.get("schema") != "code-reads-v1":
                    raise ValueError("wrong schema")
                key = (str(event["work_id"]), str(event["attempt"]))
                totals[key]["commands"] += 1
                totals[key]["stdout_bytes"] += int(event["stdout_bytes"])
                totals[key]["stderr_bytes"] += int(event["stderr_bytes"])
                totals[key]["elapsed_ms"] += int(event["elapsed_ms"])
                if int(event["exit_code"]) != 0:
                    totals[key]["failed_commands"] += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                malformed += 1
    return totals, malformed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    arguments = parser.parse_args()
    review_dir = arguments.review_dir.resolve()
    orchestration_path = review_dir / "orchestration.tsv"
    if not orchestration_path.is_file():
        fail(f"missing {orchestration_path}")
    attempts = read_tsv(orchestration_path)
    manifest_path = review_dir / "input-manifest.tsv"
    manifest = read_tsv(manifest_path) if manifest_path.is_file() else []

    # Manifested input bytes per (work_id, attempt): unique paths count once,
    # matching the budget rule that multi-role paths count once per worker.
    input_bytes: dict[tuple[str, str], int] = defaultdict(int)
    counted_paths: set[tuple[tuple[str, str], str]] = set()
    for row in manifest:
        key = (row.get("work_id", ""), row.get("attempt", ""))
        path = row.get("input_path", "")
        if (key, path) in counted_paths:
            continue
        counted_paths.add((key, path))
        try:
            input_bytes[key] += int(row.get("bytes", "0") or 0)
        except ValueError:
            fail(f"{manifest_path}: non-numeric bytes for {path}")

    units = []
    artifact_seen: set[str] = set()
    for row in attempts:
        key = (row.get("work_id", ""), row.get("attempt", ""))
        artifact = row.get("artifact", "")
        artifact_bytes = 0
        if artifact and artifact not in {"-", ""} \
                and artifact not in artifact_seen:
            artifact_seen.add(artifact)
            candidate = Path(artifact)
            if not candidate.is_absolute():
                candidate = review_dir / artifact
            if candidate.is_file():
                artifact_bytes = candidate.stat().st_size
        units.append({
            "phase": row.get("phase", "?"),
            "work_id": key[0],
            "attempt": key[1],
            "state": row.get("state", "?"),
            "tier": row.get("tier", "?"),
            "input_bytes": input_bytes.get(key, 0),
            "artifact_bytes": artifact_bytes,
        })

    tsv_path = review_dir / "cost-report.tsv"
    header = ["phase", "work_id", "attempt", "state", "tier",
              "input_bytes", "artifact_bytes"]
    tsv_lines = ["\t".join(header)]
    tsv_lines += [
        "\t".join(str(unit[column]) for column in header) for unit in units
    ]
    tsv_path.write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")

    per_phase: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int))
    tier_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int))
    for unit in units:
        phase = per_phase[str(unit["phase"])]
        phase["attempts"] += 1
        phase["input_bytes"] += int(unit["input_bytes"])
        phase["artifact_bytes"] += int(unit["artifact_bytes"])
        if str(unit["attempt"]) not in ("", "1"):
            phase["retry_attempts"] += 1
        tier = tier_totals[str(unit["tier"])]
        tier["attempts"] += 1
        tier["input_bytes"] += int(unit["input_bytes"])

    total_input = sum(unit["input_bytes"] for unit in units)
    total_output = sum(unit["artifact_bytes"] for unit in units)
    largest = sorted(units, key=lambda unit: -int(unit["input_bytes"]))[:15]
    read_costs, malformed_read_events = code_read_costs(review_dir)
    if read_costs or malformed_read_events:
        read_tsv_path = review_dir / "code-read-costs.tsv"
        read_tsv_lines = [
            "work_id\tattempt\tcommands\tfailed_commands\tstdout_bytes\t"
            "stderr_bytes\telapsed_ms"
        ]
        read_tsv_lines += [
            f"{key[0]}\t{key[1]}\t{stats['commands']}\t"
            f"{stats['failed_commands']}\t{stats['stdout_bytes']}\t"
            f"{stats['stderr_bytes']}\t{stats['elapsed_ms']}"
            for key, stats in sorted(read_costs.items())
        ]
        read_tsv_path.write_text("\n".join(read_tsv_lines) + "\n",
                                 encoding="utf-8")

    def phase_sort(key: str):
        try:
            return (0, float(key))
        except ValueError:
            return (1, key)

    md = [
        "# Review cost report",
        "",
        f"- Attempts: {len(units)} "
        f"({sum(1 for u in units if str(u['attempt']) not in ('', '1'))} "
        "retries/continuations)",
        f"- Manifested input bytes: {total_input:,} "
        f"({tokens(total_input)} tokens at {TOKEN_BYTES} B/token)",
        f"- Artifact output bytes: {total_output:,} "
        f"({tokens(total_output)} tokens)",
        "- Input covers preassigned manifest rows only; worktree/tool reads",
        "  during reasoning are not manifested. Output is artifact size, not",
        "  model output tokens. Full per-unit data: cost-report.tsv.",
        "",
        "## Per phase",
        "",
        "| phase | attempts | retries | input bytes | artifact bytes |",
        "| --- | --- | --- | --- | --- |",
    ]
    md += [
        f"| {phase} | {stats['attempts']} | {stats['retry_attempts']} "
        f"| {stats['input_bytes']:,} | {stats['artifact_bytes']:,} |"
        for phase, stats in sorted(per_phase.items(),
                                   key=lambda item: phase_sort(item[0]))
    ]
    md += [
        "",
        "## Per resolved tier",
        "",
        "| tier | attempts | input bytes |",
        "| --- | --- | --- |",
    ]
    md += [
        f"| {tier} | {stats['attempts']} | {stats['input_bytes']:,} |"
        for tier, stats in sorted(tier_totals.items())
    ]
    if read_costs or malformed_read_events:
        total_commands = sum(value["commands"] for value in read_costs.values())
        total_stdout = sum(value["stdout_bytes"] for value in read_costs.values())
        total_stderr = sum(value["stderr_bytes"] for value in read_costs.values())
        total_elapsed = sum(value["elapsed_ms"] for value in read_costs.values())
        largest_reads = sorted(
            read_costs.items(), key=lambda item: -item[1]["stdout_bytes"])
        md += [
            "",
            "## Instrumented code/tool reads",
            "",
            f"- Commands: {total_commands:,}",
            f"- Captured stdout bytes: {total_stdout:,} "
            f"({tokens(total_stdout)} token proxy)",
            f"- Captured stderr bytes: {total_stderr:,}",
            f"- Aggregate command elapsed: {duration(total_elapsed / 1000)}",
            f"- Malformed log events: {malformed_read_events}",
            "- These are emitted-byte proxies, not provider token counts;",
            "  repeated reads are intentionally counted repeatedly.",
            "",
            "### Largest 30 work attempts by captured stdout",
            "",
            "The uncapped per-attempt data is in `code-read-costs.tsv`.",
            "",
            "| work attempt | commands | failed | stdout bytes | elapsed |",
            "| --- | --- | --- | --- | --- |",
        ]
        md += [
            f"| {key[0]}#{key[1]} | {stats['commands']} "
            f"| {stats['failed_commands']} | {stats['stdout_bytes']:,} "
            f"| {duration(stats['elapsed_ms'] / 1000)} |"
            for key, stats in largest_reads[:30]
        ]
    progress_path = review_dir / "progress.md"
    if progress_path.is_file():
        phase_rows, thread_rows, total_seconds = parse_timeline(progress_path)
        if total_seconds is not None:
            md += [
                "",
                "## Wall clock (from timestamped progress.md lines)",
                "",
                f"- Total span: {duration(total_seconds)}",
                "- Phase elapsed is measured from the previous phase marker;",
                "  thread latency is spawn-to-collect and includes any wave",
                "  queueing after spawn was logged.",
                "",
                "| phase marker | elapsed |",
                "| --- | --- |",
            ]
            md += [f"| {label} | {duration(elapsed)} |"
                   for label, elapsed in phase_rows]
            if thread_rows:
                slowest = sorted(thread_rows, key=lambda row: -row[1])[:15]
                md += [
                    "",
                    "| thread | spawn → collect |",
                    "| --- | --- |",
                ]
                md += [f"| {work_id} | {duration(elapsed)} |"
                       for work_id, elapsed in slowest]

    md += [
        "",
        "## Largest work units by manifested input",
        "",
        "| phase | work unit | attempt | tier | input bytes | artifact bytes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    md += [
        f"| {unit['phase']} | {unit['work_id']} | {unit['attempt']} "
        f"| {unit['tier']} | {unit['input_bytes']:,} "
        f"| {unit['artifact_bytes']:,} |"
        for unit in largest
    ]
    md_path = review_dir / "cost-report.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {md_path} and {tsv_path}: {len(units)} attempts, "
          f"{total_input:,} input bytes, {total_output:,} artifact bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
