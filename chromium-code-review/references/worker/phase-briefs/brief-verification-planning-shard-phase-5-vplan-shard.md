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

## Brief — Verification-Planning Shard (Phase 5, VPLAN⟨shard⟩)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

Use this map/collect form when the selected candidate index and canonical row
packets exceed one worker's input budget.

```text
Scope: plan verification only for the exact candidate IDs in
⟨review-dir⟩/verification/planning/VPLAN⟨shard⟩.scope.tsv. Do not issue
verdicts or inspect another planner shard.

Inputs: the scope TSV, its selected canonical candidate packet, fresh
indexes/candidates.tsv fingerprint metadata, plan.md, and the verification
reference sections. Verify all exact files through input-manifest.tsv.

ID allocation: use only the reserved inclusive interval V⟨start⟩..V⟨end⟩
from verification/planning/index.tsv. Assign batch IDs monotonically; record
unused reserved IDs. Never reuse an earlier/delta batch ID.

Procedure: execute Verification Planner steps 1–3 for this scope. Mechanically
co-located duplicate-affinity groups remain together. Account every scoped
candidate exactly once as a batch member or merge proposal; a merge names a
survivor that this planning universe schedules. Write complete skeptic briefs
with Generated Common Headers. Record each brief's manifest rows in your shard
deliverable; never write the root input-manifest.tsv — the exact collector
merges shard manifest rows atomically.

Deliverable: immutable
⟨review-dir⟩/verification/planning/VPLAN⟨shard⟩.md containing merge rows,
batch rows, generated brief paths, scoped candidate IDs, used/unused reserved
V IDs, and source fingerprints. Do not write verification/batches.md.

Return: one line — shard, scoped/accounted counts, used/unused V interval,
brief paths, output path, complete/partial with exact remainder.
```
