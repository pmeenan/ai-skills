#!/usr/bin/env python3
"""Shared strict Markdown-table and structured-amendment handling."""

from __future__ import annotations

import json
import re
from typing import Iterable


Table = tuple[str, list[str], list[dict[str, str]]]

PLAN_ROSTER_COLUMNS = (
    "roster entry", "scope", "status", "tier", "batch", "subagent",
    "outcome",
)
PLAN_CONTINUATION_HEADING = re.compile(
    r"^Round-two residue continuation — PLAN attempt ([1-9][0-9]*)$"
)
PLAN_CONTINUATION_PREFIX = "Round-two residue continuation"
PLAN_DEFERRED_STATUS = "deferred — pending TER gate (round two)"
PLAN_REPAIR_COLUMNS = (
    "roster entry", "expected status", "scope", "status", "tier", "batch",
    "evidence",
)
PLAN_REPAIR_HEADING = re.compile(
    r"^Plan repair continuation — PLAN attempt ([1-9][0-9]*)$"
)
PLAN_REPAIR_PREFIX = "Plan repair continuation"
PLAN_GRAPH_HEADING = re.compile(
    r"^Graph routing continuation — PLAN attempt ([1-9][0-9]*)$"
)
PLAN_GRAPH_PREFIX = "Graph routing continuation"
PLAN_NOT_APPLICABLE_PREFIX = "not applicable — trigger absence proved by "
PLAN_SPAWN_TIERS = {"mechanical", "standard", "frontier"}

_PARENTHESIZED_SHARD = re.compile(
    r"^(?P<base>.+?)\s+\(shard\s*(?P<shard>[1-9][0-9]*)"
    r"(?:\s*:[^)]*)?\)\s*$",
    re.IGNORECASE,
)
_EM_DASH_SHARD = re.compile(
    r"^(?P<base>.+?)\s+—\s*shard\s*(?P<shard>[1-9][0-9]*)"
    r"(?:\s*:?.*)?$",
    re.IGNORECASE,
)


def plan_row_identity(roster_entry: str) -> tuple[str, int | None]:
    """Return the stable plan identity: base roster name plus shard number."""
    value = roster_entry.strip()
    for pattern in (_PARENTHESIZED_SHARD, _EM_DASH_SHARD):
        match = pattern.fullmatch(value)
        if match:
            return match.group("base").strip(), int(match.group("shard"))
    return value, None


def _plan_continuation_kind(heading: str) -> str | None:
    if PLAN_CONTINUATION_HEADING.fullmatch(heading):
        return "residue"
    if PLAN_REPAIR_HEADING.fullmatch(heading):
        return "repair"
    if PLAN_GRAPH_HEADING.fullmatch(heading):
        return "graph"
    return None


def _plan_continuation_attempt(heading: str) -> int | None:
    for pattern in (
        PLAN_CONTINUATION_HEADING, PLAN_REPAIR_HEADING, PLAN_GRAPH_HEADING
    ):
        match = pattern.fullmatch(heading)
        if match:
            return int(match.group(1))
    return None


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


