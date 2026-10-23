# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Contents

- Verifying Candidate Findings
- Skeptic Verdicts
- Execution-Based Verification
- Evaluating Fixes
- Root-Cause Trigger Planning
- Root-Cause, Layering, And Fix Optimality
- Final Synthesis Pass
- Verdict Alignment And Gerrit Output Rules

## Verifying Candidate Findings

Verify each non-trivial candidate before presenting it. Prefer concrete code
traces over speculative concerns — but spend the trace: refute candidates with
code, not from memory.

- Build a minimal state or call trace from the code that demonstrates the
  issue, or demonstrates its absence.
- Read the candidate's `Candidate descriptors` row and close every declared
  obligation. Do not substitute a local syntax observation for a
  `local-proof`, `base-contract`, `caller-reachability`, `callee/backend-implementation`,
  `async-operation-owner`, `destruction/cancellation`, `platform-branches`,
  or `style-authority` trace.
- Cite the exact code path and any relevant tests or comments.
- Classify the issue: correctness bug, contract mismatch, missing test,
  performance risk, lifecycle risk, or polish.
- Check whether existing tests intentionally codify the observed behavior —
  but verify that a CL-introduced test or comment does not itself codify a
  misreading of a governing external specification or subsystem invariant in
  `context.md`.
- Challenge the finding: look for alternate caller paths, wrappers, overrides,
  feature gates, or invariants that make it unreachable or lower its severity.
