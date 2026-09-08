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
//   total_ns          wall time inside the probed scope (timed calls only),
//                     exclusive of nested scopes of the same counter
//   applicable_ns     that time on calls where the invariant held
//   repeated_ns       that time on calls whose input hash was already seen
//   nested_calls      calls that ran inside another scope of the same counter
//   build_id          GNU build id of the executable that emitted the row
//
// A call count says how often a site ran; it does not say how much of the
// site's time those calls carried. A root update that finds nothing dirty on
// 92% of its calls spends its time in the other 8%, so `applicable_calls`
// alone overstates what skipping those calls would save. The campaign gate
// therefore binds only packets whose rows are time-weighted: every call was
// recorded through a RedundancyScope covering the work the hypothesis would
// skip, so `applicable_ns / total_ns` bounds the avoidable time.
//
// Recursive sites (layout of a box lays out its children through the same
// function; a pre-paint walk visits its subtree) are timed exclusively: a
// scope's elapsed time excludes the time of scopes of the same counter that
// ran inside it, so `total_ns` is the time under the outermost calls rather
// than that time counted once per nesting level. Rows say so with
// "timing":"exclusive"; the gate refuses rows that do not.
//
// Every row names the executable that produced it (`build_id`, the ELF
// NT_GNU_BUILD_ID of the running program). A packet records it, and
// packets bound together must come from one build per probe patch: a log
// from a binary built before the patch changed is not evidence for it.
//
// Usage (instrumented twin only; never lands):
//
//   #include "chrome-cycle-profiling/resources/redundancy_probe.h"
//
//   const LayoutResult* BlockNode::Layout(const ConstraintSpace& space, ...) {
//     static thread_local perf_instrumentation::RedundancyCounter counter(
//         "layout/box-layout");
//     perf_instrumentation::RedundancyScope scope(counter);
//     scope.SetKey(perf_instrumentation::HashCombine(box_key, space_hash));
//     ...   // the work the hypothesis would skip
//     scope.SetApplicable(cache_status == LayoutCacheStatus::kHit);
//     return result;   // the scope records key, applicable and elapsed time
//   }
//
// `Record(key, applicable)` still exists for counting alone; rows it produces
// carry no time and the gate refuses them above the story floor.
//
// The scope opens before the work the probed function does, as the first
// statement of the function the packet names as its `probe_symbol`. A scope
// opened after part of the work (after a lifecycle update inside a hit test,
// after the paint tree walk) times only the rest; the gate compares each
// packet's time per repetition with the probed function's share of the
// story's cycle profile and refuses a packet that times a fraction of it.
//
// Emit rows from the same place the cycle rows are flushed (after the scored
// interval closes, never inside a score timer):
//
//   perf_instrumentation::EmitRedundancyRows(stderr, block, repetition_suite);
//
// Rows look like:
//   [SP3_REDUNDANCY_ROW] {"schema_version":1,"site":"style/resolve-style",
//     "group":"3|TodoMVC-React","calls":8123,"applicable_calls":8123,
//     "distinct_inputs":412,"repeated_inputs":7711,"overflow":0,
//     "timed_calls":8123,"total_ns":41230000,"applicable_ns":40100000,
//     "repeated_ns":39000000,"nested_calls":0,"timing":"exclusive",
//     "build_id":"5f0c...",...}
//
// `redundancy_evidence.py` reduces the rows into the packet that
// `campaign.py decompose` binds to the proposal.

#ifndef TOOLS_PERF_MECHANISM_REDUNDANCY_PROBE_H_
#define TOOLS_PERF_MECHANISM_REDUNDANCY_PROBE_H_

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunsafe-buffer-usage"
#pragma clang diagnostic ignored "-Wexit-time-destructors"
#pragma clang diagnostic ignored "-Wshorten-64-to-32"

#include <elf.h>
#include <link.h>
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

