<!-- Generated from ../../scaling-and-indexes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Scaling And Compact Indexes

Use this contract to scale effort without weakening coverage or overfilling an
agent context. The deterministic helpers produce routing evidence; workers
still make semantic review decisions.

## Sharded Aggregation

Collection, verification planning, root-cause planning, reconciliation, and
challenge planning use map/collect topology whenever their indexed assigned
input exceeds the agent budget.

1. Partition exact row/surface IDs into non-overlapping shards under budget.
2. Give each worker the index slice and only its selected canonical bodies.
3. Write immutable shard artifacts; never have two workers write one canonical
   file.
4. Use a deterministic collector to verify union equality, zero duplicates,
   source fingerprints, and required fields before assembling the canonical
   manifest/table.
5. Route semantic conflicts to a bounded reconciliation worker; do not let the
   collector adjudicate them.

Dense single-file diffs may shard by stable hunk/surface range rather than
path. Each hunk and changed surface belongs to exactly one inventory shard;
file-level risks and per-file floor are checked across their union.

Do not pipeline final verification from an incomplete discovery corpus merely
to save latency. High-risk discovery may run first, but Collection remains the
barrier before the final candidate index, deduplication, and verdict plan.
