# Release-like instrumented twin

Use this recipe verbatim. The counter logs, not an agent transcription, are
the raw evidence.

## Build once

1. Create a distinct output directory such as `out/perf_instrumented` with
   the same resolved GN args, compiler, PGO profile, and source SHA as the
   release-like baseline. It must resolve to `is_official_build=true`,
   `is_debug=false`, `chrome_pgo_phase=2`, and `use_thin_lto=true`.
2. Keep symbols/frame pointers recorded as provenance. They may differ from
   the score binary, but PGO/ThinLTO may not.
3. Add `chrome-cycle-profiling/resources/cycle_profiler.h` temporarily and
   build. A `perf_event_open` failure is a failed run, not a zero result.
4. Run an instrumented versus uninstrumented A/A. Reject overhead above 1%.

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

First write metadata only:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py scaffold \
  --opp <id> --mechanism-key <component/strategy> --profile-id <profile> \
  --variant baseline --out <baseline.metadata.json>
```

Replace only the `REPLACE` metadata fields. Do not add `blocks`. Then ingest
one or more harness logs:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py ingest \
  --metadata <baseline.metadata.json> --log <block-1.log> --log <block-2.log> \
  --log <block-3.log> --out <baseline.raw.json>
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py summarize \
  --raw <baseline.raw.json> --out <sizing.json>
```

`ingest` digest-binds every log and reconstructs every block. Editing a raw
counter after ingestion makes validation fail. Repeat the same process for
oracle and candidate metadata/logs, then use `compare`.

The comparison reports both mechanism cycles removed and the paired change
in total scored cycles. A positive `moved_work_warning` means total work grew
with 95% confidence; the skeptic must not call that net work removal.

## Pilot before a long campaign

Before authorizing 20–40 landings, complete this chain for 3–5 candidates:

`emitted counters -> baseline sizing -> oracle -> candidate -> batch A/B`

Proceed only if the mechanistic direction and cumulative A/B direction agree
and all instrumentation quality fields remain zero. Fix the harness rather
than explaining away disagreement.
