---
name: chromium-code-review
description: Reviews a Chromium CL when requested (e.g. "review CL 12345") and re-reviews updated patchsets against prior feedback. Checks bug alignment, patchset freshness, correctness, tests, style, performance, lifecycle, and Chromium conventions.
---

# Chromium CL Reviewer Skill

When the user asks you to review a Chromium CL, perform a rigorous review of the
latest patchset and produce actionable feedback suitable for Chromium code
review. Optimize for a clear landing recommendation with the smallest necessary
set of blocking comments.

The review runs in two mindsets, kept deliberately separate:

- **Discovery** casts a wide net. Enumerate candidate issues cheaply; a wrong
  hypothesis costs nothing because verification filters it later. Most missed
  bugs are missed because the suspicion was never written down, not because
  verification failed.
- **Verification** is skeptical. Every candidate is traced through real code
  before it may appear in the review, and severity is calibrated there.

Filtering during discovery is the main way reviews miss real issues; skipping
verification is the main way they report false ones.

Throughout this skill, rules are stated in bold; indented text under a rule is
the measured failure that motivates it. The rules are normative even if you
skip the rationale.

## You Are The Orchestrator

The agent reading this file coordinates the review; it does not perform it.
Every unit of real analysis — context gathering, inventory, planning,
discovery, verification, root-cause analysis, reconciliation, drafting,
challenge — runs in a fresh-context subagent whose deliverable is files in
the review directory. Handoffs between phases are those files, never
conversation context.

**Invoking this skill IS the user's explicit request for multi-agent
orchestration.** Where a harness gates heavy orchestration on user opt-in,
this invocation satisfies it. Do not ask the user for permission to spawn
subagents, and do not downgrade to serial self-execution while any
subagent-spawning tool exists in the harness — the serial path in Degraded
Modes is only for harnesses with no such tool at all.

  This architecture is load-bearing, not stylistic: runs that held the whole
  review in one context blew through 1M-token windows mid-review and lost
  all progress. Files survive context loss; a compacted orchestrator resumes
  from the review directory.

**Hard context-budget rules for the orchestrator:**

1. **Never read the diff, the worktree, `detail.json`, `comments.json`, any
   `ledger/`, `verification/`, or `briefs/` file, or any reference file
   other than this file and `references/phase-briefs.md`.** Everything the
   orchestrator needs arrives as `pin.md`, one-line subagent status
   messages, and the compact per-phase returns defined below.
2. **Check artifacts by existence and size (`ls`, `wc -l`), never by reading
   them.**
3. **Subagent final messages are status lines** — row IDs/counts plus file
   paths, nothing else. If a worker returns bulk content in its final
   message (e.g. the harness denied it file access), write that content
   verbatim to the artifact path the worker should have written, and do not
   re-read it or quote it in later prompts.
4. **Append a one-line outcome to `progress.md` after every phase and every
   collected thread.** After compaction or a restart, resume by reading
   `progress.md`, `pin.md`, and `plan.md` — never by redoing completed
   phases. `progress.md` is the orchestrator's memory; conversation context
   is not.
5. The only large files the orchestrator ever reads are `draft-review.md`
   and `gerrit-comments.md`, once, at delivery (Phase 9).
6. **Honor partial returns.** Every brief tells workers that when their
   remaining work will not fit in context, they finish what they can at
   full rigor and return "partial — remaining: ⟨scope⟩". On a partial
   return, record it in `progress.md` and spawn a continuation with the
   same brief plus one line: "Continuation: your deliverable already
   contains prior work — do not redo it; process only: ⟨remaining scope⟩."
   Loop until the phase reports complete. A partial return is a normal
   handoff, never grounds to mark the phase done or to fold the remaining
   scope into another agent.

## Reference Files And Scripts

Paths below are relative to this skill's directory. **Every path placed in a
subagent brief must be expanded to an absolute path** — subagents start in
the repository checkout, where skill-relative paths do not resolve.

Orchestrator-facing (the only skill files the orchestrator loads):

- `references/phase-briefs.md`: a filled-in brief for every phase subagent.
  Copy the brief, substitute the pin values and absolute paths, spawn.
- `scripts/fetch-cl.sh`: fetches and pins a patchset — Gerrit REST metadata
  (all revisions plus published comments), XSSI stripping, ref fetch, a
  detached worktree at the explicit SHA, and `rev-parse` verification — and
  writes `pin.md`, `detail.json`, and `comments.json` into the review
  directory. Use it instead of hand-running those steps.

