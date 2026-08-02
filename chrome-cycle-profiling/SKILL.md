---
name: chrome-cycle-profiling
description: High-precision performance profiling in Desktop Chromium utilizing software cpu-clock sampling profilers (perf/pprof) with V8 JIT basic-prof symbolization for authoritative ground truth, complemented by exclusive self-time C++ cycle instrumentation and randomized block-interleaved A/B verification.
---

# Performance Profiling & Verification in Desktop Chromium

This skill provides the authoritative runbook, instrumentation resources, and verification protocols for profiling and optimizing CPU performance in Desktop Chromium for Speedometer 3.

---

## 1. Environment Constraints & Ground Truth Protocol

1. **No Hardware PMU Constraint:**
   * Desktop Cloud VMs lack hardware performance counters (`perf stat -e cycles` fails).
   * **Mandatory Flag:** All sampling `perf record` invocations MUST explicitly specify `-e cpu-clock -F 997 -k mono`. Software-timer sampling provides accurate time attribution and flame graphs.
   * **Microarchitectural Limitation:** Software sampling cannot measure hardware cache misses, branch mispredicts, or instruction stalls. Any candidate relying on microarchitectural effects MUST be validated on bare metal or Pinpoint, never claimed from local VM data.
2. **Full-Suite Scope & Headless Screening:**
   * **Full Suite Scope:** Phase 1 profiling and feasibility scope-gate decisions MUST be based on a representative profile across the **full Speedometer 3 suite** (`--stories=all`). Single-story profiles are used strictly for localized candidate discovery.
   * **Headless vs Desktop:** Local VM profiling and verification runs execute headless (`--headless=new`). Local runs serve as relative A/B screening evidence. Desktop-mode Pinpoint trybots or bare-metal desktop runs are the authoritative ground truth for candidate promotion and final validation.
3. **JIT Symbolization (`--perf-basic-prof`) & `-k mono` Requirement:**
   * Chrome MUST run with `--no-sandbox --js-flags=--perf-basic-prof`. `--no-sandbox` MUST be a separate Chrome flag (NOT placed inside `--js-flags`), allowing renderers to write `/tmp/perf-<pid>.map` files cleanly.
   * **Symbol Map Retention:** `/tmp/perf-*.map` files must remain intact in `/tmp` until all `perf report` and `perf script` flame graph generation steps are complete.
   * **Monotonic Clock:** `perf record` MUST specify `-k mono` so timestamp slicing via `perf script --time` correlates cleanly with browser MONOTONIC execution timestamps.
4. **Full Process Tree Partitioning & Structured Manifest:**
   * **Two Profiling Reports:** Phase 1 full-suite sampling requires two reports:
     1. Full Chrome process-tree report partitioned into Browser, Renderer, GPU, and Utility roles.
     2. Renderer-specific deep-dive report for candidate investigation.
   * **Structured PID/Timestamp Manifest:** Extract structured PID/TID manifests from Crossbench logs: `{"run_id": "...", "story": "...", "repetition": 0, "phase": "measurement", "pid": 1234, "tid": 5678, "role": "renderer", "timestamp_mono_ns": 123456789000}`.
   * **Quality Rejection Gate:** Reject profiles with unmatched measurement marks, poor call stack unwinding, overall `[unknown]` frames >15%, concentrated `[unknown]` frames >10% within any dominant call stack, or insufficient total samples (<5,000 samples).

---

## 2. Mandatory Phase 0 Preflight & Script Conformance Checklist

Execute these 5 preflight steps in order before Phase 1 profiling. All 5 must pass and emit required JSON manifests:

```bash
# Step 1: Software sampling check
perf stat -e cpu-clock true

# Step 2: System-wide permissions check (must use sudo & -a)
sudo perf record -e cpu-clock -F 997 -k mono -g -a -o /tmp/preflight-a.data -- sleep 2 && sudo perf report -i /tmp/preflight-a.data --stdio | head -5

# Step 3: Symbolization smoke test against live Chrome (using -k mono, --no-sandbox, & --js-flags=--perf-basic-prof)
out/perf/chrome --user-data-dir=/tmp/perf-profile --no-first-run --no-sandbox --headless=new --js-flags=--perf-basic-prof https://example.com &
CHROME_PID=$!
sleep 5
RENDERER_PID=$(ps aux | grep "type=renderer" | grep -v "grep" | head -n 1 | awk '{print $2}')
perf record -e cpu-clock -F 997 -k mono -g -p $RENDERER_PID -o /tmp/preflight-jit.data -- sleep 5
kill $CHROME_PID || true
perf report -i /tmp/preflight-jit.data --stdio | head -50

# Step 4: Interleaved 10-rep Genuine A/A Baseline Calibration (--aa mode)
python3 .agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py --browser=out/perf/chrome --blocks=5 --aa

# Step 5: End-to-End Phase 1 Probed Pipeline Validation (Run AFTER applying profiling probes)
python3 .agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py --browser=out/perf/chrome --stories=NewsSite-Next
```

