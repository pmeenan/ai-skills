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

## Brief — Verification-Plan Exact Collector (Phase 5)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: collect VPLAN shards mechanically; do not group candidates, propose
merges, or alter planner decisions.

Inputs: verification/planning/index.tsv, every planned VPLAN*.scope.tsv and
VPLAN*.md, indexes/candidates.tsv plus manifest fingerprints, and generated
skeptic brief paths. Verify exact files through input-manifest.tsv if this
contract runs in a worker wrapper.

Procedure: require non-overlapping scope IDs whose union exactly equals the
selected full/delta candidate universe. Require every candidate exactly once
as a batch member or merge proposal; every merge survivor scheduled; reserved
V intervals disjoint and after existing IDs; emitted V IDs inside their owning
interval and globally unique; all named briefs present with manifest rows.
Reject missing, duplicate, foreign, stale, or out-of-range data.

Deliverable: canonical verification/batches.md assembled in numeric V order
without semantic edits, and the shard-recorded manifest rows merged into the
root input-manifest.tsv via one atomic rewrite. Preserve immutable shard
results and unused reserved IDs in planning/index.tsv.

Return: one line — universe/accounted counts, duplicate/foreign/missing IDs,
interval/brief errors, canonical path, complete/needs-repair.
```
