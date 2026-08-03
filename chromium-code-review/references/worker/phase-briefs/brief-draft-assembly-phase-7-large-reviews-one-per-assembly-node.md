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

## Brief — Draft Assembly (Phase 7, large reviews, one per assembly node)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: assemble node ⟨node-ID⟩ for revision ⟨draft-revision⟩ from only these
explicit child paths: ⟨paths⟩. Never read ledgers, verdicts, root-cause files,
cards, or the worktree.

Precondition: at most 12 children and aggregate input at most
profile.json:/context_budget/worker_input_budget_bytes. If exceeded,
return `needs another assembly level`; never squeeze, summarize, or omit.

Procedure: order and join children, remove only exact repeated boilerplate,
and validate required headings/part IDs. Per-item fragment bytes are immutable:
do not alter, summarize, deduplicate, or omit them. The assembled
draft-review.md must contain every draft fragment exactly once and
gerrit-comments.md every finding's Gerrit fragment exactly once. A non-root
node writes
draft-assembly/⟨node-ID⟩.md. The root writes draft-review.md and
gerrit-comments.md and updates the draft-dependent gate lines, with Freshness
still pending-delivery. The root must include `FRAME.md` and start
draft-review.md with `- Draft revision: ⟨draft-revision⟩`. Append the node row
to draft-assembly/manifest.md. At the root, collect every per-item coverage row
into `output-coverage.tsv`, rejecting duplicate/missing/foreign items and
remeasuring every byte count/hash. If either root output exceeds the worker input
budget, also write bounded immutable draft/Gerrit fragments and
`draft-sections/index.tsv` using the exact dual-path byte/hash schema in
⟨skill-dir⟩/references/worker/templates/exact-output-fragments-draft-parts-and-draft-assembly.md. The root outputs must byte-equal the fragments concatenated in
numeric `order` with no inserted separator/newline/normalization; each fragment
owns its trailing newline. Represent an empty destination explicitly instead
of dropping it.

Return: one line — node ID, child count/bytes, output path, missing/duplicate
part IDs, complete or needs another level.
```
