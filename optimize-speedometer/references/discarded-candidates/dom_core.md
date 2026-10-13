# Discarded Candidates: DOM Core & Tree Mutation

Subsystem: `third_party/blink/renderer/core/dom/`, `core/editing/serializers/`

---

## DOM-01: `Element::setInnerHTML` Buffer Pre-allocation
- **Concept:** Pre-allocate string builders or parser buffers based on input HTML length during `setInnerHTML`.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Negligible impact (`+0.02%`).
- **Causal Failure Mechanism:** String materialization and HTML tokenizer state machine instantiation dwarf initial buffer allocation costs. The allocation is already handled efficiently by WTF `StringBuilder` exponential growth.
- **Durable Invariant:** Do not attempt pre-sizing or capacity reservation optimizations for HTML parser input buffers.

---

## DOM-02: `HTMLCollection` Sequential Index Caching
- **Concept:** Cache the last accessed integer index and corresponding node pointer in `HTMLCollection` to optimize `collection[i]` sequential iteration loops.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Flat delta (`+0.07%`).
- **Causal Failure Mechanism:** Blink already implements `CollectionItemsCache` and `CollectionIndexCache` inside `ContainerNode`. Adding an extra layer of index caching at the IDL wrapper level added redundant branch checks without avoiding tree walks.
- **Durable Invariant:** Do not add outer index/iterator caches to DOM collections; internal collection caches already optimize forward/backward traversal.

---

## DOM-03: `Element::SetAttributeInternal` Redundancy Check
- **Concept:** In `Element::SetAttributeInternal`, check if `getAttribute(name) == new_value` and return early to avoid attribute synchronization and mutation records.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Net negative (`-0.20%`).
- **Causal Failure Mechanism:** Modern JavaScript UI frameworks (React, Vue, Preact, Lit) already maintain virtual DOM or template state and omit setting unchanged attributes in user-space script. The C++ check was evaluated on every legitimate attribute update where strings differed, adding string equality comparison overhead to every mutation.
- **Durable Invariant:** Avoid adding duplicate-check branches to general DOM attribute setters. Frameworks already deduplicate in JS; C++ checks only penalize genuine mutations.

---

## DOM-04: `ContainerNode::NotifyNodeRemoved` Leaf Short-Circuit
- **Concept:** When removing a leaf node, bypass subtree walks in `NotifyNodeRemoved` by checking `!node->hasChildren()`.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Regressed `TodoMVC-JavaScript-ES5-Complex-DOM` (`-1.56%`).
- **Causal Failure Mechanism:** Blink's `ContainerNode::RemoveBetween` already batches removal notifications. Adding pre-removal checks on every individual child detachment added redundant branch evaluations without reducing work in batched removal routines.
- **Durable Invariant:** Do not add outer leaf-node guards to removal notification pipelines; batch removal routines (`RemoveChildren`, `RemoveBetween`) already optimize unparented and childless subtrees.

---

## DOM-05: `ContainerNode::RemoveChildren` Batch Detachment
- **Concept:** Manually unlink child node linked-list pointers in a flat loop inside `RemoveChildren()` before triggering tree detachments to optimize bulk deletions.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `e7fe5448749d0`).
- **Empirical Result:** Stat-sig regression on `NewsSite-Nuxt` (`-0.88%`).
- **Causal Failure Mechanism:** Pre-unlinking child pointers disrupted Blink's unified layout tree detachment (`DetachLayoutTree`) and invalidated DOM tree structural invariants expected by subsequent MutationObserver notification scopes.
- **Durable Invariant:** Never modify DOM tree sibling/parent pointers ahead of Blink's standard `Node::DetachLayoutTree` and `ContainerNodeWillBeRemoved` sequence.

---

## DOM-06: `SelectorQuery` Childless Container Bypass & `SpaceSplitString` Single-Class
- **Concept:** In `SelectorQuery::QueryAll()`, return early if `!root_node.hasChildren()`. In `SpaceSplitString`, optimize single-class elements by checking `vector_.front()`.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `94aa1c3d49674`).
- **Empirical Result:** Sub-threshold suite delta `+0.18% [-0.21%, +0.58%]` ($t = 0.94$); zero stat-sig story wins.
- **Causal Failure Mechanism:** While directionally positive in `TodoMVC-Backbone` (`+1.18%`), querying selectors against childless nodes is rare in modern frameworks. The per-call cycle savings were too small (<5 cycles) to cross statistical significance.
- **Durable Invariant:** Selector query optimizations must address selector matching complexity (e.g. bloom filters or rule sharing) rather than trivial container empty checks.

