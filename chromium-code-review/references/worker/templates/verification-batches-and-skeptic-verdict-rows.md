<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## verification/ — Batches And Skeptic Verdict Rows

The verification planner writes `verification/batches.md` — the
candidate→batch map plus merge proposals — and one skeptic brief per batch:

When planning input exceeds the worker budget, partition mechanically by exact
candidate IDs before spawning planners. Keep mechanically proposed duplicate
affinity groups together. Reserve a disjoint V-ID interval per shard whose
length equals its candidate count (the maximum batches it can emit):

```tsv
planner_shard	scope_path	output	candidate_ids	candidate_count	v_start	v_end	assigned_bytes
VPLAN001	verification/planning/VPLAN001.scope.tsv	verification/planning/VPLAN001.md	EPW-2,AL-1,AL-2	3	V004	V006	48120
VPLAN002	verification/planning/VPLAN002.scope.tsv	verification/planning/VPLAN002.md	ML-1,CLP-1	2	V007	V008	31210
```

Intervals start after every existing/previously reserved V ID, never overlap,
and remain reserved even when a shard uses fewer batches. A shard may emit
only IDs inside its interval and records unused IDs. Each scope contains exact,
non-overlapping candidate IDs and their canonical source selectors. Each
planner result contains merge proposals and batch rows in the canonical shapes
plus the exact generated brief paths; it never writes `batches.md`.

The deterministic collector rejects missing/duplicate/foreign candidate IDs,
overlapping/out-of-range batch IDs, a merge whose survivor is not scheduled,
missing briefs, and stale input fingerprints. It requires the shard union to
equal the selected candidate-index universe exactly, then concatenates merge
and batch rows in numeric V order into canonical `verification/batches.md`
without adjudicating them. Delta planning applies the same contract to exactly
the named reopened-round IDs.

```markdown
# Verification batches — CL 9999999 PS3

## Merge proposals (dispositions for reconciliation; rows are never edited)

| row | proposal |
| --- | --- |
| AL-1 | merge-into EPW-2: same trigger, invariant, and bad outcome; duplicate evidence at delay_buffer.cc:203 |

## Batches

| batch | brief | candidates | verdict file |
| --- | --- | --- | --- |
| V001 | briefs/V001.md | EPW-2 | verification/V001.md |
| V002 | briefs/V002.md | EPW-1, AL-2, AL-3 | verification/V002.md |
| V003 | briefs/V003.md | ML-1, ML-2, CLP-1, CLP-2, CLP-3, CLP-4, CLP-5 | verification/V003.md |
```

When fresh `indexes/candidates.tsv` has zero data rows after exact source
fingerprint validation, do not
spawn a Verification Planner or skeptic. Write this canonical fast-path file
mechanically:

```markdown
# Verification batches — CL 9999999 PS3

- Input candidate index: indexes/candidates.tsv
- Candidate count: 0
- Result: empty — exact candidate index contains zero rows

## Merge proposals

None.

## Batches

None.
```

This is valid only for a present, validated zero-row index. It is not a
fallback for missing ledgers, incomplete collection, or parser failure. After
writing it, regenerate indexes so `indexes/verdicts.tsv` is a fresh zero-row
view with current source fingerprints before evaluating the root-cause fast
path.

### Budget-limited verification

When the recorded spawn budget or deadline is exhausted, preserve the batch
plan and every candidate. For each terminated skeptic batch, append this table
to `verification/batches.md`, with one row per directly assigned candidate and
one per proposed merge alias whose ultimate survivor is in that batch:

```markdown
## Budget-limited verification

| candidate | batch | attempt | survivor | reason |
| --- | --- | --- | --- | --- |
| EPW-3 | V038 | 1 | - | spawn-budget exhausted |
| AL-4 | V038 | 1 | EPW-3 | spawn-budget exhausted |
```

Use `deadline exhausted` only after the recorded UTC deadline; otherwise use
`spawn-budget exhausted` only after that many recorded task-bearing attempts.
The batch and latest terminated attempt must match the preserved plan. Its
`remaining_scope` must be exactly `budget exhausted; candidates: ` followed by
the comma-separated directly assigned candidate IDs (not merge aliases).
Each gap's sealed brief must name every directly assigned candidate. A changed
brief, missing termination, incomplete alias coverage, or existing verdict
blocks this exception. Never invent a REFUTED or UNPROVEN result for work not
done. User-priority verification and unresolved blockers remain explicit; do
not silently replace a promised finding validation with a gap.

For an unstarted/unsealed batch, seal its existing brief with the normal
`seal-work-unit.py` helper, phase 5 and frontier tier, artifact
`verification/V038.md`, and the batch plan as a control input. Immediately
terminate the sealed attempt using `set-work-state.py` with the exact
`remaining_scope` above and `--log`. Do not spawn it or materialize unused code
packets. Only authenticated budget gaps on a work unit with no task ID in any
attempt may omit unread named inputs; the brief self-row and exact assignment
remain required. Started units retain all ordinary input-integrity checks.

