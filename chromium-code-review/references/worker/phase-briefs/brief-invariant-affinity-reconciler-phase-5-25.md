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

## Brief — Invariant Affinity Reconciler (Phase 5.25)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: perform one global semantic-affinity and consistency pass after every
skeptic batch has collected; do not issue verdicts or draft comments.

Inputs: fresh ⟨review-dir⟩/indexes/candidates.tsv, ⟨review-dir⟩/indexes/verdicts.tsv and manifest
fingerprints, ⟨review-dir⟩/verification/batches.md, and only the indexed Trace
closure / Verified affinity blocks needed to resolve conflicts.

Procedure:
1. Assign every CONFIRMED or UNPROVEN candidate/verdict pair to exactly one
   RF001, RF002, ... family by shared base/protocol, invariant owner, violated
   invariant, state transition, fix layer, and related symbols. Similar wording
   or file location alone is insufficient; separate skeptic batches do not
   prevent a shared family.
2. Run the six mandatory global checks from
   ⟨skill-dir⟩/references/worker/templates/verification-affinity-md-invariant-affinity-and-consistency-audit.md:
   contradictory
   assumptions, invariant-owner collisions, style-authority scope, lifetime
   operation owner, reachability termination, and repeated local fixes.
3. Write ⟨review-dir⟩/verification/affinity.md in the exact Root families and
   Consistency audit shapes. Cite code/artifacts for every result. If ownership
   remains genuinely unresolved, keep the related rows together and state the
   precise open question rather than splitting them into local tickets.
4. Rebuild indexes so every surviving verdict carries root_family. On very
   large inputs, descriptor extraction may be sharded, but final family
   assignment remains one global pass over all compact descriptors.

Deliverable: ⟨review-dir⟩/verification/affinity.md.

Return: one line — surviving pairs, root-family count, consistency conflicts,
and artifact path.
```
