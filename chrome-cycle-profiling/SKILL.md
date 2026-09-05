---
name: chrome-cycle-profiling
description: High-precision Desktop Chromium profiling with hardware-cycle perf sampling, V8 JIT basic-prof symbolization, self-auditing targeted C++ cycle instrumentation, and randomized block-interleaved A/B verification.
---

# Performance Profiling & Verification in Desktop Chromium

This skill provides the authoritative runbook, instrumentation resources, and verification protocols for profiling and optimizing CPU performance in Desktop Chromium for Speedometer 3.

For benchmark selection, payload provenance, campaign gates, and local versus
SSH transport, read `../optimize-campaign/SKILL.md`. The score runner and
cycle-profile runner support both `speedometer3` and `jetstream3` adapters with
adapter-specific score parsing; JetStream exact-window campaign import remains blocked pending end-to-end validation.

---

## 1. Environment Constraints & Ground Truth Protocol

1. **Bare-Metal PMU Available:**
   * The test environment is a physical bare-metal machine with hardware PMU counters.
   * **Mandatory Flag:** All sampling `perf record` invocations use hardware cycles with a fixed period: `-e cycles -c 875000 -k mono -g` (about 4 kHz per CPU at the tuner's 3.5 GHz base clock; `--perf-frequency` is the fallback when the clock is not locked). Software-timer sampling (`cpu-clock`) is deprecated in favor of hardware ground truth. Stay under `kernel.perf_event_max_sample_rate` and check `dmesg` for throttling after a capture.
   * **Microarchitectural Awareness:** Hardware cache misses, branch mispredicts, and instruction stalls can now be measured locally using hardware events.
2. **Full-Suite Scope & Headless Screening:**
   * **Full Suite Scope:** Phase 1 profiling and feasibility scope-gate decisions MUST be based on a representative profile across the **default Speedometer 3.1 suite** (`--stories=default`, 20 workloads matching Pinpoint). Explicit `--stories=all` extends coverage to 32 workloads and has a different aggregate. Single-story profiles are used strictly for localized candidate discovery.
   * **Rendering surface:** Campaign profiles, mechanism captures and score runs all use the campaign display policy (`--display :1 --display-vt 9` on the Linux box: a GPU-backed X server owned by the tuner session). Headless mode renders through SwiftShader and is diagnostic only; it puts canvas rasterization and CPU raster on the renderer main thread, which the Mac M1 PGO Pinpoint bot never does. Local runs are relative screening evidence; the Mac M1 PGO bot is the validation reference.
3. **JIT Symbolization (`--perf-basic-prof`) & `-k mono` Requirement:**
   * Chrome MUST run with `--no-sandbox --js-flags=--perf-basic-prof`. `--no-sandbox` MUST be a separate Chrome flag (NOT placed inside `--js-flags`), allowing renderers to write `/tmp/perf-<pid>.map` files cleanly.
   * **Symbol Map Retention:** `/tmp/perf-*.map` files must remain intact in `/tmp` until all `perf report` and `perf script` flame graph generation steps are complete.
   * **Monotonic Clock:** `perf record` MUST specify `-k mono` so timestamp slicing via `perf script --time` correlates cleanly with browser MONOTONIC execution timestamps.
4. **Full Process Tree Partitioning & Structured Manifest:**
   * **Two Profiling Reports:** Phase 1 full-suite sampling requires two reports:
     1. Full Chrome process-tree report partitioned into Browser, Renderer, GPU, and Utility roles.
     2. Renderer-specific deep-dive report for candidate investigation.
   * **Structured PID/Timestamp Manifest:** Poll the launched command's descendants while profiling and record every Chrome PID with its browser, renderer, GPU, or utility role. Preserve the labeled sync/async intervals used by the benchmark score. Outer suite windows are diagnostic only.
   * **Score Weighting & Per-Story Decomposition:** Preserve exact per-suite score intervals. `run_cycle_benchmark.py` passes `--stories-out-dir` and `--stories-scope main-thread` to the analyzer, which emits one independent silo analysis per observed story under `analysis/stories/<story>/` scoped to the renderer main thread (shares local to that story's main-thread scored cycles, entry keys `story:<name>/…`, a score-time composition and portability flags per entry) plus a `stories_index.json` summary. The full-suite and renderer views remain diagnostic. Workload-specific bottlenecks are therefore analyzed as independent silos without geometric-mean dilution or off-thread noise.
   * **Quality Rejection Gate:** Reject profiles with unmatched score marks, poor call stack unwinding, overall `[unknown]` frames >15%, concentrated `[unknown]` frames >10% within any dominant call stack, insufficient total samples (<5,000), or fewer than 100 nominal main-thread samples at the requested marginal floor — applying the sample gates independently to every story silo (a failing story rejects the capture; increase repetitions, default 32).
5. **Mandatory Remote Transfer Compression (`scp -C` / `rsync -z`):**
   * The physical measurement host is remote with constrained upstream/downstream bandwidth.
   * All artifact, patch, log, manifest, and capture transfers to/from the remote host MUST specify compression flags: `scp -C` or `rsync -avz` / `rsync -z`.

---

## 2. Mandatory Phase 0 Preflight & Script Conformance Checklist

Execute these 5 preflight steps in order before Phase 1 profiling. All 5 must pass and emit required JSON manifests:

`run_cycle_benchmark.py` also resolves the browser output directory's GN args
and hard-fails unless the build is official, non-debug, PGO phase 2, and
ThinLTO. Symbols and frame-pointer state are recorded as provenance.

```bash
# Step 1: Software sampling check
perf stat -e cycles true

# Step 2: Process-scoped perf permissions check (matches the capture pipeline)
perf record -e cycles -F 997 -k mono -g -o /tmp/preflight-process.data -- sleep 2 && perf report -i /tmp/preflight-process.data --stdio | head -5

# Step 3: Symbolization smoke test against live Chrome (using -k mono, --no-sandbox, & --js-flags=--perf-basic-prof)
out/perf/chrome --user-data-dir=/tmp/perf-profile --no-first-run --no-sandbox --headless=new --js-flags=--perf-basic-prof https://example.com &
CHROME_PID=$!
sleep 5
RENDERER_PID=$(ps aux | grep "type=renderer" | grep -v "grep" | head -n 1 | awk '{print $2}')
perf record -e cycles -F 997 -k mono -g -p $RENDERER_PID -o /tmp/preflight-jit.data -- sleep 5
kill $CHROME_PID || true
perf report -i /tmp/preflight-jit.data --stdio | head -50

# Step 4: Symbol-free release-build Genuine A/A Baseline Calibration
python3 .agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py --browser=out/release/chrome --required-build-role=release --blocks=32 --aa

# Step 5: Apply the bundled probe and validate the end-to-end Phase 1 pipeline
git apply --check .agents/skills/optimize-campaign/assets/speedometer3/performance-mark-monotonic-probe.patch
git apply .agents/skills/optimize-campaign/assets/speedometer3/performance-mark-monotonic-probe.patch
autoninja -C out/perf chrome
python3 .agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py --browser=out/perf/chrome --stories=NewsSite-Next --display=:1 --display-vt=9
```

# Step 6: Redundancy probe smoke test (compile the header once against the twin)
g++ -std=c++20 -fsyntax-only -I.agents/skills .agents/skills/chrome-cycle-profiling/resources/redundancy_probe.h

### Preflight Pass Criteria & Script Conformance Assertions:
1. **C++ Frames Symbolized:** `blink::...` and `content::...` symbols visible, not raw hex addresses (`symbol_level = 1`).
2. **Deep Stack Unwinding:** Multi-level call graphs visible (`enable_profiling = true` frame pointers).
3. **Named JS Frames:** Named JS functions (`/tmp/perf-*.map` symbols) visible in `perf report`.
4. **A/A Baseline Calibration:** Crossbench completes 32 randomized blocks
   (16 ABBA, 16 BAAB; 64 paired reps per arm) in `--aa` mode, reporting the
   session noise floor and MDE and creating `scratch/ab_results_manifest.json`.
5. **Phase 1 Conformance Verification:**
   - (a) `blink::`/`content::` C++ frames symbolized.
   - (b) Named JS frames (`JS:^runSync`, `JS:^layout`) present.
   - (c) Every `[SP3_SCORE_TIME]` sync/async start has its matching end.
   - (d) `scratch/perf_run_manifest.json` reports `interval_kind: exact-scored`, process roles, and labeled intervals.
   - (e) Per-story analyzer artifacts report `metric_weighting: speedometer-story-v1` with their story name (the diagnostic full view stays `speedometer-geomean-v1`); outer windows are never candidate weight.

---

## 3. Opportunity-Sizing & Correctness Guardrails

1. **Discovery Is Not Sizing:** Hardware-cycle sample share locates broad work. It does not size a mechanism or predict score delta. Use exact-score counters plus paired baseline/oracle/candidate exclusive-cycle evidence through `mechanism_evidence.py`. Classify work as score-critical or CPU-only with a trace artifact.
2. **Instrumentation:** Targeted mechanism cycle probes MUST use user-space PMU reads (`_rdpmc` via `mmap_page`) with platform-specific measured overhead. Synchronous kernel `read(fd)` syscalls (~1,200 cycles) are banned in microsecond-scale paths. Probes MUST be gated on `IsInScoredWindow()` to avoid counter reads and accumulation outside scored intervals after thread initialization (preventing ratio inflation from unscored page loading or stylesheet parsing). Probes MUST be 100% structurally symmetric between baseline and candidate; never place probes inside conditional feature branches. Require at least three independent blocks, adaptive subsampling for sites called >100k times, and an instrumentation A/A confidence interval entirely within ±1%. Baseline exclusive share must not exceed the parent symbol's sample share in the release `perf record` profile.
3. **Correctness Guardrails:** Oracles are opportunity-sizing experiments. Candidate implementations must pass comprehensive correctness checks:
   - Layout geometry & element node count smoke tests.
   - Event listeners & lifecycle ordering.
   - MutationObservers & custom elements.
   - Style invalidation, compositing, accessibility, focus/selection.
   - Oilpan garbage collection lifetime checks.
4. **Mechanical Test Suites:** Combine bounded review checklists with dynamic unit tests, WPT test suites, and recompute-and-compare assertion modes (`DCHECK` verification builds). Remove diagnostic assertions and probes before scoring runs.

---

## 4. Statistical Rigor & Block Log-Difference Verification

1. **Genuine Session A/A Calibration:** Re-measure score noise per session/reboot using the symbol-free official build: `run_ab_benchmark.py --browser=out/release/chrome --required-build-role=release --blocks=32 --aa`. `out/perf` is for symbols-on sampling profiles, never authoritative score claims.
2. **Randomized Block-Interleaved Order (ABBA/BAAB):** `run_ab_benchmark.py` generates a fresh recorded seed by default, balances ABBA and BAAB counts, shuffles the schedule, and uses fresh browser state per rep. Do not repeatedly reuse seed 42.
3. **Block Log-Difference Statistics:** For each block $b$, compute observation $d_b = \text{mean}(\ln B) - \text{mean}(\ln A)$. Compute paired log-ratio mean $\bar{d}$ and 95% confidence intervals across block observations.
4. **Adaptive Block Scaling & Power Rule:** Target $80\%$ statistical power ($\alpha=0.05$). Start at $N=32$ complete blocks. If the CI crosses zero or MDE exceeds the effect that must be resolved, increase to a larger even block count while retaining exact ABBA/BAAB balance. Never rerun until a favorable point appears. If the required count is impractical, classify **INCONCLUSIVE** and route to a more stable lab/Pinpoint or stop.
5. **Provisional Local Promotion & Regression Sign Guardrail:**
   - All local score improvements are explicitly labeled **provisional** until Pinpoint trybot or bare-metal desktop confirmation.
   - **Per-story regression limit:** $\text{CI}_{\text{lower}} \ge \ln(0.98) \approx -2.0\%$ (lower 95% confidence bound must not drop below $-2.0\%$).
   - **5% Overall Suite Goal Bar:** Declared achieved only when full-suite lower 95% confidence bound is at least $+5.0\%$ ($\text{CI}_{\text{lower}} \ge \ln(1.05) \approx +5.0\%$).

---

## 5. Worktree Isolation & Candidate Transfer

* **Campaign profiling uses the shared execution mode:** With `execution: ssh`, profiling runs on the measurement host from a committed SHA via `remote_measure.py`. With `execution: local`, it uses the existing local Chromium tree and never checks out or rewrites it. The disposable-worktree pattern below applies only to standalone use outside a campaign, where probes are applied as patches: use a dedicated disposable worktree (`git worktree add ../perf-profile-phase1`), commit probes on the disposable branch, sample, then remove the worktree. Note a fresh Chromium worktree needs a `gclient sync` before it can build. Broad `git clean -fd` across repo root is strictly forbidden in every mode.
* **Targeted Probe Revert:** When working in local branches, revert only the bundled probe's target:
  ```bash
  git checkout -- third_party/blink/renderer/core/timing/performance.cc
  git status --porcelain
  ```
* **Candidate Integration Transfer:** Save accepted candidate implementations as explicit git commits on the campaign branch named in the campaign ledger (`campaign.py show`), one commit per opportunity. Use isolated candidate worktrees against the frozen baseline for qualification, then integrate accepted commits into the recorded campaign branch.
* **Safe Result Directory Cleanup:** Create results under explicit `mktemp -d` directories and delete ONLY those resolved absolute directory paths.

---

## 6. Automation Scripts

* **Full-Suite Perf Sampling and Tree Analysis:** `python3 .agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py --browser=out/perf/chrome --stories=default --repetitions=32 --display=:1 --display-vt=9` (defaults to enabling the campaign feature; pass `--enable-features=` for a true baseline capture; `--stories=all` explicitly extends coverage to 32 workloads; `--perf-sample-period`/`--perf-frequency` control sampling)
* **Redundancy Probe:** `resources/redundancy_probe.h` counts calls, applicable calls and repeated inputs per scored group; reduce its `[SP3_REDUNDANCY_ROW]` lines with `optimize-campaign/scripts/redundancy_evidence.py` before proposing a skip-the-subtree or reuse-a-result mechanism.
* **Randomized Block A/B Benchmark:** `python3 .agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py --browser=out/release/chrome --required-build-role=release --blocks=32 --feature=FeatureName`
  - `--aa` for A/A calibration; `--browser-a=... --browser-b=...` for binary-vs-binary comparison (bisecting a batch regression). In aa/two-binary modes, `--enable-features=<flags>` applies identically to BOTH arms — required when comparing flag-gated campaign builds, which are otherwise baseline-identical.
  - `--feature` refuses feature names not defined in the source tree (Chrome silently ignores unknown features); `--skip-feature-check` overrides.
  - The manifest (`scratch/ab_results_manifest.json`) includes per-story block statistics with Bonferroni-adjusted flags (`stat_sig_story_regressions`, `stat_sig_story_improvements`); `unadjusted_story_flags` and `expected_false_positive_stories` show how much of the unadjusted list is expected noise. Acceptance uses the campaign fixed-plan block statistics; do not selectively rerun flagged stories.
  - Score runs keep ASLR enabled (per-repetition layout randomization); the runner records the rendering surface, GPU renderer, active VT and foreign GPU compute processes, and refuses a display that is not GPU-backed.
* **Campaign Execution:** Use `python3 .agents/skills/optimize-campaign/scripts/remote_measure.py`. Its `--execution local` mode uses the current physical host without Git tree mutation; `--execution ssh` transfers committed refs, builds on the measurement host, and runs under a lock.
* **Workspace Cleanup:** Delete only explicitly created output directories:
  ```bash
  rm -rf scratch/results_ab_interleaved_* scratch/results_perf_sampling_*
  ```
