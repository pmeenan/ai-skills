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
