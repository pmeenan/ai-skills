#!/usr/bin/env python3
"""Deterministic interdiff hunk computation and line-range mapping.

For same-reviewer Round 2+ reviews (`prior_context.reviewer_history` in
`profile.json`), `indexes/interdiff-hunks.tsv` records zero-context diff hunks
between the reviewer's latest prior reviewed patchset SHA (`prior_sha`) and the
pinned patchset SHA (`revision_sha`).

Both `profile-review.py` (automatically during Phase 1 when `prior_sha` is in
the local git object store) and Phase 2 `PF` (via the CLI after fetching a
missing `prior_sha`) use this module so Phase 5 verifiers and Phase 6
reconciliation gates have one mechanical source of truth for whether a cited
code path changed since the prior review round.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


INTERDIFF_COLUMNS = (
    "id",
    "path",
    "old_path",
    "old_start",
    "old_count",
    "new_start",
    "new_count",
    "prior_sha",
    "revision_sha",
)

FIELD_RE = re.compile(r"^- ([^:\n]+):\s*(.+?)\s*$", re.MULTILINE)
LOCATION_SPAN_RE = re.compile(
    r"(?:^|[\s`(\[,;])([A-Za-z0-9_.+@{}\-/]+):([1-9]\d*)(?:-([1-9]\d*))?(?=$|[\s`)\],;.]|:(?!\d))"
)


def fail(message: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"interdiff_hunks.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def commit_reachable(worktree: Path, sha: str) -> bool:
    if not sha or not re.fullmatch(r"[0-9a-fA-F]{7,64}", sha):
        return False
    res = subprocess.run(
        ["git", "-C", str(worktree), "cat-file", "-e", f"{sha}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return res.returncode == 0


def _strip_diff_path(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if value == "/dev/null":
        return value
    if value.startswith(("a/", "b/")):
        return value[2:]
    return value


def parse_interdiff_patch(
    patch: str, prior_sha: str, revision_sha: str
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    old_path = "unknown"
    new_path = "unknown"
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            old_path = "unknown"
            new_path = "unknown"
            continue
        if line.startswith("rename from "):
            old_path = _strip_diff_path(line[len("rename from ") :])
            continue
        if line.startswith("rename to "):
            new_path = _strip_diff_path(line[len("rename to ") :])
            continue
        if line.startswith("--- "):
            candidate = _strip_diff_path(line[4:])
            if candidate != "/dev/null":
                old_path = candidate
                if new_path == "unknown":
                    new_path = candidate
            continue
        if line.startswith("+++ "):
            candidate = _strip_diff_path(line[4:])
            if candidate != "/dev/null":
                new_path = candidate
                if old_path == "unknown":
                    old_path = candidate
            continue
        match = re.match(
            r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:\s*(.*))?$", line
        )
        if not match:
            continue
        effective_new = new_path if new_path != "unknown" else old_path
        effective_old = old_path if old_path != "unknown" else effective_new
        output.append(
            {
                "id": f"IH{len(output) + 1:04d}",
                "path": effective_new,
                "old_path": effective_old,
                "old_start": int(match.group(1)),
                "old_count": int(match.group(2) or "1"),
                "new_start": int(match.group(3)),
                "new_count": int(match.group(4) or "1"),
                "prior_sha": prior_sha,
                "revision_sha": revision_sha,
            }
        )
    return output


def compute_interdiff_hunks(
    worktree: Path, prior_sha: str, revision_sha: str
) -> list[dict[str, Any]] | None:
    """Return zero-context interdiff hunks, or `None` if `prior_sha` is unreachable."""
    if not commit_reachable(worktree, prior_sha) or not commit_reachable(
        worktree, revision_sha
    ):
        return None
    res = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "diff",
            "--unified=0",
            "--find-renames",
            prior_sha,
            revision_sha,
            "--",
        ],
        text=True,
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if res.returncode != 0:
        return None
    return parse_interdiff_patch(res.stdout, prior_sha, revision_sha)


def format_interdiff_tsv(hunks: list[dict[str, Any]]) -> str:
    lines = ["\t".join(INTERDIFF_COLUMNS)]
    for hunk in hunks:
        lines.append("\t".join(str(hunk[col]) for col in INTERDIFF_COLUMNS))
    return "\n".join(lines) + "\n"


def write_interdiff_tsv(review_dir: Path, hunks: list[dict[str, Any]]) -> Path:
    destination = review_dir / "indexes" / "interdiff-hunks.tsv"
    atomic_write(destination, format_interdiff_tsv(hunks))
    return destination


def load_interdiff_hunks(review_dir: Path) -> list[dict[str, Any]] | None:
    """Load `indexes/interdiff-hunks.tsv`, returning `None` if absent."""
    path = review_dir / "indexes" / "interdiff-hunks.tsv"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None or tuple(reader.fieldnames) != INTERDIFF_COLUMNS:
            raise ValueError(
                f"{path} has columns {reader.fieldnames!r}; expected {list(INTERDIFF_COLUMNS)!r}"
            )
        rows: list[dict[str, Any]] = []
        for idx, row in enumerate(reader, start=2):
            try:
                rows.append(
                    {
                        "id": (row.get("id") or "").strip(),
                        "path": (row.get("path") or "").strip(),
                        "old_path": (row.get("old_path") or "").strip(),
                        "old_start": int(row["old_start"]),
                        "old_count": int(row["old_count"]),
                        "new_start": int(row["new_start"]),
                        "new_count": int(row["new_count"]),
                        "prior_sha": (row.get("prior_sha") or "").strip(),
                        "revision_sha": (row.get("revision_sha") or "").strip(),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}:{idx}: malformed interdiff row: {exc}") from exc
    return rows


def parse_location_ranges(text: str) -> list[tuple[str, int, int]]:
    """Extract `(repo_rel_path, start_line, end_line)` spans from a location cell."""
    spans: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()
    for match in LOCATION_SPAN_RE.finditer(text or ""):
        raw_path = match.group(1).lstrip("/")
        if raw_path.startswith(("http", "https")) or raw_path.endswith((".json", ".tsv")):
            continue
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        if end < start:
            start, end = end, start
        item = (raw_path, start, end)
        if item not in seen:
            seen.add(item)
            spans.append(item)
    return spans


def parse_location_range(text: str) -> tuple[str, int, int] | None:
    spans = parse_location_ranges(text)
    return spans[0] if spans else None


def overlaps_interdiff(
    hunks: list[dict[str, Any]], path: str, start: int, end: int
) -> dict[str, Any] | None:
    """Return the first interdiff hunk overlapping `path:start-end` in new coordinates."""
    norm_path = path.lstrip("/")
    lo, hi = (start, end) if start <= end else (end, start)
    for hunk in hunks:
        if hunk["path"] != norm_path:
            continue
        new_start = int(hunk["new_start"])
        new_count = int(hunk["new_count"])
        if new_count > 0:
            hunk_lo = new_start
            hunk_hi = new_start + new_count - 1
        else:
            # Pure deletion at `new_start` sits between `new_start` and `new_start + 1`.
            hunk_lo = max(1, new_start)
            hunk_hi = new_start + 1
        if lo <= hunk_hi and hi >= hunk_lo:
            return hunk
    return None


def map_prior_range_to_revision(
    hunks: list[dict[str, Any]],
    prior_path: str,
    prior_start: int,
    prior_end: int,
) -> tuple[str, int, int] | None:
    """Map an untouched `prior_sha` range to `revision_sha` coordinates.

    Returns `None` when the prior range itself was modified by an interdiff hunk.
    """
    norm_prior = prior_path.lstrip("/")
    lo, hi = (prior_start, prior_end) if prior_start <= prior_end else (prior_end, prior_start)
    file_hunks = sorted(
        (
            h
            for h in hunks
            if h.get("old_path") == norm_prior or h.get("path") == norm_prior
        ),
        key=lambda item: (int(item["old_start"]), int(item["new_start"])),
    )
    mapped_path = norm_prior
    delta = 0
    for hunk in file_hunks:
        if hunk.get("old_path") == norm_prior and hunk.get("path"):
            mapped_path = str(hunk["path"])
        old_start = int(hunk["old_start"])
        old_count = int(hunk["old_count"])
        new_count = int(hunk["new_count"])
        if old_count > 0:
            old_lo = old_start
            old_hi = old_start + old_count - 1
            if lo <= old_hi and hi >= old_lo:
                return None
            if old_hi < lo:
                delta += new_count - old_count
        else:
            # Pure insertion after `old_start`: touches the boundary if inside `[lo, hi]`,
            # or shifts `[lo, hi]` downward if strictly before `lo`.
            if lo <= old_start <= hi:
                return None
            if old_start < lo:
                delta += new_count
    return (mapped_path, max(1, lo + delta), max(1, hi + delta))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument(
        "--prior-sha",
        help="explicit baseline SHA; defaults to profile.json latest_prior_reviewed_sha",
    )
    args = parser.parse_args()
    review_dir = args.review_dir.resolve()
    pin_path = review_dir / "pin.md"
    if not pin_path.is_file():
        fail(f"missing {pin_path}")
    fields = dict(FIELD_RE.findall(pin_path.read_text(encoding="utf-8")))
    revision = fields.get("Revision SHA", "").strip()
    worktree_raw = fields.get("Worktree", "").strip()
    worktree = Path(worktree_raw.split(" (", 1)[0]) if worktree_raw else None
    if not revision or worktree is None or not worktree.is_dir():
        fail("pin.md must provide valid Revision SHA and Worktree")

    prior_sha = (args.prior_sha or "").strip()
    if not prior_sha:
        profile_path = review_dir / "profile.json"
        if profile_path.is_file():
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            prior_sha = str(
                profile.get("prior_context", {})
                .get("reviewer_history", {})
                .get("latest_prior_reviewed_sha")
                or ""
            ).strip()
    if not prior_sha:
        fail("no prior SHA supplied via --prior-sha or profile.json reviewer_history")

    hunks = compute_interdiff_hunks(worktree, prior_sha, revision)
    if hunks is None:
        fail(f"commit {prior_sha} or {revision} is not reachable in {worktree}")
    destination = write_interdiff_tsv(review_dir, hunks)
    print(f"{len(hunks)} hunk(s): {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
