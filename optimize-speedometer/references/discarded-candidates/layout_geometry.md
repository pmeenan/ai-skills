# Discarded Candidates: Layout Engine & Geometry

Subsystem: `third_party/blink/renderer/core/layout/`, `core/dom/`

---

## LAY-01: `Element::RebuildLayoutTree` Pseudo-Element Check
- **Concept:** In `Element::RebuildLayoutTree`, skip checking for `::before` and `::after` pseudo-elements if the element's style does not specify pseudo-element styles.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `0972933e1e8c1`).
- **Empirical Result:** Stat-sig regressions on `TodoMVC-JavaScript-ES6-Webpack` (`-2.24%`) and `TodoMVC-Vue-Complex-DOM` (`-1.53%`).
- **Causal Failure Mechanism:** Pseudo-element layout attachment is tightly coupled with anonymous box generation. Skipping the pseudo-element rebuild check left child layout objects in a dirty state, triggering synchronous layout recalculation flushes during subsequent frames.
- **Durable Invariant:** Do not skip pseudo-element attachment checks during `RebuildLayoutTree`; style-based dirty bits do not capture inherited anonymous box constraints.

---

## LAY-02: `Element::getBoundingClientRect` Viewport Caching
- **Concept:** Cache the computed `DOMRect` on `ElementRareData` and invalidate it only on scroll or layout invalidations.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Net negative (`-0.08%`).
- **Causal Failure Mechanism:** Cache invalidation overhead on every DOM mutation, transform change, and ancestor scroll exceeded the cost of recalculating the bounding rect. Cache hit rate in interactive benchmarks was <15%.
- **Durable Invariant:** Never introduce memoization caches for layout geometry coordinates without hardware-backed or layout-tree-versioned cache validation.

---

## LAY-03: `Element::GetBoundingClientRect` Single-Box Direct Quad Calculation
- **Concept:** For elements whose `LayoutObject` is a simple `LayoutBox`, compute client quad coordinates directly from `AbsoluteBoundingBoxRect()` without calling `LocalFrameView::UpdateLayout()`.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `7a42f04e3b2d5`).
- **Empirical Result:** Regressed `NewsSite-Next` (`-1.02%`) and `NewsSite-Nuxt` (`-0.44%`), suite delta `-0.22%`.
- **Causal Failure Mechanism:** Skipping the lifecycle layout update caused geometry queries to read stale coordinates whenever preceding script mutated DOM state. When layout updates were later forced by subsequent reads, the engine suffered pipeline stalls.
- **Durable Invariant:** Geometry APIs (`getBoundingClientRect`, `offsetTop`, `offsetWidth`) must guarantee clean layout state; never bypass lifecycle updates to calculate geometry.

---

## LAY-04: `LayoutBox` Non-Form Controls & Childless Containment
- **Concept:** In `LayoutBox::DefaultIntrinsicContentInlineSize`, early-return `kIndefiniteSize` when `!element.IsFormControlElement()`. In `Node::contains`, fast-path `!hasChildren()`.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `5bd0c31335e1c`).
- **Empirical Result:** Net suite drag of `-0.21% [-0.59%, +0.17%]`. Zero stat-sig wins.
- **Causal Failure Mechanism:** `DefaultIntrinsicContentInlineSize` is already only called on boxes requiring intrinsic sizing. Adding polymorphic type checks (`IsFormControlElement`) and containment branches added evaluation cost across millions of box evaluations during layout passes without skipping measurable work.
- **Durable Invariant:** Do not add type-filter branches inside inner layout traversal algorithms unless profiling proves the non-target types dominate >50% of the inclusive time.
