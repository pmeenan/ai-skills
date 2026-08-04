#!/usr/bin/env python3
"""Validate one worker artifact before its orchestration attempt is collected."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from artifact_tables import (
    PLAN_DEFERRED_STATUS,
    PLAN_ROSTER_COLUMNS,
    effective_tables,
    plan_row_identity,
)


ROW_ID = re.compile(r"^(?:[A-Z][A-Z0-9]*-\d+|R\d+-RC\d+-\d+)$")
CITATION = re.compile(r"(?:^|[\s`(\[])([A-Za-z0-9_.+@{}\-/]+):\d+")
EVIDENCE_EXCEPTION = re.compile(r"evidence-exception:\s*\S+")
ARTIFACT_POINTER = re.compile(
    r"(?:^|\s|`)([A-Za-z0-9_.+@{}\-/]+\.(?:json|md):/"
    r"[A-Za-z0-9_./~-]+)"
)
ROOT_FAMILY = re.compile(r"^RF\d{3,}$")
OBLIGATIONS = {
    "local-proof",
    "base-contract",
    "caller-reachability",
    "callee/backend-implementation",
    "async-operation-owner",
    "destruction/cancellation",
    "platform-branches",
    "style-authority",
}
CLASS_OBLIGATIONS = {
    "general": set(),
    "contract": {
        "base-contract", "caller-reachability",
        "callee/backend-implementation",
    },
    "async-lifetime": {
        "callee/backend-implementation", "async-operation-owner",
        "destruction/cancellation", "platform-branches",
    },
    "style-convention": {"style-authority"},
    "state-protocol": {
        "base-contract", "caller-reachability",
        "callee/backend-implementation",
    },
    "platform": {"platform-branches"},
}
DESCRIPTOR_COLUMNS = {
    "candidate", "classes", "obligations", "base / interface",
    "invariant owner", "violated invariant", "state / transition",
    "proposed fix layer", "related symbols",
}
AFFINITY_COLUMNS = DESCRIPTOR_COLUMNS - {"classes", "obligations"}
TRACE_RESULTS = {
    "PROVES CANDIDATE", "REFUTES CANDIDATE", "NEUTRAL", "OPEN",
}
CONSISTENCY_CHECKS = {
    "contradictory assumptions",
    "invariant-owner collisions",
    "style-authority scope",
    "lifetime operation owner",
    "reachability termination",
    "repeated local fixes",
}
PLAN_NOT_APPLICABLE = re.compile(
    r"not applicable\s+—\s+trigger absence proved by\s+"
    r"(?:T\d+|I[A-Z0-9]+-T\d+)"
    r"(?:\s*,\s*(?:T\d+|I[A-Z0-9]+-T\d+))*",
    re.IGNORECASE,
)
PLAN_UNREVIEWED = re.compile(r"unreviewed\s+—\s+\S.*", re.IGNORECASE)
SPECIALIST_LENSES = {
    "Threading And Synchronization",
    "Ownership And Blink Lifecycle",
    "Mojo IPC Authorization And Sandbox",
    "Performance And Resource Scaling",
    "Platform And Language Semantics",
    "Build API And Generated Assets",
    "Privacy And Telemetry",
    "Accessibility And Internationalization",
    "Network Semantics",
    "Fuzzing And Test Strategy",
}


def tokens(value: str) -> set[str]:
    return {
        token.strip().lower()
        for token in re.split(r"[,;]", value)
        if token.strip()
    }


def descriptor_check(
    parsed: list[tuple[str, list[str], list[dict[str, str]]]],
    artifact: Path,
) -> None:
    candidates: set[str] = set()
    descriptors: dict[str, dict[str, str]] = {}
    found_descriptor_table = False
    for heading, header, rows in parsed:
        if heading == "Candidate rows":
            for row in rows:
                status = row.get("status", "").lower()
                if "candidate" in status or "reopened" in status:
                    candidates.add(row.get("id", "").strip())
        if heading == "Candidate descriptors":
            found_descriptor_table = True
            if not DESCRIPTOR_COLUMNS.issubset(header):
                fail(f"{artifact} Candidate descriptors table has wrong columns")
            for row in rows:
                candidate = row.get("candidate", "").strip()
                if candidate in descriptors:
                    fail(
                        f"{artifact} duplicates Candidate descriptors for "
                        f"{candidate}"
                    )
                descriptors[candidate] = row
    if candidates and not found_descriptor_table:
        fail(f"{artifact} lacks exact 'Candidate descriptors' heading")
    if set(descriptors) - candidates:
        fail(
            f"{artifact} has descriptors for non-candidates: "
            + ", ".join(sorted(set(descriptors) - candidates))
        )
    for candidate in sorted(candidates):
        row = descriptors.get(candidate)
        if row is None:
            fail(f"{artifact} candidate {candidate} has no descriptor row")
        classes = tokens(row.get("classes", ""))
        obligations = tokens(row.get("obligations", ""))
        unknown_classes = classes - set(CLASS_OBLIGATIONS)
        unknown_obligations = obligations - OBLIGATIONS
        if not classes or unknown_classes:
            fail(
                f"{artifact} candidate {candidate} has invalid classes: "
                f"{', '.join(sorted(unknown_classes)) or '(blank)'}"
            )
        if not obligations or unknown_obligations:
            fail(
                f"{artifact} candidate {candidate} has invalid obligations: "
                f"{', '.join(sorted(unknown_obligations)) or '(blank)'}"
            )
        required = set().union(*(CLASS_OBLIGATIONS[item] for item in classes))
        missing = required - obligations
        if missing:
            fail(
                f"{artifact} candidate {candidate} lacks class-required "
                f"obligations: {', '.join(sorted(missing))}"
            )
        for field in DESCRIPTOR_COLUMNS - {"candidate", "classes", "obligations"}:
            value = row.get(field, "").strip()
            if not value or value.lower() in {"-", "unknown", "n/a"}:
                fail(
                    f"{artifact} candidate {candidate} has unresolved "
                    f"descriptor '{field}'; use 'unknown — reason' when the "
                    "answer is genuinely not known yet"
                )


def fail(message: str) -> None:
    print(f"validate-worker-artifact.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def inventory_check(root: Path, artifact: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="inventory-artifact-check.") as temporary:
        isolated = Path(temporary)
        profile = root / "profile.json"
        if profile.is_file():
            shutil.copy2(profile, isolated / "profile.json")
        if artifact.name == "inventory.md" and artifact.parent == root:
            destination = isolated / "inventory.md"
        else:
            destination = isolated / "inventory" / artifact.name
            destination.parent.mkdir()
        shutil.copy2(artifact, destination)
        builder = Path(__file__).with_name("build-review-indexes.py")
        result = subprocess.run(
            [sys.executable, str(builder), str(isolated)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            fail(result.stderr.strip() or result.stdout.strip())


def ledger_check(parsed: list[tuple[str, list[str], list[dict[str, str]]]],
                 artifact: Path) -> None:
    headings = {heading for heading, _, _ in parsed}
    if artifact.name != "PR.md" and "reopened" not in artifact.parts:
        for required in ("Compliance matrix", "Candidate rows"):
            if required not in headings:
                fail(f"{artifact} lacks exact '{required}' heading")
    for heading, header, rows in parsed:
        if heading == "Compliance matrix":
            if not {"question", "answer", "evidence"}.issubset(header):
                fail(f"{artifact} compliance matrix has wrong columns")
            for index, row in enumerate(rows, 1):
                answer = row.get("answer", "").strip()
                evidence = row.get("evidence", "").strip()
                if not answer or not evidence:
                    fail(
                        f"{artifact} compliance matrix row {index} has a blank "
                        "answer/evidence"
                    )
                if re.fullmatch(
                    r"(?i)(yes|pass|clean|safe)(?:\s*[—-].*)?", answer
                ) and not CITATION.search(evidence):
                    fail(
                        f"{artifact} compliance matrix row {index} is a "
                        "citation-free PASS"
                    )
                if answer.upper().startswith("N/A") and not re.search(
                    r"[—:-]\s*\S", answer
                ):
                    fail(
                        f"{artifact} compliance matrix row {index} has N/A "
                        "without a reason"
                    )
        if heading in {"Candidate rows", "Prior-feedback rows"}:
            if "id" not in header:
                fail(f"{artifact} {heading} table has no id column")
            for row in rows:
                identifier = row.get("id", "").strip()
                if identifier and ROW_ID.fullmatch(identifier) is None:
                    fail(f"{artifact} has invalid row ID '{identifier}'")
    if re.fullmatch(r"(?:GSS|GAI)\d*", artifact.stem.upper()):
        assessment_tables = [
            (header, rows) for heading, header, rows in parsed
            if heading == "Specialist escalation assessments"
        ]
        if len(assessment_tables) != 1:
            fail(
                f"{artifact} must have exactly one "
                "'Specialist escalation assessments' table"
            )
        header, rows = assessment_tables[0]
        required = {
            "lens", "graph scope", "likelihood", "signals",
            "counterevidence",
        }
        if not required.issubset(header):
            fail(f"{artifact} specialist assessment table has wrong columns")
        by_lens: dict[str, dict[str, str]] = {}
        for row in rows:
            lens = row.get("lens", "").strip()
            if lens in by_lens:
                fail(f"{artifact} duplicates specialist assessment for {lens}")
            by_lens[lens] = row
        missing = SPECIALIST_LENSES - set(by_lens)
        unknown = set(by_lens) - SPECIALIST_LENSES
        if missing or unknown:
            fail(
                f"{artifact} specialist assessments have missing/unknown lenses: "
                f"missing={','.join(sorted(missing)) or '-'}; "
                f"unknown={','.join(sorted(unknown)) or '-'}"
            )
        graph_scopes = {
            row.get("graph scope", "").strip().upper()
            for row in by_lens.values()
        }
        if len(graph_scopes) != 1:
            fail(
                f"{artifact} specialist assessments must share one exact "
                "assigned graph scope"
            )
        for lens, row in by_lens.items():
            likelihood = row.get("likelihood", "").strip().lower()
            signals = row.get("signals", "").strip()
            counterevidence = row.get("counterevidence", "").strip()
            if likelihood not in {"low", "medium", "high"}:
                fail(f"{artifact} {lens} must use low, medium, or high")
            graph_scope = row.get("graph scope", "").strip()
            empty_scope = graph_scope.lower() == "graph:none"
            if not empty_scope and not re.fullmatch(
                r"(?i)graph:(?:E-[A-Z0-9-]+)(?:,E-[A-Z0-9-]+)*",
                graph_scope,
            ):
                fail(f"{artifact} {lens} has invalid exact graph scope")
            if not signals or not counterevidence or not (
                CITATION.search(f"{signals} {counterevidence}")
                or ARTIFACT_POINTER.search(f"{signals} {counterevidence}")
                or re.search(r"\bE-[A-Z0-9-]+\b", f"{signals} {counterevidence}")
            ):
                fail(f"{artifact} {lens} lacks cited signals/counterevidence")
            if likelihood == "low" and not (
                CITATION.search(counterevidence)
                or ARTIFACT_POINTER.search(counterevidence)
                or re.search(r"\bE-[A-Z0-9-]+\b", counterevidence)
            ):
                fail(f"{artifact} {lens} low likelihood lacks cited counterevidence")
            if likelihood in {"medium", "high"} and not (
                CITATION.search(signals)
                or ARTIFACT_POINTER.search(signals)
                or re.search(r"\bE-[A-Z0-9-]+\b", signals)
            ):
                fail(f"{artifact} {lens} likelihood lacks cited positive signals")
            if empty_scope and likelihood != "low":
                fail(
                    f"{artifact} {lens} graph:none assessment must be low; "
                    "a higher likelihood requires an inventory edge"
                )
    probe_tables = [
        (header, rows) for heading, header, rows in parsed
        if heading == "Specialist probe outcome"
    ]
    if probe_tables:
        if len(probe_tables) != 1:
            fail(f"{artifact} has duplicate Specialist probe outcome tables")
        header, rows = probe_tables[0]
        required = {
            "lens", "graph scope", "result", "evidence", "remaining scope",
        }
        if not required.issubset(header) or len(rows) != 1:
            fail(f"{artifact} has malformed Specialist probe outcome")
        row = rows[0]
        result = row.get("result", "").strip().lower()
        evidence = row.get("evidence", "")
        remaining = row.get("remaining scope", "").strip()
        if result not in {"clean", "escalate"}:
            fail(f"{artifact} probe result must be clean or escalate")
        if not (CITATION.search(evidence) or ARTIFACT_POINTER.search(evidence)):
            fail(f"{artifact} probe outcome lacks cited evidence")
        if result == "clean" and remaining not in {"", "-", "—"}:
            fail(f"{artifact} clean probe must have no remaining scope")
        if result == "escalate" and not re.search(
            r"(?i)specialist:full.*graph:(?:E-[A-Z0-9-]+)"
            r"(?:,E-[A-Z0-9-]+)*",
            remaining,
        ):
            fail(f"{artifact} escalated probe lacks full remaining graph scope")
    descriptor_check(parsed, artifact)


def verdict_check(
    root: Path,
    parsed: list[tuple[str, list[str], list[dict[str, str]]]],
    artifact: Path,
) -> None:
    candidate_index = root / "indexes" / "candidates.tsv"
    if not candidate_index.is_file():
        fail(f"{artifact} cannot validate trace closure without {candidate_index}")
    with candidate_index.open(encoding="utf-8", newline="") as source:
        candidates = {
            row["id"]: row
            for row in csv.DictReader(source, delimiter="\t")
        }
    verdicts: dict[str, str] = {}
    closures: dict[str, dict[str, str]] = {}
    affinities: set[str] = set()
    headings = {heading for heading, _, _ in parsed}
    for heading, header, rows in parsed:
        if {"candidate", "verdict"}.issubset(header):
            for row in rows:
                candidate = row.get("candidate", "").strip()
                if candidate:
                    verdicts[candidate] = row.get("verdict", "").strip()
        if heading == "Trace closure":
            if not {
                "candidate", "obligation", "result", "evidence"
            }.issubset(header):
                fail(f"{artifact} Trace closure table has wrong columns")
            for row in rows:
                candidate = row.get("candidate", "").strip()
                obligation = row.get("obligation", "").strip().lower()
                result = row.get("result", "").strip()
                evidence = row.get("evidence", "").strip()
                if obligation not in OBLIGATIONS:
                    fail(
                        f"{artifact} candidate {candidate} has unknown trace "
                        f"obligation '{obligation}'"
                    )
                if obligation in closures.setdefault(candidate, {}):
                    fail(
                        f"{artifact} duplicates trace obligation {obligation} "
                        f"for {candidate}"
                    )
                normalized_result = result.upper()
                if normalized_result not in TRACE_RESULTS and not re.match(
                    r"(?i)^NOT APPLICABLE\s+[—-]\s+\S", result
                ):
                    fail(
                        f"{artifact} candidate {candidate} has invalid trace "
                        f"result '{result}'"
                    )
                if not evidence or (
                    not CITATION.search(evidence)
                    and not EVIDENCE_EXCEPTION.search(evidence)
                ):
                    fail(
                        f"{artifact} candidate {candidate} obligation "
                        f"{obligation} lacks path:line evidence or an "
                        "evidence-exception"
                    )
                closures[candidate][obligation] = normalized_result
        if heading == "Verified affinity":
            if not AFFINITY_COLUMNS.issubset(header):
                fail(f"{artifact} Verified affinity table has wrong columns")
            affinities.update(
                row.get("candidate", "").strip() for row in rows
            )
    for required in ("Trace closure", "Verified affinity"):
        if verdicts and required not in headings:
            fail(f"{artifact} lacks exact '{required}' heading")
    for candidate, verdict in verdicts.items():
        indexed = candidates.get(candidate)
        if indexed is None:
            fail(f"{artifact} verdict targets unknown candidate {candidate}")
        required = tokens(indexed.get("obligations", ""))
        actual = set(closures.get(candidate, {}))
        if actual != required:
            fail(
                f"{artifact} candidate {candidate} trace closure mismatch: "
                f"missing={sorted(required - actual)}, "
                f"foreign={sorted(actual - required)}"
            )
        if candidate not in affinities:
            fail(f"{artifact} candidate {candidate} has no Verified affinity row")
        results = set(closures[candidate].values())
        if verdict == "CONFIRMED" and "PROVES CANDIDATE" not in results:
            fail(
                f"{artifact} CONFIRMED candidate {candidate} has no trace "
                "obligation that PROVES CANDIDATE"
            )
        if verdict == "REFUTED" and "REFUTES CANDIDATE" not in results:
            fail(
                f"{artifact} REFUTED candidate {candidate} has no trace "
                "obligation that REFUTES CANDIDATE"
            )
        if verdict == "UNPROVEN" and "OPEN" not in results:
            fail(
                f"{artifact} UNPROVEN candidate {candidate} has no OPEN "
                "trace obligation"
            )
        if verdict in {"CONFIRMED", "REFUTED"} and "OPEN" in results:
            fail(
                f"{artifact} {verdict} candidate {candidate} still has an "
                "OPEN trace obligation"
            )


def affinity_check(
    root: Path,
    parsed: list[tuple[str, list[str], list[dict[str, str]]]],
    artifact: Path,
) -> None:
    verdict_index = root / "indexes" / "verdicts.tsv"
    if not verdict_index.is_file():
        fail(f"{artifact} cannot validate families without {verdict_index}")
    with verdict_index.open(encoding="utf-8", newline="") as source:
        verdict_rows = list(csv.DictReader(source, delimiter="\t"))
    surviving = {
        row.get("candidate", ""): row.get("id", "")
        for row in verdict_rows
        if row.get("verdict") in {"CONFIRMED", "UNPROVEN"}
    }
    known = {
        value
        for row in verdict_rows
        for value in (row.get("candidate", ""), row.get("id", ""))
        if value
    }
    candidate_index = root / "indexes" / "candidates.tsv"
    if candidate_index.is_file():
        with candidate_index.open(encoding="utf-8", newline="") as source:
            known.update(
                row.get("id", "")
                for row in csv.DictReader(source, delimiter="\t")
                if row.get("id")
            )
    membership: dict[str, str] = {}
    audit: dict[str, int] = {}
    headings = {heading for heading, _, _ in parsed}
    for heading, header, rows in parsed:
        if heading == "Root families":
            required = {
                "root family", "members", "shared invariant",
                "invariant owner", "state / transition", "fix layer",
                "related symbols", "disposition",
            }
            if not required.issubset(header):
                fail(f"{artifact} Root families table has wrong columns")
            for row in rows:
                family = row.get("root family", "").strip()
                if not ROOT_FAMILY.fullmatch(family):
                    fail(f"{artifact} has invalid root family '{family}'")
                members = set(re.findall(ROW_ID.pattern[1:-1], row.get("members", "")))
                if not members:
                    fail(f"{artifact} root family {family} has no members")
                for member in members:
                    if member not in known:
                        fail(
                            f"{artifact} root family {family} has unknown "
                            f"member {member}"
                        )
                    if member in membership:
                        fail(
                            f"{artifact} row {member} belongs to both "
                            f"{membership[member]} and {family}"
                        )
                    membership[member] = family
                for field in required - {"root family", "members"}:
                    if not row.get(field, "").strip():
                        fail(
                            f"{artifact} root family {family} has blank {field}"
                        )
        if heading == "Consistency audit":
            if not {"check", "rows / families", "evidence", "result"}.issubset(
                header
            ):
                fail(f"{artifact} Consistency audit table has wrong columns")
            for row in rows:
                check = row.get("check", "").strip().lower()
                audit[check] = audit.get(check, 0) + 1
                evidence = row.get("evidence", "")
                if check not in CONSISTENCY_CHECKS:
                    fail(f"{artifact} has unknown consistency check '{check}'")
                if not row.get("result", "").strip():
                    fail(f"{artifact} consistency check '{check}' has no result")
                if not (
                    CITATION.search(evidence)
                    or ARTIFACT_POINTER.search(evidence)
                    or EVIDENCE_EXCEPTION.search(evidence)
                ):
                    fail(
                        f"{artifact} consistency check '{check}' lacks "
                        "code/artifact evidence or evidence-exception"
                    )
    for heading in ("Root families", "Consistency audit"):
        if heading not in headings:
            fail(f"{artifact} lacks exact '{heading}' heading")
    for check in sorted(CONSISTENCY_CHECKS):
        if audit.get(check, 0) != 1:
            fail(
                f"{artifact} consistency check '{check}' occurs "
                f"{audit.get(check, 0)} times"
            )
    for candidate, verdict_id in surviving.items():
        if candidate not in membership or verdict_id not in membership:
            fail(
                f"{artifact} surviving candidate/verdict "
                f"{candidate}/{verdict_id} is not fully assigned"
            )
        if membership[candidate] != membership[verdict_id]:
            fail(
                f"{artifact} candidate/verdict {candidate}/{verdict_id} "
                "is split across root families"
            )


def plan_check(
    parsed: list[tuple[str, list[str], list[dict[str, str]]]],
    artifact: Path,
) -> None:
    roster_tables = [
        (header, rows)
        for _, header, rows in parsed
        if "roster entry" in header and "status" in header
    ]
    if len(roster_tables) != 1:
        fail(
            f"{artifact} has {len(roster_tables)} effective roster tables; "
            "expected exactly one"
        )
    header, rows = roster_tables[0]
    if tuple(header) != PLAN_ROSTER_COLUMNS:
        fail(
            f"{artifact} roster must have exactly the ordered columns "
            + " | ".join(PLAN_ROSTER_COLUMNS)
        )
    if not rows:
        fail(f"{artifact} roster has no rows")

    identities: set[tuple[str, int | None]] = set()
    modes: dict[str, set[str]] = {}
    for row in rows:
        entry = row.get("roster entry", "").strip()
        base, shard = plan_row_identity(entry)
        if not base:
            fail(f"{artifact} has a blank roster entry")
        if shard is None and re.search(r"\(shard\b|—\s*shard\b", entry, re.I):
            fail(f"{artifact} has malformed shard label '{entry}'")
        identity = (base, shard)
        if identity in identities:
            fail(
                f"{artifact} duplicates effective plan identity {base}"
                + (f" shard {shard}" if shard is not None else "")
            )
        identities.add(identity)
        modes.setdefault(base, set()).add("sharded" if shard is not None else "unsharded")

        status = row.get("status", "")
        if status in {"spawn", PLAN_DEFERRED_STATUS}:
            continue
        if PLAN_NOT_APPLICABLE.fullmatch(status) or PLAN_UNREVIEWED.fullmatch(status):
            continue
        fail(f"{artifact} plan row '{entry}' has invalid status '{status}'")

    for base, base_modes in modes.items():
        if len(base_modes) > 1:
            fail(
                f"{artifact} mixes sharded and unsharded effective rows for "
                f"{base}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--kind",
        choices=(
            "auto", "inventory", "plan", "ledger", "verdict", "affinity",
            "generic",
        ),
        default="auto",
    )
    arguments = parser.parse_args()
    root = arguments.review_dir.resolve()
    artifact = arguments.artifact.resolve()
    if not root.is_dir():
        fail(f"review directory does not exist: {root}")
    if not artifact.is_file():
        fail(f"artifact does not exist: {artifact}")
    if root not in artifact.parents:
        fail(f"artifact is outside review directory: {artifact}")
    try:
        text = artifact.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        fail(f"cannot read {artifact}: {error}")
    parsed, errors = effective_tables(text, str(artifact))
    if errors:
        fail("; ".join(errors))

    kind = arguments.kind
    relative = artifact.relative_to(root)
    if kind == "auto":
        if relative.as_posix() == "inventory.md" or relative.parts[:1] == ("inventory",):
            kind = "inventory"
        elif relative.as_posix() == "plan.md":
            kind = "plan"
        elif relative.parts[:1] == ("ledger",):
            kind = "ledger"
        elif (
            relative.parts[:1] == ("verification",)
            and re.fullmatch(r"V\d+\.md", artifact.name)
        ):
            kind = "verdict"
        elif relative.as_posix() == "verification/affinity.md":
            kind = "affinity"
        else:
            kind = "generic"
    if kind == "inventory":
        inventory_check(root, artifact)
    elif kind == "plan":
        plan_check(parsed, artifact)
    elif kind == "ledger":
        ledger_check(parsed, artifact)
    elif kind == "verdict":
        verdict_check(root, parsed, artifact)
    elif kind == "affinity":
        affinity_check(root, parsed, artifact)
    print(f"valid {kind}: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
