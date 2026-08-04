<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Shared Execution Contract

For each activated section, produce the named artifact with:

1. exact trigger hits (`path:line` and symbol);
2. the required model or matrix;
3. one prefixed candidate row per unresolved invariant or omission;
4. `PASS` rows only when evidence cites code or a test by `path:line`.

Do not infer safety from comments, DCHECKs in release-only paths, type names, or
the CL description. Trace the concrete producer, consumer, owner, boundary, and
teardown/version state.

A `specialist:full` scope executes the whole assigned section. A
`specialist:probe` scope executes at most three cited risk units: the deepest
or highest-fanout applicable path, one teardown/error/boundary path, and one
test-defense path. Escalate by returning `partial` with the unreviewed full
scope when the probe confirms a section trigger, creates a candidate,
discovers a new relevant graph obligation, or leaves high residual risk; the next
attempt continues the same work ID and ledger. A clean probe must still cite
the guards, owners, bounds, compatibility mechanisms, or tests that reduced
the likelihood. "Looks risky" without those signals is neither escalation nor
closure.

Every probe writes `## Specialist probe outcome` with columns `lens | graph
scope | result | evidence | remaining scope`. `result` is `clean` or
`escalate`; an escalated row retains `specialist:full; graph:...` as remaining
scope. The validator rejects a clean result with a candidate or open graph
obligation and rejects escalation without a later complete same-work-ID
continuation whose attempt-specific brief retains the full graph scope and
directly depends on the escalated attempt.

When generalists estimate this section's likelihood, ask whether a full sweep
is likely to discover additional relevant edges. Amplify for interactions
among soft patterns, unresolved graph depth/fanout, boundary crossings, and
missing defenses or adversarial tests. One isolated, fully traced local
pattern can be `low`; it is not automatically `medium`. Several interacting
patterns or an unguarded deep chain can be `high`. Use `low` only with
affirmative cited counterevidence.
