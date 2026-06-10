---
name: chromium-code-review
description: Reviews a Chromium CL when requested (e.g. "review CL 12345") and re-reviews updated patchsets against prior feedback. Checks bug alignment, patchset freshness, correctness, tests, style, performance, lifecycle, and Chromium conventions.
---

# Chromium CL Reviewer Skill

When the user asks you to review a Chromium CL, perform a rigorous review of the
latest patchset and produce actionable feedback suitable for Chromium code
review. Optimize for a clear landing recommendation with the smallest necessary
set of blocking comments.

The review runs in two phases with deliberately different mindsets:

- **Discovery** casts a wide net. Enumerate candidate issues cheaply; a wrong
  hypothesis costs nothing because verification filters it later. Most missed
  bugs are missed because the suspicion was never written down, not because
  verification failed.
- **Verification** is skeptical. Every candidate is traced through real code
  before it may appear in the review, and severity is calibrated there.

Keep the phases separate. Filtering during discovery is the main way reviews
miss real issues; skipping verification is the main way they report false ones.

## Reference Files

- `references/discovery-checklists.md`: per-risk-area questions, required
  traces, and mechanical lead generation. Read the sections matching the
  risk-area map **before** line-by-line analysis, not at synthesis time — the
  checklists only raise recall if they shape what you look for.
- `references/deep-dive-recipes.md`: step-by-step trace procedures with named
  work products — context rules, desk-check simulation, arithmetic drills,
  data lineage, and recipes for the killer bug classes (lifetime, container
  invalidation, error paths, state machines, teardown). Read alongside the
  checklists in Pass 3 for any CL touching arithmetic, buffers, lifetimes,
  state, persistence, or trust boundaries.
- `references/verification-and-fixes.md`: how to verify candidate findings,
  evaluate proposed fixes, and run the final synthesis pass. Read before
  promoting candidates into the review or endorsing any fix.

For a full non-trivial CL review all three files end up loaded; the only
question is when. Load the discovery checklists and recipes early, and the
verification file once the candidate list is built.

## Review Modes

- **Full CL review:** inspect the latest patchset against its parent, gather
  bug and design context, run the full procedure below, and produce
  Gerrit-ready comments.
- **Follow-up review:** run the full procedure including Pass 2
  (prior-feedback reconciliation). Prior feedback is context, not the boundary
  of the review: after resolving prior findings, discovery still covers the
  whole changed surface.
- **Targeted review:** focus on the requested subsystem, file, or risk area,
  loading only the matching discovery sections, but still report any serious
  blocker discovered nearby.
- **Short summary:** honor the shorter format, but still pin the patchset and
  disclose important unverified areas.

## Fetch And Pin The Patchset

- Fetch CL details from Chromium Gerrit with the REST API:
  `https://chromium-review.googlesource.com/changes/chromium%2Fsrc~<CL>/detail?o=CURRENT_REVISION&o=CURRENT_COMMIT&o=CURRENT_FILES&o=MESSAGES&o=DETAILED_ACCOUNTS`
- Strip the Gerrit XSSI prefix (`)]}'`) before parsing JSON.
- Record the current patchset number, revision SHA, parent SHA, subject, status,
  owner, files changed, and CL description.
- Fetch the current revision ref and inspect the diff against its parent.
- Avoid permanently changing the user's workspace. If you temporarily check out
  the patchset for building or inspection, restore the original checkout.
- Refresh Gerrit metadata before final output. If a newer patchset appeared
  during review, inspect the inter-patchset delta before finalizing.
- State the exact patchset number and revision SHA in the review.

## Gather Context

- Follow public Bug links and design docs referenced by the CL description when
  needed to judge intent, scope, or bug alignment.
- Audit the CL description, commit message, and referenced design docs against
  the current implementation. Flag stale architectural claims when iterative
  refactoring made the docs no longer match the code.
- Compare changed code to nearby Chromium patterns, ownership boundaries, and
  existing tests. When local precedent is unclear, search the module and then
  the wider tree.

## Review Procedure

