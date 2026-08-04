#!/usr/bin/env python3
"""Mechanically generate a discovery brief from Common Header and templates."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def fail(msg: str) -> None:
    print(f"build-discovery-brief.py: ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def extract_fenced_block(text: str) -> str:
    match = re.search(r"```text\s+(.*?)\s+```", text, re.DOTALL)
    if not match:
        fail("could not find fenced ```text block in template")
    return match.group(1).strip()


def parse_pin(pin_md: Path) -> dict[str, str]:
    if not pin_md.is_file():
        fail(f"missing pin.md at {pin_md}")
    text = pin_md.read_text(encoding="utf-8")
    cl_match = re.search(r"# CL (\d+) — patchset (\d+) pin", text)
    if not cl_match:
        fail("could not parse CL/patchset from pin.md")
    cl, ps = cl_match.group(1), cl_match.group(2)

    rev_match = re.search(r"- Revision SHA:\s*([0-9a-fA-F]+)", text)
    parent_match = re.search(r"- Parent SHA:\s*([0-9a-fA-F]+)", text)
    wt_match = re.search(r"- Worktree:\s*(\S+)", text)

    if not (rev_match and parent_match and wt_match):
        fail("could not parse SHA/worktree fields from pin.md")

    return {
        "CL": cl,
        "PS": ps,
        "sha": rev_match.group(1),
        "parent-sha": parent_match.group(1),
        "worktree": wt_match.group(1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mechanically generate a Chromium review discovery brief."
    )
    parser.add_argument("review_dir", type=Path, help="Path to review directory")
    parser.add_argument("--work-id", required=True, help="Work unit ID (e.g. CVI)")
    parser.add_argument("--attempt", type=int, default=1, help="Attempt number")
    parser.add_argument("--entry", required=True, help="Roster entry name")
    parser.add_argument(
        "--procedure",
        required=True,
        help="Procedure reference path (relative to references/ or absolute)",
    )
    parser.add_argument(
        "--pathspec", default="", help="Optional explicit pathspec for scope"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: review_dir/briefs/<work-id>.md)",
    )

    args = parser.parse_args()

    review_dir = args.review_dir.resolve()
    skill_dir = review_dir / "skill-snapshot"
    if not skill_dir.is_dir():
        fail(f"missing skill-snapshot at {skill_dir}")

    pin_info = parse_pin(review_dir / "pin.md")

    header_tmpl = skill_dir / "references/worker/templates/generated-common-header.md"
    body_tmpl = skill_dir / "references/worker/templates/subagent-brief-discovery-thread.md"

    if not header_tmpl.is_file() or not body_tmpl.is_file():
        fail("missing required brief templates in skill-snapshot")

    header_text = extract_fenced_block(header_tmpl.read_text(encoding="utf-8"))
    body_text = extract_fenced_block(body_tmpl.read_text(encoding="utf-8"))

    proc_path = args.procedure
    if not proc_path.startswith("/"):
        proc_path = str(skill_dir / "references" / proc_path)

    combined = f"{header_text}\n\n{body_text}\n"

    scope_str = args.pathspec if args.pathspec else args.entry

    replacements = {
        "⟨CL⟩": pin_info["CL"],
        "⟨PS⟩": pin_info["PS"],
        "⟨sha⟩": pin_info["sha"],
        "⟨parent-sha⟩": pin_info["parent-sha"],
        "⟨review-dir⟩": str(review_dir),
        "⟨worktree⟩": pin_info["worktree"],
        "⟨work-id⟩": args.work_id,
        "⟨attempt⟩": str(args.attempt),
        "⟨skill-dir⟩": str(skill_dir),
        "⟨roster entry⟩": args.entry,
        "CL 9999999": f"CL {pin_info['CL']}",
        "patchset 3": f"patchset {pin_info['PS']}",
        "4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9": pin_info["sha"],
        "8b1d77e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b177": pin_info["parent-sha"],
        "4f2a09c1d8e7": pin_info["sha"][:12],
        "8b1d77e6f5a4": pin_info["parent-sha"][:12],
        "/checkout/chromium/codereview/worktrees/cl-9999999-ps3": pin_info["worktree"],
        "/tmp/scratch/cl-9999999-ps3": str(review_dir),
        "EPW-code.md": f"{args.work_id}-code.md",
        "ledger/EPW.md": f"ledger/{args.work_id}.md",
        "row IDs EPW-1, EPW-2, ...": f"row IDs {args.work_id}-1, {args.work_id}-2, ...",
        "references/worker/deep-dive-recipes/recipe-error-path-walk.md": proc_path.split("skill-snapshot/")[-1] if "skill-snapshot/" in proc_path else proc_path,
        "net/streams/delay_buffer.cc and delay_buffer.h — functions\n   DelayBuffer::Push, DelayBuffer::Flush, DelayBuffer::OnTimer.": f"{scope_str} ({args.entry}).",
    }

    for k, v in replacements.items():
        combined = combined.replace(k, v)

    out_path = args.output or (review_dir / "briefs" / f"{args.work_id}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(combined, encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
