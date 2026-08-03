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

## Brief — Root-Cause Challenger (Phase 5.5, one per batch)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: root-cause, layering, and fix optimality for batch RC⟨batch⟩ ONLY —
these complete root families or change-level inventory scopes: ⟨IDs, e.g.
RF001 (EPW-2/V001-1, AL-4/V002-2), T001⟩. Other batches' items are context, not
work items.

Inputs: the listed verdict rows in ⟨review-dir⟩/verification/*.md, the
candidate rows they reference in ⟨review-dir⟩/ledger/*.md, any listed
inventory trigger-scope rows, and ⟨review-dir⟩/context.md.

Procedure: read
⟨skill-dir⟩/references/worker/verification-and-fixes/root-cause-layering-and-fix-optimality.md
and execute it fully — every layer
walk and drill — for each complete family in your batch. Produce a
State × Method matrix when protocol state is involved, explain excluded
nearby methods, select one fix layer and comment count for the family, and
make the required Suggested-edit decision. For an applicable edit, re-read the
pinned changed-side range and record its verbatim selected lines plus the exact
replacement in the canonical multiline RC-row fields from the root-cause shape
file named below;
otherwise record the concrete eligibility condition that fails. Put only
`applicable — RC⟨batch⟩-⟨n⟩` in the root-family table cell; the RC row owns
the lossless code.

Deliverables:
- ⟨review-dir⟩/root-cause/RC⟨batch⟩.md — RC⟨batch⟩-⟨n⟩ rows in the shape
  from
  ⟨skill-dir⟩/references/worker/templates/root-cause-plan-root-cause-rows-and-reopened-rows.md:
  better-owner hypotheses,
  callsite gaps, duplicated-state risks, stale-fix risks, and
  refutations, each with path:line evidence.
- If your pass opens new candidates, write them first as canonical rows in
  ⟨review-dir⟩/ledger/reopened/round-⟨round⟩-RC⟨batch⟩.md with IDs
  R⟨round⟩-RC⟨batch⟩-1, -2, ... and the Reopened Candidates shape from the
  same root-cause shape file. A status-line-only or brief-only candidate does
  not exist.
- When a reopened row needs a named discovery recipe, write a bounded
  Generated Common Header discovery brief with exact scope; its worker appends
  evidence/amendments or additional canonical rows to the same round, without
  replacing parent rows. Do not write a skeptic brief. After collection, the
  Verification Planner runs in delta mode over exactly the round IDs, then the
  Root-Cause Planner runs in delta mode over their verdicts.

Return: one line — candidates checked, RC rows written, canonical reopened row
IDs, requested discovery brief paths if any, file paths, `complete` or explicit
remaining.
```
