#!/usr/bin/env python3
"""Validate one worker artifact before its orchestration attempt is collected."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from artifact_tables import effective_tables


ROW_ID = re.compile(r"^(?:[A-Z][A-Z0-9]*-\d+|R\d+-RC\d+-\d+)$")
CITATION = re.compile(r"(?:^|[\s`(\[])([A-Za-z0-9_.+@{}\-/]+):\d+")


def fail(message: str) -> None:
    print(f"validate-worker-artifact.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def inventory_check(root: Path, artifact: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="inventory-artifact-check.") as temporary:
        isolated = Path(temporary)
        profile = root / "profile.json"
        if profile.is_file():
            shutil.copy2(profile, isolated / "profile.json")
        if artifact.name == "inventory.md" and artifact.parent == root:
            destination = isolated / "inventory.md"
        else:
            destination = isolated / "inventory" / artifact.name
            destination.parent.mkdir()
        shutil.copy2(artifact, destination)
        builder = Path(__file__).with_name("build-review-indexes.py")
        result = subprocess.run(
            [sys.executable, str(builder), str(isolated)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            fail(result.stderr.strip() or result.stdout.strip())


def ledger_check(parsed: list[tuple[str, list[str], list[dict[str, str]]]],
                 artifact: Path) -> None:
    headings = {heading for heading, _, _ in parsed}
    if artifact.name != "PR.md" and "reopened" not in artifact.parts:
        for required in ("Compliance matrix", "Candidate rows"):
            if required not in headings:
                fail(f"{artifact} lacks exact '{required}' heading")
    for heading, header, rows in parsed:
        if heading == "Compliance matrix":
            if not {"question", "answer", "evidence"}.issubset(header):
                fail(f"{artifact} compliance matrix has wrong columns")
            for index, row in enumerate(rows, 1):
                answer = row.get("answer", "").strip()
                evidence = row.get("evidence", "").strip()
                if not answer or not evidence:
                    fail(
                        f"{artifact} compliance matrix row {index} has a blank "
                        "answer/evidence"
                    )
                if re.fullmatch(
                    r"(?i)(yes|pass|clean|safe)(?:\s*[—-].*)?", answer
                ) and not CITATION.search(evidence):
                    fail(
                        f"{artifact} compliance matrix row {index} is a "
                        "citation-free PASS"
                    )
                if answer.upper().startswith("N/A") and not re.search(
                    r"[—:-]\s*\S", answer
                ):
                    fail(
                        f"{artifact} compliance matrix row {index} has N/A "
                        "without a reason"
                    )
        if heading in {"Candidate rows", "Prior-feedback rows"}:
            if "id" not in header:
                fail(f"{artifact} {heading} table has no id column")
            for row in rows:
                identifier = row.get("id", "").strip()
                if identifier and ROW_ID.fullmatch(identifier) is None:
                    fail(f"{artifact} has invalid row ID '{identifier}'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--kind", choices=("auto", "inventory", "ledger", "generic"),
        default="auto",
    )
    arguments = parser.parse_args()
    root = arguments.review_dir.resolve()
    artifact = arguments.artifact.resolve()
    if not root.is_dir():
        fail(f"review directory does not exist: {root}")
    if not artifact.is_file():
        fail(f"artifact does not exist: {artifact}")
    if root not in artifact.parents:
        fail(f"artifact is outside review directory: {artifact}")
    try:
        text = artifact.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        fail(f"cannot read {artifact}: {error}")
    parsed, errors = effective_tables(text, str(artifact))
    if errors:
        fail("; ".join(errors))

    kind = arguments.kind
    relative = artifact.relative_to(root)
    if kind == "auto":
        if relative.as_posix() == "inventory.md" or relative.parts[:1] == ("inventory",):
            kind = "inventory"
        elif relative.parts[:1] == ("ledger",):
            kind = "ledger"
        else:
            kind = "generic"
    if kind == "inventory":
        inventory_check(root, artifact)
    elif kind == "ledger":
        ledger_check(parsed, artifact)
    print(f"valid {kind}: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