- Apply Universal Verification Principles during refutation:
  - **Contract Authority Hierarchy & Verbatim Spec Quotes (External Specs & Subsystem Invariants Outrank Local Comments/Tests):** Normative external specifications (W3C, WHATWG, WICG, IETF RFCs, WebIDL/Mojo wire contracts) and documented subsystem invariants (`context.md`, `callers/directory-docs.md`) outrank CL-local header comments, inline comments, and CL-introduced unit tests. Local comments or unit tests that codify a misreading of the governing external specification **never** refute a spec-mismatch candidate; unless the CL explicitly marks the divergence as an intentional staged `TODO` with safe gating/fallback, confirm the mismatch (or record `UNPROVEN` as an owner question when specification intent is genuinely ambiguous). Whenever quoting a specification in a verdict or finding, quote the spec's exact words verbatim (e.g. `"origins"`, `"globally disclosable"`), never paraphrasing code identifiers inside quotation marks or citing unverified section numbers.
  - **Documented Intent Overrides Syntactic Omissions:** Within the bounds of the Contract Authority Hierarchy above, adjacent inline comments, docstrings, and header contracts are binding design specifications for internal implementation choices. An omitted branch or conditional that is explicitly documented in code comments or header docs as intentional design is NOT a defect unless it violates a governing external specification, base-interface contract, or higher-level subsystem invariant.
  - **Burden of Proof Requires Reachable Harm, Stubbed-Consumer Discounting, & Trusted-Caller Calibration:** A missing `if` check or omitted pre-filter is ONLY a blocking bug if a reachable trace produces a concrete bad state (memory corruption, security bypass, data loss, or broken invariant). Defense-in-depth checks on inputs supplied exclusively by trusted browser-process code (e.g. re-verifying a browser-computed staging digest at commit time, guarding a browser-constructed file path where a side effect inside `DLOG(ERROR)` is unreachable in production, or guarding against `>2 GiB` buffers that cannot cross a single Mojo message), interface contract discrepancies where no external caller can hold or mint the required token/handle (e.g. an untrusted WebUI origin that cannot call a restricted Mojo capability), and hazards that require a caller to violate a documented "call at most once" contract (e.g. calling `Finish()` after `Discard()`) are at most **P3** (`nit:`), never P1/P2 blockers, unless reachable from untrusted input without a browser bug. Likewise, if a state propagation or bookkeeping bug (such as copying a permission flag by value instead of sharing state) only affects a consumer method that is explicitly unimplemented/stubbed (`TODO`, `NOTIMPLEMENTED`, `kOperationFailed`) in the current CL, cap severity at **P3** (non-blocking) and frame it as "fix before or with the follow-up CL that implements `<consumer>`," never P1/P2.
  - **Cross-Context / IPC Delivery-Channel Plausibility:** Whenever a candidate claims a token, handle, capability, or message can be transferred between two execution contexts, origins, `StorageKey`s, frames, or processes, verify that each named transport/delivery mechanism (`postMessage`, `BroadcastChannel`, `SharedWorker`, `ServiceWorker`, `IndexedDB`, `window.opener`, etc.) can actually connect those two contexts under web-platform partitioning and frame-messaging rules (for example, `BroadcastChannel`, `SharedWorker`, and `ServiceWorker` are partitioned by `StorageKey` / top-level site and cannot cross top-level sites, and fenced frames block embedder `postMessage`). Prune any impossible delivery mechanism via an amendment before confirming the finding.
  - **`SequenceBound` / Single-Sequence FIFO Serialization & Error Latching:** Before confirming a P1/P2 concurrency or state-machine corruption claim on a UI-thread Mojo wrapper, check whether all backend operations funnel through a single `base::SequenceBound<T>` or `SequencedTaskRunner` (running FIFO on one sequence) that latches error state on failure, and whether normal renderer callers serialize operations (e.g. `WritableStream`). If backend state cannot be corrupted and only UI-thread status callback ordering on out-of-order raw Mojo IPC is affected, calibrate as **P3**, never P1/P2.
  - **Experimental-Flag & Deliberate-Test Cross-Check:** When evaluating a Mojom/IDL comment or contract mismatch, check whether the WebIDL method is gated behind an unenabled `Experimental` runtime feature flag (or another finding notes it is dead in the default config) and whether a test in the CL explicitly asserts the implemented behavior. If it is not web-exposed by default, has no security/privacy impact, and appears deliberate from the test, calibrate as a **P3 question/nit** (asking whether the mojom comment or the implementation should change), never a P2 blocker.
  - **Explicit `TODO`-Tracked Scope, Launch-Gate Notes, & Open Reviewer Threads:** Before confirming that a request, factory, or pipeline stage lacks an observer, token, or subsystem integration (for example, `devtools_observer` or `devtools_request_id` being `mojo::NullRemote()` / empty), trace the factory construction helper and its caller chain (such as `NavigationRequest` calling `URLLoaderFactoryParamsHelper::CreateForEarlyHintsPreload`) for existing `TODO(crbug.com/...)` comments. In any CL—including small bug fixes as well as foundation or stacked CLs—missing integrations or pre-existing gaps that are already tracked by an explicit in-code `TODO` (such as `BrowsingDataRemover` wiring, storage quota enforcement, or missing DevTools instrumentation on Early Hints preloads) or by an open Gerrit thread waiting on the reviewer's own input are not P1/P2 findings: refute them as `REFUTED` (citing the `TODO` `path:line` or open thread ID) or record a non-blocking design question (`UNPROVEN`), unless the code being landed actively causes new harm today (for example, an unguarded OTR profile writing to the regular profile directory). However, when a CL is the first to web-expose writes or persistence behind a default-disabled feature flag (`FEATURE_DISABLED_BY_DEFAULT` / `status: "test"`) and defers cumulative quota, eviction, or resource caps via a `TODO`, surface it as an explicit non-blocking **Launch-Gate Note** in both the review summary (`draft-parts/FRAME.md`) and the Patchset-Level Gerrit comment (`gerrit-parts/FRAME.md`), noting that the default-off flag is why it doesn't block this CL and that it must land before any field trial or default-on launch. Likewise, generic requests to "add UMA histograms, tracing, or benchmarks" in a foundation CL with no callers and no `histograms.xml` in scope are `REFUTED`.
  - **Untouched-File Attribution, Test-Layer Adequacy, & Consolidation:** Cross-check every claim about what the CL modifies against `pin.md` and `gerrit/changed-files.txt`. Never confirm a candidate that attributes existing code in an untouched file to the CL or faults the CL for not unit-testing a helper in a file the CL did not modify. When a CL already tests the modified function at the appropriate test layer and/or includes an end-to-end test proving the core new behavior works (for example, verifying an Early Hints preload fails with `ERR_INTERNET_DISCONNECTED` under offline emulation), requests for extra test permutations (such as latency/throughput cases in addition to offline) or assertions on downstream stages unchanged by the CL are at most optional **P3** suggestions or `REFUTED`, never P2 blockers. Conversely, **missing a required test layer** on newly introduced code is **P2**: (a) adding new browser-process Mojo implementations (`*Impl`) that parse untrusted input or run a state machine with **zero unit tests (`*_unittest.cc`)**—relying only on `EvalJs` browsertests where Blink pre-validation prevents reaching browser-side `ReportBadMessage`, origin/OTR/partition guards, or concurrent/interleaved Mojo states—is **P2**; and (b) implementing a web-exposed API governed by a W3C/WHATWG/WICG spec and asserting portable JS spec behavior only via C++ `EvalJs` in `browsertest.cc` with **zero WPTs (`external/wpt/` or `wpt_internal/`)** is **P2** (noting that WPTs may land in this CL or an immediately stacked CL). Group all missing test-layer and test-placement candidates for the feature (unit tests, WPTs, browser-only integration cases, and stack-constructed C++ unit tests placed inside `browsertest.cc`) into **one consolidated P2 finding** (plus a short pointer comment on `BUILD.gn`), keeping separate P3 nits only for bugs inside specific existing test bodies (such as dead branches or overly broad `try/catch` blocks).
  - **Concrete Trigger Implementation, `base::NotFatalUntil`, & Origin Attribution:** Do not confirm a synchronous callback-reentrancy or cancellation crash (for example, "if a `URLLoaderThrottle` cancels synchronously in `WillStartRequest`") as P1/P2 based only on what an abstract interface permits; trace the concrete throttles/delegates registered on that code path and name a real implementation that takes the synchronous branch. When assessing `CHECK` crash severity, inspect whether the `CHECK` uses `base::NotFatalUntil::M<N>` (non-fatal dump report before milestone `N`). Assign `Origin` strictly: if a downstream quirk or ordering hazard (such as `WarnUnusedPreloads` firing on failed preloads, or map insertion occurring after `CreateLoaderAndStart`) already existed before the CL and the CL only lets an intended feature (like DevTools emulation) reach that path, its origin is `pre-existing`, never `CL-introduced`.
  - **Producer/Consumer Symmetry (Read vs. Write Scoping):** Query/read paths scope to the key space of stored data, not to the write-side preconditions of the caller. Cache, index, and storage lookup APIs must match the full potential key space of stored data, regardless of caller context.
