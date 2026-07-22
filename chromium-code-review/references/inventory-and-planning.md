# Inventory And Planning

This file is executed by the early-phase worker agents: the
Context-and-Inventory agent (Pass 1), the Prior-Feedback agent (Pass 2), and
the Planner agent (Pass 3 plan construction). The orchestrator does not load
it. Artifact shapes live in `references/templates.md`; rules are stated in
bold, and indented text under a rule is the measured failure that motivates
it.

## Contents

- Gather Context (Pass 1)
- Pass 1 — Changed-Surface Inventory And Risk-Area Map
- Pass 2 — Prior-Feedback Reconciliation
- Pass 3 — The Thread Plan
- The Roster
- Plan-Construction Rules
- Writing Discovery Briefs

## Gather Context (Pass 1)

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

Record the results in `context.md`: bug summary and alignment notes,
description-vs-implementation discrepancies, and the scope-relevance notes
that the holistic thread and the draft writer will consume.

## Pass 1 — Changed-Surface Inventory And Risk-Area Map

Build two artifacts from the diff before anyone forms opinions, written to
`inventory.md` (or `inventory/<shard>.md` when the orchestrator sharded the
CL by file group):

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
  sections the planner triggers.

## Pass 2 — Prior-Feedback Reconciliation

Executed by the Prior-Feedback agent on follow-up reviews only. Inputs: the
pin, `prior-feedback-input.md` (the prior review text the orchestrator
saved), and `comments.json`. Deliverable: `ledger/PR.md` in the ledger-row
shape from `references/templates.md`.

- Inspect both latest-vs-base and latest-vs-prior-reviewed-patchset. Prior
  patchset SHAs come from `detail.json` (`ALL_REVISIONS`); materialize the
  prior patchset the same way as the current one when a file-level diff is
  needed — in a second detached worktree, never by touching the pinned one.
- Resolve every prior finding as a `PR-<n>` row: fixed, partially fixed,
  still open, obsolete, or superseded, with evidence from the current
  patchset.
- Reconcile against the unresolved Gerrit comment threads in
  `comments.json`, not only against the prior review text.
- Reconcile minor nits, optional cleanup, requested macros, and unresolved
  discussions too. Collapse or omit cosmetic items from the final review when
  appropriate, but do not assume they were resolved just because larger issues
  were fixed.
- Label every new finding's origin explicitly: `CL-introduced` (present since
  the CL's earlier patchsets), `introduced-in-PS<N>` (a regression the newer
  patchset added — often by the fix itself), or `pre-existing` (in the
  surrounding codebase). The delta review exists to catch the middle class;
  do not let it collapse into the first.

## Pass 3 — The Thread Plan

Executed by the Planner agent. Inputs: `pin.md`, `directives.md`,
`context.md`, all inventory files, and — read first — the Context Rules and
each recipe's trigger line in `references/deep-dive-recipes.md`, plus a skim
of the `references/discovery-checklists.md` sections matched by the risk
map. The plan is only as good as the planner's grasp of what each thread is
for.

From the risk map and the changed-surface inventory, list:

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
changes, and reentrancy first; renames and plumbing last. Assign each
spawned thread to a priority batch of three or four accordingly. Ensure some
thread owns the smallest and least obvious files — the per-file ledger floor
depends on it.

## The Roster

The plan enumerates the **full roster**, copied verbatim with one line each —
never derived from memory:

- Recipes: Desk-Check Simulation + Arithmetic Drills, Data Lineage,
  Callback And Task Lifetime, Container And View Invalidation,
  Error-Path Walk, State × Method Matrix, Mode × Host-Capability Matrix,
  Teardown Order.
- Sections: Mechanical Leads, Per-Surface Invariants, Async And Lifecycle,
  State/Persistence/Cache, Integration And Feature Control, Security And
  Trust Boundaries, Contracts And API Shape, Tests As Specifications,
  Changed-Lines Polish.
- Always: the holistic thread.

## Plan-Construction Rules

Write the complete plan into `plan.md` before any thread is spawned — one
line per thread with name, scope, and status (`spawn` /
`not triggered: <reason>`), in the roster shape from
`references/templates.md`. Hard rules, each learned from a measured failure:

