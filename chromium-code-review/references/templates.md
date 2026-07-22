# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## Contents

- Row IDs
- The Review Directory
- pin.md
- directives.md And progress.md
- inventory.md — Changed-Surface Inventory And Risk-Area Map
- plan.md — Thread-Plan Roster
- Subagent Brief — Discovery Thread
- ledger/⟨THREAD⟩.md — Compliance Matrix And Candidate Rows
- Per-File Floor Rows
- Subagent Brief — Verification Skeptic
- verification/ — Batches And Skeptic Verdict Rows
- root-cause/ — Root-Cause Rows
- reconciliation.md — Reconciliation Table And Pre-Output Gate
- Final-Review Finding

## Row IDs

Rows are identified as `⟨THREAD⟩-⟨n⟩`, assigned by the thread that creates
the row, numbered from 1 in creation order. A row keeps its ID through
verification, reconciliation, and the final review; the orchestrator never
renumbers or re-keys another thread's rows.

| Roster entry / source | ID prefix |
| --- | --- |
| Desk-Check Simulation + Arithmetic Drills | DCS |
| Data Lineage | DL |
| Callback And Task Lifetime | CTL |
| Container And View Invalidation | CVI |
| Error-Path Walk | EPW |
| State × Method Matrix | SMM |
| Mode × Host-Capability Matrix | MHM |
| Teardown Order | TDO |
| Mechanical Leads | ML |
| Per-Surface Invariants | PSI |
| Async And Lifecycle | AL |
| State/Persistence/Cache | SPC |
| Integration And Feature Control | IFC |
| Security And Trust Boundaries | STB |
| Contracts And API Shape | CAS |
| Tests As Specifications | TAS |
| Changed-Lines Polish | CLP |
| Holistic-and-polish thread | HOL |
| Prior-review reconciliation (Pass 2) | PR |
| Collection-audit rows (per-file floor) | ORC |
| Verification skeptic verdicts | V⟨batch⟩ (e.g. V1, V2, VRC1) |
| Root-cause challenger rows | RC⟨batch⟩ (e.g. RC1, RC2) |

A sharded roster entry appends its shard number to the prefix: shard 2 of
Error-Path Walk is thread `EPW2`, rows `EPW2-⟨n⟩`, ledger file
`ledger/EPW2.md`, and its own row in `plan.md`. Skeptic verdicts are keyed
by batch: batch 1 writes `verification/V1.md` with IDs `V1-⟨n⟩`, so
concurrent skeptics never collide on a file or an ID.

## The Review Directory

```
<scratchpad>/cl-9999999-ps3/
  pin.md                  # patchset pin block (scripts/fetch-cl.sh writes this)
  detail.json             # Gerrit change detail (ALL_REVISIONS)
  comments.json           # published comments; unresolved threads live here
  worktree/               # detached read-only checkout at the pinned SHA
  directives.md           # review mode + user directives (orchestrator)
  progress.md             # orchestrator phase log; the resume point
  context.md              # Phase 1: bug/design context, scope-relevance notes
  inventory.md            # Phase 1: inventory + risk map (inventory/<shard>.md when sharded)
  prior-feedback-input.md # Phase 2 input (follow-up reviews only)
  plan.md                 # Phase 3: thread-plan roster with statuses
  briefs/EPW.md           # Phase 3: one brief per spawned thread
  briefs/V1.md            # Phase 5: one brief per skeptic batch
  mechanical-leads.md     # output of scripts/mechanical-leads.sh
  ledger/EPW.md           # one file per spawned thread
  ledger/AL.md
  ledger/...
  collection.md           # Phase 4.5: collection audit + ORC per-file floor rows
  verification/batches.md # Phase 5: candidate→batch map + merge proposals
  verification/V1.md      # skeptic verdict rows, one file per batch
  root-cause/RC1.md       # root-cause/layering rows, one file per batch
  reconciliation.md       # reconciliation table + filled pre-output gate
  draft-review.md         # Phase 7: full review text
  gerrit-comments.md      # Phase 7: Gerrit-ready comments
  challenge.md            # Phase 8: synthesis-challenger findings
```

