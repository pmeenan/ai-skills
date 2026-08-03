<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## root-cause/ — Plan, Root-Cause Rows, And Reopened Rows

The Root-Cause Planner, not the orchestrator, reads verdict files and applies
the trigger rules. It writes `root-cause/batches.md`:

When trigger-planning input exceeds the worker budget, derive the exact trigger
universe from fresh verdict/inventory indexes and partition it mechanically.
Keep candidate/verdict links and related inventory scopes together. Reserve a
disjoint RC-ID interval per shard whose length equals its trigger count:

```tsv
planner_shard	scope_path	output	trigger_ids	trigger_count	rc_start	rc_end	assigned_bytes
RCPLAN001	root-cause/planning/RCPLAN001.scope.tsv	root-cause/planning/RCPLAN001.md	verdict:V001-1,scope:T001	2	RC003	RC004	52110
RCPLAN002	root-cause/planning/RCPLAN002.scope.tsv	root-cause/planning/RCPLAN002.md	verdict:V002-3	1	RC005	RC005	28400
```

Intervals start after every existing/previously reserved RC ID, never overlap,
and stay reserved when unused. Each planner writes Trigger Accounting rows,
batch rows, and exact generated RC brief paths only to its immutable RCPLAN result,
using IDs inside its interval. The deterministic collector rejects
missing/duplicate/foreign triggers, overlapping/out-of-range batch IDs,
unaccounted triggers, absent briefs, and stale fingerprints. It requires the
shard union to equal the derived trigger universe exactly and assembles
canonical `root-cause/batches.md` in numeric RC order without making semantic
trigger or grouping decisions. Delta mode uses exactly the named round's
verdict triggers plus any new canonical trigger-scope IDs explicitly created
for that round; it never reschedules original inventory scopes.

```markdown
# Root-cause plan — CL 9999999 PS3

## Trigger accounting

| candidate / verdict | root family | trigger | disposition | RC batch |
| --- | --- | --- | --- | --- |
| EPW-2 / V001-1 | RF001 | P1 CONFIRMED + proposed fix | scheduled | RC001 |
| T001 | — | inventory: async/lifecycle + new state holder | scheduled | RC002 |
| CLP-1 / V003-3 | — | cheap P3 punctuation, no fix analysis | not applicable: no root-cause trigger proved by V003-3 | — |

## Batches

| batch | brief | root families / scopes | output | bounded input |
| --- | --- | --- | --- | --- |
| RC001 | briefs/RC001.md | RF001: EPW-2/V001-1, SMM-4/V004-1 | root-cause/RC001.md | one complete root family, 121 lines |
| RC002 | briefs/RC002.md | inventory scope T001 | root-cause/RC002.md | one change-level invariant walk |
```

Every CONFIRMED/UNPROVEN verdict, proposed fix, and inventory scope marked
root-cause required gets one trigger row, even when the result is
`not applicable` with cited verdict/index evidence. Every surviving root
family is scheduled as one semantic unit; never split one family because its
members came from different skeptic batches. Keep unrelated families separate.
If one family exceeds a worker budget, shard evidence extraction but provide
one challenger a compact synthesis containing every member ID.

When fresh `indexes/verdicts.tsv` contains zero data rows and
`indexes/inventory.tsv` contains no root-cause-required scope, the trigger set is
mechanically empty. Do not spawn a Root-Cause Planner or challenger; write the
canonical `root-cause/batches.md` fast path:

```markdown
# Root-cause plan — CL 9999999 PS3

- Verdict index: indexes/verdicts.tsv
- Inventory index: indexes/inventory.tsv
- Trigger count: 0
- Result: empty — the validated verdict index is empty and inventory proves no triggers

## Trigger accounting

None.

## Batches

None.
```

Any verdict row, unknown/malformed index value, or possible inventory trigger requires the Planner;
the empty path is proof-based, not inferred from a status message.

One root-cause row is written for each scheduled candidate or inventory scope, with the fields
from Root-Cause, Layering, And Fix Optimality. Each challenger owns one batch
and file (`root-cause/RC001.md`, rows `RC001-⟨n⟩`):

````markdown
# Root-cause rows — batch RC001 — CL 9999999 PS3

## RC001-1 (for EPW-2 / V001-1)

- Root family: RF001
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
- Suggested-edit decision: applicable — replaces net/streams/delay_buffer.cc:203
- Suggested-edit selected lines:

  ```cpp
  return write_len_;
  ```
- Suggested-edit replacement:

  ```suggestion
  return result;
  ```

## Root-family analysis

| root family | members | shared invariant | invariant owner | state / transition | method coverage | excluded nearby | fix layer | comment count | suggested edit | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RF001 | EPW-2/V001-1, SMM-4/V004-1 | completion reports bytes accepted XOR an error | DelayBuffer completion boundary | backend failure → cleanup → completion | Read, Write, and ReadMultiple checked; affected cells share the same pre-operation state contract | Connect excluded because it establishes rather than consumes the state | enforce the contract at the shared state boundary | one — members share owner and bad outcome | applicable — RC001-1 | delay_buffer.h:61-75; delay_buffer.cc:180-205 |

````

Every RC row has an exact `Root family` and `Suggested-edit decision`. An
applicable decision uses the multiline `Suggested-edit selected lines` and
`Suggested-edit replacement` fields above; an omitted decision uses
`omitted — <specific reason>` and has neither fence. The root-family table
stores only `applicable — <RC-row-ID>` or the exact omitted decision. This
keeps multiline code out of lossy table cells and gives reconciliation a
canonical decision to copy into the evidence card.

Reopened candidates become canonical rows before further work. For round 1,
challenger RC001 owns `ledger/reopened/round-1-RC001.md`:

```markdown
# Reopened candidates — round 1 / RC001

## Candidate rows

| id | parent rows | claim | location | evidence / hypothesis | requested recipe | origin | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1-RC001-1 | EPW-2 / V001-1 / RC001-1 | sibling caller can report stale progress | net/streams/other_delay_stream.cc:90 | IF the shared helper is entered after cleanup THEN it returns stale length UNLESS caller resets write_len_ (not found) | Error-Path Walk: OtherDelayStream completion paths | CL-introduced | candidate |

## Candidate descriptors

| candidate | classes | obligations | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1-RC001-1 | contract | base-contract, caller-reachability, callee/backend-implementation | shared completion-helper contract | unknown — delta verification must compare sibling callers | completion reports bytes XOR error | backend failure → cleanup → sibling completion | unknown — compare helper and sibling caller | OtherDelayStream, OnWriteFailure |
```

A row that exists only in a status line or brief does not exist. Requested
recipe work uses a Generated Common Header discovery brief and appends evidence
or additional rows under `ledger/reopened/`; then the Verification Planner runs
in delta mode over exactly the round IDs and the Root-Cause Planner runs in
delta mode over their verdicts. Increment the round until no open/triggered
rows remain. No challenger writes a skeptic brief directly.
