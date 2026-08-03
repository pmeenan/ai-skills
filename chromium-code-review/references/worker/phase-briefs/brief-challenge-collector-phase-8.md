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

## Brief — Challenge Collector (Phase 8)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).

Canonical path: run
`python3 ⟨skill-dir⟩/scripts/collect-challenge-round.py ⟨review-dir⟩ ⟨round⟩`
directly once every planned shard of the round has returned. It verifies the
shard artifacts, fills the round index's `issues` column, appends the round
result, and writes the `challenge.md` pointer; a nonzero exit is
`needs-repair` for the named shards. Do not spawn an agent merely to execute
this deterministic collection.

The brief below is a degraded wrapper only when the helper cannot execute; it
must preserve the helper's exact output and exit semantics.

```text
Scope: collect challenge shards for draft revision ⟨draft-revision⟩; do not
re-adjudicate them.

Inputs: challenge/round-⟨round⟩/index.md and every planned CH*.md in that
round directory. Verify every
planned shard exists and mechanically extract issue IDs/counts.

Deliverable: finalize the immutable round index with every shard, scope, issue
ID, missing shard, and result; write challenge.md as a compact pointer/summary
to `challenge/round-⟨round⟩/index.md`. Never overwrite an older round.

Return: one line — complete/incomplete, total open issues, missing shards,
path. Any draft revision requires an entirely new challenge plan, fresh shard
IDs, and a new collection pass; addressing old issues alone is not sufficient.
```
