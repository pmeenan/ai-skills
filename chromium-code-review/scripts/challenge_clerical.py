from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


def issue_classification(row: dict[str, str]) -> str:
    explicit = row.get("classification", "").strip().lower()
    if explicit:
        return explicit
    for field in ("scope", "required correction"):
        if re.search(r"\bclerical\b", row.get(field, ""), re.I):
            return "clerical"
    return ""


def load_clerical_resolutions(
    review_dir: Path, round_dir: Path, revision: str
) -> tuple[dict[tuple[str, str], dict[str, Any]], list[str]]:
    path = round_dir / "clerical-resolutions.json"
    if not path.is_file():
        return {}, []
    errors: list[str] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, [f"{path}: invalid JSON: {error}"]
    if not isinstance(value, dict) or value.get("draft_revision") != revision:
        return {}, [f"{path}: draft_revision must equal {revision}"]
    rows = value.get("resolutions")
    if not isinstance(rows, list):
        return {}, [f"{path}: resolutions must be an array"]
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            errors.append(f"{path}: every resolution must be an object")
            continue
        issue = row.get("issue")
        shard = row.get("shard")
        key = (str(shard), str(issue))
        if key in result:
            errors.append(f"{path}: duplicate resolution for {shard}/{issue}")
            continue
        if row.get("classification") != "clerical" or not row.get("evidence"):
            errors.append(
                f"{path}: {shard}/{issue} requires classification clerical and evidence"
            )
            continue
        corrections = row.get("corrections")
        if not isinstance(corrections, list) or not corrections:
            errors.append(f"{path}: {shard}/{issue} has no corrections")
            continue
        valid = True
        for correction in corrections:
            if not isinstance(correction, dict):
                valid = False
                errors.append(f"{path}: {shard}/{issue} correction is not an object")
                continue
            relative = correction.get("path", "")
            pure = PurePosixPath(relative)
            target = (review_dir / pure).resolve()
            try:
                target.relative_to(review_dir.resolve())
            except ValueError:
                valid = False
                errors.append(f"{path}: {shard}/{issue} path escapes review directory")
                continue
            if pure.is_absolute() or ".." in pure.parts or not target.is_file():
                valid = False
                errors.append(f"{path}: {shard}/{issue} has invalid path {relative}")
                continue
            kind = correction.get("kind")
            if kind == "structured-amendment":
                amendment = correction.get("amendment", "")
                text = target.read_text(encoding="utf-8")
                if relative != "reconciliation.md" or not amendment \
                        or amendment not in text or "replace-fields" not in text:
                    valid = False
                    errors.append(
                        f"{path}: {shard}/{issue} structured amendment is not present"
                    )
                continue
            if kind != "exact-text-projection":
                valid = False
                errors.append(f"{path}: {shard}/{issue} has unknown correction kind")
                continue
            before_relative = correction.get("before_path", "")
            before_pure = PurePosixPath(before_relative)
            before = (review_dir / before_pure).resolve()
            try:
                before.relative_to(review_dir.resolve())
            except ValueError:
                before = Path()
            if before_pure.is_absolute() or ".." in before_pure.parts \
                    or not before.is_file():
                valid = False
                errors.append(f"{path}: {shard}/{issue} has invalid before_path")
                continue
            before_payload = before.read_bytes()
            audited = hashlib.sha256(before_payload).hexdigest()
            if correction.get("audited_sha256") != audited:
                valid = False
                errors.append(f"{path}: {shard}/{issue} audited_sha256 mismatch")
                continue
            payload = target.read_bytes()
            current = hashlib.sha256(payload).hexdigest()
            if correction.get("current_sha256") != current:
                valid = False
                errors.append(f"{path}: {shard}/{issue} current_sha256 mismatch")
                continue
            try:
                projected = before_payload.decode("utf-8")
            except UnicodeDecodeError:
                valid = False
                errors.append(f"{path}: {shard}/{issue} projection path is not UTF-8")
                continue
            replacements = correction.get("replacements")
            if not isinstance(replacements, list) or not replacements:
                valid = False
                errors.append(f"{path}: {shard}/{issue} has no replacements")
                continue
            for replacement in replacements:
                if not isinstance(replacement, dict):
                    valid = False
                    break
                old = replacement.get("old")
                new = replacement.get("new")
                count = replacement.get("count")
                if not isinstance(old, str) or not isinstance(new, str) \
                        or old == new or not isinstance(count, int) or count < 1 \
                        or projected.count(old) != count:
                    valid = False
                    errors.append(f"{path}: {shard}/{issue} invalid exact replacement")
                    break
                projected = projected.replace(old, new, count)
            if valid and projected.encode() != payload:
                valid = False
                errors.append(f"{path}: {shard}/{issue} projection does not equal current file")
        if valid:
            result[key] = row
    return result, errors
