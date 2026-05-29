---
name: chrome-cycle-profiling
description: High-precision, low-overhead CPU cycle profiling in Blink utilizing the __rdtscp instruction and Crossbench stories, with automated validation and A/B comparisons.
---

# High-Precision CPU Cycle Profiling in Blink

This skill provides detailed instructions, templates, and scripts to perform high-precision, near-zero overhead CPU cycle profiling in the Blink renderer thread, bypassing OS timer limitations and Perfetto tracing distortion.

---

## **1. When to Use this Skill**
Use this skill when:
* Investigating micro-overheads or timing tight execution loops (e.g., functions running 5,000+ times during a page load).
* Standard timing utilities (`base::TimeTicks`) skew measurements due to OS clock query overhead (~100–500 ns per call).
* Tracing frameworks (like Perfetto) inject dynamic vtable lookup overhead, distorting the baseline.
* Performing pristine A/B Speedometer story comparison benchmarks.

---

## **2. How to Instrument C++ Code**

### **Step 1: Drop in the CycleProfiler Header**
Copy [cycle_profiler.h](resources/cycle_profiler.h) directly into the directory of the target Blink component (e.g., `third_party/blink/renderer/platform/loader/fetch/` or `third_party/blink/renderer/core/loader/`).

### **Step 2: Define Custom Phases**
Inside `cycle_profiler.h`, define your profiling phases in the `Phase` enum and match them in `PrintPhase` calls inside `Accumulate()`:
```cpp
enum Phase {
  kRequestResource,
  kMyCustomPhase,
  kCount
};
```

### **Step 3: Add Scoped Instruments**
Import `cycle_profiler.h` in your C++ source file and place RAII scope timers at the entry points of target blocks:
```cpp
#include "third_party/blink/renderer/platform/loader/fetch/cycle_profiler.h"

void MyExpensiveFunction() {
  ScopedCycleProfiler cycle_scope(CycleProfiler::kMyCustomPhase);
  // function body...
}
```

> [!IMPORTANT]
> The profiler is **disabled by default** (`g_enabled{false}`). You must explicitly call `CycleProfiler::Enable()` to start collection (e.g., based on a trigger), or change the default value of `g_enabled` to `true` in `cycle_profiler.h` to profile everything from the start.

### **Step 4: Recompile Chrome**
Recompile Chrome before running the benchmark:
```bash
autoninja -C out/Default chrome
```

---

## **3. Running the Cycle Profiler Automation**

Use the self-contained python script [run_cycle_benchmark.py](scripts/run_cycle_benchmark.py) to execute the Speedometer stories, capture stderr logs, and output a clean percentage breakdown:

```bash
# Run Speedometer stories (NewsSite-Next, NewsSite-Nuxt by default)
python3 .agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py

# Run with custom repetitions or browser path
python3 .agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py --repetitions=5 --browser=out/Default/chrome
```

---

## **4. Performing High-Precision A/B Comparisons**

To verify if a feature flag or optimization produces a real-world change under identical top-level conditions, use [run_ab_benchmark.py](scripts/run_ab_benchmark.py):

```bash
python3 .agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py --feature=MyOptimizationFeature --repetitions=5
```

---

## **5. Best Practices & Rigorous Protocol**

1. **Minimize Measurement Overhead**:
   * Keep micro-timing probes active *only* during investigation phases.
   * When collecting final cumulative impact timing numbers, **comment out or remove all micro-level probes** and keep only the top-level timer active. This guarantees pristine top-level measurements.
2. **Spawning a Flash-level Subagent**:
   * To run benchmarks, recompile code, and parse results in the background without polluting your main chat context, spawn a dedicated, flash-level coder subagent:
     ```bash
     # Start a separate subagent conversation
     agentapi new-conversation --model=flash-lite "Compile out/Default and run the cycle profiling script..."
     ```
3. **Adversarial Audit Requirement**:
   * Never land a performance optimization based solely on your own assumptions.
   * Always spawn an **adversarial pro-level subagent** to act as a Performance Critic:
     ```bash
     # Spawn critic subagent
     agentapi new-conversation --model=pro "Critically review this C++ caching design for atomic ref-counting overhead and security bypasses..."
     ```
4. **Safety and Security Checks**:
   * Caches must be dynamically bound to their security context. If caching Permissions Policy or Security Origins, bind the cache directly to the document's `PermissionsPolicy` instance pointer to handle dynamic changes securely.
5. **Profiling Speedometer3 NewsSite**:
   * To profile only the measurement phase and ignore warmup/framework overhead:
     * Use `is_first_request_` in `ResourceFetcher` to count new iframes.
     * Enable profiling (via `CycleProfiler::Enable()`) when `iframe_count == 4`.
     * Filter requests to only include those containing 'newssite' in the URL to exclude framework requests at the end.
6. **Workspace Cleanup**:
   * Once the performance data is gathered, clean up the temporary Crossbench results directories completely to keep the workspace pristine.
   * If you used the default output directory:
     ```bash
     vpython3 .agents/skills/chrome-cycle-profiling/scripts/cleanup_results.py
     ```
   * If you used custom output directories (e.g., for A/B testing), make sure to remove them manually as the script may not cover them:
     ```bash
     rm -rf scratch/results_disabled scratch/results_enabled
     ```