**Every roster line appears in the plan with a status.** An omitted line is
invisible; a wrong not-triggered reason is catchable.

  Measured runs keep paying for omissions: one silently dropped the Teardown
  recipe and with it the only thread that checks end-of-operation resource
  release; another (large CL) omitted the Mode × Host matrix and both
  arithmetic techniques — and six of its nine serious misses were cells and
  drills those threads own.

**"Not triggered: <reason>" is an honest, expected status; folding is not.**
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

**Sharding is allowed; folding is not.** For broad CLs, split a roster
entry into shards — each shard is its own plan row, brief, and ledger
file, with the shard number appended to the ID prefix (`EPW1`, `EPW2`;
rows `EPW1-<n>`). Splitting one entry into narrower scopes preserves the
roster; merging several entries into one thread destroys it.

**Budget shards by trace units, not just file counts.** File counts bound
reading; they do not bound tracing, and the trace-heavy recipes explode
combinatorially inside even one dense file. Estimate each thread's trace
load from the inventory and shard along the recipe's natural unit when it
exceeds roughly one context's worth of honest tracing:

- File-shaped threads (checklist sections, polish, mechanical leads):
  ~15 files or ~1500 changed lines per shard.
- Path-walking recipes (Error-Path Walk, Desk-Check + Arithmetic Drills,
  Data Lineage, Callback And Task Lifetime, Teardown Order): shard by
  entry point — roughly 8–10 functions/lineages/callbacks per shard, fewer
  when the paths are deep (a DoLoop state machine counts as several).
- Matrix recipes (State × Method, Mode × Host-Capability): shard by matrix
  block — roughly 40 cells per shard, split along whole states or modes so
  every shard still owns complete rows. A thread that must pencil-whip
  cells to finish is over-budget by definition; the measured bare-PASS
  failures are what an over-budgeted matrix thread produces.

Name each shard's exact entry points, states, or cells in its plan row and
brief — "the rest" is not a scope, and an unnamed unit is how a trace gets
silently skipped.

**A matrix row whose answer lacks a `path:line` citation is an unanswered
row.** The collection audit sends such rows back to their thread or records
that scope as unreviewed — write the briefs so threads know a bare PASS is
not an answer.

  A bare "PASS" is how a measured run waved through a diff hunk that
  literally wrapped the old truncation check in `if (!new_flag)`.

## Writing Discovery Briefs

Subagents start cold: no conversation memory and no loaded skill. A thread
is only as good as its brief, so fill in the template in
`references/templates.md` (Subagent Brief — Discovery Thread) rather than
composing briefs freehand. Write each brief to
`<review-dir>/briefs/<THREAD>.md`. Every path in a brief (worktree,
reference files, ledger file) must be absolute.

1. **Pin:** CL number, patchset, revision SHA, parent SHA, and the absolute
   worktree path (or how to obtain the diff).
2. **Scope:** the exact files and surfaces this thread owns. Other threads'
   findings and open ledger rows are context, not work items: do not
   implement, extend, or execution-validate another thread's finding.
   (A measured run's holistic thread picked up a P1's suggested regression
   test and began implementing the fix and the test in the owner's
   checkout.)
3. **Procedure:** the absolute reference file path and the section or recipe
   to read FIRST and then execute — e.g. "read
   `<skill-dir>/references/deep-dive-recipes.md`; apply the Context Rules,
   then run 'Recipe: Error-Path Walk' on these functions." Point at the file
   rather than paraphrasing the recipe into the brief; paraphrases drop the
   steps that matter.
4. **Deliverable:** the absolute path of the thread's own ledger file
   (`<review-dir>/ledger/<THREAD>.md`) to write in the shapes from
   `references/templates.md`, plus a final message consisting only of the
   row IDs produced and the file path. Ledger rows only, no prose narrative.
   First a compliance matrix: one row per checklist question or recipe step
   in the brief's scope, each answered with concrete evidence (`path:line`)
   or N/A-with-reason — an unanswered row is a skipped check, and "no
   findings" without a complete matrix is not an acceptable return. Then the
   candidate rows: ID (`<THREAD>-<n>`), claim, repo-relative `path:line`,
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
   file, even when the harness invites it. Briefs also carry the
   partial-return rule: a thread whose scope outgrows its context finishes
   what it can at full rigor and returns "partial — remaining: ⟨scope⟩"
   rather than thinning out the tracing — the orchestrator spawns a
   continuation.

Echo the review mode and any user directives from `directives.md` into
every brief so targeted-review scope limits and format requests survive the
handoff.