- To refute a candidate, name the specific guard (the line) or documented design contract/comment that proves safe behavior, or produce the concrete trace that completes safely. "Looks handled" or "the caller probably checks" is not a refutation — it is the shallow read the candidate exists to challenge. For hypotheses written as IF/THEN/UNLESS, refutation means filling in the UNLESS with a citation.
- If honest tracing can neither confirm nor refute a candidate, do not drop
  it: convert it into a question for the CL owner in the review's Questions
  section, stating what you traced and what remains unproven. Uncertainty
  rounded down to "probably fine" is how reviews miss real bugs.
- Never edit a discovery ledger to record a verdict. Record refutation in the
  skeptic verdict file and reconciliation; discovery rows remain append-only.
  If a worker must correct its own earlier row, use the normative Amendments
  section from templates.md, preserving the original row and ID.
- Matrix cells marked incompatible-but-guarded are verification inputs too:
  confirm that the named guard actually guards the cell's scenario, on the
  path the scenario takes. In a measured run a cell cited `ShouldTruncate()`
  as the guard for `StopCaching(keep_entry=true)` — but that guard only runs
  on the failure path, and the success path skipped it entirely.
- Distinguish observation from proposed fix. Never recommend a concrete fix
  until it has been traced through the relevant edge cases below.
- For async-lifetime claims, identify who retains the caller buffer or
  operation state after an `ERR_IO_PENDING`-style return, then trace
  cancellation and callback invalidation through destruction on each backend.
  Distinguish between *synchronous local scope* (where a local variable lives
  for the duration of the loop/operation) and *asynchronous handoffs* (where the
  initiating method returns while background tasks run). If an asynchronous
  helper receives a raw child pointer (`parent->child.get()`), verify that the
  callback closure holds an owning anchor (`scoped_refptr<Parent>` or
  `std::unique_ptr`) until completion. Local variable death, declaration order,
  or callback capture syntax alone cannot confirm a use-after-free without
  tracing the asynchronous completion path. **Standard `PostTaskAndReplyWithResult`
  reply ownership:** when a service posts background work via
  `PostTaskAndReplyWithResult` with value-copied inputs and passes the caller's
  `OnceCallback` directly as the reply (without dereferencing `this` or service
  members in the reply), the service's destruction before the reply runs is safe
  and callers guarding their own state with `WeakPtr` is the standard Chromium
  contract (`REFUTED`); also do not claim `weak_factory_` is "unused" when
  `GetWeakPtr()` is public API.