---

# Campaign `speedometer-september` Discarded & Parked Candidates

## SP3-SEP-240 (#240): `dom/import-node-template-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::Document::importNode(blink::Node*, blink::V8UnionBooleanOrImportNodeOptions*, blink::ExceptionState&)`
- **Stories:** `TodoMVC-WebComponents`, `TodoMVC-Lit-Complex-DOM`, `Perf-Dashboard`
- **Upper Bound:** target-story share 3.47% (TodoMVC-WebComponents), avoidable fraction 0.9665, local story impact 3.04%, suite impact 0.2585%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "r106 batch-3 design (outbox/SIZING-BATCH-3-ORACLES.md a30e8ab4, 19/19 quotes; profile recomputed by the host): importNode is 3.15% of TodoMVC-WebComponents, 99.6% of it DocumentFragment::Clone -> per-instance AppendChild 1.04%, CloneAttributesFrom 0.85% (ElementData already shared across clones), CreateElement 0.36%, TextFieldInputType::UpdateView 0.32%. A template cache cannot skip creating distinct DOM nodes; the shareable part is already shared. Parked before any oracle build."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-26` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** 99.6% of Document::importNode in TodoMVC-WebComponents is per-instance DOM node construction (DocumentFragment::Clone), while ElementData is already shared; revisit only if bulk DOM node cloning itself can be amortized.
- **Design Docs:** `outbox/SIZING-BATCH-3-PROBE-DESIGN.md`
- **Evidence Pointers:** `evidence/probe_r185_todomvc_webcomponents__dom_document_import_node.json`

---

## SP3-SEP-318 (#318): `dom/selector-query-subtree-bloom-filter-tag-name-bits`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `void blink::SelectorQuery::Execute<blink::SingleElementSelectorQueryTrait>(blink::ContainerNode&, blink::SingleElementSelectorQueryTrait::OutputType&) const`
- **Stories:** `NewsSite-Next`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `TodoMVC-WebComponents`, `TodoMVC-JavaScript-ES5`, `Perf-Dashboard`, `NewsSite-Nuxt`, `TodoMVC-Svelte-Complex-DOM` (+11 more)
- **Upper Bound:** target-story share 1.59% (NewsSite-Next), avoidable fraction 0.7419, local story impact 1.17%, suite impact 0.2052%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "Sizing (ROUND-197) epoch check: candidate evidence is out of epoch (sp3-baseline-1 / sp3-post-158-r3). On the current profile sp3-tot-frontier-1, NewsSite-Next SelectorQuery::Execute share 0.6285% x 75.07% = 0.4718%, below the 1.0000% story floor (operator report ROUND-197.318.md sha256 c4fdae2a41a8)."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below the 1.0000% NewsSite-Next story floor on Epoch 1 profile sp3-tot-frontier-1 (0.6285% x 75.07% = 0.4718%); revisit if SelectorQuery::Execute share rises.
- **Design Docs:** `outbox/ROUND-197.318.md`
- **Evidence Pointers:** `evidence/probe_r185_newssite_next__dom_container_node_query_selector.json`, `evidence/cost_eff_298.json`

---

## SP3-SEP-412 (#412): `bindings/to-blink-atomic-string`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::AtomicString blink::ToBlinkString<blink::AtomicString>(v8::Isolate*, v8::Local<v8::String>, blink::ExternalMode)`
- **Stories:** `Charts-observable-plot`, `React-Stockcharts-SVG`, `TodoMVC-WebComponents`, `TodoMVC-Vue`, `Perf-Dashboard`, `NewsSite-Next`, `TodoMVC-Lit-Complex-DOM`, `NewsSite-Nuxt` (+9 more)
- **Upper Bound:** target-story share 2.22% (Charts-observable-plot), avoidable fraction 0.7227, local story impact 1.59%, suite impact 0.4188%
- **Measured Result:** 32-block Charts-observable-plot oracle A/B (Speedometer3Oracle412): -0.1269% [-0.3100%, +0.0565%] vs 1.2545% floor (93.75% fired, 0/476,621 audit mismatches); twin post-hoc share 1.6746% [1.6531%, 1.6952%]
- **Ledger Reason (verbatim):** "Sizing (ROUND-197): 32-block Charts-observable-plot paired oracle (Speedometer3Oracle412, manifest evidence/oracle_412/ab-plot/ab_results_manifest.json sha256 1c5ed51006207d7d, 0/476621 audit mismatches, fired on 7149334 of 7625955 applicable calls) measured -0.1269% [-0.3100%, +0.0565%] vs the 1.2545% story floor: bypassing AtomicString::FromUTF8 on nearly every applicable call yields no gain because v8::String::WriteOneByteV2 still runs (operator report). Twin post-hoc cycle share 1.6746% does not translate into wall-clock savings."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** 32-block Charts-observable-plot oracle (Speedometer3Oracle412) fired on 93.75% of applicable calls and measured -0.1269% [-0.3100%, +0.0565%] because v8::String::WriteOneByteV2 still runs; revisit only if V8-side external or pre-atomized string handoff can bypass copying altogether.
- **Design Docs:** `outbox/SIZING-414-412-DESIGN.md`
- **Evidence Pointers:** `evidence/oracle_412/oracle-412.patch`, `evidence/oracle_412/ab-plot/ab_results_manifest.json`, `evidence/twin_r197/sizing-412-plot.json`, `measurements/tot-profile/analysis/stories/Charts-observable-plot/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/Charts-observable-plot/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/cost_356_r10.json`, `measurements/tot-profile/analysis/stories/React-Stockcharts-SVG/candidate_frontier.json`

