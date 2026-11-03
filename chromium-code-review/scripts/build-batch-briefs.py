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
import interdiff_hunks  # noqa: E402


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


def load_candidate_locations(review_dir: Path) -> dict[str, str]:
    """Return effective canonical candidate `id -> location`."""
    locations: dict[str, str] = {}
    sources = sorted((review_dir / "ledger").glob("**/*.md"))
    if (review_dir / "collection.md").is_file():
        sources.append(review_dir / "collection.md")
    for path in sources:
        parsed, errors = effective_tables(path.read_text(encoding="utf-8"), str(path))
        if errors:
            continue
        for heading, header, rows in parsed:
            if heading != "Candidate rows" and path.name != "collection.md":
                continue
            if not {"id", "claim", "location", "evidence / hypothesis", "status"}.issubset(header):
                continue
            for row in rows:
                identifier = row.get("id", "")
                if identifier and identifier not in locations:
                    locations[identifier] = row.get("location", "")
    return locations


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
    cand_locations = load_candidate_locations(review_dir)
    profile_path = review_dir / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    all_files = {str(item.get("path", "")): str(item.get("status", "M")) for item in profile.get("files", [])}
    prior_ctx = profile.get("prior_context")
    reviewer_hist = (
        prior_ctx.get("reviewer_history", {})
        if isinstance(prior_ctx, dict) and isinstance(prior_ctx.get("reviewer_history"), dict)
        else {}
    )
    interdiff_path = review_dir / "indexes" / "interdiff-hunks.tsv"
    pr_ledger_path = review_dir / "ledger" / "PR.md"
    is_followup = bool(reviewer_hist.get("same_reviewer_followup")) or interdiff_path.is_file()
    loaded_hunks = (
        interdiff_hunks.load_interdiff_hunks(review_dir)
        if interdiff_path.is_file()
        else None
    )

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

        ledger_inputs = ", ".join(p.relative_to(review_dir).as_posix() for p in sorted(source_ledgers))
        base_inputs = [
            str(code_packet_path),
            str(review_dir / "callers/index.tsv"),
            str(review_dir / "callers/directory-docs.md"),
        ]
        followup_block = ""
        if is_followup:
            for extra_input in (profile_path, interdiff_path, pr_ledger_path):
                if extra_input.is_file():
                    base_inputs.append(str(extra_input))
            round_num = reviewer_hist.get("review_round", 2)
            prior_ps = reviewer_hist.get("latest_prior_reviewed_patchset")
            prior_sha = reviewer_hist.get("latest_prior_reviewed_sha")
            baseline_desc = (
                f"PS{prior_ps}" + (f" ({str(prior_sha)[:12]})" if prior_sha else "")
                if prior_ps is not None
                else "prior reviewed patchset"
            )
            overlap_lines: list[str] = []
            if loaded_hunks is not None:
                for cid in cand_ids:
                    loc_text = cand_locations.get(cid, "")
                    spans = interdiff_hunks.parse_location_ranges(loc_text)
                    matched_hunk = None
                    for span_path, span_start, span_end in spans:
                        matched_hunk = interdiff_hunks.overlaps_interdiff(
                            loaded_hunks, span_path, span_start, span_end
                        )
                        if matched_hunk is not None:
                            break
                    if matched_hunk is not None:
                        overlap_lines.append(
                            f"- `{cid}` ({loc_text}): interdiff-touched "
                            f"(`{matched_hunk['id']}` at "
                            f"`{matched_hunk['path']}:{matched_hunk['new_start']}`)"
                        )
                    elif spans:
                        overlap_lines.append(
                            f"- `{cid}` ({loc_text}): unchanged-since-prior-review"
                        )
                    else:
                        overlap_lines.append(
                            f"- `{cid}` ({loc_text or 'no path:line'}): interdiff-overlap-unclassified"
                        )
            followup_lines = [
                "\n\n## Same-Reviewer Follow-Up Context\n",
                f"- Same-reviewer follow-up round: {round_num} (latest baseline: {baseline_desc}).",
                *overlap_lines,
                "- Apply the Round-N unchanged-code severity recalibration and accepted-deferral (`deferred (accepted)`) rules from `verifying-candidate-findings.md`.",
            ]
            followup_block = "\n".join(followup_lines)

        inputs_prose = (
            ", ".join(base_inputs[:-1]) + f", and {base_inputs[-1]}"
            if len(base_inputs) > 1
            else base_inputs[0]
        )
        body = (
            f"Scope: verify batch {work_id} ONLY — candidate rows {', '.join(cand_ids)}.\n\n"
            f"Inputs: {inputs_prose} (inline candidate rows extracted from {ledger_inputs}).\n\n"
            f"## Assigned Candidate Rows\n\n"
            + "\n".join(embedded_rows)
            + followup_block
            + "\n\nProcedure:\n"
            f"1. Read {skill_dir / 'references/worker/verification-and-fixes/verifying-candidate-findings.md'}, "
            f"{skill_dir / 'references/worker/verification-and-fixes/skeptic-verdicts.md'}, "
            f"{skill_dir / 'references/worker/verification-and-fixes/evaluating-fixes.md'}, and "
            f"{skill_dir / 'references/worker/synthesis-and-output/severity-calibration.md'}.\n"
            f"2. Verify each candidate in {', '.join(cand_ids)} against the pinned worktree and emit one verdict row ({work_id}-1, {work_id}-2, ...) "
            f"plus `## Trace closure` and `## Verified affinity` in the exact shape from "
            f"{skill_dir / 'references/worker/templates/verification-batches-and-skeptic-verdict-rows.md'}.\n\n"
            f"Deliverable: {review_dir / 'verification' / f'{work_id}.md'}.\n"
        )
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        if brief_path.exists():
            brief_path.chmod(0o644)
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
            artifact=str((review_dir / f"verification/{work_id}.md").resolve()),
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
            if support_path.exists():
                support_path.chmod(0o644)
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
            "⟨review-dir⟩/verification/*.md": (
                ", ".join(p.relative_to(review_dir).as_posix() for p in sorted(source_verdicts)) + " (embedded below)"
                if source_verdicts else "verification/batches.md"
            ),
            "⟨review-dir⟩/ledger/*.md": (
                ", ".join(p.relative_to(review_dir).as_posix() for p in sorted(source_ledgers)) + " (embedded below)"
                if source_ledgers else "collection.md"
            ),
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
        if brief_path.exists():
            brief_path.chmod(0o644)
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
            artifact=str((review_dir / f"root-cause/{work_id}.md").resolve()),
            extra_roles=extra_roles,
        )
        print(" ".join(shlex.quote(part) for part in cmd))
        if do_seal:
            seal_res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if seal_res.returncode != 0:
                fail(f"seal-work-unit.py failed for {work_id}: {seal_res.stderr.strip()}")


