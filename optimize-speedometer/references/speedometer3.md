# Speedometer 3 benchmark semantics

Read this reference before any Speedometer profile, mechanism capture, or
campaign-policy decision. Use the shared runbook and playbooks in
`../../optimize-campaign/` for the state machine.

## Adapter contract

- Adapter id: `speedometer3`
- Crossbench benchmark: `speedometer_3.1` (matches Pinpoint `speedometer3`)
- Payload: Chromium-pinned `third_party/speedometer/v3.1`
- Default workloads: 20 stories (`--stories=default`, matching Pinpoint)
- Available workloads: 32 stories (`--stories=all`, including optional stories)
- Suite score: `Score`, higher is better
- Workload scalar: story total time, lower is better
- Metric model: `speedometer-story-v1`
- Exact profile intervals: benchmark score marks captured by the existing
  monotonic-mark probe

The aggregate score is higher-is-better. Story values emitted in detailed
results are total times and are lower-is-better. Never use one story's time as
the aggregate score.

Chromium's Telemetry `speedometer3` currently inherits `Speedometer31`. Keep
the Crossbench benchmark, result filename (`speedometer_3.1.json`), and local
payload on that same version. Recheck the mapping in
`tools/perf/benchmarks/speedometer3.py` when updating Chromium; do not silently
follow a moving alias during a campaign. Version-specific `speedometer_3.0`
requests are rejected rather than reinterpreted as 3.1.

Use `--stories=default` for campaign discovery, A/A calibration, and full-suite
score checkpoints. Pinpoint's unfiltered `Speedometer3` story leaves the
payload's default-enabled workloads selected. `--stories=all` explicitly
enables all 32 workloads and remains available for extended investigation;
its aggregate is a different workload set and cannot replace a default-suite
checkpoint or be compared directly with Pinpoint's default score.

Existing 3.0 measurements and calibration remain evidence for 3.0 only.
Start fresh 3.1 evidence and calibration under the updated skill digest;
do not relabel old manifests or rewrite an in-use campaign's history.

## Exact profile policy

- Admit only the sync and async timers that feed Speedometer's score.
  Outer-suite `[SP3_MONO_TIME]` intervals are diagnostic.
- Require `interval_kind: exact-scored` and
  `metric_weighting: speedometer-story-v1`.
- Decompose all 20 default stories (or all 32 for explicit extended coverage) under
  `analysis/stories/<story>/`, scoped to the renderer main thread. Every share
  is local to that story's main-thread scored cycles; frontier identities
  remain story-qualified; each report carries its score-time composition and
  portability flags.
- Rank at a 1% local floor and qualify against max(1%, 2 × the story's
  calibrated MDE). Require at least 100 nominal main-thread samples at the
  floor in every story. Increase repetitions rather than dropping a failing
  story; the starting policy is 32 repetitions with fixed-period sampling
  (875,000 cycles, about 4 kHz per CPU at the locked base clock).
- Treat the equal-weight full-suite profile as diagnostic. It never supplies
  campaign shares or mechanism priorities.
- Rank each opportunity by its estimated effect on its own `target_story`.
  Cross-story benefit is a noted bonus, never summed or divided by workload count.
- Consult `references/discarded-candidates/INDEX.md` and the relevant subsystem
  file to verify that proposed mechanisms do not duplicate previously invalidated
  hypotheses or anti-patterns.

Install the exact mark probe from
`../../optimize-campaign/assets/speedometer3/performance-mark-monotonic-probe.patch`
once on a new campaign branch. It replaces the older outer-window probe. Run
`git apply --check`, compile the affected Blink target with warnings as
errors, and run the exact-interval smoke test. The probe buffers marks and
flushes outside scored intervals; do not add and remove it around individual
runs.

Example profile capture:

```bash
python3 .agents/skills/optimize-campaign/scripts/remote_measure.py \
  --mode profile --benchmark speedometer3 --ref <campaign-tip> \
  --stories default --repetitions 32 --share-floor-pct 1.0 \
  --enable-features Speedometer3Optimizations \
  --summary-out <capture.json>
```

## Mechanism evidence policy

Speedometer mechanism sizing is operational. JetStream mechanism sizing is
not an alternate use of this path.

- Gate every probe on `IsInScoredWindow()`. Outside score timers, return
  before PMU reads or accumulation.
- Emit rows only after the scored interval, at `sp3-measurement-end`, through
  `FlushSpeedometerScoreMarks()`. Never perform in-band I/O inside a timer.
- Use user-space `_rdpmc` reads through `mmap_page`; synchronous `read(fd)`
  syscalls are too expensive for micro-probes.
- Place baseline and candidate probes symmetrically. Never put a probe only
  inside the optimization or feature-enabled branch.
- Size and verify the target story alone, with at least four repetitions per
  block and a default of ten. Use at least three independent blocks.
- Require the mechanism's baseline exclusive share not to exceed its enclosing
  function's sampled story share.
- Require the avoidable-share lower confidence bound to meet the target
  story's qualification floor (max(1%, 2 × calibrated MDE)). Profile share is
  not a score forecast.
- Capture on the campaign display (`--display :1 --display-vt 9` on the Linux
  box); `compare` refuses arms from different rendering surfaces.

Both metadata creation and capture name the adapter explicitly:

```bash
python3 .agents/skills/optimize-campaign/scripts/mechanism_evidence.py scaffold \
  --benchmark speedometer3 --opp <id> \
  --mechanism-key <component/strategy> --profile-id <profile> \
  --target-story <story> --variant baseline --out <metadata.json>
python3 .agents/skills/optimize-campaign/scripts/mechanism_evidence.py capture \
  --benchmark speedometer3 --metadata <filled-metadata.json> \
  --variant baseline --browser out/perf_instrumented/chrome \
  --block 1 --repetitions 10 \
  --enable-features Speedometer3Optimizations \
  --out-dir <block-dir> --out <capture.json>
```

## Pilot and checkpoint policy

- Treat the first five candidates as a fail-closed pilot. Block the sixth
  landing until a targeted A/B over the exact landed target-story set has a
  positive 95% CI and a same-tip default-suite A/B has no statistically
  significant regression.
- Reprofile and record a targeted checkpoint after at most five runtime
  changes. Keep the default-suite checkpoint at most ten landings stale.
- After the pilot, a current-tip targeted CI that is not positive blocks the
  next landing. A retained default-suite statistically significant regression
  also blocks.
- Use at least 32 balanced blocks for authoritative checkpoints. Thirty-two
  blocks produce 128 page-load repetitions. The existing conservative
  64-minute duration floor applies to both default-suite and all-story runs;
  it is a plausibility check, not a calibrated 3.1 duration or noise estimate.
- Use the MDE to preregister one larger confirmation when needed. Do not keep
  drawing fresh 95% tests until one passes. Story flags in the runner
  manifest are Bonferroni-adjusted over all stories plus the suite; the
  unadjusted list is diagnostic and a null run produces about one such flag
  per 20 stories.
- Validate on the Mac M1 PGO Pinpoint bot; rendering-backend and
  font-shaping findings need that confirmation before more local host time.

Use official PGO phase 2 ThinLTO `out/perf` for exact profiles and symbol-free
`out/release` for score evidence. A release-like `out/perf_instrumented` twin
may retain symbols but must match the product build's consequential optimizer
settings and recorded provenance.
