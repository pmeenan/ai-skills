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

## Brief — Collection Exact-Coverage Collector (Phase 4.5, sharded)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: mechanically collect collection shards; make no review judgments.

Inputs: collection/index.tsv, plan.md, pin.md, fresh indexes/inventory.tsv
fingerprint, and every planned
collection/shards/CA*.md. Extract only IDs, declared thread coverage, gaps,
and observed-file lists.

Procedure: enforce the deterministic collection contract in templates.md:
every entry required by the active plan topology is present (both complete
generalist edge partitions plus required routing continuations for
`evidence-graph-v1`); every N/A
proof resolves to complete
trigger-index scope; every spawned thread and expected shard occurs exactly
once; no foreign thread; union observed files; exact diff against the pinned
changed-file list. Write
collection/uncovered-files.tsv. If it is nonempty, generate bounded
Generated-Common-Header floor-review briefs that own non-overlapping file
sets; those workers emit canonical ORC rows. After floor shards and repairs
complete, assemble collection.md without paraphrasing shard/ORC rows. Then run
the deterministic index builder to regenerate `indexes/candidates.tsv` and
`indexes/manifest.json`. A duplicate,
missing, malformed, or uncollected unit returns needs-repair and blocks
verification.

Deliverables: collection.md, collection/uncovered-files.tsv,
indexes/candidates.tsv plus its manifest fingerprint,
and floor-review briefs when required.

Return: one line — complete/needs-repair, exact thread coverage, uncovered
file count, ORC count, candidate count, and paths.
```
