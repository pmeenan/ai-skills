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
