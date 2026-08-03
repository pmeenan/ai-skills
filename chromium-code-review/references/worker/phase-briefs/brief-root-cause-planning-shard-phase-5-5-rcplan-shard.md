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

## Brief — Root-Cause-Planning Shard (Phase 5.5, RCPLAN⟨shard⟩)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

Use this map/collect form when the exact trigger universe and canonical packets
exceed one worker's input budget. In delta mode the universe is exactly the
named round's verdict triggers plus new trigger-scope IDs canonicalized for
that round, never original scopes already processed.

```text
Scope: plan root-cause work only for the exact trigger IDs in
⟨review-dir⟩/root-cause/planning/RCPLAN⟨shard⟩.scope.tsv. Do not perform
root-cause analysis or inspect another planner shard.

Inputs: the scope TSV, selected candidate/verdict/inventory packets, fresh
indexes/{verdicts,candidates,inventory}.tsv fingerprint metadata, and the
root-cause trigger reference sections. Verify exact files through
input-manifest.tsv.

ID allocation: use only reserved inclusive interval RC⟨start⟩..RC⟨end⟩
from root-cause/planning/index.tsv. Assign batch IDs monotonically, record
unused IDs, and never reuse an earlier/delta batch ID.

Procedure: apply every Root-Cause Trigger Planning rule to every scoped
trigger. Write one Trigger Accounting disposition per trigger, group scheduled
items only with related trace-sized work, and generate complete challenger
briefs with Generated Common Headers. Record each brief's manifest rows in
your shard deliverable; never write the root input-manifest.tsv — the exact
collector merges shard manifest rows atomically.

Deliverable: immutable
⟨review-dir⟩/root-cause/planning/RCPLAN⟨shard⟩.md containing trigger rows,
batch rows, generated brief paths, scoped trigger IDs, used/unused RC interval,
and source fingerprints. Do not write root-cause/batches.md.

Return: one line — shard, scoped/accounted/scheduled counts, used/unused RC
interval, brief paths, output path, complete/partial with exact remainder.
```
