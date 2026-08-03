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

## Brief — Verification Planner (Phase 5)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: plan verification; do not issue verdicts yourself.

Inputs: ⟨review-dir⟩/indexes/candidates.tsv with its fresh
indexes/manifest.json fingerprint, ⟨review-dir⟩/collection.md, and
⟨review-dir⟩/plan.md. Read the compact candidate index first and extract each
full candidate row from its indexed artifact/anchor only when assigning it.
In delta mode, filter the index to exactly the explicitly named reopened-round
IDs. Compliance matrices and unrelated ledger prose are not inputs.

Procedure: read
⟨skill-dir⟩/references/worker/verification-and-fixes/verifying-candidate-findings.md
and
⟨skill-dir⟩/references/worker/verification-and-fixes/skeptic-verdicts.md.
In delta mode, preserve all prior batch
files and process exactly the supplied reopened-round IDs; ordinary candidate
rows are context and must not be scheduled again. Then:
1. Identify duplicate candidate rows across threads; record proposed
   merges as dispositions ("AL-1 merge-into EPW-2: same trigger, invariant,
   and outcome; duplicate evidence at path:line") in
   verification/batches.md. Never delete or edit a row. A merge candidate is
   accounted without an independent verdict only if reconciliation later
   validates equivalence and cites the survivor's verdict; otherwise it must
   be scheduled.
2. Validate each candidate's descriptor row. Preserve every semantic field
   and typed obligation in the inline packet; reject a plan that omits a
   class-required obligation.
3. Group every remaining candidate into skeptic batches, sized by trace
   cost rather than row count: a serious candidate whose refutation needs
   caller sweeps or interleaving analysis gets its own batch (or shares
   with 1–2 closely related rows); mid-weight candidates ~3–5 per batch;
   only cheap/cosmetic rows (naming, punctuation, description nits) go up
   to the 8-row cap. Within those bounds, group by code locality:
   candidates anchored in the same file or surface share a batch unless
   severity demands isolation — one code load then serves every verdict in
   the batch, while splitting same-file candidates across batches re-reads
   the same code in each one. Also cap each inline candidate packet at
   `candidate_packet_budget_bytes` from profile.json; split instead of
   truncating. Every candidate row from every thread appears in
   exactly one batch or one merge line.
4. Assign the next unused zero-padded IDs V001, V002, ... (including in delta
   mode) and write one skeptic brief per batch
   to ⟨review-dir⟩/briefs/V⟨batch⟩.md
   in the shape from
   ⟨skill-dir⟩/references/worker/templates/subagent-brief-verification-skeptic.md,
   prepending the Generated Common Header from
   ⟨skill-dir⟩/references/worker/templates/generated-common-header.md
   verbatim (directives, untrusted-input authority, append/retry, and
   partial semantics), with the batch's full candidate
   rows inline, verdict IDs V⟨batch⟩-⟨n⟩, deliverable file
   ⟨review-dir⟩/verification/V⟨batch⟩.md, and the anchor-table reference
   pointing at
   ⟨skill-dir⟩/references/worker/synthesis-and-output/severity-calibration.md.
   Also write ⟨review-dir⟩/packets/V⟨batch⟩.spec.tsv (shape in
   ⟨skill-dir⟩/references/worker/templates/scope-packet-spec-and-code-packets.md)
   with one diff row per file the batch's candidates cite, and list
   ⟨review-dir⟩/packets/V⟨batch⟩-code.md as an assigned input in the brief;
   the orchestrator materializes it before sealing. Register each
   brief and its exact candidate/reference/control inputs in input-manifest.tsv.

Deliverables: ⟨review-dir⟩/verification/batches.md and the briefs.

Return: the batch list only — batch id, brief path, candidate count — plus
the merge-proposal count.
```

If validated `indexes/candidates.tsv` has zero data rows, do not spawn this planner or
any skeptic. Use the canonical empty `verification/batches.md` shape from
templates.md mechanically, then regenerate indexes so `indexes/verdicts.tsv`
is a fresh zero-row view. Missing/incomplete source artifacts never qualify.