Worker-facing (loaded by subagents because their briefs point at them; the
orchestrator never loads these):

- `references/templates.md`: the normative shapes of every artifact this
  skill produces — review directory layout, row-ID scheme, thread-plan
  roster, subagent briefs, compliance matrices, skeptic verdicts,
  reconciliation table, final findings. Workers copy the shapes and fill
  them in; nobody invents formats.
- `references/inventory-and-planning.md`: context gathering, the Pass 1
  changed-surface inventory and risk-area map, Pass 2 prior-feedback
  reconciliation, the full thread roster with the plan-construction rules,
  and how to write discovery briefs.
- `references/discovery-checklists.md`: per-risk-area questions, required
  traces, and mechanical lead generation, executed by discovery threads.
- `references/deep-dive-recipes.md`: step-by-step trace procedures with
  named work products, executed by discovery threads.
- `references/verification-and-fixes.md`: verification batching, the
  skeptic verdict schema, fix evaluation, the root-cause/layering pass, the
  final-synthesis contradiction checklist, and the Gerrit output rules.
- `references/synthesis-and-output.md`: finding format, severity
  calibration and the anchor table, the review output format, the
  pre-output gate, and tone.
- `scripts/mechanical-leads.sh`: run by the Mechanical Leads thread; emits
  ledger-ready candidate rows.

## Review Modes

- **Full CL review:** inspect the latest patchset against its parent, gather
  bug and design context, run the full pipeline below, and produce
  Gerrit-ready comments.
- **Follow-up review:** run the full pipeline including Phase 2
  (prior-feedback reconciliation). Prior feedback is context, not the
  boundary of the review: after resolving prior findings, discovery still
  covers the whole changed surface.
- **Targeted review:** focus on the requested subsystem, file, or risk area —
  the planner triggers only the matching roster entries — but any serious
  blocker discovered nearby is still reported.
- **Short summary:** honor the shorter format, but still pin the patchset and
  disclose important unverified areas.

Record the mode and any user directives (scope limits, format requests,
prior-review text location) in `directives.md` at the start; every phase
brief echoes it so workers see the user's constraints without the
orchestrator restating them.

## The Review Directory

Every review gets a working directory — under the harness scratchpad when one
exists, otherwise a temp directory outside the repository — with this layout
(shapes in `references/templates.md`):

```
<scratchpad>/cl-<CL>-ps<PS>/
  pin.md                  # patchset pin block (fetch-cl.sh writes this)
  detail.json             # Gerrit change detail (ALL_REVISIONS)
  comments.json           # published comments; unresolved threads live here
  worktree/               # detached read-only checkout at the pinned SHA
  directives.md           # review mode + user directives (orchestrator writes)
  progress.md             # orchestrator phase log; the resume point
  context.md              # Phase 1: bug/design context, scope-relevance notes
  inventory.md            # Phase 1: changed-surface inventory + risk-area map
                          # (inventory/<shard>.md when sharded)
  prior-feedback-input.md # Phase 2 input: prior review text (follow-ups only)
  plan.md                 # Phase 3: thread-plan roster with statuses
  briefs/<THREAD>.md      # Phase 3: one filled brief per spawned thread
  briefs/V<batch>.md      # Phase 5: skeptic briefs
  mechanical-leads.md     # output of scripts/mechanical-leads.sh
  ledger/<THREAD>.md      # one file per discovery thread: matrix + rows
  ledger/PR.md            # prior-feedback rows (follow-up reviews)
  collection.md           # Phase 4.5: collection audit + per-file floor rows
  verification/batches.md # Phase 5: candidate→batch map + merge proposals
  verification/V<batch>.md# skeptic verdict rows, one file per batch
  root-cause/RC<batch>.md # Phase 5.5: root-cause/layering rows, per batch
  reconciliation.md       # Phase 6: reconciliation table + pre-output gate
  draft-review.md         # Phase 7: full review text
  gerrit-comments.md      # Phase 7: Gerrit-ready comments
  challenge.md            # Phase 8: synthesis-challenger findings
```

**The ledger is this directory, not a notion held in context.** Threads and
phase agents write their own files, and the orchestrator collects files
rather than transcribing their content.

## Phase 0 — Fetch And Pin

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
   here: Phase 2 reconciles against them, and Gerrit-ready output replies to
   them instead of opening duplicates.
