<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## inventory.md — Changed-Surface Inventory And Risk-Area Map

```markdown
# Inventory — CL 9999999 PS3

## Changed surfaces

| surface ID | surface | owned hunks / earliest changed line | contract source | callers | old → new behavior | state / lifetime | tests | reachability | scope label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0001 | DelayBuffer::Push (delay_buffer.h:41) | H0001 / net/streams/delay_buffer.h:41 | header comment | DelayStream::DoWrite | new API | owns buffer_, pending_ | delay_buffer_unittest.cc | production | core |
| S0002 | DelayBuffer::Flush (delay_buffer.h:48) | H0001,H0004 / net/streams/delay_buffer.h:48 | header comment | DelayStream teardown | new API | drains buffer_ | none found | production | core |
| S0003 | DelayBufferTest fixture (delay_buffer_unittest.cc:28) | H0005 / net/streams/delay_buffer_unittest.cc:28 | test fixture | TEST_F members (S0004) | new fixture: mock socket + mock time | owns mock_socket_, task_env_ | self | test-only | test/support |
| S0004 | group: 23 TEST_F(DelayBufferTest, Push*/Flush*/Abort*) | H0006-H0014 / net/streams/delay_buffer_unittest.cc:62 | N/A (class) | N/A (class) | new coverage: push/flush/abort paths incl. error and teardown | N/A (class) | self | test-only | test/support |

Homogeneous surface classes — test bodies, generated blocks, mechanical
accessor blocks, data-only tables — appear as one `group:` row per file (per
fixture for tests) with a member count and name list/pattern, per the
aggregation rule in `references/inventory-and-planning.md`. Fixtures and
stateful helpers/mocks keep individual rows. Class-meaningless fields are
`N/A (class)`; no per-member caller lookups.

## Risk-area map

| file | risk areas |
| --- | --- |
| net/streams/delay_buffer.cc | async/lifecycle, buffering/backpressure, memory ownership |
| net/streams/delay_buffer_unittest.cc | tests |

## Trigger inventory

| scope ID | surface | discovery triggers | root-cause trigger | graph scope | evidence |
| --- | --- | --- | --- | --- | --- |
| T001 | DelayBuffer timer/queue state holder | CTL, SMM, AL, TDO, TSY hard | required: changed sequence ownership and cancellation order | graph:E-STATE-1 | delay_buffer.h:55-78 |
| T002 | test description cleanup | TAS, CLP | not required: test prose only | graph:E-CALL-1 | delay_buffer_unittest.cc:310 |
| T003 | Ownership And Blink Lifecycle | OBL absent | not required: no ownership/Blink-lifecycle path, symbol, surface, or profile signal matched | — | profile.json:/risk_signals; pin.md:/Changed-files |
```

Schema-3 inventory also contains the typed handoff graph:

```markdown
## Complexity graph edges

| edge | from | to | kind | status | evidence |
| --- | --- | --- | --- | --- | --- |
| E-CALL-1 | S0001 | DelayStream::DoWrite | caller | open | callers/index.tsv:/DelayBuffer::Push |
| E-STATE-1 | S0001 | S0002 | state-transition | open | net/streams/delay_buffer.cc:41-88 |
```

Allowed kinds are `caller`, `ownership`, `lifetime`, `state-transition`,
`data-format`, `error-flow`, `persistence`, `cross-sequence`, `test-coverage`,
and `candidate-affinity`. Ledger producers update them append-only:

```markdown
## Complexity graph delta

| edge | status | evidence | candidate | next obligation |
| --- | --- | --- | --- | --- |
| E-STATE-1 | candidate | net/streams/delay_buffer.cc:64-88 | AL-1 | trace teardown after queued failure |
```

Each schema-3 generalist ledger also records an independent soft escalation
prior for every specialist lens over its exact assigned edge slice:

```markdown
## Specialist escalation assessments

| lens | graph scope | likelihood | signals | counterevidence |
| --- | --- | --- | --- | --- |
| Threading And Synchronization | graph:E-CALL-1,E-STATE-1 | high | cross-sequence reply plus teardown-owned cancellation at net/streams/delay_buffer.cc:64-88 | WeakPtr blocks use-after-free but does not prove callback ordering; net/streams/delay_buffer.h:55-78 |
| Network Semantics | graph:E-CALL-1,E-STATE-1 | low | no request/response policy transition in the assigned graph; net/streams/delay_buffer.cc:41-88 | all values remain inside the existing stream contract at net/streams/delay_buffer.h:41-78 |
```

Use all ten exact specialist names and only `low`, `medium`, or `high`.
Signals and counterevidence must cite code/test evidence or graph edges. The
likelihood measures residual discovery value: whether a full sweep is likely
to uncover additional specialist edges. An isolated local construct with
closed ownership, uses, exits, and consumers may be low even though it matches
a soft amplifier. The
builder derives `indexes/specialist-priors.tsv`, rejects duplicate or malformed
assessments, and infers the assessor from the `GSS[shard]` or `GAI[shard]`
ledger identity.

For a zero-edge inventory, each generalist uses `graph:none` for all ten rows.
Those rows must be `low` with cited counterevidence. Medium or high means the
inventory failed to record the edge that creates the risk, so add that edge
before continuing.

Inventory scope IDs schedule analysis but are not ledger findings and do not
receive review dispositions. If root-cause work over a scope finds an issue,
the challenger creates a canonical reopened ledger row before verification.
Every triggerable recipe/checklist roster entry gets its own trigger row,
including a proved-absence row; never group several absent specialist entries
into one catch-all row. The always-run holistic row needs no trigger proof.
Every positive Chromium specialist trigger uses the exact token `<PREFIX>
hard`; `<PREFIX> absent` proves only that the hard-trigger column was checked.
Soft likelihood amplifiers never appear as positive trigger tokens. Under
schema 3, every positive Chromium specialist trigger also cites the
exact `graph:E-...` slice containing the triggering surface. Negative rows use
`—`; a full specialist row scoped to unrelated edges does not satisfy the
trigger.

After all inventory workers finish, run `scripts/build-review-indexes.py`.
It validates canonical inputs and atomically derives the sorted
`indexes/inventory.tsv`, effective `indexes/topology.tsv`, and
`indexes/specialist-priors.tsv` plus source fingerprints in
`indexes/manifest.json`:

```tsv
kind	id	subject	scope	tags	citations	source
surface	S0001	DelayBuffer::Push	core	production	delay_buffer.h:41	inventory.md
trigger	T001	DelayBuffer timer/queue state holder	required: changed sequence ownership and cancellation order	CTL,SMM,AL,TDO,TSY hard,root-cause-required=yes,graph-scope=graph:E-STATE-1	delay_buffer.h:55-78	inventory.md
trigger	T014	Security And Trust Boundaries	not required: no trust-boundary path/token matches	STB,root-cause-required=no,graph-scope=-	profile.json:/risk_signals	inventory.md
```

`source` and `id` identify the canonical narrative block to extract when
judgment is needed. IDs are stable within the pinned revision: unsharded
surfaces use `S0001...`; sharded surfaces use `S<I-shard>-0001...`; trigger
rows use monolithic `T<n>` or sharded `I<shard>-T<n>` IDs, where `<shard>` is
uppercase ASCII letters/digits (for example `I2-T7` or `INET-T003`). For a
dense single-file partition, each
hunk ID appears in exactly one shard scope, and the shard owning a surface's
earliest changed line owns the full surface row. A duplicate or missing owner
blocks planning.

Every index read also validates `indexes/manifest.json`; stale derived views
are never trusted:

```json
{
  "schema_version": 2,
  "indexes": {
    "inventory.tsv": {
      "row_count": 32,
      "output_sha256": "...",
      "sources": [{"path": "inventory.md", "bytes": 8124, "sha256": "..."},
                  {"path": "profile.json", "bytes": 4217, "sha256": "..."}]
    }
  }
}
```

The helper atomically regenerates an index and its manifest entry together.
Missing sources, fingerprint mismatches, duplicate IDs, or a pin mismatch
block every planner and fast path that depends on that index.
