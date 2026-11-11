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
from pathlib import Path, PurePosixPath

from artifact_tables import (
    PLAN_DEFERRED_STATUS,
    PLAN_ROSTER_COLUMNS,
    effective_tables,
    plan_row_identity,
)
try:
    from report_verifier import WorktreeCorpus, verify_fragment_text
except ImportError:
    WorktreeCorpus = None  # type: ignore[assignment]
    verify_fragment_text = None  # type: ignore[assignment]


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
SUGGESTED_EDIT_FIELD = re.compile(
    r"(?im)^- \*\*Suggested edit:\*\*\s*(applicable|omitted)\s*(?:—|-)\s*"
    r"(\S[^\r\n]*)$"
)
CARD_SUGGESTED_EDIT_FIELD = re.compile(
    r"(?im)^- Suggested edit decision:\s*(applicable|omitted)\s*(?:—|-)\s*"
    r"(\S[^\r\n]*)$"
)
SUGGESTION_TARGET = re.compile(
    r"^replaces\s+([A-Za-z0-9_.+@{}\-/]+):([1-9]\d*)(?:-([1-9]\d*))?$"
)
NON_SPECIFIC_OMISSION = {
    "n/a", "na", "none", "optional", "omitted", "not applicable", "tbd",
    "todo", "unknown", "-", "—",
}
FINDING_REQUIRED_FIELDS = (
    "Claim",
    "Location",
    "Evidence",
    "Severity",
    "Origin",
    "Fix status",
    "Suggested edit",
    "Regression test",
    "Rows",
)
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


PRIOR_FEEDBACK_RESOLUTION_RE = re.compile(
    r"(?i)^(?:"
    r"(?:fixed|partially[- ]fixed|still[- ]open|obsolete|superseded|"
    r"reviewer[- ]decision[- ]pending|not[- ]posted|deferred[- ]accepted)\b"
    r"|deferred\s*\(\s*accepted(?:\b[^)]*)?\)"
    r")"
)
OPEN_PRIOR_FEEDBACK_RE = re.compile(r"(?i)^(?:still[- ]open|partially[- ]fixed)\b")


