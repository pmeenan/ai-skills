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

## What this catalog has in common

Every entry is a Layer 3/4 leaf change (guards, caches on small objects,
pre-sizing) sized at well under 1% of a story, measured on headless
SwiftShader rendering, and qualified from a typed avoidable fraction. Under
the current policy none of them would reach implementation: the story floor
is twice the calibrated MDE (roughly 1% to 4% of a story), Layer 1/2 claims
need a redundancy packet, and rendering-backend entries are Pinpoint-first.
Read the catalog for the *failure mechanisms*, not as a list of forbidden
functions.

## Interpreting historical evidence

These entries describe particular revisions, workloads, hosts and attempted
mechanisms. Missing provenance or a noisy confidence interval lowers confidence
in a generalized lesson. Treat a rejection as a hypothesis to understand, not
a permanent prohibition on a function, subsystem, branch or optimization class.
A changed mechanism or relevant source/compiler/workload change can justify a
new bounded investigation, with the old evidence retained. Record current
campaign rejections in that campaign's ledger/artifacts; update this frozen
skill catalog only between campaigns.

---

## 3. Campaign `speedometer-september` Catalog & Machine-Readable Index

- **Machine-readable catalog:** [`discarded-candidates.json`](discarded-candidates.json) (`69` total entries: `26` earlier-campaign entries + `43` `speedometer-september` entries: `41` parked mechanisms, `1` rejected mechanism `#228`, `1` parked discovery `#388`).
- **Per-file counts:** `dom_core.md` (6 legacy + 4 `speedometer-september`), `html_forms.md` (3 legacy + 2 `speedometer-september`), `events.md` (2 legacy + 0 `speedometer-september`), `layout_geometry.md` (4 legacy + 16 `speedometer-september`), `cssom_style.md` (4 legacy + 10 `speedometer-september`), `canvas_graphics.md` (2 legacy + 8 `speedometer-september`), `svg.md` (2 legacy + 1 `speedometer-september`), `lifecycle_editing.md` (3 legacy + 2 `speedometer-september`).
- **Workflow integration:** Investigators must check this index, the matching subsystem file, and `discarded-candidates.json` before proposing or drafting a mechanism. `campaign.py decompose-draft` and `campaign.py decompose` emit a non-fatal `WARNING` when a `novel` mechanism key or its anchor function matches an entry in `discarded-candidates.json`.

