#!/usr/bin/env python3
"""Deterministically build Phase 3 plan.md, scope packets, and discovery briefs.

For schema-3 `evidence-graph-v1` reviews that do not require multi-shard
partitioning (`profile.json` `initial_plan_fast_path_eligible: true` and at
most `--max-unsharded-edges` inventory complexity-graph edges), the initial
Phase 3 thread plan is a deterministic function of:
  1. `profile.json` (pinned revision/parent/worktree, changed files/hunks)
  2. `indexes/inventory.tsv` and `indexes/topology.tsv` (surfaces and edges)
  3. `inventory.md` (`Trigger inventory` `<PREFIX> hard` specialist triggers)

Instead of spawning an LLM Planner (`PLAN`) agent merely to emit the two
unsharded generalist rows (`GSS` and `GAI`) plus any `<PREFIX> hard`
specialist rows, this helper deterministically writes:
  - `plan.md`
  - `packets/<WORK>.spec.tsv` and `packets/<WORK>-code.md` (via
    `build-scope-packets.py`)
  - `briefs/<WORK>.md` (via `build-discovery-brief.py`)

When `compact_generalist_fast_path_eligible` is true (or always for unsharded
`evidence-graph-v1` initial passes), `GSS` also receives `mechanical-leads.md`
(when present) and `GAI` also receives `context.md` (when present) plus any
precomputed `callers/dossiers/*.md` class lifetime dossiers, closing
mechanical-leads and holistic alignment within the dual-frontier passes without
spawning extra discovery subagents.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent

GENERALIST_ROWS = (
    ("Generalist Semantic And State Discovery", "GSS"),
    ("Generalist Adversarial And Integration Discovery", "GAI"),
)

SPECIALIST_PREFIX_TO_NAME = {
    "TSY": "Threading And Synchronization",
    "OBL": "Ownership And Blink Lifecycle",
    "MIS": "Mojo And IPC Security",
    "PRS": "Performance And Resource Scaling",
    "PLS": "Platform And Language Semantics",
    "BAG": "Build, API, And Generated Assets",
    "PAT": "Privacy, Abuse, And Telemetry",
    "AXI": "Accessibility And UI Integration",
    "NET": "Networking, Storage, And Protocols",
    "FTS": "Fuzzing And Test Strategy",
}


def fail(message: str) -> None:
    print(f"build-initial-plan.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        fail(f"missing required index file: {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def parse_hard_triggers(inventory_md: Path) -> dict[str, set[str]]:
    """Return mapping of specialist prefix -> set of graph edge IDs for `<PREFIX> hard`."""
    if not inventory_md.is_file():
        return {}
    text = inventory_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_trigger_table = False
    headers: list[str] = []
    hard_edges: dict[str, set[str]] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_trigger_table = stripped == "## Trigger inventory"
            headers = []
            continue
        if not in_trigger_table or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not headers:
            headers = [cell.lower() for cell in cells]
            continue
        if all(re.fullmatch(r"[-: ]+", cell) for cell in cells if cell):
            continue
        row = dict(zip(headers, cells + [""] * (len(headers) - len(cells))))
        discovery = row.get("discovery triggers", "")
        graph_scope = row.get("graph scope", "")
        edge_match = re.search(
            r"(?i)graph:((?:E-[A-Z0-9-]+)(?:,E-[A-Z0-9-]+)*)", graph_scope
        )
        edges = (
            {item.strip().upper() for item in edge_match.group(1).split(",")}
            if edge_match else set()
        )
        for prefix in SPECIALIST_PREFIX_TO_NAME:
            if re.search(
                rf"(?<![A-Za-z0-9]){re.escape(prefix)}\s+hard(?![A-Za-z0-9])",
                discovery,
                re.IGNORECASE,
            ):
                if not edges:
                    fail(
                        f"inventory.md positive '{prefix} hard' trigger row "
                        f"'{row.get('scope id', '?')}' lacks graph:<edge-id(s)>"
                    )
                hard_edges.setdefault(prefix, set()).update(edges)
    return hard_edges


def write_scope_spec(
    spec_path: Path,
    files: list[dict[str, object]],
    note_suffix: str,
) -> None:
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["kind\tpath\told_range\tnew_range\tnote"]
    for item in files:
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        status = str(item.get("status", "M"))
        rows.append(f"diff\t{path}\t-\t-\t{status} full file diff ({note_suffix})")
    spec_path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument(
        "--worktree", type=Path,
        help="pinned git worktree (defaults to pin.worktree in profile.json)",
    )
    parser.add_argument(
        "--max-unsharded-edges", type=int, default=12,
        help="maximum topology edges allowed before delegating to the LLM Planner for sharding",
    )
    args = parser.parse_args()

    review_dir = args.review_dir.resolve()
    profile_path = review_dir / "profile.json"
    if not profile_path.is_file():
        fail(f"missing {profile_path}; run profile-review.py first")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("schema_version", 0) < 3 or (
        profile.get("topology", {}).get("policy") != "evidence-graph-v1"
    ):
        fail("build-initial-plan.py requires schema_version >= 3 evidence-graph-v1")
    if not profile.get("initial_plan_fast_path_eligible", False):
        fail(
            "profile.json marks initial_plan_fast_path_eligible=false "
            f"(effort={profile.get('effort')}); spawn the Phase 3 PLAN agent to shard"
        )

    worktree = (
        args.worktree.resolve()
        if args.worktree is not None
        else Path(profile["pin"]["worktree"]).resolve()
    )
    revision = str(profile["pin"]["revision_sha"])
    parent = str(profile["pin"]["parent_sha"])
    files = list(profile.get("files", []))
    if not files:
        fail("profile.json contains no changed files")

    inventory_rows = read_tsv(review_dir / "indexes" / "inventory.tsv")
    topology_rows = read_tsv(review_dir / "indexes" / "topology.tsv")
    topology_edges = sorted(
        {row.get("edge", "").strip() for row in topology_rows if row.get("edge", "").strip()}
    )
    if len(topology_edges) > args.max_unsharded_edges:
        fail(
            f"topology has {len(topology_edges)} edges (> {args.max_unsharded_edges}); "
            "spawn the Phase 3 PLAN agent to partition connected components"
        )

    surface_ids = [
        row.get("id", "").strip()
        for row in inventory_rows
        if row.get("kind") == "surface" and row.get("id", "").strip()
    ]
    if not surface_ids:
        fail("indexes/inventory.tsv contains no surface rows")

    graph_scope = "graph:all-inventory-edges" if topology_edges else "graph:none"
    hard_triggers = parse_hard_triggers(review_dir / "inventory.md")

    plan_table_rows: list[tuple[str, str, str, str, str]] = []
    spawn_units: list[tuple[str, str, str, str]] = []
    for roster_name, work_id in GENERALIST_ROWS:
        plan_table_rows.append((roster_name, graph_scope, "spawn", "frontier", "D01"))
        spawn_units.append((roster_name, work_id, graph_scope, "generalist"))

    for prefix, edges in sorted(hard_triggers.items()):
        roster_name = SPECIALIST_PREFIX_TO_NAME[prefix]
        spec_scope = f"specialist:full; graph:{','.join(sorted(edges))}"
        plan_table_rows.append((roster_name, spec_scope, "spawn", "frontier", "D01"))
        spawn_units.append((roster_name, prefix, spec_scope, "specialist:full"))

    plan_lines = [
        f"# Thread plan — {revision[:12]}",
        "",
        "| roster entry | scope | status | tier | batch | subagent | outcome |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for roster_name, scope_cell, status, tier, batch in plan_table_rows:
        plan_lines.append(
            f"| {roster_name} | {scope_cell} | {status} | {tier} | {batch} | — | — |"
        )
    (review_dir / "plan.md").write_text("\n".join(plan_lines) + "\n", encoding="utf-8")

    # Ensure skill-snapshot exists so worker references and templates are immutable
    snapshot_dir = review_dir / "skill-snapshot"
    if not snapshot_dir.is_dir():
        snapshot_script = SCRIPT_DIR / "snapshot-skill.py"
        snap_res = subprocess.run(
            [sys.executable, str(snapshot_script), str(SCRIPT_DIR.parent), str(review_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if snap_res.returncode != 0:
            fail(f"snapshot-skill.py failed: {snap_res.stderr.strip()}")

    helper_dir = snapshot_dir / "scripts" if (snapshot_dir / "scripts").is_dir() else SCRIPT_DIR
    scope_packet_script = helper_dir / "build-scope-packets.py"
    discovery_brief_script = helper_dir / "build-discovery-brief.py"

    dossier_files = sorted((review_dir / "callers" / "dossiers").glob("*.md")) if (
        review_dir / "callers" / "dossiers"
    ).is_dir() else []

    procedure_for = {
        "GSS": "worker/discovery-checklists/contracts-and-api-shape.md",
        "GAI": "worker/discovery-checklists/async-and-lifecycle.md",
        "TSY": "worker/chromium-specialist-checklists/threading-and-synchronization-tsy.md",
        "OBL": "worker/chromium-specialist-checklists/ownership-and-blink-lifecycle-obl.md",
        "MIS": "worker/chromium-specialist-checklists/mojo-ipc-authorization-and-sandbox-mis.md",
        "PRS": "worker/chromium-specialist-checklists/performance-and-resource-scaling-prs.md",
        "PLS": "worker/chromium-specialist-checklists/platform-and-language-semantics-pls.md",
        "BAG": "worker/chromium-specialist-checklists/build-api-and-generated-assets-bag.md",
        "PAT": "worker/chromium-specialist-checklists/privacy-and-telemetry-pat.md",
        "AXI": "worker/chromium-specialist-checklists/accessibility-and-internationalization-axi.md",
        "NET": "worker/chromium-specialist-checklists/networking-and-storage-net.md",
        "FTS": "worker/chromium-specialist-checklists/fuzzing-and-test-strategy-fts.md",
    }

    for roster_name, work_id, scope_cell, _unit_kind in spawn_units:
        spec_path = review_dir / "packets" / f"{work_id}.spec.tsv"
        code_packet_path = review_dir / "packets" / f"{work_id}-code.md"
        brief_path = review_dir / "briefs" / f"{work_id}.md"
        write_scope_spec(spec_path, files, f"{work_id} {scope_cell}")
        res = subprocess.run(
            [
                sys.executable,
                str(scope_packet_script),
                str(review_dir),
                work_id,
                "--spec",
                str(spec_path),
                "--worktree",
                str(worktree),
                "--parent",
                parent,
                "--revision",
                revision,
                "--output",
                str(code_packet_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            fail(f"build-scope-packets.py failed for {work_id}: {res.stderr.strip()}")

        brief_cmd = [
            sys.executable,
            str(discovery_brief_script),
            str(review_dir),
            "--work-id",
            work_id,
            "--entry",
            roster_name,
            "--procedure",
            procedure_for.get(work_id, "worker/discovery-checklists/index.md"),
            "--pathspec",
            f"{scope_cell}; surfaces: {','.join(surface_ids)}",
            "--output",
            str(brief_path),
        ]
        res = subprocess.run(brief_cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            fail(f"build-discovery-brief.py failed for {work_id}: {res.stderr.strip()}")

        assigned_extras: list[str] = []
        if work_id == "GSS" and (review_dir / "mechanical-leads.md").is_file():
            assigned_extras.append(
                f"- `{review_dir / 'mechanical-leads.md'}` (close every mechanical lead row alongside your surface/state audit)"
            )
        if work_id == "GAI":
            if (review_dir / "context.md").is_file():
                assigned_extras.append(
                    f"- `{review_dir / 'context.md'}` (audit holistic CL description and intent alignment)"
                )
            for dossier in dossier_files:
                assigned_extras.append(
                    f"- `{dossier.resolve()}` (2-hop Class Lifetime & Async Hop Dossier)"
                )
        if assigned_extras:
            brief_text = brief_path.read_text(encoding="utf-8")
            brief_text += (
                "\n### Additional Precomputed Inputs Assigned To This Pass\n\n"
                + "\n".join(assigned_extras)
                + "\n"
            )
            brief_path.write_text(brief_text, encoding="utf-8")

    mode_label = (
        "compact-dual-generalist"
        if profile.get("compact_generalist_fast_path_eligible") and not hard_triggers
        else "deterministic-initial-plan"
    )
    print(
        f"{mode_label}: wrote {review_dir / 'plan.md'} and "
        f"{len(spawn_units)} packet/brief pair(s): "
        + ", ".join(work_id for _, work_id, _, _ in spawn_units)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
