#ifndef TOOLS_PERF_MECHANISM_CYCLE_PROFILER_H_
#define TOOLS_PERF_MECHANISM_CYCLE_PROFILER_H_

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunsafe-buffer-usage"
#pragma clang diagnostic ignored "-Wunknown-pragmas"

#ifdef UNSAFE_BUFFERS_BUILD
#pragma allow_unsafe_buffers
#endif

// Temporary Linux-only instrumentation for scored mechanism evidence.
// Remove this from production diffs. Emit rows only outside score timers.

#include <asm/unistd.h>
#include <linux/perf_event.h>
#include <sys/mman.h>
#include <unistd.h>

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
#include <x86intrin.h>
#define SP3_HAS_RDPMC 1
#endif

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

namespace perf_instrumentation {

struct CounterRead {
  uint64_t value = 0;
  uint64_t time_enabled = 0;
  uint64_t time_running = 0;
};

class ThreadCycleEvent {
 public:
  ThreadCycleEvent(const ThreadCycleEvent&) = delete;
  ThreadCycleEvent& operator=(const ThreadCycleEvent&) = delete;

  static ThreadCycleEvent& Get() {
    // Intentionally leaked to avoid a non-trivial thread_local destructor.
    thread_local auto* event = new ThreadCycleEvent;
    return *event;
  }

  bool available() const { return fd_ >= 0; }
  int open_errno() const { return open_errno_; }

  bool Read(CounterRead* result) const {
    if (fd_ < 0)
      return false;
#if defined(SP3_HAS_RDPMC)
    if (mmap_page_ && mmap_page_->cap_user_rdpmc) {
      uint32_t seq;
      uint64_t count;
      uint64_t time_enabled, time_running;
      do {
        seq = mmap_page_->lock;
        std::atomic_thread_fence(std::memory_order_acquire);
        uint32_t idx = mmap_page_->index;
        if (idx == 0)
          break;
        count = mmap_page_->offset + static_cast<uint64_t>(_rdpmc(idx - 1));
        time_enabled = mmap_page_->time_enabled;
        time_running = mmap_page_->time_running;
        std::atomic_thread_fence(std::memory_order_acquire);
      } while (mmap_page_->lock != seq);
      if (mmap_page_->index != 0) {
        result->value = count;
        result->time_enabled = time_enabled;
        result->time_running = time_running;
        return true;
      }
    }
#endif
    struct ReadFormat {
      uint64_t value;
      uint64_t time_enabled;
      uint64_t time_running;
    } data = {};
    if (read(fd_, &data, sizeof(data)) != sizeof(data))
      return false;
    result->value = data.value;
    result->time_enabled = data.time_enabled;
    result->time_running = data.time_running;
    return true;
  }

 private:
  ThreadCycleEvent() {
    perf_event_attr attr = {};
    attr.type = PERF_TYPE_HARDWARE;
    attr.size = sizeof(attr);
    attr.config = PERF_COUNT_HW_CPU_CYCLES;
    attr.exclude_kernel = 1;
    attr.exclude_hv = 1;
    attr.read_format = PERF_FORMAT_TOTAL_TIME_ENABLED |
                       PERF_FORMAT_TOTAL_TIME_RUNNING;
    // pid=0 measures the calling thread; cpu=-1 follows CPU migration.
    fd_ = static_cast<int>(
        syscall(__NR_perf_event_open, &attr, 0, -1, -1, 0));
    if (fd_ < 0) {
      open_errno_ = errno;
    } else {
      void* page = mmap(nullptr, 4096, PROT_READ, MAP_SHARED, fd_, 0);
      if (page != MAP_FAILED) {
        mmap_page_ = static_cast<struct perf_event_mmap_page*>(page);
      }
    }
  }

  // Leaked by Get(); retained for correctness if instantiated another way.
  ~ThreadCycleEvent() {
    if (mmap_page_) {
      munmap(mmap_page_, 4096);
    }
    if (fd_ >= 0)
      close(fd_);
  }

