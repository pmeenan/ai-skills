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

---

# Campaign `speedometer-september` Discarded & Parked Candidates

## SP3-SEP-224 (#224): `layout/inline-prepare-layout-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::InlineNode::PrepareLayout(blink::InlineNodeData*) const`
- **Stories:** `Editor-TipTap`
- **Upper Bound:** target-story share 8.16% (Editor-TipTap), avoidable fraction 0.4952, local story impact 2.91%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "withdrawn for rework per outbox/inspection-2026-09-07.md: fraction read from a probe whose key or applicable predicate does not state the hypothesis, existing Chromium reuse not examined; re-list as known if the reworked count still clears the floor"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-07` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Revisit if a reworked probe with a key and applicable predicate that state the hypothesis and examine existing InlineNode::PrepareLayout reuse clears the story floor.
- **Design Docs:** `outbox/inspection-2026-09-07.md`
- **Evidence Pointers:** `evidence/probe_rework_tiptap_inline_prepare.json`

---

## SP3-SEP-226 (#226): `layout/inline-layout-caching`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::InlineLayoutAlgorithm::Layout()`
- **Stories:** `Perf-Dashboard`, `NewsSite-Next`, `TodoMVC-Angular-Complex-DOM`, `Editor-TipTap`, `Editor-CodeMirror`, `React-Stockcharts-SVG`, `TodoMVC-WebComponents`, `NewsSite-Nuxt` (+3 more)
- **Upper Bound:** target-story share 17.65% (Perf-Dashboard), avoidable fraction 0.9481, local story impact 16.70%, suite impact 1.2340%
- **Measured Result:** 32-block Perf-Dashboard oracle A/B: -0.57% [-0.89%, -0.25%] (fired 19/767 calls/rep, 2.5%)
- **Ledger Reason (verbatim):** "round 72: the redesigned oracle (skip at BlockNode::Layout after PrepareLayoutIfNeeded, complete key with text hash, items count, Style pointer, inline size, percentage resolution, BFC offsets, exclusion space; layout slot only) ran 32 blocks on Perf-Dashboard without a crash and bounds the story gain at -0.57% [-0.89, -0.25]; it reached 767 and fired 19 calls per repetition (2.5%). The round-61b crash was symbolized (CHECK in BoxFragmentPainter::PaintInlineItems: stale fragment items when an inline result is reused without PrepareLayout; evidence/oracle_batch2/0_226_diag_sym1_perfdash_1/gdb_bt.log). Under a sound key the redundancy the counter saw (79% repeats of (block, text, constraints)) is not reusable: the misses are most likely replaced ComputedStyle pointers and exclusion-space differences. Four builds, three runs."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-22` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Revisit only if inline layout caching can avoid ComputedStyle pointer churn and exclusion-space misses without stale PaintInlineItems fragment state (32-block oracle measured -0.57% [-0.89%, -0.25%] with 2.5% fire rate).
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch1/3_226_perfdash_32`, `evidence/oracle_batch2/1_226_perfdash_32`, `evidence/oracle_batch2/0_226_diag_sym1_perfdash_1`, `evidence/probe_rework_perfdash_inline_layout.json`, `measurements/tot-profile/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-profile-2/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-lens.json`, `evidence/probe_r155_newssite_next__layout_inline_layout_algorithm.json`

---

