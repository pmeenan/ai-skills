#!/usr/bin/env python3
"""Mechanically collect a synthesis-challenge round.

Replaces the mechanical-tier Challenge Collector agent for the normal path:
it verifies every planned shard artifact exists, extracts issue IDs and
statuses from the immutable shard files, fills the round index's `issues`
column, appends the round result, and writes the compact `challenge.md`
pointer. It makes no review judgment — a missing shard or malformed table is
a nonzero exit (needs-repair), never a silent pass — and it never edits a
shard artifact.

Usage: collect-challenge-round.py <review-dir> <round>

Exit 0 means the round collected mechanically (result may still be
`revision required`); nonzero means the round is structurally incomplete and
must be repaired before it can count.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

REQUIRED_COLUMNS = ["shard", "scope", "brief", "artifact",
                    "expected coverage", "issues"]
CLOSED_STATUSES = {"resolved", "fixed", "addressed", "withdrawn", "rebutted",
                   "closed", "done"}


def fail(message: str) -> None:
    print(f"collect-challenge-round.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell)


def parse_shard_issues(path: Path) -> tuple[list[str], int]:
    """Return (issue IDs, open count) from one immutable shard artifact."""
    identifiers: list[str] = []
    open_count = 0
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = split_row(line)
        if is_separator(cells):
            continue
        if header is None:
            header = [cell.lower() for cell in cells]
            continue
        row = dict(zip(header, cells))
        identifier = row.get("id", "")
        if not re.fullmatch(r"CH\d+-\d+", identifier):
            continue
        identifiers.append(identifier)
        if row.get("status", "").lower() not in CLOSED_STATUSES:
            open_count += 1
    return identifiers, open_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("round", type=int)
    arguments = parser.parse_args()
    review_dir = arguments.review_dir.resolve()
    round_dir = review_dir / "challenge" / f"round-{arguments.round}"
    index_path = round_dir / "index.md"
    if not index_path.is_file():
        fail(f"missing round index: {index_path}")
    lines = index_path.read_text(encoding="utf-8").splitlines()

    revision = next(
        (match.group(1) for line in lines
         if (match := re.match(r"- Draft revision:\s*(\d+)\s*$", line))),
        None)
    if not revision:
        fail(f"{index_path} lacks '- Draft revision: <n>'")

    problems: list[str] = []
    total_issues = 0
    total_open = 0
    shard_count = 0
    header: list[str] | None = None
    output: list[str] = []
    for line in lines:
        if re.match(r"- (Result|Total open issues):", line):
            continue  # Replaced by this collection pass.
        if not line.lstrip().startswith("|"):
            header = None
            output.append(line)
            continue
        cells = split_row(line)
        if is_separator(cells):
            output.append(line)
            continue
        if header is None:
            header = [cell.lower() for cell in cells]
            if not set(REQUIRED_COLUMNS).issubset(header):
                header = ["-skip-"]
            output.append(line)
            continue
        if header == ["-skip-"]:
            output.append(line)
            continue
        row = dict(zip(header, cells))
        shard = row.get("shard", "")
        shard_count += 1
        if not re.fullmatch(r"CH\d+", shard):
            problems.append(f"invalid shard id '{shard}'")
            output.append(line)
            continue
        artifact = row.get("artifact", "")
        artifact_path = review_dir / artifact
        if not artifact or not artifact_path.is_file() \
                or artifact_path.stat().st_size == 0:
            problems.append(f"shard {shard}: missing/empty artifact {artifact}")
            output.append(line)
            continue
        shard_text = artifact_path.read_text(encoding="utf-8")
        recorded = re.search(r"draft revision\s+(\d+)", shard_text, re.I)
        if recorded and recorded.group(1) != revision:
            problems.append(
                f"shard {shard}: audited draft revision {recorded.group(1)}, "
                f"round expects {revision}")
        identifiers, open_count = parse_shard_issues(artifact_path)
        total_issues += len(identifiers)
        total_open += open_count
        row["issues"] = ", ".join(identifiers) if identifiers else "none"
        output.append("| " + " | ".join(
            row.get(column, "") for column in header) + " |")

    if shard_count == 0:
        problems.append("round index has no shard table rows")

    if problems:
        result = "incomplete — " + "; ".join(problems)
    elif total_issues:
        result = "revision required"
    else:
        result = "pass"
    while output and not output[-1].strip():
        output.pop()
    output += ["", f"- Result: {result}",
               f"- Total open issues: {total_open}"]
    temporary = index_path.with_name(index_path.name + ".tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    temporary.replace(index_path)

    index_relative = index_path.relative_to(review_dir).as_posix()
    pointer = [
        f"# Challenge index — round {arguments.round} / draft revision "
        f"{revision}",
        "",
        f"- Draft revision: {revision}",
        f"- Index: {index_relative}",
        f"- Total open issues: {total_open}",
        f"- Result: {result}",
    ]
    (review_dir / "challenge.md").write_text(
        "\n".join(pointer) + "\n", encoding="utf-8")

    print(f"round {arguments.round}: {shard_count} shards, "
          f"{total_issues} issues ({total_open} open), result: {result}")
    if problems:
        for problem in problems:
            print(f"collect-challenge-round.py: ERROR: {problem}",
                  file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
