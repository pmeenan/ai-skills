#!/usr/bin/env python3
"""Append one correctly formatted, timestamped event to progress.md.

The cost report derives all wall-clock evidence (phase elapsed, per-attempt
spawn-to-collect latency) from progress.md, so spawn/collect/phase events
must follow one exact grammar. This helper is the way to emit them — it
stamps UTC time itself and validates the shape, so the orchestrator never
hand-formats an event line. Free-text notes remain ordinary lines via `note`.

Grammar appended (one line per call):
  spawned:    - <ISO8601Z> spawned <WORK_ID> attempt <N>[: <text>]
  collected:  - <ISO8601Z> collected <WORK_ID> attempt <N>: <text>
  phase:      - <ISO8601Z> Phase <label> done: <text>
  note:       - <ISO8601Z> <text>

Work IDs are opaque tokens (no whitespace) — nothing here depends on any
harness's task-identifier shape. Attempt numbers make retries distinct.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys


def fail(message: str) -> None:
    print(f"log-progress.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("event", choices=["spawned", "collected", "phase",
                                          "note"])
    parser.add_argument("args", nargs="*")
    arguments = parser.parse_args()
    review_dir = arguments.review_dir.resolve()
    progress = review_dir / "progress.md"
    if not review_dir.is_dir():
        fail(f"no review directory: {review_dir}")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event = arguments.event
    args = arguments.args
    if event in ("spawned", "collected"):
        if len(args) < 2:
            fail(f"{event} needs: <WORK_ID> <attempt> [text...]")
        work_id, attempt, *rest = args
        if re.search(r"\s", work_id) or not work_id:
            fail(f"work ID must be one non-empty token: '{work_id}'")
        if not re.fullmatch(r"[1-9]\d*", attempt):
            fail(f"attempt must be a positive integer: '{attempt}'")
        text = " ".join(rest)
        if event == "collected" and not text:
            fail("collected needs an outcome text")
        line = f"- {stamp} {event} {work_id} attempt {attempt}"
        if text:
            line += f": {text}"
    elif event == "phase":
        if len(args) < 2:
            fail("phase needs: <label> <text...>")
        label, *rest = args
        if not label or re.search(r"\s", label):
            fail(f"phase label must be one non-empty token: '{label}'")
        line = f"- {stamp} Phase {label} done: {' '.join(rest)}"
    else:
        if not args:
            fail("note needs text")
        line = f"- {stamp} {' '.join(args)}"
    with progress.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
