# Discarded Candidates: CSSOM, Styling & Text Shaping

Subsystem: `third_party/blink/renderer/core/css/`, `platform/fonts/`

---

## CSS-01: `CSSComputedStyleDeclaration` String Fast-Path
- **Concept:** Cache serialized CSS property strings in `CSSComputedStyleDeclaration` to avoid constructing `CSSValue` objects for repeated `getComputedStyle(e).getPropertyValue(...)` calls.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Net negative (`-0.64%`).
- **Causal Failure Mechanism:** Verifying that layout tree styles had not mutated required inspecting `ComputedStyle` generation IDs. The ID check plus atomic string hashing equaled the cost of the lightweight `CSSValue` materialization.
- **Durable Invariant:** Do not attempt string-level caching on `CSSComputedStyleDeclaration`; the engine's `ComputedStyle` sharing already handles style memoization.

---

## CSS-02: `EasySelectorChecker::Match` Subselector Bypass
- **Concept:** Fast-path compound selector evaluation in `EasySelectorChecker` by skipping pseudo-class checks on simple tag/class matchers.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Stat-sig regression on `TodoMVC-JavaScript-ES5` (`-2.29%`).
- **Causal Failure Mechanism:** Subtle interactions with shadow DOM boundaries and `:host` / `:not()` pseudo-classes caused false-positive rule matches, forcing style invalidations and invalid cascade applications.
- **Durable Invariant:** Selector matching shortcuts must be verified against 100% of WPT selector tests; partial shortcuts in `EasySelectorChecker` consistently produce style cascade bugs.

---

## CSS-03: `NGShapeCache` 96-Char Buffer Expansion
- **Concept:** Expand HarfBuzz text shape cache buffer from 64 characters to 96 characters to improve hit rates in code editors (`Editor-CodeMirror`, `Editor-TipTap`).
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Stat-sig regression on `Editor-CodeMirror` (`-2.51%`).
- **Causal Failure Mechanism:** Larger keys increased hash table collision rates and cache memory footprint. In CodeMirror, code tokens are short (5–20 characters), so expanding the key length increased memory bandwidth without improving hit rates for real tokens.
- **Durable Invariant:** Do not increase shape cache or text layout key lengths without proof that average token length in the target workload exceeds the existing boundary.

---

## CSS-04: `Seeker<T>::Seek` Empty Rule Intervals Check
- **Concept:** In `Seeker<T>::Seek`, add an early-return check if the interval list is empty.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `2f4b0e8e09591`).
- **Empirical Result:** Stat-sig regression on `TodoMVC-Lit` (`-2.69% [-5.22%, -0.08%]`).
- **Causal Failure Mechanism:** `Seeker<T>::Seek` is inlined into the innermost loop of CSS rule set matching. In official ThinLTO/PGO2 builds, LLVM perfectly arranges binary branch targets. Adding an outer check introduced branch mispredictions and increased instruction cache footprint on every rule lookup.
- **Durable Invariant:** Never add micro-branch guards or outer empty checks to tightly inlined template search helpers like `Seeker<T>::Seek`. In PGO builds, outer branches cause net regressions.

---

# Campaign `speedometer-september` Discarded & Parked Candidates

## SP3-SEP-225 (#225): `fonts/shape-result-ink-bounds-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::ShapeResultView::ComputeInkBounds() const`
- **Stories:** `Editor-TipTap`, `TodoMVC-Vue`, `TodoMVC-WebComponents`, `TodoMVC-Preact-Complex-DOM`, `NewsSite-Nuxt`, `NewsSite-Next`, `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM` (+12 more)
- **Upper Bound:** target-story share 6.50% (Editor-TipTap), avoidable fraction 0.3205, local story impact 2.07%, suite impact 0.1206%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "User decision 2026-10-12: parked as not worth the effort; decomposition-gate suite-impact upper bound 0.1206% is below the 0.20% cutoff. Unmeasured; revisit only if the bound is revised upward."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-12` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below a 0.20% suite-impact cutoff (0.1206%); revisit if the bound rises on a newer profile or workload.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probe_rework_tiptap_ink_bounds.json`

---

