#!/usr/bin/env python3
"""Refresh Gerrit scalars and finalize a review delivery freshness gate."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
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


def load_detail(args: argparse.Namespace, cl: str, mode: str = "current", root: Path | None = None) -> dict[str, Any]:
    if args.detail_json:
        return decode_json(args.detail_json.read_bytes(), str(args.detail_json))
    if mode == "local" and root is not None and (root / "detail.json").is_file():
        return decode_json((root / "detail.json").read_bytes(), str(root / "detail.json"))
    qualified = f"{args.gerrit_project}~{cl}"
    encoded = urllib.parse.quote(qualified, safe="")
    base = args.gerrit_base.rstrip("/")
    return fetch_detail(f"{base}/changes/{encoded}/detail?o=ALL_REVISIONS")


def load_comments(args: argparse.Namespace, cl: str, mode: str = "current") -> dict[str, Any] | None:
    if args.comments_json:
        return decode_json(args.comments_json.read_bytes(), str(args.comments_json))
    if mode != "current" or args.detail_json:
        return None
    qualified = f"{args.gerrit_project}~{cl}"
    encoded = urllib.parse.quote(qualified, safe="")
    base = args.gerrit_base.rstrip("/")
    return fetch_detail(f"{base}/changes/{encoded}/comments")


def archive_prior_bytes(root: Path, path: Path) -> None:
    if not path.is_file():
        return
    import hashlib
    payload = path.read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    destination = root / "output-history" / f"{sha}.bin"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        with destination.open("xb") as stream:
            stream.write(payload)
        destination.chmod(0o444)


def refresh_comment_threads(root: Path, live_comments: dict[str, Any]) -> str | None:
    import importlib.util
    extractor_path = Path(__file__).resolve().with_name("extract-unresolved-comments.py")
    spec = importlib.util.spec_from_file_location("extract_unresolved_comments", extractor_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {extractor_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    live_normalized = module.normalize(live_comments)
    live_by_root = {
        str(thread["root_id"]).strip(): str(thread.get("latest_id") or "").strip()
        for thread in live_normalized.get("threads", [])
        if isinstance(thread, dict)
        and thread.get("unresolved") is True
        and thread.get("root_id")
    }
    threads_path = root / "gerrit" / "unresolved-threads.json"
    existing_by_root: dict[str, str] | None = None
    if threads_path.is_file():
        existing_data = json.loads(threads_path.read_text(encoding="utf-8"))
        if isinstance(existing_data, dict) and isinstance(existing_data.get("threads"), list):
            existing_by_root = {
                str(thread["root_id"]).strip(): str(thread.get("latest_id") or "").strip()
                for thread in existing_data["threads"]
                if isinstance(thread, dict)
                and thread.get("unresolved") is True
                and thread.get("root_id")
            }
    stale_replies: list[str] = []
    gerrit_path = root / "gerrit-comments.md"
    if gerrit_path.is_file():
        gerrit_text = gerrit_path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?m)^###\s+Thread\s+([^\s—]+).*$", gerrit_text):
            root_id = match.group(1).strip().strip("`")
            next_heading = re.search(r"(?m)^##", gerrit_text[match.end():])
            end = (
                match.end() + next_heading.start()
                if next_heading is not None else len(gerrit_text)
            )
            section = gerrit_text[match.end():end]
            if root_id not in live_by_root:
                stale_replies.append(f"resolved/unknown thread {root_id}")
                continue
            latest_match = re.search(
                r"(?im)^-\s*Latest comment id:\s*(\S+)", section
            )
            if latest_match:
                cited_latest = latest_match.group(1).strip().strip("`")
                if live_by_root[root_id] and cited_latest != live_by_root[root_id]:
                    stale_replies.append(
                        f"thread {root_id} latest_id {cited_latest} != {live_by_root[root_id]}"
                    )
    threads_changed = existing_by_root is not None and existing_by_root != live_by_root
    if not threads_changed and not stale_replies:
        return None
    for target in (
        root / "comments.json",
        threads_path,
        root / "profile.json",
        root / "profile.md",
    ):
        archive_prior_bytes(root, target)
    atomic_write(
        root / "comments.json",
        json.dumps(live_comments, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    atomic_write(
        threads_path,
        json.dumps(live_normalized, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    profile_path = root / "profile.json"
    if profile_path.is_file():
        profile_cmd = [
            sys.executable,
            str(Path(__file__).resolve().with_name("profile-review.py")),
            str(root),
        ]
        try:
            existing_profile = json.loads(profile_path.read_text(encoding="utf-8"))
            budget = existing_profile.get("context_budget", {})
            tokens = budget.get("estimation", {}).get("context_window_tokens")
            if isinstance(tokens, int) and tokens > 0:
                profile_cmd.extend(["--context-window-tokens", str(tokens)])
            tier_tokens = budget.get("reported_tier_context_tokens", {})
            if isinstance(tier_tokens, dict):
                for tier, tier_val in sorted(tier_tokens.items()):
                    if isinstance(tier_val, int) and tier_val > 0:
                        profile_cmd.extend(["--tier-context-window-tokens", f"{tier}:{tier_val}"])
            subprocess.run(profile_cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if (root / "indexes").is_dir():
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve().with_name("build-review-indexes.py")),
                        str(root),
                    ],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
        except (OSError, ValueError, TypeError):
            pass
    details = []
    if threads_changed:
        details.append("unresolved Gerrit thread set or latest comment IDs changed")
    if stale_replies:
        details.append("gerrit-comments.md targets " + ", ".join(stale_replies))
    return "; ".join(details) + "; reconcile prior-feedback.md and gerrit-comments.md"


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
    cl_match = re.search(r"^# CL\s+([0-9a-zA-Z_-]+)\b", text, re.MULTILINE)
    patchset = values.get("Pinned patchset", "")
    sha = values.get("Revision SHA", "")
    if not cl_match or not patchset.isdigit() or not SHA_RE.fullmatch(sha):
        raise ValueError("pin.md lacks a CL number, pinned patchset, or full revision SHA")
    directives = (root / "directives.md").read_text(encoding="utf-8") if (root / "directives.md").is_file() else ""
    historical = bool(re.search(r"(?im)^- Mode:\s*historical patchset\b", directives))
    local = bool(
        re.search(r"(?im)^- Mode:\s*local\b", directives)
        or values.get("Mode") == "local branch"
        or values.get("Status") == "LOCAL"
        or cl_match.group(1) in {"0", "local"}
    )
    if local:
        mode = "local"
    elif historical:
        mode = "historical"
    else:
        mode = "current"
    return cl_match.group(1), patchset, sha, mode


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
    parser.add_argument("--comments-json", type=Path, help="normalized or XSSI-prefixed Gerrit /comments JSON")
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
        detail = load_detail(args, cl, mode=mode, root=root)
        live_comments = load_comments(args, cl, mode=mode)
        current_ps, current_sha, revisions = current_data(detail)
        gerrit_updated = str(detail.get("updated") or "unavailable")
        pinned_revision = revisions.get(pinned_sha)
        if not isinstance(pinned_revision, dict) or str(pinned_revision.get("_number", "")) != pinned_ps:
            raise ValueError("pinned SHA does not map to the pinned patchset in ALL_REVISIONS")
        challenge = challenge_proof(root)
        comment_staleness = (
            refresh_comment_threads(root, live_comments)
            if live_comments is not None else None
        )
        if mode == "historical":
            result = "historical pin verified"
            reason = f"pinned PS{pinned_ps}/SHA mapping remains present; current is PS{current_ps}"
        elif mode == "local":
            branch_head = None
            pin_values = fields((root / "pin.md").read_text(encoding="utf-8"))
            ref_val = pin_values.get("Ref", "")
            wt_val = pin_values.get("Worktree", "").split(" (", 1)[0]
            if ref_val.startswith("refs/heads/") and wt_val and Path(wt_val).is_dir():
                branch = ref_val.removeprefix("refs/heads/")
                try:
                    p = subprocess.run(
                        ["git", "-C", wt_val, "rev-parse", f"refs/heads/{branch}"],
                        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    )
                    branch_head = p.stdout.strip()
                except subprocess.CalledProcessError:
                    pass
            is_uncommitted = pin_values.get("Subject", "").startswith("[LOCAL UNCOMMITTED]")
            if is_uncommitted:
                parent_sha = pin_values.get("Parent SHA")
                if branch_head and parent_sha and branch_head != parent_sha:
                    result = "newer patchset"
                    reason = f"local branch has moved from parent {parent_sha[:10]} to {branch_head[:10]}; re-pin required"
                else:
                    result = "current"
                    reason = "local review pin is current"
            elif branch_head and branch_head != pinned_sha:
                result = "newer patchset"
                reason = f"local branch has moved from {pinned_sha[:10]} to {branch_head[:10]}; re-pin required"
            else:
                result = "current"
                reason = "local review pin is current"
        elif current_sha == pinned_sha:
            if comment_staleness:
                result = "stale comments"
                reason = comment_staleness
            else:
                result = "current"
                reason = "Gerrit current revision equals the pinned revision"
        elif args.accept_proven_trivial_delta and proven_trivial_delta(root, pinned_sha, current_sha):
            if comment_staleness:
                result = "stale comments"
                reason = comment_staleness
            else:
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
        archive_prior_bytes(root, root / "reconciliation.md")
        atomic_write(root / "reconciliation.md", reconciliation_update[1])
        if (root / "indexes").is_dir():
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().with_name("build-review-indexes.py")),
                    str(root),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
    print(f"{result}: {'yes' if affirmative else 'no'}")
    return 0 if affirmative else 2


if __name__ == "__main__":
    raise SystemExit(main())