// The GNU build id of the running executable (the first object
// dl_iterate_phdr reports), as lowercase hex; "unknown" when the program
// carries no NT_GNU_BUILD_ID note. Computed once per process.
inline int BuildIdCallback(struct dl_phdr_info* info, size_t, void* out) {
  char* buffer = static_cast<char*>(out);
  for (int i = 0; i < info->dlpi_phnum; ++i) {
    const ElfW(Phdr)& phdr = info->dlpi_phdr[i];
    if (phdr.p_type != PT_NOTE)
      continue;
    const char* note = reinterpret_cast<const char*>(info->dlpi_addr + phdr.p_vaddr);
    const char* end = note + phdr.p_memsz;
    while (note + sizeof(ElfW(Nhdr)) <= end) {
      const ElfW(Nhdr)* header = reinterpret_cast<const ElfW(Nhdr)*>(note);
      const size_t name_size = (header->n_namesz + 3) & ~size_t{3};
      const size_t desc_size = (header->n_descsz + 3) & ~size_t{3};
      const char* name = note + sizeof(ElfW(Nhdr));
      const char* desc = name + name_size;
      if (desc + header->n_descsz > end)
        break;
      if (header->n_type == NT_GNU_BUILD_ID && header->n_namesz == 4 &&
          memcmp(name, "GNU", 4) == 0 && header->n_descsz > 0) {
        size_t length = header->n_descsz;
        if (length > 32)
          length = 32;
        for (size_t j = 0; j < length; ++j) {
          static const char kHex[] = "0123456789abcdef";
          const unsigned char byte = static_cast<unsigned char>(desc[j]);
          buffer[2 * j] = kHex[byte >> 4];
          buffer[2 * j + 1] = kHex[byte & 15];
        }
        buffer[2 * length] = '\0';
        return 1;
      }
      note = desc + desc_size;
    }
  }
  return 1;  // only the first object (the executable) is consulted
}

inline const char* BuildId() {
  static const char* const id = [] {
    static char buffer[65] = "unknown";
    char scratch[65] = {0};
    dl_iterate_phdr(&BuildIdCallback, scratch);
    if (scratch[0])
      memcpy(buffer, scratch, sizeof(scratch));
    return buffer;
  }();
  return id;
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
class RedundancyScope;

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
  // few loads inside it. No allocation, no syscalls. Counts only; prefer
  // RedundancyScope so the row is time-weighted.
  void Record(uint64_t input_hash, bool applicable) {
    RecordImpl(input_hash, applicable, /*timed=*/false, /*elapsed_ns=*/0,
               /*nested=*/false);
  }

  // A call recorded with the wall time its scope covered, exclusive of
  // nested scopes of this counter; `nested` says it ran inside one.
  void RecordTimed(uint64_t input_hash, bool applicable, uint64_t elapsed_ns,
                   bool nested = false) {
    RecordImpl(input_hash, applicable, /*timed=*/true, elapsed_ns, nested);
  }

 private:
  friend class RedundancyScope;

  void RecordImpl(uint64_t input_hash, bool applicable, bool timed,
                  uint64_t elapsed_ns, bool nested) {
    if (!IsInScoredWindow())
      return;
    if (owner_tid_ != CurrentTid()) {
      thread_affinity_violations_++;
      return;
    }
    calls_++;
    if (applicable)
      applicable_calls_++;
    if (nested)
      nested_calls_++;
    if (timed) {
      timed_calls_++;
      total_ns_ += elapsed_ns;
      if (applicable)
        applicable_ns_ += elapsed_ns;
    }
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
        if (timed)
          repeated_ns_ += elapsed_ns;
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

 public:

  void Reset() {
    calls_ = applicable_calls_ = distinct_inputs_ = repeated_inputs_ = 0;
    timed_calls_ = total_ns_ = applicable_ns_ = repeated_ns_ = 0;
    nested_calls_ = 0;
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
        "\"timed_calls\":%llu,\"total_ns\":%llu,\"applicable_ns\":%llu,"
        "\"repeated_ns\":%llu,\"nested_calls\":%llu,\"timing\":\"exclusive\","
        "\"build_id\":\"%s\","
        "\"thread_affinity_violations\":%llu}\n",
        static_cast<unsigned long long>(getpid()),
        static_cast<unsigned long long>(owner_tid_),
        static_cast<unsigned long long>(MonotonicRawNanoseconds()),
        static_cast<unsigned long long>(calls_),
        static_cast<unsigned long long>(applicable_calls_),
        static_cast<unsigned long long>(distinct_inputs_),
        static_cast<unsigned long long>(repeated_inputs_),
        overflow_ ? 1 : 0,
        static_cast<unsigned long long>(timed_calls_),
        static_cast<unsigned long long>(total_ns_),
        static_cast<unsigned long long>(applicable_ns_),
        static_cast<unsigned long long>(repeated_ns_),
        static_cast<unsigned long long>(nested_calls_),
        BuildId(),
        static_cast<unsigned long long>(thread_affinity_violations_));
  }

  const char* site() const { return site_; }
  uint64_t calls() const { return calls_; }
  uint64_t applicable_calls() const { return applicable_calls_; }
  uint64_t distinct_inputs() const { return distinct_inputs_; }
  uint64_t repeated_inputs() const { return repeated_inputs_; }
  bool overflow() const { return overflow_; }
  uint64_t timed_calls() const { return timed_calls_; }
  uint64_t total_ns() const { return total_ns_; }
  uint64_t nested_calls() const { return nested_calls_; }

 private:
  const char* site_;
  const uint64_t owner_tid_;
  uint64_t calls_ = 0;
  uint64_t applicable_calls_ = 0;
  uint64_t distinct_inputs_ = 0;
  uint64_t repeated_inputs_ = 0;
  uint64_t thread_affinity_violations_ = 0;
  uint64_t timed_calls_ = 0;
  uint64_t total_ns_ = 0;
  uint64_t applicable_ns_ = 0;
  uint64_t repeated_ns_ = 0;
  uint64_t nested_calls_ = 0;
  bool overflow_ = false;
  uint64_t* slots_ = nullptr;
  // Innermost open scope of this counter on its thread; nested scopes hand
  // their elapsed time to it so every call is timed exclusively.
  RedundancyScope* active_scope_ = nullptr;
};

