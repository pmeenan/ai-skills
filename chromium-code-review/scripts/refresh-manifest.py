#!/usr/bin/env python3
"""Restamp input-manifest.tsv prestate rows after their files changed.

Prestate inputs (working-tree files a worker is told to re-read) grow between
attempts, so the bytes/sha256 recorded at seal time go stale and the delivery
gate fails with `byte count mismatch`. Repairing that with an ad-hoc
`hashlib` snippet rewrites the whole table and loses rows. Use this instead.

  refresh-manifest.py <review-dir> <WORK_ID> <attempt> [--role prestate]
                      [--dry-run]

`--role` is repeatable and defaults to `prestate`. `brief` and `reference`
rows can never be restamped: the brief is frozen read-only at seal time and
references come from the sealed skill snapshot, so their hashes are the
integrity anchors the gate checks. If one of those hashes no longer matches,
the honest repair is to seal a new attempt — not to re-stamp the seal.

The rewrite runs under the `.orchestration.lock` guard and through the same
journal as `seal-work-unit.py`; orchestration.tsv is journalled back with its
current bytes so it cannot drift. `--dry-run` reports the deltas and writes
nothing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from orchestration_state import (
    INPUT_COLUMNS,
    ORCHESTRATION_COLUMNS,
    SEALED_ROLES,
    commit,
    digest,
    encode,
    fail,
    guard,
    raw_table,
    read_rows,
    recover,
    require_review_dir,
    set_program,
)

set_program("refresh-manifest.py")

RESTAMPABLE_ROLES = (
    "assigned", "candidate-packet", "card", "control", "frame", "prestate",
    "section",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("work_id")
    parser.add_argument("attempt", type=int)
    parser.add_argument(
        "--role", action="append", default=None,
        help="Manifest role to restamp; repeatable. Default: prestate. "
             "Sealed roles (" + ", ".join(sorted(SEALED_ROLES)) + ") are "
             "always refused.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report the deltas and change nothing.")
    arguments = parser.parse_args()

    root = require_review_dir(arguments.review_dir)
    if arguments.attempt < 1:
        fail("attempt must be a positive integer, like 1")
    roles = list(dict.fromkeys(arguments.role or ["prestate"]))
    for role in roles:
        if role in SEALED_ROLES:
            fail(
                f"refusing to restamp role '{role}': {' and '.join(sorted(SEALED_ROLES))} "
                "rows are the sealed integrity anchors this review is checked "
                f"against, so rehashing them would forge the seal instead of "
                f"detecting drift. If the {role} input really changed, seal a "
                "new attempt with seal-work-unit.py"
            )
        if role not in RESTAMPABLE_ROLES:
            fail(
                f"unknown role '{role}'; restampable roles are "
                + ", ".join(RESTAMPABLE_ROLES)
            )

    with guard(root):
        recover(root)
        path = root / "input-manifest.tsv"
        if not path.is_file():
            fail(
                f"no input-manifest.tsv in {root}; seal the work unit with "
                "seal-work-unit.py before refreshing its inputs"
            )
        rows = read_rows(path, INPUT_COLUMNS)
        key = (arguments.work_id, str(arguments.attempt))
        unit_rows = [
            row for row in rows if (row["work_id"], row["attempt"]) == key
        ]
        if not unit_rows:
            known = ", ".join(
                sorted({f"{row['work_id']}:{row['attempt']}" for row in rows})
            ) or "(no rows)"
            fail(
                f"no input-manifest rows for {arguments.work_id}:"
                f"{arguments.attempt}; seal it first with seal-work-unit.py. "
                f"Sealed units: {known}"
            )
        selected = [row for row in unit_rows if row["role"] in roles]
        if not selected:
            present = ", ".join(sorted({row["role"] for row in unit_rows}))
            fail(
                f"{arguments.work_id}:{arguments.attempt} has no "
                f"{', '.join(roles)} rows; its roles are {present} — pass a "
                "matching --role"
            )

        changes = 0
        for row in selected:
            input_path = Path(row["input_path"])
            if not input_path.is_file():
                fail(
                    f"manifest input no longer exists: {input_path}; restore "
                    "the file or reseal the attempt without it"
                )
            try:
                payload = input_path.read_bytes()
            except OSError as error:
                fail(f"cannot read {input_path}: {error}")
            size = str(len(payload))
            sha = digest(payload)
            if row["bytes"] == size and row["sha256"] == sha:
                print(f"unchanged {row['role']} {input_path} {size} bytes")
                continue
            print(
                f"{'would restamp' if arguments.dry_run else 'restamped'} "
                f"{row['role']} {input_path} bytes {row['bytes']}->{size} "
                f"sha256 {row['sha256'][:12]}->{sha[:12]}"
            )
            changes += 1
            if not arguments.dry_run:
                row["bytes"] = size
                row["sha256"] = sha

        if arguments.dry_run:
            print(
                f"refresh-manifest.py: dry run, {changes} of {len(selected)} "
                "row(s) would change; nothing written"
            )
            return 0
        if changes:
            commit(
                root,
                raw_table(root, "orchestration.tsv", ORCHESTRATION_COLUMNS),
                encode(INPUT_COLUMNS, rows),
            )
        print(
            f"refresh-manifest.py: restamped {changes} of {len(selected)} "
            f"{'/'.join(roles)} row(s) for {arguments.work_id}:"
            f"{arguments.attempt}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
