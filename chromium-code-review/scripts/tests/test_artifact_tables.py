#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from artifact_tables import (  # noqa: E402
    PLAN_DEFERRED_STATUS,
    PLAN_REPAIR_COLUMNS,
    effective_tables,
    parse_tables,
)


COLUMNS = "| roster entry | scope | status | tier | batch | subagent | outcome |"
SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- |"
REPAIR_COLUMNS = "| " + " | ".join(PLAN_REPAIR_COLUMNS) + " |"
REPAIR_SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- |"


def plan(initial_rows: list[str], continuations: list[tuple[int, list[str]]]) -> str:
    sections = ["# Plan", "", COLUMNS, SEPARATOR, *initial_rows]
    for attempt, rows in continuations:
        sections.extend([
            "",
            f"## Round-two residue continuation — PLAN attempt {attempt}",
            "",
            COLUMNS,
            SEPARATOR,
            *rows,
        ])
    return "\n".join(sections) + "\n"


def row(entry: str, scope: str, status: str, tier: str = "frontier") -> str:
    return f"| {entry} | {scope} | {status} | {tier} | D01 | — | — |"


def repair(
    text: str,
    attempt: int,
    rows: list[str],
) -> str:
    return text + "\n" + "\n".join((
        f"## Plan repair continuation — PLAN attempt {attempt}",
        "",
        REPAIR_COLUMNS,
        REPAIR_SEPARATOR,
        *rows,
        "",
    ))


def repair_row(
    entry: str,
    expected_status: str,
    scope: str,
    status: str,
    tier: str,
    batch: str,
    evidence: str = "T001",
) -> str:
    return (
        f"| {entry} | {expected_status} | {scope} | {status} | {tier} | "
        f"{batch} | {evidence} |"
    )


def roster_rows(text: str) -> tuple[list[dict[str, str]], list[str]]:
    parsed, errors = effective_tables(text, "plan.md")
    rows = [
        item
        for _, header, table_rows in parsed
        if "roster entry" in header and "status" in header
        for item in table_rows
    ]
    return rows, errors


