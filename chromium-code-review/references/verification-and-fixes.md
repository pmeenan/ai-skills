# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in SKILL.md.

## Contents

- Verifying Candidate Findings
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
- Record refuted candidates in the ledger with a one-line reason instead of
  deleting them; synthesis re-checks the ledger.
- Distinguish observation from proposed fix. Never recommend a concrete fix
  until it has been traced through the relevant edge cases below.

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
