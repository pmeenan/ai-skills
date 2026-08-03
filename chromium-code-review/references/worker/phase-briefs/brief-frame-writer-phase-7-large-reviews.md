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

## Brief — Frame Writer (Phase 7, large reviews)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: draft non-finding framing for revision ⟨draft-revision⟩; do not draft or
re-adjudicate individual findings/questions.

Inputs: synthesis/index.md and reconciliation disposition counts, context.md, pin.md,
directives.md, plan.md, orchestration.tsv, ledger/PR.md if present, and
root-cause/batches.md summary. Extract only compact outcome fields.

Deliverable: draft-parts/FRAME.md with High-Level Summary, Prior Review
Follow-Up, cited Positives, Verification Notes, Next Steps, verdict sentence,
and the complete ordered card-part list. The list must name every card in
synthesis/index.md with no omission; a missing card part is a truncation
defect, not an editorial choice. Apply verdict alignment. Freshness remains
pending-delivery.

Return: one line — verdict sentence, ordered part count, path.
```
