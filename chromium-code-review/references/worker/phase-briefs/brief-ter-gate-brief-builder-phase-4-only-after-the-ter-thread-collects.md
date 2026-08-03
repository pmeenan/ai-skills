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

## Brief — TER Gate-Brief Builder (Phase 4, only after the TER thread collects)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).
Work unit `VTERB`, `depends_on` the TER work unit. The orchestrator cannot
read TER ledgers, so this worker turns them into a manifest-complete gate
brief.

```text
Scope: generate the TER gate skeptic's brief; perform no equivalence
analysis and issue no verdicts.

Inputs: ⟨review-dir⟩/ledger/TER.md (and each explicit TER shard ledger
path).

Procedure: read the Transformation classes, Residue, and difference-table
sections. Enumerate as exact absolute paths: every TER ledger file and
every scratch transcript the ledger cites (transcripts live under
⟨review-dir⟩/scratch/TER/ and are cited review-relative; resolve them
against the review directory — a citation you cannot resolve to an
existing file is an error to report, not to skip). Fill the shape in
⟨skill-dir⟩/references/worker/templates/subagent-brief-ter-gate-skeptic.md
verbatim, prepending the Generated Common Header from
⟨skill-dir⟩/references/worker/templates/generated-common-header.md (work ID
VTER, tier frontier), with those enumerated inputs — never a glob.

Deliverables:
- ⟨review-dir⟩/briefs/VTER.md — the complete gate brief.
- ⟨review-dir⟩/briefs/VTER.manifest-fragment.tsv — input-manifest rows for
  work_id VTER attempt 1: the mandatory brief self-row for briefs/VTER.md
  itself, plus one row per enumerated input, each with exact bytes and
  SHA-256.

Return: one line — class count, input count, both paths.
```

The orchestrator then merges the fragment into root `input-manifest.tsv`
atomically, records the `VTER` work unit (`frontier`, `depends_on` VTERB,
artifact `verification/VTER.md`), and spawns the gate skeptic with the
standard "read and execute the brief at ⟨path⟩" prompt.
