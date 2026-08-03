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

## Brief — Inventory Shard (Phase 1, one per file group or dense hunk range)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: only inventory shard ⟨SHARD⟩. File-group scope: ⟨explicit file list or
`none`⟩. Dense-file scope: ⟨path plus exact H IDs and old/new changed-line
intervals, or `none`⟩. Do not inventory another shard's hunks/surfaces and do
not create or edit context.md. For a surface crossing dense-shard boundaries,
the shard owning its earliest changed line owns the complete surface row;
adjacent reads are context only.

Pinned range/pathspec: parent ⟨parent-sha⟩, revision ⟨sha⟩, exact repo-relative
pathspec ⟨explicit path list including both sides of renames/deletions⟩. Use
only that range/pathspec and the hunk ownership map in
⟨review-dir⟩/profile.json, never ambient HEAD.

Procedure: read
⟨skill-dir⟩/references/worker/inventory-and-planning/pass-1-changed-surface-inventory-and-risk-area-map.md
and
⟨skill-dir⟩/references/worker/inventory-and-planning/specialist-trigger-decisions.md,
then execute Pass 1 for every scoped file. Inventory every changed/new/removed
function, method, constructor, destructor, stateful lambda, and helper,
including private, anonymous-namespace, test-only, and generated surfaces —
aggregated per the Pass 1 aggregation rule: test bodies, generated blocks,
mechanical accessors, data-only tables, and repeated-transformation sites get
one `group:` row per (this shard × file × fixture/class) with a leading
member count, name list, and this shard's owned hunks — group only members
whose hunks this shard owns; never one detailed row per member, and never a
caller grep for an aggregated group member. Individually-rowed surfaces
(fixtures, stateful helpers/mocks) keep their normal fields. Also evaluate
every recipe,
base-checklist, and specialist trigger under "Specialist
Trigger Decisions." Emit one trigger row per recipe/checklist roster entry for
this shard, including complete negative evidence. The deterministic collector
checks the union of file-group
paths or dense hunk IDs and the earliest-changed-line surface ownership rule;
silently omitting or duplicating scope is invalid.

Deliverable: ⟨review-dir⟩/inventory/⟨SHARD⟩.md — changed surfaces,
risk-area map, and shard-unique trigger inventory in the inventory shape from
⟨skill-dir⟩/references/worker/templates/inventory-md-changed-surface-inventory-and-risk-area-map.md. The orchestrator regenerates the central
inventory index after all shards finish; do not handwrite it.

Return: one line — shard name, risk areas, scoped-file count, surface count,
path, and `complete` or explicit remaining files.
```