### Preflight Pass Criteria & Script Conformance Assertions:
1. **C++ Frames Symbolized:** `blink::...` and `content::...` symbols visible, not raw hex addresses (`symbol_level = 1`).
2. **Deep Stack Unwinding:** Multi-level call graphs visible (`enable_profiling = true` frame pointers).
3. **Named JS Frames:** Named JS functions (`/tmp/perf-*.map` symbols) visible in `perf report`.
4. **A/A Baseline Calibration:** Crossbench completes 5 randomized ABBA/BAAB blocks in `--aa` mode, reporting session noise floor and MDE, and creating `scratch/ab_results_manifest.json`.
5. **Phase 1 Conformance Verification:**
   - (a) `blink::`/`content::` C++ frames symbolized.
   - (b) Named JS frames (`JS:^runSync`, `JS:^layout`) present.
   - (c) Both `[SP3_MONO_TIME]` start/end timestamps found in `browser.stdout.log`.
   - (d) `scratch/perf_run_manifest.json` written with process PIDs and sliced timestamps.
   - (e) Sliced window duration is plausible (~5--15 seconds for `NewsSite-Next`).

---

## 3. Opportunity-Sizing & Correctness Guardrails

1. **Opportunity-Sizing Plausibility Check & Sensitivity Ranges:** CPU-clock sample share is an **opportunity-sizing plausibility check**, not a rigid rejection invariant. On-CPU sample time differs from wall-clock score duration; removing small critical-path CPU work can unblock wall-clock score by more than its sample share. Use sensitivity ranges (Optimistic: 100% unblocked, Plausible: 50-70% unblocked, Conservative: 25% unblocked) as explicit sensitivity assumptions for feasibility estimation, corroborated by wall-time trace events.
2. **Correctness Guardrails:** Oracles are opportunity-sizing experiments. Candidate implementations must pass comprehensive correctness checks:
   - Layout geometry & element node count smoke tests.
   - Event listeners & lifecycle ordering.
   - MutationObservers & custom elements.
   - Style invalidation, compositing, accessibility, focus/selection.
   - Oilpan garbage collection lifetime checks.
3. **Mechanical Test Suites:** Combine LLM intent reviews with dynamic unit tests, WPT test suites, and recompute-and-compare assertion modes (`DCHECK` verification builds). Remove diagnostic assertions and probes before scoring runs.

---

## 4. Statistical Rigor & Block Log-Difference Verification

1. **Genuine Session A/A Calibration:** Re-measure local A/A noise floor per session/reboot using `run_ab_benchmark.py --browser=out/perf/chrome --blocks=5 --aa`.
2. **Randomized Block-Interleaved Order (ABBA/BAAB):** `run_ab_benchmark.py` alternates executions in randomized ABBA/BAAB blocks with fresh browser state per rep.
3. **Block Log-Difference Statistics:** For each block $b$, compute observation $d_b = \text{mean}(\ln B) - \text{mean}(\ln A)$. Compute paired log-ratio mean $\bar{d}$ and 95% confidence intervals across block observations.
4. **Adaptive Block Scaling & Power Rule:** Target $80\%$ statistical power ($\alpha=0.05$). Initial sample is $N=5$ blocks (10 paired reps). If underpowered relative to session MDE, scale adaptively up to $N_{\text{max}}=15$ blocks. If a candidate remains underpowered after 15 blocks, classify as **INCONCLUSIVE** and route to Pinpoint or reject without further local reruns.
5. **Provisional Local Promotion & Regression Sign Guardrail:**
   - All local score improvements are explicitly labeled **provisional** until Pinpoint trybot or bare-metal desktop confirmation.
   - **Per-story regression limit:** $\text{CI}_{\text{lower}} \ge \ln(0.98) \approx -2.0\%$ (lower 95% confidence bound must not drop below $-2.0\%$).
   - **5% Overall Suite Goal Bar:** Declared achieved only when full-suite lower 95% confidence bound is at least $+5.0\%$ ($\text{CI}_{\text{lower}} \ge \ln(1.05) \approx +5.0\%$).

---

## 5. Worktree Isolation & Candidate Transfer

* **Disposable Worktree Rule:** Phase 1 profiling MUST run in a dedicated disposable worktree (`git worktree add ../perf-profile-phase1`). Apply probes, commit on disposable branch (`git commit -m "Phase 1 profiling probes"`), run sampling, and remove worktree (`git worktree remove ../perf-profile-phase1`). Broad `git clean -fd` across repo root is strictly forbidden.
* **Targeted Probe Revert:** When working in local branches, revert ONLY the two specific profiling probe files:
  ```bash
  git checkout -- third_party/blink/renderer/core/timing/performance.cc third_party/speedometer/v3.0/resources/benchmark-runner.mjs
  git status --porcelain
  ```
* **Candidate Integration Transfer:** Save accepted candidate implementations as explicit git commits on candidate branches. Merge accepted candidate commits into the `speedometer-5pct-integration` integration branch for Phase 4 multi-candidate evaluation.
* **Safe Result Directory Cleanup:** Create results under explicit `mktemp -d` directories and delete ONLY those resolved absolute directory paths.

---

## 6. Automation Scripts

* **Full-Suite Perf Sampling Run:** `python3 .agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py --browser=out/perf/chrome --stories=all`
* **Randomized Block A/B Benchmark:** `python3 .agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py --browser=out/perf/chrome --blocks=5 --feature=FeatureName`
* **Workspace Cleanup:** Delete only explicitly created output directories:
  ```bash
  rm -rf scratch/results_ab_interleaved_* scratch/results_perf_sampling_*
  ```