## SP3-SEP-232 (#232): `css/element-matched-rules-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::ElementRuleCollector::CollectMatchingRules(blink::MatchRequest const&, blink::PartNames*)`, `blink::LocalFrameView::UpdateAllLifecyclePhases(blink::DocumentUpdateReason)`
- **Stories:** `TodoMVC-Lit-Complex-DOM`, `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-Vue`, `TodoMVC-WebComponents`, `NewsSite-Next`, `NewsSite-Nuxt`, `TodoMVC-Backbone` (+9 more)
- **Upper Bound:** target-story share 3.80% (TodoMVC-Lit-Complex-DOM), avoidable fraction 0.2639, local story impact 0.94%, suite impact 0.4250%, causal budget aggregate upper 6.94%, twin ceiling 4.52%
- **Measured Result:** Twin sizing (TodoMVC-Svelte-Complex-DOM): avoidable cycle share 4.327% [4.133%, 4.522%] (ceiling 4.52%); r102-r105 candidate r4 (7d556c93): 0 collections taken on TodoMVC-Svelte-Complex-DOM (+0.23% gate/signature overhead)
- **Ledger Reason (verbatim):** "r102-r105: candidate r4 (7d556c93) is correct (tests, receipts) but takes no collections on TodoMVC-Svelte-Complex-DOM. Diagnostics (recounted by the host): 92% of author rule collections repeat a cache key (757 of 821 per repetition), yet every one visits a rule the safe cache refuses: '.notifications-group .notifications-list li > div > :nth-child(2)' (universal bucket, subject :nth-child; 516/rep) and non-subject :hover/:focus rules (304/rep). Reaching them needs sibling-index and ancestor/sibling hover-focus state in the key plus affected-by flag replay onto ancestors and siblings: much larger and riskier for a 3.2% [2.7, 3.7] ceiling vs the 2.134% floor, with +0.23% gate/signature cost measured at r102. User decision 2026-09-25: park. Reversible with reopen; patches r1-r4 and diagnostics under evidence/candidates/232/."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-26` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Revisit if ElementRuleCollector matched-rules caching can cheaply encode sibling-index (:nth-child) and ancestor/sibling :hover/:focus state without exceeding the 3.2% ceiling on TodoMVC-Svelte-Complex-DOM.
- **Design Docs:** `outbox/CANDIDATE-232-DESIGN.md`
- **Evidence Pointers:** `evidence/twin_batch1/sizing-232.json`, `evidence/twin_232_on_234/sizing-232.json`, `evidence/candidates/232`, `evidence/probe_r185_todomvc_backbone__css_element_rule_collector_calls.json`, `evidence/probe_r185_todomvc_lit_complex_dom__css_element_rule_collector_calls.json`, `measurements/tot-profile/analysis/stories/TodoMVC-Vue/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/TodoMVC-Vue/candidate_frontier.json`, `measurements/tot-lens.json`

---

## SP3-SEP-233 (#233): `style/shadow-root-active-style-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::StyleEngine::UpdateActiveStyle()`
- **Stories:** `TodoMVC-WebComponents`
- **Upper Bound:** target-story share 1.57% (TodoMVC-WebComponents), avoidable fraction 0.9900, local story impact 1.55%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "withdrawn per outbox/inspection-2026-09-07.md round 5: reviews for the revision-4 decompositions were authored by the orchestrator (400-byte transcripts, generated task ids), covered-by rows were assigned by symbol substring across unrelated phases, and the fraction used does not follow from the packet's applicable predicate"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-07` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Withdrawn in Round 5 decomposition audit; revisit only if a valid time-weighted probe on StyleEngine::UpdateActiveStyle clears the story floor.
- **Design Docs:** `outbox/inspection-2026-09-07.md`
- **Evidence Pointers:** `ledger.json`

---

