# Discovery Checklists

Read the sections matching the risk-area map **before** line-by-line analysis.
These checklists exist to raise recall: they tell you what to suspect, and
every suspicion goes into the finding ledger as a candidate. Do not filter
candidates here — wrong hypotheses are free, and verification prunes them
later. Reviews miss most when suspicions are never written down.

Answer the questions concretely, per surface or per call site: name the
member, the line, the caller. A yes/no answered from memory is not an answer.

## Contents

- Routing
- Mechanical Leads
- Per-Surface Invariant Questions
- Async And Lifecycle
- State, Persistence, And Cache
- Integration And Feature Control
- Contracts And API Shape
- Tests As Specifications
- Changed-Lines Polish

## Routing

| Diff touches | Read |
| --- | --- |
| callbacks, timers, `WeakPtr`, `SequenceChecker`, ref-counting, posted tasks, cancellation handles, Mojo pipes, sockets, task runners | Async And Lifecycle |
| caches, persisted data, metadata, secondary writes, invalidation, doom/reset paths, origin/scheme decisions | State, Persistence, And Cache |
| feature flags, `#if` gates, factories, decorators, service wiring, new entrypoints | Integration And Feature Control |
| public headers, API comments, predicates, sentinels, `DCHECK`s, shared helpers | Contracts And API Shape |
| new or changed tests, any new public behavior | Tests As Specifications |
| any changed lines | Mechanical Leads, Changed-Lines Polish |

## Mechanical Leads

Run these against the materialized patchset where practical; each hit becomes
a ledger candidate to explain or flag. Commands enumerate leads that are easy
to miss by reading.

- `git diff --check` for trailing whitespace and conflict markers, and a
  formatter diff for changed files (for example,
  `git clang-format --diff <parent>` for Chromium C++/Blink changes). Neither
  catches extra or missing blank lines — scan those manually in the polish
  pass.
- For each changed or new function/method: `git grep -n '<Name>('` and visit
  each non-test caller. Changed semantics with unchanged callers is a classic
  miss.
- For each feature flag or build gate in the diff: grep the flag name across
  the tree, list every gate site, and check that the sites agree on polarity
  and default.
- Grep changed files for `PostTask`, `BindOnce`, `BindRepeating`,
  `base::Unretained`, and new timers. For each, name the object that owns the
  callback target and the line that guarantees the callback cannot outlive
  it.
- For each new symbol used in a changed file (`std::move`, `std::fill`,
  containers, base helpers, test utilities), confirm the file has the direct
  include. Do not rely on transitive includes for STL, base, or test helpers.
- Find the tests exercising changed code:
  `git grep -l '<ClassName>' -- '*test*'`. An empty result for a changed
  public behavior is itself a finding.
- If Gerrit or coverage tooling flags an uncovered changed line, treat it as a
  real lead until disproven (see Tests As Specifications for how to chase it).

## Per-Surface Invariant Questions

For each entry in the changed-surface inventory, answer:

- What is the public contract, per headers, comments, tests, and nearby
  usage?
- What mutable state does it hold, and what invariants hold between fields?
- What are the legal state transitions across public calls? Which call
  sequences are illegal, and what enforces that?
- What async work, timers, callbacks, cancellation, and reset/destruction
  behavior does it have?
- What happens on invalid, default, zero/empty, and sentinel inputs?

