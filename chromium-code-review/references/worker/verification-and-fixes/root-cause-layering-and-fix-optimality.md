<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Root-Cause, Layering, And Fix Optimality

Run this after candidate verification and before final synthesis. The goal is
to catch surface fixes: changes that repair the observed hunk, caller, or test
without repairing the invariant owner.

For every complete root family containing a P1/P2 candidate, risky P3,
proposed fix, performance optimization,
flaky-test fix, async/lifecycle change, state-machine change, cache/throttle,
or new state holder, record a root-cause row with these fields:

- **Symptom:** the observed failure, performance cost, race, or review concern.
- **Direct trigger:** the local branch, caller sequence, input, or timing that
  exposes it.
- **Violated invariant:** the property that should always hold, stated without
  reference to the proposed fix.
- **Invariant owner:** the class, method, helper, state enum, protocol, or
  data model that should enforce or cache that invariant.
- **Right-layer evidence:** upstream/source layer checked, local layer checked,
  downstream/caller layer checked, and any canonical state/shared helper found
  by search.
- **Callsite coverage:** whether every production caller or mode sharing the
  invariant is covered, with representative `path:line` citations.
- **Chosen-fix verdict:** validated right layer, plausible but needs owner
  confirmation, too local/surface-level, or no fix proposed.
- **Suggested-edit decision:** `applicable` only when one exact Gerrit inline
  replacement fully implements the validated fix; otherwise
  `omitted — <specific reason>`. For an applicable edit, record the
  repo-relative changed-side range, the verbatim selected lines, and the exact
  replacement. Re-trace the replacement through the same edge cases as the
  chosen fix; a plausible code sketch is not an applicable edit. Use the
  canonical multiline RC-row fields from `templates.md`; never compress
  multiline selected/replacement text into a root-family table cell. The
  table cell references the owning RC row, and reconciliation copies that
  row's decision byte-for-byte into the evidence card.
- **Family coverage:** every candidate/verdict member, a State × Method matrix
  when a protocol state is involved, excluded nearby methods with reasons,
  one chosen fix layer, and whether the family produces one review comment.
  Multiple comments require distinct invariant owners or independently bad
  outcomes, not merely different methods or discovery threads.

Use these drills to fill the row:

- Walk one layer upstream to the producer/source of the value, event, state, or
  timing decision. Ask whether enforcing the invariant there would protect more
  callsites with less state or fewer special cases.
- Walk one layer downstream to the consumers/callers. Ask whether the issue is
  caller-specific or shared by all users of the same API, state, cached value,
  or callback contract.
- Search for an existing canonical state owner, shared helper, base-class
  contract, or sibling implementation before endorsing a new field, cache,
  wrapper, or special-case branch.
- For duplicated or cached state, prove why the cache belongs at the proposed
  layer instead of on the canonical object that owns the source value. A cache
  beside a derived consumer is fragile unless invalidation and all relevant
  callers are accounted for.
- For performance work, identify the unit of work whose cost is being reduced
  and the component that actually owns scheduling, batching, throttling, or
  caching for that unit. A rate limit, cache, or token bucket at an input edge
  is suspect when a central worker/state holder owns the work.
- For flaky-test fixes, separate deterministic observation from deterministic
  behavior. Name the production method/protocol whose race was exposed, then
  verify whether the new test setup prevents the race at its source or only
  waits for this test's final condition more carefully.
- For state machines, build or reuse the State × Method matrix for any
  implicated state owner. A bad-state concern must cite the transition path
  that reaches it; a refutation must cite the guard or transition that blocks
  it.
- For async operations, trace the ownership of the pending operation, the
  cancellation/reset/destruction path, and the callback completion contract.
  A local waiter fix is insufficient if the operation itself can still drop,
  duplicate, or reorder completion.

If this pass changes the likely invariant owner, exposes a missing caller
family, reveals duplicated canonical state, or opens a new state-machine or
async scenario, first write each issue as a canonical row in
`ledger/reopened/round-<N>-RC<batch>.md`, with ID
`R<N>-RC<batch>-<n>`, full evidence, origin, requested recipe (if any), and
parent candidate/verdict/RC links. A row that exists only in a brief or status
message does not exist. Run any requested narrow discovery recipe first; it
appends evidence/amendments or additional canonical reopened rows. Then rerun
the Verification Planner in delta mode over exactly that round, execute its
skeptics, and rerun the Root-Cause Planner in delta mode. Challengers do not
create skeptic briefs directly. Increment rounds until no open/triggered row
remains. Do not bury the result as a caveat: either verify it, refute it,
merge it with proven equivalence, or ask the owner before synthesis.

Examples of the intended reasoning pattern:

- Parser performance: if parser-side rate limiting controls work owned by the
  tree builder, check whether the tree builder is the invariant owner because
  it sees all sources of tree-building work.
- Site-for-cookies caching: if a document caches a value derived from
  `SecurityOrigin`, check whether `SecurityOrigin` is the canonical owner and
  whether caching there improves all callsites with less invalidation risk.
- Flaky tests: if a test's end condition is made deterministic, still verify
  whether the method under test can race under production-like sequencing.
