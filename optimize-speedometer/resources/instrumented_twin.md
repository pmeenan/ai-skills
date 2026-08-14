# Release-like instrumented twin

Use this recipe verbatim. The counter logs, not an agent transcription, are
the raw evidence.

## Build once

1. Create a distinct output directory such as `out/perf_instrumented` with
   the same resolved GN args, compiler, PGO profile, and source SHA as the
   release-like baseline. It must resolve to `is_official_build=true`,
   `is_debug=false`, `chrome_pgo_phase=2`, and `use_thin_lto=true`.
2. Keep symbols/frame pointers recorded as provenance. They may differ from
   the score binary, but PGO/ThinLTO may not. `out/perf` remains the official
   symbols-on broad-profile build; `out/release` remains the symbol-free
   authoritative score build. Never use either name for the instrumented twin.
3. Add `chrome-cycle-profiling/resources/cycle_profiler.h` temporarily and
   build. A `perf_event_open` failure is a failed run, not a zero result.
4. Run an uninstrumented arm A versus instrumented arm B full-suite `ab2`
   with at least 32 balanced blocks, then reduce the untouched runner manifest:

   ```bash
   python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py calibrate-aa \
     --manifest <ab_results_manifest.json> --out <instrumentation-aa.json>
   ```

   Put the emitted overhead and artifact digest into every metadata file.
   The upper 95% confidence bound must be at most 1%.
   This A/A artifact may be reused by multiple opportunities only while arm B
   is the exact same instrumented browser SHA and build provenance. Any
   rebuild that changes the browser requires a fresh calibration. A 32-block
   calibration has the same 64-minute hard floor as a checkpoint and normally
   takes hours; start it once per stable build and wait for completion.

## Instrument one measurement thread

On the owning thread, call `CalibrateProbeOverhead()` and reject zero. Create
fresh `CycleBlock` objects on that same thread for each block and
`repetition|suite` group:

- `scored_total`: wrap the exact scored interval with
  `Accounting::kInclusive`;
- `mechanism`: wrap the smallest proposed work region with
  `Accounting::kExclusive`;
- `avoidable`: count only work proved avoidable by the invariant or oracle,
  using dual-path counting or scopes that do not nest inside `mechanism`.

### Critical Probe Invariants:
1. **User-Space PMU Reads Only (`_rdpmc`):**
   `ThreadCycleEvent` MUST read PMU counters via user-space `mmap` and `_rdpmc`
   (~15 cycles). Never use synchronous kernel `read(fd)` syscalls (~1,200 cycles)
   in hot microsecond-scale paths.
2. **Exact Scored-Window Gating (`IsInScoredWindow`):**
   Mechanism probes MUST be gated on `IsInScoredWindow()`. When executed outside
   the Speedometer 3 scoring window (e.g. initial navigation, stylesheet loading,
   unscored DOM setup, between-suite GC), probes MUST immediately return without
   calling `_rdpmc`, without accumulating cycles into the mechanism block, and
   without incrementing call counters. This prevents numerator cycle pollution
   where unscored setup cycles are added to the numerator while the denominator
   contains only scored-window cycles.
3. **Speedometer 3 Performance Mark Integration:**
   In `Performance::mark()` (`third_party/blink/renderer/core/timing/performance.cc`):
   - On `IsSpeedometerScoreStart(mark_name)` (`sp3-sync-start` / `sp3-async-start`):
     call `perf_instrumentation::SetScoredWindowActive(true)` and instantiate the
     inclusive `g_score_probe` on `GetGlobalScoredTotalBlock()`.
   - On `IsSpeedometerScoreEnd(mark_name)` (`sp3-sync-end` / `sp3-async-end`):
     call `perf_instrumentation::SetScoredWindowActive(false)` and destroy `g_score_probe`.
   - On `sp3-measurement-end`: invoke `FlushSpeedometerScoreMarks()` to emit `[SP3_CYCLE_ROW]`
     logs for all completed suite groups. **Never** perform file/stream I/O or `fflush`
     inside an active score timer.
4. **Reference Block Accessors (`CycleBlock&`):**
   Global block getters must return `inline CycleBlock& GetGlobal...()` referencing a
   `static thread_local CycleBlock block(CalibrateProbeOverhead())` to prevent accidental
   copies, slicing, or deleted copy-assignment invocations on underlying atomic state.
5. **Strict Probe Symmetry:**
   Baseline and candidate probe placements MUST be 100% structurally symmetric.
   **Never** place a probe inside a conditional branch such as `if (feature_enabled)`
   or `if (!has_work)`. The candidate must execute the identical probe boundaries
   as baseline; candidate speedup is measured by the reduction in work *between*
   the probes, never by skipping the probe itself.
6. **Adaptive Subsampling for High-Frequency Operations:**
   For operations called $>100,000$ times per suite run, set `sample_every` (e.g. 64
   or 256) so cumulative probe execution time remains strictly negligible.
7. **Sampling Profile Ceiling Sanity Check:**
   A mechanism's baseline exclusive cycle share cannot exceed the total sample share
   of its enclosing function in the release `perf record` profile (`sp3-prof-*`).