## SP3-SEP-228 (#228): `layout/flex-item-min-max-cache`
- **Kind / Status:** `mechanism` / `rejected`
- **Functions / Anchors:** `blink::FlexLayoutAlgorithm::ConstructAndAppendFlexItems(blink::FlexLayoutAlgorithm::Phase, blink::BasicHeapVector<(blink::internal::HeapCollectionType)1, cppgc::internal::BasicMember<blink::LayoutBox, cppgc::internal::StrongMemberTag, cppgc::internal::DijkstraWriteBarrierPolicy, cppgc::internal::DisabledCheckingPolicy, cppgc::internal::CompressedPointer>, 0u>*)`
- **Stories:** `NewsSite-Next`, `Editor-TipTap`, `Editor-CodeMirror`, `NewsSite-Nuxt`
- **Upper Bound:** target-story share 22.48% (NewsSite-Next), avoidable fraction 0.4166, local story impact 9.37%
- **Measured Result:** Round 22 versioned counter: 0.0-4.6% repeated min/max time (NewsSite-Next 4.6% of 2.7% = 0.12%)
- **Ledger Reason (verbatim):** "Round 22 counter at BlockNode::ComputeMinMaxSizes keyed on the inputs and the DOM/style versions: repeated min/max computations are 0.0-4.6% of the function's time in every story (Next 4.6% of a 2.7% share); the earlier 63.8% was measured in a lambda without the versions in the key, across DOM mutations. See the notes."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-10` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Rejected: true repeated min/max computations with DOM/style versions included in the key are 0.0-4.6% of BlockNode::ComputeMinMaxSizes time (0.12% of NewsSite-Next); revisit only if a workload exhibits high same-version min/max repetition.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probes-round22.patch`

---

## SP3-SEP-229 (#229): `layout/reusing-text-shaper-item-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::InlineNode::ShapeText(blink::InlineItemsData*, blink::String const*, blink::BasicHeapVector<(blink::internal::HeapCollectionType)1, cppgc::internal::BasicMember<blink::InlineItem, cppgc::internal::StrongMemberTag, cppgc::internal::DijkstraWriteBarrierPolicy, cppgc::internal::DisabledCheckingPolicy, cppgc::internal::CompressedPointer>, 0u> const*, blink::Font const*) const`
- **Stories:** `Editor-TipTap`
- **Upper Bound:** target-story share 31.38% (Editor-TipTap), avoidable fraction 0.1028, local story impact 3.22%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "withdrawn per outbox/inspection-2026-09-07.md round 5: reviews for the revision-4 decompositions were authored by the orchestrator (400-byte transcripts, generated task ids), covered-by rows were assigned by symbol substring across unrelated phases, and the fraction used does not follow from the packet's applicable predicate"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-07` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Withdrawn in Round 5 decomposition audit; superseded by #243 and #289 on InlineNode::ShapeText / ReusingTextShaper.
- **Design Docs:** `outbox/inspection-2026-09-07.md`
- **Evidence Pointers:** `ledger.json`

---

## SP3-SEP-230 (#230): `layout/simplified-layout-caching`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::SimplifiedLayoutAlgorithm::Layout()`
- **Stories:** `Perf-Dashboard`
- **Upper Bound:** target-story share 10.35% (Perf-Dashboard), avoidable fraction 0.9402, local story impact 9.62%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "withdrawn per outbox/inspection-2026-09-07.md round 5: reviews for the revision-4 decompositions were authored by the orchestrator (400-byte transcripts, generated task ids), covered-by rows were assigned by symbol substring across unrelated phases, and the fraction used does not follow from the packet's applicable predicate"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-07` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Withdrawn in Round 5 decomposition audit; revisit only if a valid time-weighted probe on SimplifiedLayoutAlgorithm::Layout clears the story floor.
- **Design Docs:** `outbox/inspection-2026-09-07.md`
- **Evidence Pointers:** `ledger.json`

---

## SP3-SEP-231 (#231): `layout/oof-candidate-layout-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::OutOfFlowLayoutPart::Run()`
- **Stories:** `Perf-Dashboard`, `NewsSite-Next`, `NewsSite-Nuxt`, `React-Stockcharts-SVG`, `TodoMVC-Backbone`, `TodoMVC-Vue`, `TodoMVC-WebComponents`, `TodoMVC-Lit-Complex-DOM` (+7 more)
- **Upper Bound:** target-story share 10.44% (Perf-Dashboard), avoidable fraction 0.9176, local story impact 9.57%, suite impact 0.6557%, causal budget aggregate upper 9.36%, twin ceiling 8.87%
- **Measured Result:** Twin sizing (Perf-Dashboard): avoidable cycle share 8.785% [8.699%, 8.870%] (ceiling 8.87%)
- **Ledger Reason (verbatim):** "r96 design (outbox/CANDIDATE-231-DESIGN.md 6ae66ae9, 18/18 quotes verified) + host profile check (scratch/results_perf_sampling_bfdi2qcr Perf-Dashboard profile.collapsed): under OutOfFlowLayoutPart::LayoutCandidates (10.00% of the story), BlockNode::Layout is 9.26%, of which 8.76% is full BlockLayoutAlgorithm (5.09) / FlexLayoutAlgorithm (3.67) runs and only 0.03% the layout-result cache check. The sized repeats (8.785%, same key and fragment size) are therefore cache misses on boxes whose subtree is dirty: the probe key had no descendant state (sizing adversary condition). A correct reuse test (clean subtree) saves only CalculateOffset/ComputeOof* and wrapper cost, 0.46-0.59% of Perf-Dashboard < 1.604% floor. The round-72 oracle's +13.54% (leak flag) reused stale layouts. Open question, not measured: whether Perf-Dashboard's subtree dirtiness comes from real content changes or no-op mutations (a discovery lead, class no-op-mutation / unchanged-output). Reversible with reopen."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-25` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Revisit if Perf-Dashboard's OOF subtree dirtiness is shown to come from no-op mutations that can be filtered upstream; clean-subtree OOF candidate caching alone saves only 0.46-0.59% vs the 1.604% Perf-Dashboard floor.
- **Design Docs:** `outbox/CANDIDATE-231-DESIGN.md`, `outbox/SIZING-231-PROBE-DESIGN.md`
- **Evidence Pointers:** `evidence/twin_batch2/sizing-231.json`, `evidence/oracle_batch2/3_231_perfdash_32`, `evidence/probe_r185_perf_dashboard__layout_oof_layout_part.json`, `evidence/probe_r185_todomvc_backbone__layout_oof_layout_part.json`, `measurements/tot-profile/analysis/stories/TodoMVC-Vue/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/TodoMVC-Vue/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/probe_r185_react_stockcharts_svg__layout_oof_layout_part.json`

