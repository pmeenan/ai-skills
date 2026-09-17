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
freeze/resume, detach, execution-context destruction, or V8 heap/GC handles
(`HandleScope`, `DirectHandle`, `Tagged<T>`, write barriers, and V8 Sandbox
pointer tables).

In the thread ledger, produce a strong/weak/raw/Oilpan/V8-handle ownership graph,
an applicable lifecycle-state table, reentrancy/GC-safepoint timelines, and `OBL-*`
rows citing the ownership/trace edge and teardown/safepoint guard.

- Give each allocation or handle one release authority. Trace early return,
  replacement, move, reset, disconnect, partial initialization, and teardown.
- Treat `raw_ptr`, raw references, spans, and views as lifetime claims. Name the
  owner and prove it outlives every synchronous and asynchronous use.
- Draw cycles through ref-counted delegates, observers, repeating callbacks,
  receivers, and remotes. Require a cycle break on errors and shutdown too.
- For Oilpan, verify all strong edges participate in `Trace`; choose `Member`,
  `WeakMember`, or `Persistent` from intended reachability. Check mixin/base
  tracing, cross-heap edges, and pre-finalizers that touch GC objects.
- For V8 Heap & GC (`v8/` and Blink-V8 bindings):
  - Never hold raw `Tagged<T>` / `HeapObject` pointers or unrooted object slots
    across a GC safepoint or allocating helper; wrap in `Handle` / `DirectHandle`
    before any call that can allocate or trigger collection.
  - Verify `HandleScope` boundaries: prevent handle accumulation inside loops
    (add an inner `HandleScope`) and require `CloseAndEscape` when returning a
    handle across a local scope.
  - Validate write barriers (`WriteBarrier`, `CONDITIONAL_WRITE_BARRIER`) on
    heap-to-heap stores; treat `SKIP_WRITE_BARRIER` or `DisallowGarbageCollection`
    as claims that must be proven against every reachable callee.
  - For V8 Sandbox (`ExternalPointerTag`, `TrustedPointerTable`,
    `CppHeapPointerTable`), verify type-specific pointer tags and enforce strict
    in-sandbox bounds/offset sanitization before dereferencing external memory.
- Do not rely on finalization for timely OS, GPU, Mojo, or network cleanup.
- Trace active, frozen, BFCache/prerendered, detached, context-destroyed,
  navigation-replaced, and destructing states as applicable. Verify suspend is
  distinct from terminal cleanup and restore/rebind cannot duplicate work.
- Bind document-scoped work to a fresh document/navigation identity so old
  callbacks cannot mutate a replacement document or restored entry.
- For `WebContentsObserver` and `NavigationThrottle` hooks (`DidStartNavigation`,
  `ReadyToCommitNavigation`, `DidFinishNavigation`, `RenderFrameDeleted`):
  verify MPArch frame-tree scope—require `IsInPrimaryMainFrame()` (or
  `GetLifecycleState() == kActive`) before mutating `WebContents`/tab-level
  state so subframe, fenced-frame, prerender, or BFCache navigations cannot
  corrupt primary page state, and require `HasCommitted()` in
  `DidFinishNavigation` before reading committed navigation state.
- For `BrowserContextKeyedServiceFactory` / `ProfileKeyedServiceFactory`
  implementations: verify that every other `KeyedService` accessed by the
  service (especially during `Shutdown()` or destructor execution) has a
  matching `DependsOn(OtherFactory::GetInstance())` call in the factory
  constructor so teardown order is guaranteed.
- Treat event dispatch, custom-element reactions, promise resolution, binding
  conversion/callbacks, DOM mutation, focus changes, and observer notification
  as script-reentrant. Revalidate pointers, indices, lifecycle, and invariants.
- Require tests for detach/destroy during callback, navigation replacement,
  freeze/restore, recursion, and collection during reachability transitions.