## SP3-SEP-243 (#243): `fonts/inline-shape-text-overlap`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::InlineNode::ShapeText(blink::InlineItemsData*, blink::String const*, blink::BasicHeapVector<(blink::internal::HeapCollectionType)1, cppgc::internal::BasicMember<blink::InlineItem, cppgc::internal::StrongMemberTag, cppgc::internal::DijkstraWriteBarrierPolicy, cppgc::internal::DisabledCheckingPolicy, cppgc::internal::CompressedPointer>, 0u> const*, blink::Font const*) const`
- **Stories:** `Editor-TipTap`, `Editor-CodeMirror`, `Perf-Dashboard`, `Charts-observable-plot`, `React-Stockcharts-SVG`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `TodoMVC-Lit-Complex-DOM`, `NewsSite-Next` (+10 more)
- **Upper Bound:** target-story share 31.38% (Editor-TipTap), avoidable fraction 0.5010, local story impact 15.72%, suite impact 0.7484%
- **Measured Result:** r75 v3 sound oracle on Editor-TipTap: -0.31% [-0.97%, +0.35%] (reused 4/258 calls/rep, 0/192 audit mismatches)
- **Ledger Reason (verbatim):** "r75 v3 sound oracle: -0.31% [-0.97, +0.35] Editor-TipTap (n.s.), feeding previous items into ReusingTextShaper from PrepareLayout with a same-offset text guard reused shape results in only 4 of 258 reached calls per repetition (0 of 192 audits mismatched). The 49.5% overlapping calls are paragraphs whose own text item changed, so reuse needs sub-item safe-to-break range copying plus offset relocation for the suffix (what InlineNodeDataEditor does for SetTextWithOffset). Three oracles built and run (r73 identical-text, r75 item-level). Revivable with that v4 design; parked so #322 (20.8% TipTap, sized) takes the host time."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-22` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Item-level shape reuse in InlineNode::ShapeText hit on only 4 of 258 calls/rep (-0.31% [-0.97%, +0.35%] on Editor-TipTap) because edited paragraphs mutate their single text item; revisit with a v4 sub-item safe-to-break range copy + suffix offset relocation design.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch2/2_243_tiptap_32`, `evidence/oracle_batch2/7_243_tiptap_32`, `evidence/oracle_batch2/10_243v3_tiptap_32`, `evidence/oracles-243v3.patch`, `measurements/tot-profile/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-profile-2/analysis/stories/Editor-TipTap/report.json`, `measurements/tot-lens.json`, `evidence/probe_r184_editor_codemirror__fonts_inline_shape_text_overlap.json`

---

## SP3-SEP-283 (#283): `css/style-cascade-important-set-without-full-cascade-map`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::StyleResolver::ResolveStyle(blink::Element*, blink::StyleRecalcContext const&, blink::StyleRequest const&)`
- **Stories:** `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-WebComponents`, `NewsSite-Next`, `NewsSite-Nuxt`, `TodoMVC-Vue`, `TodoMVC-Backbone` (+6 more)
- **Upper Bound:** target-story share 19.62% (TodoMVC-Svelte-Complex-DOM), avoidable fraction 0.0750, local story impact 1.46%, suite impact 0.4492%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "host, round 43: measured story by story (ai-skills 3ca2ba6) the claim reads 0.4492% of the suite against the 0.4494% floor and 1.46% of Svelte against 2.13%; it qualified at suite scope only under the home-fraction assumption (0.549%). A real mechanism at the noise floor; reopen if sizing sharpens or a fuller reading raises the claim."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-17` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Suite impact (0.4492%) sits right at the 0.4494% suite floor (1.46% on TodoMVC-Svelte-Complex-DOM vs 2.13% floor); revisit if calibration MDE tightens or a broader cascade optimization raises the bound.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/cost_eff_249.json`

---

## SP3-SEP-289 (#289): `fonts/reusing-text-shaper-segmented-and-per-item-shape-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::InlineNode::PrepareLayout(blink::InlineNodeData*) const`
- **Stories:** `Editor-TipTap`, `TodoMVC-JavaScript-ES5`, `NewsSite-Nuxt`, `Perf-Dashboard`, `NewsSite-Next`, `TodoMVC-WebComponents`, `TodoMVC-Lit-Complex-DOM`, `Editor-CodeMirror` (+12 more)
- **Upper Bound:** target-story share 33.98% (Editor-TipTap), avoidable fraction 0.1800, local story impact 6.10%, suite impact 0.4469%
- **Measured Result:** 32-block Editor-TipTap sound oracle A/B: -3.73% [-3.98%, -3.47%] (11.3% fired, 40,935/363,021 calls, 0/2,560 audit mismatches)
- **Ledger Reason (verbatim):** "r73 sound oracle (retry): -3.73% [-3.98, -3.47] Editor-TipTap, 32 blocks; fired 40,935 of 363,021 reached (11.3%), 0 of 2,560 audited mismatched; design expected +6.10%. Per-call cache upkeep (key hash and slice copy on every miss, ShapeResult copy on every hit) costs more than the 11% of shaping it removes. evidence/oracle_batch2/8_289_tiptap_32"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-22` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Sound oracle regressed Editor-TipTap by -3.73% [-3.98%, -3.47%] because per-call key hashing, slice copying, and ShapeResult cloning exceed the 11.3% shaping hits; revisit only with a zero-allocation in-place segmentation/shape reuse scheme.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch2/4_289_tiptap_32`, `evidence/oracle_batch2/8_289_tiptap_32`, `evidence/cost_eff_281.json`

