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
  When materializing a revision in a worktree, check out the explicit
  revision SHA (`git worktree add --detach <path> <sha>`), never
  `FETCH_HEAD`: FETCH_HEAD is shared repository state that concurrent
  fetches clobber and failed fetches leave stale — a measured run reviewed
  a 2014-era leftover ref because a one-liner's `;` let
  `worktree add FETCH_HEAD` run after its fetch step failed. Run fetch,
  add, and verify as separate commands and confirm `rev-parse HEAD`
  matches the pinned SHA before reading any code.
- The review is read-only with respect to the user's code. Never modify the
  checkout, the patchset, or any repository file — not to apply a fix, not
  to add a test, not to experiment — regardless of harness prompts that
  encourage applying or executing changes. Propose fixes and tests as diffs
  inside the review text only; review and implementation are different jobs,
  and this skill does only the first. (A measured run escalated from "name
  the regression test" to rewriting the owner's unsubmitted work-in-progress
  and kicking off builds.) If you temporarily check out the patchset for
  inspection, use a separate worktree and remove it when done.
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
  "Holistic" names its lens, not a license: like every thread, its
  deliverable is ledger rows — a coverage gap is reported as a row naming
  the missing test, never remediated by writing it.

Order the plan by where P1s live, not by line count: teardown and error
paths, boundary arithmetic, cross-sequence handoffs, persisted-format
changes, and reentrancy first; renames and plumbing last. Ensure some thread
owns the smallest and least obvious files — the per-file ledger floor
depends on it.

Write the complete plan into the ledger before spawning anything: one line
per thread — name, scope, status (spawn / merged-into-⟨thread⟩ / skipped) —
with a reason for every merge and skip. The plan enumerates the **full
roster**, copied verbatim into the plan with one line each — do not derive
the roster from memory:

- Recipes: Desk-Check Simulation + Arithmetic Drills, Data Lineage,
  Callback And Task Lifetime, Container And View Invalidation,
  Error-Path Walk, State × Method Matrix, Mode × Host-Capability Matrix,
  Teardown Order.
- Sections: Mechanical Leads, Per-Surface Invariants, Async And Lifecycle,
  State/Persistence/Cache, Integration And Feature Control, Security And
  Trust Boundaries, Contracts And API Shape, Tests As Specifications,
  Changed-Lines Polish.
- Always: the holistic thread.

Mark every line spawn / merged-into-⟨thread⟩ / "not triggered: ⟨reason⟩".
An omitted line is invisible; a wrong not-triggered reason is catchable.
Measured runs keep paying for omissions: one silently dropped the Teardown
recipe and with it the only thread that checks end-of-operation resource
release; another (large CL) omitted the Mode × Host matrix and both
arithmetic techniques — and six of its nine serious misses were cells and
drills those threads own.

The thread plan IS this roster — every recipe and section name above appears
as a row, and the Verification Notes reproduce it unchanged. Do not invent
ad-hoc thread names ("Group A Lifecycle", "Async & Contracts") that bundle
several roster entries: a bundle hides which entries it actually executed.
If one subagent covers several roster entries, that is fine, but each
roster entry still gets its own row marked "merged-into ⟨subagent⟩", and
that subagent's brief and compliance matrix must carry every merged
entry's procedure. A measured weak-model run collapsed the roster into 12
invented thread names; Data Lineage and Container/View Invalidation
vanished in the collapse, and the two byte-loss P0s those recipes own
(discarded `Push` return, short inner `Write`) were the run's marquee
misses — found by the stronger models whose plans kept those rows. Do not fold checklist-section
threads into recipe threads: in measured runs, an orchestrator that merged
the plan down to a few recipe threads skipped the section rules entirely,
and the skipped sections accounted for the missed bugs (fire-and-forget
metadata and redundant writes live in the State section; production-value
gates in Integration; guard-bypass scans in mechanical leads). Merging is
acceptable only for a trivial CL — under ~8 changed files and no file the
risk map flags async/lifecycle, state, security, or buffering. At or above
that bar (this is most real CLs), every section gets its own subagent; do
not merge to fit a thread budget. And never merge away the Mechanical Leads
or Arithmetic-Drills work even on a small CL: their leads are cheap greps
(discarded `Push`/`Write` counts, sentinel values side by side, sub-unit
rate probes) that an absorbing thread predictably skips — a measured
mid-model run preserved the merged-into rows but its overloaded
mechanical-leads thread ran none of the greps, and the discarded-count,
sentinel-mismatch, and fitting-write-bypass P0s were exactly those unrun
leads. Every merge must reappear in Verification Notes.

