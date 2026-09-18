<!-- Generated from ../../execution-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Execution Orchestration (Phases 4 to 6)

Discovery execution, collection audit, verification, root-cause analysis, and
reconciliation. The orchestrator loads this file when Phase 4 becomes runnable
and works from it through the end of Phase 6, then hands off to
`references/synthesis-orchestration.md` for Phases 7 to 9.

Everything the orchestrator needs for these phases is here; `SKILL.md` keeps the
standing rules that apply across all phases — the context budget, partial
returns and narrow repair, sealing, waiting on `await-workers.py`, and the
prohibition on reading helper source — and does not restate anything below.

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
