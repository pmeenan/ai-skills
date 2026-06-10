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

Discovery is a set of independent investigation threads, not one long read.
Runs of this skill show the same pattern across models: a single agent
sustains real depth on only one or two threads per pass — whichever grab its
attention — and everything else gets a shallow read. So do not execute
discovery as one agent. Build a thread plan and give every thread its own
subagent.

First, read `references/deep-dive-recipes.md` (at minimum the Context Rules
and each recipe's trigger line) and skim the discovery-checklist sections
matched by the risk map: the thread plan is only as good as the
orchestrator's grasp of what each thread is for.

**Thread plan.** From the risk map and the changed-surface inventory, list:

- One thread per deep-dive recipe whose trigger matches, scoped to the
  surfaces that triggered it (e.g. "Mode × Host-Capability Matrix for
  HttpCache::Writers"; "Error-Path Walk for the changed functions in
  http_cache_writers.cc").
- One thread per matched discovery-checklist section (async, state,
  integration, security, contracts, tests), scoped to its files. These
  threads also walk the section's required traces and, for the surfaces they
  own, answer the per-surface invariant questions with at least three
  IF/THEN/UNLESS hypotheses each.
- One mechanical-leads thread: run the commands, return every hit as a row.
- One holistic-and-polish thread: bug alignment and scope (does the CL solve
  the bug it cites, cohesively, at a reviewable size, without unnecessary
  abstraction?), idiom consistency (names, types, containers, callbacks,
  ownership, error handling vs nearby code), performance and memory cost,
  test-coverage proportionality, and the Changed-Lines Polish scan.

Order the plan by where P1s live, not by line count: teardown and error
paths, boundary arithmetic, cross-sequence handoffs, persisted-format
changes, and reentrancy first; renames and plumbing last. Ensure some thread
owns the smallest and least obvious files — the per-file ledger floor
depends on it.

Write the complete plan into the ledger before spawning anything: one line
per thread — name, scope, status (spawn / merged-into-⟨thread⟩ / skipped) —
with a reason for every merge and skip. Every matched recipe AND every
matched checklist section gets its own line, and the mechanical-leads and
holistic threads are always in the plan. Do not fold checklist-section
threads into recipe threads: in measured runs, an orchestrator that merged
the plan down to a few recipe threads skipped the section rules entirely,
and the skipped sections accounted for the missed bugs (fire-and-forget
metadata and redundant writes live in the State section; production-value
gates in Integration; guard-bypass scans in mechanical leads). Merging is
acceptable only for trivial CLs, and every merge must reappear in
Verification Notes.

Spawn one subagent per planned thread with a self-contained brief (see
Subagent Briefs); run threads in parallel where the harness allows. Overlap
between threads is fine — redundant coverage is how disjoint blind spots get
closed. If subagents are genuinely unavailable, execute the same plan
yourself as serial sweeps in plan order, completing each thread's rows
before starting the next.

Merge every returned row into the ledger verbatim. Do not judge severity,
likelihood, or fixability while merging; duplicates are collapsed and
quality is judged in verification.

### Pass 4 — Verification

Read `references/verification-and-fixes.md`, collapse duplicate ledger rows,
then verify candidates adversarially — with dedicated skeptic subagents
where available: one per serious-looking candidate (batch small related
ones), briefed to REFUTE it under the refutation standard. A skeptic that
cannot name the guard line or produce the safe trace has confirmed the
finding, not dismissed it.

For each candidate: build a minimal trace, challenge it, classify it, and
calibrate severity. Survivors become findings; refuted rows keep their
one-line refutation. A candidate that honest tracing can neither confirm nor
refute becomes a question for the CL owner in the review — never a silent
drop. Evaluate any fix you intend to propose against the fix heuristics in
the same file, and verify proposed fixes as carefully as bugs.

### Pass 5 — Synthesis

Run the final synthesis pass from the verification file: contradiction checks,
ledger reconciliation, and the not-verified list. Where subagents are
available, also spawn one challenger over the draft review, briefed with the
Final Synthesis checklist, to hunt contradictions, unaccounted ledger rows,
and miscalibrated severities before sending. Refresh Gerrit metadata as
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

## Subagent Briefs

Subagents start cold: no conversation memory and no loaded skill. A thread
is only as good as its brief, so fill in this template rather than composing
briefs freehand:

1. **Pin:** CL number, patchset, revision SHA, and how to obtain the diff —
   or the local file paths if the patchset is materialized.
2. **Scope:** the exact files and surfaces this thread owns. For broad CLs,
   partition threads by file group as well as by recipe/section.
3. **Procedure:** the exact reference file path and the section or recipe to
   read FIRST and then execute — e.g. "read
   `references/deep-dive-recipes.md`; apply the Context Rules, then run
   'Recipe: Error-Path Walk' on these functions." Point at the file rather
   than paraphrasing the recipe into the brief; paraphrases drop the steps
   that matter.
4. **Deliverable:** ledger rows only, no prose narrative. First a
   compliance matrix: one row per checklist question or recipe step in the
   brief's scope, each answered with concrete evidence (`path:line`) or
   N/A-with-reason — an unanswered row is a skipped check, and "no findings"
   without a complete matrix is not an acceptable return. Then the candidate
   rows: claim, repo-relative `path:line`, evidence, and either an
   IF/THEN/UNLESS hypothesis or a trace record
   (`scenario → lines visited → outcome`). Discovery threads leave severity
   blank.
5. **Rules:** discovery enumerates without filtering — "probably fine" rows
   are still rows; an incomplete recipe step (a guard you cannot name, a
   test you cannot find) is itself a row; the CL description is a claim to
   audit, not ground truth.

Verification skeptics swap (3)–(5) for the candidate rows under test, the
pinned patchset, and the instruction to read
`references/verification-and-fixes.md` first and refute under its standard.

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
   or not traced, and any important areas not verified. Reproduce the full
   thread plan with each thread's outcome: rows returned, or merged (name
   the absorbing thread), or skipped (with reason). A skipped or merged-away
   thread is an unverified area by definition.
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
