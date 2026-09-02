# Discarded Candidates: Frame Lifecycle, Editing & Navigation

Subsystem: `third_party/blink/renderer/core/frame/`, `core/editing/`, `core/loader/`

---

## FRAME-01: `LocalFrameView` Childless Traversal Bypass
- **Concept:** In `LocalFrameView::ForAllNonThrottledLocalFrameViews`, skip recursion if the frame has no child frames.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `7ca3a7b231c25`).
- **Empirical Result:** Stat-sig regressions on `TodoMVC-WebComponents` (`-4.97%`) and `TodoMVC-Lit` (`-3.26%`).
- **Causal Failure Mechanism:** Frame traversal is responsible for triggering lifecycle callbacks, intersection observers, and resize observations in precise document order. Bypassing traversal disrupted callback ordering in multi-component custom element trees.
- **Durable Invariant:** Do not bypass or reorder frame iteration in `LocalFrameView`; frame lifecycle ordering is strictly required for web observer notifications.

---

## EDIT-01: `DomSelection::rangeCount` Layout Flush Bypass & Lazy Focus
- **Concept:** In `DomSelection::rangeCount`, return 0 early if selection has no ranges without forcing a synchronous layout update.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `2ed50198cef96`).
- **Empirical Result:** Stat-sig regressions on `TodoMVC-React` (`-2.36%`), `TodoMVC-Svelte-Complex-DOM` (`-2.89%`), `TodoMVC-Webpack-Complex` (`-0.94%`).
- **Causal Failure Mechanism:** Skipping the layout update left the selection controller with un-updated layout positions. When subsequent DOM operations or events queried selection bounds, the engine was forced into delayed, high-latency synchronous layout recalculations.
- **Durable Invariant:** Selection range queries must ensure clean layout; delaying layout flushes in selection queries causes cascading layout thrashing during event dispatch.

---

## NAV-01: `HistoryItem` Lazy Navigation API UUIDs
- **Concept:** Defer generating 128-bit random UUID strings for `HistoryItem` instances until queried by JavaScript via the Navigation API.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `8a82f82fdda9d`).
- **Empirical Result:** Flat delta (`-0.12%`); zero stat-sig wins across all 32 stories.
- **Causal Failure Mechanism:** While Navigation API history items generate UUIDs on creation, Speedometer 3 stories execute inside pre-loaded single page applications where full navigation is not invoked during timed test runs.
- **Durable Invariant:** Navigation API optimizations have zero impact on standard SPA benchmarks like Speedometer; verify that navigation lifecycles actually execute in the target benchmark before sizing.
