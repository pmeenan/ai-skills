#!/usr/bin/env python3
"""Manage ref-counted Chromium review worktree leases.

Each pinned patchset owns a lock directory, `cl-<CL>-ps<PS>/`, holding one
append-only JSON-lines activity log per holder: `<holder>.log`. Several
independent reviews (different agents or models) may hold the same pin at the
same time; each has its own token, its own liveness, and its own release. The
pin is live while any holder log has a recent mtime, so the directory entries
are the reference count and the cached worktree survives until the last holder
goes away. Short fcntl locks serialize mutations, but no process or stdin
stream must remain alive between commands.
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

# Exit codes callers branch on. OWNERSHIP_LOST means this review was replaced
# and must stop; NO_RECORDED_LEASE means it never held one, so a caller may
# safely mint a fresh identity.
OWNERSHIP_LOST = 3
NO_RECORDED_LEASE = 4

# A holder log whose last event is one of these did not end by its owner's
# choice — the review was replaced and may not quietly return.
TAKEOVER_EVENTS = frozenset(
    {"forced-takeover", "stale-takeover", "garbage-collected-stale"}
)

# Holder keys never contain a dot, so `<holder>.log` can never be confused with
# an archived `<holder>.<state>-<stamp>-<token>-<random>.log`.
HOLDER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
HOLDER_LOG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.log")
PIN_DIR_PATTERN = re.compile(r"cl-[0-9]+-ps[0-9]+")


class LeaseReadError(Exception):
    """A holder log exists but does not contain a valid owner row."""


def fail(message: str, code: int = 2) -> None:
    print(f"worktree-lease.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def warn(message: str) -> None:
    print(f"worktree-lease.py: WARNING: {message}", file=sys.stderr)


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def validate_stale_seconds(value: int) -> int:
    if value < 60:
        fail("--stale-seconds must be at least 60")
    return value


def validate_holder(value: str) -> str:
    if HOLDER_PATTERN.fullmatch(value) is None:
        fail(
            "--holder must be 1-64 characters of [A-Za-z0-9_-] and start with "
            f"an alphanumeric: {value!r}"
        )
    return value


@contextmanager
def mutation_guard(lock_root: Path, timeout: float = 30.0) -> Iterator[None]:
    """Serialize every lease mutation under one lock-root guard.

    One guard for the whole lock root — rather than one per pin — keeps a
    consistent order against `gc`, which walks every pin while holding it.
    """
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


def lock_root_of(pin_dir: Path) -> Path:
    return pin_dir.parent


def guard_root_for(holder_log: Path) -> Path:
    """The canonical lock root guarding a holder log.

    Migrated logs live at `locks/cl-<CL>-ps<PS>/<holder>.log` and pre-upgrade
    ones directly at `locks/cl-<CL>-ps<PS>.log`. Both must serialize against
    the same guard, or a legacy heartbeat can race the migration that moves
    the log out from under it.
    """
    if PIN_DIR_PATTERN.fullmatch(holder_log.parent.name):
        return holder_log.parent.parent
    return holder_log.parent


def pin_dir_for(holder_log: Path) -> Path:
    """The pin lock directory a recorded holder log belongs to."""
    if PIN_DIR_PATTERN.fullmatch(holder_log.parent.name):
        return holder_log.parent
    return holder_log.with_suffix("")


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
    warn(f"archived corrupt lease {path} as {destination}")
    return destination


def owner_or_fail(path: Path) -> dict[str, object]:
    try:
        return first_row(path)
    except LeaseReadError as error:
        fail(str(error))


def holder_logs(pin_dir: Path) -> list[Path]:
    """Active (non-archived) holder logs in a pin lock directory."""
    if not pin_dir.is_dir():
        return []
    return sorted(
        path for path in pin_dir.glob("*.log")
        if path.is_file() and HOLDER_LOG_PATTERN.fullmatch(path.name)
    )


def archived_holder_logs(pin_dir: Path) -> list[Path]:
    """Archived (`<holder>.<state>-...`) logs in a pin lock directory."""
    if not pin_dir.is_dir():
        return []
    return sorted(
        path for path in pin_dir.glob("*.log")
        if path.is_file() and not HOLDER_LOG_PATTERN.fullmatch(path.name)
    )


def holder_key_of(log: Path) -> str:
    """The holder key of an active or archived log name."""
    return log.name.split(".", 1)[0]


def last_event(path: Path) -> str:
    event = ""
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("event"), str):
                    event = row["event"]
    except (OSError, UnicodeError):
        return ""
    return event


def live_holders(
    pin_dir: Path, stale_seconds: int
) -> list[tuple[Path, dict[str, object]]]:
    result: list[tuple[Path, dict[str, object]]] = []
    for path in holder_logs(pin_dir):
        try:
            owner = first_row(path)
        except LeaseReadError:
            continue
        if lease_age(path) <= stale_seconds:
            result.append((path, owner))
    return result


def legacy_lease_path(pin_dir: Path) -> Path:
    return pin_dir.with_name(pin_dir.name + ".log")


def migrate_legacy_pin(pin_dir: Path) -> None:
    """Fold a pre-ref-count single-file lease into its pin lock directory.

    The caller must already hold the lock-root mutation guard. Liveness is
    preserved by copying the original mtime, so an in-flight legacy review
    keeps holding its worktree across the upgrade.
    """
    legacy = legacy_lease_path(pin_dir)
    if not legacy.is_file():
        return
    pin_dir.mkdir(parents=True, exist_ok=True)
    activity_mtime = legacy.stat().st_mtime
    try:
        owner = first_row(legacy)
    except LeaseReadError:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = pin_dir / (
            f"legacy.corrupt-{stamp}-no-token-{secrets.token_hex(3)}.log"
        )
        os.replace(legacy, destination)
        os.utime(destination, (activity_mtime, activity_mtime))
        warn(f"archived corrupt lease {legacy} as {destination}")
        return
    token = str(owner["token"])
    destination = pin_dir / f"legacy-{token[:8]}.log"
    while destination.exists():
        destination = pin_dir / f"legacy-{token[:8]}-{secrets.token_hex(3)}.log"
    os.replace(legacy, destination)
    os.utime(destination, (activity_mtime, activity_mtime))
    warn(
        f"migrated single-holder lease {legacy} to ref-counted holder "
        f"{destination}"
    )


def resolve_holder_log(recorded: Path, token: str) -> Path:
    """Resolve the holder log a review's pin.md points at.

    Falls back to a token search inside the pin lock directory so a review
    pinned before the ref-count upgrade keeps working after migration.
    """
    if recorded.is_file():
        return recorded
    if recorded.suffix == ".log":
        pin_dir = recorded.with_suffix("")
        for candidate in holder_logs(pin_dir):
            try:
                if first_row(candidate)["token"] == token:
                    return candidate
            except LeaseReadError:
                continue
    return recorded


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


def recorded_lease(review_dir: Path) -> tuple[Path, str]:
    """The lease path and token exactly as pin.md records them."""
    recorded = Path(pin_field(review_dir, "Worktree lease"))
    token = pin_field(review_dir, "Worktree lease token")
    return recorded, token


@contextmanager
def held_holder_log(review_dir: Path) -> Iterator[tuple[Path, str]]:
    """Guard, migrate, then resolve a review's holder log.

    Resolution must happen under the guard: a legacy lease resolved first and
    locked afterwards can be migrated in between, leaving the caller appending
    to a path that no longer exists — or recreating one after migration.
    """
    recorded, token = recorded_lease(review_dir)
    with mutation_guard(guard_root_for(recorded)):
        migrate_legacy_pin(pin_dir_for(recorded))
        yield resolve_holder_log(recorded, token), token


def acquire(arguments: argparse.Namespace) -> None:
    pin_dir = arguments.lease.resolve()
    review_dir = arguments.review_dir.resolve()
    holder = validate_holder(arguments.holder)
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    with mutation_guard(lock_root_of(pin_dir)):
        migrate_legacy_pin(pin_dir)
        pin_dir.mkdir(parents=True, exist_ok=True)
        path = pin_dir / f"{holder}.log"
        if path.exists():
            try:
                owner = first_row(path)
            except LeaseReadError:
                archive_corrupt_lease(path)
            else:
                age = lease_age(path)
                fresh = age <= stale_seconds
                same_review = str(owner.get("review_dir", "")) == str(review_dir)
                if fresh and same_review and not arguments.force:
                    # Re-pinning the same review directory (resume, refresh)
                    # keeps the original token so pin.md stays valid. The
                    # `reused` state tells the caller this lease predates the
                    # current invocation and must survive its failure.
                    token = str(owner["token"])
                    append_event(
                        path, token, "reacquired", review_dir=str(review_dir)
                    )
                    print(f"{token}\treused")
                    return
                if fresh and not arguments.force:
                    owner_review = owner.get("review_dir", "unknown")
                    fail(
                        f"holder {holder!r} already holds this pin "
                        f"({int(age)}s since progress; review {owner_review}): "
                        f"{path}. Concurrent reviews must pass a distinct "
                        "--holder; use --force-restart only after explicit "
                        "user confirmation.",
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
            "holder": holder,
            "host": socket.gethostname(),
            "peer_holders": [
                other.stem for other, _ in live_holders(pin_dir, stale_seconds)
                if other != path
            ],
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
    print(f"{token}\tcreated")


def heartbeat(arguments: argparse.Namespace) -> None:
    review_dir = arguments.review_dir.resolve()
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    with held_holder_log(review_dir) as (path, token):
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


def archive_released(path: Path, token: str, message: str) -> Path:
    """Release an already-guarded holder log."""
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
    with held_holder_log(review_dir) as (path, token):
        destination = archive_released(path, token, arguments.message)
    print(destination)


def release_token(arguments: argparse.Namespace) -> None:
    recorded = arguments.lease.resolve()
    with mutation_guard(guard_root_for(recorded)):
        migrate_legacy_pin(pin_dir_for(recorded))
        path = resolve_holder_log(recorded, arguments.token)
        destination = archive_released(path, arguments.token, arguments.message)
    print(destination)


def check(arguments: argparse.Namespace) -> None:
    review_dir = arguments.review_dir.resolve()
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    with held_holder_log(review_dir) as (path, token):
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


def holder_of(arguments: argparse.Namespace) -> None:
    """Print the holder key a review directory already owns.

    This is how a re-pin recovers its own identity instead of minting a second
    holder. The three outcomes are deliberately distinct, because a caller
    must never turn the middle one into a fresh identity:

      exit 0                  this review owns `<holder>` (printed on stdout)
      exit OWNERSHIP_LOST     it was replaced or expired — it must stop
      exit NO_RECORDED_LEASE  it never held one — a fresh identity is safe

    Every ownership decision is made under the mutation guard so a concurrent
    release or takeover cannot land between resolution and token validation.
    """
    review_dir = arguments.review_dir.resolve()
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    pin = review_dir / "pin.md"
    if not pin.is_file():
        fail(f"review has no pin.md: {pin}", code=NO_RECORDED_LEASE)
    try:
        lines = pin.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"cannot read {pin}: {error}", code=NO_RECORDED_LEASE)
    fields: dict[str, str] = {}
    for label in ("Worktree lease", "Worktree lease token"):
        prefix = f"- {label}: "
        for line in lines:
            if line.startswith(prefix):
                fields[label] = line.removeprefix(prefix)
                break
    if len(fields) != 2:
        fail(f"{pin} records no worktree lease", code=NO_RECORDED_LEASE)
    recorded = Path(fields["Worktree lease"])
    token = fields["Worktree lease token"]

    with mutation_guard(guard_root_for(recorded)):
        migrate_legacy_pin(pin_dir_for(recorded))
        pin_dir = pin_dir_for(recorded)
        path = resolve_holder_log(recorded, token)
        if path.is_file():
            try:
                owner = first_row(path)
            except LeaseReadError:
                owner = None
            if owner is not None and owner["token"] == token:
                if not PIN_DIR_PATTERN.fullmatch(path.parent.name):
                    fail(
                        f"holder log is not inside a pin lock directory: {path}",
                        code=OWNERSHIP_LOST,
                    )
                age = lease_age(path)
                if age > stale_seconds:
                    # Matching the token is not enough: an hour without
                    # progress means gc may already have retired this holder
                    # and reclaimed the worktree, so reviving it silently
                    # would resume a review whose evidence is no longer
                    # guaranteed to exist.
                    fail(
                        f"this review's lease expired {int(age)}s after its "
                        f"last progress (limit {stale_seconds}s): {path}. It "
                        "must stop rather than silently revive; pass an "
                        "explicit --holder only if the user confirms "
                        "restarting it.",
                        code=OWNERSHIP_LOST,
                    )
                print(holder_key_of(path))
                return
            fail(
                f"this review's lease at {path} is now held by another review; "
                "it was replaced and must stop. Re-running under a different "
                "identity would resume a review that lost its pin — pass an "
                "explicit --holder only if the user confirms a takeover.",
                code=OWNERSHIP_LOST,
            )
        # No active log: the archives say whether this review ended its own
        # lease or had it taken away.
        for archive in archived_holder_logs(pin_dir):
            try:
                owner = first_row(archive)
            except LeaseReadError:
                continue
            if owner["token"] != token:
                continue
            event = last_event(archive)
            if event == "released":
                print(holder_key_of(archive))
                return
            fail(
                f"this review's lease ended with '{event}' ({archive}); it was "
                "replaced or expired and must stop rather than resume under a "
                "new identity.",
                code=OWNERSHIP_LOST,
            )
        fail(
            f"no lease history for this review under {pin_dir}",
            code=NO_RECORDED_LEASE,
        )


def holders(arguments: argparse.Namespace) -> None:
    """Print one `holder<TAB>age<TAB>review_dir` row per live holder."""
    pin_dir = arguments.lease.resolve()
    stale_seconds = validate_stale_seconds(arguments.stale_seconds)
    with mutation_guard(lock_root_of(pin_dir)):
        migrate_legacy_pin(pin_dir)
    for path, owner in live_holders(pin_dir, stale_seconds):
        review = owner.get("review_dir", "unknown")
        print(f"{path.stem}\t{int(lease_age(path))}\t{review}")


def pin_is_live(pin_dir: Path, stale_seconds: int) -> bool:
    return bool(live_holders(pin_dir, stale_seconds))


def recent_takeover_age(pin_dir: Path) -> float | None:
    archives = [
        *pin_dir.glob("*.stale-*.log"),
        *pin_dir.glob("*.forced-*.log"),
        *pin_dir.glob("*.corrupt-*.log"),
    ]
    ages = [lease_age(archive) for archive in archives if archive.is_file()]
    return min(ages) if ages else None


def prune_archived_leases(lock_root: Path) -> None:
    if not lock_root.is_dir():
        return
    archives = [
        *lock_root.glob("cl-*-ps*/*.*-*.log"),
        # Pre-ref-count archives written directly into the lock root.
        *lock_root.glob("cl-*-ps*.*-*.log"),
    ]
    for archive in archives:
        if archive.is_file() and lease_age(archive) > ARCHIVE_RETENTION_SECONDS:
            try:
                archive.unlink()
            except OSError as error:
                warn(f"could not prune archived lease {archive}: {error}")


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


def retire_dead_holders(pin_dir: Path) -> None:
    """Archive every remaining holder log of a pin with no live holder."""
    for path in holder_logs(pin_dir):
        try:
            owner = first_row(path)
        except LeaseReadError:
            archive_corrupt_lease(path)
            continue
        age = lease_age(path)
        activity_mtime = path.stat().st_mtime
        token = str(owner["token"])
        append_event(
            path, token, "garbage-collected-stale", age_seconds=int(age)
        )
        archive_lease(path, "stale", token, activity_mtime=activity_mtime)


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
            pin_dir = lock_root / candidate.name
            migrate_legacy_pin(pin_dir)
            if pin_is_live(pin_dir, stale_seconds):
                continue
            retire_dead_holders(pin_dir)

            takeover_age = recent_takeover_age(pin_dir)
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
                    warn(
                        "preserving non-empty unregistered cache directory "
                        f"{candidate}; inspect and remove it manually if safe"
                    )
                continue
            status = subprocess.run(
                ["git", "-C", str(candidate), "status", "--porcelain", "--untracked-files=all"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if status.returncode != 0:
                warn(f"preserving unreadable inactive worktree {candidate}")
            elif status.stdout:
                warn(
                    f"preserving dirty inactive worktree {candidate}; inspect "
                    f"it, then run git -C {repo} worktree remove --force "
                    f"{candidate} only if safe"
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
                    warn(
                        f"could not remove {candidate}: "
                        f"{removed.stderr.strip()}"
                    )
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "prune"], check=True
        )
        prune_archived_leases(lock_root)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    # acquire prints "<token>\t<created|reused>"; `reused` means the lease
    # predates this invocation, so a failing caller must not release it.
    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("lease", type=Path, help="pin lock directory")
    acquire_parser.add_argument("--review-dir", required=True, type=Path)
    acquire_parser.add_argument("--holder", required=True)
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

    holder_of_parser = subparsers.add_parser("holder-of")
    holder_of_parser.add_argument("review_dir", type=Path)
    holder_of_parser.add_argument("--stale-seconds", type=int, default=DEFAULT_STALE_SECONDS)
    holder_of_parser.set_defaults(handler=holder_of)

    holders_parser = subparsers.add_parser("holders")
    holders_parser.add_argument("lease", type=Path, help="pin lock directory")
    holders_parser.add_argument("--stale-seconds", type=int, default=DEFAULT_STALE_SECONDS)
    holders_parser.set_defaults(handler=holders)

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
