// Copyright 2026 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Temporary redundancy probe for optimization-campaign discovery.
//
// Sampling profiles say where cycles go; they cannot say how often a subtree
// runs per benchmark step or how often it runs with an input it has already
// seen. Those two numbers are what a Layer 1 (skip the subtree) or Layer 2
// (cache/share the result) claim rests on, so the campaign requires them as
// measured evidence before a proposal is ranked. This header counts, inside
// the exact scored window only:
//
//   calls             entries to the probed site
//   applicable_calls  entries where the proposed invariant held (caller-supplied)
//   distinct_inputs   distinct input hashes seen in the scored group
//   repeated_inputs   calls whose input hash was already seen in the group
//
// Usage (instrumented twin only; never lands):
//
//   #include "chrome-cycle-profiling/resources/redundancy_probe.h"
//
//   void StyleResolver::ResolveStyle(Element& element) {
//     static thread_local perf_instrumentation::RedundancyCounter counter(
//         "style/resolve-style");
//     counter.Record(perf_instrumentation::HashBytes(&key, sizeof key),
//                    /*applicable=*/element.NeedsStyleRecalc());
//     ...
//   }
//
// Emit rows from the same place the cycle rows are flushed (after the scored
// interval closes, never inside a score timer):
//
//   perf_instrumentation::EmitRedundancyRows(stderr, block, repetition_suite);
//
// Rows look like:
//   [SP3_REDUNDANCY_ROW] {"schema_version":1,"site":"style/resolve-style",
//     "group":"3|TodoMVC-React","calls":8123,"applicable_calls":8123,
//     "distinct_inputs":412,"repeated_inputs":7711,"overflow":0,...}
//
// `redundancy_evidence.py` reduces the rows into the packet that
// `campaign.py decompose` binds to the proposal.

#ifndef TOOLS_PERF_MECHANISM_REDUNDANCY_PROBE_H_
#define TOOLS_PERF_MECHANISM_REDUNDANCY_PROBE_H_

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunsafe-buffer-usage"
#pragma clang diagnostic ignored "-Wexit-time-destructors"
#pragma clang diagnostic ignored "-Wshorten-64-to-32"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <atomic>
#include <mutex>
#include <vector>

namespace perf_instrumentation {

inline uint64_t CurrentTid() {
  static thread_local const uint64_t tid =
      static_cast<uint64_t>(syscall(__NR_gettid));
  return tid;
}

inline void WriteJsonString(FILE* output, const char* value) {
  for (const unsigned char* p =
           reinterpret_cast<const unsigned char*>(value ? value : "");
       *p; ++p) {
    if (*p == '"' || *p == '\\') {
      std::fputc('\\', output);
      std::fputc(*p, output);
    } else if (*p >= 0x20) {
      std::fputc(*p, output);
    }
  }
}

inline uint32_t CaptureBlockFromEnvironment(uint32_t fallback) {
  const char* value = std::getenv("SP3_CYCLE_CAPTURE_BLOCK");
  if (!value || !*value)
    return fallback;
  char* end = nullptr;
  const unsigned long parsed = std::strtoul(value, &end, 10);
  if (!end || *end || parsed == 0 || parsed > UINT32_MAX)
    return fallback;
  return static_cast<uint32_t>(parsed);
}

inline uint64_t MonotonicRawNanoseconds() {
  struct timespec timestamp = {};
  if (clock_gettime(CLOCK_MONOTONIC_RAW, &timestamp) != 0)
    return 0;
  return static_cast<uint64_t>(timestamp.tv_sec) * 1000000000ULL +
         static_cast<uint64_t>(timestamp.tv_nsec);
}

inline std::atomic<bool>& ScoredWindowActive() {
  static std::atomic<bool> active{false};
  return active;
}

inline bool IsInScoredWindow() {
  return ScoredWindowActive().load(std::memory_order_relaxed);
}

inline void SetScoredWindowActive(bool active) {
  ScoredWindowActive().store(active, std::memory_order_relaxed);
}

// FNV-1a over arbitrary bytes; adequate for distinct-input counting.
inline uint64_t HashBytes(const void* data, size_t length) {
  uint64_t hash = 1469598103934665603ULL;
  const unsigned char* bytes = static_cast<const unsigned char*>(data);
  for (size_t i = 0; i < length; ++i) {
    hash ^= bytes[i];
    hash *= 1099511628211ULL;
  }
  return hash ? hash : 1;  // zero is the empty-slot sentinel below
}

inline uint64_t HashCombine(uint64_t a, uint64_t b) {
  a ^= b + 0x9e3779b97f4a7c15ULL + (a << 6) + (a >> 2);
  return a ? a : 1;
}

class RedundancyCounter;

inline std::mutex& RedundancyRegistryMutex() {
  static auto& mutex = *new std::mutex();
  return mutex;
}

inline std::vector<RedundancyCounter*>& RedundancyRegistry() {
  static auto& registry = *new std::vector<RedundancyCounter*>();
  return registry;
}

class RedundancyCounter {
 public:
  // Fixed-capacity open-addressing set; sized for one repetition of one story.
  static constexpr size_t kCapacityLog2 = 17;  // 131072 slots
  static constexpr size_t kCapacity = size_t{1} << kCapacityLog2;

