<!-- Generated from ../../scaling-and-indexes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Scaling And Compact Indexes

Use this contract to scale effort without weakening coverage or overfilling an
agent context. The deterministic helpers produce routing evidence; workers
still make semantic review decisions.

## Agent Input Budget

Before generating a brief, estimate the bytes or tokens of every assigned
artifact and required reference section. When the harness exposes context
capacity, assigned input may consume at most 35% of it. Use a tokenizer when
available and a conservative four-bytes-per-token estimate otherwise. When
capacity is unknown, use 128 KiB as the assigned-artifact ceiling. The limit
excludes neither repeated headers nor reference text: count everything the
worker must load. Leave the remaining context for code, tool output, reasoning,
and the deliverable.

Assign the generated per-section worker references
(`references/worker/⟨stem⟩/⟨slug⟩.md` in the snapshot) rather than whole
reference files whenever the worker needs only named sections; each section
file is an immutable packet with its own measurable size, which keeps
reference overhead out of every worker's 35% budget.

Scoped code enters the same accounting through code packets: the planner's
`packets/⟨WORK⟩.spec.tsv` is materialized into `packets/⟨WORK⟩-code.md`
before sealing and manifested as an `assigned` input, so the largest input
class — the code itself — is measured and budgeted per worker instead of
re-derived invisibly. A packet that alone approaches the worker budget is a
sharding signal, exactly like any other oversized assigned input.

If a unit exceeds the budget, shard it by a named natural unit before spawn.
If an already-running worker discovers deeper-than-profiled work, it writes a
full-quality partial artifact plus exact remaining scope and yields to a fresh
continuation. Never compress evidence or reduce the checklist to fit.
