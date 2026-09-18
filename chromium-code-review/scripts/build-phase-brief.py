#!/usr/bin/env python3
"""Mechanically generate a phase brief from Common Header and templates."""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

from brief_inputs import named_brief_inputs


# Every placeholder is a substitution this generator owes the brief, except
# these four: they are instruction templates the Common Header addresses to
# the worker at execution time, and no value exists for them here. Leaving
# them unsubstituted is correct; leaving any other one is the defect the
# placeholder gate below exists to catch.
RUNTIME_PLACEHOLDERS = frozenset({
    "exact path",
    "worktree-or-current-directory",
    "command...",
    "explicit list of unprocessed scope",
})

# Both spellings of the changed-file pathspec placeholder that appear in
# phase-briefs.md. Keep them in sync with that file.
PATHSPEC_PLACEHOLDERS = (
    "\u27e8explicit path list including both sides of renames/deletions\u27e9",
    "\u27e8pathspec\u27e9",
)

PLACEHOLDER_RE = re.compile("\u27e8(.*?)\u27e9", re.DOTALL)

# Mirrors seal-work-unit.py's TIERS so a derived or supplied tier cannot
# produce a seal command that seal-work-unit.py rejects.
TIERS = ("frontier", "inherit", "mechanical", "standard")

ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])(/[A-Za-z0-9_.+@{}%=/:-]+)")