  explicit RedundancyCounter(const char* site)
      : site_(site), owner_tid_(CurrentTid()) {
    slots_ = static_cast<uint64_t*>(calloc(kCapacity, sizeof(uint64_t)));
    std::lock_guard<std::mutex> lock(RedundancyRegistryMutex());
    RedundancyRegistry().push_back(this);
  }

  RedundancyCounter(const RedundancyCounter&) = delete;
  RedundancyCounter& operator=(const RedundancyCounter&) = delete;

  // Cheap enough for hot paths: one branch outside the scored window, a
  // few loads inside it. No allocation, no syscalls.
  void Record(uint64_t input_hash, bool applicable) {
    if (!IsInScoredWindow())
      return;
    if (owner_tid_ != CurrentTid()) {
      thread_affinity_violations_++;
      return;
    }
    calls_++;
    if (applicable)
      applicable_calls_++;
    if (input_hash == 0)
      input_hash = 1;
    if (overflow_ || !slots_)
      return;
    size_t index = static_cast<size_t>(input_hash * 0x9E3779B97F4A7C15ULL >>
                                       (64 - kCapacityLog2));
    for (size_t probe = 0; probe < kCapacity; ++probe) {
      uint64_t& slot = slots_[(index + probe) & (kCapacity - 1)];
      if (slot == input_hash) {
        repeated_inputs_++;
        return;
      }
      if (slot == 0) {
        if (distinct_inputs_ + 1 >= kCapacity / 2) {
          overflow_ = true;  // load factor guard; counts stay valid
          return;
        }
        slot = input_hash;
        distinct_inputs_++;
        return;
      }
    }
    overflow_ = true;
  }

  void Reset() {
    calls_ = applicable_calls_ = distinct_inputs_ = repeated_inputs_ = 0;
    thread_affinity_violations_ = 0;
    overflow_ = false;
    if (slots_) {
      memset(slots_, 0, kCapacity * sizeof(uint64_t));
    }
  }

  void Emit(FILE* output, uint32_t block, const char* repetition_suite) const {
    const char* capture_nonce = std::getenv("SP3_CYCLE_CAPTURE_NONCE");
    std::fprintf(output, "[SP3_REDUNDANCY_ROW] {\"schema_version\":1,\"block\":%u,"
                         "\"capture_nonce\":\"", block);
    WriteJsonString(output, capture_nonce);
    std::fprintf(output, "\",\"site\":\"");
    WriteJsonString(output, site_);
    std::fprintf(output, "\",\"group\":\"");
    WriteJsonString(output, repetition_suite);
    std::fprintf(
        output,
        "\",\"pid\":%llu,\"tid\":%llu,\"emitted_monotonic_raw_ns\":%llu,"
        "\"calls\":%llu,\"applicable_calls\":%llu,\"distinct_inputs\":%llu,"
        "\"repeated_inputs\":%llu,\"overflow\":%d,"
        "\"thread_affinity_violations\":%llu}\n",
        static_cast<unsigned long long>(getpid()),
        static_cast<unsigned long long>(owner_tid_),
        static_cast<unsigned long long>(MonotonicRawNanoseconds()),
        static_cast<unsigned long long>(calls_),
        static_cast<unsigned long long>(applicable_calls_),
        static_cast<unsigned long long>(distinct_inputs_),
        static_cast<unsigned long long>(repeated_inputs_),
        overflow_ ? 1 : 0,
        static_cast<unsigned long long>(thread_affinity_violations_));
  }

  const char* site() const { return site_; }
  uint64_t calls() const { return calls_; }
  uint64_t applicable_calls() const { return applicable_calls_; }
  uint64_t distinct_inputs() const { return distinct_inputs_; }
  uint64_t repeated_inputs() const { return repeated_inputs_; }
  bool overflow() const { return overflow_; }

 private:
  const char* site_;
  const uint64_t owner_tid_;
  uint64_t calls_ = 0;
  uint64_t applicable_calls_ = 0;
  uint64_t distinct_inputs_ = 0;
  uint64_t repeated_inputs_ = 0;
  uint64_t thread_affinity_violations_ = 0;
  bool overflow_ = false;
  uint64_t* slots_ = nullptr;
};

// Emit and reset every registered counter for the group that just closed.
inline void EmitRedundancyRows(FILE* output,
                               uint32_t block,
                               const char* repetition_suite) {
  block = CaptureBlockFromEnvironment(block);
  const char* env_log = std::getenv("SP3_REDUNDANCY_LOG");
  FILE* file_log = nullptr;
  if (env_log && *env_log) {
    file_log = std::fopen(env_log, "a");
  }
  std::lock_guard<std::mutex> lock(RedundancyRegistryMutex());
  for (RedundancyCounter* counter : RedundancyRegistry()) {
    counter->Emit(output, block, repetition_suite);
    if (file_log) {
      counter->Emit(file_log, block, repetition_suite);
    }
    counter->Reset();
  }
  std::fflush(output);
  if (file_log) {
    std::fflush(file_log);
    std::fclose(file_log);
  }
}

}  // namespace perf_instrumentation

#pragma clang diagnostic pop

#endif  // TOOLS_PERF_MECHANISM_REDUNDANCY_PROBE_H_
