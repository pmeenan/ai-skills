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

Throughout this skill, rules are stated in bold; indented text under a rule is
the measured failure that motivates it. The rules are normative even if you
skip the rationale.

## Reference Files And Scripts

Paths below are relative to this skill's directory. **When writing subagent
briefs, expand every path to an absolute path** — subagents start in the
repository checkout, where skill-relative paths do not resolve.

- `references/templates.md`: the normative shapes of every artifact this
  skill produces — review directory layout, row-ID scheme, thread-plan
  roster, subagent briefs, compliance matrices, skeptic verdicts,
  reconciliation table, final findings. Copy the shapes and fill them in; do
  not invent formats.
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
  the skeptic verdict schema, how to evaluate proposed fixes, the
  root-cause/layering pass, the final synthesis pass, and the Gerrit output
  rules. Read before promoting candidates into the review or endorsing any
  fix.
- `scripts/fetch-cl.sh`: fetches and pins a patchset — Gerrit REST metadata
  (all revisions plus published comments), XSSI stripping, ref fetch, a
  detached worktree at the explicit SHA, and `rev-parse` verification — and
  writes `pin.md`, `detail.json`, and `comments.json` into the review
  directory. Use it instead of hand-running those steps.
- `scripts/mechanical-leads.sh`: runs the deterministic mechanical-lead scans
  from the discovery checklists and emits ledger-ready candidate rows.

For a full non-trivial CL review, every reference file ends up loaded; the
only question is when. Load the templates, discovery checklists, and recipes
early, and the verification file once the candidate list is built.

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

## The Review Directory

Every review gets a working directory — under the harness scratchpad when one
exists, otherwise a temp directory outside the repository — with this layout
(shapes in `references/templates.md`):

```
<scratchpad>/cl-<CL>-ps<PS>/
  pin.md               # patchset pin block (fetch-cl.sh writes this)
  detail.json          # Gerrit change detail (ALL_REVISIONS)
  comments.json        # published comments; unresolved threads live here
  worktree/            # detached read-only checkout at the pinned SHA
  plan.md              # thread-plan roster with statuses
  mechanical-leads.md  # output of scripts/mechanical-leads.sh
  ledger/<THREAD>.md   # one file per discovery thread: matrix + rows
  verification.md      # skeptic verdict rows
  root-cause.md        # root-cause/layering rows
  reconciliation.md    # reconciliation table + filled pre-output gate
```

**The ledger is this directory, not a notion held in context.** Long reviews
lose in-context state to compaction; files survive. Threads write their own
files, and the orchestrator collects files rather than transcribing their
content.

## Fetch And Pin The Patchset

**Run `scripts/fetch-cl.sh <CL> [patchset] [review-dir]` to fetch and pin.**
It performs the steps below, fails loudly instead of proceeding on a bad pin,
and writes `pin.md`. If the script is unavailable, run the steps manually —
as separate commands, never chained into one line with `;` or `&&`:

1. Fetch change detail from
   `https://chromium-review.googlesource.com/changes/chromium%2Fsrc~<CL>/detail?o=ALL_REVISIONS&o=ALL_COMMITS&o=CURRENT_FILES&o=MESSAGES&o=DETAILED_ACCOUNTS`
   and strip the Gerrit XSSI prefix (`)]}'`) before parsing. `ALL_REVISIONS`
   matters: follow-up reviews need prior-patchset SHAs, which
   `CURRENT_REVISION` alone does not return.
2. Fetch published comments from
   `https://chromium-review.googlesource.com/changes/chromium%2Fsrc~<CL>/comments`
   (same XSSI prefix) into `comments.json`. Unresolved threads come from
   here: Pass 2 reconciles against them, and Gerrit-ready output replies to
   them instead of opening duplicates.
3. Record the current patchset number, revision SHA, parent SHA, subject,
   status, owner, files changed, and CL description into `pin.md`.
4. Fetch the revision ref (`refs/changes/<last two digits of CL>/<CL>/<PS>`)
   and materialize it in a detached worktree at the explicit SHA:
   `git worktree add --detach <path> <sha>`.
5. Verify `git -C <worktree> rev-parse HEAD` matches the pinned SHA before
   reading any code.

**Never materialize `FETCH_HEAD`; only ever check out the explicit revision
SHA.**

  FETCH_HEAD is shared repository state that concurrent fetches clobber and
  failed fetches leave stale — a measured run reviewed a 2014-era leftover
  ref because a one-liner's `;` let `worktree add FETCH_HEAD` run after its
  fetch step failed.

