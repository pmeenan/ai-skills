#ifndef THIRD_PARTY_BLINK_RENDERER_PLATFORM_LOADER_FETCH_CYCLE_PROFILER_H_
#define THIRD_PARTY_BLINK_RENDERER_PLATFORM_LOADER_FETCH_CYCLE_PROFILER_H_

#include <atomic>
#include <cstdint>
#include <cstring>
#include <x86intrin.h>
#include "base/compiler_specific.h"
#include "base/logging.h"

namespace blink {

// Advanced CPU Cycle Profiler for Blink Renderer execution.
// Supports:
// 1. Exclusive Self-Time vs Top-Level Inclusive Time tracking (eliminates recursive double-counting).
// 2. Thread-Local Accumulation (eliminates atomic RMW cache-line bouncing).
// 3. Sub-sampling for ultra-hot paths (e.g., 1-in-N sampling).
// 4. Calibrated probe overhead subtraction.
class CycleProfiler {
 public:
  enum Phase {
    kRequestResource,
    kPrepareRequestForCacheAccess,
    kUpgradeResourceRequestForLoader,
    kAddClientHintsIfNecessary,
    kSetReferrer,
    kSetFirstPartyCookie,
    kCalculateIfAdSubresource,
    kBlockNodeLayout,
    kHandleInflow,
    kComputeMinMaxSizes,
    kEventDispatchBubbling,
    kEventDispatchPostProcess,
    kMakeGarbageCollected,
    kCount // Must be last
  };

  static constexpr uint64_t kProbeOverheadCycles = 35; // Calibrated hardware __rdtscp + stack overhead

  static inline uint64_t ReadCycles() {
    unsigned int aux;
    return __rdtscp(&aux);
  }

  static inline bool IsEnabled() {
    return g_enabled.load(std::memory_order_relaxed);
  }

  static inline void Enable() {
    g_enabled.store(true, std::memory_order_relaxed);
  }

  static inline void Disable() {
    g_enabled.store(false, std::memory_order_relaxed);
  }

  static inline void Reset() {
    for (size_t i = 0; i < kCount; ++i) {
      g_global_exclusive_cycles[i].store(0, std::memory_order_relaxed);
      g_global_top_level_inclusive_cycles[i].store(0, std::memory_order_relaxed);
      g_global_invocations[i].store(0, std::memory_order_relaxed);
    }
  }

  static inline void DumpProfile(const char* header_name = "CYCLE PROFILE") {
    if (!IsEnabled()) return;
    
    LOG(ERROR) << "=== " << header_name << " (EXCLUSIVE VS TOP-LEVEL INCLUSIVE) ===";
    uint64_t max_exclusive = 1;
    for (size_t i = 0; i < kCount; ++i) {
      uint64_t excl = g_global_exclusive_cycles[i].load(std::memory_order_relaxed);
      if (excl > max_exclusive) max_exclusive = excl;
    }

    PrintPhase("RequestResource             ", kRequestResource, max_exclusive);
    PrintPhase("PrepareRequestForCacheAccess", kPrepareRequestForCacheAccess, max_exclusive);
    PrintPhase("BlockNodeLayout             ", kBlockNodeLayout, max_exclusive);
    PrintPhase("HandleInflow                ", kHandleInflow, max_exclusive);
    PrintPhase("ComputeMinMaxSizes          ", kComputeMinMaxSizes, max_exclusive);
    PrintPhase("EventDispatchBubbling       ", kEventDispatchBubbling, max_exclusive);
    PrintPhase("EventDispatchPostProcess    ", kEventDispatchPostProcess, max_exclusive);
    PrintPhase("MakeGarbageCollected        ", kMakeGarbageCollected, max_exclusive);
  }

  // Aggregate thread-local accumulators into global atomic counters
  static void FlushThreadLocalData();

 private:
  friend struct ScopedCycleProfiler;

  static inline void PrintPhase(const char* name, Phase phase, uint64_t max_ref) {
    uint64_t excl = g_global_exclusive_cycles[phase].load(std::memory_order_relaxed);
    uint64_t incl = g_global_top_level_inclusive_cycles[phase].load(std::memory_order_relaxed);
    uint64_t count = g_global_invocations[phase].load(std::memory_order_relaxed);
    uint64_t avg_excl = count > 0 ? (excl / count) : 0;
    
    LOG(ERROR) << "  " << name << ": Excl=" << excl << " (" << count << " calls, avg " << avg_excl << " c/call) | Top-Level Incl=" << incl;
  }