| ID | Key | Kind / Status | Target Story | Subsystem File | Measured Result / Bound |
|:---|:---|:---|:---|:---|:---|
| `SP3-SEP-224` (`#224`) | `layout/inline-prepare-layout-cache` | `mechanism` / `parked` | `Editor-TipTap` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-225` (`#225`) | `fonts/shape-result-ink-bounds-cache` | `mechanism` / `parked` | `Editor-TipTap` | [`cssom_style.md`](cssom_style.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-226` (`#226`) | `layout/inline-layout-caching` | `mechanism` / `parked` | `Perf-Dashboard` | [`layout_geometry.md`](layout_geometry.md) | 32-block Perf-Dashboard oracle A/B: -0.57% [-0.89%, -0.25%] (fired 19/767 calls/rep, 2.5%) |
| `SP3-SEP-227` (`#227`) | `compositing/paint-artifact-incremental-layerization` | `mechanism` / `parked` | `TodoMVC-Svelte-Complex-DOM` | [`canvas_graphics.md`](canvas_graphics.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-228` (`#228`) | `layout/flex-item-min-max-cache` | `mechanism` / `rejected` | `NewsSite-Next` | [`layout_geometry.md`](layout_geometry.md) | Round 22 versioned counter: 0.0-4.6% repeated min/max time (NewsSite-Next 4.6% of 2.7% ... |
| `SP3-SEP-229` (`#229`) | `layout/reusing-text-shaper-item-cache` | `mechanism` / `parked` | `Editor-TipTap` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-230` (`#230`) | `layout/simplified-layout-caching` | `mechanism` / `parked` | `Perf-Dashboard` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-231` (`#231`) | `layout/oof-candidate-layout-cache` | `mechanism` / `parked` | `Perf-Dashboard` | [`layout_geometry.md`](layout_geometry.md) | Twin sizing (Perf-Dashboard): avoidable cycle share 8.785% [8.699%, 8.870%] (ceiling 8.... |
| `SP3-SEP-232` (`#232`) | `css/element-matched-rules-cache` | `mechanism` / `parked` | `TodoMVC-Lit-Complex-DOM` | [`cssom_style.md`](cssom_style.md) | Twin sizing (TodoMVC-Svelte-Complex-DOM): avoidable cycle share 4.327% [4.133%, 4.522%]... |
| `SP3-SEP-233` (`#233`) | `style/shadow-root-active-style-cache` | `mechanism` / `parked` | `TodoMVC-WebComponents` | [`cssom_style.md`](cssom_style.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-235` (`#235`) | `root/update-style-and-layout-for-node` | `mechanism` / `parked` | `Perf-Dashboard` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-236` (`#236`) | `parser/domparser-template-cache` | `mechanism` / `parked` | `TodoMVC-JavaScript-ES5` | [`html_forms.md`](html_forms.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-237` (`#237`) | `paint/pre-paint-tree-walk-cache` | `mechanism` / `parked` | `NewsSite-Nuxt` | [`canvas_graphics.md`](canvas_graphics.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-238` (`#238`) | `hittest/tree-scope-element-from-point-cache` | `mechanism` / `parked` | `NewsSite-Nuxt` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-239` (`#239`) | `canvas/flush-canvas-internal` | `mechanism` / `parked` | `Charts-chartjs` | [`canvas_graphics.md`](canvas_graphics.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-240` (`#240`) | `dom/import-node-template-cache` | `mechanism` / `parked` | `TodoMVC-WebComponents` | [`dom_core.md`](dom_core.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-241` (`#241`) | `resource/resource-request-memory-cache-hit` | `mechanism` / `parked` | `NewsSite-Next` | [`lifecycle_editing.md`](lifecycle_editing.md) | 32-block NewsSite-Next oracle A/B (Speedometer3Oracle241): +1.090% [+0.908%, +1.271%] v... |
| `SP3-SEP-242` (`#242`) | `layout/layout-result-discarded-before-paint` | `mechanism` / `parked` | `Editor-TipTap` | [`layout_geometry.md`](layout_geometry.md) | Paired oracle on Editor-TipTap: +0.15% [-0.15%, +0.45%] |
| `SP3-SEP-243` (`#243`) | `fonts/inline-shape-text-overlap` | `mechanism` / `parked` | `Editor-TipTap` | [`cssom_style.md`](cssom_style.md) | r75 v3 sound oracle on Editor-TipTap: -0.31% [-0.97%, +0.35%] (reused 4/258 calls/rep, ... |
| `SP3-SEP-244` (`#244`) | `layout/inline-min-max-text-overlap` | `mechanism` / `parked` | `Editor-TipTap` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-283` (`#283`) | `css/style-cascade-important-set-without-full-cascade-map` | `mechanism` / `parked` | `TodoMVC-Svelte-Complex-DOM` | [`cssom_style.md`](cssom_style.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-285` (`#285`) | `html/fastpath-parser-raw-attribute-span-cache` | `mechanism` / `parked` | `TodoMVC-jQuery` | [`html_forms.md`](html_forms.md) | 32-block TodoMVC-jQuery oracle A/B: -7.84% [-8.04%, -7.64%] slower (97% fired, 0/3.96M ... |
| `SP3-SEP-286` (`#286`) | `paint/non-layered-paint-properties-fast-path` | `mechanism` / `parked` | `NewsSite-Nuxt` | [`canvas_graphics.md`](canvas_graphics.md) | 32-block NewsSite-Nuxt oracle A/B: -0.26% [-0.58%, +0.07%] (26% fired, 1,061/4,035 call... |
| `SP3-SEP-288` (`#288`) | `layout/set-style-non-inherited-subgroup-and-image-fast-path` | `mechanism` / `parked` | `TodoMVC-Svelte-Complex-DOM` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-289` (`#289`) | `fonts/reusing-text-shaper-segmented-and-per-item-shape-cache` | `mechanism` / `parked` | `Editor-TipTap` | [`cssom_style.md`](cssom_style.md) | 32-block Editor-TipTap sound oracle A/B: -3.73% [-3.98%, -3.47%] (11.3% fired, 40,935/3... |
| `SP3-SEP-316` (`#316`) | `layout/lazy-line-break-ascii-alpha-run-fast-forward` | `mechanism` / `parked` | `Editor-TipTap` | [`layout_geometry.md`](layout_geometry.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-318` (`#318`) | `dom/selector-query-subtree-bloom-filter-tag-name-bits` | `mechanism` / `parked` | `NewsSite-Next` | [`dom_core.md`](dom_core.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-319` (`#319`) | `css/apply-animated-style-skip-base-data-and-transition-update` | `mechanism` / `parked` | `TodoMVC-Svelte-Complex-DOM` | [`cssom_style.md`](cssom_style.md) | Twin sizing on TodoMVC-Svelte-Complex-DOM: 1.63% [1.61%, 1.66%] avoidable cycle share v... |
| `SP3-SEP-320` (`#320`) | `fonts/harfbuzz-extract-shape-results-single-pass-and-uninitialized-run-glyphs` | `mechanism` / `parked` | `Editor-TipTap` | [`cssom_style.md`](cssom_style.md) | 32-block Editor-TipTap oracle A/B (Speedometer3Oracle320): +0.616% [+0.352%, +0.881%] v... |
| `SP3-SEP-321` (`#321`) | `canvas/retain-paint-op-buffer-capacity-across-canvas-size-reset` | `mechanism` / `parked` | `Charts-chartjs` | [`canvas_graphics.md`](canvas_graphics.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-322` (`#322`) | `layout/reuse-container-layout-when-children-unchanged` | `mechanism` / `parked` | `Editor-TipTap` | [`layout_geometry.md`](layout_geometry.md) | Twin sizing (Editor-TipTap): avoidable cycle share 20.817% [19.301%, 22.332%] (ceiling ... |
| `SP3-SEP-323` (`#323`) | `style/share-matched-rules-across-same-descriptor-elements` | `mechanism` / `parked` | `TodoMVC-Lit-Complex-DOM` | [`cssom_style.md`](cssom_style.md) | 32-block TodoMVC-Svelte-Complex-DOM sound oracle A/B: -0.28% [-0.89%, +0.32%] (18.3% fi... |
| `SP3-SEP-324` (`#324`) | `paint/precise-pre-paint-dirtiness-after-unchanged-layout` | `mechanism` / `parked` | `NewsSite-Nuxt` | [`canvas_graphics.md`](canvas_graphics.md) | 32-block NewsSite-Nuxt paired oracle A/B: +0.44% [+0.03%, +0.85%] vs 1.084% floor (303/... |
| `SP3-SEP-388` (`#388`) | `todomvc-react-redux-cc-layertreehost-requestmainframeupdate-bool` | `discovery` / `parked` | `TodoMVC-React-Redux` | [`lifecycle_editing.md`](lifecycle_editing.md) | r185 --vt 9 probe packet coverage: 2.05 aggregate (iteration 0 = 6.69, iterations 1+ = ... |
| `SP3-SEP-407` (`#407`) | `flex/reuse-flex-item-construction-when-unchanged` | `mechanism` / `parked` | `NewsSite-Nuxt` | [`layout_geometry.md`](layout_geometry.md) | r166 diagnostic counter on NewsSite-Next: all-clean reusable slice = 1.37% of Construct... |
| `SP3-SEP-408` (`#408`) | `layout/same-pass-relayout-under-changed-constraints` | `mechanism` / `parked` | `NewsSite-Next` | [`layout_geometry.md`](layout_geometry.md) | r166 diagnostic counter on NewsSite-Next: same-space second layout = 0.26% of BlockNode... |
| `SP3-SEP-409` (`#409`) | `layout/reuse-flex-container-layout-when-children-unchanged` | `mechanism` / `parked` | `NewsSite-Nuxt` | [`layout_geometry.md`](layout_geometry.md) | r167 no-force provenance run on NewsSite-Next: 0 applicable calls out of 2,533,400 Bloc... |
| `SP3-SEP-411` (`#411`) | `css/recalc-style-identical-output-residual` | `mechanism` / `parked` | `TodoMVC-Lit-Complex-DOM` | [`cssom_style.md`](cssom_style.md) | 32-block full-suite oracle A/B (Speedometer3Oracle411): -1.5178% [-1.6008%, -1.4348%] v... |
| `SP3-SEP-412` (`#412`) | `bindings/to-blink-atomic-string` | `mechanism` / `parked` | `Charts-observable-plot` | [`dom_core.md`](dom_core.md) | 32-block Charts-observable-plot oracle A/B (Speedometer3Oracle412): -0.1269% [-0.3100%,... |
| `SP3-SEP-413` (`#413`) | `layout/layout-svg-text` | `mechanism` / `parked` | `Charts-observable-plot` | [`svg.md`](svg.md) | Unmeasured (parked prior to oracle/A/B measurement) |
| `SP3-SEP-414` (`#414`) | `paint/recalc-ink-overflow-unchanged` | `mechanism` / `parked` | `Editor-TipTap` | [`canvas_graphics.md`](canvas_graphics.md) | 32-block Editor-TipTap oracle A/B (Speedometer3Oracle414): -0.9906% [-1.1795%, -0.8027%... |
| `SP3-SEP-415` (`#415`) | `dom/custom-element-reaction-queue-invoke` | `mechanism` / `parked` | `TodoMVC-WebComponents` | [`dom_core.md`](dom_core.md) | 32-block full-suite oracle A/B (Speedometer3Oracle415): +0.2923% [+0.1683%, +0.4163%] s... |
| `SP3-SEP-416` (`#416`) | `paint/paint-layer-descendant-flags-unchanged` | `mechanism` / `parked` | `TodoMVC-WebComponents` | [`canvas_graphics.md`](canvas_graphics.md) | 32-block full-suite oracle A/B (Speedometer3Oracle416): -0.6486% [-0.7414%, -0.5557%] v... |
