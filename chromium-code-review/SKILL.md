---
name: chromium-cl-reviewer
description: Reviews a Chromium CL when requested (e.g. "review CL 12345"). Checks bug alignment, patchset freshness, correctness, tests, style, performance, lifecycle, and Chromium conventions.
---

# Chromium CL Reviewer Skill

When the user asks you to review a Chromium CL, perform a rigorous review of
the latest patchset and produce actionable feedback suitable for Chromium code
review.

## 1. Fetch And Pin The Patchset

- Fetch CL details from Chromium Gerrit with the REST API:
  `https://chromium-review.googlesource.com/changes/chromium%2Fsrc~<CL>/detail?o=CURRENT_REVISION&o=CURRENT_COMMIT&o=CURRENT_FILES&o=MESSAGES&o=DETAILED_ACCOUNTS`
- Strip the Gerrit XSSI prefix (`)]}'`) before parsing JSON.
- Record the current patchset number, revision SHA, parent SHA, subject, status,
  owner, files changed, and CL description.
- Fetch the current revision ref and inspect the diff against its parent.
- If the checkout is not already on the target patchset, avoid permanently
  changing the user's workspace. If you temporarily check out the patchset for
  building or inspection, restore the original checkout.
- Refresh Gerrit metadata before final output. If a newer patchset appeared
  during review, inspect the inter-patchset delta before finalizing.
- State the exact patchset number and revision SHA in the review.

## 2. Gather Relevant Context

- Follow public Bug links and design docs referenced by the CL description when
  they are needed to judge intent, scope, or bug alignment.
- Audit the CL description, commit message, and referenced design docs against
  the current implementation; flag stale architectural claims when iterative
  refactoring made the docs no longer match the code.
- If the user provides prior review feedback, create an internal checklist:
  prior issue, expected fix, evidence in the current patchset, and residual
  risk. Explicitly report whether each prior issue is fixed, partially fixed, or
  still open.
- Compare the changed code to nearby Chromium patterns, ownership boundaries,
  and existing tests. When local precedent is unclear, use repository search or
  code search to find similar patterns in the module or wider tree.

## 3. Review Method

Use an adversarial mindset, but calibrate severity carefully. The goal is LGTM
with the smallest necessary set of blocking comments.

If subagents are available and the user explicitly permitted delegation or
parallel agent work, use them for independent passes such as:

- Clean-slate correctness / invariant / architecture review that is not anchored
  to prior findings.
- Async / lifecycle / cancellation review.
- Tests-as-specifications review.
- Fast style / consistency / common anti-pattern review.
- Synthesis pass that challenges findings, severities, and proposed fixes.

For non-trivial CLs, partition at least some deep-review work by subsystem or
file group, not only by review lens, so coverage is complete rather than
overlapping. Give each reviewer the same severity calibration and ask for
pre-classified findings.

If subagents are not permitted or available, perform these passes yourself.

## 4. Required Internal Artifacts

Before finalizing the review, create concise internal notes for these artifacts.
Do not dump them verbatim unless useful to the user; use them to force coverage.

**Changed surface inventory**
- List every changed public API, wrapper/decorator, factory, stateful helper,
  feature entrypoint, and production wiring point.
- For each surface, record its contract source, primary callers, old behavior,
  new behavior, mutable state, ownership/lifetime model, and tests.
- Mark whether the surface is production-reachable, test-only, or future-stack
  plumbing.

**Patchset delta inventory**
- For follow-up reviews, inspect both latest-vs-base and
  latest-vs-prior-reviewed-patchset.
- Resolve each prior finding as fixed, partially fixed, still open, obsolete, or
  superseded by a new issue, with evidence from the current patchset.
- After closing prior findings, run a clean-slate pass over the whole changed
  surface; prior feedback must not define the review boundary.

**Integration and disabled-path trace**
- Trace each new behavior from public/config entrypoint through factories,
  decorators, feature flags, Mojo/CDP/service plumbing, and runtime call sites to
  the concrete code that changes behavior.
- Verify the default/disabled path still uses the old behavior with minimal
  changes, or identify the shared-path change explicitly.
- Search for existing implementations of the same conceptual feature and check
  whether old and new paths can both apply.
- If new production behavior has broad blast radius, check for a `base::Feature`,
  Finch/enterprise/runtime kill-switch, or an explicit reason it is unnecessary.

**Risk-area map**
- Classify changed files by risk area: API contract, async/lifecycle,
  buffering/backpressure, persistence/cache state, security/privacy, memory
  ownership, threading/sequencing, performance, feature gating, integration
  wiring, and tests.
- Make at least one pass that is not anchored to the largest or most obvious
  class in the diff.

**Finding ledger**
- Account for every distinct finding from prior reports, subagents, and your own
  passes. Carry it into the final review, downgrade it, mark it fixed, or state
  why it is dismissed.
