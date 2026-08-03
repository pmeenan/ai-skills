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

## Brief — Reconciliation Shard (Phase 6, when indexed)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: reconcile only RB⟨batch⟩, the exact row IDs in
⟨review-dir⟩/reconciliation/shards/RB⟨batch⟩.scope.tsv. Do not draft review
text or disposition foreign rows.

Inputs: indexes/reconciliation.tsv plus exact indexed row bodies for the
assigned relationship closures. Candidate/verdict, merge-survivor,
root-cause-parent, and reopened-parent relationships are kept in one shard.
The measured required input is below profile.json's worker budget.

Procedure: apply the Reconciliation rules in
⟨skill-dir⟩/references/worker/synthesis-and-output/reconciliation-phase-6.md
to every assigned definition exactly once. Write one disposition per defining row and
one bounded evidence card per promoted finding/question. Finding cards carry
the root-cause Suggested edit decision and its exact replacement evidence or
specific omission reason. For each merge, emit the exact structured Merge
equivalence row (shape in
⟨skill-dir⟩/references/worker/templates/reconciliation-md-reconciliation-table-and-pre-output-gate.md);
shard scopes keep the merged row, survivor,
and verdict together. Cards obey
evidence_card_budget_bytes and split supporting material rather than truncate.

Deliverables: reconciliation/shards/RB⟨batch⟩.md and this shard's immutable
synthesis cards. Do not write canonical reconciliation.md or synthesis/index.md.

Return: one line — shard, definition/disposition counts, promoted/question
card IDs, missing/foreign IDs, paths, complete/partial with exact remainder.
```
