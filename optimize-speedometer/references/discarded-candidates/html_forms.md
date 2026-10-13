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

---

# Campaign `speedometer-september` Discarded & Parked Candidates

## SP3-SEP-236 (#236): `parser/domparser-template-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `blink::DOMParser::parseFromString(blink::V8UnionStringOrTrustedHTML const*, blink::V8SupportedType const&, blink::ExceptionState&)`
- **Stories:** `TodoMVC-JavaScript-ES5`
- **Upper Bound:** target-story share 22.34% (TodoMVC-JavaScript-ES5), avoidable fraction 0.0946, local story impact 2.08%, suite impact 0.1179%
- **Measured Result:** Unmeasured (parked prior to oracle/A/B measurement)
- **Ledger Reason (verbatim):** "User decision 2026-10-12: parked as not worth the effort; decomposition-gate suite-impact upper bound 0.1179% is below the 0.20% cutoff. Unmeasured; revisit only if the bound is revised upward."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-10-12` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Below a 0.20% suite-impact cutoff (0.1179%); revisit if the bound rises on a newer profile or workload.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/probe_r185_todomvc_javascript_es5__parser_domparser_parse_from_string.json`

---

## SP3-SEP-285 (#285): `html/fastpath-parser-raw-attribute-span-cache`
- **Kind / Status:** `mechanism` / `parked`
- **Functions / Anchors:** `void blink::(anonymous namespace)::HTMLFastPathParser<unsigned char>::ParseChildren<blink::(anonymous namespace)::HTMLFastPathParser<unsigned char>::TagInfo::Ul>(blink::ContainerNode*)`, `blink::Element* blink::(anonymous namespace)::HTMLFastPathParser<char16_t>::ParseElement<true>()`, `blink::Element* blink::(anonymous namespace)::HTMLFastPathParser<unsigned char>::ParseElement<true>()`
- **Stories:** `TodoMVC-jQuery`, `TodoMVC-JavaScript-ES5`, `TodoMVC-JavaScript-ES6-Webpack-Complex-DOM`, `TodoMVC-Backbone`, `Charts-chartjs`, `Charts-observable-plot`, `Editor-CodeMirror`, `Editor-TipTap` (+12 more)
- **Upper Bound:** target-story share 29.12% (TodoMVC-jQuery), avoidable fraction 0.1450, local story impact 4.21%, suite impact 0.6907%
- **Measured Result:** 32-block TodoMVC-jQuery oracle A/B: -7.84% [-8.04%, -7.64%] slower (97% fired, 0/3.96M audit mismatches)
- **Ledger Reason (verbatim):** "round 72: oracle (raw attribute span cache in the fast-path parser) fired on 97% of reached calls with 0 mismatches in 3.96M audited calls and made TodoMVC-jQuery 7.84% [7.64, 8.04] SLOWER: hashing and comparing the span plus copying the attribute vector costs more than scanning it. The mechanism cannot beat the fast path; the packet's time-weighted repeat (1.1%) said as much."
- **Campaign / Date / Baseline:** `speedometer-september` | `2026-09-22` | `68c685e50ae62703d3ac2b0fe52b017461f238b8` (`sp3-frontier-2`)
- **Revisit If:** Oracle regressed TodoMVC-jQuery by -7.84% [-8.04%, -7.64%] because hashing/comparing raw attribute spans and copying the attribute vector costs more than HTMLFastPathParser's inline scan (1.1% time-weighted repeat); do not revisit.
- **Design Docs:** none
- **Evidence Pointers:** `evidence/oracle_batch2/6_285_jquery_32`, `evidence/cost_eff_256.json`, `evidence/cost_eff_308.json`
