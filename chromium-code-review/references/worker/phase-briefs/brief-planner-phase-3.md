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

## Brief — Planner (Phase 3)

Tier: `frontier` (Model Tiers in `references/scaling-and-indexes.md`).

```text
Scope: build the complete thread plan and write every discovery brief.

Inputs: ⟨review-dir⟩/pin.md, ⟨review-dir⟩/directives.md,
⟨review-dir⟩/profile.json, ⟨review-dir⟩/context.md, and
⟨review-dir⟩/indexes/inventory.tsv plus its fresh fingerprint in
indexes/manifest.json. Read the compact index first. Extract only
the indexed narrative blocks needed to resolve a triggered or ambiguous row;
do not ingest every inventory file.

Procedure: read
⟨skill-dir⟩/references/inventory-and-planning.md — "Pass 3", "The Roster",
"Plan-Construction Rules", and "Writing Discovery Briefs" — and execute
them. Read the Context Rules and every recipe trigger line in
⟨skill-dir⟩/references/deep-dive-recipes.md and
⟨skill-dir⟩/references/specialist-recipes.md. Skim the matched sections
of ⟨skill-dir⟩/references/discovery-checklists.md and
⟨skill-dir⟩/references/chromium-specialist-checklists.md before deciding
statuses. Ambiguous specialist evidence spawns the narrow row; it never
becomes an unsupported not-applicable status.

Residue mode (round two, only after the TER gate ran): read the TER
ledger and ⟨review-dir⟩/verification/VTER.md, convert each
`deferred — pending TER gate (round two)` row to `spawn` with an exact
concrete scope copied into the brief (never "see the TER ledger"), and
begin each residue-scoped row's scope cell with `residue(TC⟨ids⟩): ` naming
the PROVEN classes it relies on — the validator rejects residue scoping
that cites a class without a PROVEN gate verdict. Plan REJECTED or
UNPROVEN classes as ordinary full review, and register the new briefs'
now-existing inputs in the manifest. Cross-site closure recipes (FPM, ACS,
per-surface invariants over unchanged callers) keep their full scope
regardless.

Deliverables:
- ⟨review-dir⟩/plan.md — the full roster, one row per entry (or shard),
  status `spawn` or
  `not applicable — trigger absence proved by ⟨T IDs⟩`, priority batch assignments, in
  the shape from
  ⟨skill-dir⟩/references/worker/templates/plan-md-thread-plan-roster.md. When Transformation
  Equivalence And Residue is spawned, bulk-scoped threads become
  `deferred — pending TER gate (round two)` rows with no briefs yet. Do
  NOT write a gate brief: the orchestrator generates the TER Gate Skeptic
  from its phase brief after the TER ledger exists, so the brief's inputs
  are complete and hashable at generation time.
- ⟨review-dir⟩/briefs/⟨THREAD⟩.md — one self-contained brief per spawn
  row, using the shapes in
  ⟨skill-dir⟩/references/worker/templates/generated-common-header.md and
  ⟨skill-dir⟩/references/worker/templates/subagent-brief-discovery-thread.md
  verbatim (including directives, untrusted-input authority,
  attempt/append-only amendments, full-payload fallback, and partial
  continuation semantics), absolute paths throughout, skill dir ⟨skill-dir⟩, review dir
  ⟨review-dir⟩, mechanical-leads script
  ⟨skill-dir⟩/scripts/mechanical-leads.sh.
- Each brief names exactly one roster entry and points its Procedure at the
  exact per-section worker reference file(s) for that entry from
  ⟨skill-dir⟩/references/worker/ — recipe threads name the recipe's file plus
  context-rules.md under worker/deep-dive-recipes/; checklist sections name
  their file under worker/discovery-checklists/ plus
  per-surface-invariant-questions.md; specialist sections name their file
  under worker/chromium-specialist-checklists/; FPM, ACS, and TER name their
  file under worker/specialist-recipes/. Copy exact paths from each stem's
  index.md — sealing verifies the named files exist. Register each named
  section file as a reference input; do not assign whole reference monoliths
  when the entry's section files exist. Shard by the natural semantic units in
  inventory-and-planning.md before any input budget is exceeded.
- ⟨review-dir⟩/packets/⟨THREAD⟩.spec.tsv — one machine-readable scope spec
  per spawn row whose scope is a dense-hunk shard, spans multiple files, or
  shares files with other threads (a single-file full-diff scope may skip
  it), in the shape from
  ⟨skill-dir⟩/references/worker/templates/scope-packet-spec-and-code-packets.md:
  diff rows for the thread's exact pathspec (copy a dense shard's owned
  old/new intervals into the range columns) plus slice rows for
  declarations/contracts worth pre-cutting. List the packet path
  ⟨review-dir⟩/packets/⟨THREAD⟩-code.md as an `assigned` input in the
  brief — the orchestrator materializes it from your spec before sealing.
- Register every generated brief and all its exact inputs in root
  input-manifest.tsv before returning; no discovery brief may spawn first.
- Priority scheduling batches use D01, D02, ...; never an unqualified number.

Return: the spawn list only — one line per thread: name, brief path,
D-batch ID — plus the proved-not-applicable count. Reserve `unreviewed` for
triggered work that later terminates or remains incomplete; never use it for
proved trigger absence.
```
