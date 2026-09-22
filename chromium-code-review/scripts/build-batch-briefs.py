#!/usr/bin/env python3
"""Deterministically build Phase 5 (V*) and Phase 5.5 (RC*) batch briefs and packets.

Given a completed `verification/batches.md` (Phase 5) or `root-cause/batches.md`
(Phase 5.5), this helper deterministically renders:
  - Phase 5 (`--phase verification`):
    - `packets/V<batch>.spec.tsv` (if not already present)
    - `packets/V<batch>-code.md` (via `build-scope-packets.py`)
    - `briefs/V<batch>.md` (with `Generated Common Header` and embedded candidate rows)
    - Exact `seal-work-unit.py` commands (or executes them when `--seal` is passed)
  - Phase 5.5 (`--phase root-cause`):
    - `briefs/RC<batch>.md` (with `Generated Common Header` and embedded candidate/verdict rows)
    - Exact `seal-work-unit.py` commands (or executes them when `--seal` is passed)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from brief_inputs import named_brief_inputs  # noqa: E402
from artifact_tables import effective_tables  # noqa: E402


def fail(message: str) -> None:
    print(f"build-batch-briefs.py: ERROR: {message}", file=sys.stderr)
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
    cl_match = re.search(r"# CL ([0-9a-zA-Z_-]+) — patchset (\d+) pin", text)
    if cl_match:
        cl, ps = cl_match.group(1), cl_match.group(2)
    else:
        cl, ps = "local", "1"
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


def batch_rows(text: str, phase: str) -> list[dict[str, str]]:
    """Read the normative Batches table, with legacy generator aliases."""
    parsed, errors = effective_tables(text, f"{phase}/batches.md")
    if errors:
        fail("; ".join(errors))
    alias = "Skeptic batches" if phase == "verification" else "Scheduled root-cause batches"
    tables = [(header, rows) for heading, header, rows in parsed
              if heading.lower() in {"batches", alias.lower()}]
    if len(tables) != 1:
        fail(f"{phase}/batches.md must contain exactly one Batches table; "
             "an empty fast path requires separate index validation and has no briefs to render")
    header, rows = tables[0]
    required = ({"batch", "brief", "candidates", "verdict file"} if phase == "verification"
                else {"batch", "brief", "root families / scopes", "output", "bounded input"})
    # Legacy root-cause plans used items for the scope column.
    if phase == "root-cause" and "items" in header:
        required = {"batch", "items"}
    if not required.issubset(header):
        fail(f"{phase}/batches.md has malformed batch columns; expected " + ", ".join(sorted(required)))
    if not rows:
        fail(f"{phase}/batches.md has zero batch rows; no briefs rendered")
    seen: set[str] = set()
    prefix = "V" if phase == "verification" else "RC"
    for row in rows:
        work_id = row.get("batch", "")
        if not re.fullmatch(rf"{prefix}\d+", work_id) or work_id in seen:
            fail(f"invalid or duplicate {phase} batch ID {work_id!r}")
        seen.add(work_id)
        scope = row.get("candidates", "") if phase == "verification" else row.get("root families / scopes", row.get("items", ""))
        if not scope or scope in {"-", "—"}:
            fail(f"{work_id} has empty batch membership")
        for field, expected in (("brief", f"briefs/{work_id}.md"),
                                ("verdict file" if phase == "verification" else "output", f"{phase}/{work_id}.md")):
            if field in row and row[field] != expected:
                fail(f"{work_id} {field} must be {expected}")
    return rows


def markdown_row(values: list[str]) -> str:
    return "| " + " | ".join(value.replace("|", r"\|") for value in values) + " |"


def load_candidate_rows(review_dir: Path) -> dict[str, tuple[Path, str, str]]:
    """Return effective canonical candidates, never descriptors with matching IDs."""
    result: dict[str, tuple[Path, str, str]] = {}
    sources = sorted((review_dir / "ledger").glob("**/*.md"))
    if (review_dir / "collection.md").is_file():
        sources.append(review_dir / "collection.md")
    for path in sources:
        parsed, errors = effective_tables(path.read_text(encoding="utf-8"), str(path))
        if errors:
            fail("; ".join(errors))
        for heading, header, rows in parsed:
            if heading != "Candidate rows" and path.name != "collection.md":
                continue
            if not {"id", "claim", "location", "evidence / hypothesis", "status"}.issubset(header):
                continue
            table_header = markdown_row(header) + "\n" + markdown_row(["---"] * len(header))
            for row in rows:
                identifier = row["id"]
                if identifier in result:
                    fail(f"duplicate canonical candidate {identifier}")
                result[identifier] = (path.resolve(), table_header, markdown_row([row.get(key, "") for key in header]))
    return result


def load_verdict_rows(review_dir: Path) -> dict[str, tuple[Path, str, str]]:
    """Return verdict_id or candidate_id -> (source_path, table_header_lines, row_line)."""
    result: dict[str, tuple[Path, str, str]] = {}
    ver_dir = review_dir / "verification"
    if not ver_dir.is_dir():
        return result
    for path in sorted(ver_dir.glob("V*.md")):
        if path.name == "VTER.md":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        header_line = ""
        sep_line = ""
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and cells[0].lower() == "id":
                header_line = stripped
                continue
            if all(re.fullmatch(r"[-: ]+", c) for c in cells if c):
                sep_line = stripped
                continue
            if len(cells) >= 2 and re.fullmatch(r"V\d+-\d+", cells[0]):
                result[cells[0]] = (path.resolve(), f"{header_line}\n{sep_line}", stripped)
                result[cells[1]] = (path.resolve(), f"{header_line}\n{sep_line}", stripped)
    return result


def merge_support_context(review_dir: Path, assigned: list[str],
                          candidates: dict[str, tuple[Path, str, str]] | None = None) -> str:
    """Bounded evidence for proposed aliases; never expands assigned RC work."""
    batch_path = review_dir / "verification" / "batches.md"
    if not batch_path.is_file():
        return ""
    tables, errors = effective_tables(batch_path.read_text(encoding="utf-8"), str(batch_path))
    if errors:
        fail("; ".join(errors))
    proposals: dict[str, tuple[str, str]] = {}
    for heading, header, rows in tables:
        if not heading.startswith("Merge proposals") or not {"row", "proposal"}.issubset(header):
            continue
        for row in rows:
            match = re.match(r"merge-into\s+((?:R\d+-RC\d+-\d+|[A-Z][A-Z0-9]*-\d+))\b", row["proposal"])
            if not match or row["row"] in proposals:
                fail(f"malformed/duplicate merge proposal {row['row']}")
            proposals[row["row"]] = (match.group(1), row["proposal"])
    aliases = sorted(set(assigned) & set(proposals))
    if not aliases:
        return ""
    candidates = candidates if candidates is not None else load_candidate_rows(review_dir)
    chains: dict[str, list[str]] = {}
    targets: set[str] = set()
    for alias in aliases:
        chain = [alias]
        current = alias
        while current in proposals:
            current = proposals[current][0]
            if current in chain:
                fail(f"provisional merge cycle for {alias}: " + " -> ".join(chain + [current]))
            chain.append(current)
        for member in chain:
            if member not in candidates:
                fail(f"provisional merge {alias} references missing canonical candidate {member}")
        chains[alias] = chain
        targets.add(current)
    cache: dict[Path, list] = {}
    def parsed(path: Path):
        if path not in cache:
            value, errors = effective_tables(path.read_text(encoding="utf-8"), str(path))
            if errors:
                fail("; ".join(errors))
            cache[path] = value
        return cache[path]
    def section(path: Path, heading: str, candidate: str, required: bool = True) -> str:
        blocks = []
        count = 0
        for name, header, rows in parsed(path):
            if name != heading:
                continue
            selected = [row for row in rows if row.get("candidate") == candidate]
            if selected:
                count += len(selected)
                blocks.append(markdown_row(header) + "\n" + markdown_row(["---"] * len(header)) + "\n"
                              + "\n".join(markdown_row([row.get(key, "") for key in header]) for row in selected))
        if required and not count:
            fail(f"merge support for {candidate} lacks {heading} in {path}")
        if heading in {"Candidate descriptors", "Verified affinity"} and count > 1:
            fail(f"merge support for {candidate} has ambiguous {heading}")
        return "\n\n".join(blocks)
    verdicts: dict[str, list[tuple[Path, list[str], dict[str, str]]]] = {target: [] for target in targets}
    for path in sorted((review_dir / "verification").glob("V*.md")):
        if path.name == "VTER.md":
            continue
        for _, header, rows in parsed(path):
            if not {"id", "candidate", "verdict"}.issubset(header):
                continue
            for row in rows:
                if row.get("candidate") in targets:
                    verdicts[row["candidate"]].append((path, header, row))
    blocks = ["# Provisional merge comparison context", "",
              "Supporting context only; assigned work remains the original RC batch scope. "
              "These are unaccepted merge proposals. A target's verdict (including REFUTED) "
              "does not establish equivalence or supply a verdict for its alias. Compare "
              "trigger, invariant, ownership, and outcome independently; preserve differences.", ""]
    sources = {batch_path}
    included: set[str] = set()
    for alias, chain in chains.items():
        blocks += [f"## Proposed chain for {alias}", " -> ".join(chain), ""]
        for member in chain[:-1]:
            blocks += [proposals[member][1], ""]
        for member in chain:
            if member in included:
                continue
            included.add(member)
            source, header, row = candidates[member]
            sources.add(source)
            blocks += [f"### Candidate {member} (comparison context)", f"Source: {source}", header, row, "",
                       "### Candidate descriptors", section(source, "Candidate descriptors", member), ""]
    for target in sorted(targets):
        matches = verdicts[target]
        if len(matches) != 1:
            fail(f"merge target {target} requires exactly one survivor verdict; found {len(matches)}")
        source, header, row = matches[0]
        if row["verdict"] not in {"CONFIRMED", "REFUTED", "UNPROVEN"}:
            fail(f"merge target {target} has invalid survivor verdict")
        sources.add(source)
        blocks += [f"## Exact survivor evidence for {target}", f"Source: {source}",
                   markdown_row(header), markdown_row(["---"] * len(header)),
                   markdown_row([row.get(key, "") for key in header]), "",
                   "### Trace closure", section(source, "Trace closure", target), "",
                   "### Verified affinity", section(source, "Verified affinity", target), ""]
    blocks += ["## Source fingerprints", ""]
    for source in sorted(sources):
        blocks.append(f"- {source}: sha256={hashlib.sha256(source.read_bytes()).hexdigest()}")
    content = "\n".join(blocks) + "\n"
    profile = json.loads((review_dir / "profile.json").read_text(encoding="utf-8"))
    budgets = profile.get("budgets", {})
    limits = [budgets.get("candidate_packet_budget_bytes"), budgets.get("worker_input_budget_bytes")]
    if any(not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0 for limit in limits):
        fail("merge comparison context requires positive candidate-packet and worker-input budgets")
    if len(content.encode("utf-8")) > min(limits):
        fail("merge comparison context exceeds packet budget; split the RC batch or extract smaller complete comparison units; never truncate")
    return content


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
    extra_roles: dict[Path, str] | None = None,
) -> list[str]:
    cmd = [
        sys.executable,
        str(skill_dir / "scripts" / "seal-work-unit.py"),
        str(review_dir),
        "--phase",
        phase,
        "--work-id",
        work_id,
        "--attempt",
        str(attempt),
        "--tier",
        tier,
        "--brief",
        str(brief),
        "--artifact",
        artifact,
    ]
    role_map = extra_roles or {}
    for path in sorted(named_brief_inputs(brief)):
        resolved = path.resolve()
        if resolved in role_map:
            role = role_map[resolved]
        elif skill_dir in resolved.parents:
            role = "reference"
        elif resolved.parent == (review_dir / "packets"):
            role = "assigned"
        else:
            role = "control"
        cmd.extend(["--input", f"{role}={resolved}"])
    return cmd


def build_verification(review_dir: Path, skill_dir: Path, pin_info: dict[str, str], attempt: int, do_seal: bool) -> None:
    batches_md = review_dir / "verification" / "batches.md"
    if not batches_md.is_file():
        fail(f"missing {batches_md}")
    rows = batch_rows(batches_md.read_text(encoding="utf-8"), "verification")

    cand_map = load_candidate_rows(review_dir)
    profile = json.loads((review_dir / "profile.json").read_text(encoding="utf-8"))
    all_files = {str(item.get("path", "")): str(item.get("status", "M")) for item in profile.get("files", [])}

    header_tmpl = skill_dir / "references/worker/templates/generated-common-header.md"
    header_text = extract_fenced_block(header_tmpl.read_text(encoding="utf-8"))
    scope_packet_script = skill_dir / "scripts" / "build-scope-packets.py"

    for row in rows:
        work_id = row.get("batch", "").strip()
        batch_num = work_id[1:]
        cand_ids = [c.strip() for c in re.split(r"[,\s]+", row.get("candidates", "")) if c.strip()]
        unknown = set(cand_ids) - set(cand_map)
        if unknown:
            fail(f"{work_id} references unknown candidate(s): " + ", ".join(sorted(unknown)))
        spec_path = review_dir / "packets" / f"{work_id}.spec.tsv"
        code_packet_path = review_dir / "packets" / f"{work_id}-code.md"
        brief_path = review_dir / "briefs" / f"{work_id}.md"

        cited_files: list[str] = []
        embedded_rows: list[str] = []
        source_ledgers: set[Path] = set()
        header_printed = False
        for cid in cand_ids:
            if cid in cand_map:
                src_path, hdr, rline = cand_map[cid]
                source_ledgers.add(src_path)
                if not header_printed:
                    embedded_rows.append(hdr)
                    header_printed = True
                embedded_rows.append(rline)
                for fpath in all_files:
                    if fpath in rline and fpath not in cited_files:
                        cited_files.append(fpath)
        if not cited_files:
            cited_files = sorted(all_files.keys())

        if not spec_path.is_file():
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_lines = ["kind\tpath\told_range\tnew_range\tnote"]
            for fpath in cited_files:
                status = all_files.get(fpath, "M")
                spec_lines.append(f"diff\t{fpath}\t-\t-\t{status} full file diff ({work_id})")
            spec_path.write_text("\n".join(spec_lines) + "\n", encoding="utf-8")

        res = subprocess.run(
            [
                sys.executable,
                str(scope_packet_script),
                str(review_dir),
                work_id,
                "--spec",
                str(spec_path),
                "--worktree",
                pin_info["worktree"],
                "--parent",
                pin_info["parent-sha"],
                "--revision",
                pin_info["sha"],
                "--output",
                str(code_packet_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            fail(f"build-scope-packets.py failed for {work_id}: {res.stderr.strip()}")

        hdr_filled = header_text
        for k, v in {
            "⟨CL⟩": pin_info["CL"],
            "⟨PS⟩": pin_info["PS"],
            "⟨sha⟩": pin_info["sha"],
            "⟨parent-sha⟩": pin_info["parent-sha"],
            "⟨review-dir⟩": str(review_dir),
            "⟨worktree⟩": pin_info["worktree"],
            "⟨work-id⟩": work_id,
            "⟨attempt⟩": str(attempt),
            "⟨skill-dir⟩": str(skill_dir),
        }.items():
            hdr_filled = hdr_filled.replace(k, v)

        ledger_inputs = ", ".join(str(p) for p in sorted(source_ledgers))
        body = (
            f"Scope: verify batch {work_id} ONLY — candidate rows {', '.join(cand_ids)}.\n\n"
            f"Inputs: {code_packet_path}, {review_dir / 'callers/index.tsv'}, "
            f"{review_dir / 'callers/directory-docs.md'}, and source candidate ledgers {ledger_inputs}.\n\n"
            f"Embedded candidate rows for {work_id}:\n\n"
            + "\n".join(embedded_rows)
            + "\n\nProcedure:\n"
            f"1. Read {skill_dir / 'references/worker/verification-and-fixes/phase-5-adversarial-verification-protocol.md'}, "
            f"{skill_dir / 'references/worker/verification-and-fixes/existence-verification-and-style-authority.md'}, and "
            f"{skill_dir / 'references/worker/synthesis-and-output/severity-calibration.md'}.\n"
            f"2. Verify each candidate in {', '.join(cand_ids)} against the pinned worktree and emit one verdict row ({work_id}-1, {work_id}-2, ...) "
            f"plus `## Trace closure` and `## Verified affinity` in the exact shape from "
            f"{skill_dir / 'references/worker/templates/verification-batches-and-skeptic-verdict-rows.md'}.\n\n"
            f"Deliverable: {review_dir / 'verification' / f'{work_id}.md'}.\n"
        )
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(f"{hdr_filled}\n\n{body}", encoding="utf-8")

        extra_roles = {p: "candidate-packet" for p in source_ledgers}
        extra_roles[code_packet_path.resolve()] = "assigned"
        cmd = seal_command(
            skill_dir=skill_dir,
            review_dir=review_dir,
            brief=brief_path,
            phase="5",
            work_id=work_id,
            attempt=attempt,
            tier="frontier",
            artifact=f"verification/{work_id}.md",
            extra_roles=extra_roles,
        )
        print(" ".join(shlex.quote(part) for part in cmd))
        if do_seal:
            seal_res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if seal_res.returncode != 0:
                fail(f"seal-work-unit.py failed for {work_id}: {seal_res.stderr.strip()}")


def build_root_cause(review_dir: Path, skill_dir: Path, pin_info: dict[str, str], attempt: int, round_num: int, do_seal: bool) -> None:
    batches_md = review_dir / "root-cause" / "batches.md"
    if not batches_md.is_file():
        fail(f"missing {batches_md}")
    rows = batch_rows(batches_md.read_text(encoding="utf-8"), "root-cause")

    cand_map = load_candidate_rows(review_dir)
    verd_map = load_verdict_rows(review_dir)

    header_tmpl = skill_dir / "references/worker/templates/generated-common-header.md"
    body_tmpl = skill_dir / "references/worker/phase-briefs/brief-root-cause-challenger-phase-5-5-one-per-batch.md"
    header_text = extract_fenced_block(header_tmpl.read_text(encoding="utf-8"))
    body_template = extract_fenced_block(body_tmpl.read_text(encoding="utf-8"))

    for row in rows:
        work_id = row.get("batch", "").strip()
        batch_num = work_id[2:]
        items_str = row.get("root families / scopes", row.get("items", "")).strip()
        brief_path = review_dir / "briefs" / f"{work_id}.md"

        cand_ids = [m for m in re.findall(r"(?:R\d+-RC\d+-\d+|[A-Z][A-Z0-9]*-\d+)", items_str) if not m.startswith(("RF", "V", "RC"))]
        verd_ids = re.findall(r"V\d+-\d+", items_str)

        source_ledgers: set[Path] = set()
        source_verdicts: set[Path] = set()
        embedded_cands: list[str] = []
        embedded_verds: list[str] = []

        for cid in cand_ids:
            if cid in cand_map:
                src_path, hdr, rline = cand_map[cid]
                source_ledgers.add(src_path)
                if not embedded_cands:
                    embedded_cands.append(hdr)
                embedded_cands.append(rline)
        for vid in verd_ids:
            if vid in verd_map:
                src_path, hdr, rline = verd_map[vid]
                source_verdicts.add(src_path)
                if not embedded_verds:
                    embedded_verds.append(hdr)
                embedded_verds.append(rline)

        support = merge_support_context(review_dir, cand_ids, cand_map)
        support_path = review_dir / "packets" / f"{work_id}-merge-context.md"
        if support:
            budget = json.loads((review_dir / "profile.json").read_text(encoding="utf-8"))["budgets"]["candidate_packet_budget_bytes"]
            embedded_bytes = len(("\n".join(embedded_cands + embedded_verds) + support).encode("utf-8"))
            if embedded_bytes > budget:
                fail(f"{work_id} assigned and comparison rows exceed candidate-packet budget; split rather than truncate")
            support_path.parent.mkdir(parents=True, exist_ok=True)
            support_path.write_text(support, encoding="utf-8")

        hdr_filled = header_text
        for k, v in {
            "⟨CL⟩": pin_info["CL"],
            "⟨PS⟩": pin_info["PS"],
            "⟨sha⟩": pin_info["sha"],
            "⟨parent-sha⟩": pin_info["parent-sha"],
            "⟨review-dir⟩": str(review_dir),
            "⟨worktree⟩": pin_info["worktree"],
            "⟨work-id⟩": work_id,
            "⟨attempt⟩": str(attempt),
            "⟨skill-dir⟩": str(skill_dir),
        }.items():
            hdr_filled = hdr_filled.replace(k, v)

        body_filled = body_template
        for k, v in {
            "⟨batch⟩": batch_num,
            "⟨round⟩": str(round_num),
            "⟨review-dir⟩": str(review_dir),
            "⟨skill-dir⟩": str(skill_dir),
            "⟨IDs, e.g.\nRF001 (EPW-2/V001-1, AL-4/V002-2), T001⟩": items_str,
            "⟨review-dir⟩/verification/*.md": ", ".join(str(p) for p in sorted(source_verdicts)) or str(review_dir / "verification/batches.md"),
            "⟨review-dir⟩/ledger/*.md": ", ".join(str(p) for p in sorted(source_ledgers)) or str(review_dir / "collection.md"),
            "R⟨round⟩-RC⟨batch⟩-1, -2, ...": f"R{round_num}-RC{batch_num}-⟨n⟩ (numbered from 1)",
        }.items():
            body_filled = body_filled.replace(k, v)

        embed_block = "\n\n### Embedded Candidate & Verdict Rows\n\n"
        if embedded_cands:
            embed_block += "#### Candidate Rows\n\n" + "\n".join(embedded_cands) + "\n\n"
        if embedded_verds:
            embed_block += "#### Verdict Rows\n\n" + "\n".join(embedded_verds) + "\n"

        if support:
            embed_block += (f"\nInputs: {support_path} — bounded comparison context for provisional aliases only; "
                            "not additional assigned candidates and not accepted merge equivalence.\n")
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(f"{hdr_filled}\n\n{body_filled}{embed_block}", encoding="utf-8")

        extra_roles = {p: "candidate-packet" for p in source_ledgers}
        for p in source_verdicts:
            extra_roles[p] = "assigned"
        if support:
            extra_roles[support_path.resolve()] = "assigned"
        cmd = seal_command(
            skill_dir=skill_dir,
            review_dir=review_dir,
            brief=brief_path,
            phase="5.5",
            work_id=work_id,
            attempt=attempt,
            tier="frontier",
            artifact=f"root-cause/{work_id}.md",
            extra_roles=extra_roles,
        )
        print(" ".join(shlex.quote(part) for part in cmd))
        if do_seal:
            seal_res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if seal_res.returncode != 0:
                fail(f"seal-work-unit.py failed for {work_id}: {seal_res.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--phase", choices=("verification", "root-cause"), required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--seal", action="store_true", help="Execute seal-work-unit.py for each generated brief")
    args = parser.parse_args()

    review_dir = args.review_dir.resolve()
    skill_dir = review_dir / "skill-snapshot"
    if not skill_dir.is_dir():
        fail(f"missing skill-snapshot at {skill_dir}")
    pin_info = parse_pin(review_dir / "pin.md")

    if args.phase == "verification":
        build_verification(review_dir, skill_dir, pin_info, args.attempt, args.seal)
    else:
        build_root_cause(review_dir, skill_dir, pin_info, args.attempt, args.round, args.seal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
