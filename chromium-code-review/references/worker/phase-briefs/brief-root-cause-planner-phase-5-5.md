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

## Brief — Root-Cause Planner (Phase 5.5)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: identify all root-cause triggers and plan bounded RC batches; do not
perform root-cause analysis yourself.

Inputs: ⟨review-dir⟩/indexes/verdicts.tsv,
⟨review-dir⟩/verification/batches.md,
⟨review-dir⟩/verification/affinity.md,
⟨review-dir⟩/indexes/candidates.tsv, and
⟨review-dir⟩/indexes/inventory.tsv, all covered by the current
indexes/manifest.json fingerprints. Read these compact indexes first. Extract
only the indexed verdict/candidate/inventory blocks for possible triggers;
do not ingest every verdict, ledger, or inventory file.

Procedure: read
⟨skill-dir⟩/references/worker/verification-and-fixes/root-cause-trigger-planning.md
and
⟨skill-dir⟩/references/worker/verification-and-fixes/root-cause-layering-and-fix-optimality.md.
Create one Trigger Accounting row for every CONFIRMED or UNPROVEN verdict,
every candidate/finding containing a proposed fix, and every inventory scope
marked root-cause required. Apply every trigger named
there; do not rely on the orchestrator's status lines. Schedule each root
family as one indivisible semantic unit containing every member
candidate/verdict ID. Never split a family by prior batch, method, or discovery
thread; keep unrelated families separate. Assign the next unused IDs RC001,
RC002, .... In delta mode,
process only the explicitly supplied reopened-round verdict IDs and preserve
all prior batch files.

Deliverables:
- ⟨review-dir⟩/root-cause/batches.md in the exact shape from
  ⟨skill-dir⟩/references/worker/templates/root-cause-plan-root-cause-rows-and-reopened-rows.md.
- briefs/RC⟨batch⟩.md per scheduled batch, using the Generated
  Common Header verbatim and embedding the exact candidate/verdict rows;
  register each brief and exact inputs in input-manifest.tsv.

Return: one line — trigger count, scheduled count, proved-not-applicable count, and
the RC batch list (ID, brief, candidate count).
```

If the fresh verdict index proves zero verdict rows and the fresh inventory
index proves no root-cause-required scope, do not
spawn this planner or a challenger. Write the canonical empty
`root-cause/batches.md` shape from templates.md mechanically. Any unknown or
malformed value disqualifies the fast path.
