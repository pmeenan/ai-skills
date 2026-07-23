#!/usr/bin/env python3
"""Freeze the worker-facing Chromium review skill bundle into a review."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Iterator


MANIFEST = "snapshot-manifest.json"
GUARD_TIMEOUT_ENV = "CHROMIUM_REVIEW_GUARD_SECONDS"


def fail(message: str) -> None:
    print(f"snapshot-skill.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@contextmanager
def guard(review_dir: Path) -> Iterator[None]:
    path = review_dir / ".skill-snapshot.lock"
    with path.open("a+", encoding="utf-8") as stream:
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
                    fail(f"timed out waiting for skill snapshot guard: {path}")
                time.sleep(min(0.1, timeout))
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def selected_files(skill_dir: Path) -> list[Path]:
    files = [skill_dir / "SKILL.md"]
    references = skill_dir / "references"
    if references.is_dir():
        files.extend(references.rglob("*.md"))
    scripts = skill_dir / "scripts"
    if scripts.is_dir():
        files.extend(path for path in scripts.iterdir()
                     if path.is_file() and path.suffix in {".py", ".sh"})
    return sorted({path.resolve() for path in files})


def verify(snapshot: Path) -> None:
    manifest_path = snapshot / MANIFEST
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read snapshot manifest {manifest_path}: {error}")
    if value.get("schema_version") != 1 or not isinstance(value.get("files"), list):
        fail(f"invalid snapshot manifest: {manifest_path}")
    expected: set[str] = set()
    for item in value["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            fail(f"invalid snapshot manifest row in {manifest_path}")
        relative = item["path"]
        expected.add(relative)
        path = snapshot / relative
        try:
            payload = path.read_bytes()
        except OSError as error:
            fail(f"cannot read snapshotted input {path}: {error}")
        if len(payload) != item.get("bytes") or digest(payload) != item.get("sha256"):
            fail(f"snapshotted input changed after sealing: {path}")
    actual = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != MANIFEST
    }
    if actual != expected:
        fail(
            "snapshot file set differs from manifest; missing="
            f"{sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )


def create(skill_dir: Path, review_dir: Path, destination: Path) -> None:
    files = selected_files(skill_dir)
    if not files or not (skill_dir / "SKILL.md").is_file():
        fail(f"not a skill directory: {skill_dir}")
    stage = Path(tempfile.mkdtemp(prefix=".skill-snapshot.", dir=review_dir))
    try:
        payloads = {source: source.read_bytes() for source in files}
        rows = []
        for source in files:
            try:
                relative = source.relative_to(skill_dir).as_posix()
            except ValueError:
                fail(f"selected file escapes skill directory: {source}")
            payload = payloads[source]
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            try:
                target.chmod(source.stat().st_mode & 0o777)
            except OSError:
                pass
            rows.append({
                "path": relative,
                "bytes": len(payload),
                "sha256": digest(payload),
            })
        for source, payload in payloads.items():
            if source.read_bytes() != payload:
                fail(f"source changed while snapshotting: {source}")
        manifest = {
            "schema_version": 1,
            "source_path": str(skill_dir),
            "files": rows,
        }
        manifest_path = stage / MANIFEST
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for path in stage.rglob("*"):
            if path.is_file():
                path.chmod(path.stat().st_mode & ~0o222)
        os.replace(stage, destination)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    skill_dir = arguments.skill_dir.resolve()
    review_dir = arguments.review_dir.resolve()
    if not review_dir.is_dir():
        fail(f"review directory does not exist: {review_dir}")
    destination = review_dir / "skill-snapshot"
    with guard(review_dir):
        if destination.exists():
            if not destination.is_dir():
                fail(f"snapshot destination is not a directory: {destination}")
            verify(destination)
        elif arguments.check:
            fail(f"skill snapshot is absent: {destination}")
        else:
            create(skill_dir, review_dir, destination)
            verify(destination)
    print(f"current: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
