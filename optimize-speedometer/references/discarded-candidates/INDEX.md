# Speedometer 3: Discarded Candidates Catalog Index

To minimize agent context usage and remain durable across Chromium refactors, rejected optimization candidates are organized by subsystem into dedicated files.

**Agent Guidance:** Consult this index to identify the relevant subsystem file. Only read the specific subsystem file matching your target opportunity.

---

## 1. Subsystem Catalog Routing

| Subsystem File | Area & Core Types | Discarded Candidate Identifiers | Primary Failure Reasons |
|:---|:---|:---|:---|
| [`dom_core.md`](dom_core.md) | `ContainerNode`, `Element`, `SelectorQuery`, `HTMLCollection` | `DOM-01` (`setInnerHTML` pre-alloc)<br>`DOM-02` (collection index cache)<br>`DOM-03` (`setAttribute` check)<br>`DOM-04` (leaf node remove check)<br>`DOM-05` (batch unlink pointers)<br>`DOM-06` (childless selector query) | Redundant with JS framework VDOM; internal Blink caches already exist; pointer unlinking breaks unified layout tree detachment. |
| [`html_forms.md`](html_forms.md) | `HTMLInputElement`, `HTMLFastPathParser`, `DOMParser` | `HTML-01` (`setValue` check)<br>`HTML-02` (attributes empty check)<br>`HTML-03` (`DOMParser` fast-path) | Frameworks already skip identical writes; parser edge cases cause fallback to full parser; low call volume. |
| [`events.md`](events.md) | `EventTarget`, `EventPath`, `EventDispatcher` | `EVT-01` (single listener bypass)<br>`EVT-02` (non-bubbling `EventPath`) | Eclipsed by V8 script transitions; non-bubbling events still require capture phase and shadow retargeting. |
| [`layout_geometry.md`](layout_geometry.md) | `LayoutBox`, `LayoutObject`, `getBoundingClientRect` | `LAY-01` (pseudo-element check)<br>`LAY-02` (viewport rect cache)<br>`LAY-03` (direct single-box quad)<br>`LAY-04` (non-form intrinsic size) | Skipping layout updates forces delayed synchronous layout thrashing; invalidation tracking exceeds recalculation cost. |
| [`cssom_style.md`](cssom_style.md) | `Seeker<T>`, `EasySelectorChecker`, `ComputedStyle`, `NGShapeCache` | `CSS-01` (computed style strings)<br>`CSS-02` (subselector bypass)<br>`CSS-03` (shape cache expansion)<br>`CSS-04` (empty rule intervals) | ThinLTO branch mispredictions in tight inlined loops; subtle pseudo-class/shadow DOM bugs; memory pressure on short tokens. |
| [`canvas_graphics.md`](canvas_graphics.md) | `Canvas2DRecorderContext`, `SkCanvas`, `PaintOp` | `CANV-01` (full-circle arc to oval)<br>`CANV-02` (`setTransform` CTM check) | Skia GPU draw call batch fragmentation (converting arcs to ovals breaks batch collapsing); matrix compare overhead. |
| [`svg.md`](svg.md) | `SVGElement`, `SVGPath`, `CSSPathCache` | `SVG-01` (SVG tag switch)<br>`SVG-02` (1-entry MRU path cache) | Branch target buffer pollution; dynamic chart data points lack temporal string locality. |
| [`lifecycle_editing.md`](lifecycle_editing.md) | `LocalFrameView`, `DomSelection`, `HistoryItem` | `FRAME-01` (frame traversal bypass)<br>`EDIT-01` (selection lazy layout)<br>`NAV-01` (Navigation API lazy UUID) | Frame lifecycle ordering required for web observers; delayed selection layout stalls pipelines; SPAs perform zero navigations. |

---

## 2. Universal Cross-Cutting Anti-Patterns

Before investigating any new candidate, verify it does not fall into these 5 proven systemic anti-patterns:

1. **ThinLTO / PGO2 Micro-Branch Traps:**
   Never add trivial outer guards (`if (empty()) return;`, `if (size() == 1) ...`) to hot, tightly inlined template/search loops (e.g. `Seeker::Seek`, `EventTarget::FireEventListeners`). LLVM PGO2 already optimizes branch layout; redundant outer branches degrade Branch Target Buffer (BTB) prediction and icache locality.
2. **Framework-Level Deduplication Redundancy:**
   Never add C++ equality guards to DOM property setters (`input.value`, `element.setAttribute`) under the assumption that script passes identical values. Modern UI frameworks (React, Vue, Preact, Lit) already deduplicate in JS; the C++ guard simply penalizes genuine mutations with unnecessary string comparison overhead.
3. **Geometry Shortcut & Delayed Layout Hazard:**
   Never bypass `LocalFrameView::UpdateLayout()` in geometry queries (`getBoundingClientRect`, `offsetTop`). Delaying clean layout creates pipeline bubbles and forces high-latency synchronous layout thrashing during subsequent script execution.
4. **Skia GPU Batch Call Fragmentation:**
   Never change the emitted `PaintOp` type (e.g. converting SkPath arcs to `drawOval`) without verifying Skia GPU op-merging. Converting homogenous op streams to heterogeneous types breaks Skia's internal batch draw call collapsing.
5. **Collection / Geometry Memoization Invalidation Overhead:**
   Never add ad-hoc caches for geometry or parsed strings without measuring invalidation frequency. In interactive DOM benchmarks, invalidation tracking cost almost always exceeds the savings of rare cache hits.
