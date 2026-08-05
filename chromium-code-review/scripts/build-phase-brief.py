#!/usr/bin/env python3
"""Mechanically generate a phase brief from Common Header and templates."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def fail(msg: str) -> None:
    print(f"build-phase-brief.py: ERROR: {msg}", file=sys.stderr)
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
        description="Mechanically generate a Chromium review phase brief."
    )
    parser.add_argument("review_dir", type=Path, help="Path to review directory")
    parser.add_argument("work_id", type=str, help="Work unit ID (e.g. CVI, PLAN)")
    parser.add_argument("brief_name", type=str, help="Heading or name of the brief in phase-briefs.md")
    parser.add_argument("--attempt", type=int, default=1, help="Attempt number")
    parser.add_argument("--shard", default="", help="Optional shard index/name")
    parser.add_argument("--thread", default="", help="Optional thread name")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    review_dir = args.review_dir.resolve()
    skill_dir = review_dir / "skill-snapshot"
    if not skill_dir.is_dir():
        fail(f"missing skill-snapshot at {skill_dir}")

    pin_info = parse_pin(review_dir / "pin.md")

    header_tmpl = skill_dir / "references/worker/phase-briefs/common-header.md"
    if not header_tmpl.is_file():
        header_tmpl = skill_dir / "references/worker/templates/generated-common-header.md"
    if not header_tmpl.is_file():
        fail(f"missing required common header template in {skill_dir}")

    header_text = extract_fenced_block(header_tmpl.read_text(encoding="utf-8"))

    phase_briefs_path = skill_dir / "references/phase-briefs.md"
    if not phase_briefs_path.is_file():
        fail(f"missing phase-briefs.md at {phase_briefs_path}")

    phase_briefs_text = phase_briefs_path.read_text(encoding="utf-8")
    lines = phase_briefs_text.split('\n')
    start = -1
    end = -1
    for i, line in enumerate(lines):
        if line.startswith("## ") and args.brief_name in line:
            start = i
        if start != -1 and line == "```":
            end = i
            break

    if start == -1 or end == -1:
        fail(f"Could not find template for {args.brief_name} in phase-briefs.md")

    template_block = "\n".join(lines[start:end+1])
    body_text = extract_fenced_block(template_block)

    combined = f"{header_text}\n\n{body_text}\n"

    replacements = {
        "⟨CL⟩": pin_info["CL"],
        "⟨PS⟩": pin_info["PS"],
        "⟨sha⟩": pin_info["sha"],
        "⟨parent-sha⟩": pin_info["parent-sha"],
        "⟨review-dir⟩": str(review_dir),
        "⟨skill-dir⟩": str(skill_dir),
        "⟨worktree⟩": pin_info["worktree"],
        "⟨work-id⟩": args.work_id,
        "⟨attempt⟩": str(args.attempt),
        "CL 9999999": f"CL {pin_info['CL']}",
        "patchset 3": f"patchset {pin_info['PS']}",
        "/tmp/scratch/cl-9999999-ps3": str(review_dir),
        "/checkout/chromium/codereview/worktrees/cl-9999999-ps3": pin_info["worktree"],
    }
    if args.shard:
        replacements["⟨SHARD⟩"] = args.shard
        replacements["⟨shard⟩"] = args.shard
    if args.thread:
        replacements["⟨THREAD⟩"] = args.thread
        replacements["⟨thread⟩"] = args.thread

    for k, v in replacements.items():
        combined = combined.replace(k, v)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(combined, encoding="utf-8")
        print(args.output)
    else:
        print(combined, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