- When prior review comments are available, reconcile minor nits, optional
  cleanup, requested macros, and unresolved discussions too. Collapse or omit
  cosmetic items from the final review when appropriate, but do not assume they
  were resolved just because larger issues were fixed.
- Do not silently drop a finding during synthesis. Information lost at
  consolidation time is a common source of incomplete reviews.

## 5. Fresh Invariant Pass

After applying any prior-review checklist, do a clean-slate pass over each
changed public API or stateful helper. Prior feedback is useful context, but it
must not define the review boundary.

For each changed API or helper, identify:

- Public contract from headers, comments, tests, and nearby usage.
- Mutable state and invariants.
- State transitions across public calls.
- Async work, timers, callbacks, cancellation, and reset/destruction behavior.
- Invalid, default, and sentinel inputs.

Walk concrete traces through the code before finalizing findings. Include at
least one reset/destruction/cancellation trace for async code and one multi-item
trace for code that queues, buffers, batches, or coalesces work. Useful trace
shapes include: call A before event B, reset before a posted callback runs, a
front item changing, a callback re-entering, and a timer firing without state
change.

For async or stateful code, include traces for synchronous completion, delayed
completion, callback destroys owner, reset/disconnect/destructor before callback,
multiple queued items, partial completion/backpressure, and zero/default/sentinel
inputs when those states are meaningful.

## 6. Correctness Protocol

For each non-trivial correctness finding, verify it before presenting it:

- Build a minimal state or call trace from the code.
- Cite the exact code path and any relevant tests or comments.
- Classify the issue as a correctness bug, contract mismatch, missing test,
  performance risk, lifecycle risk, or polish.
- Check whether existing tests intentionally codify the observed behavior.
- Distinguish observation from proposed fix. Never recommend a concrete fix
  until it has been traced through relevant edge cases.
- Challenge the finding before presenting it: look for alternate caller paths,
  wrappers, overrides, feature gates, or invariants that would make the issue
  unreachable or lower severity.
- Review any proposed fix as carefully as the original bug. Trace it through
  boundary inputs, all affected state transitions, existing tests, and likely
  re-entrant/cancellation paths. If you cannot validate the fix, label it as an
  option needing verification rather than endorsing it.

Before proposing a fix, sanity-check it against common Chromium edge cases:

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

If the fix is plausible but not fully validated, phrase it as an option or ask
for clarification instead of presenting it as the correct change.

When a proposed fix changes API shape or caller obligations, compare plausible
alternatives before recommending one. Examples: reject invalid input vs accept a
sentinel, explicit cancellation handle vs weak callback pruning, edge-triggered
vs level-triggered notifications, and owned task cancellation vs caller-managed
weak callbacks.

## 7. Async And Lifecycle Checklist

For changes involving callbacks, timers, `WeakPtr`, `SequenceChecker`,
ref-counting, posted tasks, cancellation handles, Mojo pipes, sockets, or task
runners, explicitly consider:

- Edge-triggered vs level-triggered callback semantics.
- Duplicate wakeups vs lost wakeups.
- Callback coalescing and timer re-arming.
- Timer resolution, zero-delay re-arming, and whether repeated timers can fire
  without state progress.
- Reset and destruction invalidating in-flight work.
- Reentrant callbacks mutating or destroying the object.
- Explicit cancellation handles vs weak no-op callbacks.
- Whether canceled or destroyed work still consumes shared resources.
- Cancellation of current and sibling operations.
- Sequence-affine handles destroyed on a different sequence.
- Object lifetime after invoking user-provided callbacks.
- Whether a callback can run before the initiating API returns, and whether that
  is allowed by the API contract.
- Whether partial completion, backpressure, or cancellation can orphan a caller
  callback or consume shared resources twice.
- `TaskEnvironment::MOCK_TIME` behavior as well as wall-time behavior: zero or
  sub-resolution delays, self-reposting tasks, and timers that can busy-loop or
  hang under `FastForwardBy`.
- Ref-counted objects whose final reference may drop on a different sequence,
  especially when they own timers, `WeakPtrFactory`, queues, or sequence-bound
  handles.

## 8. Test Coverage Checklist

For new or changed APIs, look for tests covering:

- The default behavior path, not only alternate modes.
- Each public option, mode, or flag.
- Multi-item and multi-chunk behavior where applicable.
- Boundary values: zero, empty, one, max, overflow, non-positive invalid input.
- Async timing: immediate completion, delayed completion, posted dispatch, and
  cancellation/reset before dispatch.
- Reentrancy and destruction from callbacks when callbacks are introduced.
- The original bug or prior-review issue, in a way that would fail without the
  fix.

Treat tests as executable specifications. For important tests, ask whether the
test would fail without the claimed fix and whether it actually exercises the
edge case named by its test or comment. For every P1/P2 finding, suggest the
smallest regression test that would have caught it.

If a test name or comment claims a behavior, trace the test control flow and
assertions to confirm it proves that behavior rather than merely codifying the
current implementation.