Then record at least three concrete hypotheses about how the surface could be
wrong (for example: "callback can fire after reset", "size 0 skips the
flush", "caller X still passes the old enum"). All three being refuted in
verification is a good outcome, not wasted work.

## Async And Lifecycle

Answer per changed callback, timer, posted task, or async operation:

- Is the callback edge-triggered or level-triggered, and which do its
  consumers assume? Can wakeups be duplicated or lost?
- Can callbacks coalesce? Can the timer re-arm while armed? Can a repeated
  timer fire without state progress (zero or sub-resolution delays)? Under
  `TaskEnvironment::MOCK_TIME`, can a self-reposting task busy-loop or hang
  `FastForwardBy`?
- What invalidates in-flight work on reset and on destruction? Name the
  member that owns the in-flight state and the line that invalidates it.
- What happens if a callback re-enters the object, mutates it, or destroys
  it?
- Is cancellation an explicit handle or a weak no-op callback? Does canceled
  or destroyed work still consume shared resources (slots, buffers, sockets)?
  Does canceling one operation cancel, orphan, or corrupt sibling operations?
- Can a sequence-affine handle be destroyed on a different sequence? Can the
  final reference to a ref-counted object drop on a different sequence while
  it owns timers, a `WeakPtrFactory`, queues, or sequence-bound handles?
- Can the callback run before the initiating API returns, and does the API
  contract allow that?
- Can partial completion, backpressure, or cancellation orphan a caller
  callback or consume a shared resource twice?
- What is the object's lifetime obligation after invoking a user-provided
  callback?

Required traces — walk each that applies through the real code before leaving
this section:

- Synchronous completion and delayed completion of the same operation.
- Reset, disconnect, or destructor running before a posted callback runs.
- A callback that destroys its owner.
- Out-of-order use of the public API: call A arriving before expected event B.
- Multiple queued items — including the front item changing — for anything
  that queues, buffers, batches, or coalesces work.
- Partial completion and backpressure.
- Zero, default, and sentinel inputs where those states are meaningful.
- For shared resources with multiple clients, transactions, streams, locks,
  writers, or readers: at least one concurrent scenario where a participant
  lags, aborts, or joins after work has started.
- For processing that can be stopped, bypassed, or canceled mid-stream: the
  subsequent reads/writes, EOF, callbacks, cleanup, and invalidation of any
  partially transformed state.

Example pattern: `timer_.Start(..., BindOnce(&Foo::OnDone, Unretained(this)))`
plus a reset path that does not stop the timer. Ask what stops the callback
when `Reset()` or `~Foo()` runs first; if nothing does and the path is
production-reachable, that is a P1 use-after-free.

Example pattern: a zero-delay self-reposting task "to retry soon". Under mock
time this busy-loops `FastForwardBy` and hangs CI — more severe than the same
loop as a wall-time nuisance.

## State, Persistence, And Cache

- For secondary writes performed on behalf of a primary operation (metadata,
  index, journal, mirror): can a secondary failure fail an
  already-successful primary operation? Can it leave partial or corrupt
  secondary state that is observable rather than invalidated, doomed, or
  unreachable?
- Is each piece of metadata optional telemetry/timing, or load-bearing —
  needed to parse, select, or validate persisted data? Load-bearing metadata
  writes must be awaited or covered by a proven atomic/journaled invalidation
  path; on failure, the affected state must be invalidated or enter an
  explicit error path.
- Is an invalidation or mutation issue reachable under the production
  lifecycle model, or only under test lifecycles? If strictly test-time,
  test-scoped invalidation helpers beat runtime overhead on production hot
  paths — but verify the reachability claim instead of assuming it.
- For same-origin or security-origin caching optimizations, verify standard
  vs non-standard URL scheme properties against the registry constants in
  `url/url_util.cc` (such as `kFileSystemScheme` or `kBlobScheme`) instead of
  grepping for literal scheme strings.

Example pattern: the primary cache write succeeds, then a fire-and-forget
metadata write fails silently. If that metadata later selects or validates
the entry, the entry is selectable-but-corrupt — P2 until proven
unobservable.

## Integration And Feature Control

- Is the new behavior actually wired into the intended production path?
  Trace it from the public/config entrypoint through factories, decorators,
  feature flags, Mojo/CDP/service plumbing, and runtime call sites to the
  concrete code whose behavior changes.
- Does the disabled/default path still use the old behavior with minimal
  change? If the change sits on a shared path, identify that explicitly.
- Search for existing implementations of the same conceptual feature. Can the
  old and new paths both apply to the same operation?
- If new production behavior has broad blast radius, is there a
  `base::Feature`, Finch/enterprise/runtime kill-switch, or an explicit
  reason one is unnecessary?
- For each new gate or predicate, trace the real production values of the
  checked fields from their source to the decision point. Unit-test fixtures
  do not establish realistic headers, flags, state enums, or wrapper
  behavior.
- If a producing/writing feature depends on a consuming/reading feature,
  platform support, or another runtime flag: is partial enablement handled
  safely, or is the producing path guarded by the full dependency set?
- For `#if`, `#if defined(...)`, and `#if !defined(...)` gates: do the
  positive and negative branches match the feature name, the default build
  configuration, and the intended platform support?

Example pattern: `#if !defined(FEATURE_X)` guarding the *enabled*
implementation compiles the feature out exactly where it should exist. The
default build silently ships the old path, and every bot stays green.

## Contracts And API Shape

- Do header comments, method contracts, and documented invariants literally
  match the implementation? Treat contradictions as defects, not cosmetic
  nits.
- For every new predicate, gate, sentinel, or constant: find all uses and
  verify collaborating classes interpret it consistently.
- Is each `DCHECK` guarding a load-bearing internal invariant, or validating
  input that crosses an API boundary where release builds need explicit
  validation or a `CHECK`?
- Where the CL accepts a nullable callback, optional dependency, sentinel, or
  optional handle: is optionality part of the public contract, and do tests
  or callers rely on the absent-value path? Log a candidate either way; the
  fix-side tradeoff is evaluated during verification.
- Does the CL route a new path through a shared completion/cleanup helper?
  Trace every existing caller at the moment the helper is entered, and the
  helper's side effects (forced success, cleanup, callback state) on the new
  path.

## Tests As Specifications

Treat tests as executable specifications and test coverage as part of the
changed surface.

- Build a quick coverage map: changed public methods, enum/mode values, and
  notable branches versus the tests that exercise them. Explicitly flag
  untested default modes or core branches even when sibling modes are well
  covered — missing coverage for core/default behavior usually outranks a
  minor implementation nit.
- Look for tests covering: the default behavior path, not only alternate
  modes; each public option, mode, or flag; multi-item and multi-chunk
  behavior where applicable; boundary values (zero, empty, one, max,
  overflow, non-positive invalid input); async timing (immediate completion,
  delayed completion, posted dispatch, cancellation/reset before dispatch);
  reentrancy and destruction from callbacks when callbacks are introduced;
  and the original bug or prior-review issue, in a way that would fail
  without the fix.
- For each important test: would it fail without the claimed fix? Does it
  exercise the edge case named by its name or comment, or merely codify the
  current implementation? Trace the test's control flow and assertions
  rather than trusting its name.
- Check mock/fixture fidelity for semantic variables production keeps
  distinct: wire bytes vs decoded bytes, headers vs synthetic flags, feature
  defaults, platform state, persisted metadata, and wrappers. A passing test
  cannot stand in for a production trace when fixtures collapse those
  distinctions.
- When Gerrit or coverage tooling flags an uncovered changed line, trace the
  relevant tests to the exact branch or return statement. Common real misses:
  an early return distinct from a later "same value" return; a cap/clamp
  branch that needs prior state initialization before time advances;
  stale-generation callback drops covered for one callback family but not its
  sibling; helper guards that look unreachable because callers pre-check
  them. If the guard is reachable, ask for the smallest public-API test that
  hits it; if it is not, ask whether the defensive branch should be removed
  or justified.

Example pattern: the fixture sets `is_compressed = true` directly while
production derives it from `Content-Encoding` parsing. Every test passes, and
the derivation is never exercised — the tests prove the plumbing, not the
feature.

## Changed-Lines Polish

A quick final scan over newly added or modified lines for low-severity but
legitimate nits. Report real ones separately as optional P3 items instead of
dropping them from an otherwise-LGTM review.

- Limit style, formatting, and consistency nits to lines modified by the CL.
  If a correctness issue depends on unchanged code, explain how the CL made
  that code relevant to the review.
- For changed comments and API docs, verify each behavioral clause is
  literally supported by the implementation. Watch for misleading causal or
  exclusivity words such as "only", "whenever", "until", "unless",
  "intervening", "transition", and "edge". Ensure comments describe the right
  actor and signal direction; producer-side code should not be described as
  the consumer notifying itself unless that is literally the API model.
- In C++ comments, prefer backticks around identifiers and symbols instead of
  old-style `|name|` markers. Scan changed prose for typos and context-free
  caller guidance: if a comment says callers should pass null, use a
  sentinel, or choose a wrapper, it should name the concrete type/API where
  that choice exists.
- For FIFO/LIFO containers, prefer Chromium's `base::queue` / `base::stack`
  over `std::queue` / `std::stack` unless the code needs the standard
  underlying container's pointer/iterator stability or another documented
  property. `base::queue` uses `base::circular_deque` and is the usual
  lower-overhead choice for simple `emplace` / `front` / `pop` queues.
- For sequence-affinity checks, prefer `SEQUENCE_CHECKER()` with
  `DCHECK_CALLED_ON_VALID_SEQUENCE()` for debug-only validation. If code uses
  `base::SequenceCheckerImpl` directly, verify there is an intentional
  release-build `CHECK()` requirement before suggesting the macro; the macro
  compiles away outside DCHECK builds.
- Look for artifacts of deleted blocks: double blank lines, orphaned
  comments, redundant braces, now-empty sections, and stale TODO wording.
- Check vertical spacing in both directions: besides stray double blank
  lines, flag a *missing* blank line where one aids readability, for example
  above a comment that introduces a new logical block or member group.
  `clang-format` neither removes nor inserts these, so they survive a
  formatter check.
- Check that removed statements or call sites did not leave unused locals,
  stale test setup parameters, or unnecessary lambda captures.
- Audit linkage and visibility constraints before suggesting test hooks or
  toggles. Helpers and feature flags inside anonymous namespaces have
  internal linkage and cannot be referenced directly from another translation
  unit.
- Respect forward declarations in public headers. Avoid suggesting wrapper
  types that require full definitions of heavy or highly transitive types
  unless the API benefit clearly justifies the compile-time cost.
- If providing a patch snippet, make it a valid unified diff with accurate
  symbol names and non-overlapping per-file hunks.
