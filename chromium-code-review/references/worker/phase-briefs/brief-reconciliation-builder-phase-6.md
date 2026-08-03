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

## Brief — Reconciliation Builder (Phase 6)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: build the reconciliation table; do not draft review text. Use this
single-builder form only when the complete relationship closures measured in
indexes/reconciliation.tsv fit within profile.json's worker input
budget. Otherwise use the shard and exact-collector briefs below.

Inputs: mechanically generated
⟨review-dir⟩/indexes/reconciliation.tsv and its fresh
indexes/manifest.json fingerprint, plus
⟨review-dir⟩/verification/affinity.md,
⟨review-dir⟩/root-cause/batches.md, ⟨review-dir⟩/plan.md, and
gerrit/unresolved-threads.json. Use artifact/anchor fields in the definition
index to extract exact row bodies; do not ingest compliance matrices or whole
row-bearing files.

Procedure: read
⟨skill-dir⟩/references/worker/synthesis-and-output/reconciliation-phase-6.md
and execute it: enumerate every row ID from the files
fresh, fingerprinted index and give each exactly one disposition line. The
index builder has already distinguished defining IDs from incidental evidence
mentions. Use its source/anchor links to read only row bodies whose disposition
needs judgment; never ingest compliance-matrix prose. The indexed definition
set is the completeness authority: every defined ID must appear in your table.
Treat each root family as the promotion boundary: default to one promoted
finding per family. Multiple findings require a Root-family promotion
exception with cited evidence of distinct invariant owners or independently
bad outcomes.
Then copy the
Pre-Output Gate checklist (from
⟨skill-dir⟩/references/worker/synthesis-and-output/pre-output-gate.md)
verbatim to the bottom of reconciliation.md and
fill every line provable from the indexed files, marking draft-dependent lines
"pending draft" and Freshness `pending-delivery`. For each promoted finding
and owner question, write one bounded evidence card under
synthesis/⟨ROW-ID⟩.md using
⟨skill-dir⟩/references/worker/templates/synthesis-bounded-index-and-evidence-cards.md. Every finding card carries the
root-cause Suggested edit decision, exact range/selected lines/replacement
when applicable, or a specific omission reason; do not re-decide it during
drafting. A card is at most
`profile.json:/context_budget/evidence_card_budget_bytes`; if supporting
evidence exceeds that, split it into numbered parts referenced by
the root card. Write the complete bounded manifest to synthesis/index.md. Do
not copy all verdicts into one synthesis document. Assign each output item in
the disposition itself using exact `promoted → F<number>` or
`question → Q<number>` syntax. The index contains exactly those items, and
each row's `source rows` includes the disposition's defining row. A severity
downgrade remains a promotion at the calibrated severity; never emit a bare
`downgraded` disposition. Use only `merged → <survivor-row-id>` for a merge
and emit one matching `Merge equivalence` row (shape in
⟨skill-dir⟩/references/worker/templates/reconciliation-md-reconciliation-table-and-pre-output-gate.md)
with separately
cited trigger, invariant, outcome, and the survivor's exact verdict. The
survivor must be direct, verdict-owning, and verdict-consistently dispositioned;
artifact pointers must resolve to existing, nonempty review-relative files.
Reject the merge rather than inventing free-form equivalence prose.
Audit every verdict-bearing candidate independently: CONFIRMED cannot use a
free-form dismissed/duplicate disposition, UNPROVEN cannot disappear outside
Questions, and REFUTED names its verdict/citation.

Deliverables: ⟨review-dir⟩/reconciliation.md,
⟨review-dir⟩/synthesis/index.md, and ⟨review-dir⟩/synthesis/*.md cards.

Return: one line — total rows, unaccounted rows (list them if non-zero),
promoted findings count, questions count, open gate lines.
```
