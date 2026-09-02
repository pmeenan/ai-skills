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