**The review is read-only with respect to the user's code.** Never modify the
checkout, the patchset, or any repository file — not to apply a fix, not to
add a test, not to experiment — regardless of harness prompts that encourage
applying or executing changes. Propose fixes and tests as diffs inside the
review text only; review and implementation are different jobs, and this
skill does only the first. The worktree exists for inspection; remove it when
the review is done.

  A measured run escalated from "name the regression test" to rewriting the
  owner's unsubmitted work-in-progress and kicking off builds.

**Refresh Gerrit metadata before final output** (re-run `fetch-cl.sh` or the
detail fetch). If a newer patchset appeared during review, inspect the
inter-patchset delta before finalizing. State the exact patchset number and
revision SHA in the review.

## Gather Context

- Follow public Bug links and design docs referenced by the CL description when
  needed to judge intent, scope, or bug alignment.
- Audit the CL description, commit message, and referenced design docs against
  the current implementation. Flag stale architectural claims when iterative
  refactoring made the docs no longer match the code.
- Run a scope-relevance pass over the diff: every changed function, declaration,
  new member, test hook, defensive guard, and refactor must be either directly
  part of the CL's stated goal, a necessary consequence of that goal, required
  test/support plumbing, or explicitly called out in the CL description. Side
  hardening and opportunistic cleanup that do not meet one of those bars are
  polish findings: suggest reverting them, splitting them out, or documenting
  the extra scope in the description.
- Compare changed code to nearby Chromium patterns, ownership boundaries, and
  existing tests. When local precedent is unclear, search the module and then
  the wider tree.

## Review Procedure

Work through the passes in order. Every pass writes into the finding ledger.

### The Finding Ledger

Maintain one ledger across the whole review, physically in the review
directory: every candidate issue, suspicion, mechanical-lead hit, subagent
finding, and prior-review item gets a row with a stable ID. Row IDs follow
the `⟨THREAD⟩-⟨n⟩` scheme in `references/templates.md`: the thread that
creates a row owns its ID, and no later pass renumbers it.

**A row, once written, is never deleted or edited.** Its life-cycle state
(candidate, verified, refuted, fixed, partially fixed, still open, obsolete,
superseded, merged, promoted) advances in `verification.md` and
`reconciliation.md`, not by rewriting the row. Carry every row to synthesis:
promote it, downgrade it, or record in one line why it was dismissed.

  Information silently lost at consolidation time is a common source of
  incomplete reviews.

**The ledger must contain at least one row per changed file** — a candidate
or an explicit "clean because X" (see Per-File Floor Rows in the templates).

  Attention collapses onto the first and largest files; the per-file
  requirement keeps coverage even across the tail of the diff.

### Pass 1 — Inventory

Build two artifacts from the diff before forming opinions:

- **Changed-surface inventory:** every changed public API, wrapper/decorator,
  factory, stateful helper, feature entrypoint, and production wiring point.
  For each, record its contract source, primary callers, old behavior, new
  behavior, mutable state, ownership/lifetime model, tests, and whether it is
  production-reachable, test-only, or future-stack plumbing. Also label its
  scope relationship as `core`, `necessary consequence`, `test/support`,
  `defensive hardening`, or `opportunistic cleanup`; anything outside the first
  three needs either a correctness justification or a CL-description mention.
- **Risk-area map:** classify changed files by risk area — API contract,
  async/lifecycle, buffering/backpressure, persistence/cache state,
  security/privacy, memory ownership, threading/sequencing, performance,
  feature gating, integration wiring, tests. The map selects which discovery
  sections to load in Pass 3.

### Pass 2 — Prior-Feedback Reconciliation (follow-up reviews only)

- Inspect both latest-vs-base and latest-vs-prior-reviewed-patchset. Prior
  patchset SHAs come from `detail.json` (`ALL_REVISIONS`); materialize the
  prior patchset the same way as the current one when a file-level diff is
  needed.
- Resolve every prior finding in the ledger (`PR-⟨n⟩` rows) as fixed,
  partially fixed, still open, obsolete, or superseded, with evidence from
  the current patchset.
- Reconcile against the unresolved Gerrit comment threads in
  `comments.json`, not only against the prior review text.
