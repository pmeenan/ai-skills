#!/usr/bin/env python3
"""Look up a gate or helper failure message in references/gate-errors.md.

The catalogue is a 700-row lookup table, far too large to read. Reading it
whole would simply move the waste that it exists to remove, so this helper
queries it: paste the failure message, get the matching rows.

    explain-gate-error.py "byte count mismatch"
    explain-gate-error.py --max 10 "invalid choice: 'inventory'"

Matching is token-based and tolerant of the concrete values a real message
carries: paths, line numbers, work IDs, and quoted values are ignored, so the
message you actually saw matches the catalogue's parameterized form.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROGRAM = "explain-gate-error.py"

# Tokens that appear in almost every row and so carry no discriminating power.
STOPWORDS = frozenset(
    """a an and are as at be but by error for from has have in is it its no
    not of on or that the this to was were will with warning fail failed
    cannot could did does do not py sh""".split()
)

PLACEHOLDER = re.compile(r"⟨[^⟩]*⟩|<[^>]*>|\{[^}]*\}")
NUMBERS = re.compile(r"\b\d[\d.,:_-]*\b")
PATHS = re.compile(r"(?<![A-Za-z0-9_])/[A-Za-z0-9_.+@%=/-]+")


def fail(message: str) -> None:
    print(f"{PROGRAM}: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def tokenize(text: str) -> list[str]:
    text = text.replace("`", " ")
    text = PLACEHOLDER.sub(" ", text)
    text = PATHS.sub(" ", text)
    text = NUMBERS.sub(" ", text)
    text = text.lower()
    return [t for t in re.split(r"[^a-z0-9_]+", text) if len(t) > 1 and t not in STOPWORDS]


def split_row(line: str) -> list[str] | None:
    """Split one markdown table row into its cells, or None if it is not one."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [c.strip() for c in stripped[1:-1].split("|")]
    if len(cells) < 3:
        return None
    if all(set(c) <= set("-: ") for c in cells):  # separator row
        return None
    return cells


def load_rows(catalogue: Path) -> list[tuple[int, str, list[str]]]:
    """Return (line number, current section, cells) for every table row."""
    rows: list[tuple[int, str, list[str]]] = []
    section = ""
    for number, line in enumerate(catalogue.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            continue
        cells = split_row(line)
        if cells is None:
            continue
        if cells[0].lower() in {"message", "flag / column", "error", "symptom"}:
            continue  # header row
        rows.append((number, section, cells))
    return rows


def score(query: list[str], pattern: list[str]) -> float:
    """Fraction of the catalogue row's distinctive tokens present in the query."""
    if not pattern:
        return 0.0
    wanted = set(pattern)
    hit = wanted & set(query)
    if len(hit) < 2 and len(wanted) > 1:
        return 0.0
    # Favour rows whose whole message is covered, then longer messages, so a
    # specific row outranks a generic one that happens to share a word.
    return len(hit) / len(wanted) + 0.01 * len(hit)


def default_catalogue() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "gate-errors.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Look up a gate or helper failure message in the gate-error catalogue.",
    )
    parser.add_argument("message", nargs="+", help="the failure message, quoted")
    parser.add_argument("--catalogue", type=Path, default=None,
                        help="default: ../references/gate-errors.md next to this script")
    parser.add_argument("--max", type=int, default=5, help="rows to print (default 5)")
    args = parser.parse_args(argv)

    catalogue = args.catalogue or default_catalogue()
    if not catalogue.is_file():
        fail(f"no gate-error catalogue at {catalogue}; pass --catalogue explicitly")
    if args.max < 1:
        fail("--max must be at least 1")

    query = tokenize(" ".join(args.message))
    if not query:
        fail("the message has no searchable words; quote the message text itself")

    scored = []
    for number, section, cells in load_rows(catalogue):
        value = score(query, tokenize(cells[0]))
        if value > 0:
            scored.append((value, number, section, cells))
    scored.sort(key=lambda item: (-item[0], item[1]))

    if not scored:
        print(f"{PROGRAM}: no row matches that message.")
        print(f"{PROGRAM}: add one to {catalogue} once you have worked out the fix.")
        return 1

    for value, number, section, cells in scored[: args.max]:
        print(f"--- {section}  ({catalogue.name}:{number}, score {value:.2f})")
        print(f"MESSAGE: {cells[0]}")
        print(f"MEANS:   {cells[1]}")
        print(f"FIX:     {cells[2]}")
        if len(cells) > 3 and cells[3]:
            print(f"SOURCE:  {cells[3]}")
        print()
    remaining = len(scored) - args.max
    if remaining > 0:
        print(f"{PROGRAM}: {remaining} further row(s) matched; re-run with --max to see them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