Never put an `avoidable` probe inside the `mechanism` probe: exclusive
parent accounting would subtract it from `mechanism.cycles`, making the row
invalid or misleading. Keep every scope participating in exclusive nesting
at `sample_every=1`; an unsampled child invocation cannot be subtracted from
its parent. A nested child's calibrated probe-boundary overhead remains in
the parent's exclusive result, so minimize such nesting and rely on the A/A
overhead gate to bound the residual tax.

Do not reuse a `CycleBlock` across threads. Same-block recursion, an ownership
violation, an invalid read, missing calibration, or a PMU running ratio below
0.99 invalidates the emitted row. Emit with `EmitCycleRow()` only after the
score interval closes. Never print or flush inside a score timer.

## Reduce logs without transcription

Keep the probe-free product tree separate from the instrumented tree. Stage
the product variant first and record `git write-tree` as `product_tree`. Save
one instrumentation-only patch, apply and stage that patch, then bind the
mapping:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py \
  bind-instrumentation --product-tree <probe-free-tree-hash> \
  --patch <instrumentation-only.patch> --out <tree-transform.json>
```

The command applies the patch to the product tree in a temporary Git index and
records the resulting `instrumented_tree`. Use the same patch digest for
baseline, oracle, and candidate; create a separate transform receipt for each
product tree. The instrumented build must come from that resulting tree. After
candidate measurement, reverse only the instrumentation patch: the remaining
staged tree must equal candidate `product_tree` and is what build/test receipts
and review bind. This avoids either landing probes or pretending the measured
binary came from the probe-free tree.

First write the metadata skeleton:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py scaffold \
  --opp <id> --mechanism-key <component/strategy> --profile-id <profile> \
  --variant baseline --out <baseline.metadata-skeleton.json>
```

Replace only the non-build `REPLACE` fields (trace classification/artifact,
instrumentation patch digest, and instrumentation A/A artifact/overhead).
Leave the build object untouched for `attach-provenance`. Do not add `blocks`.

Run the following on the configured bare-metal measurement host, in its
campaign checkout. `provenance` does not trust a pre-existing binary: it runs
`autoninja -C out/perf_instrumented chrome` itself, captures the build output,
then measures the resulting identity and attaches it to the skeleton:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py \
  provenance --browser out/perf_instrumented/chrome \
  --product-tree <probe-free-tree-hash> \
  --transform-artifact <tree-transform.json> --out <build-provenance.json>
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py \
  attach-provenance --metadata <baseline.metadata-skeleton.json> \
  --provenance <build-provenance.json> --out <baseline.metadata.json>
```

`provenance` records the bare-metal host/boot/kernel/CPU, staged tree, remote
rebuild receipt, browser SHA/build-id, resolved GN args, bundled Clang digest,
exact `.text`-section digest, and PGO profile from `toolchain.ninja`. Do not
type or copy any of those fields. A VM, changed tree, failed rebuild,
stale/missing browser, or candidate whose executable `.text` matches baseline
fails.

`build.source_tree` is the instrumented tree; `build.product_tree` is the
probe-free tree; `instrumentation.revision` is the instrumentation patch
SHA-256.

Still on that same host and boot, do not invoke Crossbench yourself and do not
create `[SP3_CYCLE_ROW]` text. Run at least three full-suite blocks through the
capture subcommand. It chooses a fresh nonce, sets the block environment,
invokes Crossbench, requires renderer PID/TID and kernel monotonic timestamps
inside its run bounds, verifies all 32 exact-scored suites, and extracts rows
directly from raw browser logs:

```bash
for block in 1 2 3; do
  python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py capture \
    --metadata <baseline.metadata.json> --variant baseline \
    --browser out/perf_instrumented/chrome --block "$block" \
    --enable-features Speedometer3Optimizations \
    --out-dir <baseline-block-$block> --out <baseline-capture-$block.json>
done
```

Then ingest only the runner-owned capture manifests:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py ingest \
  --metadata <baseline.metadata.json> \
  --capture-manifest <baseline-capture-1.json> \
  --capture-manifest <baseline-capture-2.json> \
  --capture-manifest <baseline-capture-3.json> --out <baseline.raw.json>
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py summarize \
  --raw <baseline.raw.json> --out <sizing.json>
```

`ingest` reopens every raw browser log, verifies its nonce and score marks,
reconstructs the extracted counter log byte-for-byte, and rebuilds every
block. Placeholder suite names, repeated synthetic totals, and zero-variance
paired effects fail. Repeat the same process for oracle and candidate source
trees/binaries, then use `compare`; baseline and variant may not use the same
Git tree or byte-identical browser.

The comparison reports both mechanism cycles removed and the paired change
in total scored cycles. A positive `moved_work_warning` means total work grew
with 95% confidence; the skeptic must not call that net work removal.

## Pilot before a long campaign

Before authorizing 20–40 landings, complete this chain for 3–5 candidates:

`emitted counters -> baseline sizing -> oracle -> candidate -> batch A/B`

The sixth landing is locked until a 32-or-more-block cumulative `out/release`
flag A/B has a positive 95% confidence interval. A positive point estimate
whose interval crosses zero leaves the pilot pending: increase the balanced
block count and remeasure. A statistically negative result fails the pilot.
Fix the harness rather than explaining away disagreement.