Thread ledger files are append-only records of discovery: later passes never
rewrite them. A row's life-cycle state advances in `verification/V⟨batch⟩.md`
(verdicts) and `reconciliation.md` (dispositions), not by editing the row.
A row, once written, is never deleted or edited, and every row is carried to
synthesis: promoted, downgraded, merged, or dismissed with a one-line recorded
reason. Information silently lost at consolidation time is a common source of
incomplete reviews.

## pin.md

```markdown
# CL 9999999 — patchset 3 pin

- Subject: [net] Add DelayBuffer for socket-level write pacing
- Status: NEW
- Owner: Jane Doe <jdoe@chromium.org>
- Updated: 2026-07-01 18:22:04
- Current patchset: 3
- Pinned patchset: 3
- Revision SHA: 4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9
- Parent SHA: 8b1d77e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b177
- Ref: refs/changes/99/9999999/3
- Worktree: /tmp/scratch/cl-9999999-ps3/worktree (rev-parse verified)
- Messages: 12; comment threads: 9 (2 unresolved)
- Files changed (3):
  - net/streams/delay_buffer.cc
  - net/streams/delay_buffer.h
  - net/streams/delay_buffer_unittest.cc
```

## directives.md And progress.md

Both are orchestrator-written and deliberately tiny. `directives.md` (echoed
into every brief):

```markdown
# Directives — CL 9999999 PS3

- Mode: follow-up review (prior review text saved to prior-feedback-input.md)
- User directives: focus requested on net/streams; short-summary format NOT
  requested; no other constraints.
```

`progress.md` is an append-only phase log — the orchestrator's resume point
after context loss. One line per event:

```markdown
# Progress — CL 9999999 PS3

- Phase 0 done: pinned PS3 4f2a09c1; worktree verified.
- Phase 1 done: context.md + inventory.md; risk areas: async, buffering, tests.
- Phase 3 done: plan.md; 15 spawn / 3 not-triggered; batches 1-4.
- Batch 1 spawned: DCS(task-a1) DL(task-a2) CTL(task-a3) CVI(task-a4).
- DCS collected: 9 rows.
...
```

## inventory.md — Changed-Surface Inventory And Risk-Area Map

```markdown
# Inventory — CL 9999999 PS3

## Changed surfaces

| surface | contract source | callers | old → new behavior | state / lifetime | tests | reachability | scope label |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DelayBuffer::Push (delay_buffer.h:41) | header comment | DelayStream::DoWrite | new API | owns buffer_, pending_ | delay_buffer_unittest.cc | production | core |
| DelayBuffer::Flush (delay_buffer.h:48) | header comment | DelayStream teardown | new API | drains buffer_ | none found | production | core |

## Risk-area map

| file | risk areas |
| --- | --- |
| net/streams/delay_buffer.cc | async/lifecycle, buffering/backpressure, memory ownership |
| net/streams/delay_buffer_unittest.cc | tests |
```

## plan.md — Thread-Plan Roster

Every roster entry appears, one line each, copied verbatim from
`references/inventory-and-planning.md` (The Roster) — never derived from
memory. Statuses are `spawn` or `not triggered: ⟨reason⟩`; there is no
"merged" status. Sharded entries get one row per shard (`EPW1`, `EPW2`).
The planner assigns priority batches; the orchestrator records the
subagent/task identifier when spawned, and the outcome when collected.

