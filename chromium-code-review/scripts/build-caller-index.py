#!/usr/bin/env python3
"""Precompute one caller search per inventory surface symbol.

Discovery threads repeatedly run the same symbol searches over the same
worktree — every thread that traces a surface re-greps its callers. This
helper runs each search exactly once after inventory collection and writes
the complete results to `callers/<symbol>.txt` plus a `callers/index.tsv`
routing table (surface ID → symbol → hits → scope → file). Threads consult
the index and open only the per-symbol files their tracing needs; they
re-search only when a symbol is absent here or a narrower/different scope is
required. Results are worktree-derived evidence like any other code read —
consulting them is optional and never substitutes for reading the call sites
a lens must actually trace.

**Search scope defaults to the whole repository** so caller-reachability
reasoning can trust the results — callers of a changed API routinely live
outside the changed directories. Passing `--pathspec` narrows the search;
every result file and index row then records that scope explicitly and is
marked scope-limited, so no worker can mistake a narrowed search for
repository-wide completeness.

Re-runs are memoized crash-safely: results are written atomically, and an
existing file is reused only when its header records the same scope and
pinned revision AND its body line count matches its declared hit count — a
truncated, stale, or foreign cache entry is rebuilt, never trusted.

Symbols come mechanically from `indexes/inventory.tsv` surface rows (the last
`::` component of the subject). Group rows and unsearchable subjects are
recorded as skipped with a reason, never silently dropped.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

IDENTIFIER = re.compile(r"[A-Za-z_]\w*")
MIN_LENGTH = 3
REPO_WIDE = "repository-wide"


def fail(message: str) -> None:
    print(f"build-caller-index.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        fail(f"missing {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        fail(f"empty {path}")
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if line.strip():
            cells = line.split("\t")
            rows.append(dict(zip(header, cells + [""] * (len(header) - len(cells)))))
    return rows


def symbol_for(subject: str) -> tuple[str, str]:
    """Return (symbol, skip_reason); exactly one is non-empty."""
    subject = subject.strip()
    if not subject:
        return "", "empty subject"
    if subject.lower().startswith("group:"):
        return "", "aggregated group row — caller search is banned by the " \
                   "inventory aggregation rule"
    tail = subject.split("::")[-1]
    match = IDENTIFIER.search(tail)
    if not match:
        return "", f"no searchable identifier in '{subject}'"
    symbol = match.group(0)
    if symbol == "operator":
        return "", f"operator overload '{subject}' — search manually"
    if len(symbol) < MIN_LENGTH:
        return "", f"symbol '{symbol}' too short to search meaningfully"
    return symbol, ""


def scope_label(pathspecs: list[str]) -> str:
    return " ".join(pathspecs) if pathspecs else REPO_WIDE


HEADER_LINES = 3


def result_header(symbol: str, hits: int, scope: str,
                  revision: str) -> list[str]:
    lines = [
        f"# Callers of `{symbol}` — git grep -I -n -w — scope: {scope} — "
        f"revision: {revision}",
        f"# {hits} hit(s).",
    ]
    if scope != REPO_WIDE:
        lines.append(
            "# SCOPE-LIMITED: callers outside the scope above are NOT "
            "included. Widen the search yourself before relying on this "
            "for caller-reachability or closure proofs.")
    else:
        lines.append("# Repository-wide and uncapped.")
    return lines


def reusable_hits(target: Path, scope: str, revision: str) -> int | None:
    """Return the cached hit count only if the cache entry is provably
    intact: same scope, same pinned revision, and a body whose line count
    matches the declared hit count. Anything else forces a re-search."""
    if not target.is_file():
        return None
    lines = target.read_text(encoding="utf-8").splitlines()
    if len(lines) < HEADER_LINES:
        return None
    if not lines[0].endswith(f"scope: {scope} — revision: {revision}"):
        return None
    declared = re.fullmatch(r"# (\d+) hit\(s\)\.", lines[1])
    if not declared:
        return None
    hits = int(declared.group(1))
    if len(lines) - HEADER_LINES != hits:
        return None
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument(
        "--revision", required=True,
        help="the pinned revision SHA from pin.md; the worktree HEAD must "
             "match it exactly")
    parser.add_argument(
        "--pathspec", action="append", default=[],
        help="narrow the search; default is the whole repository")
    arguments = parser.parse_args()
    review_dir = arguments.review_dir.resolve()
    worktree = arguments.worktree.resolve()
    if not (worktree / ".git").exists():
        fail(f"not a git worktree: {worktree}")
    head = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False)
    if head.returncode != 0:
        fail(f"cannot resolve worktree HEAD: {head.stderr.strip()}")
    if head.stdout.strip() != arguments.revision:
        fail(f"worktree HEAD {head.stdout.strip() or '?'} does not match "
             f"pinned revision {arguments.revision}")
    revision = arguments.revision
    rows = read_tsv(review_dir / "indexes" / "inventory.tsv")
    surfaces = [row for row in rows if row.get("kind") == "surface"]
    if not surfaces:
        fail("inventory index has no surface rows")

    pathspecs = list(arguments.pathspec)
    scope = scope_label(pathspecs)
    callers = review_dir / "callers"
    callers.mkdir(parents=True, exist_ok=True)
    searched: dict[str, int] = {}
    reused = 0
    index_rows = []
    for row in surfaces:
        surface_id = row.get("id", "")
        subject = row.get("subject", "")
        symbol, reason = symbol_for(subject)
        if reason:
            index_rows.append((surface_id, subject, "-", "-", "-",
                               f"skipped — {reason}"))
            continue
        if symbol not in searched:
            target = callers / f"{symbol}.txt"
            cached = reusable_hits(target, scope, revision)
            if cached is not None:
                searched[symbol] = cached
                reused += 1
            else:
                command = ["git", "-C", str(worktree), "grep", "-I", "-n",
                           "-w", symbol]
                if pathspecs:
                    command += ["--", *pathspecs]
                result = subprocess.run(
                    command, capture_output=True, text=True, check=False)
                if result.returncode not in (0, 1):
                    fail(f"git grep failed for '{symbol}': "
                         f"{result.stderr.strip()}")
                hits = result.stdout.splitlines()
                searched[symbol] = len(hits)
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_text(
                    "\n".join(result_header(symbol, len(hits), scope,
                                            revision) + hits)
                    + "\n", encoding="utf-8")
                temporary.replace(target)
        index_rows.append((surface_id, subject, symbol,
                           str(searched[symbol]), scope,
                           f"callers/{symbol}.txt"))

    index_lines = ["surface_id\tsubject\tsymbol\thits\tscope\tresult"]
    index_lines += ["\t".join(row) for row in index_rows]
    (callers / "index.tsv").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8")
    skipped = sum(1 for row in index_rows if row[2] == "-")
    print(f"{callers / 'index.tsv'}: {len(surfaces)} surfaces, "
          f"{len(searched)} symbols ({reused} reused), {skipped} skipped, "
          f"{sum(searched.values())} total hits, scope: {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
