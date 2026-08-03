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

## Brief — Root-Cause-Plan Exact Collector (Phase 5.5)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: collect RCPLAN shards mechanically; do not decide triggers, regroup
items, or alter planner dispositions.

Inputs: root-cause/planning/index.tsv, every planned RCPLAN*.scope.tsv and
RCPLAN*.md, fresh index fingerprints, and generated challenger brief paths.
Verify exact files through input-manifest.tsv if this contract runs in a worker
wrapper.

Procedure: require non-overlapping trigger scopes whose union exactly equals
the derived full/delta trigger universe. Require one Trigger Accounting row per
trigger; disjoint reserved RC intervals after existing IDs; every emitted RC
ID inside its owner interval and globally unique; and every scheduled item in
exactly one batch with a present manifested brief. Reject missing, duplicate,
foreign, stale, or out-of-range data.

Deliverable: canonical root-cause/batches.md assembled in numeric RC order
without semantic edits, and the shard-recorded manifest rows merged into the
root input-manifest.tsv via one atomic rewrite. Preserve immutable shard
results and unused reserved IDs in planning/index.tsv.

Return: one line — universe/accounted/scheduled counts, coverage/interval/
brief errors, canonical path, complete/needs-repair.
```
