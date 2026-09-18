# Execution Orchestration (Phases 4 to 6)

Discovery execution, collection audit, verification, root-cause analysis, and
reconciliation. The orchestrator loads this file when Phase 4 becomes runnable
and works from it through the end of Phase 6, then hands off to
`references/synthesis-orchestration.md` for Phases 7 to 9.

Everything the orchestrator needs for these phases is here; `SKILL.md` keeps the
standing rules that apply across all phases — the context budget, partial
returns and narrow repair, sealing, waiting on `await-workers.py`, and the
prohibition on reading helper source — and does not restate anything below.

## Phase 4 — Discovery Execution

**Wave width is a floor, not a ceiling: never spawn one agent while two or more
dependency-ready rows are queued.** Launch the whole dependency-ready set up to
available capacity, default eight. Spawn a planner and its first executor batch
together where the dependency allows it.

**Then block on `scripts/await-workers.py` until the wave returns.** Do not
poll, do not set timers, and do not end the turn.

  Measured mean worker latency is 49 minutes. Runs that launched waves of one or
  two spent most of their wall clock idle — 79% of one 17.9-hour run. The single
  run that launched eight at once collected seven of eight threads in 65
  minutes. Day-plus runs were queue-dominated: a three-child default against a
  30-thread plan left most of the clock waiting on scheduling, not analysis.

Runs of this skill show the same pattern across models: a single agent sustains
real depth on only one or two threads per pass — whichever grab its attention —
and everything else gets a shallow read. So discovery is never one agent.

**Spawn one subagent per spawned effective plan row, with the spawn prompt "Read
and execute the brief at ⟨absolute path to briefs/THREAD.md⟩. It defines your
pin, scope, procedure, deliverable, and rules." Never inline a brief's body into
the spawn prompt.** The two generalist passes are independent; their shards may
run in parallel, but every shard covers one pass's exact edge slice and the two
passes use the same partition. Collect all generalist shards, rebuild
`indexes/topology.tsv` and `indexes/specialist-priors.tsv`, then respawn the
Planner to append the graph-routing continuation before launching any targeted
lens. This fan-in is mandatory even when the next continuation is empty. The
targeted fan-out occurs only after their graph deltas and specialist priors are
indexed. Run threads in parallel where the harness allows, and record each
thread's subagent/task identifier in `plan.md`.

**Spawn every worker at its annotated model tier** — phase briefs carry a
`Tier:` line, `plan.md` rows carry a `tier` column, and skeptics, root-cause
challengers, and synthesis challengers are always `frontier` — per the Model
Tiers contract in `references/scaling-and-indexes.md`. Tiers are a floor; when
the harness cannot select per-subagent models or thinking levels, inherit the
session model and continue.

**Derive each wave from live harness capacity, never a hard-coded batch size.**
Reserve one slot for the orchestrator; launch at most `min(runnable rows,
available child slots)` from the highest-priority dependency-ready rows in
`orchestration.tsv`. If capacity cannot be queried, start with at most eight
children, reduce the wave after a capacity rejection, and refill a slot only
after collecting its prior task. Priority: teardown and error paths, boundary
arithmetic, cross-sequence handoffs, persisted formats, and reentrancy first;
renames and plumbing last. Overlap between threads is fine — redundant coverage
is how disjoint blind spots get closed.

**Discovery ends only when every planned thread has delivered its ledger file;
outstanding threads are blocking dependencies, not background noise.** Expect
the section threads to be slowest — they read the most — and to carry the most
findings. If a thread dies to a transient harness error (capacity limits, rate
limits, timeouts), mark its attempt retryable and follow the targeted
continuation and repair rule above; only when retries are exhausted record it in
`plan.md` and `progress.md` as "terminated — scope unreviewed". Never mark an
uncollected thread Completed. If you interrupt a thread deliberately, collect
its partial ledger file before killing it and record it as "interrupted —
partial".

**If the plan contains `deferred — pending TER gate (round two)` rows, or an
already collected not-applicable roster row cites the wrong absence proof, run
the matching procedure in `references/conditional-orchestration.md`.** Deferred
is transient: no deferred row may survive to the collection audit.