- Reconcile minor nits, optional cleanup, requested macros, and unresolved
  discussions too. Collapse or omit cosmetic items from the final review when
  appropriate, but do not assume they were resolved just because larger issues
  were fixed.
- Label every new finding's origin explicitly: `CL-introduced` (present since
  the CL's earlier patchsets), `introduced-in-PS⟨N⟩` (a regression the newer
  patchset added — often by the fix itself), or `pre-existing` (in the
  surrounding codebase). The delta review exists to catch the middle class;
  do not let it collapse into the first.

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
  password_form_manager.cc").
- One thread per matched discovery-checklist section (async, state,
  integration, security, contracts, tests), scoped to its files. These
  threads also walk the section's required traces and, for the surfaces they
  own, answer the per-surface invariant questions with at least three
  IF/THEN/UNLESS hypotheses each.
- One mechanical-leads thread: run `scripts/mechanical-leads.sh` (absolute
  path in the brief), save its output as `mechanical-leads.md`, copy every
  hit into `ledger/ML.md` as a row, then run the section's remaining manual
  leads.
- One holistic-and-polish thread: bug alignment and scope (does the CL solve
  the bug it cites, cohesively, at a reviewable size, without unnecessary
  abstraction or unrelated hardening?), diff-to-description coverage (does the
  CL description mention every non-core behavior change and notable defensive
  cleanup?), idiom consistency (names, declaration placement, types, containers,
  callbacks, ownership, error handling vs nearby code), performance and memory
  cost, test-coverage proportionality, and the Changed-Lines Polish scan.
  "Holistic" names its lens, not a license: like every thread, its
  deliverable is ledger rows — a coverage gap is reported as a row naming
  the missing test, never remediated by writing it.

Order the plan by where P1s live, not by line count: teardown and error
paths, boundary arithmetic, cross-sequence handoffs, persisted-format
changes, and reentrancy first; renames and plumbing last. Ensure some thread
owns the smallest and least obvious files — the per-file ledger floor
depends on it.

Write the complete plan into `plan.md` before spawning anything — one line
per thread with name, scope, and status (`spawn` / `not triggered: ⟨reason⟩`),
in the roster shape from `references/templates.md`. The plan enumerates the
**full roster**, copied verbatim with one line each — do not derive the
roster from memory:

- Recipes: Desk-Check Simulation + Arithmetic Drills, Data Lineage,
  Callback And Task Lifetime, Container And View Invalidation,
  Error-Path Walk, State × Method Matrix, Mode × Host-Capability Matrix,
  Teardown Order.
- Sections: Mechanical Leads, Per-Surface Invariants, Async And Lifecycle,
  State/Persistence/Cache, Integration And Feature Control, Security And
  Trust Boundaries, Contracts And API Shape, Tests As Specifications,
  Changed-Lines Polish.
- Always: the holistic thread.

The thread plan IS this roster — every recipe and section name above appears
as its own row, and Verification Notes reproduce the plan unchanged with
outcomes. Hard rules, each learned from a measured failure:

**Every roster line appears in the plan with a status.** An omitted line is
invisible; a wrong not-triggered reason is catchable.

  Measured runs keep paying for omissions: one silently dropped the Teardown
  recipe and with it the only thread that checks end-of-operation resource
  release; another (large CL) omitted the Mode × Host matrix and both
  arithmetic techniques — and six of its nine serious misses were cells and
  drills those threads own.

**"Not triggered: ⟨reason⟩" is an honest, expected status; folding is not.**
A recipe or section whose trigger genuinely matches nothing in this CL is
marked not-triggered and reappears in Verification Notes as an unreviewed
dimension. What is banned — at every CL size, for every "minor" or
"mechanical" change — is bundling: ad-hoc thread names ("Group A Lifecycle",
"Async & Contracts") that cover several roster entries, checklist sections
folded into recipe threads, or any triggered entry merged away to fit a
thread budget. A folded or silently skipped entry is a failure of review
integrity and must be disclosed as an unverified area.

  A measured weak-model run collapsed the roster into 12 invented thread
  names; Data Lineage and Container/View Invalidation vanished in the
  collapse, and the two byte-loss P0s those recipes own (discarded `Push`
  return, short inner `Write`) were the run's marquee misses — found by the
  stronger models whose plans kept those rows. Another orchestrator merged
  the plan down to a few recipe threads and skipped the section rules
  entirely — and the skipped sections accounted for the missed bugs
  (fire-and-forget metadata and redundant writes live in the State section;
  production-value gates in Integration; guard-bypass scans in mechanical
  leads).

