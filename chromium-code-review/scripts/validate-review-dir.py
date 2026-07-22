#!/usr/bin/env python3
"""Deterministically validate a chromium-code-review working directory.

Usage:
  validate-review-dir.py REVIEW_DIR [--phase PHASE] [--require-active-lease]

Phases are pin, collection, verification, reconciliation, final, or auto.
The default infers the latest phase from existing artifacts. Validation is
strict about machine-checkable contracts and reports judgment-only checks as
warnings instead of pretending to prove them.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable


PHASES = {"pin": 0, "collection": 1, "verification": 2,
          "reconciliation": 3, "final": 4}
ROW_ID_TEXT = r"(?:[A-Z][A-Z0-9]*-\d+|R\d+-RC\d+-\d+)"
ROW_ID = re.compile(rf"^{ROW_ID_TEXT}$")
CITATION = re.compile(r"(?:^|[\s`(\[])([A-Za-z0-9_.+@{}\-/]+):\d+")
ARTIFACT_POINTER = re.compile(
    r"(?:^|\s|`)([A-Za-z0-9_.+@{}\-/]+\.(?:json|md):/"
    r"[A-Za-z0-9_./~-]+)"
)
ROSTER = (
    "Desk-Check Simulation + Arithmetic Drills",
    "Data Lineage",
    "Callback And Task Lifetime",
    "Container And View Invalidation",
    "Error-Path Walk",
    "State × Method Matrix",
    "Mode × Host-Capability Matrix",
    "Teardown Order",
    "Field Propagation Matrix",
    "Associative Container Semantics",
    "Transformation Equivalence And Residue",
    "Mechanical Leads",
    "Per-Surface Invariants",
    "Async And Lifecycle",
    "State/Persistence/Cache",
    "Integration And Feature Control",
    "Security And Trust Boundaries",
    "Contracts And API Shape",
    "Tests As Specifications",
    "Changed-Lines Polish",
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
    "Holistic-and-polish thread",
)
ROSTER_PREFIX = {
    "Desk-Check Simulation + Arithmetic Drills": "DCS",
    "Data Lineage": "DL",
    "Callback And Task Lifetime": "CTL",
    "Container And View Invalidation": "CVI",
    "Error-Path Walk": "EPW",
    "State × Method Matrix": "SMM",
    "Mode × Host-Capability Matrix": "MHM",
    "Teardown Order": "TDO",
    "Field Propagation Matrix": "FPM",
    "Associative Container Semantics": "ACS",
    "Transformation Equivalence And Residue": "TER",
    "Mechanical Leads": "ML",
    "Per-Surface Invariants": "PSI",
    "Async And Lifecycle": "AL",
    "State/Persistence/Cache": "SPC",
    "Integration And Feature Control": "IFC",
    "Security And Trust Boundaries": "STB",
    "Contracts And API Shape": "CAS",
    "Tests As Specifications": "TAS",
    "Changed-Lines Polish": "CLP",
    "Threading And Synchronization": "TSY",
    "Ownership And Blink Lifecycle": "OBL",
    "Mojo IPC Authorization And Sandbox": "MIS",
    "Performance And Resource Scaling": "PRS",
    "Platform And Language Semantics": "PLS",
    "Build API And Generated Assets": "BAG",
    "Privacy And Telemetry": "PAT",
    "Accessibility And Internationalization": "AXI",
    "Network Semantics": "NET",
    "Fuzzing And Test Strategy": "FTS",
    "Holistic-and-polish thread": "HOL",
}
TRIGGER_ID_TEXT = r"(?:T\d+|I[A-Z0-9]+-T\d+)"
TRIGGER_ID = re.compile(rf"^{TRIGGER_ID_TEXT}$", re.IGNORECASE)
MANIFEST_COLUMNS = (
    "phase", "work_id", "attempt", "state", "tier", "task_id", "brief",
    "artifact", "remaining_scope", "depends_on",
)
MANIFEST_TIERS = {"mechanical", "standard", "frontier", "inherit"}
TIER_ORDER = {"mechanical": 0, "standard": 1, "frontier": 2}
TIER_FLOOR_STANDARD = {"Mechanical Leads", "Changed-Lines Polish"}
EVIDENCE_EXCEPTION = re.compile(r"evidence-exception:\s*\S+")
GATE_VERDICTS = {"PROVEN", "REJECTED", "UNPROVEN"}
RESIDUE_SCOPE = re.compile(r"^residue\((TC\d+(?:\s*,\s*TC\d+)*)\):\s+\S")
MANIFEST_STATES = {
    "queued", "running", "partial", "retryable", "needs-repair",
    "complete", "terminated",
}
INPUT_MANIFEST_COLUMNS = (
    "work_id", "attempt", "phase", "brief", "input_path", "role", "bytes",
    "sha256",
)
INPUT_MANIFEST_ROLES = {
    "brief", "control", "reference", "assigned", "candidate-packet", "card",
    "frame", "section", "prestate",
}
SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_SCRIPT = SCRIPT_DIR / "profile-review.py"
INDEX_SCRIPT = SCRIPT_DIR / "build-review-indexes.py"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def emit(self) -> int:
        for message in self.errors:
            print(f"ERROR: {message}")
        for message in self.warnings:
            print(f"WARNING: {message}")
        if self.errors:
            print(f"FAIL: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
            return 1
        print(f"PASS: 0 errors, {len(self.warnings)} warning(s)")
        return 0


def read_text(path: Path, report: Report, required: bool = True) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if required:
            report.error(f"missing required artifact: {path}")
    except (OSError, UnicodeError) as error:
        report.error(f"cannot read {path}: {error}")
    return ""


def read_json(path: Path, report: Report) -> Any:
    try:
        raw = path.read_bytes()
        if raw.startswith(b")]}'"):
            report.error(f"{path} still contains Gerrit's XSSI prefix")
            return None
        return json.loads(raw)
    except FileNotFoundError:
        report.error(f"missing required artifact: {path}")
    except (OSError, json.JSONDecodeError) as error:
        report.error(f"invalid JSON in {path}: {error}")
    return None


def split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith(r"\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [cell.replace(r"\|", "|").strip() for cell in cells]


def tables(text: str) -> Iterable[tuple[str, list[str], list[list[str]]]]:
    lines = text.splitlines()
    heading = ""
    index = 0
    while index < len(lines):
        if lines[index].startswith("## "):
            heading = lines[index][3:].strip()
        if (lines[index].lstrip().startswith("|") and index + 1 < len(lines)
                and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1])):
            header = [cell.lower() for cell in split_row(lines[index])]
            index += 2
            rows = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                row = split_row(lines[index])
                if len(row) == len(header):
                    rows.append(row)
                index += 1
            yield heading, header, rows
            continue
        index += 1


def table_dicts(text: str) -> Iterable[tuple[str, list[str], list[dict[str, str]]]]:
    for heading, header, rows in tables(text):
        yield heading, header, [dict(zip(header, row)) for row in rows]


def field(text: str, name: str) -> str | None:
    match = re.search(rf"^- {re.escape(name)}:\s*(.*?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def validate_scaling_outputs(root: Path, report: Report) -> dict[str, int]:
    """Require fresh deterministic helper outputs and return context budgets."""
    for script in (PROFILE_SCRIPT, INDEX_SCRIPT):
        try:
            result = subprocess.run(
                [sys.executable, str(script), str(root), "--check"],
                check=False, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            report.error(f"cannot run {script.name} --check: {error}")
            continue
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            report.error(f"{script.name} --check failed: {detail or 'unknown error'}")

    profile = read_json(root / "profile.json", report)
    budgets: dict[str, int] = {}
    if not isinstance(profile, dict):
        return budgets
    context = profile.get("context_budget")
    if not isinstance(context, dict):
        report.error("profile.json lacks context_budget object")
        return budgets
    for name in (
        "worker_input_budget_bytes",
        "candidate_packet_budget_bytes",
        "evidence_card_budget_bytes",
    ):
        value = context.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            report.error(f"profile.json context_budget has invalid {name}")
        else:
            budgets[name] = value
    tier_budgets = context.get("tier_worker_input_budget_bytes")
    if isinstance(tier_budgets, dict):
        for tier, value in tier_budgets.items():
            if tier in TIER_ORDER and isinstance(value, int) \
                    and not isinstance(value, bool) and value > 0:
                budgets[f"tier:{tier}"] = value
            else:
                report.error(
                    f"profile.json tier_worker_input_budget_bytes has invalid "
                    f"entry {tier!r}")
    worker = budgets.get("worker_input_budget_bytes")
    for name in ("candidate_packet_budget_bytes", "evidence_card_budget_bytes"):
        if worker is not None and budgets.get(name, 0) > worker:
            report.error(f"profile.json {name} exceeds worker_input_budget_bytes")
    return budgets


def validate_pin(root: Path, report: Report, require_active_lease: bool = False,
                 lease_stale_seconds: int = 3600) -> tuple[str | None, list[str]]:
    detail = read_json(root / "detail.json", report)
    comments = read_json(root / "comments.json", report)
    pin = read_text(root / "pin.md", report)
    if detail is not None and not isinstance(detail, dict):
        report.error("detail.json must contain an object")
        detail = None
    if comments is not None and not isinstance(comments, dict):
        report.error("comments.json must contain a path-to-arrays object")
    elif isinstance(comments, dict):
        for path, values in comments.items():
            if not isinstance(path, str) or not isinstance(values, list):
                report.error("comments.json must map every path string to an array")
                break

    selected_ps = field(pin, "Pinned patchset")
    sha = field(pin, "Revision SHA")
    parent = field(pin, "Parent SHA")
    is_current = field(pin, "Is current at fetch")
    current_ps = field(pin, "Gerrit-current patchset at fetch")
    current_sha_at_fetch = field(pin, "Gerrit-current revision SHA at fetch")
    fetched_at = field(pin, "Metadata fetched at")
    for label, value in (("Pinned patchset", selected_ps), ("Revision SHA", sha),
                         ("Parent SHA", parent), ("Is current at fetch", is_current),
                         ("Gerrit-current patchset at fetch", current_ps),
                         ("Gerrit-current revision SHA at fetch", current_sha_at_fetch),
                         ("Metadata fetched at", fetched_at)):
        if not value:
            report.error(f"pin.md is missing '- {label}:'")
    if sha and not re.fullmatch(r"[0-9a-fA-F]{40,64}", sha):
        report.error("pin.md Revision SHA is not a full hexadecimal object id")
    if parent and not re.fullmatch(r"[0-9a-fA-F]{40,64}", parent):
        report.error("pin.md Parent SHA is not a full hexadecimal object id")
    if is_current not in (None, "yes", "no"):
        report.error("pin.md Is current at fetch must be yes or no")
    if selected_ps and current_ps and is_current:
        expected = "yes" if selected_ps == current_ps else "no"
        if is_current != expected:
            report.error(f"pin.md Is current at fetch is {is_current}, expected {expected}")
    if isinstance(detail, dict) and sha:
        revisions = detail.get("revisions")
        if not isinstance(revisions, dict) or sha not in revisions:
            report.error("pin.md Revision SHA is absent from detail.json revisions")
        else:
            detail_ps = str(revisions[sha].get("_number"))
            if selected_ps and detail_ps != selected_ps:
                report.error("pin.md patchset does not match detail.json revision number")
        current_sha = detail.get("current_revision")
        if current_sha in (revisions or {}) and current_ps:
            actual_current = str(revisions[current_sha].get("_number"))
            if actual_current != current_ps:
                report.error("pin.md Gerrit-current patchset does not match detail.json")
            if current_sha_at_fetch != current_sha:
                report.error("pin.md Gerrit-current revision SHA does not match detail.json")

    worktree_value = field(pin, "Worktree")
    if worktree_value:
        worktree_path = Path(worktree_value.split(" (", 1)[0])
        if not worktree_path.is_dir():
            report.error(f"pinned worktree does not exist: {worktree_path}")
        elif sha:
            try:
                actual = subprocess.run(
                    ["git", "-C", str(worktree_path), "rev-parse", "HEAD"],
                    check=True, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE).stdout.strip()
                if actual != sha:
                    report.error(f"worktree HEAD {actual} does not match pin {sha}")
                dirty = subprocess.run(
                    ["git", "-C", str(worktree_path), "status", "--porcelain",
                     "--untracked-files=all"], check=True, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
                if dirty:
                    report.error("pinned worktree has local or untracked changes")
            except subprocess.CalledProcessError as error:
                report.error(f"cannot verify pinned worktree: {error.stderr.strip()}")
    else:
        report.error("pin.md is missing '- Worktree:'")

    worktree_lease = field(pin, "Worktree lease")
    worktree_lease_token = field(pin, "Worktree lease token")
    if bool(worktree_lease) != bool(worktree_lease_token):
        report.error("pin.md must contain both Worktree lease and Worktree lease token")
    if require_active_lease:
        if not worktree_lease or not worktree_lease_token:
            report.error("active worktree lease is required but absent from pin.md")
        else:
            helper = Path(__file__).with_name("worktree-lease.py")
            try:
                checked = subprocess.run(
                    [str(helper), "check", str(root), "--stale-seconds",
                     str(lease_stale_seconds)], text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError as error:
                report.error(
                    f"cannot run active worktree lease validator {helper}: {error}")
            else:
                if checked.returncode != 0:
                    detail = checked.stderr.strip() or checked.stdout.strip()
                    report.error(
                        f"active worktree lease validation failed: {detail}")

    changed: list[str] = []
    in_files = False
    for line in pin.splitlines():
        if line.startswith("- Files changed"):
            in_files = True
            continue
        if in_files:
            match = re.match(r"^  - (.*?)(?: \[[A-Z?]+; \+[0-9?]+/-[0-9?]+\])?$", line)
            if match:
                changed.append(match.group(1))
            elif line.strip():
                in_files = False
    if "- Files changed: none" not in pin and not changed:
        report.error("pin.md has no mechanically readable changed-file list")
    return sha, changed


def validate_unresolved(root: Path, report: Report, required: bool) -> None:
    path = root / "gerrit" / "unresolved-threads.json"
    if not path.exists():
        if required:
            report.error(f"missing normalized Gerrit thread artifact: {path}")
        return
    value = read_json(path, report)
    if not isinstance(value, dict):
        report.error("unresolved-threads.json must contain an object")
        return
    if (not isinstance(value.get("summary"), dict)
            or not isinstance(value.get("threads"), list)
            or not isinstance(value.get("malformed"), list)):
        report.error("unresolved-threads.json requires summary, threads, and malformed")
        return
    summary = value["summary"]
    for key in ("total_threads", "unresolved_threads", "malformed_entries"):
        if not isinstance(summary.get(key), int) or summary[key] < 0:
            report.error(f"unresolved-threads.json summary has invalid {key}")
    if summary.get("unresolved_threads") != len(value["threads"]):
        report.error("unresolved-threads.json summary has the wrong unresolved count")
    if summary.get("malformed_entries") != len(value["malformed"]):
        report.error("unresolved-threads.json summary has the wrong malformed count")
    if (isinstance(summary.get("total_threads"), int)
            and isinstance(summary.get("unresolved_threads"), int)
            and summary["total_threads"] < summary["unresolved_threads"]):
        report.error("unresolved-threads.json total_threads is below unresolved_threads")
    roots = set()
    for thread in value["threads"]:
        if not isinstance(thread, dict):
            report.error("unresolved thread entry is not an object")
            continue
        for required_field in ("root_id", "latest_id", "path", "unresolved", "comments"):
            if required_field not in thread:
                report.error(f"unresolved thread is missing {required_field}")
        if thread.get("unresolved") is not True:
            report.error(f"thread {thread.get('root_id')} is present but not unresolved")
        root_id = thread.get("root_id")
        if root_id in roots:
            report.error(f"duplicate normalized thread root: {root_id}")
        roots.add(root_id)
        comments = thread.get("comments")
        if isinstance(comments, list) and comments:
            latest = max(comments, key=lambda item: (
                str(item.get("updated") or item.get("created") or ""),
                str(item.get("id") or "")))
            if latest.get("id") != thread.get("latest_id") or latest.get("unresolved") is not True:
                report.error(f"thread {root_id} latest-comment state is inconsistent")


def trigger_associates_with_roster(
    roster_name: str, trigger_row: dict[str, str]
) -> bool:
    prefix = ROSTER_PREFIX[roster_name]
    discovery_tokens = {
        token.upper()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]*", trigger_row["discovery_triggers"])
    }
    if prefix in discovery_tokens:
        return True
    normalized_surface = re.sub(r"[^a-z0-9]+", " ", trigger_row["surface"].lower()).strip()
    normalized_name = re.sub(r"[^a-z0-9]+", " ", roster_name.lower()).strip()
    return normalized_name in normalized_surface


def trigger_proves_roster_absence(
    roster_name: str, trigger_row: dict[str, str]
) -> bool:
    prefix = ROSTER_PREFIX[roster_name]
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(prefix)}\s+absent(?![A-Za-z0-9])",
        trigger_row["discovery_triggers"],
        re.IGNORECASE,
    ) is not None


def trigger_positively_activates_roster(
    roster_name: str, trigger_row: dict[str, str]
) -> bool:
    prefix = ROSTER_PREFIX[roster_name]
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(prefix)}"
        rf"(?![A-Za-z0-9]|\s+absent\b)",
        trigger_row["discovery_triggers"],
        re.IGNORECASE,
    ) is not None


def tier_override(root: Path) -> bool:
    directives = root / "directives.md"
    if not directives.is_file():
        return False
    return bool(re.search(r"(?m)^[-*]?\s*tier-override:\s*\S+",
                          directives.read_text(encoding="utf-8")))


def validate_plan(
    root: Path, trigger_rows: dict[str, dict[str, str]], report: Report
) -> None:
    text = read_text(root / "plan.md", report)
    roster_rows: list[dict[str, str]] = []
    tier_column_seen = False
    for _, header, rows in table_dicts(text):
        if "roster entry" in header and "status" in header:
            if "tier" in header:
                tier_column_seen = True
            roster_rows.extend(rows)
    if not roster_rows:
        report.error("plan.md has no roster table")
        return
    if not tier_column_seen:
        report.error("plan.md roster table lacks a tier column")
    counts: Counter[str] = Counter()
    for row in roster_rows:
        name = re.sub(r"\s+(?:\(shard[^)]*\)|—\s*shard.*)$", "", row["roster entry"], flags=re.I)
        counts[name] += 1
        status = row.get("status", "")
        if status == "spawn":
            tier = row.get("tier", "").strip()
            if tier_column_seen and tier not in {"mechanical", "standard", "frontier"}:
                report.error(
                    f"plan row '{row['roster entry']}' has invalid tier '{tier}'")
            elif tier == "mechanical" and name in ROSTER:
                report.error(
                    f"plan row '{row['roster entry']}' assigns mechanical tier "
                    "to a discovery thread")
            elif name in ROSTER and tier in TIER_ORDER:
                floor = "standard" if name in TIER_FLOOR_STANDARD else "frontier"
                if TIER_ORDER[tier] < TIER_ORDER[floor]:
                    if tier_override(root):
                        report.warn(
                            f"plan row '{row['roster entry']}' runs below its "
                            f"{floor} floor under a user tier-override")
                    else:
                        report.error(
                            f"plan row '{row['roster entry']}' tier '{tier}' is "
                            f"below its {floor} floor and directives.md records "
                            "no tier-override")
            continue
        not_applicable = re.fullmatch(
            r"not applicable\s+—\s+trigger absence proved by\s+"
            rf"({TRIGGER_ID_TEXT}(?:\s*,\s*{TRIGGER_ID_TEXT})*)",
            status,
            re.I,
        )
        if not_applicable:
            cited = {item.strip().upper() for item in not_applicable.group(1).split(",")}
            if name in ROSTER:
                positive_ids = {
                    identifier for identifier, trigger_row in trigger_rows.items()
                    if trigger_positively_activates_roster(name, trigger_row)
                }
                if positive_ids:
                    report.error(
                        f"plan row '{row['roster entry']}' is not applicable but "
                        f"positive {ROSTER_PREFIX[name]} trigger rows exist: "
                        + ", ".join(sorted(positive_ids))
                    )
                absence_ids = {
                    identifier for identifier, trigger_row in trigger_rows.items()
                    if trigger_proves_roster_absence(name, trigger_row)
                }
                missing_absence = absence_ids - cited
                if missing_absence:
                    report.error(
                        f"plan row '{row['roster entry']}' omits {ROSTER_PREFIX[name]} "
                        f"absence proof rows: " + ", ".join(sorted(missing_absence))
                    )
            for identifier in sorted(cited):
                trigger_row = trigger_rows.get(identifier)
                if trigger_row is None:
                    report.error(
                        f"plan row '{row['roster entry']}' cites unknown trigger {identifier}"
                    )
                elif name in ROSTER and not trigger_associates_with_roster(
                    name, trigger_row
                ):
                    report.error(
                        f"plan row '{row['roster entry']}' cites {identifier}, which "
                        f"does not prove trigger absence for {name}"
                    )
                elif name in ROSTER and not trigger_proves_roster_absence(
                    name, trigger_row
                ):
                    report.error(
                        f"plan row '{row['roster entry']}' cites {identifier}, which "
                        f"does not carry required '{ROSTER_PREFIX[name]} absent' proof"
                    )
            continue
        if re.fullmatch(r"unreviewed\s+—\s+\S.*", status, re.I):
            continue
        report.error(f"plan row '{row['roster entry']}' has invalid status '{status}'")
    for name in ROSTER:
        if counts[name] == 0:
            report.error(f"plan.md omits roster entry: {name}")
    for name in counts:
        if name not in ROSTER:
            report.error(f"plan.md invents or renames roster entry: {name}")


def validate_trigger_inventory(
    root: Path, report: Report
) -> tuple[set[str], dict[str, dict[str, str]]]:
    inventory_paths = ([root / "inventory.md"] if (root / "inventory.md").exists()
                       else sorted((root / "inventory").glob("*.md")))
    if not inventory_paths:
        report.error("missing inventory.md or inventory/*.md artifacts")
        return set(), {}
    seen: dict[str, Path] = {}
    trigger_rows: dict[str, dict[str, str]] = {}
    required: set[str] = set()
    found_table = False
    for path in inventory_paths:
        text = read_text(path, report)
        for heading, header, rows in table_dicts(text):
            if heading != "Trigger inventory":
                continue
            found_table = True
            if not {
                "scope id", "surface", "discovery triggers",
                "root-cause trigger", "evidence",
            }.issubset(header):
                report.error(f"{path}: Trigger inventory has the wrong columns")
                continue
            for row in rows:
                scope = row.get("scope id", "").upper()
                trigger = row.get("root-cause trigger", "")
                if not TRIGGER_ID.fullmatch(scope):
                    report.error(f"{path}: invalid trigger scope ID '{scope}'")
                    continue
                if scope in seen:
                    report.error(f"duplicate trigger scope ID {scope}: {seen[scope]} and {path}")
                seen[scope] = path
                trigger_rows[scope] = {
                    "surface": row.get("surface", ""),
                    "discovery_triggers": row.get("discovery triggers", ""),
                }
                if not re.match(r"(?i)^(required|not required):\s*\S", trigger):
                    report.error(f"{path}: {scope} has invalid root-cause trigger '{trigger}'")
                elif trigger.lower().startswith("required:"):
                    required.add(scope)
                evidence = row.get("evidence", "")
                if trigger.lower().startswith("required:"):
                    if not CITATION.search(evidence):
                        report.error(f"{path}: {scope} has no path:line trigger evidence")
                elif not (CITATION.search(evidence) or ARTIFACT_POINTER.search(evidence)):
                    report.error(
                        f"{path}: {scope} has no cited trigger-absence evidence"
                    )
    if not found_table:
        report.error("inventory artifacts have no ## Trigger inventory table")
    return required, trigger_rows


def validate_root_cause_trigger_accounting(root: Path, required: set[str],
                                           report: Report) -> None:
    path = root / "root-cause" / "batches.md"
    text = read_text(path, report)
    accounting: Counter[str] = Counter()
    scheduled: set[str] = set()
    found_table = False
    for heading, header, rows in table_dicts(text):
        if heading != "Trigger accounting":
            continue
        found_table = True
        if not {"candidate / verdict", "disposition", "rc batch"}.issubset(header):
            report.error(f"{path}: Trigger accounting has the wrong columns")
            continue
        for row in rows:
            scope = row.get("candidate / verdict", "")
            scope = scope.upper()
            if not TRIGGER_ID.fullmatch(scope):
                continue
            accounting[scope] += 1
            disposition = row.get("disposition", "")
            batch = row.get("rc batch", "")
            if re.match(r"(?i)^scheduled\b", disposition) and re.fullmatch(r"RC\d+", batch):
                scheduled.add(scope)
    if not found_table:
        report.error(f"{path}: missing ## Trigger accounting table")
    for scope in sorted(required):
        if accounting[scope] != 1:
            report.error(
                f"root-cause trigger scope {scope} has {accounting[scope]} accounting rows")
        elif scope not in scheduled:
            report.error(f"root-cause-required scope {scope} is not scheduled to an RC batch")


def validate_generated_briefs(root: Path, report: Report) -> None:
    brief_root = root / "briefs"
    paths = sorted(brief_root.glob("**/*.md")) if brief_root.exists() else []
    if not paths:
        report.error("no generated briefs/*.md artifacts found")
        return
    requirements = {
        "directives": re.compile(r"directives\.md", re.I),
        "pin/revision": re.compile(r"\brevision\b", re.I),
        "authority boundary": re.compile(r"authority boundary|untrusted", re.I),
        "append/retry": re.compile(r"append-only|amendment", re.I),
        "partial return": re.compile(r"\bpartial\b", re.I),
    }
    for path in paths:
        text = read_text(path, report)
        for label, pattern in requirements.items():
            if not pattern.search(text):
                report.error(f"{path}: generated brief lacks {label} contract")


def validate_input_manifest(root: Path, budgets: dict[str, int],
                            report: Report) -> dict[str, list[dict[str, str]]]:
    path = root / "input-manifest.tsv"
    if not path.is_file():
        report.error(f"missing required worker input manifest: {path}")
        return {}
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            if tuple(reader.fieldnames or ()) != INPUT_MANIFEST_COLUMNS:
                report.error("input-manifest.tsv has wrong columns or order")
                return {}
            rows = list(reader)
    except (OSError, csv.Error) as error:
        report.error(f"cannot parse input-manifest.tsv: {error}")
        return {}

    grouped: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for line_number, row in enumerate(rows, 2):
        work_id = row["work_id"]
        if not work_id or re.search(r"[\t\r\n]", work_id):
            report.error(f"input-manifest.tsv:{line_number}: invalid work_id")
            continue
        try:
            attempt = int(row.get("attempt", ""))
            if attempt < 1:
                raise ValueError
        except ValueError:
            report.error(
                f"input-manifest.tsv:{line_number}: invalid attempt "
                f"'{row.get('attempt', '')}'")
            continue
        grouped[(work_id, attempt)].append(row)
        if not row["phase"]:
            report.error(f"input-manifest.tsv:{line_number}: blank phase")
        if row["role"] not in INPUT_MANIFEST_ROLES:
            report.error(
                f"input-manifest.tsv:{line_number}: invalid role '{row['role']}'"
            )
        brief = Path(row["brief"])
        input_path = Path(row["input_path"])
        if not brief.is_absolute():
            report.error(f"input-manifest.tsv:{line_number}: brief is not absolute")
        if not input_path.is_absolute():
            report.error(f"input-manifest.tsv:{line_number}: input_path is not absolute")
            continue
        if not input_path.is_file():
            report.error(
                f"input-manifest.tsv:{line_number}: missing input {input_path}"
            )
            continue
        payload = input_path.read_bytes()
        try:
            declared = int(row["bytes"])
        except ValueError:
            declared = None
            report.error(f"input-manifest.tsv:{line_number}: invalid bytes value")
        if row["role"] == "prestate":
            # A canonical artifact the attempt appends to: the declared bytes
            # and hash cover the immutable pre-attempt prefix.
            if declared is not None:
                if declared > len(payload):
                    report.error(
                        f"input-manifest.tsv:{line_number}: prestate prefix "
                        f"{declared} exceeds current size of {input_path}")
                elif row["sha256"] != hashlib.sha256(
                        payload[:declared]).hexdigest():
                    report.error(
                        f"input-manifest.tsv:{line_number}: prestate prefix "
                        f"hash mismatch for {input_path} — prior content was "
                        "rewritten, not appended")
        else:
            if declared is not None and declared != len(payload):
                report.error(
                    f"input-manifest.tsv:{line_number}: byte count mismatch for "
                    f"{input_path}: {declared} != {len(payload)}"
                )
            actual_hash = hashlib.sha256(payload).hexdigest()
            if row["sha256"] != actual_hash:
                report.error(
                    f"input-manifest.tsv:{line_number}: sha256 mismatch for {input_path}"
                )


    worker_budget = budgets.get("worker_input_budget_bytes")
    candidate_budget = budgets.get("candidate_packet_budget_bytes")
    evidence_budget = budgets.get("evidence_card_budget_bytes")
    resolved_tiers: dict[tuple[str, int], str] = {}
    orch_briefs: dict[tuple[str, int], str] = {}
    orchestration = root / "orchestration.tsv"
    orchestration_readable = False
    if orchestration.is_file():
        try:
            with orchestration.open(encoding="utf-8", newline="") as stream:
                for row in csv.DictReader(stream, delimiter="\t"):
                    try:
                        attempt_number = int(row.get("attempt", ""))
                    except ValueError:
                        continue
                    key = (row.get("work_id", ""), attempt_number)
                    if row.get("tier") in TIER_ORDER:
                        resolved_tiers[key] = row["tier"]
                    orch_briefs[key] = row.get("brief", "")
            orchestration_readable = True
        except OSError:
            pass
    if orchestration_readable:
        for key, orch_brief in sorted(orch_briefs.items()):
            if orch_brief in {"", "—", "-"}:
                continue
            if key not in grouped:
                report.error(
                    f"work unit {key[0]} attempt {key[1]} has a brief but no "
                    "input-manifest rows")
        for key in sorted(grouped):
            if key not in orch_briefs:
                report.error(
                    f"input manifest work {key[0]} attempt {key[1]} has no "
                    "orchestration.tsv attempt")
    for (work_id, attempt), work_rows in grouped.items():
        briefs = {row["brief"] for row in work_rows}
        phases = {row["phase"] for row in work_rows}
        if len(briefs) != 1:
            report.error(f"input manifest work {work_id} names multiple briefs")
        if len(phases) != 1:
            report.error(f"input manifest work {work_id} names multiple phases")
        orch_brief = orch_briefs.get((work_id, attempt), "")
        if len(briefs) == 1 and orch_brief not in {"", "—", "-"} and \
                Path(next(iter(briefs))).resolve() != Path(orch_brief).resolve():
            report.error(
                f"input manifest work {work_id} attempt {attempt} names brief "
                f"{next(iter(briefs))} but orchestration.tsv records "
                f"{orch_brief}")
        unique: dict[Path, int] = {}
        candidate_paths: dict[Path, int] = {}
        self_rows = 0
        for row in work_rows:
            input_path = Path(row["input_path"])
            try:
                size = int(row["bytes"])
            except ValueError:
                continue
            unique[input_path] = size
            if row["role"] == "candidate-packet":
                candidate_paths[input_path] = size
            if row["role"] == "card" and evidence_budget is not None \
                    and size > evidence_budget:
                report.error(
                    f"input manifest work {work_id} card {input_path} exceeds "
                    f"profile evidence-card budget ({size} > {evidence_budget})"
                )
            if row["role"] == "brief" and row["input_path"] == row["brief"]:
                self_rows += 1
        total = sum(unique.values())
        effective_budget = worker_budget
        tier = resolved_tiers.get((work_id, attempt))
        tier_budget = budgets.get(f"tier:{tier}") if tier else None
        if tier_budget is None and tier is not None:
            # A concrete resolved tier means model selection is in use; an
            # unreported capacity gets the documented 128 KiB fallback.
            # Only `inherit` keeps the session budget.
            tier_budget = 131072
        if tier_budget is not None:
            effective_budget = (tier_budget if effective_budget is None
                                else min(effective_budget, tier_budget))
        if effective_budget is not None and total > effective_budget:
            report.error(
                f"input manifest work {work_id} exceeds its worker-input "
                f"budget ({total} > {effective_budget} bytes"
                + (f", {tier} tier" if tier_budget is not None else "")
                + ")"
            )
        candidate_total = sum(candidate_paths.values())
        if candidate_budget is not None and candidate_total > candidate_budget:
            report.error(
                f"input manifest work {work_id} candidate packets exceed profile "
                f"budget ({candidate_total} > {candidate_budget} bytes)"
            )
        if self_rows != 1:
            report.error(
                f"input manifest work {work_id} attempt {attempt} has "
                f"{self_rows} input-manifest self rows, expected 1"
            )

    expected_briefs = {
        item.resolve() for item in (root / "briefs").glob("**/*.md")
        if item.is_file()
    }
    for orch_brief in orch_briefs.values():
        if orch_brief not in {"", "—", "-"}:
            expected_briefs.add(Path(orch_brief).resolve())
    manifest_briefs = {
        Path(row["brief"]).resolve() for row in rows
        if Path(row["brief"]).is_absolute()
    }
    for brief in sorted(expected_briefs - manifest_briefs):
        report.error(
            f"generated analytical brief {brief} has 0 input-manifest self "
            "rows")
    for brief in sorted(manifest_briefs - expected_briefs):
        report.error(f"input-manifest self row references unknown brief {brief}")

    manifest_inputs_by_brief: dict[Path, set[Path]] = defaultdict(set)
    for row in rows:
        brief = Path(row["brief"])
        input_path = Path(row["input_path"])
        if brief.is_absolute() and input_path.is_absolute():
            manifest_inputs_by_brief[brief.resolve()].add(input_path.resolve())
    absolute_path = re.compile(r"(?<![A-Za-z0-9_.-])(/[A-Za-z0-9_.+@{}%=/:-]+)")
    for brief in sorted(expected_briefs):
        if not brief.is_file():
            continue
        active = False
        named_inputs: set[Path] = set()
        for line in brief.read_text(encoding="utf-8").splitlines():
            if re.match(r"^(?:Inputs?|Procedure):", line, re.I):
                active = True
            elif active and re.match(
                    r"^(?:Scope|Deliverables?|Return|Rules|Precondition):", line,
                    re.I):
                active = False
            if not active:
                continue
            for quoted in re.findall(r"`(/[^`]+)`", line):
                if quoted.endswith("/"):
                    continue
                candidate = Path(quoted)
                if not candidate.is_dir():
                    named_inputs.add(candidate.resolve())
            bare_line = re.sub(r"`[^`]*`", " ", line)
            for match in absolute_path.finditer(bare_line):
                raw = match.group(1)
                if raw.endswith("/"):
                    continue  # an explicit directory reference
                candidate = Path(raw.rstrip(".,;:)]}"))
                if candidate.is_dir():
                    continue
                named_inputs.add(candidate.resolve())
        for omitted in sorted(named_inputs - manifest_inputs_by_brief[brief]):
            report.error(
                f"generated analytical brief {brief} names input {omitted} in "
                "Inputs/Procedure but input-manifest.tsv omits it"
            )
    merged: dict[str, list[dict[str, str]]] = {}
    for (work_id, attempt) in sorted(grouped, key=lambda key: key[1]):
        merged[work_id] = grouped[(work_id, attempt)]  # latest attempt wins
    return merged


def validate_manifest(root: Path, report: Report, final: bool) -> None:
    path = root / "orchestration.tsv"
    if not path.exists():
        report.error(f"missing required orchestration manifest: {path}")
        return
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            if tuple(reader.fieldnames or ()) != MANIFEST_COLUMNS:
                report.error("orchestration.tsv has wrong columns or order")
                return
            rows = list(reader)
    except (OSError, csv.Error) as error:
        report.error(f"cannot parse orchestration.tsv: {error}")
        return
    seen = set()
    attempts: dict[str, list[int]] = defaultdict(list)
    latest: dict[str, dict[str, str]] = {}
    rows_by_key: dict[tuple[str, int], dict[str, str]] = {}
    running_artifacts: dict[str, str] = {}
    for line_number, row in enumerate(rows, 2):
        key = (row["work_id"], row["attempt"])
        if key in seen:
            report.error(f"orchestration.tsv:{line_number}: duplicate work_id/attempt {key}")
        seen.add(key)
        try:
            attempt = int(row["attempt"])
            if attempt < 1:
                raise ValueError
        except ValueError:
            report.error(f"orchestration.tsv:{line_number}: invalid attempt '{row['attempt']}'")
            continue
        attempts[row["work_id"]].append(attempt)
        rows_by_key[(row["work_id"], attempt)] = row
        if row["state"] not in MANIFEST_STATES:
            report.error(f"orchestration.tsv:{line_number}: invalid state '{row['state']}'")
        if row.get("tier", "") not in MANIFEST_TIERS:
            report.error(
                f"orchestration.tsv:{line_number}: invalid tier '{row.get('tier', '')}'")
        if row["state"] in {"partial", "retryable", "needs-repair", "terminated"} \
                and row["remaining_scope"] in {"", "—", "-"}:
            report.error(f"orchestration.tsv:{line_number}: {row['state']} requires remaining_scope")
        for column in ("brief", "artifact"):
            value = row[column]
            if value and value not in {"—", "-"} and not Path(value).is_absolute():
                report.error(f"orchestration.tsv:{line_number}: {column} is not absolute")
        if row["brief"] not in {"", "—", "-"}:
            brief = Path(row["brief"])
            if not brief.is_file() or brief.stat().st_size == 0:
                report.error(f"work unit {row['work_id']} has missing/empty brief {brief}")
        if row["state"] == "complete":
            if row["artifact"] in {"", "—", "-"}:
                if row["brief"] not in {"", "—", "-"}:
                    report.error(
                        f"completed analytical unit {row['work_id']} records "
                        "no artifact")
            else:
                artifact = Path(row["artifact"])
                if not artifact.is_file() or artifact.stat().st_size == 0:
                    report.error(f"completed unit {row['work_id']} has missing/empty artifact {artifact}")
        if row["state"] == "running" and row["artifact"] not in {"", "—", "-"}:
            writer = f"{row['work_id']}:{attempt}"
            previous = running_artifacts.setdefault(row["artifact"], writer)
            if previous != writer:
                report.error(
                    f"canonical artifact {row['artifact']} has concurrent writers "
                    f"{previous} and {writer}")
        latest[row["work_id"]] = row
    for work_id, values in attempts.items():
        if values != sorted(values) or len(values) != len(set(values)):
            report.error(f"manifest attempts for {work_id} are not unique and increasing")
    override = tier_override(root)
    frontier_kinds = re.compile(r"^(?:V\d+|VTER|RC\d+|CH\w*|VPLAN\w*|RCPLAN\w*|PLAN|PR)$")
    for work_id, values in attempts.items():
        ordered = [rows_by_key[(work_id, attempt)] for attempt in sorted(values)
                   if (work_id, attempt) in rows_by_key]
        recorded = [row.get("tier", "") for row in ordered
                    if row.get("tier", "") in TIER_ORDER]
        if frontier_kinds.match(work_id):
            for tier in recorded:
                if TIER_ORDER[tier] < TIER_ORDER["frontier"]:
                    message = (
                        f"work unit {work_id} is a frontier-contract kind but "
                        f"an attempt recorded tier '{tier}'")
                    report.warn(message + " under a user tier-override") \
                        if override else report.error(message)
                    break
        if recorded:
            first = recorded[0]
            for tier in recorded[1:]:
                if TIER_ORDER[tier] < TIER_ORDER[first]:
                    message = (
                        f"work unit {work_id} continuation dropped from tier "
                        f"'{first}' to '{tier}'")
                    report.warn(message + " under a user tier-override") \
                        if override else report.error(message)
                    break
        for attempt in sorted(values):
            if attempt == min(values):
                continue
            row = rows_by_key.get((work_id, attempt))
            if row is None:
                continue
            tokens = [item.strip() for item in
                      row.get("depends_on", "").split(",") if item.strip()
                      and item.strip() not in {"—", "-"}]
            prior_refs = [token for token in tokens
                          if re.fullmatch(rf"{re.escape(work_id)}:\d+", token)
                          and int(token.split(":")[1]) < attempt]
            if not prior_refs:
                report.error(
                    f"work unit {work_id} attempt {attempt} does not depend "
                    "on a prior attempt of the same unit")
            prior_attempts = [int(token.split(":")[1]) for token in prior_refs]
            for prior in prior_attempts:
                prior_row = rows_by_key.get((work_id, prior))
                if prior_row is None:
                    continue
                brief_now = row.get("brief", "")
                brief_prior = prior_row.get("brief", "")
                if brief_now not in {"", "—", "-"} and \
                        brief_now == brief_prior:
                    report.error(
                        f"work unit {work_id} attempt {attempt} reuses "
                        "attempt "
                        f"{prior}'s brief; continuations need an "
                        "attempt-specific brief with the explicit remainder")
    for row in rows:
        if row["state"] not in {"running", "complete"}:
            continue
        dependencies = row["depends_on"]
        if dependencies in {"", "—", "-"}:
            continue
        for dependency in (item.strip() for item in dependencies.split(",")):
            match = re.fullmatch(r"([^:]+):(\d+)", dependency)
            if match:
                dependency_row = rows_by_key.get((match.group(1), int(match.group(2))))
            else:
                dependency_row = latest.get(dependency)
            if dependency_row is None:
                report.error(f"work unit {row['work_id']} has unknown dependency {dependency}")
            elif dependency_row["state"] != "complete":
                is_attempt_handoff = (
                    match is not None
                    and match.group(1) == row["work_id"]
                    and dependency_row["state"]
                    in {"partial", "retryable", "needs-repair"}
                )
                if not is_attempt_handoff:
                    report.error(
                        f"work unit {row['work_id']} is {row['state']} while dependency "
                        f"{dependency} is {dependency_row['state']}")
    if final:
        for work_id, row in latest.items():
            if row["state"] not in {"complete", "terminated"}:
                report.error(f"work unit {work_id} is non-terminal at final validation: {row['state']}")


def validate_collection_coverage(root: Path, report: Report, level: int) -> None:
    """Prove spawn -> terminal attempt -> ledger -> collection disposition,
    joined at exact work-unit granularity, plus recorded-tier consistency."""
    plan_path = root / "plan.md"
    if not plan_path.is_file():
        return
    text = plan_path.read_text(encoding="utf-8")
    spawned: list[tuple[str, str, str]] = []  # (display name, work_id, tier)
    unreviewed: list[tuple[str, str]] = []  # (display name, work_id)
    for _, header, rows in table_dicts(text):
        if "roster entry" not in header or "status" not in header:
            continue
        for row in rows:
            status = row.get("status", "")
            if status.startswith("unreviewed"):
                entry = row["roster entry"]
                name = re.sub(r"\s+(?:\(shard[^)]*\)|—\s*shard.*)$", "",
                              entry, flags=re.I)
                prefix = ROSTER_PREFIX.get(name)
                if prefix:
                    shard = re.search(
                        r"(?:\((?:shard\s*)?|—\s*shard\s*)(\d+)", entry,
                        re.I)
                    unreviewed.append(
                        (entry, f"{prefix}{shard.group(1)}" if shard
                         else prefix))
                continue
            if status != "spawn":
                continue
            entry = row["roster entry"]
            name = re.sub(r"\s+(?:\(shard[^)]*\)|—\s*shard.*)$", "", entry,
                          flags=re.I)
            prefix = ROSTER_PREFIX.get(name)
            if not prefix:
                continue
            shard = re.search(
                r"(?:\((?:shard\s*)?|—\s*shard\s*)(\d+)", entry, re.I)
            shard_like = re.search(r"\(shard\b|—\s*shard\b", entry, re.I)
            if shard_like and not shard:
                report.error(
                    f"plan row '{entry}' has a shard-like label with no "
                    "shard number; it must not alias the unsharded work unit")
                continue
            work_id = f"{prefix}{shard.group(1)}" if shard else prefix
            spawned.append((entry, work_id, row.get("tier", "").strip()))
    if not spawned and not unreviewed:
        return
    work_ids = [work_id for _, work_id, _ in spawned]
    for duplicate in {w for w in work_ids if work_ids.count(w) > 1}:
        report.error(f"plan.md has duplicate spawn work unit {duplicate}")

    latest_row: dict[str, dict[str, str]] = {}
    tiers_by_work: dict[str, list[str]] = {}
    orchestration = root / "orchestration.tsv"
    if orchestration.is_file():
        try:
            with orchestration.open(encoding="utf-8", newline="") as stream:
                best: dict[str, int] = {}
                for row in csv.DictReader(stream, delimiter="\t"):
                    work_id = row.get("work_id", "")
                    try:
                        attempt = int(row.get("attempt", "0"))
                    except ValueError:
                        continue
                    tiers_by_work.setdefault(work_id, []).append(
                        row.get("tier", ""))
                    if attempt >= best.get(work_id, 0):
                        best[work_id] = attempt
                        latest_row[work_id] = row
        except OSError:
            pass

    audit_rows: dict[str, dict[str, str]] = {}
    audit_table_seen = False
    gap_units: dict[str, dict[str, str]] = {}
    audit_complete = False
    collection = root / "collection.md"
    if collection.is_file():
        collection_text = collection.read_text(encoding="utf-8")
        for heading, header, rows in table_dicts(collection_text):
            if heading == "Thread audit" and "thread" in header:
                audit_table_seen = True
                if list(header) != ["thread", "expected artifact", "matrix",
                                    "anomaly-to-candidate",
                                    "append/amendments", "verdict"]:
                    report.error(
                        "collection.md Thread audit table must have exactly "
                        "the ordered columns thread | expected artifact | "
                        "matrix | anomaly-to-candidate | append/amendments | "
                        "verdict")
                for row in rows:
                    thread = row.get("thread", "").strip()
                    if thread in audit_rows:
                        report.error(
                            f"collection.md Thread audit has duplicate rows "
                            f"for '{thread}'")
                    audit_rows[thread] = row
                    verdict = row.get("verdict", "").strip()
                    if verdict and verdict != "pass" and \
                            not verdict.startswith("gap"):
                        report.error(
                            f"collection.md Thread audit verdict for "
                            f"'{thread}' must be 'pass' or 'gap: ...', got "
                            f"'{verdict}'")
                    if verdict == "pass":
                        matrix = row.get("matrix", "").strip().lower()
                        anomaly = row.get(
                            "anomaly-to-candidate", "").strip().lower()
                        amendments = row.get(
                            "append/amendments", "").strip().lower()
                        if not matrix.startswith("complete") or \
                                not anomaly.startswith("complete") or \
                                not amendments.startswith("valid"):
                            report.error(
                                f"collection.md Thread audit row for "
                                f"'{thread}' is verdict pass but its cells "
                                "do not read complete/complete/valid")
            if heading == "Gaps" and "unit" in header:
                for row in rows:
                    unit = row.get("unit", "").strip()
                    if unit:
                        gap_units[unit] = row
        if not audit_table_seen:
            report.error("collection.md lacks a Thread audit table")
        if "## Audit result" not in collection_text:
            report.error("collection.md lacks an Audit result section")
        else:
            section = collection_text.split("## Audit result", 1)[1]
            section = section.split("\n## ", 1)[0]
            values = [line.strip().strip("`")
                      for line in section.splitlines() if line.strip()]
            if len(values) != 1 or values[0].lower() != "complete":
                report.error(
                    "collection.md Audit result section must contain exactly "
                    "one value line, the normalized token 'complete'; finish "
                    "repairs or record gaps as terminated — unreviewed before "
                    "this gate")
            else:
                audit_complete = True

    override = tier_override(root)
    for entry, work_id, plan_tier in spawned:
        expected_ledger = (root / "ledger" / f"{work_id}.md").resolve()
        if not expected_ledger.is_file():
            report.error(
                f"spawned work unit '{entry}' has no ledger/{work_id}.md "
                "artifact")
        if work_id not in latest_row:
            report.error(
                f"spawned work unit '{entry}' has no orchestration.tsv attempt")
        else:
            row = latest_row[work_id]
            if row.get("state", "") not in {"complete", "terminated"}:
                report.error(
                    f"spawned work unit '{entry}' has no terminal "
                    "orchestration attempt (complete/terminated)")
            artifact = row.get("artifact", "")
            if row.get("state", "") == "complete" and (
                    artifact in {"", "—", "-"}
                    or Path(artifact).resolve() != expected_ledger):
                report.error(
                    f"work unit {work_id}'s completed attempt artifact "
                    f"'{artifact}' is not ledger/{work_id}.md")
        if audit_table_seen:
            row = audit_rows.get(work_id)
            if row is None:
                report.error(
                    f"collection.md Thread audit has no row for spawned work "
                    f"unit '{work_id}'")
            else:
                if not row.get("verdict", "").strip():
                    report.error(
                        f"collection.md Thread audit row for '{work_id}' has "
                        "an empty verdict")
                expected_cell = f"ledger/{work_id}.md"
                if row.get("expected artifact", "").strip() != expected_cell:
                    report.error(
                        f"collection.md Thread audit row for '{work_id}' "
                        f"names expected artifact "
                        f"'{row.get('expected artifact', '').strip()}', not "
                        f"{expected_cell}")
        if plan_tier in TIER_ORDER:
            for attempt_tier in tiers_by_work.get(work_id, []):
                if attempt_tier == "inherit" or attempt_tier not in TIER_ORDER:
                    continue
                if TIER_ORDER[attempt_tier] < TIER_ORDER[plan_tier]:
                    if override:
                        report.warn(
                            f"work unit {work_id} attempt ran at "
                            f"{attempt_tier}, below its planned {plan_tier} "
                            "tier, under a user tier-override")
                    else:
                        report.error(
                            f"work unit {work_id} attempt ran at "
                            f"{attempt_tier}, below its planned {plan_tier} "
                            "tier, with no tier-override in directives.md")

    for thread, row in sorted(audit_rows.items()):
        verdict = row.get("verdict", "").strip()
        if verdict.startswith("gap") and thread not in gap_units:
            report.error(
                f"collection.md Thread audit records a gap for '{thread}' "
                "with no matching Gaps row")
        if verdict == "pass" and thread in gap_units:
            report.error(
                f"collection.md Thread audit row '{thread}' is verdict pass "
                "but a Gaps row exists for it")
    unreviewed_units = {work_id for _, work_id in unreviewed}
    for unit in sorted(gap_units):
        row = audit_rows.get(unit)
        has_gap_verdict = bool(row) and \
            row.get("verdict", "").strip().startswith("gap")
        if not has_gap_verdict and unit not in unreviewed_units:
            report.error(
                f"collection.md Gaps row '{unit}' matches neither a "
                "gap-verdict audit row nor an unreviewed plan row")
    if audit_complete:
        for unit in sorted(gap_units):
            row = latest_row.get(unit, {})
            state = row.get("state", "")
            if state != "terminated":
                report.error(
                    f"collection.md Audit result is complete while gap unit "
                    f"'{unit}' is not terminated in orchestration.tsv "
                    f"(state '{state or 'absent'}')")
            else:
                gap_scope = gap_units[unit].get(
                    "exact remaining scope", "").strip()
                remaining = row.get("remaining_scope", "").strip()
                if gap_scope and remaining and gap_scope != remaining:
                    report.error(
                        f"gap unit '{unit}' scope '{gap_scope}' does not "
                        f"equal its terminated attempt's remaining_scope "
                        f"'{remaining}'")
    for entry, work_id in unreviewed:
        state = latest_row.get(work_id, {}).get("state", "")
        if state != "terminated":
            report.error(
                f"unreviewed plan row '{entry}' has no terminated "
                f"orchestration attempt for {work_id} (state "
                f"'{state or 'absent'}')")
        if audit_table_seen and work_id not in gap_units:
            report.error(
                f"unreviewed plan row '{entry}' has no matching collection "
                f"Gaps row for {work_id}")


def validate_ter_gate(root: Path, report: Report) -> None:
    """TER completeness: spawned TER must produce its gate tables; classes
    need PROVEN/REJECTED/UNPROVEN VTER verdicts with execution provenance;
    class x file membership is reconciled; residue scoping is fail-closed."""
    plan_path = root / "plan.md"
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    ter_spawned = False
    plan_rows: list[dict[str, str]] = []
    for _, header, rows in table_dicts(plan_text):
        if "roster entry" not in header or "status" not in header:
            continue
        for row in rows:
            plan_rows.append(row)
            name = re.sub(r"\s+(?:\(shard[^)]*\)|—\s*shard.*)$", "",
                          row.get("roster entry", ""), flags=re.I)
            if ROSTER_PREFIX.get(name) == "TER" and row.get("status") == "spawn":
                ter_spawned = True

    class_files: dict[str, list[str]] = {}
    sentinel_seen = False
    membership: dict[tuple[str, str], int] = {}
    ledger = root / "ledger"
    ter_paths = sorted(ledger.glob("TER*.md")) if ledger.exists() else []
    per_shard_ok: dict[Path, dict[str, bool]] = {}
    for path in ter_paths:
        text = read_text(path, report)
        shard_state = per_shard_ok.setdefault(
            path, {"classes_heading": False, "residue_heading": False,
                   "content": False})
        if "## Transformation classes" in text:
            shard_state["classes_heading"] = True
        if "## Residue" in text:
            shard_state["residue_heading"] = True
        for heading, header, rows in table_dicts(text):
            if heading == "Transformation classes" and "class id" in header:
                for row in rows:
                    identifier = row.get("class id", "").strip()
                    if identifier in {"—", "-", "none"}:
                        if shard_state["content"]:
                            report.error(
                                f"{path}: sentinel row coexists with other "
                                "class rows in this shard")
                        sentinel_seen = True
                        shard_state["content"] = True
                        if row.get("members", "").strip() != "0":
                            report.error(
                                f"{path}: no-classes sentinel row must have "
                                "member count 0")
                        if row.get("files", "").strip() not in {"—", "-", ""}:
                            report.error(
                                f"{path}: no-classes sentinel row must not "
                                "name files")
                        if row.get("proof", "").strip().strip("—-") == "":
                            report.error(
                                f"{path}: no-classes sentinel row needs "
                                "concrete scan evidence in its proof cell, "
                                "not a placeholder")
                        continue
                    if not re.fullmatch(r"TC\d+", identifier):
                        if identifier:
                            report.error(
                                f"{path}: invalid transformation class ID "
                                f"'{identifier}'")
                        continue
                    if identifier in class_files:
                        report.error(f"{path}: duplicate class {identifier}")
                    shard_state["content"] = True
                    files = [item.strip() for item in
                             re.split(r"[;,]", row.get("files", ""))
                             if item.strip() and item.strip() not in {"—", "-"}]
                    if len(files) != len(set(files)):
                        report.error(
                            f"{path}: class {identifier} lists duplicate "
                            "files")
                    class_files[identifier] = files
                    if not files:
                        report.error(
                            f"{path}: class {identifier} lists no files; the "
                            "files cell must be an explicit path list")
                    members = row.get("members", "").strip()
                    if not members.isdigit() or int(members) < len(files):
                        report.error(
                            f"{path}: class {identifier} member count "
                            f"'{members}' is missing or below its file count")
            if "id" in header and "status" in header:
                for row in rows:
                    status = row.get("status", "")
                    match = re.match(
                        r"(?:clean|mixed)\s*\(class (TC\d+)", status)
                    if not match:
                        continue
                    location = row.get("location", "")
                    file_path = location.split(":", 1)[0].strip()
                    key = (match.group(1), file_path)
                    membership[key] = membership.get(key, 0) + 1

    if ter_spawned:
        if not ter_paths:
            report.error("TER is spawned but no ledger/TER*.md exists")
        for path, shard_state in sorted(per_shard_ok.items()):
            if not shard_state["classes_heading"]:
                report.error(
                    f"{path} lacks a Transformation classes table")
            if not shard_state["residue_heading"]:
                report.error(f"{path} lacks a Residue section")
            if shard_state["classes_heading"] and not shard_state["content"]:
                report.error(
                    f"{path}: Transformation classes table has neither a "
                    "valid TC class nor the explicit no-classes sentinel row")
    if sentinel_seen and class_files:
        report.error(
            "a no-classes sentinel row coexists with real transformation "
            "classes")

    for class_id, files in sorted(class_files.items()):
        for file_path in files:
            count = membership.get((class_id, file_path), 0)
            if count == 0:
                report.error(
                    f"class {class_id} lists {file_path} but has no "
                    "clean/mixed membership row for it")
            elif count > 1:
                report.error(
                    f"class {class_id} has {count} membership rows for "
                    f"{file_path}")
    for (class_id, file_path) in sorted(membership):
        if class_id in class_files and file_path not in class_files[class_id]:
            report.error(
                f"membership row cites {file_path} which class {class_id} "
                "does not list")
        if class_id not in class_files:
            report.error(
                f"membership row cites unknown class {class_id}")

    gate = root / "verification" / "VTER.md"
    gate_verdicts: dict[str, str] = {}
    if class_files and not gate.is_file():
        report.error(
            "TER produced transformation classes but verification/VTER.md "
            "is missing")
    if gate.is_file():
        gate_table_seen = False
        seen_gate_ids: set[str] = set()
        for _, header, rows in table_dicts(read_text(gate, report)):
            if not {"id", "class", "verdict", "evidence"}.issubset(header):
                continue
            if list(header) != ["id", "class", "verdict", "evidence"]:
                report.error(
                    "VTER.md gate table must have exactly the ordered "
                    "columns id | class | verdict | evidence")
            gate_table_seen = True
            for row in rows:
                row_id = row.get("id", "").strip()
                if not re.fullmatch(r"VTER-\d+", row_id):
                    report.error(f"VTER.md row ID '{row_id}' is not VTER-<n>")
                elif row_id in seen_gate_ids:
                    report.error(f"VTER.md duplicates row ID {row_id}")
                seen_gate_ids.add(row_id)
                identifier = row.get("class", "").strip()
                verdict = row.get("verdict", "").strip()
                evidence = row.get("evidence", "")
                if identifier in gate_verdicts:
                    report.error(
                        f"VTER.md has duplicate verdict for {identifier}")
                gate_verdicts[identifier] = verdict
                if verdict not in GATE_VERDICTS:
                    report.error(
                        f"VTER.md verdict '{verdict}' for {identifier} is "
                        "not PROVEN/REJECTED/UNPROVEN")
                if verdict in {"PROVEN", "REJECTED"} and not CITATION.search(
                        evidence):
                    report.error(
                        f"VTER.md {verdict} verdict for {identifier} has no "
                        "path:line citation — the gate accepts no "
                        "evidence-exception")
                if identifier not in class_files:
                    report.error(
                        f"VTER.md verdict targets unknown transformation "
                        f"class {identifier}")
        if not gate_table_seen:
            report.error(
                "VTER.md lacks the id | class | verdict | evidence gate table")
        for class_id in sorted(set(class_files) - set(gate_verdicts)):
            report.error(
                f"transformation class {class_id} has no VTER gate verdict")

        # Execution provenance: a hand-written gate file must not count.
        vter_row = None
        orchestration = root / "orchestration.tsv"
        if orchestration.is_file():
            try:
                with orchestration.open(encoding="utf-8", newline="") as stream:
                    best = -1
                    for row in csv.DictReader(stream, delimiter="\t"):
                        if row.get("work_id") != "VTER":
                            continue
                        try:
                            attempt = int(row.get("attempt", "0"))
                        except ValueError:
                            continue
                        if attempt > best:
                            best = attempt
                            vter_row = row
            except OSError:
                pass
        if vter_row is None:
            report.error(
                "verification/VTER.md exists without a VTER orchestration "
                "work unit — the gate has no execution provenance")
        else:
            if vter_row.get("state") != "complete":
                report.error("VTER work unit is not complete")
            if vter_row.get("tier") not in {"frontier", "inherit"}:
                report.error(
                    f"VTER work unit recorded tier "
                    f"'{vter_row.get('tier')}'; the gate is frontier-only")
            artifact = vter_row.get("artifact", "")
            if artifact in {"", "—", "-"} or \
                    Path(artifact).resolve() != gate.resolve():
                report.error(
                    "VTER work unit's artifact is not verification/VTER.md")
            if vter_row.get("brief", "") in {"", "—", "-"}:
                report.error("VTER work unit has no brief")
            dependencies = vter_row.get("depends_on", "")
            tokens = [item.strip().split(":", 1)[0]
                      for item in dependencies.split(",") if item.strip()]
            if "VTERB" not in tokens:
                report.error(
                    "VTER work unit does not depend on the gate-brief "
                    "builder (VTERB)")

        ter_units = set()
        vterb_row = None
        if orchestration.is_file():
            try:
                with orchestration.open(encoding="utf-8", newline="") as stream:
                    for row in csv.DictReader(stream, delimiter="\t"):
                        work = row.get("work_id", "")
                        if re.fullmatch(r"TER\d*", work):
                            ter_units.add(work)
                        if work == "VTERB":
                            vterb_row = row
            except OSError:
                pass
        if vterb_row is None:
            report.error(
                "verification/VTER.md exists without a VTERB gate-brief "
                "builder work unit")
        else:
            if vterb_row.get("state") != "complete":
                report.error("VTERB work unit is not complete")
            builder_tokens = {
                item.strip().split(":", 1)[0]
                for item in vterb_row.get("depends_on", "").split(",")
                if item.strip() and item.strip() not in {"—", "-"}}
            for missing in sorted(ter_units - builder_tokens):
                report.error(
                    f"VTERB does not depend on spawned TER work unit "
                    f"{missing}; the builder must consume every TER shard")

    for row in plan_rows:
        if row.get("status", "") != "spawn":
            continue
        scope = row.get("scope", "").strip()
        match = RESIDUE_SCOPE.match(scope)
        if match:
            for class_id in (item.strip() for item in
                             match.group(1).split(",")):
                if gate_verdicts.get(class_id) != "PROVEN":
                    report.error(
                        f"plan row '{row['roster entry']}' is residue-scoped "
                        f"to {class_id} without a PROVEN VTER gate verdict")
            entry = row["roster entry"]
            name = re.sub(r"\s+(?:\(shard[^)]*\)|—\s*shard.*)$", "",
                          entry, flags=re.I)
            prefix = ROSTER_PREFIX.get(name)
            if prefix:
                shard = re.search(
                    r"(?:\((?:shard\s*)?|—\s*shard\s*)(\d+)", entry, re.I)
                residue_unit = f"{prefix}{shard.group(1)}" if shard else prefix
                dependent = False
                orchestration = root / "orchestration.tsv"
                if orchestration.is_file():
                    try:
                        with orchestration.open(
                                encoding="utf-8", newline="") as stream:
                            for orow in csv.DictReader(stream, delimiter="\t"):
                                if orow.get("work_id") != residue_unit:
                                    continue
                                bases = {
                                    item.strip().split(":", 1)[0]
                                    for item in
                                    orow.get("depends_on", "").split(",")
                                    if item.strip()}
                                if bases & {"VTER", "PLAN"}:
                                    dependent = True
                    except OSError:
                        pass
                if not dependent:
                    report.error(
                        f"residue-scoped work unit {residue_unit} has no "
                        "orchestration attempt depending on VTER or the "
                        "round-two Planner")
        elif re.match(r"residue", scope, re.I):
            report.error(
                f"plan row '{row['roster entry']}' has a malformed "
                f"residue scope '{scope}'; the required form is "
                "'residue(TC<ids>): <exact scope>'")


def ledger_data(root: Path, report: Report) -> tuple[dict[str, Path], set[str], set[str]]:
    source_ids: dict[str, Path] = {}
    candidate_ids: set[str] = set()
    covered_files: set[str] = set()

    def add(identifier: str, path: Path) -> None:
        if identifier in source_ids:
            report.error(f"duplicate row ID {identifier}: {source_ids[identifier]} and {path}")
        else:
            source_ids[identifier] = path

    ledger_paths = sorted((root / "ledger").glob("**/*.md")) if (root / "ledger").exists() else []
    if not ledger_paths:
        report.error("no ledger/*.md artifacts found")
    for path in ledger_paths:
        text = read_text(path, report)
        relative = path.relative_to(root / "ledger")
        if relative.as_posix() == "PR.md":
            if "## Prior-feedback rows" not in text or "## Candidate rows" not in text:
                report.error(f"{path} lacks exact Prior-feedback rows/Candidate rows headings")
        elif relative.parts and relative.parts[0] == "reopened":
            if "## Candidate rows" not in text:
                report.error(f"{path} lacks exact Candidate rows heading")
        elif "## Compliance matrix" not in text or "## Candidate rows" not in text:
            report.error(f"{path} lacks exact Compliance matrix/Candidate rows headings")
        for heading, header, rows in table_dicts(text):
            if heading == "Compliance matrix":
                for index, row in enumerate(rows, 1):
                    answer = row.get("answer", "")
                    evidence = row.get("evidence", "")
                    if not answer or not evidence:
                        report.error(f"{path}: compliance matrix row {index} has a blank answer/evidence")
                    if re.fullmatch(r"(?i)(yes|pass|clean|safe)(?:\s*[—-].*)?", answer) and not CITATION.search(evidence):
                        report.error(f"{path}: compliance matrix row {index} is a citation-free PASS")
                    if answer.upper().startswith("N/A") and not re.search(r"[—:-]\s*\S", answer):
                        report.error(f"{path}: compliance matrix row {index} has N/A without a reason")
            if heading == "Prior-feedback rows" and "id" in header:
                for row in rows:
                    identifier = row.get("id", "")
                    if not ROW_ID.fullmatch(identifier):
                        report.error(f"{path}: invalid prior-feedback row ID '{identifier}'")
                    else:
                        add(identifier, path)
            if heading == "Candidate rows" and "id" in header:
                for row in rows:
                    identifier = row.get("id", "")
                    if not ROW_ID.fullmatch(identifier):
                        report.error(f"{path}: invalid candidate row ID '{identifier}'")
                        continue
                    # A still-open PR row appears in both Prior-feedback rows
                    # and Candidate rows by design; it is one source row.
                    if identifier not in source_ids:
                        add(identifier, path)
                    elif source_ids[identifier] != path or not identifier.startswith("PR-"):
                        report.error(f"duplicate row ID {identifier}: {source_ids[identifier]} and {path}")
                    status = row.get("status", "").lower()
                    if "candidate" in status or "reopened" in status:
                        candidate_ids.add(identifier)
                    location = row.get("location", "")
                    match = CITATION.search(location)
                    if match:
                        covered_files.add(match.group(1))

    collection = root / "collection.md"
    if collection.exists():
        text = read_text(collection, report)
        for _, header, rows in table_dicts(text):
            if "id" not in header:
                continue
            for row in rows:
                identifier = row.get("id", "")
                if not ROW_ID.fullmatch(identifier) or not identifier.startswith("ORC"):
                    continue
                add(identifier, collection)
                status = row.get("status", "").lower()
                if "candidate" in status or "reopened" in status:
                    candidate_ids.add(identifier)
                match = CITATION.search(row.get("location", ""))
                if match:
                    covered_files.add(match.group(1))
    else:
        report.error("missing required artifact: collection.md")

    verification = root / "verification"
    verification_paths = [
        path for path in (sorted(verification.glob("V*.md"))
                          if verification.exists() else [])
        if path.name != "VTER.md"
    ]
    for path in verification_paths:
        text = read_text(path, report)
        for _, header, rows in table_dicts(text):
            if not {"id", "candidate", "verdict"}.issubset(header):
                continue
            for row in rows:
                identifier = row.get("id", "")
                if ROW_ID.fullmatch(identifier):
                    add(identifier, path)

    root_cause = root / "root-cause"
    for path in sorted(root_cause.glob("RC*.md")) if root_cause.exists() else []:
        text = read_text(path, report)
        for identifier in re.findall(r"^## (RC[0-9]+-[0-9]+)\b", text, re.MULTILINE):
            add(identifier, path)
        for heading, header, rows in table_dicts(text):
            if heading == "Reopened candidate rows" and "id" in header:
                for row in rows:
                    identifier = row.get("id", "")
                    if ROW_ID.fullmatch(identifier):
                        add(identifier, path)
                        candidate_ids.add(identifier)
                        match = CITATION.search(row.get("location", ""))
                        if match:
                            covered_files.add(match.group(1))
    return source_ids, candidate_ids, covered_files


def validate_verdicts(root: Path, candidates: set[str], report: Report) -> None:
    verdicts: Counter[str] = Counter()
    for path in sorted((root / "verification").glob("V*.md")):
        if path.name == "VTER.md":
            continue
        for _, header, rows in table_dicts(read_text(path, report)):
            if {"candidate", "verdict"}.issubset(header):
                for row in rows:
                    candidate = row.get("candidate", "")
                    verdict = row.get("verdict", "")
                    if candidate:
                        verdicts[candidate] += 1
                    if verdict not in {"CONFIRMED", "REFUTED", "UNPROVEN"}:
                        report.error(f"{path}: invalid verdict '{verdict}' for {candidate}")
                    evidence = row.get("evidence", "")
                    if verdict in {"CONFIRMED", "REFUTED"}:
                        if not CITATION.search(evidence) and not EVIDENCE_EXCEPTION.search(evidence):
                            report.error(
                                f"{path}: {verdict} verdict for {candidate} has no "
                                "path:line citation or evidence-exception")
                    elif not evidence or not CITATION.search(evidence):
                        report.warn(f"{path}: verdict for {candidate} has no path:line detectable by validator")

    merged: dict[str, str] = {}
    batches = root / "verification" / "batches.md"
    if batches.exists():
        for heading, header, rows in table_dicts(read_text(batches, report)):
            if heading.startswith("Merge proposals") and {"row", "proposal"}.issubset(header):
                for row in rows:
                    match = re.match(rf"merge-into\s+({ROW_ID_TEXT})", row["proposal"])
                    if match:
                        merged[row["row"]] = match.group(1)
    for candidate in sorted(candidates):
        if verdicts[candidate] == 0:
            survivor = merged.get(candidate)
            if not survivor or verdicts[survivor] != 1:
                report.error(f"candidate {candidate} has no verdict and no verdict-covered merge survivor")
        elif verdicts[candidate] > 1:
            report.error(f"candidate {candidate} has {verdicts[candidate]} verdict rows")
    for candidate in verdicts:
        if candidate not in candidates:
            report.error(f"verdict references unknown/non-candidate row {candidate}")

    known_rows = candidates | set(verdicts)
    for path in sorted((root / "briefs").glob("**/*.md")):
        for reopened_id in set(re.findall(r"R\d+-RC\d+-\d+", read_text(path, report))):
            if reopened_id not in known_rows:
                report.error(f"{path} references non-canonical reopened row {reopened_id}")


def validate_reconciliation(root: Path, source_ids: dict[str, Path], report: Report,
                            final: bool) -> None:
    path = root / "reconciliation.md"
    text = read_text(path, report)
    dispositions: Counter[str] = Counter()
    for _, header, rows in table_dicts(text):
        if {"row", "disposition"}.issubset(header):
            for row in rows:
                identifier = row.get("row", "")
                if ROW_ID.fullmatch(identifier):
                    dispositions[identifier] += 1
                    if not row.get("disposition"):
                        report.error(f"reconciliation row {identifier} has blank disposition")
    for identifier in sorted(source_ids):
        if dispositions[identifier] != 1:
            report.error(f"row {identifier} has {dispositions[identifier]} reconciliation dispositions")
    for identifier in dispositions:
        if identifier not in source_ids:
            report.error(f"reconciliation references unknown row {identifier}")

    if final:
        gate = text.split("## Pre-output gate", 1)
        if len(gate) != 2:
            report.error("reconciliation.md lacks ## Pre-output gate")
        else:
            answers = {}
            for line in gate[1].splitlines():
                match = re.match(r"^(\d+)\.\s+\*\*[^*]+:\*\*\s*(.*)$", line)
                if match:
                    answers[int(match.group(1))] = match.group(2)
            for number in range(1, 14):
                answer = answers.get(number, "")
                if not re.match(r"(?i)^yes\b", answer):
                    report.error(
                        f"pre-output gate line {number} is not affirmatively complete")


def validate_synthesis(root: Path, source_ids: dict[str, Path],
                       budgets: dict[str, int], report: Report) -> set[str]:
    index = root / "synthesis" / "index.md"
    text = read_text(index, report)
    cards: set[str] = set()
    total_bytes = 0
    evidence_budget = budgets.get("evidence_card_budget_bytes")
    worker_budget = budgets.get("worker_input_budget_bytes")
    for _, header, rows in table_dicts(text):
        if not {"item", "card", "bytes", "source rows"}.issubset(header):
            continue
        for row in rows:
            item = row["item"]
            if item in cards:
                report.error(f"synthesis/index.md duplicates item {item}")
            cards.add(item)
            card = root / row["card"]
            if not card.is_file():
                report.error(f"synthesis card is missing: {card}")
                continue
            actual = card.stat().st_size
            total_bytes += actual
            if evidence_budget is not None and actual > evidence_budget:
                report.error(
                    f"synthesis card exceeds profile evidence-card budget: "
                    f"{card} ({actual} > {evidence_budget} bytes)"
                )
            try:
                declared = int(row["bytes"])
                if declared != actual:
                    report.error(f"synthesis card byte count mismatch for {card}: {declared} != {actual}")
            except ValueError:
                report.error(f"synthesis/index.md has invalid byte count for {item}")
            for source in (part.strip() for part in row["source rows"].split(",")):
                if source and source not in source_ids:
                    report.error(f"synthesis item {item} cites unknown source row {source}")
    if not cards and source_ids:
        report.warn("synthesis/index.md contains no evidence-card rows")
    if len(cards) > 12 or (worker_budget is not None and total_bytes > worker_budget):
        parts = root / "draft-parts"
        assembly = root / "draft-assembly" / "manifest.md"
        if not parts.is_dir() or not any(parts.glob("*.md")):
            report.error("large synthesis handoff lacks draft-parts/*.md")
        elif not (parts / "FRAME.md").is_file():
            report.error("large synthesis handoff lacks required draft-parts/FRAME.md")
        for item in sorted(cards):
            if not (parts / f"{item}.md").is_file():
                report.error(f"large synthesis handoff lacks draft part for {item}")
        assembly_text = read_text(assembly, report)
        found_nodes = False
        found_root = False
        for _, header, rows in table_dicts(assembly_text):
            if not {"node", "inputs", "input bytes", "output", "status"}.issubset(header):
                continue
            found_nodes = True
            for row in rows:
                raw_inputs = row["inputs"]
                if re.search(r"\*|\.\.\.", raw_inputs):
                    report.error(
                        f"assembly node {row['node']} uses a glob/range instead of "
                        "exact child paths"
                    )
                child_values = [
                    item.strip().strip("`") for item in raw_inputs.split(",")
                    if item.strip()
                ]
                if len(child_values) != len(set(child_values)):
                    report.error(f"assembly node {row['node']} repeats a child path")
                actual_input_bytes = 0
                for child_value in dict.fromkeys(child_values):
                    child = Path(child_value)
                    child = child if child.is_absolute() else root / child
                    if not child.is_file():
                        report.error(
                            f"assembly node {row['node']} has missing child {child}"
                        )
                    else:
                        actual_input_bytes += child.stat().st_size
                try:
                    node_bytes = int(row["input bytes"])
                    if node_bytes != actual_input_bytes:
                        report.error(
                            f"assembly node {row['node']} input bytes mismatch: "
                            f"{node_bytes} != {actual_input_bytes}"
                        )
                    if (worker_budget is not None
                            and actual_input_bytes > worker_budget):
                        report.error(
                            f"assembly node {row['node']} exceeds profile worker-input "
                            f"budget ({actual_input_bytes} > {worker_budget} bytes)"
                        )
                except ValueError:
                    report.error(f"assembly node {row['node']} has invalid input bytes")
                child_count = len(child_values)
                if child_count > 12:
                    report.error(f"assembly node {row['node']} has {child_count} children")
                if row["status"] != "complete":
                    report.error(f"assembly node {row['node']} is not complete")
                if "draft-review.md" in row["output"]:
                    found_root = True
                    if "FRAME.md" not in row["inputs"]:
                        report.error("root assembly node does not directly include FRAME.md")
        if not found_nodes:
            report.error("large synthesis handoff lacks a valid assembly manifest")
        elif not found_root:
            report.error("large synthesis handoff lacks a root draft-review assembly node")
    return cards


DRAFT_SECTION_COLUMNS = (
    "revision", "order", "section", "type", "draft_path", "draft_bytes",
    "draft_sha256", "gerrit_path", "gerrit_bytes", "gerrit_sha256", "cards",
    "rows", "global_frame",
)


def validate_draft_sections(root: Path, draft_revision: str,
                            worker_budget: int | None,
                            report: Report) -> dict[str, dict[str, str]]:
    """Validate immutable large-draft sections and exact root concatenation."""
    draft = root / "draft-review.md"
    gerrit = root / "gerrit-comments.md"
    index = root / "draft-sections" / "index.tsv"
    root_is_large = (
        worker_budget is not None
        and ((draft.is_file() and draft.stat().st_size > worker_budget)
             or (gerrit.is_file() and gerrit.stat().st_size > worker_budget))
    )
    if not index.exists():
        if root_is_large:
            report.error(
                "large draft exceeds profile worker-input budget but lacks "
                "draft-sections/index.tsv"
            )
        return {}

    try:
        with index.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            if tuple(reader.fieldnames or ()) != DRAFT_SECTION_COLUMNS:
                report.error("draft-sections/index.tsv has wrong columns or order")
                return {}
            rows = list(reader)
    except (OSError, csv.Error) as error:
        report.error(f"cannot parse draft-sections/index.tsv: {error}")
        return {}
    if not rows:
        report.error("draft-sections/index.tsv contains no section rows")
        return {}

    sections: dict[str, dict[str, str]] = {}
    ordered_fragments: list[tuple[int, bytes, bytes]] = []
    orders: set[int] = set()
    draft_paths: set[str] = set()
    gerrit_paths: set[str] = set()
    global_frames = 0

    def artifact(value: str, label: str, line_number: int,
                 allow_empty: bool = False) -> Path | None:
        if allow_empty and value == "-":
            return None
        candidate = Path(value)
        if (not value or value in {"—", "-"} or candidate.is_absolute()
                or ".." in candidate.parts):
            report.error(
                f"draft-sections/index.tsv:{line_number}: invalid {label} '{value}'"
            )
            return None
        path = root / candidate
        if not path.is_file():
            report.error(
                f"draft-sections/index.tsv:{line_number}: missing {label} {path}"
            )
            return None
        return path

    for line_number, row in enumerate(rows, 2):
        identifier = row["section"]
        if not re.fullmatch(r"[A-Z][A-Z0-9_-]*", identifier):
            report.error(
                f"draft-sections/index.tsv:{line_number}: invalid section '{identifier}'"
            )
            continue
        if identifier in sections:
            report.error(f"draft-sections/index.tsv duplicates section {identifier}")
            continue
        sections[identifier] = row
        try:
            order = int(row["order"])
            if order < 1:
                raise ValueError
        except ValueError:
            report.error(f"draft section {identifier} has invalid order '{row['order']}'")
            order = line_number - 1
        if order in orders:
            report.error(f"draft-sections/index.tsv duplicates order {order}")
        orders.add(order)
        if row["revision"] != draft_revision:
            report.error(
                f"draft section {identifier} revision {row['revision']} does not match "
                f"draft revision {draft_revision or 'missing'}"
            )
        if row["global_frame"] not in {"yes", "no"}:
            report.error(f"draft section {identifier} has invalid global_frame value")
        elif row["global_frame"] == "yes":
            global_frames += 1

        draft_path = artifact(row["draft_path"], "draft_path", line_number)
        gerrit_path = artifact(
            row["gerrit_path"], "gerrit_path", line_number, allow_empty=True
        )
        if row["draft_path"] in draft_paths:
            report.error(f"draft-sections/index.tsv reuses draft_path {row['draft_path']}")
        draft_paths.add(row["draft_path"])
        if row["gerrit_path"] != "-":
            if row["gerrit_path"] in gerrit_paths:
                report.error(
                    f"draft-sections/index.tsv reuses gerrit_path {row['gerrit_path']}"
                )
            gerrit_paths.add(row["gerrit_path"])

        draft_payload = b""
        gerrit_payload = b""
        if draft_path is not None:
            draft_payload = draft_path.read_bytes()
            try:
                declared_bytes = int(row["draft_bytes"])
                if declared_bytes != len(draft_payload):
                    report.error(
                        f"draft section {identifier} draft byte count mismatch: "
                        f"{declared_bytes} != {len(draft_payload)}"
                    )
            except ValueError:
                report.error(f"draft section {identifier} has invalid draft_bytes value")
            actual_hash = hashlib.sha256(draft_payload).hexdigest()
            if not re.fullmatch(r"[0-9a-f]{64}", row["draft_sha256"]):
                report.error(f"draft section {identifier} has invalid draft_sha256")
            elif row["draft_sha256"] != actual_hash:
                report.error(
                    f"draft section {identifier} draft_sha256 mismatch: "
                    f"{row['draft_sha256']} != {actual_hash}"
                )
        if gerrit_path is not None:
            gerrit_payload = gerrit_path.read_bytes()
        if gerrit_path is not None or row["gerrit_path"] == "-":
            try:
                declared_bytes = int(row["gerrit_bytes"])
                if declared_bytes != len(gerrit_payload):
                    report.error(
                        f"draft section {identifier} Gerrit byte count mismatch: "
                        f"{declared_bytes} != {len(gerrit_payload)}"
                    )
            except ValueError:
                report.error(f"draft section {identifier} has invalid gerrit_bytes value")
            actual_hash = hashlib.sha256(gerrit_payload).hexdigest()
            if not re.fullmatch(r"[0-9a-f]{64}", row["gerrit_sha256"]):
                report.error(f"draft section {identifier} has invalid gerrit_sha256")
            elif row["gerrit_sha256"] != actual_hash:
                report.error(
                    f"draft section {identifier} gerrit_sha256 mismatch: "
                    f"{row['gerrit_sha256']} != {actual_hash}"
                )
        ordered_fragments.append((order, draft_payload, gerrit_payload))

    if global_frames != 1:
        report.error(
            f"draft-sections/index.tsv has {global_frames} global-frame sections, expected 1"
        )
    if orders != set(range(1, len(rows) + 1)):
        report.error(
            "draft-sections/index.tsv order values are not unique contiguous 1..N"
        )
    ordered_fragments.sort(key=lambda item: item[0])
    if (draft.is_file()
            and b"".join(item[1] for item in ordered_fragments) != draft.read_bytes()):
        report.error("draft-review.md is not the exact indexed section concatenation")
    if (gerrit.is_file()
            and b"".join(item[2] for item in ordered_fragments) != gerrit.read_bytes()):
        report.error("gerrit-comments.md is not the exact indexed section concatenation")
    return sections


def validate_final(root: Path, sha: str | None, source_ids: dict[str, Path],
                   synthesis_items: set[str], budgets: dict[str, int],
                   input_assignments: dict[str, list[dict[str, str]]],
                   report: Report) -> None:
    draft = read_text(root / "draft-review.md", report)
    gerrit = read_text(root / "gerrit-comments.md", report)
    if sha and sha not in draft:
        report.error("draft-review.md does not state the full pinned revision SHA")
    if not re.search(r"(?i)patchset\s+\d+|PS\d+", draft):
        report.error("draft-review.md does not state the reviewed patchset")
    draft_revision = field(draft, "Draft revision") or ""
    if not re.fullmatch(r"[1-9]\d*", draft_revision):
        report.error("draft-review.md lacks a positive integer Draft revision")
    if re.search(r"(?:file://|/(?:tmp|home)/|<[^>]+>)", gerrit):
        report.error("gerrit-comments.md contains a local path/URL or placeholder inline")
    sections = validate_draft_sections(
        root, draft_revision, budgets.get("worker_input_budget_bytes"), report
    )
    synthesis_card_paths: dict[str, Path] = {}
    synthesis_index = root / "synthesis" / "index.md"
    if synthesis_index.is_file():
        for _, header, rows in table_dicts(read_text(synthesis_index, report)):
            if {"item", "card"}.issubset(header):
                for row in rows:
                    synthesis_card_paths[row["item"]] = (root / row["card"]).resolve()
    delivery = root / "delivery-gate.md"
    delivery_text = read_text(delivery, report)
    pinned_value = field(delivery_text, "Pinned") or ""
    current_value = field(delivery_text, "Gerrit current") or ""
    pinned_match = re.search(r"\b[0-9a-fA-F]{40,64}\b", pinned_value)
    current_match = re.search(r"\b[0-9a-fA-F]{40,64}\b", current_value)
    pinned_delivery_sha = pinned_match.group(0) if pinned_match else None
    current_delivery_sha = current_match.group(0) if current_match else None
    if not pinned_delivery_sha:
        report.error(f"{delivery.name} Pinned field lacks a full revision SHA")
    elif sha and pinned_delivery_sha != sha:
        report.error(f"{delivery.name} Pinned SHA does not match pin.md")
    if not current_delivery_sha:
        report.error(f"{delivery.name} Gerrit current field lacks a full revision SHA")
    if re.search(r"(?i)\b(pending|unknown|unverified)\b", delivery_text):
        report.error(f"{delivery.name} is not a completed freshness decision")
    result = field(delivery_text, "Result")
    accepted = {"current", "historical pin verified", "trivial delta verified"}
    if result not in accepted:
        report.error(f"{delivery.name} has non-deliverable result: {result or 'missing'}")
    gate_line = field(delivery_text, "Gate line") or ""
    if not re.match(r"(?i)^yes\b", gate_line):
        report.error(f"{delivery.name} does not contain an affirmative Gate line")
    if result == "current" and sha and current_delivery_sha != sha:
        report.error(f"{delivery.name} claims current but Gerrit current differs from pin.md")
    delta_path = root / "patchset-delta.md"
    if delta_path.exists():
        delta_classification = field(read_text(delta_path, report), "Classification") or ""
        if re.match(r"(?i)^material\b", delta_classification):
            report.error("material patchset delta cannot be delivered from the old review directory")
    if result == "trivial delta verified":
        delta = read_text(delta_path, report)
        if sha and sha not in delta:
            report.error("patchset-delta.md does not identify the pinned old SHA")
        if not current_delivery_sha or current_delivery_sha not in delta:
            report.error("patchset-delta.md does not identify the delivered Gerrit-current SHA")
        if not re.search(r"(?im)^-?\s*Classification:\s*trivial\b", delta):
            report.error("patchset-delta.md does not classify the inspected delta as trivial")
        if current_delivery_sha and current_delivery_sha not in draft:
            report.error(
                "trivial-delta draft does not state the delivered Gerrit-current SHA"
            )
        current_ps = re.search(r"(?i)\bPS\s*(\d+)\b", current_value)
        if current_ps and not re.search(
                rf"(?i)(?:\bPS\s*{current_ps.group(1)}\b|"
                rf"\bpatchset\s+{current_ps.group(1)}\b)", draft):
            report.error(
                "trivial-delta draft does not state the delivered Gerrit-current patchset"
            )

    challenge_pointer = read_text(root / "challenge.md", report)
    pointer = re.search(r"challenge/round-(\d+)/index\.md", challenge_pointer)
    if not pointer:
        report.error("challenge.md does not point to a completed round index")
    else:
        index_path = root / pointer.group(0)
        index_text = read_text(index_path, report)
        challenge_revision = field(index_text, "Draft revision") or ""
        if not re.fullmatch(r"[1-9]\d*", challenge_revision):
            report.error(f"{index_path} lacks a positive integer Draft revision")
        if challenge_revision != draft_revision:
            report.error(
                f"latest challenge audited draft revision "
                f"{challenge_revision or 'missing'}, current draft is "
                f"{draft_revision or 'missing'}")
        checked_revision = field(delivery_text, "Checked after challenge revision") or ""
        if checked_revision != challenge_revision:
            report.error(
                f"{delivery.name} challenge revision {checked_revision or 'missing'} "
                f"does not match challenged draft revision "
                f"{challenge_revision or 'missing'}")
        if not re.search(r"(?im)^- Result:\s*(?:pass|passed|clean)\b", index_text):
            report.error(f"latest challenge index is not a pass: {index_path}")
        found_shards = False
        seen_shards: set[str] = set()
        coverage: Counter[str] = Counter()
        global_section_ids = {
            identifier for identifier, section in sections.items()
            if section.get("global_frame") == "yes"
        }
        global_consistency_shards = 0
        for _, header, rows in table_dicts(index_text):
            required_columns = {
                "shard", "scope", "brief", "artifact", "expected coverage", "issues",
            }
            if not required_columns.issubset(header):
                continue
            found_shards = True
            for row in rows:
                shard = row.get("shard", "")
                if not re.fullmatch(r"CH\d+", shard):
                    report.error(f"{index_path} has invalid challenge shard '{shard}'")
                elif shard in seen_shards:
                    report.error(f"{index_path} duplicates challenge shard {shard}")
                seen_shards.add(shard)
                if not row.get("scope") or not row.get("expected coverage"):
                    report.error(f"{index_path} shard {shard or '?'} lacks scope/coverage")
                if sections and row.get("scope", "").lower().startswith(
                        "global-consistency"):
                    global_consistency_shards += 1
                expected_tokens = {
                    item.strip() for item in
                    row.get("expected coverage", "").split(",") if item.strip()
                }
                if sections:
                    is_global_scope = row.get("scope", "").lower().startswith(
                        "global-consistency"
                    )
                    if ("global:consistency" in expected_tokens) != is_global_scope:
                        report.error(
                            f"{index_path} shard {shard or '?'} global scope/token mismatch"
                        )
                for token in expected_tokens:
                    if token:
                        coverage[token] += 1
                brief = row.get("brief", "")
                brief_path = root / brief
                if (not brief or brief in {"—", "-", "none"}
                        or not brief_path.is_file() or brief_path.stat().st_size == 0):
                    report.error(f"challenge shard {shard or '?'} has missing/empty brief")
                artifact = row.get("artifact", "")
                artifact_path: Path | None = None
                if artifact and artifact not in {"—", "-", "none"}:
                    artifact_path = root / artifact
                    if (not artifact_path.is_file()
                            or artifact_path.stat().st_size == 0):
                        report.error(f"challenge shard missing/empty: {artifact_path}")
                else:
                    report.error(f"{index_path} shard {shard or '?'} lacks an artifact")
                if row.get("issues", "").lower() not in {"none", "0", "—", "-"}:
                    report.error(f"passing challenge shard {shard or '?'} still lists issues")
                if sections and brief_path.is_file():
                    brief_text = read_text(brief_path, report)
                    if re.search(r"\b(?:draft-review|gerrit-comments)\.md\b", brief_text):
                        report.error(
                            f"{brief_path}: sectioned large-draft challenger receives "
                            "a whole draft/Gerrit output"
                        )
                    if re.search(r"(?:draft|gerrit)-sections/\*", brief_text):
                        report.error(
                            f"{brief_path}: sectioned challenger uses a whole-section glob"
                        )
                    assigned_sections = {
                        token.split(":", 1)[1]
                        for token in expected_tokens if token.startswith("section:")
                    }
                    assigned_cards = {
                        token.split(":", 1)[1]
                        for token in expected_tokens if token.startswith("card:")
                    }
                    manifest_rows = input_assignments.get(shard, [])
                    if not manifest_rows:
                        report.error(
                            f"sectioned challenge shard {shard or '?'} has no "
                            "input-manifest work row"
                        )
                    elif {Path(item["brief"]).resolve() for item in manifest_rows} \
                            != {brief_path.resolve()}:
                        report.error(
                            f"input-manifest work {shard} does not name its challenge brief"
                        )
                    role_paths: dict[str, set[Path]] = defaultdict(set)
                    for item in manifest_rows:
                        role_paths[item["role"]].add(Path(item["input_path"]).resolve())
                    expected_section_paths: set[Path] = set()
                    expected_frame_paths: set[Path] = set()
                    for identifier in assigned_sections:
                        section = sections.get(identifier)
                        if section is None:
                            continue
                        destination = (expected_frame_paths
                                       if section["global_frame"] == "yes"
                                       else expected_section_paths)
                        destination.add((root / section["draft_path"]).resolve())
                        if section["gerrit_path"] != "-":
                            destination.add((root / section["gerrit_path"]).resolve())
                    allowed_frame_paths: set[Path] = set()
                    for identifier in global_section_ids:
                        section = sections[identifier]
                        allowed_frame_paths.add((root / section["draft_path"]).resolve())
                        if section["gerrit_path"] != "-":
                            allowed_frame_paths.add((root / section["gerrit_path"]).resolve())
                    expected_card_paths = {
                        synthesis_card_paths[item] for item in assigned_cards
                        if item in synthesis_card_paths
                    }
                    for item in sorted(assigned_cards - set(synthesis_card_paths)):
                        report.error(
                            f"challenge shard {shard or '?'} assigns unknown card {item}"
                        )
                    for missing in sorted(expected_section_paths - role_paths["section"]):
                        report.error(
                            f"input-manifest work {shard} lacks assigned section {missing}"
                        )
                    for missing in sorted(expected_frame_paths - role_paths["frame"]):
                        report.error(
                            f"input-manifest work {shard} lacks assigned frame {missing}"
                        )
                    for missing in sorted(expected_card_paths - role_paths["card"]):
                        report.error(
                            f"input-manifest work {shard} lacks assigned card {missing}"
                        )
                    for unexpected in sorted(
                            role_paths["section"] - expected_section_paths):
                        report.error(
                            f"input-manifest work {shard} has unassigned section {unexpected}"
                        )
                    for unexpected in sorted(
                            role_paths["frame"] - allowed_frame_paths):
                        report.error(
                            f"input-manifest work {shard} has unknown frame {unexpected}"
                        )
                    for unexpected in sorted(role_paths["card"] - expected_card_paths):
                        report.error(
                            f"input-manifest work {shard} has unassigned card {unexpected}"
                        )
                    referenced_draft = set(re.findall(
                        r"draft-sections/([A-Z][A-Z0-9_-]*)\.md", brief_text
                    ))
                    referenced_gerrit = set(re.findall(
                        r"gerrit-sections/([A-Z][A-Z0-9_-]*)\.md", brief_text
                    ))
                    allowed = assigned_sections | global_section_ids
                    for identifier in sorted(
                            (referenced_draft | referenced_gerrit) - allowed):
                        report.error(
                            f"{brief_path}: references unassigned draft section {identifier}"
                        )
                    for identifier in sorted(assigned_sections):
                        section = sections.get(identifier)
                        if section is None:
                            continue
                        if identifier not in referenced_draft:
                            report.error(
                                f"{brief_path}: assigned section {identifier} lacks draft input"
                            )
                        if (section["gerrit_path"] != "-"
                                and identifier not in referenced_gerrit):
                            report.error(
                                f"{brief_path}: assigned section {identifier} lacks Gerrit input"
                            )
                        if (artifact_path is not None and artifact_path.is_file()
                                and (section["draft_sha256"] not in
                                     read_text(artifact_path, report)
                                     or section["gerrit_sha256"] not in
                                     read_text(artifact_path, report))):
                            report.error(
                                f"{artifact_path}: does not record both audited hashes for "
                                f"section {identifier}"
                            )
        if not found_shards or not seen_shards:
            report.error(f"{index_path} has no complete challenge shard roster")
        if sections and global_consistency_shards != 1:
            report.error(
                f"{index_path} has {global_consistency_shards} global-consistency "
                "shards, expected 1"
            )
        expected_coverage = ({f"card:{item}" for item in synthesis_items}
                             | {f"row:{item}" for item in source_ids}
                             | {f"section:{item}" for item in sections})
        if sections:
            expected_coverage.add("global:consistency")
        for token in sorted(expected_coverage):
            if coverage[token] != 1:
                report.error(
                    f"challenge coverage token {token} appears {coverage[token]} times")
        for token in sorted(set(coverage) - expected_coverage):
            report.error(f"challenge coverage names unknown token {token}")
    reconciliation = read_text(root / "reconciliation.md", report)
    freshness = re.search(r"^2\.\s+\*\*[^*]+:\*\*\s*(.*)$",
                          reconciliation, re.MULTILINE)
    if (not freshness or not re.match(r"(?i)^yes\b", freshness.group(1))
            or "delivery-gate.md" not in freshness.group(1)):
        report.error(
            "reconciliation Freshness gate is not affirmative with a delivery-gate.md citation")


def infer_phase(root: Path) -> str:
    if (root / "draft-review.md").exists() or (root / "gerrit-comments.md").exists():
        return "final"
    if (root / "reconciliation.md").exists():
        return "reconciliation"
    if any(p.name != "VTER.md" for p in (root / "verification").glob("V*.md")) if (root / "verification").exists() else False:
        return "verification"
    if (root / "collection.md").exists() or (root / "plan.md").exists():
        return "collection"
    return "pin"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--phase", choices=("auto", *PHASES), default="auto")
    parser.add_argument("--require-active-lease", action="store_true")
    parser.add_argument(
        "--lease-stale-seconds", type=int,
        default=os.environ.get("CHROMIUM_REVIEW_LEASE_SECONDS", "3600"))
    arguments = parser.parse_args()
    root = arguments.review_dir.resolve()
    if not root.is_dir():
        print(f"validate-review-dir.py: ERROR: not a directory: {root}", file=sys.stderr)
        return 2
    phase = infer_phase(root) if arguments.phase == "auto" else arguments.phase
    level = PHASES[phase]
    report = Report()
    sha, changed_files = validate_pin(
        root, report, arguments.require_active_lease,
        arguments.lease_stale_seconds)
    validate_unresolved(root, report, required=level >= PHASES["collection"])
    source_ids: dict[str, Path] = {}
    candidates: set[str] = set()
    covered: set[str] = set()
    required_root_cause_scopes: set[str] = set()
    synthesis_items: set[str] = set()
    budgets: dict[str, int] = {}
    input_assignments: dict[str, list[dict[str, str]]] = {}
    if level >= PHASES["collection"]:
        budgets = validate_scaling_outputs(root, report)
        required_root_cause_scopes, trigger_rows = validate_trigger_inventory(
            root, report
        )
        validate_plan(root, trigger_rows, report)
        validate_generated_briefs(root, report)
        input_assignments = validate_input_manifest(root, budgets, report)
        validate_manifest(root, report, final=level >= PHASES["final"])
        source_ids, candidates, covered = ledger_data(root, report)
        validate_collection_coverage(root, report, level)
        validate_ter_gate(root, report)
        for changed in sorted(set(changed_files) - covered):
            report.error(f"per-file floor missing ledger/ORC row for {changed}")
    if level >= PHASES["verification"]:
        validate_verdicts(root, candidates, report)
        validate_root_cause_trigger_accounting(root, required_root_cause_scopes,
                                               report)
    if level >= PHASES["reconciliation"]:
        validate_reconciliation(root, source_ids, report,
                                final=level >= PHASES["final"])
        synthesis_items = validate_synthesis(root, source_ids, budgets, report)
    if level >= PHASES["final"]:
        validate_final(
            root, sha, source_ids, synthesis_items, budgets, input_assignments,
            report,
        )
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