---

## SP3-SEP-415 (#415): `dom/custom-element-reaction-queue-invoke`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::CustomElementReactionQueue::InvokeReactions(blink::Element&)`
- **Stories:** `TodoMVC-WebComponents`, `TodoMVC-Lit-Complex-DOM`, `Perf-Dashboard`
- **Upper Bound:** target-story share 15.39% (TodoMVC-WebComponents), avoidable fraction 0.9568, local story impact 14.30%, suite impact 0.8634%, causal budget aggregate upper 1.82%
- **Measured Result:** 32-block full-suite oracle A/B (Speedometer3Oracle415): +0.2923% [+0.1683%, +0.4163%] suite, +1.5762% [+1.3312%, +1.8209%] TodoMVC-WebComponents; twin avoidable share 0.9740% [0.9704%, 0.9774%] < 1.100% story floor
- **Ledger Reason (verbatim):** "User decision 2026-10-13 after sizing (ROUND-197/198). The TodoMVC-WebComponents oracle measured +1.58% [+1.33, +1.82] (Speedometer3Oracle415), but the twin avoidable share is 0.974% [0.970, 0.977] (evidence/twin_r198/sizing-415-webcomponents.json), below the 1.100% story floor (campaign.py:11026). The part that removes it (DESIGN-415.md Component A) skips attributeChangedCallback by lexically matching the page's JavaScript source (if (oldValue === newValue) return;), which is benchmark-specific special-casing and not upstreamable. The general part (Component B: reaction-stack fast path and queue pooling) is about 0.71% by subtraction, unmeasured, and below the floor."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-13` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** Twin avoidable share on TodoMVC-WebComponents is 0.974% [0.970%, 0.977%] < 1.100% story floor, and the oracle's +1.58% relied on Component A (pattern-matching page JS source `if (oldValue === newValue) return;`), which is disallowed benchmark special-casing; Component B alone is ~0.71% < 1.100% floor. Revisit only if V8/Blink callback boundary overhead is reduced generally across all callbacks.
- **Design Docs:** `outbox/DESIGN-415.md`
- **Evidence Pointers:** `evidence/oracle_415/oracle-415.patch`, `evidence/oracle_415/ab-suite/ab_results_manifest.json`, `evidence/oracle_415/budget-415.json`, `evidence/twin_r198/sizing-415-webcomponents.json`, `evidence/cost_371_r2.json`, `evidence/probe_r185_todomvc_lit_complex_dom__dom_custom_element_reaction_queue_invoke.json`, `measurements/tot-profile/analysis/stories/TodoMVC-Lit-Complex-DOM/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/TodoMVC-Lit-Complex-DOM/candidate_frontier.json`