- For style and idiom claims, cite authority applicable to the changed directory
  and check both prior-patchset history (`ledger/PR.md`) and local convention in
  the changed and sibling directories:
  - Blink/WebKit naming guidance is not a Chromium-wide convention, a mechanical
    `bool` hit without local authority or concrete callsite ambiguity is
    `REFUTED`, and valid UTF-8 section symbols (`§`, e.g. `§ 8.4`) in
    specification citations are permitted by Chromium style (`REFUTED`).
  - Never confirm a style or idiom candidate that reverts a deliberate
    prior-patchset fix recorded in `ledger/PR.md` or contradicts a documented
    lifetime/error-path contract in adjacent header comments (specifically: a
    `base::OnceCallback` parameter that is only conditionally consumed so the
    caller can invoke `mojo::ReportBadMessage` before the callback is destroyed
    on validation-failure paths uses a non-const lvalue reference
    `OnceCallback&` or pointer, not `OnceCallback&&`, which Google C++ style
    discourages when the callee does not unconditionally move-from the
    parameter).
  - Before confirming any style/convention claim not backed by an explicit rule
    in the Chromium C++ Style Guide (for example, claiming `// static` comments
    above out-of-line static member definitions are non-standard when they are
    standard Chromium idiom), grep the changed directory and sibling directories
    in the pinned worktree; refute (`REFUTED`) any claim that contradicts
    prevalent Chromium usage.

## Skeptic Verdicts

Every candidate examined in verification gets exactly one verdict row in
its batch's `verification/V⟨batch⟩.md` file (shape in
`references/templates.md`), with ID `V⟨batch⟩-⟨n⟩` and a reference to the
candidate row under test. Three verdicts exist, each with mandatory
evidence fields — a verdict missing its fields is not a verdict:

- **CONFIRMED** requires: the completing trace
  (`scenario → lines visited → bad outcome`), a severity proposal matched to
  the anchor table in `references/synthesis-and-output.md` (name the anchor
  and argue any delta), and an
  origin label (`CL-introduced`, `introduced-in-PS⟨N⟩`, or `pre-existing`).
- **REFUTED** requires: the guard's `path:line`, documented design contract/comment citation, or the concrete safe trace
  that completes without the bad outcome. For IF/THEN/UNLESS hypotheses,
  refutation means filling the UNLESS with a citation. Speculative "looks handled" or
  "the caller probably checks" are not refutations; explicit code comments, documented invariants, or proof of safe/idempotent execution are valid refutations.
- **UNPROVEN** requires: what was traced, what remains unproven, and a
  drafted question for the CL owner. UNPROVEN rows go to the review's
  Questions section — never to the bin.