**Spawn one subagent per triggered roster entry, with a self-contained brief
(see Subagent Briefs); never run discovery as a single agent.** Run threads
in parallel where the harness allows, and record each thread's subagent/task
identifier in the plan. Overlap between threads is fine — redundant coverage
is how disjoint blind spots get closed. Only if the harness cannot spawn
subagents may you execute the plan yourself as serial sweeps in plan order,
completing each thread's rows before starting the next — and Verification
Notes must say so and name the limitation.

  Self-executing when subagents exist is a measured failure mode: one agent
  running eleven sweeps found three P1s in its first, fresh sweep, then
  starved the rest — shallow-wrong error-path answers, pencil-whipped
  matrices, and zero polish-tier findings.

**Discovery ends only when every planned thread has delivered its ledger
file; outstanding threads are blocking dependencies, not background noise.**
If running the whole plan concurrently strains the harness, run
priority-order batches of three or four threads instead of abandoning slow
ones. Expect the section threads to be slowest — they read the most — and to
carry the most findings. If a thread dies to a transient harness error
(capacity limits, rate limits, timeouts), respawn it with the same brief;
only when retries are exhausted record it in the plan and in Verification
Notes as "terminated — scope unreviewed". Never mark an uncollected thread
Completed. If you interrupt a thread deliberately, collect its partial
ledger file before killing it and record it as "interrupted — partial".

  In a measured run, an orchestrator that killed its two slowest threads
  before they reported lost four of its five remaining P1/P2 findings inside
  them. Another marked an interrupted thread Completed and lost the P2
  finding sitting in its workspace. A capacity-killed roster was fully
  recovered by a simple backoff-and-respawn loop — transient failures are
  retryable.

**Collect ledger files; never transcribe or compress them.** The merge step
is: confirm each thread's `ledger/⟨THREAD⟩.md` exists and is complete, and
carry its rows forward verbatim under their own row IDs. Deduplication is a
reconciliation-table disposition ("row X merged into row Y"), never a
pre-processing step; severity, likelihood, and fixability are judged in
verification, not at merge time.

  A measured run hand-consolidated 18 threads' rows into a renamed digest
  and lost three findings (including one a thread had explicitly produced);
  its reconciliation table then faithfully protected the digest — which no
  longer contained them.

**A matrix row whose answer lacks a `path:line` citation is an unanswered
row** — send it back to the thread or record that scope as unreviewed.

  A bare "PASS" is how a measured run waved through a diff hunk that
  literally wrapped the old truncation check in `if (!new_flag)`.

### Pass 4 — Verification

Read `references/verification-and-fixes.md`. Mark duplicate ledger rows as
merged into their surviving row — a recorded disposition, never a deletion —
then verify candidates adversarially, with dedicated skeptic subagents where
available: one per serious-looking candidate (batch small related ones),
briefed to REFUTE it under the refutation standard and to return one verdict
row per candidate into `verification.md`, in the schema from the Skeptic
Verdicts section (CONFIRMED / REFUTED / UNPROVEN, each with its mandatory
evidence fields). A skeptic that cannot name the guard line or produce the
safe trace has confirmed the finding, not dismissed it.

For each candidate: build a minimal trace, challenge it, classify it, and
calibrate severity. Survivors become findings; refuted rows keep their
one-line refutation. A candidate that honest tracing can neither confirm nor
refute becomes a question for the CL owner in the review — never a silent
drop. Evaluate any fix you intend to propose against the fix heuristics in
the same file, and verify proposed fixes as carefully as bugs.

### Pass 4.5 — Root-Cause, Layering, And Fix Optimality

Run this after verification and before synthesis. This pass is adversarial to
the review's own current explanation: it asks whether the CL fixes the real
cause at the right layer, rather than just the first observed symptom.

For every P1/P2 candidate, risky P3, proposed fix, performance optimization,
flaky-test fix, async/lifecycle change, state-machine change, cache/throttle,
or new state holder, follow the Root-Cause, Layering, And Fix Optimality
section of `references/verification-and-fixes.md` and record the required
artifacts as `RC-⟨n⟩` rows in `root-cause.md`:

- the causal chain from symptom to invariant owner;
- the upstream/source layer, local layer, downstream/caller layer, and any
  existing shared helper or canonical state owner checked;
