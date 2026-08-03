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

## Brief — Draft Writer (Phase 7, only when bounded)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: write the review from the reconciled record.

Precondition: synthesis/index.md contains at most 12 cards and the measured
required input size is at most
profile.json:/context_budget/worker_input_budget_bytes. If either bound is exceeded, stop with `needs sharded
draft` and use the Finding Writer / Draft Assembly briefs below.

Inputs: ⟨review-dir⟩/reconciliation.md, ⟨review-dir⟩/synthesis/index.md,
the assigned ⟨review-dir⟩/synthesis/*.md cards, ⟨review-dir⟩/context.md, ⟨review-dir⟩/pin.md,
⟨review-dir⟩/directives.md, ⟨review-dir⟩/plan.md, ⟨review-dir⟩/ledger/PR.md
(if present), ⟨review-dir⟩/gerrit/unresolved-threads.json (extract only
card-referenced thread IDs with jq), and the
worktree for verbatim quotes. If ⟨review-dir⟩/challenge.md exists, address
every open item in its referenced shard files — fix or rebut each one
explicitly in Verification Notes. This is draft revision ⟨draft-revision⟩.

Procedure: read
⟨skill-dir⟩/references/synthesis-and-output.md — "Drafting The Review",
"Finding Format", "Severity Calibration", "Output Format", "Tone" (most of
the file, so use the canonical reference) — and
⟨skill-dir⟩/references/worker/verification-and-fixes/verdict-alignment-and-gerrit-output-rules.md,
then execute them.
Findings come from the reconciliation table's promotions; report record
contradictions instead of papering over them. You must exhaustively include
every single promoted finding without truncation, sampling, or omission so
the author receives all actionable feedback in a single review round. For
every synthesis item, write the exact `draft-parts/⟨item⟩.md` fragment in the
shape from
⟨skill-dir⟩/references/worker/templates/exact-output-fragments-draft-parts-and-draft-assembly.md;
for every finding also write
`gerrit-parts/⟨item⟩.md`. Include the canonical `Synthesis item` field in each
draft fragment, then assemble those bytes without editing them. Copy each
card's Suggested edit decision exactly. If applicable, put the same
replacement text in one fenced `suggestion` block in both fragments and target
the recorded contiguous range; if omitted, retain its specific reason in the
review fragment and do not invent a partial snippet.

Deliverables: ⟨review-dir⟩/draft-review.md,
⟨review-dir⟩/gerrit-comments.md, every exact per-item fragment,
⟨review-dir⟩/output-coverage.tsv with measured sizes/hashes, and completed
draft-dependent gate lines in reconciliation.md. The coverage item set must
exactly equal synthesis/index.md; each draft fragment occurs exactly once in
the review and each finding's Gerrit fragment occurs exactly once in the
Gerrit output. Do not mark Freshness yes: it remains
`pending-delivery` until the post-challenge Gerrit refresh. For revision >1,
first preserve the prior current outputs as draft-review.revision-⟨n-1⟩.md and
gerrit-comments.revision-⟨n-1⟩.md; never append a second review to the old file.
Start draft-review.md with `- Draft revision: ⟨draft-revision⟩` so the challenge
and delivery gate can mechanically prove which content they audited.

Return: one line — findings by severity, questions count, the verdict
sentence, gate status (all draft-dependent lines yes/no; Freshness must be
pending-delivery), file paths.
```
