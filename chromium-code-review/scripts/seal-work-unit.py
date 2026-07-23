#!/usr/bin/env python3
"""Atomically register and hash a finalized Chromium review work unit."""

from __future__ import annotations

import argparse
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
from typing import Iterator


ORCHESTRATION_COLUMNS = (
    "phase", "work_id", "attempt", "state", "tier", "task_id", "brief",
    "artifact", "remaining_scope", "depends_on",
)
INPUT_COLUMNS = (
    "work_id", "attempt", "phase", "brief", "input_path", "role", "bytes",
    "sha256",
)
ROLES = {
    "control", "reference", "assigned", "candidate-packet", "card", "frame",
    "section", "prestate",
}
TIERS = {"mechanical", "standard", "frontier", "inherit"}
JOURNAL = ".work-unit-seal-transaction.json"
GUARD_TIMEOUT_ENV = "CHROMIUM_REVIEW_GUARD_SECONDS"


def fail(message: str) -> None:
    print(f"seal-work-unit.py: ERROR: {message}", file=sys.stderr)
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
                fail(f"{path} has wrong columns or order")
            return list(reader)
    except (OSError, csv.Error) as error:
        fail(f"cannot parse {path}: {error}")


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
                        f"{root / '.orchestration.lock'}"
                    )
                time.sleep(min(0.1, timeout))
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def recover(root: Path) -> None:
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
        fail(f"cannot recover interrupted seal transaction {journal}: {error}")
    atomic_write(root / "orchestration.tsv", orchestration)
    atomic_write(root / "input-manifest.tsv", inputs)
    journal.unlink()


def parse_input(value: str) -> tuple[str, Path]:
    role, separator, raw_path = value.partition("=")
    if not separator or role not in ROLES:
        fail(f"--input must be ROLE=/absolute/path with role in {sorted(ROLES)}")
    path = Path(raw_path)
    if not path.is_absolute():
        fail(f"input path must be absolute: {raw_path}")
    path = path.resolve()
    if not path.is_file():
        fail(f"input does not exist: {path}")
    return role, path


def validate_budget(root: Path, tier: str,
                    inputs: list[tuple[str, Path, bytes]]) -> None:
    profile_path = root / "profile.json"
    if not profile_path.is_file():
        return
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        context = profile.get("context_budget", {})
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read {profile_path}: {error}")
    unique = {path: len(payload) for _, path, payload in inputs}
    total = sum(unique.values())
    limits = []
    global_limit = context.get("worker_input_budget_bytes")
    if isinstance(global_limit, int):
        limits.append(global_limit)
    tier_limit = context.get("tier_worker_input_budget_bytes", {}).get(tier)
    if isinstance(tier_limit, int):
        limits.append(tier_limit)
    if limits and total > min(limits):
        fail(f"work unit inputs exceed budget ({total} > {min(limits)} bytes)")
    candidate_limit = context.get("candidate_packet_budget_bytes")
    candidate_total = sum(
        len(payload) for role, _, payload in inputs if role == "candidate-packet"
    )
    if isinstance(candidate_limit, int) and candidate_total > candidate_limit:
        fail(
            "candidate packet inputs exceed budget "
            f"({candidate_total} > {candidate_limit} bytes)"
        )