  int fd_ = -1;
  int open_errno_ = 0;
  struct perf_event_mmap_page* mmap_page_ = nullptr;
};

inline uint64_t CurrentTid() {
  return static_cast<uint64_t>(syscall(__NR_gettid));
}

inline bool CounterDelta(const CounterRead& start,
                         const CounterRead& end,
                         uint64_t* scaled_cycles,
                         uint64_t* enabled,
                         uint64_t* running) {
  if (end.value < start.value || end.time_enabled <= start.time_enabled ||
      end.time_running <= start.time_running) {
    return false;
  }
  const uint64_t raw = end.value - start.value;
  *enabled = end.time_enabled - start.time_enabled;
  *running = end.time_running - start.time_running;
  if (*running > *enabled)
    return false;
  const long double scaled = static_cast<long double>(raw) *
                             static_cast<long double>(*enabled) /
                             static_cast<long double>(*running);
  if (scaled < 0 || scaled > static_cast<long double>(UINT64_MAX))
    return false;
  *scaled_cycles = static_cast<uint64_t>(scaled);
  return true;
}

// Calibrate on the measurement thread and in the same build as the probes.
// Zero means calibration failed and causes every scope to be marked invalid.
inline uint64_t CalibrateProbeOverhead() {
  constexpr size_t kSamples = 101;
  std::array<uint64_t, kSamples> samples = {};
  ThreadCycleEvent& event = ThreadCycleEvent::Get();
  if (!event.available())
    return 0;
  for (size_t i = 0; i < kSamples; ++i) {
    CounterRead start;
    CounterRead end;
    uint64_t enabled = 0;
    uint64_t running = 0;
    if (!event.Read(&start) || !event.Read(&end) ||
        !CounterDelta(start, end, &samples[i], &enabled, &running)) {
      return 0;
    }
  }
  std::sort(samples.begin(), samples.end());
  return samples[kSamples / 2];
}

enum class Accounting { kExclusive, kInclusive };

struct CycleBlock {
  explicit CycleBlock(uint64_t calibrated_overhead = 0)
      : owner_tid(CurrentTid()), probe_overhead_cycles(calibrated_overhead) {}

  bool CheckOwner() {
    if (owner_tid != CurrentTid()) {
      thread_affinity_violations.fetch_add(1, std::memory_order_relaxed);
      return false;
    }
    return true;
  }

  const uint64_t owner_tid;
  uint64_t calls = 0;
  uint64_t applicable_calls = 0;
  uint64_t sampled_calls = 0;
  uint64_t cycles = 0;
  uint64_t probe_overhead_cycles = 0;
  uint64_t time_enabled = 0;
  uint64_t time_running = 0;
  uint64_t multiplexed_samples = 0;
  uint64_t invalid_reads = 0;
  uint64_t unavailable_reads = 0;
  uint64_t uncalibrated_scopes = 0;
  uint64_t nested_same_block_violations = 0;
  std::atomic<uint64_t> thread_affinity_violations = 0;
};

class ScopedCycleProbe {
 public:
  // Subsampling does not compose with exclusive parents: an unsampled child
  // cannot subtract its cycles. Use sample_every=1 for every scope in an
  // exclusive nesting chain. Child boundary overhead also remains charged to
  // the parent; keep nesting shallow and enforce the instrumentation A/A gate.
  ScopedCycleProbe(CycleBlock& block,
                   bool applicable,
                   Accounting accounting = Accounting::kExclusive,
                   uint32_t sample_every = 1)
      : block_(block),
        accounting_(accounting),
        sample_every_(sample_every ? sample_every : 1) {
    if (!block_.CheckOwner())
      return;
    ++block_.calls;
    if (!applicable)
      return;
    ++block_.applicable_calls;
    if (block_.applicable_calls % sample_every_ != 0)
      return;
    if (block_.probe_overhead_cycles == 0) {
      ++block_.uncalibrated_scopes;
      return;
    }
    for (ScopedCycleProbe* scope = active_scope_; scope; scope = scope->parent_) {
      if (&scope->block_ == &block_) {
        ++block_.nested_same_block_violations;
        return;
      }
    }
    event_ = &ThreadCycleEvent::Get();
    if (!event_->available()) {
      ++block_.unavailable_reads;
      return;
    }
    if (!event_->Read(&start_)) {
      ++block_.invalid_reads;
      return;
    }
    parent_ = active_scope_;
    active_scope_ = this;
    active_ = true;
  }

  ScopedCycleProbe(const ScopedCycleProbe&) = delete;
  ScopedCycleProbe& operator=(const ScopedCycleProbe&) = delete;

  ~ScopedCycleProbe() {
    if (!active_)
      return;
    active_scope_ = parent_;
    CounterRead end;
    uint64_t inclusive = 0;
    uint64_t enabled = 0;
    uint64_t running = 0;
    if (!event_->Read(&end) ||
        !CounterDelta(start_, end, &inclusive, &enabled, &running)) {
      ++block_.invalid_reads;
      return;
    }
    block_.time_enabled += enabled;
    block_.time_running += running;
    if (running < enabled)
      ++block_.multiplexed_samples;
    const uint64_t net = inclusive > block_.probe_overhead_cycles
                             ? inclusive - block_.probe_overhead_cycles
                             : 0;
    const uint64_t exclusive = net > child_cycles_ ? net - child_cycles_ : 0;
    block_.cycles +=
        (accounting_ == Accounting::kInclusive ? net : exclusive) * sample_every_;
    ++block_.sampled_calls;
    if (parent_)
      parent_->child_cycles_ += net;
  }

 private:
  CycleBlock& block_;
  Accounting accounting_;
  ThreadCycleEvent* event_ = nullptr;
  ScopedCycleProbe* parent_ = nullptr;
  CounterRead start_;
  uint64_t child_cycles_ = 0;
  uint32_t sample_every_ = 1;
  bool active_ = false;

