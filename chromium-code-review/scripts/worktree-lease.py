#!/usr/bin/env python3
"""Manage timestamped Chromium review worktree leases.

A lease is an append-only JSON-lines activity log. Its mtime is the liveness
signal; the first row owns a random token copied into pin.md. Short fcntl locks
serialize mutations, but no process or stdin stream must remain alive between
commands.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
from typing import Iterator


DEFAULT_STALE_SECONDS = os.environ.get("CHROMIUM_REVIEW_LEASE_SECONDS", "3600")
ARCHIVE_RETENTION_SECONDS = 30 * 24 * 60 * 60
WORKTREE_REMOVAL_MULTIPLIER = 2


class LeaseReadError(Exception):
    """The current lease exists but does not contain a valid owner row."""


def fail(message: str, code: int = 2) -> None:
    print(f"worktree-lease.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def validate_stale_seconds(value: int) -> int:
    if value < 60:
        fail("--stale-seconds must be at least 60")
    return value


@contextmanager
def mutation_guard(lock_root: Path, timeout: float = 30.0) -> Iterator[None]:
    lock_root.mkdir(parents=True, exist_ok=True)
    guard = lock_root / ".lease-guard.lock"
    with guard.open("a+", encoding="utf-8") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fail(f"timed out waiting for lease mutation guard: {guard}")
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def lease_age(path: Path) -> float:
    return max(0.0, time.time() - path.stat().st_mtime)


def first_row(path: Path) -> dict[str, object]:
    try:
        with path.open(encoding="utf-8") as stream:
            line = stream.readline()
        value = json.loads(line)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LeaseReadError(f"cannot read lease {path}: {error}") from error
    token = value.get("token") if isinstance(value, dict) else None
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{32}", token) is None:
        raise LeaseReadError(f"lease has no valid owner token: {path}")
    return value


def append_event(path: Path, token: str, event: str, **extra: object) -> None:
    row: dict[str, object] = {
        "at": now_text(),
        "event": event,
        "token": token,
        **extra,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def archive_lease(
    path: Path,
    state: str,
    token: str,
    *,
    activity_mtime: float | None = None,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = path.with_name(
        f"{path.stem}.{state}-{stamp}-{token[:8]}-{secrets.token_hex(3)}{path.suffix}"
    )
    os.replace(path, destination)
    if activity_mtime is not None:
        os.utime(destination, (activity_mtime, activity_mtime))
    return destination


def archive_corrupt_lease(path: Path) -> Path:
    activity_mtime = path.stat().st_mtime
    destination = archive_lease(
        path, "corrupt", "no-token", activity_mtime=activity_mtime
    )
    print(
        f"worktree-lease.py: WARNING: archived corrupt lease {path} as "
        f"{destination}",
        file=sys.stderr,
    )
    return destination


def owner_or_fail(path: Path) -> dict[str, object]:
    try:
        return first_row(path)
    except LeaseReadError as error:
        fail(str(error))


def pin_field(review_dir: Path, label: str) -> str:
    pin = review_dir / "pin.md"
    try:
        lines = pin.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"cannot read {pin}: {error}")
    prefix = f"- {label}: "
    for line in lines:
        if line.startswith(prefix):
            return line.removeprefix(prefix)
    fail(f"{pin} has no '{label}' field")


def lease_from_review(review_dir: Path) -> tuple[Path, str]:
    path = Path(pin_field(review_dir, "Worktree lease"))
    token = pin_field(review_dir, "Worktree lease token")
    return path, token


def acquire(arguments: argparse.Namespace) -> None:
    path = arguments.lease.resolve()
    review_dir = arguments.review_dir.resolve()
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    with mutation_guard(path.parent):
        if path.exists():
            try:
                owner = first_row(path)
            except LeaseReadError:
                archive_corrupt_lease(path)
            else:
                age = lease_age(path)
                if age <= stale_seconds and not arguments.force:
                    owner_review = owner.get("review_dir", "unknown")
                    fail(
                        f"CL worktree lease is active ({int(age)}s since progress; "
                        f"review {owner_review}): {path}. Use --force-restart only "
                        "after explicit user confirmation.",
                        code=3,
                    )
                old_token = str(owner["token"])
                activity_mtime = path.stat().st_mtime
                append_event(
                    path,
                    old_token,
                    "forced-takeover" if arguments.force else "stale-takeover",
                    age_seconds=int(age),
                    replacement_review=str(review_dir),
                )
                archive_lease(
                    path,
                    "forced" if arguments.force else "stale",
                    old_token,
                    activity_mtime=(None if arguments.force else activity_mtime),
                )

        token = secrets.token_hex(16)
        row = {
            "at": now_text(),
            "event": "acquired",
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "review_dir": str(review_dir),
            "token": token,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    print(token)


def heartbeat(arguments: argparse.Namespace) -> None:
    review_dir = arguments.review_dir.resolve()
    path, token = lease_from_review(review_dir)
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    with mutation_guard(path.parent):
        if not path.exists():
            fail(f"lease is absent; reacquire before continuing: {path}", code=3)
        owner = owner_or_fail(path)
        if owner["token"] != token:
            fail(f"lease was replaced by another review: {path}", code=3)
        age = lease_age(path)
        if age > stale_seconds:
            fail(
                f"lease expired {int(age)}s after its last progress; reacquire "
                "before continuing",
                code=3,
            )
        append_event(path, token, "heartbeat", message=arguments.message)


def release_values(path: Path, token: str, message: str) -> Path:
    with mutation_guard(path.parent):
        if not path.exists():
            fail(f"lease is already absent: {path}", code=3)
        owner = owner_or_fail(path)
        if owner["token"] != token:
            fail(f"refusing to release another review's lease: {path}", code=3)
        append_event(path, token, "released", message=message)
        destination = archive_lease(path, "released", token)
        if path.exists():
            fail(f"active lease path still exists after release: {path}")
        if not destination.is_file():
            fail(f"release archive was not created: {destination}")
    return destination


def release(arguments: argparse.Namespace) -> None:
    review_dir = arguments.review_dir.resolve()
    path, token = lease_from_review(review_dir)
    destination = release_values(path, token, arguments.message)
    print(destination)


def release_token(arguments: argparse.Namespace) -> None:
    destination = release_values(
        arguments.lease.resolve(), arguments.token, arguments.message
    )
    print(destination)


def check(arguments: argparse.Namespace) -> None:
    review_dir = arguments.review_dir.resolve()
    path, token = lease_from_review(review_dir)
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    if not path.is_file():
        fail(f"active lease is absent: {path}", code=3)
    owner = owner_or_fail(path)
    if owner["token"] != token:
        fail(f"lease token does not match this review: {path}", code=3)
    age = lease_age(path)
    if age > stale_seconds:
        fail(
            f"lease is stale ({int(age)}s since progress; limit "
            f"{stale_seconds}s): {path}",
            code=3,
        )
    print(f"active {int(age)}s {path}")


def lease_is_active(path: Path, stale_seconds: int) -> bool:
    if not path.is_file():
        return False
    try:
        first_row(path)
        return lease_age(path) <= stale_seconds
    except LeaseReadError:
        return False


def recent_takeover_age(path: Path) -> float | None:
    archives = [
        *path.parent.glob(f"{path.stem}.stale-*{path.suffix}"),
        *path.parent.glob(f"{path.stem}.forced-*{path.suffix}"),
        *path.parent.glob(f"{path.stem}.corrupt-*{path.suffix}"),
    ]
    ages = [lease_age(archive) for archive in archives if archive.is_file()]
    return min(ages) if ages else None


def prune_archived_leases(lock_root: Path) -> None:
    for archive in lock_root.glob("cl-*-ps*.*-*.log"):
        if archive.is_file() and lease_age(archive) > ARCHIVE_RETENTION_SECONDS:
            try:
                archive.unlink()
            except OSError as error:
                print(
                    f"worktree-lease.py: WARNING: could not prune archived "
                    f"lease {archive}: {error}",
                    file=sys.stderr,
                )


def registered_worktrees(repo: Path) -> set[Path]:
    output = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    return {
        Path(line.removeprefix("worktree ")).resolve()
        for line in output.splitlines()
        if line.startswith("worktree ")
    }


def gc_cache(arguments: argparse.Namespace) -> None:
    repo = arguments.repo.resolve()
    worktree_root = arguments.worktree_root.resolve()
    lock_root = worktree_root.parent / "locks"
    exclude = arguments.exclude.resolve()
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    with mutation_guard(lock_root):
        registered = registered_worktrees(repo)
        for candidate in sorted(worktree_root.glob("cl-*-ps*")):
            if not candidate.is_dir() or candidate.resolve() == exclude:
                continue
            lease = lock_root / f"{candidate.name}.log"
            if lease_is_active(lease, stale_seconds):
                continue
            if lease.exists():
                try:
                    owner = first_row(lease)
                except LeaseReadError:
                    archive_corrupt_lease(lease)
                else:
                    age = lease_age(lease)
                    activity_mtime = lease.stat().st_mtime
                    token = str(owner["token"])
                    append_event(
                        lease,
                        token,
                        "garbage-collected-stale",
                        age_seconds=int(age),
                    )
                    archive_lease(
                        lease, "stale", token, activity_mtime=activity_mtime
                    )

            takeover_age = recent_takeover_age(lease)
            removal_seconds = stale_seconds * WORKTREE_REMOVAL_MULTIPLIER
            if takeover_age is not None and takeover_age <= removal_seconds:
                print(
                    "worktree-lease.py: preserving inactive worktree during "
                    f"takeover cleanup grace ({int(takeover_age)}s of "
                    f"{removal_seconds}s): {candidate}",
                    file=sys.stderr,
                )
                continue

            resolved = candidate.resolve()
            if resolved not in registered:
                try:
                    candidate.rmdir()
                    print(f"Removed empty unregistered cache directory {candidate}", file=sys.stderr)
                except OSError:
                    print(
                        "worktree-lease.py: WARNING: preserving non-empty "
                        f"unregistered cache directory {candidate}; inspect and "
                        "remove it manually if safe",
                        file=sys.stderr,
                    )
                continue
            status = subprocess.run(
                ["git", "-C", str(candidate), "status", "--porcelain", "--untracked-files=all"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if status.returncode != 0:
                print(
                    f"worktree-lease.py: WARNING: preserving unreadable inactive worktree {candidate}",
                    file=sys.stderr,
                )
            elif status.stdout:
                print(
                    "worktree-lease.py: WARNING: preserving dirty inactive "
                    f"worktree {candidate}; inspect it, then run "
                    f"git -C {repo} worktree remove --force {candidate} only "
                    "if safe",
                    file=sys.stderr,
                )
            else:
                print(f"Removing inactive cached worktree {candidate} ...", file=sys.stderr)
                removed = subprocess.run(
                    ["git", "-C", str(repo), "worktree", "remove", str(candidate)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if removed.returncode != 0:
                    print(
                        f"worktree-lease.py: WARNING: could not remove {candidate}: "
                        f"{removed.stderr.strip()}",
                        file=sys.stderr,
                    )
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "prune"], check=True
        )
        prune_archived_leases(lock_root)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("lease", type=Path)
    acquire_parser.add_argument("--review-dir", required=True, type=Path)
    acquire_parser.add_argument("--stale-seconds", type=int, default=DEFAULT_STALE_SECONDS)
    acquire_parser.add_argument("--force", action="store_true")
    acquire_parser.set_defaults(handler=acquire)

    heartbeat_parser = subparsers.add_parser("heartbeat")
    heartbeat_parser.add_argument("review_dir", type=Path)
    heartbeat_parser.add_argument("message")
    heartbeat_parser.add_argument("--stale-seconds", type=int, default=DEFAULT_STALE_SECONDS)
    heartbeat_parser.set_defaults(handler=heartbeat)

    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("review_dir", type=Path)
    release_parser.add_argument("message", nargs="?", default="review complete")
    release_parser.set_defaults(handler=release)

    release_token_parser = subparsers.add_parser("release-token")
    release_token_parser.add_argument("lease", type=Path)
    release_token_parser.add_argument("token")
    release_token_parser.add_argument("message", nargs="?", default="setup failed")
    release_token_parser.set_defaults(handler=release_token)

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("review_dir", type=Path)
    check_parser.add_argument("--stale-seconds", type=int, default=DEFAULT_STALE_SECONDS)
    check_parser.set_defaults(handler=check)

    gc_parser = subparsers.add_parser("gc")
    gc_parser.add_argument("--repo", required=True, type=Path)
    gc_parser.add_argument("--worktree-root", required=True, type=Path)
    gc_parser.add_argument("--exclude", required=True, type=Path)
    gc_parser.add_argument("--stale-seconds", type=int, default=DEFAULT_STALE_SECONDS)
    gc_parser.set_defaults(handler=gc_cache)
    return result


def main() -> None:
    arguments = parser().parse_args()
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
