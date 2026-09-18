#!/usr/bin/env python3
"""Change one orchestration.tsv row's state safely and idempotently.

State transitions used to be hand-rolled `python3 -c` rewrites of
orchestration.tsv — dozens per run — which reorder columns, drop rows and
strand the table in a shape the delivery gate rejects hours later. This is
the only supported way to move a work unit between states.

  set-work-state.py <review-dir> <WORK_ID> <attempt> <state>
      [--task-id ID] [--remaining-scope TEXT] [--note TEXT] [--log] [--force]

Exactly one row (matched on work_id + attempt) is touched, and only its
`state` — plus `task_id` / `remaining_scope` when those flags are given.
Every other row and column is rewritten byte-for-byte. The mutation happens
under the `.orchestration.lock` guard through the same journal as
`seal-work-unit.py`, and any interrupted transaction found on entry is
replayed before this one starts.

`--log` additionally appends the matching progress.md event through
log-progress.py (complete -> `collected`, running -> `spawned`, otherwise a
`note`) and heartbeats the worktree lease, so a long-running phase does not
look abandoned.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from orchestration_state import (
    STATES,
    fail,
    heartbeat,
    log_progress,
    require_review_dir,
    set_program,
    set_state,
)

set_program("set-work-state.py")


def emit_progress(root: Path, work_id: str, attempt: int, state: str,
                  note: str) -> None:
    """Append the progress.md event that matches this transition."""
    text = note or f"state {state}"
    if state == "complete":
        error = log_progress(root, "collected", work_id, str(attempt), text)
    elif state == "running":
        error = log_progress(root, "spawned", work_id, str(attempt), text)
    else:
        error = log_progress(
            root, "note", f"{work_id}:{attempt}", "state", state, "—", text
        )
    if error:
        print(
            f"set-work-state.py: WARNING: state was written but progress.md "
            f"was not updated: {error}; append the event by hand with "
            "log-progress.py",
            file=sys.stderr,
        )
    beat = heartbeat(root, f"{work_id}:{attempt} {state}")
    if beat:
        print(
            f"set-work-state.py: WARNING: lease heartbeat failed: {beat}; the "
            "state change is still committed",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("work_id")
    parser.add_argument("attempt", type=int)
    parser.add_argument("state", choices=list(STATES))
    parser.add_argument("--task-id", default=None,
                        help="Harness task identifier to record for this row.")
    parser.add_argument("--remaining-scope", default=None,
                        help="Replacement remaining_scope cell for this row.")
    parser.add_argument("--note", default="",
                        help="Text for the --log progress.md event.")
    parser.add_argument("--log", action="store_true",
                        help="Append a progress.md event and heartbeat the lease.")
    parser.add_argument(
        "--force", action="store_true",
        help="Allow leaving a terminal state (complete, terminated).",
    )
    arguments = parser.parse_args()

    root = require_review_dir(arguments.review_dir)
    if arguments.attempt < 1:
        fail("attempt must be a positive integer, like 1")
    if not arguments.work_id or any(
        character in arguments.work_id for character in "\t\r\n "
    ):
        fail(f"work ID must be one non-empty token: '{arguments.work_id}'")
    for label, value in (("--task-id", arguments.task_id),
                         ("--remaining-scope", arguments.remaining_scope)):
        if value is not None and any(character in value for character in "\t\r\n"):
            fail(f"{label} must not contain tabs or newlines")

    previous, changed = set_state(
        root, arguments.work_id, arguments.attempt, arguments.state,
        task_id=arguments.task_id, remaining_scope=arguments.remaining_scope,
        force=arguments.force,
    )
    unit = f"{arguments.work_id}:{arguments.attempt}"
    if changed:
        print(f"set-work-state.py: {unit} {previous} -> {arguments.state}")
    else:
        print(f"set-work-state.py: {unit} already {arguments.state}")
    if arguments.log:
        emit_progress(root, arguments.work_id, arguments.attempt,
                      arguments.state, arguments.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