  static inline thread_local ScopedCycleProbe* active_scope_ = nullptr;
};

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

inline const char* CurrentProcessType() {
  char command_line[8192] = {};
  FILE* input = std::fopen("/proc/self/cmdline", "rb");
  if (!input)
    return "unknown";
  const size_t size = std::fread(command_line, 1, sizeof(command_line) - 1, input);
  std::fclose(input);
  size_t offset = 0;
  while (offset < size) {
    const char* argument = command_line + offset;
    const size_t length = std::strlen(argument);
    if (std::strcmp(argument, "--type=renderer") == 0)
      return "renderer";
    offset += length + 1;
  }
  return "other";
}

inline uint64_t MonotonicRawNanoseconds() {
  struct timespec timestamp = {};
  if (clock_gettime(CLOCK_MONOTONIC_RAW, &timestamp) != 0)
    return 0;
  return static_cast<uint64_t>(timestamp.tv_sec) * 1000000000ULL +
         static_cast<uint64_t>(timestamp.tv_nsec);
}

inline void EmitCycleRow(FILE* output,
                         uint32_t block,
                         const char* repetition_suite,
                         const CycleBlock& mechanism,
                         const CycleBlock& avoidable,
                         const CycleBlock& scored_total) {
  const ThreadCycleEvent& event = ThreadCycleEvent::Get();
  const char* capture_nonce = std::getenv("SP3_CYCLE_CAPTURE_NONCE");
  block = CaptureBlockFromEnvironment(block);
  std::fprintf(output, "[SP3_CYCLE_ROW] {\"schema_version\":1,\"block\":%u,"
                       "\"capture_nonce\":\"", block);
  WriteJsonString(output, capture_nonce);
  std::fprintf(output, "\",\"group\":\"");
  WriteJsonString(output, repetition_suite);
  std::fprintf(output, "\",\"pid\":%llu,\"tid\":%llu,\"process_type\":\"",
               static_cast<unsigned long long>(getpid()),
               static_cast<unsigned long long>(CurrentTid()));
  std::fprintf(output, "%s", CurrentProcessType());
  std::fprintf(
      output,
      "\",\"emitted_monotonic_raw_ns\":%llu,"
      "\"calls\":%llu,\"applicable_calls\":%llu,"
      "\"exclusive_cycles\":%llu,\"avoidable_cycles\":%llu,"
      "\"total_scored_cycles\":%llu,\"probe_overhead_cycles\":%llu,"
      "\"time_enabled\":%llu,\"time_running\":%llu,"
      "\"multiplexed_samples\":%llu,\"invalid_reads\":%llu,"
      "\"unavailable_reads\":%llu,\"uncalibrated_scopes\":%llu,"
      "\"nested_violations\":%llu,\"thread_affinity_violations\":%llu,"
      "\"perf_open_errno\":%d}\n",
      static_cast<unsigned long long>(MonotonicRawNanoseconds()),
      static_cast<unsigned long long>(mechanism.calls),
      static_cast<unsigned long long>(mechanism.applicable_calls),
      static_cast<unsigned long long>(mechanism.cycles),
      static_cast<unsigned long long>(avoidable.cycles),
      static_cast<unsigned long long>(scored_total.cycles),
      static_cast<unsigned long long>(mechanism.probe_overhead_cycles),
      static_cast<unsigned long long>(mechanism.time_enabled +
                                      avoidable.time_enabled +
                                      scored_total.time_enabled),
      static_cast<unsigned long long>(mechanism.time_running +
                                      avoidable.time_running +
                                      scored_total.time_running),
      static_cast<unsigned long long>(mechanism.multiplexed_samples +
                                      avoidable.multiplexed_samples +
                                      scored_total.multiplexed_samples),
      static_cast<unsigned long long>(mechanism.invalid_reads +
                                      avoidable.invalid_reads +
                                      scored_total.invalid_reads),
      static_cast<unsigned long long>(mechanism.unavailable_reads +
                                      avoidable.unavailable_reads +
                                      scored_total.unavailable_reads),
      static_cast<unsigned long long>(mechanism.uncalibrated_scopes +
                                      avoidable.uncalibrated_scopes +
                                      scored_total.uncalibrated_scopes),
      static_cast<unsigned long long>(mechanism.nested_same_block_violations +
                                      avoidable.nested_same_block_violations +
                                      scored_total.nested_same_block_violations),
      static_cast<unsigned long long>(
          mechanism.thread_affinity_violations.load(std::memory_order_relaxed) +
          avoidable.thread_affinity_violations.load(std::memory_order_relaxed) +
          scored_total.thread_affinity_violations.load(
              std::memory_order_relaxed)),
      event.open_errno());
  std::fflush(output);
}

}  // namespace perf_instrumentation

#pragma clang diagnostic pop

#endif  // TOOLS_PERF_MECHANISM_CYCLE_PROFILER_H_