def fail(msg: str) -> None:
    print(f"build-phase-brief.py: ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def note(msg: str) -> None:
    print(f"build-phase-brief.py: NOTE: {msg}", file=sys.stderr)


def extract_fenced_block(text: str) -> str:
    match = re.search(r"```text\s+(.*?)\s+```", text, re.DOTALL)
    if not match:
        fail("could not find fenced ```text block in template")
    return match.group(1).strip()


def parse_pin(pin_md: Path) -> dict[str, str]:
    if not pin_md.is_file():
        fail(f"missing pin.md at {pin_md}")
    text = pin_md.read_text(encoding="utf-8")
    cl_match = re.search(r"# CL ([0-9a-zA-Z_-]+) — patchset (\d+) pin", text)
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


def collapse(text: str) -> str:
    """Render a possibly multi-line placeholder body on one diagnostic line."""
    return " ".join(text.split())


def unsubstituted_placeholders(text: str) -> list[str]:
    """Return each distinct placeholder body still present, in first-seen order."""
    seen: list[str] = []
    for body in PLACEHOLDER_RE.findall(text):
        if body in RUNTIME_PLACEHOLDERS or body in seen:
            continue
        seen.append(body)
    return seen


def substitution_flag(body: str) -> str:
    """Name the exact flag that fills this placeholder."""
    if f"\u27e8{body}\u27e9" in PATHSPEC_PLACEHOLDERS:
        return "--pathspec 'path/one.cc path/one.h'"
    return f"--set {shlex.quote(collapse(body) + '=VALUE')}"


def brief_tier(template_block: str) -> str:
    """Read the `Tier:` line the phase-briefs.md section states, if any."""
    match = re.search(
        r"(?im)^Tier:\s*`?([A-Za-z-]+)`?", template_block
    )
    return match.group(1) if match else ""


def brief_artifact(brief_text: str) -> str:
    """Read the absolute deliverable path the brief's Deliverable line names."""
    for line in brief_text.splitlines():
        if not re.match(r"(?i)^Deliverables?:", line):
            continue
        for quoted in re.findall(r"`(/[^`]+)`", line):
            if not quoted.endswith("/"):
                return quoted
        bare = re.sub(r"`[^`]*`", " ", line)
        for match in ABSOLUTE_PATH_RE.finditer(bare):
            raw = match.group(1)
            if raw.endswith("/"):
                continue
            return raw.rstrip(".,;:)]}")
    return ""


def brief_phase(heading: str) -> str:
    """Read the phase number the section heading states, e.g. `(Phase 4.5,`."""
    match = re.search(r"(?i)\(\s*Phase\s+([0-9]+(?:\.[0-9]+)?)", heading)
    return match.group(1) if match else ""


def seal_command(
    *,
    skill_dir: Path,
    review_dir: Path,
    brief: Path,
    phase: str,
    work_id: str,
    attempt: int,
    tier: str,
    artifact: str,
) -> str:
    """Spell out the seal-work-unit.py call this brief requires.

    The `--input` list is whatever `validate-review-dir.py` will extract from
    the brief, so a caller who runs this command verbatim cannot hit the
    "names input ... but input-manifest.tsv omits it" gate.
    """
    parts = [
        "python3",
        str(skill_dir / "scripts" / "seal-work-unit.py"),
        str(review_dir),
        "--phase", phase,
        "--work-id", work_id,
        "--attempt", str(attempt),
        "--tier", tier,
        "--brief", str(brief),
        "--artifact", artifact,
    ]
    for path in sorted(named_brief_inputs(brief)):
        role = "reference" if skill_dir in path.parents else "control"
        parts.extend(["--input", f"{role}={path}"])
    return " ".join(shlex.quote(part) for part in parts)


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
    parser.add_argument(
        "--pathspec",
        default="",
        help="Space-separated changed-file pathspec, including both sides of "
             "renames/deletions; fills the changed-file pathspec placeholders",
    )
    parser.add_argument(
        "--set",
        dest="substitutions",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Substitute \u27e8KEY\u27e9 with VALUE; repeatable",
    )
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Emit the brief even if placeholders remain unsubstituted",
    )
    parser.add_argument(
        "--phase",
        default="",
        help="Phase for the emitted seal command (default: the phase named in "
             "the brief's heading)",
    )
    parser.add_argument(
        "--tier",
        default="",
        metavar="|".join(TIERS),
        help="Tier for the emitted seal command (default: the brief's Tier: line)",
    )
    parser.add_argument(
        "--artifact",
        default="",
        help="Artifact for the emitted seal command (default: the absolute "
             "path on the brief's Deliverable: line)",
    )
    parser.add_argument(
        "--emit-seal-command",
        dest="emit_seal_command",
        action="store_true",
        default=True,
        help="Print the exact seal-work-unit.py command for the brief (default)",
    )
    parser.add_argument(
        "--no-emit-seal-command",
        dest="emit_seal_command",
        action="store_false",
        help="Suppress the seal-work-unit.py command",
    )

    args = parser.parse_args()

    if args.tier and args.tier not in TIERS:
        fail(f"--tier must be one of {', '.join(TIERS)}, got {args.tier!r}")

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
        available = [line[3:].strip() for line in lines if line.startswith("## ")]
        fail(
            f"Could not find template for {args.brief_name} in "
            f"phase-briefs.md; pass a name that is a substring of exactly one "
            "of these headings:\n  " + "\n  ".join(available)
        )

    template_block = "\n".join(lines[start:end+1])
    body_text = extract_fenced_block(template_block)

    combined = f"{header_text}\n\n{body_text}\n"

    replacements = {
        "\u27e8CL\u27e9": pin_info["CL"],
        "\u27e8PS\u27e9": pin_info["PS"],
        "\u27e8sha\u27e9": pin_info["sha"],
        "\u27e8parent-sha\u27e9": pin_info["parent-sha"],
        "\u27e8review-dir\u27e9": str(review_dir),
        "\u27e8skill-dir\u27e9": str(skill_dir),
        "\u27e8worktree\u27e9": pin_info["worktree"],
        "\u27e8work-id\u27e9": args.work_id,
        "\u27e8attempt\u27e9": str(args.attempt),
        "CL 9999999": f"CL {pin_info['CL']}",
        "patchset 3": f"patchset {pin_info['PS']}",
        "/tmp/scratch/cl-9999999-ps3": str(review_dir),
        "/checkout/chromium/codereview/worktrees/cl-9999999-ps3": pin_info["worktree"],
    }
    if args.shard:
        replacements["\u27e8SHARD\u27e9"] = args.shard
        replacements["\u27e8shard\u27e9"] = args.shard
    if args.thread:
        replacements["\u27e8THREAD\u27e9"] = args.thread
        replacements["\u27e8thread\u27e9"] = args.thread
    if args.pathspec:
        for placeholder in PATHSPEC_PLACEHOLDERS:
            replacements[placeholder] = args.pathspec
    for item in args.substitutions:
        key, separator, value = item.partition("=")
        if not separator or not key:
            fail(f"--set must be KEY=VALUE, got {item!r}")
        replacements[f"\u27e8{key}\u27e9"] = value

    for k, v in replacements.items():
        combined = combined.replace(k, v)

    # A brief that reaches a worker with a placeholder in it is hand-edited
    # after sealing, and a hand-edited sealed brief is what produces
    # "input-manifest.tsv byte count mismatch". Refuse instead.
    remaining = unsubstituted_placeholders(combined)
    if remaining and not args.allow_placeholders:
        detail = "\n".join(
            f"  \u27e8{collapse(body)}\u27e9 — fill with {substitution_flag(body)}"
            for body in remaining
        )
        fail(
            f"{len(remaining)} placeholder(s) are still unsubstituted; "
            "substitute each one, or pass --allow-placeholders to emit the "
            "brief anyway:\n" + detail
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(combined, encoding="utf-8")
        print(args.output)
    else:
        print(combined, end="")

    if not args.emit_seal_command:
        return 0
    if not args.output:
        note(
            "no seal command emitted: seal-work-unit.py needs the brief on "
            "disk; rerun with --output <brief path>"
        )
        return 0

    heading = lines[start]
    phase = args.phase or brief_phase(heading)
    derived_tier = brief_tier(template_block)
    tier = args.tier or derived_tier
    derived_artifact = brief_artifact(combined)
    artifact = args.artifact or derived_artifact
    missing = []
    if not phase:
        missing.append(f"--phase (heading {heading.strip()!r} names no phase)")
    if not tier:
        missing.append("--tier (the brief states no Tier: line)")
    if not artifact:
        missing.append("--artifact (the brief states no Deliverable: path)")
    if tier and tier not in TIERS:
        missing.append(
            f"--tier (the brief's Tier: line says {tier!r}, which is not one "
            f"of {', '.join(TIERS)})"
        )
    if missing:
        note(
            "no seal command emitted; rerun supplying "
            + "; ".join(missing)
        )
        return 0

    sources = (
        f"phase from {'--phase' if args.phase else 'the brief heading'}, "
        f"tier from {'--tier' if args.tier else 'the brief Tier: line'}, "
        f"artifact from "
        f"{'--artifact' if args.artifact else 'the brief Deliverable: line'}"
    )
    print(f"# seal command ({sources}):")
    print(seal_command(
        skill_dir=skill_dir,
        review_dir=review_dir,
        brief=args.output.resolve(),
        phase=phase,
        work_id=args.work_id,
        attempt=args.attempt,
        tier=tier,
        artifact=artifact,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
