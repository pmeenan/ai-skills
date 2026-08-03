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

## Brief — Reconciliation Exact-Coverage Collector (Phase 6, sharded)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: collect reconciliation shards mechanically; do not change a
disposition, severity, merge, or card.

Inputs: indexes/reconciliation.tsv, every RB*.scope.tsv and RB*.md, the
generated synthesis cards, plan.md, root-cause/batches.md, and compact gate
counts. Extract IDs and manifest fields only.

Procedure: prove every defining ID has exactly one disposition, no shard emits
a foreign/duplicate ID, and promoted/question dispositions have exactly one
card while all other dispositions have none. Require exactly one structured
Merge equivalence row for every merged disposition and no foreign equivalence
row. Concatenate dispositions in
definition-index order, build synthesis/index.md from measured card paths and
bytes, and fill the non-draft gate lines from compact evidence. Any mismatch
returns needs-repair; never choose among conflicting rows yourself.

Deliverables: reconciliation.md and synthesis/index.md. These canonical files
are emitted only after exact one-to-one coverage passes.

Return: one line — total/missing/duplicate/foreign definitions, promoted and
question card coverage, open gate lines, paths, complete/needs-repair.
```
