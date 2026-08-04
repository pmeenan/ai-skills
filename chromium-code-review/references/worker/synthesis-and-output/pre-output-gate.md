<!-- Generated from ../../synthesis-and-output.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Pre-Output Gate

Copy this checklist verbatim to the bottom of `reconciliation.md`. Before the
draft, lines may be `pending draft`; before the final challenge only Freshness
may remain `pending-delivery`. Every other line is answered "yes" with a
citation or "no" with the deviation disclosed in Verification Notes. Final
delivery is blocked while any line is pending or blank.

1. **Pin:** `pin.md` exists; the review text states its patchset number and
   revision SHA.
2. **Freshness:** after the final synthesis challenge (and after every draft
   revision/re-challenge), `delivery-gate.md` records a successful Gerrit
   metadata refresh; the current PS/SHA equals the pin, an explicitly
   requested historical pin is verified in ALL_REVISIONS, or a newer trivial
   delta is recorded in `patchset-delta.md`, followed by a metadata draft
   revision and a fresh passing challenge. A material delta blocks delivery
   and restarts in a new pin.
   Reconciliation and drafting record this as `pending-delivery`; only Phase 9
   may finalize it.
3. **Plan topology:** every entry required by the active topology appears in
   `plan.md`. For `evidence-graph-v1`, both generalist passes cover the same
   complete edge partition (or both use `graph:none`) and every required graph
   continuation is present. A legacy plan accounts for every roster entry as
   spawned, not-applicable-with-trigger proof, or unreviewed-with-reason. No
   required entry is missing, bundled, or renamed.
4. **Collection:** every spawned thread has a collected `ledger/<THREAD>.md`,
   or is disclosed as terminated/interrupted with its partial rows preserved.
5. **Matrices:** no compliance-matrix row is blank or a citation-free PASS;
   each is evidence-closed, N/A-with-reason, or disclosed as unreviewed
   (per `collection.md`).
6. **Per-file floor:** every changed file has at least one ledger row
   (thread rows or `ORC` rows in `collection.md`).
7. **Reconciliation:** every row ID across `ledger/*.md`,
   `ledger/reopened/*.md`, `collection.md`, `verification/*.md`, and
   `root-cause/*.md` has exactly one disposition line — no ranges, no "rest
   dismissed".
8. **Verdicts (comprehensive and non-truncated):** every promoted finding
   cites a CONFIRMED verdict with its trace, and every promoted finding and
   owner question has exactly one measured draft fragment included in
   draft-review.md and, for findings, exactly one measured Gerrit fragment
   included in gerrit-comments.md, with reconciliation→card→coverage sets
   equal and no truncation, sampling, or
   "representative subset"; every independently refuted row cites its guard or
   safe trace; every UNPROVEN row appears in Questions; every merged candidate
   either has its own verdict or has validated trigger/invariant/outcome
   equivalence to a survivor whose verdict is cited (a merged candidate is
   represented by its survivor, never dropped).
9. **Root cause:** `root-cause/batches.md` accounts for every trigger; the
   layering pass ran for every triggering candidate and
   fix; reopened rows were re-verified, refuted, or converted to questions.
10. **Severity and origin:** every finding names its anchor-table match (or
   argues the delta) and carries an origin label.
11. **Verdict consistency:** if any P1/P2 finding stands, the recommendation
    reads "not LGTM until <finding>"; no approval is combined with blocking
    conditions.
12. **Gerrit text:** no local paths or `file://` URLs; no placeholder
    inlines; quoted lines re-checked verbatim against the pinned patchset;
    every applicable Suggested edit has identical apply-ready `suggestion`
    blocks in the review and Gerrit fragment, and every omitted edit names a
    specific reason;
    replies target normalized root/latest IDs from
    `gerrit/unresolved-threads.json` instead of duplicating them.
13. **Honesty:** the test-execution statement matches what was actually run;
    Verification Notes reproduce the plan with outcomes and human-readable
    thread names; orchestration.tsv has a terminal state for every spawned
    attempt; the current draft revision has a complete fresh challenge index.
