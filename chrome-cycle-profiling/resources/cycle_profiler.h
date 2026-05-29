#ifndef THIRD_PARTY_BLINK_RENDERER_PLATFORM_LOADER_FETCH_CYCLE_PROFILER_H_
#define THIRD_PARTY_BLINK_RENDERER_PLATFORM_LOADER_FETCH_CYCLE_PROFILER_H_

#include <atomic>
#include <x86intrin.h>
#include "base/compiler_specific.h"
#include "base/logging.h"

namespace blink {

// High-precision, low-overhead CPU cycle profiler using the hardware __rdtscp instruction.
// Executing ReadCycles() takes ~20-30 CPU cycles, virtually eliminating the observer effect.
class CycleProfiler {
 public:
  // 1. Define your custom profiling phases here
  enum Phase {
    kRequestResource,
    kPrepareRequestForCacheAccess,
    kUpgradeResourceRequestForLoader,
    kAddClientHintsIfNecessary,
    kSetReferrer,
    kSetFirstPartyCookie,
    kCalculateIfAdSubresource,
    kCount // Must be last
  };

  static inline uint64_t ReadCycles() {
    unsigned int aux;
    return __rdtscp(&aux);
  }

  static inline void Accumulate(Phase phase, uint64_t start_cycles) {
    if (!g_enabled.load()) {
      return;
    }
    uint64_t elapsed = ReadCycles() - start_cycles;
    UNSAFE_BUFFERS(g_cycles[phase]) += elapsed;
    
    // 2. Change the trigger phase and interval as needed (e.g., print every 1000 calls)
    if (phase == kRequestResource) {
      int64_t count = ++g_count;
      if (count % 500 == 0) {
        uint64_t total = UNSAFE_BUFFERS(g_cycles[kRequestResource]).load();
        if (total == 0) total = 1;
        LOG(ERROR) << "=== CYCLE PROFILE (" << count << " calls) ===";
        
        // 3. Add your PrintPhase statements here to match your custom phases
        PrintPhase("RequestResource             ", kRequestResource, total);
        PrintPhase("PrepareRequestForCacheAccess", kPrepareRequestForCacheAccess, total);
        PrintPhase("UpgradeResourceRequestLoader", kUpgradeResourceRequestForLoader, total);
        PrintPhase("AddClientHintsIfNecessary   ", kAddClientHintsIfNecessary, total);
        PrintPhase("SetReferrer                 ", kSetReferrer, total);
        PrintPhase("SetFirstPartyCookie         ", kSetFirstPartyCookie, total);
        PrintPhase("CalculateIfAdSubresource    ", kCalculateIfAdSubresource, total);
      }
    }
  }

  static inline void Enable() { g_enabled.store(true); }
  static inline void Disable() { g_enabled.store(false); }
  static inline bool IsEnabled() { return g_enabled.load(); }

 private:
  static inline void PrintPhase(const char* name, Phase phase, uint64_t total) {
    uint64_t cycles = UNSAFE_BUFFERS(g_cycles[phase]).load();
    double pct = (100.0 * cycles) / total;
    LOG(ERROR) << "  " << name << ": " << cycles << " cycles (" << pct << "%)";
  }

  static inline std::atomic<uint64_t> g_cycles[kCount] = {};
  static inline std::atomic<int64_t> g_count{0};
  static inline std::atomic<bool> g_enabled{false};
};

// RAII helper to profile a block of code
struct ScopedCycleProfiler {
  CycleProfiler::Phase phase;
  uint64_t start;
  ScopedCycleProfiler(CycleProfiler::Phase p) : phase(p), start(CycleProfiler::ReadCycles()) {}
  ~ScopedCycleProfiler() {
    CycleProfiler::Accumulate(phase, start);
  }
};

}  // namespace blink

#endif  // THIRD_PARTY_BLINK_RENDERER_PLATFORM_LOADER_FETCH_CYCLE_PROFILER_H_
