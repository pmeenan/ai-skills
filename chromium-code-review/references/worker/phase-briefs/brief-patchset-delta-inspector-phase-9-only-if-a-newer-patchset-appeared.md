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

## Brief — Patchset-Delta Inspector (Phase 9, only if a newer patchset appeared)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: assess patchset ⟨new-PS⟩, which appeared during the review of
patchset ⟨PS⟩.

Procedure: fetch the new revision ref by its explicit name and inspect it
through explicit-object Git commands without creating a worktree (never use
FETCH_HEAD or change the pinned worktree). Diff it against the reviewed
revision ⟨sha⟩. Classify the
delta: trivial (rebase/comment/format only, with no changed executable or
contract semantics) or material (behavior, new
files, changed logic). For material deltas, list the affected findings
(by row ID from ⟨review-dir⟩/reconciliation.md) and which roster threads'
scopes the delta touches. Do not amend old verdicts or claim they apply to
the new SHA: a material delta requires a newly pinned review directory and a
restart from Phase 1.

Deliverable: ⟨review-dir⟩/patchset-delta.md, recording the old PS/SHA,
new PS/SHA, exact file delta, classification, cited-line revalidation, and
inspection timestamp.

Return: one line — trivial or material, affected finding IDs, threads to
re-run, file path.
```
