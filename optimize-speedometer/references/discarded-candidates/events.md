# Discarded Candidates: DOM Events & Dispatch

Subsystem: `third_party/blink/renderer/core/dom/events/`

---

## EVT-01: `EventTarget::FireEventListeners` Single-Listener Bypass
- **Concept:** Bypass iteration over `EventListenerVector` when the vector contains exactly one listener.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Net negative (`-0.11%`).
- **Causal Failure Mechanism:** In Chromium, the cost of event dispatch is dominated by V8 context switches, isolate entry, and script execution. Branching on vector size saved 1-2 CPU cycles inside C++, which was eclipsed by branch misprediction penalties on varied listener topologies.
- **Durable Invariant:** Do not add branch specializations for small vector sizes in `EventTarget::FireEventListeners`.

---

## EVT-02: `EventPath` Non-Bubbling Event Allocation Bypass
- **Concept:** When an event has `bubbles = false`, avoid allocating the full `EventPath` vector and dispatch only to the target node.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `b62a277517deb`).
- **Empirical Result:** Net suite drag (`-0.36%`).
- **Causal Failure Mechanism:** Even non-bubbling events must participate in capture phase dispatch and shadow boundary retargeting (WHATWG DOM § 2.8). Bypassing `EventPath` forced fallback paths and broke V8 inline caching for event dispatch trampolines.
- **Durable Invariant:** `EventPath` construction is required for correct shadow DOM retargeting and capture dispatch; do not attempt to bypass it based solely on the `bubbles` flag.