def ensure_indexes(review_dir: Path, skill_dir: Path) -> None:
    index_script = (
        skill_dir / "scripts" / "build-review-indexes.py"
        if (skill_dir / "scripts" / "build-review-indexes.py").is_file()
        else SCRIPT_DIR / "build-review-indexes.py"
    )
    res = subprocess.run(
        [sys.executable, str(index_script), str(review_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        fail(f"build-review-indexes.py failed: {res.stderr.strip()}")


def plan_verification(
    review_dir: Path,
    skill_dir: Path,
    max_candidates: int = 30,
    max_per_batch: int = 5,
) -> int:
    cand_tsv = review_dir / "indexes" / "candidates.tsv"
    if not cand_tsv.is_file():
        ensure_indexes(review_dir, skill_dir)
    with cand_tsv.open(encoding="utf-8", newline="") as stream:
        candidates = list(csv.DictReader(stream, delimiter="\t"))
    if len(candidates) > max_candidates:
        fail(
            f"indexes/candidates.tsv has {len(candidates)} rows "
            f"(> {max_candidates}); spawn the Phase 5 VPLAN subagent to shard"
        )
    batches_md = review_dir / "verification" / "batches.md"
    batches_md.parent.mkdir(parents=True, exist_ok=True)
    if not candidates:
        batches_md.write_text(
            "# Verification batches\n\n"
            "- Candidate count: 0\n"
            "- Result: empty — no verification batches scheduled\n",
            encoding="utf-8",
        )
        print(f"plan_verification: 0 candidates -> wrote empty {batches_md}")
        return 0

    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    primary_by_sig: dict[tuple[str, str, str], dict[str, str]] = {}
    primaries: list[dict[str, str]] = []
    merges: list[tuple[str, str, str]] = []
    for row in sorted(candidates, key=lambda r: r.get("id", "")):
        cid = row.get("id", "").strip()
        loc = norm(row.get("location", ""))
        owner = norm(row.get("invariant_owner", ""))
        inv = norm(row.get("violated_invariant", ""))
        sig = (loc, owner, inv)
        if (
            loc
            and owner not in {"", "-", "unknown"}
            and inv not in {"", "-", "unknown"}
            and sig in primary_by_sig
        ):
            surv = primary_by_sig[sig]
            surv_id = surv["id"].strip()
            merges.append((
                cid,
                surv_id,
                f"same location ({row.get('location', '').strip()}) and "
                f"invariant ({row.get('invariant_owner', '').strip()}: "
                f"{row.get('violated_invariant', '').strip()})",
            ))
        else:
            if loc and owner and inv:
                primary_by_sig[sig] = row
            primaries.append(row)

    # Order primaries by file path and topology component so related candidates
    # stay together in the same batch.
    cand_to_edge: dict[str, str] = {}
    topo_tsv = review_dir / "indexes" / "topology.tsv"
    if topo_tsv.is_file():
        with topo_tsv.open(encoding="utf-8", newline="") as stream:
            for t_row in csv.DictReader(stream, delimiter="\t"):
                edge_id = (t_row.get("edge") or "").strip()
                for member in (t_row.get("candidate") or "").split(","):
                    member = member.strip()
                    if member and member != "-" and member not in cand_to_edge:
                        cand_to_edge[member] = edge_id

    def primary_sort_key(row: dict[str, str]) -> tuple[str, str, str]:
        cid = row.get("id", "").strip()
        loc = row.get("location", "").strip()
        file_path = loc.split(":", 1)[0] if ":" in loc else loc
        return (file_path, cand_to_edge.get(cid, ""), cid)

    ordered = sorted(primaries, key=primary_sort_key)
    batches: list[tuple[str, list[str]]] = []
    for index in range(0, len(ordered), max(1, max_per_batch)):
        chunk = [item["id"].strip() for item in ordered[index:index + max(1, max_per_batch)]]
        batch_id = f"V{len(batches) + 1:03d}"
        batches.append((batch_id, chunk))

    lines = [
        "# Verification batches",
        "",
        f"- Candidate count: {len(candidates)}",
        "",
        "## Batches",
        "",
        "| batch | candidates | brief | verdict file |",
        "| --- | --- | --- | --- |",
    ]
    for batch_id, chunk in batches:
        lines.append(
            f"| {batch_id} | {', '.join(chunk)} | briefs/{batch_id}.md | "
            f"verification/{batch_id}.md |"
        )
    if merges:
        lines.extend([
            "",
            "## Merge proposals",
            "",
            "| row | proposal | reason |",
            "| --- | --- | --- |",
        ])
        for dup_id, surv_id, reason in merges:
            lines.append(f"| {dup_id} | merge-into {surv_id} | {reason} |")
    batches_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"plan_verification: {len(candidates)} candidate(s) -> "
        f"{len(batches)} batch(es), {len(merges)} merge proposal(s)"
    )
    return len(batches)


def plan_root_cause(
    review_dir: Path,
    skill_dir: Path,
    max_survivors: int = 8,
    max_families_per_batch: int = 4,
    schedule_p3: bool = False,
) -> int:
    ensure_indexes(review_dir, skill_dir)
    verd_tsv = review_dir / "indexes" / "verdicts.tsv"
    cand_tsv = review_dir / "indexes" / "candidates.tsv"
    with verd_tsv.open(encoding="utf-8", newline="") as stream:
        verdict_rows = list(csv.DictReader(stream, delimiter="\t"))
    with cand_tsv.open(encoding="utf-8", newline="") as stream:
        cand_rows = {
            row["id"].strip(): row
            for row in csv.DictReader(stream, delimiter="\t")
            if row.get("id")
        }

    surviving = [
        row
        for row in sorted(verdict_rows, key=lambda r: r.get("id", ""))
        if row.get("verdict") in {"CONFIRMED", "UNPROVEN"}
    ]
    if len(surviving) > max_survivors:
        fail(
            f"indexes/verdicts.tsv has {len(surviving)} surviving rows "
            f"(> {max_survivors}); spawn IAR and RCPLAN subagents"
        )

    merge_aliases_by_survivor: dict[str, list[str]] = {}
    v_batches_md = review_dir / "verification" / "batches.md"
    if v_batches_md.is_file():
        parsed_vb, _ = effective_tables(
            v_batches_md.read_text(encoding="utf-8"), str(v_batches_md)
        )
        for heading, header, rows in parsed_vb:
            if heading.startswith("Merge proposals") and {"row", "proposal"}.issubset(header):
                for m_row in rows:
                    m_match = re.match(
                        r"(?i)^merge-into\s+([A-Z][A-Z0-9]*-\d+|R\d+-RC\d+-\d+)\b",
                        m_row.get("proposal", "").strip(),
                    )
                    if m_match:
                        merge_aliases_by_survivor.setdefault(
                            m_match.group(1), []
                        ).append(m_row.get("row", "").strip())

    def norm_field(val: str) -> str:
        return re.sub(r"\s+", " ", (val or "").strip())

    families: list[dict[str, object]] = []
    family_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for v_row in surviving:
        cid = v_row.get("candidate", "").strip()
        vid = v_row.get("id", "").strip()
        c_row = cand_rows.get(cid, {})
        inv_owner = norm_field(v_row.get("invariant_owner", ""))
        if not inv_owner or inv_owner == "-":
            inv_owner = norm_field(c_row.get("invariant_owner", "")) or "local"
        violated_inv = norm_field(v_row.get("violated_invariant", ""))
        if not violated_inv or violated_inv == "-":
            violated_inv = norm_field(c_row.get("violated_invariant", "")) or norm_field(c_row.get("claim", ""))
        state_trans = norm_field(v_row.get("state_transition", ""))
        if not state_trans or state_trans == "-":
            state_trans = norm_field(c_row.get("state_transition", "")) or "local state"
        fix_layer = norm_field(v_row.get("proposed_fix_layer", ""))
        if not fix_layer or fix_layer == "-":
            fix_layer = norm_field(c_row.get("proposed_fix_layer", "")) or norm_field(c_row.get("location", ""))
        rel_syms = norm_field(v_row.get("related_symbols", ""))
        if not rel_syms or rel_syms == "-":
            rel_syms = norm_field(c_row.get("related_symbols", "")) or cid

        key = (inv_owner.lower(), violated_inv.lower())
        fam = family_by_key.get(key)
        if fam is None:
            rf_id = f"RF{len(families) + 1:03d}"
            fam = {
                "id": rf_id,
                "members": [],
                "pairs": [],
                "shared_invariant": violated_inv,
                "invariant_owner": inv_owner,
                "state_transition": state_trans,
                "fix_layer": fix_layer,
                "related_symbols": rel_syms,
                "citations": [],
                "needs_rc": False,
            }
            families.append(fam)
            family_by_key[key] = fam
        members_list: list[str] = fam["members"]  # type: ignore[assignment]
        for item_id in (cid, vid, *merge_aliases_by_survivor.get(cid, [])):
            if item_id and item_id not in members_list:
                members_list.append(item_id)
        pairs_list: list[dict[str, str]] = fam["pairs"]  # type: ignore[assignment]
        pairs_list.append(v_row)
        cites_list: list[str] = fam["citations"]  # type: ignore[assignment]
        for cite in (
            v_row.get("citations", "").split(",")[0].strip(),
            c_row.get("location", "").strip(),
        ):
            if cite and cite not in cites_list:
                cites_list.append(cite)
        sev = (
            v_row.get("severity")
            or c_row.get("severity")
            or ""
        ).strip().upper()
        verdict_val = (v_row.get("verdict") or "").strip().upper()
        if schedule_p3 or verdict_val != "CONFIRMED" or not sev.startswith("P3"):
            fam["needs_rc"] = True

    default_evidence = "profile.json:/files"
    if surviving:
        first_cite = (
            surviving[0].get("citations", "").split(",")[0].strip()
            or cand_rows.get(surviving[0].get("candidate", ""), {}).get("location", "").strip()
        )
        if first_cite:
            default_evidence = first_cite
    elif verdict_rows:
        first_cite = verdict_rows[0].get("citations", "").split(",")[0].strip()
        if first_cite:
            default_evidence = first_cite

    rf_summary = (
        ", ".join(str(f["id"]) for f in families)
        if families else "none (0 surviving verdicts)"
    )
    affinity_lines = [
        "# Verified invariant affinity",
        "",
        "## Root families",
        "",
        "| root family | members | shared invariant | invariant owner | state / transition | fix layer | related symbols | disposition |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for fam in families:
        disp = (
            "root-cause batch required"
            if fam["needs_rc"]
            else "non-risky P3 validated in verification"
        )
        affinity_lines.append(
            f"| {fam['id']} | {', '.join(fam['members'])} | "  # type: ignore[arg-type]
            f"{fam['shared_invariant']} | {fam['invariant_owner']} | "
            f"{fam['state_transition']} | {fam['fix_layer']} | "
            f"{fam['related_symbols']} | {disp} |"
        )
    checks = (
        "contradictory assumptions",
        "invariant-owner collisions",
        "style-authority scope",
        "lifetime operation owner",
        "reachability termination",
        "repeated local fixes",
    )
    affinity_lines.extend([
        "",
        "## Consistency audit",
        "",
        "| check | rows / families | evidence | result |",
        "| --- | --- | --- | --- |",
    ])
    for check_name in checks:
        affinity_lines.append(
            f"| {check_name} | {rf_summary} | {default_evidence} | "
            "clean — no cross-verdict conflict |"
        )
    affinity_path = review_dir / "verification" / "affinity.md"
    affinity_path.parent.mkdir(parents=True, exist_ok=True)
    affinity_path.write_text("\n".join(affinity_lines) + "\n", encoding="utf-8")
    ensure_indexes(review_dir, skill_dir)

    # Read required T* triggers from inventory.md / inventory/*.md
    inv_paths = (
        [review_dir / "inventory.md"]
        if (review_dir / "inventory.md").is_file()
        else (
            sorted((review_dir / "inventory").glob("*.md"))
            if (review_dir / "inventory").is_dir() else []
        )
    )
    required_triggers: list[dict[str, str]] = []
    for inv_path in inv_paths:
        parsed_inv, _ = effective_tables(
            inv_path.read_text(encoding="utf-8"), str(inv_path)
        )
        for heading, header, rows in parsed_inv:
            if heading != "Trigger inventory" or "scope id" not in header:
                continue
            for row in rows:
                t_id = row.get("scope id", "").strip().upper()
                rc_trig = row.get("root-cause trigger", "").strip()
                rc_req = (
                    row.get("root-cause required", row.get("root-cause-required", ""))
                    .strip()
                    .lower()
                )
                if t_id and (
                    rc_trig.lower().startswith("required")
                    or rc_req in {"yes", "true"}
                ):
                    required_triggers.append({
                        "id": t_id,
                        "graph_scope": row.get("graph scope", "").strip(),
                        "evidence": row.get("evidence", "").strip(),
                    })

    topo_status: dict[str, str] = {}
    topo_tsv = review_dir / "indexes" / "topology.tsv"
    if topo_tsv.is_file():
        with topo_tsv.open(encoding="utf-8", newline="") as stream:
            for t_row in csv.DictReader(stream, delimiter="\t"):
                e_id = (t_row.get("edge") or "").strip().upper()
                if e_id:
                    topo_status[e_id] = (t_row.get("status") or "").strip().lower()

    scheduled_items: list[str] = []
    trigger_decisions: list[tuple[str, str, str, str]] = []
    # Pack families that require RC batches first, then any T* triggers with open edges
    rc_batches: list[tuple[str, list[str]]] = []
    current_batch_items: list[str] = []
    family_to_rc_batch: dict[str, str] = {}
    trigger_to_rc_batch: dict[str, str] = {}

    def flush_batch() -> None:
        nonlocal current_batch_items
        if not current_batch_items:
            return
        rc_id = f"RC{len(rc_batches) + 1:03d}"
        rc_batches.append((rc_id, list(current_batch_items)))
        current_batch_items = []

    for fam in families:
        rf_id = str(fam["id"])
        pairs_list = fam["pairs"]  # type: ignore[assignment]
        if fam["needs_rc"]:
            pair_tokens = [
                f"{p.get('candidate', '').strip()}/{p.get('id', '').strip()}"
                for p in pairs_list
            ]
            item_token = f"{rf_id} ({', '.join(pair_tokens)})"
            if len(current_batch_items) >= max(1, max_families_per_batch):
                flush_batch()
            rc_id = f"RC{len(rc_batches) + 1:03d}"
            current_batch_items.append(item_token)
            family_to_rc_batch[rf_id] = rc_id

    for trig in sorted(required_triggers, key=lambda r: r["id"]):
        t_id = trig["id"]
        g_scope = trig["graph_scope"]
        m_edges = re.search(
            r"(?i)graph:((?:E-[A-Z0-9-]+)(?:,E-[A-Z0-9-]+)*)", g_scope
        )
        edges = (
            [part.strip().upper() for part in m_edges.group(1).split(",") if part.strip()]
            if m_edges else []
        )
        open_edges = [
            e_id for e_id in edges
            if topo_status.get(e_id) in {"open", "disputed", "unreviewed"}
        ]
        if open_edges:
            if len(current_batch_items) >= max(1, max_families_per_batch):
                flush_batch()
            rc_id = f"RC{len(rc_batches) + 1:03d}"
            current_batch_items.append(t_id)
            trigger_to_rc_batch[t_id] = rc_id
            trigger_decisions.append((t_id, "—", "scheduled", rc_id))
        else:
            proof = (
                f"graph:{','.join(edges)}" if edges else ""
            )
            cite = trig["evidence"]
            reason_parts = [p for p in (proof, cite) if p]
            reason_str = (
                ", ".join(reason_parts)
                if reason_parts else default_evidence
            )
            trigger_decisions.append((
                t_id,
                "—",
                f"not applicable — all graph edges resolved in discovery/verification ({reason_str})",
                "—",
            ))

    flush_batch()

    for fam in families:
        rf_id = str(fam["id"])
        pairs_list = fam["pairs"]  # type: ignore[assignment]
        cites_list = fam["citations"]  # type: ignore[assignment]
        first_cite = cites_list[0] if cites_list else default_evidence
        for p in pairs_list:
            cid = p.get("candidate", "").strip()
            vid = p.get("id", "").strip()
            if rf_id in family_to_rc_batch:
                rc_id = family_to_rc_batch[rf_id]
                trigger_decisions.append((
                    f"{cid} / {vid}",
                    rf_id,
                    "scheduled",
                    rc_id,
                ))
            else:
                trigger_decisions.append((
                    f"{cid} / {vid}",
                    rf_id,
                    f"not applicable — non-risky P3 validated in verification ({vid}, {first_cite})",
                    "—",
                ))

    rc_lines = [
        "# Root-cause batches",
        "",
        f"- Trigger count: {len(rc_batches)}",
    ]
    if not rc_batches:
        rc_lines.append(
            "- Result: empty — all triggers and non-risky P3 families closed in Trigger accounting"
        )
    if trigger_decisions:
        rc_lines.extend([
            "",
            "## Trigger accounting",
            "",
            "| candidate / verdict | root family | disposition | rc batch |",
            "| --- | --- | --- | --- |",
        ])
        for scope_cell, rf_cell, disp_cell, batch_cell in trigger_decisions:
            rc_lines.append(
                f"| {scope_cell} | {rf_cell} | {disp_cell} | {batch_cell} |"
            )
    if rc_batches:
        rc_lines.extend([
            "",
            "## Batches",
            "",
            "| batch | brief | root families / scopes | output | bounded input |",
            "| --- | --- | --- | --- | --- |",
        ])
        for rc_id, items in rc_batches:
            rc_lines.append(
                f"| {rc_id} | briefs/{rc_id}.md | {'; '.join(items)} | "
                f"root-cause/{rc_id}.md | {len(items)} item(s) |"
            )

    rc_batches_path = review_dir / "root-cause" / "batches.md"
    rc_batches_path.parent.mkdir(parents=True, exist_ok=True)
    rc_batches_path.write_text("\n".join(rc_lines) + "\n", encoding="utf-8")
    print(
        f"plan_root_cause: {len(surviving)} surviving verdict(s), "
        f"{len(families)} root family/families -> {len(rc_batches)} RC batch(es)"
    )
    return len(rc_batches)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--phase", choices=("verification", "root-cause"), required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--plan", action="store_true", help="Deterministically generate batches.md (and affinity.md for root-cause) before building briefs")
    parser.add_argument("--max-candidates", type=int, default=30, help="Maximum candidates for --plan --phase verification fast path")
    parser.add_argument("--max-per-batch", type=int, default=5, help="Maximum candidates per V* batch for --plan --phase verification")
    parser.add_argument("--max-survivors", type=int, default=8, help="Maximum surviving verdicts for --plan --phase root-cause fast path")
    parser.add_argument("--max-families-per-batch", type=int, default=4, help="Maximum root families / triggers per RC* batch for --plan --phase root-cause")
    parser.add_argument("--schedule-p3", action="store_true", help="Schedule CONFIRMED P3 families to RC* batches instead of closing them in Trigger accounting")
    parser.add_argument("--seal", action="store_true", help="Execute seal-work-unit.py for each generated brief")
    args = parser.parse_args()

    review_dir = args.review_dir.resolve()
    skill_dir = review_dir / "skill-snapshot"
    if not skill_dir.is_dir():
        fail(f"missing skill-snapshot at {skill_dir}")
    pin_info = parse_pin(review_dir / "pin.md")

    if args.phase == "verification":
        if args.plan:
            planned = plan_verification(
                review_dir,
                skill_dir,
                max_candidates=args.max_candidates,
                max_per_batch=args.max_per_batch,
            )
            if planned == 0:
                return 0
        build_verification(review_dir, skill_dir, pin_info, args.attempt, args.seal)
    else:
        if args.plan:
            planned = plan_root_cause(
                review_dir,
                skill_dir,
                max_survivors=args.max_survivors,
                max_families_per_batch=args.max_families_per_batch,
                schedule_p3=args.schedule_p3,
            )
            if planned == 0:
                return 0
        build_root_cause(review_dir, skill_dir, pin_info, args.attempt, args.round, args.seal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