```markdown
# Thread plan — CL 9999999 PS3

| roster entry | scope | status | batch | subagent | outcome |
| --- | --- | --- | --- | --- | --- |
| Desk-Check Simulation + Arithmetic Drills | Push/Flush size math, delay_buffer.cc | spawn | 1 | task-a1 | 9 rows |
| Data Lineage | bytes: caller → buffer → socket | spawn | 1 | task-a2 | 4 rows |
| Callback And Task Lifetime | timer_ + flush callback | spawn | 1 | task-a3 | 6 rows |
| Container And View Invalidation | spans into buffer_ | spawn | 2 | task-a4 | 3 rows |
| Error-Path Walk | Push/Flush/OnTimer error branches | spawn | 1 | task-a5 | 7 rows |
| State × Method Matrix | DelayBuffer implicit states | spawn | 2 | task-a6 | matrix + 5 rows |
| Mode × Host-Capability Matrix | — | not triggered: CL adds a new class; no new mode/flag/container on an existing host | — | — | — |
| Teardown Order | ~DelayBuffer, Abort() | spawn | 2 | task-a7 | 4 rows |
| Mechanical Leads | script + manual leads, whole diff | spawn | 2 | task-b1 | 11 rows |
| Per-Surface Invariants | DelayBuffer public API | spawn | 3 | task-b2 | 6 rows |
| Async And Lifecycle | timer, posted flush, cancellation | spawn | 3 | task-b3 | 8 rows |
| State/Persistence/Cache | — | not triggered: no persisted data, cache, or doom/reset of stored state in diff | — | — | — |
| Integration And Feature Control | kDelayBufferFeature wiring | spawn | 3 | task-b4 | 5 rows |
| Security And Trust Boundaries | — | not triggered: no IPC/Mojo surface; delay params come from browser-side config, not renderer | — | — | — |
| Contracts And API Shape | delay_buffer.h contracts, Socket base clauses | spawn | 3 | task-b5 | 6 rows |
| Tests As Specifications | delay_buffer_unittest.cc coverage map | spawn | 4 | task-b6 | 7 rows |
| Changed-Lines Polish | all changed lines | spawn | 4 | task-b7 | 5 rows |
| Holistic-and-polish thread | bug alignment, scope, description coverage | spawn | 4 | task-b8 | 4 rows |
```

## Subagent Brief — Discovery Thread

Fill this in; do not compose briefs freehand. Every path is absolute —
subagents start cold in the repository checkout, where skill-relative paths
do not resolve.

```text
You are one discovery thread of a Chromium CL review. Execute exactly the
procedure below. Your deliverable is ledger rows, not prose narrative, and
not fixes.

1. Pin: CL 9999999, patchset 3,
   revision 4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9,
   parent 8b1d77e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b177.
   Read-only worktree: /tmp/scratch/cl-9999999-ps3/worktree
   (verify first: git -C <worktree> rev-parse HEAD matches the revision).
   Diff: git -C <worktree> diff 8b1d77e6f5a4 4f2a09c1d8e7

2. Scope: net/streams/delay_buffer.cc and delay_buffer.h — functions
   DelayBuffer::Push, DelayBuffer::Flush, DelayBuffer::OnTimer. Other
   threads own everything else. Other threads' findings are context, not
   work items: do not implement, extend, or execution-validate them.

3. Procedure: read
   /home/user/src/ai-skills/chromium-code-review/references/deep-dive-recipes.md;
   apply the Context Rules, then run "Recipe: Error-Path Walk" on the scoped
   functions. Execute the recipe as written — do not work from a summary of
   it.

4. Deliverable: write your compliance matrix and candidate rows to
   /tmp/scratch/cl-9999999-ps3/ledger/EPW.md in the shapes from
   /home/user/src/ai-skills/chromium-code-review/references/templates.md,
   with row IDs EPW-1, EPW-2, ... First the compliance matrix: one row per
   recipe step per scoped function, each answered with concrete `path:line`
   evidence or N/A-with-reason — an unanswered row is a skipped check, and
   "no findings" without a complete matrix is not an acceptable return.
   Then the candidate rows: claim, repo-relative `path:line`, evidence, and
   either an IF/THEN/UNLESS hypothesis or a trace record
   (scenario → lines visited → outcome). Leave severity blank. Your final
   message is only: the list of row IDs you produced and the ledger file
   path.

5. Rules: discovery enumerates without filtering — "probably fine" rows are
   still rows; an incomplete recipe step (a guard you cannot name, a test
   you cannot find) is itself a row; the CL description is a claim to audit,
   not ground truth. Close a matrix row clean only by citing the guard line
   or the safe trace. Any anomaly your answer records — a success-shaped
   return after failure cleanup, duplicated cleanup, a skipped check, an
   unawaited write — becomes a candidate row even if it looks benign;
   benignity is verification's call, not yours. You are read-only outside
   your own ledger file: never edit a repository file, even when the
   harness invites it. If your scope will not fit in your context, do not
   thin out the tracing to finish: complete what you can at full rigor,
   write it to your ledger file, and end with "partial — remaining:
   ⟨unprocessed functions/files/cells⟩" so the orchestrator can spawn a
   continuation.
```

