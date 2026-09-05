// Deterministic mock-PMU consumer; never opens a real perf event.

#include <asm/unistd.h>
#include <linux/perf_event.h>
#include <sys/mman.h>
#include <unistd.h>
#include <x86intrin.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <cassert>
#include <vector>
static int tid_calls = 0;
static uint64_t clock_value = 0;
static std::vector<uint64_t> readings;
static size_t position = 0;
static long MockSyscall(long n, ...) {
  if (n == __NR_gettid) { ++tid_calls; return 1234; }
  errno = EPERM; return -1;
}
static uint64_t MockTsc() { return ++clock_value * 100; }
static uint64_t MockPmc(unsigned) {
  assert(position < readings.size());
  return readings[position++];
}
#define private public
#define syscall MockSyscall
#define __rdtsc MockTsc
#undef _rdpmc
#define _rdpmc MockPmc
#include "cycle_profiler.h"
#undef private
#undef syscall
#undef __rdtsc
#undef _rdpmc
using namespace perf_instrumentation;
static perf_event_mmap_page page = {};
static void SetReads(std::initializer_list<uint64_t> values) {
 readings = values; position = 0; clock_value = 0;
 page.cap_user_rdpmc = 1;
}
int main() {
  uint64_t cycles, enabled, running;
  assert(CounterDelta({100,100,100},{300,300,300},&cycles,&enabled,&running) && cycles==200);
  assert(CounterDelta({100,100,100},{300,500,300},&cycles,&enabled,&running) && cycles==400);
  assert(!CounterDelta({100,100,100},{300,100,100},&cycles,&enabled,&running));
  assert(!CounterDelta({100,100,100},{300,200,300},&cycles,&enabled,&running));
  assert(!CounterDelta({100,100,100},{99,200,200},&cycles,&enabled,&running));
  assert(!CounterDelta({0,0,0},{UINT64_MAX,2,1},&cycles,&enabled,&running));
  std::puts("PASS arithmetic: direct, scaled, zero-time rejection, invalid-ratio rejection, backward rejection, overflow rejection");
  auto& event=ThreadCycleEvent::Get();
  auto& total=GetGlobalScoredTotalBlock();
  assert(CalibrateProbeOverhead()==0);
  page.cap_user_time=1; page.pmc_width=64; page.index=1; page.time_mult=1;
  event.fd_=100; event.mmap_page_=&page;
  total.probe_overhead_cycles=10;
  SetScoredWindowActive(true);
  {
    CycleBlock a(10), b(10);
    SetReads({100,200,400,600});
    int before=tid_calls;
    { ScopedCycleProbe outer(a,true); { ScopedCycleProbe inner(b,true); } }
    assert(a.cycles==300 && b.cycles==190);
    assert(tid_calls == before);
    std::printf("PASS nested: outer=300 child=190 (child boundary overhead retained); hot-path gettid syscalls=%d\n",tid_calls-before);
  }
  {
    CycleBlock a(10);
    SetReads({100,600});
    { ScopedCycleProbe outer(a,true); { ScopedCycleProbe inner(a,true); } }
    assert(a.nested_same_block_violations==1);
    std::puts("PASS same-block recursion detected");
  }
  {
    CycleBlock a(10), b(10);
    SetReads({100,200,600});
    { ScopedCycleProbe outer(a,true); { ScopedCycleProbe inner(b,true); page.cap_user_rdpmc=0; } page.cap_user_rdpmc=1; }
    assert(b.invalid_reads==1 && b.cycles==0);
    assert(a.cycles==490);
    std::puts("PASS failed child end-read marked invalid; parent retains child work, consumer must reject whole row");
  }
  {
    CycleBlock a(10), attr(10);
    SetReads({100,600});
    { ScopedCycleProbe probe(a,true,Accounting::kExclusive,1,false,&attr); }
    assert(a.cycles==490 && attr.cycles==490 && attr.calls==1);
    std::puts("PASS attributed cycles track mechanism cycles");
  }
  {
    CycleBlock a(10);
    SetReads({100,600});
    SetScoredWindowActive(false);
    { ScopedCycleProbe probe(a,true); }
    assert(a.calls==0 && position==0);
    SetScoredWindowActive(true);
    std::puts("PASS initialized unscored probe does not count or read PMU");
  }
  {
    CycleBlock a(10), attr(10);
    SetReads({100,600});
    { ScopedCycleProbe probe(a,true,Accounting::kExclusive,1,false,&a); }
    assert(a.invalid_reads == 1 && a.cycles == 0);
    std::printf("PASS rejected aliased attribution: calls=%llu cycles=%llu sampled_calls=%llu\n",(unsigned long long)a.calls,(unsigned long long)a.cycles,(unsigned long long)a.sampled_calls);
  }
  {
    CycleBlock a(10), b(10);
    SetReads({100,600});
    { ScopedCycleProbe outer(a,true); { ScopedCycleProbe inner(b,true,Accounting::kExclusive,64); } }
    assert(a.invalid_reads > 0 && b.invalid_reads > 0);
    std::printf("PASS rejected subsampled child: parent cycles=%llu child=%llu invalid=%llu\n",(unsigned long long)a.cycles,(unsigned long long)b.cycles,(unsigned long long)(a.invalid_reads+b.invalid_reads));
  }
}