def _apply_plan_repair_table(
    heading: str,
    header: list[str],
    repair_rows: list[dict[str, str]],
    base_rows: list[dict[str, str]],
    source: str,
    errors: list[str],
) -> None:
    """Apply one atomic proof/status repair table to effective roster rows."""
    if tuple(header) != PLAN_REPAIR_COLUMNS:
        errors.append(
            f"{source}: plan repair '{heading}' must have exactly the ordered "
            "columns " + " | ".join(PLAN_REPAIR_COLUMNS)
        )
        return
    if not repair_rows:
        errors.append(f"{source}: plan repair '{heading}' has no rows")
        return

    table_error_count = len(errors)
    seen: set[tuple[str, int | None]] = set()
    operations: list[tuple[int, dict[str, str]]] = []
    for repair in repair_rows:
        entry = repair.get("roster entry", "")
        identity = plan_row_identity(entry)
        label = identity[0] + (
            f" shard {identity[1]}" if identity[1] is not None else ""
        )
        if not identity[0]:
            errors.append(f"{source}: plan repair '{heading}' has a blank target")
            continue
        if identity in seen:
            errors.append(
                f"{source}: plan repair '{heading}' duplicates target {label}"
            )
            continue
        seen.add(identity)
        matches = [
            (index, row) for index, row in enumerate(base_rows)
            if plan_row_identity(row.get("roster entry", "")) == identity
        ]
        if len(matches) != 1:
            errors.append(
                f"{source}: plan repair target '{label}' resolves to "
                f"{len(matches)} rows; expected exactly one"
            )
            continue
        index, target = matches[0]
        prior_status = target.get("status", "")
        expected_status = repair.get("expected status", "")
        replacement_status = repair.get("status", "")
        if prior_status == PLAN_DEFERRED_STATUS:
            errors.append(
                f"{source}: plan repair target '{label}' is deferred; use the "
                "round-two residue continuation"
            )
        if prior_status != expected_status:
            errors.append(
                f"{source}: plan repair target '{label}' expected status "
                f"'{expected_status}' but effective status is '{prior_status}'"
            )
        if not prior_status.startswith(PLAN_NOT_APPLICABLE_PREFIX):
            errors.append(
                f"{source}: plan repair target '{label}' is not an existing "
                "not-applicable proof row"
            )
        if replacement_status != "spawn" and not replacement_status.startswith(
                PLAN_NOT_APPLICABLE_PREFIX):
            errors.append(
                f"{source}: plan repair target '{label}' replacement status "
                "must be spawn or an exact not-applicable proof"
            )
        if replacement_status == prior_status:
            errors.append(
                f"{source}: plan repair target '{label}' is a no-op"
            )
        evidence = repair.get("evidence", "").strip()
        if evidence in {"", "—", "-"}:
            errors.append(
                f"{source}: plan repair target '{label}' lacks evidence"
            )

        replacement = dict(target)
        if replacement_status == "spawn":
            scope = repair.get("scope", "").strip()
            tier = repair.get("tier", "").strip()
            batch = repair.get("batch", "").strip()
            if scope in {"", "—", "-"}:
                errors.append(
                    f"{source}: plan repair spawn target '{label}' lacks scope"
                )
            if tier not in PLAN_SPAWN_TIERS:
                errors.append(
                    f"{source}: plan repair spawn target '{label}' has invalid "
                    f"tier '{tier}'"
                )
            if batch in {"", "—", "-"}:
                errors.append(
                    f"{source}: plan repair spawn target '{label}' lacks batch"
                )
        else:
            for field in ("scope", "tier", "batch"):
                if repair.get(field, "") != target.get(field, ""):
                    errors.append(
                        f"{source}: plan repair not-applicable target '{label}' "
                        f"must preserve {field}"
                    )
        for field in ("scope", "status", "tier", "batch"):
            replacement[field] = repair.get(field, "")
        operations.append((index, replacement))

    if len(errors) != table_error_count:
        return
    for index, replacement in operations:
        base_rows[index] = replacement


def _row_matches(heading: str, row: dict[str, str], index: int,
                 target: str) -> bool:
    if target.startswith("matrix:") and heading == "Compliance matrix":
        return target == f"matrix:{index}"
    if target.startswith("descriptor:") and heading == "Candidate descriptors":
        return row.get("candidate") == target.removeprefix("descriptor:")
    if target.startswith("trace:") and heading == "Trace closure":
        parts = target.split(":", 2)
        return (
            len(parts) == 3
            and row.get("candidate") == parts[1]
            and row.get("obligation") == parts[2]
        )
    if target.startswith("affinity:") and heading == "Verified affinity":
        return row.get("candidate") == target.removeprefix("affinity:")
    if target.startswith("family:") and heading == "Root families":
        return row.get("root family") == target.removeprefix("family:")
    if target.startswith("audit:") and heading == "Consistency audit":
        return row.get("check") == target.removeprefix("audit:")
    if target.startswith("root-family:") and heading == "Root-family analysis":
        return row.get("root family") == target.removeprefix("root-family:")
    for column in (
        "surface id", "scope id", "id", "row", "class id", "thread", "unit"
    ):
        if row.get(column) == target:
            return True
    return False


