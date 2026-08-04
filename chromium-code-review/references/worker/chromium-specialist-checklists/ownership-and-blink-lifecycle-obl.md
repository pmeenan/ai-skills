<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Ownership And Blink Lifecycle (OBL)

Within a routed scope, inspect owning/non-owning pointers, `raw_ptr`, reference cycles, external
handles, `GarbageCollected`, `Member`, `WeakMember`, `Persistent`, `Trace`, DOM
or event mutation, script-capable bindings, navigation, BFCache, prerender,
freeze/resume, detach, or execution-context destruction.

In the thread ledger, produce a strong/weak/raw/Oilpan/handle ownership graph,
an applicable lifecycle-state table, reentrancy timelines, and `OBL-*`
rows citing the ownership/trace edge and teardown guard.

- Give each allocation or handle one release authority. Trace early return,
  replacement, move, reset, disconnect, partial initialization, and teardown.
- Treat `raw_ptr`, raw references, spans, and views as lifetime claims. Name the
  owner and prove it outlives every synchronous and asynchronous use.
- Draw cycles through ref-counted delegates, observers, repeating callbacks,
  receivers, and remotes. Require a cycle break on errors and shutdown too.
- For Oilpan, verify all strong edges participate in `Trace`; choose `Member`,
  `WeakMember`, or `Persistent` from intended reachability. Check mixin/base
  tracing, cross-heap edges, and pre-finalizers that touch GC objects.
- Do not rely on finalization for timely OS, GPU, Mojo, or network cleanup.
- Trace active, frozen, BFCache/prerendered, detached, context-destroyed,
  navigation-replaced, and destructing states as applicable. Verify suspend is
  distinct from terminal cleanup and restore/rebind cannot duplicate work.
- Bind document-scoped work to a fresh document/navigation identity so old
  callbacks cannot mutate a replacement document or restored entry.
- Treat event dispatch, custom-element reactions, promise resolution, binding
  conversion/callbacks, DOM mutation, focus changes, and observer notification
  as script-reentrant. Revalidate pointers, indices, lifecycle, and invariants.
- Require tests for detach/destroy during callback, navigation replacement,
  freeze/restore, recursion, and collection during reachability transitions.