Each verdict file also contains `## Trace closure` and
`## Verified affinity`. Emit exactly one closure row for every obligation
declared by that candidate—no omissions and no invented extras. Results are
`PROVES CANDIDATE`, `REFUTES CANDIDATE`, `NEUTRAL`, `OPEN`, or
`NOT APPLICABLE — reason`, each with code evidence or an explicit
`evidence-exception:`. CONFIRMED/REFUTED may not retain OPEN obligations;
UNPROVEN must name at least one. Verified affinity restates or corrects the
base/interface, invariant owner, violated invariant, state/transition, likely
fix layer, and related symbols after tracing.

A skeptic that cannot produce REFUTED's required fields has confirmed the
finding, not dismissed it. When the decisive evidence legitimately has no
`path:line` — an absence proof ("no other caller exists": cite the search
run), tool output, or a spec/standard citation — write
`evidence-exception: <nonempty reason and the actual evidence>` in the
evidence field; the validator rejects CONFIRMED/REFUTED rows that have
neither a citation nor a nonempty exception, and an exception is itself a
claim the synthesis challenger may re-check. When verification runs without subagents, the
orchestrator holds itself to the same schema — one verdict row per
candidate, same mandatory fields.

A candidate with a proposed duplicate merge is the sole exception to the
one-verdict-per-candidate rule. It may share the surviving candidate's verdict
only after reconciliation verifies equal trigger, violated invariant, and bad
outcome, with citations. Similar location or fix is insufficient. A rejected
merge returns to verification; it is never silently dismissed.

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
- **Protocol event ordering and preconditions.** Never propose or endorse a fix
  that emits secondary or extra-info protocol events (such as
  `DevToolsObserver::OnRawRequest` / `Network.requestWillBeSentExtraInfo` with a
  synthesized `devtools_request_id`) when the primary lifecycle event
  (`Network.requestWillBeSent`) is never emitted for that request. Emitting
  orphan secondary events violates protocol ordering contracts.
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

## Root-Cause Trigger Planning

The Root-Cause Planner reads the actual candidate and verdict files; the
orchestrator must not infer triggers from terse status messages. It writes one
Trigger Accounting row for every CONFIRMED or UNPROVEN verdict, every
candidate with a proposed fix, and every inventory scope marked `root-cause
required`. Inventory scopes ensure risky changes receive a layering pass even
when discovery found no defect candidate. Schedule root-cause work when any of
these is true:

- proposed P1 or P2;
- risky P3 whose severity depends on reachability or invariant ownership;
- any concrete fix recommendation, regardless of severity;
- performance optimization, flaky-test fix, async/lifecycle change,
  state-machine change, cache/throttle, persisted format, or new state holder;
- a candidate whose local symptom may be shared across caller families.

Rows that meet no trigger remain in the plan as `not applicable — trigger
absence proved by <T IDs>`. Batch scheduled work by related invariant and trace cost; serious
candidates normally stand alone or in very small groups, and no fixed quota
may combine unrelated traces. Keep every generated brief bounded. Assign
distinct zero-padded `RC001`, `RC002`, ... IDs. Generated root-cause briefs inherit the
common directives, authority boundary, append/retry, and partial-return
contract from templates.md.

Before this planning step, the global Invariant Affinity Reconciler assigns
every CONFIRMED/UNPROVEN candidate and verdict to one `RF<number>` family and
runs the six-row cross-batch consistency audit in templates.md. Root-cause
planning consumes whole families, not isolated line items. Sharding may extract
descriptors but may not make independent family assignments.

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
  chosen fix; a plausible code sketch is not an applicable edit. When the
  selected range `path:start-end` ends with a blank separator line in the pinned
  file, the replacement block must preserve that trailing blank line so applying
  the suggestion does not concatenate adjacent blocks or functions. In any P3 /
  style / assertion / test-cleanup finding on a modified file, scope the
  requested changes strictly to lines, call sites, and classes touched or
  extended by the CL's diff hunks — never bundle untouched pre-existing lines or
  unmodified sibling classes in the same file into the ask. Use the
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