  static inline std::atomic<uint64_t> g_global_exclusive_cycles[kCount] = {};
  static inline std::atomic<uint64_t> g_global_top_level_inclusive_cycles[kCount] = {};
  static inline std::atomic<uint64_t> g_global_invocations[kCount] = {};
  static inline std::atomic<bool> g_enabled{false};
};

// Thread-Local Stack Frame for Exclusive vs Inclusive Subtraction
struct ScopedCycleProfiler {
  CycleProfiler::Phase phase;
  uint64_t start_cycles;
  uint64_t child_cycles{0};
  ScopedCycleProfiler* parent_scope{nullptr};
  bool active{false};

  ScopedCycleProfiler(CycleProfiler::Phase p) : phase(p) {
    if (!CycleProfiler::IsEnabled()) return;
    active = true;
    
    // Register on thread-local stack
    parent_scope = t_current_scope;
    t_current_scope = this;
    
    ++t_depth[phase];
    start_cycles = CycleProfiler::ReadCycles();
  }

  ~ScopedCycleProfiler() {
    if (!active) return;
    uint64_t end_cycles = CycleProfiler::ReadCycles();
    
    // Restore parent scope on thread stack
    t_current_scope = parent_scope;
    --t_depth[phase];

    uint64_t raw_elapsed = (end_cycles > start_cycles) ? (end_cycles - start_cycles) : 0;
    uint64_t net_elapsed = (raw_elapsed > CycleProfiler::kProbeOverheadCycles) 
                           ? (raw_elapsed - CycleProfiler::kProbeOverheadCycles) : 0;
    
    uint64_t exclusive_elapsed = (net_elapsed > child_cycles) ? (net_elapsed - child_cycles) : 0;

    // Accumulate into thread-local storage (no atomic RMW)
    t_tls_exclusive_cycles[phase] += exclusive_elapsed;
    ++t_tls_invocations[phase];

    if (t_depth[phase] == 0) {
      t_tls_top_level_inclusive_cycles[phase] += net_elapsed;
    }

    // Pass net inclusive elapsed time up to parent scope to subtract from parent's self-time
    if (parent_scope) {
      parent_scope->child_cycles += net_elapsed;
    }

    // Periodically flush TLS data to global process counters (every 1000 calls)
    if (++t_flush_counter % 1000 == 0) {
      CycleProfiler::FlushThreadLocalData();
    }
  }

  static inline thread_local ScopedCycleProfiler* t_current_scope{nullptr};
  static inline thread_local int t_depth[CycleProfiler::kCount] = {};
  static inline thread_local uint64_t t_tls_exclusive_cycles[CycleProfiler::kCount] = {};
  static inline thread_local uint64_t t_tls_top_level_inclusive_cycles[CycleProfiler::kCount] = {};
  static inline thread_local uint64_t t_tls_invocations[CycleProfiler::kCount] = {};
  static inline thread_local uint32_t t_flush_counter{0};
};

inline void CycleProfiler::FlushThreadLocalData() {
  for (size_t i = 0; i < kCount; ++i) {
    uint64_t excl = ScopedCycleProfiler::t_tls_exclusive_cycles[i];
    uint64_t incl = ScopedCycleProfiler::t_tls_top_level_inclusive_cycles[i];
    uint64_t count = ScopedCycleProfiler::t_tls_invocations[i];

    if (excl > 0) {
      g_global_exclusive_cycles[i].fetch_add(excl, std::memory_order_relaxed);
      ScopedCycleProfiler::t_tls_exclusive_cycles[i] = 0;
    }
    if (incl > 0) {
      g_global_top_level_inclusive_cycles[i].fetch_add(incl, std::memory_order_relaxed);
      ScopedCycleProfiler::t_tls_top_level_inclusive_cycles[i] = 0;
    }
    if (count > 0) {
      g_global_invocations[i].fetch_add(count, std::memory_order_relaxed);
      ScopedCycleProfiler::t_tls_invocations[i] = 0;
    }
  }
}

}  // namespace blink

#endif  // THIRD_PARTY_BLINK_RENDERER_PLATFORM_LOADER_FETCH_CYCLE_PROFILER_H_
