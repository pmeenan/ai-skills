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
  - **Burden of Proof Requires Reachable Harm & Trusted-Caller Calibration:** A missing `if` check or omitted pre-filter is ONLY a blocking bug if a reachable trace produces a concrete bad state (memory corruption, security bypass, data loss, or broken invariant). Defense-in-depth checks on inputs supplied exclusively by trusted browser-process code (e.g. re-verifying a browser-computed staging digest at commit time, or guarding against `>2 GiB` buffers that cannot cross a single Mojo message) and hazards that require a caller to violate a documented "call at most once" contract (e.g. calling `Finish()` after `Discard()`) are at most **P3** (or a P3 doc/behavior mismatch if `Discard()` after `Finish()` deletes the committed file because `path_` is not cleared), never P1/P2 blockers, unless reachable from untrusted input without a browser bug.
  - **Explicit `TODO`-Tracked Scope & Open Reviewer Threads:** In foundation or stacked CLs, missing follow-up integrations that are already tracked by an explicit in-code `TODO` (such as `BrowsingDataRemover` wiring or storage quota enforcement) or by an open Gerrit thread waiting on the reviewer's own input are not new P2 blockers: refute them as `REFUTED` (citing the `TODO` `path:line` or open thread ID) or record a non-blocking design question (`UNPROVEN`), unless the code being landed actively causes harm today (for example, an unguarded OTR profile writing to the regular profile directory). Likewise, generic requests to "add UMA histograms, tracing, or benchmarks" in a foundation CL with no callers and no `histograms.xml` in scope are `REFUTED`.
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
- For style claims, cite authority applicable to the changed directory.
  Blink/WebKit naming guidance is not a Chromium-wide convention, a
  mechanical `bool` hit without local authority or concrete callsite ambiguity
  is REFUTED, and valid UTF-8 section symbols (`§`, e.g. `§ 8.4`) in
  specification citations are permitted by Chromium style (`REFUTED`).