If the harness denies subagents file access, item 4 changes to: return the
full matrix and all rows in the final message — never summarized.

## ledger/⟨THREAD⟩.md — Compliance Matrix And Candidate Rows

The exact section headings `## Compliance matrix` and `## Candidate rows`
are load-bearing: late-phase agents extract the row sections mechanically
(`sed`/`grep`) instead of reading whole ledgers, so a renamed heading makes
a thread's rows invisible to verification and reconciliation.

```markdown
# EPW — Error-Path Walk — CL 9999999 PS3

Scope: DelayBuffer::Push, ::Flush, ::OnTimer (net/streams/delay_buffer.cc)

## Compliance matrix

| # | step / question | answer | evidence | candidate |
| --- | --- | --- | --- | --- |
| 1 | Push: cleanup skipped on early return? | ERR_ABORTED path leaves `pending_` set | net/streams/delay_buffer.cc:141 | EPW-1 |
| 2 | Push: completion callback invoked on every path? | yes — all three returns run `std::move(callback_)` | net/streams/delay_buffer.cc:120,133,144 | — |
| 3 | Flush: members left half-initialized? | N/A — Flush has no early returns | net/streams/delay_buffer.cc:150-171 | — |
| 4 | OnTimer: return value traced one step into consumer? | returns `write_len_` after `OnWriteFailure()` ran | net/streams/delay_buffer.cc:203 | EPW-2 |

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| EPW-1 | ERR_ABORTED path leaves `pending_` set; next Push hits `CHECK(!pending_)` | net/streams/delay_buffer.cc:141 | IF Push returns ERR_ABORTED THEN `pending_` stays true and the next Push CHECK-crashes UNLESS a reset path clears it (none found in this class) | CL-introduced | | candidate |
| EPW-2 | Success-shaped return after failure cleanup | net/streams/delay_buffer.cc:203 | trace: OnTimer → OnWriteFailure() at :199 clears `buffer_` → returns `write_len_ > 0` → caller's DoLoop treats the failed write as progress | CL-introduced | | candidate |
```

The matrix row 1 shows the anomaly rule in action: the answer records the
anomaly AND emits the candidate. Row 4 is the mandatory-candidate class
(success-shaped return after failure cleanup) — recorded, never adjudicated
in-thread.

## Per-File Floor Rows

Every changed file must have at least one ledger row — attention collapses
onto the first and largest files, and the per-file floor keeps coverage even
across the tail of the diff. When no thread emitted a row for a file, the
collection-audit agent reads that file's diff and adds an explicit
clean-or-candidate `ORC` row to `collection.md` (never a silent omission):

```markdown
| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| ORC-1 | clean: file only re-exports the new header; no logic | net/streams/delay_buffer_export.h:1-14 | whole file read; two `#include`s and a comment | CL-introduced | | clean (cited) |
```

## Subagent Brief — Verification Skeptic

```text
You are a verification skeptic for a Chromium CL review. Your job is to
REFUTE each candidate below; a refutation you cannot complete is a
confirmation, not a dismissal.

