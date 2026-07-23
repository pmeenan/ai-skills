#!/usr/bin/env python3
"""Shared strict Markdown-table and structured-amendment handling."""

from __future__ import annotations

import json
import re
from typing import Iterable


Table = tuple[str, list[str], list[dict[str, str]]]


def split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith(r"\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [cell.replace(r"\|", "|").strip() for cell in cells]


def parse_tables(text: str, source: str = "input") -> tuple[list[Table], list[str]]:
    lines = text.splitlines()
    heading = ""
    index = 0
    parsed: list[Table] = []
    errors: list[str] = []
    while index < len(lines):
        if lines[index].startswith("## "):
            heading = lines[index][3:].strip()
        if (
            lines[index].lstrip().startswith("|")
            and index + 1 < len(lines)
            and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1])
        ):
            header = [cell.lower() for cell in split_row(lines[index])]
            index += 2
            rows: list[dict[str, str]] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                values = split_row(lines[index])
                if len(values) != len(header):
                    errors.append(
                        f"{source}:{index + 1}: malformed Markdown table row; "
                        f"expected {len(header)} cells, found {len(values)}"
                    )
                else:
                    rows.append(dict(zip(header, values)))
                index += 1
            parsed.append((heading, header, rows))
            continue
        index += 1
    return parsed, errors


def _row_matches(heading: str, row: dict[str, str], index: int,
                 target: str) -> bool:
    if target.startswith("matrix:") and heading == "Compliance matrix":
        return target == f"matrix:{index}"
    for column in (
        "surface id", "scope id", "id", "row", "class id", "thread", "unit"
    ):
        if row.get(column) == target:
            return True
    return False


def effective_tables(text: str, source: str = "input") -> tuple[list[Table], list[str]]:
    """Parse tables and apply append-only structured field replacements.

    A structured amendment uses operation `replace-fields` and stores a JSON
    object in `replacement / reason`. Targets are stable row IDs or
    `matrix:<1-based-row>`. Every target must resolve to exactly one row and
    every replacement key must name an existing column.
    """
    parsed, errors = parse_tables(text, source)
    amendments: list[dict[str, str]] = []
    for heading, header, rows in parsed:
        if heading == "Amendments" and {
            "amendment", "target", "operation", "replacement / reason"
        }.issubset(header):
            amendments.extend(rows)

    for amendment in amendments:
        if amendment.get("operation", "").strip().lower() != "replace-fields":
            continue
        name = amendment.get("amendment", "").strip() or "unnamed amendment"
        target = amendment.get("target", "").strip()
        raw = amendment.get("replacement / reason", "").strip()
        try:
            replacements = json.loads(raw)
        except json.JSONDecodeError as error:
            errors.append(
                f"{source}: {name} replace-fields payload is not valid JSON: {error}"
            )
            continue
        if not isinstance(replacements, dict) or not replacements or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in replacements.items()
        ):
            errors.append(
                f"{source}: {name} replace-fields payload must be a non-empty "
                "JSON object of string fields"
            )
            continue
        matches: list[tuple[list[str], dict[str, str]]] = []
        for heading, header, rows in parsed:
            if heading == "Amendments":
                continue
            for index, row in enumerate(rows, 1):
                if _row_matches(heading, row, index, target):
                    matches.append((header, row))
        if len(matches) != 1:
            errors.append(
                f"{source}: {name} target '{target}' resolves to {len(matches)} "
                "rows; expected exactly one"
            )
            continue
        header, row = matches[0]
        unknown = sorted(set(replacements) - set(header))
        if unknown:
            errors.append(
                f"{source}: {name} replaces unknown field(s): {', '.join(unknown)}"
            )
            continue
        row.update(replacements)
    return parsed, errors


def iter_effective_tables(text: str, source: str = "input") -> Iterable[Table]:
    tables, errors = effective_tables(text, source)
    if errors:
        raise ValueError("\n".join(errors))
    yield from tables