Work through the passes in order. Every pass writes into the finding ledger.

### The Finding Ledger

Maintain one ledger across the whole review: every candidate issue, suspicion,
mechanical-lead hit, subagent finding, and prior-review item gets an entry with
a status (candidate, verified, refuted, fixed, partially fixed, still open,
obsolete, superseded). Carry every entry to synthesis: promote it, downgrade
it, or record in one line why it was dismissed. Never silently drop an entry —
information lost at consolidation time is a common source of incomplete
reviews.

The ledger must contain at least one entry per changed file — a candidate or
an explicit "clean because X". Attention collapses onto the first and largest
files; the per-file requirement keeps coverage even across the tail of the
diff.

### Pass 1 — Inventory

Build two artifacts from the diff before forming opinions:

- **Changed-surface inventory:** every changed public API, wrapper/decorator,
  factory, stateful helper, feature entrypoint, and production wiring point.
  For each, record its contract source, primary callers, old behavior, new
  behavior, mutable state, ownership/lifetime model, tests, and whether it is
  production-reachable, test-only, or future-stack plumbing.
- **Risk-area map:** classify changed files by risk area — API contract,
  async/lifecycle, buffering/backpressure, persistence/cache state,
  security/privacy, memory ownership, threading/sequencing, performance,
  feature gating, integration wiring, tests. The map selects which discovery
  sections to load in Pass 3.

### Pass 2 — Prior-Feedback Reconciliation (follow-up reviews only)

- Inspect both latest-vs-base and latest-vs-prior-reviewed-patchset.
- Resolve every prior finding in the ledger as fixed, partially fixed, still
  open, obsolete, or superseded, with evidence from the current patchset.
- Reconcile minor nits, optional cleanup, requested macros, and unresolved
  discussions too. Collapse or omit cosmetic items from the final review when
  appropriate, but do not assume they were resolved just because larger issues
  were fixed.

### Pass 3 — Discovery

Read the discovery-checklist sections selected by the risk map and
`references/deep-dive-recipes.md`, then:

- Apply the context rules from the recipes file before reviewing any hunk:
  full enclosing functions, class headers and destructors, and the parent
  revision of heavily changed files.
- Run the mechanical leads (commands listed in the checklist file). Every hit
  becomes a ledger candidate to explain or flag.
- Run every deep-dive recipe whose trigger matches the diff, and record the
  named work products in the ledger. An incomplete recipe step (a guard you
  cannot name, a test you cannot find) is itself a candidate.
- For each surface in the changed-surface inventory, answer the per-surface
  invariant questions and record **at least three candidate hypotheses** about
  how it could be wrong before declaring it clean. Write each hypothesis in
  falsifiable form — "IF ⟨sequence or input⟩ THEN ⟨bad outcome⟩ UNLESS
  ⟨guard not yet found⟩" — so verification knows exactly what guard to look
  for. Vague candidates ("might have threading issues") are not ledger
  entries. All three being refuted later is a good outcome, not wasted work.
- Walk the required traces for the matching risk areas; the checklist sections
  state them. Record each walked trace in the ledger as
  `scenario → lines visited → outcome`. A trace with no written outcome was
  not walked; "checked cancellation, looks fine" does not count.
- Trace integration: each new behavior from its public/config entrypoint
  through wiring to the concrete code that changes, and the disabled/default
  path to confirm old behavior is preserved (details in the integration
  checklist section).
- Answer the holistic questions: Does the CL solve the bug it cites, at a
  scope appropriate to the stated bug and follow-up stack? Is it cohesive, or
  does it mix behavior changes with unrelated refactoring? Is it reviewable at
  this size, or should it be split? Does it avoid unnecessary abstraction? Do
  names, types, containers, callbacks, ownership, and error handling match
  nearby Chromium idioms? Are performance and memory costs bounded or
  documented? Is test coverage proportional to risk and blast radius?
- Make at least one pass that is not anchored to the largest or most obvious
  file class in the diff.