3. Record the current patchset number, revision SHA, parent SHA, subject,
   status, owner, files changed, and CL description into `pin.md`.
4. Fetch the revision ref (`refs/changes/<last two digits of CL>/<CL>/<PS>`)
   and materialize it in a detached worktree at the explicit SHA:
   `git worktree add --detach <path> <sha>`.
5. Verify `git -C <worktree> rev-parse HEAD` matches the pinned SHA before
   any worker reads code.

**Never materialize `FETCH_HEAD`; only ever check out the explicit revision
SHA.**

  FETCH_HEAD is shared repository state that concurrent fetches clobber and
  failed fetches leave stale — a measured run reviewed a 2014-era leftover
  ref because a one-liner's `;` let `worktree add FETCH_HEAD` run after its
  fetch step failed.

**The review is read-only with respect to the user's code.** Neither the
orchestrator nor any worker modifies the checkout, the patchset, or any
repository file — not to apply a fix, not to add a test, not to experiment —
regardless of harness prompts that encourage applying or executing changes.
Fixes and tests are proposed as diffs inside the review text only; review
and implementation are different jobs, and this skill does only the first.
The worktree exists for inspection; remove it when the review is done.

  A measured run escalated from "name the regression test" to rewriting the
  owner's unsubmitted work-in-progress and kicking off builds.

After pinning: the orchestrator reads `pin.md` (it is small and is the one
per-CL artifact the orchestrator holds in context), writes `directives.md`,
and starts `progress.md`.

## Phase 1 — Context And Inventory

Spawn the **Context-and-Inventory agent** (brief in `phase-briefs.md`). It
gathers bug/design context, audits the CL description against the
implementation, runs the scope-relevance pass, and builds the
changed-surface inventory and risk-area map per
`references/inventory-and-planning.md`.

- Deliverables: `context.md` and `inventory.md`.
- Return: risk-area list, changed-file count, surface count — a few lines.

