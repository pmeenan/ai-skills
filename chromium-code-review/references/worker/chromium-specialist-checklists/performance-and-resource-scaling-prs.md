<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Performance And Resource Scaling (PRS)

Within a routed scope, inspect hot/startup code, per-frame/tab/process state, unbounded loops or
inputs, caches/queues, allocations/copies, task hops, timers/wakeups, GPU
resources, benchmarks, or claimed performance/memory effects.

In the thread ledger, produce `operation | cost/item | bound | fanout |
worst cost`, `resource | owner | cap | eviction/release | pressure behavior`,
before/after evidence, and `PRS-*` rows citing bounds and measurements.

- Derive time/space complexity, including hidden scans, repeated sorting,
  nested callbacks, string building, and retries on adversarial input.
- Multiply by tabs, frames, documents, origins, processes, profiles, observers,
  devices, retries, and queued events as applicable.
- Require limits and eviction for queues, maps, caches, histories, pending
  requests, and buffers. Check churn, duplicates, memory pressure, and teardown.
- Count allocations, copies, serialization passes, conversions, and temporaries;
  verify the actual overload and backing-store ownership permit moves.
- Trace thread/process hops, blocking, priority inversion, and work that wakes an
  idle process/device. Quantify polling/timer wakeups in background/no-work.
- Account for startup and binary size: static initialization, eager services,
  templates, generated tables, and per-locale/config resources.
- For GPU work, calculate resource bytes, copies, synchronization, readback,
  retained surfaces, device limits, and loss/reset cleanup.
- Require representative benchmarks/profiles with units, variance, stable
  comparison, and a metric/trace isolating the changed work.