- whether the fix covers all callsites sharing the invariant, not only the
  observed caller or failing test;
- for duplicated or cached state, why this location is safer than fixing or
  caching the canonical value;
- for flaky tests, whether the underlying method/protocol is deterministic or
  only the waiter/end condition was made deterministic;
- for async and state machines, the reachable interleaving or state transition
  that confirms or refutes the risk.

If the pass identifies a better owner, a missing caller family, duplicated
state, an unverified state-machine cell, or a new affected surface, add new
ledger rows and return to the relevant Discovery and Verification recipes
before final output. Synthesis may not start until reopened rows are verified,
refuted, or converted into owner questions.

Where subagents are available, spawn one root-cause challenger after
verification. Brief it with the pinned patchset, the verified candidates and
proposed fixes, and the instruction to read `references/verification-and-fixes.md`
and execute only the Root-Cause, Layering, And Fix Optimality section. Its
deliverable is `RC-⟨n⟩` rows in `root-cause.md`: better-owner hypotheses,
callsite gaps, duplicated-state risks, stale-fix risks, and refutations with
`path:line` evidence. If the challenger returns new rows, verify them before
synthesis.

### Pass 5 — Synthesis

Run the final synthesis pass from the verification file: contradiction checks,
root-cause/layering closure, ledger reconciliation, and the not-verified list.
Synthesis produces a **reconciliation table** in `reconciliation.md` as a
required artifact: every thread-emitted row ID mapped to its disposition —
promoted (to finding N), refuted (with the citation), converted to a
question, downgraded, or merged (into row M). Build the table by enumerating
the row IDs present in `ledger/*.md`, `verification.md`, and
`root-cause.md` — the files themselves, never an orchestrator's summary of
them, with no ranges and no "rest dismissed". Output is blocked until every
row has a disposition.

  In a measured run, a P1 candidate recorded by the error-path thread was
  silently dropped between ledger and review; findings reported by several
  threads survived consolidation while single-source rows vanished — the
  table exists to protect the single-source rows.

Where subagents are available, also spawn one challenger over the draft
review, briefed with the Final Synthesis checklist, to hunt contradictions,
unaccounted ledger rows, and miscalibrated severities before sending.

Then fill in the Pre-Output Gate (below) at the bottom of
`reconciliation.md`, refresh Gerrit metadata as described in Fetch And Pin,
and produce output.

## Finding Format

Record and report every finding with:

- **Claim:** one sentence describing concrete behavior, not vibes.
- **Location:** repo-relative `path:line` against the reviewed patchset.
- **Evidence:** the minimal state/call trace or citation that demonstrates it.
- **Severity:** P1/P2/P3 per the calibration below, naming the matched anchor.
- **Origin:** `CL-introduced`, `pre-existing`, or — in follow-up reviews —
  `introduced-in-PS⟨N⟩` for regressions the newer patchset added.
- **Fix status:** validated fix, option needing verification, or no fix
  proposed.
- For P1/P2 findings: the smallest regression test that would have caught it.
- **Rows:** the ledger row and verdict IDs behind the finding (e.g.
  `EPW-2 / V-1`) — an internal trail for the gate; omit it from Gerrit-ready
  text.

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

Anchor table — match each finding to the nearest anchor and argue any delta
explicitly. Anchors beat intuition, especially for test-gap severity:

| Finding pattern | Severity |
| --- | --- |
| Dropped completion callback on an error path (caller waits forever) | P1 |
| Success-shaped return (positive length, `OK`) after failure cleanup in a `DoLoop`-style state machine | P1 |
| Discarded accepted/written-count return (`Push`, short `Write`) — silent byte loss | P1 |
| Callback or timer bound with `Unretained` plus a reachable destroy-before-fire path | P1 |
| Documented base-interface contract clause violated by an override (buffer retention across `ERR_IO_PENDING`, `OK`-vs-byte-count semantics) | P1 |
| Renumbered or reused values of a persisted/serialized enum | P1 |
| Zero-delay self-reposting task that busy-loops `FastForwardBy` under mock time (CI hang) | P1 |
| Restriction feature (throttle, quota, block, isolation) silently degrading to unrestricted behavior on the common path | P1; P2 when the bypass needs an uncommon mode |
| Success-only metric (duration, success count, size/ratio) logged on aborted or cancelled operations | P2 |
| Load-bearing metadata written fire-and-forget (selectable-but-corrupt state) | P2 until proven unobservable |
| Missing test coverage for the default/core mode of new behavior | P2 |
| Sidecar (cache/compression/metrics) failure propagated into the primary operation's result | P2 |
| Untested kill-switch OFF branch whose OFF behavior differs from pre-CL behavior | P2 |
| Untested kill-switch OFF branch that only gates memoization of an invalidation-free value | P3 |
| Ambiguous boolean name (policy vs state, `should_` vs `is_`) | P3 |
| Non-ASCII punctuation in comments or developer-facing prose | P3 |
| Defensive hardening or opportunistic cleanup absent from the CL description | P3 (suggest split or description mention) |