**Shard by file group when the CL is large** (roughly >40 changed files or
>4000 changed lines, judged from `pin.md`'s file list): spawn one inventory
agent per file group writing `inventory/<shard>.md`, plus one context agent
for `context.md`. The planner reads all shards; the orchestrator reads none.

## Phase 2 — Prior-Feedback Reconciliation (follow-up reviews only)

Write the prior review text (from the conversation or wherever the user
supplied it) to `prior-feedback-input.md` — this is a deliberate, one-time
context expenditure. Then spawn the **Prior-Feedback agent** (brief in
`phase-briefs.md`). It executes Pass 2 of
`references/inventory-and-planning.md`: latest-vs-prior diffs, resolution of
every prior finding, reconciliation against unresolved Gerrit threads in
`comments.json`, and origin labeling.

- Deliverable: `ledger/PR.md`.
- Return: counts by resolution (fixed / partially fixed / still open /
  obsolete / superseded) — one line.

## Phase 3 — Thread Planning

Spawn the **Planner agent** (brief in `phase-briefs.md`). It reads the
inventory, skims the recipe trigger lines and checklist sections, and builds
the full thread plan under the roster rules in
`references/inventory-and-planning.md` — every roster entry present with a
status, no folding, sharding where scopes are large. It then writes one
self-contained discovery brief per spawned thread.

- Deliverables: `plan.md` and `briefs/<THREAD>.md` for every `spawn` row.
- Return: the spawn list — thread name, brief path, priority batch — plus
  the not-triggered count. This list is the orchestrator's work queue;
  keep it, do not re-derive it.

## Phase 4 — Discovery Execution

The orchestrator now executes the plan. Runs of this skill show the same
pattern across models: a single agent sustains real depth on only one or
two threads per pass — whichever grab its attention — and everything else
gets a shallow read. So discovery is never one agent.

**Spawn one subagent per triggered roster entry, with the spawn prompt
"Read and execute the brief at ⟨absolute path to briefs/THREAD.md⟩. It
defines your pin, scope, procedure, deliverable, and rules." Never run
discovery as a single agent, and never inline a brief's body into the spawn
prompt.** Run threads in parallel where the harness allows, and record each
thread's subagent/task identifier in `plan.md`.

  Self-executing when subagents exist is a measured failure mode: one agent
  running eleven sweeps found three P1s in its first, fresh sweep, then
  starved the rest — shallow-wrong error-path answers, pencil-whipped
  matrices, and zero polish-tier findings.

**Run priority-ordered batches of three or four threads** (the planner's
batch order: where P1s live first — teardown and error paths, boundary
arithmetic, cross-sequence handoffs, persisted formats, reentrancy; renames
and plumbing last). Overlap between threads is fine — redundant coverage is
how disjoint blind spots get closed.

**Discovery ends only when every planned thread has delivered its ledger
file; outstanding threads are blocking dependencies, not background noise.**
Expect the section threads to be slowest — they read the most — and to
carry the most findings. If a thread dies to a transient harness error
(capacity limits, rate limits, timeouts), respawn it with the same brief;
only when retries are exhausted record it in `plan.md` and `progress.md` as
"terminated — scope unreviewed". Never mark an uncollected thread
Completed. If you interrupt a thread deliberately, collect its partial
ledger file before killing it and record it as "interrupted — partial".

  In a measured run, an orchestrator that killed its two slowest threads
  before they reported lost four of its five remaining P1/P2 findings inside
  them. Another marked an interrupted thread Completed and lost the P2
  finding sitting in its workspace. A capacity-killed roster was fully
  recovered by a simple backoff-and-respawn loop — transient failures are
  retryable.

**Collect ledger files; never transcribe or compress them.** Collection is:
confirm the thread's `ledger/<THREAD>.md` exists and is non-trivial
(`ls`, `wc -l`), record the outcome (row count from the thread's status
message) in `plan.md` and `progress.md`, and move on. Rows are carried
forward by the files themselves under their own IDs. Deduplication is a
reconciliation-time disposition ("row X merged into row Y"), never an
orchestrator pre-processing step; severity is judged in verification, not
at collection.

  A measured run hand-consolidated 18 threads' rows into a renamed digest
  and lost three findings (including one a thread had explicitly produced);
  its reconciliation table then faithfully protected the digest — which no
  longer contained them.

## Phase 4.5 — Collection Audit

Spawn the **Collection-Audit agent** (brief in `phase-briefs.md`). It reads
every ledger file and checks: each spawned thread's file is present and its
compliance matrix complete; no matrix row is a citation-free PASS; every
changed file has at least one ledger row, adding explicit `ORC` clean rows
to `collection.md` where none exists; and anomalies recorded in matrix
answers were emitted as candidate rows.

- Deliverable: `collection.md` (audit result, ORC per-file floor rows, gap
  list).
- Return: "complete" or the gap list — thread names to respawn or send-back
  questions. Respawn gapped threads with their same brief, then re-run the
  audit. Verification does not start until the audit returns complete or
  every remaining gap is recorded as an unreviewed area.

## Phase 5 — Verification

Spawn the **Verification-Planner agent** (brief in `phase-briefs.md`). It
reads all ledger files plus `collection.md`, proposes duplicate merges (as
dispositions for reconciliation, never deletions), groups candidates into
skeptic batches — serious candidates individually or in small related
groups, per `references/verification-and-fixes.md` — and writes one skeptic
brief per batch with the candidate rows inline, assigning verdict IDs
`V<batch>-<n>`.

- Deliverables: `verification/batches.md` and `briefs/V<batch>.md`.
- Return: the batch list (batch id, brief path, candidate count).

Then spawn one **skeptic** per batch — same spawn pattern and batching
(three or four at a time), same retry rules as discovery. Each writes
`verification/V<batch>.md`. Skeptics are briefed to REFUTE under the
refutation standard; a skeptic that cannot name the guard line or produce
the safe trace has confirmed the finding, not dismissed it. Candidates that
honest tracing can neither confirm nor refute become owner questions —
never silent drops.

## Phase 5.5 — Root-Cause, Layering, And Fix Optimality

Root-cause work is trace-heavy — each candidate needs upstream, local, and
downstream layer walks — so it is batched like verification, never one
agent over the whole record. The skeptic status lines already gave the
orchestrator every verdict by row ID: group the CONFIRMED candidates (plus
proposed fixes and the other triggers named in
`references/verification-and-fixes.md`, which the skeptic severity
proposals identify) into batches of **three to five candidates**, related
candidates together, without reading any verdict file.

Spawn one **Root-Cause Challenger** per batch (brief in `phase-briefs.md`,
with the batch's row IDs listed). Each executes the Root-Cause, Layering,
And Fix Optimality section of `references/verification-and-fixes.md` over
its batch only, writing `RC<batch>-<n>` rows to
`root-cause/RC<batch>.md`. If a challenger identifies a better owner, a
missing caller family, duplicated state, or a new affected surface, it
adds new ledger rows and writes `briefs/VRC<batch>.md` for their
verification.

- Return per challenger: candidates checked, RC rows written, rows
  reopened (with the VRC brief path when non-empty).
- If rows were reopened: spawn the VRC skeptic(s) (and, when the
  challenger says the new rows need discovery-recipe work first, the named
  discovery brief) and loop until no open rows remain. Synthesis may not
  start until reopened rows are verified, refuted, or converted into owner
  questions.

## Phase 6 — Reconciliation

Spawn the **Reconciliation-Builder agent** (brief in `phase-briefs.md`). It
enumerates every row ID present in `ledger/*.md`, `collection.md`,
`verification/*.md`, and `root-cause/*.md` — the files themselves, never a
summary — and writes the reconciliation table: one disposition line per row
(promoted / refuted / question / downgraded / merged / clean), no ranges,
no "rest dismissed". It also writes the pre-output gate skeleton from
`references/synthesis-and-output.md` at the bottom of `reconciliation.md`,
filling the lines it can prove.

- Deliverable: `reconciliation.md`.
- Return: total rows, unaccounted rows (must be zero), promoted-finding
  count, open gate lines. Output is blocked while any row lacks a
  disposition — fix the cause (usually an uncollected file) and respawn.

## Phase 7 — Draft Review

Spawn the **Draft-Writer agent** (brief in `phase-briefs.md`). It reads
`reconciliation.md`, the confirmed verdicts, `root-cause/*.md`, `context.md`,
`pin.md`, `comments.json` (for replies to existing threads), and the
worktree (for verbatim quoted lines), and writes the full review per
`references/synthesis-and-output.md`: `draft-review.md` plus
`gerrit-comments.md`, and completes the pre-output gate in
`reconciliation.md`.

- Return: finding counts by severity, the verdict line, and gate status
  (every line answered, or the "no" lines listed).

## Phase 8 — Synthesis Challenge

Spawn the **Synthesis Challenger** (brief in `phase-briefs.md`). It reads
the draft against the review directory and hunts contradictions,
unaccounted ledger rows, miscalibrated severities, and gate lines answered
untruthfully, using the Final Synthesis checklist in
`references/verification-and-fixes.md`. Deliverable: `challenge.md`.

- Return: issue count. If non-zero, respawn the Draft Writer with
  `challenge.md` as an additional input for one revision cycle; disputes
  still standing after that are disclosed in Verification Notes rather than
  silently resolved.

## Phase 9 — Delivery

The orchestrator finishes the review:

1. **Refresh Gerrit metadata without reading bulk JSON:** fetch the detail
   URL to a temp file, strip the XSSI prefix, and extract only the current
   patchset number and updated timestamp (e.g. with `jq`). If a newer
   patchset appeared during review, spawn the **Patchset-Delta Inspector**
   (brief in `phase-briefs.md`) and route material deltas back through
   Phases 5–8 before finalizing. The review states the exact patchset
   number and revision SHA it covers.
2. Read `draft-review.md` and `gerrit-comments.md` — the one sanctioned
   large read — and deliver them to the user. The orchestrator's final
   check is editorial judgment only: formatting, and consistency between
   verdict and findings. If it spots a content problem, it routes the issue
   back through Phase 8 rather than editing findings itself — the draft is
   the synthesis of the record; the orchestrator has not read the record.
3. Remove the worktree (`git worktree remove`).

## Degraded Modes

- **The harness cannot spawn subagents:** execute the plan yourself as
  serial sweeps in plan order, completing each thread's rows before
  starting the next, and keep every artifact-and-gate obligation.
  Verification Notes must say so and name the limitation. Watch your own
  context: write rows to files as you go, and prefer finishing the ledger
  over holding analysis in memory.
- **Subagents cannot write files:** their briefs' fallback applies — the
  full matrix and rows come back in the final message, never summarized.
  The orchestrator writes each returned payload verbatim to the artifact
  path the worker would have written, without re-reading it afterward, and
  disclosure in Verification Notes names the degraded handoff.

## Severity, Output, And Tone

Severity calibration, the anchor table, the finding format, the review
output format, the pre-output gate, and tone norms live in
`references/synthesis-and-output.md`. They bind the workers that produce
verdicts and review text; the orchestrator does not restate or override
them.
