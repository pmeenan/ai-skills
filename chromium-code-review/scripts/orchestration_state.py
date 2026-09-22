#!/usr/bin/env python3
"""Shared mutation primitives for orchestration.tsv and input-manifest.tsv.

`seal-work-unit.py` creates the two orchestration tables under a flock guard,
writes them through a journal, and replaces them atomically. Every later
mutation must use exactly the same discipline or a crash — or a concurrent
worker — silently corrupts the tables and the delivery gate fails much later
with an unhelpful diagnostic. `set-work-state.py`, `await-workers.py` and
`refresh-manifest.py` therefore share this module instead of each hand-rolling
a `python3 -c` rewrite.

The sibling scripts are hyphenated and cannot be imported, so the shared code
lives here under an importable underscore name (mirroring `artifact_tables.py`).

Discipline implemented here, in order:
  1. `guard()`   — exclusive flock on `<review-dir>/.orchestration.lock`.
  2. `recover()` — replay any journal left by an interrupted transaction
                   (ours or `seal-work-unit.py`'s) before reading anything.
  3. `commit()`  — write the journal, then replay it, so an interrupted commit
                   is completed by the next invocation rather than lost.

`set_program()` makes `fail()` print the calling script's name, matching the
`<script>.py: ERROR: ...` convention used everywhere else in this skill.
"""

from __future__ import annotations

import csv
from contextlib import contextmanager
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Iterator, NoReturn, Sequence


SCRIPTS = Path(__file__).resolve().parent

ORCHESTRATION_COLUMNS = (
    "phase", "work_id", "attempt", "state", "tier", "task_id", "brief",
    "artifact", "remaining_scope", "depends_on",
)
INPUT_COLUMNS = (
    "work_id", "attempt", "phase", "brief", "input_path", "role", "bytes",
    "sha256",
)
STATES = (
    "queued", "running", "partial", "retryable", "needs-repair", "complete",
    "terminated",
)
TERMINAL_STATES = frozenset({"complete", "terminated"})
# Roles whose bytes/sha256 are integrity anchors: the brief is frozen read-only
# by seal-work-unit.py and references come from the sealed skill snapshot.
# Restamping either would forge the seal instead of detecting drift.
SEALED_ROLES = frozenset({"brief", "reference"})
DETERMINISTIC_INDEX_NAMES = {
    "inventory.tsv",
    "topology.tsv",
    "specialist-priors.tsv",
    "candidates.tsv",
    "verdicts.tsv",
    "reconciliation.tsv",
    "manifest.json",
}
JOURNAL = ".work-unit-seal-transaction.json"
GUARD_TIMEOUT_ENV = "CHROMIUM_REVIEW_GUARD_SECONDS"

_program = "orchestration_state.py"


def set_program(name: str) -> None:
    """Make fail() report `name` — call this once from the importing script."""
    global _program
    _program = name


