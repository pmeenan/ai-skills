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
Scope: build the graph-driven thread plan and write every spawned discovery brief.

Inputs: ⟨review-dir⟩/pin.md, ⟨review-dir⟩/directives.md,
⟨review-dir⟩/profile.json, ⟨review-dir⟩/context.md, and
⟨review-dir⟩/indexes/inventory.tsv, `indexes/topology.tsv`,
`indexes/specialist-priors.tsv`, plus fresh fingerprints in
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
statuses. Ambiguous specialist evidence uses the two-pass likelihood contract
below; it never becomes an unsupported not-applicable status.

For `evidence-graph-v1`, first plan the two passes `Generalist Semantic And
State Discovery` and `Generalist Adversarial And Integration Discovery`. Use
one `graph:all-inventory-edges` row per pass only when it fits; otherwise give
both passes the same connected-component/budget shards, with every edge
assigned exactly once per pass. Every generalist shard emits `Specialist
escalation assessments` for all ten specialist lenses over its exact edge
slice, using low/medium/high plus cited signals and counterevidence. Rate the
residual chance that a full sweep will discover additional specialist edges,
not the mere presence of specialist-flavored constructs. One isolated local
construct with closed ownership/uses/exits can be low. The
semantic/state and adversarial/integration passes decide independently. After
every generalist-shard ledger exists, rebuild topology and specialist priors,
then
append `## Graph routing continuation — PLAN attempt ⟨N⟩`; each row must cite
`graph:<edge-id(s)>`. For specialist lenses, a `<PREFIX> hard` trigger or high from
either pass selects `specialist:full`; medium from both selects
`specialist:full`; exactly one medium selects `specialist:probe` by default
(full is allowed). Two lows with affirmative counterevidence add no
likelihood-driven row. Other catalog lenses remain driven by an
unresolved/disputed edge, candidate obligation, or required graph split. Do
not enumerate absent catalog lenses in the plan. If inventory produced zero
edges, plan one unsharded `graph:none` row per pass. Each still emits all ten
assessments as `low` with cited counterevidence; any medium/high judgment means
inventory must first add the missing edge.

Residue mode (round two, only after the TER gate ran): read the TER
ledger and verification/VTER.md (when present). Preserve the collected plan
prefix and append exactly `## Round-two residue continuation — PLAN attempt
⟨attempt⟩` with the exact ordered columns `roster entry | scope | status |
tier | batch | subagent | outcome`; never rewrite the original rows or append
a second ordinary roster table. Transition each
`deferred — pending TER gate (round two)` row to `spawn` with an exact
concrete scope copied into the brief (never "see the TER ledger"), and
begin each residue-scoped row's scope cell with `residue(TC⟨ids⟩): ` naming
the PROVEN classes it relies on — the validator rejects residue scoping
that cites a class without a PROVEN gate verdict. Plan REJECTED or
UNPROVEN classes as ordinary full review, and register the new briefs'
now-existing inputs in the manifest. Cross-site closure recipes (FPM, ACS,
per-surface invariants over unchanged callers) keep their full scope
regardless. An unsharded deferred row may become distinct numbered shard rows;
otherwise preserve the earlier shard number. Do not mix sharded and unsharded
continuation rows for one roster entry, and do not target a row already
transitioned by an earlier attempt.

Proof-repair mode (only for a collected non-deferred not-applicable row):
preserve the collected plan prefix and append exactly `## Plan repair
continuation — PLAN attempt ⟨attempt⟩` with the exact ordered columns `roster
entry | expected status | scope | status | tier | batch | evidence`. Use the
current effective row's stable roster identity and exact status as the guard.
Either supply a corrected exact trigger-absence proof while preserving scope,
tier, and batch, or transition to `spawn` with concrete scope, tier, and batch.
Never use this form for a deferred row or to change identity, subagent, or
outcome. The two continuation heading kinds share one increasing attempt
sequence; any ambiguous, duplicate, stale, or unsupported target blocks the
whole repair table.

Deliverables:
- ⟨review-dir⟩/plan.md — two initial generalist passes (sharded when required) plus append-only graph-routed rows, status `spawn` or
  `not applicable — trigger absence proved by ⟨T IDs⟩`, priority batch assignments, in
  the shape from
  ⟨skill-dir⟩/references/worker/templates/plan-md-thread-plan-roster.md. When Transformation
  Equivalence And Residue is spawned, bulk-scoped threads become
  `deferred — pending TER gate (round two)` rows with no briefs yet. Do
  NOT write a gate brief: the orchestrator generates the TER Gate Skeptic
  from its phase brief after the TER ledger exists, so the brief's inputs
  are complete and hashable at generation time. In residue mode, the
  deliverable is the append-only round-two continuation table specified
  above; raw earlier rows remain audit history and the effective plan contains
  only their transitioned replacements. In proof-repair mode, the deliverable
  is the separate append-only Plan repair continuation table specified above.
- ⟨review-dir⟩/briefs/⟨THREAD⟩.md — one self-contained brief per spawn
  row, generated mechanically with `python3 ⟨skill-dir⟩/scripts/build-discovery-brief.py ⟨review-dir⟩ --work-id ⟨THREAD⟩ --entry "⟨roster entry⟩" --procedure "⟨procedure path⟩" [--pathspec "⟨pathspec⟩"]` instead of hand-composing scripts or markdown. Use the shapes in
  ⟨skill-dir⟩/references/worker/templates/generated-common-header.md and
  ⟨skill-dir⟩/references/worker/templates/subagent-brief-discovery-thread.md
  verbatim (including directives, untrusted-input authority,
  attempt/append-only amendments, full-payload fallback, and partial
  continuation semantics), absolute paths throughout, skill dir ⟨skill-dir⟩, review dir
  ⟨review-dir⟩, mechanical-leads script
  ⟨skill-dir⟩/scripts/mechanical-leads.sh.
- Each brief names exactly one roster entry and points its Procedure at the
  exact per-section worker reference file(s) for that entry from
  ⟨skill-dir⟩/references/worker/ — for `Generalist Semantic And State Discovery`, point Procedure at `worker/discovery-checklists/state-persistence-and-cache.md` (or the primary matching checklist file under worker/discovery-checklists/); for `Generalist Adversarial And Integration Discovery`, point Procedure at `worker/discovery-checklists/integration-and-feature-control.md` (or the primary matching checklist file under worker/discovery-checklists/); recipe threads name the recipe's file plus
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
- Do not edit orchestration.tsv or input-manifest.tsv; the orchestrator seals and registers each generated brief after collection before spawning.
- Priority scheduling batches use D01, D02, ...; never an unqualified number.

Return: the spawn list only — one line per thread: name, brief path,
D-batch ID — plus the proved-not-applicable count. Reserve `unreviewed` for
triggered work that later terminates or remains incomplete; never use it for
proved trigger absence.
```