Every gap ID's reconciliation disposition is exactly
`unreviewed — budget exhausted`. An alias in this table is an **unverified
merge proposal**, never a validated merge. All other candidates retain the
normal verdict/merge obligations; delivered findings and questions retain all
root-cause, evidence-card, challenge, and freshness gates. A tentative proposed
fix in an unverified discovery row does not manufacture a verified root family;
it remains unreviewed with that candidate. Actual CONFIRMED/UNPROVEN verdicts,
actual suggested-edit decisions, and all required inventory triggers retain
normal root-cause accounting. The challenge covers these unreviewed
reconciliation rows as well as delivered findings.

A budget-limited draft must contain `- Review completeness: limited` and this
exact count-bearing text under `## Verification Notes`, plus a visible link to
`verification/batches.md` containing the full gap table:

```text
Limited review: 2 candidate IDs were not independently verified because the review budget was exhausted.
```

Count direct candidates and unverified aliases. Neither draft nor Gerrit
output may claim LGTM, a clean review, or complete verification. Preserve these
omissions in plan/progress and do not infer that absence of a verified finding
means the deferred hypotheses were refuted.

Every candidate row appears exactly once as either a verification-batch member
or a merge proposal. A proposed merge does not require a second skeptic verdict
for the merged row; reconciliation must validate that its trigger, invariant,
and outcome are equivalent to the survivor and cite the survivor's verdict. If
equivalence is not established, reject the merge and schedule the row in its
own verification batch.

Each skeptic writes its own `verification/V⟨batch⟩.md`:

```markdown
# Verification verdicts — batch V001 — CL 9999999 PS3

| id | candidate | verdict | evidence | severity (anchor) | origin |
| --- | --- | --- | --- | --- | --- |
| V001-1 | EPW-2 | CONFIRMED | trace: timer fires after write failure; delay_buffer.cc:199 clears buffer_, :203 returns write_len_=1024; consumer delay_stream.cc:88 advances its offset → bytes silently lost | P1 (anchor: success-shaped return after failure cleanup) | CL-introduced |
| V002-1 | EPW-1 | REFUTED | guard: delay_buffer.cc:96 — Abort() resets pending_ before any caller can re-enter Push; safe trace: Push → ERR_ABORTED → Abort → Push completes | — | — |
| V002-3 | AL-3 | UNPROVEN | traced both orderings; could not establish whether OnDisconnect can run before OnTimer on the IO sequence → Question Q2 for owner: "Can the disconnect handler run before a queued OnTimer on the same sequence?" | — | — |

## Trace closure

| candidate | obligation | result | evidence |
| --- | --- | --- | --- |
| EPW-2 | base-contract | PROVES CANDIDATE | DelayBuffer::OnTimer promises an operation result at delay_buffer.h:71; its caller treats positive values as accepted bytes at delay_stream.cc:88 |
| EPW-2 | caller-reachability | PROVES CANDIDATE | production trace DelayStream::DoWrite → DelayBuffer::OnTimer → DoWriteComplete at delay_stream.cc:71-91 |
| EPW-2 | callee/backend-implementation | PROVES CANDIDATE | backend error reaches OnWriteFailure at delay_buffer.cc:199 but :203 replaces it with write_len_ |

## Verified affinity

| candidate | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- |
| EPW-2 | OnTimer completion result consumed by DelayStream::DoWriteComplete | DelayBuffer::OnTimer completion boundary | completion reports bytes accepted XOR an error | backend write failure → cleanup → timer completion | return the retained backend error from OnTimer after cleanup | DelayBuffer::OnTimer, OnWriteFailure, DelayStream::DoWriteComplete |
```

(The V002 rows above belong in `verification/V002.md`; they are shown here only
to illustrate all three verdict shapes.) Each candidate has one Trace closure
row per declared obligation and exactly one Verified affinity row. Trace
results are `PROVES CANDIDATE`, `REFUTES CANDIDATE`, `NEUTRAL`, `OPEN`, or
`NOT APPLICABLE — reason`. Each row cites code or uses an explicit
`evidence-exception:`. CONFIRMED requires at least one proving row and no OPEN
row; REFUTED requires at least one refuting row and no OPEN row; UNPROVEN
requires an OPEN row. For async-lifetime claims, local variable or member
destruction is never sufficient by itself: close the backend operation owner,
buffer-retention contract, callback invalidation, destruction/cancellation,
and every relevant platform branch.

After skeptic collection, regenerate `indexes/verdicts.tsv` mechanically:

```tsv
id	candidate	verdict	severity	origin	citations	evidence_excerpt	source	trace_closure	base_interface	invariant_owner	violated_invariant	state_transition	proposed_fix_layer	related_symbols	root_family
V001-1	EPW-2	CONFIRMED	P1	CL-introduced	delay_buffer.cc:199-203	trace: timer fires...	verification/V001.md	base-contract=PROVES CANDIDATE; caller-reachability=PROVES CANDIDATE; callee/backend-implementation=PROVES CANDIDATE	OnTimer completion contract	DelayBuffer::OnTimer	completion reports bytes XOR error	write failure → cleanup → completion	return retained error	OnTimer, DoWriteComplete	RF001
```

Every non-merged candidate has exactly one verdict. Merged candidates retain
their explicit merge edge in `verification/batches.md`. Missing, duplicate, or
unknown candidate references block root-cause planning.