def _apply_plan_continuations(
    text: str,
    parsed: list[Table],
    source: str,
    errors: list[str],
) -> list[Table]:
    """Collapse append-only round-two plan tables into one effective roster.

    The source text remains the audit record. Only the parsed effective view
    is changed, and only for the exact plan continuation heading and schema.
    """
    declared: list[tuple[str, int, str]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.startswith("## "):
            continue
        heading = line[3:].strip()
        if not heading.startswith((
            PLAN_CONTINUATION_PREFIX, PLAN_REPAIR_PREFIX, PLAN_GRAPH_PREFIX
        )):
            continue
        kind = _plan_continuation_kind(heading)
        attempt = _plan_continuation_attempt(heading)
        if kind is None or attempt is None:
            if heading.startswith(PLAN_CONTINUATION_PREFIX):
                expected = "'Round-two residue continuation — PLAN attempt <N>'"
            elif heading.startswith(PLAN_REPAIR_PREFIX):
                expected = "'Plan repair continuation — PLAN attempt <N>'"
            else:
                expected = "'Graph routing continuation — PLAN attempt <N>'"
            errors.append(
                f"{source}:{line_number}: non-canonical plan continuation "
                f"heading; expected {expected}"
            )
            continue
        declared.append((heading, attempt, kind))

    if not declared:
        return parsed

    attempts = [attempt for _, attempt, _ in declared]
    if len(attempts) != len(set(attempts)):
        errors.append(f"{source}: duplicate PLAN continuation attempt heading")
    if any(current <= previous for previous, current in zip(attempts, attempts[1:])):
        errors.append(
            f"{source}: PLAN continuation attempt headings are not strictly "
            "increasing"
        )

    working: list[Table] = [
        (heading, list(header), [dict(row) for row in rows])
        for heading, header, rows in parsed
    ]
    continuation_indexes: list[int] = []
    heading_counts: dict[str, int] = {}
    for index, (heading, _, _) in enumerate(working):
        if _plan_continuation_kind(heading) is not None:
            continuation_indexes.append(index)
            heading_counts[heading] = heading_counts.get(heading, 0) + 1

    for heading, _, _ in declared:
        count = heading_counts.get(heading, 0)
        if count != 1:
            errors.append(
                f"{source}: plan continuation section '{heading}' contains "
                f"{count} tables; expected exactly one"
            )

    if errors:
        return working

    first_continuation = min(continuation_indexes)
    base_indexes = [
        index
        for index, (heading, header, _) in enumerate(working)
        if index < first_continuation
        and _plan_continuation_kind(heading) is None
        and tuple(header) == PLAN_ROSTER_COLUMNS
    ]
    if len(base_indexes) != 1:
        errors.append(
            f"{source}: plan continuation resolves against {len(base_indexes)} "
            "earlier canonical roster tables; expected exactly one"
        )
        return working

    base_rows = working[base_indexes[0]][2]
    for continuation_index in continuation_indexes:
        heading, header, continuation_rows = working[continuation_index]
        if PLAN_REPAIR_HEADING.fullmatch(heading):
            _apply_plan_repair_table(
                heading, header, continuation_rows, base_rows, source, errors
            )
            continue
        if tuple(header) != PLAN_ROSTER_COLUMNS:
            errors.append(
                f"{source}: plan continuation '{heading}' must have exactly "
                "the ordered columns " + " | ".join(PLAN_ROSTER_COLUMNS)
            )
            continue
        if not continuation_rows:
            errors.append(f"{source}: plan continuation '{heading}' has no rows")
            continue

        if PLAN_GRAPH_HEADING.fullmatch(heading):
            table_error_count = len(errors)
            effective_identities = {
                plan_row_identity(row.get("roster entry", ""))
                for row in base_rows
            }
            additions: list[dict[str, str]] = []
            for row in continuation_rows:
                entry = row.get("roster entry", "")
                identity = plan_row_identity(entry)
                if not identity[0]:
                    errors.append(
                        f"{source}: graph routing continuation '{heading}' "
                        "has a blank roster entry"
                    )
                    continue
                if identity in effective_identities:
                    errors.append(
                        f"{source}: graph routing continuation '{heading}' "
                        f"duplicates effective identity {entry}"
                    )
                effective_identities.add(identity)
                if row.get("status", "") != "spawn":
                    errors.append(
                        f"{source}: graph routing row '{entry}' must have "
                        "status 'spawn'"
                    )
                if "graph:" not in row.get("scope", "").lower():
                    errors.append(
                        f"{source}: graph routing row '{entry}' scope must "
                        "cite graph:<edge-id(s)>"
                    )
                additions.append(dict(row))
            if len(errors) == table_error_count:
                base_rows.extend(additions)
            continue

        table_error_count = len(errors)
        groups: dict[str, list[tuple[tuple[str, int | None], dict[str, str]]]] = {}
        seen_continuation_identities: set[tuple[str, int | None]] = set()
        for row in continuation_rows:
            entry = row.get("roster entry", "")
            identity = plan_row_identity(entry)
            if not identity[0]:
                errors.append(
                    f"{source}: plan continuation '{heading}' has a blank "
                    "roster entry"
                )
                continue
            if identity in seen_continuation_identities:
                errors.append(
                    f"{source}: plan continuation '{heading}' duplicates "
                    f"transition target {identity[0]}"
                    + (f" shard {identity[1]}" if identity[1] is not None else "")
                )
                continue
            seen_continuation_identities.add(identity)
            if row.get("status", "") != "spawn":
                errors.append(
                    f"{source}: plan continuation row '{entry}' has status "
                    f"'{row.get('status', '')}'; expected 'spawn'"
                )
            groups.setdefault(identity[0], []).append((identity, row))

        operations: list[tuple[int, list[dict[str, str]]]] = []
        for base, rows in groups.items():
            continuation_shards = [identity[1] for identity, _ in rows]
            has_unsharded = any(shard is None for shard in continuation_shards)
            has_sharded = any(shard is not None for shard in continuation_shards)
            if has_unsharded and has_sharded:
                errors.append(
                    f"{source}: plan continuation '{heading}' mixes sharded "
                    f"and unsharded rows for {base}"
                )
                continue

            effective = [
                (index, plan_row_identity(row.get("roster entry", "")), row)
                for index, row in enumerate(base_rows)
                if plan_row_identity(row.get("roster entry", ""))[0] == base
            ]
            unsharded = [item for item in effective if item[1][1] is None]
            sharded = [item for item in effective if item[1][1] is not None]

            if has_unsharded:
                if len(rows) != 1 or len(unsharded) != 1 or sharded:
                    errors.append(
                        f"{source}: plan continuation target '{base}' resolves "
                        "ambiguously; expected exactly one earlier unsharded "
                        "deferred row"
                    )
                    continue
                index, _, target = unsharded[0]
                if target.get("status", "") != PLAN_DEFERRED_STATUS:
                    errors.append(
                        f"{source}: plan continuation target '{base}' is not "
                        "an earlier deferred row"
                    )
                    continue
                operations.append((index, [dict(rows[0][1])]))
                continue

            if len(unsharded) == 1 and not sharded:
                index, _, target = unsharded[0]
                if target.get("status", "") != PLAN_DEFERRED_STATUS:
                    errors.append(
                        f"{source}: sharded plan continuation target '{base}' "
                        "is not an earlier deferred row"
                    )
                    continue
                operations.append((index, [dict(row) for _, row in rows]))
                continue
            if unsharded:
                errors.append(
                    f"{source}: sharded plan continuation target '{base}' is "
                    "ambiguous"
                )
                continue

            for identity, replacement in rows:
                matches = [item for item in sharded if item[1] == identity]
                label = f"{base} shard {identity[1]}"
                if len(matches) != 1:
                    errors.append(
                        f"{source}: plan continuation target '{label}' "
                        f"resolves to {len(matches)} earlier rows; expected "
                        "exactly one deferred row"
                    )
                    continue
                index, _, target = matches[0]
                if target.get("status", "") != PLAN_DEFERRED_STATUS:
                    errors.append(
                        f"{source}: plan continuation target '{label}' is not "
                        "an earlier deferred row"
                    )
                    continue
                operations.append((index, [dict(replacement)]))

        if len(errors) != table_error_count:
            continue
        for index, replacements in sorted(operations, reverse=True):
            base_rows[index:index + 1] = replacements

    return [
        table for index, table in enumerate(working)
        if index not in set(continuation_indexes)
    ]


def effective_tables(text: str, source: str = "input") -> tuple[list[Table], list[str]]:
    """Parse tables and apply append-only structured field replacements.

    A structured amendment uses operation `replace-fields` and stores a JSON
    object in `replacement / reason`. Targets are stable row IDs or
    `matrix:<1-based-row>`. Descriptor/verification family tables use the
    explicit targets `descriptor:<candidate>`, `trace:<candidate>:<obligation>`,
    `affinity:<candidate>`, `family:<RF-id>`, `audit:<check>`, and
    `root-family:<RF-id>`. Every target must resolve to exactly one row and
    every replacement key must name an existing column.
    """
    parsed, errors = parse_tables(text, source)
    parsed = _apply_plan_continuations(text, parsed, source, errors)
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