**Collect ledger files; never transcribe or compress them.** Collection is:
confirm the thread's `ledger/⟨THREAD⟩.md` exists and is non-trivial (`ls`,
`wc -l`), independently run
`⟨review-dir⟩/skill-snapshot/scripts/validate-worker-artifact.py` on it, and
only after a zero exit record the outcome (row count from the thread's status
message) in `plan.md` and `progress.md`. A nonzero exit is `needs-repair`, not
`complete`; return the exact diagnostics to the owning attempt while it still
owns a new artifact, or create a narrow amendment attempt for collected
prestate. Rows are carried forward by the files themselves under their own IDs.
Deduplication is a reconciliation-time disposition (`merged →
⟨survivor-row-id⟩` plus structured equivalence), never an orchestrator
pre-processing step; severity is judged in verification, not at collection.

## Phase 4.5 — Collection Audit

Spawn one bounded **Collection-Audit agent** or sharded auditors plus a
deterministic exact-coverage collector, as selected by the input budget. They
read every ledger file and check: each spawned thread's file is present and its
compliance matrix complete; no matrix row is a citation-free PASS; every changed
file has at least one ledger row, adding explicit `ORC` clean rows to
`collection.md` where none exists; and anomalies recorded in matrix answers were
emitted as candidate rows.

- Deliverable: `collection.md` (audit result, ORC per-file floor rows, gap
  list).
- Return: "complete" or a list of generated repair-brief paths. Each repair
  brief names only the missing compliance rows, citations, candidate amendments,
  files, or trace units and preserves the canonical ledger and IDs; do not
  respawn a whole discovery brief. Run those repairs, then re-run the audit.
  Verification does not start until the audit returns complete or every
  remaining gap is recorded as an unreviewed area.

Run `scripts/validate-review-dir.py ⟨review-dir⟩ --phase collection
--require-active-lease`; route each error through the targeted repair path and
rerun until it passes. Warnings are disclosed but do not impersonate
mechanically proven success. Then rebuild the compact indexes.

## Phase 5 — Verification

If fresh `indexes/candidates.tsv` proves zero candidates, write the canonical
empty `verification/batches.md` and skip planner and skeptics. Otherwise spawn
one bounded **Verification-Planner** or sharded planners over index slices. They
open `indexes/topology.tsv` first and require every candidate to belong to at
least one graph edge. Candidate-bearing connected components, not candidate row
count, define the semantic batching units; split a component only at a cited
articulation point or input-budget boundary. They open only selected canonical
rows, propose duplicate merges (as dispositions for reconciliation, never
deletions), group candidates into skeptic batches — serious candidates
individually or in small related groups, per
`references/verification-and-fixes.md` — and write one skeptic brief per batch
with the candidate rows inline, assigning verdict IDs `V⟨batch⟩-⟨n⟩`.

- Deliverables: `verification/batches.md` and `briefs/V⟨batch⟩.md`.
- Return: the batch list (batch id, brief path, candidate count).

Then spawn one **skeptic** per batch — same spawn pattern, capacity-derived
waves, and targeted retry rules as discovery. Each writes
`verification/V⟨batch⟩.md`. Skeptics are briefed to REFUTE under the refutation
standard; a skeptic that cannot name the guard line or produce the safe trace
has confirmed the finding, not dismissed it. Candidates that honest tracing can
neither confirm nor refute become owner questions — never silent drops. Each
verdict artifact closes every typed obligation from its candidate descriptor and
restates the verified semantic affinity; worker-artifact validation rejects
incomplete cross-layer traces.

After every skeptic batch collects, spawn one global **Invariant Affinity
Reconciler** using the Phase 5.25 brief. It assigns every CONFIRMED/UNPROVEN
candidate and verdict to exactly one root family, audits assumptions across
batches, and writes `verification/affinity.md`. Descriptor extraction may be
sharded for scale, but family assignment is global. Rebuild indexes afterward.
Root-cause planning is blocked until complete family coverage and all six
consistency-audit rows validate.

## Phase 5.5 — Root-Cause, Layering, And Fix Optimality

If the fresh verdict index has zero rows and the inventory index proves no
root-cause-required scope, write canonical empty Trigger Accounting and skip
planner and challengers. Otherwise root-cause trigger selection is analysis,
never inferred by the orchestrator from status lines. Spawn the **Root-Cause
Planner** (brief in `phase-briefs.md`). It reads every skeptic verdict, applies
every trigger in `references/verification-and-fixes.md`, includes the
inventory's root-cause-required change scopes, groups complete root
families/scopes into trace-sized batches, and writes `root-cause/batches.md`
plus one complete `briefs/RC⟨batch⟩.md` per batch. One family is indivisible
even when its members came from different skeptic batches; unrelated families
remain separate.

