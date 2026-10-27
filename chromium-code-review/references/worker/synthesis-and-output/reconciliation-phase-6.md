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
  disposition: CONFIRMED is promoted (`promoted → F<number>`), structurally
  merged, or assigned one of the explicit audited follow-up/note dispositions
  (`note → N<number>`, `suppressed — unchanged since prior review (...)` for
  `P3`, `pre-existing`, or justified `below round-<N> bar:` `P2` items on
  mechanically verified unchanged code — never `P1`, `subordinated → thread
  <root_id> (...)`, or
  `launch-gate note (...)`); UNPROVEN becomes an owner question
  (`question → Q<number>`), reviewer note (`note → N<number>`),
  `subordinated → thread <root_id> (...)`, or structural merge; and REFUTED is
  refuted/dismissed with its verdict or code citation, or structurally merged.
  `dismissed: duplicate` cannot bypass the merge contract.
- **Same-Reviewer Round 2+ / Round 3+ Interdiff-First Promotion Gate:** When
  `profile.json:/prior_context/reviewer_history/same_reviewer_followup` is
  `true` and `indexes/interdiff-hunks.tsv` is present, apply full promotion
  rigor to `latest_prior_reviewed_sha..revision_sha` interdiff hunks, incomplete
  fixes to posted prior comments, and regressions or new interactions triggered
  by those fixes. Meanwhile, the validator mechanically rejects promoting
  (`promoted → F<number>`) any candidate overlapping a `not-posted` `PR-<n>`
  location whose code path does not overlap `indexes/interdiff-hunks.tsv`. For
  candidates targeting code **unchanged** since `latest_prior_reviewed_sha`
  (mechanically verified not to overlap any hunk in
  `indexes/interdiff-hunks.tsv`), prevent late-round scope creep without
  dropping audit rows: (1) suppress newly discovered `P3` nits and `Origin:
  pre-existing` observations via `suppressed — unchanged since prior review
  (<V-id>)`, and suppress `CL-introduced` / earlier-round `P2` items that fall
  below the late-round bar only with an explicit justification `suppressed —
  unchanged since prior review (<V-id>, below round-<N> bar: <specific reason>)`
  (**P1** defects are strictly non-suppressible even on unchanged code — the
  validator rejects any `P1` suppression, any `P2` suppression without `below
  round-<N> bar: <reason>`, and any suppression whose location overlaps
  `indexes/interdiff-hunks.tsv`); (2) fold newly noticed pre-launch
  completeness gaps on unchanged code behind a `FEATURE_DISABLED_BY_DEFAULT`
  flag into `launch-gate note (<V-id>)`, surfaced as a non-blocking
  **Launch-Gate Note** in `FRAME.md`; (3) subordinate candidates whose scope is
  already covered by an open `reviewer decision pending` Gerrit thread via
  `subordinated → thread <root_id> (<V-id>)`; (4) route subtle edge cases or
  external-spec tensions in code implementing `Reviewer email`'s own prior
  suggestion to `note → N<number> (<V-id>)` (Reviewer Note in `draft-review.md`
  only); and (5) apply a **P1 ship-stopper bar** (reachable security/privacy
  violation, memory corruption/UAF, crash, hang, or data loss) before promoting
  any newly noticed blocker on unchanged code already reviewed by `Reviewer
  email`.
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
- Every UNPROVEN verdict maps to a Questions entry (or a Reviewer Note
  `note → N<number>` / `subordinated → thread <root_id>` when applicable); every
  reopened root-cause row maps to a verdict, question, or note.
- Every row amendment is applied in order; the original row remains present
  and its disposition cites the effective amendment.
- `root-cause/batches.md` accounts for every trigger, including not-applicable
  rows with reasons.

For each promoted finding, owner question, and reviewer note, write one
immutable bounded evidence card under `synthesis/<ROW-ID>.md` in the
templates.md shape and add a manifest row to `synthesis/index.md`. Write each card using harness-native file creation tools or write a standalone script file (`cat << 'EOF' > gen_cards.py` with a quoted `'EOF'` delimiter) to avoid shell command-substitution errors on verbatim code lines containing backticks. A card is at most
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
