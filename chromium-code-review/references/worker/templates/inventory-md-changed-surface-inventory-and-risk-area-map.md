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

| scope ID | surface | discovery triggers | root-cause trigger | evidence |
| --- | --- | --- | --- | --- |
| T001 | DelayBuffer timer/queue state holder | CTL, SMM, AL, TDO | required: async/lifecycle + new state holder | delay_buffer.h:55-78 |
| T002 | test description cleanup | TAS, CLP | not required: test prose only | delay_buffer_unittest.cc:310 |
| T003 | Ownership And Blink Lifecycle | OBL absent | not required: no ownership/Blink-lifecycle path, symbol, surface, or profile signal matched | profile.json:/risk_signals; pin.md:/Changed-files |
```

Inventory scope IDs schedule analysis but are not ledger findings and do not
receive review dispositions. If root-cause work over a scope finds an issue,
the challenger creates a canonical reopened ledger row before verification.
Every triggerable recipe/checklist roster entry gets its own trigger row,
including a proved-absence row; never group several absent specialist entries
into one catch-all row. The always-run holistic row needs no trigger proof.

After all inventory workers finish, run `scripts/build-review-indexes.py`.
It validates canonical inputs and atomically derives the sorted
`indexes/inventory.tsv` plus source fingerprints in `indexes/manifest.json`:

```tsv
kind	id	subject	scope	tags	citations	source
surface	S0001	DelayBuffer::Push	core	production	delay_buffer.h:41	inventory.md
trigger	T001	DelayBuffer timer/queue state holder	required: async/lifecycle + new state holder	CTL,SMM,AL,TDO,root-cause-required=yes	delay_buffer.h:55-78	inventory.md
trigger	T014	Security And Trust Boundaries	not required: no trust-boundary path/token matches	STB,root-cause-required=no	profile.json:/risk_signals	inventory.md
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