- Consult `callers/directory-docs.md` directly (in addition to `context.md`) to
  read the verbatim ancestor `README.md` architecture sections, `DEPS`
  `include_rules` / `specific_include_rules` / `!` temporary allowlist rules, and
  `OWNERS` constraints for the affected directories. Use those subsystem docs to
  confirm which class or layer is the documented canonical invariant owner and
  whether a shared helper already exists before endorsing a new wrapper, cache,
  or cross-directory dependency.
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
  duplicate, or reorder completion. When a fix threads an async result struct
  across `PostTaskAndReplyWithResult` or `SequenceBound::AsyncCall(...).Then(...)`
  into a `WeakPtr`-guarded callback, verify that every resource on the reply
  struct (such as `scoped_refptr`, `std::unique_ptr`, file descriptors, or Mojo
  handles) uses RAII cleanup in its destructor if the `WeakPtr` is invalidated
  before the reply runs.

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

## Final Synthesis Pass

Before final output, run a contradiction pass over the ledger and the draft
review:

- Does the final review account for every ledger entry — promoted at its
  calibrated severity (including downgrades), merged, or dismissed with a
  recorded reason?
- Did the root-cause/layering pass run for every triggering candidate or fix,
  and are any reopened rows verified, refuted, or converted into questions?
- Is the selected fix layer the invariant owner or intentionally below/above
  it for a cited reason?
- Are findings derived from actual code traces rather than assumptions?
- **Citation, symbol, variable, and line-number verification:** Does every
  `path:line` or `path:start-end` citation in `draft-parts/*.md`,
  `gerrit-parts/*.md`, `draft-review.md`, and `gerrit-comments.md` resolve to an
  existing file in the pinned worktree with in-bounds line numbers
  (`1 <= start <= end <= total_lines`)? Does every `- Line: \`...\`` quote in
  `gerrit-parts/*.md` and `gerrit-comments.md` match the pinned worktree's line
  text verbatim? Do all backticked functions, methods, classes, member
  variables, parameters, and constants cited at a `path:line` (or in the
  finding's `Claim`, `Location`, `Evidence`, `Fix status`, and Gerrit `Comment`)
  actually exist in the cited file and at the cited line (not hallucinated
  identifiers, wrong `.h` vs `.cc` files, or off-by-one line numbers pointing to
  an adjacent declaration)? In any P3 / style / assertion / test-cleanup finding
  on a modified file, are all cited line numbers and class names in `Evidence`,
  `Fix status`, and Gerrit `Comment` strictly inside the CL's diff hunks (never
  bundling untouched pre-existing lines or unmodified sibling classes in the same
  file)? And if a finding names cross-context delivery mechanisms (such as
  `BroadcastChannel`, `postMessage`, `SharedWorker`, or `fenced-frame`), can
  each named channel actually cross the boundary in question under web-platform
  partitioning rules?
- Do proposed fixes preserve the documented contract and nearby Chromium
  idioms? Have API-shaping fixes been weighed against reasonable alternatives?
- **Cross-finding fix compatibility & no grab-bag bundling:** Do any two
  promoted findings recommend mutually incompatible fixes (for example, one
  finding recommending asynchronous `ImportantFileWriter::ScheduleWrite()` while
  another recommends propagating a synchronous `bool SaveMetadata()` return
  value), or repeat the same prose across multiple findings? Reconcile
  conflicting fix recommendations so they agree on a coherent architecture,
  trim duplicated sub-points, and never bundle unrelated observations into a
  single multi-topic finding.
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

Scale this pass by evidence cards rather than by ingesting the entire record.
The Challenge Planner sizes content and structural shards by their actual
assigned input bytes. Six finding/question cards and 200 reconciliation rows
are starting heuristics, not hard caps. Each shard must fit 35% of a known
context window or the 128 KiB unknown-capacity fallback, subject to its
resolved tier's input budget. Every item/row appears in exactly one shard.