Build a quick coverage map for changed public methods, enum/mode values, and
notable branches. Explicitly flag untested default modes or core branches even
when sibling modes are well covered.

Missing coverage for a core/default behavior is usually more important than a
minor implementation nit.

## 9. Review Criteria

Evaluate the CL against these areas:

**Bug Alignment**
- Does the CL solve the issue described by the bug and CL description?
- Is the scope appropriate for the stated bug and follow-up stack?

**Chromium Style And Consistency**
- Does the code follow Chromium style and nearby idioms?
- Are names, types, containers, callbacks, ownership, and error handling
  consistent with surrounding code?

**Design And Scope**
- Is the change appropriately sized and cohesive?
- Does it separate behavior changes from unrelated refactoring?
- Does it avoid unnecessary abstraction?
- If the CL is large, identify whether it is still reviewable or should be
  split.

**Quality And Correctness**
- Are edge cases and lifecycle transitions handled?
- Are performance and memory costs bounded or documented?
- Are CHECK/DCHECK/release behavior choices appropriate for the API contract?
- Is test coverage proportional to risk and blast radius?

**Contracts And Cross-Cutting Consistency**
- Do header comments, method contracts, and documented invariants match the
  implementation? Treat contradictions as defects, not cosmetic nits.
- For every new predicate, gate, sentinel, or constant, find all uses and verify
  collaborating classes interpret it consistently.
- Is a `DCHECK` being used for a load-bearing invariant or for input crossing an
  API boundary where release builds need explicit validation or `CHECK`?

**Integration And Feature Control**
- Is the new behavior actually wired into the intended production path?
- Does disabled/default behavior preserve the old path?
- Can existing and new implementations of the same feature both apply?
- Is there an appropriate kill-switch for broad runtime behavior changes?

## 10. Severity Calibration

- **P1:** Serious correctness, security, data loss, UAF, deadlock, or major
  regression risk. Must fix before landing.
- **P2:** Real correctness risk, missing coverage for core/default behavior,
  likely production regression, or contract ambiguity that can mislead callers.
  Normally fix before LGTM.
- **P3:** Documentation clarity, non-blocking test polish, minor efficiency,
  small consistency issues, or defensive improvements. Often optional or
  follow-up-worthy.
- In stack or foundation CLs, API contract mistakes can be P1 even before a
  production caller lands if follow-up CLs are likely to bake in the behavior.
- Avoid blocking on speculative problems, style preferences, or fixes whose
  tradeoffs have not been validated.
- Do not downgrade an API-shape, sentinel, or contract issue merely because it is
  documented if the documented behavior remains a footgun for downstream CLs.
- A mock-time hang that can block CI is more severe than a comparable real-time
  performance nuisance.

## 11. Final Synthesis Pass

Before final output, run a contradiction pass:

- Are findings derived from actual code traces rather than assumptions?
- Do proposed fixes preserve the documented contract and nearby Chromium idioms?
- Have API-shaping fixes been weighed against reasonable alternatives?
- Did the integration trace prove the code is wired into the intended runtime
  path, and did the disabled/default-path trace prove old behavior is preserved?
- Do tests prove the intended behavior, or merely compile/run nearby paths?
- Are prior-review findings clearly separated from new findings?
- Are any findings contradicted by another caller path, wrapper, override,
  feature flag, or test-only restriction?
- Are any issues only style preferences, and should they be P3 or omitted?
- Are severities calibrated for this CL's position in any larger stack?
- What did you not verify: tests not run, callers not traced, platform paths not
  checked, or assumptions that still need confirmation?

## 12. Communication And Tone

Follow Chromium review norms:

- Assume competence and goodwill.
- Lead with concrete findings, not broad praise.
- Explain why each requested change matters.
- Ask "why" when intent is unclear and the answer affects the review.
- Avoid bikeshedding; label optional polish as optional.
- Make next steps explicit: what blocks LGTM, what is optional, and what can
  land as follow-up.

## 13. Output Format

Format the final review as:

1. **Issues & Suggestions:** Findings first, ordered by severity, with
   file/line references and actionable guidance. Separate blocking issues from
   optional polish.
2. **High-Level Summary:** State whether the CL accomplishes its goal, name the
   patchset and revision SHA, and summarize bug alignment.
3. **Prior Review Follow-Up:** If prior issues were supplied, summarize their
   status with evidence.
4. **Positives:** Briefly note important good decisions.
5. **Questions:** Only questions whose answers affect correctness, API contract,
   or landing readiness.
6. **Verification Notes:** State tests run or not run, production wiring traced
   or not traced, and any important areas not verified.
7. **Next Steps:** State what is required before `+1 LGTM` and what is optional.

For Gerrit-ready review text, cite findings as repo-relative `path:line` against
the reviewed patchset and re-check line numbers before sending. Avoid leaking
local filesystem paths in comments meant for Gerrit.
