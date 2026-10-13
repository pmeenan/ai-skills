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

---

# Campaign `speedometer-september` Discarded & Parked Candidates

## SP3-SEP-241 (#241): `resource/resource-request-memory-cache-hit`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::ResourceFetcher::RequestResource(blink::FetchParameters&, blink::ResourceFactory const&, blink::ResourceClient*)`, `blink::ImageResource::Fetch(blink::FetchParameters&, blink::ResourceFetcher*)`
- **Stories:** `NewsSite-Next`, `NewsSite-Nuxt`, `TodoMVC-Svelte-Complex-DOM`, `TodoMVC-Preact-Complex-DOM`, `TodoMVC-Lit-Complex-DOM`, `TodoMVC-WebComponents`, `TodoMVC-Vue`, `TodoMVC-Backbone` (+6 more)
- **Upper Bound:** target-story share 1.51% (NewsSite-Next), avoidable fraction 0.9810, local story impact 1.46%, suite impact 0.2945%
- **Measured Result:** 32-block NewsSite-Next oracle A/B (Speedometer3Oracle241): +1.090% [+0.908%, +1.271%] vs 1.0% floor (100% fired, 0 audit mismatches)
- **Ledger Reason (verbatim):** "r109 oracle A/B (evidence/oracle_batch3/ab-241, manifest e3dc6d84; 32 blocks, NewsSite-Next, Speedometer3Optimizations on both arms): +1.090% [0.908, 1.271] against a 1.0% floor, lower bound below it. The oracle is an explicit upper bound: it skipped CanRequest/CSP/WillSendRequest/SetReferrer on same-fetcher memory-cache hits (302 per iteration, 100% fired, 0 audit mismatches); a shippable change must keep the security checks (PrepareResourceRequestForCacheAccess sub-costs: annotations 0.60%, CanRequest 0.22% of the story), so its gain is lower still."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-26` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Oracle upper bound (+1.090% [0.908%, 1.271%] on NewsSite-Next) skipped mandatory security checks (CanRequest/CSP, 0.22% + 0.60% annotations) and still had its CI lower bound below the 1.0% story floor; revisit only if security/CSP checks on same-fetcher memory-cache hits can be soundly memoized.
- **Design Docs:** `outbox/SIZING-BATCH-3-PROBE-DESIGN.md`
- **Evidence Pointers:** `evidence/oracle_batch3/ab-241`, `evidence/oracle_batch3/oracle-241.r2.patch`, `evidence/cost_346_r7.json`, `measurements/tot-profile/analysis/stories/NewsSite-Nuxt/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/NewsSite-Nuxt/candidate_frontier.json`, `measurements/tot-lens.json`, `evidence/cost_339_r7.json`, `measurements/tot-profile/analysis/stories/NewsSite-Next/candidate_frontier.json`

---

## SP3-SEP-388 (#388): `todomvc-react-redux-cc-layertreehost-requestmainframeupdate-bool`
- **Kind / Status:** `discovery` / `parked`
- **Functions / Anchors:** `TodoMVC-React-Redux/cc::LayerTreeHost::RequestMainFrameUpdate(bool)`
- **Stories:** `TodoMVC-React-Redux`
- **Upper Bound:** target-story share 10.34% (TodoMVC-React-Redux)
- **Measured Result:** r185 --vt 9 probe packet coverage: 2.05 aggregate (iteration 0 = 6.69, iterations 1+ = 1.32) vs [0.5, 2.0] gate band
- **Ledger Reason (verbatim):** "User decision 2026-10-11: parked. Decomposition cannot bind: in TodoMVC-React-Redux the BlockNode::Layout probe family (e.g. probe_r185_todomvc_react_redux__layout_same_pass_cc_rest.json, build 214f1ab3edbd, --vt 9 re-measurement) reads aggregate packet time coverage 2.05, above the gate band [0.5, 2.0] (campaign.py enforce_packet_time_coverage); the excess is in-process iteration 0 (6.69) vs iterations 1+ (1.32). Revisit after the skill update scores coverage on iterations 1+, or with a lower-tax layout probe."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-11` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** Packet-time coverage on TodoMVC-React-Redux was 2.05 across all iterations due to iteration-0 warm-up (6.69 on iter 0 vs 1.32 on iterations 1+); revisit now that optimize-campaign scores packet-time coverage on in-process iterations 1+.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probe_r185_todomvc_react_redux__layout_same_pass_cc_rest.json`, `evidence/redundancy_r185_redux_tot.log`