For a large draft, challengers consume immutable indexed draft/Gerrit sections,
not the whole assembled output. Content shards read only assigned sections,
their bounded cards, and the global frame. Structural shards read assigned row
ranges, the gate, and frame. One global shard checks section order, hashes,
headings, verdict/finding consistency, and Gerrit target coverage from compact
indexes. Each challenge row records the section hashes audited. A collector
verifies exact card/row/section coverage and exactly one `global:consistency`
token, then writes the compact challenge index.

Any draft change after challenge creates a new draft revision and requires a
new full challenge generation: fresh plan, fresh shard IDs/artifacts, and a
fresh collected index. Rechecking only the previously reported problems is not
a contradiction pass and cannot satisfy the gate. The only exception is an
explicitly clerical issue closed by the collector's authenticated exact-text
projection receipt; it proves the complete current bytes from the preserved
challenged bytes and leaves the immutable shard unchanged. Gerrit freshness is checked
only after the last collected challenge and is rechecked after every revision.

## Verdict Alignment And Gerrit Output Rules

### Verdict Formatting

Avoid contradictory verdicts. If there is a **CL-introduced** (or
`introduced-in-PS<N>`) blocking defect (P1 or P2), the verdict must explicitly
state that the change is blocked. Pre-existing codebase issues (`Origin:
pre-existing`) are informational follow-ups and NEVER block `LGTM`. Do not
combine approvals with blocking conditions.

- *Incorrect:* "LGTM with optional Polish (P3) after resolving one blocking
  P2 defect"
- *Incorrect:* "Not LGTM until the pre-existing P1 ordering bug is fixed"
- *Correct:* "Not LGTM until the CL-introduced P2 telemetry bug is fixed;
  remaining items are optional P3."
- *Correct:* "LGTM with optional P3 polish (plus one pre-existing follow-up
  noted for reference)."

### Gerrit-Ready Comments Constraints

When formatting comments meant to be copy-pasted directly to Gerrit:

- **No local paths:** Neither `draft-review.md` nor `gerrit-comments.md` may
  ever contain local absolute file paths (e.g. `/usr/local/...`,
  `/codereview/worktrees/...`, `/tmp/...`, `/home/...`) or local `file:///`
  URLs. Use repo-relative references only (e.g.
  `net/http/http_cache_writers.cc:1010`).
- **Patchset-level summary comment required:** `gerrit-comments.md` must always
  include a `## Main comment` (or `## Patchset-Level Comment`) section before
  inline comments (emitted via `gerrit-parts/FRAME.md` in sharded drafts) that
  gives the author a concise landing-readiness summary, blocking `P1`/`P2` vs
  optional `P3` counts, prior review status, and any non-blocking **Launch-Gate
  Note** for explicit `TODO`-tracked production prerequisites (such as
  quota/eviction wiring on a default-off feature). Keep internal `Verification
  Notes` (such as `"No local test execution was performed during this review"` or
  thread-audit summaries) inside `draft-review.md` only — do not include an
  internal `Verification notes:` bullet in `gerrit-comments.md`.
- **Verbatim quoted code line required:** Every new inline comment in
  `gerrit-parts/<item>.md` and `gerrit-comments.md` must include `- Line: \`<verbatim line from the pinned patchset>\`` copied directly from the card's `Verbatim changed line` field (which itself must be extracted verbatim from the worktree at the pinned revision, never paraphrased from memory).
- **No placeholder or fake inlines:** do not output generic placeholder
  inline comments (e.g., `L16500 (General Nit) // General Nit`). General
  feedback belongs in the main comment body; inline comments must target
  real, modified lines of code.
