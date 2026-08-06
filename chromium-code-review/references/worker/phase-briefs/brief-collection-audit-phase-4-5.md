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

## Brief — Collection Audit (Phase 4.5)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: audit discovery collection; do not re-review the CL. Use this
single-worker form only when all required ledgers/briefs fit within
profile.json's worker input budget. Otherwise use the shard and
deterministic-collector briefs below.

Inputs: ⟨review-dir⟩/plan.md, ⟨review-dir⟩/ledger/*.md,
⟨review-dir⟩/pin.md (changed-file list), ⟨review-dir⟩/briefs/*.md.
Also use the fresh `indexes/inventory.tsv` fingerprint and extract only the
trigger rows/blocks cited by plan statuses.
Work ledger-by-ledger and lean on mechanical extraction — blank or
citation-free matrix cells, rows missing a `path:line`, and the per-file
location column are all greppable; read a ledger's full text only when a
mechanical hit needs judgment. For the per-file floor, extract every
location column across all ledgers and diff that set against pin.md's file
list instead of holding all ledgers in context.

Procedure and checks:
1. The plan covers every entry required by the active topology. For
   `evidence-graph-v1`, both generalist passes cover the same complete edge
   partition (or both use `graph:none`) and every required graph-routing
   continuation is present.
   Every not-applicable row cites
   trigger-inventory IDs whose evidence covers every deterministic signal for
   that roster entry, whose `surface` associates the ID with that exact row,
   and whose `discovery triggers` says exactly `<PREFIX> absent`; unsupported,
   positive-trigger, unrelated-ID, or grouped catch-all absence proofs are
   gaps, and any matched or ambiguous trigger requires a spawned row. Accept
   monolithic `T<n>` and sharded `I<shard>-T<n>` IDs.
2. Every plan row with status spawn has a ledger file whose compliance
   matrix covers its brief's scope, with no blank rows and no
   citation-free PASS — an answer without a path:line citation is
   unanswered (if N/A, provide the primary file path:line).
3. Any anomaly recorded inside a matrix answer (success-shaped return
   after failure cleanup, duplicated cleanup, skipped check, unawaited
   write) has a corresponding candidate row; if a thread adjudicated one
   benign inline without a row, flag it as a gap.
4. Per-file floor: every changed file in pin.md (including headers, tests, and build files) has at least one explicit ledger
   row. For files with none, read the file's diff yourself and append an
   explicit ORC-⟨n⟩ clean-or-candidate row to ⟨review-dir⟩/collection.md
   in the Per-File Floor shape from
   ⟨skill-dir⟩/references/worker/templates/per-file-floor-rows.md — never a
   silent omission.

Deliverable: ⟨review-dir⟩/collection.md — audit verdict per thread, your
ORC rows, and a gap list naming the exact matrix rows or trace units to repair.
For every gap, also write a narrow attempt-numbered repair brief under
briefs/repairs/ using the Generated Common Header, naming only the missing
matrix rows, IDs, files, or trace units and preserving the canonical artifact.
Never request a rerun of already completed scope.

Return: one line — "complete" or the gap list, plus ORC row count and the
file path.
```