## Subagent Briefs

Subagents start cold: no conversation memory and no loaded skill. A thread is
only as good as its brief, so fill in this template rather than composing
briefs freehand — `references/templates.md` contains a fully filled-in
example of each brief kind; copy its shape. Every path in a brief (worktree,
reference files, ledger file) must be absolute.

1. **Pin:** CL number, patchset, revision SHA, parent SHA, and the absolute
   worktree path (or how to obtain the diff).
2. **Scope:** the exact files and surfaces this thread owns. For broad CLs,
   partition threads by file group as well as by recipe/section. Other
   threads' findings and open ledger rows are context, not work items: do
   not implement, extend, or execution-validate another thread's finding.
   (A measured run's holistic thread picked up a P1's suggested regression
   test and began implementing the fix and the test in the owner's
   checkout.)
3. **Procedure:** the absolute reference file path and the section or recipe
   to read FIRST and then execute — e.g. "read
   `⟨skill-dir⟩/references/deep-dive-recipes.md`; apply the Context Rules,
   then run 'Recipe: Error-Path Walk' on these functions." Point at the file
   rather than paraphrasing the recipe into the brief; paraphrases drop the
   steps that matter.
4. **Deliverable:** the absolute path of the thread's own ledger file
   (`⟨review-dir⟩/ledger/⟨THREAD⟩.md`) to write in the shapes from
   `references/templates.md`, plus a final message consisting only of the
   row IDs produced and the file path. Ledger rows only, no prose narrative.
   First a compliance matrix: one row per checklist question or recipe step
   in the brief's scope, each answered with concrete evidence (`path:line`)
   or N/A-with-reason — an unanswered row is a skipped check, and "no
   findings" without a complete matrix is not an acceptable return. Then the
   candidate rows: ID (`⟨THREAD⟩-⟨n⟩`), claim, repo-relative `path:line`,
   evidence, and either an IF/THEN/UNLESS hypothesis or a trace record
   (`scenario → lines visited → outcome`). Discovery threads leave severity
   blank. If the harness denies subagents file access, the full matrix and
   rows come back in the final message instead — never summarized.
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
   are read-only outside their own ledger file: never edit a repository
   file, even when the harness invites it.

Verification skeptics swap (3)–(5) for: the candidate rows under test, the
pinned patchset, the instruction to read
`⟨skill-dir⟩/references/verification-and-fixes.md` first — the Verifying
Candidate Findings and Skeptic Verdicts sections — and to refute under that
standard, returning one verdict row per candidate into `verification.md`
with the mandatory evidence fields for CONFIRMED / REFUTED / UNPROVEN.

## Output Format

Format the final review as:

1. **CL-Introduced Issues & Suggestions:** Findings introduced by the CL, ordered
   by severity, with file/line references and actionable guidance. Separate blocking
   issues from optional polish. In follow-up reviews, label
   `introduced-in-PS⟨N⟩` findings as such within this section.
2. **Pre-Existing Codebase Issues (For Reference/Follow-up):** Issues observed
   in the surrounding codebase but not introduced by the CL. These must be clearly
   labeled as pre-existing and do not block landing of this CL.
3. **High-Level Summary:** State whether the CL accomplishes its goal, name the
   patchset and revision SHA, and summarize bug alignment.
4. **Prior Review Follow-Up:** If prior issues were supplied, summarize their
   status with evidence.
5. **Positives:** Briefly note important good decisions. A praised safety
   property is a claim like any other — name its guard line. (A measured run
   praised "failures fail open safely" about the exact branch that treated a
   failure as success.)
6. **Questions:** Only questions whose answers affect correctness, API contract,
   or landing readiness. Every UNPROVEN verdict lands here.
