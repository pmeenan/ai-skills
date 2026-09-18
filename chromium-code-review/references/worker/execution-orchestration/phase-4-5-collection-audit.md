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
