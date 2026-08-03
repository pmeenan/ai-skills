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

## Brief — Synthesis Challenger (Phase 8, one per CH shard)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: adversarial audit of draft revision ⟨draft-revision⟩ for challenge
shard ⟨CH-batch⟩ only: ⟨card IDs, draft-section IDs, structural row IDs, or
global-index scope⟩. Change nothing.

Inputs: for a bounded single-shard draft, draft-review.md and
gerrit-comments.md plus output-coverage.tsv and the assigned exact per-item
fragments. For a sectioned draft, only the assigned immutable
draft-sections/*.md and matching gerrit-sections/*.md, the bounded global frame,
and their index rows/hashes — never the complete draft. Also use the scoped
synthesis cards, assigned reconciliation rows, plan.md, and the worktree for
spot-checking quoted lines. Structural shards mechanically extract only their
assigned rows and cited source rows. The global shard reads only the frame,
ordered headings/digests, verdict summary, and Gerrit target index.

Procedure: first verify every assigned section SHA-256 against
draft-sections/index.tsv and record the hashes audited. Then read
⟨skill-dir⟩/references/worker/verification-and-fixes/final-synthesis-pass.md
and audit the draft against its checklist. Read the draft and scoped
cards fully; audit assigned structural rows mechanically and read only
specific source rows a suspicious disposition cites. Hunt: unaccounted rows,
contradictions between findings and other caller paths or feature gates,
miscalibrated severities (check each against the anchor table in
⟨skill-dir⟩/references/worker/synthesis-and-output/severity-calibration.md),
verdict/finding
inconsistencies, gate lines answered untruthfully, and Gerrit-text rule
violations. Remember the restriction-feature inversion: silently degrading
to unrestricted behavior is a finding, not graceful fallback.

Deliverable: ⟨review-dir⟩/challenge/round-⟨round⟩/⟨CH-batch⟩.md — immutable shard file in
the Challenge shape: one row per issue with draft claim, record claim,
path:line/row evidence, required correction, and status.

Return: one line — issue count and the file path.
```
