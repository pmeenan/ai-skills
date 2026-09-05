# Evidence model

Load this reference before collecting or interpreting performance evidence.

## Discovery

Use profiles restricted to the exact intervals that contribute to the score.
Preserve workload silos and process coverage. Treat samples outside the scored
window as diagnostic only.

## Mechanism sizing

Use paired, instrumented captures to measure the concrete work removed or
added. Bind captures to source, binary, host boot, skill digest, benchmark,
metric model, and interval contract. Instrumentation results do not establish
benchmark score movement.

## Score claims

Use randomized balanced blocks and raw per-repetition results. Recompute
statistics from the raw values. Acceptance uses the randomized block as the
independent unit; retain every page-load result within its block. Benchmark-internal iterations are nested implementation details.

Do not transfer noise assumptions between benchmarks. A new benchmark starts
uncalibrated and must pass A/A calibration before thresholds become policy.

Latency reductions have a separate trace-backed route; see
[measurement-policy.md](measurement-policy.md) for causal paths, aggregate
headroom, fixed-plan decisions and authenticated admission.
