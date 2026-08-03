<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## directives.md, progress.md, And orchestration.tsv

Both are orchestrator-written and deliberately tiny. `directives.md` (echoed
into every brief):

```markdown
# Directives — CL 9999999 PS3

- Mode: follow-up review (prior review text saved to prior-feedback-input.md)
- User directives: focus requested on net/streams; short-summary format NOT
  requested; no other constraints.
```

Only when the user actually requested a cheaper run, add a line-anchored
`tier-override: <the user's exact request>` entry; its presence downgrades
the validator's below-floor tier errors to disclosed warnings, so never
include it by default — prose that merely mentions the term mid-line does
not activate it.

`progress.md` is an append-only phase log — the orchestrator's resume point
after context loss. One line per event:

Every line is appended through `scripts/log-progress.py`, which stamps UTC
time and enforces the event grammar the cost report parses (phase elapsed
time, per-attempt spawn-to-collect latency). One `spawned` event per work
unit — even when a wave launches several at once — and one `collected` event
per collection; a retry logs its own attempt number.

```markdown
# Progress — CL 9999999 PS3

- 2026-07-01T14:02:11Z Phase 0 done: pinned PS3 4f2a09c1; profile high-risk; worktree verified.
- 2026-07-01T14:19:45Z Phase 1 done: context.md + inventory.md; risk areas: async, buffering, tests.
- 2026-07-01T14:31:02Z Phase 3 done: plan.md; 15 spawn / 3 not-applicable (proved); batches D01-D04.
- 2026-07-01T14:32:40Z spawned DCS attempt 1: batch D01
- 2026-07-01T14:32:41Z spawned DL attempt 1: batch D01
- 2026-07-01T15:04:18Z collected DCS attempt 1: 9 rows
- 2026-07-01T15:20:02Z spawned DCS attempt 2: continuation — remaining cells
...
```

`orchestration.tsv` is the structured authority for work-unit state, with one
row per attempt and fixed columns below. Rewrite current state atomically
through a sibling temporary file while retaining all prior attempt rows. Tabs
and newlines inside values are escaped; paths are absolute. `remaining_scope`
is mandatory for `partial`, `retryable`, `needs-repair`, and `terminated`.

```tsv
phase	work_id	attempt	state	tier	task_id	brief	artifact	remaining_scope	depends_on
4	EPW	1	partial	frontier	task-a5	/tmp/scratch/cl-9999999-ps3/briefs/EPW.md	/tmp/scratch/cl-9999999-ps3/ledger/EPW.md	OnTimer cancellation cells	PLAN
4	EPW	2	complete	frontier	task-b9	/tmp/scratch/cl-9999999-ps3/briefs/EPW-attempt-2.md	/tmp/scratch/cl-9999999-ps3/ledger/EPW.md	-	EPW:1
```

Allowed states are `queued`, `running`, `partial`, `retryable`, `needs-repair`,
`complete`, and `terminated`. `tier` records the resolved model tier the
attempt actually ran at (`mechanical`, `standard`, `frontier`, or `inherit`
when the harness cannot select models); a resolved tier below the plan's
recommendation requires a user directive or disclosed harness limitation. Only one attempt may write a canonical artifact
at a time. `progress.md` remains the compact human audit log;
`orchestration.tsv` is the mechanically queryable authority.
