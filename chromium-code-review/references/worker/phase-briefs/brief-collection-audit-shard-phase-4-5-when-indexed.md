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

## Brief — Collection-Audit Shard (Phase 4.5, when indexed)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: audit only collection shard CA⟨batch⟩ from
⟨review-dir⟩/collection/index.tsv. Do not inspect another shard and do not
perform the global per-file-floor diff.

Inputs: the shard's exact plan rows, briefs, whole ledger artifacts, and the
compact inventory-index rows plus canonical trigger blocks cited by those plan
rows. Their measured total is below profile.json's worker input budget.

Procedure: apply checks 1–3 from the Collection Audit brief. Mechanically
extract candidate location paths and write a sorted Observed Files section.
For every gap, write only the narrow repair brief owned by this shard.

Deliverable: ⟨review-dir⟩/collection/shards/CA⟨batch⟩.md with Thread Audit,
Observed Files, and Gaps in the shapes from
⟨skill-dir⟩/references/worker/templates/collection-md-collection-audit.md. Do not write ORC rows.

Return: one line — shard, audited-thread count, gap count, observed-file
count, path, and complete/partial with exact remainder.
```
