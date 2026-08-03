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

## Brief — Context (Phase 1, always separate from inventory when spawned)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

Only when `profile.json` sets `context_fast_path_eligible: true`, render the
empty-source `context.md` skeleton mechanically and skip this worker. Inventory
and the always-run holistic lens still audit description alignment and scope.
Any link, prior feedback, unresolved thread, or unknown profile evidence
requires the worker.

```text
Scope: bug/design/description alignment and scope relevance for the full CL.
Do not build the changed-surface inventory.

Procedure: read
⟨skill-dir⟩/references/worker/inventory-and-planning/gather-context-pass-1.md
and execute it against the pinned diff. Read the CL
description from ⟨review-dir⟩/pin.md; follow public bug links and design
docs it references. Bound external ingestion: distill each bug or design
doc into context.md rather than carrying its full text — for long bug
threads read the description plus the comments that state intent, scope
decisions, or repro details (skip CI/bot chatter); for large design docs
extract the sections the CL implements. Record what you skimmed vs read
fully so the draft writer can caveat bug-alignment claims.

Deliverable: ⟨review-dir⟩/context.md — Sources Consulted, Intended Behavior
And Scope, Description-To-Code Alignment, Scope Relevance, and Unknowns And
Caveats in the exact shape from
⟨skill-dir⟩/references/worker/templates/context-md.md.

Return: one line — sources consulted count, discrepancies count, unknowns
count, and the deliverable path.
```
