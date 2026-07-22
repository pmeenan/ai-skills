#!/usr/bin/env python3
"""Refresh Gerrit scalars and finalize a review delivery freshness gate."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


FIELD_RE = re.compile(r"^- ([^:]+):\s*(.*?)\s*$", re.MULTILINE)
SHA_RE = re.compile(r"[0-9a-fA-F]{40,64}")


def fields(text: str) -> dict[str, str]:
    return {key: value for key, value in FIELD_RE.findall(text)}


def decode_json(data: bytes, source: str) -> dict[str, Any]:
    text = data.decode("utf-8-sig")
    if text.startswith(")]}'"):
        newline = text.find("\n")
        if newline < 0:
            raise ValueError(f"{source} contains only a Gerrit XSSI prefix")
        text = text[newline + 1 :]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain a JSON object")
    return value


def fetch_detail(url: str) -> dict[str, Any]:
    error = "request did not run"
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=15) as response:
                return decode_json(response.read(), url)
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exception:
            error = str(exception)
            if attempt < 2:
                time.sleep(0.25 * (attempt + 1))
    raise ValueError(f"Gerrit detail fetch failed after 3 attempts: {error}")


def load_detail(args: argparse.Namespace, cl: str) -> dict[str, Any]:
    if args.detail_json:
        return decode_json(args.detail_json.read_bytes(), str(args.detail_json))
    qualified = f"{args.gerrit_project}~{cl}"
    encoded = urllib.parse.quote(qualified, safe="")
    base = args.gerrit_base.rstrip("/")
    return fetch_detail(f"{base}/changes/{encoded}/detail?o=ALL_REVISIONS")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def pinned_data(root: Path) -> tuple[str, str, str, str]:
    pin_path = root / "pin.md"
    text = pin_path.read_text(encoding="utf-8")
    values = fields(text)
    cl_match = re.search(r"^# CL\s+(\d+)\b", text, re.MULTILINE)
    patchset = values.get("Pinned patchset", "")
    sha = values.get("Revision SHA", "")
    if not cl_match or not patchset.isdigit() or not SHA_RE.fullmatch(sha):
        raise ValueError("pin.md lacks a CL number, pinned patchset, or full revision SHA")
    directives = (root / "directives.md").read_text(encoding="utf-8") if (root / "directives.md").is_file() else ""
    historical = bool(re.search(r"(?im)^- Mode:\s*historical patchset\b", directives))
    return cl_match.group(1), patchset, sha, "historical" if historical else "current"


def current_data(detail: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    revisions = detail.get("revisions")
    current_sha = detail.get("current_revision")
    if not isinstance(revisions, dict) or not SHA_RE.fullmatch(str(current_sha or "")):
        raise ValueError("detail has no ALL_REVISIONS map or full current_revision")
    current = revisions.get(current_sha)
    if not isinstance(current, dict) or not str(current.get("_number", "")).isdigit():
        raise ValueError("detail current_revision is absent from revisions or lacks _number")
    return str(current["_number"]), str(current_sha), revisions


def challenge_proof(root: Path) -> tuple[str, str] | None:
    draft = (root / "draft-review.md").read_text(encoding="utf-8") if (root / "draft-review.md").is_file() else ""
    draft_revision = fields(draft).get("Draft revision", "")
    pointer_text = (root / "challenge.md").read_text(encoding="utf-8") if (root / "challenge.md").is_file() else ""
    pointer = re.search(r"challenge/round-(\d+)/index\.md", pointer_text)
    if not pointer:
        return None
    index_path = root / pointer.group(0)
    if not index_path.is_file():
        return None
    index_text = index_path.read_text(encoding="utf-8")
    challenged_revision = fields(index_text).get("Draft revision", "")
    if not draft_revision or challenged_revision != draft_revision:
        return None
    if not re.search(r"(?im)^- Result:\s*(?:pass|passed|clean)\b", index_text):
        return None
    return draft_revision, pointer.group(0)


def proven_trivial_delta(root: Path, pinned_sha: str, current_sha: str) -> bool:
    path = root / "patchset-delta.md"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    draft = (root / "draft-review.md").read_text(encoding="utf-8")
    values = fields(text)
    reviewed = values.get("Reviewed pin", "")
    inspected = values.get("Inspected Gerrit current", "")
    return bool(
        pinned_sha in reviewed
        and current_sha in inspected
        and current_sha in draft
        and re.match(r"(?i)^trivial\b", values.get("Classification", ""))
        and re.match(r"(?i)^every\b|^yes\b|^all\b", values.get("Cited-line revalidation", ""))
        and re.match(r"(?i)^every\b|^yes\b|^all\b", values.get("Conclusion revalidation", ""))
    )


def freshness_replacement(root: Path, result: str) -> tuple[str, str] | None:
    path = root / "reconciliation.md"
    if not path.is_file():
        return None
    original = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^2\.\s+(?:\*\*)?Freshness:(?:\*\*)?\s*.*$", re.MULTILINE)
    matches = list(pattern.finditer(original))
    if len(matches) != 1:
        return None
    replacement = f"2. **Freshness:** yes — {result}; delivery-gate.md"
    return original, pattern.sub(replacement, original, count=1)


def gate_text(
    checked_at: str, challenge_revision: str, pinned_ps: str, pinned_sha: str,
    current_ps: str, current_sha: str, gerrit_updated: str, result: str, gate_line: str,
) -> str:
    return (
        "# Delivery freshness\n"
        f"- Checked after challenge revision: {challenge_revision}\n"
        f"- Checked at: {checked_at}\n"
        f"- Pinned: PS{pinned_ps} {pinned_sha}\n"
        f"- Gerrit current: PS{current_ps} {current_sha}\n"
        f"- Gerrit updated: {gerrit_updated}\n"
        f"- Result: {result}\n"
        f"- Gate line: {gate_line}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--detail-json", type=Path, help="normalized or XSSI-prefixed Gerrit detail JSON")
    parser.add_argument("--gerrit-base", default="https://chromium-review.googlesource.com")
    parser.add_argument("--gerrit-project", default="chromium/src")
    parser.add_argument("--checked-at", help="RFC3339 timestamp; defaults to current UTC")
    parser.add_argument(
        "--accept-proven-trivial-delta", action="store_true",
        help="accept, but never infer, an existing fully revalidated trivial-delta artifact",
    )
    args = parser.parse_args()
    root = args.review_dir.resolve()
    checked_at = args.checked_at or dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    pinned_ps = "unavailable"
    pinned_sha = "unavailable"
    current_ps = "unavailable"
    current_sha = "unavailable"
    gerrit_updated = "unavailable"
    result = "fetch failed"
    reason = "freshness refresh failed"
    challenge = None
    reconciliation_update = None
    try:
        cl, pinned_ps, pinned_sha, mode = pinned_data(root)
        detail = load_detail(args, cl)
        current_ps, current_sha, revisions = current_data(detail)
        gerrit_updated = str(detail.get("updated") or "unavailable")
        pinned_revision = revisions.get(pinned_sha)
        if not isinstance(pinned_revision, dict) or str(pinned_revision.get("_number", "")) != pinned_ps:
            raise ValueError("pinned SHA does not map to the pinned patchset in ALL_REVISIONS")
        challenge = challenge_proof(root)
        if mode == "historical":
            result = "historical pin verified"
            reason = f"pinned PS{pinned_ps}/SHA mapping remains present; current is PS{current_ps}"
        elif current_sha == pinned_sha:
            result = "current"
            reason = "Gerrit current revision equals the pinned revision"
        elif args.accept_proven_trivial_delta and proven_trivial_delta(root, pinned_sha, current_sha):
            result = "trivial delta verified"
            reason = "accepted existing patchset-delta.md revalidation for the unchanged Gerrit-current SHA"
        else:
            result = "newer patchset"
            reason = "Gerrit current differs from the pin; delta classification is required"
        if result in {"current", "historical pin verified", "trivial delta verified"} and challenge:
            reconciliation_update = freshness_replacement(root, result)
            if reconciliation_update is None:
                reason = "reconciliation.md lacks exactly one mechanically replaceable Freshness line"
    except (OSError, ValueError, json.JSONDecodeError) as error:
        reason = str(error)

    affirmative = (
        result in {"current", "historical pin verified", "trivial delta verified"}
        and challenge is not None
        and reconciliation_update is not None
    )
    challenge_revision = challenge[0] if challenge else "none"
    if affirmative:
        gate_line = f"yes — {reason}; draft revision {challenge[0]} passed {challenge[1]}"
    else:
        gate_line = f"no — {reason}"
    atomic_write(
        root / "delivery-gate.md",
        gate_text(
            checked_at, challenge_revision, pinned_ps, pinned_sha,
            current_ps, current_sha, gerrit_updated, result, gate_line,
        ),
    )
    if affirmative and reconciliation_update:
        atomic_write(root / "reconciliation.md", reconciliation_update[1])
    print(f"{result}: {'yes' if affirmative else 'no'}")
    return 0 if affirmative else 2


if __name__ == "__main__":
    raise SystemExit(main())