1. Pin: CL 9999999, patchset 3,
   revision 4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9; read-only worktree at
   /tmp/scratch/cl-9999999-ps3/worktree (verify rev-parse HEAD first).

2. Candidates under test (full rows inline — this is skeptic batch 1):
   EPW-2 | Success-shaped return after failure cleanup |
   net/streams/delay_buffer.cc:203 | trace: OnTimer → OnWriteFailure() at
   :199 clears buffer_ → returns write_len_ > 0.

3. Procedure: read
   /home/user/src/ai-skills/chromium-code-review/references/verification-and-fixes.md
   — the "Verifying Candidate Findings" and "Skeptic Verdicts" sections —
   and refute under that standard.

4. Deliverable: write one verdict row per candidate to
   /tmp/scratch/cl-9999999-ps3/verification/V1.md, IDs V1-1, V1-2, ...,
   in the shape from templates.md. CONFIRMED requires the completing trace
   plus a severity proposal matched to the anchor table in
   /home/user/src/ai-skills/chromium-code-review/references/synthesis-and-output.md
   plus an origin label. REFUTED requires the guard `path:line` or the
   concrete safe trace. UNPROVEN requires what you traced, what remains
   unproven, and a drafted question for the CL owner. Your final message
   is only: verdict per row ID and the file path.

5. Rules: refute with code, not memory. "Looks handled", "the caller
   probably checks", and "by design" are not refutations. You are read-only
   outside your own verdict file.
```

## verification/ — Batches And Skeptic Verdict Rows

The verification planner writes `verification/batches.md` — the
candidate→batch map plus merge proposals — and one skeptic brief per batch:

```markdown
# Verification batches — CL 9999999 PS3

## Merge proposals (dispositions for reconciliation; rows are never edited)

| row | proposal |
| --- | --- |
| AL-1 | merge-into EPW-2: same return-path defect, duplicate evidence |

## Batches

| batch | brief | candidates | verdict file |
| --- | --- | --- | --- |
| V1 | briefs/V1.md | EPW-2 | verification/V1.md |
| V2 | briefs/V2.md | EPW-1, AL-2, AL-3 | verification/V2.md |
| V3 | briefs/V3.md | ML-1, ML-2, CLP-1..CLP-5 | verification/V3.md |
```

Each skeptic writes its own `verification/V⟨batch⟩.md`:

```markdown
# Verification verdicts — batch V1 — CL 9999999 PS3

| id | candidate | verdict | evidence | severity (anchor) | origin |
| --- | --- | --- | --- | --- | --- |
| V1-1 | EPW-2 | CONFIRMED | trace: timer fires after write failure; delay_buffer.cc:199 clears buffer_, :203 returns write_len_=1024; consumer delay_stream.cc:88 advances its offset → bytes silently lost | P1 (anchor: success-shaped return after failure cleanup) | CL-introduced |
| V2-1 | EPW-1 | REFUTED | guard: delay_buffer.cc:96 — Abort() resets pending_ before any caller can re-enter Push; safe trace: Push → ERR_ABORTED → Abort → Push completes | — | — |
| V2-3 | AL-3 | UNPROVEN | traced both orderings; could not establish whether OnDisconnect can run before OnTimer on the IO sequence → Question Q2 for owner: "Can the disconnect handler run before a queued OnTimer on the same sequence?" | — | — |
```

(The V2 rows above belong in `verification/V2.md`; they are shown here only
to illustrate all three verdict shapes.)

## root-cause/ — Root-Cause Rows

One row per P1/P2 candidate, risky P3, or proposed fix, with the fields from
the Root-Cause, Layering, And Fix Optimality section. Each root-cause
challenger owns one batch and writes its own file (`root-cause/RC1.md`,
rows `RC1-⟨n⟩`), so concurrent challengers never collide:

```markdown
# Root-cause rows — batch RC1 — CL 9999999 PS3

## RC1-1 (for EPW-2 / V1-1)

