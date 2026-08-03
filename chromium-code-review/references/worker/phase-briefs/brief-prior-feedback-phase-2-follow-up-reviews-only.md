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

## Brief — Prior Feedback (Phase 2, follow-up reviews only)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: reconcile prior review feedback against the pinned patchset.

Inputs: ⟨review-dir⟩/prior-feedback-input.md (the prior review text),
⟨review-dir⟩/gerrit/unresolved-threads.json (already normalized; extract
fields with jq rather than reading it whole),
⟨review-dir⟩/detail.json (extract prior patchset SHAs via jq from
ALL_REVISIONS; do not read it whole).

Procedure: read
⟨skill-dir⟩/references/worker/inventory-and-planning/pass-2-prior-feedback-reconciliation.md
and execute it. Derive the prior reviewed revision under the Baseline
Derivation contract in
⟨skill-dir⟩/references/worker/templates/ledger-pr-md-prior-feedback-reconciliation.md:
prefer an explicit PS/SHA in the supplied
feedback; otherwise map `revisions[*]._number` and `created` plus review/message
timestamps and choose the newest revision no later than the prior-review
timestamp. Never assume the baseline is the pinned patchset minus one. If derivation is ambiguous, record baseline
unknown and do not invent `introduced-in-PS...` origin. Diff explicit SHAs;
do not create a second worktree: fetch only an explicit ref if an object is
missing and compare explicit SHAs through the repository object database.
Never use FETCH_HEAD or change the pinned worktree.

Deliverable: ⟨review-dir⟩/ledger/PR.md — Baseline Derivation, Gerrit Thread
Normalization, one PR-⟨n⟩ Prior-Feedback row per prior finding and unresolved
thread, plus Candidate rows only for partial/open items and one Candidate
descriptors row per such item, in the shape from
⟨skill-dir⟩/references/worker/templates/ledger-pr-md-prior-feedback-reconciliation.md.

Return: one line — counts by resolution (fixed / partial / open / obsolete
/ superseded) and the file path.
```
