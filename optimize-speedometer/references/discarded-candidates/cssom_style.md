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
