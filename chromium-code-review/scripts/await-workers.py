#!/usr/bin/env python3
"""Block in one tool call until a spawn wave's artifacts land, then collect.

An orchestrator that says "awaiting deliverable" and ends its turn is never
woken: roughly two in five subagents write their artifact and never send a
completion message, so multi-hour runs deliver nothing. Polling the harness
instead (`manage_task status`, `manage_subagents list`, timers) burns hundreds
of turns. This script replaces both: one call blocks until every unit of the
wave is finished, and prints a short table — never per-poll chatter, never
artifact contents.

  await-workers.py <review-dir>
      [--work WORK_ID[:ATTEMPT]]...   default: every running or queued row
      [--timeout-seconds N]           default 5400
      [--poll-seconds N]              default 30
      [--heartbeat TEXT] [--no-heartbeat]
      [--validate | --no-validate]    default --validate
      [--no-transition] [--quiet]

A unit is satisfied when its `artifact` column names a file that exists, is
non-empty, and (unless --no-validate) passes validate-worker-artifact.py.
A continuation with an artifact prestate must also preserve its authenticated
prefix and append new bytes. An unchanged artifact never proves completion;
a no-op worker must append an explicit completion attestation. The
validator runs at most once per (path, mtime, size), so a slow validator is
not re-run on every poll. Satisfied units move to `complete` and get a
`collected` progress.md event unless --no-transition; units whose artifact the
validator rejects move to `needs-repair` and stop being waited on.

Exit codes:
  0  every unit satisfied
  2  timed out with at least one unit still outstanding
  3  every unit finished, but at least one is needs-repair

Set CHROMIUM_REVIEW_ARTIFACT_VALIDATOR to an alternative validator command
(argv split with shlex, invoked as `<command> <review-dir> <artifact>`) to
override validate-worker-artifact.py; this exists for tests.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
import re
from pathlib import Path
import shlex
import subprocess
import sys
import time

from orchestration_state import (
    SCRIPTS,
    INPUT_COLUMNS,
    digest,
    read_rows,
    fail,
    heartbeat,
    log_progress,
    orchestration_rows,
    require_review_dir,
    set_program,
    set_state,
)

set_program("await-workers.py")

VALIDATOR_ENV = "CHROMIUM_REVIEW_ARTIFACT_VALIDATOR"
OUTSTANDING_STATES = ("running", "queued")


@dataclass
class Unit:
    work_id: str
    attempt: int
    artifact: Path
    entry_state: str
    state: str = "outstanding"
    detail: str = ""
    elapsed: float = 0.0
    notes: list[str] = field(default_factory=list)
    brief: Path | None = None
    prestate: tuple[int, str] | None = None
    prestate_error: str = ""

    @property
    def name(self) -> str:
        return f"{self.work_id}:{self.attempt}"


def parse_spec(spec: str, rows: list[dict[str, str]]) -> dict[str, str]:
    work_id, separator, raw_attempt = spec.partition(":")
    if not work_id:
        fail(f"--work needs WORK_ID[:ATTEMPT], got '{spec}'")
    candidates = [row for row in rows if row["work_id"] == work_id]
    if not candidates:
        known = ", ".join(sorted({row["work_id"] for row in rows})) or "(none)"
        fail(
            f"--work {spec}: no orchestration row for '{work_id}'; seal it "
            f"with seal-work-unit.py first. Sealed work IDs: {known}"
        )
    if separator:
        if not raw_attempt.isdigit() or int(raw_attempt) < 1:
            fail(f"--work {spec}: attempt must be a positive integer")
        exact = [row for row in candidates if row["attempt"] == raw_attempt]
        if not exact:
            attempts = ", ".join(sorted(row["attempt"] for row in candidates))
            fail(
                f"--work {spec}: attempt {raw_attempt} is not sealed; sealed "
                f"attempts for {work_id}: {attempts}"
            )
        if len(exact) > 1:
            fail(
                f"--work {spec}: {len(exact)} rows match; orchestration.tsv is "
                "corrupt — remove the duplicate row before waiting"
            )
        return exact[0]
    return max(candidates, key=lambda row: int(row["attempt"]))


def resolve(rows: list[dict[str, str]], specs: list[str]) -> list[Unit]:
    if specs:
        chosen = []
        seen: set[tuple[str, str]] = set()
        for spec in specs:
            row = parse_spec(spec, rows)
            key = (row["work_id"], row["attempt"])
            if key not in seen:
                seen.add(key)
                chosen.append(row)
    else:
        chosen = [row for row in rows if row["state"] in OUTSTANDING_STATES]
    units = []
    for row in chosen:
        artifact = Path(row["artifact"])
        if not artifact.is_absolute():
            fail(
                f"{row['work_id']}:{row['attempt']} has a relative artifact "
                f"path '{row['artifact']}'; reseal the unit with an absolute "
                "--artifact"
            )
        units.append(Unit(
            work_id=row["work_id"], attempt=int(row["attempt"]),
            artifact=artifact, entry_state=row["state"], brief=Path(row["brief"]),
        ))
    return units


def bind_prestates(root: Path, units: list[Unit]) -> None:
    """Capture each sealed continuation baseline once, before polling."""
    rows = read_rows(root / "input-manifest.tsv", INPUT_COLUMNS)
    for unit in units:
        assigned = [row for row in rows if row["work_id"] == unit.work_id
                    and row["attempt"] == str(unit.attempt)]
        prestates = [row for row in assigned if row["role"] == "prestate"
                    and Path(row["input_path"]).resolve() == unit.artifact.resolve()]
        if not prestates:
            continue
        self_rows = [row for row in assigned if row["role"] == "brief"
                     and row["input_path"] == row["brief"] == str(unit.brief)]
        try:
            if len(prestates) != 1 or len(self_rows) != 1:
                raise ValueError("requires exactly one artifact prestate and self brief row")
            prestate, self_row = prestates[0], self_rows[0]
            if prestate["brief"] != str(unit.brief):
                raise ValueError("prestate belongs to a different brief")
            payload = unit.brief.read_bytes()
            if self_row["bytes"] != str(len(payload)) or self_row["sha256"] != digest(payload):
                raise ValueError("self brief seal is stale")
            size = int(prestate["bytes"])
            if size < 0 or re.fullmatch(r"[0-9a-f]{64}", prestate["sha256"]) is None:
                raise ValueError("prestate size/hash is invalid")
            unit.prestate = (size, prestate["sha256"])
        except (OSError, ValueError) as error:
            unit.prestate_error = f"cannot authenticate continuation prestate: {error}"


def validator_command() -> list[str]:
    override = os.environ.get(VALIDATOR_ENV, "").strip()
    if override:
        return shlex.split(override)
    return [sys.executable, str(SCRIPTS / "validate-worker-artifact.py")]


def validate(root: Path, artifact: Path, stat: os.stat_result,
             memo: dict[tuple[str, int, int], tuple[bool, list[str]]],
             ) -> tuple[bool, list[str]]:
    """Validate once per (path, mtime, size); memoized across polls."""
    key = (str(artifact), stat.st_mtime_ns, stat.st_size)
    if key in memo:
        return memo[key]
    try:
        result = subprocess.run(
            [*validator_command(), str(root), str(artifact)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        outcome = (False, [f"cannot run the artifact validator: {error}"])
        memo[key] = outcome
        return outcome
    lines = [
        line.strip()
        for line in (result.stderr + "\n" + result.stdout).splitlines()
        if line.strip()
    ]
    outcome = (result.returncode == 0, lines[:3])
    memo[key] = outcome
    return outcome


def finish(root: Path, unit: Unit, state: str, detail: str, elapsed: float,
           transition: bool) -> None:
    unit.state = state
    unit.detail = detail
    unit.elapsed = elapsed
    if not transition:
        return
    try:
        set_state(root, unit.work_id, unit.attempt, state)
    except SystemExit:
        unit.notes.append(f"{unit.name} state not updated")
        return
    if state == "complete":
        error = log_progress(
            root, "collected", unit.work_id, str(unit.attempt),
            f"artifact {unit.artifact}",
        )
    else:
        error = log_progress(
            root, "note", f"{unit.name}", "needs-repair —", detail or "invalid artifact",
        )
    if error:
        unit.notes.append(f"{unit.name} progress.md not updated: {error}")


def poll_unit(root: Path, unit: Unit, memo: dict, do_validate: bool,
              elapsed: float, transition: bool) -> bool:
    """Return True when the unit is finished (satisfied or needs-repair)."""
    if unit.prestate_error:
        finish(root, unit, "needs-repair", unit.prestate_error, elapsed, transition)
        return True
    try:
        stat = unit.artifact.stat()
    except FileNotFoundError:
        unit.detail = f"no artifact yet at {unit.artifact}"
        return False
    except OSError as error:
        unit.detail = f"cannot stat {unit.artifact}: {error}"
        return False
    if unit.prestate is not None:
        size, expected_hash = unit.prestate
        try:
            payload = unit.artifact.read_bytes()
        except OSError as error:
            unit.detail = f"cannot read continuation artifact: {error}"
            return False
        if len(payload) < size or digest(payload[:size]) != expected_hash:
            finish(root, unit, "needs-repair", "continuation rewrote its sealed prestate prefix",
                   elapsed, transition)
            return True
        if len(payload) == size:
            unit.detail = "unchanged prestate; waiting for appended work or completion attestation"
            return False
    if stat.st_size == 0:
        unit.detail = f"artifact is empty: {unit.artifact}"
        return False
    if do_validate:
        valid, diagnostics = validate(root, unit.artifact, stat, memo)
        if not valid:
            finish(root, unit, "needs-repair",
                   " | ".join(diagnostics) or "validator rejected the artifact",
                   elapsed, transition)
            return True
    finish(root, unit, "complete", str(unit.artifact), elapsed, transition)
    return True


def seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument(
        "--work", action="append", default=[], metavar="WORK_ID[:ATTEMPT]",
        help="Wait on this unit; repeatable. Without :ATTEMPT the highest "
             "sealed attempt is used. Default: every running or queued row.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=5400.0)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--heartbeat", default=None,
                        help="Lease heartbeat note; default describes the wave.")
    parser.add_argument("--no-heartbeat", action="store_true",
                        help="Do not heartbeat the worktree lease while waiting.")
    parser.add_argument("--validate", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Run validate-worker-artifact.py on each artifact.")
    parser.add_argument("--no-transition", action="store_true",
                        help="Report only; do not move any row's state.")
    parser.add_argument("--quiet", action="store_true",
                        help="Print the summary plus any non-complete unit only.")
    arguments = parser.parse_args()

    root = require_review_dir(arguments.review_dir)
    if arguments.poll_seconds <= 0:
        fail("--poll-seconds must be greater than zero")
    if arguments.timeout_seconds <= 0:
        fail("--timeout-seconds must be greater than zero")

    units = resolve(orchestration_rows(root), arguments.work)
    if not units:
        print("await-workers.py: nothing outstanding")
        return 0

    bind_prestates(root, units)
    transition = not arguments.no_transition
    names = ", ".join(unit.name for unit in units)
    note = arguments.heartbeat or f"awaiting {len(units)} unit(s): {names}"[:200]
    if not arguments.quiet:
        print(
            f"await-workers.py: waiting on {len(units)} unit(s), timeout "
            f"{seconds(arguments.timeout_seconds)}s, poll "
            f"{seconds(arguments.poll_seconds)}s, validation "
            f"{'on' if arguments.validate else 'off'}"
        )

    memo: dict[tuple[str, int, int], tuple[bool, list[str]]] = {}
    outstanding = list(units)
    start = time.monotonic()
    heartbeat_error: str | None = None
    while True:
        elapsed = time.monotonic() - start
        outstanding = [
            unit for unit in outstanding
            if not poll_unit(root, unit, memo, arguments.validate, elapsed,
                             transition)
        ]
        if not outstanding:
            break
        if time.monotonic() - start >= arguments.timeout_seconds:
            break
        time.sleep(arguments.poll_seconds)
        if not arguments.no_heartbeat:
            # Losing the lease must never lose the wait: report it once in the
            # summary and keep waiting.
            error = heartbeat(root, note)
            if error and heartbeat_error is None:
                heartbeat_error = error

    total = time.monotonic() - start
    for unit in outstanding:
        unit.elapsed = total
    complete = [unit for unit in units if unit.state == "complete"]
    repair = [unit for unit in units if unit.state == "needs-repair"]
    for unit in units:
        if arguments.quiet and unit.state == "complete":
            continue
        print(
            f"{unit.name} {unit.state} {int(unit.elapsed)}s "
            f"{unit.detail or unit.artifact}"
        )
    trailer = ""
    if heartbeat_error:
        trailer += f"; lease heartbeat unavailable: {heartbeat_error}"
    for unit in units:
        for entry in unit.notes:
            trailer += f"; {entry}"
    if not transition:
        trailer += "; states left unchanged (--no-transition)"
    print(
        f"await-workers.py: {len(complete)} complete, {len(repair)} "
        f"needs-repair, {len(outstanding)} outstanding after "
        f"{int(total)}s{trailer}"
    )
    if outstanding:
        return 2
    if repair:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