7. **Verification Notes:** State tests run or not run, production wiring traced
   or not traced, and any important areas not verified.
   - Name subagents by human-readable thread name (e.g. "the Error-Path Walk
     thread"), never by internal conversation IDs or task UUIDs.
   - Claim test execution only if the exact commands ran successfully against
     the pinned patchset; otherwise state: "No local test execution was
     performed during this review."
   Reproduce the full thread plan from `plan.md` with each thread's outcome:
   rows returned (count), not-triggered (with reason), "terminated — scope
   unreviewed", or "interrupted — partial". Include each thread's
   human-readable name (mapped to its task identifier in `plan.md`), or
   "self-executed" plus the harness limitation that forced it. A
   not-triggered thread is an unverified dimension by definition, and any
   plan deviation — a folded or unspawned entry — is disclosed here as an
   unverified area. On large CLs the full compliance matrices live in the
   review directory with Verification Notes pointing at it — every per-row
   answer must exist somewhere retrievable; a "combined audit summary" that
   discards rows defeats the accounting. Also state the root-cause/layering
   pass outcome: candidate count checked, any better owner or broader
   invariant found, and any discovery/verification rows reopened because of
   it.
8. **Next Steps:** State what is required before `+1 LGTM` and what is optional.

For full CL reviews, append compact **Gerrit-Ready Comments** unless the user
asks for a short summary only, following the Verdict Alignment And Gerrit
Output Rules section of `references/verification-and-fixes.md`:

- **Main body:** brief landing-readiness summary, blockers, optional items,
  prior review status, and verification notes.
- **Replies to existing unresolved threads:** file and thread line, status, and
  the exact response, using the threads recorded in `comments.json`. Do not
  open duplicate new threads for an existing topic.
- **New inline comments:** repo-relative file, exact line or range, verbatim line
  text from the reviewed patchset, and concise comment text. Prefix optional
  polish with `nit:`.

For Gerrit-ready text, cite findings as repo-relative `path:line` against the
reviewed patchset, extract quoted code verbatim, and re-check line numbers
before sending. Avoid leaking local filesystem paths in comments meant for
Gerrit.

## Pre-Output Gate

Copy this checklist verbatim to the bottom of `reconciliation.md` and fill it
in before writing any review text. Every line is answered "yes" with a
citation (a file or row ID in the review directory) or "no" with the
deviation disclosed in Verification Notes. Producing the review while a line
is blank is the failure mode this gate exists to stop.

1. **Pin:** `pin.md` exists; the review text states its patchset number and
   revision SHA; Gerrit metadata was refreshed after synthesis and any newer
   patchset delta inspected.
2. **Roster:** every roster entry appears in `plan.md` as spawned or
   not-triggered-with-reason; no entry is missing, bundled, or renamed.
3. **Collection:** every spawned thread has a collected `ledger/⟨THREAD⟩.md`,
   or is disclosed as terminated/interrupted with its partial rows preserved.
4. **Matrices:** no compliance-matrix row is blank or a citation-free PASS;
   each is evidence-closed, N/A-with-reason, or disclosed as unreviewed.
5. **Per-file floor:** every changed file has at least one ledger row.
6. **Reconciliation:** every row ID across `ledger/*.md`, `verification.md`,
   and `root-cause.md` has exactly one disposition line — no ranges, no
   "rest dismissed".
7. **Verdicts:** every promoted finding cites a CONFIRMED verdict with its
   trace; every refuted row cites its guard or safe trace; every UNPROVEN
   row appears in Questions.
8. **Root cause:** the layering pass ran for every triggering candidate and
   fix; reopened rows were re-verified, refuted, or converted to questions.
9. **Severity and origin:** every finding names its anchor-table match (or
   argues the delta) and carries an origin label.
10. **Verdict consistency:** if any P1/P2 finding stands, the recommendation
    reads "not LGTM until ⟨finding⟩"; no approval is combined with blocking
    conditions.
11. **Gerrit text:** no local paths or `file://` URLs; no placeholder
    inlines; quoted lines re-checked verbatim against the pinned patchset;
    replies target existing threads from `comments.json` instead of
    duplicating them.
12. **Honesty:** the test-execution statement matches what was actually run;
    Verification Notes reproduce the plan with outcomes and human-readable
    thread names.

## Tone

Follow Chromium review norms: assume competence and goodwill, lead with concrete
findings, explain why each requested change matters, ask "why" when intent is
unclear and affects correctness, label optional polish as optional, and make
landing blockers explicit.
