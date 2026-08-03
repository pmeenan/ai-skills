#!/usr/bin/env python3
"""Generate per-section worker reference files from the canonical references.

Canonical reference files stay authoritative and unchanged. This helper derives
`references/worker/<stem>/<slug>.md` — one file per `##` section, prefixed with
the source file's preamble (everything before the first `##` heading) — plus a
per-stem `index.md` mapping section headings to generated files. Workers and
generated briefs name the exact section files they need instead of ingesting a
whole reference monolith; the canonical file remains the fallback whenever a
worker genuinely needs several sections.

Two mechanical transforms, both deliberately conservative:

- Split: fence-aware, at `##` headings only; `## Contents` link tables are
  dropped (useless standalone). Heading levels and body bytes are preserved so
  load-bearing headings (e.g. `## Candidate rows`) extract identically.
- Rationale strip: the references state rules in bold and record the measured
  failure that motivates each rule as an indented paragraph; the files
  themselves declare the rules normative without the rationale. A block is
  stripped only when every line is indented at least two spaces, it is
  delimited by blank lines, it sits outside code fences, and the nearest
  preceding non-blank line is flush-left prose that does not introduce it with
  a trailing colon. Anything else is preserved verbatim.

Run standalone for inspection, or let snapshot-skill.py invoke it while
staging a review snapshot so every snapshot carries the derived files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys

WORKER_DIR = "worker"
GENERATED_NOTE = (
    "<!-- Generated from ../../{stem}.md by build_worker_references.py; "
    "do not edit. Canonical text lives in the source file. -->"
)

FENCE = re.compile(r"^(`{3,}|~{3,})")
HEADING = re.compile(r"^## +(.+?)\s*$")
INDENTED = re.compile(r"^ {2,}\S")


def fail(message: str) -> None:
    print(f"build_worker_references.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def slugify(heading: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return slug or "section"


def fence_states(lines: list[str]) -> list[bool]:
    """Per-line flag: is this line inside (or opening/closing) a code fence?"""
    states = []
    open_fence = ""
    for line in lines:
        match = FENCE.match(line)
        if open_fence:
            states.append(True)
            if match and match.group(1)[0] == open_fence[0] \
                    and len(match.group(1)) >= len(open_fence):
                open_fence = ""
        elif match:
            states.append(True)
            open_fence = match.group(1)
        else:
            states.append(False)
    return states


def strip_rationale(lines: list[str]) -> list[str]:
    """Drop blank-line-delimited fully-indented rationale blocks."""
    fenced = fence_states(lines)
    keep = [True] * len(lines)
    index = 0
    while index < len(lines):
        if fenced[index] or not INDENTED.match(lines[index]) \
                or (index > 0 and lines[index - 1].strip()):
            index += 1
            continue
        end = index
        while end < len(lines) and lines[end].strip():
            if fenced[end] or not INDENTED.match(lines[end]):
                break
            end += 1
        else:
            # Block is uniformly indented and blank-line-terminated (or EOF).
            previous = next(
                (i for i in range(index - 1, -1, -1) if lines[i].strip()),
                None,
            )
            if previous is not None and not fenced[previous] \
                    and not lines[previous].startswith((" ", "\t")) \
                    and not lines[previous].rstrip().endswith(":"):
                for i in range(index, end):
                    keep[i] = False
                # Also drop the now-redundant trailing blank separator.
                if end < len(lines) and not lines[end].strip():
                    keep[end] = False
            index = end + 1
            continue
        index = end + 1
    return [line for line, kept in zip(lines, keep) if kept]


def split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    fenced = fence_states(lines)
    boundaries = [
        (index, HEADING.match(line).group(1))
        for index, line in enumerate(lines)
        if not fenced[index] and HEADING.match(line)
    ]
    if not boundaries:
        return lines, []
    preamble = lines[: boundaries[0][0]]
    sections = []
    for position, (start, title) in enumerate(boundaries):
        end = boundaries[position + 1][0] if position + 1 < len(boundaries) \
            else len(lines)
        sections.append((title, lines[start:end]))
    return preamble, sections


def trim(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def build(references_dir: Path) -> list[Path]:
    if not references_dir.is_dir():
        fail(f"not a directory: {references_dir}")
    worker_root = references_dir / WORKER_DIR
    if worker_root.exists():
        shutil.rmtree(worker_root)
    generated: list[Path] = []
    for source in sorted(references_dir.glob("*.md")):
        lines = source.read_text(encoding="utf-8").splitlines()
        preamble, sections = split_sections(strip_rationale(lines))
        if not sections:
            continue
        stem_dir = worker_root / source.stem
        stem_dir.mkdir(parents=True, exist_ok=True)
        note = GENERATED_NOTE.format(stem=source.stem)
        used: dict[str, int] = {}
        index_rows = []
        for title, body in sections:
            if title.strip().lower() == "contents":
                continue
            slug = slugify(title)
            used[slug] = used.get(slug, 0) + 1
            if used[slug] > 1:
                slug = f"{slug}-{used[slug]}"
            target = stem_dir / f"{slug}.md"
            payload = [note, ""] + trim(preamble) + [""] + trim(body)
            target.write_text("\n".join(payload) + "\n", encoding="utf-8")
            generated.append(target)
            index_rows.append((title, target.name, len(body)))
        index_lines = [
            note,
            "",
            f"# Worker reference index — {source.name}",
            "",
            "Generated per-section files. A brief should name the exact",
            "section file(s) its worker must execute; fall back to the",
            f"canonical `../../{source.name}` only when a worker genuinely",
            "needs most of its sections. Each file repeats the source",
            "preamble, so its rules travel with every section.",
            "",
            "| section | file | source lines |",
            "| --- | --- | --- |",
        ]
        index_lines += [
            f"| {title} | {name} | {count} |"
            for title, name, count in index_rows
        ]
        index_path = stem_dir / "index.md"
        index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        generated.append(index_path)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references_dir", type=Path)
    arguments = parser.parse_args()
    generated = build(arguments.references_dir.resolve())
    print(f"generated {len(generated)} worker reference files under "
          f"{arguments.references_dir / WORKER_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
