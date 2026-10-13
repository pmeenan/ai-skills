# Discarded Candidates: SVG Subsystem

Subsystem: `third_party/blink/renderer/core/svg/`

---

## SVG-01: `Document::createElementNS` SVG Tag Dispatcher
- **Concept:** Implement a `switch` on common SVG tag names (`path`, `circle`, `rect`, `g`) in `Document::createElementNS` to bypass generic tag lookup tables.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Stat-sig regression on `TodoMVC-Lit-Complex-DOM` (`-2.42%`).
- **Causal Failure Mechanism:** The hardcoded tag dispatch switch created branch table pressure and polluted branch target buffers when non-SVG or varied elements were created in rapid succession.
- **Durable Invariant:** Do not replace Blink's atomic-string qualified name hash tables with hardcoded C++ `switch` statements for element creation.

---

## SVG-02: `CSSPathCache` 1-Entry MRU Cache
- **Concept:** Add a 1-entry MRU cache for parsed `SVGPathByteStream` instances keyed by path string.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `a514ed9da50da`).
- **Empirical Result:** Inaudible delta (`+0.21% [-0.25%, +0.67%]`); zero stat-sig wins across all 32 stories.
- **Causal Failure Mechanism:** Speedometer SVG chart workloads (`React-Stockcharts-SVG`, `Charts-observable-plot`) render dynamic time-series charts where each data point has unique path coordinates. Sequential identical path strings are virtually nonexistent in timed loops.
- **Durable Invariant:** Do not add 1-entry MRU caches for path or geometry strings without confirming temporal locality (repeated identical consecutive strings) in the target workload.

---

# Campaign `speedometer-september` Discarded & Parked Candidates

## SP3-SEP-413 (#413): `layout/layout-svg-text`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::LayoutSVGText::UpdateSVGLayout(blink::SVGLayoutInfo const&)`
- **Stories:** `Charts-observable-plot`, `React-Stockcharts-SVG`
- **Upper Bound:** target-story share 4.00% (Charts-observable-plot), avoidable fraction 0.5071, local story impact 2.02%, suite impact 0.1588%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "User decision 2026-10-12: parked as not worth the effort; decomposition-gate suite-impact upper bound 0.1588% is below the 0.20% cutoff. Unmeasured; revisit only if the bound is revised upward."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-12` | `bbda0de4ff47bec0172dedca40a851b0af591d7a` (`sp3-tot-frontier-1`)
- **Revisit If:** Below a 0.20% suite-impact cutoff (0.1588%); revisit if the bound rises on a newer profile or workload.
- **Design Docs:** none
- **Evidence Pointers:** `measurements/tot-profile/analysis/stories/Charts-observable-plot/candidate_frontier.json`, `measurements/tot-profile-2/analysis/stories/Charts-observable-plot/candidate_frontier.json`, `measurements/tot-lens.json`