- **Concise, query-based inlines (1–3 sentences):** frame inline feedback as
  concise questions or direct observations (1–3 sentences stating the concrete
  bug/impact and the ask, e.g., "Can we gate these success-only metrics...?").
  Prefix every P3 optional-polish inline comment with `nit:`. Never paste
  multi-paragraph trace dumps, internal gate metadata (`Rows`, `Synthesis item`,
  `Fix status`, anchor names), or unmodified external subsystem `path:line`
  coordinates into author-facing Gerrit inline comments (name the external
  class/method concisely in prose instead). In any P3 style, assertion, or
  test-cleanup inline comment on a modified file, cite and request changes only
  on lines and classes touched by the CL's diff hunks — never bundle untouched
  pre-existing lines or unmodified sibling classes in the same file. Avoid
  repeating the same suggestion across multiple files/declarations; place a
  single comment at the most relevant site.
- **Make applicable edits directly actionable:** every promoted finding has a
  `Suggested edit` decision inherited from its evidence card. Mark it
  `applicable` only when the validated fix is fully determined, replaces one
  contiguous changed-side range of at most 10 lines, needs at most 20
  replacement lines, and requires no coordinated edit, API/design choice,
  generated output, or unseen context. Then include the exact same fenced
  `suggestion` block in both the review finding and its Gerrit fragment. The
  block contains replacement text only — no diff markers, ellipses,
  placeholders, or explanatory prose — and its target range must be the lines
  Gerrit should replace. When the replaced range `path:start-end` ends with a
  blank separator line in the pinned file, preserve that trailing blank line in
  the `suggestion` block so applying the edit does not join adjacent blocks.
  This is an apply-ready edit, not pseudocode.
  Re-check the path is normalized and repo-relative, the positive range is
  in-bounds and intersects the pinned patch's changed side, and the selected
  text exactly equals those lines in the pinned revision. The Gerrit fragment
  contains exactly one standalone target declaration (`path:start-end` or a
  `###` heading with that value), so the fence cannot accidentally bind to a
  citation in explanatory prose.
- **Explain omissions:** when any eligibility condition fails, write
  `Suggested edit: omitted — <specific reason>` in the review finding and
  keep the Gerrit comment to concise fix guidance. Typical reasons are
  coordinated multi-location changes, an unresolved owner/API choice,
  replacement too large for one inline, or a fix not yet validated. Never
  force a locally neat snippet that repairs only one symptom of a root family.
- **Exhaustive coverage without truncation:** Every promoted finding (each a
  card in `synthesis/index.md`) writes one exact
  `gerrit-parts/<item>.md` target/comment fragment and measured
  `output-coverage.tsv` row; the fragment bytes occur exactly once in
  `gerrit-comments.md`. Merged duplicates are already folded into their
  surviving finding, so they need no separate comment. Do not sample,
  compress, or truncate promoted findings to shorten output length. Presenting
  100% of actionable bugs upfront is mandatory to prevent multiple review
  rounds.
- **Normalize threads before replying:** `comments.json` is keyed by file and
  contains CommentInfo arrays. Flatten with paths retained, group replies by
  transitive `in_reply_to` root, order within each thread by `updated` (stable
  ID tie-break), and take unresolved state from that thread's latest comment.
  Target the normalized root/latest IDs in `gerrit/unresolved-threads.json`.
  Never use the last file-array element or the change's latest message as
  unresolved-thread state, never emit a `### Thread <root_id>` or `- Reply-To:
  root <root_id>, latest <latest_id>` reply for a thread that is already
  resolved on Gerrit (absent from `gerrit/unresolved-threads.json`), never
  attach `- Reply-To:` to a `### path:line` inline comment whose `path` or
  `line` differs from the thread root's location in
  `gerrit/unresolved-threads.json` (place replies to existing threads under
  `## Replies to existing unresolved threads` at the thread's own `path:line` and
  omit `Reply-To:` on standalone inline comments at other locations), and when
  an open thread is awaiting a decision from the reviewer running the review
  (`Reviewer email` in `pin.md`), present a `[Reviewer decision on thread <id>:
  Option A ... / Option B ...]` placeholder in `## Main comment` instead of
  writing third-person `"awaiting reviewer confirmation"` or posting a
  prescriptive agent reply.
