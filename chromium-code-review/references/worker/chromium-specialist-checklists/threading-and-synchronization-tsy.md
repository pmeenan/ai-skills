<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Threading And Synchronization (TSY)

Within a routed scope, inspect locks, condition variables, waitable events, atomics,
`SequenceChecker`, `ThreadChecker`, cross-sequence callbacks, `ThreadPool`, task
traits, or mutable state reached from multiple sequences.

In the thread ledger, produce `state | readers | writers | synchronization |
required order`, a lock-order graph, wait/post/cancel/destroy timelines, and
`TSY-*` rows with citations to synchronization edges and interleaving tests.

- Enumerate all shared mutable fields and require one consistent protection
  strategy. Name the happens-before edge covering both publication and payload.
- Justify every atomic load/store/exchange/RMW memory order. Flag relaxed
  publication, compound invariants split across atomics, stale compare/exchange
  expected values, and ABA for reusable addresses, slots, or generations.
- Add lock-acquisition edges from success and error paths. Flag cycles,
  callbacks or blocking calls under locks, and unlocked use of invalidatable
  state.
- Require condition-variable waits to re-check a predicate in a loop. Trace
  predicate mutation/signaling under the right lock; probe signal-before-wait,
  spurious wakeup, cancellation, and shutdown for lost wakeups.
- Verify `SEQUENCE_CHECKER` construction or `DETACH_FROM_SEQUENCE` establishes
  the intended first-use sequence. Trace handoff, move, reset, and destruction;
  checked methods do not make a cross-sequence destructor safe.
- Check `ThreadPool` `MayBlock`/`WithBaseSyncPrimitives`, priority, and shutdown
  behavior. Prevent abandoned required cleanup, shutdown stalls, priority
  inversion, and blocking on latency-sensitive sequences.
- Require deterministic interleaving tests using barriers/events/task
  environments or mock time. Sleep-based timing and one schedule prove nothing.