---

## SP3-SEP-235 (#235): `root/update-style-and-layout-for-node`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::Document::UpdateStyleAndLayoutForNode(blink::Node const*, blink::DocumentUpdateReason)`
- **Stories:** `Perf-Dashboard`, `Editor-CodeMirror`, `React-Stockcharts-SVG`, `Editor-TipTap`, `Charts-chartjs`, `TodoMVC-WebComponents`, `TodoMVC-JavaScript-ES5`, `TodoMVC-React-Complex-DOM` (+8 more)
- **Upper Bound:** target-story share 32.02% (Perf-Dashboard), avoidable fraction 0.0550, local story impact 1.75%, suite impact 0.1409%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "User decision 2026-10-12: parked as not worth the effort; decomposition-gate suite-impact upper bound 0.1409% is below the 0.20% cutoff. Unmeasured; revisit only if the bound is revised upward."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-12` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below a 0.20% suite-impact cutoff (0.1409%); revisit if the bound rises on a newer profile or workload.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probe_r185_perf_dashboard__root_update_style_and_layout_for_node.json`, `evidence/probes-round185-tot.patch`

---

## SP3-SEP-238 (#238): `hittest/tree-scope-element-from-point-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::LayoutView::HitTest(blink::HitTestLocation const&, blink::HitTestResult&)`, `blink::TreeScope::ElementFromPoint(double, double) const`
- **Stories:** `NewsSite-Nuxt`, `NewsSite-Next`
- **Upper Bound:** target-story share 8.53% (NewsSite-Nuxt), avoidable fraction 0.9463, local story impact 8.04%, suite impact 0.7544%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "re-parked by the host, round 57: the user's 2026-09-17 decision (harness artifact: the elementFromPoint calls this mechanism would cache are the runner's Page.layout probes) stands; the #129 r3 revision carried the origin row and the gate reopened it automatically"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-18` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Harness artifact (caches the benchmark runner's Page.layout elementFromPoint probe); do not revisit.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probe_r184_newssite_nuxt__hittest_layout_view_hit_test.json`, `measurements/tot-profile/analysis/stories/NewsSite-Nuxt/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Nuxt/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/probe_r184_newssite_next__hittest_layout_view_hit_test.json`, `measurements/tot-profile/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Next/candidate_frontier.json`, `evidence/probe_r185_newssite_nuxt__hittest_tree_scope_element_from_point.json`

