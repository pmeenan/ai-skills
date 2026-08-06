<!-- Generated from ../../synthesis-and-output.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Reconciliation (Phase 6)

Synthesis produces a **reconciliation table** in `reconciliation.md` as a
required artifact: every row ID mapped to its disposition — promoted (to
finding N), refuted (with the citation), converted to a question,
merged (into row M), or clean (cited). A severity downgrade is not a terminal
disposition: the confirmed finding remains `promoted → F<number>` at its
calibrated severity. Build the table by
enumerating the row IDs present in `ledger/*.md`, `collection.md`,
`verification/*.md`, and `root-cause/*.md` — the files themselves, never a
summary of them, with no ranges and no "rest dismissed". Output is blocked
until every row has a disposition.

Cross-checks while building the table:

- Every verdict-bearing candidate has a verdict-consistent terminal
  disposition: CONFIRMED is promoted or structurally merged, UNPROVEN becomes
  a question or structural merge, and REFUTED is refuted/dismissed with its
  verdict or code citation, or structurally merged. `dismissed: duplicate`
  cannot bypass the merge contract.
- Every serious candidate has a verdict row; a candidate with no verdict is
  an unaccounted row, not an implicit dismissal, except a candidate with an
  explicit merge proposal. A merged candidate does not need a redundant
  verdict only when reconciliation verifies the same trigger, violated
  invariant, and outcome as the survivor and cites the survivor's verdict. If
  equivalence fails, reject the merge and return the row for verification.
- Merge dispositions use exactly `merged → <survivor-row-id>` and have one
  matching `Merge equivalence` row in the templates.md shape. That row
  separately cites equal trigger, violated invariant, and outcome, plus the
  survivor's exact verdict. The survivor exists, owns a verdict, is not itself
  merged, and has the verdict-consistent terminal disposition. When both rows
  have verdicts their verdict classes match; when affinity assigned both,
  their root family matches. Free-form `merged because ...` prose is invalid.
  Equivalence cells require actual code citations or canonical artifact
  pointers whose review-relative files exist and are nonempty;
  `evidence-exception:` is not sufficient for a semantic merge.
- Every UNPROVEN verdict maps to a Questions entry; every reopened
  root-cause row maps to a verdict or a question.
- Every row amendment is applied in order; the original row remains present
  and its disposition cites the effective amendment.
- `root-cause/batches.md` accounts for every trigger, including not-applicable
  rows with reasons.

For each promoted finding and owner question, write one immutable bounded
evidence card under `synthesis/<ROW-ID>.md` in the templates.md shape and add a
manifest row to `synthesis/index.md`. Write each card using harness-native file creation tools or write a standalone script file (`cat << 'EOF' > gen_cards.py` with a quoted `'EOF'` delimiter) to avoid shell command-substitution errors on verbatim code lines containing backticks. A card is at most
`profile.json:/context_budget/evidence_card_budget_bytes`. It
contains the effective candidate row, verdict, root-cause result, merge
support, severity/origin, Gerrit-thread target, verbatim line, and caveats
needed for that item — not entire source artifacts. Every finding card also
carries the root-cause pass's Suggested edit decision. An applicable decision
includes the exact changed-side target range, verbatim selected lines, and
replacement, plus exact `Root cause` and `Root family` bindings; reconciliation
must not substitute a locally attractive snippet for an RC omission. When no
root-cause pass ran, record both bindings as `none` and the decision as omitted
because no fix was validated. An omitted decision includes a specific reason. Split excess supporting
material into numbered parts; never truncate a row. This card set,
not all verdict and ledger files, is the Draft Writer's synthesis input.

Then write the Pre-Output Gate checklist (below) verbatim at the bottom of
`reconciliation.md`, filling every line you can prove from the files
(roster, collection, matrices, per-file floor, reconciliation, verdicts,
root cause). Leave draft-dependent lines for the Draft Writer marked
`pending draft`. Mark only Freshness `pending-delivery`; it cannot be yes
until metadata is refreshed after the final challenge.

ID enumeration extracts row-definition columns/headings, including the
reopened form `R<round>-RC<batch>-<n>`; an ID merely cited inside evidence is not a new
row definition. Deduplicate the definition set before testing one-disposition
coverage.