Allocate depth by where P1s live, not by line count: teardown and error
paths, boundary arithmetic, cross-sequence handoffs, persisted-format
changes, and reentrancy harbor most serious bugs; mechanical renames and
plumbing harbor few.

Do not judge severity, likelihood, or fixability during this pass; that is
verification's job.

### Pass 4 — Verification

Read `references/verification-and-fixes.md`, then verify every ledger
candidate: build a minimal trace, challenge it, classify it, and calibrate
severity. Candidates that survive become findings; the rest are recorded as
refuted with a one-line reason. A candidate that honest tracing can neither
confirm nor refute becomes a question for the CL owner in the review — never
a silent drop. Evaluate any fix you intend to propose against the fix
heuristics in the same file.

### Pass 5 — Synthesis

Run the final synthesis pass from the verification file: contradiction checks,
ledger reconciliation, and the not-verified list. Refresh Gerrit metadata as
described in Fetch And Pin, then produce output.

## Finding Format

Record and report every finding with:

- **Claim:** one sentence describing concrete behavior, not vibes.
- **Location:** repo-relative `path:line` against the reviewed patchset.
- **Evidence:** the minimal state/call trace or citation that demonstrates it.
- **Severity:** P1/P2/P3 per the calibration below.
- **Fix status:** validated fix, option needing verification, or no fix
  proposed.
- For P1/P2 findings: the smallest regression test that would have caught it.

## Severity Calibration

- **P1:** Serious correctness, security, data loss, UAF, deadlock, or major
  regression risk. Must fix before landing.
- **P2:** Real correctness risk, missing coverage for core/default behavior,
  likely production regression, or contract ambiguity that can mislead
  callers. Normally fix before LGTM.
- **P3:** Documentation clarity, non-blocking test polish, minor efficiency,
  small consistency issues, or defensive improvements. Often optional or
  follow-up-worthy.

Calibration notes:

- In stack or foundation CLs, API contract mistakes can be P1 even before a
  production caller lands if follow-up CLs are likely to bake in the behavior.
- Do not downgrade an API-shape, sentinel, or contract issue merely because it
  is documented if the documented behavior remains a footgun for downstream
  CLs.
- A mock-time hang that can block CI is more severe than a comparable
  real-time performance nuisance.
- Avoid blocking on speculative problems, style preferences, or fixes whose
  tradeoffs have not been validated.

## Subagent Strategy

If subagents are available, use them for non-trivial CLs where independent,
parallel coverage is worth the overhead. Useful passes include:

- Clean-slate correctness / invariant / architecture review.
- Async / lifecycle / cancellation review.
- Tests-as-specifications review.
- Fast style / consistency / common anti-pattern review.
- Synthesis pass that challenges findings, severities, and proposed fixes.

For broad CLs, partition at least some deep-review work by subsystem or file
group, not only by review lens. Give each reviewer the finding format, the
severity calibration, the phase discipline (discovery enumerates without
filtering; verification prunes), and the deep-dive recipes matching their
slice, and ask for pre-classified findings. Merge
subagent output into the ledger rather than pasting it through to the review
unverified. If subagents are unavailable or overkill, perform the passes
yourself in the procedure order.

## Output Format

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

For full CL reviews, append compact **Gerrit-Ready Comments** unless the user
asks for a short summary only:

- **Main body:** brief landing-readiness summary, blockers, optional items,
  prior review status, and verification notes.
- **Replies to existing unresolved threads:** file and thread line, status, and
  the exact response. Do not open duplicate new threads for an existing topic.
- **New inline comments:** repo-relative file, exact line or range, verbatim line
  text from the reviewed patchset, and concise comment text. Prefix optional
  polish with `nit:`.

For Gerrit-ready text, cite findings as repo-relative `path:line` against the
reviewed patchset, extract quoted code verbatim, and re-check line numbers
before sending. Avoid leaking local filesystem paths in comments meant for
Gerrit.

## Tone

Follow Chromium review norms: assume competence and goodwill, lead with concrete
findings, explain why each requested change matters, ask "why" when intent is
unclear and affects correctness, label optional polish as optional, and make
landing blockers explicit.
