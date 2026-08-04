#!/usr/bin/env python3
"""Materialize one work unit's scoped code packet from the pinned worktree.

Reads the machine-readable scope spec the planner wrote next to the brief
(`packets/<WORK>.spec.tsv`) and emits `packets/<WORK>-code.md`: the exact
scoped diff (optionally filtered to the spec's old/new line ranges for
dense-file shards) plus line-numbered changed-side slices. The orchestrator
runs this before sealing the work unit, so the packet is an existing,
hashable `assigned` input — scoped code becomes measured input instead of
every worker re-deriving the same diff from the worktree.

The packet is a starting point, never a boundary: workers may open any
worktree file whenever their procedure needs more context. A spec row that
matches nothing is a spec bug and fails closed.

Spec columns (TSV with header): kind, path, old_range, new_range, note.
- kind `diff`: unified diff of `path` between the pinned parent and revision.
  Ranges of `-` take every hunk; otherwise a hunk is kept when it intersects
  any old-side interval (old_range) or new-side interval (new_range), both
  comma-separated inclusive `start-end` lists.
- kind `slice`: revision-side lines `new_range` of `path` from the worktree,
  emitted with line numbers for citation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def fail(message: str) -> None:
    print(f"build-scope-packets.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_ranges(cell: str, spec: Path, line: int) -> list[tuple[int, int]]:
    cell = cell.strip()
    if cell in {"", "-"}:
        return []
    ranges = []
    for part in cell.split(","):
        match = re.fullmatch(r"\s*(\d+)-(\d+)\s*", part)
        if not match:
            fail(f"{spec}:{line}: bad range '{part.strip()}'")
        start, end = int(match.group(1)), int(match.group(2))
        if start < 1 or end < start:
            fail(f"{spec}:{line}: bad range '{part.strip()}'")
        ranges.append((start, end))
    return ranges


def intersects(start: int, count: int, ranges: list[tuple[int, int]]) -> bool:
    end = start + max(count, 1) - 1
    return any(start <= high and end >= low for low, high in ranges)


def filter_hunks(diff: str, old_ranges, new_ranges) -> str:
    if not old_ranges and not new_ranges:
        return diff
    lines = diff.splitlines()
    header: list[str] = []
    body_start = next(
        (i for i, line in enumerate(lines) if HUNK.match(line)), len(lines))
    header = lines[:body_start]
    kept: list[str] = []
    keep = False
    for line in lines[body_start:]:
        match = HUNK.match(line)
        if match:
            old_start, old_count = int(match.group(1)), int(match.group(2) or 1)
            new_start, new_count = int(match.group(3)), int(match.group(4) or 1)
            keep = (intersects(old_start, old_count, old_ranges)
                    or intersects(new_start, new_count, new_ranges))
        if keep:
            kept.append(line)
    if not kept:
        return ""
    return "\n".join(header + kept)


def fence(payload: str, info: str = "") -> list[str]:
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", payload)),
                  default=0)
    marker = "`" * max(3, longest + 1)
    return [marker + info, payload, marker]


def read_spec(spec: Path) -> list[dict[str, str]]:
    if not spec.is_file():
        fail(f"missing scope spec: {spec}")
    lines = spec.read_text(encoding="utf-8").splitlines()
    if not lines:
        fail(f"empty scope spec: {spec}")
    header = [cell.strip() for cell in lines[0].split("\t")]
    required = {"kind", "path", "old_range", "new_range", "note"}
    if not required.issubset(header):
        fail(f"{spec}: header must contain {sorted(required)}")
    rows = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) != len(header):
            fail(f"{spec}:{number}: expected {len(header)} columns")
        row = dict(zip(header, cells))
        row["_line"] = str(number)
        rows.append(row)
    if not rows:
        fail(f"{spec}: no data rows")
    return rows


def check_path(path: str, spec: Path, line: str) -> None:
    if path.startswith(("/", "~")) or ".." in Path(path).parts or not path:
        fail(f"{spec}:{line}: path must be repo-relative without '..': "
             f"'{path}'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("work_id")
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    review_dir = arguments.review_dir.resolve()
    worktree = arguments.worktree.resolve()
    if not (worktree / ".git").exists():
        fail(f"not a git worktree: {worktree}")
    packets = review_dir / "packets"
    packets.mkdir(parents=True, exist_ok=True)
    spec = (arguments.spec or packets / f"{arguments.work_id}.spec.tsv")
    output_path = (arguments.output
                   or packets / f"{arguments.work_id}-code.md")

    head = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False)
    if head.returncode != 0 or head.stdout.strip() != arguments.revision:
        fail(f"worktree HEAD {head.stdout.strip() or '?'} does not match "
             f"pinned revision {arguments.revision}")

    output = [
        f"# Code packet — {arguments.work_id} — revision "
        f"{arguments.revision} (parent {arguments.parent})",
        "",
        "Generated by build-scope-packets.py from the pinned worktree. This",
        "is your exact scoped diff and changed-side slices: read it before",
        "opening worktree files, cite the repo-relative `path:line` numbers",
        "shown here, and open any worktree file whenever your procedure",
        "needs more context — the packet prevents re-deriving your scope,",
        "it never bounds your tracing.",
    ]
    for row in read_spec(spec):
        kind, path, line = row["kind"], row["path"], row["_line"]
        check_path(path, spec, line)
        note = row.get("note", "")
        old_ranges = parse_ranges(row["old_range"], spec, int(line))
        new_ranges = parse_ranges(row["new_range"], spec, int(line))
        if kind == "diff":
            result = subprocess.run(
                ["git", "-C", str(worktree), "diff",
                 arguments.parent, arguments.revision, "--", path],
                capture_output=True, text=True, check=False)
            if result.returncode != 0:
                fail(f"{spec}:{line}: git diff failed for {path}: "
                     f"{result.stderr.strip()}")
            diff = filter_hunks(result.stdout, old_ranges, new_ranges)
            if not diff.strip():
                fail(f"{spec}:{line}: no hunks for {path} in the requested "
                     "ranges — fix the spec, do not guess scope")
            scope_note = ""
            if old_ranges or new_ranges:
                scope_note = (f" (hunks intersecting old {row['old_range']} "
                              f"/ new {row['new_range']})")
            output += ["", f"## Diff: {path}{scope_note}"
                       + (f" — {note}" if note and note != "-" else "")]
            output += fence(diff.rstrip("\n"), "diff")
        elif kind == "slice":
            if not new_ranges:
                fail(f"{spec}:{line}: slice rows require new_range")
            target = worktree / path
            if not target.is_file():
                fail(f"{spec}:{line}: no such worktree file: {path}")
            file_lines = target.read_text(
                encoding="utf-8", errors="replace").splitlines()
            for start, end in new_ranges:
                if start > len(file_lines):
                    fail(f"{spec}:{line}: slice {start}-{end} starts past "
                         f"end of {path} ({len(file_lines)} lines)")
                clamped = min(end, len(file_lines))
                numbered = "\n".join(
                    f"{number:6d}\t{text}" for number, text in enumerate(
                        file_lines[start - 1:clamped], start=start))
                suffix = "" if clamped == end else \
                    f" (clamped to EOF at {clamped})"
                output += ["", f"## Slice: {path} lines {start}-{end}"
                           f"{suffix} (revision side)"
                           + (f" — {note}" if note and note != "-" else "")]
                output += fence(numbered)
        else:
            fail(f"{spec}:{line}: unknown kind '{kind}'")

    payload = "\n".join(output) + "\n"
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(output_path)
    print(f"{output_path} ({len(payload.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
