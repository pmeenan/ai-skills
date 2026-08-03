<!-- Generated from ../../synthesis-and-output.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Finding Format

Record and report every finding with:

- **Synthesis item:** its unique `F<number>` from the reconciliation
  disposition and `synthesis/index.md`.
- **Claim:** one sentence describing concrete behavior, not vibes.
- **Location:** repo-relative `path:line` against the reviewed patchset.
- **Evidence:** the minimal state/call trace or citation that demonstrates it.
- **Severity:** P1/P2/P3 per the calibration below, naming the matched anchor.
- **Origin:** `CL-introduced`, `pre-existing`, or — in follow-up reviews —
  `introduced-in-PS<N>` for regressions the newer patchset added.
- **Fix status:** validated fix, option needing verification, or no fix
  proposed.
- **Suggested edit:** `applicable — replaces path:start-end`, followed by the
  exact fenced `suggestion` replacement, or
  `omitted — <specific reason>`. Applicability is decided and evidenced in
  the root-cause/evidence card, not improvised while drafting. The same
  replacement block must appear byte-for-byte in the Gerrit-ready comment.
- For P1/P2 findings: the smallest regression test that would have caught it.
- **Rows:** the ledger row and verdict IDs behind the finding (e.g.
  `EPW-2 / V001-1`) — an internal trail for the gate; omit it from
  Gerrit-ready text.

Record every owner question as its own exact draft fragment with non-empty
`Synthesis item` (`Q<number>`), `Question`, `Why it matters`, and `Rows`
fields. Questions do not get Gerrit fragment rows.
