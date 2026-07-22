# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Contents

- Reconciliation (Phase 6)
- Drafting The Review (Phase 7)
- Finding Format
- Severity Calibration
- Output Format
- Pre-Output Gate
- Tone

## Reconciliation (Phase 6)

Synthesis produces a **reconciliation table** in `reconciliation.md` as a
required artifact: every row ID mapped to its disposition — promoted (to
finding N), refuted (with the citation), converted to a question,
downgraded, merged (into row M), or clean (cited). Build the table by
enumerating the row IDs present in `ledger/*.md`, `collection.md`,
`verification/*.md`, and `root-cause/*.md` — the files themselves, never a
summary of them, with no ranges and no "rest dismissed". Output is blocked
until every row has a disposition.

  In a measured run, a P1 candidate recorded by the error-path thread was
  silently dropped between ledger and review; findings reported by several
  threads survived consolidation while single-source rows vanished — the
  table exists to protect the single-source rows.

Cross-checks while building the table:

- Every serious candidate has a verdict row; a candidate with no verdict is
  an unaccounted row, not an implicit dismissal.
- Merge dispositions cite the surviving row; the merged row's evidence must
  actually duplicate the survivor's.
- Every UNPROVEN verdict maps to a Questions entry; every reopened
  root-cause row maps to a verdict or a question.

Then write the Pre-Output Gate checklist (below) verbatim at the bottom of
`reconciliation.md`, filling every line you can prove from the files
(roster, collection, matrices, per-file floor, reconciliation, verdicts,
root cause). Leave the lines that depend on the draft (pin statement,
verdict consistency, Gerrit text, honesty) for the Draft-Writer, marked
"pending draft".

## Drafting The Review (Phase 7)

Inputs: `reconciliation.md`, the CONFIRMED/UNPROVEN verdicts in
`verification/*.md`, `root-cause/*.md`, `context.md`, `pin.md`,
`directives.md`, `ledger/PR.md` (follow-ups), `comments.json` (for replies
to existing threads), and the worktree for verbatim quoted lines. Write
`draft-review.md` in the Output Format below and `gerrit-comments.md` under
the Verdict Alignment And Gerrit Output Rules in
`references/verification-and-fixes.md`, then complete the remaining
pre-output gate lines in `reconciliation.md`. Producing review text while a
gate line is blank is the failure mode the gate exists to stop.

Findings come from the reconciliation table's promotions — the draft writer
does not re-adjudicate verdicts. If the record looks contradictory
(a promotion without a CONFIRMED verdict, a verdict without a disposition),
that is a gate failure to report to the orchestrator, not a judgment call
to paper over.

## Finding Format

Record and report every finding with:

- **Claim:** one sentence describing concrete behavior, not vibes.
- **Location:** repo-relative `path:line` against the reviewed patchset.
- **Evidence:** the minimal state/call trace or citation that demonstrates it.
- **Severity:** P1/P2/P3 per the calibration below, naming the matched anchor.
- **Origin:** `CL-introduced`, `pre-existing`, or — in follow-up reviews —
  `introduced-in-PS<N>` for regressions the newer patchset added.
- **Fix status:** validated fix, option needing verification, or no fix
  proposed.
- For P1/P2 findings: the smallest regression test that would have caught it.
- **Rows:** the ledger row and verdict IDs behind the finding (e.g.
  `EPW-2 / V1-1`) — an internal trail for the gate; omit it from
  Gerrit-ready text.

## Severity Calibration

- **P1:** Serious correctness, security, data loss, UAF, deadlock, or major
  regression risk. Must fix before landing.
- **P2:** Real correctness risk, missing coverage for core/default behavior,
  likely production regression, or contract ambiguity that can mislead
  callers. Normally fix before LGTM.
- **P3:** Documentation clarity, non-blocking test polish, minor efficiency,
  small consistency issues, or defensive improvements. Often optional or
  follow-up-worthy.

Calibration notes:

