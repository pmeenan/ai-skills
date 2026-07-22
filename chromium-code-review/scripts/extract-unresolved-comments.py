#!/usr/bin/env python3
"""Normalize Gerrit /comments output into unresolved reply threads.

Usage:
  extract-unresolved-comments.py COMMENTS_JSON [-o OUTPUT_JSON]

The input must already be ordinary JSON (fetch-cl.sh strips Gerrit's XSSI
prefix). Thread state is determined only from the latest comment after reply
graph grouping; array position is deliberately ignored.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


PRESERVED_FIELDS = (
    "id",
    "in_reply_to",
    "line",
    "range",
    "side",
    "patch_set",
    "author",
    "created",
    "updated",
    "message",
    "unresolved",
)


def fail(message: str) -> "NoReturn":
    raise ValueError(message)


def comment_order(comment: dict[str, Any]) -> tuple[str, str]:
    return (str(comment.get("updated") or comment.get("created") or ""),
            str(comment.get("id") or ""))


def normalize(source: dict[str, Any]) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    malformed: list[dict[str, Any]] = []

    for path in sorted(source):
        values = source[path]
        if not isinstance(path, str) or not isinstance(values, list):
            fail("comments.json must map path strings to arrays")
        for index, raw in enumerate(values):
            if not isinstance(raw, dict):
                malformed.append({
                    "path": path,
                    "index": index,
                    "reason": "comment is not an object",
                })
                continue
            comment = dict(raw)
            comment["path"] = path
            comment_id = comment.get("id")
            if not isinstance(comment_id, str) or not comment_id:
                malformed.append({
                    "path": path,
                    "index": index,
                    "reason": "comment has no non-empty id",
                })
                continue
            if comment_id in by_id:
                malformed.append({
                    "id": comment_id,
                    "path": path,
                    "reason": "duplicate comment id",
                })
                continue
            by_id[comment_id] = comment

    root_cache: dict[str, str] = {}

    def find_root(comment_id: str) -> str:
        if comment_id in root_cache:
            return root_cache[comment_id]
        trail: list[str] = []
        positions: dict[str, int] = {}
        current = comment_id
        while True:
            if current in root_cache:
                root = root_cache[current]
                break
            if current in positions:
                cycle = trail[positions[current]:]
                root = min(cycle)
                malformed.append({
                    "ids": sorted(cycle),
                    "root_id": root,
                    "reason": "reply cycle",
                })
                break
            positions[current] = len(trail)
            trail.append(current)
            parent = by_id[current].get("in_reply_to")
            if not parent:
                root = current
                break
            if not isinstance(parent, str) or parent not in by_id:
                root = current
                malformed.append({
                    "id": current,
                    "missing_in_reply_to": parent,
                    "root_id": root,
                    "reason": "missing reply ancestor",
                })
                break
            current = parent
        for item in trail:
            root_cache[item] = root
        return root

    groups: dict[str, list[dict[str, Any]]] = {}
    for comment_id, comment in by_id.items():
        groups.setdefault(find_root(comment_id), []).append(comment)

    unresolved_threads: list[dict[str, Any]] = []
    for root_id, comments in groups.items():
        comments.sort(key=comment_order)
        latest = comments[-1]
        if latest.get("unresolved") is not True:
            continue
        normalized_comments = []
        for comment in comments:
            item = {field: comment[field] for field in PRESERVED_FIELDS
                    if field in comment}
            item["path"] = comment["path"]
            normalized_comments.append(item)
        unresolved_threads.append({
            "root_id": root_id,
            "latest_id": latest["id"],
            "path": latest["path"],
            "line": latest.get("line"),
            "range": latest.get("range"),
            "side": latest.get("side"),
            "patch_set": latest.get("patch_set"),
            "unresolved": True,
            "comments": normalized_comments,
        })

    unresolved_threads.sort(key=lambda thread: (
        str(thread.get("path") or ""),
        thread.get("line") if isinstance(thread.get("line"), int) else -1,
        str(thread["root_id"]),
    ))
    malformed.sort(key=lambda item: json.dumps(item, sort_keys=True))
    return {
        "summary": {
            "total_threads": len(groups),
            "unresolved_threads": len(unresolved_threads),
            "malformed_entries": len(malformed),
        },
        "threads": unresolved_threads,
        "malformed": malformed,
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comments_json", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    arguments = parser.parse_args()
    try:
        raw = arguments.comments_json.read_bytes()
        if raw.startswith(b")]}'"):
            fail("input still has Gerrit's XSSI prefix; run fetch-cl.sh or normalize it first")
        source = json.loads(raw)
        if not isinstance(source, dict):
            fail("comments.json must contain a JSON object")
        result = normalize(source)
        if arguments.output:
            atomic_write(arguments.output, result)
        else:
            json.dump(result, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
            sys.stdout.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"extract-unresolved-comments.py: ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
