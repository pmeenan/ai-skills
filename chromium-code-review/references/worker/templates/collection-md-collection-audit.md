<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## collection.md — Collection Audit

Use one Collection-Audit worker only when the measured ledgers and briefs fit
within `profile.json:/context_budget/worker_input_budget_bytes`. When
they do not, generate `collection/index.tsv` deterministically, packing whole
thread artifacts without splitting a thread across shards:

```tsv
shard	thread	plan_row	brief	ledger	ledger_bytes
CA001	EPW	Error-Path Walk	briefs/EPW.md	ledger/EPW.md	18342
CA001	AL	Async And Lifecycle	briefs/AL.md	ledger/AL.md	21940
CA002	TAS	Tests As Specifications	briefs/TAS.md	ledger/TAS.md	30411
```

Each spawned plan row appears exactly once. Each audit worker writes
`collection/shards/CA<batch>.md` with the Thread Audit and Gaps sections below,
plus a sorted `observed_files` list extracted from its candidate locations.
After all shards finish, the deterministic collector must:

1. reject missing/duplicate thread coverage and absent shard artifacts;
2. union observed files and diff them against the pinned changed-file list;
3. write `collection/uncovered-files.tsv` and schedule bounded floor-review
   shards for those files, whose only analytical output is canonical ORC rows;
4. verify every reported anomaly maps to a candidate or exact repair gap; and
5. assemble the immutable canonical `collection.md` without paraphrasing or
   dropping shard rows.

The collector performs no code-review judgment. Any failed exactness check
produces a targeted repair, not a best-effort merge.

```markdown
# Collection audit — CL 9999999 PS3

## Thread audit

| thread | expected artifact | matrix | anomaly-to-candidate | append/amendments | verdict |
| --- | --- | --- | --- | --- | --- |
| EPW | ledger/EPW.md | complete; all cells cited or N/A-with-reason | complete | valid | pass |
| AL | ledger/AL.md | complete; cell 7 closed by amendment A1 | complete | valid | pass |

## Per-file floor

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| ORC-1 | clean: file only re-exports the new header; no logic | net/streams/delay_buffer_export.h:1-14 | whole diff read | CL-introduced | | clean (cited) |

## Gaps

| unit | exact remaining scope | required action |
| --- | --- | --- |

A `gap: ...` verdict requires a matching Gaps row, and the Audit result may
read `complete` only when the Gaps table is empty or every remaining gap's
work unit is `terminated` in orchestration.tsv (the AL example above was
closed by a continuation amendment before this audit was finalized). The
validator enforces the exact ordered audit columns, rejects duplicate
thread rows, and reconciles gaps against orchestration state.

## Audit result

complete
```

The Audit result section's value line must be the exact normalized token
`complete` — written only when Gaps is empty or every remaining scope is
explicitly marked `terminated — unreviewed` in orchestration.tsv and
Verification Notes. The collection gate fails on anything else; prose like
"not complete"/"incomplete" never passes by substring accident.

After collection is complete, regenerate `indexes/candidates.tsv`
deterministically by
extracting canonical candidate definitions (including effective amendments)
from all ledger, reopened, prior-feedback, and ORC sources. It is the compact
Verification-Planner routing input; `evidence_excerpt` selects likely groups
but never replaces opening the canonical `source` row for judgment:

```tsv
id	claim	location	origin	severity	status	citations	evidence_excerpt	source	classes	obligations	base_interface	invariant_owner	violated_invariant	state_transition	proposed_fix_layer	related_symbols
EPW-2	failed flush reported as success	net/streams/delay_buffer.cc:203	CL-introduced	-	candidate	net/streams/delay_buffer.cc:203	trace: OnTimer...	ledger/EPW.md	contract	base-contract, caller-reachability, callee/backend-implementation	OnTimer completion contract	unknown — verification pending	completion reports bytes XOR error	write failure → timer completion	unknown — compare completion layers	OnTimer, DoWriteComplete
```

Every canonical candidate definition appears exactly once. Zero data rows is
the mechanically provable zero-candidate condition; a missing or malformed
source is an error, never an empty review.