def same_rows(left: list[dict[str, str]], right: list[dict[str, str]],
              columns: tuple[str, ...]) -> bool:
    def normalized(rows: list[dict[str, str]]) -> list[tuple[str, ...]]:
        return sorted(tuple(row[column] for column in columns) for row in rows)

    return normalized(left) == normalized(right)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--tier", required=True, choices=sorted(TIERS))
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--depends-on", default="-")
    parser.add_argument("--remaining-scope", default="-")
    parser.add_argument("--input", action="append", default=[])
    arguments = parser.parse_args()

    root = arguments.review_dir.resolve()
    if not root.is_dir():
        fail(f"review directory does not exist: {root}")
    if arguments.attempt < 1:
        fail("--attempt must be positive")
    if not arguments.work_id or any(char in arguments.work_id for char in "\t\r\n"):
        fail("--work-id is invalid")
    brief_arg = arguments.brief
    artifact_arg = arguments.artifact
    if not brief_arg.is_absolute() or not artifact_arg.is_absolute():
        fail("--brief and --artifact must be absolute")
    brief = brief_arg.resolve()
    artifact = artifact_arg.resolve()
    if not brief.is_file() or root not in brief.parents:
        fail(f"brief must be an existing file inside the review: {brief}")
    if root not in artifact.parents:
        fail(f"artifact must be inside the review: {artifact}")

    snapshot_check = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("snapshot-skill.py")),
         str(Path(__file__).resolve().parent.parent), str(root), "--check"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if snapshot_check.returncode != 0:
        fail(
            "skill snapshot is absent or stale: "
            + (snapshot_check.stderr.strip() or snapshot_check.stdout.strip())
        )

    parsed_inputs = [parse_input(value) for value in arguments.input]
    snapshot = (root / "skill-snapshot").resolve()
    for role, path in parsed_inputs:
        if role == "reference" and snapshot not in path.parents:
            fail(f"reference input is not from the sealed skill snapshot: {path}")
    declared = [("brief", brief), *parsed_inputs]
    if len(set(declared)) != len(declared):
        fail("an input role/path is listed more than once")
    with guard(root):
        recover(root)
        all_inputs: list[tuple[str, Path, bytes]] = [
            ("brief", brief, brief.read_bytes())
        ]
        all_inputs.extend(
            (role, path, path.read_bytes()) for role, path in parsed_inputs
        )
        deduplicated = all_inputs
        validate_budget(root, arguments.tier, deduplicated)

        orchestration_path = root / "orchestration.tsv"
        inputs_path = root / "input-manifest.tsv"
        orchestration = read_rows(orchestration_path, ORCHESTRATION_COLUMNS)
        inputs = read_rows(inputs_path, INPUT_COLUMNS)
        key = (arguments.work_id, str(arguments.attempt))
        expected_orchestration = {
            "phase": arguments.phase,
            "work_id": arguments.work_id,
            "attempt": str(arguments.attempt),
            "state": "queued",
            "tier": arguments.tier,
            "task_id": "-",
            "brief": str(brief),
            "artifact": str(artifact),
            "remaining_scope": arguments.remaining_scope,
            "depends_on": arguments.depends_on,
        }
        expected_inputs = []
        for role, path, payload in deduplicated:
            expected_inputs.append({
                "work_id": arguments.work_id,
                "attempt": str(arguments.attempt),
                "phase": arguments.phase,
                "brief": str(brief),
                "input_path": str(path),
                "role": role,
                "bytes": str(len(payload)),
                "sha256": digest(payload),
            })
        existing_orchestration = [
            row for row in orchestration
            if (row["work_id"], row["attempt"]) == key
        ]
        existing_inputs = [
            row for row in inputs
            if (row["work_id"], row["attempt"]) == key
        ]
        if existing_orchestration or existing_inputs:
            if (
                existing_orchestration == [expected_orchestration]
                and same_rows(existing_inputs, expected_inputs, INPUT_COLUMNS)
            ):
                brief.chmod(brief.stat().st_mode & ~0o222)
                if brief.read_bytes() != all_inputs[0][2]:
                    fail(f"brief changed while restoring its seal: {brief}")
                print(
                    f"already sealed {arguments.work_id}:{arguments.attempt} "
                    f"{brief}"
                )
                return 0
            fail(
                f"attempt already exists but does not match the requested "
                f"seal: {key}; inspect the queued row instead of incrementing "
                "the attempt"
            )

        # Make the final brief immutable only after all rejectable checks pass.
        # A crash here is harmless: a subsequent invocation can still hash and
        # register the same read-only file.
        brief.chmod(brief.stat().st_mode & ~0o222)
        if brief.read_bytes() != all_inputs[0][2]:
            fail(f"brief changed while sealing: {brief}")
        orchestration.append(expected_orchestration)
        inputs.extend(expected_inputs)
        orchestration_payload = encode(ORCHESTRATION_COLUMNS, orchestration)
        input_payload = encode(INPUT_COLUMNS, inputs)
        journal = root / JOURNAL
        atomic_write(
            journal,
            json.dumps({
                "orchestration": orchestration_payload,
                "inputs": input_payload,
            }, sort_keys=True) + "\n",
        )
        recover(root)
    print(f"sealed {arguments.work_id}:{arguments.attempt} {brief}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
