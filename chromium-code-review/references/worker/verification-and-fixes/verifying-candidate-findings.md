<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

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
