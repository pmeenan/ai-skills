# Discarded Candidates: 2D Canvas & Graphics Pipeline

Subsystem: `third_party/blink/renderer/modules/canvas/`, `platform/graphics/`, `cc/paint/`

---

## CANV-01: `Canvas2DRecorderContext::DrawPathInternal` Full-Circle Arc to `drawOval`
- **Concept:** When `arc(x, y, r, 0, 2*PI)` is called, emit a `drawOval` paint op instead of constructing a full SkPath circular contour.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `f962a0a15a3d3`).
- **Empirical Result:** Directly regressed target story `Charts-chartjs` **`-2.50% [-3.28%, -1.71%]`**.
- **Causal Failure Mechanism:** In Skia's GPU playback pipeline, `drawOval` and `drawArc`/`drawPath` are serialized as different `PaintOp` types. Chart.js draws hundreds of circular markers in batch; converting full circles to ovals broke Skia's internal paint op batching, causing more draw calls and GPU state flushes.
- **Durable Invariant:** Do not convert SkPath arcs to Skia ovals/rectangles without verifying Skia GPU op-merging and batching behavior; op-type diversity prevents batch draw call collapsing.

---

## CANV-02: `Canvas2DRecorderContext::setTransform` CTM Redundancy Check
- **Concept:** Check if the new 6-element affine transform matrix equals the current transform in `Canvas2DRecorderContext::setTransform` and return early.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `2aff51c8caf23`).
- **Empirical Result:** Stat-sig regression on `TodoMVC-WebComponents-Complex` (`-2.14%`).
- **Causal Failure Mechanism:** Redundant `setTransform` calls were exceedingly rare in the benchmark. The 6-float comparison (`AffineTransform` equality) executed on every valid transform change, adding pure CPU overhead without pruning work.
- **Durable Invariant:** Do not add matrix redundancy checks to Canvas 2D transform setters unless redundant calls exceed 60% of total invocations in profile traces.

---

# Campaign `speedometer-september` Discarded & Parked Candidates

## SP3-SEP-227 (#227): `compositing/paint-artifact-incremental-layerization`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::PaintArtifactCompositor::Update(blink::PaintArtifact const&, blink::PaintArtifactCompositor::ViewportProperties const&, blink::BasicHeapVector<(blink::internal::HeapCollectionType)1, cppgc::internal::BasicMember<blink::TransformPaintPropertyNode const, cppgc::internal::StrongMemberTag, cppgc::internal::DijkstraWriteBarrierPolicy, cppgc::internal::DisabledCheckingPolicy, cppgc::internal::CompressedPointer>, 32u> const&, blink::Vector<std::__Cr::unique_ptr<cc::ViewTransitionRequest, std::__Cr::default_delete<cc::ViewTransitionRequest> >, 0u, blink::PartitionAllocator>)`, `TodoMVC-Vue/cc::LayerTreeHost::RequestMainFrameUpdate(bool)`, `TodoMVC-WebComponents/cc::LayerTreeHost::RequestMainFrameUpdate(bool)`
- **Stories:** `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-Vue`, `TodoMVC-WebComponents`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `TodoMVC-Angular-Complex-DOM`, `TodoMVC-React-Complex-DOM` (+9 more)
- **Upper Bound:** target-story share 5.10% (TodoMVC-Svelte-Complex-DOM), avoidable fraction 0.5333, suite impact 0.3088%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "Sizing (ROUND-197) epoch check: candidate evidence is out of epoch (sp3-baseline-1 / sp3-post-158-r3). On the current profile sp3-tot-frontier-1, TodoMVC-Svelte-Complex-DOM PendingLayer::Matches share 0.7803% x 58.9% = 0.4596%, below the 1.3910% story floor (operator report ROUND-197.227.md sha256 503db2391c73)."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below the 1.3910% TodoMVC-Svelte-Complex-DOM story floor on Epoch 1 profile sp3-tot-frontier-1 (0.7803% x 58.9% = 0.4596%); revisit if PendingLayer::Matches share or repeat fraction rises.
- **Design Docs:** `outbox/ROUND-197.227.md`
- **Evidence Pointers:** `evidence/probe_r185_todomvc_svelte_complex_dom__compositing_layerizer_layerize_group.json`, `evidence/probe_rework_svelte_pac_layers.json`, `evidence/probe_rework_preact_pac_layers.json`, `evidence/probe_rework_lit_pac_chunks.json`

