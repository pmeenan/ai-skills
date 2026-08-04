#!/usr/bin/env python3
"""Run one code-reading command and record its observable cost.

Enabled instrumented reviews use this wrapper for commands whose output is
consumed as code evidence (git diff/show/grep, rg, sed, and similar reads).
The command's stdout and stderr are replayed byte-for-byte and its exit status
is preserved. A compact JSONL event is appended under the review directory;
command output itself is never retained by this helper.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


SCHEMA = "code-reads-v1"
DIRECTIVE = "instrumentation: code-reads-v1"


def fail(message: str) -> None:
    print(f"instrument-command.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def enabled(review_dir: Path) -> bool:
    directives = review_dir / "directives.md"
    if not directives.is_file():
        return False
    return any(line.strip() == DIRECTIVE for line in
               directives.read_text(encoding="utf-8").splitlines())


def validate_command_shape(command: list[str]) -> None:
    """Reject measured command shapes known to emit accidental repo-wide data."""
    operation = Path(command[0]).name
    if operation in {"bash", "sh"} and "-c" in command:
        script_index = command.index("-c") + 1
        if script_index >= len(command):
            fail(f"{operation} -c lacks a script argument")
        if len(command) > script_index + 1:
            fail(
                f"{operation} -c pipeline must be one quoted command argument; "
                "trailing argv would become shell positional parameters"
            )
    if operation == "rg" and command[1:] == ["--files"]:
        fail(
            "unscoped 'rg --files' is forbidden in a Chromium worktree; use "
            "the inventory/caller indexes or add an explicit path scope"
        )


def append_event(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def main() -> int:
    raw = sys.argv[1:]
    try:
        divider = raw.index("--")
    except ValueError:
        fail("missing -- before command")
    command = raw[divider + 1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("work_id")
    parser.add_argument("attempt", type=int)
    parser.add_argument("--cwd", type=Path)
    arguments = parser.parse_args(raw[:divider])
    review_dir = arguments.review_dir.resolve()
    if not review_dir.is_dir():
        fail(f"no review directory: {review_dir}")
    if not enabled(review_dir):
        fail(f"{review_dir / 'directives.md'} lacks '{DIRECTIVE}'")
    if not arguments.work_id or any(char.isspace()
                                    for char in arguments.work_id):
        fail("work ID must be one non-empty token")
    if arguments.attempt < 1:
        fail("attempt must be positive")
    if not command:
        fail("missing command after --")
    validate_command_shape(command)
    cwd = (arguments.cwd or Path.cwd()).resolve()
    if not cwd.is_dir():
        fail(f"no command working directory: {cwd}")

    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout_file, \
            tempfile.TemporaryFile() as stderr_file:
        try:
            result = subprocess.run(command, cwd=cwd, stdout=stdout_file,
                                    stderr=stderr_file, check=False)
        except OSError as error:
            fail(f"cannot execute {command[0]}: {error}")
        elapsed_ms = round((time.monotonic() - started) * 1000)
        stdout_bytes = stdout_file.tell()
        stderr_bytes = stderr_file.tell()
        stdout_file.seek(0)
        stderr_file.seek(0)
        while chunk := stdout_file.read(1024 * 1024):
            sys.stdout.buffer.write(chunk)
        while chunk := stderr_file.read(1024 * 1024):
            sys.stderr.buffer.write(chunk)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.flush()

    encoded = json.dumps(command, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    event: dict[str, object] = {
        "schema": SCHEMA,
        "timestamp": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "work_id": arguments.work_id,
        "attempt": arguments.attempt,
        "cwd": str(cwd),
        "command": command,
        "command_sha256": hashlib.sha256(encoded).hexdigest(),
        "operation": Path(command[0]).name,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "elapsed_ms": elapsed_ms,
        "exit_code": result.returncode,
    }
    destination = (review_dir / "instrumentation" / "code-reads" /
                   f"{arguments.work_id}-attempt-{arguments.attempt}.jsonl")
    append_event(destination, event)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