---

## SP3-SEP-319 (#319): `css/apply-animated-style-skip-base-data-and-transition-update`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::StyleResolver::ResolveStyle(blink::Element*, blink::StyleRecalcContext const&, blink::StyleRequest const&)`
- **Stories:** `TodoMVC-Svelte-Complex-DOM`, `NewsSite-Nuxt`, `TodoMVC-Preact-Complex-DOM`, `NewsSite-Next`, `TodoMVC-Vue`, `TodoMVC-WebComponents`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM` (+6 more)
- **Upper Bound:** target-story share 19.62% (TodoMVC-Svelte-Complex-DOM), avoidable fraction 0.1150, local story impact 2.25%, suite impact 0.7709%, causal budget aggregate upper 2.25%
- **Measured Result:** Twin sizing on TodoMVC-Svelte-Complex-DOM: 1.63% [1.61%, 1.66%] avoidable cycle share vs 2.134% floor
- **Ledger Reason (verbatim):** "round 69: twin-sized avoidable share 1.63% [1.61, 1.66] of TodoMVC-Svelte-Complex-DOM's scored cycles (baseline share 4.66%, applicability 0.75, 3 blocks on twin Build 13269594), below the story floor 2.134% (2 x MDE 1.067). The oracle's +7.72% was flagged as a leak in round 60 and the counter expected 2.25%; the twin settles it. evidence/twin_batch1/sizing-319.json (45b7d4ed)."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-22` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Twin-sized avoidable share is 1.63% [1.61%, 1.66%] of TodoMVC-Svelte-Complex-DOM, below the 2.134% story floor; revisit if story MDE tightens or combined with another StyleResolver animation/cascade change.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/twin_batch1/sizing-319.json`, `evidence/oracle_batch1/5_319_svelte_48`, `evidence/cost_eff_249.json`, `evidence/probe_rework_svelte_transition.json`

---

## SP3-SEP-320 (#320): `fonts/harfbuzz-extract-shape-results-single-pass-and-uninitialized-run-glyphs`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::HarfBuzzShaper::ExtractShapeResults(blink::RangeContext*, bool&, blink::ReshapeQueueItem const&, blink::SimpleFontData const*, UScriptCode, blink::CanvasRotationInVertical, blink::HarfBuzzShaper::FallbackFontStage&, blink::ShapeResult*) const`, `blink::ShapeResult::InsertRun(blink::ShapeResultRun*, unsigned int, unsigned int, unsigned int*, hb_buffer_t*)`
- **Stories:** `Editor-TipTap`, `NewsSite-Nuxt`, `NewsSite-Next`, `Editor-CodeMirror`, `Perf-Dashboard`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-WebComponents`, `TodoMVC-JavaScript-ES5` (+12 more)
- **Upper Bound:** target-story share 3.93% (Editor-TipTap), avoidable fraction 0.5500, local story impact 2.12%, suite impact 0.1642%
- **Measured Result:** 32-block Editor-TipTap oracle A/B (Speedometer3Oracle320): +0.616% [+0.352%, +0.881%] vs 1.0% floor (100% fired, 0 audit mismatches)
- **Ledger Reason (verbatim):** "r109 oracle A/B (evidence/oracle_batch3/ab-320, manifest ff6e5ca3; 32 blocks, Editor-TipTap, Speedometer3Optimizations on both arms, Speedometer3Oracle320 toggled): +0.616% [0.352, 0.881], below the 1.0% story floor even at the upper bound; the oracle fired on 100% of ExtractShapeResults calls with 0 audit mismatches, so the single-pass fast path is real but small (0.29x the 2.12% estimate)."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-26` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Oracle A/B on Editor-TipTap measured +0.616% [+0.352%, +0.881%] at 100% fire rate, below the 1.0% story floor even at the CI upper bound; revisit if bundled with adjacent HarfBuzzShaper work or if story MDE tightens.
- **Design Docs:** `outbox/SIZING-BATCH-3-PROBE-DESIGN.md`
- **Evidence Pointers:** `evidence/oracle_batch3/ab-320`, `evidence/oracle_batch3/oracle-320.r2.patch`, `evidence/cost_eff_310.json`

---

