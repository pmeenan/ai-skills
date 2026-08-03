<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Evaluating Fixes

Review any proposed fix as carefully as the original bug: trace it through
boundary inputs, all affected state transitions, existing tests, and likely
reentrant/cancellation paths. If you cannot validate the fix, present it as an
option needing verification rather than endorsing it as the correct change.

Sanity-check fixes against common Chromium edge cases:

- Zero, empty, immediate, max-size, overflow, and negative values.
- Posted tasks, timers, delayed callbacks, and task ordering.
- Completion-delay clock origin: total observed latency vs extra latency after
  a wrapped operation completes. Verify synchronous wrapped completion, wrapped
  completion before the budget expires, and wrapped completion after the budget
  is already exhausted.
- Reentrancy from callbacks.
- Cancellation, reset, shutdown, and object destruction.
- `WeakPtr`, ref-counting, ownership transfer, and RAII handles.
- Sequence/thread affinity and destructor sequence requirements.
- Boundary capacity and backpressure behavior.
- Numeric conversion, truncation, overflow, sentinel agreement, and
  representability across signed/unsigned, `size_t`, `int`, and floating-point
  math.
- Terminal or one-shot sentinel results (EOF, closed, cancelled, no more data)
  must not be masked by status predicates added before the operation runs.
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