- In stack or foundation CLs, API contract mistakes can be P1 even before a
  production caller lands if follow-up CLs are likely to bake in the behavior.
- Do not downgrade an API-shape, sentinel, or contract issue merely because it
  is documented if the documented behavior remains a footgun for downstream
  CLs.
- A mock-time hang that can block CI is more severe than a comparable
  real-time performance nuisance.
- Avoid blocking on speculative problems, style preferences, or fixes whose
  tradeoffs have not been validated.

Anchor table — match each finding to the nearest anchor and argue any delta
explicitly. Anchors beat intuition, especially for test-gap severity:

| Finding pattern | Severity |
| --- | --- |
| Dropped completion callback on an error path (caller waits forever) | P1 |
| Success-shaped return (positive length, `OK`) after failure cleanup in a `DoLoop`-style state machine | P1 |
| Discarded accepted/written-count return (`Push`, short `Write`) — silent byte loss | P1 |
| Callback or timer bound with `Unretained` plus a reachable destroy-before-fire path | P1 |
| Documented base-interface contract clause violated by an override (buffer retention across `ERR_IO_PENDING`, `OK`-vs-byte-count semantics) | P1 |
| Renumbered or reused values of a persisted/serialized enum | P1 |
| Zero-delay self-reposting task that busy-loops `FastForwardBy` under mock time (CI hang) | P1 |
| Restriction feature (throttle, quota, block, isolation) silently degrading to unrestricted behavior on the common path | P1; P2 when the bypass needs an uncommon mode |
| Success-only metric (duration, success count, size/ratio) logged on aborted or cancelled operations | P2 |
| Load-bearing metadata written fire-and-forget (selectable-but-corrupt state) | P2 until proven unobservable |
| Missing test coverage for the default/core mode of new behavior | P2 |
| Sidecar (cache/compression/metrics) failure propagated into the primary operation's result | P2 |
| Untested kill-switch OFF branch whose OFF behavior differs from pre-CL behavior | P2 |
| Untested kill-switch OFF branch that only gates memoization of an invalidation-free value | P3 |
| Ambiguous boolean name (policy vs state, `should_` vs `is_`) | P3 |
| Non-ASCII punctuation in comments or developer-facing prose | P3 |
| Defensive hardening or opportunistic cleanup absent from the CL description | P3 (suggest split or description mention) |

## Output Format

Format the final review as:

1. **CL-Introduced Issues & Suggestions:** Findings introduced by the CL, ordered
   by severity, with file/line references and actionable guidance. Separate blocking
   issues from optional polish. In follow-up reviews, label
   `introduced-in-PS<N>` findings as such within this section.
2. **Pre-Existing Codebase Issues (For Reference/Follow-up):** Issues observed
   in the surrounding codebase but not introduced by the CL. These must be clearly
   labeled as pre-existing and do not block landing of this CL.
3. **High-Level Summary:** State whether the CL accomplishes its goal, name the
   patchset and revision SHA, and summarize bug alignment.
4. **Prior Review Follow-Up:** If prior issues were supplied, summarize their
   status with evidence.
5. **Positives:** Briefly note important good decisions. A praised safety
   property is a claim like any other — name its guard line. (A measured run
   praised "failures fail open safely" about the exact branch that treated a
   failure as success.)
6. **Questions:** Only questions whose answers affect correctness, API contract,
   or landing readiness. Every UNPROVEN verdict lands here.