// Records one call, with its wall time, when the scope closes. Declare it at
// the top of the work the hypothesis would skip; set the key and the
// applicable flag whenever they become known before the scope ends. Scopes
// of one counter nest (a recursive site): each records its own time less
// the time of the scopes that ran inside it.
class RedundancyScope {
 public:
  explicit RedundancyScope(RedundancyCounter& counter,
                           uint64_t input_hash = 0,
                           bool applicable = false)
      : counter_(counter),
        input_hash_(input_hash),
        applicable_(applicable),
        active_(IsInScoredWindow()),
        start_ns_(active_ ? MonotonicRawNanoseconds() : 0),
        parent_(counter.active_scope_) {
    counter_.active_scope_ = this;
  }

  RedundancyScope(const RedundancyScope&) = delete;
  RedundancyScope& operator=(const RedundancyScope&) = delete;

  void SetKey(uint64_t input_hash) { input_hash_ = input_hash; }
  void SetApplicable(bool applicable) { applicable_ = applicable; }

  ~RedundancyScope() {
    counter_.active_scope_ = parent_;
    if (!active_)
      return;
    uint64_t end_ns = MonotonicRawNanoseconds();
    uint64_t elapsed_ns = end_ns > start_ns_ ? end_ns - start_ns_ : 0;
    if (parent_)
      parent_->child_ns_ += elapsed_ns;
    uint64_t exclusive_ns = elapsed_ns > child_ns_ ? elapsed_ns - child_ns_ : 0;
    counter_.RecordTimed(input_hash_, applicable_, exclusive_ns,
                         /*nested=*/parent_ != nullptr);
  }

 private:
  RedundancyCounter& counter_;
  uint64_t input_hash_;
  bool applicable_;
  const bool active_;
  const uint64_t start_ns_;
  RedundancyScope* const parent_;
  uint64_t child_ns_ = 0;
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
