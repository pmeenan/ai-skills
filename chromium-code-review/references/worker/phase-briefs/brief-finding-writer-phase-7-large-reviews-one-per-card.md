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

## Brief — Finding Writer (Phase 7, large reviews, one per card)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: draft only card ⟨card-ID⟩ for draft revision ⟨draft-revision⟩. Do not
read other cards or reopen the corpus.

Inputs: synthesis/⟨card-path⟩.md, directives.md, pin.md, and the worktree only
to recheck this card's quoted line/location. Input must be at most
profile.json:/context_budget/evidence_card_budget_bytes; an
oversized card is returned for splitting.

Procedure: read, under ⟨skill-dir⟩/references/worker/synthesis-and-output/,
the files finding-format.md, severity-calibration.md, output-format.md, and
tone.md, plus
⟨skill-dir⟩/references/worker/verification-and-fixes/verdict-alignment-and-gerrit-output-rules.md. Draft the
finding or question exactly from the reconciled evidence; do not re-adjudicate.
Include the exact `Synthesis item: ⟨card-ID⟩` field and internal source-row
trail in the review fragment. For a finding, copy its Suggested edit decision:
an applicable edit has the identical fenced `suggestion` replacement in the
review and Gerrit fragments at the card's exact target range; an omitted edit
keeps the card's specific reason and has no suggestion block.

Deliverables: exact final-output bytes in
`draft-parts/⟨card-ID⟩.md`; for a finding, exact target/comment bytes in
`gerrit-parts/⟨card-ID⟩.md`; and one measured
`output-coverage/⟨card-ID⟩.tsv` data row in the schema from
⟨skill-dir⟩/references/worker/templates/exact-output-fragments-draft-parts-and-draft-assembly.md. A question
uses `-` for all Gerrit fields. Do not add wrappers or metadata that should not
appear in the final output.

Return: one line — card ID, destination/ordering key, output path, complete
or explicit remaining.
```
