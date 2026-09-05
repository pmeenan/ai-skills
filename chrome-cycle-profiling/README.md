# Chromium cycle profiling in campaigns

Use this skill for exact scored-window CPU profiles and instrumented mechanism
measurements. CPU share locates work; it does not establish wall-clock savings.
The [shared campaign](../optimize-campaign/README.md) owns state, measurement
plans, reviews and admission. Timing/parallelism hypotheses use its separate
trace-based latency route.

## Start profiling for a new campaign

> Use optimize-campaign with optimize-speedometer and chrome-cycle-profiling to
> start campaign `<name>` in `~/src/chromium/src`, from baseline `<full commit>`
> on display `:1` (VT 9). Check for an existing
> campaign or active measurement first. Use Speedometer 3.1's 20 default
> workloads and exact scored sync/async windows. Establish the required host
> calibration, collect independent profiles using the recorded profile build,
> and inspect inclusive callers and unnecessary subtrees before choosing leaves.
> Preserve raw perf/trace artifacts and per-story denominators. Stop after
> producing a source-grounded opportunity frontier; do not implement candidates
> or claim a score improvement from sample shares.

## Resume profiling or sizing part-way through

> Resume chrome-cycle-profiling within the existing campaign `<absolute campaign
> directory>` in `~/src/chromium/src`. Audit its ledger, profile capture IDs,
> exact-window marks, build identities, probe calibration and retained artifacts.
> Check for a running measurement and follow it before taking the shared host
> lease. Continue the unfinished profile or mechanism gate using the recorded
> benchmark/workloads, feature state and skill digest. Keep numerator and
> denominator on the same thread/process scope; measure applicability and added
> work, and use interleaved paired captures. Do not create a new campaign,
> fabricate missing counters or treat a failed PMU read as zero cost.

Every capture names its rendering surface: campaign runs use the GPU-backed
X display (`--display :1 --display-vt 9` on the Linux box) inside a tuner
session; headless is diagnostic only. Story silos are renderer main-thread
only, sampled at a fixed period near 4 kHz per CPU with 32 repetitions.

For standalone diagnosis, explicitly name the build, benchmark, workloads,
display and measurement interval. Such output becomes campaign evidence only after the
shared pipeline validates provenance and its required gates.
