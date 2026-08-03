<!-- Generated from ../../phase-briefs.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Phase Briefs

Orchestrator-facing: these briefs and SKILL.md are the only skill content the
orchestrator loads before synthesis; Phase 7 also loads
`synthesis-orchestration.md`. Once the snapshot exists, load the per-brief
section files under `⟨skill-dir⟩/references/worker/phase-briefs/`
just-in-time — the Common Header once, then each phase's brief when that
phase becomes runnable — rather than ingesting this whole file. Each brief
below is spawned as one fresh-context subagent. Copy the brief, substitute every `⟨placeholder⟩` (all paths
absolute — subagents start cold in the repository checkout), prepend the
Common Header, and spawn. Do not paraphrase briefs or compose them freehand,
and do not inline reference-file content into them.

For every substitution, `⟨skill-dir⟩` is the verified immutable
`⟨review-dir⟩/skill-snapshot`, never the live canonical skill checkout. The
snapshot contains generated per-section worker references under
`⟨skill-dir⟩/references/worker/⟨stem⟩/⟨slug⟩.md` (each stem has an
`index.md` naming its sections); the briefs below already point at the exact
section files their workers execute, so a worker never ingests a whole
reference monolith for one section. Finish
the substituted brief and its exact input list, then register both with
`⟨skill-dir⟩/scripts/seal-work-unit.py` before spawning it. A sealed brief is
read-only; corrections use a new attempt-numbered brief and seal.

Discovery-thread and skeptic briefs are NOT here — the Planner and
Verification-Planner agents write those into `⟨review-dir⟩/briefs/`, and the
orchestrator spawns them with only: "Read and execute the brief at
⟨absolute brief path⟩. It defines your pin, scope, procedure, deliverable,
and rules."

## Brief — Inventory (Phase 1, unsharded)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: every changed file in the pinned diff. Build inventory only; context.md
is owned by the Context agent.

Pinned range/pathspec: parent ⟨parent-sha⟩, revision ⟨sha⟩, exact changed-file
pathspec ⟨explicit path list including both sides of renames/deletions⟩. Use
only `git diff ⟨parent-sha⟩ ⟨sha⟩ -- ⟨pathspec⟩`, never ambient HEAD.

Inputs also include ⟨review-dir⟩/profile.json and profile.md.

Procedure: read
⟨skill-dir⟩/references/worker/inventory-and-planning/pass-1-changed-surface-inventory-and-risk-area-map.md
and
⟨skill-dir⟩/references/worker/inventory-and-planning/specialist-trigger-decisions.md,
then execute Pass 1. Inventory every changed/new/removed function, method,
constructor, destructor, stateful lambda, and helper, including private,
anonymous-namespace, test-only, and generated surfaces — but aggregate
homogeneous classes per the Pass 1 aggregation rule: test bodies, generated
blocks, mechanical accessors, data-only tables, and repeated-transformation
sites get one `group:` row per file/fixture with a leading member count and
name list, never one detailed row per member, and never a caller grep for an
aggregated group member. Surfaces keeping individual rows —
production/contract surfaces, fixtures, stateful helpers/mocks,
production-reachable test utilities — get their normal fields, including
caller searches where the schema asks. Evaluate every recipe,
base-checklist, and specialist trigger, including the deterministic path,
symbol, and surface signals under "Specialist Trigger Decisions"; emit one
trigger-inventory row per recipe/checklist roster entry, including proved
absence rows. The always-run holistic row needs no trigger row.
Use context.md if present, but do not block on it and do not edit it.

Deliverable: ⟨review-dir⟩/inventory.md — changed surfaces, risk-area map,
and stable trigger inventory (including root-cause-required scope IDs) in
the exact shape from
⟨skill-dir⟩/references/worker/templates/inventory-md-changed-surface-inventory-and-risk-area-map.md. The orchestrator
regenerates `indexes/inventory.tsv` after collection; do not handwrite it.

Return: one line — risk areas, changed-file count, surface count, path.
```
