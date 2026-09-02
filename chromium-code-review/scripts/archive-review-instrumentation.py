#!/usr/bin/env python3
"""Archive one instrumented review for later bulk cost analysis.

The archive contains control-plane metrics, packet specifications, indexes,
and command read-cost logs. It deliberately excludes source-code payloads,
ledgers, findings, comments, and drafts. Runs are grouped by schema and the
committed skill Git revision (or an explicit version).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid


SCHEMA = "code-reads-v1"
DIRECTIVE = "instrumentation: code-reads-v1"
ROOT_FILES = (
    "pin.md", "directives.md", "profile.json", "profile.md", "plan.md",
    "orchestration.tsv", "input-manifest.tsv", "progress.md",
    "cost-report.tsv", "cost-report.md", "delivery-gate.md",
    "code-read-costs.tsv",
)
TREE_PATTERNS = (
    ("instrumentation/code-reads", "*.jsonl"),
    ("packets", "*.spec.tsv"),
    ("callers", "index.tsv"),
    ("indexes", "*.tsv"),
)


def fail(message: str) -> None:
    print(f"archive-review-instrumentation.py: ERROR: {message}",
          file=sys.stderr)
    raise SystemExit(2)


def field(text: str, label: str, default: str = "unknown") -> str:
    match = re.search(rf"^- {re.escape(label)}:\s*(.+?)\s*$", text, re.M)
    return match.group(1) if match else default


def safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unknown"


def git_version(skill_dir: Path) -> tuple[str, str, bool]:
    repository_head = subprocess.run(
        ["git", "-C", str(skill_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False)
    if repository_head.returncode != 0:
        fail("cannot resolve repository Git revision: "
             f"{repository_head.stderr.strip()}")
    revision = subprocess.run(
        ["git", "-C", str(skill_dir), "log", "-1", "--format=%H", "--",
         "."], capture_output=True, text=True, check=False)
    if revision.returncode != 0 or not revision.stdout.strip():
        fail(f"cannot resolve last skill Git revision: {revision.stderr.strip()}")
    dirty = subprocess.run(
        ["git", "-C", str(skill_dir), "diff", "--quiet", "HEAD", "--",
         "."], check=False).returncode != 0
    return (revision.stdout.strip(), repository_head.stdout.strip(), dirty)


def copy_selected(review_dir: Path, stage: Path) -> list[str]:
    copied = []
    for relative in ROOT_FILES:
        source = review_dir / relative
        if source.is_file():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(relative)
    for root, pattern in TREE_PATTERNS:
        source_root = review_dir / root
        if not source_root.is_dir():
            continue
        for source in sorted(source_root.glob(pattern)):
            if not source.is_file():
                continue
            relative = source.relative_to(review_dir)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(relative.as_posix())
    snapshot_manifest = review_dir / "skill-snapshot" / \
        "snapshot-manifest.json"
    if snapshot_manifest.is_file():
        target = stage / "snapshot-manifest.json"
        shutil.copyfile(snapshot_manifest, target)
        copied.append("snapshot-manifest.json")
    return copied


def run_identity(review_dir: Path, cl: str, patchset: str,
                 revision: str) -> dict[str, str]:
    """Return one persistent identity for this review directory."""
    path = review_dir / "instrumentation" / "run.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            fail(f"malformed instrumentation identity {path}: {error}")
        required = {"schema", "run_uuid", "run_id", "started_at"}
        if value.get("schema") != SCHEMA or not required.issubset(value):
            fail(f"invalid instrumentation identity: {path}")
        return {key: str(value[key]) for key in value}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_uuid = str(uuid.uuid4())
    run_id = (f"{stamp}-cl-{safe(cl)}-ps-{safe(patchset)}-"
              f"{safe(revision)[:12]}-{run_uuid[:12]}")
    label = ""
    directives = (review_dir / "directives.md").read_text(encoding="utf-8")
    for line in directives.splitlines():
        if line.startswith("instrumentation-label:"):
            label = line.split(":", 1)[1].strip()
            break
    value = {
        "schema": SCHEMA,
        "run_uuid": run_uuid,
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "label": label,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    try:
        # Do not overwrite an identity another process created concurrently.
        os.link(temporary, path)
        temporary.unlink()
    except FileExistsError:
        temporary.unlink(missing_ok=True)
        return run_identity(review_dir, cl, patchset, revision)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--canonical-skill-dir", type=Path)
    parser.add_argument("--version")
    arguments = parser.parse_args()
    review_dir = arguments.review_dir.resolve()
    directives = review_dir / "directives.md"
    if not directives.is_file() or DIRECTIVE not in {
            line.strip() for line in directives.read_text(
                encoding="utf-8").splitlines()}:
        fail(f"review is not opted into '{DIRECTIVE}'")

    manifest_path = review_dir / "skill-snapshot" / "snapshot-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read snapshot manifest: {error}")
    source_path = manifest.get("source_path")
    skill_dir = (arguments.canonical_skill_dir or
                 (Path(source_path) if isinstance(source_path, str) else None))
    if skill_dir is None:
        fail("canonical skill directory is unknown")
    skill_dir = skill_dir.resolve()
    if not (skill_dir / "SKILL.md").is_file():
        fail(f"not a canonical skill directory: {skill_dir}")

    commit, repository_head, dirty = git_version(skill_dir)
    version = safe(arguments.version or commit)
    if dirty and arguments.version is None:
        version += "-dirty"
    manifest_digest = hashlib.sha256(
        manifest_path.read_bytes()).hexdigest()
    pin_text = (review_dir / "pin.md").read_text(
        encoding="utf-8", errors="replace")
    title = re.search(r"^# CL ([0-9a-zA-Z_-]+).*patchset (\d+)", pin_text, re.M)
    cl = title.group(1) if title else "unknown"
    patchset = title.group(2) if title else safe(
        field(pin_text, "Pinned patchset"))
    revision = safe(field(pin_text, "Revision SHA"))
    identity = run_identity(review_dir, cl, patchset, revision)
    run_id = identity["run_id"]
    root = skill_dir / "instrumentation" / "runs" / SCHEMA / version
    root.mkdir(parents=True, exist_ok=True)
    destination = root / run_id
    if destination.exists():
        existing_metadata = destination / "metadata.json"
        try:
            existing = json.loads(existing_metadata.read_text(
                encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            fail(f"existing archive is unreadable: {destination}: {error}")
        if existing.get("run_uuid") != identity["run_uuid"]:
            fail(f"archive collision with another run: {destination}")
        print(destination)
        return 0
    stage = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=root))
    try:
        copied = copy_selected(review_dir, stage)
        metadata = {
            "schema": SCHEMA,
            "archived_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "skill_git_revision": commit,
            "repository_git_revision": repository_head,
            "skill_git_dirty": dirty,
            "version_directory": version,
            "run_uuid": identity["run_uuid"],
            "run_id": run_id,
            "instrumentation_label": identity.get("label", ""),
            "run_started_at": identity["started_at"],
            "snapshot_manifest_sha256": manifest_digest,
            "review": {"cl": cl, "patchset": patchset,
                       "revision": revision},
            "files": copied,
        }
        (stage / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        os.replace(stage, destination)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    pointer = review_dir / "instrumentation-archive.md"
    pointer.write_text(
        "# Instrumentation archive\n\n"
        f"- Schema: {SCHEMA}\n- Skill revision: {commit}\n"
        f"- Snapshot manifest SHA-256: {manifest_digest}\n"
        f"- Archive: {destination}\n",
        encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
