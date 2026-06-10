# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in SKILL.md.

## Contents

- Verifying Candidate Findings
- Execution-Based Verification
- Evaluating Fixes
- Final Synthesis Pass

## Verifying Candidate Findings

Verify each non-trivial candidate before presenting it. Prefer concrete code
traces over speculative concerns — but spend the trace: refute candidates with
code, not from memory.

- Build a minimal state or call trace from the code that demonstrates the
  issue, or demonstrates its absence.
- Cite the exact code path and any relevant tests or comments.
- Classify the issue: correctness bug, contract mismatch, missing test,
  performance risk, lifecycle risk, or polish.
- Check whether existing tests intentionally codify the observed behavior.
- Challenge the finding: look for alternate caller paths, wrappers, overrides,
  feature gates, or invariants that make it unreachable or lower its severity.
- To refute a candidate, name the specific guard (the line) that prevents it,
  or produce the concrete trace that completes safely. "Looks handled" or
  "the caller probably checks" is not a refutation — it is the shallow read
  the candidate exists to challenge. For hypotheses written as
  IF/THEN/UNLESS, refutation means filling in the UNLESS with a citation.
- If honest tracing can neither confirm nor refute a candidate, do not drop
  it: convert it into a question for the CL owner in the review's Questions
  section, stating what you traced and what remains unproven. Uncertainty
  rounded down to "probably fine" is how reviews miss real bugs.
- Record refuted candidates in the ledger with a one-line reason instead of
  deleting them; synthesis re-checks the ledger.
- Matrix cells marked incompatible-but-guarded are verification inputs too:
  confirm that the named guard actually guards the cell's scenario, on the
  path the scenario takes. In a measured run a cell cited `ShouldTruncate()`
  as the guard for `StopCaching(keep_entry=true)` — but that guard only runs
  on the failure path, and the success path skipped it entirely.
- Distinguish observation from proposed fix. Never recommend a concrete fix
  until it has been traced through the relevant edge cases below.

## Execution-Based Verification

Code citations and paper traces are the default standard of evidence — cheap
and almost always sufficient. Building the patchset or running tests is a
bounded, last-resort tier, not a routine step:

- Use it only in verification (never discovery), and only for a P1/P2
  candidate whose paper trace is genuinely contested — where running the
  smallest test would settle confirm-vs-refute.
- Build only the narrowest target against an existing warm build directory
  (`autoninja -C out/<existing> <test_target>`, e.g. `net_unittests` or
  `components_unittests`, plus a tight `--gtest_filter`). Never `gn gen` a
  fresh output directory in a temporary worktree: a cold Chromium build
  costs an hour-plus and buys less than an hour of tracing. If no warm
  build exists, skip execution and record the candidate as "needs
  execution verification" in Verification Notes.
- Budget it: if the build or run exceeds roughly ten minutes, stop and fall
  back to the paper trace.
- Record in Verification Notes exactly what was built or run, how long it
  took, and which candidate it settled — so the next iteration can judge
  whether the time was earned. The regression test named in a P1/P2 finding
  is a description for the CL owner, not an obligation to implement and run
  it.
- Execution never includes applying a proposed fix or a new test to the
  user's checkout or the review worktree. If trying a change is truly
  unavoidable, copy the touched files to a scratch directory outside the
  repository and experiment there; the review itself stays read-only.

## Evaluating Fixes

Review any proposed fix as carefully as the original bug: trace it through
boundary inputs, all affected state transitions, existing tests, and likely
reentrant/cancellation paths. If you cannot validate the fix, present it as an
option needing verification rather than endorsing it as the correct change.

Sanity-check fixes against common Chromium edge cases:

- Zero, empty, immediate, max-size, overflow, and negative values.
- Posted tasks, timers, delayed callbacks, and task ordering.
- Reentrancy from callbacks.
- Cancellation, reset, shutdown, and object destruction.
- `WeakPtr`, ref-counting, ownership transfer, and RAII handles.
- Sequence/thread affinity and destructor sequence requirements.
- Boundary capacity and backpressure behavior.
- Numeric conversion, truncation, overflow, sentinel agreement, and
  representability across signed/unsigned, `size_t`, `int`, and floating-point
  math.