class PlanContinuationTest(unittest.TestCase):
    def test_one_to_one_transition_preserves_raw_history(self) -> None:
        text = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)],
            [(2, [row("Error-Path Walk", "new", "spawn")])],
        )
        effective, errors = roster_rows(text)
        self.assertEqual([], errors)
        self.assertEqual(1, len(effective))
        self.assertEqual("new", effective[0]["scope"])
        self.assertEqual("spawn", effective[0]["status"])

        raw, raw_errors = parse_tables(text, "plan.md")
        self.assertEqual([], raw_errors)
        self.assertEqual([1, 1], [len(rows) for _, _, rows in raw])
        self.assertEqual(
            [PLAN_DEFERRED_STATUS, "spawn"],
            [rows[0]["status"] for _, _, rows in raw],
        )

    def test_unsharded_deferred_row_expands_to_shards(self) -> None:
        text = plan(
            [row("Error-Path Walk", "whole", PLAN_DEFERRED_STATUS)],
            [(2, [
                row("Error-Path Walk (shard 1: parse)", "parse", "spawn"),
                row("Error-Path Walk (shard 2: consume)", "consume", "spawn"),
            ])],
        )
        effective, errors = roster_rows(text)
        self.assertEqual([], errors)
        self.assertEqual(
            [
                "Error-Path Walk (shard 1: parse)",
                "Error-Path Walk (shard 2: consume)",
            ],
            [item["roster entry"] for item in effective],
        )
        self.assertTrue(all(item["status"] == "spawn" for item in effective))

    def test_pre_sharded_rows_transition_by_number_not_scope_label(self) -> None:
        text = plan(
            [
                row("Error-Path Walk (shard 1: old-a)", "old-a", PLAN_DEFERRED_STATUS),
                row("Error-Path Walk (shard 2: old-b)", "old-b", PLAN_DEFERRED_STATUS),
            ],
            [(2, [
                row("Error-Path Walk (shard 1: new-a)", "new-a", "spawn"),
                row("Error-Path Walk (shard 2: new-b)", "new-b", "spawn"),
            ])],
        )
        effective, errors = roster_rows(text)
        self.assertEqual([], errors)
        self.assertEqual(["new-a", "new-b"], [item["scope"] for item in effective])

    def test_later_attempt_transitions_disjoint_remaining_row(self) -> None:
        text = plan(
            [
                row("Error-Path Walk", "old-a", PLAN_DEFERRED_STATUS),
                row("Data Lineage", "old-b", PLAN_DEFERRED_STATUS),
            ],
            [
                (2, [row("Error-Path Walk", "new-a", "spawn")]),
                (3, [row("Data Lineage", "new-b", "spawn")]),
            ],
        )
        effective, errors = roster_rows(text)
        self.assertEqual([], errors)
        self.assertEqual(["spawn", "spawn"], [item["status"] for item in effective])

    def assert_plan_error(self, text: str, fragment: str) -> None:
        _, errors = roster_rows(text)
        self.assertTrue(errors, "expected plan continuation error")
        self.assertIn(fragment, "\n".join(errors))

    def test_rejects_wrong_columns(self) -> None:
        text = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)], [])
        text += (
            "\n## Round-two residue continuation — PLAN attempt 2\n\n"
            "| roster entry | status | scope | tier | batch | subagent | outcome |\n"
            f"{SEPARATOR}\n"
            "| Error-Path Walk | spawn | new | frontier | D01 | — | — |\n"
        )
        self.assert_plan_error(text, "must have exactly the ordered columns")

    def test_rejects_noncanonical_heading(self) -> None:
        text = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)], [])
        text += (
            "\n## Round-two residue continuation - PLAN attempt 2\n\n"
            f"{COLUMNS}\n{SEPARATOR}\n"
            f"{row('Error-Path Walk', 'new', 'spawn')}\n"
        )
        self.assert_plan_error(text, "non-canonical plan continuation heading")

    def test_rejects_duplicate_and_non_increasing_attempts(self) -> None:
        text = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)],
            [
                (3, [row("Error-Path Walk", "new", "spawn")]),
                (2, [row("Data Lineage", "new", "spawn")]),
                (2, [row("Data Lineage", "newer", "spawn")]),
            ],
        )
        self.assert_plan_error(text, "duplicate PLAN continuation attempt")
        self.assert_plan_error(text, "not strictly increasing")

    def test_rejects_duplicate_shard_target(self) -> None:
        text = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)],
            [(2, [
                row("Error-Path Walk (shard 1: a)", "a", "spawn"),
                row("Error-Path Walk (shard 1: b)", "b", "spawn"),
            ])],
        )
        self.assert_plan_error(text, "duplicates transition target")

    def test_rejects_mixed_sharded_and_unsharded_rows(self) -> None:
        text = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)],
            [(2, [
                row("Error-Path Walk", "whole", "spawn"),
                row("Error-Path Walk (shard 1: a)", "a", "spawn"),
            ])],
        )
        self.assert_plan_error(text, "mixes sharded and unsharded")

    def test_rejects_unknown_non_deferred_and_repeated_targets(self) -> None:
        unknown = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)],
            [(2, [row("Data Lineage", "new", "spawn")])],
        )
        self.assert_plan_error(unknown, "resolves ambiguously")

        non_deferred = plan(
            [row("Error-Path Walk", "old", "spawn")],
            [(2, [row("Error-Path Walk", "new", "spawn")])],
        )
        self.assert_plan_error(non_deferred, "is not an earlier deferred row")

        repeated = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)],
            [
                (2, [row("Error-Path Walk", "new", "spawn")]),
                (3, [row("Error-Path Walk", "newer", "spawn")]),
            ],
        )
        self.assert_plan_error(repeated, "is not an earlier deferred row")

    def test_rejects_non_spawn_continuation_status(self) -> None:
        text = plan(
            [row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)],
            [(2, [row("Error-Path Walk", "new", "unreviewed — stopped")])],
        )
        self.assert_plan_error(text, "expected 'spawn'")

    def test_plan_repair_corrects_not_applicable_proof(self) -> None:
        old = "not applicable — trigger absence proved by T004"
        new = "not applicable — trigger absence proved by T024"
        text = repair(
            plan([row("Teardown Order", "—", old, "—")], []),
            2,
            [repair_row("Teardown Order", old, "—", new, "—", "D01", "T024")],
        )
        effective, errors = roster_rows(text)
        self.assertEqual([], errors)
        self.assertEqual(new, effective[0]["status"])
        self.assertEqual("—", effective[0]["scope"])

    def test_plan_repair_transitions_not_applicable_to_spawn(self) -> None:
        old = "not applicable — trigger absence proved by T004"
        text = plan([row("Callback And Task Lifetime", "—", old, "—")], [])
        parsed, errors = effective_tables(text, "raw-plan.md")
        base = next(rows for _, header, rows in parsed if tuple(header) == (
            "roster entry", "scope", "status", "tier", "batch", "subagent",
            "outcome",
        ))
        base[0]["subagent"] = "task-old"
        base[0]["outcome"] = "historical"
        text = text.replace("| D01 | — | — |", "| D01 | task-old | historical |")
        text = repair(text, 2, [repair_row(
            "Callback And Task Lifetime", old,
            "T001,T003 positive callback/lifetime scope", "spawn", "frontier",
            "D06", "T001,T003",
        )])
        effective, errors = roster_rows(text)
        self.assertEqual([], errors)
        self.assertEqual("spawn", effective[0]["status"])
        self.assertEqual("frontier", effective[0]["tier"])
        self.assertEqual("task-old", effective[0]["subagent"])
        self.assertEqual("historical", effective[0]["outcome"])

    def test_plan_repair_rejects_deferred_target(self) -> None:
        text = repair(
            plan([row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS)], []),
            2,
            [repair_row(
                "Error-Path Walk", PLAN_DEFERRED_STATUS, "new", "spawn",
                "frontier", "D02",
            )],
        )
        self.assert_plan_error(text, "use the round-two residue continuation")

    def test_plan_repair_rejects_stale_or_duplicate_target(self) -> None:
        old = "not applicable — trigger absence proved by T004"
        text = repair(
            plan([row("Teardown Order", "—", old, "—")], []),
            2,
            [
                repair_row("Teardown Order", "wrong", "—", old, "—", "D01"),
                repair_row("Teardown Order", old, "new", "spawn", "frontier", "D02"),
            ],
        )
        self.assert_plan_error(text, "duplicates target Teardown Order")
        self.assert_plan_error(text, "expected status 'wrong'")

    def test_plan_repair_rejects_unknown_target_and_wrong_columns(self) -> None:
        old = "not applicable — trigger absence proved by T004"
        unknown = repair(
            plan([row("Teardown Order", "—", old, "—")], []),
            2,
            [repair_row("Unknown", old, "new", "spawn", "frontier", "D02")],
        )
        self.assert_plan_error(unknown, "resolves to 0 rows")
        wrong = plan([row("Teardown Order", "—", old, "—")], []) + (
            "\n## Plan repair continuation — PLAN attempt 2\n\n"
            f"{COLUMNS}\n{SEPARATOR}\n{row('Teardown Order', 'new', 'spawn')}\n"
        )
        self.assert_plan_error(wrong, "must have exactly the ordered columns")

    def test_plan_repair_rejects_invalid_transition_and_field_changes(self) -> None:
        old = "not applicable — trigger absence proved by T004"
        invalid = repair(
            plan([row("Teardown Order", "—", old, "—")], []),
            2,
            [repair_row("Teardown Order", old, "changed", "unreviewed", "—", "D01", "—")],
        )
        self.assert_plan_error(invalid, "must be spawn or an exact not-applicable proof")
        self.assert_plan_error(invalid, "lacks evidence")

        new = "not applicable — trigger absence proved by T024"
        changed = repair(
            plan([row("Teardown Order", "—", old, "—")], []),
            2,
            [repair_row("Teardown Order", old, "changed", new, "—", "D01", "T024")],
        )
        self.assert_plan_error(changed, "must preserve scope")

    def test_plan_repair_heading_attempts_share_continuation_order(self) -> None:
        old = "not applicable — trigger absence proved by T004"
        text = plan(
            [
                row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS),
                row("Teardown Order", "—", old, "—"),
            ],
            [(3, [row("Error-Path Walk", "new", "spawn")])],
        )
        text = repair(text, 2, [repair_row(
            "Teardown Order", old, "—",
            "not applicable — trigger absence proved by T024", "—", "D01", "T024",
        )])
        self.assert_plan_error(text, "not strictly increasing")

        duplicate = plan(
            [
                row("Error-Path Walk", "old", PLAN_DEFERRED_STATUS),
                row("Teardown Order", "—", old, "—"),
            ],
            [(2, [row("Error-Path Walk", "new", "spawn")])],
        )
        duplicate = repair(duplicate, 2, [repair_row(
            "Teardown Order", old, "—",
            "not applicable — trigger absence proved by T024", "—", "D01", "T024",
        )])
        self.assert_plan_error(duplicate, "duplicate PLAN continuation attempt")

    def test_rejects_noncanonical_plan_repair_heading(self) -> None:
        old = "not applicable — trigger absence proved by T004"
        text = plan([row("Teardown Order", "—", old, "—")], []) + (
            "\n## Plan repair continuation - PLAN attempt 2\n\n"
            f"{REPAIR_COLUMNS}\n{REPAIR_SEPARATOR}\n"
            f"{repair_row('Teardown Order', old, '—', old, '—', 'D01')}\n"
        )
        self.assert_plan_error(text, "non-canonical plan continuation heading")


if __name__ == "__main__":
    unittest.main()