7. **Verification Notes:** State tests run or not run, production wiring traced
   or not traced, and any important areas not verified.
   - Name subagents by human-readable thread name (e.g. "the Error-Path Walk
     thread"), never by internal conversation IDs or task UUIDs.
   - Claim test execution only if the exact commands ran successfully against
     the pinned patchset; otherwise state: "No local test execution was
     performed during this review."
   Reproduce the full thread plan from `plan.md` with each thread's outcome:
   rows returned (count), not-triggered (with reason), "terminated — scope
   unreviewed", or "interrupted — partial". Include each thread's
   human-readable name (mapped to its task identifier in `plan.md`), or
   "self-executed" plus the harness limitation that forced it. A
   not-triggered thread is an unverified dimension by definition, and any
   plan deviation — a folded or unspawned entry, a degraded file-access
   handoff — is disclosed here as an unverified area. On large CLs the full
   compliance matrices live in the review directory with Verification Notes
   pointing at it — every per-row answer must exist somewhere retrievable; a
   "combined audit summary" that discards rows defeats the accounting. Also
   state the root-cause/layering pass outcome: candidate count checked, any
   better owner or broader invariant found, and any discovery/verification
   rows reopened because of it.
8. **Next Steps:** State what is required before `+1 LGTM` and what is optional.

For full CL reviews, append compact **Gerrit-Ready Comments** unless the user
asks for a short summary only, following the Verdict Alignment And Gerrit
Output Rules section of `references/verification-and-fixes.md`:

- **Main body:** brief landing-readiness summary, blockers, optional items,
  prior review status, and verification notes.
- **Replies to existing unresolved threads:** file and thread line, status, and
  the exact response, using the threads recorded in `comments.json`. Do not
  open duplicate new threads for an existing topic.
- **New inline comments:** repo-relative file, exact line or range, verbatim line
  text from the reviewed patchset, and concise comment text. Prefix optional
  polish with `nit:`.

For Gerrit-ready text, cite findings as repo-relative `path:line` against the
reviewed patchset, extract quoted code verbatim, and re-check line numbers
before sending. Avoid leaking local filesystem paths in comments meant for
Gerrit.

## Pre-Output Gate

Copy this checklist verbatim to the bottom of `reconciliation.md` and fill it
in before any review text is written. Every line is answered "yes" with a
citation (a file or row ID in the review directory) or "no" with the
deviation disclosed in Verification Notes. Producing the review while a line
is blank is the failure mode this gate exists to stop.

1. **Pin:** `pin.md` exists; the review text states its patchset number and
   revision SHA; Gerrit metadata was refreshed after synthesis and any newer
   patchset delta inspected.
2. **Roster:** every roster entry appears in `plan.md` as spawned or
   not-triggered-with-reason; no entry is missing, bundled, or renamed.
3. **Collection:** every spawned thread has a collected `ledger/<THREAD>.md`,
   or is disclosed as terminated/interrupted with its partial rows preserved.
4. **Matrices:** no compliance-matrix row is blank or a citation-free PASS;
   each is evidence-closed, N/A-with-reason, or disclosed as unreviewed
   (per `collection.md`).
5. **Per-file floor:** every changed file has at least one ledger row
   (thread rows or `ORC` rows in `collection.md`).
6. **Reconciliation:** every row ID across `ledger/*.md`, `collection.md`,
   `verification/*.md`, and `root-cause/*.md` has exactly one disposition
   line — no ranges, no "rest dismissed".
7. **Verdicts:** every promoted finding cites a CONFIRMED verdict with its
   trace; every refuted row cites its guard or safe trace; every UNPROVEN
   row appears in Questions.
8. **Root cause:** the layering pass ran for every triggering candidate and
   fix; reopened rows were re-verified, refuted, or converted to questions.
9. **Severity and origin:** every finding names its anchor-table match (or
   argues the delta) and carries an origin label.
10. **Verdict consistency:** if any P1/P2 finding stands, the recommendation
    reads "not LGTM until <finding>"; no approval is combined with blocking
    conditions.
11. **Gerrit text:** no local paths or `file://` URLs; no placeholder
    inlines; quoted lines re-checked verbatim against the pinned patchset;
    replies target existing threads from `comments.json` instead of
    duplicating them.
12. **Honesty:** the test-execution statement matches what was actually run;
    Verification Notes reproduce the plan with outcomes and human-readable
    thread names.

## Tone

Follow Chromium review norms: assume competence and goodwill, lead with concrete
findings, explain why each requested change matters, ask "why" when intent is
unclear and affects correctness, label optional polish as optional, and make
landing blockers explicit.