def fail(message: str) -> NoReturn:
    print(f"{_program}: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_write(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def encode(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def read_rows(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            if tuple(reader.fieldnames or ()) != columns:
                fail(
                    f"{path} has wrong columns or order; expected the "
                    f"{len(columns)} columns {', '.join(columns)} — restore "
                    "the file before mutating it"
                )
            return list(reader)
    except (OSError, csv.Error) as error:
        fail(f"cannot parse {path}: {error}")
    return []


@contextmanager
def guard(root: Path) -> Iterator[None]:
    with (root / ".orchestration.lock").open("a+", encoding="utf-8") as stream:
        try:
            timeout = float(os.environ.get(GUARD_TIMEOUT_ENV, "30"))
        except ValueError:
            fail(f"{GUARD_TIMEOUT_ENV} must be a positive number")
        if not math.isfinite(timeout) or timeout <= 0:
            fail(f"{GUARD_TIMEOUT_ENV} must be a positive number")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fail(
                        "timed out waiting for orchestration mutation guard: "
                        f"{root / '.orchestration.lock'}; another script is "
                        "mutating this review — retry, or raise "
                        f"{GUARD_TIMEOUT_ENV}"
                    )
                time.sleep(min(0.1, timeout))
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def recover(root: Path) -> None:
    """Replay an interrupted table transaction, then drop its journal."""
    journal = root / JOURNAL
    if not journal.exists():
        return
    try:
        value = json.loads(journal.read_text(encoding="utf-8"))
        orchestration = value["orchestration"]
        inputs = value["inputs"]
        if not isinstance(orchestration, str) or not isinstance(inputs, str):
            raise ValueError("payloads are not strings")
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        fail(
            f"cannot recover interrupted table transaction {journal}: {error}; "
            "inspect the journal by hand, then delete it once the two tables "
            "are consistent"
        )
    atomic_write(root / "orchestration.tsv", orchestration)
    atomic_write(root / "input-manifest.tsv", inputs)
    journal.unlink()


def raw_table(root: Path, name: str, columns: tuple[str, ...]) -> str:
    """Exact current bytes of a table, so a commit leaves it untouched."""
    path = root / name
    if not path.exists():
        return encode(columns, [])
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        fail(f"cannot read {path}: {error}")
    return ""


def commit(root: Path, orchestration_payload: str, input_payload: str) -> None:
    """Journal both table payloads, then replay them atomically."""
    atomic_write(
        root / JOURNAL,
        json.dumps(
            {"orchestration": orchestration_payload, "inputs": input_payload},
            sort_keys=True,
        ) + "\n",
    )
    recover(root)


def require_review_dir(value: Path) -> Path:
    root = value.resolve()
    if not root.is_dir():
        fail(f"review directory does not exist: {root}")
    return root


def locate(rows: list[dict[str, str]], work_id: str, attempt: int) -> int:
    """Index of the one row for work_id:attempt, or fail with guidance."""
    key = (work_id, str(attempt))
    matches = [
        index for index, row in enumerate(rows)
        if (row["work_id"], row["attempt"]) == key
    ]
    if not matches:
        known = ", ".join(
            sorted({f"{row['work_id']}:{row['attempt']}" for row in rows})
        ) or "(no rows)"
        fail(
            f"no row for {work_id}:{attempt}; seal it first with "
            f"seal-work-unit.py. Sealed units: {known}"
        )
    if len(matches) > 1:
        fail(
            f"{len(matches)} rows match {work_id}:{attempt}; the table is "
            "corrupt — delete the duplicate rows (keep the one whose artifact "
            "column is correct) before mutating state"
        )
    return matches[0]


def set_state(root: Path, work_id: str, attempt: int, state: str, *,
              task_id: str | None = None, remaining_scope: str | None = None,
              force: bool = False) -> tuple[str, bool]:
    """Set one row's state (and optionally task_id / remaining_scope).

    Returns (previous_state, changed). Every other row and column survives
    byte-for-byte because only the located row's fields are reassigned, and
    input-manifest.tsv is journalled back with its current bytes.
    """
    if state not in STATES:
        fail(f"unknown state '{state}'; legal states: {', '.join(STATES)}")
    with guard(root):
        recover(root)
        path = root / "orchestration.tsv"
        if not path.is_file():
            fail(
                f"no orchestration.tsv in {root}; seal the work unit with "
                "seal-work-unit.py before setting its state"
            )
        rows = read_rows(path, ORCHESTRATION_COLUMNS)
        row = rows[locate(rows, work_id, attempt)]
        previous = row["state"]
        if previous in TERMINAL_STATES and previous != state and not force:
            fail(
                f"{work_id}:{attempt} is already {previous}, a terminal state; "
                f"refusing to move it to {state}. Pass --force if the unit "
                "really must be reopened, or seal a new attempt instead"
            )
        changed = row["state"] != state
        row["state"] = state
        if task_id is not None and row["task_id"] != task_id:
            row["task_id"] = task_id
            changed = True
        if remaining_scope is not None and row["remaining_scope"] != remaining_scope:
            row["remaining_scope"] = remaining_scope
            changed = True
        if changed:
            commit(
                root,
                encode(ORCHESTRATION_COLUMNS, rows),
                raw_table(root, "input-manifest.tsv", INPUT_COLUMNS),
            )
        return previous, changed


def orchestration_rows(root: Path) -> list[dict[str, str]]:
    """Current orchestration rows, healing any interrupted transaction."""
    with guard(root):
        recover(root)
        path = root / "orchestration.tsv"
        if not path.is_file():
            fail(
                f"no orchestration.tsv in {root}; nothing has been sealed, so "
                "there is nothing to wait for"
            )
        return read_rows(path, ORCHESTRATION_COLUMNS)


def run_helper(name: str, arguments: Sequence[str]) -> str | None:
    """Run a sibling script; return None on success or a one-line reason."""
    script = SCRIPTS / name
    if not script.is_file():
        return f"{name} is missing from {SCRIPTS}"
    try:
        result = subprocess.run(
            [sys.executable, str(script), *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        return f"cannot run {name}: {error}"
    if result.returncode != 0:
        detail = (result.stderr.strip() or result.stdout.strip()
                  or f"exit {result.returncode}")
        return detail.splitlines()[0]
    return None


def log_progress(root: Path, event: str, *arguments: str) -> str | None:
    """Append one progress.md event through log-progress.py's grammar."""
    return run_helper("log-progress.py", [str(root), event, *arguments])


def heartbeat(root: Path, message: str) -> str | None:
    """Heartbeat the worktree lease; returns a reason when it did not work."""
    return run_helper("worktree-lease.py", ["heartbeat", str(root), message])