- Symptom: consumer advances past bytes the socket never accepted.
- Direct trigger: write failure while a flush timer is armed.
- Violated invariant: a completion value must report what the operation
  actually did (bytes accepted XOR error), on every path.
- Invariant owner: DelayBuffer::OnTimer's return contract with the DoLoop in
  DelayStream::DoWriteComplete.
- Right-layer evidence: upstream (socket Write) already reports the error
  correctly (delay_socket.cc:171); local layer drops it; downstream caller
  cannot distinguish (delay_stream.cc:88). Shared helper checked:
  OnWriteFailure() is the canonical cleanup and is correct — only the return
  value after it is wrong.
- Callsite coverage: OnTimer is the only caller of OnWriteFailure that also
  returns a length (delay_buffer.cc:203); Flush propagates the error
  (delay_buffer.cc:167).
- Chosen-fix verdict: validated right layer — return the error from OnTimer
  after cleanup; no API change needed.
```

## reconciliation.md — Reconciliation Table And Pre-Output Gate

One line per row ID, enumerated from the files (`ledger/*.md`,
`collection.md`, `verification/*.md`, `root-cause/*.md`) — never from a
summary of them. No ranges, no "rest dismissed": a row without its own line
blocks output.

```markdown
# Reconciliation — CL 9999999 PS3

| row | thread | disposition |
| --- | --- | --- |
| EPW-1 | Error-Path Walk | refuted (V2-1: guard delay_buffer.cc:96) |
| EPW-2 | Error-Path Walk | promoted → Finding 1 (P1, V1-1, RC1-1) |
| AL-1 | Async And Lifecycle | merged → EPW-2 (same return-path defect, duplicate evidence) |
| AL-2 | Async And Lifecycle | refuted (V2-2: timer stopped in Abort, delay_buffer.cc:97) |
| AL-3 | Async And Lifecycle | question → Q2 (V2-3: UNPROVEN) |
| ML-1 | Mechanical Leads | promoted → Finding 3 (P3 non-ASCII em dash in comment) |
| ML-2 | Mechanical Leads | dismissed: intentional sentinel, values agree (V3-2 citation) |
| ORC-1 | Collection audit | clean (cited) |
| RC1-1 | Root-cause challenger | supports Finding 1; no new rows opened |
```

The gate is filled at the bottom of the same file; the canonical checklist
lives in `references/synthesis-and-output.md` (Pre-Output Gate). Filled
lines look like:

```markdown
## Pre-output gate

1. Pin: yes — pin.md; review states PS3 / 4f2a09c1; metadata refreshed
   16:41, no newer patchset.
2. Roster: yes — plan.md has all 18 entries; 3 not-triggered with reasons.
3. Collection: yes — 15 spawned, 15 ledger files present.
...
```

## Final-Review Finding

```markdown
#### 1. Failed flush reported as success — silent byte loss (P1)

- **Claim:** When the flush timer fires after a write failure,
  `DelayBuffer::OnTimer` runs failure cleanup but still returns
  `write_len_`, so the caller's DoLoop advances past bytes the socket never
  accepted.
- **Location:** net/streams/delay_buffer.cc:203
- **Evidence:** OnWriteFailure() at delay_buffer.cc:199 clears `buffer_`;
  the subsequent `return write_len_;` reports 1024 accepted bytes;
  delay_stream.cc:88 advances the read offset by the returned count.
- **Severity:** P1 (anchor: success-shaped return after failure cleanup).
- **Origin:** CL-introduced.
- **Fix status:** validated fix — return the error code captured by
  OnWriteFailure() after cleanup completes (traced through immediate,
  delayed, and abort paths).
- **Regression test:** in delay_buffer_unittest.cc, fail the underlying
  write with ERR_CONNECTION_RESET while a flush is pending and assert the
  flush completion reports the error and the consumer offset does not
  advance.
- **Rows:** EPW-2 / V1-1 / RC1-1 (internal trail — omit from Gerrit-ready
  text).
```
