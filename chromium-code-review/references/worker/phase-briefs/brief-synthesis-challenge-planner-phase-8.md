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

## Brief — Synthesis Challenge Planner (Phase 8)

Tier: `standard` (Model Tiers in `references/scaling-and-indexes.md`).

If all content and structural coverage fits one budgeted shard, do not spawn
this planner or a collector agent. Render the one-row round index and
Generated-Common-Header challenger brief mechanically, spawn the independent
challenger, then finalize the index deterministically. The challenger and
fresh-round requirement remain mandatory.

```text
Scope: shard the adversarial audit; do not audit the content yourself.

Inputs: synthesis/index.md, reconciliation.md, output-coverage.tsv,
draft-review.md, and gerrit-comments.md for challenge round ⟨round⟩. When
draft-sections/index.tsv exists, use it as the content-routing authority and
verify its revision, byte counts, hashes, cards, and rows before planning.

Procedure: assign CH001, CH002, ... content shards whose assigned cards,
draft/Gerrit sections, frame, and required references fit profile.json's worker
input budget (six cards is only a starting heuristic). Add bounded structural
shards (200 rows is only a starting heuristic) for accounting/gate checks.
Exactly one shard whose scope starts `global-consistency` owns the bounded frame, ordered section
headings/digests, verdict summary, and Gerrit target index; it does not read
every large-draft section body. Write one generated
brief per shard using the Common Header and Synthesis Challenger brief below.
Register every generated challenger brief and its exact section/frame/card/
control inputs in input-manifest.tsv before any shard spawns.
Every finding, question, and structural row is in exactly one shard; global
verdict/Gerrit consistency checks are explicitly assigned to CH001.

Deliverable: challenge/round-⟨round⟩/index.md. Record
`- Draft revision: ⟨draft-revision⟩`, then a table with exact columns `shard`,
`scope`, `brief`, `artifact`, `expected coverage`, and `issues`. The planner
fills all but `issues`; the collector fills `issues` without changing coverage.
`expected coverage` is a comma-separated, range-free list of exact
`card:⟨synthesis item⟩`, `row:⟨reconciliation row ID⟩`, and, for sectioned
drafts, `section:⟨section ID⟩` tokens plus exactly one
`global:consistency` token. Across the table, every synthesis item,
reconciliation row, content section, and global check appears exactly once.
The global shard receives digests/index metadata without claiming another
shard's section token.
Return: one line — shard list and coverage totals.
```