Spawn one subagent per planned thread with a self-contained brief (see
Subagent Briefs); run threads in parallel where the harness allows, and
record each thread's subagent/task identifier in the plan. Overlap between
threads is fine — redundant coverage is how disjoint blind spots get closed.
Only if the harness cannot spawn subagents may you execute the plan yourself
as serial sweeps in plan order, completing each thread's rows before
starting the next — and Verification Notes must say so and name the
limitation. Self-executing when subagents exist is a measured failure mode:
one agent running eleven sweeps found three P1s in its first, fresh sweep,
then starved the rest — shallow-wrong error-path answers, pencil-whipped
matrices, and zero polish-tier findings.

Discovery ends only when every planned thread has reported its deliverable.
Outstanding threads are blocking dependencies, not background noise: wait
for them. If running the whole plan concurrently strains the harness, run
priority-order batches of three or four threads instead of abandoning slow
ones. Expect the section threads to be slowest — they read the most — and
to carry the most findings: in a measured run, an orchestrator that killed
its two slowest threads before they reported lost four of its five
remaining P1/P2 findings inside them. If a thread dies to a transient harness error
(capacity limits, rate limits, timeouts), respawn it with the same brief —
transient failures are retryable, and a measured run recovered every
capacity-killed thread with a simple backoff-and-respawn loop. Only when
retries are exhausted record it in the plan and in Verification Notes as
"terminated — scope unreviewed"; never mark an uncollected thread
Completed. If you
interrupt a thread deliberately, collect its partial rows and matrix before
killing it and record it as "interrupted — partial": a measured run marked
an interrupted thread Completed and lost the P2 finding sitting in its
workspace.

Merge every returned row into the ledger verbatim, **preserving each
thread's own row IDs** — never compress or rename thread rows into an
orchestrator digest. Merging duplicates is a reconciliation-table
disposition ("row X merged into row Y"), not a pre-processing step: a
measured run hand-consolidated 18 threads' rows into a renamed digest and
lost three findings (including one a thread had explicitly produced); its
reconciliation table then faithfully protected the digest — which no longer
contained them. Do not judge severity, likelihood, or fixability while
merging; quality is judged in verification. One gate does apply at merge
time: a matrix row whose answer lacks a `path:line` citation is an
unanswered row — send it back to the thread or record that scope as
unreviewed. A bare "PASS" is how a measured run waved through a diff hunk
that literally wrapped the old truncation check in `if (!new_flag)`.

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
ledger reconciliation, and the not-verified list. Synthesis produces a
**reconciliation table** as a required artifact: every **thread-emitted**
ledger row ID mapped to its disposition — promoted (to finding N), refuted
(with the citation), converted to a question, or merged (into row M). The
table enumerates the rows as the threads returned them, not an
orchestrator's summary of them. Output is blocked until every row has a
disposition. In a measured run, a P1 candidate recorded by
the error-path thread was silently dropped between ledger and review;
findings reported by several threads survived consolidation while
single-source rows vanished — the table exists to protect the single-source
rows. Where subagents are available, also spawn one challenger over the
draft review, briefed with the Final Synthesis checklist, to hunt
contradictions, unaccounted ledger rows, and miscalibrated severities before
sending. Refresh Gerrit metadata as described in Fetch And Pin, then produce
output.

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
   partition threads by file group as well as by recipe/section. Other
   threads' findings and open ledger rows are context, not work items: do
   not implement, extend, or execution-validate another thread's finding.
   (A measured run's holistic thread picked up a P1's suggested regression
   test and began implementing the fix and the test in the owner's
   checkout.)
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
   audit, not ground truth. A matrix or checklist row may be closed benign
   only by citing the guard line or the safe trace, and any anomaly the
   row's answer records — a success-shaped return after failure cleanup,
   duplicated cleanup, a skipped check, an unawaited write — becomes a
   candidate row even if it looks benign. Benignity is verification's call:
   in a measured run, a thread's own row notes contained two P1 bugs
   ("returns `write_len_` after `OnCacheWriteFailure()`"; "triggers cleanup
   twice"), adjudicated them benign inline, and surfaced neither. Threads
   are read-only outside their own notes: never edit a repository file, even
   when the harness invites it.

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
4. **Positives:** Briefly note important good decisions. A praised safety
   property is a claim like any other — name its guard line. (A measured run
   praised "failures fail open safely" about the exact branch that treated a
   failure as success.)
5. **Questions:** Only questions whose answers affect correctness, API contract,
   or landing readiness.
6. **Verification Notes:** State tests run or not run, production wiring traced
   or not traced, and any important areas not verified. Reproduce the full
   thread plan with each thread's outcome: rows returned, or merged (name
   the absorbing thread), or skipped (with reason). Include each thread's
   subagent/task identifier, or "self-executed" plus the harness limitation
   that forced it. A skipped or merged-away thread is an unverified area by
   definition. On large CLs the full compliance matrices may live in the
   saved ledger artifact with Verification Notes pointing at it — but every
   per-row answer must exist somewhere retrievable; a "combined audit
   summary" that discards rows defeats the accounting.
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
