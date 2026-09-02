# Discarded Candidates: HTML Elements & Forms

Subsystem: `third_party/blink/renderer/core/html/`

---

## HTML-01: `HTMLInputElement::setValue` Redundancy Check
- **Concept:** Check if `input->value() == new_value` in `HTMLInputElement::setValueForBinding` and return early to bypass sanitization, layout dirtiness, and selection resets.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `1da92dcd7047f`).
- **Empirical Result:** Stat-sig regression in `TodoMVC-JavaScript-ES5-Complex-DOM` (`-1.56%`).
- **Causal Failure Mechanism:** Modern frameworks already track input state in JavaScript and only assign `input.value = ...` when the value has changed. The C++ string equality check added string length checks and character comparison overhead to every actual user keystroke/state update, causing mispredicted branches in ThinLTO builds.
- **Durable Invariant:** Do not add string equality guards to `HTMLInputElement::setValue` or similar form control value setters.

---

## HTML-02: `HTMLFastPathParser::ParseAttributes` Empty Check
- **Concept:** Add an early exit in `HTMLFastPathParser::ParseAttributes` when the tag attributes span contains only whitespace.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Regressions across Svelte, Vue, and ES5.
- **Causal Failure Mechanism:** Edge cases in HTML whitespace handling and entity decoding caused the fast-path parser to misclassify valid attributes or fail on trailing slashes, forcing expensive fallback to the full `HTMLDocumentParser`.
- **Durable Invariant:** Do not alter tokenizer scanning or attribute slicing boundaries in `HTMLFastPathParser` without proving that fallback rates to the full parser remain strictly 0.00%.

---

## HTML-03: `DOMParser::parseFromString` Fast-Path
- **Concept:** Route `DOMParser::parseFromString(html, "text/html")` to `HTMLFastPathParser` directly.
- **Rejection Stage:** Initial Review / Adversarial Audit.
- **Empirical Result:** Inaudible delta (`+0.05%`).
- **Causal Failure Mechanism:** `DOMParser` creates an isolated implementation document and already routes directly into Blink's optimized parser pipeline. The DOMParser call frequency in Speedometer 3 is too low to produce measurable benchmark deltas.
- **Durable Invariant:** Optimizations to `DOMParser` must prove significant call volume in target stories before investigation.