---

## SP3-SEP-242 (#242): `layout/layout-result-discarded-before-paint`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::BlockNode::Layout(blink::ConstraintSpace const&, blink::BlockBreakToken const*, blink::EarlyBreak const*, blink::ColumnSpannerPath const*) const`
- **Stories:** `Editor-TipTap`, `NewsSite-Next`, `NewsSite-Nuxt`, `Perf-Dashboard`, `React-Stockcharts-SVG`, `Editor-CodeMirror`, `TodoMVC-Backbone`, `TodoMVC-Lit-Complex-DOM` (+10 more)
- **Upper Bound:** target-story share 55.76% (Editor-TipTap), avoidable fraction 0.4650, local story impact 25.92%, suite impact 3.8280%
- **Measured Result:** Paired oracle on Editor-TipTap: +0.15% [-0.15%, +0.45%]
- **Ledger Reason (verbatim):** "round 60: the paired oracle (second unpainted layout returns the previous result) bounds the story gain at +0.15% [-0.15, +0.45] on Editor-TipTap against a 30% counter reading; the post-hoc predicate has no online oracle, and #322 on the same function reads +3.66% [3.29, 4.04]. No causal budget, so not sizable; superseded by #322 for sizing."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-19` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Paired oracle on Editor-TipTap measured +0.15% [-0.15%, +0.45%] with no online predictor of whether a layout result will be discarded before paint; superseded by #322.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch1/1b_242_tiptap_32`, `measurements/tot-profile/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-profile-2/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-lens.json`, `measurements/tot-profile/analysis/stories/Editor-CodeMirror/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/Editor-CodeMirror/candidate_frontier.json`, `evidence/probe_r155_newssite_next__layout_unconsumed_cross_pass.json`, `measurements/tot-profile/analysis/stories/NewsSite-Next/candidate_frontier.json`

---

## SP3-SEP-244 (#244): `layout/inline-min-max-text-overlap`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::InlineNode::ComputeMinMaxSizes(blink::WritingMode, blink::ConstraintSpace const&, blink::MinMaxSizesInput const&) const`, `blink::InlineNode::ComputeMinMaxSizes(blink::WritingMode, blink::ConstraintSpace const&, blink::MinMaxSizesFloatInput const&) const`
- **Stories:** `Editor-TipTap`, `Editor-CodeMirror`, `Perf-Dashboard`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `Charts-observable-plot`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM` (+11 more)
- **Upper Bound:** target-story share 8.36% (Editor-TipTap), avoidable fraction 0.5706, local story impact 4.65%, suite impact 0.3148%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "Sizing (ROUND-197) epoch check: candidate evidence is out of epoch (sp3-baseline-1 / sp3-post-158-r3). On the current profile sp3-tot-frontier-1, Editor-TipTap InlineNode::ComputeMinMaxSizes share 0.6290% x 67.1% = 0.4221%, below the 1.0000% story floor (operator report ROUND-197.244.md sha256 9be3cf8edfab)."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below the 1.0000% Editor-TipTap story floor on Epoch 1 profile sp3-tot-frontier-1 (0.6290% x 67.1% = 0.4221%); revisit if InlineNode::ComputeMinMaxSizes share rises.
- **Design Docs:** `outbox/ROUND-197.244.md`
- **Evidence Pointers:** `evidence/probe_r185_editor_tiptap__layout_inline_min_max_text_overlap.json`, `measurements/tot-profile/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-profile-2/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-lens.json`, `evidence/probe_r184_editor_codemirror__layout_inline_min_max_text_overlap.json`

---

## SP3-SEP-288 (#288): `layout/set-style-non-inherited-subgroup-and-image-fast-path`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::LayoutObject::SetStyle(blink::ComputedStyle const*, blink::LayoutObject::ApplyStyleChanges)`
- **Stories:** `TodoMVC-Svelte-Complex-DOM`
- **Upper Bound:** target-story share 3.42% (TodoMVC-Svelte-Complex-DOM), avoidable fraction 0.3500, local story impact 1.14%, suite impact 0.0000%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "host, round 43: measured story by story (ai-skills 3ca2ba6) the claim reads 0.440% of the suite against the 0.449% floor and 1.14% of Svelte against 2.13%; it qualified at suite scope only under the home-fraction assumption (0.490%). A real mechanism below the noise floor; reopen if sizing sharpens or a fuller reading raises the claim."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-17` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below the suite floor (0.440% vs 0.449%) and story floor (1.14% vs 2.13% on TodoMVC-Svelte-Complex-DOM); revisit if calibration MDE tightens or combined with a broader LayoutObject::SetStyle fast path.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/cost_eff_264.json`