---

## SP3-SEP-237 (#237): `paint/pre-paint-tree-walk-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::PrePaintTreeWalk::Walk(blink::LocalFrameView&, blink::PrePaintTreeWalk::PrePaintTreeWalkContext const&)`
- **Stories:** `NewsSite-Nuxt`, `NewsSite-Next`, `TodoMVC-Svelte-Complex-DOM`, `Editor-CodeMirror`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-WebComponents`, `TodoMVC-Vue` (+12 more)
- **Upper Bound:** target-story share 7.12% (NewsSite-Nuxt), avoidable fraction 0.2020, local story impact 1.43%, suite impact 0.1553%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "re-parked by the host, round 57: parked in round 46 as the harness-driven redundant-trigger form of the pre-paint idea; #324 (precise pre-paint dirtiness, unchanged-output) is its successor; the #137 r3 revision reopened it automatically through a covered-by wrapper"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-18` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Harness-driven redundant-trigger artifact (superseded by #324 unchanged-output pre-paint hypothesis); do not revisit unless real-world non-harness triggers are demonstrated.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probes-round46.patch`

---

## SP3-SEP-239 (#239): `canvas/flush-canvas-internal`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::BaseRenderingContext2D::FlushCanvasInternal(blink::Canvas2DResourceProvider*, blink::Canvas2DBitmapProvider*, blink::FlushReason)`
- **Stories:** `Charts-chartjs`, `Perf-Dashboard`
- **Upper Bound:** target-story share 4.76% (Charts-chartjs), avoidable fraction 0.2719, local story impact 1.29%, suite impact 0.0700%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "User decision 2026-10-12: parked as not worth the effort; decomposition-gate suite-impact upper bound 0.07% is below the 0.20% cutoff. Unmeasured; revisit only if the bound is revised upward."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-12` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below a 0.20% suite-impact cutoff (0.0700%); revisit if the bound rises on a newer profile or workload.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probe_r185_charts_chartjs__canvas_flush_canvas_internal.json`

---

## SP3-SEP-286 (#286): `paint/non-layered-paint-properties-fast-path`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::PaintPropertyTreeBuilder::UpdateForSelf()`
- **Stories:** `NewsSite-Nuxt`, `NewsSite-Next`, `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-WebComponents`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-Vue`, `Charts-observable-plot` (+12 more)
- **Upper Bound:** target-story share 3.33% (NewsSite-Nuxt), avoidable fraction 0.4500, local story impact 1.50%, suite impact 0.5231%
- **Measured Result:** 32-block NewsSite-Nuxt oracle A/B: -0.26% [-0.58%, +0.07%] (26% fired, 1,061/4,035 calls/rep)
- **Ledger Reason (verbatim):** "round 72: oracle (skip paint-property update for non-layered objects without properties whose location, size and Style pointer are unchanged) fired on 26% of reached calls (1,061 of 4,035 per repetition) and bounds NewsSite-Nuxt at -0.26% [-0.58, +0.07]: the skipped work is trivial. Same conclusion as #324."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-22` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Oracle measured -0.26% [-0.58%, +0.07%] on NewsSite-Nuxt despite firing on 26% of calls because PaintPropertyTreeBuilder::UpdateForSelf for non-layered objects is trivial; do not revisit.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch2/5_286_nuxt_32`, `evidence/cost_eff_258.json`

---

## SP3-SEP-321 (#321): `canvas/retain-paint-op-buffer-capacity-across-canvas-size-reset`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `cc::PaintOpBuffer::AllocatePaintOpSlowPath(unsigned short)`
- **Stories:** `Charts-chartjs`, `Charts-observable-plot`, `Perf-Dashboard`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-WebComponents`, `TodoMVC-Vue`, `TodoMVC-Svelte-Complex-DOM` (+12 more)
- **Upper Bound:** target-story share 1.65% (Charts-chartjs), avoidable fraction 0.8500, local story impact 1.37%, suite impact 0.0806%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "User decision 2026-10-12: parked as not worth the effort; decomposition-gate suite-impact upper bound 0.0806% is below the 0.20% cutoff. Unmeasured; revisit only if the bound is revised upward."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-12` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below a 0.20% suite-impact cutoff (0.0806%); revisit if the bound rises on a newer profile or workload.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/cost_eff_314.json`

---

## SP3-SEP-324 (#324): `paint/precise-pre-paint-dirtiness-after-unchanged-layout`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::PrePaintTreeWalk::Walk(blink::LayoutObject const&, blink::PrePaintTreeWalk::PrePaintTreeWalkContext const&, blink::PrePaintInfo*)`, `blink::PrePaintTreeWalk::Walk(blink::LocalFrameView&, blink::PrePaintTreeWalk::PrePaintTreeWalkContext const&)`
- **Stories:** `NewsSite-Nuxt`, `NewsSite-Next`, `Editor-CodeMirror`, `Editor-TipTap`, `TodoMVC-WebComponents`, `TodoMVC-Vue`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-Angular-Complex-DOM` (+9 more)
- **Upper Bound:** target-story share 7.21% (NewsSite-Nuxt), avoidable fraction 0.6230, local story impact 4.47%, suite impact 0.6939%
- **Measured Result:** 32-block NewsSite-Nuxt paired oracle A/B: +0.44% [+0.03%, +0.85%] vs 1.084% floor (303/975 fired out of 7,570 walked objects/rep)
- **Ledger Reason (verbatim):** "round 61b: the paired oracle (skip WalkInternal for a flagged object whose previous visit at the same key changed nothing; key = new paint offset, size, parent transform/clip, Style pointer, visual overflow) bounds the story gain at +0.44% [+0.03, +0.85] on NewsSite-Nuxt against an expected 4.17% and a story floor of 1.084%. Reach/fire counters: 975 reached and 303 fired per iteration out of 7,570 walked objects; the counter's 44% post-hoc unchanged output is not predictable from the object's own flags. evidence/oracle_batch1b/6_324_nuxt_32/."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-20` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Paired oracle on NewsSite-Nuxt measured +0.44% [+0.03%, +0.85%] vs the 1.084% story floor because post-hoc unchanged pre-paint output (44%) is not predictable from the object's own pre-call flags; revisit only if a cheaper upstream layout/paint dirtiness invariant is found.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch1/6_324_nuxt_32`, `evidence/probe_r184_newssite_nuxt__paint_pre_paint_object_output_unchanged.json`, `evidence/probe_r184_editor_codemirror__paint_pre_paint_object_output_unchanged.json`, `evidence/probe_r184_newssite_next__paint_pre_paint_object_output_unchanged.json`, `evidence/probes-round184-tot.patch`, `measurements/tot-profile/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-lens.json`

---

## SP3-SEP-414 (#414): `paint/recalc-ink-overflow-unchanged`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::PhysicalBoxFragment::RecalcInkOverflow()`
- **Stories:** `Editor-TipTap`, `NewsSite-Nuxt`, `NewsSite-Next`, `TodoMVC-Vue`, `TodoMVC-WebComponents`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `Editor-CodeMirror` (+9 more)
- **Upper Bound:** target-story share 4.23% (Editor-TipTap), avoidable fraction 0.6257, local story impact 2.61%, suite impact 0.5780%
- **Measured Result:** 32-block Editor-TipTap oracle A/B (Speedometer3Oracle414): -0.9906% [-1.1795%, -0.8027%]; twin 3.1206% [3.0846%, 3.1573%] dominated by first-time kNotSet fragments (487.81/530.53 calls/rep)
- **Ledger Reason (verbatim):** "Sizing design round (ROUND-199, outbox/DESIGN-414-PREDICTOR.md sha256 3502003a86a6) after the ROUND-197 oracle measured -0.99% on Editor-TipTap. The twin's 3.12% post-hoc avoidable share was mostly an artifact: 487.81 of 530.53 applicable calls/rep are first-time recalcs on freshly built fragments (InkOverflowType kNotSet), whose stored rect defaults to LocalRect() (ink_overflow.cc:208-216), and these cannot be skipped soundly (painters read every FragmentItem's ink overflow). Sound predictors (dirty bits, fragment identity plus generation, layout-cache hits) reach only the 42.72 calls/rep already computed, where FragmentItem::RecalcInkOverflow already short-circuits text ink bounds (fragment_item.cc:1043): estimated +0.08% to +0.18%, below the 1.0% story floor."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** Twin's 3.12% post-hoc share was dominated by first-time recalcs on freshly built fragments (InkOverflowType::kNotSet, 487.81/530.53 calls/rep) whose default rect equals LocalRect() and cannot be skipped soundly; sound predictors reach <= 42.72 calls/rep (+0.08% to +0.18% < 1.0% floor). Revisit only if fragment construction preserves prior InkOverflow across inline rebuilds.
- **Design Docs:** `outbox/SIZING-414-412-DESIGN.md`, `outbox/DESIGN-414-PREDICTOR.md`
- **Evidence Pointers:** `evidence/oracle_414/oracle-414.patch`, `evidence/oracle_414/ab-tiptap/ab_results_manifest.json`, `evidence/twin_r197/sizing-414-tiptap.json`, `evidence/cost_334_r3.json`, `evidence/probe_r185_editor_tiptap__paint_recalc_ink_overflow_unchanged.json`, `evidence/cost_344_r74.json`, `evidence/probe_r185_newssite_nuxt__paint_recalc_ink_overflow_unchanged.json`, `evidence/probes-round185-tot.patch`

---

## SP3-SEP-416 (#416): `paint/paint-layer-descendant-flags-unchanged`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::PaintLayer::UpdateDescendantDependentFlags()`
- **Stories:** `TodoMVC-WebComponents`, `TodoMVC-Vue`, `NewsSite-Nuxt`, `NewsSite-Next`, `Editor-TipTap`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `TodoMVC-React-Complex-DOM`, `TodoMVC-Lit-Complex-DOM` (+9 more)
- **Upper Bound:** target-story share 1.65% (TodoMVC-WebComponents), avoidable fraction 0.4857, local story impact 0.76%, suite impact 0.5685%
- **Measured Result:** 32-block full-suite oracle A/B (Speedometer3Oracle416): -0.6486% [-0.7414%, -0.5557%] vs 0.4031% suite floor (0 audit mismatches)
- **Ledger Reason (verbatim):** "User decision 2026-10-13 after sizing (ROUND-197): 32-block full-suite paired oracle (Speedometer3Oracle416, disjoint from #414, 0 audit mismatches) measured -0.6486% [-0.7414%, -0.5557%] vs the 0.4031% suite floor."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** 32-block full-suite oracle (Speedometer3Oracle416) measured -0.6486% [-0.7414%, -0.5557%] vs the 0.4031% suite floor; do not revisit.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_416/oracle-416.patch`, `evidence/oracle_416/ab-suite/ab_results_manifest.json`, `evidence/probes-round185-tot.patch`, `evidence/cost_397_r140.json`, `measurements/tot-profile/analysis/stories/TodoMVC-Vue/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/TodoMVC-Vue/candidate_frontier.json`, `measurements/tot-lens.json`, `measurements/tot-profile/analysis/stories/TodoMVC-WebComponents/candidate_frontier.json`