Spawn one **Root-Cause Challenger** per planned batch in capacity-derived waves.
Each executes Root-Cause, Layering, And Fix Optimality over every complete
family in its batch and writes `root-cause/RC⟨batch⟩.md`. It also decides
whether the validated fix is safely expressible as one small Gerrit suggested
edit, recording the exact selected range and replacement when it is, or the
specific reason it is not. Drafting never invents this decision from local
prose. The RC row is the canonical owner: reconciliation and drafting preserve
its family, decision, selected text, and replacement.

**Reopened issues are canonical ledger rows before they become work.** A
challenger that finds a better owner, missing caller family, duplicated state,
or new affected surface writes each candidate to its own append-only
`ledger/reopened/round-⟨N⟩-RC⟨batch⟩.md`, with stable ID `R⟨N⟩-RC⟨batch⟩-⟨n⟩`,
full evidence, origin, and parent row links. A row that exists only in a brief
or status message does not exist. The challenger may also request a named
discovery recipe, but does not synthesize a skeptic brief itself.

After collecting a round, if any canonical reopened rows exist, rerun the
requested narrowly scoped discovery-recipe briefs first; those workers append
evidence, amendments, or additional canonical reopened rows without replacing
the parent rows. Then rerun the Verification Planner in **delta mode** over
exactly that round's row IDs, execute the resulting skeptics, and rerun the
Root-Cause Planner in delta mode over their verdicts. Increment the round and
repeat until the planner reports no triggered or open rows. All rounds remain in
the manifest and reconciliation record. Synthesis may not start until every
reopened row is verified, refuted, merged, or converted into an owner question.

Run the validator with `--phase verification --require-active-lease` after the
final reopened round.

## Phase 6 — Reconciliation

Spawn one bounded **Reconciliation Builder** or row-disjoint builders plus a
deterministic collector, selected from `indexes/reconciliation.tsv`. They
enumerate every row ID present in `ledger/*.md`, `collection.md`,
`ledger/reopened/*.md`, `verification/*.md`, and `root-cause/*.md` — the files
themselves, never a summary — and write the reconciliation table: one
disposition line per row (promoted / refuted / question / merged / clean), no
ranges, no "rest dismissed". A confirmed finding whose severity was downgraded
is still `promoted → F⟨number⟩` at its calibrated severity; a bare `downgraded`
disposition would make it disappear from output and is forbidden. The default is
one promoted finding per root family; multiple promotions require a cited
exception proving distinct owners or independently bad outcomes. The inverse is
equally strict: every `merged → ⟨survivor-row-id⟩` disposition has one
structured, cited Merge equivalence row proving equal trigger, invariant, and
outcome and naming the survivor's exact verdict. Artifact pointers used as
equivalence evidence resolve to existing, nonempty review-relative files.
Free-form merges, merge chains, cross-family merges, and verdict-class
mismatches are gate failures. It also writes the pre-output gate skeleton from
`references/synthesis-and-output.md` at the bottom of `reconciliation.md`,
filling the lines it can prove.

- Deliverables: `reconciliation.md`, `synthesis/index.md`, and one bounded
  `synthesis/⟨ROW-ID⟩.md` evidence card per promoted finding or owner question.
  A card contains only that row's claim, calibrated disposition, citations,
  trace, root-cause/fix analysis, origin, and existing-thread mapping, including
  the Suggested edit decision and exact replacement evidence when applicable.
  Cards obey the profile's evidence-card budget; if a trace is larger, split it
  into numbered parts referenced by the index. Never cap the number of cards or
  truncate evidence. These cards are the synthesis handoff; the Draft Writer
  must not reread the entire discovery/verification corpus.
- Return: total rows, unaccounted rows (must be zero), promoted-finding count,
  question count, card count, open gate lines. Output is blocked while any row
  lacks a disposition — fix the cause (usually an uncollected file) and respawn.

Run the validator with `--phase reconciliation --require-active-lease` before
drafting.