---

## SP3-SEP-316 (#316): `layout/lazy-line-break-ascii-alpha-run-fast-forward`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::LazyLineBreakIterator::NextBreakOpportunity(unsigned int, unsigned int) const`, `blink::LazyLineBreakIterator::PreviousBreakOpportunity(unsigned int, unsigned int) const`
- **Stories:** `Editor-TipTap`, `NewsSite-Next`, `NewsSite-Nuxt`, `Editor-CodeMirror`, `Perf-Dashboard`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-WebComponents`, `TodoMVC-Svelte-Complex-DOM` (+12 more)
- **Upper Bound:** target-story share 5.83% (Editor-TipTap), avoidable fraction 0.2204, local story impact 1.28%, suite impact 0.0770%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "User decision 2026-10-12: parked as not worth the effort; decomposition-gate suite-impact upper bound 0.077% is below the 0.20% cutoff. Unmeasured; revisit only if the bound is revised upward."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-12` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below a 0.20% suite-impact cutoff (0.0770%); revisit if the bound rises on a newer profile or workload.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/cost_eff_294.json`

---

## SP3-SEP-322 (#322): `layout/reuse-container-layout-when-children-unchanged`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::BlockNode::Layout(blink::ConstraintSpace const&, blink::BlockBreakToken const*, blink::EarlyBreak const*, blink::ColumnSpannerPath const*) const`
- **Stories:** `Editor-TipTap`, `Editor-CodeMirror`, `NewsSite-Next`, `NewsSite-Nuxt`, `Perf-Dashboard`, `TodoMVC-Lit-Complex-DOM`, `React-Stockcharts-SVG`, `Charts-observable-plot` (+10 more)
- **Upper Bound:** target-story share 10.07% (Editor-TipTap), avoidable fraction 0.5697, local story impact 5.74%, suite impact 2.5606%, causal budget aggregate upper 4.04%, twin ceiling 22.33%
- **Measured Result:** Twin sizing (Editor-TipTap): avoidable cycle share 20.817% [19.301%, 22.332%] (ceiling 22.33%); r86 twin on Editor-TipTap: +0.12% [+0.03%, +0.20%] total cycles (only 5/8,190 BlockNode::Layout calls/rep completed container reuse)
- **Ledger Reason (verbatim):** "r87 diagnostic (counters, r87-diag/redundancy.log, verified by the host): of 8,190 BlockNode::Layout calls per Editor-TipTap repetition only 28 reach the candidate's child-dirty block-container branch; 12 leave it on the simplified path, and 7 of those fall back after a child's size or baseline changed (paying the container layout twice), so 5 containers per repetition complete it. Nearly all of TipTap's layout is inline-children containers and self-dirty boxes, which the shape must exclude (the #226 PaintInlineItems crash class). The twin (r86) matched: no mechanism reduction, total cycles +0.12 [+0.03, +0.20]. Sized 20.8% is not reachable by container-level reuse; the redundancy lives in inline layout (see parked #226/#243/#289). Patch c7620da2 and tests kept in evidence/candidates/322 for reference."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-24` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Container-level BlockNode::Layout reuse when children are unchanged reaches only 5 containers/rep on Editor-TipTap (twin +0.12% [+0.03%, +0.20%]) because TipTap's work is inside inline-children containers; revisit only via inline-level reuse (see #243 v4).
- **Design Docs:** `outbox/CANDIDATE-322-DESIGN.md`
- **Evidence Pointers:** `evidence/twin_batch1/sizing-322.json`, `evidence/candidates/322`, `evidence/oracle_batch1/1a_322_codemirror_32`, `evidence/oracle_batch1/1c_322_tiptap_32`, `measurements/tot-profile/analysis/stories/Editor-CodeMirror/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/Editor-CodeMirror/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/probe_r155_newssite_next__layout_geometry_unchanged_block_child_dirty.json`

---

## SP3-SEP-407 (#407): `flex/reuse-flex-item-construction-when-unchanged`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::FlexLayoutAlgorithm::ConstructAndAppendFlexItems(blink::FlexLayoutAlgorithm::Phase, blink::BasicHeapVector<(blink::internal::HeapCollectionType)1, cppgc::internal::BasicMember<blink::LayoutBox, cppgc::internal::StrongMemberTag, cppgc::internal::DijkstraWriteBarrierPolicy, cppgc::internal::DisabledCheckingPolicy, cppgc::internal::CompressedPointer>, 0u>*)`
- **Stories:** `NewsSite-Nuxt`, `NewsSite-Next`, `Editor-CodeMirror`, `Editor-TipTap`, `Perf-Dashboard`
- **Upper Bound:** target-story share 18.34% (NewsSite-Nuxt), avoidable fraction 0.2948, local story impact 5.40%, suite impact 2.5731%
- **Measured Result:** r166 diagnostic counter on NewsSite-Next: all-clean reusable slice = 1.37% of ConstructAndAppendFlexItems (0.31% of story < 1.0% floor)
- **Ledger Reason (verbatim):** "Round-166 diagnostic (patch evidence/probes-round166-tot.patch a452143b, build 8ffa44bf, log scratch/r166/redundancy_r166_next.log bb0e0b86, NewsSite-Next 20 reps): flex/item-construct-unchanged-output 0.2122 of ConstructAndAppendFlexItems splits into all-clean 0.0137 (606 calls/rep) and some-dirty 0.1989 (2581 calls/rep). Only all-clean is reusable construction; 0.0137 x 22.48 = 0.31 pct-pts < 1.0 story floor (pre-registered threshold f >= 0.04448). some-dirty time is owned by the child layouts it triggers."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-02` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** All-clean reusable flex-item construction is only 1.37% of ConstructAndAppendFlexItems (0.31% of NewsSite-Next < 1.0% floor), while the 19.89% some-dirty slice is child layout time; revisit only if child layout dirtiness itself is eliminated.
- **Design Docs:** `outbox/R166-PROBE-DESIGN.md`
- **Evidence Pointers:** `evidence/probes-round166-tot.patch`, `evidence/probe_r155_newssite_next__flex_item_construct_unchanged_output.json`, `measurements/tot-profile/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/probe_r168_newssite_nuxt__flex_item_construct_unchanged_output.json`, `evidence/probes-round168-tot.patch`, `evidence/cost_343_r14.json`

---

## SP3-SEP-408 (#408): `layout/same-pass-relayout-under-changed-constraints`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::BlockNode::Layout(blink::ConstraintSpace const&, blink::BlockBreakToken const*, blink::EarlyBreak const*, blink::ColumnSpannerPath const*) const`
- **Stories:** `NewsSite-Next`, `Editor-TipTap`, `NewsSite-Nuxt`, `Editor-CodeMirror`, `Perf-Dashboard`, `Charts-observable-plot`, `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-Preact-Complex-DOM` (+9 more)
- **Upper Bound:** target-story share 2.71% (NewsSite-Next), avoidable fraction 0.3623, local story impact 0.97%, suite impact 0.7869%
- **Measured Result:** r166 diagnostic counter on NewsSite-Next: same-space second layout = 0.26% of BlockNode::Layout (0.07% of story < 1.0% floor)
- **Ledger Reason (verbatim):** "Round-166 diagnostic (patch a452143b, build 8ffa44bf, log scratch/r166/redundancy_r166_next.log bb0e0b86): layout/unconsumed-same-pass 0.3667 of BlockNode::Layout splits by ConstraintSpace hash ignoring cache_slot: space-equal output-equal 0.0023 + space-equal output-changed 0.0003 = 0.0026 x 26.93 = 0.07 pct-pts < 1.0 floor (pre-registered f >= 0.03713): same-space second layouts are already served by the layout cache. The mass is space-changed: output-equal 0.1974 (11236 calls/rep), output-changed 0.1668. space-changed-output-equal (second layout under a different space with equal size/baselines/BFC offsets) is a different, early-cutoff hypothesis, not #408s reuse; recorded for a separate decision."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-02` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** Same-ConstraintSpace second layouts in one pass are only 0.26% of BlockNode::Layout (0.07% of NewsSite-Next < 1.0% floor); the 19.74% space-changed-output-equal slice was split out and landed as #410.
- **Design Docs:** `outbox/R166-PROBE-DESIGN.md`
- **Evidence Pointers:** `evidence/probes-round166-tot.patch`, `evidence/probe_r155_newssite_next__layout_unconsumed_same_pass.json`, `measurements/tot-profile/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-lens.json`

---

## SP3-SEP-409 (#409): `layout/reuse-flex-container-layout-when-children-unchanged`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::BlockNode::Layout(blink::ConstraintSpace const&, blink::BlockBreakToken const*, blink::EarlyBreak const*, blink::ColumnSpannerPath const*) const`
- **Stories:** `NewsSite-Nuxt`, `NewsSite-Next`, `Editor-TipTap`, `Editor-CodeMirror`, `Perf-Dashboard`, `Charts-observable-plot`
- **Upper Bound:** target-story share 11.69% (NewsSite-Nuxt), avoidable fraction 0.1917, local story impact 2.22%, suite impact 1.6150%
- **Measured Result:** r167 no-force provenance run on NewsSite-Next: 0 applicable calls out of 2,533,400 BlockNode::Layout calls (100% harness-made)
- **Ledger Reason (verbatim):** "harness-made (round 167 trigger provenance; rule pre-registered in r166/r167: proceed only if no-force eligible fraction x 26.93 >= 1.0). Build 8ffa44bf (patch a452143b), NewsSite-Next 20 reps on the r46 no-force workload scratch/provenance_r46/sp3_noforce (benchmark-runner.mjs bf7b7a4a = v3.1 minus the body getBoundingClientRect + elementFromPoint lines), log scratch/r167/redundancy_r167_next_noforce.log a6e087d1 (12500 rows; host re-ran sums_r166.py: identical, partitions exact): layout/geometry-unchanged-flex-child-dirty records 2533400 BlockNode::Layout calls (9.093 s) with 0 applicable calls; eligible 0, oof 0, percent 0, fragmented 0 -> 0 x 26.93 = 0 pct-pts. With the force present (r166 log bb0e0b86) the same counter read 240000 applicable calls, 0.1390 of BlockNode::Layout, eligible 0.0891, origin-harness 100%. Removing the two harness lines cut BlockNode::Layout time 13.50 s -> 9.09 s. Same outcome as #237 in round 46."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-02` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** 100% harness-made on NewsSite-Next (0 applicable calls out of 2,533,400 BlockNode::Layout calls when the runner's forced getBoundingClientRect + elementFromPoint is removed); do not revisit.
- **Design Docs:** `outbox/R166-PROBE-DESIGN.md`, `outbox/R168-PROBE-DESIGN.md`
- **Evidence Pointers:** `evidence/probes-round166-tot.patch`, `evidence/probe_r155_newssite_next__layout_geometry_unchanged_flex_child_dirty.json`, `measurements/tot-profile/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Next/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/probe_r168_newssite_nuxt__layout_geometry_unchanged_flex_child_dirty.json`, `measurements/tot-profile/analysis/stories/NewsSite-Nuxt/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Nuxt/candidate_frontier.json`