- Compile-time gate polarity: when a fix adds or edits `#if`,
  `#if defined(...)`, or `#if !defined(...)` gates — especially snippets
  suggested in review — re-verify branch polarity against the feature name,
  default build configuration, and intended platforms.

Heuristics for choosing between fixes:

- **Prefer state invalidation over partial recovery.** For components managing
  ephemeral, transient, or reconstructible state (caches, Mojo/IPC channels,
  page loading/rendering pipelines, media playback state), prefer total state
  invalidation, reset, or destruction on error/abort over complicating control
  flow to salvage partial state. Correctness and code simplicity outrank
  absolute retention efficiency.
- **Avoid conditional carve-outs for errors.** Do not introduce complex branch
  logic special-casing specific cancellation errors or sub-phases when
  resetting the component or restarting from a clean slate is valid and much
  safer.
- **Shared-helper invariants and side effects.** Before adding assertions to a
  shared helper or routing a new path through an existing completion/cleanup
  helper, trace every caller at the exact moment the helper is entered and
  account for the helper's side effects. If the helper forces success,
  cleanup, or callback state incompatible with the new path, suggest a
  narrower helper or an explicit path. (Example pattern: a fix funnels a new
  failure path through a helper that unconditionally records success and runs
  completion cleanup.)
- **Observable cascade analysis.** For state cleanup, flag-reset, or retry
  bugs, trace the downstream observable effect — a lost callback, mismatched
  result, corrupt persisted data, spurious retry, or double failure — before
  deciding severity or endorsing a fix.
- **Fail open for sidecar layers.** When fixing errors in an optimization
  layer (cache writes, compression, prefetch), prefer dooming the entry and
  letting the primary operation succeed over propagating the error to the
  consumer. The primary path's contract outranks the optimization's
  bookkeeping.
- **Fail open is for optimizations, not restrictions.** The heuristic
  inverts when the feature's purpose IS the restriction — throttling,
  blocking, isolation, quotas: a path that silently degrades to the
  unrestricted behavior is a finding, not graceful fallback. A measured
  run's synthesis challenger rejected a real bug ("in-flight requests
  silently fall back to the unthrottled factory") as "graceful, intended
  fallback" — exactly this inversion.

When a fix changes API shape or caller obligations:

- For nullable callbacks, optional dependencies, sentinels, or optional
  handles: first verify whether optionality is part of the public contract and
  whether tests or callers rely on the absent-value path. Suggest making the
  value mandatory only after comparing that API-shape change against
  preserving the optional contract with clearer tests or docs.
- Compare plausible alternatives before recommending one. Examples: reject
  invalid input vs accept a sentinel; explicit cancellation handle vs weak
  callback pruning; edge-triggered vs level-triggered notifications; owned
  task cancellation vs caller-managed weak callbacks.

## Final Synthesis Pass

Before final output, run a contradiction pass over the ledger and the draft
review:

- Does the final review account for every ledger entry — promoted, downgraded,
  or dismissed with a recorded reason?
- Are findings derived from actual code traces rather than assumptions?
- Do proposed fixes preserve the documented contract and nearby Chromium
  idioms? Have API-shaping fixes been weighed against reasonable alternatives?
- Did the integration trace prove the code is wired into the intended runtime
  path, and did the disabled/default-path trace prove old behavior is
  preserved?
- Do tests prove the intended behavior, or merely compile/run nearby paths?
- Are prior-review findings clearly separated from new findings?
- Is any finding contradicted by another caller path, wrapper, override,
  feature flag, or test-only restriction?
- Are any findings only style preferences that should be P3 or omitted?
- Are severities calibrated for this CL's position in any larger stack?
- What did you not verify — tests not run, callers not traced, platform paths
  not checked, assumptions that still need confirmation? State these in the
  review's Verification Notes.