def ledger_check(parsed: list[tuple[str, list[str], list[dict[str, str]]]],
                 artifact: Path) -> None:
    headings = {heading for heading, _, _ in parsed}
    if artifact.name != "PR.md" and "reopened" not in artifact.parts:
        for required in ("Compliance matrix", "Candidate rows"):
            if required not in headings:
                fail(f"{artifact} lacks exact '{required}' heading")
    non_open_prior_rows: dict[str, str] = {}
    candidate_ids: set[str] = set()
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
                if heading == "Prior-feedback rows" and identifier:
                    resolution = row.get("resolution", "").strip()
                    if "resolution" in header and not PRIOR_FEEDBACK_RESOLUTION_RE.search(
                        resolution
                    ):
                        fail(
                            f"{artifact} prior-feedback row {identifier} has "
                            f"unrecognized resolution '{resolution}'"
                        )
                    if resolution and not OPEN_PRIOR_FEEDBACK_RE.search(resolution):
                        non_open_prior_rows[identifier] = resolution
                elif (
                    heading == "Candidate rows"
                    and identifier
                    and "candidate" in row.get("status", "").lower()
                ):
                    candidate_ids.add(identifier)
    for identifier in sorted(candidate_ids & set(non_open_prior_rows)):
        fail(
            f"{artifact} prior-feedback row {identifier} has non-open "
            f"resolution '{non_open_prior_rows[identifier]}' and must not "
            "appear as an active candidate row"
        )
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
        for lens, row in by_lens.items():
            likelihood = row.get("likelihood", "").strip().lower()
            signals = row.get("signals", "").strip()
            counterevidence = row.get("counterevidence", "").strip()
            if likelihood not in {"low", "medium", "high"}:
                fail(f"{artifact} {lens} must use low, medium, or high")
            graph_scope = row.get("graph scope", "").strip()
            empty_scope = graph_scope.lower() == "graph:none"
            all_edges_scope = (
                graph_scope.lower() == "graph:all-inventory-edges"
                and artifact.stem.upper() in {"GSS", "GAI"}
            )
            if not empty_scope and not all_edges_scope and not re.fullmatch(
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


def reconciliation_check(
    text: str,
    parsed: list[tuple[str, list[str], list[dict[str, str]]]],
    artifact: Path,
) -> None:
    disp_tables = [
        (header, rows)
        for _, header, rows in parsed
        if {"row", "thread", "disposition"}.issubset(header)
    ]
    if not disp_tables:
        fail(f"{artifact} lacks a '| row | thread | disposition |' table")
    gate_parts = re.split(r"(?im)^## Pre-output gate\s*$", text, maxsplit=1)
    if len(gate_parts) != 2:
        fail(f"{artifact} lacks '## Pre-output gate' section")
    answers: dict[int, str] = {}
    for line in gate_parts[1].splitlines():
        match = re.match(r"^(\d+)\.\s+(?:\*\*[^*]+:\*\*|[^*:]+:)\s*(.*)$", line)
        if match:
            answers[int(match.group(1))] = match.group(2).strip()
    for number in range(1, 14):
        if number not in answers or not answers[number]:
            fail(f"{artifact} pre-output gate lacks non-empty item {number}")


def report_fragment_check(
    root: Path,
    text: str,
    artifact: Path,
    is_gerrit: bool,
) -> None:
    # Self-review output is never posted to Gerrit; skip prose/quote nitpicks.
    self_review = any(
        (root / name).is_file() and re.search(
            r"(?im)^-\s*Self-review:\s*(?:yes|true|1)\b",
            (root / name).read_text(encoding="utf-8", errors="replace"),
        )
        for name in ("pin.md", "directives.md", "draft-review.md")
    )
    if (not self_review and WorktreeCorpus is not None
            and verify_fragment_text is not None):
        corpus = WorktreeCorpus.load(root)
        errors = verify_fragment_text(
            corpus,
            artifact.relative_to(root).as_posix(),
            text,
            is_gerrit=is_gerrit,
        )
        if errors:
            fail("; ".join(errors))
    if not is_gerrit:
        draft_fragment_structure_check(root, text, artifact)


def fenced_blocks(text: str, info: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines()
    cursor = 0
    while cursor < len(lines):
        opening = re.fullmatch(
            rf"([ ]{{0,3}})```{re.escape(info)}\s*", lines[cursor]
        )
        if opening is None:
            cursor += 1
            continue
        indent = opening.group(1)
        content: list[str] = []
        cursor += 1
        while cursor < len(lines):
            if re.fullmatch(rf"{re.escape(indent)}```\s*", lines[cursor]):
                blocks.append(
                    "\n".join(
                        value[len(indent):]
                        if value.startswith(indent) else value
                        for value in content
                    )
                )
                break
            content.append(lines[cursor])
            cursor += 1
        cursor += 1
    return blocks


def fenced_field(text: str, label: str, info: str = "") -> str | None:
    lines = text.splitlines()
    heading = re.compile(rf"^[ \t]*-\s*{re.escape(label)}:\s*$")
    for index, line in enumerate(lines):
        if heading.match(line) is None:
            continue
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines):
            return None
        opening = re.fullmatch(
            r"([ ]{0,6})```([A-Za-z0-9_+.-]*)[ \t]*", lines[cursor]
        )
        if opening is None:
            return None
        if info and opening.group(2) != info:
            return None
        indent = opening.group(1)
        content: list[str] = []
        cursor += 1
        while cursor < len(lines):
            if re.fullmatch(rf"{re.escape(indent)}```[ \t]*", lines[cursor]):
                return "\n".join(
                    value[len(indent):]
                    if value.startswith(indent) else value
                    for value in content
                )
            content.append(lines[cursor])
            cursor += 1
        return None
    return None


def pin_field(pin_text: str, name: str) -> str | None:
    match = re.search(rf"^- {re.escape(name)}:\s*(.+?)\s*$", pin_text, re.M)
    return match.group(1) if match else None


def verify_suggestion_against_worktree(
    root: Path,
    label: str,
    detail: str,
    selected: str | None,
    replacement: str | None,
    require_selected: bool = True,
) -> None:
    target = SUGGESTION_TARGET.fullmatch(detail)
    if target is None:
        fail(
            f"{label} has malformed applicable Suggested edit target "
            f"'{detail}'; expected 'replaces path:start-end'"
        )
    repo_path = target.group(1)
    pure_path = PurePosixPath(repo_path)
    if (
        pure_path.is_absolute()
        or ".." in pure_path.parts
        or not pure_path.parts
        or pure_path.as_posix() != repo_path
    ):
        fail(
            f"{label} Suggested edit target '{repo_path}' is not a normalized "
            "repo-relative path"
        )
    start = int(target.group(2))
    end = int(target.group(3) or start)
    target_text = f"{repo_path}:{start}" + (f"-{end}" if target.group(3) else "")
    if end < start:
        fail(f"{label} Suggested edit target range {target_text} is reversed")
    if end - start + 1 > 10:
        fail(
            f"{label} Suggested edit selects {end - start + 1} lines; "
            "maximum is 10"
        )
    if require_selected and selected is None:
        fail(f"{label} applicable Suggested edit lacks selected lines")
    if replacement is None:
        fail(f"{label} applicable Suggested edit lacks a suggestion block")
    replacement_lines = replacement.rstrip("\r\n").splitlines()
    if len(replacement_lines) > 20:
        fail(
            f"{label} Suggested edit has {len(replacement_lines)} replacement "
            "lines; maximum is 20"
        )
    if any(
        line.strip().lower()
        in {"...", "…", "<replacement>", "<code>", "placeholder"}
        for line in replacement_lines
    ):
        fail(f"{label} Suggested edit contains a placeholder or elision")

    pin_path = root / "pin.md"
    if not pin_path.is_file():
        return
    try:
        pin = pin_path.read_text(encoding="utf-8")
    except OSError:
        return
    changed: set[str] = set()
    in_files = False
    for line in pin.splitlines():
        if line.startswith("- Files changed"):
            in_files = True
            continue
        if in_files:
            match = re.match(
                r"^  - (.*?)(?: \[[A-Z?]+; \+[0-9?]+/-[0-9?]+\])?$",
                line,
            )
            if match:
                changed.add(match.group(1))
            elif line.strip():
                in_files = False
    if changed and repo_path not in changed:
        fail(
            f"{label} Suggested edit targets unchanged or unknown file "
            f"{repo_path}"
        )
    worktree_value = pin_field(pin, "Worktree")
    revision = pin_field(pin, "Revision SHA")
    parent = pin_field(pin, "Parent SHA")
    if not worktree_value or not revision or not parent:
        return
    worktree = Path(worktree_value.split(" (", 1)[0])
    if not worktree.is_dir():
        return
    inside = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if inside.returncode != 0:
        return
    try:
        source = subprocess.run(
            ["git", "-C", str(worktree), "show", f"{revision}:{repo_path}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.decode("utf-8")
        diff = subprocess.run(
            [
                "git", "-C", str(worktree), "diff", "--unified=0",
                parent, revision, "--", repo_path,
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (subprocess.CalledProcessError, UnicodeDecodeError):
        return
    source_lines = source.splitlines()
    if end > len(source_lines):
        fail(
            f"{label} Suggested edit range {target_text} is outside the "
            f"pinned file's {len(source_lines)} lines"
        )
    actual_selected = "\n".join(source_lines[start - 1:end])
    if require_selected and selected != actual_selected:
        fail(
            f"{label} Suggested edit selected lines do not match the pinned "
            f"changed-side range {target_text}"
        )
    changed_new_lines: set[int] = set()
    for hunk in re.finditer(
        r"(?m)^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff
    ):
        hunk_start = int(hunk.group(1))
        hunk_count = int(hunk.group(2) or "1")
        changed_new_lines.update(range(hunk_start, hunk_start + hunk_count))
    if not changed_new_lines.intersection(range(start, end + 1)):
        fail(
            f"{label} Suggested edit range {target_text} does not intersect "
            "a changed-side hunk in the pinned patch"
        )


def root_cause_check(
    root: Path,
    text: str,
    parsed: list[tuple[str, list[str], list[dict[str, str]]]],
    artifact: Path,
) -> None:
    decisions: dict[str, dict[str, str]] = {}
    amendment_ids: set[str] = set()
    matches = list(re.finditer(r"(?m)^## (RC\d+-\d+)\b[^\r\n]*$", text))
    for match in matches:
        identifier = match.group(1)
        next_heading = re.search(r"(?m)^## (?!#)[^\r\n]+$", text[match.end():])
        end = (
            match.end() + next_heading.start()
            if next_heading is not None else len(text)
        )
        section = text[match.end():end]
        family_match = re.search(
            r"(?im)^- Root family:[ \t]*(\S[^\r\n]*)$", section
        )
        decision_match = re.search(
            r"(?im)^- Suggested-edit decision:\s*"
            r"(applicable|omitted)\s*(?:—|-)\s*(\S[^\r\n]*)$",
            section,
        )
        if decision_match is None:
            continue
        if identifier in decisions:
            fail(
                f"{artifact} root-cause Suggested edit decision {identifier} "
                "is defined more than once"
            )
        status = decision_match.group(1).lower()
        detail = decision_match.group(2).strip()
        selected = fenced_field(section, "Suggested-edit selected lines")
        replacement = fenced_field(
            section, "Suggested-edit replacement", "suggestion"
        )
        if family_match is None:
            fail(
                f"{artifact} root-cause row {identifier} with a Suggested edit "
                "decision lacks an exact Root family field"
            )
        family = family_match.group(1).strip()
        if not re.fullmatch(r"RF\d{3,}", family):
            if status != "omitted":
                fail(
                    f"{artifact} root-cause row {identifier} cannot own an "
                    "applicable family decision without an exact RF identity"
                )
            elif detail.lower() in NON_SPECIFIC_OMISSION:
                fail(
                    f"{artifact} root-cause row {identifier} has a "
                    "non-specific Suggested edit omission reason"
                )
            elif selected is not None or replacement is not None:
                fail(
                    f"{artifact} root-cause row {identifier} marks Suggested "
                    "edit omitted but contains selected/replacement fences"
                )
            continue
        decisions[identifier] = {
            "family": family,
            "status": status,
            "detail": detail,
            "selected": selected or "",
            "replacement": replacement or "",
            "has_selected": "yes" if selected is not None else "no",
            "has_replacement": "yes" if replacement is not None else "no",
        }
    amendment_headings = list(re.finditer(
        r"(?m)^## Suggested-edit amendments\s*$", text
    ))
    for amendment_heading in amendment_headings:
        amendment_end = re.search(
            r"(?m)^## (?!#)[^\r\n]+$", text[amendment_heading.end():]
        )
        amendment_text = text[
            amendment_heading.end():
            amendment_heading.end() + amendment_end.start()
            if amendment_end is not None else len(text)
        ]
        amendment_matches = list(re.finditer(
            r"(?m)^### (RC\d+-SA\d+)\s*$", amendment_text
        ))
        if not amendment_matches:
            fail(
                f"{artifact}: Suggested-edit amendments section has no "
                "RC<batch>-SA<n> entries"
            )
        for position, amendment_match in enumerate(amendment_matches):
            amendment_id = amendment_match.group(1)
            end = (
                amendment_matches[position + 1].start()
                if position + 1 < len(amendment_matches)
                else len(amendment_text)
            )
            section = amendment_text[amendment_match.end():end]
            if amendment_id in amendment_ids:
                fail(
                    f"{artifact} Suggested edit amendment {amendment_id} is "
                    "defined more than once"
                )
            amendment_ids.add(amendment_id)
            if amendment_id.split("-", 1)[0] != artifact.stem:
                fail(
                    f"{artifact} Suggested edit amendment {amendment_id} does "
                    f"not match file prefix {artifact.stem}"
                )
            target_match = re.search(
                r"(?im)^- Target:[ \t]*(RC\d+-\d+)\s*$", section
            )
            decision_match = re.search(
                r"(?im)^- Suggested-edit decision:\s*"
                r"(applicable|omitted)\s*(?:—|-)\s*(\S[^\r\n]*)$",
                section,
            )
            evidence_match = re.search(
                r"(?im)^- Evidence:[ \t]*(\S[^\r\n]*)$", section
            )
            attempt_match = re.search(
                r"(?im)^- Attempt:[ \t]*([1-9]\d*)\s*$", section
            )
            if not all((target_match, decision_match, evidence_match,
                        attempt_match)):
                fail(
                    f"{artifact} Suggested edit amendment {amendment_id} "
                    "requires Target, Suggested-edit decision, Evidence, and "
                    "positive Attempt fields"
                )
            target_id = target_match.group(1)
            if target_id not in decisions:
                fail(
                    f"{artifact} Suggested edit amendment {amendment_id} "
                    f"targets unknown row {target_id}"
                )
            status = decision_match.group(1).lower()
            detail = decision_match.group(2).strip()
            selected = fenced_field(section, "Suggested-edit selected lines")
            replacement = fenced_field(
                section, "Suggested-edit replacement", "suggestion"
            )
            decisions[target_id].update({
                "status": status,
                "detail": detail,
                "selected": selected or "",
                "replacement": replacement or "",
                "has_selected": "yes" if selected is not None else "no",
                "has_replacement": "yes" if replacement is not None else "no",
            })

    for identifier, dec in sorted(decisions.items()):
        status = dec["status"]
        detail = dec["detail"]
        if status == "applicable":
            verify_suggestion_against_worktree(
                root,
                f"{artifact} row {identifier}",
                detail,
                dec["selected"] if dec["has_selected"] == "yes" else None,
                dec["replacement"] if dec["has_replacement"] == "yes" else None,
                require_selected=True,
            )
        else:
            if detail.lower() in NON_SPECIFIC_OMISSION:
                fail(
                    f"{artifact} root-cause row {identifier} has a "
                    "non-specific Suggested edit omission reason"
                )
            if dec["has_selected"] == "yes" or dec["has_replacement"] == "yes":
                fail(
                    f"{artifact} root-cause row {identifier} marks Suggested "
                    "edit omitted but contains selected/replacement fences"
                )

    for heading, header, rows in parsed:
        if heading != "Root-family analysis":
            continue
        required_columns = {
            "root family", "members", "shared invariant",
            "invariant owner", "state / transition", "method coverage",
            "excluded nearby", "fix layer", "comment count",
            "suggested edit", "evidence",
        }
        if not required_columns.issubset(header):
            fail(f"{artifact} Root-family analysis has wrong columns")
        for row in rows:
            family = row.get("root family", "").strip()
            if not re.fullmatch(r"RF\d{3,}", family):
                continue
            for col in required_columns - {"root family"}:
                if not row.get(col, "").strip():
                    fail(
                        f"{artifact} root family {family} has blank {col}"
                    )
            choice = row.get("suggested edit", "").strip()
            if not re.match(
                r"(?i)^(?:applicable|omitted)\s*(?:—|-)\s*\S", choice
            ):
                fail(
                    f"{artifact} root family {family} has malformed "
                    "Suggested edit decision"
                )
            members = {
                key: val for key, val in decisions.items()
                if val["family"] == family
            }
            app_match = re.fullmatch(r"applicable\s*(?:—|-)\s*(RC\d+-\d+)", choice)
            if app_match:
                rc_id = app_match.group(1)
                if rc_id not in members or members[rc_id]["status"] != "applicable":
                    fail(
                        f"{artifact} root family {family} names absent or "
                        f"non-applicable RC decision {rc_id}"
                    )
            else:
                matches_omitted = [
                    key for key, val in members.items()
                    if val["status"] == "omitted"
                    and choice == f"omitted — {val['detail']}"
                ]
                if not matches_omitted:
                    fail(
                        f"{artifact} root family {family} Suggested edit cell "
                        f"'{choice}' lacks an exact matching RC row decision"
                    )


def synthesis_card_check(
    root: Path,
    text: str,
    artifact: Path,
) -> None:
    decision = CARD_SUGGESTED_EDIT_FIELD.search(text)
    has_finding_markers = (
        decision is not None
        or re.search(r"(?im)^- Root cause:\s*", text) is not None
        or re.search(r"(?im)^- Root family:\s*", text) is not None
    )
    if not has_finding_markers:
        return
    if decision is None:
        fail(
            f"{artifact} synthesis finding card lacks a non-empty "
            "'- Suggested edit decision:' field"
        )
    root_cause_match = re.search(
        r"(?im)^- Root cause:\s*(RC\d+-\d+|none)\b", text
    )
    root_family_match = re.search(
        r"(?im)^- Root family:\s*(RF\d{3,}|none)\b", text
    )
    if root_cause_match is None or root_family_match is None:
        fail(
            f"{artifact} synthesis finding card lacks exact Root cause / "
            "Root family binding fields"
        )
    status = decision.group(1).lower()
    detail = decision.group(2).strip()
    blocks = fenced_blocks(text, "suggestion")
    card_replacement = fenced_field(
        text, "Suggested edit replacement", "suggestion"
    )
    selected = fenced_field(text, "Suggested edit selected lines")
    if status == "applicable":
        if len(blocks) != 1 or card_replacement is None:
            fail(
                f"{artifact} synthesis finding card applicable Suggested edit "
                f"has {len(blocks)} suggestion blocks; expected exactly one"
            )
        verify_suggestion_against_worktree(
            root,
            f"{artifact}",
            detail,
            selected,
            card_replacement,
            require_selected=True,
        )
    else:
        if detail.lower() in NON_SPECIFIC_OMISSION:
            fail(
                f"{artifact} synthesis finding card has a non-specific "
                "Suggested edit omission reason"
            )
        if blocks:
            fail(
                f"{artifact} synthesis finding card marks Suggested edit "
                "omitted but contains a suggestion block"
            )


def draft_fragment_structure_check(
    root: Path,
    text: str,
    artifact: Path,
) -> None:
    if artifact.parent.name == "draft-parts" and re.fullmatch(
        r"([FQN]\d+)\.md", artifact.name
    ):
        item = artifact.stem
        if not re.search(
            rf"(?m)^- \*\*Synthesis item:\*\* {re.escape(item)}\s*$", text
        ):
            fail(
                f"{artifact} draft fragment lacks exact "
                f"'- **Synthesis item:** {item}' marker"
            )
        if item.startswith("F"):
            required_fields = FINDING_REQUIRED_FIELDS
        elif item.startswith("N"):
            required_fields = ("Note", "Why it matters", "Rows")
        else:
            required_fields = ("Question", "Why it matters", "Rows")
        for field_name in required_fields:
            if not re.search(
                rf"(?m)^- \*\*{re.escape(field_name)}:\*\*\s*\S", text
            ):
                fail(
                    f"{artifact} draft fragment lacks non-empty "
                    f"'{field_name}' field"
                )
        if item.startswith("F"):
            decision = SUGGESTED_EDIT_FIELD.search(text)
            if decision is None:
                fail(
                    f"{artifact} draft fragment lacks a valid "
                    "'- **Suggested edit:** (applicable|omitted) — ...' field"
                )
            status = decision.group(1).lower()
            detail = decision.group(2).strip()
            blocks = fenced_blocks(text, "suggestion")
            if status == "applicable":
                if len(blocks) != 1:
                    fail(
                        f"{artifact} applicable Suggested edit requires "
                        f"exactly one suggestion block (found {len(blocks)})"
                    )
                verify_suggestion_against_worktree(
                    root,
                    f"{artifact}",
                    detail,
                    None,
                    blocks[0],
                    require_selected=False,
                )
            else:
                if detail.lower() in NON_SPECIFIC_OMISSION:
                    fail(
                        f"{artifact} has a non-specific Suggested edit "
                        "omission reason"
                    )
                if blocks:
                    fail(
                        f"{artifact} marks Suggested edit omitted but "
                        "contains a suggestion block"
                    )
    elif artifact.name == "draft-review.md":
        markers = list(
            re.finditer(
                r"(?m)^- \*\*Synthesis item:\*\* (F\d+)\s*$", text
            )
        )
        for idx, match in enumerate(markers):
            item = match.group(1)
            line_start = text.rfind("\n", 0, match.start()) + 1
            heading_before = list(
                re.finditer(r"(?m)^###\s+[^\r\n]+$", text[:line_start])
            )
            block_start = (
                heading_before[-1].start() if heading_before else line_start
            )
            next_heading = re.search(
                r"(?m)^##(?:#)?\s+[^\r\n]+$", text[match.end():]
            )
            next_marker = (
                markers[idx + 1].start()
                if idx + 1 < len(markers) else len(text)
            )
            block_end = min(
                match.end() + next_heading.start()
                if next_heading is not None else len(text),
                next_marker,
            )
            block_text = text[block_start:block_end]
            for field_name in FINDING_REQUIRED_FIELDS:
                if not re.search(
                    rf"(?m)^- \*\*{re.escape(field_name)}:\*\*\s*\S",
                    block_text,
                ):
                    fail(
                        f"{artifact} finding {item} lacks non-empty "
                        f"'{field_name}' field"
                    )
            decision = SUGGESTED_EDIT_FIELD.search(block_text)
            if decision is not None:
                status = decision.group(1).lower()
                detail = decision.group(2).strip()
                blocks = fenced_blocks(block_text, "suggestion")
                if status == "applicable":
                    if len(blocks) != 1:
                        fail(
                            f"{artifact} finding {item} applicable Suggested "
                            f"edit requires 1 suggestion block (found {len(blocks)})"
                        )
                    verify_suggestion_against_worktree(
                        root,
                        f"{artifact} finding {item}",
                        detail,
                        None,
                        blocks[0],
                        require_selected=False,
                    )
                else:
                    if detail.lower() in NON_SPECIFIC_OMISSION:
                        fail(
                            f"{artifact} finding {item} has a non-specific "
                            "Suggested edit omission reason"
                        )
                    if blocks:
                        fail(
                            f"{artifact} finding {item} marks Suggested edit "
                            "omitted but contains a suggestion block"
                        )


def challenge_index_check(
    root: Path,
    parsed: list[tuple[str, list[str], list[dict[str, str]]]],
    artifact: Path,
) -> None:
    has_sections = (root / "draft-sections" / "index.tsv").is_file()
    for _, header, rows in parsed:
        if not {"shard", "scope", "expected coverage"}.issubset(header):
            continue
        for row in rows:
            shard = row.get("shard", "").strip()
            scope = row.get("scope", "").strip()
            tokens_set = {
                item.strip()
                for item in row.get("expected coverage", "").split(",")
                if item.strip()
            }
            is_global_scope = scope.lower().startswith("global-consistency")
            if ("global:consistency" in tokens_set) != is_global_scope:
                fail(
                    f"{artifact} shard {shard or '?'} global-consistency "
                    "scope and global:consistency token must match"
                )
            if not has_sections and (
                is_global_scope or "global:consistency" in tokens_set
            ):
                fail(
                    f"{artifact} shard {shard or '?'} includes "
                    "global:consistency, which is only valid when "
                    "draft-sections/index.tsv exists"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--kind",
        choices=(
            "auto", "inventory", "plan", "ledger", "verdict", "affinity",
            "root-cause", "reconciliation", "synthesis-card",
            "draft-fragment", "gerrit-fragment", "challenge-index", "generic",
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
    relative = artifact.relative_to(root)
    if relative.as_posix() == "internal-review-raw.md" and arguments.kind == "auto":
        if not text.strip():
            fail(f"{artifact}: internal-review-raw.md is empty")
        print(f"valid generic: {artifact}")
        return 0
    parsed, errors = effective_tables(text, str(artifact))
    if errors:
        fail("; ".join(errors))

    kind = arguments.kind
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
        elif (
            relative.parts[:1] == ("root-cause",)
            and re.fullmatch(r"RC\d+\.md", artifact.name)
        ):
            kind = "root-cause"
        elif relative.as_posix() == "reconciliation.md":
            kind = "reconciliation"
        elif (
            relative.parts[:1] == ("synthesis",)
            and artifact.name != "index.md"
            and artifact.suffix == ".md"
        ):
            kind = "synthesis-card"
        elif (
            relative.parts[:1] == ("draft-parts",)
            or relative.as_posix() == "draft-review.md"
        ):
            kind = "draft-fragment"
        elif (
            relative.parts[:1] == ("gerrit-parts",)
            or relative.as_posix() == "gerrit-comments.md"
        ):
            kind = "gerrit-fragment"
        elif re.fullmatch(r"challenge/round-\d+/index\.md", relative.as_posix()):
            kind = "challenge-index"
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
    elif kind == "root-cause":
        root_cause_check(root, text, parsed, artifact)
    elif kind == "reconciliation":
        reconciliation_check(text, parsed, artifact)
    elif kind == "synthesis-card":
        synthesis_card_check(root, text, artifact)
    elif kind == "draft-fragment":
        report_fragment_check(root, text, artifact, is_gerrit=False)
    elif kind == "gerrit-fragment":
        report_fragment_check(
            root,
            text,
            artifact,
            is_gerrit=(artifact.name != "FRAME.md"),
        )
    elif kind == "challenge-index":
        challenge_index_check(root, parsed, artifact)
    print(f"valid {kind}: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