## SP3-SEP-323 (#323): `style/share-matched-rules-across-same-descriptor-elements`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::StyleResolver::ResolveStyle(blink::Element*, blink::StyleRecalcContext const&, blink::StyleRequest const&)`
- **Stories:** `TodoMVC-Lit-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `TodoMVC-JavaScript-ES5`, `TodoMVC-Backbone`, `Charts-observable-plot`, `TodoMVC-Vue` (+11 more)
- **Upper Bound:** target-story share 12.21% (TodoMVC-Lit-Complex-DOM), avoidable fraction 0.6949, local story impact 8.29%, suite impact 3.4562%
- **Measured Result:** 32-block TodoMVC-Svelte-Complex-DOM sound oracle A/B: -0.28% [-0.89%, +0.32%] (18.3% fired, 118,844/650,432 calls, 0/7,469 audit mismatches)
- **Ledger Reason (verbatim):** "r73 sound oracle: -0.28% [-0.89, +0.32] TodoMVC-Svelte-Complex-DOM, 32 blocks, not significant; sibling-restricted cross-element style sharing fired 118,844 of 650,432 reached (18.3%), 0 of 7,469 audited mismatched; design expected +2.74%. Skipping rule matching and cascade for those elements buys nothing measurable against the per-element style clone. evidence/oracle_batch2/9_323_svelte_32"
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-22` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Sibling-restricted cross-element matched-rule sharing fired on 18.3% of calls on TodoMVC-Svelte-Complex-DOM but measured -0.28% [-0.89%, +0.32%]; revisit only if matched-rule sharing can avoid the per-element ComputedStyle clone without signature overhead.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch2/9_323_svelte_32`, `evidence/probe_r185_todomvc_javascript_es6_webpack_complex_dom__style_resolve_style_content_key_repeat.json`, `evidence/probe_r185_todomvc_javascript_es5__style_resolve_style_content_key_repeat.json`, `evidence/probe_r185_todomvc_backbone__style_resolve_style_content_key_repeat.json`, `measurements/tot-profile/analysis/stories/Charts-observable-plot/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/Charts-observable-plot/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/probe_r185_todomvc_lit_complex_dom__style_resolve_style_content_key_repeat.json`

---

## SP3-SEP-411 (#411): `css/recalc-style-identical-output-residual`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::Element::RecalcStyle(blink::StyleRecalcChange, blink::StyleRecalcContext const&)`
- **Stories:** `TodoMVC-Lit-Complex-DOM`, `Editor-CodeMirror`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `TodoMVC-JavaScript-ES5`, `Perf-Dashboard`, `TodoMVC-Backbone`, `Charts-observable-plot`, `TodoMVC-Vue` (+8 more)
- **Upper Bound:** target-story share 15.50% (TodoMVC-Lit-Complex-DOM), avoidable fraction 0.1765, local story impact 2.73%, suite impact 0.9880%
- **Measured Result:** 32-block full-suite oracle A/B (Speedometer3Oracle411): -1.5178% [-1.6008%, -1.4348%] vs 0.4031% suite floor (1.45% hit rate, 0 audit mismatches)
- **Ledger Reason (verbatim):** "User decision 2026-10-13 after sizing (ROUND-197): 32-block full-suite paired oracle (Speedometer3Oracle411, evidence/oracle_411/ab-suite/ab_results_manifest.json sha256 73b50ca1aa85, 0 audit mismatches) measured -1.5178% [-1.6008%, -1.4348%] vs the 0.4031% suite floor. Its pre-call selector-dependency key hit on only 726 of 50176 RecalcOwnStyle calls (1.45%, TodoMVC-JavaScript-ES6-Webpack-Complex-DOM), and the earlier proposal 406b was dropped on small priors (see the #406 ledger note of 2026-10-02). No cheap predictor of identical output before resolution is known."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** 32-block full-suite oracle (Speedometer3Oracle411) measured -1.5178% [-1.6008%, -1.4348%] with a 1.45% hit rate on its pre-call selector-dependency key; revisit only if a near-zero-cost pre-call predictor of identical RecalcOwnStyle output is discovered.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_411/oracle-411.patch`, `evidence/oracle_411/ab-suite/ab_results_manifest.json`, `evidence/probe_r184_editor_codemirror__style_element_recalc_style.json`, `evidence/probe_r185_todomvc_javascript_es6_webpack_complex_dom__style_element_recalc_style.json`, `evidence/probe_r185_todomvc_javascript_es5__style_element_recalc_style.json`, `evidence/probes-round185-tot.patch`, `evidence/probe_r185_perf_dashboard__style_element_recalc_style.json`, `evidence/probe_r185_todomvc_backbone__style_element_recalc_style.json`
